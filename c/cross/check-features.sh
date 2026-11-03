#!/bin/sh
# check-features.sh [OUT] [--uno NAME:FACE.SVF:MAXFLASH ...] - the size and symbol gate of the library's feature switches.
#
# Builds c/src/*.c and links c/cross/probe.c (-DPROFILE=1, the P1 probe of build-all.sh, its empty -DPROFILE=0 probe
# linked with the -DSVF_NO_SCALE objects subtracted, as build-all.sh's P0) for every CONFIG below on both toolchains (avr: avr-gcc 16.1.0, atmega328p; m0plus: arm-none-eabi-gcc 15.2.1,
# Cortex-M0+), with build-all.sh's flags (-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections, --gc-sections).
# Writes OUT/features/rows.txt, one line a build: "TOOLCHAIN CONFIG text rodata data bss" (OUT defaults to c/build/cross-features;
# text is Berkeley `size` text, rodata included, as the tables of SIZES.md; rodata the .rodata* sections of `size -A`, a part of
# text, informational). Then
#   - check-sizes-md.sh --features: the gated rows (minimal on both toolchains, default on m0plus) equal the "Minimal config"
#     table of SIZES.md exactly (text, rodata, data, bss); other rows are printed as "info" lines;
#   - the symbol rule: check_absent CONFIG PREFIX... below; the linked probe's `nm --defined-only` has no symbol with those
#     prefixes (a symbol of an excluded feature that survived --gc-sections is a leak);
#   - the strings rule: the linked probe's .rodata*/.data (objcopy -O binary) contain none of JMAP, jmap, BIG (the library
#     has no strings: the JSET magic is compared byte by byte, never stored);
#   - --uno NAME:FACE.SVF:MAXFLASH (any number): the Arduino image of build-all.sh's `port arduino` (the minimal flags) with
#     FACE instead of NEODG16G; its flash (text + data) may not exceed MAXFLASH bytes (faces outside the repository).
# The strings rule scans: avr the linked image's .text (AVR read-only data lives there; .rodata/.data are empty) for JMAP and
# jmap only (BIG is 3 letters, a false-positive risk in code bytes); the other toolchains .rodata* and .data for JMAP, jmap
# and BIG. An objcopy failure is a failure of the gate.
# Prints "features: OK" when every gate holds; exit 1 otherwise, 2 for a usage error. A missing toolchain FAILS (exit 1).
#
# Adding a feature (Tasks 5, 7, 13, 17, 18): a CONFIGS entry (NAME:flags, flags joined by commas), its row in the table, and
# check_absent calls.
#
# Test hooks (c/cross/test-check-features.sh): FEATURES_ROWS_HOOK=FILE uses FILE as the rows (no toolchain, no build),
# FEATURES_NM_HOOK=FILE as the symbols ("TOOLCHAIN CONFIG SYMBOL" lines), FEATURES_SIZES_MD=FILE as SIZES.md,
# FEATURES_STRINGS_HOOK=FILE as extracted image bytes ("TOOLCHAIN CONFIG TEXT" lines), FEATURES_LINKLOG_HOOK=FILE as the
# failed P1 link log of avr allon, FEATURES_UNO_HOOK=FILE as the Uno sizes ("NAME text data bss" lines, size -A numbers).
set -u
HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
OPT=${OPT:-$HOME/opt}

# CONFIGS: NAME:flags (flags joined by commas). minimal = the Uno flags of c/ports/arduino/README.md (without the
# -include/-DSVF_RD8 of the AVR toolchain, which TC_avr carries); default = P1 of build-all.sh; allon = every switch 1; minimal+RECOG = minimal with SVF_JMAP_RECOG=1 (info row: the cost of the JMAP recognition); minimal+JMAP = minimal with SVF_JMAP=1 (SVF_JMAP_LIST follows: the cost of the JMAP reader with the LIST reader); minimal+JMAP+nolist = the same with -DSVF_JMAP_LIST=0 (the JMAP reader alone); ksonly = the KS-only build -DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0 (LIST on; -Werror clean); ksonly+nolist = the same with -DSVF_JMAP_LIST=0; these rows are info rows held by BUDGETS; minimal+BIG = minimal with SVF_JSET_BIG=1 (info row: the cost of the widened limits, version 1 reader); minimal+BIG+V2 = the same with the version 2 reader too (-DSVF_JSET_V2=1).
CONFIGS="minimal:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JSET_V2=0
default:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT
minimal+RECOG:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JSET_V2=0,-DSVF_JMAP_RECOG=1
minimal+JMAP:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JSET_V2=0,-DSVF_JMAP=1
minimal+JMAP+nolist:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JSET_V2=0,-DSVF_JMAP=1,-DSVF_JMAP_LIST=0
ksonly:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JMAP=1,-DSVF_JSET_V1=0,-DSVF_JSET_V2=0
ksonly+nolist:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JMAP=1,-DSVF_JSET_V1=0,-DSVF_JSET_V2=0,-DSVF_JMAP_LIST=0
minimal+BIG:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JSET_V2=0,-DSVF_JSET_BIG=1
minimal+BIG+V2:-DSVF_NO_SCALE,-DSVF_TARGETS=0x02,-DSVF_NO_STREAM,-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,-DSVF_JSET_V2=1,-DSVF_JSET_BIG=1
allon:-DSVF_JSET_V1=1,-DSVF_JSET_V2=1,-DSVF_JSET_POP4=1,-DSVF_MERGE_WORDS=1,-DSVF_GRAY8_LUT1=1,-DSVF_SCALE_FAST=1,-DSVF_JMAP=1,-DSVF_JSET_BIG=1"
# BUDGETS: "TOOLCHAIN CONFIG MAXTEXT" (PL-6 of the JMAP-LIST plan): the row's text may not exceed MAXTEXT; the recorded pre-LIST rows
# plus the design's bands (minimal+JMAP: AVR 14932 + 600, M0+ 7338 + 350; +nolist 14932 + 100, 7338 + 60; ksonly 13048 + 600,
# 6550 + 350; ksonly+nolist 13148 / 6610; minimal+RECOG 13210 + 40, 6326 + 40).
BUDGETS="avr minimal+JMAP 15532
m0plus minimal+JMAP 7688
avr minimal+JMAP+nolist 15032
m0plus minimal+JMAP+nolist 7398
avr ksonly 13648
m0plus ksonly 6900
avr ksonly+nolist 13148
m0plus ksonly+nolist 6610
avr minimal+RECOG 13250
m0plus minimal+RECOG 6366"
TOOLCHAINS="avr m0plus"
INFO_OVERFLOW="allon" # configs whose link may overflow the target: an info line (they are not gated)

# check_absent CONFIG PREFIX...: no symbol of CONFIG (on any toolchain) may start with one of the prefixes.
absent_rules() {
	check_absent minimal pop4 svf_open_stream svf__scale   # no POP4 (V2 reader off), SVF_NO_STREAM, SVF_NO_SCALE
	# jmap_fields (the entry decoder) is a real, non-inlined symbol of the minimal+JMAP and ksonly rows, so these
	# rules see a leak: with SVF_JMAP and SVF_JMAP_RECOG 0 (minimal, and the MCU default) no jmap function may be linked in;
	# the recognition's jmap_fallback is inlined (no symbol) and is guarded by the exact size rows instead
	check_absent minimal jmap
	check_absent default jmap
	check_absent minimal+BIG jmap                          # BIG is independent of JMAP: no jmap function in the MCU rows with BIG either
	# the LIST reader's statics are named jlist_* (PL-2) and compiled only under SVF_JMAP && SVF_JMAP_LIST: no such symbol where
	# the LIST reader is off (the MCU rows, and the +nolist rows with SVF_JMAP on)
	check_absent minimal jlist
	check_absent default jlist
	check_absent minimal+BIG jlist
	check_absent minimal+BIG+V2 jlist
	check_absent minimal+JMAP+nolist jlist
	check_absent ksonly+nolist jlist
	check_absent default svf_open_stream svf__scale        # SVF_NO_STREAM, SVF_NO_SCALE (pop4 is on: POP4 defaults to 1)
}

COMMON="-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections"
GC="-Wl,--gc-sections"
ARM=$OPT/arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi
AVR=$OPT/avr-gcc-16.1.0/bin/avr
SVF=$(dirname "$C")/svf

usage() { echo "usage: check-features.sh [OUT] [--uno NAME:FACE.SVF:MAXFLASH ...]" >&2; exit 2; }
fail() { echo "features: FAIL: $1" >&2; exit 1; }

OUT=
UNO=
while [ $# -gt 0 ]; do
	case $1 in
	--uno)
		shift
		[ $# -gt 0 ] || usage
		while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do
			case $1 in
			*:*:*) ;;
			*) echo "check-features.sh: --uno wants NAME:FACE.SVF:MAXFLASH, got '$1'" >&2; usage ;;
			esac
			mx=${1##*:}
			case $mx in '' | *[!0-9]*) echo "check-features.sh: MAXFLASH is not a number in '$1'" >&2; usage ;; esac
			UNO="$UNO $1"
			shift
		done ;;
	-*) usage ;;
	*) [ -z "$OUT" ] || usage; OUT=$1; shift ;;
	esac
done
OUT=${OUT:-$C/build/cross-features}
MD=${FEATURES_SIZES_MD:-$HERE/SIZES.md}

if [ -n "$(ls -A "$OUT" 2>/dev/null)" ] && [ ! -f "$OUT/.svf-cross-features" ]; then
	fail "refusing to use $OUT: not empty and not a check-features output directory (no .svf-cross-features)"
fi
mkdir -p "$OUT/features" || exit 1
OUT=$(cd "$OUT" && pwd) || exit 1
: >"$OUT/.svf-cross-features"
F=$OUT/features
rows=$F/rows.txt syms=$F/syms.txt strs=$F/strings.txt defs=$F/defines.txt
: >"$rows"; : >"$syms"; : >"$strs"; : >"$defs"
status=0

# tc_setup TOOLCHAIN: sets CC SIZE NM OBJCOPY TCFLAGS LDFLAGS EXT; 1 when the toolchain is missing.
tc_setup() {
	case $1 in
	avr)
		CC=$AVR-gcc SIZE=$AVR-size NM=$AVR-nm OBJCOPY=$AVR-objcopy
		TCFLAGS="-mmcu=atmega328p -Os -include avr/pgmspace.h -DSVF_RD8(p)=pgm_read_byte(p)" LDFLAGS= ;;
	m0plus)
		CC=$ARM-gcc SIZE=$ARM-size NM=$ARM-nm OBJCOPY=$ARM-objcopy
		TCFLAGS="-mcpu=cortex-m0plus -mthumb -Os"
		LDFLAGS="--specs=nano.specs --specs=nosys.specs -nostartfiles -Wl,-e,main" ;;
	esac
	for t in "$CC" "$SIZE" "$NM" "$OBJCOPY"; do
		[ -x "$t" ] || { echo "features: FAIL: $1: not found: $t (c/cross/install-toolchains.sh)" >&2; return 1; }
	done
}

# measure ELF: "text rodata data bss" (text, data, bss of `size`; rodata of the .rodata* sections of `size -A`).
measure() {
	set -- "$1" $("$SIZE" "$1" | awk 'NR == 2 { print $1, $2, $3 }')
	[ $# -eq 4 ] || return 1
	ro=$("$SIZE" -A "$1" | awk '$1 ~ /^\.rodata/ { r += $2 } END { print r + 0 }')
	echo "$2 $ro $3 $4"
}

# base_p0 TOOLCHAIN: sets T0 R0 D0 B0, the empty probe (-DPROFILE=0) linked with the objects of build-all.sh's "noscale" set
# (-DSVF_NO_SCALE alone): the startup code and main, subtracted from every row as build-all.sh subtracts its P0.
base_p0() {
	d=$F/$1-base
	rm -rf "$d"; mkdir -p "$d" || return 1
	for s in "$C"/src/*.c; do
		# shellcheck disable=SC2086
		$CC $COMMON $TCFLAGS -DSVF_NO_SCALE -I"$C/include" -c "$s" -o "$d/$(basename "$s" .c).o" 2>"$d/log" ||
			{ echo "features: FAIL: $1 P0: compiling $s"; sed 's/^/  /' "$d/log"; return 1; }
	done
	# shellcheck disable=SC2086
	$CC $COMMON $TCFLAGS -DSVF_NO_SCALE -DPROFILE=0 -I"$C/include" "$C/cross/probe.c" "$d"/*.o $GC $LDFLAGS \
		-o "$d/p0.elf" 2>"$d/log" || { echo "features: FAIL: $1: linking P0"; sed 's/^/  /' "$d/log"; return 1; }
	v=$(measure "$d/p0.elf") || return 1
	set -- $v
	[ $# -eq 4 ] || return 1
	T0=$1 R0=$2 D0=$3 B0=$4
}

# overflow_of LOG: the N of "overflowed by N bytes" in a link log, when that is all that went wrong; else nothing (as build-all.sh:
# GNU ld goes on after a region overflow, so an undefined reference or any other error line must not hide behind it).
overflow_of() {
	[ -z "$(grep -i 'error\|undefined reference\|cannot find\|multiple definition' "$1" | grep -v 'overflowed by\|ld returned')" ] &&
		sed -n 's/.*overflowed by \([0-9][0-9]*\) bytes.*/\1/p' "$1" | head -n 1
}

# link_verdict TOOLCHAIN CONFIG LOG: a P1 link that failed. A config of INFO_OVERFLOW whose log holds only a region overflow is
# an info line (0); anything else prints the log and fails (1).
link_verdict() {
	over=$(overflow_of "$3")
	case " $INFO_OVERFLOW " in
	*" $2 "*) if [ -n "$over" ]; then echo "info: $1 $2 does not link: region overflowed by $over bytes"; return 0; fi ;;
	esac
	echo "features: FAIL: $1 $2: linking P1"; sed 's/^/  /' "$3"
	return 1
}

# scan_strings TOOLCHAIN CONFIG FILE: FILE (extracted bytes) must hold none of the strings; avr scans .text (see the header)
# for JMAP/jmap, the others .rodata*/.data for JMAP/jmap/BIG. Appends a line to $strs on a hit.
scan_strings() {
	case $1 in
	avr) set -- "$1" "$2" "$3" -e JMAP -e jmap ;;
	*) set -- "$1" "$2" "$3" -e JMAP -e jmap -e BIG ;;
	esac
	tc=$1 cfg=$2 f=$3
	shift 3
	if grep -a -q "$@" "$f"; then echo "$tc $cfg: a JMAP/jmap/BIG string in the linked image" >>"$strs"; fi
}

# uno_check NAME TEXT DATA BSS MAXFLASH: the flash gate (text + data may not exceed MAXFLASH).
uno_check() {
	flash=$(($2 + $3))
	if [ $flash -gt "$5" ]; then
		echo "features: uno $1: flash $flash > $5 (+$((flash - $5))); RAM $(($3 + $4))"
		return 1
	fi
	echo "uno $1: flash $flash <= $5 (text $2 + data $3), RAM $(($3 + $4))"
}

# build_one TOOLCHAIN CONFIG FLAGS: objects, the P1 probe, the row (minus P0); the symbols and the strings of P1. A config that
# is not gated and does not fit the target (allon on the Uno) is an "info" line, not a failure.
build_one() {
	tc=$1 cfg=$2 flags=$(echo "$3" | tr , ' ')
	d=$F/$tc-$cfg
	rm -rf "$d"; mkdir -p "$d" || return 1
	# the switch defaults the toolchain's preprocessor gives svf.h (the defaults rule below): "TC CONFIG JMAP RECOG LIST"
	# shellcheck disable=SC2086
	echo "$tc $cfg" $(echo '#include "svf.h"' | $CC $TCFLAGS $flags -I"$C/include" -x c -dM -E - 2>"$d/log" |
		awk '$2 == "SVF_JMAP" { j = $3 } $2 == "SVF_JMAP_RECOG" { r = $3 } $2 == "SVF_JMAP_LIST" { l = $3 } END { print j, r, l }') >>"$defs"
	for s in "$C"/src/*.c; do
		o=$(basename "$s" .c).o
		# shellcheck disable=SC2086
		$CC $COMMON $TCFLAGS $flags -I"$C/include" -c "$s" -o "$d/$o" 2>"$d/log" ||
			{ echo "features: FAIL: $tc $cfg: compiling $s"; sed 's/^/  /' "$d/log"; return 1; }
	done
	# shellcheck disable=SC2086
	if ! $CC $COMMON $TCFLAGS $flags -DPROFILE=1 -I"$C/include" "$C/cross/probe.c" "$d"/*.o $GC $LDFLAGS \
		-o "$d/p1.elf" 2>"$d/log"; then
		link_verdict "$tc" "$cfg" "$d/log"
		return $?
	fi
	v=$(measure "$d/p1.elf") || return 1
	set -- $v
	[ $# -eq 4 ] || return 1
	echo "$tc $cfg $(($1 - T0)) $(($2 - R0)) $(($3 - D0)) $(($4 - B0))" >>"$rows"
	"$NM" --defined-only "$d/p1.elf" | awk -v t="$tc" -v c="$cfg" 'NF == 3 { print t, c, $3 }' >>"$syms"
	case $tc in avr) secs="-j .text" ;; *) secs="-j .rodata* -j .data" ;; esac
	# shellcheck disable=SC2086
	set -f
	"$OBJCOPY" -O binary $secs "$d/p1.elf" "$d/ro.bin" 2>"$d/objcopy.log" ||
		{ set +f; echo "features: FAIL: $tc $cfg: objcopy failed"; sed 's/^/  /' "$d/objcopy.log"; return 1; }
	set +f
	scan_strings "$tc" "$cfg" "$d/ro.bin"
}

# uno_build NAME FACE MAXFLASH: the Arduino image of build-all.sh with FACE; flash = text + data of the linked image.
uno_build() {
	un=$1 face=$2 max=$3
	tc_setup avr || return 1
	d=$F/uno-$un
	rm -rf "$d"; mkdir -p "$d" || return 1
	[ -f "$face" ] || { echo "features: FAIL: uno $un: no face $face"; return 1; }
	python3 -I "$C/bench/mkface.py" "$face" "$d/face.c" --name svf_face_data --profile mcu-strict || return 1
	# the flags of c/ports/arduino/README.md (= the "minimal" config): one place
	mf=$(echo "$CONFIGS" | sed -n 's/^minimal://p' | tr , ' ')
	avrf="-mmcu=atmega328p -Os -ffunction-sections -fdata-sections -include avr/pgmspace.h -DSVF_RD8(p)=pgm_read_byte(p) $mf"
	W="-Wall -Wextra -Werror"
	for s in "$C"/src/*.c "$d/face.c"; do
		# shellcheck disable=SC2086
		"$AVR-gcc" -std=c99 $W $avrf -I"$C/include" -c "$s" -o "$d/$(basename "$s" .c).o" || return 1
	done
	# shellcheck disable=SC2086
	"$AVR-g++" -x c++ -std=gnu++11 $W $avrf -fno-exceptions -I"$C/ports/arduino/stub" -I"$C/include" \
		-c "$C/ports/arduino/arduino.ino" -o "$d/arduino.o" || return 1
	"$AVR-g++" -mmcu=atmega328p $GC "$d"/*.o -o "$d/uno.elf" || return 1
	# build-all.sh's sizes_a (size -A, loadable sections): the figure of the arduino row of SIZES.md "Port examples"
	set -- $("$AVR-size" -A "$d/uno.elf" | awk '
		$1 ~ /^\.(comment|debug|note|stack|ARM\.attributes|riscv\.attributes|xtensa\.info|xt\.)/ || NF != 3 || $1 == "section" { next }
		$1 ~ /^\.data/ { d += $2; next } $1 ~ /^\.(bss|noinit)/ { b += $2; next } { t += $2 }
		END { print t + 0, d + 0, b + 0 }')
	uno_check "$un" "$1" "$2" "$3" "$max"
}

if [ -n "${FEATURES_ROWS_HOOK:-}" ]; then
	cp "$FEATURES_ROWS_HOOK" "$rows" || exit 1
	[ -z "${FEATURES_NM_HOOK:-}" ] || cp "$FEATURES_NM_HOOK" "$syms" || exit 1
	# FEATURES_STRINGS_HOOK=FILE: lines "TOOLCHAIN CONFIG TEXT", TEXT standing for the extracted bytes
	if [ -n "${FEATURES_STRINGS_HOOK:-}" ]; then
		while read -r htc hcfg htext; do
			printf '%s\n' "$htext" >"$F/hook.bin"
			scan_strings "$htc" "$hcfg" "$F/hook.bin"
		done <"$FEATURES_STRINGS_HOOK"
	fi
	# FEATURES_DEFINES_HOOK=FILE: lines "TOOLCHAIN CONFIG JMAP RECOG LIST" (the preprocessor's SVF_JMAP, SVF_JMAP_RECOG and SVF_JMAP_LIST)
	[ -z "${FEATURES_DEFINES_HOOK:-}" ] || cp "$FEATURES_DEFINES_HOOK" "$defs" || exit 1
	# FEATURES_LINKLOG_HOOK=FILE: a failed P1 link log of avr allon
	if [ -n "${FEATURES_LINKLOG_HOOK:-}" ]; then
		link_verdict avr allon "$FEATURES_LINKLOG_HOOK" || status=1
	fi
else
	for tc in $TOOLCHAINS; do
		tc_setup "$tc" || exit 1
	done
	msg=$(OPT=$OPT sh "$HERE/install-toolchains.sh" --verify arm avr 2>&1) ||
		{ echo "$msg" >&2; fail "install verification failed: install-toolchains.sh --verify arm avr"; }
	for tc in $TOOLCHAINS; do
		tc_setup "$tc" || exit 1
		base_p0 "$tc" || exit 1
		for entry in $(echo "$CONFIGS" | tr '\n' ' '); do
			build_one "$tc" "${entry%%:*}" "${entry#*:}" || status=1
		done
	done
	[ $status -eq 0 ] || exit 1
fi

# the size gate
sh "$HERE/check-sizes-md.sh" --features "$rows" "$MD" || status=1

# the symbol rule
check_absent() {
	cfg=$1
	shift
	for p in "$@"; do
		awk -v c="$cfg" -v p="$p" '$2 == c && index($3, p) == 1 { print "features: FAIL: " $1 " " $2 ": symbol " $3 " is linked (prefix " p ")"; bad = 1 }
			END { exit bad }' "$syms" >&2 || status=1
	done
}
absent_rules

# the defaults rule: what `$CC -dM -E` of svf.h prints for the config's flags: SVF_JMAP, SVF_JMAP_RECOG and SVF_JMAP_LIST are 0 for
# the MCU configs, SVF_JMAP and SVF_JMAP_LIST 1 where a config asks for SVF_JMAP (LIST follows it), SVF_JMAP_LIST 0 where the
# config says so, SVF_JMAP_RECOG 1 for minimal+RECOG
while read -r dtc dcfg dj dr dl; do
	case $dcfg in
	minimal | default | minimal+BIG | minimal+BIG+V2) want="0 0 0" ;;
	minimal+RECOG) want="0 1 0" ;;
	minimal+JMAP | ksonly | allon) want="1 - 1" ;;
	minimal+JMAP+nolist | ksonly+nolist) want="1 - 0" ;;
	*) continue ;;
	esac
	set -- $want
	{ [ "$dj" = "$1" ] && { [ "$2" = - ] || [ "$dr" = "$2" ]; } && [ "$dl" = "$3" ]; } ||
		{ echo "features: FAIL: $dtc $dcfg: svf.h defines SVF_JMAP $dj SVF_JMAP_RECOG $dr SVF_JMAP_LIST $dl, wanted $1 $2 $3" >&2; status=1; }
done <"$defs"
if [ ! -s "$defs" ] && { [ -z "${FEATURES_ROWS_HOOK:-}" ] || [ -n "${FEATURES_DEFINES_HOOK:-}" ]; }; then
	echo "features: FAIL: no SVF_JMAP defaults were probed" >&2
	status=1
fi

# the budget rule (PL-6): a budgeted row's text may not exceed its budget. Once the rows hold any budgeted config, all must be there.
if grep -q -e ' minimal+JMAP ' -e ' ksonly ' -e ' minimal+RECOG ' -e ' ksonly+nolist ' -e ' minimal+JMAP+nolist ' "$rows" ||
	[ -z "${FEATURES_ROWS_HOOK:-}" ]; then
	echo "$BUDGETS" | while read -r btc bcfg bmax; do
		btext=$(awk -v t="$btc" -v c="$bcfg" '$1 == t && $2 == c { print $3 }' "$rows")
		if [ -z "$btext" ]; then
			echo "features: FAIL: $btc $bcfg: no row to check against budget $bmax" >&2
		elif [ "$btext" -gt "$bmax" ]; then
			echo "features: FAIL: $btc $bcfg text $btext over budget $bmax" >&2
		fi
	done 2>"$F/budget.txt"
	if [ -s "$F/budget.txt" ]; then
		cat "$F/budget.txt" >&2
		status=1
	fi
fi

# the strings rule
if [ -s "$strs" ]; then
	sed 's/^/features: FAIL: /' "$strs" >&2
	status=1
fi

# the Uno images
for u in $UNO; do
	n=${u%%:*} rest=${u#*:}
	if [ -n "${FEATURES_ROWS_HOOK:-}" ]; then # a hook run builds nothing: FEATURES_UNO_HOOK=FILE has lines "NAME text data bss"
		[ -n "${FEATURES_UNO_HOOK:-}" ] || continue
		set -- $(grep "^$n " "$FEATURES_UNO_HOOK") || { echo "features: FAIL: no uno hook line for $n"; status=1; continue; }
		uno_check "$n" "$2" "$3" "$4" "${rest##*:}" >&2 || status=1
		continue
	fi
	uno_build "$n" "${rest%:*}" "${rest##*:}" || status=1
done

[ $status -eq 0 ] || exit 1
echo "features: OK"
