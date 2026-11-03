#!/bin/sh
# The Pico emulated screens: builds the three profile images and the negative fixtures against the pico-sdk, runs
# pico-screen.mjs on each (the three real images must byte-match screen_ref.py and leave their PNGs), and checks that
# every failure exit of the runner fires on a purpose-built bad input.
# Usage: sh c/ports/check/test_pico_screen.sh   (from the repository root)
# Environment: OPT (default ~/opt; the pico-sdk, the Arm toolchain, rp2040js, the boot ROM and node v24 come from there),
# NODE, OUT (default c/build/screens: the .fb, .log, .png, -ref.png files and the build trees go there)
# Prints "pico-screen-negative: OK", or "pico-screen: SKIPPED (missing: ...)" when something is not installed (exit 0,
# or 1 with SVF_REQUIRE_SCREENS=1); exit 1 on a failure.

# the settings (OPT, NODE, SDK, ARMTC as TC, RPJS, ROM, NM, OUT) and build_pico come from screens-lib.sh
here=$(cd "$(dirname "$0")" && pwd)
SCR_DIR=$here
. "$here/screens-lib.sh"
root=$SCR_ROOT
TC=$ARMTC

# A missing dependency is a SKIPPED line, never an OK; with SVF_REQUIRE_SCREENS=1 (set by build-all.sh --ports) it is a failure.
missing=
for need in "$SDK/pico_sdk_init.cmake" "$RPJS/node_modules/rp2040js/package.json" "$ROM" "$NM" "$NODE"; do
	[ -e "$need" ] || missing="$missing $need"
done
if [ -n "$missing" ]; then
	echo "pico-screen: SKIPPED (missing:$missing)"
	[ "${SVF_REQUIRE_SCREENS:-}" != 1 ] || exit 1
	exit 0
fi
mkdir -p "$OUT" || exit 1
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() {
	echo "pico-screen: FAIL: $1" >&2
	exit 1
}

# the skip rule itself: an empty OPT is SKIPPED and exits 0, or 1 with SVF_REQUIRE_SCREENS=1
msg=$(env -u SVF_REQUIRE_SCREENS OPT=$tmp/none sh "$0" 2>&1) || fail "a missing dependency failed without SVF_REQUIRE_SCREENS"
case $msg in "pico-screen: SKIPPED (missing:"*) ;; *) fail "skip message: $msg" ;; esac
msg=$(SVF_REQUIRE_SCREENS=1 OPT=$tmp/none sh "$0" 2>&1) && fail "SVF_REQUIRE_SCREENS=1 did not fail on a missing dependency"
case $msg in "pico-screen: SKIPPED (missing:"*) ;; *) fail "required skip message: $msg" ;; esac

# the panel models' unit tests (silent on success)
"$NODE" --test "$here/test_panels.mjs" >"$tmp/panels.out" 2>&1 || { cat "$tmp/panels.out" >&2; fail "test_panels.mjs"; }
build() { # DIR SRC [CMAKE ARGS...] ; builds into DIR, log in DIR.log
	d=$1
	s=$2
	shift 2
	PICO_SDK_PATH=$SDK PICO_TOOLCHAIN_PATH=$TC cmake -S "$s" -B "$d" -DPICO_NO_PICOTOOL=1 "$@" >"$d.log" 2>&1 &&
		cmake --build "$d" >>"$d.log" 2>&1 || { tail -n 20 "$d.log" >&2; fail "build of $d"; }
}
run() { # ELF PROFILE SHOWS OUTDIR [BOOTROM]: the runner's stdout; its exit status is left in $rc
	"$NODE" "$here/pico-screen.mjs" "$RPJS" "${5:-$ROM}" "$NM" "$1" "$2" "$3" "$4"
}
shows() { python3 -I "$here/screens.py" shows "$1"; }

# the three real images: ok line, then identical to the reference (the compare writes the PNG)
for p in colour grey mono; do
	build_pico $p || fail "build of $p"
	line=$(run "$OUT/build-pico-$p/svf_pico_$p.elf" $p "$(shows $p)" "$OUT") || fail "$p: $line"
	echo "$line" | grep -q "^ok: shows=$(shows $p) " || fail "$p: $line"
	echo "pico-$p: $line"
	python3 -I "$here/screen_ref.py" pico $p "$OUT" | grep -q "^screen-pico-$p: OK\$" || fail "$p: differs from the reference"
	[ -s "$OUT/pico-$p.png" ] || fail "$p: no PNG"
done

# negatives: one per failure exit of the runner
build "$tmp/fix" "$here/fixtures"
neg() { # NAME EXPECTED_PREFIX ELF PROFILE SHOWS [BOOTROM]
	name=$1
	want=$2
	d=$tmp/neg-$name
	mkdir -p "$d"
	# an earlier run's frame and log are in the output directory: a failing run must leave neither as a result
	echo stale >"$d/pico-$4.fb"
	echo stale >"$d/pico-$4.log"
	msg=$(run "$3" "$4" "$5" "$d" "${6:-$ROM}")
	rc=$?
	[ "$rc" = 1 ] || fail "$name: exit $rc, not 1 ($msg)"
	case $msg in "$want"*) ;; *) fail "$name: '$msg' does not start with '$want'" ;; esac
	[ ! -e "$d/pico-$4.fb" ] || fail "$name: a stale .fb is still there"
	[ ! -e "$d/pico-$4.log" ] || ! grep -q '^stale$' "$d/pico-$4.log" || fail "$name: a stale .log is still there"
}
mono=$OUT/build-pico-mono/svf_pico_mono.elf
neg bkpt "fail: BKPT #" "$tmp/fix/fix_bkpt.elf" mono 1
neg wfi "fail: waiting with no alarm" "$tmp/fix/fix_wfi.elf" mono 1
neg noshow "fail: shows 0 != 1" "$tmp/fix/fix_noshow.elf" mono 1
# the mono image on the colour panel: the colour profile's I2C bus NACKs, the SDK's write returns, no SPI byte comes
neg wrong_profile "fail: shows 0 != 15" "$mono" colour 15
# the NACKs of the colour profile's unused I2C bus are in its .log, stamped with the emulated time
grep -q '^\[[0-9]* ns\] nack 0x3c write$' "$tmp/neg-wrong_profile/pico-colour.log" || fail "wrong_profile: no stamped NACK line in the .log"
# the colour image on the mono panel: the SPI bytes go nowhere, the panel saw no show
neg wrong_profile_colour_on_mono "fail: shows 0 != 1" "$OUT/build-pico-colour/svf_pico_colour.elf" mono 1
# 20 s of sleep: the run ends at the 10 s emulated-time cap (the sleep is alarm-driven, a few iterations)
neg timeout "fail: emulated time > 10 s" "$tmp/fix/fix_sleep.elf" mono 1
# a busy loop: the host iteration bound (lowered for the test; its default is 10^9)
SVF_PICO_ITER_BOUND=2000000
export SVF_PICO_ITER_BOUND
neg iteration_bound "fail: iteration bound" "$tmp/fix/fix_loop.elf" mono 1
unset SVF_PICO_ITER_BOUND
neg wrong_count "fail: shows 1 != 2" "$mono" mono 2
# SVF_PICO_ITER_BOUND may only lower the bound (the .log names the bound in force)
grep -q '^iteration bound 1000000000$' "$tmp/neg-wrong_count/pico-mono.log" || fail "default iteration bound not 10^9"
for v in 1e12 Infinity 0 -5 abc; do
	SVF_PICO_ITER_BOUND=$v
	export SVF_PICO_ITER_BOUND
	neg "bound_$v" "fail: shows 1 != 2" "$mono" mono 2
	unset SVF_PICO_ITER_BOUND
	grep -q '^iteration bound 1000000000$' "$tmp/neg-bound_$v/pico-mono.log" || fail "SVF_PICO_ITER_BOUND=$v changed the bound"
done
SVF_PICO_ITER_BOUND=12345
export SVF_PICO_ITER_BOUND
neg bound_low "fail: iteration bound" "$mono" mono 1
unset SVF_PICO_ITER_BOUND
grep -q '^iteration bound 12345$' "$tmp/neg-bound_low/pico-mono.log" || fail "a lower bound is not in force"
head -c 2000 "$mono" >"$tmp/bad.elf"
neg short_elf "fail: bad ELF:" "$tmp/bad.elf" mono 1
printf 'not an elf at all, but long enough to hold a header of fifty-two bytes....' >"$tmp/junk.elf"
neg junk_elf "fail: bad ELF:" "$tmp/junk.elf" mono 1
# a file over 16 MiB is refused before it is read whole
head -c 17000000 /dev/zero >"$tmp/big.elf"
neg big_elf "fail: bad ELF: " "$tmp/big.elf" mono 1
case $msg in *"16 MiB"*) ;; *) fail "big_elf: '$msg' does not name the size limit" ;; esac
# a program header table whose end overflows 32 bits is named as an overflow
python3 -I - "$mono" "$tmp/phoff.elf" <<'PY' || fail "patch ELF (phoff)"
import struct, sys
d = bytearray(open(sys.argv[1], "rb").read())
struct.pack_into("<I", d, 28, 0xFFFFFFF0)
open(sys.argv[2], "wb").write(d)
PY
neg phoff_overflow "fail: bad ELF: program header table overflows 32 bits" "$tmp/phoff.elf" mono 1
# a PT_LOAD at 0xFFFFFFF0 (past flash and SRAM, and its end overflows 32 bits), and one inside the address space but outside
for name in 0xFFFFFFF0 0x30000000; do
	python3 -I - "$mono" "$tmp/seg.elf" $name <<'PY' || fail "patch ELF"
import struct, sys
src, dst, paddr = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
d = bytearray(open(src, "rb").read())
phoff, phentsize, phnum = struct.unpack_from("<I", d, 28)[0], struct.unpack_from("<H", d, 42)[0], struct.unpack_from("<H", d, 44)[0]
for i in range(phnum):
	ph = phoff + i * phentsize
	if struct.unpack_from("<I", d, ph)[0] == 1 and struct.unpack_from("<I", d, ph + 16)[0] > 0:
		struct.pack_into("<I", d, ph + 12, paddr)
		break
open(dst, "wb").write(d)
PY
	neg "seg_$name" "fail: bad ELF: PT_LOAD" "$tmp/seg.elf" mono 1
done
head -c 16383 "$ROM" >"$tmp/short.rom"
neg bootrom "fail: bad bootrom" "$mono" mono 1 "$tmp/short.rom"
echo "pico-screen-negative: OK"
