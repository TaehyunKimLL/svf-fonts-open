**English** | [한국어](desktop-app.ko.md)

# SVF maker desktop app

The SVF maker desktop app turns your own fonts into SVF faces on your own computer. You pick fonts (outline fonts, bitmap
fonts, classic Mac Hangul fonts, DOS Johab fonts, existing SVF files) and an output folder; the app detects what each file
is, offers the conversion routes that fit, runs the repository's font tools, shows every result drawn by the same C
renderer the games use, and writes the faces into the output folder. Nothing is uploaded and nothing is sent anywhere.

This page describes what the app is and how to use it. How it is built and packaged (AppImage, licences, release check) is
in [maker-desktop.md](maker-desktop.md); the server and its HTTP API are in [../maker/README.md](../maker/README.md); the
design is `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`.

Status: the Linux AppImage is built and tested on the author's host (Ubuntu 24.04, x86_64). Windows and macOS packages are
**not built and not verified** (see the last section). The package is not signed and has no auto-update.

## Contents

1. What the app is made of
2. Starting the app
3. The window, step by step
4. Inputs the app understands
5. Routes and presets
6. What a run writes
7. Menu, zoom and window state
8. Privacy and security
9. Where files live, logs, and environment variables
10. Failure handling
11. Limits and what has not been verified

## 1. What the app is made of

The app is three layers in one package.

| Layer | What it is | Where |
|---|---|---|
| Shell | An Electron program: one window, a native menu, four native dialogs. It starts and stops the other two layers and hands the page a tiny bridge. | `desktop/main.js`, `desktop/preload.js`, `desktop/lib/*.js` |
| Maker server (the "sidecar") | A Python HTTP server bound to `127.0.0.1` on a random port. It detects fonts, plans routes, runs the tools as jobs and serves the page. In the package it is a PyInstaller one-directory bundle, `svf-maker-sidecar`; every tool is the same executable, called as `svf-maker-sidecar run-tool <name>`. | `maker/*.py`, `tools/*.py` |
| Page | The user interface, plain HTML and ES modules served by the sidecar. It previews faces by running the C renderer compiled to WebAssembly (`maker/static/wasm/svf.wasm`) in the page itself. | `maker/static/` |

The window title is "SVF maker". The shell loads exactly one page, `http://127.0.0.1:<port>/`; while the sidecar is still
starting (more than 2 seconds) the window shows a small "starting the maker..." page.

## 2. Starting the app

On Linux the package is one file, `svf-maker-<version>.AppImage` (about 150 MB).

    chmod +x svf-maker-0.1.0.AppImage
    ./svf-maker-0.1.0.AppImage

- The AppImage mounts itself with its own statically linked FUSE 3 code; it needs only `fusermount` or `fusermount3` on
  the machine (present on Ubuntu 24.04), not `libfuse.so.2`.
- It needs glibc 2.39 or newer (the build host's version; nothing older is tested).
- A graphical session is required. Without `$DISPLAY` the app stops with Electron's "Missing X server" message.
- Only one app per user runs at a time. Starting it again focuses the existing window (and its second process quits
  before it spawns anything). Two servers can never share one data folder (`instance.lock`).
- On systems that forbid unprivileged user namespaces (Ubuntu 24.04 does) the launcher adds `--no-sandbox`, and the
  renderer runs without Chromium's sandbox; Help > About says so. See section 8.

Start-up sequence, for the curious: the shell takes the single-instance lock, opens its log, starts the sidecar with a
fresh random token and `127.0.0.1:0`, waits for the line `svf-maker listening on 127.0.0.1:<port>` (up to 75 s; a normal
start prints it well within 2 s), opens the window and loads the page. The page asks `/api/caps` once to learn whether
it runs in local mode and which optional parts exist.

## 3. The window, step by step

The window opens at 1200 x 800 (the size and position you leave it in are remembered). The page has a top bar and four
areas: sources (left), batch settings (middle), fonts (right) and steps (bottom).

### 3.1 First run: the acknowledgement

The first time per session you start a conversion the page shows "before you convert": you are responsible for having the
right to convert the fonts you choose, faces are written only to your chosen output folder, and if you publish them you
should check each font's licence. Press OK to continue. The tools never check licences for you; when no licence is
chosen, every note and `BUILD.md` says "licence: not checked (user's responsibility)".

### 3.2 Sources panel (left)

1. **choose files** opens the native file dialog (multi-select). **choose folder** opens the native folder dialog. Each
   pick is added to the list of source roots; you can pick several times. Fonts are read **where they are**: they are not
   copied or uploaded, and an archive is only listed, not unpacked.
2. The text box "paths, one absolute path per line" is the same list as text; you can paste paths instead of using the
   dialogs.
3. **choose output folder** opens a folder dialog (with "create folder"); it starts in the folder you used last. The
   "output folder" text box shows or takes the path directly.
4. **detect** reads the sources and fills the fonts table.

Every path is checked: it must be absolute, must not be a symbolic link, must not be the app's own data folder, and must
not overlap the output folder or another source.

While a job lives the app keeps intermediate files in `.svf-maker-<id>/` inside the output folder (permissions 0700) and
removes them when the job ends, is deleted or the app quits. Choose an output folder that is **not synced** by a cloud
client.

Below the panel, **jobs** lists the jobs of this session so you can switch between them.

### 3.3 Fonts table (right)

After detection every font (or every face of a collection) is a row: its file, family and style, its kind (see section
4), the pixel sizes it offers if the font is a bitmap, a per-row include box, and a drawn preview of Hangul syllables made
by the WASM renderer. A row with no route stays disabled and unchecked, with the reason shown (for instance a Hangul
font that has no companion table). The page also lists refused files (not a font, unreadable, outside the rules) in a
"refused" list instead of hiding them.

### 3.4 Batch settings (middle)

One set of settings applies to the whole batch; a row can opt out.

| Control | Meaning |
|---|---|
| dest | The sub-folder of the output's `svf/` tree the faces go to (an existing name from the list, or "new" with a name such as `my/set`). |
| kinds | **precomposed**: one variable-width glyph per syllable (SVF v3). **jamo**: a face that carries jamo pieces and composes syllables at draw time (JSET block). Tick one or both. |
| layout | For jamo: the piece layout (for example `844`, `adaptive`, `621`, or a Mac or Hanterm layout when the source needs it). |
| sizes | Pixel sizes to produce, such as `16, 20`. Bitmap fonts offer only the sizes they contain. |
| bpp | 1 bit or 2 bits per pixel; tick one or both. |
| range | The set of characters to include. |
| preset | A named recipe (section 5). "plain" uses the tools' defaults. |
| advanced panel | Fine controls: cell, ascent, width, space advance, mono hint, clip cell, fit cell, Latin top, embolden, symbols, JSET version, header ascent, fit baseline, AA refine, clean noise, binarize (threshold, ridge, mono), Latin ascent, Hangul ascent. A value here wins over the preset's. Controls that a route cannot use are hidden or disabled. |

### 3.5 Buttons in the top bar

| Button | Does |
|---|---|
| save settings | Stores the current settings on the job (and reads them back for checking). |
| run | Queues the job. The status line shows its state and, if the server is busy, its position. |
| cancel | Stops the running job and kills its tool processes. |
| edit and re-run | After a run, returns to the settings with the same sources. |
| open folder | Shows the output folder in the system file manager (only for a folder you picked in this app). |
| download zip | Used by upload mode of the plain web page; the desktop app writes into the output folder instead and has no zip. |
| delete job | Forgets the job and frees its output folder; faces already written stay. |

### 3.6 Steps table (bottom)

Each job is a list of steps (detect, convert, check, preview...). The table shows each step with its tool, its argument
list, its state, and the end of its log, so you can see exactly which command ran for which font. Every result face is
drawn on a canvas, and the page counts a face as good only when the canvas has ink.

## 4. Inputs the app understands

| Input | Notes |
|---|---|
| TrueType, OpenType, collections (`.ttf`, `.otf`, `.ttc`), variable fonts | Outline fonts. A variable font is converted at the instance you choose. |
| BDF, PCF, HBF bitmap fonts | ISO 10646, ISO 8859 and KS C 5601 encodings; Johab BDF. |
| DOS raw Hangul fonts | Johab 8x4x4 / 6x2x1 style raw fonts (and 24 px HBIOS). An HWP `ASCII.PFT` (12x24 English) is used as a companion for a 24 px face; `HANGUL*.PFT` is not read and is shown as not read. |
| Classic Mac HangulTalk 7.1 type-3 `fbit` | From a resource fork, an AppleDouble `._Name`, a MacBinary `.bin`, a JM archive or a raw `fbit` resource; needs the HTBL 1 table (`InputBackSupport` or `<Name>.htbl1`, picked as another source) and may use a Latin suitcase (FOND + NFNT). |
| Classic Mac HangulTalk 1.0 fonts | The fork with its `fdef`; a raw 1.0 `fbit` without `fdef` is listed with what is missing. |
| Hanterm Johab fonts | Layout `hanterm-johab`. |
| SVF files (`.svf`) | Copied (when allowed by the route) or used as the source for a jamo fit; an SVF upload keeps its own JSET block. |

No proprietary font, bitmap or table is distributed with the app. The tests use synthetic inputs.

A licence file next to a font is used only when it is picked too (or the whole folder is picked). The app can record the
licence you choose in the face's note; it never decides on its own that a font is free to convert.

## 5. Routes and presets

For each font the maker offers the routes that fit its kind. A route is a fixed sequence of the repository's tools:

| Kind | Routes |
|---|---|
| precomposed | `mkfont` (outline to SVF); `johab844` (DOS raw, 16 px); `bdfface`; `mac fbit 7.1 bdf + mkfont`; `copy` (an SVF as is) |
| jamo | `composite`; `experimental fit` (2 bpp, slow, quality-bound); `mask fit` (needs `freetype-py` and `uharfbuzz`, see section 9); `vector fit` (takes minutes per font); `dos raw`; `hanterm`; `mac fbit 1.0`; `mac fbit 7.1 direct` and `derived`; `bdfface + from-svf fit`; `from-svf fit`; `copy` |

Presets are named starting points. The advanced panel overrides them.

| Preset | Recipe | Reproduces |
|---|---|---|
| `plain` | the tools' defaults | |
| `dos-l-1bpp` | cell 16, 1 bpp, ASCII + KS X 1001 without hanja + 8 extras | `svf/dos/NEODG16.SVF` (one glyph fewer) |
| `dos-u-2bpp` | cell 16, 2 bpp, clip cell, ascent size-2 | `svf/dos/GBATB17.SVF` (byte-identical at size 17), `NGOTB16.SVF` |
| `latin-18cell-2bpp` | cell 18, width 18, 2 bpp, listed characters only | `svf/dos/PAPLG16.SVF` |
| `jamo-844`, `jamo-844-symbols`, `jamo-844-hbios24`, `jamo-621` | jamo layouts from DOS raw fonts | the layouts named in `maker/presets.py` |

## 6. What a run writes

Inside the output folder, and nothing else:

    <output>/
      svf/<dest>/<NAME>.SVF          the face
      svf/<dest>/<NAME>.TXT          its note (how it was made, the licence you chose or "not checked")
      svf/<dest>/<licence file>      when a licence text was chosen
      build-<id>/
        BUILD.md                     what was converted, with which commands
        LICENCES.tsv.lines           lines for the repository's web/LICENCES.tsv
        FAMILIES.tsv.lines           lines for its families table
        FACES.TSV.lines              lines for its faces table

- A name the job did not write itself is never replaced. If a file is already there the run skips or refuses; it does not
  overwrite your files.
- The `.lines` files are fragments that you merge into the repository's tables by hand (the repository's
  `web/mkindex.py --check` accepts the merged result).
- Every written face passes the repository's `facecheck.py`, and the page draws it with the renderer before it counts as
  done.

## 7. Menu, zoom and window state

- **File**: Open output folder; Quit.
- **View**: Reload; Actual size; Zoom in and Zoom out (Ctrl and `+` or `-`, from 50% to 300%).
- **Help**: About shows the app version, build id, Electron, Chromium and Node versions, the sidecar's version and Python,
  the renderer sandbox state, and a button for the third-party licences (`THIRD-PARTY.txt`).

The shell remembers four things in `shell-state.json`: the window position and size, the zoom factor, the last output
folder, and the output folders it handed out (the last 32, as real paths; only those can be opened by "Open output
folder"). It stores no token and no input path.

## 8. Privacy and security

- **No network.** The page's Content-Security-Policy allows only its own origin; the shell cancels every request that is not
  to the sidecar (new windows, navigation, downloads, device and permission requests are all refused); the maker's own code
  imports no network library. There is no telemetry, no crash upload and no update check.
- **Token.** The sidecar is started with a new random token on every launch. The shell adds it as `X-Maker-Token` to the
  page's `/api/` requests; the page itself never sees it. Every request must also carry this server's `Host`; the server
  binds to loopback only and refuses anything else.
- **Bridge.** The page gets `window.svfMaker` with four functions: `pickFiles()`, `pickFolder()`, `pickOutputDir()`,
  `openOutputFolder()` (and the read-only `platform`). The shell answers only a frame of the maker's own origin. Paths are
  absolute; a cancelled dialog returns an empty list or `null`.
- **Files.** Fonts are read in place and never modified. Output is written only under the folder you chose.
- **Sandbox.** The page runs with context isolation, no Node integration and a sandboxed preload. Chromium's own process
  sandbox is **off** where the system denies user namespaces (an AppImage cannot carry the SUID helper); the renderer then
  loads only the app's own page from loopback.
- **Processes.** Each tool runs in its own session and is recorded in `tools.pids`; quitting the app, or a crash, leaves
  no tool running (the next start reaps leftovers).
- **Third-party code.** `THIRD-PARTY.txt` lists every bundled library with its licence; a build fails on an unattributed
  or GPL library.

## 9. Where files live, logs, and environment variables

| What | Where |
|---|---|
| App data (jobs, work files, `instance.lock`, `tools.pids`) | `~/.config/svf-maker/maker` (the app's user-data folder plus `maker`) |
| Window state | `~/.config/svf-maker/shell-state.json` |
| Shell log | `~/.config/svf-maker/logs/` (no font names or paths beyond what the redaction rules allow; token never) |
| Development run data | `~/.config/svf-maker/maker-dev` |

Optional environment variables (set them before starting the app):

| Variable | Effect |
|---|---|
| `JAMOSET_PYLIB` | A folder with `freetype-py` and `uharfbuzz`; enables the `mask fit` route and `binarize mono`. |
| `SVF_RECOG_PYTHON` + `SVF_RECOG_DIR` | An interpreter (absolute path, with numpy, torch, PIL, fontTools) and a folder with your own `recog.py` for the piece identity check. Scoring only; nothing is shipped. Without them the page says the check is unavailable. |
| `SVF_MAKER_DEV=1` | Development mode: run `python3 maker/server.py` from a checkout instead of the frozen sidecar. `SVF_MAKER_DEV_REPO` names the checkout. |
| `SVF_MAKER_DEVTOOLS=1` | Enables the developer tools and a View > Toggle DevTools item. |
| `SVF_MAKER_SHELL_LOG=stderr` | The shell log also goes to standard error. |
| `SVF_MAKER_SMOKE=1` | Start, check `/api/caps`, print one line and quit (used by the release check). |

## 10. Failure handling

- **The server fails to start** (error dialog, then the app quits): the dialog shows the last lines of the server's
  output. If another maker is still shutting down, wait a moment and start again.
- **The server stops while the app runs**: a dialog offers Restart or Quit. Restarts are limited; too many in a short time
  ends the app.
- **The window crashes**: the app reloads the same page once; a second crash shows a message and quits.
- **Quitting**: the shell asks the sidecar to stop (up to 45 s), cancels the running job and kills its tool processes. A
  job that was queued or running at that moment is marked failed (`interrupted`), because its working files go with the
  process; faces already written in the output folder remain.
- **Disk full, unusual file systems, case-insensitive disks, sync clients**: not tested (see below).

## 11. Limits and what has not been verified

- Windows and macOS: not built, not run. The server is not Windows-ready (process-group, lock and file-link calls are
  POSIX). The macOS plan (signing, notarisation) is written in [maker-desktop.md](maker-desktop.md).
- The `mask fit` route has never run a job on the author's host (the libraries are not installed there); the identity
  check has only been tested with a stub; `vector fit` takes minutes per font.
- Native dialogs, the file manager integration, starting through a real FUSE mount with a window, the GPU path and a
  sandboxed renderer are checked by hand only; the automated tests stub the dialogs and run with the GPU off.
- Real Mac, HWP and Johab files are tested only where an environment variable points at your own copy; the repository's
  tests use synthetic inputs.
- The AppImage is not bit-reproducible, and there is no automatic update; a new version is a new file.
