# Blit Fast Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-pixel `blit` of `c/src/svf_draw.c` with dedicated loops per (target kind, source bpp) so the
Pico, screen and DOS speed budgets come within reach, with output byte-identical to `tools/svfline.py`, the
no-malloc/ASan gate green and Cortex-M0+ P1/P2 text <= 8192 B; then re-measure every platform.

**Architecture:** `blit` keeps its contract (a `cellview` at (x, y) cut to the clip rectangle) and becomes a
dispatcher: the cut is computed once, then one loop per (kind, bpp) runs over whole source bytes. The mono targets share
a `pack8` that turns 8 pixels of 2 or 8 bpp into one 1 bpp byte (1 bpp bytes are read directly; ruling in Task 3) at the threshold, so MONO_PAGE (8 x 8 transpose into page
bytes) and MONO_ROW (shifted byte OR) are written once. The walker, composition, cache and scaling are untouched; a
scaled cell is an 8 bpp cell and takes the 8 bpp loops. A compile switch `SVF_TARGETS` leaves unused kinds out of a
size-constrained build. Every path is proven by sweeps against `svfline` before it is written (the oracle exists; the
tests pass on the old `blit` and must keep passing), and by the emulated cycle counts after.

**Tech Stack:** C99 (`-std=c99 -Wall -Wextra -Werror`), make; Python 3 unittest (`tools/test_c_renderer.py`); cross
toolchains and emulators already installed under `~/opt` (`c/cross/install-toolchains.sh`, `c/bench/install-emulators.sh`).

**Spec:** `docs/superpowers/specs/2026-10-20-blit-fast-paths-design.md` (read it first). Budgets and constraints:
`spec/renderer-design.md`. Target rules: `c/include/svf.h` ("A drawing target"). Reference: `tools/svfline.py`
(`draw_target`, `to_target`, `Target.put`, `scale_coverage`). Numbers to beat: `c/bench/MEASUREMENTS.md`.

## Global Constraints

- Only `c/src/svf_draw.c` (the targets section), `c/include/svf.h` (the `SVF_TARGETS` switch and its doc), `c/tests/svfdump.c`
  (if a test needs an option), `tools/test_c_renderer.py`, `c/cross/build-all.sh`, `c/cross/SIZES.md`,
  `c/bench/MEASUREMENTS.md` change. Fix rounds added: `c/check.sh`, `c/tests/test_args.c`, `c/Makefile` (test-args-page),
  the port build files (`c/ports/*/CMakeLists.txt`, `c/ports/*/README.md`) and the spec and plan records. No change to `svf_scale.c`, `svf_jamo.c`, `svf_face.c`, `svf_stream.c`, `svfline.py`.
- C99; headers `<stdint.h>`, `<stddef.h>`, `<string.h>` only; no static data (`size`: data 0, bss 0 for every object); no
  allocator symbol (`c/check.sh`); no lookup table larger than 4 entries built on the stack per cell; no unrolling.
- Output byte-identical to `svfline` on every kind, clip, offset, threshold, byte order and ratio: `tools/test_c_renderer.py`
  must be green after every task (`SVF_ASAN=1` included via `make -C c check`), never "temporarily red".
- No pixel or byte outside the clip is written (ASan guards, `TARGET_FILL` bytes and stride padding are compared).
- Cortex-M0+ `-Os` P1/P2 text <= 8192 B after every task (`c/cross/build-all.sh`), not only at the end.
- Every measurement labelled emulated with emulator, clock and compiler, as in MEASUREMENTS.md; a missed budget is
  recorded with its number, never argued away.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Clip edges inside a source byte: a cell cut at columns that are not multiples of 8 (x = -7, -1, clip x0 = 9,
   x1 = w - 9) must mask, not store, the columns outside — Task 1 `test_clip_at_byte_edges`, Tasks 3-4 under ASan with
   stride w + 3.
2. The MONO_ROW shift with a negative x (x = -5: `s = 3`, byte offset `-1`) must read no source byte before the row and
   write no target byte before `(x + c0) >> 3` — Task 3 `test_mono_every_phase` x in -9..15.
3. The MONO_PAGE page gather at the top of a cell (y_baseline such that the cell starts at target row 3: page 0 holds
   rows 3..7 of the cell only) and at the last partial page of a 37-row target (5 rows) — Task 4, y_baseline 0..15 on
   100 x 37.
4. 2 bpp thresholds: `least = ceil(thr / 85)` with thr 0 counted as 1 (`0 -> 1`, `1..85 -> 1`, `86..170 -> 2`,
   `171..255 -> 3`); threshold 255 must set level 3 only — Task 3 `test_mono_every_phase` thresholds (0, 1, 85, 86, 128,
   170, 171, 255).
5. A scaled cell (8 bpp, width not a multiple of 8, e.g. 16 * 3/2 = 24, 19 * 5/4 = 24, 14 * 3/2 = 21) on a mono target
   must take the pack path with the same bits as `svfline` — Task 1 `test_scaled_cells_every_kind`.

---

## File structure

```
c/src/svf_draw.c           blit dispatcher; pack8, transpose8; one loop per (kind, bpp); SVF_TARGETS guards
c/include/svf.h            SVF_TARGETS mask (SVF_TARGET_GRAY8 .. SVF_TARGET_CB) and its doc under "A drawing target"
tools/test_c_renderer.py   TargetMixin (factored from TestTargets), new class TestBlitPaths, TestTargetsSwitch
c/cross/build-all.sh       P1/P2 built with -DSVF_TARGETS=SVF_TARGET_MONO_PAGE, P3 with RGB565, extra row P1 all targets
c/cross/SIZES.md           re-measured table and findings
c/bench/MEASUREMENTS.md    before/after per budget, platforms still over budget
```

Faces the sweeps use (cell widths not multiples of 8, from `svf/dos`): `SMYJO18.SVF` (19 x 18, 1 bpp, pitch 3, 5
padding bits), `NEODG16D.SVF` (22 x 22, 1 bpp), `NGOTB14.SVF` (14 x 14, 2 bpp), `GBA17BX1.SVF` (26 x 24, 2 bpp); plus
`MARUS24.SVF` (dy), `PAPLG16 + PAPLG18` (the DOS line), the `--marks` synthetic face and the `--bpp8` synthetic face
(`svf_synth.py --bpp8 --from SYNTH_BASE`, 8 bpp without scaling).

---

### Task 1: The oracle first: byte-identity sweeps over every phase, edge, bpp and ratio

**Files:** Modify `tools/test_c_renderer.py` only.

**Interfaces — Produces:** `TargetMixin` with the methods now on `TestTargets` (`opts_of`, `draw`, `target`, `expect`,
`check`; `TestTargets` keeps its tests and inherits it) and:

```python
ODD_FACES = (SMYJO18, NEODG16D, NGOTB14, GBA17BX1)          # 19, 22 (1 bpp), 14, 26 (2 bpp) pixel cells
PHASE_X = tuple(range(-9, 16))                              # every x & 7 twice, negative included
PHASE_Y = tuple(range(0, 16))                               # every page phase of a cell top (y_baseline - ascent + dy)
THRESHOLDS = (0, 1, 85, 86, 128, 170, 171, 255)
class TestBlitPaths(TargetMixin, unittest.TestCase)
```

Every test asserts, through `check`, `out == svfline.draw_target(...)` and `out == svfline.to_target(draw_gray8(...))`
(bytes, whole buffer, `TARGET_FILL` pre-filled, stride = row bytes + 3 on the 100 x 37 target), no `Sanitizer`,
`runtime error` or `guard bytes changed` on stderr.

- [ ] **Step 1: Write the tests** (they are expected to PASS on the current `blit`: the oracle is being pinned before the
  rewrite):
  - `test_mono_every_phase`: kinds `mono-page`, `mono-row`; chains `[f]` for f in `ODD_FACES + (MARUS24, bpp8)`, text
    `"W#가각 Qy"`; target 100 x 37 stride + 3; x in `PHASE_X` at y_baseline 20, and y_baseline in `PHASE_Y` at x 3;
    threshold 128 for 1 bpp faces, every `THRESHOLDS` value for the 2 bpp and 8 bpp faces (at x 3, y 20 only, to bound
    the count). Also asserts, for a 2 bpp face, that the set-bit count is non-increasing over `THRESHOLDS` and equal
    for thresholds 0 and 1 (the `0 -> 1` rule).
  - `test_clip_at_byte_edges`: kinds `mono-page`, `mono-row`, `gray8`, `rgb565`; chain `[SMYJO18]` and
    `[PAPLG16, PAPLG18]`; target 100 x 37; clip `(x0, y0, x1, y1)` for x0 in `(0, 1, 7, 8, 9, 15, 16)`, x1 in
    `(w, w - 1, w - 7, w - 8, w - 9)`, with (y0, y1) = (3, h - 3), and y0 in `(0, 1, 7, 8, 9)`, y1 in `(h, h - 1, h - 5,
    h - 8)` with (x0, x1) = (3, w - 3); the line at x = -7 and at x = w - 20, y_baseline 20. Asserts in addition that
    every byte of a `gray8` buffer outside the clip is `TARGET_FILL`.
  - `test_scaled_cells_every_kind`: `--scale=` 2/1, 3/2, 5/4, 1/2 on kinds `gray8`, `mono-page`, `mono-row`, `rgb565`,
    `cb`; chains `[NGOTB14]`, `[SMYJO18]`, `[PAPLG16, PAPLG18]`; x in `(-3, 0, 5, 8, 13)`, y_baseline 30 on 128 x 64;
    thresholds 128 and 200 for the mono kinds.
  - `test_overlap_every_kind`: chain `[marks, PAPLG18]`, text `"Áè 가́"`, every kind, x in `(0, 1, 7, 8)`,
    y_baseline 20, 128 x 64, RGB565 with fg 0x1234 bg 0xABCD both byte orders (the later cell wins; cb once a cell pixel:
    `check` already asserts this).
  - `test_wide_cell_on_small_target`: chain `[svf/dos/NEODG32A.SVF]` (46 x 54, 1 bpp) on 32 x 20 `mono-page` and
    `mono-row`, x in `(-40, -8, -1, 0, 20)`, y_baseline in `(-10, 5, 19, 60)` (cells wider and taller than the target;
    cells wholly outside draw nothing).
- [ ] **Step 2: Run** `python3 -m unittest tools.test_c_renderer -k TestBlitPaths -k TestTargets` -> PASS (the current
  code is the baseline). Then a one-off mutation check, not committed: in `blit` change `0x80u >> (px & 7)` to
  `0x40u >> (px & 7)` (MONO_ROW) and run `-k test_mono_every_phase` -> FAIL; revert; change the MONO_PAGE `(py >> 3)` to
  `((py + 1) >> 3)` -> FAIL; revert. Record both failures in the commit message.
- [ ] **Step 3: Run** `make -C c check` -> `no-malloc: OK`, `asan: OK`; note the wall time of `TestBlitPaths` (keep the
  whole file under 10 minutes on the host: trim `PHASE_X` to `range(-9, 16, 1)` only where noted, never the edges).
- [ ] **Step 4: Commit** `c tests: blit sweeps over every phase, byte edge, bpp, threshold and ratio (oracle for the fast paths)`.

### Task 2: Dispatcher, GRAY8 and RGB565 loops per bpp, generic callback

**Files:** Modify `c/src/svf_draw.c`.

**Interfaces — Consumes:** `cellview`, `rect`, `blend565`. **Produces (all `static` in svf_draw.c):**
```c
typedef struct { int32_t c0, c1, r0, r1; } cut;           /* the cell's visible columns and rows */
static int cut_cell(const rect *r, const cellview *cv, int32_t x, int32_t y, cut *k);  /* 0 when nothing is visible */
static void blit_gray8(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
static void blit_rgb565(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
static void blit_cb(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
static void blit(const svf_target *t, const rect *r, const cellview *cv, int32_t x, int32_t y);  /* the dispatcher */
```
`blit_gray8`: `switch (cv->bpp)` once, then a row loop per case: 1 bpp per source byte (skip 0; for each set bit store
255: `max(existing, 255)` is 255), 2 bpp per source byte (skip 0; four pixels through `uint8_t lvl[4] = {0, 85, 170, 255}`,
store when `v > dst`), 8 bpp per pixel `if (v > dst) dst = v`. `blit_rgb565`: the colour pairs (`uint8_t pair[4][2]`,
fg at index 3 for 1 bpp, levels 1..3 at 2 bpp) built once per cell in the target's byte order; 1 bpp per set bit store
two bytes; 2 bpp per source byte skip 0 then four pixels; 8 bpp per pixel `blend565` when `v > 0` (as today). `blit_cb`
is the current per-pixel loop. MONO_PAGE and MONO_ROW stay on the current per-pixel code for now (moved into
`blit_mono_page` / `blit_mono_row` with the same bodies; Tasks 3-4 replace them).

- [ ] **Step 1: The failing measurement**: `c/bench/run-pico.sh` (needs `~/opt`); record `syl_ga -Os` cycles
  (expected 14126 as in MEASUREMENTS.md) and `c/bench/run-dos.sh` `line40_mapped` (23030 µs). These are the numbers
  the task must move; the identity tests of Task 1 are the gate.
- [ ] **Step 2: Implement** the dispatcher and the three loops above; `blit` becomes `if (!cut_cell(...)) return;
  switch (t->kind) {...}`; `svf__coverage` remains only in `blit_cb` (and in the mono bodies until Tasks 3-4).
- [ ] **Step 3: Run** `python3 -m unittest tools.test_c_renderer` -> PASS (every class); `make -C c check` -> OK;
  `c/cross/build-all.sh` -> every toolchain OK, Cortex-M0+ P1 and P2 text <= 8192 (record the number).
- [ ] **Step 4: Run** `c/bench/run-dos.sh` -> `line40_mapped` below 23030 µs (record; the 2 bpp GRAY8 loop is the DOS
  line's hot path); `c/bench/run-pico.sh` unchanged within noise (the Pico draws MONO_PAGE, still per-pixel here).
- [ ] **Step 5: Commit** `c: blit dispatch per target kind and bpp; GRAY8 and RGB565 byte-wise loops (DOS line40 X -> Y ms)`.

### Task 3: pack8 and the MONO_ROW shifted-OR path

**Files:** Modify `c/src/svf_draw.c`.

**Interfaces — Produces:**
```c
/* The least 2 bpp level at or above the threshold: 1..3 (thr 0 counts as 1). */
static uint8_t least_level(uint8_t thr);                   /* (thr ? thr : 1) + 84) / 85 */
/* Pixels 8i..8i+7 of a row as one MSB-first byte: 1 bpp the byte, 2 bpp level >= least, 8 bpp byte >= thr;
 * pixels past the row's width are 0. */
static uint8_t pack8(const cellview *cv, const uint8_t *row, int32_t i, uint8_t least, uint8_t thr);
static void blit_mono_row(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
```
`blit_mono_row`, per row: `s = x & 7` computed as `((x % 8) + 8) % 8`, `q = (x - s) / 8` (floor; `x = 8q + s`);
target bytes `B` from `(x + k->c0) >> 3` to `(x + k->c1 - 1) >> 3` (both >= 0); `v = (src(B - q - 1) << (8 - s) |
src(B - q) >> s)` where `src(j)` is `pack8(cv, row, j, ...)` for `0 <= j < ceil(cv->w / 8)` and 0 otherwise (1 bpp:
the byte itself; when `s == 0` only `src(B - q)`); mask the first byte to columns `>= x + c0` and the last to columns
`< x + c1` (`0xFF >> ((x + c0) & 7)` and `0xFF << (7 - ((x + c1 - 1) & 7))`); `if (v) dst[B] |= v`. For bpp 1, `pack8`
is skipped (direct byte load); for bpp 2 and 8 the branch is per 8 pixels, outside any bit loop.

- [ ] **Step 1: The gate**: no bench case draws MONO_ROW, and none is added. This task is held by Task 1's
  `test_mono_every_phase` (every x & 7, negative x, odd widths, every threshold) and `test_clip_at_byte_edges`; run
  them now (PASS on the Task 2 code) so a later failure is this task's.
- [ ] **Step 2: Implement** `least_level`, `pack8`, `blit_mono_row`.
- [ ] **Step 3: Run** `python3 -m unittest tools.test_c_renderer -k TestBlitPaths -k TestTargets -k TestScale -k TestCache`
  -> PASS; then the whole file and `make -C c check` -> OK; `c/cross/build-all.sh` -> P1/P2 <= 8192 (record).
- [ ] **Step 4: Spot measurement** (recorded in the commit message, not in MEASUREMENTS.md): the host bench
  `screen32` time with `SVF_T_MONO_ROW` substituted for `SVF_T_MONO_PAGE` in a scratch copy of bench.c is lower than
  with the Task 2 code; a one-line note is enough.
- [ ] **Step 5: Commit** `c: MONO_ROW by shifted byte ORs; pack8 folds 2 and 8 bpp into the 1 bpp mono paths`.

### Task 4: The MONO_PAGE 8 x 8 transpose path

**Files:** Modify `c/src/svf_draw.c`.

**Interfaces — Produces:**
```c
/* out[c] bit k = b[k] bit (7 - c): 8 glyph-row bytes to 8 page-column bytes (two uint32 words, three swap stages). */
static void transpose8(const uint8_t b[8], uint8_t out[8]);
static void blit_mono_page(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
```
`blit_mono_page`: for each page `p` from `(y + k->r0) >> 3` to `(y + k->r1 - 1) >> 3` and each source byte column `i`
from `k->c0 >> 3` to `(k->c1 - 1) >> 3`: gather `b[bit]` for bit 0..7 as `pack8`/the byte of cell row
`8p + bit - y` when `k->r0 <= row < k->r1`, else 0; if `b[0] | ... | b[7]` is 0 continue; `transpose8`; store
`dst[p * stride + x + 8i + c] |= out[c]` for every c when `8i >= k->c0 && 8i + 8 <= k->c1`, otherwise only for
`c0 <= 8i + c < c1` (and only when `out[c]` is not 0, so no byte is touched needlessly). `transpose8` is the classic
three-stage swap (7, 14, then the 4-bit halves) on `x = b[7]<<24 | b[6]<<16 | b[5]<<8 | b[4]` and `y` of `b[3..0]`
(rows fed in reverse so the output bit is the row index, as the contract says: verify against a plain 64-iteration
loop in a throwaway host program before relying on it; Task 1's `test_mono_page_hand_computed` and
`test_mono_every_phase` then hold it).

- [ ] **Step 1: The failing measurement**: `c/bench/run-pico.sh` -> `syl_ga -Os` cycles (Task 2's number, ~14,100)
  and `screen32` (~453,000): the targets are <= 6,250 and <= 250,000 cycles (the budgets).
- [ ] **Step 2: Implement** `transpose8` and `blit_mono_page`; delete the last mono use of `svf__coverage`.
- [ ] **Step 3: Run** the whole `tools/test_c_renderer.py` -> PASS; `make -C c check` -> OK; `c/cross/build-all.sh`
  -> P1/P2 <= 8192 (record; if over, go to Task 5 before anything else).
- [ ] **Step 4: Run** `c/bench/run-pico.sh` (both `-Os` and `-O2`) and `c/bench/run-avr.sh`; checksums must still
  read `ok` (report.awk fails otherwise). Record cycles; `PROFILE=1 c/bench/run-pico.sh` once to confirm `blit_*`
  is no longer the top symbol.
- [ ] **Step 5: Commit** `c: MONO_PAGE by 8x8 bit transpose of glyph rows into page bytes (Pico syl_ga X -> Y cycles)`.

### Task 5: SVF_TARGETS compile switch and the size gate

**Files:** Modify `c/include/svf.h`, `c/src/svf_draw.c`, `c/cross/build-all.sh`, `c/cross/SIZES.md`,
`tools/test_c_renderer.py`, `c/Makefile` (one target).

**Interfaces — Produces (svf.h, under "A drawing target"):**
```c
#define SVF_TARGET_GRAY8 0x01u
#define SVF_TARGET_MONO_PAGE 0x02u
#define SVF_TARGET_MONO_ROW 0x04u
#define SVF_TARGET_RGB565 0x08u
#define SVF_TARGET_CB 0x10u
#ifndef SVF_TARGETS
#define SVF_TARGETS 0x1Fu   /* the kinds compiled in; a kind left out is SVF_E_ARG at svf_target_init and svf_draw_utf8 */
#endif
```
`target_ok` returns 0 for a kind whose bit is clear; each `blit_*` and the tables it needs are inside
`#if SVF_TARGETS & SVF_TARGET_*`; the dispatcher's `switch` has a case per compiled kind only (a `default:` that
cannot be reached returns). `build-all.sh`: P1 and P2 add `-DSVF_TARGETS=0x02`, P3 `-DSVF_TARGETS=0x08`, P4 none; a
new row `P1*` (P1 with every target, `-DSVF_TARGETS=0x1F`) so both numbers are on record; the 8192 gate stays on P1
and P2. `c/Makefile`: `svfdump-page` builds the ASan svfdump with `-DSVF_TARGETS=0x02` (for the test below).

- [ ] **Step 1: Failing test** `TestTargetsSwitch.test_kind_left_out_is_refused`: with `svfdump-page`, `line` on
  `mono-page` draws the same bytes as the default build for `LINE_TEXTS[0]` on `[PAPLG16, PAPLG18]` at (2, 28), and
  `gray8`, `mono-row`, `rgb565`, `cb` exit 2 with `SVF_E_ARG` and an unchanged (`TARGET_FILL`) buffer.
- [ ] **Step 2: Run** `-k TestTargetsSwitch` -> FAIL (no such make target).
- [ ] **Step 3: Implement** the switch, the Makefile target, the build-all.sh rows; document in svf.h.
- [ ] **Step 4: Run** `-k TestTargetsSwitch` -> PASS; whole file and `make -C c check` -> OK;
  `c/cross/build-all.sh` -> every toolchain OK, P1/P2 <= 8192; paste the table into `SIZES.md` with the date, and a
  finding line per profile: P1 (MONO_PAGE only), P1* (all targets), each against 5718 before. If P1* also fits,
  say so (decided by the user on 2026-10-21: the gate stays on P1/P2; see the design).
- [ ] **Step 5: Commit** `c: SVF_TARGETS leaves unused target kinds out of a build; sizes re-measured`.

### Task 6: Re-measure every platform, record before/after, list what is still over budget

**Files:** Modify `c/bench/MEASUREMENTS.md` (and `c/bench/run-*.sh` only if a script no longer runs as is).

- [ ] **Step 1: Run** `c/bench/run-pico.sh`, `c/bench/run-avr.sh`, `c/bench/run-dos.sh`, `c/bench/run-wasm.sh`
  (each prints its Markdown rows; checksums must read `ok`). Run `c/bench/run-pico.sh` and `run-dos.sh` twice; the
  cycle-counted and PIT-timed numbers must repeat exactly (as noted in MEASUREMENTS.md) or the run is not used.
- [ ] **Step 2: Rewrite** `MEASUREMENTS.md`: the header date and commit; the four result tables replaced; a new table
  under "Against the budgets" with columns `budget | before (2026-10-19) | after | verdict` for the Pico syllable
  (`-Os` and `-O2`), the Pico screen, the DOS line (mapped, mapped + cache, streamed warm, cold; DX2-66 and DX-33), the
  WASM line, the Uno fit (flash bytes before/after: the new code changes the fit); "Findings" rewritten: what the
  blit costs now per pixel (`PROFILE=1` run), what remains (compose, decode) and, as its own list,
  **"Still over budget"**: platform, case, measured, budget, factor, and the follow-up card each needs (Pico:
  interpolator/PIO/DMA display transfer; DOS: 32-bit/mode 13h, or the syllable cache as the recommended default;
  ESP32 DMA and the AVR PROGMEM page path only if measured over). Keep the emulator and provenance sections.
- [ ] **Step 3: Verify** `python3 -m unittest discover -s tools` -> PASS (nothing in the tree depends on the numbers),
  `git diff --check` clean, `c/cross/build-all.sh` and `make -C c check` OK one last time on the final tree.
- [ ] **Step 4: Commit** `c/bench: re-measured after the blit fast paths (before/after per budget; still over: ...)`,
  the "still over" list in the message body; put the same list and the SIZES.md numbers in the card handoff
  (`agentws complete t_b5256c18` with the commit SHAs, test and build-all output as evidence).
