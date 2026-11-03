/* test_rd8.c - see test_rd8.h. */
#include "test_rd8.h"

#include <stdio.h>
#include <stdlib.h>

static uintptr_t alias_at;
static const uint8_t *real_at;
static size_t map_len;
static uint32_t forbid_lo, forbid_hi;
static unsigned long calls;

void svf_test_rd8_map(const uint8_t *alias, const uint8_t *real, size_t len)
{
	alias_at = (uintptr_t)alias;
	real_at = real;
	map_len = len;
}

void svf_test_rd8_forbid(uint32_t lo, uint32_t hi)
{
	forbid_lo = lo;
	forbid_hi = hi;
}

unsigned long svf_test_rd8_calls(void)
{
	return calls;
}

uint8_t svf_test_rd8(const void *p)
{
	uintptr_t a = (uintptr_t)p;
	size_t off;

	if (a < alias_at || a - alias_at >= map_len) {
		fprintf(stderr, "svf_test_rd8: not mapped face memory: %p\n", p);
		exit(3);
	}
	off = (size_t)(a - alias_at);
	if (off >= forbid_lo && off < forbid_hi) {
		fprintf(stderr, "svf_test_rd8: forbidden read at %lu\n", (unsigned long)off);
		exit(3);
	}
	++calls;
	return real_at[off];
}
