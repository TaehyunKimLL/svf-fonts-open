#!/bin/sh
# Tests of the gates in check-features.sh that need no toolchain (fake rows and nm output through the env hooks
# FEATURES_ROWS_HOOK and FEATURES_NM_HOOK; FEATURES_SIZES_MD names the table).
# Usage: sh c/cross/test-check-features.sh   (prints "check-features-gates: OK"; exit 1 on a failure)
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "check-features-gates: FAIL: $1" >&2; exit 1; }
CF="sh $here/check-features.sh"

cat >"$tmp/md" <<'MD'
## Minimal config

| toolchain | config | text | rodata | data | bss |
|---|---|---:|---:|---:|---:|
| avr | minimal | 12,920 | 100 | 18 | 5 |
| m0plus | minimal | 6,146 | 90 | 0 | 5 |
| m0plus | default | 7,441 | 95 | 0 | 5 |
| m0plus | allon | 9,000 | 99 | 0 | 5 |

## Findings
MD
cat >"$tmp/rows" <<'ROWS'
avr minimal 12920 100 18 5
m0plus minimal 6146 90 0 5
m0plus default 7441 95 0 5
m0plus allon 9000 99 0 5
ROWS
: >"$tmp/nm"
export FEATURES_SIZES_MD=$tmp/md FEATURES_NM_HOOK=$tmp/nm

run() { # ROWSFILE [ARGS]: runs the gate on it; output in $tmp/out, status in $?
	r=$1; shift
	FEATURES_ROWS_HOOK=$r $CF "$tmp/o" "$@" >"$tmp/out" 2>&1
}

run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "matching rows rejected (rc $rc): $(cat "$tmp/out")"
grep -qx 'features: OK' "$tmp/out" || fail "no 'features: OK' line: $(cat "$tmp/out")"
[ -s "$tmp/o/features/rows.txt" ] || fail "no OUT/features/rows.txt"
cmp -s "$tmp/rows" "$tmp/o/features/rows.txt" || fail "rows.txt differs from the rows"

sed 's/^avr minimal 12920/avr minimal 12921/' "$tmp/rows" >"$tmp/bad"
run "$tmp/bad"; rc=$?
[ $rc -eq 1 ] || fail "avr minimal text 12921 gave exit $rc"
grep -q 'avr minimal 12920 -> 12921 (+1)' "$tmp/out" || fail "growth not named: $(cat "$tmp/out")"
grep -q 'features: OK' "$tmp/out" && fail "features: OK printed on a size mismatch"

sed 's/^m0plus minimal 6146/m0plus minimal 6145/' "$tmp/rows" >"$tmp/bad"
run "$tmp/bad"; rc=$?
[ $rc -eq 1 ] || fail "m0plus minimal text 6145 (shrink) gave exit $rc"
grep -q 'm0plus minimal 6146 -> 6145 (-1)' "$tmp/out" || fail "shrink not named: $(cat "$tmp/out")"

sed 's/^m0plus default 7441 95 0 5/m0plus default 7441 95 0 6/' "$tmp/rows" >"$tmp/bad"
run "$tmp/bad"; rc=$?
[ $rc -eq 1 ] || fail "m0plus default bss 6 gave exit $rc"

grep -v '^m0plus default' "$tmp/rows" >"$tmp/bad"
run "$tmp/bad"; rc=$?
[ $rc -eq 1 ] || fail "a missing gated row gave exit $rc"
grep -q 'm0plus default' "$tmp/out" || fail "missing row not named: $(cat "$tmp/out")"

sed 's/^m0plus allon 9000/m0plus allon 9100/' "$tmp/rows" >"$tmp/bad"
run "$tmp/bad"; rc=$?
[ $rc -eq 0 ] || fail "allon growth gave exit $rc: $(cat "$tmp/out")"
grep -q '^info.*m0plus allon' "$tmp/out" || fail "no info line for allon: $(cat "$tmp/out")"

# the symbol rule: nm lines "TOOLCHAIN CONFIG SYMBOL"
echo 'm0plus minimal pop4' >"$tmp/nm"
run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "pop4 in minimal gave exit $rc"
grep -q 'pop4' "$tmp/out" || fail "symbol not named: $(cat "$tmp/out")"
echo 'm0plus minimal svf_open_stream_x' >"$tmp/nm"
run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "svf_open_stream* in minimal gave exit $rc"
echo 'avr minimal svf__scale_cell' >"$tmp/nm"
run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "svf__scale* in minimal gave exit $rc"
echo 'm0plus default pop4' >"$tmp/nm"
run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "pop4 in default (POP4 on) rejected, exit $rc: $(cat "$tmp/out")"
echo 'm0plus allon svf_open_stream' >"$tmp/nm"
run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "svf_open_stream in allon rejected, exit $rc"

# the strings rule
: >"$tmp/nm"
echo 'm0plus default xx a jmap here' >"$tmp/str"
FEATURES_STRINGS_HOOK=$tmp/str run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "jmap in the image gave exit $rc"
grep -q 'm0plus default' "$tmp/out" || fail "string hit not named: $(cat "$tmp/out")"
echo 'avr minimal xx BIG here' >"$tmp/str"
FEATURES_STRINGS_HOOK=$tmp/str run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "BIG in an avr image (not scanned there) rejected, exit $rc"
echo 'm0plus minimal xx BIG here' >"$tmp/str"
FEATURES_STRINGS_HOOK=$tmp/str run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "BIG in an m0plus image gave exit $rc"
echo 'm0plus minimal clean bytes' >"$tmp/str"
FEATURES_STRINGS_HOOK=$tmp/str run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "a clean image rejected, exit $rc"

# the defaults rule: FEATURES_DEFINES_HOOK lines "TOOLCHAIN CONFIG JMAP RECOG LIST"
cat >"$tmp/defs" <<'D'
avr minimal 0 0 0
m0plus minimal 0 0 0
m0plus default 0 0 0
m0plus minimal+RECOG 0 1 0
m0plus minimal+JMAP 1 0 1
m0plus minimal+JMAP+nolist 1 0 0
m0plus ksonly+nolist 1 0 0
D
FEATURES_DEFINES_HOOK=$tmp/defs run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "correct defaults rejected, exit $rc: $(cat "$tmp/out")"
sed 's/^m0plus default 0 0 0/m0plus default 1 0 0/' "$tmp/defs" >"$tmp/defs2"
FEATURES_DEFINES_HOOK=$tmp/defs2 run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "SVF_JMAP 1 on the m0plus default gave exit $rc"
grep -q 'm0plus default: svf.h defines SVF_JMAP 1' "$tmp/out" || fail "defaults hit not named: $(cat "$tmp/out")"
sed 's/^avr minimal 0 0 0/avr minimal 0 1 0/' "$tmp/defs" >"$tmp/defs2"
FEATURES_DEFINES_HOOK=$tmp/defs2 run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "SVF_JMAP_RECOG 1 on avr minimal gave exit $rc"
sed 's/^avr minimal 0 0 0/avr minimal 0 0 1/' "$tmp/defs" >"$tmp/defs2"
FEATURES_DEFINES_HOOK=$tmp/defs2 run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "SVF_JMAP_LIST 1 on avr minimal gave exit $rc"
grep -q 'SVF_JMAP_LIST 1' "$tmp/out" || fail "LIST value not named: $(cat "$tmp/out")"
sed 's/^m0plus minimal+JMAP 1 0 1/m0plus minimal+JMAP 1 0 0/' "$tmp/defs" >"$tmp/defs2"
FEATURES_DEFINES_HOOK=$tmp/defs2 run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "SVF_JMAP_LIST 0 on minimal+JMAP gave exit $rc"
sed 's/^m0plus ksonly+nolist 1 0 0/m0plus ksonly+nolist 1 0 1/' "$tmp/defs" >"$tmp/defs2"
FEATURES_DEFINES_HOOK=$tmp/defs2 run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "SVF_JMAP_LIST 1 on ksonly+nolist gave exit $rc"

# the budget rule (PL-6): the gated rows right, the LIST rows at and over their budgets
cat >"$tmp/brows" <<'R'
avr minimal 12920 100 18 5
m0plus minimal 6146 90 0 5
m0plus default 7441 95 0 5
m0plus allon 9000 99 0 5
avr minimal+JMAP 15532 100 18 5
m0plus minimal+JMAP 7688 100 0 5
avr minimal+JMAP+nolist 15032 100 18 5
m0plus minimal+JMAP+nolist 7398 100 0 5
avr ksonly 13648 100 18 5
m0plus ksonly 6900 100 0 5
avr ksonly+nolist 13148 100 18 5
m0plus ksonly+nolist 6610 100 0 5
avr minimal+RECOG 13250 100 18 5
m0plus minimal+RECOG 6366 100 0 5
R
run "$tmp/brows"; rc=$?
[ $rc -eq 0 ] || fail "rows at their budgets rejected, exit $rc: $(cat "$tmp/out")"
for row in "avr minimal+JMAP 15532 15533 15532" "m0plus minimal+JMAP 7688 7689 7688" "avr minimal+JMAP+nolist 15032 15033 15032" \
	"m0plus minimal+JMAP+nolist 7398 7399 7398" "avr ksonly 13648 13649 13648" "m0plus ksonly 6900 6901 6900" \
	"avr ksonly+nolist 13148 13149 13148" "m0plus ksonly+nolist 6610 6611 6610" "avr minimal+RECOG 13250 13251 13250" \
	"m0plus minimal+RECOG 6366 6367 6366"; do
	set -- $row
	sed "s/^$1 $2 $3 /$1 $2 $4 /" "$tmp/brows" >"$tmp/bad"
	run "$tmp/bad"; rc=$?
	[ $rc -eq 1 ] || fail "$1 $2 text $4 gave exit $rc"
	grep -q "features: FAIL: $1 $2 text $4 over budget $5" "$tmp/out" || fail "budget not named for $1 $2: $(cat "$tmp/out")"
done
# a budget row missing from the rows is a failure (a lost row must not pass), but only when the rows hold any of the configs
grep -v '^avr ksonly ' "$tmp/brows" >"$tmp/bad"
run "$tmp/bad"; rc=$?
[ $rc -eq 1 ] || fail "a missing budget row gave exit $rc"
grep -q 'avr ksonly' "$tmp/out" || fail "missing budget row not named: $(cat "$tmp/out")"

# the jlist symbol rule: no jlist_ symbol in the MCU rows and the +nolist rows
for cfg in minimal default minimal+BIG minimal+BIG+V2 minimal+JMAP+nolist ksonly+nolist; do
	echo "avr $cfg jlist_find" >"$tmp/nm"
	run "$tmp/rows"; rc=$?
	[ $rc -eq 1 ] || fail "jlist_find in $cfg gave exit $rc"
	grep -q "avr $cfg: symbol jlist_find is linked" "$tmp/out" || fail "jlist symbol not named for $cfg: $(cat "$tmp/out")"
done
echo 'avr minimal+JMAP jlist_find' >"$tmp/nm"
run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "jlist_find in minimal+JMAP (LIST on) rejected, exit $rc: $(cat "$tmp/out")"
: >"$tmp/nm"

# the allon link verdict: a pure overflow is info, an overflow beside another error is a failure
printf '%s\n' "ld: region 'text' overflowed by 402 bytes" 'collect2: error: ld returned 1 exit status' >"$tmp/log"
FEATURES_LINKLOG_HOOK=$tmp/log run "$tmp/rows"; rc=$?
[ $rc -eq 0 ] || fail "a pure overflow gave exit $rc: $(cat "$tmp/out")"
grep -q '^info: avr allon does not link: region overflowed by 402 bytes' "$tmp/out" || fail "no overflow info line"
printf '%s\n' "ld: p.o: undefined reference to \`svf_x'" "ld: region 'text' overflowed by 402 bytes" 'collect2: error: ld returned 1 exit status' >"$tmp/log"
FEATURES_LINKLOG_HOOK=$tmp/log run "$tmp/rows"; rc=$?
[ $rc -eq 1 ] || fail "overflow plus undefined reference gave exit $rc"
grep -q 'undefined reference' "$tmp/out" || fail "the log is not printed"

# the --uno flash gate: size -A numbers through the hook
echo 'hg 22258 18 1085' >"$tmp/uno"
FEATURES_UNO_HOOK=$tmp/uno run "$tmp/rows" --uno hg:x.SVF:22276; rc=$?
[ $rc -eq 0 ] || fail "flash == MAXFLASH rejected, exit $rc: $(cat "$tmp/out")"
FEATURES_UNO_HOOK=$tmp/uno run "$tmp/rows" --uno hg:x.SVF:22275; rc=$?
[ $rc -eq 1 ] || fail "flash MAXFLASH+1 gave exit $rc"
grep -q 'flash 22276 > 22275 (+1)' "$tmp/out" || fail "measured flash not printed: $(cat "$tmp/out")"

# a bad argument: usage, exit 2
FEATURES_ROWS_HOOK=$tmp/rows $CF "$tmp/o" --uno oops >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] || fail "a malformed --uno gave exit $rc, wanted 2"
FEATURES_ROWS_HOOK=$tmp/rows $CF "$tmp/o" --uno a:b:xx >/dev/null 2>&1; rc=$?
[ $rc -eq 2 ] || fail "a non-numeric MAXFLASH gave exit $rc, wanted 2"
echo "check-features-gates: OK"
