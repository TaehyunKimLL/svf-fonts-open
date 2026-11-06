#!/bin/bash
# build-appimage.sh [--release]: the whole local build, from the checkout root:
#   the frozen sidecar (maker/build-sidecar.sh, frozen test included, 0 skips), THIRD-PARTY.txt (fail closed), the
#   AppImage through electron-builder, then desktop/build/release-check.sh on the result.
# --release adds the D8 sources gate (desktop/build/out/sources/MANIFEST.json must be complete).
#
# The AppImage toolset: electron-builder copies six old libraries (appindicator, gconf, indicator, notify, Xss, Xtst)
# into the AppImage's usr/lib. libindicator is GPL-3.0 (forbidden by the generator, spec 8.10) and both the legacy
# appimage-12.0.1 and the newer 1.0.2/1.0.3 toolsets carry it, so the build points electron-builder at a copy of the
# legacy toolset (APPIMAGE_TOOLS_PATH, its documented override) without libindicator and without libappindicator, which
# cannot load without it (prune-appimage-toolset.py, driven by appimage-toolset.json with the sha256 of the downloaded
# archive and of each removed file). The app has no tray icon; nothing else changes. Ruling of the controller, plan issue 32.
# Run it under ~/.local/bin/heavy (it takes the browser lock itself for the smoke run).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT"
RELEASE=0
[ "${1:-}" = "--release" ] && RELEASE=1

T=${SVF_DESKTOP_TMP:-$HOME/work/tmp/svf-desktop-build}
mkdir -p "$T"
[ -f "$T/README" ] || echo "made by desktop/build/build-appimage.sh: pip download, PyInstaller work, pruned AppImage toolset, extractions; delete when no build is running" > "$T/README"
T=$(cd "$T" && pwd)
export SVF_DESKTOP_TMP="$T"
START=$(date +%s)

bash maker/build-sidecar.sh

POOL="$HOME/.cache/electron-builder/appimage-12.0.1"
find_tool() { ls -d "$POOL"/appimage-12.0.1-*/ 2>/dev/null | head -1; }
TOOL=$(find_tool)
if [ -z "$TOOL" ]; then            # fetch the legacy toolset once, with a throw-away build
    (cd desktop && npx electron-builder --linux AppImage --publish never >/dev/null 2>&1 || true; rm -rf dist)
    TOOL=$(find_tool)
fi
[ -n "$TOOL" ] || { echo "build-appimage: the appimage-12.0.1 toolset is not in $POOL" >&2; exit 1; }
python3 desktop/build/prune-appimage-toolset.py "$TOOL" "$POOL/appimage-12.0.1.7z" "$T/appimage-tools"
export APPIMAGE_TOOLS_PATH="$T/appimage-tools"

SRC=()
[ "$RELEASE" = 1 ] && SRC=(--sources desktop/build/out/sources)
node desktop/build/third-party.mjs --sidecar desktop/build/out/sidecar/svf-maker-sidecar --provenance desktop/build/out/sidecar-provenance.json \
    --electron desktop/node_modules/electron/dist --usrlib "$T/appimage-tools/lib/x64" --pysite "$T/pysite" --repo desktop/build/out/repo \
    --meta . --toolset-record desktop/build/appimage-toolset.json --out desktop/build/out/THIRD-PARTY.txt "${SRC[@]}"

VERSION=$(node -p "require('./desktop/package.json').version")
(cd desktop && rm -rf dist && npx electron-builder --linux AppImage --publish never)
APP="desktop/dist/svf-maker-$VERSION.AppImage"
echo "build-appimage: $(( $(date +%s) - START )) s to the AppImage ($(du -m "$APP" | cut -f1) MB, linux-unpacked $(du -sm desktop/dist/linux-unpacked | cut -f1) MB)"

bash desktop/build/release-check.sh "$APP" $([ "$RELEASE" = 1 ] && echo --release)
