#!/bin/sh
# run-esp32-hw.sh [OUT] - times c/bench/bench.c (GRAY8 build: the 1 bpp rows syl_ga, syl_bwelk, screen32, line8 and the
# 2 bpp aa_* rows) on a REAL ESP32-S3 (DevKitC-1 on PORT, default /dev/ttyUSB0) with the CCOUNT cycle counter, for
# SVF_GRAY8_LUT1=0 and 1 at -Os and -O2. Not part of the automatic gates: it needs the board, ESP-IDF v5.5.6 and flashes it
# (the board's own firmware is gone afterwards; restore it: cd $OLED_DIR && idf.py -p PORT flash).
#   export UV_PYTHON_INSTALL_DIR=$UVPY IDF_TOOLS_PATH=$OPT/espressif PATH=$UVPY/cpython-3.12-linux-x86_64-gnu/bin:$PATH
#   . $OPT/esp-idf-v5.5.6/export.sh; sh c/bench/run-esp32-hw.sh
# Environment: OPT (default ~/opt), UVPY (the uv-managed Python, default $OPT/uv-python), OLED_DIR (the board's own firmware
# project to restore; no default, only printed in the restore hint), PORT, XT, FACE*.
# The library and bench.c are compiled with the pinned xtensa-esp-elf gcc 16.1 (the compiler of run-esp32.sh's rows) into a
# static library, linked into a minimal IDF app (c/bench/esp32hw/main) at 240 MHz; bench.c is edited by sed in OUT only:
# rsr.icount -> rsr.ccount, no calibration, fflush(NULL), idle instead of exit. Code runs from flash through the 32 KB
# instruction cache as in an IDF app. "cycles" are CCOUNT ticks of core 0 (FreeRTOS tick interrupts included, 100 Hz).
# Each configuration is run twice (a reset in between); the expected checksums are sums.inc.sh's SUMS_GRAY8. Exit 0 when
# every row of every run has the expected checksum; non-zero (and a message) if a run is cut short (no end= line), a case of
# SUMS_GRAY8 is missing, a checksum is wrong, or the sed edits of bench.c did not take effect.
set -u
HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}
UVPY=${UVPY:-$OPT/uv-python}
OLED_DIR=${OLED_DIR:-<your-board-firmware-project>}
OUT=${1:-$C/build/bench/esp32hw}
PORT=${PORT:-/dev/ttyUSB0}
XT=${XT:-$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf}
FACE=${FACE:-$(dirname "$C")/svf/dos/NEODG16G.SVF}
FACE16=${FACE16:-$(dirname "$C")/svf/dos/PAPLG16.SVF}
FACE18=${FACE18:-$(dirname "$C")/svf/dos/PAPLG18.SVF}
. "$HERE/sums.inc.sh"
[ -n "${IDF_PATH:-}" ] || { echo "esp32hw: export the ESP-IDF environment first (see the header)"; exit 1; }
mkdir -p "$OUT" || exit 1
python3 -I "$HERE/mkface.py" "$FACE" "$OUT/face.c" --profile mcu-strict || exit 1
python3 -I "$HERE/mkface.py" "$FACE16" "$OUT/face16.c" --name bench_face16 --profile mcu-strict || exit 1
python3 -I "$HERE/mkface.py" "$FACE18" "$OUT/face18.c" --name bench_face18 --profile mcu-strict || exit 1
sed -e 's/rsr\.icount/rsr.ccount/' -e 's/^\tbench_calibrate();$//' -e 's/fflush(stdout)/fflush(NULL)/' \
	-e 's/^static void bench_exit(int code) { exit(code); }$/static void bench_exit(int code) { (void)code; for (;;) __asm__ volatile("nop"); }/' \
	"$HERE/bench.c" > "$OUT/bench_hw.c" || exit 1
# the edits must have taken effect (bench.c changed under them: refuse rather than time the wrong thing)
if grep -q 'rsr\.icount %0' "$OUT/bench_hw.c" || grep -q '^[[:space:]]*bench_calibrate();$' "$OUT/bench_hw.c" ||
	grep -q 'bench_exit(int code) { exit(code); }' "$OUT/bench_hw.c" || ! grep -q 'rsr\.ccount' "$OUT/bench_hw.c" || ! grep -q 'for (;;) __asm__' "$OUT/bench_hw.c"; then
	echo "esp32hw: the sed edits of bench.c did not take effect (ICOUNT timing, calibration or exit() remain): bench.c changed, update this script"
	exit 1
fi
status=0
for opt in -Os -O2; do
	for lut in 0 1; do
		tag=lut$lut$opt
		d=$OUT/$tag
		mkdir -p "$d/obj"
		rm -f "$d/obj"/*.o "$d/libbench.a"
		for f in "$OUT/bench_hw.c" "$C"/src/*.c "$OUT/face.c" "$OUT/face16.c" "$OUT/face18.c"; do
			"$XT-gcc" -std=gnu99 -Wall -Wextra -ffunction-sections -fdata-sections -mlongcalls $opt \
				-DSVF_NO_SCALE -DSVF_TARGETS=0x01 -DSVF_GRAY8_LUT1=$lut -DBENCH_ESP32S3 -DBENCH_ICOUNT_SHIFT=5 \
				-DBENCH_KIND=SVF_T_GRAY8 -Dmain=bench_main -I "$C/ports" -I "$C/include" -I "$HERE" -c "$f" \
				-o "$d/obj/$(basename "$f" .c).o" || { echo "esp32hw: build failed ($tag)"; exit 1; }
		done
		"$XT-ar" rcs "$d/libbench.a" "$d"/obj/*.o || exit 1
		idf.py -C "$HERE/esp32hw" -B "$d/idf" -DBENCH_LIB="$d/libbench.a" -DSDKCONFIG="$d/sdkconfig" \
			-DSDKCONFIG_DEFAULTS="$HERE/esp32hw/sdkconfig.defaults" -p "$PORT" build flash > "$d/idf.log" 2>&1 ||
			{ echo "esp32hw: build/flash failed ($tag), see $d/idf.log"; exit 1; }
		for run in 1 2; do
			python3 - "$PORT" "$d/run$run.txt" "$run" <<'P'
import serial, sys, time
s = serial.Serial(sys.argv[1], 115200, timeout=1)
if sys.argv[3] != "1":  # reset through the board's auto-reset circuit (EN low), boot the app again
    s.dtr = False
    s.rts = True
    time.sleep(0.2)
    s.rts = False
end = time.time() + 240
buf = b""
while time.time() < end and b"end=" not in buf:
    buf += s.read(4096)
open(sys.argv[2], "wb").write(buf)
P
			awk -v tag="$tag" -v run="$run" -v sums="$SUMS_GRAY8" '
				BEGIN { n = split(sums, a, " "); for (i = 1; i <= n; i++) { split(a[i], kv, ":"); want[kv[1]] = kv[2] } }
				/^case=/ { split($1, c, "="); name = c[2]; sum = ""; cyc = ""; per = ""
					for (i = 2; i <= NF; i++) { split($i, kv, "="); if (kv[1] == "sum") sum = kv[2]; if (kv[1] == "per_iter_cycles") per = kv[2] }
					got[name] = 1; ok = (name in want) ? (want[name] == sum ? "ok" : "BAD") : "-"
					if (ok == "BAD") bad = 1
					printf "| %s | run%s | %s | %s | %s |\n", tag, run, name, per, ok; seen++ }
				/^end=/ { ended = 1 }
				END { for (k in want) if (!(k in got)) { print "esp32hw: " tag " run" run ": case " k " missing" > "/dev/stderr"; bad = 1 }
					if (!ended) { print "esp32hw: " tag " run" run ": no end= line (run cut short)" > "/dev/stderr"; bad = 1 }
					if (!seen || bad) exit 1 }' "$d/run$run.txt" || status=1
		done
	done
done
exit $status
