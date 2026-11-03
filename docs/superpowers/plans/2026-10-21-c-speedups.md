# Portable C Speedups (SWAR merge, 1 bpp GRAY8 table, separable scaling, M33 and Hazard3 runners) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three hot kernels of the C SVF renderer (`svf__merge`, the 1 bpp case of `blit_gray8`, the
area-averaged branch of `svf__scale_cell`) faster on every target with portable C that is byte-identical to today,
and measure it before and after on every runner, including two new ones for the RP2350 (Cortex-M33 under QEMU
`mps2-an505` as instruction counts; Hazard3 and Cortex-M33 under rp2350js, which boots real pico-sdk `pico2` images
and counts cycles).

**Architecture:** The kernels change in place behind two new `svf.h` switches (`SVF_MERGE_WORDS`, `SVF_GRAY8_LUT1`)
that follow the `SVF_WORD_STORE` pattern; nothing public, no scratch size and no other blit changes. Exactness is
proved by the gates that exist (golden tests, bench checksums on every emulator, the VESA PNGs) plus one new exhaustive
host test, `c/tests/test_kernels.c`, written before any kernel changes as the net. The two RP2350 runners are
`run-m33.sh` (a `bench.c` section on the ESP32 reporter's pattern, `printf` lines for `report.awk`, one pinned Ubuntu
`qemu-system-arm` .deb added to `install-emulators.sh`) and `run-rp2350.sh` (a `bench.c` section of marker functions
in pico-sdk 2.3.1 `pico2` images for both cores, run under rp2350js at a pinned commit with a committed patch and read
by `rp2350-run.mjs` on `pico-run.mjs`'s pattern; the pinned `riscv32-pico-elf` toolchain builds the Hazard3 images).
Before/after comes from one tree: the baseline rows are captured on main 344a090 first, the after rows at the end.

**Tech Stack:** C99 (`-std=c99 -Wall -Wextra -Werror`), make, POSIX sh, Python 3 unittest
(`tools/test_c_renderer.py`); cross toolchains and emulators under `~/opt` (`c/cross/install-toolchains.sh`,
`c/bench/install-emulators.sh`): arm-none-eabi-gcc 15.2.1, riscv32-esp-elf-gcc 16.1.0, Espressif QEMU 9.2.2,
rp2040js 1.4.0, simavr 1.8, DOSBox-X 2026.08.31 (`/usr/bin/dosbox-x`), DJGPP gcc 12.2.0, emcc 6.0.13, node v24.13.0,
pico-sdk 2.3.1; new: Ubuntu `qemu-system-arm` 8.2.2 (.deb, `dpkg-deb -x`, no sudo), rp2350js at commit af0114c with
`c/bench/rp2350js.patch` (source tarball, `npm ci` from its lockfile, `tsc`), riscv32-pico-elf-gcc 16.1.0
(pico-sdk-tools v2.3.1-0); host `cmake` for the pico-sdk builds (not pinned, as for `build-all.sh --ports`).

**Spec:** `docs/superpowers/specs/2026-10-21-c-speedups-design.md` at commit 42b2395 (card t_662ef38c). Read it
first: every rule below is argued from it. The feasibility study it follows is
`<workdir>/svf-fonts-review/simd-feasibility.md`, the spike code `<workdir>/svf-fonts-review/simd-spike/`
(`kern.c`: `max2_32`, `merge2_swar`, `lut1`, `scale_sep`, `test_merge`, `test_scale`; `m33.c`, `m33.ld`: the M33
harness). Worktree: `<workdir>/svf-fonts-wt/c-speedups`, branch `c-speedups` from main 344a090 (the spec commit
42b2395 is on it; the library at 344a090 is the "before").

## Global Constraints

- Library (`c/src`, `c/include`): C99; only `<stdint.h>`, `<stddef.h>`, `<string.h>`; no `malloc` (`c/check.sh`
  no-malloc); no static data except `static const` tables (every object keeps data 0, bss 0 in `c/cross/SIZES.md`);
  no SIMD, no intrinsics, no inline asm; `-Werror` on every toolchain.
- **No fast mode.** Every change is byte-identical: `make -C c check`, `c/cross/build-all.sh --ports` (37 OK), every
  runner's checksums `ok`, the ten `c/ports/dos/shots/*.png` unchanged, `run-screens.sh` unchanged.
- Three functions change: `svf__merge` (svf_jamo.c), the 1 bpp case of `blit_gray8` (svf_draw.c), the area-averaged
  branch of `svf__scale_cell` (svf_scale.c). Every public declaration, the walker, the cache, the stream code, every
  other blit, `svf__scale_len`, `svf__scale_dim`, the block path and `svf_chain_scratch_bytes` stay as they are.
- `svf__merge(const svf_face *f, uint8_t *dst, const uint8_t *src, uint16_t n)` keeps its contract: any run of
  bytes, `src` in face memory read through `SVF__RD8`; the word form compiles only where `SVF_RD8_PLAIN` is defined
  or, with an override, runs only for a streamed face (`f->rd`).
- New switches, both in `svf.h` next to `SVF_WORD_STORE` (`#ifndef`, arch default, `-D` override), documented there:
  `SVF_MERGE_WORDS` (default 1 where `__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__` and not `__AVR__`, else 0),
  `SVF_GRAY8_LUT1` (default 1, 0 on `__AVR__`). `SVF_WORD_STORE` and `SVF_NO_SCALE` unchanged. No switch keeps the
  old 2 bpp merge loop or the old box filter: before/after is measured from git.
- Word access: `memcpy` only, never a pointer cast; on a strict-align target the destination word is accessed only
  after a run-time 4-alignment test and the source word is assembled from bytes (little-endian: that is why the
  switch defaults to 1 only there).
- Cortex-M0+ P1/P2 text <= 8192 B after every library task (`c/cross/build-all.sh` fails otherwise; now 5674),
  recorded in the commit message. The 8 KB budget does not apply to Cortex-M33 or Hazard3 rows (RP2350 is not the
  small target). AVR: `run-avr.sh` must still fit 32,256 B of flash.
- Every number written into `MEASUREMENTS.md` or `SIZES.md` is emulated or an instruction count and says so; the QEMU
  Cortex-M33 rows say "instructions ... not RP2350 cycles"; the rp2350js rows (Hazard3 and Cortex-M33) say "rp2350js
  cycles", the 150 MHz conversion (the SDK's `clk_sys`; rp2350js itself runs 125 MHz) and what rp2350js does not model
  (XIP flash and cache, bus contention, load-use stalls); a missed budget is written with its number.
- Every runner verifies its pinned tools (`--verify`) before use; the new downloads are the `qemu-system-arm` .deb
  (Task 3, sha256 pinned), the rp2350js source tarball at commit af0114c (sha256 pinned; its `package-lock.json` pins
  every npm package by integrity) and the `riscv32-pico-elf` 16.1.0 toolchain tarball of pico-sdk-tools v2.3.1-0
  (sha256 pinned, the publisher's digest) (Task 4). The RP2350 images are pico-sdk 2.3.1 `pico2` builds booted
  through the A2 boot ROM bundled in the pinned rp2350js source.
- Scripts quote every argument, use no `eval`, and (like `run-dos.sh`) check an output path before deleting under it.
- `make -C c check` green after every task; the Python tests it runs (`tools/test_c_renderer.py`) extended where a
  script or `bench.c` changes.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never add `.superpowers/`. No `git stash`.

## Review Focus

1. `svf__merge` on a streamed face whose piece row straddles two cache blocks: `svf__stream_rows` calls it twice with
   `dst + k` and an `n` that is not a multiple of 4, `dst + k` and `p + o` at any offsets mod 4; the word loop and its
   byte tail must give the reference bytes and touch nothing past `n` — Task 5 `test_merge_runs` (independent offsets
   0..3 on each pointer, `n` 0..199, guard bytes checked) and `make -C c check` (TestStream).
2. A 1 bpp GRAY8 blit whose cut starts and ends inside one source byte (a 3-pixel clip: `lo` and `hi` in the same byte)
   and one whose whole-byte run ends at the target's last column: no byte outside `[c0, c1)` may change — Task 5
   `test_gray8_lut1_cuts` at every `(lo, hi)` with `lo < hi` within and across bytes, with guard bytes on both sides.
3. A 1 bpp GRAY8 blit of a cell partly left of the target (`x = -3`, clip at 0): the whole-byte path must start at the
   first fully visible source byte, not at the cell's byte 0 — Task 5 `test_gray8_lut1_cuts` includes `x = -3` and
   `x = -8`.
4. `svf__scale_cell` where one source pixel feeds two output pixels across the 128-column accumulator block boundary
   (num > den, `sw` > 128) and where the last output span is clamped by `cell_w` (den > num, `cell_w` not a multiple
   of den) — Task 5 `test_scale_sweep` (48 x 48 cells at 16/3 give `sw` 256; 47 x 47 at 1/16 and 3/16 give clamped
   spans).
5. A 2 bpp merge of a byte pair whose fields are equal in the high bit but differ in the low bit in every position
   (0x55 against 0xAA, 0xFF against 0x00): the SWAR low-bit term must pick the right field — Task 5
   `test_merge2_pairs` (all 65,536 pairs through the byte form).
6. `rp2350-run.mjs`'s intervals: they open and close on the PC of the marker functions' first instruction, so a stop
   without a start, a report or end inside an open interval, a core-0 wait or a fault entry inside an interval must
   fail the run, never be counted; the calibration (`cal=empty`, `cal=loop1m` within 16 cycles of 2,000,000 Hazard3 /
   3,000,000 M33, and 2,000,000 instructions on both) must be checked on every build, and the counter must be core 0's
   — Task 4 `test_rp2350_run_reads_the_marks`, the calibration check in `run-rp2350.sh`, the two identical runs.

---

## File structure

```
c/include/svf.h                 SVF_MERGE_WORDS, SVF_GRAY8_LUT1 next to SVF_WORD_STORE (Task 6)
c/src/svf_internal.h            SVF__MERGE_UNALIGNED (Task 6)
c/src/svf_jamo.c                svf__merge: byte SWAR + word loop (Task 6)
c/src/svf_draw.c                svf__lut1 and the whole-byte path of blit_gray8 case 1 (Task 7)
c/src/svf_scale.c               separable box filter (Task 8)
c/src/svf_face.c                svf__glyph_index: the mid shift (Task 9)
c/tests/test_kernels.c          the exhaustive host net (Task 5)
c/Makefile                      test-kernels x 3 builds in check (Task 5)
c/bench/bench.c                 line40_scaled32 (Task 2); BENCH_M33 (Task 3); BENCH_RP2350 (Task 4)
c/bench/m33.ld                  bare-metal linker script (Task 3)
c/bench/run-m33.sh, run-rp2350.sh    the runners (Tasks 3, 4)
c/bench/rp2350/CMakeLists.txt   the pico-sdk project of the RP2350 bench images, both cores (Task 4)
c/bench/rp2350-run.mjs          runs an image under rp2350js and reads the marker functions (Task 4)
c/bench/rp2350js.patch          the four rp2350js fixes, applied at install (Task 4)
c/bench/install-emulators.sh    name qemu-arm: the pinned .deb (Task 3); name rp2350js (Task 4)
c/cross/install-toolchains.sh, install-lib.sh   name pico-rv: riscv32-pico-elf 16.1.0, a tarball with no top directory (Task 4)
c/bench/sums.py, sums.inc.sh    SUMS_LINE40 (Task 2)
c/bench/run-dos.sh, run-wasm.sh the scaled case (Task 2)
c/bench/mkface.py               arrays aligned to 4 (Task 6)
c/bench/check-measurements-md.py, measurements-raw.txt   M33 (QEMU) and RP2350 rp2350js rows (Tasks 3, 4, 10)
c/bench/MEASUREMENTS.md         baseline (Task 1), runner rows (Tasks 3, 4), before/after and Still over budget (Task 10)
c/cross/build-all.sh, SIZES.md  cortex-m33 and hazard3-rp2350 toolchain rows (Tasks 3, 4), re-measure (Task 10)
tools/test_c_renderer.py        TestBenchSums line sums, the stub builds and script tests of the two runners
```

Measured facts the tasks rely on (this host, 2026-10-21):

- The bench faces' glyph data: HGKEY6J `data_off` 4025, stride 32; PAPLG16 1824, stride 90; PAPLG18 24953, stride 90;
  MARUS24 27197, stride 72; MARUS24A 27197, stride 144. Every `data_off` but PAPLG16's is odd, so on a strict-align
  target **no** source row of the budget faces is 4-aligned: the word loop must assemble source words from bytes and
  may use a native word only for the destination (the caller's cell). `cmap_off` is 36 in every face.
- The 40 code point PAPLG line at 3/2: width 749, ascent 26, descent 6 (`svfline.measure`, 497/17/4 at 1/1), so the
  scaled case needs a 960 x 36 GRAY8 target; `svf_chain_scratch_bytes` for the chain at 3/2 is 909 bytes (90 at 1/1).
  Its checksum from `tools/svfline.py` (and `c/build/svfdump --scale=3/2 --target=gray8 line 960 36 0 28 ...`):
  `13e5d91d` over 34,560 bytes; the 1/1 line on 640 x 24 at baseline 19 is `d88e20f9` (as today).
- `qemu-system-arm_8.2.2+ds-0ubuntu1.18_amd64.deb`: 10,963,018 bytes, sha256
  `06184a21b9c8dc573ab6d255e9826cc4732df90e56bd65c52e92ad640af4d60a`, URL
  `http://archive.ubuntu.com/ubuntu/pool/main/q/qemu/qemu-system-arm_8.2.2%2bds-0ubuntu1.18_amd64.deb` (a copy is in
  `/tmp/simd-dl/`); `dpkg-deb -x` gives `usr/bin/qemu-system-arm` ("QEMU emulator version 8.2.2 (Debian
  1:8.2.2+ds-0ubuntu1.18)"), which runs with the host's shared libraries (`ldd`: nothing missing) and needs no data
  files for `-M mps2-an505`. Under `-icount shift=0` one SysTick tick is exactly 50 instructions (a 1,000,000 x
  `subs; bne` loop reads 40,000 ticks).
- The M33 bare-metal shape was run end to end under QEMU while planning (output, calibration, exit codes 0 and 3): the
  probe sources were `/tmp/plan-probe/m33/{m33.c,m33.ld}` (volatile; Task 3 carries everything they contained).
- The RP2350 shape (re-plan, 2026-10-21): `bench.c` with marker functions in pico-sdk 2.3.1 `pico2` images (Hazard3:
  `-DPICO_PLATFORM=rp2350-riscv` with riscv32-pico-elf-gcc 16.1.0, pico-sdk's `-mcpu=hazard3-rp2350 -mstrict-align`;
  M33: `rp2350-arm-s` with arm-none-eabi-gcc 15.2.1), booted under rp2350js af0114c + the four fixes of
  `c/bench/rp2350js.patch` through its A2 boot ROM, gave all 120 rows `ok` (both cores, 8 builds each), byte-identical
  on a second run; the calibration loop of 1,000,000 x 2 instructions read 2,000,004-2,000,006 cycles (Hazard3) and
  3,000,001-3,000,002 (M33) above the empty interval (7-8 / 11-12 cycles); without the patch the Hazard3 images fail.
  rp2350js keeps `clk_sys` at 125 MHz (the SDK sets 150): the rows convert its cycles at 150 MHz. The probes were in
  `/tmp` (volatile; Task 4 carries everything they contained).

---

### Task 1: Baseline on 344a090

**Files:**
- Modify: `c/bench/MEASUREMENTS.md` (only rows that drifted)

**Interfaces:**
- Produces: `c/build/bench/before/{host,dos,wasm,pico,pico-prof,esp32,avr}/` (untracked run directories) and
  `c/build/cross-before/` (the `build-all.sh` size table), which Task 10 reads as the "before".

- [ ] **Step 1: Confirm the tree is the baseline**

Run: `git log --oneline -3` and `git diff --stat 344a090 -- c/src c/include c/bench c/cross`
Expected: HEAD is 42b2395 (or later docs-only commits); the diff lists only `docs/` files.

- [ ] **Step 2: Run the host gate**

Run: `make -C c check 2>&1 | tail -n 8`
Expected: `no-malloc: OK`, `targets: OK cc`, `asan: OK`, `targets: OK <clang>`, `clang: OK (...)`, exit 0.

- [ ] **Step 3: Run every runner into the before directories**

Run, in order (each prints Markdown rows; keep the raw output):
```bash
sh c/bench/run-host.sh c/build/bench/before/host | tee c/build/bench/before/host.md
sh c/bench/run-dos.sh c/build/bench/before/dos | tee c/build/bench/before/dos.md; echo "exit $?"
sh c/bench/run-wasm.sh c/build/bench/before/wasm | tee c/build/bench/before/wasm.md; echo "exit $?"
sh c/bench/run-pico.sh c/build/bench/before/pico | tee c/build/bench/before/pico.md; echo "exit $?"
PROFILE=1 sh c/bench/run-pico.sh c/build/bench/before/pico-prof | tee c/build/bench/before/pico-prof.md; echo "exit $?"
sh c/bench/run-esp32.sh c/build/bench/before/esp32 | tee c/build/bench/before/esp32.md; echo "exit $?"
sh c/bench/run-avr.sh c/build/bench/before/avr | tee c/build/bench/before/avr.md; echo "exit $?"
```
Expected: `run-host.sh` ends `end=0`; `run-dos.sh` and `run-pico.sh` exit 2 (budgets already missed: `**missed**`
rows exist) and every row ends `ok |`; `run-wasm.sh`, `run-esp32.sh`, `run-avr.sh` exit 0; no row contains
`**expected`.

- [ ] **Step 4: Run the size table and the ports gate**

Run: `sh c/cross/build-all.sh c/build/cross-before | tee c/build/cross-before.md` then
`sh c/cross/build-all.sh --ports c/build/cross-ports 2>&1 | tee c/build/cross-ports.log | grep -c ': OK'`
Expected: every toolchain `OK`; the table's `cortex-m0plus | 15.2.1 | P1 | 5674` and `P2 | 5674` rows; the ports
run prints `37`, exit 0.

- [ ] **Step 5: Run the VESA shots and confirm the PNGs are the committed ones**

Run: `bash c/ports/dos/vesa-shots.sh c/build/ports/dos-vesa; git status --short c/ports/dos/shots`
Expected: exit 0; `git status` prints nothing (ten PNGs byte-identical to the committed files).

- [ ] **Step 6: Compare the fresh rows with MEASUREMENTS.md**

For each table of `c/bench/MEASUREMENTS.md` (Pico MONO_PAGE/GRAY8/RGB565, Uno, DOS 486, Packed kinds, WASM,
ESP32-C3, ESP32-S3): compare the cycles / instructions / µs / checksum columns with the Step 3 rows (`diff` on the
case rows after cutting the build column; the DOS µs may differ by up to 0.03 µs mapped and 0.033 % streamed, the
WASM times are host times and are not compared). Where a Pico, ESP32, Uno or DOS row differs beyond that spread,
replace the row with the fresh one and note the date and commit above the table ("re-measured 2026-10-21 on
344a090"). Run `python3 -I c/bench/check-measurements-md.py c/bench/MEASUREMENTS.md` after any edit (silent, exit 0;
regenerate `measurements-raw.txt` with `--raw c/build/bench/before/pico c/build/bench/before/esp32` and the ratio
block with `--print` if a Pico or ESP32 row moved).

- [ ] **Step 7: Commit (only if a row moved)**

```bash
git add c/bench/MEASUREMENTS.md c/bench/measurements-raw.txt
git commit -m "bench: baseline rows re-measured on main 344a090 before the C speedups"
```
If nothing moved, no commit: write "baseline identical to MEASUREMENTS.md" in the task report.

---

### Task 2: The scaled bench case `line40_scaled32`

**Files:**
- Modify: `c/bench/bench.c:536-549` (line section constants and `screen`), `c/bench/bench.c:551` (`scratch`),
  `c/bench/bench.c:716-760` (`main` of the line section)
- Modify: `c/bench/sums.py`, `c/bench/sums.inc.sh`, `c/bench/run-dos.sh:31-45`, `c/bench/run-wasm.sh:22-25`
- Test: `tools/test_c_renderer.py` (`TestBenchSums`)

**Interfaces:**
- Produces: bench case `line40_scaled32`: the 40 code point line (`line_text`) drawn by the mapped PAPLG16 + PAPLG18
  chain with `scale_num 3, scale_den 2`, no syllable cache, on `SVF_T_GRAY8` 960 x 36 (stride 960) at (0, 28),
  `BENCH_LINE_N` iterations, checksum FNV-1a over the 34,560 bytes: `13e5d91d`. Constants `SCALED_W 960`,
  `SCALED_H 36`, `SCALED_Y 28` in `bench.c`. `sums.inc.sh` gains
  `SUMS_LINE40="line40_mapped:d88e20f9 line40_mapped_cache:d88e20f9 line40_stream_cold:d88e20f9 line40_stream_warm:d88e20f9 line40_stream_small:d88e20f9 line40_stream_nocache:d88e20f9 line40_scaled32:13e5d91d"`
  (printed by `sums.py` as a fourth line after the three kinds, computed with `svfline`); `sums_for_faces` in
  `sums.inc.sh` recomputes it with the other three when `FACE16`/`FACE18` are overridden (its loop gains `LINE40`);
  Tasks 3 and 4 use it for their line builds.

- [ ] **Step 1: Write the failing test**

In `TestBenchSums` of `tools/test_c_renderer.py` add:
```python
def test_host_line_build_matches_sums_line40(self):
    """The host line build (no BENCH_MCU) prints the SUMS_LINE40 checksums: the 1/1 line and the 3/2 line, both
    computed by svfline (sums.py)."""
    want = bench_sums()["LINE40"]            # bench_sums() already returns every SUMS_<name> line sums.py prints
    with tempfile.TemporaryDirectory() as tmp:
        r = run_in_session(["sh", os.path.join(BENCH, "run-host.sh"), os.path.join(tmp, "line")], dict(os.environ), 300)
    self.assertEqual(r.returncode, 0, r.stderr)
    got = dict(re.findall(r"case=(line40_\w+) .* sum=([0-9a-f]{8})", r.stdout))
    for pair in want.split():
        name, s = pair.split(":")
        self.assertEqual(got.get(name), s, name)
```
and in `sums.py` a `set_line()` that draws `line_text` at 1/1 on `gray8` 640 x 24 at (0, 19) and at `scale=(3, 2)` on
960 x 36 at (0, 28) (`svfline.placements(..., scale=(3, 2))`, `draw_target`), refusing clipping as `draw()` does but
measuring with `svfline.measure(paths, text, scale=(3, 2))` for the scaled line (749 x 26 + 6 must fit 960 x 36 at
baseline 28), and prints `SUMS_LINE40="..."` with the seven names above. `TestBenchSums.test_host_matches_sums_inc`
already compares every `SUMS_` line of `sums.inc.sh` with `sums.py`: add the line to `sums.inc.sh`, and add `LINE40`
to the `for _k in MONO_PAGE GRAY8 RGB565` loop of `sums_for_faces` there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -I c/bench/sums.py | tail -n 1` and
`python3 -m unittest tools.test_c_renderer.TestBenchSums -v 2>&1 | tail -n 6`
Expected: `SUMS_LINE40="... line40_scaled32:13e5d91d"`; `test_host_line_build_matches_sums_line40` FAILS (no
`line40_scaled32` case in the host output).

- [ ] **Step 3: Add the case to `bench.c`**

In the line section: `#define SCALED_W 960`, `#define SCALED_H 36`, `#define SCALED_Y 28`; the non-DOS/host `screen`
becomes `static uint8_t screen[SCALED_W * SCALED_H];` (the DOS/host one, 81,920 bytes, already holds it);
`static uint8_t scratch[1024];` (909 needed at 3/2). A function
`static void scaled_case(svf_chain *c)` that sets `c->scale_num = 3; c->scale_den = 2;`, checks
`svf_chain_scratch_bytes(c) <= sizeof scratch` (else `bench_end(97)`), inits a GRAY8 target on `screen` 960 x 36
stride 960, clears it once, draws `line_text` `BENCH_LINE_N` times at (0, `SCALED_Y`) between `bench_start` /
`bench_stop`, `check(e, 11)`, reports `"line40_scaled32"` with `fnv1a(screen, SCALED_W * SCALED_H)`, then resets
`scale_num = scale_den = 0`. Call it in `main` right after `line40_mapped_cache` (cache released) and before
`packed_cases`. Update the header comment's case list.

- [ ] **Step 4: Add the case to the DOS and WASM runners**

`run-dos.sh`: add `line40_scaled32:13e5d91d` to `SUMS` and `line40_scaled32_bytes:13e5d91d` to `SUMSB`, **not** to
`BUDGETS`/`BUDGETSB` (the 16 ms budget is the 1/1 line; build the lists so a case can have a sum without a budget).
`run-wasm.sh`: source `sums.inc.sh` and use `SUMS=$SUMS_LINE40`; `BUDGETS` unchanged (six cases).

- [ ] **Step 5: Run the tests and the two runners**

Run: `python3 -m unittest tools.test_c_renderer.TestBenchSums -v 2>&1 | tail -n 6`;
`sh c/bench/run-host.sh c/build/bench/host | grep scaled`; `sh c/bench/run-wasm.sh; echo "exit $?"`;
`sh c/bench/run-dos.sh | grep -c 'ok |'; echo "exit ${PIPESTATUS[0]}"`
Expected: tests PASS; host prints `case=line40_scaled32 ... sum=13e5d91d`; WASM exit 0 with a `line40_scaled32`
row `13e5d91d ok` and budget `-`; DOS: 2 presets x 2 builds x 20 cases (19 today + the scaled one) = 80 `ok` rows,
exit 2 (as before).

- [ ] **Step 6: Record the before rows**

Append the `line40_scaled32` DOS (both presets, both builds) and WASM rows to the matching tables of
`c/bench/MEASUREMENTS.md` (the case description in "What is measured": "the same line at 3/2 on GRAY8 960 x 36,
baseline 28, mapped, no syllable cache; no budget"). MEASUREMENTS.md has no host table today: add a short section
`### Host (x86-64; host CPU times, not an emulation)` after the WASM section with the seven `line40_*` rows of
`run-host.sh` (`report.awk` shape, the build column naming the host CPU and compiler, budget `-`). Copy the run
directories to `c/build/bench/before/` (`host`, `dos`, `wasm`), replacing Task 1's:
`mkdir -p c/build/bench/before && sh c/bench/run-host.sh c/build/bench/before/host >c/build/bench/before/host.md`,
`sh c/bench/run-dos.sh "$PWD/c/build/bench/before/dos" >c/build/bench/before/dos.md` (`run-dos.sh` refuses a
relative OUT), `sh c/bench/run-wasm.sh c/build/bench/before/wasm >c/build/bench/before/wasm.md`.

- [ ] **Step 7: Commit**

```bash
git add c/bench/bench.c c/bench/sums.py c/bench/sums.inc.sh c/bench/run-dos.sh c/bench/run-wasm.sh tools/test_c_renderer.py c/bench/MEASUREMENTS.md
git commit -m "bench: line40_scaled32 (the PAPLG line at 3/2 on GRAY8 960x36) on host, DOS and WASM; SUMS_LINE40 from svfline"
```

---

### Task 3: The Cortex-M33 runner (`run-m33.sh`)

**Files:**
- Modify: `c/bench/install-emulators.sh` (name `qemu-arm`), `c/bench/bench.c:62-69` (the one-of check, `BENCH_MCU`),
  `c/bench/bench.c:130-280` (the QEMU reporter branch), `c/cross/build-all.sh` (`try cortex-m33`),
  `c/cross/SIZES.md` (toolchain row, size rows), `c/bench/check-measurements-md.py`, `c/bench/MEASUREMENTS.md`
- Create: `c/bench/m33.ld`, `c/bench/run-m33.sh`
- Modify: `c/cross/test-installers.sh` (a `qemu-arm` case; manual check, committed)
- Test: `tools/test_c_renderer.py` (`TestBenchSums`)

**Interfaces:**
- Consumes: `SUMS_MONO_PAGE`, `SUMS_GRAY8`, `SUMS_RGB565`, `SUMS_LINE40` from `sums.inc.sh` (Task 2); `guard.sh`
  (`run_guarded`, `verify_ok`, `note_unpinned`); `report.awk` with `-v mhz=150 -v exact=1`.
- Produces: `-DBENCH_M33` in `bench.c`: a member of the QEMU reporter branch (`#elif defined(BENCH_ESP32C3) ||
  defined(BENCH_ESP32S3) || defined(BENCH_M33)`), `BENCH_SYL_N 100u`, `BENCH_SCREEN_N 20u`,
  `BENCH_LINE_N 20u` there; `BENCH_MCU` is **not** implied by `BENCH_M33` (the runner passes `-DBENCH_MCU` for the
  set A/B builds and omits it for the line build, as `run-host.sh` does); `-DBENCH_ESP_STUB` compiles the section on
  the host with faked counters (the existing stub, now shared by the four QEMU sections). Output lines are the C3's
  (`case=NAME iters=N cycles=C per_iter_cycles=P.F sum=S`, `end=0`) preceded by one calibration line
  `cal=loop2m ticks=T insns=I` with `I = T * 50`. Installer name `qemu-arm`, tree
  `$PREFIX/qemu-system-arm-8.2.2-0ubuntu1.18/` (the .deb's `usr/` tree), binary `usr/bin/qemu-system-arm`,
  `MANIFEST_PIN_qemu_arm`. Runner `c/bench/run-m33.sh [OUT]` (default `c/build/bench/m33`), env `QEMU_ARM`, `LIMIT`,
  `FACE/FACE16/FACE18`; 8 builds: {MONO_PAGE 0x02, GRAY8 0x01, RGB565 0x08} x {-Os, -O2} with `-DBENCH_MCU
  -DSVF_NO_SCALE -DSVF_TARGETS=<bit> -DBENCH_KIND=SVF_T_<kind>`, plus the line build at -Os and -O2 (no `BENCH_MCU`,
  default `SVF_TARGETS`, scaling in, faces 16 and 18); raw output `OUT/run-<opt>-<NAME>.txt` with NAME in
  `MONO_PAGE GRAY8 RGB565 LINE` and opt `Os`/`O2`. Row label: `Cortex-M33 emulated (QEMU 8.2.2 mps2-an505 -icount
  shift=0: SysTick ticks x 50 = instructions, not RP2350 cycles; arm-none-eabi-gcc 15.2.1 <opt>; <NAME>,
  SVF_TARGETS=<mask>)`, `mhz=150` (RP2350 clock: the µs column is an estimate at one instruction per cycle at 150 MHz). Exit 0 only when every
  row is `ok` and the calibration holds; 1 otherwise. Toolchain row `cortex-m33` in `build-all.sh` and `SIZES.md`.

- [ ] **Step 1: Write the failing tests**

In `tools/test_c_renderer.py`:
- `test_esp_sections_compile_and_report_on_host`: extend the `(chip, extra)` tuple with `("M33", ["-DBENCH_MCU"])`
  (the loop passes no `-DBENCH_MCU` of its own and `BENCH_M33` does not imply it: without the flag the stub would
  compile the line section, not the MCU cases the test checks), and for M33 assert the output has exactly one line
  matching `^cal=loop2m ticks=(\d+) insns=(\d+)$` with `insns == ticks * 50`.
- `test_run_scripts_fail_on_a_missing_install`: add `"run-m33.sh"` (expects exit 1 and "not installed" with
  `OPT` pointing at an empty directory).
- `test_run_scripts_leave_no_emulator_when_terminated`: add `("run-m33.sh", "QEMU_ARM")` with the tool check
  `arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc`, and skip that entry (`unittest.SkipTest`) unless
  `sh c/bench/install-emulators.sh --verify qemu-arm` exits 0 and prints `qemu-arm: OK` (as
  `test_run_pico_names_the_guard_exit` does for rp2040js): `run-m33.sh` runs `verify_ok ... qemu-arm` even with
  `QEMU_ARM` overridden, so on a host without the pinned tree it would exit before the fake emulator starts.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest tools.test_c_renderer.TestBenchSums -v 2>&1 | grep -E "M33|m33|FAIL|ERROR" | head`
Expected: the M33 stub build fails to compile (`#error "build with exactly one of ..."`), the two script tests fail
(no `run-m33.sh`).

- [ ] **Step 3: Add `qemu-arm` to `install-emulators.sh`**

Constants `QEMU_ARM_URL` (the pool URL above), `QEMU_ARM_SHA256`
`06184a21b9c8dc573ab6d255e9826cc4732df90e56bd65c52e92ad640af4d60a`, `QEMU_ARM_LOCAL=$DL/qemu-arm/qemu-system-arm.deb`,
`QEMU_ARM=$PREFIX/qemu-system-arm-8.2.2-0ubuntu1.18`. Install: `fetch_sha qemu-arm URL SHA LOCAL`, then
`dpkg-deb -x "$FETCHED" "$QEMU_ARM"` (refuse if `dpkg-deb` is missing), check `usr/bin/qemu-system-arm --version`
prints `QEMU emulator version 8.2.2`, `written qemu-arm "$QEMU_ARM" "$QEMU_ARM_SHA256"`; verify: `manifest_verify`
against `MANIFEST_PIN_qemu_arm`; adopt: compare with a fresh `dpkg-deb -x` of the verified download (`mode=exact`).
Add the name to the usage lines, the header comment (what the .deb is, that the Ubuntu pool drops superseded
versions so the copy under `PREFIX/dl/qemu-arm/` is the durable source, as DJGPP's note says), the `--verify`
default list, **all three** "unknown name" lists (the `verify` and `adopt` `case` fallbacks and the install `NAMES`
check) and an install branch (`if want qemu-arm; then ... fi`, with the `absent` / `dest_ok` / `present` shape of the
QEMU loop). `c/cross/test-installers.sh`: a `qemu-arm` case (fresh install into a temporary PREFIX from the real
`dl/` copy, `--verify`, `--adopt`), skipped with the script's "skipped (no ...)" line when
`$REAL/dl/qemu-arm/qemu-system-arm.deb` is absent. Install it: copy `/tmp/simd-dl/qemu-system-arm_*.deb` to
`~/opt/dl/qemu-arm/qemu-system-arm.deb`, run `sh c/bench/install-emulators.sh ~/opt qemu-arm`, paste the printed
pin, then `sh c/bench/install-emulators.sh --verify qemu-arm` prints `qemu-arm: OK`.

- [ ] **Step 4: Add the `BENCH_M33` section to `bench.c` and `c/bench/m33.ld`**

`m33.ld`: `MEMORY { RAM (rwx) : ORIGIN = 0x10000000, LENGTH = 4M }`; `.text` with `KEEP(*(.vectors))` first, then
`*(.text*) *(.rodata*)`; `.data`; `.bss (NOLOAD)` bracketed by `__bss_start__`/`__bss_end__` (ALIGN 4); then
`end = .;` (libnosys `_sbrk`) and `__stack_top = ORIGIN(RAM) + LENGTH(RAM)`. The section (outside
`BENCH_ESP_STUB`): a 16-entry vector table in `.vectors` (`&__stack_top`, `reset_handler`, faults to a handler that
calls `bench_end(99)`, entry 15 `systick_handler` incrementing a `volatile uint32_t wraps`); `reset_handler` zeroes
`.bss` and calls `main`, then `bench_end` with its result; `bench_calibrate()` (M33: programs SysTick with
`SYST_RVR 0xFFFFFF`, `SYST_CVR 0`, `SYST_CSR 7`, waits for the first tick, runs 1,000,000 iterations of `subs; bne`
and prints `cal=loop2m ticks=%lu insns=%lu` with `insns = ticks * 50`) is called at the top of **both** `main`s
under `#if defined(BENCH_ESP32S3) || defined(BENCH_M33)` (the S3's call today; the line section's `main` gets the
same two lines); `bench_now()` returns `(wraps * 0x1000000 + (0xFFFFFF - SYST_CVR)) * 50` read wrap-stable (the
spike's `plat_now`), so the C3's `bench_start`/`bench_stop`/`bench_report` are shared unchanged. The branch's inner
`#if defined(BENCH_ESP32C3) ... #else` (the S3) becomes `#if defined(BENCH_ESP32C3)` /
`#elif defined(BENCH_ESP32S3)` / `#else` (the M33), the S3's `BENCH_ICOUNT_SHIFT` `#error`s staying in its arm;
`bench_exit(code)` is semihosting
`SYS_EXIT_EXTENDED` (`bkpt 0xAB` with r0 = 0x20, r1 -> `{0x20026, code}`: on 32-bit ARM plain `SYS_EXIT` cannot carry a
code); `int _write(int fd, const void *buf, size_t n)` sends the bytes through `SYS_WRITE0` (r0 = 0x04, r1 = a
NUL-terminated copy, in chunks of at most 63 bytes). With `BENCH_ESP_STUB` the stub prints
`cal=loop2m ticks=40000 insns=2000000`. Extend the "exactly one of" `#error` and the `BENCH_MCU` comment. (Hazard3 is
not a QEMU section: Task 4 measures it under rp2350js in its own `BENCH_RP2350` section.)

- [ ] **Step 5: Write `c/bench/run-m33.sh`**

On the `run-esp32.sh` pattern: header comment (what the number is: SysTick ticks x 50 under `-icount shift=0`, a
granularity of 50 instructions per interval, no pipeline or memory timing, not RP2350 cycles; no budget);
`ARM=$OPT/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi`, `QEMU_ARM=${QEMU_ARM:-$OPT/qemu-system-arm-8.2.2-0ubuntu1.18/usr/bin/qemu-system-arm}`;
`note_unpinned m33 QEMU_ARM ...`; `verify_ok m33 "$C/cross/install-toolchains.sh" arm`;
`verify_ok m33 "$HERE/install-emulators.sh" qemu-arm`; `sums_for_faces m33 ...`; faces by `mkface.py` as
`run-esp32.sh`. The sums of a build are selected with a `case $name in MONO_PAGE) SUMS=$SUMS_MONO_PAGE ;; ... LINE)
SUMS=$SUMS_LINE40 ;; esac`, **not** `run-esp32.sh`'s `eval` (Global Constraints: no `eval` in new scripts).
Compile line (set A/B builds):
`"$ARM-gcc" -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -mcpu=cortex-m33 -mthumb $opt -DBENCH_M33 -DBENCH_MCU -DSVF_NO_SCALE -DSVF_TARGETS=$bit -DBENCH_KIND=SVF_T_$name -I "$C/include" "$HERE/bench.c" "$C"/src/*.c "$OUT/face.c" "$OUT/face16.c" "$OUT/face18.c" -T "$HERE/m33.ld" --specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,--gc-sections -Wl,--no-warn-rwx-segments -o "$OUT/bench-$tag.elf"`;
the line builds drop `-DBENCH_MCU -DSVF_NO_SCALE -DSVF_TARGETS= -DBENCH_KIND=` and `face.c` and add
`-u _printf_float` (the line section prints `reads_per_iter=%.1f`; nano's `printf` prints an empty value without it;
the call is outside every timed interval, say so in the header comment). Run:
`run_guarded ... "$QEMU_ARM" -M mps2-an505 -semihosting -icount shift=0,sleep=off -nographic -monitor none -serial none -kernel "$OUT/bench-$tag.elf"`.
After each run an awk check of the calibration line: exactly one `cal=loop2m` line, `insns == ticks * 50`,
`|insns - 2000000| <= 2000`; a failure prints `m33: calibration failed ($tag)` and sets status 1. Rows by
`report.awk` with the label above, `-v mhz=150 -v sums="$SUMS" -v exact=1` (line builds: `$SUMS_LINE40`).

- [ ] **Step 6: Add the toolchain row**

`build-all.sh`: after `try cortex-m0plus`, `try cortex-m33 "$(version "$ARM-gcc")" "$ARM-gcc" "$ARM-size" "-mcpu=cortex-m33 -mthumb -Os" "--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"`
(no budget line: the budget test keys on `cortex-m0plus`). `SIZES.md`: a `cortex-m33` row in the Toolchains table
(same tarball as `cortex-m0plus`, flags `-mcpu=cortex-m33 -mthumb -Os`, "RP2350 ARM core; no budget") and its eight
P rows in the Sizes table from `sh c/cross/build-all.sh c/build/cross`.

- [ ] **Step 7: Run the tests and the runner**

Run: `python3 -m unittest tools.test_c_renderer.TestBenchSums -v 2>&1 | tail -n 12`;
`mkdir -p c/build/bench/before && (set -o pipefail; sh c/bench/run-m33.sh "$PWD/c/build/bench/before/m33" | tee c/build/bench/before/m33.md); echo "exit $?"`
(the raw `run-<opt>-<NAME>.txt` files land in `before/m33/`, where Step 8 and Task 10 read them; `pipefail` reports
the runner's status, not `tee`'s); `sh c/cross/test-installers.sh`
Expected: tests PASS; the runner prints the rows of 8 builds (MONO_PAGE 5 cases, GRAY8 9, RGB565 9, LINE 7, each
at `-Os` and `-O2`: 60 rows), one `cal=loop2m` line per build with `insns == ticks * 50` and `insns` within 0.1 % of
2,000,000, every row `ok`, exit 0; `installers: OK` (or "skipped" if the real `dl/` copies are absent).

- [ ] **Step 8: Record the rows and extend the checker**

`MEASUREMENTS.md`: a "How time is measured" row and a provenance row for QEMU 8.2.2 (the .deb URL, size, sha256,
`dpkg-deb -x`, host shared libraries), and a section `### Cortex-M33 (RP2350 ARM core; no budget; instruction counts)`
with the C3 section's shape (a short paragraph on what the number is, then one table per kind headed
`MONO_PAGE (\`-DSVF_TARGETS=0x02\`)`, `GRAY8 (...)`, `RGB565 (...)`, `LINE (default \`SVF_TARGETS\`, scaling on)`:
`| case | iterations | -Os instructions/iteration | -O2 instructions/iteration | -Os µs at 150 MHz, 1 instruction/cycle estimate |
-O2 µs at 150 MHz, 1 instruction/cycle estimate |`). `check-measurements-md.py`: `parse` recognises `### Cortex-M33` as section `M33`
with `mhz 150` and the kind line `LINE (` as kind `LINE`; `make_raw` takes an optional fourth and fifth directory
(`--raw PICO ESP32 [M33 [RP2350]]`) reading `run-<opt>-<KIND>.txt` for `M33`; regenerate `measurements-raw.txt`
with the Task 1 Pico and ESP32 directories and `c/build/bench/before/m33`.
Run: `python3 -I c/bench/check-measurements-md.py c/bench/MEASUREMENTS.md; echo $?` — Expected: silent, 0.

- [ ] **Step 9: Commit**

```bash
git add c/bench/install-emulators.sh c/bench/bench.c c/bench/m33.ld c/bench/run-m33.sh c/cross/build-all.sh c/cross/SIZES.md c/cross/test-installers.sh c/bench/check-measurements-md.py c/bench/measurements-raw.txt c/bench/MEASUREMENTS.md tools/test_c_renderer.py
git commit -m "bench: Cortex-M33 runner (QEMU 8.2.2 mps2-an505, SysTick x 50 = instructions), pinned qemu-system-arm .deb, cortex-m33 size rows"
```

---

### Task 4: The RP2350 runner under rp2350js (`run-rp2350.sh`: Hazard3 and Cortex-M33, cycles)

> Re-planned 2026-10-21 (user: "4번을 rp2350js로 바꾸자", "다 추정이면 돌아가는 쪽이 좋다"): the QEMU `virt` Hazard3 runner
> is replaced. Pre-flight rulings this task honours: **F1** (`mkdir -p` first, `set -o pipefail`), **F4** (the run
> goes to an absolute `before/rp2350` directory so `--raw` finds the raw files), **F7** (consumed: `sums_for_faces`
> recomputes `SUMS_LINE40`), **F8** (adapted: the new section's compile test passes `-DBENCH_MCU` for the MCU builds;
> `BENCH_RP2350` does not imply it), **F9** (adapted: the SIGTERM test's entry runs only when `rp2350js`, `pico-rv`
> and `pico-sdk` verify), **F10** (sums by `case`, no `eval`), **F20** (adapted: each new installer name goes into
> every "unknown name" list, the usage, the header, the `--verify` default list, an install branch and a
> `test-installers.sh` case), **F23** (RGB565 builds and the default-`SVF_TARGETS` LINE build, as Task 3). Dropped:
> **F11** (no newlib-nano here: pico-sdk's own `printf` formats floats, and no stdio driver is initialised, so the
> `reads_per_iter` line goes nowhere and nothing reads it), **F21** (no QEMU `-cpu` properties to remove), **F22** (no
> QEMU reporter branch: `BENCH_RP2350` is its own section with no `bench_exit`, `_write`, `_start` or `__getreent`).

**Files:**
- Create: `c/bench/rp2350js.patch` (Appendix A: a header comment, then the four fixes as a unified diff),
  `c/bench/rp2350/CMakeLists.txt`, `c/bench/rp2350-run.mjs`, `c/bench/run-rp2350.sh`
- Modify: `c/bench/install-emulators.sh` (name `rp2350js`), `c/cross/install-toolchains.sh` (name `pico-rv`),
  `c/cross/install-lib.sh` (`unpack` of a tarball with no top directory), `c/cross/test-installers.sh` (both names),
  `c/bench/bench.c` (header comment, one-of check, `BENCH_MCU` comment, the `BENCH_RP2350` section, the two
  `bench_calibrate()` calls), `c/cross/build-all.sh` (`try hazard3-rp2350`), `c/cross/SIZES.md`,
  `c/bench/check-measurements-md.py`, `c/bench/measurements-raw.txt`, `c/bench/MEASUREMENTS.md`
- Test: `tools/test_c_renderer.py` (`TestBenchSums`)

**Interfaces:**
- Consumes: `SUMS_*` and `sums_for_faces` (Task 2), `guard.sh` (`run_guarded`, `verify_ok`, `note_unpinned`,
  `guard_why`), `report.awk` with `-v mhz=150 -v exact=1 -v need_insns=1`, `mkface.py`, pico-sdk 2.3.1
  (`install-toolchains.sh` name `pico-sdk`), arm-none-eabi-gcc 15.2.1 (name `arm`), node v24.13.0.
- Produces, installers:
  - `install-toolchains.sh` name **`pico-rv`**: Raspberry Pi's `riscv32-pico-elf-gcc` 16.1.0, pico-sdk-tools release
    v2.3.1-0, `PRV_URL=https://github.com/raspberrypi/pico-sdk-tools/releases/download/v2.3.1-0/riscv-toolchain-16-x86_64-lin.tar.gz`
    (129,680,495 bytes), `PRV_SHA=fc36f1b37f99de54a358115443638023de34e15fe199e718e50cca4d212e7e9f` (the release asset's
    published digest, checked 2026-10-21 through the GitHub API, and the sha256 of the copy on this host), tree
    `$PREFIX/pico-riscv-toolchain-16-v2.3.1-0` (bin `riscv32-pico-elf-gcc`), `MANIFEST_PIN_pico_rv`. The tarball has
    **no top directory** (`bin/ include/ lib/ libexec/ riscv32-pico-elf/ share/` at its root): `install-lib.sh`'s
    `unpack NAME FILE DEST` gains a fourth argument `flat` under which the fresh unpack directory itself is moved to
    DEST (and the "one top directory" check is skipped); `reg pico-rv` sets `R_FLAT=flat` and `tool`/`adopt` pass it.
    pico-sdk 2.3.1 finds the compiler by its triple (`PICO_GCC_TRIPLE` default list starts with `riscv32-pico-elf`)
    under `-DPICO_TOOLCHAIN_PATH`. Why this toolchain and not the ESP gcc: the real `pico2` RISC-V build is made with
    it; it accepts pico-sdk's `-mcpu=hazard3-rp2350` (the ESP gcc 16.1.0 does not, spec section "RP2350 RISC-V") and
    carries the Zb* multilib.
  - `install-emulators.sh` name **`rp2350js`**: github.com/c1570/rp2350js commit
    `af0114cbee8e9e91574204b66f10aa2961cbf28c` (rp2350js 2.0.1, MIT), `RPJS_URL=https://github.com/c1570/rp2350js/archive/af0114cbee8e9e91574204b66f10aa2961cbf28c.tar.gz`
    (1,246,966 bytes), `RPJS_SHA256=2bcf172e083c53671df4a5787a793bca5aa5ee5451098a84f017852eb227bcf2` (computed: GitHub
    publishes no checksum for a generated archive; two downloads on 2026-10-21 agreed), durable copy
    `RPJS_LOCAL=$DL/rp2350js/rp2350js-af0114c.tar.gz` (kept on first fetch, as qemu-arm's .deb: GitHub may regenerate
    archives), `RPJS_LOCK_SHA256=dd88d3100bd97acdcaa3daa3c2c931590938cd5a42d72e2daf7978d684f24e05` (the tarball's
    `package-lock.json`, checked after unpack so a reader sees what pins the npm tree), tree `RPJS=$PREFIX/rp2350js-af0114c`,
    `MANIFEST_PIN_rp2350js`. Build (`build_rpjs DEST`, in the work area): `fetch_sha` the tarball; unpack (one top
    directory `rp2350js-<commit>`); check the lockfile's sha256; `patch -p1 --forward --no-backup-if-mismatch -d SRC
    <"$HERE/rp2350js.patch"` (refuse if `patch` is missing; patch(1) skips the header comment); `npm ci --ignore-scripts
    --no-audit --no-fund --prefer-offline --cache "$DL/rp2350js/npm-cache"` with `PATH=$NODE_BIN:$PATH` (npm checks every
    package of the lockfile against its sha512 integrity; `--ignore-scripts` skips husky and `canvas`'s native build,
    which `tsc` does not need; the cache under `DL` makes a reinstall or `--adopt` work offline: measured, `--offline`
    from that cache installs the same 430 packages); `node node_modules/typescript/bin/tsc -p tsconfig.json` (TypeScript
    5.9.3 from the lockfile; CommonJS only, into `dist/cjs/`, not `npm run build`, which also wants rimraf and the ESM
    pass); then DEST receives `dist/cjs/`, `node_modules/uf2/` (uf2 2.0.0, no dependencies: the only package
    `dist/cjs/index.js` loads, through `utils/load-firmware.js`; the MCP server's `@modelcontextprotocol/sdk` and `zod`
    are not loaded by it), `package.json` and `LICENSE`. Install: absent -> build into `$WORK/rpjs-tree`, check
    `"$NODE_BIN/node" -p 'typeof require(process.argv[1]).RP2350' "$WORK/rpjs-tree/dist/cjs/index.js"` prints
    `function`, `mv` into place, `written rp2350js "$RPJS" "$RPJS_SHA256"`; present -> `dest_ok`, `present`. Verify:
    `manifest_verify rp2350js "$RPJS" "$(pin rp2350js)"`. Adopt: a fresh build in the work area, `adopt_compare ...
    exact` (tsc output is deterministic: a fresh build equalled the spike's `dist/cjs`, 194 files). A change to
    `rp2350js.patch` changes `dist/cjs`, so `--verify` fails until the tree is rebuilt and the pin re-pasted: the
    manifest pin covers the patch. Needs node (`NODE_BIN`), npm (node v24.13.0 bundles 11.6.2), `patch`, and the npm
    registry (or the cache) on the first install. Header comment: what rp2350js is, the commit, why a source tarball
    (no npm release of this fork at that commit), the patch, the npm cache, and that the boot ROM it uses is the A2 ROM
    bundled in its source (`src/bootroms/bootrom-rp2350-a2.ts`), pinned by the tarball's sha256.
- Produces, `c/bench/rp2350js.patch`: Appendix A verbatim: four rp2350js fixes measured in the spike (documented in
  `<workdir>/qemu-pico/docs/superpowers/specs/2026-10-21-qemu-pico-core-design.md`, "Spike result: rp2350js"): M33 GPIO
  coprocessor MCR/MRC/MCRR decode (`src/cortex-m33/coprocessor.ts`), Zcmp `cm.mvsa01`/`cm.mva01s` register fields
  (`src/riscv/decode.ts`), Zbb `orc.b` and `sltiu`'s immediate (and the `zip`/`unzip` bit order) (`src/riscv/cpu.ts`).
  The bench needs the RISC-V ones (measured: without them the Hazard3 images fail); the M33 one is kept so the tree is
  the one the spike validated against the panel references.
- Produces, `bench.c`: `-DBENCH_RP2350` joins the "exactly one of" check (and its `#error` text). `BENCH_MCU` is not
  implied (comment extended: "BENCH_M33 and BENCH_RP2350 do not imply it"). A new section `#elif defined(BENCH_RP2350)`
  after `BENCH_AVR`'s (before the QEMU branch), with no clock in the program:
  ```c
  #elif defined(BENCH_RP2350)
  /* RP2350 (Hazard3 or Cortex-M33) in a pico-sdk pico2 image under rp2350js: no clock in the program. Calls to four
   * marker functions let c/bench/rp2350-run.mjs read rp2350js's cycle counter: it watches the PC of each function's
   * first instruction. The functions are real code (a store to bench_mark_state; on a board they cost a few cycles and
   * do nothing else); noinline and distinct stores keep gcc from inlining or merging them. */
  #include <stdio.h> /* FILE in the line section; no stdio driver is initialised, so its printf goes nowhere */
  #define BENCH_SYL_N 100u
  #define BENCH_SCREEN_N 20u
  #define BENCH_LINE_N 20u
  volatile uint32_t bench_mark_state;
  __attribute__((noinline, used)) void bench_mark_start(void) { bench_mark_state = 1; }
  __attribute__((noinline, used)) void bench_mark_stop(void) { bench_mark_state = 2; }
  __attribute__((noinline, used)) void bench_mark_report(const char *name, uint32_t iters, uint32_t sum)
  {
  	__asm__ volatile("" ::"r"(name), "r"(iters), "r"(sum) : "memory"); /* the arguments stay in a0-a2 / r0-r2 */
  	bench_mark_state = 3;
  }
  __attribute__((noinline, used)) void bench_mark_end(int code)
  {
  	__asm__ volatile("" ::"r"(code) : "memory");
  	bench_mark_state = 4;
  	for (;;)
  		__asm__ volatile("" ::: "memory");
  }
  static void bench_start(void) { bench_mark_start(); }
  static void bench_stop(void) { bench_mark_stop(); }
  static void bench_report(const char *name, uint32_t iters, uint32_t sum) { bench_mark_report(name, iters, sum); }
  static void bench_end(int code) { bench_mark_end(code); }
  /* Two intervals the runner checks before the cases: an empty one (start, stop: the marks' own cost) and a loop of
   * 1,000,000 x 2 instructions whose cost rp2350js models exactly (Hazard3: addi 1 cycle + a backward bnez its
   * one-entry branch predictor hits, 1 cycle; Cortex-M33: subs 1 + taken bne 2). 32-bit encodings at a 4-aligned
   * label: no misaligned-fetch cycle after the jump. Reported as cal_empty and cal_loop1m. */
  static void bench_calibrate(void)
  {
  	uint32_t n = 1000000u;
  	bench_start();
  	bench_stop();
  	bench_report("cal_empty", 1, 0);
  	bench_start();
  #if defined(__riscv)
  	__asm__ volatile(".option push\n\t.option norvc\n\t.p2align 2\n1:\taddi %0, %0, -1\n\tbnez %0, 1b\n\t.option pop"
  	                 : "+r"(n));
  #elif defined(__thumb__)
  	__asm__ volatile(".p2align 2\n1:\tsubs %0, %0, #1\n\tbne 1b" : "+l"(n)::"cc");
  #else
  #error "BENCH_RP2350 is for the RP2350's Hazard3 or Cortex-M33"
  #endif
  	bench_stop();
  	bench_report("cal_loop1m", 1000000u, 0);
  }
  ```
  `bench_calibrate()` is called at the top of both `main`s: `#if defined(BENCH_ESP32S3) || defined(BENCH_M33) ||
  defined(BENCH_RP2350)` (MCU) and `#if defined(BENCH_M33) || defined(BENCH_RP2350)` (line). The header comment gains a
  `-DBENCH_RP2350` entry. `main` is pico-sdk's: its crt0 and runtime init (clocks to 150 MHz, which rp2350js ignores)
  run before it.
- Produces, `c/bench/rp2350/CMakeLists.txt`: a pico-sdk project (`include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)`,
  `project(svf_bench_rp2350 C CXX ASM)`, `pico_sdk_init()`), required cache variable `BENCH_GEN` (the directory with
  `face.c`, `face16.c`, `face18.c` from `mkface.py`; `FATAL_ERROR` if unset); `SVF_C` = `${CMAKE_CURRENT_LIST_DIR}/../..`;
  eight executables `bench-<opt>-<NAME>` for opt `Os O2` and NAME `MONO_PAGE` (0x02), `GRAY8` (0x01), `RGB565` (0x08),
  `LINE`: the MCU ones `bench.c` + `c/src/*.c` + the three faces with `BENCH_RP2350 BENCH_MCU SVF_NO_SCALE
  SVF_TARGETS=<bit> BENCH_KIND=SVF_T_<NAME>`, LINE `bench.c` + `c/src/*.c` + `face16.c face18.c` with `BENCH_RP2350`
  only (default `SVF_TARGETS`, scaling in); each `target_compile_options(... PRIVATE -<opt>)` (applies to the whole
  image, SDK sources included; it follows the Release `-O3` on the command line, so it wins: measured in
  `flags.make`, `-O3 -DNDEBUG -Os`), `target_include_directories(... ${SVF_C}/include)`,
  `target_link_libraries(... pico_stdlib)`; `set_source_files_properties(bench.c ${SVF_SRCS} PROPERTIES COMPILE_OPTIONS
  "-std=c99;-Wall;-Wextra;-Werror")` (not on the SDK's sources: its headers need C11 `static_assert`; measured). No
  `pico_add_extra_outputs` (the run passes `-DPICO_NO_PICOTOOL=1`; the ELF is what rp2350js loads). Comment at the top:
  what the images are and that they are the same kind of image as the `c/ports/pico` builds for `pico2`.
- Produces, `c/bench/rp2350-run.mjs RP2350JS_DIR CORE ELF NM` (CORE `riscv` or `arm`; NM a file of `nm` output,
  "ADDR TYPE NAME" lines), on `pico-run.mjs`'s shape and output:
  - loads `RP2350JS_DIR/dist/cjs/index.js` through `createRequire`; checks the ELF (32-bit LE, `e_machine` 243 for
    riscv, 40 for arm: exit 2 otherwise); copies each `PT_LOAD` segment with `filesz > 0` to its **physical** address
    in flash (0x10000000) or SRAM (0x20000000) (anything else: exit 2); `new RP2350({ coreArch: CORE })`, logger warn
    and error to stderr; `mcu.reset()`; requires core 0's PC to be in the boot ROM (`< 0x8000`; measured 0x7dfc riscv,
    0x88 arm) before the first step: the image boots through the A2 ROM, which finds its IMAGE_DEF in flash.
  - symbols from NM: `bench_mark_start`, `bench_mark_stop`, `bench_mark_report`, `bench_mark_end` (each `& ~1`;
    missing: `no <name> in NM`, exit 2), and the fault entries present among `isr_hardfault isr_nmi isr_svcall
    __unhandled_user_irq panic _exit isr_riscv_machine_exception hard_assertion_failure` (the spike's list).
  - the loop: before each `mcu.step()`, with `pc = core0.PC >>> 0`: at `bench_mark_start` an interval opens (core 0's
    `cycles` and the step count noted; a start while open fails); at `bench_mark_stop` it closes and its cycles
    (`core0.cycles` difference) and steps add to the case (a stop while closed fails); at `bench_mark_report` (fails
    if an interval is open) the name (NUL-terminated at `a0`/`r0`, at most 64 bytes), iterations (`a1`/`r1`) and
    checksum (`a2`/`r2`) are read (`core0.getRegister(10 + i)` on riscv, `core0.regs.r[i]` on arm): a name starting
    `cal_` prints `cal=<rest> cycles=C insns=I`, any other `case=NAME iters=N cycles=C per_iter_cycles=P insns=I
    per_iter_insns=Q sum=S` (P, Q with one decimal, S eight hex digits: `pico-run.mjs`'s line), and the counts reset;
    at `bench_mark_end` it prints `end=CODE total_cycles=T` and exits 0 for code 0, else 1; at a fault entry `fail:
    entered <sym>` and exit 1. A core-0 wait (`core0.waiting`) inside an open interval fails; outside it the clock is
    advanced to the next alarm and the step taken (the spike's handling; the boot ROM and runtime init may wait). An
    exception thrown by the emulator prints `fail: emulator: <message> (PC ...)` and exits 1. A run that passes 4e9
    cycles fails.
  - What a count is: cycles of an interval = `core0.cycles` when core 0 is about to execute `bench_mark_stop`'s first
    instruction minus the same at `bench_mark_start`'s: the start function's body and return and the call into stop
    are in it (a constant per interval, which `cal=empty` shows: 7-8 cycles Hazard3, 11-12 M33, measured); insns =
    `mcu.step()` calls in between (one core-0 instruction each). Core 1 stays parked by the boot ROM (the bench never
    launches it); its cycles are not counted. The header comment says all of this and lists what rp2350js does not
    model (below).
- Produces, `c/bench/run-rp2350.sh [OUT]` (default `c/build/bench/rp2350`), env `CORES` (default `riscv arm`; any other
  word: `rp2350: unknown core`, exit 1), `NODE` (override noted by `note_unpinned`), `LIMIT` (600), `FACE/FACE16/FACE18`.
  Verifies `install-toolchains.sh arm pico-rv pico-sdk` and `install-emulators.sh rp2350js` (`verify_ok`), needs
  `cmake` on PATH (`rp2350: cmake not found`, exit 1); `sums_for_faces rp2350 ...`; faces by `mkface.py` into
  `OUT/gen`; per core one configure `cmake -S "$HERE/rp2350" -B "$OUT/build-$core" -DPICO_SDK_PATH="$OPT/pico-sdk-2.3.1"
  -DPICO_BOARD=pico2 -DPICO_PLATFORM=<rp2350-riscv | rp2350-arm-s> -DPICO_TOOLCHAIN_PATH=<$OPT/pico-riscv-toolchain-16-v2.3.1-0
  | $OPT/arm-gnu-toolchain-15.2.rel1> -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release -DBENCH_GEN="$OUT/gen"` and
  `cmake --build "$OUT/build-$core" -j "$(nproc)"` into `OUT/build-$core.log` (shown and exit 1 on failure; the build
  directory is reused, never deleted: one per core, so its cache never changes platform); then per build
  `nm` (`riscv32-pico-elf-nm` / `arm-none-eabi-nm`) into `OUT/nm-<core>-<opt>-<NAME>.txt` and `run_guarded
  "$OUT/run-<core>-<opt>-<NAME>.txt" "$OUT/run-<core>-<opt>-<NAME>.err" "$NODE" "$HERE/rp2350-run.mjs"
  "$OPT/rp2350js-af0114c" <core> "$OUT/build-$core/bench-<opt>-<NAME>.elf" <nm file>`. After each run the calibration
  check (awk): exactly one `cal=empty cycles=E insns=EI` and one `cal=loop1m cycles=L insns=LI` line; `0 < E <= 32`;
  `|L - E - W| <= 16` with W 2,000,000 (riscv) or 3,000,000 (arm); `|LI - EI - 2000000| <= 16`; else `rp2350:
  calibration failed (<tag>)`, status 1. Rows by `report.awk` with `-v mhz=150 -v sums="$SUMS" -v exact=1 -v
  need_insns=1`, sums chosen by `case` (`MONO_PAGE`, `GRAY8`, `RGB565`, `LINE` -> `$SUMS_LINE40`). Row labels:
  `Hazard3 emulated (rp2350js af0114c + rp2350js.patch, pico-sdk 2.3.1 pico2 image booted from the A2 boot ROM:
  rp2350js cycles, µs at 150 MHz, the SDK clk_sys; XIP flash and cache, bus contention and load-use stalls not modelled;
  riscv32-pico-elf-gcc <ver> -<opt>; <NAME>, SVF_TARGETS=<mask>)` and the same with `Cortex-M33 emulated` and
  `arm-none-eabi-gcc <ver>`. Exit 0 when every build ran, every row is `ok` and every calibration held; 1 otherwise
  (no budget, so never 2). Raw output names: `OUT/run-<core>-<opt>-<NAME>.txt` with core `riscv`/`arm`, opt `Os`/`O2`.
- Produces, sizes: `build-all.sh` `try hazard3-rp2350` with `PRV=$OPT/pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf`,
  flags `-mcpu=hazard3-rp2350 -mstrict-align -Os` (pico-sdk 2.3.1's flags for `rp2350-riscv`, from the build's
  `flags.make`), link `--specs=nosys.specs -nostartfiles -Wl,-e,main` (measured: the library links with it), no
  budget line; `SIZES.md` a `hazard3-rp2350` Toolchains row (the pico-sdk-tools tarball, "RP2350 RISC-V core; the
  pico-sdk's flags; no budget") and its eight P rows.
- What rp2350js does not model (header of `run-rp2350.sh` and `rp2350-run.mjs`, MEASUREMENTS.md), from its README at
  af0114c and the source: "somewhat correct instruction cycle counts" (its own words; its Hazard3 table: 1 cycle an
  ALU op, a one-entry backward-branch predictor, +1 for a misaligned 32-bit fetch after a jump, 3 for an AMO, 17 for a
  divide; its M33 table is its own and not checked here against Arm's); every memory access costs the same: **no XIP
  flash or XIP cache timing** (code and faces are in flash, as on a board), no QMI, no bus contention or APB wait
  states, no Hazard3 dependent-register (load-use) penalty (README "Missing"); timer and system interrupts and
  exceptions are listed as missing (the bench uses none; a fault entry ends the run); `clk_sys` stays at 125 MHz
  whatever the SDK programs (measured: `clkSys` 125000000), so the rows convert cycles at 150 MHz, the SDK's clock, and
  a time read from the emulated chip's timers would be wrong (the runner reads none). Real hardware is this fast or
  slower wherever flash or the bus matter; the cycle counts are rp2350js's, not the chip's.

- [ ] **Step 1: Write the failing tests**

In `TestBenchSums` of `tools/test_c_renderer.py`:
- `test_rp2350_section_compiles`: for each compiler that exists under `OPT`
  (`pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf-gcc` with `-mcpu=hazard3-rp2350 -mstrict-align`,
  `arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc` with `-mcpu=cortex-m33 -mthumb`; skip when neither is there),
  `-std=c99 -Wall -Wextra -Werror -fsyntax-only -DBENCH_RP2350 -I c/include c/bench/bench.c` twice: with `-DBENCH_MCU
  -DSVF_NO_SCALE -DSVF_TARGETS=0x01 -DBENCH_KIND=SVF_T_GRAY8` (the MCU cases, set B included) and without (the line
  section); each exits 0 with no output. (No SDK header is needed: the section includes only `<stdio.h>`.)
- `test_run_scripts_fail_on_a_missing_install`: add `"run-rp2350.sh"` (exit 1, "not installed").
- `test_run_scripts_leave_no_emulator_when_terminated`: add `("run-rp2350.sh", "NODE")`, appended only when
  `install-emulators.sh --verify rp2350js` prints `rp2350js: OK` and `c/cross/install-toolchains.sh --verify pico-rv
  pico-sdk` prints `pico-rv: OK` and `pico-sdk: OK` (both exit 0) and `cmake` is on PATH: the runner verifies them
  even with `NODE` overridden (the fake node starts after the two CMake builds, about 10 s; the test waits up to 60 s).
- `test_rp2350_run_reads_the_marks` (same skip as the entry above): `CORES=riscv sh c/bench/run-rp2350.sh TMP/o`:
  exit 0; 30 lines ending ` ok |` (5 + 9 + 9 + 7 cases x 2 opts), none containing `**expected`; each
  `TMP/o/run-riscv-*.txt` has one `cal=empty` and one `cal=loop1m` line; then `node c/bench/rp2350-run.mjs
  ~/opt/rp2350js-af0114c riscv TMP/o/build-riscv/bench-Os-MONO_PAGE.elf TMP/o/nm-riscv-Os-MONO_PAGE.txt` again prints
  exactly the bytes of `TMP/o/run-riscv-Os-MONO_PAGE.txt` (deterministic); and with a copy of that nm file without the
  `bench_mark_start` line it exits 2 and prints `no bench_mark_start`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m unittest tools.test_c_renderer.TestBenchSums -v 2>&1 | grep -E "rp2350|FAIL|ERROR|skipped" | head`
Expected: `test_rp2350_section_compiles` FAILS (`#error "build with exactly one of ..."`);
`test_run_scripts_fail_on_a_missing_install` FAILS (no `run-rp2350.sh`); the two install-dependent tests are skipped
(nothing pinned yet).

- [ ] **Step 3: Pin the RISC-V toolchain (`pico-rv`)**

`install-lib.sh`: `unpack NAME FILE DEST [flat]` as in Interfaces (update its comment). `install-toolchains.sh`: the
`PRV_*` constants, `reg pico-rv` (`R_DEST=$PREFIX/pico-riscv-toolchain-16-v2.3.1-0 R_BIN=riscv32-pico-elf-gcc
R_URL=$PRV_URL R_SHA=$PRV_SHA R_FLAT=flat`; every other name sets `R_FLAT=`), `tool` and `adopt` pass `$R_FLAT` to
`unpack`; the name in the Names line, the "Pinned releases" header (release, URL, digest, "no top directory"), the
`--verify` default list, `verify`'s tarball case, and **all three** "unknown name" texts (verify, adopt, the install
NAMES check); an install line `want pico-rv && tool pico-rv`. `test-installers.sh`: a `pico-rv` case (install into a
temporary PREFIX from `$REAL/dl/pico-rv/riscv-toolchain-16-x86_64-lin.tar.gz`, `--verify`, `--adopt`), skipped with
the script's "skipped (no ...)" line when that file is absent. The tree on this host was unpacked by the spike: adopt
it, do not reinstall.
Run:
```bash
mkdir -p ~/opt/dl/pico-rv && cp ~/opt/dl/pico-riscv-toolchain-16-v2.3.1-0/riscv-toolchain-16-x86_64-lin.tar.gz ~/opt/dl/pico-rv/ 2>/dev/null
sh c/cross/install-toolchains.sh --adopt pico-rv
```
Expected: `pico-rv: adopted .../pico-riscv-toolchain-16-v2.3.1-0; manifest pin: MANIFEST_PIN_pico-rv=<hash>`; paste it as
`MANIFEST_PIN_pico_rv=<hash>`; then `sh c/cross/install-toolchains.sh --verify pico-rv` prints `pico-rv: OK` (exit 0).
If the adoption reports a difference from the verified tarball, stop and report it (do not delete the tree: the
script never replaces a tree in place).

- [ ] **Step 4: Commit the patch and pin rp2350js**

Create `c/bench/rp2350js.patch` with the text of Appendix A (header comment, then the diff exactly as given; check:
`sed -n '/^diff --git/,$p' c/bench/rp2350js.patch | sha256sum` prints
`61596cb94ca344b24dd1ae6ee118449f35c776cd7f70481a03ffbb75a61b7056`, the diff the spike measured). `install-emulators.sh`:
the `RPJS_*` constants, `build_rpjs`, the install branch (`if want rp2350js; then ... fi`, with the `absent` /
`dest_ok` / `present` shape), `verify` and `adopt` cases, the name in Names, the header (what, commit, sha256, the
patch, npm cache, needs node/npm/patch/network-or-cache, the bundled A2 ROM), the `--verify` default list and **all
three** "unknown name" texts. `test-installers.sh`: an `rp2350js` case (fresh install into a temporary PREFIX whose
`dl/rp2350js/` is a copy of the real one, `--verify`, `--adopt`), skipped when `$REAL/dl/rp2350js/rp2350js-af0114c.tar.gz`
or `$REAL/dl/rp2350js/npm-cache` is absent.
Run: `sh c/bench/install-emulators.sh ~/opt rp2350js`, paste the printed `MANIFEST_PIN_rp2350js=...`, then
`sh c/bench/install-emulators.sh --verify rp2350js` and `sh c/cross/test-installers.sh`
Expected: the install prints `rp2350js: installed; manifest pin: ...` and `rp2350js: af0114c (~/opt/rp2350js-af0114c)`;
`--verify` prints `rp2350js: OK` (exit 0); `installers: OK` (or the "skipped" lines for absent `dl/` copies).
Then `sh c/bench/install-emulators.sh --adopt rp2350js` (a fresh build compared with the installed tree): exit 0, the
same pin.

- [ ] **Step 5: Add the `BENCH_RP2350` section to `bench.c`**

Per the Interfaces block (one-of check and its `#error` text, `BENCH_MCU` comment, the section, the two calibration
calls, the header comment's entry).
Run: `python3 -m unittest tools.test_c_renderer.TestBenchSums.test_rp2350_section_compiles -v 2>&1 | tail -n 3`
Expected: PASS.

- [ ] **Step 6: Write `c/bench/rp2350/CMakeLists.txt`, `c/bench/rp2350-run.mjs` and `c/bench/run-rp2350.sh`**

Per the Interfaces block. `run-rp2350.sh`'s header comment on `run-pico.sh`'s and `run-m33.sh`'s pattern: what is
built (real `pico2` images, both cores, eight builds each), how a count is taken (marks, `core.cycles`, the constant
per interval), the calibration and its tolerances, the 150 MHz conversion and rp2350js's 125 MHz, what rp2350js does
not model, that the patch is applied at install (Appendix A's four fixes), that no budget applies, the exit status,
the OUT layout, and that `run-m33.sh` (QEMU) stays as the instruction-count cross-check of the M33 rows. No `eval`; every
expansion quoted; the build directories are reused, never deleted.
Run: `CORES=riscv sh c/bench/run-rp2350.sh /tmp/rp2350-try | tail -n 8; echo "exit $?"` and
`grep -h '^cal=' /tmp/rp2350-try/run-riscv-*.txt | sort | uniq -c`
Expected: rows ending `ok |`, exit 0; `cal=empty cycles=7` / `8` and `cal=loop1m cycles=2000011` .. `2000014` (planning
probe values; the gate is the difference within 16 of 2,000,000).

- [ ] **Step 7: Add the toolchain row**

`build-all.sh`: `PRV=$OPT/pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf` beside `ESP=`, and after
`try esp32c3-riscv32`: `try hazard3-rp2350 "$(version "$PRV-gcc")" "$PRV-gcc" "$PRV-size" "-mcpu=hazard3-rp2350 -mstrict-align -Os" "--specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"`
(comment: RP2350's RISC-V core with pico-sdk 2.3.1's flags; no budget, as `cortex-m33`). `SIZES.md`: the Toolchains
row and the eight P rows from the run below.

- [ ] **Step 8: Run the tests, the runner twice and the size table**

Run:
```bash
python3 -m unittest tools.test_c_renderer.TestBenchSums -v 2>&1 | tail -n 14
mkdir -p c/build/bench/before && (set -o pipefail; sh c/bench/run-rp2350.sh "$PWD/c/build/bench/before/rp2350" | tee c/build/bench/before/rp2350.md); echo "exit $?"
(set -o pipefail; sh c/bench/run-rp2350.sh /tmp/rp2350-again | tee /tmp/rp2350-again.md); echo "exit $?"
diff c/build/bench/before/rp2350.md /tmp/rp2350-again.md && for f in c/build/bench/before/rp2350/run-*.txt; do cmp "$f" "/tmp/rp2350-again/$(basename "$f")"; done; echo "diff $?"
sh c/cross/build-all.sh c/build/cross | grep -E "hazard3-rp2350"
sh c/cross/test-installers.sh
```
(the library is still 344a090's, so these rows are the "before"; `pipefail` reports the runner's status, not `tee`'s;
the raw files land in `before/rp2350/`, where Step 9 and Task 10 read them.)
Expected: tests PASS (the two install-dependent ones run, not skipped); each run: 16 builds, **120 rows** (60 Hazard3,
60 M33), every row `ok`, exit 0, every calibration within its tolerance (planning probe: Hazard3 loop - empty =
2,000,004 .. 2,000,006 cycles, M33 3,000,001 .. 3,000,002; empty 7-8 and 11-12); the two runs identical (`diff 0`,
no output: rp2350js is stepped by cycles, nothing depends on host time); `hazard3-rp2350: OK 16.1.0 (...)` and its
eight P rows; `installers: OK` (or skipped lines). Planning-probe values to sanity-check, not gates: MONO_PAGE `-Os`
`syl_ga` about 4,175 cycles (Hazard3) and 5,404 (M33), LINE `-Os` `line40_scaled32` about 7.63 M (Hazard3) and
6.74 M (M33) cycles an iteration. Write in the task report: the wall time of a full run (planning: about 30 s), and
the M33 `per_iter_insns` of the MONO_PAGE `-Os` rows next to `run-m33.sh`'s QEMU instruction counts of Task 3 (two
images of the same library code: pico-sdk's `-mcpu=cortex-m33 -march=armv8-m.main+fp+dsp -mfloat-abi=softfp` against
the bare `-mcpu=cortex-m33 -mthumb`; a cross-check, not a gate).

- [ ] **Step 9: Record the rows and extend the checker**

`MEASUREMENTS.md`:
- "How time is measured": one row `RP2350 (Hazard3 and Cortex-M33, 150 MHz)` | rp2350js af0114c + `c/bench/rp2350js.patch`
  on node v24.13.0, pico-sdk 2.3.1 `pico2` images booted through the bundled A2 boot ROM, driven by
  `c/bench/rp2350-run.mjs` | rp2350js's cycle counter (`core.cycles` of core 0) between the PCs of the marker functions;
  µs = cycles / 150 (the SDK's `clk_sys`; rp2350js runs 125 MHz) | the "does not model" list of the Interfaces block,
  the calibration (`cal=empty`, `cal=loop1m`, tolerances) and "two runs byte-identical".
- Provenance rows: rp2350js (URL, 1,246,966 bytes, sha256, the lockfile's sha256, `npm ci` integrity, TypeScript 5.9.3,
  uf2 2.0.0, the patch and its four fixes, manifest pin) and riscv32-pico-elf-gcc 16.1.0 (URL, 129,680,495 bytes,
  sha256 = the release's published digest, manifest pin).
- Two sections in the Cortex-M33 section's shape, placed after it: `### RP2350 Hazard3 under rp2350js (RISC-V core; no
  budget; rp2350js cycles)` and `### RP2350 Cortex-M33 under rp2350js (Arm core; no budget; rp2350js cycles)`: a
  paragraph each (what the count is, the per-interval constant, the calibration, the 150 MHz conversion, what is not
  modelled, the run date and commit, "two complete runs give byte-identical rows"), then one table per kind headed
  `MONO_PAGE (\`-DSVF_TARGETS=0x02\`)`, `GRAY8 (...)`, `RGB565 (...)`, `LINE (default \`SVF_TARGETS\`, scaling on)`:
  `| case | iterations | -Os cycles/iteration | -O2 cycles/iteration | -Os µs at 150 MHz | -O2 µs at 150 MHz |`. In
  the M33 rp2350js section, one sentence on the QEMU instruction counts of `### Cortex-M33` (the Step 8 cross-check
  ratio for MONO_PAGE `-Os`).
- The section names must **not** start with `### Cortex-M33` (the checker's prefix for the QEMU section).
`check-measurements-md.py`: `parse` maps `### RP2350 Hazard3` to section `H3` and `### RP2350 Cortex-M33` to `M33R`,
both `mhz 150`; `make_raw(pico_dir, esp_dir, m33_dir=None, rp2350_dir=None)` (the parameter was `hazard3_dir`; usage
`--raw PICO ESP32 [M33 [RP2350]]`, docstring updated) reads `run-riscv-<o>-<k>.txt` as `H3` and `run-arm-<o>-<k>.txt`
as `M33R` for k in the three kinds and `LINE`, with `per_iter_insns` as the sixth field. Regenerate
`measurements-raw.txt` with Task 1's Pico and ESP32 directories, `c/build/bench/before/m33` and
`c/build/bench/before/rp2350`. `tools/test_c_renderer.py` `test_measurements_md_numbers_are_derived`: two more doctored
anchors, `("h3-us", "<the H3 MONO_PAGE syl_ga row as written>", <its -Os µs + 0.01>)` and `("m33r-count", ...)` (a
cycle count + 1), so the new sections are checked, not skipped.
Run: `python3 -I c/bench/check-measurements-md.py c/bench/MEASUREMENTS.md; echo $?` and
`python3 -m unittest tools.test_c_renderer.TestBenchSums.test_measurements_md_numbers_are_derived -v 2>&1 | tail -n 3`
Expected: silent, 0; PASS.

- [ ] **Step 10: Run the gate and commit**

Run: `make -C c check 2>&1 | tail -n 6` — Expected: green (the new tests run where the installs verify).
```bash
git add c/bench/rp2350js.patch c/bench/rp2350/CMakeLists.txt c/bench/rp2350-run.mjs c/bench/run-rp2350.sh c/bench/install-emulators.sh c/cross/install-toolchains.sh c/cross/install-lib.sh c/cross/test-installers.sh c/bench/bench.c c/cross/build-all.sh c/cross/SIZES.md c/bench/check-measurements-md.py c/bench/measurements-raw.txt c/bench/MEASUREMENTS.md tools/test_c_renderer.py
git commit -m "bench: RP2350 runner under rp2350js (pico2 images of Hazard3 and Cortex-M33 through the A2 boot ROM, cycles between marker functions), pinned rp2350js af0114c + four fixes and riscv32-pico-elf 16.1.0, hazard3-rp2350 size rows"
```


---

### Task 5: The exhaustive kernel net `c/tests/test_kernels.c`

**Files:**
- Create: `c/tests/test_kernels.c`
- Modify: `c/Makefile` (`test-kernels`, `check`)

**Interfaces:**
- Consumes: `svf__merge` and `svf__scale_cell` from `c/src/svf_internal.h` (compiled with `-Isrc`); `svf_test_blit`
  (`-DSVF_TEST_HOOKS`, declared as in `tests/test_pad.c`); `svf__coverage`.
- Produces: `make -C c test-kernels` builds three programs, `$(O)/test-kernels` (defaults), `$(O)/test-kernels-bytes`
  (`-DSVF_WORD_STORE=0`), `$(O)/test-kernels-plain` (`-DSVF_MERGE_WORDS=0 -DSVF_GRAY8_LUT1=0`), each the sanitizer
  build (`$(ASAN)`, `-DSVF_TEST_HOOKS -Iinclude -Isrc tests/test_kernels.c $(SRCS)`); each prints one line
  `kernels: OK merge2=65536 runs=2000 or1=2000 max8=2000 lut1=4300800 scale=16513002` and exits 0, or `kernels: FAIL <test>: <where>`
  on stderr and exits 1; `check` runs the three and requires the three lines equal (as `test-pad`). The reference
  implementations live in the test and never change: `ref_max2(uint8_t x, uint8_t y)` (the per-field loop of today's
  `svf__merge`), `ref_merge(uint8_t bpp, uint8_t *dst, const uint8_t *src, unsigned n)`, `ref_gray8_1bpp(...)`
  (today's bit loop over a cut), `ref_scale_cell(const svf_face *f, const uint8_t *cell, uint8_t num, uint8_t den,
  uint8_t *out)` (today's `svf__scale_cell` with `span`/`overlap`, copied verbatim). Random numbers: xorshift32
  seeded 12345 (the spike's `rnd`). (Until Tasks 6-8 land, the library side is the old code: the net passes on it and
  must keep passing after.)

- [ ] **Step 1: Write the test**

`c/tests/test_kernels.c` with, under a `main` that runs them in order and counts failures:
```c
/* all 65,536 (dst, src) pairs through the library's byte form: svf__merge with n = 1 on a 2 bpp face */
static void test_merge2_pairs(void);      /* FAIL names the pair and the two bytes */
/* 2,000 random runs: n in 0..199, dst at offset od in 0..3 and src at os in 0..3 of 4-aligned buffers, random
 * bytes, 8 guard bytes before and after dst; svf__merge against ref_merge, memcmp over the guards too; done for
 * bpp 2 and bpp 1 (the 1 bpp OR word loop); the svf_face is zeroed except bpp */
static void test_merge_runs(void);        /* counts runs=2000 or1=2000 max8=2000 (bpp 2, 1, 8; each run also merges into exact-size heap copies) */
/* the 1 bpp GRAY8 path through svf_test_blit on a GRAY8 target 40 x 1 (stride 40, 8 guard bytes each side in a
 * 56-byte buffer): a one-row 1 bpp cell of w = 24 (pitch 3) holding (v, v ^ 0xFF, v) for every v in 0..255, the
 * target prefilled with each of the patterns 0x00, 0xFF, 0x80, and bytes from rnd(); for every (lo, hi) with
 * 0 <= lo < hi <= 24 set by clip_x0 = x + lo, clip_x1 = x + hi, at x in {-8, -7, -6, -5, -3, -1, 0, 1, 2, 3, 5, 6, 7, 16} (3 rows of distinct data): the whole buffer against
 * the expected image computed with ref_gray8_1bpp (OR of 255 where the cell bit is set, inside [lo, hi) and inside
 * the target, nothing else changed) */
static void test_gray8_lut1_cuts(void);   /* counts lut1 = the number of blits compared */
/* every reduced num/den with den in 2..16 and num in 1..16; cells (w, h) in {(1,1), (3,2), (8,8), (13,11),
 * (16,16), (18,18), (24,24), (47,47), (48,48)}; bpp 1, 2, 8; cell bytes from rnd(); svf__scale_cell against
 * ref_scale_cell over svf__scale_dim(w) * svf__scale_dim(h) bytes (output buffers 384 * 384 + 16 guard bytes each:
 * the largest cell of the sweep is 48 at 15/2 = 360 x 360); the svf_face is zeroed except cell_w, cell_h, bpp,
 * pitch = (w * bpp + 7) / 8 */
static void test_scale_sweep(void);       /* counts scale = output pixels compared: 16513002 (143 reduced ratios x 9 cells x 3 bpp x 2 random fills; cells in exact-size heap copies) */
```
`#ifdef SVF_NO_SCALE` is not needed (the test is never built noscale). The target for the blit tests comes from
`svf_target_init(&t, SVF_T_GRAY8, buf + 8, 40, 40, 1, 40)`. Reviewer note: `ref_scale_cell` with its `span` and
`overlap` is the old implementation copied verbatim into the test on purpose (the spec: "the old implementation moved
into the test as the reference"); do not flag the duplication.

- [ ] **Step 2: Add the Makefile rules and run**

Rules `$(O)/test-kernels`, `$(O)/test-kernels-bytes`, `$(O)/test-kernels-plain` as above (the plain build passes
`-DSVF_MERGE_WORDS=0 -DSVF_GRAY8_LUT1=0`: unknown to the library until Task 6, harmless now); `check:` gains
`test-kernels` and the three-way equality line; update the Makefile header comment.
Run: `make -C c test-kernels && c/build/test-kernels && c/build/test-kernels-bytes && c/build/test-kernels-plain`
Expected: three identical `kernels: OK merge2=65536 runs=2000 or1=2000 max8=2000 lut1=4300800 scale=16513002` lines.

- [ ] **Step 3: Prove the net bites**

Edit `c/src/svf_jamo.c:179` to take the smaller field (`x > y ? x : y` -> `x < y ? x : y`), run
`make -C c test-kernels && c/build/test-kernels`: Expected `kernels: FAIL merge2_pairs: ...`, exit 1. Then
`git checkout -- c/src/svf_jamo.c`. Do the same once for `svf_scale.c` (`+ 0x8000u` -> `+ 0x7FFFu`): FAIL on
`scale_sweep`; restore. Do the same for `svf_draw.c` `blit_gray8` case 1 (`dst[x + col] = 255` -> `= 254`): FAIL on
`gray8_lut1_cuts`; restore. `git status --short c/src` prints nothing afterwards.

- [ ] **Step 4: Run the gate and commit**

Run: `make -C c check 2>&1 | tail -n 10` — Expected: the three `kernels: OK` lines, then the usual OK lines, exit 0.
```bash
git add c/tests/test_kernels.c c/Makefile
git commit -m "tests: test_kernels, the exhaustive host net for svf__merge, the 1 bpp GRAY8 blit and svf__scale_cell (in make check)"
```

---

### Task 6: `svf__merge`: byte SWAR for 2 bpp, the word loop (1 bpp OR, 2 bpp SWAR), unsigned counters

> **Re-plan after SVF v3 lands; carry F5, F6, F13, F15, F16, F18** (pre-flight
> `.superpowers/sdd/2026-10-21-c-speedups/preflight.md`; F15 as ruled by the controller: the `mkface.py` `aligned(4)`
> change is dropped and recorded as a spec deviation). Tasks 6-10 are re-planned on the v3 layout
> (`<workdir>/svf-fonts-review/svf-v3-design.md`) after the separate SVF v3 plan; the text below is the
> 344a090 draft. RP2350: `run-hazard3.sh` no longer exists; every Hazard3 gate below is `run-rp2350.sh` (Task 4,
> Hazard3 and Cortex-M33 under rp2350js, cycles); `run-m33.sh` stays the QEMU instruction-count check.

**Files:**
- Modify: `c/include/svf.h:270-278` (the switches after `SVF_WORD_STORE`), `c/src/svf_internal.h:65-67` (comment),
  `c/src/svf_jamo.c:157-184`, `c/bench/mkface.py`
- Test: `c/tests/test_kernels.c` (Task 5), the gates

**Interfaces:**
- Consumes: Task 5's net.
- Produces: `svf.h`: `SVF_MERGE_WORDS` (`#ifndef`; 1 when `!defined(__AVR__) && defined(__BYTE_ORDER__) &&
  __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__`, else 0) and `SVF_GRAY8_LUT1` (`#ifndef`; 0 under `__AVR__`, else 1),
  each with a comment in the `SVF_WORD_STORE` style saying what it selects, the default and that pixels are the same
  either way. `svf_internal.h`: `#define SVF__MERGE_UNALIGNED 1` when `SVF_WORD_STORE || defined(__ARM_FEATURE_UNALIGNED)`
  else 0 (one `memcpy` of 4 bytes is one load at any alignment: x86, WASM, ARMv7-M and up). `svf_jamo.c`:
  `static uint8_t svf__max2(uint8_t x, uint8_t y)` = `xh=(x&0xAA)>>1, yh=(y&0xAA)>>1, eq=~(xh^yh),
  lo=((eq&(x|y))|(xh&~yh&x)|(yh&~xh&y))&0x55, result ((x|y)&0xAA)|lo` (all in `unsigned`, cast at the end) and
  `static uint32_t svf__max2w(uint32_t x, uint32_t y)` (the same with `0xAAAAAAAAu`/`0x55555555u`); `svf__merge`
  signature unchanged, counters `unsigned k, len = n`. Structure: `#if SVF_MERGE_WORDS` the word loop runs for bpp 1
  (OR) and 2 (`svf__max2w`) while `k + 4 <= len`, when `words_ok`: `#ifdef SVF_RD8_PLAIN` always, `#else` only
  `f->rd != NULL`; and, `#if !SVF__MERGE_UNALIGNED`, only when `((uintptr_t)dst & 3) == 0`. Loads/stores: the
  destination word by `memcpy(&d, dst + k, 4)` / `memcpy(dst + k, &d, 4)`; the source word `memcpy` where
  `SVF__MERGE_UNALIGNED`, else assembled `s = p0 | p1 << 8 | p2 << 16 | p3 << 24` from four `SVF__RD8` bytes
  (little-endian by the switch's default rule). The tails and the `SVF_MERGE_WORDS 0` build: byte loops, 1 bpp OR,
  2 bpp `dst[k] = svf__max2(dst[k], b)` on every byte (no zero test), 8 bpp unchanged. `mkface.py`: the array gets
  `__attribute__((aligned(4)))` (every compiler of this repo is gcc or clang) so an embedded face's tables start
  aligned.

- [ ] **Step 1: Run the net and the Pico rows before the change (the measured "before" of this task)**

Run: `c/build/test-kernels` (built by Task 5) and keep Task 1's `c/build/bench/before/pico.md` at hand.
Expected: `kernels: OK ...`.

- [ ] **Step 2: Add the switches and `SVF__MERGE_UNALIGNED`**

Per the Interfaces block, with the comments. Nothing uses them yet: `make -C c lib` builds.

- [ ] **Step 3: Rewrite `svf__merge`**

Per the Interfaces block. Update the comment above `svf__merge` in `svf_internal.h` ("byte by byte" becomes "words
where `SVF_MERGE_WORDS` ... , bytes otherwise; any run of a cell can be merged").

- [ ] **Step 4: Run the net in all three builds and the sanitizer gate**

Run: `make -C c check 2>&1 | tail -n 10`
Expected: the three `kernels: OK` lines identical (`runs=2000 or1=2000 max8=2000`), `asan: OK`, `clang: OK`, exit 0. The
`svfdump-rd8` test inside (`TestReadOverride`) passes: with the override the word loop reads only streamed memory.

- [ ] **Step 5: Check the code the strict-align targets get**

Run: `~/opt/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc -std=c99 -Wall -Wextra -Werror -mcpu=cortex-m0plus -mthumb -Os -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -Ic/include -c c/src/svf_jamo.c -o /tmp/jamo-m0.o && ~/opt/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-objdump -d /tmp/jamo-m0.o | awk '/<svf__merge>:/,/^$/' | grep -cE 'ldr\s|str\s'`
and the same with `-mcpu=cortex-m33` (`SVF__MERGE_UNALIGNED` 1: `ldr` for both words) and with the ESP gcc
`-march=rv32imc_zicsr_zifencei -mabi=ilp32 -Os` (`lw`/`sw` for the destination, `lbu` for the source).
Expected: at least one word load and one word store in `svf__merge` on each; no `memcpy` call
(`grep -c 'bl.*memcpy\|jal.*memcpy'` prints 0). Write the instruction count of the 2 bpp word loop body in the task
report.

- [ ] **Step 6: Run every cross gate**

```bash
sh c/cross/build-all.sh c/build/cross | grep -E 'cortex-m0plus \| 15.2.1 \| P[12] |: OK|FAIL'
sh c/cross/build-all.sh --ports c/build/cross-ports 2>&1 | grep -c ': OK'
mkdir -p c/build/bench/after-merge && (set -o pipefail; sh c/bench/run-pico.sh "$PWD/c/build/bench/after-merge/pico" | tee c/build/bench/after-merge/pico.md); echo "exit $?"
sh c/bench/run-esp32.sh; echo "exit $?"
sh c/bench/run-avr.sh; echo "exit $?"
sh c/bench/run-dos.sh | grep -c 'ok |'; sh c/bench/run-wasm.sh; echo "exit $?"
sh c/bench/run-m33.sh; echo "exit $?"; sh c/bench/run-rp2350.sh; echo "exit $?"
bash c/ports/dos/vesa-shots.sh; git status --short c/ports/dos/shots
```
(`vesa-shots.sh` and `run-dos.sh` refuse a relative OUT: call `vesa-shots.sh` with no argument, its default is
`c/build/ports/dos-vesa`.)
Expected: every toolchain OK, P1 and P2 text <= 8192 (write the numbers down); `37`; Pico exit 0 or 2 with every row
`ok` and `syl_bwelk` `-Os` cycles below Task 1's 7744; ESP32, AVR (flash <= 32,256), WASM, M33, RP2350 exit 0; DOS 80
`ok` rows and `line40_mapped` DX2-66 below 15190.90 µs; `git status` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add c/include/svf.h c/src/svf_internal.h c/src/svf_jamo.c c/bench/mkface.py
git commit -m "c/src: svf__merge as byte SWAR (2 bpp) with a word loop for 1 and 2 bpp behind SVF_MERGE_WORDS; unsigned counters; M0+ P1/P2 <N> B"
```

---

### Task 7: The 1 bpp -> GRAY8 table

> **Re-plan after SVF v3 lands; carry F5, F6, F13, F15, F16, F18.** RP2350 gates: `run-rp2350.sh` (Task 4), not
> `run-hazard3.sh`.

**Files:**
- Modify: `c/src/svf_draw.c:517-560` (`blit_gray8` case 1 and the table above it)
- Test: `c/tests/test_kernels.c` (`test_gray8_lut1_cuts`), the gates

**Interfaces:**
- Consumes: `SVF_GRAY8_LUT1` (Task 6).
- Produces: under `#if (SVF_TARGETS & SVF_TARGET_GRAY8) && SVF_GRAY8_LUT1`, `static const uint8_t svf__lut1[256][8]`
  generated at compile time by nested macros (`SVF__L1B(v, j)` = `(v) >> (7 - (j)) & 1 ? 255 : 0`; `SVF__L1(v)` the
  8-entry row; `SVF__L1x4`, `SVF__L1x16`, `SVF__L1x64` repeating it; the initialiser `SVF__L1x64(0), SVF__L1x64(64),
  SVF__L1x64(128), SVF__L1x64(192)`; the macros `#undef`'d after the table). `blit_gray8` case 1: for a source byte
  `b` with `lo == b * 8 && hi == b * 8 + 8` (wholly inside the cut), OR the 8 table bytes into `dst + x + b * 8`:
  `#if SVF_WORD_STORE` two `uint32_t` through `memcpy` (load, OR, store), `#else` a loop of 8 byte ORs; the partial
  first and last bytes keep today's bit loop; the `!v` skip stays. With `SVF_GRAY8_LUT1 0` the case is today's code.
  INDEXED8 unchanged.

- [ ] **Step 1: Implement**

Per the Interfaces block; the comment at the table says what it is, that `max(d, 255) == d | 255`, that it is
`.rodata` dropped by `--gc-sections` where unreferenced, and its 2 KB.

- [ ] **Step 2: Run the net and the gate**

Run: `make -C c check 2>&1 | tail -n 10`
Expected: three identical `kernels: OK` lines (the `-plain` build takes the bit loop, the other two the table),
`asan: OK`, `clang: OK`, the 0x000..0x1FF targets gate OK (the table compiles under every mask), exit 0.

- [ ] **Step 3: Check the size rule**

Run: `sh c/cross/build-all.sh c/build/cross | grep -E 'cortex-m0plus \| 15.2.1 \| P(1|2|3g|1\*) '`
Expected: P1 and P2 unchanged from Task 6 (no GRAY8: the table is not linked), P3g and P1* about 2 KB larger. Then
`~/opt/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-nm --size-sort c/build/cross/cortex-m0plus/p1.elf | grep -c lut1`
prints 0 and the same on `p3g.elf` prints 1.

- [ ] **Step 4: Run the runners the table reaches**

```bash
mkdir -p c/build/bench/after-lut1 && (set -o pipefail; sh c/bench/run-pico.sh "$PWD/c/build/bench/after-lut1/pico" | tee c/build/bench/after-lut1/pico.md); echo "exit $?"
(set -o pipefail; sh c/bench/run-esp32.sh "$PWD/c/build/bench/after-lut1/esp32" | tee c/build/bench/after-lut1/esp32.md); echo "exit $?"
sh c/bench/run-m33.sh; echo "exit $?"; sh c/bench/run-rp2350.sh; echo "exit $?"
sh c/bench/run-host.sh c/build/bench/host | grep -E 'line40_24m_|end='
sh c/bench/run-dos.sh | grep -c 'ok |'; sh c/bench/run-avr.sh; echo "exit $?"
sh c/cross/build-all.sh --ports c/build/cross-ports 2>&1 | grep -c ': OK'
bash c/ports/dos/vesa-shots.sh; git status --short c/ports/dos/shots
```
Expected: every row `ok`; the Pico GRAY8 `syl_ga` / `line8` rows below Task 6's; AVR rows unchanged (the switch is 0);
`37`; no PNG change.

- [ ] **Step 5: Commit**

```bash
git add c/src/svf_draw.c
git commit -m "c/src: blit_gray8 1 bpp through a compile-time 2 KB table behind SVF_GRAY8_LUT1; M0+ P1/P2 <N> B"
```

---

### Task 8: The separable box filter

> **Re-plan after SVF v3 lands; carry F5, F6, F13, F15, F16, F18.** RP2350 gates: `run-rp2350.sh` (Task 4), not
> `run-hazard3.sh`.

**Files:**
- Modify: `c/src/svf_scale.c:44-89` (`span`, `overlap`, the area-averaged branch of `svf__scale_cell`)
- Test: `c/tests/test_kernels.c` (`test_scale_sweep`), `make -C c check` (TestScale), the gates

**Interfaces:**
- Consumes: nothing new.
- Produces: `svf__scale_cell` signature and the `den == 1` block path unchanged. New in `svf_scale.c`:
  `typedef struct { uint8_t start, count, w[17]; } svf__axis;` and
  `static void axis_weights(svf__axis t[16], uint8_t num, uint8_t den)`: for `o` in `0..num-1`,
  `lo = o * den / num`, `hi = ((o + 1) * den - 1) / num + 1`, `t[o].start = lo`, `t[o].count = hi - lo`
  (<= 17), `t[o].w[i] = overlap(lo + i, o, num, den)` (1/num units, <= 16); output pixel `o` covers source pixels
  `(o / num) * den + start + i`, `i < count`, those `< n`. The branch: tables `tx[16]`, `ty[16]` on the stack, an
  accumulator `uint16_t acc[128]`; for each output row `oy` and each block of at most 128 output columns: clear `acc`;
  for each source row `sy` of `oy`'s span (`wy` its weight) and each output column `ox` of the block:
  `h = Σ_i wx_i * svf__coverage(f->bpp, row, sx0 + i)` over the in-range source pixels, `acc[ox - ox0] += h * wy`;
  then `out[...] = ((acc << 16) / den2 + 0x8000) >> 16` as today (`sum <= 255 * den² <= 65280` fits `uint16_t`).
  The `o / num`, `o % num` pairs are walked by increment, not divided per pixel. `span` and `overlap` stay only as
  far as `axis_weights` needs them. No scratch, no static buffer, under 1 KB of stack.

- [ ] **Step 1: Implement**

Per the Interfaces block; the header comment of the branch states the identity
`sum = Σ_sy wy · Σ_sx wx · cov` and the periodicity argument (output `o + num` covers source `s + den` with the same
weights) in two lines.

- [ ] **Step 2: Run the net and the gate**

Run: `make -C c check 2>&1 | tail -n 10`
Expected: `kernels: OK ... scale=<the same count as Task 5>`, `asan: OK` (TestScale's `test_box_filter_exact`,
`test_scaled_lines_match_reference` and the noscale build inside), `clang: OK`, exit 0.

- [ ] **Step 3: Run the scaled rows and the VESA PNGs**

```bash
sh c/bench/run-host.sh c/build/bench/host | grep -E 'scaled|end='
sh c/bench/run-dos.sh | grep -E 'scaled32 \|' ; sh c/bench/run-wasm.sh | grep scaled
sh c/bench/run-m33.sh | grep -E 'LINE.*scaled'; echo "exit $?"; sh c/bench/run-rp2350.sh | grep -E 'LINE.*scaled'; echo "exit $?"
bash c/ports/dos/vesa-shots.sh; git status --short c/ports/dos/shots
sh c/cross/build-all.sh c/build/cross | grep -E 'P[45] '
sh c/cross/build-all.sh --ports c/build/cross-ports 2>&1 | grep -c ': OK'
```
Expected: every `line40_scaled32` row `13e5d91d ok` and faster than Task 2's rows (host about 2x, WASM about 1.9x,
M33 about 1.9x `-Os`); the ten PNGs unchanged (the DOS example draws 3/2 on the packed kinds); P4/P5 sizes recorded;
`37`.

- [ ] **Step 4: Commit**

```bash
git add c/src/svf_scale.c
git commit -m "c/src: svf__scale_cell area-averaged branch as a separable box filter (per-axis periodic weights, 128-column accumulator); exact, no scratch change"
```

---

### Task 9: The cmap `mid` shift in `svf__glyph_index`

> **Re-plan after SVF v3 lands; carry F5, F6, F13, F15, F16, F18.** RP2350 gates: `run-rp2350.sh` (Task 4), not
> `run-hazard3.sh`.

**Files:**
- Modify: `c/src/svf_face.c:189`

**Interfaces:**
- Produces: `uint16_t mid = (uint16_t)(((unsigned)lo + hi) >> 1);` in place of `lo + (hi - lo) / 2` (the spec allows
  folding this into the card; `lo <= hi` and both `uint16_t`, so the two are equal and the sum fits `unsigned`). The
  remaining `uint16_t` loop counters of the library (`svf__mask_cell`, `svf__stream_rows`, the cache scans) are per
  row or per block, not per byte, and stay.

- [ ] **Step 1: Change the line and run the gate**

Run: `make -C c check 2>&1 | tail -n 4` — Expected: `asan: OK`, `clang: OK`, exit 0 (every glyph lookup of the golden
tests goes through it).

- [ ] **Step 2: Check the division is gone and the counts moved**

Run: `~/opt/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-gcc -std=c99 -Wall -Wextra -Werror -march=rv32imc_zicsr_zifencei -mabi=ilp32 -Os -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -Ic/include -c c/src/svf_face.c -o /tmp/face-c3.o && ~/opt/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-objdump -d /tmp/face-c3.o | awk '/<svf__glyph_index>:/,/^$/' | grep -cE '\bdiv|rem'`
Expected: 0. Then `sh c/bench/run-pico.sh | grep -E 'Os; MONO_PAGE.*syl_ga'` and `sh c/bench/run-esp32.sh | grep -E 'c3.*-Os.*syl_ga'`:
instructions per iteration not above Task 7's; every row `ok`.

- [ ] **Step 3: Commit**

```bash
git add c/src/svf_face.c
git commit -m "c/src: svf__glyph_index takes the midpoint by an unsigned shift (no division per probe)"
```

---

### Task 10: After rows, before/after tables, sizes, Still over budget

> **Re-plan after SVF v3 lands; carry F5, F6, F13, F15, F16, F18.** RP2350 gates: `run-rp2350.sh` (Task 4), not
> `run-hazard3.sh`.

**Files:**
- Modify: `c/bench/MEASUREMENTS.md`, `c/bench/measurements-raw.txt`, `c/cross/SIZES.md`
- Test: `python3 -I c/bench/check-measurements-md.py`, `make -C c check`, `c/cross/build-all.sh --ports`

**Interfaces:**
- Consumes: Task 1's and Task 2's `c/build/bench/before/*` and `c/build/cross-before.md` (the before), the runs below
  (the after).

- [ ] **Step 1: Run everything on the branch head**

```bash
set -o pipefail; A=$PWD/c/build/bench/after; mkdir -p "$A"
sh c/bench/run-host.sh "$A/host" | tee "$A/host.md"; echo "exit $?"
sh c/bench/run-dos.sh "$A/dos" | tee "$A/dos.md"; echo "exit $?"
sh c/bench/run-wasm.sh "$A/wasm" | tee "$A/wasm.md"; echo "exit $?"
sh c/bench/run-pico.sh "$A/pico" | tee "$A/pico.md"; echo "exit $?"
PROFILE=1 sh c/bench/run-pico.sh "$A/pico-prof" | tee "$A/pico-prof.md"; echo "exit $?"
sh c/bench/run-esp32.sh "$A/esp32" | tee "$A/esp32.md"; echo "exit $?"
sh c/bench/run-avr.sh "$A/avr" | tee "$A/avr.md"; echo "exit $?"
sh c/bench/run-m33.sh "$A/m33" | tee "$A/m33.md"; echo "exit $?"
sh c/bench/run-rp2350.sh "$A/rp2350" | tee "$A/rp2350.md"; echo "exit $?"
sh c/cross/build-all.sh c/build/cross | tee c/build/cross-after.md
sh c/cross/build-all.sh --ports c/build/cross-ports 2>&1 | grep -c ': OK'
bash c/ports/dos/vesa-shots.sh; git status --short c/ports/dos/shots
make -C c check 2>&1 | tail -n 4
```
(`pipefail` so each `exit` is the runner's, not `tee`'s; absolute OUTs because `run-dos.sh` refuses a relative one;
`vesa-shots.sh` with no argument, its default being `c/build/ports/dos-vesa`.)
Expected: every row `ok`; DOS and Pico exit 0 or 2, the rest 0; `37`; no PNG change; the gate green. Run `run-dos.sh`
and `run-pico.sh` a second time and `diff` the rows (the DOS spread rule of MEASUREMENTS.md; the Pico rows identical).

- [ ] **Step 2: Replace the result tables**

Every result table of `MEASUREMENTS.md` (Pico x 3 kinds, Uno, DOS 486, Packed kinds, WASM, Host (Task 2's
section), ESP32-C3, ESP32-S3, Cortex-M33 (QEMU), RP2350 Hazard3 and RP2350 Cortex-M33 (rp2350js)) gets the after rows; the header paragraph names the commit measured. Regenerate
`measurements-raw.txt` (`--raw` with the after directories pico, esp32, m33, rp2350) and the ratio block (`--print`).

- [ ] **Step 3: Write the before/after tables**

A new section `## Before -> after the C speedups (2026-10-21, 344a090 -> <head>)` with one table per target
(`| case | before | after | ratio |`, the unit named per target: µs emulated for Pico/DOS/Uno, instructions for
ESP32-C3/S3 and the QEMU M33, rp2350js cycles for the RP2350 Hazard3 and M33, host µs for WASM), covering: Pico MONO_PAGE `-Os`/`-O2` syl_ga, syl_bwelk, compose_bwelk,
screen32, line8; Pico GRAY8 and RGB565 set B; DOS DX2-66 and DX-33 `line40_mapped`, `_cache`, `stream_*`,
`line40_scaled32`, and the packed rows (only the merge reaches them: PAPLG18 and MARUS24A compose 2 bpp pieces,
MARUS24 1 bpp ones; the table is GRAY8-only, so say so above the packed rows); WASM; ESP32-C3/S3 the same cases;
the QEMU M33 and the rp2350js Hazard3 and M33 (Tasks 3-4 rows against Step 1); Uno (unchanged cycles, flash before/after). Below each table the per cent of the Pico profile
(`PROFILE=1`) that `svf__merge` takes before and after, from the two `pico-prof` runs. Also a "How often the aligned
word path fires" note: the faces' `data_off` parity (above) and the `insns` delta of `syl_bwelk` on the Pico.

- [ ] **Step 4: Update the budget sections**

"Against the budgets": the after column and verdicts (DOS DX2-66 mapped margin, Pico `syl_ga`/`syl_bwelk` `-Os`,
WASM, Uno fit). "Still over budget": the rows that remain, with the new numbers, naming t_8a3815c4 (DOS cold /
nocache / small, DX-33) and t_4108b260 (Pico `syl_bwelk`; the 50 µs budget applies with the syllable cache on,
user 2026-10-21), and t_8b967a59 if `syl_ga` `-Os` is still over; drop rows that are now met.

- [ ] **Step 5: Re-measure SIZES.md**

Replace the Sizes table with `c/build/cross-after.md`'s (now with `cortex-m33` and `hazard3-rp2350` rows), add a
section `### Before -> after the C speedups` (text before/after/change per toolchain and profile from
`c/build/cross-before.md` plus the two new toolchains' Task 3/4 rows), and in Findings: M0+ P1/P2 against 8192 (the
numbers), P3g and P1* with the 2 KB table, the RP2350 rows "no budget", AVR P1 (byte SWAR only). `build-all.sh --ports`
already compared the Port examples table (Step 1 printed 37): if a port row moved, update that table with the measured
values and re-run `sh c/cross/build-all.sh --ports c/build/cross-ports 2>&1 | grep -c ': OK'` to 37.

- [ ] **Step 6: Check and commit**

Run: `python3 -I c/bench/check-measurements-md.py c/bench/MEASUREMENTS.md; echo $?` (silent, 0) and
`make -C c check 2>&1 | tail -n 3` (green: `TestBenchSums.test_measurements_md_numbers_are_derived` reads the
new file; if its doctored-copy anchors (`| 6335 | 50.68 |` and the others) no longer exist, update those anchors in
`tools/test_c_renderer.py` to rows of the new tables).
```bash
git add c/bench/MEASUREMENTS.md c/bench/measurements-raw.txt c/cross/SIZES.md tools/test_c_renderer.py
git commit -m "docs: MEASUREMENTS before/after per target for the C speedups (QEMU M33 and rp2350js Hazard3/M33 included), SIZES re-measured with the RP2350 rows, Still over budget handed to t_8a3815c4 / t_4108b260"
```

---

## Self-review notes

- Spec coverage: the merge (Task 6, byte SWAR, word loop for 1 and 2 bpp, alignment rule, `SVF_RD8` rule, unsigned
  counters, `mkface.py` alignment), the table (Task 7, switch, placement, size rule, INDEXED8 untouched), the box
  filter (Task 8, no scratch change), the switches and their documentation (Task 6), code size and the 8 KB gate
  (every library task's Step with `build-all.sh`, Task 10), the target matrix and runners (Tasks 3, 4), the scaled
  case (Task 2), exactness gates (every task), `test_kernels` (Task 5), budgets and "Still over budget" (Task 10),
  the `mid` shift (Task 9, allowed by the spec); Cortex-A out of scope and the asm section need no task.
- Gaps resolved against the spec, stated where they apply: (1) the spec's "both pointers 4-aligned" word path can
  never fire on the strict-align targets because every bench face's `data_off` is odd, so Task 6 takes the spec's
  named fallback (source words assembled from bytes, native word only for the aligned destination, M33 and
  Cortex-A through `__ARM_FEATURE_UNALIGNED`), and the switch defaults to 1 only on little-endian targets, which
  the assembly order requires; (2) the spec says the scaled case's checksum comes "through sums.py/sums.inc.sh as
  every other case" while the DOS/WASM line sums are literals in the runners: Task 2 adds `SUMS_LINE40` to both
  files and a host test that pins the C output to it; (3) the spec names MONO_PAGE and GRAY8 builds for the new
  runners and expects an RGB565 M33 ratio in its matrix: the runners build all three kinds, as `run-esp32.sh` does;
  (4) the spec's "widening the loop counters" is the loop variables of the loops Task 6 rewrites and cannot be a
  separate gate, so the separate small task is the spec-allowed `mid` shift (Task 9); (5) the accumulator of the box
  filter is bounded on the stack by 128-column blocks (256 B) rather than the spec's 4 KB or the scratch, which has
  no room for it on the last output row.

## Appendix A: `c/bench/rp2350js.patch`

The file is these header lines followed by the diff below, unchanged (patch(1) and `git apply` skip text before the
first `diff --git`). The diff part's sha256 is `61596cb94ca344b24dd1ae6ee118449f35c776cd7f70481a03ffbb75a61b7056`.

Header:
```
rp2350js.patch - applied by c/bench/install-emulators.sh (name rp2350js) to github.com/c1570/rp2350js at commit
af0114cbee8e9e91574204b66f10aa2961cbf28c before it is built. Four emulator fixes, found when the svf-fonts pico2 and
pico2 RISC-V images were run under rp2350js (2026-10-21): the Cortex-M33 GPIO coprocessor's MCR/MRC/MCRR decoding
(pico-sdk gpio_coproc.h); the Zcmp cm.mvsa01 / cm.mva01s register fields (s0-s1, s2-s7); Zbb orc.b (any non-zero
byte, not bit 7) and the zip/unzip bit order; sltiu's sign-extended immediate compared unsigned. Without them the
bench's Hazard3 images stop with an emulator error or a wrong checksum. The lines marked SPIKE PATCH are the changes.
```

Diff:
```diff
diff --git a/src/cortex-m33/coprocessor.ts b/src/cortex-m33/coprocessor.ts
index 4c7f3ba..5d47643 100644
--- a/src/cortex-m33/coprocessor.ts
+++ b/src/cortex-m33/coprocessor.ts
@@ -63,106 +63,48 @@ function writeMrcResult(core: CortexM33Core, Rt: number, value: number) {
 // ============================================================================
 
 function cp0Gpioc(core: CortexM33Core, hw0: number, hw1: number): number {
-  if (!isMrcMcr(hw0, hw1)) return 1; // CDP → NOP
-
-  const opc1 = (hw0 >>> 5) & 0x7;
-  const CRn = hw0 & 0xf;
-  const opc2 = (hw1 >>> 5) & 0x7;
+  // SPIKE PATCH: decode per pico-sdk gpio_coproc.h. MCR/MRC: opc1 = op, CRm = bank
+  // (0 OUT lo, 1 OUT hi, 4 OE lo, 5 OE hi, 8 IN lo, 9 IN hi). MCRR/MRRC: opc1 = op, CRm = 0 OUT / 4 OE / 8 IN.
+  const sio = core.chip.sio;
+  const r = core.regs.r;
+  const ci = core.coreIndex;
   const CRm = hw1 & 0xf;
   const Rt = (hw1 >>> 12) & 0xf;
-  const isRead = ((hw0 >>> 4) & 1) !== 0; // L bit: 1=MRC (read), 0=MCR (write)
-  const regs = core.regs;
-
-  // Bank select: 0=LO OUT, 1=LO OE, 2=LO IN, 4=HI OUT, 5=HI OE, 6=HI IN.
-  const isInput = opc1 === 2 || opc1 === 6;
-  const isOe = opc1 === 1 || opc1 === 5;
-  const isHi = opc1 >= 4;
-  void isHi; // HI bank is RAZ/WI on RP2350.
-
-  const sio = core.chip.sio;
-
-  // SIO GPIO register offsets (RP2350 layout — differs from RP2040).
-  const GPIO_OUT = 0x010;
-  const GPIO_OUT_SET = 0x018;
-  const GPIO_OUT_CLR = 0x020;
-  const GPIO_OUT_XOR = 0x028;
-  const GPIO_OE = 0x030;
-  const GPIO_OE_SET = 0x038;
-  const GPIO_OE_CLR = 0x040;
-  const GPIO_OE_XOR = 0x048;
-  const GPIO_IN = 0x004;
-
-  const baseOffset = isInput ? GPIO_IN : isOe ? GPIO_OE : GPIO_OUT;
-
-  const isBulk = CRn === 0 && CRm === 0;
-  if (isBulk) {
+  // SIO: IN 0x04 (HI 0x08), OUT 0x10, OE 0x30; put +0, xor +0x18, set +0x08, clr +0x10; HI = +4
+  const OPD = [0, 0x18, 0x08, 0x10];
+  const baseOf = (crm: number) => ((crm & 4) ? 0x30 : 0x10) + ((crm & 1) ? 4 : 0);
+  const wr = (crm: number, op: number, v: number) => sio.writeUint32(baseOf(crm) + OPD[op], v >>> 0, ci);
+  const rd = (crm: number) => (crm & 8) ? sio.readUint32((crm & 1) ? 0x08 : 0x04, ci) : sio.readUint32(baseOf(crm), ci);
+  const bit = (crm: number, op: number, pin: number) => {
+    pin &= 63;
+    wr((crm & 4) | (pin >= 32 ? 1 : 0), op, 1 << (pin & 31));
+  };
+  const top = (hw0 >>> 8) & 0xff; // 0xee/0xfe MCR/MRC, 0xec/0xfc MCRR/MRRC
+  const isRead = ((hw0 >>> 4) & 1) !== 0;
+  if ((top & 0xef) === 0xee) {
+    if ((hw1 & 0x10) === 0) return 1; // CDP
+    const opc1 = (hw0 >>> 5) & 7;
+    if (isRead) { writeMrcResult(core, Rt, rd(CRm)); return 1; }
+    const v = r[Rt];
+    if (opc1 <= 3) wr(CRm, opc1, v);
+    else if (opc1 >= 5) bit(CRm, [0, 0, 0, 0, 0, 1, 2, 3][opc1], v);
+    return 1;
+  }
+  if ((top & 0xef) === 0xec && ((hw0 >>> 5) & 7) === 2) {
+    const Rt2 = hw0 & 0xf;
+    const opc1 = (hw1 >>> 4) & 0xf;
     if (isRead) {
-      if (isInput) {
-        writeMrcResult(core, Rt, sio.readUint32(GPIO_IN, core.coreIndex) & PIN_MASK);
-      } else if (!isHi) {
-        writeMrcResult(core, Rt, sio.readUint32(baseOffset, core.coreIndex) & PIN_MASK);
-      } else {
-        writeMrcResult(core, Rt, 0); // HI bank RAZ
-      }
-    } else {
-      const val = regs.r[Rt] & PIN_MASK;
-      if (!isInput && !isHi) {
-        switch (opc2) {
-          case 0:
-            sio.writeUint32(baseOffset, val, core.coreIndex);
-            break;
-          case 1:
-            sio.writeUint32(isOe ? GPIO_OE_SET : GPIO_OUT_SET, val, core.coreIndex);
-            break;
-          case 2:
-            sio.writeUint32(isOe ? GPIO_OE_CLR : GPIO_OUT_CLR, val, core.coreIndex);
-            break;
-          case 3:
-            sio.writeUint32(isOe ? GPIO_OE_XOR : GPIO_OUT_XOR, val, core.coreIndex);
-            break;
-        }
-      }
-    }
-  } else {
-    // Per-bit operation.
-    const pin = (CRn << 4) | CRm;
-    if (pin >= 30) {
-      if (isRead) writeMrcResult(core, Rt, 0);
+      r[Rt] = rd(CRm) >>> 0;
+      r[Rt2] = rd(CRm | 1) >>> 0;
       return 1;
     }
-    const bitMask = 1 << pin;
-    if (isRead) {
-      if (isInput) {
-        writeMrcResult(core, Rt, (sio.readUint32(GPIO_IN, core.coreIndex) >> pin) & 1);
-      } else {
-        writeMrcResult(core, Rt, (sio.readUint32(baseOffset, core.coreIndex) >> pin) & 1);
-      }
-    } else {
-      if (!isInput && !isHi) {
-        switch (opc2) {
-          case 4:
-            // Per-bit "put": Rt[0]=1 → set only this pin; Rt[0]=0 → clear only
-            // this pin. Must NOT do a bulk write (which zeroes every other pin).
-            if (regs.r[Rt] & 1) {
-              sio.writeUint32(isOe ? GPIO_OE_SET : GPIO_OUT_SET, bitMask, core.coreIndex);
-            } else {
-              sio.writeUint32(isOe ? GPIO_OE_CLR : GPIO_OUT_CLR, bitMask, core.coreIndex);
-            }
-            break;
-          case 5:
-            sio.writeUint32(isOe ? GPIO_OE_SET : GPIO_OUT_SET, bitMask, core.coreIndex);
-            break;
-          case 6:
-            sio.writeUint32(isOe ? GPIO_OE_CLR : GPIO_OUT_CLR, bitMask, core.coreIndex);
-            break;
-          case 7:
-            sio.writeUint32(isOe ? GPIO_OE_XOR : GPIO_OUT_XOR, bitMask, core.coreIndex);
-            break;
-        }
-      }
-    }
+    if (opc1 <= 3) { wr(CRm, opc1, r[Rt]); wr(CRm | 1, opc1, r[Rt2]); }
+    else if (opc1 === 4) bit(CRm, (r[Rt2] & 1) ? 2 : 3, r[Rt]);
+    else if (opc1 <= 7) { if (r[Rt2] & 1) bit(CRm, [0, 0, 0, 0, 0, 1, 2, 3][opc1], r[Rt]); }
+    else if (opc1 <= 11) wr(CRm | (r[Rt2] & 1), opc1 - 8, r[Rt]);
+    return 1;
   }
-  return 1;
+  return -1;
 }
 
 // ============================================================================
diff --git a/src/riscv/cpu.ts b/src/riscv/cpu.ts
index 40d9343..4b7b392 100644
--- a/src/riscv/cpu.ts
+++ b/src/riscv/cpu.ts
@@ -613,8 +613,8 @@ export class CPU implements ICpuCore {
         const u = this.getRegisterU(s1);
         let result = 0;
         for (let i = 0; i < 16; i++) {
-          result |= ((u >>> (16 + i)) & 1) << (2 * i);
-          result |= ((u >>> i) & 1) << (2 * i + 1);
+          result |= ((u >>> i) & 1) << (2 * i); // SPIKE PATCH: low half to even bits
+          result |= ((u >>> (16 + i)) & 1) << (2 * i + 1);
         }
         this.setRegisterU(r, result >>> 0);
         break;
@@ -623,8 +623,8 @@ export class CPU implements ICpuCore {
         const u = this.getRegisterU(s1);
         let result = 0;
         for (let i = 0; i < 16; i++) {
-          result |= ((u >>> (2 * i + 1)) & 1) << i;
-          result |= ((u >>> (2 * i)) & 1) << (16 + i);
+          result |= ((u >>> (2 * i)) & 1) << i; // SPIKE PATCH: even bits to low half
+          result |= ((u >>> (2 * i + 1)) & 1) << (16 + i);
         }
         this.setRegisterU(r, result >>> 0);
         break;
@@ -633,7 +633,7 @@ export class CPU implements ICpuCore {
         this.setRegister(r, this.getRegister(s1) < imm ? 1 : 0);
         break;
       case T_SLTIU:
-        this.setRegister(r, this.getRegisterU(s1) < (imm & 0xfff) ? 1 : 0);
+        this.setRegister(r, this.getRegisterU(s1) < (imm >>> 0) ? 1 : 0); // SPIKE PATCH: sx12 imm compared unsigned (was imm & 0xfff)
         break;
       case T_XORI:
         this.setRegister(r, this.getRegister(s1) ^ imm);
@@ -687,7 +687,7 @@ export class CPU implements ICpuCore {
         const u = this.getRegisterU(s1);
         let result = 0;
         for (let i = 0; i < 32; i += 8) {
-          if (u & (0x80 << i)) result |= 0xff << i;
+          if (u & (0xff << i)) result |= 0xff << i; // SPIKE PATCH: any nonzero byte (was bit 7 only)
         }
         this.setRegisterU(r, result >>> 0);
         break;
diff --git a/src/riscv/decode.ts b/src/riscv/decode.ts
index 9b07e18..90ce907 100644
--- a/src/riscv/decode.ts
+++ b/src/riscv/decode.ts
@@ -21,6 +21,9 @@ const LEN_SHIFT = 8;
 const LEN_32 = 1 << LEN_SHIFT;
 const LEN_16 = 0;
 
+// SPIKE PATCH: Zcmp sreg mapping (s0,s1 = x8,x9; s2..s7 = x18..x23)
+const zcmpSreg = (v: number) => (v < 2 ? 8 + v : 16 + v);
+
 function emit(
   tag: number,
   rd: number,
@@ -741,13 +744,13 @@ function decodeC2(inst: number): Int53 {
       }
       const masked2 = inst & 0b1111110001100011;
       if (masked2 === 0b1010110000100010) {
-        const r1s = 8 + ((inst >>> 7) & 1);
-        const r2s = 8 + ((inst >>> 2) & 1);
+        const r1s = zcmpSreg((inst >>> 7) & 7); // SPIKE PATCH (was 8 + bit 7)
+        const r2s = zcmpSreg((inst >>> 2) & 7); // SPIKE PATCH (was 8 + bit 2)
         return emit(T_CM_MVSA01, r1s, r2s, 10, 11, LEN_16);
       }
       if (masked2 === 0b1010110001100010) {
-        const r1s = 8 + ((inst >>> 7) & 1);
-        const r2s = 8 + ((inst >>> 2) & 1);
+        const r1s = zcmpSreg((inst >>> 7) & 7); // SPIKE PATCH (was 8 + bit 7)
+        const r2s = zcmpSreg((inst >>> 2) & 7); // SPIKE PATCH (was 8 + bit 2)
         return emit(T_CM_MVA01S, 10, 11, r1s, r2s, LEN_16);
       }
       break;
```
