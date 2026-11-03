/* svfdump - the library's view of a face, for tools/test_c_renderer.py (host only).
 *
 *   svfdump FACE glyphs   per code point table entry, in table order, little-endian: u32 code point, advance,
 *                         bearing x, ink width, dy (4 zero bytes without a metrics table), then the cell bytes
 *   svfdump FACE info     one line of key=value: bpp cell_w cell_h ascent flags glyphs metrics cmap_linear dy_ignored
 *                         jset_bad jamo, then from the file's header version, rec, row, tab (log2 units), off (16 or 32,
 *                         always 3 since v2 is not read), data_size, then jset_unread jmap_bad jmap_unread
 *   svfdump FACE syllables
 *                         the cells (svf_glyph) of U+AC00..U+D7A3 then U+3131..U+3163, a zero cell where svf_has is 0,
 *                         then one byte: svf_is_jamo
 *   svfdump FACE has U+XXXX...
 *                         per code point one line: "U+XXXX has=0", or "U+XXXX has=1 advance=A bearing=B ink=W dy=D"
 *                         (svf_metrics_of)
 *
 *   svfdump FACE cells U+XXXX...
 *                         the cells (svf_glyph) of the code points in the order given (a zero cell for one that fails)
 *   svfdump FACE reads U+XXXX...
 *                         per code point one line "U+XXXX reads=N": the read callback calls svf_glyph made (stream)
 *
 *   svfdump line W H X Y TEXT FACE...
 *                         TEXT (its bytes, as UTF-8) drawn by svf_draw_utf8 on a W x H target (GRAY8, stride W, unless
 *                         the target options say otherwise) with the pen at X on the baseline Y, over the chain of the
 *                         FACEs in order: the target buffer's bytes (buf_len of them), or for --target=cb one line
 *                         "X Y COV" a plot call, in call order
 *   svfdump measure TEXT FACE...
 *                         svf_measure_utf8 of TEXT over the chain: one line "width=W ascent=A descent=D"
 *
 * Options, before FACE (or before line / measure, applying to every face):
 *   --stream[=CACHE_KB:BLOCK]  open with svf_open_stream (no cache, or CACHE_KB KB of cache in BLOCK-byte blocks); the
 *                              tables buffer is svf_stream_tables_size bytes; prints "svfdump: open reads=N" (callback
 *                              calls so far) on stderr
 *   --face-offset=K            a mapped face's bytes start K (0..3) bytes past a 4-byte boundary (the allocation is
 *                              exactly K + the file's size, so a read outside the file is caught by AddressSanitizer)
 *   --tables-bytes=N           a tables buffer of N bytes instead; when too small: "... SVF_E_NOMEM (tables need X
 *                              bytes)"
 *   --fail-read-after=N[:error]  callback calls 0..N-1 succeed; call N fills its buffer with 0xA5 and comes back one
 *                              byte short (or returns -1 with :error); later calls succeed
 *   --trace-reads              every callback call on stderr: "svfdump: read OFFSET LEN"
 *   --missing-advance=N        line, measure: the chain's missing_advance (default 0)
 *   --scratch-delta=N          line: the scratch is svf_chain_scratch_bytes + N bytes (N may be negative; default 0)
 *   --print-scratch            line: "svfdump: scratch=N" (svf_chain_scratch_bytes) on stderr
 *   --scale=NUM/DEN            line, measure: the chain's scale_num / scale_den (default 0/0)
 *   --syllable-cache=BYTES     line: svf_chain_cache with a buffer of BYTES bytes (default 0: no cache); its error is
 *                              printed ("svfdump: cache: SVF_E_...") and exits 2
 *   --print-reads              line: "svfdump: line reads=N" on stderr after drawing, N the faces' svf_stream_reads
 *                              summed (open reads included)
 * Target options (line):
 *   --target=KIND              gray8 (default), mono-page, mono-row, rgb565, cb, indexed8, rgb555, xrgb8888, rgb888 or gray
 *                              (svf_target_kind)
 *   --stride=N                 the target's stride (default the bytes of one row of the kind; 0 for cb)
 *   --buf-delta=N              buf_len is rows * stride + N (N may be negative; default 0); cb has no buffer
 *   --fill=N                   the buffer's bytes before drawing (default 0)
 *   --clip=X0:Y0:X1:Y1         the clip rectangle, set after svf_target_init (default the whole target)
 *   --fg=N --bg=N              fg565, bg565 (default 0xFFFF, 0); --threshold=N mono_threshold (default 128)
 *   --big-endian               flags SVF_TF_RGB16_BIGENDIAN
 *   --gray-bits=N --lsb-first  gray: gray_bits (0..255, so the library's refusal is testable; default the library's 8),
 *                              flags SVF_TF_GRAY_LSB_FIRST
 *   --index-base=N --index-levels=N  indexed8: index_base, index_levels (0..255; default 0, 255)
 *   --fg888=N --bg888=N        xrgb8888, rgb888: fg888, bg888 (0..0xFFFFFFFF; default 0x00FFFFFF, 0)
 *   --misalign=K               the target buffer starts K (0..3) bytes past a 4-byte boundary (default 0)
 *   --no-plot                  cb: plot left NULL
 * The buffer has 16 bytes of 0xA5 on each side (the allocation is GUARD + K + buffer + GUARD, at most 2^28 bytes
 * of buffer: a larger target is refused with exit 1): if drawing changes one, "svfdump: guard bytes changed" and
 * exit 3.
 *   --forbid=LO:HI             file offsets [LO, HI) must never be read: a stream callback call touching them, or (the
 *                              svfdump-rd8 build) an SVF_RD8 read of a mapped face in them, exits 3 ("forbidden")
 *
 * The svfdump-rd8 build (c/Makefile) hands a mapped face to the library at an alias read only through SVF_RD8
 * (tests/test_rd8.h) and prints "svfdump: rd8 calls=N" on stderr at the end.
 *
 * A glyph that fails (svf_glyph error) is reported on stderr ("svfdump: glyph U+XXXX: SVF_E_..."), and the dump goes
 * on; the exit is then 2. Its cell is written as svf_glyph left it for SVF_E_IO (the library zeroes it), as a zero
 * cell for any other error.
 * Exit 0 on success, 2 with the error's name on stderr when the library refuses the face (SVF_E_VERSION adds "not version
 * 3; version 2 is not read since v3: convert with tools/svf2to3.py"), 1 on a usage error. A face
 * refused with SVF_E_LAYOUT names the file's units and the build's supported set:
 *   svfdump: FILE: SVF_E_LAYOUT (rec=R row=W tab=T off=O; build accepts every layout | build accepts R/W/T[,R/W/T])
 * The file is read into a buffer of exactly its size, so a read past the end is caught by AddressSanitizer; the stream
 * callback exits 3 with "read past the end" if asked for a byte past the file.
 */
#include "svf.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *err_name(svf_err e)
{
	switch (e) {
	case SVF_OK: return "SVF_OK";
	case SVF_E_MAGIC: return "SVF_E_MAGIC";
	case SVF_E_VERSION: return "SVF_E_VERSION";
	case SVF_E_BPP: return "SVF_E_BPP";
	case SVF_E_RANGE: return "SVF_E_RANGE";
	case SVF_E_NOMEM: return "SVF_E_NOMEM";
	case SVF_E_IO: return "SVF_E_IO";
	case SVF_E_ARG: return "SVF_E_ARG";
	case SVF_E_LAYOUT: return "SVF_E_LAYOUT";
	}
	return "SVF_E_?";
}

static int fail(const char *what, svf_err e)
{
	fprintf(stderr, "svfdump: %s: %s%s\n", what, err_name(e),
	        e == SVF_E_VERSION ? " (not version 3; version 2 is not read since v3: convert with tools/svf2to3.py)" : "");
	return 2;
}

/* A face refused with SVF_E_LAYOUT: the file's units (header bytes 9 and 10) and what the build reads. */
static int fail_layout(const char *what, const uint8_t *data, size_t len)
{
	const uint16_t *set;
	size_t n = svf_layouts(&set), i;

	if (len < 11) {
		fprintf(stderr, "svfdump: %s: SVF_E_LAYOUT\n", what);
		return 2;
	}
	fprintf(stderr, "svfdump: %s: SVF_E_LAYOUT (rec=%u row=%u tab=%u off=%u; build accepts ", what, data[9] & 7u,
	        data[9] >> 3 & 7u, data[10] & 7u, data[10] & 8 ? 32u : 16u);
	if (!n)
		fprintf(stderr, "every layout)\n");
	else {
		for (i = 0; i < n; ++i)
			fprintf(stderr, "%s%u/%u/%u", i ? "," : "", set[i] & 7u, set[i] >> 3 & 7u, set[i] >> 8 & 7u);
		fprintf(stderr, ")\n");
	}
	return 2;
}

static uint8_t *read_file(const char *path, size_t *len)
{
	FILE *fp = fopen(path, "rb");
	uint8_t *buf;
	long n;

	if (!fp)
		return NULL;
	if (fseek(fp, 0, SEEK_END) != 0 || (n = ftell(fp)) < 0 || fseek(fp, 0, SEEK_SET) != 0) {
		fclose(fp);
		return NULL;
	}
	buf = malloc(n ? (size_t)n : 1);
	if (buf && n && fread(buf, 1, (size_t)n, fp) != (size_t)n) {
		free(buf);
		buf = NULL;
	}
	fclose(fp);
	*len = (size_t)n;
	return buf;
}

static void put32(uint32_t v)
{
	uint8_t b[4];
	b[0] = (uint8_t)v;
	b[1] = (uint8_t)(v >> 8);
	b[2] = (uint8_t)(v >> 16);
	b[3] = (uint8_t)(v >> 24);
	fwrite(b, 1, 4, stdout);
}

/* Reports a glyph svf_glyph refused and zeroes its cell unless the error is SVF_E_IO (the library's zero cell is kept,
 * so the tests see it); returns the exit code (2). */
static int glyph_failed(uint32_t cp, svf_err e, uint8_t *cell, size_t n)
{
	fprintf(stderr, "svfdump: glyph U+%04lX: %s\n", (unsigned long)cp, err_name(e));
	if (e != SVF_E_IO)
		memset(cell, 0, n);
	return 2;
}

/* A streamed face without a cache composes in twice the cell (svf.h); the dump allocates that for every face. */
static int dump_glyphs(const svf_face *f)
{
	size_t n = svf_cell_bytes(f), cell_len = 2 * n;
	uint8_t *cell = malloc(cell_len);
	uint16_t i;
	int rc = 0;

	if (!cell)
		return fail("cell", SVF_E_NOMEM);
	for (i = 0; i < svf_glyph_count(f); ++i) {
		uint32_t cp = svf_cmap_cp(f, i);
		svf_metrics m;
		uint8_t mb[4] = {0, 0, 0, 0};
		svf_err e;

		if (svf_metrics_of(f, cp, &m) > 0) {
			mb[0] = m.advance;
			mb[1] = (uint8_t)m.bearing_x;
			mb[2] = m.ink_w;
			mb[3] = (uint8_t)m.dy;
		}
		e = svf_glyph(f, cp, cell, cell_len);
		if (e != SVF_OK)
			rc = glyph_failed(cp, e, cell, n);
		put32(cp);
		fwrite(mb, 1, 4, stdout);
		fwrite(cell, 1, n, stdout);
	}
	free(cell);
	return rc;
}

/* @p data: the file's bytes (an opened face has at least its header). */
static void dump_info(const svf_face *f, const uint8_t *data)
{
	uint16_t st = svf_status(f);
	unsigned version = data[4] | data[5] << 8;
	uint32_t data_size = (uint32_t)data[28] | (uint32_t)data[29] << 8 | (uint32_t)data[30] << 16 | (uint32_t)data[31] << 24;

	printf("bpp=%u cell_w=%u cell_h=%u ascent=%u flags=%u glyphs=%u metrics=%d cmap_linear=%d dy_ignored=%d "
	       "jset_bad=%d jamo=%d version=%u rec=%u row=%u tab=%u off=%u data_size=%lu jset_unread=%d jmap_bad=%d "
	       "jmap_unread=%d\n",
	       svf_bpp(f), svf_cell_w(f), svf_cell_h(f), svf_ascent(f), svf_flags(f), svf_glyph_count(f),
	       (svf_flags(f) & SVF_FLAG_METRICS) && !(st & SVF_FACE_METRICS_DROPPED), !!(st & SVF_FACE_CMAP_LINEAR),
	       !!(st & SVF_FACE_DY_IGNORED), !!(st & SVF_FACE_JSET_BAD), svf_is_jamo(f), version,
	       version == 3 ? data[9] & 7u : 0u, version == 3 ? data[9] >> 3 & 7u : 0u, version == 3 ? data[10] & 7u : 0u,
	       version == 3 ? (data[10] & 8 ? 32u : 16u) : 0u, (unsigned long)data_size, !!(st & SVF_FACE_JSET_UNREAD),
	       !!(st & SVF_FACE_JMAP_BAD), !!(st & SVF_FACE_JMAP_UNREAD));
}

static int dump_range(const svf_face *f, uint8_t *cell, size_t n, uint32_t lo, uint32_t hi)
{
	uint32_t cp;
	int rc = 0;

	for (cp = lo; cp <= hi; ++cp) {
		memset(cell, 0, n);
		if (svf_has(f, cp)) {
			svf_err e = svf_glyph(f, cp, cell, 2 * n);
			if (e != SVF_OK)
				rc = glyph_failed(cp, e, cell, n);
		}
		fwrite(cell, 1, n, stdout);
	}
	return rc;
}

static int dump_syllables(const svf_face *f)
{
	size_t n = svf_cell_bytes(f);
	uint8_t *cell = malloc(2 * n);
	int rc;

	if (!cell)
		return fail("cell", SVF_E_NOMEM);
	rc = dump_range(f, cell, n, 0xAC00, 0xD7A3);
	rc |= dump_range(f, cell, n, 0x3131, 0x3163);
	free(cell);
	putchar(svf_is_jamo(f) ? 1 : 0);
	return rc;
}

/* A numeric option value: decimal, 0x hex or 0 octal digits only (no blank, '+' or '-', which strtoul would take, '-'
 * wrapping), nothing after them, no overflow, at most @p max. Returns 1 and stores it, or 0. */
static int parse_num(const char *s, unsigned long max, unsigned long *out)
{
	char *end;
	unsigned long v;

	if (!isdigit((unsigned char)*s))
		return 0;
	errno = 0;
	v = strtoul(s, &end, 0);
	if (*end || errno || v > max)
		return 0;
	*out = v;
	return 1;
}

/* Parses "U+XXXX" into @p cp; 0 (with a message) if it is not one. */
static int parse_cp(const char *arg, unsigned long *cp)
{
	char *end;

	if (strncmp(arg, "U+", 2) != 0 || !(*cp = strtoul(arg + 2, &end, 16), *end == '\0')) {
		fprintf(stderr, "svfdump: not a code point: %s\n", arg);
		return 0;
	}
	return 1;
}

static int dump_cells(const svf_face *f, int argc, char **argv)
{
	size_t n = svf_cell_bytes(f);
	uint8_t *cell = malloc(2 * n);
	int i, rc = 0;

	if (!cell)
		return fail("cell", SVF_E_NOMEM);
	for (i = 0; i < argc; ++i) {
		unsigned long cp;
		svf_err e;

		if (!parse_cp(argv[i], &cp)) {
			rc = 1;
			break;
		}
		e = svf_glyph(f, (uint32_t)cp, cell, 2 * n);
		if (e != SVF_OK)
			rc = glyph_failed((uint32_t)cp, e, cell, n);
		fwrite(cell, 1, n, stdout);
	}
	free(cell);
	return rc;
}

static int dump_reads(const svf_face *f, int argc, char **argv)
{
	size_t n = svf_cell_bytes(f);
	uint8_t *cell = malloc(2 * n);
	int i, rc = 0;

	if (!cell)
		return fail("cell", SVF_E_NOMEM);
	for (i = 0; i < argc && !rc; ++i) {
		unsigned long cp;
		uint32_t before = svf_stream_reads(f);
		svf_err e;

		if (!parse_cp(argv[i], &cp)) {
			rc = 1;
			break;
		}
		e = svf_glyph(f, (uint32_t)cp, cell, 2 * n);
		if (e != SVF_OK)
			rc = glyph_failed((uint32_t)cp, e, cell, n);
		printf("U+%04lX reads=%lu\n", cp, (unsigned long)(svf_stream_reads(f) - before));
	}
	free(cell);
	return rc;
}

static int dump_has(const svf_face *f, int argc, char **argv)
{
	int i;

	for (i = 0; i < argc; ++i) {
		unsigned long cp;
		svf_metrics m;

		if (!parse_cp(argv[i], &cp))
			return 1;
		if (!svf_has(f, (uint32_t)cp)) {
			printf("U+%04lX has=0\n", cp);
			continue;
		}
		if (svf_metrics_of(f, (uint32_t)cp, &m) < 0) {
			fprintf(stderr, "svfdump: U+%04lX: svf_has without metrics\n", cp);
			return 2;
		}
		printf("U+%04lX has=1 advance=%u bearing=%d ink=%u dy=%d\n", cp, m.advance, m.bearing_x, m.ink_w, m.dy);
	}
	return 0;
}

/* The stream callback over the file in memory: bounds-checked, counted, traced, and failing on request. */
typedef struct {
	const uint8_t *data;
	size_t len;
	unsigned long calls;
	long fail_at; /* the call that fails, or -1 */
	int fail_error;
	int trace;
	uint32_t forbid_lo, forbid_hi; /* offsets never to be read (empty when equal) */
} source;

static long read_cb(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	source *s = ctx;
	unsigned long call = s->calls++;

	if (s->trace)
		fprintf(stderr, "svfdump: read %lu %lu\n", (unsigned long)offset, (unsigned long)len);
	if (offset > s->len || len > s->len - offset) {
		fprintf(stderr, "svfdump: read past the end: %lu + %lu > %lu\n", (unsigned long)offset, (unsigned long)len,
		        (unsigned long)s->len);
		exit(3);
	}
	if (len && offset < s->forbid_hi && offset + len > s->forbid_lo) {
		fprintf(stderr, "svfdump: forbidden read: %lu + %lu\n", (unsigned long)offset, (unsigned long)len);
		exit(3);
	}
	if (s->fail_at >= 0 && call == (unsigned long)s->fail_at) {
		memset(dst, 0xA5, len);
		return s->fail_error ? -1 : (long)len - 1;
	}
	memcpy(dst, s->data + offset, len);
	return (long)len;
}

static int usage(void)
{
	fprintf(stderr, "usage: svfdump [--stream[=CACHE_KB:BLOCK]] [--face-offset=K] [--tables-bytes=N] [--fail-read-after=N[:error]] "
	                "[--trace-reads] [--forbid=LO:HI] FACE glyphs|info|syllables|has|cells|reads [U+XXXX...]\n"
	                "       svfdump [face options] [--missing-advance=N] [--scratch-delta=N] [--print-scratch] "
	                "[--scale=NUM/DEN] [--syllable-cache=BYTES] [--print-reads] [target options] "
	                "line W H X Y TEXT FACE...\n"
	                "       svfdump [face options] [--missing-advance=N] [--scale=NUM/DEN] measure TEXT FACE...\n");
	return 1;
}

/* Options of the command line. */
typedef struct {
	int stream;
	size_t cache_len;
	unsigned long block;
	long tables_bytes; /* -1: svf_stream_tables_size */
	long face_offset;  /* --face-offset */
	long fail_at;
	int fail_error, trace;
	uint32_t forbid_lo, forbid_hi;
	long missing_advance;
	long scratch_delta;
	int print_scratch;             /* --print-scratch */
	long scale_num, scale_den;     /* --scale */
	svf_target_kind kind;          /* --target (default gray8) */
	long stride;                   /* --stride (-1: the row bytes of the kind) */
	long buf_delta;                /* --buf-delta */
	long clip[4];                  /* --clip */
	int clip_set;
	long fg, bg, threshold, tflags; /* --fg, --bg, --threshold, --big-endian */
	long index_base, index_levels; /* --index-base, --index-levels */
	long gray_bits;                /* --gray-bits (-1: not given, the library's 8) */
	unsigned long fg888, bg888;    /* --fg888, --bg888 */
	long misalign;                 /* --misalign */
	int fill;                      /* --fill */
	int no_plot;                   /* --no-plot */
	long cache_bytes;              /* --syllable-cache */
	int print_reads;               /* --print-reads */
} options;

/* A face opened from a file with its buffers and stream source. */
typedef struct {
	svf_face face;
	uint8_t *data, *tables, *cache, *alias, *raw; /* raw: the allocation @p data lies in, when --face-offset moved it */
	size_t len;
	source src;
} loaded;

static void unload(loaded *l)
{
	free(l->tables);
	free(l->cache);
	free(l->alias);
	free(l->raw ? l->raw : l->data);
	memset(l, 0, sizeof *l);
}

/* Opens @p path as the options say; on an error prints it and returns the exit code (2, or 1), else 0. */
static int load(loaded *l, const char *path, const options *o)
{
	size_t len = 0, tables_len = 0;
	svf_err e;

	memset(l, 0, sizeof *l);
	l->src.fail_at = o->fail_at;
	l->src.fail_error = o->fail_error;
	l->src.trace = o->trace;
	l->src.forbid_lo = o->forbid_lo;
	l->src.forbid_hi = o->forbid_hi;
	l->data = read_file(path, &len);
	if (!l->data)
		return fail(path, SVF_E_IO);
	if (o->face_offset) {
		/* The file's bytes K past the start of an allocation of exactly K + len bytes (malloc'd, so 4-aligned). */
		uint8_t *moved = malloc(len + (size_t)o->face_offset);
		if (!moved) {
			unload(l);
			return fail("face", SVF_E_NOMEM);
		}
		memcpy(moved + o->face_offset, l->data, len);
		free(l->data);
		l->raw = moved;
		l->data = moved + o->face_offset;
	}
	l->len = len;
	if (o->stream) {
		size_t need;
		l->src.data = l->data;
		l->src.len = len;
		need = svf_stream_tables_size(read_cb, &l->src, (uint32_t)len, &e);
		if (e == SVF_OK) {
			tables_len = o->tables_bytes >= 0 ? (size_t)o->tables_bytes : need;
			l->tables = malloc(tables_len ? tables_len : 1);
			l->cache = o->cache_len ? malloc(o->cache_len) : NULL;
			if (!l->tables || (o->cache_len && !l->cache))
				e = SVF_E_NOMEM;
			else
				e = svf_open_stream(&l->face, read_cb, &l->src, (uint32_t)len, l->tables, tables_len, l->cache,
				                    o->cache_len, (uint16_t)(o->block > 0xFFFF ? 0 : o->block));
		}
		fprintf(stderr, "svfdump: open reads=%lu\n", l->src.calls);
		if (e == SVF_E_NOMEM && tables_len < need)
			fprintf(stderr, "svfdump: %s: %s (tables need %lu bytes)\n", path, err_name(e), (unsigned long)need);
	} else {
#ifdef SVF_TEST_RD8
		/* A separate address space: the library gets an alias of 0x5A bytes, read only through svf_test_rd8. */
		l->alias = malloc(len ? len : 1);
		if (!l->alias) {
			unload(l);
			return fail("alias", SVF_E_NOMEM);
		}
		memset(l->alias, 0x5A, len ? len : 1);
		svf_test_rd8_map(l->alias, l->data, len);
		svf_test_rd8_forbid(o->forbid_lo, o->forbid_hi);
		e = svf_open_mapped(&l->face, l->alias, len);
#else
		if (o->forbid_lo != o->forbid_hi) {
			fprintf(stderr, "svfdump: --forbid needs --stream or the svfdump-rd8 build\n");
			unload(l);
			return 1;
		}
		e = svf_open_mapped(&l->face, l->data, len);
#endif
	}
	if (e != SVF_OK) {
		int rc = e == SVF_E_LAYOUT ? fail_layout(path, l->data, len) : fail(path, e);
		unload(l);
		return rc;
	}
	return 0;
}

#define BUF_MAX (1L << 28) /* the largest target buffer svfdump allocates */
#define GUARD 16 /* bytes of 0xA5 before and after the target buffer, checked after drawing */

static const char *const kind_names[] = {"gray8",    "mono-page", "mono-row", "rgb565",  "cb",
                                        "indexed8", "rgb555",    "xrgb8888", "rgb888", "gray"};

/* The plot callback of --target=cb: one line "X Y COV" a call. */
static void plot_cb(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	(void)ctx;
	printf("%d %d %u\n", x, y, cov);
}

/* svfdump line: the target of the options (buffer of rows * stride + buf_delta bytes filled with the fill byte, the
 * GUARD bytes around it), the line drawn on it; writes the buffer (or the plot lines). Returns the exit code. */
static int draw_line(svf_chain *chain, const char *text, size_t text_len, const long *place, const options *o)
{
	long w = place[0], h = place[1], stride;
	long long row = 0, rows = 0, total;
	long need = (long)svf_chain_scratch_bytes(chain) + o->scratch_delta;
	long blen;
	uint8_t *mem, *buf, *scratch;
	svf_target t;
	svf_err e;
	int rc = 0, k;

	if (o->print_scratch)
		fprintf(stderr, "svfdump: scratch=%lu\n", (unsigned long)svf_chain_scratch_bytes(chain));
	if (w > 0 && h > 0) {
		switch (o->kind) {
		case SVF_T_GRAY8: row = w; rows = h; break;
		case SVF_T_MONO_PAGE: row = w; rows = (h + 7) / 8; break;
		case SVF_T_MONO_ROW: row = (w + 7) / 8; rows = h; break;
		case SVF_T_RGB565: row = 2 * w; rows = h; break;
		case SVF_T_INDEXED8: row = w; rows = h; break;
		case SVF_T_RGB555: row = 2 * w; rows = h; break;
		case SVF_T_XRGB8888: row = 4 * w; rows = h; break;
		case SVF_T_RGB888: row = 3 * w; rows = h; break;
		case SVF_T_GRAY: {
			/* the bits given (8 if absent; 1 if not 1/2/4/8, so the draw-time refusal is what the test sees) */
			long bits = o->gray_bits < 0 ? 8 : (o->gray_bits == 2 || o->gray_bits == 4 || o->gray_bits == 8) ? o->gray_bits : 1;
			row = (w * bits + 7) / 8;
			rows = h;
			break;
		}
		default: break;
		}
	}
	/* row <= 4 * 32767, rows <= 32767, stride <= 0xFFFF, so rows * stride < 2^31; buf_delta is within +-(2^31 - 1)
	 * (checked at parsing): the sum is long long and cannot overflow. */
	stride = o->stride >= 0 ? o->stride : (row > 0xFFFF ? 0xFFFF : (long)row);
	total = o->kind == SVF_T_COVERAGE_CB ? 0 : rows * stride + o->buf_delta;
	if (total < 0)
		total = 0;
	if (total > BUF_MAX) {
		fprintf(stderr, "svfdump: target too large (%lld bytes, limit %ld)\n", total, (long)BUF_MAX);
		return 1;
	}
	blen = (long)total;
	mem = malloc((size_t)blen + 2 * GUARD + (size_t)o->misalign);
	scratch = malloc(need > 0 ? (size_t)need : 1);
	if (!mem || !scratch) {
		free(mem);
		free(scratch);
		return fail("line", SVF_E_NOMEM);
	}
	buf = mem + GUARD + o->misalign;
	memset(mem, 0xA5, (size_t)blen + 2 * GUARD + (size_t)o->misalign);
	memset(buf, o->fill, (size_t)blen);
	e = svf_target_init(&t, o->kind, o->kind == SVF_T_COVERAGE_CB ? NULL : buf, (size_t)blen, (int16_t)w,
	                    (int16_t)h, (uint16_t)stride);
	if (e == SVF_OK) {
		if (o->clip_set) {
			t.clip_x0 = (int16_t)o->clip[0];
			t.clip_y0 = (int16_t)o->clip[1];
			t.clip_x1 = (int16_t)o->clip[2];
			t.clip_y1 = (int16_t)o->clip[3];
		}
		t.fg565 = (uint16_t)o->fg;
		t.bg565 = (uint16_t)o->bg;
		t.mono_threshold = (uint8_t)o->threshold;
		t.flags = (uint8_t)o->tflags;
		t.fg888 = (uint32_t)o->fg888;
		t.bg888 = (uint32_t)o->bg888;
		t.index_base = (uint8_t)o->index_base;
		t.index_levels = (uint8_t)o->index_levels;
		if (o->gray_bits >= 0)
			t.gray_bits = (uint8_t)o->gray_bits;
		t.plot = o->no_plot ? NULL : plot_cb;
		e = svf_draw_utf8(chain, text, text_len, (int16_t)place[2], (int16_t)place[3], &t, scratch,
		                  need > 0 ? (size_t)need : 0);
	}
	if (e != SVF_OK)
		rc = fail("line", e);
	for (k = 0; k < GUARD + o->misalign; ++k)
		if (mem[k] != 0xA5) {
			fprintf(stderr, "svfdump: guard bytes changed\n");
			rc = 3;
			break;
		}
	for (k = 0; k < GUARD; ++k)
		if (buf[blen + k] != 0xA5) {
			fprintf(stderr, "svfdump: guard bytes changed\n");
			rc = 3;
			break;
		}
	fwrite(buf, 1, (size_t)blen, stdout);
	free(mem);
	free(scratch);
	return rc;
}

/* svfdump line W H X Y TEXT FACE... / measure TEXT FACE...: the GRAY8 buffer of the line (W*H bytes) on stdout, or
 * "width=W ascent=A descent=D". TEXT's bytes are copied to a buffer of exactly their length (no NUL), so a read past
 * it is caught by AddressSanitizer. The scratch is svf_chain_scratch_bytes plus --scratch-delta bytes, allocated
 * exactly. An svf_draw_utf8 error is printed ("svfdump: line: SVF_E_...") and the buffer still written; exit 2. */
static int line_cmd(int argc, char **argv, const options *o)
{
	int is_line = strcmp(argv[0], "line") == 0, nplace = is_line ? 4 : 0, nfaces, i, rc = 0;
	long place[4];
	loaded *faces;
	svf_face **ptrs;
	svf_chain chain;
	const char *text;
	size_t text_len;
	char *tbuf;

	if (argc < 3 + nplace)
		return usage();
	for (i = 0; i < nplace; ++i) {
		char *end;
		place[i] = strtol(argv[1 + i], &end, 10);
		if (*end || place[i] < -32768 || place[i] > 32767)
			return usage();
	}
	text = argv[1 + nplace];
	nfaces = argc - 2 - nplace;
	if (nfaces > 255)
		return usage();
#ifdef SVF_TEST_RD8
	if (!o->stream && nfaces > 1) {
		fprintf(stderr, "svfdump: the rd8 build maps one face: line and measure take one face without --stream\n");
		return 1;
	}
#endif
	text_len = strlen(text);
	tbuf = malloc(text_len ? text_len : 1);
	faces = calloc((size_t)nfaces, sizeof *faces);
	ptrs = calloc((size_t)nfaces, sizeof *ptrs);
	if (!tbuf || !faces || !ptrs) {
		free(tbuf);
		free(faces);
		free(ptrs);
		return fail("line", SVF_E_NOMEM);
	}
	memcpy(tbuf, text, text_len);
	memset(&chain, 0, sizeof chain);
	for (i = 0; i < nfaces && !rc; ++i) {
		rc = load(&faces[i], argv[2 + nplace + i], o);
		ptrs[i] = &faces[i].face;
	}
	chain.faces = ptrs;
	chain.count = (uint8_t)nfaces;
	chain.is_mark = NULL;
	chain.missing_advance = (uint8_t)o->missing_advance;
	chain.scale_num = (uint8_t)o->scale_num;
	chain.scale_den = (uint8_t)o->scale_den;
	if (!rc && !is_line) {
		svf_extent ext;
		svf_err e = svf_measure_utf8(&chain, tbuf, text_len, &ext);
		if (e != SVF_OK)
			rc = fail("measure", e);
		else
			printf("width=%d ascent=%d descent=%d\n", ext.width, ext.ascent, ext.descent);
	} else if (!rc) {
		uint8_t *cache = malloc(o->cache_bytes > 0 ? (size_t)o->cache_bytes : 1);
		svf_err e = cache ? svf_chain_cache(&chain, o->cache_bytes > 0 ? cache : NULL, (size_t)o->cache_bytes)
		                  : SVF_E_NOMEM;
		if (e != SVF_OK) {
			rc = fail("cache", e);
		} else {
			rc = draw_line(&chain, tbuf, text_len, place, o);
			if (o->print_reads) {
				unsigned long reads = 0;
				for (i = 0; i < nfaces; ++i)
					reads += svf_stream_reads(ptrs[i]);
				fprintf(stderr, "svfdump: line reads=%lu\n", reads);
			}
		}
		free(cache);
	}
	for (i = 0; i < nfaces; ++i)
		unload(&faces[i]);
	free(faces);
	free(ptrs);
	free(tbuf);
	return rc;
}

int main(int argc, char **argv)
{
	options o;
	loaded l;
	int rc, a = 1;
	const char *cmd;

	memset(&o, 0, sizeof o);
	o.tables_bytes = -1;
	o.fail_at = -1;
	o.stride = -1;
	o.fg = 0xFFFF;
	o.threshold = 128;
	o.index_levels = 255;
	o.gray_bits = -1;
	o.fg888 = 0x00FFFFFFul;
	for (; a < argc && strncmp(argv[a], "--", 2) == 0; ++a) {
		char *end;
		const char *eq = strchr(argv[a], '=');
		if (eq && !eq[1]) /* every option that takes a value refuses an empty one */
			return usage();
		if (strcmp(argv[a], "--stream") == 0) {
			o.stream = 1;
		} else if (strncmp(argv[a], "--stream=", 9) == 0) {
			o.stream = 1;
			o.cache_len = strtoul(argv[a] + 9, &end, 10) * 1024;
			if (*end != ':')
				return usage();
			o.block = strtoul(end + 1, &end, 10);
			if (*end)
				return usage();
		} else if (strncmp(argv[a], "--face-offset=", 14) == 0) {
			o.face_offset = strtol(argv[a] + 14, &end, 10);
			if (end == argv[a] + 14 || *end || o.face_offset < 0 || o.face_offset > 3)
				return usage();
		} else if (strncmp(argv[a], "--tables-bytes=", 15) == 0) {
			o.tables_bytes = strtol(argv[a] + 15, &end, 10);
			if (*end || o.tables_bytes < 0)
				return usage();
		} else if (strncmp(argv[a], "--fail-read-after=", 18) == 0) {
			o.fail_at = strtol(argv[a] + 18, &end, 10);
			if (strcmp(end, ":error") == 0)
				o.fail_error = 1;
			else if (*end || o.fail_at < 0)
				return usage();
		} else if (strncmp(argv[a], "--forbid=", 9) == 0) {
			o.forbid_lo = (uint32_t)strtoul(argv[a] + 9, &end, 10);
			if (*end != ':')
				return usage();
			o.forbid_hi = (uint32_t)strtoul(end + 1, &end, 10);
			if (*end)
				return usage();
		} else if (strcmp(argv[a], "--trace-reads") == 0) {
			o.trace = 1;
		} else if (strncmp(argv[a], "--missing-advance=", 18) == 0) {
			o.missing_advance = strtol(argv[a] + 18, &end, 10);
			if (*end || o.missing_advance < 0 || o.missing_advance > 255)
				return usage();
		} else if (strncmp(argv[a], "--target=", 9) == 0) {
			int k;
			for (k = 0; k < 10 && strcmp(argv[a] + 9, kind_names[k]) != 0; ++k)
				;
			if (k == 10)
				return usage();
			o.kind = (svf_target_kind)k;
		} else if (strncmp(argv[a], "--stride=", 9) == 0) {
			o.stride = strtol(argv[a] + 9, &end, 0);
			if (*end || o.stride < 0 || o.stride > 0xFFFF)
				return usage();
		} else if (strncmp(argv[a], "--buf-delta=", 12) == 0) {
			errno = 0; /* a 32-bit long saturates at LONG_MIN / LONG_MAX with ERANGE */
			o.buf_delta = strtol(argv[a] + 12, &end, 0);
			/* +-(2^31 - 1): rows * stride (below 2^31) + buf_delta stays far inside long long */
			if (*end || errno || o.buf_delta < -0x7FFFFFFFl || o.buf_delta > 0x7FFFFFFFl)
				return usage();
		} else if (strncmp(argv[a], "--clip=", 7) == 0) {
			int k;
			end = argv[a] + 6;
			for (k = 0; k < 4; ++k) {
				if (*end != (k ? ':' : '='))
					return usage();
				o.clip[k] = strtol(end + 1, &end, 10);
				if (o.clip[k] < -32768 || o.clip[k] > 32767)
					return usage();
			}
			if (*end)
				return usage();
			o.clip_set = 1;
		} else if (strncmp(argv[a], "--fg=", 5) == 0 || strncmp(argv[a], "--bg=", 5) == 0) {
			unsigned long v;
			if (!parse_num(argv[a] + 5, 0xFFFF, &v))
				return usage();
			*(argv[a][2] == 'f' ? &o.fg : &o.bg) = (long)v;
		} else if (strncmp(argv[a], "--index-base=", 13) == 0 || strncmp(argv[a], "--index-levels=", 15) == 0) {
			int is_base = argv[a][8] == 'b';
			unsigned long v;
			if (!parse_num(argv[a] + (is_base ? 13 : 15), 255, &v))
				return usage();
			*(is_base ? &o.index_base : &o.index_levels) = (long)v;
		} else if (strncmp(argv[a], "--fg888=", 8) == 0 || strncmp(argv[a], "--bg888=", 8) == 0) {
			unsigned long v;
			if (!parse_num(argv[a] + 8, 0xFFFFFFFFul, &v))
				return usage();
			*(argv[a][2] == 'f' ? &o.fg888 : &o.bg888) = v;
		} else if (strncmp(argv[a], "--misalign=", 11) == 0) {
			o.misalign = strtol(argv[a] + 11, &end, 10);
			if (end == argv[a] + 11 || *end || o.misalign < 0 || o.misalign > 3)
				return usage();
		} else if (strncmp(argv[a], "--threshold=", 12) == 0) {
			unsigned long v;
			if (!parse_num(argv[a] + 12, 255, &v))
				return usage();
			o.threshold = (long)v;
		} else if (strncmp(argv[a], "--fill=", 7) == 0) {
			unsigned long v;
			if (!parse_num(argv[a] + 7, 255, &v))
				return usage();
			o.fill = (int)v;
		} else if (strcmp(argv[a], "--no-plot") == 0) {
			o.no_plot = 1;
		} else if (strcmp(argv[a], "--big-endian") == 0) {
			o.tflags |= SVF_TF_565_BIGENDIAN;
		} else if (strcmp(argv[a], "--lsb-first") == 0) {
			o.tflags |= SVF_TF_GRAY_LSB_FIRST;
		} else if (strncmp(argv[a], "--gray-bits=", 12) == 0) {
			unsigned long v;
			if (!parse_num(argv[a] + 12, 255, &v))
				return usage();
			o.gray_bits = (long)v;
		} else if (strncmp(argv[a], "--syllable-cache=", 17) == 0) {
			o.cache_bytes = strtol(argv[a] + 17, &end, 10);
			if (*end || o.cache_bytes < 0)
				return usage();
		} else if (strcmp(argv[a], "--print-reads") == 0) {
			o.print_reads = 1;
		} else if (strcmp(argv[a], "--print-scratch") == 0) {
			o.print_scratch = 1;
		} else if (strncmp(argv[a], "--scale=", 8) == 0) {
			o.scale_num = strtol(argv[a] + 8, &end, 10);
			if (*end != '/' || o.scale_num < 0 || o.scale_num > 255)
				return usage();
			o.scale_den = strtol(end + 1, &end, 10);
			if (*end || o.scale_den < 0 || o.scale_den > 255)
				return usage();
		} else if (strncmp(argv[a], "--scratch-delta=", 16) == 0) {
			o.scratch_delta = strtol(argv[a] + 16, &end, 10);
			if (*end)
				return usage();
		} else {
			return usage();
		}
	}
	if (a < argc && (strcmp(argv[a], "line") == 0 || strcmp(argv[a], "measure") == 0))
		return line_cmd(argc - a, argv + a, &o);
	if (argc - a < 2)
		return usage();
	cmd = argv[a + 1];
	if ((argc - a != 2 && strcmp(cmd, "has") != 0 && strcmp(cmd, "reads") != 0 && strcmp(cmd, "cells") != 0) ||
	    (strcmp(cmd, "glyphs") != 0 && strcmp(cmd, "info") != 0 && strcmp(cmd, "syllables") != 0 &&
	     strcmp(cmd, "has") != 0 && strcmp(cmd, "reads") != 0 && strcmp(cmd, "cells") != 0))
		return usage();
	rc = load(&l, argv[a], &o);
	if (rc)
		return rc;
	if (strcmp(cmd, "glyphs") == 0) {
		rc = dump_glyphs(&l.face);
	} else if (strcmp(cmd, "syllables") == 0) {
		rc = dump_syllables(&l.face);
	} else if (strcmp(cmd, "has") == 0) {
		rc = dump_has(&l.face, argc - a - 2, argv + a + 2);
	} else if (strcmp(cmd, "reads") == 0) {
		rc = dump_reads(&l.face, argc - a - 2, argv + a + 2);
	} else if (strcmp(cmd, "cells") == 0) {
		rc = dump_cells(&l.face, argc - a - 2, argv + a + 2);
	} else {
		dump_info(&l.face, l.data);
		rc = 0;
	}
#ifdef SVF_TEST_RD8
	fprintf(stderr, "svfdump: rd8 calls=%lu\n", svf_test_rd8_calls());
#endif
	unload(&l);
	return rc;
}
