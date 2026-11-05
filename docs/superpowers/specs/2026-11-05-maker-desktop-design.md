# SVF maker desktop app: Electron shell and packaging (design)

Cards t_f04f1355 ("maker: Electron shell with the Python sidecar on 127.0.0.1") and t_e64a56a7 ("maker: packaging:
PyInstaller sidecar + Linux AppImage; Windows/macOS build notes"), goal t_afb4689b. Written 2026-11-05 on branch
`desktop` of the OFL-only repository (`svf-fonts-open`, base `1513dd2`) for a builder who has not seen the repository.
Every fact below was read from the tree or run on this host (Ubuntu 24.04, x86_64) unless it says "not verified" or
"UNVERIFIED"; section 4 lists what was run. Where a choice is the owner's I decided for the builder, marked "(design
call)", and collected it again in section 14 ("Decisions needed") with my recommendation. The owner was not available
for questions.

Read with this document: `docs/maker-audit.md` (section 4 "Electron shell with a Python sidecar", section 8 "the shell
contract"), `maker/README.md` ("Token and loopback", "Local mode (desktop app)", "Local mode: for the shell"),
`docs/superpowers/specs/2026-11-04-maker-local-mode-design.md` (sections 10.2-10.6: the token, loopback, the bridge,
SIGTERM), `docs/superpowers/specs/2026-11-03-maker-controls-wasm-preview-design.md` (the WASM preview module and
`maker/build-wasm.sh`), `maker/server.py` (`main`, `make_server`, `_parse_token`), `maker/routes.py` (`PY`, `SRCPREP`,
`source_commands`), `maker/jobs.py` (`run_command`, `_stop`, `Worker.stop`, `_job_env`), `maker/preview.py`
(`run_bounded`, `ENV`), `maker/zipout.py` (`repo_head`, `_note_token`, `_mkindex`), `maker/caps.py`, `NOTICE.md`.

## 1. Intent

The maker is a Python HTTP server (`maker/server.py`) that bakes SVF faces from fonts with the repository's Python
tools (`tools/*.py`) and shows a page that previews every result with the C renderer compiled to WebAssembly. Its
*local mode* (card t_cbd14d61, shipped at `1513dd2`) reads fonts where they are, converts them, writes only into an
output folder the user picked, and is switched on by a per-launch token. It was built for a desktop shell that does not
exist yet: a native window, native file dialogs that hand the server absolute paths, a sidecar process that lives and
dies with the window, and a package a user can download and run without Python, emsdk or a checkout.

This design is that shell and that package: an Electron app whose main process spawns a frozen Python sidecar (the
maker server and every tool in one PyInstaller one-dir bundle), loads the maker's page over `http://127.0.0.1:<port>/`,
adds the token to every API request itself, exposes the four-function bridge `window.svfMaker` to the page, and stops
the sidecar with SIGTERM. The first deliverable is a Linux AppImage; Windows and macOS are documented as unverified
build notes.

## 2. Goals

- One double-clickable Linux AppImage that contains Electron, the frozen sidecar (Python 3.12 + Pillow + fontTools +
  the maker + the tools), the built preview module, the `svf/` faces the maker needs and a generated `THIRD-PARTY`
  licence file; it needs no Python, no git and no network on the user's machine.
- The local-mode contract of `docs/maker-audit.md` section 8 implemented exactly: token in the environment, loopback
  port 0, the stdout handshake, `http://` not `file://`, `X-Maker-Token` added by the shell, `window.svfMaker`
  (`pickFiles`, `pickFolder`, `pickOutputDir`, `openOutputFolder`, `platform`), SIGTERM then wait then kill.
- Every tool launch byte-identical in effect between source mode (`python3 -P tools/X.py`) and frozen mode
  (`<sidecar> run-tool X`): same argv after the launcher prefix, same cwd, same scrubbed environment, same process
  group and cancellation path, same exit codes and stderr, the same command line in the face's note.
- Nothing proprietary leaves the machine and nothing in the shell makes an outbound connection: no update check, no
  crash upload, no telemetry; the shell's own logs hold no input bytes and no request bodies.
- The repository stays OFL-only: the bundle holds only OFL faces and licence texts from `svf/`, and every bundled
  third-party component (Electron and Chromium, CPython, Pillow and its native libraries, fontTools, the npm packages
  that ship in the app) is listed with its licence in a generated `THIRD-PARTY.txt`.
- The existing gates stay green: the maker suite (909 tests at `1513dd2`, "909 tests OK (skipped 14)" per its commit),
  `tools/test_*.py`, `make -C c check`, `c/src` and `c/include` untouched.
- What can be verified on this host is verified by tests that run here (section 10); what cannot is listed, not implied.

## 3. Non-goals

- Porting any tool to JavaScript or Rust (the owner's decision of 2026-11-05: the tools stay Python).
- Auto-update, an update check, crash reporting, analytics, a store listing, code signing and notarization as *done*
  work (section 9.11 documents the steps for Windows and macOS; none is run here).
- A Windows or macOS build run here (no such host; section 9.11 is UNVERIFIED by construction). The server is POSIX-only
  today (`os.killpg`, `start_new_session`; local-mode design section 4): Windows needs server-side work this design
  names but does not do (section 9.11).
- Any change to the page's behaviour, the routes, the tools' pixel rules, `c/src`, the WASM module or the local-mode
  endpoints. The one server-side change is the launcher helper (section 7) plus two small flags (section 7.8, 7.9).
- The tailnet or systemd deployment; a multi-user server; the plain upload mode as a desktop feature (it stays
  available, D10 of the local-mode design, but the shell always runs with the token).
- The jamo recogniser (numpy + torch) inside the bundle (section 8.7 says how the optional recogniser is reached).

## 4. Constraints and facts (checked 2026-11-05 on this host unless marked)

The maker today (`1513dd2`):

- `maker/server.py main()` reads `SVF_MAKER_REPO` (default: the checkout above `maker/`), `SVF_MAKER_DATA` (default
  `~/.local/share/svf-maker`), `SVF_MAKER_BIND` (default `127.0.0.1:8766`; `_bind` turns `host:port` into a pair, no host
  means 127.0.0.1), `SVF_MAKER_TOKEN` (`_parse_token`: `None` when unset or empty; else exactly 32 lower-case hex
  characters or `LocalModeError("SVF_MAKER_TOKEN: 32 hex characters")`, exit 2). `make_server` refuses a non-loopback
  host with the token (`"local mode binds 127.0.0.1 or ::1 only"`, exit 2), sets `os.umask(0o077)`, and the process
  prints exactly one line to stdout, `"svf-maker listening on %s:%d" % server.server_address[:2]`, flushed, after the
  socket is bound (`server.py:1950`). SIGTERM and SIGINT raise `KeyboardInterrupt` in `serve_forever`; `finally` runs
  `worker.stop()` (cancels the running job, kills the tool process groups, waits up to 30 s, sweeps every local job's
  files directory) and `server_close()`; the exit code is 0 (`test_server_signals.py` asserts it and that stderr has no
  traceback). Every `/api/` request needs `X-Maker-Token`; `/` and `/static/*` need only a `Host` naming the server;
  the page is served with `Content-Security-Policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval';
  connect-src 'self'; img-src 'self' blob: data:; font-src 'self'; style-src 'self'` (`server.py CSP`). `GET /api/caps`
  answers `{"wasm", "mask_libs", "recog", "local"}`.
- The server's paths: `repo_dir` = `SVF_MAKER_REPO`; `svf_dir = <repo>/svf` (the `RepoIndex` of every face for the
  name/byte clash rules, the chosen `repo` licence texts, `dos/NEODG16.SVF` as the Latin fallback of previews and as the
  base of the `johab844` route, `settings.py:1468`); `tools_dir = <repo>/tools` (every tool argv); `static_dir =
  <maker/>/static` (`MAKER_DIR` from `server.__file__`, `server.py:12,478`); `<repo>/web/mkindex.py` is loaded by path
  (`zipout._mkindex`) to read `<repo>/web/LICENCES.tsv` (`_existing_globs`; `[]` when unreadable); `zipout.repo_head`
  runs `git -C <repo> rev-parse HEAD` and writes "repo HEAD <sha>" into `BUILD.md` (`"unknown"` without git).
- Every tool launch is `routes.PY = [sys.executable, "-P"]` plus a script path (section 7.3 lists all 29 sites):
  `tools/<name>.py` through `_tool(paths, name)` or `os.path.join(tools_dir, name)`, `maker/srcprep.py` through
  `routes.SRCPREP` (an absolute path from `routes.__file__`), `maker/recog_score.py` through `jobs.py:1497`, and the
  one module launch `PY + ["-m", "fontTools.varLib.instancer", ...]` (`routes.py:386`). `jobs.run_command` and
  `preview.run_bounded` run the argv with `cwd` = the step's or preview's work directory, `env` = `{"PATH", "HOME",
  "LANG": "C.UTF-8"}` (a local job adds `TMPDIR=<files dir>/work/tmp` and `PYTHONDONTWRITEBYTECODE=1`,
  `jobs._job_env`), `stdin=DEVNULL`, `start_new_session=True`; cancellation and timeouts are `os.killpg(SIGTERM)`, wait
  `KILL_GRACE` = 5 s, `os.killpg(SIGKILL)` (`jobs._stop`); `preview.kill_all` SIGKILLs every bounded child at stop.
  `zipout._note_token` writes `python3` for a token equal to `sys.executable` and `tools/<name>` / `maker/<name>` for
  a path under the checkout, so a local job's note reads `python3 -P tools/mkfont.py neodgm.ttf NEODU16.SVF ...`.
- The tools import each other as top-level modules (`import jamoset`, `import mkfont`, ...; each inserts its own
  directory into `sys.path` because `python -I`/`-P` drops it) and have a `main()` (no arguments in `jamoset`, `jamovec`,
  `mkfont`, `bdfface`, `johab844`; `main(argv=None)` in `macsfnt`, `macfbit3`, `macfbit_svf`, `svf2to3`, `svfdy`,
  `svfline`, `srcprep`, `recog_score`), guarded by `if __name__ == "__main__"`. None reads `sys.argv` outside
  argparse. Third-party imports of the modules the maker runs: `fontTools` (mkfont, jamovec, jamoaa, macsfnt, srcprep,
  detect; `fontTools.varLib.instancer` as a module launch; `fontTools.ttLib` loads its table classes by name at run
  time, so a freezer must collect `fontTools.ttLib.tables.*`), `PIL` (mkfont, macfbit_svf, jamofill, detect, preview);
  optional and absent here: `freetype` + `uharfbuzz` (jamofit, for `mask fit` and `binarize mono`, loaded from
  `JAMOSET_PYLIB`), `numpy` + `torch` + the user's `recog.py` (recog_score, jamomerge; `SVF_RECOG_DIR`), `pathops`
  (jamoseg; never launched by the maker). `caps.compute` imports `jamofit` (light) and uses `importlib.util.find_spec`
  for numpy/torch.
- `maker/build-wasm.sh` compiles `c/ports/web/svf_web.c` + `c/src/*.c` with the line of `c/ports/web/emcc-flags.sh`
  into `maker/static/wasm/svf.js` + `svf.wasm` (git-ignored). Run here: 1.3 s, `svf.wasm 39808 bytes, svf.js 6937
  bytes`, emcc 6.0.13 at `~/opt/emsdk/upstream/emscripten/emcc`.
- The page already supports the bridge: `maker.js bridge()` returns `window.svfMaker` when present, hides the
  typed-path fields then, asks for the acknowledgement once per session (`sessionStorage`, `ACK_KEY`), and sends no
  token itself. `maker/test/test_page_dom.py` drives it in headless Chrome through `maker/test/pagedrive.mjs` (DevTools
  protocol over node's WebSocket; `--header NAME:VALUE` plays the shell's header, `--preload FILE` plays the preload
  bridge); `maker/test/smoke_dom.py` is the end-to-end smoke in a browser.
- Sizes in the tree: `tools/` 2.3 MB (with tests), `svf/` 12 MB (faces + licence texts), `maker/static` 164 KB,
  `web/` 372 KB, `svf/dos/NEODG16.SVF` 132 KB. Licences: code MIT (`LICENSE`), faces OFL 1.1 (`NOTICE.md`).

The host and what was run (the "spike" of section 8; its files are under `/tmp` and are not part of the repository):

- Ubuntu 24.04.5, glibc 2.39, node v22.23.4, npm 12.0.2, Python 3.12.3, Pillow 10.2.0 (licence metadata `HPND`),
  fontTools 4.66.1 (MIT), no numpy, no freetype-py, no uharfbuzz, no PyInstaller, no electron, no appimagetool; `Xvfb`
  and `xvfb-run` present; `google-chrome` present; emsdk present (above); `apparmor_restrict_unprivileged_userns = 1`
  (Ubuntu 24.04's default).
- Network: PyPI and GitHub reachable. `python3 -m venv` fails here (no `ensurepip`: python3-venv is not installed), so
  PyInstaller was installed with `python3 -m pip install --target /tmp/pyi-probe/site pyinstaller` -> **PyInstaller
  6.22.3** (bootloader `Linux-64bit-intel`). `npm install electron electron-builder` worked (3 s, 283 packages) ->
  **Electron 45.2.3** (Chromium 156.0.8078.80, Node 24.22.2, MIT) and **electron-builder 26.18.0** (MIT); npm 12 blocked
  Electron's postinstall (`allowScripts`), so the binary was fetched with `node node_modules/electron/install.js` (into
  `~/.cache/electron`, 119 MB). `electron --version` without a display dies with SIGTRAP; under `xvfb-run -a
  electron --no-sandbox` it runs.
- A first PyInstaller one-dir build of a spike entry point (section 7.1's shape, the server and every tool as hidden
  imports, `--collect-submodules fontTools`) was 113 MB and **failed at start**: `pyi_rth_pkgres` -> `ImportError: The
  'jaraco' package is required` (Debian's setuptools `pkg_resources` was pulled in through `fontTools.ui`/wx). A second
  build excluding `wx`, `fontTools.ui`, `brotli`, `zopfli`, `lxml`, `numpy`, `torch`, `tkinter`, `gi`, `PIL.ImageQt`,
  `PIL.ImageTk`, `unicodedata2`, `lz4`, `scipy`, `matplotlib`, `sympy`, `xattr` and collecting only `fontTools.ttLib` and
  `fontTools.pens` (+ `fontTools.varLib.instancer`) built in 6 s and is **47 MB** (libpython 8.7 MB, fontTools 11 MB,
  PIL 0.6 MB + 40 shared libraries: libfreetype, libharfbuzz, libraqm, libjpeg, libtiff, libwebp, libopenjp2, lcms2,
  libcrypto/libssl, libstdc++, ...). Its runtime facts (`sidecar --probe` under `env -i PATH=<empty dir> HOME LANG
  PYTHONPATH=<dir with a planted json.py>`): `sys.flags` has `isolated=1, ignore_environment=1, no_site=1,
  safe_path=True, dont_write_bytecode=1`; `sys.path` is `[_internal/base_library.zip, _internal/python3.12/lib-dynload,
  _internal]` only (the planted `PYTHONPATH` is ignored); run from the planted directory as cwd, the cwd is not on
  `sys.path`; the bootloader adds `LD_LIBRARY_PATH`, `_PYI_ARCHIVE_FILE`, `_PYI_LINUX_PROCESS_NAME`,
  `_PYI_PARENT_PROCESS_LEVEL` to its own environment; the serving process is a single process (no re-exec parent).
  Start-up: `run-tool svfline --help` 0.03 s (three runs), `run-tool mkfont --help` 0.05 s (source `python3 -P
  tools/mkfont.py --help` 0.05 s); `run-tool mkfont neodgm.ttf OUT --size 16 --bpp 1 --unicode ascii,ksx1001-hangul`
  0.30-0.34 s against 0.24 s in source mode (about +0.1 s per launch for the bundle's library loads); the output is
  **byte-identical** (`cmp`, 115,460 bytes). `run-tool srcprep|instancer|jamoset|macfbit_svf --help` all dispatch
  (`usage: srcprep.py`, `usage: fonttools varLib.instancer`, `usage: jamoset.py`, `usage: macfbit_svf.py`).
- The frozen sidecar in `serve` mode under the scrubbed environment with `SVF_MAKER_TOKEN`, `SVF_MAKER_BIND=127.0.0.1:0`,
  `SVF_MAKER_REPO=<this worktree>`, `SVF_MAKER_DATA=<tmp>`: printed `svf-maker listening on 127.0.0.1:38253`; `GET /`
  200 (9,222 bytes), `/static/maker.js` 200, `/static/wasm/svf.wasm` 200 `application/wasm`, `/api/caps` 403 without the
  header and `{"wasm": true, "mask_libs": false, "recog": false, "local": true}` with it, the CSP header present. A
  **local job run through it end to end** (`POST /api/jobs {"source": "local"}`, `PUT sources` with a folder holding
  `ttf/neodgm/neodgm.ttf`, `POST detect`, `PUT settings` 16 px 1 bpp precomposed, `GET probe/.../16/1.json` 200, `POST
  run`): state `done` in 0.7 s, wrote `svf/dos/NEODU16.SVF`, `svf/dos/NEODU.TXT`, `build-<id>/{BUILD.md,
  FACES.TSV.lines, FAMILIES.tsv.lines, LICENCES.tsv.lines}`, the face **byte-identical** to the source-mode run, the
  note line `python3 -P tools/mkfont.py neodgm.ttf NEODU16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
  --report report.json`, `GET face/s01.svf` 200; `GET preview/<font>/source.png` 200 (a 521-byte PNG: Pillow and
  its FreeType binding work inside the bundle); SIGTERM -> exit within 200 ms, no files directory left. (The spike
  reached the tools through a compatibility shim in its entry point that maps `-P /path/tools/X.py` to `run-tool X`;
  the design replaces that with the launcher helper of section 7, not the shim.)
- From node (`child_process.spawn(sidecar, ["serve"], {detached: true, env: {...}})`, as the main process will):
  the port line arrived after 96 ms (145 ms when run from inside the extracted AppImage below), `fetch` of `/api/caps`
  with the header 200, `process.kill(-pid, "SIGTERM")` -> exit code 0 after 16 ms (idle server).
- Electron under `xvfb-run -a electron --no-sandbox` with `session.fromPartition("maker")` (no `persist:`),
  `webRequest.onBeforeSendHeaders({urls: [origin + "/*"]})` adding `X-Maker-Token` for `/api/` paths, and
  `webRequest.onBeforeRequest({urls: ["<all_urls>"]})` cancelling every URL outside the origin, a page served by a node
  HTTP server with the maker's CSP: the page's `fetch("/api/caps")` arrived with the header, `/` and `/probe.js`
  without it; a `fetch("http://127.0.0.1:1/x")` from the page was rejected ("Failed to fetch") - by the CSP's
  `connect-src 'self'` before `onBeforeRequest` saw it (the cancel list stayed empty), so both layers exist and the CSP
  is the first.
- electron-builder: `electron-builder --linux AppImage --publish never` on a one-file app: 6.9 s, downloaded
  `appimage-12.0.1.7z` and `7zip-linux-x64.tar.gz` from GitHub into `~/.cache/electron-builder` (14 MB), produced a
  **126 MB** AppImage (Electron 45's own `dist/` is 275 MB unpacked: `locales/`, `resources.pak`, `libvk_swiftshader`, ...).
  The same with `extraResources` = the 47 MB sidecar + `svf/` + `tools/*.py` + `web/{mkindex.py, LICENCES.tsv,
  FAMILIES.tsv}`: 6.1 s, **151 MB** AppImage, `linux-unpacked` 334 MB (`resources/sidecar` 47 MB, `resources/repo` 13
  MB). FUSE is absent here, so the AppImage itself refuses to mount ("--appimage-extract"); after `--appimage-extract`,
  `squashfs-root/AppRun` under `xvfb-run` printed the app's "probe ok" **both with and without `--no-sandbox`** on this
  Ubuntu 24.04 host (`apparmor_restrict_unprivileged_userns = 1`), and the bundled sidecar started from
  `resources/sidecar/` with `SVF_MAKER_REPO=resources/repo` (port line after 145 ms, caps 200).

## 5. Binding decisions (the owner, 2026-11-05)

1. The font tools stay Python; no JS/Rust port. The desktop app wraps a frozen Python sidecar (the maker server and
   all tools) in Electron.
2. Proprietary fonts (Mac/HWP) never leave the machine: the app runs the maker in local mode (token + loopback only);
   the bridge picks paths; results go to the user's output folder.
3. The repository is OFL-only: the bundle contains only OFL assets (`NEODG16.SVF` and the rest of `svf/`); the
   licences of everything bundled are listed in a generated THIRD-PARTY file.
4. Linux AppImage first (verifiable here); Windows and macOS builds are documented as UNVERIFIED steps.
5. Nothing assumes a tailnet or systemd.
6. The font licence is the user's responsibility (the page's acknowledgement popup exists; the shell adds none).

## 6. Architecture (A)

### 6.1 Processes

```
Electron main process (desktop/main.js)            Node; owns the window, the sidecar, the dialogs, the log
  |-- spawns --> svf-maker-sidecar serve          frozen Python (PyInstaller one-dir), 127.0.0.1:<port>, own session
  |                 |-- spawns per step --> svf-maker-sidecar run-tool <name> ...   (jobs.run_command, own session)
  |                 `-- spawns per preview/probe/bake --> the same                   (preview.run_bounded)
  `-- BrowserWindow (renderer, sandboxed, contextIsolation)  loads http://127.0.0.1:<port>/
        preload.js  --> window.svfMaker (contextBridge -> ipcRenderer.invoke)
```

Files added to the repository (section 11 says in which slice): `desktop/package.json`, `desktop/main.js`,
`desktop/preload.js`, `desktop/lib/*.mjs` (the pure helpers the node tests import: the port-line parser, the URL
guard, the environment builder, the shutdown sequencer), `desktop/build/` (electron-builder config, the AppImage and
THIRD-PARTY scripts), `desktop/test/` (node tests, the xvfb Electron test), `maker/sidecar.py` (the frozen entry
point), `maker/toolrun.py` (the launcher helper), `maker/sidecar.spec` (PyInstaller), `maker/build-sidecar.sh`.

### 6.2 Spawning the sidecar and the handshake

(design call) The main process spawns the sidecar before the window is created, with:

- command: `[<resources>/sidecar/svf-maker-sidecar, "serve", "--exit-with-parent"]` (section 7.9) in the packaged
  app; in development (`SVF_MAKER_DEV=1`, or no `resources/sidecar/` found) `[python3, "-P", <checkout>/maker/server.py]`
  with the same environment, so the shell can be developed and tested without a frozen build;
- `child_process.spawn(cmd[0], cmd.slice(1), {detached: true, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
  env})` - `detached: true` gives the sidecar its own session, so `process.kill(-pid, sig)` reaches it and every tool
  group it leaves behind, and so the shell's own death does not SIGHUP it mid-sweep (the sidecar watches the parent
  instead, 7.9);
- `env` built by `desktop/lib/env.mjs` from scratch (not `process.env` spread): `PATH` (the user's, for nothing the
  maker needs but `jobs.ENV` reads it), `HOME`, `LANG=C.UTF-8`, `SVF_MAKER_TOKEN` = `crypto.randomBytes(16).toString("hex")`
  (new per launch, never logged, never written to disk), `SVF_MAKER_BIND=127.0.0.1:0`, `SVF_MAKER_DATA=<userData>/maker`,
  `SVF_MAKER_REPO=<resources>/repo` (section 8.4), `SVF_MAKER_ROOTS` only when the user set it in the shell's
  environment, and the optional pass-throughs `JAMOSET_PYLIB` and `SVF_RECOG_DIR` (8.7) when set in the shell's
  environment. On Linux `XDG_RUNTIME_DIR` and `TMPDIR` are **not** passed (the sidecar's own temp files for a local job go
  under the files directory; its process-wide `tempfile` default falls back to `/tmp`, as in source mode);
- the handshake: `desktop/lib/portline.mjs parsePortLine(buffer)` matches `/^svf-maker listening on 127\.0\.0\.1:(\d+)$/m`
  on the accumulated stdout (the exact line `server.py:1950` prints; the host is `127.0.0.1` because the bind is, and the
  parser also accepts `::1` in brackets for a future IPv6 bind but the shell never asks for one). The wait is bounded
  (15 s); an exit before the line, or the timeout, is a start failure: the main process shows a message box with the
  last 20 lines of the sidecar's stderr (which never contains the token: `_parse_token` prints only its fixed message)
  and quits. The port is never read from anywhere else and is not configurable.

### 6.3 The token header and the session

- `session.fromPartition("maker")` - no `persist:` prefix, so cache, cookies and storage are in memory and leave with
  the process (the byte endpoints of a local job answer `no-store` already; this keeps even `/static/*` off the disk).
- `ses.webRequest.onBeforeSendHeaders({urls: [origin + "/*"]}, (details, cb) => ...)`: for a URL whose `pathname`
  starts with `/api/` set `requestHeaders["X-Maker-Token"] = token` (assign, so there is exactly one; delete any
  `x-maker-token` spelled otherwise); every other URL of the origin is passed unchanged. `origin` is
  `http://127.0.0.1:<port>` as a string; the filter is per origin, so a second window or a reloaded page gets it too.
- `ses.webRequest.onBeforeRequest({urls: ["<all_urls>"]}, (details, cb) => cb({cancel: !isOurs(details.url)}))` with
  `isOurs(url)` = `url === origin + "/" || url.startsWith(origin + "/")` (exact string prefix; `desktop/lib/guard.mjs`),
  `devtools://` allowed only when devtools are enabled (6.8). The sidecar's CSP (`connect-src 'self'` ...) is the first
  layer, verified in section 4; this is the second, and it also covers requests the page does not make itself
  (favicons, prefetch, a dictionary download). `webPreferences.spellcheck = false` (Electron's Hunspell dictionary
  download is the one outbound request Chromium would make on its own).
- `ses.setPermissionRequestHandler((_wc, _perm, cb) => cb(false))`, `ses.setPermissionCheckHandler(() => false)`,
  `ses.setDevicePermissionHandler(() => false)`: the page needs no permission (no clipboard, camera, notifications).
- The page is loaded with `win.loadURL(origin + "/")`. Never `file://` (the server refuses `Origin: null`; audit section
  4) and never a custom scheme: the page's own relative URLs, its `import("/static/wasm/svf.js")` and `fetch("/api/...")`
  resolve against the sidecar origin only when the document is on it.

### 6.4 Navigation guards and the window

- `webPreferences`: `{preload: <app>/preload.js, contextIsolation: true, sandbox: true, nodeIntegration: false,
  nodeIntegrationInWorker: false, webSecurity: true, allowRunningInsecureContent: false, spellcheck: false, partition:
  "maker", devTools: <6.8>}`.
- `win.webContents.on("will-navigate", (e, url) => { if (!isOurs(url)) e.preventDefault(); })`; the page itself
  navigates only to `/?job=<id>` (its own URL form); `will-redirect` the same; `setWindowOpenHandler(() => ({action:
  "deny"}))`; `will-attach-webview` prevented; `app.on("web-contents-created")` applies the three to any web contents.
- One window (`desktop/main.js createWindow()`), 1200x800 default, the last size and position remembered in
  `<userData>/shell-state.json` (sizes only; no paths), title "SVF maker", the app icon from `desktop/build/icon.png`
  (a new 512x512 PNG the builder draws from the `svf/dos/NEODG16.SVF` glyph "ㅅ" or a plain monogram; no proprietary
  art). `show: false` until `ready-to-show`.
- Single instance: `app.requestSingleInstanceLock()`; the loser quits at once (before spawning a sidecar); the holder
  focuses its window on `second-instance`. Two instances would otherwise be two sidecars with two data roots... the
  data root is one per user, and `jobs.Store` has no cross-process lock, so one instance is a correctness rule, not a
  nicety.
- `window-all-closed` -> `app.quit()` on every platform including macOS (design call: the sidecar must not outlive the
  window; a dock-resident app with no window has nothing to show). `activate` re-creates the window if the app is
  still alive (macOS only reaches it during the quit sequence; harmless).

### 6.5 The bridge: `window.svfMaker` (the exact contract of the local-mode design, 10.6)

`desktop/preload.js` (runs sandboxed, `contextIsolation` on):

```js
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("svfMaker", {
  pickFiles:        () => ipcRenderer.invoke("maker:pick-files"),      // Promise<string[]>   ([] when cancelled)
  pickFolder:       () => ipcRenderer.invoke("maker:pick-folder"),     // Promise<string[]>   ([] or [dir])
  pickOutputDir:    () => ipcRenderer.invoke("maker:pick-output-dir"), // Promise<string|null>
  openOutputFolder: () => ipcRenderer.invoke("maker:open-output"),     // Promise<void>; takes no argument
  platform: process.platform,                                          // "linux" | "darwin" | "win32"
});
```

`desktop/main.js` handlers (`ipcMain.handle`), each first checking `new URL(event.senderFrame.url).origin === origin`
(any other sender gets a rejected promise and a log line):

- `maker:pick-files`: `dialog.showOpenDialog(win, {properties: ["openFile", "multiSelections"], defaultPath:
  lastInputDir})` -> `canceled ? [] : filePaths` (absolute paths as the OS gives them; no normalisation: the server
  realpaths and checks them, local-mode design 7.1);
- `maker:pick-folder`: `{properties: ["openDirectory"]}` -> `[]` or `[dir]` (two dialogs because Electron cannot
  combine `openFile` and `openDirectory` on Linux and Windows: the local-mode design's reason);
- `maker:pick-output-dir`: `{properties: ["openDirectory", "createDirectory"], defaultPath: lastOutputDir}` ->
  `null` or the path; the main process remembers it as `lastOutputDir` for this launch (and in `shell-state.json`,
  design call: only this one path is persisted, so the next launch's dialog opens there; D3 below asks whether to
  persist it at all);
- `maker:open-output`: `shell.showItemInFolder(lastOutputDir)` when set, else nothing (the page shows the job's
  `output_dir` as text only; the shell reveals the folder *it* handed out, never a path from the page; never
  `shell.openPath`, which executes files).

No other IPC channel exists; `ipcRenderer` is not exposed; the bridge object is frozen by `contextBridge`.

### 6.6 Quit, crash, and what happens when the sidecar dies

- Quit sequence (`app.on("before-quit")`, also reached from the window's close, the menu, SIGINT/SIGTERM to Electron
  and `second-instance` on the loser): `e.preventDefault()` once, then `desktop/lib/shutdown.mjs stopSidecar(child)`:
  `process.kill(-child.pid, "SIGTERM")`; wait for `exit` up to **35 s** (`Worker.stop`'s 30 s for a running job plus
  the stop sweep); then `process.kill(-child.pid, "SIGKILL")` and wait up to 5 s more; then `app.exit(0)`. While
  waiting the window stays (hidden after 1 s) and a "stopping the maker..." line goes to the log; the sidecar's own
  behaviour is `server.py main()`'s `finally` (section 4). A SIGKILL leaves `.svf-maker-<id>/` in the output folder until
  the next start's `recover` sweep (local-mode design 8.3) - that is the server's rule and the shell relies on it.
- Electron crashes (the main process is killed, segfaults, OOM): the sidecar is in its own session and would survive;
  `serve --exit-with-parent` (7.9) makes it notice within 2 s and run the same `finally` as SIGTERM. So the only way
  to orphan a tool child is to SIGKILL the sidecar itself, which the shell does only after the 35 s wait.
- The sidecar dies on its own (`child.on("exit")` while not quitting; a Python crash, an OOM kill, a user `kill`):
  the main process logs the exit code/signal and the stderr tail, shows a `dialog.showMessageBox` "The maker stopped
  (exit N). Restart it? [Restart] [Quit]"; Restart spawns a new sidecar with a **new token and a new port** (the old
  session's header rule is removed and a new one installed; `ses.webRequest` handlers are replaced by calling them
  again with the new filter) and `win.loadURL(newOrigin + "/")`; the page's job list comes from the data directory,
  so the user's finished jobs are still there (a running job is `failed (interrupted)` by `recover`). At most 3
  restarts in 5 minutes; then only Quit. No separate error page is bundled (design call: a message box needs no
  navigation exception and no second origin).
- A renderer crash (`render-process-gone`): reload the same URL once; a second time, the message box above.

### 6.7 Logging (privacy rules of the local-mode design, 10.4)

`<userData>/logs/shell.log` (append; rotated at 1 MiB to `shell.log.1`, two kept): timestamps, app and sidecar
versions and build id, the sidecar's command (without its environment), the port, start/stop/exit events with codes
and timings, restart decisions, IPC refusals, and the last 50 lines of the sidecar's **stderr** (`server.py` prints
only its own messages there; tool stderr stays in the job's `work/sNN/stderr.txt`). Never: the token, request URLs
with job ids beyond the start/stop events, request or response bodies, the paths the dialogs returned (counts only:
"pick-files: 3"), any byte of an input. The sidecar's stdout after the port line is logged as-is (it prints nothing
more today). `SVF_MAKER_SHELL_LOG=stderr` sends the same lines to the terminal for development.

### 6.8 Menu, zoom, about, devtools

A small application menu (Linux/Windows: in the window; macOS: the app menu), roles only where Electron has them:
File > Open output folder (= `maker:open-output`), Quit; View > Reload (the page reloads on the same origin; the
header rule is per session, so the token is still added), Actual size / Zoom in / Zoom out (`role` items;
`zoomFactor` persisted in `shell-state.json`), Toggle developer tools **only when `SVF_MAKER_DEVTOOLS=1`** is in the
environment (and `webPreferences.devTools` is false otherwise, so the shortcut does nothing); Help > About: a message
box with the app version, the build id (8.8), Electron/Chromium/Node versions, the sidecar's Python version (the
sidecar prints it in `sidecar --version`, 7.1), and a "Third-party licences" button that opens `<resources>/THIRD-PARTY.txt`
with `shell.openPath` (the only `openPath` call: the app's own text file). No tray icon, no notifications.

### 6.9 Updating

Out of scope and a non-goal (section 3): no `autoUpdater`, no update check, no "a new version is available". The
user downloads a new AppImage. A static test (10.3) fails if `desktop/` imports `electron-updater`, `autoUpdater`,
`net`, `http(s)` or calls `fetch`/`XMLHttpRequest` with an absolute URL.

## 7. The sidecar entry point and the launcher helper (B)

### 7.1 `maker/sidecar.py`: one executable, three commands

```
svf-maker-sidecar serve [--exit-with-parent]     -> maker/server.py main()   (env as today; section 6.2)
svf-maker-sidecar run-tool NAME ARGS...          -> tools/NAME.py main(), maker/srcprep.py, maker/recog_score.py,
                                                    or fontTools.varLib.instancer (NAME "instancer"); exit code = the tool's
svf-maker-sidecar selfcheck                      -> JSON on stdout: {"frozen", "version", "build_id", "python",
                                                    "flags": {"isolated", "ignore_environment", "safe_path",
                                                    "no_site"}, "path": sys.path, "tools": [names]}   (the test gate)
svf-maker-sidecar --version                      -> "svf-maker-sidecar <version> <build id> python <x.y.z>"
```

`run-tool` resolves `NAME` against a fixed table (design call: a table, not `importlib.import_module(NAME)` of
anything: `jamoset`, `jamovec`, `mkfont`, `macfbit_svf`, `macfbit3`, `macsfnt`, `bdfface`, `johab844`, `svf2to3`,
`svfdy`, `svfline`, `facecheck`, `srcprep`, `recog_score`, `instancer`), sets `sys.argv = [NAME + ".py", *ARGS]` so
argparse's `prog`, usage lines and error messages are the ones the tools print today (verified: `usage: jamoset.py
...`), calls `main()` (or `main(ARGS)` for the `argv=None` ones - either form takes the same `sys.argv`), and exits
with its return value or 0; an uncaught exception prints the traceback and exits 1 as `python3` would; `instancer`
is `fontTools.varLib.instancer.main(ARGS)`. An unknown name prints `run-tool: unknown tool 'X'` and exits 2. The entry
point imports every tool statically (an `import` table) so PyInstaller's analysis sees them without hidden-import
flags; in source mode it inserts `maker/` and `tools/` into `sys.path` first, as `server.py` does.

The `-P path.py` shim the spike used (section 4) is **not** part of the design: `run-tool` is the one launch form, so a
stale `[sys.executable, "-P", ...]` in a frozen build is a loud failure (`usage:` on stderr, exit 2), not a silent
success path with two shapes.

### 7.2 `maker/toolrun.py`: the one place that knows how to launch

```python
"""How the maker launches a tool: `python3 -P <script>` in source mode, `<sidecar> run-tool <name>` when frozen."""
import os, sys

FROZEN = bool(getattr(sys, "frozen", False))        # PyInstaller sets sys.frozen on the frozen process
MAKER_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_SCRIPTS = ("srcprep", "recog_score")           # the maker's own CLIs

def tool(name, tools_dir):
    """argv prefix for tools/<name>.py: [py, "-P", <tools_dir>/<name>.py] or [sidecar, "run-tool", name]."""
    if FROZEN:
        return [sys.executable, "run-tool", name]
    return [sys.executable, "-P", os.path.join(tools_dir, name + ".py")]

def maker_script(name):
    """argv prefix for maker/<name>.py (srcprep, recog_score)."""
    if FROZEN:
        return [sys.executable, "run-tool", name]
    return [sys.executable, "-P", os.path.join(MAKER_DIR, name + ".py")]

def module(dotted):
    """argv prefix for `python3 -P -m <dotted>`; frozen: the run-tool name of that module ("instancer")."""
    if FROZEN:
        return [sys.executable, "run-tool", MODULE_NAMES[dotted]]
    return [sys.executable, "-P", "-m", dotted]

MODULE_NAMES = {"fontTools.varLib.instancer": "instancer"}

def note_prefix(argv, tools_dir):
    """`(prefix_tokens_for_the_note, rest)`: the launcher part of @p argv as the note shows it in BOTH modes:
    ["python3", "-P", "tools/<name>.py"], ["python3", "-P", "maker/<name>.py"] or ["python3", "-P", "-m", dotted]."""
```

`tool(name, tools_dir)` takes the name without `.py` (so the call sites change from `_tool(paths, "mkfont.py")` to
`toolrun.tool("mkfont", paths["tools"])`); `note_prefix` gives `zipout._note_token`'s replacement the launcher tokens
in the note's form, so a local job's note is **the same text in source and frozen mode** (`python3 -P tools/mkfont.py
...`: verified today's form in section 4; a test pins it in both modes). `FROZEN` is read once at import; tests set
`toolrun.FROZEN = True` with `mock.patch` to check the frozen shape without a build.

### 7.3 Every call site, and the change (at `1513dd2`)

| Site | Today | Change |
|---|---|---|
| `maker/routes.py:20` `PY = [sys.executable, "-P"]` | the prefix every route uses | removed; `routes` imports `toolrun`. (Keep `PY` as a deprecated alias for one commit if the tests need it; the design prefers deleting it and fixing the tests in the same commit.) |
| `maker/routes.py:26` `SRCPREP = <maker/>/srcprep.py` | the maker's CLI path | removed; `toolrun.maker_script("srcprep")` |
| `maker/routes.py:135` mkfont, `:141,:148,:156` jamovec master/render/master, `:165,:173` jamoset `--from-ttf`, `:187` jamoset DOS raw, `:196` johab844, `:203` jamoset hanterm, `:215` macfbit_svf build, `:225` jamoset mac-fbit-45sets, `:235` macfbit3 bdf, `:240` mkfont (bdf + mkfont), `:253` bdfface, `:262` jamoset `--from-svf` (after bdfface), `:298` svf2to3, `:324` jamoset `--from-svf` | `PY + [_tool(paths, "X.py"), ...]` | `toolrun.tool("X", paths["tools"]) + [...]`; `_tool` is deleted (its only job was the join) |
| `maker/routes.py:237` srcprep `bdf-pixel-size` | `PY + [SRCPREP, ...]` | `toolrun.maker_script("srcprep") + [...]` |
| `maker/routes.py:379,:383` macsfnt extract/unicode, `:392` macfbit3 fbit | `PY + [os.path.join(tools_dir, "X.py"), ...]` | `toolrun.tool("X", tools_dir) + [...]` |
| `maker/routes.py:381,:388,:390,:394,:396` srcprep ttc-face, pcf-bdf, mac-fork, mac-htbl, mac-fork-named | `PY + [SRCPREP, ...]` | `toolrun.maker_script("srcprep") + [...]` |
| `maker/routes.py:386` instancer | `PY + ["-m", "fontTools.varLib.instancer", ...]` | `toolrun.module("fontTools.varLib.instancer") + [...]` |
| `maker/settings.py:1446` svfdy | `routes.PY + [os.path.join(tools_dir, "svfdy.py"), ...]` | `toolrun.tool("svfdy", tools_dir) + [...]` |
| `maker/jobs.py:1497` recog_score | `routes.PY + [<maker/>/recog_score.py, ...]` | `toolrun.maker_script("recog_score") + [...]` (and 8.7 for the external-interpreter option) |
| `maker/zipout.py:419` `_note_token`: `token == sys.executable -> "python3"`, a path under the checkout -> `tools/<name>` | per token | `note_commands` first splits each argv with `toolrun.note_prefix` and maps the prefix; the per-token rules stay for the rest (a frozen `run-tool` token would otherwise be shown as the sidecar's basename) |
| `maker/preview.py:191-251` `bake_source_face`, `maker/server.py:1637-1675` the probe, `:1839-1843` source conversions | build argv through `routes.*` / `settings.*` | no change: they inherit |
| `maker/test/test_routes.py:23` `PY = [sys.executable, "-P"]` and its 13 uses; `maker/test/test_zipout.py:115-131,:550`; `maker/test/test_plan_inputs.py` (7 `PY` uses) | expect `[python, "-P", "/T/mkfont.py", ...]` | expect `toolrun.tool("mkfont", "/T") + [...]`; a new `test_toolrun.py` pins both shapes and `note_prefix` |
| `maker/test/test_srcprep.py:103-389`, `test_fixtures.py:75`, `test_real_inputs.py:107,:151`, `test_clip_math.py:33`, `test_plan_inputs.py:806`, `test_server_signals.py:86,:113` | run a script or the server directly with `sys.executable` | unchanged: they test the scripts as scripts |

`routes.py`'s `VALUED` flags, `apply_flags` and every positional rule are untouched: only the first two or three tokens
of each argv change, and only in frozen mode.

### 7.4 Byte-identical behaviour, cwd, environment, cancellation

- The argv after the launcher prefix is the same list; `jobs.run_command` and `preview.run_bounded` are unchanged:
  same `cwd` (the step's or preview's work directory), same `env` (`ENV` or `_job_env`'s), `stdin=DEVNULL`,
  `start_new_session=True`, the same `_stop` (SIGTERM, 5 s, SIGKILL on the group) and the same output cap. A frozen
  tool is the same executable as the server, started fresh per launch, so its process group, exit codes and
  stderr behave as `python3`'s; the bootloader installs no signal handler in one-dir mode (verified only in that
  SIGTERM to the serving process behaved as `server.py` expects; the per-tool kill path is exercised by the frozen
  smoke test of 10.2).
- Environment scrubbing: the tool's environment is the three (or five) keys the maker sets today; the frozen tool
  needs nothing else (verified under `env -i PATH=<empty dir>`): PyInstaller's bootloader sets `LD_LIBRARY_PATH`
  for its own process from the bundle path and the `_PYI_*` keys for itself, both inside the child; they are not
  required from the parent. `PYTHONDONTWRITEBYTECODE=1` is moot in the frozen process (`dont_write_bytecode=1` is
  built in) and harmless. `TMPDIR` is honoured by the frozen `tempfile` as by `python3`.
- `python3 -P` isolation preserved: the frozen interpreter runs with `isolated=1`, `ignore_environment=1`,
  `safe_path=True`, `no_site=1` (section 4), so `PYTHONPATH`, `PYTHONHOME`, user site-packages, the cwd and the
  script directory never enter `sys.path`; the only code on `sys.path` is the bundle. That is stricter than `-P`
  (which keeps `PYTHONPATH`) and is why the scrubbed environment is still passed: it is the maker's rule, not the
  bundle's need. The tools' own `sys.path.insert(0, HERE)` lines become no-ops (`HERE` is the bundle directory,
  already on the path); `jamoaa.load_fonttools` and `jamofit.load_libs` still append `JAMOSET_PYLIB` parts (8.7).
- Working directory: the sidecar `serve` process inherits the shell's cwd (the AppImage's mount point or wherever
  the user started it); it reads nothing relative, and every tool gets an absolute `cwd`. The main process passes
  `cwd: os.homedir()` to `spawn` anyway, so a removed launch directory cannot make the sidecar's `os.getcwd()` fail.

### 7.5 What the frozen server reads from `SVF_MAKER_REPO`

`<resources>/repo/` holds `svf/` (whole: `RepoIndex` needs every face for the clash and identical rules; the Latin
fallback and the `johab844` base; the `repo` licence texts - 12 MB), `web/mkindex.py`, `web/LICENCES.tsv`,
`web/FAMILIES.tsv`, and `BUILD_ID` (7.8). `tools/` is **not** needed by the frozen server (the code is in the bundle
and `tools_dir` is only joined into argv by `toolrun.tool`, which ignores it when frozen) - except when the optional
recogniser runs under an external interpreter (8.7, D5), in which case `repo/tools/*.py` and `repo/maker/*.py`
(without tests) are shipped too.

### 7.6 Static files

`server.static_dir` is `<dirname(server.__file__)>/static`; in the bundle `server.__file__` is `<_internal>/server.pyc`,
so `maker/static/` (with the built `wasm/`) is added as data `static/` -> `<_internal>/static/` (verified: `/static/maker.js`
and `/static/wasm/svf.wasm` served from the frozen sidecar). No code change.

### 7.7 Optional libraries: `JAMOSET_PYLIB` and `SVF_RECOG_DIR` with a frozen sidecar

- `mask fit` / `binarize mono` need freetype-py and uharfbuzz from `JAMOSET_PYLIB`; `jamofit.load_libs` appends that
  directory to `sys.path` and imports them. In the frozen process this works only when the directory holds builds for
  **CPython 3.12 on the same platform** (uharfbuzz is a compiled extension; freetype-py loads the system `libfreetype`
  through ctypes). The shell passes `JAMOSET_PYLIB` through when set; `caps.mask_libs` stays false otherwise and the
  routes are not offered - no new failure mode, and `maker/README.md` says what the directory must contain.
- The identity check needs numpy and torch (hundreds of MB; never bundled). Two ways to reach them from a frozen
  sidecar: (a) `SVF_RECOG_DIR` plus a `SVF_RECOG_PYLIB` directory appended to `sys.path` like `JAMOSET_PYLIB` - works
  only for 3.12 wheels of the user's torch; (b) **an external interpreter**: `SVF_RECOG_PYTHON=/path/to/python3` (one
  with numpy, torch and the recogniser's needs); `jobs.py:1497` then launches `[SVF_RECOG_PYTHON, "-P",
  <resources>/repo/maker/recog_score.py, ...]` (the script and the `tools/` modules it imports shipped as source, 7.5),
  and `caps.recog_dir` checks `SVF_RECOG_DIR` + the interpreter's `find_spec` by running `[python, "-c", "import numpy,
  torch"]` once at start (bounded, 20 s) instead of its own `find_spec`. Recommendation: (b), because a user with torch
  has a Python, and (a) ties them to the bundle's exact interpreter. Decision needed (D5). Until decided, the frozen
  sidecar simply reports `recog: false` and the page says the check is unavailable (today's behaviour with no
  recogniser).

### 7.8 The build id instead of `git rev-parse`

`zipout.repo_head(repo_dir)` first reads `<repo_dir>/BUILD_ID` (one line, stripped, at most 200 characters) and
returns it when the file exists; otherwise `git` as today; otherwise `"unknown"`. `maker/build-sidecar.sh` writes
`BUILD_ID` = `<git describe --always --dirty> <ISO date of the commit> sidecar <version>` into the resources tree
(e.g. `1513dd2 2026-11-05 sidecar 0.1.0`), so `BUILD.md`'s "repo HEAD ..." line names the source of the faces a user
made with the app. `git` is not needed on the user's machine and is not in the tool environment anyway.

### 7.9 `serve --exit-with-parent` (the one new server flag)

A thread started after the bind polls `os.getppid()` every 2 s; when it is no longer the pid recorded at start (the
parent died: on Linux and macOS the orphan is re-parented to 1 or a subreaper), it calls the same shutdown as SIGTERM
(`os.kill(os.getpid(), SIGTERM)`), so a crashed shell never leaves a serving sidecar behind. Off by default (the
tests and the manual `python3 -P maker/server.py` run keep today's behaviour). POSIX-only, like the rest of the
server. (Alternative, Linux-only and immediate: `prctl(PR_SET_PDEATHSIG, SIGTERM)` via ctypes; rejected here for
portability to macOS; a builder may add it under `sys.platform == "linux"` as a second layer.)

## 8. Packaging (C)

### 8.1 Freezer: PyInstaller (recommended), and why not the others

| Option | For | Against |
|---|---|---|
| **PyInstaller 6.x one-dir** (recommended) | verified here (47 MB, 6 s build, byte-identical output, `isolated` interpreter, single process, clean SIGTERM); hooks for Pillow and fontTools exist; one executable serves and runs tools; supports Linux, macOS, Windows from the same spec | the Debian setuptools `pkg_resources` trap (section 4; excluded in the spec); the bundle's glibc floor is the build host's (8.10) |
| Nuitka | compiles to C: faster start, harder to read | long builds (minutes), a C toolchain on every build host, `fontTools`' dynamic table imports need the same care; nothing here needs the speed (tool launches are 0.03-0.3 s) |
| shiv / zipapp + an embedded CPython (python-build-standalone) | pure-Python archive, transparent | ships no CPython itself: another download + assembly step per platform; Pillow and fontTools wheels still have to be unpacked beside it; the `isolated`/`safe_path` discipline must be re-created by hand; not verified here |
| a system Python dependency (no freezer) | smallest package | fails the goal (no Python on the user's machine); Windows users rarely have one |

### 8.2 One-dir, not one-file

One-dir: the executable plus `_internal/` (verified). One-file would extract the whole bundle into a temp directory
**on every launch** - and the maker launches the sidecar executable once per tool step, per preview, per probe
(tens of times per job), so one-file would add seconds and tens of MB of temp I/O per step, would re-extract under the
scrubbed environment (one-file's child needs `_MEIPASS2`/`_PYI_ARCHIVE_FILE` from the parent to skip extraction), and
is the form antivirus heuristics flag most (self-extracting). One-dir starts in 0.03 s and extracts nothing. The
AppImage squashfs already gives the user a single file.

### 8.3 `maker/sidecar.spec` (what it must contain)

```python
# -*- mode: python -*-   maker/sidecar.spec: pyinstaller maker/sidecar.spec (from the checkout root)
import os
ROOT = os.path.abspath(SPECPATH + "/..")
a = Analysis([os.path.join(ROOT, "maker", "sidecar.py")],
             pathex=[os.path.join(ROOT, "maker"), os.path.join(ROOT, "tools")],
             datas=[(os.path.join(ROOT, "maker", "static"), "static")],       # index.html, *.js, style.css, wasm/
             hiddenimports=["fontTools.varLib.instancer"],
             hookspath=[], runtime_hooks=[],
             excludes=["wx", "fontTools.ui", "brotli", "_brotli", "zopfli", "lxml", "unicodedata2", "lz4", "numpy",
                       "torch", "scipy", "matplotlib", "sympy", "tkinter", "gi", "PIL.ImageQt", "PIL.ImageTk",
                       "xattr", "pkg_resources", "setuptools", "jaraco", "freetype", "uharfbuzz", "pathops",
                       "test", "unittest.mock"],
             noarchive=False)
# fontTools loads table classes by name: collect them
from PyInstaller.utils.hooks import collect_submodules
a.hiddenimports += collect_submodules("fontTools.ttLib") + collect_submodules("fontTools.pens") \
                 + collect_submodules("fontTools.varLib")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="svf-maker-sidecar", console=True, upx=False,
          strip=False)                                   # strip/upx: off (reproducibility, antivirus; 8.10)
coll = COLLECT(exe, a.binaries, a.datas, name="svf-maker-sidecar")
```

Points: the tools are reached by the entry point's static import table, so no `--hidden-import` per tool; the three
`collect_submodules` cover fontTools' run-time imports (the spike built with `fontTools.ttLib` + `fontTools.pens` +
`varLib.instancer` and ran mkfont, srcprep and the instancer; `fontTools.varLib` whole is added for `instancer`'s own
lazy imports - **not verified** beyond `--help`); `excludes` names what the spike measured as dead weight (wx + GTK
alone were 60 MB) and the recogniser/mask libraries (never bundled; 7.7); `console=True` so stdout is a pipe (the
handshake) and on Windows a console is not shown because the shell spawns with `windowsHide`. `maker/build-sidecar.sh`
runs `pyinstaller --noconfirm --clean --distpath desktop/build/out/sidecar maker/sidecar.spec` from a `venv` the
script creates (`python3 -m venv` needs `python3-venv` on Debian/Ubuntu; the script says so and falls back to
`pip install --target`, which is what worked here), pins `pyinstaller==6.22.3 pillow==10.2.0 fonttools==4.66.1` in
`desktop/build/requirements-sidecar.txt` (the versions verified here; D6 asks whether to track newer), builds the
WASM module first (8.5), then writes `BUILD_ID` and runs `svf-maker-sidecar selfcheck` as its last step.

### 8.4 The resources layout of the packaged app

```
<AppImage>/resources/
  app.asar                      desktop/main.js, preload.js, lib/, package.json  (electron-builder's default)
  sidecar/svf-maker-sidecar     PyInstaller one-dir (executable + _internal/ with static/ and wasm/)
  repo/svf/...                  the faces and licence texts, copied whole from svf/ (12 MB)
  repo/web/mkindex.py, LICENCES.tsv, FAMILIES.tsv
  repo/BUILD_ID
  repo/tools/*.py, repo/maker/*.py   only if D5 chooses the external recogniser interpreter (no tests, no __pycache__)
  THIRD-PARTY.txt               generated (8.9)
```

`SVF_MAKER_REPO=<resources>/repo` (verified: the sidecar served and ran a job from exactly this layout inside the
extracted AppImage). The data root is `<userData>/maker` = `~/.config/svf-maker/maker` on Linux (Electron's
`app.getPath("userData")`, `<productName>` = `svf-maker`); the server keeps its retention (20 jobs / 7 days). The
OFL-only rule: the copy step copies `svf/` as it is; a test (10.3) asserts every `.SVF` in the package has a
`LICENCES.tsv` row (the picker's own rule, `tools/test_web_picker.py`) and that no file outside `svf/`'s licence set
ends in `.TXT`.

### 8.5 The WASM module in a CI-less build

`maker/build-wasm.sh` needs emsdk (`EMSDK`, default `~/opt/emsdk`; here emcc 6.0.13, 1.3 s). `build-sidecar.sh` calls
it before PyInstaller so `maker/static/wasm/` is in the data files; without emsdk it stops with the script's own
message (`no emcc at ...`) - a package without the module would show "preview module not built" in every cell, which
is not a release. The module's bytes are path-independent (the WASM design verified that `web/build.sh` and
`build-wasm.sh` give identical bytes), so the package's `svf.wasm` can be compared with a fresh build in the release
check (10.2). No CI: the release is built on this host by hand, and `docs/maker-desktop.md` (slice S5) lists the
command sequence and the emsdk/PyInstaller/Electron versions it was last run with.

### 8.6 Size and start-up budget (measured, section 4)

| Item | Measured | Budget |
|---|---|---|
| Sidecar one-dir | 47 MB (113 MB before the excludes) | <= 60 MB |
| `repo/svf` + `web` | 13 MB | as is |
| AppImage, bare Electron 45 | 126 MB | - |
| AppImage, full (Electron + sidecar + repo) | **151 MB** | <= 170 MB |
| `linux-unpacked` | 334 MB | - |
| Sidecar port line | 96 ms (145 ms from the extracted AppImage) | <= 2 s (the shell waits 15 s) |
| Tool launch overhead | +0.1 s per launch (mkfont 16 px: 0.30-0.34 s frozen vs 0.24 s source) | <= +0.3 s |
| SIGTERM to exit, idle | 16 ms; 200 ms after a finished job | <= 35 s with a running job (the server's own bound) |
| PyInstaller build | 6 s; electron-builder 6-7 s (+ first-time downloads: Electron 119 MB, appimage tool 14 MB) | - |

Electron's own 126 MB is the floor; the sidecar is a third of it. The next 20 MB of savings would be `locales/` (Electron
ships 50+; the page is English-only - electron-builder's `electronLanguages: ["en-US"]`, **not verified**) and the
`fontTools` subpackages the tools never import (`feaLib`, `otlLib`, `subset`, ... 11 MB today; pruning them by
exclude is a per-module exercise with a test per tool - left to the builder, not required for the budget).

### 8.7 AppImage assembly: electron-builder (recommended) over electron-packager + appimagetool

electron-builder (26.18.0, MIT) did the whole thing here in one command (downloaded its pinned `appimage-12.0.1`
tool, packed `linux-unpacked`, wrote the AppImage, 6 s), takes `extraResources` for the sidecar and the repo tree, and
has the Windows (NSIS/portable) and macOS (dmg/zip, signing, notarization) targets the UNVERIFIED notes of 9.11 rely
on, so one `desktop/package.json` "build" block describes all three. electron-packager + appimagetool would need a
hand-written AppDir (`AppRun`, `.desktop`, icon), a separately downloaded appimagetool (not installed here) and a
second tool chain per platform. electron-builder's `asar` packs only `desktop/` (`files: ["main.js", "preload.js",
"lib/**"]`); the sidecar and the repo stay unpacked under `resources/` (`extraResources`), because the sidecar must be
executable and PyInstaller's `_internal` must be a real directory.

`desktop/package.json` "build": `appId org.svf-fonts.maker`, `productName svf-maker`, `linux.target ["AppImage"]`,
`linux.category Utility`, `linux.desktop.Name "SVF maker"`, `desktopName svf-maker.desktop` + `linux.syncDesktopName
true` (electron-builder's own warning), `extraResources` as in 8.4, `electronVersion` pinned, `npmRebuild false`,
`publish: null`. `desktop/build/build-appimage.sh`: `maker/build-sidecar.sh`, then `node desktop/build/third-party.mjs`
(8.9), then `npx electron-builder --linux AppImage --publish never`, then the release check of 10.2 on the result.

**Sandbox note (Linux).** Chromium's SUID sandbox helper cannot be setuid inside an AppImage (FUSE mounts are `nosuid`),
so Electron falls back to user namespaces; Ubuntu 24.04 restricts unprivileged user namespaces by AppArmor
(`apparmor_restrict_unprivileged_userns = 1` here) - yet the extracted AppImage's `AppRun` started and ran **without**
`--no-sandbox` on this host under xvfb (section 4). Electron 45 evidently copes on this configuration; other distros
and kernels are **not verified**. The shell must not add `--no-sandbox` by default (it would drop the renderer sandbox
for every user). If a report shows the "SUID sandbox helper" failure, the documented workaround is the AppImage's
own `--no-sandbox` argument or the distro's AppArmor profile; D7 asks whether the AppRun wrapper should detect the
case and add the flag itself.

### 8.8 Versioning and the build id

`desktop/package.json` `version` is the app's (semver, starts 0.1.0); the sidecar prints the same (`--version`,
from a `maker/VERSION` file the build script writes - or `importlib.metadata` is avoided on purpose: there is no
package); `BUILD_ID` (7.8) carries the git describe. The About box shows all three. A mismatch between the sidecar's
and the app's version is logged at start (not fatal).

### 8.9 `THIRD-PARTY.txt` generation

`desktop/build/third-party.mjs` writes `<resources>/THIRD-PARTY.txt` from three sources, each with the component,
version, licence name and the full licence text:

1. Electron and Chromium: `node_modules/electron/dist/LICENSE` (Electron, MIT) and `LICENSES.chromium.html` (every
   Chromium third-party notice; electron-builder copies them into the package as `LICENSE.electron.txt` and
   `LICENSES.chromium.html` - verified in `linux-unpacked/`; the generated file points at those two and inlines
   Electron's);
2. the npm packages that ship inside `app.asar` - with the recommended design there are **none** (`desktop/` has no
   runtime dependency; Electron is a devDependency); the script fails if `dependencies` is non-empty and not listed;
3. the sidecar: Python (PSF-2.0; `_internal/base_library.zip` and `libpython3.12`), Pillow (HPND, from
   `importlib.metadata` in the build venv), fontTools (MIT), and **every shared library PyInstaller collected** into
   `_internal/` (the 40 `.so` files here: libfreetype (FTL/GPLv2), libharfbuzz (MIT), libraqm (MIT), libfribidi (LGPL
   2.1), libjpeg (IJG), libtiff (libtiff), libwebp (BSD), libopenjp2 (BSD-2), liblcms2 (MIT), libpng (PNG), libjbig
   (GPL-2 - **check: Pillow's `_imaging` links it through libtiff on Ubuntu; a GPL library in the bundle is a licence
   question for the owner**, D8), libLerc (Apache-2), libdeflate (MIT), libzstd (BSD), liblzma (public domain/0BSD),
   libbz2 (bzip2), libcrypto/libssl (Apache-2), libstdc++/libgcc_s/libgomp (GPL-3 with the GCC runtime exception),
   libffi (MIT), libexpat (MIT), libglib-2.0/libpcre2 (LGPL-2.1 / BSD), libgraphite2 (LGPL-2.1), libimagequant (GPL-3
   or commercial - **same question**, D8), libbsd/libmd (BSD), libXau/libXdmcp (MIT), libreadline/libtinfo (GPL-3 /
   MIT - readline is pulled by the stdlib `readline` module: exclude `readline` and `curses` in the spec), libsharpyuv
   (BSD)). The script reads each `.so`'s Debian package and copyright file (`dpkg -S` + `/usr/share/doc/<pkg>/copyright`)
   on the build host and fails on any library it cannot attribute, so the list above is **generated, not typed**; the
   licence names above are from my knowledge of those projects and the copyright files are the source of truth.

The file also restates that the faces in `repo/svf` are OFL 1.1 (`NOTICE.md`'s table copied) and that the maker's own
code is MIT. A test (10.3) runs the generator against the built sidecar and asserts no unattributed file.

### 8.10 Reproducibility and the glibc floor

- Reproducible enough: pinned versions (`requirements-sidecar.txt`, `package.json` with a lockfile committed,
  `electronVersion`), `strip`/`upx` off, `SOURCE_DATE_EPOCH` exported by the build script from the commit date
  (PyInstaller 6 honours it for the archive timestamps; electron-builder's AppImage is deterministic for the same
  inputs per its docs - **not verified**). Byte-identical rebuilds are **not** a goal; "same inputs, same contents
  list and same sizes" is what the release check records.
- The sidecar's native libraries come from the build host; PyInstaller bundles the system libraries it finds except
  glibc itself, so the package runs on systems with **glibc >= the build host's (2.39 here, Ubuntu 24.04)**. Electron 45
  needs glibc >= 2.31-ish (Ubuntu 20.04+; from Electron's own support policy, not verified). Building the sidecar in a
  container of the oldest supported distro (Ubuntu 22.04, glibc 2.35) would widen the floor at the cost of a
  container step - D9.

### 8.11 Windows and macOS: documented, UNVERIFIED

Nothing below was run. It is the plan a builder on those hosts follows, and what blocks it.

- **macOS.** PyInstaller one-dir builds the same spec on macOS (arm64 and x86_64 are separate builds; a universal2
  build needs universal wheels of Pillow and fontTools). The server already runs on macOS (POSIX). electron-builder
  target `dmg` + `zip`; `extraResources` the same; the AppImage's `--no-sandbox` question does not exist.
  Signing: a Developer ID Application certificate, `electron-builder` with `mac.hardenedRuntime: true`, an
  entitlements file allowing nothing beyond `com.apple.security.cs.allow-unsigned-executable-memory` (Chromium) -
  and **every binary under `resources/sidecar/` must be signed too** (`codesign --deep` does not reach
  `_internal/*.so` reliably; sign them individually with `--options runtime`, PyInstaller's docs say the bootloader
  tolerates it), then `notarytool submit` and `stapler`. Without signing, Gatekeeper blocks the app on first run
  (right-click Open works). The file dialogs are native; `shell.showItemInFolder` reveals in Finder. The named
  resource fork reading of the local-mode design (D11 there) is where a Mac host would verify something this design
  cannot.
- **Windows.** The **server is not Windows-ready** (`os.killpg`, `start_new_session`, `signal.SIGTERM` to a group,
  `os.umask(0o077)` semantics, `os.link` for the no-replace write): a port needs Job Objects (or
  `CREATE_NEW_PROCESS_GROUP` + `GenerateConsoleCtrlEvent`) for the group kill, `CreateProcess` flags in
  `run_command`/`run_bounded`, and a review of every `realpath`/inode rule of the local-mode design on NTFS (inode =
  file index; `(st_dev, st_ino)` is populated by Python 3.12 on Windows). That is a card of its own; until it is done
  the Windows build is not attempted. When it is: PyInstaller one-dir with the same spec (`console=False` would hide the
  stdout pipe - keep `console=True` and `windowsHide` in the spawn), electron-builder target `nsis` or `portable`,
  the Electron spawn with `detached: false` and `taskkill /T` semantics through the Job Object, signing with a code
  signing certificate (SmartScreen otherwise warns). Antivirus: PyInstaller one-dir with a signed executable is the
  least-flagged form; one-file is the most.

### 8.12 Auto-update: non-goal

Stated in 6.9. The build also sets `publish: null` so electron-builder generates no update manifest (`latest-linux.yml`).

## 9. Security and privacy summary (what the shell adds to the server's rules)

The server's threat model and rules stand (local-mode design 10.1-10.5). The shell adds: the token exists only in the
main process's memory and the sidecar's environment; the renderer is sandboxed with context isolation and no node;
every request of the renderer is filtered to the sidecar origin (CSP first, `webRequest` second); navigation and new
windows are denied; no permission is granted; the IPC surface is four handlers that check the sender's origin; the
only paths that reach the server are the ones the user picked in a native dialog; the shell makes no outbound
connection (static test) and the sidecar none (the server's tests); the shell's log holds no bytes and no paths of
inputs. What the shell does not guard: another process of the same user (it can read the output folder and the
inputs anyway), and the `JAMOSET_PYLIB`/`SVF_RECOG_DIR` code the user names (their own).

## 10. Tests (D)

### 10.1 Unit tests that run in the maker suite (every slice; Python)

- `maker/test/test_toolrun.py`: `tool`, `maker_script`, `module` in source mode equal today's lists; with
  `toolrun.FROZEN` patched true they are `[sys.executable, "run-tool", name]`; `note_prefix` gives `python3 -P
  tools/<name>.py` in both modes; every `routes.routes(font).commands(...)` over `canonical_fonts()` starts with a
  `toolrun` prefix (no stray `sys.executable` list anywhere: a grep-style assertion over `maker/*.py` that the string
  `[sys.executable, "-P"` appears only in `toolrun.py`).
- `test_zipout.py`: `repo_head` reads `BUILD_ID` when present (a temp dir with the file), falls back to git, then
  "unknown"; the note of a frozen-shaped argv equals the note of the source-shaped one.
- `test_server.py` / `test_server_signals.py`: `serve --exit-with-parent`: start the server as a child of a helper
  process, kill the helper, assert the server exits 0 within 5 s and its stop sweep ran (an existing local job's files
  directory is gone).
- Existing suites updated for the new argv prefix (7.3). Gate: the whole maker suite through
  `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'` - 909 tests OK today plus the new ones;
  `tools/test_*.py`; `make -C c check`; `git diff --stat 1513dd2 -- c/src c/include` empty.

### 10.2 The frozen sidecar (runs here; needs the build)

`maker/test/test_frozen.py`, skipped unless `SVF_MAKER_SIDECAR=<path to svf-maker-sidecar>`:

- `selfcheck` JSON: `frozen` true, `flags.isolated`, `ignore_environment`, `safe_path`, `no_site` all true, `sys.path`
  has only bundle entries, `tools` lists the table of 7.1;
- under `env -i PATH=<empty dir> HOME LANG PYTHONPATH=<dir with a planted json.py>` from a cwd that also holds a planted
  `jamoset.py`: `run-tool svfline --help` exits 0 (nothing shadowed); `run-tool nosuch` exits 2;
- `run-tool mkfont ttf/neodgm/neodgm.ttf OUT --size 16 --bpp 1 --unicode ascii,ksx1001-hangul` **byte-equal** to
  `python3 -P tools/mkfont.py` (the spike's 115,460-byte check), and the same for one `jamoset --layout 844` DOS raw
  fixture (`inputfx`) and one `srcprep ttc-face`;
- `serve` under the scrubbed environment with the token and `127.0.0.1:0`: the port line within 2 s; `/` 200;
  `/static/wasm/svf.wasm` 200 `application/wasm`; `/api/caps` 403 then 200; a local job of `neodgm.ttf` to `done` with
  the face byte-equal to the source-mode job (`LocalRunBase` re-used with the server as a subprocess instead of
  in-process: the `localfx` helpers take a port); the note's command line equal to the source-mode note;
  a job with a step that blocks for more than 5 s, cancelled by SIGTERM to the server: exit 0, no process of the
  tool's group left (`pgrep -g`), the files directory gone. `test_server_signals.py` uses `python -c` steps, which the
  frozen executable cannot run, and the `run-tool` table takes no test-only name (7.1), so the builder picks a real
  tool that blocks: `jamovec master` on a large synthetic composite TTF (`inputfx`), or `mkfont` reading a FIFO as its
  source (`open` blocks until a writer appears; the test holds the writer and never writes);
- a wrong `SVF_MAKER_TOKEN` and a non-loopback `SVF_MAKER_BIND`: exit 2 with the fixed messages, nothing on stdout.

`maker/build-sidecar.sh` runs this test as its last step; the release check of `build-appimage.sh` runs it again
against `resources/sidecar/` of the extracted AppImage (`--appimage-extract`; FUSE is not available here) with
`SVF_MAKER_REPO=<extracted>/resources/repo`, plus `cmp` of the package's `svf.wasm` against a fresh `build-wasm.sh`.

### 10.3 The shell (runs here; node + xvfb)

- `desktop/test/unit.test.mjs` (`node --test`): `parsePortLine` on the exact line, a partial line, two lines, a line
  with `::1`; `isOurs` on the origin, a path, the origin with a different port, `http://localhost:<port>/`,
  `file://`, `devtools://`; `buildEnv` has exactly the keys of 6.2 (no `process.env` leak: run with a decoy
  `SVF_MAKER_TOKEN` in the test's environment and assert the built one differs and is 32 hex); the static scan of 6.9
  over `desktop/*.js` and `desktop/lib/**`.
- `desktop/test/e2e.mjs` run as `xvfb-run -a electron --no-sandbox desktop/test/e2e.mjs` (skipped when `xvfb-run` or
  the electron binary is missing): the real main process code (`desktop/main.js` exports its functions when
  `SVF_MAKER_TEST=1`) with `dialog.showOpenDialog` replaced by a stub returning a temp folder with `neodgm.ttf`, against
  the **source-mode server** (`python3 -P maker/server.py`) and, when `SVF_MAKER_SIDECAR` is set, the frozen one.
  Asserts: the handshake; the page loads with title "SVF maker"; `window.svfMaker` has the four functions and
  `platform`; `fetch("/api/caps")` from the page is 200 (the header was added) and `fetch("http://127.0.0.1:1/x")`
  rejects; `window.open` returns null and `location = "http://example.invalid/"` does not navigate; the page's
  "choose folder" -> "detect" -> "run" flow through the DOM (the selectors `test_page_dom.py` uses) ends with a done
  job and a drawn canvas (`data-drawn="1"`); "open folder" calls the stubbed `shell.showItemInFolder` with the output
  folder; closing the window stops the sidecar with exit 0 within 35 s; killing the main process with SIGKILL makes the
  sidecar exit by itself within 5 s (`--exit-with-parent`).
- The existing browser harness stays the page's gate: `test_page_dom.py` (pagedrive with `--header` and `--preload`)
  and `smoke_dom.py` run unchanged; nothing in the page changes in these cards.

### 10.4 Not verified (and where it is said in the code or docs)

Windows and macOS entirely (8.11); FUSE-mounted AppImage start (no FUSE here: only `--appimage-extract` runs);
the sandbox fallback on other distros/kernels (8.7); glibc older than 2.39 (8.10); `electronLanguages` pruning (8.6);
`fontTools.varLib` beyond `instancer --help` in the frozen build (8.3; the frozen test of 10.2 adds a real `instance`
op); `JAMOSET_PYLIB` with 3.12 wheels in the frozen process and any recogniser (7.7); native dialogs with a display
(the e2e stubs them; a human run under a real session is the manual check the release notes list);
`SOURCE_DATE_EPOCH` determinism (8.10); a real disk-full or a removed output folder during the quit sweep (the
server's own mocks cover it); the Hunspell download being the only Chromium-initiated request (6.3; the `webRequest`
cancel covers unknowns).

## 11. Task decomposition for the plan writer (E)

| Slice | Content | Verifiable by | Touches |
|---|---|---|---|
| **S1 toolrun** (first: no Electron, no build) | `maker/toolrun.py`; the 29 call sites of 7.3; `_note_token`/`note_commands` via `note_prefix`; `repo_head` + `BUILD_ID`; tests updated; `test_toolrun.py` | the maker suite (909 + new) green; `tools/test_*` green | `routes.py`, `settings.py`, `jobs.py`, `zipout.py`, `maker/test/test_routes.py`, `test_zipout.py`, `test_plan_inputs.py`, new `toolrun.py`, `test_toolrun.py` |
| **S2 sidecar** | `maker/sidecar.py` (`serve`, `run-tool`, `selfcheck`, `--version`), `serve --exit-with-parent` in `server.py`, `maker/sidecar.spec`, `maker/build-sidecar.sh` (+ `requirements-sidecar.txt`, WASM first, `BUILD_ID`), `maker/test/test_frozen.py` | build here; 10.2 green under `env -i`; the frozen local job byte-equal to source | `server.py` (the flag), new files, `.gitignore` (`desktop/build/out/`) |
| **S3 shell** | `desktop/` (package.json, main.js, preload.js, lib/, test/unit, test/e2e), the icon | 10.3 under xvfb against the source-mode server; then against S2's sidecar | `desktop/` only (the page is already bridge-aware: no change to `maker/static`) |
| **S4 AppImage** | electron-builder config, `extraResources`, `third-party.mjs`, `build-appimage.sh` with the release check (extract, frozen test, wasm cmp, licence completeness, size budget) | a 150 MB-class AppImage built here and checked extracted | `desktop/build/`, `desktop/package.json` |
| **S5 docs** | `docs/maker-desktop.md` (how to build, versions last used, the manual checks, the Windows/macOS notes of 8.11 verbatim), `maker/README.md` (a "Desktop app" section; the `run-tool` form; `SVF_RECOG_PYTHON` if D5), `NOTICE.md` (one line: the desktop package bundles third-party components listed in its THIRD-PARTY.txt), `docs/maker-audit.md` section 9 (the two cards' closing evidence), `docs/STATUS.md` | the `test_readme_and_notice_wording` test and a read-through | docs only |

Order and serialization: S1 -> S2 (S2 needs `toolrun` for the frozen job to run; both edit `maker/`), S3 can start
after S1 against the source-mode server and only its last step needs S2; S4 needs S2 and S3; S5 last (it cites the
measured numbers). Shared files: `maker/server.py` is touched by S2 only; `maker/jobs.py`, `routes.py`, `settings.py`,
`zipout.py` by S1 only; S3 and S4 touch `desktop/` only - so S1/S2 are serial, S3 runs beside S2, S4 after both.
Reviews: S1's review diffs every argv prefix before/after (a mechanical change with 29 sites); S2's review runs the
frozen test itself; S3's review runs the xvfb test; S4's review opens THIRD-PARTY.txt against `ls _internal/*.so`.

Risks, with the mitigation each slice carries:

- A missed call site in S1 (a tool launched with the old prefix fails only in frozen mode): the grep assertion of
  10.1 and the frozen job of 10.2 (which exercises mkfont, srcprep and svfdy; a jamo route and a Mac route are
  added to `test_frozen.py` so every launcher form runs frozen at least once).
- PyInstaller misses a lazy import (a fontTools table, a PIL plugin): the frozen tests run the real tools; the spec's
  `collect_submodules` covers fontTools; PIL's hook collects its plugins (PyInstaller's own hook; verified in that
  the frozen server's `GET preview/<font>/source.png` returned a PNG: `preview.source_png` renders with Pillow's
  FreeType binding inside the bundle, section 4).
- The `pkg_resources` trap and similar host-specific pulls: `excludes` in the spec, `selfcheck` as the build's last
  step, and the build runs in a venv with only the pinned three packages (the spike used the host's site-packages,
  which is where wx came from).
- The glibc floor (8.10): stated in the release notes; D9 for a container build.
- The AppImage sandbox on other distros (8.7): D7; the release notes carry the `--no-sandbox` workaround.
- GPL/LGPL libraries in the sidecar bundle (8.9): D8; the generator makes the list visible before release.
- Electron's size and the download: 151 MB is what it is; the budget line is the gate, not a goal to beat.
- The sidecar outliving a crashed shell: `--exit-with-parent` (7.9), tested in 10.3.

## 12. Left to the builder

- The exact file split of `desktop/lib/` and whether `main.js` is ESM or CJS (Electron 45 supports both; the preload
  under `sandbox: true` must be CJS).
- The icon's artwork; the `.desktop` entry's categories and comment.
- The exact message texts of the message boxes and the About box.
- The size and position persistence format (`shell-state.json` keys).
- Which fontTools subpackages to exclude beyond the measured ones (8.6), each with a frozen test of the tool that
  used it.
- The blocking step used by the SIGTERM-during-a-job frozen test (10.2).
- The handling of `JAMOSET_PYLIB`/`SVF_RECOG_DIR` pass-through when the shell is started from a desktop launcher
  with no such variables (the pass-through is simply absent; a settings UI for them is not in these cards).
- Whether `build-sidecar.sh` uses a venv or `pip --target` (both work; the venv needs `python3-venv` on Debian/Ubuntu).

## 13. README/NOTICE wording (for S5)

`maker/README.md` gains "Desktop app": how the app runs the maker (token, port 0, the handshake, `run-tool`), where
its data lives (`~/.config/svf-maker/maker`), that it makes no connection anywhere, how to build it
(`desktop/build/build-appimage.sh`, the three prerequisites: emsdk, Python 3.12 with venv, node 22 + npm), and that
Windows and macOS packages are not built or verified. `NOTICE.md` gains one sentence under "Converters for proprietary
formats" or a new short section "Desktop package": "The desktop package bundles Electron/Chromium, CPython, Pillow,
fontTools and the shared libraries they need; their licences are listed in the package's THIRD-PARTY.txt. It contains
no font that is not in `svf/`." `test_readme_and_notice_wording` is extended to assert both.

## 14. Decisions needed (the owner)

Each with my recommendation; the design above assumes the recommendation.

- **D1. A message box, not an error page, when the sidecar dies** (6.6), with restart = new token + new port, at
  most 3 restarts in 5 minutes. Alternative: a bundled `error.html` on a custom scheme (needs a navigation exception).
- **D2. `window-all-closed` quits on macOS too** (6.4): the sidecar never runs without a window. Alternative: the
  usual macOS dock-resident behaviour with the sidecar kept alive (then "quit" must still SIGTERM it).
- **D3. Persist the last output folder path in `shell-state.json`** (6.5) so the dialog reopens there. It is one
  path of the user's own folder, not an input. Alternative: remember it for the launch only.
- **D4. `run-tool` only; no `-P path.py` compatibility shim in the frozen entry point** (7.1). Alternative: keep the
  shim so an old `routes.PY` form still runs frozen (two shapes, silent).
- **D5. The optional recogniser with a frozen sidecar** (7.7): recommend an external interpreter named by
  `SVF_RECOG_PYTHON` running the shipped `repo/maker/recog_score.py` (then `repo/tools/*.py` and `repo/maker/*.py` are
  shipped as source, +2.5 MB). Alternative: `SVF_RECOG_PYLIB` appended to the frozen interpreter's path (3.12 wheels
  only). Until decided, `recog` is simply false in the package.
- **D6. Pin the versions verified here** (PyInstaller 6.22.3, Pillow 10.2.0, fontTools 4.66.1, Electron 45.2.3,
  electron-builder 26.18.0) in the build files, and move them only with a release check run. Alternative: floating
  minimums.
- **D7. No `--no-sandbox` by default** (8.7); document the workaround. Alternative: an `AppRun` wrapper that adds it
  when `/proc/sys/kernel/apparmor_restrict_unprivileged_userns` is 1 and the SUID helper is unusable (on this host it
  was not needed).
- **D8. GPL/LGPL shared libraries in the sidecar bundle** (8.9: libjbig, libimagequant, libfribidi, libgraphite2,
  libglib, libreadline). Recommend: exclude the stdlib `readline`/`curses` (drops libreadline/libtinfo), build Pillow
  from a wheel instead of Ubuntu's package (the PyPI wheel bundles its own libjpeg/libtiff/libwebp... under their
  licences and no libjbig/libimagequant - **not verified**: the spike used the Debian-packaged Pillow 10.2.0 and
  system libraries), and ship the LGPL ones with their notices (dynamic linking). Alternative: accept the list as the
  generator prints it and review before each release.
- **D9. Build the sidecar on this host (glibc 2.39 floor)** for the first release; a container build on Ubuntu 22.04
  later if a user reports an older system. Alternative: the container from the start.
- **D10. Remember window size/zoom in `shell-state.json`** (6.4, 6.8). Alternative: nothing persisted but the
  server's data.
- **D11. `--exit-with-parent` by `getppid` polling every 2 s** (7.9), POSIX. Alternative: `PR_SET_PDEATHSIG` on
  Linux as a second layer (immediate); or nothing (a crashed shell leaves a sidecar until the user kills it).
- **D12. The data root `<userData>/maker`** (`~/.config/svf-maker/maker` on Linux) rather than today's default
  `~/.local/share/svf-maker` - Electron's convention, one place to remove. Alternative: keep the server's default
  (then two users of the source-mode server and the app would share one store).
