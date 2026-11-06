#!/bin/bash
# release-check.sh APPIMAGE [--release]: checks a built AppImage by extracting it (no FUSE here): one line
# "CHECK <name> ok|FAIL <why>" per check, exit 1 on any FAIL. --release adds the D8 sources gate; without it that check
# is reported as skipped (private build).
# The smoke check takes the host-wide browser lock itself (waiting for it as long as it takes, then 90 s for the run):
# run this script under ~/.local/bin/heavy, never under the lock (that would deadlock it).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
APP=${1:-}
RELEASE=0
[ "${2:-}" = "--release" ] && RELEASE=1
T=${SVF_DESKTOP_TMP:-$HOME/work/tmp/svf-desktop-build}
OUT="$ROOT/desktop/build/out"
FAILED=0
ok()   { echo "CHECK $1 ok${2:+ $2}"; }
fail() { echo "CHECK $1 FAIL $2"; FAILED=1; }

mkdir -p "$T"
[ -f "$T/README" ] || echo "made by desktop/build/release-check.sh: AppImage extractions and comparison builds; delete when no check is running" > "$T/README"

# ---- size -----------------------------------------------------------------------------------------------------------
if [ -z "$APP" ] || [ ! -f "$APP" ]; then
    fail size "no such AppImage: ${APP:-<none>}"
    echo "CHECK extract FAIL nothing to extract"
    exit 1
fi
APP=$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")
SIZE=$(stat -c %s "$APP")
if [ "$SIZE" -le $((170 * 1024 * 1024)) ]; then ok size "AppImage $((SIZE / 1048576)) MB"; else fail size "AppImage $((SIZE / 1048576)) MB > 170 MB"; fi

# ---- extract --------------------------------------------------------------------------------------------------------
X="$T/release-$(date +%s)"
mkdir -p "$X"
if (cd "$X" && "$APP" --appimage-extract >/dev/null 2>&1) && [ -d "$X/squashfs-root" ]; then ok extract "$X/squashfs-root"; else fail extract "--appimage-extract failed"; exit 1; fi
SQ="$X/squashfs-root"
RES="$SQ/resources"
SIDE="$RES/sidecar/svf-maker-sidecar"
SIDE_MB=$(du -sm "$SIDE" 2>/dev/null | cut -f1)
[ "${SIDE_MB:-999}" -le 60 ] && ok size-sidecar "${SIDE_MB} MB" || fail size-sidecar "${SIDE_MB:-?} MB > 60 MB"

# ---- layout (spec 8.4) ----------------------------------------------------------------------------------------------
MISS=""
for p in resources/app.asar resources/sidecar/svf-maker-sidecar/svf-maker-sidecar resources/repo/svf resources/repo/web \
         resources/repo/BUILD_ID resources/repo/tools resources/repo/maker resources/THIRD-PARTY.txt; do
    [ -e "$SQ/$p" ] || MISS="$MISS $p"
done
STRAY=$(find "$RES/repo" \( -name 'test_*.py' -o -name '__pycache__' -o -name testdata \) 2>/dev/null | head -3 | tr '\n' ' ')
if [ -z "$MISS" ] && [ -z "$STRAY" ]; then ok layout; else fail layout "missing:${MISS:- none} stray: ${STRAY:-none}"; fi

# ---- AppRun (electron-builder's, unchanged: D7) ---------------------------------------------------------------------
if grep -q 'unshare -Ur' "$SQ/AppRun" 2>/dev/null && grep -q -- '--no-sandbox' "$SQ/AppRun" 2>/dev/null; then ok apprun "unshare probe and --no-sandbox present"; else fail apprun "AppRun lacks the unshare probe or --no-sandbox (is it electron-builder's own?)"; fi

# ---- the embedded .desktop entry ------------------------------------------------------------------------------------
DESK=$(ls "$SQ"/*.desktop 2>/dev/null | head -1)
EXEC=$(grep '^Exec=' "$DESK" 2>/dev/null | head -1)
if echo "$EXEC" | grep -q 'AppRun'; then ok desktop-entry "$EXEC"; else fail desktop-entry "Exec line lacks AppRun: ${EXEC:-<none>}"; fi

# ---- the frozen test against the extracted sidecar: no failure, no skip ---------------------------------------------
cd "$ROOT"
FROZEN_LOG="$X/frozen.log"
SVF_MAKER_SIDECAR="$SIDE/svf-maker-sidecar" SVF_MAKER_STAGED_REPO="$RES/repo" SVF_MAKER_REF_SITE="$T/pysite" \
    SVF_MAKER_FROZEN_REQUIRED=1 python3 -m unittest discover -s maker/test -p test_frozen.py > "$FROZEN_LOG" 2>&1
if tail -3 "$FROZEN_LOG" | grep -q '^OK' && ! grep -q 'skipped=' "$FROZEN_LOG"; then ok frozen "$(grep '^Ran ' "$FROZEN_LOG")"; else fail frozen "see $FROZEN_LOG"; fi
PILLOW_LINE=$(grep -a 'debian pillow' "$FROZEN_LOG" | tail -1)

# ---- the WASM module equals a fresh build ---------------------------------------------------------------------------
if SVF_WASM_OUT="$T/wasm-cmp" bash maker/build-wasm.sh >/dev/null 2>&1 && cmp -s "$T/wasm-cmp/svf.wasm" "$SIDE/_internal/static/wasm/svf.wasm"; then ok wasm; else fail wasm "svf.wasm differs from a fresh build (or emcc failed)"; fi

# ---- the licence generator over the extraction ----------------------------------------------------------------------
LIC_OUT="$X/THIRD-PARTY.check.txt"
SRC_ARGS=()
[ "$RELEASE" = 1 ] && SRC_ARGS=(--sources "$OUT/sources")
if node desktop/build/third-party.mjs --sidecar "$SIDE" --provenance "$OUT/sidecar-provenance.json" --electron "$SQ" --usrlib "$SQ/usr/lib" \
        --pysite "$T/pysite" --repo "$RES/repo" --meta . --toolset-record desktop/build/appimage-toolset.json --out "$LIC_OUT" "${SRC_ARGS[@]}" 2> "$X/licences.err"; then
    ok licences "$(grep -c '^### ' "$LIC_OUT") components"
    # what the AppImage ships against what it must ship: the notices as regenerated, the tool sources as in the checkout
    while IFS= read -r line; do
        case "$line" in *" ok") ok "${line%% *}" ;; *) fail "${line%% *}" "${line#* FAIL }" ;; esac
    done < <(bash "$ROOT/desktop/build/verify-extraction.sh" "$SQ" "$LIC_OUT" "$ROOT")
else
    fail licences "$(head -3 "$X/licences.err" | tr '\n' ';')"
fi

# ---- smoke: the extracted AppRun, under the browser lock ------------------------------------------------------------
SMOKE_LOG="$X/smoke.log"
UD="$T/release-ud"
rm -rf "$UD"
# the lock first (it may be held for a long time by another run), then the 90 s budget on the Electron run itself
SVF_MAKER_SMOKE=1 SVF_MAKER_SHELL_LOG=stderr flock "$HOME/work/tmp/svf-browser.lock" timeout 90 xvfb-run -a "$SQ/AppRun" --disable-gpu --user-data-dir="$UD" > "$SMOKE_LOG" 2>&1
RC=$?
SHELL_PID=$(sed -n 's/.*shell pid=\([0-9]*\).*/\1/p' "$SMOKE_LOG" | head -1)
SIDE_PID=$(sed -n 's/.*sidecar start mode=packaged pid=\([0-9]*\).*/\1/p' "$SMOKE_LOG" | head -1)
alive() { [ -n "$1" ] && [ -r "/proc/$1/status" ] && ! grep -q '^State:.*[ZX]' "/proc/$1/status"; }
if [ $RC -eq 0 ] && grep -q 'svf-maker smoke ok SVF maker' "$SMOKE_LOG" && grep -q 'sidecar start mode=packaged' "$SMOKE_LOG" \
        && grep -q 'sidecar exit code=0' "$SMOKE_LOG" && ! alive "$SHELL_PID" && ! alive "$SIDE_PID"; then
    ok smoke "$(grep -a -o 'renderer sandbox: .*' "$SMOKE_LOG" | head -1)"
else
    fail smoke "rc=$RC; see $SMOKE_LOG"
fi
SANDBOX_LINE=$(grep -a -o 'renderer sandbox: .*' "$SMOKE_LOG" | head -1)

# ---- sources (D8 release gate) --------------------------------------------------------------------------------------
if [ "$RELEASE" = 1 ]; then
    if grep -q 'corresponding sources archived: YES' "$LIC_OUT" 2>/dev/null; then ok sources "gate YES"; else fail sources "corresponding sources are not archived (desktop/build/out/sources/MANIFEST.json)"; fi
else
    echo "CHECK sources skipped (private build; D8 release gate)"
fi

# ---- contents record ------------------------------------------------------------------------------------------------
BID=$(head -1 "$RES/repo/BUILD_ID" 2>/dev/null | cut -d' ' -f1)
REC="$OUT/release-${BID:-unknown}-$(sha256sum "$APP" | cut -c1-8).txt"       # one record per AppImage, never overwriting another's
{
    echo "AppImage: $APP ($SIZE bytes)"
    echo "BUILD_ID: $(head -1 "$RES/repo/BUILD_ID" 2>/dev/null)"
    echo "desktop entry: $EXEC"
    echo "smoke: ${SANDBOX_LINE:-no sandbox line}"
    echo "mount: not tested (no FUSE on this host); the extracted AppRun was run under xvfb"
    echo "${PILLOW_LINE:-debian pillow: not run}"
    echo "files (size path):"
    (cd "$SQ" && find . -type f -printf '%s %p\n' | sort -k2)
} > "$REC"
ok contents "$REC"
exit $FAILED
