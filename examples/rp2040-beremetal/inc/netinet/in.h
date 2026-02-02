#ifndef NETINET_INET_H
#define NETINET_INET_H

// Redirect to sys/socket.h which provides all necessary types
// (sockaddr_in, sockaddr_in6, in_addr, etc.) via lwip/inet.h.
// Required by sctp_os_userspace.h.
#include <sys/socket.h>

#endif  // NETINET_INET_H
