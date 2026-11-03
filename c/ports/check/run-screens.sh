#!/bin/sh
# The five emulated screens: Pico colour, grey and mono under rp2040js, ESP32-C3 and ESP32-S3 colour under Espressif's
# QEMU (esp_rgb panel). Each image is built, run to its last frame, and the panel memory is compared byte for byte with
# the reference of screen_ref.py (the ESP32 screendump PPM too).
# Usage: sh c/ports/check/run-screens.sh [OUT]   (default c/build/screens; a path with spaces is fine)
#        sh c/ports/check/run-screens.sh --missing   (prints what the screens lack, the paths space separated; empty
#        when nothing; exit 0: build-all.sh's screens gate)
# Writes under OUT: build-pico-<p>/ and esp/ (the builds), <board>-<profile>.{fb,log,ref,png}, -ref.png, a -diff.png on a
# difference, <board>-colour.ppm and -qemu.err for the ESP32 runs.
# First `install-toolchains.sh --verify arm xtensa esp pico-sdk` and `install-emulators.sh --verify rp2040js bootrom
# [qemu-rv] [qemu-xt]`, before anything is judged missing (a present but drifted install stops the run). Prints, per run,
# "screen-<board>-<profile>: OK" and "pico-sdk-size <profile>: text T data D bss B" for each Pico image; exit 1 on any
# failure. A screen is accepted only when its runner exited 0 and printed a line starting "ok: " in this run: the
# board's old .fb, .ppm and .png are deleted first, so a screen that did not run cannot print OK.
# Environment: OPT (default ~/opt), NODE (default node v24 under OPT), QEMU_RV and QEMU_XT (the QEMU binaries; defaults
# under OPT, an override is not verified). What a group of screens needs and lacks (the Pico: pico-sdk, rp2040js, boot
# ROM, node, Arm toolchain; each ESP32 board: its toolchain, executable QEMU, Pillow) prints
# "screen-<group>: SKIPPED (missing: ...)" and the group is not run: exit 0, or 1 with SVF_REQUIRE_SCREENS=1 (which
# build-all.sh --ports sets; then nothing is built). An OUT in the environment is the default output directory (as
# test_pico_screen.sh uses it); the argument wins.
# SVF_SIZES_MD=FILE compares the Pico SDK image sizes with FILE instead of c/cross/SIZES.md (a test hook): the run prints
# "screens: note: SIZES.md overridden: FILE" and exits 3 whatever happened; build-all.sh unsets it.
SCR_DIR=$(cd "$(dirname "$0")" && pwd) || exit 1
. "$SCR_DIR/screens-lib.sh"
here=$SCR_DIR
set -u

# lacking GROUP-PATHS...: the paths that are not there (-x for programs), space separated
lacking_f() { for n in "$@"; do [ -f "$n" ] || printf ' %s' "$n"; done; }
lacking_x() { for n in "$@"; do [ -x "$n" ] || printf ' %s' "$n"; done; }
pillow=
python3 -I -c 'import PIL' 2>/dev/null || pillow=" Pillow"
pico_base="$(lacking_f "$SDK/pico_sdk_init.cmake" "$RPJS/node_modules/rp2040js/package.json" "$ROM")$(lacking_x "$NM" "$NODE" "$ARMTC/bin/arm-none-eabi-gcc" "$ARMTC/bin/arm-none-eabi-size")"

rv_base="$(lacking_x "$RV-gcc" "$QEMU_RV")"
xt_base="$(lacking_x "$XT-gcc" "$QEMU_XT")"
# Pillow serves every group (screen_ref.py writes the PNGs); in the all-groups list it is named once
pico_miss=$pico_base$pillow rv_miss=$rv_base$pillow xt_miss=$xt_base$pillow
all_miss=$pico_base$rv_base$xt_base$pillow
# --missing: print what the screens lack (all groups, space separated, empty when nothing) and stop: build-all.sh asks
# this before it runs the screens, so the two cannot disagree. Nothing is verified, built or written.
if [ "${1:-}" = --missing ]; then
	echo "${all_miss# }"
	exit 0
fi
[ -n "${1:-}" ] && OUT=$1
mkdir -p "$OUT" || exit 1
OUT=$(cd "$OUT" && pwd) || exit 1

# the installs this run uses, checked against their pins first (silent on success; an absent tree is reported by the
# installer as not installed, exit 0, and judged below); an override of a QEMU is not a pinned tree
emu="rp2040js bootrom"
[ "$QEMU_RV" != "$OPT/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32" ] || emu="$emu qemu-rv"
[ "$QEMU_XT" != "$OPT/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa" ] || emu="$emu qemu-xt"
if ! msg=$(OPT=$OPT sh "$SCR_ROOT/c/cross/install-toolchains.sh" --verify arm xtensa esp pico-sdk 2>&1); then
	echo "$msg" >&2
	echo "screens: install verification failed (install-toolchains.sh --verify arm xtensa esp pico-sdk)" >&2
	exit 1
fi
# shellcheck disable=SC2086
if ! msg=$(OPT=$OPT sh "$SCR_ROOT/c/bench/install-emulators.sh" --verify $emu 2>&1); then
	echo "$msg" >&2
	echo "screens: install verification failed (install-emulators.sh --verify $emu)" >&2
	exit 1
fi

if [ -n "$all_miss" ] && [ "${SVF_REQUIRE_SCREENS:-}" = 1 ]; then
	echo "screens: SKIPPED (missing:$all_miss)"
	exit 1
fi

# an override of a tool the installers pin is not verified: say so
for n in QEMU_RV QEMU_XT NODE; do
	eval "v=\$$n"
	case $n in QEMU_RV) def=$OPT/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32 ;;
	QEMU_XT) def=$OPT/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa ;;
	*) def=$OPT/node-v24.13.0-linux-x64/bin/node ;; esac
	[ "$v" = "$def" ] || echo "screens: note: unpinned $n=$v"
done

status=0
SIZES_MD=${SVF_SIZES_MD:-$SCR_ROOT/c/cross/SIZES.md} # tests point it at a doctored copy
if [ -n "${SVF_SIZES_MD:-}" ]; then # such a run proves nothing about the real table: it never ends in success
	echo "screens: note: SIZES.md overridden: $SVF_SIZES_MD"
	sizes_override=1
fi
sizes_rows=$OUT/pico-sdk-sizes.txt # "profile text data bss" a Pico image, compared with SIZES.md after the loop
rm -f "$sizes_rows"
ref() { python3 -I "$here/screen_ref.py" "$@"; } # BOARD PROFILE OUT: its OK line, or what differs (exit 1)

# accepted LINE RC: a run happened now and said so
accepted() { [ "$2" = 0 ] && case $1 in "ok: "*) return 0 ;; esac; return 1; }

if [ -n "$pico_miss" ]; then
	rm -f "$OUT"/pico-*.fb "$OUT"/pico-*.png
	echo "screen-pico: SKIPPED (missing:$pico_miss)"
else
	for p in colour grey mono; do
		rm -f "$OUT/pico-$p.fb" "$OUT/pico-$p.png" "$OUT/pico-$p.log"
		if ! build_pico $p; then status=1; continue; fi
		elf=$OUT/build-pico-$p/svf_pico_$p.elf
		if ! sz=$("$ARMTC/bin/arm-none-eabi-size" "$elf" | awk 'NR == 2 { print "text", $1, "data", $2, "bss", $3 }') || [ -z "$sz" ]; then
			echo "screen-pico-$p: FAIL arm-none-eabi-size"
			status=1
			continue
		fi
		echo "pico-sdk-size $p: $sz"
		echo "$p $sz" | awk '{ print $1, $3, $5, $7 }' >>"$sizes_rows"
		line=$("$NODE" "$here/pico-screen.mjs" "$RPJS" "$ROM" "$NM" "$elf" $p "$(python3 -I "$here/screens.py" shows $p)" "$OUT")
		if ! accepted "$line" $?; then
			echo "screen-pico-$p: FAIL $line"
			status=1
			continue
		fi
		echo "pico-$p: $line"
		ref pico $p "$OUT" || status=1
	done
	# the link sizes are documented in SIZES.md ("Pico SDK images"): a change is a difference to settle there
	# (a profile that did not build is already a failure; the check also counts rows, so a fourth profile cannot slip by)
	if [ -s "$sizes_rows" ]; then
		if ! sh "$SCR_ROOT/c/cross/check-sizes-md.sh" --pico-sdk "$sizes_rows" "$SIZES_MD"; then
			echo "screens: SIZES.md \"Pico SDK images\" differs from the sizes measured above"
			status=1
		fi
	fi
fi

for b in esp32c3 esp32s3; do
	case $b in esp32c3) q=$QEMU_RV m=$rv_miss ;; *) q=$QEMU_XT m=$xt_miss ;; esac
	rm -f "$OUT/$b-colour.fb" "$OUT/$b-colour.ppm" "$OUT/$b-colour.png"
	if [ -n "$m" ]; then
		echo "screen-$b: SKIPPED (missing:$m)"
		continue
	fi
	if ! build_esp $b; then status=1; continue; fi
	line=$(python3 -I "$here/esp-screen.py" "$q" "$OUT/esp/screen-$b.elf" $b "$OUT")
	if ! accepted "$line" $?; then
		echo "screen-$b-colour: FAIL $line"
		status=1
		continue
	fi
	echo "$b-colour: $line"
	ref $b colour "$OUT" || status=1
done

# the runner's negative: a guest that prints a banner before screen=ready is refused, not run
if [ -z "$rv_miss" ]; then
	if build_esp esp32c3 "$here/fixtures/fix_banner.c"; then
		mkdir -p "$OUT/neg-banner"
		msg=$(python3 -I "$here/esp-screen.py" "$QEMU_RV" "$OUT/esp/fix_banner-esp32c3.elf" esp32c3 "$OUT/neg-banner")
		rc=$?
		case $msg in
		"fail: unexpected line: boot banner"*) [ "$rc" = 1 ] || { echo "screens: banner fixture exit $rc"; status=1; } ;;
		*) echo "screens: banner fixture: '$msg' (exit $rc)"; status=1 ;;
		esac
	else
		status=1
	fi
fi
if [ "${sizes_override:-0}" = 1 ]; then # not a verdict on the repository: exit 3 whatever the screens did
	[ $status -eq 0 ] || echo "screens: FAIL (and SIZES.md overridden)"
	exit 3
fi
exit $status
