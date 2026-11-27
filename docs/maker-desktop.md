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

### 5.1. Linux host measurements (2026-11-09–24)

Recorded on Ubuntu 24.04 x86_64 with glibc 2.39. The size/build run on November 22 and sample run on November 24 retain their dates and commits below; the other observations have no separate execution date. These are historical measurements, not current test counts or timing guarantees.

| Item | Value |
|---|---|
| Sidecar one-dir | 47 MB; build 8-9 s (about 30 s with the frozen test); startup port line well under 2 s |
| AppImage | 140 MB (133.9 MiB, commit 3d40de8, 2026-11-22; 149.7 MB before the static runtime and zstd); `linux-unpacked` 335 MB; electron-builder about 50 s; the whole script 1 min 26 s with warm caches |
| Frozen test | 28 tests, 0 skipped: byte-equal to the pinned wheels under `env -i` (svf2ttf and rawcarve too), the 7 bundled recipes, frozen jobs and notes equal source mode |
| Electron task counts (`--no-sandbox --disable-gpu` under xvfb) | one instance 87, second-instance case 114 (planning measurements, with the GPU 143 and 170); the lifecycle test's peak was 79-80 |
| Debian Pillow comparison | equal |
| `sample set` e2e step | dev 12.6 s, packaged 14.9 s (17 steps: 10 faces and 3 TTF / BDF exports; 2026-11-24, commit 8c10dc1); before the exports dev 10.4 s, packaged 15.0 s (14 steps) |

## 6. Support and remaining verification

Packaging in this checkout targets Linux x86_64. Section 6.5 describes the separate Windows branch.

### 6.1. glibc floor

The recorded Linux package uses glibc 2.39 (Ubuntu 24.04), the build host's version, as its supported floor.
PyInstaller bundles collected system libraries but does not ship glibc. No exact minimum required-symbol audit
was recorded, so compatibility with older glibc is not promised. Rebuilding in an Ubuntu 22.04 (glibc 2.35)
container to widen compatibility was a plan, not a completed build.

### 6.2. Manual checks for a human on a real desktop

- Open native file, folder and output-folder dialogs on a real display; check selection and cancellation. Automated tests stub them.
- Check that **open folder** shows the selected output folder in the desktop file manager.
- Run `./svf-maker-0.1.0.AppImage` in a session with a window manager to check FUSE mounting and window display together.
- Run with the GPU enabled; automated checks use `--disable-gpu`.
- On a host allowing user namespaces, verify sandboxed execution and the detected state in Help > About.

### 6.3. Clean-machine start record (2026-11-20)

Host `pc` ran Ubuntu 24.04.5 without `libfuse2t64` or `libfuse.so.2`; `fusermount` and `fusermount3` were present.
There was no display and no package was installed for the test. The then-current AppImage (about 133 MB,
zstd squashfs) was copied to `~/work/tmp/svf-clean` and run with `env -i HOME="$HOME" PATH=/usr/bin:/bin`.

```text
$ ./svf-maker-0.1.0.AppImage --appimage-version
AppImage runtime version: https://github.com/AppImage/type2-runtime/commit/dd6cebe
# exit 0
$ ./svf-maker-0.1.0.AppImage
ERROR:ui/ozone/platform/x11/ozone_platform_x11.cc:257] Missing X server or $DISPLAY
# exit 1
$ ./svf-maker-0.1.0.AppImage --appimage-mount
# squashfs mounted, including AppRun, chrome_100_percent.pak, ...
```

The old runtime's `dlopen(): error loading libfuse.so.2` failure was gone. Electron started from the mounted
image and exited for lack of a display. This run did not verify a window.

### 6.4. Xvfb window record (2026-11-22)

On the same `pc` host, the AppImage from commit `3d40de8` started under Xvfb: the window rendered and a local-mode
conversion ran through the packaged sidecar. A clean checkout of that commit built following the Quick start in
1 minute 26 seconds with warm caches, producing a 140,426,554-byte AppImage; all `CHECK` results in that run succeeded.
Both the extracted `AppRun` and the AppImage printed `svf-maker smoke ok SVF maker` under Xvfb.
The development launch `node_modules/.bin/electron --no-sandbox .` from `desktop/`, also under Xvfb, logged
`sidecar start mode=dev` and the port line. These results do not establish real window-manager or GPU behaviour.

### 6.5. Windows and macOS (status on 2026-11-27)

**Windows:** branch `windows-build` has an x64 NSIS installer and portable executable build.
[GitHub Actions run 45350084767](https://github.com/TaehyunKimLL/svf-fonts-open/actions/runs/45350084767)
succeeded on 2026-11-24 at commit `edd8a6d`. As of 2026-11-27 it has not merged into main.
The branch's `desktop/package.json` selects `nsis` and `portable`; `.github/workflows/windows.yml` runs Windows
suites, frozen-sidecar build, packaging, e2e and smoke checks. This success does not establish Windows support in
current main. Earlier porting work concerning main's POSIX locks, process groups and file-link calls is retained
in the historical records below.

**macOS:** no package has been built or run. The plan was separate arm64/x86_64 PyInstaller one-dir builds and
`dmg`/`zip` packages; universal2 would need universal wheels. The Linux cp312 wheel lock cannot be reused unchanged.
Developer ID signing, hardened runtime/entitlements, individual sidecar binary signing, `notarytool` notarisation
and stapling remain plans, not a verified build procedure. Process identity using `ps -o lstart=` and native
resource forks have not been verified on macOS either.

### 6.6. Other unverified items

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
- Windows build, 2026-11-24 — <https://github.com/TaehyunKimLL/svf-fonts-open/actions/runs/45350084767>

## 8. 기록 / Records

### 8.1. Earlier platform plan and verification limits (2026-11-22–24)

The following is the historical record. Its Windows “not built” status is superseded by section 6.5.
Porting/signing commands and external platform descriptions below remain the plan as recorded, not successful execution evidence.

> ### Windows and macOS (UNVERIFIED)
>
> Nothing below was run. It is the plan a builder on those hosts follows, and what blocks it. Not built or verified.
>
> - **macOS.** PyInstaller one-dir builds the same spec on macOS (arm64 and x86_64 are separate builds; a universal2
>   build needs universal wheels of Pillow and fontTools; `desktop/build/requirements.lock` pins Linux cp312 wheels only).
>   The server already runs on macOS (POSIX), but the registry's macOS start time (`ps -o lstart=`) is untested. electron-builder
>   target `dmg` + `zip`; `extraResources` the same; the AppImage's `--no-sandbox` question does not exist. Signing: a
>   Developer ID Application certificate, `mac.hardenedRuntime: true`, an entitlements file allowing nothing beyond
>   `com.apple.security.cs.allow-unsigned-executable-memory` (Chromium) - and every binary under `resources/sidecar/` must be
>   signed too (`codesign --deep` does not reach `_internal/*.so` reliably; sign them individually with `--options runtime`),
>   then `notarytool submit` and `stapler`. Without signing, Gatekeeper blocks the app on first run (right-click Open works).
> - **Windows.** The **server is not Windows-ready** (`os.killpg`, `start_new_session`, `signal.SIGTERM` to a group,
>   `os.umask(0o077)` semantics, `os.link` for the no-replace write, `fcntl` locks in the registry and the data-root lock): a
>   port needs Job Objects (or `CREATE_NEW_PROCESS_GROUP` + `GenerateConsoleCtrlEvent`) for the group kill, `CreateProcess`
>   flags in `run_command`/`run_bounded`, and a review of every `realpath`/inode rule of the local-mode design on NTFS. That is
>   a card of its own; until it is done the Windows build is not attempted. Then: the same PyInstaller spec (keep
>   `console=True` and the shell's `windowsHide`), electron-builder target `nsis` or `portable`, the Electron spawn with a Job
>   Object, signing with a code-signing certificate.
>
> ### Not verified here
>
> Windows and macOS entirely; an AppImage start on a real desktop (window manager, GPU; the Xvfb window run above is done); a sandboxed renderer; glibc older than 2.39; `JAMOSET_PYLIB` with
> 3.12 wheels in the frozen process and any real recogniser (the tests use a stub interpreter); native dialogs with a display;
> the composition of the AppImage runtime beyond what its binary states (its embedded licence list and version strings: type2-runtime, musl libc, libfuse 3.15.0, squashfuse 0.5.2, libzstd 1.5.6, zlib 1.3.1; musl's own version is not embedded, so its COPYRIGHT is taken from v1.2.5);
> `SOURCE_DATE_EPOCH` determinism of the AppImage (the sidecar is not bit-reproducible: `base_library.zip` member order
> changes per build); a FreeType other than 2.13.2 in a future Pillow wheel; the exact URLs of the recorded sources
> (recorded, not fetched).

### 8.2. Sample-conversion verification details (2026-11-20–24)


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
