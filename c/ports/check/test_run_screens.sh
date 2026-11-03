#!/bin/sh
# Tests of run-screens.sh's own rules (the emulators themselves are tested by test_pico_screen.sh and test_esp_screen.py):
#  - with SVF_REQUIRE_SCREENS=1 a QEMU that is not executable fails the run at once, naming it, with no OK line and nothing built
#  - without it that board is SKIPPED (no OK line) although a previous run left its .fb in OUT, and the others run
#    and are OK; the stale files are gone afterwards
#  - OUT with a space in it works
# Usage: sh c/ports/check/test_run_screens.sh   Prints "run-screens-gates: OK"; exit 1 on a failure. Needs the emulated
# screens installed (about 30 s); with SVF_REQUIRE_SCREENS unset a host without them reports SKIPPED and passes nothing.
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "run-screens-gates: FAIL: $1" >&2; exit 1; }
RS="sh $here/run-screens.sh"
echo "not a program" >"$tmp/notexec"
chmod 644 "$tmp/notexec"

# 1. required: fails fast
out="$tmp/req out"
msg=$(SVF_REQUIRE_SCREENS=1 QEMU_RV=$tmp/notexec $RS "$out" 2>&1)
rc=$?
[ "$rc" = 1 ] || fail "required, QEMU not executable: exit $rc, not 1 ($msg)"
case $msg in *"SKIPPED (missing:"*"$tmp/notexec"*) ;; *) fail "required: no SKIPPED line naming the QEMU: $msg" ;; esac
case $msg in *": OK"*) fail "required: an OK line: $msg" ;; esac
[ ! -d "$out/build-pico-mono" ] || fail "required: something was built before the failure"

# 2. not required: the board is skipped, the rest runs; stale files from an earlier run do not become an OK
out="$tmp/out dir"
mkdir -p "$out"
python3 -I "$here/screen_ref.py" --ref-only esp32c3 colour "$out" >/dev/null || fail "reference"
cp "$out/esp32c3-colour.ref" "$out/esp32c3-colour.fb"
msg=$(env -u SVF_REQUIRE_SCREENS QEMU_RV=$tmp/notexec $RS "$out" 2>&1)
rc=$?
case $msg in *"SKIPPED (missing:"*) ;; *) fail "not required: no SKIPPED line: $msg" ;; esac
case $msg in *"screen-esp32c3"*"SKIPPED"*) ;; *) fail "not required: the C3 is not reported SKIPPED: $msg" ;; esac
case $msg in *"screens: note: unpinned QEMU_RV=$tmp/notexec"*) ;; *) fail "an override of QEMU_RV is not noted: $msg" ;; esac
case $msg in *"screens: note: unpinned NODE"*|*"unpinned QEMU_XT"*) fail "a default is called unpinned: $msg" ;; esac
case $msg in *"screen-esp32c3-colour: OK"*) fail "a stale .fb gave an OK for the board that did not run: $msg" ;; esac
[ "$rc" = 0 ] || fail "not required: exit $rc ($msg)"
for s in pico-colour pico-grey pico-mono esp32s3-colour; do
	case $msg in *"screen-$s: OK"*) ;; *) fail "not required, OUT with a space: no 'screen-$s: OK': $msg" ;; esac
done
[ ! -e "$out/esp32c3-colour.fb" ] || fail "the stale esp32c3-colour.fb is still there"
# 3. the SIZES.md gate bites through run-screens.sh: a doctored "Pico SDK images" table is named; and a run with SVF_SIZES_MD
# set notes it and exits 3, never 0 (the boards that can run still print their OK lines); the real table passes (case 2)
# the mono row's text is read from SIZES.md, so a re-measure needs no edit here
mono=$(awk -F'|' '/^## Pico SDK images/ { on = 1; next } /^## / { on = 0 } on && $2 ~ /^ *mono *$/ { gsub(/[ ,]/, "", $3); print $3 }' "$here/../../cross/SIZES.md")
[ -n "$mono" ] || fail "SIZES.md has no Pico SDK mono row"
mono_more=$((mono + 1))
mono_c=$(printf '%s' "$mono" | sed ':a;s/\([0-9]\)\([0-9]\{3\}\)\($\|,\)/\1,\2\3/;ta')
mono_more_c=$(printf '%s' "$mono_more" | sed ':a;s/\([0-9]\)\([0-9]\{3\}\)\($\|,\)/\1,\2\3/;ta')
sed "s/| mono | $mono_c |/| mono | $mono_more_c |/" "$here/../../cross/SIZES.md" >"$tmp/SIZES.md"
cmp -s "$tmp/SIZES.md" "$here/../../cross/SIZES.md" && fail "the doctoring changed nothing (SIZES.md has no mono $mono_c row?)"
out="$tmp/sizes out"
msg=$(env -u SVF_REQUIRE_SCREENS SVF_SIZES_MD=$tmp/SIZES.md QEMU_RV=$tmp/notexec QEMU_XT=$tmp/notexec $RS "$out" 2>&1)
rc=$?
[ "$rc" = 3 ] || fail "doctored SIZES.md: exit $rc, not 3 (an overridden SIZES.md never succeeds) ($msg)"
case $msg in *"screens: note: SIZES.md overridden: $tmp/SIZES.md"*) ;; *) fail "doctored SIZES.md: no override note: $msg" ;; esac
case $msg in *"Pico SDK image mono says text/data/bss $mono_more 0 2384, measured $mono 0 2384"*) ;; *) fail "doctored SIZES.md: the difference is not named: $msg" ;; esac
case $msg in *"screen-pico-mono: OK"*) ;; *) fail "doctored SIZES.md: the mono screen did not run: $msg" ;; esac
echo "run-screens-gates: OK"
