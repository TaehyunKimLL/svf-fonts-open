#!/bin/sh
# run-host.sh [OUT] - builds c/bench/bench.c for the host (-DBENCH_HOST) with the faces embedded as run-wasm.sh does
# (PAPLG16, PAPLG18) plus the two 24 px faces of the packed-kind cases (MARUS24A, MARUS24), runs it and prints its raw
# output: the pixel checksums run-dos.sh's SUMS are taken from (and tools/svfline.py's draw_target must agree with).
# The times are the host CPU's, not a measurement of anything else. Build and output go to OUT (default
# c/build/bench/host). Extra arguments after OUT are compiler flags (-DSVF_WORD_STORE=0 -DBENCH_CASE_SUFFIX='"_bytes"').
set -u

HERE=$(cd "$(dirname "$0")" && pwd) || exit 1
C=$(dirname "$HERE")
SVF=$(dirname "$C")/svf/dos
OUT=${1:-$C/build/bench/host}
[ $# -eq 0 ] || shift
mkdir -p "$OUT" || exit 1
for f in PAPLG16:face16 PAPLG18:face18 MARUS24A:face24a MARUS24:face24m; do
	python3 -I "$HERE/mkface.py" "$SVF/${f%%:*}.SVF" "$OUT/${f#*:}.c" --name "bench_${f#*:}" ${BENCH_PROFILE:+--profile "$BENCH_PROFILE"} || exit 1
done
cc -std=c99 -Wall -Wextra -Werror -O2 -DBENCH_HOST -I"$C/include" "$@" "$HERE/bench.c" "$C"/src/*.c "$OUT"/face*.c \
	-o "$OUT/bench" || { echo "host: build failed"; exit 1; }
"$OUT/bench" >"$OUT/run.txt"
status=$?
cat "$OUT/run.txt"
exit $status
