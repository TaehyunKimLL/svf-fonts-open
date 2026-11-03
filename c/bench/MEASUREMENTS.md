# Emulated speed measurements

Re-measured 2026-10-23 after the C speedups 6-10 on SVF v3 (library at 8bff82e: the `svf__merge` word path, the 64 B GRAY8 nibble table, the separable box filter, the cmap midpoint shift): the result tables below are the rows of that run (`c/build/bench/after/`; profile named in each section), the section "Before -> after the C speedups" has the v3 rows (4539e42) beside them, and the ESP32-S3 section there adds a run on real silicon. The paragraph after this one (2026-10-23, b45e9dc) and the section "Before -> after SVF v3" are the earlier v3 state.

Re-measured 2026-10-23 on SVF v3 (library and bench at b45e9dc): the result tables below are the v3 rows (profile named in each section), the section "Before -> after SVF v3" has v2, v3 x-boxed and v3 y-cropped side by side, and the prose of "Findings" and below still quotes the pre-v3 2026-10-21 run unless it says v3. The text below this paragraph is the 2026-10-20/21 description of the method.

Measured 2026-10-20 and 2026-10-21 (library as of commit a293e6e, after the blit fast paths of t_b5256c18; the Pico,
ESP32-C3 and ESP32-S3 sections and the "Screens" section were measured on 2026-10-21 on branch mcu-ports, the Uno and WASM
sections on 2026-10-20 (the Uno re-run on 2026-10-21 unchanged), the DOS sections on 2026-10-21 (below); the "before" numbers in "Against the budgets" are the 2026-10-19 run on branch c-renderer,
library 91fa206) with `c/bench/run-pico.sh`, `run-avr.sh`, `run-dos.sh`, `run-wasm.sh` and `run-esp32.sh`, and
`c/ports/check/run-screens.sh`. The DOS tables and the "Packed kinds (VESA)" section are the 2026-10-21 run of
branch vesa-out, library and bench as of commit 377b286 (the VESA packed kinds, the word stores, `run-dos.sh` with its
`_bytes` build), except the `line40_scaled32` rows, which were added at commit 4baf109 on branch c-speedups (bench.c
only; the library is unchanged) and measured once. The RGB565 rows of the Pico, ESP32-C3 and ESP32-S3 tables, three ESP32-S3 GRAY8 `-Os` rows, the ratio
tables, the `blit_rgb565` share and the "Screens" cycles were re-measured on 2026-10-21 on the merge of vesa-out with main
(post-VESA: the RGB565 blit is VESA's `blit_rgb16`, shared with RGB555; every checksum unchanged; the MONO_PAGE and GRAY8
Pico rows did not move). Emulators installed by `c/bench/install-emulators.sh`, compilers by
`c/cross/install-toolchains.sh` (versions and flags in `c/cross/SIZES.md`). Every number below is **emulated**: none
comes from real hardware, and the ESP32 numbers are not even cycles (instruction counts, below). Re-run the five scripts
and replace the tables to update. The bench is not part of `make -C c check` (the emulators are host tools).

## What is measured

`c/bench/bench.c` (one file, a section a platform) times each case over N iterations and reports the time per
iteration and an FNV-1a checksum of the target buffer. Each checksum equals the one computed from `tools/svfline.py`
(lines, converted to the target kind; `c/bench/sums.py`, embedded in `c/bench/sums.inc.sh`, which `TestBenchSums` keeps
equal to `sums.py` and to the host build of `bench.c`) or `tools/jamoset.py` (`compose_bwelk`), so every platform drew the
reference pixels; `c/bench/report.awk` fails a run whose checksum differs, whose case set is not the expected one, or
(Pico) whose instruction count is missing.

> **Public-release note (2026-11-03).** Every Set A number in this file was measured with the face HGKEY6J (a
> 16 px 6x2x1 jamo set of the iolo collection), which this repository does not publish. The benches now default to
> `svf/dos/NEODG16G.SVF` (Neo Dunggeunmo, 6x2x1, 10,124 bytes in `mcu-strict`) and `screen32` places its lines at the
> face's ascent; `sums.inc.sh` holds the checksums of the new face. The cycle tables below were **not** re-measured with it.

- **Set A** (Pico, Uno, ESP32-C3, ESP32-S3, Cortex-M33, RP2350 under rp2350js: one 16 px 1 bpp jamo face, `svf/iolo/HGKEY6J.SVF`, 8,716 bytes in the `mcu-strict` profile (12,921 bytes in the pre-v3 format of the rows below), embedded by
  `c/bench/mkface.py --profile mcu-strict`: in flash on the Pico, PROGMEM on the Uno; mapped; a 128 x 64 target; library built with
  `-DSVF_NO_SCALE`, no syllable cache):
  - `syl_ga`, `syl_bwelk`: `svf_draw_utf8` of 가 (2 pieces) and 뷁 (3 pieces): decode, chain lookup, metrics,
    compose, blit. The "composed and drawn 16 px syllable" of the budget.
  - `compose_bwelk`: `svf_compose` of 뷁 alone.
  - `screen32`: clear the target buffer and draw 4 lines of 8 syllables (32 glyphs, all composed): the
    "128 x 64 screen". Hangul only, the slowest kind of glyph.
  - `line8` (not on the Uno): the first of those lines, 8 syllables, drawn alone.
- **Set B** (Pico, ESP32-C3, ESP32-S3, Cortex-M33, RP2350 under rp2350js; GRAY8 and RGB565 builds only): `svf/dos/PAPLG16.SVF` + `PAPLG18.SVF` (2 bpp,
  `PAPLG18` a jamo face), a 240 x 24 band, foreground 0xFFE0 on background 0x0010:
  - `aa_syl_ga`, `aa_syl_bwelk`: the same two syllables as 2 bpp antialiased glyphs.
  - `aa_line12`: a 12 code point line (`다람쥐 헌 쳇바퀴에 타`).
  - `aa_screen10`: ten bands, each cleared and a line drawn; only the clear and the draw are timed (50 intervals over 5
    iterations), the bands' checksums are chained but not timed.
- **Kinds and buffers.** One build per target kind, with that kind alone compiled in (`-DSVF_TARGETS=<bit>`): MONO_PAGE
  (`0x02`, the SSD1306 page layout, 1 KB for the 128 x 64 screen), GRAY8 (`0x01`, 8 KB), RGB565 (`0x08`, 16 KB; the
  band is 240 x 24 x 2 bytes). The Uno build keeps every kind (`run-avr.sh` passes no `-DSVF_TARGETS`), MONO_PAGE only
  in its 1 KB buffer. The MONO_PAGE rows are the ones the budgets apply to; the GRAY8 and RGB565 rows have **no budget**
  (user ruling, 2026-10-20: the colour and grey ports run on small panels).
- **Pico builds**: six (3 kinds x `-Os`, `-O2`), 46 rows; gcc 15.2.1, `-mcpu=cortex-m0plus -mthumb`. `pico-run.mjs` also counts the instructions a case executes (`insns`).
- **ESP32 builds** (`c/bench/run-esp32.sh`): twelve, chip (ESP32-C3 riscv32 `rv32imc_zicsr_zifencei`, ESP32-S3 Xtensa
  LX7) x kind x `-Os`/`-O2`, gcc 16.1.0 (crosstool-NG esp-16.1.0_20260609), bare-metal on QEMU's `-kernel` path, no ESP-IDF;
  iterations are the Pico's (100 / 20 / 5; a whole run takes about 10 s); 92 rows, every checksum `ok`.
- **DOS and WASM** (`svf/dos/PAPLG16.SVF` then `PAPLG18.SVF`, 2 bpp, the second a jamo face; P4 profile; one line of
  40 code points, `Score: 120 점, 다람쥐 헌 쳇바퀴에 타고파! 뷁쌓읽 가나다 OK` (18 syllables), on `SVF_T_GRAY8`
  640 x 24):
  - `line40_mapped`: both faces held whole in memory (DOS: read from the files into memory first, not timed).
  - `line40_mapped_cache`: the same with a 64-slot composed-syllable cache (`svf_chain_cache`).
  - `line40_stream_cold`: both faces streamed (DOS: `fseek` + `fread` on the .SVF files; WASM: a callback copying from
    the embedded arrays), 1 KB block caches that hold the line's blocks (16 slots PAPLG16, 64 slots PAPLG18, 82 KB),
    the first draw after opening (42 reads).
  - `line40_stream_warm`: the same, further draws (0 reads a draw).
  - `line40_stream_small`: caches smaller than the line's working set (4 and 16 slots, 21 KB): 43 reads a draw.
  - `line40_stream_nocache`: no block cache: every glyph and piece read when drawn (65 reads a draw).
  - `line40_scaled32`: the same line at 3/2 (`scale_num 3`, `scale_den 2`) on `SVF_T_GRAY8` 960 x 36, baseline 28, mapped, no
    syllable cache; no budget (the 16 ms budget is the 1/1 line). Also on the host (`run-host.sh`), not on the packed kinds.
- **DOS and the host, packed kinds** (the VESA modes; mapped faces; the same 40 code point line drawn with
  `index_base 16`, `index_levels 3`, `fg565 0xFFFF`, `fg888 0xFFFFFF`, background 0 on a buffer cleared to 0; the
  checksum covers `rows * stride`): `line40_<kind>` (PAPLG16 + PAPLG18, 640 x 24, baseline 19) for `indexed8`,
  `rgb555`, `rgb565`, `xrgb8888`, `rgb888`; `line40_24_<kind>` (MARUS24A, 2 bpp, 640 x 32, baseline 25) the same five;
  `line40_24m_<kind>` (MARUS24, 1 bpp, 640 x 32) for `indexed8`, `rgb565`, `xrgb8888`. `run-dos.sh` builds the program
  twice, `BENCH.EXE` (the library as `svf.h` defaults it: word stores on x86) and `BENCHB.EXE`
  (`-DSVF_WORD_STORE=0 -DBENCH_CASE_SUFFIX='"_bytes"'`, library too: the byte loops, every case name ending in
  `_bytes`), and runs both at both presets. The checksums come from the host build (`c/bench/run-host.sh`: the four
  faces embedded by `mkface.py`) and were cross-checked against `tools/svfline.py` `draw_target` on the same kind with
  the same options (fill 0): all 13 packed sums agree; both builds draw the same pixels.

## How time is measured

| platform | emulator | time base | accuracy |
|---|---|---|---|
| Pico (RP2040, Cortex-M0+, 125 MHz) | rp2040js 1.4.0 on node v24.13.0, driven by `c/bench/pico-run.mjs` (ELF loaded into flash/SRAM, no boot ROM) | rp2040js's cycle counter (`core.cycles`, the Cortex-M0+ instruction timings) between BKPT markers; µs = cycles / 125 | cycle-counted core; every memory access costs the same, so XIP flash cache misses (real Pico: code + face = 19.1 KB of flash, more than the 16 KB XIP cache) and wait states are **not** modelled: real hardware is this fast or slower. Division is libgcc's software routine (pico-sdk would use the SIO divider; division is 1-2 % of a drawn syllable). |
| Uno (ATmega328P, 16 MHz) | simavr 1.8 through `c/bench/avr-run.c` (linked with libsimavr) | simavr's cycle counter (`avr->cycle`, AVR instruction timings) between writes to GPIOR0; µs = cycles / 16 | cycle-counted; PROGMEM reads (`LPM`) are timed as on the chip |
| DOS (486) | DOSBox-X 2026.08.31, `core=normal`, `cputype=486`, `cycles=fixed 23880` (its "486DX2 66MHz" preset) and `fixed 12010` ("486DX 33MHz"), headless under xvfb-run | the program's `uclock()` (DJGPP: the emulated 8254 PIT at 1.19 MHz), which runs on emulated time | **approximate**: DOSBox-X runs a fixed number of instructions per emulated millisecond, whatever they are; a real 486 spends 1 to 40+ clocks an instruction, so this is DOSBox-X's calibration of a 486, not a 486. The two presets give times in the ratio of their cycle settings (30.23 / 15.18 ms = 1.99 for the mapped line, 2026-10-20; 23880 / 12010 = 1.99), and repeated runs give the same µs to 0.01 µs for the mapped cases and within 0.02 % for the streamed ones (the 2026-10-21 runs of this tree: five runs of the DOS bench, every row identical; an independent run of the same commit by the reviewer differed by up to 0.03 µs on the mapped rows and 0.033 % on the streamed ones, so that is the spread to expect): the time base is emulated, not the host's. |
| ESP32-C3 | Espressif QEMU 9.2.2 (`esp_develop_9.2.2_20260417`), `qemu-system-riscv32 -M esp32c3 -icount shift=0,sleep=off`, `-semihosting`, driven by `c/bench/run-esp32.sh` | `rdinstret` (the RISC-V retired-instruction counter) before and after each case; the 'cycles' column holds **instruction counts** | **not cycles**: QEMU is a translator with no pipeline, memory or cache timing. The count is the instructions the guest executed; a real C3 spends at least one cycle on each, so instructions / 160 MHz is a **lower bound** of the time on a C3. The machine has one core. |
| ESP32-S3 | the same QEMU, `qemu-system-xtensa -M esp32s3 -icount shift=5,sleep=off`, `-semihosting`, `run-esp32.sh` | the Xtensa `ICOUNT` register of **core 0** (instructions that core completed; not `CCOUNT`, which includes the unparkable core 1); the 'cycles' column holds **instruction counts** | **not cycles**: QEMU's Xtensa models no instruction timing. The count is an instruction count (checked on 1,000,000-instruction loops by `c/bench/check-esp32-cal.sh` on every run, and against a core-0 execution trace once, below); instructions / 240 MHz is a **lower bound** of the time on an S3, the same kind of bound as the C3's, and says nothing about a real S3's cycles. |
| Cortex-M33 (RP2350 ARM core, 150 MHz) | Ubuntu's QEMU 8.2.2 (`qemu-system-arm 1:8.2.2+ds-0ubuntu1.18`), `-M mps2-an505 -icount shift=0,sleep=off`, semihosting on a stdio chardev, driven by `c/bench/run-m33.sh` | SysTick (24-bit down counter, wraps counted by its interrupt; a read of the counter at 0, the one tick between the wrap's interrupt and the reload, is taken again) before and after each case, ticks x 50 = guest instructions (under `-icount shift=0` one tick of the 20 MHz processor clock is exactly 50 instructions; `cal=loop2m` checks it, through the same `bench_now()` the rows use, on a 2,000,000-instruction loop); the 'cycles' column holds instructions and the µs column divides them by 150 MHz | instruction-counted with a granularity of 50 instructions per interval; no pipeline, memory or bus timing, so not RP2350 cycles; the µs figures are an estimate at one instruction per cycle, not a bound |
| RP2350 (Hazard3 and Cortex-M33, 150 MHz) | rp2350js af0114c + `c/bench/rp2350js.patch` on node v24.13.0, pico-sdk 2.3.1 `pico2` images booted through the bundled A2 boot ROM, driven by `c/bench/rp2350-run.mjs` (`c/bench/run-rp2350.sh`) | rp2350js's cycle counter (`core.cycles` of core 0) between the PCs of the marker functions `bench.c` calls; µs = cycles / 150 (the SDK's `clk_sys`; rp2350js runs 125 MHz) | **rp2350js cycles, not RP2350 cycles**: no XIP flash or cache timing, no bus contention or QMI, no Hazard3 load-use penalty, no timer or system interrupts or exceptions (a fault entry ends the run); each build is calibrated (`cal=empty` 7-8 / 11-12 cycles, `cal=loop1m` within 16 cycles of 2,000,000 Hazard3 / 3,000,000 M33, 2,000,000 instructions) and two runs are byte-identical |
| WASM | none: node v24.13.0 (V8 13.6.233.17) runs the module on the host CPU (AMD Ryzen AI MAX+ PRO 395) | `emscripten_get_now()` (`performance.now`) | host-dependent; the first case includes V8's tier-up. Labelled with the host CPU instead of "emulated". |

Emulator provenance (`c/bench/install-emulators.sh`, verified before use, installed under `~/opt`, no sudo):

| emulator | source | hash |
|---|---|---|
| simavr 1.8 | https://github.com/buserror/simavr/archive/refs/tags/v1.8.tar.gz (source; built with host gcc 13.3.0 and libelf 0.190) | sha256 `51e2682d23fb4843191ee81dadcb5488fa6194553a108bbd6e60e8b1260269d6` (computed: the project publishes no checksum; two downloads agreed) |
| rp2040js 1.4.0 | https://registry.npmjs.org/rp2040js/-/rp2040js-1.4.0.tgz (no dependencies) | sha512 integrity `knEMw0SRP9JPVLvhhYB3rjP4gLQhcWs9UOXKvxFU9Rn5eWvmlPzObMhEjfeLZ6H8FGepd6ZtMAYzGEtCaB9qYg==` (the registry's) |
| DOSBox-X 2026.08.31 | `/usr/bin/dosbox-x`, already on this host (not installed by the script); DJGPP's DPMI host is its built-in CWSDPMI | - |
| node v24.13.0 | `~/opt/node-v24.13.0-linux-x64`, already on this host | - |

Provenance of the ESP32 and Pico bench tools (`c/bench/install-emulators.sh` and `c/cross/install-toolchains.sh`, verified
by `--verify` before every use of `run-esp32.sh`, `run-pico.sh` and `run-screens.sh`; installed under `~/opt`, no sudo):

| tool | source | hash |
|---|---|---|
| QEMU 9.2.2 riscv32 (`esp_develop_9.2.2_20260417`) | https://github.com/espressif/qemu/releases/download/esp-develop-9.2.2-20260417/qemu-riscv32-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz (16,842,920 bytes) | sha256 `547f03e04701a92cbb699f7f7d015adc1f5b5ef93cbb94c0dd9b7107e2d84e77` (the release's `qemu-esp_develop_9.2.2_20260417-checksum.sha256`) |
| QEMU 9.2.2 xtensa | https://github.com/espressif/qemu/releases/download/esp-develop-9.2.2-20260417/qemu-xtensa-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz (15,619,396 bytes) | sha256 `0eecb2a34a5586c0e59110f77b9343b7b336e82fdb0e1a30e1dc1bab8a547e35` (the same asset) |
| Xtensa toolchain (xtensa-esp-elf 16.1.0) | https://github.com/espressif/crosstool-NG/releases/download/esp-16.1.0_20260609/xtensa-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz (89,005,792 bytes) | sha256 `f708752ebb35cab21f184b2574114ed1187619db0edb8a4ba913c06ca2fa675e` (asset `crosstool-NG-esp-16.1.0_20260609-checksum.sha256`) |
| RISC-V toolchain (riscv32-esp-elf 16.1.0) | https://github.com/espressif/crosstool-NG/releases/download/esp-16.1.0_20260609/riscv32-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz | sha256 `0b029ab31ebc7f74e2c4779077251b21a22cd620669dc4c82e7adc478d403a8d` (the same asset) |
| rp2350js 2.0.1 (commit af0114c, `c1570/rp2350js`, MIT) | https://github.com/c1570/rp2350js/archive/af0114cbee8e9e91574204b66f10aa2961cbf28c.tar.gz (source, 1,246,966 bytes; no npm release at that commit); `npm ci --ignore-scripts` from its `package-lock.json` (430 packages, each checked against its sha512 integrity; TypeScript 5.9.3, uf2 2.0.0), `tsc` to CommonJS, with `c/bench/rp2350js.patch` applied (four fixes: the Cortex-M33 GPIO coprocessor MCR/MRC/MCRR decode, Zcmp `cm.mvsa01`/`cm.mva01s`, Zbb `orc.b` and `zip`/`unzip`, `sltiu`'s immediate; diff sha256 `61596cb94ca344b24dd1ae6ee118449f35c776cd7f70481a03ffbb75a61b7056`); installed as `~/opt/rp2350js-af0114c/`, manifest pin `MANIFEST_PIN_rp2350js` in `install-emulators.sh`; the A2 boot ROM is `src/bootroms/bootrom-rp2350-a2.ts` of that source | archive sha256 `2bcf172e083c53671df4a5787a793bca5aa5ee5451098a84f017852eb227bcf2` (computed: GitHub publishes no checksum for a generated archive; two downloads agreed); `package-lock.json` sha256 `dd88d3100bd97acdcaa3daa3c2c931590938cd5a42d72e2daf7978d684f24e05` |
| RISC-V toolchain (riscv32-pico-elf-gcc 16.1.0, Raspberry Pi) | https://github.com/raspberrypi/pico-sdk-tools/releases/download/v2.3.1-0/riscv-toolchain-16-x86_64-lin.tar.gz (129,680,495 bytes; no top directory in the tarball), installed as `~/opt/pico-riscv-toolchain-16-v2.3.1-0/`, manifest pin `MANIFEST_PIN_pico_rv` in `install-toolchains.sh` | sha256 `fc36f1b37f99de54a358115443638023de34e15fe199e718e50cca4d212e7e9f` (the digest GitHub lists for the release asset) |
| QEMU 8.2.2 qemu-system-arm (Ubuntu `1:8.2.2+ds-0ubuntu1.18`) | https://archive.ubuntu.com/ubuntu/pool/main/q/qemu/qemu-system-arm_8.2.2%2bds-0ubuntu1.18_amd64.deb (10,963,018 bytes; the pool drops superseded versions, so the copy in `~/opt/dl/qemu-arm/` is the durable source); unpacked with `dpkg-deb -x` (no root) into `~/opt/qemu-system-arm-8.2.2-0ubuntu1.18/`, binary `usr/bin/qemu-system-arm`; runs with the host's shared libraries (nothing missing by `ldd`) and needs no data files for `-M mps2-an505` | sha256 `06184a21b9c8dc573ab6d255e9826cc4732df90e56bd65c52e92ad640af4d60a`; tree manifest pin `9a25a1c005a52039b4b0f4689910860affdb02d4e06949a503bc79caaa42377c` |
| pico-sdk 2.3.1 | https://github.com/raspberrypi/pico-sdk.git tag `2.3.1`, commit `079c6f39023649b154152db30f1d781e884879bc` (hard-coded; the script stops unless the clone's HEAD is this commit); no submodules | git commit |
| RP2040 B1 boot ROM (for rp2040js) | https://raw.githubusercontent.com/wokwi/rp2040js/v1.4.0/demo/bootrom.ts (tag v1.4.0 = commit `0c1c316e87b34e616985af35d4c147fc19cfeee9`) converted to `~/opt/rp2040js-1.4.0/bootrom-b1.bin` (16,384 bytes) | `bootrom.ts` sha256 `99f8a1f813ce3aa9415884de3fb6c5b962d3c6fa0394b05413ad3c7b3c39ec62` (measured twice; the file is not a release asset); `.bin` sha256 `90b31e108faedfa6bbcfcc33ba05dac61e645108cfbbdc385f8dafc71fde44ae` |

QEMU has no RP2040 machine (`qemu-system-arm` models the RP2350's Arm core only as the generic Cortex-M33 board mps2-an505 below); rp2040js models the RP2040 itself, so it is used for the Pico.

## Results

**Re-taken 2026-10-27 (Group B review round 1, library at 1cbe1f2, bench unchanged): the Pico and Uno rows below moved.** A bisect
(base 2fb312d, first changed commit 450b776, Task 5 of the JSET v3 plan) puts the change in `svf_is_jamo`, which went from
`f && (flags & JAMO) && !(status & JSET_BAD)` to `f && f->jset_lc != 0` (the cause bits zero `jset_lc`), 7 cycles fewer per call on
both ISAs and called several times per glyph; every checksum is unchanged. Pico MONO_PAGE `-Os`: `syl_ga` 6091 -> 6049, `syl_bwelk`
7321 -> 7279 (still over its 50 µs budget), `compose_bwelk` 3188 -> 3181, `screen32` 188251 -> 187299, `line8` 44617 -> 44379; every
other Pico row of the three kinds and both optimisation levels was re-run (`run-pico.sh`, this table and the ratio tables). Uno:
`syl_ga` 17208 -> 17166, `syl_bwelk` 20113 -> 20071, `compose_bwelk` 8414 -> 8407, `screen32` 523325 -> 522373; fit flash 27430 -> 27440
(+10 B: the version and status logic of `svf__jset_check`), RAM 1224 unchanged. **Not re-taken:** the DOS, WASM, Host, ESP32,
Cortex-M33 and RP2350 tables and the tables of the older sections ("Before -> after ..." keep their own runs; the JSET v1 + v2 section's "v1" column is RAW's `picoV1`). The DOS rows read about +105 µs (+0.9 %) on
every row in a probe run at 51a4020; the cause is not explained (a uniform shift on rows that never call `svf_is_jamo`: host or
emulator noise is suspected), and the DOS table was not re-taken.

### Pico (MONO_PAGE budget: <= 50 µs a syllable, <= 2 ms a screen; GRAY8 and RGB565: no budget)

Six builds, one target kind each (`run-pico.sh`, `-DSVF_TARGETS=<bit>`), grouped by kind with MONO_PAGE first.
**Emulated**: rp2040js's cycle counter, the Cortex-M0+ instruction timings, every memory access one cycle, the XIP flash
cache not modelled (the colour and grey images hold 139 KB of faces behind the RP2040's 16 KB XIP cache, the mono
one 13 KB; real GRAY8 and RGB565 drawing is as fast as these rows or slower, by an amount the bench cannot give). The
`insns` column is the instructions the core executed (BKPT markers excluded); it is what the C3 and S3 tables below
count too, so it is the column to compare across chips.

#### MONO_PAGE (`-DSVF_TARGETS=0x02`, 128 x 64 SSD1306 page buffer, 1 KB)

| build (emulator, version, clock; compiler, flags; kind) | case | iterations | cycles/iteration | µs/iteration | insns/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---:|---|---|
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; MONO_PAGE, SVF_TARGETS=0x02) | syl_ga | 100 | 6049 | 48.39 | 3923 | 50 | met | 29897c8f ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; MONO_PAGE, SVF_TARGETS=0x02) | syl_bwelk | 100 | 7279 | 58.23 | 4716 | 50 | **missed** | dc7e66c5 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; MONO_PAGE, SVF_TARGETS=0x02) | compose_bwelk | 100 | 3181 | 25.45 | 2067 | - | - | aab2d890 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; MONO_PAGE, SVF_TARGETS=0x02) | screen32 | 20 | 187299 | 1498.39 | 121676 | 2000 | met | e13a0418 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; MONO_PAGE, SVF_TARGETS=0x02) | line8 | 100 | 44379 | 355.03 | 28852 | - | - | ec19e65d ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; MONO_PAGE, SVF_TARGETS=0x02) | syl_ga | 100 | 4941 | 39.53 | 3464 | 50 | met | 29897c8f ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; MONO_PAGE, SVF_TARGETS=0x02) | syl_bwelk | 100 | 5898 | 47.18 | 4160 | 50 | met | dc7e66c5 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; MONO_PAGE, SVF_TARGETS=0x02) | compose_bwelk | 100 | 2661 | 21.29 | 1883 | - | - | aab2d890 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; MONO_PAGE, SVF_TARGETS=0x02) | screen32 | 20 | 151879 | 1215.03 | 106940 | 2000 | met | e13a0418 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; MONO_PAGE, SVF_TARGETS=0x02) | line8 | 100 | 35652 | 285.22 | 25215 | - | - | ec19e65d ok |

#### GRAY8 (`-DSVF_TARGETS=0x01`, 128 x 64, 8 KB; set B on a 240 x 24 band)

| build (emulator, version, clock; compiler, flags; kind) | case | iterations | cycles/iteration | µs/iteration | insns/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---:|---|---|
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | syl_ga | 100 | 7354 | 58.83 | 4551 | - | - | 6e77093d ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | syl_bwelk | 100 | 9152 | 73.22 | 5668 | - | - | 7e42aa20 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | compose_bwelk | 100 | 3181 | 25.45 | 2067 | - | - | aab2d890 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | screen32 | 20 | 285443 | 2283.54 | 177031 | - | - | 68ae8406 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | line8 | 100 | 55303 | 442.42 | 34152 | - | - | 363d4177 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | aa_syl_ga | 100 | 15823 | 126.58 | 11168 | - | - | 868f3420 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | aa_syl_bwelk | 100 | 19522 | 156.17 | 13979 | - | - | 087e0af1 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | aa_line12 | 20 | 155459 | 1243.67 | 110202 | - | - | 8a1e14e9 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; GRAY8, SVF_TARGETS=0x01) | aa_screen10 | 5 | 1566477 | 12531.82 | 1073846 | - | - | ff58266a ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | syl_ga | 100 | 6522 | 52.18 | 4368 | - | - | 6e77093d ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | syl_bwelk | 100 | 7921 | 63.37 | 5340 | - | - | 7e42aa20 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | compose_bwelk | 100 | 2661 | 21.29 | 1883 | - | - | aab2d890 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | screen32 | 20 | 259369 | 2074.96 | 171424 | - | - | 68ae8406 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | line8 | 100 | 48763 | 390.10 | 32740 | - | - | 363d4177 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | aa_syl_ga | 100 | 14044 | 112.35 | 10549 | - | - | 868f3420 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | aa_syl_bwelk | 100 | 17184 | 137.47 | 13119 | - | - | 087e0af1 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | aa_line12 | 20 | 139448 | 1115.58 | 104702 | - | - | 8a1e14e9 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; GRAY8, SVF_TARGETS=0x01) | aa_screen10 | 5 | 1449609 | 11596.87 | 1032614 | - | - | ff58266a ok |

#### GRAY (`SVF_T_GRAY` at its default 8 bits) against GRAY8, three builds (2026-10-26, Task 3 of the SDL target plan)

`PICO_KINDS="GRAY8:0x01 GRAY8:0x201 GRAY:0x200" c/bench/run-pico.sh`: the same cases, the same expected checksums (SUMS_GRAY8) in the three builds -- GRAY8 alone (`SVF_TARGETS=0x01`), GRAY8 with GRAY compiled in (`0x201`) and GRAY alone (`0x200`, `-DBENCH_KIND=SVF_T_GRAY`, bits 8 through `blit_gray8`); rp2040js 1.4.0, 125 MHz, gcc 15.2.1. The requirement is that neither GRAY build costs more than 1.01 x the cycles of GRAY8 alone (at -Os and -O2, every case); the largest ratio is 1.0063. These rows are the comparison only: they do not start with `| Pico emulated (` and are not parsed by `check-measurements-md.py`, and `measurements-raw.txt` has no entry for them (the 0x201 and 0x200 builds are not among the kinds the checker knows). All 60 rows (3 builds x 2 optimisations x 10 cases) printed `ok` checksums.

| opt | case | cycles GRAY8 0x01 | cycles GRAY8 0x201 | cycles GRAY 0x200 | 0x201 / 0x01 | 0x200 / 0x01 |
|---|---|---:|---:|---:|---:|---:|
| -O2 | aa_line12 | 139583 | 136792 | 139756 | 0.98 | 1.0012 |
| -O2 | aa_screen10 | 1450507 | 1432422 | 1451793 | 0.9875 | 1.0009 |
| -O2 | aa_syl_bwelk | 17202 | 17132 | 17243 | 0.9959 | 1.0024 |
| -O2 | aa_syl_ga | 14063 | 13891 | 14104 | 0.9878 | 1.0029 |
| -O2 | compose_bwelk | 2665 | 2665 | 2665 | 1.0 | 1.0 |
| -O2 | layout_probe | 5768 | 5768 | 5768 | 1.0 | 1.0 |
| -O2 | line8 | 48900 | 48051 | 49025 | 0.9826 | 1.0026 |
| -O2 | screen32 | 259915 | 256519 | 260415 | 0.9869 | 1.0019 |
| -O2 | syl_bwelk | 7941 | 7855 | 7982 | 0.9892 | 1.0052 |
| -O2 | syl_ga | 6543 | 6457 | 6584 | 0.9869 | 1.0063 |
| -Os | aa_line12 | 155744 | 152507 | 152532 | 0.9792 | 0.9794 |
| -Os | aa_screen10 | 1568436 | 1544670 | 1544846 | 0.9848 | 0.985 |
| -Os | aa_syl_bwelk | 19566 | 19121 | 19124 | 0.9773 | 0.9774 |
| -Os | aa_syl_ga | 15867 | 15570 | 15573 | 0.9813 | 0.9815 |
| -Os | compose_bwelk | 3188 | 3188 | 3188 | 1.0 | 1.0 |
| -Os | layout_probe | 5969 | 5969 | 5969 | 1.0 | 1.0 |
| -Os | line8 | 55541 | 55257 | 55274 | 0.9949 | 0.9952 |
| -Os | screen32 | 286395 | 285288 | 285356 | 0.9961 | 0.9964 |
| -Os | syl_bwelk | 9194 | 9170 | 9173 | 0.9974 | 0.9977 |
| -Os | syl_ga | 7396 | 7378 | 7381 | 0.9976 | 0.998 |

The first attempt (two call sites of `blit_gray8` in the dispatch) cost GRAY8 in the 0x201 build up to 4.7 % at -Os (`blit_gray8` was no longer inlined); one shared call site fixed -Os, and an `always_inline` on `blit_gray8` in the combined build only fixed the one -O2 case left (aa_syl_bwelk 1.0153). Both are off on AVR (size, not speed, matters there). The rows above were re-run on 2026-10-26 on the tree rebased onto main's compact JSET readers (the cycles moved with them, so they are not the numbers of the review round 1 commit; the gate compares the three builds with each other on the same tree); the maximum ratio is 1.0063 and all 60 rows printed `ok` checksums.

The GRAY8 0x01 -Os cycles equal the rows of the GRAY8 section above; the 0x01 -O2 cycles are 9 to 90 less than that section's (syl_ga 6543 against 6552, aa_line12 139583 against 139592, screen32 259915 against 259951, aa_screen10 1450507 against 1450597; compose_bwelk and layout_probe 0): the same run at e5232ca (before the GRAY kind) gives the section's values, i.e. the section above is the library as it was and the difference comes from Task 2's change of `svf_draw_utf8` (the draw-time `target_ok(t, gray_bits)`), not from this table's builds. The GRAY8 section's rows were re-taken on 2026-10-27 (library at 1cbe1f2, see the note under "Results") and now differ from this table, a run of 2026-10-26 that is not re-taken: this paragraph describes that run, the comparison among its three builds (the gate) is unaffected.

Two runs of the 0x201 build at -Os, both within the 1.01 gate: the first Step 4 run of the final dispatch (merged call site and `always_inline`, before the review-round edits of `blit_gray_packed`'s `top` and the AVR split) had syl_ga 7205 (0.9674 of GRAY8 0x01), syl_bwelk 9106 (0.9715), screen32 284491 (0.9719), line8 55204 (0.9636); the run of the final tree has syl_ga 7430 (0.9976), syl_bwelk 9349 (0.9974), screen32 291620 (0.9962), line8 57008 (0.995), i.e. up to 3 % slower than the first run, because inlining and layout of `svf_draw_utf8` moved with that small edit; those two runs predate the rebase onto the JSET readers, the table above is the run on the rebased tree. GRAY8 0x01 is the same in both.

#### RGB565 (`-DSVF_TARGETS=0x08`, 128 x 64, 16 KB; set B on a 240 x 24 band)

| build (emulator, version, clock; compiler, flags; kind) | case | iterations | cycles/iteration | µs/iteration | insns/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---:|---|---|
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | syl_ga | 100 | 8983 | 71.86 | 6216 | - | - | 2dfe3ba1 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | syl_bwelk | 100 | 11406 | 91.25 | 7871 | - | - | 00dcd68f ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | compose_bwelk | 100 | 3181 | 25.45 | 2067 | - | - | aab2d890 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | screen32 | 20 | 405605 | 3244.84 | 272498 | - | - | c714230b ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | line8 | 100 | 69400 | 555.20 | 48249 | - | - | 00dbcc05 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | aa_syl_ga | 100 | 17806 | 142.45 | 12284 | - | - | b0a50bda ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | aa_syl_bwelk | 100 | 22345 | 178.76 | 15536 | - | - | 2176bfa9 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | aa_line12 | 20 | 179543 | 1436.34 | 124060 | - | - | 18680583 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | aa_screen10 | 5 | 1783244 | 14265.95 | 1218792 | - | - | d1cd559a ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | syl_ga | 100 | 7993 | 63.94 | 5794 | - | - | 2dfe3ba1 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | syl_bwelk | 100 | 9920 | 79.36 | 7207 | - | - | 00dcd68f ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | compose_bwelk | 100 | 2661 | 21.29 | 1883 | - | - | aab2d890 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | screen32 | 20 | 373943 | 2991.55 | 258871 | - | - | c714230b ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | line8 | 100 | 61346 | 490.77 | 44715 | - | - | 00dbcc05 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | aa_syl_ga | 100 | 15880 | 127.04 | 11876 | - | - | b0a50bda ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | aa_syl_bwelk | 100 | 19935 | 159.48 | 15037 | - | - | 2176bfa9 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | aa_line12 | 20 | 160836 | 1286.69 | 120448 | - | - | 18680583 ok |
| Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -O2; RGB565, SVF_TARGETS=0x08) | aa_screen10 | 5 | 1591541 | 12732.33 | 1191762 | - | - | d1cd559a ok |

Run twice (`c/bench/run-pico.sh`; the second run of this task's rows is `c/build/t10/pico-r2`): every cycle, instruction and checksum identical (stdout `diff` clean). `PROFILE=1` (below) is
a separate build.

Note (2026-10-21, 96d69c7): `run-pico.sh` builds one program per target kind with `-DSVF_TARGETS=<bit>`. The MONO_PAGE rows of the
2026-10-20 run (all five kinds compiled in) were `syl_ga` 6,070 cycles (48.56 µs, `-Os`), 5,357 (`-O2`); `syl_bwelk` 7,479 /
6,639; `screen32` 193,280 / 173,335; the single-kind rows above are slower. In the single-kind MONO_PAGE build `syl_ga`
at `-Os` takes 6,335 cycles (50.68 µs, budget 50 µs). The cause is **suspected, not established**: gcc inlining `pack8`
into `svf_draw_utf8` when only one kind is compiled in (card t_8b967a59 covers establishing it and the speed). The
consequence was measured (**superseded**: the C speedups fixed it, `syl_ga` `-Os` is 48.73 µs (48.39 µs since the 2026-10-27 re-take), met, in the row above; this note is history): **`syl_ga` at `-Os` newly missed its budget** (by 1.4 %; `-O2`: 5,452 cycles, 43.6 µs, met).
`syl_bwelk` already missed before (`-Os` 7,744 cycles, 61.9 µs; `-O2` 6,734, 53.9 µs). The speed itself is left to the
card t_8b967a59.

Counts since 9234022 (2026-10-21): `pico-run.mjs` excludes the BKPT #1 and #2 steps from the cycles as it always did from the insns.

### Uno (no speed budget; the fit is the requirement)

| build (emulator, version, clock; compiler, flags) | case | iterations | cycles/iteration | µs/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---|---|
| Uno emulated (simavr 1.8, ATmega328P 16 MHz; avr-gcc 16.1.0 -Os) | syl_ga | 20 | 17166 | 1072.89 | - | - | 29897c8f ok |
| Uno emulated (simavr 1.8, ATmega328P 16 MHz; avr-gcc 16.1.0 -Os) | syl_bwelk | 20 | 20071 | 1254.45 | - | - | dc7e66c5 ok |
| Uno emulated (simavr 1.8, ATmega328P 16 MHz; avr-gcc 16.1.0 -Os) | compose_bwelk | 20 | 8407 | 525.44 | - | - | aab2d890 ok |
| Uno emulated (simavr 1.8, ATmega328P 16 MHz; avr-gcc 16.1.0 -Os) | screen32 | 2 | 522373 | 32648.31 | - | - | e13a0418 ok |

Uno fit (bench build, the five original target kinds: `run-avr.sh` passes `-DSVF_TARGETS=0x1F`): BASE (c592140) flash 27434 of
32256 bytes in SVF v3 (face 8716 in `mcu-strict`, code and constants 18718; v2: 31302 with the 12921 byte face), RAM 1223 of 2048 bytes before the stack; this tree (2026-10-26, JSET v1 + v2 readers, AVR default v1 alone) **27430 / 18714 / 1224**; re-taken 2026-10-27 (450b776, `svf_is_jamo`): **27440 / 18724 / 1224**. The Arduino port build
(`-DSVF_TARGETS=0x02`, MONO_PAGE only) is 22270 bytes of flash (`c/cross/SIZES.md`; a cross build with stub Wire and
core, not an arduino-cli build).

### DOS 486 (budget: <= 16 ms one line, mapped and streamed from a file)

| build (emulator, version, clock; compiler, flags) | case | iterations | cycles/iteration | µs/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---|---|
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_mapped | 50 | - | 11876.45 | 16000 | met | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_mapped_cache | 50 | - | 9235.82 | 16000 | met | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_cold | 1 | - | 23040.11 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_warm | 50 | - | 12818.69 | 16000 | met | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_small | 50 | - | 20177.68 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_nocache | 5 | - | 22354.05 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX2-66: cputype=486 cycles=fixed 23880; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_scaled32 | 50 | - | 145522.15 | - | - | 13e5d91d ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_mapped | 50 | - | 23646.81 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_mapped_cache | 50 | - | 18389.36 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_cold | 1 | - | 40603.26 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_warm | 50 | - | 25522.89 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_small | 50 | - | 36035.30 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_stream_nocache | 5 | - | 40997.00 | 16000 | **missed** | d88e20f9 ok |
| DOS emulated (DOSBox-X 2026.08.31, 486DX-33: cputype=486 cycles=fixed 12010; DJGPP gcc 12.2.0 -O2 -march=i486; word stores) | line40_scaled32 | 50 | - | 289743.09 | - | - | 13e5d91d ok |

v2 run (`c/bench/run-dos.sh`, 2026-10-21; the rows above are 2026-10-23 with SVF v3; word-store build, GRAY8 line; the `_bytes` rows are in the next section):
five runs of this tree gave identical rows; an independent run differed by at most 0.03 µs (mapped) and 0.033 %
(streamed). Against the 2026-10-20 run (library a293e6e) the GRAY8 `line40_mapped` row went from 15184.06 µs to
15190.90 µs on the DX2-66.

### Packed kinds (VESA), DOS emulated, 2026-10-21, library and bench at commit 377b286

(The table below is the SVF v3 run of 2026-10-23, library and bench at b45e9dc, profile `dos`; the prose after it quotes the 2026-10-21 v2 run at 377b286, whose figures differ.)

Every time below is **emulated** (DOSBox-X 2026.08.31, `core=normal`, `cputype=486`, `cycles=fixed 23880` for the
486DX2-66 preset and `fixed 12010` for the 486DX-33 preset, headless under xvfb-run; DJGPP gcc 12.2.0 `-O2
-march=i486`; `uclock()` on emulated time). Not real hardware: DOSBox-X runs a fixed number of **instructions** per
emulated millisecond whatever they are, so a word store costs the same as a byte store there, while a real 486 spends
1 to 40+ clocks an instruction. The word-store comparison therefore counts instructions and does not model memory
(a real 486's cache, bus and the unaligned 4-byte store penalty are not here): treat a row's word-versus-bytes
percentage as an instruction-count result, to be confirmed on a 486 or a cycle-accurate emulator. Each case ran in
the word-store build (`BENCH.EXE`) and the byte-loop build (`BENCHB.EXE`, `_bytes`), several times, with the same
rows each time (spread as above);
every checksum is `ok`. "16 ms" is the budget of the line, met or over, word / bytes.

| case | iterations | DX2-66 word µs | DX2-66 `_bytes` µs | word vs bytes | DX2-66 16 ms | DX-33 word µs | DX-33 `_bytes` µs | DX-33 16 ms | checksum |
|---|---:|---:|---:|---:|---|---:|---:|---|---|
| line40_mapped | 50 | 11868.84 | 11868.85 | -0.00 % | met / met | 23631.62 | 23631.62 | over / over | d88e20f9 ok |
| line40_mapped_cache | 50 | 9235.02 | 9235.04 | -0.00 % | met / met | 18387.77 | 18387.65 | over / over | d88e20f9 ok |
| line40_indexed8 | 50 | 11442.08 | 11545.58 | -0.90 % | met / met | 22782.06 | 22987.71 | over / over | db2a4271 ok |
| line40_rgb555 | 50 | 11402.10 | 12834.02 | -11.16 % | met / met | 22702.46 | 25553.41 | over / over | 9c1a4e65 ok |
| line40_rgb565 | 50 | 11377.13 | 12808.86 | -11.18 % | met / met | 22652.07 | 25503.34 | over / over | d86ce745 ok |
| line40_xrgb8888 | 50 | 12889.87 | 12889.91 | -0.00 % | met / met | 25664.29 | 25664.66 | over / over | 2c995f55 ok |
| line40_rgb888 | 50 | 13136.31 | 13136.31 | +0.00 % | met / met | 26155.25 | 26155.18 | over / over | aa90d161 ok |
| line40_24_indexed8 | 50 | 14939.29 | 15145.26 | -1.36 % | met / met | 29745.34 | 30155.32 | over / over | 30762be9 ok |
| line40_24_rgb555 | 50 | 14531.39 | 16957.21 | -14.31 % | met / over | 28932.82 | 33762.73 | over / over | 7d011e01 ok |
| line40_24_rgb565 | 50 | 14506.04 | 16932.01 | -14.33 % | met / over | 28882.45 | 33712.70 | over / over | e65da549 ok |
| line40_24_xrgb8888 | 50 | 17075.90 | 17076.10 | -0.00 % | over / over | 33999.48 | 33999.45 | over / over | dccb4dbd ok |
| line40_24_rgb888 | 50 | 17467.94 | 17467.96 | -0.00 % | over / over | 34779.85 | 34779.85 | over / over | 322d1519 ok |
| line40_24m_indexed8 | 50 | 12801.44 | 12798.09 | +0.03 % | met / met | 25488.21 | 25481.49 | over / over | 211b3db6 ok |
| line40_24m_rgb565 | 50 | 11798.15 | 13338.10 | -11.55 % | met / met | 23490.55 | 26556.95 | over / over | bdcc87ef ok |
| line40_24m_xrgb8888 | 50 | 13878.54 | 13878.56 | -0.00 % | met / met | 27632.80 | 27633.23 | over / over | 8f65703c ok |
| line40_stream_cold | 1 | 23034.24 | 23041.79 | -0.03 % | over / over | 40589.85 | 40605.78 | over / over | d88e20f9 ok |
| line40_stream_warm | 50 | 12811.28 | 12811.26 | +0.00 % | met / met | 25507.77 | 25507.70 | over / over | d88e20f9 ok |
| line40_stream_small | 50 | 20169.85 | 20170.12 | -0.00 % | over / over | 36020.73 | 36017.94 | over / over | d88e20f9 ok |
| line40_stream_nocache | 5 | 22348.35 | 22348.68 | -0.00 % | over / over | 40982.42 | 40978.23 | over / over | d88e20f9 ok |
| line40_scaled32 | 50 | 145514.52 | 145559.83 | -0.03 % | - / - | 289727.90 | 289818.00 | - / - | 13e5d91d ok |
| line40_mapped | 50 | 11868.84 | 11868.85 | -0.00 % | met / met | 23631.62 | 23631.62 | over / over | d88e20f9 ok |
| line40_mapped_cache | 50 | 9235.02 | 9235.04 | -0.00 % | met / met | 18387.77 | 18387.65 | over / over | d88e20f9 ok |
| line40_scaled32 | 50 | 145514.52 | 145559.83 | -0.03 % | - / - | 289727.90 | 289818.00 | - / - | 13e5d91d ok |
| line40_stream_cold | 1 | 23034.24 | 23041.79 | -0.03 % | over / over | 40589.85 | 40605.78 | over / over | d88e20f9 ok |
| line40_stream_warm | 50 | 12811.28 | 12811.26 | +0.00 % | met / met | 25507.77 | 25507.70 | over / over | d88e20f9 ok |
| line40_stream_small | 50 | 20169.85 | 20170.12 | -0.00 % | over / over | 36020.73 | 36017.94 | over / over | d88e20f9 ok |
| line40_stream_nocache | 5 | 22348.35 | 22348.68 | -0.00 % | over / over | 40982.42 | 40978.23 | over / over | d88e20f9 ok |
| line40_mapped | 50 | 11868.84 | 11868.85 | -0.00 % | met / met | 23631.62 | 23631.62 | over / over | d88e20f9 ok |
| line40_mapped_cache | 50 | 9235.02 | 9235.04 | -0.00 % | met / met | 18387.77 | 18387.65 | over / over | d88e20f9 ok |
| line40_scaled32 | 50 | 145514.52 | 145559.83 | -0.03 % | - / - | 289727.90 | 289818.00 | - / - | 13e5d91d ok |
| line40_stream_cold | 1 | 23034.24 | 23041.79 | -0.03 % | over / over | 40589.85 | 40605.78 | over / over | d88e20f9 ok |
| line40_stream_warm | 50 | 12811.28 | 12811.26 | +0.00 % | met / met | 25507.77 | 25507.70 | over / over | d88e20f9 ok |
| line40_stream_small | 50 | 20169.85 | 20170.12 | -0.00 % | over / over | 36020.73 | 36017.94 | over / over | d88e20f9 ok |
| line40_stream_nocache | 5 | 22348.35 | 22348.68 | -0.00 % | over / over | 40982.42 | 40978.23 | over / over | d88e20f9 ok |
| line40_mapped | 50 | 11868.84 | 11868.85 | -0.00 % | met / met | 23631.62 | 23631.62 | over / over | d88e20f9 ok |
| line40_mapped_cache | 50 | 9235.02 | 9235.04 | -0.00 % | met / met | 18387.77 | 18387.65 | over / over | d88e20f9 ok |
| line40_scaled32 | 50 | 145514.52 | 145559.83 | -0.03 % | - / - | 289727.90 | 289818.00 | - / - | 13e5d91d ok |
| line40_stream_cold | 1 | 23034.24 | 23041.79 | -0.03 % | over / over | 40589.85 | 40605.78 | over / over | d88e20f9 ok |
| line40_stream_warm | 50 | 12811.28 | 12811.26 | +0.00 % | met / met | 25507.77 | 25507.70 | over / over | d88e20f9 ok |
| line40_stream_small | 50 | 20169.85 | 20170.12 | -0.00 % | over / over | 36020.73 | 36017.94 | over / over | d88e20f9 ok |
| line40_stream_nocache | 5 | 22348.35 | 22348.68 | -0.00 % | over / over | 40982.42 | 40978.23 | over / over | d88e20f9 ok |

**Verdict per kind** (a word path stays in the x86 default only if its row is not slower):

- **RGB565 and RGB555** (pairs of pixels as 4-byte stores, 1 and 2 bpp faces): faster on every face, 8.9 % (PAPLG16 +
  PAPLG18, 2 bpp), 10.7 % (MARUS24A, 2 bpp) and 11.2 % (MARUS24, 1 bpp, RGB565). **Stays.** RGB565 before and after
  (F11): `line40_rgb565_bytes` 16130.96 µs against `line40_rgb565` 14699.27 µs on the DX2-66 (-1431.69 µs, -8.9 %;
  16.13 ms is over the 16 ms line budget, 14.70 ms is met), 32118.31 against 29266.92 µs on the DX-33. (The 15184.06 µs
  of the 2026-10-20 notes is the **GRAY8** `line40_mapped` row, not RGB565: 15190.90 µs now.)
- **INDEXED8, 2 bpp faces** (a `0xFF` source byte as one 4-byte maximum): faster, 0.69 % (PAPLG16 + PAPLG18) and
  0.99 % (MARUS24A). **Stays.**
- **INDEXED8, 1 bpp faces** (a nibble `0xF` as one 4-byte maximum): **slower**. The run of 2026-10-21 before the
  change measured `line40_24m_indexed8` (MARUS24) at 13850.42 µs (word) against 13225.90 µs (`_bytes`), word 4.7 %
  slower, on the DX-33 27576.79 against 26333.63 µs; the 1 bpp word path was therefore **removed from the x86 default
  in `c/src/svf_draw.c` in this task** (commit 377b286; the 2 bpp path stays). After the removal the rows agree to 0.03 %
  (13229.30 against 13225.93 µs); the other `indexed8` rows moved by at most 0.2 % (14794.36 to 14764.18 µs for
  `line40_indexed8`). Pixels are unchanged (checksums, `make -C c check`, the ten PNGs of `vesa-shots.sh`). The
  removal is in the one `SVF_WORD_STORE` switch, so it applies to every build where the switch is 1, WASM included;
  the packed kinds are not benched on WASM (`bench.c` builds those cases for DOS and the host only), so the WASM
  effect is unmeasured (only the size moved, `c/cross/SIZES.md`).
- **XRGB8888 and RGB888**: no word path (the 3 and 4 byte pixel stores are `memcpy` in both builds): the two builds
  agree to 0.002 %. Nothing to decide.
- The GRAY8 rows and the streamed rows do not use the switch: equal to 0.01 %.

**24 px against the 16 ms line budget.** On the DX2-66 preset the 1 bpp face MARUS24 meets it on all three kinds
(12.23 ms RGB565, 13.23 ms INDEXED8, 14.31 ms XRGB8888), the 2 bpp face MARUS24A does not on any (20.14 ms RGB565
to 23.10 ms RGB888, 1.26x to 1.44x over) although both draw the same 40 code points; the 16 px line (PAPLG16 +
PAPLG18) meets it for INDEXED8, RGB555 and RGB565 (14.70 to 14.76 ms) and misses it by 1.3 % for XRGB8888 (16.21 ms)
and 2.9 % for RGB888 (16.46 ms). **DX-33 finding: on the 486DX-33 preset no row meets 16 ms**, 16 px or 24 px: the
16 px rows take 29.3 to 32.8 ms (1.83x to 2.05x), MARUS24A 40.1 to 46.0 ms (2.5x to 2.9x), MARUS24 24.3 to 28.5 ms
(1.52x to 1.78x). The DX-33 budget is not reachable by the blit alone: it halves the cycles of the DX2-66, so the
whole line would have to be about 1.9x cheaper (the GRAY8 mapped row, 30.2 ms, is already over).

**Flush** (`flush_WxH_bpp` of `c/ports/dos/vesa-shots.sh`, 2026-10-21; **DOSBox-X emulated** `uclock()` time under
`cycles = fixed 23880`, not real hardware; one flush of all rows of the back buffer to the VBE frame buffer): 640x480
8 bpp 4140 µs, 15 and 16 bpp 8159 µs, 24 bpp 12180 µs, 32 bpp 16201 µs; 1024x768 8 bpp 10475 µs, 15 and 16 bpp 20768
µs, 24 bpp 31059 µs, 32 bpp 41352 µs (`c/ports/dos/README.md`). A 32 bpp 640x480 flush alone is 16.2 ms on the
DX2-66 preset, as long as the whole 16 ms line budget.

**Uno fit at `-DSVF_TARGETS=0x1F`** (`c/bench/run-avr.sh`, simavr 1.8 **emulated**, avr-gcc 16.1.0 `-Os`; re-run
2026-10-21, checksums `ok`, cycle counts unchanged): flash 27434 of 32256 bytes in v3 (face 8716, code and constants 18718; v2: 31302 with the 12921 byte face),
RAM 1223 of 2048 bytes before the stack. The nine-kind default (`0x1FF`) is not built on the Uno; the Arduino port
(`-DSVF_TARGETS=0x02`) is 22270 bytes of flash (`c/cross/SIZES.md`).

### WASM (budget: <= 1 ms the sample line)

Median of five runs, 2026-10-26 (`c/build/t10/wasm-r1..r5`; `line40_mapped` 13.31 to 13.79 µs).

| build (emulator, version, clock; compiler, flags) | case | iterations | cycles/iteration | µs/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---|---|
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_mapped | 2000 | - | 13.74 | 1000 | met | d88e20f9 ok |
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_mapped_cache | 2000 | - | 9.45 | 1000 | met | d88e20f9 ok |
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_scaled32 | 2000 | - | 152.46 | - | - | 13e5d91d ok |
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_stream_cold | 1 | - | 81.94 | 1000 | met | d88e20f9 ok |
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_stream_warm | 2000 | - | 12.34 | 1000 | met | d88e20f9 ok |
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_stream_small | 2000 | - | 13.06 | 1000 | met | d88e20f9 ok |
| WASM (node v24.13.0, V8 13.6.233.17-node.37, on AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; emcc 6.0.13 -O2) | line40_stream_nocache | 200 | - | 13.16 | 1000 | met | d88e20f9 ok |

### Host (x86-64; host CPU times, not an emulation)

`c/bench/run-host.sh` (`cc` 13.3.0 `-O2 -DBENCH_HOST`, the faces embedded by `mkface.py`; the line section; runner unchanged since 2026-10-21, rows re-taken 2026-10-26). These are the host CPU's times, not a measurement of any target;
the checksums are the ones the other runners' sums come from. Repeated runs of the same build
differ by up to about 50 % (`line40_mapped` gave 10.04 and 14.95 µs). **The rows are the median of five runs, 2026-10-26** (`c/build/t10/host-r1..r5`; `line40_mapped` 7.93 to 8.42 µs, the machine quiet), so read them as indicative only.

| build (emulator, version, clock; compiler, flags) | case | iterations | cycles/iteration | µs/iteration | budget µs | result | pixel checksum |
|---|---|---:|---:|---:|---:|---|---|
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_mapped | 2000 | - | 7.99 | - | - | d88e20f9 ok |
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_mapped_cache | 2000 | - | 6.18 | - | - | d88e20f9 ok |
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_stream_cold | 1 | - | 32.40 | - | - | d88e20f9 ok |
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_stream_warm | 2000 | - | 8.47 | - | - | d88e20f9 ok |
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_stream_small | 2000 | - | 8.87 | - | - | d88e20f9 ok |
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_stream_nocache | 200 | - | 8.92 | - | - | d88e20f9 ok |
| host x86-64 (AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S; cc 13.3.0 -O2) | line40_scaled32 | 2000 | - | 108.81 | - | - | 13e5d91d ok |

### ESP32-C3 (no budget; instruction counts)

`c/bench/run-esp32.sh` (twelve builds: chip x kind x `-Os`/`-O2`; 92 rows, every checksum `ok`, QEMU exit 0). Iterations
are the Pico's (100 / 20 / 5). **These are instruction counts, not cycles and not microseconds**: `rdinstret` around each
case, the instructions QEMU executed on the one core (no pipeline, memory, cache or flash timing, CPI >= 1 on a real
core), so instructions / 160 MHz is a **lower bound** of the time on a C3 and the counts say nothing about a real C3's
cycles. They include the few instructions between the counter read in `bench_start` and the one in `bench_stop`, once per
interval (`aa_screen10` has 50 intervals of ten bands over 5 iterations), and any exception handler that runs inside a case.
Two complete runs give byte-identical rows (`cmp`).

MONO_PAGE (`-DSVF_TARGETS=0x02`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 160 MHz, lower bound | `-O2` µs at 160 MHz, lower bound |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3375 | 2885 | 21.09 | 18.03 |
| syl_bwelk | 100 | 4141 | 3511 | 25.88 | 21.94 |
| compose_bwelk | 100 | 1812 | 1529 | 11.32 | 9.56 |
| screen32 | 20 | 98680 | 84880 | 616.75 | 530.50 |
| line8 | 100 | 24368 | 20969 | 152.30 | 131.06 |

GRAY8 (`-DSVF_TARGETS=0x01`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 160 MHz, lower bound | `-O2` µs at 160 MHz, lower bound |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 4013 | 3658 | 25.08 | 22.86 |
| syl_bwelk | 100 | 5153 | 4572 | 32.21 | 28.58 |
| compose_bwelk | 100 | 1812 | 1529 | 11.32 | 9.56 |
| screen32 | 20 | 120259 | 111502 | 751.62 | 696.88 |
| line8 | 100 | 29787 | 27526 | 186.17 | 172.04 |
| aa_syl_ga | 100 | 8525 | 8065 | 53.28 | 50.41 |
| aa_syl_bwelk | 100 | 10712 | 10065 | 66.95 | 62.90 |
| aa_line12 | 20 | 81449 | 78562 | 509.06 | 491.01 |
| aa_screen10 | 5 | 598796 | 577011 | 3742.47 | 3606.32 |

RGB565 (`-DSVF_TARGETS=0x08`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 160 MHz, lower bound | `-O2` µs at 160 MHz, lower bound |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 4387 | 3836 | 27.42 | 23.98 |
| syl_bwelk | 100 | 5699 | 4890 | 35.62 | 30.56 |
| compose_bwelk | 100 | 1812 | 1529 | 11.32 | 9.56 |
| screen32 | 20 | 135711 | 119996 | 848.20 | 749.98 |
| line8 | 100 | 33134 | 29185 | 207.09 | 182.41 |
| aa_syl_ga | 100 | 8882 | 8097 | 55.51 | 50.61 |
| aa_syl_bwelk | 100 | 11362 | 10162 | 71.01 | 63.51 |
| aa_line12 | 20 | 86647 | 80105 | 541.55 | 500.65 |
| aa_screen10 | 5 | 839843 | 647875 | 5249.02 | 4049.22 |

### ESP32-S3 (no budget; ICOUNT instruction counts, core 0)

Same builds and iterations. **Instruction counts of core 0**, from the Xtensa `ICOUNT` register (turned on with
`ICOUNTLEVEL` 15 by `bench_calibrate`), not cycles and not microseconds; the µs columns divide them by 240 MHz and are a
**lower bound** of the time on an S3, the same kind of bound as the C3's (QEMU's Xtensa has no instruction timing, a real
core spends at least a cycle on each instruction).

- **Why not CCOUNT (correction, 7e54163, 2026-10-21).** The first version converted `CCOUNT` (`ccount * 25 / 32` at `-icount
  shift=5`) and called that an estimate of instructions. It was wrong for every case that another core's time landed
  in. `-M esp32s3` has two vCPUs; with `-kernel` the APP CPU (core 1) is not parked but loops on a double exception at
  ROM 0x400003c0, and under `-icount` QEMU's round-robin gives it turns of about 390,630 instructions (12.5 ms of
  virtual time). The virtual clock, and with it core 0's `CCOUNT`, counts those instructions too, so a case read 0, 1,
  2 ... extra turns, by an amount that depends on code layout (screen32 `-Os` MONO_PAGE: 3,306,284 converted against
  2,134,438 for core 0; GRAY8 `aa_syl_ga` `-Os`: 22,053 an iteration against 10,334). The 1,000-NOP calibration
  could not see it (too short for core 1 to be scheduled), and the first cross-check counted the `Trace 1:` lines too,
  so it agreed with the error. The raw `ccount=` field of an S3 row is that clock (the 9234022 numbers were derived from it);
  it is kept in the output only as evidence.
- **Core 1 cannot be stopped in this QEMU (tried, none works).** The `SYSTEM_CORE_1_CONTROL_0` bits RUNSTALL / RESETING
  at 0x600C0000 (the device there, `esp32s3.soc.clk`, does not implement the register: reads 0); the RTC_CNTL
  `OPTIONS0` / `SW_CPU_STALL` stall fields at the offsets 0xAC, 0xB0, 0xB4, 0xB8, 0xBC, 0xC0, 0xC4 (stored, no effect on
  core 1); `-smp 1` (the reviewer saw QEMU dump core; not retried); `-device loader` writing a `waiti` loop at the reset vector 0x40000400 of
  core 1 (accepted, no effect: the ROM region is read-only to it). So the S3 measurement is of core 0 alone, with
  `ICOUNT`, which the CPU keeps per core.
- **The gate.** Before the cases the S3 build prints `cal=nop1000` (1,000 NOPs: 1280 +- 2 CCOUNT ticks, the tick rate) and
  four `cal=loop1m` lines (a loop of 500,000 x (addi, bnez) = 1,000,000 instructions, longer than a turn of core 1);
  `c/bench/check-esp32-cal.sh` (called by `run-esp32.sh`) requires exactly one NOP line and exactly four loop lines, in
  exactly that form, with the `ICOUNT` advance within 1,000,000 +- 0.1 %. Run on the 9234022 build's measurement
  (CCOUNT converted, the same four loops) it fails: every second loop reads 2,171,877 (`ccount=2780002`) and the
  check prints `cal: loop1m icount 2171877 is not 1,000,000 +- 0.1 %`; on the current build it passes (1,000,001 each).
  The `ccount` of the same loops still reads 2,780,004 in every second loop: the clock does include core 1.
- The count includes the few instructions between the counter read in `bench_start` and the one in `bench_stop` once
  per interval, and any exception handler that runs inside a case. Two complete runs give byte-identical rows and raw
  output (`cmp`).

Cross-check (once, not scripted; S3 `-Os` builds, except the one `-O2` case named below, `-accel tcg,one-insn-per-tb=on -d nochain,exec` through a pipe, the
`Trace 0:` lines (core 0 only) counted from the `rsr.icount` of `bench_start` to the one of `bench_stop`; the logs are
hundreds of MB and not kept). MONO_PAGE: `syl_ga` 346,214 traced against 346,008 `ICOUNT` (-206), `syl_bwelk` 426,614
against 426,408 (-206), `compose_bwelk` 200,910 against 200,907 (-3), `screen32` 2,134,437 against 2,134,247 (-190),
`line8` 2,612,145 against 2,611,909 (-236). GRAY8: `aa_syl_ga` 1,033,420 against 1,033,206 (-214), `aa_syl_bwelk`
1,414,404 against 1,414,183 (-221), `aa_line12` 2,113,048 against 2,112,978 (-70), `aa_screen10` (50 intervals summed)
3,817,801 against 3,817,645 (-156). So `ICOUNT` is within 0.001-0.06 % of the full core-0 count and, in these cases, below
it; it is **not** a bound in either direction (the `-O2` GRAY8 `aa_screen10` reads 2 above the trace; that comparison is
from a review's own `-O2` trace of 2026-10-21, not one of the `-Os` traces listed). The measured cause of the shortfall: for
each window exception that core 0 takes inside the interval the trace lists the faulting instruction twice (once at the fault,
once when it is re-executed after the handler) while `ICOUNT` counts it once, so against the trace `ICOUNT` is one lower per exception, plus at most about 30 for a long interval. In the same traces core 1 ran 0,
1,171,891, 1,953,152 ... instructions inside the intervals (multiples of 390,630) in exactly the cases the old figures
were inflated in; none now enters the count.

MONO_PAGE (`-DSVF_TARGETS=0x02`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 240 MHz, lower bound | `-O2` µs at 240 MHz, lower bound |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3114 | 2496 | 12.97 | 10.40 |
| syl_bwelk | 100 | 3773 | 3040 | 15.72 | 12.67 |
| compose_bwelk | 100 | 1532 | 1274 | 6.38 | 5.31 |
| screen32 | 20 | 93134 | 75342 | 388.06 | 313.92 |
| line8 | 100 | 23036 | 18434 | 95.98 | 76.81 |

GRAY8 (`-DSVF_TARGETS=0x01`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 240 MHz, lower bound | `-O2` µs at 240 MHz, lower bound |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3286 | 2904 | 13.69 | 12.10 |
| syl_bwelk | 100 | 4361 | 3653 | 18.17 | 15.22 |
| compose_bwelk | 100 | 1532 | 1274 | 6.38 | 5.31 |
| screen32 | 20 | 102176 | 95499 | 425.73 | 397.91 |
| line8 | 100 | 25020 | 21913 | 104.25 | 91.30 |
| aa_syl_ga | 100 | 8528 | 7542 | 35.53 | 31.43 |
| aa_syl_bwelk | 100 | 10888 | 9387 | 45.37 | 39.11 |
| aa_line12 | 20 | 83212 | 74287 | 346.72 | 309.53 |
| aa_screen10 | 5 | 615117 | 559124 | 2562.99 | 2329.68 |

RGB565 (`-DSVF_TARGETS=0x08`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 240 MHz, lower bound | `-O2` µs at 240 MHz, lower bound |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3662 | 3249 | 15.26 | 13.54 |
| syl_bwelk | 100 | 4735 | 4077 | 19.73 | 16.99 |
| compose_bwelk | 100 | 1532 | 1274 | 6.38 | 5.31 |
| screen32 | 20 | 115918 | 114934 | 482.99 | 478.89 |
| line8 | 100 | 27903 | 24775 | 116.26 | 103.23 |
| aa_syl_ga | 100 | 8107 | 7777 | 33.78 | 32.40 |
| aa_syl_bwelk | 100 | 10404 | 9775 | 43.35 | 40.73 |
| aa_line12 | 20 | 80044 | 77594 | 333.52 | 323.31 |
| aa_screen10 | 5 | 735239 | 601661 | 3063.50 | 2506.92 |

### Cortex-M33 (RP2350 ARM core; no budget; instruction counts)

`c/bench/run-m33.sh` (eight builds: MONO_PAGE, GRAY8, RGB565 and the line cases, each `-Os` and `-O2`; 60 rows, every checksum
`ok`, QEMU exit 0, `arm-none-eabi-gcc` 15.2.1, 2026-10-21). Iterations are the Pico's (100 / 20 / 5) for the set A/B cases and 20 for the
line cases (`line40_stream_cold` 1, `line40_stream_nocache` 2: `BENCH_LINE_N / 10`). **These are instruction counts, not RP2350
cycles and not microseconds**: QEMU 8.2.2 `-M mps2-an505 -icount shift=0` runs one instruction to the nanosecond of virtual time,
so a SysTick tick of the 20 MHz processor clock is exactly 50 instructions executed, and the program reads SysTick (ticks x 50)
before and after each case. The count has a granularity of 50 instructions per interval, includes the few dozen instructions
between the counter read of `bench_start` and the one of `bench_stop` (the same every interval) and any exception handler that
runs inside a case, and has no pipeline, memory, cache, flash or bus timing. Every build prints one calibration line first,
`cal=loop2m ticks=40000 insns=2000000`: a loop of 1,000,000 x (`subs`, `bne`) reads 40,000 ticks, and `run-m33.sh` fails
unless `insns` (the advance of `bench_now()`, the clock every row uses) is within 100 of `ticks * 50` (the raw SysTick
difference) and within 100 of 2,000,000. instructions / 150 MHz is the time **at one instruction per cycle**: an
estimate, not a bound. Taken branches, loads and multi-cycle operations make a real Cortex-M33 slower, and its limited
dual issue can make short stretches faster. The first M33 numbers are the baseline for the speed work of
`docs/superpowers/plans/2026-10-21-c-speedups.md`. Two complete runs give byte-identical rows (`cmp`).

MONO_PAGE (`-DSVF_TARGETS=0x02`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 150 MHz, 1 instruction/cycle estimate | `-O2` µs at 150 MHz, 1 instruction/cycle estimate |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3308 | 2626 | 22.05 | 17.50 |
| syl_bwelk | 100 | 3874 | 3132 | 25.83 | 20.88 |
| compose_bwelk | 100 | 1527 | 1368 | 10.18 | 9.12 |
| screen32 | 20 | 102848 | 82090 | 685.65 | 547.27 |
| line8 | 100 | 24479 | 19348 | 163.19 | 128.98 |

GRAY8 (`-DSVF_TARGETS=0x01`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 150 MHz, 1 instruction/cycle estimate | `-O2` µs at 150 MHz, 1 instruction/cycle estimate |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3638 | 2752 | 24.26 | 18.34 |
| syl_bwelk | 100 | 4510 | 3330 | 30.07 | 22.20 |
| compose_bwelk | 100 | 1528 | 1368 | 10.18 | 9.12 |
| screen32 | 20 | 141460 | 114588 | 943.07 | 763.92 |
| line8 | 100 | 27363 | 20421 | 182.42 | 136.14 |
| aa_syl_ga | 100 | 8784 | 7992 | 58.56 | 53.28 |
| aa_syl_bwelk | 100 | 10186 | 8882 | 67.91 | 59.21 |
| aa_line12 | 20 | 85510 | 77825 | 570.07 | 518.83 |
| aa_screen10 | 5 | 834880 | 777110 | 5565.87 | 5180.73 |

RGB565 (`-DSVF_TARGETS=0x08`):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 150 MHz, 1 instruction/cycle estimate | `-O2` µs at 150 MHz, 1 instruction/cycle estimate |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 4711 | 3926 | 31.41 | 26.17 |
| syl_bwelk | 100 | 5901 | 4888 | 39.34 | 32.58 |
| compose_bwelk | 100 | 1527 | 1368 | 10.18 | 9.12 |
| screen32 | 20 | 208298 | 184410 | 1388.65 | 1229.40 |
| line8 | 100 | 36266 | 30148 | 241.77 | 200.99 |
| aa_syl_ga | 100 | 8674 | 7684 | 57.83 | 51.23 |
| aa_syl_bwelk | 100 | 10154 | 8451 | 67.70 | 56.34 |
| aa_line12 | 20 | 86038 | 75382 | 573.58 | 502.55 |
| aa_screen10 | 5 | 949610 | 612900 | 6330.73 | 4086.00 |

LINE (default `SVF_TARGETS`, scaling on; the 40 code point PAPLG16 + PAPLG18 line, 640 x 24 GRAY8, baseline 19; `line40_scaled32` at 3/2 on 960 x 36):

| case | iterations | `-Os` instructions/iteration | `-O2` instructions/iteration | `-Os` µs at 150 MHz, 1 instruction/cycle estimate | `-O2` µs at 150 MHz, 1 instruction/cycle estimate |
|---|---:|---:|---:|---:|---:|
| line40_mapped | 20 | 232288 | 217400 | 1548.58 | 1449.33 |
| line40_mapped_cache | 20 | 195158 | 180672 | 1301.05 | 1204.48 |
| line40_scaled32 | 20 | 3738508 | 2938472 | 24923.38 | 19589.82 |
| line40_stream_cold | 1 | 401400 | 370100 | 2676.00 | 2467.33 |
| line40_stream_warm | 20 | 248685 | 230795 | 1657.90 | 1538.63 |
| line40_stream_small | 20 | 339460 | 319250 | 2263.07 | 2128.33 |
| line40_stream_nocache | 2 | 263625 | 248725 | 1757.50 | 1658.17 |

### RP2350 Hazard3 under rp2350js (RISC-V core; no budget; rp2350js cycles)

`c/bench/run-rp2350.sh` (eight builds a core: MONO_PAGE, GRAY8, RGB565 and the line cases, each `-Os` and `-O2`; 60 rows, every checksum `ok`, every calibration within its tolerance, 2026-10-21, the library as of 344a090, `c/src` and `c/include` unchanged since, before any speed change: the "before" rows of `docs/superpowers/plans/2026-10-21-c-speedups.md`). The images are real pico-sdk 2.3.1 `pico2` builds (`-mcpu=hazard3-rp2350 -mstrict-align`, riscv32-pico-elf-gcc 16.1.0; ALU op 1 cycle, a one-entry backward-branch predictor, +1 for a misaligned 32-bit fetch after a jump, 3 for an AMO, 17 for a divide), booted through the A2 boot ROM bundled in rp2350js af0114c (+ `c/bench/rp2350js.patch`, four emulator fixes) and run by `c/bench/rp2350-run.mjs`. **These are rp2350js cycles, not RP2350 cycles**: the runner reads core 0's `cycles` counter at the first instruction of the marker functions `bench.c` calls around each case, so a count holds the marks' own cost, a constant per interval (`cal=empty`: 7-8 cycles). Every build first reports `cal=empty` and `cal=loop1m` (1,000,000 x two instructions whose cost rp2350js models exactly); `run-rp2350.sh` fails unless the loop minus the empty interval is within 16 cycles of 2,000,000 and its instruction count within 16 of 2,000,000 (measured: loop 2,000,011 - 2,000,014 cycles). The µs columns divide by 150 MHz, the SDK's `clk_sys`; rp2350js itself runs 125 MHz whatever the SDK programs, so no time is read from the emulated chip. **What rp2350js does not model**: XIP flash and XIP cache timing (code and faces are in flash, as on a board), QMI, bus contention and APB wait states, Hazard3's dependent-register (load-use) penalty; timer and system interrupts and exceptions (the bench uses none; entering a fault handler ends the run). Its instruction cycle counts are "somewhat correct" in its own words. rp2350js's cycle counts are an estimate that could be off in either direction: its timing tables are not checked against the chip. Two complete runs give byte-identical rows (`diff`) and byte-identical raw files (`cmp`).

MONO_PAGE (`-DSVF_TARGETS=0x02`):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 3601 | 2808 | 24.01 | 18.72 |
| syl_bwelk | 100 | 4391 | 3371 | 29.27 | 22.47 |
| compose_bwelk | 100 | 1902 | 1428 | 12.68 | 9.52 |
| screen32 | 20 | 105820 | 82184 | 705.47 | 547.90 |
| line8 | 100 | 26167 | 20329 | 174.45 | 135.53 |

GRAY8 (`-DSVF_TARGETS=0x01`):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 4385 | 3640 | 29.23 | 24.27 |
| syl_bwelk | 100 | 5531 | 4450 | 36.87 | 29.67 |
| compose_bwelk | 100 | 1878 | 1428 | 12.52 | 9.52 |
| screen32 | 20 | 131519 | 111166 | 876.80 | 741.11 |
| line8 | 100 | 32594 | 27419 | 217.29 | 182.79 |
| aa_syl_ga | 100 | 9685 | 8152 | 64.57 | 54.35 |
| aa_syl_bwelk | 100 | 12036 | 10026 | 80.24 | 66.84 |
| aa_line12 | 20 | 93594 | 79596 | 623.96 | 530.64 |
| aa_screen10 | 5 | 678679 | 577805 | 4524.53 | 3852.03 |

RGB565 (`-DSVF_TARGETS=0x08`):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 5076 | 4149 | 33.84 | 27.66 |
| syl_bwelk | 100 | 6461 | 5176 | 43.07 | 34.51 |
| compose_bwelk | 100 | 1901 | 1428 | 12.67 | 9.52 |
| screen32 | 20 | 157233 | 129588 | 1048.22 | 863.92 |
| line8 | 100 | 38624 | 31707 | 257.49 | 211.38 |
| aa_syl_ga | 100 | 9691 | 8113 | 64.61 | 54.09 |
| aa_syl_bwelk | 100 | 12064 | 9968 | 80.43 | 66.45 |
| aa_line12 | 20 | 95022 | 80174 | 633.48 | 534.49 |
| aa_screen10 | 5 | 958166 | 679051 | 6387.77 | 4527.01 |

LINE (default `SVF_TARGETS`, scaling on; the 40 code point PAPLG16 + PAPLG18 line, 640 x 24 GRAY8, baseline 19; `line40_scaled32` at 3/2 on 960 x 36):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| line40_mapped | 20 | 257993 | 199248 | 1719.95 | 1328.32 |
| line40_mapped_cache | 20 | 209274 | 158628 | 1395.16 | 1057.52 |
| line40_scaled32 | 20 | 4566034 | 3388443 | 30440.22 | 22589.62 |
| line40_stream_cold | 1 | 375481 | 277862 | 2503.21 | 1852.41 |
| line40_stream_warm | 20 | 285479 | 217781 | 1903.19 | 1451.87 |
| line40_stream_small | 20 | 313507 | 241481 | 2090.05 | 1609.87 |
| line40_stream_nocache | 2 | 290336 | 229888 | 1935.57 | 1532.59 |

### RP2350 Cortex-M33 under rp2350js (Arm core; no budget; rp2350js cycles)

`c/bench/run-rp2350.sh` (eight builds a core: MONO_PAGE, GRAY8, RGB565 and the line cases, each `-Os` and `-O2`; 60 rows, every checksum `ok`, every calibration within its tolerance, 2026-10-21, the library as of 344a090, `c/src` and `c/include` unchanged since, before any speed change: the "before" rows of `docs/superpowers/plans/2026-10-21-c-speedups.md`). The images are real pico-sdk 2.3.1 `pico2` builds (`-mcpu=cortex-m33 -march=armv8-m.main+fp+dsp -mfloat-abi=softfp`, arm-none-eabi-gcc 15.2.1; rp2350js's M33 timing table is its own and not checked here against Arm's), booted through the A2 boot ROM bundled in rp2350js af0114c (+ `c/bench/rp2350js.patch`, four emulator fixes) and run by `c/bench/rp2350-run.mjs`. **These are rp2350js cycles, not RP2350 cycles**: the runner reads core 0's `cycles` counter at the first instruction of the marker functions `bench.c` calls around each case, so a count holds the marks' own cost, a constant per interval (`cal=empty`: 11-12 cycles). Every build first reports `cal=empty` and `cal=loop1m` (1,000,000 x two instructions whose cost rp2350js models exactly); `run-rp2350.sh` fails unless the loop minus the empty interval is within 16 cycles of 3,000,000 and its instruction count within 16 of 2,000,000 (measured: loop 3,000,013 cycles). The µs columns divide by 150 MHz, the SDK's `clk_sys`; rp2350js itself runs 125 MHz whatever the SDK programs, so no time is read from the emulated chip. **What rp2350js does not model**: XIP flash and XIP cache timing (code and faces are in flash, as on a board), QMI, bus contention and APB wait states, Hazard3's dependent-register (load-use) penalty; timer and system interrupts and exceptions (the bench uses none; entering a fault handler ends the run). Its instruction cycle counts are "somewhat correct" in its own words. rp2350js's cycle counts are an estimate that could be off in either direction: its timing tables are not checked against the chip. Two complete runs give byte-identical rows (`diff`) and byte-identical raw files (`cmp`). The QEMU instruction counts of `### Cortex-M33` above are the cross-check: the rp2350js `insns` of MONO_PAGE `-Os` (per iteration: syl_ga 3343.1, syl_bwelk 3988.1, compose_bwelk 1641.1, screen32 102074.4, line8 25031.1) are 0.94 - 0.98 of the QEMU counts (3420, 4065, 1718, 108275, 25648); the two images are the same library code built by pico-sdk's flags (`-mcpu=cortex-m33 -march=armv8-m.main+fp+dsp -mfloat-abi=softfp`) and by the bare `-mcpu=cortex-m33 -mthumb`, so a small difference is expected; a cross-check, not a gate.

MONO_PAGE (`-DSVF_TARGETS=0x02`):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 5132 | 3795 | 34.21 | 25.30 |
| syl_bwelk | 100 | 6065 | 4548 | 40.43 | 30.32 |
| compose_bwelk | 100 | 2388 | 1949 | 15.92 | 12.99 |
| screen32 | 20 | 152233 | 112042 | 1014.88 | 746.95 |
| line8 | 100 | 37579 | 27677 | 250.53 | 184.51 |

GRAY8 (`-DSVF_TARGETS=0x01`):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 5977 | 4176 | 39.85 | 27.84 |
| syl_bwelk | 100 | 7466 | 5041 | 49.77 | 33.61 |
| compose_bwelk | 100 | 2388 | 1949 | 15.92 | 12.99 |
| screen32 | 20 | 182679 | 128514 | 1217.86 | 856.76 |
| line8 | 100 | 44782 | 30850 | 298.55 | 205.67 |
| aa_syl_ga | 100 | 12111 | 10054 | 80.74 | 67.03 |
| aa_syl_bwelk | 100 | 13952 | 11063 | 93.01 | 73.75 |
| aa_line12 | 20 | 115614 | 96408 | 770.76 | 642.72 |
| aa_screen10 | 5 | 862632 | 721482 | 5750.88 | 4809.88 |

RGB565 (`-DSVF_TARGETS=0x08`):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| syl_ga | 100 | 6892 | 5284 | 45.95 | 35.23 |
| syl_bwelk | 100 | 8685 | 6576 | 57.90 | 43.84 |
| compose_bwelk | 100 | 2388 | 1949 | 15.92 | 12.99 |
| screen32 | 20 | 218445 | 168782 | 1456.30 | 1125.22 |
| line8 | 100 | 52631 | 40108 | 350.87 | 267.39 |
| aa_syl_ga | 100 | 12053 | 10069 | 80.35 | 67.13 |
| aa_syl_bwelk | 100 | 13909 | 11100 | 92.73 | 74.00 |
| aa_line12 | 20 | 117649 | 97445 | 784.32 | 649.63 |
| aa_screen10 | 5 | 1344606 | 825902 | 8964.04 | 5506.01 |

LINE (default `SVF_TARGETS`, scaling on; the 40 code point PAPLG16 + PAPLG18 line, 640 x 24 GRAY8, baseline 19; `line40_scaled32` at 3/2 on 960 x 36):

| case | iterations | `-Os` cycles/iteration | `-O2` cycles/iteration | `-Os` µs at 150 MHz | `-O2` µs at 150 MHz |
|---|---:|---:|---:|---:|---:|
| line40_mapped | 20 | 308369 | 268428 | 2055.79 | 1789.52 |
| line40_mapped_cache | 20 | 254516 | 218345 | 1696.77 | 1455.63 |
| line40_scaled32 | 20 | 6047381 | 4021013 | 40315.87 | 26806.75 |
| line40_stream_cold | 1 | 439273 | 361199 | 2928.49 | 2407.99 |
| line40_stream_warm | 20 | 339232 | 290664 | 2261.54 | 1937.76 |
| line40_stream_small | 20 | 375330 | 321854 | 2502.20 | 2145.69 |
| line40_stream_nocache | 2 | 348350 | 306607 | 2322.34 | 2044.05 |

## Before -> after SVF v3 (2026-10-21, 5b0cf5d -> b45e9dc)

Before = the v2 tree at 5b0cf5d (`c/build/v2/bench`, Task 1, 2026-10-21); after = the library and bench at b45e9dc (`c/build/v3/bench-x`
for the x-boxed column, `c/build/v3/bench-y` for the y-cropped one), all measured 2026-10-23 with the same runner scripts, tools and emulators. The v3 library
reads the face as it finds it; the profile each runner embeds is named above its table (`mcu-strict` for every MCU runner, `wasm` for run-wasm, `dos` for
run-dos, which is svf-fonts' own DOS demo (ScummVM's DOS data ships `default`), `default` for run-host). The two v3 columns differ only in the `mcu-strict` box policy
(`BENCH_BOX=y` for the y-cropped run, MCU runners only; the other targets have no y-cropped run and show `-`). `ratio` = v3 x-boxed / v2: below 1 is faster.
Every v3 and v2 checksum is the one in `c/bench/sums.py` (`ok`); the cases are the ones of the results above, `layout_probe` (new in v3) left out.
Pico and Uno in µs of emulated time, DOS in µs of DOSBox-X time, ESP32-C3, ESP32-S3 and the QEMU Cortex-M33 in instructions per iteration (not time), the two
rp2350js cores in rp2350js cycles per iteration, WASM and host in µs of host CPU time. Kinds and `-Os`/`-O2` as in the sections above.

### Pico (µs emulated, rp2040js 125 MHz; profile `mcu-strict`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 50.68 | 49.43 | 51.45 | 0.98x |
| MONO_PAGE `-Os` syl_bwelk | 61.95 | 60.48 | 61.13 | 0.98x |
| MONO_PAGE `-Os` compose_bwelk | 28.82 | 27.35 | 28.00 | 0.95x |
| MONO_PAGE `-Os` screen32 | 1618.94 | 1565.29 | 1605.42 | 0.97x |
| MONO_PAGE `-Os` line8 | 383.37 | 372.96 | 382.66 | 0.97x |
| MONO_PAGE `-O2` syl_ga | 43.62 | 40.11 | 41.77 | 0.92x |
| MONO_PAGE `-O2` syl_bwelk | 53.87 | 48.96 | 49.46 | 0.91x |
| MONO_PAGE `-O2` compose_bwelk | 27.91 | 23.00 | 23.50 | 0.82x |
| MONO_PAGE `-O2` screen32 | 1413.76 | 1272.94 | 1305.41 | 0.90x |
| MONO_PAGE `-O2` line8 | 332.90 | 300.90 | 308.68 | 0.90x |
| GRAY8 `-Os` syl_ga | 66.20 | 64.95 | 66.97 | 0.98x |
| GRAY8 `-Os` syl_bwelk | 85.30 | 83.83 | 84.48 | 0.98x |
| GRAY8 `-Os` compose_bwelk | 28.82 | 27.35 | 28.00 | 0.95x |
| GRAY8 `-Os` screen32 | 2573.79 | 2520.14 | 2560.27 | 0.98x |
| GRAY8 `-Os` line8 | 516.08 | 505.67 | 515.37 | 0.98x |
| GRAY8 `-Os` aa_syl_ga | 175.22 | 131.52 | 135.95 | 0.75x |
| GRAY8 `-Os` aa_syl_bwelk | 241.65 | 163.70 | 163.94 | 0.68x |
| GRAY8 `-Os` aa_line12 | 1799.03 | 1303.69 | 1332.12 | 0.72x |
| GRAY8 `-Os` aa_screen10 | 16142.60 | 12927.46 | 13115.01 | 0.80x |
| GRAY8 `-O2` syl_ga | 59.02 | 55.52 | 57.18 | 0.94x |
| GRAY8 `-O2` syl_bwelk | 75.42 | 70.51 | 71.02 | 0.93x |
| GRAY8 `-O2` compose_bwelk | 27.91 | 23.00 | 23.50 | 0.82x |
| GRAY8 `-O2` screen32 | 2363.96 | 2223.13 | 2255.60 | 0.94x |
| GRAY8 `-O2` line8 | 462.78 | 430.79 | 438.57 | 0.93x |
| GRAY8 `-O2` aa_syl_ga | 139.44 | 118.34 | 122.06 | 0.85x |
| GRAY8 `-O2` aa_syl_bwelk | 186.64 | 147.69 | 148.01 | 0.79x |
| GRAY8 `-O2` aa_line12 | 1432.26 | 1183.54 | 1207.78 | 0.83x |
| GRAY8 `-O2` aa_screen10 | 13695.55 | 12072.64 | 12263.15 | 0.88x |
| RGB565 `-Os` syl_ga | 74.15 | 72.90 | 74.92 | 0.98x |
| RGB565 `-Os` syl_bwelk | 94.97 | 93.50 | 94.14 | 0.98x |
| RGB565 `-Os` compose_bwelk | 28.82 | 27.35 | 28.00 | 0.95x |
| RGB565 `-Os` screen32 | 3365.38 | 3311.74 | 3351.86 | 0.98x |
| RGB565 `-Os` line8 | 583.54 | 573.13 | 582.82 | 0.98x |
| RGB565 `-Os` aa_syl_ga | 190.60 | 146.90 | 151.33 | 0.77x |
| RGB565 `-Os` aa_syl_bwelk | 263.75 | 185.80 | 186.04 | 0.70x |
| RGB565 `-Os` aa_line12 | 1985.58 | 1490.25 | 1518.68 | 0.75x |
| RGB565 `-Os` aa_screen10 | 17834.48 | 14619.34 | 14806.89 | 0.82x |
| RGB565 `-O2` syl_ga | 68.03 | 64.53 | 66.18 | 0.95x |
| RGB565 `-O2` syl_bwelk | 86.05 | 81.14 | 81.64 | 0.94x |
| RGB565 `-O2` compose_bwelk | 27.91 | 23.00 | 23.50 | 0.82x |
| RGB565 `-O2` screen32 | 3190.28 | 3049.45 | 3081.92 | 0.96x |
| RGB565 `-O2` line8 | 538.46 | 506.46 | 514.23 | 0.94x |
| RGB565 `-O2` aa_syl_ga | 151.46 | 130.36 | 134.09 | 0.86x |
| RGB565 `-O2` aa_syl_bwelk | 204.29 | 165.34 | 165.66 | 0.81x |
| RGB565 `-O2` aa_line12 | 1580.99 | 1332.26 | 1356.51 | 0.84x |
| RGB565 `-O2` aa_screen10 | 14655.48 | 13032.57 | 13223.08 | 0.89x |

### Uno (µs emulated, simavr 16 MHz, `-Os`; profile `mcu-strict`, built `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| syl_ga | 1162.70 | 1075.51 | 1113.95 | 0.93x |
| syl_bwelk | 1371.95 | 1257.08 | 1268.14 | 0.92x |
| compose_bwelk | 626.63 | 525.88 | 536.94 | 0.84x |
| screen32 | 35669.88 | 32707.81 | 33450.50 | 0.92x |

Flash (bench build `-DSVF_TARGETS=0x1F`): v2 31302 B (face 12921 B), v3 x-boxed 27434 B (face 8716 B), v3 y-cropped 28854 B (face 10136 B); RAM 1220, 1223 and 1223 B.

### DOS (µs emulated, DOSBox-X 486DX2-66 and 486DX-33 presets; profile `dos`; word-store build, the `_bytes` builds are in the packed-kinds table)

Note on the "v3 (4539e42)" column of the DOS tables in this section: 20 of its values are the published v3 numbers (the tables of the SVF v3 section), not a re-run of 4539e42; they differ from the v3base re-run (`c/build/bench/before`) by at most one `uclock()` tick (0.84 µs), and no ratio changes.

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| DX2-66 line40_mapped | 15190.92 | 12450.54 | - | 0.82x |
| DX2-66 line40_mapped_cache | 9958.11 | 9320.32 | - | 0.94x |
| DX2-66 line40_scaled32 | 224678.24 | 221937.88 | - | 0.99x |
| DX2-66 line40_indexed8 | 14764.18 | 12023.82 | - | 0.81x |
| DX2-66 line40_rgb555 | 14724.42 | 11983.84 | - | 0.81x |
| DX2-66 line40_rgb565 | 14699.27 | 11958.48 | - | 0.81x |
| DX2-66 line40_xrgb8888 | 16212.04 | 13471.46 | - | 0.83x |
| DX2-66 line40_rgb888 | 16458.41 | 13717.86 | - | 0.83x |
| DX2-66 line40_24_indexed8 | 20568.77 | 16155.00 | - | 0.79x |
| DX2-66 line40_24_rgb555 | 20160.48 | 15746.88 | - | 0.78x |
| DX2-66 line40_24_rgb565 | 20135.29 | 15721.72 | - | 0.78x |
| DX2-66 line40_24_xrgb8888 | 22705.21 | 18291.61 | - | 0.81x |
| DX2-66 line40_24_rgb888 | 23097.20 | 18683.43 | - | 0.81x |
| DX2-66 line40_24m_indexed8 | 13229.27 | 12939.57 | - | 0.98x |
| DX2-66 line40_24m_rgb565 | 12226.17 | 11936.24 | - | 0.98x |
| DX2-66 line40_24m_xrgb8888 | 14306.41 | 14016.66 | - | 0.98x |
| DX2-66 line40_stream_cold | 29350.98 | 23624.26 | - | 0.80x |
| DX2-66 line40_stream_warm | 15052.78 | 13392.58 | - | 0.89x |
| DX2-66 line40_stream_small | 28789.99 | 20751.49 | - | 0.72x |
| DX2-66 line40_stream_nocache | 24938.23 | 22932.50 | - | 0.92x |
| DX-33 line40_mapped | 30246.15 | 24789.72 | - | 0.82x |
| DX-33 line40_mapped_cache | 19827.08 | 18557.15 | - | 0.94x |
| DX-33 line40_scaled32 | 447348.30 | 441891.87 | - | 0.99x |
| DX-33 line40_indexed8 | 29396.60 | 23940.14 | - | 0.81x |
| DX-33 line40_rgb555 | 29317.07 | 23860.59 | - | 0.81x |
| DX-33 line40_rgb565 | 29266.53 | 23810.15 | - | 0.81x |
| DX-33 line40_xrgb8888 | 32278.82 | 26822.36 | - | 0.83x |
| DX-33 line40_rgb888 | 32769.72 | 27313.26 | - | 0.83x |
| DX-33 line40_24_indexed8 | 40953.50 | 32165.42 | - | 0.79x |
| DX-33 line40_24_rgb555 | 40140.72 | 31352.62 | - | 0.78x |
| DX-33 line40_24_rgb565 | 40090.92 | 31302.85 | - | 0.78x |
| DX-33 line40_24_xrgb8888 | 45207.65 | 36419.60 | - | 0.81x |
| DX-33 line40_24_rgb888 | 45988.05 | 37199.97 | - | 0.81x |
| DX-33 line40_24m_indexed8 | 26340.32 | 25763.52 | - | 0.98x |
| DX-33 line40_24m_rgb565 | 24342.56 | 23765.85 | - | 0.98x |
| DX-33 line40_24m_xrgb8888 | 28484.89 | 27907.74 | - | 0.98x |
| DX-33 line40_stream_cold | 50631.09 | 41763.19 | - | 0.82x |
| DX-33 line40_stream_warm | 29971.17 | 26665.38 | - | 0.89x |
| DX-33 line40_stream_small | 49305.97 | 37177.19 | - | 0.75x |
| DX-33 line40_stream_nocache | 45743.98 | 42140.33 | - | 0.92x |

### ESP32-C3 (instructions per iteration, QEMU rdinstret; not time; profile `mcu-strict`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3619 | 3360 | 3519 | 0.93x |
| MONO_PAGE `-Os` syl_bwelk | 4474 | 4123 | 4171 | 0.92x |
| MONO_PAGE `-Os` compose_bwelk | 2153 | 1800 | 1848 | 0.84x |
| MONO_PAGE `-Os` screen32 | 108694 | 98326 | 101436 | 0.90x |
| MONO_PAGE `-Os` line8 | 26596 | 24283 | 25027 | 0.91x |
| MONO_PAGE `-O2` syl_ga | 2996 | 2895 | 3031 | 0.97x |
| MONO_PAGE `-O2` syl_bwelk | 3667 | 3546 | 3587 | 0.97x |
| MONO_PAGE `-O2` compose_bwelk | 1688 | 1567 | 1608 | 0.93x |
| MONO_PAGE `-O2` screen32 | 89886 | 85672 | 88332 | 0.95x |
| MONO_PAGE `-O2` line8 | 21990 | 21149 | 21785 | 0.96x |
| GRAY8 `-Os` syl_ga | 4204 | 3945 | 4104 | 0.94x |
| GRAY8 `-Os` syl_bwelk | 5539 | 5188 | 5236 | 0.94x |
| GRAY8 `-Os` compose_bwelk | 2153 | 1800 | 1848 | 0.84x |
| GRAY8 `-Os` screen32 | 130024 | 119655 | 122766 | 0.92x |
| GRAY8 `-Os` line8 | 31901 | 29588 | 30332 | 0.93x |
| GRAY8 `-Os` aa_syl_ga | 10267 | 8547 | 8813 | 0.83x |
| GRAY8 `-Os` aa_syl_bwelk | 13904 | 10679 | 10652 | 0.77x |
| GRAY8 `-Os` aa_line12 | 103885 | 81515 | 83119 | 0.78x |
| GRAY8 `-Os` aa_screen10 | 746276 | 598670 | 607807 | 0.80x |
| GRAY8 `-O2` syl_ga | 3860 | 3759 | 3895 | 0.97x |
| GRAY8 `-O2` syl_bwelk | 4892 | 4771 | 4812 | 0.98x |
| GRAY8 `-O2` compose_bwelk | 1688 | 1567 | 1608 | 0.93x |
| GRAY8 `-O2` screen32 | 119742 | 115528 | 118188 | 0.96x |
| GRAY8 `-O2` line8 | 29399 | 28558 | 29194 | 0.97x |
| GRAY8 `-O2` aa_syl_ga | 9538 | 8182 | 8399 | 0.86x |
| GRAY8 `-O2` aa_syl_bwelk | 12839 | 10195 | 10165 | 0.79x |
| GRAY8 `-O2` aa_line12 | 98225 | 79793 | 81083 | 0.81x |
| GRAY8 `-O2` aa_screen10 | 707806 | 586868 | 594643 | 0.83x |
| RGB565 `-Os` syl_ga | 4631 | 4372 | 4531 | 0.94x |
| RGB565 `-Os` syl_bwelk | 6032 | 5681 | 5729 | 0.94x |
| RGB565 `-Os` compose_bwelk | 2153 | 1800 | 1848 | 0.84x |
| RGB565 `-Os` screen32 | 145725 | 135356 | 138467 | 0.93x |
| RGB565 `-Os` line8 | 35362 | 33049 | 33793 | 0.93x |
| RGB565 `-Os` aa_syl_ga | 10790 | 9070 | 9336 | 0.84x |
| RGB565 `-Os` aa_syl_bwelk | 14794 | 11569 | 11542 | 0.78x |
| RGB565 `-Os` aa_line12 | 110807 | 88437 | 90041 | 0.80x |
| RGB565 `-Os` aa_screen10 | 999965 | 852359 | 861496 | 0.85x |
| RGB565 `-O2` syl_ga | 3947 | 3846 | 3982 | 0.97x |
| RGB565 `-O2` syl_bwelk | 5046 | 4925 | 4966 | 0.98x |
| RGB565 `-O2` compose_bwelk | 1688 | 1567 | 1608 | 0.93x |
| RGB565 `-O2` screen32 | 125002 | 120788 | 123448 | 0.97x |
| RGB565 `-O2` line8 | 30206 | 29365 | 30001 | 0.97x |
| RGB565 `-O2` aa_syl_ga | 9517 | 8161 | 8378 | 0.86x |
| RGB565 `-O2` aa_syl_bwelk | 12883 | 10239 | 10209 | 0.79x |
| RGB565 `-O2` aa_line12 | 99132 | 80700 | 81990 | 0.81x |
| RGB565 `-O2` aa_screen10 | 774271 | 653333 | 661108 | 0.84x |

### ESP32-S3 (instructions per iteration, QEMU core-0 ICOUNT; not time; profile `mcu-strict`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3460 | 3152 | 3305 | 0.91x |
| MONO_PAGE `-Os` syl_bwelk | 4264 | 3836 | 3881 | 0.90x |
| MONO_PAGE `-Os` compose_bwelk | 2009 | 1582 | 1627 | 0.79x |
| MONO_PAGE `-Os` screen32 | 106712 | 94374 | 97347 | 0.88x |
| MONO_PAGE `-Os` line8 | 26119 | 23328 | 24036 | 0.89x |
| MONO_PAGE `-O2` syl_ga | 2753 | 2509 | 2649 | 0.91x |
| MONO_PAGE `-O2` syl_bwelk | 3392 | 3078 | 3121 | 0.91x |
| MONO_PAGE `-O2` compose_bwelk | 1625 | 1311 | 1354 | 0.81x |
| MONO_PAGE `-O2` screen32 | 85448 | 76118 | 78870 | 0.89x |
| MONO_PAGE `-O2` line8 | 20723 | 18610 | 19270 | 0.90x |
| GRAY8 `-Os` syl_ga | 3632 | 3324 | 3477 | 0.92x |
| GRAY8 `-Os` syl_bwelk | 4852 | 4424 | 4469 | 0.91x |
| GRAY8 `-Os` compose_bwelk | 2009 | 1582 | 1627 | 0.79x |
| GRAY8 `-Os` screen32 | 115754 | 103416 | 106389 | 0.89x |
| GRAY8 `-Os` line8 | 28103 | 25312 | 26020 | 0.90x |
| GRAY8 `-Os` aa_syl_ga | 10332 | 8724 | 8910 | 0.84x |
| GRAY8 `-Os` aa_syl_bwelk | 14142 | 11109 | 11055 | 0.79x |
| GRAY8 `-Os` aa_line12 | 105649 | 84888 | 85924 | 0.80x |
| GRAY8 `-Os` aa_screen10 | 763519 | 627385 | 630493 | 0.82x |
| GRAY8 `-O2` syl_ga | 3161 | 2917 | 3057 | 0.92x |
| GRAY8 `-O2` syl_bwelk | 4005 | 3691 | 3734 | 0.92x |
| GRAY8 `-O2` compose_bwelk | 1625 | 1311 | 1354 | 0.81x |
| GRAY8 `-O2` screen32 | 105605 | 96275 | 99027 | 0.91x |
| GRAY8 `-O2` line8 | 24202 | 22089 | 22749 | 0.91x |
| GRAY8 `-O2` aa_syl_ga | 9111 | 7642 | 7558 | 0.84x |
| GRAY8 `-O2` aa_syl_bwelk | 12372 | 9494 | 9311 | 0.77x |
| GRAY8 `-O2` aa_line12 | 94585 | 75152 | 74183 | 0.79x |
| GRAY8 `-O2` aa_screen10 | 694139 | 566097 | 557425 | 0.82x |
| RGB565 `-Os` syl_ga | 4008 | 3700 | 3853 | 0.92x |
| RGB565 `-Os` syl_bwelk | 5226 | 4798 | 4843 | 0.92x |
| RGB565 `-Os` compose_bwelk | 2009 | 1582 | 1627 | 0.79x |
| RGB565 `-Os` screen32 | 129496 | 117158 | 120131 | 0.90x |
| RGB565 `-Os` line8 | 30986 | 28195 | 28903 | 0.91x |
| RGB565 `-Os` aa_syl_ga | 9911 | 8303 | 8489 | 0.84x |
| RGB565 `-Os` aa_syl_bwelk | 13658 | 10625 | 10571 | 0.78x |
| RGB565 `-Os` aa_line12 | 102482 | 81720 | 82756 | 0.80x |
| RGB565 `-Os` aa_screen10 | 883641 | 747507 | 750615 | 0.85x |
| RGB565 `-O2` syl_ga | 3506 | 3262 | 3402 | 0.93x |
| RGB565 `-O2` syl_bwelk | 4429 | 4115 | 4158 | 0.93x |
| RGB565 `-O2` compose_bwelk | 1625 | 1311 | 1354 | 0.81x |
| RGB565 `-O2` screen32 | 125040 | 115710 | 118462 | 0.93x |
| RGB565 `-O2` line8 | 27064 | 24951 | 25611 | 0.92x |
| RGB565 `-O2` aa_syl_ga | 9346 | 7877 | 7793 | 0.84x |
| RGB565 `-O2` aa_syl_bwelk | 12760 | 9882 | 9699 | 0.77x |
| RGB565 `-O2` aa_line12 | 97892 | 78460 | 77490 | 0.80x |
| RGB565 `-O2` aa_screen10 | 736676 | 608634 | 599962 | 0.83x |

### Cortex-M33 under QEMU (instructions per iteration, SysTick x 50; not time; profile `mcu-strict`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3420 | 3308 | 3398 | 0.97x |
| MONO_PAGE `-Os` syl_bwelk | 4065 | 3886 | 3918 | 0.96x |
| MONO_PAGE `-Os` compose_bwelk | 1718 | 1540 | 1572 | 0.90x |
| MONO_PAGE `-Os` screen32 | 108275 | 103062 | 104875 | 0.95x |
| MONO_PAGE `-Os` line8 | 25648 | 24524 | 24968 | 0.96x |
| MONO_PAGE `-O2` syl_ga | 2688 | 2602 | 2706 | 0.97x |
| MONO_PAGE `-O2` syl_bwelk | 3238 | 3120 | 3154 | 0.96x |
| MONO_PAGE `-O2` compose_bwelk | 1489 | 1370 | 1404 | 0.92x |
| MONO_PAGE `-O2` screen32 | 85758 | 81918 | 83998 | 0.96x |
| MONO_PAGE `-O2` line8 | 20080 | 19296 | 19800 | 0.96x |
| GRAY8 `-Os` syl_ga | 4498 | 4385 | 4474 | 0.97x |
| GRAY8 `-Os` syl_bwelk | 5724 | 5546 | 5576 | 0.97x |
| GRAY8 `-Os` compose_bwelk | 1718 | 1540 | 1571 | 0.90x |
| GRAY8 `-Os` screen32 | 170588 | 165375 | 167188 | 0.97x |
| GRAY8 `-Os` line8 | 34790 | 33668 | 34112 | 0.97x |
| GRAY8 `-Os` aa_syl_ga | 11080 | 8982 | 9170 | 0.81x |
| GRAY8 `-Os` aa_syl_bwelk | 15074 | 11243 | 11192 | 0.75x |
| GRAY8 `-Os` aa_line12 | 113720 | 88710 | 89768 | 0.78x |
| GRAY8 `-Os` aa_screen10 | 1023560 | 859930 | 866160 | 0.84x |
| GRAY8 `-O2` syl_ga | 4234 | 4149 | 4253 | 0.98x |
| GRAY8 `-O2` syl_bwelk | 5320 | 5200 | 5234 | 0.98x |
| GRAY8 `-O2` compose_bwelk | 1489 | 1370 | 1404 | 0.92x |
| GRAY8 `-O2` screen32 | 163348 | 159505 | 161585 | 0.98x |
| GRAY8 `-O2` line8 | 32984 | 32200 | 32704 | 0.98x |
| GRAY8 `-O2` aa_syl_ga | 10018 | 8054 | 8281 | 0.80x |
| GRAY8 `-O2` aa_syl_bwelk | 13569 | 9964 | 9950 | 0.73x |
| GRAY8 `-O2` aa_line12 | 103682 | 80415 | 81810 | 0.78x |
| GRAY8 `-O2` aa_screen10 | 950960 | 798440 | 808040 | 0.84x |
| RGB565 `-Os` syl_ga | 4824 | 4712 | 4800 | 0.98x |
| RGB565 `-Os` syl_bwelk | 6092 | 5914 | 5944 | 0.97x |
| RGB565 `-Os` compose_bwelk | 1718 | 1540 | 1572 | 0.90x |
| RGB565 `-Os` screen32 | 213722 | 208512 | 210325 | 0.98x |
| RGB565 `-Os` line8 | 37434 | 36310 | 36754 | 0.97x |
| RGB565 `-Os` aa_syl_ga | 10906 | 8807 | 8995 | 0.81x |
| RGB565 `-Os` aa_syl_bwelk | 14960 | 11130 | 11079 | 0.74x |
| RGB565 `-Os` aa_line12 | 113548 | 88535 | 89592 | 0.78x |
| RGB565 `-Os` aa_screen10 | 1133260 | 969660 | 975900 | 0.86x |
| RGB565 `-O2` syl_ga | 3987 | 3902 | 4006 | 0.98x |
| RGB565 `-O2` syl_bwelk | 4994 | 4876 | 4909 | 0.98x |
| RGB565 `-O2` compose_bwelk | 1489 | 1370 | 1404 | 0.92x |
| RGB565 `-O2` screen32 | 188080 | 184240 | 186318 | 0.98x |
| RGB565 `-O2` line8 | 30882 | 30098 | 30601 | 0.97x |
| RGB565 `-O2` aa_syl_ga | 9650 | 7686 | 7913 | 0.80x |
| RGB565 `-O2` aa_syl_bwelk | 13080 | 9474 | 9459 | 0.72x |
| RGB565 `-O2` aa_line12 | 100520 | 77252 | 78648 | 0.77x |
| RGB565 `-O2` aa_screen10 | 781700 | 629300 | 638860 | 0.81x |
| LINE `-Os` line40_mapped | 297352 | 242390 | 243925 | 0.82x |
| LINE `-Os` line40_mapped_cache | 208180 | 199218 | 198898 | 0.96x |
| LINE `-Os` line40_scaled32 | 4467938 | 4412975 | 4414510 | 0.99x |
| LINE `-Os` line40_stream_cold | 524500 | 411450 | 436400 | 0.78x |
| LINE `-Os` line40_stream_warm | 310545 | 258785 | 261398 | 0.83x |
| LINE `-Os` line40_stream_small | 489202 | 349560 | 392075 | 0.71x |
| LINE `-Os` line40_stream_nocache | 305550 | 273725 | 274475 | 0.90x |
| LINE `-O2` line40_mapped | 276678 | 225752 | 228900 | 0.82x |
| LINE `-O2` line40_mapped_cache | 191762 | 183898 | 184568 | 0.96x |
| LINE `-O2` line40_scaled32 | 4457548 | 4406622 | 4409770 | 0.99x |
| LINE `-O2` line40_stream_cold | 481050 | 378500 | 403250 | 0.79x |
| LINE `-O2` line40_stream_warm | 282992 | 239148 | 242962 | 0.85x |
| LINE `-O2` line40_stream_small | 461408 | 327602 | 370918 | 0.71x |
| LINE `-O2` line40_stream_nocache | 286200 | 257075 | 258175 | 0.90x |

### RP2350 Hazard3 under rp2350js (cycles per iteration; profile `mcu-strict`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 4175 | 3943 | 4131 | 0.94x |
| MONO_PAGE `-Os` syl_bwelk | 5214 | 4920 | 4978 | 0.94x |
| MONO_PAGE `-Os` compose_bwelk | 2603 | 2309 | 2367 | 0.89x |
| MONO_PAGE `-Os` screen32 | 125432 | 116352 | 120052 | 0.93x |
| MONO_PAGE `-Os` line8 | 30642 | 28667 | 29555 | 0.94x |
| MONO_PAGE `-O2` syl_ga | 2980 | 2822 | 2962 | 0.95x |
| MONO_PAGE `-O2` syl_bwelk | 3597 | 3410 | 3453 | 0.95x |
| MONO_PAGE `-O2` compose_bwelk | 1623 | 1469 | 1512 | 0.91x |
| MONO_PAGE `-O2` screen32 | 89112 | 83072 | 85824 | 0.93x |
| MONO_PAGE `-O2` line8 | 21824 | 20533 | 21193 | 0.94x |
| GRAY8 `-Os` syl_ga | 5042 | 4813 | 5001 | 0.95x |
| GRAY8 `-Os` syl_bwelk | 6616 | 6325 | 6383 | 0.96x |
| GRAY8 `-Os` compose_bwelk | 2603 | 2309 | 2367 | 0.89x |
| GRAY8 `-Os` screen32 | 155372 | 146308 | 150008 | 0.94x |
| GRAY8 `-Os` line8 | 38203 | 36231 | 37119 | 0.95x |
| GRAY8 `-Os` aa_syl_ga | 12639 | 10468 | 10752 | 0.83x |
| GRAY8 `-Os` aa_syl_bwelk | 16896 | 12939 | 12891 | 0.77x |
| GRAY8 `-Os` aa_line12 | 126575 | 99655 | 101319 | 0.79x |
| GRAY8 `-Os` aa_screen10 | 897928 | 720479 | 728215 | 0.80x |
| GRAY8 `-O2` syl_ga | 4117 | 4099 | 4239 | 1.00x |
| GRAY8 `-O2` syl_bwelk | 5082 | 5084 | 5127 | 1.00x |
| GRAY8 `-O2` compose_bwelk | 1605 | 1469 | 1512 | 0.92x |
| GRAY8 `-O2` screen32 | 127548 | 126046 | 128798 | 0.99x |
| GRAY8 `-O2` line8 | 31422 | 31311 | 31971 | 1.00x |
| GRAY8 `-O2` aa_syl_ga | 9385 | 7945 | 8186 | 0.85x |
| GRAY8 `-O2` aa_syl_bwelk | 12433 | 9684 | 9642 | 0.78x |
| GRAY8 `-O2` aa_line12 | 96612 | 77598 | 79012 | 0.80x |
| GRAY8 `-O2` aa_screen10 | 688393 | 563291 | 570579 | 0.82x |
| RGB565 `-Os` syl_ga | 5646 | 5418 | 5606 | 0.96x |
| RGB565 `-Os` syl_bwelk | 7280 | 6990 | 7048 | 0.96x |
| RGB565 `-Os` compose_bwelk | 2602 | 2308 | 2366 | 0.89x |
| RGB565 `-Os` screen32 | 176805 | 167765 | 171465 | 0.95x |
| RGB565 `-Os` line8 | 43088 | 41124 | 42012 | 0.95x |
| RGB565 `-Os` aa_syl_ga | 12779 | 10601 | 10885 | 0.83x |
| RGB565 `-Os` aa_syl_bwelk | 17085 | 13121 | 13073 | 0.77x |
| RGB565 `-Os` aa_line12 | 129494 | 102562 | 104226 | 0.79x |
| RGB565 `-Os` aa_screen10 | 1187730 | 1010184 | 1017920 | 0.85x |
| RGB565 `-O2` syl_ga | 4142 | 4163 | 4303 | 1.01x |
| RGB565 `-O2` syl_bwelk | 5174 | 5215 | 5258 | 1.01x |
| RGB565 `-O2` compose_bwelk | 1605 | 1469 | 1512 | 0.92x |
| RGB565 `-O2` screen32 | 130730 | 130476 | 133228 | 1.00x |
| RGB565 `-O2` line8 | 31711 | 31911 | 32571 | 1.01x |
| RGB565 `-O2` aa_syl_ga | 9437 | 8244 | 8485 | 0.87x |
| RGB565 `-O2` aa_syl_bwelk | 12528 | 10140 | 10098 | 0.81x |
| RGB565 `-O2` aa_line12 | 97918 | 81490 | 82904 | 0.83x |
| RGB565 `-O2` aa_screen10 | 795488 | 689325 | 696613 | 0.87x |
| LINE `-Os` line40_mapped | 333062 | 260157 | 260574 | 0.78x |
| LINE `-Os` line40_mapped_cache | 229712 | 202359 | 199843 | 0.88x |
| LINE `-Os` line40_scaled32 | 6741103 | 6651758 | 6652175 | 0.99x |
| LINE `-Os` line40_stream_cold | 461881 | 377599 | 390417 | 0.82x |
| LINE `-Os` line40_stream_warm | 358991 | 287597 | 290314 | 0.80x |
| LINE `-Os` line40_stream_small | 393088 | 315625 | 327708 | 0.80x |
| LINE `-Os` line40_stream_nocache | 338260 | 291758 | 289662 | 0.86x |
| LINE `-O2` line40_mapped | 249136 | 210091 | 211370 | 0.84x |
| LINE `-O2` line40_mapped_cache | 176884 | 167340 | 166110 | 0.95x |
| LINE `-O2` line40_scaled32 | 5338646 | 5090352 | 5091631 | 0.95x |
| LINE `-O2` line40_stream_cold | 326203 | 288680 | 298471 | 0.88x |
| LINE `-O2` line40_stream_warm | 257611 | 228599 | 231153 | 0.89x |
| LINE `-O2` line40_stream_small | 292355 | 252299 | 263759 | 0.86x |
| LINE `-O2` line40_stream_nocache | 251800 | 239870 | 237596 | 0.95x |

### RP2350 Cortex-M33 under rp2350js (cycles per iteration; profile `mcu-strict`)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 5404 | 5162 | 5331 | 0.96x |
| MONO_PAGE `-Os` syl_bwelk | 6459 | 6107 | 6160 | 0.95x |
| MONO_PAGE `-Os` compose_bwelk | 2783 | 2432 | 2485 | 0.87x |
| MONO_PAGE `-Os` screen32 | 163797 | 153436 | 156777 | 0.94x |
| MONO_PAGE `-Os` line8 | 40137 | 37871 | 38675 | 0.94x |
| MONO_PAGE `-O2` syl_ga | 3917 | 3746 | 3934 | 0.96x |
| MONO_PAGE `-O2` syl_bwelk | 4733 | 4509 | 4567 | 0.95x |
| MONO_PAGE `-O2` compose_bwelk | 2163 | 1936 | 1994 | 0.90x |
| MONO_PAGE `-O2` screen32 | 118600 | 111362 | 115062 | 0.94x |
| MONO_PAGE `-O2` line8 | 29000 | 27499 | 28387 | 0.95x |
| GRAY8 `-Os` syl_ga | 6715 | 6473 | 6642 | 0.96x |
| GRAY8 `-Os` syl_bwelk | 8531 | 8179 | 8232 | 0.96x |
| GRAY8 `-Os` compose_bwelk | 2783 | 2432 | 2485 | 0.87x |
| GRAY8 `-Os` screen32 | 209424 | 199063 | 202404 | 0.95x |
| GRAY8 `-Os` line8 | 51338 | 49072 | 49876 | 0.96x |
| GRAY8 `-Os` aa_syl_ga | 14492 | 12140 | 12529 | 0.84x |
| GRAY8 `-Os` aa_syl_bwelk | 19256 | 14940 | 14934 | 0.78x |
| GRAY8 `-Os` aa_line12 | 148217 | 118174 | 120597 | 0.80x |
| GRAY8 `-Os` aa_screen10 | 1078992 | 881713 | 892296 | 0.82x |
| GRAY8 `-O2` syl_ga | 5652 | 5481 | 5669 | 0.97x |
| GRAY8 `-O2` syl_bwelk | 7079 | 6855 | 6913 | 0.97x |
| GRAY8 `-O2` compose_bwelk | 2163 | 1936 | 1994 | 0.90x |
| GRAY8 `-O2` screen32 | 178368 | 171130 | 174830 | 0.96x |
| GRAY8 `-O2` line8 | 43555 | 42054 | 42942 | 0.97x |
| GRAY8 `-O2` aa_syl_ga | 12244 | 10111 | 10584 | 0.83x |
| GRAY8 `-O2` aa_syl_bwelk | 16392 | 12439 | 12514 | 0.76x |
| GRAY8 `-O2` aa_line12 | 126913 | 99534 | 102696 | 0.78x |
| GRAY8 `-O2` aa_screen10 | 927828 | 747395 | 764951 | 0.81x |
| RGB565 `-Os` syl_ga | 7164 | 6922 | 7091 | 0.97x |
| RGB565 `-Os` syl_bwelk | 9079 | 8727 | 8780 | 0.96x |
| RGB565 `-Os` compose_bwelk | 2783 | 2432 | 2485 | 0.87x |
| RGB565 `-Os` screen32 | 230009 | 219648 | 222989 | 0.95x |
| RGB565 `-Os` line8 | 55189 | 52923 | 53727 | 0.96x |
| RGB565 `-Os` aa_syl_ga | 14562 | 12210 | 12599 | 0.84x |
| RGB565 `-Os` aa_syl_bwelk | 19523 | 15207 | 15201 | 0.78x |
| RGB565 `-Os` aa_line12 | 151072 | 121029 | 123452 | 0.80x |
| RGB565 `-Os` aa_screen10 | 1568462 | 1371183 | 1381766 | 0.87x |
| RGB565 `-O2` syl_ga | 5406 | 5235 | 5423 | 0.97x |
| RGB565 `-O2` syl_bwelk | 6761 | 6537 | 6595 | 0.97x |
| RGB565 `-O2` compose_bwelk | 2163 | 1936 | 1994 | 0.90x |
| RGB565 `-O2` screen32 | 175340 | 168102 | 171802 | 0.96x |
| RGB565 `-O2` line8 | 41431 | 39930 | 40818 | 0.96x |
| RGB565 `-O2` aa_syl_ga | 12178 | 10045 | 10518 | 0.82x |
| RGB565 `-O2` aa_syl_bwelk | 16314 | 12361 | 12436 | 0.76x |
| RGB565 `-O2` aa_line12 | 127136 | 99757 | 102919 | 0.78x |
| RGB565 `-O2` aa_screen10 | 1026235 | 845802 | 863358 | 0.82x |
| LINE `-Os` line40_mapped | 397236 | 323347 | 324038 | 0.81x |
| LINE `-Os` line40_mapped_cache | 283300 | 261333 | 257717 | 0.92x |
| LINE `-Os` line40_scaled32 | 7628408 | 7554519 | 7555210 | 0.99x |
| LINE `-Os` line40_stream_cold | 527022 | 454251 | 468733 | 0.86x |
| LINE `-Os` line40_stream_warm | 411160 | 354210 | 357066 | 0.86x |
| LINE `-Os` line40_stream_small | 462950 | 390308 | 406584 | 0.84x |
| LINE `-Os` line40_stream_nocache | 386866 | 363328 | 356632 | 0.94x |
| LINE `-O2` line40_mapped | 348951 | 280264 | 284184 | 0.80x |
| LINE `-O2` line40_mapped_cache | 245360 | 223784 | 222023 | 0.91x |
| LINE `-O2` line40_scaled32 | 7250256 | 7181569 | 7185489 | 0.99x |
| LINE `-O2` line40_stream_cold | 428715 | 373035 | 386643 | 0.87x |
| LINE `-O2` line40_stream_warm | 346428 | 302500 | 307326 | 0.87x |
| LINE `-O2` line40_stream_small | 397702 | 333690 | 351153 | 0.84x |
| LINE `-O2` line40_stream_nocache | 338615 | 318443 | 312898 | 0.94x |

### WASM (µs of host CPU time, node/V8; profile `wasm`; the median of four runs, because one run of `line40_mapped` read 18.73 µs and the next three 13.35 to 14.61)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| line40_mapped | 14.19 | 14.01 | - | 0.99x |
| line40_mapped_cache | 9.16 | 8.99 | - | 0.98x |
| line40_scaled32 | 192.49 | 189.30 | - | 0.98x |
| line40_stream_cold | 66.34 | 81.00 | - | 1.22x |
| line40_stream_warm | 12.83 | 12.07 | - | 0.94x |
| line40_stream_small | 13.61 | 12.74 | - | 0.94x |
| line40_stream_nocache | 12.63 | 12.82 | - | 1.02x |

The picker's real case (F27), the same run with `BENCH_PROFILE=default` (the face embedded as `svf/` ships it, aligned records, u32 offsets), the median of three runs:

| case | v2 | v3 `wasm` profile | v3 `default` profile | `default` / v2 |
|---|---:|---:|---:|---:|
| line40_mapped | 14.19 | 14.01 | 13.61 | 0.96x |
| line40_mapped_cache | 9.16 | 8.99 | 8.99 | 0.98x |
| line40_scaled32 | 192.49 | 189.30 | 190.41 | 0.99x |
| line40_stream_cold | 66.34 | 81.00 | 67.41 | 1.02x |
| line40_stream_warm | 12.83 | 12.07 | 11.89 | 0.93x |
| line40_stream_small | 13.61 | 12.74 | 12.35 | 0.91x |
| line40_stream_nocache | 12.63 | 12.82 | 12.88 | 1.02x |

### Host (µs of host CPU time; profile `default`; one run each on a shared machine, repeated runs differ by up to 50 %)

| case | v2 | v3 x-boxed | v3 y-cropped | ratio |
|---|---:|---:|---:|---:|
| line40_mapped | 9.75 | 10.00 | - | 1.03x |
| line40_mapped_cache | 6.30 | 6.19 | - | 0.98x |
| line40_scaled32 | 165.37 | 171.36 | - | 1.04x |
| line40_indexed8 | 11.17 | 8.58 | - | 0.77x |
| line40_rgb555 | 10.49 | 8.38 | - | 0.80x |
| line40_rgb565 | 10.47 | 8.32 | - | 0.79x |
| line40_xrgb8888 | 12.24 | 10.06 | - | 0.82x |
| line40_rgb888 | 12.38 | 10.39 | - | 0.84x |
| line40_24_indexed8 | 14.74 | 11.30 | - | 0.77x |
| line40_24_rgb555 | 14.88 | 11.03 | - | 0.74x |
| line40_24_rgb565 | 14.86 | 11.04 | - | 0.74x |
| line40_24_xrgb8888 | 17.43 | 13.52 | - | 0.78x |
| line40_24_rgb888 | 18.05 | 14.27 | - | 0.79x |
| line40_24m_indexed8 | 10.01 | 8.78 | - | 0.88x |
| line40_24m_rgb565 | 8.39 | 7.67 | - | 0.91x |
| line40_24m_xrgb8888 | 11.54 | 11.16 | - | 0.97x |
| line40_stream_cold | 42.28 | 33.18 | - | 0.78x |
| line40_stream_warm | 10.08 | 8.64 | - | 0.86x |
| line40_stream_small | 10.48 | 9.00 | - | 0.86x |
| line40_stream_nocache | 9.94 | 8.98 | - | 0.90x |

**Card t_fed9917c ("blit may get slower"): it did not.** In v3 every case is faster than v2 or within 1 % of it on every target
measured, except four rp2350js Hazard3 `-O2` rows of the GRAY8 and RGB565 builds (`syl_bwelk` GRAY8 +0.04 %, RGB565 `syl_ga` +0.5 %, `syl_bwelk` +0.8 %,
`line8` +0.6 %), which are instruction-count noise on a core with no other change. Per target, `-Os` / `-O2`, MONO_PAGE build, x-boxed against v2
(a syllable is 2 pieces for `syl_ga` and 3 for `syl_bwelk`; the line cases are the 8-syllable `line8` and the 40-code point `line40` lines):
Pico `syl_ga` -2 % / -8 %, `syl_bwelk` -2 % / -9 %, `line8` -3 % / -10 %; ESP32-C3 syllables -7 to -8 % / -3 %, `line8` -9 % / -4 %; ESP32-S3
syllables -9 to -10 % / -9 %, `line8` -11 % / -10 %; Cortex-M33 under QEMU syllables -3 to -4 % / -3 to -4 %, `line8` -4 %, `line40_mapped` -18 % / -18 %,
`line40_stream_warm` -17 % / -15 %; Hazard3 syllables -6 % / -5 %, `line40_mapped` -22 % / -16 %, `line40_stream_warm` -20 % / -11 %; rp2350js
Cortex-M33 syllables -4 to -5 % / -4 to -5 %, `line40_mapped` -19 % / -20 %, `line40_stream_warm` -14 % / -13 %; DOS 486DX2-66 `line40_mapped`
-18 % (15190.9 to 12450.5 µs), `line40_stream_warm` -11 % (15052.6 to 13392.6 µs), `line40_stream_cold` -20 %, the DX-33 preset the same ratios; WASM and host
within the run-to-run noise (the median of four WASM runs: mapped -1 %, stream_warm -6 %, stream_cold +22 % on a single-iteration case that
reads 65 to 85 µs from run to run). The scaled line (`line40_scaled32`) moves by 1 to 5 %. The 2 bpp, GRAY8 and RGB565 rows (the `aa_*` cases) are faster or equal as well,
by the ratios of the tables. The cause was not isolated in this task; a plausible one is that records hold only the ink box, so a piece copies and merges fewer bytes
(not measured separately), and the blit itself is unchanged.
Absolute budgets, Pico MONO_PAGE `-Os`: `syl_ga` 49.43 µs now meets 50 µs (v2: 50.68 µs, missed by 1.4 %); `syl_bwelk` 60.48 µs still misses (v2: 61.95 µs).

**The `mcu-strict` box policy: x stays (decided 2026-10-23).** The rule of the plan: y wins only if it is faster on `syl_bwelk` by more than 5 % (the Pico budget row);
otherwise x. Pico MONO_PAGE `-Os`, cycles per iteration (µs at 125 MHz), x-boxed against y-cropped: `syl_ga` 6179 (49.43) against 6431 (51.45); `syl_bwelk` 7560
(60.48) against 7641 (61.13); `compose_bwelk` 3419 (27.35) against 3500 (28.00). The y-cropped face is slower on all three, not faster (`syl_bwelk` +1.1 %), and
larger: the embedded `mcu-strict` faces are 8716 B (HGKEY6J), 7460 B (PAPLG16) and 67200 B (PAPLG18) x-boxed against 10136 B (+16.3 %), 11124 B (+49.1 %) and
85092 B (+26.6 %) y-cropped; the Uno bench build links in 27434 B of flash with the x-boxed face and 28854 B with the y-cropped one. y-cropped is also slower on
the other MCU runs (ESP32-C3 `syl_ga` -Os 3519 against 3360 instructions, Hazard3 4131 against 3943 cycles); of the MCU result rows, 33 are faster y-cropped, each by under 2 %, none of
them a 1 bpp MONO_PAGE row (`aa_*` 2 bpp syllables and the cached and uncached line cases). So `PROFILES["mcu-strict"]` keeps `box = "x"`, `tools/jamoset.py` is unchanged, and the
Task 7 step 4, `c/ports/FACES.md` and the gated tables of `SIZES.md` stay as they are.

## Before -> after the C speedups (2026-10-23, 4539e42 -> 8bff82e)

### Pico (µs emulated, rp2040js 125 MHz; profile `mcu-strict`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 49.43 | 49.14 | 0.99x |
| MONO_PAGE `-Os` syl_bwelk | 60.48 | 60.00 | 0.99x |
| MONO_PAGE `-Os` compose_bwelk | 27.35 | 27.00 | 0.99x |
| MONO_PAGE `-Os` screen32 | 1565.29 | 1556.66 | 0.99x |
| MONO_PAGE `-Os` line8 | 372.96 | 370.94 | 0.99x |
| MONO_PAGE `-O2` syl_ga | 40.11 | 39.82 | 0.99x |
| MONO_PAGE `-O2` syl_bwelk | 48.96 | 48.48 | 0.99x |
| MONO_PAGE `-O2` compose_bwelk | 23.00 | 22.65 | 0.98x |
| MONO_PAGE `-O2` screen32 | 1272.94 | 1264.31 | 0.99x |
| MONO_PAGE `-O2` line8 | 300.90 | 298.89 | 0.99x |
| GRAY8 `-Os` syl_ga | 64.95 | 59.58 | 0.92x |
| GRAY8 `-Os` syl_bwelk | 83.83 | 74.98 | 0.89x |
| GRAY8 `-Os` compose_bwelk | 27.35 | 27.00 | 0.99x |
| GRAY8 `-Os` screen32 | 2520.14 | 2341.82 | 0.93x |
| GRAY8 `-Os` line8 | 505.67 | 458.34 | 0.91x |
| GRAY8 `-Os` aa_syl_ga | 131.52 | 127.35 | 0.97x |
| GRAY8 `-Os` aa_syl_bwelk | 163.70 | 157.96 | 0.96x |
| GRAY8 `-Os` aa_line12 | 1303.69 | 1262.20 | 0.97x |
| GRAY8 `-Os` aa_screen10 | 12927.46 | 12642.25 | 0.98x |
| GRAY8 `-O2` syl_ga | 55.52 | 52.54 | 0.95x |
| GRAY8 `-O2` syl_bwelk | 70.51 | 64.74 | 0.92x |
| GRAY8 `-O2` compose_bwelk | 23.00 | 22.65 | 0.98x |
| GRAY8 `-O2` screen32 | 2223.13 | 2124.52 | 0.96x |
| GRAY8 `-O2` line8 | 430.79 | 403.85 | 0.94x |
| GRAY8 `-O2` aa_syl_ga | 118.34 | 112.70 | 0.95x |
| GRAY8 `-O2` aa_syl_bwelk | 147.69 | 138.82 | 0.94x |
| GRAY8 `-O2` aa_line12 | 1183.54 | 1131.39 | 0.96x |
| GRAY8 `-O2` aa_screen10 | 12072.64 | 11688.47 | 0.97x |
| RGB565 `-Os` syl_ga | 72.90 | 72.62 | 1.00x |
| RGB565 `-Os` syl_bwelk | 93.50 | 93.02 | 0.99x |
| RGB565 `-Os` compose_bwelk | 27.35 | 27.00 | 0.99x |
| RGB565 `-Os` screen32 | 3311.74 | 3303.11 | 1.00x |
| RGB565 `-Os` line8 | 573.13 | 571.11 | 1.00x |
| RGB565 `-Os` aa_syl_ga | 146.90 | 143.22 | 0.97x |
| RGB565 `-Os` aa_syl_bwelk | 185.80 | 180.54 | 0.97x |
| RGB565 `-Os` aa_line12 | 1490.25 | 1454.87 | 0.98x |
| RGB565 `-Os` aa_screen10 | 14619.34 | 14376.38 | 0.98x |
| RGB565 `-O2` syl_ga | 64.53 | 64.24 | 1.00x |
| RGB565 `-O2` syl_bwelk | 81.14 | 80.66 | 0.99x |
| RGB565 `-O2` compose_bwelk | 23.00 | 22.65 | 0.98x |
| RGB565 `-O2` screen32 | 3049.45 | 3040.83 | 1.00x |
| RGB565 `-O2` line8 | 506.46 | 504.44 | 1.00x |
| RGB565 `-O2` aa_syl_ga | 130.36 | 127.32 | 0.98x |
| RGB565 `-O2` aa_syl_bwelk | 165.34 | 160.76 | 0.97x |
| RGB565 `-O2` aa_line12 | 1332.26 | 1302.43 | 0.98x |
| RGB565 `-O2` aa_screen10 | 13032.57 | 12823.21 | 0.98x |

### Uno (µs emulated, simavr 16 MHz, `-Os`; profile `mcu-strict`, built `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| syl_ga | 1075.51 | 1075.51 | 1.00x |
| syl_bwelk | 1257.08 | 1257.08 | 1.00x |
| compose_bwelk | 525.88 | 525.88 | 1.00x |
| screen32 | 32707.81 | 32707.81 | 1.00x |

### DOS (µs emulated, DOSBox-X 486DX2-66 and 486DX-33 presets; profile `dos`; word-store build, the `_bytes` builds are in the packed-kinds table)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| DX2-66 line40_mapped | 12450.54 | 11868.84 | 0.95x |
| DX2-66 line40_mapped_cache | 9320.32 | 9235.02 | 0.99x |
| DX2-66 line40_scaled32 | 221937.88 | 145514.52 | 0.66x |
| DX2-66 line40_indexed8 | 12023.82 | 11442.08 | 0.95x |
| DX2-66 line40_rgb555 | 11983.84 | 11402.10 | 0.95x |
| DX2-66 line40_rgb565 | 11958.48 | 11377.13 | 0.95x |
| DX2-66 line40_xrgb8888 | 13471.46 | 12889.87 | 0.96x |
| DX2-66 line40_rgb888 | 13717.86 | 13136.31 | 0.96x |
| DX2-66 line40_24_indexed8 | 16155.00 | 14939.29 | 0.92x |
| DX2-66 line40_24_rgb555 | 15746.88 | 14531.39 | 0.92x |
| DX2-66 line40_24_rgb565 | 15721.72 | 14506.04 | 0.92x |
| DX2-66 line40_24_xrgb8888 | 18291.61 | 17075.90 | 0.93x |
| DX2-66 line40_24_rgb888 | 18683.43 | 17467.94 | 0.93x |
| DX2-66 line40_24m_indexed8 | 12939.57 | 12801.44 | 0.99x |
| DX2-66 line40_24m_rgb565 | 11936.24 | 11798.15 | 0.99x |
| DX2-66 line40_24m_xrgb8888 | 14016.66 | 13878.54 | 0.99x |
| DX2-66 line40_stream_cold | 23624.26 | 23034.24 | 0.98x |
| DX2-66 line40_stream_warm | 13392.58 | 12811.28 | 0.96x |
| DX2-66 line40_stream_small | 20751.49 | 20169.85 | 0.97x |
| DX2-66 line40_stream_nocache | 22932.50 | 22348.35 | 0.97x |
| DX-33 line40_mapped | 24789.72 | 23631.62 | 0.95x |
| DX-33 line40_mapped_cache | 18557.15 | 18387.77 | 0.99x |
| DX-33 line40_scaled32 | 441891.87 | 289727.90 | 0.66x |
| DX-33 line40_indexed8 | 23940.14 | 22782.06 | 0.95x |
| DX-33 line40_rgb555 | 23860.59 | 22702.46 | 0.95x |
| DX-33 line40_rgb565 | 23810.15 | 22652.07 | 0.95x |
| DX-33 line40_xrgb8888 | 26822.36 | 25664.29 | 0.96x |
| DX-33 line40_rgb888 | 27313.26 | 26155.25 | 0.96x |
| DX-33 line40_24_indexed8 | 32165.42 | 29745.34 | 0.92x |
| DX-33 line40_24_rgb555 | 31352.62 | 28932.82 | 0.92x |
| DX-33 line40_24_rgb565 | 31302.85 | 28882.45 | 0.92x |
| DX-33 line40_24_xrgb8888 | 36419.60 | 33999.48 | 0.93x |
| DX-33 line40_24_rgb888 | 37199.97 | 34779.85 | 0.93x |
| DX-33 line40_24m_indexed8 | 25763.52 | 25488.21 | 0.99x |
| DX-33 line40_24m_rgb565 | 23765.85 | 23490.55 | 0.99x |
| DX-33 line40_24m_xrgb8888 | 27907.74 | 27632.80 | 0.99x |
| DX-33 line40_stream_cold | 41763.19 | 40589.85 | 0.97x |
| DX-33 line40_stream_warm | 26665.38 | 25507.77 | 0.96x |
| DX-33 line40_stream_small | 37177.19 | 36020.73 | 0.97x |
| DX-33 line40_stream_nocache | 42140.33 | 40982.42 | 0.97x |

### ESP32-C3 (instructions per iteration, QEMU rdinstret; not time; profile `mcu-strict`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3360 | 3360 | 1.00x |
| MONO_PAGE `-Os` syl_bwelk | 4123 | 4126 | 1.00x |
| MONO_PAGE `-Os` compose_bwelk | 1800 | 1802 | 1.00x |
| MONO_PAGE `-Os` screen32 | 98326 | 98340 | 1.00x |
| MONO_PAGE `-Os` line8 | 24283 | 24283 | 1.00x |
| MONO_PAGE `-O2` syl_ga | 2895 | 2857 | 0.99x |
| MONO_PAGE `-O2` syl_bwelk | 3546 | 3484 | 0.98x |
| MONO_PAGE `-O2` compose_bwelk | 1567 | 1523 | 0.97x |
| MONO_PAGE `-O2` screen32 | 85672 | 84586 | 0.99x |
| MONO_PAGE `-O2` line8 | 21149 | 20895 | 0.99x |
| GRAY8 `-Os` syl_ga | 3945 | 3998 | 1.01x |
| GRAY8 `-Os` syl_bwelk | 5188 | 5138 | 0.99x |
| GRAY8 `-Os` compose_bwelk | 1800 | 1802 | 1.00x |
| GRAY8 `-Os` screen32 | 119655 | 119919 | 1.00x |
| GRAY8 `-Os` line8 | 29588 | 29702 | 1.00x |
| GRAY8 `-Os` aa_syl_ga | 8547 | 8510 | 1.00x |
| GRAY8 `-Os` aa_syl_bwelk | 10679 | 10697 | 1.00x |
| GRAY8 `-Os` aa_line12 | 81515 | 81354 | 1.00x |
| GRAY8 `-Os` aa_screen10 | 598670 | 598146 | 1.00x |
| GRAY8 `-O2` syl_ga | 3759 | 3630 | 0.97x |
| GRAY8 `-O2` syl_bwelk | 4771 | 4545 | 0.95x |
| GRAY8 `-O2` compose_bwelk | 1567 | 1523 | 0.97x |
| GRAY8 `-O2` screen32 | 115528 | 111208 | 0.96x |
| GRAY8 `-O2` line8 | 28558 | 27452 | 0.96x |
| GRAY8 `-O2` aa_syl_ga | 8182 | 8037 | 0.98x |
| GRAY8 `-O2` aa_syl_bwelk | 10195 | 10038 | 0.98x |
| GRAY8 `-O2` aa_line12 | 79793 | 78481 | 0.98x |
| GRAY8 `-O2` aa_screen10 | 586868 | 576404 | 0.98x |
| RGB565 `-Os` syl_ga | 4372 | 4372 | 1.00x |
| RGB565 `-Os` syl_bwelk | 5681 | 5684 | 1.00x |
| RGB565 `-Os` compose_bwelk | 1800 | 1802 | 1.00x |
| RGB565 `-Os` screen32 | 135356 | 135371 | 1.00x |
| RGB565 `-Os` line8 | 33049 | 33049 | 1.00x |
| RGB565 `-Os` aa_syl_ga | 9070 | 8867 | 0.98x |
| RGB565 `-Os` aa_syl_bwelk | 11569 | 11347 | 0.98x |
| RGB565 `-Os` aa_line12 | 88437 | 86552 | 0.98x |
| RGB565 `-Os` aa_screen10 | 852359 | 839193 | 0.98x |
| RGB565 `-O2` syl_ga | 3846 | 3808 | 0.99x |
| RGB565 `-O2` syl_bwelk | 4925 | 4863 | 0.99x |
| RGB565 `-O2` compose_bwelk | 1567 | 1523 | 0.97x |
| RGB565 `-O2` screen32 | 120788 | 119702 | 0.99x |
| RGB565 `-O2` line8 | 29365 | 29111 | 0.99x |
| RGB565 `-O2` aa_syl_ga | 8161 | 8069 | 0.99x |
| RGB565 `-O2` aa_syl_bwelk | 10239 | 10135 | 0.99x |
| RGB565 `-O2` aa_line12 | 80700 | 80024 | 0.99x |
| RGB565 `-O2` aa_screen10 | 653333 | 647268 | 0.99x |

### ESP32-S3 (instructions per iteration, QEMU core-0 ICOUNT; not time; profile `mcu-strict`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3152 | 3116 | 0.99x |
| MONO_PAGE `-Os` syl_bwelk | 3836 | 3776 | 0.98x |
| MONO_PAGE `-Os` compose_bwelk | 1582 | 1538 | 0.97x |
| MONO_PAGE `-Os` screen32 | 94374 | 93296 | 0.99x |
| MONO_PAGE `-Os` line8 | 23328 | 23076 | 0.99x |
| MONO_PAGE `-O2` syl_ga | 2509 | 2471 | 0.98x |
| MONO_PAGE `-O2` syl_bwelk | 3078 | 3016 | 0.98x |
| MONO_PAGE `-O2` compose_bwelk | 1311 | 1267 | 0.97x |
| MONO_PAGE `-O2` screen32 | 76118 | 75032 | 0.99x |
| MONO_PAGE `-O2` line8 | 18610 | 18356 | 0.99x |
| GRAY8 `-Os` syl_ga | 3324 | 3288 | 0.99x |
| GRAY8 `-Os` syl_bwelk | 4424 | 4364 | 0.99x |
| GRAY8 `-Os` compose_bwelk | 1582 | 1538 | 0.97x |
| GRAY8 `-Os` screen32 | 103416 | 102338 | 0.99x |
| GRAY8 `-Os` line8 | 25312 | 25060 | 0.99x |
| GRAY8 `-Os` aa_syl_ga | 8724 | 8530 | 0.98x |
| GRAY8 `-Os` aa_syl_bwelk | 11109 | 10891 | 0.98x |
| GRAY8 `-Os` aa_line12 | 84888 | 83257 | 0.98x |
| GRAY8 `-Os` aa_screen10 | 627385 | 615410 | 0.98x |
| GRAY8 `-O2` syl_ga | 2917 | 2879 | 0.99x |
| GRAY8 `-O2` syl_bwelk | 3691 | 3629 | 0.98x |
| GRAY8 `-O2` compose_bwelk | 1311 | 1267 | 0.97x |
| GRAY8 `-O2` screen32 | 96275 | 95189 | 0.99x |
| GRAY8 `-O2` line8 | 22089 | 21835 | 0.99x |
| GRAY8 `-O2` aa_syl_ga | 7642 | 7517 | 0.98x |
| GRAY8 `-O2` aa_syl_bwelk | 9494 | 9363 | 0.99x |
| GRAY8 `-O2` aa_line12 | 75152 | 74201 | 0.99x |
| GRAY8 `-O2` aa_screen10 | 566097 | 558497 | 0.99x |
| RGB565 `-Os` syl_ga | 3700 | 3664 | 0.99x |
| RGB565 `-Os` syl_bwelk | 4798 | 4738 | 0.99x |
| RGB565 `-Os` compose_bwelk | 1582 | 1538 | 0.97x |
| RGB565 `-Os` screen32 | 117158 | 116080 | 0.99x |
| RGB565 `-Os` line8 | 28195 | 27943 | 0.99x |
| RGB565 `-Os` aa_syl_ga | 8303 | 8109 | 0.98x |
| RGB565 `-Os` aa_syl_bwelk | 10625 | 10407 | 0.98x |
| RGB565 `-Os` aa_line12 | 81720 | 80089 | 0.98x |
| RGB565 `-Os` aa_screen10 | 747507 | 735532 | 0.98x |
| RGB565 `-O2` syl_ga | 3262 | 3224 | 0.99x |
| RGB565 `-O2` syl_bwelk | 4115 | 4053 | 0.98x |
| RGB565 `-O2` compose_bwelk | 1311 | 1267 | 0.97x |
| RGB565 `-O2` screen32 | 115710 | 114624 | 0.99x |
| RGB565 `-O2` line8 | 24951 | 24697 | 0.99x |
| RGB565 `-O2` aa_syl_ga | 7877 | 7752 | 0.98x |
| RGB565 `-O2` aa_syl_bwelk | 9882 | 9751 | 0.99x |
| RGB565 `-O2` aa_line12 | 78460 | 77508 | 0.99x |
| RGB565 `-O2` aa_screen10 | 608634 | 601034 | 0.99x |

### Cortex-M33 under QEMU (instructions per iteration, SysTick x 50; not time; profile `mcu-strict`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3308 | 3290 | 0.99x |
| MONO_PAGE `-Os` syl_bwelk | 3886 | 3856 | 0.99x |
| MONO_PAGE `-Os` compose_bwelk | 1540 | 1518 | 0.99x |
| MONO_PAGE `-Os` screen32 | 103062 | 102525 | 0.99x |
| MONO_PAGE `-Os` line8 | 24524 | 24398 | 0.99x |
| MONO_PAGE `-O2` syl_ga | 2602 | 2583 | 0.99x |
| MONO_PAGE `-O2` syl_bwelk | 3120 | 3088 | 0.99x |
| MONO_PAGE `-O2` compose_bwelk | 1370 | 1348 | 0.98x |
| MONO_PAGE `-O2` screen32 | 81918 | 81375 | 0.99x |
| MONO_PAGE `-O2` line8 | 19296 | 19170 | 0.99x |
| GRAY8 `-Os` syl_ga | 4385 | 3620 | 0.83x |
| GRAY8 `-Os` syl_bwelk | 5546 | 4492 | 0.81x |
| GRAY8 `-Os` compose_bwelk | 1540 | 1518 | 0.99x |
| GRAY8 `-Os` screen32 | 165375 | 141135 | 0.85x |
| GRAY8 `-Os` line8 | 33668 | 27282 | 0.81x |
| GRAY8 `-Os` aa_syl_ga | 8982 | 8766 | 0.98x |
| GRAY8 `-Os` aa_syl_bwelk | 11243 | 10168 | 0.90x |
| GRAY8 `-Os` aa_line12 | 88710 | 85420 | 0.96x |
| GRAY8 `-Os` aa_screen10 | 859930 | 834250 | 0.97x |
| GRAY8 `-O2` syl_ga | 4149 | 2710 | 0.65x |
| GRAY8 `-O2` syl_bwelk | 5200 | 3286 | 0.63x |
| GRAY8 `-O2` compose_bwelk | 1370 | 1348 | 0.98x |
| GRAY8 `-O2` screen32 | 159505 | 113875 | 0.71x |
| GRAY8 `-O2` line8 | 32200 | 20243 | 0.63x |
| GRAY8 `-O2` aa_syl_ga | 8054 | 7950 | 0.99x |
| GRAY8 `-O2` aa_syl_bwelk | 9964 | 8838 | 0.89x |
| GRAY8 `-O2` aa_line12 | 80415 | 77628 | 0.97x |
| GRAY8 `-O2` aa_screen10 | 798440 | 775640 | 0.97x |
| RGB565 `-Os` syl_ga | 4712 | 4694 | 1.00x |
| RGB565 `-Os` syl_bwelk | 5914 | 5883 | 0.99x |
| RGB565 `-Os` compose_bwelk | 1540 | 1518 | 0.99x |
| RGB565 `-Os` screen32 | 208512 | 207972 | 1.00x |
| RGB565 `-Os` line8 | 36310 | 36184 | 1.00x |
| RGB565 `-Os` aa_syl_ga | 8807 | 8656 | 0.98x |
| RGB565 `-Os` aa_syl_bwelk | 11130 | 10136 | 0.91x |
| RGB565 `-Os` aa_line12 | 88535 | 85948 | 0.97x |
| RGB565 `-Os` aa_screen10 | 969660 | 949000 | 0.98x |
| RGB565 `-O2` syl_ga | 3902 | 3884 | 1.00x |
| RGB565 `-O2` syl_bwelk | 4876 | 4844 | 0.99x |
| RGB565 `-O2` compose_bwelk | 1370 | 1348 | 0.98x |
| RGB565 `-O2` screen32 | 184240 | 183695 | 1.00x |
| RGB565 `-O2` line8 | 30098 | 29970 | 1.00x |
| RGB565 `-O2` aa_syl_ga | 7686 | 7642 | 0.99x |
| RGB565 `-O2` aa_syl_bwelk | 9474 | 8408 | 0.89x |
| RGB565 `-O2` aa_line12 | 77252 | 75185 | 0.97x |
| RGB565 `-O2` aa_screen10 | 629300 | 611470 | 0.97x |
| LINE `-Os` line40_mapped | 242390 | 232118 | 0.96x |
| LINE `-Os` line40_mapped_cache | 199218 | 195140 | 0.98x |
| LINE `-Os` line40_scaled32 | 4412975 | 3738338 | 0.85x |
| LINE `-Os` line40_stream_cold | 411450 | 401200 | 0.98x |
| LINE `-Os` line40_stream_warm | 258785 | 248512 | 0.96x |
| LINE `-Os` line40_stream_small | 349560 | 339288 | 0.97x |
| LINE `-Os` line40_stream_nocache | 273725 | 263450 | 0.96x |
| LINE `-O2` line40_mapped | 225752 | 217030 | 0.96x |
| LINE `-O2` line40_mapped_cache | 183898 | 180635 | 0.98x |
| LINE `-O2` line40_scaled32 | 4406622 | 2938098 | 0.67x |
| LINE `-O2` line40_stream_cold | 378500 | 369800 | 0.98x |
| LINE `-O2` line40_stream_warm | 239148 | 230422 | 0.96x |
| LINE `-O2` line40_stream_small | 327602 | 318878 | 0.97x |
| LINE `-O2` line40_stream_nocache | 257075 | 248350 | 0.97x |

### RP2350 Hazard3 under rp2350js (cycles per iteration; profile `mcu-strict`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 3943 | 3662 | 0.93x |
| MONO_PAGE `-Os` syl_bwelk | 4920 | 4413 | 0.90x |
| MONO_PAGE `-Os` compose_bwelk | 2309 | 1932 | 0.84x |
| MONO_PAGE `-Os` screen32 | 116352 | 107455 | 0.92x |
| MONO_PAGE `-Os` line8 | 28667 | 26539 | 0.93x |
| MONO_PAGE `-O2` syl_ga | 2822 | 2799 | 0.99x |
| MONO_PAGE `-O2` syl_bwelk | 3410 | 3371 | 0.99x |
| MONO_PAGE `-O2` compose_bwelk | 1469 | 1442 | 0.98x |
| MONO_PAGE `-O2` screen32 | 83072 | 82411 | 0.99x |
| MONO_PAGE `-O2` line8 | 20533 | 20379 | 0.99x |
| GRAY8 `-Os` syl_ga | 4813 | 4424 | 0.92x |
| GRAY8 `-Os` syl_bwelk | 6325 | 5609 | 0.89x |
| GRAY8 `-Os` compose_bwelk | 2309 | 1961 | 0.85x |
| GRAY8 `-Os` screen32 | 146308 | 133448 | 0.91x |
| GRAY8 `-Os` line8 | 36231 | 33113 | 0.91x |
| GRAY8 `-Os` aa_syl_ga | 10468 | 9741 | 0.93x |
| GRAY8 `-Os` aa_syl_bwelk | 12939 | 12093 | 0.93x |
| GRAY8 `-Os` aa_line12 | 99655 | 94136 | 0.94x |
| GRAY8 `-Os` aa_screen10 | 720479 | 681825 | 0.95x |
| GRAY8 `-O2` syl_ga | 4099 | 3631 | 0.89x |
| GRAY8 `-O2` syl_bwelk | 5084 | 4450 | 0.88x |
| GRAY8 `-O2` compose_bwelk | 1469 | 1442 | 0.98x |
| GRAY8 `-O2` screen32 | 126046 | 111394 | 0.88x |
| GRAY8 `-O2` line8 | 31311 | 27469 | 0.88x |
| GRAY8 `-O2` aa_syl_ga | 7945 | 8179 | 1.03x |
| GRAY8 `-O2` aa_syl_bwelk | 9684 | 10064 | 1.04x |
| GRAY8 `-O2` aa_line12 | 77598 | 80000 | 1.03x |
| GRAY8 `-O2` aa_screen10 | 563291 | 580987 | 1.03x |
| RGB565 `-Os` syl_ga | 5418 | 5137 | 0.95x |
| RGB565 `-Os` syl_bwelk | 6990 | 6483 | 0.93x |
| RGB565 `-Os` compose_bwelk | 2308 | 1931 | 0.84x |
| RGB565 `-Os` screen32 | 167765 | 158868 | 0.95x |
| RGB565 `-Os` line8 | 41124 | 38996 | 0.95x |
| RGB565 `-Os` aa_syl_ga | 10601 | 9735 | 0.92x |
| RGB565 `-Os` aa_syl_bwelk | 13121 | 12107 | 0.92x |
| RGB565 `-Os` aa_line12 | 102562 | 95484 | 0.93x |
| RGB565 `-Os` aa_screen10 | 1010184 | 961670 | 0.95x |
| RGB565 `-O2` syl_ga | 4163 | 4140 | 0.99x |
| RGB565 `-O2` syl_bwelk | 5215 | 5176 | 0.99x |
| RGB565 `-O2` compose_bwelk | 1469 | 1442 | 0.98x |
| RGB565 `-O2` screen32 | 130476 | 129816 | 0.99x |
| RGB565 `-O2` line8 | 31911 | 31757 | 1.00x |
| RGB565 `-O2` aa_syl_ga | 8244 | 8140 | 0.99x |
| RGB565 `-O2` aa_syl_bwelk | 10140 | 10006 | 0.99x |
| RGB565 `-O2` aa_line12 | 81490 | 80578 | 0.99x |
| RGB565 `-O2` aa_screen10 | 689325 | 682233 | 0.99x |
| LINE `-Os` line40_mapped | 260157 | 257550 | 0.99x |
| LINE `-Os` line40_mapped_cache | 202359 | 208789 | 1.03x |
| LINE `-Os` line40_scaled32 | 6651758 | 4490671 | 0.68x |
| LINE `-Os` line40_stream_cold | 377599 | 373436 | 0.99x |
| LINE `-Os` line40_stream_warm | 287597 | 284738 | 0.99x |
| LINE `-Os` line40_stream_small | 315625 | 312683 | 0.99x |
| LINE `-Os` line40_stream_nocache | 291758 | 289938 | 0.99x |
| LINE `-O2` line40_mapped | 210091 | 200210 | 0.95x |
| LINE `-O2` line40_mapped_cache | 167340 | 158656 | 0.95x |
| LINE `-O2` line40_scaled32 | 5090352 | 3389405 | 0.67x |
| LINE `-O2` line40_stream_cold | 288680 | 278573 | 0.96x |
| LINE `-O2` line40_stream_warm | 228599 | 218492 | 0.96x |
| LINE `-O2` line40_stream_small | 252299 | 242192 | 0.96x |
| LINE `-O2` line40_stream_nocache | 239870 | 230696 | 0.96x |

### RP2350 Cortex-M33 under rp2350js (cycles per iteration; profile `mcu-strict`)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| MONO_PAGE `-Os` syl_ga | 5162 | 5144 | 1.00x |
| MONO_PAGE `-Os` syl_bwelk | 6107 | 6077 | 1.00x |
| MONO_PAGE `-Os` compose_bwelk | 2432 | 2410 | 0.99x |
| MONO_PAGE `-Os` screen32 | 153436 | 152897 | 1.00x |
| MONO_PAGE `-Os` line8 | 37871 | 37745 | 1.00x |
| MONO_PAGE `-O2` syl_ga | 3746 | 3727 | 0.99x |
| MONO_PAGE `-O2` syl_bwelk | 4509 | 4478 | 0.99x |
| MONO_PAGE `-O2` compose_bwelk | 1936 | 1914 | 0.99x |
| MONO_PAGE `-O2` screen32 | 111362 | 110818 | 1.00x |
| MONO_PAGE `-O2` line8 | 27499 | 27372 | 1.00x |
| GRAY8 `-Os` syl_ga | 6473 | 5989 | 0.93x |
| GRAY8 `-Os` syl_bwelk | 8179 | 7478 | 0.91x |
| GRAY8 `-Os` compose_bwelk | 2432 | 2410 | 0.99x |
| GRAY8 `-Os` screen32 | 199063 | 183343 | 0.92x |
| GRAY8 `-Os` line8 | 49072 | 44948 | 0.92x |
| GRAY8 `-Os` aa_syl_ga | 12140 | 12123 | 1.00x |
| GRAY8 `-Os` aa_syl_bwelk | 14940 | 13964 | 0.93x |
| GRAY8 `-Os` aa_line12 | 118174 | 115802 | 0.98x |
| GRAY8 `-Os` aa_screen10 | 881713 | 863852 | 0.98x |
| GRAY8 `-O2` syl_ga | 5481 | 4108 | 0.75x |
| GRAY8 `-O2` syl_bwelk | 6855 | 4971 | 0.73x |
| GRAY8 `-O2` compose_bwelk | 1936 | 1914 | 0.99x |
| GRAY8 `-O2` screen32 | 171130 | 127290 | 0.74x |
| GRAY8 `-O2` line8 | 42054 | 30545 | 0.73x |
| GRAY8 `-O2` aa_syl_ga | 10111 | 9986 | 0.99x |
| GRAY8 `-O2` aa_syl_bwelk | 12439 | 10993 | 0.88x |
| GRAY8 `-O2` aa_line12 | 99534 | 96070 | 0.97x |
| GRAY8 `-O2` aa_screen10 | 747395 | 719106 | 0.96x |
| RGB565 `-Os` syl_ga | 6922 | 6904 | 1.00x |
| RGB565 `-Os` syl_bwelk | 8727 | 8697 | 1.00x |
| RGB565 `-Os` compose_bwelk | 2432 | 2410 | 0.99x |
| RGB565 `-Os` screen32 | 219648 | 219109 | 1.00x |
| RGB565 `-Os` line8 | 52923 | 52797 | 1.00x |
| RGB565 `-Os` aa_syl_ga | 12210 | 12065 | 0.99x |
| RGB565 `-Os` aa_syl_bwelk | 15207 | 13921 | 0.92x |
| RGB565 `-Os` aa_line12 | 121029 | 117837 | 0.97x |
| RGB565 `-Os` aa_screen10 | 1371183 | 1345826 | 0.98x |
| RGB565 `-O2` syl_ga | 5235 | 5216 | 1.00x |
| RGB565 `-O2` syl_bwelk | 6537 | 6506 | 1.00x |
| RGB565 `-O2` compose_bwelk | 1936 | 1914 | 0.99x |
| RGB565 `-O2` screen32 | 168102 | 167558 | 1.00x |
| RGB565 `-O2` line8 | 39930 | 39803 | 1.00x |
| RGB565 `-O2` aa_syl_ga | 10045 | 10001 | 1.00x |
| RGB565 `-O2` aa_syl_bwelk | 12361 | 11030 | 0.89x |
| RGB565 `-O2` aa_line12 | 99757 | 97107 | 0.97x |
| RGB565 `-O2` aa_screen10 | 845802 | 823526 | 0.97x |
| LINE `-Os` line40_mapped | 323347 | 308755 | 0.95x |
| LINE `-Os` line40_mapped_cache | 261333 | 254525 | 0.97x |
| LINE `-Os` line40_scaled32 | 7554519 | 6047767 | 0.80x |
| LINE `-Os` line40_stream_cold | 454251 | 439659 | 0.97x |
| LINE `-Os` line40_stream_warm | 354210 | 339618 | 0.96x |
| LINE `-Os` line40_stream_small | 390308 | 375716 | 0.96x |
| LINE `-Os` line40_stream_nocache | 363328 | 348736 | 0.96x |
| LINE `-O2` line40_mapped | 280264 | 267785 | 0.96x |
| LINE `-O2` line40_mapped_cache | 223784 | 218281 | 0.98x |
| LINE `-O2` line40_scaled32 | 7181569 | 4020370 | 0.56x |
| LINE `-O2` line40_stream_cold | 373035 | 360556 | 0.97x |
| LINE `-O2` line40_stream_warm | 302500 | 290021 | 0.96x |
| LINE `-O2` line40_stream_small | 333690 | 321211 | 0.96x |
| LINE `-O2` line40_stream_nocache | 318443 | 305964 | 0.96x |

### WASM (µs of host CPU time, node/V8; profile `wasm`; the median of four runs, because one run of `line40_mapped` read 18.73 µs and the next three 13.35 to 14.61)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| line40_mapped | 14.01 | 16.61 | 1.19x |
| line40_mapped_cache | 8.99 | 10.46 | 1.16x |
| line40_scaled32 | 189.30 | 150.37 | 0.79x |
| line40_stream_cold | 81.00 | 84.15 | 1.04x |
| line40_stream_warm | 12.07 | 12.24 | 1.01x |
| line40_stream_small | 12.74 | 12.94 | 1.02x |
| line40_stream_nocache | 12.82 | 13.07 | 1.02x |

### Host (µs of host CPU time; profile `default`; one run each on a shared machine, repeated runs differ by up to 50 %)

| case | v3 (4539e42) | after | ratio |
|---|---:|---:|---:|
| line40_mapped | 10.00 | 8.54 | 0.85x |
| line40_mapped_cache | 6.19 | 6.69 | 1.08x |
| line40_scaled32 | 171.36 | 110.18 | 0.64x |
| line40_indexed8 | 8.58 | 8.13 | 0.95x |
| line40_rgb555 | 8.38 | 7.82 | 0.93x |
| line40_rgb565 | 8.32 | 7.84 | 0.94x |
| line40_xrgb8888 | 10.06 | 9.54 | 0.95x |
| line40_rgb888 | 10.39 | 9.73 | 0.94x |
| line40_24_indexed8 | 11.30 | 10.44 | 0.92x |
| line40_24_rgb555 | 11.03 | 10.13 | 0.92x |
| line40_24_rgb565 | 11.04 | 10.16 | 0.92x |
| line40_24_xrgb8888 | 13.52 | 12.69 | 0.94x |
| line40_24_rgb888 | 14.27 | 13.26 | 0.93x |
| line40_24m_indexed8 | 8.78 | 8.49 | 0.97x |
| line40_24m_rgb565 | 7.67 | 7.21 | 0.94x |
| line40_24m_xrgb8888 | 11.16 | 10.70 | 0.96x |
| line40_stream_cold | 33.18 | 31.83 | 0.96x |
| line40_stream_warm | 8.64 | 8.37 | 0.97x |
| line40_stream_small | 9.00 | 8.69 | 0.97x |
| line40_stream_nocache | 8.98 | 9.07 | 1.01x |

### ESP32-S3 on real silicon (T7-C1: `SVF_GRAY8_LUT1`, CCOUNT cycles, not an emulation)

The QEMU rows above count instructions; a real Xtensa LX7 pays for taken branches and loads, which the count ignores, and Task 7's nibble table was
5 to 33 % **more** instructions on the S3. This run times it on an ESP32-S3-DevKitC-1 (ESP32-S3, 240 MHz, ESP-IDF v5.5.6 app, code in flash behind the
instruction cache, FreeRTOS tick 100 Hz, nothing else running) with `c/bench/run-esp32-hw.sh`: the GRAY8 build of `bench.c` (the same cases, iterations and `mcu-strict`
face as `run-esp32.sh`; `bench.c` edited by sed in the build directory only: `rsr.icount` -> `rsr.ccount`, no calibration) compiled with the
pinned xtensa-esp-elf gcc 16.1.0, `-DSVF_GRAY8_LUT1=0` and `=1`, `-Os` and `-O2`. **Cycles per iteration** (CCOUNT of core 0, the cycle counter itself); each
configuration was run twice after a reset and the two runs agree to 0.1 % (shown: run 1); every checksum equals the simulator rows' (`sums.inc.sh`
`SUMS_GRAY8`), `ok` in all 80 rows. `bench.c` has no `line40` cases on the ESP32 (those are DOS, host, M33 and RP2350 builds); the 1 bpp GRAY8 rows are `syl_ga`,
`syl_bwelk`, `screen32` and `line8`, the 2 bpp `aa_*` rows do not use the table.

| case | iterations | `-Os` LUT1=0 | `-Os` LUT1=1 | `-Os` change | `-O2` LUT1=0 | `-O2` LUT1=1 | `-O2` change |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 100 | 5369 | 5641 | +5.1 % | 4396 | 5297 | +20.5 % |
| syl_bwelk | 100 | 6348 | 6512 | +2.6 % | 4810 | 5908 | +22.8 % |
| compose_bwelk | 100 | 2075 | 2075 | +0.0 % | 1626 | 1624 | -0.2 % |
| screen32 | 20 | 150453 | 156967 | +4.3 % | 129329 | 156820 | +21.3 % |
| line8 | 100 | 37255 | 38947 | +4.5 % | 29323 | 36476 | +24.4 % |
| aa_syl_ga | 100 | 11777 | 11717 | -0.5 % | 9546 | 9539 | -0.1 % |
| aa_syl_bwelk | 100 | 14539 | 14397 | -1.0 % | 11515 | 11506 | -0.1 % |
| aa_line12 | 20 | 114645 | 114145 | -0.4 % | 93657 | 93457 | -0.2 % |
| aa_screen10 | 5 | 834044 | 830394 | -0.4 % | 686130 | 687005 | +0.1 % |

**Result: LUT1=1 is slower on the S3 at every 1 bpp row** (`-Os` +2.6 to +5.1 %, `-O2` +20.5 to +24.4 %); the 2 bpp `aa_*` rows (not touched by the switch) move by -1.0 to -0.4 % at `-Os` and -0.2 to +0.1 % at `-O2` (code placement). So the instruction counts were right in sign and the silicon is no kinder than the count: **the
Xtensa default stays `SVF_GRAY8_LUT1` 0** (as Task 8 set it from the counts), now measured. The silicon takes about 1.6 cycles per instruction at `-Os` (`syl_ga`: 3288
instructions in QEMU, 5369 cycles here) because the face and code stream from flash through the cache; `-O2` makes the bit loop 18 % faster in cycles than `-Os` (the table 6 %). `layout_probe` is not a draw and is left out of the comparison.

### Hazard3 rows treated as code placement (T6-C1, T7-C2), final build

Against the v3 baseline (4539e42) and Task 6's run, rp2350js cycles per iteration: Hazard3 `-O2` `line40_scaled32` 5090352 -> **3389405** (0.67x; Task 6 read 5322574, the +4.56 % the placement
ruling excluded; the separable filter of Task 8 replaced that function and the row is now a clear gain). Hazard3 `-Os` `line40_*`: `line40_mapped` 260157 -> 257550 (-1.0 %), `line40_stream_cold` -1.1 %, `line40_stream_warm` -1.0 %,
`line40_stream_small` -0.9 %, `line40_stream_nocache` -0.6 %, `line40_scaled32` 6651758 -> 4490671 (0.68x); **one row is still above its baseline: `line40_mapped_cache` 202359 -> 208789 (+3.2 %)** (Task 7 read +8.4 %, 219278; Task 9's shift recovered part of it).
Hazard3 `-O2` `line40_*` are -3.5 to -5.2 %. Also above baseline on Hazard3 `-O2`: the GRAY8 2 bpp rows `aa_syl_ga` 7945 -> 8179 (+2.9 %), `aa_syl_bwelk` 9684 -> 10064 (+3.9 %), `aa_line12` +3.1 %, `aa_screen10` +3.1 %
(Task 7 introduced +3.7 %; the 2 bpp code did not change in Task 7, so this is placement or inlining; Task 9 recovered part of it). The only other rows above their baseline by more than 0.3 % are ESP32-C3 `-Os`
GRAY8 `syl_ga` 3945 -> 3998 (+1.3 %, within the C3's noted noise) and `line8` +0.4 %.

### What moved, per task (final rows against 4539e42; the plan's expectation of each task beside it)

- **Task 6, the `svf__merge` word path (`SVF_MERGE_WORDS`): kept.** Expectation: DOS `line40_mapped` -1 to -3 %, M33 `aa_*` -3 to -6 %, Pico `syl_bwelk` 0 to -1.5 %, Uno identical. Task 6 alone read DOS DX2-66 12450.54 -> 11994.62 µs (-3.66 %), QEMU M33 `-Os`
  `aa_syl_bwelk` 11243 -> 10301 (-8.38 %, above the band), Pico `syl_bwelk` unchanged; in the final run DOS DX2-66 `line40_mapped` is 11868.84 µs (-4.7 % with Tasks 7-9) and DX-33 23631.62 µs, QEMU M33 `-Os` `aa_syl_bwelk` 10168 (-9.6 %), `-O2` 8838 (-11.3 %),
  rp2350js M33 `-Os` 13964 (-6.5 %), Hazard3 `-Os` 12093 (-6.5 %). The Uno rows are identical (switch 0). Cost: +176 B on Cortex-M0+ P1* (8826 -> 9002).
- **Task 7, GRAY8 1 bpp through a 64 B nibble table (`SVF_GRAY8_LUT1`): kept, on everywhere except AVR and Xtensa.** Expectation: Pico, ESP32, M33, Hazard3 GRAY8 `syl_ga`, `syl_bwelk`, `screen32`, `line8` 1.15-1.4x. Pico `-Os` `syl_ga` 64.95 -> 59.58 µs
  (1.09x), `syl_bwelk` 83.83 -> 74.98 (1.12x), `screen32` 2520.14 -> 2341.82 (1.08x), `line8` 1.10x; `-O2` 1.05-1.09x: **below the band on the Pico**. QEMU M33 `-Os` 1.17-1.23x, `-O2` 1.40-1.59x (in the band),
  rp2350js M33 1.08-1.38x, Hazard3 1.09-1.14x. ESP32-C3 `-Os` 0.99-1.00x (no gain; `-O2` 1.04-1.05x), and the table is off on the S3, where the silicon run above shows it would lose. MONO_PAGE and RGB565 rows: identical in Task 7.
- **Task 8, the separable box filter in `svf__scale_cell`: kept; every scaled row faster, below the planned ~2x everywhere.** `line40_scaled32`: DOS DX2-66 221937.88 -> 145514.52 µs (1.53x; planned ~2x), DX-33 441891.85 -> 289727.90 (1.53x),
  QEMU M33 `-Os` 4412975 -> 3738338 (1.18x; planned 1.8-1.9x), `-O2` 4406622 -> 2938098 (1.50x; planned 2.2-2.4x), Hazard3 6651758 -> 4490671 (1.48x) / 5090352 -> 3389405 (1.50x; planned 1.8-2.2x), rp2350js M33 7554519 -> 6047767 (1.25x) /
  7181569 -> 4020370 (1.79x), WASM 189.30 -> 150.37 µs (1.26x; the run-to-run spread is larger than that), host 171.36 -> 110.18 µs (1.56x, median of five). The planned bands were estimates from a spike; per-cell setup dominates at 3/2. No unscaled row moved. The scaled path
  now needs about 0.9 KB of stack (`c/cross/SIZES.md`, Findings).
- **Task 9, the cmap midpoint by an unsigned shift (`svf__glyph_index`): kept; `div` count 1 -> 0 in the function.** Expectation: Pico `syl_*` -0.5 to -1 %, C3/Hazard3 under 1 % or what rp2350js charges a `div`, x86/M33/Xtensa no change. Pico MONO_PAGE `-Os` `svf__glyph_index` 75600 -> 72000 cycles over 100 `syl_ga`
  (11.6 -> 11.1 % of the profile build), 123000 -> 117000 over `syl_bwelk` (15.5 -> 14.9 %); the plain rows -0.6 % (`syl_ga` 6179 -> 6143) and -0.8 % (`syl_bwelk` 7560 -> 7500) with all tasks; Hazard3 `-Os` `syl_ga` 3943 -> 3662 (-7.1 %), `syl_bwelk` 4920 -> 4413 (-10.3 %), a
  `div` costing more than the expectation assumed. **T9-F1 (the review's HIGH, fixed in 8bff82e):** the first form `((unsigned)lo + hi) >> 1` overflowed where `int` is 16 bits (AVR) for tables over 32767 entries; the final form `lo + ((unsigned)(hi - lo) >> 1)` is exact and costs +4 B on Cortex-M0+ and
  +13 to +21 Pico cycles per syllable (+0.2 to +0.3 %: `syl_ga` -Os 6130 -> 6143, `syl_bwelk` 7479 -> 7500); `test_kernels` emulates the search in 16-bit arithmetic for counts up to 65535 and shows the old midpoint failing.

Pico `PROFILE=1` (rp2040js, the plain-build flags plus `-fno-inline-functions-called-once -fno-inline-small-functions`; `-Os`; cycles over the case's 100 iterations and the share of the case). `svf__merge` has no symbol of its own in either build (v3 inlines the 1 and 2 bpp merges into
`svf__put_rows`), so its work is in the `svf__put_rows` row:

| kind | case | function | v3 (4539e42) cycles | v3 share | after cycles | after share |
|---|---|---|---:|---:|---:|---:|
| MONO_PAGE | syl_ga | blit_mono_page | 200100 | 30.6 % | 200100 | 30.8 % |
| MONO_PAGE | syl_ga | svf__put_rows | 41000 | 6.3 % | 41000 | 6.3 % |
| MONO_PAGE | syl_ga | svf__glyph_index | 75600 | 11.6 % | 72000 | 11.1 % |
| MONO_PAGE | syl_ga | (case total, profile build) | 653904 | 100 % | 650304 | 100 % |
| MONO_PAGE | syl_bwelk | blit_mono_page | 203300 | 25.7 % | 203300 | 25.9 % |
| MONO_PAGE | syl_bwelk | svf__put_rows | 65500 | 8.3 % | 65500 | 8.3 % |
| MONO_PAGE | syl_bwelk | svf__glyph_index | 123000 | 15.5 % | 117000 | 14.9 % |
| MONO_PAGE | syl_bwelk | (case total, profile build) | 791505 | 100 % | 785505 | 100 % |
| GRAY8 | syl_ga | blit_gray8 | 423900 | 50.9 % | 246800 | 31.0 % |
| GRAY8 | syl_ga | svf__put_rows | 41000 | 4.9 % | 41000 | 5.1 % |
| GRAY8 | syl_ga | svf__glyph_index | 75600 | 9.1 % | 72000 | 9.0 % |
| GRAY8 | syl_ga | (case total, profile build) | 833204 | 100 % | 796904 | 100 % |
| GRAY8 | syl_bwelk | blit_gray8 | 509900 | 48.4 % | 260000 | 26.3 % |
| GRAY8 | syl_bwelk | svf__put_rows | 65500 | 6.2 % | 65500 | 6.6 % |
| GRAY8 | syl_bwelk | svf__glyph_index | 123000 | 11.7 % | 117000 | 11.8 % |
| GRAY8 | syl_bwelk | (case total, profile build) | 1053605 | 100 % | 987705 | 100 % |

The plain (non-profile) `-Os` Pico rows are in the Pico table above. In the GRAY8 build `blit_gray8` fell from 50.9 % to 31.0 % of `syl_ga` (423900 -> 246800 cycles, -42 %) and from 48.4 % to 26.3 % of `syl_bwelk`: the nibble table is the single largest change of the five tasks on the Pico.

**Run-to-run checks.** Pico: the second run (`c/build/bench/after/pico2.md`) is identical to the first (rows `diff` clean). DOS: the second run (`dos2.md`) differs from the first by at most 0.84 µs (one timer tick of `uclock()`; the 1-iteration row `line40_stream_cold` and `layout_probe`); the 50-iteration rows agree to 0.02 µs or better. WASM is the median of four runs of the earlier (2026-10-2x) measurement
(`line40_mapped` read 20.62, 19.11, 14.10, 14.04 µs: the machine was busy during the first two); host is the median of five runs of one build (both the earlier 2026-10-2x runs; the Host and WASM tables in Results were re-taken 2026-10-26 as medians of five runs each, spreads in their introductions: WASM `line40_mapped` 13.31 to 13.79 µs, host 7.93 to 8.42 µs). Neither is a measurement of a target.

## Before -> after JSET v1 + v2 (2026-10-26, c592140 -> ccd0190 + Task 10)

**The shipped faces are JSET version 1** (spec amendment 3: v1 is the standard, `svf/` is unchanged from c592140, every writer and
`svf2to3` default to `--jset-version 1`); **the v2 rows describe an opt-in pack**, the compact format a memory-constrained build or
pack chooses with `--jset-version 2|auto`. The v2 faces below are build outputs in `c/build/jset2/` (`c/bench/JSET2-IDENTITY.md` says how
to regenerate them), not committed. BASE = the library of c592140 (main after the C speedups) with its faces, as measured in Task 1
and shown in the result tables before this task. Every checksum of every run below is `ok` (pixel-identical to BASE: `sums.py`
computes them for the v2 copies too). All runs: this tree, the default build (both JSET readers; AVR the version 1 reader alone;
validation on).

Runs: v1 face = `c/build/t10/<runner>`; v2 copy = `c/build/t10/<runner>-v2` with `FACE=c/build/jset2/forced/iolo/HGKEY6J.SVF`,
`FACE16=c/build/jset2/svf/dos/PAPLG16.SVF`, `FACE18=c/build/jset2/svf/dos/PAPLG18.SVF`; "v2 reader alone" = a scratch worktree of
HEAD (`c/build/t10/div`, not committed) whose version 2 decomposition (`pieces_v2` in `c/src/svf_jamo.c`) has its two multiply-shifts
replaced by the three divisions of the original design (R7); "v2" = the shipped decomposition. The scratch rows are in the tables
below, which `check-measurements-md.py` does not parse.

### Cycle gate (R2)

| row | BASE | v1 face | gate | v2 copy | Task 3 accepted | v2 vs BASE |
|---|---:|---:|---|---:|---:|---:|
| Pico MONO_PAGE `-Os` `syl_ga` (cycles) | 6143 | 6091 (-0.8 %) | <= BASE: met | 6458 | 6458 | +5.1 % |
| Pico MONO_PAGE `-Os` `syl_bwelk` | 7500 | 7321 (-2.4 %) | <= BASE: met | 8027 | 8027 | +7.0 % |
| Pico MONO_PAGE `-Os` `screen32` | 194583 | 188251 (-3.3 %) | <= BASE: met | 206545 | 206545 | +6.1 % |
| Uno `syl_ga` / `syl_bwelk` / `screen32` (cycles) | 17208 / 20113 / 523325 | 17208 / 20113 / 523325 | not slower: met (identical) | - | - | - |
| DOS DX2-66 `line40_mapped` (µs) | 11868.84 | 11876.45 (+0.06 %) | not slower: **7.6 µs slower** | - | - | - |
| DOS DX2-66 `line40_stream_warm` (µs) | 12811.28 | 12818.69 (+0.06 %) | not slower: **7.4 µs slower** | - | - | - |

The DOS rows are 0.06 % above BASE (emulated time at fixed cycles) and far under their 16 ms budget. The difference is real and
deterministic: HEAD twice and c592140 twice give the same rows to within one PIT tick (0.02-1.7 µs on the 50-iteration rows;
e.g. `line40_mapped` 11876.45 against 11868.84 µs, `line40_stream_warm` 12818.69 against 12811.28 µs, on every run). It is a constant
+7.4 to +7.7 µs on the mapped and warm-streamed 50-iteration rows (+5.7 to +5.9 µs on the first-draw and 5-iteration rows `line40_stream_cold` and `line40_stream_nocache`), about 0.19 µs a glyph, and it is the same +7.6 µs on the PAPLG16/18 rows, which
carry no JSET block (`line40_scaled32` +7.6 µs of 145 ms; `line40_mapped_cache` +0.8 µs; the 24 px rows +52 µs; these figures are
`c/build/t10/dos` against `c/build/t10/dos-base1`, not a re-taken table: the packed-kind table below is the 2026-10-21/23 run). The
cause was not isolated (30 min time box, no library change): two experiments on c592140, one extra byte in the `svf_face` JSET
fields and 1.6 KB of unused code in `svf_jamo.o`, did not reproduce it. Under DOSBox-X's fixed instructions per emulated millisecond
the figure means the drawing path executes about 4.5 more instructions a glyph, which the disassembly of the draw, face and stream
objects does not show; **the instruction count of the drawing path is the open question.** It is the one place the "not slower than
BASE" criterion is not met to the microsecond; reported in the Task 10 report and put to the user for a ruling. The v2 copy
figures equal the accepted Task 3 figures exactly.

### Pico (cycles per iteration; rp2040js 125 MHz)

Pico, cycles per iteration (rp2040js, 125 MHz; insns in the next table), single-kind builds. BASE = c592140 + the c-speedups merge as measured in Task 1 (the rows of the result tables before this task); v1 = the shipped face (JSET v1, default build); v2 reader alone = the opt-in v2 copy of the face with the three divisions of the decomposition put back (scratch worktree, not committed: `s / 588`, `(s / 28) % 21`, `s % 28`); v2 = the v2 copy with the shipped multiply-shift decomposition. Faces: `HGKEY6J` (forced v2 copy), `PAPLG16`/`PAPLG18` (auto v2 copies). The shipped faces are v1; the v2 columns describe an opt-in pack.

MONO_PAGE `-Os`:

| case | BASE | v1 | v1 vs BASE | v2 reader alone | v2 | v2 vs BASE | v2 vs reader alone |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 6143 | 6091 | -0.8 % | 6520 | 6458 | +5.1 % | -1.0 % |
| syl_bwelk | 7500 | 7321 | -2.4 % | 8217 | 8027 | +7.0 % | -2.3 % |
| compose_bwelk | 3375 | 3188 | -5.5 % | 4131 | 3938 | +16.7 % | -4.7 % |
| screen32 | 194583 | 188251 | -3.3 % | 213071 | 206545 | +6.1 % | -3.1 % |
| line8 | 46368 | 44617 | -3.8 % | 50930 | 49131 | +6.0 % | -3.5 % |

MONO_PAGE `-O2`:

| case | BASE | v1 | v1 vs BASE | v2 reader alone | v2 | v2 vs BASE | v2 vs reader alone |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 4978 | 4962 | -0.3 % | 5399 | 5355 | +7.6 % | -0.8 % |
| syl_bwelk | 6060 | 5918 | -2.3 % | 6825 | 6656 | +9.8 % | -2.5 % |
| compose_bwelk | 2831 | 2665 | -5.9 % | 3609 | 3438 | +21.4 % | -4.7 % |
| screen32 | 158039 | 152425 | -3.6 % | 177278 | 171398 | +8.5 % | -3.3 % |
| line8 | 37361 | 35789 | -4.2 % | 42108 | 40469 | +8.3 % | -3.9 % |

GRAY8 `-Os`:

| case | BASE | v1 | v1 vs BASE | v2 reader alone | v2 | v2 vs BASE | v2 vs reader alone |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 7448 | 7396 | -0.7 % | 7825 | 7763 | +4.2 % | -0.8 % |
| syl_bwelk | 9373 | 9194 | -1.9 % | 10090 | 9900 | +5.6 % | -1.9 % |
| compose_bwelk | 3375 | 3188 | -5.5 % | 4131 | 3938 | +16.7 % | -4.7 % |
| screen32 | 292727 | 286395 | -2.2 % | 311215 | 304689 | +4.1 % | -2.1 % |
| line8 | 57292 | 55541 | -3.1 % | 61854 | 60055 | +4.8 % | -2.9 % |
| aa_syl_ga | 15919 | 15867 | -0.3 % | 16396 | 16334 | +2.6 % | -0.4 % |
| aa_syl_bwelk | 19745 | 19566 | -0.9 % | 20652 | 20462 | +3.6 % | -0.9 % |
| aa_line12 | 157775 | 155744 | -1.3 % | 163726 | 161642 | +2.5 % | -1.3 % |
| aa_screen10 | 1580281 | 1568436 | -0.7 % | 1617382 | 1605164 | +1.6 % | -0.8 % |

GRAY8 `-O2`:

| case | BASE | v1 | v1 vs BASE | v2 reader alone | v2 | v2 vs BASE | v2 vs reader alone |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 6568 | 6552 | -0.2 % | 6989 | 6945 | +5.7 % | -0.6 % |
| syl_bwelk | 8092 | 7950 | -1.8 % | 8857 | 8688 | +7.4 % | -1.9 % |
| compose_bwelk | 2831 | 2665 | -5.9 % | 3609 | 3438 | +21.4 % | -4.7 % |
| screen32 | 265565 | 259951 | -2.1 % | 284804 | 278924 | +5.0 % | -2.1 % |
| line8 | 50481 | 48909 | -3.1 % | 55228 | 53589 | +6.2 % | -3.0 % |
| aa_syl_ga | 14088 | 14072 | -0.1 % | 14608 | 14564 | +3.4 % | -0.3 % |
| aa_syl_bwelk | 17353 | 17211 | -0.8 % | 18306 | 18137 | +4.5 % | -0.9 % |
| aa_line12 | 141424 | 139592 | -1.3 % | 147797 | 145892 | +3.2 % | -1.3 % |
| aa_screen10 | 1461059 | 1450597 | -0.7 % | 1501876 | 1490857 | +2.0 % | -0.7 % |

RGB565 `-Os`:

| case | BASE | v1 | v1 vs BASE | v2 reader alone | v2 | v2 vs BASE | v2 vs reader alone |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 9077 | 9025 | -0.6 % | 9454 | 9392 | +3.5 % | -0.7 % |
| syl_bwelk | 11627 | 11448 | -1.5 % | 12344 | 12154 | +4.5 % | -1.5 % |
| compose_bwelk | 3375 | 3188 | -5.5 % | 4131 | 3938 | +16.7 % | -4.7 % |
| screen32 | 412889 | 406557 | -1.5 % | 431377 | 424851 | +2.9 % | -1.5 % |
| line8 | 71389 | 69638 | -2.5 % | 75951 | 74152 | +3.9 % | -2.4 % |
| aa_syl_ga | 17902 | 17850 | -0.3 % | 18379 | 18317 | +2.3 % | -0.3 % |
| aa_syl_bwelk | 22568 | 22389 | -0.8 % | 23475 | 23285 | +3.2 % | -0.8 % |
| aa_line12 | 181859 | 179828 | -1.1 % | 187810 | 185726 | +2.1 % | -1.1 % |
| aa_screen10 | 1797048 | 1785203 | -0.7 % | 1834149 | 1821931 | +1.4 % | -0.7 % |

RGB565 `-O2`:

| case | BASE | v1 | v1 vs BASE | v2 reader alone | v2 | v2 vs BASE | v2 vs reader alone |
|---|---:|---:|---:|---:|---:|---:|---:|
| syl_ga | 8030 | 8014 | -0.2 % | 8451 | 8407 | +4.7 % | -0.5 % |
| syl_bwelk | 10082 | 9940 | -1.4 % | 10847 | 10678 | +5.9 % | -1.6 % |
| compose_bwelk | 2831 | 2665 | -5.9 % | 3609 | 3438 | +21.4 % | -4.7 % |
| screen32 | 380103 | 374489 | -1.5 % | 399342 | 393462 | +3.5 % | -1.5 % |
| line8 | 63055 | 61483 | -2.5 % | 67802 | 66163 | +4.9 % | -2.4 % |
| aa_syl_ga | 15915 | 15899 | -0.1 % | 16435 | 16391 | +3.0 % | -0.3 % |
| aa_syl_bwelk | 20095 | 19953 | -0.7 % | 21048 | 20879 | +3.9 % | -0.8 % |
| aa_line12 | 162803 | 160971 | -1.1 % | 169176 | 167271 | +2.7 % | -1.1 % |
| aa_screen10 | 1602901 | 1592439 | -0.7 % | 1643718 | 1632699 | +1.9 % | -0.7 % |

### Cortex-M33 under QEMU (instructions per iteration, MONO_PAGE; not time)

| case | `-Os` BASE | `-Os` v1 | `-Os` v2 | `-O2` BASE | `-O2` v1 | `-O2` v2 |
|---|---:|---:|---:|---:|---:|---:|
| syl_ga | 3290 | 3308 | 3495 | 2583 | 2626 | 2824 |
| syl_bwelk | 3856 | 3874 | 4234 | 3088 | 3132 | 3516 |
| compose_bwelk | 1518 | 1527 | 1901 | 1348 | 1368 | 1770 |
| screen32 | 102525 | 102848 | 111958 | 81375 | 82090 | 91900 |
| line8 | 24398 | 24479 | 26730 | 19170 | 19348 | 21774 |

The v1 face on the M33 is up to 1.7 % above BASE in instruction count (`-O2` `syl_ga` 2583 -> 2626, `screen32` 81375 -> 82090,
+0.9 %): the dual-reader build decomposes v1 syllables with the multiply-shifts and validates the block once at open; the Pico
rows, which carry the gate, are below BASE.

### Uno

| | BASE | this tree (v1 face; the AVR default reads version 1 alone) |
|---|---:|---:|
| flash of 32256 B (face 8716 B) | 27434 | 27430 (code and constants 18714, was 18718) |
| RAM of 2048 B before the stack | 1223 | 1224 |
| `syl_ga` / `syl_bwelk` / `compose_bwelk` / `screen32` (cycles) | 17208 / 20113 / 8414 / 523325 | 17208 / 20113 / 8414 / 523325 |

Divide symbols left in the Cortex-M0+ P1 link (`c/cross/SIZES.md`, JSET section): `__udivsi3` 266 B + `__aeabi_uidivmod` 8 B, because `svf_draw` still divides (17 call sites); `svf_jamo.o` call sites 1 default / 5 v1-only / 0 v2-only, BASE 6.

### Fuzz (one hour each under ASan/UBSan, validation on, corpus of v1 and v2 seeds)

`make -C c fuzz fuzz-rd fuzz-corpus`, then `fuzz-open` (libFuzzer + ASan/UBSan, `-DSVF_FUZZ_POISON`, JSET validation on, both readers) and
`fuzz-open-rd` (the same with the `SVF_RD8` accessor build), each `-fork=16 -max_total_time=3600 -max_len=2000000` over the same
corpus directory, run one after the other through `heavy` (2026-10-25/26). The seed corpus holds 987 files, 4 of them JSET v2
faces (`v2-default-HGKEY6J.SVF`, `v2-default-NSQRB16.SVF`, `v2-mcu-strict-HGKEY6J.SVF`, `v2-mcu-strict-NSQRB16.SVF`) and 42 bad-JSET kinds in 5 v2
variants (Task 8); the two runs grew it to 1,666 files.

| run | executions | coverage line (last) | exit | crashes |
|---|---:|---|---:|---:|
| `fuzz-open` | 1,592,261 | `cov: 1064 ft: 4955 corp: 1038`, 3607 s | 0 | none (`artifacts/` empty) |
| `fuzz-open-rd` | 826,218 | `cov: 1184 ft: 5558 corp: 964`, 3600 s | 0 | none (`artifacts-rd/` empty) |

`python3 -I c/tests/fuzz_replay.py c/build/svfdump-asan c/build/fuzz/corpus` (the C reader against `jamoset.parse_svfn` over the grown
corpus, 1,666 files): the first replay found one disagreement, "cell of U+3157 differs", on a file the `fuzz-open-rd` run added
(`corpus/2b7e0744...`, 22,768 B, kept in the corpus): a JSET v1 face whose compat entry for U+3157 names plane-15 piece 159 while its glyph
table also holds a different U+3157 glyph. The spec draws a compat code point with a compatPiece as that piece alone
(`spec/SVF.md`), and the C reader, c592140's reader and `jamoset.unpack().compat` all do; the replay oracle compared the raw table
glyph. The oracle now follows the compat piece (`compat_pieces` in `c/tests/fuzz_replay.py`; test `TestFuzzReplayCompat` in
`tools/test_c_renderer.py` builds the situation from HGKEY6J and fails on the old oracle). Replay over the same corpus: files=1666
disagreements=0, exit 0; no sanitizer report.

## Against the budgets

Note (2026-10-26): the result tables above were re-taken in the compact JSET Task 10 (shipped JSET v1 faces, default builds, HEAD of ccd0190 + docs); the figures in this section's prose and table are the earlier 8bff82e measurements, and "Before -> after JSET v1 + v2" above gives the current Pico, Uno and DOS verdicts (Pico `-Os` `syl_ga` 6091 cycles = 48.7 µs met, `syl_bwelk` 7321 = 58.6 µs still over, `screen32` 188251 = 1.51 ms met; re-taken 2026-10-27 at 1cbe1f2: 6049 = 48.4 µs, 7279 = 58.2 µs, 187299 = 1.50 ms, same verdicts; DOS DX2-66 mapped 11.88 ms, streamed warm 12.82 ms, met).

Before = 2026-10-19 (library 91fa206). After = the C speedups 6-10 on SVF v3, library at 8bff82e, measured 2026-10-23 (the rows of the result tables
above; WASM is the median of four runs). The v3 figures before the speedups (4539e42) are in "Before -> after the C speedups". Every Pico, DOS and Uno figure is **emulated** (rp2040js, DOSBox-X, simavr); the WASM row is the
host CPU. The DX-33 rows hold the same 16 ms budget at half the clock (the line was budgeted for the DX2-66 class).

| budget | before (2026-10-19) | after (C speedups) | verdict |
|---|---|---|---|
| Pico 125 MHz `-Os` (P1 size profile), <= 50 µs a composed and drawn 16 px syllable | 113.0 µs (가) / 125.8 µs (뷁) | 49.1 µs (가; 49.4 at 4539e42) / 60.0 µs (뷁; 60.5) | 가 **met** (1.02x margin); 뷁 **still over**, 1.20x |
| Pico `-O2`, same budget | 70.6 / 84.3 µs | 39.8 / 48.5 µs | **met** for both (1.03x margin for 뷁) |
| Pico `-Os`, <= 2 ms a 128 x 64 MONO_PAGE screen of 32 glyphs | 3.63 ms | 1.56 ms | **met** (1.28x margin) |
| Pico `-O2`, same budget | 2.31 ms | 1.26 ms | **met** (1.58x margin) |
| DOS 486DX2-66 preset, <= 16 ms one PAPLG16 + PAPLG18 line, mapped | 23.0 ms | 11.9 ms (emulated; 12.5 at 4539e42) | **met** (1.35x margin) |
| DX2-66, mapped + syllable cache | 17.8 ms | 9.2 ms (emulated) | **met** (1.73x margin) |
| DX2-66, streamed warm | 22.9 ms | 12.8 ms (emulated) | **met** (1.25x margin) |
| DX2-66, streamed cold (first draw, 42 reads) | 37.2 ms | 23.0 ms (emulated) | **still over**, 1.44x |
| DX-33 preset, mapped / mapped + cache / streamed warm / cold | 45.9 / 35.4 / 45.6 / 66.2 ms | 23.6 / 18.4 / 25.5 / 40.6 ms (emulated) | **still over**: 1.48x / 1.15x / 1.59x / 2.54x |
| WASM, <= 1 ms the sample line | 13.9-33.6 µs warm, 81.9 µs first streamed draw | 10.5-13.1 µs warm (`line40_mapped` 16.6 µs in a spread of 14.0-20.6), 84.2 µs first streamed draw (median of four) | **met** (60x margin or more) |
| Uno fit: links with one ~9 KB 1 bpp jamo face in PROGMEM and draws | flash 25,854 of 32,256 bytes (bench build) | bench build (`-DSVF_TARGETS=0x1F`, `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`) 27,434 B, 4,822 B to spare, RAM 1,223 of 2,048 B before the stack; Arduino port build with `-DSVF_TARGETS=0x02` 22,270 B, 9,986 B to spare; every Uno row identical to 4539e42 (`SVF_MERGE_WORDS` and `SVF_GRAY8_LUT1` are 0 on AVR, and the Uno builds have no scaler) | **met**; checksums `ok` |

What the speedups did to the verdicts: one changed, to met: DOS DX2-66 `line40_24_indexed8` went from over budget to met (16.16 -> 14.94 ms); no other verdict moved. Pico `syl_ga` `-Os` stays met (49.43 -> 49.14 µs, 1.7 % under the line: the single-kind MONO_PAGE build is what the budget names), `syl_bwelk` `-Os` stays over (60.48 -> 60.00 µs, 1.20x). The DOS DX2-66 mapped, cached and streamed-warm rows are 1 to 5 % faster (more margin); the DX-33 rows are 1 to 5 % faster and all stay over. The scaled line
(`line40_scaled32`, no budget) is 1.5x faster.

Colour and grey on small panels: no budget (user, 2026-10-20). Measured (emulated, Pico, single-kind builds, C speedups, 2026-10-23): RGB565 `syl_ga` 72.6 µs `-Os` / 64.2 µs `-O2`, `syl_bwelk` 93.0 / 80.7 µs, `screen32` 3.30 / 3.04 ms, `aa_line12` (a 12 code point 2 bpp line on a 240 x 24 band) 1.45 / 1.30 ms, `aa_screen10` 14.4 / 12.8 ms; GRAY8 `syl_ga` 59.6 / 52.5 µs, `syl_bwelk` 75.0 / 64.7 µs, `screen32` 2.34 / 2.12 ms, `aa_line12` 1.26 / 1.13 ms, `aa_screen10` 12.6 / 11.7 ms. The XIP cache is not modelled: real figures are these or slower. The ESP32 numbers are instruction counts and carry no budget verdict.

Library size (`c/cross/SIZES.md`, re-measured 2026-10-23 with `c/cross/build-all.sh` at 8bff82e, `-Os`, text bytes): Cortex-M0+
P1/P2 6194 (6022 before the speedups, 5674 before v3), P3 8192, P4 14068, **P1* (every one of the nine target kinds) 9190**;
ESP32-C3 P1 7391, P1* 10758, P4 16654. The 8192-byte size budget is the Cortex-M0+ P1/P2 profile (MONO_PAGE only, the
OLED target): it is met with 1998 B to spare (**2026-10-26, default build with both JSET readers: P1/P2 7441, 751 B to spare; P1* 10437, 2245 B over**; the figures in this paragraph are the 8bff82e ones). P1* is **998 B over** 8192. **Decision (user, 2026-10-21, renewed 2026-10-22
for the v3 figure of Task 7: the 8 KB budget stays on P1/P2 (MONO_PAGE only). P1* at 8794 B, 602 B over, was accepted ("빌드크기 ok"): a small
target chooses its kinds through `SVF_TARGETS`.** Task 8 of v3 moved P1* to 8826 B (+32 B). The C speedups moved it to 9190 B (+364 B: the word merge +176, the nibble table +192, the midpoint shift -8, its 16-bit fix +4); each step was under the plan's 200 B stop, the sum is over it,
and the user has accepted only the earlier figures: **reported to the user, not yet separately accepted.**

## Findings

The findings below were written on the pre-v3 tree (2026-10-20/21): their figures are v2's, and the v3 figures are in the result tables and in "Before -> after SVF v3" above.

- **The C speedups 6-10 (2026-10-23, 4539e42 -> 8bff82e; tables in "Before -> after the C speedups").** All four library changes paid on their targets and one budget verdict flipped, to met (DOS DX2-66 `line40_24_indexed8`, 16.16 -> 14.94 ms; the Task 10 report's "no verdict flipped" was wrong). The 1 bpp GRAY8 nibble table (Task 7) is the largest single gain on the Pico (GRAY8 `-Os` `syl_ga`
  64.95 -> 59.58 µs; `blit_gray8` 50.9 -> 31.0 % of the profile build's `syl_ga`) and on the Cortex-M33 (`-O2` 1.40-1.59x); it was measured on the ESP32-S3's real silicon and *loses* there (+2.6 to +24 % cycles), so Xtensa keeps the bit loop. The word merge (Task 6) gives DOS `line40_mapped` -4.7 % and
  M33 `aa_syl_bwelk` 6 to 11 %, and nothing on the Pico's MONO_PAGE rows (the budget rows). The separable box filter (Task 8) makes `line40_scaled32` 1.18 to 1.79x faster (1.53x on the DOS presets): below the 1.8-2.4x the plan estimated, so scaled text stays about 1.5x rather than 2x
  until a column-sum pass; it costs +312 B in the scaler profiles and about 0.9 KB of stack on AVR (`c/cross/SIZES.md`). The midpoint shift (Task 9) is worth -0.6 to -0.8 % on the Pico and -7 to -10 % on Hazard3 `-Os`; its 16-bit overflow was a real bug on AVR (T9-F1, fixed). What the speedups did **not** move: the
  Pico `syl_bwelk` `-Os` budget (60.0 µs against 50, the cost is compose: `svf__glyph_index` 15 %, `svf__put_rows` 8 % of the syllable), every DOS cold, small-cache and DX-33 row beyond a few percent, MONO_PAGE and RGB565 on every chip beyond 1-2 %, the Uno (switches 0), and ESP32 1 bpp GRAY8 (C3 within noise, S3 table off).
  A few rows got slower and are named in the ESP32-S3 / Hazard3 sections above (Hazard3 `-O2` GRAY8 2 bpp +3 to +4 %, Hazard3 `-Os` `line40_mapped_cache` +3.2 %, C3 `-Os` GRAY8 `syl_ga` +1.3 %).
- **Pico: the blit is no longer two thirds of a syllable.** `syl_ga` fell from 14,126 to 6,070 cycles at `-Os`
  (5,357 at `-O2`) with every kind compiled in, and is 6,335 (5,452) in the single-kind MONO_PAGE build; `screen32` fell
  from 453,194 to 193,280 (173,335 at `-O2`), 202,367 (176,720) single-kind. The fast paths are the dispatch per target
  kind, MONO_ROW shifted ORs, and MONO_PAGE by 8 x 8 bit transpose (no per-pixel bpp test).
- **What the blit costs per pixel now (`PROFILE=1 c/bench/run-pico.sh`).** In the profile build `blit_mono_page`
  is still the top symbol: 29.9 % of `syl_ga` (200,100 of 669,504 cycles over 100 iterations) at `-Os`, 22.7 % at
  `-O2` (135,100 of 595,314); `screen32` 30.5 % / 23.3 %. That does not mean the blit is slow: the profile build
  disables inlining (`-fno-inline-functions-called-once -fno-inline-small-functions`; 6,695 cycles instead of 6,335
  for `syl_ga` at `-Os`), so `blit_mono_page` absorbs the work of the helpers that normally inline into it, and drawing
  a page-packed glyph is the bulk of drawing one. Per pixel: `blit_mono_page` plus `transpose8` is about 2,400 cycles
  per `syl_ga` at `-Os`, 9.4 cycles for each of its 256 pixels (about 39 before), and 6.9 at `-O2`; over `screen32`
  (8,192 pixels a screen) `blit_mono_page` alone costs 7.9 (`-Os`) and 5.3 (`-O2`) cycles a pixel. Behind the blit
  at `-Os`: `svf__merge` 12.2 %, `svf__glyph_index` 11.3 %, `rd32` 6.6 %, `transpose8` 6.0 %, `svf_draw_utf8` 3.9 %,
  `memset` 3.9 %, `svf_jamo_pieces` 3.6 %, `svf_compose` 2.2 %.
- **What remains is compose and decode.** `compose_bwelk` is 3,603 cycles of the 7,744 for `syl_bwelk` (47 %), 3,620
  in the profile build with `svf__merge` 34 %, `svf__glyph_index` 25 % and `rd32` 15 % of it; a 3-piece syllable pays
  twice what a 2-piece one does in `svf__merge`/`svf__glyph_index`. `syl_bwelk` misses the 50 µs design budget (62.0 µs
  `-Os`, 53.9 µs `-O2`), and `syl_ga` at `-Os` by 1.4 % in the single-kind build.
- **Pico, the kinds against each other (cycles, emulated, single-kind builds; ratios in the generated tables below).**
  The expectation that GRAY8 at 1 bpp would sit close to MONO_PAGE did not hold: GRAY8 costs about 1.3-1.7x of MONO_PAGE and
  RGB565 about 1.5-2.3x, the most on `screen32`, the case that also clears and fills the larger buffer (8 KB, 16 KB against
  1 KB); `compose_bwelk` is the same in all three kinds (3,603 / 3,489 cycles), so the whole difference is in the blit and the
  buffer. RGB565 costs a further 1.1x over GRAY8 on the other cases. The 2 bpp band cases (set B, PAPLG16 + PAPLG18) cost far more
  than the 1 bpp ones (GRAY8 `aa_syl_ga` 21,903 cycles against 8,275 for `syl_ga` at `-Os`; `aa_line12` 224,879 cycles for 12
  code points). Why GRAY8 pays more than a page-packed blit was not isolated (a byte a pixel instead of eight pixels a byte is
  the obvious difference; this is not measured).
- **`blit_rgb565`'s share (the VESA card t_6ab9ec2d; `PROFILE=1 c/bench/run-pico.sh`, RGB565 builds; emulated; re-measured
  2026-10-21 on the merge, post-VESA).** The RGB565 blit is now VESA's `blit_rgb16` (the body shared with RGB555, the blend
  passed as a function pointer; the profile lists it as `blit_rgb16.constprop.0`, with its pixel helper `rgb16_pix` as a
  separate 1.0-1.5 %). The profile build disables inlining, so a share is an upper bound for the blit in the plain build (as
  for `blit_mono_page` above). At `-Os`: `syl_ga` 47.7 % (4,658 of 9,768 cycles an iteration), `syl_bwelk` 47.4 % (5,843 of
  12,325), `screen32` 34.9 % (151,523 of 434,708), `line8` 51.0 %, and in the 2 bpp path `aa_syl_ga` 35.8 % (8,707 of
  24,350), `aa_syl_bwelk` 34.7 %, `aa_line12` 38.5 % (97,999 of 254,271), `aa_screen10` 30.7 %. At `-O2`: 44.9 % (4,046 of
  9,017), 44.8 %, 32.0 %, 48.1 %, 39.6 %, 38.6 %, 42.9 %, 39.8 %. `blend565` (the 8 bpp-path blend) is separate and small:
  1.0-2.4 % in the cases where the profile lists it (not `aa_syl_ga`, `aa_syl_bwelk`, nor `-Os` `aa_screen10`). So the
  blit is at most about half of an RGB565 syllable. Against the pre-VESA blit (2026-10-21, mcu-ports) the plain builds
  moved by at most 0.04 % at `-Os`; at `-O2` the 1 bpp cases are 0.9-1.5 % slower and the 2 bpp ones 1.7-3.0 % faster. The
  cycles and instructions of the plain builds are in the RGB565 table above (`syl_ga` 9,269 cycles / 6,427 insns `-Os`,
  8,504 / 6,182 `-O2`; `aa_line12` 248,198 / 172,660 and 197,623 / 154,339; `screen32` 420,673 / 284,447 and
  398,784 / 278,548; `aa_screen10` 2,229,310 / 1,535,122 and 1,831,935 / 1,413,571). The MCU word-store default
  (t_47ca86d1) should be judged on these post-VESA rows.
- **The Pico, the C3 and the S3 in instructions** (set A and B, per iteration; the Pico's `insns` against the C3's
  `rdinstret`, the S3's core-0 `ICOUNT` beside them; ratios in the generated tables below). **Instruction counts only, not
  time**: a Pico instruction is a Thumb-1 one of one to a few cycles, the C3's and S3's cycles per instruction are unknown, so
  only the Pico column also exists as cycles. The Pico executes more instructions than the C3 in every case, from 1.12x
  (`compose_bwelk`, `-Os`) up to 2.2x (RGB565 `screen32`, `-O2`, the largest gap); the S3 count is within 0.82-1.02x of the C3's.
  Why the Pico executes more instructions on the wider kinds was not investigated. Neither is a time, and the S3 and C3 are
  different compilers' code, not a speed comparison of the chips.
- **DOS: with the GRAY8 row pointers the line is under 16 ms on the DX2-66 preset** (15.2 ms mapped, 15.1 streamed
  warm, 10.0 ms with the syllable cache), within 6 % of the budget without the cache; on the DX-33 preset only the
  cache build comes close (19.8 ms). A cold first draw still reads 42 blocks (29.3 ms), and caches smaller than
  the line's working set (28.8 ms with 4/16 slots) or none (24.9 ms) are over by 1.6-1.8x. The block-read cost is
  about 0.34 ms a 1 KB block as before ((29.3 - 15.1) ms / 42 reads).
- **DOS: a block cache smaller than a line's working set reads on every draw** (unchanged finding): 43 blocks a draw
  with 16 slots; size the cache to the blocks a screen touches (64 slots, 66 KB) or use smaller blocks.
- **Mapped is still slower than streamed-warm on the WASM build** (22.0 vs 13.2 µs); the DOS presets show no gap
  (15.2 vs 15.1 ms). Not investigated: it does not bear on a budget.
- **Uno**: a syllable takes 1.16-1.37 ms and a 32-glyph screen 35.7 ms at 16 MHz (no budget), about 2.1x faster than
  before; the bench build's flash grew to 31,302 B (`-DSVF_TARGETS=0x1F`, the five original kinds), the port build
  (MONO_PAGE only) is 26,442 B.
- **WASM** meets its budget by more than 45x on this host.
- **Packed kinds on DOS (emulated, DX2-66)**: the three RGB16/INDEXED8 kinds of the 16 px line cost 14.7 to 14.8 ms,
  8 % under the budget with the word paths and over it for RGB555/RGB565 without (16.1 ms); XRGB8888 and RGB888 cost 16.2 and
  16.5 ms, 1 % and 3 % over, with no word path to give back. A 24 px line costs about 1.4x the 16 px line with the 2 bpp
  face and 0.83x to 0.90x with the 1 bpp face (a 1 bpp source decodes faster; not investigated further). The 1 bpp INDEXED8 word path was slower
  than the byte loops and is gone; the Uno, Pico and WASM rows do not depend on it.

### Ratios between the tables (generated)

The block between the markers is produced from the result tables above by `python3 -I c/bench/check-measurements-md.py --print
c/bench/MEASUREMENTS.md`, and checked against them (and the µs columns against the counts) by `tools/test_c_renderer.py`, so by
`make -C c check`. The markers are part of the file.

<!-- ratios:begin -->
Pico cycles per iteration against MONO_PAGE (GRAY8 / MONO_PAGE, RGB565 / MONO_PAGE) and RGB565 against GRAY8, single-kind builds:

| case | `-Os` GRAY8 / MONO | `-Os` RGB565 / MONO | `-Os` RGB565 / GRAY8 | `-O2` GRAY8 / MONO | `-O2` RGB565 / MONO | `-O2` RGB565 / GRAY8 |
|---|---:|---:|---:|---:|---:|---:|
| syl_ga | 1.22x | 1.49x | 1.22x | 1.32x | 1.62x | 1.23x |
| syl_bwelk | 1.26x | 1.57x | 1.25x | 1.34x | 1.68x | 1.25x |
| compose_bwelk | 1.00x | 1.00x | 1.00x | 1.00x | 1.00x | 1.00x |
| screen32 | 1.52x | 2.17x | 1.42x | 1.71x | 2.46x | 1.44x |
| line8 | 1.25x | 1.56x | 1.25x | 1.37x | 1.72x | 1.26x |
| aa_syl_ga | - | - | 1.13x | - | - | 1.13x |
| aa_syl_bwelk | - | - | 1.14x | - | - | 1.16x |
| aa_line12 | - | - | 1.15x | - | - | 1.15x |
| aa_screen10 | - | - | 1.14x | - | - | 1.10x |

Instructions per iteration, Pico `insns` / C3 and S3 core-0 `ICOUNT` / C3 (counts, not time):

| kind | case | `-Os` Pico / C3 | `-Os` S3 / C3 | `-O2` Pico / C3 | `-O2` S3 / C3 |
|---|---|---:|---:|---:|---:|
| MONO_PAGE | syl_ga | 1.16x | 0.92x | 1.20x | 0.87x |
| MONO_PAGE | syl_bwelk | 1.14x | 0.91x | 1.18x | 0.87x |
| MONO_PAGE | compose_bwelk | 1.14x | 0.85x | 1.23x | 0.83x |
| MONO_PAGE | screen32 | 1.23x | 0.94x | 1.26x | 0.89x |
| MONO_PAGE | line8 | 1.18x | 0.95x | 1.20x | 0.88x |
| GRAY8 | syl_ga | 1.13x | 0.82x | 1.19x | 0.79x |
| GRAY8 | syl_bwelk | 1.10x | 0.85x | 1.17x | 0.80x |
| GRAY8 | compose_bwelk | 1.14x | 0.85x | 1.23x | 0.83x |
| GRAY8 | screen32 | 1.47x | 0.85x | 1.54x | 0.86x |
| GRAY8 | line8 | 1.15x | 0.84x | 1.19x | 0.80x |
| GRAY8 | aa_syl_ga | 1.31x | 1.00x | 1.31x | 0.94x |
| GRAY8 | aa_syl_bwelk | 1.30x | 1.02x | 1.30x | 0.93x |
| GRAY8 | aa_line12 | 1.35x | 1.02x | 1.33x | 0.95x |
| GRAY8 | aa_screen10 | 1.79x | 1.03x | 1.79x | 0.97x |
| RGB565 | syl_ga | 1.42x | 0.83x | 1.51x | 0.85x |
| RGB565 | syl_bwelk | 1.38x | 0.83x | 1.47x | 0.83x |
| RGB565 | compose_bwelk | 1.14x | 0.85x | 1.23x | 0.83x |
| RGB565 | screen32 | 2.01x | 0.85x | 2.16x | 0.96x |
| RGB565 | line8 | 1.46x | 0.84x | 1.53x | 0.85x |
| RGB565 | aa_syl_ga | 1.38x | 0.91x | 1.47x | 0.96x |
| RGB565 | aa_syl_bwelk | 1.37x | 0.92x | 1.48x | 0.96x |
| RGB565 | aa_line12 | 1.43x | 0.92x | 1.50x | 0.97x |
| RGB565 | aa_screen10 | 1.45x | 0.88x | 1.84x | 0.93x |
<!-- ratios:end -->

### Still over budget

Figures of the C speedups run (2026-10-23, library at 8bff82e; the result tables above were re-taken on 2026-10-27, Pico `syl_bwelk` is now 7279 cycles = 58.2 µs, 1.16x, the other figures here are the 2026-10-23 ones); the factor is measured / budget. The rows now met are gone (DOS DX2-66 `line40_mapped` 11.9 ms and warm 12.8 ms were already met). The follow-up cards: **t_4108b260** (Pico `syl_bwelk`: the 50 µs budget applies with the syllable cache on, user 2026-10-21) and **t_8a3815c4** (DOS cold, small cache and DX-33).

| platform | case | measured | budget | factor | follow-up card needed |
|---|---|---:|---:|---:|---|
| Pico `-Os` | syl_bwelk (3-piece syllable) | 60.0 µs | 50 µs | 1.20x | **t_4108b260**: the syllable cache on the Pico (the budget applies with it on); the measured remainder is compose (`svf__glyph_index` 15 %, `svf__put_rows` 8 % of the profile build's syllable) and the blit, 3,375 of 7,500 cycles for `compose_bwelk` (the v2 profile: 3,603 of 7,744) |
| DOS 486DX2-66 | line40 streamed cold (first draw) | 23.0 ms | 16 ms | 1.44x | **t_8a3815c4**: syllable cache as the recommended default and a warm-up pass; 32-bit / mode 13h (target-specific) |
| DOS DX2-66 | line40 stream_small (4/16-slot caches) | 20.2 ms | 16 ms | 1.26x | **t_8a3815c4**: size the block cache to the working set (documented), or the syllable cache default |
| DOS DX2-66 | line40 stream_nocache | 22.3 ms | 16 ms | 1.40x | **t_8a3815c4**: same |
| DOS 486DX-33 | mapped / mapped + cache / warm / cold | 23.6 / 18.4 / 25.5 / 40.6 ms | 16 ms | 1.48x / 1.15x / 1.59x / 2.54x | **t_8a3815c4**: syllable cache as the recommended default (1.15x), 32-bit / mode 13h for the rest |
| DOS DX-33 | stream_small / nocache | 36.0 / 41.0 ms | 16 ms | 2.25x / 2.56x | **t_8a3815c4**: same |
| DOS DX2-66 | line40_24_<kind> (MARUS24A, 2 bpp, 640 x 32), word build | rgb565 14.51 and rgb555 14.53 met (were 15.72, 15.75), indexed8 14.94 met (was 16.16); xrgb8888 17.08 and rgb888 17.47 over (were 18.29, 18.68) | 16 ms | up to 1.09x | **t_8a3815c4**: only the two 32/24 bpp kinds are left; or use the 1 bpp MARUS24 (meets on all three kinds measured) |
| DOS DX-33 | every 16 px and 24 px packed row | 22.7 to 34.8 ms | 16 ms | 1.42x to 2.17x | **t_8a3815c4**: same as the DX-33 GRAY8 line |

Rows dropped as now met: DOS DX2-66 `line40_24_indexed8` (16.16 -> 14.94 ms), `line40_24_rgb555` and `line40_24_rgb565` (were met, now with more margin). The DOS DX2-66 `line40_xrgb8888` and `line40_rgb888` rows (12.9 and 13.1 ms) were already under 16 ms.

Not listed, because not measured over: ESP32 DMA (the ESP32 numbers are instruction counts under QEMU, no time and no budget) and the AVR PROGMEM
page path (no Uno speed budget; the Uno case fits with room).

## Screens

`sh c/ports/check/run-screens.sh` (and `c/cross/build-all.sh --ports`, which runs it) builds the three real Pico images
with pico-sdk 2.3.1 and the two bare ESP32 colour images, runs each to its last frame on the emulated panel, and
compares the panel memory byte for byte with the `svfline` reference (the ESP32 `screendump` PPM too). Results of the
2026-10-23 run (C speedups, 8bff82e; the b45e9dc run gave 4,929,286, 1,900,193 and 353,790 cycles, and the 2026-10-21 v2 run gave 4,887,430, 1,782,010 and 323,106 cycles: the whole-program counts rose by 0.9 %, 6.6 % and 9.5 % although every drawing case above got faster; they include `svf_open`, which now validates every record of a mapped face, and the cause was not isolated) (**emulated**; the clock is rp2040js's, so `cycles` is rp2040js's instruction-cycle counter
(including 8 extra cycles for each use of the SIO hardware divider, which the clock does not see) and `nanos` its emulated
clock, in which the init `sleep_ms` delays count (242 ms in the colour image); the two do not convert into each other
at 125 MHz, and neither is a drawing time; the ESP32 runs report no time):

| screen | panel model | result | shows | cycles (instruction counter, emulated) | nanos (emulated clock, sleeps included) | PNG (not committed) |
|---|---|---|---:|---:|---:|---|
| pico colour | rp2040js ST7789 240 x 240 | OK | 15 | 4,896,236 | 280,633,728 | `c/build/screens/pico-colour.png` |
| pico grey | SSD1327 128 x 128 | OK | 1 | 1,868,488 | 14,551,360 | `c/build/screens/pico-grey.png` |
| pico mono | SSD1306 128 x 64 | OK | 1 | 349,000 | 2,771,520 | `c/build/screens/pico-mono.png` |
| esp32c3 colour | QEMU `esp_rgb` 320 x 240, `-M esp32c3` | OK (screendump and VRAM) | - | - | - | `c/build/screens/esp32c3-colour.png` |
| esp32s3 colour | QEMU `esp_rgb`, `-M esp32s3` | OK (screendump and VRAM) | - | - | - | `c/build/screens/esp32s3-colour.png` |

Each `*-ref.png` beside them is the reference. The Pico screens also print the image's link size (`arm-none-eabi-size`,
the table "Pico SDK images" of `c/cross/SIZES.md`). Two proofs that the check bites were run once on 2026-10-21 (06f5154): a wrong byte
in a text string makes the run fail with an offset and a diff PNG, and a split (`nostop`) SSD1306 control byte makes
the mono run fail.

## SVF_JSET_BIG hot path (2026-10-27, JSET v3 / JMAP / BIG plan Task 17, card t_380104f8)

`SVF_JSET_BIG` (19 x 28 classes, 128 / 128 / 64 sets) is not in the hot path: the Pico MONO_PAGE builds (`c/bench/run-pico.sh`, rp2040js 1.4.0, gcc 15.2.1, `PICO_KINDS=MONO_PAGE:0x02`, HGKEY6J, `mcu-strict`) were run twice, at the Cortex-M0+ defaults (`SVF_JSET_BIG` 0) and with `BENCH_CFLAGS=-DSVF_JSET_BIG=1` (the script's flag hook, added in this task). Every case is equal, cycle for cycle and instruction for instruction, in both optimisations (the only raw difference is `total_cycles` of the whole run, 10200430 against 10200403, which includes the one-off open of the three faces):

| Pico MONO_PAGE `-Os` | syl_ga | syl_bwelk | compose_bwelk | screen32 | line8 |
|---|---:|---:|---:|---:|---:|
| defaults (BIG 0) | 6049 | 7279 | 3181 | 187299 | 44379 |
| `-DSVF_JSET_BIG=1` | 6049 | 7279 | 3181 | 187299 | 44379 |

`-O2`: 4941 / 5898 / 2661 / 151879 / 35652 in both. These equal the reference of the result tables above (re-taken 2026-10-27 after the `svf_is_jamo` speed-up); checksums unchanged.
