# VESA 2.0 packed output kinds and a DOS VBE 2.0 example: design

Card t_6ab9ec2d, 2026-10-20, revision 4. Follows t_b5256c18 (`docs/superpowers/specs/2026-10-20-blit-fast-paths-design.md`:
the per-kind blit paths and the `SVF_TARGETS` switch) and t_78219730 (`spec/renderer-design.md`,
`c/bench/MEASUREMENTS.md`). A plan follows this document; nothing here is implemented yet. Choices the user did not
make are marked **my call**; the user's answers of 2026-10-20 are in "Decisions taken" and the changes of this
revision in "Revision 4" at the end.

## Intent

DOS after VGA means VESA 2.0: a linear framebuffer (LFB) the program maps once and writes with plain stores, in packed
pixel formats. The renderer has one of them (RGB565). The user wants the rest of what VBE 2.0 cards offer: 8 bpp
palette (modes 0x101/0x103/0x105), 15 bpp RGB555 (0x110/0x113/0x116) and 24/32 bpp (0x112/0x115/0x118), each as a
target kind that draws exactly what `tools/svfline.py` draws, each left out of a build that does not want it, and a
DOS example that finds a VBE 2.0 mode, maps the LFB through DPMI, draws into a system-RAM back buffer and copies the
changed rows with `rep movsd`. Planar 16-colour modes are not part of this.

## Goals

1. Four target kinds: `SVF_T_INDEXED8`, `SVF_T_RGB555`, `SVF_T_XRGB8888`, `SVF_T_RGB888`. Each byte-identical to a
   `tools/svfline.py` rule (`Target.put`, `to_target`, `draw_target`), on every face, clip, phase, overlap and ratio
   the existing sweeps cover.
2. Each kind behind its own `SVF_TARGETS` bit; Cortex-M0+ P1/P2 text stays <= 8192 B with the new kinds masked out
   (today 5674). The compile gate of `c/check.sh` grows to every mask of the nine bits.
3. Packed fast paths: 4 pixels per 32-bit access for INDEXED8, 2 per store for the 16-bit kinds (RGB565 gets the same
   upgrade), empty-byte skip, byte order folded into per-cell constants. Exact: the word path writes the same bytes
   the byte loop writes, only with fewer accesses; it is compiled where unaligned stores are cheap (x86, WASM) and
   measured before it is enabled anywhere else.
4. A DOS example `c/ports/dos/svfvesa.c` (DJGPP) at 16, 8 and 32 bpp (and 15/24 bpp when the mode exists), with
   DOSBox-X (S3, VBE 2.0) screenshots at 640 x 480 and 1024 x 768, and DOS speed rows for the new kinds at 16 and
   24 px faces in `c/bench/MEASUREMENTS.md`.

## Non-goals

- No fast mode. The accuracy policy on the card (an opt-in mode may deviate ±1 LSB on 8/2 bpp colour blends) is not
  used here: every new kind is exact only. A fast mode is its own card, measured against these exact paths.
- No planar (4 bpp) VGA/VESA modes, no bank-switched (non-LFB) VBE 1.2 fallback in the example, no VBE 3.0 features
  (protected-mode interface, refresh control; its `Lin*` mode-info fields are read when the BIOS is 3.0, nothing
  more), no mode 13h changes (`svfdemo.c` stays as it is).
- No palette management in the library: INDEXED8 writes indices; the palette is the caller's (the example sets it).
- No RGBA/RGBX byte orders for the web port (user, question 4): XRGB8888 is the x86 LFB order only.
- No change to the walker, `svf_glyph`/`svf_compose`, the syllable cache or `svf_scale.c`.

## Anti-goals (a failure even if it works)

- Any pixel that differs from `svfline` in the default build, on any kind, old or new.
- A word store that touches a byte outside the clip or a padding byte of a row, or one formed from a misaligned
  pointer cast (UB; the sanitizer build must stay clean with the buffer at any alignment).
- Static data in `c/src`, a `malloc`, a header beyond the three allowed, a pointer formed before a row start, signed
  overflow on a 16-bit `int` (AVR compiles every kind in P1\*/P4).
- P1/P2 growing because of a kind they do not compile (the mask must really leave the code out); a speed or size
  change on the Pico/ESP32 RGB565 paths that was not measured.
- A DOS example that hard-codes mode numbers: a real S3 Trio reports 0x112 as 24 bpp, DOSBox-X as 32 bpp.

## Public API additions (`c/include/svf.h`)

```c
typedef enum {
	SVF_T_GRAY8, SVF_T_MONO_PAGE, SVF_T_MONO_ROW, SVF_T_RGB565, SVF_T_COVERAGE_CB, /* as today: 0..4 */
	SVF_T_INDEXED8,  /* 5: one byte a pixel, a palette index from a coverage ramp or a threshold */
	SVF_T_RGB555,    /* 6: two bytes a pixel, xRRRRRGGGGGBBBBB */
	SVF_T_XRGB8888,  /* 7: four bytes a pixel, memory order B G R X */
	SVF_T_RGB888     /* 8: three bytes a pixel, memory order B G R */
} svf_target_kind;

#define SVF_TARGET_GRAY8     0x001u /* ... 0x010u SVF_TARGET_CB as today */
#define SVF_TARGET_INDEXED8  0x020u
#define SVF_TARGET_RGB555    0x040u
#define SVF_TARGET_XRGB8888  0x080u
#define SVF_TARGET_RGB888    0x100u
#ifndef SVF_TARGETS
#define SVF_TARGETS 0x1FFu          /* default: every kind */
#endif

#define SVF_TF_565_BIGENDIAN 0x01u                   /* unchanged: RGB565 and RGB555, high byte first */
#define SVF_TF_RGB16_BIGENDIAN SVF_TF_565_BIGENDIAN  /* the name that says it applies to both; the same bit */

/* Word stores (below): 1 where a 4-byte memcpy at any alignment is one store (x86, WASM), else 0; -DSVF_WORD_STORE=0/1
 * for every source overrides. Pixels are the same either way. */
#ifndef SVF_WORD_STORE
#if defined(__i386__) || defined(__x86_64__) || defined(__wasm__)
#define SVF_WORD_STORE 1
#else
#define SVF_WORD_STORE 0
#endif
#endif

typedef struct svf_target {
	svf_target_kind kind;
	uint8_t *buf;
	size_t buf_len;
	int16_t w, h;
	uint16_t stride;
	int16_t clip_x0, clip_y0, clip_x1, clip_y1;
	uint16_t fg565, bg565;   /* RGB565: 5/6/5 values; RGB555: 5/5/5 values, bit 15 copied to the pixel */
	uint8_t mono_threshold;  /* MONO_PAGE, MONO_ROW, and INDEXED8 with index_levels 1 */
	uint8_t flags;           /* SVF_TF_565_BIGENDIAN */
	void (*plot)(void *ctx, int16_t x, int16_t y, uint8_t cov);
	void *ctx;
	uint32_t fg888, bg888;   /* XRGB8888 and RGB888: 0x00RRGGBB; bits 31..24 of fg888 are XRGB8888's X byte */
	uint8_t index_base;      /* INDEXED8: the ramp's first index (its level 0, the background level) */
	uint8_t index_levels;    /* INDEXED8: ink levels above it, 1..255; index_base + index_levels <= 255 */
} svf_target;
```

- **Bit i is kind i** stays true (5..8 <-> 0x20..0x100). The default mask is 0x1FF; every place that spells the old
  default (`c/tests/test_args.c` `#if SVF_TARGETS == 0x1Fu`, `c/check.sh`'s 0x1F, the header comment) is updated,
  since a stale `0x1F` guard would silently skip the `lines()` argument tests in the default build.
- **Fields** (user, question 3): the 16-bit kinds share `fg565`/`bg565` (for RGB555 they hold 15-bit values plus bit
  15; the field name is historical and the header says so). The 24/32-bit kinds get `fg888`/`bg888`. INDEXED8 gets
  `index_base`/`index_levels` and reuses `mono_threshold`. The new fields are appended, so existing initialisers
  stay valid.
- **`svf_target_init`** sets, as today, the clip to the whole target, `fg565 = 0xFFFF`, `bg565 = 0`,
  `mono_threshold = 128`, `flags = 0`, `plot`/`ctx` NULL, and now `fg888 = 0x00FFFFFF`, `bg888 = 0`, `index_base = 0`,
  `index_levels = 255`. An INDEXED8 target with defaults therefore draws the GRAY8 bytes (index = coverage), and an
  RGB555 target with defaults draws white with bit 15 set (0xFFFF: the default is "set"; a caller who needs bit 15
  clear passes `fg565 = 0x7FFF`, as the DOS example does).
- **Validation** (`target_ok`, re-checked on every draw as today): row bytes INDEXED8 `w`, RGB555 `2w`, XRGB8888
  `4w`, RGB888 `3w`, computed in `uint32_t`; `stride >= row` and `rows * stride <= buf_len` as for the other kinds.
  Because `stride` is `uint16_t`, a 32 bpp target is at most 16383 pixels wide and a 24 bpp one 21845 (the check
  fails on its own); the header says so. INDEXED8 additionally needs `index_levels >= 1` and
  `(unsigned)index_base + index_levels <= 255`, else `SVF_E_ARG`.
- **The compile gate becomes 2048 compiles** (user, question 5): `c/check.sh targets_ok` compiles `svf_draw.c` for
  every `SVF_TARGETS` in 0x000..0x1FF, with and without `SVF_NO_SCALE`, with gcc and clang. Measured here one compile
  is 0.15 s (gcc) / 0.10 s (clang): 4 minutes serial, about 20 s in parallel. The script writes one job per record
  to a list, **one compound token per job** so no record is ever empty or split (`0x1FF`, `0x1FF:-DSVF_NO_SCALE`,
  `0x1FF:-DSVF_WORD_STORE=0`, ...: the mask, then `:`-separated extra defines, none containing whitespace), and runs
  `xargs -P "$(nproc 2>/dev/null || echo 1)" -n 1 sh -c '...' "$CC"` where the one-line script splits its single
  argument on `:` into `-DSVF_TARGETS=<mask>` and the extra defines; each job prints its own `targets: FAIL: <job>` and
  the compiler's output on failure, so the first failure is still named, and `xargs`'s exit status (non-zero when any
  job fails) fails the gate. Records in the list, per compiler: 512 masks x {none, `-DSVF_NO_SCALE`} = 1024, plus
  `-DSVF_WORD_STORE=0` and `=1` for the masks 0x1FF, 0x1E8, 0x008 and each single new bit (14 more), so both word-store
  builds stay warning-free with any kind left out.
- **`svfdump`** gains the kind names `indexed8`, `rgb555`, `xrgb8888`, `rgb888`; the options `--index-base=N`,
  `--index-levels=N`, `--fg888=N`, `--bg888=N`; and `--misalign=K` (0..3): the target buffer starts K bytes past a
  4-byte boundary. The allocation becomes `GUARD + K + blen + GUARD` with both guards checked around the shifted
  buffer, so a misaligned run cannot report a false guard change.

## Pixel rules per kind (the words that go into `svf.h` and `svfline.py`)

Every kind receives, per drawn cell, its pixels with coverage > 0 inside the clip, row by row, cells in line order,
and touches nothing else. Coverage `c` is 1 bpp 255, 2 bpp level k * 85, 8 bpp (including every scaled cell) the byte.
All arithmetic below is unsigned, and its width is stated per expression because AVR's `int` and `unsigned` are 16
bits and the AVR P1\*/P4 size rows compile these kinds: the INDEXED8 level `((unsigned)c * n + 127u) / 255u` fits 16
bits (at most `255 * 255 + 127 = 65152`); the 5-bit channel blends of `blend565`/`blend555` fit 16 bits (at most
`63 * 255 + 127`); the 8-bit channel blend and the palette formula also fit 16 bits unsigned, because their weights
sum to 255 (or n): at most `255 * 255 + 127 = 65152`. The hazard is the signed promotion of `uint8_t` to a 16-bit
`int` (65152 > 32767), so `blend888` and `vbe_palette_entry` compute in `uint32_t` (`((uint32_t)c_bg * (255u - c) +
(uint32_t)c_fg * c + 127u) / 255u`) or `unsigned`, never with promoted `uint8_t`s. Word constants are built in `uint32_t`
(`(uint32_t)top * 0x01010101u`). **16-bit-int test build note:** no host compiler gives a 16-bit `int`, so the gate
checks this two ways: the AVR object set of `build-all.sh` compiles every kind with `-Werror` (a compile check only),
and `c/tests/test_blend16.c` (host, run by `make -C c check`) evaluates `blend888`, `blend565`, `blend555`, the
level formula and the palette formula at every coverage and channel value; the copy models AVR's promotion rule: an
intermediate built from promoted `uint8_t`/`int` operands is checked to stay within a 16-bit signed `int`
(<= 32767) and the test fails otherwise, while an expression the source computes in `unsigned`/`uint32_t` is
checked through a copy of each expression whose
intermediates are `uint16_t` (so a 16-bit wrap happens on the host too) and compares with the Python values: an
expression that is only right with a 32-bit `int` fails there, not on the Uno. The same file asserts the stated
maxima (65152 for the level, the 8-bit blend and the palette formula; 16192 for the 5-bit blends).

### SVF_T_INDEXED8

One byte a pixel at `buf[y * stride + x]`. With `n = index_levels`, `b = index_base`:

- **Level:** `L = (c * n + 127) / 255` for `n >= 2` (round half up: a 2 bpp level k with n = 3 gives L = k exactly;
  n = 255 gives L = c). For `n = 1` (user, question 2: the threshold-index form), `L = 1` when
  `c >= mono_threshold` (0 counting as 1, the mono rule), else 0; at threshold 128 this is what the ramp formula gives
  for n = 1 anyway, and it makes an n = 1 INDEXED8 draw agree bit for bit with MONO_ROW at any threshold.
- **L = 0 leaves the pixel untouched** (as a mono kind leaves a pixel below threshold). Otherwise the index is
  `i = b + L` (always >= 1, since b + L >= L >= 1: 0 can serve as the "untouched" sentinel in a per-cell table).
- **Overlap: the GRAY8 max rule** (user, question 1): the pixel becomes `max(existing, i)`, reading the existing byte,
  exactly as GRAY8 takes `max(existing, coverage)`. Because L is monotonic in c, the largest index wins exactly when
  the largest coverage does, so `draw_target` (per cell) and `to_target` (of the GRAY8 max line) give the same bytes,
  as they do for GRAY8: the test asserts both. **Consequence the header states:** text shows only where the existing
  index is below the ink's; the background index (and any UI colour the text must cover) has to be below the ramp.
  The example's palette puts the background at 0 and every ramp above 16; the tests prefill 0, values below the ramp,
  inside it (above and below the drawn index) and above it, including 255, and assert `max` in each case.
- **Defaults** (b 0, n 255) reproduce GRAY8 byte for byte (L = c, max): a test.

### SVF_T_RGB555

Two bytes a pixel at `buf[y * stride + 2x]`, low byte first (high first with the big-endian flag), the value
`(fg565 & 0x8000) | blend555(fg565 & 0x7FFF, bg565 & 0x7FFF, c)`: per 5/5/5 channel (shifts 10, 5, 0, mask 31)
`(c_bg * (255 - c) + c_fg * c + 127) / 255`, the same arithmetic as `blend565` on its 5-bit channels (one test checks
`blend555 == blend565` on R and B for every coverage and channel value). Bit 15 of the written pixel is bit 15 of
`fg565`, whatever the coverage; with the default `fg565 = 0xFFFF` it is set (**my call**: the whole pixel is written,
bg is the known background, and the bit is the caller's to clear or set; tests cover both states byte for byte). A
later cell's pixel replaces an earlier one (the RGB565 rule: the existing pixel is never read).

### SVF_T_XRGB8888

Four bytes a pixel at `buf[y * stride + 4x]`, in memory `B, G, R, X`: the little-endian dword `X RR GG BB`, which
is what every x86 VBE 32 bpp mode (RedFieldPosition 16, Green 8, Blue 0, reserved 24) stores. Channels are
`blend888`: per 8-bit channel `(c_bg * (255 - c) + c_fg * c + 127) / 255` in `uint32_t` (the sum reaches 65152,
past a 16-bit signed `int`) over `fg888`/`bg888`; `X` is byte 3 of
`fg888` (bits 31..24; 0 by default, so a caller using the buffer as ARGB can ask for 0xFF). One byte order (user,
question 4). Later cell wins.

### SVF_T_RGB888

Three bytes a pixel at `buf[y * stride + 3x]`, in memory `B, G, R`, the same `blend888`. Later cell wins. It is
worth having (**my call**): the blend, the colour tables and the loop shape are XRGB8888's, so it is one more blit
function of three loops (an estimated 250-400 B of Thumb, 0 when masked out), and it is not optional for real
hardware: an S3 Trio64 and most Cirrus BIOSes report mode 0x112/0x115/0x118 as 24 bpp, while DOSBox-X reports them as
32 bpp (`vesa vbe 1.2 modes are 32bpp = auto`). Without RGB888 the example would run in the emulator and fail on the
card the card is named after. Its fast path is the byte loop (3-byte pixels do not pack into words without crossing
pixels; the skip of empty source bytes is kept).

### Which overlap rule, and why

| kind | overlap of two cells of one line | why |
|---|---|---|
| INDEXED8 | largest index wins (`max`, reads the pixel) | the card asks for the GRAY8 max rule; an index is a coverage level, and max keeps a mark's base intact under a lighter mark |
| RGB555, XRGB8888, RGB888 | later cell wins (never reads) | the RGB565 rule, for the RGB565 reasons: a blended colour cannot be max-ed, reading a 16/32-bit pixel to recover coverage is impossible, and not reading is what makes the packed store a pure store |

## Fast paths

Each new kind is one `blit_*` of three loops (1, 2, 8 bpp source), chosen once per cell as today; every loop skips
a source byte of 0 (1 and 2 bpp). Per-cell constants are built on the stack (no static data; a table per cell is
allowed, the blit plan's 4-entry limit was that plan's constraint), and only the ones the cell's bpp uses (1 bpp: the
top colour and its pair word; 2 bpp: the 4 level colours and the 16 pair words; 8 bpp: none).

**Word stores** (`SVF_WORD_STORE`, above) go through `memcpy(dst, &word, 4)` (2 for one 16-bit pixel): with a
constant size gcc, clang and DJGPP gcc emit one `mov` on x86 and one `i32.store` on WASM; no pointer is cast, so any
buffer alignment is defined behaviour and the sanitizer build stays clean. On Cortex-M0+ and ESP32-C3 an unaligned
4-byte `memcpy` is four byte stores or a call, so there the default is the byte loop and nothing changes for the Pico
and ESP32 ports (built `SVF_TARGETS=0x02`/`0x08`). **In this card `SVF_WORD_STORE` stays 0 on every MCU**; this card
only records the Cortex-M0+ P3 size with `-DSVF_WORD_STORE=1`. The decision to widen the default is taken later, from
the RGB565 speed rows of the MCU ports card t_47ca86d1 (running in parallel): its Pico cases `syl_ga`, `screen32`,
`aa_line12` and `aa_screen10` on RGB565 at `-Os` and `-O2`, plus the `blit_rgb565` share of its `PROFILE=1` run,
measured with `-DSVF_WORD_STORE=1` against 0; the default widens to ARMv6-M only if none of those rows is slower and
P3 is not larger, and to ESP32-C3 only by the same comparison on t_47ca86d1's instruction-count bench, if that bench
lands. Until those rows exist nothing off x86/WASM changes, and no Pico run is part of this card.
The word tables are built host-independently: each 2- or 4-byte pixel is first laid out as bytes in the
target's order (as `pair[j][2]` is today), and a word is `memcpy`'d from the byte array, so a big-endian host writes
the same bytes.

- **INDEXED8.** Per cell: `top = b + n`, and for 2 bpp `idx[4]` with `idx[k] = b + L(k * 85)` or 0 when L is 0
  (the sentinel above). 1 bpp: per source byte, each nibble that is 0xF and whose 4 target columns lie inside
  `[c0, c1)` is one 4-byte load, four byte `max`es against `top` and one 4-byte store ("4 px per 32-bit access":
  the max rule needs the read; 2 word accesses replace 8 byte accesses); any other nibble does its set bits as bytes
  (`if (top > dst[i]) dst[i] = top`). 2 bpp: a byte of 0xFF (four top-level pixels) inside the cut takes the same word
  path with `top`; otherwise 4 pixels through `idx[]`, skipping `idx[k] == 0` (level 0 and L = 0 pixels are never
  touched) and doing the byte max for the rest. 8 bpp: per pixel, compute L, skip 0, byte max. n = 1: per pixel
  `c >= thr`, then as the top level (1 bpp: the mono pack is not reused, the destination is a byte a pixel).
  *Task 10: the 1 bpp nibble word path was removed (measured 4.7 % slower than the byte loops on the emulated
    486DX2-66, c/bench/MEASUREMENTS.md); the 2 bpp path stays.*
- **RGB555 and RGB565: one shared `blit_rgb16`** (`#if SVF_TARGETS & (SVF_TARGET_RGB565 | SVF_TARGET_RGB555)`),
  parameterised by the 4 per-level colours its caller computes (blend565, or blend555 with bit 15 applied); the
  existing `blit_rgb565` becomes a caller of it. Per cell: `pix[4][2]` in the target's byte order (as today) and, at
  2 bpp with `SVF_WORD_STORE`, `pair[4][4][4]`, the 16 two-pixel byte quads for every (level a, level b) copied from
  `pix` (no blend per pixel at 1/2 bpp). 1 bpp: per source byte, each 2-bit group `11` whose two columns are inside the
  cut is one 4-byte store of the top pair; a lone bit is a 2-byte store. 2 bpp: per source byte, the high pixel pair
  and the low pair: both levels non-zero and inside the cut, one 4-byte store of `pair[a][b]`; else 2-byte stores of
  the non-zero one(s). 8 bpp: per pixel blend and a 2-byte store (unchanged: scaled TFT text is rare, and a per-pixel
  blend pair would not be fewer instructions). Without `SVF_WORD_STORE` the loops are today's byte-pair loops.
- **XRGB8888.** Per cell `px32[4][4]` (the level colours as `B G R X` bytes); 1 and 2 bpp store one 4-byte pixel per
  covered pixel (a `memcpy` of 4, one store on every architecture that allows it, four bytes elsewhere); 8 bpp blends
  per pixel. One pixel is already one 32-bit store: nothing to pack.
- **RGB888.** As XRGB8888 with 3-byte stores (`pix24[4][3]`).
- **The cut edges.** A word access needs all its pixels inside `[c0, c1)`; the first and last source byte of a row
  fall back to the byte loop when a group crosses `c0` or `c1`. The row pointer stays
  `t->buf + (size_t)(y + row) * stride` and every index is `k * (size_t)(x + col)` with `x + col >= 0`: nothing is
  formed before the row start (clang's `-fsanitize=pointer-overflow` and `TestBlitPaths.test_negative_x_on_row_zero`
  cover the new kinds too).
- **What is measured, and what counts.** The DOS bench (below) runs every packed kind with `SVF_WORD_STORE` 1 and 0
  and `MEASUREMENTS.md` keeps both rows; a word path is kept in the x86 default only if its row is not slower. Honest
  caveat for the record: DOSBox-X executes a fixed number of instructions per emulated millisecond and models no memory
  bus, so it can show the instruction count falling, not the store bandwidth a real 486/Pentium saves; the
  real-hardware benefit is the stated reason, the emulated number the only one we have.

## `tools/svfline.py` (the reference) changes

The reference must gain the new kinds (controller ruling: the "do not change svfline.py" constraint belonged to the
blit plan, whose kinds already existed; this card adds kinds, and byte identity is against this file).

- `TARGET_KINDS += ("indexed8", "rgb555", "xrgb8888", "rgb888")`; `target_row_bytes`: w, 2w, 4w, 3w; `target_rows`: h.
  Two named sets the tests use: `LATER_CELL_KINDS = {"rgb565", "rgb555", "xrgb8888", "rgb888"}` (per-cell
  `draw_target` may differ from `to_target`) and `RGB16_KINDS = {"rgb565", "rgb555"}` (the byte-order flag applies).
- `Target.__init__` gains `index_base=0, index_levels=255, fg888=0xFFFFFF, bg888=0`.
- New pure functions, each a few lines and the words of the rules above: `index_level(cov, levels, threshold)`,
  `blend555(fg, bg, cov)` (low 15 bits; the caller ORs bit 15 of fg), `blend888(fg, bg, cov)`; `Target.put` gets
  one branch per kind (INDEXED8 untouched-when-0 then `max`, the others plain writes in the kind's byte order, RGB555
  with bit 15 from fg). `to_target` and `draw_target` do not change: they already send every covered pixel through
  `put`.
- The module docstring's "Targets" paragraph lists the four kinds with their rules, as it lists the five today.

## Test plan (`tools/test_c_renderer.py`, `c/tests/test_args.c`, `c/Makefile`, `c/check.sh`)

The sweeps that iterate `svfline.TARGET_KINDS` (`TestTargets`, `TestBlitPaths`, the scale tests that draw on targets)
run on the new kinds once the mixin knows their options; but as written today they special-case RGB565 by name in
nine places and sweep with 565 colours only, so the following changes are part of the plan, not left to discovery:

- **Generalise the mixin and the sweeps.** `TargetMixin.opts_of`/`target`/`expect` take `index_base`, `index_levels`,
  `fg888`, `bg888`, `misalign`. Every `kind == "rgb565"` test becomes `kind in svfline.LATER_CELL_KINDS` (the
  `check` assertion `out == to_target`, `test_overlap_every_kind`, `test_later_cell_lower_coverage`,
  `test_negative_x_on_row_zero`, `test_bottom_edge`), and every big-endian loop runs for `kind in RGB16_KINDS`.
  `test_later_cell_lower_coverage` asserts `cells != line` for every later-cell kind and the exact later-cell bytes at
  the probe pixel (565: today's value; 555: `blend555` with bit 15; 888/8888: `blend888` bytes in B G R (X) order).
  Sweep defaults per kind are non-trivial so a channel swap or a wrong X byte cannot hide: 888 kinds `fg888
  0x8C123456`, `bg888 0x00ABCDEF`; RGB555 `fg 0x1234`/`bg 0xABCD` as RGB565, both byte orders; INDEXED8 two ramps,
  `(base 16, levels 3)` and `(base 64, levels 63)`, each once with the fill byte below the ramp (0 and base - 1) and
  once inside it (base + 1) so the `max` rule is exercised across phases, clips, scale and misalignment, plus the
  default ramp once (the GRAY8 identity).
- **INDEXED8 rules.** Defaults equal GRAY8 byte for byte on every chain and placement. n = 3 on 2 bpp faces equals
  `base + level` on a zero-filled buffer. n = 1 at every value of `THRESHOLDS` equals the MONO_ROW bits of the same
  line (unpacked). The `max` rule with prefilled buffers: fill bytes 0, base - 1, base + 1 (inside, below the drawn
  top), base + n (inside, the top), base + n + 1 and 255, on `HLHHL` of the overlap faces, per cell against
  `draw_target` and against `to_target` (they must agree); with fill 255 nothing changes and the test says so. L = 0
  pixels untouched (8 bpp face with coverages 1..42 at n = 3). `base + n > 255` and `n = 0` refused.
- **RGB555.** `blend555` vs `blend565` channel identity; big/little byte order are each other's swap; bit 15 follows
  fg (fg 0xFFFF and 0x7FFF, byte-level); asymmetric colours pin the channel order (the RGB565 wide-cell test
  duplicated).
- **XRGB8888 / RGB888.** Asymmetric fg/bg pin `B, G, R(, X)`; X from fg888 bits 31..24 at 0x00 and 0x8C; stride + 3
  and stride + 5 paddings never written; the widths past the stride limit refused (32 bpp 16384, 24 bpp 21846) and
  the largest widths accepted (32 bpp 16383, 24 bpp 21845; buf_len permitting); the later-cell rule on `HL`.
- **Word stores.** `--misalign=1..3` on every packed kind at every x phase under ASan/UBSan (gcc and clang); clip
  edges at every column mod 4 (INDEXED8) and mod 2 (16-bit) of a 1 bpp all-ink face (`pad1`) and a 2 bpp all-level-3
  face, so each nibble/pair falls on each side of `c0`/`c1`; a target 1, 2 and 3 pixels wide; the whole
  `TestBlitPaths` once more against an `svfdump-bytes` build (`-DSVF_WORD_STORE=0`) so both paths are held to the
  reference on the host.
- **Masks.** `svfdump-page` (0x02) keeps refusing everything else, now including the four new kinds;
  `svfdump-vesa` (`-DSVF_TARGETS=0x1E8`: INDEXED8 | RGB555 | RGB565 | XRGB8888 | RGB888, the DOS profile P5) draws
  the same bytes as the default build on those five kinds and refuses GRAY8, the mono kinds and the callback;
  `test-args` (`#if SVF_TARGETS == 0x1FFu`) and `test-args-page` gain the new kinds' NULL/argument cases
  (`index_levels` 0, base overflow, NULL buf, stride short by one, 32 bpp width 16384, 24 bpp width 21846).
  `check.sh targets_ok` over 0..0x1FF as above.
- **The DOS example's parser on the host.** The VBE/DPMI code that can run without a BIOS is a pure C unit,
  `c/ports/dos/vbe_select.c` with `vbe_select.h` (no `<dpmi.h>`, no I/O):
  - `int vbe_modes_copy(const uint8_t block[512], vbe_read_word_fn read_word, void *ctx, uint16_t modes[257])`:
    validates `VideoModePtr`, reads the list one word at a time through
    `typedef int (*vbe_read_word_fn)(void *ctx, uint32_t seg, uint32_t off, uint16_t *out)` (0 ok, -1 a failed or
    out-of-range read; the DOS program's callback is `dosmemget` on `seg * 16 + off`, a host test's a low-memory
    image array), stops at 0xFFFF, at 256 entries, before 0x100000 or at the first failed read, and returns the count
    of modes copied (0..256; a negative value for an invalid pointer or a failed first read). `modes[]` has 257
    entries so that for every non-negative return the 0xFFFF sentinel is stored at `modes[count]`, also at count
    256; after a negative return `modes[]` is unspecified and must not be walked.
  - `int vbe_mode_accept(const uint8_t info[256], unsigned vbe_version, unsigned w, unsigned h, unsigned bpp,
    vbe_mode *out)`: the attribute, layout and depth rules below (the `Lin*`/plain choice, every field position
    validated against its mask size and the depth), the pitch and size checks, the `map_size` and back-buffer
    arithmetic; returns 0 and fills `out` (pitch, kind, bytes_pp, phys_base, lfb_size, map_size, buffer size) or a
    negative reason code whose text the program prints.
  - `int vbe_status(unsigned ax, unsigned fn)`: the status helper; 0 for `ax == 0x004F`, else `VBE_FATAL` for
    fn 4F00h/4F01h/4F02h and `VBE_FALLBACK` for 4F08h/4F09h.
  - `vbe_palette_entry(k, n, bg, fg, dac_bits, out[4])`: the palette rule below in B G R pad order.
  `svfvesa.c` only wraps them around `__dpmi_int`, `dosmemput`/`dosmemget`, the mapping calls and `movedata`.
  `c/tests/test_vbe.c` (built and run by `make -C c check` under the sanitizers, host only) feeds them hostile input
  through a callback over a 1 MiB-shaped image (reads at or past 0x100000 fail): a controller block with
  `VideoModePtr` at 0xFFFFE, 0xFFF00 and 0x100000 - 512 (only words wholly below 1 MiB are read), a list with no
  0xFFFF within 256 entries, a list with the terminator first, a read that fails mid-list, mode blocks with the LFB
  bit clear, `PhysBasePtr` 0, `BytesPerScanLine` 0, 65535 and 65536-wrapped values, `Lin*` fields zero and non-zero
  with different layouts, field positions that overlap or exceed the depth (`RedFieldPosition 11` with mask 6,
  position 28 with mask 8 at 32 bpp, position 16 at 16 bpp), masks 5/5/5 reported as 16 bpp, 24 bpp reported with
  32 positions, `XResolution` 0, 4097 and 65535, every combination that makes `pitch * h` or `w * bytes_pp * h`
  exceed the caps, and `vbe_status` for every (ax, fn) pair. Each refusal asserts the reason code, each accepted
  case asserts pitch, kind, `map_size` and the buffer size, and `vbe_modes_copy`'s count and sentinel are asserted
  for every list case.
- **Gate:** `make -C c check` (gcc and clang sanitizers, `pointer-overflow` included), `c/cross/build-all.sh` every
  toolchain OK with the budget line unchanged, `--ports` building both DOS programs.

## DOS VBE 2.0 example (`c/ports/dos/svfvesa.c`, `vbe_select.c`, `vesa_lines.c`, `vesa-lines.txt`, `vesa-shots.sh`, `README.md`; `c/tests/test_vbe.c`)

A second program next to `svfdemo.c` (mode 13h stays as the smallest example). Usage: `SVFVESA.EXE` with no
arguments runs the card's sequence at 640 x 480: 16 bpp, a key, 8 bpp with the palette ramps, a key, 32 bpp, a key
(a depth whose mode is missing is reported and skipped). `SVFVESA.EXE W H BPP [DUMP]` runs one mode (W, H decimal;
BPP 8, 15, 16, 24 or 32), waits for a key, and with DUMP writes the back buffer to that file. The mode is chosen by
geometry and channel layout, never by number. Every VBE call is checked for `AX == 0x004F`: a failure of 4F00h, 4F01h
or 4F02h names the function and exits to text mode; a failure of 4F08h or 4F09h (the palette calls) is not fatal and
takes the fallbacks named below (6-bit DAC; ports 3C8h/3C9h).

- **Mode query (VBE 2.0).** `"VBE2"` is written into a 512-byte block in DJGPP's transfer buffer (`__tb`, via
  `dosmemput`), `INT 10h AX=4F00h` (`__dpmi_int`, ES:DI = the block), the block read back with `dosmemget`; require
  `VbeVersion >= 0x200`. The mode list pointer (`VideoModePtr`, a real-mode far pointer) is validated as
  `lin = (uint32_t)seg * 16 + off`, and the list is copied out of DOS memory with `dosmemget` into a local
  `uint16_t modes[257]` (`vbe_modes_copy`) before any other VBE call, in steps of one word while
  `lin + 2 * (i + 1) <= 0x100000`, until
  0xFFFF or 256 entries (a list is often placed inside the caller's 512-byte block, which the next call would
  overwrite; a pointer at or past 1 MiB, a list that reaches 1 MiB before its terminator, or one with no terminator
  within 256 entries is reported and the entries read so far are used). Then for each mode: the 256-byte
  ModeInfoBlock area at `__tb` is **zeroed first** (`dosmemput` of 256 zero bytes, so a BIOS that fills fewer bytes
  leaves no stale fields from the previous mode), then `AX=4F01h` (the list is already in C memory). A mode is
  accepted when ModeAttributes has
  bits 0 (supported), 4 (graphics) and 7 (LFB), `XResolution` and `YResolution` match, `PhysBasePtr != 0`,
  `MemoryModel` is 4 (packed, 8 bpp) or 6 (direct colour), and the layout matches. Layout fields: for an LFB mode the
  linear ones (`LinBytesPerScanLine`, `LinRedMaskSize`/`LinRedFieldPosition` and the green/blue/reserved pairs, at
  the offsets VBE 3.0 defines) are used **whenever they are filled** (`LinBytesPerScanLine != 0` and the three
  `Lin*MaskSize` non-zero for a direct-colour mode, `LinBytesPerScanLine != 0` alone for 8 bpp), whatever
  `VbeVersion` says (a 3.0 BIOS may give the LFB a different layout than the banked window, and some 2.0 BIOSes fill
  the fields too); otherwise the plain ones (`BytesPerScanLine`, `RedMaskSize`...), which is what a 2.0 BIOS that
  leaves the reserved area zero gives, and what a 3.0 BIOS that reports zero `Lin*` before the mode is set falls
  back to. Whichever set is selected, **for a direct-colour mode (MemoryModel 6) every field position is validated
  before use**, over the channels whose mask size is > 0 only (red, green, blue, and the reserved field when its
  mask size is non-zero; for a 32 bpp mode the reserved field must be absent or exactly size 8 at position 24, the X byte
  that XRGB8888 writes, else the mode is refused): with `depth = BitsPerPixel == 15 ? 16 : BitsPerPixel`, `position + mask_size <= depth`
  for each, the mask sizes sum to at most `depth`, and the fields do not overlap; a block that fails this is
  "unsupported layout" whatever its depth says. An 8 bpp palette mode (MemoryModel 4) has no fields and skips these
  checks. The 15-as-16 rule matters in practice: DOSBox-X 2026.08.31 reports its M_LIN15 modes as `BitsPerPixel 15`
  with R 5 @ 10, G 5 @ 5, B 5 @ 0 and a reserved field 1 @ 15 (`src/ints/int10_vesa.cpp` 358-374), whose sum is 16;
  `test_vbe.c` carries that 5/5/5/1 block as an accepted case. Depth: 8 bpp `BitsPerPixel == 8`; 15 bpp mask sizes
  5/5/5 at positions 10/5/0 (`BitsPerPixel` may read 15 or 16: the masks decide, and the mode is then the
  **logical** 15 bpp whatever the field said); 16 bpp 5/6/5 at 11/5/0; 24 bpp `BitsPerPixel 24` and 8/8/8 at 16/8/0;
  32 bpp `BitsPerPixel 32`, the same positions. Kind: 8 -> INDEXED8, 15 -> RGB555, 16 -> RGB565, 24 -> RGB888,
  32 -> XRGB8888. Modes with other
  layouts are listed as "unsupported layout" and skipped. Set with
  `AX=4F02h BX=mode | 0x4000` (LFB bit). Text mode is restored with `INT 10h AX=0003h` at every exit, success or
  error (4F03h only reads the current mode and is not used).
- **Checked sizes.** `bytes_pp` from the depth (1, 2, 2, 3, 4); accept only `1 <= w <= 4096`, `1 <= h <= 4096`,
  `pitch >= w * bytes_pp`, `pitch <= 65535` (the renderer's stride); `lfb_size = pitch * h` in `uint32_t` (at most
  65535 * 4096 < 2^32, so no overflow after those checks) and `lfb_size <= 16 MB` (**my call**: larger than any VBE
  2.0 LFB this program handles); `map_size = (lfb_size + 4095) & ~4095u`; back buffer `w * bytes_pp * h` (<= 64 MB by
  the same bounds), `malloc` checked, `dirty` is `h` bytes checked; every `movedata` length is `rows * w * bytes_pp`
  with `rows` counted inside `[0, h)` and the LFB offset `y * pitch` checked `< lfb_size - rows * pitch + pitch`.
- **LFB mapping (DPMI).** `__dpmi_physical_address_mapping` of `PhysBasePtr` for `map_size` bytes (a page multiple),
  then `__dpmi_allocate_ldt_descriptors(1)`, `__dpmi_set_segment_base_address` to the linear address returned and
  `__dpmi_set_segment_limit(map_size - 1)` (page-granular above 1 MB: the low 12 bits are 0xFFF by construction).
  Copies go through `movedata(_my_ds(), src, sel, off, n)`, which DJGPP implements as `rep movsl` plus the tail, with
  no near-pointer tricks (`__djgpp_nearptr_enable` disables memory protection for the whole program and is not used,
  **my call**). At exit the descriptor is freed and `__dpmi_free_physical_address_mapping` is called; a failure of
  that call (DPMI 1.0, absent from some 0.9 hosts) is ignored.
- **Back buffer.** `w * bytes_pp` pitch in system RAM (`malloc` in the example: 1024 x 768 x 4 = 3 MB; the library
  stays allocation-free), cleared to the background pixel of the kind (below). All drawing is `svf_draw_utf8` on this
  buffer; the LFB is write-only.
- **Dirty rows.** A `uint8_t dirty[h]` row mask; the clear marks every row once, each line's draw marks
  `[y_baseline - ext.ascent, y_baseline + ext.descent)` from `svf_measure_utf8`, clamped to `[0, h)`. `flush()`
  copies maximal runs of dirty rows: a run of r rows is one `movedata` of `r * w * bytes_pp` bytes when
  `pitch == w * bytes_pp`, else one per row; it clears the mask and prints the rows copied and the `uclock()` time.
- **Content: one shared table.** `c/ports/dos/vesa-lines.txt`, read by `svfvesa.c` at run time (next to the faces)
  and by `vesa-shots.sh`, so the C program and the `svfline` oracle cannot drift. One line per text line, fields
  separated by `|`: faces (`+`-joined file names, streamed as `svfdemo.c` streams), scale `num/den`, x, baseline,
  colour name, text (UTF-8; `{W}x{H} {BPP}` substituted by both readers; `#` lines are comments). **The colours,
  the background and the ramps live in the same file**, in two sections that precede the lines (`[colours]`,
  `[lines]`; a `[background]` entry in `[colours]`), so there is no prose-only table either reader could follow
  differently: a colour record is `name | rgb565 | rgb555 | rgb888 | index_base | index_levels`, and the 8 bpp
  palette is derived from it by both readers with one rule (below). **Parser rules, identical in `vesa_lines.c` and
  the Python reader**, and every violation a clear error naming the line number: the file is UTF-8 and validated as
  such (an invalid sequence is an error, not U+FFFD); a line is at most 512 bytes including its newline (513 is an
  error); fields are split on `|` and **the one trim rule** is: every field, the text field included, loses its
  leading and trailing spaces and tabs and nothing else (inner spaces stay; a text that should start or end with a
  space cannot, by design); an empty text field is allowed, an empty field anywhere else is an error; a colour
  record has exactly 6 fields, a line record exactly 6; a section header is exactly `[colours]` or `[lines]` and
  `[colours]` must come first; at most 16 colours and 32 lines (the 17th colour and the 33rd line are errors); a
  duplicate colour name is an error, and `background` is required once; numbers are decimal or `0x` hex
  with these ranges: rgb565/rgb555 0..0xFFFF, rgb888 0..0xFFFFFFFF, index_base 0..255, index_levels 0..255 (0 only
  for `background`), `index_base + index_levels <= 255`, scale `num/den` each 1..16, x and baseline -32768..32767;
  a line's colour must name a defined colour other than `background`; a face entry is a bare file name matching
  `[A-Za-z0-9_]{1,8}\.SVF` (DOS 8.3, upper case), joined by `+`, at most 4 per line (a 5th is an error), and is
  opened only in the faces directory the program is given (its current directory on DOS, `svf/dos` for the host
  tools): anything with `/`, `\`, `:`, `..` or a leading `.` is an error, and the host tools additionally resolve
  each entry with `realpath` and refuse one whose resolved path is not inside the resolved faces directory (a
  symlink in the faces directory cannot escape it). The parser tests cover each boundary on both sides: 16 vs 17
  colours, 32 vs 33 lines, 4 vs 5 faces, a line of exactly 512 and of 513 bytes, an empty text field (accepted) and
  an empty numeric/name field (refused), and the trim rule on a text with leading, trailing and inner spaces. The
  initial file (positions fixed, inside 640 x 480; the 1024 x 768 screens show the same lines at the top left):

  ```
  [colours]
  # name       | rgb565 | rgb555 | rgb888   | index_base | index_levels   (rgb888 also gives the palette colour)
  background   | 0x0010 | 0x0010 | 0x000084 | 0          | 0
  white        | 0xFFFF | 0x7FFF | 0xFFFFFF | 16         | 3
  yellow       | 0xFFE0 | 0x7FE0 | 0xFFFF00 | 32         | 3
  scaled       | 0xFFFF | 0x7FFF | 0xFFFFFF | 64         | 63
  [lines]
  # faces                 | scale | x  | baseline | colour | text
  PAPLG16.SVF+PAPLG18.SVF | 1/1   | 16 |  40      | white  | SVF VESA 2.0 예제 {W}x{H} {BPP} bpp
  MARUS24A.SVF            | 1/1   | 16 |  90      | white  | 다람쥐 헌 쳇바퀴에 타고파! MARUS24A
  MARUS24.SVF             | 1/1   | 16 | 130      | white  | 키스의 고유조건은 입술끼리 MARUS24
  PAPLG16.SVF+PAPLG18.SVF | 3/2   | 16 | 180      | scaled | 스케일 3/2: 가나다 Score 120 점
  PAPLG16.SVF+PAPLG18.SVF | 1/1   | 16 | 220      | yellow | 노란 줄: 만나야 하고 특별한 기술은
  ```

  `background` is the clear value of every kind (its `rgb565`/`rgb555`/`rgb888`, or its `index_base` at 8 bpp) and
  the `bg565`/`bg888` of every line. **Palette rule** (both readers): index `background.index_base` (0) takes
  `background.rgb888` (0, 0, 132); for every other colour with `index_levels n`, index `base + k` (k = 0..n) takes,
  per 8-bit channel with `bg` the background's and `fg` the colour's channel value, the integer expression
  `(bg * (n - k) + fg * k + n / 2) / n` computed in `uint32_t` (round half up; at n = 255 the sum reaches 65152,
  past a 16-bit signed `int`), so 16..19 run blue to white (the 2 bpp levels 1..3
  are indices 17..19, 1 bpp ink 19), 32..35 blue to yellow, 64..127 blue to white in 64 steps (the scaled line's
  8 bpp cells show the finer quantisation); every index no colour names is (0, 0, 132) too; with a 6-bit DAC each
  channel is then `>> 2`. The background index 0 is below every ramp, as the INDEXED8 max rule requires; a readers'
  check refuses a file whose background index is not below every ramp or whose ramps overlap. The host tool
  `c/tests/vesa-lines-dump` (`vesa_lines.c` plus a `main`, built by `make -C c check`) prints the parsed table and
  the 256-entry palette as text (`--print-table FILE`); a unit test in `tools/test_c_renderer.py` parses the same
  file with the Python reader and compares the two, and feeds both readers the malformed files of the parser rules
  (over-long line, 5 and 7 fields, `..` and `C:` face paths, duplicate colour, missing background, overlapping
  ramps, invalid UTF-8, out-of-range numbers), asserting each is refused with the same line number.
- **8 bpp palette calls.** `AX=4F08h BL=00h BH=08h` asks for an 8-bit DAC (DOSBox-X: `enable 8-bit dac = true` by
  default); `BH` on return is the width granted (8, or 6 when refused). `AX=4F09h BL=00h CX=count DX=first` sets the
  entries from a table in `__tb` whose 4-byte entries are **blue, green, red, pad** (not R G B: a swap turns the yellow
  ramp cyan, which the capture check catches because it compares against the intended palette); at 6 bits each value
  is `v >> 2`. Neither call is fatal: a refused 4F08h means 6 bits; a failed 4F09h means ports 3C8h/3C9h at 6 bits,
  as the mode 13h demo. The width in use is printed with the sum (below) so the capture check expands with it.
- **Checksum and the run-ready file.** After drawing and flushing, the program writes `sum=<FNV-1a of the back
  buffer>` (the bench's function), `dac=<6|8>` and `mode=0x<n> WxH BPPbpp pitch=<p>` (BPP is the **logical depth
  requested**, 15 for a 5/5/5 mode even when its block says `BitsPerPixel 16`; the block's value follows as
  `bits=<b>` for the record) to `SUM.TXT` in the current directory and
  `fclose`s it **before** waiting for the key (DJGPP's redirected stdout is fully buffered and DOSBox-X writes a
  local-drive file to the host at close, so a line on stdout would not be visible until exit); with DUMP it writes and
  closes the back buffer file first. The same line is also printed to stdout for a human run. `vesa-shots.sh` waits
  for `SUM.TXT` to exist and contain `sum=` with a 60 s timeout, and on timeout kills DOSBox-X and fails loudly
  (`vesa-shots: SVFVESA did not report (W H BPP); see OUT.TXT and dosbox.log`). It computes the expected value in
  Python: `svfline.Target` of the kind with the colours of `vesa-lines.txt`, **its buffer prefilled with the
  background pixel** (the clear value: svfline's default buffer is zero, which would never match), `draw_target` of
  each table line (same chain, scale, x, baseline, colour/ramp), then the same FNV-1a over the bytes; a difference
  fails the script. The DOS build of the new kinds is thereby held to the reference, not only looked at.
- **DOSBox-X configuration.** `machine = svga_s3`, `memsize = 16`, `vmemsize = 8` (1024 x 768 x 32 needs 3 MB;
  `auto` may give less), `output = surface`, `windowresolution = original`, `scaler = none`, `aspect = false`,
  `captures = <OUT>/capture`, `core = normal`, `cputype = 486`, `cycles = fixed 23880` (the bench's DX2-66 preset,
  so the printed flush times are comparable). Under `xvfb-run -a -s "-screen 0 1280x1024x24"` (the window must fit at
  1024 x 768). For the 24 bpp run `vesa vbe 1.2 modes are 32bpp = false` (then DOSBox-X lists 0x112/0x118 as 24 bpp,
  `src/ints/int10_modes.cpp` lines 148/154 against 164/166 of 2026.08.31); the 15 bpp modes (0x110/0x116) are listed
  by default. In DOSBox-X 2026.08.31 the S3 table has 8/15/16/24-or-32 bpp at both 640 x 480 and 1024 x 768, so every
  kind has a mode at both sizes.
- **Script hygiene.** `vesa-shots.sh` works in a directory it creates under `c/build/ports/dos-vesa` (or a given
  OUT), quotes every shell argument, writes the DOSBox-X configuration and autoexec with a heredoc from fixed
  strings plus OUT only, and checks OUT is an absolute path whose every component matches `[A-Za-z0-9._-]+` and is
  neither `.` nor `..` (so `../` cannot pass; no spaces: DOSBox-X's `mount` and autoexec take it unquoted). Before
  it deletes or writes anything there, OUT and each of its existing components must be real directories, not
  symlinks (`test -L` on every prefix, and on `OUT/capture`, `OUT/SUM.TXT`, `OUT/DUMP.RAW` when present: a symlink there
  is refused before anything is deleted), and OUT must be either absent (the script creates it), empty, or carry the
  marker file `.vesa-shots` the script wrote on an earlier run; anything else is refused without touching it. The
  faces are copied from `svf/dos` after the parser's name rules and the `realpath` containment check above.
  `DOSBOX_X` (default `/usr/bin/dosbox-x`) is the one executable run; no `eval`.
- **Screenshots.** For each of (640 x 480, 1024 x 768) x (8, 15, 16, 24, 32) the script first deletes `SUM.TXT`,
  `DUMP.RAW`, `OUT.TXT` and every file in `capture/` from any earlier launch (inside the verified OUT only), then
  runs DOSBox-X once with an autoexec `SVFVESA.EXE W H BPP DUMP.RAW > OUT.TXT`. It waits for `SUM.TXT` (above; 60 s,
  loud failure), checks that its `mode=` line reports the expected `W`, `H` and the requested logical `BPP` (the
  program writes `mode=0x<n> WxH BPPbpp pitch=<p> bits=<b>`; a stale or mismatched file fails the run with the values
  seen), then
  `xdotool key --window <id> ctrl+F5` takes DOSBox-X's own capture (a PNG of the
  rendered frame, exact pixels, no window grab or 2x check needed; **my call** over the ffmpeg grab of
  `screenshot.sh`, which stays for mode 13h). The binding is pinned by writing a mapper file (`mapperfile =`) with
  `hand_scrshot "key 62 mod1"` on Ctrl-F5 (as built; the event is `hand_scrshot`, not `hand_capture`, and the file also carries `mod_1` and `key_space` because a mapper file replaces all default bindings) rather than trusting the default; the script waits for the PNG (`capture/*.png`, the
  newest) to appear and stop growing before it presses the key that ends the program, and falls back to the ffmpeg
  x11grab of `screenshot.sh` (checked 1:1 at `windowresolution = original`) if no PNG appears in 10 s. Files:
  `c/ports/dos/shots/<w>x<h>-<bpp>bpp.png` (10 files, about 50-200 KB each as PNG of mostly flat colour); the README
  shows the six the card asks for (8/16/32 at both sizes) and lists the 15/24 bpp ones.
- **How the screenshots are checked.** (1) The checksum above: the back buffer is byte-identical to `svfline`.
  (2) The capture against the dumped back buffer, pixel by pixel, after converting the dump: 32/24 bpp exact; 16/15
  bpp with DOSBox-X's own expansion (`v * 0x21 >> 2` for 5 bits, `v * 0x41 >> 4` for 6; **my call** to try exact
  first), and 8 bpp through the **intended** palette (8-bit DAC: as written; 6-bit: `v >> 2` expanded the same way).
  If the exact rule fails, the script **derives the expansion from the capture itself**: the background fills most of
  the frame and its 5/6-bit (or DAC) value is known, and the white and yellow ink pixels give the top of each channel,
  so the script fits each channel's expansion to {`v * 0x21 >> 2`, `v << 3 | v >> 2`, `v << 3`, `v * 255 / 31`} (and
  the 6-bit equivalents), re-checks exactly with the rule that fits, and records the rule in the README; only if no
  listed rule fits does it fall back to a tolerance of ±8 per channel for 5-bit and ±4 for 6-bit values (the largest
  error `v << 3` leaves) and says so. Either way a wrong pitch, a swapped channel, a stale LFB or a swapped palette
  entry cannot pass. (3) By
  eye, as the close criterion says: the reviewer opens the six PNGs and looks for the title with the right
  `{W}x{H} {BPP}`, the two 24 px lines, the scaled line, the yellow line, correct colours (no red/blue swap, no dark
  text, blue background), and identical layout across depths at one size.

## Measurements (`c/bench/bench.c -DBENCH_DOS`, `run-dos.sh`, `run-avr.sh`, `MEASUREMENTS.md`)

New DOS cases, mapped faces, one 40 code point line as today, 640 x 24 (16 px) and 640 x 32 (24 px) targets;
`run-dos.sh` copies `MARUS24.SVF` and `MARUS24A.SVF` next to `BENCH.EXE` as it copies the PAPLG pair:

| case | faces | target |
|---|---|---|
| `line40_<kind>` | PAPLG16 + PAPLG18 (18 px cells; the pair the "16 px" rows already use) | indexed8 (base 16, n 3), rgb555, rgb565, xrgb8888, rgb888 |
| `line40_24_<kind>` | MARUS24A (24 px, 2 bpp jamo set with ASCII; user, question 6) | the same five kinds |
| `line40_24m_<kind>` | MARUS24 (24 px, 1 bpp jamo set with ASCII): the 1 bpp word-path case | indexed8, rgb565, xrgb8888 |
| `line40_<kind>_bytes` | the 16 px pair, library built with `-DSVF_WORD_STORE=0` (a second BENCH.EXE) | indexed8, rgb555, rgb565 |
| `flush_WxH_<bpp>` | the example's dirty-row copy of a whole frame to the LFB (printed by `svfvesa.c` per run, collected by `vesa-shots.sh`, not in bench.c) | 8, 16, 32 at both sizes |

Each case carries its `svfline` checksum in `run-dos.sh` `SUMS` (the host build `-DBENCH_HOST` prints the C value;
the plan's step computes the same FNV-1a over `svfline.draw_target`'s buffer with the same fill and the two must agree
before the sum is recorded). Budget: the 16 ms DX2-66 line budget applies to every `line40_*` row (`BUDGETS`); the
24 px rows are expected over it on the DX-33 preset and the finding is recorded, not hidden. `MEASUREMENTS.md` gets a
"Packed kinds (VESA)" section with both presets, the before/after of RGB565 (the 2-pixel store is a change to an
existing kind), and the still-over table updated. Everything stays labelled emulated.

**Uno bench.** `run-avr.sh` builds with no `SVF_TARGETS` today, so the default 0x1FF would link the four new blits
into a program that has 944 B of flash to spare. It gets `-DSVF_TARGETS=0x1F` (the five kinds it has always
measured), its header comment says so, and the Uno fit line is re-recorded at that mask. The Pico bench is a
MONO_PAGE-only build and does not move; the ARMv6-M word-store decision belongs to t_47ca86d1's RGB565 rows (above),
not to this card.

## Size budget

- **P1/P2 (MONO_PAGE only) and P3 (RGB565 only): unchanged in intent**, since the new code is under bits they do not
  set and `SVF_WORD_STORE` is 0 on their architectures; the gate (Cortex-M0+ P1/P2 <= 8192 B) is re-run and
  `SIZES.md` re-measured. RGB565's shared `blit_rgb16` may move P3 by some tens of bytes either way; it is recorded,
  and with `-DSVF_WORD_STORE=1` once more so the ARM cost of the word path is on record.
- **P1\* (every kind) and P4 (everything) grow** by the four blits and two blend helpers: an estimate of 1.2-2.0 KB
  Thumb (INDEXED8 three loops with the max and word path ~400 B, `blit_rgb16` with its pair table ~350 B over today's
  `blit_rgb565`, XRGB8888 ~250 B, RGB888 ~250 B, `blend888` ~80 B); the plan measures after each kind. Neither row has
  a gate, and the gate stays on P1/P2 whatever P1\* becomes (user, question 7: closed).
- **`c/cross/probe.c`**: PROFILE 4 lists all nine kinds (else `--gc-sections` drops the new blits and P4 is
  under-counted); a new `PROFILE == 5` ("P5 VESA", **my call**) initialises and draws on the five packed kinds
  (INDEXED8, RGB555, RGB565, XRGB8888, RGB888), a streamed face with a block cache and scaling, the DOS example's
  calls; `build-all.sh` adds the object set `vesa -DSVF_TARGETS=0x1E8` (scaling in) and the row `P5`, so the number
  the DOS user pays is on record on DJGPP and the others.
- **DJGPP**: `SVFVESA.EXE` size reported by `build-all.sh --ports` next to `SVFDEMO.EXE`.

## Risks

- **Mode numbers and depths differ between the emulator and cards** (0x112 24 vs 32 bpp; some BIOSes report 16 bpp
  for 5/5/5). The example selects by masks, and RGB888 exists for that reason; still, the only hardware run here is
  DOSBox-X. A real-card run is a finding for later.
- **DOSBox-X's colour expansion** may not be the rule assumed; the capture check then derives the rule from the
  capture, and only as a last resort becomes tolerant (±8 for 5-bit, ±4 for 6-bit channels). The exact check is the
  checksum against `svfline`; the capture check exists to catch a wrong pitch, swapped channels, a swapped palette or
  a stale LFB, which a tolerance does not hide.
- **The MCU word-store decision depends on another card** (t_47ca86d1's RGB565 rows). If that card does not land,
  the default simply stays off on MCUs, which is the safe state; nothing here waits for it.
- **DPMI physical mapping** of a 3 MB LFB under CWSDPMI (DOSBox-X's built-in host) is routine; `memsize = 16` leaves
  room for the back buffer. If `__dpmi_physical_address_mapping` fails on a host, the program says so and exits to
  text mode: no bank-switched fallback.
- **The 2048-compile gate**: ~20 s on this host, 4 minutes on a one-core CI host. The user accepted it.
- **INDEXED8's max rule** makes text invisible over an index above the ramp. That is the GRAY8 behaviour the card
  asked for; the header states it, the example and the tests arrange the palette accordingly, and a caller with a
  bright UI index below text must place the text ramp above it.
- **Word stores cost code** in exactly the kinds the DOS user compiles; if DOSBox-X shows no instruction saving they
  are dropped from the measured rows and kept only where a row improves (the rule above), so the design does not
  depend on them. Off x86 they are off until measured.
- **`uint16_t stride`** caps 32 bpp targets at 16383 pixels wide: no VBE mode is wider, but a widened stride would be
  an API change for another card.

## What counts as done (the card's close criterion, measurable)

- `make -C c check` green with gcc and clang (ASan, UBSan, pointer-overflow), the 0x000..0x1FF compile gate included;
  every `TestTargets`/`TestBlitPaths`/new test above passing on the four kinds, byte for byte against `svfline`, with
  and without `SVF_WORD_STORE`.
- `c/cross/build-all.sh`: every toolchain OK; Cortex-M0+ P1/P2 text <= 8192 B with the new kinds masked out;
  `SIZES.md` updated with P5 and the P3 word-store row.
- `c/ports/dos/vesa-shots.sh` runs in DOSBox-X: ten PNGs, the six required ones in the README, checksums equal to
  `svfline`, the capture check passing, the images looked at.
- `MEASUREMENTS.md`: the rows above at both presets, emulated, with the before/after of RGB565 and the Uno fit at
  `0x1F`.

## Decisions taken (user, 2026-10-20)

1. INDEXED8 overlap is plain `max(existing, index)`, the GRAY8 rule; the background index must be below the ramp
   (documented, arranged by the example, tested with prefills below, inside and above the ramp, 0 and 255 included).
2. `index_levels = 1` follows `mono_threshold` (a threshold-index kind).
3. RGB555 reuses `fg565`/`bg565`, with the alias flag name; no API break.
4. XRGB8888 has one byte order (B G R X); no RGBA kind in this card.
5. The compile gate runs all 2048 masks, in parallel. (Superseded in review: the gate is the 0x000..0x1FF gate, the 512
   masks of the nine target bits with and without `SVF_NO_SCALE` plus the word-store jobs, 1038 jobs per compiler.)
6. The 24 px faces are MARUS24A and MARUS24.
7. If P1\* exceeds 8192 B the gate stays on P1/P2; the question is closed. Confirmed by the user on 2026-10-21: P1\* measured 8474 B (282 B over); the gate stays on P1/P2 (5674 B) and small targets choose their kinds through `SVF_TARGETS`.

No open questions remain for the user.

## Revision 1 (2026-10-20, after three reviews and the user's answers)

- INDEXED8: ramp-max-or-replace replaced by plain `max` (user 1); the word path is now load-max-store; prefill tests
  listed; `idx[]` sentinel wording fixed; level-0 pixels explicitly skipped.
- RGB555: the output expression includes bit 15 from fg; the default (`fg565 = 0xFFFF`) sets it; both states tested.
- Unsigned, 16-bit-safe arithmetic stated for the level formula, `blend888` and the word constants (AVR).
- `SVF_WORD_STORE`: word stores on x86/WASM by default, off elsewhere until the Pico/ESP32-C3 measurements say
  otherwise; in the compile gate; word tables built via `memcpy` from byte arrays (host-endian independent), per bpp.
- Tests: `LATER_CELL_KINDS`/`RGB16_KINDS` replace the `rgb565` name tests; `test_later_cell_lower_coverage` and the
  `check` assertion generalised; asymmetric 888 colours, two non-trivial ramps with fills, big-endian for both 16-bit
  kinds; `test_args.c`'s default-mask guard updated to 0x1FF; `svfdump-vesa` is 0x1E8; `svfdump-bytes`; `--misalign`
  shifts both guards.
- Gate: the `xargs -P` invocation and failure reporting spelled out.
- DOS example: `AX == 0x004F` after every call; mode list validated, copied out of `__tb` and capped at 256; `Lin*`
  fields only with VBE 3.0, plain fields with 2.0; `PhysBasePtr`/pitch validity; checked size arithmetic for pitch,
  mapping (page-granular limit), back buffer, dirty rows and every `movedata`; text mode restored with `INT 10h
  AX=0003h`; 4F09h entry order B G R pad and 6-bit fallback; mapping release failure ignored; one CLI syntax plus the
  no-argument 16 -> 8 -> 32 bpp sequence; one shared `vesa-lines.txt` and colour table for `svfvesa.c` and
  `vesa-shots.sh`; the oracle's buffer prefilled with the background; script quoting and DOS-safe paths; capture
  hotkey pinned by a mapper file, waits and ffmpeg fallback; `xvfb-run -a`; capture check against the intended
  palette, exact rule first.
- Bench: `run-dos.sh` copies the 24 px faces; `run-avr.sh` gets `-DSVF_TARGETS=0x1F`; `probe.c` P4 lists all kinds
  and P5 is defined.

## Revision 2 (2026-10-20, after the re-reviews)

- Run-ready handshake: `svfvesa.c` writes `SUM.TXT` (sum, DAC width, mode, pitch) and closes it before waiting for
  the key; `vesa-shots.sh` waits on that file with a 60 s timeout and fails loudly.
- VBE status: fatal only for 4F00h/4F01h/4F02h; 4F08h/4F09h failures take the 6-bit DAC and port fallbacks.
- Linear fields: `Lin*` used whenever filled for an LFB mode, whatever the VBE version; plain fields otherwise
  (covers 2.0 BIOSes that fill them and 3.0 BIOSes that report zero before the mode is set).
- Compile-gate job list: one compound token per job (`mask[:define...]`), `xargs -n 1`; no empty argument.
- `vesa-lines.txt` holds the colours, background and ramps as data (`[colours]`/`[lines]`), with one palette rule
  for both readers and a parser cross-check test; no prose-only colour table.
- The VBE parsing and size arithmetic are a pure C unit (`vbe_select.c`) tested on the host under the sanitizers
  with hostile input (`c/tests/test_vbe.c`): pointers near 1 MiB with the bounded word-by-word read, unterminated
  lists, zero/huge pitch, malformed blocks, every failed-call path; the mode list read now stops before 0x100000.
- Capture check: the expansion rule is derived from the capture when the first rule fails; the tolerance fallback is
  ±8 for 5-bit channels (covers `v << 3`), ±4 for 6-bit.
- MCU word stores: off in this card; the ARMv6-M decision uses t_47ca86d1's RGB565 rows (`syl_ga`, `screen32`,
  `aa_line12`, `aa_screen10` at `-Os`/`-O2`, the `blit_rgb565` profile share), ESP32-C3 its instruction-count bench
  if it lands; the Pico run is dropped from this card.
- Stale wording removed (the Uno bench no longer compiles the new kinds; width-limit test values corrected:
  16384/21846 refused, 16383/21845 accepted; 24 bpp 21846 added to `test-args`).
- The full `svf_target` struct is listed; open questions replaced by the decisions taken.

## Revision 3 (2026-10-20, last pass after the revision-2 re-reviews)

- `vbe_modes_copy` reads through a failure-capable `read_word(ctx, seg, off, out)` callback (DOS: `dosmemget`; the
  host tests: a 1 MiB-shaped image), stores into `modes[257]` so the 0xFFFF sentinel always fits, and returns the
  count; the status helper is `vbe_status(ax, fn)` with `VBE_FATAL`/`VBE_FALLBACK`; `vbe_mode_accept` returns reason
  codes.
- The 256-byte ModeInfo area at `__tb` is zeroed before every 4F01h; every selected field position (Lin\* or plain)
  is validated against its mask size and the depth, with overlap and sum checks, before use.
- `vesa-shots.sh` deletes `SUM.TXT`, `DUMP.RAW`, `OUT.TXT` and earlier captures before each launch and checks the
  `mode=` line (now `mode=0x<n> WxH BPPbpp pitch=<p>`) against the expected W/H/BPP; a stale or mismatched file fails
  the run.
- `vesa-lines.txt` parser rules: UTF-8 validation, 512-byte lines, exact field counts, trim rules, numeric ranges,
  at most 16 colours / 32 lines / 4 faces a line, duplicate-name and missing-background errors, face names
  restricted to bare DOS 8.3 `.SVF` names opened only in the faces directory (`/`, `\`, `:`, `..`, leading `.`
  refused); the script's own path check is per component and refuses `.`/`..`.
- Palette formula as the integer expression `(bg * (n - k) + fg * k + n / 2) / n` per channel; the host tool is
  `c/tests/vesa-lines-dump --print-table`; both readers are tested on the same malformed files.
- Ruling recorded: the implementation plan is written after this design is approved (SOL's "named plan absent" is
  expected, not a gap).

## Revision 4 (2026-10-20, correctness residuals from the final checks; the last design revision)

- Field checks: apply to direct-colour modes (MemoryModel 6) and to channels with mask size > 0 only; 8 bpp palette
  modes skip them; the 15-as-16 rule applies to the sum check too. DOSBox-X 2026.08.31's M_LIN15 report
  (`BitsPerPixel 15`, R5@10 G5@5 B5@0, reserved 1@15; `src/ints/int10_vesa.cpp` 358-374) is an accepted test case.
- Arithmetic widths per expression: INDEXED8 level and the 5-bit blends fit 16 bits; `blend888` and the palette
  formula are `uint32_t` (their sums reach 65152, past a 16-bit signed `int`; the earlier 130177 was wrong — the weights sum to 255); `c/tests/test_blend16.c` evaluates every expression with 16-bit
  intermediates on the host, as the 16-bit-int test build note says.
- A 5/5/5 mode reported as `BitsPerPixel 16` is the logical 15 bpp: `SUM.TXT`'s `mode=` line carries the requested
  logical depth (plus `bits=<b>` for the record) and `vesa-shots.sh` compares that.
- Output directory: no symlink in OUT or its prefixes; OUT must be absent, empty or marked by an earlier run before
  anything is deleted; face entries resolved with `realpath` and verified inside the faces directory.
- Parser: boundary tests on both sides (16/17 colours, 32/33 lines, 4/5 faces, 512/513-byte lines, empty text vs
  empty other field); the one trim rule stated once and tested; the sentinel guarantee of `vbe_modes_copy` holds
  for non-negative returns only.
- Wording: `modes[257]` everywhere; the header names revision 4.
