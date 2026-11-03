/* vesa_lines - the reader of vesa-lines.txt (the colours, the background and the text lines the VBE example draws),
 * the 8 bpp palette derived from it and the {W} {H} {BPP} substitution. C99, no allocation, no DPMI: the host tool
 * tests/vesa_lines_dump.c and the DOS program share it, and tools/vesa_lines.py is the same parser in Python (the
 * tests feed both the same files). The file is UTF-8 text, validated; the file at most 65536 bytes; a line is at most 512 bytes including its
 * newline; fields are split on '|' and every field loses its leading and trailing spaces and tabs (the text field
 * included, so it cannot start or end with a space); an empty text is allowed, any other empty field is an error.
 *
 *   [colours]   first section; name | rgb565 | rgb555 | rgb888 | index_base | index_levels   (6 fields, 16 at most)
 *   [lines]     once, after it; faces | scale | x | baseline | colour | text                  (6 fields, 32 at most)
 *
 * Blank lines and lines starting with '#' are comments. Any other header, a repeated header, a header after [lines]
 * and a record before [colours] is an error at that line. Numbers are decimal or 0x hex (x and baseline may carry a
 * '-'). A colour name is 1..31 printable ASCII bytes without spaces; `background` is required once, has index_levels
 * 0 and an index below every ramp; the ramps base .. base + levels of two colours do not overlap. A face entry is
 * [A-Z0-9_]{1,8}\.SVF exactly (at most 4 joined by '+'), a bare DOS name opened only in the faces directory, and not a
 * DOS device name (CON PRN AUX NUL COM1..9 LPT1..9). */
#ifndef VESA_LINES_H
#define VESA_LINES_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define VL_MAX_COLOURS 16
#define VL_MAX_LINES 32
#define VL_MAX_FACES 4
#define VL_LINE_BYTES 512 /* a line including its newline; 513 is an error */
#define VL_MAX_FILE 65536 /* a larger file is refused ("file too large", line 1) */
#define VL_NAME_BYTES 32 /* a colour name is 1..31 bytes of printable ASCII without spaces */

typedef struct {
	char name[VL_NAME_BYTES];
	uint16_t rgb565, rgb555;
	uint32_t rgb888;
	uint8_t index_base, index_levels;
} vl_colour;

typedef struct {
	char faces[VL_MAX_FACES][13];
	uint8_t nfaces, num, den, colour; /* colour: an index into vl_table.colours */
	int16_t x, baseline;
	char text[VL_LINE_BYTES];
} vl_line;

typedef struct {
	vl_colour colours[VL_MAX_COLOURS];
	uint8_t ncolours, background; /* background: an index into colours */
	vl_line lines[VL_MAX_LINES];
	uint8_t nlines;
} vl_table;

/* The streamed faces' block cache: blocks of VL_CACHE_BLOCK bytes, vl_cache_slots(file length) of them (the whole file
 * when small, 64 at most, never fewer than the 2 svf_open_stream needs); a slot is VL_CACHE_BLOCK + 8 bytes. */
#define VL_CACHE_BLOCK 1024
size_t vl_cache_slots(size_t file_len);

/* Reads the whole file. 0, or -1 with the message in err and the 1-based line in *line_no (a refusal at the end of
 * the file, such as a missing background, is at the line after the last one). The table is zeroed first. */
int vl_parse(FILE *fp, vl_table *t, char err[128], int *line_no);

/* The 256 palette entries as B G R pad: index background.index_base and every index no colour names take
 * background.rgb888; index base + k of a ramp of n levels takes (bg * (n - k) + fg * k + n / 2) / n per channel
 * (vbe_palette_entry), >> 2 with dac_bits 6. */
void vl_palette(const vl_table *t, unsigned dac_bits, uint8_t pal[256][4]);

/* text with {W} {H} {BPP} replaced by the decimal numbers (anything else, {X} included, is copied); out is always
 * NUL-terminated when out_len > 0, and the result is cut to fit. Returns the length the whole result needs. */
size_t vl_substitute(const char *text, unsigned w, unsigned h, unsigned bpp, char *out, size_t out_len);

#endif
