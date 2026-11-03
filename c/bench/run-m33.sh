#!/bin/sh
# run-m33.sh [OUT] - runs c/bench/bench.c on an emulated Cortex-M33 (RP2350's Arm core) under QEMU 8.2.2 -M mps2-an505
# and prints Markdown table rows (report.awk). Nothing here is cycle-accurate or an RP2350 cycle count:
#   -icount shift=0,sleep=off: virtual time runs one instruction to the nanosecond, so one SysTick tick of the 20 MHz
#   processor clock is exactly 50 instructions executed. The program reads SysTick (bench_now in bench.c; ticks x 50)
#   before and after each case: the number of guest instructions executed between the two reads, a granularity of 50
#   instructions per interval. No pipeline, memory, cache or flash timing, no wait states: not RP2350 cycles. The us
#   column is instructions / 150 MHz, the RP2350's default clock: the time at one instruction per cycle, an ESTIMATE and
#   not a bound. Taken branches, loads and multi-cycle operations make the chip slower than that, and the M33's limited
#   dual issue can make short stretches faster. There is no budget.
# The program prints through ARM semihosting (SYS_WRITE0); a bare -semihosting sends that to QEMU's stderr, so the
# console is a chardev on stdio (-chardev stdio,id=semi -semihosting-config enable=on,chardev=semi) and the rows come
# from stdout as with the other runners.
# BENCH_CFLAGS (environment, words split) adds compiler flags to every build, e.g. BENCH_CFLAGS=-DSVF_SMALL: the checksums do not move.
# The "cycles" column holds those instruction counts. They are deterministic: a repeat run gives the same numbers.
# Before the cases every build prints a calibration line, cal=loop2m ticks=T insns=I, for a loop of 1,000,000 x (subs,
# bne) = 2,000,000 instructions: T is the raw SysTick difference, I the advance of bench_now(), the clock every row uses.
# The run fails unless there is exactly one such line, |I - T * 50| <= 100 (the two agree) and |I - 2,000,000| <= 100 (the
# instruction rate holds: the end-to-end check of the measurement).
#
# Eight builds: {MONO_PAGE 0x02, GRAY8 0x01, RGB565 0x08} x {-Os, -O2} with the library as the size table builds it
# (-DBENCH_MCU -DSVF_NO_SCALE -DSVF_TARGETS=<bit>), and the line cases (bench.c without BENCH_MCU, the default
# SVF_TARGETS, scaling in, faces 16 and 18) at -Os and -O2. The line cases print reads_per_iter with a float printf
# (-u _printf_float: newlib-nano prints an empty value without it); that call is outside every timed interval. The
# iteration counts are 100 / 20 / 20 (bench.c), a run takes seconds. The face arrays come from mkface.py as in
# run-pico.sh and the expected checksums from sums.inc.sh (kept equal to sums.py by TestBenchSums); with another FACE,
# FACE16 or FACE18 sums.py computes them. The compiler and the QEMU install are verified first, and must be present.
# QEMU runs under guard.py: a time limit (LIMIT seconds, default 600), output capped (1 MiB stdout, 64 KiB stderr),
# killed on TERM/INT/HUP of this script and when it dies.
# Exit status: 0 every run finished with the expected checksums and the calibration held, 1 a run, a checksum or the
# calibration failed.
# Build and raw output go to OUT (default c/build/bench/m33): bench-<opt>-<NAME>.elf, build-<opt>-<NAME>.log (the compiler's
# output: libnosys' "is not implemented" link warnings, shown only when a build fails), run-<opt>-<NAME>.txt (opt Os or
# O2; NAME MONO_PAGE, GRAY8, RGB565 or LINE) and .err. ARM (compiler prefix) and QEMU_ARM override the pinned tools: an
# override is run unverified and printed as "m33: note: unpinned VAR=value".
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/m33}
FACE=${FACE:-$(dirname "$C")/svf/dos/NEODG16G.SVF}
FACE16=${FACE16:-$(dirname "$C")/svf/dos/PAPLG16.SVF}
FACE18=${FACE18:-$(dirname "$C")/svf/dos/PAPLG18.SVF}
ARM=${ARM:-$OPT/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi}
QEMU_ARM=${QEMU_ARM:-$OPT/qemu-system-arm-8.2.2-0ubuntu1.18/usr/bin/qemu-system-arm}
LIMIT=${LIMIT:-600} # seconds a QEMU run may take (the runs take seconds)

. "$HERE/sums.inc.sh" # SUMS_<kind>: the expected checksums
. "$HERE/guard.sh" # run_guarded OUT ERR CMD...: QEMU under guard.py, killed with this script; verify_ok, guard_why
note_unpinned m33 ARM "$OPT/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi"
note_unpinned m33 QEMU_ARM "$OPT/qemu-system-arm-8.2.2-0ubuntu1.18/usr/bin/qemu-system-arm"
verify_ok m33 "$C/cross/install-toolchains.sh" arm
verify_ok m33 "$HERE/install-emulators.sh" qemu-arm
sums_for_faces m33 "$(dirname "$C")" # faces other than the defaults have other checksums

mkdir -p "$OUT" || exit 1
python3 -I "$HERE/mkface.py" "$FACE" "$OUT/face.c" --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE16" "$OUT/face16.c" --name bench_face16 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE18" "$OUT/face18.c" --name bench_face18 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
armver=$("$ARM-gcc" -dumpfullversion) || exit 1
status=0

for kind in "MONO_PAGE 0x02" "GRAY8 0x01" "RGB565 0x08" "LINE -"; do
	set -- $kind
	name=$1 bit=$2
	case $name in
	MONO_PAGE) SUMS=$SUMS_MONO_PAGE ;;
	GRAY8) SUMS=$SUMS_GRAY8 ;;
	RGB565) SUMS=$SUMS_RGB565 ;;
	LINE) SUMS=$SUMS_LINE40 ;;
	esac
	[ -n "$SUMS" ] || { echo "m33: no sums for $name"; exit 1; }
	if [ "$name" = LINE ]; then
		mask="default"
	else
		mask=$bit
	fi
	for o in Os O2; do
		tag=$o-$name
		if [ "$name" = LINE ]; then
			set -- -DBENCH_M33 -u _printf_float "$OUT/face16.c" "$OUT/face18.c"
		else
			set -- -DBENCH_M33 -DBENCH_MCU -DSVF_NO_SCALE "-DSVF_TARGETS=$bit" "-DBENCH_KIND=SVF_T_$name" \
				"$OUT/face.c" "$OUT/face16.c" "$OUT/face18.c"
		fi
		"$ARM-gcc" -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -mcpu=cortex-m33 -mthumb "-$o" \
			${BENCH_CFLAGS:-} "$@" -I "$C/include" "$HERE/bench.c" "$C"/src/*.c -T "$HERE/m33.ld" --specs=nano.specs \
			--specs=nosys.specs -nostartfiles -Wl,--gc-sections -Wl,--no-warn-rwx-segments -o "$OUT/bench-$tag.elf" >"$OUT/build-$tag.log" 2>&1 ||
			{ cat "$OUT/build-$tag.log"; echo "m33: build failed ($tag)"; exit 1; }
		run_guarded "$OUT/run-$tag.txt" "$OUT/run-$tag.err" "$QEMU_ARM" -M mps2-an505 -chardev stdio,id=semi \
			-semihosting-config enable=on,chardev=semi -icount shift=0,sleep=off -nographic -monitor none -serial none -kernel "$OUT/bench-$tag.elf"
		q=$?
		if ! awk '/^cal=/ { if ($0 ~ /^cal=loop2m ticks=[0-9]+ insns=[0-9]+$/) { n++; split($0, a, /[= ]/); t = a[4]; i = a[6] } else bad = 1 }
		          END { d = i - 2000000; if (d < 0) d = -d; e = i - t * 50; if (e < 0) e = -e; exit !(n == 1 && !bad && e <= 100 && d <= 100) }' "$OUT/run-$tag.txt"; then
			echo "m33: calibration failed ($tag), see $OUT/run-$tag.txt"
			status=1
		fi
		awk -v build="Cortex-M33 emulated (QEMU 8.2.2 mps2-an505 -icount shift=0: SysTick ticks x 50 = instructions, not RP2350 cycles; arm-none-eabi-gcc $armver -$o; $name, SVF_TARGETS=$mask)" \
			-v mhz=150 -v sums="$SUMS" -v exact=1 -f "$HERE/report.awk" "$OUT/run-$tag.txt"
		s=$?
		if [ $s -ne 0 ] || [ $q -ne 0 ]; then
			echo "m33: run failed ($tag: qemu exit $q$([ $q -eq 0 ] || echo " ($(guard_why $q))"), report exit $s), see $OUT/run-$tag.txt"
			status=1
		fi
	done
done
exit $status
