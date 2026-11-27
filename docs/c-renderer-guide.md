**English** | [한국어](c-renderer-guide.ko.md)

# SVF C renderer: integration guide

This guide shows how to put the SVF C renderer (`c/`) into your own program: how to get the source, open faces, embed a face in
firmware, choose a face that fits your target, draw UTF-8 text with Hangul syllables composed from jamo sets, choose a
drawing target, budget memory, build for supported platforms, and what to check when
something draws wrong. It is a tutorial. The reference is [c/README.md](../c/README.md) (API tables, compile-time
switches, ports) and, above all, the comments in [c/include/svf.h](../c/include/svf.h), which state the exact contract
of every function. The file format is [spec/SVF.md](../spec/SVF.md); the design is
[spec/renderer-design.md](../spec/renderer-design.md).

The portable C programs in sections 3–12 can be copied into separate files and built with `cc -std=c99 -Wall -Wextra -Ic/include EXAMPLE.c c/src/*.c -o EXAMPLE`.
The embedded example additionally links the generated `face.c`; the SDL example uses the flags in section 13.6; the C++ example compiles the C sources with `cc` first, then links with `c++`.
Run file-based examples with `svf/dos/NEODG16A.SVF`. No font bytes need to be written into application source by hand.
For browser integration, continue with the [web renderer guide](web-renderer-guide.md).

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
17. Related documents

## 1. The model in five words

**Face, chain, target, scratch, line.**

- A **face** (`svf_face`) is one opened `.SVF` file: a cell size, a bit depth (1, 2 or 8 bits per pixel), a table of
  glyphs, and optionally a jamo set that lets it compose Hangul syllables (all 11,172, or the ones its table lists). You allocate the struct; the library never
  allocates.
- A **chain** (`svf_chain`) is an ordered list of faces. Each code point is drawn by the first face that has it, so
  `{ ascii_face, hangul_face }` draws a mixed line with two faces.
- A **target** (`svf_target`) is where pixels go: a byte buffer in one of nine buffer formats, or a callback that receives
  one `(x, y, coverage)` per pixel.
- **Scratch** is a caller-supplied temporary byte buffer for glyph decoding, composition and scaling; `svf_chain_scratch_bytes()` says how big.
- A **line** is one call, `svf_draw_utf8()`: UTF-8 bytes in, pixels out, drawn along a baseline.

Everything is C99, uses only `<stdint.h>`, `<stddef.h>` and `<string.h>`, never calls `malloc`, and draws byte-identical
pixels to the Python reference (`tools/jamoset.py`, `tools/svfline.py`).

Vocabulary used below: a **cell** is the reconstructed bitmap of one glyph (`cell_w x cell_h` pixels); **coverage** is how much
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

2. **Build the static library** with the supplied Makefile: `make -C c` writes `libsvf.a` (and the `svfdump` tool) to `c/build`; `O=DIR` moves them.
3. **Vendor or submodule it.** The code is MIT-licensed (the faces under `svf/` are OFL; see
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

### 2.1 Setting options in CMake and Makefiles

Propagate definitions from a CMake library target with `PUBLIC` so the application and library agree on header struct sizes.
Set `SVF_ROOT` to the absolute path of the SVF sources. This target builds the library alone.

```cmake
cmake_minimum_required(VERSION 3.16)
project(svf_embed C)
set(SVF_ROOT "" CACHE PATH "SVF source directory")
file(GLOB SVF_SOURCES CONFIGURE_DEPENDS "${SVF_ROOT}/c/src/*.c")
add_library(svf STATIC ${SVF_SOURCES})
target_include_directories(svf PUBLIC "${SVF_ROOT}/c/include")
target_compile_features(svf PUBLIC c_std_99)
target_compile_definitions(svf PUBLIC SVF_JMAP=1 SVF_JMAP_LIST=1)
```

```sh
cmake -S /path/to/project -B /tmp/svf-cmake -DSVF_ROOT="$PWD"
cmake --build /tmp/svf-cmake
make -C c O=/tmp/svf-make lib CFLAGS='-O2 -DSVF_JMAP=1 -DSVF_JMAP_LIST=1'
```

In a custom Makefile, apply the same `CPPFLAGS` to the application and all five C sources. The supplied `c/Makefile` accepts definitions through `CFLAGS`. For Arduino use the port build script or global extra flags; for ESP-IDF set definitions on `${COMPONENT_LIB}`. With the Pico SDK, use `target_compile_definitions` on the application target separately from SDK initialization; do not overwrite `CMAKE_C_FLAGS`. Section 13 gives each port’s commands.

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
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
	if (argc < 2) { fprintf(stderr, "usage: ex1 FACE [TEXT]\n"); return 2; }
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
	if (svf_measure_utf8(&chain, text, strlen(text), &e) != SVF_OK) return 1;
	/* e.width is the pen's travel, not the ink: the last cell can reach past it, so leave a cell's width of room */
	int w = e.width + svf_cell_w(&face) + 2, h = e.ascent + e.descent + 2;
	if (w <= 0 || w > 32767 || h <= 0 || h > 32767) return 1;
	uint8_t *pix = calloc((size_t)w * h, 1);
	size_t need = svf_chain_scratch_bytes(&chain);
	uint8_t *scratch = malloc(need);

	if (!pix || !scratch) { free(scratch); free(pix); free(bytes); return 1; }
	svf_target t;
	if (svf_target_init(&t, SVF_T_GRAY8, pix, (size_t)w * h, (int16_t)w, (int16_t)h, (uint16_t)w) != SVF_OK) return 1;
	err = svf_draw_utf8(&chain, text, strlen(text), 1, (int16_t)(1 + e.ascent), &t, scratch, need);
	/* Check every error; streamed glyphs can also fail record validation. */

	for (int y = 0; y < h; y++) {
		for (int x = 0; x < w; x++) putchar(pix[y * w + x] > 127 ? '#' : pix[y * w + x] ? '+' : '.');
		putchar('\n');
	}
	free(scratch); free(pix); free(bytes);
	return err == SVF_OK ? 0 : 1;
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

- `svf_open_mapped` validates the whole file; a face that opens with the default validation settings is safe to draw. The return value says why a file was
  refused (`SVF_E_MAGIC`, `SVF_E_VERSION`, ...).
- `svf_measure_utf8` gives the line's extent without reading a glyph: `e.width` is the **pen's travel** (the sum of the
  advances), not the width of the ink; `e.ascent` and `e.descent` are the rows the cells reach above and below the
  baseline (whole cells, not only the rows that have ink). Here 64 x (12 + 4); glyph `dy` also affects the vertical extent. `e.width` saturates at 32,767, so split long lines.
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
1 MiB face does not need 1 MiB of RAM.

```c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>
#include "svf.h"

static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
{
#if LONG_MAX < UINT32_MAX
    if (off > (uint32_t)LONG_MAX) return -1;
#endif
    return fseek((FILE *)ctx, (long)off, SEEK_SET) == 0
        ? (long)fread(dst, 1, len, (FILE *)ctx) : -1;
}

int main(int argc, char **argv)
{
    FILE *fp;
    long length;
    svf_face face;
    svf_err err;
    uint8_t *tables = NULL, *scratch = NULL;
    uint8_t cache[2 * (1024 + 8)], pixels[128 * 32] = {0};
    svf_face *faces[] = {&face};
    svf_chain chain = {0};
    svf_target target;
    int rc = 1;
    if (argc != 2) { fprintf(stderr, "usage: stream FACE\n"); return 2; }
    fp = fopen(argv[1], "rb");
    if (!fp) return 1;
    if (fseek(fp, 0, SEEK_END) || (length = ftell(fp)) <= 0 ||
        (uint64_t)length > UINT32_MAX) goto done;
    size_t need = svf_stream_tables_size(rd, fp, (uint32_t)length, &err);
    if (err != SVF_OK || !need || !(tables = malloc(need))) goto done;
    err = svf_open_stream(&face, rd, fp, (uint32_t)length, tables, need,
                          cache, sizeof cache, 1024);
    if (err != SVF_OK) goto done;
    chain.faces = faces; chain.count = 1;
    size_t scratch_len = svf_chain_scratch_bytes(&chain);
    scratch = malloc(scratch_len);
    if (!scratch) goto done;
    err = svf_target_init(&target, SVF_T_GRAY8, pixels, sizeof pixels, 128, 32, 128);
    if (err != SVF_OK) goto done;
    err = svf_draw_utf8(&chain, "SVF 한글", strlen("SVF 한글"), 0, 20,
                        &target, scratch, scratch_len);
    size_t ink = 0;
    for (size_t i = 0; i < sizeof pixels; ++i) ink += pixels[i] != 0;
    printf("status=%u tables=%zu scratch=%zu reads=%lu ink=%zu draw=%d\n",
           (unsigned)svf_status(&face), need, scratch_len,
           (unsigned long)svf_stream_reads(&face), ink, (int)err);
    rc = err != SVF_OK;
done:
    free(scratch); free(tables); fclose(fp);
    return rc;
}
```

Rules worth knowing:

- `svf_stream_tables_size` tells you how big `tables` must be. It depends on the face and on which readers the build
  compiles. For `NEODG16A.SVF` (a jamo face) it is 8,153 bytes; for the precomposed `NEODG16.SVF` it is 46,492 bytes
  (measured).
- The block cache is optional (`cache_len` 0 means none). With one, the library reads whole `block_size`-byte blocks
  (a power of two from 64 to 4096) and keeps the most recently used ones. A slot is `block_size + 8` bytes and the cache
  must hold at least two slots. Pass `sizeof cache` as `cache_len`.
- The face keeps pointers to your `tables`, `cache`, `rd` and `ctx`: keep them alive. One streamed face must not
  be drawn from two threads at once.
- A failed or short read returns `SVF_E_IO` for the glyph being drawn only; the line continues and the error is returned at
  the end. Invalid streamed records can also return `SVF_E_RANGE`. `svf_stream_reads(&face)` counts callback calls (handy for tuning cache size).
- Composing a syllable of a streamed face **without** a cache needs `2 * svf_cell_bytes` of scratch (the second half holds
  the piece being read). `svf_chain_scratch_bytes` already accounts for it.
- `-DSVF_NO_STREAM` omits the streaming declarations and definitions: calls fail compilation with strict warnings or fail at link time.

External SPI flash uses the same streaming interface: keep device state in `ctx` and make `rd` read `len` bytes at `off` relative to the start of the face. Return exactly `len` on success, or a negative/short result on failure. Memory-mapped flash is simpler to use with `svf_open_mapped`, like the `const` array in section 5.

### 4.3 What the face tells you

After a successful open the accessors report the header: `svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`,
`svf_glyph_count`, `svf_flags`. `svf_has(f, cp)` says whether the face can draw a code point (a stored glyph, or a
syllable or compatibility jamo it composes). `svf_metrics_of(f, cp, &m)` returns the advance, bearing, ink width and
vertical offset of a glyph.

`svf_status(f)` is easy to miss and important: a face can open successfully and still carry **status bits** saying what
was dropped, for example `SVF_FACE_JSET_BAD` (the jamo block failed validation: the face is plain and will not compose
Hangul) or `SVF_FACE_JSET_UNREAD` (a version 1 or 2 header is valid but its reader is absent). A Hangul face whose
status is non-zero is the first thing to check when syllables do not appear (section 16).

An open can return `SVF_OK` with these status bits. Stored glyphs can still be drawn, so check `svf_has` for
characters the application needs and log both the error code and status for diagnostics.

| Status | Meaning |
|---|---|
| `SVF_FACE_CMAP_LINEAR` | Unsorted or duplicate code points; linear lookup, last duplicate wins. |
| `SVF_FACE_DY_IGNORED` | Invalid dy range ignored. |
| `SVF_FACE_METRICS_DROPPED` | Metrics region dropped; cell-width advances used. |
| `SVF_FACE_JSET_BAD`, `SVF_FACE_JMAP_BAD` | Malformed composition block; see the [specification](../spec/SVF.md#validation) for fallback details. |
| `SVF_FACE_JSET_UNREAD`, `SVF_FACE_JMAP_UNREAD` | This reader is disabled in the build; a supported fallback is used when available. |

## 5. Embedding a face

A microcontroller has no file system (or none you want to depend on), and a program that ships one face is simpler with
the face inside it. `c/bench/mkface.py` writes a face as a C array:

    python3 -I c/bench/mkface.py svf/dos/NEODG16G.SVF face.c --name neodg16g --profile mcu-strict

It needs Python 3 and `tools/jamoset.py`. The import path is relative to the script, so it can run from other working
directories; the paths below assume the project root. `--name` must be a C identifier. The output exposes these symbols:

`face.c` defines `const uint8_t neodg16g[]` and `const uint32_t neodg16g_len`.
On AVR the array has `PROGMEM`; its alignment follows the selected layout.

- With a linker configuration that places the array in flash, it needs no RAM copy; on AVR it is `PROGMEM`, which puts it in
  flash's own address space (the library then reads it through `SVF_RD8`, section 4.1). `NAME_len` is the face's size
  in bytes: pass both to `svf_open_mapped`.
- `aligned(A)` is `A = 2^max(REC, TAB)` bytes of the written layout (4 for `mcu-strict`; left out when it is 1), so a
  record's offset in the file is its address alignment. Alignment is **only speed**. `svf_open_mapped` checks the
  alignment of the offsets *inside the file* against the layout, never the address of the array: a face opens and
  draws the same from an odd address .
- `--profile mcu-strict` rewrites the face in the layout of `SVF_LAYOUT_MCU_STRICT` (record and table units 4 bytes, row
  unit 1 byte, 16-bit offsets where they fit); the pixels are the same. The 117 shipped faces all use
  4/1/4-byte layout units, so a build with
  `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` opens the shipped files as they are, and the profile only shrinks the
  offsets: NEODG16G goes from 10,684 to 10,124 bytes. Without `--profile` the bytes are the file's own. A face in the
  `dos` or `wasm` profile (1/1/1-byte layout units) is refused by such a build with `SVF_E_LAYOUT`.
- **Use `mkface.py` for embedded faces.** Default `xxd -i` output defines `unsigned char name[]` without `const`;
  linking it unchanged can create a RAM copy. AVR `PROGMEM` and layout alignment also need separate declarations.

### 5.1 Where the array goes, per platform

| Target | Where the face lives | Notes |
|---|---|---|
| AVR (Arduino Uno) | `PROGMEM` flash | build the library with `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`. Without `SVF_RD8` the library reads flash addresses as RAM and `svf_open_mapped` returns `SVF_E_MAGIC` . The text passed to `svf_draw_utf8` is read with plain loads: keep it in RAM (copy a `PROGMEM` string with `strncpy_P` first) |
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
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "svf.h"

extern const uint8_t neodg16g[];            /* face.c from mkface.py --name neodg16g */
extern const uint32_t neodg16g_len;

/* Your display driver: one pixel, on/off (or a grey level from cov). */
static unsigned ink;
void lcd_set_pixel(int16_t x, int16_t y, uint8_t on)
{
    (void)x; (void)y;
    ink += on != 0;
}

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

int main(void)
{
    int init = text_init(128, 32);
    if (init) { printf("init=%d\n", init); return 1; }
    int width = text_draw("SVF 한글", 0, 0);
    printf("status=%u width=%d ink=%u\n", (unsigned)svf_status(&face), width, ink);
    return width < 0;
}
```

`svf_is_jamo` is 1 for a face that composes Hangul and `svf_status` is 0 when nothing was dropped (section 4.3). A face
can still draw stored glyphs when its composition block is unusable. `JMAP_UNREAD` alone does not imply a plain
face: a supported fallback can still compose syllables. A precomposed face has no jamo block, so check `svf_has(&face, 0xD55C)`
for it instead.

Build `text_cb.c` with `face.c` and run it. The host pixel routine counts lit-pixel calls; replace it with display writes on a device.

```sh
cc -std=c99 -Wall -Wextra -Ic/include text_cb.c face.c c/src/*.c -o text_cb
./text_cb
# status=0 width=64 ink=248
```

### 5.3 C++ and Arduino: keep `face.c` a C file

Generate the array into a `.c` file and let the C compiler build it. In C++ a namespace-scope `const` array has
internal linkage unless declared with external linkage, so another translation unit cannot refer to it.[9] The Arduino build compiles `.c`
files in the sketch folder as C. Declare it in the C++ side with C linkage (as `c/ports/arduino/arduino.ino` does):

```cpp
#ifdef __AVR__
#include <avr/pgmspace.h>
#else
#define PROGMEM
#endif
#include "svf.h"                          /* svf.h is wrapped in extern "C" for C++ itself */

extern "C" {
extern const uint8_t neodg16g[] PROGMEM;  /* face.c, from mkface.py */
extern const uint32_t neodg16g_len;
}

static svf_face face;
bool face_ok() { return svf_open_mapped(&face, neodg16g, neodg16g_len) == SVF_OK; }
int main() { return face_ok() ? 0 : 1; }
```

### 5.4 Licences to ship

A program or image with a face in it distributes font software.[10] Ship with it: the face's own licence text (for NEODG16G,
`svf/dos/OFL.TXT` and `svf/dos/NEODGM.TXT`; for PAPLG16 and PAPLG18 `svf/dos/OFLPAPLG.TXT`; `web/LICENCES.tsv` maps every
face under `svf/` to its licence files), [NOTICE.md](../NOTICE.md) (what is under which licence), and
[LICENSE](../LICENSE) (MIT, for the library's code). `c/ports/FACES.md` names the source, copyright and licence of each
face the ports embed; the Pico, ESP32 and CH582 builds copy it and the licence texts to `<build>/licences/`.

## 6. Choosing a face for your target

A face is a file; its size, not its pixel size, decides where it fits. Measure the one you mean to use:

    python3 -I c/bench/mkface.py svf/dos/NEODG16A.SVF x.c --name x --profile mcu-strict && tail -2 x.c

The last line, `const uint32_t x_len = 15528u;`, is the number in the table below: the bytes you link. Measured on this
faces: array bytes use `mcu-strict` output; stream tables use the original file and default host build:

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

- **Hangul.** The jamo-set faces in the table compose pieces; coverage depends on the composition block (section 10).
  A precomposed face stores a glyph per supported syllable. The arrays above make NEODG16 about 8.24 times the size
  of NEODG16A. For a small device, choose a jamo face that supports the required syllables.
- **Uno.** The ATmega328P provides 2 KiB SRAM.[3] The table assumes faces embedded in flash. Check final code,
  face, globals and stack together; use the AVR flash reads and build switches in section 13.1.
- **CH582.** The port's `link.ld` allocates 448 KiB flash and 32 KiB RAM. Include code and data copied from flash as well as the face.
- **Pico.** The Pico board has 2 MiB flash and Pico 2 has 4 MiB.[6] These face sizes fit that capacity, but check the entire image.
- **ESP32.** Embedded capacity depends on the partition table. The table assumes a 1 MiB app partition;
  GBATB47 alone exceeds it. Use a larger app partition or a separate data partition (section 13.4).[5]
- **Streaming** (a file on SD, SPIFFS or disk) needs RAM for the tables (the column above, for the shipped file) plus
  an optional block cache; the Uno cannot (`NEODG16G` alone needs 5,129 bytes of tables, and the Uno build leaves the reader out).
- **RAM** for drawing is small: scratch is one cell for an unscaled mapped face (`Cell bytes`, section 11) plus your frame buffer; scaling and streaming can need more scratch (sections 9 and 11).

## 7. Lines of text: chains, metrics, measuring

### 7.1 Fallback chains

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc < 2 || argc > 3) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    hangul_face = face;
    size_t latin_len;
    uint8_t *latin_bytes = slurp(argc == 3 ? argv[2] : argv[1], &latin_len);
    if (!latin_bytes || svf_open_mapped(&latin_face, latin_bytes, latin_len) != SVF_OK) {
        free(latin_bytes); free(bytes); return 1;
    }
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;

svf_face *faces[2] = { &latin_face, &hangul_face };
svf_chain chain = {0};
chain.faces = faces;
chain.count = 2;
chain.missing_advance = 8;      /* pixels to advance for a code point no face has (nothing is drawn) */
svf_target target;
svf_extent extent;
const char *text = "SVF 한글";
if (svf_target_init(&target, SVF_T_GRAY8, pix, sizeof pix, 64, 24, 64) != SVF_OK ||
    svf_measure_utf8(&chain, text, strlen(text), &extent) != SVF_OK ||
    svf_draw_utf8(&chain, text, strlen(text), 0, 20, &target, scratch, scratch_len) != SVF_OK)
    return 1;
printf("faces=%u width=%d scratch=%zu\n", (unsigned)chain.count, extent.width,
       svf_chain_scratch_bytes(&chain));
    free(latin_bytes); free(bytes);
    return 0;
}
```

Each code point is drawn by the first face for which `svf_has` is true. Order matters: put the face whose style you want
for shared characters (digits, punctuation) first. A `chain.faces` that is `NULL`, a `count` of 0, or a NULL entry makes
the chain "without faces": calls using it return `SVF_E_ARG` and draw nothing.

Run the complete chain example as `./chain svf/dos/NEODG16A.SVF svf/dos/PAPLG16.SVF`. Omitting the second argument opens the same file twice to demonstrate the call sequence.

### 7.2 Marks, advances, invalid UTF-8

- Advances come from the face's metrics table (variable width); a face without one advances by the cell width. A composed
  syllable advances by the jamo block's syllable advance (or the cell width).
- Supported combining marks do not advance. They start at the current pen, shifted left by `min(-bearing_x, cell_w)`
  only when face flag bit 2 is set and `bearing_x < 0`. The default predicate covers U+0300..U+036F;
  supply `chain.is_mark` for other ranges. A code point absent from every face advances `missing_advance`, even if it is a mark.
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

How a 2 bpp level becomes a colour on each kind (the exact blend and rounding, the mono threshold per level), with
figures, and which bpp suits which display: [Anti-aliasing](anti-aliasing.md#23-from-level-to-colour).

### 8.1 Colour text on a 32-bit surface

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

svf_target t;
if (svf_target_init(&t, SVF_T_XRGB8888, surface_pixels, (size_t)pitch * height,
                    (int16_t)width, (int16_t)height, (uint16_t)pitch) != SVF_OK) return 1;
t.fg888 = 0x00FFC000;      /* amber text */
t.bg888 = 0x00000020;      /* the background colour the caller knows */
for (size_t i = 0; i < sizeof pix; i += 4) {
    pix[i] = 0x20; pix[i + 1] = 0; pix[i + 2] = 0; pix[i + 3] = 0;
}
if (svf_draw_utf8(&chain, "SVF 한글", strlen("SVF 한글"), 0, 20,
                  &t, scratch, scratch_len) != SVF_OK) return 1;
printf("status=%u scratch=%zu\n", (unsigned)svf_status(&face), svf_chain_scratch_bytes(&chain));
    free(bytes);
    return 0;
}
```

`stride` is a `uint16_t` number of bytes, so a 32-bit target is at most 16,383 pixels wide. The pixel's **memory order is
B, G, R, X on every host**; as one native 32-bit value that is `0x00RRGGBB` only on a little-endian host. The core writes the same four bytes on a big-endian host.

### 8.2 The callback target: the universal adapter

When your pixel format is not one of the above, or you want to blend over existing content, or the destination is another
library's surface, use the callback. The library calls `plot(ctx, x, y, coverage)` once per cell for each pixel with coverage above
0 inside the clip, row by row, with no buffer involved. This example blends white text with existing pixels in a 32-bit surface (it reads and writes memory bytes B, G, R, X directly):

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

typedef struct { uint8_t *pix; int pitch; uint32_t fg; } Surf;      /* your surface */

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	Surf *s = ctx;
	uint8_t *px = s->pix + (size_t)y * s->pitch + 4 * (size_t)x;
	for (int c = 0; c < 3; ++c) {                              /* B, G, R */
		uint32_t b = px[c], f = (s->fg >> (8 * c)) & 255;
		px[c] = (uint8_t)((b * (255 - cov) + f * cov + 127) / 255);
	}
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

Surf s = { pix, 64 * 4, 0x00FFFFFF };
svf_target t;
if (svf_target_init(&t, SVF_T_COVERAGE_CB, NULL, 0, 64, 24, 0) != SVF_OK) return 1;
t.plot = plot;
t.ctx = &s;
if (svf_draw_utf8(&chain, "가A", strlen("가A"), 2, 16, &t, scratch, scratch_len) != SVF_OK) return 1;
printf("status=%u scratch=%zu\n", (unsigned)svf_status(&face), svf_chain_scratch_bytes(&chain));
    free(bytes);
    return 0;
}
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
U+AC00..U+D7A3 from two or three pieces, taking the maximum coverage per pixel. Compatibility jamo U+3131..U+3163
use their single designated piece. You do nothing special; just draw Hangul text. One qualification: the syllable table can be partial. A version 3 JMAP block
that is SPARSE (a bitmap and its entries) or LIST (a sorted list of up to 255 exceptions) and has **no fallback** block
composes only the syllables it lists: `svf_has` is 0 for the others and they are drawn as missing glyphs
(`missing_advance`); with a fallback block, a syllable the table does not list goes to the fallback. Dense JMAP and
version 1 and 2 blocks cover all 11,172.

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

if (svf_is_jamo(&face)) {
	uint16_t pieces[3];
	int n = svf_jamo_pieces(&face, 0xD55C /* 한 */, pieces);   /* 3: initial, medial, final */
	for (int i = 0; i < n; i++)
		printf("piece %u\n", (unsigned)pieces[i]);               /* glyph U+F0000 + number in the face */
}
size_t cell_len = svf_chain_scratch_bytes(&chain);
uint8_t *cell = malloc(cell_len);
if (!cell || svf_glyph(&face, 0xD55C, cell, cell_len) != SVF_OK) {
    free(cell); free(bytes); return 1;
}
free(cell);
printf("status=%u scratch=%zu\n", (unsigned)svf_status(&face), svf_chain_scratch_bytes(&chain));
    free(bytes);
    return 0;
}
```

`svf_glyph` and `svf_compose` return the cell of one code point without a target: useful for caching glyphs in your own
atlas.

### 10.1 What your build reads

Jamo blocks come in versions 1, 2 and 3 (JMAP, with a LIST form). The default desktop/DOS/WASM/SDL build reads them
all (but not under `-DSVF_SMALL`, section 12). A small-MCU build reads fewer (see the table in [c/README.md](../c/README.md), "Jamo sets: what each build reads").
An unread composition block sets a status bit. A supported JSET fallback still composes syllables; without one, the
face opens **plain**. Check `svf_status`, `svf_is_jamo` and `svf_has` for the required code points at load time.

### 10.2 The composed-syllable cache

Composing costs a few table lookups and a merge per syllable. For text that repeats (a UI, a dialogue box redrawn every
frame) give the chain a cache:

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

static uint8_t syl[4096];                       /* slots of (8 + the largest cell bytes of the chain's faces) */
svf_chain_cache(&chain, syl, sizeof syl);
chain.scale_num = 3; chain.scale_den = 2;
size_t need = svf_chain_scratch_bytes(&chain);
if (need > sizeof scratch) return 1;
const svf_target_kind kinds[] = {SVF_T_GRAY8, SVF_T_MONO_ROW, SVF_T_RGB565};
const uint16_t strides[] = {64, 8, 128};
for (unsigned k = 0; k < 3; ++k) {
    svf_target t;
    memset(pix, 0, sizeof pix);
    if (svf_target_init(&t, kinds[k], pix, sizeof pix, 64, 24, strides[k]) != SVF_OK) return 1;
    t.fg565 = 0xffff; t.bg565 = 0;
    t.clip_x0 = 2; t.clip_x1 = 62;
    if (svf_draw_utf8(&chain, "한글", strlen("한글"), 0, 20, &t, scratch, need) != SVF_OK) return 1;
    unsigned nonzero = 0;
    for (size_t j = 0; j < sizeof pix; ++j) nonzero += pix[j] != 0;
    printf("kind=%d scratch=%zu nonzero=%u\n", (int)kinds[k], need, nonzero);
}

    free(bytes);
    return 0;
}
```

Pixels are identical with or without it. It matters most for streamed faces: a cached syllable causes no reads at all.
Non-composed cells, such as Latin glyphs, do not use this cache and can still cause reads on a repeated line. The cache is round robin with a linear lookup: tens of slots suit small targets; thousands do not. Call
`svf_chain_cache` again after you change `chain.faces` or reopen a face.

## 11. Memory budget

All memory is yours. Add up:

| Item | Size |
|---|---|
| `svf_face` | `sizeof(svf_face)`: 96 bytes on a 64-bit host with `SVF_JMAP` (80 without; smaller on MCUs; use `sizeof` for the actual ABI) |
| `svf_chain`, `svf_target` | a few tens of bytes each |
| Scratch | `svf_chain_scratch_bytes(&chain)`: one cell (`svf_cell_bytes`), twice that for a streamed face without a block cache; when scaling, **twice the cell plus the scaled cell** (section 9) |
| Streamed face | `svf_stream_tables_size(...)` for the tables, plus `slots * (block_size + 8)` for the optional cache |
| Syllable cache | `slots * (8 + largest cell bytes)` |
| Target buffer | `rows * stride` (or none for the callback kind) |
| Mapped face | the file itself, in RAM or flash (a flash-resident `const` array or PROGMEM face needs no RAM copy, section 5) |
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
  reads**: it flips the *defaults* of `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG` and `SVF_JSET_BIG` to 0 (they are 1 in
  default desktop/DOS/WASM builds). A `SVF_SMALL` build on a desktop, DOS or WASM therefore
  no longer reads version 3 (JMAP, LIST) jamo blocks or the BIG limits: a face that needs them opens **plain**, with
  `SVF_FACE_JSET_BAD` set (`SVF_FACE_JMAP_UNREAD` only with `-DSVF_JMAP_RECOG=1`), and draws no Hangul. Add `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`
  (`SVF_JMAP_LIST` follows `SVF_JMAP`) if you need them.

The complete switch table with defaults per toolchain is in [c/README.md](../c/README.md), "Compile-time switches", and
the sizes each configuration produces are in `c/cross/SIZES.md`.

| Macro | Default and effect |
|---|---|
| `SVF_SMALL` | Undefined. Defining it reduces fast paths and disables JMAP/BIG defaults; `=0` still counts as defined. |
| `SVF_JMAP` | 1 on desktop/DOS/WASM, 0 on AVR/MCU/SMALL. Version 3 mapping reader; affects `svf_face` size. |
| `SVF_JMAP_LIST` | Follows `SVF_JMAP`. LIST reader; 1 without JMAP is a compile error. |
| `SVF_JMAP_RECOG` | 1 on desktop/DOS/WASM, 0 on MCU/SMALL. Recognizes JMAP and uses its fallback even without the JMAP reader. |
| `SVF_JSET_BIG` | 1 on desktop/DOS/WASM, 0 on MCU/SMALL. Widens class and set limits. |
| `SVF_JSET_V1`, `SVF_JSET_V2` | V1 is 1; V2 is 0 on AVR and 1 elsewhere. At least one of V1, V2 or JMAP must be enabled. The CH582 port explicitly disables V2. |
| `SVF_JSET_TRUSTED` | 0. Use 1 only for validated embedded faces; skips table-content validation. |
| `SVF_JSET_POP4` | Normally 1, 0 on AVR/SMALL. Selects the V2 popcount implementation. |
| `SVF_NO_STREAM`, `SVF_NO_SCALE` | Undefined; defining either removes that feature. |
| `SVF_LAYOUTS` | All valid layouts by default; for example restrict to `SVF_LAYOUT_MCU_STRICT`. |
| `SVF_TARGETS` | `0x3ff`. OR target bits: GRAY8 `0x001`, MONO_PAGE `0x002`, MONO_ROW `0x004`, RGB565 `0x008`, CB `0x010`, INDEXED8 `0x020`, RGB555 `0x040`, XRGB8888 `0x080`, RGB888 `0x100`, GRAY `0x200`. |
| `SVF_RD8(p)` | Ordinary memory read; override with `pgm_read_byte(p)` for AVR PROGMEM. |
| `SVF_MERGE_WORDS`, `SVF_GRAY8_LUT1`, `SVF_SCALE_FAST`, `SVF_WORD_STORE` | CPU/SMALL-dependent optimizations; see [svf.h](../c/include/svf.h) for exact defaults. Pixel semantics stay the same. |

## 13. Platforms

Use each port's build settings and display driver as a starting point. Commands below start at the project root.
Check both the build and the actual panel. Memory use depends on the toolchain, SDK, faces and flags; inspect `size`
and the link map for the final image. See the [build size tables](../c/cross/SIZES.md) for individual configurations.

### 13.1 Arduino Uno and other Arduino cores

Arduino compiles `.c` files in the sketch folder as C.[1] This Uno configuration enables `MONO_PAGE` only.
Install `arduino-cli` and the `arduino:avr` core first.

```sh
mkdir -p ~/Arduino/libraries/svf
cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
python3 -I c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
arduino-cli compile -b arduino:avr:uno c/ports/arduino \
    --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"
```

Put generated `face.c` beside the `.ino` and declare its symbols with C linkage as in section 5.3.
Pass the same flags through `compiler.c.extra_flags` and `compiler.cpp.extra_flags`. Avoid `build.extra_flags` for
`-include avr/pgmspace.h`: it also reaches assembler sources. AVR `PROGMEM` reads require the `SVF_RD8` override.[2]
Keep text in RAM or copy it with a function such as `strncpy_P` before drawing.

[arduino.ino](../c/ports/arduino/arduino.ino) draws into a 128 x 64, 1,024-byte page buffer and sends 16-byte chunks
through `Wire`. The Uno has 2 KiB SRAM,[3] shared by the frame buffer, Wire buffers, globals and stack. The flags above
remove scaling and streaming. On the Mega, this port cannot read faces outside the address range of `pgm_read_byte`.
Do not apply the AVR `SVF_RD8` flags to other cores with memory-mapped flash. See the
[Arduino port](../c/ports/arduino/README.md) for details.

### 13.2 WCH CH582 (RISC-V, bare metal)

The [CH582 port](../c/ports/ch582/README.md) uses WCH CH583 EVT startup and peripheral code with
`riscv32-esp-elf-gcc`. Set `CH583_SDK` and `CROSS` in the [Makefile](../c/ports/ch582/Makefile) to change the SDK
and compiler paths.

```sh
sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
make -C c/ports/ch582
# BOOT held while connecting USB / USB 연결 시 BOOT 버튼 누름
make -C c/ports/ch582 flash
```

The library uses `-std=c99`; the port uses `-std=gnu99`. Library switches match the Uno:
`SVF_NO_SCALE`, `SVF_NO_STREAM`, `SVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, `SVF_TARGETS=0x02`, `SVF_JSET_V2=0`.
The face is a flash `const` array. [link.ld](../c/ports/ch582/link.ld) allocates 448 KiB flash, 32 KiB RAM and a
2,048-byte stack. `.highcode` lives in RAM, so include it in both flash and RAM budgets.

The 128 x 64 SH1106 uses I2C on PB20 (SDA) and PB21 (SCL), address 0x3C, with a 1,024-byte `MONO_PAGE` buffer.
`display_show(buf, y, rows)` sends it through the bounded `ch582_i2c_write`.
`FREQ_SYS=24000000` must match `SetSysClock(CLK_SOURCE_PLL_24MHz)` in `main.c`.

### 13.3 DOS (DJGPP)

DJGPP produces 32-bit protected-mode executables. Real DOS needs a DPMI host; `CWSDPMI.EXE` can be placed beside
the executable or on `PATH`.[4]

```sh
DJ="$HOME/opt/djgpp/bin/i586-pc-msdosdjgpp"
"$DJ-gcc" -std=gnu99 -O2 -Ic/include c/ports/dos/svfdemo.c c/src/*.c -o SVFDEMO.EXE
"$DJ-gcc" -std=gnu99 -O2 -Ic/include -Ic/ports/dos c/ports/dos/svfvesa.c c/ports/dos/vbe_select.c \
    c/ports/dos/vesa_lines.c c/src/*.c -o SVFVESA.EXE
```

The library uses the full `__DJGPP__` defaults. Use `-std=gnu99` so the headers declare the port's POSIX functions.
Without long-filename support use 8.3 names such as `NEODG16A.SVF` and `VESALINE.TXT`.
Open with `fopen(path, "rb")`, or `O_RDONLY | O_BINARY` for the low-level file API.[4]

`svfdemo.c` streams PAPLG16 and PAPLG18 with 16 and 64 cache slots respectively, using 1 KiB blocks.
Its 320 x 200 GRAY8 screen is 64,000 bytes, copied to VGA mode 13h with a grey palette.
`svfvesa.c` supports 8, 15, 16, 24 and 32 bpp VBE targets. Use section 4.2 for large streamed faces.
See the [DOS port](../c/ports/dos/README.md) for execution details.

### 13.4 ESP32 (ESP-IDF)

The [ESP32 port](../c/ports/esp32/README.md) targets ESP32-C3 and ESP32-S3. Activate the ESP-IDF environment first.
Use a build directory per profile and chip; also check the shared `sdkconfig` when switching chips.

```sh
cd c/ports/esp32
idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3
idf.py -B build-colour build flash monitor
```

`main/CMakeLists.txt` generates face arrays with `mkface.py --profile mcu-strict`.
A custom component includes `svf.h`, `svf_internal.h`, `svf_*.c` and generated `face.c`, all with the same definitions.
Use `PUBLIC` definitions and include paths if other components also include `svf.h`.[5]

```cmake
# main/CMakeLists.txt; svf/ contains headers and sources / 헤더와 소스는 svf/에 둔다
file(GLOB SVF_SRCS svf/*.c)
idf_component_register(SRCS main.c face.c ${SVF_SRCS} INCLUDE_DIRS svf)
target_compile_definitions(${COMPONENT_LIB} PUBLIC SVF_NO_SCALE SVF_TARGETS=0x08)
```

Open flash `const` arrays with `svf_open_mapped`. For a data partition, use `esp_partition_find_first`, then
`esp_partition_mmap(..., ESP_PARTITION_MMAP_DATA, &ptr, &handle)` and open with the actual file length.
Call `esp_partition_munmap(handle)` after the face is no longer used. Mount SPIFFS with `esp_vfs_spiffs_register`
and stream through the stdio callback in section 4.2. Declare `esp_partition` and `spiffs` dependencies when the
custom component uses those APIs.[5]

The colour profile sends 320 x 24 RGB565 bands (15,360 bytes) to an ILI9341 through `spi_device_polling_transmit`.
Set `SVF_TF_RGB16_BIGENDIAN` to match the driver; the QEMU `esp_rgb` driver uses flags 0.
Check the final image against the selected partition table to determine whether the face fits.

### 13.5 Raspberry Pi Pico and Pico 2 (pico-sdk)

Set the pico-sdk path; add `-DPICO_BOARD=pico2` for the Pico 2's Arm cores. With `PICO_NO_PICOTOOL=1`, this project
skips `pico_add_extra_outputs`, so it does not produce a `.uf2`.[6]

```sh
cmake -S c/ports/pico -B build-pico-mono -DSVF_PROFILE=mono -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico-mono
cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico2-mono
```

For a custom target, add `c/src/*.c` and generated `face.c`, with `c/include` on the include path. Use
`target_compile_definitions` to give the app and library the same switches, then link `pico_stdlib` and the bus
library. The [port's CMakeLists.txt](../c/ports/pico/CMakeLists.txt) is a complete example.

SSD1306 uses I2C on GP4/GP5 (`i2c_write_blocking`); ST7789 uses SPI on GP16..GP20 (`spi_write_blocking`).
The colour profile uses 240 x 24 RGB565 bands (11,520 bytes), with `SVF_TF_RGB16_BIGENDIAN`.
Faces are read from XIP flash.[6] Emulator execution time alone does not establish real flash, cache or bus timings.
See the [Pico port](../c/ports/pico/README.md) for wiring and flashing.

### 13.6 SDL2 and SDL3

The [SDL port](../c/ports/sdl/README.md) supports SDL2 and SDL3 through `sdl_compat.h`.
This SDL3 example loads a face, draws at scale 2/1 and saves `out.bmp`.
`SDL_PIXELFORMAT_BGRX32` specifies memory bytes B, G, R, X regardless of host byte order.[7]

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
      SDL_Surface *surf = SDL_CreateSurface(320, 48, SDL_PIXELFORMAT_BGRX32); /* memory bytes B G R X */
      if (!surf || !SDL_FillSurfaceRect(surf, NULL, SDL_MapSurfaceRGB(surf, 0, 0, 0x20)) || !SDL_LockSurface(surf))
          return 1;
      if (svf_target_init(&t, SVF_T_XRGB8888, surf->pixels, (size_t)surf->pitch * surf->h, (int16_t)surf->w,
                          (int16_t)surf->h, (uint16_t)surf->pitch) != SVF_OK)
          return 1;
      t.fg888 = 0x00FFC000;
      t.bg888 = 0x00000020;                                  /* the colour the surface was filled with */
      svf_err e = svf_draw_utf8(&chain, s, strlen(s), 4, (int16_t)(4 + 2 * svf_ascent(&face)), &t, scratch, sizeof scratch);
      SDL_UnlockSurface(surf);
      bool saved = SDL_SaveBMP(surf, "out.bmp");
      SDL_DestroySurface(surf);
      SDL_free(bytes);
      return e == SVF_OK && saved ? 0 : 1;
  }
  ```
```sh
export PKG_CONFIG_PATH="$HOME/opt/sdl3/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
cc -std=c99 -Wall -Wextra -Ic/include sdl_min.c c/src/*.c $(pkg-config --cflags --libs sdl3) \
    -Wl,-rpath,$(pkg-config --variable=libdir sdl3) -o sdl_min
SDL_VIDEODRIVER=dummy ./sdl_min svf/dos/NEODG16A.SVF
```

Pass `surf->pitch` as the stride. Lock the surface while drawing and first fill it with the colour used for `bg888`.
16-bit SDL surfaces follow host byte order; set `SVF_TF_RGB16_BIGENDIAN` on a big-endian host.
`make -C c/ports/sdl SDL=2` or `SDL=3` builds the complete example;
`sh c/ports/sdl/check.sh` compares the supported surface formats against Python output.

### 13.7 Web (WebAssembly, Emscripten)

The [web renderer guide](web-renderer-guide.md) has HTML and Node examples and memory cleanup order.
The shared build function includes `EMSCRIPTEN_KEEPALIVE` APIs, `_malloc`, `_free`, heap views and memory growth.[8]

```sh
mkdir -p /tmp/svf-module
. c/ports/web/emcc-flags.sh
svf_web_compile "$PWD" /tmp/svf-module
```

The wrapper exposes GRAY8, MONO_PAGE, MONO_ROW and RGB565, with up to four face slots.
`svfw_draw` starts with 65,536 bytes of static scratch and allocates dynamically if more is needed. GBATB47 at 16/1
needs `2*648 + (46*16)*(54*16) = 637200` bytes. The C core does not allocate dynamically.
Call `svfw_reset` before freeing face memory; reacquire heap views after calls that may grow WASM memory.[8]

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
6. **Threads.** Independent faces/chains can be used in parallel. Do not share mutable state such as a streamed face or
   syllable cache concurrently. Use independent scratch and targets for each call.
7. **Clipping.** Set the target's clip rectangle (`clip_x0..clip_y1`) to your dialogue box; the library will not write
   outside it and does not read glyphs for cells wholly outside.
8. **Validate user-supplied faces.** `svf_open_*` is built to reject hostile files (it is fuzz-tested), but never build
   with `-DSVF_JSET_TRUSTED=1` for faces that do not come from your own build.
9. **Same switches everywhere** (section 2).

A wrapper can hold the face, chain, scratch and syllable cache, with `width(str)`
and `draw(str, x, y_top)` methods calling `svf_measure_utf8` and `svf_draw_utf8`.

## 15. Testing your integration

- **The reference.** `tools/svfline.py` draws the same line in Python; its output must equal the C output byte for byte.
  [tools/test_c_renderer.py](../tools/test_c_renderer.py) shows how to drive and compare both renderers.
- **The gate.** `make -C c check` runs the unit programs under sanitizers, verifies that no object references `malloc`,
  `calloc`, `realloc` or `free`, and runs the Python comparison.
- **Your own checks.** A tiny program that draws a known string into a `SVF_T_GRAY8` buffer and prints it (section 3) is
  the fastest way to see a layout problem. Compile your tests with `-fsanitize=address,undefined`.
- **Faces.** To see what a face file holds, run `c/build/svfdump FACE info` (header values, layout units, and the status
  bits `jset_bad`, `jset_unread`, `jmap_bad`, `jmap_unread`; `svfdump FACE has U+AC00 U+D55C` says whether each code
  point draws; `svfdump FACE syllables` dumps every composed syllable cell, the C side of the Python identity tests), or
  `jamoset.parse_svfn` in Python. `tools/facecheck.py` is **not** a face checker: it checks manifests and the faces
  a font map names. See the [maker app](maker-desktop.md) for production and the [desktop app](desktop-app.md) for inspection and previews.

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
| `svf_open_mapped` returns `SVF_E_MAGIC` on an AVR build, the face being a `PROGMEM` array | the library was built without `-DSVF_RD8(p)=pgm_read_byte(p)`, so it reads flash addresses as RAM | build every library source with `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'` (section 5.1) |
| The face array eats RAM, or the link overflows RAM | the array was made with `xxd -i` (not `const`, so `.data`) | generate it with `c/bench/mkface.py` (section 5); check `size` shows the face under text, not data |
| Hangul draws nothing after adding `-DSVF_SMALL` | `SVF_SMALL` turns the defaults of `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG` and `SVF_JSET_BIG` off: a version 3 or BIG face opens plain (`JSET_BAD`; `JMAP_UNREAD` only with `-DSVF_JMAP_RECOG=1`) | add `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`, or write the face in a form the build reads (section 10.1, section 12) |
| Only some Hangul syllables draw, the rest are missing | the face's JMAP is SPARSE or LIST with no fallback block: it composes only the syllables it lists | `svf_has(face, cp)` per syllable; rebuild the face with a fallback or a dense table (section 10) |
| Text ends cut off at the right of the buffer | the buffer was sized from `e.width`, the pen's travel, but the last glyph's ink reaches past it | `e.width + svf_cell_w(face)` (section 3) |
| Crashes or garbage after upgrading | translation units built with different `-D` switches (`SVF_JMAP` changes `svf_face`) | rebuild everything with one flag set |
| `SVF_E_IO` on a streamed face | the read callback returned a short or negative count | return exactly `len` bytes or a negative value; check the file position logic |

## 17. Related documents

Start with the [project overview](../README.md), [SVF glossary](../spec/SVF.md#glossary),
[renderer design](../spec/renderer-design.md) and [jamo sets](jamo-sets.md) for data and composition rules.
Use [recipes](recipes.md) and the [tools guide](tools.md) to create and convert faces,
and [anti-aliasing](anti-aliasing.md) to choose coverage, colours and output depth.
The [web guide](web-renderer-guide.md), [desktop app](desktop-app.md) and [maker app](maker-desktop.md) describe application workflows.

## 참고 문헌 / References

1. Arduino, Sketch build process: https://docs.arduino.cc/arduino-cli/sketch-build-process/
2. AVR-LibC, Program Space Utilities: https://avrdudes.github.io/avr-libc/avr-libc-user-manual/group__avr__pgmspace.html
3. Arduino UNO R3 datasheet (ATmega328P SRAM): https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf
4. DJGPP FAQ mirror (DPMI, binary files): https://djgpp.mirror.garr.it/v2faq/faq6_2.html ; https://djgpp.mirror.garr.it/v2faq/faq9_4.html
5. ESP-IDF v5.5, build system, partitions and SPIFFS; CMake compile definitions: https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-guides/build-system.html ; https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/storage/partition.html ; https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-guides/partition-tables.html ; https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/storage/spiffs.html ; https://cmake.org/cmake/help/latest/command/target_compile_definitions.html
6. Raspberry Pi, Pico C/C++ SDK and Pico/Pico 2 datasheets: https://datasheets.raspberrypi.com/pico/raspberry-pi-pico-c-sdk.pdf ; https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf ; https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf
7. SDL3, pixel formats and surfaces: https://wiki.libsdl.org/SDL3/SDL_PixelFormat ; https://wiki.libsdl.org/SDL3/SDL_LockSurface ; https://wiki.libsdl.org/SDL3/SDL_SaveBMP
8. Emscripten, module options and memory access: https://emscripten.org/docs/api_reference/module.html ; https://emscripten.org/docs/porting/connecting_cpp_and_javascript/Interacting-with-code.html
9. C++ linkage: https://en.cppreference.com/cpp/language/storage_duration#Internal_linkage
10. SIL Open Font License 1.1: https://openfontlicense.org/open-font-license-official-text/
