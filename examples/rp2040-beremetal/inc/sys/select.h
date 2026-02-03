#ifndef _SYS_SELECT_H_STUB
#define _SYS_SELECT_H_STUB

// Stub for select() on RP2040 bare metal.
//
// libpeermx uses select() to poll sockets for incoming data. In RP2040
// bare metal mode, lwIP callbacks directly fill receive buffers.
//
// This stub polls cyw43_arch_poll() repeatedly during the timeout period,
// giving lwIP time to process incoming packets and fire callbacks.

#include <sys/time.h>
#include <pico/cyw43_arch.h>
#include <pico/time.h>

// fd_set for select() - only define if not already defined
#ifndef FD_SETSIZE
#define FD_SETSIZE 16
#endif

#ifndef _FD_SET_DEFINED
#define _FD_SET_DEFINED
typedef struct {
    unsigned long fds_bits[1];
} fd_set;
#endif

#ifndef FD_ZERO
#define FD_ZERO(set)      ((set)->fds_bits[0] = 0)
#endif
#ifndef FD_SET
#define FD_SET(fd, set)   ((set)->fds_bits[0] |= (1UL << (fd)))
#endif
#ifndef FD_CLR
#define FD_CLR(fd, set)   ((set)->fds_bits[0] &= ~(1UL << (fd)))
#endif
#ifndef FD_ISSET
#define FD_ISSET(fd, set) ((set)->fds_bits[0] & (1UL << (fd)))
#endif

// select stub - poll with timeout
static inline int select(int nfds, fd_set *readfds, fd_set *writefds,
                         fd_set *exceptfds, struct timeval *timeout) {
    (void)nfds;
    (void)writefds;
    (void)exceptfds;

    if (!readfds || !readfds->fds_bits[0]) {
        return 0;
    }

    // Calculate timeout in microseconds
    uint64_t timeout_us = 0;
    if (timeout) {
        timeout_us = (uint64_t)timeout->tv_sec * 1000000 + timeout->tv_usec;
    }

    // Poll with timeout - give lwIP time to process incoming packets
    uint64_t start = time_us_64();
    do {
        cyw43_arch_poll();
        if (timeout_us > 0) {
            uint64_t elapsed = time_us_64() - start;
            if (elapsed >= timeout_us) {
                break;
            }
            // Small sleep to avoid busy loop
            sleep_us(100);
        }
    } while (timeout_us > 0 && (time_us_64() - start) < timeout_us);

    // Return 1 to indicate caller should try recv
    return 1;
}

#endif
