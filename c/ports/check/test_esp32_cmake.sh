#!/bin/sh
# Configure-time checks of c/ports/esp32/CMakeLists.txt rules that need no ESP-IDF: a stand-in IDF_PATH whose
# project.cmake is empty lets the top-level file run to the end (the component in main/ is not entered: test_esp32_component.sh
# checks it). Run by host-checks.sh (silent on success).
# Usage: sh c/ports/check/test_esp32_cmake.sh        Prints "esp32-cmake: OK"; exit 1 on a failure.
here=$(cd "$(dirname "$0")" && pwd)
src=$here/../esp32
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "esp32-cmake: FAIL: $1" >&2; exit 1; }
mkdir -p "$tmp/idf/tools/cmake" && : >"$tmp/idf/tools/cmake/project.cmake"
# cfg B ARGS... : configure with the stand-in IDF; the log is $tmp/B.log
cfg() {
	b=$1
	shift
	IDF_PATH=$tmp/idf cmake -S "$src" -B "$tmp/$b" "$@" >"$tmp/$b.log" 2>&1
}
# err B WANT ARGS... : the configure must fail and its log must hold WANT, as the first error
err() {
	b=$1 want=$2
	shift 2
	cfg "$b" "$@" && fail "$b: configured"
	first=$(grep -A1 -m1 'CMake Error' "$tmp/$b.log" | tr '\n' ' ' | tr -s ' ')
	case $first in *"$want"*) ;; *) fail "$b: first error '$first' lacks '$want'";; esac
}
err typo "choose one of colour, grey, mono" -DSVF_PROFILE=color
err rgbgrey "SVF_DISPLAY esp_rgb needs SVF_PROFILE colour" -DSVF_PROFILE=grey -DSVF_DISPLAY=esp_rgb
err rgbmono "SVF_DISPLAY esp_rgb needs SVF_PROFILE colour" -DSVF_PROFILE=mono -DSVF_DISPLAY=esp_rgb
err disp "ili9341 or esp_rgb" -DSVF_DISPLAY=ili9340
err kind "t_8e7da3c1" -DSVF_PROFILE=grey -DSVF_GREY_KIND=GRAY4
# no IDF: the profile is validated first, then the missing IDF is reported; the failed configure locks nothing
IDF_PATH= cmake -S "$src" -B "$tmp/noidf" -DSVF_PROFILE=colour >"$tmp/noidf0.log" 2>&1 && fail "noidf: configured"
grep -q 'IDF_PATH' "$tmp/noidf0.log" || fail "noidf: no IDF_PATH message"
cfg noidf -DSVF_PROFILE=grey || fail "noidf: a failed configure locked the directory"
# the IDF path as a cache variable (-DIDF_PATH=, as PICO_SDK_PATH is given), with the environment empty
IDF_PATH= cmake -S "$src" -B "$tmp/cachepath" -DIDF_PATH="$tmp/idf" >"$tmp/cachepath.log" 2>&1 || fail "cachepath: -DIDF_PATH not honoured"
IDF_PATH= cmake -S "$src" -B "$tmp/badpath" -DIDF_PATH="$tmp/nonexistent" >"$tmp/badpath.log" 2>&1 && fail "badpath: configured"
grep -q 'IDF_PATH' "$tmp/badpath.log" || fail "badpath: no IDF_PATH message"
# defaults, and the lock of a configured directory
cfg two || fail "two: default configure"
grep -q 'SVF_PROFILE_CONFIGURED:INTERNAL=colour' "$tmp/two/CMakeCache.txt" || fail "two: default is not colour"
cfg two -DSVF_PROFILE=grey && fail "two: profile change accepted"
grep -q 'configured for colour' "$tmp/two.log" || fail "two: no 'configured for colour'"
cfg two -DSVF_PROFILE=colour -DSVF_GREY_KIND=GRAY4 || fail "two: colour locked by SVF_GREY_KIND"
cfg two -DSVF_DISPLAY=esp_rgb || fail "two: colour with esp_rgb"
cfg g -DSVF_PROFILE=grey || fail "g: configure"
grep -q 'SVF_PROFILE_CONFIGURED:INTERNAL=grey/GRAY8' "$tmp/g/CMakeCache.txt" || fail "g: lock key lacks the kind"
cfg g -DSVF_PROFILE=mono && fail "g: profile change accepted"
echo "esp32-cmake: OK"
