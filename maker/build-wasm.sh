#!/bin/bash
# build-wasm.sh - builds the maker's preview module: maker/static/wasm/svf.js + svf.wasm (SVF_WASM_OUT overrides the
# directory), from c/ports/web/svf_web.c and c/src with the compile line of c/ports/web/emcc-flags.sh (the same as
# web/build.sh). emcc from EMSDK, default ~/opt/emsdk. Prints "svf.wasm N bytes, svf.js N bytes"; writes nothing else.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
OUT=${SVF_WASM_OUT:-$ROOT/maker/static/wasm}

. "$ROOT/c/ports/web/emcc-flags.sh"

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
svf_web_compile "$ROOT" "$OUT"

echo "svf.wasm $(wc -c <"$OUT/svf.wasm") bytes, svf.js $(wc -c <"$OUT/svf.js") bytes"
