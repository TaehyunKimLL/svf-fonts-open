# Pico, ESP32-C3 and ESP32-S3 port profiles (colour TFT, grey OLED, mono OLED), emulated screens and benches: design

Card t_47ca86d1, 2026-10-20, revision 5 (changelog at the end; revision 5 records rulings taken during execution). Follow-up of t_b5256c18
(`docs/superpowers/specs/2026-10-20-blit-fast-paths-design.md`, the `SVF_TARGETS` switch) on top of t_78219730
(`spec/renderer-design.md`, `c/ports/`, `c/bench/`). Neighbours: t_6ab9ec2d (VESA kinds; wants a Pico RGB565
measurement, "Pico RGB565 rows for the VESA card" below) and t_8e7da3c1 (GRAY4 target, after VESA; "The grey profile
and GRAY4 later" below). Plan: to be written from this document.

## Why

Each microcontroller example drives one display: the Pico an SSD1306 (`SVF_T_MONO_PAGE`, `-DSVF_TARGETS=0x02`), the
ESP32 an ILI9341 (`SVF_T_RGB565`, `0x08`). The user wants both boards to support colour and grey too, even where
that is slow: a Pico with a TFT and an ESP32 with a mono OLED are at least as common as the two pairings shipped.
Support and correctness come first; speed is measured and recorded, not budgeted, for the small LCD and OLED
targets (user, 2026-10-20). The card's close criterion is binding: three profiles per port built by
`c/cross/build-all.sh --ports` with sizes in `c/cross/SIZES.md`; `c/bench/run-pico.sh` measuring RGB565 and GRAY8
next to MONO_PAGE (syllable, line, screen; `-Os` and `-O2`) with checksums ok; an ESP32 bench (emulated or
cycle-counted) or a documented reason; `c/bench/MEASUREMENTS.md` rows for each; `make -C c check` green.

**User decisions, 2026-10-20.** Revision 1: the ESP32-S3 (Xtensa LX7) is in scope next to the ESP32-C3 (RV32IMC),
with the same three profiles, sizes and a bench; the original ESP32 (LX6) is not. The Pico colour panel is an
ST7789 240 x 240. Espressif's QEMU and Xtensa toolchain are installed under `~/opt` with the publisher's checksums
pinned. Revision 2: **emulated screens** (card close updated): the real Pico binaries run under rp2040js with
virtual SSD1306, SSD1327 and ST7789 panels on the emulated I2C/SPI peripherals, each panel's memory saved as PNG and
compared byte for byte, in the panel's pixel format, with `tools/svfline.py`; the ESP32-C3/S3 colour example draws
on QEMU's `esp_rgb` panel, captured with the monitor's `screendump` under `-display none` and compared the same way;
PNGs kept as artifacts. These are the end-to-end check and replace nothing in the recording-stub driver tests.

## What changes, what does not

- `c/ports/pico/` and `c/ports/esp32/` gain a build option `SVF_PROFILE` with the values `colour`, `grey`, `mono`,
  one profile source and one display driver each per value, and READMEs that say what was verified. The ESP32 port
  gains a second colour display backend, `esp_rgb` (QEMU's panel). The library (`c/src`, `c/include`) does not
  change: no new kind, no new flag, no API. The profiles are consumers of what exists.
- `c/ports/check/` is new: recording stubs, driver and profile host tests, the rp2040js panel models and runner,
  the QEMU screen runner, the `svfline` screen reference, `run-screens.sh`.
- `c/cross/build-all.sh --ports` builds nine stub images (Pico x 3, ESP32-C3 x 3, ESP32-S3 x 3) instead of two and
  runs the host checks; `c/cross/SIZES.md` gets a port table and an `esp32s3-xtensa` toolchain;
  `c/cross/install-toolchains.sh` installs the Xtensa toolchain and the pico-sdk and re-verifies installs.
  `c/ports/arduino`, `dos`, `web` are untouched.
- `c/bench/bench.c` (the `BENCH_MCU` section) gains a target kind option and a few cases; `c/bench/run-pico.sh` runs
  it per kind; a new `c/bench/run-esp32.sh` runs it under QEMU for both ESP32 chips; `c/bench/install-emulators.sh`
  installs that QEMU and the rp2040js boot ROM file; `c/bench/MEASUREMENTS.md` gets the rows; `c/bench/pico-run.mjs`
  adds an instruction count. `report.awk` does not change.
- The gate `make -C c check` does not change; it must stay green (the ports, checks and benches are host-tool work
  outside it, as before).

## The profiles

One profile is chosen at configure time. A profile fixes the target kind (and so the `SVF_TARGETS` bit the library is
compiled with), the faces embedded, the draw buffer, the drawing loop and the display driver linked.

| profile | kind, `SVF_TARGETS` | display the example drives | faces (flash) | draw buffer (RAM) | drawing |
|---|---|---|---|---|---|
| `colour` | `SVF_T_RGB565`, `0x08` | Pico: ST7789 240 x 240 over SPI (user's choice). ESP32-C3/S3: ILI9341 320 x 240 over SPI, as today; or QEMU's `esp_rgb` 320 x 240 (`SVF_DISPLAY=esp_rgb`) | PAPLG16 (ASCII, 2 bpp) + PAPLG18 (2 bpp jamo): 139,457 bytes | one text band, `PORT_LCD_W` x 24 px RGB565: 11,520 bytes on the Pico (240), 15,360 on the ESP32 (320) | band by band: a clear pass of H / 24 = 10 bands at y = 24 i filled with `bg565`, then five text bands at y = 16 + 28 i: fill, draw one line at the band's baseline 19 (x 8), `display_show(band, y, 24)`. Byte order from the driver (`display_565_bigendian`) |
| `grey` | `SVF_T_GRAY8`, `0x01` | SSD1327 128 x 128 grey OLED (16 levels, two pixels a byte); Pico over I2C (address 0x3C), ESP32 over 4-wire SPI (*my call*: each port keeps the bus its stubs already model) | the same PAPLG16 + PAPLG18 pair (anti-aliasing is the point of a grey panel) | a 128 x 128 GRAY8 frame: 16,384 bytes | whole frame: clear, draw every line at its screen baseline (x 4, baselines 17 + 24 i), one `display_show(frame, 0, 128)`; the driver packs to the panel's 4 bits |
| `mono` | `SVF_T_MONO_PAGE`, `0x02` | SSD1306 128 x 64 (Pico over I2C as today; ESP32 over 4-wire SPI, the 7-pin modules) | HGKEY6J (16 px 1 bpp jamo): 12,921 bytes | the 1 KB page frame, exactly `OLED_W * OLED_H / 8` bytes (no transport byte in front of it) | whole frame as today: clear, four lines at x 0, baselines 16 i + ascent, one `display_show(frame, 0, 64)` |

The band and frame loops are different code (a band loop draws each line at a band-relative baseline and sends after
each line; a frame loop draws at screen baselines and sends once), as are the face sets (one face, 32 bytes of
scratch; two faces, 90 bytes of scratch) and the text. They live in one source file per profile, not behind `#if`s in
one `main.c`.

**Per-port panel width.** `PORT_LCD_W` is defined in each port's `display.h` (240 on the Pico, 320 on the ESP32) and
is the one width `profile_colour.c` uses: the band array (`static uint8_t band[PORT_LCD_W * LINE_H * 2]`), the
target width and the stride (`2 * PORT_LCD_W`). The panel height is 240 on both (`PORT_LCD_H`). The byte order of a
pixel is the colour driver's: `extern const uint8_t display_565_bigendian;` (1 in `disp_st7789.c` and
`disp_ili9341.c`, 0 in `disp_esp_rgb.c`), and `profile_colour.c` sets `SVF_TF_565_BIGENDIAN` from it, so a band is
always in the bytes the panel takes and no driver swaps.

**Default.** Each port's default profile is what it does today: Pico `mono`, ESP32 `colour` (`SVF_DISPLAY=ili9341`).
The existing READMEs, sizes and bench rows stay true of the defaults.

**How a user picks one.**

    cmake -S c/ports/pico -B build-pico -DSVF_PROFILE=colour -DPICO_SDK_PATH=$HOME/opt/pico-sdk-2.3.1 && cmake --build build-pico
                                                                         # build-pico/svf_pico_colour.elf (.uf2 with picotool, below)
    # c/ports/pico/CMakeLists.txt takes PICO_SDK_PATH as a cache variable and falls back to the environment variable
    # (today it reads $ENV{PICO_SDK_PATH} only, so -D alone would not work):
    #   if(NOT DEFINED PICO_SDK_PATH AND DEFINED ENV{PICO_SDK_PATH}) set(PICO_SDK_PATH $ENV{PICO_SDK_PATH}) endif()
    cd c/ports/esp32 && idf.py -DSVF_PROFILE=grey set-target esp32c3 build flash monitor      # or set-target esp32s3
    cd c/ports/esp32 && idf.py -DSVF_PROFILE=colour -DSVF_DISPLAY=esp_rgb set-target esp32c3 build   # for QEMU

`SVF_PROFILE` (and `SVF_DISPLAY`) are CMake cache variables in both ports (`idf.py -D` passes them through to
CMake). An unknown value is a configure error listing the choices. Switching profiles in an existing build directory
needs `idf.py fullclean` / a fresh `-B` directory (the cache keeps the old value); the READMEs say so. The output
name carries the profile (`svf_pico_<profile>.elf`, `svf_esp32_<profile>.elf`), so the three can sit side by side.

**One table, read by every build.** The mapping profile -> kind, `SVF_TARGETS` bit, faces, driver and bus is written
once, in `c/ports/profiles.txt`:

    # profile  kind       targets  faces (under svf/)                driver_pico  driver_esp32  bus_pico  bus_esp32
    colour     RGB565     0x08     dos/PAPLG16.SVF,dos/PAPLG18.SVF    st7789       ili9341       spi       spi
    grey       GRAY8      0x01     dos/PAPLG16.SVF,dos/PAPLG18.SVF    ssd1327      ssd1327       i2c       spi
    mono       MONO_PAGE  0x02     iolo/HGKEY6J.SVF                   ssd1306      ssd1306       i2c       spi

`c/ports/profiles.cmake` parses it (`file(STRINGS)` + a regex) into `SVF_KIND`, `SVF_TARGETS_BIT`, `SVF_FACES`,
`SVF_DRIVER`, `SVF_BUS` for a given `SVF_PROFILE` and port; both `CMakeLists.txt` include it, and `build-all.sh
--ports` runs the same file in script mode (`cmake -DSVF_PROFILE=<p> -DSVF_PORT=<port> -P c/ports/profiles.cmake`
prints the row) and compares it with its own awk reading of `profiles.txt`, so the CMake parse is exercised on every
run even where the SDK build is not. From the row a build derives: `-DSVF_NO_SCALE -DSVF_TARGETS=<targets>`
(library and example alike), the `mkface.py` rules for the faces (array names `paplg16`/`paplg18`, or `svf_face_data`
for the one-face profile, as today; `-DSVF_FACE_ASCII=`/`-DSVF_FACE_HANGUL=`/`-DSVF_FACE=` override the paths),
the sources `main.c profile_<profile>.c disp_<driver>.c` plus the generated face files, and the bus library (Pico:
`hardware_spi` or `hardware_i2c`). Each driver defines `const char svf_port_driver_<driver>[]` and each profile
`const char svf_port_profile_<profile>[]` (unique symbol names, so `nm` can look for them); `build-all.sh --ports`
checks that the linked image holds exactly the row's two symbols and that `SVF_TARGETS` on its compile line is the
row's.

**ESP-IDF specifics.** ESP-IDF evaluates component `CMakeLists.txt` files first in script mode
(`CMAKE_BUILD_EARLY_EXPANSION`), where a `-D` cache value may be unset. So `SVF_PROFILE` and `SVF_DISPLAY` are
declared, defaulted and validated in the top-level `c/ports/esp32/CMakeLists.txt` before
`project(svf_esp32_${SVF_PROFILE})`; `main/CMakeLists.txt` only selects sources, generated faces and definitions,
inside `if(NOT CMAKE_BUILD_EARLY_EXPANSION)` where it matters. The chip comes from `IDF_TARGET` (`esp32c3` or
`esp32s3`); `main/CMakeLists.txt` turns it into `-DSVF_ESP32S3=1` for the S3 (the stub and QEMU builds pass the same
define), which the drivers use for the S3's pin numbers. `max_transfer_sz` of the SPI bus is the profile's largest
send: the band (15,360), the SSD1327 chunk (256), the page frame (1,024).

**Source layout per port** (Pico; the ESP32 mirrors it under `main/`):

    c/ports/profiles.txt       the table above; c/ports/profiles.cmake parses it (both ports, build-all.sh)
    c/ports/grey_pack.h        static inline grey_pack_rows(): GRAY8 rows -> SSD1327 bytes (both ssd1327 drivers, the host check)
    c/ports/FACES.md           the faces' provenance and licences ("Faces and licences" below), copied beside every image
    c/ports/pico/
      CMakeLists.txt           SVF_PROFILE -> profiles.cmake -> defines, faces, sources, bus library, licence copies
      main.c                   stdio/clock init the SDK wants, display_init(), profile_run(), then svf_port_idle(): a
                               separate, non-inlined function (its own symbol, looked up with nm by the screen runner)
                               that loops on sleep_ms(1000) for ever; nothing profile-specific. No BKPT anywhere: it
                               faults on hardware without a debugger
      profile.h                void profile_run(void);  void svf_port_idle(void);
      display.h                PORT_LCD_W 240, PORT_LCD_H 240, OLED sizes, and the driver interface every profile uses:
                                 void display_init(void);
                                 void display_show(const uint8_t *buf, int16_t y, int16_t rows);
                                 extern const uint8_t display_565_bigendian;   /* colour drivers */
                               buf is rows rows of the profile's draw format (RGB565 pairs in the driver's order, GRAY8
                               bytes, or MONO_PAGE pages: rows a multiple of 8), shown at panel row y
      profile_colour.c         paplg16/paplg18 externs, the wide text set, static band[PORT_LCD_W * 24 * 2], the band loop
      profile_grey.c           paplg16/paplg18 externs, the 128 px 2 bpp text set, static frame[128 * 128], the frame loop
      profile_mono.c           svf_face_data extern, the 128 px 1 bpp text set, static frame[128 * 64 / 8], the frame loop
      disp_st7789.c            SPI0: MOSI GP19 and SCK GP18 on GPIO_FUNC_SPI; CS GP17, DC GP16, RST GP20 are SIO outputs
                               (gpio_init + gpio_set_dir + gpio_put; the panel model reads them as gpio[n].value) (*my call*);
                               init SWRESET 0x01, SLPOUT 0x11, COLMOD 0x3A 0x55, MADCTL 0x36 0x00, INVON 0x21 (the usual IPS
                               modules), DISPON 0x29; CASET 0x2A / RASET 0x2B / RAMWR 0x2C a band, CS low for the
                               transaction, DC low for a command byte and high for its parameters and the pixels
      disp_ssd1327.c           I2C0 SDA GP4, SCL GP5 (the mono example's pins), address 0x3C; init 0xAE, 0xA0 0x51, 0xA8 0x7F,
                               0xA1 0x00, 0xA2 0x00, 0x81 0x7F, 0xB1 0xF1, 0xBC 0x08, 0xA4, 0xAF; window 0x15 0 63, 0x75 0 127;
                               display_show packs 4 GRAY8 rows at a time (grey_pack_rows) into bytes 1..256 of a static
                               257-byte chunk buffer whose byte 0 is 0x40, and sends 32 chunks, each ONE
                               i2c_write_blocking(i2c0, 0x3C, chunk, 257, false) (8,192 panel bytes a frame)
      disp_ssd1306.c           today's init and window code; display_show sends the frame as eight page writes from a
                               static 129-byte driver buffer: byte 0 = 0x40, bytes 1..128 = the next 128 bytes of the
                               profile's frame, i2c_write_blocking(i2c0, 0x3C, page, 129, false) each. The render buffer is
                               the profile's 1024 bytes; the driver never writes before or after it. Never a nostop split:
                               with the pico-sdk a nostop write followed by another write puts a repeated START and the
                               address on the bus, and the SSD1306 then reads the first frame byte as a control byte
                               (measured in review under rp2040js with pico-sdk 2.3.1)
      stub/                    today's pico-sdk stand-ins reorganised as the SDK has them: hardware/gpio.h (gpio_init,
                               gpio_set_dir, gpio_put, gpio_set_function, gpio_pull_up), hardware/spi.h (spi_init,
                               spi_set_format, spi_write_blocking), hardware/i2c.h, pico/stdlib.h including hardware/gpio.h;
                               plus the recording mode (SVF_STUB_RECORD, "Host checks" below)
      README.md

The ESP32 `main/` gets `profile_*.c` the same, `disp_ili9341.c` (today's SPI and LCD code moved out of `main.c`),
`disp_ssd1327.c` and `disp_ssd1306.c` over 4-wire SPI (`spi_master`, DC/RST on GPIO: a data phase is bytes with DC
high, there is no 0x40 control byte and no RAMWR on these two controllers), `disp_esp_rgb.c` ("Emulated screens"
below) and `main_qemu.c` (a `main()` that calls `display_init()`, `profile_run()`, prints `screen=ready` and spins,
for the bare QEMU build only), so its `stub/` needs only the recording mode. Pins are `PIN_` defines at the top of
each driver: ESP32-C3 as today (MOSI 7, SCLK 6, CS 10, DC 2, RST 3); ESP32-S3 under `#if SVF_ESP32S3`: MOSI 11,
SCLK 12, CS 10, DC 4, RST 5 (11/12 are the S3's FSPI IOMUX pins; GPIO 26-32 are its flash/PSRAM pins and are
avoided).

**Colours and levels.** `colour`: fg 0xFFE0 on bg 0x0010 as the ESP32 example has (yellow on navy). `grey`: the
GRAY8 frame is cleared to 0 and coverage is brightness (white text on black); a dimmer text is a right shift at pack
time, not a library feature. `mono`: as today (threshold 128).

**The text, per profile** (widths measured 2026-10-20 with `tools/svfline.py measure` and re-measured in review; the
plan re-measures each string before committing it):

| profile | faces, placement | panel | lines (width px) |
|---|---|---|---|
| colour | PAPLG16 + PAPLG18; x 8, band baseline 19, bands at y 16 + 28 i | 240 x 240 or 320 x 240 | board line: "Pico ST7789 RGB565" (178), "ESP32-C3 ILI9341 RGB565" (227), "ESP32-S3 ILI9341 RGB565" (225); then "다람쥐 헌 쳇바퀴에 타고파!" (222), "키스의 고유조건은 입술끼리" (228), "만나야 하고 특별한 기술은" (216), "필요치 않다." (101). 228 + 8 = 236 <= 240 |
| grey | PAPLG16 + PAPLG18; x 4, baselines 17 + 24 i (the fifth line's descent ends at row 117 < 128) | 128 x 128 | "Pico GRAY8" (97) or "ESP32 GRAY8" (116; "ESP32-S3 GRAY8" is 144 and does not fit, so both ESP32 chips show "ESP32 GRAY8"), "다람쥐 헌" (78), "쳇바퀴에" (72), "타고파!" (60), "안녕하세요" (90); 116 + 4 = 120 <= 128 |
| mono | HGKEY6J; x 0 (one line is exactly 128 px), four lines as today | 128 x 64 | "Pico SVF 예제" (104) or "ESP32 SVF 예제" (112), "다람쥐 헌 쳇바퀴" (128), "에 타고파! 1bpp" (120), "안녕하세요" (80) |

These strings, positions and colours are also the input of the screen reference (`c/ports/check/screen_ref.py`),
which reads them from one place: `c/ports/check/screens.py` holds the per-profile text, x, baselines, colours and
threshold as data, and the profile sources carry the same strings (the host profile tests compare the two, so they
cannot drift apart silently).

**Faces and licences.** The images embed font software. `c/ports/FACES.md` carries the table below, every port
README links it, and the CMake files copy it and the licence texts next to the output image (`<build>/licences/`).
The READMEs say that a distributed image must carry those files (the OFL's condition for copies and Modified
Versions). `mkface.py` already names the source file in the generated array's header comment.

| face file | derived from (source, version) | copyright / author | licence | licence file | how it was made |
|---|---|---|---|---|---|
| `svf/dos/PAPLG16.SVF` (ASCII, 2 bpp, 18 px cell, 149 glyphs) | Paperlogy-4Regular.ttf, Paperlogy 4 Regular version 1.000 | Copyright (c) 2024 PT& (www.designptn.com); Paperlogy redesigned by Lee Juim, Hangul glyphs from Gmarket Sans, Latin from Montserrat (the font's name table, quoted in `OFLPAPLG.TXT`) | SIL OFL 1.1, no Reserved Font Name claimed | `svf/dos/OFLPAPLG.TXT` | rasterised at 16 px by `mkfont.py` (`tools/scumm-fonts/bake-paperlogy.sh`, the exact command in `svf/dos/PAPLG.TXT`): a Modified Version under the OFL |
| `svf/dos/PAPLG18.SVF` (2 bpp jamo set, 18 x 18, 24/16/16 piece sets) | the same font, version 1.000 | the same | the same | the same | Paperlogy's syllable outlines separated into initial/medial/final vector pieces, rasterised at 18 px and merged to 24/16/16 sets by `fontbuild2.py` (research run `seg-night/F`; `svf/dos/PAPLG.TXT` records the run, hashes and IoU): a Modified Version under the OFL |
| `svf/iolo/HGKEY6J.SVF` (16 px 1 bpp jamo set, 6x2x1 layout) | HGKEY (청계천한글) `.fnt` of https://github.com/iolo/6x2x1-fonts at commit d2d0bd4bb60d807b14b1fa44459e5d9a1d35b5d1 (an Apple II-era bitmap font; the repository does not name the original font's maker) | Copyright (c) 2025 Dongsu Jang <iolo@kakao.com> (the notice of both licence files of that repository, reproduced in `svf/iolo/`) | SIL OFL 1.1 and MIT, as the repository ships both | `svf/iolo/LICENSE-OFL.txt`, `svf/iolo/LICENSE-MIT.txt` (`svf/iolo/IOLO.TXT`) | built 2026-10-18 by `tools/build/iolo_jset.py` (`jamoset.py --layout 621 --check`) from the original `.fnt` |

A distributed image carries the copyright notices above verbatim (`FACES.md` holds them) together with the licence
texts; that is what the OFL and the MIT licence require of copies.

## The grey profile and GRAY4 later

The SSD1327 (and the SSD1322) hold 4 bits a pixel, two pixels a byte: a 128 x 128 frame is 64 bytes a row and
8,192 bytes. The library has no 4-bit kind; that is card t_8e7da3c1, which comes after the VESA card. Until then the
grey profile draws GRAY8 and the driver converts, through one shared helper:

    /* c/ports/grey_pack.h: rows GRAY8 rows of w pixels (stride bytes apart) to w / 2 bytes a row at out, the left pixel
     * in the high nibble: the order the SSD1327 shows with remap 0xA0 = 0x51 (bit 0, column address remap, set; bit 1,
     * the nibble remap, clear; bit 4 the COM remap, bit 6 the odd/even split), the same convention as Adafruit's
     * SSD1327 code. Level = coverage >> 4: 2 bpp coverage 0/85/170/255 lands on 0/5/10/15.
     * Returns the bytes written, rows * w / 2; 0 and writes nothing unless w is even and >= 2, stride >= w and
     * rows >= 0 (no byte outside gray8[0 .. (rows - 1) * stride + w) is read). */
    static inline size_t grey_pack_rows(const uint8_t *gray8, size_t stride, int w, int rows, uint8_t *out)
    {
        int r, x;
        if (!gray8 || !out || w < 2 || (w & 1) || stride < (size_t)w || rows < 0)
            return 0;
        for (r = 0; r < rows; ++r, gray8 += stride)
            for (x = 0; x < w; x += 2)
                *out++ = (uint8_t)((gray8[x] & 0xF0) | (gray8[x + 1] >> 4));
        return (size_t)rows * (size_t)(w / 2);
    }

`disp_ssd1327.c` (both ports) calls it for 4 rows at a time into a 256-byte chunk (32 chunks a frame) between the
window commands and the data writes, and treats a 0 return as "nothing to send" (the frame stays as it was).
Designed so GRAY4 slots in without restructuring:

- The grey profile's kind and buffer size come from one CMake cache variable `SVF_GREY_KIND` (default `GRAY8`), from
  which the CMake derives the `SVF_TARGETS` bit and a `-DSVF_GREY_KIND_<K>=1` define (a C `#if` cannot compare enum
  constants: selection macros are `SVF_TARGETS` bits or these defines, never `SVF_T_*` names). When `SVF_T_GRAY4`
  exists, `-DSVF_GREY_KIND=GRAY4` halves the frame to 8 KB, `profile_grey.c` initialises that kind, and
  `disp_ssd1327.c` sends the frame's rows as they are instead of packing: the `grey_pack_rows` call and the helper
  are the only lines replaced. The GRAY4 card owns the conversion rule (`>> 4` is the example's choice, not a
  contract; the card may round differently and will want a nibble-order flag like `SVF_TF_565_BIGENDIAN`) and the
  SSD1322 (256 x 64, SPI) example if it wants one.
- The bench names its grey rows by the kind (`GRAY8` in the build column, below), so GRAY4 rows are added next to
  them with the same case names, not instead of them. The size table row is keyed by profile and kind (`grey, GRAY8`).
  The SSD1327 panel model and the screen reference compare the panel's 4-bit bytes, which is what a GRAY4 build must
  produce too.

## Emulated screens: the real binaries on virtual panels

### Pico: rp2040js with panel models on the emulated I2C and SPI

**The binaries are the pico-sdk builds** of the three profiles (`cmake -S c/ports/pico -B ... -DSVF_PROFILE=<p>`),
so the SDK's own I2C and SPI drivers program the RP2040's peripherals, which rp2040js emulates (`RPI2C` at
0x40044000, `RPSPI` at 0x4003c000, the GPIO pins). This needs the pico-sdk on the host: `install-toolchains.sh`
clones https://github.com/raspberrypi/pico-sdk.git at tag `2.3.1` (commit `079c6f39023649b154152db30f1d781e884879bc`,
checked before anything in the clone runs, as emsdk's commit is; no submodule: tinyusb, cyw43, lwip, mbedtls and
btstack are not used) into `~/opt/pico-sdk-2.3.1`; `cmake` 3.28.3 is on the host; the compiler is the installed Arm
toolchain (`PICO_TOOLCHAIN_PATH=$OPT/arm-gnu-toolchain-15.2.rel1`). The build is configured with
`-DPICO_NO_PICOTOOL=1`: the SDK then produces the `.elf` and no `.uf2` (SDK 2.x makes UF2s with picotool, which its
CMake would otherwise fetch from git at configure time; the README gives the picotool line for a user who wants the
`.uf2`). Verified in review (2026-10-20): a no-submodule clone of 2.3.1 configures offline with `PICO_NO_PICOTOOL`,
builds with the Arm 15.2 toolchain, and the ELF boots under rp2040js from `PC = 0x10000000` after `loadBootrom`
(the boot ROM's vector gives SP 0x20041F00; boot2 vectors into flash). rp2040js's own CI runs pico-sdk images too
(`ci-pico-sdk.yml` at v1.4.0: `hello_usb.uf2` under `npm run start:micropython`, SDK 1.2.0 to 2.1.1).

**The boot ROM file.** The npm package does not ship the RP2040 boot ROM; rp2040js's repository does, as a
TypeScript array (`demo/bootrom.ts` at tag v1.4.0, commit `0c1c316e87b34e616985af35d4c147fc19cfeee9`, 50,364 bytes,
sha256 `99f8a1f813ce3aa9415884de3fb6c5b962d3c6fa0394b05413ad3c7b3c39ec62`, re-measured for this revision; its header:
"built from raspberrypi/pico-bootrom revision B1 00a4a19114195e20fb817bdfbca1165e157eef37"). `install-emulators.sh`
fetches that file from
https://raw.githubusercontent.com/wokwi/rp2040js/v1.4.0/demo/bootrom.ts into `~/opt/dl/rp2040js/bootrom.ts`, checks
the sha256 above, parses the 4,096 `0x...` words of the array in order (a regex over the file; the count must be
4,096) and writes them little-endian as the 16,384-byte binary `~/opt/rp2040js-1.4.0/bootrom-b1.bin`, whose sha256
the plan records in the script at first generation and the script checks on every later run. That `.bin` is the one
canonical location; nothing is copied under `c/build/` and no `.ts` or `.mjs` module holds the ROM. The runner reads
the `.bin` into a `Uint32Array` (little-endian) for `mcu.loadBootrom`.

**The runner, `c/ports/check/pico-screen.mjs RP2040JS_DIR BOOTROM_BIN NM ELF PROFILE SHOWS OUT`** (a sibling of
`c/bench/pico-run.mjs`, but not a copy of its loader):

1. `const mcu = new RP2040(); const clock = mcu.clock;` (the constructor makes its own `SimulationClock`; the
   class is not exported from the package root and the package's `exports` map refuses the deep path, measured in
   review; `RP2040JS_DIR` is used for the absolute-path `require` of the package as `pico-run.mjs` does), then
   `mcu.loadBootrom(words)` **first**: loading the ROM resets the chip and fills flash with 0xFF, so it must precede
   the flash copy. Then `mcu.onBreak = (code) => fail('BKPT #' + code + ' at ' + PC)`: under the pico-sdk a
   HardFault (`isr_hardfault` in `crt0.S`), `panic()` and `_exit()` all end in a BKPT, and rp2040js's default
   `onBreak` does nothing, so without this a faulting image would spin on the BKPT until the time limit. The two
   rp2040js warnings the SDK's I2C init provokes (`IC_DMA_CR`, `IC_SDA_HOLD`, logged through `mcu.logger.warn`) are
   recorded in the `.log` and are not failures.
2. Copies every `PT_LOAD` segment with `filesz > 0` to its **physical address `p_paddr`** (into flash at
   0x10000000... or SRAM), not `p_vaddr` as `pico-run.mjs` does: an SDK ELF's `.data` has its load image in flash
   (2.3.1 probe: VMA 0x200000C0, LMA 0x10001ADC) and crt0 copies it out; loading by VMA was measured to run off the
   end of SRAM and crash the process, loading by LMA boots. `.bss` is SRAM's zero fill.
3. `mcu.core.PC = 0x10000000` (boot2 at the start of flash, as rp2040js's demo does); attaches the panel model the
   profile names; resolves the address of `svf_port_idle` from `nm ELF` (the first instruction's address, bit 0
   cleared) and the expected **show count** from `screens.py` (`SHOWS`: 15 for colour, 1 for grey, 1 for mono; a
   show is one `display_show`: one RAMWR window, or the 8 page writes / 32 chunk writes that fill an OLED window
   once, as the panel models count them; the data-transfer counts, 15 / 8 / 32, are logged but not asserted).
4. Runs rp2040js's own clocked loop (`Simulator.execute` in `dist/cjs/simulator.js`), reproduced inline:
   `if (mcu.core.waiting) clock.tick(clock.nanosToNextAlarm); else clock.tick(mcu.core.executeInstruction() * 8)`
   (8 ns a cycle at 125 MHz). `mcu.step()` alone never advances the timer, so the SDK's `sleep_ms` (SLPOUT 120 ms,
   the reset pulses, the idle loop) would hang: measured in review, a `sleep_ms(120)` probe ran 2 x 10^9 cycles under
   `step()` and finished in 20,920 cycles with the tick loop. Waiting adds clock time, not `core.cycles`.
5. **Completion is deterministic**: the loop stops when `core.PC` equals the address of `svf_port_idle`. Every
   driver write is a blocking SDK call that returns after the bytes are on the bus, so when `profile_run` has
   returned and `main` enters `svf_port_idle`, the panel holds everything the firmware sent; there is no frame
   heuristic, no quiet window and no race with the capture (the ST7789 has no frame notion of its own, and the
   colour profile's 15 RAMWR windows all precede the idle call). The runner then checks that the panel's **show
   count** equals `SHOWS` (a profile that skipped a band fails here, not in the byte compare). Failure exits, each
   a message naming the cause: `onBreak` (a fault, panic or `_exit`); `clock.nanos` above 10 s of emulated time
   (the SDK start-up, the reset pulses, 120 ms after `SWRESET` and 120 ms after `SLPOUT` take about 242 ms on the ST7789, the OLEDs sleep only in their reset pulses; rp2040js's I2C and SPI transfers take
   no emulated time, so a frame costs instructions only: the review's 1,300-byte probe reached the idle symbol after
   84,033 cycles and 120.66 ms); and `core.waiting && clock.nanosToNextAlarm === 0` (the core sleeps with no alarm
   set: `nanosToNextAlarm` is then 0 and the tick loop would spin for ever without advancing the clock), plus a
   host-side bound of 10^9 loop iterations as the last resort.
6. Writes `OUT/pico-<profile>.fb` (the panel memory, raw), `OUT/pico-<profile>.png`, and `OUT/pico-<profile>.log`
   (every command and transfer the panel saw, one line each, with the clock time).

**The panel models, `c/ports/check/panels.mjs`**, hang on rp2040js's hooks (names and semantics confirmed in review
against `dist/cjs/peripherals/i2c.js` and `spi.js`; all of them may complete synchronously):

- `Ssd1306I2C(mcu.i2c[0], 0x3C)` and `Ssd1327I2C(mcu.i2c[0], 0x3C)`: `onStart(repeated)` -> `completeStart()`;
  `onConnect(address, mode)` -> `completeConnect(address === 0x3C && mode === I2CMode.Write)` **and the control-byte
  framing restarts here**, on every address phase, including a repeated START (`onStart(true)`), exactly as the
  controller does: the next byte is a control byte; `onWriteByte(b)` -> feed, `completeWrite(true)`; `onStop()` ->
  `completeStop()`. Framing: the first byte after an address is the control byte; 0x00 means every following byte
  until the next address is a command byte, 0x40 means data, 0x80/0xC0 (Co set) means one command or data byte then
  another control byte. A driver that split the control byte from its data with a `nostop` write would therefore show
  as a diff, as on hardware. SSD1306: 0x20 mode, 0x21 c0 c1, 0x22 p0 p1, data in horizontal addressing into a
  1,024-byte page memory (page = y >> 3, bit = y & 7: the MONO_PAGE layout), other commands logged; each data write
  counts as one transfer, and the 8 page writes of one `display_show` count as one show (the model counts a show when
  the address counter wraps back to the window start). SSD1327: 0x15 c0 c1 (columns of two pixels), 0x75 r0 r1,
  data into 8,192 bytes (64 a row), the remap byte logged (the model does not mirror; the reference is in the panel's
  native order and the remap only affects the scan, which the model does not render); a show = the 32 chunks that
  fill the window once.
- `St7789Spi(mcu.spi[0], { dc: 16, cs: 17 })`: `onTransmit(v)` -> feed `v` if `mcu.gpio[17].value === GPIOPinState.Low`
  with `mcu.gpio[16].value` as DC (SIO outputs, readable this way: confirmed in review), `completeTransmit(0)`.
  0x2A/0x2B take four parameter bytes (big-endian halves), 0x2C starts pixel data into a 240 x 240 x 2 memory in the
  window with wrap at the window's end, bytes stored as received (big-endian RGB565: the panel's format); each 0x2C
  is one show; 0x36, 0x3A, 0x21, 0x11, 0x29 logged.

The models are small (each under 150 lines), decode only what the drivers send plus the commands above, and log any
other command rather than failing, so a datasheet mistake shows as a diff, not as a crash.

**The reference, `c/ports/check/screen_ref.py BOARD PROFILE OUT`** with `BOARD` one of `pico`, `esp32c3`, `esp32s3`
(the board line differs per chip and the colour byte order per driver), builds the expected panel memory with
`tools/svfline.py` from `screens.py`: mono, one `draw_target` on a 128 x 64 `mono-page` target of the four lines'
placements (1,024 bytes); grey, one `draw_target` on a 128 x 128 `gray8` target of the five lines, then the same
`>> 4` nibble packing in Python (8,192 bytes); colour, a `PORT_LCD_W` x 240 RGB565 buffer, big-endian for the Pico's
ST7789 and little-endian for `esp_rgb`, filled with bg, into which each of the five lines is drawn through a 24-row
`rgb565` band target prefilled with bg at (8, 19) and placed at y = 16 + 28 i. File names are one scheme everywhere:
`OUT/<board>-<profile>.fb` (from the runners), `.ref`, `-ref.png`, `-diff.png`, `.png`, `.log`, and for QEMU
`.ppm`. It compares `.fb` with `.ref` byte for byte and on a difference prints the first differing offset (as x, y)
and writes the diff PNG. Bit-identical panel memory is the pass; nothing else is.

**PNGs** are written with Pillow (10.2.0 on this host), mono and grey as 8-bit greyscale images (SSD1306 bits and
SSD1327 nibbles expanded), colour with the 5/6/5 bits replicated into 8 (the rule QEMU uses, below). They are
artifacts (`c/build/screens/`), not compared.

### ESP32-C3 and ESP32-S3: QEMU's `esp_rgb` panel

**The device** (Espressif QEMU 9.2.2, `hw/display/esp_rgb.c`, present on both the `esp32c3` and the `esp32s3`
machine; checked with `info mtree` and a probe on 2026-10-20): a register block at **0x21000000** (28 bytes) and a
VRAM region at **0x20000000** (0x1D4C00 bytes = 800 x 600 x 4), both in the CPU's address space. Registers, 32-bit
accesses only (other sizes are ignored):

| offset | name | meaning |
|---:|---|---|
| 0x00 | `RGB_VERSION` | read: major << 16 \| minor (reads 0x00000002: 0.2) |
| 0x04 | `RGB_WIN_SIZE` | width << 16 \| height; write resizes the window (clamped to 10..800 x 10..600) |
| 0x08 | `RGB_UPDATE_FROM` | x << 16 \| y of the area to copy on the next update |
| 0x0C | `RGB_UPDATE_TO` | x << 16 \| y, exclusive |
| 0x10 | `RGB_UPDATE_CONTENT` | guest address of the pixels (in the VRAM region or internal RAM), row-major, (to.x - from.x) pixels a row |
| 0x14 | `RGB_UPDATE_STATUS` | bit 0 ENA: copy the area on the next window update; cleared by the device after the copy |
| 0x18 | `RGB_BPP_VALUE` | 16 (`r5g6b5`, native little-endian 16-bit words) or 32 (`x8r8g8b8`) |

The copy happens in the device's update callback, which runs on a display refresh or on `screendump`
(`graphic_hw_update`). Under `-display none` there is no refresh, so the copy happens at `screendump` only, and
`RGB_UPDATE_STATUS` stays 1 until then: **the driver must not poll it** (ESP-IDF's `esp_lcd_qemu_rgb` does, and
would hang here).

**The driver, `disp_esp_rgb.c`** (plain MMIO, no SDK call, so it serves the IDF build on QEMU and the bare build
alike): `display_init` writes 16 to `RGB_BPP_VALUE` and `320 << 16 | 240` to `RGB_WIN_SIZE`; `display_show(buf, y,
rows)` copies `rows * 320 * 2` bytes to `ESP_RGB_VRAM + y * 640` (the band is little-endian: `display_565_bigendian`
is 0 here) and then programs the whole window, `FROM = 0`, `TO = 320 << 16 | 240`, `CONTENT = ESP_RGB_VRAM`,
`STATUS = 1`, so whenever the update runs the surface shows all of VRAM, not the last band. Nothing is read back.
The driver keeps two notions apart so that it compiles under `-Werror` on the 32-bit chips and on a 64-bit host
alike: **where it writes** and **what it tells the device**. `ESP_RGB_REGS` and `ESP_RGB_VRAM` are pointer-valued
macros, defaulting to `((volatile uint32_t *)(uintptr_t)0x21000000u)` and `((uint8_t *)(uintptr_t)0x20000000u)`,
and every store goes through those pointers; the value written to `RGB_UPDATE_CONTENT` is a separate `uint32_t`
macro `ESP_RGB_VRAM_ADDR` (default `0x20000000u`), never a pointer cast to 32 bits. The host driver test overrides
the two pointer macros with the addresses of its arrays (the VRAM one 153,600 bytes, the register one seven words)
and leaves `ESP_RGB_VRAM_ADDR` at its default, so it asserts the device sees 0x20000000 while the bytes land in host
memory, with no pointer-to-integer conversion anywhere.

**The build run here is bare** (ESP-IDF is not installed): `main_qemu.c` + `profile_colour.c` + `disp_esp_rgb.c` +
the library + the two face arrays, linked with the toolchains' QEMU runtimes exactly as the bench is ("The ESP32
benches" below: `esp32c3.qemu.specs`; `sys.qemu.specs` + `sim.elf.specs` + `entire_dram_seg`). `main_qemu.c` calls
`display_init`, `profile_run`, prints `screen=ready\n` on the semihosting console and spins. The IDF image on QEMU is
not run here (it would need `idf.py`); the README says so.

**The runner, `c/ports/check/esp-screen.py QEMU ELF BOARD OUT`** (`BOARD` `esp32c3` or `esp32s3`), starts

    $QEMU -M <esp32c3|esp32s3> -display none -nographic -serial none -semihosting -qmp unix:OUT/qmp.sock,server,nowait -icount shift=0,sleep=off -kernel ELF

after unlinking a stale `OUT/qmp.sock` (a previous interrupted run leaves one, and QEMU then fails to bind), then
reads the guest's stdout line by line with a 30 s timeout, stripping whitespace (CR included) and ignoring empty
lines and the known start-up lines a runtime may print before the guest's own output (a list in the script, today
empty: with `-qmp` the default monitor is off and stdout carried only the guest's lines in review); it succeeds on
`screen=ready`, and on timeout, on QEMU exiting first or on any other non-empty line it kills QEMU and fails with the
output seen. It connects to the QMP socket (JSON, no terminal echo),
sends `qmp_capabilities`, `screendump` (`filename=OUT/<board>-colour.ppm`), `pmemsave` (`val=0x20000000,
size=153600, filename=OUT/<board>-colour.fb`), `quit`, each with a 10 s reply timeout. `screendump` triggers the
device update, so it comes first; the PPM is the 320 x 240 surface, 8 bits a channel with each 5/6/5 channel
replicated into 8 (`r << 3 | r >> 2`: a probe wrote 0x0010 and read back 0, 0, 132). QEMU has no PNG output in this
build ("Enable PNG support with libpng"), so the runner converts the PPM to `OUT/<board>-colour.png` with Pillow.
`screen_ref.py <board> colour OUT` compares the VRAM dump byte for byte with the little-endian reference (153,600
bytes, the board line of that chip) and, as a second check, the PPM with the replicated reference. The whole
sequence was run on both machines on 2026-10-20 with a pattern-filling guest: the VRAM dump was exact, `pmemsave`
and `memsave` gave the same bytes, and QEMU exited 0; the register block was spot-checked in review (`xp /7wx
0x21000000` at reset: version 0.2, 800 x 600, BPP 32).

Only the colour profile has a QEMU panel; the grey and mono ESP32 drivers (SPI OLEDs) have no QEMU model and are
covered by the recording-stub checks only.

### `c/ports/check/run-screens.sh [OUT]`

Builds the three Pico profiles with the pico-sdk (`cmake` + `make`, the SDK and toolchain paths from `OPT`), runs
`pico-screen.mjs` and `screen_ref.py pico <profile> OUT` for each; builds the two bare ESP32 colour images (C3, S3),
runs `esp-screen.py` and `screen_ref.py <board> colour OUT` for each; prints `screen-pico-<profile>: OK` x 3 and
`screen-<board>-colour: OK` x 2 (five lines), exit 1 on any difference or a run that does not finish. `build-all.sh --ports` calls it after the
host checks when the pico-sdk and QEMU are installed, and prints `screens: skipped (<what is missing>)` otherwise;
the card's close needs them run. Artifacts (`.fb`, `.ref`, `.ppm`, `.png`, `.log`) stay under `OUT` (default
`c/build/screens`), never in the repository.

## What is verified on the host and what is only built

No Pico, ESP32 or display is at hand (as for every port so far). The split, per profile and board, goes into each
README's "What was checked":

| | verified here | only built, written to the documented API |
|---|---|---|
| library paths the profiles use (RGB565, GRAY8, MONO_PAGE at 1 and 2 bpp, clipping, byte order, threshold) | `tools/test_c_renderer.py` `TestTargets` against `tools/svfline.py` (byte identity), in `make -C c check`; the bench checksums equal the `svfline` reference for every kind on the Pico, the C3 and the S3 | - |
| the SVF side of each profile (faces open, chain, scratch size, target init, the lines fit the panel, the draw calls) | compiles and links for Cortex-M0+, RV32IMC and Xtensa LX7 in `build-all.sh --ports` with `-Werror`; the host profile tests draw every profile's screen on the host and compare it with `svfline`; each text line measured on the host against its panel width | - |
| the drivers' command streams: init bytes, window coordinates, data phase, byte counts, DC levels, I2C control bytes | `c/ports/check/test_drivers.c` on the host against recording stubs | - |
| the profiles' show sequences (which rows, how many times, with what bytes) | `c/ports/check/test_profiles.c` on the host (the real `profile_<p>.c`, a recording `display_show`) | - |
| `grey_pack_rows` | `c/ports/check/test_grey_pack.c` (patterns, the refused calls, under ASan) | - |
| **the Pico firmware end to end**: the pico-sdk build of each profile, the SDK's I2C/SPI drivers, the example's driver code and the pixels on the panel | `run-screens.sh`: the real `svf_pico_<profile>.elf` under rp2040js on the virtual SSD1306 / SSD1327 / ST7789; panel memory identical to `svfline` | timing, voltages, panel variants, pin mapping, the controllers' undecoded commands (logged, not modelled), the `.uf2` step (picotool) |
| **the ESP32 colour drawing end to end** on QEMU's panel (C3 and S3) | `run-screens.sh`: the bare build of `profile_colour.c` + `disp_esp_rgb.c` on `-M esp32c3` / `-M esp32s3`; VRAM identical to `svfline`; PNG from `screendump` | the ESP-IDF build itself (`idf.py` absent): the IDF CMake files are read, not run; the ILI9341/SSD13xx SPI paths on real panels |
| electrical and timing behaviour, SPI mode and clock, panel variants (ST7789 inversion and 80-row offset in portrait, BGR order, SSD1327 remap) | - | written to the datasheets; the one byte to change per variant named in the README |

### Host checks (`build-all.sh --ports` runs them with the host compiler)

- **Recording stubs.** The stub headers of both ports gain `#ifdef SVF_STUB_RECORD` branches: `i2c_write_blocking`,
  `spi_write_blocking`, `spi_device_polling_transmit`, `gpio_put`/`gpio_set_level` (the DC, CS and RST pins) call
  `svf_rec_bytes(int dc, const uint8_t *p, size_t n)`, `svf_rec_gpio(int pin, int level)`,
  `svf_rec_i2c(uint8_t addr, const uint8_t *p, size_t n, int nostop)` into a log the test owns. Without the define
  they stay the no-ops they are. The drivers are plain C99 against those headers, so each `disp_*.c` compiles on the
  host unchanged.
- **`c/ports/check/test_drivers.c`** links one driver at a time (seven runs: three Pico drivers, three ESP32 SPI
  drivers, `disp_esp_rgb.c` against a fake VRAM array) and asserts, from tables written out of the datasheets in the
  test itself: the init sequence byte for byte with its DC levels (and, over I2C, the address, the 0x00 control byte
  a command, and **no `nostop` write anywhere**: every I2C write is a whole transaction); for `display_show(buf, y,
  rows)` with a counting pattern: the window commands with the coordinates derived from `y` and `rows`
  (ST7789/ILI9341 CASET/RASET as big-endian halves; SSD1327 0x15/0x75; SSD1306 0x21/0x22), the data phase
  (ST7789/ILI9341: 0x2C with DC low then the bytes with DC high; I2C SSD1306: eight writes of 129 bytes, each 0x40
  then 128 frame bytes in order; I2C SSD1327: 32 writes of 257 bytes, each 0x40 then 256 packed bytes; SPI OLEDs:
  bytes with DC high and no prefix; `esp_rgb`: the VRAM bytes and the four register writes of a show (FROM, TO, CONTENT, STATUS; init writes BPP and WIN_SIZE)), the data byte count
  (`PORT_LCD_W * rows * 2`; 8 x 128 or 32 x 256 payload bytes; 1,024) and the bytes themselves (the buffer;
  `grey_pack_rows` of it; the buffer). It prints `port-check-driver-<port>-<driver>: OK` a run.
- **`c/ports/check/test_profiles.c`** links one real `profile_<p>.c` with the library, its generated faces and a
  recording `display_show` (no driver), calls `profile_run()`, and asserts the show sequence: colour, ten shows at
  y = 24 i with 24 rows (rows 0..239 once, all bytes bg), then five shows at y = 16 + 28 i with 24 rows, each byte
  identical to the `svfline` band of that line (so this is also the host screen check of the colour drawing, for
  `PORT_LCD_W` 240 and 320: the test is run once per port's `display.h`, and for the ESP32 colour profile twice, with
  `display_565_bigendian` 1 (ILI9341) and 0 (`esp_rgb`), the reference in the matching order); grey, one show
  (0, 128) whose 16,384 bytes
  equal the `svfline` frame; mono, one show (0, 64) whose 1,024 bytes equal the `svfline` page frame. The strings
  the profile drew are compared with `screens.py`. Prints `port-check-profile-<port>-<profile>: OK` (seven runs:
  the ESP32 colour profile twice).
- **`c/ports/check/test_grey_pack.c`** (built with `-fsanitize=address,undefined`): a 4 x 4 and a 6 x 3 pattern at
  strides equal to and larger than `w` against hand-written bytes; `w` odd, `w` 0, `stride < w`, `rows` 0 and
  `rows < 0` return 0 and write nothing; a buffer of exactly `(rows - 1) * stride + w` bytes is not over-read
  (ASan would say). `port-check-grey-pack: OK`.

## `build-all.sh --ports` and the size table

`port pico PROFILE`, `port esp32c3 PROFILE` and `port esp32s3 PROFILE` are called three times each from the rows of
`profiles.txt`, so the run prints, in order, `port-dos`, `port-web`, nine `port-<board>-<profile>` lines,
`port-arduino` (twelve `port-*: OK` lines), then `port-check-grey-pack: OK`, seven `port-check-driver-*: OK`, seven
`port-check-profile-*: OK`, and the five `screen-*: OK` lines of `run-screens.sh` (or one `screens: skipped` line):
32 `OK` lines when everything is installed; any failure fails the run (exit 1) as now. The S3 stub build uses
`$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc` with `-mlongcalls -Os` (the
compiler's default `-mdynconfig=xtensa_esp32s3.so` selects the S3 core; `-mlongcalls` is what ESP-IDF compiles
with) and `-DSVF_ESP32S3=1`.

`c/cross/SIZES.md` gets a "Port examples" table replacing the prose figures in "Findings":

| port | profile | kind, `SVF_TARGETS` | faces (bytes) | text | data | bss | text without faces |
|---|---|---|---:|---:|---:|---:|---:|
| pico | colour | RGB565 0x08 | 139,457 | | | | |
| pico | grey | GRAY8 0x01 | 139,457 | | | | |
| pico | mono | MONO_PAGE 0x02 | 12,921 | 18,793 | 0 | 1,088 | 5,872 |
| esp32c3 | colour | RGB565 0x08 | 139,457 | 146,881 | 0 | 15,572 | 7,424 |
| esp32c3 | grey | GRAY8 0x01 | 139,457 | | | | |
| esp32c3 | mono | MONO_PAGE 0x02 | 12,921 | | | | |
| esp32s3 | colour / grey / mono | | | | | | |
| arduino | - | MONO_PAGE 0x02 | 12,921 | 26,420 | 18 | 1,099 | 13,499 |

(the filled cells are today's numbers, to be re-measured; "text without faces" is the column to read for code; the
stub links, as today, with the pico-sdk links of `run-screens.sh` reported beside them in the Pico README). The
library table gets a toolchain row **esp32s3-xtensa** (`xtensa-esp32s3-elf-gcc 16.1.0`, `-mlongcalls -Os`, linked
like the other bare rows with `--specs=nosys.specs -nostartfiles -Wl,-e,main`; probed in review: it links) and, for
every toolchain, one profile row **P3g: grey OLED**, P3 with `SVF_T_GRAY8` instead of `SVF_T_RGB565`
(`-DSVF_TARGETS=0x01`; `probe.c` `PROFILE=3` takes a kind macro), so the "core plus one output path" number exists
for all three paths the ports use. *My call*; the 8192-byte gate stays on P1/P2 (the P1* question of the last card is
still the user's and is not reopened here) (decided 2026-10-21: the gate stays on P1/P2; P1* 8474 B, 282 over, accepted).

## The Pico bench

### Builds

`run-pico.sh` builds `bench.c` once per (kind, optimisation): `-DBENCH_KIND=SVF_T_MONO_PAGE -DSVF_TARGETS=0x02`,
`-DBENCH_KIND=SVF_T_GRAY8 -DSVF_TARGETS=0x01`, `-DBENCH_KIND=SVF_T_RGB565 -DSVF_TARGETS=0x08`, each at `-Os` and
`-O2`: six runs, each the library as the matching profile builds it. `BENCH_KIND` defaults to `SVF_T_MONO_PAGE`, so
the AVR and the existing host builds are unchanged; it is used in C expressions only (buffer size, `svf_target_init`),
never in `#if`. The MONO_PAGE rows thereby change from the all-kinds build measured on 2026-10-20 to the `0x02`
build (the one the Pico mono profile links); the previous rows stay in the "before" table and the difference, if any,
is reported (the inner loops are the same code; only the dispatch and the link layout differ, and rp2040js does not
model layout).

### Cases

Two face sets, so the colour and grey rows can be read two ways: against the mono rows (same face, same pixels) and
as what the colour/grey examples actually draw (2 bpp, anti-aliased).

**Set A, the 1 bpp face (HGKEY6J, 16 px), 128 x 64, every kind.** The buffer is 1 KB (MONO_PAGE), 8 KB (GRAY8) or
16 KB (RGB565); fg 0xFFFF, bg 0x0000, little-endian pairs, so the clear is `memset` 0 for every kind (and so set A
cannot catch a byte-order fault: 0xFFFF and 0x0000 read the same either way; set B does). Cases: `syl_ga`,
`syl_bwelk`, `compose_bwelk`, `screen32` as today, plus **`line8`**: one line of eight syllables (the screen's first
line, 128 px), the "line" of the card for the mono-sized screen. `line8` is compiled `#if !defined(BENCH_AVR)`:
`run-avr.sh` and the Uno table stay exactly as they are (*my call*: the Uno has no line budget and one profile).

**Set B, the 2 bpp pair (PAPLG16 + PAPLG18), a 240 x 24 band, GRAY8 and RGB565 only**, compiled
`#if !defined(BENCH_AVR) && (SVF_TARGETS & (SVF_TARGET_GRAY8 | SVF_TARGET_RGB565))` (139 KB of faces and an
11.5 KB band do not fit an ATmega328P; a 2 bpp face on a mono target is the threshold path, not an example here:
*my call* to leave it out). Colours as the colour example: fg 0xFFE0, bg 0x0010, `SVF_TF_565_BIGENDIAN`; the band is
filled with the two-byte background in the target's order before each line (GRAY8: cleared to 0).

- `aa_syl_ga`, `aa_syl_bwelk`: one 18 px syllable composed and drawn into the band, the same spot each time.
- `aa_line12`: "다람쥐 헌 쳇바퀴에 타" (12 code points, 180 px; the full pangram would fit 240 too, 12 is a choice
  that keeps the case short), drawn into the filled band at x 8, baseline 19.
- `aa_screen10`: ten times (fill the band, draw the line): a 240 x 240 redraw as the ST7789 example does it, band by
  band. The checksum runs over the ten bands in order (the FNV state carried from band to band).

The GRAY8 rows of set B use the same 240 x 24 geometry as RGB565, not the 128 x 128 panel of the grey example, so
the two kinds' rows differ only in the blit; the grey example's panel is the size table's business, not the bench's.

Iterations as today (`BENCH_SYL_N` 100, `BENCH_SCREEN_N` 20); `aa_screen10` 5. The 139 KB face pair goes into
rp2040js's flash (16 MB modelled: `rp2040.js`, `flash = new Uint8Array(16 * MB)`) with the same `-Ttext=0x10000000`
link; no boot ROM, as today (the bench has no SDK code).

### Checksums

Every target-buffer checksum comes from `tools/svfline.py`, as the three existing line checksums do: a new
`c/bench/sums.py` lays out each case's text on the case's kind, size, colours, byte order and threshold with
`svfline.draw_target`, hashes the buffer (for `aa_screen10` the ten buffers in order) and prints the `SUMS` strings
per kind, which the run scripts embed (regenerated and diffed by the plan, not read at run time). `compose_bwelk`
is different: it hashes the composed cell in the face's packed 1 bpp layout, kind-independent; `sums.py` computes it
from `tools/jamoset.py`'s composition packed the same way (where today's value came from). `bench.c` built
`-DBENCH_HOST -DBENCH_MCU -DBENCH_KIND=...` prints the same checksums on the host, the second check. The four
existing MONO_PAGE values must come out unchanged from `sums.py`; if they do not, the script is wrong.

### How the rows map to the report

`report.awk` is not changed. The kind is part of the build column, since it is a different build of the library:

    | Pico emulated (rp2040js 1.4.0, 125 MHz; gcc 15.2.1 -Os; RGB565, SVF_TARGETS=0x08) | syl_ga | 100 | ... | ... | - | - | <sum> ok |

Case names stay the same across kinds, so a reader lines up `syl_ga` under MONO_PAGE, GRAY8 and RGB565 at the same
flags. Budgets: the MONO_PAGE rows keep `syl_ga:50 syl_bwelk:50 screen32:2000`; the GRAY8 and RGB565 rows get
none (`-` in the budget and result columns, as the Uno rows have): the user's ruling that small LCD and OLED targets
have no speed budget, measured honestly. `run-pico.sh`'s exit status therefore depends on the mono budgets and on
every checksum, as now. `PROFILE=1` works per kind as today and gives `blit_rgb565` / `blit_gray8` their own lines.
`pico-run.mjs` additionally counts instructions (one per `mcu.step()` between the markers) and prints `insns=` and
`per_iter_insns=` on the case line (`report.awk` ignores fields it does not know), so the Pico and the ESP32-C3 rows
can be compared in one unit, instructions, in the findings.

### Pico RGB565 rows for the VESA card (t_6ab9ec2d)

The VESA card may add a 2-pixel word store to the RGB565 1 bpp and 2 bpp paths (today each covered pixel is two
byte stores, `dst[i]`, `dst[i + 1]`, in the target's byte order; the 8 bpp path blends per pixel) on x86 only, and
wants to know whether it would help a Cortex-M0+. This card records the rows and the `blit_rgb565` share; the
experiment is the VESA card's. What to compare:

- Rows: RGB565, `-Os` and `-O2`, cases `syl_ga` (1 bpp path, 256 source pixels, about 100 set), `screen32`
  (1 bpp, 32 glyphs), `aa_line12` and `aa_screen10` (2 bpp path with the colour-pair table): `cycles/iteration`,
  `insns/iteration`, and from a `PROFILE=1` run `blit_rgb565`'s cycles and share, recorded in MEASUREMENTS.md next
  to the rows (as the last card did for `blit_mono_page`).
- The experiment: the same bench with the store enabled for Cortex-M0+, RGB565 builds only, rerun; rp2040js is
  deterministic (identical counts run to run, recorded 2026-10-20), so any difference in those rows is the store's.
  The GRAY8 and MONO_PAGE rows must not move.
- Reading the result: rp2040js charges one extra cycle per SRAM or flash access whatever its width (`cyclesIO`),
  and a real M0+ spends 2 cycles on STRB/STRH/STR to zero-wait SRAM alike, so for the blit's stores (band and
  scratch in SRAM) a saving in the emulator is an instruction-count saving on hardware too; the face reads from
  flash are what it does not model. The Cortex-M0+ faults on an unaligned word store, and neither the bench nor the
  example buffers are declared with 4-byte alignment (`uint8_t` arrays), so a 2-pixel store must test the address
  (`x + col` even and the row base 4-aligned) rather than assume it.

## The ESP32 benches (ESP32-C3 and ESP32-S3)

### What exists on this host (checked 2026-10-20)

- Compilers: `~/opt/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-gcc` 16.1.0 (the C3; the size table's
  toolchain) and `~/opt/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc` 16.1.0
  (crosstool-NG esp-16.1.0_20260609). Both ship a newlib with a QEMU semihosting runtime (what each provides is
  listed under "Build and run lines").
- Emulator: `qemu-system-riscv32` and `qemu-system-xtensa`, QEMU 9.2.2 (`esp_develop_9.2.2_20260417`, Espressif's
  fork; on this host today both sit in `~/opt/qemu-esp-9.2.2-20260417/qemu/bin/`, the layout the installer replaces
  with one directory per archive, "Provenance and installers" below); machines `esp32c3` and `virt` (RISC-V), `esp32`, `esp32s3`,
  `sim` and others (Xtensa); the chip ROMs are bundled (`share/qemu/esp32c3-rom.bin`, `esp32s3_rev0_rom.bin`); the
  `esp_rgb` panel on both ESP machines. The TCG plugin interface is not enabled in this build (`-plugin help`), so
  instruction counting is by counters and `-icount`, not by a plugin.
- Not present and not needed: distribution QEMU (apt, needs sudo), Renode, Wokwi, ESP-IDF, `esptool`.
- Nothing cycle-accurate exists for either chip: QEMU is a translator. With `-icount shift=N,sleep=off` it advances
  virtual time by 2^N ns per guest instruction, deterministically (`sleep=off` keeps it from aligning virtual time
  to the host clock, which otherwise moves the S3's `CCOUNT` by a tick between runs: 1281/1282 in revision 1's
  probe, identical in 15 of 15 runs with `sleep=off` in review); rp2040js, by contrast, applies the Cortex-M0+
  instruction timings.

### Probes run for revisions 1 and 2 (in `/tmp`, not committed)

| machine | how the ELF was built | result |
|---|---|---|
| `qemu-system-riscv32 -M esp32c3 -semihosting -icount shift=0,sleep=off -kernel` | `-specs=esp32c3.qemu.specs -march=rv32imc_zicsr_zifencei -mabi=ilp32`, `printf`, 60-deep recursion, a 140 KB const array, `rdinstret` | runs from the ELF entry at 0x40380000 (the ROM is not involved); `rodata` goes to IRAM (384 KB); `printf` reaches stdout through semihosting; `rdinstret` identical in 15 of 15 runs; QEMU does **not** exit when `main` returns (the runtime's `_exit` spins), so the bench ends with the RISC-V semihosting `SYS_EXIT_EXTENDED` sequence itself, which was verified to end QEMU with the given status |
| `qemu-system-riscv32 -M virt -cpu rv32 -bios none -icount shift=0,align=off -kernel` | bare: `_start` at 0x80000000 (sets `sp`, `gp`, zeroes `.bss`), 16550 at 0x10000000 (byte writes), `rdinstret` | works, deterministic, `SYS_EXIT` ends QEMU with status 0. Kept as the documented fallback only |
| `qemu-system-xtensa -M esp32s3 -semihosting -icount shift=5,sleep=off -kernel` | `-specs=sys.qemu.specs -specs=sim.elf.specs -Wl,--defsym=entire_dram_seg=1 -mlongcalls`, `printf`, 60-deep recursion, a 140 KB const array, `CCOUNT` | the ROM stub jumps to the ELF entry (text at 0x40378000 in IRAM, data in DRAM); without `entire_dram_seg` the 140 KB array does not link (`dram_seg` is 0x3FCF0000 + 64 KB by default; with it 0x3FC80000 + 448 KB); `printf` through semihosting; the recursion passes (window exceptions handled by `crt1-sim`); `exit(code)` ends QEMU with that status; 1000 straight `nop`s read `CCOUNT` 1281 at shift 5 (40 at shift 0, 320 at 3, 5125 at 7): the machine clocks `CCOUNT` at 40 MHz of virtual time, so **CCOUNT x 25 / 2^shift** is the instruction count of a straight-line sequence to within a tick (0.78 instruction at shift 5) |
| the same with `-specs=board.elf.specs` (with or without `sys.qemu.specs`) | | no output, or exit 1: not used |
| `-M esp32s3 ... -accel tcg,one-insn-per-tb=on -d exec -D log` | the S3 probe | one `Trace` line per executed instruction: an exact count, the plan's cross-check of the `CCOUNT` rule over one case |
| `-M esp32c3` / `-M esp32s3` with `-display none -qmp unix:` and the `esp_rgb` registers above | the screen probe | `screendump` and `pmemsave` as described under "Emulated screens" |

### Approach (*my call*): one script, two chips, each number labelled by what it is

`c/bench/run-esp32.sh [OUT]` builds `bench.c` for each (chip, kind, optimisation): twelve builds, the library with
`-DSVF_NO_SCALE -DSVF_TARGETS=<bit>` as the size table and the profiles build it, and runs each under QEMU. Both
builds are newlib programs (`printf`), so the `BENCH_ESP32C3`/`BENCH_ESP32S3` sections of `bench.c` are the host
section's reporting with another clock; `bench.c`'s "exactly one of" check and `BENCH_MCU` list the two new macros.

**What the C3 number is.** `rdinstret` before and after the timed loop (a `volatile` asm with a `"memory"`
clobber): the number of guest instructions QEMU executed in the span, exception handlers included, nothing else: no
pipeline, memory, cache or flash timing. The core is single-issue in-order, CPI >= 1, so instructions / 160 MHz (the
µs column with `mhz=160`) is a **lower bound** of the time on a real C3. Label: "instructions (rdinstret), lower
bound".

**What the S3 number is.** `rsr CCOUNT` before and after, converted as `insns = (ccount * 25 + 16) / 32` at
`-icount shift=5` (the shift passed as `-DBENCH_ICOUNT_SHIFT=5`; the product in `uint64_t`). `CCOUNT` here is QEMU's
virtual clock at 40 MHz, which under `-icount` advances per instruction, so the conversion is exact for straight-line
code (the NOP calibration proves that and nothing more) and is an **estimate** for a loop: it counts the
instructions QEMU translated, but a tick is 1.28 instructions, so a reading is within about one instruction, and no
timing of branches, loads or multi-cycle ops enters it either way. Label: "CCOUNT x 25/32 at icount shift 5,
estimate of instructions (calibrated on NOPs)"; the µs column (`mhz=240`) is "estimate / 240 MHz" and is not called
a bound. The plan's cross-check (one case under `-d exec` with `one-insn-per-tb`, the `Trace` count between the
case's first and last PC against the converted `CCOUNT`) is recorded in MEASUREMENTS.md with the difference.

**Line format, exactly what `report.awk` reads with `mhz` set** (as `pico-run.mjs` prints it), integers only, no
float `printf`: `case=%s iters=%lu cycles=%lu per_iter_cycles=%lu.%lu sum=%08lx` with the fraction one decimal
digit, `c / n` and `(c % n) * 10 / n`; the S3 line adds `ccount=%lu`, raw (unknown fields are ignored); then
`end=%d` from `bench_end`, after which the C3 build executes the semihosting `SYS_EXIT`/`SYS_EXIT_EXTENDED` sequence
with the code and the S3 build calls `exit(code)`, so QEMU's exit status is 0 only for `end=0`. `cycles=` holds
the instruction count (C3) or estimate (S3) on these rows.

**Calibration, S3 only.** Before the cases the S3 build runs 1000 straight `nop`s between two `rsr CCOUNT` and
prints `cal=nop1000 ccount=N` (a `cal=` line, not a `case=` line, so `report.awk` sees no unknown case);
`run-esp32.sh` fails the run unless N is within 2 of 1280: the conversion is checked on every run, not assumed.

**Cases, faces, checksums**: sets A and B exactly as on the Pico, the same `SUMS` from `sums.py`.

**Build and run lines** (`OPT` defaults to `~/opt`; `C` is `c/`; `OUT` defaults to `c/build/bench/esp32`;
`<opt>` is `-Os` or `-O2`; `<bit>` and `<kind>` one of `0x02 SVF_T_MONO_PAGE`, `0x01 SVF_T_GRAY8`,
`0x08 SVF_T_RGB565`; the face arrays `OUT/face.c`, `OUT/face16.c`, `OUT/face18.c` come from `mkface.py` as in
`run-pico.sh`):

    RV=${RV:-$OPT/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf}
    XT=${XT:-$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf}
    QEMU_RV=${QEMU_RV:-$OPT/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32}
    QEMU_XT=${QEMU_XT:-$OPT/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa}

    # ESP32-C3
    $RV-gcc -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -march=rv32imc_zicsr_zifencei -mabi=ilp32 <opt> \
        -DSVF_NO_SCALE -DSVF_TARGETS=<bit> -DBENCH_ESP32C3 -DBENCH_KIND=<kind> -I$C/include \
        $C/bench/bench.c $C/src/*.c $OUT/face.c $OUT/face16.c $OUT/face18.c \
        -specs=esp32c3.qemu.specs -Wl,--gc-sections -o $OUT/bench-c3<opt>-<kind>.elf
    $QEMU_RV -M esp32c3 -nographic -monitor none -serial stdio -semihosting -icount shift=0,sleep=off \
        -kernel $OUT/bench-c3<opt>-<kind>.elf >$OUT/run-c3<opt>-<kind>.txt 2>$OUT/run-c3<opt>-<kind>.err

    # ESP32-S3
    $XT-gcc -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -mlongcalls <opt> \
        -DSVF_NO_SCALE -DSVF_TARGETS=<bit> -DBENCH_ESP32S3 -DBENCH_ICOUNT_SHIFT=5 -DBENCH_KIND=<kind> -I$C/include \
        $C/bench/bench.c $C/src/*.c $OUT/face.c $OUT/face16.c $OUT/face18.c \
        -specs=sys.qemu.specs -specs=sim.elf.specs -Wl,--defsym=entire_dram_seg=1 -Wl,--gc-sections -o $OUT/bench-s3<opt>-<kind>.elf
    $QEMU_XT -M esp32s3 -nographic -monitor none -serial stdio -semihosting -icount shift=5,sleep=off \
        -kernel $OUT/bench-s3<opt>-<kind>.elf >$OUT/run-s3<opt>-<kind>.txt 2>$OUT/run-s3<opt>-<kind>.err

    awk -v build="ESP32-C3 emulated (QEMU 9.2.2 esp_develop, -M esp32c3 -icount shift=0: instructions (rdinstret), lower bound; riscv32-esp-elf-gcc 16.1.0 <opt>; <kind>, SVF_TARGETS=<bit>)" \
        -v mhz=160 -v sums="$SUMS_<kind>" -f $C/bench/report.awk $OUT/run-c3<opt>-<kind>.txt
    awk -v build="ESP32-S3 emulated (QEMU 9.2.2 esp_develop, -M esp32s3 -icount shift=5: CCOUNT x 25/32, estimate of instructions; xtensa-esp32s3-elf-gcc 16.1.0 <opt>; <kind>, SVF_TARGETS=<bit>)" \
        -v mhz=240 -v sums="$SUMS_<kind>" -f $C/bench/report.awk $OUT/run-s3<opt>-<kind>.txt

What the runtimes provide (so nothing bare is written for the bench):

- `esp32c3.qemu.specs` (`riscv32-esp-elf/lib/`): includes `esp.qemu.specs`; startfile `crt1-board.o` (reset entry,
  `sp` from the memory map, `gp`, `.bss` cleared, `main`); libraries `-lc -lsemihost -lpthread_stubs` (newlib with
  semihosting `write`: stdout); linker scripts `esp32c3.memory.ld` (IRAM 0x40380000, DRAM 0x3FC80000) and `app.elf.ld`;
  `--no-warn-rwx-segments`; refuses a build without `-march=rv32imc*`. Exit: its `_exit` spins, hence the explicit
  semihosting exit in `bench_end`. QEMU's own notices ("Not initializing SPI Flash", "Loading kernel at address") are
  on stderr, kept in `.err`.
- `sys.qemu.specs` + `sim.elf.specs` (`xtensa-esp-elf/lib/esp32s3/`): startfile `crt1-sim.o` (reset vector, the
  window overflow/underflow vectors, stack, `.bss`); libraries `-lc -lgloss -lpthread_stubs` with `libsys_qemu`
  whole-archive (semihosting console and `exit`, which stops QEMU with the status); linker scripts `memory.elf.ld`
  (IRAM 0x40378000 + 448 KB; DRAM 0x3FCF0000 + 64 KB, or 0x3FC80000 + 448 KB with `entire_dram_seg` defined, which the
  139 KB face pair needs; on silicon that region overlaps the IRAM alias, which QEMU's machine keeps apart: fine for
  an emulator-only bench, and the checksums would show otherwise) and `app.elf.ld`.

**Determinism**: each run is repeated once by the plan; counts must be identical (`sleep=off` on both chips).

**What the instruction stream is.** The objects are the ones the size table measures; the link is the runtime's
(`crt1-board`/`crt1-sim`, the specs' linker scripts, RISC-V relaxation on with `gp` set by the startup), the same
kind of link ESP-IDF makes, so the stream can differ from an IDF link by relaxation only, as any two links do.

Why not the alternatives: the ESP machines with a flash image would need ESP-IDF and `esptool` (absent) and would
count instructions all the same; distribution QEMU needs sudo and lacks the ESP machines; building QEMU from source
needs meson, ninja and glib headers the user-space rule does not provide for; Renode's ESP32 support is partial and
also a translator; Wokwi is closed and online. A real board re-measures when one is at hand, as
`spec/renderer-design.md` says of every board.

### Provenance and installers

Every tarball below is already on this host (installed by the user on 2026-10-20); the scripts verify what they
fetch and **re-verify what is installed on every run** (SOL). Rules, one tree per archive:

- **One destination per archive, never shared.** The two QEMU tarballs unpack to
  `$PREFIX/qemu-esp-9.2.2-20260417-riscv32/qemu/` and `$PREFIX/qemu-esp-9.2.2-20260417-xtensa/qemu/` (each tarball's
  top directory is `qemu/`; `unpack` moves it under its own parent). Two archives into one directory would nest the
  second (`mv` of an existing directory moves it inside) and overwrite the manifest. `QEMU_RV`/`QEMU_XT` point at
  these. On this host both binaries currently share `~/opt/qemu-esp-9.2.2-20260417/qemu/`; the plan re-installs
  from the verified copies in `~/opt/dl` (16 and 15 MB) into the two directories and leaves the old one alone.
- **`unpack` creates the parent** (`mkdir -p "$(dirname "$DEST")"`) before moving the tarball's top directory to
  `DEST`, and then checks the layout it promised (`DEST/bin/<tool>` runs and prints the pinned version), so a clean
  machine installs the Xtensa toolchain into `$PREFIX/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/` (the
  tarball's top directory `xtensa-esp-elf/` kept under its parent, the layout already on this host).
- **Manifest.** An install of a tarball writes `<dest>/.svf-manifest`: line 1 the archive's pinned sha256, then the
  tree list, computed **relative to the root** so that two trees compare like with like wherever they sit:

      (cd "$dir" && { find . -type f ! -name .svf-manifest | LC_ALL=C sort | xargs -d '\n' sha256sum;
                      find . -type l | LC_ALL=C sort | while read -r l; do printf 'link %s -> %s\n' "$l" "$(readlink "$l")"; done; })

  (every regular file hashed, every symlink listed with its target: the Xtensa tarball holds 54 links; `.svf-manifest`
  itself excluded). `--verify <name>` recomputes exactly that list and compares; a difference stops the script with
  the first mismatching path.
- **Git clones** (pico-sdk) get **no file in the working tree**: the pinned commit lives in the script, and
  `--verify` checks `git -C <dest> rev-parse HEAD` equals it and `git -C <dest> status --porcelain` prints nothing
  (no `.git/` hashing: packfiles differ between clones). Were any marker ever needed there, it would go in
  `<dest>/.git/info/exclude` first; a plain file would make `status` report it and fail every verify.
- **First manifest for trees the user already installed** (the three ESP tarballs): `--adopt <name>` re-hashes the
  copy in `~/opt/dl` against the pin, unpacks it into a temporary directory, computes the list above for the
  temporary tree and for the installed one (both relative to their roots, so the paths agree), compares, and only
  then writes the manifest; a difference is reported and nothing is written.
- **`--verify` covers installed packages only**: a package whose directory is absent is reported as "not installed"
  and is not an error (the Arm toolchain, pico-sdk, the ESP toolchains and QEMUs are each optional to some script).
  Each script verifies exactly what its targets need before running them: `run-pico.sh` the Arm toolchain and
  rp2040js; `run-esp32.sh` the two ESP toolchains and QEMUs; `run-screens.sh` the Arm toolchain, pico-sdk, rp2040js
  with the boot ROM, the ESP toolchains and QEMUs; `build-all.sh` every toolchain it builds with, and, separately,
  tests the presence of pico-sdk and the QEMUs to decide between running `run-screens.sh` and printing
  `screens: skipped (<what is missing>)`. A present-but-corrupt tree is always an error; the installers never
  replace one on their own.
- Downloads: exact URLs below, `curl --fail` into `<file>.part`, rename after the hash matches, unpack into a fresh
  directory and move into place, as the scripts do today.

The chain: the GitHub release page of the publisher -> its checksum asset (a plain sha256 list the publisher uploads
with the binaries; not a signature) -> the tarball. The local copies were checked against the assets on 2026-10-20
and match line for line.

| what | URL | sha256 (publisher's) | where the publisher lists it | installed at |
|---|---|---|---|---|
| QEMU riscv32 | https://github.com/espressif/qemu/releases/download/esp-develop-9.2.2-20260417/qemu-riscv32-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz (16,842,920 bytes) | `547f03e04701a92cbb699f7f7d015adc1f5b5ef93cbb94c0dd9b7107e2d84e77` | asset `qemu-esp_develop_9.2.2_20260417-checksum.sha256` of the same release | `~/opt/qemu-esp-9.2.2-20260417-riscv32/qemu/` (local copy `~/opt/dl/qemu-esp/qemu-riscv32-esp.tar.xz`) |
| QEMU xtensa | https://github.com/espressif/qemu/releases/download/esp-develop-9.2.2-20260417/qemu-xtensa-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz (15,619,396 bytes) | `0eecb2a34a5586c0e59110f77b9343b7b336e82fdb0e1a30e1dc1bab8a547e35` | the same asset | `~/opt/qemu-esp-9.2.2-20260417-xtensa/qemu/` (local copy `~/opt/dl/xtensa-esp/qemu-xtensa-esp.tar.xz`) |
| Xtensa toolchain | https://github.com/espressif/crosstool-NG/releases/download/esp-16.1.0_20260609/xtensa-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz (89,005,792 bytes) | `f708752ebb35cab21f184b2574114ed1187619db0edb8a4ba913c06ca2fa675e` | asset `crosstool-NG-esp-16.1.0_20260609-checksum.sha256` (the same asset lists the riscv32 toolchain's `0b029ab3...` already pinned) | `~/opt/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/` (local copy `~/opt/dl/xtensa-esp/xtensa-esp-elf.tar.xz`) |
| pico-sdk | https://github.com/raspberrypi/pico-sdk.git tag `2.3.1`, commit `079c6f39023649b154152db30f1d781e884879bc` (hard-coded; the script stops unless the clone's HEAD is this commit; confirmed in review with `git ls-remote`) | (git commit) | the tag | `~/opt/pico-sdk-2.3.1` (to be installed by the plan) |
| rp2040js boot ROM file | https://raw.githubusercontent.com/wokwi/rp2040js/v1.4.0/demo/bootrom.ts (50,364 bytes; tag v1.4.0 = commit `0c1c316e87b34e616985af35d4c147fc19cfeee9`) | `99f8a1f813ce3aa9415884de3fb6c5b962d3c6fa0394b05413ad3c7b3c39ec62` (measured twice, 2026-10-20; the file is not a release asset; its content is the RP2040 B1 boot ROM, `pico-bootrom` revision `00a4a19114195e20fb817bdfbca1165e157eef37`) | the rp2040js repository at that tag | `~/opt/dl/rp2040js/bootrom.ts` (the download), converted to `~/opt/rp2040js-1.4.0/bootrom-b1.bin` (16,384 bytes, the words little-endian; its sha256 pinned in the script at first generation) |

The "self-pinned, no published hash" wording of revision 0 was wrong and is withdrawn (the publisher assets exist
for the three tarballs; the boot ROM file and the SDK are pinned by content and by commit).

## MEASUREMENTS.md rows

- "What is measured": set A gains `line8`; set B and its 240 x 24 band are described; the kinds and their buffers;
  the ESP32 builds.
- "How time is measured": rows for the ESP32-C3 (instructions, `rdinstret`, lower bound) and the ESP32-S3 (`CCOUNT`
  x 25/32, estimate, the calibration and the cross-check) and the provenance rows above.
- "Results": the Pico table grows to the six builds (kind x flags), grouped by kind with MONO_PAGE first, with the
  `insns` column; new "ESP32-C3 (no budget; instruction counts)" and "ESP32-S3 (no budget; CCOUNT-derived
  estimates)" tables with the same grouping; the Uno table unchanged.
- "Against the budgets": the MONO_PAGE rows re-measured; one line "colour and grey on small panels: no budget
  (user, 2026-10-20); measured: Pico RGB565 `syl_ga` x µs, GRAY8 y µs, ...". The "Still over" table keeps its
  entries and gains none from this card unless a MONO_PAGE row regresses.
- "Findings": the ratio of RGB565 and GRAY8 to MONO_PAGE per case (expected: GRAY8 1 bpp close to MONO_PAGE,
  RGB565 1 bpp more because of two byte stores a pixel, the 2 bpp paths more again); `blit_rgb565`'s share from
  `PROFILE=1` for the VESA card; the Pico and the C3 compared in instructions per case, the S3 beside them with its
  estimate label, with the caveat that only the Pico column is also cycles.
- A "Screens" section pointing at `run-screens.sh`, with the five results and the PNG paths of the last run.

## Tests

- `make -C c check` green, unchanged: the library does not change. If any library change turns out to be needed,
  it is a separate card.
- `c/cross/build-all.sh --ports`: 32 `OK` lines (twelve `port-*`, `port-check-grey-pack`, seven
  `port-check-driver-*`, seven `port-check-profile-*`, five `screen-*`); the profile consistency check (`nm` for the
  two unique symbols, the `SVF_TARGETS` bit, the `profiles.cmake` row against the awk row) passes for all nine
  images; `install-*.sh --verify` passes first for the toolchains the run builds with (absent optional packages
  are reported, not failed).
- `c/ports/check/run-screens.sh`: the three Pico profiles build with the pico-sdk and draw, under rp2040js, panel
  memory identical to the `svfline` reference, each run ending at `svf_port_idle` with the expected show count; the
  two ESP32 colour builds draw identical VRAM on `-M esp32c3` and `-M esp32s3`; PNGs written; a deliberately wrong
  byte in a text string makes the run fail with an offset and a diff PNG, and a deliberately split (`nostop`)
  SSD1306 control byte makes the mono run fail (the plan does both once to prove the checks bite).
- `c/bench/run-pico.sh`: six runs, every checksum `ok` (twice: counts identical); `c/bench/sums.py` reproduces the
  four existing MONO_PAGE checksums; `bench.c` on the host (`-DBENCH_HOST -DBENCH_MCU -DBENCH_KIND=...`) prints the
  same checksums for every kind; `run-avr.sh` output unchanged.
- `c/bench/run-esp32.sh`: twelve runs, every checksum `ok`, `end=0` and QEMU status 0, the S3 calibration within
  2 of 1280; repeated once, counts identical; the `-d exec` cross-check recorded.
- The READMEs' "What was checked" paragraphs match the table above, per profile and chip, with the sizes from
  `SIZES.md`, and link `c/ports/FACES.md`.
- `tools/test_c_renderer.py` is unchanged; `TestTargets` already covers the three kinds at 1 and 2 bpp, odd strides,
  both byte orders, thresholds and clipping.

## Risks

- **Hardware still unverified.** The emulated screens prove the firmware's bytes against the panel models, which
  decode what the datasheets say; a module variant (ST7789 inversion, the 80-row offset in portrait on 240 x 240
  modules, BGR order; SSD1327 remap) or a timing matter would not show. Each README names the module assumed and the
  one byte to change.
- **pico-sdk under rp2040js.** Retired for 2.3.1 by the review's measurement (configures offline, builds, boots
  under rp2040js from 0x10000000 after `loadBootrom`); what remains is the full profile images, which the first plan
  task runs. The SDK CMake fetches picotool from git unless `PICO_NO_PICOTOOL=1`; the check builds set it, so the
  configure step is offline. The runner's loader (by `p_paddr`) and clock loop are the two details a port of
  `pico-run.mjs` would get wrong; both are specified from measurements above.
- **XIP cache.** The colour and grey Pico profiles put 139 KB of faces in flash behind a 16 KB XIP cache; rp2040js
  does not model it (recorded already for the 19 KB mono image). Real colour/grey numbers will be slower than the
  bench rows by an amount the bench cannot give; the README and MEASUREMENTS.md say so.
- **Numbers are not time.** The ESP32 rows can be misread as µs; the labels, the table headings and the findings
  say what each number is (C3 instructions, lower bound; S3 CCOUNT-derived estimate). The S3 conversion rests on
  the 40 MHz `CCOUNT` clock of the QEMU machine, checked by the calibration line on every run, and on `sleep=off`.
- **The toolchains' QEMU runtimes** were probed with `printf` programs holding a 140 KB array, not with the bench
  or the colour example; if the full builds trip over them (stack size, section placement), the bare `virt` route
  for the C3 is documented above, and for the S3 the fix is a `--defsym` or a linker-script override, not a new
  machine.
- **`esp_rgb` update timing.** The panel copies at `screendump` only under `-display none`; a driver that polls
  `RGB_UPDATE_STATUS` hangs there. `disp_esp_rgb.c` does not poll; the README says why, and that under a real
  display the copy happens at the next refresh instead.
- **Bench run time.** Set B on the emulators draws 2 bpp 18 px cells from a 124 KB face; `aa_screen10` at 5
  iterations is about 50 band draws, well under a minute a build. If a run exceeds a few minutes the iteration count
  is lowered, never the case removed. The Pico screen runs execute the SDK start-up and a full frame (rp2040js's
  I2C and SPI models take no emulated time; the waits, SLPOUT and resets, cost clock time but no instructions under
  the tick loop): well under a second each in review.
- **Pico RAM for the grey frame**: 16 KB of 264 KB; the C3 has 400 KB, the S3 512 KB. No pressure, but the examples
  keep every buffer static and sized by the profile, so the numbers in the size table are the whole RAM story.
- **ESP-IDF `-D` pass-through and early expansion**: handled above; a stale `build/` keeps the old cache value.
- **Default drift.** Keeping each port's default profile as today means the two boards default differently
  (`mono` vs `colour`); the READMEs state the default on the first line.
- **Install verification cost.** Hashing the installed trees (about 1 GB in all) on every script run takes a few
  seconds; acceptable, and `--verify` is one place to tune if not.

## What counts as done

- Both ports configure and build three profiles (`SVF_PROFILE=colour|grey|mono`) from `profiles.txt`, one profile
  source and one driver each, plus the ESP32 `esp_rgb` backend; `c/cross/build-all.sh --ports` builds all nine stub
  images (Pico, ESP32-C3, ESP32-S3) with `-Werror`, runs the host checks and the consistency check;
  `c/cross/SIZES.md` carries the port table, the `esp32s3-xtensa` toolchain and the P3g rows; the installers pin the
  publisher hashes, the SDK commit and the boot ROM file, and re-verify installs.
- `c/ports/check/run-screens.sh` runs the three real Pico images under rp2040js on the virtual SSD1306, SSD1327 and
  ST7789, and the ESP32-C3 and ESP32-S3 colour images on QEMU's `esp_rgb`, with panel memory identical to `svfline`
  and PNG artifacts kept.
- `c/bench/run-pico.sh` runs six builds with sets A and B, every checksum from `svfline` ok, MONO_PAGE budgets
  reported as before, RGB565/GRAY8 rows without a budget, `insns` recorded; `blit_rgb565` share recorded for the
  VESA card.
- `c/bench/run-esp32.sh` runs twelve builds on the `esp32c3` and `esp32s3` machines with checksums ok and the S3
  calibration passing; MEASUREMENTS.md has the rows and findings listed; every number labelled by what it is.
- `make -C c check` green; the READMEs' "What was checked" per profile and `c/ports/FACES.md` are true.

## Open questions for the user

None. (Possible later work, not asked for: the grey and mono ESP32 profiles could also be shown on `esp_rgb`
through a converting driver; the ESP-IDF images themselves could be run on QEMU once `idf.py` is installed.)

## Changelog

**Revision 5 (2026-10-21, after execution)** records the rulings taken while the plan was carried out, so this spec
stays the reference. Where the body above says otherwise, this entry wins:

- The ESP32-S3 rows count **core 0's Xtensa `ICOUNT`**, not "`CCOUNT` x 25/32, estimate" (the S3 lines of "The ESP32
  benches", the MEASUREMENTS.md rows, the risks and the done list). Under `-icount` `CCOUNT` is the global virtual clock
  and also advances while core 1, which this QEMU cannot park, spins in the ROM, by a layout-dependent amount. `ICOUNT`
  counts only core 0's completed instructions; the S3 `us` column is instructions / 240 MHz, a lower bound like the
  C3's. The calibration gate (`check-esp32-cal.sh`) checks 1,000 NOPs against `CCOUNT` and four loops of 1,000,000
  instructions against `ICOUNT`. Commit 7e54163; MEASUREMENTS.md "Why not CCOUNT".
- `build-all.sh --ports` prints **37 `OK` lines**, not 32: 12 ports + 15 `port-check-*` + 5 `screen-*` +
  `pico-screen-negative` + `run-screens-gates` + 3 unit tests (`port-check-unit-esp-screen`, `-screens`, `-panels`).
  Commit 06f5154.
- `c/bench/report.awk` **does change**, compatibly: opt-in `exact=1` (the cases run are exactly those of `sums`, each
  once) and `need_insns=1` (every case carries positive `insns` and `per_iter_insns`), commit 0d9fa9d; and a
  cycle-reporting run must have positive `iters`, `cycles` and `per_iter_cycles` that agree with each other, commit
  9234022. Runs that set none of these read as before.
- `tools/test_c_renderer.py` **is not unchanged**: it gains `TestBenchSums` (the host build of `bench.c` agrees with
  `sums.py` and with the `SUMS_<kind>` constants of `c/bench/sums.inc.sh`, and `report.awk` refuses a wrong case set or
  instruction count). Commit 0d9fa9d.

**Revision 4 (2026-10-20, the last before the user's approval)** after the revision-3 re-reviews (Opus
approve-with-changes, probed under rp2040js; agy reject; SOL stopped by the user):

- Opus I1: the runner's failure exits are mechanisms, not words: `mcu.onBreak` fails the run (SDK HardFault, `panic`,
  `_exit` all end in BKPT and the default handler ignores it); `core.waiting` with `nanosToNextAlarm === 0` fails
  instead of spinning; a host iteration bound as the last resort. `mcu.clock` is used (`SimulationClock` is not
  exported); the SDK's two harmless I2C-init warnings are logged, not failed.
- agy C1: no `.svf-manifest` inside a git clone (the pin lives in the script; `rev-parse HEAD` + clean `status`);
  `.git/info/exclude` named should a marker ever be needed.
- agy C2 / Opus m2: the runner asserts the panel's **show** count against `SHOWS` (15 / 1 / 1), never the
  data-transfer count (15 / 8 / 32, logged only).
- agy: manifests are computed relative to each root (`cd "$dir" && find . ...`), so `--adopt` compares equal
  paths; symlinks listed with their targets (Opus m4).
- agy: `--verify` covers installed packages only; each script verifies what its targets need; `build-all.sh` tests
  presence separately before `run-screens.sh` or `screens: skipped`.
- agy: `esp-screen.py` unlinks a stale `OUT/qmp.sock`, strips whitespace, ignores empty and known start-up lines
  while waiting for `screen=ready` (any other non-empty line still fails).
- agy: `disp_esp_rgb.c` separates the host-side pointers (`ESP_RGB_REGS`, `ESP_RGB_VRAM`, overridable) from the
  32-bit value the device is told (`ESP_RGB_VRAM_ADDR`), so it compiles under `-Werror` on 64-bit hosts without a
  pointer-to-integer cast.
- Opus m3: `screen_ref.py ... OUT` in the `run-screens.sh` shorthand; the "400 kHz" wording replaced by what rp2040js
  emulates (transfers take no emulated time; 120.66 ms and 84,033 cycles to the idle symbol in the probe).

**Revision 3 (2026-10-20)** after the revision-2 re-reviews (Opus approve-with-changes, measured under rp2040js;
agy reject; SOL unavailable):

- Opus C1: no `nostop` split anywhere. The SSD1306 driver sends eight writes of 0x40 + 128 bytes from a static
  129-byte buffer; the SSD1327 driver one 257-byte write a chunk (byte 0 = 0x40); both I2C panel models restart
  control-byte framing on every `onConnect` (repeated START included) and handle `onStart`; `test_drivers.c` asserts
  the whole-transaction writes and forbids `nostop`; the screen test deliberately breaks it once.
- Opus I1: `pico-screen.mjs` loads SDK ELF segments by `p_paddr` (the `.data` load image lives in flash) and calls
  `loadBootrom` before the flash copy (it fills flash with 0xFF).
- Opus I2 / agy I3: the runner drives rp2040js's `SimulationClock` with the `Simulator.execute` loop (8 ns a cycle,
  `nanosToNextAlarm` while waiting); completion is the PC reaching `svf_port_idle` (a named, non-inlined idle
  function called after `profile_run`, no BKPT), with the show count checked against `screens.py` and a 10 s limit of
  emulated time; the quiet-window heuristic and the cycle limit are gone, so the ST7789 capture cannot race.
- agy C1: one install directory per QEMU archive (`qemu-esp-9.2.2-20260417-riscv32/qemu/`, `-xtensa/qemu/`),
  `QEMU_RV`/`QEMU_XT` updated, one manifest each; the shared directory on this host is re-installed from the verified
  copies.
- agy C2: `unpack` creates the destination's parent and checks the promised layout (`bin/<tool>` runs).
- agy I4: `screen_ref.py BOARD PROFILE OUT` with `BOARD` in `pico|esp32c3|esp32s3`; one file scheme
  `OUT/<board>-<profile>.*` for runners and reference.
- agy I5: the manifest excludes itself; git clones are verified by `rev-parse HEAD` and a clean `status`, never by
  hashing `.git/`; `--adopt` writes the first manifest for already-installed trees (Opus m3).
- agy I6: the boot ROM has one canonical form and place: `demo/bootrom.ts` (sha256 `99f8a1f8...ec62`, pinned)
  downloaded to `~/opt/dl/rp2040js/`, converted to `~/opt/rp2040js-1.4.0/bootrom-b1.bin`; no module under `c/`.
- agy I7 / Opus m4: `FACES.md` names the tools (`mkfont.py` via `bake-paperlogy.sh`; `fontbuild2.py`), Paperlogy's
  sources (Lee Juim; Gmarket Sans; Montserrat) and version, and HGKEY6J's copyright notice (Dongsu Jang, 2025).
- agy minors: `PICO_SDK_PATH` as a cache variable with an environment fallback; `ESP_RGB_REGS`/`ESP_RGB_VRAM` macros
  for the host driver test; `esp-screen.py` timeouts. Opus minors: CS/DC as SIO outputs; the remap rationale in
  `grey_pack.h`; the ESP32 colour profile test in both byte orders (seven profile runs, 32 `OK` lines); the S3 pin
  reason; the rp2040js CI wording.

**Revision 2 (2026-10-20)** after the re-reviews (Opus approve-with-changes, SOL approve-with-changes, agy reject)
and the user's emulated-screens requirement:

- **Emulated screens** (user): the pico-sdk builds of the three Pico profiles run under rp2040js with SSD1306,
  SSD1327 and ST7789 panel models on the emulated I2C/SPI (hooks, framing, memories, stop condition, boot ROM file
  and SDK pinned); the ESP32-C3/S3 colour example draws on QEMU's `esp_rgb` (register map and addresses from the
  device source and a probe; `disp_esp_rgb.c`; QMP `screendump` + `pmemsave`; the PPM's 5/6/5 replication rule);
  `screen_ref.py` compares panel memory byte for byte with `svfline`; PNG artifacts; `run-screens.sh` in
  `build-all.sh --ports`.
- agy C1: `PORT_LCD_W` per port (240 / 320) sizes the band, target and stride; `display_565_bigendian` per driver.
- agy C2: the mono render buffer is exactly 1,024 bytes; the SSD1306 driver sends the 0x40 control byte with
  `nostop` and the frame as a second call of the same transaction.
- Opus I1 / SOL / agy: the colour band clause now matches the drawing (10-band clear, then five text bands at
  y = 16 + 28 i); `test_profiles.c` links the real `profile_<p>.c` through a recording `display_show` and checks
  y/rows and bytes for both widths; `test_drivers.c` expectations fixed for the SPI OLEDs (DC-high data, no prefix).
- Opus I2: `-Wl,--defsym=entire_dram_seg=1` on the S3 line, with why; the "1.4 MB" claim corrected.
- Opus I3: `-icount shift=5,sleep=off` (S3) and `shift=0,sleep=off` (C3); the determinism claim restated.
- SOL: S3 rows labelled "CCOUNT x 25/32, estimate", C3 "instructions, lower bound", with what each is and is not;
  full build and run lines without ellipses and what each specs file provides; `grey_pack_rows` validates `w`,
  `stride`, `rows` and is tested under ASan; installers re-verify installs by manifest on every run; the complete
  Xtensa URL; the faces' provenance table (`c/ports/FACES.md`).
- agy Important: ESP32-S3 pins fixed (MOSI 11, SCLK 12, CS 10, DC 4, RST 5); unique `svf_port_driver_<d>` /
  `svf_port_profile_<p>` symbols for the `nm` check; install directory layout (top directories kept) stated.
- Opus minors: `max_transfer_sz` 256 for the SSD1327; `per_iter_cycles` one decimal digit and a 64-bit product;
  grey x 4, mono x 0; `profiles.cmake` run by `build-all.sh` in script mode; GPIO stubs in `hardware/gpio.h`
  included by `pico/stdlib.h`; the `sim.elf.specs` size-link fallback dropped (bare link probed); `BENCH_ESP32C3`/
  `BENCH_ESP32S3` in `bench.c`'s checks. agy minors: `grey_pack_rows` declares its indices.

**Revision 1 (2026-10-20)** after the first reviews and the user's decisions: ESP32-S3 added; `profile_<p>.c` per
profile with one `display_show(buf, y, rows)`; SSD1327 arithmetic fixed (8,192 bytes, 32 chunks of 256) and
`grey_pack_rows` shared; ESP32 bench protocol and environment specified and probed; publisher checksums pinned;
`c/ports/profiles.txt`; `SVF_PROFILE` validated in the top-level ESP-IDF CMake; exact text sets with widths;
`line8` and set B out of the AVR build; set B colours; `compose_bwelk` from `jamoset`; VESA section corrected;
`pico-run.mjs` instruction count; recording-stub driver checks; licence sections.
