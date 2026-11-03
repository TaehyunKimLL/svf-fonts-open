#!/bin/sh
# run-esp32.sh [OUT] - runs c/bench/bench.c on an emulated ESP32-C3 (RV32IMC) and ESP32-S3 (Xtensa LX7) under
# Espressif's QEMU 9.2.2 (esp_develop) and prints Markdown table rows (report.awk). Nothing here is cycle-accurate:
# QEMU is a translator, and what each number is, is said in the build string of its rows and in MEASUREMENTS.md.
#   ESP32-C3  -M esp32c3 -icount shift=0,sleep=off: rdinstret before and after each case, the number of guest
#             instructions executed (exception handlers included; no pipeline, memory, cache or flash timing). One
#             instruction per cycle at most, so instructions / 160 MHz is a LOWER BOUND of the time on a C3.
#   ESP32-S3  -M esp32s3 -icount shift=5,sleep=off: the Xtensa ICOUNT register of core 0 before and after each case
#             (instructions completed by that core; it excludes a few hundred instructions of a long case that a full
#             trace shows, see MEASUREMENTS.md). Not CCOUNT: under -icount CCOUNT is the global virtual clock (25 ns a
#             tick, 32 ns an instruction at shift 5, so one instruction is 1.28 ticks), which also advances for
#             the APP CPU (core 1) that this QEMU cannot park and that spins in the ROM, by a layout-dependent amount.
#             The us column is instructions / 240 MHz, a lower bound of the time on a real S3 (not cycles).
# The "cycles" column holds those instruction counts. Both are deterministic: a repeat run gives the same numbers.
# Before the cases the S3 build prints a calibration (check-esp32-cal.sh): 1,000 NOPs read 1280 +- 2 CCOUNT ticks, and
# four loops of 1,000,000 instructions read 1,000,000 +- 0.1 % of ICOUNT (the end-to-end check of the measurement); the
# run fails otherwise.
#
# Twelve builds (chip x {MONO_PAGE, GRAY8, RGB565} x {-Os, -O2}), the library with -DSVF_NO_SCALE -DSVF_TARGETS=<bit>
# as the size table builds it; the iteration counts are the Pico's (100 / 20 / 5; bench.c), a run takes seconds. The
# face arrays come from mkface.py as in run-pico.sh and the expected checksums from sums.inc.sh (kept equal to sums.py
# by TestBenchSums); with another FACE, FACE16 or FACE18 sums.py computes them. Both installs (compilers and QEMU) are
# verified first, and must be present. Each QEMU runs under guard.py: a time limit (LIMIT seconds, default 600), output
# capped (1 MiB stdout, 64 KiB stderr), killed on TERM/INT/HUP of this script and when it dies. There are no budgets here.
# Exit status: 0 every run finished with the expected checksums, 1 a run, a checksum or the calibration failed.
# Build and raw output go to OUT (default c/build/bench/esp32). RV, XT (compiler prefixes), QEMU_RV and QEMU_XT override the
# pinned tools: an override is run unverified and printed as "esp32: note: unpinned VAR=value".
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/esp32}
FACE=${FACE:-$(dirname "$C")/svf/dos/NEODG16G.SVF}
FACE16=${FACE16:-$(dirname "$C")/svf/dos/PAPLG16.SVF}
FACE18=${FACE18:-$(dirname "$C")/svf/dos/PAPLG18.SVF}
RV=${RV:-$OPT/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf}
XT=${XT:-$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf}
QEMU_RV=${QEMU_RV:-$OPT/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32}
QEMU_XT=${QEMU_XT:-$OPT/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa}
LIMIT=${LIMIT:-600} # seconds a QEMU run may take (the runs take seconds)

. "$HERE/sums.inc.sh" # SUMS_<kind>: the expected checksums
. "$HERE/guard.sh" # run_guarded OUT ERR CMD...: QEMU under guard.py, killed with this script; verify_ok, guard_why
# an override of a compiler or QEMU runs, unverified, under the pinned versions' row labels: said so
note_unpinned esp32 RV "$OPT/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf"
note_unpinned esp32 XT "$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf"
note_unpinned esp32 QEMU_RV "$OPT/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32"
note_unpinned esp32 QEMU_XT "$OPT/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa"
verify_ok esp32 "$C/cross/install-toolchains.sh" esp xtensa
verify_ok esp32 "$HERE/install-emulators.sh" qemu-rv qemu-xt
sums_for_faces esp32 "$(dirname "$C")" # faces other than the defaults have other checksums

mkdir -p "$OUT" || exit 1
python3 -I "$HERE/mkface.py" "$FACE" "$OUT/face.c" --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE16" "$OUT/face16.c" --name bench_face16 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE18" "$OUT/face18.c" --name bench_face18 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
rvver=$("$RV-gcc" -dumpfullversion) || exit 1
xtver=$("$XT-gcc" -dumpfullversion) || exit 1
status=0

# run_qemu TAG QEMU ARGS...: the emulator under guard.py; the raw output in OUT/run-TAG.txt and .err.
run_qemu() {
	_tag=$1
	shift
	run_guarded "$OUT/run-$_tag.txt" "$OUT/run-$_tag.err" "$@"
}

for kind in "MONO_PAGE 0x02" "GRAY8 0x01" "RGB565 0x08"; do
	set -- $kind
	name=$1 bit=$2
	eval "SUMS=\$SUMS_$name"
	[ -n "$SUMS" ] || { echo "esp32: no sums for $name"; exit 1; }
	for opt in -Os -O2; do
		# ESP32-C3
		tag=c3$opt-$name
		# shellcheck disable=SC2086
		"$RV-gcc" -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
			-march=rv32imc_zicsr_zifencei -mabi=ilp32 $opt -DSVF_NO_SCALE -DSVF_TARGETS=$bit -DBENCH_ESP32C3 \
			-DBENCH_KIND=SVF_T_$name -I "$C/ports" -I "$C/include" "$HERE/bench.c" "$C"/src/*.c "$OUT/face.c" \
			"$OUT/face16.c" "$OUT/face18.c" -specs=esp32c3.qemu.specs -Wl,--gc-sections -o "$OUT/bench-$tag.elf" ||
			{ echo "esp32: build failed ($tag)"; exit 1; }
		run_qemu "$tag" "$QEMU_RV" -M esp32c3 -nographic -monitor none -serial stdio -semihosting \
			-icount shift=0,sleep=off -kernel "$OUT/bench-$tag.elf"
		q=$?
		awk -v build="ESP32-C3 emulated (QEMU 9.2.2 esp_develop, -M esp32c3 -icount shift=0: instructions (rdinstret), lower bound; riscv32-esp-elf-gcc $rvver $opt; $name, SVF_TARGETS=$bit)" \
			-v mhz=160 -v sums="$SUMS" -v exact=1 -f "$HERE/report.awk" "$OUT/run-$tag.txt"
		s=$?
		if [ $s -ne 0 ] || [ $q -ne 0 ]; then
			echo "esp32: run failed ($tag: qemu exit $q$([ $q -eq 0 ] || echo " ($(guard_why $q))"), report exit $s), see $OUT/run-$tag.txt"
			status=1
		fi

		# ESP32-S3
		tag=s3$opt-$name
		# shellcheck disable=SC2086
		"$XT-gcc" -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -mlongcalls $opt \
			-DSVF_NO_SCALE -DSVF_TARGETS=$bit -DBENCH_ESP32S3 -DBENCH_ICOUNT_SHIFT=5 -DBENCH_KIND=SVF_T_$name \
			-I "$C/ports" -I "$C/include" "$HERE/bench.c" "$C"/src/*.c "$OUT/face.c" "$OUT/face16.c" "$OUT/face18.c" \
			-specs=sys.qemu.specs -specs=sim.elf.specs -Wl,--defsym=entire_dram_seg=1 -Wl,--gc-sections \
			-o "$OUT/bench-$tag.elf" || { echo "esp32: build failed ($tag)"; exit 1; }
		run_qemu "$tag" "$QEMU_XT" -M esp32s3 -nographic -monitor none -serial stdio -semihosting \
			-icount shift=5,sleep=off -kernel "$OUT/bench-$tag.elf"
		q=$?
		if ! sh "$HERE/check-esp32-cal.sh" "$OUT/run-$tag.txt" 4; then
			echo "esp32: calibration failed ($tag), see $OUT/run-$tag.txt"
			status=1
		fi
		awk -v build="ESP32-S3 emulated (QEMU 9.2.2 esp_develop, -M esp32s3 -icount shift=5: ICOUNT of core 0, instructions; xtensa-esp32s3-elf-gcc $xtver $opt; $name, SVF_TARGETS=$bit)" \
			-v mhz=240 -v sums="$SUMS" -v exact=1 -f "$HERE/report.awk" "$OUT/run-$tag.txt"
		s=$?
		if [ $s -ne 0 ] || [ $q -ne 0 ]; then
			echo "esp32: run failed ($tag: qemu exit $q$([ $q -eq 0 ] || echo " ($(guard_why $q))"), report exit $s), see $OUT/run-$tag.txt"
			status=1
		fi
	done
done
exit $status
