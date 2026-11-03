/* test_args - every public entry point of svf.h called with each NULL pointer and bad argument (host only, run under
 * the sanitizer build by tools/test_c_renderer.py). Prints one line per case; exit 0 when all pass, 1 otherwise.
 *
 *   test-args FACE       FACE must have a valid JSET (a composed syllable is exercised too)
 *
 * Each case names the call and the result svf.h documents for it: SVF_E_ARG for a function returning svf_err, the
 * sentinel for one that cannot (0, -1, 0xFFFFFFFF), and out-parameters left untouched where the header says so. The
 * same calls are made with a zeroed face (what a failed open leaves), which must also be safe.
 */
#include "svf.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int bad;

static void check(const char *name, int ok)
{
	printf("%s: %s\n", name, ok ? "ok" : "FAIL");
	bad |= !ok;
}

/* One case: "WHO: WHAT: ok" when EXPR holds (uses the caller's who and name). */
#define CASE(what, expr)                                                                                               \
	do {                                                                                                           \
		snprintf(name, sizeof name, "%s: %s", who, what);                                                      \
		check(name, expr);                                                                                     \
	} while (0)

typedef struct {
	const uint8_t *data;
	size_t len;
} source;

static long read_cb(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	source *s = ctx;

	if (offset > s->len || len > s->len - offset)
		return -1;
	memcpy(dst, s->data + offset, len);
	return (long)len;
}

static uint8_t *read_file(const char *path, size_t *len)
{
	FILE *fp = fopen(path, "rb");
	uint8_t *buf = NULL;
	long n;

	if (!fp)
		return NULL;
	if (fseek(fp, 0, SEEK_END) == 0 && (n = ftell(fp)) > 0 && fseek(fp, 0, SEEK_SET) == 0) {
		buf = malloc((size_t)n);
		if (buf && fread(buf, 1, (size_t)n, fp) != (size_t)n) {
			free(buf);
			buf = NULL;
		}
		*len = (size_t)n;
	}
	fclose(fp);
	return buf;
}

/* The face accessors and lookups with @p f (NULL or a zeroed face): every sentinel. */
static void face_queries(const char *who, const svf_face *f)
{
	char name[96];
	svf_metrics m = {7, 7, 7, 7};
	uint16_t out[3] = {7, 7, 7};
	uint8_t cell[64];

	CASE("svf_bpp 0", svf_bpp(f) == 0);
	CASE("svf_cell_w 0", svf_cell_w(f) == 0);
	CASE("svf_cell_h 0", svf_cell_h(f) == 0);
	CASE("svf_ascent 0", svf_ascent(f) == 0);
	CASE("svf_flags 0", svf_flags(f) == 0);
	CASE("svf_status 0", svf_status(f) == 0);
	CASE("svf_glyph_count 0", svf_glyph_count(f) == 0);
	CASE("svf_cell_bytes 0", svf_cell_bytes(f) == 0);
	CASE("svf_cmap_cp 0xFFFFFFFF", svf_cmap_cp(f, 0) == 0xFFFFFFFFu);
	CASE("svf_has 0", !svf_has(f, 'A') && !svf_has(f, 0xAC00));
	CASE("svf_metrics_of -1, m untouched",
	     svf_metrics_of(f, 'A', &m) == -1 && svf_metrics_of(f, 0xAC00, &m) == -1 && m.advance == 7 &&
	         m.bearing_x == 7 && m.ink_w == 7 && m.dy == 7);
	CASE("svf_stream_reads 0", svf_stream_reads(f) == 0);
	CASE("svf_is_jamo 0", !svf_is_jamo(f));
	CASE("svf_jamo_pieces 0, out untouched",
	     svf_jamo_pieces(f, 0xAC00, out) == 0 && svf_jamo_pieces(f, 0x3131, out) == 0 && out[0] == 7 && out[1] == 7 &&
	         out[2] == 7);
	if (!f) {
		CASE("svf_glyph SVF_E_ARG", svf_glyph(f, 'A', cell, sizeof cell) == SVF_E_ARG);
		CASE("svf_compose SVF_E_ARG", svf_compose(f, 0xAC00, cell, sizeof cell) == SVF_E_ARG);
	} else {
		CASE("svf_glyph SVF_E_RANGE", svf_glyph(f, 'A', cell, sizeof cell) == SVF_E_RANGE);
		CASE("svf_compose SVF_E_RANGE", svf_compose(f, 0xAC00, cell, sizeof cell) == SVF_E_RANGE);
	}
}

/* NULL out-parameters and buffers with an opened face @p f (who names its source). */
static void face_buffers(const char *who, const svf_face *f)
{
	char name[96];
	uint16_t out[3];
	uint8_t cell[1];

	CASE("open", svf_glyph_count(f) > 0 && svf_is_jamo(f));
	CASE("svf_metrics_of NULL m: -1", svf_metrics_of(f, 'A', NULL) == -1 && svf_metrics_of(f, 0xAC00, NULL) == -1);
	CASE("svf_jamo_pieces NULL out: 0", svf_jamo_pieces(f, 0xAC00, NULL) == 0 && svf_jamo_pieces(f, 0x3131, NULL) == 0);
	CASE("svf_jamo_pieces works", svf_jamo_pieces(f, 0xAC00, out) >= 2);
	CASE("svf_glyph NULL cell, len > 0: SVF_E_ARG",
	     svf_glyph(f, 'A', NULL, 4096) == SVF_E_ARG && svf_glyph(f, 0xAC00, NULL, 4096) == SVF_E_ARG &&
	         svf_glyph(f, 0x10FFFF, NULL, 4096) == SVF_E_ARG);
	CASE("svf_glyph NULL cell, len 0: SVF_E_NOMEM",
	     svf_glyph(f, 'A', NULL, 0) == SVF_E_NOMEM && svf_glyph(f, 0xAC00, NULL, 0) == SVF_E_NOMEM);
	CASE("svf_glyph short cell: SVF_E_NOMEM", svf_glyph(f, 'A', cell, sizeof cell) == SVF_E_NOMEM);
	CASE("svf_compose NULL cell, len > 0: SVF_E_ARG",
	     svf_compose(f, 0xAC00, NULL, 4096) == SVF_E_ARG && svf_compose(f, 'A', NULL, 4096) == SVF_E_ARG);
	CASE("svf_compose NULL cell, len 0: SVF_E_NOMEM", svf_compose(f, 0xAC00, NULL, 0) == SVF_E_NOMEM);
}

static void opens(const uint8_t *data, size_t len, source *src)
{
	const char *who = "open";
	char name[96];
	static uint8_t tables[1 << 20], cache[4096];
	svf_face f;
	svf_err e = SVF_OK;

	{
		const uint16_t *set = (const uint16_t *)data; /* not NULL: svf_layouts overwrites it */
		CASE("svf_layouts NULL set", svf_layouts(NULL) == svf_layouts(&set));
		CASE("svf_layouts set", (svf_layouts(&set) == 0) == (set == NULL));
	}
	CASE("svf_open_mapped NULL face", svf_open_mapped(NULL, data, len) == SVF_E_ARG);
	CASE("svf_open_mapped NULL data, len > 0", svf_open_mapped(&f, NULL, len) == SVF_E_ARG);
	CASE("svf_open_mapped NULL data, len 0: SVF_E_MAGIC", svf_open_mapped(&f, NULL, 0) == SVF_E_MAGIC);
	CASE("svf_open_stream NULL face",
	     svf_open_stream(NULL, read_cb, src, (uint32_t)len, tables, sizeof tables, NULL, 0, 0) == SVF_E_ARG);
	CASE("svf_open_stream NULL callback",
	     svf_open_stream(&f, NULL, src, (uint32_t)len, tables, sizeof tables, NULL, 0, 0) == SVF_E_ARG);
	CASE("svf_open_stream NULL tables, len > 0",
	     svf_open_stream(&f, read_cb, src, (uint32_t)len, NULL, sizeof tables, NULL, 0, 0) == SVF_E_ARG);
	CASE("svf_open_stream NULL tables, len 0: SVF_E_NOMEM",
	     svf_open_stream(&f, read_cb, src, (uint32_t)len, NULL, 0, NULL, 0, 0) == SVF_E_NOMEM);
	CASE("svf_open_stream NULL cache, len > 0",
	     svf_open_stream(&f, read_cb, src, (uint32_t)len, tables, sizeof tables, NULL, sizeof cache, 512) == SVF_E_ARG);
	CASE("svf_open_stream bad block size",
	     svf_open_stream(&f, read_cb, src, (uint32_t)len, tables, sizeof tables, cache, sizeof cache, 100) == SVF_E_ARG);
	CASE("svf_stream_tables_size NULL callback: 0, SVF_E_ARG",
	     svf_stream_tables_size(NULL, src, (uint32_t)len, &e) == 0 && e == SVF_E_ARG);
	CASE("svf_stream_tables_size NULL err", svf_stream_tables_size(read_cb, src, (uint32_t)len, NULL) > 0);
	CASE("svf_stream_tables_size NULL callback, NULL err: 0", svf_stream_tables_size(NULL, src, (uint32_t)len, NULL) == 0);
}

static void plot_cb(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	(void)ctx;
	(void)x;
	(void)y;
	(void)cov;
}

#if SVF_TARGETS == 0x3FFu
static void lines(svf_face *good)
{
	const char *who = "line";
	char name[96];
	static uint8_t buf[64 * 32], scratch[8192], cbuf[8192];
	svf_face zero, *faces[2], *nulls[1] = {NULL}, *zeros[1];
	svf_chain c, nc;
	svf_target t, cb;
	svf_extent ex = {7, 7, 7};
	const char *text = "A\xea\xb0\x80"; /* "A" U+AC00 */

	memset(&zero, 0, sizeof zero);
	faces[0] = good;
	faces[1] = &zero;
	zeros[0] = &zero;
	memset(&c, 0, sizeof c);
	c.faces = faces;
	c.count = 2;

	/* svf_target_init */
	CASE("svf_target_init NULL target", svf_target_init(NULL, SVF_T_GRAY8, buf, sizeof buf, 64, 32, 64) == SVF_E_ARG);
	CASE("svf_target_init NULL buf", svf_target_init(&t, SVF_T_GRAY8, NULL, sizeof buf, 64, 32, 64) == SVF_E_ARG);
	CASE("svf_target_init bad kind", svf_target_init(&t, (svf_target_kind)99, buf, sizeof buf, 64, 32, 64) == SVF_E_ARG);
	CASE("svf_target_init NULL buf, coverage cb", svf_target_init(&cb, SVF_T_COVERAGE_CB, NULL, 0, 64, 32, 0) == SVF_OK);
	CASE("svf_target_init ok", svf_target_init(&t, SVF_T_GRAY8, buf, sizeof buf, 64, 32, 64) == SVF_OK);

	/* svf_chain_scratch_bytes */
	CASE("svf_chain_scratch_bytes NULL chain: 0", svf_chain_scratch_bytes(NULL) == 0);
	nc = c;
	nc.faces = NULL;
	CASE("svf_chain_scratch_bytes NULL faces: 0", svf_chain_scratch_bytes(&nc) == 0);
	nc = c;
	nc.count = 0;
	CASE("svf_chain_scratch_bytes no faces: 0", svf_chain_scratch_bytes(&nc) == 0);
	nc = c;
	nc.faces = nulls;
	nc.count = 1;
	CASE("svf_chain_scratch_bytes NULL face: 0", svf_chain_scratch_bytes(&nc) == 0);
	nc = c;
	nc.scale_num = 17;
	nc.scale_den = 1;
	CASE("svf_chain_scratch_bytes refused ratio: 0", svf_chain_scratch_bytes(&nc) == 0);
	CASE("svf_chain_scratch_bytes ok", svf_chain_scratch_bytes(&c) > 0 && svf_chain_scratch_bytes(&c) <= sizeof scratch);

	/* svf_chain_cache */
	CASE("svf_chain_cache NULL chain", svf_chain_cache(NULL, cbuf, sizeof cbuf) == SVF_E_ARG);
	nc = c;
	nc.faces = NULL;
	CASE("svf_chain_cache NULL faces", svf_chain_cache(&nc, cbuf, sizeof cbuf) == SVF_E_ARG && !nc.cache);
	nc = c;
	nc.faces = nulls;
	nc.count = 1;
	CASE("svf_chain_cache NULL face", svf_chain_cache(&nc, cbuf, sizeof cbuf) == SVF_E_ARG && !nc.cache);
	nc = c;
	nc.count = 0;
	CASE("svf_chain_cache no faces", svf_chain_cache(&nc, cbuf, sizeof cbuf) == SVF_E_ARG);
	nc = c;
	CASE("svf_chain_cache NULL buf, len > 0", svf_chain_cache(&nc, NULL, sizeof cbuf) == SVF_E_ARG && !nc.cache);
	CASE("svf_chain_cache NULL buf, len 0", svf_chain_cache(&nc, NULL, 0) == SVF_OK && !nc.cache);
	CASE("svf_chain_cache too small: SVF_E_NOMEM", svf_chain_cache(&nc, cbuf, 1) == SVF_E_NOMEM && !nc.cache);

	/* svf_measure_utf8 */
	CASE("svf_measure_utf8 NULL chain", svf_measure_utf8(NULL, text, 4, &ex) == SVF_E_ARG);
	CASE("svf_measure_utf8 NULL extent", svf_measure_utf8(&c, text, 4, NULL) == SVF_E_ARG);
	CASE("svf_measure_utf8 NULL text, len > 0", svf_measure_utf8(&c, NULL, 4, &ex) == SVF_E_ARG);
	CASE("svf_measure_utf8 NULL text, len 0",
	     svf_measure_utf8(&c, NULL, 0, &ex) == SVF_OK && ex.width == 0 && ex.ascent == 0 && ex.descent == 0);
	nc = c;
	nc.faces = nulls;
	nc.count = 1;
	CASE("svf_measure_utf8 NULL face", svf_measure_utf8(&nc, text, 4, &ex) == SVF_E_ARG);
	nc = c;
	nc.faces = NULL;
	CASE("svf_measure_utf8 NULL faces", svf_measure_utf8(&nc, text, 4, &ex) == SVF_E_ARG);
	nc = c;
	nc.scale_num = 0;
	nc.scale_den = 3;
	CASE("svf_measure_utf8 refused ratio", svf_measure_utf8(&nc, text, 4, &ex) == SVF_E_ARG);
	nc = c;
	nc.faces = zeros;
	nc.count = 1;
	CASE("svf_measure_utf8 zeroed face", svf_measure_utf8(&nc, text, 4, &ex) == SVF_OK);

	/* svf_draw_utf8 */
	CASE("svf_draw_utf8 NULL chain", svf_draw_utf8(NULL, text, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_E_ARG);
	CASE("svf_draw_utf8 NULL text, len > 0", svf_draw_utf8(&c, NULL, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_E_ARG);
	CASE("svf_draw_utf8 NULL text, len 0", svf_draw_utf8(&c, NULL, 0, 0, 20, &t, scratch, sizeof scratch) == SVF_OK);
	CASE("svf_draw_utf8 NULL target", svf_draw_utf8(&c, text, 4, 0, 20, NULL, scratch, sizeof scratch) == SVF_E_ARG);
	CASE("svf_draw_utf8 NULL scratch, len > 0", svf_draw_utf8(&c, text, 4, 0, 20, &t, NULL, sizeof scratch) == SVF_E_ARG);
	CASE("svf_draw_utf8 NULL scratch, len 0: SVF_E_NOMEM", svf_draw_utf8(&c, text, 4, 0, 20, &t, NULL, 0) == SVF_E_NOMEM);
	nc = c;
	nc.faces = nulls;
	nc.count = 1;
	CASE("svf_draw_utf8 NULL face", svf_draw_utf8(&nc, text, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_E_ARG);
	nc = c;
	nc.faces = NULL;
	CASE("svf_draw_utf8 NULL faces", svf_draw_utf8(&nc, text, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_E_ARG);
	nc = c;
	nc.faces = zeros;
	nc.count = 1;
	CASE("svf_draw_utf8 zeroed face", svf_draw_utf8(&nc, text, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_OK);
	{
		svf_target tb = t;
		tb.buf = NULL;
		CASE("svf_draw_utf8 target buf edited to NULL",
		     svf_draw_utf8(&c, text, 4, 0, 20, &tb, scratch, sizeof scratch) == SVF_E_ARG);
	}
	CASE("svf_draw_utf8 coverage cb without plot",
	     svf_draw_utf8(&c, text, 4, 0, 20, &cb, scratch, sizeof scratch) == SVF_E_ARG);
	cb.plot = plot_cb;
	CASE("svf_draw_utf8 coverage cb with plot", svf_draw_utf8(&c, text, 4, 0, 20, &cb, scratch, sizeof scratch) == SVF_OK);
	CASE("svf_draw_utf8 ok", svf_draw_utf8(&c, text, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_OK);
#if SVF_TARGETS & SVF_TARGET_GRAY
	{
		static uint8_t gbuf[16 * 64];
		svf_target tg;
		const unsigned bits_list[3] = {0, 3, 16};
		char label[32];
		unsigned i;

		CASE("init GRAY stride 8 ok",
		     svf_target_init(&tg, SVF_T_GRAY, gbuf, 16 * 8, 63, 16, 8) == SVF_OK && tg.gray_bits == 8 &&
		         tg.mono_threshold == 128);
		CASE("init GRAY stride 7", svf_target_init(&tg, SVF_T_GRAY, gbuf, 16 * 7, 63, 16, 7) == SVF_E_ARG);
		CASE("init GRAY buf_len 127", svf_target_init(&tg, SVF_T_GRAY, gbuf, 127, 63, 16, 8) == SVF_E_ARG);
		CASE("init GRAY NULL buf", svf_target_init(&tg, SVF_T_GRAY, NULL, 16 * 8, 63, 16, 8) == SVF_E_ARG);
		(void)svf_target_init(&tg, SVF_T_GRAY, gbuf, 16 * 8, 63, 16, 8);
		CASE("draw GRAY bits 8 on stride 8",
		     svf_draw_utf8(&c, text, 4, 0, 12, &tg, scratch, sizeof scratch) == SVF_E_ARG);
		tg.gray_bits = 1;
		CASE("draw GRAY bits 1 on stride 8",
		     svf_draw_utf8(&c, text, 4, 0, 12, &tg, scratch, sizeof scratch) == SVF_OK);
		(void)svf_target_init(&tg, SVF_T_GRAY, gbuf, 16 * 31, 63, 16, 31);
		tg.gray_bits = 4;
		CASE("draw GRAY bits 4 on stride 31",
		     svf_draw_utf8(&c, text, 4, 0, 12, &tg, scratch, sizeof scratch) == SVF_E_ARG);
		(void)svf_target_init(&tg, SVF_T_GRAY, gbuf, 16 * 32, 63, 16, 32);
		tg.gray_bits = 4;
		CASE("draw GRAY bits 4 on stride 32",
		     svf_draw_utf8(&c, text, 4, 0, 12, &tg, scratch, sizeof scratch) == SVF_OK);
		for (i = 0; i < 3; ++i) {
			(void)svf_target_init(&tg, SVF_T_GRAY, gbuf, 16 * 64, 63, 16, 64);
			tg.gray_bits = (uint8_t)bits_list[i];
			snprintf(label, sizeof label, "draw GRAY bits %u", bits_list[i]);
			CASE(label, svf_draw_utf8(&c, text, 4, 0, 12, &tg, scratch, sizeof scratch) == SVF_E_ARG);
		}
	}
#endif
#if SVF_TARGETS & SVF_TARGET_INDEXED8
	{
		static uint8_t ibuf[64 * 32];
		svf_target ti;
		CASE("svf_target_init INDEXED8 ok",
		     svf_target_init(&ti, SVF_T_INDEXED8, ibuf, sizeof ibuf, 64, 32, 64) == SVF_OK &&
		         ti.index_levels == 255 && ti.index_base == 0);
		CASE("svf_draw_utf8 INDEXED8 defaults",
		     svf_draw_utf8(&c, text, 4, 0, 20, &ti, scratch, sizeof scratch) == SVF_OK);
		ti.index_levels = 0;
		CASE("svf_draw_utf8 INDEXED8 index_levels 0",
		     svf_draw_utf8(&c, text, 4, 0, 20, &ti, scratch, sizeof scratch) == SVF_E_ARG);
		ti.index_base = 200;
		ti.index_levels = 56;
		CASE("svf_draw_utf8 INDEXED8 index_base 200 + 56 levels",
		     svf_draw_utf8(&c, text, 4, 0, 20, &ti, scratch, sizeof scratch) == SVF_E_ARG);
		ti.index_levels = 55;
		CASE("svf_draw_utf8 INDEXED8 index_base 200 + 55 levels",
		     svf_draw_utf8(&c, text, 4, 0, 20, &ti, scratch, sizeof scratch) == SVF_OK);
		ti.index_base = 0;
		ti.index_levels = 255;
		CASE("svf_draw_utf8 INDEXED8 index_base 0 + 255 levels",
		     svf_draw_utf8(&c, text, 4, 0, 20, &ti, scratch, sizeof scratch) == SVF_OK);
	}
#endif
#if SVF_TARGETS & SVF_TARGET_RGB555
	{
		static uint8_t rbuf[64 * 2 * 32];
		svf_target tr;
		CASE("svf_target_init RGB555 stride 2w ok, fg565 default 0xFFFF",
		     svf_target_init(&tr, SVF_T_RGB555, rbuf, sizeof rbuf, 64, 32, 128) == SVF_OK && tr.fg565 == 0xFFFFu);
		CASE("svf_target_init RGB555 stride 2w - 1 refused",
		     svf_target_init(&tr, SVF_T_RGB555, rbuf, sizeof rbuf, 64, 32, 127) == SVF_E_ARG);
		(void)svf_target_init(&tr, SVF_T_RGB555, rbuf, sizeof rbuf, 64, 32, 128);
		CASE("svf_draw_utf8 RGB555 ok", svf_draw_utf8(&c, text, 4, 0, 20, &tr, scratch, sizeof scratch) == SVF_OK);
		tr.stride = 127;
		CASE("svf_draw_utf8 RGB555 stride 2w - 1 edited in",
		     svf_draw_utf8(&c, text, 4, 0, 20, &tr, scratch, sizeof scratch) == SVF_E_ARG);
	}
#endif
#if SVF_TARGETS & (SVF_TARGET_XRGB8888 | SVF_TARGET_RGB888)
	{
		static uint8_t wide[65536 + 4], nb[64 * 4 * 8];
		svf_target tw;
#if SVF_TARGETS & SVF_TARGET_XRGB8888
		CASE("svf_target_init XRGB8888 width 16384 refused",
		     svf_target_init(&tw, SVF_T_XRGB8888, wide, sizeof wide, 16384, 1, 65535) == SVF_E_ARG);
		CASE("svf_target_init XRGB8888 width 16383 stride 65532 ok, fg888 default 0x00FFFFFF",
		     svf_target_init(&tw, SVF_T_XRGB8888, wide, sizeof wide, 16383, 1, 65532) == SVF_OK &&
		         tw.fg888 == 0x00FFFFFFu && tw.bg888 == 0);
		CASE("svf_target_init XRGB8888 width 16385 (4w wraps 16 bits to 4) refused",
		     svf_target_init(&tw, SVF_T_XRGB8888, wide, sizeof wide, 16385, 1, 65535) == SVF_E_ARG);
		CASE("svf_target_init XRGB8888 width 32767 (4w wraps to 65532) refused",
		     svf_target_init(&tw, SVF_T_XRGB8888, wide, sizeof wide, 32767, 1, 65535) == SVF_E_ARG);
		CASE("svf_target_init XRGB8888 NULL buf refused",
		     svf_target_init(&tw, SVF_T_XRGB8888, NULL, sizeof nb, 64, 8, 256) == SVF_E_ARG);
		CASE("svf_target_init XRGB8888 stride 4w - 1 refused",
		     svf_target_init(&tw, SVF_T_XRGB8888, nb, sizeof nb, 64, 8, 255) == SVF_E_ARG);
		CASE("svf_target_init XRGB8888 stride 4w ok",
		     svf_target_init(&tw, SVF_T_XRGB8888, nb, sizeof nb, 64, 8, 256) == SVF_OK);
		CASE("svf_draw_utf8 XRGB8888 ok", svf_draw_utf8(&c, text, 4, 0, 20, &tw, scratch, sizeof scratch) == SVF_OK);
		tw.stride = 255;
		CASE("svf_draw_utf8 XRGB8888 stride 4w - 1 edited in",
		     svf_draw_utf8(&c, text, 4, 0, 20, &tw, scratch, sizeof scratch) == SVF_E_ARG);
#endif
#if SVF_TARGETS & SVF_TARGET_RGB888
		CASE("svf_target_init RGB888 width 21846 refused",
		     svf_target_init(&tw, SVF_T_RGB888, wide, sizeof wide, 21846, 1, 65535) == SVF_E_ARG);
		CASE("svf_target_init RGB888 width 21845 stride 65535 ok",
		     svf_target_init(&tw, SVF_T_RGB888, wide, sizeof wide, 21845, 1, 65535) == SVF_OK);
		CASE("svf_target_init RGB888 width 21847 (3w wraps 16 bits to 5) refused",
		     svf_target_init(&tw, SVF_T_RGB888, wide, sizeof wide, 21847, 1, 65535) == SVF_E_ARG);
		CASE("svf_target_init RGB888 width 32767 (3w wraps to 32765) refused",
		     svf_target_init(&tw, SVF_T_RGB888, wide, sizeof wide, 32767, 1, 65535) == SVF_E_ARG);
		CASE("svf_target_init RGB888 width 21845 stride 65535: fg888 default 0x00FFFFFF, bg888 0",
		     svf_target_init(&tw, SVF_T_RGB888, wide, sizeof wide, 21845, 1, 65535) == SVF_OK &&
		         tw.fg888 == 0x00FFFFFFu && tw.bg888 == 0);
		CASE("svf_target_init RGB888 NULL buf refused",
		     svf_target_init(&tw, SVF_T_RGB888, NULL, sizeof nb, 64, 8, 192) == SVF_E_ARG);
		CASE("svf_target_init RGB888 stride 3w - 1 refused",
		     svf_target_init(&tw, SVF_T_RGB888, nb, sizeof nb, 64, 8, 191) == SVF_E_ARG);
		CASE("svf_target_init RGB888 stride 3w ok", svf_target_init(&tw, SVF_T_RGB888, nb, sizeof nb, 64, 8, 192) == SVF_OK);
		CASE("svf_draw_utf8 RGB888 ok", svf_draw_utf8(&c, text, 4, 0, 20, &tw, scratch, sizeof scratch) == SVF_OK);
		tw.stride = 191;
		CASE("svf_draw_utf8 RGB888 stride 3w - 1 edited in",
		     svf_draw_utf8(&c, text, 4, 0, 20, &tw, scratch, sizeof scratch) == SVF_E_ARG);
#endif
	}
#endif
	CASE("svf_chain_cache ok, then draw",
	     svf_chain_cache(&c, cbuf, sizeof cbuf) == SVF_OK &&
	         svf_draw_utf8(&c, text, 4, 0, 20, &t, scratch, sizeof scratch) == SVF_OK);
	CASE("svf_is_mark_default", svf_is_mark_default(0x301) && !svf_is_mark_default('A'));
}

#elif SVF_TARGETS == SVF_TARGET_MONO_PAGE || SVF_TARGETS == 0x1E8u || SVF_TARGETS == SVF_TARGET_GRAY
/* A build with kinds left out of SVF_TARGETS (make test-args-page, 0x02: MONO_PAGE only; make test-args-vesa,
 * 0x1E8: the five packed kinds; make test-args-gray, 0x200: GRAY only): every kind not in the mask is refused by svf_target_init and by svf_draw_utf8 on a
 * hand-edited target (the buffer, between guard bytes, is unchanged); a kept kind draws, so the refusals are the
 * left-out kinds. */
static void left_out(svf_face *good)
{
	static const char *const names[10] = {"GRAY8",    "MONO_PAGE", "MONO_ROW", "RGB565", "CB",
	                                      "INDEXED8", "RGB555",    "XRGB8888", "RGB888", "GRAY"};
	static const svf_target_kind kinds[10] = {SVF_T_GRAY8,    SVF_T_MONO_PAGE, SVF_T_MONO_ROW,
	                                          SVF_T_RGB565,   SVF_T_COVERAGE_CB, SVF_T_INDEXED8,
	                                          SVF_T_RGB555,   SVF_T_XRGB8888,    SVF_T_RGB888, SVF_T_GRAY};
	enum { STRIDE = 256, ROWS = 32 };
	static uint8_t mem[STRIDE * ROWS + 32], scratch[8192];
	uint8_t *buf = mem + 16;
	svf_face *faces[1];
	svf_chain c;
	svf_target t;
	char name[64];
	unsigned k, kept = 10;
	size_t i;
	int same = 1;

	faces[0] = good;
	memset(&c, 0, sizeof c);
	c.faces = faces;
	c.count = 1;
	memset(mem, 0x5A, sizeof mem);
	for (k = 0; k < 10; ++k)
		if (SVF_TARGETS & (1u << k))
			kept = k; /* the last kept kind is the control */
	check("left out: a kind is kept", kept < 10);
	for (k = 0; k < 10; ++k) {
		int in = (SVF_TARGETS & (1u << k)) != 0;

		/* arguments valid for any kind: width 64, row STRIDE bytes (4 w), buf_len for ROWS rows */
		snprintf(name, sizeof name, "left out: svf_target_init %s", names[k]);
		check(name, (svf_target_init(&t, kinds[k], buf, STRIDE * ROWS, 64, ROWS, STRIDE) == SVF_OK) == in);
	}
	/* a valid kept-kind target for the refusal loop below, which edits only t.kind */
	check("left out: kept kind init",
	      svf_target_init(&t, kinds[kept], buf, STRIDE * ROWS, 64, ROWS, STRIDE) == SVF_OK);
	for (k = 0; k < 10; ++k) {
		if (SVF_TARGETS & (1u << k))
			continue;
		t.kind = kinds[k]; /* a caller's edit of a valid target */
		t.plot = plot_cb;
		snprintf(name, sizeof name, "left out: svf_draw_utf8 %s", names[k]);
		check(name, svf_draw_utf8(&c, "A", 1, 2, 20, &t, scratch, sizeof scratch) == SVF_E_ARG);
	}
	for (i = 0; i < sizeof mem; ++i)
		same &= mem[i] == 0x5A;
	check("left out: buffer unchanged", same);
	/* control: t was edited above, so make it a valid kept-kind target again; the same draw then works, so the
	 * refusals above are the left-out kinds */
	check("left out: control init",
	      svf_target_init(&t, kinds[kept], buf, STRIDE * ROWS, 64, ROWS, STRIDE) == SVF_OK);
	check("left out: svf_draw_utf8 control ok", svf_draw_utf8(&c, "A", 1, 2, 20, &t, scratch, sizeof scratch) == SVF_OK);
#if SVF_TARGETS == SVF_TARGET_GRAY
	/* the GRAY-only build: bits 8 on a stride of w draws (blit_gray8 is compiled for GRAY alone) */
	check("left out: draw GRAY bits 8 on stride 63",
	      svf_target_init(&t, SVF_T_GRAY, buf, 63 * ROWS, 63, ROWS, 63) == SVF_OK &&
	          svf_draw_utf8(&c, "A", 1, 2, 20, &t, scratch, sizeof scratch) == SVF_OK);
#endif
}
#endif

int main(int argc, char **argv)
{
	size_t len = 0;
	uint8_t *data;
	static uint8_t tables[1 << 20], cache[4096];
	source src;
	svf_face mapped, streamed, zero;

	if (argc < 2) {
		fprintf(stderr, "usage: test-args FACE\n");
		return 2;
	}
	data = read_file(argv[1], &len);
	if (!data) {
		printf("%s: FAIL (cannot read)\n", argv[1]);
		return 1;
	}
	src.data = data;
	src.len = len;

	face_queries("NULL face", NULL);
	memset(&zero, 0, sizeof zero);
	face_queries("zeroed face", &zero);
	opens(data, len, &src);
	check("mapped: opens", svf_open_mapped(&mapped, data, len) == SVF_OK);
	face_buffers("mapped", &mapped);
	check("streamed: opens",
	      svf_open_stream(&streamed, read_cb, &src, (uint32_t)len, tables, sizeof tables, NULL, 0, 0) == SVF_OK);
	face_buffers("streamed", &streamed);
	check("streamed+cache: opens",
	      svf_open_stream(&streamed, read_cb, &src, (uint32_t)len, tables, sizeof tables, cache, sizeof cache, 512) ==
	          SVF_OK);
	face_buffers("streamed+cache", &streamed);
#if SVF_TARGETS == 0x3FFu
	lines(&mapped);
#elif SVF_TARGETS == SVF_TARGET_MONO_PAGE || SVF_TARGETS == 0x1E8u || SVF_TARGETS == SVF_TARGET_GRAY
	left_out(&mapped);
#endif
	free(data);
	return bad;
}
