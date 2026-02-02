#ifndef _NETINET_IP_H_STUB
#define _NETINET_IP_H_STUB

// Minimal netinet/ip.h for RP2040 bare metal.
// Required because sctp_os_userspace.h only defines struct ip
// for _WIN32 or __native_client__. For other platforms (including
// RP2040), it expects <netinet/ip.h> to provide the definition.

#include <stdint.h>
#include <sys/socket.h>  // for struct in_addr

#define IPVERSION 4

#define IPTOS_LOWDELAY     0x10
#define IPTOS_THROUGHPUT   0x08
#define IPTOS_RELIABILITY  0x04

struct ip {
    uint8_t  ip_hl:4;
    uint8_t  ip_v:4;
    uint8_t  ip_tos;
    uint16_t ip_len;
    uint16_t ip_id;
    uint16_t ip_off;
    uint8_t  ip_ttl;
    uint8_t  ip_p;
    uint16_t ip_sum;
    struct in_addr ip_src;
    struct in_addr ip_dst;
};

#define IP_MAXPACKET 65535

#endif
