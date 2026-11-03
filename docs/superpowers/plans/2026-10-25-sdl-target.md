# SDL2 / SDL3 target (`c/ports/sdl`) and the parametric GRAY kind: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A library kind `SVF_T_GRAY` (1/2/4/8 bits a pixel, bit order, one level rule, byte-identical to
`tools/svfline.py`), then one `svfsdl.c` built against SDL2 and SDL3 that draws the lines table into SDL surfaces of
eight formats and proves headlessly, under both SDLs, that every byte equals `svfline.py`'s.

**Architecture:** Tasks 1-3 are the library task the spec puts first (reference rule, C kind with its tests, size and
speed measurement with a stop rule). Tasks 4-9 are the port: the pinned SDL3 build, the checker (written before the
program it checks), the program in two steps (packed kinds, then the palettised kinds and demos), the `build-all.sh`
integration, and the screenshots and README. Nothing of the port touches `c/src`, `c/include` or `tools/svfline.py`.

**Tech Stack:** C99 (`-Wall -Wextra -Werror`), GNU make + pkg-config, SDL 2.30.0 (host package) and SDL 3.5.0-dev (the
user's fork `~/opt/src/SDL3`, built into `~/opt/sdl3`), POSIX sh, Python 3 (`-I`) with PIL, xvfb-run.

**Spec:** `docs/superpowers/specs/2026-10-24-sdl-target-design.md` (approved by the user 2026-10-25; HEAD 8854fef of
branch `sdl-target`, card t_02418f83). Read the spec with this plan: the plan cites its sections by name and does not
repeat its tables.

All commands run from the repository root `<workdir>/svf-fonts-wt/sdl-target` (branch `sdl-target`, from main
e5232ca). Heavy builds (`build-all.sh`, `make -C c check`, fuzz) run as `~/.local/bin/heavy CMD...` (2 slots at most).
SDD ledgers go under `.superpowers/sdd/2026-10-25-sdl-target/` and are never staged.

## Global Constraints

- SVF v3 only; the format (`spec/SVF.md`) does not change; there is no 4 bpp SVF (faces are 1, 2 and 8 bpp).
- Library changes only in Tasks 2-3: `c/include/svf.h`, `c/src/svf_draw.c` (plus tests, `c/tests/svfdump.c`, `c/Makefile`,
  `c/check.sh`, `c/bench`). At the end `git diff --stat main -- c/src c/include tools/svfline.py` names exactly
  `c/include/svf.h`, `c/src/svf_draw.c`, `tools/svfline.py`.
- New kind: `SVF_T_GRAY = 9`; `SVF_TF_GRAY_LSB_FIRST 0x02u`; `SVF_TARGET_GRAY 0x200u`; `SVF_TARGETS` default `0x3FFu`;
  field `uint8_t gray_bits` after `index_levels`, `svf_target_init` sets 8. `SVF_T_GRAY8` and `SVF_T_MONO_ROW` keep
  their values, bits and behaviour.
- Level rule: `L = index_level(cov, (1 << bits) - 1, mono_threshold)` (for bits 1 that is the mono rule, threshold 0
  counting as 1); `L = 0` leaves the pixel; else the field becomes `max(field, L)`. Row padding bits and padding bytes are
  never written.
- No allocation in `c/src` (the `check.sh` nm gate). All library arithmetic 16-bit safe for AVR.
- Size rule: Cortex-M0+ P1/P2, the Uno (`arduino`, `arduino-small`), the Pico/ESP32 colour, grey and mono images and P5
  (`0x1E8`) unchanged in `SIZES.md`; P1\* and P4 growth reported; **if Cortex-M0+ P1\* grows by more than 400 B, stop and
  report before Task 4.**
- Speed rule: bits 8 of `SVF_T_GRAY` and GRAY8 with the GRAY bit compiled in cost at most +1.0 % rp2040js cycles in any
  `run-pico.sh` case against the GRAY8 `0x01` build (rp2040js cycle counts are deterministic); more is a failure of Task 3.
- Port: one `c/ports/sdl/svfsdl.c` + `c/ports/sdl/sdl_compat.h`; no SDL version test anywhere else; `-std=c99 -Wall
  -Wextra -Werror -O2`; the library compiled with its defaults; stride = SDL pitch; no `SDL_ConvertSurface` and no
  `SDL_RenderReadPixels` on the proven path.
- SDL3 = the user's fork `~/opt/src/SDL3` (HEAD `7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06` today) built into
  `~/opt/sdl3` with `-DSDL_X11_XTEST=OFF` and the spec's cmake switches, commit recorded; a missing SDL2 or SDL3 is a
  failure of `c/ports/sdl/check.sh`, never a skip.
- The DOS port's files, `tools/vesa_lines.py`, `c/ports/dos/vesa_check.py` and the DOS sums do not change.
- Branch interplay: the `jset-compact` branch also changes `c/src/svf_jamo.c` and `c/cross/SIZES.md`; whichever of the
  two branches merges into main second rebases and re-measures every `SIZES.md` row (`build-all.sh` and `--ports` exit 0
  on the rebased tree) in its merge commit.
- Commits: one per task (fix rounds may add more), message names card t_02418f83, ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; no push; `.superpowers/` never staged.
- Implementers are Sonnet; reviews run Claude + agy Flash per task. A finding a later task can fix goes into that task's
  dispatch (fold forward), not a separate fix round.

## Review Focus

1. **Widths that are not a whole number of bytes or pixel groups** (`--size 641x479`, `161x101`): pitch padding bytes
   and the padding bits of the last byte of a gray row must stay 0, under both SDLs. Tests: Task 6 step 6 (641x479 for
   every packed kind), Task 7 step 5 (161x101 for gray bits 1/2/4, both orders, index8, rgb565).
2. **Text running off the surface** at small sizes (lines whose x or baseline put cells past the right or bottom edge):
   clipped, no write past the row's pixels. Same tests as 1 (161x101 clips every line of `sdl-lines.txt`).
3. **Bad command lines and missing inputs** (unknown `--format`, `--threshold 256`/`-1`/`abc`, `--gray-bits 3`, a missing
   face file, a missing lines file): exit 2 with one message on stderr, no dump file written, no SDL window left open.
   Tests: Task 6 step 7, Task 7 step 6.
4. **Sizes the 16-bit fields cannot hold** (`--size 16384x10 --format xrgb8888`: pitch 65536; `--size 40000x10`): refused
   with a message naming the limit, exit 2. Test: Task 6 step 7.
5. **The SDL3 install is absent or moved** (`SDL3_PREFIX` pointing nowhere, or the recorded commit differing from the
   fork tree): `check.sh` fails naming `SDL3_PREFIX` / the two shas; `install-toolchains.sh --verify sdl3` fails on a
   wrong `COMMIT`. Tests: Task 4 step 4, Task 6 step 8.

---

## File structure

| path | task | responsibility |
|---|---|---|
| `tools/svfline.py` | 1 | kind `"gray"`: row bytes, `Target(gray_bits, lsb_first)`, `put` |
| `c/include/svf.h`, `c/src/svf_draw.c` | 2 | `SVF_T_GRAY`: enum, flag, mask bit, field, `target_ok`, init, `blit_gray_packed`, dispatch |
| `c/tests/svfdump.c`, `c/Makefile` | 2 | `--target=gray --gray-bits=N --lsb-first`; builds `svfdump-gray`, `test-args-gray` |
| `c/tests/test_args.c`, `tools/test_c_renderer.py`, `c/check.sh` | 2 | argument cases; identity sweeps and equalities; mask gate `0x000..0x3FF` |
| `c/tests/test_kernels.c`, `c/tests/test_pad.c` | 3 | packed-body net against a fixed per-pixel model; inked padding bits |
| `c/bench/bench.c`, `c/bench/run-pico.sh`, `c/cross/SIZES.md`, `c/bench/MEASUREMENTS.md` | 3 | bits-8 speed rows; size rows |
| `c/cross/install-toolchains.sh`, `c/cross/SIZES.md` | 4 | `sdl3` entry: build the fork, `COMMIT`, `--verify` |
| `c/ports/sdl/sdl_check.py`, `c/ports/sdl/test_sdl_check.py` | 5 | dump reader, expected buffer, compare, diff PNG, `sum=` |
| `c/ports/sdl/sdl_compat.h`, `svfsdl.c`, `Makefile`, `sdl-lines.txt`, `check.sh` | 6, 7 | the program, its build, its table, the matrix |
| `c/cross/build-all.sh`, `c/cross/check-sizes-md.sh`, `c/cross/test-build-all.sh` | 8 | `--port sdl`, `info` rows, OK count 43 |
| `c/ports/sdl/shots.sh`, `sdl_shots.py`, `shots/*.png`, `README.md` | 9 | screenshots, comparison, README |

---

### Task 1: The reference rule of `"gray"` in `tools/svfline.py`

**Files:**
- Modify: `tools/svfline.py:298-395` (`TARGET_KINDS`, `target_row_bytes`, `Target.__init__`, `Target.put`, module docstring line 36)
- Test: `tools/test_c_renderer.py` class `TestReferenceFormulas` (line 1493)

**Interfaces:**
- Produces: `TARGET_KINDS` ends with `"gray"`; `target_row_bytes("gray", w, gray_bits=8)` (new keyword, default 8; other
  kinds ignore it) `= (w * gray_bits + 7) // 8`; `target_rows("gray", h) = h`;
  `Target(kind, w, h, stride=None, buf=None, fg565=0xFFFF, bg565=0, threshold=128, big_endian=False, index_base=0,
  index_levels=255, fg888=0xFFFFFF, bg888=0, gray_bits=8, lsb_first=False)` (two keywords appended; positional callers
  unchanged; default stride uses `gray_bits`).

- [ ] **Step 1: Write the failing tests** in `TestReferenceFormulas`:

```python
def test_gray_levels(self):
    # one pixel at x=0, MSB first; (bits, cov, threshold) -> the byte
    for bits, cov, thr, want in ((1, 85, 128, 0x00), (1, 170, 128, 0x80), (1, 85, 1, 0x80), (1, 255, 255, 0x80),
                                 (1, 254, 255, 0x00), (1, 1, 0, 0x80), (2, 85, 128, 0x40), (2, 170, 128, 0x80),
                                 (2, 255, 128, 0xC0), (4, 85, 128, 0x50), (4, 170, 128, 0xA0), (4, 255, 128, 0xF0),
                                 (8, 85, 0, 85), (8, 200, 0, 200)):
        t = svfline.Target("gray", 8, 1, gray_bits=bits, threshold=thr)
        t.put(0, 0, cov)
        self.assertEqual(t.buf[0], want, (bits, cov, thr))

def test_gray_bit_order_and_max(self):
    t = svfline.Target("gray", 4, 1, gray_bits=4, lsb_first=True)
    t.put(1, 0, 255); t.put(0, 0, 85); t.put(0, 0, 17)   # 17 -> level 1 < 5: max keeps 5
    self.assertEqual(bytes(t.buf), bytes((0xF5, 0x00)))
    t = svfline.Target("gray", 9, 1, gray_bits=2)          # 9 px: 3 bytes, the last holds 1 px + 6 padding bits
    t.put(8, 0, 255)
    self.assertEqual(bytes(t.buf), bytes((0, 0, 0xC0)))
    self.assertEqual(svfline.target_row_bytes("gray", 9, gray_bits=2), 3)
    self.assertEqual(svfline.target_row_bytes("gray", 9, gray_bits=1), 2)

def test_gray_equalities(self):
    for cov in range(1, 256):
        for thr in (0, 1, 128, 255):
            a = svfline.Target("gray", 8, 1, gray_bits=1, threshold=thr); a.put(3, 0, cov)
            b = svfline.Target("mono-row", 8, 1, threshold=thr); b.put(3, 0, cov)
            self.assertEqual(a.buf, b.buf, (cov, thr))
        c = svfline.Target("gray", 2, 1, gray_bits=8); c.put(1, 0, cov)
        d = svfline.Target("gray8", 2, 1); d.put(1, 0, cov)
        self.assertEqual(c.buf, d.buf, cov)
```

Note the mono-row threshold rule today is `cov >= self.threshold` (no `max(thr, 1)`): with `thr == 0` and `cov >= 1` both
sides set the bit, so the equality holds for every `cov > 0` (put is only called with `cov > 0`).

- [ ] **Step 2: Run to verify they fail**
Run: `python3 -I tools/test_c_renderer.py TestReferenceFormulas -v 2>&1 | tail -5`
Expected: the three `test_gray_*` fail (`KeyError: 'gray'` or `TypeError` on `gray_bits`).

- [ ] **Step 3: Implement** in `tools/svfline.py`: the interfaces above; `put` for `"gray"`:
`ppb = 8 // bits; i = y * stride + (x * bits >> 3); s = bits * (x % ppb) if lsb_first else 8 - bits * (x % ppb + 1);
L = index_level(cov, (1 << bits) - 1, threshold)`; when `L > (b[i] >> s & mask)` store it in the field. A `gray_bits`
outside {1, 2, 4, 8} raises `ValueError` in `Target.__init__` (the C library refuses it with SVF_E_ARG at draw).
Docstring line 36 gains "gray: levels of gray_bits packed in rows, the max rule".

- [ ] **Step 4: Run to verify they pass**
Run: `python3 -I tools/test_c_renderer.py TestReferenceFormulas -v 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 5: Commit**
```bash
git add tools/svfline.py tools/test_c_renderer.py
git commit -m "tools: svfline target kind gray (1/2/4/8 bits, bit order, the INDEXED8 ramp / mono rule, max) (card t_02418f83)"
```

---

### Task 2: `SVF_T_GRAY` in the library, svfdump, and its identity tests

**Files:**
- Modify: `c/include/svf.h:283-306,373-430` (enum, flags, mask, `SVF_TARGETS` default and its doc lines 293-328, the kind's
  rule paragraph, "Rows:" least strides, struct field, init doc)
- Modify: `c/src/svf_draw.c` (`target_ok` 362, `svf_target_init` 408, the GRAY8 guards 520/551, `index_level` guard 603,
  new `blit_gray_packed`, dispatch 1120)
- Modify: `c/tests/svfdump.c` (usage 48-58, kind table 529, option parsing 772-840, buffer sizing)
- Modify: `c/tests/test_args.c` (after line 300; kind tables 381-383), `c/Makefile` (targets `svfdump-gray`, `test-args-gray`)
- Modify: `c/check.sh:11-29`, `tools/test_c_renderer.py` (`kind_runs` 1474, `TargetMixin` 2963-3015, `TestTargetsSwitch`
  3983, the `CHECK_LIST_ONLY` test 4461, `build()` 47; new class `TestGrayKind`)

**Interfaces:**
- Consumes: Task 1's `svfline.Target(..., gray_bits, lsb_first)` and `target_row_bytes("gray", w, gray_bits=)`.
- Produces (C): the Global Constraints' names, and these observable rules:
  - `svf_target_init(t, SVF_T_GRAY, buf, buf_len, w, h, stride)`: OK when `buf != NULL`, `stride >= (w + 7) / 8` and
    `buf_len >= h * stride`; sets `gray_bits = 8`, `mono_threshold = 128`. (Implementation: init runs the check with the
    bits-1 bound, e.g. `target_ok` takes the bits to check as a parameter; the draw-time call passes `t->gray_bits`.)
  - `svf_draw_utf8` on SVF_T_GRAY: SVF_E_ARG unless `gray_bits` is 1, 2, 4 or 8 and `stride >= (w * gray_bits + 7) / 8`.
  - Bits 8 draws through `blit_gray8` unchanged (`SVF_TF_GRAY_LSB_FIRST` has no effect at bits 8); bits 1/2/4 through
    `static void blit_gray_packed(const svf_target *t, const cellview *cv, const cut *k, int32_t x, int32_t y)`.
  - Guards: `blit_gray8`, its LUT table and `lut1_or4` compile under `SVF_TARGETS & (SVF_TARGET_GRAY8 | SVF_TARGET_GRAY)`;
    `index_level` under `SVF_TARGETS & (SVF_TARGET_INDEXED8 | SVF_TARGET_GRAY)`; `blit_gray_packed` and the GRAY cases
    under `SVF_TARGETS & SVF_TARGET_GRAY`.
- Produces (svfdump): `--target=gray`, `--gray-bits=N` (0..255 accepted by the parser so the library's refusal is
  testable; default: the library's 8), `--lsb-first` (sets `SVF_TF_GRAY_LSB_FIRST`); the buffer's least row for gray is
  `(w * bits + 7) / 8` with `bits` the given `--gray-bits` (8 if absent; 1 if the value is not 1/2/4/8, so the draw-time
  refusal is what the test sees). Kind name index 9 = `"gray"`.
- Produces (tests): `kind_runs` yields gray once per `GRAY_VARIANTS = tuple({"gray_bits": b, "lsb_first": o} for b in
  (1, 2, 4, 8) for o in (False, True))`; `TargetMixin.opts_of/target` accept `gray_bits=None, lsb_first=False`.

- [ ] **Step 1: Write the failing tests.**
  - `c/tests/test_args.c` under `#if SVF_TARGETS & SVF_TARGET_GRAY`, a 63 x 16 target: `CASE`s "init GRAY stride 8 ok"
    (`stride 8`, `buf_len 128` -> OK, `gray_bits == 8`, `mono_threshold == 128`), "init GRAY stride 7" -> SVF_E_ARG,
    "init GRAY buf_len 127" -> SVF_E_ARG, "init GRAY NULL buf" -> SVF_E_ARG, "draw GRAY bits 8 on stride 8" -> SVF_E_ARG,
    "draw GRAY bits 1 on stride 8" -> SVF_OK, "draw GRAY bits 4 on stride 31" -> SVF_E_ARG, "... stride 32" -> OK,
    "draw GRAY bits 0 / 3 / 16" -> SVF_E_ARG each (one `uint8_t gbuf[16 * 64]`, `buf_len = 16 * stride` per case; the
    draw cases use the file's existing face fixture). The kind tables at 381-383 gain `"GRAY"` / `SVF_T_GRAY`. Built also as
    `test-args-gray` (`-DSVF_TARGETS=0x200`), where "draw GRAY bits 8 on stride 63" is SVF_OK (bits 8 from a 0x200-only
    build) and GRAY8 init is SVF_E_ARG; `test-args-page` and `test-args-vesa` refuse SVF_T_GRAY at init.
  - `tools/test_c_renderer.py`: `kind_runs` and `TargetMixin` as in Interfaces (adding `"gray"` to `TARGET_KINDS` in Task 1
    already enrolls it in every `TestBlitPaths`, `TestWordStores` and `TestTargets` sweep: all pen phases, clip edges,
    scales 1/1 2/1 3/2, overlap, odd widths, `--stride` + 3, `--misalign 0..3`, guard bytes). New class `TestGrayKind(TargetMixin, unittest.TestCase)`:
    - `test_bits8_equals_gray8`: on `ODD_FACES + (MARUS24, self.bpp8-like synth 8 bpp)`, `PHASE_X`, w 100 h 37: svfdump
      `gray` bits 8 (both orders) bytes == svfdump `gray8` bytes.
    - `test_bits1_equals_mono_row`: the same faces, thresholds `(1, 128, 255)`: `gray` bits 1 MSB == `mono-row`.
    - `test_bits4_equals_grey_pack`: 1 bpp and 2 bpp sweep faces only (docstring says why: `grey_pack_rows` is `cov >> 4`,
      equal to the rule only on levels 0/85/170/255): `gray` bits 4 MSB == the GRAY8 buffer packed in Python as
      `c/ports/grey_pack.h` does (high nibble = first pixel, `v >> 4`).
    - `test_threshold_only_bits1`: a 2 bpp face at bits 2 and 4 gives the same bytes at thresholds 1 and 255; at bits 1
      they differ.
    - `test_padding_bits_untouched`: w 61 (bits 1: 3 padding bits; bits 2: 3 px; bits 4: 1 px), fill 0xA5, a line whose
      cells cross column 60: the padding bits of every row's last byte equal the fill's bits.
  - `TestTargetsSwitch`: `"gray"` added to the refused kinds of `svfdump-page` and `svfdump-vesa`; new
    `test_gray_only_build`: `svfdump-gray` (`-DSVF_TARGETS=0x200`) draws gray bits 8 identical to the default build and
    refuses `gray8` with exit 2.
  - The `CHECK_LIST_ONLY` test (4461): `2066` job lines (1024 masks x 2 + 9 masks x 2).
- [ ] **Step 2: Run to verify they fail.**
  Run: `make -C c O=/tmp/svf-t2 test-args && python3 -I tools/test_c_renderer.py TestGrayKind TestTargetsSwitch -v 2>&1 | tail -5`
  Expected: compile error (`SVF_T_GRAY` undeclared) / the new tests FAIL.
- [ ] **Step 3: Implement `svf.h`** exactly as the spec's "Public API" block (enum value 9 with its comment, the flag, the
  mask, `SVF_TARGETS` default `0x3FFu`, the field after `index_levels`). Add the kind's rule paragraph after RGB888's
  (373-398): the level rule, the max rule, bits 8 == GRAY8 bytes, bits 1 MSB == MONO_ROW bytes at the same threshold,
  `mono_threshold` read at bits 1 only, padding never written; "Rows:" gains "GRAY ceil(w * gray_bits / 8) (init checks
  ceil(w / 8))"; `mono_threshold`'s and `flags`' comments name GRAY.
- [ ] **Step 4: Implement `svf_draw.c`**: `target_ok` case `SVF_T_GRAY` (bits check, `row = (w * bits + 7) / 8`), init
  as in Interfaces (sets `gray_bits` only under the GRAY guard), the guards, the dispatch case:
  `case SVF_T_GRAY: if (t->gray_bits == 8) blit_gray8(...); else blit_gray_packed(...); break;` (the 8-only branch is
  compiled when the build has `blit_gray8`, i.e. always with the GRAY bit). `blit_gray_packed` is one per-pixel loop:

```c
	/* per row r in [r0, r1), col in [c0, c1): */
	uint8_t cov = svf__coverage(cv->bpp, src, col), L, f;
	uint32_t px = (uint32_t)(x + col) * bits;           /* x + col >= 0 inside the clip */
	uint8_t *d = dst + (px >> 3), s;
	if (!cov || !(L = index_level(cov, top, thr))) continue;  /* top = (1 << bits) - 1 */
	s = lsb ? (uint8_t)(px & 7u) : (uint8_t)(8u - bits - (px & 7u));
	f = (uint8_t)(*d >> s & top);
	if (L > f) *d = (uint8_t)((*d & ~(top << s)) | (L << s));
```

  `index_level(cov, 1, thr)` is the mono rule, so bits 1 needs no branch of its own.
- [ ] **Step 5: svfdump and Makefile** as in Interfaces; Makefile targets `svfdump-gray` (`-DSVF_TARGETS=0x200`, sanitizer
  flags as `svfdump-vesa`) and `test-args-gray` (as `test-args-vesa` with `0x200`), both added to the lists `build()` and
  `check` already build (`build()` line 47 gains `svfdump-gray`; `check` runs `test-args-gray` where it runs `test-args-vesa`).
  The header comment at Makefile line 4 names them.
- [ ] **Step 6: `c/check.sh`**: `targets_jobs` loops `v` 0..1023 (`0x%03X`), the WORD_STORE mask list becomes
  `0x3FF 0x1FF 0x1E8 0x008 0x020 0x040 0x080 0x100 0x200`; header comment: "0x000..0x3FF gate: all 1024 masks", "2066 jobs".
- [ ] **Step 7: Run the targeted tests.**
  Run: `python3 -I tools/test_c_renderer.py TestReferenceFormulas TestGrayKind TestTargetsSwitch TestBlitPaths -v 2>&1 | tail -3`
  Expected: `OK`.
- [ ] **Step 8: Run the whole gate.**
  Run: `~/.local/bin/heavy make -C c check && ~/.local/bin/heavy make -C c fuzz-smoke`
  Expected: exit 0; output includes `targets: OK cc`, `targets: OK clang`, `asan: OK`, `clang: OK`; fuzz-smoke no crash.
- [ ] **Step 9: Commit**
```bash
git add c/include/svf.h c/src/svf_draw.c c/tests/svfdump.c c/tests/test_args.c c/Makefile c/check.sh tools/test_c_renderer.py
git commit -m "lib: SVF_T_GRAY, the parametric grey kind (1/2/4/8 bits, SVF_TF_GRAY_LSB_FIRST, SVF_TARGET_GRAY 0x200), bits 8 through blit_gray8 (card t_02418f83)"
```

---

### Task 3: Kernel and padding nets, bits-8 speed, sizes (stop rule)

**Files:**
- Modify: `c/tests/test_kernels.c` (new section; the printed line), `c/tests/test_pad.c` (kind 3 = GRAY)
- Modify: `c/bench/bench.c` (`BENCH_LINE_KIND`; `BENCH_KIND == SVF_T_GRAY` handled as GRAY8 in `BENCH_A_BYTES`/`_USED`/`_STRIDE` and set B), `c/bench/run-pico.sh` (`PICO_KINDS`)
- Modify: `c/cross/SIZES.md`, `c/bench/MEASUREMENTS.md`

**Interfaces:**
- Consumes: Task 2's `SVF_T_GRAY`, `svf_test_blit` (exists, `SVF_TEST_HOOKS`).
- Produces: test_kernels' line gains ` gray=<pixels compared>` at its end, the same number in all five builds;
  `bench.c`: `#ifndef BENCH_LINE_KIND / #define BENCH_LINE_KIND SVF_T_GRAY8` used at the two `svf_target_init(...,
  SVF_T_GRAY8, ...)` calls (lines 852, 962); `run-pico.sh`: `PICO_KINDS` (default `"MONO_PAGE 0x02" "GRAY8 0x01"
  "RGB565 0x08"`, a space-separated list of `NAME:BIT`; a `GRAY` entry takes `SUMS_GRAY8`).

- [ ] **Step 1: Write the failing tests.**
  - `test_kernels.c` `gray_packed()`: 3000 random cells (bpp 1, 2, 8; w 1..40, h 1..6, random content incl. inked padding
    bits as test_pad does), x in -9..40, a 64 x 8 target at bits {1, 2, 4} x {MSB, LSB}, threshold random 0..255, random
    prefill; reference written in the file (per pixel: coverage from the stored cell, `index_level` copied, field max as
    Task 2's rule); compare the whole buffer plus 16 guard bytes each side. On mismatch print
    `kernels: FAIL gray: bits=%u lsb=%u x=%d` and exit 1.
  - `test_pad.c`: kind 3 = SVF_T_GRAY at bits 1, 2, 4 and both orders, model per pixel (padding pixels of the cell never
    drawn; target bits outside the cut unchanged); target width 13 + 3 so the last byte has padding bits. The checksum line
    changes; both builds print the same.
- [ ] **Step 2: Prove the net can fail, then pass.** With the reference's shift deliberately using the other bit order,
  Run: `make -C c O=/tmp/svf-t3 test-kernels` -> `kernels: FAIL gray: ...`, exit 1. Restore the reference and run
  `make -C c O=/tmp/svf-t3 test-kernels test-pad`: OK lines, the five kernels builds print the same line, both pad
  builds the same checksum.
- [ ] **Step 3: bench and run-pico changes** as in Interfaces. Host check of the bits-8 path:
  Run: `c/bench/run-host.sh /tmp/b0 > /tmp/b0.txt; c/bench/run-host.sh /tmp/b1 -DBENCH_LINE_KIND=SVF_T_GRAY > /tmp/b1.txt; diff <(awk '{print $1, $NF}' /tmp/b0.txt) <(awk '{print $1, $NF}' /tmp/b1.txt)`
  Expected: no checksum difference (times printed side by side in the commit message, informational).
- [ ] **Step 4: Pico bits-8 speed.**
  Run: `PICO_KINDS="GRAY8:0x01 GRAY8:0x201 GRAY:0x200" ~/.local/bin/heavy c/bench/run-pico.sh /tmp/pico-gray`
  Expected: every case's checksum OK in all three builds; per case cycles of `GRAY8 0x201` and `GRAY 0x200` at most
  1.01 x those of `GRAY8 0x01`, at `-Os` and `-O2`. Over: stop, report the rows (failure of this task).
- [ ] **Step 5: Sizes.** Baseline from main first, in a throwaway worktree:
  `git worktree add /tmp/svf-main e5232ca && ~/.local/bin/heavy /tmp/svf-main/c/cross/build-all.sh /tmp/sz-before`, then
  `~/.local/bin/heavy c/cross/build-all.sh /tmp/sz-after` and `~/.local/bin/heavy c/cross/build-all.sh --ports /tmp/pt-after`.
  Expected: Cortex-M0+ P1, P2, P3, P3g, P3w, P5 and AVR P1/P2 text unchanged; the `--ports` run fails only on rows that
  link the default `SVF_TARGETS` (none of pico/esp32/arduino/ch582: they set masks) and on the dos/web program sizes.
  If Cortex-M0+ P1\* grows by more than 400 B, or any row of the "unchanged" list moves (the AVR struct is 1 byte larger:
  if the Uno row moves, that is the cause to report), **stop and report** with the numbers.
- [ ] **Step 6: Record.** `SIZES.md`: the "Sizes" table re-measured (every toolchain), a new subsection "Before -> after
  the GRAY kind (text bytes, e5232ca -> <sha>)" with P1\*/P4 per toolchain and the "unchanged" profiles listed, the
  dos/web program line updated, the 8 KB paragraph's P1\* figure; the P1\* growth is put to the user for acceptance in
  the task report (not self-accepted). `MEASUREMENTS.md`: the three Pico GRAY builds' rows side by side.
  Run: `~/.local/bin/heavy c/cross/build-all.sh /tmp/sz-final && ~/.local/bin/heavy c/cross/build-all.sh --ports /tmp/pt-final`
  Expected: both exit 0 (the table now matches).
- [ ] **Step 7: Commit**
```bash
git add c/tests/test_kernels.c c/tests/test_pad.c c/bench/bench.c c/bench/run-pico.sh c/cross/SIZES.md c/bench/MEASUREMENTS.md
git commit -m "lib: GRAY kind nets (test_kernels gray, test_pad), bits-8 bench rows, SIZES.md before/after (card t_02418f83)"
```

---

### Task 4: The pinned SDL3 (the user's fork) in `install-toolchains.sh`

**Files:**
- Modify: `c/cross/install-toolchains.sh` (header "Names" and "Pinned releases"; install, `--verify` cases), `c/cross/SIZES.md` (toolchain table)
- Test: `c/cross/test-installers.sh` (one case)

**Interfaces:**
- Produces: name `sdl3`; `SDL3_SRC=${SDL3_SRC:-$HOME/opt/src/SDL3}`; `SDL3_COMMIT=7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06`;
  install builds into `PREFIX/sdl3` and writes `PREFIX/sdl3/COMMIT` (one line, the 40-hex sha); `--verify sdl3`: OK when
  `PREFIX/sdl3/COMMIT` equals `SDL3_COMMIT` and `PREFIX/sdl3/lib/pkgconfig/sdl3.pc` exists; "not installed" when the
  directory is absent; error otherwise. Later tasks find SDL3 with `PKG_CONFIG_PATH=$SDL3_PREFIX/lib/pkgconfig`,
  `SDL3_PREFIX ?= $HOME/opt/sdl3`.

- [ ] **Step 1: Write the failing test** in `test-installers.sh`: with `OPT=$tmp`, a fake `$tmp/sdl3/COMMIT` holding
  `0000...` (40 zeros) and an empty `lib/pkgconfig/sdl3.pc`: `install-toolchains.sh --verify sdl3` exits non-zero and its
  output names both shas; with the right sha it exits 0; with no `$tmp/sdl3` it prints `sdl3: not installed`.
- [ ] **Step 2: Run to verify it fails.** Run: `sh c/cross/test-installers.sh 2>&1 | tail -3`. Expected: the sdl3 case FAILs (unknown name).
- [ ] **Step 3: Implement.** Install: refuse with `sdl3: the fork tree is not at $SDL3_SRC (the user's SDL3 fork; no
  download)` if absent; refuse if `git -C "$SDL3_SRC" rev-parse HEAD` is not `SDL3_COMMIT` (print both); else cmake
  configure into `PREFIX/.svf-work/sdl3-build` with the spec's switches (`-DCMAKE_BUILD_TYPE=Release -DSDL_SHARED=ON
  -DSDL_STATIC=ON -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF -DSDL_AUDIO=OFF -DSDL_JOYSTICK=OFF -DSDL_HAPTIC=OFF -DSDL_CAMERA=OFF
  -DSDL_SENSOR=OFF -DSDL_GPU=OFF -DSDL_WAYLAND=OFF -DSDL_X11_XTEST=OFF -DCMAKE_INSTALL_PREFIX=PREFIX/sdl3`), build,
  install, write `COMMIT`. A present `PREFIX/sdl3` is not replaced (the script's rule). Header: the fork is the user's, at a path, not a URL.
- [ ] **Step 4: Run the test, then install for real.**
  Run: `sh c/cross/test-installers.sh 2>&1 | tail -3 && ~/.local/bin/heavy c/cross/install-toolchains.sh "$HOME/opt" sdl3 && OPT=$HOME/opt c/cross/install-toolchains.sh --verify sdl3`
  Expected: tests pass; install ends with the SDL3 version; verify `sdl3: OK 7a588ba6...`; `PKG_CONFIG_PATH=$HOME/opt/sdl3/lib/pkgconfig pkg-config --modversion sdl3` prints `3.5.0`.
- [ ] **Step 5: SIZES.md** toolchain table: row `sdl3 | 3.5.0-dev (fork ~/opt/src/SDL3, commit 7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06) | install-toolchains.sh sdl3 | host desktop port only`; and `sdl2 | 2.30.0 | libsdl2-dev (system) |`.
- [ ] **Step 6: Commit**
```bash
git add c/cross/install-toolchains.sh c/cross/test-installers.sh c/cross/SIZES.md
git commit -m "cross: install-toolchains sdl3 - the user's SDL3 fork built into ~/opt/sdl3 with its commit recorded and verified (card t_02418f83)"
```

---

### Task 5: The checker `c/ports/sdl/sdl_check.py`

**Files:**
- Create: `c/ports/sdl/sdl_check.py`, `c/ports/sdl/test_sdl_check.py`, `c/ports/sdl/sdl-lines.txt`

**Interfaces:**
- Dump format (settled here, spec "Dump mode"; little-endian u16s), 16-byte header then `pitch * h` bytes:

| offset | field |
|---|---|
| 0-7 | `b"SVFSDL1 "` |
| 8-9, 10-11, 12-13 | w, h, pitch |
| 14 | bits per pixel: 32, 24, 16, 8, 4, 2 or 1 (index8 8; alpha-demo coverage 8) |
| 15 | flags: bit 0 `SVF_TF_RGB16_BIGENDIAN` set; bit 1 palettised (index8, gray); bit 2 LSB first (gray); bit 3 alpha-demo coverage buffer; bits 4-5 SDL major - 2 (0 = SDL2, 1 = SDL3); bits 6-7 zero |

- CLI: `sdl_check.py DUMP --kind K --lines FILE --faces DIR [--threshold N] [--diff PNG]` with `K` in `xrgb8888 argb8888
  rgb565 rgb555 bgr24 index8 gray alpha`. Exit 0 identical (prints `sdl-check: OK <kind> <w>x<h> pitch=<p> sdl<major> sum=<fnv1a 8 hex>`),
  1 a byte differs (prints `sdl-check: DIFF <kind> byte <i> pixel (<x>,<y>) got <g> want <w>` and writes the diff PNG,
  default `DUMP + ".diff.png"`), 2 a bad dump / usage / a header that contradicts `--kind` (bits, palettised flag, LSB on a
  non-gray kind, reserved bits) or `sys.byteorder` (big-endian flag on a little-endian host).
- `expected(table, faces_dir, kind, w, h, pitch, threshold=128, gray_bits=8, lsb_first=False, big_endian=False) -> bytes`:
  rows cleared to the background pixel (`xrgb8888`: B G R 0 of `rgb888`; `argb8888`: B G R 0xFF; `rgb565`/`rgb555`: the
  colour's value in the endian of the flag; `bgr24`: B G R; `index8`: `background.index_base`; `gray`: 0 bytes) and the
  padding bytes 0; then per line `svfline.Target(kind_of[K], w, h, stride=pitch, buf=buf, ...)` with the colours as the
  spec's checker paragraph says (`argb8888`: `fg888 | 0xFF000000`; `index8`: the line colour's `index_base`/`index_levels`
  and `threshold`; `gray`: `gray_bits`, `lsb_first`, `threshold`, colours ignored; `alpha`: kind `gray8`, stride `w`),
  `svfline.placements` + `draw_target` as `tools/vesa_lines.py expected_buffer`. Imports `parse`, `substitute`,
  `_face_path`, `fnv1a` from `tools/vesa_lines.py` (unchanged). `{BPP}` substitutes the header's bits per pixel.
- `sdl-lines.txt`: the DOS file's format and faces; colours `background 0x0010 0x0010 0x000084 0 0`, `white 0xFFFF
  0x7FFF 0xFFFFFF 16 3` (title: a 3-level ramp), `yellow 0xFFE0 0x7FE0 0xFFFF00 32 1` (one ink index, thresholded),
  `scaled 0xFFFF 0x7FFF 0xFFFFFF 64 63`; six lines: title `SVF SDL 예제 {W}x{H} {BPP} bpp` (PAPLG16+PAPLG18, white), MARUS24A
  line (white), MARUS24 line (white, 1 bpp), a 3/2 line (scaled), a 2/1 line (scaled), a yellow PAPLG line. No SDL version in any text.

- [ ] **Step 1: Write the failing tests** `test_sdl_check.py` (unittest, run as `python3 -I c/ports/sdl/test_sdl_check.py`): it
  builds dumps itself from `expected()` (no SDL needed): (a) for each kind at 63 x 40 with pitch rounded up to 4
  (`xrgb8888` 252, `rgb565` 128, `bgr24` 192, `index8` 64, `gray` bits 4 32) the dump checks exit 0 and the `sum=` of a
  repeated run is equal; (b) one byte flipped inside the pixels -> exit 1, the message names that byte's (x, y), the PNG
  exists; (c) one padding byte set to 1 -> exit 1; (d) header with bit 1 clear for `--kind index8` -> exit 2; wrong magic,
  short file -> exit 2; (e) `argb8888` dump checked as `xrgb8888` -> exit 1 (the 4th byte differs); (f) `gray` bits 1 at
  `--threshold 255` differs from the default threshold's expected buffer on a 2 bpp line.
- [ ] **Step 2: Run to verify they fail.** Run: `python3 -I c/ports/sdl/test_sdl_check.py 2>&1 | tail -3`. Expected: `ModuleNotFoundError` / errors.
- [ ] **Step 3: Implement** `sdl_check.py` (the interfaces above; PIL only for the diff PNG: differing pixels red on the
  expected picture expanded as grey bytes) and `sdl-lines.txt`. `tools/vesa_lines.py` must parse `sdl-lines.txt`:
  Run: `python3 -I tools/vesa_lines.py --print-table c/ports/sdl/sdl-lines.txt | head -3` exits 0.
- [ ] **Step 4: Run to verify they pass.** Run: `python3 -I c/ports/sdl/test_sdl_check.py -v 2>&1 | tail -3`. Expected: `OK`.
- [ ] **Step 5: Commit**
```bash
git add c/ports/sdl/sdl_check.py c/ports/sdl/test_sdl_check.py c/ports/sdl/sdl-lines.txt
git commit -m "ports/sdl: the headless checker (dump header, expected buffer at the SDL pitch, diff PNG, sum) and sdl-lines.txt (card t_02418f83)"
```

---

### Task 6: `svfsdl` for the packed kinds, the compat header, the Makefile, `check.sh`

**Files:**
- Create: `c/ports/sdl/sdl_compat.h`, `c/ports/sdl/svfsdl.c`, `c/ports/sdl/Makefile`, `c/ports/sdl/check.sh`

**Interfaces:**
- Consumes: Task 4 (`~/opt/sdl3`), Task 5 (dump format, checker CLI, `sdl-lines.txt`), `vesa_lines.h` (`vl_parse`,
  `vl_substitute`, `vl_cache_slots`, `VL_CACHE_BLOCK`, `vl_palette`).
- `sdl_compat.h`: the spec's block (`SVFSDL_OK`, `SVFSDL_EVENT_QUIT`, `SVFSDL_EVENT_KEY_DOWN`, `svfsdl_create_window`,
  `svfsdl_create_surface`, `svfsdl_surface_format`, `svfsdl_create_renderer`, `svfsdl_render_copy`) plus
  `svfsdl_major()` (2 or 3, from `SDL_MAJOR_VERSION`), `svfsdl_create_texture(r, fmt, w, h)` and, for Task 7,
  `SDL_Palette *svfsdl_surface_palette(SDL_Surface *s)`. Under 90 lines; the SDL2 `SDL_PixelFormatEnum` vs SDL3
  `SDL_PixelFormat` type is hidden as `typedef ... svfsdl_format;`. Anything needing more than a macro or one-line inline is
  reported in the task report.
- `svfsdl.c` command line: `--format F` (`xrgb8888` default, `argb8888`, `rgb565`, `rgb555`, `bgr24`; Task 7 adds
  `index8`, `gray`), `--size WxH` (default 640x480), `--present surface|texture|texture-direct` (default surface),
  `--stream`, `--syllable-cache=BYTES`, `--faces DIR` (default `svf/dos`), `--lines FILE` (default
  `c/ports/sdl/sdl-lines.txt`), `--dump FILE`, `--shot FILE`, `--frames N` (0 = until a key or close; with `--dump` or
  `--shot` default 1). Order in a run: draw, present, shot, dump, exit. Exit 0 ok, 2 usage / input error (no dump file
  written), 1 SDL or library error at run time. Prints one line: `svfsdl: SDL <x.y.z> driver <name> window <fmt name> back <fmt name> pitch <p> draw <us> us sum=<fnv1a>`.
- Rules (spec "Surfaces, pitch, locking, textures"): back buffer created by the port; the format it got checked against the
  one asked (mismatch: exit 1); `svf_target_init(&t, kind, s->pixels, (size_t)s->pitch * s->h, s->w, s->h, (uint16_t)s->pitch)`;
  refused before SDL init: `w` or `h` > 32767, `pitch` estimate `w * bytes` > 65535 (rounded to 4) with
  `svfsdl: --size WxH: pitch P > 65535 (stride is 16 bits)`; clear rows (background pixel of the kind, then padding 0);
  `SDL_LockSurface`/`Unlock` around draw and dump; faces mapped (`fread` whole file, `svf_open_mapped`) or streamed (callback
  `fseek`+`fread`, cache `vl_cache_slots`, `VL_CACHE_BLOCK`, tables from `svf_stream_tables_size`); scratch from
  `chain_scratch` via the public scratch size function the DOS port uses. `rgb565`/`rgb555` set
  `SVF_TF_RGB16_BIGENDIAN` when `SDL_BYTEORDER == SDL_BIG_ENDIAN`; `argb8888` fg `0xFF000000 | rgb888`, clear alpha 0xFF.
  `texture-direct` draws into the locked texture, never dumps (`--dump` with it is a usage error).
- `Makefile`: `SDL ?=` (empty = both), `SDL3_PREFIX ?= $(HOME)/opt/sdl3`, `O ?= ../../build/ports/sdl`, `ASAN=1` adds
  `-fsanitize=address,undefined -fno-omit-frame-pointer`; outputs `$(O)/svfsdl2`, `$(O)/svfsdl3` (`-DSVFSDL=2|3`, SDL3
  with `-Wl,-rpath,<libdir>`); sources as the spec's "Build integration"; targets `all check shots clean`.
- `check.sh [OUT]`: builds both (a pkg-config failure prints `port-sdl-check: FAIL sdl3 not found (SDL3_PREFIX=...)` and
  exits 1; `SVFSDL_ONLY=2|3` builds and runs one), runs `test_sdl_check.py` first, then the matrix with
  `SDL_VIDEODRIVER=dummy` and `--frames 1`, each run checked by `sdl_check.py`, and asserts the SDL2 and SDL3 dumps of one
  case are byte-equal (`cmp` after the 16-byte header, whose byte 15 differs in bits 4-5 only). Last line
  `port-sdl-check: OK sdl2 <n> runs, sdl3 <n> runs, sum=<fnv1a of the xrgb8888 mapped dump>`.

- [ ] **Step 1: Write the failing check** — `check.sh` with this task's matrix per SDL: 5 kinds x {mapped, `--stream`};
  `xrgb8888 --syllable-cache=65536`; `rgb565 --present texture`; `xrgb8888 --present texture-direct` (exit 0, no dump);
  every kind at `--size 641x479` (Review Focus 1); one `ASAN=1` build of `svfsdl2` running `rgb565 --stream`. 
- [ ] **Step 2: Run to verify it fails.** Run: `sh c/ports/sdl/check.sh /tmp/sdlck`. Expected: build failure (no `svfsdl.c`).
- [ ] **Step 3: Implement** `sdl_compat.h`, `svfsdl.c`, `Makefile` (interfaces above).
- [ ] **Step 4: Run to verify it passes.** Run: `sh c/ports/sdl/check.sh /tmp/sdlck`. Expected: `port-sdl-check: OK sdl2 19 runs, sdl3 18 runs, sum=...` (the ASAN run counts under sdl2; the expected-failure runs of step 7 are not counted), exit 0.
- [ ] **Step 5: Version-test scan.** Run: `grep -n "SDL_VERSION_ATLEAST\|SVFSDL ==" c/ports/sdl/*.c; grep -rn "SDL" c/src c/include`. Expected: no output.
- [ ] **Step 6: Padding probe** (Review Focus 1, 2): already in the matrix (641x479); also confirm the dump's padding is
  zero: `python3 -I -c` reading the 641x479 `rgb565` dump: bytes `1282..1283` of each 1284-byte row are 0.
- [ ] **Step 7: Error cases** (Review Focus 3, 4), added to `check.sh` as expected-failure runs (each must exit 2, print one
  `svfsdl:` line on stderr, leave no dump file): `--format rgb24`, `--size 16384x10` (xrgb8888), `--size 40000x10`,
  `--faces /nonexistent`, `--lines /nonexistent`, `--dump x --present texture-direct`, `--syllable-cache=abc`.
- [ ] **Step 8: SDL3 absent** (Review Focus 5): Run: `SDL3_PREFIX=/nonexistent sh c/ports/sdl/check.sh /tmp/sdlck2; echo rc=$?`. Expected: `port-sdl-check: FAIL sdl3 not found (SDL3_PREFIX=/nonexistent)`, `rc=1`.
- [ ] **Step 9: Commit**
```bash
git add c/ports/sdl/sdl_compat.h c/ports/sdl/svfsdl.c c/ports/sdl/Makefile c/ports/sdl/check.sh
git commit -m "ports/sdl: svfsdl from one source for SDL2 and SDL3 (xrgb8888, argb8888, rgb565, rgb555, bgr24), headless byte-identity check (card t_02418f83)"
```

---

### Task 7: `index8`, `gray`, `--threshold`, `--alpha-demo`

**Files:**
- Modify: `c/ports/sdl/svfsdl.c`, `c/ports/sdl/sdl_compat.h` (`svfsdl_surface_palette`), `c/ports/sdl/check.sh`

**Interfaces:**
- Consumes: Task 2's `SVF_T_GRAY` / `gray_bits` / `SVF_TF_GRAY_LSB_FIRST`; Task 5's dump flags and checker kinds `index8 gray alpha`.
- Options: `--format index8` (`SDL_PIXELFORMAT_INDEX8`, `SVF_T_INDEXED8`, per line `index_base`/`index_levels` of its
  colour, clear to `background.index_base`); `--format gray --gray-bits 1|2|4|8 [--lsb-first]` (`INDEX1MSB/LSB`,
  `INDEX2MSB/LSB`, `INDEX4MSB/LSB`, `INDEX8`; `SVF_T_GRAY`, clear 0); `--threshold N` (0..255, default 128;
  `mono_threshold` of index8 and gray targets; accepted with other formats and ignored there); `--alpha-demo` (one line,
  the table's first, drawn on `SVF_T_GRAY8` w x h stride w; converted to `SDL_PIXELFORMAT_BGRA32` `(b, g, r, c)` with the
  line colour's rgb888; blitted with `SDL_BLENDMODE_BLEND` over a gradient; `--dump` writes the GRAY8 buffer, flags bit 3).
- Palettes: `index8`: `vl_palette(table, 8, pal)` -> `SDL_Color {pal[i][2], pal[i][1], pal[i][0], 255}` x 256; `gray`:
  `2^bits` entries, entry k = `(bg * (n - k) + 255 * k + n / 2) / n` per channel, `n = 2^bits - 1`, `bg` the background's
  rgb888. Set with `SDL_SetPaletteColors(svfsdl_surface_palette(s), colors, 0, count)`.
- Presenting: `surface` blits through the palette; `texture` for `index8`/`gray` uses `SDL_CreateTextureFromSurface`;
  `texture-direct` with `index8`/`gray` is a usage error (exit 2).

- [ ] **Step 1: Write the failing check** — `check.sh` matrix additions per SDL: `index8` mapped and `--stream`;
  `index8 --threshold 1`, `--threshold 255`; `index8 --present texture`; `gray` bits {1,2,4,8} x {MSB, LSB} mapped;
  `gray --gray-bits 4 --stream`; `gray --gray-bits 1 --threshold 1` and `255`; `--alpha-demo`.
- [ ] **Step 2: Run to verify it fails.** Run: `sh c/ports/sdl/check.sh /tmp/sdlck`. Expected: the new runs exit 2 (unknown format).
- [ ] **Step 3: Implement** (interfaces above).
- [ ] **Step 4: Run to verify it passes.** Run: `sh c/ports/sdl/check.sh /tmp/sdlck`. Expected: `port-sdl-check: OK sdl2 36 runs, sdl3 35 runs, sum=...` (17 new a SDL).
- [ ] **Step 5: Small clipped surface** (Review Focus 1, 2): add `--size 161x101` runs for `gray` bits 1/2/4 x both orders,
  `index8`, `rgb565`; Run check.sh again. Expected: `port-sdl-check: OK sdl2 44 runs, sdl3 43 runs, sum=...`.
- [ ] **Step 6: Error cases** (Review Focus 3) as expected-failure runs: `--threshold 256`, `--threshold -1`, `--threshold abc`,
  `--gray-bits 3`, `--gray-bits 4` without `--format gray`, `--format gray --present texture-direct`. Each exit 2, no dump.
- [ ] **Step 7: Commit**
```bash
git add c/ports/sdl/svfsdl.c c/ports/sdl/sdl_compat.h c/ports/sdl/check.sh
git commit -m "ports/sdl: index8 (CLUT8) with --threshold, gray on INDEX1/2/4/8 MSB/LSB through SVF_T_GRAY, --alpha-demo (card t_02418f83)"
```

---

### Task 8: `build-all.sh --port sdl`, informational size rows

**Files:**
- Modify: `c/cross/build-all.sh` (`ALL_PORTS`, `port()`, the header's port list and OK count 42 -> 43, `--verify` names
  for `--ports`), `c/cross/check-sizes-md.sh` (skip `info` lines), `c/cross/test-build-all.sh`, `c/cross/SIZES.md`

**Interfaces:**
- Consumes: Task 6/7 `c/ports/sdl/check.sh [OUT]`, `make -C c/ports/sdl O=...`; Task 4 `--verify sdl3`.
- Produces: `port sdl`: runs `sh "$P/sdl/check.sh" "$d"`, then prints `port-sdl: OK svfsdl2 <bytes> bytes, svfsdl3 <bytes>
  bytes` (one OK line; `port-sdl-check:` lines of the script are passed through but do not end in `: OK` counted by the
  header's count — the header comment says the count is 43 with the `port-sdl` line); rows file lines `info program sdl2
  <bytes>` and `info program sdl3 <bytes>`; `check-sizes-md.sh` ignores lines whose first token is `info`; `SIZES.md`
  "Port examples" gets a separate line `(informational, not gated: sdl2: `svfsdl2` N bytes; sdl3: `svfsdl3` N bytes.)` under the dos/web line.
  `--ports` verifies `sdl3` with the other names.

- [ ] **Step 1: Write the failing test** in `test-build-all.sh`: a rows file with an `info program sdl2 123` line passes
  `check-sizes-md.sh` against a SIZES.md fixture that does not mention it; `build-all.sh --port nosuch` lists `sdl` among
  the names.
- [ ] **Step 2: Run to verify it fails.** Run: `sh c/cross/test-build-all.sh 2>&1 | tail -3`. Expected: FAIL on the info line.
- [ ] **Step 3: Implement** (interfaces above).
- [ ] **Step 4: Run.** Run: `sh c/cross/test-build-all.sh && ~/.local/bin/heavy c/cross/build-all.sh --port sdl /tmp/pt-sdl`.
  Expected: tests pass; `port-sdl: OK svfsdl2 ... bytes, svfsdl3 ... bytes`.
- [ ] **Step 5: Full gate.** Run: `~/.local/bin/heavy c/cross/build-all.sh --ports /tmp/pt-all 2>&1 | grep -c ': OK'` after
  adding the two sizes to SIZES.md. Expected: `43`, exit 0.
- [ ] **Step 6: Commit**
```bash
git add c/cross/build-all.sh c/cross/check-sizes-md.sh c/cross/test-build-all.sh c/cross/SIZES.md
git commit -m "cross: build-all --port sdl (check.sh, informational svfsdl2/svfsdl3 sizes), 43 OK lines (card t_02418f83)"
```

---

### Task 9: Screenshots and README

**Files:**
- Create: `c/ports/sdl/shots.sh`, `c/ports/sdl/sdl_shots.py`, `c/ports/sdl/shots/sdl{2,3}-{xrgb8888,argb8888,rgb565,index8,gray4}.png`, `c/ports/sdl/README.md`

**Interfaces:**
- Consumes: Task 6/7 `--shot FILE.bmp --dump FILE --frames 1`.
- `sdl_shots.py BMP DUMP --kind K --png OUT`: converts to PNG (PIL), checks size W x H and >= 1 % of pixels off the
  background, compares the picture with the dump expanded as SDL shows it (32-bit exact; RGB565 `v * 0x21 >> 2` for 5
  bits, `v * 0x41 >> 4` for 6; index8 through `vl_palette`-equivalent palette from `tools/vesa_lines.palette(table, 8)`;
  gray through the Task 7 grey palette); prints `exact`, or `shl`/`tolerance` with the count (not a failure). The
  comparison code is copied here (small), `vesa_check.py` is not touched. Exit 0 / 1 (size or blank) / 2 usage.
- `shots.sh [OUT]`: `xvfb-run` missing -> message and exit 2; for SDL2 and SDL3, the five formats at 640 x 480,
  `xvfb-run -a -s "-screen 0 1280x1024x24" svfsdlN --format K --present surface --shot B --dump D --frames 1`, then
  `sdl_shots.py`, copying PNGs to `c/ports/sdl/shots/`; then reports per format `sdl2 == sdl3: identical` or the count of
  differing pixels. `make -C c/ports/sdl shots` runs it.

- [ ] **Step 1: Write the failing test**: `test_sdl_check.py` gains `TestShots`: a synthetic BMP made with PIL from an
  expected xrgb8888 buffer passes `sdl_shots.py` as `exact`; an all-background BMP exits 1 (blank).
- [ ] **Step 2: Run to verify it fails.** Run: `python3 -I c/ports/sdl/test_sdl_check.py TestShots 2>&1 | tail -3`. Expected: errors (no module).
- [ ] **Step 3: Implement** `sdl_shots.py`, `shots.sh`.
- [ ] **Step 4: Run.** Run: `sh c/ports/sdl/shots.sh /tmp/sdlshots`. Expected: ten PNGs, every format `exact`, every
  format `sdl2 == sdl3: identical` (or the reason printed and carried into the README).
- [ ] **Step 5: README** with the spec's six sections ("README contents"), including the format table with the ScummVM
  `PixelFormat` equivalents, the threshold sentence ("levels 85/170/255 of a 2 bpp face: 128 keeps the upper two, 255
  keeps only full pixels, 1 keeps any ink"; "for gray bits >= 2 the threshold is not read"), "gray ignores the table's line
  colours", `RGB24` not offered, `texture-direct` a demonstration, the run counts and `sum=` from Task 7/8, the SDL3 commit,
  and the 2 x 5 screenshot table.
- [ ] **Step 6: Commit and hand to the user.**
```bash
git add c/ports/sdl/shots.sh c/ports/sdl/sdl_shots.py c/ports/sdl/test_sdl_check.py c/ports/sdl/shots/*.png c/ports/sdl/README.md
git commit -m "ports/sdl: screenshots (SDL2/SDL3 x xrgb8888, argb8888, rgb565, index8, gray 4) and README (card t_02418f83)"
```
  Post the ten PNG paths and the `port-sdl-check` / `port-sdl` lines on card t_02418f83 (`agentws comment`); the card
  waits for the user's eye check (done-criterion 5). Re-run `make -C c check` and `build-all.sh --ports` once on the final
  HEAD and quote their last lines in the comment.

---

## Self-review notes

- **Spec coverage:** Goals 1-6 -> Tasks 6, 6/7, 5-7, 2 (gate green with the GRAY tests), 1-3, 9. GRAY section: API Task 2,
  rule Task 1/2, equalities Task 2, `test_args`/`test_kernels`/`test_pad`/gate Tasks 2-3, size/speed Task 3, AVR (16-bit
  arithmetic: `index_level` reused, shifts on `uint8_t`) Task 2. INDEX8 section Task 7; ARGB and `--alpha-demo` Tasks 6/7;
  surfaces/pitch/locking/presenting Task 6; streaming/cache Task 6; lines table Task 5; compat Task 6; headless check
  Tasks 5-7; build integration Tasks 4, 6, 8; screenshots/README Task 9; done criteria 1-6 Tasks 2-9; risks: P1\* stop
  rule Task 3, SDL3 drift Task 4/6, ASAN case Task 6, `xvfb-run` absent Task 9.
- **Settled here (spec left open or inconsistent):** dump header layout (16 bytes; "bpp" is bits per pixel, the SDL major in
  flag bits 4-5; the checker takes `--kind`/`--threshold` because ARGB vs XRGB and the threshold are not in the header);
  init's stride bound computed with bits 1; P5 (`0x1E8`) does not contain the GRAY bit so it is in the unchanged list,
  not the growth list; dos/web program sizes grow (default `SVF_TARGETS`) and are updated in Task 3; SDL binary sizes are
  `info` rows on their own SIZES.md line (the dos/web parenthesis is gated exactly); the checker builds its own expected
  buffer and the shot comparison is copied, so no DOS file moves; the bits-8 speed criterion is +1.0 % rp2040js cycles
  (deterministic emulator) plus equal host checksums; the matrix is 43-44 runs a SDL, not the spec's estimate of 34; `sdl_check.py` tests
  run from `check.sh`, not from `make -C c check`.
- **Type consistency:** `gray_bits` (C field, svfline keyword, svfdump `--gray-bits`, svfsdl `--gray-bits`), `lsb_first` /
  `--lsb-first` / `SVF_TF_GRAY_LSB_FIRST`, `BENCH_LINE_KIND`, `PICO_KINDS`, `SDL3_PREFIX`, `SDL3_COMMIT` used identically.
