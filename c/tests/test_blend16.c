/* test_blend16 - the renderer's integer formulas under the arithmetic of a target whose int is 16 bits (AVR).
 *
 * No host compiler gives a 16-bit int, so every formula is written twice here: a uint32_t reference (the value
 * tools/svfline.py computes) and a model whose every intermediate is wrapped to what the target holds:
 *   - an expression the source computes in unsigned / uint32_t is modelled with each intermediate cut to uint16_t
 *     (U16), so a result that is only right with a 32-bit int differs from the reference on the host too;
 *   - an expression built from promoted uint8_t operands is an int on the target, 16 bits signed: S16 evaluates it
 *     in 32 bits, fails the test above 32767, and returns it as int16_t. (The weights times a channel, up to
 *     255 * 255, are never formed this way: they are unsigned, hence U16.)
 * The test fails on any model/reference mismatch or any S16 intermediate above 32767, and asserts the observed
 * maxima: level, 8-bit blend and palette 65152; 5/6-bit blend 16192. It links nothing of the library.
 * Prints "blend16: OK" and exits 0.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define U16(x) ((uint16_t)(x))
static long s16max; /* the largest S16 intermediate */
static int bad, quiet, flagged; /* quiet: the self-check below expects s16 to flag a value */

static int16_t s16(long v, const char *what)
{
	if (v > s16max)
		s16max = v;
	if (v > 32767 || v < -32768) {
		if (!bad && !quiet)
			fprintf(stderr, "blend16: FAIL: %s = %ld does not fit a 16-bit int\n", what, v);
		if (!quiet)
			bad = 1;
		else
			flagged = 1;
	}
	return (int16_t)v;
}
#define S16(x) s16((long)(x), #x)

static void mismatch(const char *what, unsigned long a, unsigned long b, unsigned long m, unsigned long r)
{
	if (!bad)
		fprintf(stderr, "blend16: FAIL: %s(%lu, %lu): model %lu, reference %lu\n", what, a, b, m, r);
	bad = 1;
}

static uint32_t max_level, max_blend8, max_blend6, max_blend5, max_palette;
#define OBS(m, v) do { if ((v) > (m)) (m) = (v); } while (0)

/* The ramp level (cov * n + 127) / 255, n >= 2. */
static uint32_t level_ref(unsigned c, unsigned n)
{
	uint32_t t = (uint32_t)c * n + 127u;
	OBS(max_level, t);
	return t / 255u;
}
static uint16_t level_model(unsigned c, unsigned n)
{
	return U16(U16(U16(c) * U16(n)) + 127u) / 255u;
}

/* The threshold form (n = 1): 1 when cov >= threshold, a threshold of 0 counting as 1. */
static unsigned thr_ref(unsigned c, unsigned thr)
{
	return c >= (thr > 1 ? thr : 1u) ? 1u : 0u;
}
static unsigned thr_model(uint8_t c, uint8_t thr)
{
	uint8_t t = thr ? thr : 1;
	return c >= t;
}

/* One channel of a 5/6/5 or 5/5/5 blend: (bg * (255 - cov) + fg * cov + 127) / 255. */
static uint32_t chan_ref(unsigned bg, unsigned fg, unsigned cov, int wide)
{
	uint32_t t = (uint32_t)bg * (255u - cov) + (uint32_t)fg * cov + 127u;
	if (wide)
		OBS(max_blend6, t);
	else
		OBS(max_blend5, t);
	return t / 255u;
}
static uint16_t chan_model(unsigned bg, unsigned fg, unsigned cov)
{
	return U16(U16(U16(bg) * U16(255u - cov)) + U16(U16(fg) * U16(cov)) + 127u) / 255u;
}

/* The 8-bit channel blend, in uint32_t in the source: ((uint32_t)bg * (255 - c) + (uint32_t)fg * c + 127) / 255. */
static uint32_t blend8_ref(unsigned bg, unsigned fg, unsigned c)
{
	uint32_t t = (uint32_t)bg * (255u - c) + (uint32_t)fg * c + 127u;
	OBS(max_blend8, t);
	return t / 255u;
}
static uint16_t blend8_model(uint8_t bg, uint8_t fg, uint8_t c)
{
	int16_t w = S16(255 - c); /* the promoted-uint8_t weight: small */
	return U16(U16(U16(bg) * U16(w)) + U16(U16(fg) * U16(c)) + 127u) / 255u;
}

/* The palette entry (bg * (n - k) + fg * k + n / 2) / n. */
static uint32_t pal_ref(unsigned bg, unsigned fg, unsigned n, unsigned k)
{
	uint32_t t = (uint32_t)bg * (n - k) + (uint32_t)fg * k + n / 2u;
	OBS(max_palette, t);
	return t / n;
}
static uint16_t pal_model(uint8_t bg, uint8_t fg, uint8_t n, uint8_t k)
{
	int16_t w = S16(n - k), half = S16(n / 2);
	return U16(U16(U16(bg) * U16(w)) + U16(U16(fg) * U16(k)) + U16(half)) / U16(n);
}

static unsigned rgb565_pack(unsigned r, unsigned g, unsigned b)
{
	return r << 11 | g << 5 | b;
}

int main(void)
{
	static const unsigned edge[] = {0, 1, 127, 128, 254, 255};
	unsigned c, n, k, bg, fg, thr, i, j;

	for (n = 1; n <= 255; ++n)
		for (c = 0; c <= 255; ++c) {
			if (n >= 2) {
				uint32_t r = level_ref(c, n);
				uint16_t m = level_model(c, n);
				if (r != m)
					mismatch("level", c, n, m, r);
			}
		}
	for (thr = 0; thr <= 255; ++thr)
		for (c = 0; c <= 255; ++c)
			if (thr_ref(c, thr) != thr_model((uint8_t)c, (uint8_t)thr))
				mismatch("threshold", c, thr, thr_model((uint8_t)c, (uint8_t)thr), thr_ref(c, thr));

	/* blend565 / blend555: every channel value (6-bit green: 0..63; 5-bit: 0..31) and coverage. */
	for (bg = 0; bg < 64; ++bg)
		for (fg = 0; fg < 64; ++fg)
			for (c = 0; c <= 255; ++c) {
				uint32_t r = chan_ref(bg, fg, c, 1);
				uint16_t m = chan_model(bg, fg, c);
				if (r != m)
					mismatch("channel", bg, fg, m, r);
				if (bg < 32 && fg < 32)
					(void)chan_ref(bg, fg, c, 0);
			}
	/* Whole 565 pixels from channel tuples, a sample of the colours at every coverage. */
	for (i = 0; i < 65536; i += 257)
		for (j = 0; j < 65536; j += 211)
			for (c = 0; c <= 255; c += 5) {
				unsigned r_ref = chan_ref(i >> 11, j >> 11, c, 0) << 11 | chan_ref(i >> 5 & 63, j >> 5 & 63, c, 1) << 5 |
				                 chan_ref(i & 31, j & 31, c, 0);
				unsigned r_mod = rgb565_pack(chan_model(i >> 11, j >> 11, c), chan_model(i >> 5 & 63, j >> 5 & 63, c),
				                             chan_model(i & 31, j & 31, c));
				if (r_ref != r_mod)
					mismatch("blend565", i, j, r_mod, r_ref);
			}

	/* blend888: every c_bg, c_fg and c. */
	for (bg = 0; bg < 256; ++bg)
		for (fg = 0; fg < 256; ++fg)
			for (c = 0; c < 256; ++c) {
				uint32_t r = blend8_ref(bg, fg, c);
				uint16_t m = blend8_model((uint8_t)bg, (uint8_t)fg, (uint8_t)c);
				if (r != m)
					mismatch("blend888", bg, fg, m, r);
			}

	/* The palette: for fixed n and k the entry is bilinear in (bg, fg), so its largest intermediate (and any 16-bit
	 * wrap) is at the vertices of the bg x fg square; the edge colours include both vertices 0 and 255 and the
	 * mid-range values, for every (n, k). The whole plane is then swept at n = 255, the largest weights. */
	/* The palette: every (n, k) with the edge colours, and the whole bg x fg plane at n = 255. */
	for (n = 1; n <= 255; ++n)
		for (k = 0; k <= n; ++k)
			for (i = 0; i < 6; ++i)
				for (j = 0; j < 6; ++j) {
					uint32_t r = pal_ref(edge[i], edge[j], n, k);
					uint16_t m = pal_model((uint8_t)edge[i], (uint8_t)edge[j], (uint8_t)n, (uint8_t)k);
					if (r != m)
						mismatch("palette", edge[i], edge[j], m, r);
				}
	for (k = 0; k <= 255; ++k)
		for (bg = 0; bg < 256; ++bg)
			for (fg = 0; fg < 256; ++fg) {
				uint32_t r = pal_ref(bg, fg, 255, k);
				uint16_t m = pal_model((uint8_t)bg, (uint8_t)fg, 255, (uint8_t)k);
				if (r != m)
					mismatch("palette", bg, fg, m, r);
			}

	if (max_level != 65152u || max_blend8 != 65152u || max_palette != 65152u || max_blend6 != 16192u ||
	    max_blend5 != 8032u) {
		fprintf(stderr, "blend16: FAIL: maxima level %lu blend8 %lu palette %lu blend6 %lu blend5 %lu\n",
		        (unsigned long)max_level, (unsigned long)max_blend8, (unsigned long)max_palette,
		        (unsigned long)max_blend6, (unsigned long)max_blend5);
		bad = 1;
	}
	/* The S16 check is live: 255 * 255 (two promoted uint8_t operands) must be seen as not fitting 16 bits. */
	{
		long before = s16max;
		quiet = 1;
		(void)s16((long)edge[5] * edge[5], "255 * 255");
		quiet = 0;
		s16max = before;
		if (!flagged) {
			fprintf(stderr, "blend16: FAIL: S16 does not flag 255 * 255\n");
			bad = 1;
		}
	}
	if (bad)
		return 1;
	printf("blend16: OK (level/blend8/palette max %lu, blend565 max %lu, largest int16 intermediate %lu)\n",
	       (unsigned long)max_level, (unsigned long)max_blend6, (unsigned long)s16max);
	return 0;
}
