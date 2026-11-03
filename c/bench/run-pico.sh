#!/bin/sh
# run-pico.sh [OUT] - times c/bench/bench.c on an emulated RP2040 (Raspberry Pi Pico, Cortex-M0+) and prints Markdown
# table rows against the design budgets (Pico at 125 MHz: <= 50 us a composed and drawn 16 px syllable, <= 2 ms a
# 128 x 64 MONO_PAGE screen of 32 glyphs).
#
# Emulator: rp2040js 1.4.0 under node (c/bench/install-emulators.sh), driven by c/bench/pico-run.mjs, which reads
# rp2040js's cycle counter around each case; cycles are converted at 125 MHz (the pico-sdk default clock). Built with
# arm-none-eabi-gcc 15.2.1 (c/cross/install-toolchains.sh) as the P1 profile of c/cross/SIZES.md:
#   -mcpu=cortex-m0plus -mthumb -Os -DSVF_NO_SCALE  (also run at -O2 for comparison)
# with libgcc's software division (pico-sdk would route division to the RP2040's SIO divider). Face: FACE (default
# svf/dos/NEODG16G.SVF, 16 px 1 bpp jamo) embedded in flash by c/bench/mkface.py --profile mcu-strict (an 8,716-byte
# array); the expected checksums are the default face's.
#
# One build per target kind and optimisation: MONO_PAGE (SVF_TARGETS=0x02, 128 x 64 SSD1306 pages), GRAY8 (0x01) and
# RGB565 (0x08), each at -Os and -O2 (-DBENCH_KIND=SVF_T_<kind> -DSVF_TARGETS=<bit>). PICO_KINDS overrides the list: space-
# separated NAME:BIT entries (default "MONO_PAGE:0x02 GRAY8:0x01 RGB565:0x08"); a GRAY entry (the parametric kind at its
# default 8 bits, e.g. GRAY:0x200 or GRAY8:0x201 for the same kind with both compiled in) takes SUMS_GRAY8. An entry that is
# not one of the defaults is tagged with its bit in the elf and run file names (bench-GRAY-0x200-Os.elf), so GRAY8:0x01 and
# GRAY8:0x201 do not overwrite each other; the default entries' names are unchanged. GRAY8 and RGB565 add set B, the
# 2 bpp band cases of PAPLG16 + PAPLG18 (svf/dos), and every kind the case line8. The expected checksums are those of
# `python3 -I c/bench/sums.py` (tools/svfline.py), embedded in sums.inc.sh as SUMS_<kind> (tools/test_c_renderer.py TestBenchSums
# keeps them equal to sums.py and to the host build of bench.c); with another FACE, FACE16 or FACE18 sums.py is run on
# those instead. The speed budgets apply to MONO_PAGE only. pico-run.mjs also counts
# the instructions of a case (insns, per_iter_insns). Measured: syl_ga at -Os newly misses 50 us in the single-kind
# MONO_PAGE build (6,335 cycles against 6,070 with all kinds: suspected: gcc inlines pack8; card t_8b967a59), syl_bwelk missed before (MEASUREMENTS.md).
#
# Build and raw output go to OUT (default c/build/bench/pico); with PROFILE=1 each run also writes a per-function
# cycle profile to OUT/run-<flags>.txt, and the builds add -fno-inline-functions-called-once -fno-inline-small-functions
# so blit and the small helpers stay functions of their own (the build of the profile in MEASUREMENTS.md; its timings
# are slower than the plain build's). NODE overrides the pinned node v24: run unverified and printed as
# "pico: note: unpinned NODE=value". Exit status: report.awk's (0 met, 2 a budget missed, 1 a failure).
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/pico}
FACE=${FACE:-$(dirname "$C")/svf/dos/NEODG16G.SVF}
ARM=$OPT/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi
NODE=${NODE:-$OPT/node-v24.13.0-linux-x64/bin/node}
RP=$OPT/rp2040js-1.4.0
COMMON="-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections"
COMMON="$COMMON -mcpu=cortex-m0plus -mthumb -DSVF_NO_SCALE -DBENCH_PICO ${BENCH_CFLAGS:-}" # BENCH_CFLAGS: more flags, e.g. -DSVF_JSET_BIG=1 (checksums are checked as usual)
LINK="--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main -Wl,--gc-sections"
LINK="$LINK -Wl,-Ttext=0x10000000 -Wl,-Tdata=0x20000000" # code and the face in flash, data in SRAM
if [ "${PROFILE:-0}" = 1 ]; then
	COMMON="$COMMON -fno-inline-functions-called-once -fno-inline-small-functions"
fi
FACE16=${FACE16:-$(dirname "$C")/svf/dos/PAPLG16.SVF}
FACE18=${FACE18:-$(dirname "$C")/svf/dos/PAPLG18.SVF}
. "$HERE/sums.inc.sh" # SUMS_<kind>: the expected checksums (python3 -I c/bench/sums.py), one set per target kind
BUDGETS_MONO_PAGE="syl_ga:50 syl_bwelk:50 screen32:2000"

LIMIT=${LIMIT:-600} # seconds a node run may take (the runs take seconds)
. "$HERE/guard.sh" # run_guarded OUT ERR CMD...: node under guard.py, killed with this script; verify_ok, guard_why
# Both installs, checked before anything is built or run (a tampered or missing tree is not timed).
note_unpinned pico NODE "$OPT/node-v24.13.0-linux-x64/bin/node" # an override runs, unverified: said so
verify_ok pico "$C/cross/install-toolchains.sh" arm
verify_ok pico "$HERE/install-emulators.sh" rp2040js
sums_for_faces pico "$(dirname "$C")" # faces other than the defaults have other checksums

mkdir -p "$OUT" || exit 1
python3 -I "$HERE/mkface.py" "$FACE" "$OUT/face.c" --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE16" "$OUT/face16.c" --name bench_face16 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
python3 -I "$HERE/mkface.py" "$FACE18" "$OUT/face18.c" --name bench_face18 --profile "${BENCH_PROFILE:-mcu-strict}" ${BENCH_BOX:+--box "$BENCH_BOX"} || exit 1
ver=$("$ARM-gcc" -dumpfullversion) || exit 1
status=0
DEFAULT_KINDS="MONO_PAGE:0x02 GRAY8:0x01 RGB565:0x08"
# shellcheck disable=SC2086
for k in ${PICO_KINDS:-$DEFAULT_KINDS}; do
	case $k in ?*:?*) ;; *) echo "pico: PICO_KINDS entry '$k' is not NAME:BIT"; exit 1 ;; esac
	name=${k%%:*} bit=${k#*:}
	ktag=$name
	case " $DEFAULT_KINDS " in *" $k "*) ;; *) ktag=$name-$bit ;; esac
	sumsname=$name
	[ "$name" = GRAY ] && sumsname=GRAY8 # the parametric kind at 8 bits has the GRAY8 checksums
	eval "SUMS=\$SUMS_$sumsname"
	[ -n "$SUMS" ] || { echo "pico: no sums for $name"; exit 1; }
	BUDGETS=
	[ "$name" = MONO_PAGE ] && BUDGETS=$BUDGETS_MONO_PAGE
	for opt in -Os -O2; do
		tag=$ktag$opt
		elf=$OUT/bench-$tag.elf
		# shellcheck disable=SC2086
		"$ARM-gcc" $COMMON -DBENCH_KIND=SVF_T_$name -DSVF_TARGETS=$bit $opt -I"$C/include" "$HERE/bench.c" \
			"$C"/src/*.c "$OUT/face.c" "$OUT/face16.c" "$OUT/face18.c" $LINK -o "$elf" ||
			{ echo "pico: build failed ($tag)"; exit 1; }
		nm=
		if [ "${PROFILE:-0}" = 1 ]; then
			nm=$OUT/nm-$tag.txt
			"$ARM-nm" -S --size-sort "$elf" >"$nm"
		fi
		if [ -n "$nm" ]; then
			run_guarded "$OUT/run-$tag.txt" "$OUT/run-$tag.err" "$NODE" "$HERE/pico-run.mjs" "$RP" "$elf" "$nm"
		else
			run_guarded "$OUT/run-$tag.txt" "$OUT/run-$tag.err" "$NODE" "$HERE/pico-run.mjs" "$RP" "$elf"
		fi
		g=$?
		if [ $g -ne 0 ]; then
			echo "pico: emulator failed ($tag): guard exit $g, $(guard_why $g); see $OUT/run-$tag.txt and $OUT/run-$tag.err"
			status=1
			continue
		fi
		awk -v build="Pico emulated (rp2040js 1.4.0, 125 MHz; gcc $ver $opt; $name, SVF_TARGETS=$bit)" -v mhz=125 \
			-v budgets="$BUDGETS" -v sums="$SUMS" -v exact=1 -v need_insns=1 -f "$HERE/report.awk" "$OUT/run-$tag.txt"
		s=$?
		if [ $s -eq 1 ]; then
			echo "pico: run failed ($tag), see $OUT/run-$tag.txt"
			status=1
		elif [ $s -eq 2 ] && [ $status -eq 0 ]; then
			status=2
		fi
	done
done
exit $status
