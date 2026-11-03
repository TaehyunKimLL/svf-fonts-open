#!/bin/sh
# run-avr.sh [OUT] - times c/bench/bench.c on an emulated ATmega328P (Arduino Uno, 16 MHz) and prints Markdown table
# rows, then the Uno fit: the flash and RAM of the program, which links the library (P1 profile) with one 1 bpp jamo
# face in PROGMEM and draws with it. No speed budget applies to the Uno; the fit is the requirement.
#
# Emulator: simavr 1.8 (c/bench/install-emulators.sh) through c/bench/avr-run.c, a host program linked with libsimavr
# that reads simavr's cycle counter around each case; cycles are converted at 16 MHz. Built with avr-gcc 16.1.0 +
# AVR-LibC 2.3.2 (c/cross/install-toolchains.sh) with the P1 flags of c/cross/SIZES.md (-DSVF_NO_STREAM, -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT) except the target set: this
# bench draws GRAY8, MONO_ROW, RGB565 and the callback besides MONO_PAGE, so it builds with the five original kinds
# (-DSVF_TARGETS=0x1F), not P1's 0x02 and not the nine-kind default:
#   -mmcu=atmega328p -Os -include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)' -DSVF_NO_SCALE -DSVF_TARGETS=0x1F
# with AVR-LibC's startup code (a complete program, vectors included). Face: FACE (default
# svf/dos/NEODG16G.SVF, 16 px 1 bpp jamo, mcu-strict profile) in PROGMEM by c/bench/mkface.py; the expected checksums are
# the default face's.
#
# Build and raw output go to OUT (default c/build/bench/avr). Exit status: report.awk's (0 ok, 1 a failure), or 1 if
# the program does not fit 32,256 bytes of flash (32 KB less a 512-byte Optiboot) or 2,048 bytes of RAM.
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/avr}
FACE=${FACE:-$(dirname "$C")/svf/dos/NEODG16G.SVF}
AVR=$OPT/avr-gcc-16.1.0/bin/avr
SIMAVR=$OPT/simavr-1.8
CFLAGS="-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -mmcu=atmega328p -Os"
CFLAGS="$CFLAGS -include avr/pgmspace.h -DSVF_RD8(p)=pgm_read_byte(p) -DSVF_NO_SCALE -DSVF_TARGETS=0x1F -DBENCH_AVR"
# the strict, mapped-only build: the stream reader left out, one layout read. BENCH_LAYOUTS, a test hook, overrides the
# layout switch: empty builds without it, a comma list of hex SVF_LAYOUT codes (0x202 is mcu-strict) builds with
# -DSVF_LAYOUTS=that list, anything else is refused (exit 2). The layout_probe case then reports the build's layouts:
# its expected sum stays the strict build's whatever the build, so an override other than 0x202 fails the run.
if [ "${BENCH_LAYOUTS+set}" != set ]; then
	LAYOUTS=-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT
elif [ -z "$BENCH_LAYOUTS" ]; then
	LAYOUTS=
elif printf '%s\n' "$BENCH_LAYOUTS" | grep -Eqx '0[xX][0-9a-fA-F]{1,4}(,0[xX][0-9a-fA-F]{1,4})*'; then
	LAYOUTS="-DSVF_LAYOUTS=$BENCH_LAYOUTS"
else
	echo "run-avr: BENCH_LAYOUTS must be empty or a comma list of hex layout codes (0x202): '$BENCH_LAYOUTS'" >&2
	exit 2
fi
CFLAGS="$CFLAGS -DSVF_NO_STREAM $LAYOUTS ${BENCH_CFLAGS:-}" # BENCH_CFLAGS: more flags, e.g. -DSVF_SMALL (checksums and fit are checked as usual)
. "$HERE/sums.inc.sh"
SUMS="syl_ga:64b1ad7b syl_bwelk:1aaf98c2 compose_bwelk:9b1093a3 screen32:f4079faf $SUMS_LAYOUT_STRICT"
FLASH_MAX=32256
RAM_MAX=2048

mkdir -p "$OUT" || exit 1
gcc -std=gnu99 -O2 -Wall -Wextra -Werror -I"$SIMAVR/include" "$HERE/avr-run.c" "$SIMAVR/lib/libsimavr.a" -lelf \
	-o "$OUT/avr-run" || { echo "avr: building avr-run failed"; exit 1; }
python3 -I "$HERE/mkface.py" "$FACE" "$OUT/face.c" --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
ver=$("$AVR-gcc" -dumpfullversion) || exit 1
# shellcheck disable=SC2086
"$AVR-gcc" $CFLAGS -I"$C/include" "$HERE/bench.c" "$C"/src/*.c "$OUT/face.c" -Wl,--gc-sections -o "$OUT/bench.elf" ||
	{ echo "avr: build failed"; exit 1; }
"$OUT/avr-run" "$OUT/bench.elf" >"$OUT/run.txt" 2>&1
awk -v build="Uno emulated (simavr 1.8, ATmega328P 16 MHz; avr-gcc $ver -Os)" -v mhz=16 -v sums="$SUMS" \
	-f "$HERE/report.awk" "$OUT/run.txt"
status=$?
[ $status -ne 0 ] && { echo "avr: run failed, see $OUT/run.txt"; status=1; }

# Flash: .text (vectors, code, the face) + .data's initial values; RAM: .data + .bss (the stack comes on top).
set -- $("$AVR-objdump" -h "$OUT/bench.elf" | awk '$2 == ".text" { t = $3 } $2 == ".data" { d = $3 }
	$2 == ".bss" { b = $3 } END { print t, d, b }')
flash=$((0x$1 + 0x$2)) ram=$((0x$2 + 0x$3)) face=$(sed -n 's/^const uint32_t bench_face_len = \([0-9]*\)u;$/\1/p' "$OUT/face.c")
echo
echo "Uno fit: flash $flash of $FLASH_MAX bytes (face $face, code and constants $((flash - face)));" \
	"RAM $ram of $RAM_MAX bytes before the stack"
[ $flash -le $FLASH_MAX ] && [ $ram -lt $RAM_MAX ] || { echo "avr: does not fit"; status=1; }
exit $status
