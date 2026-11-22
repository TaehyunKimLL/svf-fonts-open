**English** | [한국어](README.ko.md)

# CH582M example (YD-CH582M board, SH1106 128 x 64 OLED over hardware I2C): mono profile, bare metal

One image, `svf_ch582_mono`: the WCH CH582M (RISC-V RV32IMAC, 32 KB SRAM, 448 KB CodeFlash) on the YD-CH582M board
draws four lines of `svf/dos/NEODG16G.SVF` (the 1 bpp jamo set, `MONO_PAGE`) on a 1.3" SH1106 OLED and stops. `main.c` runs
`SetSysClock(CLK_SOURCE_PLL_24MHz); led_init(); display_init(); profile_run();` and then `svf_port_idle()` (the
status LED). Bare metal and polled: no stdio, no `PRINT`, no interrupts, no BLE stack, no sleep modes, no vendor IDE
(a Makefile and a stock GCC with the WCH EVT sources). **Not yet tried on a panel**: nothing here has run on a board
(see "What was checked").

**The image runs at 24 MHz**, not the 60 MHz of the EVT examples: the CH582's I2C module clock must be 2..36 MHz
(`I2C_Init` writes the system clock in MHz into its FREQ field), and at 32 MHz the SDK's divider gives about 427 kHz
SCL with the 16/9 duty (about 410 kHz with duty 2), over the SH1106's 400 kHz limit either way. At 24 MHz with `I2C_DutyCycle_2` the divider is exactly 24e6 / (400e3 x 3) = 20,
so SCL is 400 kHz. `FREQ_SYS=24000000` in the Makefile must match `main.c`'s `SetSysClock`.

## Board

Labels read from the board's photo; the status column says what is known and what is assumed.

| part | pin | status |
|---|---|---|
| Type-C = USB1 (ISP bootloader) | PB10 UD-, PB11 UD+ | pins: datasheet (the ISP port of every CH58x); that the Type-C connector is wired to them is a **board assumption**, like the USB-A row |
| USB-A host port = USB2 | PB12 U2D-, PB13 U2D+ | **assumption** from the board (the only other USB pins); unverified |
| BOOT button | PB22: hold during reset or power-on for the USB bootloader | wchisp's CH58x device table (`DOWNLOAD_CFG` 1 = PB22, the default) |
| RST button | PB23 (RST#, internal pull-up) | datasheet |
| LED | PB4 (silkscreen "PB4"); polarity unknown | **assumption**: active low (the LED between 3V3 and the pin, like the WeAct board); the firmware blinks, so either polarity shows a pattern |
| PWR LED | (power) | -- |
| 2 x 4 header (8 holes in the photo) | PB14 TIO, PB15 TCK + 3V3/GND | **guess**: the 2-wire debug header |

PB12/PB13 are taken to be USB2's D-/D+ on this board (the assumption in the table; they are also on the pin rows as B12/B13), so the OLED uses the I2C pin remap (`GPIOPinRemap(ENABLE, RB_PIN_I2C)`):
**SCL on PB21, SDA on PB20**. Hardware I2C master, 7-bit address 0x3C, 400 kHz, the pins `GPIO_ModeIN_PU` (internal
pull-ups on; the module's own pull-ups help).

Wiring. Both pins are on the two-row header along the board's bottom edge, on different rows: **B21 on the inner row**
(between B23 and B19; this row starts with 3.3V) and **B20 on the edge row** (between B22 and B18; this row starts with GND).
B22, next to B20, is the BOOT pin: do not wire to it.

| OLED | board |
|---|---|
| VCC | 3.3V |
| GND | GND |
| SCL | **B21** |
| SDA | **B20** |

## Build

Needs `make`, `python3` (the face array comes from `c/bench/mkface.py` at build time, not committed) and, installed
under `$HOME/opt` by the repository's installer:

    sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
    make -C c/ports/ch582

That makes `build/svf_ch582_mono.{elf,bin,hex,map}`, `build/licences/` and prints the sizes. `make size` prints them again,
`make flash` (below), `make clean` removes `build/`. Variables (all overridable on the command line):

| variable | default | meaning |
|---|---|---|
| `OPT` | `$(HOME)/opt` | where the installer put the tools |
| `CROSS` | `$(OPT)/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-` | compiler prefix (`riscv32-esp-elf-gcc` 16.1.0, the `esp` toolchain; it is not on `PATH`) |
| `CH583_SDK` | `$(OPT)/ch583-evt` | the WCH CH583 EVT clone (only `EVT/EXAM/SRC/` and the root `LICENSE` are used); the Makefile stops with a message when its `Ld/Link.ld` or `LICENSE` is missing |
| `WCHISP` | `$(OPT)/wchisp-0.3.0/wchisp` | the flash tool |
| `BUILD` | `build` | output directory |
| `EXTRA_CFLAGS` | empty | extra flags for the port's own files (the driver variants below) |
| `STACK_INFO` | empty | `1` adds `-fstack-usage -fcallgraph-info=su` (read by `c/cross/stack-usage.py`) |

A change of `EXTRA_CFLAGS`, `STACK_INFO` or any other flag rebuilds the objects (a flag stamp, `build/obj/flags.stamp`).

The alternative compiler is xPack riscv-none-elf-gcc 15.2.0-1 (documented, not installed here; same flags):
`https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v15.2.0-1/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz`
(433,494,794 bytes, sha256 `aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758`); use it with
`make -C c/ports/ch582 CROSS=riscv-none-elf-` (with its `bin/` on `PATH`).

Why the flags: the SDK's sources (`CH58x_gpio.c`, `CH58x_i2c.c`, `CH58x_sys.c`, `startup_CH583.S`) are written for the
WCH GCC 8 and get `-DINT_SOFT -w`: `INT_SOFT` makes `__INTERRUPT` the plain `interrupt()` attribute (stock GCC rejects
WCH's `"WCH-Interrupt-fast"`, which `-Werror` would turn into an error) and `-w` keeps vendor warnings out of a `-Werror` build.
The port's files get `-std=gnu99` because the WCH headers (`core_riscv.h`) use `asm volatile` in a static inline,
which `-std=c99` rejects; the library and the host and stub builds stay `-std=c99`. `-mstrict-align` is on because
the core's handling of unaligned loads is not documented (the library never needs them). The library is built with
`-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0` (mapped face, one layout,
`MONO_PAGE` only, the JSET version 1 reader alone: the port draws the version 1 face NEODG16G, as the Arduino port does; drop
`-DSVF_JSET_V2=0` from `SVFDEFS` in the Makefile, which reaches the library objects too, to open version 2 faces, about +1.5 KB of flash). `link.ld` is WCH's `EVT/EXAM/SRC/Ld/Link.ld` byte for byte except one functional change, `__stack_size = 2048`, and a provenance header comment
(WCH has 512); `libISP583.a` (WCH's binary, in the Apache-2.0 EVT repository) is linked because `HardFault_Handler`
calls into it.

## Flash

Over the Type-C port with [wchisp](https://github.com/ch32-rs/wchisp) v0.3.0 (GPL-2.0; a separate tool that is only run
to flash, never linked into the image).

1. Once, a udev rule so the bootloader is reachable without root: put
   `SUBSYSTEM=="usb", ATTRS{idVendor}=="4348", ATTRS{idProduct}=="55e0", MODE="0666"` in
   `/etc/udev/rules.d/50-wchisp.rules`, then `sudo udevadm control --reload-rules && sudo udevadm trigger`.
2. Hold the BOOT button (PB22) while plugging in the Type-C cable, then release. If `lsusb` shows nothing, unplug, hold
   BOOT and plug in again. (Holding BOOT and tapping RST with the cable in works only if the RST pin function is enabled
   in the chip's configuration: the datasheet's default is off, and this board's setting is unknown.)
   `lsusb` shows `4348:55e0` (the WCH ISP bootloader). Some WCH bootloaders enumerate as `1a86:55e0` instead; if `lsusb`
   shows that, add a second rule line with `ATTRS{idVendor}=="1a86"` (wchisp handles both).
3. `make -C c/ports/ch582 flash` (rebuilds a stale image first, checks the flash placement, then runs
   `wchisp flash build/svf_ch582_mono.elf`). `~/opt/wchisp-0.3.0/wchisp info` shows the chip if in doubt.
4. The board resets into the program. The LED on PB4 tells the outcome: **steady on** = the frame went out and every
   byte was acknowledged; **2 Hz** = an I2C write timed out or was not acknowledged (no panel, wrong address, wrong pins);
   **8 Hz** = an `svf_*` drawing call failed. The LED polarity is assumed (active low); if it is the other way round,
   steady reads as off but the blink patterns still show. If the LED blinks 2 Hz after you pressed RST (not after a
   power-up), power-cycle the board: the panel may be holding SDA low.

## Variants of the module

The driver assumes the usual 132-column SH1106 module with the 128 visible columns at RAM columns 2..129, mounted with
(0, 0) at the top left. Three switches change that (`EXTRA_CFLAGS`, given to `flash` and to `make`/`size` alike: a flag
change rebuilds the objects, so a plain `make flash` afterwards would rebuild the default image and flash that,
discarding the variant):

- `OLED_SSD1306` (default 0): 1 for a real SSD1306, which a module sold as "SH1106" sometimes is. The init then sends the
  SSD1306's charge pump (`8D 14`) and page addressing (`20 02`) instead of the SH1106's DC-DC (`AD 8B`) and pump voltage
  (`32`), the contrast, pre-charge and VCOMH of the Pico SSD1306 driver, and the column offset defaults to 0.
  With the SH1106 init such a panel stays blank while the LED still reports success.
- `SH1106_COL_OFFSET` (default 2): the RAM column of the first visible column; 0 for an SH1106 whose RAM starts at it
  (the picture shows shifted by two columns otherwise).
- `SH1106_REMAP` (default 1: segment remap `0xA1` and COM scan reversed `0xC8`): 0 for a picture rotated by 180 degrees.

(a) an SH1106 with its RAM at column 0:

      make -C c/ports/ch582 EXTRA_CFLAGS=-DSH1106_COL_OFFSET=0 flash

(b) a real SSD1306:

      make -C c/ports/ch582 EXTRA_CFLAGS=-DOLED_SSD1306=1 flash

(c) a module mounted upside down (any controller; add the flag to (a) or (b) as needed, e.g. `'-DOLED_SSD1306=1 -DSH1106_REMAP=0'`):

      make -C c/ports/ch582 EXTRA_CFLAGS=-DSH1106_REMAP=0 flash

The init waits 20 ms (`SH1106_RESET_MS`) after power-up before the first command, clears the whole display RAM (all 8 pages,
132 columns: it holds noise at power-up) and only then switches the display on.

If the picture is faint or flickers, the init values to tune first are clock `0xD5, 0x80`, pre-charge `0xD9, 0x22`,
contrast `0x81, 0x80`, VCOM deselect `0xDB, 0x35` and the pump voltage `0x32` (`disp_sh1106.c`, the init table); they are the values common SH1106
libraries use, not values from a measurement (the SSD1306 values are the Pico driver's).

## Debug (not needed here)

wlink v0.1.3 (`https://github.com/ch32-rs/wlink/releases/download/v0.1.3/wlink-v0.1.3-linux-x64.tar.gz`, 826,918 bytes,
sha256 `b0d55a32adf55214e7b6bf29b5eb45c61a13252622e2be3bf5dba7573e4359d8`) with a WCH-Link on PB14/PB15 is the way to
debug this chip; nothing here uses it and it is not downloaded.

## Memory

From the build and `make -C c/ports/ch582 size` (24 MHz build, the faces included; the `.bin` size is the file's, the stack peak comes from a `STACK_INFO=1` build read by `c/cross/stack-usage.py`):

| | bytes |
|---|---:|
| flash image (`.bin`) | 21,068 |
| text (code, constants, faces 10,124; `.highcode` counted) | 22,456 |
| `.highcode` (vector table, `CH58x_sys.c`'s single section, `libISP583`; lives in RAM, copied from flash at reset) | 2,576 |
| of which `libISP583.a` kept after `--gc-sections` | 1,062 |
| data | 20 |
| bss | 1,232 |
| stack (`__stack_size`) | 2,048 |
| RAM used (`.highcode` + data + bss + stack) | 5,876 of 32,768 |
| stack peak of `main` (`STACK_INFO=1`, `c/cross/stack-usage.py`: `main` > `profile_run` > `svf_draw_utf8` > ... > `svf__merge`) | 640 |

The linker's own `--print-memory-usage` reports RAM at 100% because `.stack` sits at the top of the 32 KB; the RAM
total above is `image_sizes.py`'s sum. `image_sizes.py` also refuses an image whose RAM total is over 8,192, or whose loadable segment ends past
`0x70000` (wchisp programs segments at their load address, so `.highcode` and `.data` must be loaded in flash). The same
sources linked against the no-op stubs of `c/ports/ch582/stub/` (no SDK): text and faces: see the "ch582 mono" row
(`c/cross/SIZES.md`, "Port examples").

## Licences

`build/licences/` holds `FACES.md` (each face's source, copyright and licence), `LICENSE-OFL.txt`, `LICENSE-MIT.txt` and the
EVT's Apache-2.0 `LICENSE-ch583-evt.txt` with WCH's "Attention" notice `NOTICE-ch583-evt.txt`. A distributed image must carry them. `link.ld` is WCH's (Apache-2.0) with the one functional change above and a provenance comment at its top.

## What was checked

**Not yet tried on a panel.** No board was attached; nothing was flashed or run.

| check | status |
|---|---|
| host checks (`sh c/ports/check/host-checks.sh`): the driver's command stream (SH1106 and SSD1306 builds), the I2C layer against a scripted peripheral (timeouts, NACK, STOP), the real `profile_mono.c`, the panel model with its negative case | yes |
| stub link (`c/cross/build-all.sh --ports`, `riscv32-esp-elf-gcc` against `stub/`) | yes: text 18,390, faces 10,124 (text without faces 8,266) |
| SDK image (the real EVT start-up and drivers, `make -C c/ports/ch582`) | yes: text 22,456, data 20, bss 1,232; `.highcode` 2,576; `libISP583` 1,062 bytes kept |
| the stub's SDK names and values against the real headers (`c/ports/check/ch582_sdk_values.c`) | yes |
| runs on the board | **no** |
| only built, not run: the pin mapping of the board (PB20/PB21 remap, the USB pins, the BOOT button), the panel variant (column offset, remap, init values), I2C timing (400 kHz at 24 MHz), the ISP sequence (udev rule, BOOT, `wchisp`), the LED polarity | listed, not run |
