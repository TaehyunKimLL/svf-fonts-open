**English** | [한국어](renderer-design.ko.md)

# Portable C SVF renderer: design

Card t_a5ca9404, 2026-10-19. This document describes the renderer to build. The next step is an implementation plan;
implementation is card t_78219730 and the WASM page is card t_fe9f6c30.

## Why

SVF faces exist today only for ScummVM. Two C++ code paths read them (`graphics/hires_text`), plus the Python tools in
this repo. The Korean jamo sets are the valuable part. A set of 13–20 KB holds all 11,172 Hangul syllables, so full Korean
text fits on devices with a few hundred KB of memory, or less. The user wants one independent C library that reads the
same files everywhere:

- **Web:** a WASM build for preview and font picking.
- **DOS:** standalone programs. This is not ScummVM, whose C++ code stays as it is.
- **Microcontrollers:** ESP32, Raspberry Pi Pico (RP2040/RP2350), Arduino-class boards.

The main use is **UI text**: menus, status lines and short messages, on monochrome OLEDs (SSD1306-class, 1 bpp) and
colour TFTs (ILI9341/ST7789-class, RGB565).

**What counts as failure (user):** using too much memory, or being too slow, even when it otherwise works. The budgets
below make that measurable.

## Goals

1. Read every SVFN v3 face in this repo (`svf/dos`, `svf/jamo-extra`, `svf/iolo`) and draw exactly what the
   Python reference draws. "Exactly" means byte-identical glyph and composed-syllable coverage
   (`tools/jamoset.py parse_svfn`, `unpack`, `pieces_of`, `compose`).
2. Compose U+AC00..U+D7A3 from a JSET block (classes up to 12×12, sets up to 32/24/16), and draw U+3131..U+3163 from
   compatibility pieces.
3. Draw a UTF-8 string on one line through a **face chain**. Each code point is taken from the first face that has it, as
   with a Latin face plus a Hangul face (PAPLG16 + PAPLG18). The line is aligned on one baseline, with advances, per-glyph
   dy, and combining marks under flag bit 2.
4. Run with no dynamic allocation in the core. All memory comes from the caller: a face struct, an optional cache buffer,
   and a scratch cell.
5. Read a face in one of two ways:
   - **mapped:** a pointer to the whole file in memory or flash, such as XIP flash on Pico/ESP32, PROGMEM, or a WASM heap
     array.
   - **streamed:** a read callback `read(ctx, offset, buf, len)`, used for DOS files and SD cards.
6. Provide output paths for the target displays:
   - a coverage callback (generic);
   - 1 bpp page buffer (SSD1306 layout, 8 rows per byte);
   - 1 bpp row-major buffer;
   - RGB565 buffer, blending against a known solid background colour;
   - 8-bit coverage buffer (the WASM page turns it into RGBA).
7. Scale:
   - **Whole multiples (2×, 3×, …):** pixel copy, exact.
   - **Other factors:** area-averaged AA. This is a fallback only; a face baked at the size is always preferred. The
     user decided this earlier: scaling is the renderer's job.
8. Build as C99 with `-Wall -Wextra -Werror` on gcc, clang, DJGPP gcc, arm-none-eabi-gcc, xtensa/riscv ESP-IDF gcc,
   avr-gcc and emscripten. No dependency beyond the standard headers `<stdint.h>`, `<stddef.h>` and `<string.h>`.

## Non-goals

- **No ScummVM integration.** No ScummVM maps (`[fonts]`, `[load]`, `[preload]`, `.HOT`), no CLUT8 compositing, no
  outline or shadow decoration.
- **No paragraph layout.** No bidi, shaping or kerning. A small optional helper wraps a string to a width at spaces and
  between Hangul syllables; it lives outside the core.
- **No SVFN v1 and v2.** Version 1 files are ordered by code page and none remain in the repo; version 2 was the
  fixed-stride form, converted to v3 in 2026-10 (`tools/svf2to3.py`). The core rejects both with `SVF_E_VERSION`.
- **No 8 bpp optimisation.** The format allows 8 bpp, but no face uses it. The parser accepts 8 bpp and the generic paths
  draw it; no fast path is written for it.
- **No reading of the shadow byte or the code page field.** No reader uses either. See "Spec fixes" below.
- **No writing or editing of fonts.** That stays in the Python tools.

## Anti-goals: this is a failure even if it works

- Memory beyond the budget below, a hidden `malloc`, or a copy of glyph data into RAM when the face is mapped.
- Missing the speed budgets on the reference boards.
- Output that differs from the Python reference on any repo face. A "close enough" composition is not acceptable.

## Budgets (the user accepted these on 2026-10-19; implementation measures them)

| What | Budget |
|---|---|
| Face state in RAM, mapped face | about 64 bytes per face (pointers, header fields). Tables are read in place |
| Scratch for one glyph | one cell, from the caller: `ceil(w*bpp/8)*h` bytes, 144 bytes at 24×24 2 bpp (largest repo face 46×54 2 bpp: 648 B); 2× that for AA scaling, and for composing a streamed face with no block cache (piece buffer + target) |
| Streamed face | cmap + metrics (8 + 4 bytes per glyph: 1.2 KB for a jamo set, up to ~38 KB for the largest face) and the JSET block (≤ 12,321 bytes with the version 1 reader, ≤ 9,246 in a version 2 only build) in caller memory; glyph data through a caller-sized block cache (for example 4 KB blocks × N) |
| Code size | ≤ 8 KB on Cortex-M0+ at `-Os`, core plus one output path |
| Smallest target | Arduino Uno class (2 KB RAM, 32 KB flash): one 1 bpp jamo set (~13 KB) in PROGMEM drawn to an SSD1306 |
| Pico, 125 MHz | ≤ 50 µs to compose and draw one 16 px syllable; ≤ 2 ms to redraw a full 128×64 OLED screen of text (~32 glyphs) |
| DOS, 486 class | one 40-character line within one frame (16 ms); a streamed face reads whole blocks only, never byte by byte (DJGPP: one DOS call per byte was measured at 77 µs) |
| Web (WASM) | ≤ 1 ms to redraw a sample line in the picker |

## How it works

### Face

- **Open.** `svf_open_mapped(face, ptr, len)` / `svf_open_stream(face, read_cb, ctx, file_len, tables_buf, tables_len)` (a streamed face is validated against its file length before any read) validate the
  header the way `jamoset.parse_svfn` and the engine do:
  - magic `SVFN`, version 3, the layout bytes (and the build's supported set), bpp in {1, 2, 8};
  - every offset and size inside the file;
  - the dy range rule (SVF.md "Per-glyph dy": a bad range means dy 0 for all glyphs).
- **Returns.** Open returns an error code; there are no warnings to print. A JSET block that fails validation (SVF.md
  rules, `jamoset.unpack` order) leaves a plain face plus a status flag the caller can read. This matches the engine.
- **cmap lookup.** Binary search over the cmap, which jamoset writes sorted. An unsorted cmap is detected at open and
  falls back to a linear scan.
- **Glyph rows.** MSB first and padded to a byte. In 2 bpp the leftmost pixel is the top bit pair, and coverage is
  level × 85.

### Jamo sets

- **Same rules as the reference.** `pieces_of` and `compose` follow `jamoset.py`: the decomposition of the code point;
  the lead, vowel and tail classes; the set lookup `(leadClass*21+vowel)*TC+tailClass`; the piece tables. 0xFFFF means
  blank.
- **Max per pixel.** A composed syllable is the per-pixel maximum of its pieces: bitwise OR at 1 bpp, max per 2-bit
  field at 2 bpp. The result goes into the caller's scratch cell.
- **Advance.** A syllable advances by the JSET advance, or by the cell width when that is 0.
- **Piece dy.** Pieces carry no dy.

### Line drawing

`svf_draw_utf8(chain, n_faces, text, x, y_baseline, target, opts)`:

- **Text handling.** Decodes UTF-8 (invalid bytes become U+FFFD, or are skipped if no face has U+FFFD). For each code point
  it picks the first face of the chain that has it, then draws.
- **Baseline.** Glyphs stand on the baseline. A face's cell top is `y_baseline - ascent`, moved by the glyph's dy.
- **Combining marks** (flag bit 2): a mark advances 0 and is drawn at `anchorX - originX`, where anchorX is the pen of the
  previous non-combining glyph on the line (a mark first in the line draws at the current pen) and
  `originX = min(-bearingX, cellWidth)` when the face has bit 2 and `bearingX < 0`, else 0 (engine:
  `glyph_source_svfn.cpp:384-390`, `engines/scumm/hires_text.cpp:1329-1334`). *My call:* "is combining" is a predicate
  hook on the chain; the default covers U+0300..U+036F only, so the core carries no Unicode table. A caller that needs
  more passes its own. No repo face holds a combining mark today, so the test uses a small synthetic face.
- **Metrics.** `svf_measure_utf8` gives width, ascent and descent (including dy reach) without drawing.
- **No metrics table** (no face in this repository today; the tests drop the table of a real face by validation): a glyph
  advances by the cell width. The engine uses East Asian Width there; no width table is needed.
- **Syllables with a valid JSET:** every U+AC00..U+D7A3 is composed, even from blank pieces. U+3131..U+3163 use the compat
  piece only when it is not 0xFFFF, else the cmap glyph. At open, every piece number the tables name must have a glyph
  (the engine's `JamoGlyphSource::usable`). Bits past the cell width in a row's last byte are masked, as the engine does.
- **Missing glyphs.** A code point no face has draws nothing and advances by a caller-set default (the default is 0). A
  ScummVM-style box is not drawn.

### Targets

- **Target interface.** A target is a small struct: buffer pointer, width, height, stride, a format enum, colours, and a
  clip rectangle.
- **Formats:**
  - `SVF_T_COVERAGE_CB`: calls `plot(ctx, x, y, coverage 0..255)` per non-zero pixel.
  - `SVF_T_MONO_PAGE`: SSD1306 pages.
  - `SVF_T_MONO_ROW`: 1 bpp row-major, MSB first.
  - `SVF_T_RGB565`: blends foreground and background by coverage; byte order is a flag.
  - `SVF_T_GRAY8`: coverage.
- **Mono output.** Mono targets threshold 2 bpp coverage at a caller value, default 128.
- **Clipping.** Every target clips to its rectangle.

### Scaling

- **Settings.** A `scale_num/scale_den` pair, defaulting to 1/1, applied per line.
- **Whole multiples.** Each source pixel is drawn as an N×N block.
- **Other factors.** Box-filter area averaging into coverage, then the target's normal path. This is the only path that
  needs the 2× scratch.
- **No reference to match.** The engine never scaled (graphics/hires_text README: "nothing here scales"). Scaled output
  is therefore tested against a Python reference written for this card in `tools/` (see Tests), not against ScummVM.

### Streaming

- **Callback.** `read_cb(ctx, offset, dst, len)` returns the bytes read.
- **Tables.** The core reads the tables once at open into the caller's `tables_buf`; open fails with `SVF_E_NOMEM` and the
  needed size if the buffer is too small.
- **Glyph data.** Read through an optional block cache: caller memory split into fixed blocks with LRU. Without a cache,
  every glyph is read on its own, one call per glyph and never per byte.
- **Batching.** A line draw first collects the glyphs it needs. On a cold cache it reads them in file order to limit seeks,
  since a Korean line otherwise seeks 10–20 times (DOS measurement).

### Optional caches

- **Composed-syllable cache.** Caller memory of N cells keyed by code point. 0 means compose every time, which the Pico
  budget already allows.

## Layout in the repo

```
c/include/svf.h          the public API (one header)
c/src/svf_face.c         open, validate, cmap, metrics, glyph rows
c/src/svf_jamo.c         JSET parse/validate, pieces_of, compose
c/src/svf_draw.c         UTF-8, chain, line, targets, scaling
c/src/svf_stream.c       read callback, block cache
c/tests/                 golden tests (host), size/perf probes
c/ports/                 thin examples: dos/ (DJGPP, VGA mode 13h or a text dump), pico/ (SSD1306 I2C), esp32/ (ILI9341 SPI), arduino/ (Uno + SSD1306), web/ (emscripten glue; the page itself is t_fe9f6c30)
```

## Tests and measurements

- **Golden (host, in the svf-fonts gate).** A Python script uses `jamoset.py` to write expected outputs for every face in
  `svf/`:
  - every glyph's rows and metrics;
  - all 11,172 composed syllables for jamo faces;
  - the compatibility pieces;
  - a set of sample lines with chains (including a dy face and a synthetic flag bit 2 face).
  *My call:* the line layout reference is a new Python script in `tools/`, reviewed with the C code. No Python line layout
  exists yet. This library is independent of ScummVM, so the engine is not the authority for lines. The rules above came
  from the engine, and the script is checked against them in review.
  The C test reads the same faces and compares byte for byte; 0 differences is the only pass. The faces come from
  `svf/` as they are, with no copies.
- **Malformed input.** Truncated files, offsets past the end, bad dy ranges, JSET blocks with 13 classes, wrong lengths
  and missing pieces. All must fail the way `test_jamoset.py` expects the engine to, and never read out of bounds. The host
  build runs with `-fsanitize=address,undefined`.
- **Scaling.** A small Python reference in `tools/` (integer and box-filter scaling of a coverage cell) gives the expected
  output.
- **No allocation.** The core object files have no undefined `malloc`, `calloc`, `realloc` or `free` symbol (`nm` check
  in the gate).
- **Boards and toolchains.** *My call (2026-10-19, the user handed the decision over):* no physical board is assumed. The
  cross toolchains (arm-none-eabi-gcc, avr-gcc, emscripten, ESP-IDF or a riscv/xtensa gcc) are installed in user space
  under `~/opt`. The project gate builds only what the gate host has; the cross builds are checked by a separate script
  that the plan names. Speed is measured on emulators (QEMU or the RP2040 emulator for Pico, simavr for AVR, DOSBox-X for
  DOS), with counted cycles where the emulator gives them, and every number is labelled as emulated. A real board
  re-measures when one is at hand.
- **Size and speed.** The board budgets are measured on real hardware, or on the closest available emulator when no board
  is at hand, and recorded in a measurements file with the board, clock and compiler. The DOS budget is measured in
  DOSBox-X at a 486 cycle setting, labelled as emulated. Missing a budget is a finding to report, not a reason to change
  the budget silently.
- **Gate.** Add the C build, the golden test and the nm check to the `svf-fonts` project gate. The builder proposes the
  dispatch.toml line; the operator applies it.

## Spec fixes that come with this work (spec/SVF.md)

- Document flag bit 2 (marks at origin). 64 faces set it; the prose does not describe it.
- State that the shadow byte (9) and the code page field (10) are unused by current readers and must be ignored by new
  ones.
- Define "cell" once. SVF.md says "a syllable is two cells wide", which is the engine's buffer notion. In the file a cell
  is the stored glyph box.
- Remove or move the ScummVM `[load]` / `[preload]` sections to a "ScummVM" appendix, as the file's header promises once
  the portable renderer has its own API.

## Left to the builder

- **Exact API names, struct layouts and error codes**, within the shapes above.
- **The block cache's eviction details** and the line pre-pass.
- **Which emulator stands in** for a missing board, and the DOS port example's video mode.
- **AVR PROGMEM access**, keeping the core free of target `#ifdef`s where possible. Likely a byte-read hook or macro used
  only for mapped faces.
- **Whether the JS compose port in research/jamo-studio is retired** once the WASM build exists. That decision belongs
  to t_fe9f6c30.
