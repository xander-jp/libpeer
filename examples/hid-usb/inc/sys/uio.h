#ifndef _SYS_UIO_H_STUB
#define _SYS_UIO_H_STUB

// Redirect to our sys/socket.h stub which defines struct iovec.
// UIO_MAXIOV is also defined in usrsctp's user_socketvar.h.
// Required by sctp_os_userspace.h.
#include <sys/socket.h>

#endif
