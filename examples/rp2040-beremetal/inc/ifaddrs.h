#ifndef _IFADDRS_H_STUB
#define _IFADDRS_H_STUB

// Stub for network interface enumeration on RP2040 bare metal.
//
// usrsctp calls getifaddrs() in sctp_init_ifns_for_vrf() to enumerate
// network interfaces. Our stub returns -1 (failure), causing usrsctp
// to skip interface enumeration. This is acceptable because:
// - RP2040 has a single WiFi interface managed by lwIP
// - We use AF_CONN mode with UDP encapsulation, not raw sockets
// - Interface binding is not needed for our use case

#include <stddef.h>
#include <sys/socket.h>

// Interface flags - referenced by usrsctp but not actually used
// when getifaddrs() returns failure
#ifndef IFF_UP
#define IFF_UP          0x1
#endif
#ifndef IFF_RUNNING
#define IFF_RUNNING     0x40
#endif
#ifndef IFF_LOOPBACK
#define IFF_LOOPBACK    0x8
#endif

struct ifaddrs {
    struct ifaddrs *ifa_next;
    char *ifa_name;
    unsigned int ifa_flags;
    struct sockaddr *ifa_addr;
    struct sockaddr *ifa_netmask;
    struct sockaddr *ifa_broadaddr;
    void *ifa_data;
};

// getifaddrs stub - returns failure to skip interface enumeration
static inline int getifaddrs(struct ifaddrs **ifap) {
    *ifap = NULL;
    return -1;
}

static inline void freeifaddrs(struct ifaddrs *ifa) {
    (void)ifa;
}

#endif
