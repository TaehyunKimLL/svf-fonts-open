/* test_pad - the blitters on cells whose padding bits are inked (the normal path never sees such a cell: svf_glyph
 * clears the padding), INDEXED8, RGB565/RGB555 and GRAY (gray_bits 1, 2, 4, both bit orders; a 13 pixel wide target, so the last byte of a row holds padding bits) at 1 and 2 bpp, through svf_test_blit (SVF_TEST_HOOKS).
 *
 * A 13 x 3 cell (1 bpp: pitch 2, 3 padding bits; 2 bpp: pitch 4, 3 padding pixels) with every padding bit set, drawn
 * at every x in -4..30, target buffer at every misalignment 0..3, with the clip right edge at the cell's width, with
 * a clip cutting the left of the cell, and unclipped. The whole buffer is compared with a per-pixel model written
 * here (guard bytes, padding bytes of rows and the columns right of the cell included), so a blit that lets a word
 * or a pair consume padding, or touches a byte outside the cut, fails. Build once with -DSVF_WORD_STORE=0 and once
 * with 1: both print the same checksum (the byte loops and the word stores agree). Prints "pad: OK <checksum>".
 */
#include "svf.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void svf_test_blit(const svf_target *t, const uint8_t *px, int32_t w, int32_t h, size_t pitch, uint8_t bpp, int32_t x,
                   int32_t y);

#define CW 13
#define CH 3
#define TW 48
#define TH 5
#define FILL 0x5A

static uint32_t sum = 2166136261u;
static long runs;

static uint16_t blend(unsigned fg, unsigned bg, unsigned cov, int bits555)
{
	unsigned sh[3], mk[3], c, v = 0;

	sh[0] = bits555 ? 10 : 11;
	sh[1] = 5;
	sh[2] = 0;
	mk[0] = 31;
	mk[1] = bits555 ? 31 : 63;
	mk[2] = 31;
	for (c = 0; c < 3; ++c)
		v |= ((((bg >> sh[c]) & mk[c]) * (255 - cov) + ((fg >> sh[c]) & mk[c]) * cov + 127) / 255) << sh[c];
	return (uint16_t)v;
}

/* The cell: pixel (col, row) level; 1 bpp 0/1, 2 bpp 0..3, varied; padding pixels all ink. */
static unsigned level_of(int bpp, int col, int row)
{
	if (col >= CW)
		return bpp == 1 ? 1 : 3;
	if (bpp == 1)
		return (col + row) % 3 != 0 || col < 4 ? 1 : 0; /* solid runs and gaps: whole nibbles and pairs exist */
	return (unsigned)((col / 2 + row) % 4) == 0 ? 3 : (unsigned)(col * 7 + row * 3) % 4;
}

int main(void)
{
	static uint8_t cell[CH * 4];
	static uint8_t buf[4 + TH * (TW * 2 + 3) + 16], want[sizeof buf];
	int bpp, kind, ramp, mis, x, mode;

#if !(SVF_TARGETS & SVF_TARGET_GRAY)
	fprintf(stderr, "pad: kind 3 (GRAY) skipped: SVF_TARGET_GRAY is not in SVF_TARGETS\n");
#define PAD_KINDS 3
#else
#define PAD_KINDS 4
#endif
	for (kind = 0; kind < PAD_KINDS; ++kind)
		for (ramp = 0; ramp < (kind == 0 ? 3 : kind == 3 ? 6 : 1); ++ramp)
			for (bpp = 1; bpp <= 2; ++bpp)
				for (mis = 0; mis < 4; ++mis)
					for (mode = 0; mode < 3; ++mode)
						for (x = -4; x <= 30; ++x) {
							int bx = kind == 0 ? 1 : 2, row, col, tw = TW;
							unsigned gbits = 1u << (ramp >> 1), stride, base = 0, n = 255, fill = FILL;
							size_t pitch = bpp == 1 ? 2 : 4;
							svf_target t;
							int c0, c1;
							svf_target_kind kd = kind == 0 ? SVF_T_INDEXED8 : kind == 1 ? SVF_T_RGB565 : kind == 2 ? SVF_T_RGB555 : SVF_T_GRAY;

							if (kind == 3)
								tw = CW; /* 13 pixels: 2, 4 and 7 bytes, with 3, 6 and 4 padding bits in the last */
							stride = kind == 3 ? (unsigned)(tw * (int)gbits + 7) / 8 + 3 : (unsigned)(TW * bx + 3);
							c1 = tw;
							c0 = 0;

							if (kind == 0 && ramp == 1) {
								base = 16;
								n = 3;
								fill = 20; /* above the ramp top 19: a lost max shows */
							} else if (kind == 0 && ramp == 2) {
								base = 16;
								n = 3;
								fill = 17;
							}
							memset(cell, 0, sizeof cell);
							for (row = 0; row < CH; ++row)
								for (col = 0; col < (int)pitch * 8 / bpp; ++col)
									cell[row * pitch + (size_t)(col * bpp) / 8] |= (uint8_t)(
									    level_of(bpp, col, row) << (8 - bpp - (col * bpp) % 8));
							memset(buf, 0xA5, sizeof buf);
							memset(buf + 4 + mis, (int)fill, TH * stride);
							if (svf_target_init(&t, kd, buf + 4 + mis, TH * stride, (uint16_t)tw, TH, (uint16_t)stride))
								return 2;
							if (kind == 0) {
								t.index_base = (uint8_t)base;
								t.index_levels = (uint8_t)n;
							} else if (kind == 3) {
								t.gray_bits = (uint8_t)gbits;
								t.flags = (ramp & 1) ? SVF_TF_GRAY_LSB_FIRST : 0;
								t.mono_threshold = 100; /* a 2 bpp level 1 (coverage 85) is below it at gray_bits 1 */
							} else {
								t.fg565 = kind == 2 ? 0xFC1Fu : 0xF81Fu;
								t.bg565 = 0x0421u;
							}
							if (mode == 0)
								c1 = x + CW; /* the clip ends at the cell's width: padding is outside */
							else if (mode == 1)
								c0 = x + 5;  /* cuts the cell's left */
							if (c1 > tw)
								c1 = tw;
							if (c0 < 0)
								c0 = 0;
							t.clip_x0 = (int16_t)c0;
							t.clip_x1 = (int16_t)(c1 < c0 ? c0 : c1);
							memcpy(want, buf, sizeof want);
							/* the model: only columns of the cell (0..CW-1) inside the clip are drawn */
							for (row = 0; row < CH; ++row)
								for (col = 0; col < CW; ++col) {
									int px = x + col;
									unsigned lv = level_of(bpp, col, row), cov;
									uint8_t *d;
									if (!lv || px < t.clip_x0 || px >= t.clip_x1 || px < 0 || px >= tw)
										continue;
									d = want + 4 + mis + (size_t)(row + 1) * stride;
									cov = bpp == 1 ? 255u : lv * 85u;
									if (kind == 3) {
										unsigned top = (1u << gbits) - 1u, bp = (unsigned)px * gbits,
										         sh = (ramp & 1) ? bp % 8 : 8 - gbits - bp % 8, l, fld;
										uint8_t *g = d + bp / 8;
										l = top == 1 ? (cov >= t.mono_threshold ? 1u : 0u) : (cov * top + 127u) / 255u;
										fld = (unsigned)(*g >> sh) & top;
										if (l > fld)
											*g = (uint8_t)((*g & ~(top << sh)) | (l << sh));
									} else if (kind == 0) {
										unsigned l = n == 1 ? 1u : (cov * n + 127u) / 255u, g = base + l;
										if (l && g > d[px])
											d[px] = (uint8_t)g;
									} else {
										unsigned v = blend(t.fg565, t.bg565, cov, kind == 2);
										if (kind == 2)
											v |= t.fg565 & 0x8000u;
										d[2 * px] = (uint8_t)v;
										d[2 * px + 1] = (uint8_t)(v >> 8);
									}
								}
							svf_test_blit(&t, cell, CW, CH, pitch, (uint8_t)bpp, x, 1);
							if (memcmp(buf, want, sizeof buf)) {
								size_t i;
								for (i = 0; i < sizeof buf && buf[i] == want[i]; ++i)
									;
								fprintf(stderr, "pad: FAIL kind %d ramp %d bpp %d mis %d mode %d x %d: byte %zu is %02x, "
								        "want %02x\n", kind, ramp, bpp, mis, mode, x, i, buf[i], want[i]);
								return 1;
							}
							for (row = 0; row < (int)sizeof buf; ++row)
								sum = (sum ^ buf[row]) * 16777619u;
							++runs;
						}
	printf("pad: OK %ld runs %08x\n", runs, (unsigned)sum);
	return 0;
}
