#!/bin/bash
# build-sidecar.sh [--no-test] - builds the frozen maker sidecar from the checkout root (spec 8.3):
#   the WASM preview module, the pinned wheels (pip --target; python3 -m venv does not work on the build host), the
#   PyInstaller one-dir bundle into desktop/build/out/sidecar/, the staged repo tree desktop/build/out/repo/ (svf/,
#   web/ index files, tools/*.py and maker/*.py without tests, BUILD_ID), a selfcheck under `env -i`, and unless
#   --no-test the frozen test (maker/test/test_frozen.py, 0 skipped).
# SVF_DESKTOP_TMP (default $HOME/work/tmp/svf-desktop-build) holds the pip download, PyInstaller's work directory and
# nothing else; keep the path short.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
cd "$ROOT"
NO_TEST=0
[ "${1:-}" = "--no-test" ] && NO_TEST=1

T=${SVF_DESKTOP_TMP:-$HOME/work/tmp/svf-desktop-build}
mkdir -p "$T"
[ -f "$T/README" ] || echo "made by maker/build-sidecar.sh: pip download (pysite/), PyInstaller work directory; delete when no build is running" > "$T/README"
T=$(cd "$T" && pwd)
OUT="$ROOT/desktop/build/out"
START=$(date +%s)

bash maker/build-wasm.sh

REQ=desktop/build/requirements-sidecar.txt
SUM=$(sha256sum "$REQ" | cut -d' ' -f1)
if [ ! -f "$T/pysite/.ok" ] || [ "$(cat "$T/pysite/.ok")" != "$SUM" ]; then
    rm -rf "$T/pysite"
    python3 -m pip install --target "$T/pysite" -r "$REQ"
    echo "$SUM" > "$T/pysite/.ok"
fi

export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
rm -rf "$OUT/sidecar" "$T/pyi-work"
mkdir -p "$OUT"
# no `site`: Debian's dist-packages (wx, setuptools) stay out of the import graph
TMPDIR="$T" PYTHONPATH="$T/pysite" python3 -S -m PyInstaller --noconfirm --clean --workpath "$T/pyi-work" \
    --distpath "$OUT/sidecar" maker/sidecar.spec

# the tree the frozen server and the external recogniser interpreter read (spec 7.5 / 8.4)
rm -rf "$OUT/repo"
mkdir -p "$OUT/repo/web" "$OUT/repo/tools" "$OUT/repo/maker"
cp -r svf "$OUT/repo/svf"
cp web/mkindex.py web/LICENCES.tsv web/FAMILIES.tsv "$OUT/repo/web/"
for f in tools/*.py maker/*.py; do
    case "$(basename "$f")" in test_*) continue ;; esac
    cp "$f" "$OUT/repo/$f"
done
VERSION=$(sed -n 's/^VERSION = "\([^"]*\)".*/\1/p' maker/sidecar.py)
echo "$(git describe --always --dirty) $(git log -1 --format=%cs) sidecar $VERSION" > "$OUT/repo/BUILD_ID"

EXE="$OUT/sidecar/svf-maker-sidecar/svf-maker-sidecar"
env -i "$EXE" selfcheck > "$T/selfcheck.json"
python3 - "$T/selfcheck.json" <<'PY'
import json, sys
info = json.load(open(sys.argv[1]))
bad = {k: v for k, v in info["modules"].items() if v is not None}
print("selfcheck: frozen=%s version=%s modules=%d bad=%s" % (info["frozen"], info["version"], len(info["modules"]), bad))
sys.exit(1 if bad or not info["frozen"] else 0)
PY

if [ "$NO_TEST" = "0" ]; then
    SVF_MAKER_SIDECAR="$EXE" SVF_MAKER_REF_SITE="$T/pysite" SVF_MAKER_STAGED_REPO="$OUT/repo" \
        SVF_MAKER_FROZEN_REQUIRED=1 python3 -m unittest discover -s maker/test -p test_frozen.py
fi
echo "build-sidecar: $(( $(date +%s) - START )) s, $(du -sm "$OUT/sidecar/svf-maker-sidecar" | cut -f1) MB"
