// POSIX compatibility functions for RP2040 bare metal.
//
// Provides inet_pton, inet_ntop, gettimeofday, localtime_r, getaddrinfo for:
// - libpeermx/src/address.c (IP address parsing/formatting)
// - libpeermx/src/ports.c (DNS resolution)
// - usrsctp internal address and time handling

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include "pico/time.h"
#include "pico/cyw43_arch.h"
#include "lwip/dns.h"
#include "lwip/ip_addr.h"
#include "sys/socket.h"
#include "sys/time.h"
#include "netdb.h"

//=============================================================================
// inet_pton / inet_ntop - IP address conversion
// lwIP only provides these when LWIP_SOCKET=1
//=============================================================================

int inet_pton(int af, const char *src, void *dst) {
    if (af == AF_INET) {
        struct in_addr *addr = (struct in_addr *)dst;
        unsigned int a, b, c, d;
        if (sscanf(src, "%u.%u.%u.%u", &a, &b, &c, &d) == 4) {
            if (a <= 255 && b <= 255 && c <= 255 && d <= 255) {
                addr->s_addr = ((uint32_t)a) | ((uint32_t)b << 8) |
                               ((uint32_t)c << 16) | ((uint32_t)d << 24);
                return 1;
            }
        }
        return 0;
    } else if (af == AF_INET6) {
        // Simplified IPv6 parsing - only full form supported
        struct in6_addr *addr = (struct in6_addr *)dst;
        unsigned int parts[8];
        if (sscanf(src, "%x:%x:%x:%x:%x:%x:%x:%x",
                   &parts[0], &parts[1], &parts[2], &parts[3],
                   &parts[4], &parts[5], &parts[6], &parts[7]) == 8) {
            for (int i = 0; i < 8; i++) {
                addr->s6_addr[i*2] = (parts[i] >> 8) & 0xff;
                addr->s6_addr[i*2+1] = parts[i] & 0xff;
            }
            return 1;
        }
        return 0;
    }
    return -1;
}

const char *inet_ntop(int af, const void *src, char *dst, uint32_t size) {
    if (af == AF_INET) {
        const struct in_addr *addr = (const struct in_addr *)src;
        uint32_t ip = addr->s_addr;
        int len = snprintf(dst, size, "%u.%u.%u.%u",
                          ip & 0xff, (ip >> 8) & 0xff,
                          (ip >> 16) & 0xff, (ip >> 24) & 0xff);
        if (len < 0 || (uint32_t)len >= size) return NULL;
        return dst;
    } else if (af == AF_INET6) {
        const struct in6_addr *addr = (const struct in6_addr *)src;
        int len = snprintf(dst, size, "%02x%02x:%02x%02x:%02x%02x:%02x%02x:"
                          "%02x%02x:%02x%02x:%02x%02x:%02x%02x",
                          addr->s6_addr[0], addr->s6_addr[1],
                          addr->s6_addr[2], addr->s6_addr[3],
                          addr->s6_addr[4], addr->s6_addr[5],
                          addr->s6_addr[6], addr->s6_addr[7],
                          addr->s6_addr[8], addr->s6_addr[9],
                          addr->s6_addr[10], addr->s6_addr[11],
                          addr->s6_addr[12], addr->s6_addr[13],
                          addr->s6_addr[14], addr->s6_addr[15]);
        if (len < 0 || (uint32_t)len >= size) return NULL;
        return dst;
    }
    return NULL;
}

//=============================================================================
// gettimeofday - using Pico SDK time functions
//=============================================================================

int gettimeofday(struct timeval *tv, void *tz) {
    (void)tz;
    if (tv) {
        uint64_t us = to_us_since_boot(get_absolute_time());
        tv->tv_sec = us / 1000000;
        tv->tv_usec = us % 1000000;
    }
    return 0;
}

//=============================================================================
// localtime_r - stub for usrsctp_dumppacket logging
// Returns a zeroed struct tm (not accurate, but sufficient for logging)
//=============================================================================

struct tm *localtime_r(const time_t *timep, struct tm *result) {
    (void)timep;
    if (result) {
        memset(result, 0, sizeof(struct tm));
        result->tm_mday = 1;
        result->tm_year = 70;  // 1970
    }
    return result;
}

//=============================================================================
// nanosleep - for usrsctp timer
//=============================================================================

int nanosleep(const struct timespec *req, struct timespec *rem) {
    (void)rem;
    if (req) {
        uint64_t us = (uint64_t)req->tv_sec * 1000000 + req->tv_nsec / 1000;
        sleep_us(us);
    }
    return 0;
}

//=============================================================================
// getaddrinfo / freeaddrinfo - DNS resolution using lwIP
//=============================================================================

// DNS callback state
static volatile int dns_done = 0;
static ip_addr_t dns_result;

static void dns_callback(const char *name, const ip_addr_t *ipaddr, void *arg) {
    (void)name;
    (void)arg;
    if (ipaddr) {
        dns_result = *ipaddr;
    } else {
        ip_addr_set_zero(&dns_result);
    }
    dns_done = 1;
}

int getaddrinfo_impl(const char *node, const char *service,
                     const struct addrinfo *hints,
                     struct addrinfo **res) {
    (void)service;
    (void)hints;

    if (!node || !res) {
        return EAI_FAIL;
    }

    // Try to parse as IP address first
    ip_addr_t addr;
    if (ipaddr_aton(node, &addr)) {
        // It's already an IP address
        struct addrinfo *ai = (struct addrinfo *)calloc(1, sizeof(struct addrinfo) + sizeof(struct sockaddr_in));
        if (!ai) return EAI_FAIL;

        struct sockaddr_in *sa = (struct sockaddr_in *)(ai + 1);
        sa->sin_family = AF_INET;
        sa->sin_addr.s_addr = ip_addr_get_ip4_u32(&addr);

        ai->ai_family = AF_INET;
        ai->ai_socktype = SOCK_STREAM;
        ai->ai_addrlen = sizeof(struct sockaddr_in);
        ai->ai_addr = (struct sockaddr *)sa;
        ai->ai_next = NULL;

        *res = ai;
        return 0;
    }

    // DNS lookup
    dns_done = 0;
    ip_addr_set_zero(&dns_result);

    err_t err = dns_gethostbyname(node, &dns_result, dns_callback, NULL);

    if (err == ERR_OK) {
        // Result was cached
        dns_done = 1;
    } else if (err == ERR_INPROGRESS) {
        // Wait for DNS callback with timeout
        uint32_t start = to_ms_since_boot(get_absolute_time());
        while (!dns_done) {
            cyw43_arch_poll();
            sleep_ms(10);
            if (to_ms_since_boot(get_absolute_time()) - start > 5000) {
                // 5 second timeout
                return EAI_FAIL;
            }
        }
    } else {
        return EAI_FAIL;
    }

    if (ip_addr_isany(&dns_result)) {
        return EAI_NONAME;
    }

    // Allocate result
    struct addrinfo *ai = (struct addrinfo *)calloc(1, sizeof(struct addrinfo) + sizeof(struct sockaddr_in));
    if (!ai) return EAI_FAIL;

    struct sockaddr_in *sa = (struct sockaddr_in *)(ai + 1);
    sa->sin_family = AF_INET;
    sa->sin_addr.s_addr = ip_addr_get_ip4_u32(&dns_result);

    ai->ai_family = AF_INET;
    ai->ai_socktype = SOCK_STREAM;
    ai->ai_addrlen = sizeof(struct sockaddr_in);
    ai->ai_addr = (struct sockaddr *)sa;
    ai->ai_next = NULL;

    *res = ai;
    return 0;
}

void freeaddrinfo_impl(struct addrinfo *res) {
    free(res);
}
