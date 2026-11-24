**English** | [한국어](maker-desktop.ko.md)

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

The user-facing version of this (what to install, where the AppImage lands, the first run) is the Quick start of
[desktop-app.md](desktop-app.md); this section is the record.

Prerequisites on the build host: a git checkout (the scripts read `git log` and `git describe`), emsdk (`$EMSDK`, default
`~/opt/emsdk`; `maker/build-wasm.sh` compiles the preview module itself; emcc 6.0.13 last used; install with
`sh c/cross/install-toolchains.sh "$HOME/opt" emsdk`), Python 3.12.3 with pip (the wheels are cp312; `python3 -m venv`
does not work on Ubuntu without `python3-venv`; the build uses `pip install --target` and `python3 -S`) and, for the
system `python3` that runs the frozen tests and the development run, Pillow and fontTools (`python3-pil`,
`python3-fonttools` from apt; apt's fontTools 4.46.0 is older than the pinned 4.66.1, see desktop-app.md), node 22.12 or
newer (apt has 18: NodeSource or nvm) and npm 12 (22.23.4 and 12.0.2 last used), `xvfb-run` and `flock` for the release check's smoke run (without `xvfb-run` the
`smoke` check fails and the script exits 1, but the AppImage is already in `desktop/dist/`), `~/work/tmp` (the browser lock
file lives there), network access once for the pinned wheels, Electron and the AppImage toolset.

    # in the checkout root
    cd desktop && npm ci && node node_modules/electron/install.js && cd ..   # npm 12 blocks install scripts (Electron's download)
    bash desktop/build/build-appimage.sh [--release]                         # any directory; it changes to the root itself

`npm ci` prints a warning about blocked install scripts (`electron-winstaller`'s `select-7z-arch.js`); it is harmless for a
Linux build. `~/.local/bin/heavy` is the author's resource guard, not a requirement: the build runs without it (the author
runs `~/.local/bin/heavy bash desktop/build/build-appimage.sh`). The AppImage is `desktop/dist/svf-maker-<version>.AppImage`.

Versions last used (all pinned: `desktop/build/requirements.lock` with hashes, `desktop/package-lock.json`):
PyInstaller 6.22.3, Pillow 10.2.0, fontTools 4.66.1, Electron 45.2.3, electron-builder 26.18.0.

Scratch: the scripts take `SVF_DESKTOP_TMP` (default `$HOME/work/tmp/svf-desktop-build`: pip download, PyInstaller work
directory, the pruned toolset, extractions); tests take `TMP_DIR` (keep it short: under about 40 characters past `$HOME`,
Chrome's socket path is limited to 107 bytes). Never `/tmp`. Every run that starts Chrome or Electron takes
`flock $HOME/work/tmp/svf-browser.lock` and runs under `~/.local/bin/heavy`.

`build-appimage.sh` runs `maker/build-sidecar.sh` (the frozen test included, no skip allowed), writes `THIRD-PARTY.txt`
(fails on an unattributed library or a GPL one), builds the AppImage and runs `desktop/build/release-check.sh`, which
prints one `CHECK <name> ok|FAIL` line each: size, extract, size-sidecar, layout, apprun, runtime (the AppImage's runtime is static: no loader, no needed library, no `libfuse.so.2` string; `desktop/build/check-runtime.mjs`, tested by `desktop/test/check-runtime.test.js`; and `--appimage-version` exits 0 with its version line under `env -i`), desktop-entry, frozen
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
| AppImage | 140 MB (133.9 MiB, commit 3d40de8, 2026-11-22; 149.7 MB before the static runtime and zstd); `linux-unpacked` 335 MB; electron-builder about 50 s; the whole script 1 min 26 s with warm caches |
| Frozen test | 28 tests, 0 skipped: byte-equal to the pinned wheels under `env -i` (svf2ttf and rawcarve too), the 7 bundled recipes, frozen jobs and notes equal source mode |
| Electron task counts (`--no-sandbox --disable-gpu` under xvfb) | one instance 87, second-instance case 114 (planning measurements, with the GPU 143 and 170); the lifecycle test's peak was 79-80 |
| Debian Pillow comparison | equal |
| `sample set` e2e step | dev 12.6 s, packaged 14.9 s (17 steps: 10 faces and 3 TTF / BDF exports; 2026-11-24, commit 8c10dc1); before the exports dev 10.4 s, packaged 15.0 s (14 steps) |

### Sample set (e2e, t_30b843b8)

`desktop/test/e2e.js` has one step per pass, `sample set`, that converts a fixed sample **through the page** in local mode
(inputs read in place, faces written into the chosen output folder), in the dev pass and in the packaged pass. The sample is
defined by `maker/test/uisample.py` (it builds the synthetic inputs at test time and owns the per-font settings table, the
expected 36-file tree and the checks): four OFL fonts of `ttf/` read in place (neodgm, NanumGothic-Bold, GowunBatang-Bold with
the `dos-u-2bpp` preset, Caveat-VF at its Bold instance), and synthetic files from the repository's fixture builders: a Mac 7.1
fbit with its HTBL table and suitcase, a HangulTalk 1.0 font, a Mac dfont, an HWP DOS 844 font with `ASCII.PFT` (`HANGUL24.PFT`
shown as not read), and KSC / johab BDFs; the KSC face is also written as `KSC16.ttf` and `KSC16.bdf` and the johab jamo set
as `JOHA16J.ttf` with `--composite` (their overrides' "also write" selects, t_97acecf9). The step picks the 9 roots and the output folder with the stubbed dialogs, changes only
enabled controls (the rows with no route stay disabled and unchecked, asserted), saves, reads the saved settings back, runs, and
then `uisample.py check` verifies: exactly the expected files and no others (no leftover `.svf-maker-*`), `facecheck.py` and
`web/mkindex.py --check` on the written tree, every face draws ink, `GOWUN17A.SVF` byte-equal to `svf/dos/GBATB17.SVF`, each
export holding exactly its face's characters (`quality.export_facts`), and the inputs unchanged. Only then are the 10 result canvases counted (`data-drawn="1"`, `Number(dataset.ink) > 0`). In the packaged
pass `--same-as` compares the faces with the dev pass: byte equality is required for the pure-Python faces (SEOU12J, HAN224J,
JOHA16J, KSC16, MUNJ16J); a difference in an outline face (NEODU16, NANUM17A, GOWUN17A, CAVEA16, SYNTH16) is printed as an
`E2E NOTE` (the dev pass renders with the host's Pillow/FreeType, the packaged one with the pinned wheels), not a failure.
`KSC16.bdf` must be byte-equal and `KSC16.ttf` and `JOHA16J.ttf` equal once its `head` timestamps are set equal (svf2ttf.py stamps the time
of the run).
`maker/test/test_uisample.py` runs the same table through the HTTP API and proves each check fails on a mutation.

## The sandbox

An AppImage cannot carry Chromium's SUID sandbox helper (FUSE mounts are `nosuid`), so the only sandbox it can have is
the user-namespace one, and Ubuntu 24.04 denies unprivileged user namespaces. electron-builder's `AppRun` probes
`unshare -Ur true` and adds `--no-sandbox` when that fails; the AppImage's `.desktop` entry reads
`Exec=AppRun %U` (the entry is the same with or without user namespaces; `AppRun` adds the flag by itself, see below). So on this host and on every Ubuntu 24.04-class system the renderer runs **without** a
sandbox (the shell logs and About shows "renderer sandbox: off (--no-sandbox; user namespaces unavailable)"); on a system
with user namespaces it would run sandboxed (not verified). The renderer only ever loads the app's own page from a
loopback server with a strict CSP, plus files the user picked; no remote content is loaded (D7, spec section 17). A `.deb`
with an AppArmor profile would restore the sandbox on Ubuntu 24.04: a later card (D13), not done here.

## The AppImage toolset, the runtime and the tray icon

**Runtime (t_ea7dcc8e).** The AppImage built with electron-builder's default (legacy `appimage-12.0.1`) toolset carries
the old type-2 runtime, which `dlopen()`s `libfuse.so.2`: on a clean Ubuntu 24.04.5 (no `libfuse2t64`) it stopped with
"dlopen(): error loading libfuse.so.2 ... AppImages require FUSE to run". `desktop/package.json` therefore sets
`"toolsets": {"appimage": "1.0.3"}` (electron-builder 26.18.0's own switch): the runtime is then the static-pie
type2 runtime of AppImage/type2-runtime **release 20251108** (`runtimes/runtime-x64`, sha256 `2fca8b44...260d`, taken from
the electron-builder-binaries release `appimage@1.0.3`, archive `appimage-tools-runtime-20251108.tar.gz` sha256 `84021a78...7665`,
both pinned in `desktop/build/appimage-toolset.json` and in electron-builder). It mounts through its own statically linked
libfuse3 and needs only a `fusermount`/`fusermount3` on the machine (present on Ubuntu 24.04). Other differences of the
newer tool path: squashfs compression is zstd (the legacy path used gzip), and the generated `.desktop` entry reads
`Exec=AppRun %U` (the `--no-sandbox` flag is added by `AppRun` itself when `unshare -Ur true` fails, as before). The release
check `runtime` keeps this from regressing. The runtime's sources (type2-runtime 20251108 with libfuse3 and squashfuse) are
the D8 component `appimage-runtime` version `20251108` (LGPL component to archive: libfuse 3.15.0; recipe: the type2-runtime release). THIRD-PARTY.txt carries the texts of all six embedded components (`desktop/build/licences/appimage-runtime.txt`, each from its upstream source at the matching version, source URLs recorded) and prints the runtime's sha256 beside the toolset record.

**Tray icon.** electron-builder copies six old libraries into the AppImage's `usr/lib` (appindicator3, gconf, indicator3,
notify, Xss, Xtst). `libindicator` is **GPL-3.0**, and the packaging rule forbids GPL in the package; the legacy toolset and
the 1.0.x ones all carry it. The build therefore points electron-builder (`APPIMAGE_TOOLS_PATH`) at a copy of the toolset
from which `libindicator` and `libappindicator` are removed (`desktop/build/prune-appimage-toolset.py`, driven by
`desktop/build/appimage-toolset.json`: the downloaded archive's sha256, the runtime's sha256 and the sha256 of each removed
file are checked and printed in THIRD-PARTY.txt; no binary is stored in the repository). **Tray-icon support
(libappindicator) is not shipped**: it cannot load without `libindicator`, and the app has no tray icon, so nothing is lost.
The release check proves the pruned AppImage still starts (extracted `AppRun` smoke) and that no GPL library remains.

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
     {"component": "appimage-runtime", "version": "20251108", "kind": "source", "archive": "runtime-src.tar.gz", "sha256": "<hex>"},
     {"component": "appimage-runtime", "version": "20251108", "kind": "recipe", "archive": "runtime-recipe.txt", "sha256": "<hex>"}]

(one `source` entry per LGPL component whose component and version equal the map's, plus a `recipe` for the AppImage
runtime). `build-appimage.sh --release` then fails unless the generator prints "corresponding sources archived: YES".

## glibc floor

The sidecar bundles the system libraries PyInstaller finds except glibc, so the package needs glibc at least the build
host's (2.39, Ubuntu 24.04). A container build on Ubuntu 22.04 (glibc 2.35) would widen it (D9; not done).

## Manual checks (a human with a real desktop)

Native file and folder dialogs (the tests stub them), "open folder" in the desktop's file manager, starting the AppImage
through FUSE with a window on a real desktop with a window manager (`./svf-maker-0.1.0.AppImage`; the mount and a window
under Xvfb were shown on the clean host, see below), the GPU path (the tests use `--disable-gpu`), a sandboxed renderer on a host with user namespaces.

## Clean-machine start (t_ea7dcc8e, 2026-11-20)

Host `pc`: Ubuntu 24.04.5, no `libfuse2t64` (`libfuse.so.2` absent), `fusermount`/`fusermount3` present, no display, nothing
installed for the test. The AppImage built from this branch (133 MB, zstd squashfs) was copied to `~/work/tmp/svf-clean` and run
with `env -i HOME=$HOME PATH=/usr/bin:/bin`:

    $ ./svf-maker-0.1.0.AppImage --appimage-version
    AppImage runtime version: https://github.com/AppImage/type2-runtime/commit/dd6cebe          (exit 0)
    $ ./svf-maker-0.1.0.AppImage
    ERROR:ui/ozone/platform/x11/ozone_platform_x11.cc:257] Missing X server or $DISPLAY          (exit 1)
    $ ./svf-maker-0.1.0.AppImage --appimage-mount     # the squashfs is mounted: AppRun, chrome_100_percent.pak, ... listed

The libfuse error is gone; the run now fails only for the missing display, after the FUSE mount (Electron started from the
mounted image).

### The window under Xvfb (t_9b9e0bd8 record, 2026-11-22)

On the same host `pc` (Ubuntu 24.04.5, no `libfuse2t64`) the AppImage built from commit 3d40de8 started under Xvfb: the
window rendered, and a conversion in local mode ran through the packaged sidecar. Not verified: a real desktop with a
window manager and a GPU, and Windows and macOS. In this documentation task the same commit was built from a clean
checkout following the Quick start (1 min 26 s with warm caches, every `CHECK` line ok, AppImage 140,426,554 bytes), the
extracted `AppRun` and the AppImage itself printed the smoke line `svf-maker smoke ok SVF maker` under Xvfb, and the
development run (`node_modules/.bin/electron --no-sandbox .` in `desktop/`, under Xvfb) logged `sidecar start mode=dev`
and the sidecar's port line.

## Windows (t_9b8f56f0)

Windows x64 is built and tested on GitHub Actions (`windows-latest`, workflow `.github/workflows/windows.yml`), never on a
desktop machine. One run does, in this order: the WASM preview module on an Ubuntu runner (emsdk 6.0.13, the pin of
`c/cross/install-toolchains.sh`; `maker/build-wasm.sh` is bash and emcc is not set up on the Windows runner), handed to the
Windows job as an artifact; on Windows the maker suite and the tools suite through `desktop/build/run-suite.py` (it prints
`SUITE ... ran= skipped=` and one `SKIP <n> <reason>` line per skip reason), the desktop unit tests, the frozen sidecar
(`desktop/build/build-sidecar-win.py`, frozen test included with `SVF_MAKER_FROZEN_REQUIRED=1`), `THIRD-PARTY.txt`
(`third-party.mjs --platform win32`, fail closed), the desktop e2e (development pass, then the packaged sidecar), the
installer and the portable `.exe` (electron-builder `--win nsis portable`, unsigned), and the smoke of the unpacked app, the
installed app and the portable app (`desktop/build/smoke-win.py`). The two `.exe` files and `THIRD-PARTY.txt` are the
run's artifact `svf-maker-windows`. pip and npm downloads are cached.

### Build it yourself (Windows)

Not tried outside the runner; the steps are the workflow's. A git checkout (`.gitattributes` keeps every file byte for byte:
no CRLF conversion), Python 3.12 (3.12.3 used) on `PATH` as `python`, node 22 with npm, and the WASM module built
elsewhere (Linux or WSL: `bash maker/build-wasm.sh`) and copied to `maker/static/wasm/`:

    # in the checkout root, PowerShell
    python -m pip install --require-hashes "--only-binary=:all:" --no-deps -r desktop/build/requirements-win.lock
    cd desktop; npm ci; cd ..
    python desktop/build/fetch-fribidi-win.py $env:USERPROFILE\work\tmp\fribidi   # and put that folder on PATH (below)
    $env:PATH = "$env:USERPROFILE\work\tmp\fribidi;$env:PATH"
    python desktop/build/build-sidecar-win.py          # wheels, icon.ico, FriBiDi, PyInstaller, provenance, staged repo, selfcheck, frozen test
    $lic = python -c "import os, sys; print(os.path.join(sys.base_prefix, 'LICENSE.txt'))"
    node desktop/build/third-party.mjs --platform win32 --sidecar desktop/build/out/sidecar/svf-maker-sidecar `
      --provenance desktop/build/out/sidecar-provenance.json --electron desktop/node_modules/electron/dist `
      --pysite "$env:USERPROFILE\work\tmp\svf-desktop-build\pysite" --repo desktop/build/out/repo --meta . `
      --python-licence $lic --out desktop/build/out/THIRD-PARTY.txt
    cd desktop; npx electron-builder --win nsis portable --x64 --publish never; cd ..
    python desktop/build/smoke-win.py desktop/dist

**FriBiDi.** Pillow's Windows wheel carries libraqm and HarfBuzz but loads FriBiDi at run time, and does not ship it;
without it Pillow falls back to its basic layout, and a face made on Windows is not the bytes the same face made on Linux
is (measured: GowunBatang-Bold 17 px 2 bpp gained U+00AD and drew U+2116 differently; a combining mark kept its
advance). `desktop/build/fetch-fribidi-win.py` downloads conda-forge's MSVC build of FriBiDi 1.0.10 (archive and DLL
sha256-pinned) and the build bundles `fribidi-0.dll` in the sidecar's `_internal/` (the spec refuses to build without
it); a development run or the test suites on Windows need that folder on `PATH`. FriBiDi is LGPL-2.1-or-later: a
separate, replaceable DLL, listed with a distribution record, and under the D8 release gate like `ffmpeg.dll`.

`desktop/build/requirements-win.lock` pins the win_amd64 cp312 wheels with hashes (the same Pillow 10.2.0, fontTools
4.66.1 and PyInstaller 6.22.3 as Linux, plus PyInstaller's Windows-only `pefile` and `pywin32-ctypes`). The spec
(`maker/sidecar.spec`) is the Linux one; on Windows it adds UTF-8 mode (`X utf8_mode=1`: a frozen program ignores
`PYTHONUTF8`) and the icon. `desktop/package.json` `build.win`: targets `nsis` (one-click, per user, no elevation,
Start-menu shortcut "SVF maker", installs to `%LOCALAPPDATA%\Programs\svf-maker`) and `portable`; icon
`build/out/icon.ico`, made from `build/icon.png` by `make-icon.py --ico` (not committed).

Notices: `desktop/build/third-party-map-win.json` attributes every `*.dll` and `*.pyd` of the sidecar's `_internal/` and of
Electron's folder (case-blind). The DLLs and extension modules of the python.org interpreter (CPython, OpenSSL, libffi, ...)
take their text from that interpreter's `LICENSE.txt` (`--python-licence`), which carries the licences of the libraries the
Windows build bundles. Microsoft binaries that come with the interpreter or with Electron (`VCRUNTIME140*.dll`,
`d3dcompiler_47.dll`, `dxil.dll`) are class `ms-redist`: redistributed unmodified under Microsoft's terms
(`desktop/build/licences/ms-distributable.txt` says so; it is not their licence text), and so is the app-local Universal
CRT the python.org build carries (`ucrtbase.dll`, `api-ms-win-*.dll`). ANGLE (`libEGL.dll`, `libGLESv2.dll`)
and the DirectX Shader Compiler point at `LICENSES.chromium.html`. The copyleft parts are the same as on Linux minus the
AppImage runtime, plus FriBiDi: `ffmpeg.dll` and `fribidi-0.dll` (LGPL-2.1; the D8 release gate applies to both the same
way) and the PyInstaller bootloader.

### What differs on Windows (the server)

`maker/oscompat.py` holds every primitive that POSIX and Windows spell differently; on POSIX each function is exactly the
call the maker made before, so Linux behaviour is unchanged.

| What | POSIX | Windows |
|---|---|---|
| A tool's process tree | new session; `killpg` SIGTERM, then SIGKILL after 5 s | started suspended in a new process group with no console, put into its own Job Object (`KILL_ON_JOB_CLOSE`), then resumed; a stop terminates the job at once (no grace period: no SIGTERM exists for it). A job that cannot be made or assigned refuses the tool. |
| A dead sidecar's tools | `PR_SET_PDEATHSIG` + the next start's reap | the kernel kills them when the sidecar's job handles close; the reap kills a recorded pid and every process below it (snapshot parent links, creation time checked) |
| Stopping the sidecar | the shell sends SIGTERM to its group | the shell closes the sidecar's stdin (`serve --stop-on-eof`): the same clean stop as SIGTERM; after 45 s it kills it (TerminateProcess) |
| The parent watch (`--exit-with-parent`) | `getppid()` polled | the parent's process handle, opened at start and waited on |
| Data-root and registry locks | `flock` | `msvcrt.locking` of one byte far past the end of the lock file (the file stays readable) |
| A replace or read racing another thread | atomic, never fails | a sharing violation is retried for up to 2 s (`retry_sharing`) |
| Links | `S_ISLNK` | a symlink **or any name-surrogate reparse point** (junction, mount point); `lstat` reports a junction as a folder, so it is checked by its reparse tag |
| No-follow open of an existing file | `O_NOFOLLOW` | `lstat` (a link is refused), open, `fstat`: the file must be the one `lstat` saw (volume serial + file index) |
| The output tree | directory descriptors and `*at()` calls | every folder written through is held open without delete sharing and without following a reparse point (`hold_dir`): it, and every folder above it, cannot be renamed or removed while the write runs; the path -> identity checks before and after each landing are the same as on POSIX |
| New-name claim | `link()`, else `O_EXCL` + replace + read-back | the same (`CreateHardLink`; FAT/exFAT and shares without hard links take the second way) |
| Output names | as the naming rules say | also refused: a device name (`CON`, `NUL.TXT`, `COM1`, ...), a trailing dot or space, the characters `<` `>` `:` `"` `/` `\` `?` `*` and the vertical bar (`TreeRefused`; an upload archive member too) |
| Picked paths | absolute | absolute with a drive or a UNC share; a device path (`\\.\`), an extended-length path (`\\?\`), a drive root and an alternate data stream (`name:stream`) are refused; a relative path inside a source may hold no drive and no colon |
| `SVF_MAKER_ROOTS` | `:`-separated | `;`-separated |
| Permission bits | `umask 077`, folders 0700, files 0600 | no mode bits: the data folder's privacy is its ACL, inherited from the user's profile (`%APPDATA%`) |
| Text written by the maker and the tools | LF | LF (`newline="\n"` on every text write; a tool's CRLF stdout is read as LF) |

Not the same guarantee: on POSIX a folder swapped between two landings is detected and the write stops (`OutputGone`); on
Windows the swap itself is impossible while the folders are held, so the write completes into the folder that was checked.
A swap of a folder the tree has not reached yet is still caught by `lstat` + identity before the folder is held.

### Measured (GitHub Actions windows-latest)

Windows Server 2025 (build 26100) runners, Python 3.12.3, node 22, 2026-11-24.

| Item | Value |
|---|---|
| Sidecar one-dir | about 30 MB; `build-sidecar-win.py` 55 s including the frozen test (28 tests, 0 failed, 2 skipped: the fork race and the `PR_SET_PDEATHSIG` knob, POSIX by nature; on Windows the Job Object covers both) |
| Installer | `svf-maker-0.1.0-setup.exe` 138,366,326 bytes; silent per-user install and uninstall checked |
| Portable | `svf-maker-0.1.0-portable.exe` 125,605,175 bytes |
| Smoke start to the clean stop | unpacked 1.3 s, installed 1.5 s, portable 12.5 s (it unpacks itself first); Help > About's line: "renderer sandbox: on" |
| Desktop e2e | 33 steps pass (development pass and packaged pass, the sample set included; `sample set` dev 20.9 s, packaged 20.2 s). The `sh` stub's stderr canary is POSIX only. |
| Maker suite | 1,277 tests in two shards (13 and 27 min; the Chrome page tests are the slow part), 0 failed, 62 skipped: 30 POSIX by nature (permission bits, signals, FIFOs, zombies, `/proc` and `PR_SET_PDEATHSIG`, `/dev/zero`, the `resource` module, Chrome's Unix socket path, a namespace), 1 the U+2116 pin below, 31 the same environment skips as on Linux (your real fonts and ROMs, optional libraries, the slow fit, the frozen classes, which run in the package job) |
| Tools suite | 980 tests (6.5 min), 0 failed, 642 skipped: 609 POSIX by nature (the C renderer's host build with gcc sanitizers and its bench and VESA shell scripts: on Windows the renderer runs as the WASM module; a mode-000 folder; the bash build scripts), 33 environment skips as on Linux |
| Desktop unit tests | 43 pass (`unit.test.js`, `third-party.test.js`, a win32 notices case included) |
| Notices | `THIRD-PARTY.txt` 15 components, no unattributed DLL |

**Not byte-equal on Windows.** With FriBiDi in place every face of the test suites is the Linux bytes except one measured
glyph: GowunBatang-Bold at 17 px 2 bpp (`dos-u-2bpp`, the shipped `svf/dos/GBATB17.SVF`) draws U+2116 differently with
Pillow's Windows build, so on Windows that face is written as a new face rather than recognised as the shipped one. The
tests pin exactly that glyph (`maker/test/wincompat.py`, `WINDOWS_RENDER_DIFFERS`): every other glyph and metric must
be equal. The cause is not established (FreeType 2.13.2 and raqm 0.10.1 on both sides).

## macOS (UNVERIFIED)

Nothing below was run. It is the plan a builder on that host follows. Not built or verified.

- **macOS.** PyInstaller one-dir builds the same spec on macOS (arm64 and x86_64 are separate builds; a universal2
  build needs universal wheels of Pillow and fontTools; `desktop/build/requirements.lock` pins Linux cp312 wheels only).
  The server already runs on macOS (POSIX), but the registry's macOS start time (`ps -o lstart=`) is untested. electron-builder
  target `dmg` + `zip`; `extraResources` the same; the AppImage's `--no-sandbox` question does not exist. Signing: a
  Developer ID Application certificate, `mac.hardenedRuntime: true`, an entitlements file allowing nothing beyond
  `com.apple.security.cs.allow-unsigned-executable-memory` (Chromium) - and every binary under `resources/sidecar/` must be
  signed too (`codesign --deep` does not reach `_internal/*.so` reliably; sign them individually with `--options runtime`),
  then `notarytool submit` and `stapler`. Without signing, Gatekeeper blocks the app on first run (right-click Open works).

## Not verified here

Windows and macOS entirely; an AppImage start on a real desktop (window manager, GPU; the Xvfb window run above is done); a sandboxed renderer; glibc older than 2.39; `JAMOSET_PYLIB` with
3.12 wheels in the frozen process and any real recogniser (the tests use a stub interpreter); native dialogs with a display;
the composition of the AppImage runtime beyond what its binary states (its embedded licence list and version strings: type2-runtime, musl libc, libfuse 3.15.0, squashfuse 0.5.2, libzstd 1.5.6, zlib 1.3.1; musl's own version is not embedded, so its COPYRIGHT is taken from v1.2.5);
`SOURCE_DATE_EPOCH` determinism of the AppImage (the sidecar is not bit-reproducible: `base_library.zip` member order
changes per build); a FreeType other than 2.13.2 in a future Pillow wheel; the exact URLs of the recorded sources
(recorded, not fetched).
