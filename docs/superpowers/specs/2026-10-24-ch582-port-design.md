# CH582M port of the C SVF renderer (YD-CH582M + SH1106 OLED): design

Card t_1a4449f3, 2026-10-24. Branch ch582-port from main c592140. Inputs: the Pico and ESP32 ports (`c/ports/pico`,
`c/ports/esp32`, `c/ports/check`), `c/cross/SIZES.md` and `install-toolchains.sh`, the CH582 datasheet (Chinese, V1.3;
`ch582-sdd/ds.pdf`), the WCH CH583 EVT at openwch/ch583 commit bd508ad, the SH1106 datasheet, and the user's direction:
"set up a development environment for the CH582M board and build a sample app using the SVF C renderer"; the user is
remote, so "just prepare": no hardware is attached, and everything must be ready so that flashing is one documented
command when the board is plugged in. Calls made here are marked **(design call)**; everything else was decided in
conversation, read from a datasheet or SDK, or measured.

## Why

The C renderer has three MCU ports (Pico, ESP32, Arduino Uno) and every one of them draws the same text through a
`display_show` of pages. The CH582M is a cheap RISC-V BLE part with 32 KB of SRAM and 448 KB of code flash: a fourth
architecture (WCH RISC-V4A, rv32imac) and the smallest RAM the ports have met after the Uno. The sample is deliberately
the existing `mono` profile (128 x 64, 1 bpp HGKEY6J, MONO_PAGE) so that its correctness is judged by the same svfline
reference the other ports use, not by eye.

## Goals

1. `c/ports/ch582/`: a Makefile build that produces `svf_ch582_mono.elf` (plus `.bin`, `.hex`, `.map`) from `main.c`,
   `profile_mono.c`, `disp_sh1106.c`, the library and the embedded face, with the pinned toolchain and SDK.
2. One flash command (`make flash`, which runs `wchisp flash build/svf_ch582_mono.elf`) with the Linux udev rule and the
   BOOT-button sequence written down.
3. Host verification without a panel: the driver's byte stream against the SH1106 command tables, and the whole image's
   drawing (profile + driver) through a C model of the SH1106 compared byte for byte with the svfline reference.
4. The port in `c/cross/build-all.sh --port ch582` (stub link, a row in the "Port examples" table of SIZES.md) and the
   real-SDK image sizes recorded like the "Pico SDK images" table.
5. A README in the shape of the Pico one: wiring table, build, flash, "what was checked", and in so many words
   "not yet tried on a panel".

## Non-goals

- Running on hardware. The real-panel run (and any fix it needs: offset, remap, contrast) is a follow-up card.
- A debugger flow. WCH-Link + wlink is mentioned for the day it is needed; nothing here depends on it.
- Grey or colour profiles on this board, timing measurements, low power, USB device code.

## Anti-goals

- No BLE stack, no `LIBCH58xBLE.a`, no FreeRTOS: the image is bare metal, polling, no interrupts of its own.
- No vendor IDE dependency: no MounRiver Studio, no `.cproject`; a Makefile and a stock GCC.
- No unpinned download: every fetched thing has a URL, a version and a sha256 (or a git commit checked before use).
- No claim that the panel works. The README says what was checked and what was not.
- No new format or library change: SVF v3 only, the library as it is on main.

## Constraints

- **Chip** CH582M (QFN48): WCH RISC-V4A core, RV32IMAC, 512 KB FlashROM of which 448 KB CodeFlash for the application
  (`0x00000000`, 448K in the SDK link script), 32 KB SRAM at `0x20000000`, hardware I2C (100/400 kHz, 7/10-bit), 2 USB
  controllers, 2-wire debug on PB14 (TIO) / PB15 (TCK). Datasheet V1.3 (`ch582-sdd/ds.txt`, pin table lines 470-590).
- **RAM** 32 KB is the budget to respect. The image's RAM: 1,024 B frame + the face struct, chain and 32 B scratch
  (the Pico stub-linked mono image has bss 1,220 B, `SIZES.md` "Port examples"), the SDK's `.highcode` functions copied
  to RAM at reset (`SetSysClock`, `mDelayuS`, `mDelaymS`, `SYS_ResetExecute`, `HardFault_Handler`: a few hundred
  bytes), `.data`, and the stack. The SDK link script sets `__stack_size = 512`; the deepest `svf_draw_utf8` chain
  without the scaler is 680 B on Cortex-M0+ (`SIZES.md`), so the port's copy of the link script sets **2048 B**
  **(design call)**. Total well under 8 KB; the number goes in the README.
- **No hardware now.** Everything is proved on the host or by a cross-link; the hardware-only items (pin mapping,
  panel variant, I2C timing, the USB bootloader) are listed, not claimed.

## Decided in conversation

### Board: YD-CH582M (VCC-GND Studio), the generic "CH582M 2-channel USB dev board"

Photo `ch582-sdd/yd-ch582m.jpg`. Labels read from it: Type-C connector, a USB-A host receptacle, BOOT and RST
buttons, PWR LED, an LED labelled PB4, a 2 x 4 header (8 holes) (3V3, GND and the debug pins), and two pin rows:
`3.3V B14 B12 B10 B6 B4 B2 B0 B23 B21 B19 GND` and `GND B15 B13 B11 B7 B5 B3 B1 B22 B20 B18 GND`, plus the PA row.

| part | pin | status |
|---|---|---|
| Type-C = USB1 (ISP bootloader) | PB10 UD-, PB11 UD+ | datasheet; the ISP port of every CH58x |
| USB-A host port = USB2 | PB12 U2D-, PB13 U2D+ | **assumption** from the board (U2D-/U2D+ are the only other USB pins); unverified |
| BOOT | PB22, hold during reset or power-on for the USB ISP bootloader | wchisp's CH58x device table: `DOWNLOAD_CFG` 1 = PB22 (default) |
| RST | PB23 (RST#, internal pull-up) | datasheet |
| LED | PB4 (the silkscreen says PB4; polarity unknown) | assumption: active low through a resistor like the WeAct board; the firmware toggles it, so either polarity shows |
| 2 x 4 header | PB14 TIO, PB15 TCK + 3V3/GND | guess: the 2-wire debug header |

### I2C on the remapped pins

PB12/PB13 are USB2's D-/D+ on this board, so the OLED uses the I2C remap: `R16_PIN_ALTERNATE` bit 11 `RB_PIN_I2C` = 1
moves SCL_/SDA_ to **PB21 (SCL) / PB20 (SDA)** (datasheet 7.x, SDK `GPIOPinRemap(ENABLE, RB_PIN_I2C)`). Hardware I2C,
master, 7-bit address **0x3C**, **400 kHz** (`I2C_Init(I2C_Mode_I2C, 400000, I2C_DutyCycle_16_9, I2C_Ack_Enable,
I2C_AckAddr_7bit, own)`), pins configured `GPIO_ModeIN_PU` (the datasheet's table 7-4: input with pull-up, open-drain
driven when needed; the SDK's I2C example does the same on PB12/PB13). Internal pull-ups on, module pull-ups expected too.

Wiring: OLED VCC -> 3.3V, GND -> GND, SCL -> **B21**, SDA -> **B20**. Both are on the two-row header along the bottom edge, on different rows: B21 on the inner row (between B23 and B19; the row starts with 3.3V), B20 on the edge row (between B22 and B18; the row starts with GND). B22, next to B20, is BOOT.

### The sample

The same screen as the Pico `mono` profile: four 16 px lines of `svf/iolo/HGKEY6J.SVF` (1 bpp jamo set) drawn with
`SVF_T_MONO_PAGE` into a 1,024 B frame and shown once. `c/ports/ch582/profile_mono.c` is the Pico file with the board
name in its first line: **"CH582 SVF 예제"**, then "다람쥐 헌 쳇바퀴", "에 타고파! 1bpp", "안녕하세요" **(design call:
the ESP32 port does the same; `screens.py` gets a `ch582` board row, so the reference is built by the same path and the
first line names the board on the panel)**. The reference is `screen_ref.py --ref-only ch582 mono`.

### Port layout: `c/ports/ch582/`

Following the Pico port's shape:

```
c/ports/ch582/
  Makefile          build, size, flash, clean (below)
  main.c            SetSysClock(60 MHz; 24 MHz as built, see "Changes during implementation"); display_init(); profile_run(); svf_port_idle()
  display.h         OLED_W 128, OLED_H 64, display_init, display_show (the Pico names and contract)
  profile.h         the Pico file (profile_run, svf_port_idle, svf_port_text[], svf_port_text_n)
  profile_mono.c    the Pico profile with the CH582 first line
  i2c.h / i2c.c     ch582_i2c_write(addr, buf, n): one bounded, polled master write on the SDK's I2C API
  disp_sh1106.c     the SH1106 driver on ch582_i2c_write and DelayMs
  led.h             PB4 as the status LED (GPIOB_SetBits/ResetBits/InverseBits)
  link.ld           the SDK's Link.ld with __stack_size 2048 (its origin and the one change noted at its top)
  README.md
  stub/             host stand-ins: CH58x_common.h (the handful of SDK calls as no-op or recording inlines), svf_stub_record.h
```

`profiles.txt` gets no new column: the CH582 builds one profile and reads nothing from the table **(design call)**;
`host-checks.sh` still takes the `mono` row's faces and `SVF_TARGETS` bit for the profile test, as it does for the others.

## Toolchain, SDK and flash tool

| what | choice | pinned at | verified |
|---|---|---|---|
| compiler | `riscv32-esp-elf-gcc` 16.1.0 (Espressif crosstool-NG esp-16.1.0_20260609), the `esp` toolchain `c/cross/install-toolchains.sh` already installs | the URL and sha256 in `SIZES.md` ("Downloads", row `esp`: `0b029ab3...`) | the installed copy builds and links `-march=rv32imac_zicsr_zifencei -mabi=ilp32` with `--specs=nano.specs --specs=nosys.specs`: it selects the multilib `rv32imac_zmmul_zaamo_zalrsc_zca/ilp32` and the ELF carries `rv32i2p1_m2p0_a2p1_c2p0_zicsr2p0_zifencei2p0` (checked 2026-10-24) |
| SDK | WCH CH583 EVT, GitHub openwch/ch583, commit `bd508ad7ceed48377619837051412a651952857f` ("Update EVT to v2.4", 2025-08-14, default branch main), Apache-2.0 `LICENSE` at the root; only `EVT/EXAM/SRC/` is used (Ld, RVMSIS, Startup, StdPeriphDriver: 596 KB, 45 files) | the commit (checked before anything in the clone is read, like pico-sdk) and a `manifest.sh` manifest of `EVT/EXAM/SRC` pinned in the installer | downloaded 2026-10-24 (tree listing and the GitHub source tarball of the commit, sha256 `f5faf578...24f` of a 101,462,588-byte archive; GitHub does not promise byte-stable source tarballs, so the pin is the commit plus the file manifest, not that sha) |
| flash tool | wchisp v0.3.0 (ch32-rs/wchisp, 2024-10-03), `wchisp-v0.3.0-linux-x64.tar.gz` 883,953 bytes, one static binary; CH582 is in its CH58x device table (`devices/0x16-CH58x.yaml`) and its README's tested list (CH58xM-EVT, WeAct CH582F) | URL `https://github.com/ch32-rs/wchisp/releases/download/v0.3.0/wchisp-v0.3.0-linux-x64.tar.gz`, sha256 `67e3d4eb0ffd3cc610d8927e3c3f452e2110531a3f14405dcaef87df219f200d` (computed from the download; the release lists no digest) | downloaded 2026-10-24; not run (no board) |
| alternative compiler (documented, not installed) | xPack riscv-none-elf-gcc 15.2.0-1 (`xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz`, 433,494,794 bytes) | sha256 `aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758` | the publisher's `.sha` file and GitHub's asset digest both say so (fetched 2026-10-24); not downloaded |
| debug (not needed here) | wlink v0.1.3 (ch32-rs/wlink, 2026-10-21) with a WCH-Link on PB14/PB15 | sha256 `b0d55a32...9d8` (GitHub asset digest) | not downloaded |

**Why the ESP toolchain (design call).** The CH58x is a plain RV32IMAC machine-mode core; the SDK's startup and drivers
need nothing a stock GCC lacks once two things are handled (next paragraph). The `esp` toolchain is already pinned,
installed and verified on this host, carries the rv32imac/ilp32 newlib-nano multilib, and gives the port a SIZES.md
toolchain row with no new download. xPack 15.2.0-1 is the documented alternative (same flags; a Makefile variable
`CROSS=riscv-none-elf-` switches). MounRiver's `riscv-wch-elf-gcc` (GCC 12 with WCH's XW extension and the
`WCH-Interrupt-fast` attribute) is rejected: it ships inside the IDE bundles with no stable URL or published sha256,
and nothing here needs its extensions. The SDK's own `.cproject` targets rv32i + M/A/C, ilp32, soft float,
`-Os`, code model any, and the `riscv-none-embed-` prefix (GCC 8).

**What the SDK needs from the compiler, read from the sources at bd508ad:**

- `Startup/startup_CH583.S` sets `gp`, `sp = _eusrstack`, copies `.highcode` and `.data` from flash to RAM, clears
  `.bss`, writes two WCH CSRs by number (`csrw 0xbc0` pipeline/prediction, `csrw 0x804` nested interrupts and hardware
  stacking), sets `mstatus`, `mtvec = _vector_base | 3` and `mret`s into `main`. Numeric CSRs assemble with any GAS;
  `-march` must include `zicsr` (and `zifencei` for `fence.i`), hence `rv32imac_zicsr_zifencei`.
- `CH58x_common.h` defines `__INTERRUPT` as `__attribute__((interrupt("WCH-Interrupt-fast")))` unless `INT_SOFT` is
  defined, when it is `__attribute__((interrupt()))`. Stock GCC warns on the WCH string and drops the attribute, which
  `-Werror` turns into an error; `CH58x_sys.c` uses `__INTERRUPT` on `HardFault_Handler`. So every SDK source is compiled
  with **`-DINT_SOFT`**, and the port defines no interrupt handler of its own.
- `__HIGH_CODE` is `section(".highcode")`; the link script places it in RAM, `AT>FLASH`; stock GCC handles it.
- `CH58x_sys.c` and `CH58x_pwr.c` reference `FLASH_ROM_SW_RESET` from `StdPeriphDriver/libISP583.a` (a 5,374-byte WCH
  binary archive inside the Apache-2.0 repository). The link lists it (`-L .../StdPeriphDriver -lISP583`) so the SDK
  sources link as WCH wrote them; `SetSysClock` does not call it, but `HardFault_Handler` (kept in the vector table)
  does, so some of its bytes are expected to stay after `--gc-sections`
  **(design call: link it rather than patch sys.c; the README records whether any of its bytes stayed)**.
- The register names differ from the datasheet's (`R16_I2C_CTRL1` in the SDK, `R16_I2C_CTLR1` in the manual); the port
  uses the SDK's API (`CH58x_i2c.h`, `CH58x_gpio.h`, `CH58x_sys.h`), not raw registers.

## Build system

`c/ports/ch582/Makefile`, GNU make, run from anywhere (`make -C c/ports/ch582`). Variables, all overridable:

| variable | default | meaning |
|---|---|---|
| `CROSS` | `riscv32-esp-elf-` | compiler prefix; `riscv-none-elf-` for xPack |
| `CH583_SDK` | `$(OPT)/ch583-evt`, `OPT` default `~/opt` | the clone; the Makefile reads `$(CH583_SDK)/EVT/EXAM/SRC` |
| `WCHISP` | `$(OPT)/wchisp-0.3.0/wchisp` | the flash tool |
| `BUILD` | `build` (under `c/ports/ch582`; `build/` is already gitignored) | outputs |

Targets: `all` (elf, bin, hex, map, then `size`), `size` (`$(CROSS)size` and the `.highcode`/`.data`/`.bss`/stack sum printed
as "RAM used"), `flash` (`$(WCHISP) flash $(BUILD)/svf_ch582_mono.elf`), `clean`. The Makefile refuses with a one-line
message when `$(CH583_SDK)/EVT/EXAM/SRC/Ld/Link.ld` is missing ("run c/cross/install-toolchains.sh ch583").

**Fetching (design call: extend `c/cross/install-toolchains.sh`, do not add a second installer).** Two new names:

- `ch583`: `git clone --depth 1 --filter=blob:none --sparse https://github.com/openwch/ch583` to
  `PREFIX/ch583-evt`, `git sparse-checkout set EVT/EXAM/SRC`, checkout of the pinned commit, HEAD checked equal to
  `bd508ad7ceed48377619837051412a651952857f` before anything is read, then `manifest_write` of `EVT/EXAM/SRC` and a
  `MANIFEST_PIN_ch583` in the script (the builder pastes the printed pin). `--verify` is HEAD == commit, a clean
  `git status --porcelain`, and the manifest. The sparse checkout keeps the 100 MB of BLE libraries, HarmonyOS and
  tools out of the tree.
- `wchisp`: the tarball at the URL above, sha256 checked, unpacked flat to `PREFIX/wchisp-0.3.0/` (it holds
  `wchisp-linux-x64/wchisp` and a README), manifest pinned like the other tarballs.

No new compiler to install; the `esp` name covers it.

**Faces.** The face array is generated at build time by `python3 -I c/bench/mkface.py svf/iolo/HGKEY6J.SVF
build/faces/svf_face_data.c --name svf_face_data --profile mcu-strict` (the Pico/ESP32 rule), never committed.

**Compiler flags.**

- Every source: `-march=rv32imac_zicsr_zifencei -mabi=ilp32 -mcmodel=medany -msmall-data-limit=8 -mstrict-align -Os
  -ffunction-sections -fdata-sections -g`. `-mstrict-align` **(design call)**: whether the V4A core takes unaligned
  loads is not documented in what was read; the library never needs them (`SVF_WORD_STORE` is 0 on RISC-V).
- The port's own files and the library: `-std=c99 -Wall -Wextra -Werror` plus the library switches below.
- The SDK's files (`CH58x_gpio.c`, `CH58x_i2c.c`, `CH58x_sys.c`, `CH58x_clk.c`, `CH58x_pwr.c`, `RVMSIS/core_riscv.c`,
  `Startup/startup_CH583.S`): `-DINT_SOFT -DFREQ_SYS=60000000 -w` (vendor code written for GCC 8; not held to
  `-Werror`) **(design call)**. `CH58x_clk.c` and `CH58x_pwr.c` are listed because `sys.c` and `clk.c` cross-reference
  (`SYS_DisableAllIrq`, safe-access sequences); the builder trims the list to what links.
- Link: `-T link.ld -nostartfiles --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections -Wl,-Map=...
  -Wl,--print-memory-usage -L$(SDK)/StdPeriphDriver -lISP583`.

**Library switches (design call):** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT
-DSVF_TARGETS=0x02`: the P1 profile of SIZES.md (mapped face only, one layout, MONO_PAGE only). The Pico mono image
links the stream reader because its CMake shares one rule with grey and colour; this port has one profile and no SD
card, so it drops the reader. `SVF_SMALL` stays off (flash is not short; the word merge and the GRAY8 table are the
measured defaults). No `SVF_RD8` override: the face array is in flash at a plain address.

## Firmware behaviour

`main`: `SetSysClock(CLK_SOURCE_PLL_60MHz)` (changed: 24 MHz as built, see "Changes during implementation"; the clock every EVT example uses; `I2C_Init` derives its timing from
`GetSysClock()`), LED off, `display_init()`, `profile_run()`, then `svf_port_idle()`.

**LED as the only status output (design call):** `svf_port_idle` is reached on success (after `display_show`) and on
every failure path (the profile's `svf_*` checks, an I2C timeout). To tell them apart without a serial port:
`display_show` returns nothing (the Pico contract), but the driver records the last I2C error in a static flag that
`svf_port_idle` reads: **steady on** = the frame went out, every byte acknowledged; **blink at 2 Hz** = an I2C write
timed out or was NACKed (no panel, wrong address, wrong pins); **blink at 8 Hz** = an `svf_*` call failed before any show.
`svf_port_idle` loops on `DelayMs` and `GPIOB_InverseBits(GPIO_Pin_4)`; it stays an own non-inlined symbol.

No stdio, no `PRINT`, no interrupts, no sleep modes.

## I2C layer and the SH1106 driver

### `ch582_i2c_write(uint8_t addr, const uint8_t *buf, size_t n)` -> 0 ok, -1 timeout/NACK

One master write, polled, in the order the SDK's I2C example uses: wait while `I2C_FLAG_BUSY`; `I2C_GenerateSTART`;
wait `I2C_EVENT_MASTER_MODE_SELECT`; `I2C_Send7bitAddress(addr << 1, I2C_Direction_Transmitter)` (the SDK writes its
argument to `R16_I2C_DATAR` as it is, with bit 0 as R/W: 0x3C goes on the wire as 0x78; the SDK example's own constants
0x42/0x52 are the 8-bit form too); wait `I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED`; per byte wait
`I2C_FLAG_TXE`, `I2C_SendData`; wait `I2C_EVENT_MASTER_BYTE_TRANSMITTED`; `I2C_GenerateSTOP`. Every wait is bounded
(a spin count sized to about 10 ms at 60 MHz **(design call)**; changed: see "Changes during implementation"); on expiry or `I2C_FLAG_AF` (NACK) the function clears
the flag, sends STOP, and returns -1. A 129-byte page write at 400 kHz is about 3 ms. `display_init` configures the pins
first: `GPIOPinRemap(ENABLE, RB_PIN_I2C)`, `GPIOB_ModeCfg(GPIO_Pin_20 | GPIO_Pin_21, GPIO_ModeIN_PU)`, then `I2C_Init`.

### `disp_sh1106.c`

The SH1106 (datasheet: 132 x 64 RAM, 8 pages) differs from the SSD1306 in three ways the Pico driver relies on: it has
**no horizontal addressing mode** (`0x20`, `0x21`, `0x22` do not exist; the column pointer increments within a page and
every page is addressed on its own with `0xB0 + page`, column low nibble `0x00..0x0F`, high nibble `0x10..0x1F`), its
charge pump is **`0xAD 0x8B`** (not `0x8D 0x14`), and 128-wide modules sit at **columns 2..129** of the 132, so every
page write starts at column 2. The I2C framing is the same as the SSD1306's: control byte `0x00` before a command,
`0x40` before data; a command is sent as ONE write together with its argument (`0x00, cmd` or `0x00, cmd, arg`),
never with the argument in a separate write: the SH1106 datasheet does not say whether a STOP between a double-byte
command and its argument clears the half-received command, and the one-write framing is valid either way **(design
call)**. A page goes as one 129-byte write (`0x40` + 128 bytes), never a nostop split.

Init, in order (the SH1106 command table, section numbers of the datasheet):

```
0xAE            display off                                   (11)
0xD5, 0x80      clock divide ratio / oscillator               (15)
0xA8, 0x3F      multiplex 64                                  (9)
0xD3, 0x00      display offset 0                              (14)
0x40            display start line 0                          (4)
0xAD, 0x8B      DC-DC on                                      (10)
0x32            pump voltage 8.0 V (the power-on value)        (3)
0xA1            segment remap: column 131 -> SEG0             (6)
0xC8            COM scan reversed: COM63 -> COM0               (13)
0xDA, 0x12      COM pads alternative                          (17)
0x81, 0x80      contrast (power-on value)                     (5)
0xD9, 0x22      pre-charge/dis-charge                         (16)
0xDB, 0x35      VCOM deselect level                           (18)
0xA4            show RAM                                      (7)
0xA6            not inverted                                  (8)
0xAF            display on                                    (11)
```

then `DelayMs(100)` before the first show (the DC-DC needs to settle; the datasheet's power-on sequence waits after
`0xAF`) **(design call: the values 0x80/0x22/0x35 are the ones the common SH1106 libraries use; the datasheet gives no
single "right" set, so the README lists them as the first things to tune on a real panel)**.

`display_show(buf, y, rows)`: the Pico contract (refuses NULL, `rows <= 0`, `y < 0`, past the panel, `rows` or `y`
not a multiple of 8). Per page `p` from `y / 8`: three commands `0xB0 + p`, `0x02` (column low nibble of 2),
`0x10` (column high nibble of 2), then the 129-byte data write. So a full-frame show is 8 x (3 commands + 1 data
write) = 32 I2C writes, against the SSD1306's 6 + 8.

The one byte to change for the common variants: `0x02` -> `0x00` in the column-low command for a module whose RAM
starts at column 0 (a 128 x 64 SSD1306 sold as "SH1106", or a 132-wide module that shows the image shifted 2 px);
`0xA1, 0xC8` -> `0xA0, 0xC0` for a module mounted upside down. Both are `#define`s at the top of the driver
(`SH1106_COL_OFFSET`, `SH1106_REMAP`) **(design call)** so the host test can be run with the alternative too.

## Host verification (design call throughout: there is no CH58x emulator in the tree)

Three layers, all in `c/ports/check` and `c/cross`, wired exactly where the Pico's are:

1. **Driver byte stream** (`test_drivers.c`, new section `DRV_SH1106`, built by `host-checks.sh` with
   `driver ch582 c/ports/ch582 c/ports/ch582/stub sh1106 DRV_SH1106`). The stub `CH58x_common.h` provides
   `GPIOPinRemap`, `GPIOB_ModeCfg`, `I2C_Init` (each reporting through `svf_rec_cfg` with new `SVF_CFG_*` codes),
   `DelayMs` (`svf_rec_sleep`) and the LED macros (no-op); `ch582_i2c_write` is not stubbed at all: the port's `i2c.c`
   is not on the test's command line, the test defines `ch582_i2c_write` itself as `svf_rec_i2c(addr, p, n, 0); return
   0;`. The test asserts the init sequence above (per command write, `0x00, cmd[, arg]`; `DRV_SH1106` gets its own expectation helper, since
   `ex_cmds` expects one byte a write), the per-page command triplet and
   data write for `(0, 64)`, `(8, 16)`, `(56, 8)`, the refusals, and the error path: a second build where the test's
   `ch582_i2c_write` returns -1 once must make the driver stop sending and raise its error flag. The `--gc-sections`
   marker check (`svf_port_driver_sh1106`) as for every driver.
2. **Profile** (`test_profiles.c`, unchanged): `profile ch582 c/ports/ch582 ch582 mono` in `host-checks.sh`. Needs the
   `ch582` board in `screens.py` (`BOARDS`, `BIGENDIAN` 0, the `lines` of the mono profile; colour and grey get the
   `ch582` entry too, copied from `pico`, so `--check` and `screen_ref.py` keep one table). The real
   `profile_mono.c` draws through a recording `display_show`; the bytes equal `ch582-mono.ref`.
3. **Panel model** (new `c/ports/check/test_sh1106_panel.c`, run by `host-checks.sh`): links `main.c` (with
   `-Dmain=port_main` and the stub SDK), `profile_mono.c`, `disp_sh1106.c`, the library (the port's switches) and the
   generated face against a C model of the SH1106: 132 x 8 bytes of RAM, a page register (`0xB0..0xB7`), a column
   register (low/high nibble commands), the two remap bits, DC-DC and display on/off state; a data byte goes to
   `ram[page][col]` and `col++` (writes past column 131 are dropped and counted; a page is never crossed, as the
   datasheet says); unknown commands are counted, never fatal. `ch582_i2c_write` feeds it (control byte `0x00`: each
   following byte a command, a double-byte command's argument taken from the same write; a write that ends
   between a double-byte command and its argument is an error, no state carried across writes; `0x40`: data). After `port_main` returns (the
   test's `svf_port_idle` returns instead of looping) the test requires: display on, DC-DC on, `0xA1`/`0xC8` set, no
   unknown command, no dropped byte, exactly 8 page fills of 128 bytes each starting at column 2, and the window
   `ram[p][2..129]` for the 8 pages equal, byte for byte, to the 1,024-byte `ch582-mono.ref` of `screen_ref.py`. The
   model also writes the window as `OUT/ch582-mono.fb` so `screen_ref.py ch582 mono OUT` makes the PNG and the diff
   the other boards get (`c/build/screens/ch582-mono.png`, not committed). A negative run (the test built with
   `-DSH1106_COL_OFFSET=0`) must differ at a known byte, proving the compare bites.
4. **Cross link**: `c/cross/build-all.sh --port ch582` builds the image with the `esp` toolchain against `stub/` (no
   SDK; `main.c`, the profile, the driver, `i2c.c` excluded and `ch582_i2c_write` a stub returning 0) and adds the row
   `ch582 | mono | MONO_PAGE 0x02 | faces | text | data | bss | text without faces` to the "Port examples" table;
   `check-sizes-md.sh` compares it. With the SDK installed (`CH583_SDK` set, as `PICO_SDK_PATH` gates the Pico's SDK
   build), `build-all.sh` also runs `make -C c/ports/ch582` and compares `riscv32-esp-elf-size` with a new table
   "CH582 SDK image" in SIZES.md (text, data, bss, `.highcode` bytes, `libISP583` bytes kept).

`build-all.sh --ports` then prints 4 more OK lines (`port-ch582`, `port-check-driver-ch582-sh1106`,
`port-check-profile-ch582-mono`, `port-check-sh1106-panel`); the README and `build-all.sh`'s count comment change with it.

## Flashing (README content)

1. Once: `sudo tee /etc/udev/rules.d/50-wchisp.rules` with `SUBSYSTEM=="usb", ATTRS{idVendor}=="4348",
   ATTRS{idProduct}=="55e0", MODE="0666"` (wchisp's README; VID 4348 = WCH, PID 55e0 = the ISP bootloader), then
   `sudo udevadm control --reload-rules && sudo udevadm trigger`.
2. Hold BOOT, plug the Type-C port into the host (or tap RST while holding BOOT), release BOOT. `lsusb` shows `4348:55e0`.
3. `make -C c/ports/ch582 flash` (= `wchisp flash build/svf_ch582_mono.elf`; `wchisp info` first if in doubt: it names
   the chip and the bootloader version). wchisp resets the chip into the application after writing.
4. The OLED shows the four lines; the PB4 LED is steady on. A 2 Hz blink means the panel did not answer (wiring, address,
   pins); 8 Hz means the drawing failed before any show (should not happen: the host test runs the same code).

The README states, as the Pico one does: not run on hardware; the pin mapping of the board, the panel variant, the I2C
timing and the ISP sequence are "only built, not run".

## Left to the builder

- The exact SDK source list that links (start with the six files above; drop what is not needed, add what the link
  asks for) and the `MANIFEST_PIN_ch583` / `MANIFEST_PIN_wchisp` values after the first install.
- The spin-count constants of `ch582_i2c_write`, with the cycle arithmetic in a comment.
- `stack-usage.py` on the image (`-fstack-usage`) to confirm 2048 B of stack is generous; the RAM sum in the README.
- Whether `SetSysClock` from `.highcode` works when called from `main` before anything else (it is the first line of
  every EVT example, so yes, but the builder checks that `.highcode` is copied by the startup it links, which is the
  SDK's).
- The `screens.py --check` width rule for the new first line ("CH582 SVF 예제" must fit 128 px at x 0; if it does not,
  shorten to "CH582 SVF").

## Questions only the user can answer (none block the build)

- None for the design. For the follow-up hardware card: whether the OLED module is a true SH1106 (132-column RAM) or an
  SSD1306 sold as one decides `SH1106_COL_OFFSET`; the first panel run tells.

## Design calls made here (summary)

1. Toolchain: the already-pinned `esp` riscv32-esp-elf-gcc 16.1.0, xPack 15.2.0-1 documented as the alternative, MounRiver rejected.
2. SDK fetched by `install-toolchains.sh` (name `ch583`: sparse git clone of `EVT/EXAM/SRC` at commit bd508ad, manifest pinned); wchisp by the same script (name `wchisp`).
3. SDK sources compiled with `-DINT_SOFT -w`; `libISP583.a` linked as the SDK expects, its retained bytes recorded.
4. Library switches: the P1 set (`SVF_NO_SCALE`, `SVF_NO_STREAM`, `SVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, `SVF_TARGETS=0x02`); `-mstrict-align`; no `SVF_SMALL`.
5. Link script: the SDK's with `__stack_size` 2048.
6. First line "CH582 SVF 예제" and a `ch582` board row in `screens.py`.
7. Clock 60 MHz PLL (changed: 24 MHz, see "Changes during implementation"); LED on PB4 as the only status output (steady / 2 Hz / 8 Hz).
8. I2C writes bounded (about 10 ms), NACK and timeout reported, STOP always sent; a command and its argument in one write.
9. SH1106 init values (contrast 0x80, pre-charge 0x22, VCOM 0x35, pump 0x32), column offset 2 and remap as `#define`s; 100 ms after display on.
10. Host verification in three layers plus the stub cross-link, with a panel model in C and a negative run.
11. No `profiles.txt` column for the CH582; `build-all.sh --port ch582` gated on `CH583_SDK` for the real-SDK sizes.

## Changes during implementation

The sections above are the design as written; the built port differs in these points (the README and `c/cross/SIZES.md`
carry the built figures):

- **24 MHz and `I2C_DutyCycle_2` replace 60 MHz and `I2C_DutyCycle_16_9`.** The I2C module clock must be 2..36 MHz
  (`I2C_Init` writes the system clock in MHz into the FREQ field), so 60 MHz is out. At 32 MHz the SDK's divider truncates
  (CCR) and gives about 427 kHz SCL with duty 16/9 (about 410 kHz with duty 2), over the SH1106's 400 kHz. At 24 MHz with duty 2 the divider is
  24e6 / (400e3 x 3) = 20, exactly 400 kHz. `main.c` calls `SetSysClock(CLK_SOURCE_PLL_24MHz)` and the Makefile has
  `-DFREQ_SYS=24000000`; `host-checks.sh` requires the two to agree.
- **Wait bound.** Each I2C wait polls at most `CH582_I2C_SPIN` = 5000 times (`i2c.h`), a count, not a time; the "about 10 ms at 60 MHz" of the design is not claimed.
- **One write per command with its argument** (`0x00, cmd, arg`), as designed, and one 129-byte write per page; unchanged,
  noted because the stub records exactly these writes.
- **`.highcode` is about 2.6 KB** (2,576 bytes), not "a few hundred bytes": the vector table, `CH58x_sys.c`'s single
  `.highcode` content (the vector table 146, `CH58x_sys.o` 1,368, and all 1,062 bytes of `ISP583.o`: 2,576 in the map). The RAM total
  stays under 8 KB (5,872 bytes with the 2,048-byte stack when this was written; 5,876 after the RAM clear below); `image_sizes.py` gates it at 8,192.
- **Final review fixes (card t_1a4449f3).**
  - *SSD1306 variant.* `disp_sh1106.c` has a controller switch `OLED_SSD1306` (default 0): with 1 the init sends the SSD1306
    charge pump `8D 14` and page addressing `20 02` instead of the SH1106's `AD 8B` and `32`, the contrast, pre-charge and
    VCOMH values of the Pico SSD1306 driver (`CF`, `F1`, `40`), and `SH1106_COL_OFFSET` defaults to 0. Without it an
    SSD1306 sold as SH1106 stayed blank (no charge pump). The per-page stream is unchanged.
  - *Reset recovery.* `display_init` waits `SH1106_RESET_MS` (20 ms) before the first command (the SH1106 needs up to 2 ms
    after RES rises, and modules put an RC on RES).
  - *RAM clear.* Before display-on (`AF`) `display_init` writes zeros to all 8 pages, 132 columns each (one data write per
    page, same per-page addressing as `display_show`): the power-on RAM is noise. This costs 8 x 4 writes (about 30 ms at
    400 kHz) and 104 bytes of text, 4 of bss (the page buffer holds 133 bytes); the sizes in `SIZES.md` and the README are re-measured.

