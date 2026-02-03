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

## Compatibility Layer (Stubs)

RP2040 bare-metal has no OS, so POSIX/BSD headers and functions must be stubbed or reimplemented. These files provide the minimal compatibility layer for usrsctp, mbedtls, and libpeermx.

### Source Files

| File | Description |
|------|-------------|
| `inet_compat.c` | POSIX function implementations: `inet_pton`, `inet_ntop` (IP address conversion), `gettimeofday` (Pico SDK time), `localtime_r` (stub for logging), `nanosleep` (Pico SDK sleep), `getaddrinfo`/`freeaddrinfo` (DNS via lwIP). |
| `atomic_compat.c` | Software atomic operations for Cortex-M0+ (ARMv6-M lacks LDREX/STREX). Implements `__sync_fetch_and_add_4`, `__sync_add_and_fetch_4`, `__sync_fetch_and_sub_4`, `__sync_bool_compare_and_swap_4` using interrupt masking (PRIMASK). |

### Header Stubs (`inc/`)

| File | Description |
|------|-------------|
| `arpa/inet.h` | Redirects to `sys/socket.h` for `inet_pton`/`inet_ntop` declarations and lwIP address types. |
| `net/if.h` | Defines `IFNAMSIZ`, `struct ifnet` (opaque), and `if_nametoindex()` stub (returns 0). Never called because `getifaddrs()` fails first. |
| `netinet/in.h` | Redirects to `sys/socket.h` for `sockaddr_in`, `sockaddr_in6`, `in_addr` types via lwIP. |
| `netinet/ip.h` | Defines `struct ip` (IPv4 header), `IPVERSION`, `IPTOS_*` constants. Required by `sctp_os_userspace.h`. |
| `netinet/in_systm.h` | Empty stub. Included by usrsctp but types (`n_short`, `n_long`) not actually used. |
| `sys/socket.h` | Central socket types stub. Defines `sockaddr`, `sockaddr_in`, `sockaddr_in6`, `sockaddr_storage`, `iovec`, `msghdr`, `cmsghdr`, socket constants (`AF_*`, `SOCK_*`, `MSG_*`, `SO_*`), and CMSG macros. Includes `<lwip/inet.h>`. |
| `sys/time.h` | Defines `struct timeval`, timer macros (`timercmp`, `timeradd`, `timersub`), declares `gettimeofday()`. |
| `sys/select.h` | Implements `select()` stub that polls `cyw43_arch_poll()` with timeout. Gives lwIP time to process packets. |
| `sys/ioctl.h` | Empty stub. Included by usrsctp but `ioctl()` code path never executed (no BSD sockets). |
| `sys/uio.h` | Redirects to `sys/socket.h` for `struct iovec` definition. |
| `netdb.h` | DNS resolution stub. Defines `struct addrinfo`, `EAI_*` errors, redirects `getaddrinfo`/`freeaddrinfo` to `inet_compat.c` implementations. |
| `pthread.h` | POSIX threads stub for single-threaded mode. All mutex/rwlock/condvar/thread functions are no-ops. Uses ARM toolchain's `sys/_pthreadtypes.h`. |
| `ifaddrs.h` | Network interface enumeration stub. `getifaddrs()` returns -1, causing usrsctp to skip interface enumeration. OK because we use AF_CONN mode. |

### Configuration Headers (`inc/`)

| File | Description |
|------|-------------|
| `lwipopts.h` | lwIP configuration for RP2040. `NO_SYS=1` (no OS), `LWIP_SOCKET=0` (raw API only), IPv4/IPv6, DNS, DHCP enabled. Memory tuned for Pico W. |
| `tusb_config.h` | TinyUSB configuration. Device mode, full speed, HID endpoint for USB communication. |
| `mbedtls_config.h` | mbedtls configuration for RP2040. Hardware entropy, memory optimizations (`SHA256_SMALLER`, `AES_FEWER_TABLES`), ECDHE key exchange, TLS 1.2 + DTLS 1.2, DTLS-SRTP, self-signed cert generation. |