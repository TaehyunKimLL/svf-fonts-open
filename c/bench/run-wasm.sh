#!/bin/sh
# run-wasm.sh [OUT] - times c/bench/bench.c compiled to WebAssembly under node and prints Markdown table rows against
# the design budget (WASM: <= 1 ms the sample line, the 40 code point PAPLG16 + PAPLG18 line of the DOS run).
#
# Not an instruction-set emulator: node (NODE, default ~/opt/node-v24.13.0-linux-x64/bin/node) runs the module on V8's
# WebAssembly tiers, on the host CPU (named in the row), timed in the program with emscripten_get_now()
# (performance.now). The first case includes V8's tier-up from its baseline compiler. Built with emcc 6.0.13
# (c/cross/install-toolchains.sh) at -std=c99 -O2, -sENVIRONMENT=node, the P4 profile (scaling in). Faces:
# svf/dos/PAPLG16.SVF and PAPLG18.SVF embedded by c/bench/mkface.py; "streamed" reads them through a callback that
# copies from those arrays.
#
# Build and raw output go to OUT (default c/build/bench/wasm). Exit status: report.awk's (0 met, 2 a budget missed,
# 1 a failure).
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
SVF=$(dirname "$C")/svf/dos
OPT=${OPT:-$HOME/opt}
OUT=${1:-$C/build/bench/wasm}
EM=$OPT/emsdk
NODE=${NODE:-$OPT/node-v24.13.0-linux-x64/bin/node}
. "$HERE/sums.inc.sh"
SUMS=$SUMS_LINE40
BUDGETS="line40_mapped:1000 line40_mapped_cache:1000 line40_stream_cold:1000 line40_stream_warm:1000"
BUDGETS="$BUDGETS line40_stream_small:1000 line40_stream_nocache:1000"
export EM_CONFIG="$EM/.emscripten"

mkdir -p "$OUT" || exit 1
python3 -I "$HERE/mkface.py" "$SVF/PAPLG16.SVF" "$OUT/face16.c" --name bench_face16 --profile "${BENCH_PROFILE:-wasm}" || exit 1
python3 -I "$HERE/mkface.py" "$SVF/PAPLG18.SVF" "$OUT/face18.c" --name bench_face18 --profile "${BENCH_PROFILE:-wasm}" || exit 1
"$EM/upstream/emscripten/emcc" -std=c99 -Wall -Wextra -Werror -O2 -DBENCH_WASM -sENVIRONMENT=node -I"$C/include" \
	"$HERE/bench.c" "$C"/src/*.c "$OUT/face16.c" "$OUT/face18.c" -o "$OUT/bench.js" ||
	{ echo "wasm: build failed"; exit 1; }
ver=$("$EM/upstream/emscripten/emcc" -dumpversion) || exit 1
nver=$("$NODE" --version) || exit 1
v8=$("$NODE" -p process.versions.v8) || exit 1
cpu=$(awk -F': ' '/^model name/ { print $2; exit }' /proc/cpuinfo)
"$NODE" "$OUT/bench.js" >"$OUT/run.txt" 2>&1
awk -v build="WASM (node $nver, V8 $v8, on $cpu; emcc $ver -O2)" -v budgets="$BUDGETS" -v sums="$SUMS" \
	-f "$HERE/report.awk" "$OUT/run.txt"
s=$?
[ $s -eq 1 ] && echo "wasm: run failed, see $OUT/run.txt"
exit $s
