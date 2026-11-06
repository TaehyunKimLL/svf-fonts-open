#!/bin/bash
# run-e2e.sh: the Electron end-to-end test under xvfb (stubbed dialogs). Needs TMP_DIR (scratch, short path).
# Pass 2 (the packaged layout) needs SVF_MAKER_SIDECAR and SVF_MAKER_STAGED_REPO. Run it as
#   flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh
cd "$(dirname "$0")/.."
if [ -z "${TMP_DIR:-}" ]; then echo "run-e2e.sh: TMP_DIR is not set (scratch directory, short path)" >&2; exit 2; fi
mkdir -p "$TMP_DIR"
if ! command -v xvfb-run >/dev/null 2>&1; then echo "SKIP: xvfb-run is not installed"; exit 0; fi
if [ ! -x node_modules/.bin/electron ]; then echo "SKIP: node_modules/.bin/electron is missing (npm ci; node node_modules/electron/install.js)"; exit 0; fi
export TMPDIR="$TMP_DIR"
exec xvfb-run -a node_modules/.bin/electron --no-sandbox --disable-gpu --user-data-dir="$TMP_DIR/e2e-base" test/e2e.js
