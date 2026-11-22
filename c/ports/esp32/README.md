**English** | [한국어](README.ko.md)

# ESP32 example (ESP-IDF): colour, grey and mono profiles (default: colour)

One image per profile, chosen at configure time with `-DSVF_PROFILE=colour|grey|mono` (default `colour`). `main/main.c`
runs `display_init(); profile_run();` and then `svf_port_idle()` (a non-inlined function that sleeps for ever in
`vTaskDelay`). The drawing is in `main/profile_<p>.c`, the panel in `main/disp_<driver>.c`.

| profile | panel | driver | wiring (ESP32-C3 / ESP32-S3) | faces |
|---|---|---|---|---|
| `colour` | 320 x 240 RGB565 ILI9341, SPI2 | `disp_ili9341.c` | MOSI 7 / 11, SCLK 6 / 12, CS 10, DC 2 / 4, RST 3 / 5 | `svf/dos/PAPLG16.SVF` + `PAPLG18.SVF` |
| `colour` with `-DSVF_DISPLAY=esp_rgb` | QEMU's 320 x 240 RGB panel, plain MMIO | `disp_esp_rgb.c` | none | the same |
| `grey` | 128 x 128 SSD1327, SPI2 | `disp_ssd1327.c` | MOSI 7 / 11, SCLK 6 / 12, CS 10, DC 2 / 4, RST 3 / 5 | the same |
| `mono` | 128 x 64 SSD1306, SPI2 | `disp_ssd1306.c` | MOSI 7 / 11, SCLK 6 / 12, CS 10, DC 2 / 4, RST 3 / 5 | `svf/dos/NEODG16G.SVF` |

`SVF_DISPLAY` (`ili9341`, the default, or `esp_rgb`) matters for `colour` only; `esp_rgb` with another profile is an
error. `c/ports/profiles.txt` is the table behind the profiles (kind, `SVF_TARGETS` bit, faces, driver, bus);
`c/ports/profiles.cmake` reads it. The library is built with `SVF_NO_SCALE` and the profile's one `SVF_TARGETS` bit
(`SVF_ESP32S3=1` too when the IDF target is esp32s3). The grey profile draws GRAY8 and the driver packs it to the
SSD1327's 4 bits a pixel; `-DSVF_GREY_KIND=GRAY8` (the only value, and the default) is the cache STRING that names the
kind.

Build (ESP-IDF installed and exported, or `-DIDF_PATH=<esp-idf directory>`; python3 for the face arrays), one build
directory per profile and chip:

    cd c/ports/esp32
    idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3 && idf.py -B build-colour build flash monitor
    idf.py -B build-grey   -DSVF_PROFILE=grey   set-target esp32s3 && idf.py -B build-grey build
    idf.py -B build-mono   -DSVF_PROFILE=mono   set-target esp32c3 && idf.py -B build-mono build
    idf.py -B build-qemu   -DSVF_PROFILE=colour -DSVF_DISPLAY=esp_rgb set-target esp32s3 && idf.py -B build-qemu build

`set-target` empties the build directory. To switch profile or chip in a directory you have, run `idf.py -B <dir>
fullclean` and configure again, or take a fresh `-B`: a stale cache keeps the old `SVF_PROFILE` / `SVF_DISPLAY`
(`-D` options of `idf.py` reach CMake's cache only when it is configured). A build directory is tied to its profile (for
grey, also to `SVF_GREY_KIND`): configuring it again with another `SVF_PROFILE` (or, for grey, another `SVF_GREY_KIND`)
is an error ("configured for ..."); use a fresh `-B` directory (or delete the old one).

`main/CMakeLists.txt` generates the profile's face arrays at build time with `c/bench/mkface.py` (not committed: PAPLG18
is a 124 KB face, about 450 KB of C) and builds the library sources into the `main` component;
`-DSVF_FACE_ASCII=` / `-DSVF_FACE_HANGUL=` pick other faces for colour and grey, `-DSVF_FACE=` another 16 px 1 bpp face
for mono.

Licences: the images embed font software ([FACES.md](../FACES.md) names each face's source, copyright and licence). A
distributed image must carry `c/ports/FACES.md` and the licence texts (`svf/dos/OFLPAPLG.TXT`,
`svf/dos/OFL.TXT`, `svf/dos/NEODGM.TXT`); configuring copies them to `<build>/licences/`.

`main/main_qemu.c` is the bare-metal main of the QEMU screen run: `display_init(); profile_run();`, then it prints
`screen=ready` (or, when a profile call failed, `screen=failed`) on the newlib semihosting console and spins. It needs no
IDF header.

Modules assumed (written to the datasheets and the usual breakout boards; not tried on a panel), and the one byte to
change for the common variant:

- ILI9341, 320 x 240: `MADCTL` (`0x36`) with `0x28` (row/column exchange for landscape, BGR panel; `0x20` for an RGB
  module), `COLMOD` `0x55`, no `INVON`.
- SSD1327, 128 x 128: remap `0xA0` with `0x51` (bit 1, the nibble remap, clear: the left pixel of a pair is the high
  nibble, the order `grey_pack_rows` packs); a module showing each pair swapped wants `0x53`.
- SSD1306, 128 x 64: segment remap and COM scan `0xA1`, `0xC8`.

`esp_rgb` (QEMU's RGB panel, `-DSVF_DISPLAY=esp_rgb`): `disp_esp_rgb.c` writes the frame to the panel's VRAM and the
update registers and **never polls** `RGB_UPDATE_STATUS`: the device copies at its next update (`screendump` under
`-display none`, the next refresh under a real display) and the status stays 1 until then, so a driver that waited
for it, as `esp_lcd_qemu_rgb` does, would hang under `-display none`. The image therefore shows nothing until the
host asks for a copy.

## What was checked

No ESP-IDF is installed here: the two `CMakeLists.txt` were read against the IDF documentation and run only through
`test_esp32_cmake.sh` and `test_esp32_component.sh` (stand-in `IDF_PATH`, mocked IDF commands), never by `idf.py`, and
nothing has run on hardware. Per profile:

| | colour (ILI9341, or `esp_rgb`) | grey (SSD1327) | mono (SSD1306) |
|---|---|---|---|
| host checks (`sh c/ports/check/host-checks.sh`: the real `profile_<p>.c` through a recording `display_show`, compared with `c/ports/check/screen_ref.py`, colour in both pixel orders and the ESP32-S3 title; driver command streams against recording stubs; the `esp_rgb` register writes counted) | yes | yes | yes |
| configure rules and component sources (`test_esp32_cmake.sh`, `test_esp32_component.sh`) | yes | yes | yes |
| links for riscv32 (ESP32-C3) and xtensa (ESP32-S3) against `stub/` (`c/cross/build-all.sh --ports`), text without faces (`c/cross/SIZES.md`) | C3 7,456 bytes, S3 6,498 | C3 6,996, S3 6,102 | C3 7,478, S3 6,564 |
| bare image of `profile_colour.c` + `disp_esp_rgb.c` run on QEMU 9.2.2 `-M esp32c3` and `-M esp32s3` (`sh c/ports/check/run-screens.sh`): VRAM and the `screendump` PPM identical to the reference on both | yes (the `esp_rgb` build only) | no | no |
| only built or read: the ESP-IDF image, SPI timing, panel variants, pin mapping, the ILI9341 / SSD13xx SPI paths on real panels | yes | yes | yes |

The PNG of the C3 and S3 screens is written to `c/build/screens/esp32c3-colour.png` and `esp32s3-colour.png` by
`run-screens.sh` (not committed). `main_qemu.c` also runs on the host with recording stubs. `c/cross/build-all.sh
--ports` runs all of these and prints 43 `OK` lines (see `c/ports/pico/README.md`). Speed: `c/bench/MEASUREMENTS.md` has
the ESP32-C3 and ESP32-S3 bench as instruction counts under QEMU, not cycles and not microseconds.
