#!/bin/sh
# install-emulators.sh [PREFIX [NAME...]] - installs the emulators of c/bench/run-*.sh in user space (no sudo).
# OPT=DIR install-emulators.sh --verify [NAME...] - re-checks what is installed (default: every name).
# OPT=DIR install-emulators.sh --adopt NAME - writes the first manifest / pin of a tree that is already installed (below).
# Tests: c/cross/test-installers.sh (a manual check, run after a change here; no gate runs it) and, for the manifests,
# c/cross/test-manifest.sh (in c/ports/check/host-checks.sh).
#
# PREFIX (default $OPT, else ~/opt; for --verify and --adopt $OPT, else ~/opt: a PREFIX in the environment is ignored)
# receives one directory an emulator; downloads go to PREFIX/dl/<name>/ and each is checked against the hash below before
# it is unpacked or installed. An emulator already in place is not replaced. The files it writes are under PREFIX, with
# these exceptions: npm keeps its cache (~/.npm), git reads the user's git configuration, curl and tar their usual state.
# No shell profile and no system package is touched, and no global npm prefix is used. Work areas (unpack, builds,
# comparison trees) are PREFIX/.svf-work, removed at exit.
#
# Names: simavr rp2040js qemu-rv qemu-xt qemu-arm bootrom rp2350js.
#
# Pinned (c/bench/MEASUREMENTS.md records the source hashes of simavr, rp2040js, both QEMUs, the boot ROM, both Espressif toolchains and pico-sdk; the manifest pins
# are recorded here and in the task report):
#   simavr   1.8      github.com/buserror/simavr tag v1.8 (source archive; the project publishes no release asset
#                     and no checksum: the sha256 below was computed from two downloads that agreed, 2026-10-19).
#                     Built with the host gcc (needs libelf headers, present on this host) into PREFIX/simavr-1.8.
#   rp2040js 1.4.0    npm registry tarball; checked against the registry's sha512 integrity before npm sees it,
#                     installed into PREFIX/rp2040js-1.4.0 (a package with no dependencies). Needs node >= 18:
#                     NODE (default PREFIX/node-v24.13.0-linux-x64/bin/node, as on this host).
#   qemu-rv, qemu-xt  Espressif's QEMU 9.2.2 (esp_develop_9.2.2_20260417), one archive and one tree each, never shared:
#                     PREFIX/qemu-esp-9.2.2-20260417-riscv32/qemu/ and PREFIX/qemu-esp-9.2.2-20260417-xtensa/qemu/. The
#                     local copies PREFIX/dl/qemu-esp/qemu-riscv32-esp.tar.xz and PREFIX/dl/xtensa-esp/qemu-xtensa-esp.tar.xz
#                     are used when their sha256 matches the publisher's, else the release asset is fetched. The old shared
#                     PREFIX/qemu-esp-9.2.2-20260417/ is never touched.
#   qemu-arm          Ubuntu's qemu-system-arm 8.2.2 (package 1:8.2.2+ds-0ubuntu1.18, the .deb below, 10,963,018 bytes), the
#                     Cortex-M33 board mps2-an505 of c/bench/run-m33.sh. The .deb's usr/ tree is unpacked with `dpkg-deb -x`
#                     (no root, no package database) into PREFIX/qemu-system-arm-8.2.2-0ubuntu1.18/; the binary is
#                     usr/bin/qemu-system-arm and runs with the host's shared libraries (mps2-an505 needs no data files).
#                     Needs dpkg-deb. The Ubuntu pool drops superseded versions, so the copy under
#                     PREFIX/dl/qemu-arm/qemu-system-arm.deb is the durable source (as DJGPP's note says); it is used when
#                     its sha256 matches, else the pool URL is fetched.
#   bootrom           the RP2040 B1 boot ROM rp2040js needs (its npm package does not ship it): demo/bootrom.ts of
#                     rp2040js tag v1.4.0 (commit 0c1c316e87b34e616985af35d4c147fc19cfeee9), sha256 pinned below, fetched
#                     to PREFIX/dl/rp2040js/bootrom.ts; its 4,096 0x... words, in order, written little-endian as the
#                     16,384-byte PREFIX/rp2040js-1.4.0/bootrom-b1.bin, whose sha256 is BOOTROM_BIN_SHA256 (pinned at the
#                     first generation, checked on every run). That file is the one canonical location of the ROM.
#                     --verify bootrom checks the .bin and, when PREFIX/dl/rp2040js/bootrom.ts is there, its sha256 too.
#   rp2350js          github.com/c1570/rp2350js (a fork of the RP2040 emulator rp2040js with an RP2350: Hazard3 and Cortex-M33
#                     cores) at commit af0114cbee8e9e91574204b66f10aa2961cbf28c (rp2350js 2.0.1, MIT), the source archive
#                     RPJS_URL (1,246,966 bytes; GitHub publishes no checksum for a generated archive: the sha256 below was
#                     computed from two downloads that agreed, 2026-10-21). A source archive because the fork has no npm
#                     release at that commit. A durable copy is kept on first fetch as PREFIX/dl/rp2350js/rp2350js-af0114c.tar.gz
#                     (as the qemu-arm .deb: GitHub may regenerate archives). Built in the work area: the archive is
#                     unpacked, the sha256 of its package-lock.json is checked (RPJS_LOCK_SHA256: it pins every npm package
#                     by integrity), c/bench/rp2350js.patch is applied (four emulator fixes found with the bench's images:
#                     see the patch's header; needs patch(1)), `npm ci --ignore-scripts` installs the 430 packages of the
#                     lockfile (npm checks each against its sha512 integrity; --ignore-scripts skips husky and canvas's
#                     native build, which tsc does not need; the npm cache PREFIX/dl/rp2350js/npm-cache makes a reinstall or
#                     --adopt work offline) and tsc (TypeScript 5.9.3 from the lockfile) builds the CommonJS output only.
#                     PREFIX/rp2350js-af0114c/ receives dist/cjs/, node_modules/uf2/ (the only package dist/cjs/index.js
#                     loads), package.json and LICENSE. Needs node and npm (NODE; node v24.13.0 bundles npm 11.6.2), patch,
#                     and the npm registry on the first install (or the cache). The boot ROM the emulator uses is the A2 ROM
#                     bundled in its source (src/bootroms/bootrom-rp2350-a2.ts), pinned by the archive's sha256. The
#                     manifest pin covers the patch: a change to rp2350js.patch changes dist/cjs, so --verify fails until the
#                     tree is rebuilt and the pin re-pasted.
# DOSBox-X (/usr/bin/dosbox-x, 2026.08.31) and node are not installed here.
#
# Verification. Threat model: accidental drift or corruption of a host-local tree (a stray edit, a truncated copy, a
# half-run upgrade), not an adversary. A tarball tree carries DEST/.svf-manifest (c/cross/manifest.sh: the archive's
# sha256, every file's sha256, every symlink's target, every file's execute bits as "exec" lines); the sha256 of that
# manifest is pinned here (MANIFEST_PIN_<name>).
# --verify checks the manifest against the pin, then the tree against the manifest, and names the first difference.
# --adopt NAME writes the first manifest of a tree already installed, after comparing it with a fresh build of the verified
# download in the work area:
#   qemu-*    the tarball unpacked beside the installed tree (byte for byte); qemu-arm: a fresh dpkg-deb -x of the verified .deb;
#   rp2040js  npm install of the verified tgz into a temporary prefix; the manifest covers PREFIX/rp2040js-1.4.0/node_modules
#             only (node_modules/.svf-manifest), not the boot ROM beside it, which has its own pin;
#   simavr    the source archive rebuilt in the work area. Measured 2026-10-21: the rebuild is NOT byte-identical to the
#             installed tree (7 of 41 entries differ: bin/simavr, lib/libsimavr.a, lib/libsimavr.so.1,
#             include/simavr/sim_core_decl.h and the two lib/pkgconfig/*.pc, which hold the install prefix). So the simavr
#             manifest cannot be pinned for every host: MANIFEST_PIN_simavr is the pin of the tree on the host that adopted
#             it. --adopt simavr requires the same set of paths, links and exec bits as the rebuild (content may differ:
#             F10) and adopts the installed tree as it is; a fresh install writes its own manifest and, where that differs
#             from MANIFEST_PIN_simavr, records its pin in PREFIX/.svf-local-pins/simavr (outside the tree), which --verify
#             then uses instead. The manifest then catches later drift, not an earlier difference from a clean build, which
#             is all the accidental-drift threat model asks.
# A tree with no pin yet is "present, not adopted". A package whose path is absent is "not installed" (not an error); a
# present but wrong tree, a file or a symlink in its place is an error and is never replaced by this script.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../cross/manifest.sh"

MODE=install
OPT=${OPT:-$HOME/opt}
case ${1:-} in
--verify | --adopt)
	MODE=${1#--}
	shift
	PREFIX=$OPT
	;;
*)
	PREFIX=${1:-$OPT}
	[ $# -eq 0 ] || shift
	;;
esac
DL=$PREFIX/dl
. "$HERE/../cross/install-lib.sh"
NODE_BIN=$(dirname "${NODE:-$PREFIX/node-v24.13.0-linux-x64/bin/node}")

SIMAVR_VER=1.8
SIMAVR_URL=https://github.com/buserror/simavr/archive/refs/tags/v$SIMAVR_VER.tar.gz
SIMAVR_SHA256=51e2682d23fb4843191ee81dadcb5488fa6194553a108bbd6e60e8b1260269d6

RP_VER=1.4.0
RP_URL=https://registry.npmjs.org/rp2040js/-/rp2040js-$RP_VER.tgz
RP_SHA512=knEMw0SRP9JPVLvhhYB3rjP4gLQhcWs9UOXKvxFU9Rn5eWvmlPzObMhEjfeLZ6H8FGepd6ZtMAYzGEtCaB9qYg==

QEMU_REL=esp-develop-9.2.2-20260417
QEMU_RV_URL=https://github.com/espressif/qemu/releases/download/$QEMU_REL/qemu-riscv32-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz
QEMU_RV_SHA256=547f03e04701a92cbb699f7f7d015adc1f5b5ef93cbb94c0dd9b7107e2d84e77
QEMU_RV_LOCAL=$DL/qemu-esp/qemu-riscv32-esp.tar.xz
QEMU_XT_URL=https://github.com/espressif/qemu/releases/download/$QEMU_REL/qemu-xtensa-softmmu-esp_develop_9.2.2_20260417-x86_64-linux-gnu.tar.xz
QEMU_XT_SHA256=0eecb2a34a5586c0e59110f77b9343b7b336e82fdb0e1a30e1dc1bab8a547e35
QEMU_XT_LOCAL=$DL/xtensa-esp/qemu-xtensa-esp.tar.xz

QEMU_ARM_URL=https://archive.ubuntu.com/ubuntu/pool/main/q/qemu/qemu-system-arm_8.2.2%2bds-0ubuntu1.18_amd64.deb
QEMU_ARM_SHA256=06184a21b9c8dc573ab6d255e9826cc4732df90e56bd65c52e92ad640af4d60a
QEMU_ARM_LOCAL=$DL/qemu-arm/qemu-system-arm.deb
QEMU_ARM=$PREFIX/qemu-system-arm-8.2.2-0ubuntu1.18

RPJS_COMMIT=af0114cbee8e9e91574204b66f10aa2961cbf28c
RPJS_URL=https://github.com/c1570/rp2350js/archive/$RPJS_COMMIT.tar.gz
RPJS_SHA256=2bcf172e083c53671df4a5787a793bca5aa5ee5451098a84f017852eb227bcf2
RPJS_LOCAL=$DL/rp2350js/rp2350js-af0114c.tar.gz
RPJS_LOCK_SHA256=dd88d3100bd97acdcaa3daa3c2c931590938cd5a42d72e2daf7978d684f24e05

BOOTROM_URL=https://raw.githubusercontent.com/wokwi/rp2040js/v1.4.0/demo/bootrom.ts
BOOTROM_TS_SHA256=99f8a1f813ce3aa9415884de3fb6c5b962d3c6fa0394b05413ad3c7b3c39ec62
BOOTROM_BIN_SHA256=90b31e108faedfa6bbcfcc33ba05dac61e645108cfbbdc385f8dafc71fde44ae

# The sha256 of each tree's .svf-manifest (printed by the install or by --adopt NAME; paste it here).
MANIFEST_PIN_simavr=866f2e18452d3052c30b852628e2d9b73045eca3f86edf2fc5f545d4f1a550b1
MANIFEST_PIN_rp2040js=2fb502fe333cc4ab2094d9b5a6e2d0c80054c789b815eb7b94e14e29a357aa4a
MANIFEST_PIN_qemu_rv=a7da3b53728791cd6a5c54b899e6b1ae7a6a2814f50f0b1decefe05cba33ea19
MANIFEST_PIN_qemu_xt=ab4444e0792ff641d9d6c7f026d72f11b948ed7eb83913b587c34bb36f6f4d66
MANIFEST_PIN_qemu_arm=9a25a1c005a52039b4b0f4689910860affdb02d4e06949a503bc79caaa42377c
MANIFEST_PIN_rp2350js=1e11241c2f12c8ab28f40639142631f7339e2abb1700b10324aba6501d59fc73

SIMAVR=$PREFIX/simavr-$SIMAVR_VER
RPJS=$PREFIX/rp2350js-af0114c
RP=$PREFIX/rp2040js-$RP_VER
BOOTROM_BIN=$RP/bootrom-b1.bin

LOCAL_PINS=$PREFIX/.svf-local-pins

# qreg NAME: sets Q_DEST, Q_URL, Q_SHA, Q_LOCAL, Q_BIN of qemu-rv / qemu-xt.
qreg() {
	case $1 in
	qemu-rv)
		Q_DEST=$PREFIX/qemu-esp-9.2.2-20260417-riscv32/qemu Q_URL=$QEMU_RV_URL Q_SHA=$QEMU_RV_SHA256
		Q_LOCAL=$QEMU_RV_LOCAL Q_BIN=qemu-system-riscv32 ;;
	qemu-xt)
		Q_DEST=$PREFIX/qemu-esp-9.2.2-20260417-xtensa/qemu Q_URL=$QEMU_XT_URL Q_SHA=$QEMU_XT_SHA256
		Q_LOCAL=$QEMU_XT_LOCAL Q_BIN=qemu-system-xtensa ;;
	esac
}

# qemu_arm_unpack DEST: the verified .deb's files (usr/...) extracted into DEST (which must not exist); sets FETCHED.
qemu_arm_unpack() {
	command -v dpkg-deb >/dev/null 2>&1 || { echo "qemu-arm: dpkg-deb is needed and not found" >&2; exit 1; }
	fetch_sha qemu-arm "$QEMU_ARM_URL" "$QEMU_ARM_SHA256" "$QEMU_ARM_LOCAL"
	# a downloaded copy is also kept under the durable name, so a reinstall works after the pool drops the version
	if [ "$FETCHED" != "$QEMU_ARM_LOCAL" ] && [ ! -e "$QEMU_ARM_LOCAL" ]; then
		cp "$FETCHED" "$QEMU_ARM_LOCAL.part" && mv "$QEMU_ARM_LOCAL.part" "$QEMU_ARM_LOCAL" ||
			{ rm -f "$QEMU_ARM_LOCAL.part"; echo "qemu-arm: cannot store $QEMU_ARM_LOCAL" >&2; exit 1; }
	fi
	[ ! -e "$1" ] && [ ! -L "$1" ] || { echo "qemu-arm: $1 exists" >&2; exit 1; }
	mkdir -p "$1"
	dpkg-deb -x "$FETCHED" "$1" || { rm -rf "$1"; echo "qemu-arm: dpkg-deb -x failed" >&2; exit 1; }
}

# build_simavr DEST: the verified source archive built (library and run_avr) and installed into DEST, building in the work
# area under a fixed directory name.
build_simavr() {
	fetch_sha simavr "$SIMAVR_URL" "$SIMAVR_SHA256"
	work_ensure
	src=$WORK/.build-simavr
	rm -rf "$src"
	mkdir -p "$src"
	tar -xzf "$FETCHED" -C "$src"
	[ -d "$src/simavr-$SIMAVR_VER/simavr" ] || { echo "simavr: unexpected archive layout" >&2; exit 1; }
	make -C "$src/simavr-$SIMAVR_VER/simavr" RELEASE=1 CC=gcc >"$src/build.log" 2>&1 ||
		{ tail -n 20 "$src/build.log" >&2; exit 1; }
	make -C "$src/simavr-$SIMAVR_VER/simavr" install RELEASE=1 CC=gcc DESTDIR="$1" PREFIX="$1" \
		>>"$src/build.log" 2>&1 || { tail -n 20 "$src/build.log" >&2; exit 1; }
}

# simavr_pin: the pin --verify uses: this host's (PREFIX/.svf-local-pins/simavr) when a fresh build was recorded, else the
# script's.
simavr_pin() {
	if [ -f "$LOCAL_PINS/simavr" ]; then cat "$LOCAL_PINS/simavr"; else pin simavr; fi
}
# simavr_pin_what: where simavr_pin comes from, for messages (manifest_verify's fourth argument)
simavr_pin_what() {
	if [ -f "$LOCAL_PINS/simavr" ]; then echo "the local pin $LOCAL_PINS/simavr"; else echo "the pin in the script"; fi
}
# simavr_record GOT: GOT, the manifest pin of a tree this host built or adopted, is kept as the local pin when it is not
# the script's.
simavr_record() {
	if [ "$1" != "$(pin simavr)" ]; then
		mkdir -p "$LOCAL_PINS"
		echo "$1" >"$LOCAL_PINS/simavr"
		echo "simavr: manifest $1 differs from the pinned tree ($(pin simavr)): the build is not reproducible; kept as the local pin $LOCAL_PINS/simavr"
	else
		rm -f "$LOCAL_PINS/simavr"
		rmdir "$LOCAL_PINS" 2>/dev/null || true
	fi
}

# install_rp DEST: the registry tarball, verified against the pinned integrity, installed from that file only.
install_rp() {
	fetch_url rp2040js "$RP_URL"
	got=$(openssl dgst -sha512 -binary "$FETCHED" | base64 -w0)
	[ "$got" = "$RP_SHA512" ] || bad rp2040js "$FETCHED"
	mkdir -p "$1"
	PATH=$NODE_BIN:$PATH npm install --prefix "$1" --no-save --no-audit --no-fund --ignore-scripts "$FETCHED" >/dev/null
}

# build_rpjs DEST: the verified source archive, patched with rp2350js.patch, npm-installed from its lockfile and compiled
# (CommonJS only) in the work area; DEST (which must not exist) receives dist/cjs, node_modules/uf2, package.json, LICENSE.
build_rpjs() {
	command -v patch >/dev/null 2>&1 || { echo "rp2350js: patch(1) is needed and not found" >&2; exit 1; }
	[ -x "$NODE_BIN/node" ] && [ -x "$NODE_BIN/npm" ] || { echo "rp2350js: node and npm are needed in $NODE_BIN" >&2; exit 1; }
	fetch_sha rp2350js "$RPJS_URL" "$RPJS_SHA256" "$RPJS_LOCAL"
	# a downloaded copy is also kept under the durable name, so a reinstall works after GitHub regenerates the archive
	if [ "$FETCHED" != "$RPJS_LOCAL" ] && [ ! -e "$RPJS_LOCAL" ]; then
		cp "$FETCHED" "$RPJS_LOCAL.part" && mv "$RPJS_LOCAL.part" "$RPJS_LOCAL" ||
			{ rm -f "$RPJS_LOCAL.part"; echo "rp2350js: cannot store $RPJS_LOCAL" >&2; exit 1; }
	fi
	work_ensure
	unpack rp2350js "$FETCHED" "$WORK/rpjs-src"
	echo "$RPJS_LOCK_SHA256  $WORK/rpjs-src/package-lock.json" | sha256sum -c - >/dev/null ||
		{ echo "rp2350js: package-lock.json does not have the pinned sha256 $RPJS_LOCK_SHA256" >&2; exit 1; }
	patch -p1 --forward --no-backup-if-mismatch -d "$WORK/rpjs-src" <"$HERE/rp2350js.patch" >"$WORK/rpjs-patch.log" 2>&1 ||
		{ cat "$WORK/rpjs-patch.log" >&2; echo "rp2350js: rp2350js.patch does not apply" >&2; exit 1; }
	mkdir -p "$DL/rp2350js/npm-cache"
	(cd "$WORK/rpjs-src" && PATH=$NODE_BIN:$PATH npm ci --ignore-scripts --no-audit --no-fund --prefer-offline \
		--cache "$DL/rp2350js/npm-cache" >"$WORK/rpjs-npm.log" 2>&1) ||
		{ tail -n 20 "$WORK/rpjs-npm.log" >&2; echo "rp2350js: npm ci failed" >&2; exit 1; }
	(cd "$WORK/rpjs-src" && "$NODE_BIN/node" node_modules/typescript/bin/tsc -p tsconfig.json >"$WORK/rpjs-tsc.log" 2>&1) ||
		{ tail -n 20 "$WORK/rpjs-tsc.log" >&2; echo "rp2350js: tsc failed" >&2; exit 1; }
	[ ! -e "$1" ] && [ ! -L "$1" ] || { echo "rp2350js: $1 exists" >&2; exit 1; }
	mkdir -p "$1/dist" "$1/node_modules"
	cp -r "$WORK/rpjs-src/dist/cjs" "$1/dist/cjs" &&
		cp -r "$WORK/rpjs-src/node_modules/uf2" "$1/node_modules/uf2" &&
		cp "$WORK/rpjs-src/package.json" "$WORK/rpjs-src/LICENSE" "$1/" ||
		{ echo "rp2350js: cannot assemble $1" >&2; exit 1; }
}

# bootrom_make TS BIN: the 4,096 words of bootrom.ts, little-endian, into BIN (16,384 bytes); non-zero if it cannot.
bootrom_make() {
	python3 -I -c '
import re, struct, sys
w = re.findall(r"0x([0-9a-fA-F]{8})", open(sys.argv[1]).read())
if len(w) != 4096:
    sys.exit("bootrom: %d words, not 4096" % len(w))
open(sys.argv[2], "wb").write(b"".join(struct.pack("<I", int(x, 16)) for x in w))' "$1" "$2"
}

# bootrom_ts: DL/rp2040js/bootrom.ts, fetched if absent and checked against its sha256 (a bad file is deleted, exit 1);
# sets BOOTROM_TS.
bootrom_ts() {
	fetch_sha rp2040js "$BOOTROM_URL" "$BOOTROM_TS_SHA256"
	BOOTROM_TS=$FETCHED
}

# bootrom_check: 0 if BOOTROM_BIN is 16,384 bytes with the pinned sha256 and, when it is there, the cached bootrom.ts has
# its pinned sha256 (an unset pin prints the hash and fails); an absent .bin is "not installed".
bootrom_check() {
	if [ -L "$BOOTROM_BIN" ] || { [ -e "$BOOTROM_BIN" ] && [ ! -f "$BOOTROM_BIN" ]; }; then
		echo "bootrom: $BOOTROM_BIN is a symlink or not a file" >&2
		return 1
	fi
	[ -f "$BOOTROM_BIN" ] || { echo "bootrom: not installed ($BOOTROM_BIN)"; return 0; }
	[ "$(wc -c <"$BOOTROM_BIN")" -eq 16384 ] || { echo "bootrom: $BOOTROM_BIN is not 16384 bytes" >&2; return 1; }
	got=$(sha256sum <"$BOOTROM_BIN" | cut -d' ' -f1)
	[ -n "$BOOTROM_BIN_SHA256" ] || { echo "bootrom: unpinned (BOOTROM_BIN_SHA256=$got)" >&2; return 1; }
	[ "$got" = "$BOOTROM_BIN_SHA256" ] || { echo "bootrom: $BOOTROM_BIN has sha256 $got, pinned $BOOTROM_BIN_SHA256" >&2; return 1; }
	if [ -f "$DL/rp2040js/bootrom.ts" ]; then
		echo "$BOOTROM_TS_SHA256  $DL/rp2040js/bootrom.ts" | sha256sum -c - >/dev/null 2>&1 ||
			{ echo "bootrom: $DL/rp2040js/bootrom.ts does not have the pinned sha256 $BOOTROM_TS_SHA256" >&2; return 1; }
	fi
	echo "bootrom: OK ($BOOTROM_BIN)"
}

# bootrom_install: converts the verified bootrom.ts into the .bin (its directory is created); exit 1 on any failure.
bootrom_install() {
	bootrom_ts
	mkdir -p "$(dirname "$BOOTROM_BIN")"
	bootrom_make "$BOOTROM_TS" "$BOOTROM_BIN.part" || { rm -f "$BOOTROM_BIN.part"; exit 1; }
	mv "$BOOTROM_BIN.part" "$BOOTROM_BIN"
}

verify() {
	case $1 in
	simavr) manifest_verify simavr "$SIMAVR" "$(simavr_pin)" "$(simavr_pin_what)" ;;
	rp2040js) manifest_verify rp2040js "$RP/node_modules" "$(pin rp2040js)" ;;
	qemu-rv | qemu-xt)
		qreg "$1"
		manifest_verify "$1" "$Q_DEST" "$(pin "$1")" ;;
	qemu-arm) manifest_verify qemu-arm "$QEMU_ARM" "$(pin qemu-arm)" ;;
	bootrom) bootrom_check ;;
	rp2350js) manifest_verify rp2350js "$RPJS" "$(pin rp2350js)" ;;
	*) echo "$1: unknown name (simavr rp2040js qemu-rv qemu-xt qemu-arm bootrom rp2350js)" >&2; return 2 ;;
	esac
}

adopt() {
	work_ensure
	case $1 in
	qemu-rv | qemu-xt)
		qreg "$1"
		[ -d "$Q_DEST" ] && [ ! -L "$Q_DEST" ] || { echo "$1: not installed, or not a directory ($Q_DEST)" >&2; exit 1; }
		fetch_sha "$1" "$Q_URL" "$Q_SHA" "$Q_LOCAL"
		unpack "$1" "$FETCHED" "$WORK/adopt-qemu"
		a=$WORK/adopt-qemu b=$Q_DEST sha=$Q_SHA mode=exact ;;
	qemu-arm)
		[ -d "$QEMU_ARM" ] && [ ! -L "$QEMU_ARM" ] || { echo "qemu-arm: not installed, or not a directory ($QEMU_ARM)" >&2; exit 1; }
		qemu_arm_unpack "$WORK/adopt-qemu-arm"
		a=$WORK/adopt-qemu-arm b=$QEMU_ARM sha=$QEMU_ARM_SHA256 mode=exact ;;
	rp2040js)
		[ -d "$RP/node_modules" ] && [ ! -L "$RP/node_modules" ] || { echo "rp2040js: not installed, or not a directory ($RP)" >&2; exit 1; }
		# the same layout as PREFIX (rp2040js-1.4.0/ beside dl/), so that npm records the same relative tgz path
		mkdir -p "$WORK/opt/dl/rp2040js"
		[ ! -f "$DL/rp2040js/rp2040js-$RP_VER.tgz" ] || cp "$DL/rp2040js/rp2040js-$RP_VER.tgz" "$WORK/opt/dl/rp2040js/"
		(DL=$WORK/opt/dl install_rp "$WORK/opt/rp2040js-$RP_VER") || exit 1
		a=$WORK/opt/rp2040js-$RP_VER/node_modules b=$RP/node_modules sha=$RP_SHA512 mode=exact ;;
	simavr)
		[ -d "$SIMAVR" ] && [ ! -L "$SIMAVR" ] || { echo "simavr: not installed, or not a directory ($SIMAVR)" >&2; exit 1; }
		build_simavr "$WORK/simavr-rebuilt"
		a=$WORK/simavr-rebuilt b=$SIMAVR sha=$SIMAVR_SHA256 mode=paths ;;
	rp2350js)
		[ -d "$RPJS" ] && [ ! -L "$RPJS" ] || { echo "rp2350js: not installed, or not a directory ($RPJS)" >&2; exit 1; }
		build_rpjs "$WORK/rpjs-fresh"
		a=$WORK/rpjs-fresh b=$RPJS sha=$RPJS_SHA256 mode=exact ;;
	bootrom)
		[ -f "$BOOTROM_BIN" ] && [ ! -L "$BOOTROM_BIN" ] || { echo "bootrom: not installed ($BOOTROM_BIN)" >&2; exit 1; }
		bootrom_ts
		bootrom_make "$BOOTROM_TS" "$WORK/bootrom.bin" || exit 1
		cmp -s "$WORK/bootrom.bin" "$BOOTROM_BIN" || { echo "bootrom: $BOOTROM_BIN differs from a fresh conversion of bootrom.ts" >&2; exit 1; }
		echo "bootrom: $BOOTROM_BIN matches a fresh conversion; BOOTROM_BIN_SHA256=$(sha256sum <"$BOOTROM_BIN" | cut -d' ' -f1)"
		return 0 ;;
	*) echo "$1: unknown name (simavr rp2040js qemu-rv qemu-xt qemu-arm bootrom rp2350js)" >&2; exit 2 ;;
	esac
	rc=0
	adopt_compare "$1" "$a" "$b" "$mode" || rc=$?
	[ $rc -ne 1 ] || exit 1
	[ $rc -eq 0 ] || echo "$1: adopting the installed tree as it is (accidental-drift threat model, see the header)"
	got=$(manifest_write "$1" "$b" "$sha") || exit 1
	[ "$1" != simavr ] || simavr_record "$got"
	echo "$1: adopted $b; manifest pin: MANIFEST_PIN_$(echo "$1" | tr - _)=$got"
}

case $MODE in
verify)
	[ $# -gt 0 ] || set -- simavr rp2040js qemu-rv qemu-xt qemu-arm bootrom rp2350js
	rc=0
	for n in "$@"; do
		verify "$n" || rc=1
	done
	exit $rc ;;
adopt)
	[ $# -eq 1 ] || { echo "usage: $0 --adopt NAME" >&2; exit 2; }
	adopt "$1"
	exit 0 ;;
esac

NAMES=$*
for n in $NAMES; do
	case $n in simavr | rp2040js | qemu-rv | qemu-xt | qemu-arm | bootrom | rp2350js) ;; *) echo "$n: unknown name (simavr rp2040js qemu-rv qemu-xt qemu-arm bootrom rp2350js)" >&2; exit 2 ;; esac
done
# want NAME: 0 if NAME was asked for (no names: every name)
want() {
	[ -z "$NAMES" ] && return 0
	case " $NAMES " in *" $1 "*) return 0 ;; esac
	return 1
}
# dest_ok NAME DIR: a tree in place must be a real directory
dest_ok() { [ -d "$2" ] && [ ! -L "$2" ] || { echo "$1: $2 is a symlink or not a directory" >&2; exit 1; }; }

# simavr: the source archive, verified, built (library and run_avr), installed.
if want simavr; then
	if absent "$SIMAVR"; then
		build_simavr "$SIMAVR"
		[ -f "$SIMAVR/lib/libsimavr.a" ] && [ -f "$SIMAVR/include/simavr/sim_avr.h" ] ||
			{ echo "simavr: install incomplete in $SIMAVR" >&2; exit 1; }
		got=$(manifest_write simavr "$SIMAVR" "$SIMAVR_SHA256") || exit 1
		simavr_record "$got"
	else
		dest_ok simavr "$SIMAVR"
		echo "simavr: present ($SIMAVR)"
		[ -f "$SIMAVR/lib/libsimavr.a" ] && [ -f "$SIMAVR/include/simavr/sim_avr.h" ] ||
			{ echo "simavr: install incomplete in $SIMAVR" >&2; exit 1; }
		if [ -n "$(simavr_pin)" ]; then manifest_verify simavr "$SIMAVR" "$(simavr_pin)" "$(simavr_pin_what)" || exit 1
		else echo "simavr: present, not adopted (sh $0 --adopt simavr)"; fi
	fi
	echo "simavr: $SIMAVR_VER ($SIMAVR)"
fi

# rp2040js: the registry tarball, verified against the pinned integrity, then installed from that file only.
if want rp2040js; then
	if absent "$RP/node_modules"; then
		install_rp "$RP"
		written rp2040js "$RP/node_modules" "$RP_SHA512"
	else
		dest_ok rp2040js "$RP/node_modules"
		echo "rp2040js: present ($RP)"
		present rp2040js "$RP/node_modules"
	fi
	v=$(PATH=$NODE_BIN:$PATH node -p 'require(process.argv[1]).version' "$RP/node_modules/rp2040js/package.json") # the path as an argument, never in the source
	[ "$v" = "$RP_VER" ] || { echo "rp2040js: $RP holds $v, not $RP_VER" >&2; exit 1; }
	echo "rp2040js: $v ($RP)"
fi

# the two QEMU trees
for q in qemu-rv qemu-xt; do
	want "$q" || continue
	qreg "$q"
	if absent "$Q_DEST"; then
		fetch_sha "$q" "$Q_URL" "$Q_SHA" "$Q_LOCAL"
		unpack "$q" "$FETCHED" "$Q_DEST"
		"$Q_DEST/bin/$Q_BIN" --version >/dev/null || { echo "$q: $Q_DEST/bin/$Q_BIN does not run" >&2; exit 1; }
		written "$q" "$Q_DEST" "$Q_SHA"
	else
		dest_ok "$q" "$Q_DEST"
		[ -x "$Q_DEST/bin/$Q_BIN" ] || { echo "$q: $Q_DEST is present but $Q_BIN is missing from it" >&2; exit 1; }
		present "$q" "$Q_DEST"
	fi
	"$Q_DEST/bin/$Q_BIN" --version | head -n 1
done

# qemu-arm: the .deb's usr/ tree, extracted without root
if want qemu-arm; then
	if absent "$QEMU_ARM"; then
		# extracted in the work area and moved into place after the version check: no partial tree at the destination
		work_ensure
		rm -rf "$WORK/unpack-qemu-arm"
		qemu_arm_unpack "$WORK/unpack-qemu-arm"
		"$WORK/unpack-qemu-arm/usr/bin/qemu-system-arm" --version | head -n 1 | grep -q '^QEMU emulator version 8\.2\.2' ||
			{ echo "qemu-arm: the .deb's usr/bin/qemu-system-arm is not QEMU 8.2.2" >&2; exit 1; }
		mv "$WORK/unpack-qemu-arm" "$QEMU_ARM"
		written qemu-arm "$QEMU_ARM" "$QEMU_ARM_SHA256"
	else
		dest_ok qemu-arm "$QEMU_ARM"
		[ -x "$QEMU_ARM/usr/bin/qemu-system-arm" ] ||
			{ echo "qemu-arm: $QEMU_ARM is present but usr/bin/qemu-system-arm is missing from it" >&2; exit 1; }
		present qemu-arm "$QEMU_ARM"
	fi
	"$QEMU_ARM/usr/bin/qemu-system-arm" --version | head -n 1
fi

# the boot ROM: bootrom.ts verified, converted once; the .bin (and the cached .ts) are checked on every run
if want bootrom; then
	[ -e "$BOOTROM_BIN" ] || [ -L "$BOOTROM_BIN" ] || bootrom_install
	bootrom_check || exit 1
fi

# rp2350js: the patched, compiled source archive (build_rpjs), built in the work area and moved into place after a check
# that its entry point loads: no partial tree at the destination
if want rp2350js; then
	if absent "$RPJS"; then
		work_ensure
		build_rpjs "$WORK/rpjs-tree"
		[ "$("$NODE_BIN/node" -p 'typeof require(process.argv[1]).RP2350' "$WORK/rpjs-tree/dist/cjs/index.js")" = function ] ||
			{ echo "rp2350js: the build's dist/cjs/index.js does not export RP2350" >&2; exit 1; }
		mv "$WORK/rpjs-tree" "$RPJS"
		written rp2350js "$RPJS" "$RPJS_SHA256"
	else
		dest_ok rp2350js "$RPJS"
		echo "rp2350js: present ($RPJS)"
		present rp2350js "$RPJS"
	fi
	echo "rp2350js: af0114c ($RPJS)"
fi
