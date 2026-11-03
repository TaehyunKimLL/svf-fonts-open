/* probe.c - a build probe for c/cross/build-all.sh: the smallest program that uses one build profile of the library,
 * so a link with --gc-sections keeps exactly the code that profile needs. Not an example (c/ports/ has those).
 *
 *   -DPROFILE=0  empty: main only (the baseline: startup code and main, subtracted from the others)
 *   -DPROFILE=1  P1 Uno: mapped face, 1 bpp, jamo, SVF_T_MONO_PAGE; built with -DSVF_NO_SCALE, no stream, no cache
 *   -DPROFILE=2  P2 M0+ OLED: P1 plus 2 bpp (bpp is a property of the face, read at run time: the same calls as P1)
 *   -DPROFILE=3  P3 TFT: mapped, 2 bpp, jamo, SVF_T_RGB565, composed-syllable cache; -DSVF_NO_SCALE
 *               (-DPROBE_KIND=SVF_T_GRAY8 makes it P3g, grey OLED: the same with SVF_T_GRAY8, built with -DSVF_TARGETS=0x01)
 *   -DPROFILE=4  P4 full (DOS, WASM): every public function, every target kind, streamed faces, scaling. On AVR build-all.sh
 *               pins -DSVF_TARGETS=0x1FF (every kind that existed before SVF_T_GRAY: a build that does not draw GRAY lowers SVF_TARGETS (the
 *               default mask 0x3FF includes GRAY on AVR too); its P4+GRAY row, the default mask, is informational and may overflow
 *               the 32 KB); this file draws GRAY when compiled in
 *   -DPROFILE=5  P5 VESA (the DOS example): a streamed face with a block cache, scale 3/2, draws on INDEXED8, RGB555,
 *                RGB565, XRGB8888 and RGB888; built with -DSVF_TARGETS=0x1E8. A link-and-size profile, not a runnable
 *                one: its 512-byte tables and 256-byte scratch do not cover JSET tables or 3/2 scaled cells.
 *
 * The face and the text come from volatile pointers, so nothing is folded at compile time; the program is linked,
 * never run. Its buffers are sized to fit the 2 KB RAM of an ATmega328P in every profile (the AVR link checks it).
 */
#include "svf.h"

#include <stdint.h>

#ifndef PROFILE
#error "build with -DPROFILE=0..5"
#endif

#ifndef PROBE_KIND
#define PROBE_KIND SVF_T_RGB565 /* PROFILE 3 only */
#endif

#if PROFILE > 0
const uint8_t *volatile probe_face;
volatile uint32_t probe_face_len;
const char *volatile probe_text;
volatile uint16_t probe_text_len;
volatile uint8_t probe_sink;

static svf_face face;
static uint8_t scratch[256];
#endif

#if PROFILE == 1 || PROFILE == 2
static uint8_t page[128 * 32 / 8];

int main(void)
{
	svf_face *faces[1] = {&face};
	svf_chain c = {0};
	svf_target t;

	if (svf_open_mapped(&face, probe_face, probe_face_len) != SVF_OK)
		return 1;
	c.faces = faces;
	c.count = 1;
	if (svf_target_init(&t, SVF_T_MONO_PAGE, page, sizeof page, 128, 32, 128) != SVF_OK)
		return 1;
	return svf_draw_utf8(&c, probe_text, probe_text_len, 0, 14, &t, scratch, sizeof scratch);
}
#elif PROFILE == 3
static uint8_t tft[32 * 8 * 2];
static uint8_t syllables[256];

int main(void)
{
	svf_face *faces[1] = {&face};
	svf_chain c = {0};
	svf_target t;

	if (svf_open_mapped(&face, probe_face, probe_face_len) != SVF_OK)
		return 1;
	c.faces = faces;
	c.count = 1;
	if (svf_chain_cache(&c, syllables, sizeof syllables) != SVF_OK)
		return 1;
	if (svf_target_init(&t, PROBE_KIND, tft, sizeof tft, 32, 8, 64) != SVF_OK)
		return 1;
	t.fg565 = 0xFFE0;
	return svf_draw_utf8(&c, probe_text, probe_text_len, 0, 14, &t, scratch, sizeof scratch);
}
#elif PROFILE == 4
static svf_face face2;
static uint8_t tables[512], blocks[2 * (64 + 8)], syllables[256], screen[16 * 8 * 4]; /* the largest kind: XRGB8888, row 64 */

static long probe_read(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	const uint8_t *src = (const uint8_t *)ctx + offset;
	uint32_t i;

	for (i = 0; i < len; ++i)
		dst[i] = src[i];
	return (long)len;
}

static void probe_plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	(void)ctx;
	probe_sink = (uint8_t)(probe_sink + x + y + cov);
}

int main(void)
{
	static const svf_target_kind kinds[] = {SVF_T_GRAY8,   SVF_T_MONO_PAGE, SVF_T_MONO_ROW,
	                                        SVF_T_RGB565,  SVF_T_COVERAGE_CB, SVF_T_INDEXED8,
	                                        SVF_T_RGB555,  SVF_T_XRGB8888,    SVF_T_RGB888
#if SVF_TARGETS & SVF_TARGET_GRAY
	                                        , SVF_T_GRAY
#endif
	};
	svf_face *faces[2] = {&face, &face2};
	svf_chain c = {0};
	svf_target t;
	svf_metrics m;
	svf_extent e;
	svf_err err;
	uint16_t pieces[3];
	unsigned k, sum = 0;
	void *ctx = (void *)(uintptr_t)probe_face;

	if (svf_open_mapped(&face, probe_face, probe_face_len) != SVF_OK)
		return 1;
	if (svf_stream_tables_size(probe_read, ctx, probe_face_len, &err) > sizeof tables)
		return 1;
	if (svf_open_stream(&face2, probe_read, ctx, probe_face_len, tables, sizeof tables, blocks, sizeof blocks, 64) !=
	    SVF_OK)
		return 1;
	sum += svf_bpp(&face) + svf_cell_w(&face) + svf_cell_h(&face) + svf_ascent(&face) + svf_flags(&face) +
	       svf_status(&face) + svf_glyph_count(&face) + (unsigned)svf_cmap_cp(&face, 0) + (unsigned)svf_has(&face, 'A') +
	       (unsigned)svf_metrics_of(&face, 'A', &m) + (unsigned)svf_cell_bytes(&face) + svf_stream_reads(&face2) +
	       (unsigned)svf_is_jamo(&face) + (unsigned)svf_jamo_pieces(&face, 0xAC00, pieces) +
	       (unsigned)svf_glyph(&face, 'A', scratch, sizeof scratch) +
	       (unsigned)svf_compose(&face, 0xAC00, scratch, sizeof scratch) + (unsigned)svf_is_mark_default(0x301);
	c.faces = faces;
	c.count = 2;
	c.scale_num = 3;
	c.scale_den = 2;
	if (svf_chain_cache(&c, syllables, sizeof syllables) != SVF_OK)
		return 1;
	if (svf_chain_scratch_bytes(&c) > sizeof scratch)
		return 1;
	if (svf_measure_utf8(&c, probe_text, probe_text_len, &e) != SVF_OK)
		return 1;
	sum += (unsigned)e.width;
	for (k = 0; k < sizeof kinds / sizeof kinds[0]; ++k) {
		if (svf_target_init(&t, kinds[k], screen, sizeof screen, 16, 8, 64) != SVF_OK)
			return 1;
		if (kinds[k] == SVF_T_GRAY)
			t.gray_bits = 4;
		t.plot = probe_plot;
		sum += (unsigned)svf_draw_utf8(&c, probe_text, probe_text_len, 0, 20, &t, scratch, sizeof scratch);
	}
	probe_sink = (uint8_t)sum;
	return 0;
}
#elif PROFILE == 5
static uint8_t tables[512], blocks[2 * (64 + 8)], syllables[256], screen[16 * 8 * 4];

static long probe_read(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	const uint8_t *src = (const uint8_t *)ctx + offset;
	uint32_t i;

	for (i = 0; i < len; ++i)
		dst[i] = src[i];
	return (long)len;
}

int main(void)
{
	static const svf_target_kind kinds[5] = {SVF_T_INDEXED8, SVF_T_RGB555, SVF_T_RGB565, SVF_T_XRGB8888,
	                                         SVF_T_RGB888};
	svf_face *faces[1] = {&face};
	svf_chain c = {0};
	svf_target t;
	unsigned k, sum = 0;
	void *ctx = (void *)(uintptr_t)probe_face;

	if (svf_open_stream(&face, probe_read, ctx, probe_face_len, tables, sizeof tables, blocks, sizeof blocks, 64) !=
	    SVF_OK)
		return 1;
	c.faces = faces;
	c.count = 1;
	c.scale_num = 3;
	c.scale_den = 2;
	if (svf_chain_cache(&c, syllables, sizeof syllables) != SVF_OK)
		return 1;
	for (k = 0; k < 5; ++k) {
		if (svf_target_init(&t, kinds[k], screen, sizeof screen, 16, 8, 64) != SVF_OK)
			return 1;
		sum += (unsigned)svf_draw_utf8(&c, probe_text, probe_text_len, 0, 20, &t, scratch, sizeof scratch);
	}
	probe_sink = (uint8_t)sum;
	return 0;
}
#else
int main(void)
{
	return 0;
}
#endif
