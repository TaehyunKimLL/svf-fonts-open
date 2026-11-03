/* svfvesa.c - draws vesa-lines.txt with the SVF renderer into a VBE 2.0 linear framebuffer mode (DJGPP).
 *
 *   SVFVESA.EXE                    640 x 480 at 16, 8 and 32 bpp in turn, a key after each (a missing depth is skipped)
 *   SVFVESA.EXE W H BPP [DUMP]     one mode (BPP 8, 15, 16, 24 or 32), a key; with DUMP the back buffer is written to
 *                                  the file DUMP first
 *
 * Run it in the directory holding vesa-lines.txt (VESALINE.TXT on a DOS without long file names) and the faces it names (streamed from their files with 1 KB block
 * caches, as svfdemo.c). The text is drawn into a system RAM back buffer of the mode's kind (INDEXED8, RGB555, RGB565,
 * RGB888 or XRGB8888) and the dirty rows are copied to the LFB through a descriptor mapped over it (movedata; no
 * near pointers). The mode is chosen by geometry and channel layout through vbe_select.c, never by number. SUM.TXT
 * (closed before the key is awaited) and the report on stdout carry
 *   sum=<FNV-1a of the back buffer> dac=<6|8> mode=0x<n> WxH BPPbpp pitch=<p> bits=<b>
 * and the flush prints `flush_<W>x<H>_<BPP> rows=<r> us=<t>`. The stdout lines are printed after text mode is back
 * (a line printed in a graphics mode would be drawn on the picture). Text mode is restored on every exit path.
 */
#include "svf.h"
#include "vbe_select.h"
#include "vesa_lines.h"

#include <conio.h>         /* getch */
#include <dpmi.h>          /* __dpmi_* */
#include <fcntl.h>         /* open */
#include <go32.h>          /* __tb, _my_ds, _go32_info_block */
#include <pc.h>            /* outportb */
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/movedata.h>  /* movedata, dosmemget, dosmemput */
#include <time.h>          /* uclock */
#include <unistd.h>        /* lseek, read, close */

#define BLOCK VL_CACHE_BLOCK /* face cache block: the file is read in aligned 1 KB blocks */
#define MAX_FACE_FILES (VL_MAX_LINES * VL_MAX_FACES) /* every line may name 4 faces of its own */
#define LINES_FILE "vesa-lines.txt"
#define LINES_FILE_8_3 "VESALINE.TXT" /* the name for a DOS without long file names (the base name has 10 characters) */

typedef struct {
	char name[13];
	int fd;
	svf_face face;
	uint8_t *tables, *cache;
} face_file;

static vl_table table;
static const char *lines_name = LINES_FILE; /* the name that was opened */
static face_file files[MAX_FACE_FILES];
static int nfiles;
static uint8_t *scratch;
static size_t scratch_len;

/* The state text mode must be restored from (all of it undone by restore()). */
static int mode_set, have_sel, have_map;
static int lfb_sel;
static __dpmi_meminfo lfb_map;

/* The stdout report: collected while a graphics mode is up, printed after text mode is back. */
static char report[2048];
static size_t report_len;

static void say(const char *fmt, ...)
{
	va_list ap;
	int n;

	if (report_len >= sizeof report - 1)
		return;
	va_start(ap, fmt);
	n = vsnprintf(report + report_len, sizeof report - report_len, fmt, ap);
	va_end(ap);
	if (n > 0)
		report_len += (size_t)n < sizeof report - report_len ? (size_t)n : sizeof report - report_len - 1;
}

static void print_report(void)
{
	fwrite(report, 1, report_len, stdout);
	fflush(stdout);
	report_len = 0;
	report[0] = 0;
}

static void video_mode(int mode)
{
	__dpmi_regs r;

	memset(&r, 0, sizeof r);
	r.x.ax = (unsigned short)mode;
	__dpmi_int(0x10, &r);
}

/* Undoes the mode, the descriptor and the mapping, in that order; safe to call twice. */
static void restore(void)
{
	if (mode_set) {
		video_mode(0x03);
		mode_set = 0;
	}
	if (have_sel) {
		__dpmi_free_ldt_descriptor(lfb_sel);
		have_sel = 0;
	}
	if (have_map) {
		__dpmi_free_physical_address_mapping(&lfb_map); /* absent from some DPMI 0.9 hosts: ignored */
		have_map = 0;
	}
}

static void on_signal(int sig)
{
	(void)sig;
	exit(2); /* atexit: restore() */
}

static void die(const char *fmt, ...)
{
	va_list ap;
	char msg[256];

	va_start(ap, fmt);
	vsnprintf(msg, sizeof msg, fmt, ap);
	va_end(ap);
	restore();
	print_report();
	printf("svfvesa: %s\n", msg);
	fflush(stdout);
	exit(1);
}

/* ---- faces ---- */

static long read_file(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	int fd = *(int *)ctx;

	if (lseek(fd, (off_t)offset, SEEK_SET) != (off_t)offset)
		return -1;
	return (long)read(fd, dst, len);
}

/* The face file called @p name (opened once, streamed, kept open for the whole run). */
static face_file *open_face(const char *name)
{
	face_file *f;
	long len;
	size_t need, slots;
	svf_err e;
	int i;

	for (i = 0; i < nfiles; i++)
		if (strcmp(files[i].name, name) == 0)
			return &files[i];
	if (nfiles == MAX_FACE_FILES)
		die("more than %d different faces", MAX_FACE_FILES);
	f = &files[nfiles];
	memset(f, 0, sizeof *f);
	strcpy(f->name, name);
	f->fd = open(name, O_RDONLY | O_BINARY);
	if (f->fd < 0 || (len = lseek(f->fd, 0, SEEK_END)) <= 0)
		die("cannot open %s", name);
	need = svf_stream_tables_size(read_file, &f->fd, (uint32_t)len, &e);
	if (e != SVF_OK)
		die("%s: not a usable face (svf_err %d)", name, (int)e);
	slots = vl_cache_slots((size_t)len); /* the whole file when small (2 slots at least), else 64 blocks */
	f->tables = malloc(need);
	f->cache = malloc(slots * (BLOCK + 8));
	if (!f->tables || !f->cache)
		die("out of memory for %s", name);
	if ((e = svf_open_stream(&f->face, read_file, &f->fd, (uint32_t)len, f->tables, need, f->cache,
	                         slots * (BLOCK + 8), BLOCK)) != SVF_OK)
		die("%s: cannot open (svf_err %d)", name, (int)e);
	nfiles++;
	return f;
}

/* Opens every face the table names and sizes the scratch buffer for the largest line. */
static void open_faces(void)
{
	int i, k;

	for (i = 0; i < table.nlines; i++) {
		const vl_line *l = &table.lines[i];
		svf_face *fs[VL_MAX_FACES];
		svf_chain c;
		size_t need;

		for (k = 0; k < l->nfaces; k++)
			fs[k] = &open_face(l->faces[k])->face;
		memset(&c, 0, sizeof c);
		c.faces = fs;
		c.count = l->nfaces;
		c.scale_num = l->num;
		c.scale_den = l->den;
		need = svf_chain_scratch_bytes(&c);
		if (need == 0 || need == (size_t)-1)
			die("line %d: scale or chain refused", i + 1);
		if (need > scratch_len)
			scratch_len = need;
	}
	scratch = malloc(scratch_len ? scratch_len : 1);
	if (!scratch)
		die("out of memory");
}

/* ---- VBE ---- */

static int read_word(void *ctx, uint32_t seg, uint32_t off, uint16_t *out)
{
	uint32_t lin = seg * 16u + off;
	uint8_t b[2];

	(void)ctx;
	if (lin > 0x100000u - 2u)
		return -1;
	dosmemget(lin, 2, b);
	*out = (uint16_t)(b[0] | (b[1] << 8));
	return 0;
}

/* INT 10h AX=@p ax with ES:DI = the transfer buffer, CX/BX/DX as given; returns the AX it came back with (0 when the
 * interrupt itself failed). */
static unsigned vbe_call(unsigned ax, unsigned bx, unsigned cx, unsigned dx, __dpmi_regs *out)
{
	__dpmi_regs r;

	memset(&r, 0, sizeof r);
	r.x.ax = (unsigned short)ax;
	r.x.bx = (unsigned short)bx;
	r.x.cx = (unsigned short)cx;
	r.x.dx = (unsigned short)dx;
	r.x.es = (unsigned short)(__tb >> 4);
	r.x.di = (unsigned short)(__tb & 15);
	if (__dpmi_int(0x10, &r) == -1)
		r.x.ax = 0;
	if (out)
		*out = r;
	return r.x.ax;
}

static void vbe_check(unsigned ax, unsigned fn, const char *what)
{
	if (vbe_status(ax, fn) != VBE_OK)
		die("VBE %s (%04Xh) failed: AX=%04X", what, fn, ax);
}

static uint16_t modes[257];
static unsigned vbe_version;

/* 4F00h: the controller block, the version and the mode list copied out of DOS memory. */
static void vbe_init(void)
{
	static const uint8_t zero[512];
	uint8_t blk[512];
	int n, cut;

	if (_go32_info_block.size_of_transfer_buffer < 1024)
		die("the DOS transfer buffer is too small (%lu bytes)", (unsigned long)_go32_info_block.size_of_transfer_buffer);
	dosmemput(zero, sizeof zero, __tb);
	dosmemput("VBE2", 4, __tb);
	vbe_check(vbe_call(0x4F00, 0, 0, 0, NULL), 0x4F00, "controller information");
	dosmemget(__tb, sizeof blk, blk);
	if (memcmp(blk, "VESA", 4) != 0)
		die("no VESA signature in the controller block");
	vbe_version = (unsigned)(blk[4] | (blk[5] << 8));
	if (vbe_version < 0x200)
		die("VBE %u.%u found, 2.0 is needed", vbe_version >> 8, vbe_version & 255);
	n = vbe_modes_copy_cut(blk, read_word, NULL, modes, &cut);
	if (n < 0)
		die("mode list: %s", vbe_reason(n));
	if (n == 0)
		die("the mode list is empty");
	if (cut != VBE_CUT_NONE)
		printf("svfvesa: the mode list was cut (%s)\n", cut == VBE_CUT_256 ? "256 entries, no terminator" :
		       cut == VBE_CUT_1MB ? "it reaches 1 MiB" : "a read failed");
}

/* The first listed mode that is a w x h LFB mode of logical depth bpp; 0 and a message in *why when none is. */
static int find_mode(unsigned w, unsigned h, unsigned bpp, unsigned *number, vbe_mode *vm)
{
	static const uint8_t zero[256];
	uint8_t info[256];
	int i, found = 0;

	for (i = 0; modes[i] != 0xFFFFu; i++) {
		vbe_mode m;
		int why;

		dosmemput(zero, sizeof zero, __tb);
		vbe_check(vbe_call(0x4F01, 0, modes[i], 0, NULL), 0x4F01, "mode information");
		dosmemget(__tb, sizeof info, info);
		why = vbe_mode_accept(info, vbe_version, w, h, bpp, &m);
		if (why == VBE_OK) {
			*number = modes[i];
			*vm = m;
			found = 1;
			break;
		}
		if (why == VBE_R_LAYOUT || why == VBE_R_PITCH || why == VBE_R_TOO_BIG)
			printf("svfvesa: mode 0x%X skipped: %s\n", modes[i], vbe_reason(why)); /* text mode: print now */
	}
	return found;
}

static void map_lfb(const vbe_mode *vm)
{
	memset(&lfb_map, 0, sizeof lfb_map);
	lfb_map.address = vm->phys_base;
	lfb_map.size = vm->map_size;
	if (__dpmi_physical_address_mapping(&lfb_map) != 0)
		die("cannot map the framebuffer at 0x%lX (%lu bytes)", (unsigned long)vm->phys_base,
		    (unsigned long)vm->map_size);
	have_map = 1;
	lfb_sel = __dpmi_allocate_ldt_descriptors(1);
	if (lfb_sel < 0)
		die("no descriptor for the framebuffer");
	have_sel = 1;
	if (__dpmi_set_segment_base_address(lfb_sel, lfb_map.address) != 0 ||
	    __dpmi_set_segment_limit(lfb_sel, vm->map_size - 1) != 0)
		die("cannot set the framebuffer descriptor");
}

/* 4F08h (an 8-bit DAC if granted) and 4F09h (the palette, B G R pad); returns the DAC width in use. A failed call is
 * not fatal: when 4F09h fails the palette goes through the VGA ports, and an 8-bit DAC that was granted is put back to
 * 6 bits first (4F08h BH=6); if that fails too the 8-bit table is written to the ports (vbe_palette_plan decides). */
static unsigned set_palette(void)
{
	static uint8_t pal[256][4];
	__dpmi_regs r;
	unsigned dac;
	int granted8, pal_ok, reset_ok = 0, i;

	granted8 = vbe_status(vbe_call(0x4F08, 0x0800, 0, 0, &r), 0x4F08) == VBE_OK && r.h.bh == 8;
	vl_palette(&table, granted8 ? 8 : 6, pal);
	dosmemput(pal, sizeof pal, __tb);
	pal_ok = vbe_status(vbe_call(0x4F09, 0x0000, 256, 0, NULL), 0x4F09) == VBE_OK;
	if (vbe_palette_needs_reset(granted8, pal_ok))
		reset_ok = vbe_status(vbe_call(0x4F08, 0x0600, 0, 0, &r), 0x4F08) == VBE_OK && r.h.bh == 6;
	if (vbe_palette_plan(granted8, pal_ok, reset_ok, &dac) == VBE_PAL_BIOS)
		return dac;
	vl_palette(&table, dac, pal);
	outportb(0x3C8, 0);
	for (i = 0; i < 256; i++) {
		outportb(0x3C9, pal[i][2]);
		outportb(0x3C9, pal[i][1]);
		outportb(0x3C9, pal[i][0]);
	}
	return dac;
}

/* ---- drawing ---- */

static uint32_t fnv1a(const uint8_t *p, size_t n)
{
	uint32_t h = 2166136261u;

	while (n--)
		h = (h ^ *p++) * 16777619u;
	return h;
}

static void fill_background(uint8_t *buf, const vbe_mode *vm, unsigned w, unsigned h)
{
	const vl_colour *bg = &table.colours[table.background];
	uint8_t px[4];
	size_t i, n = vm->bytes_pp, count = (size_t)w * h;

	switch (vm->depth) {
	case 8: px[0] = bg->index_base; break;
	case 15: px[0] = (uint8_t)bg->rgb555; px[1] = (uint8_t)(bg->rgb555 >> 8); break;
	case 16: px[0] = (uint8_t)bg->rgb565; px[1] = (uint8_t)(bg->rgb565 >> 8); break;
	default:
		px[0] = (uint8_t)bg->rgb888; px[1] = (uint8_t)(bg->rgb888 >> 8); px[2] = (uint8_t)(bg->rgb888 >> 16);
		px[3] = 0; /* the X byte is never set from the file */
	}
	for (i = 0; i < count; i++)
		memcpy(buf + i * n, px, n);
}

static svf_target_kind kind_of(unsigned depth)
{
	switch (depth) {
	case 8: return SVF_T_INDEXED8;
	case 15: return SVF_T_RGB555;
	case 16: return SVF_T_RGB565;
	case 24: return SVF_T_RGB888;
	default: return SVF_T_XRGB8888;
	}
}

/* Draws every table line into buf (rows pitch bytes apart) and marks the rows each one reaches in dirty[]. */
static void draw_lines(uint8_t *buf, const vbe_mode *vm, unsigned w, unsigned h, uint8_t *dirty)
{
	const vl_colour *bg = &table.colours[table.background];
	char text[1024];
	int i, k;

	for (i = 0; i < table.nlines; i++) {
		const vl_line *l = &table.lines[i];
		const vl_colour *c = &table.colours[l->colour];
		svf_face *fs[VL_MAX_FACES];
		svf_chain chain;
		svf_target t;
		svf_extent ext;
		svf_err e;
		long y0, y1, y;
		size_t n;

		for (k = 0; k < l->nfaces; k++)
			fs[k] = &open_face(l->faces[k])->face;
		memset(&chain, 0, sizeof chain);
		chain.faces = fs;
		chain.count = l->nfaces;
		chain.scale_num = l->num;
		chain.scale_den = l->den;
		if (svf_target_init(&t, kind_of(vm->depth), buf, vm->buf_size, (int16_t)w, (int16_t)h,
		                    (uint16_t)(w * vm->bytes_pp)) != SVF_OK)
			die("the back buffer target is refused");
		t.fg565 = vm->depth == 15 ? c->rgb555 : c->rgb565;
		t.bg565 = vm->depth == 15 ? bg->rgb555 : bg->rgb565;
		t.fg888 = c->rgb888; /* bits 31..24 (the X byte) stay 0 */
		t.bg888 = bg->rgb888;
		t.index_base = c->index_base;
		t.index_levels = c->index_levels;
		vl_substitute(l->text, w, h, vm->depth, text, sizeof text);
		n = strlen(text);
		if ((e = svf_measure_utf8(&chain, text, n, &ext)) != SVF_OK ||
		    (e = svf_draw_utf8(&chain, text, n, l->x, l->baseline, &t, scratch, scratch_len)) != SVF_OK)
			die("line %d: drawing failed (svf_err %d)", i + 1, (int)e);
		y0 = (long)l->baseline - ext.ascent;
		y1 = (long)l->baseline + ext.descent;
		if (y0 < 0)
			y0 = 0;
		if (y1 > (long)h)
			y1 = (long)h;
		for (y = y0; y < y1; y++)
			dirty[y] = 1;
	}
}

/* Copies the runs of dirty rows to the LFB; returns the rows copied. Every copy is checked against the LFB size. */
static unsigned flush(const uint8_t *buf, const vbe_mode *vm, unsigned w, unsigned h, uint8_t *dirty)
{
	size_t row = (size_t)w * vm->bytes_pp;
	unsigned y = 0, copied = 0;

	while (y < h) {
		unsigned r, end;

		if (!dirty[y]) {
			y++;
			continue;
		}
		for (end = y; end < h && dirty[end]; end++)
			;
		if (row == vm->pitch) {
			r = end - y;
			if (!vbe_copy_ok(vm->lfb_size, vm->pitch, y, r))
				die("flush refused: rows %u..%u leave the framebuffer", y, end - 1);
			movedata(_my_ds(), (unsigned)(buf + (size_t)y * row), (unsigned)lfb_sel, y * vm->pitch, r * row);
		} else {
			unsigned yy;

			for (yy = y; yy < end; yy++) {
				if (!vbe_copy_ok(vm->lfb_size, vm->pitch, yy, 1))
					die("flush refused: row %u leaves the framebuffer", yy);
				movedata(_my_ds(), (unsigned)(buf + (size_t)yy * row), (unsigned)lfb_sel, yy * vm->pitch, row);
			}
		}
		copied += end - y;
		memset(dirty + y, 0, end - y);
		y = end;
	}
	return copied;
}

/* One mode: select, map, set, palette, draw, flush, report, wait for a key, restore. 0 ok, 1 no such mode. */
static int run_mode(unsigned w, unsigned h, unsigned bpp, const char *dump)
{
	vbe_mode vm;
	unsigned number, dac = 8, rows;
	uint8_t *buf, *dirty;
	uclock_t t0, t1;
	uint32_t sum;
	char line[200];
	FILE *fp;

	if (!find_mode(w, h, bpp, &number, &vm)) {
		printf("svfvesa: no %ux%u %u bpp linear framebuffer mode\n", w, h, bpp);
		fflush(stdout);
		return 1;
	}
	buf = malloc(vm.buf_size);
	dirty = malloc(h);
	if (!buf || !dirty)
		die("out of memory for the %lu byte back buffer", (unsigned long)vm.buf_size);
	memset(dirty, 1, h); /* the clear marks every row once */
	fill_background(buf, &vm, w, h);
	map_lfb(&vm);
	mode_set = 1; /* before the call: a failed 4F02h may still have left the display in a graphics state */
	vbe_check(vbe_call(0x4F02, number | 0x4000, 0, 0, NULL), 0x4F02, "set mode");
	if (vm.depth == 8)
		dac = set_palette();
	draw_lines(buf, &vm, w, h, dirty);
	t0 = uclock();
	rows = flush(buf, &vm, w, h, dirty);
	t1 = uclock();
	say("flush_%ux%u_%u rows=%u us=%lu\n", w, h, bpp, rows,
	    (unsigned long)((unsigned long long)(t1 - t0) * 1000000ull / UCLOCKS_PER_SEC));
	sum = fnv1a(buf, vm.buf_size);
	if (dump) {
		if (!(fp = fopen(dump, "wb")) || fwrite(buf, 1, vm.buf_size, fp) != vm.buf_size || fclose(fp) != 0)
			die("cannot write %s", dump);
	}
	snprintf(line, sizeof line, "sum=%08lx dac=%u mode=0x%x %ux%u %ubpp pitch=%lu bits=%u", (unsigned long)sum, dac,
	         number, w, h, bpp, (unsigned long)vm.pitch, vm.bits);
	if (!(fp = fopen("SUM.TXT", "w")) || fprintf(fp, "%s\n", line) < 0 || fclose(fp) != 0)
		die("cannot write SUM.TXT");
	say("%s\n", line);
	getch();
	restore();
	print_report();
	free(buf);
	free(dirty);
	return 0;
}

static int arg_num(const char *s, unsigned *v)
{
	char *end;
	unsigned long x;

	if (!*s || *s < '0' || *s > '9')
		return -1;
	x = strtoul(s, &end, 10);
	if (*end || x > 100000ul)
		return -1;
	*v = (unsigned)x;
	return 0;
}

int main(int argc, char **argv)
{
	unsigned w, h, bpp;
	FILE *fp;
	char err[128];
	int line_no = 0;

	atexit(restore);
	signal(SIGINT, on_signal);
	if (argc != 1 && !((argc == 4 || argc == 5) && arg_num(argv[1], &w) == 0 && arg_num(argv[2], &h) == 0 &&
	                   arg_num(argv[3], &bpp) == 0 && w >= 1 && w <= 4096 && h >= 1 && h <= 4096 &&
	                   (bpp == 8 || bpp == 15 || bpp == 16 || bpp == 24 || bpp == 32))) {
		printf("usage: SVFVESA [W H BPP [DUMPFILE]]   (BPP 8, 15, 16, 24 or 32)\n");
		return 2;
	}
	if (!(fp = fopen(lines_name, "rb")) && !(fp = fopen(lines_name = LINES_FILE_8_3, "rb")))
		die("cannot open " LINES_FILE " (or " LINES_FILE_8_3 ")");
	if (vl_parse(fp, &table, err, &line_no) != 0)
		die("%s: line %d: %s", lines_name, line_no, err);
	fclose(fp);
	open_faces();
	vbe_init();
	if (argc != 1)
		return run_mode(w, h, bpp, argc == 5 ? argv[4] : NULL) == 0 ? 0 : 1;
	run_mode(640, 480, 16, NULL);
	run_mode(640, 480, 8, NULL);
	run_mode(640, 480, 32, NULL);
	return 0;
}
