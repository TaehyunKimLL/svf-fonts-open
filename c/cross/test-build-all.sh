#!/bin/sh
# Tests of the gates in build-all.sh that need no toolchain: the screens gate and the SIZES.md comparison.
# Usage: sh c/cross/test-build-all.sh   (prints "build-all-gates: OK"; exit 1 on a failure)
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "build-all-gates: FAIL: $1" >&2; exit 1; }
BA="sh $here/build-all.sh --screens-missing"

# the screens gate: the per-archive QEMU trees; the old shared tree does not count
o=$tmp/opt
mkdir -p "$o/pico-sdk-2.3.1" "$o/rp2040js-1.4.0" "$o/qemu-esp-9.2.2-20260417-riscv32/qemu/bin" \
	"$o/qemu-esp-9.2.2-20260417/qemu/bin"
touch "$o/pico-sdk-2.3.1/pico_sdk_init.cmake" "$o/rp2040js-1.4.0/bootrom-b1.bin"
m=$(OPT=$o QEMU_RV= QEMU_XT= $BA)
case $m in *rp2040js*) ;; *) fail "rp2040js (node_modules) absent but not reported missing: '$m'" ;; esac
mkdir -p "$o/rp2040js-1.4.0/node_modules/rp2040js"
touch "$o/rp2040js-1.4.0/node_modules/rp2040js/package.json"
for q in qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32 qemu-esp-9.2.2-20260417/qemu/bin/qemu-system-xtensa; do
	touch "$o/$q"; chmod +x "$o/$q"
done
m=$(OPT=$o QEMU_RV= QEMU_XT= $BA)
case $m in *qemu-system-xtensa*) ;; *) fail "only the old shared xtensa tree is present: expected qemu-system-xtensa missing, got '$m'" ;; esac
case $m in *qemu-system-riscv32*) fail "riscv32 QEMU is present, got '$m'" ;; esac
mkdir -p "$o/qemu-esp-9.2.2-20260417-xtensa/qemu/bin"
touch "$o/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa"
chmod +x "$o/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa"
m=$(OPT=$o QEMU_RV= QEMU_XT= $BA)
case $m in *qemu-system-xtensa*) fail "per-archive xtensa tree present but reported missing: '$m'" ;; esac
# QEMU_XT overrides
m=$(OPT=$o QEMU_XT=$tmp/nonexistent $BA)
case $m in *"$tmp/nonexistent"*) ;; *) fail "QEMU_XT override ignored: '$m'" ;; esac
# the list is run-screens.sh's own (--missing): one list for the gate and the screens run
r=$(OPT=$o QEMU_XT=$tmp/nonexistent sh "$here/../ports/check/run-screens.sh" --missing)
[ "$m" = "$r" ] || fail "build-all.sh and run-screens.sh --missing disagree: '$m' against '$r'"

# SIZES.md comparison
printf 'pico colour 10 100 0 5 RGB565 0x08\nesp32c3 mono 7 70 1 2 MONO_PAGE 0x02\nch582 mono 8 80 1 2 MONO_PAGE 0x02\n' >"$tmp/rows"
cat >"$tmp/ok.md" <<'MD'
## Port examples

| port | profile | kind | faces | text | data | bss | w/o |
|---|---|---|---:|---:|---:|---:|---:|
| pico | colour | RGB565 0x08 | 10 | 1,00 | 0 | 5 | 90 |
| esp32c3 | mono | MONO_PAGE 0x02 | 7 | 70 | 1 | 2 | 63 |
| ch582 | mono | MONO_PAGE 0x02 | 8 | 80 | 1 | 2 | 72 |

## Findings
MD
sed -i 's/1,00 /100 /' "$tmp/ok.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/ok.md" || fail "matching table rejected"
sed '/^| esp32c3 /s/| 70 | 1 |/| 71 | 1 |/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed text accepted"
sed 's/RGB565 0x08/RGB565 0x10/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed SVF_TARGETS accepted"
sed '/^| esp32c3 /s/MONO_PAGE 0x02/GRAY8 0x02/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed kind accepted"
sed 's/| 90 |/| 91 |/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed text-without-faces accepted"
sed '/^| esp32c3 /s/| 63 |/| 64 |/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed text-without-faces (second row) accepted"
sed '/^| ch582 /s/| 72 |/| 73 |/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed ch582 text-without-faces accepted"
sed '/^| ch582 /s/| 8 | 80 |/| 7 | 80 |/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed ch582 face count accepted"
sed '/^| ch582 /s/| 80 | 1 |/| 81 | 1 |/' "$tmp/ok.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "changed ch582 text accepted"
grep -v '^| ch582' "$tmp/ok.md" >"$tmp/short.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/short.md" >/dev/null && fail "missing ch582 row accepted"
grep -v esp32c3 "$tmp/ok.md" >"$tmp/short.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/short.md" >/dev/null && fail "missing row accepted"
# the program sizes of dos and web: the "(dos: ...; web: ...)" line under the table
printf 'program dos 250708\nprogram web 23525\n' >>"$tmp/rows"
sed 's/^## Findings/(dos: `SVFDEMO.EXE` 250,708 bytes; web: `svf.wasm` 23,525 bytes.)\n\n## Findings/' "$tmp/ok.md" >"$tmp/prog.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/prog.md" || fail "matching program sizes rejected"
sed 's/23,525 bytes/22,407 bytes/' "$tmp/prog.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "stale web size accepted"
sed 's/; web: `svf.wasm` 23,525 bytes//' "$tmp/prog.md" >"$tmp/bad.md"
sh "$here/check-sizes-md.sh" "$tmp/rows" "$tmp/bad.md" >/dev/null && fail "missing web size accepted"
# informational rows (SDL: `info program sdl2 N`) are skipped, they are not gated; a non-info unknown row still fails
cp "$tmp/rows" "$tmp/rows.info"
printf 'info program sdl2 123\ninfo program sdl3 456\n' >>"$tmp/rows.info"
sh "$here/check-sizes-md.sh" "$tmp/rows.info" "$tmp/prog.md" || fail "info rows rejected"
cp "$tmp/rows" "$tmp/rows.unk"
printf 'program sdl2 123\n' >>"$tmp/rows.unk"
sh "$here/check-sizes-md.sh" "$tmp/rows.unk" "$tmp/prog.md" >/dev/null && fail "non-info unknown program row accepted"
cp "$tmp/rows" "$tmp/rows.unk"
printf 'sdl2 - 0 1 2 3 MONO_PAGE 0x02\n' >>"$tmp/rows.unk"
sh "$here/check-sizes-md.sh" "$tmp/rows.unk" "$tmp/prog.md" >/dev/null && fail "non-info unknown port row accepted"
# --port with an unknown name lists sdl
nm=$(sh "$here/build-all.sh" --port nosuch "$tmp/nosuch" 2>&1)
case $nm in *" sdl"*) ;; *) fail "--port nosuch does not list sdl: $nm" ;; esac
# port sdl with a fake check.sh (SVF_SDL_CHECK): the sizes come from OUT/ports/sdl, never from its asan subdirectory;
# exactly one line matches ': OK'; the rows file gets the info rows; the note lines are passed on
cat >"$tmp/fakecheck.sh" <<'EOF'
#!/bin/sh
mkdir -p "$1/asan"
head -c 1000 /dev/zero >"$1/svfsdl2"
head -c 2000 /dev/zero >"$1/svfsdl3"
chmod +x "$1/svfsdl2" "$1/svfsdl3"
head -c 9000 /dev/zero >"$1/asan/svfsdl2"
echo "port-sdl-check: note: fake note"
echo "port-sdl-check: OK sdl2 5 runs, sdl3 4 runs, sum=1"
EOF
SVF_SDL_ROWS=$tmp/sdlrows SVF_SDL_CHECK=$tmp/fakecheck.sh sh "$here/build-all.sh" --port sdl "$tmp/sdlout" >"$tmp/sdl.out" 2>&1 ||
	fail "port sdl with the fake check.sh failed: $(cat "$tmp/sdl.out")"
[ "$(grep -c ': OK' "$tmp/sdl.out")" = 1 ] || fail "port sdl prints not exactly one ': OK' line: $(cat "$tmp/sdl.out")"
grep -qx 'port-sdl: OK (test hook) svfsdl2 1000 bytes, svfsdl3 2000 bytes' "$tmp/sdl.out" || fail "port sdl sizes (asan read?): $(cat "$tmp/sdl.out")"
grep -qx 'port-sdl-check-runs: sdl2 5 runs, sdl3 4 runs, sum=1' "$tmp/sdl.out" || fail "port sdl lacks the runs line"
grep -q 'TEST HOOK: SVF_SDL_CHECK in use' "$tmp/sdl.out" || fail "port sdl hook note missing"
grep -q 'fake note' "$tmp/sdl.out" || fail "port sdl dropped the check.sh note"
[ "$(cat "$tmp/sdlrows")" = "info program sdl2 1000
info program sdl3 2000" ] || fail "port sdl rows: $(cat "$tmp/sdlrows")"
# a missing binary: FAIL, nonzero, no OK line and no size
printf '#!/bin/sh\nmkdir -p "$1/asan"; head -c 5 /dev/zero >"$1/asan/svfsdl2"; head -c 7 /dev/zero >"$1/svfsdl2"; chmod +x "$1/svfsdl2"\n' >"$tmp/fakecheck2.sh"
SVF_SDL_ROWS=$tmp/sdlrows2 SVF_SDL_CHECK=$tmp/fakecheck2.sh sh "$here/build-all.sh" --port sdl "$tmp/sdlout2" >"$tmp/sdl2.out" 2>&1 &&
	fail "port sdl without svfsdl3 succeeded"
grep -q 'port-sdl: FAIL' "$tmp/sdl2.out" || fail "port sdl without svfsdl3: no FAIL message"
grep -q ': OK' "$tmp/sdl2.out" && fail "port sdl without svfsdl3 printed an OK line"
[ ! -s "$tmp/sdlrows2" ] || fail "port sdl without svfsdl3 wrote rows"
# a non-executable or empty binary is a failure too
printf '#!/bin/sh\n: >"$1/svfsdl2"; chmod +x "$1/svfsdl2"; head -c 9 /dev/zero >"$1/svfsdl3"\n' >"$tmp/fakecheck3.sh"
SVF_SDL_ROWS=$tmp/sdlrows3 SVF_SDL_CHECK=$tmp/fakecheck3.sh sh "$here/build-all.sh" --port sdl "$tmp/sdlout3" >"$tmp/sdl3.out" 2>&1 &&
	fail "port sdl with an empty / non-executable binary succeeded"
# an overflow row needs "overflowed by N bytes" and no other error in the same link log
cat >"$tmp/ov.log" <<'LOG'
/x/ld: region `text' overflowed by 222 bytes
collect2: error: ld returned 1 exit status
LOG
[ "$(sh "$here/build-all.sh" --overflow-of "$tmp/ov.log")" = 222 ] || fail "a plain overflow log was not read as 222"
cat >"$tmp/ov2.log" <<'LOG'
probe.o: in function `main': undefined reference to `svf_nothing'
/x/ld: region `text' overflowed by 222 bytes
collect2: error: ld returned 1 exit status
LOG
[ -z "$(sh "$here/build-all.sh" --overflow-of "$tmp/ov2.log")" ] || fail "an overflow hid an undefined reference"
printf '%s\n' "/x/ld: region \`text' overflowed by 9 bytes" "foo.c:1: error: boom" >"$tmp/ov3.log"
[ -z "$(sh "$here/build-all.sh" --overflow-of "$tmp/ov3.log")" ] || fail "an overflow hid a compiler error line"
# the AVR GRAY -Werror line (build-all.sh --gray-werror): a passing compiler prints one line that is not an OK line, a failing
# one (here: a fake that rejects SVF_TARGETS=0x201) prints FAIL and exits 1
g=$(sh "$here/build-all.sh" --gray-werror t cc -DSVF_NO_SCALE) || fail "gray-werror with the host cc failed: $g"
[ "$g" = "t gray-werror: ok 0x01 0x200 0x201 0x3FF" ] || fail "gray-werror line: '$g'"
case $g in *": OK"*) fail "the gray-werror line counts as an OK line" ;; esac
printf '#!/bin/sh\ncase "$*" in *0x201*) echo "svf_draw.c:1: error: fake" >&2; exit 1 ;; esac\n' >"$tmp/badcc"
chmod +x "$tmp/badcc"
g=$(sh "$here/build-all.sh" --gray-werror t "$tmp/badcc"); [ $? = 1 ] || fail "gray-werror accepted a failing compiler"
case $g in "t: FAIL gray-werror SVF_TARGETS=0x201"*) ;; *) fail "gray-werror FAIL line: '$g'" ;; esac
# the hooks and the self-re-run marker never reach a full run
h=$(SVF_SDL_CHECK=/x SVF_SDL_ROWS=/y SVF_BA_INNER=1 sh "$here/build-all.sh" --print-hooks --ports "$tmp/o")
[ "$h" = "SVF_SDL_CHECK=unset SVF_SDL_ROWS=unset counted=yes" ] || fail "a full run takes a test hook: $h"
h=$(SVF_SDL_CHECK=/x SVF_SDL_ROWS=/y sh "$here/build-all.sh" --print-hooks --port sdl "$tmp/o")
[ "$h" = "SVF_SDL_CHECK=/x SVF_SDL_ROWS=/y counted=no" ] || fail "--port sdl lost the test hooks: $h"
# the OK count of a full run: EXPECT_OK, less 7 for skipped screens and 1 a skipped unit; ch582-sdk skips remove none
exp=$(sed -n 's/^EXPECT_OK=\([0-9]*\) .*/\1/p' "$here/build-all.sh")
grep -q "^# A full run prints $exp OK lines" "$here/build-all.sh" || fail "the header does not say $exp OK lines"
grep -q "prints $exp \`OK\` lines" "$here/../ports/pico/README.md" || fail "pico README does not say $exp OK lines"
i=0; : >"$tmp/full.out"; while [ $i -lt "$exp" ]; do echo "x$i: OK" >>"$tmp/full.out"; i=$((i + 1)); done
sh "$here/build-all.sh" --count-check "$tmp/full.out" 0 || fail "a full count was rejected"
sh "$here/build-all.sh" --count-check "$tmp/full.out" 3 >/dev/null; [ $? = 3 ] || fail "the rc of a failed run was not kept"
echo "ch582-sdk: SKIPPED (not installed: x)" >>"$tmp/full.out"
sh "$here/build-all.sh" --count-check "$tmp/full.out" 0 || fail "a ch582-sdk skip changed the expected count"
sed '$d' "$tmp/full.out" | sed '$d' >"$tmp/short.out"
sh "$here/build-all.sh" --count-check "$tmp/short.out" 0 >/dev/null && fail "a short count was accepted"
sed -n "8,\$p" "$tmp/full.out" >"$tmp/scr.out"
echo "screens: SKIPPED (missing: x)" >>"$tmp/scr.out"
sh "$here/build-all.sh" --count-check "$tmp/scr.out" 0 || fail "36 OK lines with screens skipped were rejected"
sed '1d' "$tmp/scr.out" >"$tmp/scr2.out"
sh "$here/build-all.sh" --count-check "$tmp/scr2.out" 0 >/dev/null && fail "a short count with screens skipped was accepted"
# an exported SVF_SIZES_MD (the SIZES.md override of run-screens.sh) never reaches the screens run of build-all
m=$(SVF_SIZES_MD=/nonexistent/SIZES.md sh "$here/build-all.sh" --print-sizes-md)
[ "$m" = "SVF_SIZES_MD=unset" ] || fail "build-all.sh passes an exported SVF_SIZES_MD on: '$m'"

# the Pico SDK images table (run-screens.sh)
printf 'colour 158204 0 12804\nmono 31876 0 2380\n' >"$tmp/prows"
cat >"$tmp/pok.md" <<'MD'
## Pico SDK images

| profile | text | data | bss |
|---|---:|---:|---:|
| colour | 158,204 | 0 | 12,804 |
| mono | 31,876 | 0 | 2,380 |

## Findings
MD
sh "$here/check-sizes-md.sh" --pico-sdk "$tmp/prows" "$tmp/pok.md" || fail "matching Pico SDK table rejected"
sed 's/12,804/12,805/' "$tmp/pok.md" >"$tmp/pbad.md"
sh "$here/check-sizes-md.sh" --pico-sdk "$tmp/prows" "$tmp/pbad.md" >/dev/null && fail "changed Pico SDK bss accepted"
sed 's/| 31,876 |/| 31,877 |/' "$tmp/pok.md" >"$tmp/pbad.md"
sh "$here/check-sizes-md.sh" --pico-sdk "$tmp/prows" "$tmp/pbad.md" >/dev/null && fail "changed Pico SDK text accepted"
grep -v mono "$tmp/pok.md" >"$tmp/pbad.md"
sh "$here/check-sizes-md.sh" --pico-sdk "$tmp/prows" "$tmp/pbad.md" >/dev/null && fail "missing Pico SDK row accepted"

# the CH582 SDK image table
printf 'svf_ch582_mono 20960 20 1228 2576 1062 2048 5872\n' >"$tmp/crows"
cat >"$tmp/cok.md" <<'MD'
## CH582 SDK image

| image | text | data | bss | .highcode | libISP583 kept | stack | RAM used |
|---|---:|---:|---:|---:|---:|---:|---:|
| svf_ch582_mono | 20,960 | 20 | 1,228 | 2,576 | 1,062 | 2,048 | 5,872 |

## Findings
MD
sh "$here/check-sizes-md.sh" --ch582-sdk "$tmp/crows" "$tmp/cok.md" || fail "matching CH582 SDK table rejected"
sed 's/| 1,062 |/| 1,063 |/' "$tmp/cok.md" >"$tmp/cbad.md"
sh "$here/check-sizes-md.sh" --ch582-sdk "$tmp/crows" "$tmp/cbad.md" >/dev/null && fail "changed libISP583 kept accepted"
sed 's/| 5,872 |/| 5,873 |/' "$tmp/cok.md" >"$tmp/cbad.md"
sh "$here/check-sizes-md.sh" --ch582-sdk "$tmp/crows" "$tmp/cbad.md" >/dev/null && fail "changed RAM used accepted"
sed 's/| 20,960 |/| 20,961 |/' "$tmp/cok.md" >"$tmp/cbad.md"
sh "$here/check-sizes-md.sh" --ch582-sdk "$tmp/crows" "$tmp/cbad.md" >/dev/null && fail "changed CH582 text accepted"
grep -v svf_ch582_mono "$tmp/cok.md" >"$tmp/cbad.md"
sh "$here/check-sizes-md.sh" --ch582-sdk "$tmp/crows" "$tmp/cbad.md" >/dev/null && fail "missing CH582 SDK row accepted"

# the CH582 SDK gate of --port ch582 (needs the esp toolchain and the installed EVT tree, else skipped): an absent tree is
# SKIPPED, a damaged or explicitly named but missing one is a FAIL and never a SKIPPED. Everything lives under $tmp: a
# copy of the cross directory whose install-toolchains.sh passes the esp verification (the toolchain is only symlinked
# into the fake OPT) and runs the real installer for ch583
REAL=${OPT:-$HOME/opt}
esp=riscv32-esp-elf-esp-16.1.0_20260609
if [ -f "$REAL/ch583-evt/EVT/EXAM/SRC/Ld/Link.ld" ] &&
	OPT=$REAL sh "$here/install-toolchains.sh" --verify esp ch583 >/dev/null 2>&1; then
	fx=$tmp/fx
	mkdir -p "$fx/cross"
	for e in "$here"/*; do
		case ${e##*/} in install-toolchains.sh | build-all.sh) ;; *) ln -s "$e" "$fx/cross/" ;; esac
	done
	cp "$here/build-all.sh" "$fx/cross/"
	for e in "$here"/../*/; do e=${e%/}; [ "${e##*/}" = cross ] || ln -s "$(cd "$e" && pwd -P)" "$fx/"; done
	ln -s "$(cd "$here/../../svf" && pwd -P)" "$tmp/svf"
	cat >"$fx/cross/install-toolchains.sh" <<EOF
#!/bin/sh
# test stand-in: only esp is verified away; ch583 goes to the real installer
case "\$*" in "--verify esp") exit 0 ;; "--verify ch583") exec sh "$here/install-toolchains.sh" --verify ch583 ;; esac
echo "stand-in installer: unexpected arguments: \$*" >&2
exit 2
EOF
	sdkgate() { # NAME OPTDIR [CH583_SDK]: runs --port ch582 into $tmp/sg-NAME; output in $tmp/sg-NAME.out
		if [ -n "${3:-}" ]; then
			OPT=$2 CH583_SDK=$3 sh "$fx/cross/build-all.sh" --port ch582 "$tmp/sg-$1" >"$tmp/sg-$1.out" 2>&1
		else
			env -u CH583_SDK OPT=$2 sh "$fx/cross/build-all.sh" --port ch582 "$tmp/sg-$1" >"$tmp/sg-$1.out" 2>&1
		fi
	}
	for d in absent link src; do
		mkdir "$tmp/o-$d" && ln -s "$REAL/$esp" "$tmp/o-$d/$esp"
	done
	cp -a "$REAL/ch583-evt" "$tmp/o-link/"
	cp -a "$REAL/ch583-evt" "$tmp/o-src/"
	sdkgate absent "$tmp/o-absent" || fail "absent EVT tree failed the run: $(cat "$tmp/sg-absent.out")"
	grep -q '^ch582-sdk: SKIPPED' "$tmp/sg-absent.out" || fail "absent EVT tree not SKIPPED: $(cat "$tmp/sg-absent.out")"
	rm "$tmp/o-link/ch583-evt/EVT/EXAM/SRC/Ld/Link.ld"
	rm -rf "$tmp/o-src/ch583-evt/EVT/EXAM/SRC"
	for d in link src; do
		sdkgate $d "$tmp/o-$d" && fail "damaged EVT tree ($d) passed"
		grep -q 'SKIPPED' "$tmp/sg-$d.out" && fail "damaged EVT tree ($d) reported SKIPPED: $(cat "$tmp/sg-$d.out")"
		grep -Eq '^ch583: .*(EVT/EXAM/SRC is missing|differs from its manifest|local changes)' "$tmp/sg-$d.out" ||
			fail "damaged EVT tree ($d) not reported by the ch583 verification: $(cat "$tmp/sg-$d.out")"
	done
	# CH583_SDK named but without Link.ld
	mkdir "$tmp/emptysdk"
	sdkgate explicit "$tmp/o-absent" "$tmp/emptysdk" && fail "explicit CH583_SDK without Link.ld passed"
	grep -q '^ch582-sdk: FAIL' "$tmp/sg-explicit.out" || fail "explicit CH583_SDK without Link.ld not a FAIL: $(cat "$tmp/sg-explicit.out")"
	grep -q 'SKIPPED' "$tmp/sg-explicit.out" && fail "explicit CH583_SDK without Link.ld reported SKIPPED"
	# a good tree: the stack gate prints its line
	sdkgate good "$REAL" || fail "good SDK run failed: $(cat "$tmp/sg-good.out")"
	grep -q '^ch582-sdk-stack: peak [1-9]' "$tmp/sg-good.out" || fail "no ch582-sdk-stack line: $(cat "$tmp/sg-good.out")"
	# the stack gate must not pass on a call-graph directory without main (stack-usage.py then has nothing to measure):
	# a stand-in make that, after the real STACK_INFO=1 build, renames the .ci files away (NOCI=rename) or deletes them
	mkdir "$tmp/fakebin"
	cat >"$tmp/fakebin/make" <<'FAKE'
#!/bin/sh
"$REALMAKE" "$@" || exit $?
case " $* " in *" STACK_INFO=1 "*)
	for a in "$@"; do case $a in BUILD=*) b=${a#BUILD=} ;; esac; done
	case $NOCI in
	rename) for f in "$b"/obj/*.ci; do mv "$f" "$f.gone"; done ;;
	empty) rm -f "$b"/obj/*.ci ;;
	esac ;;
esac
FAKE
	chmod +x "$tmp/fakebin/make"
	for k in rename empty; do
		if REALMAKE=$(command -v make) PATH=$tmp/fakebin:$PATH NOCI=$k OPT=$REAL sh "$fx/cross/build-all.sh" --port ch582 \
			"$tmp/sg-noci-$k" >"$tmp/sg-noci-$k.out" 2>&1; then
			fail "stack gate passed with the call-graph files gone ($k): $(cat "$tmp/sg-noci-$k.out")"
		fi
		grep -q '^ch582-sdk: FAIL .*stack' "$tmp/sg-noci-$k.out" || fail "stack gate ($k) not a stack FAIL: $(cat "$tmp/sg-noci-$k.out")"
		grep -q 'ch582-sdk-stack: peak' "$tmp/sg-noci-$k.out" && fail "stack gate ($k) printed a peak"
	done
	# the Makefile of the port, on a scratch BUILD: `flash` rebuilds a stale image first (a recompile of main.c comes
	# before the wchisp line), and a changed flag string (also one holding a quote) recompiles the objects (real builds:
	# a dry run lists everything, the stamp being a forced target)
	mk="make -C $here/../ports/ch582 BUILD=$tmp/mkb OPT=$REAL CH583_SDK=$REAL/ch583-evt"
	$mk >"$tmp/mk.out" 2>&1 || fail "ch582 Makefile build: $(tail -5 "$tmp/mk.out")"
	$mk >"$tmp/mk.out" 2>&1; grep -q ' -c main\.c' "$tmp/mk.out" && fail "ch582 Makefile rebuilds an up-to-date tree"
	# age the scratch object, never the checkout's source: a new stamp on main.c would make the next real build in this
	# tree recompile (the checkout's mtime is asserted unchanged below)
	mt=$(stat -c %Y "$here/../ports/ch582/main.c")
	touch -d 2000-01-01 "$tmp/mkb/obj/main.o"
	$mk WCHISP=true flash >"$tmp/mk.out" 2>&1 || fail "ch582 make flash: $(tail -5 "$tmp/mk.out")"
	cl=$(grep -n ' -c main\.c' "$tmp/mk.out" | head -n 1 | cut -d: -f1)
	wl=$(grep -n '^true flash' "$tmp/mk.out" | head -n 1 | cut -d: -f1)
	pl=$(grep -n 'image_sizes\.py' "$tmp/mk.out" | tail -n 1 | cut -d: -f1)
	{ [ -n "$pl" ] && [ -n "$wl" ] && [ "$pl" -lt "$wl" ] && [ "$cl" -lt "$pl" ]; } || fail "make flash does not run compile, then image_sizes.py, then wchisp: $(cat "$tmp/mk.out")"
	[ "$(stat -c %Y "$here/../ports/ch582/main.c")" = "$mt" ] || fail "the ch582 Makefile checks changed main.c's mtime"
	$mk EXTRA_CFLAGS=-DSH1106_COL_OFFSET=0 >"$tmp/mk.out" 2>&1 || fail "ch582 build with EXTRA_CFLAGS: $(tail -5 "$tmp/mk.out")"
	grep -q ' -c disp_sh1106\.c' "$tmp/mk.out" || fail "EXTRA_CFLAGS change does not recompile disp_sh1106.o"
	$mk EXTRA_CFLAGS="-DSVF_TEST_Q='1'" >"$tmp/mk.out" 2>&1 || fail "EXTRA_CFLAGS holding a quote breaks the build: $(tail -5 "$tmp/mk.out")"
	$mk EXTRA_CFLAGS="-DSVF_TEST_Q='1'" >"$tmp/mk.out" 2>&1
	grep -q ' -c main\.c' "$tmp/mk.out" && fail "unchanged quoted EXTRA_CFLAGS rebuilds"
else
	echo "build-all-gates: ch582 SDK gate skipped (no esp toolchain or EVT tree under $REAL)"
fi

# the "Size switches" tables (build-all.sh rows.md and rows-switches.md)
cat >"$tmp/srows" <<'MD'
| cortex-m0plus | 15.2.1 | P1 | 100 | 0 | 8 |
| avr-atmega328p | 16.1.0 | P1 | 200 | 0 | 9 |
| avr-atmega328p | 16.1.0 | P4 | 300 | 0 | 9 |
MD
cat >"$tmp/svrows" <<'MD'
| cortex-m0plus | 15.2.1 | P1 [SVF_SMALL] | 90 | 0 | 8 |
| avr-atmega328p | 16.1.0 | P1 [SVF_SMALL] | 200 | 0 | 9 |
| avr-atmega328p | 16.1.0 | P4 [SVF_SMALL] | 250 | 0 | 9 |
MD
cat >"$tmp/sok.md" <<'MD'
## Size switches

| Cortex-M0+ (15.2.1) | default | `SVF_SMALL` |
|---|---:|---:|
| P1 | 100 | 90 |

| AVR (16.1.0) | default | `SVF_SMALL` | `SVF_MERGE_WORDS=0` |
|---|---:|---:|---:|
| P1 text | 200 | 200 | 200 (default) |
| P4 text | 300 | 250 | 300 (default) |
| P4 data + bss | 9 | 9 | 9 |

## Findings
MD
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sok.md" || fail "matching Size switches rejected"
sed 's/| 100 | 90 |/| 100 | 89 |/' "$tmp/sok.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "changed M0+ switch cell accepted"
sed 's/| 300 | 250 |/| 300 | 251 |/' "$tmp/sok.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "changed AVR switch cell accepted"
sed 's/| P4 data + bss | 9 |/| P4 data + bss | 10 |/' "$tmp/sok.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "changed AVR data + bss accepted"
# a variant whose link overflowed (build-all.sh: "overflow N"): the cell "overflow N", data + bss "-"
cat >>"$tmp/svrows" <<'MD'
| avr-atmega328p | 16.1.0 | P1 [JSET_BOTH] | 400 | 0 | 9 |
| avr-atmega328p | 16.1.0 | P4 [JSET_BOTH] | overflow 2574 | - | - |
MD
sed 's/^| AVR (16.1.0) | default | `SVF_SMALL` | `SVF_MERGE_WORDS=0` |$/& `JSET_BOTH` |/; s/^|---|---:|---:|---:|$/&---:|/
	s/^| P1 text | 200 | 200 | 200 (default) |$/& 400 |/; s/^| P4 text | 300 | 250 | 300 (default) |$/& overflow 2,574 |/
	s/^| P4 data + bss | 9 | 9 | 9 |$/& - |/' "$tmp/sok.md" >"$tmp/sover.md"
grep -q 'overflow 2,574' "$tmp/sover.md" || fail "test table not built"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sover.md" || fail "matching overflow cells rejected"
sed 's/overflow 2,574/overflow 2,575/' "$tmp/sover.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "changed overflow bytes accepted"
sed 's/overflow 2,574/32,700/' "$tmp/sover.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "a size where the link overflowed accepted"
sed 's/| 9 | 9 | 9 | - |/| 9 | 9 | 9 | 9 |/' "$tmp/sover.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "data + bss of an overflowed link accepted"
sed 's/| 200 (default) | 400 |/| 200 (default) | overflow 1 |/' "$tmp/sover.md" >"$tmp/sbad.md"
sh "$here/check-sizes-md.sh" --switches "$tmp/srows" "$tmp/svrows" "$tmp/sbad.md" >/dev/null && fail "overflow where the build linked accepted"
echo "build-all-gates: OK"
