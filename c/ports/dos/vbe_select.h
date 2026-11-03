/* vbe_select - the pure part of the DOS VBE 2.0 example: the mode list copy, the mode-block rules, the size and copy
 * arithmetic, the status helper and the palette entry. C99, <stdint.h> only: no DPMI, no I/O, no allocation. The VBE
 * blocks are hostile input: every value read from them is range-checked and every product is checked before use.
 * Tested on the host by tests/test_vbe.c under the sanitizers. */
#ifndef VBE_SELECT_H
#define VBE_SELECT_H

#include <stdint.h>

enum {
	VBE_OK = 0,
	VBE_FATAL = -1, /* vbe_status: a failed INT 10h AX=4F00h/4F01h/4F02h */
	VBE_FALLBACK = -2, /* vbe_status: a failed 4F08h/4F09h (palette): use 6 bits / the VGA ports */
	VBE_R_BAD_PTR = -10, /* vbe_modes_copy: VideoModePtr leaves no whole word below 1 MiB */
	VBE_R_READ = -11, /* vbe_modes_copy: the first read failed */
	VBE_R_UNSUPPORTED = -20, /* vbe_mode_accept: ModeAttributes bit 0 clear */
	VBE_R_NOT_GRAPHICS = -21, /* bit 4 clear */
	VBE_R_NO_LFB = -22, /* bit 7 clear */
	VBE_R_RESOLUTION = -23, /* XResolution/YResolution differ from the request */
	VBE_R_NO_PHYS = -24, /* PhysBasePtr is 0 */
	VBE_R_MODEL = -25, /* MemoryModel is not 4 (8 bpp) / 6 (direct colour) as the request needs */
	VBE_R_LAYOUT = -26, /* a field position or size is out of range, overlapping or not the reserved byte of 32 bpp */
	VBE_R_DEPTH = -27, /* BitsPerPixel and the masks do not make the requested depth */
	VBE_R_PITCH = -28, /* pitch 0, below w * bytes_pp, or above 65535 */
	VBE_R_RANGE = -29, /* a request outside 1..4096 (or a depth not in 8 15 16 24 32) */
	VBE_R_TOO_BIG = -30 /* pitch * h above 16 MB */
};

typedef struct {
	uint16_t mode_bits; /* ModeAttributes */
	unsigned depth; /* 8 15 16 24 32: the logical depth (a 5/5/5 mode reported as 16 bpp is 15) */
	unsigned bytes_pp; /* 1 2 2 3 4 */
	unsigned bits; /* BitsPerPixel as the block said */
	uint32_t pitch; /* bytes a scan line: the Lin* value when the Lin* set is complete, else the plain one */
	uint32_t phys_base; /* PhysBasePtr */
	uint32_t lfb_size; /* pitch * h, at most 16 MB */
	uint32_t map_size; /* lfb_size rounded up to a page */
	uint32_t buf_size; /* w * bytes_pp * h, the back buffer; never above lfb_size */
} vbe_mode;

/* Reads the 16-bit word at seg * 16 + off; 0 ok, -1 failed or out of range. The offset can exceed 0xFFFF (the list
 * runs on past a segment; use the linear address, e.g. dosmemget), so do not truncate it to 16 bits. */
typedef int (*vbe_read_word_fn)(void *ctx, uint32_t seg, uint32_t off, uint16_t *out);

/* Why a mode list copy stopped short of its 0xFFFF terminator (vbe_modes_copy_cut). */
enum { VBE_CUT_NONE = 0, VBE_CUT_256 = 1, VBE_CUT_1MB = 2, VBE_CUT_READ = 3 };

/* Copies the mode list the 4F00h block points to into modes[]: stops at 0xFFFF, at 256 entries, before a word that
 * would reach past 1 MiB or at the first failed read. Returns the count 0..256 with modes[count] = 0xFFFF (so
 * modes[] has 257 entries), VBE_R_BAD_PTR when the pointer leaves no whole word below 1 MiB, VBE_R_READ when the
 * first read fails. After a negative return modes[] is unspecified. */
int vbe_modes_copy(const uint8_t block[512], vbe_read_word_fn read_word, void *ctx, uint16_t modes[257]);

/* vbe_modes_copy, and *cut (when not NULL) says why the list ended: VBE_CUT_NONE (the terminator, or an empty list),
 * VBE_CUT_256 (256 entries and no terminator after them), VBE_CUT_1MB (the next word would reach past 1 MiB) or
 * VBE_CUT_READ (a read failed after the first). Set to VBE_CUT_NONE on a negative return. */
int vbe_modes_copy_cut(const uint8_t block[512], vbe_read_word_fn read_word, void *ctx, uint16_t modes[257], int *cut);

/* Accepts the 4F01h block for a w x h mode of logical depth bpp (8 15 16 24 32), or returns the reason (VBE_R_*).
 * out is zeroed first and filled on success only. vbe_version is for the caller's message: the choice between the Lin*
 * and the plain fields depends on what the block holds, not on the version. */
int vbe_mode_accept(const uint8_t info[256], unsigned vbe_version, unsigned w, unsigned h, unsigned bpp, vbe_mode *out);

/* 0 when ax == 0x004F; else VBE_FALLBACK for fn 4F08h/4F09h and VBE_FATAL for every other function. */
int vbe_status(unsigned ax, unsigned fn);

/* The palette entry for step k of n between bg and fg ({R, G, B} each): out = {B, G, R, 0}, each channel
 * (bg * (n - k) + fg * k + n / 2) / n in uint32_t, then >> 2 when dac_bits is 6. n = 0 gives bg; k > n is n. */
void vbe_palette_entry(unsigned k, unsigned n, const uint8_t bg[3], const uint8_t fg[3], unsigned dac_bits, uint8_t out[4]);

/* The palette fallback decision, a pure function of what the calls returned. granted8: 4F08h succeeded and granted an
 * 8-bit DAC; pal_ok: 4F09h succeeded; reset_ok: the 4F08h BH=6 reset after a failed 4F09h succeeded (consulted only
 * when vbe_palette_needs_reset). Returns VBE_PAL_BIOS (the 4F09h table stands) or VBE_PAL_PORTS (write the table through
 * ports 3C8h/3C9h) and sets *dac_bits to the DAC width the table must be built for and the run reports: 8 or 6; after
 * a failed 4F09h with an 8-bit DAC the port writes are 6-bit only if the reset to 6 bits worked, else 8. */
enum { VBE_PAL_BIOS = 0, VBE_PAL_PORTS = 1 };
int vbe_palette_plan(int granted8, int pal_ok, int reset_ok, unsigned *dac_bits);
/* 1 when a failed 4F09h after a granted 8-bit DAC calls for the reset to 6 bits. */
int vbe_palette_needs_reset(int granted8, int pal_ok);

/* 1 when the rows y .. y + rows - 1 lie inside the LFB: y * pitch <= lfb_size and rows * pitch <= lfb_size - y * pitch;
 * computed without wrapping. A pitch of 0 gives 0. */
int vbe_copy_ok(uint32_t lfb_size, uint32_t pitch, uint32_t y, uint32_t rows);

/* The refusal text of a VBE_* code. */
const char *vbe_reason(int code);

#endif
