/* test_kernels - the exhaustive host net for the three hot kernels: svf__merge (1 and 2 bpp), the 1 bpp GRAY8 blit and
 * svf__scale_cell's area-averaged branch, each against a reference written here that never changes (the old byte
 * loops, copied verbatim). Built five ways (defaults, -DSVF_WORD_STORE=0 -DSVF__MERGE_UNALIGNED=0 (the bytes build:
 * the only host test of the strict-align path, so the define must stay), -DSVF_MERGE_WORDS=0 -DSVF_GRAY8_LUT1=0, -DSVF_SCALE_FAST=0 (the direct 2-D
 * scaler), -DSVF_SMALL) that
 * must print the same line:
 *   kernels: OK merge2=65536 runs=2000 or1=2000 max8=2000 rows=6000 put=9000 lut1=<blits compared>
 *   scale=<output pixels compared> gray=<inked cell pixels modelled in the target>
 * (the generator is seeded, so every count is a constant: gray=126179 here, and main() fails on any other, so a run in which
 * the blit drew nothing, or the sampling changed, is not a pass)
 * or "kernels: FAIL <test>: <where>" on stderr and exit 1.
 */
#include "svf_internal.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void svf_test_blit(const svf_target *t, const uint8_t *px, int32_t w, int32_t h, size_t pitch, uint8_t bpp, int32_t x,
                   int32_t y);

static uint32_t rng = 12345u;

static uint32_t rnd(void)
{
	rng ^= rng << 13;
	rng ^= rng >> 17;
	rng ^= rng << 5;
	return rng;
}

static unsigned long n_merge2, n_runs, n_or1, n_max8, n_rows, n_put, n_lut1, n_scale, n_gray;

static int fail(const char *test, const char *fmt, long a, long b, long c, long d, long e)
{
	fprintf(stderr, "kernels: FAIL %s: ", test);
	fprintf(stderr, fmt, a, b, c, d, e);
	fputc('\n', stderr);
	return 1;
}

/* ---- references ---- */

static uint8_t ref_max2(uint8_t x, uint8_t y)
{
	uint8_t v = 0;
	int sh;

	for (sh = 6; sh >= 0; sh -= 2) {
		uint8_t a = (uint8_t)((x >> sh) & 3), b = (uint8_t)((y >> sh) & 3);
		v = (uint8_t)(v | (a > b ? a : b) << sh);
	}
	return v;
}

static void ref_merge(uint8_t bpp, uint8_t *dst, const uint8_t *src, unsigned n)
{
	unsigned k;

	for (k = 0; k < n; ++k) {
		if (bpp == 1)
			dst[k] = (uint8_t)(dst[k] | src[k]);
		else if (bpp == 8)
			dst[k] = src[k] > dst[k] ? src[k] : dst[k];
		else
			dst[k] = ref_max2(dst[k], src[k]);
	}
}

/* The old 1 bpp GRAY8 bit loop over the cut [c0, c1) of one row: ink sets 255. dst is the row at the cell's x (so
 * dst[col] is cell column col; may be addressed below the row start only for col >= -x, which the cut guarantees). */
static void ref_gray8_1bpp(uint8_t *dst, const uint8_t *src, int32_t c0, int32_t c1)
{
	int32_t b, col;

	for (b = c0 >> 3; b <= (c1 - 1) >> 3; ++b) {
		uint8_t v = src[b];
		int32_t lo = b * 8 > c0 ? b * 8 : c0, hi = b * 8 + 8 < c1 ? b * 8 + 8 : c1;
		if (!v)
			continue;
		for (col = lo; col < hi; ++col)
			if (v >> (7 - (col - b * 8)) & 1)
				dst[col] = 255;
	}
}

static uint32_t ref_span_lo(uint32_t o, uint8_t num, uint8_t den)
{
	return o * den / num;
}

static void span(uint32_t o, uint8_t num, uint8_t den, uint32_t n, uint32_t *lo, uint32_t *hi)
{
	*lo = ref_span_lo(o, num, den);
	*hi = ((o + 1) * den - 1) / num + 1;
	if (*hi > n)
		*hi = n;
}

static uint32_t overlap(uint32_t s, uint32_t o, uint8_t num, uint8_t den)
{
	uint32_t a = s * num > o * den ? s * num : o * den;
	uint32_t b = (s + 1) * num < (o + 1) * den ? (s + 1) * num : (o + 1) * den;
	return b - a;
}

static uint32_t ref_dim(uint8_t v, uint8_t num, uint8_t den)
{
	return ((uint32_t)v * num + den - 1u) / den;
}

static void ref_scale_cell(const svf_face *f, const uint8_t *cell, uint8_t num, uint8_t den, uint8_t *out)
{
	uint32_t sw = ref_dim(f->cell_w, num, den), sh = ref_dim(f->cell_h, num, den);
	uint32_t den2 = (uint32_t)den * den, ox, oy;

	for (oy = 0; oy < sh; ++oy) {
		uint32_t y0, y1;
		span(oy, num, den, f->cell_h, &y0, &y1);
		for (ox = 0; ox < sw; ++ox) {
			uint32_t x0, x1, sx, sy, sum = 0;
			span(ox, num, den, f->cell_w, &x0, &x1);
			for (sy = y0; sy < y1; ++sy) {
				const uint8_t *src = cell + (size_t)sy * f->pitch;
				uint32_t row = 0;
				for (sx = x0; sx < x1; ++sx)
					row += svf__coverage(f->bpp, src, (int32_t)sx) * overlap(sx, ox, num, den);
				sum += row * overlap(sy, oy, num, den);
			}
			*out++ = (uint8_t)(((sum << 16) / den2 + 0x8000u) >> 16);
		}
	}
}

/* ---- tests ---- */

static int test_merge2_pairs(void)
{
	svf_face f;
	unsigned d, s;

	memset(&f, 0, sizeof f);
	f.bpp = 2;
	for (d = 0; d < 256; ++d)
		for (s = 0; s < 256; ++s) {
			uint8_t dst = (uint8_t)d, src = (uint8_t)s;
			svf__merge(&f, &dst, 0, &src, 0, 1, 1);
			if (dst != ref_max2((uint8_t)d, (uint8_t)s))
				return fail("merge2_pairs", "dst %02lx src %02lx got %02lx want %02lx%.0ld", (long)d, (long)s,
				            (long)dst, (long)ref_max2((uint8_t)d, (uint8_t)s), 0L);
			++n_merge2;
		}
	return 0;
}

#define GUARD 8

/* Each run merges twice: into the guarded 4-aligned buffers (guard bytes checked too) and into exact-size heap copies
 * (hs = os + n bytes, hd = od + n), so a read past the source or a read-modify-write past n is an ASan error. */
static int test_merge_runs(void)
{
	static uint32_t dbuf[(GUARD + 4 + 200 + GUARD + 3) / 4 + 1], obuf[(GUARD + 4 + 200 + GUARD + 3) / 4 + 1],
	    sbuf[(4 + 200) / 4 + 2];
	uint8_t *db = (uint8_t *)dbuf, *ob = (uint8_t *)obuf, *sb = (uint8_t *)sbuf;
	size_t total = sizeof dbuf;
	static const int bpps[] = {2, 1, 8};
	svf_face f;
	int run, bi;

	memset(&f, 0, sizeof f);
	for (bi = 0; bi < 3; ++bi) {
		int bpp = bpps[bi];
		f.bpp = (uint8_t)bpp;
		for (run = 0; run < 2000; ++run) {
			unsigned n = rnd() % 200, od = rnd() % 4, os = rnd() % 4, i;
			uint8_t *dst = db + GUARD + od, *rdst = ob + GUARD + od, *hs, *hd;
			const char *name = bpp == 2 ? "merge_runs" : bpp == 1 ? "merge_runs_or1" : "merge_runs_max8";

			for (i = 0; i < total; ++i)
				db[i] = (uint8_t)rnd();
			for (i = 0; i < sizeof sbuf; ++i)
				sb[i] = (uint8_t)rnd();
			memcpy(ob, db, total);
			hs = (uint8_t *)malloc(os + n);
			hd = (uint8_t *)malloc(od + n);
			if (!hs || !hd)
				return fail(name, "out of memory", 0L, 0L, 0L, 0L, 0L);
			memcpy(hs, sb, os + n);
			memcpy(hd + od, dst, n);
			svf__merge(&f, dst, 0, sb + os, 0, (uint16_t)n, 1);
			ref_merge((uint8_t)bpp, rdst, sb + os, n);
			if (memcmp(db, ob, total)) {
				for (i = 0; db[i] == ob[i]; ++i)
					;
				return fail(name, "n %ld od %ld os %ld byte %ld got %02lx", (long)n, (long)od, (long)os, (long)i,
				            (long)db[i]);
			}
			svf__merge(&f, hd + od, 0, hs + os, 0, (uint16_t)n, 1);
			if (memcmp(hd + od, rdst, n)) {
				for (i = 0; hd[od + i] == rdst[i]; ++i)
					;
				return fail(name, "heap copies: n %ld od %ld os %ld byte %ld got %02lx", (long)n, (long)od,
				            (long)os, (long)i, (long)hd[od + i]);
			}
			free(hs);
			free(hd);
			if (bpp == 2)
				++n_runs;
			else if (bpp == 1)
				++n_or1;
			else
				++n_max8;
		}
	}
	return 0;
}

#define TW 40
#define TH 3

static int test_gray8_lut1_cuts(void)
{
	static const int xs[] = {-8, -7, -6, -5, -3, -1, 0, 1, 2, 3, 5, 6, 7, 16};
	static const uint8_t fills[] = {0x00, 0xFF, 0x80};
	uint8_t buf[GUARD + TW * TH + GUARD], want[sizeof buf], cell[3 * TH];
	unsigned v, fi, xi;
	int lo, hi, r;
	svf_target t;

	for (fi = 0; fi < 4; ++fi)
		for (v = 0; v < 256; ++v) {
			/* three rows with distinct data (a row-addressing bug shows) */
			cell[0] = (uint8_t)v;
			cell[1] = (uint8_t)(v ^ 0xFF);
			cell[2] = (uint8_t)v;
			cell[3] = (uint8_t)(v ^ 0xFF);
			cell[4] = (uint8_t)v;
			cell[5] = (uint8_t)(v ^ 0x3C);
			cell[6] = (uint8_t)(v ^ 0xA5);
			cell[7] = (uint8_t)v;
			cell[8] = (uint8_t)(v ^ 0xFF);
			for (xi = 0; xi < sizeof xs / sizeof xs[0]; ++xi) {
				int x = xs[xi];
				for (lo = 0; lo < 24; ++lo)
					for (hi = lo + 1; hi <= 24; ++hi) {
						int32_t c0, c1, i;
						if (fi < 3)
							memset(buf, fills[fi], sizeof buf);
						else
							for (i = 0; i < (int32_t)sizeof buf; ++i)
								buf[i] = (uint8_t)rnd();
						memcpy(want, buf, sizeof want);
						if (svf_target_init(&t, SVF_T_GRAY8, buf + GUARD, TW * TH, TW, TH, TW))
							return fail("gray8_lut1_cuts", "target_init", 0L, 0L, 0L, 0L, 0L);
						t.clip_x0 = (int16_t)(x + lo);
						t.clip_x1 = (int16_t)(x + hi);
						/* the expected cut: inside [lo, hi) and inside the target */
						c0 = lo > -x ? lo : -x;
						c1 = hi < TW - x ? hi : TW - x;
						if (c0 < c1)
							for (r = 0; r < TH; ++r)
								ref_gray8_1bpp(want + GUARD + r * TW + x, cell + 3 * r, c0, c1);
						svf_test_blit(&t, cell, 24, TH, 3, 1, x, 0);
						if (memcmp(buf, want, sizeof buf)) {
							for (i = 0; buf[i] == want[i]; ++i)
								;
							return fail("gray8_lut1_cuts",
							            "fill %ld v %ld x %ld lo/hi %ld/%ld", (long)fi, (long)v, (long)x, (long)lo,
							            (long)hi) |
							       fail("gray8_lut1_cuts", "first differing byte %ld (buffer, guard %ld) got %02lx "
							            "want %02lx%.0ld", (long)i, (long)GUARD, (long)buf[i], (long)want[i], 0L);
						}
						++n_lut1;
					}
			}
		}
	return 0;
}

#define OUTMAX (384u * 384u)

static int test_scale_sweep(void)
{
	static const int cw[] = {1, 3, 8, 13, 16, 18, 24, 47, 48}, chh[] = {1, 2, 8, 11, 16, 18, 24, 47, 48};
	static uint8_t got[OUTMAX + 16], want[OUTMAX + 16];
	int num, den, ci, bpp, pass;

	for (den = 2; den <= 16; ++den)
		for (num = 1; num <= 16; ++num) {
			int a = num, b = den;
			while (b) {
				int r = a % b;
				a = b;
				b = r;
			}
			if (a != 1)
				continue;
			for (ci = 0; ci < 9; ++ci)
				for (bpp = 1; bpp <= 8; bpp = bpp == 2 ? 8 : bpp * 2)
					for (pass = 0; pass < 2; ++pass) {
						svf_face f;
						unsigned w = (unsigned)cw[ci], h = (unsigned)chh[ci], pitch = (w * (unsigned)bpp + 7) / 8, i, n;
						uint8_t *cell = (uint8_t *)malloc(pitch * h); /* exact size: a read past it is an ASan error */

						if (!cell)
							return fail("scale_sweep", "out of memory", 0L, 0L, 0L, 0L, 0L);
						memset(&f, 0, sizeof f);
						f.cell_w = (uint8_t)w;
						f.cell_h = (uint8_t)h;
						f.bpp = (uint8_t)bpp;
						f.pitch = (uint8_t)pitch;
						for (i = 0; i < pitch * h; ++i)
							cell[i] = (uint8_t)rnd();
						n = svf__scale_dim((uint8_t)w, (uint8_t)num, (uint8_t)den) *
						    svf__scale_dim((uint8_t)h, (uint8_t)num, (uint8_t)den);
						if (n > OUTMAX)
							return fail("scale_sweep", "output %ld too big (%ld/%ld)%.0ld%.0ld", (long)n, (long)num,
							            (long)den, 0L, 0L);
						memset(got, 0xA5, n + 16);
						memset(want, 0xA5, n + 16);
						svf__scale_cell(&f, cell, (uint8_t)num, (uint8_t)den, got);
						ref_scale_cell(&f, cell, (uint8_t)num, (uint8_t)den, want);
						if (memcmp(got, want, n + 16)) {
							for (i = 0; got[i] == want[i]; ++i)
								;
							return fail("scale_sweep", "ratio %ld/%ld cell %ldx%ld bpp %ld: output byte (of n+16)",
							            (long)num, (long)den, (long)w, (long)h, (long)bpp) |
							       fail("scale_sweep", "pass %ld output byte %ld of %ld got %02lx want %02lx",
							            (long)pass, (long)i, (long)n, (long)got[i], (long)want[i]);
						}
						free(cell);
						n_scale += n;
					}
		}
	return 0;
}

/* svf__merge over h rows (a record's box rows into a cell): each bpp, random widths, heights and both pitches, against
 * ref_merge row by row; the bytes between the rows (and the guards) unchanged, the source read in exact-size heap
 * memory so a read past its last row is an ASan error. */
static int test_merge_rows(void)
{
	static uint8_t db[GUARD + 40 * 32 + GUARD], ob[sizeof db];
	static const int bpps[] = {1, 2, 8};
	svf_face f;
	int run, bi;

	memset(&f, 0, sizeof f);
	for (bi = 0; bi < 3; ++bi) {
		f.bpp = (uint8_t)bpps[bi];
		for (run = 0; run < 2000; ++run) {
			unsigned n = rnd() % 9, h = 1 + rnd() % 32, dp = n + rnd() % 9, sp = n + rnd() % 9, i, r;
			size_t slen = (size_t)(h - 1) * sp + n;
			uint8_t *hs = (uint8_t *)malloc(slen ? slen : 1);

			if (!hs)
				return fail("merge_rows", "out of memory", 0L, 0L, 0L, 0L, 0L);
			for (i = 0; i < sizeof db; ++i)
				db[i] = (uint8_t)rnd();
			for (i = 0; i < slen; ++i)
				hs[i] = (uint8_t)rnd();
			memcpy(ob, db, sizeof db);
			svf__merge(&f, db + GUARD, (uint16_t)dp, hs, (uint16_t)sp, (uint16_t)n, (uint8_t)h);
			for (r = 0; r < h; ++r)
				ref_merge((uint8_t)f.bpp, ob + GUARD + (size_t)r * dp, hs + (size_t)r * sp, n);
			free(hs);
			if (memcmp(db, ob, sizeof db)) {
				for (i = 0; db[i] == ob[i]; ++i)
					;
				return fail("merge_rows", "bpp %ld n %ld h %ld dp %ld byte %ld", (long)f.bpp, (long)n, (long)h,
				            (long)dp, (long)i);
			}
			++n_rows;
		}
	}
	return 0;
}

/* svf__put_rows with merge on: bpp 1, 2 and 8; a face with f.layout REC 2 / ROW 0 and pitch p in 1..12, cell_h 1..24;
 * 3000 random records per bpp: full width (x0 0, wb p) at any y0 and h, the record bytes placed with the phase
 * 4 + ((y0 * p) & 3) in a 4-aligned heap block of exact size, and partial ones (wb < p); the cell at offset 0..3 of a
 * 4-aligned buffer with 8 guard bytes each side, prefilled from rnd(); against ref_merge row by row into a copy;
 * memcmp over the guards too. */
static int test_put_rows(void)
{
	static uint32_t dbuf[(GUARD + 3 + 12 * 24 + GUARD + 3) / 4], obuf[sizeof dbuf / 4];
	uint8_t *db = (uint8_t *)dbuf, *ob = (uint8_t *)obuf;
	static const int bpps[] = {1, 2, 8};
	svf_face f;
	int run, bi;

	memset(&f, 0, sizeof f);
	f.layout = 2; /* REC 2, ROW 0 */
	for (bi = 0; bi < 3; ++bi) {
		f.bpp = (uint8_t)bpps[bi];
		for (run = 0; run < 3000; ++run) {
			unsigned p = 1 + rnd() % 12, ch = 1 + rnd() % 24, co = rnd() % 4, full = p == 1 || rnd() % 2, i, r;
			unsigned y0 = rnd() % ch, h = 1 + rnd() % (ch - y0), wb = full ? p : 1 + rnd() % (p - 1);
			unsigned x0 = full ? 0 : rnd() % (p - wb + 1), off = 4 + ((y0 * p) & 3), len = h * wb;
			size_t total = GUARD + co + (size_t)p * ch + GUARD;
			uint8_t *blk = (uint8_t *)malloc(off + len), *cell = db + GUARD + co;
			svf__rec_t rec;

			if (!blk)
				return fail("put_rows", "out of memory", 0L, 0L, 0L, 0L, 0L);
			f.pitch = (uint8_t)p;
			f.stride = (uint16_t)(p * ch);
			f.cell_h = (uint8_t)ch;
			f.cell_w = (uint8_t)(p * 8 / f.bpp);
			for (i = 0; i < off + len; ++i)
				blk[i] = (uint8_t)rnd();
			for (i = 0; i < total; ++i)
				db[i] = (uint8_t)rnd();
			memcpy(ob, db, total);
			rec.x0 = (uint8_t)x0, rec.y0 = (uint8_t)y0, rec.wb = (uint8_t)wb, rec.h = (uint8_t)h;
			rec.p = (uint16_t)off, rec.rp = (uint16_t)wb;
			svf__put_rows(&f, cell, blk + off, &rec, 1);
			for (r = 0; r < h; ++r)
				ref_merge((uint8_t)f.bpp, ob + GUARD + co + (size_t)(y0 + r) * p + x0, blk + off + (size_t)r * wb, wb);
			free(blk);
			if (memcmp(db, ob, total)) {
				for (i = 0; db[i] == ob[i]; ++i)
					;
				fprintf(stderr, "kernels: FAIL put_rows: bpp %d p %u x0 %u wb %u y0 %u h %u cell offset %u byte %ld\n",
				        f.bpp, p, x0, wb, y0, h, co, (long)i - GUARD - (long)co);
				return 1;
			}
			++n_put;
		}
	}
	return 0;
}

/* The cmap search with 16-bit int arithmetic (every sum cut to uint16_t, as on AVR): the midpoint of the library
 * (SVF__CMAP_MID with U = uint16_t) must find every key and end for counts up to 65535; the pre-fix midpoint
 * (lo + hi) >> 1 in 16 bits must NOT (the test's own proof that it sees the overflow). Returns found index or -1;
 * -2 when the loop did not end in 40 probes. */
static long search16(unsigned count, unsigned key, int old)
{
	uint16_t lo = 0, hi = (uint16_t)count;
	int probes = 0;
	while (lo < hi) {
		uint16_t mid = old ? (uint16_t)((uint16_t)(lo + hi) >> 1) : SVF__CMAP_MID(lo, hi, uint16_t);
		if (++probes > 40)
			return -2;
		if (mid == key)
			return mid;
		if (mid < key)
			lo = (uint16_t)(mid + 1);
		else
			hi = mid;
	}
	return -1;
}

static int test_cmap_mid16(void)
{
	static const unsigned counts[] = {1, 2, 3, 100, 32767, 32768, 32769, 40000, 50000, 65534, 65535};
	unsigned c, k, old_bad = 0;
	for (c = 0; c < sizeof counts / sizeof counts[0]; ++c) {
		unsigned n = counts[c];
		for (k = 0; k < n; k += (n > 3000 && k < n - 8 ? 7 : 1)) {
			long r = search16(n, k, 0);
			if (r != (long)k)
				return fail("cmap_mid16", "count %ld key %ld found %ld", (long)n, (long)k, r, 0, 0);
			if (search16(n, k, 1) != (long)k)
				++old_bad;
		}
	}
	if (!old_bad)
		return fail("cmap_mid16", "the 16-bit pre-fix midpoint was not seen to fail%ld", 0, 0, 0, 0, 0);
	return 0;
}

#if SVF_TARGETS & SVF_TARGET_GRAY
/* SVF_T_GRAY with gray_bits 1, 2 and 4 (the packed blitter; 8 goes through blit_gray8 and is tested by the identity tests):
 * a 64 x 8 target at each bits and bit order, a cell of 1, 2 or 8 bpp with random content, padding bits inked, at a
 * random x (-9..40) and y, a random threshold and a random prefill, 16 guard bytes each side. The reference is written
 * here, per pixel: the coverage from the stored cell, the level (the ramp rule, the mono rule for one level), the
 * field's max, the field's bits only. */
static unsigned ref_gray_cov(unsigned bpp, const uint8_t *row, unsigned col)
{
	if (bpp == 1)
		return (row[col / 8] >> (7 - col % 8) & 1) ? 255u : 0u;
	if (bpp == 2)
		return (unsigned)(row[col / 4] >> (6 - 2 * (col % 4)) & 3) * 85u;
	return row[col];
}

static int test_gray_packed(void)
{
	enum { TWG = 64, THG = 8, GG = 16 };
	rng = 12345u; /* reseeded: the pinned count below must not depend on how many numbers the earlier tests drew */
	static const uint8_t bitsv[] = {1, 2, 4};
	static const int bppv[] = {1, 2, 8};
	uint8_t buf[GG + 32 * THG + GG], want[sizeof buf], cell[40 * 6];
	int run;

	for (run = 0; run < 3000; ++run) {
		unsigned bits = bitsv[rnd() % 3], bpp = (unsigned)bppv[rnd() % 3], lsb = rnd() & 1, w = 1 + rnd() % 40,
		         h = 1 + rnd() % 6, thr = rnd() % 256, pitch = (w * bpp + 7) / 8, stride = (TWG * bits + 7) / 8,
		         top = (1u << bits) - 1u, row, col, i;
		int x = (int)(rnd() % 50) - 9, y = (int)(rnd() % (THG - h + 1));
		size_t total = (size_t)GG + stride * THG + GG;
		svf_target t;

		for (i = 0; i < sizeof cell; ++i)
			cell[i] = (uint8_t)rnd(); /* padding bits inked at random */
		for (i = 0; i < total; ++i)
			buf[i] = (uint8_t)rnd();
		memcpy(want, buf, total);
		if (svf_target_init(&t, SVF_T_GRAY, buf + GG, (size_t)stride * THG, TWG, THG, (uint16_t)stride))
			return fail("gray", "target_init%.0ld%.0ld%.0ld%.0ld%.0ld", 0L, 0L, 0L, 0L, 0L);
		t.gray_bits = (uint8_t)bits;
		t.flags = lsb ? SVF_TF_GRAY_LSB_FIRST : 0;
		t.mono_threshold = (uint8_t)thr;
		for (row = 0; row < h; ++row)
			for (col = 0; col < w; ++col) {
				int px = x + (int)col;
				unsigned cov, lv, bitpos, sh, f;
				uint8_t *d;

				if (px < 0 || px >= TWG)
					continue;
				cov = ref_gray_cov(bpp, cell + row * pitch, col);
				if (top == 1)
					lv = cov >= (thr ? thr : 1u) ? 1u : 0u;
				else
					lv = (cov * top + 127u) / 255u;
				if (!lv)
					continue;
				bitpos = (unsigned)px * bits;
				sh = lsb ? bitpos % 8 : 8 - bits - bitpos % 8;
				d = want + GG + (size_t)(y + (int)row) * stride + bitpos / 8;
				f = (unsigned)(*d >> sh) & top;
				if (lv > f)
					*d = (uint8_t)((*d & ~(top << sh)) | (lv << sh));
				++n_gray;
			}
		svf_test_blit(&t, cell, (int32_t)w, (int32_t)h, pitch, (uint8_t)bpp, x, y);
		if (memcmp(buf, want, total))
			return fail("gray", "bits=%ld lsb=%ld x=%ld bpp=%ld w=%ld", (long)bits, (long)lsb, (long)x, (long)bpp,
			            (long)w);
	}
	return 0;
}
#endif

int main(void)
{
	if (test_merge2_pairs() || test_merge_runs() || test_merge_rows() || test_put_rows() || test_gray8_lut1_cuts() || test_scale_sweep() || test_cmap_mid16()
#if SVF_TARGETS & SVF_TARGET_GRAY
	    || test_gray_packed()
#endif
	)
		return 1;
#if SVF_TARGETS & SVF_TARGET_GRAY
	if (n_gray != 126179ul) {
		fprintf(stderr, "kernels: FAIL gray: %lu inked pixels modelled, want 126179\n", n_gray);
		return 1;
	}
#endif
	printf("kernels: OK merge2=%lu runs=%lu or1=%lu max8=%lu rows=%lu put=%lu lut1=%lu scale=%lu gray=%lu\n", n_merge2, n_runs,
	       n_or1, n_max8, n_rows, n_put, n_lut1, n_scale, n_gray);
	return 0;
}
