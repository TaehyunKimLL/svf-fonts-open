# SVF maker

The maker turns uploaded fonts (TTF/OTF/TTC, variable fonts, Mac fonts, BDF/PCF, DOS Johab raw fonts, SVF files) into
SVFN v3 faces with the repository's tools and a page that previews every result in the browser. It listens on
127.0.0.1 only and keeps its jobs under a data directory.

## Run it

    SVF_MAKER_REPO=$PWD SVF_MAKER_DATA=$(mktemp -d) SVF_MAKER_BIND=127.0.0.1:8766 python3 -P maker/server.py

`SVF_MAKER_REPO` is the checkout (its `tools/` and `svf/` are used), `SVF_MAKER_DATA` the job store, `SVF_MAKER_BIND`
`host:port` (default 127.0.0.1:8766). Open `http://127.0.0.1:8766/`.

## Token and loopback

`SVF_MAKER_TOKEN` (32 lower-case hex characters, a fresh one per launch) switches on local mode. With it set, every
`/api/` request must carry exactly one `X-Maker-Token` header with that value (else 403), every request (the page and
`/static/*` too) must name this server in its `Host` header, and the server binds `127.0.0.1` or `::1` only: a
`SVF_MAKER_BIND` that is not loopback is refused and the process exits 2 (a bad token also exits 2; the token is never
printed). The page is served with a Content-Security-Policy that allows only its own origin. Without the token the
maker behaves as before.

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

## Notes

- `GET /api/caps` is served and tested but the page does not call it yet: it learns what is missing from the notices
  (the module, the libraries, the recogniser) and from `mask_ok` on the font entries. It is for a shell that wants to
  show the capabilities up front.
- The server still renders a PNG for baked sources (a DOS raw or SVF entry) into `work/preview/<font>.png`. The page no
  longer shows it (it draws the baked face with WASM); it stays because `test_preview.py` and the source-PNG route use it
  as the byte oracle's image form. Nothing else depends on it.
- Stopping the server (SIGTERM, SIGINT or exit) cancels the running job and kills its tool processes (each runs in its
  own session); a queued job stays queued and is re-queued at the next start.

## What has not been run

- **The `mask fit` route has never run a job**: it needs freetype-py and uharfbuzz (`JAMOSET_PYLIB`), which are not installed
  on the host this was built on. Its argv, its offering and its refusals are tested; its result is not.
- **No real recogniser has been run** for the identity check; the tests use a stub that reads syllables from a file. The
  numpy/torch path is unverified.
- **The `vector fit` takes minutes per font**: `jamovec.py master` on NanumGothic Regular measured 172 s under the OOM
  guard (the render is under a second); on the synthetic test font the whole job takes 1.1 s.

## Tests

    ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'     # the maker suite
    ~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py   # the module and the picker
    python3 maker/test/smoke_dom.py                                                  # the page in headless Chrome

The page tests (`test_page_dom.py`, `smoke_dom.py`) need google-chrome or chromium-browser and the built module and
skip without them. `docs/maker-audit.md` records the design state and the gap list.
