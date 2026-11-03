#!/bin/sh
# run-rp2350.sh [OUT] - times c/bench/bench.c as real pico-sdk 2.3.1 `pico2` images on rp2350js's RP2350, both cores (Hazard3
# and Cortex-M33), and prints Markdown table rows (report.awk). The numbers are rp2350js's cycles, not the chip's.
#
# What is built: per core one CMake configure of c/bench/rp2350 (pico-sdk's crt0, runtime init, linker script and
# IMAGE_DEF, -DPICO_BOARD=pico2, -DPICO_PLATFORM=rp2350-riscv with riscv32-pico-elf-gcc 16.1.0 for Hazard3, rp2350-arm-s with
# arm-none-eabi-gcc 15.2.1 for the Cortex-M33) and eight builds: {MONO_PAGE 0x02, GRAY8 0x01, RGB565 0x08} x {-Os, -O2} with the
# library as the size table builds it (-DBENCH_MCU -DSVF_NO_SCALE -DSVF_TARGETS=<bit>), and the line cases (no
# -DBENCH_MCU, the default SVF_TARGETS, scaling in, faces 16 and 18) at -Os and -O2. The face arrays come from mkface.py as in
# run-pico.sh, the expected checksums from sums.inc.sh (with another FACE, FACE16 or FACE18 sums.py computes them).
#
# How a count is taken: c/bench/rp2350-run.mjs (see its header) boots each ELF through the A2 boot ROM bundled in rp2350js and
# reads core 0's cycle counter at the first instruction of the marker functions bench.c calls around each case. A count
# holds a constant per interval (the marks' own cost: cal=empty, 7-8 cycles Hazard3, 11-12 Cortex-M33). Before the cases every
# build reports two calibration intervals, cal=empty (start, stop) and cal=loop1m (1,000,000 x two instructions whose cost
# rp2350js models exactly: Hazard3 addi 1 + predicted bnez 1, Cortex-M33 subs 1 + taken bne 2). The run fails ("rp2350:
# calibration failed") unless there is exactly one of each, 0 < E <= 32 cycles, |L - E - W| <= 16 with W 2,000,000 (Hazard3) or
# 3,000,000 (Cortex-M33), and |LI - EI - 2,000,000| <= 16 instructions: the end-to-end check of the measurement.
# The us column is cycles / 150, the SDK's clk_sys; rp2350js itself runs the chip at 125 MHz whatever the SDK programs, so no
# time is read from the emulated chip. Rows have no budget (the 8 KB and 50 us / 2 ms budgets are the Pico's).
#
# What rp2350js does not model: XIP flash and XIP cache timing (code and faces are in flash, as on a board), QMI, bus
# contention and APB wait states, Hazard3's dependent-register (load-use) penalty; timer and system interrupts and exceptions
# (the bench uses none; entering a fault handler ends the run). Its cycle counts are "somewhat correct" in its own words; the
# counts are an estimate that could be off in either direction: its timing tables are not checked against the chip. The Cortex-M33 rows are cycles of rp2350js's model; run-m33.sh
# (QEMU, instructions) stays as the instruction-count cross-check of them.
#
# c/bench/rp2350js.patch (four rp2350js fixes: the Cortex-M33 GPIO coprocessor decode, Zcmp cm.mvsa01 / cm.mva01s, Zbb orc.b and
# zip/unzip, sltiu) is applied when install-emulators.sh builds rp2350js; the install is verified here against its manifest pin.
# Without the three RISC-V fixes the Hazard3 images fail.
#
# CORES (default "riscv arm"; any other word: "rp2350: unknown core", exit 1) selects the cores, NODE overrides the pinned node
# v24 (run unverified and printed as "rp2350: note: unpinned NODE=value"), LIMIT (600) is the seconds a node run may take
# (guard.py), FACE / FACE16 / FACE18 the faces. The installs (arm, pico-rv, pico-sdk, rp2350js) are verified first and must
# be present; cmake must be on PATH. A run takes about 30 s.
# Exit status: 0 every build ran, every row is ok and every calibration held; 1 otherwise (no budget, so never 2).
# Build and raw output go to OUT (default c/build/bench/rp2350; made absolute): gen/ (the faces), build-<core>/ (one CMake
# build directory a core, reused and never deleted: its cache never changes platform) with build-<core>.log, nm-<core>-<opt>-<NAME>.txt
# (nm output of each ELF) and run-<core>-<opt>-<NAME>.txt / .err (core riscv or arm; opt Os or O2; NAME MONO_PAGE, GRAY8, RGB565
# or LINE).
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/rp2350}
FACE=${FACE:-$(dirname "$C")/svf/dos/NEODG16G.SVF}
FACE16=${FACE16:-$(dirname "$C")/svf/dos/PAPLG16.SVF}
FACE18=${FACE18:-$(dirname "$C")/svf/dos/PAPLG18.SVF}
NODE=${NODE:-$OPT/node-v24.13.0-linux-x64/bin/node}
CORES=${CORES:-riscv arm}
LIMIT=${LIMIT:-600} # seconds a node run may take
PRV=$OPT/pico-riscv-toolchain-16-v2.3.1-0
ARMTC=$OPT/arm-gnu-toolchain-15.2.rel1
RPJS=$OPT/rp2350js-af0114c
SDK=$OPT/pico-sdk-2.3.1

. "$HERE/sums.inc.sh" # SUMS_<kind>: the expected checksums
. "$HERE/guard.sh" # run_guarded OUT ERR CMD...: node under guard.py, killed with this script; verify_ok, guard_why
for core in $CORES; do
	case $core in
	riscv | arm) ;;
	*) echo "rp2350: unknown core: $core (riscv arm)"; exit 1 ;;
	esac
done
note_unpinned rp2350 NODE "$OPT/node-v24.13.0-linux-x64/bin/node"
verify_ok rp2350 "$C/cross/install-toolchains.sh" arm pico-rv pico-sdk
verify_ok rp2350 "$HERE/install-emulators.sh" rp2350js
command -v cmake >/dev/null 2>&1 || { echo "rp2350: cmake not found"; exit 1; }
sums_for_faces rp2350 "$(dirname "$C")" # faces other than the defaults have other checksums

mkdir -p "$OUT" || exit 1
OUT=$(cd "$OUT" && pwd) || exit 1 # the CMake build directories and the raw files are found by absolute path
mkdir -p "$OUT/gen" || exit 1
python3 -I "$HERE/mkface.py" "$FACE" "$OUT/gen/face.c" --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE16" "$OUT/gen/face16.c" --name bench_face16 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE18" "$OUT/gen/face18.c" --name bench_face18 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
status=0

for core in $CORES; do
	case $core in
	riscv)
		platform=rp2350-riscv toolchain=$PRV cc=$PRV/bin/riscv32-pico-elf cname="Hazard3"
		gccname=riscv32-pico-elf-gcc want=2000000 ;;
	arm)
		platform=rp2350-arm-s toolchain=$ARMTC cc=$ARMTC/bin/arm-none-eabi cname="Cortex-M33"
		gccname=arm-none-eabi-gcc want=3000000 ;;
	esac
	ver=$("$cc-gcc" -dumpfullversion) || exit 1
	bdir=$OUT/build-$core
	cmake -S "$HERE/rp2350" -B "$bdir" -DPICO_SDK_PATH="$SDK" -DPICO_BOARD=pico2 -DPICO_PLATFORM="$platform" \
		-DPICO_TOOLCHAIN_PATH="$toolchain" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release -DBENCH_GEN="$OUT/gen" \
		>"$OUT/build-$core.log" 2>&1 &&
		cmake --build "$bdir" -j "$(nproc)" >>"$OUT/build-$core.log" 2>&1 ||
		{ tail -n 40 "$OUT/build-$core.log"; echo "rp2350: build failed ($core), see $OUT/build-$core.log"; exit 1; }
	for kind in "MONO_PAGE 0x02" "GRAY8 0x01" "RGB565 0x08" "LINE -"; do
		set -- $kind
		name=$1 bit=$2
		case $name in
		MONO_PAGE) SUMS=$SUMS_MONO_PAGE ;;
		GRAY8) SUMS=$SUMS_GRAY8 ;;
		RGB565) SUMS=$SUMS_RGB565 ;;
		LINE) SUMS=$SUMS_LINE40 ;;
		esac
		[ -n "$SUMS" ] || { echo "rp2350: no sums for $name"; exit 1; }
		mask=$bit
		[ "$name" != LINE ] || mask=default
		for o in Os O2; do
			tag=$core-$o-$name
			elf=$bdir/bench-$o-$name.elf
			"$cc-nm" "$elf" >"$OUT/nm-$tag.txt" || { echo "rp2350: nm failed ($tag)"; exit 1; }
			run_guarded "$OUT/run-$tag.txt" "$OUT/run-$tag.err" "$NODE" "$HERE/rp2350-run.mjs" "$RPJS" "$core" "$elf" "$OUT/nm-$tag.txt"
			g=$?
			if [ "$g" -ne 0 ]; then
				echo "rp2350: emulator failed ($tag): guard exit $g, $(guard_why "$g"); see $OUT/run-$tag.txt and $OUT/run-$tag.err"
				status=1
				continue
			fi
			if ! awk -v w="$want" '/^cal=/ {
				if ($0 ~ /^cal=empty cycles=[0-9]+ insns=[0-9]+$/) { ne++; split($2, a, "="); e = a[2] + 0; split($3, a, "="); ei = a[2] + 0 }
				else if ($0 ~ /^cal=loop1m cycles=[0-9]+ insns=[0-9]+$/) { nl++; split($2, a, "="); l = a[2] + 0; split($3, a, "="); li = a[2] + 0 }
				else bad = 1 }
				END { d = l - e - w; if (d < 0) d = -d; di = li - ei - 2000000; if (di < 0) di = -di
				      exit !(ne == 1 && nl == 1 && !bad && e > 0 && e <= 32 && d <= 16 && di <= 16) }' "$OUT/run-$tag.txt"; then
				echo "rp2350: calibration failed ($tag), see $OUT/run-$tag.txt"
				status=1
			fi
			awk -v build="$cname emulated (rp2350js af0114c + rp2350js.patch, pico-sdk 2.3.1 pico2 image booted from the A2 boot ROM: rp2350js cycles, µs at 150 MHz, the SDK clk_sys; XIP flash and cache, bus contention and load-use stalls not modelled; $gccname $ver -$o; $name, SVF_TARGETS=$mask)" \
				-v mhz=150 -v sums="$SUMS" -v exact=1 -v need_insns=1 -f "$HERE/report.awk" "$OUT/run-$tag.txt"
			s=$?
			if [ "$s" -ne 0 ]; then
				echo "rp2350: run failed ($tag), see $OUT/run-$tag.txt"
				status=1
			fi
		done
	done
done
exit $status
