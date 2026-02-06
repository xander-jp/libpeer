#ifndef _SYS_IOCTL_H_STUB
#define _SYS_IOCTL_H_STUB

// Empty stub - only needed for compilation.
// sctp_os_userspace.h includes <sys/ioctl.h>, but ioctl() is only
// called after socket() succeeds in sctp_userspace.c. Since we use
// lwIP raw API (not BSD sockets), socket() is not available and
// the ioctl code path is never executed.

#endif
