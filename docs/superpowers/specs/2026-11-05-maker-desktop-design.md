# SVF maker desktop app: Electron shell and packaging (design)

Cards t_f04f1355 ("maker: Electron shell with the Python sidecar on 127.0.0.1") and t_e64a56a7 ("maker: packaging:
PyInstaller sidecar + Linux AppImage; Windows/macOS build notes"), goal t_afb4689b. Written 2026-11-05 on branch
`desktop` of the OFL-only repository (`svf-fonts-open`) for a builder who has not seen the repository; revised the
same day after three independent reviews (section 16 lists every finding and what was done with it) and rebased on
`main` at `94011ff` (= `1513dd2` plus the lifecycle fixes of card t_cbd14d61, which touched `maker/jobs.py`,
`maker/server.py`, `maker/test/localfx.py`, `test_local.py`; every line number below is of `94011ff`).
Every fact below was read from the tree or run on this host (Ubuntu 24.04, x86_64) unless it says "not verified" or
"UNVERIFIED"; section 4 lists what was run, and `desktop/spike/README.md` holds the exact commands and outputs with the
probe scripts, so the numbers can be re-run. Where a choice is the owner's I decided for the builder, marked "(design
call)", and collected it again in section 14 ("Decisions needed") with my recommendation; section 15 holds the
controller's rulings on the first version. The owner was not available for questions.

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
  group and cancellation path, same exit codes, the same stderr except the form of an uncaught traceback (7.1), and
  the same command line in the face's note, in `BUILD.md` and in `log.md`.
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
  endpoints. The server-side changes are the launcher helper and its consumers (7.2-7.3), the forwarded
  `JAMOSET_PYLIB` (7.4), the recogniser probe (7.7), the build id (7.8), `--exit-with-parent` (7.9), the tool registry
  (7.10) and a no-op second `Worker.stop` (6.6) - no route, tool, endpoint or page behaviour changes.
- The tailnet or systemd deployment; a multi-user server; the plain upload mode as a desktop feature (it stays
  available, D10 of the local-mode design, but the shell always runs with the token).
- The jamo recogniser (numpy + torch) inside the bundle (section 8.7 says how the optional recogniser is reached).

## 4. Constraints and facts (checked 2026-11-05 on this host unless marked)

The maker today (`94011ff`):

- `maker/server.py main()` (`:1975`) reads `SVF_MAKER_REPO` (default: the checkout above `maker/`), `SVF_MAKER_DATA`
  (default `~/.local/share/svf-maker`), `SVF_MAKER_BIND` (default `127.0.0.1:8766`; `_bind` turns `host:port` into a
  pair, no host means 127.0.0.1), `SVF_MAKER_TOKEN` (`_parse_token`: `None` when unset or empty; else exactly 32
  lower-case hex characters or `LocalModeError("SVF_MAKER_TOKEN: 32 hex characters")`, exit 2). It takes **no
  command-line arguments** today. `make_server` (`:457`) refuses a non-loopback host with the token (`"local mode binds
  127.0.0.1 or ::1 only"`, exit 2), sets `os.umask(0o077)`, computes `caps.compute(...)` **once** (`:479`; `GET /api/caps`
  at `:1772` serves that dict), builds the store and the worker, runs `startup_cleanup()` **synchronously** (`:504`,
  called at `:530`) under one deadline `STARTUP_CLEANUP_S = 30.0` (`:56`; per-folder stats up to `STAT_TIMEOUT_S`),
  then `worker.recover()`, then binds. Only then does `main` print exactly one line to stdout, `"svf-maker listening on
  %s:%d" % server.server_address[:2]`, flushed (`:1986`; for a `::1` bind the host prints **without brackets**), and
  registers `atexit.register(server.worker.stop)` (`:1987`). SIGTERM and SIGINT raise `KeyboardInterrupt` in
  `serve_forever`; `finally` (`:2003`) runs `worker.stop()` and `server_close()`; the exit code is 0
  (`test_server_signals.py` asserts it and that stderr has no traceback). `Worker.stop(timeout=30)` (`jobs.py:1060`)
  cancels the running job, `preview.kill_all()`, waits up to 30 s for the job to end, joins the thread (+1 s), then
  `sweep_local_files()` under `STOP_SWEEP_TOTAL_S = 8.0` (`jobs.py:51`); it is "idempotent" in effect but a second
  call (the `atexit` one after `finally`) **runs the sweep again** (another 8 s bound). So a busy server's stop path is up
  to 30 + 1 + 8 + 8 = 47 s. Every `/api/` request needs `X-Maker-Token`; `/` and `/static/*` need only a `Host` naming
  the server; the page is served with `Content-Security-Policy: default-src 'self'; script-src 'self'
  'wasm-unsafe-eval'; connect-src 'self'; img-src 'self' blob: data:; font-src 'self'; style-src 'self'` (`server.py
  CSP`, `:179`). `GET /api/caps` answers `{"wasm", "mask_libs", "recog", "local"}`.
- The server's paths: `repo_dir` = `SVF_MAKER_REPO`; `svf_dir = <repo>/svf` (the `RepoIndex` of every face for the
  name/byte clash rules, the chosen `repo` licence texts, `dos/NEODG16.SVF` as the Latin fallback of previews and as the
  base of the `johab844` route, `settings.py:1468`); `tools_dir = <repo>/tools` (every tool argv); `static_dir =
  <maker/>/static` (`MAKER_DIR` from `server.__file__`, `server.py:12,478`); `<repo>/web/mkindex.py` is loaded by path
  (`zipout._mkindex`) to read `<repo>/web/LICENCES.tsv` (`_existing_globs`; `[]` when unreadable; `read_licences`
  needs nothing but the stdlib); `zipout.repo_head` (`:89`) runs `git -C <repo> rev-parse HEAD` and writes "repo HEAD
  <sha>" into `BUILD.md` (`"unknown"` without git).
- Every tool launch is `routes.PY = [sys.executable, "-P"]` plus a script path (section 7.3 lists all 29 sites):
  `tools/<name>.py` through `_tool(paths, name)` (`routes.py:99`) or `os.path.join(tools_dir, name)`, `maker/srcprep.py`
  through `routes.SRCPREP` (an absolute path from `routes.__file__`, `:26`), `maker/recog_score.py` through
  `jobs.py:1514`, and the one module launch `PY + ["-m", "fontTools.varLib.instancer", ...]` (`routes.py:386`).
  `jobs.run_command` (`:315`) and `preview.run_bounded` (`:141`) run the argv with `cwd` = the step's or preview's work
  directory, `env` = `{"PATH", "HOME", "LANG": "C.UTF-8"}` (`jobs.ENV` `:221`, `preview.ENV` `:49`; a local job adds
  `TMPDIR=<files dir>/work/tmp` and `PYTHONDONTWRITEBYTECODE=1`, `jobs._job_env` `:1239`), `stdin=DEVNULL`,
  `start_new_session=True` - **so every tool is its own session and process group: a signal to the sidecar's group
  does not reach any tool**; cancellation and timeouts are `os.killpg(SIGTERM)`, wait `KILL_GRACE` = 5 s,
  `os.killpg(SIGKILL)` (`jobs._stop` `:300`); `preview.kill_all` (`:128`) SIGKILLs every bounded child at stop.
  `JAMOSET_PYLIB` is read by the server (`server.py:1418`, passed as `pylib` into `plan_steps`) and only the `mask fit`
  route puts `--pylib` on its argv (`routes.py:167`); the `experimental fit` route (`:173`) and the composite route do
  not, and the tool environment strips `JAMOSET_PYLIB`, while `jamoset.py`'s `--binarize` default is `mono`
  (`:2870`) which needs the libraries - a pre-existing gap of source mode that the frozen sidecar widens (no
  site-packages at all): section 7.4 closes it.
- Notes and logs: `zipout._note_token` (`:411`) writes `python3` for a token equal to `sys.executable` (`:419`) and
  `tools/<name>` / `maker/<name>` for a path under the checkout, but `note_commands` (`:434`) applies it **only when
  `sources` is given** (a local job); an upload job's note gets the raw argv. The johab844 comment is added when a
  token's basename is `johab844.py` (`:451`, `_johab844_comment` `:457` reads the base face from `argv[4]`).
  `_command_lines` (`:168`) writes `shlex.join(argv)` raw, and `log_step` (`:199`) uses it for `log.md`, which becomes
  `build-<id>/BUILD.md` in the user's output folder. `settings.probe_argv` (`:1402`) slices the mkfont argv by position
  (`mkfont_argv[2]` the script, `[5:]` the flags, `[:2]` the launcher, `:1408-1421`). So a local job's note reads
  `python3 -P tools/mkfont.py neodgm.ttf NEODU16.SVF ...` today, and three places assume the launcher's shape.
- The tools import each other as top-level modules (`import jamoset`, `import mkfont`, ...; each inserts its own
  directory into `sys.path` because `python -I`/`-P` drops it). Their entry contracts, read from each file: a bare
  `main()` called from the guard as `main()` (its return value ignored): `jamoset` (`:3006`), `jamovec` (`:385`),
  `mkfont` (`:773`), `bdfface` (`:285`), `johab844` (`:94`); `main(argv=None)` called as `sys.exit(main())`:
  `macfbit_svf` (`:1086`), `macfbit3` (`:354`), `macsfnt` (`:144`), `svf2to3` (`:318`), `svfdy` (`:119`), `svfline`
  (`:464`), `maker/srcprep.py` (`:542`), `maker/recog_score.py` (`:208`); `facecheck` has `main()` with
  `sys.exit(main())` (`:159`); **`jamoaa`, `jamofit`, `jamoadapt` have no `main` at all** (libraries). None reads
  `sys.argv` outside argparse. The import graph computed by `desktop/spike/import_graph.py` (every `import` statement,
  top-level or inside a function, from the roots `server` + the twelve CLIs the maker launches) reaches exactly 28
  sibling modules: `archive bdfface caps detect jamoaa jamoadapt jamofit jamoset jamovec jobs johab844 macfbit3
  macfbit_svf macsfnt mkfont naming presets preview quality routes server settings sources srcprep svf2to3 svfdy
  svfline zipout`; third-party `PIL`, `fontTools`, and the optional `freetype`, `uharfbuzz` (inside `try` in
  `jamofit`); never reached: `facecheck fontmetrics jamoexc jamofill jamomerge jamoseg recog_score svf_synth
  vesa_lines`. `fontTools.ttLib` loads its table classes by name at run time, so a freezer must collect
  `fontTools.ttLib.tables.*`. `caps.compute` imports `jamofit` (light) and uses `importlib.util.find_spec` for
  numpy/torch; `caps.recog_dir` is called again per jamo step (`jobs.py:1502`), cheap today. `tools/testdata/` holds
  only `jset1/` and `v2/` (test fixtures); `tools/testdata/mac-fbit-golden.json`, which `jamoset.MAC_GOLDEN` (`:2698`)
  would read beside `jamoset.py`, does **not** exist in this repository (`mac_golden()` returns None either way).
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
  (Ubuntu 24.04's default) and `unshare -Ur true` fails ("write failed /proc/self/uid_map: Operation not permitted"):
  unprivileged user namespaces are not available to this user.
- Pillow from PyPI (`pip install --target ... pillow==10.2.0`: `pillow.libs/` with its own `libfreetype 2.13.2`,
  `libharfbuzz`, `libraqm 0.10.1`, libjpeg, libtiff, libwebp, libopenjp2, lcms2, libpng, ...) against Debian's
  `python3-pil` 10.2.0 (system libfreetype 2.13.2, raqm 0.10.1): `mkfont` output **byte-identical** for
  `neodgm.ttf` 16 px 1 bpp (115,460 bytes) and `NanumGothic-Bold.ttf` 17 px 2 bpp (207,684 bytes). So the wheel is a
  safe reference for this host's library versions (8.10); other FreeType versions are not verified.
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
  `squashfs-root/AppRun` under `xvfb-run` printed the app's "probe ok", and the bundled sidecar started from
  `resources/sidecar/` with `SVF_MAKER_REPO=resources/repo` (port line after 145 ms, caps 200).
- **The sandbox, read from the files and `/proc` (corrects the first version of this design):** electron-builder's
  generated `AppRun` is a shell script that runs `unshare -Ur true` and, when that fails, execs the binary with
  **`--no-sandbox`** (its own fail-safe, with a comment saying so); its `.desktop` entry is `Exec=AppRun --no-sandbox
  %U`, so a launcher starts the app without the sandbox on every system. The shipped binary started directly without
  the flag dies: `FATAL ... The SUID sandbox helper binary was found, but is not configured correctly ... chrome-sandbox
  is owned by root and has mode 4755` (an AppImage mount is `nosuid`; `chrome-sandbox` in the squashfs is `0755`
  user-owned). With `--no-sandbox` the renderer's `/proc/<pid>/status` reads `Seccomp: 0`, `NoNewPrivs: 1`, the same
  user namespace as the browser process: **no renderer sandbox at all** (not even the seccomp-bpf layer). Electron's
  `app.getAppMetrics()[].sandboxed` is Windows-only and reports nothing here. On a host where `unshare -Ur` works the
  namespace sandbox would be used; **not verified** (no such host).

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

- command, packaged: `[<resources>/sidecar/svf-maker-sidecar, "serve", "--exit-with-parent=<process.pid>"]` (7.9);
  development (`SVF_MAKER_DEV=1`, or `resources/sidecar/` absent): `[python3, "-P", <checkout>/maker/server.py,
  "--exit-with-parent=<process.pid>"]` - the flag is `server.main`'s, so both launches get the parent-death handling -
  with `SVF_MAKER_REPO=<checkout>` (the checkout's `svf/`, `tools/`, `web/`; `desktop/lib/paths.mjs` resolves
  `<checkout>` as the parent of `desktop/` when `SVF_MAKER_DEV_REPO` is unset) and `SVF_MAKER_DATA=<userData>/maker-dev`
  (a separate store, so a development run never mixes with the packaged app's jobs). Everything else is the same;
  10.3's e2e runs this development command first, then the packaged one when a sidecar is built;
- `child_process.spawn(cmd[0], cmd.slice(1), {detached: true, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
  cwd: os.homedir(), env})` - `detached: true` gives the sidecar its own session, so the shell's own death or a
  terminal's SIGHUP does not reach it mid-sweep, and `process.kill(-pid, sig)` addresses the sidecar's group. **That
  group holds the sidecar only**: every tool runs in its own session (section 4), so no signal from the shell reaches
  a tool; the server kills its tools itself on SIGTERM, and the orphan case is handled by 7.10;
- `env` built by `desktop/lib/env.mjs` from scratch (not `process.env` spread): `PATH` (the user's, for nothing the
  maker needs but `jobs.ENV` reads it), `HOME`, `LANG=C.UTF-8`, `SVF_MAKER_TOKEN` = `crypto.randomBytes(16).toString("hex")`
  (new per launch, never logged, never written to disk), `SVF_MAKER_BIND=127.0.0.1:0`, `SVF_MAKER_DATA` (above),
  `SVF_MAKER_REPO` (above; packaged: `<resources>/repo`, section 8.4), and these pass-throughs only when set in the
  shell's own environment: `SVF_MAKER_ROOTS`, `JAMOSET_PYLIB`, `SVF_RECOG_DIR`, `SVF_RECOG_PYTHON` (7.7). The list is
  the one constant `ENV_KEYS` in `env.mjs`, and 10.3 pins it. On Linux `XDG_RUNTIME_DIR` and `TMPDIR` are **not** passed
  (the sidecar's own temp files for a local job go under the files directory; its process-wide `tempfile` default falls
  back to `/tmp`, as in source mode);
- the handshake: `desktop/lib/portline.mjs parsePortLine(buffer)` matches
  `/^svf-maker listening on (127\.0\.0\.1|::1):(\d+)\r?\n/m` on the accumulated stdout - the line `server.py:1986`
  prints, **terminated by its newline** (so a partial chunk `...:382` cannot yield a wrong port), `::1` unbracketed as
  the server prints it (the shell never asks for an IPv6 bind; the alternative is accepted, not used). The wait is
  bounded by `HANDSHAKE_S = 75` = `STARTUP_CLEANUP_S` 30 + the recogniser probe bound 20 (7.7) + 25 margin: the server
  does its start-up cleanup (a crash's leftovers on a slow or hung mount, up to 30 s) **before** it prints the line
  (section 4), so a short deadline would call a healthy sidecar dead. After 2 s without the line the window shows a
  "starting the maker..." page (a bundled `starting.html` loaded with `loadFile`, allowed by the guard as the one
  `file://` document of the app's own; it makes no request) so the user sees something. An exit before the line, or
  the deadline, is a start failure: the main process runs the stop sequence of 6.6 on the group (the sidecar may still
  be alive and sweeping), shows a message box with the last 20 lines of the sidecar's stderr (which never contains the
  token: `_parse_token` prints only its fixed message) and quits. The port is never read from anywhere else and is not
  configurable. The two numbers `HANDSHAKE_S` and `STOP_WAIT_S` (6.6) are written in `desktop/lib/budget.mjs` with the
  server constants they derive from, and `test_frozen.py` (10.2) asserts the server's constants are still those.

### 6.3 The token header and the session

- `session.fromPartition("maker")` - no `persist:` prefix, so cache, cookies and storage are in memory and leave with
  the process (the byte endpoints of a local job answer `no-store` already; this keeps even `/static/*` off the disk).
- The current sidecar is one mutable object `sidecar = {child, port, origin, token}` in `main.js`, replaced as a
  whole by every (re)start (6.6); **every handler below reads `sidecar.origin`/`sidecar.token` at call time**, none
  captures them in a closure, so a restart with a new port and token needs no re-registration except the one filter
  that takes URLs:
- `ses.webRequest.onBeforeSendHeaders({urls: ["http://127.0.0.1/*"]}, ...)` - the filter is registered **once** on the
  host pattern (Electron's URL patterns match the host, not the port, so one registration covers every port the sidecar
  may get); the handler itself checks `details.url.startsWith(sidecar.origin + "/")` and, for a `pathname` starting with
  `/api/`, sets `requestHeaders["X-Maker-Token"] = sidecar.token` (assign, so there is exactly one; delete any
  `x-maker-token` spelled otherwise); every other URL is passed unchanged. A request to an old port after a restart
  gets no header (and the guard below cancels it).
- `ses.webRequest.onBeforeRequest({urls: ["<all_urls>"]}, (details, cb) => cb({cancel: !isOurs(details.url)}))` with
  `isOurs(url)` = `url === sidecar.origin + "/" || url.startsWith(sidecar.origin + "/")` or the app's own
  `starting.html` `file://` URL (6.2) (exact string prefix; `desktop/lib/guard.mjs` takes the origin as an argument so
  the unit test needs no Electron), `devtools://` allowed only when devtools are enabled (6.8). The sidecar's CSP
  (`connect-src 'self'` ...) is the first layer, verified in section 4; this is the second, and it also covers requests
  the page does not make itself (favicons, prefetch, a dictionary download). `webPreferences.spellcheck = false`
  (Electron's Hunspell dictionary download is the one outbound request Chromium would make on its own).
- `ses.on("will-download", (e) => e.preventDefault())`: the page's `download zip` link exists for upload jobs
  (`maker.js:573`); the app never saves a download (a local job writes its folder itself), so no write path exists
  outside the server. The link is hidden for local jobs anyway.
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

`desktop/main.js` handlers (`ipcMain.handle`), each first checking that `event.senderFrame` is not null (a frame
navigated away or destroyed) and `new URL(event.senderFrame.url).origin === sidecar.origin` (any other sender gets a
rejected promise and a log line):

- `maker:pick-files`: `dialog.showOpenDialog(win, {properties: ["openFile", "multiSelections"], defaultPath:
  lastInputDir})` -> `canceled ? [] : filePaths` (absolute paths as the OS gives them; no normalisation: the server
  realpaths and checks them, local-mode design 7.1);
- `maker:pick-folder`: `{properties: ["openDirectory"]}` -> `[]` or `[dir]` (two dialogs because Electron cannot
  combine `openFile` and `openDirectory` on Linux and Windows: the local-mode design's reason);
- `maker:pick-output-dir`: `{properties: ["openDirectory", "createDirectory"], defaultPath: lastOutputDir}` ->
  `null` or the path; the main process adds it to `handedOut` (the set of output folders this shell gave the page, in
  any launch, persisted in `shell-state.json` - D3 ruled the path may be persisted) and uses the last one as the next
  dialog's `defaultPath`;
- `maker:open-output`: the page's **open job** decides the folder, not the last dialog (the page can show an older
  job from its list, a reloaded `?job=` or the job restored after a restart - `maker.js:2054,2238-2240` set
  `state.output` from the job, and the audit's contract says "the job's output folder"): the handler reads `?job=<id>`
  from `win.webContents.getURL()`, does `GET /api/jobs/<id>` itself from the main process (with `sidecar.token`; the
  one request the main process makes, to `sidecar.origin` only), takes `output_dir`, and reveals it with
  `shell.showItemInFolder(path)` **only if it is in `handedOut`** (a folder the shell's own dialog returned); otherwise
  nothing and a log line. No path from the page is ever opened (the page shows `output_dir` as text only); never
  `shell.openPath`, which executes files.

No other IPC channel exists; `ipcRenderer` is not exposed; the bridge object is frozen by `contextBridge`.

### 6.6 Quit, crash, and what happens when the sidecar dies

- Quit sequence: `app.on("before-quit")` is reached from the window's close (`window-all-closed` -> `app.quit()`;
  the window is already gone on that path, so nothing is shown), the menu, `second-instance` on the loser, and the
  signals - Electron's main process does **not** turn SIGINT/SIGTERM into `before-quit` by itself, so `main.js`
  installs `process.on("SIGINT"|"SIGTERM"|"SIGHUP", () => app.quit())`. The handler does `e.preventDefault()` once, then
  `desktop/lib/shutdown.mjs stopSidecar(sidecar)`: `process.kill(-child.pid, "SIGTERM")`; wait for `exit` up to
  **`STOP_WAIT_S` = 45 s** (= `Worker.stop`'s 30 s for a running job + the thread join 1 s + `STOP_SWEEP_TOTAL_S` 8 s +
  6 s margin, section 4); then `process.kill(-child.pid, "SIGKILL")` and wait up to 5 s more; then `app.exit(0)`. The
  server side is made to fit that number: `Worker.stop` records that it completed and the `atexit` second call returns
  at once (today it sweeps a second time, up to 8 s more: `jobs.py:1060`, `server.py:1987`; the change is one flag,
  slice S2). While waiting, a "stopping the maker..." line goes to the log. A SIGKILL leaves `.svf-maker-<id>/` in the
  output folder until the next start's `recover` sweep (local-mode design 8.3) and may leave a tool running (7.10) -
  that is the server's rule and the shell relies on it.
- Electron crashes (the main process is killed, segfaults, OOM): the sidecar is in its own session and would survive;
  `serve --exit-with-parent=<pid>` (7.9) makes it notice within 2 s and run the same `finally` as SIGTERM, with its
  stdout/stderr pipes replaced first (they lead to the dead shell). So the only way to orphan a tool child is to
  SIGKILL the sidecar itself, which the shell does only after the 45 s wait - and 7.10 says how such an orphan is
  found and killed before anything sweeps its directories.
- The sidecar dies on its own (`child.on("exit")` while not quitting; a Python crash, an OOM kill, a user `kill`):
  the main process logs the exit code/signal and the stderr tail, shows a `dialog.showMessageBox` "The maker stopped
  (exit N). Restart it? [Restart] [Quit]"; Restart replaces `sidecar` with a new spawn (**new token, new port**; the
  handlers of 6.3 read the new values at call time; the header filter is host-wide, so nothing is re-registered),
  waits for the handshake (6.2's deadline: the new sidecar's `startup_cleanup` first reaps the orphaned tools, 7.10,
  then sweeps), and `win.loadURL(sidecar.origin + "/")`; the navigation guard reads `sidecar.origin` at that moment, so
  the load is allowed. The page's job list comes from the data directory, so the user's finished jobs are still there
  (a running job is `failed (interrupted)` by `recover`). At most 3 restarts in 5 minutes; then only Quit. No separate
  error page is bundled (design call: a message box needs no navigation exception and no second origin; the
  `starting.html` of 6.2 is the one static document and it is the app's own file).
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
svf-maker-sidecar serve [--exit-with-parent=PID] -> maker/server.py main(argv)   (env as today; section 6.2)
svf-maker-sidecar run-tool NAME ARGS...          -> one of the CLIs below; exit code = the tool's
svf-maker-sidecar selfcheck                      -> JSON on stdout: {"frozen", "version", "build_id", "python",
                                                    "flags": {"isolated", "ignore_environment", "safe_path",
                                                    "no_site"}, "path": sys.path, "tools": [names],
                                                    "modules": [every module of 7.1's graph, imported, with errors],
                                                    "budget": {"startup_cleanup_s", "stop_timeout_s", "stop_sweep_s"}}
svf-maker-sidecar --version                      -> "svf-maker-sidecar <version> <build id> python <x.y.z>"
```

`run-tool` resolves `NAME` against a fixed table (design call: a table, not `importlib.import_module(NAME)` of
anything) built from **each tool's real entry contract** (section 4; the first version of this design named
`facecheck` and `recog_score` too - `facecheck` is never launched by the maker and shells out to `git`; `recog_score`
runs under the external interpreter of 7.7 - both are out):

| `NAME` | module | entry | guard form in the file | how `run-tool` calls it |
|---|---|---|---|---|
| `jamoset`, `jamovec`, `mkfont`, `bdfface`, `johab844` | `tools/<name>.py` | `main()` | `main()` (return value ignored) | `sys.argv = [NAME + ".py", *ARGS]; main(); exit 0` (a `SystemExit` inside propagates as it does today) |
| `macfbit_svf`, `macfbit3`, `macsfnt`, `svf2to3`, `svfdy`, `svfline` | `tools/<name>.py` | `main(argv=None)` | `sys.exit(main())` | `sys.argv = [...]; sys.exit(main())` (so `None` -> 0, an int -> that code, exactly the guard) |
| `srcprep` | `maker/srcprep.py` | `main(argv=None)` | `sys.exit(main())` | the same |
| `instancer` | `fontTools.varLib.instancer` | `main(args=None)` | (`python -m`: `sys.exit(main())`) | `sys.exit(main(ARGS))` |

`sys.argv[0]` is `NAME + ".py"` so argparse's `prog`, usage lines and error messages are the ones the tools print today
(verified: `usage: jamoset.py ...`). An uncaught exception is caught by `run-tool`, printed with
`traceback.print_exc()` and exits 1 - the frozen bootloader would otherwise print a traceback without source lines plus
its own `[PYI-<pid>:ERROR] Failed to execute script` line; with the catch, stderr differs from `python3`'s only in the
absent source lines of the traceback (the goal of section 2 says so). An unknown name prints `run-tool: unknown tool
'X'` and exits 2. **One small function per table entry holds that entry's `import`** (design call: PyInstaller's
analysis follows function-level imports - verified: `jamoadapt`, imported only inside functions of `jamoset`,
`jamoaa` and `jamovec`, is in the spike's PYZ without a hidden import - and a `run-tool mkfont` must not import the
server, Pillow and every other tool first: the 0.03-0.05 s start-up of section 4 was measured with hidden imports,
which do not execute). `serve` imports `server` the same way. In source mode the entry point inserts `maker/` and
`tools/` into `sys.path` first, as `server.py` does. The library modules (`jamoaa`, `jamofit`, `jamoadapt`) are not
entries: they reach the bundle through the graph, and `selfcheck`'s `modules` item imports every module of the graph by
name so a missing one is a failed self-check, not a failed job. The graph itself is computed, not typed:
`desktop/spike/import_graph.py` is promoted to `maker/test/test_sidecar_imports.py`, which asserts that the frozen
sidecar's `selfcheck.modules` covers the reachable set the test computes from the sources at test time (28 modules
today, section 4).

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

def split_prefix(argv):
    """`(prefix, rest)`: the launcher tokens of @p argv and what follows them, recognising BOTH shapes whatever mode
    this process is in: [py, "-P", <path>.py] (3), [py, "-P", "-m", dotted] (4), [sidecar, "run-tool", name] (3).
    ValueError for anything else. Every consumer that today slices argv by position uses this."""

def note_prefix(argv):
    """`(prefix_tokens_for_the_note, rest)`: `split_prefix`, with the prefix rewritten as the note shows it in BOTH
    modes: ["python3", "-P", "tools/<name>.py"], ["python3", "-P", "maker/<name>.py"] (srcprep, recog_score) or
    ["python3", "-P", "-m", dotted]; the name of a frozen `run-tool` token maps back to its file."""
```

`tool(name, tools_dir)` takes the name without `.py` (so the call sites change from `_tool(paths, "mkfont.py")` to
`toolrun.tool("mkfont", paths["tools"])`). The **prefix is three tokens in both modes** for `tool` and `maker_script`
and four/three for `module`; nothing may rely on that: `split_prefix` is the one place that knows the shapes, and the
three positional consumers found in the code (section 4: `settings.probe_argv`'s `[2]`/`[5:]`/`[:2]`,
`zipout._johab844_comment`'s `argv[4]` and the `basename == "johab844.py"` test of `note_commands`) are rewritten on
it (7.3). `note_prefix` is applied to **every** command line the maker writes - `_command_lines` (hence `log_md`,
`BUILD.md`, `log_step`) and both branches of `note_commands` (upload jobs too, which today get the raw argv) - **before**
the johab844 detection, so the note, `BUILD.md` and the log are **the same text in source and frozen mode**
(`python3 -P tools/mkfont.py ...`, verified today's form in section 4; a test pins all three in both modes, and that a
frozen `run-tool johab844` argv still gets its comment line). `FROZEN` is read once at import; tests set
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
| `maker/jobs.py:1502,:1514` `_identity`: `caps.recog_dir(os.environ)` per step, then `routes.PY + [<maker/>/recog_score.py, ...]` | the recogniser launch | `toolrun.recog_argv(self.caps)` (7.7): `[SVF_RECOG_PYTHON, "-P", <repo>/maker/recog_score.py, ...]` when the external interpreter is configured, else today's `[sys.executable, "-P", <maker/>/recog_score.py]` in source mode; no per-step probe (the result is in `self.caps`) |
| `maker/caps.py` `recog_dir`, `compute` | `find_spec("numpy")`/`("torch")` in this process | `compute` probes the external interpreter once at start (7.7) and keeps `recog_python` beside `recog`; `recog_dir` unchanged for source mode without `SVF_RECOG_PYTHON` |
| `maker/jobs.py:221` `ENV`, `maker/preview.py:49` `ENV` | `{PATH, HOME, LANG}` | plus `JAMOSET_PYLIB` when it is set in the server's environment (7.4); `test_local.py:1834` patches `jobs.ENV["HOME"]` and keeps working |
| `maker/zipout.py:419` `_note_token`: `token == sys.executable -> "python3"`, a path under the checkout -> `tools/<name>` | per token, local jobs only | the launcher prefix is handled by `toolrun.note_prefix` first, for every job; `_note_token` keeps the per-token rules for the rest of a local job's argv |
| `maker/zipout.py:434-455` `note_commands` (the `sources is None` branch leaves the raw argv; the johab844 test is `basename == "johab844.py"` over `argv[:4]`), `:457` `_johab844_comment` (`argv[4]`) | positional | every argv goes through `note_prefix` **first**, in both branches; the johab844 test becomes `rest[0]`'s name after `split_prefix`; `_johab844_comment` reads the base face from `rest[2]` |
| `maker/zipout.py:168` `_command_lines` (raw `shlex.join(argv)`; used by `log_step` `:199` -> `log.md` -> `BUILD.md`) | raw | `note_prefix` on every argv before `shlex.join`, so `BUILD.md` never carries the AppImage's random mount path |
| `maker/settings.py:1402-1421` `probe_argv` (`mkfont_argv[2]`, `[5:]`, `[:2]`) | positional | `prefix, rest = toolrun.split_prefix(mkfont_argv)`; `rest[0]` is the source, `rest[1]` the output, `rest[2:]` the flags; the probe argv is `prefix + [src, out_svf, "--size", ...]` |
| `maker/preview.py:191-251` `bake_source_face`, `maker/server.py:1637-1712` the probe, `:1839-1879` source conversions | build argv through `routes.*` / `settings.*` | no change: they inherit |
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
- Environment scrubbing: the tool's environment is the three (or five) keys the maker sets today **plus
  `JAMOSET_PYLIB` when the server itself has it** (`jobs.ENV` and `preview.ENV` gain it at import time, like `PATH`):
  today the key is stripped, so a `binarize mono` on the `experimental fit` or `composite` route (which do not pass
  `--pylib`, `routes.py:173`; `jamoset`'s default is `mono`, `:2870`) finds the libraries only when they are in the
  interpreter's site-packages - which the frozen interpreter never has. Forwarding the one key keeps the scrub and
  makes the frozen behaviour equal to a source-mode host with the libraries installed; `caps.mask_libs` already tells
  the page whether the route is on offer. The frozen tool needs nothing else (verified under `env -i PATH=<empty
  dir>`): PyInstaller's bootloader sets `LD_LIBRARY_PATH` for its own process from the bundle path and the `_PYI_*`
  keys for itself, both inside the child; they are not required from the parent. `PYTHONDONTWRITEBYTECODE=1` is moot in
  the frozen process (`dont_write_bytecode=1` is built in) and harmless. `TMPDIR` is honoured by the frozen `tempfile`
  as by `python3`.
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
`web/FAMILIES.tsv`, `BUILD_ID` (7.8), and - because D5 is ruled (the external recogniser interpreter, 7.7) -
`maker/*.py` and `tools/*.py` **as source, without `test_*.py` and without `testdata/`** (2.5 MB; the files
`recog_score.py` and its imports need under another interpreter). The frozen server itself does not read
`repo/tools/` (the code is in the bundle and `tools_dir` is only joined into argv by `toolrun.tool`, which ignores it
when frozen). `tools/testdata/` is test fixtures only; the golden file `jamoset.MAC_GOLDEN` would read does not exist
in this repository (section 4), so no data file is missing from the bundle today - if one is ever added beside
`jamoset.py`, it goes into the spec's `datas` as `testdata/` (the frozen `__file__` directory is `_internal/`) and into
`repo/tools/testdata/`, and `test_sidecar_imports.py` lists every `os.path.join(os.path.dirname(__file__), ...)` in
the reachable modules so such a file cannot be forgotten silently.

### 7.6 Static files

`server.static_dir` is `<dirname(server.__file__)>/static`; in the bundle `server.__file__` is `<_internal>/server.pyc`,
so `maker/static/` (with the built `wasm/`) is added as data `static/` -> `<_internal>/static/` (verified: `/static/maker.js`
and `/static/wasm/svf.wasm` served from the frozen sidecar). No code change. The `sys.path.insert` lines of
`server.py:14-16` and `srcprep.py` add `<sidecar dir>/tools` and a duplicate `_internal` entry when frozen (harmless;
the review's probe saw them), so `selfcheck`'s path rule is "every entry is under the sidecar's own directory", not
"only the three bundle entries".

### 7.7 Optional libraries: `JAMOSET_PYLIB` and `SVF_RECOG_DIR` with a frozen sidecar

- `mask fit` / `binarize mono` need freetype-py and uharfbuzz from `JAMOSET_PYLIB`; `jamofit.load_libs` appends that
  directory to `sys.path` and imports them. In the frozen process this works only when the directory holds builds for
  **CPython 3.12 on the same platform** (uharfbuzz is a compiled extension; freetype-py loads the system `libfreetype`
  through ctypes). The shell passes `JAMOSET_PYLIB` through when set; `caps.mask_libs` stays false otherwise and the
  routes are not offered - no new failure mode, and `maker/README.md` says what the directory must contain.
- The identity check needs numpy and torch (hundreds of MB; never bundled). D5 (ruled, section 15) is **an external
  interpreter**, and this is its complete path, each place named:
  - the shell passes `SVF_RECOG_PYTHON` (and `SVF_RECOG_DIR`) through when set (6.2's `ENV_KEYS`; the first version
    dropped it);
  - `caps.compute(static_dir, environ, local)` (`caps.py`, called once in `make_server`, `server.py:479`) gains:
    when `SVF_RECOG_PYTHON` names an executable and `SVF_RECOG_DIR` a directory with `recog.py`, it runs
    `[SVF_RECOG_PYTHON, "-I", "-c", "import numpy, torch, PIL, fontTools"]` **once**, bounded (20 s, `subprocess.run`
    with a scrubbed environment), and sets `recog = (returncode == 0)` and a private `recog_python = <path>` (the
    dict served by `/api/caps` is filtered to booleans, `server.py:1772`, so the path never leaves the server); the
    probe imports the four packages `recog_score.py` needs through `detect`, `jamoset`, `mkfont` (section 4), not
    numpy/torch alone. Without `SVF_RECOG_PYTHON`, today's `find_spec` rule stands (source mode on a host with torch
    installed); the frozen sidecar then reports `recog: false` since it excludes numpy/torch;
  - `jobs.Worker._identity` (`:1502-1514`) no longer calls `caps.recog_dir` per step: it reads `self.caps["recog"]`
    and `self.caps.get("recog_python")`, and `toolrun.recog_argv(caps, repo_dir)` gives `[recog_python, "-P",
    <repo_dir>/maker/recog_score.py, FACE, "-o", ...]` for the external interpreter (the script and the modules it
    imports - `detect`, `jamoset`, `mkfont`, and theirs - are shipped **as source** under `<resources>/repo/maker/` and
    `<resources>/repo/tools/`, 7.5: a frozen bundle's `.pyc` inside the PYZ cannot be run by another interpreter) or
    today's `[sys.executable, "-P", <maker/>/recog_score.py, ...]` when no external interpreter is set and the
    process is not frozen; the step's environment gets `SVF_RECOG_DIR` as today (`:1517`);
  - `recog_score.py` itself is unchanged: its `sys.path.append` lines put the shipped `maker/` and `tools/` sources
    on the path of the external interpreter, and it inserts `SVF_RECOG_DIR` for `recog` (`:241`).
  The test (10.2) runs it twice: with no configuration (`recog: false`, the page says unavailable) and with a stub
  `SVF_RECOG_PYTHON` = the host's `python3` plus a stub `recog.py` (`test_recog_score.py`'s) against the frozen sidecar,
  asserting a jamo step got its `identity.json`.

### 7.8 The build id instead of `git rev-parse`

`zipout.repo_head(repo_dir)` first reads `<repo_dir>/BUILD_ID` (one line, stripped, at most 200 characters) and
returns it when the file exists; otherwise `git` as today **but only when not frozen** (a frozen process's
`os.environ` carries the bootloader's `LD_LIBRARY_PATH=<_internal>`, under which `git` could load the bundle's libz
or libcrypto; frozen without `BUILD_ID` is `"unknown"`); otherwise `"unknown"`. `maker/build-sidecar.sh` writes
`BUILD_ID` = `<git describe --always --dirty> <ISO date of the commit> sidecar <version>` into the resources tree
(e.g. `1513dd2 2026-11-05 sidecar 0.1.0`), so `BUILD.md`'s "repo HEAD ..." line names the source of the faces a user
made with the app. `git` is not needed on the user's machine and is not in the tool environment anyway.

### 7.9 `serve --exit-with-parent=PID` (one of the two new server flags)

`server.main(argv=None)` gains an `argparse` parser with this one option (today it takes no arguments, section 4).
The expected parent pid is **passed by the shell** (`process.pid`), not read by the sidecar: a shell that dies during
the sidecar's own start-up would already have left `os.getppid()` at 1 or a subreaper, and a value recorded then
would never change again. A daemon thread started **before** `make_server` (so the 30 s start-up cleanup is covered
too) polls `os.getppid()` every 2 s; when it is not `PID`, it (1) `os.dup2`s `/dev/null` onto fds 1 and 2 - the pipes
lead to the dead shell, Python ignores SIGPIPE, and every `print(..., file=sys.stderr)` on the stop path (`sweep:`
lines, `print_exc`) would raise `BrokenPipeError` and could abort the sweep - and (2) raises the same shutdown as
SIGTERM (`os.kill(os.getpid(), SIGTERM)`), so a crashed shell never leaves a serving sidecar behind. Off by default
(the tests and the manual `python3 -P maker/server.py` run keep today's behaviour). POSIX-only, like the rest of the
server (on Windows there is no re-parenting; the Windows port of 8.11 would use a Job Object). On Linux the sidecar
additionally sets `prctl(PR_SET_PDEATHSIG, SIGTERM)` through `ctypes` at the same point (immediate, no 2 s poll;
D11's second layer), guarded by `sys.platform == "linux"` and a `try` (a failing `prctl` is logged, not fatal).

### 7.10 Tools that outlive the sidecar (the orphan rule)

Every tool is its own session (section 4), so neither the shell's group signal nor the sidecar's death reaches it. A
tool outlives the sidecar in exactly two cases: the shell SIGKILLs the sidecar after `STOP_WAIT_S` (6.6), or the
sidecar itself dies (crash, OOM kill, `kill -9`). The next sidecar start then sweeps `.svf-maker-<id>/` directories
(`startup_cleanup`, `recover`) that such a tool may still be writing. The rule, with the two layers that enforce it:

1. **The registry.** `jobs.run_command` and `preview.run_bounded` (the two runners, nothing else spawns) append one
   line `"<pgid> <leader pid> <start time> <argv[0]>\n"` to `<data_root>/tools.pids` right after `Popen` (the start
   time is `/proc/<pid>/stat` field 22 on Linux and `ps -o lstart= -p` on macOS; it guards against pid reuse) and
   remove it when the child is reaped (`run_command`'s `finally`, `run_bounded`'s end). The file is one line per
   live tool, under the data root (never under an output folder), written through a lock file, and holds no path of
   an input (`argv[0]` is the launcher). `make_server` reaps it **first**, before `startup_cleanup()` and `recover()`:
   for each line whose leader still exists with the same start time and whose `argv[0]` is this launcher (`sys.executable`
   in frozen mode; `python3` in source mode: the start time is the real guard), `os.killpg(pgid, SIGKILL)`, wait for
   the leader to vanish (bounded, 5 s per entry, `REAP_TOTAL_S` = 10 s overall inside the start-up budget of 6.2), then
   truncate the file. So a sweep never races a tool of a previous sidecar: either the tool is dead or the sidecar does
   not start (an un-killable process is logged and the start proceeds; `D`-state processes cannot be waited for).
2. **`PR_SET_PDEATHSIG` in the tool.** On Linux, `run-tool` (frozen) sets `prctl(PR_SET_PDEATHSIG, SIGKILL)` first
   thing, so a tool dies with its sidecar at once. Source-mode tools (`python3 -P tools/X.py`) cannot get it without a
   change in every tool, and `Popen(preexec_fn=...)` is documented unsafe in a threaded process (the server has
   handler threads), so source mode relies on layer 1 alone. (The prctl in `run-tool` is not verified yet: 10.2 adds
   the test.)

The test (10.2, "SIGKILL the sidecar during a tool"): a frozen local job whose step is `jamovec master` on a large
synthetic composite TTF (minutes; the design's blocking step, since a FIFO is refused by `sources.py` - a source must
be a regular file or folder); SIGKILL the sidecar while the tool runs; assert within 3 s that the tool is gone
(layer 2) - then the same with `PR_SET_PDEATHSIG` disabled by an env knob `SVF_MAKER_NO_PDEATHSIG=1` (test-only):
the tool survives, `tools.pids` names it, a new sidecar start kills it before its first sweep (the directory is
gone after the start and no tool of that pgid exists), and the job is `failed (interrupted)`.

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
from PyInstaller.utils.hooks import collect_submodules
ROOT = os.path.abspath(SPECPATH + "/..")
# fontTools loads table classes by name at run time: the lists must be COMPUTED BEFORE Analysis() and passed to it
# (mutating a.hiddenimports afterwards does nothing: the graph is already built - a review built the first version
# of this spec and found 9 of 29 fontTools.pens modules in the PYZ).
HIDDEN = (["fontTools.varLib.instancer"] + collect_submodules("fontTools.ttLib")
          + collect_submodules("fontTools.pens") + collect_submodules("fontTools.varLib"))
a = Analysis([os.path.join(ROOT, "maker", "sidecar.py")],
             pathex=[os.path.join(ROOT, "maker"), os.path.join(ROOT, "tools")],
             datas=[(os.path.join(ROOT, "maker", "static"), "static")],       # index.html, *.js, style.css, wasm/
             hiddenimports=HIDDEN,
             hookspath=[], runtime_hooks=[],
             excludes=["wx", "fontTools.ui", "brotli", "_brotli", "zopfli", "lxml", "unicodedata2", "lz4", "numpy",
                       "torch", "scipy", "matplotlib", "sympy", "tkinter", "gi", "PIL.ImageQt", "PIL.ImageTk",
                       "xattr", "pkg_resources", "setuptools", "jaraco", "freetype", "uharfbuzz", "pathops",
                       "readline", "curses", "_curses", "test", "unittest.mock"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="svf-maker-sidecar", console=True, upx=False,
          strip=False)                                   # strip/upx: off (reproducibility, antivirus; 8.10)
coll = COLLECT(exe, a.binaries, a.datas, name="svf-maker-sidecar")
```

Points: the tools are reached by the entry point's per-entry import functions (7.1), so no `--hidden-import` per
tool; the three `collect_submodules` cover fontTools' run-time imports and are passed **into** `Analysis` (the spike
used the equivalent command-line flags, which is why it worked); `fontTools.varLib` whole is for `instancer`'s own lazy
imports - verified only by `--help` in the spike, so 10.2 runs a real `instance` op (a variable-font fixture of
`inputfx`) and a real TTC face read in the frozen build; `excludes` names what the spike measured as dead weight (wx +
GTK alone were 60 MB), the Debian `pkg_resources` trap, `readline`/`curses` (the D8 ruling: they pull libreadline and
libtinfo, GPL-3) and the recogniser/mask libraries (never bundled; 7.7); `console=True` so stdout is a pipe (the
handshake) and on Windows a console is not shown because the shell spawns with `windowsHide`. If tracebacks with
source lines matter to the owner, `module_collection_mode={"<tool>": "pyz+py"}` in `Analysis` ships the tools'
sources beside the `.pyc` (not required by this design: 7.1 reworded the goal). `maker/build-sidecar.sh` runs
`pyinstaller --noconfirm --clean --distpath desktop/build/out/sidecar maker/sidecar.spec` from a `venv` the script
creates (`python3 -m venv` needs `python3-venv` on Debian/Ubuntu; the script says so and falls back to `pip install
--target`, which is what worked here) **holding only the pinned wheels** `pyinstaller==6.22.3 pillow==10.2.0
fonttools==4.66.1` of `desktop/build/requirements-sidecar.txt` (the versions verified here; D6 ruled to pin; the venv
is also what keeps host packages such as wx out of the graph), builds the WASM module first (8.5), then writes
`BUILD_ID` and runs `svf-maker-sidecar selfcheck` as its last step.

### 8.4 The resources layout of the packaged app

```
<AppImage>/resources/
  app.asar                      desktop/main.js, preload.js, lib/, package.json  (electron-builder's default)
  sidecar/svf-maker-sidecar     PyInstaller one-dir (executable + _internal/ with static/ and wasm/)
  repo/svf/...                  the faces and licence texts, copied whole from svf/ (12 MB)
  repo/web/mkindex.py, LICENCES.tsv, FAMILIES.tsv
  repo/BUILD_ID
  repo/tools/*.py, repo/maker/*.py   sources for the external recogniser interpreter (D5 ruled; no tests, no __pycache__)
  THIRD-PARTY.txt sources: desktop/build/out/sources/   (beside the AppImage, not inside it: the copyleft source archive, 8.10)
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
| Sidecar port line | 96 ms (145 ms from the extracted AppImage) on a clean data root | <= 2 s clean; up to 30 s after a crash with leftovers on a slow mount (`STARTUP_CLEANUP_S`), + 20 s for the recogniser probe (7.7): the shell waits `HANDSHAKE_S` = 75 s (6.2) |
| Tool launch overhead | +0.1 s per launch (mkfont 16 px: 0.30-0.34 s frozen vs 0.24 s source) | <= +0.3 s |
| SIGTERM to exit, idle | 16 ms; 200 ms after a finished job | <= 39 s with a running job (30 + 1 + 8, section 4, after the `atexit` double-sweep is made a no-op): the shell waits `STOP_WAIT_S` = 45 s (6.6) |
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

**Sandbox (Linux) - the facts of section 4, which correct the first version of this design and the D7 ruling built on
it.** Chromium's SUID sandbox helper cannot be setuid inside an AppImage (FUSE mounts are `nosuid`; the binary without
the flag aborts with the FATAL SUID message), so the only sandbox an AppImage can have is the user-namespace one, and
Ubuntu 24.04 denies unprivileged user namespaces by AppArmor (`unshare -Ur` fails here). electron-builder's own
`AppRun` already does what D7's "alternative" described: it probes `unshare -Ur true` and adds `--no-sandbox` when
that fails, and its `.desktop` entry adds the flag unconditionally. So **on this host, and on every Ubuntu 24.04-class
system, the packaged app runs with no renderer sandbox at all** (Seccomp 0); on a system with user namespaces it
would run sandboxed (not verified). The design's position, replacing D7 (new D7 in section 14): keep electron-builder's
`AppRun` as it is (the app would not start otherwise), and make the state visible and honest - the main process logs
`app.commandLine.hasSwitch("no-sandbox")` and the renderer's `/proc/<pid>/status` `Seccomp`/`NoNewPrivs` at start
(`desktop/lib/sandbox.mjs`, Linux only), the About box shows "renderer sandbox: off (user namespaces unavailable)" or
"on", `docs/maker-desktop.md` says which systems get which and why, and 10.3 records the state of its own run. The
content the renderer handles is the app's own page and files the user picked, from a server on 127.0.0.1, with no
remote content ever (6.3); that is the argument for shipping without the sandbox, stated, not hidden. A `.deb` target
(electron-builder generates an AppArmor profile that grants `userns` to `/opt/<app>/<exe>`) would restore the sandbox
on Ubuntu 24.04 for users who install a package rather than run an AppImage - a later card, not these (D13).

### 8.8 Versioning and the build id

`desktop/package.json` `version` is the app's (semver, starts 0.1.0); the sidecar prints the same (`--version`,
from a `maker/VERSION` file the build script writes - or `importlib.metadata` is avoided on purpose: there is no
package); `BUILD_ID` (7.8) carries the git describe. The About box shows all three. A mismatch between the sidecar's
and the app's version is logged at start (not fatal).

### 8.9 `THIRD-PARTY.txt` generation

`desktop/build/third-party.mjs` writes `<resources>/THIRD-PARTY.txt` from **four** sources, each with the component,
version, licence name, the full licence text, and - new in this revision - a **distribution record** (where the
corresponding source is, how the component may be replaced) for every copyleft component. The attribution map is a
checked-in file, `desktop/build/third-party-map.json`: one entry per native library file name pattern
(`libfreetype-*.so.6*`, `libharfbuzz.so.0`, ...) with `component`, `version` (or `from: "dpkg"` / `from: "wheel"`),
`licence` (SPDX), `source_url`, `copyleft: none|lgpl|gpl`; the generator fails on any file in the bundle that no entry
matches (fail closed), and on any `gpl` entry (section 8.10's GPL rule). The sources:

1. Electron and Chromium: `node_modules/electron/dist/LICENSE` (Electron, MIT) and `LICENSES.chromium.html` (every
   Chromium third-party notice; electron-builder copies them into the package as `LICENSE.electron.txt` and
   `LICENSES.chromium.html` - verified in `linux-unpacked/`; the generated file points at those two and inlines
   Electron's). Electron's `libffmpeg.so` is **LGPL-2.1** (Chromium's ffmpeg build): it needs the distribution record of
   8.10 like the sidecar's LGPL libraries;
2. the npm packages that ship inside `app.asar` - with the recommended design there are **none** (`desktop/` has no
   runtime dependency; Electron is a devDependency); the script fails if `dependencies` is non-empty and not listed;
3. the sidecar: CPython (PSF-2.0; `_internal/base_library.zip`, `libpython3.12`; from the build host's `python3`,
   attributed through `dpkg`), Pillow and fontTools (HPND, MIT: from the wheels' `*.dist-info/METADATA` and
   `dist-info/licenses/` or `LICENSE` files in the build venv), and **every shared library PyInstaller collected** into
   `_internal/`, attributed by **two paths**: a file inside a wheel's `*.libs/` directory (Pillow's `pillow.libs/`:
   `libfreetype-<hash>.so.6.20.1`, `libharfbuzz-<hash>.so.0.60830.0`, libjpeg, libtiff, libwebp, libopenjp2, lcms2,
   libpng16, libsharpyuv, libbrotli*, liblzma, libXau, libxcb - the list of section 4; **not dpkg-owned**, so the first
   version's `dpkg -S`-only generator would have failed on each) is attributed from the map's `from: "wheel"` entry
   (the wheel's own licence files are the texts: Pillow's wheel ships its vendored libraries' licences in
   `pillow-<v>.dist-info/`... **not verified**: the builder checks the wheel's `LICENSE`/`licenses/` content, and where a
   vendored library's text is not in the wheel the map's `source_url` plus the upstream licence text file committed
   under `desktop/build/licences/` is used); a file from the system (`libpython3.12`, `libcrypto`, `libssl`, `libstdc++`,
   `libgcc_s`, `libgomp`, `libffi`, `libexpat`, `libz`, `libbz2`, `libzstd`, `libglib-2.0`, `libpcre2-8`, ...) is attributed
   through `dpkg -S` + `/usr/share/doc/<pkg>/copyright` and must also have a map entry (the copyright file is the
   text, the map the classification). With the Pillow **wheel** (D8, ruled) the Debian-only libraries the first
   version listed - libjbig (GPL-2), libimagequant (GPL-3), libLerc, libdeflate, libfribidi, libgraphite2, libraqm -
   are **not** in the bundle (the wheel's `pillow.libs/` of section 4 has none of them; Pillow's wheel does not link
   libimagequant or libjbig), libreadline/libtinfo are out through the spec's excludes, and what remains copyleft is
   LGPL: `libglib-2.0` (LGPL-2.1, pulled by `gi`-free fontTools? - **the builder checks which collected library pulls
   it and excludes the puller if possible**), plus Electron's `libffmpeg`. The generator prints the final list; the
   release check (10.2) fails on any `gpl` entry and on any `lgpl` entry without a distribution record;
4. the AppImage runtime: electron-builder embeds its `appimage-12.0.1` runtime (from `electron-userland/electron-builder-binaries`,
   built from AppImageKit's type-2 runtime: MIT, with squashfuse (BSD-2) and **libfuse (LGPL-2.1) linked statically**,
   plus zlib/liblzma) at the head of the file; the download holds no licence file (section 4). The map carries one
   entry for it with the versions above, the upstream URLs, and - because a static LGPL link is the one case where
   "replace the library" needs the object files or the source - the record points at the runtime's source and build
   recipe in electron-builder-binaries. **Not verified** beyond reading the file names; the builder confirms the
   runtime's composition from that repository before the first public release (D8).

The file also restates that the faces in `repo/svf` are OFL 1.1 (`NOTICE.md`'s table copied) and that the maker's own
code is MIT. A test (10.3) runs the generator against the built sidecar and asserts no unattributed file and no
`gpl` entry.

### 8.10 Reproducibility, the Pillow reference, copyleft components, and the glibc floor

- Reproducible enough: pinned versions (`requirements-sidecar.txt`, `package.json` with a lockfile committed,
  `electronVersion`), `strip`/`upx` off, `SOURCE_DATE_EPOCH` exported by the build script from the commit date
  (PyInstaller 6 honours it for the archive timestamps; electron-builder's AppImage is deterministic for the same
  inputs per its docs - **not verified**). Byte-identical rebuilds are **not** a goal; "same inputs, same contents
  list and same sizes" is what the release check records.
- **The Pillow reference.** `mkfont` rasterises with Pillow's FreeType binding, so the Pillow build decides the bytes
  of every outline-derived face. D8 ruled the PyPI wheel; the reference for the frozen tests is therefore **the build
  venv's interpreter with the same wheel** (`requirements-sidecar.txt`), not the host's Debian Pillow: 10.2's
  byte-equal checks run `python3 -P tools/mkfont.py` from that venv. On this host the two agree (section 4: wheel
  10.2.0 and Debian 10.2.0 both carry FreeType 2.13.2 and raqm 0.10.1 and give identical 1 bpp and 2 bpp faces), and
  the release check records a second comparison against the host's Debian Pillow as "equal" or "differs: <reason>" -
  informational, because the repository's shipped faces were made with the host's Pillow and a future FreeType in a
  newer wheel may hint differently. A difference there is a fact for `docs/recipes.md`, not a failed release.
- **Copyleft components (D8, the complete rule).** (a) GPL (non-LGPL, no linking exception): **none may be in the
  package**; the generator fails. (b) LGPL-2.1/3 dynamically linked (`libffmpeg.so` of Electron, any `lib*.so` in
  `_internal/` classified `lgpl`): THIRD-PARTY.txt carries, per component, its version, the URL of the exact source
  (the Debian source package and version for a dpkg-attributed file; the upstream tag for a wheel-vendored one), the
  statement that the file is a separate shared object a user may replace with a compatible build (LGPL-2.1 s.6 /
  LGPL-3 s.4: the relink right is met by dynamic linking), and the licence text - and the release archives the
  corresponding source tarballs next to the AppImage (`desktop/build/out/sources/`), so the written offer is a
  download, not a promise. (c) LGPL statically linked (the AppImage runtime's libfuse, 8.9 item 4): the same record
  plus the runtime's own source and build recipe, since replacement means rebuilding the runtime; if the owner does
  not want that obligation the alternative is electron-builder's `type2-runtime` option or a plain tarball
  (`linux-unpacked` + a launcher script) instead of an AppImage - D8. (d) GCC runtime libraries (libstdc++, libgcc_s,
  libgomp): GPL-3 with the runtime library exception; attributed, no source obligation beyond the text. None of this
  binds until the first distribution (the package is private until the owner flips it, like the repository); it is
  a **release gate** of 10.2, not an S4 blocker, and `docs/maker-desktop.md` says so.
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
  `toolrun.FROZEN` patched true they are `[sys.executable, "run-tool", name]`; `split_prefix` on all three shapes and
  `ValueError` on anything else; `note_prefix` gives `python3 -P tools/<name>.py` in both modes; **every argv builder**
  starts with a `toolrun` prefix in both modes: `route.commands(...)` and `route.prepare_commands(...)` over
  `canonical_fonts()`, `routes.source_commands` for every op kind (`rsrc-sfnt`, `ttc-face`, `mac-cmap`, `instance`,
  `pcf-bdf`, `mac-fork`, `mac-fbit3`, `mac-htbl`, `mac-fork-named`), `routes.svf_commands`, `settings._dy_argv`,
  `settings.probe_argv` (fed a frozen-shaped mkfont argv, the probe argv keeps the prefix and the flags), and
  `toolrun.recog_argv` for both configurations; and no stray launcher: a source scan asserting `sys.executable`
  appears in `maker/*.py` only in `toolrun.py` and `zipout.py` (the `_note_token` compare), with `routes.PY` and
  `routes.SRCPREP` gone.
- `test_zipout.py`: `repo_head` reads `BUILD_ID` when present (a temp dir with the file), falls back to git only when
  not frozen, then "unknown"; for one mkfont step and one johab844 step, the note (upload job **and** local job),
  `BUILD.md`'s command lines and `log_step`'s text are **equal** between a source-shaped and a frozen-shaped argv,
  and the johab844 comment line is present in both.
- `test_jobs.py` / `test_preview.py`: `ENV` carries `JAMOSET_PYLIB` when the process has it and not otherwise; the
  registry file of 7.10 has one line while a `run_command`/`run_bounded` child runs and none after (the existing
  sleeper scripts); `Worker.stop` twice runs one sweep.
- `test_server.py` / `test_server_signals.py`: `serve --exit-with-parent=<pid>` with a helper parent: kill the
  helper, assert the server exits 0 within 5 s with its stop sweep run (an existing local job's files directory is
  gone) and nothing on the dead pipes (the helper's pipe ends are closed first; no `BrokenPipeError` in the server's
  exit code); `main(argv)`'s parser refuses an unknown option with exit 2; the registry reap at start kills a planted
  sleeper group listed in `tools.pids` with a matching start time and leaves one with a stale start time alone.
- `maker/test/test_sidecar_imports.py`: the reachable set computed from the sources (7.1) equals the design's list
  when the sources are the design's; it is the oracle for `selfcheck.modules` in 10.2.
- Existing suites updated for the new argv prefix (7.3). Gate: the whole maker suite through
  `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'` - 909 tests OK at `94011ff` plus the
  new ones; `tools/test_*.py`; `make -C c check`; `git diff --stat 94011ff -- c/src c/include` empty.

### 10.2 The frozen sidecar (runs here; needs the build)

`maker/test/test_frozen.py`, skipped unless `SVF_MAKER_SIDECAR=<path to svf-maker-sidecar>`:

- `selfcheck` JSON: `frozen` true, `flags.isolated`, `ignore_environment`, `safe_path`, `no_site` all true, every
  `sys.path` entry under the sidecar's directory (7.6), `tools` equals the table of 7.1, `modules` covers the set
  `test_sidecar_imports.py` computes with no import error, `budget` equals the server constants `desktop/lib/budget.mjs`
  cites;
- **every name of the `run-tool` table**: `run-tool <name> --help` exits 0 and prints `usage: <name>.py` (or `usage:
  fonttools varLib.instancer`), under `env -i PATH=<empty dir> HOME LANG PYTHONPATH=<dir with a planted json.py>` from
  a cwd that also holds a planted `jamoset.py` (nothing shadowed); `run-tool nosuch` exits 2; a tool made to raise
  (an unreadable input path) exits 1 with a `Traceback` on stderr and no `[PYI-` line;
- byte-equal to the **build venv's** `python3 -P` (8.10): `run-tool mkfont ttf/neodgm/neodgm.ttf OUT --size 16 --bpp 1
  --unicode ascii,ksx1001-hangul` (the spike's 115,460-byte check), `mkfont` 2 bpp, one `jamoset --layout 844` DOS raw
  fixture (`inputfx`), one `jamoset --from-ttf --layout adaptive` (the default jamo layout: the first version tested no
  jamo step frozen, and `jamoadapt` is reached only through function-level imports), one `srcprep ttc-face`, one real
  `instancer` op on `inputfx`'s variable-font fixture, one `macsfnt extract` + `unicode`, one `johab844`; plus the
  informational comparison with the host's Debian Pillow (8.10);
- `serve` under the scrubbed environment with the token and `127.0.0.1:0`: the port line within 2 s on a clean data
  root. A slow start-up cleanup cannot be staged here without a slow mount, so the test asserts the **constants**
  instead: `STARTUP_CLEANUP_S`, `Worker.stop`'s default and `STOP_SWEEP_TOTAL_S` are what `budget.mjs` says (a change
  on either side fails the test, and the 75 s / 45 s numbers stay derived); the one staged case is a planted stale
  files directory with a pending-sweeps record, which the start sweeps before the port line appears.
  `/` 200; `/static/wasm/svf.wasm` 200 `application/wasm`; `/api/caps` 403 then 200; a local job of `neodgm.ttf` to
  `done` with the face byte-equal to the source-mode job (`LocalRunBase` re-used with the server as a subprocess
  instead of in-process: the `localfx` helpers take a port - after the lifecycle fixes landed in `94011ff` that file is
  S2's to change); the note's and `BUILD.md`'s command lines equal to the source-mode ones; a jamo `adaptive` job
  to `done`; the recogniser both ways (7.7);
- a job with a step that blocks for more than 5 s (`jamovec master` on a large synthetic composite TTF from
  `inputfx`; `test_server_signals.py`'s `python -c` steps cannot run under the frozen executable, the `run-tool` table
  takes no test-only name, and a FIFO is refused as a source by `sources.py`), cancelled by SIGTERM to the server:
  exit 0, no process of the tool's group left (`pgrep -g`), the files directory gone, `tools.pids` empty;
- the same job, the sidecar **SIGKILLed** during the tool (7.10): the tool is gone within 3 s (PDEATHSIG), and with
  `SVF_MAKER_NO_PDEATHSIG=1` it survives, is listed in `tools.pids`, and the next `serve` start kills it before its
  first sweep; the job is `failed (interrupted)`;
- a wrong `SVF_MAKER_TOKEN` and a non-loopback `SVF_MAKER_BIND`: exit 2 with the fixed messages, nothing on stdout.

`maker/build-sidecar.sh` runs this test as its last step; the release check of `build-appimage.sh` runs it again
against `resources/sidecar/` of the extracted AppImage (`--appimage-extract`; FUSE is not available here) with
`SVF_MAKER_REPO=<extracted>/resources/repo`, plus `cmp` of the package's `svf.wasm` against a fresh `build-wasm.sh`.

### 10.3 The shell (runs here; node + xvfb)

- `desktop/test/unit.test.mjs` (`node --test`): `parsePortLine` on the exact line with its newline, a partial line
  without one (no match), two lines, a `::1` line; `isOurs(origin, url)` on the origin, a path, the origin with a
  different port (refused: a restart's old port), `http://localhost:<port>/`, `file://` (only the app's own
  `starting.html` passes), `devtools://`; `buildEnv` has exactly `ENV_KEYS` (6.2, with `SVF_RECOG_PYTHON`; no
  `process.env` leak: run with a decoy `SVF_MAKER_TOKEN` in the test's environment and assert the built one differs
  and is 32 hex; the four pass-throughs present only when set); `budget.mjs`'s numbers are the derivations 6.2/6.6
  state; the static scan of 6.9 over `desktop/*.js` and `desktop/lib/**`.
- `desktop/test/e2e.mjs` run as `xvfb-run -a electron --no-sandbox desktop/test/e2e.mjs` (skipped when `xvfb-run` or
  the electron binary is missing): the real main process code (`desktop/main.js` exports its functions when
  `SVF_MAKER_TEST=1`) with `dialog.showOpenDialog` replaced by a stub returning a temp folder with `neodgm.ttf`, against
  the **development command** of 6.2 (`python3 -P maker/server.py --exit-with-parent=<pid>` with the checkout as
  `SVF_MAKER_REPO`) and, when `SVF_MAKER_SIDECAR` is set, the packaged one. Asserts: the handshake; the page loads
  with title "SVF maker"; `window.svfMaker` has the four functions and `platform`; `fetch("/api/caps")` from the page is
  200 (the header was added) and `fetch("http://127.0.0.1:1/x")` rejects; `window.open` returns null and `location =
  "http://example.invalid/"` does not navigate; a click on a `download` link triggers no save (`will-download`
  prevented); the page's "choose folder" -> "detect" -> "run" flow through the DOM (the selectors `test_page_dom.py`
  uses) ends with a done job and a drawn canvas (`data-drawn="1"`); "open folder" calls the stubbed
  `shell.showItemInFolder` with **that job's** `output_dir` (the test opens an older job from the list first, so the
  last dialog's folder and the job's differ); a simulated sidecar crash (`kill -9` of the sidecar) shows the message
  box stub's "Restart", and the restarted sidecar's page loads and its `/api/caps` is 200 with the **new** token on
  the **new** port; closing the window stops the sidecar with exit 0 within `STOP_WAIT_S`; `SIGTERM` to the Electron
  main process does the same (the handler of 6.6); killing the main process with SIGKILL makes the sidecar exit by
  itself within 5 s (`--exit-with-parent`) with a local job's files directory present and swept; on Linux the test
  logs the renderer's `Seccomp`/`NoNewPrivs` from `/proc` (always "off" under `--no-sandbox`: the run records it, it
  cannot assert a sandbox this host cannot provide; 8.7).
- The existing browser harness stays the page's gate: `test_page_dom.py` (pagedrive with `--header` and `--preload`)
  and `smoke_dom.py` run unchanged; nothing in the page changes in these cards.

### 10.4 Not verified (and where it is said in the code or docs)

Windows and macOS entirely (8.11); FUSE-mounted AppImage start (no FUSE here: only `--appimage-extract` runs);
a sandboxed renderer on a host with user namespaces (8.7: here there are none, and the run is unsandboxed); glibc
older than 2.39 (8.10); `electronLanguages` pruning (8.6); `fontTools.varLib` beyond `instancer --help` in the frozen
build until 10.2's real `instance` op runs (8.3); `JAMOSET_PYLIB` with 3.12 wheels in the frozen process and any real
recogniser (7.7: the test uses a stub `recog.py`); `PR_SET_PDEATHSIG` in `run-tool` and the registry reap (7.10: the
tests are specified, not run); the `atexit` no-op and the 45 s derivation (6.6) on a busy server; native dialogs with
a display (the e2e stubs them; a human run under a real session is the manual check the release notes list); the
composition of the AppImage runtime and the Pillow wheel's licence files (8.9); `SOURCE_DATE_EPOCH` determinism
(8.10); a FreeType other than 2.13.2 in a future Pillow wheel (8.10); a real disk-full or a removed output folder
during the quit sweep (the server's own mocks cover it); the Hunspell download being the only Chromium-initiated
request (6.3; the `webRequest` cancel covers unknowns).

## 11. Task decomposition for the plan writer (E)

| Slice | Content | Verifiable by | Touches |
|---|---|---|---|
| **S1 toolrun** (first: no Electron, no build) | `maker/toolrun.py` (`tool`, `maker_script`, `module`, `split_prefix`, `note_prefix`, `recog_argv`); the 29 launch sites and the three positional consumers of 7.3; `note_commands` both branches, `_command_lines`, `_johab844_comment`, `probe_argv` on `split_prefix`; `repo_head` + `BUILD_ID` + no git when frozen; `ENV` + `JAMOSET_PYLIB` in `jobs.py` and `preview.py`; the recogniser path of 7.7 in `caps.py` and `jobs._identity`; tests updated; `test_toolrun.py`, `test_sidecar_imports.py` | the maker suite (909 at `94011ff` + new) green; `tools/test_*` green | `routes.py`, `settings.py`, `jobs.py` (`ENV`, `_identity`), `preview.py` (`ENV`), `caps.py`, `zipout.py`, `maker/test/test_routes.py`, `test_zipout.py`, `test_plan_inputs.py`, `test_jobs.py`, `test_preview.py`, new `toolrun.py`, `test_toolrun.py`, `test_sidecar_imports.py` |
| **S2 sidecar** | `maker/sidecar.py` (`serve`, `run-tool` with the 7.1 table and lazy imports, `selfcheck`, `--version`, PDEATHSIG in `run-tool`); in `server.py`: `main(argv)` with `--exit-with-parent=PID` (dup2 + SIGTERM, PDEATHSIG), the registry reap before `startup_cleanup`, `Worker.stop` second-call no-op (`jobs.py`), the registry writes in `run_command`/`run_bounded` (`jobs.py`, `preview.py`); `maker/sidecar.spec`, `maker/build-sidecar.sh` (+ `requirements-sidecar.txt`, the venv, WASM first, `BUILD_ID`), `maker/test/test_frozen.py` (with `localfx` taking a port) | build here; 10.2 green under `env -i`; the frozen local jobs byte-equal to the build venv's source mode | `server.py` (`main`, `make_server`), `jobs.py` (`run_command`, `Worker.stop`), `preview.py` (`run_bounded`), `maker/test/localfx.py`, `test_server_signals.py`, new files, `.gitignore` (`desktop/build/out/`) |
| **S3 shell** | `desktop/` (package.json, main.js, preload.js, `starting.html`, lib/{env,portline,guard,budget,shutdown,sandbox,paths}.mjs, test/unit, test/e2e), the icon | 10.3 under xvfb against the development command; then against S2's sidecar | `desktop/` only (the page is already bridge-aware: no change to `maker/static`) |
| **S4 AppImage** | electron-builder config, `extraResources`, `third-party.mjs` + `third-party-map.json` + `desktop/build/licences/`, `build-appimage.sh` with the release check (extract, frozen test, wasm cmp, licence completeness and copyleft rule, size budget, sources archive) | a 150 MB-class AppImage built here and checked extracted | `desktop/build/`, `desktop/package.json` |
| **S5 docs** | `docs/maker-desktop.md` (how to build, versions last used, the manual checks, the sandbox state per system, the Windows/macOS notes of 8.11 verbatim), `maker/README.md` (a "Desktop app" section; the `run-tool` form; `SVF_RECOG_PYTHON`; `JAMOSET_PYLIB` forwarded), `NOTICE.md` (one line: the desktop package bundles third-party components listed in its THIRD-PARTY.txt), `docs/maker-audit.md` section 9 (the two cards' closing evidence), `docs/STATUS.md` | the `test_readme_and_notice_wording` test and a read-through | docs only |

Order and serialization: S1 -> S2 (S2 needs `toolrun` for the frozen job to run; both edit `maker/jobs.py` and
`maker/preview.py`, in different functions - S1 `ENV` and `_identity`, S2 `run_command`/`run_bounded`/`Worker.stop` -
so they are **serial**, S2 rebased on S1); S3 can start after S1 against the development command and only its last
step needs S2; S4 needs S2 and S3; S5 last (it cites the measured numbers). The lifecycle fixes of card t_cbd14d61 are
**merged** (`94011ff`), so there is no in-flight branch to wait for; `maker/test/localfx.py` (which those fixes also
touched) is S2's to change now. Shared files: `maker/server.py` is S2's only; `caps.py`, `routes.py`, `settings.py`,
`zipout.py` S1's only; S3 and S4 touch `desktop/` only. Reviews: S1's review diffs every argv prefix before/after (a
mechanical change with 29 sites plus the three positional consumers); S2's review runs the frozen test itself; S3's
review runs the xvfb test; S4's review opens THIRD-PARTY.txt against `ls _internal/*.so` and the map.

Risks, with the mitigation each slice carries:

- A missed call site in S1 (a tool launched with the old prefix fails only in frozen mode): the source scan of 10.1,
  the builder-by-builder assertions, and the frozen jobs of 10.2 (mkfont, srcprep, svfdy, a jamo `adaptive` route, a
  Mac route, the instancer and johab844, so every launcher form runs frozen at least once).
- A positional consumer of the launcher prefix left behind (three were found: `probe_argv`, `note_commands`'s johab844
  test, `_johab844_comment`): `split_prefix` is the one way to take an argv apart, and the frozen johab844 job's note
  is asserted to carry its comment line.
- PyInstaller misses a lazy import (a fontTools table, a PIL plugin, a tool reached only inside a function): the
  `collect_submodules` lists are computed before `Analysis` (the first spec had them after, where they did nothing);
  the ast-computed graph is the oracle of `selfcheck.modules`; the frozen tests run the real tools; PIL's hook collects
  its plugins (verified in that the frozen server's `GET preview/<font>/source.png` returned a PNG: `preview.source_png`
  renders with Pillow's FreeType binding inside the bundle, section 4).
- The handshake or the stop wait shorter than the server's own work (the first version had 15 s and 35 s against a
  30 s start-up cleanup and a 47 s stop path): both numbers are derived in `budget.mjs` from the server's constants and
  a test pins the constants on both sides.
- A tool outliving a SIGKILLed sidecar and a sweep racing it: 7.10's two layers and its test.
- No renderer sandbox inside the AppImage on userns-restricted systems: stated in 8.7, shown in the About box, D7/D13.
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
- The size of the synthetic composite TTF that makes `jamovec master` block long enough for the SIGTERM and SIGKILL
  tests of 10.2 (the step is decided; its fixture is not).
- The exact format of `tools.pids` lines and its lock (7.10 fixes the fields, not the syntax).
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
- **D7 (re-opened; the first ruling rested on a wrong fact).** The AppImage runs with **no renderer sandbox** on
  userns-restricted systems (Ubuntu 24.04 and this host): electron-builder's `AppRun` adds `--no-sandbox` when
  `unshare -Ur` fails and its `.desktop` entry adds it always; the binary without the flag aborts (8.7, section 4).
  Recommendation: ship electron-builder's `AppRun` unchanged, log and show the sandbox state (About box), say it in
  the docs; the renderer handles only the app's own local content. Alternative: refuse to start without a sandbox
  (then the AppImage does not run on Ubuntu 24.04 at all), or a `.deb` with an AppArmor profile as the sandboxed
  distribution (D13).
- **D8 (revised with the measured facts).** With the Pillow PyPI wheel (ruled) the bundle has **no GPL library**
  (the wheel's `pillow.libs/` carries libfreetype, libharfbuzz, libjpeg, libtiff, libwebp, libopenjp2, lcms2, libpng,
  libsharpyuv, libbrotli*, liblzma, libXau, libxcb - no libjbig, no libimagequant; section 4) and `readline`/`curses`
  are excluded; the wheel's faces are byte-identical to the Debian build's here. What remains copyleft is LGPL,
  dynamically linked (Electron's `libffmpeg`, possibly `libglib-2.0` if a collected library pulls it), plus the
  AppImage runtime's static libfuse. Recommendation: the complete rule of 8.10 - GPL forbidden by the generator; LGPL
  dynamic: a per-component distribution record (version, exact source URL, replaceability statement, licence text)
  and the source tarballs archived with each release; LGPL static (the runtime): the same plus the runtime's build
  recipe, or switch to electron-builder's `type2-runtime` / a tarball distribution if the owner declines that
  obligation. All of it a release gate, binding at the first public distribution. Alternative: accept notices only
  (the first version's wording - rejected by two reviews as incomplete).
- **D9. Build the sidecar on this host (glibc 2.39 floor)** for the first release; a container build on Ubuntu 22.04
  later if a user reports an older system. Alternative: the container from the start.
- **D10. Remember window size/zoom in `shell-state.json`** (6.4, 6.8). Alternative: nothing persisted but the
  server's data.
- **D11. `--exit-with-parent` by `getppid` polling every 2 s** (7.9), POSIX. Alternative: `PR_SET_PDEATHSIG` on
  Linux as a second layer (immediate); or nothing (a crashed shell leaves a sidecar until the user kills it).
- **D12. The data root `<userData>/maker`** (`~/.config/svf-maker/maker` on Linux) rather than today's default
  `~/.local/share/svf-maker` - Electron's convention, one place to remove. Alternative: keep the server's default
  (then two users of the source-mode server and the app would share one store).
- **D13 (new). A `.deb` target as the sandboxed Linux distribution**, later card: electron-builder's deb target writes
  an AppArmor profile granting `userns` to `/opt/svf-maker/svf-maker`, which restores Chromium's namespace sandbox on
  Ubuntu 24.04 (**not verified**). Recommendation: not in these cards; note it in `docs/maker-desktop.md`.
- **D14 (new). The tool registry (7.10) in both modes, PDEATHSIG only in the frozen tool.** Recommendation: as
  designed (the registry is a few lines in the two runners and one reap at start; it is what makes an immediate
  restart safe). Alternative: PDEATHSIG only (Linux-only, and nothing for source mode or macOS).
- **D15 (new). `openOutputFolder` reveals the open job's folder** through a main-process `GET /api/jobs/<id>`, only if
  the shell handed that folder out (6.5). Alternative: the last dialog's folder (the first version; it can reveal an
  unrelated folder after a restart or when an older job is shown).

## 15. Rulings on section 14 (2026-11-05, controller)

D1 sidecar death -> message box with restart (new token/port). D2 `window-all-closed` quits on macOS too. D3 persist the last
output folder path in `shell-state.json` (path only, no file content). D4 `run-tool` only, no `-P path.py` shim. D5 optional
recogniser through an external interpreter (`SVF_RECOG_PYTHON` running the shipped `recog_score.py`); `caps.recog` stays false
until set. D6 pin the verified versions. D7 no `--no-sandbox` by default; document the workaround. D8 exclude stdlib
readline/curses, prefer the Pillow PyPI wheel, ship the LGPL notices, record the check in THIRD-PARTY. D9 build on this host
first (glibc 2.39 floor), container build later. D10 remember window size/zoom in `shell-state.json`. D11 `--exit-with-parent`
by getppid polling on POSIX. D12 data root `<userData>/maker`. Rulings of the controller, reversible by editing this section
and the plan.

Rulings that the review round re-opened (section 16): **D7** rested on a wrong fact (the AppImage ran "without
`--no-sandbox`" only because electron-builder's `AppRun` added the flag): re-decided in section 14 as the new D7. **D8**
is kept, with its wording replaced by the complete rule of 8.10. **D5** stands; its implementation is now spelled out in
7.7 (the first version left four places unresolved). D13-D15 are new.

## 16. Review dispositions (2026-11-05)

Three independent reviews of the first version (`fcd81a3`): Opus (Important I1-I10, Minor M1-M15), AGY (Critical 1-3,
Important 1-7, Minor 1-3), SOL (P1 x2, P2 x5). Every finding was checked against the code at `94011ff` before the
design was changed; "fixed" names the section that changed, "n/a" gives the reason. Duplicates are merged.

| Finding | Checked | Disposition |
|---|---|---|
| AGY C1: `sidecar.py` maps `jamoaa.main`/`jamofit.main`, which do not exist | `jamoaa`, `jamofit`, `jamoadapt` have no `main` (section 4); the first version's table did **not** list them (it listed `facecheck` and `recog_score`, which the maker does not launch as `run-tool`) - the review quoted a table this document never had | fixed anyway at the root: 7.1 now derives the table from each tool's real guard (`main()` vs `sys.exit(main())`), drops `facecheck`/`recog_score`, and 10.2 runs `run-tool <name> --help` for **every** name |
| AGY C2: `jamoadapt` missing from the imports/hidden imports | reachable only through function-level imports (`jamoset:2992`, `jamoaa`, `jamovec:203`); PyInstaller follows those and the spike's PYZ holds it (section 4) | fixed by construction: the graph is computed (`desktop/spike/import_graph.py` -> `test_sidecar_imports.py`), `selfcheck.modules` imports every reachable module, 10.2 runs a frozen `adaptive` jamo step (7.1, 10.2) |
| AGY C3 + SOL P2 (`SVF_RECOG_PYTHON`) + Opus M5 | `env.mjs` list lacked it; `jobs.py:1514` builds the script path from `__file__` (unrunnable by another interpreter when frozen); `caps.compute` runs once at start (`server.py:479`, `/api/caps` serves the dict at `:1772` - the per-`GET` claim is **not** so), but `caps.recog_dir` is called per jamo step (`jobs.py:1502`); the probe must cover PIL/fontTools too | fixed: 6.2 `ENV_KEYS`, 7.7 (probe once in `compute`, four packages, cached `recog_python`, `toolrun.recog_argv` with the shipped `repo/maker/recog_score.py`), 7.5 (sources shipped), 7.3 rows for `jobs._identity`/`caps.py`, 10.2 both configurations |
| Opus I8 + AGY Imp.1 + Opus M9 (notes/BUILD.md/johab844/positional) | confirmed at `zipout.py:168,:199,:434-457` and `settings.py:1408-1421` (section 4) | fixed: 7.2 `split_prefix`/`note_prefix` applied in `_command_lines` and both `note_commands` branches before the johab844 test; 7.3 rows; 10.1 equality tests for note, `BUILD.md`, log, upload and local |
| AGY Imp.2 (`JAMOSET_PYLIB` stripped) | confirmed: only `routes.py:167` passes `--pylib`; `jamoset` defaults to `--binarize mono` (`:2870`); the stripped `ENV` is a pre-existing source-mode gap | fixed: 7.4 forwards the key into `jobs.ENV`/`preview.ENV` when set; 10.1 test |
| AGY Imp.3 (`mac-fbit-golden.json` omitted) | the file does **not** exist in this repository (`tools/testdata/` holds `jset1/`, `v2/` only); `mac_golden()` returns None either way | n/a today; 7.5 says where it goes if ever added and adds a test that lists `__file__`-relative paths of reachable modules |
| AGY Imp.4 + Opus M13 (restart vs per-port closures, `senderFrame` null) | the first version said handlers are "replaced"; closures were implied | fixed: 6.3 one mutable `sidecar` object read at call time, host-wide header filter registered once; 6.5 null check; 10.3 restart test asserts the new port and token work |
| AGY Imp.5 (`probe_argv` 3-element slice) | confirmed `settings.py:1408,:1409,:1421` | fixed: 7.2/7.3 via `split_prefix`; 10.1 feeds a frozen-shaped argv |
| AGY Imp.6 + Opus I6 + SOL P2 x2 (licence generator: wheel `.so`, GPL guard, source obligations, AppImage runtime) | the wheel's `pillow.libs/` is not dpkg-owned (section 4); the download holds no licence file for the runtime | fixed: 8.9 four sources, `third-party-map.json` (fail closed, `gpl` forbidden), wheel attribution path, runtime entry; 8.10 the complete copyleft rule (records, source archive, static-link case, release gate); D8 revised |
| AGY Imp.7 + Opus I10 (slices: `caps.py` missing; conflict with lifecycle-fixes) | the lifecycle fixes are merged (`94011ff`: `jobs.py`, `server.py`, `localfx.py`, `test_local.py`) | fixed: 11 lists `caps.py`, `jobs.py` functions per slice, `localfx.py` to S2, S1/S2 serial; every line reference refreshed (section 4) |
| Opus I1 + SOL P2 (hidden imports after `Analysis`) | the review's rebuild from the first spec showed 9/29 `fontTools.pens` modules; the spike had used command-line flags | fixed: 8.3 computes the lists before `Analysis` and passes `hiddenimports=`; 10.2 runs a real `instance` op and TTC/Mac reads frozen |
| Opus I2 + SOL P1 (15 s handshake vs 30 s start-up cleanup + 20 s probe) | confirmed `server.py:56,:504,:530,:1986` | fixed: 6.2 `HANDSHAKE_S` = 75 derived in `budget.mjs`, a "starting" page after 2 s, give-up runs the stop sequence; 8.6; 10.2 pins the constants |
| Opus I3 (35 s quit wait vs 47 s stop path; `atexit` double stop) | confirmed `jobs.py:1060` sweeps on every call, `server.py:1987,:2003` | fixed: 6.6 `STOP_WAIT_S` = 45, `Worker.stop` second call a no-op (S2); 8.6; 10.1 test |
| Opus I4 (`openOutputFolder` reveals the wrong folder) | confirmed `maker.js:2054,2238-2240` set `state.output` from the open job | fixed: 6.5 reveals the open job's `output_dir` (main-process `GET /api/jobs/<id>`), only if the shell handed it out; D15; 10.3 test |
| Opus I5 (sandbox claim contradicted; untested) | **confirmed and worse**: `AppRun` adds `--no-sandbox` when `unshare -Ur` fails; `.desktop` always; the bare binary aborts; `/proc` shows Seccomp 0 (section 4); `getAppMetrics().sandboxed` is Windows-only | fixed: section 4 facts corrected, 8.7 rewritten, D7 re-opened, D13 (`.deb`), 10.3 records the state, About box shows it |
| Opus I7 (Pillow wheel invalidates the byte identity) | measured: wheel 10.2.0 and Debian 10.2.0 give identical 1 bpp and 2 bpp faces here (section 4) | fixed: 8.10 names the build venv's wheel as the reference and keeps a Debian comparison as informational; 10.2 compares against the venv |
| Opus I9 (dead pipes after a shell crash) | `print(..., file=sys.stderr)` on the stop path; Python ignores SIGPIPE | fixed: 7.9 `dup2` `/dev/null` onto fds 1-2 before the self-SIGTERM; 10.1 test with closed pipe ends |
| SOL P1 + Opus M1 + AGY Min.2 (tools outlive the sidecar; group kill does not reach them) | confirmed `start_new_session=True` in both runners (section 4) | fixed: 6.2 corrected; 7.10 registry (`<data>/tools.pids`, reap before `startup_cleanup`) + PDEATHSIG in `run-tool`; D14; 10.2 SIGKILL-during-a-tool test both ways |
| SOL P2 (dev mode paths, no parent-death handling) | the first version's dev command lacked the flag and used the packaged env | fixed: 6.2 development command with `SVF_MAKER_REPO=<checkout>`, `maker-dev` data root, `--exit-with-parent=<pid>`; 10.3 runs it |
| SOL (measurements uncorroborated) | - | fixed: `desktop/spike/` holds the probe scripts and `README.md` the exact commands and outputs (section 4 points at it) |
| Opus M2 (regex `$` on a partial chunk; `::1` unbracketed) | `server_address[0]` is `"::1"` | fixed: 6.2 regex requires the newline and takes `::1` bare; 10.3 unit test |
| Opus M3 (frozen traceback form, `[PYI-...]` line) | reproduced by the reviewer's probe | fixed: 7.1 `run-tool` catches and prints the traceback, exit 1; section 2 goal reworded; `module_collection_mode` named in 8.3 |
| Opus M4 (return value ignored by bare `main()` guards) | confirmed (section 4) | fixed: 7.1 table gives each entry its guard's form and `run-tool` mirrors it |
| Opus M6 (`readline`/`curses` not in excludes) | - | fixed: 8.3 |
| Opus M7 (static import table would import everything per launch) | the spike's start-up was measured with hidden imports | fixed: 7.1 per-entry import functions |
| Opus M8 (`sys.path` gains `<sidecar>/tools`) | `server.py:14-16`, `srcprep.py:19` | fixed: 7.6 selfcheck rule "under the sidecar's directory" |
| Opus M10 (window gone on the close path; Electron signals) | - | fixed: 6.6 (no "window stays"; explicit `process.on` handlers); 10.3 SIGTERM test |
| Opus M11 + AGY Min.1 (ppid race) | - | fixed: 7.9 `--exit-with-parent=PID` passed by the shell, thread before `make_server`, PDEATHSIG on Linux |
| Opus M12 (`git` under the bundle's `LD_LIBRARY_PATH`) | - | fixed: 7.8 no git fallback when frozen |
| Opus M14 (`download zip` link -> save dialog) | `maker.js:573` | fixed: 6.3 `will-download` prevented; 10.3 |
| Opus M15 (a FIFO cannot be a source) | `sources.py` requires a regular file or folder | fixed: 10.2 uses `jamovec master` on a large synthetic TTF |
| AGY Min.3 (`test_toolrun` covers only `route.commands`) | - | fixed: 10.1 lists every argv builder |
| AGY: "`caps.recog_dir()` is called on every `GET /api/caps`" | **not so**: `compute` once at start (`:479`), the dict is served (`:1772`) | n/a as stated; the per-step call (`jobs.py:1502`) is real and is removed (7.7) |
| AGY: references to `stage-repo.mjs`, `desktop/build/sidecar.spec`, `X-SVF-Maker-Token`, `pickSources`, `--repo`, a `TOOLS` dict with `jamofill` | none of these names is in this document (the header is `X-Maker-Token`, the bridge is the four functions of 6.5, the spec is `maker/sidecar.spec`) | n/a: the review described another text; the substance behind each (the dispatch table, the data files, the token header, the restart) is handled above |
| Opus "what checks out" (29 sites, module paths, handshake, token scope, bridge members, byte identity 43 vs 47 MB, SIGTERM `SIG_DFL`) | agrees with section 4 | recorded; the 43 MB figure is the reviewer's own build (the design keeps 47 MB as the upper measured value) |

## 17. Rulings on the remaining decisions (2026-11-05, controller)

D7 ship electron-builder's AppRun unchanged (it adds `--no-sandbox` when user namespaces are unavailable), the shell shows the
renderer sandbox state in its About box and writes it to its log, and the page loads only local content (loopback origin, strict
CSP, navigation and request guards): the residual risk is the owner's own local content. A `.deb` with an AppArmor profile is the
sandboxed path (D13: later, not in this card). D8 accept the copyleft rule as written: GPL forbidden by the generator, LGPL
per-component distribution record and source archive are a RELEASE GATE (the bundle is not public yet), the AppImage runtime's
static libfuse obligation is accepted until a release is planned. D14 yes (registry in both modes, PDEATHSIG frozen-only).
D15 yes (`openOutputFolder` reveals the open job's output folder, only if the shell handed it out). Rulings of the controller,
reversible by editing this section and the plan.
