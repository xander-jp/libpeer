/**
 * atomic_compat.c - Software atomic operations for Cortex-M0/M0+ (ARMv6-M)
 *
 * ARMv6-M lacks hardware atomic instructions (LDREX/STREX), so we implement
 * these using interrupt disabling (PRIMASK).
 */

#include <stdint.h>
#include <stdbool.h>

// __sync_fetch_and_add_4
uint32_t __sync_fetch_and_add_4(volatile uint32_t *ptr, uint32_t val) {
    uint32_t primask;
    __asm__ volatile ("mrs %0, primask" : "=r" (primask));
    __asm__ volatile ("cpsid i");

    uint32_t old = *ptr;
    *ptr = old + val;

    __asm__ volatile ("msr primask, %0" : : "r" (primask));
    return old;
}

// __sync_add_and_fetch_4 (returns NEW value)
uint32_t __sync_add_and_fetch_4(volatile uint32_t *ptr, uint32_t val) {
    uint32_t primask;
    __asm__ volatile ("mrs %0, primask" : "=r" (primask));
    __asm__ volatile ("cpsid i");

    uint32_t newval = *ptr + val;
    *ptr = newval;

    __asm__ volatile ("msr primask, %0" : : "r" (primask));
    return newval;
}

// __sync_fetch_and_sub_4
uint32_t __sync_fetch_and_sub_4(volatile uint32_t *ptr, uint32_t val) {
    uint32_t primask;
    __asm__ volatile ("mrs %0, primask" : "=r" (primask));
    __asm__ volatile ("cpsid i");

    uint32_t old = *ptr;
    *ptr = old - val;

    __asm__ volatile ("msr primask, %0" : : "r" (primask));
    return old;
}

// __sync_bool_compare_and_swap_4
bool __sync_bool_compare_and_swap_4(volatile uint32_t *ptr, uint32_t oldval, uint32_t newval) {
    uint32_t primask;
    __asm__ volatile ("mrs %0, primask" : "=r" (primask));
    __asm__ volatile ("cpsid i");

    bool success = false;
    if (*ptr == oldval) {
        *ptr = newval;
        success = true;
    }

    __asm__ volatile ("msr primask, %0" : : "r" (primask));
    return success;
}
