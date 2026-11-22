**English** | [한국어](c-renderer-guide.ko.md)

# SVF C renderer: integration guide

This guide shows how to put the SVF C renderer (`c/`) into your own program: how to get the source, open faces, draw
UTF-8 text with Hangul syllables composed from jamo sets, choose a drawing target, budget memory, and what to check when
something draws wrong. It is a tutorial. The reference is [c/README.md](../c/README.md) (API tables, compile-time
switches, ports) and, above all, the comments in [c/include/svf.h](../c/include/svf.h), which state the exact contract
of every function. The file format is [spec/SVF.md](../spec/SVF.md); the design is
[spec/renderer-design.md](../spec/renderer-design.md).

Every example below was compiled with `gcc -std=c99 -Wall -Wextra` against this repository and run on the shipped faces;
the output shown is real.

## Contents

1. The model in five words
2. Getting the library into your build
3. A complete first program
4. Faces: mapped and streamed
5. Lines of text: chains, metrics, measuring
6. Targets: where the pixels go
7. Scaling
8. Hangul: jamo faces and syllable composition
9. Memory budget
10. Compile-time switches: three recipes
11. Integrating into an application with its own text path
12. Testing your integration
13. Troubleshooting

## 1. The model in five words

**Face, chain, target, scratch, line.**

- A **face** (`svf_face`) is one opened `.SVF` file: a cell size, a bit depth (1, 2 or 8 bits per pixel), a table of
  glyphs, and optionally a jamo set that lets it draw every Hangul syllable. You allocate the struct; the library never
  allocates.
- A **chain** (`svf_chain`) is an ordered list of faces. Each code point is drawn by the first face that has it, so
  `{ ascii_face, hangul_face }` draws a mixed line with two faces.
- A **target** (`svf_target`) is where pixels go: a byte buffer in one of ten pixel formats, or a callback that receives
  one `(x, y, coverage)` per pixel.
- **Scratch** is a caller-supplied byte buffer big enough for one cell; `svf_chain_scratch_bytes()` says how big.
- A **line** is one call, `svf_draw_utf8()`: UTF-8 bytes in, pixels out, drawn along a baseline.

Everything is C99, uses only `<stdint.h>`, `<stddef.h>` and `<string.h>`, never calls `malloc`, and draws byte-identical
pixels to the Python reference (`tools/jamoset.py`, `tools/svfline.py`).

Vocabulary used below: a **cell** is the stored bitmap of one glyph (`cell_w x cell_h` pixels); **coverage** is how much
ink a pixel has, 0..255 (a 1 bpp ink pixel is 255, a 2 bpp level `k` is `k * 85`, an 8 bpp pixel is its byte); the
**baseline** is the row under the ascent: a cell's top row is `y_baseline - ascent + dy`.

## 2. Getting the library into your build

The library is six files and one header. There is nothing to configure and no dependency.

    c/include/svf.h
    c/src/svf_face.c  svf_jamo.c  svf_stream.c  svf_draw.c  svf_scale.c   (+ svf_internal.h)

Three ways to use it:

1. **Compile the sources into your program.** Add `c/src/*.c` to your build and `-I c/include`. This is what the
   examples here do:

       gcc -std=c99 -I c/include my_app.c c/src/*.c -o my_app

2. **Build the static library** with the repository's Makefile: `make -C c` writes `libsvf.a` (and the `svfdump` tool) to `c/build`; `O=DIR` moves them.
3. **Vendor or submodule it.** The repository is public and MIT-licensed for code (the faces under `svf/` are OFL; see
   [NOTICE.md](../NOTICE.md)). A project such as ScummVM can add the repository as a git submodule and compile the six
   files with its own build system.

**One rule matters above all: every source file that includes `svf.h`, and every library source, must be compiled with
the same `-D` switches.** `SVF_JMAP` changes the size of `svf_face`; mixing builds corrupts memory. Put the switches in
one place (a project-wide flags variable, or a small header you force-include).

The defaults on a desktop, DOS or WASM build are the full feature set: every target kind, streaming, scaling, every jamo
block version. You only set switches to *remove* things on a small device (section 10).

## 3. A complete first program

This program opens a face file, draws a mixed Hangul/Latin line into an 8-bit buffer, and prints it as text. Save it as
`ex1.c`:

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
	FILE *fp = fopen(path, "rb");
	if (!fp) return NULL;
	fseek(fp, 0, SEEK_END);
	long n = ftell(fp);
	fseek(fp, 0, SEEK_SET);
	uint8_t *p = malloc((size_t)n);
	if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
	fclose(fp);
	*len = (size_t)n;
	return p;
}

int main(int argc, char **argv)
{
	size_t len;
	uint8_t *bytes = slurp(argv[1], &len);
	svf_face face;
	svf_err err = bytes ? svf_open_mapped(&face, bytes, len) : SVF_E_IO;
	if (err != SVF_OK) { fprintf(stderr, "open failed: %d\n", (int)err); return 1; }

	svf_face *faces[1] = { &face };
	svf_chain chain = {0};            /* zeroed: scale 1/1, default marks, no cache */
	chain.faces = faces;
	chain.count = 1;

	const char *text = argc > 2 ? argv[2] : "SVF 안녕";
	svf_extent e;
	svf_measure_utf8(&chain, text, strlen(text), &e);
	int w = e.width + 2, h = e.ascent + e.descent + 2;
	uint8_t *pix = calloc((size_t)w * h, 1);
	size_t need = svf_chain_scratch_bytes(&chain);
	uint8_t *scratch = malloc(need);

	svf_target t;
	if (svf_target_init(&t, SVF_T_GRAY8, pix, (size_t)w * h, (int16_t)w, (int16_t)h, (uint16_t)w) != SVF_OK) return 1;
	err = svf_draw_utf8(&chain, text, strlen(text), 1, (int16_t)(1 + e.ascent), &t, scratch, need);
	/* err is SVF_OK, or SVF_E_IO if a streamed read failed part-way */

	for (int y = 0; y < h; y++) {
		for (int x = 0; x < w; x++) putchar(pix[y * w + x] > 127 ? '#' : pix[y * w + x] ? '+' : '.');
		putchar('\n');
	}
	return 0;
}
```

Build and run it on a shipped face:

    gcc -std=c99 -Wall -Wextra -I c/include ex1.c c/src/*.c -o ex1
    ./ex1 svf/dos/NEODG16A.SVF

Output (a 16x16 jamo-set face; its Hangul is composed from pieces at draw time):

    ..................................................................
    ..................................................................
    ....................................####....##....##.........##...
    ..#####..##...##..######...........##..##...##....##.........##...
    .##...##.##...##.##...............##....##..##....##......#####...
    .##......##...##.##...............##....##..#####.##.........##...
    .##......##...##.##...............##....##..##....##......#####...
    ..#####..##...##.######............##..##...##....##.........##...
    ......##.##...##.##.................####....##.....#######...##...
    ......##.##...##.##...............................................
    ......##.##...##.##................##................########.....
    .##...##..##.##..##................##..............###......###...
    ..#####....###...##................##..............##........##...
    ...................................##..............###......###...
    ....................................##########.......########.....
    ..................................................................
    ..................................................................
    ..................................................................

What it shows, step by step:

- `svf_open_mapped` validates the whole file; a face that opens is safe to draw. The return value says why a file was
  refused (`SVF_E_MAGIC`, `SVF_E_VERSION`, ...).
- `svf_measure_utf8` gives the line's extent without reading a glyph: `e.width` (pen travel), `e.ascent` and `e.descent`
  (rows above and below the baseline). Here 64 x (12 + 4).
- The baseline row passed to `svf_draw_utf8` is `1 + e.ascent`: the extent's ascent, plus the 1-pixel margin we left.
- The target needs `buf_len` of at least `rows * stride`; `svf_target_init` checks it and refuses (`SVF_E_ARG`) if it is
  short, if the kind is not compiled into this build, or if the stride is too small.

## 4. Faces: mapped and streamed

There are two ways to open a face. After that every call is the same.

### 4.1 Mapped: the whole file is addressable

    svf_err svf_open_mapped(svf_face *f, const uint8_t *data, size_t len);

Use it when the face is in RAM, in flash (`const` array), or in PROGMEM. The library reads `data` **in place**: the bytes
must stay valid and unchanged for as long as the face is used (a glyph's record is drawn without being re-checked). On
AVR, build the library with `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'` so every face read goes through
`pgm_read_byte`.

On a desktop you can `fread` the file into a heap buffer (section 3), or `mmap` it. Keep the buffer alive.

### 4.2 Streamed: the file stays on disk, an SD card or the network

    size_t svf_stream_tables_size(svf_read_fn rd, void *ctx, uint32_t file_len, svf_err *err);
    svf_err svf_open_stream(svf_face *f, svf_read_fn rd, void *ctx, uint32_t file_len,
                            uint8_t *tables, size_t tables_len,
                            uint8_t *cache, size_t cache_len, uint16_t block_size);

You supply a read callback, a buffer for the file's tables (the header, the code point table, metrics, the jamo block, the
glyph offset table) and optionally a block cache. Glyph rows are read when drawn. This is what the DOS programs do, so a
1 MB face does not need 1 MB of RAM.

```c
static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
{
	FILE *fp = ctx;
	return fseek(fp, (long)off, SEEK_SET) == 0 ? (long)fread(dst, 1, len, fp) : -1;
}

static uint8_t tables[256 * 1024], cache[8 * (1024 + 8)];
svf_err err;
size_t need = svf_stream_tables_size(rd, fp, file_len, &err);   /* 0 and err set when the header is refused */
if (need && need <= sizeof tables)
	err = svf_open_stream(&face, rd, fp, file_len, tables, sizeof tables, cache, sizeof cache, 1024);
```

Rules worth knowing:

- `svf_stream_tables_size` tells you how big `tables` must be. It depends on the face and on which readers the build
  compiles. For `NEODG16A.SVF` (a jamo face) it is 8,153 bytes; for the precomposed `NEODG16.SVF` it is 46,492 bytes
  (measured).
- The block cache is optional (`cache_len` 0 means none). With one, the library reads whole `block_size`-byte blocks
  (a power of two from 64 to 4096) and keeps the most recently used ones. A slot is `block_size + 8` bytes and the cache
  must hold at least two slots. Pass `sizeof cache` as `cache_len`.
- The face keeps pointers to your `tables`, `cache`, `rd` and `ctx`: keep them alive. One face (with its cache) must not
  be drawn from two threads at once.
- A failed or short read returns `SVF_E_IO` for the glyph being drawn only; the line continues and the error is returned at
  the end. `svf_stream_reads(&face)` counts callback calls (handy for tuning cache size).
- Composing a syllable of a streamed face **without** a cache needs `2 * svf_cell_bytes` of scratch (the second half holds
  the piece being read). `svf_chain_scratch_bytes` already accounts for it.
- A build with `-DSVF_NO_STREAM` does not even declare these functions: a call is a compile error, not a run-time failure.

### 4.3 What the face tells you

After a successful open the accessors report the header: `svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`,
`svf_glyph_count`, `svf_flags`. `svf_has(f, cp)` says whether the face can draw a code point (a stored glyph, or a
syllable or compatibility jamo it composes). `svf_metrics_of(f, cp, &m)` returns the advance, bearing, ink width and
vertical offset of a glyph.

`svf_status(f)` is easy to miss and important: a face can open successfully and still carry **status bits** saying what
was dropped, for example `SVF_FACE_JSET_BAD` (the jamo block failed validation: the face is plain and will not compose
Hangul) or `SVF_FACE_JSET_UNREAD` (the jamo block is fine but this build does not read that version). A Hangul face whose
status is non-zero is the first thing to check when syllables do not appear (section 13).

## 5. Lines of text: chains, metrics, measuring

### 5.1 Fallback chains

```c
svf_face *faces[2] = { &latin_face, &hangul_face };
svf_chain chain = {0};
chain.faces = faces;
chain.count = 2;
chain.missing_advance = 8;      /* pixels to advance for a code point no face has (nothing is drawn) */
```

Each code point is drawn by the first face for which `svf_has` is true. Order matters: put the face whose style you want
for shared characters (digits, punctuation) first. A `chain.faces` that is `NULL`, a `count` of 0, or a NULL entry makes
the chain "without faces": calls using it return `SVF_E_ARG` and draw nothing.

### 5.2 Marks, advances, invalid UTF-8

- Advances come from the face's metrics table (variable width); a face without one advances by the cell width. A composed
  syllable advances by the jamo block's syllable advance (or the cell width).
- Combining marks advance 0 and are drawn over the previous glyph. The default predicate is U+0300..U+036F; the core
  carries no Unicode tables, so pass your own `chain.is_mark` for more.
- Invalid UTF-8 never crashes and never reads past `len`: each bad subpart is drawn as U+FFFD if a face has it, else skipped
  without advancing. NUL is an ordinary code point (`len` bytes are drawn, not a C string).

### 5.3 Measuring before drawing

`svf_measure_utf8(&chain, s, len, &e)` gives `e.width`, `e.ascent`, `e.descent` using exactly the layout rules of the
draw, without reading any glyph (so it is cheap, and a streamed face does no I/O). Use it for centring, right-aligning,
word wrap and for sizing the buffer you draw into. Words and lines are yours: the library draws one line at a time and
knows nothing about wrapping.

## 6. Targets: where the pixels go

A target converts each drawn pixel's coverage to your format. You choose the kind with `svf_target_init`:

    svf_err svf_target_init(svf_target *t, svf_target_kind kind, uint8_t *buf, size_t buf_len,
                            int16_t w, int16_t h, uint16_t stride);

| You draw to | Use | Notes |
|---|---|---|
| A 32-bit framebuffer or SDL surface (B, G, R, X in memory) | `SVF_T_XRGB8888` | set `t.fg888`, `t.bg888` as `0x00RRGGBB` |
| 24-bit | `SVF_T_RGB888` | same fields |
| 16-bit colour LCD | `SVF_T_RGB565` / `SVF_T_RGB555` | `t.fg565`, `t.bg565`; `SVF_TF_RGB16_BIGENDIAN` in `t.flags` for high byte first |
| A palette mode (VGA mode 13h, VBE 8 bpp, SDL CLUT8) | `SVF_T_INDEXED8` | `t.index_base`, `t.index_levels` select a ramp of palette entries |
| SSD1306 pages | `SVF_T_MONO_PAGE` | bit `y & 7` of `buf[(y >> 3) * stride + x]` |
| 1 bpp bitmap rows | `SVF_T_MONO_ROW` | MSB first |
| 1/2/4/8-bit grey | `SVF_T_GRAY` | `t.gray_bits`; MSB first, or `SVF_TF_GRAY_LSB_FIRST` |
| One byte of coverage per pixel | `SVF_T_GRAY8` | a mask you composite yourself |
| **Anything else** | `SVF_T_COVERAGE_CB` | a callback receives `(x, y, coverage)` |

How the kinds treat existing pixels is exact and documented above `svf_target` in `svf.h`. The short version:

- Colour kinds (`RGB565`, `RGB555`, `XRGB8888`, `RGB888`) **do not read the existing pixel**. They write the blend of
  `bg` and `fg` by coverage, so `bg` must be the colour the background really is. Draw on a plain background, or use the
  callback kind to blend over arbitrary content.
- `GRAY8`, `INDEXED8`, `GRAY` keep the maximum of the existing value and the new one. For `INDEXED8` that means the text
  shows only where the existing index is lower than the ink's: put the background index below the ramp
  `index_base + 1 .. index_base + index_levels`.
- `MONO_*` set bits when coverage is at least `t.mono_threshold` (default 128) and never clear bits.
- Only pixels inside the clip rectangle (`t.clip_x0..clip_y1`, half-open, default the whole target) are written; no byte
  of a neighbouring pixel and no row padding is touched.

### 6.1 Colour text on a 32-bit surface

```c
svf_target t;
svf_target_init(&t, SVF_T_XRGB8888, surface_pixels, (size_t)pitch * height, width, height, (uint16_t)pitch);
t.fg888 = 0x00FFC000;      /* amber text */
t.bg888 = 0x00000020;      /* the background colour the caller knows */
```

`stride` is a `uint16_t` number of bytes, so a 32-bit target is at most 16,383 pixels wide.

### 6.2 The callback target: the universal adapter

When your pixel format is not one of the above, or you want to blend over existing content, or the destination is another
library's surface, use the callback. The library calls `plot(ctx, x, y, coverage)` once for each pixel with coverage above
0 inside the clip, row by row, with no buffer involved. This example blends white text over a 32-bit surface that already
contains a picture (compiled and run against `NEODG16A.SVF`):

```c
typedef struct { uint8_t *pix; int pitch; uint32_t fg; } Surf;      /* your surface */

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	Surf *s = ctx;
	uint32_t *px = (uint32_t *)(s->pix + y * s->pitch) + x;
	uint32_t bg = *px, out = 0;
	for (int sh = 0; sh <= 16; sh += 8) {                       /* B, G, R */
		uint32_t b = (bg >> sh) & 255, f = (s->fg >> sh) & 255;
		out |= ((b * (255 - cov) + f * cov + 127) / 255) << sh;
	}
	*px = out;
}

Surf s = { pix, 64 * 4, 0x00FFFFFF };
svf_target t;
svf_target_init(&t, SVF_T_COVERAGE_CB, NULL, 0, 64, 24, 0);    /* w, h still define the bounds and clip */
t.plot = plot;
t.ctx = &s;
svf_draw_utf8(&chain, "가A", 4, 2, 16, &t, scratch, scratch_len);
```

`plot` must be set before drawing (else `SVF_E_ARG`). Where two cells overlap on one pixel (a mark over its base) the callback
is called once per cell, so a blending callback composes both, which is what you want.

## 7. Scaling

Set `chain.scale_num` and `chain.scale_den` (each 1 to 16; 0 and 0 mean 1/1). A whole multiple (`2/1`, `3/1`) draws every
source pixel as an N x N block, so bitmap edges stay hard. Any other ratio is area-averaged into 8-bit coverage, so
`3/2` of a 1 bpp face gets grey edge pixels (use a colour or grey target for it; on a mono target the threshold decides).
Lengths scale with rounding half up (symmetric), so the measured extent equals what is drawn. `x`, `y_baseline` and the clip
are always in output pixels.

Scratch grows with scaling: `svf_chain_scratch_bytes(&chain)` includes the scaled cell (about
`ceil(cell_w*num/den) * ceil(cell_h*num/den)` bytes more). Always recompute it after changing the scale. For a 16x16 face
at 3/2 it was 640 bytes in the measured run.

For small MCU builds `-DSVF_NO_SCALE` removes scaling entirely (any ratio but n/n is then `SVF_E_ARG`), and the fast
scaler's stack frame is about 610 to 680 bytes; see `svf.h` "Scaling" before using it on a 2 KB RAM chip.

## 8. Hangul: jamo faces and syllable composition

A **precomposed** face stores one glyph per syllable it covers. A **jamo-set** face (header flag bit 1, `svf_is_jamo(f)`)
stores a few hundred small pieces and a table that says which pieces form each syllable. `svf_draw_utf8` composes
U+AC00..U+D7A3 (and compatibility jamo U+3131..U+3163) from the pieces on the fly: the maximum coverage of two or three
pieces. You do nothing special; just draw Hangul text.

```c
if (svf_is_jamo(&face)) {
	uint16_t pieces[3];
	int n = svf_jamo_pieces(&face, 0xD55C /* 한 */, pieces);   /* 3: initial, medial, final */
}
uint8_t cell[64];                                      /* >= svf_cell_bytes(&face) */
svf_glyph(&face, 0xD55C, cell, sizeof cell);           /* the composed cell, MSB first, rows padded to bytes */
```

`svf_glyph` and `svf_compose` return the cell of one code point without a target: useful for caching glyphs in your own
atlas.

### 8.1 What your build reads

Jamo blocks come in versions 1, 2 and 3 (JMAP, with a LIST form). The default desktop/DOS/WASM/SDL build reads them
all. A small-MCU build reads fewer (see the table in [c/README.md](../c/README.md), "Jamo sets: what each build reads").
A face the build cannot read still opens, as a **plain** face with a status bit; it simply does not compose Hangul. Faces
for your own application: build the faces the same way the repository's tools do, and check `svf_status` at load time.

### 8.2 The composed-syllable cache

Composing costs a few table lookups and a merge per syllable. For text that repeats (a UI, a dialogue box redrawn every
frame) give the chain a cache:

```c
static uint8_t syl[4096];                       /* slots of (8 + the largest cell bytes of the chain's faces) */
svf_chain_cache(&chain, syl, sizeof syl);
```

Pixels are identical with or without it. It matters most for streamed faces: a cached syllable causes no reads at all.
Measured on a streamed 16x16 face, a first draw of "한글 ab" at 3/2 made 10 read calls and the second, cached, made no
more. The cache is round robin with a linear lookup: tens of slots suit small targets; thousands do not. Call
`svf_chain_cache` again after you change `chain.faces` or reopen a face.

## 9. Memory budget

All memory is yours. Add up:

| Item | Size |
|---|---|
| `svf_face` | `sizeof(svf_face)`: 96 bytes on a 64-bit host with `SVF_JMAP` (80 without; smaller on MCUs; 96 is the cap) |
| `svf_chain`, `svf_target` | a few tens of bytes each |
| Scratch | `svf_chain_scratch_bytes(&chain)`: one cell (`svf_cell_bytes`), twice that for a streamed face without a block cache, plus the scaled cell when scaling |
| Streamed face | `svf_stream_tables_size(...)` for the tables, plus `slots * (block_size + 8)` for the optional cache |
| Syllable cache | `slots * (8 + largest cell bytes)` |
| Target buffer | `rows * stride` (or none for the callback kind) |
| Mapped face | the file itself, in RAM or flash (flash faces cost no RAM) |
| Stack | the scaler's own frame: about 610 bytes on AVR, 680 on Cortex-M0+ with the default fast scaler |

A 16x16 1 bpp cell is 32 bytes; a 24x24 2 bpp cell is 144 bytes.

## 10. Compile-time switches: three recipes

Switches are `-D` flags given to **every** source (section 2). You almost never need them on a desktop. The ones that
matter for choosing a recipe:

- **Desktop, DOS, WASM, SDL, ScummVM-class applications: no switches.** Everything is on.
- **A small MCU with one display:** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_TARGETS=<one kind's bit> -DSVF_JSET_V2=0
  -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, and write faces with the matching profile (`tools/jamoset.py`
  `mcu-strict`). The Arduino Uno build uses exactly this: see [c/ports/arduino/README.md](../c/ports/arduino/README.md).
- **Smallest code on any CPU:** `-DSVF_SMALL` turns off the speed-oriented fast paths. Pixels are identical; only speed
  is lost.

The complete switch table with defaults per toolchain is in [c/README.md](../c/README.md), "Compile-time switches", and
the sizes each configuration produces are in `c/cross/SIZES.md`.

## 11. Integrating into an application with its own text path

Most applications already have a "draw this string at x, y with this colour" routine and a "how wide is this string"
routine. The renderer maps onto both:

| Application needs | Library call |
|---|---|
| Open the font at start-up | `svf_open_mapped` (face loaded into memory) or `svf_open_stream` (large faces, low RAM) |
| Width and height of a string | `svf_measure_utf8` (`width`; height = `ascent + descent`, or the face's `cell_h`) |
| Draw a string | `svf_draw_utf8` into a target |
| Draw into the application's own surface | `SVF_T_COVERAGE_CB` with the surface in `ctx` (section 6.2), or the target kind that matches its pixel format |
| Same string drawn every frame | the syllable cache (section 8.2), and cache your own rendered string bitmap |
| Per-glyph advance for your own layout | `svf_metrics_of`, or `svf_measure_utf8` on a single character |

Points that routinely cause trouble:

1. **Text encoding.** The library takes UTF-8. Applications that store text as CP949/EUC-KR, UHC or a game-specific
   code page must convert to UTF-8 (or to code points) before calling. There is no byte-pair guessing in the library.
2. **Baseline, not top.** `y_baseline` is the row under the glyph's ascent. To draw a line with its top at `top`, pass
   `top + e.ascent` (with `e` from `svf_measure_utf8`), or `top + svf_ascent(&face)`.
3. **Line height.** The extent's `ascent + descent` is the ink extent of what was measured. For uniform line spacing use
   the faces' `cell_h`.
4. **Several sizes.** One face is one cell size. Use one face per size (`svf/dos` has many), or draw one size scaled
   with an integer ratio, which keeps pixels crisp.
5. **Face lifetime.** The face struct, the data buffer (mapped) or tables/cache/`ctx` (streamed) must outlive every draw.
   Do not put a `svf_face` in memory you will move.
6. **Threads.** Independent faces/chains can be used in parallel. One face (with its cache) and one chain (with its
   syllable cache) are not used from two threads at once.
7. **Clipping.** Set the target's clip rectangle (`clip_x0..clip_y1`) to your dialogue box; the library will not write
   outside it and does not read glyphs for cells wholly outside.
8. **Validate user-supplied faces.** `svf_open_*` is built to reject hostile files (it is fuzz-tested), but never build
   with `-DSVF_JSET_TRUSTED=1` for faces that do not come from your own build.
9. **Same switches everywhere** (section 2).

A typical wrapper is about thirty lines: an object holding the face, chain, scratch and syllable cache, with `width(str)`
and `draw(str, x, y_top)` methods calling `svf_measure_utf8` and `svf_draw_utf8`.

Note on ScummVM: the repository's ScummVM work currently uses its own SVF reader (`jamo_set.h`), which does not read the
version 3 jamo block; replacing it with this library is tracked separately (see [c/README.md](../c/README.md), "Who uses
it"). Everything in this section applies to that integration.

## 12. Testing your integration

- **The reference.** `tools/svfline.py` draws the same line in Python; its output must equal the C output byte for byte.
  `tools/test_c_renderer.py` is the repository's own comparison; read it for how to drive both sides.
- **The gate.** `make -C c check` runs the unit programs under sanitizers, verifies that no object references `malloc`,
  `calloc`, `realloc` or `free`, and runs the Python comparison.
- **Your own checks.** A tiny program that draws a known string into a `SVF_T_GRAY8` buffer and prints it (section 3) is
  the fastest way to see a layout problem. Compile your tests with `-fsanitize=address,undefined`.
- **Faces.** `tools/facecheck.py` validates a face file from the writer's side; the maker app checks every face it writes
  and draws it before counting it done.

## 13. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `svf_open_mapped` returns `SVF_E_MAGIC` | not an SVFN file, or the file was read in text mode or truncated | open in binary mode; compare the length |
| `SVF_E_VERSION` | a version 2 file | convert with `tools/svf2to3.py` |
| `SVF_E_LAYOUT` | the build was compiled with `-DSVF_LAYOUTS=...` and the face uses another layout | write the face with the profile the build reads, or widen `SVF_LAYOUTS` |
| Hangul draws nothing but Latin works | the face is plain: check `svf_status` for `SVF_FACE_JSET_BAD`, `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD` | build with the readers the face needs (section 8.1) or rewrite the face |
| Hangul draws as missing-glyph spacing | no face in the chain has the code point | `svf_has(face, cp)`; add a face, set `missing_advance` |
| `svf_draw_utf8` returns `SVF_E_NOMEM` | scratch smaller than `svf_chain_scratch_bytes` (recompute after changing scale or faces) | enlarge scratch |
| `SVF_E_ARG` from `svf_target_init` | kind not in `SVF_TARGETS`, `buf_len < rows * stride`, stride too small, or w/h 0 | check each; for GRAY set `gray_bits` after init |
| `SVF_E_ARG` from `svf_draw_utf8` | a chain without faces; a scale ratio outside 1..16 or `SVF_NO_SCALE`; `INDEXED8` with a bad ramp; `COVERAGE_CB` without `plot` | check them |
| Text is missing on an `INDEXED8` target | the background index is not below the ink ramp (max rule) | renumber the palette |
| Colour text has a halo | `bg565`/`bg888` is not the real background | set the true background, or use the callback target |
| Glyphs one row too high or low | passed the top row instead of the baseline | `y_baseline = top + ascent` |
| Crashes or garbage after upgrading | translation units built with different `-D` switches (`SVF_JMAP` changes `svf_face`) | rebuild everything with one flag set |
| `SVF_E_IO` on a streamed face | the read callback returned a short or negative count | return exactly `len` bytes or a negative value; check the file position logic |
