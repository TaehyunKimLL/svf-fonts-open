#!/bin/sh
# check.sh [OUT] - builds svfsdl2 and svfsdl3 (and, once, an ASAN/UBSAN svfsdl2 in OUT/asan), runs the headless matrix under
# SDL_VIDEODRIVER=dummy and holds every dump to sdl_check.py (the Python reference and its C oracle). Last line
# `port-sdl-check: OK sdl2 <n> runs, sdl3 <n> runs, sum=<fnv1a of the xrgb8888 mapped dump>`; any failure prints
# `port-sdl-check: FAIL <why>` and exits 1.
#   SVFSDL_ONLY=2|3   build and run one SDL only; the last line then reads `port-sdl-check: OK sdl<N> only: <n> runs, with ASAN|no ASAN,
#                     sum=<..>` (the ASAN runs belong to SDL2; the cross-SDL identity is not checked)
#   SDL3_PREFIX       the SDL3 install (default $HOME/opt/sdl3); SDL3_SRC the fork tree it was built from (default $HOME/opt/src/SDL3)
#   Per SDL: 5 kinds x {mapped, --stream}, --syllable-cache, --present texture, --present texture-direct (exit 0, no dump),
#   every kind at 641x479 (pitch padding); index8 (mapped, --stream, --threshold 1 / 255, --present texture); gray at 1/2/4/8
#   bits x MSB/LSB, gray --stream, gray --present texture, gray 1 bit --threshold 1 / 255; --alpha-demo (mapped, --stream,
#   --present texture, with --gray-bits); rgb555 and bgr24 --present texture; xrgb8888 with --threshold --lsb-first (ignored); the small 161x101 surface (gray 1/2/4
#   x both orders, index8, rgb565); then the cross-SDL byte identity, the ASAN runs (rgb565, gray 4 --stream, --alpha-demo, --alpha-demo --present texture;
#   counted under sdl2) and the expected-failure runs (not counted). Every run checks the SDL pixel format the surface got
#   against the name given to run_case, and every index8 / gray surface-present run also compares its --shot with a palette
#   computed in sdl_check.py. A rerun removes only what a run writes here (d2-*/d3-* dumps, their diff PNGs and BMPs, bad.dump).
set -u
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
SDL3_PREFIX=${SDL3_PREFIX:-$HOME/opt/sdl3}
SDL3_SRC=${SDL3_SRC:-$HOME/opt/src/SDL3}
only=${SVFSDL_ONLY:-}
case "$only" in "" | 2 | 3) ;; *) echo "port-sdl-check: FAIL SVFSDL_ONLY=$only (empty, 2 or 3)"; exit 1 ;; esac
export SDL3_PREFIX
fail() { echo "port-sdl-check: FAIL $*"; exit 1; }
want() { [ -z "$only" ] || [ "$only" = "$1" ]; }

OUT=${1:-}
[ -n "$OUT" ] || OUT=$(mktemp -d "${TMPDIR:-/tmp}/sdlck.XXXXXX") || fail "no temp dir"
mkdir -p "$OUT" && OUT=$(cd "$OUT" && pwd) || fail "cannot create $OUT"
# nothing of an earlier run is compared; only the names this script writes are removed, other files of OUT stay
rm -f "$OUT"/d[23]-*.dump "$OUT"/d[23]-*.dump.diff.png "$OUT"/d[23]-*.dump.bmp "$OUT"/bad.dump "$OUT"/nolines.txt \
	"$OUT"/alpha-badface.txt "$OUT"/asan/d[23]-*.dump "$OUT"/asan/d[23]-*.dump.diff.png "$OUT"/asan/d[23]-*.dump.bmp

if want 3; then
	PKG_CONFIG_PATH="$SDL3_PREFIX/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}" pkg-config --exists sdl3 2>/dev/null ||
		fail "sdl3 not found (SDL3_PREFIX=$SDL3_PREFIX)"
	if [ -d "$SDL3_SRC" ] && have=$(git --no-optional-locks -C "$SDL3_SRC" rev-parse HEAD 2>/dev/null); then
		built=$(cat "$SDL3_PREFIX/COMMIT" 2>/dev/null || echo none)
		[ "$built" = "$have" ] || fail "sdl3 built from $built, fork tree at $have (SDL3_PREFIX=$SDL3_PREFIX)"
	else
		echo "port-sdl-check: note: no fork tree at $SDL3_SRC, SDL3 commit not compared"
	fi
fi
if want 2; then
	pkg-config --exists sdl2 2>/dev/null || fail "sdl2 not found"
fi

for s in 2 3; do
	want $s || continue
	make -s -C "$here" SDL=$s O="$OUT" >"$OUT/build$s.log" 2>&1 || { cat "$OUT/build$s.log"; fail "build svfsdl$s"; }
done
if want 2; then
	make -s -C "$here" SDL=2 ASAN=1 O="$OUT" >"$OUT/buildasan.log" 2>&1 || { cat "$OUT/buildasan.log"; fail "build asan"; }
fi

python3 -I "$here/test_sdl_check.py" >"$OUT/test_sdl_check.log" 2>&1 || { tail -20 "$OUT/test_sdl_check.log"; fail "test_sdl_check.py"; }

KINDS="xrgb8888 argb8888 rgb565 rgb555 bgr24"
. "$here/window_deep.sh"
FACES="$root/svf/dos"
LINES="$here/sdl-lines.txt"
n2=0
n3=0
xsum=

# run_case BIN SDL TAG KIND SIZE BACK [args]: one dump run + the checker; prints nothing, sets $sum, fails the script on error.
# KIND alpha runs --alpha-demo (no --format). BACK is the SDL pixel format name the svfsdl: line must print for the back
# surface ("A|B": either name, SDL2 and SDL3 name xrgb8888 differently). A --threshold in the args is also given to the
# checker; an index8 or gray run presented as a surface also saves --shot, which the checker compares with its own palette.
run_case() {
	bin=$1; s=$2; tag=$3; kind=$4; size=$5; back=$6; shift 6
	d="${DDIR:-$OUT}/d$s-$tag.dump"
	rm -f "$d" "$d.bmp"
	thr=128; prev=; shotargs=
	for a in "$@"; do [ "$prev" = --threshold ] && thr=$a; prev=$a; done
	present=0
	for a in "$@"; do [ "$a" = --present ] && present=1; done
	if [ "$kind" = alpha ]; then fmt=--alpha-demo; else fmt="--format $kind"; fi
	if [ $present -eq 0 ] && { [ "$kind" = index8 ] || [ "$kind" = gray ]; }; then shotargs=$d.bmp; fi
	# shellcheck disable=SC2086
	out=$(SDL_VIDEODRIVER=dummy "$bin" $fmt --size "$size" --frames 1 --faces "$FACES" --lines "$LINES" --dump "$d" ${shotargs:+--shot "$shotargs"} "$@" 2>&1) ||
		fail "svfsdl$s $tag: $out"
	case "$out" in "svfsdl: SDL "*" driver dummy window "*" back "*" pitch "*" draw "*" us sum="*) ;; *) fail "svfsdl$s $tag: bad line: $out" ;; esac
	bk=${out#* back }; bk=${bk%% *}
	case "|$back|" in *"|$bk|"*) ;; *) fail "svfsdl$s $tag: back surface is $bk, expected $back" ;; esac
	[ "$kind" != alpha ] || case "$out" in *" covpitch ${size%x*} draw "*) ;; *) fail "svfsdl$s $tag: no covpitch ${size%x*}: $out" ;; esac
	# the shot palette gate reads the window's pixels back as 24 or 32 bit colour: below that (a 16 bit X display) the window
	# quantises the palette, so the comparison is skipped, loudly
	if [ -n "$shotargs" ]; then
		win=$(window_of "$out")
		window_deep "$win" || { echo "port-sdl-check: note: svfsdl$s $tag: window format $win is below 24 bits, shot palette comparison SKIPPED"; shotargs=; }
	fi
	chk=$(python3 -I "$here/sdl_check.py" "$d" --kind "$kind" --threshold "$thr" --lines "$LINES" --faces "$FACES" --diff "$d.diff.png" ${shotargs:+--shot "$shotargs"} 2>&1) ||
		fail "svfsdl$s $tag: $chk"
	[ -z "$shotargs" ] || case "$chk" in *" shot=ok sum="*) ;; *) fail "svfsdl$s $tag: shot not compared: $chk" ;; esac
	sum=${chk##*sum=}
	[ "${out##*sum=}" = "$sum" ] || fail "svfsdl$s $tag: program sum ${out##*sum=} != checker $sum"
	case "$chk" in *" sdl$s "*) ;; *) fail "svfsdl$s $tag: header SDL major: $chk" ;; esac
	[ "$s" = 2 ] && n2=$((n2 + 1)) || n3=$((n3 + 1))
}
# the expected back-surface name of a gray run: bits, order (msb|lsb)
gray_back() { if [ "$1" = 8 ]; then echo SDL_PIXELFORMAT_INDEX8; else echo "SDL_PIXELFORMAT_INDEX$1$(echo "$2" | tr a-z A-Z)"; fi; }
# The port asks for the array-order names (BGRX32, BGRA32); SDL prints the packed name they equal on this host: on a
# little-endian host XRGB8888 (SDL2: RGB888) and ARGB8888, on a big-endian one BGRX8888 and BGRA8888 (and only those).
if [ "$(python3 -I -c 'import sys; print(sys.byteorder)')" = big ]; then
	XRGB_BACK=SDL_PIXELFORMAT_BGRX8888; ARGB_BACK=SDL_PIXELFORMAT_BGRA8888
else
	XRGB_BACK="SDL_PIXELFORMAT_XRGB8888|SDL_PIXELFORMAT_RGB888"; ARGB_BACK=SDL_PIXELFORMAT_ARGB8888
fi
kind_back() {
	case $1 in
	xrgb8888) echo "$XRGB_BACK" ;;
	argb8888) echo "$ARGB_BACK" ;;
	rgb565) echo SDL_PIXELFORMAT_RGB565 ;;
	rgb555) echo "SDL_PIXELFORMAT_XRGB1555|SDL_PIXELFORMAT_RGB555" ;;
	bgr24) echo SDL_PIXELFORMAT_BGR24 ;;
	esac
}
ALPHA_BACK=$ARGB_BACK

for s in 2 3; do
	want $s || continue
	bin="$OUT/svfsdl$s"
	for k in $KINDS; do
		kb=$(kind_back $k)
		run_case "$bin" $s "$k-mapped" "$k" 640x480 "$kb"
		[ "$k" = xrgb8888 ] && [ -z "$xsum" ] && xsum=$sum
		run_case "$bin" $s "$k-stream" "$k" 640x480 "$kb" --stream
		run_case "$bin" $s "$k-odd" "$k" 641x479 "$kb"
	done
	run_case "$bin" $s cache xrgb8888 640x480 "$(kind_back xrgb8888)" --syllable-cache=65536
	# --threshold and --lsb-first are accepted with other formats and ignored there: the bytes are the plain run's
	run_case "$bin" $s xrgb-ignored xrgb8888 640x480 "$(kind_back xrgb8888)" --threshold 1 --lsb-first
	[ "$sum" = "$xsum" ] || fail "svfsdl$s xrgb8888 --threshold 1 --lsb-first changed the bytes ($sum != $xsum)"
	run_case "$bin" $s texture rgb565 640x480 SDL_PIXELFORMAT_RGB565 --present texture
	# the other 16 and 24 bit kinds through a texture: a texture format the renderer refuses is exit 1 (an error, not a conversion)
	run_case "$bin" $s texture-rgb555 rgb555 640x480 "$(kind_back rgb555)" --present texture
	run_case "$bin" $s texture-bgr24 bgr24 640x480 "$(kind_back bgr24)" --present texture
	run_case "$bin" $s index8-mapped index8 640x480 SDL_PIXELFORMAT_INDEX8
	run_case "$bin" $s index8-stream index8 640x480 SDL_PIXELFORMAT_INDEX8 --stream
	run_case "$bin" $s index8-thr1 index8 640x480 SDL_PIXELFORMAT_INDEX8 --threshold 1
	run_case "$bin" $s index8-thr255 index8 640x480 SDL_PIXELFORMAT_INDEX8 --threshold 255
	run_case "$bin" $s index8-texture index8 640x480 SDL_PIXELFORMAT_INDEX8 --present texture
	for b in 1 2 4 8; do
		run_case "$bin" $s gray$b-msb gray 640x480 "$(gray_back $b msb)" --gray-bits $b
		run_case "$bin" $s gray$b-lsb gray 640x480 "$(gray_back $b lsb)" --gray-bits $b --lsb-first
	done
	run_case "$bin" $s gray4-stream gray 640x480 SDL_PIXELFORMAT_INDEX4MSB --gray-bits 4 --stream
	run_case "$bin" $s gray4-texture gray 640x480 SDL_PIXELFORMAT_INDEX4MSB --gray-bits 4 --present texture
	run_case "$bin" $s gray1-thr1 gray 640x480 SDL_PIXELFORMAT_INDEX1MSB --gray-bits 1 --threshold 1
	run_case "$bin" $s gray1-thr255 gray 640x480 SDL_PIXELFORMAT_INDEX1MSB --gray-bits 1 --threshold 255
	run_case "$bin" $s alpha alpha 640x480 "$ALPHA_BACK"
	asum=$sum
	run_case "$bin" $s alpha-stream alpha 640x480 "$ALPHA_BACK" --stream
	run_case "$bin" $s alpha-texture alpha 640x480 "$ALPHA_BACK" --present texture
	run_case "$bin" $s alpha-grayarg alpha 640x480 "$ALPHA_BACK" --gray-bits 4 # ignored under --alpha-demo
	[ "$sum" = "$asum" ] || fail "svfsdl$s --alpha-demo --gray-bits 4 changed the bytes"
	# the other spelling order, and --format ignored too
	out=$(SDL_VIDEODRIVER=dummy "$bin" --gray-bits 4 --format xrgb8888 --alpha-demo --frames 1 --faces "$FACES" --lines "$LINES" 2>&1) ||
		fail "svfsdl$s --gray-bits 4 --alpha-demo: $out"
	[ "${out##*sum=}" = "$asum" ] || fail "svfsdl$s --gray-bits 4 --alpha-demo: sum ${out##*sum=} != $asum"
	[ "$s" = 2 ] && n2=$((n2 + 1)) || n3=$((n3 + 1))
	# the demo opens the first line's faces only: a face missing on a later line is no error
	{ cat "$LINES"; echo "NOSUCH.SVF | 1/1 | 16 | 40 | white | x"; } >"$OUT/alpha-badface.txt"
	out=$(SDL_VIDEODRIVER=dummy "$bin" --alpha-demo --stream --frames 1 --faces "$FACES" --lines "$OUT/alpha-badface.txt" 2>&1) ||
		fail "svfsdl$s --alpha-demo with a missing face on line 2: $out"
	[ "${out##*sum=}" = "$asum" ] || fail "svfsdl$s --alpha-demo, bad face on line 2: sum ${out##*sum=} != $asum"
	[ "$s" = 2 ] && n2=$((n2 + 1)) || n3=$((n3 + 1))
	# the small clipped surface (161x101): sub-byte rows with padding bits, a pitch rounded up by SDL
	for b in 1 2 4; do
		run_case "$bin" $s gray$b-small-msb gray 161x101 "$(gray_back $b msb)" --gray-bits $b
		run_case "$bin" $s gray$b-small-lsb gray 161x101 "$(gray_back $b lsb)" --gray-bits $b --lsb-first
	done
	run_case "$bin" $s index8-small index8 161x101 SDL_PIXELFORMAT_INDEX8
	run_case "$bin" $s rgb565-small rgb565 161x101 SDL_PIXELFORMAT_RGB565
	out=$(SDL_VIDEODRIVER=dummy "$bin" --format xrgb8888 --size 640x480 --present texture-direct --frames 1 --faces "$FACES" --lines "$LINES" 2>&1) ||
		fail "svfsdl$s texture-direct: $out"
	case "$out" in "svfsdl: SDL "*" driver dummy window "*" back SDL_PIXELFORMAT_"*" pitch "*" draw "*" us sum="*) ;; *) fail "svfsdl$s texture-direct: bad line: $out" ;; esac
	# drawn into SDL's own memory: where the locked pitch is w * 4 (w = 640 of the run above) the bytes are the xrgb8888
	# mapped dump's; any other pitch skips the comparison, loudly
	tp=${out#* pitch }; tp=${tp%% *}
	if [ "$tp" = $((640 * 4)) ]; then
		[ "${out##*sum=}" = "$xsum" ] || fail "svfsdl$s texture-direct: sum ${out##*sum=} != $xsum"
	else
		echo "port-sdl-check: note: svfsdl$s texture-direct: locked pitch $tp != $((640 * 4)), sum comparison skipped"
	fi
	[ "$s" = 2 ] && n2=$((n2 + 1)) || n3=$((n3 + 1))
done

# the 641x479 rgb565 padding: bytes 2w .. pitch-1 of every row are 0 (Review Focus 1, 2), w/h/pitch from the header
for s in 2 3; do
	want $s || continue
	python3 -I -c '
import sys
b = open(sys.argv[1], "rb").read()
w, h, p = (int.from_bytes(b[o:o + 2], "little") for o in (8, 10, 12))
assert b[:8] == b"SVFSDL1 " and (w, h) == (641, 479) and p >= 2 * w and len(b) == 16 + p * h, "unexpected header"
assert all(not any(b[16 + y * p + 2 * w:16 + (y + 1) * p]) for y in range(h)), "padding not zero"
' "$OUT/d$s-rgb565-odd.dump" || fail "svfsdl$s rgb565 641x479 padding"
done

# the two SDLs wrote the same bytes after the header, and the header differs in bits 4-5 of byte 15 only
if want 2 && want 3; then
	for f in "$OUT"/d2-*.dump; do
		g="$OUT/d3-${f##*/d2-}"
		cmp -s -i 16 "$f" "$g" || fail "SDL2 and SDL3 dumps differ: ${f##*/d2-}"
		cmp -s -n 15 "$f" "$g" || fail "headers differ before byte 15: ${f##*/d2-}"
		a=$(od -An -tu1 -j15 -N1 "$f"); b=$(od -An -tu1 -j15 -N1 "$g")
		[ $((b - a)) -eq 16 ] || fail "header byte 15 of ${f##*/d2-}: $a vs $b"
	done
fi

# the one ASAN/UBSAN run (counted under sdl2)
if want 2; then
	mkdir -p "$OUT/asan"
	ASAN_OPTIONS=${ASAN_OPTIONS:-detect_leaks=1}
	UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
	export ASAN_OPTIONS UBSAN_OPTIONS
	DDIR="$OUT/asan" run_case "$OUT/asan/svfsdl2" 2 asan rgb565 640x480 SDL_PIXELFORMAT_RGB565 --stream --syllable-cache=65536
	DDIR="$OUT/asan" run_case "$OUT/asan/svfsdl2" 2 asan-gray4 gray 640x480 SDL_PIXELFORMAT_INDEX4MSB --gray-bits 4 --stream
	DDIR="$OUT/asan" run_case "$OUT/asan/svfsdl2" 2 asan-alpha alpha 640x480 "$ALPHA_BACK"
	DDIR="$OUT/asan" run_case "$OUT/asan/svfsdl2" 2 asan-alpha-texture alpha 640x480 "$ALPHA_BACK" --present texture
	unset ASAN_OPTIONS UBSAN_OPTIONS
fi

# expected failures: exit 2, one `svfsdl:` line on stderr containing $1, no dump file (not counted)
nf=0
printf '[colours]\nbackground | 0x0010 | 0x0010 | 0x000084 | 0 | 0\n[lines]\n' >"$OUT/nolines.txt"
expect_usage() {
	want_msg=$1; ebin=$2; shift 2
	rm -f "$OUT/bad.dump"
	err=$(SDL_VIDEODRIVER=dummy "$ebin" "$@" 2>&1 >/dev/null); rc=$?
	[ $rc -eq 2 ] || fail "expected exit 2 from '$*', got $rc: $err"
	[ "$(printf '%s\n' "$err" | wc -l)" -eq 1 ] && case "$err" in "svfsdl: "*"$want_msg"*) true ;; *) false ;; esac ||
		fail "expected one svfsdl: line with '$want_msg' from '$*': $err"
	[ ! -e "$OUT/bad.dump" ] || fail "'$*' left a dump file"
	nf=$((nf + 1))
}
for s in 2 3; do
	want $s || continue
	b="$OUT/svfsdl$s"
	expect_usage "--format rgb24" "$b" --format rgb24 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "pitch 65536 > 65535" "$b" --format xrgb8888 --size 16384x10 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "width or height > 32767" "$b" --format xrgb8888 --size 40000x10 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "width or height > 32767" "$b" --format xrgb8888 --size 10x40000 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "cannot open face" "$b" --format xrgb8888 --faces /nonexistent --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "cannot open lines file" "$b" --format xrgb8888 --faces "$FACES" --lines /nonexistent --dump "$OUT/bad.dump"
	expect_usage "texture-direct" "$b" --format xrgb8888 --present texture-direct --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "--syllable-cache=abc" "$b" --format xrgb8888 --syllable-cache=abc --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "cannot write" "$b" --format xrgb8888 --faces "$FACES" --lines "$LINES" --dump "$OUT/nonexistent-dir/bad.dump"
	expect_usage "--threshold 256: expected 0..255" "$b" --format index8 --threshold 256 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "--threshold -1: expected 0..255" "$b" --format index8 --threshold -1 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "--threshold abc: expected 0..255" "$b" --format index8 --threshold abc --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "--gray-bits 3: expected 1, 2, 4 or 8" "$b" --format gray --gray-bits 3 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "--gray-bits needs --format gray" "$b" --format xrgb8888 --gray-bits 4 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "texture-direct cannot be used with --format gray" "$b" --format gray --present texture-direct --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "texture-direct cannot be used with --format index8" "$b" --format index8 --present texture-direct --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "texture-direct cannot be used with --alpha-demo" "$b" --alpha-demo --present texture-direct --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "has no text line for --alpha-demo" "$b" --alpha-demo --faces "$FACES" --lines "$OUT/nolines.txt" --dump "$OUT/bad.dump"
	expect_usage "--format rgb25" "$b" --alpha-demo --format rgb25 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
	expect_usage "--shot needs --present surface" "$b" --format xrgb8888 --present texture --shot "$OUT/bad.dump" --faces "$FACES" --lines "$LINES"
	expect_usage "--gray-bits 3: expected 1, 2, 4 or 8" "$b" --alpha-demo --gray-bits 3 --faces "$FACES" --lines "$LINES" --dump "$OUT/bad.dump"
done
nexp=0
for s in 2 3; do want $s && nexp=$((nexp + 21)); done
[ $nf -eq $nexp ] || fail "expected $nexp error cases, ran $nf"

[ -n "$xsum" ] || fail "no xrgb8888 mapped sum"
if want 2; then [ "$n2" -gt 0 ] || fail "no sdl2 runs"; fi
if want 3; then [ "$n3" -gt 0 ] || fail "no sdl3 runs"; fi
if [ -z "$only" ]; then
	echo "port-sdl-check: OK sdl2 $n2 runs, sdl3 $n3 runs, sum=$xsum"
else # one SDL only: say which ran and that the ASAN run (sdl2) was not part of it for SDL3
	if [ "$only" = 2 ]; then nn=$n2; asan=with ASAN; else nn=$n3; asan="no ASAN"; fi
	echo "port-sdl-check: OK sdl$only only: $nn runs, $asan, sum=$xsum"
fi
