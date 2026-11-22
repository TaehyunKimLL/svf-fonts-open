**English** | [한국어](c-renderer-guide.ko.md)

# SVF C renderer: integration guide

This guide shows how to put the SVF C renderer (`c/`) into your own program: how to get the source, open faces, embed a face in
firmware, choose a face that fits your target, draw UTF-8 text with Hangul syllables composed from jamo sets, choose a
drawing target, budget memory, build for each platform the repository has an example for, and what to check when
something draws wrong. It is a tutorial. The reference is [c/README.md](../c/README.md) (API tables, compile-time
switches, ports) and, above all, the comments in [c/include/svf.h](../c/include/svf.h), which state the exact contract
of every function. The file format is [spec/SVF.md](../spec/SVF.md); the design is
[spec/renderer-design.md](../spec/renderer-design.md).

Every C example below was compiled with `gcc -std=c99 -Wall -Wextra` against this repository (the embedded-face sample
also for Cortex-M0+ with arm-none-eabi-gcc and for the ATmega328P with avr-gcc; the platform samples with the toolchain
of their platform) and run where it can run on the shipped faces; the output shown is real.

## Contents

1. The model in five words
2. Getting the library into your build
3. A complete first program
4. Faces: mapped and streamed
5. Embedding a face
6. Choosing a face for your target
7. Lines of text: chains, metrics, measuring
8. Targets: where the pixels go
9. Scaling
10. Hangul: jamo faces and syllable composition
11. Memory budget
12. Compile-time switches: three recipes
13. Platforms: Arduino, CH582, DOS, ESP32, Pico, SDL, Web
14. Integrating into an application with its own text path
15. Testing your integration
16. Troubleshooting

## 1. The model in five words

**Face, chain, target, scratch, line.**

- A **face** (`svf_face`) is one opened `.SVF` file: a cell size, a bit depth (1, 2 or 8 bits per pixel), a table of
  glyphs, and optionally a jamo set that lets it compose Hangul syllables (all 11,172, or the ones its table lists). You allocate the struct; the library never
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

The library is five source files, one private header and one public header. It has no dependency.

    c/include/svf.h
    c/src/svf_face.c  svf_jamo.c  svf_stream.c  svf_draw.c  svf_scale.c   (+ svf_internal.h)

Three ways to use it:

1. **Compile the sources into your program.** Add `c/src/*.c` to your build and `-I c/include`. This is what the
   examples here do:

       gcc -std=c99 -I c/include my_app.c c/src/*.c -o my_app

2. **Build the static library** with the repository's Makefile: `make -C c` writes `libsvf.a` (and the `svfdump` tool) to `c/build`; `O=DIR` moves them.
3. **Vendor or submodule it.** The repository is public and MIT-licensed for code (the faces under `svf/` are OFL; see
   [NOTICE.md](../NOTICE.md)). A project such as ScummVM can add the repository as a git submodule and compile the
   sources with its own build system.

**One rule matters above all: every source file that includes `svf.h`, and every library source, must be compiled with
the same `-D` switches.** `SVF_JMAP` changes the size of `svf_face`; mixing builds corrupts memory. Put the switches in
one place (a project-wide flags variable, or a small header you force-include).

On a desktop (any compiler that defines `__unix__`, `_WIN32` or `__APPLE__`), a DOS build (`__DJGPP__`) and a WASM
build (`__EMSCRIPTEN__`) you need no switches: the defaults are the full feature set (every target kind, streaming,
scaling, every jamo block version). You set switches there only to *remove* things. **Any other target gets the
small-device defaults**: an MCU, bare metal, or a compiler that defines none of those macros reads no version 3 (JMAP,
LIST) jamo block and no BIG limits, so a face that needs them opens plain; set what you need explicitly (`-DSVF_JMAP=1`
and the others of section 12). `-DSVF_SMALL` has the same effect on a desktop (section 12).

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
	/* e.width is the pen's travel, not the ink: the last cell can reach past it, so leave a cell's width of room */
	int w = e.width + svf_cell_w(&face) + 2, h = e.ascent + e.descent + 2;
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

    ..................................................................................
    ..................................................................................
    ....................................####....##....##.........##...................
    ..#####..##...##..######...........##..##...##....##.........##...................
    .##...##.##...##.##...............##....##..##....##......#####...................
    .##......##...##.##...............##....##..#####.##.........##...................
    .##......##...##.##...............##....##..##....##......#####...................
    ..#####..##...##.######............##..##...##....##.........##...................
    ......##.##...##.##.................####....##.....#######...##...................
    ......##.##...##.##...............................................................
    ......##.##...##.##................##................########.....................
    .##...##..##.##..##................##..............###......###...................
    ..#####....###...##................##..............##........##...................
    ...................................##..............###......###...................
    ....................................##########.......########.....................
    ..................................................................................
    ..................................................................................
    ..................................................................................

What it shows, step by step:

- `svf_open_mapped` validates the whole file; a face that opens is safe to draw. The return value says why a file was
  refused (`SVF_E_MAGIC`, `SVF_E_VERSION`, ...).
- `svf_measure_utf8` gives the line's extent without reading a glyph: `e.width` is the **pen's travel** (the sum of the
  advances), not the width of the ink; `e.ascent` and `e.descent` are the rows the cells reach above and below the
  baseline (whole cells, not only the rows that have ink). Here 64 x (12 + 4).
- That is why the buffer is `e.width + svf_cell_w(&face) + 2` wide, not `e.width + 2`: a glyph can have ink beyond its
  advance (PAPLG16's `f` reaches 3 pixels past it, measured), so the last cell can need up to a cell width more, and a
  combining mark first in a line can start left of `x`. The library clips to the target, so nothing outside is
  written; too small a buffer cuts ink off instead of corrupting memory.
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
status is non-zero is the first thing to check when syllables do not appear (section 16).

## 5. Embedding a face

A microcontroller has no file system (or none you want to depend on), and a program that ships one face is simpler with
the face inside it. `c/bench/mkface.py` writes a face as a C array:

    python3 c/bench/mkface.py svf/dos/NEODG16G.SVF face.c --name neodg16g --profile mcu-strict

It needs Python 3 and the repository's `tools/` (it imports `tools/jamoset.py` by a path relative to itself, so run it
from a checkout) and writes nothing but the output file. `--name` must be a C identifier. The output, abridged:

```c
/* Generated by c/bench/mkface.py from svf/dos/NEODG16G.SVF (10124 bytes, profile mcu-strict). */
#include <stdint.h>
#ifdef __AVR__
#include <avr/pgmspace.h>
#define BENCH_FACE_ATTR PROGMEM
#else
#define BENCH_FACE_ATTR
#endif
const uint8_t neodg16g[] BENCH_FACE_ATTR __attribute__((aligned(4))) = {
	83,86,70,78,3,0,7,0,1,2,2,0,23,1,16,16,12,0,0,0,120,11,0,0,
	...
};
const uint32_t neodg16g_len = 10124u;
```

- The array is `const`, so it stays in flash (read-only data) and costs no RAM; on AVR it is `PROGMEM`, which puts it in
  flash's own address space (the library then reads it through `SVF_RD8`, section 4.1). `NAME_len` is the face's size
  in bytes: pass both to `svf_open_mapped`.
- `aligned(A)` is `A = 2^max(REC, TAB)` bytes of the written layout (4 for `mcu-strict`; left out when it is 1), so a
  record's offset in the file is its address alignment. Alignment is **only speed**. `svf_open_mapped` checks the
  alignment of the offsets *inside the file* against the layout, never the address of the array: a face opens and
  draws the same from an odd address (tested).
- `--profile mcu-strict` rewrites the face in the layout of `SVF_LAYOUT_MCU_STRICT` (record and table units 4 bytes, row
  unit 1 byte, 16-bit offsets where they fit); the pixels are the same. **Every face under `svf/` already has that
  layout** (the units; all 116 files checked with `svfdump FACE info`), so a build with
  `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` opens the shipped files as they are, and the profile only shrinks the
  offsets: NEODG16G goes from 10,684 to 10,124 bytes. Without `--profile` the bytes are the file's own. A face in the
  `tight` profile (1/1/1) is refused by such a build with `SVF_E_LAYOUT`.
- **Do not use `xxd -i`.** It writes `unsigned char name[]`, which is not `const`: the array is placed in `.data`, a
  copy in RAM (measured with arm-none-eabi-gcc 15.2.1: 10,688 bytes of `.data` for NEODG16G, five times an Uno's whole
  RAM), it has no `PROGMEM` on AVR, no alignment, and `unsigned int name_len` is 16 bits on AVR. It is fine on a
  desktop, where a RAM copy is the point.

### 5.1 Where the array goes, per platform

| Target | Where the face lives | Notes |
|---|---|---|
| AVR (Arduino Uno) | `PROGMEM` flash | build the library with `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`. Without `SVF_RD8` the library reads flash addresses as RAM and `svf_open_mapped` returns `SVF_E_MAGIC` (run on simavr: 0 with the override, 1 without). The text passed to `svf_draw_utf8` is read with plain loads: keep it in RAM (copy a `PROGMEM` string with `strncpy_P` first) |
| Other Arduino cores (ARM, ESP32, RP2040) | `const` array in flash | flash is memory-mapped, so no `SVF_RD8` override and no `PROGMEM` (`mkface` adds it on `__AVR__` only) |
| ESP32 (ESP-IDF) | `const` array (`.rodata` in flash), **or** a data partition mapped with `esp_partition_mmap`, **or** a file on SPIFFS streamed | the partition keeps the face out of the app image and its size; SPIFFS + `svf_open_stream` keeps it out of the address space too (section 13.4) |
| Raspberry Pi Pico / Pico 2 | `const` array in flash, executed in place (XIP) | the faces are read through the XIP cache: a first touch of a block is a flash read (section 13.5) |
| CH582 | `const` array in CodeFlash | the linker places `.rodata` in flash; no RAM copy |
| DOS, SDL, desktop, WASM | a file read into memory (`fread`, `SDL_LoadFile`, a JavaScript `Uint8Array` copied into the module), or `mmap`ed | or streamed from the file (section 4.2); the buffer must outlive the face |

### 5.2 After opening: check the face

`svf_open_mapped` tells you the file is valid, not that this build can compose its Hangul. Check both, once, at start-up
(this is `text_cb.c`; it compiles on the host, for Cortex-M0+ and, with the Uno flags of section 13.1 but `-DSVF_TARGETS=0x10` (this example draws through the callback kind; `0x02` would make `text_init` return -3), for AVR):

```c
/* text_cb.c - draw UTF-8 with a face embedded by c/bench/mkface.py through your own pixel routine. */
#include <stdint.h>
#include <string.h>
#include "svf.h"

extern const uint8_t neodg16g[];            /* face.c from mkface.py --name neodg16g */
extern const uint32_t neodg16g_len;

/* Your display driver: one pixel, on/off (or a grey level from cov). */
void lcd_set_pixel(int16_t x, int16_t y, uint8_t on);

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	(void)ctx;
	lcd_set_pixel(x, y, cov >= 128);
}

static svf_face face;                       /* must outlive every draw */
static svf_face *faces[1] = {&face};
static svf_chain chain;
static svf_target target;
static uint8_t scratch[32];                 /* >= svf_chain_scratch_bytes(&chain): 16 x 16 x 1 bpp */

int text_init(int16_t lcd_w, int16_t lcd_h)
{
	if (svf_open_mapped(&face, neodg16g, neodg16g_len) != SVF_OK)
		return -1;
	memset(&chain, 0, sizeof chain);
	chain.faces = faces;
	chain.count = 1;
	chain.missing_advance = 8;
	if (svf_chain_scratch_bytes(&chain) > sizeof scratch)
		return -2;
	if (svf_target_init(&target, SVF_T_COVERAGE_CB, NULL, 0, lcd_w, lcd_h, 0) != SVF_OK)
		return -3;
	target.plot = plot;
	return svf_is_jamo(&face) && svf_status(&face) == 0 ? 0 : -4;   /* -4: opened plain: svf_status says why */
}

/* Draws s with its top-left at (x, y_top); returns the width drawn (the pen's travel). */
int text_draw(const char *s, int16_t x, int16_t y_top)
{
	svf_extent e;
	if (svf_measure_utf8(&chain, s, strlen(s), &e) != SVF_OK)
		return -1;
	if (svf_draw_utf8(&chain, s, strlen(s), x, (int16_t)(y_top + svf_ascent(&face)), &target, scratch,
	                  sizeof scratch) != SVF_OK)
		return -1;
	return e.width;
}
```

`svf_is_jamo` is 1 for a face that composes Hangul and `svf_status` is 0 when nothing was dropped (section 4.3). A face
that opens but is plain (`JSET_BAD`, `JSET_UNREAD`, `JMAP_UNREAD`) draws Latin and silently no Hangul; this check is
how you find out on the bench, not in the field. A precomposed face has no jamo block, so check `svf_has(&face, 0xD55C)`
for it instead.

### 5.3 C++ and Arduino: keep `face.c` a C file

Generate the array into a `.c` file and let the C compiler build it. In C++ a namespace-scope `const` array has
internal linkage and a C++ name, so the linker would not find it from another file; the Arduino build compiles `.c`
files in the sketch folder as C. Declare it in the C++ side with C linkage (as `c/ports/arduino/arduino.ino` does):

```cpp
#include <avr/pgmspace.h>
#include "svf.h"                          /* svf.h is wrapped in extern "C" for C++ itself */

extern "C" {
extern const uint8_t neodg16g[] PROGMEM;  /* face.c, from mkface.py */
extern const uint32_t neodg16g_len;
}

static svf_face face;
bool face_ok() { return svf_open_mapped(&face, neodg16g, neodg16g_len) == SVF_OK; }
```

### 5.4 Licences to ship

A program or image with a face in it distributes font software. Ship with it: the face's own licence text (for NEODG16G,
`svf/dos/OFL.TXT` and `svf/dos/NEODGM.TXT`; for PAPLG16 and PAPLG18 `svf/dos/OFLPAPLG.TXT`; `web/LICENCES.tsv` maps every
face under `svf/` to its licence files), [NOTICE.md](../NOTICE.md) (what is under which licence), and
[LICENSE](../LICENSE) (MIT, for the library's code). `c/ports/FACES.md` names the source, copyright and licence of each
face the ports embed; the Pico, ESP32 and CH582 builds copy it and the licence texts to `<build>/licences/`.

## 6. Choosing a face for your target

A face is a file; its size, not its pixel size, decides where it fits. Measure the one you mean to use:

    python3 c/bench/mkface.py svf/dos/NEODG16A.SVF x.c --name x --profile mcu-strict && tail -2 x.c

The last line, `const uint32_t x_len = 15528u;`, is the number in the table below: the bytes you link. Measured on this
repository's faces, `mcu-strict`:

| Face | Cell, bits | Hangul | Array bytes | Cell bytes | Stream tables | Uno | CH582 | Pico | ESP32 |
|---|---|---|---:|---:|---:|---|---|---|---|
| `PAPLG16` | 18x18, 2 | none (ASCII, 149 glyphs) | 7,460 | 90 | 2,396 | yes | yes | yes | yes |
| `NEODG16G` | 16x16, 1 | jamo (composes all 11,172) | 10,124 | 32 | 5,129 | yes | yes | yes | yes |
| `NEODG16A` | 16x16, 1 | jamo | 15,528 | 32 | 8,153 | yes | yes | yes | yes |
| `NEODG16C` | 16x16, 1 | jamo | 19,088 | 32 | 9,721 | no | yes | yes | yes |
| `NDGPR16` (`svf/jamo-extra`) | 16x16, 1 | jamo | 25,532 | 32 | 15,519 | no | yes | yes | yes |
| `NEODG32` | 36x36, 1 | jamo | 30,616 | 180 | 8,153 | no | yes | yes | yes |
| `SGDAY16` (`svf/jamo-extra`) | 16x16, 1 | jamo | 38,204 | 32 | 23,117 | no | yes | yes | yes |
| `NSQRR16` (`svf/jamo-extra`) | 16x16, 1 | jamo | 53,204 | 32 | 30,365 | no | yes | yes | yes |
| `PAPLG18` | 18x18, 2 | jamo | 67,200 | 90 | 29,341 | no | yes | yes | yes |
| `NEODG16` | 16x16, 1 | precomposed (2,905 glyphs) | 127,908 | 32 | 46,492 | no | yes | yes | yes |
| `NGOTB15` | 16x16, 2 | precomposed (2,446 glyphs) | 178,352 | 64 | 39,148 | no | yes | yes | yes |
| `GBATB47` | 46x54, 2 | precomposed (2,446 glyphs) | 1,162,764 | 648 | 39,148 | no | no | yes | needs a bigger partition |

- **Hangul.** A jamo-set face stores a few hundred pieces and composes every syllable; a precomposed face stores one
  glyph per syllable it covers (the common 2,350 of KS X 1001 and a few more), so it is several times larger for the same
  pixel size (NEODG16 against NEODG16A: 8 times) and cannot draw the rest. For a small device take a jamo face.
- **Uno** (ATmega328P, 32,256 bytes of flash with Optiboot, 2 KB of RAM): the NEODG16G sketch is 23,694 bytes of flash
  with its 10,124 byte face, so 13,570 bytes are code; the face must be at most 18,686 bytes (13,570 + 15,528 = 29,098
  fits, 13,570 + 19,088 = 32,658 does not). The jamo faces open and compose with the Uno switches (checked on the
  host with them: `SVF_JSET_V2=0`, no `JMAP`, no `BIG`).
- **CH582**: 448 KB of CodeFlash; the image is about 12 KB of code without its face, so a face up to about 400 KB fits.
  RAM (32 KB) is not the limit for a mapped face.
- **Pico**: 2 MB of flash on the Pico board (4 MB on the Pico 2), executed in place; the whole mono image is 35,484
  bytes with its 10,124 byte face (section 13.5). Every face above fits; the larger the face, the more the XIP cache
  (16 KB on the RP2040) misses.
- **ESP32-C3 / S3**: module flash is typically 4 MB and the default partition table has a 1 MB application partition:
  the mono image is 229,648 bytes with its face (about 220 KB without), so every face but GBATB47 fits it; GBATB47
  goes in its own data partition (section 13.4).
- **Streaming** (a file on SD, SPIFFS or disk) needs RAM for the tables (the column above, for the shipped file) plus
  a block cache; the Uno cannot (`NEODG16G` alone needs 5,129 bytes of tables, and the Uno build leaves the reader out).
- **RAM** for drawing is small: scratch is one cell (`Cell bytes`, section 11) plus your frame buffer.

## 7. Lines of text: chains, metrics, measuring

### 7.1 Fallback chains

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

### 7.2 Marks, advances, invalid UTF-8

- Advances come from the face's metrics table (variable width); a face without one advances by the cell width. A composed
  syllable advances by the jamo block's syllable advance (or the cell width).
- Combining marks advance 0 and are drawn over the previous glyph. The default predicate is U+0300..U+036F; the core
  carries no Unicode tables, so pass your own `chain.is_mark` for more.
- Invalid UTF-8 never crashes and never reads past `len`: each bad subpart is drawn as U+FFFD if a face has it, else skipped
  without advancing. NUL is an ordinary code point (`len` bytes are drawn, not a C string).

### 7.3 Measuring before drawing

`svf_measure_utf8(&chain, s, len, &e)` gives `e.width`, `e.ascent`, `e.descent` using exactly the layout rules of the
draw, without reading any glyph (so it is cheap, and a streamed face does no I/O). Use it for centring, right-aligning,
word wrap and for sizing the buffer you draw into. `e.width` is the pen's **travel**, not the extent of the ink: the
last cell can reach past it (up to a cell width), so add `svf_cell_w(face)` when you size a buffer (section 3). Words and lines are yours: the library draws one line at a time and
knows nothing about wrapping.

## 8. Targets: where the pixels go

A target converts each drawn pixel's coverage to your format. You choose the kind with `svf_target_init`:

    svf_err svf_target_init(svf_target *t, svf_target_kind kind, uint8_t *buf, size_t buf_len,
                            int16_t w, int16_t h, uint16_t stride);

| You draw to | Use | Notes |
|---|---|---|
| A 32-bit framebuffer or SDL surface (B, G, R, X in memory: the dword `0x00RRGGBB` on a little-endian machine) | `SVF_T_XRGB8888` | set `t.fg888`, `t.bg888` as `0x00RRGGBB` |
| 24-bit | `SVF_T_RGB888` | same fields |
| 16-bit colour LCD | `SVF_T_RGB565` / `SVF_T_RGB555` | `t.fg565`, `t.bg565`; `SVF_TF_RGB16_BIGENDIAN` in `t.flags` for high byte first (its older name, `SVF_TF_565_BIGENDIAN`, is the same bit) |
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

### 8.1 Colour text on a 32-bit surface

```c
svf_target t;
svf_target_init(&t, SVF_T_XRGB8888, surface_pixels, (size_t)pitch * height, width, height, (uint16_t)pitch);
t.fg888 = 0x00FFC000;      /* amber text */
t.bg888 = 0x00000020;      /* the background colour the caller knows */
```

`stride` is a `uint16_t` number of bytes, so a 32-bit target is at most 16,383 pixels wide. The pixel's **memory order is
B, G, R, X on every host**; as one native 32-bit value that is `0x00RRGGBB` only on a little-endian machine (x86, ARM,
RISC-V, WebAssembly). On a big-endian host write the four bytes yourself.

### 8.2 The callback target: the universal adapter

When your pixel format is not one of the above, or you want to blend over existing content, or the destination is another
library's surface, use the callback. The library calls `plot(ctx, x, y, coverage)` once for each pixel with coverage above
0 inside the clip, row by row, with no buffer involved. This example blends white text over a 32-bit surface that already
contains a picture (compiled and run against `NEODG16A.SVF`; it reads and writes the pixel as one little-endian
`uint32_t`, B in the low byte, matching the memory order B, G, R, X):

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

## 9. Scaling

Set `chain.scale_num` and `chain.scale_den` (each 1 to 16; 0 and 0 mean 1/1). A whole multiple (`2/1`, `3/1`) draws every
source pixel as an N x N block, so bitmap edges stay hard. Any other ratio is area-averaged into 8-bit coverage, so
`3/2` of a 1 bpp face gets grey edge pixels (use a colour or grey target for it; on a mono target the threshold decides).
Lengths scale with rounding half up (symmetric), so the measured extent equals what is drawn. `x`, `y_baseline` and the clip
are always in output pixels.

Scratch grows with scaling. A scaled line needs, for the largest face of the chain, **twice the stored cell plus the
scaled cell**:

    scratch = 2 * svf_cell_bytes(face) + ceil(cell_w * num / den) * ceil(cell_h * num / den)

The scaled cell is 8-bit coverage, one byte a pixel; the formula is the same for a mapped and a streamed face, with or
without a block cache (at 1/1 the need is one cell, two for a streamed face without a cache). `svf_chain_scratch_bytes`
computes it: always recompute after changing the scale. Measured for the 16x16 1 bpp `NEODG16A` (a 32 byte cell): 3/2
needs 2 x 32 + 24 x 24 = 640 bytes, 2/1 needs 2 x 32 + 32 x 32 = 1,088, 1/2 needs 2 x 32 + 8 x 8 = 128.

For small MCU builds `-DSVF_NO_SCALE` removes scaling entirely (any ratio but n/n is then `SVF_E_ARG`), and the fast
scaler's stack frame is about 610 to 680 bytes; see `svf.h` "Scaling" before using it on a 2 KB RAM chip.

## 10. Hangul: jamo faces and syllable composition

A **precomposed** face stores one glyph per syllable it covers. A **jamo-set** face (header flag bit 1, `svf_is_jamo(f)`)
stores a few hundred small pieces and a table that says which pieces form each syllable. `svf_draw_utf8` composes
U+AC00..U+D7A3 (and compatibility jamo U+3131..U+3163) from the pieces on the fly: the maximum coverage of two or three
pieces. You do nothing special; just draw Hangul text. One qualification: the syllable table can be partial. A version 3 JMAP block
that is SPARSE (a bitmap and its entries) or LIST (a sorted list of up to 255 exceptions) and has **no fallback** block
composes only the syllables it lists: `svf_has` is 0 for the others and they are drawn as missing glyphs
(`missing_advance`); with a fallback block, a syllable the table does not list goes to the fallback. Dense JMAP and
version 1 and 2 blocks cover all 11,172.

```c
if (svf_is_jamo(&face)) {
	uint16_t pieces[3];
	int n = svf_jamo_pieces(&face, 0xD55C /* 한 */, pieces);   /* 3: initial, medial, final */
	for (int i = 0; i < n; i++)
		printf("piece %u\n", (unsigned)pieces[i]);               /* glyph U+F0000 + number in the face */
}
uint8_t cell[64];                                      /* >= svf_cell_bytes(&face) */
svf_glyph(&face, 0xD55C, cell, sizeof cell);           /* the composed cell, MSB first, rows padded to bytes */
```

`svf_glyph` and `svf_compose` return the cell of one code point without a target: useful for caching glyphs in your own
atlas.

### 10.1 What your build reads

Jamo blocks come in versions 1, 2 and 3 (JMAP, with a LIST form). The default desktop/DOS/WASM/SDL build reads them
all (but not under `-DSVF_SMALL`, section 12). A small-MCU build reads fewer (see the table in [c/README.md](../c/README.md), "Jamo sets: what each build reads").
A face the build cannot read still opens, as a **plain** face with a status bit; it simply does not compose Hangul. Faces
for your own application: build the faces the same way the repository's tools do, and check `svf_status` at load time.

### 10.2 The composed-syllable cache

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

## 11. Memory budget

All memory is yours. Add up:

| Item | Size |
|---|---|
| `svf_face` | `sizeof(svf_face)`: 96 bytes on a 64-bit host with `SVF_JMAP` (80 without; smaller on MCUs; 96 is the cap) |
| `svf_chain`, `svf_target` | a few tens of bytes each |
| Scratch | `svf_chain_scratch_bytes(&chain)`: one cell (`svf_cell_bytes`), twice that for a streamed face without a block cache; when scaling, **twice the cell plus the scaled cell** (section 9) |
| Streamed face | `svf_stream_tables_size(...)` for the tables, plus `slots * (block_size + 8)` for the optional cache |
| Syllable cache | `slots * (8 + largest cell bytes)` |
| Target buffer | `rows * stride` (or none for the callback kind) |
| Mapped face | the file itself, in RAM or flash (a `const` array or PROGMEM face costs no RAM, section 5) |
| Stack | the scaler's own frame: about 610 bytes on AVR, 680 on Cortex-M0+ with the default fast scaler |

A 16x16 1 bpp cell is 32 bytes; a 24x24 2 bpp cell is 144 bytes.

## 12. Compile-time switches: three recipes

Switches are `-D` flags given to **every** source (section 2). You almost never need them on a desktop. The ones that
matter for choosing a recipe:

- **Desktop, DOS, WASM, SDL, ScummVM-class applications: no switches.** Everything is on.
- **A small MCU with one display:** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_TARGETS=<one kind's bit> -DSVF_JSET_V2=0
  -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, and write faces with the matching profile (`tools/jamoset.py`
  `mcu-strict`; the shipped faces already have that layout, `c/bench/mkface.py --profile mcu-strict` shrinks their
  offsets, section 5). The Arduino Uno build uses exactly this: see [c/ports/arduino/README.md](../c/ports/arduino/README.md).
- **Smallest code on any CPU:** `-DSVF_SMALL` turns off the speed-oriented fast paths (word merge, the GRAY8 table, the
  fast scaler, the nibble popcount table); pixels are identical, only speed is lost. **It also changes what the build
  reads**: it flips the *defaults* of `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG` and `SVF_JSET_BIG` to 0 (they are 1 by
  default only without `SVF_SMALL`; measured with `gcc -dM -E`). A `SVF_SMALL` build on a desktop, DOS or WASM therefore
  no longer reads version 3 (JMAP, LIST) jamo blocks or the BIG limits: a face that needs them opens **plain**, with
  `SVF_FACE_JSET_BAD` set (`SVF_FACE_JMAP_UNREAD` only with `-DSVF_JMAP_RECOG=1`), and draws no Hangul. Add `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`
  (`SVF_JMAP_LIST` follows `SVF_JMAP`) if you need them.

The complete switch table with defaults per toolchain is in [c/README.md](../c/README.md), "Compile-time switches", and
the sizes each configuration produces are in `c/cross/SIZES.md`.

## 13. Platforms

One subsection per platform: the toolchain and versions the example was built with here, how to build it, what to take
into a project of your own (files and flags), the glue between `svf_target` and the platform's pixels, the measured
memory, and the limits. The port READMEs under `c/ports/<port>/` have the rest. The ports were built here and, for Pico
and ESP32 (colour), run on emulators; none has been run on its board (each README says what was checked), and the
Arduino instructions were never run through `arduino-cli`. A figure marked "measured" was printed by a build made for this
guide from a clean `git archive` of the repository.

### 13.1 Arduino Uno and other Arduino cores

- **Toolchain.** avr-gcc 16.1.0 with AVR-LibC 2.3.2 (the Zak Kemble build that `sh c/cross/install-toolchains.sh "$HOME/opt" avr`
  installs under `~/opt`), `-Os`. arduino-cli is not installed here, so the commands below were not run against a stock
  AVR core: they are the settings `c/cross/build-all.sh --ports` uses for the same sources, which it compiles and links
  against `c/ports/arduino/stub/`. Record your own core's avr-gcc version; the library is C99 and needs no more.
- **Build** (from the repository root; the library goes in as an Arduino library, the generated `face.c` into the sketch
  folder, not committed):

      mkdir -p ~/Arduino/libraries/svf && cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
      python3 c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
      F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
      arduino-cli compile -b arduino:avr:uno c/ports/arduino \
          --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"

- **For your own sketch.** Copy `svf.h`, `svf_internal.h` and `svf_*.c` into a library folder, put the generated `face.c`
  beside your `.ino`, declare it `extern "C"` (section 5.3), and give the C and C++ compiles the flags above. They go to
  `compiler.c.extra_flags` and `compiler.cpp.extra_flags`, **not** to `build.extra_flags`: the AVR core passes that to its
  assembler sources too, and `-include avr/pgmspace.h` fails there. `-DSVF_JSET_V2=0` builds the version 1 reader alone
  (NEODG16G is a version 1 face; the version 2 reader would cost about 2.4 KB), `-DSVF_TARGETS=0x02` compiles only
  `MONO_PAGE`, `-DSVF_NO_STREAM` drops the stream reader, `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` makes the layout units
  constants.
- **Pixel glue.** A 128 x 64 SSD1306 page buffer is 1,024 bytes; the target writes straight into the controller's layout,
  and `Wire` sends it 16 bytes at a time (its buffer is 32 bytes):

  ```cpp
  static uint8_t page[128 * 64 / 8];
  svf_target_init(&t, SVF_T_MONO_PAGE, page, sizeof page, 128, 64, 128);      /* stride: bytes per page */
  /* ... svf_draw_utf8(...) ..., then per 16 bytes: */
  Wire.beginTransmission(0x3C); Wire.write(0x40); Wire.write(page + i, 16); Wire.endTransmission();
  ```

  Text kept in `PROGMEM` is copied to RAM before drawing (`strncpy_P(text, lines[i], sizeof text - 1)`): the library reads
  the string with plain loads.
- **Memory (measured, ATmega328P).** `c/cross/build-all.sh --ports`: 23,694 bytes of flash (text 23,676 plus data 18) of
  32,256, the face being 10,124; 1,103 bytes of RAM before the stack, of which the page buffer is 1,024. The real `Wire`
  adds about 200 bytes of buffers and the core a few dozen, leaving about 700 bytes of stack.
- **Limits.** Scaling is off (`-DSVF_NO_SCALE`): a scaled draw needs about 864 bytes of stack beside a 1 KB page buffer,
  so build with `-DSVF_SCALE_FAST=0` (451 bytes, measured statically) if you must. A version 2 face opens plain without
  the version 2 reader; a version 3 face opens **plain** (`SVF_FACE_JSET_BAD`: `SVF_JMAP` and `SVF_JMAP_RECOG` are 0 on AVR); add `-DSVF_JMAP_RECOG=1` to recognise the block (`JMAP_UNREAD`) and read a version 1 fallback JSET it carries (from `svf.h` and `c/README.md`; not built here). Streaming does not fit: the tables
  alone are 5,129 bytes. **Arduino Mega 2560**: the same sketch links for the ATmega2560 (23,820 bytes of flash), but faces
  and data above 64 KB of flash need far reads (`pgm_read_byte_far`), which the library does not do: not supported, not
  tested (the build prints a `FLAG` line when a Mega image's flash end reaches 65,536). **Other cores** (SAMD, RP2040,
  ESP32 under the Arduino IDE): flash is memory-mapped, so build the library as ordinary C with no `SVF_RD8` override
  and no `PROGMEM`; `mkface.py` already emits a plain `const` array there. Not tried here. Details:
  [c/ports/arduino/README.md](../c/ports/arduino/README.md).

### 13.2 WCH CH582 (RISC-V, bare metal)

- **Toolchain.** `riscv32-esp-elf-gcc` 16.1.0 (crosstool-NG esp-16.1.0_20260609, `sh c/cross/install-toolchains.sh "$HOME/opt" esp`),
  the WCH CH583 EVT sources that this port uses for the CH582M (commit `bd508ad` of
  github.com/openwch/ch583) and `wchisp` 0.3.0 to flash. xPack `riscv-none-elf-gcc` 15.2.0-1 is documented as an
  alternative (`CROSS=riscv-none-elf-`), not installed here.
- **Build and flash** (24 MHz; the board's BOOT button held while plugging in the Type-C cable):

      sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
      make -C c/ports/ch582            # build/svf_ch582_mono.{elf,bin,hex,map}, build/licences/
      make -C c/ports/ch582 flash

- **For your own project.** Compile `c/src/*.c` and your generated `face.c` with
  `-march=rv32imac_zicsr_zifencei -mabi=ilp32 -mcmodel=medany -msmall-data-limit=8 -mstrict-align -Os -std=c99` and
  `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0` (the same
  switches as the Uno: mapped face, one layout, `MONO_PAGE`, the version 1 reader). The WCH start-up code, the SDK
  sources (`CH58x_gpio.c`, `CH58x_i2c.c`, `CH58x_sys.c`) and `link.ld` come from the EVT tree; read the port's Makefile for
  their flags (`-DINT_SOFT -w`, `-std=gnu99` for the port's own files). The face is a `const` array in CodeFlash.
- **Pixel glue.** The panel is a 128 x 64 SH1106 on hardware I2C (PB20 SDA, PB21 SCL, address 0x3C), driven through the
  port's `display_show(const uint8_t *buf, int16_t y, int16_t rows)` over `int ch582_i2c_write(uint8_t addr, const
  uint8_t *buf, size_t n)` (0 on success, -1 on a timeout or NACK, bounded by `CH582_I2C_SPIN`). The frame is a 1,024
  byte `MONO_PAGE` buffer as in section 13.1: `svf_target_init(&t, SVF_T_MONO_PAGE, frame, sizeof frame, 128, 64, 128)`.
- **Memory (measured).** `.bin` 21,068 bytes; text 22,456 (faces 10,124), data 20, bss 1,232, `.highcode` 2,576 (it lives in
  RAM); RAM used 5,876 of 32,768 with a 2,048 byte stack; stack peak of `main` 640.
- **Limits.** The image runs at 24 MHz (the I2C module clock must be 2..36 MHz); `FREQ_SYS` in the Makefile must match
  `SetSysClock`. **Not yet tried on a panel**: the pin mapping, panel variants (SH1106 or a real SSD1306, column offset)
  and the LED outcome codes are in the README. Details: [c/ports/ch582/README.md](../c/ports/ch582/README.md).

### 13.3 DOS (DJGPP)

- **Toolchain.** DJGPP `i586-pc-msdosdjgpp-gcc` 12.2.0 with binutils 2.30 (build-djgpp v3.4) in `~/opt/djgpp`; DOSBox-X
  2026.08.31 to run it. The program is a 32-bit protected-mode `.EXE` that needs a DPMI host: **`CWSDPMI.EXE`** must be in
  the program's directory or on `PATH` on real DOS (DOSBox-X has one built in).
- **Build** (measured: `SVFDEMO.EXE` 266,265 bytes, `SVFVESA.EXE` 294,345):

      DJ=~/opt/djgpp/bin/i586-pc-msdosdjgpp
      $DJ-gcc -std=gnu99 -O2 -Ic/include c/ports/dos/svfdemo.c c/src/*.c -o SVFDEMO.EXE
      $DJ-gcc -std=gnu99 -O2 -Ic/include -Ic/ports/dos c/ports/dos/svfvesa.c c/ports/dos/vbe_select.c \
          c/ports/dos/vesa_lines.c c/src/*.c -o SVFVESA.EXE

- **For your own project.** `c/src/*.c` and `-I c/include`, no switches: `__DJGPP__` selects the full defaults (every
  target kind, streaming, scaling, JMAP, BIG). `-std=gnu99`, not `-std=c99`: under strict `-std=c99` DJGPP's headers
  hide POSIX names such as `lseek` (measured: an implicit-declaration warning). **8.3 names:** on a DOS without long file names the face file must be a bare 8.3 name
  in upper case (`NEODG16A.SVF`; every face under `svf/dos` already is), and a data file such as `vesa-lines.txt` must
  be copied as `VESALINE.TXT`. Open files with **`O_BINARY`** (DJGPP defaults to text mode).
- **Streamed or mapped.** `svfdemo.c` streams both faces (`svf_open_stream`, a `read_file` callback with `lseek` + `read`,
  1 KB blocks in a block cache: PAPLG16 16 slots, PAPLG18 64 slots), so a 1 MB face does not need 1 MB of RAM. To map
  instead, read the file whole and open it in place (compiled here with DJGPP 12.2.0):

  ```c
  /* dos_mapped.c - DJGPP: a face file read whole into memory and opened mapped. */
  #include <fcntl.h>
  #include <stdlib.h>
  #include <unistd.h>
  #include "svf.h"

  svf_err load_face(svf_face *f, const char *path)       /* path: a bare 8.3 name such as NEODG16A.SVF */
  {
  	int fd = open(path, O_RDONLY | O_BINARY);           /* O_BINARY: DJGPP opens in text mode by default */
  	off_t len;
  	uint8_t *bytes;

  	if (fd < 0)
  		return SVF_E_IO;
  	len = lseek(fd, 0, SEEK_END);
  	lseek(fd, 0, SEEK_SET);
  	bytes = len > 0 ? malloc((size_t)len) : NULL;       /* keep it: the face reads it in place while it draws */
  	if (!bytes || read(fd, bytes, (size_t)len) != len) {
  		free(bytes);
  		close(fd);
  		return SVF_E_IO;
  	}
  	close(fd);
  	return svf_open_mapped(f, bytes, (size_t)len);
  }
  ```

- **Pixel glue.** Mode 13h: draw into a 320 x 200 `GRAY8` buffer, set the palette to a grey ramp so a coverage byte is its
  own colour index (`outportb(0x3C8, 0)` then three `outportb(0x3C9, i >> 2)` per entry), set the mode with
  `__dpmi_int(0x10, &regs)` (`regs.x.ax = 0x13`; `0x03` returns to text) and copy the buffer with
  `dosmemput(screen, sizeof screen, 0xA0000)`. For VBE 2.0 linear-framebuffer modes (8, 15, 16, 24, 32 bits) use
  `svfvesa.c`: the packed target kinds, mode chosen by geometry and channel layout, rows copied with `movedata`.
- **Memory.** `svfdemo.c`: tables 4,096 + 32,768 bytes, caches 16 x 1,032 + 64 x 1,032 bytes, scratch 180, the 64,000 byte
  screen buffer. Cache slots must cover the blocks one line touches, or the same blocks are read again and again.
- **Limits.** A mapped face is a `malloc` in DJGPP's protected-mode heap, bounded by the machine's extended memory; stream
  big ones. The headless run and the exact-pixel checks are in [c/ports/dos/README.md](../c/ports/dos/README.md).

### 13.4 ESP32 (ESP-IDF)

- **Toolchain.** ESP-IDF **v5.5.6** (the version built here, in `~/opt/esp-idf-v5.5.6`; export its environment with
  `. $IDF_PATH/export.sh`, or pass `-DIDF_PATH=`), with the toolchains it installs. The port covers the **ESP32-C3**
  (RISC-V) and **ESP32-S3** (Xtensa); the original ESP32 has size rows (`xtensa-esp32-elf-gcc` 16.1.0) but no port image
  (its flash pins and the usual boards' wiring differ from the port's pin tables).
- **Build** (one build directory per profile and chip; `main/CMakeLists.txt` generates the face arrays with `mkface.py`):

      cd c/ports/esp32
      idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3 && idf.py -B build-colour build flash monitor
      idf.py -B build-grey   -DSVF_PROFILE=grey   set-target esp32s3 && idf.py -B build-grey build
      idf.py -B build-mono   -DSVF_PROFILE=mono   set-target esp32c3 && idf.py -B build-mono build

  `idf.py` writes `sdkconfig` and `sdkconfig.old` into the project directory (`c/ports/esp32/.gitignore` lists them).
- **For your own project.** Make the library a component: copy `svf.h`, `svf_internal.h` and `svf_*.c` into `main/svf/` and
  generate `face.c`:

  ```cmake
  # main/CMakeLists.txt
  file(GLOB SVF_SRCS svf/*.c)
  idf_component_register(SRCS main.c face.c ${SVF_SRCS} INCLUDE_DIRS svf REQUIRES esp_partition spiffs)
  target_compile_definitions(${COMPONENT_LIB} PRIVATE SVF_NO_SCALE SVF_TARGETS=0x08)   # one kind: RGB565 here
  ```

  Every source that includes `svf.h` must see the same `-D` switches (section 2): `target_compile_definitions` on the
  component does that. This component form was built here with ESP-IDF v5.5.6 for the ESP32-S3.
- **The face.** A `const` array in flash needs nothing else. A face in its own data partition is memory-mapped with no RAM
  copy; a face on SPIFFS is streamed through stdio (tables and block cache in RAM). Both compile with ESP-IDF v5.5.6
  (`esp_faces.c`, built as a component here for the ESP32-S3):

  ```c
  /* esp_faces.c - ESP-IDF: (a) a face in its own flash partition, memory-mapped (no RAM copy);
   * (b) a face file on SPIFFS, streamed through stdio (tables + block cache in RAM). */
  #include <stdio.h>
  #include "esp_partition.h"
  #include "esp_spiffs.h"
  #include "svf.h"

  /* (a) partitions.csv:  font, data, 0x40, , 256K   then: parttool.py write_partition --partition-name font --input FACE.SVF */
  static esp_partition_mmap_handle_t font_map;

  /* face_len: the face's size in bytes (store it when you write the partition); passing p->size also works: the 0xFF padding after the face opens with status 0 */
  svf_err face_from_partition(svf_face *f, uint32_t face_len)
  {
  	const esp_partition_t *p = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x40, "font");
  	const void *ptr;
  	if (!p || face_len > p->size)
  		return SVF_E_IO;
  	if (esp_partition_mmap(p, 0, p->size, ESP_PARTITION_MMAP_DATA, &ptr, &font_map) != ESP_OK)
  		return SVF_E_IO;
  	return svf_open_mapped(f, (const uint8_t *)ptr, face_len);   /* keep the mapping for the face's lifetime */
  }

  /* (b) streamed from SPIFFS: mount once at start-up, then open faces */
  static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
  {
  	FILE *fp = ctx;
  	return fseek(fp, (long)off, SEEK_SET) == 0 ? (long)fread(dst, 1, len, fp) : -1;
  }
  static uint8_t tables[16 * 1024], cache[8 * (512 + 8)];   /* one face at a time */

  esp_err_t spiffs_mount(void)                                /* call once */
  {
  	esp_vfs_spiffs_conf_t conf = {.base_path = "/spiffs", .partition_label = NULL, .max_files = 2,
  	                              .format_if_mount_failed = false};
  	return esp_vfs_spiffs_register(&conf);
  }

  svf_err face_from_spiffs(svf_face *f, const char *path)
  {
  	FILE *fp = fopen(path, "rb");
  	long len;
  	size_t need;
  	svf_err e;

  	if (!fp)
  		return SVF_E_IO;
  	if (fseek(fp, 0, SEEK_END) != 0 || (len = ftell(fp)) <= 0) {
  		fclose(fp);
  		return SVF_E_IO;
  	}
  	need = svf_stream_tables_size(rd, fp, (uint32_t)len, &e);
  	if (!need) {
  		fclose(fp);
  		return e;
  	}
  	if (need > sizeof tables) {
  		fclose(fp);
  		return SVF_E_NOMEM;
  	}
  	e = svf_open_stream(f, rd, fp, (uint32_t)len, tables, sizeof tables, cache, sizeof cache, 512);
  	if (e != SVF_OK)
  		fclose(fp);                                          /* on success keep fp open: the face reads it while drawing */
  	return e;
  }
  ```

  Keep the mapping for as long as the face is drawn; `esp_partition_munmap(font_map)` releases it.
- **Pixel glue.** The port draws a colour band (320 x 24 `RGB565`, 15,360 bytes) and sends it with
  `spi_device_polling_transmit(spi_device_handle_t, spi_transaction_t *)` (ILI9341 on SPI2). The ILI9341 takes the high byte
  first, so set `t.flags = SVF_TF_RGB16_BIGENDIAN` (the older name `SVF_TF_565_BIGENDIAN` is the same bit); the QEMU RGB
  panel takes native words (flag 0). The port's `display_show(const uint8_t *buf, int16_t y, int16_t rows)` is the
  boundary a profile draws against.
- **Memory (measured, ESP-IDF v5.5.6, Release).** `.bin` of the colour profile on ESP32-C3 294,960 bytes (faces 74,660), grey
  on ESP32-S3 317,856, mono on ESP32-C3 229,648 (face 10,124); each in the default 1 MB application partition (72 %, 70 % and
  78 % free). `idf.py size`, colour on C3: flash code 109,930, `.rodata` 117,180, DRAM `.bss` 19,320 and `.data` 6,920;
  mono: `.bss` 4,920.
- **Limits.** Nothing here has run on an ESP32 board (the `esp_rgb` panel has run on QEMU 9.2.2); wiring, `MADCTL` and the
  panel variants are listed in the README. Details: [c/ports/esp32/README.md](../c/ports/esp32/README.md).

### 13.5 Raspberry Pi Pico and Pico 2 (pico-sdk)

- **Toolchain.** pico-sdk **2.3.1**, arm-none-eabi-gcc 15.2.1 (Arm GNU Toolchain 15.2.Rel1), CMake, Python 3 for the face
  arrays; picotool 2.3.1 to make a `.uf2` (see the port README).
- **Build.** One directory per profile; `-DPICO_NO_PICOTOOL=1` makes the `.elf` only. For a **Pico 2** (RP2350, Arm
  cores) add `-DPICO_BOARD=pico2`:

      cmake -S c/ports/pico -B build-pico-mono  -DSVF_PROFILE=mono -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
      cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
      cmake --build build-pico-mono

- **For your own project.** The port's `CMakeLists.txt` is the template: generate the face with an `add_custom_command`
  running `mkface.py`, add `c/src/*.c`, link `pico_stdlib` and the bus library, and define the switches on the target
  (this form was built here for the Pico and, with `-DPICO_BOARD=pico2`, the Pico 2; 33,988 and 32,340 bytes of text
  with a `main.c` that draws into an RGB565 band):

  ```cmake
  file(GLOB SVF_SRCS svf/c/src/*.c)
  add_executable(app main.c face.c ${SVF_SRCS})
  target_include_directories(app PRIVATE svf/c/include)
  target_compile_definitions(app PRIVATE SVF_NO_SCALE SVF_TARGETS=0x08)      # RGB565 only
  target_link_libraries(app pico_stdlib hardware_spi)
  ```

- **Pixel glue.** I2C panels: `i2c_write_blocking(i2c0, addr, buf, len, false)` (SSD1306 mono at GP4/GP5, address 0x3C); SPI
  colour: `spi_write_blocking(spi0, buf, len)` (ST7789 on GP16..GP20). The ST7789 takes RGB565 high byte first:
  `t.flags = SVF_TF_RGB16_BIGENDIAN`. The port draws the colour profile in 24-row bands (240 x 24 x 2 = 11,520 bytes) and
  calls `display_show(band, y, 24)`.
- **Memory (measured, `arm-none-eabi-size`, Release, the faces included).**

  | Image | Pico (RP2040) text / bss | Pico 2 (RP2350) text / bss |
  |---|---|---|
  | mono (NEODG16G, 10,124) | 35,484 / 2,384 | 33,636 / 2,000 |
  | grey (PAPLG16 + PAPLG18, 74,660) | 99,256 / 17,936 | 97,420 / 17,552 |
  | colour (PAPLG16 + PAPLG18) | 99,828 / 12,812 | 98,176 / 12,428 |

  The Pico column equals the "Pico SDK images" table of `c/cross/SIZES.md`.
- **Limits.** The faces sit in flash behind the **XIP cache** (16 KB on the RP2040); the emulators used here (rp2040js,
  the bench) do not model it, so real drawing times are the emulated ones or slower, by an amount nothing here measures. The
  hardware has not been run. Pico 2 was built, not run. Details: [c/ports/pico/README.md](../c/ports/pico/README.md).

### 13.6 SDL2 and SDL3

- **Toolchain.** The host gcc 13.3.0; SDL 2.30.0 or newer (`libsdl2-dev`) or SDL3 (3.5.0-dev from the user's fork in
  `~/opt/sdl3`: any SDL3 that `pkg-config sdl3` finds builds the example). `c/ports/sdl/svfsdl.c` is one source for both
  (`sdl_compat.h`) and covers every SDL pixel format the kinds match.
- **A minimal sample** (SDL3; a face mapped from disk, one line at 2/1 scale in an `XRGB8888` surface, saved as BMP).
  Built and run here with SDL 3.5.0-dev under `SDL_VIDEODRIVER=dummy`:

  ```c
  /* sdl_min.c - SDL3: a face file mapped from disk, one line drawn into an XRGB8888 surface, saved as BMP. */
  #include <SDL3/SDL.h>
  #include <string.h>
  #include "svf.h"

  int main(int argc, char **argv)
  {
  	size_t len;
  	void *bytes = SDL_LoadFile(argc > 1 ? argv[1] : "NEODG16A.SVF", &len);   /* keep it while the face is used */
  	static svf_face face;
  	svf_face *faces[1] = {&face};
  	svf_chain chain = {0};
  	svf_target t;
  	uint8_t scratch[2048];                               /* 2/1 of 16x16: 2*32 + 32*32 = 1,088 */
  	const char *s = "SDL 한글 렌더링";

  	if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK)
  		return 1;
  	chain.faces = faces;
  	chain.count = 1;
  	chain.scale_num = 2;                                   /* 2/1: crisp double size */
  	chain.scale_den = 1;
  	if (svf_chain_scratch_bytes(&chain) > sizeof scratch)
  		return 1;
  	SDL_Surface *surf = SDL_CreateSurface(320, 48, SDL_PIXELFORMAT_XRGB8888); /* memory B G R X on little-endian */
  	if (!surf || !SDL_FillSurfaceRect(surf, NULL, SDL_MapSurfaceRGB(surf, 0, 0, 0x20)) || !SDL_LockSurface(surf))
  		return 1;
  	if (svf_target_init(&t, SVF_T_XRGB8888, surf->pixels, (size_t)surf->pitch * surf->h, (int16_t)surf->w,
  	                    (int16_t)surf->h, (uint16_t)surf->pitch) != SVF_OK)
  		return 1;
  	t.fg888 = 0x00FFC000;
  	t.bg888 = 0x00000020;                                  /* the colour the surface was filled with */
  	svf_err e = svf_draw_utf8(&chain, s, strlen(s), 4, (int16_t)(4 + 2 * svf_ascent(&face)), &t, scratch, sizeof scratch);
  	SDL_UnlockSurface(surf);
  	SDL_SaveBMP(surf, "out.bmp");
  	SDL_DestroySurface(surf);
  	SDL_free(bytes);
  	return e == SVF_OK ? 0 : 1;
  }
  ```

      export PKG_CONFIG_PATH=~/opt/sdl3/lib/pkgconfig
      cc -std=c99 -Wall -Wextra -I c/include sdl_min.c c/src/*.c $(pkg-config --cflags --libs sdl3) \
          -Wl,-rpath,$(pkg-config --variable=libdir sdl3) -o sdl_min
      SDL_VIDEODRIVER=dummy ./sdl_min svf/dos/NEODG16A.SVF

- **The full example.** `make -C c/ports/sdl SDL=2` or `SDL=3` builds `svfsdl2` / `svfsdl3`
  (`c/build/ports/sdl/`); `sh c/ports/sdl/check.sh` proves the surface bytes against `tools/svfline.py` on both SDLs for
  every format (the dump, not the screenshot, is the proof).
- **Pixel glue.** `stride` is the surface's `pitch` (SDL rounds a row up to 4 bytes) and the surface must be locked
  (`SDL_LockSurface`) while you draw; clear it first (the library never writes padding, and the grey and indexed kinds
  keep the maximum of the old and new value). Name formats by **memory order**: `SDL_PIXELFORMAT_BGRX32` is
  `SVF_T_XRGB8888` (B, G, R, X in memory on every host; as a native `uint32_t` it is `0x00RRGGBB` only on a
  little-endian machine); `SDL_PIXELFORMAT_RGB24` has no matching kind. 16-bit kinds follow the host: add
  `SVF_TF_RGB16_BIGENDIAN` when `SDL_BYTEORDER` is big-endian.
- **Limits.** A 32-bit target is at most 16,383 pixels wide (a `uint16_t` stride); only little-endian was run. SDL2 and SDL3
  differ in how they widen RGB565 for display, not in the bytes the library writes. Details:
  [c/ports/sdl/README.md](../c/ports/sdl/README.md).

### 13.7 Web (WebAssembly, emscripten)

- **Toolchain.** emsdk tag **6.0.13** (emcc 6.0.13, installed by `sh c/cross/install-toolchains.sh "$HOME/opt" emsdk`, with
  node 24.19.0), `-O2`, `-std=c99 -Wall -Wextra -Werror`.
- **Build** (the line `web/build.sh` runs, kept in `c/ports/web/emcc-flags.sh`; measured `svf.wasm` 39,808 bytes,
  `svf.js` 6,937):

      EM_CONFIG=~/opt/emsdk/.emscripten ~/opt/emsdk/upstream/emscripten/emcc -std=c99 -Wall -Wextra -Werror -O2 \
          -Ic/include c/ports/web/svf_web.c c/src/*.c -o svf.js -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
          -sENVIRONMENT=web,node -sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16,HEAP32 \
          -sALLOW_MEMORY_GROWTH

  `web/build.sh [OUT]` does that and also writes `faces.json` and copies the faces and licences for the picker page.
- **For your own project.** Compile `c/ports/web/svf_web.c` with `c/src/*.c` and keep its exports
  (`svfw_open(slot, data, len)`, `svfw_target2(kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags)`,
  `svfw_scale`, `svfw_measure(text, len, out)`, `svfw_draw(text, len, x, baseline)`, `svfw_reset`, ... listed in
  [c/ports/web/README.md](../c/ports/web/README.md)), or write your own `EMSCRIPTEN_KEEPALIVE` glue over the C API. No
  switches: `__EMSCRIPTEN__` selects the full defaults.
- **Pixel glue.** JavaScript owns the target buffer (a view of the module's memory) and the face bytes; the C side
  draws into it. The kinds the glue exposes are `GRAY8`, `MONO_PAGE`, `MONO_ROW` and `RGB565` (flags 0 or
  `SVF_TF_RGB16_BIGENDIAN`, whose older name is `SVF_TF_565_BIGENDIAN`); copy the buffer to a `<canvas>` `ImageData` yourself.
- **Memory.** `svfw_draw` needs `svf_chain_scratch_bytes`: a static 64 KB first, then a `malloc` of exactly the need (a
  large scaled cell, e.g. GBATB47 at 16/1, needs 637 KB). This port is the only code that allocates; `c/src` never does.
- **Limits.** Face bytes must stay in the module's memory while a slot uses them: call `svfw_reset` before freeing them.
  At most four faces in the chain. `-sALLOW_MEMORY_GROWTH` moves the heap: re-take your `HEAPU8` view after any call
  that may grow it.

## 14. Integrating into an application with its own text path

Most applications already have a "draw this string at x, y with this colour" routine and a "how wide is this string"
routine. The renderer maps onto both:

| Application needs | Library call |
|---|---|
| Open the font at start-up | `svf_open_mapped` (face loaded into memory) or `svf_open_stream` (large faces, low RAM) |
| Width and height of a string | `svf_measure_utf8` (`width` is the pen's travel, not the ink; height = `ascent + descent`, or the face's `cell_h`) |
| Draw a string | `svf_draw_utf8` into a target |
| Draw into the application's own surface | `SVF_T_COVERAGE_CB` with the surface in `ctx` (section 8.2), or the target kind that matches its pixel format |
| Same string drawn every frame | the syllable cache (section 10.2), and cache your own rendered string bitmap |
| Per-glyph advance for your own layout | `svf_metrics_of`, or `svf_measure_utf8` on a single character |

Points that routinely cause trouble:

1. **Text encoding.** The library takes UTF-8. Applications that store text as CP949/EUC-KR, UHC or a game-specific
   code page must convert to UTF-8 (or to code points) before calling. There is no byte-pair guessing in the library.
2. **Baseline, not top.** `y_baseline` is the row under the glyph's ascent. To draw a line with its top at `top`, pass
   `top + e.ascent` (with `e` from `svf_measure_utf8`), or `top + svf_ascent(&face)`.
3. **Line height.** The extent's `ascent + descent` is the rows the cells of the measured text reach above and below the
   baseline (a cell's ascent and `cell_h - ascent`, moved by its `dy`), not the rows that have ink. For uniform line
   spacing use the faces' `cell_h`.
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

## 15. Testing your integration

- **The reference.** `tools/svfline.py` draws the same line in Python; its output must equal the C output byte for byte.
  `tools/test_c_renderer.py` is the repository's own comparison; read it for how to drive both sides.
- **The gate.** `make -C c check` runs the unit programs under sanitizers, verifies that no object references `malloc`,
  `calloc`, `realloc` or `free`, and runs the Python comparison.
- **Your own checks.** A tiny program that draws a known string into a `SVF_T_GRAY8` buffer and prints it (section 3) is
  the fastest way to see a layout problem. Compile your tests with `-fsanitize=address,undefined`.
- **Faces.** To see what a face file holds, run `c/build/svfdump FACE info` (header values, layout units, and the status
  bits `jset_bad`, `jset_unread`, `jmap_bad`, `jmap_unread`; `svfdump FACE has U+AC00 U+D55C` says whether each code
  point draws; `svfdump FACE syllables` dumps every composed syllable cell, the C side of the Python identity tests), or
  `jamoset.parse_svfn` in Python. `tools/facecheck.py` is **not** a face checker: it checks manifests and the faces
  a font map names. The maker app checks every face it writes and draws it before counting it done.

## 16. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `svf_open_mapped` returns `SVF_E_MAGIC` | not an SVFN file, or the file was read in text mode or truncated | open in binary mode; compare the length |
| `SVF_E_VERSION` | a version 2 file | convert with `tools/svf2to3.py` |
| `SVF_E_LAYOUT` | the build was compiled with `-DSVF_LAYOUTS=...` and the face uses another layout | write the face with the profile the build reads, or widen `SVF_LAYOUTS` |
| Hangul draws nothing but Latin works | the face is plain: check `svf_status` for `SVF_FACE_JSET_BAD`, `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD` | build with the readers the face needs (section 10.1) or rewrite the face |
| Hangul draws as missing-glyph spacing | no face in the chain has the code point | `svf_has(face, cp)`; add a face, set `missing_advance` |
| `svf_draw_utf8` returns `SVF_E_NOMEM` | scratch smaller than `svf_chain_scratch_bytes` (recompute after changing scale or faces) | enlarge scratch |
| `SVF_E_ARG` from `svf_target_init` | kind not in `SVF_TARGETS`, `buf_len < rows * stride`, stride too small, or w/h 0 | check each; for GRAY set `gray_bits` after init |
| `SVF_E_ARG` from `svf_draw_utf8` | a chain without faces; a scale ratio outside 1..16 or `SVF_NO_SCALE`; `INDEXED8` with a bad ramp; `COVERAGE_CB` without `plot` | check them |
| Text is missing on an `INDEXED8` target | the background index is not below the ink ramp (max rule) | renumber the palette |
| Colour text has a halo | `bg565`/`bg888` is not the real background | set the true background, or use the callback target |
| Glyphs one row too high or low | passed the top row instead of the baseline | `y_baseline = top + ascent` |
| `svf_open_mapped` returns `SVF_E_MAGIC` on an AVR build, the face being a `PROGMEM` array | the library was built without `-DSVF_RD8(p)=pgm_read_byte(p)`, so it reads flash addresses as RAM | build every library source with `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'` (section 5.1; simavr: 1 without, 0 with) |
| The face array eats RAM, or the link overflows RAM | the array was made with `xxd -i` (not `const`, so `.data`) | generate it with `c/bench/mkface.py` (section 5); check `size` shows the face under text, not data |
| Hangul draws nothing after adding `-DSVF_SMALL` | `SVF_SMALL` turns the defaults of `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG` and `SVF_JSET_BIG` off: a version 3 or BIG face opens plain (`JSET_BAD`; `JMAP_UNREAD` only with `-DSVF_JMAP_RECOG=1`) | add `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`, or write the face in a form the build reads (section 10.1, section 12) |
| Only some Hangul syllables draw, the rest are missing | the face's JMAP is SPARSE or LIST with no fallback block: it composes only the syllables it lists | `svf_has(face, cp)` per syllable; rebuild the face with a fallback or a dense table (section 10) |
| Text ends cut off at the right of the buffer | the buffer was sized from `e.width`, the pen's travel, but the last glyph's ink reaches past it | `e.width + svf_cell_w(face)` (section 3) |
| Crashes or garbage after upgrading | translation units built with different `-D` switches (`SVF_JMAP` changes `svf_face`) | rebuild everything with one flag set |
| `SVF_E_IO` on a streamed face | the read callback returned a short or negative count | return exactly `len` bytes or a negative value; check the file position logic |
