#!/bin/sh
# check.sh [--asan] OBJ... - the library's gate (make -C c check passes --asan and both builds' objects).
#
# no-malloc: no object may call the allocator (spec: no dynamic allocation in the core). Fails if any object has an
# undefined malloc, calloc, realloc or free symbol, if nm fails on an object, or if no object is given.
# --asan: then runs tools/test_c_renderer.py with SVF_ASAN=1, so every test runs against the
# -fsanitize=address,undefined build of the library and its test programs ("asan: OK"; PYTHON names the interpreter,
# default python3). Then the same run again with CC set to clang (CLANG, else ~/opt/llvm-*/bin/clang, else clang on
# PATH): only clang's -fsanitize=pointer-overflow catches a destination pointer formed before the row ("clang: OK");
# no clang prints "clang: skipped (not found)".
# targets: svf_draw.c is compiled (-Werror, no output) for every SVF_TARGETS value 0x000..0x3FF (the 0x000..0x3FF
# gate: all 1024 masks), each also with -DSVF_NO_SCALE, plus the masks 0x3FF, 0x1FF, 0x1E8, 0x008, 0x020, 0x040, 0x080,
# 0x100 and 0x200 each with -DSVF_WORD_STORE=0 and =1: 2066 jobs a compiler (on x86 the =1 jobs repeat the default), run with
# xargs -P nproc, by the default compiler (CC, else cc) and by clang: a build with kinds left out stays warning-free
# ("targets: OK <compiler>"). The job list is written to $OUT/jobs (OUT, default c/build/check) and kept.
# CHECK_LIST_ONLY=1 (exactly 1) prints the job list to stdout and exits 0 before anything else (the unit test of the
# list; no --asan run, no compiling).
# targets_jobs: one token per job on stdout, MASK[:-DFLAG...] (no whitespace); a flag after the mask's colon is a
# compiler option.
targets_jobs() {
	v=0
	while [ $v -le 1023 ]; do
		printf '0x%03X\n0x%03X:-DSVF_NO_SCALE\n' $v $v
		v=$((v + 1))
	done
	for m in 0x3FF 0x1FF 0x1E8 0x008 0x020 0x040 0x080 0x100 0x200; do
		printf '%s:-DSVF_WORD_STORE=0\n%s:-DSVF_WORD_STORE=1\n' $m $m
	done
}
if [ "${CHECK_LIST_ONLY:-}" = 1 ]; then
	targets_jobs
	exit 0
fi
NM=${NM:-nm}
PYTHON=${PYTHON:-python3}
asan=0
if [ "$1" = "--asan" ]; then
	asan=1
	shift
fi
[ $# -gt 0 ] || { echo "no-malloc: FAIL: no objects given"; exit 1; }
status=0
for o in "$@"; do
	if ! syms=$($NM -u "$o"); then
		echo "no-malloc: FAIL: $NM -u $o failed"
		status=1
		continue
	fi
	bad=$(printf '%s\n' "$syms" | awk '{print $NF}' | grep -E '^_?(malloc|calloc|realloc|free)$')
	if [ -n "$bad" ]; then
		echo "no-malloc: FAIL: $o uses $(echo $bad)"
		status=1
	fi
done
[ $status -eq 0 ] || exit $status
echo "no-malloc: OK ($# objects)"
[ $asan -eq 1 ] || exit 0
root=$(cd "$(dirname "$0")/.." && pwd) || exit 1
src=$root/c/src
OUT=${OUT:-$root/c/build/check}
# targets_ok CC: compiles svf_draw.c for every job, in parallel; one failing job fails the gate (xargs exits non-zero).
targets_ok() {
	mkdir -p "$OUT" || return 1
	list=$OUT/jobs
	targets_jobs >"$list" || return 1
	SVF_SRC=$src
	export SVF_SRC
	# shellcheck disable=SC2016
	xargs -P "$(nproc 2>/dev/null || echo 1)" -n 1 sh -c '
		mask=${1%%:*}
		flag=
		[ "$1" != "$mask" ] && flag=${1#*:}
		if ! out=$("$0" -std=c99 -Wall -Wextra -Werror -O2 -DSVF_TARGETS=$mask $flag -I"$SVF_SRC/../include" \
			-c "$SVF_SRC/svf_draw.c" -o /dev/null 2>&1); then
			echo "targets: FAIL: $0 -DSVF_TARGETS=$mask $flag"
			printf "%s\n" "$out"
			exit 1
		fi' "$1" <"$list"
	rc=$?
	[ $rc -eq 0 ] || return 1
	echo "targets: OK $1"
}
targets_ok "${CC:-cc}" || exit 1
if SVF_ASAN=1 PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$root/tools/test_c_renderer.py"; then
	echo "asan: OK"
else
	echo "asan: FAIL: tools/test_c_renderer.py with SVF_ASAN=1"
	exit 1
fi
clang=${CLANG:-}
if [ -z "$clang" ]; then
	for c in "$HOME"/opt/llvm-*/bin/clang; do
		[ -x "$c" ] && clang=$c
	done
fi
[ -n "$clang" ] || clang=$(command -v clang 2>/dev/null)
if [ -z "$clang" ] || [ ! -x "$clang" ]; then
	echo "clang: skipped (not found)"
	exit 0
fi
targets_ok "$clang" || exit 1
if CC="$clang" SVF_ASAN=1 PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$root/tools/test_c_renderer.py"; then
	echo "clang: OK ($clang)"
else
	echo "clang: FAIL: tools/test_c_renderer.py with SVF_ASAN=1 CC=$clang"
	exit 1
fi
