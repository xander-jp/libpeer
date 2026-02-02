#ifndef _SYS_SELECT_H_STUB
#define _SYS_SELECT_H_STUB

// Stub for select() on RP2040 bare metal.
//
// libpeermx uses select() to poll sockets for incoming data. In RP2040
// bare metal mode, lwIP callbacks directly fill receive buffers, and
// udp_socket_recvfrom() calls cyw43_arch_poll() to process events.
//
// This stub always returns 1 (pretending data is ready), which causes
// the code to attempt reads. The actual recv functions return 0 if no
// data is available.

#include <sys/time.h>

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

// select stub - always returns 1 to trigger read attempts
static inline int select(int nfds, fd_set *readfds, fd_set *writefds,
                         fd_set *exceptfds, struct timeval *timeout) {
    (void)nfds;
    (void)writefds;
    (void)exceptfds;
    (void)timeout;
    // Return 1 to indicate data might be ready
    // The actual recv will return 0 if nothing available
    return (readfds && readfds->fds_bits[0]) ? 1 : 0;
}

#endif
