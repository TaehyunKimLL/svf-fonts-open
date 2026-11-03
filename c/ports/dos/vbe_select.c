/* vbe_select - see vbe_select.h. Block offsets are those of VBE 2.0/3.0; every field is read byte-wise
 * little-endian. */
#include "vbe_select.h"

#include <string.h>

enum { /* VbeInfoBlock */
	IB_MODEPTR = 14
};
enum { /* ModeInfoBlock */
	MI_ATTR = 0,
	MI_PITCH = 16,
	MI_XRES = 18,
	MI_YRES = 20,
	MI_BITS = 25,
	MI_MODEL = 27,
	MI_FIELDS = 31, /* R G B Rsvd, (size, position) pairs */
	MI_PHYS = 40,
	MI_LINPITCH = 50,
	MI_LINFIELDS = 54 /* LinRed size/pos .. LinRsvd, after the page counts at 52, 53 */
};

#define MAX_LFB 0x1000000u /* 16 MB */
#define MAX_DIM 4096u
#define MAX_PITCH 65535u
#define MEM_1MB 0x100000u

static unsigned rd16(const uint8_t *b, unsigned o) { return (unsigned)b[o] | ((unsigned)b[o + 1] << 8); }

static uint32_t rd32(const uint8_t *b, unsigned o) { return rd16(b, o) | ((uint32_t)rd16(b, o + 2) << 16); }

int vbe_modes_copy_cut(const uint8_t block[512], vbe_read_word_fn read_word, void *ctx, uint16_t modes[257], int *cut)
{
	uint32_t off = rd16(block, IB_MODEPTR), seg = rd16(block, IB_MODEPTR + 2), lin = seg * 16u + off;
	unsigned n = 0;
	int why = VBE_CUT_NONE;

	if (cut)
		*cut = VBE_CUT_NONE;
	if (lin > MEM_1MB - 2u)
		return VBE_R_BAD_PTR;
	for (;;) {
		uint16_t v;

		if (lin + 2u * (n + 1u) > MEM_1MB) {
			why = VBE_CUT_1MB;
			break;
		}
		if (read_word(ctx, seg, off + 2u * n, &v) != 0) {
			if (n == 0)
				return VBE_R_READ;
			why = VBE_CUT_READ;
			break;
		}
		if (v == 0xFFFFu)
			break;
		modes[n++] = v;
		if (n == 256) {
			/* the terminator may follow the 256th entry */
			why = VBE_CUT_256;
			if (lin + 2u * 257u <= MEM_1MB && read_word(ctx, seg, off + 512u, &v) == 0 && v == 0xFFFFu)
				why = VBE_CUT_NONE;
			break;
		}
	}
	modes[n] = 0xFFFFu;
	if (cut)
		*cut = why;
	return (int)n;
}

int vbe_modes_copy(const uint8_t block[512], vbe_read_word_fn read_word, void *ctx, uint16_t modes[257])
{
	return vbe_modes_copy_cut(block, read_word, ctx, modes, NULL);
}

/* The four channels (R G B Rsvd) of the field set at offset o. */
static void fields(const uint8_t *info, unsigned o, unsigned size[4], unsigned pos[4])
{
	unsigned i;

	for (i = 0; i < 4; i++) {
		size[i] = info[o + 2 * i];
		pos[i] = info[o + 2 * i + 1];
	}
}

/* Every channel with a size lies inside depth bits, the sizes sum to at most depth, the fields do not overlap; a
 * 32 bpp reserved field is absent or exactly 8 @ 24. */
static int layout_ok(const unsigned size[4], const unsigned pos[4], unsigned bits)
{
	unsigned depth = bits == 15 ? 16 : bits, sum = 0, i;
	uint64_t used = 0;

	for (i = 0; i < 4; i++) {
		uint64_t m;

		if (size[i] == 0)
			continue;
		if (pos[i] > depth || size[i] > depth - pos[i])
			return 0;
		sum += size[i];
		m = (((uint64_t)1 << size[i]) - 1) << pos[i];
		if (used & m)
			return 0;
		used |= m;
	}
	if (sum > depth)
		return 0;
	if (bits == 32 && size[3] != 0 && (size[3] != 8 || pos[3] != 24))
		return 0;
	return 1;
}

static int is_(const unsigned size[4], const unsigned pos[4], unsigned r, unsigned rp, unsigned g, unsigned gp,
	       unsigned b, unsigned bp)
{
	return size[0] == r && pos[0] == rp && size[1] == g && pos[1] == gp && size[2] == b && pos[2] == bp;
}

int vbe_mode_accept(const uint8_t info[256], unsigned vbe_version, unsigned w, unsigned h, unsigned bpp, vbe_mode *out)
{
	unsigned attr, bits, model, size[4], pos[4], depth, bytes_pp;
	uint32_t pitch, lfb;

	(void)vbe_version;
	memset(out, 0, sizeof *out);
	if (w < 1 || w > MAX_DIM || h < 1 || h > MAX_DIM)
		return VBE_R_RANGE;
	if (bpp != 8 && bpp != 15 && bpp != 16 && bpp != 24 && bpp != 32)
		return VBE_R_RANGE;
	attr = rd16(info, MI_ATTR);
	if (!(attr & 1u))
		return VBE_R_UNSUPPORTED;
	if (!(attr & 0x10u))
		return VBE_R_NOT_GRAPHICS;
	if (!(attr & 0x80u))
		return VBE_R_NO_LFB;
	if (rd16(info, MI_XRES) != w || rd16(info, MI_YRES) != h)
		return VBE_R_RESOLUTION;
	if (rd32(info, MI_PHYS) == 0)
		return VBE_R_NO_PHYS;
	model = info[MI_MODEL];
	if (model != (bpp == 8 ? 4u : 6u))
		return VBE_R_MODEL;
	bits = info[MI_BITS];
	if (bpp == 8) {
		if (bits != 8)
			return VBE_R_DEPTH;
		depth = 8;
		/* no fields; the Lin pitch is used whenever it is filled */
		pitch = rd16(info, MI_LINPITCH) ? rd16(info, MI_LINPITCH) : rd16(info, MI_PITCH);
	} else {
		unsigned ls[4], lp[4];

		if (bits != 15 && bits != 16 && bits != 24 && bits != 32)
			return VBE_R_DEPTH;
		fields(info, MI_LINFIELDS, ls, lp);
		if (rd16(info, MI_LINPITCH) != 0 && ls[0] && ls[1] && ls[2]) {
			fields(info, MI_LINFIELDS, size, pos);
			pitch = rd16(info, MI_LINPITCH);
		} else {
			fields(info, MI_FIELDS, size, pos);
			pitch = rd16(info, MI_PITCH);
		}
		if (!layout_ok(size, pos, bits))
			return VBE_R_LAYOUT;
		if ((bits == 15 || bits == 16) && is_(size, pos, 5, 10, 5, 5, 5, 0))
			depth = 15;
		else if (bits == 16 && is_(size, pos, 5, 11, 6, 5, 5, 0))
			depth = 16;
		else if ((bits == 24 || bits == 32) && is_(size, pos, 8, 16, 8, 8, 8, 0))
			depth = bits;
		else
			return VBE_R_DEPTH;
	}
	if (depth != bpp)
		return VBE_R_DEPTH;
	bytes_pp = depth == 8 ? 1u : depth == 24 ? 3u : depth == 32 ? 4u : 2u;
	if (pitch == 0 || pitch > MAX_PITCH || pitch < (uint32_t)w * bytes_pp)
		return VBE_R_PITCH;
	if (h > MAX_LFB / pitch) /* pitch * h > 16 MB, and no product is formed that could wrap */
		return VBE_R_TOO_BIG;
	lfb = pitch * h;
	out->mode_bits = (uint16_t)attr;
	out->depth = depth;
	out->bytes_pp = bytes_pp;
	out->bits = bits;
	out->pitch = pitch;
	out->phys_base = rd32(info, MI_PHYS);
	out->lfb_size = lfb;
	out->map_size = (lfb + 4095u) & ~(uint32_t)4095u;
	out->buf_size = (uint32_t)w * bytes_pp * h; /* w * bytes_pp <= pitch, so this is <= lfb */
	return VBE_OK;
}

int vbe_status(unsigned ax, unsigned fn)
{
	if (ax == 0x004Fu)
		return VBE_OK;
	return fn == 0x4F08u || fn == 0x4F09u ? VBE_FALLBACK : VBE_FATAL;
}

void vbe_palette_entry(unsigned k, unsigned n, const uint8_t bg[3], const uint8_t fg[3], unsigned dac_bits, uint8_t out[4])
{
	unsigned c;

	if (k > n)
		k = n;
	for (c = 0; c < 3; c++) {
		uint32_t v;

		if (n == 0)
			v = bg[c];
		else
			v = ((uint32_t)bg[c] * (n - k) + (uint32_t)fg[c] * k + n / 2) / n;
		out[2 - c] = (uint8_t)(dac_bits == 6 ? v >> 2 : v); /* B G R: the channels are {R, G, B} */
	}
	out[3] = 0;
}

int vbe_palette_needs_reset(int granted8, int pal_ok)
{
	return granted8 && !pal_ok;
}

int vbe_palette_plan(int granted8, int pal_ok, int reset_ok, unsigned *dac_bits)
{
	if (pal_ok) {
		*dac_bits = granted8 ? 8u : 6u;
		return VBE_PAL_BIOS;
	}
	*dac_bits = vbe_palette_needs_reset(granted8, pal_ok) && !reset_ok ? 8u : 6u;
	return VBE_PAL_PORTS;
}

int vbe_copy_ok(uint32_t lfb_size, uint32_t pitch, uint32_t y, uint32_t rows)
{
	uint64_t start = (uint64_t)y * pitch;

	if (pitch == 0 || start > lfb_size)
		return 0;
	return (uint64_t)rows * pitch <= lfb_size - start;
}

const char *vbe_reason(int code)
{
	switch (code) {
	case VBE_OK: return "ok";
	case VBE_FATAL: return "VBE call failed";
	case VBE_FALLBACK: return "VBE palette call failed";
	case VBE_R_BAD_PTR: return "mode list pointer outside the first megabyte";
	case VBE_R_READ: return "mode list unreadable";
	case VBE_R_UNSUPPORTED: return "mode not supported";
	case VBE_R_NOT_GRAPHICS: return "not a graphics mode";
	case VBE_R_NO_LFB: return "no linear framebuffer";
	case VBE_R_RESOLUTION: return "resolution differs";
	case VBE_R_NO_PHYS: return "no framebuffer address";
	case VBE_R_MODEL: return "unsupported memory model";
	case VBE_R_LAYOUT: return "unsupported layout";
	case VBE_R_DEPTH: return "depth does not match the masks";
	case VBE_R_PITCH: return "bad bytes per scan line";
	case VBE_R_RANGE: return "request out of range";
	case VBE_R_TOO_BIG: return "framebuffer larger than 16 MB";
	default: return "unknown reason";
	}
}
