# Arduino Uno example (SSD1306 over I2C, face in PROGMEM)

`arduino.ino` draws four lines of Korean and ASCII on a 128 x 64 SSD1306 OLED. The face, `svf/dos/NEODG16G.SVF`
(16 px 1 bpp jamo, 10.1 KB in the `mcu-strict` layout), stays in flash (PROGMEM): the library is built with `-DSVF_TARGETS=0x02` (MONO_PAGE only), `-DSVF_NO_STREAM` (no stream reader: this sketch opens the face mapped; `svf_open_stream`, `svf_stream_tables_size` and `svf_stream_reads` are then not declared, so a sketch that calls them does not compile: drop the switch to stream a face), `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` (the library reads only the face layout `mkface.py --profile mcu-strict` writes; 23,676 bytes of text with this face, the `arduino` row of `c/cross/SIZES.md`) and with `-DSVF_RD8(p)=pgm_read_byte(p)`, so
every read of the face goes through `pgm_read_byte`. The text lines are in PROGMEM too. The MONO_PAGE target draws into
a 128 x 64 page buffer in the SSD1306's layout: **1 KB, half of the Uno's 2 KB of RAM.** Wire sends 32 bytes a
transmission, so the frame goes out 16 bytes at a time. Wiring: SDA A4, SCL A5, display address 0x3C.

Build with arduino-cli (from the repository root; the library goes in as an Arduino library, the face array is
generated into the sketch folder, `face.c`, not committed):

    mkdir -p ~/Arduino/libraries/svf && cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
    python3 c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
    F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
    arduino-cli compile -b arduino:avr:uno c/ports/arduino \
        --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"

`-DSVF_JSET_V2=0` (also svf.h's AVR default, spelled out here) builds only the JSET version 1 reader: NEODG16G's small
jamo set is a version 1 block, and adding the version 2 reader would cost about 2.4 KB of flash (P1 in
`c/cross/SIZES.md` "Size switches") that this sketch does not need (a version 2 face then opens as a plain face, without
syllables). `SVF_JMAP` (the version 3 reader) is 0 on AVR by default and stays off here: a version 3 face opens through its
JSET fallback, or as a plain face.

The flags go to the C and C++ compiles only (`compiler.c.extra_flags`, `compiler.cpp.extra_flags`), not to
`build.extra_flags`: the AVR core's recipes pass `build.extra_flags` to its assembler sources (`.S`) too, and
`-include avr/pgmspace.h` there feeds C declarations to the assembler, which fails. The shell's single quotes keep the
value whole; the double quotes inside are for arduino-cli, which splits a recipe into arguments itself (no shell), so
the macro with its parentheses stays one argument, `-DSVF_RD8(p)=pgm_read_byte(p)`.

(In the Arduino IDE, put the same flags, double quotes included, in `compiler.c.extra_flags` and
`compiler.cpp.extra_flags` of a `platform.local.txt` next to the AVR core's `platform.txt`.)

What was checked: no Arduino core or arduino-cli is installed here, so neither command above has been run against a
real arduino-cli build, and the sketch has not been built with arduino-cli or run.
`c/cross/build-all.sh --ports` compiles the library and the generated face with avr-gcc 16.1.0 (`-mmcu=atmega328p
-Os`, the flags above), compiles `arduino.ino` as C++ against `stub/` (no-op stand-ins for `Wire` and the core's
`main`) and links them: the SVF side (PROGMEM face, `svf_open_mapped`, chain, `svf_target_init`, `svf_draw_utf8` into
the page buffer) compiles and links for the ATmega328P; the Wire and SSD1306 code is written to the Arduino API and is
unverified. That link: 23,694 bytes of flash (text 23,676 + data 18; a cross build against `stub/`, not the arduino-cli build) (of 32 KB; the face 10,124), 1,103 bytes of RAM before the stack (the page
buffer 1,024). The real Wire library adds its buffers (about 200 bytes) and the core a few dozen: about 700 bytes stay
for the stack.
This sketch is built with `-DSVF_NO_SCALE`. A sketch that scales (`scale_num`/`scale_den` other than 1/1) must also budget the stack of the scaler: `svf__scale_cell` has a 610 B frame and a scaled `svf_draw_utf8` peaks at about 864 B of stack on the ATmega328P (+413 B over the unscaled path), which does not fit beside the page buffer in 2 KB. Build with `-DSVF_SCALE_FAST=0` (or `-DSVF_SMALL`) for the direct scaler, whose peak is 451 B (measured statically with `c/cross/stack-usage.py`; see `c/cross/SIZES.md` "Size switches").

## Mega 2560

The same sketch and face also link for the ATmega2560 (Arduino Mega, 256 KB of flash): `c/cross/build-all.sh --ports` builds them with `-mmcu=atmega2560` and the Uno flags (flash 23,820 B) and, as a second row, with every target and reader (`-DSVF_TARGETS=0x1FF -DSVF_JSET_V2=1 -DSVF_JMAP=1 -DSVF_JSET_BIG=1`, flash 40,508 B); `c/cross/SIZES.md` "Port examples" has the rows `arduino-mega` and `arduino-mega-rich`. This is a build only: no Mega board or emulator run, and arduino-cli is not used (`-b arduino:avr:mega` with the same flags is untested). The face data stays in PROGMEM below 64 KB, read by the near `pgm_read_byte`; faces or data above 64 KB need far reads, which are out of scope (not supported, not tested). The build prints a `FLAG` line when a Mega image's flash end reaches 65,536 B.
