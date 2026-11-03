/* vesa-lines-dump [--dac 6|8] --print-table FILE - the table vesa_lines.c parsed from FILE and its 256-entry palette as
 * text (the format of tools/vesa_lines.py print_table; the test compares the two). On a refusal: stderr
 * `vesa-lines: line N: message`, exit 1. A usage error exits 2. Also, for the tests:
 *   --substitute W H BPP TEXT [OUTLEN]   vl_substitute into an OUTLEN byte buffer (default 1024): the result, then
 *                                        "\nneed=<length the whole result needs>\n"
 *   --cache-slots LEN                    vl_cache_slots(LEN)
 *   --open-face FILE                     svf_open_stream on FILE with the cache svfvesa sizes: "ok" or the svf_err */
#include "svf.h"
#include "vesa_lines.h"

#include <stdlib.h>

static long read_file(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	FILE *fp = ctx;

	if (fseek(fp, (long)offset, SEEK_SET) != 0)
		return -1;
	return (long)fread(dst, 1, len, fp);
}

static int open_face(const char *path)
{
	static uint8_t tables[65536], cache[64 * (VL_CACHE_BLOCK + 8)];
	svf_face f;
	svf_err e;
	long len;
	size_t need;
	FILE *fp = fopen(path, "rb");

	if (!fp || fseek(fp, 0, SEEK_END) != 0 || (len = ftell(fp)) <= 0)
		return 2;
	need = svf_stream_tables_size(read_file, fp, (uint32_t)len, &e);
	if (e == SVF_OK && need <= sizeof tables)
		e = svf_open_stream(&f, read_file, fp, (uint32_t)len, tables, need, cache,
		                    vl_cache_slots((size_t)len) * (VL_CACHE_BLOCK + 8), VL_CACHE_BLOCK);
	fclose(fp);
	if (e != SVF_OK) {
		printf("svf_err %d\n", (int)e);
		return 1;
	}
	printf("ok\n");
	return 0;
}

int main(int argc, char **argv)
{
	static vl_table t;
	static uint8_t pal[256][4];
	const char *path = NULL;
	unsigned dac = 8;
	char err[128];
	int i, line_no = 0;
	FILE *fp;

	if (argc == 3 && strcmp(argv[1], "--cache-slots") == 0) {
		printf("%lu\n", (unsigned long)vl_cache_slots((size_t)strtoul(argv[2], NULL, 10)));
		return 0;
	}
	if (argc == 3 && strcmp(argv[1], "--open-face") == 0)
		return open_face(argv[2]);
	if ((argc == 6 || argc == 7) && strcmp(argv[1], "--substitute") == 0) {
		static char out[65536];

		memset(out, 0x7F, sizeof out); /* a missing NUL store shows as garbage after the text */
		size_t outlen = argc == 7 ? (size_t)strtoul(argv[6], NULL, 10) : 1024, need;

		if (outlen > sizeof out)
			outlen = sizeof out;
		need = vl_substitute(argv[5], (unsigned)atoi(argv[2]), (unsigned)atoi(argv[3]), (unsigned)atoi(argv[4]), out,
		                     outlen);
		fwrite(out, 1, outlen ? strlen(out) : 0, stdout);
		printf("\nneed=%lu\n", (unsigned long)need);
		return 0;
	}
	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--print-table") == 0 && i + 1 < argc && !path)
			path = argv[++i];
		else if (strcmp(argv[i], "--dac") == 0 && i + 1 < argc && (strcmp(argv[i + 1], "6") == 0 || strcmp(argv[i + 1], "8") == 0))
			dac = (unsigned)atoi(argv[++i]);
		else {
			fprintf(stderr, "usage: vesa-lines-dump [--dac 6|8] --print-table FILE\n");
			return 2;
		}
	}
	if (!path) {
		fprintf(stderr, "usage: vesa-lines-dump [--dac 6|8] --print-table FILE\n");
		return 2;
	}
	fp = fopen(path, "rb");
	if (!fp) {
		fprintf(stderr, "vesa-lines: cannot open %s\n", path);
		return 2;
	}
	if (vl_parse(fp, &t, err, &line_no) != 0) {
		fprintf(stderr, "vesa-lines: line %d: %s\n", line_no, err);
		fclose(fp);
		return 1;
	}
	fclose(fp);
	for (i = 0; i < t.ncolours; i++) {
		const vl_colour *c = &t.colours[i];

		printf("colour name=%s rgb565=0x%04X rgb555=0x%04X rgb888=0x%06X base=%u levels=%u\n", c->name, c->rgb565,
		       c->rgb555, (unsigned)c->rgb888, c->index_base, c->index_levels);
	}
	printf("background=%s\n", t.colours[t.background].name);
	for (i = 0; i < t.nlines; i++) {
		const vl_line *l = &t.lines[i];
		int k;

		printf("line faces=");
		for (k = 0; k < l->nfaces; k++)
			printf("%s%s", k ? "+" : "", l->faces[k]);
		printf(" scale=%u/%u x=%d baseline=%d colour=%s text=%s\n", l->num, l->den, l->x, l->baseline,
		       t.colours[l->colour].name, l->text);
	}
	vl_palette(&t, dac, pal);
	for (i = 0; i < 256; i++)
		printf("palette[%d]=%02X %02X %02X\n", i, pal[i][0], pal[i][1], pal[i][2]);
	return 0;
}
