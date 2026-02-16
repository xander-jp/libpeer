# libpeer + RP2350 WebRTC HID-USB Mouse

Firmware for Pico 2W (RP2350) that receives mouse commands over a WebRTC DataChannel and relays them to a host PC as a USB HID Mouse device, leveraging the dual-core architecture.

## Architecture: Dual-Core Split

```
┌─────────────────────────────────────────────────────────┐
│  Core 1 — CYW43 / WiFi / WebRTC                        │
│                                                         │
│  cyw43_arch_init()                                      │
│   → WiFi (scan → auth → DHCP)                          │
│   → DNS → Signaling Server (HTTP POST)                  │
│   → ICE → DTLS handshake → SCTP → DataChannel open     │
│   → peer_connection_loop() + keepalive (15s ± jitter)   │
│                                                         │
│  onmessage() → queue_try_add(&g_queue, &entry)          │
└───────────────────────┬─────────────────────────────────┘
                        │ multicore queue (lock-free)
┌───────────────────────▼─────────────────────────────────┐
│  Core 0 — USB HID Mouse                                │
│                                                         │
│  board_init() → tusb_init()                             │
│   → tud_task() + hid_task() tight loop                  │
│                                                         │
│  hid_task() → queue_try_remove(&g_queue, &itm)          │
│   → sscanf "op dx dy" → tud_hid_mouse_report()         │
└─────────────────────────────────────────────────────────┘
```

### Why Dual-Core Separation

- **CYW43 IRQ isolation**: Calling `cyw43_arch_init()` on Core1 binds the WiFi background worker IRQs to Core1, preventing interference with Core0's `USBCTRL_IRQ`.
- **USB requires a tight loop**: `tud_task()` will timeout the USB protocol if blocked. It cannot share a core with heavy WiFi/DTLS processing.

## Critical: Deferred USB Initialization

**This is the single most important design decision.**

USB device initialization (`board_init()` → `tusb_init()`) on Core0 must be **deferred** until the WebRTC session on Core1 has fully completed (ICE → DTLS → USRSCTP → DataChannel open).

```c
// main() — Core 0
multicore_launch_core1(core1_entry);

// Wait until DataChannel is ready (first queue entry arrives)
while (1) {
    queue_entry_t itm;
    if (queue_try_remove(&g_queue, &itm)) { break; }
    sleep_ms(100);
}

// Only NOW initialize USB
board_init();
irq_set_priority(USBCTRL_IRQ, 0);
tusb_init();
```

### Why This Matters

Initializing CYW43 (WiFi) and TinyUSB simultaneously on the Pico 2W **exceeds the power budget**. During the DTLS handshake and USRSCTP negotiation, the CYW43 chip draws peak current. Bringing up the USB PHY at the same time causes:

```
TinyUSB PANIC: EP0 is already available
```

This panic indicates that endpoint 0 has entered an invalid hardware state. The root cause is the USB controller registers becoming unstable due to insufficient power.

**Solution**: Defer Core0's USB initialization until Core1's DTLS + USRSCTP completes and the DataChannel opens — i.e., after the power peak has passed. The trigger is successfully dequeuing the first DataChannel message from the multicore queue.

## DataChannel Protocol

### Single command
```json
{"type": "mouse", "command": "0 5 -3"}
```

### Batch commands
```json
{"type": "mouse", "commands": ["0 5 -3", "0 2 1", "0 0 0"]}
```

Command format: `"op dx dy"` (space-separated)
- `op`: button state (0=none, 1=left, 2=right, 4=middle)
- `dx`: X-axis delta (-127 to 127)
- `dy`: Y-axis delta (-127 to 127)

## Build

```bash
export WIFI_SSID="your-ssid"
export WIFI_PASSWORD="your-password"
export SIGNALING_URL="http://your-server:8080/webrtc"
export SIGNALING_TOKEN="optional-token"

cd cmake.rp2350
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

Target board: `pico2_w` (RP2350)

Output: `rp2350bm-hidusb.uf2`

## USB Device Identity

| Field        | Value          |
|-------------|----------------|
| VID         | `0x413C`       |
| PID         | `0x301A`       |
| Device      | mx-mouse       |
| Protocol    | HID Boot Mouse |

## Timing Sequence (typical)

```
[TIMING] Boot complete: ~2000 ms
[TIMING] WiFi scan start
[TIMING] WiFi auth/assoc done
[TIMING] DHCP bound
[TIMING] DNS resolved
[TIMING] Signaling server connect
[TIMING] ICE checking → connected → completed
[TIMING] DataChannel opened (SCTP ready)
         ← Core0 USB initialization starts here →
[TIMING] First message TX / RX
```

## LED Feedback

| Event              | Pattern              |
|-------------------|----------------------|
| WiFi connected    | 100ms x 5 blinks    |
| DataChannel TX    | 100ms x 3 blinks    |
| DataChannel RX    | 20ms x 15 blinks    |

## Keepalive

DataChannel keepalive messages are sent at 15-second intervals with ±20% jitter to prevent NAT table expiry from dropping the session.

## Disconnect Recovery: Watchdog Reboot

When the PeerConnection enters `FAILED` or `DISCONNECTED` state (e.g. WiFi drops, remote peer closes, DTLS timeout), the firmware triggers a full hardware reset via `watchdog_reboot()`.

```c
case PEER_CONNECTION_FAILED:
case PEER_CONNECTION_DISCONNECTED:
    watchdog_reboot(0, 0, 0);
```

A clean cold boot is chosen over in-place teardown/reconnect because CYW43, DTLS (mbedTLS), and USRSCTP all hold deeply nested global state that cannot be safely re-initialized without a full reset. The entire startup sequence — WiFi, WebRTC, deferred USB init — replays from scratch, guaranteeing a known-good state.
