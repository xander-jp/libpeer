#ifndef _SYS_SOCKET_H_STUB
#define _SYS_SOCKET_H_STUB

//=============================================================================
// Minimal socket types stub for RP2040 bare metal (NO_SYS=1, LWIP_SOCKET=0)
//
// This header provides type definitions and constants required by usrsctp
// to compile. We use lwIP raw API instead of BSD sockets, so no actual
// socket functions are implemented here.
//
// usrsctp uses AF_CONN mode with UDP encapsulation - it doesn't use the
// BSD socket API internally, but its headers reference these types.
//=============================================================================

#include <stdint.h>
#include <stddef.h>

// lwIP provides in_addr, in6_addr, and related types
#include <lwip/inet.h>

//-----------------------------------------------------------------------------
// Basic socket types - used throughout usrsctp headers
//-----------------------------------------------------------------------------
#ifndef __SOCKLEN_T_DEFINED
#define __SOCKLEN_T_DEFINED
typedef uint32_t socklen_t;
#endif

#ifndef __SA_FAMILY_T_DEFINED
#define __SA_FAMILY_T_DEFINED
typedef uint8_t sa_family_t;
#endif

// ssize_t is already defined in lwip/arch.h

//-----------------------------------------------------------------------------
// Address families - used by usrsctp for socket address handling
//-----------------------------------------------------------------------------
#ifndef AF_INET
#define AF_INET 2
#endif
#ifndef AF_INET6
#define AF_INET6 10
#endif

//-----------------------------------------------------------------------------
// Socket types - SOCK_SEQPACKET is used by SCTP
//-----------------------------------------------------------------------------
#ifndef SOCK_STREAM
#define SOCK_STREAM 1
#endif
#ifndef SOCK_DGRAM
#define SOCK_DGRAM 2
#endif
#ifndef SOCK_SEQPACKET
#define SOCK_SEQPACKET 5
#endif

//-----------------------------------------------------------------------------
// Socket constants - used by usrsctp internally
//-----------------------------------------------------------------------------
#ifndef IPPORT_RESERVED
#define IPPORT_RESERVED 1024
#endif
#ifndef INET_ADDRSTRLEN
#define INET_ADDRSTRLEN 16
#endif
#ifndef INET6_ADDRSTRLEN
#define INET6_ADDRSTRLEN 46
#endif
#ifndef SOMAXCONN
#define SOMAXCONN 128
#endif

//-----------------------------------------------------------------------------
// Message flags - used by usrsctp's send/recv operations
// MSG_EOR and MSG_NOTIFICATION are especially important for SCTP
//-----------------------------------------------------------------------------
#ifndef MSG_OOB
#define MSG_OOB 0x01
#endif
#ifndef MSG_PEEK
#define MSG_PEEK 0x02
#endif
#ifndef MSG_DONTWAIT
#define MSG_DONTWAIT 0x40
#endif
#ifndef MSG_EOR
#define MSG_EOR 0x80
#endif
#ifndef MSG_TRUNC
#define MSG_TRUNC 0x20
#endif
#ifndef MSG_NOTIFICATION
#define MSG_NOTIFICATION 0x1000
#endif

//-----------------------------------------------------------------------------
// Protocol levels - referenced by usrsctp socket option handling
//-----------------------------------------------------------------------------
#ifndef IPPROTO_IP
#define IPPROTO_IP 0
#endif
#ifndef IPPROTO_TCP
#define IPPROTO_TCP 6
#endif
#ifndef IPPROTO_UDP
#define IPPROTO_UDP 17
#endif

//-----------------------------------------------------------------------------
// Socket options - used by usrsctp's setsockopt/getsockopt
//-----------------------------------------------------------------------------
#ifndef SOL_SOCKET
#define SOL_SOCKET 0xfff
#endif
#ifndef SO_LINGER
#define SO_LINGER 0x0080
#endif
#ifndef SO_REUSEADDR
#define SO_REUSEADDR 0x0004
#endif
#ifndef SO_RCVBUF
#define SO_RCVBUF 0x1002
#endif
#ifndef SO_SNDBUF
#define SO_SNDBUF 0x1001
#endif
#ifndef SO_ERROR
#define SO_ERROR 0x1007
#endif

//-----------------------------------------------------------------------------
// Shutdown flags - used by usrsctp's shutdown handling
//-----------------------------------------------------------------------------
#ifndef SHUT_RD
#define SHUT_RD 0
#endif
#ifndef SHUT_WR
#define SHUT_WR 1
#endif
#ifndef SHUT_RDWR
#define SHUT_RDWR 2
#endif

//-----------------------------------------------------------------------------
// Linger structure - used with SO_LINGER option
//-----------------------------------------------------------------------------
#ifndef __LINGER_DEFINED
#define __LINGER_DEFINED
struct linger {
    int l_onoff;
    int l_linger;
};
#endif

//-----------------------------------------------------------------------------
// Socket address structures - fundamental types used throughout usrsctp
//-----------------------------------------------------------------------------
#ifndef __SOCKADDR_DEFINED
#define __SOCKADDR_DEFINED
struct sockaddr {
    uint8_t sa_len;
    uint8_t sa_family;
    char sa_data[14];
};
#endif

#ifndef __SOCKADDR_IN_DEFINED
#define __SOCKADDR_IN_DEFINED
struct sockaddr_in {
    uint8_t sin_len;
    uint8_t sin_family;
    uint16_t sin_port;
    struct in_addr sin_addr;
    char sin_zero[8];
};
#endif

#ifndef __SOCKADDR_IN6_DEFINED
#define __SOCKADDR_IN6_DEFINED
struct sockaddr_in6 {
    uint8_t sin6_len;
    uint8_t sin6_family;
    uint16_t sin6_port;
    uint32_t sin6_flowinfo;
    struct in6_addr sin6_addr;
    uint32_t sin6_scope_id;
};
#endif

#ifndef __SOCKADDR_STORAGE_DEFINED
#define __SOCKADDR_STORAGE_DEFINED
struct sockaddr_storage {
    uint8_t ss_len;
    uint8_t ss_family;
    char __ss_padding[126];
};
#endif

//-----------------------------------------------------------------------------
// I/O vector for scatter/gather - used by usrsctp's message handling
//-----------------------------------------------------------------------------
#ifndef __IOVEC_DEFINED
#define __IOVEC_DEFINED
struct iovec {
    void *iov_base;
    size_t iov_len;
};
#endif

#ifndef UIO_MAXIOV
#define UIO_MAXIOV 1024
#endif

//-----------------------------------------------------------------------------
// Control message header and macros - used for SCTP ancillary data
// (sndrcvinfo, notifications, etc.)
//-----------------------------------------------------------------------------
#ifndef __CMSGHDR_DEFINED
#define __CMSGHDR_DEFINED
struct cmsghdr {
    socklen_t cmsg_len;
    int cmsg_level;
    int cmsg_type;
};
#endif

#ifndef CMSG_ALIGN
#define CMSG_ALIGN(len) (((len) + sizeof(long) - 1) & ~(sizeof(long) - 1))
#endif
#ifndef CMSG_SPACE
#define CMSG_SPACE(len) (CMSG_ALIGN(sizeof(struct cmsghdr)) + CMSG_ALIGN(len))
#endif
#ifndef CMSG_LEN
#define CMSG_LEN(len) (CMSG_ALIGN(sizeof(struct cmsghdr)) + (len))
#endif
#ifndef CMSG_DATA
#define CMSG_DATA(cmsg) ((unsigned char *)((struct cmsghdr *)(cmsg) + 1))
#endif
#ifndef CMSG_FIRSTHDR
#define CMSG_FIRSTHDR(mhdr) \
    ((size_t)(mhdr)->msg_controllen >= sizeof(struct cmsghdr) ? \
     (struct cmsghdr *)(mhdr)->msg_control : (struct cmsghdr *)0)
#endif
#ifndef CMSG_NXTHDR
#define CMSG_NXTHDR(mhdr, cmsg) \
    (((char *)(cmsg) + CMSG_ALIGN((cmsg)->cmsg_len) + sizeof(struct cmsghdr) > \
      (char *)(mhdr)->msg_control + (mhdr)->msg_controllen) ? \
     (struct cmsghdr *)0 : \
     (struct cmsghdr *)((char *)(cmsg) + CMSG_ALIGN((cmsg)->cmsg_len)))
#endif

//-----------------------------------------------------------------------------
// Message header structure - used by usrsctp's recvmsg/sendmsg
//-----------------------------------------------------------------------------
#ifndef __MSGHDR_DEFINED
#define __MSGHDR_DEFINED
struct msghdr {
    void *msg_name;
    socklen_t msg_namelen;
    struct iovec *msg_iov;
    int msg_iovlen;
    void *msg_control;
    socklen_t msg_controllen;
    int msg_flags;
};
#endif

//-----------------------------------------------------------------------------
// IP address conversion functions - implemented in lwIP or our stubs
//-----------------------------------------------------------------------------
int inet_pton(int af, const char *src, void *dst);
const char *inet_ntop(int af, const void *src, char *dst, uint32_t size);

#endif  // _SYS_SOCKET_H_STUB
