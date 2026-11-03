# SVF C renderer (`c/`)

A portable C99 library that reads SVFN v3 bitmap faces ([spec/SVF.md](../spec/SVF.md)) and draws UTF-8 lines with them,
including Hangul syllables composed from jamo-set faces. Design: [spec/renderer-design.md](../spec/renderer-design.md).
The Python tools are the reference: `tools/jamoset.py` (`parse_svfn`, `pieces_of`, `compose`) for glyphs and syllables,
`tools/svfline.py` for lines, targets and scaling. The library draws byte-identical pixels to them.

- **No allocation.** The caller owns every byte: the face struct, the tables buffer and cache of a streamed face, the
  scratch cell, the target buffer. `make -C c check` fails if an object references `malloc`, `calloc`, `realloc` or `free`.
- **Small dependencies.** `<stdint.h>`, `<stddef.h>` and `<string.h>` only.
- **One source for every target**, trimmed at compile time by the switches below.

Who uses it (2026-11-01):

| user | where | what it builds |
|---|---|---|
| MCU examples | `c/ports/{pico,esp32,arduino,ch582}` | mapped faces in flash, one target kind each |
| DOS programs | `c/ports/dos` | `SVFDEMO.EXE` (mode 13h) and `SVFVESA.EXE` (VBE 2.0), streamed faces |
| WASM picker | `c/ports/web` -> `web/` | `svf.wasm`, the font picker page ([web/README.md](../web/README.md)) |
| SDL2 / SDL3 | `c/ports/sdl` | `svfsdl2`, `svfsdl3`: SDL surfaces of every pixel format the kinds cover |
| ScummVM | `graphics/hires_text` (submodule user of this repo) | **not yet**: ScummVM still has its own SVF reader (`jamo_set.h`), which refuses a version 3 JSET block; card t_5a7bcd78 replaces it with this library |

## Files

| path | what |
|---|---|
| `include/svf.h` | the whole public API and every compile-time switch, with its contract in comments |
| `src/svf_face.c` | header, layout and table validation, `svf_open_mapped`, accessors, code point lookup |
| `src/svf_jamo.c` | JSET v1/v2 readers, JMAP (dense, SPARSE, LIST), `svf_jamo_pieces`, `svf_compose` |
| `src/svf_stream.c` | streamed faces: `svf_open_stream`, the block cache (empty under `SVF_NO_STREAM`) |
| `src/svf_draw.c` | targets, chains, `svf_measure_utf8`, `svf_draw_utf8`, the composed-syllable cache |
| `src/svf_scale.c` | scaled cells (empty under `SVF_NO_SCALE`) |
| `tests/` | `svfdump` (the C side of the Python tests), unit programs, fuzz harness and corpus script |
| `cross/` | cross builds, size tables and size/symbol gates (`SIZES.md`) |
| `bench/` | emulated speed benches and identity sweeps (`MEASUREMENTS.md`, `JSET2-IDENTITY.md`) |
| `ports/` | the examples above, their host checks (`ports/check`) and the embedded faces' notices (`ports/FACES.md`) |

Build the host library and `svfdump`: `make -C c` (outputs in `c/build`, `O=DIR` to move them).

## Faces: held whole or streamed

A face is opened in one of two ways; after that every call is the same.

- **Mapped** (`svf_open_mapped`): the whole file is in addressable memory (RAM, flash, PROGMEM). Every table and every
  glyph record is validated at open; the bytes must not change while the face is used. On AVR the library is built with
  `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'` so every face read goes through `pgm_read_byte`.
- **Streamed** (`svf_open_stream`): the file stays on disk, SD card or network. The header and tables are read once into
  a caller buffer (`svf_stream_tables_size` says how big); glyph rows are read on demand through an `svf_read_fn`
  callback, optionally through a block cache (`block_size` a power of two in 64..4096, slots of `block_size + 8` bytes,
  at least 2). A glyph record is checked when it is read. Not compiled under `-DSVF_NO_STREAM` (the three stream
  functions are then not even declared).

```c
/* mapped: a face linked into flash */
svf_face face;
if (svf_open_mapped(&face, face_bytes, face_len) != SVF_OK) { /* refused: see svf_err */ }

/* streamed: a file read through a callback, 8 cache slots of 1 KB */
static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
{
	FILE *fp = ctx;
	return fseek(fp, (long)off, SEEK_SET) == 0 ? (long)fread(dst, 1, len, fp) : -1;
}
static uint8_t tables[64 * 1024], cache[8 * (1024 + 8)];
svf_err err;
size_t need = svf_stream_tables_size(rd, fp, file_len, &err);  /* 0 and err set when the header is refused */
if (need && need <= sizeof tables)
	err = svf_open_stream(&face, rd, fp, file_len, tables, sizeof tables, cache, sizeof cache, 1024);
```

## Public API

Every function is safe with NULL pointers: one that returns `svf_err` returns `SVF_E_ARG`; the others return the
sentinel their comment names (a NULL face reads as a zeroed face). `c/tests/test_args.c` calls each with each.

### Errors (`svf_err`)

| value | meaning |
|---|---|
| `SVF_OK` | success |
| `SVF_E_MAGIC` | not an SVFN file |
| `SVF_E_VERSION` | not version 3 (convert a v2 file with `tools/svf2to3.py`) |
| `SVF_E_BPP` | bits per pixel not 1, 2 or 8 |
| `SVF_E_RANGE` | a size or offset outside the file, an empty glyph box, a code point or glyph that is absent |
| `SVF_E_NOMEM` | a caller buffer too small |
| `SVF_E_IO` | a read callback failed (streamed faces) |
| `SVF_E_ARG` | a NULL pointer or bad argument (also a target kind or scale this build does not compile) |
| `SVF_E_LAYOUT` | layout bytes, flags, alignment or offset table invalid, or a layout outside the build's `SVF_LAYOUTS` |

### Face status bits (`svf_status`)

A face that opens can still carry status bits: they say what was dropped, never a failure of the open.

| bit | name | meaning |
|---|---|---|
| 0x0001 | `SVF_FACE_CMAP_LINEAR` | code point table not strictly increasing: linear scan, the last entry wins |
| 0x0002 | `SVF_FACE_DY_IGNORED` | the header's dy range is invalid: every glyph at dy 0 |
| 0x0004 | `SVF_FACE_METRICS_DROPPED` | metrics table outside the file: dropped, cells advance by their width |
| 0x0008 | `SVF_FACE_JSET_BAD` | the JSET part fails validation, or has a version this build does not know: plain face |
| 0x0010 | `SVF_FACE_JSET_UNREAD` | a well-formed v1 or v2 block whose reader is not compiled: plain face |
| 0x0020 | `SVF_FACE_JMAP_BAD` | a version 3 block (JMAP) fails a JMAP rule, its fallback included |
| 0x0040 | `SVF_FACE_JMAP_UNREAD` | a version 3 block the build recognises but does not read: its fallback JSET is read instead, if any |

### Functions

| function | contract (one line; the full text is the comment in `svf.h`) |
|---|---|
| `svf_open_mapped(f, data, len)` | opens a face held whole; validates header, layout, tables, every glyph record and the JSET part |
| `svf_open_stream(f, rd, ctx, file_len, tables, tables_len, cache, cache_len, block_size)` | opens a face read through `rd`; on any error the face is all zero (not under `SVF_NO_STREAM`) |
| `svf_stream_tables_size(rd, ctx, file_len, err)` | bytes of `tables` that file needs with this build's readers; 0 with `err` set if the header is refused |
| `svf_stream_reads(f)` | calls made to the read callback since open (0 for a mapped face) |
| `svf_layouts(&set)` | the layout codes this build reads; 0 and NULL when it reads every valid layout |
| `svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`, `svf_flags`, `svf_status`, `svf_glyph_count` | header values; 0 for a NULL face |
| `svf_cmap_cp(f, i)` | code point of code point table entry `i`, or 0xFFFFFFFF |
| `svf_has(f, cp)` | non-zero if the face draws `cp` (a stored glyph, or a syllable / compat jamo it composes) |
| `svf_metrics_of(f, cp, &m)` | 1 from the metrics table, 0 without one (cell metrics), -1 when the face has no glyph |
| `svf_cell_bytes(f)` | bytes of one stored cell: `((cell_w * bpp + 7) / 8) * cell_h` |
| `svf_glyph(f, cp, cell, cell_len)` | copies the stored or composed rows of `cp` into `cell` (MSB first, rows padded to a byte) |
| `svf_is_jamo(f)` | non-zero if the face composes syllables (a usable JSET or JMAP) |
| `svf_jamo_pieces(f, cp, out)` | piece numbers of `cp` in draw order; returns 2 or 3 for a syllable, 1 for a compat jamo, 0 otherwise |
| `svf_compose(f, cp, cell, cell_len)` | composes `cp` by the maximum coverage of its pieces |
| `svf_is_mark_default(cp)` | the default mark predicate: U+0300..U+036F |
| `svf_chain_cache(c, buf, len)` | gives a chain a composed-syllable cache (round robin; same pixels with or without it) |
| `svf_target_init(t, kind, buf, buf_len, w, h, stride)` | fills a target (whole-target clip, defaults per kind); `SVF_E_ARG` for a kind not compiled |
| `svf_chain_scratch_bytes(c)` | the scratch `svf_draw_utf8` needs for this chain at its scale |
| `svf_measure_utf8(c, s, len, &e)` | width, ascent and descent of a line without reading a glyph |
| `svf_draw_utf8(c, s, len, x, y_baseline, t, scratch, scratch_len)` | draws a UTF-8 line; a failed streamed read skips that glyph and returns `SVF_E_IO` at the end |

Composition needs room: a streamed face **without** a cache composes into `2 * svf_cell_bytes` (the second half holds
the piece being read). `svf_chain_scratch_bytes` already accounts for that and for scaling.

### Chains, targets and scale

A `svf_chain` is a list of faces: each code point is drawn by the first face that has it (`svf_has`); a code point no
face has advances `missing_advance` pixels. Marks (`is_mark`, default U+0300..U+036F) advance 0 and are drawn over the
previous glyph. `scale_num / scale_den` (each 1..16, 0/0 meaning 1/1) scales the line: whole multiples repeat pixels,
other ratios are area-averaged (`tools/svfline.py` "Scaling" is the reference).

| kind | `SVF_TARGETS` bit | pixel |
|---|---|---|
| `SVF_T_GRAY8` | 0x001 | one byte, max(existing, coverage) |
| `SVF_T_MONO_PAGE` | 0x002 | SSD1306 pages: bit `y & 7` of `buf[(y >> 3) * stride + x]`, set at `mono_threshold` |
| `SVF_T_MONO_ROW` | 0x004 | 1 bpp rows, MSB first, same threshold rule |
| `SVF_T_RGB565` | 0x008 | `bg565`/`fg565` blended per channel (`SVF_TF_RGB16_BIGENDIAN` for high byte first) |
| `SVF_T_COVERAGE_CB` | 0x010 | `plot(ctx, x, y, coverage)` callback, no buffer |
| `SVF_T_INDEXED8` | 0x020 | palette index `index_base + level`, max rule (VGA/VBE 8 bpp, SDL CLUT8) |
| `SVF_T_RGB555` | 0x040 | 5/5/5 blend, bit 15 from `fg565` |
| `SVF_T_XRGB8888` | 0x080 | B, G, R, X bytes (VBE 32 bpp) |
| `SVF_T_RGB888` | 0x100 | B, G, R bytes |
| `SVF_T_GRAY` | 0x200 | `gray_bits` 1, 2, 4 or 8 a pixel, MSB or LSB first (`SVF_TF_GRAY_LSB_FIRST`) |

Every kind writes only pixels inside the clip rectangle and never a padding byte. The exact formulas are in `svf.h`
above `svf_target`.

```c
svf_face *faces[2] = {&ascii_face, &hangul_face};
svf_chain chain = {0};                 /* zeroed: scale 1/1, default marks, no cache */
chain.faces = faces;
chain.count = 2;

static uint8_t page[128 * 64 / 8], scratch[512];
svf_target t;
if (svf_target_init(&t, SVF_T_MONO_PAGE, page, sizeof page, 128, 64, 128) != SVF_OK) { /* kind not compiled */ }
if (svf_chain_scratch_bytes(&chain) > sizeof scratch) { /* scratch too small */ }

const char *s = "안녕 SVF";
svf_extent e;
svf_measure_utf8(&chain, s, strlen(s), &e);           /* e.width, e.ascent, e.descent */
svf_draw_utf8(&chain, s, strlen(s), 0, (int16_t)svf_ascent(&hangul_face), &t, scratch, sizeof scratch);
```

`c/ports/arduino/arduino.ino` is a complete small program along these lines (a mapped face in PROGMEM, MONO_PAGE).

## Compile-time switches

Every switch is a `-D` given to **every** source of the library and to every file that includes `svf.h` (`SVF_JMAP`
changes the size of `svf_face`). A feature left out is not in the object code at all. The defaults below were read with
`-dM -E` of `svf.h` under each toolchain on 2026-11-01 (host gcc 13.3 x86-64, DJGPP i586 gcc 12.2, emcc 6.0.13,
avr-gcc 16.1.0 `-mmcu=atmega328p`, arm-none-eabi-gcc 15.2.1 Cortex-M0+, riscv32-esp-elf-gcc 16.1.0,
xtensa-esp32s3/esp32-elf-gcc 16.1.0):

| switch | host, DOS, WASM, SDL | AVR | Cortex-M, RISC-V, Xtensa | `-DSVF_SMALL` (host) | what it does |
|---|---|---|---|---|---|
| `SVF_TARGETS` | 0x3FF | 0x3FF | 0x3FF | 0x3FF | OR of the kinds compiled; others refused with `SVF_E_ARG` |
| `SVF_NO_STREAM` | unset | unset | unset | unset | defined: no streamed faces (`svf_stream.c` empty) |
| `SVF_NO_SCALE` | unset | unset | unset | unset | defined: no scaling (`svf_scale.c` empty; ratios but n/n are `SVF_E_ARG`) |
| `SVF_LAYOUTS` | unset (all) | unset | unset | unset | comma list of `SVF_LAYOUT` codes read, e.g. `SVF_LAYOUT_MCU_STRICT`; others `SVF_E_LAYOUT` |
| `SVF_RD8(p)` | plain load | plain load | plain load | plain load | the byte read of mapped faces; AVR ports set `pgm_read_byte(p)` |
| `SVF_WORD_STORE` | 1 (x86, wasm) | 0 | 0 | 1 | 4-byte stores at any alignment; same pixels |
| `SVF_SMALL` | unset | unset | unset | set | umbrella: the four speed switches below default to 0 |
| `SVF_MERGE_WORDS` | 1 | 0 | 1 | 0 | word-at-a-time merge of jamo piece rows |
| `SVF_GRAY8_LUT1` | 1 | 0 | 1 (Xtensa 0) | 0 | 64 B nibble table for the GRAY8 1 bpp blit |
| `SVF_SCALE_FAST` | 1 | 1 | 1 | 0 | separable area average (610 B stack frame on AVR, 680 B on M0+) instead of the 2-D loop |
| `SVF_JSET_V1` | 1 | 1 | 1 | 1 | JSET version 1 reader |
| `SVF_JSET_V2` | 1 | 0 | 1 | 1 | JSET version 2 (compact) reader |
| `SVF_JSET_POP4` | 1 | 0 | 1 | 0 | nibble popcount table of the v2 reader |
| `SVF_JSET_TRUSTED` | 0 | 0 | 0 | 0 | 1 skips JSET content validation: only for faces built into flash, never for files |
| `SVF_JSET_BIG` | 1 | 0 | 0 | 0 | v1/v2 limits 19 x 28 classes, 128 / 128 / 64 sets (narrow: 12 x 12, 32 / 24 / 16) |
| `SVF_JMAP` | 1 | 0 | 0 | 0 | version 3 block (JMAP) reader; grows `svf_face` |
| `SVF_JMAP_LIST` | 1 | 0 | 0 | 0 | the LIST form (flag 0x08); follows `SVF_JMAP`, 1 without it is an `#error` |
| `SVF_JMAP_RECOG` | 1 (compiled out: `SVF_JMAP` is 1) | 0 | 0 | 0 | without `SVF_JMAP`: recognise a v3 block, read its fallback JSET |

How the defaults are decided (`svf.h`): `SVF_JMAP`, `SVF_JMAP_RECOG` and `SVF_JSET_BIG` are 1 only when the compiler is
not AVR, `SVF_SMALL` is not set, and one of `__unix__`, `_WIN32`, `__APPLE__`, `__DJGPP__`, `__EMSCRIPTEN__` is
defined; a bare-metal x86 build without those gets the MCU defaults. `SVF_JMAP_RECOG` only acts where `SVF_JMAP` is 0, so
on the host it needs an explicit `-DSVF_JMAP=0`. An explicit `-DSVF_X=0/1` always wins. `SVF_JSET_V1`, `SVF_JSET_V2` and
`SVF_JMAP` may not all be 0.

What the ports actually build with:

| build | flags on top of the defaults |
|---|---|
| Arduino Uno (`c/ports/arduino`, the `minimal` config of `check-features.sh`) | `-DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0`, PROGMEM reads |
| CH582 | the Uno switches (version 1 reader alone) |
| Pico, ESP32-C3/S3 | `-DSVF_NO_SCALE` and the profile's one `SVF_TARGETS` bit (`c/ports/profiles.txt`) |
| DOS, WASM, SDL | the defaults (every kind, streaming, scaling, JMAP, LIST, BIG) |

## Jamo sets: what each build reads

A jamo-set face (header flag bit 1) carries a JSET block; a syllable U+AC00..U+D7A3 is the maximum coverage of two or
three pieces (glyphs at U+F0000 + piece number). The block's forms, all specified in [spec/SVF.md](../spec/SVF.md):

- **JSET version 1** ("Jamo-set fonts"): class tables and set tables; the standard form, written by default.
- **JSET version 2** ("JSET block version 2 (compact; exception-only)"): bit-packed tables; written only on request
  (`--jset-version 2`, see "When to use version 2").
- **BIG limits** for versions 1 and 2: up to 19 lead x 28 tail classes and 128 / 128 / 64 initial / medial / final sets,
  against the narrow 12 x 12 and 32 / 24 / 16.
- **Version 3, JMAP** ("Version 3: mapping table (JMAP)"): a direct map from a syllable to its pieces, dense (all
  11,172) or SPARSE (a bitmap and NS entries), with an optional FALLBACK v1/v2 block for the syllables it does not list.
- **JMAP LIST** (flag 0x08, same section): a sorted list of at most 255 exceptions (syllable -> three piece numbers over
  the pool shared with the fallback); a miss goes to the fallback, without one the syllable is not composed.

| face carries | default host / DOS / WASM / SDL | AVR default | other MCU default |
|---|---|---|---|
| v1, narrow limits | composed | composed | composed |
| v2, narrow limits | composed | plain, `JSET_UNREAD` | composed |
| v1 or v2 over the narrow limits | composed (BIG) | plain, `JSET_BAD` | plain, `JSET_BAD` |
| v3 JMAP, dense or SPARSE | composed | plain, `JSET_BAD` (unknown version) | plain, `JSET_BAD` |
| v3 JMAP LIST | composed | plain, `JSET_BAD` | plain, `JSET_BAD` |

Other combinations: `-DSVF_JMAP_RECOG=1` on an MCU turns a v3 block into `JMAP_UNREAD` and reads its fallback JSET when
that reader is compiled (else `JSET_UNREAD` / `JSET_BAD` say why not); `-DSVF_JMAP=1 -DSVF_JMAP_LIST=0` applies only the
LIST header rules (R1', L2, L3, R4): a block that passes is `JMAP_UNREAD` with its fallback read, one that fails is
`JMAP_BAD`. The KS-only build `-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0` reads JMAP alone (a fallback is then
`JSET_UNREAD`). A bad JSET part never fails the open: the face loads plain and the status says why. The matrix is tested
by `test_status_unread_bits` and `test_jmap_list_status_matrix` in `tools/test_c_renderer.py`.

## Ports

| port | one line | README |
|---|---|---|
| `pico` | Raspberry Pi Pico (pico-sdk 2.3.1): colour ST7789 RGB565, grey SSD1327 GRAY8, mono SSD1306 MONO_PAGE | [ports/pico/README.md](ports/pico/README.md) |
| `esp32` | ESP-IDF, ESP32-C3 and ESP32-S3: colour ILI9341 (or `esp_rgb`), grey SSD1327, mono SSD1306 | [ports/esp32/README.md](ports/esp32/README.md) |
| `arduino` | Arduino Uno (and Mega size rows): SSD1306 over I2C, face in PROGMEM | [ports/arduino/README.md](ports/arduino/README.md) |
| `ch582` | WCH CH582M (YD-CH582M), SH1106 OLED over hardware I2C, bare metal, 24 MHz | [ports/ch582/README.md](ports/ch582/README.md) |
| `dos` | DJGPP: `SVFDEMO.EXE` in mode 13h and `SVFVESA.EXE` in VBE 2.0 LFB modes, faces streamed from files | [ports/dos/README.md](ports/dos/README.md) |
| `web` | emscripten glue `svf_web.c` for the WASM picker in `web/` | [ports/web/README.md](ports/web/README.md) |
| `sdl` | `svfsdl.c`, one source for SDL2 and SDL3, every SDL pixel format the kinds cover, headless byte check | [ports/sdl/README.md](ports/sdl/README.md) |

The original ESP32 (Xtensa LX6, Odroid-Go) has size rows (`esp32-xtensa`) but no port image: it needs its own driver and
board code. The Arduino Mega reads PROGMEM below 64 KB only (near `pgm_read_byte`); far reads are not supported.

## Tests and gates

| command | proves | time |
|---|---|---|
| `make -C c check` | `tools/test_c_renderer.py` under ASan/UBSan, then again with clang (350 tests on 2026-11-01); no-malloc; every `SVF_TARGETS` mask 0x000..0x3FF compiled warning-free (2066 jobs per compiler); kernel nets (`test-kernels`, `test-pad`, `test-blend16`, `test-vbe`); the narrow hot-path and LIST=0 object-code identity tests (need the Arm toolchain) | over 30 min on one host: the ASan pass alone took 966 s (2026-11-01) |
| `python3 -m unittest discover -s tools -p 'test_*.py'` | the Python tools, including the C tests above without the sanitizer pass | - |
| `sh c/cross/check-features.sh [OUT]` | builds the P1 probe for every switch config on AVR and Cortex-M0+: gated rows equal "Minimal config" of `SIZES.md` exactly, budgets hold, no symbol of an excluded feature, no `JMAP`/`jmap`/`BIG` strings; prints `features: OK` | 22 s on one host (2026-11-01) |
| `sh c/cross/test-check-features.sh` | the gates of `check-features.sh` on fake rows (no toolchain): `check-features-gates: OK` | about 1 s |
| `sh c/cross/build-all.sh [OUT]` | builds `c/src` with every toolchain for the probe profiles P0-P5 and the switch variants, prints the size tables (copy them into `SIZES.md` by hand); fails on a missing toolchain or a Cortex-M0+ P1/P2 above 8,192 B | 146 s on one host (2026-11-01) |
| `sh c/cross/build-all.sh --ports [OUT]` | every port image, the host checks of `c/ports/check`, the emulated screens; compares the "Port examples" table (43 OK lines at the JMAP-LIST merge) | not timed here |
| `sh c/cross/build-all.sh --port NAME [OUT]` | one port: `dos`, `web`, `sdl`, `arduino`, `ch582`, `pico` or `esp32` | - |
| `sh c/cross/test-build-all.sh` | the screens gate and the `SIZES.md` comparison on fixtures: `build-all-gates: OK` | about 13 s |
| `sh c/cross/test-manifest.sh`, `sh c/cross/test-installers.sh` | the toolchain installers' manifests; the installers themselves (manual, about 30 s) | under 1 s / 30 s |
| `sh c/ports/check/host-checks.sh`, `sh c/ports/check/run-screens.sh` | display drivers against recording stubs; the five emulated screens byte for byte | - |
| `sh c/bench/run-{pico,avr,dos,wasm,host,esp32,m33,rp2350}.sh [OUT]` | emulated speed rows and pixel checksums for `MEASUREMENTS.md`; `run-esp32-hw.sh` needs a real ESP32-S3 board | minutes each (not timed here) |
| `python3 c/bench/jset2-identity.py OLD_DUMP NEW_DUMP OLD_DIR NEW_DIR OUT.md` | pixel identity of every face between two `svfdump` builds (results in `c/bench/JSET2-IDENTITY.md`); `v2v3-identity.py` did the same for v2 -> v3 | - |
| `make -C c fuzz-smoke` | six libFuzzer targets (`fuzz`, `-strict`, `-rd`, `-nojmap`, `-nolist`, `-mcu`) for `FUZZ_SMOKE_S` (60) s each over the generated corpus; needs clang | about 6 min plus builds |

Toolchains and emulators are installed by `c/cross/install-toolchains.sh` and `c/bench/install-emulators.sh` into
`~/opt`.

## Sizes and speeds

Sizes live in [cross/SIZES.md](cross/SIZES.md) (its tables are compared by `build-all.sh --ports`, `check-features.sh`), speeds in
[bench/MEASUREMENTS.md](bench/MEASUREMENTS.md). The headline figures below are copied from `c/cross/SIZES.md` as of
ca86268; re-read that file before quoting them.

Library alone, the P1 probe (one mapped jamo face, MONO_PAGE), text bytes ("Minimal config"):

| toolchain | config | text | gated |
|---|---|---:|---|
| AVR (avr-gcc 16.1.0) | `minimal` (Uno flags) | 12,930 | exact |
| Cortex-M0+ (gcc 15.2.1) | `minimal` (v1 reader alone) | 6,162 | exact |
| Cortex-M0+ | `default` (both readers) | 7,381 | exact |
| AVR / M0+ | `minimal+RECOG` | 13,238 / 6,358 | budget 13,250 / 6,366 |
| AVR / M0+ | `minimal+JMAP` (LIST on) | 15,370 / 7,646 | budget 15,532 / 7,688 |
| AVR / M0+ | `minimal+JMAP+nolist` | 15,002 / 7,398 | budget 15,032 / 7,398 |
| AVR / M0+ | `ksonly` | 13,460 / 6,822 | budget 13,648 / 6,900 |
| AVR / M0+ | `minimal+BIG` | 12,956 / 6,158 | info |
| AVR / M0+ | `minimal+BIG+V2` | 15,314 / 7,369 | info |

Whole programs ("Port examples"):

| image | text | data | bss | note |
|---|---:|---:|---:|---|
| Arduino Uno, NEODG16G (`arduino` row, 10,124 B face) | 23,676 | 18 | 1,085 | stub link, Uno flags |
| Arduino Mega, Uno flags (`arduino-mega`) | 23,802 | 18 | 1,085 | |
| Arduino Mega, every kind and reader (`arduino-mega-rich`) | 40,490 | 18 | 1,094 | |
| ESP32-C3 / ESP32-S3 mono (stub link) | 22,174 / 20,576 | 0 | 1,088 / 1,092 | without faces 12,050 / 10,452 |
| ESP32 original (Xtensa LX6), P1 probe | 7,794 | 0 | 848 | size row only, no port image |
| Pico mono, real pico-sdk 2.3.1 image | 35,484 | 0 | 2,384 | "Pico SDK images" |
| CH582 mono, real SDK image | 22,456 | 20 | 1,232 | RAM used 5,876 B ("CH582 SDK image") |

Speed budgets (from `MEASUREMENTS.md`): Pico `-Os` MONO_PAGE `syl_ga` 48.39 µs (budget 50, met), `syl_bwelk` 58.23 µs
(**missed**; met at `-O2`, 47.18 µs), `screen32` 1,498.39 µs (budget 2 ms); DOS 486DX2-66 `line40_mapped` 11,876.45 µs
(budget 16 ms, met; cold streamed and DX-33 rows miss); WASM `line40_mapped` 13.74 µs (budget 1 ms).

## Adding a switch

1. **Default off on every MCU.** Put the default in `svf.h` next to the others and document it in the "Size switches"
   comment block; a feature for desktops follows the `SVF_JMAP` positive list (`__unix__ _WIN32 __APPLE__ __DJGPP__
   __EMSCRIPTEN__`, not `__AVR__`, not `SVF_SMALL`). An explicit `-D` must win.
2. **Size gate.** Add a `CONFIGS` entry to `c/cross/check-features.sh`, its row to `SIZES.md` "Minimal config", and a
   `BUDGETS` line if the row is held to a ceiling. The gated rows (`avr minimal`, `m0plus minimal`, `m0plus default`) must
   not move; raising a budget is a ruling, not an edit.
3. **Symbol rule.** Name the feature's statics with a unique prefix and add `check_absent CONFIG PREFIX` for every config
   that leaves it out (check that the symbol survives `-Os`, or the rule is vacuous; see `jlist` below). No strings in the
   library.
4. **Status matrix test.** Every face kind the feature reads or refuses gets a row in `tools/test_c_renderer.py` for
   builds with and without it, mapped and streamed (as `test_jmap_list_status_matrix`), plus fuzz seeds and, if the
   harness can reach a new path, a fuzz target.
5. **Hot-path identity.** If the switch touches the lookup or validation code, prove the object code of the old path is
   unchanged with the switch off (`test_narrow_hot_path_identical`, `test_jmap_nolist_identical`), and run the identity
   sweep of `c/bench/jset2-identity.py` over `svf/`.

## Known gaps

- The Cortex-M0+ `minimal+JMAP+nolist` budget has **zero headroom** (7,398 of 7,398): the next byte in the LIST=0 arm
  or the JMAP reader needs a re-measure and a budget ruling.
- `check_absent ... jlist` cannot fail on a real build (no `jlist_` symbol survives `-Os`); the `+nolist` size rows and
  `test_jmap_nolist_identical` are the real leak guard.
- No LIST reader without `SVF_JMAP` (an MCU exception face would need one); BIG with `SVF_NO_STREAM`/`mcu-strict` (an
  AVR BIG port) is not fuzzed.
- Arduino Mega: faces above 64 KB of flash need far reads, not supported.
- DOS: the rows read about +105 µs (+0.9 %) in a probe at 51a4020, cause not explained, table not re-taken.

Sources: `c/cross/SIZES.md` "JMAP-LIST identity, budgets and follow-ups", the "Implemented" notes of
`docs/superpowers/specs/2026-10-26-jset-limits-design.md` and `2026-10-27-jmap-list-design.md`, `c/bench/MEASUREMENTS.md`
"Results". The development status of the whole repository is in [docs/STATUS.md](../docs/STATUS.md).
