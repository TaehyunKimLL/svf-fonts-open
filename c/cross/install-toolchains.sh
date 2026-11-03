#!/bin/sh
# install-toolchains.sh [PREFIX [NAME...]] - installs the cross toolchains of c/cross/build-all.sh in user space (no sudo).
# OPT=DIR install-toolchains.sh --verify [NAME...] - re-checks what is installed (default: every name).
# OPT=DIR install-toolchains.sh --adopt NAME - writes the first manifest of a tree that is already installed (below).
# Tests: c/cross/test-installers.sh (a manual check, run after a change here; no gate runs it) and, for the manifests,
# c/cross/test-manifest.sh (in c/ports/check/host-checks.sh).
#
# PREFIX (default $OPT, else ~/opt; for --verify and --adopt $OPT, else ~/opt: a PREFIX in the environment is ignored)
# receives one directory a toolchain; downloads go to PREFIX/dl/<name>/ and every tarball is checked against the sha256
# below (the one its publisher lists) before it is unpacked. A toolchain already in place is not replaced. Prints each
# compiler's version. The files it writes are under PREFIX, with these exceptions: git reads the user's git configuration,
# curl and tar their usual state. Work areas (unpack, clone, comparison trees) are PREFIX/.svf-work, removed at exit.
#
# Names: clang arm avr esp xtensa emsdk pico-sdk pico-rv ch583 wchisp sdl3.
#
# Verification. Threat model: accidental drift or corruption of a host-local tree (a stray edit, a truncated copy, a
# half-run upgrade), not an adversary. An install of a tarball writes DEST/.svf-manifest (c/cross/manifest.sh: line 1 the
# archive's sha256, or for ch583 the commit, then every file's sha256, every symlink's target and "exec" lines for the execute bits, relative to
# DEST). The sha256 of that manifest is pinned here (MANIFEST_PIN_<name>, below): --verify checks the manifest against the pin, then the tree against the
# manifest, and names the first difference. A tree with no pin yet is "present, not adopted": --adopt NAME unpacks the
# verified download into a temporary directory, compares it with the installed tree, and only if they agree writes the
# manifest and prints its pin to paste into this script. emsdk and pico-sdk are git clones and carry no file (ch583, a sparse git clone, carries one for EVT/EXAM/SRC only): --verify
# is HEAD == the pinned commit and an empty `git status --porcelain` (no .git hashing: packfiles differ between clones),
# which covers tracked files and untracked files that are not ignored, not ignored files or .git itself.
# A package whose directory is absent is "not installed" (not an error); a present but wrong tree is an error and is
# never replaced by this script.
#
# Pinned releases (c/cross/SIZES.md records the same):
#   clang   LLVM 23.1.3               github.com/llvm/llvm-project release llvmorg-23.1.3
#   arm     Arm GNU Toolchain 15.2.Rel1 (arm-none-eabi)   developer.arm.com
#   avr     avr-gcc 16.1.0 + AVR-LibC 2.3.2 (Zak Kemble build v16.1.0-1)   github.com/ZakKemble/avr-gcc-build
#   esp     riscv32-esp-elf 16.1.0 (Espressif crosstool-NG esp-16.1.0_20260609)   github.com/espressif/crosstool-NG
#   xtensa  xtensa-esp-elf 16.1.0 (the same release), kept under its top directory: PREFIX/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf
#   emsdk   emsdk tag 6.0.13 (emscripten 6.0.13)   github.com/emscripten-core/emsdk; the two archives its install
#           unpacks (node 24.19.0, the emscripten-releases build) are fetched and verified here, not by emsdk
#   pico-sdk  raspberrypi/pico-sdk tag 2.3.1, commit 079c6f39023649b154152db30f1d781e884879bc, no submodule (tinyusb, cyw43,
#           lwip, mbedtls and btstack are not used); the HEAD is checked before anything in the clone is read
#   pico-rv riscv32-pico-elf-gcc 16.1.0, Raspberry Pi's RISC-V toolchain of pico-sdk-tools release v2.3.1-0
#           (github.com/raspberrypi/pico-sdk-tools; sha256 = the digest GitHub lists for the release asset, 129,680,495
#           bytes). The tarball has no top directory (bin/ include/ lib/ libexec/ riscv32-pico-elf/ share/ at its root):
#           it is unpacked as it is into PREFIX/pico-riscv-toolchain-16-v2.3.1-0 (install-lib.sh unpack ... flat).
#           pico-sdk 2.3.1 finds the compiler by its triple under -DPICO_TOOLCHAIN_PATH; it is the toolchain of the real
#           pico2 RISC-V build and accepts -mcpu=hazard3-rp2350 (the ESP gcc does not).
#   ch583   WCH EVT (openwch/ch583) commit bd508ad7ceed48377619837051412a651952857f, a sparse checkout of EVT/EXAM/SRC (plus the
#           root files): PREFIX/ch583-evt. The HEAD is checked before checkout; the manifest of EVT/EXAM/SRC is pinned
#   wchisp  wchisp v0.3.0 (github.com/ch32-rs/wchisp), 883,953 bytes, sha256 computed here (the release lists no digest);
#           one top directory (wchisp-linux-x64/: wchisp, README.md): PREFIX/wchisp-0.3.0/wchisp
#   sdl3    the user's SDL3 fork, a working tree at a path (SDL3_SRC, default ~/opt/src/SDL3), not a URL and no download: its
#           HEAD must be SDL3_COMMIT (7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06, SDL 3.5.0-dev) or the install refuses. The tree is
#           only read (cmake configures out of tree, in PREFIX/.svf-work/sdl3-build); the build installs into PREFIX/sdl3 and
#           writes PREFIX/sdl3/COMMIT (into the staged tree, after the build and install succeed, before it is moved into
#           place). The install also refuses a fork tree with uncommitted changes to tracked files (it prints them): a dirty
#           build must not be recorded as the pinned commit. SDL3_JOBS (default 2) is the build's -j. With no NAMES, sdl3 is
#           installed only when SDL3_SRC is a git tree; otherwise "sdl3: skipped (no fork tree at ...)" and the rest goes on
#           (an explicit sdl3 refuses). --verify proves the record (COMMIT == SDL3_COMMIT and lib/pkgconfig/sdl3.pc exists),
#           not the integrity of the installed files; there is no manifest and --adopt sdl3 is refused.
# DJGPP (i586-pc-msdosdjgpp-gcc) is not installed here and not covered by --verify: build-all.sh expects it in PREFIX/djgpp
# (SIZES.md: provenance).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/manifest.sh"

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
case $PREFIX in /*) ;; *) PREFIX=$(pwd)/$PREFIX ;; esac # absolute: sdl3 bakes it into its install prefix
DL=$PREFIX/dl
. "$HERE/install-lib.sh"

LLVM_VER=23.1.3
LLVM_URL=https://github.com/llvm/llvm-project/releases/download/llvmorg-$LLVM_VER/LLVM-$LLVM_VER-Linux-X64.tar.zst
LLVM_SHA=14d2f701eb68fb799001bdea6231048f3990690fa2f406d563555ff8f744daba

ARM_VER=15.2.rel1
ARM_URL=https://developer.arm.com/-/media/Files/downloads/gnu/$ARM_VER/binrel/arm-gnu-toolchain-$ARM_VER-x86_64-arm-none-eabi.tar.xz
ARM_SHA=597893282ac8c6ab1a4073977f2362990184599643b4c5ee34870a8215783a16

AVR_VER=16.1.0
AVR_URL=https://github.com/ZakKemble/avr-gcc-build/releases/download/v$AVR_VER-1/avr-gcc-$AVR_VER-x64-linux.tar.bz2
AVR_SHA=8621ecc6514df50202b58b23b0f8f72f0e535ec35ee40426194e9a15c57692f6

ESP_REL=esp-16.1.0_20260609
ESP_URL=https://github.com/espressif/crosstool-NG/releases/download/$ESP_REL/riscv32-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz
ESP_SHA=0b029ab31ebc7f74e2c4779077251b21a22cd620669dc4c82e7adc478d403a8d

# The Xtensa tarball's top directory (xtensa-esp-elf/) is kept under its own parent. The installer's own copy of the
# archive (the user's, from 2026-10-20) is DL/xtensa-esp/xtensa-esp-elf.tar.xz; it is used when its sha256 matches.
XT_URL=https://github.com/espressif/crosstool-NG/releases/download/$ESP_REL/xtensa-esp-elf-16.1.0_20260609-x86_64-linux-gnu.tar.xz
XT_SHA=f708752ebb35cab21f184b2574114ed1187619db0edb8a4ba913c06ca2fa675e
XT_LOCAL=$DL/xtensa-esp/xtensa-esp-elf.tar.xz

PICO_TAG=2.3.1
PICO_COMMIT=079c6f39023649b154152db30f1d781e884879bc # the tag's commit: checked before anything in the clone is read
PICO_GIT=${PICO_GIT:-https://github.com/raspberrypi/pico-sdk.git} # the environment overrides it for the installer tests (a local mirror)

EMSDK_TAG=6.0.13
EMSDK_COMMIT=35659964bc2762fffec0d257997fb61475f765b7 # the tag's commit: checked before anything in the clone runs
EMSDK_GIT=https://github.com/emscripten-core/emsdk.git
# What "emsdk install 6.0.13" at that commit unpacks (its emsdk_manifest.json and emscripten-releases-tags.json), at the
# URL emsdk would fetch. node: the sha256 nodejs.org lists in v24.19.0/SHASUMS256.txt (the copy emsdk fetches is
# byte-identical). The releases build: emsdk and Google list no hash, so the sha256 is the one recorded when the
# toolchain of SIZES.md was installed (2026-10-20: a fresh download matched the installed tree file for file).
EM_STORE=https://storage.googleapis.com/webassembly/emscripten-releases-builds
EM_NODE=node-v24.19.0-linux-x64.tar.xz
EM_NODE_SHA=14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647
EM_REL=eb132757325583b787fe9414b09afea9442b72ad
EM_REL_SHA=cda6801012ff3319a539111826ed02a9abd7eff135c2ef261c8941caf5a3763e

PRV_URL=https://github.com/raspberrypi/pico-sdk-tools/releases/download/v2.3.1-0/riscv-toolchain-16-x86_64-lin.tar.gz
PRV_SHA=fc36f1b37f99de54a358115443638023de34e15fe199e718e50cca4d212e7e9f

WCH_URL=https://github.com/ch32-rs/wchisp/releases/download/v0.3.0/wchisp-v0.3.0-linux-x64.tar.gz
WCH_SHA=67e3d4eb0ffd3cc610d8927e3c3f452e2110531a3f14405dcaef87df219f200d # computed; the release lists no digest

CH583_COMMIT=bd508ad7ceed48377619837051412a651952857f # checked before checkout
CH583_GIT=${CH583_GIT:-https://github.com/openwch/ch583.git} # the environment overrides it (a local mirror)

# The sha256 of each tree's DEST/.svf-manifest (printed by the install or by --adopt NAME; paste it here).
MANIFEST_PIN_clang=d92cf9ba79c9d3182d2fc1d4e2da84e8aa4f9264f2c802572769d4274880e7c6
MANIFEST_PIN_arm=6c89a508362d9f50fee71cfadeb5d818eb91d1c9d6cfe23931d2fb3005132495
MANIFEST_PIN_avr=e19de3f41fbb3b9ab65506697e3af7a3c2a1a804c251d691835b791b5b2eaf8a
MANIFEST_PIN_esp=8f76585946974ca6545f1dd71aa42248b94c3e92610b7530e22463f5a1283fa0
MANIFEST_PIN_xtensa=5ad8881a7e12073a3467c4d8b6d73b6c51812117c1132bcd86125eb7124b8252
MANIFEST_PIN_pico_rv=8a3ead20f9c57dd32e7ae5e47f0cc0e5f7d45d9260b514a9708677f566fed1cc
MANIFEST_PIN_ch583=eb4b6904b70321e8b9108f16b7d8e56d85dac17ce1fd49f343e759120ab97d71
MANIFEST_PIN_wchisp=63261f23711c025570efb93a94118f985884da10539013cabc6debd74e1d8a07

SDL3_SRC=${SDL3_SRC:-$HOME/opt/src/SDL3} # the user's fork (a working tree; never modified here)
SDL3_COMMIT=7a588ba6beae4b6f6cc45fdbdca6fd1aea5a2f06 # its HEAD must be this before anything is built

CH583=$PREFIX/ch583-evt
SDL3=$PREFIX/sdl3

# reg NAME: sets R_DEST (the tree), R_BIN (a tool that must run), R_EXE (its path under R_DEST, default bin/R_BIN), R_URL, R_SHA, R_LOCAL, R_FLAT of a tarball toolchain
# (R_FLAT=flat: the tarball has no top directory).
reg() {
	R_LOCAL= R_FLAT=
	R_EXE=
	case $1 in
	clang) R_DEST=$PREFIX/llvm-$LLVM_VER R_BIN=clang R_URL=$LLVM_URL R_SHA=$LLVM_SHA ;;
	arm) R_DEST=$PREFIX/arm-gnu-toolchain-$ARM_VER R_BIN=arm-none-eabi-gcc R_URL=$ARM_URL R_SHA=$ARM_SHA ;;
	avr) R_DEST=$PREFIX/avr-gcc-$AVR_VER R_BIN=avr-gcc R_URL=$AVR_URL R_SHA=$AVR_SHA ;;
	esp) R_DEST=$PREFIX/riscv32-esp-elf-$ESP_REL R_BIN=riscv32-esp-elf-gcc R_URL=$ESP_URL R_SHA=$ESP_SHA ;;
	xtensa)
		R_DEST=$PREFIX/xtensa-esp-elf-$ESP_REL/xtensa-esp-elf R_BIN=xtensa-esp32s3-elf-gcc R_URL=$XT_URL R_SHA=$XT_SHA
		R_LOCAL=$XT_LOCAL ;;
	pico-rv)
		R_DEST=$PREFIX/pico-riscv-toolchain-16-v2.3.1-0 R_BIN=riscv32-pico-elf-gcc R_URL=$PRV_URL R_SHA=$PRV_SHA
		R_FLAT=flat ;;
	wchisp) R_DEST=$PREFIX/wchisp-0.3.0 R_BIN=wchisp R_EXE=wchisp R_URL=$WCH_URL R_SHA=$WCH_SHA ;;
	*) echo "$1: not a tarball toolchain" >&2; exit 2 ;;
	esac
	[ -n "$R_EXE" ] || R_EXE=bin/$R_BIN
}

# tool NAME: installs the tarball toolchain NAME unless its destination exists; a tree in place is verified against its
# pin (or reported as not adopted when it has none yet); a fresh install writes its manifest and checks/prints the pin.
tool() {
	reg "$1"
	if absent "$R_DEST"; then
		fetch_sha "$1" "$R_URL" "$R_SHA" "$R_LOCAL"
		unpack "$1" "$FETCHED" "$R_DEST" "$R_FLAT"
		"$R_DEST/$R_EXE" --version >/dev/null || { echo "$1: $R_DEST/$R_EXE does not run" >&2; exit 1; }
		written "$1" "$R_DEST" "$R_SHA"
	else
		[ -d "$R_DEST" ] && [ ! -L "$R_DEST" ] || { echo "$1: $R_DEST is a symlink or not a directory" >&2; exit 1; }
		[ -x "$R_DEST/$R_EXE" ] || { echo "$1: $R_DEST is present but $R_EXE is missing from it" >&2; exit 1; }
		present "$1" "$R_DEST"
	fi
	"$R_DEST/$R_EXE" --version | head -n 1
}

# adopt NAME: the first manifest of an installed tarball tree. The download (verified) is unpacked into the work area and
# listed beside the installed tree; only when the two lists agree is the manifest written.
adopt() {
	reg "$1"
	[ -d "$R_DEST" ] && [ ! -L "$R_DEST" ] || { echo "$1: not installed, or not a directory ($R_DEST)" >&2; exit 1; }
	fetch_sha "$1" "$R_URL" "$R_SHA" "$R_LOCAL"
	work_ensure
	unpack "$1" "$FETCHED" "$WORK/adopt-tree" "$R_FLAT"
	adopt_compare "$1" "$WORK/adopt-tree" "$R_DEST" exact || exit 1
	got=$(manifest_write "$1" "$R_DEST" "$R_SHA") || exit 1
	echo "$1: adopted $R_DEST; manifest pin: MANIFEST_PIN_$(echo "$1" | tr - _)=$got"
}

# verify NAME: one name of --verify; 1 on a failure.
verify() {
	case $1 in
	clang | arm | avr | esp | xtensa | pico-rv | wchisp)
		reg "$1"
		manifest_verify "$1" "$R_DEST" "$(pin "$1")" ;;
	emsdk) verify_git emsdk "$PREFIX/emsdk" "$EMSDK_COMMIT" ;;
	pico-sdk) verify_git pico-sdk "$PREFIX/pico-sdk-$PICO_TAG" "$PICO_COMMIT" ;;
	ch583) verify_ch583 ;;
	sdl3) verify_sdl3 ;;
	*) echo "$1: unknown name (clang arm avr esp xtensa emsdk pico-sdk pico-rv ch583 wchisp sdl3)" >&2; return 2 ;;
	esac
}
# verify_sdl3: "not installed" (0) only for an absent directory; otherwise COMMIT is SDL3_COMMIT and sdl3.pc exists.
verify_sdl3() {
	if absent "$SDL3"; then
		echo "sdl3: not installed ($SDL3)"
		return 0
	fi
	[ -d "$SDL3" ] && [ ! -L "$SDL3" ] || { echo "sdl3: $SDL3 is a symlink or not a directory" >&2; return 1; }
	got=$(cat "$SDL3/COMMIT" 2>/dev/null) || got=
	[ "$got" = "$SDL3_COMMIT" ] || { echo "sdl3: $SDL3/COMMIT is '$got', not $SDL3_COMMIT" >&2; return 1; }
	[ -f "$SDL3/lib/pkgconfig/sdl3.pc" ] || { echo "sdl3: $SDL3/lib/pkgconfig/sdl3.pc is missing" >&2; return 1; }
	echo "sdl3: OK $SDL3_COMMIT ($SDL3)"
}
# verify_ch583: the git-clone rule plus the manifest of EVT/EXAM/SRC against its pin.
verify_ch583() {
	if absent "$CH583"; then
		echo "ch583: not installed ($CH583)"
		return 0
	fi
	git_clean "$CH583" ch583 "$CH583_COMMIT" && ch583_src_present &&
		manifest_verify ch583 "$CH583/EVT/EXAM/SRC" "$(pin ch583)" &&
		echo "ch583: clone at $CH583_COMMIT, clean"
}
# ch583_src_present: a clone that exists must have EVT/EXAM/SRC (a sparse selection that left it out is an error;
# manifest_verify alone would call the absent directory "not installed").
ch583_src_present() {
	[ -d "$CH583/EVT/EXAM/SRC" ] && [ ! -L "$CH583/EVT/EXAM/SRC" ] ||
		{ echo "ch583: $CH583 is present but EVT/EXAM/SRC is missing from it" >&2; return 1; }
}
# verify_git NAME DIR COMMIT: "not installed" (0) only for an absent path; otherwise the git-clone rule.
verify_git() {
	if absent "$2"; then
		echo "$1: not installed ($2)"
		return 0
	fi
	git_clean "$2" "$1" "$3" && echo "$1: OK ($2 at $3, clean)"
}

case $MODE in
verify)
	[ $# -gt 0 ] || set -- clang arm avr esp xtensa emsdk pico-sdk pico-rv ch583 wchisp sdl3
	rc=0
	for n in "$@"; do
		verify "$n" || rc=1
	done
	exit $rc ;;
adopt)
	[ $# -eq 1 ] || { echo "usage: $0 --adopt NAME" >&2; exit 2; }
	case $1 in
	clang | arm | avr | esp | xtensa | pico-rv | wchisp) adopt "$1" ;;
	sdl3) echo "sdl3: cannot be adopted (no manifest; --verify checks COMMIT and lib/pkgconfig/sdl3.pc)" >&2; exit 2 ;;
	ch583) echo "ch583: cannot be adopted (its manifest is written by the install and pinned in this script; --verify checks it)" >&2; exit 2 ;;
	*) echo "$1: git clones have no manifest (--verify checks HEAD and git status)" >&2; exit 2 ;;
	esac
	exit 0 ;;
esac

# want NAME: 0 if NAME was asked for (no names: every name)
want() {
	[ $# -eq 1 ] || return 1
	[ -z "$NAMES" ] && return 0
	case " $NAMES " in *" $1 "*) return 0 ;; esac
	return 1
}
NAMES=$*
for n in $NAMES; do
	case $n in clang | arm | avr | esp | xtensa | emsdk | pico-sdk | pico-rv | ch583 | wchisp | sdl3) ;; *) echo "$n: unknown name (clang arm avr esp xtensa emsdk pico-sdk pico-rv ch583 wchisp sdl3)" >&2; exit 2 ;; esac
done

for t in clang arm avr esp xtensa pico-rv wchisp; do
	! want "$t" || tool "$t"
done

# pico-sdk: a shallow clone of the tag into the work area, moved into place only when its HEAD is PICO_COMMIT (checked
# before anything in it is read; the tag, when the clone has it, must name the same commit). No submodule, and no file is
# added to the working tree: --verify is HEAD plus an empty git status. A failed clone leaves nothing behind.
PICO=$PREFIX/pico-sdk-$PICO_TAG
if want pico-sdk; then
	if absent "$PICO"; then
		work_ensure
		ptmp=$WORK/pico-sdk
		git clone --quiet --branch "$PICO_TAG" --depth 1 "$PICO_GIT" "$ptmp"
		git_clean "$ptmp" pico-sdk "$PICO_COMMIT" || exit 1
		tagc=$(git -C "$ptmp" rev-parse -q --verify "refs/tags/$PICO_TAG^{commit}" || true)
		[ -z "$tagc" ] || [ "$tagc" = "$PICO_COMMIT" ] || { echo "pico-sdk: tag $PICO_TAG names $tagc" >&2; exit 1; }
		mv "$ptmp" "$PICO"
	else
		git_clean "$PICO" pico-sdk "$PICO_COMMIT" || exit 1
	fi
	echo "pico-sdk: $PICO_TAG $(git -C "$PICO" rev-parse HEAD)"
fi

# ch583: WCH's EVT (openwch/ch583), only EVT/EXAM/SRC, fetched by commit into the work area; its HEAD must be CH583_COMMIT
# before checkout. The manifest of EVT/EXAM/SRC (excluded from git status) is the pinned part; --verify is the git-clone
# rule plus that manifest. A failed fetch leaves nothing behind.
if want ch583; then
	if absent "$CH583"; then
		work_ensure
		ctmp=$WORK/ch583
		mkdir "$ctmp"
		git -C "$ctmp" init -q
		git -C "$ctmp" remote add origin "$CH583_GIT"
		git -C "$ctmp" sparse-checkout set EVT/EXAM/SRC
		git -C "$ctmp" fetch -q --depth 1 --filter=blob:none origin "$CH583_COMMIT"
		fh=$(git -C "$ctmp" rev-parse FETCH_HEAD)
		[ "$fh" = "$CH583_COMMIT" ] || { echo "ch583: fetched $fh, not $CH583_COMMIT" >&2; exit 1; }
		git -C "$ctmp" -c advice.detachedHead=false checkout -q FETCH_HEAD
		echo /EVT/EXAM/SRC/.svf-manifest >>"$ctmp/.git/info/exclude"
		git_clean "$ctmp" ch583 "$CH583_COMMIT" || exit 1
		mv "$ctmp" "$CH583"
		written ch583 "$CH583/EVT/EXAM/SRC" "$CH583_COMMIT"
	else
		git_clean "$CH583" ch583 "$CH583_COMMIT" || exit 1
		ch583_src_present || exit 1
		manifest_verify ch583 "$CH583/EVT/EXAM/SRC" "$(pin ch583)" || exit 1
	fi
	echo "ch583: $(git -C "$CH583" rev-parse HEAD)"
fi

# emsdk: the git repository at the pinned tag, whose commit must be EMSDK_COMMIT before anything in it runs. emsdk
# checks no hash of what it downloads, so it downloads nothing: the two archives its install unpacks are fetched and
# verified here (fetch_sha), copied to the names emsdk gives them in PREFIX/emsdk/downloads/, and "emsdk install" runs with
# EMSDK_KEEP_DOWNLOADS=1, under which emsdk uses an archive already there instead of downloading it. Both copies are
# verified again after the install, before anything unpacked runs (activate, emcc); a mismatch removes what was
# unpacked. "activate" writes PREFIX/emsdk/.emscripten only (no shell profile). The verify rule is the git-clone rule.
EM=$PREFIX/emsdk
emsdk_pinned() {
	head=$(git -C "$EM" rev-parse HEAD) || exit 1
	[ "$head" = "$EMSDK_COMMIT" ] || { echo "emsdk: $EM is at $head, not $EMSDK_COMMIT (tag $EMSDK_TAG)" >&2; exit 1; }
}
# emsdk_archives_ok: 0 if both archives in EM/downloads/ have their pinned sha256.
emsdk_archives_ok() {
	printf '%s  %s\n%s  %s\n' "$EM_NODE_SHA" "$EM/downloads/$EM_NODE" "$EM_REL_SHA" \
		"$EM/downloads/$EM_REL-wasm-binaries.tar.xz" | sha256sum -c - >/dev/null
}
if want emsdk; then
	if [ -x "$EM/upstream/emscripten/emcc" ]; then
		echo "emsdk: present ($EM)"
		git_clean "$EM" emsdk "$EMSDK_COMMIT" || exit 1
	else
		[ -d "$EM/.git" ] || git clone --quiet "$EMSDK_GIT" "$EM"
		git -C "$EM" fetch --quiet --tags
		git -C "$EM" -c advice.detachedHead=false checkout --quiet "$EMSDK_COMMIT"
		emsdk_pinned
		grep -q "\"$EMSDK_TAG\": \"$EM_REL\"" "$EM/emscripten-releases-tags.json" ||
			{ echo "emsdk: tag $EMSDK_TAG does not name releases build $EM_REL" >&2; exit 1; }
		fetch_sha emsdk "$EM_STORE/deps/$EM_NODE" "$EM_NODE_SHA"
		node_dl=$FETCHED
		fetch_sha emsdk "$EM_STORE/linux/$EM_REL/wasm-binaries.tar.xz" "$EM_REL_SHA"
		mkdir -p "$EM/downloads"
		cp "$node_dl" "$EM/downloads/$EM_NODE"
		cp "$FETCHED" "$EM/downloads/$EM_REL-wasm-binaries.tar.xz"
		emsdk_archives_ok || { echo "emsdk: copied archives fail their sha256" >&2; exit 1; }
		EMSDK_KEEP_DOWNLOADS=1 "$EM/emsdk" install "$EMSDK_TAG"
		if ! emsdk_archives_ok; then
			rm -rf "$EM/upstream" "$EM/node"
			echo "emsdk: an archive changed during install (unpacked trees removed)" >&2
			exit 1
		fi
		rm -f "$EM/downloads/$EM_NODE" "$EM/downloads/$EM_REL-wasm-binaries.tar.xz" # verified copies stay in DL/emsdk
		"$EM/emsdk" activate "$EMSDK_TAG"
	fi
	echo "emsdk: $(git -C "$EM" describe --tags) $(git -C "$EM" rev-parse HEAD)"
	EM_CONFIG=$EM/.emscripten "$EM/upstream/emscripten/emcc" --version | head -n 1
fi

# sdl3: the user's SDL3 fork, built from the working tree at SDL3_SRC (read only: cmake configures out of tree into the
# work area) into PREFIX/sdl3; its HEAD must be SDL3_COMMIT and its tracked files clean (and no untracked file under src include cmake CMakeLists.txt). COMMIT is written into the stage
# after the build and install, so a failed build leaves no sdl3. A tree in place is not replaced (verified only). Audio,
# joystick, haptic, camera, sensor and GPU are off (the spec).
sdl3_tree() { [ -d "$SDL3_SRC/.git" ] || [ -f "$SDL3_SRC/.git" ]; }
if want sdl3 && [ -z "$NAMES" ] && absent "$SDL3" && ! sdl3_tree; then
	echo "sdl3: skipped (no fork tree at $SDL3_SRC)"
elif want sdl3; then
	if absent "$SDL3"; then
		sdl3_tree || { echo "sdl3: the fork tree is not at $SDL3_SRC (the user's SDL3 fork; no download)" >&2; exit 1; }
		head=$(git -C "$SDL3_SRC" rev-parse HEAD) || exit 1
		[ "$head" = "$SDL3_COMMIT" ] ||
			{ echo "sdl3: $SDL3_SRC is at $head, not $SDL3_COMMIT (the pin); not building" >&2; exit 1; }
		# --no-optional-locks: no index refresh in the user's tree. Tracked changes and untracked files under the paths the
		# build globs would be built but recorded as the pinned commit.
		dirty=$(git --no-optional-locks -C "$SDL3_SRC" status --porcelain --untracked-files=no) || exit 1
		[ -z "$dirty" ] || { echo "sdl3: $SDL3_SRC has uncommitted changes to tracked files; not building:" >&2; echo "$dirty" >&2; exit 1; }
		dirty=$(git --no-optional-locks -C "$SDL3_SRC" ls-files --others --exclude-standard -- src include cmake CMakeLists.txt) || exit 1
		[ -z "$dirty" ] || { echo "sdl3: $SDL3_SRC has untracked files under src include cmake CMakeLists.txt; not building:" >&2; echo "$dirty" >&2; exit 1; }
		work_ensure
		sb=$WORK/sdl3-build
		stage=$WORK/sdl3-stage
		cmake -S "$SDL3_SRC" -B "$sb" -DCMAKE_BUILD_TYPE=Release -DSDL_SHARED=ON -DSDL_STATIC=ON -DSDL_TESTS=OFF \
			-DSDL_EXAMPLES=OFF -DSDL_AUDIO=OFF -DSDL_JOYSTICK=OFF -DSDL_HAPTIC=OFF -DSDL_CAMERA=OFF -DSDL_SENSOR=OFF \
			-DSDL_GPU=OFF -DSDL_WAYLAND=OFF -DSDL_X11_XTEST=OFF -DCMAKE_INSTALL_PREFIX="$SDL3"
		cmake --build "$sb" -j "${SDL3_JOBS:-2}"
		DESTDIR=$stage cmake --install "$sb" >/dev/null
		echo "$SDL3_COMMIT" >"$stage$SDL3/COMMIT"
		mv "$stage$SDL3" "$SDL3"
	else
		echo "sdl3: present ($SDL3), not replaced"
	fi
	verify_sdl3 || exit 1
	PKG_CONFIG_PATH=$SDL3/lib/pkgconfig pkg-config --modversion sdl3
fi
