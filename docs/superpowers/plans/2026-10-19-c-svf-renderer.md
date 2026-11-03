# Portable C SVF Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a malloc-free C99 library in `c/` that reads SVFN v2 faces and draws them, including composed Hangul from JSET
blocks, with output identical to `tools/jamoset.py`. It must run on the host, DOS (DJGPP), WASM and microcontrollers.

**Architecture:** One public header `c/include/svf.h` and four sources: face, jamo, draw and stream. A host dump tool
(`c/tests/svfdump.c`) writes the library's view of a face in a fixed binary format. Python unittests in `tools/` build the
library, run the dump, and compare it byte for byte with the same data computed by `jamoset.py`. The Python tests are
the golden reference, so no golden files are stored. The existing gate (`unittest discover -s tools`) therefore runs the C
tests with no new gate step except the nm check. Line layout and scaling get small new Python references in `tools/`.

**Tech Stack:** C99 (gcc/clang, `-std=c99 -Wall -Wextra -Werror`), make; Python 3 unittest; cross: DJGPP gcc (installed at
`~/opt/djgpp`), arm-none-eabi-gcc, avr-gcc, emscripten, riscv/xtensa gcc (installed in Task 9).

**Spec:** `spec/renderer-design.md` (read it first; its "My call" lines are decisions, not suggestions). Format:
`spec/SVF.md`. Reference code: `tools/jamoset.py` (`parse_svfn` 573, `unpack` 525, `pieces_of` 434, `compose` 844,
`decompose` 429, constants 45-60).

## Global Constraints

- C99 only; headers allowed: `<stdint.h>`, `<stddef.h>`, `<string.h>`. No `<stdlib.h>` / `<stdio.h>` in `c/src/`.
- No `malloc`/`calloc`/`realloc`/`free` symbol in any `c/src/*.o` (checked by `c/check.sh`).
- `-std=c99 -Wall -Wextra -Werror` on every compiler; host tests also with `-fsanitize=address,undefined`.
- Byte-identical with `jamoset.py` on every face under `svf/` (`svf/dos`, `svf/jamo-extra`, `svf/iolo`, `svf/games/*`).
- SVFN v1 rejected (`SVF_E_VERSION`); bpp ∈ {1, 2, 8}; shadow byte and code page field never read.
- JSET limits: lead/tail classes 1..12, sets 1..24/1..16/1..16, block ≤ 11,681 bytes; pieces at U+F0000 + n; 0xFFFF = blank.
- 2 bpp coverage of level k is `k * 85`; rows MSB-first, padded to a byte; bits past the cell width are masked.
- Budgets (measured in Task 10): face state ≤ 64 B on 32-bit targets (a test asserts sizeof with -m32); code ≤ 8 KB on Cortex-M0+ `-Os` (core + one target); Pico 125 MHz ≤ 50 µs per 16 px syllable and ≤ 2 ms per 128×64 screen; DOS 486 one 40-char line ≤ 16 ms; WASM sample line ≤ 1 ms.
- Measurements on emulators are labelled "emulated" with emulator, clock and compiler.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A truncated or hostile face (offsets/sizes past the end, cmap count overflow `count*8`, metrics past the end) must fail open with an error code and never read out of bounds — Task 1 fuzz-style truncation test runs every face truncated at 40 points under ASan.
2. A UTF-8 string with invalid bytes, overlong forms, surrogates or a truncated tail must draw U+FFFD (or skip) and never read past the terminator/length — Task 4 `test_utf8_invalid`.
3. Drawing partly or wholly off the target (negative x/y, glyph wider than target, dy pushing ink above row 0) must clip, not write outside the buffer — Task 5 `test_clip_edges` under ASan.
4. A streamed face whose read callback returns short reads or an error mid-line must stop drawing that glyph and report, not draw stale cache bytes — Task 3 `test_stream_short_read`.
5. A chain whose faces have different ascents and cell heights (PAPLG16 cell 18 / ascent 14 + PAPLG18 ascent 17) must share one baseline — Task 4 `test_chain_baseline_paplg`.

---

## File structure

```
c/include/svf.h            public API (all types and functions below)
c/src/svf_face.c           open (mapped), header/offset validation, cmap lookup, metrics, glyph row access
c/src/svf_jamo.c           JSET validation and lookup, pieces_of, compose
c/src/svf_stream.c         open (streamed), table loading, block cache
c/src/svf_draw.c           UTF-8 decode, chain, line layout, measure, targets, scaling, syllable cache
c/Makefile                 host lib + tests; CC/CFLAGS overridable; `make check` runs c/check.sh
c/check.sh                 nm no-malloc check over c/src objects
c/tests/svfdump.c          host CLI: writes the library's view of a face/line (format per task below)
c/tests/synth/             tiny synthetic faces made by tools/svf_synth.py (marks, malformed)
c/cross/build-all.sh       cross builds + size report (Task 9)
c/bench/                   emulated speed probes (Task 10)
c/ports/{dos,pico,esp32,arduino,web}/   examples (Task 11)
tools/svfline.py           Python reference: line layout + targets + scaling (Tasks 4-6)
tools/svf_synth.py         writes synthetic faces (marks-at-origin face, malformed variants)
tools/test_c_renderer.py   unittest: builds c/ and compares svfdump with jamoset/svfline
```

`tools/test_c_renderer.py` builds with `make -C c` into a temp dir (`O=` variable), skips with a clear message if no `cc`
exists, and runs every face it compares.

---

### Task 1: Face open, validation, cmap, metrics, glyph rows (mapped)

**Files:** Create `c/include/svf.h`, `c/src/svf_face.c`, `c/Makefile`, `c/check.sh`, `c/tests/svfdump.c`,
`tools/test_c_renderer.py`.

**Interfaces — Produces:**
```c
typedef enum { SVF_OK = 0, SVF_E_MAGIC, SVF_E_VERSION, SVF_E_BPP, SVF_E_RANGE, SVF_E_NOMEM, SVF_E_IO, SVF_E_ARG } svf_err;
typedef struct { uint8_t advance; int8_t bearing_x; uint8_t ink_w; int8_t dy; } svf_metrics;
typedef struct svf_face svf_face;          /* full definition in svf.h; caller allocates; sizeof <= 96 */
svf_err svf_open_mapped(svf_face *f, const uint8_t *data, size_t len);
uint8_t svf_bpp(const svf_face *f); uint8_t svf_cell_w(const svf_face *f); uint8_t svf_cell_h(const svf_face *f);
uint8_t svf_ascent(const svf_face *f); uint16_t svf_flags(const svf_face *f);
int     svf_has(const svf_face *f, uint32_t cp);                 /* cmap glyph or composable syllable/compat */
int     svf_metrics_of(const svf_face *f, uint32_t cp, svf_metrics *m);   /* 0 if no metrics table: m = {cell_w,0,cell_w,0} */
svf_err svf_glyph(const svf_face *f, uint32_t cp, uint8_t *cell, size_t cell_len); /* stored rows, padding masked; SVF_E_RANGE if absent */
size_t  svf_cell_bytes(const svf_face *f);                       /* ((cell_w*bpp+7)/8)*cell_h */
```
Validation order and rules = `jamoset.parse_svfn` plus the engine's (spec "Face"): magic, version 2, bpp, every offset +
size within `len` using 64-bit arithmetic, dy range rule (bad range → all dy 0, `SVF_FACE_DY_IGNORED` status bit readable
via `svf_status(f)`). cmap sortedness detected once at open (status bit `SVF_FACE_CMAP_LINEAR`).
Every read of mapped face bytes goes through `SVF_RD8(p)` / `SVF_RD16LE(p)` / `SVF_RD32LE(p)` macros in `svf.h`,
defaulting to plain loads; an AVR build defines `SVF_RD8(p)` as `pgm_read_byte(p)` (Task 11 arduino) — no other target
`#ifdef` in `c/src/`.

`svfdump FACE glyphs` output, little-endian: for each cmap entry in cmap order: u32 cp, 4 metrics bytes (zeros if no
table), cell bytes.

- [ ] **Step 1: Write the failing test** `tools/test_c_renderer.py::TestFace::test_glyphs_all_faces` — for every
  `svf/**/*.SVF|svf`, expected bytes built from `jamoset.parse_svfn` (`f.glyphs`, `f.metrics`, `f.dy`, padding bits
  masked) in cmap order; `assertEqual(run_dump(face, 'glyphs'), expected)`. Plus `test_truncated_faces_fail`: each face
  truncated at 40 evenly spaced lengths (and 0, 35, 36) → `svfdump` exits 2 with an error name, never crashes; the test
  binary is built with ASan/UBSan.
- [ ] **Step 2: Run** `python3 -m unittest tools.test_c_renderer -k TestFace` → FAIL (no `c/`).
- [ ] **Step 3: Implement** the functions above in `c/src/svf_face.c`; `svfdump.c` (host only, may use stdio/stdlib)
  maps the file with fread into a buffer. `c/Makefile` targets: `lib` (`libsvf.a`), `svfdump`, `svfdump-asan`, `check`.
  `c/check.sh`: `nm -u` on each `c/src/*.o`, fail on `malloc|calloc|realloc|free`.
- [ ] **Step 4: Run** the same command → PASS for 153 faces; `make -C c check` → `no-malloc: OK`.
- [ ] **Step 5: Commit** `c: SVFN v2 face open, validation, cmap and glyph rows (153 faces match jamoset)`.

### Task 2: JSET validation, pieces_of, compose

**Files:** Create `c/src/svf_jamo.c`; modify `c/include/svf.h`, `c/tests/svfdump.c`, `tools/test_c_renderer.py`.

**Interfaces — Consumes:** Task 1. **Produces:**
```c
int     svf_is_jamo(const svf_face *f);          /* valid JSET present */
int     svf_jamo_pieces(const svf_face *f, uint32_t cp, uint16_t out[3]); /* count (2 or 3; 1 for compat), 0 if not composable */
svf_err svf_compose(const svf_face *f, uint32_t cp, uint8_t *cell, size_t cell_len); /* syllable/compat by max coverage */
```
`svf_glyph` from Task 1 now routes U+AC00..D7A3 and compat-with-piece through `svf_compose` when `svf_is_jamo`.
`svf_has` (Task 1) must also answer true for every U+AC00..D7A3 and for compat jamo with a piece when the face has a valid
JSET (a face chain picks faces by it). JSET rules: `jamoset.unpack` order and messages' conditions — including the
conditional finSet check (a finSet entry >= NF is valid when `i % TC` is not a tail class of any tail 1..27), plus "every named piece has a glyph" (engine `usable`); a
failing block → plain face, status bit `SVF_FACE_JSET_BAD`. Syllable advance = JSET advance or cell width; bearing 0, dy 0.
Max-coverage per pixel: OR at 1 bpp, per-2-bit-field max at 2 bpp, byte max at 8 bpp.

`svfdump FACE syllables`: 11,172 cells U+AC00..D7A3 then 51 cells U+3131..3163 (blank cell if not drawable), then a byte
`svf_is_jamo`.

- [ ] **Step 1: Failing tests** `TestJamo::test_syllables_all_jamo_faces` (expected from `jamoset.compose` for every face
  with a JSET; compat from compat piece or cmap glyph per `blank_compat` rule) and `test_malformed_jset_falls_back`
  (synthetic faces from `tools/svf_synth.py --jset-bad KIND` for KIND in `lc13, tc13, ni25, length, leadclass, finset,
  missing_piece` → dump shows `is_jamo = 0` and the cmap glyphs unchanged), `test_unused_finset_entry_accepted` (a face
  whose finSet holds NF for a tail class no tail 1..27 uses still composes like jamoset), and `test_has_composable`
  (`svfdump FACE has U+AC00 U+3131 U+0041` on a jamo face whose cmap lacks U+AC00).
- [ ] **Step 2: Run** `-k TestJamo` → FAIL.
- [ ] **Step 3: Implement** `svf_jamo.c` and `tools/svf_synth.py` (writes faces with `jamoset.write_svfn`; the malformed
  kinds patch bytes of a valid small jamo face, e.g. `svf/iolo` 16 px).
- [ ] **Step 4: Run** → PASS (all jamo faces, all 7 kinds).
- [ ] **Step 5: Commit** `c: JSET validation and syllable composition (byte-identical to jamoset.compose)`.

### Task 3: Streamed faces and the block cache

**Files:** Create `c/src/svf_stream.c`; modify `svf.h`, `svfdump.c`, `tools/test_c_renderer.py`.

**Interfaces — Produces:**
```c
typedef long (*svf_read_fn)(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len);  /* bytes read, <0 error */
size_t  svf_stream_tables_size(svf_read_fn rd, void *ctx, uint32_t file_len, svf_err *err);   /* bytes open needs for cmap+metrics+JSET */
svf_err svf_open_stream(svf_face *f, svf_read_fn rd, void *ctx, uint32_t file_len, uint8_t *tables, size_t tables_len,
                        uint8_t *cache, size_t cache_len, uint16_t block_size);  /* cache may be NULL/0 */
uint32_t svf_stream_reads(const svf_face *f);   /* callback calls so far (test/bench counter) */
```
`file_len` is the file size: every range is validated against it exactly as Task 1 validates against `len`, before any
read (design review: a callback alone cannot bound reads). `cache_len` includes the cache's own metadata: each block
slot is `block_size` bytes plus an 8-byte tag (u32 block number, u32 LRU stamp) stored at the front of `cache`;
`block_size` must be a power of two in 64..4096 and `cache_len` must hold at least 2 slots, else `SVF_E_ARG`.
Same validation as Task 1, reading the header and tables through `rd`. Without a cache each glyph/piece is one `rd` call
of exactly the cell bytes; with a cache, whole aligned blocks, LRU. Compose of a streamed face reads pieces into the
second half of the caller cell buffer: `svf_compose` needs `cell_len >= 2*svf_cell_bytes(f)` for streamed faces with no
cache (`SVF_E_NOMEM` otherwise) — document in `svf.h`.

`svfdump --stream[=CACHE_KB:BLOCK] FACE glyphs|syllables` uses the stream path; output must equal the mapped dump.

- [ ] **Step 1: Failing tests** `TestStream::test_stream_equals_mapped` (every face, three configurations: no cache,
  4 KB cache / 512 B blocks, 32 KB / 4 KB), `test_tables_size_too_small` (`SVF_E_NOMEM` and the size), and
  `test_stream_short_read` (svfdump `--fail-read-after N`: the glyph whose read fails returns `SVF_E_IO`, dump records the
  error, later glyphs still correct; also a short read while REPLACING an occupied cache block: that glyph returns
  `SVF_E_IO`, the replaced slot is invalidated, and no later glyph shows bytes of the old block).
- [ ] **Step 2: Run** `-k TestStream` → FAIL.
- [ ] **Step 3: Implement** `svf_stream.c`; face struct gains a source union (mapped pointer / read callback + cache).
- [ ] **Step 4: Run** → PASS; also count reads: a jamo syllable with no cache uses ≤ 3 calls (`svf_stream_reads`).
- [ ] **Step 5: Commit** `c: streamed faces with a caller-sized block cache`.

### Task 4: Line layout reference and `svf_draw_utf8` (GRAY8 target)

**Files:** Create `c/src/svf_draw.c`, `tools/svfline.py`; modify `svf.h`, `svfdump.c`, `tools/svf_synth.py`,
`tools/test_c_renderer.py`.

**Interfaces — Consumes:** Tasks 1-3. **Produces:**
```c
typedef int (*svf_is_mark_fn)(uint32_t cp);   /* default svf_is_mark_default: U+0300..U+036F */
typedef struct { svf_face **faces; uint8_t count; svf_is_mark_fn is_mark; uint8_t missing_advance; } svf_chain;
typedef enum { SVF_T_GRAY8, SVF_T_MONO_PAGE, SVF_T_MONO_ROW, SVF_T_RGB565, SVF_T_COVERAGE_CB } svf_target_kind;
typedef struct svf_target {
  svf_target_kind kind; uint8_t *buf; size_t buf_len; int16_t w, h; uint16_t stride;     /* stride in bytes */
  int16_t clip_x0, clip_y0, clip_x1, clip_y1;                             /* half-open; set by svf_target_init to full */
  uint16_t fg565, bg565; uint8_t mono_threshold; uint8_t flags;           /* SVF_TF_565_BIGENDIAN */
  void (*plot)(void *ctx, int16_t x, int16_t y, uint8_t cov); void *ctx;
} svf_target;
svf_err svf_target_init(svf_target *t, svf_target_kind k, uint8_t *buf, size_t buf_len, int16_t w, int16_t h, uint16_t stride);
/* SVF_E_ARG unless w,h > 0, stride >= the row bytes of kind, and buf_len covers the buffer (SSD1306 pages: ceil(h/8)*stride).
   svf_draw_utf8 re-validates and intersects the clip rectangle with [0,w)x[0,h) on every call; addresses use size_t. */
typedef struct { int16_t width, ascent, descent; } svf_extent;  /* descent includes dy reach */
svf_err svf_measure_utf8(const svf_chain *c, const char *s, size_t len, svf_extent *e);
svf_err svf_draw_utf8(const svf_chain *c, const char *s, size_t len, int16_t x, int16_t y_baseline,
                      svf_target *t, uint8_t *scratch, size_t scratch_len);
```
Rules (spec "Line drawing", engine-derived, mirrored in `svfline.py`): first face in the chain with `svf_has`; glyph cell
top = `y_baseline - ascent + dy`; advance = metrics advance (syllables: JSET advance or cell width; no metrics table:
cell width); marks advance 0 and draw at `anchorX - originX` (originX = `min(-bearing_x, cell_w)` if flag bit 2 and
`bearing_x < 0`, else 0; anchorX = pen of the previous non-mark glyph, or the current pen if first); missing glyph:
nothing drawn, advance `missing_advance`; invalid UTF-8 (overlong, surrogate, > U+10FFFF, truncated) → U+FFFD if the
chain has it, else skipped. GRAY8 writes `max(existing, coverage)` per pixel.

`svfline.py` API: `layout(chain_paths, text, x, y_baseline, w, h, is_mark=default) -> bytearray(w*h)` (GRAY8) and
`measure(...) -> (width, ascent, descent)`, built on `jamoset.parse_svfn/compose`. `svfdump line W H X Y TEXT FACE...`
writes the GRAY8 buffer.

- [ ] **Step 1: Failing tests** `TestLine`:
  - `test_lines_match_reference` — samples × chains:
    - texts: `"다람쥐 헌 쳇바퀴에 타고파"`, `"Score: 120 점"`, `"뷁쌓읽 ㄱㄴㅎ ㅏ"`, `"Áè"`, `""`;
    - chains: `[PAPLG16, PAPLG18]`, `[MARUS24]` (dy face), `[svf/iolo first 16 px face]`, `[synth marks face, PAPLG18]`.
  - `test_chain_baseline_paplg` — PAPLG16 'A' and PAPLG18 '가' share the baseline row: the bottom ink row of 'A' (no
    descender) and the reference's baseline agree.
  - `test_utf8_invalid` — bytes `b"\xff\xc0\xafA\xed\xa0\x80\xf4\x90\x80\x80\xe1\x80"` match the reference and never read
    past `len` (ASan).
  - `test_measure_matches` — `svf_measure_utf8` equals `svfline.measure` for every sample.
- [ ] **Step 2: Run** `-k TestLine` → FAIL.
- [ ] **Step 3: Implement** `svfline.py` (reference) then `svf_draw.c`; `svf_synth.py --marks` writes a 16 px 1 bpp face
  with flag bit 2, glyphs A, e, U+0301 and U+0300 with negative bearings.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `c: UTF-8 line layout over a face chain (matches tools/svfline.py)`.

### Task 5: Display targets and clipping

**Files:** Modify `svf_draw.c`, `svf.h`, `svfdump.c`, `tools/svfline.py`, `tools/test_c_renderer.py`.

**Interfaces — Consumes:** Task 4 targets. Conversion rules (also in `svfline.to_target`):
- MONO_PAGE (SSD1306): byte `buf[(y>>3)*stride + x]`, bit `y&7`, set if `cov >= mono_threshold` (default 128), never cleared.
- MONO_ROW: byte `buf[y*stride + (x>>3)]`, bit `7-(x&7)`, same threshold rule.
- RGB565: pixel = blend(bg, fg, cov) per channel `(c_bg*(255-cov) + c_fg*cov + 127)/255` in 5/6/5 space, written only where `cov > 0`; byte order by flag.
- COVERAGE_CB: `plot(ctx, x, y, cov)` for each `cov > 0`, row-major order.
- All kinds: only pixels inside the clip rectangle are touched.

- [ ] **Step 1: Failing tests** `TestTargets::test_targets_match_reference` (each kind × the Task 4 samples, target
  128×64 and 100×37 to hit odd strides) and `test_clip_edges` (draw at x = -7, y_baseline = 3, and x = w-5; clip rect
  inset by 3; ASan; buffer guard bytes around `buf` stay 0xA5) and `test_bad_targets` (clip rect outside the target,
  stride below the row bytes, w or h <= 0, buf_len one byte short, 320x240 RGB565 so 16-bit address math would
  overflow → `SVF_E_ARG` or correct clipped output, never a write outside `buf`).
- [ ] **Step 2: Run** `-k TestTargets` → FAIL.
- [ ] **Step 3: Implement** the four target writers behind one per-pixel dispatch; keep GRAY8/MONO as tight loops.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `c: mono page/row, RGB565 and callback targets with clipping`.

### Task 6: Scaling

**Files:** Create `c/src/svf_scale.c` (so a build without scaling leaves it out); modify `svf_draw.c`, `svf.h`,
`tools/svfline.py`, `tools/test_c_renderer.py`.

**Interfaces — Produces:** `svf_chain` gains `uint8_t scale_num, scale_den;` (0/0 treated as 1/1). Whole multiples
(`num % den == 0`): each source pixel → N×N block; advances, ascent and dy scaled by N. Other ratios: output pixel
(ox, oy) covers source area `[ox*den/num, (ox+1)*den/num)` per axis; coverage = area-weighted mean of source coverage,
computed in fixed point (16.16), rounded half up; advances `(adv*num + den/2)/den`. Needs `scratch_len >=
2*svf_cell_bytes` + the scaled cell in GRAY8 (`ceil(w*num/den)*ceil(h*num/den)`); `svf_draw_utf8` returns `SVF_E_NOMEM`
otherwise. The ratio is reduced by gcd; num, den in 1..16 (`SVF_E_ARG` otherwise); every size product is computed in
uint32 and checked. Non-integer ratios: ascent, dy and pen x scale as `(v*num + den/2)/den` (round half up, negative
values symmetric), the baseline row is the scaled ascent.

- [ ] **Step 1: Failing tests** `TestScale::test_scaled_lines_match_reference` (ratios 2/1, 3/1, 3/2, 5/4 on the Task 4
  samples, GRAY8 and MONO_PAGE), `test_scratch_too_small` and `test_bad_ratio` (0/1, 17/1, 1/17 → `SVF_E_ARG`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** in `svfline.py` (reference) and `svf_draw.c`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `c: integer and area-averaged scaling`.

### Task 7: Composed-syllable cache and no-malloc/sanitizer gate

**Files:** Modify `svf_draw.c`, `svf.h`, `c/check.sh`, `tools/test_c_renderer.py`; propose the gate line.

**Interfaces — Produces:** `svf_err svf_chain_cache(svf_chain *c, uint8_t *buf, size_t len);` — N slots of
`8 + max cell bytes` (u32 cp, u8 face index, 3 bytes pad) keyed by (face index, cp), round-robin replacement; `len = 0` disables. Output identical with or
without the cache.

- [ ] **Step 1: Failing test** `TestCache::test_cache_transparent` (Task 4 and 5 samples drawn with caches of 0, 1, 7
  and 64 slots → identical buffers; with a stream face, `svf_stream_reads` drops when the cache is on).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; extend `c/check.sh` to also build the whole test set with `-fsanitize=address,undefined`
  and run `tools/test_c_renderer.py` against that build (`SVF_ASAN=1`).
- [ ] **Step 4: Run** `make -C c check` → `no-malloc: OK`, `asan: OK`.
- [ ] **Step 5: Commit** `c: optional composed-syllable cache; check.sh runs the sanitizer build`; write in the card
  handoff the proposed gate addition for `[project.svf-fonts]`: `["make", "-C", "c", "check"]` (operator applies).

### Task 8: Spec fixes in `spec/SVF.md`

**Files:** Modify `spec/SVF.md`.

- [ ] **Step 1:** Document flag bit 2 (marks at origin) with the rule from Task 4; state bytes 9 (shadow) and 10-11 (code
  page) are not read by current readers; define "cell" as the stored glyph box (the engine's two-cell buffer is its own
  notion); move `[load]`/`[preload]` sections under a "ScummVM loading (appendix)" heading; point to `c/include/svf.h`.
- [ ] **Step 2: Verify** `python3 -m unittest discover -s tools` still passes (doc-only) and `git diff --check`.
- [ ] **Step 3: Commit** `spec: flag bit 2, unused header fields, cell, ScummVM appendix`.

### Task 9: Cross toolchains, cross builds and code size

**Files:** Create `c/cross/install-toolchains.sh`, `c/cross/build-all.sh`, `c/cross/SIZES.md`.

- [ ] **Step 1:** `install-toolchains.sh` installs into `~/opt` (user space, no sudo): arm-none-eabi-gcc (Arm GNU
  Toolchain tarball), avr-gcc (+ avr-libc), emsdk (emscripten), riscv32-esp-elf or xtensa-esp32-elf gcc (Espressif
  tarball). Each step skips if present; prints versions.
- [ ] **Step 2:** `build-all.sh` builds `c/src/*.c` with each toolchain: host gcc, clang, DJGPP (`i586-pc-msdosdjgpp-gcc`),
  `arm-none-eabi-gcc -mcpu=cortex-m0plus -mthumb -Os`, `avr-gcc -mmcu=atmega328p -Os`, `emcc -O2`, ESP gcc `-Os`; all
  with `-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections`. Size = `size` of a link with `--gc-sections` for each profile:
  P1 Uno: mapped face, 1 bpp, jamo, MONO_PAGE, no stream/scale/cache; P2 M0+ OLED: as P1 plus 2 bpp; P3 TFT: mapped,
  2 bpp, jamo, RGB565, syllable cache; P4 full: everything (DOS/WASM). The 8 KB budget applies to P1 and P2 on Cortex-M0+.
- [ ] **Step 3: Run** `c/cross/build-all.sh` → every toolchain `OK`; Cortex-M0+ P1 and P2 text ≤ 8192 bytes. Write the table
  (toolchain, version, text/data/bss) to `SIZES.md`. Over budget → record it as a finding in `SIZES.md` and the handoff;
  do not change the budget.
- [ ] **Step 4: Commit** `c: cross builds for DJGPP, Cortex-M0+, AVR, ESP32, WASM; sizes`.

### Task 10: Emulated speed measurements

**Files:** Create `c/bench/bench.c`, `c/bench/run-*.sh`, `c/bench/MEASUREMENTS.md`.

- [ ] **Step 1:** `bench.c`: composes+draws one 16 px syllable N times and a 32-glyph 128×64 MONO_PAGE screen N times;
  reports cycles (DWT/SysTick on M0+ emulation where the emulator counts them, `rdtsc`/`uclock` on DOS, `performance.now`
  in node for WASM).
- [ ] **Step 2: Run** on: QEMU or rp2040js for Pico (125 MHz), simavr for ATmega328P (16 MHz; Uno fit = links with one
  ~13 KB 1 bpp jamo face in PROGMEM and draws), DOSBox-X at a 486 cycle setting (40-char PAPLG16+18 line, mapped and
  streamed from a file), node for WASM. Every row labelled `emulated` with emulator, version, clock, compiler.
- [ ] **Step 3:** Compare with the budgets; misses go in `MEASUREMENTS.md` as findings with the measured number.
- [ ] **Step 4: Commit** `c: emulated speed measurements against the design budgets`.

### Task 11: Port examples

**Files:** Create `c/ports/{dos,pico,esp32,arduino,web}/` (each a README + one source file + build line).

- [ ] **Step 1:** dos: DJGPP program drawing a PAPLG16+18 line in VGA mode 13h from files (streamed). pico: SSD1306 over
  I2C (pico-sdk CMake) with a mapped face in flash. esp32: ILI9341 over SPI (ESP-IDF) with RGB565. arduino: Uno +
  SSD1306, face in PROGMEM through `-DSVF_RD8(p)=pgm_read_byte(p)` (Task 1 macros). web: emscripten glue exporting
  open/draw to a GRAY8 buffer (the page is card t_fe9f6c30).
- [ ] **Step 2: Verify** each builds with `c/cross/build-all.sh --ports`; the dos example runs in DOSBox-X and a screenshot
  is stored as `c/ports/dos/screenshot.png`.
- [ ] **Step 3: Commit** `c: port examples (DOS, Pico, ESP32, Arduino, web glue)`.
