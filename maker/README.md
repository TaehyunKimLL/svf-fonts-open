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

## Local mode (desktop app)

With the token set (above) the maker reads fonts **where they are** and writes the faces only into an output folder the
user picked. Nothing is uploaded, nothing is copied into the data directory, no zip is made. The desktop app drives it:

- `POST /api/jobs {"source": "local", "output_dir": "/abs/folder"}` creates the job (403 without the token);
  `PUT /api/jobs/<id>/sources {"paths": [...]}` gives it the files or folders to read (each is checked: absolute, not a
  link, not the data folder, not overlapping the output folder or another input; an optional `SVF_MAKER_ROOTS`
  allow-list limits them further); then the usual `POST detect`, `PUT settings`, `POST run`. A picked path is read in
  place; an archive is listed, not unpacked.
- A run writes `svf/<dest>/<NAME>.SVF` and its note (and a licence text when one was chosen) and `build-<id>/`
  (`BUILD.md`, `LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`) into the output folder, and nothing else.
  A name the job did not write itself is never replaced. While a job lives, the files the conversion needs on the way
  are kept in `.svf-maker-<id>/` inside the output folder (mode 0700) and removed when the job ends, is deleted or
  the server stops; choose a folder that is not synced.
- A licence is **optional**: when none is chosen the note and `BUILD.md` say "licence: not checked (user's
  responsibility)". Converting a font you have no right to convert is your own responsibility; if you publish a result,
  check the font's licence. The page asks you to acknowledge this once per session.
- What it reads besides the usual kinds: classic Mac **HangulTalk 7.1 type-3 `fbit`** fonts (a resource fork, an
  AppleDouble `._Name`, a MacBinary `.bin`, a JM archive, a raw `fbit` resource) with their **HTBL 1** table
  (`InputBackSupport` or `<Name>.htbl1`, picked as another source) and an optional Latin suitcase (FOND + NFNT),
  through `macfbit_svf.py` (direct or derived) or `macfbit3.py bdf` + `mkfont.py`; and **HangulTalk 1.0** fonts (the
  fork with its `fdef`) through `jamoset.py --layout mac-fbit-45sets`. A raw 1.0 `fbit` resource without its `fdef` is
  listed with what is missing. HWP: HANGUL*.PFT is not read; ASCII.PFT is a companion (a 12x24 English font) for a
  24 px DOS raw face, from any folder of the batch. A licence file next to a font picked as a single file is used only
  when it is picked too (or the folder is chosen).
- **No proprietary font is distributed**: no proprietary font, bitmap or table is in this repository or in the maker.
  The tests build synthetic inputs; checks on real files run only where an environment variable names your own copy
  (`SVF_MAKER_REAL_MAC1`, `_MAC3`, `_NAMEDFORK`, `_PFT`, ...).
- the maker has no code that makes an outbound connection and sends nothing anywhere (no telemetry, no crash upload, no update check). The tests check that the maker's own modules import no network library and that an in-process socket guard sees no connection to anything but 127.0.0.1; they do not see its tool subprocesses. The one optional
  external piece is the identity check: `SVF_RECOG_DIR` names your own `recog.py`, and the no-network tests do not
  cover that external code.

## Desktop app

`desktop/` is an Electron shell around this server: the packaged app starts the frozen sidecar
(`svf-maker-sidecar serve --exit-with-parent=<pid>`, a PyInstaller one-dir bundle of the server and every tool), with
a fresh `SVF_MAKER_TOKEN`, `SVF_MAKER_BIND=127.0.0.1:0` and its own data root `~/.config/svf-maker/maker`; it reads the
port from the stdout line ("svf-maker listening on 127.0.0.1:<port>"), loads `http://127.0.0.1:<port>/`, adds the token
header to `/api/` requests, gives the page `window.svfMaker` (four functions) and stops the sidecar on quit. In the
bundle every tool is the same executable: `svf-maker-sidecar run-tool <name> ...` (`maker/toolrun.py` builds the
argv; source mode still runs `python3 -P tools/<name>.py`). The app makes no network connection: the page's CSP allows
its own origin only, the shell cancels every other request, and the maker has no outbound code (above).

Optional pieces stay outside the bundle: the identity check runs under an interpreter you name with
`SVF_RECOG_PYTHON` (an absolute path; it is probed once at start for numpy, torch, PIL and fontTools) with
`SVF_RECOG_DIR`, and the mask-fit libraries come from `JAMOSET_PYLIB`; the packaged repo tree carries
`maker/*.py` and `tools/*.py` as source for that interpreter.

Build on Linux (the whole sequence, versions and numbers: `docs/maker-desktop.md`): `~/.local/bin/heavy bash
desktop/build/build-appimage.sh` needs emsdk (the WASM module), Python 3.12 with pip, and node 22 with npm. It builds
the frozen sidecar, generates `THIRD-PARTY.txt` and an AppImage, and runs the release check. Windows and macOS packages
are not built or verified: the steps are written down in `docs/maker-desktop.md` and the server is not Windows-ready.

## Optional environment

- `JAMOSET_PYLIB` - the folder holding freetype-py and uharfbuzz, for the `mask fit` route and `binarize mono`
  (without them those are not offered).
- `SVF_RECOG_PYTHON` - the interpreter that runs the identity check when the maker is frozen (see Desktop app).
- `SVF_RECOG_DIR` - a folder with `recog.py` and its weights (numpy and torch needed) for the piece identity check of
  a jamo set. Scoring only: no recogniser or weights are in this repository, and without the folder the page says the
  check is unavailable.

## Notes

- `GET /api/caps` is called by the page once at load, only to learn whether local mode is on (`local`: the sources panel
  instead of the upload panel); what is missing (the module, the libraries, the recogniser) it still learns from the
  notices and from `mask_ok` on the font entries.
- The server still renders a PNG for baked sources (a DOS raw or SVF entry) into `work/preview/<font>.png`. The page no
  longer shows it (it draws the baked face with WASM); it stays because `test_preview.py` and the source-PNG route use it
  as the byte oracle's image form. Nothing else depends on it.
- Stopping the server (SIGTERM, SIGINT or exit) cancels the running job and kills its tool processes (each runs in its
  own session); a queued upload job stays queued and is re-queued at the next start; a queued or running local job is
  marked failed (`interrupted`), because its files directory goes with the process.

## Local mode: for the shell, and what has not been run

The shell (card t_f04f1355) starts the server with `SVF_MAKER_TOKEN` and `SVF_MAKER_BIND=127.0.0.1:0`, reads the port
from the stdout line, loads `http://127.0.0.1:<port>/`, adds `X-Maker-Token` to every `/api/` request, exposes
`window.svfMaker` (`pickFiles`, `pickFolder`, `pickOutputDir`, `openOutputFolder`; the paths are absolute, a cancelled
dialog gives `[]`/`null`, `openOutputFolder` takes no argument) and stops the server with SIGTERM. The full contract and
the evidence for the card's closing measurement are in `docs/maker-audit.md`, section 8. Not verified here: `unshare -rn`,
real Mac/HWP files, macOS named forks, Electron and native dialogs, FAT/exFAT/SMB mounts, disk full, case-insensitive
filesystems and sync clients.

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
