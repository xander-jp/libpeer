# LibPeer Unity Sample (macOS)

DataChannel sample - Unity implementation equivalent to `examples/generic/main.c`

## Setup

### 1. Open the project in Unity

```bash
# Open from Unity Hub or directly with Unity Editor
open -a Unity LibPeerSample
```

**Note**: Unity will initialize the project on first launch.

### 2. Create a scene

1. Create a new scene with `File > New Scene`
2. Save as `Assets/Scenes/SampleScene.unity`
3. Create an empty GameObject (`Create Empty`)
4. Attach the `LibPeerSample` script

### 3. Create UI (Optional)

1. Create `GameObject > UI > Canvas`
2. Add the following UI elements:
   - `InputField` (for URL input)
   - `Button` x2 (Connect / Disconnect)
   - `Text` x2 (Status / Log)
3. Drag & drop to `LibPeerSample` component

## Usage

### Start the SFU server

```bash
# Start SFU locally (port 8888)
cd /path/to/sfu
./sfu

# In another terminal, start cloudflared tunnel
cloudflared tunnel --url http://127.0.0.1:8888
# => A URL like https://xxx-xxx-xxx.trycloudflare.com will be displayed
```

### Connect from Unity

1. Start Play mode in Unity Editor
2. Set the cloudflared URL in Inspector's `Signaling Url` field
   - Example: `https://neo-pin-dat-revised.trycloudflare.com`
3. Right-click `LibPeerSample` component and select `Connect`
4. Once connected, messages are sent automatically every second

## Verification

Log output on successful connection:
```
[12:34:56] Connecting to: https://xxx.trycloudflare.com/whip/00/00/00
[12:34:56] Signaling connected
[12:34:57] State: checking
[12:34:57] State: connected
[12:34:57] State: completed
[12:34:57] DataChannel opened
[12:34:58] Sent: datachannel message : 00000
[12:34:59] Sent: datachannel message : 00001
```

When receiving `ping`, it automatically replies with `pong`.

## Build

```bash
# macOS standalone build
# Unity Editor: File > Build Settings > macOS > Build
```

## Troubleshooting

### libpeer.bundle not found

```
DllNotFoundException: peer
```

Check if the UPM package is correctly imported:
- `Packages/manifest.json` contains `jp.co.mixi.libpeer`
- `Packages/jp.co.mixi.libpeer/Plugins/macOS/libpeer.bundle` exists

### Cannot connect

- Verify cloudflared tunnel is running
- Verify SFU server is running on port 8888
- Verify HTTPS URL is correct
