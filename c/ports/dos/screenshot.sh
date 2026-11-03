#!/bin/sh
# screenshot.sh [OUT] - builds SVFDEMO.EXE with DJGPP, runs it in DOSBox-X headless (xvfb-run) and stores the screen
# as c/ports/dos/screenshot.png (320 x 200, the mode 13h pixels).
#
# DOSBox-X draws mode 13h at 2x into a 640 x 400 window (scaler none, no menu); the window is grabbed with ffmpeg's
# x11grab once the program waits for its key, checked to be exact 2 x 2 blocks, and reduced to 320 x 200. xdotool
# moves the pointer off the window first and then presses the key that ends the program.
# Needs: ~/opt/djgpp (OPT overrides), dosbox-x, xvfb-run, xdotool, ffmpeg, python3 with PIL. Build files go to OUT
# (default c/build/ports/dos-run).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
C=$(dirname "$(dirname "$HERE")")
OUT=${1:-$C/build/ports/dos-run}
DJ=${OPT:-$HOME/opt}/djgpp/bin/i586-pc-msdosdjgpp

rm -rf "$OUT"
mkdir -p "$OUT/obj"
for s in "$C"/src/*.c; do
	"$DJ-gcc" -std=c99 -Wall -Wextra -Werror -O2 -I"$C/include" -c "$s" -o "$OUT/obj/$(basename "$s" .c).o"
done
"$DJ-gcc" -std=gnu99 -Wall -Wextra -Werror -O2 -I"$C/include" "$HERE/svfdemo.c" "$OUT"/obj/*.o -o "$OUT/SVFDEMO.EXE"
for f in PAPLG16 PAPLG18; do # the dos profile: 1 byte units
	python3 -I "$(dirname "$C")/tools/svf2to3.py" "$(dirname "$C")/svf/dos/$f.SVF" "$OUT/$f.SVF" --profile dos >/dev/null || exit 1
done
cat >"$OUT/demo.conf" <<EOF
[sdl]
output = surface
windowresolution = original
[dosbox]
machine = svga_s3
memsize = 16
[render]
scaler = none
aspect = false
[autoexec]
mount c "$OUT"
c:
SVFDEMO.EXE > OUT.TXT
exit
EOF
cd "$OUT"
timeout 120 xvfb-run -a -s "-screen 0 800x600x24" sh -c '
	dosbox-x -conf demo.conf -nopromptfolder -fastlaunch -nomenu >dosbox.log 2>&1 &
	sleep 6
	xdotool mousemove 799 599
	set -- $(xdotool search --name DOSBox getwindowgeometry --shell %@ | sed -n "s/^\(X\|Y\)=//p")
	ffmpeg -loglevel error -y -f x11grab -video_size 640x400 -i "$DISPLAY+$1,$2" -frames:v 1 window.png
	xdotool key space
	wait'
tr -d '\r' <OUT.TXT
python3 - "$OUT/window.png" "$HERE/screenshot.png" <<'EOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("L")
px = im.load()
assert im.size == (640, 400), im.size
assert all(len({px[x, y], px[x + 1, y], px[x, y + 1], px[x + 1, y + 1]}) == 1
           for y in range(0, 400, 2) for x in range(0, 640, 2)), "not a 2x image of the screen"
im.resize((320, 200), Image.NEAREST).save(sys.argv[2])
print("wrote", sys.argv[2])
EOF
