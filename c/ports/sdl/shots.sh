#!/bin/sh
# shots.sh [OUT] - the screenshots of the SDL example: for SDL2 and SDL3 and for xrgb8888, argb8888, rgb565, index8 and gray
# (4 bits), at 640 x 480, `xvfb-run -a -s "-screen 0 1280x1024x24" svfsdlN --format K --present surface --shot B.bmp --dump D
# --frames 1`: the window's pixels as SDL showed them. Each BMP goes through sdl_shots.py (PNG, size, >= 1 % ink, compared
# with the same run's dump as SDL expands it: `exact`, or `shl` / `tolerance` (<= 1 level) printed as information). The ten PNGs and
# overview.png (the 2 x 5 grid) are stored in c/ports/sdl/shots/ (SVFSDL_SHOTS_DEST=DIR stores them there instead), only when all
# ten passed. Then, per format, whether the SDL2 and the SDL3 picture are the same pixels (information, not a failure).
# OUT (default: a temp dir, removed at the end) must not be the stored directory; the work is in OUT/work. Last line `port-sdl-shots: OK ...`; a failure prints `port-sdl-shots: FAIL <why>` and exits 1; no xvfb-run: exit 2.
#   SVFSDL_ONLY is not offered: the comparison needs both SDLs. SDL3_PREFIX as in check.sh.
set -u
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
DEST=${SVFSDL_SHOTS_DEST:-$here/shots}
fail() { echo "port-sdl-shots: FAIL $*"; exit 1; }
command -v xvfb-run >/dev/null 2>&1 || { echo "port-sdl-shots: xvfb-run not found (apt install xvfb); no screenshots made"; exit 2; }

OUT=${1:-}
if [ -z "$OUT" ]; then
	OUT=$(mktemp -d "${TMPDIR:-/tmp}/sdlshots.XXXXXX") || fail "no temp dir"
	made=$OUT
	trap 'rm -rf "$made"' EXIT # a directory this script made is removed again; one the caller named is kept
fi
mkdir -p "$OUT" && OUT=$(cd "$OUT" && pwd -P) || fail "cannot create $OUT"
mkdir -p "$DEST" || fail "cannot create $DEST"
DEST=$(cd "$DEST" && pwd -P)
# the working files live in OUT/work, so the stored pictures (DEST) are written only by the final copies and a failed run
# leaves them as they were
[ "$OUT" != "$DEST" ] && [ "$OUT/work" != "$DEST" ] || fail "OUT must not be the directory the pictures are stored in ($DEST)"
OUT=$OUT/work
rm -rf "$OUT" && mkdir -p "$OUT" || fail "cannot create $OUT"
FACES="$root/svf/dos"
LINES="$here/sdl-lines.txt"

for s in 2 3; do
	make -s -C "$here" SDL=$s O="$OUT" >"$OUT/build$s.log" 2>&1 || { cat "$OUT/build$s.log"; fail "build svfsdl$s"; }
done

# name | svfsdl format arguments | sdl_shots.py kind
ok=0; exact=0
for s in 2 3; do
	for spec in "xrgb8888|--format xrgb8888|xrgb8888" "argb8888|--format argb8888|argb8888" "rgb565|--format rgb565|rgb565" \
		"index8|--format index8|index8" "gray4|--format gray --gray-bits 4|gray"; do
		name=${spec%%|*}; rest=${spec#*|}; args=${rest%%|*}; kind=${rest#*|}
		b="$OUT/sdl$s-$name.bmp"; d="$OUT/sdl$s-$name.dump"; png="$OUT/sdl$s-$name.png"
		# shellcheck disable=SC2086
		line=$(xvfb-run -a -s "-screen 0 1280x1024x24" "$OUT/svfsdl$s" $args --size 640x480 --present surface --shot "$b" \
			--dump "$d" --frames 1 --faces "$FACES" --lines "$LINES" 2>&1) || fail "svfsdl$s $name: $line"
		res=$(python3 -I "$here/sdl_shots.py" "$b" "$d" --kind "$kind" --png "$png" --lines "$LINES" 2>&1) ||
			fail "svfsdl$s $name: $res ($line)"
		echo "sdl$s $name: ${res#sdl-shots: } [${line#svfsdl: }]" | sed 's/ draw [0-9]* us//'
		ok=$((ok + 1))
		case "$res" in *" exact "*) exact=$((exact + 1)) ;; esac
	done
done
[ $ok -eq 10 ] || fail "$ok of 10 pictures"

same=0
for name in xrgb8888 argb8888 rgb565 index8 gray4; do
	r=$(python3 -I "$here/sdl_shots.py" compare "$OUT/sdl2-$name.png" "$OUT/sdl3-$name.png") || fail "compare $name"
	[ "$r" != identical ] || same=$((same + 1))
	echo "$name: sdl2 == sdl3: $r"
done

python3 -I "$here/sdl_shots.py" overview "$OUT" "$OUT/overview.png" || fail "overview"
cp "$OUT"/sdl[23]-*.png "$OUT/overview.png" "$DEST/" || fail "cannot store the pictures in $DEST"
echo "port-sdl-shots: OK 10 pictures in $DEST, $exact exact, sdl2 == sdl3 identical for $same of 5 formats"
