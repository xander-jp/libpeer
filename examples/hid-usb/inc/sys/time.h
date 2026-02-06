#ifndef _SYS_TIME_H_STUB
#define _SYS_TIME_H_STUB

// Stub for sys/time.h on RP2040 bare metal.
// Provides struct timeval and timer macros for usrsctp.

#include <stdint.h>

#ifndef _TIMEVAL_DEFINED
#define _TIMEVAL_DEFINED
struct timeval {
    long tv_sec;
    long tv_usec;
};
#endif

// Timer comparison and arithmetic macros used by usrsctp
#ifndef timercmp
#define timercmp(a, b, CMP) \
    (((a)->tv_sec == (b)->tv_sec) ? \
     ((a)->tv_usec CMP (b)->tv_usec) : \
     ((a)->tv_sec CMP (b)->tv_sec))
#endif

#ifndef timerclear
#define timerclear(tvp) ((tvp)->tv_sec = (tvp)->tv_usec = 0)
#endif

#ifndef timerisset
#define timerisset(tvp) ((tvp)->tv_sec || (tvp)->tv_usec)
#endif

#ifndef timeradd
#define timeradd(a, b, result) \
    do { \
        (result)->tv_sec = (a)->tv_sec + (b)->tv_sec; \
        (result)->tv_usec = (a)->tv_usec + (b)->tv_usec; \
        if ((result)->tv_usec >= 1000000) { \
            ++(result)->tv_sec; \
            (result)->tv_usec -= 1000000; \
        } \
    } while (0)
#endif

#ifndef timersub
#define timersub(a, b, result) \
    do { \
        (result)->tv_sec = (a)->tv_sec - (b)->tv_sec; \
        (result)->tv_usec = (a)->tv_usec - (b)->tv_usec; \
        if ((result)->tv_usec < 0) { \
            --(result)->tv_sec; \
            (result)->tv_usec += 1000000; \
        } \
    } while (0)
#endif

// gettimeofday - implemented in inet_compat.c
int gettimeofday(struct timeval *tv, void *tz);

#endif
