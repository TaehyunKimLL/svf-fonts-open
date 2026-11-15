# SVF maker desktop app

An Electron shell (`desktop/`) around the maker server, and a build that packages it with a frozen Python sidecar as a
Linux AppImage. Cards t_f04f1355 (shell) and t_e64a56a7 (packaging). Design: `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`;
plan: `docs/superpowers/plans/2026-11-05-maker-desktop.md`. The package is private until the owner flips the repository.

## What it is

- `desktop/main.js` spawns `svf-maker-sidecar serve --exit-with-parent=<pid>` (a PyInstaller one-dir bundle of the server
  and every tool) with a new per-launch token and `127.0.0.1:0`, reads the port line, loads `http://127.0.0.1:<port>/`,
  adds `X-Maker-Token` to `/api/` requests itself, gives the page `window.svfMaker` and stops the sidecar on quit.
  Every request that is not the sidecar's own origin is cancelled, navigation and new windows are refused, no download is
  saved, no permission is granted. No network connection is made. Nothing is updated automatically.
- The sidecar runs each tool as `svf-maker-sidecar run-tool <name> ...` in its own session, registers it in
  `<data root>/tools.pids`, and a start reaps what a dead run left (`maker/toolreg.py`). One server per data root
  (`instance.lock`). The data root is `~/.config/svf-maker/maker` (`<userData>/maker`); development runs use
  `<userData>/maker-dev`.
- Optional pieces stay outside: the identity check runs under `SVF_RECOG_PYTHON` with `SVF_RECOG_DIR`; the mask-fit
  libraries come from `JAMOSET_PYLIB`. The package carries `maker/*.py` and `tools/*.py` as source for that interpreter.

## Build (Linux)

Prerequisites on the build host: emsdk (`~/opt/emsdk`, emcc 6.0.13 last used), Python 3.12.3 with pip (`python3 -m venv`
does not work on Ubuntu without `python3-venv`; the build uses `pip install --target` and `python3 -S`), node 22 and
npm 12, `xvfb-run` for the release check's smoke run, network access once for the pinned wheels and Electron.

    cd desktop && npm ci && node node_modules/electron/install.js && cd ..   # npm 12 blocks Electron's postinstall
    ~/.local/bin/heavy bash desktop/build/build-appimage.sh [--release]

Versions last used (all pinned: `desktop/build/requirements.lock` with hashes, `desktop/package-lock.json`):
PyInstaller 6.22.3, Pillow 10.2.0, fontTools 4.66.1, Electron 45.2.3, electron-builder 26.18.0.

Scratch: the scripts take `SVF_DESKTOP_TMP` (default `$HOME/work/tmp/svf-desktop-build`: pip download, PyInstaller work
directory, the pruned toolset, extractions); tests take `TMP_DIR` (keep it short: under about 40 characters past `$HOME`,
Chrome's socket path is limited to 107 bytes). Never `/tmp`. Every run that starts Chrome or Electron takes
`flock $HOME/work/tmp/svf-browser.lock` and runs under `~/.local/bin/heavy`.

`build-appimage.sh` runs `maker/build-sidecar.sh` (the frozen test included, no skip allowed), writes `THIRD-PARTY.txt`
(fails on an unattributed library or a GPL one), builds the AppImage and runs `desktop/build/release-check.sh`, which
prints one `CHECK <name> ok|FAIL` line each: size, extract, size-sidecar, layout, apprun, desktop-entry, frozen
(`test_frozen.py` against the extracted sidecar, 0 skipped), wasm (`cmp` with a fresh build), licences (the generator over
the extraction), notices and sources (the bundled `THIRD-PARTY.txt` equals the regenerated one; `resources/repo/{maker,tools}/*.py` and `resources/repo/web/mkindex.py` equal the checkout by sha256: `desktop/build/verify-extraction.sh`, run through `verify-report.sh`/`run-verify.sh`, which fail closed on a non-zero exit, a missing or duplicate result line or any other output, stderr included), smoke (the extracted `AppRun` under xvfb), sources (`--release` only) and contents (a file list record in
`desktop/build/out/release-<build id>-<AppImage sha256 prefix>.txt`, one per AppImage).

`build-appimage.sh` and `release-check.sh` take the browser lock themselves for the smoke run (they wait for it as long as it
takes, then allow 90 s for the Electron run): start them under `~/.local/bin/heavy`, **never under `flock`**, which would
deadlock them.

### Measured (this host, Ubuntu 24.04 x86_64, glibc 2.39)

| Item | Value |
|---|---|
| Sidecar one-dir | 47 MB; build 8-9 s (about 30 s with the frozen test); startup port line well under 2 s |
| AppImage | 149.7 MB (142 MiB); `linux-unpacked` 335 MB; electron-builder about 50 s |
| Frozen test | 26 tests, 0 skipped: byte-equal to the pinned wheels under `env -i`, frozen jobs and notes equal source mode |
| Electron task counts (`--no-sandbox --disable-gpu` under xvfb) | one instance 87, second-instance case 114 (planning measurements, with the GPU 143 and 170); the lifecycle test's peak was 79-80 |
| Debian Pillow comparison | equal |

## The sandbox

An AppImage cannot carry Chromium's SUID sandbox helper (FUSE mounts are `nosuid`), so the only sandbox it can have is
the user-namespace one, and Ubuntu 24.04 denies unprivileged user namespaces. electron-builder's `AppRun` probes
`unshare -Ur true` and adds `--no-sandbox` when that fails; its `.desktop` entry here reads
`Exec=AppRun --no-sandbox %U`. So on this host and on every Ubuntu 24.04-class system the renderer runs **without** a
sandbox (the shell logs and About shows "renderer sandbox: off (--no-sandbox; user namespaces unavailable)"); on a system
with user namespaces it would run sandboxed (not verified). The renderer only ever loads the app's own page from a
loopback server with a strict CSP, plus files the user picked; no remote content is loaded (D7, spec section 17). A `.deb`
with an AppArmor profile would restore the sandbox on Ubuntu 24.04: a later card (D13), not done here.

## The AppImage toolset and the tray icon

electron-builder copies six old libraries into the AppImage's `usr/lib` (appindicator, gconf, indicator, notify, Xss,
Xtst). `libindicator` is **GPL-3.0**, and the packaging rule forbids GPL in the package; both the legacy `appimage-12.0.1`
toolset and the newer 1.0.2/1.0.3 ones carry it. The build therefore points electron-builder at a copy of the legacy
toolset from which `libindicator` and `libappindicator` are removed (`desktop/build/prune-appimage-toolset.py`, driven by
`desktop/build/appimage-toolset.json`: the downloaded archive's sha256 and the sha256 of each removed file are checked and
printed in THIRD-PARTY.txt; no binary is stored in the repository). **Tray-icon support (libappindicator) is not
shipped**: `libappindicator` cannot load without `libindicator`, and the app has no tray icon, so nothing is lost. The
release check proves the pruned AppImage still starts (extracted `AppRun` smoke) and that no GPL library remains in the tree.

## Licences and the release gate

`THIRD-PARTY.txt` is generated from the bundle. Rules: every shared object in the sidecar, in Electron's directory and in
`usr/lib` must match an entry of `desktop/build/third-party-map.json` (fail closed); the sha256 of every Electron and `usr/lib` library is printed beside it; a sidecar library must match its
build-time provenance (`sidecar-provenance.py`, from PyInstaller's table of contents); class `gpl` is forbidden; class
`lgpl` needs a distribution record; `svf/` may hold only OFL-listed faces. The copyleft components today: ffmpeg
(`libffmpeg.so` of Electron, LGPL-2.1), the AppImage runtime (libfuse linked statically, LGPL-2.1) and the PyInstaller
bootloader (GPL with the bootloader exception).

**D8, a release gate (not a gate of a private build):** before the first public release the corresponding source archives
are placed in `desktop/build/out/sources/` with a `MANIFEST.json`:

    [{"component": "ffmpeg (Chromium build, in Electron)", "version": "Electron 45.2.3", "kind": "source",
      "archive": "ffmpeg-....tar.xz", "sha256": "<hex>"},
     {"component": "appimage-runtime", "version": "12.0.1", "kind": "source", "archive": "runtime-src.tar.gz", "sha256": "<hex>"},
     {"component": "appimage-runtime", "version": "12.0.1", "kind": "recipe", "archive": "runtime-recipe.txt", "sha256": "<hex>"}]

(one `source` entry per LGPL component whose component and version equal the map's, plus a `recipe` for the AppImage
runtime). `build-appimage.sh --release` then fails unless the generator prints "corresponding sources archived: YES".

## glibc floor

The sidecar bundles the system libraries PyInstaller finds except glibc, so the package needs glibc at least the build
host's (2.39, Ubuntu 24.04). A container build on Ubuntu 22.04 (glibc 2.35) would widen it (D9; not done).

## Manual checks (a human with a real desktop)

Native file and folder dialogs (the tests stub them), "open folder" in the desktop's file manager, starting the AppImage
through FUSE (`./svf-maker-0.1.0.AppImage`; no FUSE on the build host, so only `--appimage-extract` and the extracted
`AppRun` were run), the GPU path (the tests use `--disable-gpu`), a sandboxed renderer on a host with user namespaces.

## Windows and macOS (UNVERIFIED)

Nothing below was run. It is the plan a builder on those hosts follows, and what blocks it. Not built or verified.

- **macOS.** PyInstaller one-dir builds the same spec on macOS (arm64 and x86_64 are separate builds; a universal2
  build needs universal wheels of Pillow and fontTools; `desktop/build/requirements.lock` pins Linux cp312 wheels only).
  The server already runs on macOS (POSIX), but the registry's macOS start time (`ps -o lstart=`) is untested. electron-builder
  target `dmg` + `zip`; `extraResources` the same; the AppImage's `--no-sandbox` question does not exist. Signing: a
  Developer ID Application certificate, `mac.hardenedRuntime: true`, an entitlements file allowing nothing beyond
  `com.apple.security.cs.allow-unsigned-executable-memory` (Chromium) - and every binary under `resources/sidecar/` must be
  signed too (`codesign --deep` does not reach `_internal/*.so` reliably; sign them individually with `--options runtime`),
  then `notarytool submit` and `stapler`. Without signing, Gatekeeper blocks the app on first run (right-click Open works).
- **Windows.** The **server is not Windows-ready** (`os.killpg`, `start_new_session`, `signal.SIGTERM` to a group,
  `os.umask(0o077)` semantics, `os.link` for the no-replace write, `fcntl` locks in the registry and the data-root lock): a
  port needs Job Objects (or `CREATE_NEW_PROCESS_GROUP` + `GenerateConsoleCtrlEvent`) for the group kill, `CreateProcess`
  flags in `run_command`/`run_bounded`, and a review of every `realpath`/inode rule of the local-mode design on NTFS. That is
  a card of its own; until it is done the Windows build is not attempted. Then: the same PyInstaller spec (keep
  `console=True` and the shell's `windowsHide`), electron-builder target `nsis` or `portable`, the Electron spawn with a Job
  Object, signing with a code-signing certificate.

## Not verified here

Windows and macOS entirely; a FUSE-mounted AppImage start; a sandboxed renderer; glibc older than 2.39; `JAMOSET_PYLIB` with
3.12 wheels in the frozen process and any real recogniser (the tests use a stub interpreter); native dialogs with a display;
the composition of the AppImage runtime beyond its file names (the map records the electron-builder-binaries source);
`SOURCE_DATE_EPOCH` determinism of the AppImage (the sidecar is not bit-reproducible: `base_library.zip` member order
changes per build); a FreeType other than 2.13.2 in a future Pillow wheel; the exact URLs of the recorded sources
(recorded, not fetched).
