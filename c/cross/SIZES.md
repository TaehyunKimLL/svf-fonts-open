# Cross builds and code size

Measured 2026-10-19, re-measured 2026-10-20 and 2026-10-21 with `c/cross/build-all.sh` (branches mcu-ports and vesa-out,
and their merge); toolchains installed by
`c/cross/install-toolchains.sh` into `~/opt`. Re-run `c/cross/build-all.sh` and replace the table to update.

## Toolchains

| toolchain | version | flags (plus `-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections`, link `-Wl,--gc-sections`) | source |
|---|---|---|---|
| host-gcc | gcc 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1) | `-O2` | system |
| clang | clang 23.1.3 (x86-64 Linux) | `-O2` | LLVM release tarball (below) |
| djgpp | i586-pc-msdosdjgpp-gcc 12.2.0, binutils 2.30 | `-O2` | `~/opt/djgpp`, pre-installed on this host, not fetched by the script (below) |
| cortex-m0plus | arm-none-eabi-gcc 15.2.1 20251203 (Arm GNU Toolchain 15.2.Rel1, build arm-15.86) | `-mcpu=cortex-m0plus -mthumb -Os`; link `--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main` | Arm tarball (below) |
| cortex-m33 | arm-none-eabi-gcc 15.2.1 20251203 (Arm GNU Toolchain 15.2.Rel1, build arm-15.86) | `-mcpu=cortex-m33 -mthumb -Os`; link `--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main` | Arm tarball (below); RP2350 ARM core, no budget (the 8 KB budget is the cortex-m0plus rows') |
| avr-atmega328p | avr-gcc 16.1.0, AVR-LibC 2.3.2, binutils 2.46.1 | `-mmcu=atmega328p -Os -include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'` | Zak Kemble build v16.1.0-1 (below) |
| avr-atmega2560 | avr-gcc 16.1.0, AVR-LibC 2.3.2, binutils 2.46.1 | `-mmcu=atmega2560 -Os -include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'` | the same toolchain as avr-atmega328p; Arduino Mega, 256 KB flash, no budget; near PROGMEM reads only (data below 64 KB) |
| esp32s3-xtensa | xtensa-esp32s3-elf-gcc 16.1.0 (crosstool-NG esp-16.1.0_20260609) | `-mlongcalls -Os` (ESP32-S3); link `--specs=nosys.specs -nostartfiles -Wl,-e,main` | Espressif tarball (below) |
| esp32-xtensa | xtensa-esp32-elf-gcc 16.1.0 (crosstool-NG esp-16.1.0_20260609) | `-mlongcalls -Os` (original ESP32, Xtensa LX6); link `--specs=nosys.specs -nostartfiles -Wl,-e,main` | Espressif tarball (below), the same as esp32s3-xtensa; compile and size only, no port image (note under the port table) |
| esp32c3-riscv32 | riscv32-esp-elf-gcc 16.1.0 (crosstool-NG esp-16.1.0_20260609) | `-march=rv32imc_zicsr_zifencei -mabi=ilp32 -Os` (ESP32-C3); link `--specs=nosys.specs -nostartfiles -Wl,-e,main` | Espressif tarball (below) |
| hazard3-rp2350 | riscv32-pico-elf-gcc 16.1.0 (Raspberry Pi, pico-sdk-tools v2.3.1-0) | `-mcpu=hazard3-rp2350 -mstrict-align -Os` (pico-sdk 2.3.1's flags for `rp2350-riscv`); link `--specs=nosys.specs -nostartfiles -Wl,-e,main` | pico-sdk-tools tarball (below); RP2350 RISC-V core; the pico-sdk's flags; no budget |
| wasm-emcc | emcc 6.0.13 (emsdk tag 6.0.13) | `-O2`, output a standalone `.wasm` | emsdk git (below) |
| sdl3 | 3.5.0-dev (fork ~/opt/src/SDL3, commit 7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06) | host desktop port only | `sh c/cross/install-toolchains.sh "$HOME/opt" sdl3` (the user's fork, built from its working tree) |
| sdl2 | 2.30.0 | | libsdl2-dev (system) |

Downloads (sha256 checked by `install-toolchains.sh` before unpacking; the publisher's value, or computed when it lists none):

| toolchain | URL | sha256 |
|---|---|---|
| clang | https://github.com/llvm/llvm-project/releases/download/llvmorg-23.1.3/LLVM-23.1.3-Linux-X64.tar.zst | `14d2f701eb68fb799001bdea6231048f3990690fa2f406d563555ff8f744daba` |
| arm | https://developer.arm.com/-/media/Files/downloads/gnu/15.2.rel1/binrel/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi.tar.xz | `597893282ac8c6ab1a4073977f2362990184599643b4c5ee34870a8215783a16` |
| xtensa | https://github.com/espressif/crosstool-NG/releases/download/esp-16.1.0_20260609/xtensa-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz (89,005,792 bytes) | `f708752ebb35cab21f184b2574114ed1187619db0edb8a4ba913c06ca2fa675e` |
| avr | https://github.com/ZakKemble/avr-gcc-build/releases/download/v16.1.0-1/avr-gcc-16.1.0-x64-linux.tar.bz2 | `8621ecc6514df50202b58b23b0f8f72f0e535ec35ee40426194e9a15c57692f6` |
| esp | https://github.com/espressif/crosstool-NG/releases/download/esp-16.1.0_20260609/riscv32-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz | `0b029ab31ebc7f74e2c4779077251b21a22cd620669dc4c82e7adc478d403a8d` |
| pico-rv | https://github.com/raspberrypi/pico-sdk-tools/releases/download/v2.3.1-0/riscv-toolchain-16-x86_64-lin.tar.gz (129,680,495 bytes; no top directory in the tarball) | `fc36f1b37f99de54a358115443638023de34e15fe199e718e50cca4d212e7e9f` (the digest GitHub lists for the release asset) |
| ch583 | https://github.com/openwch/ch583.git commit `bd508ad7ceed48377619837051412a651952857f` (WCH EVT; sparse checkout of `EVT/EXAM/SRC`; HEAD checked before checkout; manifest of `EVT/EXAM/SRC` pinned) | (git commit, no archive) |
| wchisp | https://github.com/ch32-rs/wchisp/releases/download/v0.3.0/wchisp-v0.3.0-linux-x64.tar.gz (883,953 bytes) | `67e3d4eb0ffd3cc610d8927e3c3f452e2110531a3f14405dcaef87df219f200d` (computed; the release lists no digest); licence GPL-2.0 (its `Cargo.toml` and root `LICENSE` at v0.3.0, GitHub's licence API; the tarball carries no licence file). wchisp is only run to flash a board, never linked into the image |
| emsdk | https://github.com/emscripten-core/emsdk.git tag `6.0.13`, commit `35659964bc2762fffec0d257997fb61475f765b7` (hard-coded; the script stops unless the clone's HEAD is this commit, before running anything from it); `emsdk install 6.0.13` resolves it to emscripten-releases build `eb132757325583b787fe9414b09afea9442b72ad` (emscripten commit `e13ee988ce3d87a738dd8f3661d02223308c412a`) | (git commit, above) |
| emsdk: node | https://storage.googleapis.com/webassembly/emscripten-releases-builds/deps/node-v24.19.0-linux-x64.tar.xz (fetched by the script, not by emsdk) | `14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647` (nodejs.org v24.19.0 SHASUMS256.txt) |
| emsdk: emscripten-releases build | https://storage.googleapis.com/webassembly/emscripten-releases-builds/linux/eb132757325583b787fe9414b09afea9442b72ad/wasm-binaries.tar.xz (fetched by the script, not by emsdk) | `cda6801012ff3319a539111826ed02a9abd7eff135c2ef261c8941caf5a3763e` (computed; neither emsdk nor Google lists one) |
| djgpp (not fetched by the script) | https://github.com/andrewwutw/build-djgpp/releases/download/v3.4/djgpp-linux64-gcc1220.tar.bz2 (build-djgpp v3.4: gcc 12.2.0, binutils 2.30); the copy on this host, `~/opt/dl/djgpp.tar.bz2` (80596981 bytes), is byte-identical to the release asset downloaded again on 2026-10-19 | `8464f17017d6ab1b2bb2df4ed82357b5bf692e6e2b7fee37e315638f3d505f00` (computed; the release lists no checksum) |

A download that fails its sha256 is deleted and the script stops. emsdk checks no hash of what it downloads, so it
downloads nothing: the script fetches and verifies the two archives `emsdk install 6.0.13` unpacks (node and the
emscripten-releases build, at the URLs emsdk would use), copies them to the names emsdk gives them in
`emsdk/downloads/`, and runs the install with `EMSDK_KEEP_DOWNLOADS=1`, under which emsdk takes an archive already
there ("already downloaded, skipping") instead of fetching it. Both are verified again after the install, before
anything unpacked runs (`activate`, `emcc`); a mismatch removes the unpacked trees. The releases build's sha256 has no
publisher: it was computed from a fresh download on 2026-10-20, whose contents matched the tree installed for the sizes
below file for file (apart from `emscripten-version.txt`, which emsdk writes, and the libraries emcc rebuilds in its
cache). The script was run end to end into a scratch prefix with these archives: emsdk skipped both downloads and the
same `emcc 6.0.13` came up; a tampered archive stopped it before emsdk ran.

## Profiles

Each row links `c/cross/probe.c` (a build probe, not an example) for one profile against the library built with the
toolchain, with `--gc-sections`:

- **P1 Uno**: mapped face, 1 bpp, jamo, `SVF_T_MONO_PAGE`; library built with `-DSVF_NO_SCALE -DSVF_NO_STREAM
  -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` (the stream reader compiled out, one layout read so the units fold to constants); no cache.
- **P2 M0+ OLED**: P1 plus 2 bpp. Bits per pixel is read from the face at run time, so the calls, and the link, are
  P1's.
- **P3 TFT**: mapped, 2 bpp, jamo, `SVF_T_RGB565`, composed-syllable cache (`svf_chain_cache`); `-DSVF_NO_SCALE`.
- **P3w**: P3 built with `-DSVF_WORD_STORE=1` (the object set `rgbw`), to keep the word-store switch on record.
- **P3g grey OLED**: P3 with `SVF_T_GRAY8` instead of `SVF_T_RGB565` (`probe.c` `-DPROBE_KIND=SVF_T_GRAY8`, library built
  with `-DSVF_NO_SCALE -DSVF_TARGETS=0x01`): the core plus the one output path the grey ports use.
- **P4 full** (DOS, WASM): every public function, every target kind (AVR: every kind that existed before GRAY, `-DSVF_TARGETS=0x1FF`; the extra informational row P4+GRAY is the default mask and reads "overflow N B" while it does not fit the 32 KB), a streamed face with a block cache, scaling.
- **P5 VESA** (the DOS example): a streamed face with a block cache, scale 3/2, draws on INDEXED8, RGB555, RGB565,
  XRGB8888 and RGB888; library built with `-DSVF_TARGETS=0x1E8`, scaling on.

A row is the profile's link minus the probe's empty `main` link (P0), in bytes: the library plus what it pulls from
the C library and the compiler runtime (`memcpy`, `memset`, `__aeabi_uidivmod`/`__udivsi3` on Cortex-M0+, 32-bit
helpers on AVR), without startup code. **text** includes read-only data. The library itself has no static data
(every object: data 0, bss 0); **bss** is the probe's own buffers (target, scratch, face), sized to fit the
ATmega328P's 2 KB RAM. DJGPP: text, data and bss are measured to the `etext`/`edata`/`end` marks of its linker
script (its sections are padded to 512 bytes) and its script places `.bss.*` input sections in `.data`, so its
**data** column holds the probe's buffers. WASM: **text** is the module's code section, **data** its data section; a
module has no bss.

## Sizes

Re-taken 2026-10-26 with the SDL target branch rebased onto main (the compact JSET readers and the GRAY kind together, `c/cross/build-all.sh` and `--ports` on the rebased tip): Cortex-M0+ P1/P2 7441 (unchanged), P1* 10437 -> 10681 (+244), P3g 9351 -> 9347, P4 15315 -> 15603, P5 12824 (unchanged); AVR (version 1 JSET reader) P1/P2 12910 -> 12920 (the `svf_target` struct is a byte larger), P1* 20982 -> 21282 (+300), P4 (pinned `0x1FF`) 32560 -> 32558, P5 25490 -> 25492, and the informational AVR row P4+GRAY (default mask) still overflows (its figure is the row of the Sizes table below and its cell in "The GRAY kind on top of JSET"; it is informational and no checker reads it: `check-sizes-md.sh` compares the port, Pico SDK, CH582 SDK and Size switches tables only, and the row appears only when the link overflows by a genuine `overflowed by N bytes` line with no other error in the log). The GRAY kind costs the same on top of JSET as on top of the version 1 reader alone (the per-toolchain deltas equal those of "Before -> after the GRAY kind" below); the table "The GRAY kind on top of JSET" below has main (b872696) against the rebased tip for every toolchain. The Cortex-M0+ P1* growth (+244), the AVR P1* growth (+300) and the Uno image / AVR P1/P2 +10 B were accepted by the user. The paragraph that follows is the JSET measurement of main, taken before the GRAY kind.

Re-taken 2026-10-27 (Group B review round 1, `build-all.sh` at 1cbe1f2): the host-gcc and clang rows (not gated) grew by the JMAP reader, now on by default on the host (`SVF_JMAP=1`): host-gcc P1 14228 -> 16273 (+2045), P1* 22244 -> 24289, P3 19229 -> 21265, P4 33769 -> 35917, P5 27321 -> 29389; clang P1 17327 -> 18907 (+1580), P4 47477 -> 49061; bss +16 (the 16 B larger `svf_face`). The whole table was re-recorded from that run: djgpp P1 13640 -> 15432 (+1792), wasm-emcc P1 12918 -> 14293 (+1375) and the other JMAP-default targets grew likewise; the MCU rows (Cortex-M0+, M33, ESP32, Hazard3, AVR) had not been re-recorded since Tasks 5-6 and now show the current values (Cortex-M0+ P1 7441 -> 7381, AVR P1 12920 -> 12930, Cortex-M33 P1 6743 -> 6689, ESP32-S3 P1 7878 -> 7826, ESP32-C3 8869 -> 8791, Hazard3 7725 -> 7659).

Re-taken 2026-10-26 at ccd0190 (compact JSET Task 10, card t_559aeb6a): the AVR and port rows equal the Task 3 figures below, the Cortex-M0+ default rows are 3 B above Task 3's first commit (its fix round and later code changes: P1/P2 7441, P1* 10437, P3 9439, P4 15315); the host-gcc and clang rows (not gated) are this host's `build-all.sh` run (host-gcc P1 14292 -> 14228, clang P1 17251 -> 17327). Re-measured 2026-10-23 at the compact JSET Task 3 commit (card t_559aeb6a; both JSET block readers, `SVF_JSET_V1` and `SVF_JSET_V2`, in every toolchain's default build except AVR, whose default reads version 1 alone; the reader builds are compared in "Size switches" below): Cortex-M0+ P1/P2 6194 -> 7438, P1* 9190 -> 10434, P3 8192 -> 9436, P4 14068 -> 15312 (the first commit; the table above has the current 7441 / 10437 / 9439 / 15315); AVR (version 1 reader alone) P1 12914 -> 12910, P4 32568 -> 32560. Earlier: re-measured 2026-10-23 at 8bff82e (C speedups Task 10, after the word merge, the 64 B GRAY8 nibble table, the separable box filter and the cmap midpoint shift; the per-profile change against 4539e42 is in "Before -> after the C speedups" below): Cortex-M0+ P1/P2 6022 -> 6194, P1* 8826 -> 9190, P3g 7760 -> 8104, P4 13412 -> 14068, P5 11089 -> 11577. Earlier: 2026-10-23 at b45e9dc (Task 9; the library after Task 8's row-loop pointer fix and fuzz fix round, which add 16 to 32 bytes to every row: Cortex-M0+ P1/P2 5990 -> 6022, P1* 8794 -> 8826, AVR P1 12894 -> 12914, host gcc P1 11813 -> 11681 and clang P1 13414 -> 13654, whose compilers moved the other way or by more). Earlier: 2026-10-22 (SVFN v3 Task 7 fix round 1: the whole table, with P1 and P2 built `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` and P1* with the same switches and every target kind, so P1* - P1 is again the cost of the other kinds; the other profiles read every layout and still link the stream reader). Against Task 7 the reader's speed fixes (the box rows merged in one call or inline, the 2 bpp merge on whole bytes, one cache lookup a record) add 160 bytes to Cortex-M0+ P1/P2 (5830 -> 5990) and 464 to P3 (7524 -> 7988), 464 to P4. The paragraph that follows is the 2026-10-21 measurement's, whose numbers are the pre-v3 ones.

Re-measured 2026-10-21 (Task 10, after the 1 bpp INDEXED8 word path was dropped: only the toolchains whose switch is 1 moved, see the word-store table) after the VESA packed kinds and the word stores (INDEXED8, RGB555, XRGB8888, RGB888; `SVF_TARGETS` has nine bits,
default `0x1FF`). P1/P2 build with `-DSVF_TARGETS=0x02`, P3 and P3w with `0x08`, P3g with `0x01`, P4 with every target that existed before the GRAY kind (`0x1FF` on AVR: the Uno's 32 KB does not hold the GRAY kind, and a build that does not draw GRAY lowers `SVF_TARGETS` -- the default mask `0x3FF` includes it on AVR too; the row "P4+GRAY", the default mask, is informational and may overflow; every target, `0x3FF`, on the other toolchains), P5 with `0x1E8`
(the five packed kinds, scaling on); P1* is P1 with every target kind. P3w is P3 with `-DSVF_WORD_STORE=1` (the word path on every toolchain). Before
this plan (2026-10, no fast paths, no switch) Cortex-M0+ P1 and P2 were 5718, P3 5906, P4 8298; the 2026-10-20 table
before the VESA kinds is the "before" column below.

| toolchain | version | profile | text | data | bss |
|---|---|---|---:|---:|---:|
| host-gcc | 13.3.0 | P1 | 16685 | 72 | 920 |
| host-gcc | 13.3.0 | P1* | 24701 | 72 | 920 |
| host-gcc | 13.3.0 | P2 | 16685 | 72 | 920 |
| host-gcc | 13.3.0 | P3 | 21673 | 80 | 1176 |
| host-gcc | 13.3.0 | P3w | 21673 | 80 | 1176 |
| host-gcc | 13.3.0 | P3g | 20993 | 80 | 1176 |
| host-gcc | 13.3.0 | P4 | 36333 | 80 | 1944 |
| host-gcc | 13.3.0 | P5 | 29797 | 80 | 1848 |
| clang | 23.1.3 | P1 | 19549 | 64 | 904 |
| clang | 23.1.3 | P1* | 34037 | 64 | 904 |
| clang | 23.1.3 | P2 | 19549 | 64 | 904 |
| clang | 23.1.3 | P3 | 24337 | 72 | 1160 |
| clang | 23.1.3 | P3w | 24337 | 72 | 1160 |
| clang | 23.1.3 | P3g | 27841 | 72 | 1160 |
| clang | 23.1.3 | P4 | 49701 | 88 | 1920 |
| clang | 23.1.3 | P5 | 37529 | 72 | 1824 |
| djgpp | 12.2.0 | P1 | 15800 | 864 | 0 |
| djgpp | 12.2.0 | P1* | 23352 | 864 | 0 |
| djgpp | 12.2.0 | P2 | 15800 | 864 | 0 |
| djgpp | 12.2.0 | P3 | 20184 | 1120 | 0 |
| djgpp | 12.2.0 | P3w | 20184 | 1120 | 0 |
| djgpp | 12.2.0 | P3g | 19368 | 1120 | 0 |
| djgpp | 12.2.0 | P4 | 33608 | 1860 | 0 |
| djgpp | 12.2.0 | P5 | 27128 | 1780 | 0 |
| cortex-m0plus | 15.2.1 | P1 | 7381 | 0 | 848 |
| cortex-m0plus | 15.2.1 | P1* | 10621 | 0 | 848 |
| cortex-m0plus | 15.2.1 | P2 | 7381 | 0 | 848 |
| cortex-m0plus | 15.2.1 | P3 | 9379 | 0 | 1104 |
| cortex-m0plus | 15.2.1 | P3w | 9683 | 0 | 1104 |
| cortex-m0plus | 15.2.1 | P3g | 9287 | 0 | 1104 |
| cortex-m0plus | 15.2.1 | P4 | 15543 | 0 | 1824 |
| cortex-m0plus | 15.2.1 | P5 | 12764 | 0 | 1760 |
| cortex-m33 | 15.2.1 | P1 | 6689 | 0 | 848 |
| cortex-m33 | 15.2.1 | P1* | 9717 | 0 | 848 |
| cortex-m33 | 15.2.1 | P2 | 6689 | 0 | 848 |
| cortex-m33 | 15.2.1 | P3 | 8605 | 0 | 1104 |
| cortex-m33 | 15.2.1 | P3w | 8937 | 0 | 1104 |
| cortex-m33 | 15.2.1 | P3g | 8529 | 0 | 1104 |
| cortex-m33 | 15.2.1 | P4 | 14457 | 0 | 1824 |
| cortex-m33 | 15.2.1 | P5 | 11796 | 0 | 1760 |
| avr-atmega328p | 16.1.0 | P1 | 12930 | 0 | 834 |
| avr-atmega328p | 16.1.0 | P1* | 21292 | 0 | 834 |
| avr-atmega328p | 16.1.0 | P2 | 12930 | 0 | 834 |
| avr-atmega328p | 16.1.0 | P3 | 16666 | 0 | 1090 |
| avr-atmega328p | 16.1.0 | P3w | 18078 | 0 | 1090 |
| avr-atmega328p | 16.1.0 | P3g | 16168 | 0 | 1090 |
| avr-atmega328p | 16.1.0 | P4 | 32568 | 0 | 1803 |
| avr-atmega2560 | 16.1.0 | P1 | 12928 | 0 | 834 |
| avr-atmega2560 | 16.1.0 | P1* | 21386 | 0 | 834 |
| avr-atmega2560 | 16.1.0 | P2 | 12928 | 0 | 834 |
| avr-atmega2560 | 16.1.0 | P3 | 16664 | 0 | 1090 |
| avr-atmega2560 | 16.1.0 | P3w | 18076 | 0 | 1090 |
| avr-atmega2560 | 16.1.0 | P3g | 16166 | 0 | 1090 |
| avr-atmega2560 | 16.1.0 | P4 | 32668 | 0 | 1803 |
| avr-atmega2560 | 16.1.0 | P4+GRAY | 32968 | 0 | 1803 |
| avr-atmega2560 | 16.1.0 | P5 | 25516 | 0 | 1747 |
| avr-atmega328p | 16.1.0 | P4+GRAY | overflow 232 B | - | - |
| avr-atmega328p | 16.1.0 | P5 | 25502 | 0 | 1747 |
| esp32s3-xtensa | 16.1.0 | P1 | 7826 | 0 | 848 |
| esp32s3-xtensa | 16.1.0 | P1* | 11066 | 0 | 848 |
| esp32s3-xtensa | 16.1.0 | P2 | 7826 | 0 | 848 |
| esp32s3-xtensa | 16.1.0 | P3 | 9942 | 0 | 1104 |
| esp32s3-xtensa | 16.1.0 | P3w | 10362 | 0 | 1104 |
| esp32s3-xtensa | 16.1.0 | P3g | 9666 | 0 | 1104 |
| esp32s3-xtensa | 16.1.0 | P4 | 16362 | 0 | 1824 |
| esp32s3-xtensa | 16.1.0 | P5 | 13426 | 0 | 1760 |
| esp32-xtensa | 16.1.0 | P1 | 7794 | 0 | 848 |
| esp32-xtensa | 16.1.0 | P1* | 11050 | 0 | 848 |
| esp32-xtensa | 16.1.0 | P2 | 7794 | 0 | 848 |
| esp32-xtensa | 16.1.0 | P3 | 9934 | 0 | 1104 |
| esp32-xtensa | 16.1.0 | P3w | 10350 | 0 | 1104 |
| esp32-xtensa | 16.1.0 | P3g | 9658 | 0 | 1104 |
| esp32-xtensa | 16.1.0 | P4 | 16350 | 0 | 1824 |
| esp32-xtensa | 16.1.0 | P5 | 13414 | 0 | 1760 |
| esp32c3-riscv32 | 16.1.0 | P1 | 8791 | 0 | 848 |
| esp32c3-riscv32 | 16.1.0 | P1* | 12439 | 0 | 848 |
| esp32c3-riscv32 | 16.1.0 | P2 | 8791 | 0 | 848 |
| esp32c3-riscv32 | 16.1.0 | P3 | 11643 | 0 | 1104 |
| esp32c3-riscv32 | 16.1.0 | P3w | 12007 | 0 | 1104 |
| esp32c3-riscv32 | 16.1.0 | P3g | 11519 | 0 | 1104 |
| esp32c3-riscv32 | 16.1.0 | P4 | 18371 | 0 | 1824 |
| esp32c3-riscv32 | 16.1.0 | P5 | 15347 | 0 | 1760 |
| hazard3-rp2350 | 16.1.0 | P1 | 7659 | 0 | 848 |
| hazard3-rp2350 | 16.1.0 | P1* | 10911 | 0 | 848 |
| hazard3-rp2350 | 16.1.0 | P2 | 7659 | 0 | 848 |
| hazard3-rp2350 | 16.1.0 | P3 | 10159 | 0 | 1104 |
| hazard3-rp2350 | 16.1.0 | P3w | 10511 | 0 | 1104 |
| hazard3-rp2350 | 16.1.0 | P3g | 10047 | 0 | 1104 |
| hazard3-rp2350 | 16.1.0 | P4 | 16063 | 0 | 1824 |
| hazard3-rp2350 | 16.1.0 | P5 | 13391 | 0 | 1760 |
| wasm-emcc | 6.0.13 | P1 | 14822 | 84 | 0 |
| wasm-emcc | 6.0.13 | P1* | 23019 | 142 | 0 |
| wasm-emcc | 6.0.13 | P2 | 14822 | 84 | 0 |
| wasm-emcc | 6.0.13 | P3 | 19168 | 84 | 0 |
| wasm-emcc | 6.0.13 | P3w | 19168 | 84 | 0 |
| wasm-emcc | 6.0.13 | P3g | 18087 | 142 | 0 |
| wasm-emcc | 6.0.13 | P4 | 32700 | 190 | 0 |
| wasm-emcc | 6.0.13 | P5 | 27127 | 84 | 0 |

### Before -> after the GRAY kind (text bytes, e5232ca -> 403288b)

The parametric grey kind `SVF_T_GRAY` (`SVF_TARGET_GRAY` 0x200, `SVF_TARGETS` default 0x3FF) added to the library. P1\* is P1 with every target kind of the default mask, so it carries the whole growth; the profiles that name their `SVF_TARGETS` (P1, P2, P3, P3w, P3g, P5) do not link the kind. Text bytes of `c/cross/build-all.sh`, e5232ca -> 403288b:

| toolchain | P1\* | P4 | P4+GRAY (informational, AVR only) |
|---|---|---|---|
| host-gcc | 19449 -> 20001 (+552) | 30853 -> 31613 (+760) | - |
| clang | 27998 -> 28430 (+432) | 43689 -> 44105 (+416) | - |
| djgpp | 18024 -> 18912 (+888) | 28456 -> 29200 (+744) | - |
| cortex-m0plus | 9190 -> 9434 (+244) | 14068 -> 14356 (+288) | - |
| cortex-m33 | 8286 -> 8558 (+272) | 13072 -> 13296 (+224) | - |
| avr-atmega328p | 20986 -> 21286 (+300) | 32568 -> 32566 (-2) | overflows (figure: Sizes table) |
| esp32s3-xtensa | 9443 -> 9763 (+320) | 14715 -> 15059 (+344) | - |
| esp32c3-riscv32 | 10758 -> 11042 (+284) | 16654 -> 16982 (+328) | - |
| hazard3-rp2350 | 9418 -> 9650 (+232) | 14534 -> 14810 (+276) | - |
| wasm-emcc | 17864 -> 18274 (+410) | 27680 -> 28143 (+463) | - |

Other profiles whose text moved:

- host-gcc: P3g 16241 -> 16313
- djgpp: P3g 14800 -> 14928
- cortex-m0plus: P3g 8104 -> 8100
- cortex-m33: P3 7448 -> 7446, P3g 7366 -> 7370
- avr-atmega328p: P1 12914 -> 12924, P2 12914 -> 12924, P5 25498 -> 25500
- esp32s3-xtensa: P5 12127 -> 12123
- esp32c3-riscv32: P3w 10607 -> 10611
- hazard3-rp2350: P5 12139 -> 12135

Every other profile of every toolchain has the same text as at e5232ca (on Cortex-M0+: P1, P2, P3, P3w and P5).

**Causes.** The moves outside P1\* and P4 come from Task 2's unconditional parts, not from linking the GRAY kind: the one-byte `gray_bits` field of `svf_target` (AVR has no tail padding to absorb it: Uno image and AVR P1/P2 +10 B, AVR P5 +2 B) and `target_ok(t, gray_bits)` read at draw time (code generation of `svf_draw_utf8` and `target_ok` changes: `target_ok` becomes `target_ok.isra.0`; M0+ P3g -4, host-gcc P3g +72, djgpp P3g +128, M33 P3 -2 / P3g +4, Pico SDK grey image -48 where `svf_draw_utf8` is 0x644 -> 0x614 B; the same `svf_draw.o` object compiles to the same size at `-DSVF_TARGETS=0x01` before and after, so the stub-linked pico grey -4 is a link-time layout effect of `target_ok.isra.0`). The spec says MCU profiles without the kind are unchanged and the Uno image byte-equal: these moves are a deviation from that clause, put to the user with the P1\* growth.

**The AVR numbers and their real causes.** GRAY is not opt-in on AVR: the default mask `0x3FF` includes it there too, so a build that does not draw GRAY lowers `SVF_TARGETS`; only the AVR P4 row is pinned to `0x1FF` (to stay comparable and to fit the Uno's 32 KB). AVR P1\* +300 and the P4+GRAY overflow have three causes (the deltas below are measured separately, each build as it was at that step, and are not additive): the packed blitter itself (P4+GRAY overflowed by 566 B in Task 2), the shift `x << (bits >> 1)` in place of the 32-bit multiply (566 -> 262 B), and the Cortex-M0+ dispatch merge (one `blit_gray8` call site, needed so `blit_gray8` stays inlined at -Os on M0+), which on AVR added 220 B to P4+GRAY (482 B) and 166 B to P1\* (+502); the merge is now off on AVR (separate cases, as before it), and dropping blit_gray_packed's dead bits-8 branch took another 32 B: P4+GRAY still overflows (the figure is in the Sizes table: with the version 1 JSET reader alone, the AVR default, it is smaller than before JSET), AVR P1\* is +300.

### The GRAY kind on top of JSET (text bytes, main b872696 -> rebased tip)

The same `build-all.sh` on main (the compact JSET readers, no GRAY kind) and on the SDL target branch rebased onto it (both). Only P1\* and P4 carry the kind; every other move is the `gray_bits` field and `target_ok` code generation described under "Before -> after the GRAY kind". The deltas equal that section's (e5232ca -> 403288b, before JSET): the two changes do not interact. A row that is only a value has not moved.

| toolchain | P1 | P1\* | P2 | P3 | P3g | P4 | P4+GRAY | P5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| host-gcc | 14228 | 21692 -> 22244 (+552) | 14228 | 19229 | 18477 -> 18549 (+72) | 33009 -> 33769 (+760) | - | 27321 |
| clang | 17327 | 31383 -> 31815 (+432) | 17327 | 22121 | 25625 | 47061 -> 47477 (+416) | - | 35329 |
| djgpp | 13640 | 20304 -> 21192 (+888) | 13640 | 18008 | 17064 -> 17192 (+128) | 30672 -> 31416 (+744) | - | 24952 |
| cortex-m0plus | 7441 | 10437 -> 10681 (+244) | 7441 | 9439 | 9351 -> 9347 (-4) | 15315 -> 15603 (+288) | - | 12824 |
| cortex-m33 | 6743 | 9499 -> 9771 (+272) | 6743 | 8663 -> 8659 (-4) | 8579 -> 8583 (+4) | 14287 -> 14511 (+224) | - | 11850 |
| avr-atmega328p | 12910 -> 12920 (+10) | 20982 -> 21282 (+300) | 12910 -> 12920 (+10) | 16656 | 16158 | 32560 -> 32558 (-2) | overflow 222 B | 25490 -> 25492 (+2) |
| esp32s3-xtensa | 7878 | 10798 -> 11118 (+320) | 7878 | 9994 | 9718 | 16070 -> 16414 (+344) | - | 13482 -> 13478 (-4) |
| esp32c3-riscv32 | 8869 | 12233 -> 12517 (+284) | 8869 | 11721 | 11597 | 18121 -> 18449 (+328) | - | 15429 -> 15425 (-4) |
| hazard3-rp2350 | 7725 | 10745 -> 10977 (+232) | 7725 | 10225 | 10113 | 15853 -> 16129 (+276) | - | 13461 -> 13457 (-4) |
| wasm-emcc | 12918 | 20709 -> 21119 (+410) | 12918 | 17286 | 16205 | 30529 -> 30992 (+463) | - | 25245 |

### Before -> after the VESA kinds (text bytes; bss is the probe's buffers)

"After" is the snapshot at the end of the INDEXED8, RGB555, XRGB8888 and RGB888 steps, **before the word stores**
(Task 6) and before the 1 bpp INDEXED8 word path was dropped (Task 10); the current figures are the Sizes table above
and the word-store table below.

| toolchain | profile | text before | text after | change | bss before | bss after |
|---|---|---:|---:|---:|---:|---:|
| host-gcc | P1 | 10869 | 10885 | +16 | 904 | 904 |
| host-gcc | P1* | 14309 | 17573 | +3264 | 904 | 904 |
| host-gcc | P2 | 10869 | 10885 | +16 | 904 | 904 |
| host-gcc | P3 | 11149 | 11149 | +0 | 1160 | 1160 |
| host-gcc | P3w | new | 11149 | | new | 1160 |
| host-gcc | P4 | 20449 | 23729 | +3280 | 1672 | 1928 |
| host-gcc | P5 | new | 18057 | | new | 1832 |
| clang | P1 | 11851 | 11883 | +32 | 888 | 888 |
| clang | P1* | 21315 | 25019 | +3704 | 888 | 888 |
| clang | P2 | 11851 | 11883 | +32 | 888 | 888 |
| clang | P3 | 11747 | 11731 | -16 | 1144 | 1144 |
| clang | P3w | new | 11731 | | new | 1144 |
| clang | P4 | 28971 | 32083 | +3112 | 1632 | 1888 |
| clang | P5 | new | 20369 | | new | 1808 |
| djgpp | P1 | 10144 | 10144 | +0 | 0 | 0 |
| djgpp | P1* | 13592 | 16200 | +2608 | 0 | 0 |
| djgpp | P2 | 10144 | 10144 | +0 | 0 | 0 |
| djgpp | P3 | 10160 | 10160 | +0 | 0 | 0 |
| djgpp | P3w | new | 10160 | | new | 0 |
| djgpp | P4 | 18872 | 21736 | +2864 | 0 | 0 |
| djgpp | P5 | new | 16016 | | new | 0 |
| cortex-m0plus | P1 | 5674 | 5674 | +0 | 844 | 844 |
| cortex-m0plus | P1* | 7094 | 8474 | +1380 | 844 | 844 |
| cortex-m0plus | P2 | 5674 | 5674 | +0 | 844 | 844 |
| cortex-m0plus | P3 | 5802 | 5802 | +0 | 1100 | 1100 |
| cortex-m0plus | P3w | new | 5802 | | new | 1100 |
| cortex-m0plus | P4 | 9718 | 11106 | +1388 | 1560 | 1816 |
| cortex-m0plus | P5 | new | 8795 | | new | 1756 |
| avr-atmega328p | P1 | 12848 | 12848 | +0 | 830 | 830 |
| avr-atmega328p | P1* | 17362 | 20922 | +3560 | 830 | 830 |
| avr-atmega328p | P2 | 12848 | 12848 | +0 | 830 | 830 |
| avr-atmega328p | P3 | 12330 | 12320 | -10 | 1086 | 1086 |
| avr-atmega328p | P3w | new | 12320 | | new | 1086 |
| avr-atmega328p | P4 | 23664 | 27540 | +3876 | 1539 | 1795 |
| avr-atmega328p | P5 | new | 20484 | | new | 1743 |
| esp32c3-riscv32 | P1 | 6935 | 6935 | +0 | 844 | 844 |
| esp32c3-riscv32 | P1* | 8495 | 10111 | +1616 | 844 | 844 |
| esp32c3-riscv32 | P2 | 6935 | 6935 | +0 | 844 | 844 |
| esp32c3-riscv32 | P3 | 7079 | 7075 | -4 | 1100 | 1100 |
| esp32c3-riscv32 | P3w | new | 7075 | | new | 1100 |
| esp32c3-riscv32 | P4 | 11087 | 12807 | +1720 | 1560 | 1816 |
| esp32c3-riscv32 | P5 | new | 10287 | | new | 1756 |
| wasm-emcc | P1 | 8927 | 8933 | +6 | 0 | 0 |
| wasm-emcc | P1* | 12543 | 15728 | +3185 | 0 | 0 |
| wasm-emcc | P2 | 8927 | 8933 | +6 | 0 | 0 |
| wasm-emcc | P3 | 9113 | 9068 | -45 | 0 | 0 |
| wasm-emcc | P3w | new | 9068 | | new | 0 |
| wasm-emcc | P4 | 17375 | 20584 | +3209 | 0 | 0 |
| wasm-emcc | P5 | new | 15263 | | new | 0 |

### Before -> after the word stores (Task 6; text bytes, `SVF_WORD_STORE` as each target sets it)

Only rows that changed. "Text after" is the 2026-10-21 figure, after Task 10 dropped the 1 bpp INDEXED8 nibble path
(it measured slower on MARUS24 in `c/bench/MEASUREMENTS.md`): P1*, P4 and P5 shrank by 88/104/64 (host gcc),
544/656/592 (clang), 96/144/176 (DJGPP) and 589/593/589 (WASM) bytes from the Task 6 values (18205/24313/18697,
26251/33539/21937, 16872/22456/16752, 17241/22101/16776). The single `SVF_WORD_STORE` switch is also what Task 10's
removal of the 1 bpp INDEXED8 word path rides on, so it applies to WASM too; WASM's packed rows are not benched, the
effect there is size only. The switch is 1 on host gcc, clang, DJGPP and WASM (x86 and WASM), 0 on Cortex-M0+, AVR
and ESP32-C3: those rows are byte-identical to before except P3w, which forces the word path on. bss and data did
not move.

| toolchain | profile | text before | text after | change |
|---|---|---:|---:|---:|
| host-gcc | P1* | 17573 | 18117 | +544 |
| host-gcc | P3 | 11149 | 11517 | +368 |
| host-gcc | P3w | 11149 | 11517 | +368 |
| host-gcc | P4 | 23729 | 24209 | +480 |
| host-gcc | P5 | 18057 | 18633 | +576 |
| clang | P1* | 25019 | 25707 | +688 |
| clang | P3 | 11731 | 12451 | +720 |
| clang | P3w | 11731 | 12451 | +720 |
| clang | P4 | 32083 | 32883 | +800 |
| clang | P5 | 20369 | 21345 | +976 |
| djgpp | P1* | 16200 | 16776 | +576 |
| djgpp | P3 | 10160 | 10768 | +608 |
| djgpp | P3w | 10160 | 10768 | +608 |
| djgpp | P4 | 21736 | 22312 | +576 |
| djgpp | P5 | 16016 | 16576 | +560 |
| cortex-m0plus | P3w | 5802 | 6106 | +304 |
| avr-atmega328p | P3w | 12320 | 13732 | +1412 |
| esp32c3-riscv32 | P3w | 7075 | 7435 | +360 |
| wasm-emcc | P1* | 15728 | 16652 | +924 |
| wasm-emcc | P3 | 9068 | 9847 | +779 |
| wasm-emcc | P3w | 9068 | 9847 | +779 |
| wasm-emcc | P4 | 20584 | 21508 | +924 |
| wasm-emcc | P5 | 15263 | 16187 | +924 |

The esp32s3-xtensa toolchain and the P3g profile came from the MCU ports (main) after these two tables were made;
they have no "before" and "after" columns here: their figures are in the Sizes table above.

### Before -> after SVF v3 (text bytes, 5b0cf5d -> b45e9dc)

Before = `c/build/v2/cross.md` (Task 1, the v2 tree at 5b0cf5d), after = `c/build/v3/cross-head.md` (`c/cross/build-all.sh` at b45e9dc, 2026-10-23, the table above). Same toolchains and flags; the v3 P1 and P2 of every toolchain build `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` (so they drop the stream reader and read one layout), P1* the same with every target kind; P3 to P5 read every layout and link the stream reader. `data` and `bss` are in the table above.

| toolchain | profile | v2 text | v3 text | change |
|---|---|---:|---:|---:|
| host-gcc | P1 | 10885 | 11681 | +796 (+7.3 %) |
| host-gcc | P1* | 18117 | 18913 | +796 (+4.4 %) |
| host-gcc | P2 | 10885 | 11681 | +796 (+7.3 %) |
| host-gcc | P3 | 11517 | 16689 | +5172 (+44.9 %) |
| host-gcc | P3w | 11517 | 16689 | +5172 (+44.9 %) |
| host-gcc | P3g | 10685 | 15857 | +5172 (+48.4 %) |
| host-gcc | P4 | 24209 | 29517 | +5308 (+21.9 %) |
| host-gcc | P5 | 18633 | 23949 | +5316 (+28.5 %) |
| clang | P1 | 11883 | 13654 | +1771 (+14.9 %) |
| clang | P1* | 25707 | 27462 | +1755 (+6.8 %) |
| clang | P2 | 11883 | 13654 | +1771 (+14.9 %) |
| clang | P3 | 12451 | 18453 | +6002 (+48.2 %) |
| clang | P3w | 12451 | 18453 | +6002 (+48.2 %) |
| clang | P3g | 15795 | 21797 | +6002 (+38.0 %) |
| clang | P4 | 32883 | 38885 | +6002 (+18.3 %) |
| clang | P5 | 21345 | 27427 | +6082 (+28.5 %) |
| djgpp | P1 | 10144 | 11056 | +912 (+9.0 %) |
| djgpp | P1* | 16776 | 17688 | +912 (+5.4 %) |
| djgpp | P2 | 10144 | 11056 | +912 (+9.0 %) |
| djgpp | P3 | 10768 | 15440 | +4672 (+43.4 %) |
| djgpp | P3w | 10768 | 15440 | +4672 (+43.4 %) |
| djgpp | P3g | 9808 | 14480 | +4672 (+47.6 %) |
| djgpp | P4 | 22312 | 27032 | +4720 (+21.2 %) |
| djgpp | P5 | 16576 | 21376 | +4800 (+29.0 %) |
| cortex-m0plus | P1 | 5674 | 6022 | +348 (+6.1 %) |
| cortex-m0plus | P1* | 8474 | 8826 | +352 (+4.2 %) |
| cortex-m0plus | P2 | 5674 | 6022 | +348 (+6.1 %) |
| cortex-m0plus | P3 | 5802 | 8020 | +2218 (+38.2 %) |
| cortex-m0plus | P3w | 6106 | 8324 | +2218 (+36.3 %) |
| cortex-m0plus | P3g | 5542 | 7760 | +2218 (+40.0 %) |
| cortex-m0plus | P4 | 11106 | 13412 | +2306 (+20.8 %) |
| cortex-m0plus | P5 | 8795 | 11089 | +2294 (+26.1 %) |
| cortex-m33 | P1 | 5038 | 5400 | +362 (+7.2 %) |
| cortex-m33 | P1* | 7650 | 8010 | +360 (+4.7 %) |
| cortex-m33 | P2 | 5038 | 5400 | +362 (+7.2 %) |
| cortex-m33 | P3 | 5112 | 7320 | +2208 (+43.2 %) |
| cortex-m33 | P3w | 5442 | 7650 | +2208 (+40.6 %) |
| cortex-m33 | P3g | 4880 | 7088 | +2208 (+45.2 %) |
| cortex-m33 | P4 | 10146 | 12440 | +2294 (+22.6 %) |
| cortex-m33 | P5 | 7921 | 10207 | +2286 (+28.9 %) |
| avr-atmega328p | P1 | 12848 | 12914 | +66 (+0.5 %) |
| avr-atmega328p | P1* | 20922 | 20986 | +64 (+0.3 %) |
| avr-atmega328p | P2 | 12848 | 12914 | +66 (+0.5 %) |
| avr-atmega328p | P3 | 12320 | 16664 | +4344 (+35.3 %) |
| avr-atmega328p | P3w | 13732 | 18076 | +4344 (+31.6 %) |
| avr-atmega328p | P3g | 11822 | 16166 | +4344 (+36.7 %) |
| avr-atmega328p | P4 | 27540 | 32122 | +4582 (+16.6 %) |
| avr-atmega328p | P5 | 20484 | 25052 | +4568 (+22.3 %) |
| esp32s3-xtensa | P1 | 6063 | 6379 | +316 (+5.2 %) |
| esp32s3-xtensa | P1* | 8983 | 9299 | +316 (+3.5 %) |
| esp32s3-xtensa | P2 | 6063 | 6379 | +316 (+5.2 %) |
| esp32s3-xtensa | P3 | 6055 | 8495 | +2440 (+40.3 %) |
| esp32s3-xtensa | P3w | 6475 | 8915 | +2440 (+37.7 %) |
| esp32s3-xtensa | P3g | 5779 | 8219 | +2440 (+42.2 %) |
| esp32s3-xtensa | P4 | 11623 | 14139 | +2516 (+21.6 %) |
| esp32s3-xtensa | P5 | 9039 | 11551 | +2512 (+27.8 %) |
| esp32c3-riscv32 | P1 | 6935 | 7207 | +272 (+3.9 %) |
| esp32c3-riscv32 | P1* | 10111 | 10383 | +272 (+2.7 %) |
| esp32c3-riscv32 | P2 | 6935 | 7207 | +272 (+3.9 %) |
| esp32c3-riscv32 | P3 | 7075 | 10059 | +2984 (+42.2 %) |
| esp32c3-riscv32 | P3w | 7435 | 10419 | +2984 (+40.1 %) |
| esp32c3-riscv32 | P3g | 6747 | 9731 | +2984 (+44.2 %) |
| esp32c3-riscv32 | P4 | 12807 | 15923 | +3116 (+24.3 %) |
| esp32c3-riscv32 | P5 | 10287 | 13399 | +3112 (+30.3 %) |
| hazard3-rp2350 | P1 | 5927 | 6219 | +292 (+4.9 %) |
| hazard3-rp2350 | P1* | 8779 | 9067 | +288 (+3.3 %) |
| hazard3-rp2350 | P2 | 5927 | 6219 | +292 (+4.9 %) |
| hazard3-rp2350 | P3 | 6035 | 8723 | +2688 (+44.5 %) |
| hazard3-rp2350 | P3w | 6391 | 9075 | +2684 (+42.0 %) |
| hazard3-rp2350 | P3g | 5755 | 8443 | +2688 (+46.7 %) |
| hazard3-rp2350 | P4 | 11063 | 13867 | +2804 (+25.3 %) |
| hazard3-rp2350 | P5 | 8847 | 11643 | +2796 (+31.6 %) |
| wasm-emcc | P1 | 8933 | 9811 | +878 (+9.8 %) |
| wasm-emcc | P1* | 16652 | 17534 | +882 (+5.3 %) |
| wasm-emcc | P2 | 8933 | 9811 | +878 (+9.8 %) |
| wasm-emcc | P3 | 9847 | 14179 | +4332 (+44.0 %) |
| wasm-emcc | P3w | 9847 | 14179 | +4332 (+44.0 %) |
| wasm-emcc | P3g | 8698 | 13030 | +4332 (+49.8 %) |
| wasm-emcc | P4 | 21508 | 25933 | +4425 (+20.6 %) |
| wasm-emcc | P5 | 16187 | 20721 | +4534 (+28.0 %) |

Faces (`python3 -I tools/svf2to3.py --tree svf c/build/v3/prof/<p> --profile <p>`, the sum of the 153 `.SVF` files of each tree, bytes; v2 = the 153 files at 5b0cf5d, 19,920,435 B):

| profile | total B | of v2 | spec |
|---|---:|---:|---:|
| mcu-strict | 13,919,772 | 69.9 % | 14,072,657 (-1.09 %) |
| default | 14,200,840 | 71.3 % | 14,140,995 (+0.42 %) |
| dos | 13,825,899 | 69.4 % | 13,666,031 (+1.17 %) |
| full | 21,249,364 | 106.7 % | 20,626,915 (+3.02 %) |

Rows off the spec by more than 1 %, each with its measured cause (per-profile glyph data, offset tables and the rest, summed over the 153 files with the header fields; glyph data / offset tables / everything else: mcu-strict 10,994,700 / 358,090 / 2,566,982; default 10,994,700 / 639,332 / 2,566,808; dos 10,779,834 / 479,534 / 2,566,531; full 18,043,224 / 639,332 / 2,566,808):

- **mcu-strict, 13,919,772 B, 1.09 % under the spec's 14,072,657.** The spec's two x-boxed rows disagree with each other: `default` (same units, REC 4 / ROW 1 / TAB 4) is priced at 63.0 % glyph data (10,934,855 B after its own tables), `mcu-strict` at 64.5 % (11,186,183 B after its u16 tables of 319,666 B). Both profiles have the same glyph data size here (10,994,700 B each, 63.35 % of the v2 data), so the measured `mcu-strict` is smaller than its spec row by the 191,483 B of glyph data the spec row carries too much, and larger by 38,424 B of offset tables (eight faces, whose data is over 256 KB (297,396 B and up), keep u32 offsets: 145 of 153 files are u16, tables 358,090 B against the spec's 319,666 B) and by 174 B of other file bytes (not isolated): -191,483 + 38,424 + 174 = -152,885 B, the gap.
- **dos, 13,825,899 B, 1.17 % over the spec's 13,666,031.** The glyph data matches the spec (10,779,834 B = 62.11 % of v2 against its 62.1 %). The whole difference is the offset tables: the spec prices all u16 (319,666 B), but a face whose data is over 64 KB needs u32 (the writer's rule: the largest u16 face has 64,814 B of data, the smallest u32 face 66,476 B; 42 of 153 files): 479,534 B, which is 159,868 B more, exactly the 13,825,899 - 13,666,031 gap.
- **full, 21,249,364 B, 3.02 % over the spec's 20,626,915.** As known in advance: the spec's `full` total leaves out the 4-byte record headers (its glyph data term is 17,355,740 + 65,312 = 17,421,052 B). Measured glyph data is 18,043,224 B; with 159,680 headers of 4 B it would be 18,059,772 B, and 196 records (blank glyphs) are shorter than header + cell, 16,548 B in all.

`default` is +0.42 % over the spec (14,200,840 against 14,140,995): inside 1 %, no sentence needed beyond the 59,845 B of glyph data the spec's 63.0 % rounds away.


### Before -> after the C speedups (text bytes, 4539e42 -> 8bff82e)

Before = `c/build/cross-v3base.md` (`c/cross/build-all.sh` at 4539e42, SVF v3 merged, before Task 6), after = `c/build/cross-after.md` (the same script at 8bff82e, 2026-10-23, the table above). Same toolchains and flags. Tasks 6-9 add the word merge (`SVF_MERGE_WORDS`, Task 6), the GRAY8 nibble table (`SVF_GRAY8_LUT1`, Task 7; off on AVR and Xtensa, so those rows carry no table), the separable box filter (Task 8; only the profiles with the scaler, P4 and P5, and the port programs) and the cmap midpoint shift (Task 9, and its 16-bit overflow fix, T9-F1).

| toolchain | profile | v3 (4539e42) text | after text | change |
|---|---|---:|---:|---:|
| host-gcc | P1 | 11681 | 11985 | +304 (+2.6 %) |
| host-gcc | P1* | 18913 | 19449 | +536 (+2.8 %) |
| host-gcc | P2 | 11681 | 11985 | +304 (+2.6 %) |
| host-gcc | P3 | 16689 | 16993 | +304 (+1.8 %) |
| host-gcc | P3w | 16689 | 16993 | +304 (+1.8 %) |
| host-gcc | P3g | 15857 | 16241 | +384 (+2.4 %) |
| host-gcc | P4 | 29517 | 30853 | +1336 (+4.5 %) |
| host-gcc | P5 | 23949 | 25093 | +1144 (+4.8 %) |
| clang | P1 | 13654 | 13942 | +288 (+2.1 %) |
| clang | P1* | 27462 | 27998 | +536 (+2.0 %) |
| clang | P2 | 13654 | 13942 | +288 (+2.1 %) |
| clang | P3 | 18453 | 18741 | +288 (+1.6 %) |
| clang | P3w | 18453 | 18741 | +288 (+1.6 %) |
| clang | P3g | 21797 | 22245 | +448 (+2.1 %) |
| clang | P4 | 38885 | 43689 | +4804 (+12.4 %) |
| clang | P5 | 27427 | 31955 | +4528 (+16.5 %) |
| djgpp | P1 | 11056 | 11360 | +304 (+2.7 %) |
| djgpp | P1* | 17688 | 18024 | +336 (+1.9 %) |
| djgpp | P2 | 11056 | 11360 | +304 (+2.7 %) |
| djgpp | P3 | 15440 | 15744 | +304 (+2.0 %) |
| djgpp | P3w | 15440 | 15744 | +304 (+2.0 %) |
| djgpp | P3g | 14480 | 14800 | +320 (+2.2 %) |
| djgpp | P4 | 27032 | 28456 | +1424 (+5.3 %) |
| djgpp | P5 | 21376 | 22688 | +1312 (+6.1 %) |
| cortex-m0plus | P1 | 6022 | 6194 | +172 (+2.9 %) |
| cortex-m0plus | P1* | 8826 | 9190 | +364 (+4.1 %) |
| cortex-m0plus | P2 | 6022 | 6194 | +172 (+2.9 %) |
| cortex-m0plus | P3 | 8020 | 8192 | +172 (+2.1 %) |
| cortex-m0plus | P3w | 8324 | 8496 | +172 (+2.1 %) |
| cortex-m0plus | P3g | 7760 | 8104 | +344 (+4.4 %) |
| cortex-m0plus | P4 | 13412 | 14068 | +656 (+4.9 %) |
| cortex-m0plus | P5 | 11089 | 11577 | +488 (+4.4 %) |
| cortex-m33 | P1 | 5400 | 5528 | +128 (+2.4 %) |
| cortex-m33 | P1* | 8010 | 8286 | +276 (+3.4 %) |
| cortex-m33 | P2 | 5400 | 5528 | +128 (+2.4 %) |
| cortex-m33 | P3 | 7320 | 7448 | +128 (+1.7 %) |
| cortex-m33 | P3w | 7650 | 7778 | +128 (+1.7 %) |
| cortex-m33 | P3g | 7088 | 7366 | +278 (+3.9 %) |
| cortex-m33 | P4 | 12440 | 13072 | +632 (+5.1 %) |
| cortex-m33 | P5 | 10207 | 10635 | +428 (+4.2 %) |
| avr-atmega328p | P1 | 12914 | 12914 | +0 (+0.0 %) |
| avr-atmega328p | P1* | 20986 | 20986 | +0 (+0.0 %) |
| avr-atmega328p | P2 | 12914 | 12914 | +0 (+0.0 %) |
| avr-atmega328p | P3 | 16664 | 16664 | +0 (+0.0 %) |
| avr-atmega328p | P3w | 18076 | 18076 | +0 (+0.0 %) |
| avr-atmega328p | P3g | 16166 | 16166 | +0 (+0.0 %) |
| avr-atmega328p | P4 | 32122 | 32568 | +446 (+1.4 %) |
| avr-atmega328p | P5 | 25052 | 25498 | +446 (+1.8 %) |
| esp32s3-xtensa | P1 | 6379 | 6523 | +144 (+2.3 %) |
| esp32s3-xtensa | P1* | 9299 | 9443 | +144 (+1.5 %) |
| esp32s3-xtensa | P2 | 6379 | 6523 | +144 (+2.3 %) |
| esp32s3-xtensa | P3 | 8495 | 8639 | +144 (+1.7 %) |
| esp32s3-xtensa | P3w | 8915 | 9059 | +144 (+1.6 %) |
| esp32s3-xtensa | P3g | 8219 | 8363 | +144 (+1.8 %) |
| esp32s3-xtensa | P4 | 14139 | 14715 | +576 (+4.1 %) |
| esp32s3-xtensa | P5 | 11551 | 12127 | +576 (+5.0 %) |
| esp32c3-riscv32 | P1 | 7207 | 7391 | +184 (+2.6 %) |
| esp32c3-riscv32 | P1* | 10383 | 10758 | +375 (+3.6 %) |
| esp32c3-riscv32 | P2 | 7207 | 7391 | +184 (+2.6 %) |
| esp32c3-riscv32 | P3 | 10059 | 10247 | +188 (+1.9 %) |
| esp32c3-riscv32 | P3w | 10419 | 10607 | +188 (+1.8 %) |
| esp32c3-riscv32 | P3g | 9731 | 10126 | +395 (+4.1 %) |
| esp32c3-riscv32 | P4 | 15923 | 16654 | +731 (+4.6 %) |
| esp32c3-riscv32 | P5 | 13399 | 13955 | +556 (+4.1 %) |
| hazard3-rp2350 | P1 | 6219 | 6395 | +176 (+2.8 %) |
| hazard3-rp2350 | P1* | 9067 | 9418 | +351 (+3.9 %) |
| hazard3-rp2350 | P2 | 6219 | 6395 | +176 (+2.8 %) |
| hazard3-rp2350 | P3 | 8723 | 8899 | +176 (+2.0 %) |
| hazard3-rp2350 | P3w | 9075 | 9251 | +176 (+1.9 %) |
| hazard3-rp2350 | P3g | 8443 | 8790 | +347 (+4.1 %) |
| hazard3-rp2350 | P4 | 13867 | 14534 | +667 (+4.8 %) |
| hazard3-rp2350 | P5 | 11643 | 12139 | +496 (+4.3 %) |
| wasm-emcc | P1 | 9811 | 10073 | +262 (+2.7 %) |
| wasm-emcc | P1* | 17534 | 17864 | +330 (+1.9 %) |
| wasm-emcc | P2 | 9811 | 10073 | +262 (+2.7 %) |
| wasm-emcc | P3 | 14179 | 14441 | +262 (+1.8 %) |
| wasm-emcc | P3w | 14179 | 14441 | +262 (+1.8 %) |
| wasm-emcc | P3g | 13030 | 13360 | +330 (+2.5 %) |
| wasm-emcc | P4 | 25933 | 27680 | +1747 (+6.7 %) |
| wasm-emcc | P5 | 20721 | 22402 | +1681 (+8.1 %) |

## Size switches

Added 2026-10-23 (Task 11). Every speed feature of the C speedups can be switched off by a define, to win the size back (the list is the comment block "Size switches" in `c/include/svf.h`): `SVF_MERGE_WORDS=0` (Task 6, the word-at-a-time `svf__merge`), `SVF_GRAY8_LUT1=0` (Task 7, the 64 B nibble table and its GRAY8 1 bpp blit), `SVF_SCALE_FAST=0` (Task 8, the separable area average: `svf__scale_cell` is then the 2-D loop of 4539e42, restored from git), and the umbrella `-DSVF_SMALL`, which makes the default of all three 0 (an explicit `-DSVF_X=1` still wins). Task 9's code point search has no switch (it is smaller than the code it replaced) and the T9-F1 overflow fix is unconditional. Pixels are the same in every combination: `test_kernels` prints the same line (scale checksum 16513002) built with the defaults, the strict-align bytes, `SVF_MERGE_WORDS=0 SVF_GRAY8_LUT1=0`, `SVF_SCALE_FAST=0` and `SVF_SMALL`. The defaults did not change (the default objects are byte-identical to 9bf36a7). Measured by `build-all.sh` (rows of Cortex-M0+ and AVR; `rows-switches.md` of its output), text bytes, `-Os`. Re-taken 2026-10-26 on the SDL target branch rebased onto main (JSET readers and GRAY kind together); the AVR scaled-path stack row is the 2026-10-23 measurement of `stack-usage.py`, not re-run: the stack does not depend on the GRAY kind's blitters nor on the JSET readers:

| Cortex-M0+ (15.2.1) | default | `SVF_SMALL` | `SVF_MERGE_WORDS=0` | `SVF_GRAY8_LUT1=0` | `SVF_SCALE_FAST=0` | `JSET_V1` | `JSET_V2` | `JSET_TRUSTED` | `JSET_POP4=0` | `JSET_BIG` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P1 | 7381 | 7173 | 7201 | 7381 | 7381 | 6162 | 6733 | 6720 | 7353 | 7369 |
| P2 | 7381 | 7173 | 7201 | 7381 | 7381 | 6162 | 6733 | 6720 | 7353 | 7369 |
| P1* | 10621 | 10245 | 10441 | 10453 | 10621 | 9402 | 9973 | 9960 | 10593 | 10609 |
| P3g | 9287 | 8911 | 9107 | 9119 | 9287 | 8068 | 8639 | 8626 | 9259 | 9275 |
| P4 | 15543 | 14859 | 15363 | 15383 | 15227 | 14324 | 14895 | 14882 | 15515 | 15531 |
| P5 | 12764 | 12240 | 12584 | 12764 | 12448 | 11545 | 12116 | 12103 | 12736 | 12752 |

| AVR (16.1.0) | default | `SVF_SMALL` | `SVF_MERGE_WORDS=0` | `SVF_GRAY8_LUT1=0` | `SVF_SCALE_FAST=0` | `JSET_BOTH` | `JSET_V2` | `JSET_TRUSTED` | `JSET_BIG` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P1 text | 12930 | 12930 | 12930 (default) | 12930 (default) | 12930 | 15242 | 13522 | 12364 | 12956 |
| P1* text | 21292 | 21292 | 21292 (default) | 21292 (default) | 21292 | 23604 | 21952 | 20726 | 21318 |
| P4 text | 32568 | 32122 | 32568 (default) | 32568 (default) | 32122 | overflow 2538 | overflow 798 | 31978 | 32602 |
| P4 scaled-path static stack (`c/cross/stack-usage.py`, `svf_draw_utf8`) | 864 | 451 | 864 | 864 | 451 | 864 | 864 | 864 | 864 (not re-run) |
| P4 data + bss | 1803 | 1803 | 1803 | 1803 | 1803 | - | - | 1803 | 1803 |

- On AVR `SVF_MERGE_WORDS` and `SVF_GRAY8_LUT1` already default to 0, so only `SVF_SCALE_FAST` moves a byte; the `=0` columns of those two are the default build. P1 and P2 are `SVF_NO_SCALE` builds: `SVF_SCALE_FAST` does nothing there, `SVF_GRAY8_LUT1` does nothing on MONO_PAGE (P1/P2) and `SVF_MERGE_WORDS` does (-180 B).
- Cortex-M0+ scaled-path static stack: 1008 B default, 680 B with `SVF_SMALL` or `SVF_SCALE_FAST=0` (the same as without the scaler), 1008 B with the other two.
- **P1\* with `SVF_SMALL`: 8818 B at c592140, against the accepted 8826 B.** Since the compact JSET Task 3 the default Cortex-M0+ build carries both JSET readers (P1\* 10437 B, `SVF_SMALL` 10037 B; Task 3's first commit measured 10434 / 10034; with the GRAY kind on top, rebased onto it, 10681 B and 10305 B); the earlier figure is the version 1 reader alone with `SVF_SMALL` (`-DSVF_JSET_V2=0 -DSVF_SMALL`; not a row of the table: the -48 B of the version 1 reader alone was measured without `SVF_SMALL`, so 8818 - 48 is an estimate). M0+ P1/P2 with `SVF_SMALL` are 7233 B (959 B under the 8192 B budget; unchanged by the GRAY kind), 6146 B with the version 1 reader alone (no `SVF_SMALL`).
- **AVR P4 with `SVF_SMALL` (or `SVF_SCALE_FAST=0`): 32112 B (32122 B at c592140), which fits an Optiboot Uno (32256 B) with 144 B to spare** (the default build's 32558 B does not). The scaled-path stack falls from 864 B to 451 B, the figure of 4539e42; P4 is still a probe, not an Uno program (1803 B of statics + 451 B stack > 2048 B).
- The JSET columns (svf.h "Size switches"; the readers by define, amendment 2026-10-23 of `docs/superpowers/specs/2026-10-23-jset-compact-design.md`): Cortex-M0+ `JSET_V1` = `-DSVF_JSET_V2=0` (the version 1 reader alone), `JSET_V2` = `-DSVF_JSET_V1=0`, `JSET_TRUSTED` = `-DSVF_JSET_TRUSTED=1` (both readers, no JSET validation: faces built into flash only), `JSET_BIG` = `-DSVF_JSET_BIG=1` (Task 17, 2026-10-27: the widened limits, 19 x 28 classes and 128 / 128 / 64 sets; it is the default on host, DOS, WASM, SDL (`__unix__`, `_WIN32`, `__APPLE__`, `__DJGPP__`, `__EMSCRIPTEN__`) builds only), `JSET_POP4=0` (the version 2 reader's popcount without its 16-entry nibble table); AVR `JSET_BOTH` = `-DSVF_JSET_V2=1`, `JSET_V2` = `-DSVF_JSET_V1=0 -DSVF_JSET_V2=1`, `JSET_TRUSTED` (the AVR default reader, version 1, without validation). "overflow N": the P4 probe does not link, N bytes over the ATmega328P's 32 KB (`build-all.sh` records it as a row; data + bss "-"). The scaled-path stack of every JSET column is measured as the other columns (no JSET function is on the deepest path).
- `build-all.sh` builds the SVF_SMALL variant of every Cortex-M0+ and AVR profile (and each switch off singly on Cortex-M0+, `SVF_SCALE_FAST=0` on AVR) and `--ports` the three Pico images and the Arduino image with `-DSVF_SMALL` (the `pico-small` and `arduino-small` rows of the Port examples table, checked by the gate): the Pico images -180 / -352 / -180 B.

### JSET v1 + v2 readers (amendment 2026-10-23)

Measured 2026-10-23 (compact JSET Task 3, card t_559aeb6a) with `build-all.sh`, text bytes against BASE c592140 (the version 1 reader of main). Readers by define (`SVF_JSET_V1`, `SVF_JSET_V2`; AVR defaults to version 1 alone, every other target to both), the version 2 reader's nibble popcount table `SVF_JSET_POP4` (on by default, off on AVR and under `SVF_SMALL`), and `SVF_JSET_TRUSTED` (default 0). With both readers the version 1 lookup takes the version 2 reader's two multiply-shifts instead of libgcc divisions (the version 1 reader alone keeps its divisions: smaller on AVR).

| reader build | M0+ P1 | M0+ P1* | AVR P1 | AVR P1* | AVR P4 (ATmega328P, 32 KB) |
|---|---:|---:|---:|---:|---|
| BASE (v1 reader, c592140) | 6194 | 9190 | 12914 | 20986 | links, 62 B free |
| v1 only (`SVF_JSET_V2=0`; AVR default) | 6146 (-48) | 9142 (-48) | 12910 (-4) | 20982 (-4) | links, 70 B free (P4 32560 B) |
| v2 only (`SVF_JSET_V1=0`) | 6729 (+535) | 9725 (+535) | 13404 (+490) | 21544 (+558) | over by 684 B |
| both (M0+ default, `SVF_JSET_POP4` on) | 7441 (+1247) | 10437 (+1247) | 15332 (+2418) | 23404 (+2418) | over by 2692 B |
| both, `SVF_JSET_POP4=0` | 7413 (+1219) | 10409 (+1219) | 15332 (POP4 is 0 on AVR) | 23404 | over by 2692 B |
| trusted (`SVF_JSET_TRUSTED=1`, the default readers) | 6764 (+570) | 9760 (+570) | 12354 (-560) | 20426 (-560) | links, 276 B free |

- This table is the Task 3 measurement, taken before the GRAY kind; the same builds with it (2026-10-26) are in "Size switches" above (Cortex-M0+ P1\* 10437 -> 10681, `JSET_V1` 9142 -> 9386, `JSET_V2` 9725 -> 9969, `JSET_TRUSTED` 9760 -> 10004; AVR P1 +10, P1\* +300, `JSET_BOTH` P4 overflow 2690, `JSET_V2` P4 overflow 682). After the Task 5 status split the table above reads Cortex-M0+ P1\* 10621, `JSET_V1` 9402, `JSET_V2` 9973, `JSET_TRUSTED` 9960, AVR `JSET_BOTH` P4 overflow 2538, `JSET_V2` P4 overflow 798.
- The trusted switch saves 677 B on Cortex-M0+ P1 (both readers: 7441 -> 6764; after Task 5 7381 -> 6720) and 556 B on AVR P1 (version 1 alone: 12910 -> 12354; after Task 5 12930 -> 12364). It keeps each reader's header length, magic and version checks, records the counts and still checks the block size the counts give against the header's region size (the T3-M1 ruling: no lookup reads past the region a streamed face loaded; 123 B on Cortex-M0+, 194 B on AVR over the first trusted measurement); the table contents are not validated, so a hostile or corrupt JSET then reads out of bounds (svf.h), so the fuzz harnesses do not compile with it and `make check` builds it once, for valid faces only (`tools/test_c_renderer.py` `test_trusted_draws_identically`).
- The nibble table costs 28 B on Cortex-M0+ in the both build (24 B in the version 2 build alone). The version 1 multiply-shifts and the dispatch with the version 2 call first save 13 B in the both build (7454 -> 7441) and cost 54 B on AVR (`JSET_BOTH` 15278 -> 15332); they make a version 1 face draw faster than at BASE (Pico MONO_PAGE `-Os` `syl_ga` 6143 -> 6091 cycles, `syl_bwelk` 7500 -> 7321).
- RAM: `svf_face` holds one byte more than at BASE (`jset_na`, the version 2 alias flag), so the AVR probes' bss is 1 B (P1) / 2 B (P4, two faces) above c592140 in every build.
- Divide symbols left (Cortex-M0+ P1 link, 2026-10-26): libgcc's `__udivsi3` (266 B) and `__aeabi_uidivmod` (8 B) are linked in the default, `JSET_V1` and `JSET_V2` builds alike, because `svf_draw` still divides (17 call sites in `svf_draw.o`). The jamo decomposition's own call sites in `svf_jamo.o`: 1 in the default build, 5 in the version 1 reader alone (which keeps its divisions), 0 in the version 2 reader alone; BASE had 6. So the division symbols leave P1 only if `svf_draw`'s divisions go too, which is out of this plan's scope (ruling J1-C1).

## Minimal config

Added 2026-10-26 (JSET v3 / JMAP / BIG plan, Task 2, card t_380104f8). `check-features.sh` (with `test-check-features.sh` for its gates) builds the P1 probe of `build-all.sh` (`probe.c -DPROFILE=1`, `-Os`, `--gc-sections`, the empty `-DPROFILE=0` probe over the `-DSVF_NO_SCALE` objects subtracted, as `build-all.sh`) for named configs on the Uno toolchain (avr-gcc 16.1.0, atmega328p) and Cortex-M0+ (arm-none-eabi-gcc 15.2.1), and `check-sizes-md.sh --features` compares the gated rows with this table by exact equality. Configs (the `CONFIGS` table at the top of the script; later tasks add rows): `minimal` = the Uno flags of `c/ports/arduino/README.md` (`-DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0`), `default` = P1, `allon` = every switch 1 (`SVF_JSET_V1/V2/POP4`, `SVF_JMAP` from Task 7, `SVF_JSET_BIG` from the Group D review, `SVF_MERGE_WORDS`, `SVF_GRAY8_LUT1`, `SVF_SCALE_FAST`; scaling and streams on; no `SVF_JSET_TRUSTED`). Gated: `avr minimal`, `m0plus minimal`, `m0plus default` (text, rodata, data, bss). Not gated, printed as `info`: `minimal+RECOG`, `minimal+JMAP`, `ksonly` (the KS-only build), `allon` (it does not link on the Uno: the ATmega328P's 32 KB overflow by 402 B before Task 7, 2590 B with `SVF_JMAP=1` in it, 2682 B with `SVF_JSET_BIG=1` and the Group D / final-review code as well (`check-features.sh` run of 2026-10-27 at 4ef4398); the Cortex-M0+ row is 14867 B, `check-features.sh` info line) and `avr default` (the AVR default equals `minimal`: version 1 reader alone, `SVF_JSET_POP4` 0). The symbol rule (`nm --defined-only` of the linked probe) and the strings rule (AVR: no `JMAP` or `jmap` in `.text`; the other targets: none of `JMAP`, `jmap`, `BIG` in `.rodata*`/`.data`; an objcopy failure fails the gate) run on the same builds. text is `size` text, the read-only data included; rodata the `.rodata*` sections, a part of text (0 on AVR: its read-only data is in the program memory section); bss is the probe's own buffers.

| toolchain | config | text | rodata | data | bss |
|---|---|---:|---:|---:|---:|
| avr | minimal | 12930 | 0 | 0 | 834 |
| m0plus | minimal | 6162 | 0 | 0 | 848 |
| avr | minimal+RECOG | 13238 | 0 | 0 | 834 |
| avr | minimal+JMAP | 15370 | 0 | 0 | 843 |
| avr | minimal+JMAP+nolist | 15002 | 0 | 0 | 843 |
| avr | ksonly | 13460 | 0 | 0 | 843 |
| avr | ksonly+nolist | 13118 | 0 | 0 | 843 |
| avr | minimal+BIG | 12956 | 0 | 0 | 834 |
| avr | minimal+BIG+V2 | 15314 | 0 | 0 | 834 |
| m0plus | minimal+RECOG | 6358 | 0 | 0 | 848 |
| m0plus | minimal+JMAP | 7646 | 16 | 0 | 860 |
| m0plus | minimal+JMAP+nolist | 7398 | 16 | 0 | 860 |
| m0plus | ksonly | 6822 | 16 | 0 | 860 |
| m0plus | ksonly+nolist | 6606 | 16 | 0 | 860 |
| m0plus | minimal+BIG | 6158 | 0 | 0 | 848 |
| m0plus | minimal+BIG+V2 | 7369 | 51 | 0 | 848 |
| m0plus | default | 7381 | 51 | 0 | 848 |
| m0plus | allon | 15155 | 115 | 0 | 860 |

Task 5 (JSET_UNREAD / JMAP_UNREAD status split, 2026-10-26): status split +10 B AVR minimal, +16 B Cortex-M0+ minimal, -60 B Cortex-M0+ default (one shared magic and version check instead of one per reader); JMAP recognition behind `SVF_JMAP_RECOG` (default 0 on AVR, `SVF_SMALL` and MCUs; +266 B AVR and +152 B Cortex-M0+ when on (+210 / +140 before review round 1, which added the flag and NS checks, the truncated-fallback verdict and the mapped-region rule): the info rows `minimal+RECOG`, minimal flags plus `-DSVF_JMAP_RECOG=1`, not gated). The first, unconditional version of the recognition measured +220 / +156 B on the minimal builds and was refused. The old baselines of the three gated rows were AVR 12920, Cortex-M0+ minimal 6146, Cortex-M0+ default 7441.

Task 6 (JMAP reader, 2026-10-26, card t_380104f8): the gated rows are unchanged (`SVF_JMAP` defaults to 0 there). The `minimal+RECOG` rows grew by 14 B AVR and 12 B Cortex-M0+ (the 0xFFFF region test; the status assignment replacing the xor is free). The info rows `minimal+JMAP` (minimal flags plus `-DSVF_JMAP=1`; the JMAP reader replaces the recognition) cost +1842 B AVR and +1092 B Cortex-M0+ over `minimal` (+1562 / +928 over `minimal+RECOG`), more than the plan's estimate (+450..700 AVR, +300..450 Cortex-M0+): R1-R8 validation inlined into `svf__jset_check` (~340 B Cortex-M0+), the entry decoder (100 B), the lookup (+228 B) and the version 1 validator no longer inlined; `svf_face` grows 9 bytes (bss 9 / 12 B more in the probe).

Task 7 (defaults, 2026-10-26, card t_380104f8): `SVF_JMAP` now defaults to 1 on `__unix__ _WIN32 __APPLE__ __DJGPP__ __EMSCRIPTEN__` builds (not `__AVR__`, not `SVF_SMALL`), 0 on every MCU: the gated rows and every AVR, Cortex-M, ESP32 and CH582 row are unchanged. New info rows `ksonly` (the KS-only build, `-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0` on the minimal flags, built `-Werror` clean): +106 B AVR and +384 B Cortex-M0+ over `minimal`, 1732 B / 716 B under `minimal+JMAP`; `allon` now includes `-DSVF_JMAP=1` (14879 B, bss 860). The one-line fix of this task (`svf_jamo_pieces` reads the JMAP only when `jmap_off` is set) moved `minimal+JMAP` to AVR 14768 (-4) and Cortex-M0+ 7262 (+8). The symbol rule gains `check_absent default jmap`. Port rows (`build-all.sh --ports`): only `port-dos` SVFDEMO.EXE 264,632 -> 265,753, `port-web` svf.wasm 37,611 -> 38,727 and the informational SDL programs moved; no Pico, ESP32, Uno or CH582 row did. sizeof(svf_face) on the host is 96 B with `SVF_JMAP` (the cap), 76 B with `-m32 -DSVF_JMAP=1` (64 B budget measured with `-DSVF_JMAP=0`).

Task 17 (BIG defaults, 2026-10-27, card t_380104f8): `SVF_JSET_BIG` defaults to 1 on the same list as `SVF_JMAP` (not `__AVR__`, not `SVF_SMALL`, `__unix__ _WIN32 __APPLE__ __DJGPP__ __EMSCRIPTEN__`), 0 on every MCU: the gated rows and every AVR, Cortex-M, ESP32 and CH582 row are unchanged. New info rows `minimal+BIG` (minimal flags plus `-DSVF_JSET_BIG=1`, version 1 reader) and `minimal+BIG+V2` (minimal flags with `-DSVF_JSET_V2=1` and `-DSVF_JSET_BIG=1`): AVR +26 B / +2384 B and Cortex-M0+ -4 B / +1207 B over `minimal`; against the same reader set without BIG (AVR `JSET_BOTH` P1 15242, Cortex-M0+ `default` 7381) BIG+V2 is +72 B AVR and -12 B Cortex-M0+. The plan's estimate (AVR +60..120 B, Cortex-M0+ +24..64 B) is not met on the low side for `minimal+BIG` (AVR +26 B, Cortex-M0+ -4 B): Task 16 measured the same (Cortex-M0+ `svf_jamo.o` no larger with BIG). The Size switches tables gain a `JSET_BIG` column (`-DSVF_JSET_BIG=1` on the default build of each toolchain). The symbol rule gains `check_absent minimal+BIG jmap`.

JMAP-LIST Task 7 (2026-10-28, card t_3cd5c9fb, parent t_455b15cb): `SVF_JMAP_LIST` defaults to the value of `SVF_JMAP` (host, DOS, WASM, SDL on; every MCU 0; `-DSVF_JMAP_LIST=0/1` wins; 1 without `SVF_JMAP` is an `#error`): the gated rows are unchanged (`avr minimal` 12930, `m0plus minimal` 6162, `m0plus default` 7381). The rows of the table above that are not gated were re-recorded from `check-features.sh` (`~/.local/bin/heavy sh c/cross/check-features.sh /tmp/feat`, `features: OK`); the pre-LIST values the budgets are over are `minimal+RECOG` 13210 / 6326, `minimal+JMAP` 14932 / 7338, `ksonly` 13048 / 6550 (AVR / Cortex-M0+). New info rows `minimal+JMAP+nolist` and `ksonly+nolist` (the same flags plus `-DSVF_JMAP_LIST=0`). `check-features.sh` enforces the `BUDGETS` table (text, exit 1 naming the row): `minimal+JMAP` (LIST on) AVR <= 15532 / M0+ <= 7688 (measured 15370 / 7646), `minimal+JMAP+nolist` <= 15032 / 7398 (15002 / 7398: **zero headroom on Cortex-M0+**: any later byte in the LIST=0 arm or the JMAP reader fails the budget), `ksonly` <= 13648 / 6900 (13460 / 6822), `ksonly+nolist` <= 13148 / 6610 (13118 / 6606), `minimal+RECOG` <= 13250 / 6366 (13238 / 6358). Symbol rule: `check_absent ... jlist` for `minimal`, `default`, `minimal+BIG`, `minimal+BIG+V2`, `minimal+JMAP+nolist`, `ksonly+nolist`. No `jlist_` symbol survives `-Os` on either toolchain, not even in the LIST=1 rows (`nm --defined-only` of the P1 links, `/tmp/feat/features/syms.txt`; every `jlist_*` static is inlined), so the symbol rule is vacuous and the `+nolist` size budgets are the leak guard. Movers of the full run (`~/.local/bin/heavy sh c/cross/build-all.sh /tmp/ba`, exit 0; the Sizes table rows of host-gcc, clang, djgpp and wasm-emcc re-recorded from it, e.g. host-gcc P1 16273 -> 16685, clang P1 18907 -> 19549, djgpp P1 15432 -> 15800, wasm-emcc P1 14293 -> 14822) and of `~/.local/bin/heavy sh c/cross/build-all.sh --ports /tmp/bp-jl` (exit 1 before this table update only for the lines below, 43 OK lines): `port-dos` SVFDEMO.EXE 265,753 -> 266,265, `port-web` svf.wasm 38,590 -> 39,234, `arduino-mega-rich` (builds `-DSVF_JMAP=1`) text 38,630 -> 39,082 (flash end 39,100); SVFVESA.EXE 294,345 B and the SDL programs (84,848 / 85,312) did not change; no AVR, Cortex-M, ESP32 (esp32-xtensa, esp32s3, esp32c3), CH582, Pico or Uno row moved.

The three gated text figures were the baselines of `SIZES.md` above (AVR P1 12920, Cortex-M0+ P1 with `-DSVF_JSET_V2=0` 6146 -- the "JSET_V1" column of Size switches --, Cortex-M0+ P1 7441), reproduced by the new script with no tuning.

## Port examples

Measured 2026-10-20 with `c/cross/build-all.sh --ports`, re-measured 2026-10-21 on the merge with the VESA packed kinds and 2026-10-22 with the SVFN v3 reader (Task 4: glyph offset table, record expansion, general layout units; no `SVF_LAYOUTS` set yet), after Task 6 (the v2 path gone, the embedded faces in v3 `default`) and in Task 7 (the faces embedded in the `mcu-strict` profile by `c/bench/mkface.py --profile mcu-strict`, hence the smaller **faces** column; the Arduino image also built with `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`) and in the Task 7 fix round 1 (the reader's speed fixes: +464 to +512 bytes of code on the Pico and ESP32 images, which link the stream reader; -260 on the Arduino image, which does not) and in the C speedups Task 6 (the `svf__merge` word path, 2026-10-23: +148 to +196 bytes of code on the Pico and ESP32 images; the Arduino image builds with `SVF_MERGE_WORDS` 0 and is unchanged; SVFDEMO.EXE +512, svf.wasm +262) and in the C speedups Task 7 (the 64-byte nibble table of the 1 bpp GRAY8 blit, 2026-10-23: +172 to +204 bytes on the GRAY8 images only; SVFDEMO.EXE +30, svf.wasm +126): each image is `main.c`, the profile, the display driver, the library
and the profile's faces, linked bare against the no-op SDK stubs (no vendor SDK; the real-SDK links are not
measured here). **faces** is the bytes of the embedded `.SVF` files; **text** includes
them; **text without faces** (text - faces) is the column to read for code. The embedded faces' notices and licences are in
`c/ports/FACES.md`. `build-all.sh --ports` compares this table with what it measured and fails on a difference. Re-measured 2026-11-03 when the mono face became `svf/dos/NEODG16G.SVF` (10,124 B in `mcu-strict`, +1,408 B over the earlier 8,716 B face): every mono row, the Arduino rows and the Pico and CH582 SDK images grew by exactly those 1,408 B of text; the code (text without faces) is unchanged. Re-measured 2026-10-23 in the compact JSET Task 3 (both JSET readers in the Pico, ESP32, DOS and web builds: +1,244 B on the Pico images (+1,216 with `SVF_SMALL`, which leaves out the popcount table), +1,476 B on ESP32-C3, +1,348 to +1,352 B on ESP32-S3, SVFDEMO.EXE +2,693, svf.wasm +2,902; the Arduino image builds `-DSVF_JSET_V2=0`, the version 1 reader alone: -4 B; the ch582 image builds `-DSVF_JSET_V2=0` too, its one face being version 1: 16,998 -> 16,982 B (-16 B), SDK image 21,064 -> 21,048 B, against 18,478 / 22,536 B with both readers, +1,496 / +1,488 B). The rows `pico-small` and `arduino-small` are the same images built with `-DSVF_SMALL` (Size switches above; the Uno build has `-DSVF_NO_SCALE` and the AVR defaults of the other two switches are 0, so `arduino-small` equals `arduino`).

| port | profile | kind, `SVF_TARGETS` | faces (bytes) | text | data | bss | text without faces |
|---|---|---|---:|---:|---:|---:|---:|
| pico | colour | RGB565 0x08 | 74,660 | 84,306 | 0 | 11,648 | 9,646 |
| pico | grey | GRAY8 0x01 | 74,660 | 84,146 | 0 | 16,772 | 9,486 |
| pico | mono | MONO_PAGE 0x02 | 10,124 | 19,678 | 0 | 1,220 | 9,554 |
| pico-small | colour | RGB565 0x08 | 74,660 | 84,098 | 0 | 11,648 | 9,438 |
| pico-small | grey | GRAY8 0x01 | 74,660 | 83,770 | 0 | 16,772 | 9,110 |
| pico-small | mono | MONO_PAGE 0x02 | 10,124 | 19,470 | 0 | 1,220 | 9,346 |
| esp32c3 | colour | RGB565 0x08 | 74,660 | 86,682 | 0 | 15,488 | 12,022 |
| esp32c3 | grey | GRAY8 0x01 | 74,660 | 86,430 | 0 | 16,768 | 11,770 |
| esp32c3 | mono | MONO_PAGE 0x02 | 10,124 | 22,174 | 0 | 1,088 | 12,050 |
| esp32s3 | colour | RGB565 0x08 | 74,660 | 85,052 | 0 | 15,492 | 10,392 |
| esp32s3 | grey | GRAY8 0x01 | 74,660 | 84,648 | 0 | 16,772 | 9,988 |
| esp32s3 | mono | MONO_PAGE 0x02 | 10,124 | 20,576 | 0 | 1,092 | 10,452 |
| arduino | - | MONO_PAGE 0x02 | 10,124 | 23,676 | 18 | 1,085 | 13,552 |
| arduino-small | - | MONO_PAGE 0x02 | 10,124 | 23,676 | 18 | 1,085 | 13,552 |
| arduino-mega | - | MONO_PAGE 0x02 | 10,124 | 23,802 | 18 | 1,085 | 13,678 |
| arduino-mega-rich | - | MONO_PAGE 0x1FF | 10,124 | 40,490 | 18 | 1,094 | 30,366 |
| ch582 | mono | MONO_PAGE 0x02 | 10,124 | 18,390 | 0 | 1,224 | 8,266 |

The rows `arduino-mega` and `arduino-mega-rich` (added 2026-10-27, card t_eb1d73b4) link the same sketch and NEODG16G `mcu-strict` face for the ATmega2560 (Arduino Mega, 256 KB of flash, 8 KB of RAM; `-mmcu=atmega2560 -Os`, avr-gcc 16.1.0): `arduino-mega` with the Uno flags of the `arduino` row (flash text + data 22,412 B, 22,394 + 18), `arduino-mega-rich` with every target and reader (`-DSVF_TARGETS=0x1FF -DSVF_JSET_V2=1 -DSVF_JMAP=1 -DSVF_JSET_BIG=1`, scaling on, `-DSVF_NO_STREAM` and the `mcu-strict` layout kept: flash 39,100 B, 39,082 + 18). The Mega has no flash budget here. The face data lives in PROGMEM below 64 KB, because `SVF_RD8` is `pgm_read_byte` (a near, 16-bit address read): **faces or data above 64 KB need far reads (`pgm_read_byte_far`, `__flash` far pointers) and are NOT supported and not tested.** `build-all.sh --ports` prints a `FLAG` line when a Mega row's flash end (text + data) reaches 65,536 B (the rows above are 22,412 and 39,100: below it). The Sizes table has the probe rows of `avr-atmega2560` (the same profiles; `build-all.sh` also builds its switch columns, which this file does not tabulate): compile and size only, no Mega board, no emulator.

The original ESP32 (Xtensa LX6, e.g. the Odroid-Go) has the `esp32-xtensa` probe rows in the Sizes table (card t_e8bb0eed; `xtensa-esp32-elf-gcc` of the same tarball, the `esp32s3-xtensa` flags, `-mlongcalls -Os`, which that compiler accepts; compile and size only, no board, no emulator). It has **no port image** here: the port's pins (`disp_*.c`, `profile_colour.c`) exist for the ESP32-C3 and ESP32-S3 only (GPIO 6 to 11 of the original ESP32 are its flash pins, and the Odroid-Go's ILI9341 wiring and init differ), so an image needs new driver and board code, which is out of scope for the size rows.

The `ch582` row (YD-CH582M, SH1106 OLED) is `main.c`, `profile_mono.c` and `disp_sh1106.c` of `c/ports/ch582` with the stub `stub/i2c_stub.c` (a no-op `ch582_i2c_write`) in place of `i2c.c`, linked bare by `riscv32-esp-elf-gcc` (`-march=rv32imac_zicsr_zifencei -mabi=ilp32 -mstrict-align -Os`, `--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main -Wl,--gc-sections`) with the Uno-style switches `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0` (the version 1 reader alone: the port draws the version 1 face NEODG16G; the port Makefile passes the same `SVFDEFS` to the library objects): the SVF side only; the real image with the SDK is the next table's.

(dos: `SVFDEMO.EXE` 266,265 bytes; web: `svf.wasm` 39,234 bytes.)

Task 17 (2026-10-27): `SVF_JSET_BIG` is now on in the dos, web and SDL builds: SVFDEMO.EXE (265,753), SVFVESA.EXE and the SDL programs (84,848 / 85,312) are byte-for-byte the same size as after Task 7, svf.wasm 38,727 -> 38,590 (-137 B).

Task 7 (2026-10-26): `SVF_JMAP` is now on in the dos, web and SDL builds: SVFDEMO.EXE +1,121 B over 264,632, svf.wasm +1,116 B over 37,611.

(informational, not gated: sdl2: `svfsdl2` 84,848 bytes; sdl3: `svfsdl3` 85,312 bytes; measured 2026-10-26 after Task 7 (`SVF_JMAP` on: +120 B each over 84,728 / 85,192).)

The web module was re-measured on 2026-10-21 after main's WASM picker changed `c/ports/web/svf_web.c` (it was 22,407
bytes), and again after the merge with the VESA packed kinds (23,525 before: `svf_web.c` builds the library with the
default `SVF_TARGETS`, so the five new kinds are linked in; SVFDEMO.EXE likewise, 250,708 before). `check-sizes-md.sh` checks both program sizes of the dos/web line above, as it checks the table.

## Pico SDK images

Measured 2026-10-21 (re-measured 2026-10-22 in Task 7, the faces in `mcu-strict`, and in the Task 7 fix round 1, the reader's speed fixes: +1,016 bytes each; and 2026-10-23 in the C speedups Task 6, the `svf__merge` word path: +168 to +176 bytes) with `c/ports/check/run-screens.sh`: the three Pico images built with the real pico-sdk 2.3.1
(`c/ports/pico`, `-DCMAKE_BUILD_TYPE=Release`, `-DPICO_NO_PICOTOOL=1`) and measured with `arm-none-eabi-size` on the
`.elf`. Unlike the stub links above they include the SDK start-up, `pico_stdlib` and the hardware drivers. `text`
includes the embedded faces (`mcu-strict` profile: colour and grey 74,660 bytes, mono 10,124). `run-screens.sh` compares this table with
what it measured and fails on a difference. Re-measured 2026-10-23 in the compact JSET Task 3 (both JSET readers: +1,976 B each).

| profile | text | data | bss |
|---|---:|---:|---:|
| colour | 99,828 | 0 | 12,812 |
| grey | 99,256 | 0 | 17,936 |
| mono | 35,484 | 0 | 2,384 |

## CH582 SDK image

The real image of `c/ports/ch582` (`make -C c/ports/ch582`): the same sources with the port's real `i2c.c` (the
bounded write, not the stub), plus the WCH EVT start-up code and the drivers it needs (`CH58x_gpio`, `CH58x_i2c`, `CH58x_sys`) and the
vendor `libISP583.a`, at 24 MHz (`CLK_SOURCE_PLL_24MHz`, I2C duty 2: 400 kHz SCL), stack 2048 bytes, built with
`riscv32-esp-elf-gcc` and measured with `riscv32-esp-elf-size` and `image_sizes.py` (the faces `mcu-strict`, mono, 10,124
bytes of the text). `text` includes `.highcode`, which lives in RAM and is copied from flash at reset (so it is counted in
`text` and, with the stack, in `RAM used`); `libISP583 kept` is the bytes of allocated `libISP583.a` input sections left
by `--gc-sections`; `RAM used` is data + bss + `.highcode` + stack. `build-all.sh --ports` compares this table with what it
measured and fails on a difference (it is built, and compared, only when the SDK is installed).

| image | text | data | bss | .highcode | libISP583 kept | stack | RAM used |
|---|---:|---:|---:|---:|---:|---:|---:|
| svf_ch582_mono | 22,456 | 20 | 1,232 | 2,576 | 1,062 | 2,048 | 5,876 |

## JSET v3 / BIG identity and gates (Task 18, card t_380104f8, 2026-10-27)

Records only; no gated table above or below is edited by this section. The branch `jset-limits` at 84ae0cf reads `svf/` (and
its version 2 copies) to the pixels of the base 2fb312d reader and the writers emit the base's bytes: the commands and the
totals (`faces=153 jamo=95 different=0` for the default, v1-only, v2-only, JMAP-off and BIG-off builds) are in
`c/bench/JSET2-IDENTITY.md`, section "Identity sweep for JSET v3 (JMAP) and BIG". The gates of the same run, each exit 0:
`make -C c check` (327 tests), `c/cross/build-all.sh`, `c/cross/build-all.sh --ports` (43 OK lines),
`c/cross/check-features.sh` (`features: OK`), `c/cross/test-build-all.sh` (`build-all-gates: OK`),
`c/cross/test-check-features.sh` (`check-features-gates: OK`). Known gap: the atmega2560 variant rows use the same switch set as the atmega328p ones (`JSET_BOTH`, `JSET_V2`, `JSET_TRUSTED`, `JSET_BIG`, `SVF_SMALL`); neither has a JMAP column (the JMAP cost per target is in the `check-features.sh` info rows), and the Mega has no per-switch JMAP/BIG column of its own (follow-up).

## JMAP-LIST identity, budgets and follow-ups (Task 11, card t_3a5f76a5, parent t_455b15cb, 2026-10-28)

Records only; no gated table above or below is edited by this section (every row of the plan's Task 7 was re-taken through
`check-features.sh` and `build-all.sh`, see the "JMAP-LIST Task 7" paragraph under "Minimal config"). The branch `jmap-list`
at 448b61c reads `svf/` to the pixels of the base fa76afb reader (`faces=153 jamo=95 different=0` for the default,
`-DSVF_JMAP_LIST=0`, `-DSVF_JSET_V2=0` and `-DSVF_JMAP=0` builds) and the writers emit the base's bytes (commands and totals in
`c/bench/JSET2-IDENTITY.md`, section "Identity sweep for JMAP-LIST"). Budgets (`check-features.sh` `BUDGETS`, text, enforced
with `-gt`), AVR / Cortex-M0+: `minimal+JMAP` 15370 / 7646 of 15532 / 7688, `minimal+JMAP+nolist` 15002 / 7398 of 15032 /
7398, `ksonly` 13460 / 6822 of 13648 / 6900, `ksonly+nolist` 13118 / 6606 of 13148 / 6610, `minimal+RECOG` 13238 / 6358 of
13250 / 6366. **The Cortex-M0+ `minimal+JMAP+nolist` budget has zero headroom (7398 of 7398):** a byte added to the shared
LIST=0 arm or the JMAP reader fails the next gate; raising it is a ruling, not an edit. No `jlist_` symbol survives `-Os`, so the
`check_absent ... jlist` rule is vacuous; the `+nolist` rows and `test_jmap_nolist_identical` are the leak guard. Gate lines of the Task 11 run (each exit 0): `make -C c check` (349 tests OK), `build-all-gates: OK`, `check-features-gates: OK`, `features: OK`, `build-all.sh --ports` (43 OK lines), `presets: OK 4 builds match the table`; the rest is in the "Implemented" note of
`docs/superpowers/specs/2026-10-27-jmap-list-design.md` (follow-ups (a)-(k) there).

## Findings

- **Known gap: no behavioural AVR run of the GRAY kind.** The AVR-only dispatch cases of `svf_draw_utf8` (GRAY8 and GRAY as separate cases) are compiled with `-Werror` for `SVF_TARGETS` 0x01, 0x200, 0x201 and 0x3FF by `build-all.sh` (the line `avr-atmega328p gray-werror: ok ...`, not an OK line) and linked in AVR P1\*, P4 and P4+GRAY, but no simavr case draws a GRAY or GRAY8 glyph on AVR; the pixels of both kinds are checked on the host and on the Pico (checksums), and the AVR dispatch has the same semantics by inspection only. To be added if a GRAY target on AVR is ever shipped.

- **8 KB budget met on P1 and P2.** (The P1* figures in this bullet are the 2026-10-21/23 ones; P1* is 9434 after the GRAY kind (10681 with the JSET readers on top), see the bullet "Cortex-M0+ P1* after the GRAY kind".) (After the C speedups (Task 10, library at 8bff82e) the Cortex-M0+ P1 and P2 text is **6194 bytes**, 1998 B under the 8192 budget (the scaler is not in them; 6022 before the speedups: word merge +176, cmap midpoint -8, its 16-bit fix +4, the rest rounding), P1* 9190 (8826 before), P3g 8104 (7760), P4 14068 (13412) and P5 11577 (11089); the speedups' own figures and the other toolchains are in "Before -> after the C speedups" above and `c/bench/MEASUREMENTS.md`. Since SVFN v3 the Cortex-M0+ P1 and P2 text was **6022 bytes** (2170 to spare; 5990 in Task 7's fix round, +32 from Task 8's row-loop pointer fix) with `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`: 7764 after Task 4, 7388 after Task 6 (the v2 path dropped, every layout and the stream reader still in), 5830 in Task 7 with the stream reader compiled out and the three units folded to constants (-1558), 5990 after the Task 7 fix round's speed fixes (+160), 6022 at b45e9dc (Task 8, +32). **P1* is 8826** with the same switches and all nine kinds: 634 over 8192, and the nine-kind library costs 2804 bytes more than MONO_PAGE alone (8826 - 6022), as before v3 (2800, below). **Decision (user, 2026-10-22, "빌드크기 ok", accepted by the user): P1* at 8794 B, 602 over 8 KB, is accepted; the budget stays on P1/P2 (MONO_PAGE only) and a small target lists its kinds through `SVF_TARGETS`.** The 8794 B figure was Task 7's; Task 8's pointer fix moved it to 8826 B (+32 B, 634 over), which is reported to the user and not yet separately accepted. The rest of this section's numbers are the pre-v3 measurements, kept as the history of the VESA kinds.) Cortex-M0+ P1 (MONO_PAGE only) and P2, before v3: text 5674 bytes <= 8192 (2518 to spare),
  against 5718 before the fast paths (-44); the VESA kinds did not change them. Only P1 and P2 are gated (the spec's size
  budget). P1* (every target kind compiled in) was 7094 before the VESA kinds and is now 8474, which is 282 over 8192:
  a build with all nine kinds does not fit 8 KB on Cortex-M0+, so a small target lists the kinds it draws with
  `SVF_TARGETS`. The nine-kind library costs 2800 bytes more than MONO_PAGE alone there (8474 - 5674).
  **Decision (user, 2026-10-21): the 8 KB budget stays on P1/P2; P1* being 282 B over is accepted, small targets
  choose their kinds through `SVF_TARGETS`.**
- **Cortex-M0+ P1* after the GRAY kind: 9434 B (+244 over the 9190 B above; 1242 B over 8192; the user accepts or refuses the growth).** On the tree rebased onto the JSET readers: 10437 -> 10681 (+244), the same growth. The parametric kind's packed blitter and its dispatch; a build that does not draw GRAY lists the kinds it draws (`-DSVF_TARGETS=...`) and does not pay it. P1 and P2 stay 6194 B.
- **Cortex-M0+ P1* after the C speedups: 9190 B (accepted 8826 B, +364 B; 998 B over 8192).** Where it moved: Task 6's word path in `svf__merge` 8826 -> 9002 (+176), Task 7's 64 B GRAY8 nibble table and its blit 9002 -> 9194 (+192), Task 9's midpoint shift 9194 -> 9186 (-8), its 16-bit overflow fix (T9-F1) 9186 -> 9190 (+4). Each step stayed under the plan's 200 B stop; the sum (+364) is over it, and the user's acceptance of P1* (8794, then 8826 B) was for the earlier figure: **reported to the user, not yet separately accepted.** P1 and P2 are the gated profiles and have 1998 B to spare. The table is the 64 B of data inside the P1* text; M0+ `SVF_GRAY8_LUT1` is on (it is a Cortex-M win, Task 7), AVR and Xtensa have it off.
- **P3g (GRAY8 only) on Cortex-M0+: 8104 B at 8bff82e, 8100 B after the GRAY kind (92 B under the 8192 reference; 9347 B with the JSET readers, 1155 B over that reference)** (7760 before; +344: word merge +176, the nibble table with its blit +172, Task 9's cmap shift with the T9-F1 fix -4; measured by switch in "Size switches" above). Against the 8192 reference this was 88 B under at 8bff82e.
- **No budget:** RP2350 (Hazard3 6395 / 9418 / P4 14534; Cortex-M33 5528 / 8286 / 13072), ESP32-C3 (7391 / 10758 / 16654) and ESP32-S3 (6523 / 9443 / 14715) have no size budget (P1 / P1* / P4 text); their growth against 4539e42 is 128 to 731 B and is listed above.
- **AVR (`SVF_MERGE_WORDS` and `SVF_GRAY8_LUT1` are 0 there, `-DSVF_NO_SCALE`/no-stream profiles unchanged) at 8bff82e; after the GRAY kind P1 and P2 are 12924, P1* 21286 (+300 over the 20986 here), P3 and P3g unchanged (with the JSET readers, rebased: P1 and P2 12920, P1* 21282, P4 32558, P5 25492, P4+GRAY still over):** P1 12914 / P1* 20986 / P3 16664 / P3g 16166 did not move (switches 0: the code is compiled out); only P4 (32122 -> 32568, +446) and P5 (25052 -> 25498, +446) moved, by the separable scaler of Task 8 (with the loop variables `unsigned`: with 32-bit loop variables P4 overflowed the text region by 822 B). **P4 no longer fits an Uno with the Optiboot bootloader**: 32568 B of text against 32256 (it fit with 134 B to spare before, 32122); the ATmega328P's 32768 B hold it only without the bootloader. P4 is the link-everything probe, not a build anyone ships on an Uno (the Uno builds in this repo are `-DSVF_NO_SCALE`), but any Uno program that uses the scaler with other kinds is bounded by it.
- **Peak stack of the scaled path (T8-S1; `c/cross/stack-usage.py`, gcc `-fstack-usage -fcallgraph-info=su`, worst case over the call graph of `svf_draw_utf8` with the scaler, frames only: return addresses of 2 B (AVR) per call and libgcc's division helpers are not counted, indirect calls (the `read` callback, `svf_plot_cb`) are the caller's to add).** `svf__scale_cell` has a frame of **610 B on AVR (16.1 `-Os`) and 680 B on Cortex-M0+ (15.2.1 `-Os`)**: the separable filter's `acc[64]` (128 B), `cov[255]`, the two axis tables (2 x (16+16+16+32) B) and scalars (543 B of arrays). Worst chain: `svf_draw_utf8` (227 / 280 B) > `svf__scale_cell` > `axis_weights` (27 / 48 B) = **864 B on AVR, 1008 B on Cortex-M0+**; without the scaler (`-DSVF_NO_SCALE`) the deepest chain is the stream reader's, 446 B on AVR and 680 B on M0+; the code before the speedups (4539e42, the scaler with `span`) peaked at 451 B and 680 B (the scale chain was 129 B for the cell). So the scaled path costs **+413 B of stack on AVR and +328 B on M0+** over v3. On an Uno (2048 B of RAM) the P4 probe has **1801 B of statics (data + bss, mostly the probe's own buffers)**: statics + 864 B stack = 2665 B > 2048 B. It did not fit before either (1801 + 451 = 2252 B), so the P4 probe is not an Uno program; a real Uno program that scales must budget about 0.9 KB of stack for the scaled draw beside its statics (the Uno bench build, 1223 B of RAM, has no scaler). **Finding for the user, no code changed:** if scaling on the Uno matters, a smaller column block (`acc`, 128 B) or a shorter `cov` (255 B) would cut it, at the price of more passes. Cortex-M0+ parts have 264 KB (RP2040) and are not at risk. Measured statically (worst case over all paths), not by stack painting.
- **Growth per kind** (Cortex-M0+ text, from the commits 04914b4..ceecb5d; the plan's measured start was 7106, 12 above
  this file's earlier 7094, from Task 1's declarations and `target_ok` fields; the commits sum to +1368, 7094 to 8474 is
  +1380):

  | step | P1* | P4 |
  |---|---:|---:|
  | Task 1 (declarations, `target_ok` fields) | 7094 -> 7106 (+12) | 9718 -> 9730 (+12) |
  | INDEXED8 (1807594) | 7106 -> 7602 (+496) | 9730 -> 10218 (+488) |
  | Task 2 fix rounds | 7602 -> 7618 (+16) | 10218 -> 10230 (+12) |
  | RGB555 (f32102b) | 7618 -> 7850 (+232) | 10230 -> 10462 (+232) |
  | XRGB8888 and RGB888 (a1cb3b1) | 7850 -> 8458 (+608) | 10462 -> 11090 (+628) |
  | Task 4 fix round (put888) | 8458 -> 8474 (+16) | 11090 -> 11106 (+16) |

  P1, P2 and P3 did not move on Cortex-M0+ in any step. AVR P1* 17362 -> 20922 (+3560), P4 23664 -> 27540 (+3876);
  DJGPP P1* 13592 -> 16200, P4 18872 -> 21736.
- **INDEXED8 against the spec's estimate.** The spec estimated about 400 bytes for INDEXED8 on Cortex-M0+; it
  measured +496 in P1* and +488 in P4, about 100 bytes (24 %) over, in the byte loops and the level ramp.
- **P3 (RGB565 only)** is 5802 on Cortex-M0+, against 5906 before the switch (-104), unchanged by the VESA kinds. P4
  (everything, scaling, streaming) is 11106, against 9718 (+1388) before the VESA kinds and 8298 before the switch.
- **P3w (P3 with `-DSVF_WORD_STORE=1`)** is P3 plus the RGB16 word path where the switch is 0 by default: Cortex-M0+
  5802 -> 6106 (+304; the M0+ P1 and P2 stay 5674 and P3 5802, the switch being 0 there), AVR 12320 -> 13732 (+1412),
  ESP32-C3 7075 -> 7435 (+360). Where the switch is 1 by default (host gcc, clang, DJGPP, WASM) P3 and P3w are equal
  and both grew (the table above): +368 host gcc, +720 clang, +608 DJGPP, +779 WASM. Only P3w builds with a forced
  switch on a target that cannot do unaligned word stores; the speed rows (Task 10) measure x86 only.
- **P5 (the DOS example's profile: streamed face, block cache, scale 3/2, INDEXED8, RGB555, RGB565, XRGB8888, RGB888
  with `-DSVF_TARGETS=0x1E8`)**: 16576 bytes on DJGPP (the DOS example's toolchain; 16016 before the word stores, 16752 with the 1 bpp INDEXED8 word path Task 10 dropped), 8795 on Cortex-M0+, 18633 on
  host gcc (18057 before the word stores), 20484 on AVR; on Cortex-M0+ 2311 under P4 (the mono, GRAY8 and callback blits and the unused public functions
  are left out). P5 is a link-and-size profile, not a runnable one.
- **Probe buffers.** P4's `screen` grew from 16*8*2 to 16*8*4 bytes (stride 64 for every kind, so XRGB8888 fits): bss
  P4 1560 -> 1816 on Cortex-M0+ and ESP32-C3, 1539 -> 1795 on AVR, 1672 -> 1928 on host gcc, 1632 -> 1888 on clang.
  These are the probe's own bytes, not the library's, which still has none.
- **P1 on host gcc, clang and WASM** grew by 16, 32 and 6 bytes with `-DSVF_TARGETS=0x02` unchanged (code layout of the
  shared dispatcher); DJGPP, Cortex-M0+, AVR and ESP32-C3 did not move.
- **put888 on Cortex-M0+**: the 4 and 3 byte stores of XRGB8888 and RGB888 stay `memcpy` calls there (no unaligned word
  stores); only DJGPP and AVR get inline stores.
- **Arduino Uno** (port-arduino, ATmega328P, MONO_PAGE only, `-DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, the face 8716 bytes in `mcu-strict`): text 22262, data 18 bytes of
  flash, 22280 of 32256 (22270 before the GRAY kind: the `svf_target` struct byte; 22250 before Task 8, 22510 in Task 7, 26442 before Task 7 with the 12921 byte pre-v3 face; about 31.2k before the switch) (cross build with stub Wire and core,
  `c/cross/build-all.sh --ports`; the README's arduino-cli build was not run: arduino-cli is not installed). ESP32-C3 P1
  6935, P1* 10111 (8495 before the VESA kinds), P3 7075. The bench build (`c/bench/run-avr.sh`, `-DSVF_TARGETS=0x1F`)
  fits in 27434 bytes of flash at b45e9dc (27414 after the Task 7 fix round, 27674 in Task 7, 31302 pre-v3; `-DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, the face in `mcu-strict` 8716 bytes).
- **Ports**: the sizes of the nine MCU images, the Arduino Uno build and the DOS and web programs are in the "Port examples"
  table above (cross builds with stub SDK calls; the README's arduino-cli build was not run: arduino-cli is not installed).
  The ESP32-C3 and ESP32-S3 library rows are in the table of sizes.
- **P1 and P2 are the same link.** The library has no bits-per-pixel switch: 1, 2 and 8 bpp are all in every build
  (`svf__coverage`, `svf__merge`), chosen per face at run time.
- **Target kinds are compile-time.** `blit` used to be one function with every target kind, so a link kept all of
  them (about 1394 bytes of P1 in the earlier measurement). With `SVF_TARGETS` each `blit_*` and its helpers (`blend565`,
  `pack8`/`least_level` for MONO_ROW or MONO_PAGE, `mono_src`, `transpose8`) are compiled only when a kind that uses
  them is listed; a kind left out is `SVF_E_ARG`. Code that `--gc-sections` still cannot remove: the streamed-face and
  syllable-cache paths (`svf_glyph`, `svf_compose`, `svf_draw_utf8`), reached through run-time tests.
- **P3g** is smaller than P3 on every MCU and on wasm. Only the x86-64 clang row is larger (15795 against 12451): clang
  auto-vectorises the grey blit with SSE on that host, which no MCU target has.
- **AVR** has no budget: ATmega328P P1 is 12914 bytes (12848 pre-v3), P1* 20986 (20922 pre-v3, 17362 before the VESA kinds). **`-DSVF_SMALL` brings AVR P4 back to 32122 B, inside an Optiboot Uno's 32256 B, and the scaled-path stack to 451 B** (Size switches above).
- Every toolchain builds every `c/src/*.c` with `-Werror` (as is, `-DSVF_NO_SCALE`, and the SVF_TARGETS sets) and
  links every profile: host gcc, clang, DJGPP, Cortex-M0+, AVR, ESP32-S3, ESP32-C3 and WASM all `OK`.
- Library constant tables of a forced-version-2 AVR build (`compat_lead`, `limits`, `pop4`) are `PROGMEM` and read with `pgm_read_byte`, and the block magic is compared byte by byte, so `-DSVF_JSET_V2=1` adds no `.data` (RAM) on an ATmega328P (it held 40 B, 56 B with `SVF_JSET_POP4=1`, before; avr-size counted that read-only `.data` as text, so the rows never showed it).
