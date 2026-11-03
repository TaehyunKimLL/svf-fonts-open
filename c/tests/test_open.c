/* test_open - open cases svfdump cannot reach (host only). Prints one line per case; exit 0 when all pass, 1 otherwise.
 *
 *   test-open            a length above 32 bits is refused before any byte is read (a v3 header); a streamed
 *                        open whose tables pass 65535 bytes only through the glyph offset table is refused
 *                        SVF_E_NOMEM when size_t is 16 bits (built with -DSVF__SIZE_MAX=0xFFFF, test-open-size16:
 *                        prints "tables-size-overflow: ok"), else opens
 *   test-open FACE [FACE3]
 *                        also: every failed svf_open_mapped / svf_open_stream leaves the face all zero (no data,
 *                        tables, cache or ctx pointer kept), for argument, header, size, read and table errors, on
 *                        FACE and on FACE3 (a v3 face)
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

static void len_above_32_bits(void)
{
	static const uint8_t head[48] = {'S', 'V', 'F', 'N', 3, 0};
	svf_face f;
	uint64_t lens[2];
	char name[64];
	int i;

	if (sizeof(size_t) <= 4) {
		printf("len-above-32-bits: skip (32-bit size_t)\n");
		return;
	}
	lens[0] = (uint64_t)1 << 32;
	lens[1] = ((uint64_t)1 << 32) + sizeof head;
	for (i = 0; i < 2; ++i) {
		/* The length is a lie: open must refuse it without reading past the bytes there are. */
		svf_err e = svf_open_mapped(&f, head, (size_t)lens[i]);
		snprintf(name, sizeof name, "len-above-32-bits v3 %llu", (unsigned long long)lens[i]);
		check(name, e == SVF_E_RANGE);
	}
}

/* ---- failed opens leave the face all zero -------------------------------------------------------------------- */

typedef struct {
	const uint8_t *data;
	size_t len;
	long fail_at; /* the call that fails, or -1 */
	long calls;
} source;

static long read_cb(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	source *s = ctx;

	if (s->calls++ == s->fail_at)
		return -1;
	if (offset > s->len || len > s->len - offset)
		return -1;
	memcpy(dst, s->data + offset, len);
	return (long)len;
}

static int all_zero(const svf_face *f)
{
	const uint8_t *p = (const uint8_t *)f;
	size_t i;

	for (i = 0; i < sizeof *f; ++i)
		if (p[i])
			return 0;
	return 1;
}

/* Opens @p data as a streamed face with a cache and a tables buffer of @p tables_len (0: the size needed), failing
 * callback call @p fail_at; the face starts as 0xFF bytes. */
static svf_err open_stream(svf_face *f, const uint8_t *data, size_t len, size_t tables_len, long fail_at)
{
	static uint8_t tables[1 << 20], cache[4096];
	source s;
	svf_err e;

	s.data = data;
	s.len = len;
	s.fail_at = -1;
	s.calls = 0;
	if (!tables_len)
		tables_len = svf_stream_tables_size(read_cb, &s, (uint32_t)len, &e);
	s.fail_at = fail_at;
	s.calls = 0;
	memset(f, 0xFF, sizeof *f);
	return svf_open_stream(f, read_cb, &s, (uint32_t)len, tables, tables_len, cache, sizeof cache, 512);
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

/* ---- tables that pass a 16-bit size_t only through the glyph offset table ------------------------------------------ */

static void put16(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)v;
	p[1] = (uint8_t)(v >> 8);
}

static void put32(uint8_t *p, uint32_t v)
{
	put16(p, v & 0xFFFF);
	put16(p + 2, v >> 16);
}

/* A v3 face of @p n blank glyphs (8 x 8, 1 bpp; units 2 / 0 / 2, u32 offsets): the code point table is 8 * n bytes, the
 * offset table 4 * (n + 1), the 4 byte records n * 4. Returns the file; *len its size. */
static uint8_t *blank_face(unsigned n, size_t *len)
{
	size_t cmap = 48, goff = cmap + 8u * n, data = goff + 4u * (n + 1), size = data + 4u * n;
	uint8_t *d = calloc(size, 1);
	unsigned i;

	if (!d)
		return NULL;
	memcpy(d, "SVFN", 4);
	put16(d + 4, 3);
	d[8] = 1;
	d[9] = 2;           /* REC 2, ROW 0 */
	d[10] = 2 | 8;      /* TAB 2, u32 offsets */
	put16(d + 12, n);
	d[14] = d[15] = 8;
	put32(d + 24, (uint32_t)data);
	put32(d + 28, 4 * n);
	put32(d + 32, (uint32_t)cmap);
	put32(d + 44, (uint32_t)goff);
	for (i = 0; i < n; ++i) {
		put32(d + cmap + 8 * i, 0x100 + i);
		put32(d + cmap + 8 * i + 4, i);
	}
	for (i = 0; i <= n; ++i)
		put32(d + goff + 4 * i, 4 * i);
	*len = size;
	return d;
}

static void tables_size_overflow(void)
{
	/* 6000 glyphs: 8 + 8 * 6000 = 48008 bytes of tables without the offset table (fits 65535), 72012 with it. 5000
	 * glyphs: 60012 either way. With a 16-bit size_t (-DSVF__SIZE_MAX=0xFFFF) the first is refused SVF_E_NOMEM, the
	 * second opens; with a wider one both open. */
	static uint8_t tables[1 << 20];
	size_t len, need;
	uint8_t *d = blank_face(6000, &len);
	source s = {NULL, 0, -1, 0};
	svf_face f;
	svf_err e;
	int ok = 1;

	if (!d) {
		check("tables-size-overflow: malloc", 0);
		return;
	}
	s.data = d;
	s.len = len;
	ok &= svf_open_mapped(&f, d, len) == SVF_OK;
	need = svf_stream_tables_size(read_cb, &s, (uint32_t)len, &e);
#ifdef SVF__SIZE_MAX
	ok &= need == 0 && e == SVF_E_NOMEM;
	/* open_stream with a buffer as big as a 16-bit size_t allows: too small for the tables, NOMEM too */
	ok &= svf_open_stream(&f, read_cb, &s, (uint32_t)len, tables, 0xFFFF, NULL, 0, 0) == SVF_E_NOMEM;
#else
	ok &= e == SVF_OK && need == 8 + 8 * 6000 + 4 * 6001;
	ok &= svf_open_stream(&f, read_cb, &s, (uint32_t)len, tables, need, NULL, 0, 0) == SVF_OK;
#endif
	free(d);
	d = blank_face(5000, &len);
	if (!d) {
		check("tables-size-overflow: malloc", 0);
		return;
	}
	s.data = d;
	s.len = len;
	need = svf_stream_tables_size(read_cb, &s, (uint32_t)len, &e);
	ok &= e == SVF_OK && need == 8 + 8 * 5000 + 4 * 5001;
	ok &= svf_open_stream(&f, read_cb, &s, (uint32_t)len, tables, need, NULL, 0, 0) == SVF_OK;
	free(d);
	check("tables-size-overflow", ok);
}

/* A callback that fails a read of 0 bytes (as an fread wrapper may). */
static long read_cb_no_zero(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	return len ? read_cb(ctx, offset, dst, len) : -1;
}

/* A hostile v3 face with a 0-byte record (glyph 0: offset entries 0, 0): a streamed glyph read refuses it with
 * SVF_E_RANGE, as a mapped open does, without ever asking the callback for 0 bytes. */
static void zero_length_record(void)
{
	static uint8_t tables[1 << 16], cell[64];
	size_t len, need;
	uint8_t *d = blank_face(8, &len);
	source s = {NULL, 0, -1, 0};
	svf_face f;
	svf_err e;
	int ok = 1;

	if (!d) {
		check("zero-length-record: malloc", 0);
		return;
	}
	put32(d + 48 + 8 * 8 + 4, 0); /* goff entry 1 = 0: record 0 is 0 bytes, record 1 is 8 */
	s.data = d;
	s.len = len;
	ok &= svf_open_mapped(&f, d, len) == SVF_E_RANGE;
	need = svf_stream_tables_size(read_cb_no_zero, &s, (uint32_t)len, &e);
	ok &= e == SVF_OK;
	ok &= svf_open_stream(&f, read_cb_no_zero, &s, (uint32_t)len, tables, need, NULL, 0, 0) == SVF_OK;
	memset(cell, 0xA5, sizeof cell);
	ok &= svf_glyph(&f, 0x100, cell, sizeof cell) == SVF_E_RANGE;
	ok &= svf_glyph(&f, 0x101, cell, sizeof cell) == SVF_OK;
	free(d);
	check("zero-length-record", ok);
}

static void failed_opens_clear(const uint8_t *good, size_t len)
{
	uint8_t *d = malloc(len);
	svf_face f;
	svf_err e;
	uint32_t cmap_off;
	size_t need;
	source s = {NULL, 0, -1, 0};

	if (!d) {
		check("cleared: malloc", 0);
		return;
	}
	s.data = good;
	s.len = len;
	need = svf_stream_tables_size(read_cb, &s, (uint32_t)len, &e);
	check("cleared: the face opens", e == SVF_OK && open_stream(&f, good, len, 0, -1) == SVF_OK &&
	                                     svf_open_mapped(&f, good, len) == SVF_OK);

	memset(&f, 0xFF, sizeof f);
	check("cleared: mapped, null data", svf_open_mapped(&f, NULL, 4) == SVF_E_ARG && all_zero(&f));
	memcpy(d, good, len);
	d[0] = 'X';
	memset(&f, 0xFF, sizeof f);
	check("cleared: mapped, bad magic", svf_open_mapped(&f, d, len) == SVF_E_MAGIC && all_zero(&f));
	check("cleared: stream, bad magic", open_stream(&f, d, len, 64, -1) == SVF_E_MAGIC && all_zero(&f));

	/* A glyph index past the count: refused after the tables are read (data, rd, ctx, cache all set by then). */
	memcpy(d, good, len);
	cmap_off = (uint32_t)d[32] | (uint32_t)d[33] << 8 | (uint32_t)d[34] << 16 | (uint32_t)d[35] << 24;
	memset(d + cmap_off + 4, 0xFF, 4);
	memset(&f, 0xFF, sizeof f);
	check("cleared: mapped, bad glyph index", svf_open_mapped(&f, d, len) == SVF_E_RANGE && all_zero(&f));
	check("cleared: stream, bad glyph index", open_stream(&f, d, len, 0, -1) == SVF_E_RANGE && all_zero(&f));

	check("cleared: stream, tables too small", open_stream(&f, good, len, need - 1, -1) == SVF_E_NOMEM && all_zero(&f));
	check("cleared: stream, header read fails", open_stream(&f, good, len, 0, 0) == SVF_E_IO && all_zero(&f));
	check("cleared: stream, cmap read fails", open_stream(&f, good, len, 0, 1) == SVF_E_IO && all_zero(&f));
	check("cleared: stream, last table read fails", open_stream(&f, good, len, 0, 3) == SVF_E_IO && all_zero(&f));

	memset(&f, 0xFF, sizeof f);
	check("cleared: stream, null callback",
	      svf_open_stream(&f, NULL, NULL, (uint32_t)len, NULL, 0, NULL, 0, 0) == SVF_E_ARG && all_zero(&f));
	memset(&f, 0xFF, sizeof f);
	{
		static uint8_t tables[64], cache[100];
		check("cleared: stream, one cache slot",
		      svf_open_stream(&f, read_cb, &s, (uint32_t)len, tables, sizeof tables, cache, sizeof cache, 64) ==
		              SVF_E_ARG &&
		          all_zero(&f));
	}
	free(d);
}

/* Header flag bits other than 0..2 are 0 (spec/SVF.md): a face with any of the other 13 bits set is SVF_E_LAYOUT, mapped
 * and streamed; flags 0 and 4 (marks at origin) still open. */
static void unknown_flag_bits(void)
{
	size_t len;
	uint8_t *d = blank_face(2, &len);
	unsigned bit, ok = 1;
	svf_face f;

	if (!d) {
		check("unknown flag bits: alloc", 0);
		return;
	}
	for (bit = 3; bit < 16; ++bit) {
		put16(d + 6, 1u << bit);
		ok &= svf_open_mapped(&f, d, len) == SVF_E_LAYOUT && all_zero(&f);
		ok &= open_stream(&f, d, len, 0, -1) == SVF_E_LAYOUT && all_zero(&f);
	}
	put16(d + 6, 0xFFF8u | 4u);
	ok &= svf_open_mapped(&f, d, len) == SVF_E_LAYOUT;
	check("flag bits 3..15 refused (SVF_E_LAYOUT), mapped and streamed", ok);
	put16(d + 6, 0);
	ok = svf_open_mapped(&f, d, len) == SVF_OK;
	put16(d + 6, 4);
	ok &= svf_open_mapped(&f, d, len) == SVF_OK;
	check("flags 0 and 4 open", ok);
	free(d);
}

int main(int argc, char **argv)
{
	int i;

	len_above_32_bits();
	tables_size_overflow();
	unknown_flag_bits();
	zero_length_record();
	for (i = 1; i < argc && i < 3; ++i) {
		size_t len = 0;
		uint8_t *data = read_file(argv[i], &len);
		if (!data) {
			printf("%s: FAIL (cannot read)\n", argv[i]);
			return 1;
		}
		failed_opens_clear(data, len);
		free(data);
	}
	return bad;
}
