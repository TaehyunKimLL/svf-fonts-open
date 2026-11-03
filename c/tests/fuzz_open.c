/* fuzz_open - libFuzzer harness over the v3 open, record expansion, metrics, line drawing and scaling (make fuzz).
 *
 * One input is a face file. It is copied three times, each copy exactly n bytes in its own allocation (a read past it is
 * an AddressSanitizer report, and one run cannot disturb another's bytes): svf_open_mapped on the first; svf_open_stream
 * on the second without a cache and on the third with a 4 KB cache of 64-byte blocks (-DSVF_NO_STREAM: mapped only).
 *
 * Each face that opens is exercised by exercise(): svf_glyph into a cell of EXACTLY svf_cell_bytes (twice that only for a
 * composed code point of an uncached streamed face, which svf.h requires) for every code point of the cmap, all compat
 * jamo, 19 x 21 lead-vowel syllables with a tail taken from the input's hash, the 28 tails of one lead-vowel pair, and
 * hash-picked syllables; svf_has and svf_metrics_of for the same; svf_measure_utf8 and svf_draw_utf8 of a fixed string set
 * (Latin, syllables, compat jamo, a mark, U+FFFD, invalid bytes) on every target kind the build has, with a clip that cuts
 * the cells, at scales 1/1, 3/2 and 2/1 (svf_scale), the target buffer and the scratch exactly sized, with and without
 * the chain's syllable cache. Everything each call returns is folded into a digest.
 *
 * The builds define SVF_FUZZ_POISON (see svf_draw.c): the scaler's idle half of the scratch is poisoned while it runs.
 * -DSVF_TEST_RD8 (make fuzz-rd) maps the first copy as an alias that only svf_test_rd8 can read (SVF_RD8 overridden).
 *
 * Checks beyond the sanitizers (each is an abort(), so libFuzzer saves the input):
 * - the read callback is never asked for a byte at or past the file end (svf.h promises it);
 * - the uncached and the cached stream agree on every open result and digest; when the mapped open succeeded (it has
 *   validated every record) both streams open and all three digests are equal: same cells, error codes, metrics, lines;
 *   when it failed with anything but SVF_E_RANGE (a record is checked only when a stream reads it) the stream's result
 *   is the same error;
 * - with and without the chain's syllable cache a line has the same pixels.
 */
#include "svf.h"
#if SVF_JSET_TRUSTED
#error "fuzz builds validate every JSET"
#endif
#ifdef SVF_TEST_RD8
#include "test_rd8.h" /* make fuzz-rd: SVF_RD8 overridden; the mapped copy is an alias of 0x5A bytes, read only through svf_test_rd8 */
#endif

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DIE(...) (fprintf(stderr, "fuzz_open: " __VA_ARGS__), fputc('\n', stderr), abort())

/* ---- digest ---------------------------------------------------------------------------------------------------- */

static void hb(uint64_t *h, const void *p, size_t n)
{
	const uint8_t *b = p;
	size_t i;

	for (i = 0; i < n; ++i)
		*h = (*h ^ b[i]) * 0x100000001B3ull;
}

static void hu(uint64_t *h, uint32_t v)
{
	hb(h, &v, 4);
}

/* ---- the stream's source -------------------------------------------------------------------------------------- */

#ifndef SVF_NO_STREAM
typedef struct {
	const uint8_t *data;
	size_t len;
} source;

static long read_cb(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	const source *s = ctx;

	if (offset >= s->len || len > s->len - offset)
		DIE("read of %u bytes at %u, file is %zu bytes", (unsigned)len, (unsigned)offset, s->len);
	memcpy(dst, s->data + offset, len);
	return (long)len;
}
#endif

/* ---- what is drawn --------------------------------------------------------------------------------------------- */

static size_t put_utf8(char *o, uint32_t cp)
{
	if (cp < 0x80) {
		o[0] = (char)cp;
		return 1;
	}
	if (cp < 0x800) {
		o[0] = (char)(0xC0 | cp >> 6), o[1] = (char)(0x80 | (cp & 0x3F));
		return 2;
	}
	if (cp < 0x10000) {
		o[0] = (char)(0xE0 | cp >> 12), o[1] = (char)(0x80 | (cp >> 6 & 0x3F)), o[2] = (char)(0x80 | (cp & 0x3F));
		return 3;
	}
	o[0] = (char)(0xF0 | cp >> 18), o[1] = (char)(0x80 | (cp >> 12 & 0x3F)), o[2] = (char)(0x80 | (cp >> 6 & 0x3F)),
	o[3] = (char)(0x80 | (cp & 0x3F));
	return 4;
}

static uint32_t xs(uint32_t *s)
{
	*s ^= *s << 13, *s ^= *s >> 17, *s ^= *s << 5;
	return *s;
}

/* The syllable of lead l, vowel v, tail t. */
static uint32_t syl(unsigned l, unsigned v, unsigned t)
{
	return 0xAC00u + (l * 21 + v) * 28 + t;
}

/* The line: Latin, hash-picked syllables, compat jamo, a mark, U+FFFD, invalid UTF-8. */
static size_t build_text(char *o, uint32_t seed)
{
	static const char tail[] = "e\xCC\x81 a\xCC\x80" "\xEF\xBF\xBD" "\xFF\xC0\xE0\x80" "g\xED\xA0\x80y";
	static const uint32_t jamo[] = {0x3131, 0x314F, 0x3162, 0x314E, 0x3163, 0x3134, 0x3150};
	size_t n = 0, i;
	uint32_t s = seed | 1;

	memcpy(o, "Hello, wgjy 0.5 ", 16), n = 16;
	for (i = 0; i < 12; ++i)
		n += put_utf8(o + n, syl(xs(&s) % 19, xs(&s) % 21, xs(&s) % 28));
	for (i = 0; i < sizeof jamo / sizeof jamo[0]; ++i)
		n += put_utf8(o + n, jamo[i]);
	memcpy(o + n, tail, sizeof tail - 1);
	return n + sizeof tail - 1;
}

/* ---- targets --------------------------------------------------------------------------------------------------- */

#define TW 48
#define TH 24

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	uint64_t *h = ctx;

	hu(h, (uint32_t)(uint16_t)x | (uint32_t)(uint16_t)y << 16);
	hb(h, &cov, 1);
}

static void target_shape(svf_target_kind k, size_t *stride, size_t *rows)
{
	*rows = TH;
	switch (k) {
	case SVF_T_MONO_PAGE:
		*stride = TW, *rows = (TH + 7) / 8;
		break;
	case SVF_T_MONO_ROW:
		*stride = (TW + 7) / 8;
		break;
	case SVF_T_RGB565:
	case SVF_T_RGB555:
		*stride = 2 * TW;
		break;
	case SVF_T_XRGB8888:
		*stride = 4 * TW;
		break;
	case SVF_T_RGB888:
		*stride = 3 * TW;
		break;
	default:
		*stride = TW;
	}
}

/* Draws the line on every target kind the build has, at three scales; folds the pixels into @p h. */
static void draw_lines(const svf_face *f, uint32_t seed, int cache, uint64_t *h)
{
	static const uint8_t num[3] = {1, 3, 2}, den[3] = {1, 2, 1};
	svf_face *faces[1];
	svf_chain ch;
	char text[256];
	size_t tn = build_text(text, seed);
	uint8_t *cbuf = NULL;
	int k, j;

	faces[0] = (svf_face *)f;
	for (k = 0; k <= (int)SVF_T_GRAY; ++k) {
		for (j = 0; j < 3; ++j) {
			size_t stride, rows, need;
			uint8_t *buf = NULL, *scratch;
			svf_target t;
			svf_extent e;
			uint64_t cbh = 14695981039346656037ull;
			svf_err er, ed;
			uint32_t r = seed * 2654435761u + (uint32_t)(k * 3 + j);

			target_shape((svf_target_kind)k, &stride, &rows);
			if (k != (int)SVF_T_COVERAGE_CB) {
				buf = calloc(rows * stride, 1);
				if (!buf)
					return;
			}
			if (svf_target_init(&t, (svf_target_kind)k, buf, rows * stride, TW, TH, (uint16_t)stride) != SVF_OK) {
				free(buf);
				continue;
			}
			t.fg565 = (uint16_t)(r >> 3 | 0x0801), t.bg565 = (uint16_t)(r >> 11), t.mono_threshold = (uint8_t)(r >> 5);
			t.fg888 = r & 0xFFFFFF, t.bg888 = r >> 8;
			t.flags = (uint8_t)(r >> 29 & 1);
			if (k == (int)SVF_T_GRAY) { /* 1, 2, 4 or 8 bits, either bit order */
				t.gray_bits = (uint8_t)(1u << (r >> 7 & 3));
				t.flags = (uint8_t)((r >> 29 & 1) << 1); /* SVF_TF_GRAY_LSB_FIRST */
			}
			if (k == (int)SVF_T_COVERAGE_CB)
				t.plot = plot, t.ctx = &cbh;
			if (r & 0x100) { /* a clip that cuts the cells, sometimes out of the target */
				t.clip_x0 = (int16_t)(r % 7 - 2), t.clip_y0 = (int16_t)(r % 5 - 1);
				t.clip_x1 = (int16_t)(TW - 3 - (int)(r % 9)), t.clip_y1 = (int16_t)(TH - 2 - (int)(r % 4));
			}
			memset(&ch, 0, sizeof ch);
			ch.faces = faces, ch.count = 1, ch.missing_advance = (uint8_t)(r & 7);
			ch.scale_num = num[j], ch.scale_den = den[j];
			if (cache) {
				size_t cl = 4 * (8 + svf_cell_bytes(f));
				cbuf = malloc(cl);
				if (!cbuf || svf_chain_cache(&ch, cbuf, cl) != SVF_OK)
					DIE("chain cache");
			}
			need = svf_chain_scratch_bytes(&ch);
			scratch = malloc(need ? need : 1);
			if (!scratch)
				DIE("out of memory");
			er = svf_measure_utf8(&ch, text, tn, &e);
			hu(h, (uint32_t)er);
			hu(h, (uint32_t)(uint16_t)e.width | (uint32_t)(uint16_t)e.ascent << 16), hu(h, (uint32_t)(uint16_t)e.descent);
			ed = svf_draw_utf8(&ch, text, tn, (int16_t)(r % 13 - 6), (int16_t)(svf_ascent(f) * num[j] / den[j] + r % 5 - 2), &t,
			                   scratch, need);
			hu(h, (uint32_t)ed);
			if (buf)
				hb(h, buf, rows * stride);
			else
				hb(h, &cbh, 8);
			free(scratch);
			free(cbuf), cbuf = NULL;
			free(buf);
		}
	}
}

/* ---- one face -------------------------------------------------------------------------------------------------- */

static int composed(const svf_face *f, uint32_t cp)
{
	uint16_t p[3];

	/* svf_jamo_pieces answers 0 for a jamo-less face and (SVF_JMAP) for a syllable a JMAP alone does not list */
	return svf_jamo_pieces(f, cp, p) > 0;
}

/* fuzz-open-nojmap only: when set, the digest leaves out everything composition can change (the syllables, the compat
 * jamo, is_jamo, the drawn lines): a mapped face composing through a fallback against a plain streamed face. */
static int skip_jamo;

static void one_cp(const svf_face *f, int uncached_stream, uint32_t cp, uint64_t *h)
{
	size_t sz = svf_cell_bytes(f), len = (uncached_stream && composed(f, cp)) ? 2 * sz : sz;
	uint8_t *cell;
	svf_metrics m;
	svf_err e;
	int mr;

	if (skip_jamo && ((cp >= 0x3131 && cp <= 0x3163) || (cp >= 0xAC00 && cp <= 0xD7A3)))
		return;
	cell = calloc(len ? len : 1, 1);
	if (!cell)
		return;
	e = svf_glyph(f, cp, cell, len);
	hu(h, cp), hu(h, (uint32_t)e);
	if (e == SVF_OK)
		hb(h, cell, sz);
	free(cell);
	hu(h, (uint32_t)svf_has(f, cp));
	memset(&m, 0, sizeof m);
	mr = svf_metrics_of(f, cp, &m);
	hu(h, (uint32_t)mr);
	if (mr >= 0)
		hb(h, &m, sizeof m);
}

#if !SVF_JMAP
#include "../src/svf_internal.h" /* SVF__JSET_LOAD_MAX */
#endif
/* PR-6 (fuzz-open-nojmap only): when set, the digest leaves out the four JSET/JMAP cause bits of the status. */
static int mask_cause;

/* Everything the face does; the digest of its results. */
static uint64_t exercise(const svf_face *f, int uncached_stream, uint32_t seed)
{
	uint64_t h = 14695981039346656037ull, a, b;
	uint32_t s = seed | 1, cp;
	unsigned l, v, t, i, n = svf_glyph_count(f);

	hu(&h, svf_bpp(f)), hu(&h, svf_cell_w(f)), hu(&h, svf_cell_h(f)), hu(&h, svf_ascent(f)), hu(&h, svf_flags(f));
	{
		uint32_t st = svf_status(f);

		if (mask_cause)
			st &= ~(uint32_t)(SVF_FACE_JMAP_BAD | SVF_FACE_JMAP_UNREAD | SVF_FACE_JSET_BAD | SVF_FACE_JSET_UNREAD);
		hu(&h, st);
	}
	hu(&h, n);
	if (!skip_jamo)
		hu(&h, (uint32_t)svf_is_jamo(f));
	for (i = 0; i < n; ++i) {
		cp = svf_cmap_cp(f, (uint16_t)i);
		one_cp(f, uncached_stream, cp, &h);
	}
	for (cp = 0x3131; cp <= 0x3163; ++cp)
		one_cp(f, uncached_stream, cp, &h);
	for (l = 0; l < 19; ++l)
		for (v = 0; v < 21; ++v)
			one_cp(f, uncached_stream, syl(l, v, (seed + l * 21 + v) % 28), &h);
	for (t = 0; t < 28; ++t)
		one_cp(f, uncached_stream, syl(seed % 19, seed / 19 % 21, t), &h);
	for (i = 0; i < 64; ++i)
		one_cp(f, uncached_stream, 0xAC00u + xs(&s) % 11172u, &h);
	one_cp(f, uncached_stream, 0, &h), one_cp(f, uncached_stream, 0xD7A4, &h), one_cp(f, uncached_stream, 0x10FFFF, &h);
	one_cp(f, uncached_stream, 0xFFFFFFFFu, &h);
	if (skip_jamo)
		return h;

	a = h;
	draw_lines(f, seed, 0, &a);
	b = h;
	draw_lines(f, seed, 1, &b);
	if (a != b)
		DIE("a line differs with the syllable cache");
	return a;
}

/* ---- the stream opens ------------------------------------------------------------------------------------------ */

#ifndef SVF_NO_STREAM
typedef struct {
	svf_face f;
	source src;
	uint8_t *tables, *cache;
	svf_err err;
} stream_t;

static void stream_open(stream_t *s, const uint8_t *copy, size_t n, int cached)
{
	size_t need;
	svf_err e;

	memset(s, 0, sizeof *s);
	s->src.data = copy, s->src.len = n;
	need = svf_stream_tables_size(read_cb, &s->src, (uint32_t)n, &e);
	if (!need) {
		s->err = e == SVF_OK ? SVF_E_NOMEM : e;
		return;
	}
	s->tables = malloc(need);
	s->cache = cached ? malloc(4096) : NULL;
	if (!s->tables || (cached && !s->cache))
		DIE("out of memory");
	s->err = svf_open_stream(&s->f, read_cb, &s->src, (uint32_t)n, s->tables, need, s->cache, cached ? 4096 : 0,
	                         cached ? 64 : 0);
}

static void stream_close(stream_t *s)
{
	free(s->tables);
	free(s->cache);
}
#endif

static uint32_t seed_of(const uint8_t *d, size_t n)
{
	uint64_t h = 14695981039346656037ull;

	hb(&h, d, n);
	return (uint32_t)(h ^ h >> 32);
}

int LLVMFuzzerTestOneInput(const uint8_t *d, size_t n)
{
	uint8_t *cm, *cu, *cc, *map;
	svf_face fm;
	svf_err em;
	uint64_t dm = 0;
	uint32_t seed;

	if (n > 0xFFFFFFFFu)
		return 0;
	cm = malloc(n ? n : 1), cu = malloc(n ? n : 1), cc = malloc(n ? n : 1);
	if (!cm || !cu || !cc)
		DIE("out of memory");
	if (n)
		memcpy(cm, d, n), memcpy(cu, d, n), memcpy(cc, d, n);
	seed = seed_of(d, n);
#ifdef SVF_TEST_RD8
	map = malloc(n ? n : 1);
	if (!map)
		DIE("out of memory");
	memset(map, 0x5A, n ? n : 1);
	svf_test_rd8_map(map, cm, n);
#else
	map = cm;
#endif
	em = svf_open_mapped(&fm, map, n);
	if (em == SVF_OK)
		dm = exercise(&fm, 0, seed);
#ifndef SVF_NO_STREAM
	{
		stream_t su, sc;
		uint64_t du = 0, dc = 0;

		stream_open(&su, cu, n, 0);
		stream_open(&sc, cc, n, 1);
		if (su.err != sc.err)
			DIE("stream open: uncached %d, cached %d", (int)su.err, (int)sc.err);
		if (em == SVF_OK && su.err != SVF_OK)
			DIE("mapped opens, stream open gives %d", (int)su.err);
		if (em != SVF_OK && em != SVF_E_RANGE && su.err != em)
			DIE("mapped open gives %d, stream open %d", (int)em, (int)su.err);
		if (su.err == SVF_OK) {
			du = exercise(&su.f, 1, seed);
			dc = exercise(&sc.f, 0, seed);
			if (du != dc)
				DIE("uncached and cached stream differ");
#if !SVF_JMAP
			/* PR-6: a build without the JMAP reader reads a mapped version 3 face's fallback JSET, but a streamed region longer
			 * than SVF__JSET_LOAD_MAX is loaded to its 16-byte header only, so the streamed face stays plain with JMAP_UNREAD
			 * and the fallback's verdict (JSET_BAD / JSET_UNREAD) or the cause of a malformed block (JMAP_BAD instead of
			 * JMAP_UNREAD) is not reached. For exactly that case (streamed face JMAP_UNREAD, region over the load max): a
			 * mapped face composing through the fallback against a plain streamed one is compared without the syllables, the
			 * compat jamo, is_jamo and the lines (skip_jamo); otherwise the digests are compared without the four cause
			 * bits. Every other face is compared whole. */
			if (em == SVF_OK && (svf_status(&su.f) & SVF_FACE_JMAP_UNREAD) && su.f.jset_len > SVF__JSET_LOAD_MAX) {
				skip_jamo = svf_is_jamo(&fm) && !svf_is_jamo(&su.f);
				mask_cause = 1;
				dm = exercise(&fm, 0, seed);
				du = exercise(&su.f, 1, seed);
				mask_cause = skip_jamo = 0;
			}
#endif
			if (em == SVF_OK && dm != du)
				DIE("mapped and streamed differ");
		}
		stream_close(&su), stream_close(&sc);
	}
#endif
	(void)dm;
#ifdef SVF_TEST_RD8
	free(map);
#endif
	free(cm), free(cu), free(cc);
	return 0;
}
