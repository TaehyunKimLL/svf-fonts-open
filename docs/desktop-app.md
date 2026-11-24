**English** | [한국어](desktop-app.ko.md)

# SVF maker desktop app

The SVF maker desktop app turns your own fonts into SVF faces on your own computer. You pick fonts (outline fonts, bitmap
fonts, classic Mac Hangul fonts, DOS Johab fonts, existing SVF files) and an output folder; the app detects what each file
is, offers the conversion routes that fit, runs the repository's font tools, shows every result drawn by the same C
renderer the games use, and writes the faces into the output folder. Nothing is uploaded and nothing is sent anywhere.

This page describes what the app is and how to use it. How it is built and packaged (AppImage, licences, release check) is
in [maker-desktop.md](maker-desktop.md); the server and its HTTP API are in [../maker/README.md](../maker/README.md); the
design is `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`.

Status: the Linux AppImage is built and tested on the author's host (Ubuntu 24.04, x86_64) and was started on a second,
clean Ubuntu 24.04.5 host (section 13). The Windows x64 installer and portable `.exe` are built and tested on GitHub
Actions (`windows-latest`); no one has used them on a Windows desktop yet (section 13). macOS is **not built and not
verified**. No package is signed, and there is no auto-update.

## Quick start

On Linux (x86_64) there is no download: the app is built from a git checkout of this repository, as below. On Windows
(x64) take the two `.exe` files the build workflow makes ([Windows (x64)](#windows-x64) below). macOS is not supported yet
(section 13).

**You need**

| What | Notes |
|---|---|
| A git checkout | The build reads `git log` and `git describe`; a plain source archive does not work. |
| Python 3.12 with pip | `python3 --version` must say 3.12 and `python3 -m pip` must work: the sidecar's pinned wheels are cp312 (3.12.3 last used). `python3-venv` is not needed. |
| Pillow and fontTools for the system `python3` | A stock Ubuntu 24.04 has neither. The build's frozen tests and the development run (below) import the maker's own Python code with the system `python3`, and that code imports `PIL` and `fontTools` (`maker/detect.py`). The packaged app does not need them (it carries pinned wheels: Pillow 10.2.0, fontTools 4.66.1). Install them with apt (below). Nothing else is imported at start-up: numpy, torch, freetype-py, uharfbuzz and pathops are optional and only used by routes that say so. |
| node 22 and npm | node 22.12 or newer (`desktop/package-lock.json` requires it); Ubuntu 24.04's apt has node 18, which is too old: use NodeSource or nvm. npm 12 with node 22.23.4 was used (npm 10, which node 22 bundles, was not tried). |
| emsdk | The build compiles the preview module (WebAssembly) itself. It looks for `emcc` in `$EMSDK/upstream/emscripten/emcc`; `$EMSDK` defaults to `~/opt/emsdk`. Without one: `sh c/cross/install-toolchains.sh "$HOME/opt" emsdk` (emcc 6.0.13 last used). |
| `xvfb-run` and `flock` | The last build step starts the new AppImage once under a virtual display (a smoke check). Without `xvfb-run` that check fails and the script exits 1, but the AppImage already exists (see below); it is only unchecked. `flock` is from util-linux. |
| Network, first build only | pip downloads the pinned wheels (hash-checked), npm and Electron download their packages, electron-builder downloads its AppImage toolset. Later builds reuse the caches. |
| Disk | A few GB: `desktop/node_modules`, the scratch directory and `desktop/dist` (the unpacked tree is about 335 MB). |

On a fresh Ubuntu 24.04 the packages are (`flock` is in util-linux, always present; `libpython3.12-dev` is not needed on a
host that has `libpython3.12t64`, which `python3` pulls in; a host without it was not tried):

    sudo apt install git curl xz-utils python3-pip python3-pil python3-fonttools xvfb

`python3-pil` is Pillow 10.2.0, the pinned version. `python3-fonttools` is 4.46.0, older than the pinned 4.66.1: the maker's
detect, route, local-mode and end-to-end test files (`maker/test/test_detect.py`, `test_routes.py`, `test_local.py`,
`test_e2e.py`) pass with it; the frozen test itself was not run with it (the author's host has fontTools 4.66.1
from pip). If you want the pinned one: `python3 -m pip install --user --break-system-packages fonttools==4.66.1`. `curl`,
`xz-utils` and `git` are what `install-toolchains.sh` needs to fetch emsdk. node 22 is installed separately (see the node
row).

**Build** (the working directory is written in front of each command; the commands are run once, in this order)

    # in the checkout root
    mkdir -p ~/work/tmp                          # the release check keeps its lock file there
    cd desktop && npm ci && node node_modules/electron/install.js && cd ..
    bash desktop/build/build-appimage.sh

- `npm ci` prints a warning that npm 12 blocked install scripts (for instance `electron-winstaller ... select-7z-arch.js`);
  it is harmless here, because the app is packaged for Linux only. The same blocking is why Electron's own binary is
  fetched by `node node_modules/electron/install.js`.
- `build-appimage.sh` changes into the checkout root by itself, so it can be started from anywhere, but all other
  commands here start in the checkout root. It builds the WebAssembly module, the frozen sidecar (with its tests), the
  notices file and the AppImage, then prints one `CHECK <name> ok` line per release check. A failing check ends the script with exit
  status 1.
- The build keeps its scratch (pip downloads, PyInstaller work directory, extractions) in `$SVF_DESKTOP_TMP`, by default
  `~/work/tmp/svf-desktop-build`; set the variable to another folder if you like. Delete it when no build is running.
- `~/.local/bin/heavy` is the author's resource guard (it limits memory and tasks on a shared host). You do not need it:
  start the build as shown. With the caches warm it took 1.5 minutes here; a first build takes longer (downloads).

**Where the AppImage lands**: `desktop/dist/svf-maker-0.1.0.AppImage` (the version is `desktop/package.json`'s), about
133 to 134 MiB (140 MB). Measure your own build; the number depends on the toolchain. Copy it anywhere; it is one
self-contained file.

**Start it** (a graphical session is needed; the first conversion below is done in the app). From the checkout root, right
after the build:

    chmod +x desktop/dist/svf-maker-0.1.0.AppImage
    desktop/dist/svf-maker-0.1.0.AppImage

or copy it first:

    mkdir -p "$HOME/Apps"
    cp desktop/dist/svf-maker-0.1.0.AppImage "$HOME/Apps/"
    cd "$HOME/Apps" && ./svf-maker-0.1.0.AppImage

Later sections write `./svf-maker-0.1.0.AppImage` for the file in the current directory.

**First conversion**

1. The window "SVF maker" opens. In the sources panel press **choose files** (or **choose folder**) and pick a font, for
   example a `.ttf`.
2. Press **choose output folder** and pick an empty folder that is not synced by a cloud client.
3. Press **detect**, read the "before you convert" note and press OK. The fonts table fills.
4. Tick the **use** box of each row you want (a row is pre-ticked only when a licence file was found with its font, and a
   DOS raw font never is), look at the batch settings (the preset `plain` is fine for a first try), and press **run**. The steps table shows each step's state, seconds and stderr (the commands themselves
   are written to `build-<id>/BUILD.md` in the output folder; [recipes.md](recipes.md#desktop-app-and-maker-routes) maps each route to its command line).
5. When the job is done, press **open folder**: the faces are in `<output>/svf/<dest>/` (section 6).

**Run from the checkout without packaging** (for development; no AppImage, no PyInstaller; it needs the same Python, node,
emsdk and network as above, but only once, and it also needs the apt packages above: the shell starts the maker with the
system `python3`, which must import Pillow and fontTools):

    # in the checkout root
    cd desktop && npm ci && node node_modules/electron/install.js
    bash ../maker/build-wasm.sh                  # still in desktop/: builds maker/static/wasm/svf.wasm
    node_modules/.bin/electron --no-sandbox .    # still in desktop/

The shell finds no packaged sidecar, so it starts `python3 -P maker/server.py` from the checkout (data folder
`~/.config/svf-maker/maker-dev`). `--no-sandbox` is for hosts that deny user namespaces (Ubuntu 24.04); leave it out
elsewhere. Logs go to `~/.config/svf-maker/logs/shell.log` (`SVF_MAKER_SHELL_LOG=stderr` also prints them).

**Remove it**: delete the AppImage and `~/.config/svf-maker/` (section 12).

### Windows (x64)

**Get it.** The repository's workflow `windows` (`.github/workflows/windows.yml`, on GitHub Actions) builds both Windows
packages on every push to its branch and on demand; open a green run and download its artifact `svf-maker-windows` (a zip,
kept 14 days). It holds:

| File | What it is |
|---|---|
| `svf-maker-0.1.0-setup.exe` | The installer: one click, for your user only (no administrator rights), installs to `%LOCALAPPDATA%\Programs\svf-maker` and adds "SVF maker" to the Start menu. Uninstall from Settings > Apps (or "Add or remove programs"). |
| `svf-maker-0.1.0-portable.exe` | One file that runs without installing: every start unpacks the app to a temporary folder first (a few seconds) and removes it at the end. |
| `THIRD-PARTY.txt` | The notices of everything bundled (the installed app carries the same file). |

To build them yourself on Windows see [maker-desktop.md](maker-desktop.md#windows-t_9b8f56f0).

**Unsigned: SmartScreen.** Neither file is code-signed. When you start one that came from the internet (a downloaded zip
marks its contents), Windows SmartScreen shows "Windows protected your PC". Choose **More info**, check that the file is
the one you downloaded from the run, then **Run anyway**. The browser may also warn on the download itself
("not commonly downloaded"). An antivirus may take a while to scan the portable file the first time. Nothing else asks for
permission: the installer does not elevate, and the app makes no network connection (Windows Firewall is never asked).

**Use it.** Start "SVF maker" from the Start menu (or the portable file). The window and the steps are the same as on Linux
(First conversion above; sections 3 to 7). Paths are Windows paths (`C:\Users\you\Fonts`, `\\server\share\fonts`);
a whole drive (`C:\`) cannot be the output folder.

**Where things are.** The app's data is in `%APPDATA%\svf-maker\` (`maker\` holds the jobs, `logs\shell.log` the log;
section 9). **Remove it**: uninstall (installer) or delete the portable file, then delete `%APPDATA%\svf-maker\` (section 12).

## Contents

Quick start (above)

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
11. Messages you may see
12. Recovery, desktop integration and uninstall
13. Limits and what has not been verified

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

On Linux the package is one file, `svf-maker-<version>.AppImage` (about 133 to 134 MiB; build it as in the Quick start).

    chmod +x svf-maker-0.1.0.AppImage
    ./svf-maker-0.1.0.AppImage

- The AppImage mounts itself with its own statically linked FUSE 3 code; it needs only `fusermount` or `fusermount3` on
  the machine (present on Ubuntu 24.04), not `libfuse.so.2`.
- It needs glibc 2.39 or newer (the build host's version; nothing older is tested).
- `/tmp` must allow execution: the image is mounted under `/tmp/.mount_*` (section 12).
- A graphical session is required. Without `$DISPLAY` the app stops with Electron's "Missing X server" message.
- The AppImage installs nothing: no menu entry, no icon theme entry. Section 12 says how to add one.
- Only one app per user runs at a time. Starting it again focuses the existing window (and its second process quits
  before it spawns anything). Two servers can never share one data folder (`instance.lock`).
- On systems that forbid unprivileged user namespaces (Ubuntu 24.04 does) the launcher adds `--no-sandbox`, and the
  renderer runs without Chromium's sandbox (automatically; you need not pass anything); Help > About says so. See section 8.

On Windows the package is the installer or the portable `.exe` (Quick start, [Windows (x64)](#windows-x64)). The same
rules hold: one app per user at a time, one server per data folder. Chromium's renderer sandbox is on there (Help > About
says "renderer sandbox: on"). The sidecar runs without a console window; its tools too.

Start-up sequence, for the curious: the shell takes the single-instance lock, opens its log, starts the sidecar with a
fresh random token and `127.0.0.1:0`, waits for the line `svf-maker listening on 127.0.0.1:<port>` (up to 75 s; a normal
start prints it well within 2 s), opens the window and loads the page. The page asks `/api/caps` once to learn whether
it runs in local mode and which optional parts exist.

## 3. The window, step by step

The window opens at 1200 x 800 (the size and position you leave it in are remembered). The page has a top bar and, below
it: a narrow left column with the sources panel and the jobs list, the batch settings beside it (right of the left
column), the fonts table across the full width below those, and the steps table at the bottom. In a window narrower than
1000 px the areas stack in one column.

### 3.1 First run: the acknowledgement

The first time per session you press **detect** (that is before anything is created) the page shows "before you
convert": you are responsible for having the right to convert the fonts you choose, faces are written only to your chosen output folder, and if you publish them you
should check each font's licence. Press OK to continue. The tools never check licences for you; when no licence is
chosen, every note and `BUILD.md` says "licence: not checked (user's responsibility)".

### 3.2 Sources panel (left)

1. **choose files** opens the native file dialog (multi-select). **choose folder** opens the native folder dialog. Each
   pick is added to the list of source roots shown under the buttons; you can pick several times. Fonts are read **where
   they are**: they are not copied or uploaded, and an archive is only listed, not unpacked.
2. **choose output folder** opens a folder dialog (with "create folder"); it starts in the folder you used last. The chosen
   path is shown next to the button.
3. **detect** reads the sources and fills the fonts table.

In the app the page has no "paths, one absolute path per line" box and no "output folder" text box: the page hides them
whenever the shell's dialogs exist. They appear only when the page is opened without the shell (for example the server
in a browser, see [../maker/README.md](../maker/README.md)), and then you type absolute paths.

Every path is checked: it must be absolute, must not be a symbolic link, must not be the app's own data folder, must not
overlap the output folder or another source, and, when `SVF_MAKER_ROOTS` is set, must be inside one of its folders
(the output folder too: `SVF_MAKER_ROOTS=$HOME/fonts:$HOME/svf-out` allows sources under `~/fonts` and an output
folder under `~/svf-out`; an output folder outside every root is refused with `output folder: outside SVF_MAKER_ROOTS`). A refused
path is listed with its reason (section 11).

While a job lives the app keeps intermediate files in `.svf-maker-<id>/` inside the output folder (permissions 0700) and
removes them when the job ends, is deleted or the app quits. Choose an output folder that is **not synced** by a cloud
client.

Below the panel, **jobs** lists the jobs of this session so you can switch between them.

### 3.3 Fonts table (full width, below the settings)

After detection every font (or every face of a collection) is a row: its file, family and style, its kind (see section
4), the pixel sizes it offers if the font is a bitmap, a per-row include box, and a drawn preview of Hangul syllables made
by the WASM renderer. A row with no route stays disabled and unchecked, with the reason shown (for instance a Hangul
font that has no companion table). The page also lists refused files (not a font, unreadable, outside the rules) in a
"refused" list instead of hiding them.

The columns are: id, use, preview, label, family/style, sizes, coverage, jamo, licence, layout and override.

- **use** includes the row in the run. A row is pre-ticked only when a licence file was found with its font; a DOS raw
  font is never pre-ticked, because its layout must be confirmed first.
- **layout** is a DOS raw font's own control: it shows "confirm" until you pick one of the candidate layouts the detector
  found for that file size (layout names such as `844`). The run is refused with "confirm the DOS Johab layout" until you have
  chosen one; the source face is not drawn before that either. For any other kind of font the cell shows a dash.
- **override** opens a per-font panel under the row. It repeats the batch controls for this one font (dest, kinds,
  layout, sizes, bpp, range, preset; an empty value means "(batch)") and adds: **jamo route** (which of the routes
  of section 5 makes this font's jamo face; "(default)" is the first native route, and `vector fit` is marked "minutes per
  font"); **precomposed route** (only for an SVF source: `copy` or `svf2ttf`, which writes the SVF's TTF / BDF only);
  **also write** (this font's own TTF / BDF choice: "(batch)" or on / off); **experimental** (allows the routes marked experimental: with it off, a route that needs it is listed but
  refused, with the reason "needs experimental"); **latin companion** (a BDF or HBF of the batch whose Latin letters are
  added; for a Mac 7.1 `fbit` the suitcases with a strike of its size); **HTBL table** (a Mac 7.1 `fbit`'s composition
  table); **instance** (a variable font's named instance); **licence name** and **note name**; **advanced options** (the
  advanced panel of section 3.4, for this font only); the per-glyph vertical-shift editor and the output names.

### 3.4 Batch settings (right of the left column)

One set of settings applies to the whole batch; a row can opt out.

| Control | Meaning |
|---|---|
| dest | The sub-folder of the output's `svf/` tree the faces go to. Only these forms are accepted: `dos`, `jamo-extra`, `games/<name>` or `new/<name>`, where `<name>` is lower-case letters, digits and `-` (for example `new/my-set`). Pick one from the list, or "new..." and type `new/<name>`. A name such as `my/set` is refused. |
| kinds | **precomposed**: one variable-width glyph per syllable (SVF v3). **jamo**: a face that carries jamo pieces and composes syllables at draw time (JSET block). Tick one or both. |
| layout | For jamo: the piece layout (for example `844`, `adaptive`, `621`, or a Mac or Hanterm layout when the source needs it). |
| sizes | Pixel sizes to produce, such as `16, 20`. Bitmap fonts offer only the sizes they contain. |
| bpp | 1 bit or 2 bits per pixel; tick one or both. |
| range | The set of characters to include. |
| preset | A named recipe (section 5). "plain" uses the tools' defaults. |
| also write TTF / BDF | Every face the run makes is also written beside its SVF as `<NAME>.ttf` (a TrueType font with the face's pixels as outlines and an embedded bitmap strike) and / or `<NAME>.bdf`, by `tools/svf2ttf.py` ([recipes.md](recipes.md#an-svf-face-back-to-a-ttf-bitmap-font)). Off by default; a font's override can turn it on or off for that font alone. **TTF as composites** (off by default) writes a jamo set's TTF with `--composite`: its pieces once as glyphs and every syllable a composite of them (smaller, as the recipe describes); a precomposed face's TTF is unchanged. |
| advanced panel | Fine controls: cell, ascent, width, space advance, mono hint, clip cell, fit cell, Latin top, embolden, symbols, JSET version, header ascent, fit baseline, AA refine, clean noise, binarize (threshold, ridge, mono), Latin ascent, Hangul ascent. A value here wins over the preset's. Controls that a route cannot use are hidden or disabled. |

### 3.5 Buttons in the top bar

| Button | Does |
|---|---|
| save settings | Stores the current settings on the job (and reads them back for checking). |
| run | Saves the current settings first (when you changed anything), then queues the job. The status line shows its state and, if the server is busy, its position. |
| cancel | Stops the running job and kills its tool processes. |
| edit and re-run | After a run, returns to the settings with the same sources. |
| open folder | Shows the output folder in the system file manager (only for a folder you picked in this app). |
| download zip | Used by upload mode of the plain web page; the desktop app writes into the output folder instead and has no zip. |
| delete job | Forgets the job and frees its output folder; faces already written stay. |

### 3.6 Steps table (bottom)

Each job is a list of steps (detect, convert, check, preview...). The columns are id, font, kind, size, bpp, name, state,
seconds, quality, stderr and result, so you can see which step ran for which font and what it printed. A face's TTF / BDF
is a step of its own (kind `export`) right after the face: its result cell says how many glyphs the file holds (read back
and checked against the face's characters) and where it was written; when the face step fails, its exports fail with
"face step failed". The commands
themselves are not in this table: `build-<id>/BUILD.md` in the output folder lists what was run, with which commands (the route table: [recipes.md](recipes.md#desktop-app-and-maker-routes)).
Every result face is
drawn on a canvas by the renderer, so you can see what was made. (That the canvas has ink is something the repository's
tests assert, not something the app checks.)

## 4. Inputs the app understands

| Input | Notes |
|---|---|
| TrueType, OpenType, collections (`.ttf`, `.otf`, `.ttc`), variable fonts | Outline fonts. A variable font is converted at the instance you choose. |
| BDF, PCF bitmap fonts | ISO 10646 (a bitmap face, converted by `mkfont`), KS C 5601 and Johab BDF (Hangul faces). |
| HBF fonts and ISO 8859 BDF | Not converted by themselves: they have no route of their own. They are offered only as **Latin companions** of a KS C 5601 BDF Hangul font (the `bdfface` route). |
| DOS raw Hangul fonts | Johab 8x4x4 / 6x2x1 style raw fonts (and 24 px HBIOS), and headerless KS X 1001 syllable dumps (Taebaek `GHAN24.PFT`). A 12x24 English font (`GASCII24.PFT`) is used as a companion for a 24 px face. |
| HWP fonts (local mode) | HWP 1.x `HANGUL.SFT` / `HANGULn.PFT` (three faces a file, a jamo set by HWP's own rule or a precomposed face) with `ASCII.SFT` / `ASCII.PFT`; HWP 3.0 `HAN*.FNT` with `ENG*.FNT`. The `.HFT` outline fonts are not read. |
| Classic Mac HangulTalk 7.1 type-3 `fbit` | From a resource fork, an AppleDouble `._Name`, a MacBinary `.bin`, a JM archive or a raw `fbit` resource; needs the HTBL 1 table (`InputBackSupport` or `<Name>.htbl1`, picked as another source) and may use a Latin suitcase (FOND + NFNT). |
| Classic Mac HangulTalk 1.0 fonts | The fork with its `fdef`; a raw 1.0 `fbit` without `fdef` is listed with what is missing. |
| Hanterm Johab fonts | Layout `hanterm-johab` (a Johab BDF). |
| SVF files (`.svf`) | Copied (when allowed by the route) or used as the source for a jamo fit; an SVF upload keeps its own JSET block. The `svf2ttf` route turns the SVF into a TTF and / or a BDF only (tick "also write TTF" or "BDF"). |
| Known ROM sets (local mode) | Font ROMs recognised by their size and SHA-256 from the built-in recipes of `maker/recipes/`: the three 86Box Korean VGA cards, each a 512 KB KS C 5601 font ROM with its 32 KB VGA BIOS (Trigem `tg_ksc5601.rom` + `tgkorvga.bin`, Kasan `kasan_ksc5601.rom` + `et4000_kasan16.bin`, ATI `ati_ksc5601.rom` + `atikorvga.bin`). Pick the folder that holds both files: the font ROM is one row, "known: <card>", and the BIOS is labelled as read with it. With one file only the row says "part of <card>: also needs <file>; pick the folder" and offers nothing; a file with the right name and size but another hash is "looks like <card>, another revision" and is not converted. The faces are a 16 px precomposed face (Hangul from the ROM, English from the BIOS's 8x16 font) and, experimental, its 8x4x4 jamo fit ([recipes.md](recipes.md#korean-vga-font-roms-86box)). Four MAME sets the same way (pick the unpacked set's folder; a zip is not read): Samsung SPC-1500 (`ss150fnt.bin` .. `ss153fnt.bin`: a precomposed face and an exact jamo set, route `spec`), Date Quiz Go Go (`uor1` .. `uor4`), X Se Dae Quiz (`obj-1.u0811`, `obj-2.u082`: a jamo set, route `dos raw`) and Quiz King of Fighters (Korea) (`vic-080-c1.c1` .. `c4.c4`) ([recipes.md](recipes.md#korean-font-roms-in-mame-sets)). An upload job only labels them. |

No proprietary font, bitmap or table is distributed with the app. The tests use synthetic inputs.

A licence file next to a font is used only when it is picked too (or the whole folder is picked). The app can record the
licence you choose in the face's note; it never decides on its own that a font is free to convert.

## 5. Routes and presets

For each font the maker offers the routes that fit its kind. A route is a fixed sequence of the repository's tools. The
routes marked (experimental) are usable only when the font's **experimental** box is ticked; the rest are native.

| Kind | Routes |
|---|---|
| precomposed | `mkfont` (outline or ISO 10646 bitmap to SVF); `johab844` (DOS raw, 16 px); `bdfface` (KS C 5601 BDF plus a Latin companion, or a known ROM set's carved Hangul and English); `mac fbit 7.1 bdf + mkfont`; `copy` (an SVF as is); `svf2ttf` (an SVF written as its TTF / BDF only) |
| jamo | `spec` (a known set's exact jamo set: SPC-1500); `composite` (a composite-glyph outline font); `experimental fit` (outline fonts; 1 or 2 bpp, slow, quality-bound; experimental); `mask fit` (1 bpp, experimental; needs `freetype-py`, `uharfbuzz` and a mask font with OpenType jamo substitution, see section 9); `vector fit` (experimental; takes minutes per font); `dos raw`; `hanterm`; `mac fbit 1.0`; `mac fbit 7.1 direct` (native) and `derived` (experimental); `bdfface + from-svf fit` and `from-svf fit` (experimental); `copy` (an SVF that already has jamo pieces); `svf2ttf` (a jamo SVF written as its TTF / BDF only) |

Presets are named starting points. The advanced panel overrides them.

| Preset | Recipe | Reproduces |
|---|---|---|
| `plain` | the tools' defaults | |
| `dos-l-1bpp` | cell 16, 1 bpp, ASCII + KS X 1001 without hanja + 8 extras | `svf/dos/NEODG16.SVF` (one glyph fewer than the shipped file) |
| `dos-u-2bpp` | cell 16, 2 bpp, clip cell, ascent size-2 | `svf/dos/GBATB17.SVF` (byte-identical at size 17), `NGOTB16.SVF` (one glyph fewer) |
| `latin-18cell-2bpp` | cell 18, width 18, 2 bpp, listed characters only | `svf/dos/PAPLG16.SVF` |
| `jamo-844`, `jamo-844-symbols`, `jamo-844-hbios24`, `jamo-621` | jamo layouts from DOS raw fonts | the layouts named in `maker/presets.py` |

## 6. What a run writes

Inside the output folder, and nothing else:

    <output>/
      svf/<dest>/<NAME>.SVF          the face
      svf/<dest>/<NAME>.ttf, .bdf    its TTF / BDF, when "also write" asks for them (the svf2ttf route: these only)
      svf/<dest>/<NAME>.TXT          its note (how it was made, the licence you chose or "not checked")
      svf/<dest>/<licence file>      when a licence text was chosen
      build-<id>/
        BUILD.md                     what was converted, with which commands
        LICENCES.tsv.lines           lines for the repository's web/LICENCES.tsv
        FAMILIES.tsv.lines           lines for its families table
        FACES.TSV.lines              lines for its faces table

- A name the job did not write itself is never replaced. If a file is already there the run skips or refuses; it does not
  overwrite your files. The same rule holds for a `.ttf` / `.bdf`.
- A TTF / BDF carries the licence the job knows for its font (the licence file you chose, and the `.TXT` files it names
  that you picked too, in its name table or its `COMMENT` lines; a licence in CP949 is read as CP949, one in any other
  encoding than UTF-8 is embedded with its unreadable bytes replaced); without one it says that the licence of the font it was made from applies (for an SVF
  converted by `svf2ttf`, the note picked beside it: only the picked files are consulted, so a face picked from a
  repository's `svf/` tree with no licence chosen does not get the files `web/LICENCES.tsv` names, as `svf2ttf.py` run by
  hand would; choose its licence file in the row). A file a licence names that you did not pick, or a link out of the
  folder you picked, is never read. It is listed in `BUILD.md`
  (its `svf2ttf.py` command and a "written" line) but has no row in the `.lines` files and is not named in the face's
  note: those describe SVF faces. Its timestamps are now, or `SOURCE_DATE_EPOCH` when the app was started with it set.
- The `.lines` files are fragments that you merge into the repository's tables by hand (the repository's
  `web/mkindex.py --check` accepts the merged result).
- The page draws every written face with the renderer so you can look at it. The repository's own checks of a face
  (`facecheck.py`, a manifest and map checker, and `web/mkindex.py --check`) are separate: run them yourself on a face you
  add to the repository (they are not part of the app).

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
  no tool running (the next start reaps leftovers). On Windows each tool runs in a Job Object of its own: when the sidecar
  ends, however it ends, Windows ends its tools with it.
- **Windows.** The rules above hold there too, with Windows' own forms (maker-desktop.md, "What differs on Windows"): a
  junction or a mount point counts as a link and is refused like a symlink; an output name Windows reserves (`CON`,
  `NUL.TXT`, `COM1`, ...) is refused; while the faces are written, the output folder and every folder written through are
  held open so that nobody can rename or remove them meanwhile. The data folder's privacy is its folder permission (ACL),
  inherited from your user profile: Windows has no `chmod 700`.
- **Third-party code.** `THIRD-PARTY.txt` lists every bundled library with its licence; a build fails on an unattributed
  or GPL library.

## 9. Where files live, logs, and environment variables

| What | Where |
|---|---|
| App data (jobs, work files, `instance.lock`, `tools.pids`) | `~/.config/svf-maker/maker` (the app's user-data folder plus `maker`) |
| Window state | `~/.config/svf-maker/shell-state.json` |
| Shell log | `~/.config/svf-maker/logs/shell.log` (and `shell.log.1`, the rotated one; no font names or paths beyond what the redaction rules allow; token never) |
| Development run data | `~/.config/svf-maker/maker-dev` |
| Windows | the same names under `%APPDATA%\svf-maker\` (`maker\`, `shell-state.json`, `logs\shell.log`, `maker-dev\`); the installed program is in `%LOCALAPPDATA%\Programs\svf-maker\` |

Optional environment variables (set them before starting the app):

| Variable | Effect |
|---|---|
| `JAMOSET_PYLIB` | A folder with `freetype-py` and `uharfbuzz`; enables the `mask fit` route and `binarize mono`. |
| `JAMOSET_MASK_FONT` | The font file with OpenType jamo substitution (`ljmo`, `vjmo`, `tjmo`) that `mask fit` uses to confine the pieces. Without it the tool looks for NotoSansKR beside the ScummVM tree, which a packaged app does not have, so set it when you use `mask fit`. |
| `SVF_MAKER_ROOTS` | Colon-separated absolute folders (on Windows semicolon-separated: `C:\fonts;D:\out`). Every source **and the output folder** must be inside one of them (a path outside is refused with "outside SVF_MAKER_ROOTS"). Example with separate roots: `SVF_MAKER_ROOTS=$HOME/fonts:$HOME/svf-out ./svf-maker-0.1.0.AppImage`. Unset: no restriction beyond the rules in section 3.2. |
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

## 11. Messages you may see

The page shows a message line under the top bar for anything the server refuses. A line has the form
`METHOD /api/...: HTTP <status>: <text>`. The texts below are the server's own.

**The server is busy (HTTP 409 with a busy kind).** Several actions can meet a job that is being changed by another
request (a second window of the same job, a preview being made, a run being prepared). These answers are not errors in
your settings:

- The page repeats the identical request by itself after 0.5, 1 and 2 seconds (at most three repeats, and not past 15
  seconds in total), with the line ` (retrying 1/3)` appended. If it still fails, the message stays and a **Try again**
  button appears; it sends the same request once more. Starting anything else clears the message and the retry.
- `job <id> is busy; try again`, `job <id>: the previous run is finishing; try again in a moment` and `job <id> is busy: a
  preview is being made; try again`: a lock is held a moment; the automatic retry usually clears it. One exception: the
  `job <id> is busy; try again` that **detect** can answer while it creates the job is not tagged as retryable, so the page
  does not retry it and shows no **Try again** button; press **detect** again.
- `a run of job <id> is being prepared`: the answer of **run** when another window of this job pressed run a moment ago.
  The page does not repeat the run (that would race the first); it shows **Try again** and also **follows** the other
  run: every second, for up to 15 seconds, it reads the job, and when the job has left the "detected" state it shows that
  job's progress and removes the message. (A preview asked for during the preparation gets the same text with
  `; try again` appended and is retried automatically.)
- `the job changed while the run was being prepared: run again`: the settings were changed (for example from another
  window) between your save and the start of the run. The page then reads the job again and shows the saved state. Check
  the settings and press **run** again.
- `job <id> is queued` (or running): the job can no longer be edited because a run has started elsewhere. The page shows
  that job's state; **your edits stay as typed** in the form (the page never throws a draft away), but they are not saved
  until you edit and re-run.

**Folders and paths.**

- `output folder is in use by job <id> (delete it, or wait until it has been idle for 30 minutes)` (at run time the
  shorter `output folder is in use by job <id>`): only one job at a
  time may hold an output folder. Delete the other job in the jobs list (faces already written stay), or pick another
  folder. A job that has only been detected and not touched for 30 minutes gives its folder up by itself.
- `the files directory is still being moved or made on a slow or hung volume; try again later`: removing or creating the
  job's `.svf-maker-<id>/` folder is still in progress (a slow disk, a network mount, a sync client). Wait and try again,
  or use a local, unsynced folder.
- `cleanup pending: the earlier files of job <id> are still being removed; try again later`: a job of an earlier session
  is still being cleaned up after a restart.
- `output folder is gone or changed`: the output folder was moved, replaced or unmounted while a job used it. Pick it again.
- A path in the "refused" list (or a notice) comes with one of these reasons: `not an absolute path`, `path too long`,
  `NUL in path`, `no such file or folder`, `the path is a symlink`, `/ cannot be chosen`, `not a regular file or folder`
  (a source), `not a folder` (the output), `the data folder cannot be chosen`, `outside SVF_MAKER_ROOTS`, `the output
  folder must not overlap an input`, `overlaps another input`. Pick the real path instead of a link, and keep the
  output folder apart from the sources.
- `confirm the DOS Johab layout`: choose the layout of a DOS raw font in its row (section 3.3).

## 12. Recovery, desktop integration and uninstall

**The AppImage does not start.**

- *No FUSE.* The AppImage's own runtime carries its FUSE code and needs only `fusermount` or `fusermount3` (package
  `fuse3`; Ubuntu 24.04 has it). If neither exists, or mounting is not allowed (a container, a locked-down system), install
  `fuse3`, or run the image without mounting it:

      ./svf-maker-0.1.0.AppImage --appimage-extract       # writes ./squashfs-root/
      ./squashfs-root/AppRun

  `squashfs-root/AppRun` is the same launcher; you can keep that folder instead of the AppImage.
- *No display, or no X authority.* The message `Missing X server or $DISPLAY` (or Electron failing to open the display)
  means there is no graphical session in this shell. Run the app from a desktop session; over `ssh` use X forwarding, or
  check that `$DISPLAY` is set and that `$XAUTHORITY` points at your session's authority file (`xauth list`). On a
  machine with no screen, `xvfb-run -a ./svf-maker-0.1.0.AppImage` runs it on a virtual display, but then you cannot use it.
- */tmp must allow execution.* The AppImage mounts itself under `/tmp/.mount_*` and runs its programs from there. When
  `/tmp` is mounted `noexec`, the start fails (typically with a "permission denied" message; not reproduced here). Remount `/tmp`
  without `noexec`, or use `--appimage-extract` and run `squashfs-root/AppRun` from a place that allows execution.
- *No sandbox.* When unprivileged user namespaces are not available, the launcher notices (it probes `unshare -Ur true`)
  and adds `--no-sandbox` by itself; you need not do anything. Help > About then says "renderer sandbox: off".
- *Something else.* Start it from a terminal with `SVF_MAKER_SHELL_LOG=stderr ./svf-maker-0.1.0.AppImage` and read the
  messages, and `~/.config/svf-maker/logs/shell.log`.

**Desktop integration.** The AppImage puts nothing into your menus or icon folders, and it is not installed anywhere. To
get a launcher, write a file `~/.local/share/applications/svf-maker.desktop` yourself:

    [Desktop Entry]
    Type=Application
    Name=SVF maker
    Exec=/home/you/Apps/svf-maker-0.1.0.AppImage %U
    Terminal=false
    Categories=Utility;

(use the real absolute path of the AppImage; add `Icon=` with an absolute path to `desktop/build/icon.png` of the
checkout if you want one). Or use an AppImage manager such as AppImageLauncher, which reads the entry inside the image.
Inside the image, `Exec=AppRun %U` is the entry and `AppRun` adds `--no-sandbox` itself when needed.

**Windows.** If the app does not start, read `%APPDATA%\svf-maker\logs\shell.log`; to see the messages as they come,
start it from a PowerShell window with `$env:SVF_MAKER_SHELL_LOG='stderr'` set first. SmartScreen's "Windows protected
your PC" is the unsigned package (Quick start). Uninstall: Settings > Apps > SVF maker (or "Add or remove programs"),
or delete the portable file; then delete `%APPDATA%\svf-maker\` to remove the data, the log and Chromium's profile. The
faces in your output folders stay.

**Uninstall.** Delete the AppImage file. The app's data is under `~/.config/svf-maker/`: the jobs and work files
(`maker/`, `maker-dev/`), `shell-state.json`, `logs/shell.log`, and Chromium's own profile data (cache, local storage and
so on) that the Electron shell keeps in the same folder. Delete `~/.config/svf-maker/` as well to remove every trace.
The faces already written in your output folders are yours and stay.

## 13. Limits and what has not been verified

- Verified on 2026-11-22: the AppImage built from commit 3d40de8 was started on a clean host (Ubuntu 24.04.5, no
  `libfuse2`) under Xvfb; the window rendered and a conversion in local mode ran through the packaged sidecar. Still
  not verified: a real desktop with a window manager and a GPU, and Windows and macOS.
- Windows x64 (t_9b8f56f0): built and tested on GitHub Actions `windows-latest` (Windows Server, no user at a desktop).
  Verified there: the maker and tools test suites on Windows (1,277 and 980 tests, 0 failed; the skips are listed in maker-desktop.md), the frozen sidecar's test, the desktop unit
  tests, the desktop end-to-end test against the development server and against the packaged sidecar (stubbed dialogs),
  a silent per-user install and uninstall, and a start of the unpacked, the installed and the portable app that loads
  the page through the packaged sidecar and stops it cleanly. **Not verified**: a real Windows 10/11 desktop (a person
  using the window, native dialogs, the GPU path, high-DPI scaling), the SmartScreen and browser download warnings (the
  files are not signed), antivirus interplay, folders synced by OneDrive or on network shares, FAT/exFAT output drives,
  long paths (over 260 characters), and Windows on Arm. The server's checks hold on Windows in their Windows form
  (maker-desktop.md, "What differs on Windows"); a tool stop there is immediate (no 5 s grace). A face made on Windows
  can differ from the same face made on Linux in single glyphs (measured: U+2116 of GowunBatang-Bold at 17 px 2 bpp), so
  such a face is written as a new one there instead of being recognised as the shipped face.
- macOS: not built, not run. The plan (signing, notarisation) is written in [maker-desktop.md](maker-desktop.md).
- TTF / BDF export: each file is read back (fontTools for a TTF) and must hold exactly the face's characters; the
  round trip (baking the TTF back with `mkfont.py` and comparing, recipes.md) is not part of a run, it takes minutes for a
  jamo set. Whether a program draws a TTF's 2 bpp strike as levels is up to its renderer (Windows and macOS not tested).
- Known ROM sets: checked against the real files only where `SVF_MAKER_REAL_86BOX` / `SVF_MAKER_REAL_MAME` names your own
  copy (every face the size recipes.md records); the tests use synthetic ROMs drawn from an OFL face.
- The `mask fit` route has never run a job on the author's host (the libraries are not installed there); the identity
  check has only been tested with a stub; `vector fit` takes minutes per font.
- Not verified, pending manual checks on a real desktop: native dialogs with a display, the file manager integration,
  starting through a real FUSE mount with a window manager, the GPU path and a sandboxed renderer. What has been run is the
  Xvfb start above; the automated tests stub the dialogs and run with the GPU off.
- Real Mac, HWP and Johab files are tested only where an environment variable points at your own copy; the repository's
  tests use synthetic inputs.
- The AppImage is not bit-reproducible, and there is no automatic update; a new version is a new file.
