# Portable C speedups for the C SVF renderer: design

Card t_662ef38c, 2026-10-21. Follows the SIMD feasibility study (card t_aa395fa1, `simd-feasibility.md`, spike code in
`simd-spike/`). Inputs: `spec/renderer-design.md`, `c/bench/MEASUREMENTS.md`, `c/cross/SIZES.md`, the library on branch
vesa-out (`c/src` at 80ab754, about to land on main). The user's direction (2026-10-21): do the C optimisation first,
on every target, not only x86: ARM and RISC-V too (ESP32 and Raspberry Pi Pico). Calls made here are marked
**(design call)**; everything else is measured or ruled already.

## Why

The feasibility study found that the only changes that move a budget-bearing target are plain C, and that they also
shrink what any later SIMD must do. Three changes were prototyped and proved byte-identical, every lane:

| change | where it applies | measured gain (end to end unless said) |
|---|---|---|
| SWAR 2 bpp piece merge (`svf__merge`, 2 bpp: per-2-bit-field max as a carry-free bitwise formula on 32-bit words) | every 2 bpp jamo face: composition | merge kernel 6-7x (x86, DOS i386 instructions, M33, aarch64); DOS 486 line40 15.19 -> 13.05 ms (1.16x); host GRAY8 set B 1.16x, RGB565 set B 1.17x; M33 RGB565 set B 1.19x |
| 1 bpp -> GRAY8 table (`blit_gray8`, 1 bpp: 2 KB table, 8 coverage bytes per source byte, ORed in) | GRAY8 target, 1 bpp faces | kernel 5x (x86 and DOS), 1.6x aarch64; host GRAY8 set A 5.27 -> 3.44 us (1.53x); M33 set A 1.48x |
| separable box filter (`svf__scale_cell`, ratios other than whole multiples: weights per axis once, same integer sums) | every scaled line that is not a whole multiple | host 2.2x (GRAY8 3/2), 1.84x (XRGB8888); M33 1.91x `-Os` / 2.37x `-O2`; DOS i386 instructions 2.2x; aarch64 1.5x |

The exactness rule for this project is "exact by default; a fast mode may deviate only within bounds". This card has
**no fast mode**: every change is byte-identical, and the existing gates are the proof (below).

## What changes, what does not

Three functions change: `svf__merge` (svf_jamo.c), the 1 bpp case of `blit_gray8` (svf_draw.c) and the area-averaged
branch of `svf__scale_cell` (svf_scale.c). Everything else stays: the walker, the cache, the stream code, every other
blit, every public declaration, the no-malloc and no-static-data rules (a `static const` table is read-only data in
text, which SIZES.md already counts as text; the library keeps data 0, bss 0), the three allowed headers, `-Werror` on
every toolchain. No SIMD, no inline asm, no intrinsics: that is the SIMD card (t_aa395fa1, after this one).

### 1. The merge

`svf__merge(f, dst, src, n)` keeps its contract (any run of bytes, `src` in face memory read through `SVF__RD8`).

- **2 bpp.** Per byte, the spike's formula replaces the 4-field loop outright **(design call)**: `xh=(x&0xAA)>>1`,
  `yh=(y&0xAA)>>1`, `eq=~(xh^yh)`, `lo=((eq&(x|y))|(xh&~yh&x)|(yh&~xh&y))&0x55`, result `((x|y)&0xAA)|lo`. The old
  loop goes; the byte form is smaller than it on every ISA read (below) and is the reference the word form is tested
  against. Where `SVF_MERGE_WORDS` is 1 the run is done 4 bytes at a time with the same formula on `uint32_t`
  (constants 0xAAAAAAAA / 0x55555555), then the byte form for the tail. The formula is per byte, so it has no
  endianness and no carries: the word form is exact by construction and the exhaustive test confirms it.
- **1 bpp.** The same word loop does the OR **(design call: a fourth change, free once the word loop exists)**; the
  byte loop stays as the tail. On the Pico the budget case is a 1 bpp face (HGKEY6J), where `svf__merge` is 12.2 % of a
  syllable in the profile build, so this is the part of the card that touches the Pico budget at all.
- **8 bpp** stays byte by byte (no face uses it).
- **Word access without assuming alignment, and without `memcpy` where the ISA is strict-align** **(design call)**.
  Where `SVF_WORD_STORE` is 1 (x86, WASM: unaligned loads are one instruction) a 4-byte `memcpy` is the load. Elsewhere
  a 4-byte `memcpy` is the wrong tool: riscv32-esp-elf gcc 16.1 under `-mstrict-align` (the C3 default and the
  pico-sdk's Hazard3 default) expands it into eight `sb` to the stack and two `lw` back, a round trip that costs more
  than the arithmetic it feeds (checked on the spike's `merge2_swar`, both with and without Zb*); Cortex-M0+ gcc
  does better (`ldrb` + `lsls` + `orrs`). So on every non-`SVF_WORD_STORE` target the word loop runs only when
  `dst` and `src` are both 4-aligned at run time (one test per call, then plain `uint32_t` loads and stores) and
  the byte forms take the rest. `svf_compose`'s `cell` is the caller's scratch and `src` is
  `f->data + data_off + g * stride`, so alignment is the caller's and the face's business; the builder records for
  the bench faces whether their rows are aligned (HGKEY6J: stride 32, so all rows or none) and `mkface.py` aligns
  the embedded arrays to 4. The byte-assembled variant (`p[0] | p[1] << 8 | ...`, explicit shifts, no `memcpy`) is
  the fallback if the aligned case proves rare on a target that matters; it is the builder's to measure.
- **Word loop and `SVF_RD8`.** The word form reads face memory with plain loads, so it compiles only where
  `SVF_RD8_PLAIN` is defined (every build but AVR's `pgm_read_byte` override) or, with an override, for a streamed
  face (`f->rd`, all RAM). A streamed face's pieces arrive through `svf__stream_rows` with `merge` set, which calls
  `svf__merge` on RAM; nothing there changes.
- **Loop counters.** `k` and `n` are `uint16_t` today, and every ISA pays a zero-extension per iteration for it (`uxth`
  on M0+, `slli; srli` on RV32, `extui` on Xtensa, see below). The rewritten loops count in `unsigned`
  **(design call)**; the signature keeps `uint16_t n`.

### 2. The 1 bpp GRAY8 table

`static const uint8_t svf__lut1[256][8]` under `#if (SVF_TARGETS & SVF_TARGET_GRAY8) && SVF_GRAY8_LUT1`, in
svf_draw.c, generated by nested macros at compile time (no generated file to keep in sync, no init code)
**(design call)**. The 1 bpp case of `blit_gray8` becomes: for a source byte wholly inside the cut (`lo == b*8` and
`hi == b*8+8`), OR the entry's 8 bytes into the 8 target bytes (a byte loop that gcc unrolls, or two words after the
same aligned check as the merge on strict-align targets; `memcpy` where `SVF_WORD_STORE` is 1), with the partial first and last bytes keeping today's
bit loop. `max(d, 255) == d | 255` and `max(d, 0) == d | 0`, so OR is the GRAY8 max rule exactly. The table is bytes,
not `uint64_t`, so it has no endianness. It is linked only when GRAY8 is compiled in and the switch is 1, which keeps
every MONO_PAGE and RGB565 build at its size. The 2 bpp table of the spike (1 KB) is **not** in this card: with a
scalar byte max it measured no faster than the bit loop on x86, M33 and aarch64; it pays only with a vector max (SIMD
card). INDEXED8 1 bpp is a max against `top`, not an OR, and is left as it is.

### 3. The separable box filter

`svf__scale_cell`'s area-averaged branch computes, per output pixel, `span()` and `overlap()` for both axes and reads
every source pixel `den` times through `svf__coverage`. The exact sum is
`sum = Σ_sy wy(sy,oy) · Σ_sx wx(sx,ox) · cov(sx,sy)`, with `wx`, `wy` the integer overlaps, and the result
`((sum << 16) / den² + 0x8000) >> 16` as now; the same integers in another order give the same bytes, which is what
the spike's 818,987-pixel sweep confirmed. The spike used 64 KB of static buffers; the library may use none. Shape
**(design call)**:

- The weights are periodic: output pixel `ox + num` covers source pixels `sx + den` with the same overlaps. So the
  per-axis tables hold `num` entries (num <= 16), each a start offset, a count (<= ceil(den/num) + 1 <= 17) and the
  weights: at most 2 × 16 × 19 bytes on the stack, independent of the face.
- Per output row: for each source row of its span, expand that row's coverage once into a byte row (`cell_w` <= 255
  bytes, stack), accumulate the horizontal sums times `wy` into a `uint16_t` accumulator of `sw` entries
  (`sum <= 255 · den² <= 65280` fits), then divide out. The accumulator is the one buffer that depends on the face
  (`sw` <= 255 · 16 / 1 = 4080 only for num/den = 16/1, which is the block path; for den >= 2 `sw` <= 2040 and for
  every repo face <= 46 · 8 = 368). It lives in the caller's scratch: the scaled cell is written row by row, so the
  rows not yet written are free; the builder may instead bound it on the stack at 2 × 255 · 8 bytes, whichever is
  simpler to prove in review. No new scratch requirement: `svf_chain_scratch_bytes` does not change.
- A source row is read by at most two output rows when scaling up and by ceil(den/num) + 1 when scaling down, so
  the coverage expansion is repeated at most that often; that is still far below today's `den` reads per source
  pixel.

The whole-multiple block path, `svf__scale_len` and `svf__scale_dim` do not change. There is no switch: one
implementation, exact.

## Build switches and per-target defaults

| switch | meaning | default |
|---|---|---|
| `SVF_MERGE_WORDS` | the 4-byte word loop in `svf__merge` (1 bpp OR, 2 bpp SWAR); 0 keeps the byte forms only | 1, except 0 on `__AVR__` (8-bit registers; the byte SWAR is already the win there) |
| `SVF_GRAY8_LUT1` | the 2 KB 1 bpp -> GRAY8 table | 1, except 0 on `__AVR__` (flash) |
| `SVF_WORD_STORE` | unchanged (VESA): the packed-kind word stores | unchanged |

Both new switches follow the `SVF_WORD_STORE` pattern in `svf.h` (`#ifndef`, arch default, `-D` override), so a port
can turn either off. `SVF_NO_SCALE` keeps leaving all of svf_scale.c out. No switch keeps the old 2 bpp merge loop or
the old box filter: before/after is measured from git (main before the merge of this branch against the branch), the
way MEASUREMENTS.md records every earlier step **(design call)**.

What each target compiles by default:

| target | merge words | 1 bpp table | separable scale | note |
|---|---|---|---|---|
| x86 host, WASM, DOS (DJGPP, i486) | yes (one unaligned load each) | yes | yes (P4/P5) | |
| Cortex-M0+ (Pico, P1/P2/P3) | yes (aligned check; byte forms otherwise) | yes in GRAY8 builds only (P3g, P1*); never in P1/P2 (no GRAY8) | no (`SVF_NO_SCALE`) | |
| Cortex-M33 (RP2350 ARM) | yes (unaligned loads are native) | yes | as the profile | no board, no cycle model: instruction counts |
| Hazard3 RV32IMAC+Zb* (RP2350 RISC-V) | yes (aligned check: Hazard3 is strict-align) | yes | as the profile | instruction counts on QEMU `virt`; Zb* gives gcc `andn`, `maxu`, `bext` for free (below) |
| ESP32-C3 (RV32IMC), ESP32-S3 (Xtensa LX7) | yes | yes in GRAY8 builds | no (`SVF_NO_SCALE` in the bench and ports) | |
| AVR (ATmega328P) | no: byte SWAR only | no | no | 8-bit; flash 954 B to spare in the bench build |
| Cortex-A (qemu-user) | as host | yes | yes | built, not timed (below) |

## Code size

Limits: Cortex-M0+ P1/P2 <= 8192 B (now 5674); AVR bench build 31,302 of 32,256 B flash (954 to spare), Arduino port
26,442. From the spike (`arm-none-eabi-gcc 15.2.1 -Os`, library text + data):

- **M0+ P1/P2** (MONO_PAGE only, `SVF_NO_SCALE`): +136 B for the SWAR merge, no table (no GRAY8), no scale: about
  5810 B, 2382 B under the limit. The word loop for 1 bpp adds a little on top; the removed 4-field loop gives some
  back. The builder re-runs `c/cross/build-all.sh` and `check-sizes-md.sh`; the gate line is P1/P2 <= 8192.
- **M0+ GRAY8 builds** (P3g 5542, P1* 8474): +136 B and +2 KB table, about 7.7 KB and 10.6 KB. P3g has no budget;
  P1* was already accepted over 8 KB (user, 2026-10-21): a small target chooses its kinds through `SVF_TARGETS`.
- **M33** (spike): GRAY8-only 6364 -> 8828 (+2464: the table and the separable scale, scale on); every kind
  9440 -> 11,904.
- **Hazard3**: the P1-shape objects (`svf_draw.c` MONO_PAGE, `svf_jamo.c`, `svf_face.c`, `-Os`) are 3332 + 1450 +
  1748 B with `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb` against 3478 + 1480 + 1770 with the C3's
  `rv32imc_zicsr_zifencei`: Zb* saves 3-4 % by itself. The merge, table and scale deltas are the C3's order.
- **The 8 KB budget and the RP2350** **(controller call)**: the P1/P2 <= 8192 B budget was set for the Cortex-M0+
  (RP2040, 264 KB SRAM, the small target). It does **not** apply to RP2350 builds, ARM M33 or RISC-V Hazard3: the
  RP2350 has 520 KB of SRAM and is not the small target. Their sizes are recorded in SIZES.md as rows without a
  budget, like the ESP32 rows.
- **AVR**: the byte SWAR replaces a loop of 16-bit shift loops (below), so the merge shrinks; no table, no words. The
  bench build must stay under 32,256 and `run-avr.sh` fails it otherwise.
- **Where the table lives**: `.rodata` of svf_draw.c under its own `#if`; with `-ffunction-sections -fdata-sections`
  and `--gc-sections` (every cross build) it is dropped whenever `blit_gray8`'s 1 bpp case does not reference it. The
  P1/P2 builds compile neither.

## Target matrix: what applies, how it is measured, what to expect

Every number is emulated or an instruction count, labelled as MEASUREMENTS.md labels it today. "Expected" uses the
feasibility numbers where they exist; a blank means no measurement yet and the builder's run is the first.

| target | applies | runner and metric | expected |
|---|---|---|---|
| x86-64 host | all three | `run-host.sh` (times are the host's; it is the checksum source for DOS) plus the scaled case below | GRAY8 set B 1.16x, set A 1.53x, scaled 2.2x (spike, same CPU) |
| WASM | all three | `run-wasm.sh`, node, `performance.now` | line40 13.03 -> 11.63 us (1.12x, spike), scaled 172.8 -> 90.5 us; the 1 ms budget is already met 45x |
| DOS 486 DX2-66 / DX-33 / Pentium (DOSBox-X instruction-calibrated presets) | merge (line40 is 2 bpp); table (1 bpp MARUS24 cases are not GRAY8: no row shows it); scale (new case) | `run-dos.sh`, PIT time under DOSBox-X; `_bytes` build unchanged | DX2-66 mapped 15.19 -> 13.05 ms (measured, L1486 raw), cache 9.96 -> 9.92, warm 15.05 -> 12.94, cold 29.35 -> 27.25; DX-33 by the 1.99 preset ratio about 30.2 -> 26 ms (still over); the Pentium preset is the SIMD card's business |
| Pico RP2040 M0+ | 1 bpp word OR (set A, MONO_PAGE budget rows), SWAR (set B rows, GRAY8/RGB565), table (GRAY8 set A rows) | `run-pico.sh`, rp2040js cycles and `insns`, `-Os` and `-O2`; `PROFILE=1` for the share | not measured in the spike. From the disassembly: the 2 bpp merge drops from about 90 to about 8 instructions a byte, the 1 bpp OR from 8 a byte to about 2 on aligned rows; `svf__merge` is 12.2 % of `syl_ga` at `-Os`, so a few per cent on the budget rows, more on `aa_*` |
| Cortex-M33 (RP2350 ARM) | all three (GRAY8 build with scale for the scaled case) | **new** `run-m33.sh`: QEMU `mps2-an505`, `-icount shift=0`, SysTick-calibrated instruction counts, semihosting (the spike's `m33.c`/`m33.ld` harness) | GRAY8 set B 297,359 -> 247,448 (1.20x `-Os`), set A 1.48x, RGB565 B 1.19x, scaled 1.91x / 2.37x (spike) |
| Hazard3 (RP2350 RISC-V) | all three (same builds as the M33 runner) | **new** `run-hazard3.sh`: QEMU `virt`, `-cpu rv32,zba=true,zbb=true,zbs=true,zbkb=true`, `-icount shift=0`, `rdinstret` as the C3 runner (below) | not measured; the C3's order (same compiler, Zb* on top): merge 3-4x, table 1.5x, scale 2x, with 3-4 % less code |
| ESP32-C3 (`rdinstret`), ESP32-S3 (core-0 `ICOUNT`) | SWAR (set B), word OR (set A), table (GRAY8 set A) | `run-esp32.sh`, instruction counts | not measured; the C3 merge loop is 9 instructions a field with a branch per field (below), so the SWAR gain is the M33's order; the S3 already has `loop` + `maxu` and gains less |
| AVR | byte SWAR only (no 2 bpp bench case: set A is 1 bpp); nothing else | `run-avr.sh`, simavr cycles; the flash fit | cycle rows unchanged (1 bpp path untouched); flash must not grow past 32,256 |
| Cortex-A (aarch64, armv7) | as host | none in this card (below) | kernels 4.5x merge, 1.5x scale (spike instruction counts) |

### Decision: the Cortex-M33 runner is in scope **(design call; the user approved it on 2026-10-21)**

RP2350 is a named target ("Raspberry Pi Pico" covers Pico 2), the card names Cortex-M33, no RP2350 model exists
(rp2040js 1.4.0 and QEMU have none), and the spike already ran the library on QEMU `mps2-an505` with calibrated
instruction counts. Cost: one pinned Ubuntu `qemu-system-arm` .deb (about 11 MB, sha256 recorded, `dpkg -x` into
`~/opt`, no sudo) added to `c/bench/install-emulators.sh` with `--verify`; `run-m33.sh` on the `run-esp32.sh` pattern
(MONO_PAGE and GRAY8, `-Os` and `-O2`, sets A and B, one GRAY8 build with scale for the scaled case); a `BENCH_M33`
section in `bench.c` for the SysTick read and semihosting output; `report.awk` rows labelled "instructions, QEMU, not
RP2350 cycles". About the size of the ESP32 runner, with the harness already written. It has no budget and never
will until a board or a cycle model exists; it is the only ARMv7-M/ARMv8-M data point, and the SIMD32 lane needs it
next.

### RP2350 RISC-V: Hazard3 (user, 2026-10-21: "rp2350 RISC-V도 커버해줘")

> **Amended 2026-10-21 (user: "4번을 rp2350js로 바꾸자", "다 추정이면 돌아가는 쪽이 좋다"):** the Hazard3 runner is not
> QEMU `virt`. `c/bench/run-rp2350.sh` builds real pico-sdk 2.3.1 `pico2` images for both RP2350 cores (Hazard3 with
> Raspberry Pi's `riscv32-pico-elf` toolchain, and the Cortex-M33) and runs them under rp2350js (pinned commit plus a
> committed patch of four emulator fixes), reading its cycle counter (µs at the SDK's 150 MHz). Every emulator gives an
> estimate, so the one that runs the real chip's firmware is preferred. QEMU `run-m33.sh` stays as the M33
> instruction-count cross-check. The `run-hazard3.sh` / QEMU `virt` text below and in the tables is superseded.

The RP2350's second core pair is Hazard3, RV32IMAC with the bit-manipulation extensions. pico-sdk 2.3.1
(`cmake/preload/toolchains/pico_riscv_gcc.cmake`) tries, in order, `-mcpu=hazard3-rp2350`, then
`-march=rv32ima_zicsr_zifencei_zba_zbb_zbs_zbkb_zca_zcb_zcmp`, then `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb`,
always `-mabi=ilp32` and, unless `PICO_NO_STRICT_ALIGN`, `-mstrict-align` (Hazard3 traps unaligned loads). Every
fact below was checked on this host on 2026-10-21.

- **Toolchain.** The pinned `riscv32-esp-elf-gcc` 16.1.0 (`~/opt/riscv32-esp-elf-esp-16.1.0_20260609`, already in
  `install-toolchains.sh` as `esp`) accepts both `-march` strings, emits `max`/`maxu`, `andn`, `bext` and the
  Zca compressed forms, and links the bench shape (`--specs=nosys.specs -nostartfiles`). It rejects
  `-mcpu=hazard3-rp2350` (unknown CPU: that name is in gcc 15's riscv-cores.def for newer builds but not in this
  crosstool-NG build). Its multilib has no Zb* variant, so libc and libgcc come from the
  `rv32imac_zmmul_zaamo_zalrsc_zca/ilp32` library; the bench calls only `memcpy`/`memset` and the library none, so
  that is harmless. **(design call)** Use the pinned ESP compiler with
  `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -mstrict-align` (the pico-sdk's third preference, the
  one every supporting gcc takes) and no new toolchain. Installing the Raspberry Pi `riscv32-pico-elf` toolchain
  (pico-sdk-tools, about 100 MB, a pin and a manifest in `install-toolchains.sh`) buys only Zcmp `cm.push/cm.pop`
  prologues (smaller code, same speed) and the `-mcpu` name; not worth it for a bench, and a port that builds with
  the pico-sdk gets the SDK's flags anyway.
- **Runner.** `run-hazard3.sh` **(design call)**: the pinned Espressif QEMU 9.2.2 `qemu-system-riscv32` already has
  the `virt` machine and the `rv32` CPU with the Zb* properties; `-M virt -cpu rv32,zba=true,zbb=true,zbs=true,zbkb=true
  -bios none -icount shift=0,sleep=off -nographic`, a bare-metal entry at 0x80000000 that sets `sp` and `gp`, the
  16550 at 0x10000000 for the rows, the sifive test finisher (0x100000, 0x5555) to end QEMU, `rdinstret` around
  each case. A test program using `maxu`, `bext` and `rdinstret` ran and counted (14,004 instructions for its loop)
  with the properties on, and hung in the illegal-instruction trap with them off, so the properties are load-bearing
  and the script must pass them. This is the `virt` fallback that the mcu-ports design (2026-10-20, its table of
  QEMU paths) already verified for the C3 and kept "as the documented fallback"; it becomes a runner of its own. No
  new emulator, no new download; `install-emulators.sh --verify qemu-rv` already guards it. Builds: the M33 runner's
  set (MONO_PAGE and GRAY8, `-Os` and `-O2`, sets A and B, one GRAY8 build with scale for the scaled case); rows
  labelled "Hazard3 emulated (QEMU 9.2.2 virt, rv32 + Zba/Zbb/Zbs/Zbkb, instructions by rdinstret, no pipeline or
  memory timing; not RP2350 cycles)", the C3's wording. Profile name in SIZES.md: `hazard3-riscv32`.
- **No RP2350 emulator exists here or anywhere found.** rp2040js 1.4.0 has no RP2350 (no file mentions it); QEMU
  9.2 has no RP2350 machine for either core; nothing models Hazard3's pipeline. Instruction counts are what this
  target gets, on both its cores, until a board is at hand.
- **What applies.** All three changes, exactly as on the C3 (same compiler, same strict-align rule, so the aligned
  check of the word loop). What Zb* adds, read from the disassembly of the spike kernels and the library objects
  built with and without the extensions:
  - SWAR 2 bpp merge: gcc uses `andn` for the three `x & ~y` terms, 3 instructions fewer of about 26 per word
    (about 10 %); nothing else changes. No intrinsic needed.
  - 1 bpp expansion: per bit `bext` + `neg` (2 instructions) instead of `sra` + `slli` + `srai` (3). The 2 KB table
    is 3-4 instructions per 8 pixels and still wins; with the table in, Zbs is not on the hot path.
  - Byte max (GRAY8 2 bpp, 8 bpp): `maxu` replaces a compare and branch, automatically, where the C is written as a
    value (`a > b ? a : b`), which `blit_gray8` is not today (it is a compare and conditional store). Writing the
    store unconditionally as `dst = max(dst, g)` would let gcc use `maxu`; that is the builder's choice during the
    rewrite, exact either way, and the M33 (`it cc / strbcc`) and x86 (`cmov`) are indifferent.
  - 8 x 8 bit transpose (`transpose8`, MONO_PAGE): gcc emits the same 74 instructions with and without Zbkb; it
    does not find `zip`/`unzip`/`brev8` on its own. A hand transpose with Zbkb `unzip` (perfect unshuffle, 3 rounds
    on two 32-bit halves) could cut it to roughly a third. That is an intrinsic/asm path for one ISA, not portable
    C: it belongs to the SIMD/asm follow-up, not this card, and the MONO_PAGE blit has no budget on the RP2350.
  - `orc.b`, `rev8`, `clz/ctz`, `cpop`: no use in these kernels (no byte-wise zero tests, no endianness swaps, no
    population counts).

### Decision: Cortex-A is out of scope **(design call)**

qemu-user aarch64/armv7 would add a second .deb (about 15 MB) and the NDK clang builds for instruction counts only;
there is no budget, no board, and the C changes are the same code the host runs. The host test suite is the proof
for the ISA-neutral parts (no endianness, no alignment assumption). The SIMD card needs qemu-user for NEON and should
add it then, together with a one-off byte-identity run of the golden test under `qemu-aarch64`.

### A scaled bench case **(design call)**

No bench case scales today (the DOS example draws 3/2 and `vesa-shots` checks it, but nothing times it). Add
`line40_scaled32` (the PAPLG line at 3/2 on GRAY8, P4 builds: host, DOS, WASM, M33, Hazard3) with its checksum from
`tools/svfline.py` through `sums.py`/`sums.inc.sh` as every other case; the MCU bench builds keep `SVF_NO_SCALE`.

## Exactness

Byte-identical, no deviation, proved by the gates that exist:

- `make -C c check`: the golden tests against `jamoset.py` and `svfline.py` (every face, all 11,172 syllables of
  every jamo face, lines, scaled lines, clips), the sanitizer build, the nm check for malloc.
- `c/cross/build-all.sh --ports`: 37 OK, `-Werror` on every toolchain.
- The bench checksums on every runner (`run-dos.sh`, `run-pico.sh`, `run-esp32.sh`, `run-avr.sh`, `run-wasm.sh`,
  `run-host.sh`, the new `run-m33.sh` and `run-hazard3.sh`): every row `ok`, `report.awk` fails a run otherwise.
- `vesa-shots` PNGs identical (the DOS example at 3/2 exercises the new box filter on the packed kinds).
- `run-screens.sh` (the port screens) unchanged.

Plus exhaustive kernel tests where they are cheap, as the spike did, in a new host test `c/tests/test_kernels.c` in
`make check` **(design call)**:

- 2 bpp merge: all 65,536 (dst, src) byte pairs through the byte form against a straight per-field reference kept in
  the test; the word form against the byte form on 2,000 random runs of random length, offset and alignment
  (0..3 on each pointer).
- 1 bpp OR word loop: the same random runs against a byte OR.
- 1 bpp table: all 256 source bytes against the bit loop, times 4 dst patterns, at every cut (`lo`, `hi` partial on
  either side, the middle whole).
- Box filter: the old implementation moved into the test as the reference; every reduced `num/den` with
  `den >= 2`, 1/2/8 bpp random cells of every width and height the format allows up to the largest repo cell, about
  800k output pixels as in the spike. (The Python reference stays the oracle for the library through the golden
  tests; this test is the cheap exhaustive sweep.)

The test runs on the host only. The cross targets are covered by the bench checksums, which draw whole lines with
every kernel on the real emulators.

## Budgets: what this card moves

| budget | now | after this card (expected) | remaining work, other card |
|---|---|---|---|
| DOS DX2-66 mapped line <= 16 ms | 15.19 ms, 1.05x margin | 13.05 ms (measured in the spike), 1.23x margin | - |
| DOS DX2-66 cold / nocache / stream_small | 29.4 / 24.9 / 28.8 ms | about 27.3 / 22.8 / 26.7 ms (spike raw): still over; the remainder is DOS reads | t_8a3815c4: syllable cache default, 32-bit path, mode 13h, read batching |
| DOS DX-33 mapped | 30.2 ms | about 26 ms by the preset ratio: still over | t_8a3815c4 |
| Pico `-Os` syl_bwelk <= 50 us | 62.0 us (7744 cycles; compose 3603) | the 1 bpp word OR trims `svf__merge`; a few per cent, not 1.24x | t_4108b260: the syllable cache (user, 2026-10-21: the 50 us budget applies with the cache on), PIO/DMA; plus the two cmap findings below |
| Pico `-Os` syl_ga <= 50 us | 50.7 us (1.01x over) | may cross under with the merge alone; to be measured | t_8b967a59 (the pack8 inlining) |
| M0+ P1/P2 <= 8192 B | 5674 | about 5810 | - |
| WASM 1 ms, Pico screen 2 ms, Uno fit | met | met, unchanged or better | - |

This card does not take on the remaining DOS or Pico work; it records in MEASUREMENTS.md "Still over budget" what is
left and hands the numbers to those cards.

### Found while reading the disassembly, left to the budget cards

Two cheap C items in `svf__glyph_index` (svf_face.c), which is 11.3 % of a Pico syllable and 19.2 % of a host 1 bpp
line, not in this card's three changes:

- `rd32` is four byte loads and shifts on every ISA, out of line on M0+ and RV32 (`rd32.isra.0`, called per probe of
  the binary search). On x86 and WASM it could be one unaligned load; on the others one aligned `ldr` when the cmap is
  4-aligned (`cmap_off` is a header field; the check is once at open). Candidate for t_4108b260 and t_8a3815c4.
- `mid = lo + (hi - lo) / 2` with `uint16_t` operands is a signed division after promotion: gcc 16 at `-Os` on the
  ESP32-C3 emits a real `div` per probe (32+ cycles on a C3 divider); M0+ gets three instructions. `(lo + hi) >> 1`
  in `unsigned` is one shift. Trivial; the builder may fold it into this card's merge commit if the reviewer agrees
  **(design call: allowed, not required)**.

## Hand-written assembly: where it could pay, what it costs, and the order

The user asked (2026-10-21) whether replacing parts of the C with assembly is also on the table. It is, under three
rules that do not bend: byte-identical output proved per target under its emulator by the gates above; a C fallback
that always exists and is the reference; a build switch per ISA (`SVF_ASM_<ISA>`, default 0 until a measurement
earns 1) that selects the asm. What follows is from the disassembly of the hot loops of the current builds
(`c/build/bench/pico`, `pico-prof`, `esp32`, `avr`; DJGPP and M33 objects rebuilt from `c/src` with the SIZES.md
flags; the blit functions read in the `PROFILE=1` builds, where they are not inlined into `svf_draw_utf8`).

### x86 DOS 486, DJGPP gcc 12.2 `-O2 -march=i486`

- `svf__merge` 2 bpp: the inner field loop is 14 instructions with two `sar %cl` (shift by CL, 3 clocks on a 486),
  a `cmp/jae` per field, and the partial result kept in a stack byte (`or %dl,-0xd(%ebp)`); four registers are
  spilled around the loop. About 70 instructions a byte. The C SWAR makes this 10-11 instructions per 4 bytes (spike,
  QEMU icount); asm could shave the register shuffling but not the arithmetic: nothing left worth an `.S` file.
- `blit_gray8` 1 bpp: per pixel a variable `sar %cl`, `and $1`, `je`, `movb $0xff`: 8 instructions a pixel. The 2 KB
  table makes it 3-4 instructions per 8 pixels; asm adds nothing.
- `blit_gray8` 2 bpp (the DOS line case, 46-49 % of the line): per pixel a variable shift, `and $3`, a multiply by 85
  (gcc uses `lea`/`imul`), a compare and a conditional store. Asm could use `shr` with carry tests and a register
  4-entry table, maybe 1.3x on this loop: about 1.1-1.15x on the line (Amdahl: the blit is half the line). The
  MMX path of the SIMD card does the same loop at 1.94x on the Pentium class; the 486 has no MMX.
- `svf__glyph_index`: `rd32` is 16 instructions of byte loads where x86 takes one `mov`: the C item above.
- Against the 16 ms budget: the DX2-66 mapped line is met by the C card (1.23x margin); the cold, nocache and small
  rows are over because of 42-65 DOS reads, which no instruction can fix; the DX-33 mapped row at about 26 ms needs
  1.63x on the whole line, and asm on the 2 bpp blit buys at most 1.15x of it. Asm does not close DX-33; the cache
  (19.8 -> about 16 ms on DX-33 mapped+cache by the ratio) and mode 13h are t_8a3815c4's levers.

### Cortex-M0+ Thumb-1 (Pico), gcc 15.2 `-Os`

- `svf__merge` 2 bpp: the compiler ran out of low registers: the field loop keeps `v`, `a`, `b` and the partial
  result on the stack (`str/ldr [sp,#..]` eight times a field), about 22 instructions a field, 90 a byte. The C SWAR
  needs no inner loop and about 14 registers' worth of temporaries that fit in r0-r7 when written as a straight
  line: 8-10 instructions per 4 bytes plus the byte-assembly of the loads. Asm would save the `uxth` and perhaps two
  instructions a word: under 10 % of a kernel that will be a few per cent of a syllable.
- `svf__merge` 1 bpp: 8 instructions a byte (`ldrb, ldrb, orrs, strb, adds, uxth, cmp, bhi`). The word loop gets
  about 4 a byte with unaligned bytes assembled, about 2 with aligned `ldr`. A Thumb-1 asm loop with `ldmia`/`stmia`
  on aligned data would be about 1.2 a byte: a further 1.6x on a kernel that is 12 % of a syllable, so about 4 % of
  `syl_bwelk`.
- `blit_mono_page` (profile build): a 108-byte frame and 40-odd stack loads and stores per 8 x 8 block around the
  gather loop, then `transpose8` (which gcc compiles well: 70 instructions, multiply tricks, no spills). The gather
  loop is 9 instructions a row at 1 bpp. In the plain build the helpers inline and some pressure goes; the spills
  remain the compiler's weak point here. A hand-written page blit keeping the eight row pointers' stride in a
  register and gathering with `ldrb` + `strb` into an 8-byte stack block could save perhaps 20-30 % of the blit,
  which is about 30 % of a syllable: 6-9 % of `syl_bwelk`.
- `svf__glyph_index`: a call to `rd32.isra.0` (14 instructions + call/return) per probe; the C fix above (aligned
  `ldr` after a check at open) takes it to 2-3 and needs no asm.
- Against 50 us: `syl_bwelk` is 7744 cycles, needs 6250. The C items (word OR about 550 cycles, aligned cmap reads
  about 600, the `mid` shift a few tens) take it near 6600; the page-blit asm could take 200-500 more; the syllable
  cache removes compose entirely on a hit. **The user ruled (2026-10-21) that the 50 us budget applies with the
  syllable cache on**, so the budget is met by the cache in t_4108b260 and no M0+ assembly is written. The
  page-blit figure above stays on record as what asm would have bought.

### Cortex-M33 Thumb-2, gcc 15.2 `-Os`

- The compiler is good here: `svf__merge` 2 bpp is 10 instructions a field with `it cc / movcc`, no spills;
  `blit_gray8` uses `it` blocks, `mla`, shifted operands. The C SWAR still wins 7.6x on the kernel (54 -> 7
  instructions a byte, spike) because it removes the loop, not because of codegen.
- What asm would add on the M33 is the DSP subset (`usub8/sel` byte max, `smlad`), which the ACLE intrinsics give
  from C: that is the SIMD32 lane of the SIMD card (1.67x on GRAY8 set B), not hand asm. No budget, no board.

### RISC-V RV32IMC (ESP32-C3), gcc 16.1 `-Os`

- `svf__merge` 2 bpp: 9 instructions a field, a taken branch for the max (RV32I has no conditional move or min/max
  without Zbb, which the C3 lacks), plus `slli; srli` per byte for the `uint16_t` counter. About 40 a byte; the SWAR
  is about 12 per 4 bytes. There is nothing the compiler misses that asm would find: RV32IMC has exactly the and/or/
  xor/shift the formula needs, and no bit-manipulation extension to exploit.
- `svf__glyph_index`: seven callee-saved registers pushed and popped on every call (48-byte frame) and the `div`
  above: both are C fixes (a leaf shape and an unsigned shift).
- `transpose8`: 60 straight-line instructions with `mul` tricks; fine.
- No budget; instruction counts only. Asm buys nothing measurable here.

### Hazard3 RV32IMAC + Zba/Zbb/Zbs/Zbkb (RP2350 RISC-V), gcc 16.1 `-Os`

- Same compiler and same loops as the C3, so the same reading: the losses are in the field loop and the `uint16_t`
  counters, both deleted by the C rewrite; `svf__glyph_index`'s `div` and 7-register prologue are C fixes.
- Zb* is used by gcc without help: `andn` in the SWAR, `maxu` for a value-form byte max, `bext` for bit tests,
  3-4 % smaller objects. The one place a hand path would beat gcc is `transpose8` with Zbkb `unzip` (gcc never emits
  it): about a third of 74 instructions, in a blit with no budget on this chip. It is an ISA-specific intrinsic path
  for the follow-up card, under a switch, with the C transpose as reference and its exhaustive 8 x 8 sweep run on
  the `virt` runner.
- Zcmp (`cm.push`/`cm.pop`) shrinks prologues but needs the Zcmp-capable binutils; speed-neutral. Not a reason for
  asm.

### Xtensa LX7 (ESP32-S3), gcc 16.1 `-Os`

- The compiler already uses the ISA's strengths: `loop` (zero-overhead) around the field loop, `maxu` for the max,
  `min`/`max` for the clip bounds in `blit_gray8`, `bbc` (branch on bit clear) for the 1 bpp test. The cost left in
  the merge is the variable shifts (`ssr; sra` twice and `ssl; sll` per field: the shift amount lives in SAR and must
  be reloaded), about 12 instructions a field. The SWAR removes the shifts; asm would not improve on what gcc emits
  for the SWAR.
- The S3's PIE (128-bit) instructions are asm-only (no intrinsics) with 16-byte alignment constraints: the SIMD card
  deferred them, and nothing here changes that.

### AVR (ATmega328P), avr-gcc 16.1 `-Os`

- `svf__merge` 2 bpp is the worst code of the set: each field shifts a 16-bit promoted value in a counted loop
  (`asr r31; ror r30; dec r0; brpl`, 7 iterations for a shift by 6), three such loops a field, about 300 cycles a
  byte. The byte SWAR in 8-bit `uint8_t` arithmetic is about 15 instructions a byte: a 20x kernel. No bench case
  shows it (set A is 1 bpp), so the gain is on record as code only.
- `svf__merge` 1 bpp: `ld X+; or; st -Y; adiw` 5 instructions a byte; nothing to gain.
- Asm on the AVR would be for the page blit, where the Uno has no speed budget (the fit is the requirement) and 954 B
  of flash; not worth a variant.

### Cost of an asm variant, per ISA

- A `.S` file (or an `asm` block) per ISA per kernel, each with the ABI, the clip cuts and the tail handling redone
  by hand; the C stays the reference and must keep passing alone (`SVF_ASM_*=0`).
- Testing: the exhaustive kernel tests run on the host, where Thumb-1, RV32, Xtensa and AVR asm cannot run. Each asm
  kernel therefore needs its test on the emulator: a bench-style harness per ISA (the spike's `m33.c`/`mdrv.c` shape)
  running the 65,536-pair merge sweep and the row sweeps under rp2040js, QEMU, simavr or DOSBox-X, plus the existing
  line checksums. That is the real cost: a runner per variant, in the gate.
- Review: assembly is read by fewer reviewers; the dual-review lanes must cover each ISA.
- Maintenance: every change to a kernel's contract (a new target kind, a clip rule) is made twice or more.

### Recommended order **(design call)**

1. **This card: portable C first, on every target.** The disassembly shows the compilers losing the most exactly in
   the loops the C rewrite deletes: the 2 bpp field loop (spills on M0+ and DOS, 16-bit shift loops on AVR, variable
   shifts on Xtensa, branches on RV32) and the per-pixel 1 bpp GRAY8 bit test. After the rewrite those loops no
   longer exist, so the compiler has nothing left to get wrong there.
2. **The two cmap items** (aligned `rd32`, unsigned `mid`) in the budget cards, or folded into this one if review
   agrees: they are C, exact, and worth more on the Pico than any asm merge.
3. **Re-disassemble after 1 and 2, then asm only inside the budget cards, only where the disassembly plus a
   measurement show the compiler leaving at least 15-20 % of that kernel's cycles on the table, and only if the
   budget is still missed after the card's C levers (syllable cache, mode 13h).** From today's reading the one
   candidate that met the bar was `blit_mono_page` on the M0+ (stack traffic around the gather; 6-9 % of a syllable
   at stake), and the user's ruling that the Pico budget applies with the syllable cache takes it off the table. The
   DOS 2 bpp GRAY8 blit is marginal (about 1.1x on the line, and the Pentium class gets MMX from the SIMD card
   instead). Nothing on the M33, C3, Hazard3, S3 or AVR meets the bar; the Hazard3 `unzip` transpose is an
   intrinsic candidate for the follow-up, not a budget item.
4. **SIMD card** (t_aa395fa1) after this one, with the revised criterion the feasibility study proposed; it is where
   the x86 MMX/SSE2, M33 SIMD32, NEON and simd128 work goes, and the M33 and (later) Cortex-A runners serve it.

The evidence supports the expected order; no change to it.

## Done criteria

The card's close criterion: byte-identical output on every gate (`make -C c check`, `build-all --ports` 37 OK,
`run-dos`/`run-pico`/`run-esp32`/`run-avr`/`run-wasm` checksums ok, `vesa-shots` PNGs identical); MEASUREMENTS.md
before/after rows per target (emulated where emulated); M0+ P1/P2 <= 8192 B; reviewed (Opus + external lanes). This
design adds, as the measurable form of "per target":

- `run-m33.sh` exists, is pinned and verified like the others, and MEASUREMENTS.md has its rows (instruction counts).
- `run-hazard3.sh` exists (pinned ESP compiler and QEMU, `virt` with the Zb* properties on, `rdinstret`), every
  row `ok`, and MEASUREMENTS.md has its rows labelled as instruction counts.
- `test_kernels` is in `make -C c check` and passes.
- `line40_scaled32` has rows on host, DOS, WASM, M33 and Hazard3 with the `svfline.py` checksum.
- MEASUREMENTS.md "Still over budget" lists what remains for t_8a3815c4 and t_4108b260 with the new numbers, and
  SIZES.md is re-measured, with a `hazard3-riscv32` toolchain row (no budget) beside the M33's.
- The two switches are documented in `svf.h` next to `SVF_WORD_STORE`, with their AVR defaults.

## Left to the builder

- The exact macro that generates the 2 KB table, and whether the accumulator of the box filter lives in the scratch
  or on a bounded stack (either is acceptable if the review can see the bound).
- How often the aligned word path fires on the M0+ and Hazard3 bench faces (`run-pico.sh insns`, `run-hazard3.sh`);
  if rarely on a target that matters, the explicit byte-assembled variant, and a note on the faces' alignment.
- The `BENCH_M33` section of `bench.c`, the SysTick calibration check (the spike's 1 tick = 50 instructions), and
  the .deb pin; the `BENCH_HAZARD3` section (entry, 16550 output, test finisher exit, `rdinstret`), which can share
  the C3's `rdinstret` code and the mcu-ports design's verified `virt` entry.
- Whether `blit_gray8`'s byte max is written in value form so that Zbb `maxu` (and M33 `it`/x86 `cmov`) apply;
  exact either way.
- Whether to fold the `mid` shift into this card (allowed) and to leave the aligned `rd32` to t_4108b260 (preferred:
  it touches `svf_face.c` and the open path).
- The plan (`docs/superpowers/plans/`), one task per kernel with its test first, the M33 runner last.

## Decisions taken by the user (2026-10-21) and what is left open

- The Cortex-M33 runner stays in this card.
- The Pico 50 us budget applies with the syllable cache on: no M0+ assembly.
- RP2350 RISC-V (Hazard3) is a target of this card: pinned ESP gcc with the pico-sdk's `-march`, QEMU `virt` with
  the Zb* properties, instruction counts, no new downloads; the 8 KB budget does not apply to RP2350 builds
  (controller call, above).

No question is left that only the user can answer. One the builder may raise in review: whether the Raspberry Pi
`riscv32-pico-elf` toolchain should be pinned later for Zcmp and `-mcpu=hazard3-rp2350`; this design says no.
