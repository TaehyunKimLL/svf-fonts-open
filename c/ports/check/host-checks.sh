#!/bin/sh
# Host checks of the MCU ports: grey_pack, and one display driver per build against the recording stubs.
# Usage: sh c/ports/check/host-checks.sh [OUT]   (from any directory: a relative OUT is taken from the caller's
# directory; OUT defaults to a temp directory). The checks themselves run from the repository root.
# Prints one "port-check-*: OK" line per check, nothing else on success; exit 1 on any failure.
set -u
OUT=${1:-}
if [ -z "$OUT" ]; then
	OUT=$(mktemp -d) || exit 1
	trap 'rm -rf "$OUT"' EXIT
fi
mkdir -p "$OUT" && OUT=$(cd "$OUT" && pwd) || exit 1 # absolute, from the caller's directory, before the cd below
cd "$(dirname "$0")/../../.." || exit 1
CC=${CC:-cc}
WARN="-std=c99 -Wall -Wextra -Werror"
status=0

# the screen table must agree with itself before anything is built from it (silent on success)
if ! msg=$(python3 c/ports/check/screens.py --check 2>&1); then
	echo "$msg" >&2
	status=1
fi

$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all -I c/ports \
	c/ports/check/test_grey_pack.c -o "$OUT/test_grey_pack" && "$OUT/test_grey_pack" || status=1

# build_run TAG EXTRA... : build and run test_drivers (ASan + UBSan) for the driver set by the caller's port/dir/stub/
# name/macro/srcs; stdout of the run goes to $OUT/run_$TAG.out, failures to stderr
build_run() {
	local tag=$1 # local: the caller's tag (the first pass's) must survive the S3 pass
	shift
	$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all "$@" \
		-DSVF_STUB_RECORD -D"$macro" -DTEST_ID="\"$port-$name\"" -I "$dir" -I "$stub" -I c/ports -I c/include \
		c/ports/check/test_drivers.c $srcs -o "$OUT/test_drivers_$tag" &&
		"$OUT/test_drivers_$tag" >"$OUT/run_$tag.out"
}

# driver PORT DIR STUBDIR NAME MACRO [s3|FLAGS]: build and run test_drivers for one driver, and, with s3, again for the
# ESP32-S3 pins (-DSVF_ESP32S3=1; its OK line is not printed, the first run's is, once both passed); any other sixth
# argument is a list of compiler flags for a second run tagged _alt (a module variant, e.g. "-DSH1106_REMAP=0"; quiet
# as well); then link it with
# the sections the firmware build uses and require its marker symbol to survive --gc-sections (display_init reads it once)
driver() {
	port=$1 dir=$2 stub=$3 name=$4 macro=$5 s3=${6:-}
	srcs=$dir/disp_$name.c
	tag=${port}_$name
	build_run "$tag" || { status=1; return; }
	if [ "$s3" = s3 ]; then
		build_run "${tag}_s3" -DSVF_ESP32S3=1 || { status=1; return; }
	elif [ -n "$s3" ]; then
		build_run "${tag}_alt" $s3 || { status=1; return; }
	fi
	cat "$OUT/run_$tag.out"
	$CC $WARN -DSVF_STUB_RECORD -D"$macro" -DTEST_ID="\"$port-$name\"" -I "$dir" -I "$stub" -I c/ports -I c/include \
		-Os -ffunction-sections -fdata-sections -Wl,--gc-sections \
		c/ports/check/test_drivers.c "$srcs" -o "$OUT/gc_${port}_$name" || { status=1; return; }
	nm "$OUT/gc_${port}_$name" | grep -q " svf_port_driver_$name\$" ||
		{ echo "port-check-driver-$port-$name: FAIL marker svf_port_driver_$name dropped by --gc-sections" >&2; status=1; }
}

# esp_rgb: the test includes disp_esp_rgb.c itself (one translation unit, over its own register and VRAM arrays), so
# the driver source is not on the command line; the driver also has to compile alone, with the default MMIO pointers,
# under -Werror on this 64-bit host (the pointer/integer split)
rgb_driver() {
	port=esp32 dir=c/ports/esp32/main stub=c/ports/esp32/stub name=esp_rgb macro=DRV_ESP_RGB srcs=
	build_run "${port}_$name" || { status=1; return; }
	cat "$OUT/run_${port}_$name.out"
	$CC -m64 $WARN -I c/ports -I c/include -I "$dir" -c "$dir/disp_esp_rgb.c" -o "$OUT/esp_rgb_default.o" || status=1
	$CC $WARN -DSVF_STUB_RECORD -D"$macro" -DTEST_ID="\"$port-$name\"" -I "$dir" -I "$stub" -I c/ports -I c/include \
		-Os -ffunction-sections -fdata-sections -Wl,--gc-sections \
		c/ports/check/test_drivers.c -o "$OUT/gc_${port}_$name" || { status=1; return; }
	nm "$OUT/gc_${port}_$name" | grep -q ' svf_port_driver_esp_rgb$' ||
		{ echo "port-check-driver-$port-$name: FAIL marker svf_port_driver_esp_rgb dropped by --gc-sections" >&2; status=1; }
}

driver pico c/ports/pico c/ports/pico/stub st7789 DRV_ST7789
driver pico c/ports/pico c/ports/pico/stub ssd1327 DRV_SSD1327
driver pico c/ports/pico c/ports/pico/stub ssd1306 DRV_SSD1306
driver esp32 c/ports/esp32/main c/ports/esp32/stub ili9341 DRV_ILI9341 s3
driver esp32 c/ports/esp32/main c/ports/esp32/stub ssd1327 DRV_ESP_SSD1327 s3
driver esp32 c/ports/esp32/main c/ports/esp32/stub ssd1306 DRV_ESP_SSD1306 s3
rgb_driver
# CH582 (SH1106 on ch582_i2c_write, which the test defines): the default module, then the variant with RAM at column 0
# and the other scan direction, then the SSD1306 build; then the bounded I2C write itself against a scripted peripheral, and the stub's
# names and values against the same checks the real SDK headers get (ch582_sdk_values.c)
driver ch582 c/ports/ch582 c/ports/ch582/stub sh1106 DRV_SH1106 "-DSH1106_COL_OFFSET=0 -DSH1106_REMAP=0"
# the SSD1306 build of the same driver (charge pump, page addressing, RAM column 0), upright and upside down (quiet);
# the globals of driver() above still name the CH582 driver
for v in "-DOLED_SSD1306=1" "-DOLED_SSD1306=1 -DSH1106_REMAP=0"; do
	build_run "ch582_sh1106_ssd$(echo "$v" | tr -cd 0-9)" $v >/dev/null || status=1
done
$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all -I c/ports/ch582/stub -I c/ports/ch582 \
	c/ports/check/test_ch582_i2c.c c/ports/ch582/i2c.c -o "$OUT/test_ch582_i2c" && "$OUT/test_ch582_i2c" || status=1
$CC $WARN -fsyntax-only -I c/ports/ch582/stub c/ports/check/ch582_sdk_values.c || status=1

# faces_for NAME: generate the C arrays of profile NAME's faces (profiles.txt column 4) into "$OUT/faces-NAME"/ (the sources
# are "$OUT/faces-NAME"/*.c; no word splitting of OUT). One face is the array svf_face_data (mono); several are named after the file (paplg16, paplg18).
# PROFILES_TXT overrides the table (a test).
faces_for() {
	name=$1
	list=$(awk -v p="$1" '$1 == p {print $4}' "${PROFILES_TXT:-c/ports/profiles.txt}")
	[ -n "$list" ] || return 1
	set -- $(echo "$list" | tr ',' ' ')
	rm -rf "$OUT/faces-$name"
	mkdir -p "$OUT/faces-$name" || return 1
	for f in "$@"; do
		if [ $# -eq 1 ]; then n=svf_face_data; else n=$(basename "$f" .SVF | tr 'A-Z' 'a-z'); fi
		python3 -I c/bench/mkface.py "svf/$f" "$OUT/faces-$name/$n.c" --name "$n" --profile mcu-strict || return 1
	done
}

# the faces come from the table: a row with another face embeds that face (silent on success)
sed 's|dos/NEODG16G.SVF|dos/PAPLG16.SVF|' c/ports/profiles.txt >"$OUT/profiles-alt.txt"
if PROFILES_TXT="$OUT/profiles-alt.txt" faces_for mono && head -1 "$OUT/faces-mono/svf_face_data.c" | grep -q 'svf/dos/PAPLG16.SVF'; then :
else
	echo "port-check-faces: FAIL mono face did not follow profiles.txt" >&2
	status=1
fi

# profile PORT DIR BOARD NAME [BE [ID [EXTRA]]]: build and run test_profiles (ASan + UBSan) for dir/profile_NAME.c against the
# reference of screen_ref.py for BOARD (colour: byte order BE, default the board's; ID the printed name, default
# PORT-NAME; EXTRA a compiler option such as -DSVF_ESP32S3=1, with its output not printed); then link it with the
# sections the firmware build uses, require its marker symbol to survive --gc-sections (profile_run reads it once)
# and run that image too (marker contents)
profile() {
	local port=$1 dir=$2 board=$3 name=$4 be=${5:-} id=${6:-$1-$4} extra=${7:-} targets greydef refopt beopt ref miss lines
	targets=$(awk -v p="$name" '$1 == p {print $3}' c/ports/profiles.txt)
	miss=$(python3 -c 'import sys; sys.path.insert(0, "c/ports/check"); import screens; print(screens.PROFILES[sys.argv[1]]["missing_advance"])' "$name") || { status=1; return; }
	faces_for "$name" || { status=1; return; }
	greydef= refopt= beopt=
	# screen_ref.py names the reference after board and profile only: one directory per run, so the -be and -le runs
	# (and the S3 run) write distinct files
	mkdir -p "$OUT/ref-$id" || { status=1; return; }
	ref="$OUT/ref-$id/$board-$name.ref"
	lines="$OUT/ref-$id/$board-$name.lines"
	[ "$name" != grey ] || { greydef=-DSVF_GREY_KIND_GRAY8=1 refopt=--gray8 ref="$OUT/ref-$id/$board-grey.gray8.ref"; }
	[ -z "$be" ] || beopt="--bigendian $be"
	python3 c/ports/check/screen_ref.py --ref-only $refopt $beopt "$board" "$name" "$OUT/ref-$id" || { status=1; return; }
	python3 c/ports/check/screens.py lines "$board" "$name" >"$lines" || { status=1; return; }
	set -- -DPROFILE_NAME="\"$name\"" -DPROFILE_MARKER="svf_port_profile_$name" -DEXPECT_MISSING_ADVANCE="$miss" \
		-DTEST_ID="\"$id\"" -DTEST_BIGENDIAN="${be:-0}" -DSVF_TARGETS="$targets" -DSVF_NO_SCALE $greydef $extra \
		-I "$dir" -I c/ports -I c/include
	$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all "$@" -Wl,--wrap=svf_draw_utf8 \
		c/ports/check/test_profiles.c "$dir/profile_$name.c" c/src/*.c "$OUT/faces-$name"/*.c \
		-o "$OUT/test_profiles_$id" || { status=1; return; }
	if [ -n "$extra" ]; then
		"$OUT/test_profiles_$id" "$ref" "$lines" >/dev/null || { status=1; return; }
	else
		"$OUT/test_profiles_$id" "$ref" "$lines" || { status=1; return; }
	fi
	$CC $WARN "$@" -Wl,--wrap=svf_draw_utf8 -Os -ffunction-sections -fdata-sections -Wl,--gc-sections \
		c/ports/check/test_profiles.c "$dir/profile_$name.c" c/src/*.c "$OUT/faces-$name"/*.c -o "$OUT/gc_profile_$id" ||
		{ status=1; return; }
	nm "$OUT/gc_profile_$id" | grep -q " svf_port_profile_$name\$" ||
		{ echo "port-check-profile-$id: FAIL marker svf_port_profile_$name dropped by --gc-sections" >&2; status=1; return; }
	"$OUT/gc_profile_$id" "$ref" "$lines" >/dev/null || { status=1; return; }
}

profile pico c/ports/pico pico colour 1
profile pico c/ports/pico pico grey
profile pico c/ports/pico pico mono
# the ESP32 colour profile on both pixel orders: ILI9341 takes high byte first (-be), esp_rgb is little-endian (-le);
# the ESP32-S3 text column (-DSVF_ESP32S3=1) is checked against the esp32s3 reference, quietly
profile esp32 c/ports/esp32/main esp32c3 colour 1 esp32-colour-be
profile esp32 c/ports/esp32/main esp32c3 colour 0 esp32-colour-le
profile esp32 c/ports/esp32/main esp32s3 colour 0 esp32s3-colour-le -DSVF_ESP32S3=1
profile esp32 c/ports/esp32/main esp32c3 grey
profile esp32 c/ports/esp32/main esp32c3 mono
profile ch582 c/ports/ch582 ch582 mono

# the whole CH582 image on the host: main.c (as port_main) with profile_mono.c, the real SH1106 driver and the library,
# over a model of the panel (RAM, page and column registers, framing); the panel's RAM window must equal the svfline
# reference, then the LED codes of the idle loop; the negative build (RAM offset 0) must show the shifted picture, the SSD1306 build (quiet
# as well) the same picture from column 0
panel_check() {
	local targets neg o
	targets=$(awk '$1 == "mono" {print $3}' c/ports/profiles.txt)
	faces_for mono || { status=1; return; }
	mkdir -p "$OUT/sh1106-panel" || { status=1; return; }
	python3 c/ports/check/screen_ref.py --ref-only ch582 mono "$OUT/sh1106-panel" || { status=1; return; }
	for neg in "" "-DSH1106_COL_OFFSET=0" "-DOLED_SSD1306=1"; do
		o="$OUT/sh1106-panel/${neg:+$(echo "$neg" | tr -cd 'A-Z0-9')-}"
		set -- -DSVF_STUB_RECORD -DSVF_TARGETS="$targets" -DSVF_NO_SCALE -DSVF_NO_STREAM \
			-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT $neg \
			-I c/ports/ch582/stub -I c/ports/ch582 -I c/ports -I c/include
		$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all "$@" -Dmain=port_main \
			-c c/ports/ch582/main.c -o "${o}ch582_main.o" &&
			$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all "$@" \
				c/ports/check/test_sh1106_panel.c "${o}ch582_main.o" c/ports/ch582/profile_mono.c c/ports/ch582/disp_sh1106.c \
				c/src/*.c "$OUT/faces-mono"/*.c -o "${o}test_sh1106_panel" || { status=1; return; }
		if [ "$neg" = -DOLED_SSD1306=1 ]; then
			"${o}test_sh1106_panel" "$OUT/sh1106-panel/ch582-mono.ref" "$OUT/sh1106-panel" >/dev/null || { status=1; return; }
		elif [ -z "$neg" ]; then
			"${o}test_sh1106_panel" "$OUT/sh1106-panel/ch582-mono.ref" "$OUT/sh1106-panel" || { status=1; return; }
			python3 c/ports/check/screen_ref.py ch582 mono "$OUT/sh1106-panel" >"$OUT/sh1106-panel/compare.out" 2>&1 ||
				{ cat "$OUT/sh1106-panel/compare.out" >&2; status=1; return; }
		else
			"${o}test_sh1106_panel" "$OUT/sh1106-panel/ch582-mono.ref" "$OUT/sh1106-panel" >/dev/null || { status=1; return; }
		fi
	done
}
panel_check

# ESP32 build rules and entry points (silent on success): the CMake configure rules (stand-in IDF_PATH) and the component
# file with mocked IDF commands (early expansion registers it; sources and definitions per profile and target) need only
# cmake; esp_rst.h's reset pulse is at least 10 ms at every tick rate; main_qemu.c (display_init, profile_run, then
# "screen=ready" flushed; svf_port_idle prints "screen=failed") runs on the host with recording stubs
for t in test_esp32_cmake test_esp32_component; do
	if ! command -v cmake >/dev/null 2>&1; then
		echo "port-check-$t: FAIL cmake not found" >&2
		status=1
	elif ! msg=$(sh "c/ports/check/$t.sh" 2>&1); then
		echo "$msg" >&2
		status=1
	fi
done
for ms in $(seq 1 20); do # every tick length, 1000 Hz .. 50 Hz
	$CC $WARN -DSVF_STUB_TICK_MS=$ms -I c/ports/esp32/stub -I c/ports/esp32/main c/ports/check/test_esp_rst.c \
		-o "$OUT/test_esp_rst_$ms" && "$OUT/test_esp_rst_$ms" || status=1
done
$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all -include c/ports/check/test_main_qemu_hooks.h \
	-Dmain=qemu_main -Dsvf_port_idle=qemu_idle -I c/ports/esp32/main -I c/ports -c c/ports/esp32/main/main_qemu.c \
	-o "$OUT/main_qemu.o" &&
	$CC $WARN -g -fsanitize=address,undefined -fno-sanitize-recover=all -I c/ports/esp32/main -I c/ports \
		c/ports/check/test_main_qemu.c "$OUT/main_qemu.o" -o "$OUT/test_main_qemu" &&
	"$OUT/test_main_qemu" >/dev/null || status=1

# the negative fixture of esp-screen.py (a guest printing a line before "screen=ready"; cross-built in run-screens.sh) must
# at least stay valid C
$CC $WARN -fsyntax-only c/ports/check/fixtures/fix_banner.c || status=1

# the installers' tree manifests (c/cross/manifest.sh, behind every --verify) and the profiles.txt reader of the CMake
# builds (profiles.cmake; needs cmake): silent on success
for t in c/cross/test-manifest.sh c/ports/check/test_profiles_cmake.sh; do
	if ! msg=$(sh "$t" 2>&1); then
		echo "$msg" >&2
		echo "host-checks: FAIL $t" >&2
		status=1
	fi
done

# the gates of c/cross/build-all.sh that need no toolchain: the screens gate and the SIZES.md comparison (silent on success)
if ! msg=$(sh c/cross/test-build-all.sh 2>&1); then
	echo "$msg" >&2
	status=1
fi

# the gates of c/cross/check-features.sh that need no toolchain (silent on success)
if ! msg=$(sh c/cross/test-check-features.sh 2>&1); then
	echo "$msg" >&2
	status=1
fi

# the size line and the gates of the CH582 image (c/ports/ch582/image_sizes.py; silent on success)
if ! msg=$(python3 -I c/ports/check/test_image_sizes.py 2>&1); then
	echo "$msg" >&2
	echo "host-checks: FAIL test_image_sizes.py" >&2
	status=1
fi

# the system clock agrees in the Makefile (FREQ_SYS) and main.c (SetSysClock): 24 MHz (silent on success)
fq=$(sed -n 's/.*-DFREQ_SYS=\([0-9]*\).*/\1/p' c/ports/ch582/Makefile | head -n 1)
pl=$(sed -n 's/^[^*]*SetSysClock(CLK_SOURCE_PLL_\([0-9]*\)MHz).*/\1/p' c/ports/ch582/main.c | head -n 1)
if [ -z "$fq" ] || [ -z "$pl" ] || [ "$fq" != "${pl}000000" ] || [ "$pl" != 24 ]; then
	echo "host-checks: FAIL ch582 clock: Makefile FREQ_SYS='$fq', main.c SetSysClock PLL='$pl' MHz (both must say 24 MHz)" >&2
	status=1
fi

exit $status
