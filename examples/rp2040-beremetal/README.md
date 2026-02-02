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

| Patch | Description |
|-------|-------------|
| libsrtp.patch | Fix `srtp_remove_stream` argument type for RP2040 |
| mbedtls.patch | Enable `MBEDTLS_SSL_DTLS_SRTP` |
| usrsctp.patch | Add RP2040 hardware RNG support and lwIP headers |