/* test_rd8.h - a host stand-in for a separate face address space (AVR PROGMEM), for the svfdump-rd8 build:
 *
 *   -include tests/test_rd8.h '-DSVF_RD8(p)=svf_test_rd8(p)'
 *
 * Mapped face bytes are handed to the library at an alias whose own bytes are 0x5A; svf_test_rd8 translates an alias
 * address to the real byte and counts the call. A plain load of mapped face bytes therefore reads 0x5A, and an
 * svf_test_rd8 call on anything but the alias (a streamed face's RAM) stops the program (exit 3). */
#ifndef TEST_RD8_H
#define TEST_RD8_H

#include <stddef.h>
#include <stdint.h>

uint8_t svf_test_rd8(const void *p);

/* Maps [alias, alias + len) onto [real, real + len). */
void svf_test_rd8_map(const uint8_t *alias, const uint8_t *real, size_t len);

/* Offsets [lo, hi) of the mapped file that svf_test_rd8 must never be asked for (exit 3). */
void svf_test_rd8_forbid(uint32_t lo, uint32_t hi);

/* svf_test_rd8 calls so far. */
unsigned long svf_test_rd8_calls(void);

#endif
