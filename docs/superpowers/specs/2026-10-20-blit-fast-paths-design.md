# Blit fast paths for the C SVF renderer: design

Card t_b5256c18, 2026-10-20. Follow-up of t_78219730 (`spec/renderer-design.md`, `c/bench/MEASUREMENTS.md`).
Plan: `docs/superpowers/plans/2026-10-20-blit-fast-paths.md`.

## Why

Three of four speed budgets are missed (emulated, 2026-10-19): Pico 125 MHz 113/126 µs a 16 px syllable at `-Os`
(budget 50), 3.63 ms a 128 x 64 MONO_PAGE screen (budget 2), DOS 486DX2-66 23.0 ms a 40-char GRAY8 line (budget 16).
The profile puts 69 % of a Pico syllable in `blit` (`c/src/svf_draw.c`): one `svf__coverage` call and a 1/2/8 bpp test
per pixel, 39 cycles a pixel; the budget needs about 7. On DOS the same loop (GRAY8, 2 bpp) is 62 % of a line.

## What changes, what does not

Only `blit` and what it calls change. The walker (decode, chain, metrics, marks, dy, pen), `svf_glyph`/`svf_compose`,
the syllable cache, `svf_scale.c` and every public declaration stay as they are. Output stays byte-identical to
`tools/svfline.py` and `tools/jamoset.py` on every target kind, clip, offset and ratio: the existing tests and the new
sweeps of the plan are the oracle. No malloc, no static data, no header beyond the three allowed, `-Werror` everywhere.

## The paths

`blit(t, r, cv, x, y)` keeps its contract: a `cellview` (pixels, w, h, pitch, bpp 1/2/8) with its top-left at (x, y),
cut to the clip `r`. It still computes the cell's visible columns `c0..c1` and rows `r0..r1` once; what follows the cut
is one dedicated loop per (target kind, source bpp), chosen once per cell, never per pixel:

| target \ source | 1 bpp | 2 bpp | 8 bpp (incl. every scaled cell) |
|---|---|---|---|
| MONO_PAGE | 8 x 8 bit transpose of 8 glyph rows into 8 page bytes | pack 8 pixels to one mono byte at the threshold, then the 1 bpp transpose | the same pack, 8 compares |
| MONO_ROW | source byte shifted by `x & 7` into two target bytes, OR | pack, then the 1 bpp row path | pack, then the 1 bpp row path |
| GRAY8 | per source byte: skip 0, else store 255 at each set bit | per source byte: skip 0, else 4 pixels through a 4-entry level table, max | per pixel max, no call |
| RGB565 | per set bit store the fg pair | per source byte: skip 0, else 4 pixels through a 4-entry colour-pair table | per pixel `blend565` (the spec's no-fast-path case; scaled TFT text is rare) |
| COVERAGE_CB | the generic per-pixel loop as today (`svf__coverage`; the callback dominates) | same | same |

- **Empty bytes.** Every 1 and 2 bpp path tests a whole source byte (or, in the page path, the OR of its 8 gathered
  bytes) for 0 and skips it: most of a glyph's bytes are blank.
- **Thresholds.** At 1 bpp ink is 255, at or above any threshold (0 counts as 1), so the 1 bpp mono paths never read
  the threshold; `svfline.to_target` agrees. At 2 bpp the threshold becomes once per cell a least level
  `ceil(thr / 85)` (1..3); at 8 bpp a byte compare. `pack8(cv, row, i, least)` turns pixels `8i..8i+7` of a row into
  one MSB-first byte for 2 and 8 bpp only (ruling, Task 3): 1 bpp rows are read directly as bytes through `mono_src`,
  never through `pack8`; the bpp test is per 8 pixels, outside the bit loop.
- **MONO_PAGE.** For each page `p` from `(y + r0) >> 3` to `(y + r1 - 1) >> 3`, and each source byte column `i`:
  gather `b[k]` = the byte of cell row `8p + k - y` (0 when that row is outside `r0..r1`), skip if all 0, transpose
  (two `uint32` words, three swap stages; rows gathered so that bit `k` of output column `c` is row `k`'s bit `7 - c`),
  then OR output columns into `buf[p * stride + x + 8i + c]`. Columns outside `c0..c1` are never stored (the first and
  last source byte column store column by column; the ones between store all 8): no byte of a pixel outside the
  clip is touched, so a 100-wide target with stride 103 and ASan guards stay clean, as today.
- **MONO_ROW.** With `s = x & 7` (x reduced to 0..7 for a negative x; `q` the floor byte offset), target byte `B`
  from `(x + c0) >> 3` to `(x + c1 - 1) >> 3` receives `src[B - q - 1] << (8 - s) | src[B - q] >> s` (bytes outside the
  row read as 0; `s == 0` is a plain copy), masked at the first and last byte to the columns inside `c0..c1`, OR-ed
  when not 0. Bits past the cell width are already 0 (`svf__mask_cell`; a packed row pads with 0).
- **GRAY8, RGB565.** One row loop per bpp. The RGB565 colour pairs (fg at 1 bpp; levels 1..3 at 2 bpp) are built
  once per cell in the target's byte order, so the endianness flag is not tested per pixel either.

## How clipping, dy, marks and scaling feed the paths

They do not know about them. The walker places a cell at `(x, y)` with dy and the mark origin already applied, and
`blit` cuts it to `c0..c1`, `r0..r1` exactly as now; every path takes that rectangle and writes nothing outside it.
A scaled cell arrives as an 8 bpp GRAY8 `cellview` (as today) and takes the 8 bpp paths, so `svf_scale.c` is untouched
and a build with `SVF_NO_SCALE` loses nothing. Overlapping cells (a mark over its base) keep their order and rules:
GRAY8 max, mono OR, RGB565 the later cell, the callback one call a cell pixel.

## Rulings that changed the design (recorded after implementation)

- **No static level table.** The 4-entry level/colour-pair tables are built on the stack per cell, not kept as static
  data: `c/src` has no static data (`size`: data 0, bss 0; checked by `c/check.sh`).
- **`pack8` serves 2 and 8 bpp only.** A 1 bpp source is read directly through `mono_src`; `pack8` over a 1 bpp
  face would over-read, so it is static and documented as 2/8 bpp.
- **MONO_PAGE stores each column byte separately** (an OR per output column, columns outside `c0..c1` never stored),
  not a word store, so no byte outside the clip is touched.
- **`SVF_TARGETS` in the port builds.** The ports are built with the flag of the output they use: Pico 0x02, ESP32 0x08,
  Arduino 0x02 (in `c/ports/*` build files and READMEs and in `build-all.sh --ports`); the Arduino port is 26438 B of flash.
- **Decided (user, 2026-10-21):** the all-targets P1 (P1*) was 7094 B on Cortex-M0+ (1098 B spare) when this was
  written; with the VESA kinds it is 8474 B, 282 B over 8192. The gate stays on P1/P2 (5674 B) and the overshoot is
  accepted: small targets choose their kinds through `SVF_TARGETS`.

## Code size (budget: Cortex-M0+ `-Os`, P1/P2 text <= 8192 B; 5718 before this work, 5674 after)

The kind and the bpp are run-time values, so `--gc-sections` cannot drop a path: every path is linked into every
build (as the one `blit` is today). The new loops are small (an estimated 60-150 B each in Thumb, about 10 loops),
but the estimate is not the gate: the plan measures with `c/cross/build-all.sh` after every path task. Two
safeguards, in order:

1. `pack8` + shared mono paths and the per-cell tables keep the count of loops at ten; nothing is unrolled.
2. A compile switch `SVF_TARGETS` (a mask of the five kinds, default all): a kind left out compiles no path and
   `svf_target_init`/`svf_draw_utf8` refuse it with `SVF_E_ARG`. This matches the budget's own words ("core plus one
   output path"): `build-all.sh` builds P1/P2 with MONO_PAGE only and P3 with RGB565 only, and adds a row "P1, all
   targets" so both numbers are on record; the 8192 gate applies to the one-output-path rows. The default build
   (tests, DOS, WASM) has every kind. **Decision for the user:** if the all-targets P1 also fits, the switch is still
   added (it is cheap and it is what a Uno build wants), but the gate could be kept on the all-targets row instead.

No bpp switch: P2 (1 + 2 bpp) must be the same link as P1, as today.

## What counts as done

- `tools/test_c_renderer.py` (new `TestBlitPaths` sweeps included) and `make -C c check` green (no-malloc, ASan/UBSan).
- `c/cross/build-all.sh`: every toolchain OK; Cortex-M0+ P1/P2 text <= 8192 B; `c/cross/SIZES.md` updated.
- `c/bench/run-pico.sh`, `run-dos.sh`, `run-avr.sh`, `run-wasm.sh` re-run; `c/bench/MEASUREMENTS.md` carries a
  before/after table per budget (the 2026-10-19 numbers kept as "before"), every number labelled emulated.
- A list of platforms still over budget with their numbers, in MEASUREMENTS.md and the card handoff; each becomes its
  own card (Pico interpolator/PIO/DMA, ESP32 DMA, DOS 32-bit/mode 13h, AVR PROGMEM page path are out of scope here).

Expected, not promised (from the profile): a Pico syllable at `-Os` from ~14,100 to ~5,500-6,500 cycles (44-52 µs:
the 50 µs budget is on the edge; composing alone is 3,600), a screen from 3.63 to ~1.5-1.8 ms; DOS from 23.0 to
~12-15 ms. The WASM budget stays met; the Uno has no speed budget and gets faster for free.
