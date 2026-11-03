# VESA 2.0 Packed Output Kinds and DOS VBE Example Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the four VBE 2.0 packed target kinds (INDEXED8, RGB555, XRGB8888, RGB888), each byte-identical to
`tools/svfline.py` and each behind its own `SVF_TARGETS` bit, with x86/WASM word stores, and a DJGPP example that
finds a VBE 2.0 LFB mode by layout, draws through a back buffer and is held to the reference by checksum and
DOSBox-X captures.

**Architecture:** `svfline.py` gains the kinds first (the oracle), then `svf_draw.c` gains one `blit_*` per kind
under its mask bit, RGB565 and RGB555 sharing `blit_rgb16`; word stores are `memcpy` of 2/4 bytes behind
`SVF_WORD_STORE` (x86/WASM default 1, every MCU 0). The DOS example is split into a pure, host-tested unit
(`vbe_select.c`: mode list, layout validation, size arithmetic, palette entry), a shared text table parser
(`vesa_lines.c`, with a Python twin) and the thin DPMI wrapper `svfvesa.c`; `vesa-shots.sh` runs it in DOSBox-X and
checks the back-buffer checksum against `svfline` and the capture against the dump.

**Tech Stack:** C99 (`-std=c99 -Wall -Wextra -Werror`; DJGPP gcc 12.2.0 `-std=gnu99` for the DOS programs), make,
sh; Python 3 unittest (`tools/test_c_renderer.py`, PIL for captures); DOSBox-X 2026.08.31 (`/usr/bin/dosbox-x`),
xvfb-run, xdotool, ffmpeg; cross toolchains under `~/opt` (`c/cross/build-all.sh`, `c/bench/run-dos.sh`).

**Spec:** `docs/superpowers/specs/2026-10-20-vesa-packed-kinds-design.md` at commit 5b93466 (card t_6ab9ec2d). Read
it first; every rule below is argued from it. Existing patterns: `docs/superpowers/plans/2026-10-20-blit-fast-paths.md`
(the blit shape, the sweeps), `c/include/svf.h` "A drawing target", `tools/svfline.py` `Target.put`.

## Global Constraints

- Library (`c/src`, `c/include`): C99; only `<stdint.h>`, `<stddef.h>`, `<string.h>`; no static data, no `malloc`
  (`c/check.sh` no-malloc), no pointer formed before a row start (row pointer `t->buf + (size_t)(y + row) * stride`,
  index `k * (size_t)(x + col)`), no pointer cast for a word access (`memcpy` only), no unrolling.
- All blend/level arithmetic unsigned; `blend888` and the palette formula in `uint32_t`; never an intermediate from
  promoted `uint8_t` operands above 32767 (AVR's 16-bit `int`). Word constants `(uint32_t)top * 0x01010101u`.
- Every kind, old and new, byte-identical to `svfline` on every sweep, with `SVF_WORD_STORE` 1 and 0; no byte outside
  the clip or in a row's padding written; ASan/UBSan/pointer-overflow clean with gcc and clang at every `--misalign`.
- `SVF_TARGETS` default `0x1FFu`; bit i is kind i; a kind masked out is not in the object code and is `SVF_E_ARG`.
- `SVF_WORD_STORE` default 1 only under `__i386__`, `__x86_64__`, `__wasm__`; 0 everywhere else; this plan does not
  change any MCU default (t_47ca86d1 decides later from its RGB565 rows).
- Cortex-M0+ P1/P2 text <= 8192 B after every library task (`c/cross/build-all.sh`), recorded in each commit message.
- No fast mode, no planar modes, no VBE 1.2 banked fallback, no change to the walker, `svf_glyph`/`svf_compose`,
  the syllable cache, `svf_scale.c` or `svfdemo.c`.
- The DOS example never selects a mode by number: geometry and channel layout only.
- Scripts quote every argument, use no `eval`, and verify output paths before deleting anything.
- Numbers in docs are emulated and say so; a missed budget is recorded with its number.
- `make -C c check` and `python3 -m unittest discover -s tools -p 'test_*.py'` green after every task.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. An INDEXED8 target with `index_levels = 1` and `mono_threshold = 0`: coverage 1 must set the index (0 counts as 1,
   the mono rule), coverage 0 never — Task 2 `test_indexed8_threshold_form` at every value of `THRESHOLDS`, 0 included.
2. A `vesa-lines.txt` line of exactly 512 bytes whose 512th byte is the newline, with multi-byte UTF-8 in the text:
   accepted by both readers with the same text; 513 refused with that line's number — Task 8 `test_vesa_lines_limits`.
3. A VBE block whose `Lin*` fields are filled for red and green only (`LinBlueMaskSize 0`): the linear set must not
   be chosen half-way; the plain fields are used — Task 7 `test_vbe.c` case `lin_partial`.
4. `vbe_modes_copy` with `VideoModePtr` at `0x100000 - 2`: exactly one word may be read, and if it is not 0xFFFF the
   count is 1 with the sentinel stored — Task 7 case `ptr_last_word`.
5. A 1 bpp cell whose last source byte has padding bits set past `cell_w` (pad bits are 0 by `svf__mask_cell`, but a
   scaled or synthetic cell may not be): the INDEXED8/RGB16 word path must take its nibble/pair groups only from
   columns `< c1` — Task 6 `test_word_path_cut_edges` with `pad1`'s 19-pixel rows (pitch 3, 5 pad bits).

---

## File structure

```
c/include/svf.h                 kinds 5..8, mask bits 0x20..0x100, SVF_TF_RGB16_BIGENDIAN, SVF_WORD_STORE, new fields, rules
c/src/svf_draw.c                target_ok cases; blend555/blend888/index level; blit_indexed8, blit_rgb16 (565+555), blit_xrgb8888, blit_rgb888
tools/svfline.py                TARGET_KINDS + 4; index_level, blend555, blend888; Target fields; LATER_CELL_KINDS, RGB16_KINDS
tools/test_c_renderer.py        TargetMixin generalised; TestReferenceFormulas; per-kind tests in TestBlitPaths; TestTargetsSwitch; TestVesaLines
c/tests/svfdump.c               kind names, --index-base/--index-levels/--fg888/--bg888/--misalign
c/tests/test_args.c             guard 0x1FFu; new-kind argument cases; left_out for the page and vesa builds
c/tests/test_blend16.c          16-bit promotion model of every formula (host, make check)
c/tests/test_vbe.c              hostile-input tests of vbe_select.c (host, sanitizers)
c/tests/vesa_lines_dump.c       --print-table FILE: parsed table + 256-entry palette as text
c/Makefile                      test-blend16, test-vbe, vesa-lines-dump, svfdump-vesa, svfdump-bytes, test-args-vesa
c/check.sh                      targets_ok: 0x000..0x1FF x {scale, noscale} x {gcc, clang} + word-store records, xargs -P
c/cross/probe.c, build-all.sh   PROFILE 4 all nine kinds; PROFILE 5 (P5 VESA, -DSVF_TARGETS=0x1E8); P3 word-store row; --ports SVFVESA.EXE
c/ports/dos/vbe_select.[ch]     pure: vbe_modes_copy, vbe_mode_accept, vbe_status, vbe_palette_entry, vbe_copy_ok
c/ports/dos/vesa_lines.[ch]     pure: vl_parse, vl_palette, vl_substitute (DJGPP and host)
c/ports/dos/svfvesa.c           DPMI/VBE wrapper: query, map, back buffer, dirty rows, SUM.TXT, DUMP
c/ports/dos/vesa-lines.txt      [colours] and [lines] (spec text verbatim)
c/ports/dos/vesa-shots.sh       DOSBox-X runs, captures, checksum and capture checks; shots/*.png
c/ports/dos/vesa_check.py       capture vs dump check (exact, derived rule, tolerance fallback)
tools/vesa_lines.py             Python twin of vesa_lines.c + expected checksum (--print-table, --expect)
c/bench/bench.c, run-dos.sh, run-avr.sh, MEASUREMENTS.md, c/cross/SIZES.md
```

Faces (`svf/dos`): `PAPLG16`+`PAPLG18` (2 bpp, 18 px cells), `MARUS24A` (24 px, 2 bpp jamo), `MARUS24` (24 px,
1 bpp jamo), the sweep faces of the blit plan (`SMYJO18`, `NEODG16D`, `NGOTB14`, `GBA17BX1`), the synthetic
`--bpp8`, `--marks`, `pad1` and overlap faces `TestBlitPaths` already builds.

---

### Task 1: Reference and API: svfline kinds, svf.h declarations, svfdump options, the 16-bit formula test

**Files:**
- Modify: `tools/svfline.py` (TARGET_KINDS, `target_row_bytes`, `Target`, docstring "Targets"), `c/include/svf.h:243-294`,
  `c/src/svf_draw.c:388-409` (init defaults only), `c/tests/svfdump.c:45-53,356-361,445-525,600-730`,
  `c/tests/test_args.c:160,351`, `c/Makefile`, `c/check.sh:11-13` (comment only), `tools/test_c_renderer.py:1364-1420`
- Create: `c/tests/test_blend16.c`
- Test: `tools/test_c_renderer.py` (`TestReferenceFormulas`, `TestBlend16`)

**Interfaces — Produces:**
```python
# svfline.py
TARGET_KINDS = ("gray8", "mono-page", "mono-row", "rgb565", "cb", "indexed8", "rgb555", "xrgb8888", "rgb888")
LATER_CELL_KINDS = {"rgb565", "rgb555", "xrgb8888", "rgb888"}
RGB16_KINDS = {"rgb565", "rgb555"}
def target_row_bytes(kind, w)   # indexed8 w, rgb555 2*w, xrgb8888 4*w, rgb888 3*w
def index_level(cov, levels, threshold)  # levels >= 2: (cov*levels + 127)//255; 1: 1 if cov >= max(threshold,1) else 0
def blend555(fg, bg, cov)       # low 15 bits, channels (10,31) (5,31) (0,31), same arithmetic as blend565
def blend888(fg, bg, cov)       # 0xRRGGBB, per 8-bit channel (bg*(255-cov) + fg*cov + 127)//255
class Target: __init__(..., big_endian=False, index_base=0, index_levels=255, fg888=0xFFFFFF, bg888=0)
# Target.put: indexed8 L = index_level(cov, n, threshold); L == 0 untouched; else b[i] = max(b[i], base + L)
#             rgb555  (fg565 & 0x8000) | blend555(fg565 & 0x7FFF, bg565 & 0x7FFF, cov), 2 bytes LE (BE with flag)
#             xrgb8888 bytes B, G, R, (fg888 >> 24) & 0xFF;  rgb888 bytes B, G, R
```
```c
/* svf.h: the enum, SVF_TARGET_INDEXED8..RGB888, SVF_TARGETS 0x1FFu, SVF_TF_RGB16_BIGENDIAN, SVF_WORD_STORE and the
 * four struct fields exactly as the spec's "Public API additions" block; the rules paragraph gains one bullet per
 * kind (the spec's "Pixel rules per kind"), the INDEXED8 max consequence, the stride limits 16383 / 21845. */
/* svf_target_init also sets fg888 = 0x00FFFFFF, bg888 = 0, index_base = 0, index_levels = 255. */
```
`svfdump`: `kind_names[9]` in enum order; `--index-base=N`, `--index-levels=N` (0..255), `--fg888=N`, `--bg888=N`
(0..0xFFFFFFFF, `strtoul`), `--misalign=K` (0..3); `draw_line` rows for the four kinds (w, 2w, 4w, 3w) and the
allocation `GUARD + K + blen + GUARD` with the buffer at `mem + GUARD + K` and both guards checked around it.
`TargetMixin.opts_of/target/expect` take `index_base, index_levels, fg888, bg888, misalign` and pass them through.
`SWEEP_KINDS = svfline.TARGET_KINDS[:5]` at module level: every sweep that iterates kinds uses it; each kind task
appends its kind, Task 4 replaces it by `svfline.TARGET_KINDS`. `test_args.c` guards become `0x1FFu`. In this task
the library still refuses the four kinds (`target_ok` has no case for them); the header documents them.

`c/tests/test_blend16.c` (no library link; `make test-blend16`, run by `check.sh` before the Python run): for each
formula a `uint32_t` reference and a 16-bit model copy; a `MODEL` macro family evaluates every intermediate as
`uint16_t` where the source expression is `unsigned`/`uint32_t`, and as `int16_t` with an overflow check where the
spec forbids promoted `uint8_t` operands; the test fails on any model/reference mismatch or any `int16_t`
intermediate above 32767. Loops: level `c, n` in 0..255 x 1..255 (threshold form at n = 1 over 0..255);
`blend565`/`blend555` over every channel value and coverage; `blend888` over every `c_bg, c_fg, c`; palette
`(bg * (n - k) + fg * k + n / 2) / n` over `n` 1..255, `k` 0..n, `bg, fg` 0..255 (fits: 255 * 255 + 127). Asserts the
observed maxima: level and 8-bit blend and palette 65152, 5/6-bit blend 16192. Prints `blend16: OK` and exits 0.

- [ ] **Step 1: Write the failing tests** `TestReferenceFormulas` (pure Python, no C): `test_index_level_values`
  (n 3: 85 -> 1, 170 -> 2, 255 -> 3, 42 -> 0, 43 -> 1; n 255: identity; n 1 thr 128: 127 -> 0, 128 -> 1; n 1 thr 0:
  0 -> 0, 1 -> 1), `test_blend555_equals_blend565_r_and_b` over every fg, bg channel value and cov (R and B of
  `blend565(fg << 1 | ..., ...)` compared channel-wise), `test_blend888_bounds` (cov 0 -> bg, 255 -> fg, 128 of
  0xFF/0x00 -> 0x80), `test_put_byte_orders` (one `put` per kind on a 1 x 1 target: xrgb8888 fg 0x8C123456 cov 255 ->
  `56 34 12 8C`; rgb888 -> `56 34 12`; rgb555 fg 0xFFFF -> bit 15 set, fg 0x7FFF -> clear, big-endian swapped;
  indexed8 base 16 n 3 cov 170 on fill 0 -> 18, on fill 200 -> 200). `TestBlend16.test_runs`: `make test-blend16`
  and the program exits 0 printing `blend16: OK`.
- [ ] **Step 2: Run** `python3 -m unittest tools.test_c_renderer -k TestReferenceFormulas -k TestBlend16` -> FAIL
  (`index_level` undefined; no make target).
- [ ] **Step 3: Implement** svfline.py, svf.h, the init defaults, svfdump options, the mixin, `SWEEP_KINDS`,
  `test_args.c` guards, `test_blend16.c`, the Makefile targets (`test-blend16` under `$(WARN) $(ASAN)`; `check` runs
  `$(O)/test-blend16` before `check.sh`).
- [ ] **Step 4: Run** the two classes -> PASS; `python3 -m unittest tools.test_c_renderer` -> PASS (the old sweeps
  on `SWEEP_KINDS`); `make -C c check` -> `blend16: OK`, `no-malloc: OK`, `asan: OK`, `clang: OK`;
  `c/cross/build-all.sh` -> every toolchain OK, P1/P2 unchanged (5674).
- [ ] **Step 5: Commit** `c: VESA packed kinds declared (svf.h, svfline reference, svfdump options, 16-bit formula test)`.

### Task 2: SVF_T_INDEXED8 (byte loops)

**Files:**
- Modify: `c/src/svf_draw.c` (`target_ok`, a `blit_indexed8` under `#if SVF_TARGETS & SVF_TARGET_INDEXED8`, the
  dispatcher), `c/tests/test_args.c` (`lines()`), `tools/test_c_renderer.py` (`SWEEP_KINDS += ("indexed8",)`,
  `TestBlitPaths`), `c/cross/probe.c:92` (kinds table grows per task so P4 links the kind)
- Test: `tools/test_c_renderer.py`

**Interfaces — Produces (static in svf_draw.c):**
```c
static uint8_t index_level(uint8_t cov, uint8_t levels, uint8_t thr);  /* spec "Level"; n = 1: cov >= (thr ? thr : 1) */
static void blit_indexed8(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
```
`target_ok`: `row = w`, and `index_levels >= 1 && (unsigned)index_base + index_levels <= 255`. Per cell:
`top = base + n`, 2 bpp `idx[4]` (`idx[0] = 0`, `idx[j] = L(j * 85) ? base + L : 0`); 1 bpp: set bit -> `if (top >
dst[i]) dst[i] = top`; 2 bpp: skip byte 0, per pixel skip `idx[lv] == 0`, byte max; 8 bpp: `L = index_level(v)`,
skip 0, byte max. This task writes the byte loops only; Task 6 adds the word path.

- [ ] **Step 1: Write the failing tests** in `TestBlitPaths`: `test_indexed8_defaults_equal_gray8` (every chain of
  `test_negative_x_on_row_zero`, `target_places`, fill 0: the indexed8 bytes equal the gray8 bytes);
  `test_indexed8_ramp_levels` (2 bpp faces, base 16 n 3, fill 0: every drawn byte in {17, 18, 19} and equals
  `base + level`); `test_indexed8_threshold_form` (n 1, every `THRESHOLDS` value, 2 bpp and 8 bpp faces: the bytes
  unpacked equal the mono-row bits of the same line); `test_indexed8_max_rule` (`HLHHL` on the overlap faces, base
  16 n 3 and base 64 n 63, fills 0, base - 1, base + 1, base + n, base + n + 1, 255: `out == draw_target ==
  to_target`; fill 255 leaves the buffer all 255); `test_indexed8_level0_untouched` (8 bpp face, n 3: every pixel
  of coverage 1..42 stays fill); `test_indexed8_refused` (`--index-levels=0` and base 200 levels 56: exit 2,
  `SVF_E_ARG`, buffer fill). `test_args.c` `lines()`: `index_levels 0` and `index_base 200 + 56` refused by
  `svf_draw_utf8` (edited after a valid `svf_target_init`). The sweeps gain the kind through `SWEEP_KINDS` with the
  spec's defaults: ramps `(16, 3)` and `(64, 63)` with fills 0, base - 1, base + 1, and `(0, 255)` once.
- [ ] **Step 2: Run** `-k indexed8` -> FAIL (exit 2, the kind is refused).
- [ ] **Step 3: Implement** `index_level`, `blit_indexed8`, the `target_ok` case, the dispatcher case, the
  `test_args` cases, `probe.c` kinds.
- [ ] **Step 4: Run** `python3 -m unittest tools.test_c_renderer` -> PASS; `make -C c check` -> OK;
  `c/cross/build-all.sh` -> OK, P1/P2 5674, record P1*/P4 Cortex-M0+ deltas in the commit message.
- [ ] **Step 5: Commit** `c: SVF_T_INDEXED8 (palette index ramp, threshold form, GRAY8 max rule)`.

### Task 3: SVF_T_RGB555 and the shared `blit_rgb16`

**Files:**
- Modify: `c/src/svf_draw.c:426-437,513-577` (blend555; `blit_rgb565` becomes `blit_rgb16` with a caller per
  kind), `tools/test_c_renderer.py` (`SWEEP_KINDS += ("rgb555",)`; every `kind == "rgb565"` test becomes `kind in
  svfline.LATER_CELL_KINDS`, every big-endian loop `kind in svfline.RGB16_KINDS`), `c/tests/test_args.c`, `c/cross/probe.c`
- Test: `tools/test_c_renderer.py`

**Interfaces — Produces:**
```c
#if SVF_TARGETS & SVF_TARGET_RGB555
static uint16_t blend555(uint16_t fg, uint16_t bg, uint8_t cov);   /* low 15 bits; caller ORs fg & 0x8000 */
#endif
#if SVF_TARGETS & (SVF_TARGET_RGB565 | SVF_TARGET_RGB555)
/* pix[j]: the two bytes of level j (j = 3 the 1 bpp ink) in the target's byte order; blend(fg, bg, cov) the 8 bpp
 * per-pixel colour (called per covered 8 bpp pixel only; 1/2 bpp use pix). */
static void blit_rgb16(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y,
                       const uint8_t pix[4][2], uint16_t (*blend)(uint16_t, uint16_t, uint8_t), uint16_t or_mask);
#endif
```
The RGB565 caller passes `blend565`, `or_mask 0`; the RGB555 caller `blend555`, `or_mask = fg565 & 0x8000`, and
masks fg/bg to 15 bits when building `pix` (the 8 bpp pixel is `(blend(fg & 0x7FFF, bg & 0x7FFF, v) | or_mask)`).
`target_ok` RGB555: `row = 2w`. Byte-pair loops as today; the word path is Task 6.

- [ ] **Step 1: Write the failing tests**: `test_rgb555_bit15_follows_fg` (fg 0xFFFF and 0x7FFF, bg 0x0010, 2 bpp
  face: every drawn pixel's bit 15 equals fg's, both byte orders); `test_rgb555_channel_order` (the RGB565
  wide-cell test of line 1920 duplicated for rgb555, fg 0x1234 bg 0xABCD, both orders); `test_later_cell_lower_coverage`
  generalised: for every `LATER_CELL_KINDS` kind `cells != line` and the probe pixel equals the kind's later-cell
  bytes (555: `blend555(0x1234 & 0x7FFF, 0xABCD & 0x7FFF, low) | (0x1234 & 0x8000)`); `test_rgb565_unchanged`:
  the existing RGB565 sweeps (unchanged code paths now through `blit_rgb16`) still pass — no new test, the step
  below runs them. `test_args.c`: an RGB555 target with stride `2w - 1` refused.
- [ ] **Step 2: Run** `-k rgb555` -> FAIL.
- [ ] **Step 3: Implement** `blend555`, `blit_rgb16`, the two callers, `target_ok`, the dispatcher, `probe.c`.
- [ ] **Step 4: Run** the whole file -> PASS (`TestTargets`, `TestBlitPaths`, `TestScale` on rgb565 prove the
  refactor); `make -C c check` -> OK; `c/cross/build-all.sh` -> P1/P2 5674; record Cortex-M0+ P3 before/after in
  the commit message.
- [ ] **Step 5: Commit** `c: SVF_T_RGB555; RGB565 and RGB555 share blit_rgb16 (P3 X -> Y B)`.

### Task 4: SVF_T_XRGB8888, SVF_T_RGB888 and `blend888`

**Files:**
- Modify: `c/src/svf_draw.c`, `tools/test_c_renderer.py` (`SWEEP_KINDS` deleted: sweeps iterate
  `svfline.TARGET_KINDS`), `c/tests/test_args.c`, `c/cross/probe.c`
- Test: `tools/test_c_renderer.py`

**Interfaces — Produces:**
```c
#if SVF_TARGETS & (SVF_TARGET_XRGB8888 | SVF_TARGET_RGB888)
static uint32_t blend888(uint32_t fg, uint32_t bg, uint8_t cov);  /* 0x00RRGGBB; each channel in uint32_t */
#endif
static void blit_xrgb8888(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
static void blit_rgb888(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y);
```
Per cell `px32[4][4]` = `B, G, R, fg888 >> 24` of level j (`px24[4][3]` without X); 1/2 bpp copy the level's bytes
(`memcpy(dst + i, px32[lv], 4)` — on every architecture: 4 bytes is one pixel, not a packing), 8 bpp blend per
pixel. `target_ok`: `row = 4w` / `3w` in `uint32_t`; a width whose row exceeds 65535 fails `stride >= row` on its own.

- [ ] **Step 1: Write the failing tests**: `test_888_byte_order` (fg 0x8C123456 bg 0x00ABCDEF on `HL`, 1 bpp face:
  xrgb8888 ink pixel `56 34 12 8C`, rgb888 `56 34 12`; X 0x00 with fg 0x00123456); `test_888_padding_untouched`
  (stride + 3 and + 5: every padding byte stays fill); `test_888_width_limits` (xrgb8888 w 16384 refused, 16383
  accepted with stride 65532; rgb888 21846 refused, 21845 accepted with stride 65535; h 1); the later-cell probe of
  Task 3 extended to the two kinds (`blend888` bytes in B G R (X) order). `test_args.c`: 32 bpp width 16384 and
  24 bpp 21846 refused, NULL buf, stride short by one.
- [ ] **Step 2: Run** `-k 888` -> FAIL.
- [ ] **Step 3: Implement** `blend888`, the two blits, `target_ok`, the dispatcher, `probe.c` (all nine kinds in
  PROFILE 4), delete `SWEEP_KINDS`.
- [ ] **Step 4: Run** the whole file -> PASS; `make -C c check` -> OK; `c/cross/build-all.sh` -> OK, P1/P2 5674;
  P1*/P4 deltas in the commit message.
- [ ] **Step 5: Commit** `c: SVF_T_XRGB8888 and SVF_T_RGB888 (blend888, B G R X order)`.

### Task 5: Mask builds, the 2048-compile gate, P5 size profile

**Files:**
- Modify: `c/check.sh:40-56`, `c/Makefile` (`svfdump-vesa` `-DSVF_TARGETS=0x1E8`, `test-args-vesa` the same mask),
  `c/tests/test_args.c` (`left_out` generalised), `c/cross/probe.c` (`PROFILE == 5`), `c/cross/build-all.sh:82-120`
  (object set `vesa -DSVF_TARGETS=0x1E8`, profile 5, the P3 `-DSVF_WORD_STORE=1` row labelled `P3w`), `c/cross/SIZES.md`,
  `tools/test_c_renderer.py` (`build()` targets, `TestTargetsSwitch`), `c/bench/run-avr.sh:24-26` (`-DSVF_TARGETS=0x1F`
  and its header comment)
- Test: `tools/test_c_renderer.py`

**Interfaces — Produces:** `check.sh targets_ok CC`: writes `$OUT/jobs` with one token per job (`0x000` ..
`0x1FF`, each also `:-DSVF_NO_SCALE`; `0x1FF`, `0x1E8`, `0x008`, `0x020`, `0x040`, `0x080`, `0x100` each with
`:-DSVF_WORD_STORE=0` and `:-DSVF_WORD_STORE=1`: 1038 records a compiler), then
`xargs -P "$(nproc 2>/dev/null || echo 1)" -n 1 sh -c '<split on :, compile, on failure print "targets: FAIL: $1"
and the compiler output; exit 1>' "$CC"`; `xargs`'s exit status fails the gate. `probe.c` PROFILE 5: a streamed
face with a block cache, scale 3/2, draws on INDEXED8, RGB555, RGB565, XRGB8888, RGB888 (the DOS example's calls).
`test_args.c`: `#if SVF_TARGETS == 0x1FFu` -> `lines()`; `#elif SVF_TARGETS == 0x02u || SVF_TARGETS == 0x1E8u` ->
`left_out()` that refuses every kind not in the mask (a table of the nine kinds, `SVF_TARGETS & (1u << k)`) and
draws on one kept kind as the control.

- [ ] **Step 1: Write the failing tests**: `TestTargetsSwitch.test_page_refuses_new_kinds` (svfdump-page: the four
  new kinds exit 2 `SVF_E_ARG`, buffer fill); `test_vesa_build_matches_default` (svfdump-vesa: the five packed
  kinds draw the same bytes as the default build on `LINE_TEXTS[0]` at `target_places`, and gray8, mono-page,
  mono-row, cb exit 2); `test_args_vesa` (the `test-args-vesa` program exits 0). `TestCheckScript.test_targets_jobs`:
  a dry-run flag `CHECK_LIST_ONLY=1` makes `targets_ok` write the job list and exit: 1038 lines, none empty, none
  with whitespace, `0x1E8:-DSVF_WORD_STORE=1` present.
- [ ] **Step 2: Run** `-k TestTargetsSwitch -k test_targets_jobs` -> FAIL.
- [ ] **Step 3: Implement** the Makefile targets, `left_out`, `check.sh`, `probe.c` P5, `build-all.sh`, `run-avr.sh`.
- [ ] **Step 4: Run** `make -C c check` -> `targets: OK gcc`, `targets: OK <clang>` (note the wall time: ~20 s
  parallel), rest OK; `c/cross/build-all.sh` -> every toolchain OK, P1/P2 <= 8192 with the kinds masked out, rows
  P5 and P3w present; `c/bench/run-avr.sh` -> checksums `ok`, fit line at `0x1F`. Paste the size table into
  `SIZES.md` with the date, P5 and P3/P3w findings, and the P1*/P4 growth per kind from the Task 2-4 commit messages.
- [ ] **Step 5: Commit** `c: SVF_TARGETS gate over 0x000..0x1FF in parallel; P5 VESA profile; svfdump-vesa; Uno bench at 0x1F`.

### Task 6: Word stores behind SVF_WORD_STORE (INDEXED8 nibbles, RGB16 pairs)

**Files:**
- Modify: `c/src/svf_draw.c` (`blit_indexed8`, `blit_rgb16`), `c/Makefile` (`svfdump-bytes`: ASan build with
  `-DSVF_WORD_STORE=0`), `tools/test_c_renderer.py` (`TestBlitPaths` and `TestWordStores`)
- Test: `tools/test_c_renderer.py`

*Task 10: the 1 bpp nibble word path was removed (measured 4.7 % slower than the byte loops on the emulated
  486DX2-66, c/bench/MEASUREMENTS.md); the 2 bpp path stays.*

**Interfaces — Produces:** inside `#if SVF_WORD_STORE`: INDEXED8 1 bpp: per source byte, each nibble `0xF` whose 4
columns are inside `[c0, c1)`: `memcpy(&w, dst + i, 4)`, per byte max against `top`, `memcpy(dst + i, &w, 4)`; any
other nibble per bit. 2 bpp: a byte `0xFF` inside the cut takes the same path; else per pixel through `idx[]`.
RGB16: per cell `pair[4][4][4]` (level a, level b -> the 4 bytes of `pix[a]`, `pix[b]`), 1 bpp: each 2-bit group
`11` inside the cut one `memcpy(dst + i, pair[3][3], 4)`, a lone bit a 2-byte copy; 2 bpp: the high and the low pair
of a byte, both levels non-zero and inside the cut -> `pair[a][b]`, else the non-zero one(s) as 2 bytes. 8 bpp
unchanged. `#else` the Task 2/3 loops. The first and last source byte of a row (where a group may cross `c0` or
`c1`) fall back to the byte loop. XRGB8888/RGB888 are unchanged (one pixel is one store).

- [ ] **Step 1: Write the failing tests** `TestWordStores`: `test_misalign_every_phase` (indexed8, rgb565, rgb555,
  xrgb8888, rgb888; `--misalign` 1..3; x in `PHASE_X`; chains `[SMYJO18]`, `[NGOTB14]`, `[MARUS24]`, `[bpp8]`;
  stride + 3: `check` passes, no sanitizer line); `test_word_path_cut_edges` (`pad1` and a 2 bpp all-level-3 face:
  clip x0 in 0..8 and x1 in w-8..w at every column mod 4 (indexed8) and mod 2 (rgb16), x in (-3, 0, 1, 2, 3, 5),
  bytes outside the clip stay fill); `test_narrow_targets` (w 1, 2, 3 on every packed kind); `test_bytes_build`
  (every `TestBlitPaths`/`TestWordStores` draw repeated with `exe_name="svfdump-bytes"`: the byte-loop build gives
  the same bytes — implemented as a class attribute `EXE` the mixin reads, the class subclassed once with
  `EXE = "svfdump-bytes"`). The tests pass against the byte loops: they are the oracle for the word paths; run
  them first (`-k TestWordStores` -> PASS on the Task 5 tree) so a later failure is this task's.
- [ ] **Step 2: Implement** the word paths and the Makefile target.
- [ ] **Step 3: Run** the whole file -> PASS; `make -C c check` -> OK (gcc and clang, every misalign);
  `c/cross/build-all.sh` -> P1/P2/P3 unchanged (the switch is 0 off x86/WASM), P3w and P5 recorded; a one-off
  mutation (not committed): drop the `inside the cut` test of the INDEXED8 nibble path -> `test_word_path_cut_edges`
  FAILS; revert; note it in the commit message.
- [ ] **Step 4: Commit** `c: word stores (4 px INDEXED8 load-max-store, 2 px RGB16 pairs) behind SVF_WORD_STORE on x86/WASM`.

### Task 7: `vbe_select.c`: the pure VBE unit and its hostile tests

**Files:**
- Create: `c/ports/dos/vbe_select.h`, `c/ports/dos/vbe_select.c`, `c/tests/test_vbe.c`
- Modify: `c/Makefile` (`test-vbe` under `$(WARN) $(ASAN) -I ports/dos`; `check` runs it), `c/check.sh` (no change: the
  Makefile runs it before `check.sh`)
- Test: `c/tests/test_vbe.c` (`TestVbe.test_runs` in `tools/test_c_renderer.py` runs the binary, exit 0)

**Interfaces — Produces (`vbe_select.h`, C99, `<stdint.h>` only):**
```c
enum { VBE_OK = 0, VBE_FATAL = -1, VBE_FALLBACK = -2,            /* vbe_status */
       VBE_R_BAD_PTR = -10, VBE_R_READ = -11,                       /* vbe_modes_copy */
       VBE_R_UNSUPPORTED = -20, VBE_R_NOT_GRAPHICS = -21, VBE_R_NO_LFB = -22, VBE_R_RESOLUTION = -23,
       VBE_R_NO_PHYS = -24, VBE_R_MODEL = -25, VBE_R_LAYOUT = -26, VBE_R_DEPTH = -27, VBE_R_PITCH = -28,
       VBE_R_RANGE = -29, VBE_R_TOO_BIG = -30 };                     /* vbe_mode_accept */
typedef struct { uint16_t mode_bits; unsigned depth /* 8 15 16 24 32, logical */, bytes_pp, bits /* BitsPerPixel */;
                 uint32_t pitch, phys_base, lfb_size, map_size, buf_size; } vbe_mode;
typedef int (*vbe_read_word_fn)(void *ctx, uint32_t seg, uint32_t off, uint16_t *out);
int vbe_modes_copy(const uint8_t block[512], vbe_read_word_fn read_word, void *ctx, uint16_t modes[257]);
int vbe_mode_accept(const uint8_t info[256], unsigned vbe_version, unsigned w, unsigned h, unsigned bpp, vbe_mode *out);
int vbe_status(unsigned ax, unsigned fn);
void vbe_palette_entry(unsigned k, unsigned n, const uint8_t bg[3], const uint8_t fg[3], unsigned dac_bits, uint8_t out[4]);
int vbe_copy_ok(uint32_t lfb_size, uint32_t pitch, uint32_t y, uint32_t rows);   /* 1 when y*pitch <= lfb_size && rows*pitch <= lfb_size - y*pitch */
const char *vbe_reason(int code);
```
Offsets: controller `VbeVersion` 4 (u16), `VideoModePtr` 14 (u32: off low, seg high). Mode info: `ModeAttributes` 0,
`BytesPerScanLine` 16, `XResolution` 18, `YResolution` 20, `BitsPerPixel` 25, `MemoryModel` 27, mask/position pairs
R 31/32 G 33/34 B 35/36 Rsvd 37/38, `PhysBasePtr` 40, `LinBytesPerScanLine` 50 (then page counts at 52, 53), Lin pairs R 54/55 G 56/57 B 58/59
Rsvd 60/61 (`MaxPixelClock` 62); all little-endian, read byte-wise. `vbe_modes_copy` rules, `vbe_mode_accept` rules (Lin-when-filled,
MemoryModel 4/6, field validation over channels with mask > 0 with `depth = 15 ? 16 : bits`, 32 bpp reserved absent
or exactly 8 @ 24, depth by masks: 5/5/5 @ 10/5/0 -> 15, 5/6/5 @ 11/5/0 -> 16, 8/8/8 @ 16/8/0 with bits 24 -> 24, 32
-> 32, 8 bpp bits 8; caps 1..4096, `pitch >= w * bytes_pp`, `pitch <= 65535`, `lfb_size = pitch * h <= 16 MB`,
`map_size = (lfb_size + 4095) & ~4095u`, `buf_size = w * bytes_pp * h`), `vbe_status` (0 for 0x004F; FATAL for
0x4F00/01/02; FALLBACK for 0x4F08/09) and the palette rule are the spec's text; `vbe_mode_accept`'s `vbe_version`
is kept for the reason text only (the Lin choice does not depend on it).

- [ ] **Step 1: Write the failing test** `c/tests/test_vbe.c`: a 1 MiB `uint8_t image[]` (static, 1 MiB) with
  `read_word` failing at or past 0x100000; `check(name, ok)` lines as `test_args.c`. Cases: `ptr_ffffe` (list at
  0xFFFFE: one word 0x0101 -> count 1, `modes[1] == 0xFFFF`), `ptr_last_word` (0xFFFFE holding 0xFFFF -> 0),
  `ptr_fff00` (list of 3 then 0xFFFF -> 3), `ptr_1mb` (seg 0xFFFF off 0x0010 -> `VBE_R_BAD_PTR`), `no_terminator`
  (256 entries, no 0xFFFF -> 256, `modes[256] == 0xFFFF`), `terminator_first` (-> 0), `read_fails_mid` (callback
  fails at entry 5 -> 5), `read_fails_first` (-> `VBE_R_READ`); mode blocks: `lfb_clear`, `phys_zero`,
  `pitch_zero`, `pitch_65535_too_big` (w 640 bpp 8 h 4096: `lfb_size` 268 MB -> `VBE_R_TOO_BIG`), `pitch_65535_ok`
  (w 640 bpp 8 h 200 -> accepted, `lfb_size` 13107000, `map_size` 13107200), `pitch_wrap` (`BytesPerScanLine`
  0 with `LinBytesPerScanLine` 0), `lin_used` (Lin pitch 4096 vs plain 2560, Lin masks filled -> pitch 4096),
  `lin_partial` (Lin R and G filled, Lin B 0 -> plain set used), `pos_overflow` (`RedFieldPosition 11` mask 6 at 16
  bpp), `rsvd_28_at_32` (-> `VBE_R_LAYOUT`), `rsvd_absent_32_ok`, `pos_16_at_16bpp`, `overlap` (R 5@10, G 6@5, B 5@0
  with R 5@8), `dosbox_lin15` (bits 15, 5@10 5@5 5@0, rsvd 1@15 -> accepted, depth 15, bytes_pp 2),
  `bits16_masks555` (-> depth 15), `bits24_pos32` (-> LAYOUT), `xres_0`, `xres_4097`, `xres_65535`, `yres_0`,
  `size_caps` (every (pitch, h, w, bytes_pp) at the 16 MB and 64 MB edges, both sides), `copy_ok` (`vbe_copy_ok`
  at `y*pitch == lfb_size` with rows 0 -> 1, rows 1 -> 0, `rows*pitch > lfb_size` -> 0, no underflow at
  `rows*pitch > lfb_size - offset`), `status_table` (every (ax in {0x004F, 0x014F, 0x024F, 0x0000}, fn in {0x4F00,
  0x4F01, 0x4F02, 0x4F08, 0x4F09})), `palette` (k 0 -> bg, k n -> fg, n 255 k 128 of 0/255 -> 128, DAC 6 -> `>> 2`,
  order B G R pad). Each accepted case asserts pitch, depth, bytes_pp, `map_size`, `buf_size`.
- [ ] **Step 2: Run** `make -C c test-vbe` -> FAIL (no such file).
- [ ] **Step 3: Implement** `vbe_select.c`, the Makefile target and `check` dependency, `TestVbe.test_runs`.
- [ ] **Step 4: Run** `make -C c check` -> `test-vbe` exits 0 under ASan/UBSan (gcc; `CC=clang make -C c test-vbe`
  once by hand), the rest OK; `python3 -m unittest tools.test_c_renderer -k TestVbe` -> PASS.
- [ ] **Step 5: Commit** `c/ports/dos: vbe_select, the VBE mode-list, layout and size unit, tested on hostile input`.

### Task 8: `vesa-lines.txt`, its two readers, the dump tool and `svfvesa.c`

**Files:**
- Create: `c/ports/dos/vesa-lines.txt` (the spec's file verbatim), `c/ports/dos/vesa_lines.h`, `c/ports/dos/vesa_lines.c`,
  `c/tests/vesa_lines_dump.c`, `tools/vesa_lines.py`, `c/ports/dos/svfvesa.c`
- Modify: `c/Makefile` (`vesa-lines-dump`), `c/cross/build-all.sh:151-156` (`SVFVESA.EXE` from `svfvesa.c`,
  `vbe_select.c`, `vesa_lines.c` + the objects; `-std=gnu99`), `tools/test_c_renderer.py` (`TestVesaLines`),
  `c/ports/dos/README.md` (a section: usage, build, the file format)
- Test: `tools/test_c_renderer.py` `TestVesaLines`

**Interfaces — Produces:**
```c
/* vesa_lines.h: C99, <stdio.h> <stdint.h> <string.h>; no allocation */
#define VL_MAX_COLOURS 16
#define VL_MAX_LINES 32
#define VL_MAX_FACES 4
#define VL_LINE_BYTES 512          /* a line including its newline; 513 is an error */
#define VL_NAME_BYTES 32           /* a colour name is 1..31 bytes of printable ASCII without spaces (plan's call) */
typedef struct { char name[VL_NAME_BYTES]; uint16_t rgb565, rgb555; uint32_t rgb888; uint8_t index_base, index_levels; } vl_colour;
typedef struct { char faces[VL_MAX_FACES][13]; uint8_t nfaces, num, den, colour; int16_t x, baseline; char text[VL_LINE_BYTES]; } vl_line;
typedef struct { vl_colour colours[VL_MAX_COLOURS]; uint8_t ncolours, background; vl_line lines[VL_MAX_LINES]; uint8_t nlines; } vl_table;
int vl_parse(FILE *fp, vl_table *t, char err[128], int *line_no);        /* 0, or -1 with the message and 1-based line */
void vl_palette(const vl_table *t, unsigned dac_bits, uint8_t pal[256][4]); /* B G R pad per index, through vbe_palette_entry */
size_t vl_substitute(const char *text, unsigned w, unsigned h, unsigned bpp, char *out, size_t out_len); /* {W} {H} {BPP} */
```
Section grammar (both readers; the rev-4 residual): the first non-comment, non-blank line must be `[colours]`;
`[lines]` once after it; any other `[...]` header, a repeated header, a record before `[colours]` or a header after
`[lines]` is an error at that line. Face name: `[A-Z0-9_]{1,8}\.SVF` exactly (upper case only, both readers: DOS
8.3 names and the files in `svf/dos`; a lower-case entry is an error — the plan's resolution of the "A-Za-z" wording).
`rgb888` range 0..0xFFFFFF. Palette: index `background.index_base` and every index no colour names take
`background.rgb888`; a ramp index `base + k` the formula via `vbe_palette_entry`; a file whose background index is not
below every ramp, or whose ramps overlap, is refused ("background index must be below every ramp" / "ramps overlap",
at the line of the second colour involved). `tools/vesa_lines.py`: `parse(path) -> Table` (same fields, same
errors as `VesaLinesError(line_no, message)`), `palette(table, dac_bits) -> [(b, g, r, 0)] * 256`,
`substitute(text, w, h, bpp)`, `print_table(table, dac_bits) -> str` (the exact text `vesa-lines-dump --print-table`
prints: one `colour name=... rgb565=0x.... rgb555=0x.... rgb888=0x...... base=N levels=N` line per colour,
`background=name`, one `line faces=A+B scale=N/D x=N baseline=N colour=name text=<text>` per line, then
`palette[i]=BB GG RR` for i 0..255), `expected_buffer(table, faces_dir, w, h, bpp) -> bytes` (svfline `Target` of
the kind — 8 INDEXED8, 15 rgb555, 16 rgb565, 24 rgb888, 32 xrgb8888 — prefilled with the background pixel, each
line drawn with its chain, scale, x, baseline and colour; `fg565 = rgb565` for 16, `rgb555` for 15, `fg888`,
`index_base/levels`; faces opened from `faces_dir` after the name rule and `os.path.realpath` containment) and
`fnv1a(bytes) -> int`; CLI `--print-table FILE [--dac N]`, `--expect FILE --faces DIR W H BPP` (prints `sum=%08x`).
`svfvesa.c` (DJGPP; `<dpmi.h>`, `<go32.h>`, `<sys/movedata.h>`, `<sys/nearptr.h>` not used): reads `vesa-lines.txt`
and the faces from the current directory (streamed with 1 KB block caches as `svfdemo.c`), `main(argc, argv)`:
no arguments = 640 x 480 at 16, 8, 32 bpp in turn, a key between; `W H BPP [DUMP]` = one mode. Per mode: the
spec's "Mode query", "LFB mapping", "Back buffer", "Dirty rows", "8 bpp palette calls", "Checksum and the run-ready
file" paragraphs, through `vbe_select.c` (`read_word` = `dosmemget` of 2 bytes at `seg * 16 + off`, every
`movedata` guarded by `vbe_copy_ok`), text mode restored on every exit path. `SUM.TXT`: one line
`sum=%08lx dac=%u mode=0x%x %ux%u %ubpp pitch=%lu bits=%u`, `fclose`d before `getch()`; the same line on stdout.
The FNV-1a is bench.c's (copied: 2166136261 / 16777619).

- [ ] **Step 1: Write the failing tests** `TestVesaLines`: `test_dump_equals_python` (`vesa-lines-dump
  --print-table c/ports/dos/vesa-lines.txt` output == `vesa_lines.print_table(parse(...), 8)`, and with `--dac 6`);
  `test_palette_values` (index 0 = (0, 0, 132) in B G R order `84 00 00`; 16..19 blue -> white: 17 = `(0*2+255*1+1)//3`
  per channel = 85 R/G, B `(132*2 + 255 + 1)//3 = 173`; 35 = yellow `00 FF FF`; 127 = `FF FF FF`; 200 = `84 00 00`);
  `test_vesa_lines_limits` (generated files: 16 vs 17 colours, 32 vs 33 lines, 4 vs 5 faces, a 512- and a 513-byte line
  with `가` in the text, empty text accepted, empty numeric and name fields refused, trim rule `  a b  ` -> `a b`,
  both readers agree on acceptance and on the line number of each refusal, the C side through
  `vesa-lines-dump`'s exit code 1 and its stderr `vesa-lines: line N: ...`); `test_vesa_lines_malformed` (5 and 7
  fields, `..\X.SVF`, `C:X.SVF`, `x.svf`, `A/B.SVF`, duplicate colour, missing background, overlapping ramps,
  background inside a ramp, invalid UTF-8 byte 0xFF, rgb888 0x1000000, index_base 255 levels 1, scale 0/1 and 17/1,
  x 32768, unknown colour, colour `background` on a line, `[extra]` header, repeated `[lines]`, a record before
  `[colours]`, `[colours]` after `[lines]`: each refused by both readers with the same line number);
  `test_substitute` (`{W}x{H} {BPP}` -> `640x480 16`, a text without braces unchanged, a `{X}` left as is);
  `test_expected_buffer_fill` (`expected_buffer` at 64 x 16, 16 bpp on a file with no lines: every pixel `10 00`;
  at 8 bpp every byte 0; at 32 bpp `84 00 00 00`).
- [ ] **Step 2: Run** `-k TestVesaLines` -> FAIL (no module, no make target).
- [ ] **Step 3: Implement** `vesa_lines.c/.h`, `vesa_lines_dump.c`, `tools/vesa_lines.py`, the Makefile target,
  `vesa-lines.txt`, `svfvesa.c`, `build-all.sh --ports`, the README section.
- [ ] **Step 4: Run** `-k TestVesaLines` -> PASS; `make -C c check` -> OK; `c/cross/build-all.sh --ports` ->
  `port-dos: OK SVFVESA.EXE N bytes` next to `SVFDEMO.EXE` (record N); a manual DOSBox-X run (`run-dos.sh`'s config
  with `SVFVESA.EXE 640 480 16 DUMP.RAW > OUT.TXT` in the autoexec, under `xvfb-run -a`) prints a `sum=` line to
  `SUM.TXT`, and `python3 tools/vesa_lines.py --expect c/ports/dos/vesa-lines.txt --faces svf/dos 640 480 16` prints the
  same sum. If it does not, the task is not done: compare `DUMP.RAW` with `expected_buffer` byte-wise to locate the
  first differing pixel before changing anything.
- [ ] **Step 5: Commit** `c/ports/dos: svfvesa (VBE 2.0 LFB example), vesa-lines.txt with one parser in C and Python`.

### Task 9: `vesa-shots.sh`: DOSBox-X runs, captures, the checksum and capture checks

**Files:**
- Create: `c/ports/dos/vesa-shots.sh`, `c/ports/dos/vesa_check.py`, `c/ports/dos/shots/<w>x<h>-<bpp>bpp.png` (10)
- Modify: `c/ports/dos/README.md` (the six required PNGs shown, the four 15/24 bpp ones listed, the expansion rule
  found, flush times), `tools/test_c_renderer.py` (`TestVesaCheck`)
- Test: `tools/test_c_renderer.py` `TestVesaCheck`; the script's own checks

**Interfaces — Produces:** `vesa-shots.sh [OUT]` (default `c/build/ports/dos-vesa`; `DOSBOX_X`, `OPT` as the other
scripts; `set -u`, no `eval`; DOSBox-X is the emulator run, xdotool and ffmpeg the host utilities): verifies OUT (absolute,
every component `[A-Za-z0-9._-]+`, not `.`/`..`, no symlink on any prefix nor on `OUT/capture`, `SUM.TXT`,
`DUMP.RAW`, `OUT.TXT`; absent, empty or holding `.vesa-shots`), builds `SVFVESA.EXE` as `build-all.sh` does, copies
`vesa-lines.txt` and the faces it names (after the name rule and `realpath` containment) from `svf/dos`, writes
`dosbox.conf` (the spec's "DOSBox-X configuration" keys; `vesa vbe 1.2 modes are 32bpp = false` for the 24 bpp runs
only), `mapper.txt` with `hand_scrshot "key 62 mod1"` (Ctrl-F5; as built: `hand_capture`/key 292 do not exist in DOSBox-X, and a mapper file also needs `mod_1 "key 224" "key 228"` and `key_space "key 44"`) and, per (640 x 480, 1024 x 768) x (8, 15, 16, 24, 32):
deletes the previous run's files inside OUT, runs `xvfb-run -a -s "-screen 0 1280x1024x24" dosbox-x -conf ... -nopromptfolder
-fastlaunch -nomenu` with autoexec `SVFVESA.EXE W H BPP DUMP.RAW > OUT.TXT`, waits <= 60 s for `SUM.TXT` containing
`sum=` (else kills DOSBox-X: `vesa-shots: SVFVESA did not report (W H BPP); see OUT.TXT and dosbox.log`, exit 1),
checks the `mode=` line against W, H, BPP, computes the expected sum with `tools/vesa_lines.py --expect`, presses
Ctrl-F5 through `xdotool key --window ID ctrl+F5`, waits for the newest `capture/*.png` to appear and stop growing
(10 s, else the ffmpeg x11grab of `screenshot.sh`), then `python3 c/ports/dos/vesa_check.py PNG DUMP.RAW W H BPP
--dac N --palette-from vesa-lines.txt`, presses the ending key, copies the PNG to `c/ports/dos/shots/`, and records
the flush rows (`flush_WxH_bpp` µs from OUT.TXT) in `OUT/flush.md`. `vesa_check.py`: converts the dump to RGB (32/24
exact; 16/15 by `v * 0x21 >> 2` / `v * 0x41 >> 4`; 8 through the intended palette at the DAC width), compares with
the PNG; on a 16/15/8 mismatch derives each channel's rule from the background and ink pixels among
`{v * 0x21 >> 2, v << 3 | v >> 2, v << 3, v * 255 // 31}` (and the 6-bit forms), re-checks exactly, prints
`rule=<name>`; if none fits, tolerance ±8 (5-bit) / ±4 (6-bit) with `tolerance=yes` printed; exit 1 on any mismatch,
a wrong size, or a PNG whose non-background pixels are fewer than 1 % of the frame.

- [ ] **Step 1: Write the failing tests** `TestVesaCheck` (synthetic, PIL): `test_exact_16bpp` (a 64 x 8 rgb565
  dump with two colours and a PNG built with the exact rule -> exit 0, `rule=exact`), `test_swapped_channels_fail`
  (R and B swapped in the PNG -> exit 1), `test_derived_rule` (PNG built with `v << 3` -> exit 0, `rule=shl3`),
  `test_wrong_pitch_fail` (PNG shifted by one column -> exit 1), `test_palette_swap_fail` (8 bpp with the yellow
  ramp's B and R swapped -> exit 1), `test_out_dir_refused` (`vesa-shots.sh` with OUT holding a stray file, OUT
  with a symlinked `capture/`, OUT relative, OUT with a space: exit 1 before any build, nothing deleted —
  `VESA_SHOTS_CHECK_ONLY=1` makes the script exit after the OUT checks).
- [ ] **Step 2: Run** `-k TestVesaCheck` -> FAIL.
- [ ] **Step 3: Implement** `vesa_check.py`, `vesa-shots.sh`.
- [ ] **Step 4: Run** `c/ports/dos/vesa-shots.sh` -> ten `sum ok`, ten `capture ok` lines (with the rule each used),
  ten PNGs in `c/ports/dos/shots/`; open the six required PNGs and confirm by eye: title with the right
  `{W}x{H} {BPP}`, the two 24 px lines, the scaled line, the yellow line, blue background, no channel swap,
  identical layout across depths at one size; `-k TestVesaCheck` -> PASS. Write the README section with the six
  images, the rule(s) found and the flush rows.
- [ ] **Step 5: Commit** `c/ports/dos: vesa-shots.sh (DOSBox-X captures of 10 VBE modes, checksum and capture checks)`
  with the PNGs.

### Task 10: DOS speed rows, Uno fit, sizes, measurements and the card evidence

**Files:**
- Modify: `c/bench/bench.c:230-375` (packed cases, `BENCH_CASE_SUFFIX`), `c/bench/run-dos.sh` (24 px faces copied,
  second build `-DSVF_WORD_STORE=0 -DBENCH_CASE_SUFFIX='"_bytes"'`, `SUMS`/`BUDGETS` for every new case), `c/bench/MEASUREMENTS.md`,
  `c/cross/SIZES.md` (final table), `c/ports/dos/README.md` (flush rows if not already)
- Test: `c/bench/run-dos.sh` (report.awk checksums `ok`), `c/bench/run-avr.sh`

**Interfaces — Produces:** in `bench.c` under `#if defined(BENCH_DOS) || defined(BENCH_HOST)`: a 640 x 32 x 4 byte
`screen` (the largest), `packed_case(name, kind, faces, w, h, baseline)` drawing `line_text` on the kind with
`index_base 16, index_levels 3`, `fg565 0xFFFF`, `fg888 0xFFFFFF`, bg 0, buffer cleared to 0, FNV over
`rows * stride` bytes; cases `line40_<kind>` (PAPLG16+PAPLG18, 640 x 24, baseline 19) for indexed8, rgb555, rgb565,
xrgb8888, rgb888; `line40_24_<kind>` (MARUS24A, 640 x 32, baseline 25) the same five; `line40_24m_<kind>`
(MARUS24, 640 x 32) for indexed8, rgb565, xrgb8888; `bench_report` appends `BENCH_CASE_SUFFIX` (default `""`) to
every name. `run-dos.sh` builds `BENCH.EXE` and `BENCHB.EXE` (the `_bytes` build), runs both at both presets, and
its `SUMS` carry every case name of both; the sums are computed once with the host build
(`cc -DBENCH_HOST -Ic/include c/bench/bench.c c/src/*.c` plus the embedded faces as `run-wasm.sh` makes them)
and cross-checked with `svfline.draw_target` on the same kind, fill 0, same options (a one-off Python snippet in
the commit message), then pasted.

- [ ] **Step 1: Add the cases and the sums**; `python3 -m unittest tools.test_c_renderer` still PASS (nothing
  depends on bench.c); the host bench prints each new case's sum and the Python value agrees.
- [ ] **Step 2: Run** `c/bench/run-dos.sh` twice -> every checksum `ok`, times repeat to 0.01 µs; record both
  presets, both builds. Run `c/bench/run-avr.sh` -> checksums `ok`, the fit line at `0x1F`. Run
  `c/cross/build-all.sh` and `make -C c check` once more on the final tree.
- [ ] **Step 3: Write** `MEASUREMENTS.md`: a "Packed kinds (VESA)" section (header date and commit; the table rows
  for every case at both presets; the `_bytes` rows beside their word-store rows and the verdict per kind: a word
  path stays in the x86 default only if its row is not slower — if one is slower, remove that path from the x86
  default in `svf_draw.c` in this task and say so); the RGB565 before/after (15184.06 µs DX2-66 mapped vs the new
  `line40_rgb565`); the `flush_WxH_bpp` rows from `vesa-shots.sh`; the 24 px rows against the 16 ms budget with the
  DX-33 finding recorded; the DOSBox-X instruction-count caveat; the Uno fit at `0x1F`. `SIZES.md`: the final table
  with P5, P3w and the per-kind growth. Update the "Still over budget" table.
- [ ] **Step 4: Verify** `git diff --check` clean; `python3 -m unittest discover -s tools -p 'test_*.py'` -> PASS;
  `make -C c check` -> OK; `c/cross/build-all.sh` and `--ports` -> OK.
- [ ] **Step 5: Commit** `c/bench: DOS rows for the packed kinds at 16 and 24 px, word-store verdicts, sizes
  (t_6ab9ec2d)`; then `agentws complete t_6ab9ec2d` with `commit:<sha>`, `test:tools/test_c_renderer.py`,
  `test:c/tests/test_vbe.c`, `artifact:c/ports/dos/shots/640x480-16bpp.png` (and the other five required),
  `doc:docs:c/bench/MEASUREMENTS.md`, `doc:docs:c/cross/SIZES.md`, the "still over" list and the word-store
  verdicts in the handoff.

---

## Self-review notes (done while writing)

- Spec coverage: every section maps to a task — API (1), pixel rules (1-4), overlap table (2-4), fast paths and
  word stores (6), `svfline` (1), test plan incl. masks and the compile gate (2-6), `vbe_select` + `test_vbe` (7),
  the example, `vesa-lines.txt`, parser, palette, `SUM.TXT` (8), DOSBox-X config, screenshots and their checks (9),
  measurements, Uno bench, size budget, P5 (5, 10). Review residuals: section grammar, face-name case, rgb888
  range (8); movedata bound as `vbe_copy_ok` (7, used in 8); `test_blend16` promotion model (1); `capture/`
  symlink and the 32 bpp reserved-field rule are in the spec text and land in 9 and 7.
- Types: `vbe_mode`, `vl_table`, `blit_rgb16`'s signature and `SWEEP_KINDS` are defined once and used by name.
- Proportion: the plan is shorter than the spec; bodies appear only where the spec leaves an algorithm open
  (the gate's job list, the dump format, the check tool's rule search).
