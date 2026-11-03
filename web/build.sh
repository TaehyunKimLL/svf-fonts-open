#!/bin/bash
# build.sh [OUT] - builds the WASM font picker into OUT (default web/dist): svf.js + svf.wasm (the renderer and
# c/ports/web/svf_web.c, emcc from EMSDK, default ~/opt/emsdk as c/cross/install-toolchains.sh installs it),
# faces.json (web/mkindex.py), faces/<group>/<FILE>.SVF and licences/<group>/<FILE> copied from svf/
# (web/copyfaces.py), and the page sources of web/ that exist (index.html, picker.js, style.css). Writes only under OUT.
# Prints "svf.wasm N bytes, svf.js N bytes, F faces, N MB copied"; exits non-zero on the first failure.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
OUT=${1:-$HERE/dist}
EMSDK=${EMSDK:-$HOME/opt/emsdk}
EMCC=$EMSDK/upstream/emscripten/emcc
C=$ROOT/c

[ -x "$EMCC" ] || { echo "build.sh: no emcc at $EMCC (c/cross/install-toolchains.sh, or set EMSDK)" >&2; exit 1; }
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)

EM_CONFIG="$EMSDK/.emscripten" "$EMCC" -std=c99 -Wall -Wextra -Werror -O2 -I"$C/include" \
	"$C/ports/web/svf_web.c" "$C"/src/*.c -o "$OUT/svf.js" -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
	-sENVIRONMENT=web,node -sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16,HEAP32 \
	-sALLOW_MEMORY_GROWTH

python3 -B "$HERE/mkindex.py" "$ROOT/svf" "$OUT/faces.json" >/dev/null

for f in index.html picker.js style.css; do
	if [ -f "$HERE/$f" ]; then cp "$HERE/$f" "$OUT/$f"; fi
done

# The faces and every licence file faces.json names, copied from svf/ (each path checked to stay under svf/ and OUT;
# exit 2 otherwise); prints "F faces, N MB copied".
copied=$(python3 -B "$HERE/copyfaces.py" "$ROOT/svf" "$OUT/faces.json" "$OUT")

echo "svf.wasm $(wc -c <"$OUT/svf.wasm") bytes, svf.js $(wc -c <"$OUT/svf.js") bytes, $copied"
