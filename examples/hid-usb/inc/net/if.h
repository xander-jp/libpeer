#ifndef _NET_IF_H_STUB
#define _NET_IF_H_STUB

// Minimal net/if.h stub for RP2040 bare metal

#ifndef IFNAMSIZ
#define IFNAMSIZ 16
#endif

// Forward declaration - used as opaque pointer in usrsctp
struct ifnet;

// Stub for if_nametoindex - only needed for linking.
// Never actually called because getifaddrs() returns -1,
// causing sctp_init_ifns_for_vrf() to early-return before
// reaching if_nametoindex(). usrsctp uses AF_CONN sockets
// with UDP encapsulation, so interface info is not required.
static inline unsigned int if_nametoindex(const char *ifname) {
    (void)ifname;
    return 0;
}

#endif
