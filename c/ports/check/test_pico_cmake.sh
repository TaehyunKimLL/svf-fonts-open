#!/bin/sh
# Configure-time checks of c/ports/pico/CMakeLists.txt (needs a pico-sdk; not part of host-checks.sh).
# Usage: PICO_SDK_PATH=<sdk> [PICO_TOOLCHAIN_PATH=<arm toolchain dir>] sh c/ports/check/test_pico_cmake.sh
# (set PICO_TOOLCHAIN_PATH when no arm-none-eabi-gcc is on PATH)
# Prints "pico-cmake: OK", or "pico-cmake: skipped (no PICO_SDK_PATH)"; exit 1 on a failure.
here=$(cd "$(dirname "$0")" && pwd)
src=$here/../pico
sdk=${PICO_SDK_PATH:-}
[ -n "$sdk" ] || { echo "pico-cmake: skipped (no PICO_SDK_PATH)"; exit 0; }
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() {
	echo "pico-cmake: FAIL: $1" >&2
	[ -z "${lastlog:-}" ] || { echo "--- tail of $lastlog:" >&2; tail -n 15 "$lastlog" >&2; }
	command -v arm-none-eabi-gcc >/dev/null 2>&1 || [ -n "${PICO_TOOLCHAIN_PATH:-}" ] ||
		echo "pico-cmake: no arm-none-eabi-gcc on PATH: set PICO_TOOLCHAIN_PATH to the toolchain directory" >&2
	exit 1
}
TC=
[ -z "${PICO_TOOLCHAIN_PATH:-}" ] || TC="-DPICO_TOOLCHAIN_PATH=$PICO_TOOLCHAIN_PATH"
cfg() { # B ARGS... ; the SDK only from the environment unless -DPICO_SDK_PATH is passed
	b=$1
	shift
	lastlog=$tmp/$b.log
	cmake -S "$src" -B "$tmp/$b" -DPICO_NO_PICOTOOL=1 $TC "$@" >"$tmp/$b.log" 2>&1
}

# the faces come from the table: a table row with another face is the face that is generated
sed 's|dos/NEODG16G.SVF|dos/PAPLG16.SVF|' "$here/../profiles.txt" >"$tmp/alt.txt"
cfg faces -DSVF_PROFILE=mono -DSVF_PROFILES_TXT="$tmp/alt.txt" || fail "faces: configure"
grep -rq 'PAPLG16.SVF' "$tmp/faces/CMakeFiles" || fail "faces: the table's face is not generated"
grep -rq 'NEODG16G.SVF' "$tmp/faces/CMakeFiles" && fail "faces: the old face is still used"

# an environment PICO_SDK_PATH works after a configure without it (the failed attempt leaves no empty cache entry)
env -u PICO_SDK_PATH cmake -S "$src" -B "$tmp/env" -DSVF_PROFILE=colour >"$tmp/env0.log" 2>&1 && fail "env: configured without an SDK"
grep -q 'PICO_SDK_PATH:' "$tmp/env0.log" || fail "env: no PICO_SDK_PATH message"
PICO_SDK_PATH=$sdk cfg env -DSVF_PROFILE=colour || fail "env: the environment SDK is ignored after a failed configure"
# ... and that failed configure did not lock the directory to a profile
env -u PICO_SDK_PATH cmake -S "$src" -B "$tmp/lock" >"$tmp/lock0.log" 2>&1 && fail "lock: configured without an SDK"
cfg lock -DSVF_PROFILE=colour -DPICO_SDK_PATH="$sdk" || fail "lock: a failed configure locked the directory"

# the lock still holds after a good configure, and a grey kind that a profile ignores does not count
cfg two -DSVF_PROFILE=colour -DPICO_SDK_PATH="$sdk" || fail "two: configure"
cfg two -DSVF_PROFILE=grey -DPICO_SDK_PATH="$sdk" && fail "two: profile change accepted"
grep -q 'configured for colour' "$tmp/two.log" || fail "two: no 'configured for colour'"
cfg two -DSVF_PROFILE=colour -DSVF_GREY_KIND=GRAY4 -DPICO_SDK_PATH="$sdk" || fail "two: colour locked by SVF_GREY_KIND"
echo "pico-cmake: OK"
