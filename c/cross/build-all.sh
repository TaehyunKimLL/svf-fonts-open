#!/bin/sh
# build-all.sh [OUT] - builds c/src/*.c with every toolchain and reports the code size of each build profile.
# build-all.sh --screens-missing - prints what the emulated screens still lack (the test of the gate).
# build-all.sh --ports [OUT] - builds the port examples of c/ports/ instead (below).
# build-all.sh --port NAME [OUT] - builds only the port example NAME into OUT/ports/ (below), needing and verifying only
#   its toolchain: dos, web, sdl (check.sh of c/ports/sdl: svfsdl2 and svfsdl3, SDL3 verified), arduino, ch582, pico (the three images pico-colour, pico-grey, pico-mono) or esp32 (the six
#   images esp32c3-* and esp32s3-*). No gate runs: no rows.txt, SIZES.md check, host checks, screens or unit tests. Exits 1 if
#   a build fails, 2 for an unknown NAME.
#
# For each toolchain: compiles every c/src/*.c once per object set (as is; -DSVF_NO_SCALE; plus the SVF_TARGETS sets above) with
#   -std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections (the JSET readers of svf.h's default per target:
#   both readers, AVR the version 1 reader alone; variant rows: cortex-m0plus JSET_V1 -DSVF_JSET_V2=0, JSET_V2
#   -DSVF_JSET_V1=0, JSET_TRUSTED -DSVF_JSET_TRUSTED=1, JSET_POP4=0, JSET_BIG -DSVF_JSET_BIG=1; avr JSET_BOTH -DSVF_JSET_V2=1, JSET_V2
#   -DSVF_JSET_V1=0 -DSVF_JSET_V2=1, JSET_TRUSTED, JSET_BIG. A variant profile whose link overflows the target's memory, as the
#   AVR P4 of both readers does, is the row "P4 [LABEL] | overflow N" (N bytes over), not a failure)
# plus the toolchain's flags below, then links c/cross/probe.c for each profile with --gc-sections and runs size on it:
#   P0 empty (the probe's main only: startup code, subtracted from the others)
#   P1 Uno: mapped face, 1 bpp, jamo, MONO_PAGE, SVF_NO_SCALE, -DSVF_TARGETS=0x02 (MONO_PAGE only), -DSVF_NO_STREAM
#      -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT (the stream reader left out, one layout read)
#   P1* P1 with every target kind (the default SVF_TARGETS; P1's other switches), so P1* - P1 is the cost of the other
#      kinds
#   P2 M0+ OLED: P1 plus 2 bpp (-DSVF_TARGETS=0x02; the same two switches)
#   P3 TFT: mapped, 2 bpp, jamo, RGB565, syllable cache, SVF_NO_SCALE, -DSVF_TARGETS=0x08 (RGB565 only)
#   P3w P3 with -DSVF_WORD_STORE=1 (the word path on every toolchain; equal to P3 where the switch is 1 by default)
#   P3g grey OLED: P3 with GRAY8 instead of RGB565 (-DPROBE_KIND=SVF_T_GRAY8, -DSVF_TARGETS=0x01)
#   P4 full: every function, every target, streamed faces, scaling. The AVR row pins -DSVF_TARGETS=0x1FF (every kind that
#      existed before SVF_T_GRAY: the Uno's 32 KB does not hold the parametric grey kind: a build that does not draw GRAY
#      lowers SVF_TARGETS, the default mask 0x3FF includes it on AVR too), so its P4 stays comparable; the informational AVR row P4+GRAY is the same with the default mask and
#      may overflow without failing the script (its row then reads "overflow N B").
#   P5 VESA (the DOS example): streamed face with a block cache, scale 3/2, INDEXED8, RGB555, RGB565, XRGB8888,
#      RGB888 (-DSVF_TARGETS=0x1E8, scaling on)
# A row is the profile's link minus the empty link (text, data, bss in bytes): the library plus the C library and
# compiler helpers it pulls in (memcpy, memset, division on cores without it), without startup code. For WASM the
# text column is the code section of the module.
# Prints "<toolchain>: OK <version>" (or FAIL with the reason) a toolchain, then the size table as Markdown; exits 1
# if any toolchain fails or is missing, or if a Cortex-M0+ P1 or P2 text exceeds 8192 bytes (BUDGET; P1* has no gate).
#
# --ports: each example of c/ports/ with its target's toolchain above, -Wall -Wextra -Werror. No vendor SDK is used:
#   dos      the whole programs (DJGPP needs no SDK): SVFDEMO.EXE, run it with c/ports/dos/screenshot.sh; and SVFVESA.EXE
#            (svfvesa.c, vesa_lines.c and vbe_select.c, the pure VBE unit tested on the host by tests/test_vbe.c), run it
#            with c/ports/dos/vesa-shots.sh
#   web      the whole module (emcc): svf.js + svf.wasm
#   pico, esp32c3, esp32s3   nine images, one per board and profile of c/ports/profiles.txt (colour, grey, mono): main.c,
#            the profile, its display driver, the library and the profile's faces, linked bare (Cortex-M0+, riscv32-esp-elf,
#            xtensa-esp32s3-elf) against c/ports/pico/stub/ or c/ports/esp32/stub/. The row of profiles.txt is read by awk
#            (kind, SVF_TARGETS, faces, driver); the grey kind's -DSVF_GREY_KIND_GRAY8=1 follows from the row's kind
#   ch582    the CH582 example (YD-CH582M, SH1106 OLED): main.c, profile_mono.c, disp_sh1106.c and
#            the stub i2c_stub.c (in place of i2c.c), the library and the face, linked bare with riscv32-esp-elf-gcc
#            against c/ports/ch582/stub/ (the row "ch582 mono" of the table, the markers svf_port_driver_sh1106 and
#            svf_port_profile_mono). Then, when the WCH EVT (c/cross/install-toolchains.sh ch583) is installed, the
#            real image: `make -C c/ports/ch582` (SDK start-up code and drivers, 24 MHz) into OUT/ports/ch582-sdk,
#            whose size line is printed as "ch582-sdk-size:" and, in the full run, compared with SIZES.md's "CH582 SDK
#            image" table (check-sizes-md.sh --ch582-sdk). An absent SDK prints "ch582-sdk: SKIPPED (not installed:
#            ...)", which fails nothing here; a failed SDK build prints "ch582-sdk: FAIL ..."
#   arduino  arduino.ino (as C++) the same for the ATmega328P against c/ports/arduino/stub/, the library built with
#            -DSVF_RD8(p)=pgm_read_byte(p) and the face in PROGMEM
#            Also the rows arduino-mega and arduino-mega-rich for the ATmega2560 (build only; near PROGMEM reads: a flash end
#            >= 65,536 B prints a FLAG line, far reads are not supported; not OK lines, the count stays)
# The stubs are no-op stand-ins for the SDK calls (I2C, SPI, GPIO, delays): these links check that the SVF side of the
# example compiles and links with the target's compiler, not that it runs or builds against the real SDK. Face arrays
# are generated with c/bench/mkface.py into OUT/ports. Prints "port-<name>: OK" or FAIL a port, with the program's
# bytes (dos, web, sdl: svfsdl2 and svfsdl3, informational rows `info program sdl2|sdl3 N`, not gated by SIZES.md; the
# check.sh output is shown on a failure, else as one `port-sdl-check-runs:` line without OK, plus its `note:` lines) or the linked image's text (code and constants: the face arrays included), data and bss (RAM;
# stubbed SDK calls hold none) and, for the nine images, the bytes of the faces embedded. Each image is also checked
# against the table: `cmake -P c/ports/profiles.cmake` must print the row awk read, the image must hold exactly the
# markers svf_port_driver_<driver> and svf_port_profile_<profile> (no second driver or profile linked in), and the compile
# line's -DSVF_TARGETS= is the row's. After port-arduino: c/ports/check/host-checks.sh (its port-check-* lines), then
# c/ports/check/run-screens.sh (the five emulated screens: its screen-*: OK lines), test_pico_screen.sh
# (pico-screen-negative: OK) and test_run_screens.sh (run-screens-gates: OK), all under SVF_REQUIRE_SCREENS=1, when
# nothing is missing (as run-screens.sh --missing lists it: pico-sdk, toolchains, QEMUs, boot ROM, node v24, Pillow),
# else "screens: SKIPPED (missing: ...)"; a missing run-screens.sh is a failure. Last the unit tests of c/ports/check (port-check-unit-esp-screen, -screens,
# -panels: OK; node v24 from OPT); one whose tool is missing prints "unit NAME: SKIPPED (missing: ...)" and
# fails the run. Exits 1 if anything fails.
# A full run prints 43 OK lines (EXPECT_OK below): 14 ports (port-dos and port-sdl each name both of their programs) + 19 port-check (host) + 5 screens
# + 1 pico-screen-negative + 1 run-screens-gates + 3 unit tests. The full run counts its own OK lines and fails on a
# mismatch; a skipped screens block ("screens: SKIPPED") removes 7 OK lines (5 screens + pico-screen-negative +
# run-screens-gates), a skipped unit test one each; other skips (ch582-sdk) remove none. Hidden first arguments of the tests
# (c/cross/test-build-all.sh): --ba-inner (the self-re-run of the full run), --print-hooks, --count-check FILE, --overflow-of LOG, --gray-werror NAME CC CFLAGS.
# The AVR toolchain also prints one line "avr-atmega328p gray-werror: ok ..." (not an OK line, the count stays): svf_draw.c compiled
# alone with -Werror for SVF_TARGETS 0x01, 0x200, 0x201 and 0x3FF, so the AVR-only GRAY dispatch of svf_draw.c is checked for every mask.
#
# Toolchains are looked up in OPT (default ~/opt, as c/cross/install-toolchains.sh installs them); build files go to
# OUT (default c/build/cross): it must be new, empty, or a directory this script made earlier (it removes the
# directories below it). Before anything is built, `install-toolchains.sh --verify` re-checks every toolchain the run
# builds with (clang arm avr esp xtensa emsdk pico-rv; with --ports: arm avr esp xtensa emsdk sdl3) against its pinned manifest or commit,
# and before the emulated screens `install-toolchains.sh --verify pico-sdk` and `install-emulators.sh --verify` the pico-sdk,
# rp2040js, both QEMUs and the boot ROM: a package that is absent is reported by the installer as not installed (and by the
# tool lookup below, if the run needs it), a present one that differs from its pin stops the run (exit 1). DJGPP is not
# installer-managed and is not covered. The pico CMake configure checks (test_pico_cmake.sh) run, silent on success, when
# the pico-sdk is installed.
set -u

PORTS=0 SM=0
ALL_PORTS="dos web sdl pico esp32 arduino ch582"
ONLY= # --port NAME: the one port built, without the gates
ROWS= # the full --ports run: OUT/ports/rows.txt, the rows check-sizes-md.sh checks (none for --port)
# run-screens.sh can be pointed at another SIZES.md for its own tests (SVF_SIZES_MD); a run of this script never takes that
unset SVF_SIZES_MD
EXPECT_OK=43 # the OK lines of a full run (the header says it too; test-build-all.sh compares)
SKIP_SCREENS_OK=7 # the OK lines a skipped screens block takes away
# count_check FILE RC: RC of the full run, FILE its output; the OK lines must be EXPECT_OK (less the skipped blocks')
count_check() {
	n=$(grep -c ': OK' "$1") want=$EXPECT_OK
	grep -q '^screens: SKIPPED' "$1" && want=$((want - SKIP_SCREENS_OK))
	want=$((want - $(grep -c '^unit .*: SKIPPED' "$1")))
	if [ "$2" = 0 ] && [ "$n" != "$want" ]; then
		echo "build-all.sh: FAIL $n lines with OK, expected $want (a full run: $EXPECT_OK)"
		return 1
	fi
	return "$2"
}
# overflow_of LOG: the N of "region `text' overflowed by N bytes" in a link log, when that is all that went wrong; else nothing.
# GNU ld goes on after a region overflow, so an undefined reference or any other error line in the same log must not hide
# behind the overflow: the link is then a failure. Only the overflow line and the final "ld returned" line are allowed.
overflow_of() {
	[ -z "$(grep -i 'error\|undefined reference\|cannot find\|multiple definition' "$1" | grep -v 'overflowed by\|ld returned')" ] &&
		sed -n 's/.*overflowed by \([0-9][0-9]*\) bytes.*/\1/p' "$1" | head -n 1
}
# gray_werror NAME CC CFLAGS...: svf_draw.c alone, compile only, -Wall -Wextra -Werror, for SVF_TARGETS 0x01, 0x200, 0x201 and
# 0x3FF (GRAY8 alone, GRAY alone, both, every kind): the AVR-only GRAY dispatch of svf_draw.c is compiled by no other
# -Werror build of every mask (the host gcc and clang gate of make check does not see the __AVR__ cases). One line that is
# not an OK line (the full run counts those): "NAME gray-werror: ok MASKS" or "NAME: FAIL gray-werror MASK" and the log.
gray_werror() {
	gname=$1 gcc_=$2
	shift 2
	for gm in 0x01 0x200 0x201 0x3FF; do
		# shellcheck disable=SC2086
		if ! gl=$("$gcc_" -std=c99 -Wall -Wextra -Werror -fsyntax-only "$@" -DSVF_TARGETS=$gm -I"$C/include" "$C/src/svf_draw.c" 2>&1); then
			echo "$gname: FAIL gray-werror SVF_TARGETS=$gm"; echo "$gl" | sed 's/^/  /'
			return 1
		fi
	done
	echo "$gname gray-werror: ok 0x01 0x200 0x201 0x3FF"
}
INNER=0 PH=0
while :; do # hidden first arguments of the tests
	case ${1:-} in
	--ba-inner) INNER=1; shift ;;
	--print-hooks) PH=1; shift ;;
	--overflow-of) overflow_of "$2"; exit 0 ;;
	--count-check) count_check "$2" "${3:-0}"; exit $? ;;
	*) break ;;
	esac
done
if [ "${1:-}" = --print-sizes-md ]; then # a test (c/cross/test-build-all.sh): what the screens run would inherit
	echo "SVF_SIZES_MD=${SVF_SIZES_MD-unset}"
	exit 0
fi
if [ "${1:-}" = --screens-missing ]; then # a test of the screens gate (c/cross/test-build-all.sh): prints what is missing
	SM=1
elif [ "${1:-}" = --ports ]; then
	PORTS=1
	shift
elif [ "${1:-}" = --port ]; then
	PORTS=1
	ONLY=${2:-}
	case " $ALL_PORTS " in
	*" $ONLY "*) [ -n "$ONLY" ] && shift 2 ;;
	*) ONLY= ;;
	esac
	[ -n "$ONLY" ] || { echo "build-all.sh: --port NAME, NAME one of: $ALL_PORTS" >&2; exit 2; }
fi
# the test hooks reach --port NAME only; a full run takes none (as it takes no SVF_SIZES_MD)
if [ -n "$ONLY" ]; then ROWS=${SVF_SDL_ROWS:-}; else unset SVF_SDL_CHECK SVF_SDL_ROWS; fi
if [ $PH -eq 1 ]; then
	echo "SVF_SDL_CHECK=${SVF_SDL_CHECK-unset} SVF_SDL_ROWS=${SVF_SDL_ROWS-unset} counted=$([ $PORTS -eq 1 ] && [ -z "$ONLY" ] && [ $INNER -eq 0 ] && echo yes || echo no)"
	exit 0
fi
HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
if [ "${1:-}" = --gray-werror ]; then # a test (c/cross/test-build-all.sh): the gray_werror check with a given compiler
	shift
	gray_werror "$@"
	exit $?
fi
OPT=${OPT:-$HOME/opt}
P=$C/ports

# screens_missing: what the emulated screens still need, as run-screens.sh --missing prints it (paths, space separated);
# empty when all is there. QEMU_RV, QEMU_XT and NODE override the tools as they do for run-screens.sh.
screens_missing() { OPT=$OPT sh "$P/check/run-screens.sh" --missing; }

if [ $SM -eq 1 ]; then
	screens_missing
	exit 0
fi
OUT=${1:-$C/build/cross}

# verify_installs SCRIPT NAME...: the installer's --verify for the toolchains this run uses; silent on success, stops
# the run (exit 1) on the first failure.
verify_installs() {
	s=$1
	shift
	if ! msg=$(OPT=$OPT sh "$s" --verify "$@" 2>&1); then
		echo "$msg" >&2
		echo "install verification failed: $s --verify $*" >&2
		exit 1
	fi
}
if [ $PORTS -eq 1 ] && [ -z "$ONLY" ] && [ $INNER -eq 0 ]; then
	# the full run counts its own OK lines: run again, tee the output, compare
	cnt=$(mktemp -d) || exit 1
	trap 'rm -rf "$cnt"' EXIT INT TERM
	{ sh "$HERE/build-all.sh" --ba-inner --ports "$@"; echo $? >"$cnt/rc"; } | tee "$cnt/out"
	rc=$(cat "$cnt/rc" 2>/dev/null || echo 1)
	count_check "$cnt/out" "${rc:-1}"
	rc=$?
	rm -rf "$cnt"
	exit "$rc"
fi
if [ $PORTS -eq 1 ]; then
	# the gate uses the pinned, verified trees only: no override of the QEMUs or node reaches the screens
	unset QEMU_RV QEMU_XT NODE
	case $ONLY in
	# ch583 is verified with the SDK image below
	'') verify_installs "$HERE/install-toolchains.sh" arm avr esp xtensa emsdk sdl3 ;;
	dos) ;; # DJGPP is not installer-managed
	web) verify_installs "$HERE/install-toolchains.sh" emsdk ;;
	sdl) [ -n "${SVF_SDL_CHECK:-}" ] || verify_installs "$HERE/install-toolchains.sh" sdl3 ;;
	pico) verify_installs "$HERE/install-toolchains.sh" arm ;;
	esp32) verify_installs "$HERE/install-toolchains.sh" esp xtensa ;;
	arduino) verify_installs "$HERE/install-toolchains.sh" avr ;;
	ch582) verify_installs "$HERE/install-toolchains.sh" esp ;;
	esac
else
	verify_installs "$HERE/install-toolchains.sh" clang arm avr esp xtensa emsdk pico-rv
fi
BUDGET=8192
COMMON="-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections"
GC="-Wl,--gc-sections"
EM=$OPT/emsdk

status=0
# The script removes directories below OUT: only a new or empty OUT, or one this script made (marker file), is used.
if [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && [ ! -f "$OUT/.svf-cross-build" ]; then
	echo "build-all: refusing to use $OUT: not empty and not a build-all output directory (no .svf-cross-build)"
	exit 1
fi
mkdir -p "$OUT" || exit 1
OUT=$(cd "$OUT" && pwd) || exit 1 # absolute: the screens runner and the checks run from other directories
: >"$OUT/.svf-cross-build"
rows=$OUT/rows.md
vrows=$OUT/rows-switches.md # the rows of the size-switch variants (build's VARIANTS), printed after the plain rows
[ $PORTS -eq 1 ] || : >"$vrows"
[ $PORTS -eq 1 ] || : >"$rows" # the toolchain size rows; a port run writes under OUT/ports only

# sizes FILE: "text data bss" of an ELF/COFF (SIZE, Berkeley format) or of a WASM module (code section; data the data
# section; bss 0: WASM has no bss, zeroed memory is part of no section).
sizes() {
	case $1 in
	*.wasm)
		set -- $("$EM/upstream/bin/llvm-objdump" -h "$1" | awk '
			$2 == "CODE" { t = $3 } $2 == "DATA" { d = $3 } END { print (t ? t : 0), (d ? d : 0) }')
		echo $((0x$1)) $((0x$2)) 0 ;;
	*.exe)
		# DJGPP's linker script pads .text and .data to 512 bytes (and puts .bss.* input sections in .data), so size
		# would count in 512-byte steps: the ends its script marks (etext, edata, end) give the bytes.
		f=$1
		set -- $("${SIZE%size}objdump" -h "$f" | awk '$2 ~ /^\.(text|data|bss)$/ { printf "%s ", $4 }')
		set -- "$@" $("${SIZE%size}nm" "$f" | awk '$3 == "etext" || $3 == "edata" || $3 == "end" { v[$3] = $1 }
			END { print v["etext"], v["edata"], v["end"] }')
		[ $# -eq 6 ] && echo $((0x$4 - 0x$1)) $((0x$5 - 0x$2)) $((0x$6 - 0x$3)) ;;
	*) "$SIZE" "$1" | awk 'NR == 2 { print $1, $2, $3 }' ;;
	esac
}

# build NAME VERSION CC SIZE CFLAGS LDFLAGS EXT [VARIANTS]: compiles, links P0..P5 and records the rows, once with the
# toolchain's flags and once for each variant of VARIANTS (a list of LABEL:-Dflags, no spaces inside, several flags
# joined by commas; the switches of svf.h: SMALL=-DSVF_SMALL or one of them off, the JSET readers), whose rows are
# labelled "P4 [LABEL]" and go below the plain rows.
build() {
	name=$1 ver=$2 CC=$3 SIZE=$4 cflags=$5 ldflags=$6 ext=$7 variants=${8:-}
	build_v "$name" "$ver" "$CC" "$SIZE" "$cflags" "$ldflags" "$ext" "" "" "" || return 1
	case $name in avr-*) gray_werror "$name" "$CC" $cflags || return 1 ;; esac
	for v in $variants; do
		(build_v "$name" "$ver" "$CC" "$SIZE" "$cflags" "$ldflags" "$ext" "" "${v%%:*}" "$(echo "${v#*:}" | tr , ' ')") ||
			return 1 # a subshell: build_v sets variables
	done
	echo "$name: OK $ver ($($CC --version 2>/dev/null | head -n 1))"
}

# build_v NAME VERSION CC SIZE CFLAGS LDFLAGS EXT VARIANTS LABEL FLAGS: one build of build (FLAGS added to every compile and link).
build_v() {
	name=$1 ver=$2 CC=$3 SIZE=$4 cflags=$5 ldflags=$6 ext=$7 vlabel=$9 vflags=${10}
	cflags="$cflags $vflags"
	d=$OUT/$name${vlabel:+-$vlabel}
	rm -rf "$d"
	mkdir -p "$d" || return 1
	# P1 and P2 are the strict, mapped-only build: one layout (mcu-strict, which the units fold to constants), no stream reader
	P12="-DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT"
	# P1* is P1 with every target kind: the same switches without SVF_TARGETS
	P1S="-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT"
	# object sets: obj (all, scaling), noscale (all targets), page (MONO_PAGE only, 0x02, mapped only, mcu-strict layout only), pagestar (page with every kind), rgb (RGB565 only, 0x08),
	# gray (GRAY8 only, 0x01), vesa (the five packed kinds, scaling, 0x1E8), rgbw (RGB565 only, word stores forced on)
	# AVR: P4 is pinned to the kinds before SVF_T_GRAY (0x1FF); objgray is the default mask, for the informational P4+GRAY row
	p4pin=
	case $name in avr-*) p4pin=-DSVF_TARGETS=0x1FF ;; esac
	g4=; [ -z "$vlabel" ] && [ -n "$p4pin" ] && g4=1 # the P4+GRAY object set is for the default run only (no variant row)
	for set in "obj $p4pin" ${g4:+"objgray "} "noscale -DSVF_NO_SCALE" "page $P12" "pagestar $P1S" \
		"rgb -DSVF_NO_SCALE -DSVF_TARGETS=0x08" "gray -DSVF_NO_SCALE -DSVF_TARGETS=0x01" "vesa -DSVF_TARGETS=0x1E8" \
		"rgbw -DSVF_NO_SCALE -DSVF_TARGETS=0x08 -DSVF_WORD_STORE=1"; do
		set -- $set
		sd=$1
		shift
		mkdir -p "$d/$sd" || return 1
		for s in "$C"/src/*.c; do
			o=$(basename "$s" .c).o
			# shellcheck disable=SC2086
			$CC $COMMON $cflags "$@" -I"$C/include" -c "$s" -o "$d/$sd/$o" 2>"$d/log" ||
				{ echo "$name: FAIL compiling $s ($sd)"; sed 's/^/  /' "$d/log"; return 1; }
		done
	done
	# P0 empty, P1 and P2 MONO_PAGE only, P1* every target, P3 RGB565 only, P4 everything (on AVR: every kind that existed before
	# SVF_T_GRAY, -DSVF_TARGETS=0x1FF = p4pin, the Uno's 32 KB does not hold the parametric grey kind; 4G is the informational
	# P4+GRAY row, the default mask, which may overflow)
	for p in 0 1 1S 2 3 3W 3g 4 4G 5; do
		if [ $p = 4G ] && { [ -z "$p4pin" ] || [ -n "$vlabel" ]; }; then continue; fi
		case $p in
		0) sd=noscale; nos=-DSVF_NO_SCALE ;;
		1S) sd=pagestar; nos="$P1S" ;;
		1 | 2) sd=page; nos="$P12" ;;
		3) sd=rgb; nos="-DSVF_NO_SCALE -DSVF_TARGETS=0x08" ;;
		3W) sd=rgbw; nos="-DSVF_NO_SCALE -DSVF_TARGETS=0x08 -DSVF_WORD_STORE=1" ;;
		3g) sd=gray; nos="-DSVF_NO_SCALE -DSVF_TARGETS=0x01 -DPROBE_KIND=SVF_T_GRAY8" ;;
		4) sd=obj; nos=$p4pin ;;
		4G) sd=objgray; nos= ;;
		5) sd=vesa; nos="-DSVF_TARGETS=0x1E8" ;;
		esac
		# shellcheck disable=SC2086
		label=P${p%[SW]}; [ "$p" = 1S ] && label='P1*'; [ "$p" = 4G ] && label=P4+GRAY; [ "$p" = 3W ] && label=P3w
		if ! $CC $COMMON $cflags $nos -DPROFILE=${p%[SWgG]} -I"$C/include" "$HERE/probe.c" $d/$sd/*.o $GC $ldflags \
			-o "$d/p$p$ext" 2>"$d/log"; then
			# a variant that does not fit the target (ld: "region `text' overflowed by N bytes"): a row, not a failure
			over=$(overflow_of "$d/log")
			if [ -n "$vlabel" ] && [ "$p" != 0 ] && [ -n "$over" ]; then
				echo "| $name | $ver | $label [$vlabel] | overflow $over | - | - |" >>"$vrows"
				continue
			fi
			if [ $p = 4G ] && [ -n "$over" ]; then # informational: only a genuine "overflowed by N bytes" is swallowed; any other error fails
				echo "| $name | $ver | $label | overflow $over B | - | - |" >>"$rows"
				continue
			fi
			echo "$name: FAIL linking P$p"; sed 's/^/  /' "$d/log"; return 1
		fi
		set -- $(sizes "$d/p$p$ext")
		[ $# -eq 3 ] || { echo "$name: FAIL sizing P$p"; return 1; }
		if [ $p = 0 ]; then
			t0=$1 d0=$2 b0=$3
			continue
		fi
		t=$(($1 - t0)) dd=$(($2 - d0)) b=$(($3 - b0))
		if [ -n "$vlabel" ]; then
			echo "| $name | $ver | $label [$vlabel] | $t | $dd | $b |" >>"$vrows"
		else
			echo "| $name | $ver | $label | $t | $dd | $b |" >>"$rows"
		fi
		if [ -z "$vlabel" ] && [ "$name" = cortex-m0plus ] && { [ "$p" = 1 ] || [ "$p" = 2 ]; } && [ $t -gt $BUDGET ]; then
			echo "$name: $label text $t > $BUDGET bytes (budget missed)"
			status=1
		fi
	done
}

# try NAME CC ...: build if CC runs, else report it missing.
try() {
	if ! command -v "$3" >/dev/null 2>&1; then
		echo "$1: FAIL not found: $3 (c/cross/install-toolchains.sh)"
		status=1
		return
	fi
	build "$@" || status=1
}

# version CC: the compiler's version number (gcc 7+ -dumpfullversion, else -dumpversion).
version() { "$1" -dumpfullversion 2>/dev/null || "$1" -dumpversion 2>/dev/null; }

DJ=$OPT/djgpp/bin/i586-pc-msdosdjgpp
ARM=$OPT/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi
AVR=$OPT/avr-gcc-16.1.0/bin/avr
ESP=$OPT/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf
PRV=$OPT/pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf
XT=$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf
XT32=$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32-elf # the original ESP32 (LX6) in the same tarball
SVF=$(dirname "$C")/svf
P=$C/ports
W="-Wall -Wextra -Werror"

# face_len FILE: the bytes of the face array mkface.py wrote to FILE (its NAME_len).
face_len() { sed -n 's/^const uint32_t [A-Za-z0-9_]*_len = \([0-9]*\)u;$/\1/p' "$1"; }

# mcu_port BOARD PROFILE: one of the nine images (BOARD pico, esp32c3 or esp32s3; PROFILE a row of profiles.txt) into
# OUT/ports/BOARD-PROFILE: prints its OK line; 1 on a failure or a table mismatch.
mcu_port() {
	board=$1 prof=$2
	d=$OUT/ports/$board-$prof
	tbl=$P/profiles.txt
	case $board in
	pico) col=pico dcol=5 bcol=7 ;;
	*) col=esp32 dcol=6 bcol=8 ;;
	esac
	row=$(awk -v p="$prof" -v dc=$dcol -v bc=$bcol '$1 == p { print "kind=" $2 " targets=" $3 " faces=" $4 " driver=" $dc " bus=" $bc }' "$tbl")
	[ -n "$row" ] || { echo "port-$board-$prof: no row in profiles.txt" >&2; return 1; }
	set -- $row
	kind=${1#kind=} targets=${2#targets=} faces=${3#faces=} driver=${4#driver=}
	# catches parser drift only: profiles.cmake (which the CMake builds use) must read the same row from profiles.txt as awk
	# does here; it cannot tell a wrong table from a right one
	want=$(cmake -DSVF_PROFILE="$prof" -DSVF_PORT=$col -P "$P/profiles.cmake" 2>&1)
	[ "$want" = "$row" ] || { echo "port-$board-$prof: FAIL profiles.cmake says '$want', awk read '$row'" >&2; return 1; }
	greydef=
	case $kind in GRAY8) greydef=-DSVF_GREY_KIND_GRAY8=1 ;; esac
	# the faces: one is svf_face_data (mono), several are named after the file (paplg16, paplg18)
	fbytes=0
	mkdir -p "$d/faces" || return 1
	nf=$(echo "$faces" | tr ',' '\n' | wc -l)
	for f in $(echo "$faces" | tr ',' ' '); do
		if [ "$nf" -eq 1 ]; then n=svf_face_data; else n=$(basename "$f" .SVF | tr 'A-Z' 'a-z'); fi
		python3 -I "$C/bench/mkface.py" "$SVF/$f" "$d/faces/$n.c" --name "$n" --profile "${BENCH_PROFILE:-mcu-strict}" || return 1
		fbytes=$((fbytes + $(face_len "$d/faces/$n.c")))
	done
	elf=$d/svf_${board}_$prof.elf
	case $board in
	pico)
		main=$P/pico/main.c prof_c=$P/pico/profile_$prof.c drv_c=$P/pico/disp_$driver.c
		size=$ARM-size nm=$ARM-nm
		# shellcheck disable=SC2086
		"$ARM-gcc" $COMMON -mcpu=cortex-m0plus -mthumb -Os -DSVF_NO_SCALE -DSVF_TARGETS=$targets $greydef \
			-I"$P/pico/stub" -I"$P/pico" -I"$P" -I"$C/include" "$main" "$prof_c" "$drv_c" "$C"/src/*.c "$d"/faces/*.c --specs=nano.specs --specs=nosys.specs \
			-nostartfiles -Wl,-e,main $GC -o "$elf" || return 1 ;;
	esp32c3 | esp32s3)
		main=$P/esp32/main/main.c prof_c=$P/esp32/main/profile_$prof.c drv_c=$P/esp32/main/disp_$driver.c
		if [ $board = esp32c3 ]; then
			size=$ESP-size nm=$ESP-nm
			# shellcheck disable=SC2086
			"$ESP-gcc" $COMMON -march=rv32imc_zicsr_zifencei -mabi=ilp32 -Os -DSVF_NO_SCALE -DSVF_TARGETS=$targets \
				$greydef -I"$P/esp32/stub" -I"$P/esp32/main" -I"$P" -I"$C/include" "$main" "$prof_c" "$drv_c" \
				"$C"/src/*.c "$d"/faces/*.c \
				--specs=nosys.specs -nostartfiles -Wl,-e,app_main -Wl,--no-warn-rwx-segments $GC -o "$elf" || return 1
		else
			size=$XT-size nm=$XT-nm
			# shellcheck disable=SC2086
			"$XT-gcc" $COMMON -mlongcalls -Os -DSVF_ESP32S3=1 -DSVF_NO_SCALE -DSVF_TARGETS=$targets $greydef \
				-I"$P/esp32/stub" -I"$P/esp32/main" -I"$P" -I"$C/include" "$main" "$prof_c" "$drv_c" \
				"$C"/src/*.c "$d"/faces/*.c \
				--specs=nosys.specs -nostartfiles -Wl,-e,app_main $GC -o "$elf" || return 1
		fi ;;
	esac
	# one marker of each kind in the image, the row's: a second driver or profile linked in, or a marker lost to
	# --gc-sections (each is read once at run time), changes the list. Names are matched whole, wherever the symbol
	# name starts (a prefix such as _ does not hide a marker)
	got=$("$nm" "$elf" | awk '$3 ~ /svf_port_(driver|profile)_/ { print $3 }' | sort | tr '\n' ' ')
	exp="svf_port_driver_$driver svf_port_profile_$prof "
	[ "$got" = "$exp" ] || { echo "port-$board-$prof: FAIL image holds '$got', expected '$exp'" >&2; return 1; }
	res=$("$size" -A "$elf" | sizes_a)
	echo "$board $prof $fbytes $(echo "$res" | awk '{ print $2, $4, $6 }') $kind $targets" >>"${ROWS:-/dev/null}"
	small=
	if [ $board = pico ]; then # the same image with -DSVF_SMALL (svf.h "Size switches"): its row is "pico-small"
		# shellcheck disable=SC2086
		"$ARM-gcc" $COMMON -mcpu=cortex-m0plus -mthumb -Os -DSVF_SMALL -DSVF_NO_SCALE -DSVF_TARGETS=$targets $greydef \
			-I"$P/pico/stub" -I"$P/pico" -I"$P" -I"$C/include" "$main" "$prof_c" "$drv_c" "$C"/src/*.c "$d"/faces/*.c --specs=nano.specs --specs=nosys.specs \
			-nostartfiles -Wl,-e,main $GC -o "$d/small.elf" || return 1
		sres=$("$size" -A "$d/small.elf" | sizes_a)
		echo "pico-small $prof $fbytes $(echo "$sres" | awk '{ print $2, $4, $6 }') $kind $targets" >>"${ROWS:-/dev/null}"
		small=" SVF_SMALL $(echo "$sres" | awk '{ print "text", $2 }')"
	fi
	echo "port-$board-$prof: OK $(basename "$elf") $res faces $fbytes$small"
}

# sizes_a: the text, data and bss of `size -A` output on stdin (loadable sections; no debug or attribute sections)
sizes_a() {
	awk '
		$1 ~ /^\.(comment|debug|note|stack|ARM\.attributes|riscv\.attributes|xtensa\.info|xt\.)/ || NF != 3 || $1 == "section" { next }
		$1 ~ /^\.data/ { d += $2; next } $1 ~ /^\.(bss|noinit)/ { b += $2; next } { t += $2 }
		END { print "text", t + 0, "data", d + 0, "bss", b + 0 }'
}

# ch582_port: the CH582 example: (1) the bare link against c/ports/ch582/stub/ (i2c_stub.c in place of i2c.c, the SDK's
# header names as no-op stand-ins), ESP's riscv32 gcc, the image's library switches; (2) the real SDK image, when the
# SDK is installed (the Makefile of c/ports/ch582 with the WCH EVT start-up and drivers). 1 on a failure.
ch582_port() {
	d=$OUT/ports/ch582
	elf=$d/svf_ch582_mono.elf
	python3 -I "$C/bench/mkface.py" "$SVF/dos/NEODG16G.SVF" "$d/face-ch582.c" --name svf_face_data \
		--profile "${BENCH_PROFILE:-mcu-strict}" || return 1
	# shellcheck disable=SC2086
	"$ESP-gcc" $COMMON -march=rv32imac_zicsr_zifencei -mabi=ilp32 -mstrict-align -Os \
		-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0 \
		-I"$P/ch582/stub" -I"$P/ch582" -I"$P" -I"$C/include" "$P/ch582/main.c" "$P/ch582/profile_mono.c" \
		"$P/ch582/disp_sh1106.c" "$P/ch582/stub/i2c_stub.c" "$C"/src/*.c "$d/face-ch582.c" \
		--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main -Wl,--no-warn-rwx-segments $GC -o "$elf" ||
		return 1
	got=$("$ESP-nm" "$elf" | awk '$3 ~ /svf_port_(driver|profile)_/ { print $3 }' | sort | tr '\n' ' ')
	exp="svf_port_driver_sh1106 svf_port_profile_mono "
	[ "$got" = "$exp" ] || { echo "port-ch582: FAIL image holds '$got', expected '$exp'" >&2; return 1; }
	fb=$(face_len "$d/face-ch582.c")
	res=$("$ESP-size" -A "$elf" | sizes_a)
	echo "ch582 mono $fb $(echo "$res" | awk '{ print $2, $4, $6 }') MONO_PAGE 0x02" >>"${ROWS:-/dev/null}"
	echo "port-ch582: OK $(basename "$elf") $res faces $fb"
	ch582_sdk
}

# ch582_sdk: the real image of c/ports/ch582/Makefile (WCH EVT SDK, start-up code and drivers) into OUT/ports/ch582-sdk;
# prints its size line (ch582-sdk-size:) and, in the full --ports run, appends it to OUT/ports/ch582-sdk-rows.txt for
# check-sizes-md.sh --ch582-sdk. An SDK that is not installed is SKIPPED (not a failure here); a failure prints
# "ch582-sdk: FAIL <what>", sets status=1 and returns 0.
ch582_sdk() {
	sdk=${CH583_SDK:-$OPT/ch583-evt}
	# the installed tree is verified first (silent and 0 when the whole tree is absent; a damaged one stops the run), so a
	# missing Link.ld is "not installed" only when nothing is installed; a CH583_SDK named by the caller is not verified
	[ -n "${CH583_SDK:-}" ] || verify_installs "$HERE/install-toolchains.sh" ch583
	if [ ! -f "$sdk/EVT/EXAM/SRC/Ld/Link.ld" ]; then
		if [ -n "${CH583_SDK:-}" ]; then
			echo "ch582-sdk: FAIL CH583_SDK=$sdk has no EVT/EXAM/SRC/Ld/Link.ld"
			status=1
		else
			echo "ch582-sdk: SKIPPED (not installed: $sdk; c/cross/install-toolchains.sh ch583)"
		fi
		return 0
	fi
	s=$sdk/EVT/EXAM/SRC
	log=$OUT/ports/ch582-sdk.log
	# the clock the values check compiles with is the Makefile's (host-checks.sh checks that one against main.c)
	freq=$(sed -n 's/.*-DFREQ_SYS=\([0-9][0-9]*\).*/\1/p' "$P/ch582/Makefile" | head -n 1)
	[ -n "$freq" ] || { echo "ch582-sdk: FAIL no -DFREQ_SYS=<Hz> in c/ports/ch582/Makefile"; status=1; return 0; }
	# the stub's names and values against the real headers (Task 2 of the port: ch582_sdk_values.c)
	if ! msg=$("$ESP-gcc" -march=rv32imac_zicsr_zifencei -mabi=ilp32 -std=gnu99 -Wall -Wextra -Werror -DINT_SOFT \
		-DFREQ_SYS="$freq" -I"$s/StdPeriphDriver/inc" -I"$s/RVMSIS" -I"$P/ch582" -I"$P" -fsyntax-only \
		"$P/check/ch582_sdk_values.c" 2>&1); then
		echo "$msg" >&2
		echo "ch582-sdk: FAIL ch582_sdk_values.c does not compile against the SDK headers"
		status=1
		return 0
	fi
	if ! make --no-print-directory -C "$P/ch582" CROSS="$ESP-" CH583_SDK="$sdk" BUILD="$OUT/ports/ch582-sdk" OPT="$OPT" \
		>"$log" 2>&1; then
		cat "$log" >&2
		echo "ch582-sdk: FAIL make -C c/ports/ch582 (log above, $log)"
		status=1
		return 0
	fi
	line=$(grep '^svf_ch582_mono: ' "$log" | tail -n 1)
	[ -n "$line" ] || { cat "$log" >&2; echo "ch582-sdk: FAIL no size line in $log"; status=1; return 0; }
	echo "ch582-sdk-size: ${line#*: }"
	# the stack gate: a second build with the call-graph files; main's worst-case depth must stay within 1536 bytes
	sulog=$OUT/ports/ch582-sdk-su.log
	if ! make --no-print-directory -C "$P/ch582" CROSS="$ESP-" CH583_SDK="$sdk" BUILD="$OUT/ports/ch582-sdk-su" OPT="$OPT" \
		STACK_INFO=1 >"$sulog" 2>&1; then
		cat "$sulog" >&2
		echo "ch582-sdk: FAIL make STACK_INFO=1 (log above, $sulog)"
		status=1
		return 0
	fi
	# main's own call-graph file must exist, and the peak must be a positive number (a root the files do not define
	# makes stack-usage.py fail; "peak 0" would be a gate that measured nothing)
	[ -f "$OUT/ports/ch582-sdk-su/obj/main.ci" ] || { echo "ch582-sdk: FAIL no stack call-graph file obj/main.ci in $OUT/ports/ch582-sdk-su"; status=1; return 0; }
	peak=$(python3 -I "$HERE/stack-usage.py" "$OUT/ports/ch582-sdk-su/obj" main | awk '$1 == "peak" { print $2 }')
	case $peak in '' | *[!0-9]* | 0*) echo "ch582-sdk: FAIL no stack peak (empty, zero or not a number) from stack-usage.py"; status=1; return 0 ;; esac
	echo "ch582-sdk-stack: peak $peak"
	if [ "$peak" -gt 1536 ]; then
		echo "ch582-sdk: FAIL stack peak $peak of main is over 1536"
		status=1
		return 0
	fi
	# the rows line: "image text data bss highcode libISP583 stack ram"
	echo "$line" | awk '{ sub(/:$/, "", $1); print $1, $3, $5, $7, $9, $11, $13, $15 }' >>"${ROWS_SDK:-/dev/null}"
}

# port NAME [PROFILE]: builds the example NAME into OUT/ports/NAME (the commands above); 1 on a failure.
port() {
	d=$OUT/ports/$1${2:+-$2} extra=
	rm -rf "$d"
	mkdir -p "$d" || return 1
	case $1 in
	dos)
		for s in "$C"/src/*.c; do
			"$DJ-gcc" -std=c99 $W -O2 -I"$C/include" -c "$s" -o "$d/$(basename "$s" .c).o" || return 1
		done
		mkdir -p "$d/vbe" && "$DJ-gcc" -std=c99 $W -O2 -I"$P/dos" -c "$P/dos/vbe_select.c" -o "$d/vbe/vbe_select.o" || return 1
		"$DJ-gcc" -std=gnu99 $W -O2 -I"$C/include" "$P/dos/svfdemo.c" "$d"/*.o -o "$d/SVFDEMO.EXE" || return 1
		"$DJ-gcc" -std=gnu99 $W -O2 -I"$C/include" -I"$P/dos" "$P/dos/svfvesa.c" "$P/dos/vesa_lines.c" \
			"$d/vbe/vbe_select.o" "$d"/*.o -o "$d/SVFVESA.EXE" || return 1
		extra=", SVFVESA.EXE $(wc -c <"$d/SVFVESA.EXE") bytes" # one port-dos line for both programs
		elf=$d/SVFDEMO.EXE ;;
	web)
		EM_CONFIG="$EM/.emscripten" "$EM/upstream/emscripten/emcc" -std=c99 $W -O2 -I"$C/include" \
			"$P/web/svf_web.c" "$C"/src/*.c -o "$d/svf.js" -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
			-sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16 -sALLOW_MEMORY_GROWTH ||
			return 1
		elf=$d/svf.wasm ;;
	sdl)
		# check.sh builds svfsdl2/svfsdl3 into $d (its sanitizer build goes apart, into a subdirectory: the sizes are read
		# from $d only); its output is shown on a failure, else as one line without OK (the run counts the OK lines)
		# SVF_SDL_CHECK: test hook (c/cross/test-build-all.sh), the script run in place of c/ports/sdl/check.sh
		hook=
		if [ -n "${SVF_SDL_CHECK:-}" ]; then
			hook=" (test hook)"
			echo "TEST HOOK: SVF_SDL_CHECK in use, check.sh and the sdl3 verification are replaced" >&2
		fi
		(unset SVFSDL_ONLY; SDL3_PREFIX=$OPT/sdl3 SDL3_SRC=${SDL3_SRC:-$OPT/src/SDL3}; export SDL3_PREFIX SDL3_SRC
		 sh "${SVF_SDL_CHECK:-$P/sdl/check.sh}" "$d") >"$d.log" 2>&1 || { cat "$d.log"; echo "port-sdl: FAIL check.sh"; return 1; }
		for b in svfsdl2 svfsdl3; do
			[ -x "$d/$b" ] && [ -s "$d/$b" ] || { echo "port-sdl: FAIL missing $d/$b"; return 1; }
		done
		s2=$(wc -c <"$d/svfsdl2") s3=$(wc -c <"$d/svfsdl3")
		grep '^port-sdl-check: note:' "$d.log" || true
		sed -n 's/^port-sdl-check: OK /port-sdl-check-runs: /p' "$d.log" | tail -n 1
		echo "info program sdl2 $s2" >>"${ROWS:-/dev/null}"
		echo "info program sdl3 $s3" >>"${ROWS:-/dev/null}"
		echo "port-sdl: OK$hook svfsdl2 $s2 bytes, svfsdl3 $s3 bytes"
		return 0 ;;
	pico | esp32c3 | esp32s3) mcu_port "$@" || return 1; return 0 ;;
	ch582) ch582_port || return 1; return 0 ;;
	arduino)
		python3 -I "$C/bench/mkface.py" "$SVF/dos/NEODG16G.SVF" "$d/face-arduino.c" --name svf_face_data \
			--profile "${BENCH_PROFILE:-mcu-strict}" || return 1
		avrf="-mmcu=atmega328p -Os -ffunction-sections -fdata-sections -include avr/pgmspace.h"
		avrf="$avrf -DSVF_RD8(p)=pgm_read_byte(p) -DSVF_NO_SCALE -DSVF_TARGETS=0x02"
		avrf="$avrf -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0" # README: a v1 face, the v1 reader
		for s in "$C"/src/*.c "$d/face-arduino.c"; do
			"$AVR-gcc" -std=c99 $W $avrf -I"$C/include" -c "$s" -o "$d/$(basename "$s" .c).o" || return 1
		done
		"$AVR-g++" -x c++ -std=gnu++11 $W $avrf -fno-exceptions -I"$P/arduino/stub" -I"$C/include" \
			-c "$P/arduino/arduino.ino" -o "$d/arduino.o" || return 1
		elf=$d/svf_uno.elf
		"$AVR-g++" -mmcu=atmega328p $GC "$d"/*.o -o "$elf" || return 1
		size=$AVR-size
		# the same with -DSVF_SMALL (svf.h "Size switches"): the row "arduino-small" (the Uno build has NO_SCALE and the
		# AVR defaults of the other two switches are 0: expected equal to the plain row)
		mkdir -p "$d/small" || return 1
		for s in "$C"/src/*.c "$d/face-arduino.c"; do
			"$AVR-gcc" -std=c99 $W $avrf -DSVF_SMALL -I"$C/include" -c "$s" -o "$d/small/$(basename "$s" .c).o" || return 1
		done
		"$AVR-g++" -x c++ -std=gnu++11 $W $avrf -DSVF_SMALL -fno-exceptions -I"$P/arduino/stub" -I"$C/include" \
			-c "$P/arduino/arduino.ino" -o "$d/small/arduino.o" || return 1
		"$AVR-g++" -mmcu=atmega328p $GC "$d"/small/*.o -o "$d/small.elf" || return 1
		sres=$("$size" -A "$d/small.elf" | sizes_a)
		echo "arduino-small - $(face_len "$d/face-arduino.c") $(echo "$sres" | awk '{ print $2, $4, $6 }') MONO_PAGE 0x02" >>"${ROWS:-/dev/null}"
		extra=" SVF_SMALL $(echo "$sres" | awk '{ print "text", $2 }')"
		# ATmega2560 (Arduino Mega): the same sketch and face with the Uno flags (row "arduino-mega") and a feature-rich
		# link (row "arduino-mega-rich": every target, both JSET readers, JMAP, BIG, scaling on; mapped face only: NO_STREAM and the mcu-strict layout as the sketch). Flash is 256 KB, no
		# budget; the face data is in PROGMEM below 64 KB (SVF_RD8 is the near pgm_read_byte), so a row whose .text end
		# is >= 65,536 is flagged (far reads are not supported or tested) and a link that overflows fails the build.
		mflags="-mmcu=atmega2560 -Os -ffunction-sections -fdata-sections -include avr/pgmspace.h -DSVF_RD8(p)=pgm_read_byte(p)"
		for v in mega mega-rich; do
			case $v in
			mega) vf="$mflags -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0"
				tg=0x02 ;;
			mega-rich) vf="$mflags -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x1FF -DSVF_JSET_V2=1 -DSVF_JMAP=1 -DSVF_JSET_BIG=1"
				tg=0x1FF ;;
			esac
			mkdir -p "$d/$v" || return 1
			for s in "$C"/src/*.c "$d/face-arduino.c"; do
				"$AVR-gcc" -std=c99 $W $vf -I"$C/include" -c "$s" -o "$d/$v/$(basename "$s" .c).o" || return 1
			done
			"$AVR-g++" -x c++ -std=gnu++11 $W $vf -fno-exceptions -I"$P/arduino/stub" -I"$C/include" \
				-c "$P/arduino/arduino.ino" -o "$d/$v/arduino.o" || return 1
			"$AVR-g++" -mmcu=atmega2560 $GC "$d/$v"/*.o -o "$d/$v.elf" || return 1
			mres=$("$size" -A "$d/$v.elf" | sizes_a)
			echo "arduino-$v - $(face_len "$d/face-arduino.c") $(echo "$mres" | awk '{ print $2, $4, $6 }') MONO_PAGE $tg" >>"${ROWS:-/dev/null}"
			mend=$(echo "$mres" | awk '{ print $2 + $4 }')
			if [ "$mend" -ge 65536 ]; then
				echo "port-arduino: FLAG arduino-$v flash end $mend >= 65536 (far reads needed; not supported)"
			else
				echo "port-arduino: info arduino-$v ATmega2560 flash end $mend < 65536 (near reads)"
			fi
		done ;;
	esac
	case $1 in
	dos | web)
		echo "program $1 $(wc -c <"$elf")" >>"${ROWS:-/dev/null}"
		echo "port-$1: OK $(basename "$elf") $(wc -c <"$elf") bytes$extra" ;;
	*)	res=$("$size" -A "$elf" | sizes_a)
		echo "$1 - $(face_len "$d/face-arduino.c") $(echo "$res" | awk '{ print $2, $4, $6 }') MONO_PAGE 0x02" >>"${ROWS:-/dev/null}"
		echo "port-$1: OK $(basename "$elf") $res$extra" ;;
	esac
}

if [ $PORTS -eq 1 ]; then
	status=0
	if [ -n "$ONLY" ]; then # --port NAME: that port's builds only, no gate
		case $ONLY in
		pico) set -- "pico colour" "pico grey" "pico mono" ;;
		esp32) set -- "esp32c3 colour" "esp32c3 grey" "esp32c3 mono" "esp32s3 colour" "esp32s3 grey" "esp32s3 mono" ;;
		*) set -- "$ONLY" ;;
		esac
		for bp in "$@"; do
			# shellcheck disable=SC2086
			port $bp || { echo "port-$(echo $bp | tr ' ' -): FAIL"; status=1; }
		done
		exit $status
	fi
	ROWS=$OUT/ports/rows.txt
	mkdir -p "$OUT/ports" && : >"$ROWS" || exit 1
	for p in dos web sdl; do
		port $p || { echo "port-$p: FAIL"; status=1; }
	done
	for b in pico esp32c3 esp32s3; do
		for prof in colour grey mono; do
			port $b $prof || { echo "port-$b-$prof: FAIL"; status=1; }
		done
	done
	port arduino || { echo "port-arduino: FAIL"; status=1; }
	ROWS_SDK=$OUT/ports/ch582-sdk-rows.txt
	: >"$ROWS_SDK" || exit 1
	port ch582 || { echo "port-ch582: FAIL"; status=1; }
	# the "Port examples" table of SIZES.md, and its dos and web program bytes, are the measured ones (silent when they are)
	sh "$HERE/check-sizes-md.sh" "$ROWS" "$HERE/SIZES.md" || status=1
	# the SDK image (when it was built): SIZES.md's "CH582 SDK image" table holds its measured numbers
	if [ -s "$ROWS_SDK" ]; then
		sh "$HERE/check-sizes-md.sh" --ch582-sdk "$ROWS_SDK" "$HERE/SIZES.md" || status=1
	fi
	sh "$P/check/host-checks.sh" "$OUT/ports/check" || status=1
	# the emulated screens need the Pico SDK, both QEMUs and the RP2040 boot ROM (c/cross/install-toolchains.sh,
	# c/bench/install-emulators.sh)
	# a present tree is verified whether or not the screens can run: a damaged one is an error here, never "skipped"
	# (the installers report an absent one as not installed, exit 0)
	emu="qemu-rv qemu-xt" # always the pinned trees: the overrides were unset above
	verify_installs "$HERE/install-toolchains.sh" pico-sdk
	# shellcheck disable=SC2086
	verify_installs "$C/bench/install-emulators.sh" rp2040js bootrom $emu
	if [ -f "$OPT/pico-sdk-2.3.1/pico_sdk_init.cmake" ]; then
		PICO_SDK_PATH=$OPT/pico-sdk-2.3.1 PICO_TOOLCHAIN_PATH=$OPT/arm-gnu-toolchain-15.2.rel1 \
			sh "$P/check/test_pico_cmake.sh" >"$OUT/ports/pico-cmake.log" 2>&1 ||
			{ cat "$OUT/ports/pico-cmake.log" >&2; echo "port-check-pico-cmake: FAIL"; status=1; }
	fi
	# the screens: run-screens.sh must exist (a missing script is a failure, never a skip). Under SVF_REQUIRE_SCREENS=1,
	# which this run sets, what run-screens.sh, test_pico_screen.sh and the unit tests below find missing is a failure
	export SVF_REQUIRE_SCREENS=1
	if [ ! -f "$P/check/run-screens.sh" ]; then
		echo "screens: FAIL c/ports/check/run-screens.sh is missing"
		status=1
	elif ! miss=$(screens_missing); then
		echo "screens: FAIL run-screens.sh --missing"
		status=1
	elif [ -n "$miss" ]; then
		echo "screens: SKIPPED (missing: $miss)"
	else
		sh "$P/check/run-screens.sh" "$OUT/screens" || status=1
		OUT="$OUT/screens" sh "$P/check/test_pico_screen.sh" || status=1
		sh "$P/check/test_run_screens.sh" || status=1
	fi
	# the unit tests of c/ports/check: silent on success, one OK line each, any failure fails the run; a missing tool
	# (node, Pillow) is "unit NAME: SKIPPED (missing: ...)" and, under SVF_REQUIRE_SCREENS=1, a failure
	unit() { # NAME NEED CMD...   (NEED: Pillow, or the program that runs the test)
		n=$1 need=$2
		shift 2
		ok=n # n: the tool is missing
		if [ "$need" = Pillow ]; then
			python3 -I -c 'import PIL' 2>/dev/null && ok=
		elif [ -x "$need" ]; then ok=; fi
		if [ -n "$ok" ]; then
			echo "unit $n: SKIPPED (missing: $need)"
			[ "${SVF_REQUIRE_SCREENS:-}" != 1 ] || status=1
		elif msg=$("$@" 2>&1); then echo "port-check-unit-$n: OK"; else echo "$msg" >&2; echo "port-check-unit-$n: FAIL"; status=1; fi
	}
	unit esp-screen Pillow python3 -I "$P/check/test_esp_screen.py"
	unit screens Pillow python3 -I "$P/check/test_screens.py"
	NODE=${NODE:-$OPT/node-v24.13.0-linux-x64/bin/node}
	unit panels "$NODE" "$NODE" --test "$P/check/test_panels.mjs"
	exit $status
fi

HOSTCC=${HOSTCC:-gcc}
try host-gcc "$(version "$HOSTCC")" "$HOSTCC" size "-O2" "" ""

CLANG=$OPT/llvm-23.1.3/bin/clang
try clang "$(version "$CLANG")" "$CLANG" "$OPT/llvm-23.1.3/bin/llvm-size" "-O2" "" ""

try djgpp "$(version "$DJ-gcc")" "$DJ-gcc" "$DJ-size" "-O2" "" ".exe"

try cortex-m0plus "$(version "$ARM-gcc")" "$ARM-gcc" "$ARM-size" "-mcpu=cortex-m0plus -mthumb -Os" \
	"--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf" \
	"SVF_SMALL:-DSVF_SMALL SVF_MERGE_WORDS=0:-DSVF_MERGE_WORDS=0 SVF_GRAY8_LUT1=0:-DSVF_GRAY8_LUT1=0 SVF_SCALE_FAST=0:-DSVF_SCALE_FAST=0 JSET_V1:-DSVF_JSET_V2=0 JSET_V2:-DSVF_JSET_V1=0 JSET_TRUSTED:-DSVF_JSET_TRUSTED=1 JSET_POP4=0:-DSVF_JSET_POP4=0 JSET_BIG:-DSVF_JSET_BIG=1"

# RP2350's Arm core: the same tarball and link as cortex-m0plus; no budget (the 8 KB budget is the RP2040's, the test keys on
# cortex-m0plus)
try cortex-m33 "$(version "$ARM-gcc")" "$ARM-gcc" "$ARM-size" "-mcpu=cortex-m33 -mthumb -Os" \
	"--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"

try avr-atmega328p "$(version "$AVR-gcc")" "$AVR-gcc" "$AVR-size" \
	"-mmcu=atmega328p -Os -include avr/pgmspace.h -DSVF_RD8(p)=pgm_read_byte(p)" "" ".elf" \
	"SVF_SMALL:-DSVF_SMALL SVF_SCALE_FAST=0:-DSVF_SCALE_FAST=0 JSET_BOTH:-DSVF_JSET_V2=1 JSET_V2:-DSVF_JSET_V1=0,-DSVF_JSET_V2=1 JSET_TRUSTED:-DSVF_JSET_TRUSTED=1 JSET_BIG:-DSVF_JSET_BIG=1" # the AVR defaults of MERGE_WORDS, GRAY8_LUT1 and JSET_POP4 are 0 already, of SVF_JSET_V2 too (v1 reader alone)

# ATmega2560 (Arduino Mega, 256 KB flash): the same probe and switch columns; PROGMEM data below 64 KB only (near pgm_read_byte)
try avr-atmega2560 "$(version "$AVR-gcc")" "$AVR-gcc" "$AVR-size" \
	"-mmcu=atmega2560 -Os -include avr/pgmspace.h -DSVF_RD8(p)=pgm_read_byte(p)" "" ".elf" \
	"SVF_SMALL:-DSVF_SMALL SVF_SCALE_FAST=0:-DSVF_SCALE_FAST=0 JSET_BOTH:-DSVF_JSET_V2=1 JSET_V2:-DSVF_JSET_V1=0,-DSVF_JSET_V2=1 JSET_TRUSTED:-DSVF_JSET_TRUSTED=1 JSET_BIG:-DSVF_JSET_BIG=1"

try esp32s3-xtensa "$(version "$XT-gcc")" "$XT-gcc" "$XT-size" "-mlongcalls -Os" \
	"--specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"

# The original ESP32 (Xtensa LX6, e.g. Odroid-Go): the same flags and link as esp32s3 (no S3 vector extension is used by either); compile and size only. No port image: see SIZES.md.
try esp32-xtensa "$(version "$XT32-gcc")" "$XT32-gcc" "$XT32-size" "-mlongcalls -Os" \
	"--specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"

try esp32c3-riscv32 "$(version "$ESP-gcc")" "$ESP-gcc" "$ESP-size" \
	"-march=rv32imc_zicsr_zifencei -mabi=ilp32 -Os" "--specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"

# RP2350's RISC-V core (Hazard3) with pico-sdk 2.3.1's flags for rp2350-riscv (from the build's flags.make); Raspberry Pi's
# riscv32-pico-elf-gcc 16.1.0, not the ESP gcc, which rejects -mcpu=hazard3-rp2350. No budget, as cortex-m33.
try hazard3-rp2350 "$(version "$PRV-gcc")" "$PRV-gcc" "$PRV-size" "-mcpu=hazard3-rp2350 -mstrict-align -Os" \
	"--specs=nosys.specs -nostartfiles -Wl,-e,main" ".elf"

export EM_CONFIG="$EM/.emscripten"
try wasm-emcc "$(version "$EM/upstream/emscripten/emcc")" "$EM/upstream/emscripten/emcc" - "-O2" "" ".wasm"

echo
echo "| toolchain | version | profile | text | data | bss |"
echo "|---|---|---|---:|---:|---:|"
cat "$rows"
if [ -s "$vrows" ]; then # the size switches: the same profiles with the speed features off (svf.h "Size switches")
	echo
	echo "Size switches:"
	echo
	echo "| toolchain | version | profile [switch] | text | data | bss |"
	echo "|---|---|---|---:|---:|---:|"
	cat "$vrows"
	# the "Size switches" tables of SIZES.md (Cortex-M0+ and AVR) are the measured ones (silent when they are)
	sh "$HERE/check-sizes-md.sh" --switches "$rows" "$vrows" "$HERE/SIZES.md" || status=1
fi
exit $status
