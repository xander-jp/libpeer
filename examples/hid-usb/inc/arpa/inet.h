#ifndef _ARPA_INET_H_STUB
#define _ARPA_INET_H_STUB

// Redirect to sys/socket.h which provides inet_pton/inet_ntop declarations
// and includes lwip/inet.h for address types.
// Required by usrsctp and libpeermx for IP address handling.
#include <sys/socket.h>

#endif
