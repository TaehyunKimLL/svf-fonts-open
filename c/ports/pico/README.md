**English** | [한국어](README.ko.md)

# Raspberry Pi Pico example (pico-sdk): colour, grey and mono profiles (default: mono)

One image per profile, chosen at configure time with `-DSVF_PROFILE=colour|grey|mono` (default `mono`). `main.c` runs
`display_init(); profile_run();` and then `svf_port_idle()` (a non-inlined function that sleeps for ever). No stdio, no
semihosting, no BKPT in the example's own code.

| profile | panel | driver | wiring | faces |
|---|---|---|---|---|
| `colour` | 240 x 240 RGB565 ST7789, SPI0 | `disp_st7789.c` | MOSI GP19, SCK GP18, CS GP17, DC GP16, RST GP20 | `svf/dos/PAPLG16.SVF` + `PAPLG18.SVF` |
| `grey` | 128 x 128 SSD1327, I2C0 | `disp_ssd1327.c` | SDA GP4, SCL GP5, address 0x3C | `PAPLG16.SVF` + `PAPLG18.SVF` |
| `mono` | 128 x 64 SSD1306, I2C0 | `disp_ssd1306.c` | SDA GP4, SCL GP5, address 0x3C | `svf/dos/NEODG16G.SVF` |

`c/ports/profiles.txt` is the table behind them (kind, `SVF_TARGETS` bit, faces, driver, bus); `profiles.cmake` reads it.
The library is built with `SVF_NO_SCALE` and the profile's one `SVF_TARGETS` bit. The grey profile draws GRAY8 and the
driver packs it to the SSD1327's 4 bits a pixel; `-DSVF_GREY_KIND=GRAY8` (the only value, and the default) is the cache
STRING that names the kind.

Toolchain (built and measured here): pico-sdk **2.3.1** (`~/opt/pico-sdk-2.3.1`), arm-none-eabi-gcc 15.2.1 (Arm GNU Toolchain
15.2.Rel1; `sh c/cross/install-toolchains.sh "$HOME/opt" arm` puts it in `~/opt/arm-gnu-toolchain-15.2.rel1/bin`, which must be on `PATH`),
CMake, python3 for the face arrays, picotool 2.3.1 for the `.uf2`.

Build (pico-sdk installed; python3 for the face arrays), one build directory per profile:

    cmake -S c/ports/pico -B build-pico-mono   -DSVF_PROFILE=mono   -DPICO_SDK_PATH=/path/to/pico-sdk
    cmake -S c/ports/pico -B build-pico-grey   -DSVF_PROFILE=grey   -DPICO_SDK_PATH=/path/to/pico-sdk
    cmake -S c/ports/pico -B build-pico-colour -DSVF_PROFILE=colour -DPICO_SDK_PATH=/path/to/pico-sdk
    cmake --build build-pico-colour      # build-pico-colour/svf_pico_colour.elf and .uf2

`PICO_SDK_PATH` may come from the environment instead. `-DCMAKE_BUILD_TYPE=Release` gives the sizes below.

**Pico 2 (RP2350, Arm cores).** The same sources build for it with `-DPICO_BOARD=pico2` (the pico-sdk's board name; it selects
the `rp2350-arm-s` platform), one fresh build directory each:

    cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH=/path/to/pico-sdk

The three profiles build for it (sizes under "What was checked"); like the Pico images they have not run on a board.
The `.uf2` conversion by hand (below) is for the RP2040; for a Pico 2 let the SDK's picotool step make it (configure
without `-DPICO_NO_PICOTOOL=1`), or give `picotool uf2 convert` the RP2350 family and platform. A build directory is tied to its profile (for grey, also to `SVF_GREY_KIND`):
configuring it again with another `SVF_PROFILE` (or, for grey, `SVF_GREY_KIND`) is an error ("configured for ..."); use a fresh
`-B` directory (or delete the old one). `CMakeLists.txt` generates the face arrays at build time with `c/bench/mkface.py` (not committed);
`-DSVF_FACE_ASCII=` / `-DSVF_FACE_HANGUL=` pick other faces for colour and grey, `-DSVF_FACE=` another 16 px 1 bpp
face for mono.

The `.uf2`: SDK 2.x makes it with picotool. Its CMake looks for an installed picotool CMake package
(`find_package(picotool CONFIG)`: `cmake --install` of a picotool build, or `-Dpicotool_DIR=<dir with picotoolConfig.cmake>`;
a `picotool` binary on the PATH alone is not found) and fetches and builds picotool from git when there is none. The
check builds pass `-DPICO_NO_PICOTOOL=1`, which skips picotool and produces the `.elf` only; configure without that option
for the `.uf2`, or convert by hand with a picotool you have:

    picotool uf2 convert build-pico-colour/svf_pico_colour.elf build-pico-colour/svf_pico_colour.uf2 --family rp2040 --platform rp2040

Modules assumed (written to the datasheets and the usual breakout boards; not tried on a panel), and the one byte to
change for the common variant:

- ST7789, 240 x 240: init `MADCTL` (`0x36`) with `0x00` (normal orientation, RGB order) and `INVON` (`0x21`, the
  usual IPS modules). A BGR module wants `0x08` for the `0x36` parameter; a module that shows inverted colours wrong
  wants `0x20` (`INVOFF`) in place of `0x21`. Many 240 x 240 modules show rows 80 to 319 of the controller's 240 x 320 RAM when
  `MADCTL` has MY set (`0xC0`, the 180-degree rotation): then the `RASET` start and end are 80 higher; with the `0x00` used here
  the window starts at row 0 and nothing is added.
- SSD1327, 128 x 128: remap `0xA0` with `0x51` (bit 0 column address remap set, bit 1 nibble remap clear: the left
  pixel of a pair is the high nibble, the order `grey_pack_rows` packs; bit 4 COM remap, bit 6 odd/even split). A module
  that shows each pair of pixels swapped wants `0x53` in that one parameter.
- SSD1306, 128 x 64: segment remap and COM scan `0xA1`, `0xC8` ((0, 0) at the top left on the usual modules).

XIP cache caveat: the colour and grey images put 74,660 bytes of faces in flash behind the RP2040's 16 KB XIP cache
(the mono image: 10,124 bytes of face, 35,484 of text in the built image). Neither rp2040js nor the bench models that cache, so real drawing times are the emulated
ones or slower, by an amount nothing here measures (`c/bench/MEASUREMENTS.md`).

Licences: the images embed font software ([FACES.md](../FACES.md) names each face's source, copyright and licence). A distributed image must carry `c/ports/FACES.md` and the licence texts
(`svf/dos/OFLPAPLG.TXT`, `svf/dos/OFL.TXT`, `svf/dos/NEODGM.TXT`); configuring copies them to
`<build>/licences/`, with the repository's `LICENSE` (the code's MIT licence) as `LICENSE-MIT.txt`.

## What was checked

The hardware has not been run. Per profile:

| | colour (ST7789) | grey (SSD1327) | mono (SSD1306) |
|---|---|---|---|
| host checks (`sh c/ports/check/host-checks.sh`: the real `profile_<p>.c` through a recording `display_show`, compared with `c/ports/check/screen_ref.py`; the driver command streams against recording stubs) | yes | yes | yes |
| builds against the real pico-sdk 2.3.1 (`-DPICO_NO_PICOTOOL=1`, `sh c/ports/check/test_pico_cmake.sh` checks the configure rules when `PICO_SDK_PATH` is set) | yes | yes | yes |
| runs under rp2040js on the panel model (`sh c/ports/check/run-screens.sh`): panel memory identical to the reference, ends at `svf_port_idle` | yes: 15 shows, 280.6 ms emulated | yes: 1 show, 13.9 ms emulated | yes: 1 show, 2.6 ms emulated |
| links for the Cortex-M0+ against `stub/` (`c/cross/build-all.sh --ports`), text without faces (`c/cross/SIZES.md`) | 9,646 bytes | 9,486 | 9,554 |
| pico-sdk 2.3.1 image, Pico (`arm-none-eabi-size`, Release; the embedded faces included; measured 2026-11-22 from a clean `git archive`) | text 99,828, data 0, bss 12,812 | text 99,256, data 0, bss 17,936 | text 35,484, data 0, bss 2,384 |
| the same for the Pico 2 (`-DPICO_BOARD=pico2`) | text 98,176, data 0, bss 12,428 | text 97,420, data 0, bss 17,552 | text 33,636, data 0, bss 2,000 |
| only built, not run: timing, voltages, panel variants, pin mapping, the `.uf2` step | yes | yes | yes |

The times in the third row are rp2040js's emulated clock (`nanos`) for the whole image run, including the SDK start-up and
the panel's init delays (`sleep_ms`, 242 ms of the colour image's 280.6 ms), not a drawing time and not a measurement of a Pico;
the instruction-cycle counter (`cycles`, in `c/bench/MEASUREMENTS.md`, "Screens") is a different figure. The PNGs of the panels are written to `c/build/screens/pico-<profile>.png` by
`run-screens.sh` (not committed). `c/cross/build-all.sh --ports` runs the host checks, `run-screens.sh`,
`test_pico_screen.sh` and the unit tests of `c/ports/check`, and prints 43 `OK` lines: 14 ports + 19 `port-check-*` +
5 `screen-*` + `pico-screen-negative` + `run-screens-gates` + 3 unit tests (`port-check-unit-*`). The stub links'
sizes are the Pico rows of the "Port examples" table of `c/cross/SIZES.md`; the pico-sdk links' sizes are its "Pico SDK
images" table, which `run-screens.sh` compares with what it measures.

Speed: `c/bench/MEASUREMENTS.md` has the Pico bench per target kind (emulated, rp2040js).
