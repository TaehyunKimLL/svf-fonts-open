/* test_main_qemu_hooks.h - included first (-include) when main_qemu.c is compiled for the host test: printf and fflush
 * become recording stubs, and fflush leaves main (which never returns) through longjmp. */
#ifndef TEST_MAIN_QEMU_HOOKS_H
#define TEST_MAIN_QEMU_HOOKS_H
#include <stdio.h>
int test_printf(const char *fmt, ...);
int test_fflush(FILE *f);
#define printf test_printf
#define fflush test_fflush
#endif
