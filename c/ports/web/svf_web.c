/* svf_web.c - emscripten glue: the SVF renderer as a few exported functions drawing into a GRAY8 buffer.
 *
 * JavaScript owns the memory it hands in (Module._malloc): the face files and the pixel buffer. The glue keeps a chain
 * of up to SVFW_FACES faces (slot 0 tried first), one target and the scratch a glyph needs.
 *
 *   svfw_open(slot, data, len)          opens the face file at data (len bytes, kept by JS while used) in slot;
 *                                       slots open in order: a slot past the chain (one after the last open slot)
 *                                       is SVF_E_ARG; the slots after it are closed. The chain is the run of open
 *                                       slots from slot 0 (a slot whose open failed ends it), so no draw sees an
 *                                       unopened or stale face. Returns an svf_err.
 *   svfw_target(buf, w, h)              draws into buf from now on: w * h bytes, one a pixel, row after row; a drawn
 *                                       pixel becomes max(itself, coverage 0..255). Returns an svf_err.
 *   svfw_scale(num, den)                the line scale (1..16 each; 1, 1 unscaled). Returns an svf_err.
 *   svfw_measure(text, len, out)        out[0..2] (int16) = width, ascent, descent of len bytes of UTF-8 at text.
 *   svfw_draw(text, len, x, baseline)   draws len bytes of UTF-8 at text, the pen at x on the row baseline.
 *   svfw_reset()                        closes every slot (the chain has no face until one is opened). SVF_OK.
 *   svfw_info(slot, out)                out[0..7] (int32) = bpp, cell_w, cell_h, ascent, flags, status, glyph count,
 *                                       is_jamo of the face in slot; SVF_E_ARG for a slot not open.
 *   svfw_has(slot, cp)                  svf_has of the face in slot: non-zero if it draws cp; 0 for a slot not open.
 *   svfw_target2(kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags)
 *                                       draws into buf from now on as svf_target kind 0..3 (GRAY8, MONO_PAGE,
 *                                       MONO_ROW, RGB565; the callback kind 4 is SVF_E_ARG): buf_len bytes, stride
 *                                       bytes a row (a page for MONO_PAGE), fg565 / bg565 0..0xFFFF, threshold 0..255,
 *                                       flags 0 or SVF_TF_565_BIGENDIAN. Returns an svf_err.
 *   svfw_order(first)                   the chain tries slot first first, the other slots after it in slot order
 *                                       (svfw_order(0) is slot order again); no face is reopened. SVF_E_ARG for a slot
 *                                       not open or a chain with an unopened slot. svfw_open and svfw_reset restore
 *                                       slot order. svfw_info and svfw_has always name slots, whatever the order.
 *
 * Scratch: svfw_draw needs svf_chain_scratch_bytes of the chain. The first buffer is a static 64 KB; a draw that needs
 * more mallocs a buffer of exactly the need first (freeing the previous one if it was malloced). A failed malloc
 * returns SVF_E_NOMEM, draws nothing and keeps the previous buffer. The port allocates; c/src never does.
 */
#include "svf.h"

#include <emscripten.h>
#include <stdlib.h>
#include <string.h>

#define SVFW_FACES 4
#define SVFW_SCRATCH 65536 /* the first scratch: an 18 px face up to 14x (2 * 90 + 252 * 252 bytes) */

static svf_face faces[SVFW_FACES];
static uint8_t opened[SVFW_FACES]; /* 1 for a slot svfw_open opened (until svfw_reset) */
static svf_face *chain_faces[SVFW_FACES] = {&faces[0], &faces[1], &faces[2], &faces[3]};
static svf_chain chain = {.faces = chain_faces}; /* count grows as slots are opened */

/* chain_faces in slot order, slot first moved to the front. Safe only because the glue sets no svf_chain_cache: that
 * cache keys its slots by chain index, so a reordered chain would be served another face's cells. */
static void order(int first)
{
	int i, n = 0;

	chain_faces[n++] = &faces[first];
	for (i = 0; i < SVFW_FACES; i++)
		if (i != first)
			chain_faces[n++] = &faces[i];
}
static svf_target target;
static uint8_t scratch_static[SVFW_SCRATCH];
static uint8_t *scratch = scratch_static;
static size_t scratch_len = sizeof scratch_static;

EMSCRIPTEN_KEEPALIVE int svfw_open(int slot, const uint8_t *data, uint32_t len)
{
	svf_err e;
	int n;

	if (slot < 0 || slot >= SVFW_FACES || slot > chain.count)
		return SVF_E_ARG;
	order(0);
	for (n = slot + 1; n < SVFW_FACES; n++) { /* the slots after it are forgotten: no stale face rejoins the chain */
		memset(&faces[n], 0, sizeof faces[n]);
		opened[n] = 0;
	}
	e = svf_open_mapped(&faces[slot], data, len);
	opened[slot] = e == SVF_OK;
	for (n = 0; n < SVFW_FACES && opened[n]; n++)
		;
	chain.count = (uint8_t)n; /* the open prefix */
	return e;
}

EMSCRIPTEN_KEEPALIVE int svfw_target(uint8_t *buf, int w, int h)
{
	if (w <= 0 || h <= 0 || w > 32767 || h > 32767)
		return SVF_E_ARG;
	return svf_target_init(&target, SVF_T_GRAY8, buf, (size_t)w * (size_t)h, (int16_t)w, (int16_t)h, (uint16_t)w);
}

EMSCRIPTEN_KEEPALIVE int svfw_scale(int num, int den)
{
	if (num < 1 || num > 16 || den < 1 || den > 16)
		return SVF_E_ARG;
	chain.scale_num = (uint8_t)num;
	chain.scale_den = (uint8_t)den;
	return SVF_OK;
}

EMSCRIPTEN_KEEPALIVE int svfw_measure(const char *text, int len, int16_t *out)
{
	svf_extent e;
	svf_err r;

	if (len < 0 || !out)
		return SVF_E_ARG;
	r = svf_measure_utf8(&chain, text, (size_t)len, &e);
	if (r == SVF_OK) {
		out[0] = e.width;
		out[1] = e.ascent;
		out[2] = e.descent;
	}
	return r;
}

EMSCRIPTEN_KEEPALIVE int svfw_draw(const char *text, int len, int x, int baseline)
{
	size_t need;

	if (len < 0)
		return SVF_E_ARG;
	need = svf_chain_scratch_bytes(&chain);
	if (need > scratch_len) {
		uint8_t *p = malloc(need);

		if (!p)
			return SVF_E_NOMEM;
		if (scratch != scratch_static)
			free(scratch);
		scratch = p;
		scratch_len = need;
	}
	return svf_draw_utf8(&chain, text, (size_t)len, (int16_t)x, (int16_t)baseline, &target, scratch, scratch_len);
}

EMSCRIPTEN_KEEPALIVE int svfw_reset(void)
{
	memset(faces, 0, sizeof faces);
	memset(opened, 0, sizeof opened);
	chain.count = 0;
	order(0);
	return SVF_OK;
}

EMSCRIPTEN_KEEPALIVE int svfw_info(int slot, int32_t *out)
{
	const svf_face *f;

	if (slot < 0 || slot >= SVFW_FACES || !opened[slot] || !out)
		return SVF_E_ARG;
	f = &faces[slot];
	out[0] = svf_bpp(f);
	out[1] = svf_cell_w(f);
	out[2] = svf_cell_h(f);
	out[3] = svf_ascent(f);
	out[4] = svf_flags(f);
	out[5] = svf_status(f);
	out[6] = svf_glyph_count(f);
	out[7] = svf_is_jamo(f) != 0;
	return SVF_OK;
}

EMSCRIPTEN_KEEPALIVE int svfw_has(int slot, uint32_t cp)
{
	if (slot < 0 || slot >= SVFW_FACES || !opened[slot])
		return 0;
	return svf_has(&faces[slot], cp) != 0;
}

EMSCRIPTEN_KEEPALIVE int svfw_target2(int kind, uint8_t *buf, uint32_t buf_len, int w, int h, int stride, int fg565,
                                      int bg565, int threshold, int flags)
{
	svf_err e;

	if (kind < SVF_T_GRAY8 || kind > SVF_T_RGB565 || w <= 0 || h <= 0 || w > 32767 || h > 32767 || stride < 0 ||
	    stride > 65535 || fg565 < 0 || fg565 > 0xFFFF || bg565 < 0 || bg565 > 0xFFFF || threshold < 0 ||
	    threshold > 255 || (flags & ~(int)SVF_TF_565_BIGENDIAN) != 0)
		return SVF_E_ARG;
	e = svf_target_init(&target, (svf_target_kind)kind, buf, buf_len, (int16_t)w, (int16_t)h, (uint16_t)stride);
	if (e != SVF_OK)
		return e;
	target.fg565 = (uint16_t)fg565;
	target.bg565 = (uint16_t)bg565;
	target.mono_threshold = (uint8_t)threshold;
	target.flags = (uint8_t)flags;
	return SVF_OK;
}

EMSCRIPTEN_KEEPALIVE int svfw_order(int first)
{
	int i;

	if (first < 0 || first >= chain.count)
		return SVF_E_ARG;
	for (i = 0; i < chain.count; i++)
		if (!opened[i])
			return SVF_E_ARG;
	order(first);
	return SVF_OK;
}
