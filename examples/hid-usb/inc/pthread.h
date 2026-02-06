#ifndef _PTHREAD_H_STUB
#define _PTHREAD_H_STUB

// Stub for POSIX threads on RP2040 bare metal (NO_SYS=1, single-threaded).
//
// usrsctp uses pthread types and functions for locking throughout its code.
// In bare metal single-threaded mode, all lock operations are no-ops since
// there's no concurrent access.
//
// The ARM toolchain provides pthread types in sys/_pthreadtypes.h.

#include <stdint.h>
#include <time.h>  // for clock_t needed by sys/_pthreadtypes.h
#include <sys/_pthreadtypes.h>

// rwlock types not provided by ARM toolchain
#ifndef _PTHREAD_RWLOCK_T_DEFINED
#define _PTHREAD_RWLOCK_T_DEFINED
typedef int pthread_rwlock_t;
typedef int pthread_rwlockattr_t;
#endif

#ifndef PTHREAD_MUTEX_INITIALIZER
#define PTHREAD_MUTEX_INITIALIZER 0
#endif
#ifndef PTHREAD_MUTEX_ERRORCHECK
#define PTHREAD_MUTEX_ERRORCHECK 0
#endif

// Mutex stubs - no-op in single-threaded mode
static inline int pthread_mutexattr_init(pthread_mutexattr_t *a) { (void)a; return 0; }
static inline int pthread_mutexattr_destroy(pthread_mutexattr_t *a) { (void)a; return 0; }
static inline int pthread_mutexattr_settype(pthread_mutexattr_t *a, int t) { (void)a; (void)t; return 0; }
static inline int pthread_mutex_init(pthread_mutex_t *m, const pthread_mutexattr_t *a) { (void)m; (void)a; return 0; }
static inline int pthread_mutex_destroy(pthread_mutex_t *m) { (void)m; return 0; }
static inline int pthread_mutex_lock(pthread_mutex_t *m) { (void)m; return 0; }
static inline int pthread_mutex_unlock(pthread_mutex_t *m) { (void)m; return 0; }
static inline int pthread_mutex_trylock(pthread_mutex_t *m) { (void)m; return 0; }

// RW lock stubs - no-op in single-threaded mode
static inline int pthread_rwlockattr_init(pthread_rwlockattr_t *a) { (void)a; return 0; }
static inline int pthread_rwlockattr_destroy(pthread_rwlockattr_t *a) { (void)a; return 0; }
static inline int pthread_rwlock_init(pthread_rwlock_t *l, const pthread_rwlockattr_t *a) { (void)l; (void)a; return 0; }
static inline int pthread_rwlock_destroy(pthread_rwlock_t *l) { (void)l; return 0; }
static inline int pthread_rwlock_rdlock(pthread_rwlock_t *l) { (void)l; return 0; }
static inline int pthread_rwlock_wrlock(pthread_rwlock_t *l) { (void)l; return 0; }
static inline int pthread_rwlock_unlock(pthread_rwlock_t *l) { (void)l; return 0; }
static inline int pthread_rwlock_tryrdlock(pthread_rwlock_t *l) { (void)l; return 0; }
static inline int pthread_rwlock_trywrlock(pthread_rwlock_t *l) { (void)l; return 0; }

// Condition variable stubs - no-op in single-threaded mode
static inline int pthread_cond_init(pthread_cond_t *c, const pthread_condattr_t *a) { (void)c; (void)a; return 0; }
static inline int pthread_cond_destroy(pthread_cond_t *c) { (void)c; return 0; }
static inline int pthread_cond_wait(pthread_cond_t *c, pthread_mutex_t *m) { (void)c; (void)m; return 0; }
static inline int pthread_cond_signal(pthread_cond_t *c) { (void)c; return 0; }
static inline int pthread_cond_broadcast(pthread_cond_t *c) { (void)c; return 0; }

// Thread stubs - no-op in single-threaded mode
static inline pthread_t pthread_self(void) { return 0; }
static inline int pthread_join(pthread_t t, void **v) { (void)t; (void)v; return 0; }
static inline int pthread_create(pthread_t *t, const pthread_attr_t *a, void *(*f)(void *), void *arg) {
    (void)t; (void)a; (void)f; (void)arg; return 0;
}

#endif
