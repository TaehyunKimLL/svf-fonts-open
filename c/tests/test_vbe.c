/* test_vbe - ports/dos/vbe_select.c on hostile input (host only, sanitizer build): the mode list copy through a
 * failure-capable word reader over a 1 MiB image, the mode-block acceptance rules, the size arithmetic, the copy bound,
 * the status helper and the palette entry. Prints one line per case; exit 0 when all pass, 1 otherwise. */
#include "vbe_select.h"

#include <stdio.h>
#include <string.h>

static int bad;

static void check(const char *name, int ok)
{
	printf("%s: %s\n", name, ok ? "ok" : "FAIL");
	bad |= !ok;
}

/* ---- the mode list ---- */

static uint8_t image[0x100010]; /* 16 bytes past 1 MiB for the lenient-reader cases */

/* ctx: number of reads still allowed (-1 = no limit); a read at or past 1 MiB fails like dosmemget out of range. */
static uint32_t rd_limit = 0x100000u; /* reads whose word does not end below this fail */
static uint32_t rd_max; /* the highest address any read asked for, failed or not */

static int rd(void *ctx, uint32_t seg, uint32_t off, uint16_t *out)
{
	int *left = ctx;
	uint32_t lin = seg * 16u + off;

	if (lin > rd_max)
		rd_max = lin;
	if (*left == 0)
		return -1;
	if (*left > 0)
		(*left)--;
	if (lin > rd_limit - 2u)
		return -1;
	*out = (uint16_t)(image[lin] | (image[lin + 1] << 8));
	return 0;
}

static void put8(uint8_t *b, unsigned o, unsigned v) { b[o] = (uint8_t)v; }
static void put16(uint8_t *b, unsigned o, unsigned v) { b[o] = (uint8_t)v; b[o + 1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *b, unsigned o, uint32_t v) { put16(b, o, v & 0xFFFFu); put16(b, o + 2, v >> 16); }

static void word(uint32_t lin, unsigned v) { put16(image, lin, v); }

static void ctrl(uint8_t blk[512], uint32_t seg, uint32_t off)
{
	memset(blk, 0, 512);
	put16(blk, 4, 0x200);
	put16(blk, 14, off);
	put16(blk, 16, seg);
}

static void list_case(const char *name, uint32_t lin, int reads, int want, uint16_t last)
{
	uint8_t blk[512];
	uint16_t modes[257];
	int left = reads, n;

	rd_max = 0;
	ctrl(blk, lin >> 4, lin & 15u);
	memset(modes, 0x55, sizeof modes);
	n = vbe_modes_copy(blk, rd, &left, modes);
	check(name, rd_max <= 0xFFFFEu && n == want && (n < 0 || modes[n] == 0xFFFF) && (n < 0 || last == 0 || modes[n - 1] == last));
}

static void lists(void)
{
	uint8_t blk[512];
	uint16_t modes[257];
	int left = -1, n, i;

	memset(image, 0, sizeof image);
	/* the last word below 1 MiB is read, nothing past it */
	word(0xFFFFE, 0x0101);
	list_case("ptr_ffffe", 0xFFFFE, -1, 1, 0x0101);
	word(0xFFFFE, 0xFFFF);
	list_case("ptr_last_word", 0xFFFFE, -1, 0, 0);
	list_case("ptr_last_byte", 0xFFFFF, -1, VBE_R_BAD_PTR, 0);
	/* a reader that would serve the 16 bytes past 1 MiB must still not be asked for them */
	rd_limit = 0x100010u;
	word(0x100000, 0x0777); word(0x100002, 0xFFFF);
	word(0xFFFFE, 0x0101);
	list_case("ptr_ffffe_lenient_reader", 0xFFFFE, -1, 1, 0x0101);
	word(0xFFFFE, 0x0102);
	list_case("ptr_ffffe_lenient_reader_2", 0xFFFFE, -1, 1, 0x0102);
	rd_limit = 0x100000u;
	word(0x100000, 0); word(0x100002, 0);
	word(0xFFFFE, 0xFFFF);
	word(0xFFF00, 0x0110); word(0xFFF02, 0x0111); word(0xFFF04, 0x0112); word(0xFFF06, 0xFFFF);
	list_case("ptr_fff00", 0xFFF00, -1, 3, 0x0112);
	ctrl(blk, 0xFFFF, 0x0010);
	check("ptr_1mb", vbe_modes_copy(blk, rd, &left, modes) == VBE_R_BAD_PTR);
	ctrl(blk, 0xFFFF, 0xFFFF);
	check("ptr_far", vbe_modes_copy(blk, rd, &left, modes) == VBE_R_BAD_PTR);
	/* 0x100000 - 512: a 256-word list reaches 1 MiB exactly, no terminator */
	for (i = 0; i < 256; i++)
		word(0xFFE00 + 2u * i, 0x0100 + i);
	list_case("no_terminator_at_1mb", 0xFFE00, -1, 256, 0x01FF);
	/* 256 entries, no terminator, in the middle of memory */
	for (i = 0; i < 300; i++)
		word(0x20000 + 2u * i, 0x0100 + (i & 0xFF));
	ctrl(blk, 0x2000, 0);
	memset(modes, 0, sizeof modes);
	n = vbe_modes_copy(blk, rd, &left, modes);
	check("no_terminator", n == 256 && modes[256] == 0xFFFF && modes[255] == 0x01FF && modes[0] == 0x0100);
	word(0x30000, 0xFFFF); word(0x30002, 0x0101);
	list_case("terminator_first", 0x30000, -1, 0, 0);
	for (i = 0; i < 10; i++)
		word(0x40000 + 2u * i, 0x0200 + i);
	list_case("read_fails_mid", 0x40000, 5, 5, 0x0204);
	list_case("read_fails_first", 0x40000, 0, VBE_R_READ, 0);
	/* ten words are readable, the eleventh read fails: the list ends with those ten (a failure after the first read is not an error) */
	list_case("read_budget_exact", 0x40000, 10, 10, 0x0209);
}

/* ---- mode blocks ---- */

typedef struct {
	unsigned bpp;
	unsigned bits;
	unsigned model;
	unsigned m[4], p[4]; /* R G B Rsvd mask sizes / positions */
} layout;

static const layout L8 = {8, 8, 4, {0}, {0}};
static const layout L15 = {15, 15, 6, {5, 5, 5, 0}, {10, 5, 0, 0}};
static const layout L15R = {15, 16, 6, {5, 5, 5, 0}, {10, 5, 0, 0}};
static const layout L16 = {16, 16, 6, {5, 6, 5, 0}, {11, 5, 0, 0}};
static const layout L24 = {24, 24, 6, {8, 8, 8, 0}, {16, 8, 0, 0}};
static const layout L32 = {32, 32, 6, {8, 8, 8, 8}, {16, 8, 0, 24}};

static void setfields(uint8_t *b, unsigned o, const layout *l)
{
	int i;

	for (i = 0; i < 4; i++) {
		put8(b, o + 2u * i, l->m[i]);
		put8(b, o + 2u * i + 1, l->p[i]);
	}
}

/* A good block: plain fields set, Lin* zero. */
static void mk(uint8_t b[256], const layout *l, unsigned w, unsigned h, unsigned pitch)
{
	memset(b, 0, 256);
	put16(b, 0, 0x99);
	put16(b, 16, pitch);
	put16(b, 18, w);
	put16(b, 20, h);
	put8(b, 25, l->bits);
	put8(b, 27, l->model);
	setfields(b, 31, l);
	put32(b, 40, 0xE0000000u);
}

static void setlin(uint8_t b[256], unsigned pitch, const layout *l)
{
	put16(b, 50, pitch);
	setfields(b, 54, l);
}

static int acc(const char *name, const uint8_t b[256], unsigned w, unsigned h, unsigned bpp, unsigned depth,
	       unsigned pitch, unsigned bytes_pp)
{
	vbe_mode m;
	int r = vbe_mode_accept(b, 0x200, w, h, bpp, &m);
	uint32_t lfb = (uint32_t)pitch * h;
	int ok = r == VBE_OK && m.depth == depth && m.bytes_pp == bytes_pp && m.pitch == pitch && m.lfb_size == lfb &&
		 m.map_size == ((lfb + 4095u) & ~4095u) && m.buf_size == (uint32_t)w * bytes_pp * h &&
		 m.phys_base == 0xE0000000u && m.mode_bits == 0x99;

	check(name, ok);
	return ok;
}

static void ref(const char *name, const uint8_t b[256], unsigned w, unsigned h, unsigned bpp, int code)
{
	vbe_mode m;
	int r = vbe_mode_accept(b, 0x200, w, h, bpp, &m);

	if (r != code)
		printf("  %s: got %d (%s) want %d (%s)\n", name, r, vbe_reason(r), code, vbe_reason(code));
	check(name, r == code);
}

static void modes(void)
{
	uint8_t b[256];
	layout l;
	vbe_mode m;

	mk(b, &L16, 640, 480, 1280);
	acc("base16", b, 640, 480, 16, 16, 1280, 2);
	mk(b, &L8, 640, 480, 640);
	acc("base8", b, 640, 480, 8, 8, 640, 1);
	mk(b, &L24, 640, 480, 1920);
	acc("base24", b, 640, 480, 24, 24, 1920, 3);
	mk(b, &L32, 640, 480, 2560);
	acc("base32", b, 640, 480, 32, 32, 2560, 4);
	mk(b, &L15, 640, 480, 1280);
	acc("base15", b, 640, 480, 15, 15, 1280, 2);

	mk(b, &L16, 640, 480, 1280);
	put16(b, 0, 0x19);
	ref("lfb_clear", b, 640, 480, 16, VBE_R_NO_LFB);
	put16(b, 0, 0x98);
	ref("attr_unsupported", b, 640, 480, 16, VBE_R_UNSUPPORTED);
	put16(b, 0, 0x89);
	ref("attr_not_graphics", b, 640, 480, 16, VBE_R_NOT_GRAPHICS);
	mk(b, &L16, 640, 480, 1280);
	put32(b, 40, 0);
	ref("phys_zero", b, 640, 480, 16, VBE_R_NO_PHYS);
	mk(b, &L16, 640, 480, 0);
	ref("pitch_zero", b, 640, 480, 16, VBE_R_PITCH);
	mk(b, &L16, 640, 480, 1279);
	ref("pitch_short", b, 640, 480, 16, VBE_R_PITCH);
	mk(b, &L16, 640, 480, 1280);
	put8(b, 27, 3);
	ref("model_planar", b, 640, 480, 16, VBE_R_MODEL);
	mk(b, &L16, 640, 480, 1280);
	ref("model_vs_request8", b, 640, 480, 8, VBE_R_MODEL);
	mk(b, &L8, 640, 480, 640);
	ref("model_vs_request16", b, 640, 480, 16, VBE_R_MODEL);
	mk(b, &L16, 640, 480, 1280);
	ref("res_mismatch_w", b, 639, 480, 16, VBE_R_RESOLUTION);
	ref("res_mismatch_h", b, 640, 479, 16, VBE_R_RESOLUTION);
	ref("depth_request", b, 640, 480, 15, VBE_R_DEPTH);
	ref("request_bpp_bad", b, 640, 480, 12, VBE_R_RANGE);
	mk(b, &L16, 640, 480, 1280);
	put8(b, 25, 12);
	ref("bits_odd", b, 640, 480, 16, VBE_R_DEPTH);
	mk(b, &L8, 640, 480, 640);
	put8(b, 25, 4);
	ref("bits8_wrong", b, 640, 480, 8, VBE_R_DEPTH);

	/* pitch 65535 */
	mk(b, &L8, 640, 4096, 65535);
	ref("pitch_65535_too_big", b, 640, 4096, 8, VBE_R_TOO_BIG);
	mk(b, &L8, 640, 200, 65535);
	acc("pitch_65535_ok", b, 640, 200, 8, 8, 65535, 1);
	{
		vbe_mode mm;
		vbe_mode_accept(b, 0x200, 640, 200, 8, &mm);
		check("pitch_65535_sizes", mm.lfb_size == 13107000u && mm.map_size == 13107200u);
	}

	/* Lin* fields: a realistic VBE 3.0 block, Lin pairs at 54..61, LinBytesPerScanLine 50 (1280) != 16 (1024), the
	 * plain set BGR (not ours) so only the Lin set can be accepted */
	l = L32;
	l.p[0] = 0; l.p[2] = 16;
	mk(b, &l, 256, 200, 1024);
	put16(b, 50, 1280);
	put8(b, 52, 1); put8(b, 53, 0); /* BnkNumberOfImagePages, LinNumberOfImagePages */
	put8(b, 54, 8); put8(b, 55, 16); put8(b, 56, 8); put8(b, 57, 8);
	put8(b, 58, 8); put8(b, 59, 0); put8(b, 60, 8); put8(b, 61, 24);
	put32(b, 62, 148500000u); /* MaxPixelClock */
	acc("vbe3_realistic", b, 256, 200, 32, 32, 1280, 4);
	mk(b, &L32, 256, 200, 1024);
	put16(b, 50, 1280);
	/* Lin pitch without Lin masks -> plain pitch */
	acc("vbe3_pitch_alone_not_enough", b, 256, 200, 32, 32, 1024, 4);
	l = L32;
	mk(b, &l, 640, 480, 2560);
	l.p[0] = 0; /* a plain set that cannot be used */
	setfields(b, 31, &l);
	setlin(b, 4096, &L32);
	acc("lin_used", b, 640, 480, 32, 32, 4096, 4);
	mk(b, &L32, 640, 480, 2560);
	setlin(b, 4096, &L32);
	put8(b, 60, 0);
	put8(b, 61, 0); /* Lin rsvd absent is fine: R G B decide */
	acc("lin_used_no_rsvd_field", b, 640, 480, 32, 32, 4096, 4);
	mk(b, &L32, 640, 480, 2560);
	setlin(b, 4096, &L32);
	put8(b, 58, 0);
	acc("lin_partial", b, 640, 480, 32, 32, 2560, 4); /* B missing: the plain set, pitch and fields */
	mk(b, &L32, 640, 480, 2560);
	setlin(b, 0, &L32);
	acc("lin_pitch_zero", b, 640, 480, 32, 32, 2560, 4);
	mk(b, &L32, 640, 480, 2560);
	put16(b, 50, 4096);
	acc("lin_masks_zero", b, 640, 480, 32, 32, 2560, 4);
	mk(b, &L8, 640, 480, 1000);
	put16(b, 50, 2000);
	acc("lin_8bpp", b, 640, 480, 8, 8, 2000, 1);
	mk(b, &L16, 640, 480, 1280);
	setlin(b, 1280, &L16);
	put8(b, 55, 12); /* the Lin set is chosen and is bad: no fallback to the plain one */
	ref("lin_bad_no_fallback", b, 640, 480, 16, VBE_R_LAYOUT);
	mk(b, &L16, 640, 480, 0);
	setlin(b, 1280, &L16);
	acc("lin_only", b, 640, 480, 16, 16, 1280, 2);

	/* layouts */
	l = L16;
	l.m[0] = 6; l.p[0] = 11;
	mk(b, &l, 640, 480, 1280);
	ref("pos_overflow", b, 640, 480, 16, VBE_R_LAYOUT);
	l = L32;
	l.p[3] = 28;
	mk(b, &l, 640, 480, 2560);
	ref("rsvd_28_at_32", b, 640, 480, 32, VBE_R_LAYOUT);
	l = L32;
	l.m[3] = 4;
	mk(b, &l, 640, 480, 2560);
	ref("rsvd_4_at_24", b, 640, 480, 32, VBE_R_LAYOUT);
	l = L32;
	l.p[3] = 0;
	mk(b, &l, 640, 480, 2560);
	ref("rsvd_8_at_0", b, 640, 480, 32, VBE_R_LAYOUT);
	l = L32;
	l.p[0] = 24; l.p[3] = 16; /* a valid, non-overlapping layout whose reserved byte is not at 24 */
	mk(b, &l, 640, 480, 2560);
	ref("rsvd_8_at_16", b, 640, 480, 32, VBE_R_LAYOUT);
	l = L32;
	l.m[3] = 0; l.p[3] = 0;
	mk(b, &l, 640, 480, 2560);
	acc("rsvd_absent_32_ok", b, 640, 480, 32, 32, 2560, 4);
	l = L32;
	l.m[3] = 0; l.p[3] = 24;
	mk(b, &l, 640, 480, 2560);
	acc("rsvd_absent_32_pos_ignored", b, 640, 480, 32, 32, 2560, 4);
	l = L16;
	l.p[0] = 16;
	mk(b, &l, 640, 480, 1280);
	ref("pos_16_at_16bpp", b, 640, 480, 16, VBE_R_LAYOUT);
	l = L16;
	l.m[0] = 5; l.p[0] = 8;
	mk(b, &l, 640, 480, 1280);
	ref("overlap", b, 640, 480, 16, VBE_R_LAYOUT);
	l = L16;
	l.m[2] = 8; /* sum 19 > 16 */
	mk(b, &l, 640, 480, 1280);
	ref("sum_over_depth", b, 640, 480, 16, VBE_R_LAYOUT);
	l = L16;
	l.m[0] = 255; l.p[0] = 255; /* 255 + 255 must not wrap */
	mk(b, &l, 640, 480, 1280);
	ref("mask_pos_255", b, 640, 480, 16, VBE_R_LAYOUT);
	l = L16;
	l.p[0] = 0; l.p[1] = 0; l.p[2] = 0; /* every field at 0 */
	mk(b, &l, 640, 480, 1280);
	ref("all_overlap", b, 640, 480, 16, VBE_R_LAYOUT);
	l = L16;
	l.m[1] = 0; l.p[1] = 0; /* green absent: not 5/6/5 */
	mk(b, &l, 640, 480, 1280);
	ref("green_absent", b, 640, 480, 16, VBE_R_DEPTH);

	l = L15;
	l.m[3] = 1; l.p[3] = 15;
	l.bits = 15;
	mk(b, &l, 640, 480, 1280);
	acc("dosbox_lin15", b, 640, 480, 15, 15, 1280, 2);
	setlin(b, 1280, &l);
	acc("dosbox_lin15_lin", b, 640, 480, 15, 15, 1280, 2);
	mk(b, &L15R, 640, 480, 1280);
	acc("bits16_masks555", b, 640, 480, 15, 15, 1280, 2);
	ref("bits16_masks555_as16", b, 640, 480, 16, VBE_R_DEPTH);
	l = L15R;
	l.bits = 24;
	mk(b, &l, 640, 480, 1920);
	ref("bits24_masks555", b, 640, 480, 15, VBE_R_DEPTH);
	l = L24;
	l.p[0] = 24; l.p[1] = 16; l.p[2] = 8;
	mk(b, &l, 640, 480, 1920);
	ref("bits24_pos32", b, 640, 480, 24, VBE_R_LAYOUT);
	l = L24;
	l.p[0] = 0; l.p[2] = 16; /* BGR order: valid layout, not ours */
	mk(b, &l, 640, 480, 1920);
	ref("bgr_order", b, 640, 480, 24, VBE_R_DEPTH);
	mk(b, &L24, 640, 480, 2560);
	ref("bits24_requested32", b, 640, 480, 32, VBE_R_DEPTH);

	/* resolution caps: the caller passes w = XResolution */
	mk(b, &L16, 0, 480, 1280);
	ref("xres_0", b, 0, 480, 16, VBE_R_RANGE);
	mk(b, &L16, 4097, 480, 65535);
	ref("xres_4097", b, 4097, 480, 16, VBE_R_RANGE);
	mk(b, &L16, 65535, 480, 65535);
	ref("xres_65535", b, 65535, 480, 16, VBE_R_RANGE);
	mk(b, &L16, 640, 0, 1280);
	ref("yres_0", b, 640, 0, 16, VBE_R_RANGE);
	mk(b, &L16, 640, 4097, 1280);
	ref("yres_4097", b, 640, 4097, 16, VBE_R_RANGE);
	mk(b, &L8, 4096, 4096, 4096);
	acc("res_4096", b, 4096, 4096, 8, 8, 4096, 1);
	mk(b, &L16, 640, 480, 1280);
	ref("req_w_0", b, 0, 480, 16, VBE_R_RANGE); /* a request outside 1..4096 is RANGE before the block is read */
	ref("req_w_4097", b, 4097, 480, 16, VBE_R_RANGE);
	ref("req_h_65536", b, 640, 65536, 16, VBE_R_RANGE);

	/* a refusal leaves the output zero */
	memset(&m, 0xAA, sizeof m);
	vbe_mode_accept(b, 0x200, 0, 0, 16, &m);
	check("refusal_zeroes_out", m.pitch == 0 && m.depth == 0 && m.map_size == 0 && m.buf_size == 0);
}

/* every (pitch, h, w, bytes_pp) at the 16 MB edge, both sides; the 64 MB side of the buffer is unreachable */
static void size_caps(void)
{
	static const layout *ls[] = {&L8, &L15, &L16, &L24, &L32};
	static const unsigned bpps[] = {8, 15, 16, 24, 32};
	static const unsigned bytes[] = {1, 2, 2, 3, 4};
	static const unsigned pitches[] = {4095, 4096, 4097, 8191, 8192, 8193, 12288, 16383, 16384, 16385, 21845, 21846,
					   32768, 65535};
	static const unsigned hs[] = {1, 255, 256, 257, 511, 512, 513, 1023, 1024, 1025, 2047, 2048, 2049, 4095, 4096};
	unsigned i, j, k, nacc = 0, nbig = 0, nbad = 0;
	uint8_t b[256];

	for (i = 0; i < 5; i++)
		for (j = 0; j < sizeof pitches / sizeof *pitches; j++)
			for (k = 0; k < sizeof hs / sizeof *hs; k++) {
				unsigned p = pitches[j], h = hs[k], w = p / bytes[i];
				vbe_mode m;
				int r;
				int want_big;

				if (w > 4096)
					w = 4096;
				if (w == 0)
					continue;
				mk(b, ls[i], w, h, p);
				r = vbe_mode_accept(b, 0x200, w, h, bpps[i], &m);
				want_big = (uint64_t)p * h > 0x1000000u;
				if (want_big ? r != VBE_R_TOO_BIG
					     : (r != VBE_OK || m.lfb_size != p * h || m.buf_size > m.lfb_size ||
						m.buf_size != w * bytes[i] * h || m.map_size < m.lfb_size ||
						m.map_size - m.lfb_size > 4095u || (m.map_size & 4095u)))
					nbad++;
				nacc += !want_big;
				nbig += want_big;
			}
	printf("size_caps: %u accepted, %u too big, %u wrong\n", nacc, nbig, nbad);
	check("size_caps", nbad == 0 && nacc > 100 && nbig > 100);
	/* the exact edge */
	mk(b, &L8, 4096, 4096, 4096);
	{
		vbe_mode m;

		check("size_edge_exact", vbe_mode_accept(b, 0x200, 4096, 4096, 8, &m) == VBE_OK && m.lfb_size == 0x1000000u &&
					     m.map_size == 0x1000000u);
	}
	mk(b, &L32, 4096, 1024, 16384);
	check("size_edge_32bpp", vbe_mode_accept(b, 0x200, 4096, 1024, 32, &(vbe_mode){0}) == VBE_OK);
	mk(b, &L32, 4096, 1025, 16384);
	check("size_edge_32bpp_over", vbe_mode_accept(b, 0x200, 4096, 1025, 32, &(vbe_mode){0}) == VBE_R_TOO_BIG);
	mk(b, &L8, 4096, 4096, 4097);
	check("size_edge_over_by_a_row", vbe_mode_accept(b, 0x200, 4096, 4096, 8, &(vbe_mode){0}) == VBE_R_TOO_BIG);
}

static void copy_ok(void)
{
	uint32_t lfb = 614400, pitch = 1280;

	check("copy_end_rows0", vbe_copy_ok(lfb, pitch, 480, 0) == 1);
	check("copy_end_rows1", vbe_copy_ok(lfb, pitch, 480, 1) == 0);
	check("copy_last_row", vbe_copy_ok(lfb, pitch, 479, 1) == 1);
	check("copy_last_row_2", vbe_copy_ok(lfb, pitch, 479, 2) == 0);
	check("copy_all", vbe_copy_ok(lfb, pitch, 0, 480) == 1);
	check("copy_all_plus_one", vbe_copy_ok(lfb, pitch, 0, 481) == 0);
	check("copy_past_end", vbe_copy_ok(lfb, pitch, 481, 0) == 0);
	check("copy_rows_over", vbe_copy_ok(lfb, pitch, 0, 1000) == 0);
	check("copy_no_underflow", vbe_copy_ok(lfb, pitch, 400, 100) == 0 && vbe_copy_ok(lfb, pitch, 400, 80) == 1);
	check("copy_wrap_y_product", vbe_copy_ok(lfb, 0x10001, 0x10001, 0) == 0);
	check("copy_wrap_y", vbe_copy_ok(lfb, 65535, 0xFFFFFFFFu, 0) == 0 && vbe_copy_ok(lfb, 65537, 65535, 0) == 0);
	check("copy_wrap_rows", vbe_copy_ok(lfb, 65535, 0, 0xFFFFFFFFu) == 0 && vbe_copy_ok(lfb, 0x10001, 0, 0x10001) == 0);
	check("copy_wrap_sum", vbe_copy_ok(0xFFFFFFFFu, 0x10000, 0x8000, 0x8000) == 0);
	check("copy_pitch_zero", vbe_copy_ok(lfb, 0, 0, 1) == 0);
	check("copy_lfb_zero", vbe_copy_ok(0, pitch, 0, 0) == 1 && vbe_copy_ok(0, pitch, 0, 1) == 0);
}

static void status_table(void)
{
	static const unsigned axs[] = {0x004F, 0x014F, 0x024F, 0x0000};
	static const unsigned fns[] = {0x4F00, 0x4F01, 0x4F02, 0x4F08, 0x4F09};
	static const int fail[] = {VBE_FATAL, VBE_FATAL, VBE_FATAL, VBE_FALLBACK, VBE_FALLBACK};
	unsigned i, j, wrong = 0;

	for (i = 0; i < 4; i++)
		for (j = 0; j < 5; j++)
			wrong += vbe_status(axs[i], fns[j]) != (i == 0 ? VBE_OK : fail[j]);
	check("status_table", wrong == 0);
	check("status_unknown_fn", vbe_status(0x004F, 0x4F05) == VBE_OK && vbe_status(0x014F, 0x4F05) == VBE_FATAL);
	check("status_ax_high", vbe_status(0x104F, 0x4F08) == VBE_FALLBACK && vbe_status(0xFFFF, 0x4F00) == VBE_FATAL);
}

static void palette(void)
{
	static const uint8_t bg[3] = {10, 20, 30}, fg[3] = {200, 100, 50};
	static const uint8_t z[3] = {0, 0, 0}, f[3] = {255, 255, 255}, o[3] = {255, 255, 255};
	uint8_t out[4];

	memset(out, 0xEE, 4);
	vbe_palette_entry(0, 4, bg, fg, 8, out);
	check("palette_k0", out[0] == 30 && out[1] == 20 && out[2] == 10 && out[3] == 0);
	vbe_palette_entry(4, 4, bg, fg, 8, out);
	check("palette_kn", out[0] == 50 && out[1] == 100 && out[2] == 200 && out[3] == 0);
	vbe_palette_entry(1, 4, bg, fg, 8, out);
	check("palette_order_bgr", out[0] == 35 && out[1] == 40 && out[2] == 58 && out[3] == 0);
	vbe_palette_entry(128, 255, z, f, 8, out);
	check("palette_mid", out[0] == 128 && out[1] == 128 && out[2] == 128);
	vbe_palette_entry(1, 4, bg, fg, 6, out);
	check("palette_dac6", out[0] == (35 >> 2) && out[1] == (40 >> 2) && out[2] == (58 >> 2) && out[3] == 0);
	memset(out, 0xEE, 4);
	vbe_palette_entry(0, 0, bg, fg, 8, out);
	check("palette_n0", out[0] == 30 && out[1] == 20 && out[2] == 10 && out[3] == 0);
	vbe_palette_entry(7, 0, bg, fg, 6, out);
	check("palette_n0_dac6", out[0] == (30 >> 2) && out[1] == (20 >> 2) && out[2] == (10 >> 2));
	vbe_palette_entry(300, 4, bg, fg, 8, out);
	check("palette_k_over_n", out[0] == 50 && out[1] == 100 && out[2] == 200);
	/* the 255-step sum reaches 65152: the formula must not run in a promoted 16-bit int */
	vbe_palette_entry(128, 255, o, o, 8, out);
	check("palette_255_sum", out[0] == 255 && out[1] == 255 && out[2] == 255);
	{
		unsigned k, c, wrong = 0;
		static const uint8_t zero[3] = {0, 0, 0};
		uint8_t hi[3];

		for (c = 0; c < 256; c += 17) {
			hi[0] = hi[1] = hi[2] = (uint8_t)c;
			for (k = 0; k <= 255; k++) {
				vbe_palette_entry(k, 255, zero, hi, 8, out);
				wrong += out[0] != (uint8_t)((c * k + 127u) / 255u);
			}
		}
		check("palette_ramp_all", wrong == 0);
	}
}

static void reasons(void)
{
	static const int codes[] = {VBE_FATAL, VBE_FALLBACK, VBE_R_BAD_PTR, VBE_R_READ, VBE_R_UNSUPPORTED,
				    VBE_R_NOT_GRAPHICS, VBE_R_NO_LFB, VBE_R_RESOLUTION, VBE_R_NO_PHYS, VBE_R_MODEL,
				    VBE_R_LAYOUT, VBE_R_DEPTH, VBE_R_PITCH, VBE_R_RANGE, VBE_R_TOO_BIG};
	unsigned i, j, ok = 1;

	for (i = 0; i < sizeof codes / sizeof *codes; i++) {
		ok &= vbe_reason(codes[i]) != NULL && vbe_reason(codes[i])[0] != 0;
		for (j = 0; j < i; j++)
			ok &= strcmp(vbe_reason(codes[i]), vbe_reason(codes[j])) != 0;
	}
	ok &= vbe_reason(12345) != NULL && vbe_reason(VBE_OK) != NULL;
	check("reasons", ok);
}

/* ---- the palette plan and the mode list cut flag ---- */

static void palette_plan(void)
{
	unsigned dac;

	/* 8-bit DAC granted, 4F09h fine: the BIOS call, 8 bits */
	check("plan_bios_8", vbe_palette_plan(1, 1, 0, &dac) == VBE_PAL_BIOS && dac == 8);
	check("plan_bios_6", vbe_palette_plan(0, 1, 0, &dac) == VBE_PAL_BIOS && dac == 6);
	/* 4F09h failed after an 8-bit DAC was granted: the reset to 6 bits worked -> ports at 6; failed -> ports at 8 */
	check("plan_ports_reset_ok", vbe_palette_plan(1, 0, 1, &dac) == VBE_PAL_PORTS && dac == 6);
	check("plan_ports_reset_failed", vbe_palette_plan(1, 0, 0, &dac) == VBE_PAL_PORTS && dac == 8);
	/* never granted: the DAC is 6 bits, nothing to reset, whatever the reset result says */
	check("plan_ports_6", vbe_palette_plan(0, 0, 0, &dac) == VBE_PAL_PORTS && dac == 6);
	check("plan_ports_6_b", vbe_palette_plan(0, 0, 1, &dac) == VBE_PAL_PORTS && dac == 6);
	check("plan_reset_needed", vbe_palette_needs_reset(1, 0) == 1 && vbe_palette_needs_reset(1, 1) == 0 &&
	      vbe_palette_needs_reset(0, 0) == 0);
}

static void cut_case(const char *name, uint32_t lin, int reads, int want_n, int want_cut)
{
	uint8_t blk[512];
	uint16_t modes[257];
	int left = reads, cut = -1, n;

	ctrl(blk, lin >> 4, lin & 15u);
	n = vbe_modes_copy_cut(blk, rd, &left, modes, &cut);
	check(name, n == want_n && cut == want_cut);
}

static void cuts(void)
{
	int i;

	memset(image, 0, sizeof image);
	for (i = 0; i < 300; i++)
		word(0x20000 + 2u * i, 0x0100 + (i & 0xFF));
	cut_case("cut_256", 0x20000, -1, 256, VBE_CUT_256);
	/* exactly 256 entries and then the terminator: not cut */
	word(0x20000 + 2u * 256, 0xFFFF);
	cut_case("cut_none_256_terminated", 0x20000, -1, 256, VBE_CUT_NONE);
	word(0x30000, 0x0101); word(0x30002, 0xFFFF);
	cut_case("cut_none", 0x30000, -1, 1, VBE_CUT_NONE);
	for (i = 0; i < 256; i++)
		word(0xFFE00 + 2u * i, 0x0100 + i);
	cut_case("cut_256_at_1mb", 0xFFE00, -1, 256, VBE_CUT_256);
	for (i = 0; i < 8; i++)
		word(0xFFFF0 + 2u * i, 0x0200 + i);
	cut_case("cut_1mb_short", 0xFFFF0, -1, 8, VBE_CUT_1MB);
	for (i = 0; i < 10; i++)
		word(0x40000 + 2u * i, 0x0200 + i);
	cut_case("cut_read", 0x40000, 5, 5, VBE_CUT_READ);
	cut_case("cut_read_first", 0x40000, 0, VBE_R_READ, VBE_CUT_NONE);
}

int main(void)
{
	lists();
	modes();
	size_caps();
	copy_ok();
	status_table();
	palette();
	reasons();
	palette_plan();
	cuts();
	printf("vbe: %s\n", bad ? "FAIL" : "OK");
	return bad;
}
