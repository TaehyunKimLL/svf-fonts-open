#!/bin/sh
# Tests of c/cross/install-toolchains.sh and c/bench/install-emulators.sh, installs and adopts, in temporary PREFIXes.
# Nothing under the real OPT is written: its dl/ copies are copied, its node is run, its pico-sdk-2.3.1 clone (or
# $PICO_MIRROR) stands in for the GitHub clone of the pico-sdk. Usage: sh c/cross/test-installers.sh   (prints
# "installers: OK"; about 30 s). A manual check, in no gate: run it after changing either installer or install-lib.sh.
here=$(cd "$(dirname "$0")" && pwd)
REAL=${OPT:-$HOME/opt}
EMU=$here/../bench/install-emulators.sh
TC=$here/install-toolchains.sh
MIRROR=${PICO_MIRROR:-$REAL/pico-sdk-2.3.1} # the pinned clean clone that install-toolchains.sh made
T=$(mktemp -d) || exit 1
cleanup() { find "$T" -type l -delete 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "installers: FAIL: $1" >&2; exit 1; }
for f in dl/rp2040js/bootrom.ts dl/rp2040js/rp2040js-1.4.0.tgz dl/simavr/v1.8.tar.gz dl/qemu-esp/qemu-riscv32-esp.tar.xz \
	dl/xtensa-esp/qemu-xtensa-esp.tar.xz dl/xtensa-esp/xtensa-esp-elf.tar.xz node-v24.13.0-linux-x64/bin/node; do
	[ -e "$REAL/$f" ] || { echo "installers: skipped (no $REAL/$f)"; exit 0; }
done
# newp NAME [DLDIR...]: a fresh PREFIX $T/NAME with copies of the named dl/ subdirectories of the real OPT
newp() {
	p=$T/$1
	shift
	mkdir -p "$p/dl"
	for d in "$@"; do cp -r "$REAL/dl/$d" "$p/dl/$d"; done
}
# no_debris PREFIX: the scripts leave no work directory behind
no_debris() { [ -z "$(ls -A "$1" | grep '^\.svf-work')" ] || fail "work directory left in $1"; }
NODE=$REAL/node-v24.13.0-linux-x64/bin/node
export NODE
pinned=$(sed -n 's/^BOOTROM_BIN_SHA256=//p' "$EMU")

# --- the boot ROM: the parent directory (rp2040js-1.4.0/) does not exist yet
newp b1 rp2040js
sh "$EMU" "$T/b1" bootrom >"$T/out" 2>&1 || fail "bootrom install into an empty prefix: $(cat "$T/out")"
[ "$(stat -c %s "$T/b1/rp2040js-1.4.0/bootrom-b1.bin")" -eq 16384 ] || fail "bootrom-b1.bin is not 16384 bytes"
[ "$(sha256sum <"$T/b1/rp2040js-1.4.0/bootrom-b1.bin" | cut -d' ' -f1)" = "$pinned" ] || fail "bootrom-b1.bin is not the pinned bytes"
OPT=$T/b1 sh "$EMU" --verify bootrom >/dev/null 2>&1 || fail "bootrom verify after install"
OPT=$T/b1 sh "$EMU" --adopt bootrom >"$T/out" 2>&1 || fail "bootrom adopt: $(cat "$T/out")"
grep -q "$pinned" "$T/out" || fail "bootrom adopt does not print the sha256"
no_debris "$T/b1"
# a corrupt cached bootrom.ts: verify fails, adopt fails, a fresh install refuses
echo x >>"$T/b1/dl/rp2040js/bootrom.ts"
OPT=$T/b1 sh "$EMU" --verify bootrom >/dev/null 2>&1 && fail "verify bootrom accepted a corrupt bootrom.ts"
OPT=$T/b1 sh "$EMU" --adopt bootrom >/dev/null 2>&1 && fail "adopt bootrom accepted a corrupt bootrom.ts"
no_debris "$T/b1"
newp b2 rp2040js
echo x >>"$T/b2/dl/rp2040js/bootrom.ts"
sh "$EMU" "$T/b2" bootrom >/dev/null 2>&1 && fail "install accepted a corrupt bootrom.ts"
[ ! -e "$T/b2/rp2040js-1.4.0/bootrom-b1.bin" ] || fail "a .bin was written from a corrupt bootrom.ts"
# a conversion failure (a bootrom.ts with the right sha256 but too few words) exits non-zero and leaves no .bin
mkdir -p "$T/m/bench"
ln -s "$here" "$T/m/cross"
head -c 1000 "$REAL/dl/rp2040js/bootrom.ts" >"$T/short.ts"
sed "s/^BOOTROM_TS_SHA256=.*/BOOTROM_TS_SHA256=$(sha256sum <"$T/short.ts" | cut -d' ' -f1)/" "$EMU" >"$T/m/bench/install-emulators.sh"
mkdir -p "$T/b3/dl/rp2040js"
cp "$T/short.ts" "$T/b3/dl/rp2040js/bootrom.ts"
sh "$T/m/bench/install-emulators.sh" "$T/b3" bootrom >"$T/out" 2>&1 && fail "a failed conversion exited 0: $(cat "$T/out")"
[ ! -e "$T/b3/rp2040js-1.4.0/bootrom-b1.bin" ] && [ ! -e "$T/b3/rp2040js-1.4.0/bootrom-b1.bin.part" ] || fail "a failed conversion left a file"
no_debris "$T/b3"

# --- simavr: a clean install must pass its own verify (the build is not byte-reproducible: a local pin)
newp s1 simavr
sh "$EMU" "$T/s1" simavr >"$T/out" 2>&1 || fail "clean simavr install: $(cat "$T/out")"
OPT=$T/s1 sh "$EMU" --verify simavr >"$T/out" 2>&1 || fail "verify after a clean simavr install: $(cat "$T/out")"
sh "$EMU" "$T/s1" simavr >"$T/out" 2>&1 || fail "second simavr run: $(cat "$T/out")"
# adopt: the same path set may differ in content; a missing file is refused
OPT=$T/s1 sh "$EMU" --adopt simavr >"$T/out" 2>&1 || fail "simavr adopt of a fresh install: $(cat "$T/out")"
OPT=$T/s1 sh "$EMU" --verify simavr >/dev/null 2>&1 || fail "verify after simavr adopt"
rm "$T/s1/simavr-1.8/lib/libsimavr.a"
OPT=$T/s1 sh "$EMU" --adopt simavr >"$T/out" 2>&1 && fail "simavr adopt accepted a tree with a missing file"
no_debris "$T/s1"
# a file or a symlink where the tree should be: an error, not "not installed"
mkdir -p "$T/d1"
echo f >"$T/d1/simavr-1.8"
OPT=$T/d1 sh "$EMU" --verify simavr >/dev/null 2>&1 && fail "a file at the simavr destination verified"
mkdir -p "$T/d2" "$T/d2elsewhere"
ln -s ../d2elsewhere "$T/d2/simavr-1.8"
OPT=$T/d2 sh "$EMU" --verify simavr >/dev/null 2>&1 && fail "a symlink at the simavr destination verified"
mkdir -p "$T/d3"
OPT=$T/d3 sh "$EMU" --verify >"$T/out" 2>&1 || fail "an empty prefix is not 'not installed': $(cat "$T/out")"

# --- rp2040js and both QEMU trees from the dl copies
newp e1 rp2040js qemu-esp xtensa-esp
rm -f "$T/e1/dl/xtensa-esp/xtensa-esp-elf.tar.xz"
sh "$EMU" "$T/e1" rp2040js qemu-rv qemu-xt >"$T/out" 2>&1 || fail "rp2040js / qemu install: $(cat "$T/out")"
OPT=$T/e1 sh "$EMU" --verify rp2040js qemu-rv qemu-xt >"$T/out" 2>&1 || fail "rp2040js / qemu verify: $(cat "$T/out")"
[ -x "$T/e1/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32" ] || fail "no riscv32 qemu in its own tree"
[ -x "$T/e1/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa" ] || fail "no xtensa qemu in its own tree"
OPT=$T/e1 sh "$EMU" --adopt rp2040js >/dev/null 2>&1 || fail "rp2040js adopt"
OPT=$T/e1 sh "$EMU" --adopt qemu-xt >/dev/null 2>&1 || fail "qemu-xt adopt"
chmod -x "$T/e1/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa"
OPT=$T/e1 sh "$EMU" --verify qemu-xt >/dev/null 2>&1 && fail "qemu-xt verified after losing +x"
chmod +x "$T/e1/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa"
no_debris "$T/e1"

# --- qemu-arm: the .deb's usr/ tree from the dl copy (its own skip: the .deb is not among the files above)
if [ -e "$REAL/dl/qemu-arm/qemu-system-arm.deb" ]; then
	newp q1 qemu-arm
	sh "$EMU" "$T/q1" qemu-arm >"$T/out" 2>&1 || fail "qemu-arm install: $(cat "$T/out")"
	OPT=$T/q1 sh "$EMU" --verify qemu-arm >"$T/out" 2>&1 || fail "qemu-arm verify: $(cat "$T/out")"
	grep -q '^qemu-arm: OK' "$T/out" || fail "qemu-arm verify does not print OK: $(cat "$T/out")"
	[ -x "$T/q1/qemu-system-arm-8.2.2-0ubuntu1.18/usr/bin/qemu-system-arm" ] || fail "no qemu-system-arm in its own tree"
	OPT=$T/q1 sh "$EMU" --adopt qemu-arm >/dev/null 2>&1 || fail "qemu-arm adopt"
	chmod -x "$T/q1/qemu-system-arm-8.2.2-0ubuntu1.18/usr/bin/qemu-system-arm"
	OPT=$T/q1 sh "$EMU" --verify qemu-arm >/dev/null 2>&1 && fail "qemu-arm verified after losing +x"
	chmod +x "$T/q1/qemu-system-arm-8.2.2-0ubuntu1.18/usr/bin/qemu-system-arm"
	no_debris "$T/q1"
else
	echo "installers: qemu-arm skipped (no $REAL/dl/qemu-arm/qemu-system-arm.deb)"
fi

# --- rp2350js: the patched source archive, built from the dl copy and the npm cache (its own skip)
if [ -e "$REAL/dl/rp2350js/rp2350js-af0114c.tar.gz" ] && [ -d "$REAL/dl/rp2350js/npm-cache" ]; then
	newp j1 rp2350js
	sh "$EMU" "$T/j1" rp2350js >"$T/out" 2>&1 || fail "rp2350js install: $(cat "$T/out")"
	grep -q '^rp2350js: af0114c' "$T/out" || fail "rp2350js install does not print its version line: $(cat "$T/out")"
	OPT=$T/j1 sh "$EMU" --verify rp2350js >"$T/out" 2>&1 || fail "rp2350js verify: $(cat "$T/out")"
	grep -q '^rp2350js: OK' "$T/out" || fail "rp2350js verify does not print OK: $(cat "$T/out")"
	OPT=$T/j1 sh "$EMU" --adopt rp2350js >/dev/null 2>&1 || fail "rp2350js adopt"
	"$NODE" -p 'typeof require(process.argv[1]).RP2350' "$T/j1/rp2350js-af0114c/dist/cjs/index.js" | grep -qx function ||
		fail "the installed rp2350js does not export RP2350"
	echo x >>"$T/j1/rp2350js-af0114c/package.json"
	OPT=$T/j1 sh "$EMU" --verify rp2350js >/dev/null 2>&1 && fail "rp2350js verified after an edit"
	no_debris "$T/j1"
else
	echo "installers: rp2350js skipped (no $REAL/dl/rp2350js/rp2350js-af0114c.tar.gz or npm-cache)"
fi

# --- toolchains: the Xtensa tree from the dl copy, the pico-sdk clone from the local mirror
if [ -d "$MIRROR/.git" ]; then
	newp t1 xtensa-esp
	PICO_GIT=file://$MIRROR sh "$TC" "$T/t1" xtensa pico-sdk >"$T/out" 2>&1 || fail "xtensa / pico-sdk install: $(cat "$T/out")"
	grep -q '^pico-sdk: .*079c6f39023649b154152db30f1d781e884879bc' "$T/out" || fail "pico-sdk line does not name the commit: $(cat "$T/out")"
	OPT=$T/t1 sh "$TC" --verify xtensa pico-sdk >"$T/out" 2>&1 || fail "xtensa / pico-sdk verify: $(cat "$T/out")"
	[ ! -e "$T/t1/pico-sdk-2.3.1/.svf-manifest" ] || fail "a manifest file in the pico-sdk working tree"
	OPT=$T/t1 sh "$TC" --adopt xtensa >/dev/null 2>&1 || fail "xtensa adopt"
	echo stray >"$T/t1/pico-sdk-2.3.1/stray"
	OPT=$T/t1 sh "$TC" --verify pico-sdk >/dev/null 2>&1 && fail "pico-sdk verified with an untracked file"
	rm "$T/t1/pico-sdk-2.3.1/stray"
	# a stray PREFIX in the environment changes nothing (the prefix is OPT or the first argument)
	PREFIX=/nonexistent OPT=$T/t1 sh "$TC" --verify xtensa >"$T/out" 2>&1 || fail "stray PREFIX: $(cat "$T/out")"
	grep -q "$T/t1" "$T/out" || fail "stray PREFIX redirected the verify"
	no_debris "$T/t1"
	# a failed clone leaves nothing behind
	newp t2
	PICO_GIT=file://$T/nonexistent sh "$TC" "$T/t2" pico-sdk >/dev/null 2>&1 && fail "a clone of a missing repository succeeded"
	no_debris "$T/t2"
	[ ! -e "$T/t2/pico-sdk-2.3.1" ] || fail "a failed clone left pico-sdk-2.3.1"
fi
# --- pico-rv: the flat tarball (no top directory) from the dl copy; its own skip
if [ -e "$REAL/dl/pico-rv/riscv-toolchain-16-x86_64-lin.tar.gz" ]; then
	newp r1 pico-rv
	sh "$TC" "$T/r1" pico-rv >"$T/out" 2>&1 || fail "pico-rv install: $(cat "$T/out")"
	[ -x "$T/r1/pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf-gcc" ] || fail "no riscv32-pico-elf-gcc in its own tree"
	OPT=$T/r1 sh "$TC" --verify pico-rv >"$T/out" 2>&1 || fail "pico-rv verify: $(cat "$T/out")"
	grep -q '^pico-rv: OK' "$T/out" || fail "pico-rv verify does not print OK: $(cat "$T/out")"
	OPT=$T/r1 sh "$TC" --adopt pico-rv >/dev/null 2>&1 || fail "pico-rv adopt"
	chmod -x "$T/r1/pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf-gcc"
	OPT=$T/r1 sh "$TC" --verify pico-rv >/dev/null 2>&1 && fail "pico-rv verified after losing +x"
	chmod +x "$T/r1/pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf-gcc"
	no_debris "$T/r1"
else
	echo "installers: pico-rv skipped (no $REAL/dl/pico-rv/riscv-toolchain-16-x86_64-lin.tar.gz)"
fi
# --- wchisp: the tarball from the dl copy (one top directory, program at the root of the tree); its own skip
if [ -e "$REAL/dl/wchisp/wchisp-v0.3.0-linux-x64.tar.gz" ]; then
	newp w1 wchisp
	sh "$TC" "$T/w1" wchisp >"$T/out" 2>&1 || fail "wchisp install: $(cat "$T/out")"
	[ -x "$T/w1/wchisp-0.3.0/wchisp" ] || fail "no wchisp in its own tree"
	OPT=$T/w1 sh "$TC" --verify wchisp >"$T/out" 2>&1 || fail "wchisp verify: $(cat "$T/out")"
	grep -q '^wchisp: OK' "$T/out" || fail "wchisp verify does not print OK: $(cat "$T/out")"
	echo x >>"$T/w1/wchisp-0.3.0/README.md"
	OPT=$T/w1 sh "$TC" --verify wchisp >/dev/null 2>&1 && fail "wchisp verified after an edit"
	no_debris "$T/w1"
else
	echo "installers: wchisp skipped (no $REAL/dl/wchisp/wchisp-v0.3.0-linux-x64.tar.gz)"
fi
# --- ch583: the real sparse WCH EVT clone, copied (its own skip)
if [ -e "$REAL/ch583-evt/EVT/EXAM/SRC/Ld/Link.ld" ]; then
	mkdir "$T/c1" && cp -a "$REAL/ch583-evt" "$T/c1/"
	OPT=$T/c1 sh "$TC" --verify ch583 >"$T/out" 2>&1 || fail "ch583 verify: $(cat "$T/out")"
	grep -q '^ch583: OK' "$T/out" || fail "ch583 verify does not print OK: $(cat "$T/out")"
	grep -q " at bd508ad7ceed48377619837051412a651952857f" "$T/out" || fail "ch583 verify does not name the commit: $(cat "$T/out")"
	echo x >>"$T/c1/ch583-evt/EVT/EXAM/SRC/Ld/Link.ld"
	OPT=$T/c1 sh "$TC" --verify ch583 >/dev/null 2>&1 && fail "ch583 verified after an edit"
	mkdir "$T/c2" && cp -a "$REAL/ch583-evt" "$T/c2/"
	echo extra >>"$T/c2/ch583-evt/EVT/EXAM/SRC/.svf-manifest"
	OPT=$T/c2 sh "$TC" --verify ch583 >/dev/null 2>&1 && fail "ch583 verified after an edit of its manifest"
	# a file git ignores (the exclude of the manifest is the only one made): the manifest still catches an added file
	mkdir "$T/c3" && cp -a "$REAL/ch583-evt" "$T/c3/"
	echo ignored >"$T/c3/ch583-evt/EVT/EXAM/SRC/.svf-manifest.bak"
	echo '/EVT/EXAM/SRC/.svf-manifest.bak' >>"$T/c3/ch583-evt/.git/info/exclude"
	OPT=$T/c3 sh "$TC" --verify ch583 >"$T/out" 2>&1 && fail "ch583 verified with an ignored extra file"
	grep -q 'differs from its manifest' "$T/out" || fail "ignored extra file not caught by the manifest: $(cat "$T/out")"
	no_debris "$T/c1"; no_debris "$T/c2"; no_debris "$T/c3"
else
	echo "installers: ch583 skipped (no $REAL/ch583-evt)"
fi
# --- ch583, fresh install and the sparse-subtree rule: a tiny synthetic repository (file://) with the pinned layout. The
# installer is copied with sed so that its commit (and pin) are the synthetic ones; the real script keeps its pins.
S=$T/syn
git init -q "$S"
git -C "$S" config uploadpack.allowFilter true
git -C "$S" config uploadpack.allowAnySHA1InWant true
mkdir -p "$S/EVT/EXAM/SRC/Ld" "$S/EVT/OTHER"
echo ld >"$S/EVT/EXAM/SRC/Ld/Link.ld"
echo other >"$S/EVT/OTHER/f"
echo licence >"$S/LICENSE"
git -C "$S" add -A
git -C "$S" -c user.name=t -c user.email=t@t commit -q -m synthetic
SYN=$(git -C "$S" rev-parse HEAD)
mkdir -p "$T/ch"
ln -s "$here/manifest.sh" "$T/ch/manifest.sh"
ln -s "$here/install-lib.sh" "$T/ch/install-lib.sh"
# mkch PIN [COMMIT]: $T/ch/install-toolchains.sh with the synthetic commit and the given manifest pin
mkch() {
	sed "s/^CH583_COMMIT=[0-9a-f]*/CH583_COMMIT=${2:-$SYN}/; s/^MANIFEST_PIN_ch583=.*/MANIFEST_PIN_ch583=$1/" "$TC" >"$T/ch/install-toolchains.sh"
}
mkch ""
newp f1
CH583_GIT=file://$S sh "$T/ch/install-toolchains.sh" "$T/f1" ch583 >"$T/out" 2>&1 || fail "ch583 fresh install: $(cat "$T/out")"
grep -q "^ch583: $SYN" "$T/out" || fail "ch583 fresh install does not print the commit: $(cat "$T/out")"
pinline=$(sed -n 's/^ch583: installed; manifest pin: MANIFEST_PIN_ch583=\([0-9a-f]\{64\}\) .*/\1/p' "$T/out")
[ -n "$pinline" ] || fail "ch583 fresh install prints no pin: $(cat "$T/out")"
F=$T/f1/ch583-evt
[ -f "$F/EVT/EXAM/SRC/Ld/Link.ld" ] || fail "fresh ch583: no EVT/EXAM/SRC/Ld/Link.ld"
[ -f "$F/LICENSE" ] || fail "fresh ch583: no root LICENSE"
[ ! -e "$F/EVT/OTHER" ] || fail "fresh ch583: the sparse checkout took EVT/OTHER"
[ -f "$F/EVT/EXAM/SRC/.svf-manifest" ] || fail "fresh ch583: no manifest"
[ "$(git -C "$F" rev-parse HEAD)" = "$SYN" ] || fail "fresh ch583: HEAD is not the commit"
[ -z "$(git -C "$F" status --porcelain)" ] || fail "fresh ch583: git status is not clean"
grep -qx '/EVT/EXAM/SRC/.svf-manifest' "$F/.git/info/exclude" || fail "fresh ch583: manifest not in .git/info/exclude"
git -C "$F" sparse-checkout list | grep -qx 'EVT/EXAM/SRC' || fail "fresh ch583: sparse-checkout not written"
no_debris "$T/f1"
# with the pin in the script: the same tree verifies, and a second run (the tree in place) passes
mkch "$pinline"
OPT=$T/f1 sh "$T/ch/install-toolchains.sh" --verify ch583 >"$T/out" 2>&1 || fail "fresh ch583 verify: $(cat "$T/out")"
CH583_GIT=file://$S sh "$T/ch/install-toolchains.sh" "$T/f1" ch583 >"$T/out" 2>&1 || fail "ch583 second run: $(cat "$T/out")"
# a fresh install into a prefix with a wrong pin is refused; a fetch of a commit the remote lacks leaves nothing
newp f2
mkch 0000000000000000000000000000000000000000000000000000000000000000
CH583_GIT=file://$S sh "$T/ch/install-toolchains.sh" "$T/f2" ch583 >/dev/null 2>&1 && fail "ch583 fresh install accepted a wrong manifest pin"
mkch "$pinline" 1111111111111111111111111111111111111111
newp f3
CH583_GIT=file://$S sh "$T/ch/install-toolchains.sh" "$T/f3" ch583 >/dev/null 2>&1 && fail "ch583 install of a commit the remote lacks succeeded"
[ ! -e "$T/f3/ch583-evt" ] || fail "a failed ch583 fetch left ch583-evt"
no_debris "$T/f3"
# a clean checkout at the pinned commit whose sparse selection excludes EVT/EXAM/SRC: --verify and install both fail
mkch "$pinline"
mkdir -p "$T/f4"
git clone -q --no-checkout "file://$S" "$T/f4/ch583-evt"
git -C "$T/f4/ch583-evt" sparse-checkout set EVT/OTHER
git -C "$T/f4/ch583-evt" -c advice.detachedHead=false checkout -q "$SYN"
[ -z "$(git -C "$T/f4/ch583-evt" status --porcelain)" ] || fail "the SRC-less fixture is not clean"
[ ! -e "$T/f4/ch583-evt/EVT/EXAM/SRC" ] || fail "the SRC-less fixture has SRC"
OPT=$T/f4 sh "$T/ch/install-toolchains.sh" --verify ch583 >"$T/out" 2>&1 && fail "ch583 verified with EVT/EXAM/SRC absent"
grep -q "EVT/EXAM/SRC is missing" "$T/out" || fail "SRC-less ch583 verify message: $(cat "$T/out")"
sh "$T/ch/install-toolchains.sh" "$T/f4" ch583 >"$T/out" 2>&1 && fail "ch583 install accepted a clone without EVT/EXAM/SRC"
# an absent whole clone is still "not installed"
mkdir -p "$T/f5"
OPT=$T/f5 sh "$TC" --verify ch583 >"$T/out" 2>&1 || fail "absent ch583 is not 'not installed': $(cat "$T/out")"
grep -q 'not installed' "$T/out" || fail "absent ch583 does not say so"
# --adopt ch583 is refused with its own reason
sh "$TC" --adopt ch583 >"$T/out" 2>&1 && fail "--adopt ch583 accepted"
grep -q 'cannot be adopted' "$T/out" || fail "--adopt ch583 message: $(cat "$T/out")"
mkdir -p "$T/t3"
echo f >"$T/t3/pico-sdk-2.3.1"
OPT=$T/t3 sh "$TC" --verify pico-sdk >/dev/null 2>&1 && fail "a file at the pico-sdk destination verified"
# --- sdl3: the verify rule on a faked tree (the fork build is a stub here; the real build is the install of Step 4)
SDLC=7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06
mkdir -p "$T/sd/sdl3/lib/pkgconfig"
: >"$T/sd/sdl3/lib/pkgconfig/sdl3.pc"
echo 0000000000000000000000000000000000000000 >"$T/sd/sdl3/COMMIT"
OPT=$T/sd sh "$TC" --verify sdl3 >"$T/out" 2>&1 && fail "sdl3 verify accepted a wrong COMMIT"
grep -q 0000000000000000000000000000000000000000 "$T/out" && grep -q "$SDLC" "$T/out" || fail "sdl3 verify does not name both shas: $(cat "$T/out")"
echo "$SDLC" >"$T/sd/sdl3/COMMIT"
OPT=$T/sd sh "$TC" --verify sdl3 >"$T/out" 2>&1 || fail "sdl3 verify of a right COMMIT: $(cat "$T/out")"
rm "$T/sd/sdl3/lib/pkgconfig/sdl3.pc"
OPT=$T/sd sh "$TC" --verify sdl3 >/dev/null 2>&1 && fail "sdl3 verified without sdl3.pc"
mkdir -p "$T/sd0"
OPT=$T/sd0 sh "$TC" --verify sdl3 >"$T/out" 2>&1 || fail "absent sdl3 verify failed: $(cat "$T/out")"
grep -q '^sdl3: not installed' "$T/out" || fail "absent sdl3 does not say 'sdl3: not installed': $(cat "$T/out")"
# an install with no fork tree, and with a fork tree at another commit, is refused (names both shas)
mkdir -p "$T/sd1"
SDL3_SRC=$T/nofork sh "$TC" "$T/sd1" sdl3 >"$T/out" 2>&1 && fail "sdl3 install accepted an absent fork tree"
grep -q 'the fork tree is not at' "$T/out" || fail "sdl3 absent-fork message: $(cat "$T/out")"
mkdir -p "$T/fork"
git -C "$T/fork" init -q
git -C "$T/fork" -c user.name=t -c user.email=t@t commit -q --allow-empty -m x
SDL3_SRC=$T/fork sh "$TC" "$T/sd1" sdl3 >"$T/out" 2>&1 && fail "sdl3 install accepted a fork at another commit"
grep -q "$SDLC" "$T/out" && grep -q "$(git -C "$T/fork" rev-parse HEAD)" "$T/out" || fail "sdl3 wrong-HEAD message lacks both shas: $(cat "$T/out")"
[ ! -e "$T/sd1/sdl3" ] || fail "a refused sdl3 install left sdl3"
no_debris "$T/sd1"
# --adopt sdl3 has its own refusal
sh "$TC" --adopt sdl3 >"$T/out" 2>&1 && fail "--adopt sdl3 accepted"
grep -q 'sdl3: cannot be adopted' "$T/out" || fail "--adopt sdl3 message: $(cat "$T/out")"
# a fork tree at the pin (the script copy gets its sha), and stub cmake/pkg-config that log their arguments
mkdir -p "$T/sc" "$T/stub"
ln -s "$here/manifest.sh" "$T/sc/manifest.sh"
ln -s "$here/install-lib.sh" "$T/sc/install-lib.sh"
mkdir -p "$T/fork2"
git -C "$T/fork2" init -q
echo a >"$T/fork2/a.c"
git -C "$T/fork2" add a.c
git -C "$T/fork2" -c user.name=t -c user.email=t@t commit -q -m x
FC=$(git -C "$T/fork2" rev-parse HEAD)
sed "s/^SDL3_COMMIT=[0-9a-f]*/SDL3_COMMIT=$FC/" "$TC" >"$T/sc/install-toolchains.sh"
cat >"$T/stub/cmake" <<'EOS'
#!/bin/sh
# stub: logs its arguments; configure remembers the prefix, install writes sdl3.pc there; STUB_FAIL=build fails the build
printf '%s\n' "$@" >>"$STUB_LOG"
case $1 in
-S) for a; do case $a in -DCMAKE_INSTALL_PREFIX=*) pfx=${a#*=} ;; esac; done
	case $pfx in /*) ;; *) echo "stub cmake: relative install prefix $pfx" >&2; exit 1 ;; esac
	shift; shift; mkdir -p "$2"; echo "$pfx" >"$2/prefix" ;;
--build) [ "${STUB_FAIL:-}" != build ] || exit 1 ;;
--install) pfx=$(cat "$2/prefix"); mkdir -p "$DESTDIR$pfx/lib/pkgconfig"; : >"$DESTDIR$pfx/lib/pkgconfig/sdl3.pc" ;;
esac
EOS
printf '#!/bin/sh\necho 3.5.0\n' >"$T/stub/pkg-config"
chmod +x "$T/stub/cmake" "$T/stub/pkg-config"
export STUB_LOG=$T/stub.log
sdl() { SDL3_SRC=$T/fork2 PATH=$T/stub:$PATH sh "$T/sc/install-toolchains.sh" "$@"; }
# dirty tracked file: refused, names it, builds nothing
echo b >>"$T/fork2/a.c"
mkdir -p "$T/sd2"
: >"$STUB_LOG"
sdl "$T/sd2" sdl3 >"$T/out" 2>&1 && fail "sdl3 install accepted a dirty fork tree"
grep -q 'uncommitted changes' "$T/out" && grep -q 'a.c' "$T/out" || fail "sdl3 dirty message: $(cat "$T/out")"
[ ! -s "$STUB_LOG" ] && [ ! -e "$T/sd2/sdl3" ] || fail "a dirty fork tree was built"
git -C "$T/fork2" checkout -q a.c
# untracked files: under the globbed paths refused, elsewhere not
mkdir -p "$T/fork2/src"
echo n >"$T/fork2/src/new.c"
sdl "$T/sd2" sdl3 >"$T/out" 2>&1 && fail "sdl3 install accepted an untracked src/new.c"
grep -q 'src/new.c' "$T/out" || fail "sdl3 untracked message: $(cat "$T/out")"
[ ! -s "$STUB_LOG" ] || fail "a fork tree with an untracked src file was built"
rm -r "$T/fork2/src"
echo n >"$T/fork2/notes.txt"
# (notes.txt, untracked outside the globbed paths, stays and must not block the installs below)
# a failed build leaves nothing and no debris
STUB_FAIL=build; export STUB_FAIL
sdl "$T/sd2" sdl3 >"$T/out" 2>&1 && fail "sdl3 install survived a failed build"
unset STUB_FAIL
[ ! -e "$T/sd2/sdl3" ] || fail "a failed sdl3 build left sdl3"
no_debris "$T/sd2"
# a good install: every switch, COMMIT, the OK line, no debris
: >"$STUB_LOG"
sdl "$T/sd2" sdl3 >"$T/out" 2>&1 || fail "sdl3 stub install: $(cat "$T/out")"
for sw in -DCMAKE_BUILD_TYPE=Release -DSDL_SHARED=ON -DSDL_STATIC=ON -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF -DSDL_AUDIO=OFF \
	-DSDL_JOYSTICK=OFF -DSDL_HAPTIC=OFF -DSDL_CAMERA=OFF -DSDL_SENSOR=OFF -DSDL_GPU=OFF -DSDL_WAYLAND=OFF -DSDL_X11_XTEST=OFF \
	"-DCMAKE_INSTALL_PREFIX=$T/sd2/sdl3"; do
	grep -qxF -- "$sw" "$STUB_LOG" || fail "sdl3 configure lacks the argument $sw: $(cat "$STUB_LOG")"
	[ "$(grep -cF -- "${sw%%=*}=" "$STUB_LOG")" -eq 1 ] || fail "sdl3 configure gives ${sw%%=*} more than once or with another value: $(cat "$STUB_LOG")"
done
[ "$(cat "$T/sd2/sdl3/COMMIT")" = "$FC" ] || fail "sdl3 COMMIT is not the pin"
grep -qx "sdl3: OK $FC ($T/sd2/sdl3)" "$T/out" || fail "sdl3 install prints no OK line: $(cat "$T/out")"
tail -n 1 "$T/out" | grep -qx 3.5.0 || fail "sdl3 install does not end with the version"
no_debris "$T/sd2"
# a tree in place is not replaced
: >"$STUB_LOG"
echo keep >"$T/sd2/sdl3/marker"
sdl "$T/sd2" sdl3 >"$T/out" 2>&1 || fail "sdl3 second run: $(cat "$T/out")"
grep -q 'not replaced' "$T/out" && [ ! -s "$STUB_LOG" ] && [ -f "$T/sd2/sdl3/marker" ] || fail "sdl3 was rebuilt over a present tree: $(cat "$T/out")"
# a relative PREFIX is made absolute
(cd "$T" && SDL3_SRC=$T/fork2 PATH=$T/stub:$PATH sh "$T/sc/install-toolchains.sh" rel sdl3 >"$T/out" 2>&1) || fail "sdl3 with a relative prefix: $(cat "$T/out")"
grep -qx "sdl3: OK $FC ($T/rel/sdl3)" "$T/out" || fail "relative-prefix OK line is not absolute: $(cat "$T/out")"
[ -f "$T/rel/sdl3/lib/pkgconfig/sdl3.pc" ] && [ "$(cat "$T/rel/sdl3/COMMIT")" = "$FC" ] || fail "relative-prefix sdl3 install: $(cat "$T/out")"
# no names: sdl3 is skipped when SDL3_SRC is no git tree (a copy whose want() accepts only sdl3 in a name-less run, so
# the other names do not download), and installed when it is
sed 's/^\t\[ -z "\$NAMES" \] && return 0/\t[ -z "$NAMES" ] \&\& { [ "$1" = sdl3 ]; return; }/' "$T/sc/install-toolchains.sh" >"$T/sc/only-sdl3.sh"
grep -q 'return; }' "$T/sc/only-sdl3.sh" || fail "the name-less test copy was not made"
mkdir -p "$T/sd3"
SDL3_SRC=$T/nofork sh "$T/sc/only-sdl3.sh" "$T/sd3" >"$T/out" 2>&1 || fail "name-less run without a fork tree: $(cat "$T/out")"
grep -qx "sdl3: skipped (no fork tree at $T/nofork)" "$T/out" || fail "name-less run does not skip sdl3: $(cat "$T/out")"
[ ! -e "$T/sd3/sdl3" ] || fail "a skipped sdl3 left sdl3"
SDL3_SRC=$T/fork2 PATH=$T/stub:$PATH sh "$T/sc/only-sdl3.sh" "$T/sd3" >"$T/out" 2>&1 || fail "name-less run with a fork tree: $(cat "$T/out")"
[ -f "$T/sd3/sdl3/COMMIT" ] || fail "name-less run did not install sdl3"
echo "installers: OK"
