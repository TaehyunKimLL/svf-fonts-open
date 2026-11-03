/* svfsdl - the SDL2 / SDL3 example of the C renderer: draws the lines of sdl-lines.txt into an SDL surface (the packed
 * kinds) with svf_draw_utf8 and presents it. One source for both SDLs (sdl_compat.h). With --dump it writes the surface's
 * bytes behind a 16-byte header for sdl_check.py (the header is described there) and exits, so a headless run under
 * SDL_VIDEODRIVER=dummy proves the bytes in SDL's memory.
 *
 *   svfsdl [--format xrgb8888|argb8888|rgb565|rgb555|bgr24|index8|gray] [--gray-bits 1|2|4|8] [--lsb-first]
 *          [--threshold N] [--alpha-demo] [--size WxH] [--present surface|texture|texture-direct] [--stream]
 *          [--syllable-cache=BYTES] [--faces DIR] [--lines FILE] [--dump FILE] [--shot FILE] [--frames N]
 *
 * index8 is a palettised 8 bpp surface (SVF_T_INDEXED8, the lines file's index ramps); gray is a palettised surface of
 * --gray-bits (default 8) bits, MSB first or with --lsb-first (SVF_T_GRAY, gray palette from the background to white).
 * --gray-bits without --format gray is a usage error (exit 2); --threshold N (0..255, default 128: the cut of 1 bit gray
 * and of an index8 colour with one level) and --lsb-first are accepted with other formats and ignored there.
 * --alpha-demo draws the first line only (the other lines' faces are not opened; a file without a text line is exit 2), as
 * GRAY8 coverage, into a BGRA32 surface of its line colour and blends it over a gradient (--present surface or texture);
 * --format and --gray-bits have no effect with it, in either order, but their values are still checked (a misspelt
 * --format, a --gray-bits other than 1, 2, 4 or 8 are exit 2); --dump writes
 * the GRAY8 buffer (pitch w) and the `svfsdl:` line gives both the surface's `pitch` and the buffer's `covpitch`. index8
 * and gray cannot use --present texture-direct (a texture has no palette), nor can --alpha-demo; --present texture
 * converts the surface once.
 * --shot saves the window surface and so needs --present surface (texture modes: exit 2, a restriction kept on purpose:
 * SDL_RenderReadPixels differs in kind between SDL2 and SDL3 and the screenshots are of the surface path). --dump and --shot show the first frame and, with --frames 0 (until closed), end there; --frames N
 * shows N frames. --present texture-direct draws into the locked texture and cannot --dump.
 *
 * Exit 0 ok, 2 a bad option or input (nothing written), 1 an SDL or library error at run time. One `svfsdl:` line on stdout. */
#include "sdl_compat.h"
#include "svf.h"
#include "vesa_lines.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define MAX_FACE_FILES (VL_MAX_LINES * VL_MAX_FACES)
#define DEFAULT_LINES "c/ports/sdl/sdl-lines.txt"

typedef struct {
	const char *name;
	svfsdl_format fmt;
	svf_target_kind kind;
	unsigned bpp, bytes;
	int rgb16, alpha;
	int pal; /* 0 no palette, 1 index8, 2 gray */
} fmt_desc;

static const fmt_desc formats[] = {
	{"xrgb8888", SDL_PIXELFORMAT_BGRX32, SVF_T_XRGB8888, 32, 4, 0, 0, 0},
	{"argb8888", SDL_PIXELFORMAT_BGRA32, SVF_T_XRGB8888, 32, 4, 0, 1, 0},
	{"rgb565", SDL_PIXELFORMAT_RGB565, SVF_T_RGB565, 16, 2, 1, 0, 0},
	{"rgb555", SDL_PIXELFORMAT_XRGB1555, SVF_T_RGB555, 16, 2, 1, 0, 0},
	{"bgr24", SDL_PIXELFORMAT_BGR24, SVF_T_RGB888, 24, 3, 0, 0, 0},
	{"index8", SDL_PIXELFORMAT_INDEX8, SVF_T_INDEXED8, 8, 1, 0, 0, 1},
	{"gray", SDL_PIXELFORMAT_INDEX8, SVF_T_GRAY, 8, 1, 0, 0, 2}, /* fmt and bpp follow --gray-bits / --lsb-first */
};
/* --alpha-demo: the buffer drawn and dumped is GRAY8 (bits per pixel 8), the surface a BGRA32 */
static const fmt_desc alpha_desc = {"alpha", SDL_PIXELFORMAT_BGRA32, SVF_T_GRAY8, 8, 1, 0, 0, 0};
/* gray surface formats by bits (1, 2, 4, 8 -> row 0..3) and bit order (MSB, LSB) */
static const svfsdl_format gray_formats[4][2] = {
	{SDL_PIXELFORMAT_INDEX1MSB, SDL_PIXELFORMAT_INDEX1LSB},
	{SDL_PIXELFORMAT_INDEX2MSB, SDL_PIXELFORMAT_INDEX2LSB},
	{SDL_PIXELFORMAT_INDEX4MSB, SDL_PIXELFORMAT_INDEX4LSB},
	{SDL_PIXELFORMAT_INDEX8, SDL_PIXELFORMAT_INDEX8},
};
static unsigned threshold = 128, lsb_first;

typedef struct {
	char name[13];
	FILE *fp;
	uint8_t *data, *tables, *cache;
	svf_face face;
} face_file;

static vl_table table;
static face_file files[MAX_FACE_FILES];
static int nfiles;
static svf_chain chains[VL_MAX_LINES];
static svf_face *chain_faces[VL_MAX_LINES][VL_MAX_FACES];
static uint8_t *chain_caches[VL_MAX_LINES];
static uint8_t *scratch;
static size_t scratch_len;

static void usage_die(const char *fmt, ...)
{
	va_list ap;

	fputs("svfsdl: ", stderr);
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
	fputc('\n', stderr);
	exit(2);
}

static void run_die(const char *what)
{
	const char *e = SDL_GetError();

	if (*e)
		fprintf(stderr, "svfsdl: %s: %s\n", what, e);
	else
		fprintf(stderr, "svfsdl: %s failed\n", what);
	exit(1);
}

/* Out of memory is a run failure (exit 1), not an input error (exit 2). */
static void oom_die(const char *what)
{
	fprintf(stderr, "svfsdl: out of memory%s%s\n", what ? " for " : "", what ? what : "");
	exit(1);
}

static long read_cb(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	FILE *fp = ctx;

	if (fseek(fp, (long)offset, SEEK_SET) != 0)
		return -1;
	return (long)fread(dst, 1, len, fp);
}

/* The face called @p name in @p dir: read whole (mapped) or opened as a stream; kept open for the run. */
static face_file *open_face(const char *dir, const char *name, int stream)
{
	face_file *f;
	char path[1024];
	long len;
	size_t need, slots;
	svf_err e;
	int i;

	for (i = 0; i < nfiles; i++)
		if (strcmp(files[i].name, name) == 0)
			return &files[i];
	if (nfiles == MAX_FACE_FILES)
		usage_die("more than %d different faces", MAX_FACE_FILES);
	f = &files[nfiles++];
	memset(f, 0, sizeof *f);
	if (strlen(name) >= sizeof f->name)
		usage_die("face name %s is longer than 12 bytes", name);
	memcpy(f->name, name, strlen(name) + 1);
	snprintf(path, sizeof path, "%s/%s", dir, name);
	f->fp = fopen(path, "rb");
	if (!f->fp || fseek(f->fp, 0, SEEK_END) != 0 || (len = ftell(f->fp)) <= 0 || fseek(f->fp, 0, SEEK_SET) != 0)
		usage_die("cannot open face %s", path);
	if (!stream) {
		f->data = malloc((size_t)len);
		if (!f->data || fread(f->data, 1, (size_t)len, f->fp) != (size_t)len)
			usage_die("cannot read face %s", path);
		if ((e = svf_open_mapped(&f->face, f->data, (size_t)len)) != SVF_OK)
			usage_die("%s: not a usable face (svf_err %d)", path, (int)e);
		return f;
	}
	need = svf_stream_tables_size(read_cb, f->fp, (uint32_t)len, &e);
	if (e != SVF_OK)
		usage_die("%s: not a usable face (svf_err %d)", path, (int)e);
	slots = vl_cache_slots((size_t)len);
	f->tables = malloc(need);
	f->cache = malloc(slots * (VL_CACHE_BLOCK + 8));
	if (!f->tables || !f->cache)
		oom_die(path);
	if ((e = svf_open_stream(&f->face, read_cb, f->fp, (uint32_t)len, f->tables, need, f->cache,
	                         slots * (VL_CACHE_BLOCK + 8), VL_CACHE_BLOCK)) != SVF_OK)
		usage_die("%s: cannot open (svf_err %d)", path, (int)e);
	return f;
}

/* Opens every face the table names, builds one chain a line, sizes the scratch for the largest. */
static void open_faces(const char *dir, int stream, size_t cache_bytes)
{
	int i, k;

	for (i = 0; i < table.nlines; i++) {
		const vl_line *l = &table.lines[i];
		svf_chain *c = &chains[i];
		size_t need;

		for (k = 0; k < l->nfaces; k++)
			chain_faces[i][k] = &open_face(dir, l->faces[k], stream)->face;
		c->faces = chain_faces[i];
		c->count = l->nfaces;
		c->scale_num = l->num;
		c->scale_den = l->den;
		need = svf_chain_scratch_bytes(c);
		if (need == 0 || need == (size_t)-1)
			usage_die("line %d: scale or chain refused", i + 1);
		if (need > scratch_len)
			scratch_len = need;
		if (cache_bytes) {
			chain_caches[i] = malloc(cache_bytes);
			if (!chain_caches[i] || svf_chain_cache(c, chain_caches[i], cache_bytes) != SVF_OK)
				usage_die("--syllable-cache=%lu: too small for one cell", (unsigned long)cache_bytes);
		}
	}
	scratch = malloc(scratch_len ? scratch_len : 1);
	if (!scratch)
		oom_die(NULL);
}

static void close_faces(void)
{
	int i;

	for (i = 0; i < nfiles; i++) {
		fclose(files[i].fp);
		free(files[i].data);
		free(files[i].tables);
		free(files[i].cache);
	}
	for (i = 0; i < VL_MAX_LINES; i++)
		free(chain_caches[i]);
	free(scratch);
}

/* After drawing: a face opened as a stream must have been read through its callback and a chain given a syllable cache
 * must hold it, so a silent fallback to mapped faces (or no cache) cannot pass the byte comparison unnoticed. */
static uint32_t total_reads(void)
{
	uint32_t n = 0;
	int i;

	for (i = 0; i < nfiles; i++)
		n += svf_stream_reads(&files[i].face);
	return n;
}

/* @p reads0: total_reads() before the draw; the draw itself must have read through the callback. */
static int check_modes(int stream, long cache_bytes, uint32_t reads0)
{
	int i;

	for (i = 0; stream && i < nfiles; i++)
		if (svf_stream_reads(&files[i].face) == 0) {
			fprintf(stderr, "svfsdl: --stream: face %s was never read through the stream\n", files[i].name);
			return 0;
		}
	if (stream && total_reads() <= reads0) {
		fprintf(stderr, "svfsdl: --stream: the draw read nothing through the stream\n");
		return 0;
	}
	for (i = 0; cache_bytes && i < table.nlines; i++)
		if (!chains[i].cache) {
			fprintf(stderr, "svfsdl: --syllable-cache: line %d has no cache\n", i + 1);
			return 0;
		}
	return 1;
}

/* Every row: w background pixels in the kind's byte order, then the padding bytes 0. */
static void clear_rows(uint8_t *p, int pitch, int w, int h, const fmt_desc *f)
{
	const vl_colour *bg = &table.colours[table.background];
	uint8_t px[4] = {0, 0, 0, 0};
	int x, y;

	if (f->pal == 2) {
		for (y = 0; y < h; y++)
			memset(p + (size_t)y * pitch, 0, (size_t)pitch);
		return;
	}
	if (f->pal == 1) {
		px[0] = bg->index_base;
	} else if (f->bytes == 2) {
		uint16_t v = f->kind == SVF_T_RGB555 ? bg->rgb555 : bg->rgb565;
		px[0] = (uint8_t)v, px[1] = (uint8_t)(v >> 8);
		if (SDL_BYTEORDER == SDL_BIG_ENDIAN)
			px[0] = (uint8_t)(v >> 8), px[1] = (uint8_t)v;
	} else {
		px[0] = (uint8_t)bg->rgb888, px[1] = (uint8_t)(bg->rgb888 >> 8), px[2] = (uint8_t)(bg->rgb888 >> 16);
		px[3] = f->alpha ? 0xFF : 0;
	}
	for (y = 0; y < h; y++) {
		uint8_t *row = p + (size_t)y * pitch;
		for (x = 0; x < w; x++)
			memcpy(row + (size_t)x * f->bytes, px, f->bytes);
		memset(row + (size_t)w * f->bytes, 0, (size_t)pitch - (size_t)w * f->bytes);
	}
}

/* Draws the first @p nlines table lines into the rows at @p p (pitch bytes apart); 0 or the failing svf_err. */
static int draw_lines(uint8_t *p, int pitch, int w, int h, const fmt_desc *f, int nlines)
{
	const vl_colour *bg = &table.colours[table.background];
	char text[1024];
	int i;

	for (i = 0; i < nlines; i++) {
		const vl_line *l = &table.lines[i];
		const vl_colour *c = &table.colours[l->colour];
		svf_target t;
		svf_err e;

		if ((e = svf_target_init(&t, f->kind, p, (size_t)pitch * h, (int16_t)w, (int16_t)h, (uint16_t)pitch)) != SVF_OK)
			return (int)e;
		t.fg565 = f->kind == SVF_T_RGB555 ? c->rgb555 : c->rgb565;
		t.bg565 = f->kind == SVF_T_RGB555 ? bg->rgb555 : bg->rgb565;
		t.fg888 = c->rgb888 | (f->alpha ? 0xFF000000u : 0);
		t.bg888 = bg->rgb888;
		if (f->rgb16 && SDL_BYTEORDER == SDL_BIG_ENDIAN)
			t.flags |= SVF_TF_RGB16_BIGENDIAN;
		if (f->pal)
			t.mono_threshold = (uint8_t)threshold;
		if (f->kind == SVF_T_INDEXED8) {
			t.index_base = c->index_base;
			t.index_levels = c->index_levels;
		} else if (f->kind == SVF_T_GRAY) {
			t.gray_bits = (uint8_t)f->bpp;
			if (lsb_first)
				t.flags |= SVF_TF_GRAY_LSB_FIRST;
		}
		vl_substitute(l->text, (unsigned)w, (unsigned)h, f->bpp, text, sizeof text);
		if ((e = svf_draw_utf8(&chains[i], text, strlen(text), l->x, l->baseline, &t, scratch, scratch_len)) != SVF_OK)
			return (int)e;
	}
	return 0;
}

static uint32_t fnv1a(const uint8_t *p, size_t n)
{
	uint32_t h = 2166136261u;

	while (n--)
		h = (h ^ *p++) * 16777619u;
	return h;
}

static int write_dump(const char *path, const uint8_t *p, int w, int h, int pitch, const fmt_desc *f)
{
	uint8_t hd[16] = {'S', 'V', 'F', 'S', 'D', 'L', '1', ' '};
	struct stat st;
	int existed = stat(path, &st) == 0; /* a file that was there before this run is never removed */
	FILE *fp = fopen(path, "wb");
	int ok;

	if (!fp)
		return 0;
	hd[8] = (uint8_t)w, hd[9] = (uint8_t)(w >> 8), hd[10] = (uint8_t)h, hd[11] = (uint8_t)(h >> 8);
	hd[12] = (uint8_t)pitch, hd[13] = (uint8_t)(pitch >> 8), hd[14] = (uint8_t)f->bpp;
	hd[15] = (uint8_t)((f->rgb16 && SDL_BYTEORDER == SDL_BIG_ENDIAN ? 1 : 0) | (f->pal ? 2 : 0) |
	                   (f->pal == 2 && lsb_first ? 4 : 0) | (f == &alpha_desc ? 8 : 0) | (svfsdl_major() - 2) << 4);
	ok = fwrite(hd, 1, 16, fp) == 16 && fwrite(p, 1, (size_t)pitch * h, fp) == (size_t)pitch * h;
	ok = fclose(fp) == 0 && ok;
	if (!ok && !existed)
		remove(path);
	return ok;
}

/* An output path that cannot be created is an input error (exit 2), found before SDL is started. */
static void probe_writable(const char *path)
{
	struct stat st;
	FILE *fp;
	int existed;

	if (!path)
		return;
	existed = stat(path, &st) == 0; /* an unreadable file exists too, and is never removed */
	fp = fopen(path, "ab");
	if (!fp)
		usage_die("cannot write %s", path);
	fclose(fp);
	if (!existed && remove(path) != 0)
		usage_die("cannot remove the probe file %s", path);
}

/* A whole decimal number up to @p max, else -1. */
static long parse_num(const char *s, long max)
{
	char *end;
	long v;

	if (!*s || *s < '0' || *s > '9')
		return -1;
	v = strtol(s, &end, 10);
	return *end || v > max ? -1 : v;
}

/* The palette of an index8 or gray surface: index8 the lines file's ramps (vl_palette), gray 2^bits levels from the
 * background (k = 0) to white, entry k = (bg * (n - k) + 255 * k + n / 2) / n per channel, n = 2^bits - 1. */
static int set_palette(SDL_Surface *s, const fmt_desc *f)
{
	SDL_Color col[256];
	uint8_t pal[256][4];
	unsigned bg = table.colours[table.background].rgb888, n = (1u << f->bpp) - 1, k, c;
	int count = f->pal == 1 ? 256 : (int)n + 1;

	vl_palette(&table, 8, pal);
	for (k = 0; k < 256; k++) {
		col[k].r = pal[k][2], col[k].g = pal[k][1], col[k].b = pal[k][0], col[k].a = 255;
		if (f->pal == 2 && k <= n) {
			uint8_t v[3];
			for (c = 0; c < 3; c++)
				v[c] = (uint8_t)((((bg >> (16 - 8 * c)) & 255) * (n - k) + 255 * k + n / 2) / n);
			col[k].r = v[0], col[k].g = v[1], col[k].b = v[2];
		}
	}
	return SVFSDL_OK(SDL_SetPaletteColors(svfsdl_surface_palette(s), col, 0, count));
}

/* The BGRA32 surface rows from the GRAY8 coverage @p cov (pitch w): bytes (b, g, r, coverage) of the first line's colour. */
static void expand_alpha(uint8_t *dst, int pitch, const uint8_t *cov, int w, int h)
{
	uint32_t c = table.colours[table.lines[0].colour].rgb888;
	int x, y;

	for (y = 0; y < h; y++) {
		for (x = 0; x < w; x++) {
			uint8_t *q = dst + (size_t)y * pitch + (size_t)x * 4;
			q[0] = (uint8_t)c, q[1] = (uint8_t)(c >> 8), q[2] = (uint8_t)(c >> 16), q[3] = cov[(size_t)y * w + x];
		}
		memset(dst + (size_t)y * pitch + (size_t)w * 4, 0, (size_t)pitch - (size_t)w * 4);
	}
}

/* An opaque left-to-right gradient surface the alpha demo is blended over. */
static SDL_Surface *make_gradient(int w, int h)
{
	SDL_Surface *g = svfsdl_create_surface(w, h, SDL_PIXELFORMAT_BGRA32);
	int x, y;

	if (!g)
		return NULL;
	SDL_SetSurfaceBlendMode(g, SDL_BLENDMODE_NONE);
	if (!SVFSDL_OK(SDL_LockSurface(g))) {
		svfsdl_destroy_surface(g);
		return NULL;
	}
	for (y = 0; y < h; y++)
		for (x = 0; x < w; x++) {
			uint8_t *q = (uint8_t *)g->pixels + (size_t)y * g->pitch + (size_t)x * 4;
			uint8_t v = (uint8_t)(w > 1 ? x * 255 / (w - 1) : 0);
			q[0] = v, q[1] = v / 2, q[2] = (uint8_t)(255 - v), q[3] = 255;
		}
	SDL_UnlockSurface(g);
	return g;
}

int main(int argc, char **argv)
{
	const char *format = "xrgb8888", *present = "surface", *faces = "svf/dos", *lines = DEFAULT_LINES;
	const char *dump = NULL, *shot = NULL;
	long wl = 640, hl = 480, frames = -1, cache_bytes = 0;
	int stream = 0, i, w, h, pitch, direct, use_tex, frame_no;
	const fmt_desc *f = NULL;
	fmt_desc gdesc;
	long gray_bits = 8;
	int gray_given = 0, alpha = 0, dpitch = 0, need;
	uint8_t *abuf = NULL;
	const uint8_t *dpix = NULL;
	uint32_t reads0;
	SDL_Surface *grad = NULL;
	SDL_Texture *gtex = NULL;
	char covpitch[32] = "";
	char err[128];
	int line_no, pitch_est;
	FILE *fp;
	SDL_Window *win = NULL;
	SDL_Renderer *ren = NULL;
	SDL_Texture *tex = NULL;
	SDL_Surface *back = NULL;
	uint8_t *pix;
	uint64_t t0;
	uint32_t sum;
	unsigned long long us;
	svfsdl_format wfmt;
	int vx, vy, vz, rc = 0, locked = 0;
	char title[64];

	for (i = 1; i < argc; i++) {
		const char *a = argv[i];
		const char *val = i + 1 < argc ? argv[i + 1] : NULL;

		if (!strcmp(a, "--stream")) {
			stream = 1;
		} else if (!strcmp(a, "--lsb-first")) {
			lsb_first = 1;
		} else if (!strcmp(a, "--alpha-demo")) {
			alpha = 1;
		} else if (!strncmp(a, "--syllable-cache=", 17)) {
			cache_bytes = parse_num(a + 17, 1 << 26);
			if (cache_bytes < 0)
				usage_die("%s: not a byte count (decimal, at most 67108864)", a);
		} else if (!strcmp(a, "--format") || !strcmp(a, "--size") || !strcmp(a, "--present") || !strcmp(a, "--faces") ||
		           !strcmp(a, "--lines") || !strcmp(a, "--dump") || !strcmp(a, "--gray-bits") || !strcmp(a, "--threshold") || !strcmp(a, "--shot") || !strcmp(a, "--frames")) {
			if (!val)
				usage_die("%s needs a value", a);
			i++;
			if (!strcmp(a, "--format")) {
				format = val;
			} else if (!strcmp(a, "--size")) {
				char *x;
				wl = strtol(val, &x, 10);
				if (x == val || *x != 'x' || (hl = parse_num(x + 1, 1L << 30)) < 0 || wl <= 0 || hl <= 0)
					usage_die("--size %s: expected WxH", val);
			} else if (!strcmp(a, "--present")) {
				present = val;
			} else if (!strcmp(a, "--gray-bits")) {
				gray_bits = parse_num(val, 8);
				gray_given = 1;
				if (gray_bits != 1 && gray_bits != 2 && gray_bits != 4 && gray_bits != 8)
					usage_die("--gray-bits %s: expected 1, 2, 4 or 8", val);
			} else if (!strcmp(a, "--threshold")) {
				long t = parse_num(val, 255);
				if (t < 0)
					usage_die("--threshold %s: expected 0..255", val);
				threshold = (unsigned)t;
			} else if (!strcmp(a, "--faces")) {
				faces = val;
			} else if (!strcmp(a, "--lines")) {
				lines = val;
			} else if (!strcmp(a, "--dump")) {
				dump = val;
			} else if (!strcmp(a, "--shot")) {
				shot = val;
			} else if ((frames = parse_num(val, 1L << 30)) < 0) {
				usage_die("--frames %s: expected a number", val);
			}
		} else {
			usage_die("unknown option %s", a);
		}
	}
	for (i = 0; i < (int)(sizeof formats / sizeof formats[0]); i++)
		if (!strcmp(format, formats[i].name))
			f = &formats[i];
	if (!f) /* a name is validated even under --alpha-demo, which then ignores its effect */
		usage_die("--format %s: expected xrgb8888, argb8888, rgb565, rgb555, bgr24, index8 or gray", format);
	if (gray_given && !alpha && strcmp(format, "gray")) /* --alpha-demo ignores --gray-bits, whatever the order */
		usage_die("--gray-bits needs --format gray");
	if (f && f->pal == 2) { /* gray: the format follows the bits and the bit order */
		gdesc = *f;
		gdesc.bpp = (unsigned)gray_bits;
		gdesc.fmt = gray_formats[gray_bits == 1 ? 0 : gray_bits == 2 ? 1 : gray_bits == 4 ? 2 : 3][lsb_first ? 1 : 0];
		f = &gdesc;
	}
	if (alpha)
		f = &alpha_desc;
	if (strcmp(present, "surface") && strcmp(present, "texture") && strcmp(present, "texture-direct"))
		usage_die("--present %s: expected surface, texture or texture-direct", present);
	direct = !strcmp(present, "texture-direct");
	use_tex = direct || !strcmp(present, "texture");
	if (alpha && direct)
		usage_die("--present texture-direct cannot be used with --alpha-demo (the texture is not the proven buffer)");
	if (direct && f->pal)
		usage_die("--present texture-direct cannot be used with --format %s (a texture has no palette)", f->name);
	if (direct && dump)
		usage_die("--dump cannot be used with --present texture-direct (the texture is not the proven buffer)");
	if (shot && use_tex)
		usage_die("--shot needs --present surface");
	if (wl > 32767 || hl > 32767)
		usage_die("--size %ldx%ld: width or height > 32767 (svf_target is 16 bits)", wl, hl);
	w = (int)wl, h = (int)hl;
	need = (int)(((long)w * (long)f->bpp + 7) / 8); /* bytes of one row of the drawn buffer */
	pitch_est = (int)(((long)need + 3) & ~3L);
	if (need > 65535 || pitch_est > 65535)
		usage_die("--size %dx%d: pitch %ld > 65535 (stride is 16 bits)", w, h, ((long)need + 3) & ~3L);
	if (alpha)
		need = w * 4; /* the BGRA32 surface; the GRAY8 buffer has pitch w */
	if (frames < 0)
		frames = dump || shot ? 1 : 0;

	probe_writable(dump);
	probe_writable(shot);
	fp = fopen(lines, "rb");
	if (!fp)
		usage_die("cannot open lines file %s", lines);
	if (vl_parse(fp, &table, err, &line_no) != 0)
		usage_die("%s:%d: %s", lines, line_no, err);
	fclose(fp);
	if (alpha && table.nlines == 0)
		usage_die("%s has no text line for --alpha-demo", lines);
	if (alpha)
		table.nlines = 1; /* the demo opens and draws the first line only */
	open_faces(faces, stream, (size_t)cache_bytes);

	SDL_SetMainReady();
	if (!SVFSDL_OK(SDL_Init(SDL_INIT_VIDEO)))
		run_die("SDL_Init");
	svfsdl_version(&vx, &vy, &vz);
	snprintf(title, sizeof title, "svfsdl SDL %d.%d.%d", vx, vy, vz);
	win = svfsdl_create_window(title, w, h);
	if (!win)
		run_die("create window");
	wfmt = SDL_GetWindowPixelFormat(win);

	if (use_tex) {
		ren = svfsdl_create_renderer(win);
		tex = ren && !f->pal ? svfsdl_create_texture(ren, f->fmt, w, h) : NULL;
		if (!ren || (!tex && !f->pal))
			run_die("create renderer/texture");
		if (tex) /* an ARGB texture is copied, not blended, except the alpha demo's */
			SDL_SetTextureBlendMode(tex, alpha ? SDL_BLENDMODE_BLEND : SDL_BLENDMODE_NONE);
	}
	if (direct) {
		void *p;
		if (!SVFSDL_OK(SDL_LockTexture(tex, NULL, &p, &pitch)))
			run_die("lock texture");
		pix = p;
		locked = 1;
	} else {
		back = svfsdl_create_surface(w, h, f->fmt);
		if (!back)
			run_die("create surface");
		SDL_SetSurfaceBlendMode(back, alpha ? SDL_BLENDMODE_BLEND : SDL_BLENDMODE_NONE); /* ARGB back buffer: the blit copies */
		if (svfsdl_surface_format(back) != f->fmt) {
			fprintf(stderr, "svfsdl: the surface got %s, not %s\n", SDL_GetPixelFormatName(svfsdl_surface_format(back)),
			        SDL_GetPixelFormatName(f->fmt));
			rc = 1;
			goto done;
		}
		if (f->pal && !set_palette(back, f))
			run_die("set palette");
		if (!SVFSDL_OK(SDL_LockSurface(back)))
			run_die("lock surface");
		locked = 1;
		pix = back->pixels;
		pitch = back->pitch;
	}
	if (pitch < need || (!alpha && pitch > 65535)) {
		fprintf(stderr, "svfsdl: the pitch SDL gave (%d) does not fit the target\n", pitch);
		rc = 1;
		goto done;
	}

	t0 = SDL_GetPerformanceCounter();
	reads0 = total_reads();
	if (alpha) {
		abuf = calloc((size_t)w * h, 1);
		if (!abuf) {
			fprintf(stderr, "svfsdl: out of memory\n");
			rc = 1;
			goto done;
		}
		i = draw_lines(abuf, w, w, h, f, 1);
		expand_alpha(pix, pitch, abuf, w, h);
		snprintf(covpitch, sizeof covpitch, " covpitch %d", w);
		dpix = abuf, dpitch = w;
	} else {
		clear_rows(pix, pitch, w, h, f);
		i = draw_lines(pix, pitch, w, h, f, table.nlines);
		dpix = pix, dpitch = pitch;
	}
	us = (unsigned long long)((SDL_GetPerformanceCounter() - t0) * 1000000u / SDL_GetPerformanceFrequency());
	if (i) {
		fprintf(stderr, "svfsdl: drawing failed (svf_err %d)\n", i);
		rc = 1;
		goto done;
	}
	if (!check_modes(stream, cache_bytes, reads0)) {
		rc = 1;
		goto done;
	}
	sum = fnv1a(dpix, (size_t)dpitch * h);
	if (direct)
		SDL_UnlockTexture(tex);
	else
		SDL_UnlockSurface(back);
	locked = 0;

	if (alpha && !(grad = make_gradient(w, h)))
		run_die("create gradient");
	if (alpha && use_tex && !(gtex = SDL_CreateTextureFromSurface(ren, grad)))
		run_die("create gradient texture");
	if (f->pal && use_tex) { /* a palettised surface is converted once, here */
		tex = SDL_CreateTextureFromSurface(ren, back);
		if (!tex)
			run_die("create texture from surface");
		SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_NONE);
	}
	for (frame_no = 0; frames == 0 || frame_no < frames; frame_no++) {
		SDL_Event ev;
		int quit = 0;

		if (use_tex) {
			if (!direct && !f->pal && !SVFSDL_OK(SDL_UpdateTexture(tex, NULL, back->pixels, back->pitch)))
				run_die("update texture");
			if (!SVFSDL_OK(SDL_RenderClear(ren)) || (gtex && !svfsdl_render_copy(ren, gtex)) || !svfsdl_render_copy(ren, tex))
				run_die("render");
			SDL_RenderPresent(ren);
		} else {
			SDL_Surface *ws = SDL_GetWindowSurface(win);
			if (!ws || (grad && !SVFSDL_OK(SDL_BlitSurface(grad, NULL, ws, NULL))) ||
			    !SVFSDL_OK(SDL_BlitSurface(back, NULL, ws, NULL)) || !SVFSDL_OK(SDL_UpdateWindowSurface(win)))
				run_die("present surface");
			if (frame_no == 0 && shot && !SVFSDL_OK(SDL_SaveBMP(ws, shot)))
				run_die("save shot");
		}
		if (frame_no == 0 && dump) { /* after present and shot */
			if (alpha) {
				i = write_dump(dump, abuf, w, h, w, f);
			} else {
				if (!SVFSDL_OK(SDL_LockSurface(back)))
					run_die("lock surface");
				i = write_dump(dump, back->pixels, w, h, pitch, f);
				SDL_UnlockSurface(back);
			}
			if (!i) {
				fprintf(stderr, "svfsdl: cannot write %s\n", dump);
				rc = 1;
				goto done;
			}
		}
		if (frame_no == 0 && frames == 0 && (dump || shot)) /* until closed would hang a dump or shot run: stop here */
			break;
		while (SDL_PollEvent(&ev))
			if (ev.type == SVFSDL_EVENT_QUIT || ev.type == SVFSDL_EVENT_KEY_DOWN)
				quit = 1;
		if (quit)
			break;
		if (frames == 0)
			SDL_Delay(16);
	}

	printf("svfsdl: SDL %d.%d.%d driver %s window %s back %s pitch %d%s draw %llu us sum=%08x\n", vx, vy, vz,
	       SDL_GetCurrentVideoDriver(), SDL_GetPixelFormatName(wfmt), SDL_GetPixelFormatName(f->fmt), pitch, covpitch, us,
	       (unsigned)sum);
	fflush(stdout);

done:
	if (locked) {
		if (direct)
			SDL_UnlockTexture(tex);
		else
			SDL_UnlockSurface(back);
	}
	if (gtex)
		SDL_DestroyTexture(gtex);
	if (tex)
		SDL_DestroyTexture(tex);
	if (ren)
		SDL_DestroyRenderer(ren);
	if (back)
		svfsdl_destroy_surface(back);
	if (grad)
		svfsdl_destroy_surface(grad);
	free(abuf);
	SDL_DestroyWindow(win);
	SDL_Quit();
	close_faces();
	return rc;
}
