#!/bin/sh
# Checks of c/ports/esp32/main/CMakeLists.txt with mocked ESP-IDF commands (cmake -P; needs only cmake and python3-free sh).
# Early expansion: ESP-IDF runs every component's CMakeLists in a separate script-mode cmake with
# CMAKE_BUILD_EARLY_EXPANSION=1; a component that does not call idf_component_register there is dropped from the build.
# Real pass: what is registered (sources, include directories) and defined, for each profile and both IDF targets.
# Usage: sh c/ports/check/test_esp32_component.sh     Prints "esp32-component: OK"; exit 1 on a failure.
here=$(cd "$(dirname "$0")" && pwd)
main=$here/../esp32/main/CMakeLists.txt
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "esp32-component: FAIL: $1" >&2; exit 1; }

# the mocks log one "MOCK <command>: <args>" line each; commands that script mode cannot run are replaced too
cat >"$tmp/mocks.cmake" <<'EOM'
set(COMPONENT_LIB __idf_main)
set(CMAKE_BINARY_DIR "${SVF_TEST_BIN}")
set(CMAKE_CURRENT_BINARY_DIR "${SVF_TEST_BIN}")
function(_mock cmd)
  string(REPLACE ";" " " _a "${ARGN}")
  message(STATUS "MOCK ${cmd}: ${_a}")
endfunction()
macro(idf_component_register)
  _mock(idf_component_register ${ARGN})
endmacro()
function(add_custom_command)
  _mock(add_custom_command ${ARGN})
endfunction()
function(add_custom_target)
  _mock(add_custom_target ${ARGN})
endfunction()
function(add_dependencies)
  _mock(add_dependencies ${ARGN})
endfunction()
function(set_source_files_properties)
  _mock(set_source_files_properties ${ARGN})
endfunction()
function(target_compile_definitions)
  _mock(target_compile_definitions ${ARGN})
endfunction()
EOM
# run NAME ARGS... : the component file in script mode with the mocks; log in $tmp/NAME.log
run() {
	n=$1
	shift
	cat >"$tmp/$n.cmake" <<EOM
include("$tmp/mocks.cmake")
include("$main")
EOM
	cmake -DSVF_TEST_BIN="$tmp/bin-$n" "$@" -P "$tmp/$n.cmake" >"$tmp/$n.log" 2>&1 || { cat "$tmp/$n.log" >&2; fail "$n: cmake failed"; }
}
mocked() { grep "MOCK $2" "$tmp/$1.log"; }
# want N CMD TEXT : the log of run N holds a CMD line with TEXT (a fixed string)
want() { mocked "$1" "$2" | grep -qF -- "$3" || fail "$1: no '$2' line with '$3'"; }
dont() { mocked "$1" "$2" | grep -qF -- "$3" && fail "$1: '$2' line has '$3'"; true; }

# early expansion: no SVF_PROFILE (it is a separate process), the component is registered, with nothing else
run early -DCMAKE_BUILD_EARLY_EXPANSION=1
grep -q 'MOCK idf_component_register' "$tmp/early.log" || fail "early: idf_component_register not called"
[ "$(grep -c 'MOCK ' "$tmp/early.log")" -eq 1 ] || fail "early: other commands ran besides idf_component_register"

targets() { awk -v p="$1" '$1 == p {print $3}' "$here/../profiles.txt"; }
# case NAME PROFILE DRIVER IDF_TARGET [-D...] : the real pass
case_() {
	n=$1 p=$2 d=$3 t=$4
	shift 4
	run "$n" -DSVF_PROFILE="$p" -DSVF_DISPLAY=ili9341 -DIDF_TARGET="$t" "$@"
	want "$n" idf_component_register "main.c profile_$p.c disp_$d.c"
	want "$n" idf_component_register "/src/svf_draw.c"
	want "$n" idf_component_register "INCLUDE_DIRS $(cd "$here/../.." && pwd)/include"
	want "$n" idf_component_register "PRIV_INCLUDE_DIRS . $(cd "$here/.." && pwd)"
	want "$n" target_compile_definitions "__idf_main PRIVATE SVF_NO_SCALE SVF_TARGETS=$(targets "$p")"
	want "$n" add_dependencies "__idf_main svf_faces"
	if [ "$t" = esp32s3 ]; then want "$n" target_compile_definitions "SVF_ESP32S3=1"; else dont "$n" target_compile_definitions SVF_ESP32S3; fi
	if [ "$p" = grey ]; then want "$n" target_compile_definitions "SVF_GREY_KIND_GRAY8=1"; else dont "$n" target_compile_definitions SVF_GREY_KIND; fi
}
case_ colour colour ili9341 esp32c3
want colour idf_component_register "faces/paplg16.c"
want colour idf_component_register "faces/paplg18.c"
case_ colour_s3 colour ili9341 esp32s3
case_ rgb colour esp_rgb esp32s3 -DSVF_DISPLAY=esp_rgb
dont rgb idf_component_register disp_ili9341.c
case_ grey grey ssd1327 esp32c3
case_ mono mono ssd1306 esp32c3
want mono idf_component_register "faces/svf_face_data.c"
echo "esp32-component: OK"
