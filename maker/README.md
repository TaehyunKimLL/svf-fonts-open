# SVF maker

The maker turns uploaded fonts (TTF/OTF/TTC, variable fonts, Mac fonts, BDF/PCF, DOS Johab raw fonts, SVF files) into
SVFN v3 faces with the repository's tools and a page that previews every result in the browser. It listens on
127.0.0.1 only and keeps its jobs under a data directory.

## Run it

    SVF_MAKER_REPO=$PWD SVF_MAKER_DATA=$(mktemp -d) SVF_MAKER_BIND=127.0.0.1:8766 python3 -P maker/server.py

`SVF_MAKER_REPO` is the checkout (its `tools/` and `svf/` are used), `SVF_MAKER_DATA` the job store, `SVF_MAKER_BIND`
`host:port` (default 127.0.0.1:8766). Open `http://127.0.0.1:8766/`.

## The preview module

The page draws faces with the C renderer built to WebAssembly. Build it once (needs emsdk, default `~/opt/emsdk`, or
set `EMSDK`):

    bash maker/build-wasm.sh

It writes `maker/static/wasm/svf.js` and `svf.wasm` (git-ignored; `SVF_WASM_OUT` overrides the folder) with the compile
line of `c/ports/web/emcc-flags.sh`, the same as `web/build.sh`. Without the module the page says "preview module not
built: run maker/build-wasm.sh" and every preview cell shows that text; nothing else breaks.

## Optional environment

- `JAMOSET_PYLIB` - the folder holding freetype-py and uharfbuzz, for the `mask fit` route and `binarize mono`
  (without them those are not offered).
- `SVF_RECOG_DIR` - a folder with `recog.py` and its weights (numpy and torch needed) for the piece identity check of
  a jamo set. Scoring only: no recogniser or weights are in this repository, and without the folder the page says the
  check is unavailable.

## Tests

    ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'     # the maker suite
    ~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py   # the module and the picker
    python3 maker/test/smoke_dom.py                                                  # the page in headless Chrome

The page tests (`test_page_dom.py`, `smoke_dom.py`) need google-chrome or chromium-browser and the built module and
skip without them. `docs/maker-audit.md` records the design state and the gap list.
