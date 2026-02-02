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