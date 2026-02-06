#ifndef _NETDB_H_STUB
#define _NETDB_H_STUB

// Stub for DNS/name resolution on RP2040 bare metal.
//
// usrsctp's sctp_pcb.c includes <netdb.h> but does not actually call
// getaddrinfo() or related functions. This header exists only for
// compilation compatibility.
//
// If DNS resolution is needed in the future, lwIP's dns.h can be used
// with dns_gethostbyname() callback API.

#include <stddef.h>
#include <sys/socket.h>

#ifndef AF_UNSPEC
#define AF_UNSPEC 0
#endif

// addrinfo flags - not used, but defined for compilation
#define AI_PASSIVE      0x01
#define AI_CANONNAME    0x02
#define AI_NUMERICHOST  0x04

#define EAI_NONAME      -2
#define EAI_FAIL        -4

struct addrinfo {
    int ai_flags;
    int ai_family;
    int ai_socktype;
    int ai_protocol;
    size_t ai_addrlen;
    struct sockaddr *ai_addr;
    char *ai_canonname;
    struct addrinfo *ai_next;
};

// DNS resolution implemented in inet_compat.c using lwIP
int getaddrinfo_impl(const char *node, const char *service,
                     const struct addrinfo *hints,
                     struct addrinfo **res);
void freeaddrinfo_impl(struct addrinfo *res);

#define getaddrinfo getaddrinfo_impl
#define freeaddrinfo freeaddrinfo_impl

#endif
