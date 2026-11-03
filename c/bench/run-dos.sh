#!/bin/sh
# run-dos.sh [OUT] - times c/bench/bench.c under DOSBox-X at 486 settings and prints Markdown table rows against the
# design budget (DOS 486: <= 16 ms one 40 code point PAPLG16 + PAPLG18 line, mapped and streamed from a file).
#
# Emulator: DOSBox-X (/usr/bin/dosbox-x; DOSBOX_X overrides), run headless through xvfb-run with core=normal,
# cputype=486 and fixed cycles at DOSBox-X's own "Emulate CPU speed" presets: 23,880 cycles/ms for a 486DX2-66 and
# 12,010 for a 486DX-33 (src/gui/menu_callback.cpp). DOSBox-X does not count 486 clocks: it runs that many
# instructions per emulated millisecond, whatever they are, so the times are approximate (a real 486 spends 1 to
# 40+ clocks an instruction). The program times itself with DJGPP's uclock() (the emulated 8254 PIT, 1.19 MHz), which
# runs on emulated time. Built with DJGPP i586-pc-msdosdjgpp-gcc 12.2.0 (~/opt/djgpp, c/cross/SIZES.md): the library
# at -std=c99 -O2 -march=i486 (the P4 profile: scaling in), bench.c at -std=gnu99 (uclock is not ANSI). DJGPP's DPMI
# host is DOSBox-X's built-in CWSDPMI. Faces: svf/dos/PAPLG16.SVF and PAPLG18.SVF converted to the dos profile (tools/svf2to3.py) next to BENCH.EXE, read into
# memory (mapped) or streamed with fseek + fread; MARUS24A.SVF and MARUS24.SVF (the 24 px packed-kind cases) are
# read into memory the same way.
#
# Two programs are built and run at both presets: BENCH.EXE (the library as c/include/svf.h defaults it: word stores on
# x86) and BENCHB.EXE (library and bench.c built with -DSVF_WORD_STORE=0 -DBENCH_CASE_SUFFIX='"_bytes"': the byte
# loops, every case name ending in _bytes), so each packed-kind row has its byte-loop row beside it. The checksums
# of the two builds are the same (SUMS: the host build of c/bench/run-host.sh, each also computed by
# tools/svfline.py draw_target on the same kind).
#
# Build and raw output go to OUT (default c/build/bench/dos). Exit status: report.awk's (0 met, 2 a budget missed,
# 1 a failure).
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
SVF=$(dirname "$C")/svf/dos
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/dos}
DJ=$OPT/djgpp/bin/i586-pc-msdosdjgpp
DOSBOX_X=${DOSBOX_X:-dosbox-x}
FLAGS="-Wall -Wextra -Werror -O2 -march=i486"
# case:checksum of every case; the _bytes build carries the same names with the suffix
CASES="line40_mapped:d88e20f9 line40_mapped_cache:d88e20f9 line40_stream_cold:d88e20f9 line40_stream_warm:d88e20f9"
CASES="$CASES line40_stream_small:d88e20f9 line40_stream_nocache:d88e20f9"
CASES="$CASES line40_indexed8:db2a4271 line40_rgb555:9c1a4e65 line40_rgb565:d86ce745 line40_xrgb8888:2c995f55"
CASES="$CASES line40_rgb888:aa90d161"
CASES="$CASES line40_24_indexed8:30762be9 line40_24_rgb555:7d011e01 line40_24_rgb565:e65da549"
CASES="$CASES line40_24_xrgb8888:dccb4dbd line40_24_rgb888:322d1519"
CASES="$CASES line40_24m_indexed8:211b3db6 line40_24m_rgb565:bdcc87ef line40_24m_xrgb8888:8f65703c"
# every case has the 16 ms line budget except line40_scaled32 (the line at 3/2: a sum, no budget) and layout_probe (the
# layouts the build reads: SVF_E_RANGE three times, this build reads every one)
SUMS="" BUDGETS="" SUMSB="" BUDGETSB=""
for c in $CASES line40_scaled32:13e5d91d layout_probe:00040404; do
	SUMS="$SUMS $c" SUMSB="$SUMSB ${c%%:*}_bytes:${c#*:}"
	case ${c%%:*} in line40_scaled32 | layout_probe) continue ;; esac
	BUDGETS="$BUDGETS ${c%%:*}:16000" BUDGETSB="$BUDGETSB ${c%%:*}_bytes:16000"
done

# OUT is checked before anything is deleted: an absolute path of plain names, not / and not $HOME (no . or .., no
# symlink on any prefix or below it) that is absent, empty, or carries the marker .run-dos this script writes (the rule
# of vesa-shots.sh); only a marked OUT is cleaned
die() {
	echo "run-dos: $*" >&2
	exit 1
}
case $OUT in /*) ;; *) die "OUT must be an absolute path: $OUT" ;; esac
rest=${OUT#/}
p=""
while [ -n "$rest" ]; do
	comp=${rest%%/*}
	if [ "$comp" = "$rest" ]; then rest=""; else rest=${rest#*/}; fi
	[ -n "$comp" ] || continue
	case $comp in . | ..) die "OUT has a . or .. component: $OUT" ;; esac
	case $comp in *[!A-Za-z0-9._-]*) die "OUT component '$comp' is not [A-Za-z0-9._-]+: $OUT" ;; esac
	p="$p/$comp"
	[ ! -L "$p" ] || die "OUT prefix $p is a symlink"
	[ ! -e "$p" ] || [ -d "$p" ] || die "OUT prefix $p is not a directory"
done
[ -n "$p" ] || die "OUT is the root directory"
home=${HOME:-}
home=${home%/}
[ "$p" != "$home" ] || die "OUT is the home directory"
if [ -d "$OUT" ]; then
	[ -z "$(find "$OUT" -type l -print -quit 2>/dev/null)" ] || die "OUT holds a symlink: $OUT"
	if [ -n "$(ls -A "$OUT")" ] && [ ! -f "$OUT/.run-dos" ]; then
		die "OUT $OUT is not empty and has no .run-dos marker; use an empty directory"
	fi
fi
mkdir -p "$OUT" && : >"$OUT/.run-dos" || die "OUT $OUT cannot be created"

rm -rf "$OUT/obj" "$OUT/objb" "$OUT/run"
mkdir -p "$OUT/obj" "$OUT/objb" "$OUT/run" || exit 1
for s in "$C"/src/*.c; do
	# shellcheck disable=SC2086
	"$DJ-gcc" -std=c99 $FLAGS -I"$C/include" -c "$s" -o "$OUT/obj/$(basename "$s" .c).o" ||
		{ echo "dos: build failed ($s)"; exit 1; }
	# shellcheck disable=SC2086
	"$DJ-gcc" -std=c99 $FLAGS -DSVF_WORD_STORE=0 -I"$C/include" -c "$s" -o "$OUT/objb/$(basename "$s" .c).o" ||
		{ echo "dos: build failed ($s, byte loops)"; exit 1; }
done
# shellcheck disable=SC2086
"$DJ-gcc" -std=gnu99 $FLAGS -DBENCH_DOS -I"$C/include" "$HERE/bench.c" "$OUT"/obj/*.o -o "$OUT/run/BENCH.EXE" ||
	{ echo "dos: build failed"; exit 1; }
# shellcheck disable=SC2086
"$DJ-gcc" -std=gnu99 $FLAGS -DBENCH_DOS -DSVF_WORD_STORE=0 '-DBENCH_CASE_SUFFIX="_bytes"' \
	-I"$C/include" "$HERE/bench.c" "$OUT"/objb/*.o -o "$OUT/run/BENCHB.EXE" ||
	{ echo "dos: build failed (byte loops)"; exit 1; }
# the faces in the dos profile (1 byte units; BENCH_PROFILE overrides it for one run)
for f in PAPLG16 PAPLG18 MARUS24A MARUS24; do
	python3 -I "$HERE/../../tools/svf2to3.py" "$SVF/$f.SVF" "$OUT/run/$f.SVF" --profile "${BENCH_PROFILE:-dos}" \
		${BENCH_BOX:+--box "$BENCH_BOX"} >/dev/null || { echo "dos: converting $f failed"; exit 1; }
done
ver=$("$DJ-gcc" -dumpfullversion) || exit 1
dbver=$("$DOSBOX_X" --version 2>&1 | awk '/^DOSBox-X version/ { print $3; exit }')

status=0
for preset in "486DX2-66 23880" "486DX-33 12010"; do
	set -- $preset
	cat >"$OUT/bench-$1.conf" <<EOF
[sdl]
fullscreen = false
[dosbox]
machine = svga_s3
memsize = 16
[cpu]
core = normal
cputype = 486
cycles = fixed $2
[autoexec]
mount c "$OUT/run"
c:
BENCH.EXE > RESULT.TXT
BENCHB.EXE > RESULTB.TXT
exit
EOF
	rm -f "$OUT/run/RESULT.TXT" "$OUT/run/RESULTB.TXT"
	timeout 1200 xvfb-run -a "$DOSBOX_X" -conf "$OUT/bench-$1.conf" -nopromptfolder -fastlaunch \
		>"$OUT/dosbox-$1.log" 2>&1
	for b in "" B; do
		tr -d '\r' <"$OUT/run/RESULT$b.TXT" >"$OUT/run$b-$1.txt" 2>/dev/null || : >"$OUT/run$b-$1.txt"
		if [ -z "$b" ]; then
			word="word stores"
			sums=$SUMS budgets=$BUDGETS
		else
			word="byte loops, -DSVF_WORD_STORE=0"
			sums=$SUMSB budgets=$BUDGETSB
		fi
		cpu="cputype=486 cycles=fixed $2"
		awk -v build="DOS emulated (DOSBox-X $dbver, $1: $cpu; DJGPP gcc $ver -O2 -march=i486; $word)" \
			-v budgets="$budgets" -v sums="$sums" -f "$HERE/report.awk" "$OUT/run$b-$1.txt"
		s=$?
		[ $s -eq 1 ] && { echo "dos: run failed ($1 $word), see $OUT/run$b-$1.txt and $OUT/dosbox-$1.log"; status=1; }
		[ $s -eq 2 ] && [ $status -eq 0 ] && status=2
	done
done
exit $status
