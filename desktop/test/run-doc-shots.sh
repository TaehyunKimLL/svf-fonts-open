#!/bin/bash
# run-doc-shots.sh: the documentation screenshots (test/doc-shots.js) under xvfb, into docs/images/maker/.
# TMP_DIR (scratch, not under /tmp) defaults to ~/work/tmp/svf-doc-shots; SHOT_DIR overrides the output folder.
# Needs node_modules/.bin/electron (npm ci), Pillow for python3 and maker/static/wasm/ (bash maker/build-wasm.sh).
cd "$(dirname "$0")/.."
if ! command -v xvfb-run >/dev/null 2>&1; then echo "run-doc-shots.sh: xvfb-run is not installed" >&2; exit 2; fi
if [ ! -x node_modules/.bin/electron ]; then echo "run-doc-shots.sh: node_modules/.bin/electron is missing (npm ci; node node_modules/electron/install.js)" >&2; exit 2; fi
if [ ! -f ../maker/static/wasm/svf.wasm ]; then echo "run-doc-shots.sh: maker/static/wasm/svf.wasm is missing (bash maker/build-wasm.sh)" >&2; exit 2; fi
export TMP_DIR="${TMP_DIR:-$HOME/work/tmp/svf-doc-shots}"
mkdir -p "$TMP_DIR"
export TMPDIR="$TMP_DIR"
exec xvfb-run -a -s "-screen 0 1280x1024x24" node_modules/.bin/electron --no-sandbox --disable-gpu test/doc-shots.js
