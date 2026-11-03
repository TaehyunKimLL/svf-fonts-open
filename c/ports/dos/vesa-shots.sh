#!/bin/bash
# vesa-shots.sh [OUT] - SVFVESA.EXE in DOSBox-X at (640 x 480, 1024 x 768) x (8, 15, 16, 24, 32 bpp): the checksum check
# (SUM.TXT against tools/vesa_lines.py --expect), the capture check (DOSBox-X's own Ctrl-F5 PNG against DUMP.RAW,
# which is itself held byte for byte to the Python reference: c/ports/dos/vesa_check.py), the ten PNGs in
# c/ports/dos/shots/ (stored only when all ten modes passed) and the flush times in OUT/flush.md.
#
# OUT (default c/build/ports/dos-vesa) must be an absolute path whose components match [A-Za-z0-9._-]+ (not . or ..),
# with no symlink on any prefix and none anywhere below it (every name the script writes or deletes lives there),
# and be absent, empty or hold the marker .vesa-shots this script writes; anything else is refused before anything is
# built, written or deleted. DOSBOX_X (default /usr/bin/dosbox-x) is the emulator run; OPT (default ~/opt) holds djgpp.
# Needs xvfb-run, xdotool, ffmpeg, python3 with PIL.
#
# Test hooks (environment): VESA_SHOTS_CHECK_ONLY=1 exits (0) after the OUT checks, saying on stderr that it skipped the
# build, the run and the store; VESA_SHOTS_NO_BUILD=1 reuses
# OUT/SVFVESA.EXE; VESA_SHOTS_DEST=DIR stores the PNGs there; VESA_SHOTS_WAIT=SECONDS (60) is the wait for SUM.TXT;
# VESA_SHOTS_PNG_TRIES=N (100, 0.1 s each) the wait for the capture; VESA_SHOTS_RUN_TIMEOUT=SECONDS (300) the limit
# of one mode's whole run. The three numbers, when set, must match [0-9]+ (decimal; empty or anything else is refused
# before it can reach bash arithmetic, which runs command substitutions).
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
SELF=$HERE/$(basename "$0")
C=$(dirname "$(dirname "$HERE")")
REPO=$(dirname "$C")
DOSBOX_X=${DOSBOX_X:-/usr/bin/dosbox-x}
DEST=${VESA_SHOTS_DEST:-$HERE/shots}

die() {
	echo "vesa-shots: $*" >&2
	exit 1
}

# the three numbers are used in arithmetic: digits only (a set but empty value is refused too), read as decimal (08 is
# not octal); no eval
for v in VESA_SHOTS_WAIT VESA_SHOTS_PNG_TRIES VESA_SHOTS_RUN_TIMEOUT; do
	if [ -n "${!v+x}" ]; then
		case ${!v} in '' | *[!0-9]*) die "$v must be a number [0-9]+, not '${!v}'" ;; esac
	fi
done
WAIT=$((10#${VESA_SHOTS_WAIT:-60}))
PNG_TRIES=$((10#${VESA_SHOTS_PNG_TRIES:-100}))
RUN_TIMEOUT=$((10#${VESA_SHOTS_RUN_TIMEOUT:-300}))

# OUT must be an absolute path of plain names with no symlink under it; absent, empty or marked (also in --inner)
check_out() {
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
	if [ -d "$OUT" ]; then
		l=$(find "$OUT" -type l -print -quit 2>/dev/null)
		[ -z "$l" ] || die "$l is a symlink; OUT may hold none"
		if [ -n "$(ls -A "$OUT")" ] && [ ! -f "$OUT/.vesa-shots" ]; then
			die "$OUT is not empty and has no .vesa-shots marker"
		fi
	fi
}

# ---- the inner half: runs under xvfb-run, one mode (called by the outer half below) ----
if [ "${1:-}" = "--inner" ]; then
	[ $# -eq 5 ] || die "--inner takes W H BPP OUT"
	W=$2 H=$3 BPP=$4 OUT=$5
	[[ $W =~ ^[1-9][0-9]{0,3}$ && $H =~ ^[1-9][0-9]{0,3}$ ]] || die "W and H must be numbers of 1 to 4 digits: '$W' '$H'"
	case $BPP in 8 | 15 | 16 | 24 | 32) ;; *) die "BPP must be 8, 15, 16, 24 or 32: '$BPP'" ;; esac
	check_out
	cd "$OUT" || die "cannot enter $OUT"
	"$DOSBOX_X" -conf dosbox.conf -nopromptfolder -fastlaunch -nomenu >dosbox.log 2>&1 &
	DPID=$!
	# stop: SIGTERM, up to 5 s for it to go, then SIGKILL
	stop() {
		kill "$DPID" 2>/dev/null || return 0
		n=0
		while [ $n -lt 50 ] && kill -0 "$DPID" 2>/dev/null; do
			sleep 0.1
			n=$((n + 1))
		done
		kill -0 "$DPID" 2>/dev/null && kill -9 "$DPID" 2>/dev/null
		wait "$DPID" 2>/dev/null
		return 0
	}
	trap 'stop; echo "vesa-shots: interrupted or timed out ($W $H $BPP)" >&2; exit 1' TERM INT
	i=0
	while [ $i -lt $((WAIT * 10)) ]; do
		grep -qs 'sum=' SUM.TXT && break
		kill -0 "$DPID" 2>/dev/null || break
		sleep 0.1
		i=$((i + 1))
	done
	if ! grep -qs 'sum=' SUM.TXT; then
		stop
		echo "vesa-shots: SVFVESA did not report ($W $H $BPP); see OUT.TXT and dosbox.log" >&2
		exit 1
	fi
	SUMLINE=$(tr -d '\r' <SUM.TXT)
	re="^sum=([0-9a-f]{8}) dac=([68]) mode=0x[0-9a-f]+ ${W}x${H} ${BPP}bpp pitch=[0-9]+ bits=[0-9]+\$"
	if ! [[ $SUMLINE =~ $re ]]; then
		stop
		die "SUM.TXT is not 'sum=<8 hex> dac=<6|8> mode=0x<n> ${W}x${H} ${BPP}bpp pitch=<p> bits=<b>': $SUMLINE"
	fi
	GOT=${BASH_REMATCH[1]}
	DAC=${BASH_REMATCH[2]}
	EXP=$(python3 "$REPO/tools/vesa_lines.py" --expect "$HERE/vesa-lines.txt" --faces "$REPO/svf/dos" "$W" "$H" "$BPP") ||
		{ stop; die "vesa_lines.py --expect failed"; }
	EXP=${EXP#sum=}
	if [ "$GOT" != "$EXP" ]; then
		stop
		die "sum mismatch ($W $H $BPP): svfvesa $GOT, reference $EXP"
	fi
	echo "sum ok  $W x $H $BPP bpp  $GOT"
	WID=""
	i=0
	while [ $i -lt 100 ] && [ -z "$WID" ]; do
		WID=$(xdotool search --name DOSBox 2>/dev/null | head -n 1)
		[ -n "$WID" ] || sleep 0.1
		i=$((i + 1))
	done
	[ -n "$WID" ] || { stop; die "no DOSBox-X window"; }
	sleep 1
	xdotool mousemove 1279 1023
	xdotool key --window "$WID" ctrl+F5
	PNG=""
	i=0
	while [ $i -lt "$PNG_TRIES" ] && [ -z "$PNG" ]; do
		PNG=$(ls -t capture/*.png 2>/dev/null | head -n 1)
		[ -n "$PNG" ] || sleep 0.1
		i=$((i + 1))
	done
	SOURCE=scrshot
	if [ -n "$PNG" ]; then
		prev=-1
		i=0
		while [ $i -lt 100 ]; do
			sz=$(wc -c <"$PNG")
			[ "$sz" = "$prev" ] && [ "$sz" != 0 ] && break
			prev=$sz
			sleep 0.2
			i=$((i + 1))
		done
	else
		SOURCE=x11grab
		echo "vesa-shots: no capture PNG in $((PNG_TRIES / 10)) s, using the ffmpeg x11grab" >&2
		GEOM=$(xdotool getwindowgeometry --shell "$WID" 2>/dev/null | sed -n 's/^\(X\|Y\)=//p' | tr '\n' ' ')
		set -- $GEOM
		if [ $# -ne 2 ]; then
			stop
			die "no window geometry for the ffmpeg grab ($W $H $BPP)"
		fi
		mkdir -p capture || { stop; die "cannot create capture/"; }
		PNG=capture/grab.png
		ffmpeg -loglevel error -y -draw_mouse 0 -f x11grab -video_size "${W}x${H}" -i "$DISPLAY+$1,$2" -frames:v 1 "$PNG" ||
			{ stop; die "ffmpeg grab failed"; }
	fi
	python3 "$HERE/vesa_check.py" "$PNG" DUMP.RAW "$W" "$H" "$BPP" --dac "$DAC" \
		--palette-from "$HERE/vesa-lines.txt" --faces "$REPO/svf/dos" --diff "$OUT/diff-${W}x${H}-${BPP}.png" >rule.txt
	RC=$?
	if [ $RC -ne 0 ]; then
		stop
		die "capture check failed ($W $H $BPP, exit $RC); $PNG kept in $OUT"
	fi
	echo "capture ok  $W x $H $BPP bpp  source=$SOURCE  $(tr '\n' ' ' <rule.txt)"
	mkdir -p staged && cp "$PNG" "staged/${W}x${H}-${BPP}bpp.png" || { stop; die "cannot stage the capture"; }
	xdotool key --window "$WID" space
	i=0
	while [ $i -lt 100 ] && kill -0 "$DPID" 2>/dev/null; do
		sleep 0.1
		i=$((i + 1))
	done
	stop
	exit 0
fi

# ---- the outer half ----
OUT=${1:-$C/build/ports/dos-vesa}

check_out
if [ -n "${VESA_SHOTS_CHECK_ONLY:-}" ]; then
	echo "vesa-shots: VESA_SHOTS_CHECK_ONLY is set: the OUT checks passed;" \
		"the build, the ten runs and the store were skipped" >&2
	exit 0
fi

DJ=${OPT:-$HOME/opt}/djgpp/bin/i586-pc-msdosdjgpp
W="-Wall -Wextra -Werror"
tools="$DOSBOX_X xvfb-run xdotool ffmpeg python3 timeout find"
[ -n "${VESA_SHOTS_NO_BUILD:-}" ] || tools="$tools $DJ-gcc"
for t in $tools; do
	command -v "$t" >/dev/null 2>&1 || die "not found: $t"
done

# the shots directory must be writable before anything is run (the PNGs are stored at the end)
mkdir -p "$DEST" || die "cannot create the shots directory $DEST"
[ -d "$DEST" ] && [ -w "$DEST" ] || die "the shots directory $DEST is not writable"

mkdir -p "$OUT/obj/vbe" "$OUT/capture" "$OUT/staged" || die "cannot create $OUT"
: >"$OUT/.vesa-shots" || die "cannot write the marker"
# delete the previous build and run files inside the verified OUT only (OUT holds no symlink)
rm -f "$OUT"/obj/*.o "$OUT"/obj/vbe/*.o "$OUT"/*.SVF "$OUT"/VESALINE.TXT "$OUT"/flush.md "$OUT"/staged/*.png
if [ -z "${VESA_SHOTS_NO_BUILD:-}" ]; then
	rm -f "$OUT"/SVFVESA.EXE "$OUT"/SVFVESA.exe
	# SVFVESA.EXE as c/cross/build-all.sh builds it
	for s in "$C"/src/*.c; do
		"$DJ-gcc" -std=c99 $W -O2 -I"$C/include" -c "$s" -o "$OUT/obj/$(basename "$s" .c).o" || die "build failed: $s"
	done
	"$DJ-gcc" -std=c99 $W -O2 -I"$HERE" -c "$HERE/vbe_select.c" -o "$OUT/obj/vbe/vbe_select.o" || die "build failed: vbe_select.c"
	"$DJ-gcc" -std=gnu99 $W -O2 -I"$C/include" -I"$HERE" "$HERE/svfvesa.c" "$HERE/vesa_lines.c" \
		"$OUT/obj/vbe/vbe_select.o" "$OUT"/obj/*.o -o "$OUT/SVFVESA.EXE" || die "build failed: svfvesa.c"
fi
[ -f "$OUT/SVFVESA.EXE" ] || die "no $OUT/SVFVESA.EXE"

# the table, as VESALINE.TXT (8.3), and the faces it names (after the parser's name rule and realpath containment)
cp "$HERE/vesa-lines.txt" "$OUT/VESALINE.TXT" || die "cannot copy the table"
FACES=$(VS_TOOLS="$REPO/tools" python3 - "$HERE/vesa-lines.txt" "$REPO/svf/dos" <<'EOF'
import os, sys
sys.path.insert(0, os.environ["VS_TOOLS"])
import vesa_lines
t = vesa_lines.parse(sys.argv[1])
names = sorted({n for l in t.lines for n in l.faces})
for l in t.lines:
    for n in l.faces:
        vesa_lines._face_path(sys.argv[2], n, l.src_line)
print("\n".join(names))
EOF
) || die "the face names of vesa-lines.txt are refused"
for f in $FACES; do
	python3 -I "$REPO/tools/svf2to3.py" "$REPO/svf/dos/$f" "$OUT/$f" --profile dos >/dev/null ||
		die "cannot convert face $f to the dos profile"
done

write_conf() { # BPP W H
	EXTRA=""
	[ "$1" != 24 ] || EXTRA="vesa vbe 1.2 modes are 32bpp = false"
	cat >"$OUT/dosbox.conf" <<EOF
[sdl]
output = surface
windowresolution = original
mapperfile = $OUT/mapper.txt
[dosbox]
machine = svga_s3
memsize = 16
vmemsize = 8
captures = $OUT/capture
$EXTRA
[render]
scaler = none
aspect = false
[cpu]
core = normal
cputype = 486
cycles = fixed 23880
[autoexec]
mount c $OUT
c:
SVFVESA.EXE $2 $3 $1 DUMP.RAW > OUT.TXT
exit
EOF
}
# A mapper file replaces every default binding, so it carries the Ctrl key (mod1), the key that ends the program
# (space) and the screenshot event: DOSBox-X's event is hand_scrshot and SDL2 key 62 is F5 (hand_capture and key 292
# of the plan are no such event and key).
cat >"$OUT/mapper.txt" <<'EOF2' || die "cannot write mapper.txt"
mod_1 "key 224" "key 228"
hand_scrshot "key 62 mod1"
key_space "key 44"
EOF2

export DOSBOX_X VESA_SHOTS_WAIT="$WAIT" VESA_SHOTS_PNG_TRIES="$PNG_TRIES"
status=0
: >"$OUT/flush.md.tmp" || die "cannot write flush.md.tmp"
for size in "640 480" "1024 768"; do
	set -- $size
	w=$1 h=$2
	for bpp in 8 15 16 24 32; do
		rm -f "$OUT/SUM.TXT" "$OUT/DUMP.RAW" "$OUT/OUT.TXT" "$OUT/rule.txt" "$OUT/capture/"* "$OUT/diff-"*.png
		write_conf "$bpp" "$w" "$h" || die "cannot write dosbox.conf"
		xvfb-run -a -s "-screen 0 1280x1024x24" timeout -k 15 "$RUN_TIMEOUT" "$SELF" --inner "$w" "$h" "$bpp" "$OUT" ||
			{ status=1; break 2; }
		tr -d '\r' <"$OUT/OUT.TXT" >"$OUT/OUT.clean" || die "cannot read OUT.TXT"
		line=$(grep "^flush_${w}x${h}_${bpp}[ ]" "$OUT/OUT.clean")
		if ! printf '%s\n' "$line" | grep -Eqx "flush_${w}x${h}_${bpp} rows=[0-9]+ us=[0-9]+"; then
			die "OUT.TXT has no flush_${w}x${h}_${bpp} line of the form 'flush_WxH_BPP rows=<n> us=<n>': '$line'"
		fi
		echo "$line" >>"$OUT/flush.md.tmp" || die "cannot write flush.md.tmp"
	done
done
[ $status -eq 0 ] || exit 1
{
	echo "| mode | rows | us |"
	echo "|---|---|---|"
	sed 's/^flush_\([0-9]*x[0-9]*\)_\([0-9]*\) rows=\([0-9]*\) us=\([0-9]*\)$/| \1 \2 bpp | \3 | \4 |/' "$OUT/flush.md.tmp"
} >"$OUT/flush.md" || die "cannot write flush.md"
rm -f "$OUT/flush.md.tmp"
# store the ten PNGs only now that every mode passed: copy under temporary names, then move; a failure removes
# the temporary names it made
n=0
for f in "$OUT"/staged/*.png; do
	[ -f "$f" ] && n=$((n + 1))
done
[ "$n" -eq 10 ] || die "$n staged PNGs, expected 10"
drop_new() {
	for f in "$OUT"/staged/*.png; do
		rm -f "$DEST/.$(basename "$f").new"
	done
}
store_die() {
	drop_new
	die "$@"
}
for f in "$OUT"/staged/*.png; do
	cp "$f" "$DEST/.$(basename "$f").new" || store_die "cannot store $(basename "$f") in $DEST"
done
for f in "$OUT"/staged/*.png; do
	mv -f "$DEST/.$(basename "$f").new" "$DEST/$(basename "$f")" || store_die "cannot store $(basename "$f") in $DEST"
done
cat "$OUT/flush.md"
echo "vesa-shots: OK (10 modes)"
