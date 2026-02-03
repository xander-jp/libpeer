# libpeer + RP2040 Baremetal Example

## Overview

| Item | Description |
|------|-------------|
| OS | None |
| RTOS | None |
| pico-sdk | Yes (used as HAL) |

### WebRTC Stack

- ICE
- DTLS
- SCTP
- DataChannel

DataChannel ping-pong works on real hardware.

## Install
```
brew install cmake openocd libraspberrypi-dev
brew tap ArmMbed/homebrew-formulae
brew install arm-none-eabi-gcc arm-none-eabi-gdb
```

## Build

```
mkdir -p ./_build
cd ./_build
cmake ..
make
openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg -c "program rp2040bm.elf verify reset exit"
```

## Patches

Patches for third-party libraries are automatically applied during the first `cmake` run.

If you need to apply them manually:

```
cd ../../third_party/libsrtp && patch -p1 < ../../examples/rp2040-beremetal/libsrtp.patch
cd ../../third_party/mbedtls && patch -p1 < ../../examples/rp2040-beremetal/mbedtls.patch
cd ../../third_party/usrsctp && patch -p1 < ../../examples/rp2040-beremetal/usrsctp.patch
```

### libsrtp.patch

| Item | Detail |
|------|--------|
| File | `include/srtp.h` |
| Change | `srtp_remove_stream(srtp_t session, unsigned int ssrc)` → `uint32_t ssrc` |
| Reason | Fix type mismatch on 32-bit ARM (RP2040). `unsigned int` size varies by platform, while `uint32_t` guarantees 32-bit width for SSRC values. |

### mbedtls.patch

| Item | Detail |
|------|--------|
| File | `include/mbedtls/mbedtls_config.h` |
| Change | Uncomment `#define MBEDTLS_SSL_DTLS_SRTP` |
| Reason | Enable DTLS-SRTP extension required for WebRTC key exchange. This feature is disabled by default in mbedtls. |

### usrsctp.patch

This is the largest patch with multiple modifications for RP2040 bare-metal support.

| File | Change | Reason |
|------|--------|--------|
| `usrsctplib/usrsctp.h` | Add lwIP header includes when `CONFIG_USE_LWIP` is defined | RP2040 uses lwIP instead of BSD sockets. Include `<lwip/sockets.h>` and `<lwip/inet.h>` for socket types. |
| `usrsctplib/usrsctp.h` | Add `__RP2040_BM__` to BSD-style `sockaddr_conn` layout | Fix `sockaddr_conn` struct alignment. RP2040 lwIP uses BSD-style layout with `sconn_len` + `sconn_family` (1 byte each) instead of Linux-style `sconn_family` (2 bytes). |
| `usrsctplib/user_environment.c` | Add RP2040 hardware RNG implementation | Use Pico SDK `pico/rand.h` and `get_rand_32()` for cryptographic random number generation. Essential for SCTP security. |
| `usrsctplib/user_socket.c` | Add debugging logs to `getsockaddr()` and `usrsctp_bind()` | Debug output for troubleshooting SCTP bind issues on RP2040. Shows byte-level sockaddr data and family values. |