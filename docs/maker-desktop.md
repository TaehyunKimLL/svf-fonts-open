**English** | [한국어](maker-desktop.ko.md)

# SVF maker desktop implementation and packaging

SVF maker consists of an Electron shell, a Python HTTP server (sidecar), and a page served by that server.
It builds a Linux x86_64 AppImage. See the [desktop app](desktop-app.md) for installation and use,
the [maker guide](../maker/README.md) for the server and HTTP API, and the [capability audit](maker-audit.md)
for conversion features. The [design](superpowers/specs/2026-11-05-maker-desktop-design.md) and
[implementation plan](superpowers/plans/2026-11-05-maker-desktop.md) describe the architecture.

## 1. Runtime structure

| Component | Behaviour | Implementation |
|---|---|---|
| Electron shell | Single-instance lock, window, menus, native dialogs, sidecar lifecycle | `desktop/main.js`, `desktop/preload.js`, `desktop/lib/` |
| Sidecar | PyInstaller one-dir bundle started with `serve --exit-with-parent=<pid>` | `maker/sidecar.py`, `maker/sidecar.spec` |
| Tool launch | `python3 -P tools/<name>.py` in source mode; `svf-maker-sidecar run-tool <name>` when frozen | `maker/toolrun.py` |
| Preview | C renderer compiled to WebAssembly and run in the page | `maker/build-wasm.sh`, `maker/static/svfview.js`, `c/ports/web/` |

The shell creates a fresh 16-byte random token encoded as 32 hexadecimal characters and starts the server on
`127.0.0.1:0`. It waits up to 75 seconds for `svf-maker listening on 127.0.0.1:<port>`.
After 2 seconds without readiness it displays a starting page. Once the port is known it loads the loopback HTTP
page and adds `X-Maker-Token` to `/api/` requests. The token is not passed to the page.

The page's `window.svfMaker` exposes `pickFiles()`, `pickFolder()`, `pickOutputDir()`,
`openOutputFolder()` and `platform`. The last function takes no argument. The shell looks up the current job's
output folder and checks it against the last 32 real paths chosen through its dialog before showing it in the file manager.

Data lives in `maker/` under Electron's `userData`, or `maker-dev/` for development runs.
The Linux default is `~/.config/svf-maker/`; `--user-data-dir` can override it.
The server's `instance.lock` prevents concurrent use of one data folder.
Each tool runs in a separate session registered in `tools.pids`. Normal shutdown stops it; after an abnormal exit,
the next start reaps identifiable leftovers. The shell allows 45 seconds for shutdown, then 5 seconds after a forced kill.

## 2. Linux build

Follow the Quick start's [prerequisites and installation commands](desktop-app.md#0-quick-start) first.
The requirements are a git checkout, Python 3.12 with pip, Pillow and fontTools for the system Python,
Node.js 22.12 or newer with npm, emsdk, `xvfb-run` and `flock`.
The pinned wheels target Linux x86_64 CPython 3.12. emsdk defaults to `~/opt/emsdk`, overridden by `$EMSDK`.

Run from the checkout root:

```sh
mkdir -p "$HOME/work/tmp"
cd desktop
npm ci
node node_modules/electron/install.js
cd ..
bash desktop/build/build-appimage.sh
```

Running Electron's installation script explicitly fetches the binary even when npm blocks install scripts.
Versions are pinned in `desktop/package-lock.json` and `desktop/build/requirements.lock`.

| Component | Pinned version |
|---|---|
| Electron | 45.2.3 |
| electron-builder | 26.18.0 |
| PyInstaller | 6.22.3 |
| Pillow | 10.2.0 |
| fontTools | 4.66.1 |
| AppImage toolset | appimage@1.0.3 |

`maker/build-sidecar.sh` builds WASM, installs hash-checked wheels with `pip --target`, runs PyInstaller,
and performs an `env -i` self-check and frozen tests. `build-appimage.sh` does not skip the frozen tests.
After generating notices, electron-builder creates `desktop/dist/svf-maker-0.1.0.AppImage`.
The version comes from `desktop/package.json`.

Scratch lives under `$SVF_DESKTOP_TMP` (default `$HOME/work/tmp/svf-desktop-build`).
The build and release-check scripts acquire `$HOME/work/tmp/svf-browser.lock` themselves for the smoke test.
Wrapping either in `flock` on that same lock deadlocks. `desktop/test/run-e2e.sh` does not acquire the lock itself;
its caller manages the lock when running it separately. That test takes a short scratch path through `TMP_DIR`
and forwards it as `TMPDIR`.

### 2.1. Release checks

`desktop/build/release-check.sh APPIMAGE [--release]` checks the following:

| Check | Condition |
|---|---|
| `size`, `size-sidecar` | AppImage ≤ 170 MiB; sidecar `du -sm` result ≤ 60 |
| `extract`, `layout` | Successful extraction, required resources present, no tests or caches in staged sources |
| `apprun`, `desktop-entry` | `unshare` probe and `--no-sandbox` branch present; entry uses `AppRun` |
| `runtime` | No ELF interpreter, dynamic dependencies or `libfuse.so.2` string; version output and exit status checked with only HOME and PATH in the environment |
| `frozen` | Extracted sidecar passes frozen tests with no skips |
| `wasm` | Byte-equal to a fresh WASM build |
| `licences`, `notices`, `sources` | Licence mapping, regenerated notices and bundled Python sources verified |
| `smoke` | Extracted `AppRun` starts under Xvfb, API responds, normal exit and process termination checked |
| `sources` (`--release`) | LGPL corresponding-source archive gate satisfied |
| `contents` | File inventory saved per build identifier and AppImage hash |

Without `--release`, the corresponding-source gate prints `CHECK sources skipped`.
Both source checks use the name `sources`; read their details to distinguish them.
Any failure produces exit status 1. The smoke test allows 90 seconds for Electron after acquiring the lock.
It tests extracted execution, so it does not also prove FUSE mounting works.

## 3. AppImage runtime and sandbox

`desktop/build/appimage-toolset.json` pins the SHA-256 hashes of the toolset archive, runtime and removed libraries.
The selected runtime is type2-runtime 20251108 with statically linked FUSE 3 code.
It does not need the host's `libfuse.so.2`, but does need `fusermount` or `fusermount3` and permission to mount.
When mounting is unavailable, use `--appimage-extract` and run the extracted `AppRun`.

`AppRun` adds `--no-sandbox` if `unshare -Ur true` fails.
Ubuntu's user-namespace restrictions depend on system policy; the distribution name alone does not establish sandbox status.
The shell requests `sandbox: true`, `contextIsolation: true` and `nodeIntegration: false`, but these do not enable
Chromium's process sandbox when running with `--no-sandbox`.
The shell log and Help > About show the detected state.

The shell blocks remote requests, new windows, downloads and permission requests. The page and sidecar communicate
over loopback HTTP. These controls do not provide operating-system network isolation for subprocesses such as an
optional recogniser. See Electron's security guide and Ubuntu's user-namespace notes in section 7.

## 4. Licences and corresponding sources

`desktop/build/third-party.mjs` generates `THIRD-PARTY.txt`. Shared libraries must match
`third-party-map.json`; sidecar libraries must match their build provenance.
Ordinary GPL libraries are rejected. The PyInstaller bootloader is classified separately as GPL with its bootloader exception.
LGPL components need a distribution record, and `svf/` may contain only allow-listed OFL faces.

`prune-appimage-toolset.py` removes the toolset's GPL-3.0 `libindicator` and its dependent `libappindicator`.
The app has no tray icon. Licence texts for the runtime's embedded components are in
`desktop/build/licences/appimage-runtime.txt`.

For a public release, prepare `desktop/build/out/sources/MANIFEST.json` and corresponding-source archives, then run
`bash desktop/build/build-appimage.sh --release`. Each LGPL component requires a `source` entry whose
`component` and `version` match the map; the AppImage runtime also requires a `recipe` entry.
Every entry needs `archive` and `sha256`. For example:

```json
[
  {"component": "appimage-runtime", "version": "20251108", "kind": "source", "archive": "runtime-src.tar.gz", "sha256": "<hex>"},
  {"component": "appimage-runtime", "version": "20251108", "kind": "recipe", "archive": "runtime-recipe.txt", "sha256": "<hex>"}
]
```

This example shows only runtime entries. Other mapped LGPL components, including Electron's ffmpeg, are also required.
The generator must print `corresponding sources archived: YES` to pass the release source check.

## 5. Automated checks and recorded runs

`npm test --prefix desktop` runs Node tests for shell utilities, notice generation, extraction verification and the
runtime checker without an Electron window. `maker/test/test_frozen.py` needs a built sidecar.
`desktop/test/run-e2e.sh` needs Xvfb and Electron; it stubs dialogs and disables the GPU.
Its second pass against the packaged layout needs `SVF_MAKER_SIDECAR` and `SVF_MAKER_STAGED_REPO`.

`maker/test/uisample.py` defines the sample conversion's inputs and expected outputs.
It uses four OFL fonts and synthetic Mac, HWP and BDF inputs to check 10 faces and 3 TTF/BDF exports.
It checks the expected file tree, unchanged inputs, face validation and actual drawing, and equality between
development and packaged results for pure-Python routes. Some outline byte differences are allowed because the
host and pinned wheels may use different FreeType versions. TTF comparisons normalise `head` timestamps.
`maker/test/test_uisample.py` exercises the checks in detail.

A recorded run on 2026-11-22 built a 140,426,554-byte AppImage from commit `3d40de8` on Ubuntu 24.04 x86_64.
The window and a local conversion also worked under Xvfb on a clean Ubuntu 24.04.5 host.
These measurements do not guarantee the size or time of a current build.

## 6. Support and remaining verification

- The build targets Linux x86_64. Windows and macOS packages have not been built or run.
- Windows needs changes or validation for `fcntl`, process-group termination, file locking/linking and path checks.
  macOS also needs separate wheels, signing, notarisation and process-identity checks. The Linux wheel lock cannot be reused unchanged.
- The recorded build host used glibc 2.39. Older glibc compatibility is unverified; required symbol versions depend
  on the collected binaries.
- A real window manager and GPU, native dialogs, file-manager integration and a sandboxed renderer need separate manual checks.
- An external recogniser's real model is unverified. Optional libraries are not bundled.
- Bit-for-bit AppImage reproducibility is not guaranteed, and there is no automatic update.

See the [C renderer](c-renderer-guide.md), [web renderer](web-renderer-guide.md) and
[renderer design](../spec/renderer-design.md) to use the output faces.

## 7. 참고 문헌 / References

- Electron: security recommendations — <https://www.electronjs.org/docs/latest/tutorial/security>
- Electron: process sandbox — <https://www.electronjs.org/docs/latest/tutorial/sandbox>
- Ubuntu 24.04: unprivileged user-namespace restrictions — <https://discourse.ubuntu.com/t/ubuntu-24-04-lts-noble-numbat-release-notes/39890>
- AppImage type2-runtime 20251108 — <https://github.com/AppImage/type2-runtime/releases/tag/20251108>
- AppImage runtime licence — <https://github.com/AppImage/type2-runtime/blob/20251108/LICENSE>
- PyInstaller bootloader exception — <https://pyinstaller.org/en/stable/license.html>
- GNU LGPL 2.1 — <https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html>
