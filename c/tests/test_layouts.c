/* test_layouts - the build's supported layout set against six files (host only).
 *
 *   test-layouts DIR BUILD
 *
 * Opens DIR/{default,mcu-strict,dos,simd16,full,u64}.svf (the same face in six layouts, tools/test_c_renderer.py
 * TestLayoutsBuild writes them with svf2to3.py), mapped and streamed, and prints one line
 *
 *   layouts: NAME=SVF_ERROR_NAME ...
 *
 * (the mapped open's result). The expectation is the build's SVF_LAYOUTS: a file is accepted iff its (REC, ROW, TAB)
 * is in svf_layouts, or every file when the build has no set; a refused file gives SVF_E_LAYOUT mapped and streamed,
 * leaves the face all zero, and svf_glyph on it returns what it returns on a memset zero face. The last line is
 * "layouts: OK BUILD" (exit 0) or "layouts: FAIL BUILD NAME" (exit 1).
 *
 *   test-layouts --cuts FILE END
 *
 * Opens the first K bytes of FILE for every K in 0..END, each in a buffer of exactly K bytes (a read past it is an
 * AddressSanitizer report), mapped and streamed: every one must be refused (not SVF_OK) and leave the face all zero.
 * Prints "cuts: N refused" (exit 0) or "cuts: FAIL at K" (exit 1).
 */
#include "svf.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *const names[] = {"default", "mcu-strict", "dos", "simd16", "full", "u64"};

static const char *err_name(svf_err e)
{
	static const char *const n[] = {"SVF_OK",       "SVF_E_MAGIC", "SVF_E_VERSION", "SVF_E_BPP",   "SVF_E_RANGE",
	                                "SVF_E_NOMEM", "SVF_E_IO",    "SVF_E_ARG",     "SVF_E_LAYOUT"};
	return (unsigned)e < sizeof n / sizeof n[0] ? n[e] : "SVF_E_?";
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

typedef struct {
	const uint8_t *data;
	size_t len;
} source;

static long read_cb(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	const source *s = ctx;

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

/* Non-zero if the build accepts a file whose layout bytes (9, 10) are @p b9, @p b10. */
static int accepted(uint8_t b9, uint8_t b10)
{
	const uint16_t *set;
	size_t n = svf_layouts(&set), i;
	uint16_t code = (uint16_t)SVF_LAYOUT(b9 & 7, b9 >> 3 & 7, b10 & 7);

	if (!n)
		return set == NULL;
	for (i = 0; i < n; ++i)
		if (set[i] == code)
			return 1;
	return 0;
}

/* The name of the first file the build gets wrong, or NULL. */
static const char *run(const char *dir, char *line, size_t line_len)
{
	size_t k, used = 0;

	line[0] = 0;
	for (k = 0; k < sizeof names / sizeof names[0]; ++k) {
		char path[1024];
		size_t len = 0;
		uint8_t *data;
		svf_face fm, fs, zero;
		uint8_t *tables;
		size_t need;
		svf_err em, es, et, want;
		source src;
		uint8_t cell[4096], cell0[4096];
		int bad = 0;

		snprintf(path, sizeof path, "%s/%s.svf", dir, names[k]);
		data = read_file(path, &len);
		if (!data || len < 11)
			return names[k];
		want = accepted(data[9], data[10]) ? SVF_OK : SVF_E_LAYOUT;
		em = svf_open_mapped(&fm, data, len);
		src.data = data;
		src.len = len;
		need = svf_stream_tables_size(read_cb, &src, (uint32_t)len, &et);
		tables = malloc(need ? need : 1);
		memset(&fs, 0xFF, sizeof fs);
		es = tables ? svf_open_stream(&fs, read_cb, &src, (uint32_t)len, tables, need, NULL, 0, 0) : SVF_E_NOMEM;
		if (em != want || es != want || et != want)
			bad = 1;
		if (want == SVF_E_LAYOUT) {
			svf_err a, b;
			memset(&zero, 0, sizeof zero);
			a = svf_glyph(&fm, 'A', cell, sizeof cell);
			b = svf_glyph(&zero, 'A', cell0, sizeof cell0);
			if (!all_zero(&fm) || !all_zero(&fs) || a != b)
				bad = 1;
		} else if (!bad) {
			/* An accepted face draws: the same cell mapped and streamed. */
			uint32_t cp = svf_cmap_cp(&fm, 0);
			memset(cell, 0, sizeof cell);
			memset(cell0, 0, sizeof cell0);
			if (svf_glyph(&fm, cp, cell, sizeof cell) != SVF_OK ||
			    svf_glyph(&fs, cp, cell0, sizeof cell0) != SVF_OK || memcmp(cell, cell0, sizeof cell))
				bad = 1;
		}
		if (used < line_len)
			used += (size_t)snprintf(line + used, line_len - used, " %s=%s", names[k], err_name(em));
		free(tables);
		free(data);
		if (bad)
			return names[k];
	}
	return NULL;
}

static int cuts(const char *path, unsigned long end)
{
	size_t len = 0;
	uint8_t *whole = read_file(path, &len);
	unsigned long k;

	if (!whole || end > len) {
		printf("cuts: FAIL cannot read %s\n", path);
		return 1;
	}
	for (k = 0; k <= end; ++k) {
		uint8_t *cut = malloc(k ? k : 1), *tables;
		svf_face fm, fs;
		source src;
		size_t need;
		svf_err et, em, es;

		if (!cut)
			return 1;
		memcpy(cut, whole, k);
		src.data = cut;
		src.len = k;
		em = svf_open_mapped(&fm, cut, k);
		need = svf_stream_tables_size(read_cb, &src, (uint32_t)k, &et);
		tables = malloc(need ? need : 1);
		es = tables ? svf_open_stream(&fs, read_cb, &src, (uint32_t)k, tables, need, NULL, 0, 0) : SVF_E_NOMEM;
		if (em == SVF_OK || es == SVF_OK || et == SVF_OK || !all_zero(&fm) || !all_zero(&fs)) {
			printf("cuts: FAIL at %lu\n", k);
			return 1;
		}
		free(tables);
		free(cut);
	}
	free(whole);
	printf("cuts: %lu refused\n", end + 1);
	return 0;
}

int main(int argc, char **argv)
{
	char line[512];
	const char *bad;

	if (argc == 4 && strcmp(argv[1], "--cuts") == 0)
		return cuts(argv[2], strtoul(argv[3], NULL, 10));
	if (argc != 3) {
		fprintf(stderr, "usage: test-layouts DIR BUILD\n");
		return 2;
	}
	bad = run(argv[1], line, sizeof line);
	printf("layouts:%s\n", line);
	if (bad) {
		printf("layouts: FAIL %s %s\n", argv[2], bad);
		return 1;
	}
	printf("layouts: OK %s\n", argv[2]);
	return 0;
}
