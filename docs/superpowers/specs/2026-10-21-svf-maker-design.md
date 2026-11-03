# SVF maker v1: design

A web page, served from this host, that turns uploaded fonts into SVF faces by running the repository's own tools, and
hands back a zip that unpacks straight into `svf/`. No AI is involved: the page is a front end to `tools/mkfont.py`,
`tools/jamoset.py`, `tools/jamovec.py` and `tools/svfline.py`. The builder is an external coding agent (opencode) working
task by task from a plan; Claude designs, plans and reviews. Every choice this document makes on its own is marked
"(design call)", a ruling by the controller after the builder check "(controller call)"; everything else is the
owner's decision (the section "The owner's decisions") or a fact from `docs/tools.md`, `spec/SVF.md` or the code,
re-checked on 2026-10-21.

## Intent and why

The faces in `svf/` were made one by one at the command line, with Claude choosing options and reading Korean tool
output. The owner wants to produce faces from a folder of fonts without Claude ("클로드 없이 생성"): upload, look at
the fonts, set the output, wait, download, unpack. `docs/tools.md` ("Gaps for the SVF maker") lists what no tool does
today: format detection, metadata and coverage reporting, a bake API with a return value, and a few bugs; the maker
fills those gaps in one place and leaves the tools as they are, apart from one fix in `mkfont.py`.

## Goals, non-goals and anti-goals

Goals:
- Upload files, a folder or an archive; see every font found, with format, family/style, built-in sizes, coverage,
  a source preview and whether a licence text was found.
- Convert a batch with one set of settings and per-font overrides into SVFN v3 faces (precomposed, jamo set or both),
  as background jobs with visible progress that survive a page reload. `run` works with the defaults alone.
- Download a zip laid out as `svf/...` whose faces are valid v3 (every writer goes through `jamoset.pack_svfn`), each with its licence text, named by a literal rule
  the owner edits on the page, with the `FACES.TSV`, `LICENCES.tsv` and `FAMILIES.tsv` lines and a build log of the
  exact commands.
- Leave a clean place to plug in a later precomposed-to-jamo segmentation route (card t_4bac9a91).

Non-goals (v1): editing glyphs; dy editing (`svfdy.py`); per-game maps and `pairing2svf.py`; 8 bpp faces; the Mac
`fbit` source; the jamo-extra build method (12x12 classes with usage weights, no repository CLI; a later item); any
user but the owner; HTTPS, accounts, sessions.

Anti-goals (never, in any version):
- Anything that needs Claude, a local LLM or a network AI.
- Writing into the repository checkout. The maker reads `svf/` (names, licence texts) and writes only under its own
  job directory and into the zip. The owner unpacks the zip into the checkout by hand.
- Silently producing an SVFN v1 face, or a face without a licence text, or a face whose name collides with a
  different existing file.

## Constraints

- Host: this machine, Python 3.12.3 at `/usr/bin/python3`, Pillow 10.2.0 and fontTools 4.66.1 installed; freetype-py,
  uharfbuzz, skia-pathops, flask, fastapi, aiohttp and python-multipart are **not** installed. (design call) The maker
  uses the standard library only, like the existing preview server; no package is installed for it.
- `mkfont.py` writes v3 only (`jamoset.pack_svfn`) and refuses a run without `--unicode` or `--chars-from`; `svfline.py`,
  the C renderer and `web/mkindex.py` read v3 only, `svf2to3.py` is the one v2 reader. The maker always passes
  `--unicode`. (Written for v2; moved onto SVF v3 by card t_a0a737c9.)
- With `--unicode`, `mkfont.py` forces variable width (`--fixed`, `--center`, `--variable` are ignored). There is no
  fixed-width path for outline fonts. The maker does not offer a fixed-width option on the precomposed route; the
  page says "variable width (v3)" next to the kind. A jamo set's syllables are one cell each by construction, so jamo
  sets are fixed-width in effect; nothing more is promised.
- `mkfont.cmap_has` raises `fontTools.ttLib.TTLibError` on a BDF, PCF or FNT when fontTools is installed (verified in
  `tools/mkfont.py:522-531`: only `ImportError` is caught). Fixing it is task one of this project: `cmap_has` returns
  `None` on `TTLibError` (and caches that), so the picture test decides presence, as it does without fontTools.
- Bitmap fonts (BDF, PCF, Windows FNT/FON) open in Pillow only at their built-in pixel size (`OSError: invalid pixel
  size` otherwise; verified with `/usr/share/fonts/X11/misc/18x18ko.pcf.gz`). The sizes offered for them are their
  strikes only. At 2 bpp such a face holds only levels 0 and 3, so 2 bpp is not offered for bitmap sources.
- `jamoset.py --from-ttf` at 1 bpp defaults to `--binarize mono`, which needs freetype-py and uharfbuzz. (design call)
  The maker does not install them; at 1 bpp it passes `--binarize threshold` always, as the recipes in `docs/tools.md`
  do, and the mask font is then skipped (free pieces), which `jamoset.py` reports itself. With `--bpp 2` `jamoset.py`
  refuses `--binarize` (verified: `tools/jamoset.py:1569-1573`, "--bpp 2 does not take ... --binarize"), so the 2 bpp
  command carries no `--binarize`; it needs fontTools only. The pixel fit is experimental either way.
- `mkfont.py` prints its summary in Korean, `jamoset.py` in English prose. The maker never parses stdout: it reads the
  produced file with `jamoset.parse_svfn` and `jamoset.unpack`, computes quality itself (below), and keeps stdout and
  stderr verbatim in the build log.
- Run time on this host: a 2 bpp fitted jamo set about 84 s per font and size, a 1 bpp threshold fit about 13 s, a
  precomposed bake a few seconds, a jamo set from a DOS raw font under a second, a `jamovec master` once per font and
  layout.
- `tools/test_tools_doc.py` demands a `docs/tools.md` section for every `tools/*.py`, `web/*.py` and `web/*.sh` file.
  (design call) The maker lives in `maker/` at the repository root, outside that census, and is documented in
  `maker/README.md` and this file; `docs/tools.md` gets one line under "Gaps" saying the maker exists.

## The owner's decisions

These are the owner's (2026-10-21), restated; the maker does not revisit them.

1. Purpose: produce SVF faces from uploaded fonts without Claude, by combining the existing tools. No AI in v1.
2. Users: the owner only ("본인만 쓸거야"). It runs server-side on this host as a systemd user service like
   `svf-preview.service`, bound to the tailnet address 100.78.108.85, calling the Python tools directly. Hardening is
   light but real: an upload size cap, a per-job time limit, a temp dir per job, archive path-traversal and
   decompression-bomb guards.
3. Input is folder- or package-level ("폴더 단위 처리나 패키지 처리"): several files, a whole folder, or an archive
   (zip, tar, tar.gz, tar.xz). The server finds every font inside. Formats: TTF/OTF/TTC, BDF, PCF (`.pcf`, `.pcf.gz`),
   Windows FNT/FON, HBF, DOS Johab raw `.fnt` (the layouts `jamoset.py` reads), and existing SVF.
4. Per font, after upload: detected format; family/style; built-in pixel sizes (bitmap fonts); coverage of ASCII, the
   2,350 KS X 1001 syllables, all 11,172, and jamo availability; the licence text found next to it, or a warning.
5. Preview ("미리보기 샘플: 가"): a sample image of the source (a Hangul + Latin line) per font, and after conversion a
   sample rendered from the produced SVF with `tools/svfline.py` (the reference) or the WASM renderer.
6. Output ("SVF 아래에 바로 넣게", "SVF zip은 화면에서 설정하게"): a zip laid out as `svf/...`. On screen: destination
   (`svf/dos`, `svf/jamo-extra`, `svf/games/<game>`, or new), kind (precomposed, jamo set, both), jamo layout, pixel
   sizes, bpp (1 and/or 2), character range (11,172, 2,350, or a list file), file names (auto by the repository rule,
   editable: after the source font plus size, never the game; identical bytes share one file), extras (licence `.TXT`,
   `FACES.TSV` lines, a build log with the exact commands). Settings apply to the batch with per-font overrides. The
   zip's contents must pass `facecheck.py`.
7. Jamo sets ("소스가 자모 형태를 추출할 수 있어야 자모 생성이 가능하다"): automatic only from natively-jamo sources:
   DOS Johab `.fnt` layouts, existing jamo-set SVFs, and composite-glyph TTFs whose syllables are built from jamo
   components (`jamovec.py --components`, the `svf/jamo-extra` route). From precomposed-only sources a pixel fit
   (`jamoset --from-ttf` / `--from-svf`) may be offered only as "experimental", showing its IoU; the owner considers
   pixel fits visually unreliable. Real segmentation is card t_4bac9a91 (local Qwen via LiteLLM), out of scope here
   except for a clean plug-in point.
8. Conversions run as background jobs with visible progress; the page survives a reload mid-job.
9. opencode implements task by task from Claude's plan; Claude designs, plans and reviews.

10. **Tuning options** (the owner, 2026-10-21: "추천대로 진행", accepting the recommendation):
    - **Presets.** A small set of named presets distilled from the recipes the shipped faces were made with
      (`tools/bake-dos-fonts.sh`, `scumm-fonts/bake-paperlogy.sh`, `tools/build/iolo_jset.py`, the `svf/dos/*.TXT`
      notes). Each preset is a fixed option list per route in one file, `maker/presets.py` (a Python table; design
      call: it can carry the comment naming the recipe), quoted by name and in full in the build log. Each is named
      after the faces it reproduces; the table is in "Settings and the routes".
    - **Advanced panel.** A collapsed panel with the main options, for the whole batch and overridable per font:
      `mkfont.py` `--cell`, `--ascent`, `--mono-hint`, `--clip-cell`, `--space-advance`; `jamoset.py` `--embolden`,
      `--symbols`, `--eng`. Only the options `docs/tools.md` shows for the chosen route and mode are shown; its Modes
      column is the source of truth. The server validates every value.
    - **Out of scope for v1.** The jamo-extra method (12x12 classes with usage weights) has no repository CLI; it is a
      later item (non-goals).
    - **Acceptance check.** For at least one preset, the end-to-end test rebuilds a shipped face from its source in
      the repository with that preset and gets byte-identical output, or the closest the tools allow with the reason
      stated.

## Architecture

### Layout (design call)

    maker/server.py      the HTTP server and API (stdlib http.server, ThreadingHTTPServer), the entry point
    maker/jobs.py        job store, queue and the worker thread
    maker/detect.py      format detection, metadata, coverage, licence search (pure functions over a file path)
    maker/routes.py      source kind + requested kind -> the tool command lines (argument lists) and output readers
    maker/archive.py     upload unpacking with the guards
    maker/naming.py      the file-name suggestion, collision and identical-bytes checks against svf/
    maker/zipout.py      the output zip, the .lines files and the build log
    maker/quality.py     quality numbers from the produced face against its precomposed reference
    maker/preview.py     sample PNGs: source (Pillow) and result (svfline.py)
    maker/static/        index.html, maker.js (one ES module, no framework), style.css
    maker/test/          fixtures/, test_maker.py (unit tests and the end-to-end test), smoke.mjs (the UI smoke test)
    maker/svf-maker.service, maker/README.md

`maker/` holds flat modules (no package, no relative imports). (controller call) Because the service runs
`python3 -P`, which drops the script directory from `sys.path` (not `-I`: that also disables the user site, where
fontTools 4.66.1 is installed on this host, so detection and every tool run would lose fontTools; found at
pre-flight 2026-10-21), `server.py` and `test_maker.py` insert both `maker/`
and `<repo>/tools/` on `sys.path` explicitly, first thing, from their own `__file__`; then `import detect`,
`import jamoset`, `import svfline`, `import mkfont` (for `NAMED_RANGES`, `cmap_has`, `collect_chars_from_files`),
`import bdfface` (`read_bdf`, `read_hbf`), `import jamofit` work. Conversions never import a tool: they run it (below).

### Process model

One process, started by systemd: the HTTP server on its threads plus **one worker thread** that runs jobs one at a
time, FIFO (design call: the tools are CPU-bound and the host is shared with other services). The repository root is
`SVF_MAKER_REPO` (default `<workdir>/svf-fonts`, read only); the data root is `SVF_MAKER_DATA` (default
`~/.local/share/svf-maker`); the bind address and port are `SVF_MAKER_BIND` (default `100.78.108.85:8766`; the preview
server has 8765). Tests start the server on `127.0.0.1:0` with a temp data root and `SVF_MAKER_REPO` set to the
checkout they run in, found from the test file's own path (controller call: that may be a worktree, never a fixed
path).

### Jobs and storage

A job is a directory `DATA/jobs/<id>/` (`id` = `secrets.token_hex(6)`, 12 hex chars) holding:

    job.json        state, created time, settings, the font list with detection results, steps with progress, errors
    upload/         the uploaded files, under their relative paths (folder uploads) or as unpacked (archives)
    work/           tool outputs, reports, previews (one subfolder per step)
    out/<id>.zip    the result
    log.md          the build log, appended as steps run (also inside the zip)

`job.json` is the only state; it is rewritten atomically (write temp, rename, one lock per job) at every change, so a
page reload or a service restart reads it back. State: `uploading` -> `detected` -> `queued` -> `running` -> `done` |
`failed`. Lifecycle (controller call): the queue order is the `created` time stored in `job.json`; at start-up every
`queued` job is re-queued in that order and every `running` job is marked `failed: interrupted` (no resume; the owner
re-runs); `cancel` works on a `queued` job (state `failed: cancelled`) as on a running one; retention keeps at most
20 jobs and 7 days, deleting the oldest `done`/`failed`/`detected` jobs first and never a `queued` or `running` one.

### Endpoints

All responses are JSON except the page and the downloads. The page is static from `maker/static/`.

| Method and path | What it does |
|---|---|
| `POST /api/jobs` | new job; returns `{id}` |
| `PUT /api/jobs/<id>/files?path=<rel>` | one uploaded file as the raw request body (no multipart; design call); `path` is percent-encoded UTF-8; the request needs `Content-Length` (411 without it; 413 when it is over the limit, before any byte is read); stored at `upload/<rel>` after the path checks; an archive (by magic) is unpacked under `upload/<rel>.d/` with the guards |
| `POST /api/jobs/<id>/detect` | scans `upload/`, fills the font list (detection, metadata, coverage, licence, source preview) and the default settings; state `detected` |
| `GET /api/jobs/<id>` | the whole `job.json` (the page polls this every 2 s while `queued` or `running`) |
| `PUT /api/jobs/<id>/settings` | the batch settings and per-font overrides (validated, see below); allowed in `detected` only |
| `POST /api/jobs/<id>/run` | computes the step list, state `queued`; refused unless every selected font has a licence and every name is valid; queued behind a running job, the page shows the position |
| `POST /api/jobs/<id>/cancel` | a queued job is failed as cancelled; a running one gets `terminate`, then `kill` after 5 s |
| `GET /api/jobs/<id>/preview/<font>/<kind>.png` | a source or result sample |
| `GET /api/jobs/<id>/zip` | the result zip (`done` only), `Content-Disposition: attachment; filename="svf-maker-<id>.zip"` |
| `GET /api/jobs` | the job list (id, state, created, font count) |
| `DELETE /api/jobs/<id>` | removes the directory (not while queued or running) |
| `GET /api/repo` | existing destinations under `svf/` (folders), existing file names per folder, and the licence `.TXT` files with their first line (for the "use an existing licence" pick) |

The page opens on `?job=<id>` and restores everything from `GET /api/jobs/<id>`; nothing but the current job id is
kept in the browser (design call: no localStorage, the server holds the truth).

### Invoking the tools

Every conversion is `subprocess.run([sys.executable, "-P", "<repo>/tools/<tool>.py", ...], cwd=work/<step>/,
env=minimal, capture_output=True, timeout=step_timeout)`: an argument list, never a shell, absolute paths for every
file, `-P` so nothing in the job directory (the cwd) or beside the tool is importable through the script path, while
the user site stays (fontTools lives there; `-I` would remove it, and the minimal env carries no `PYTHON*` variable
that `-P` would leave in force). `env` is `PATH`, `HOME`, `LANG=C.UTF-8` only (design call:
no `JAMOSET_PYLIB`, no `JAMOSET_MASK_FONT`, so behaviour does not depend on the owner's shell). The command line
(`shlex.join`), exit code, elapsed seconds, stdout and stderr go to `log.md` under a heading per step. A non-zero exit
or a timeout fails the step, not the job: the batch continues and the job ends `done` with failed steps listed.

## Detection rules per format

Detection reads magic bytes, then size, then the extension (design call: the extension is a hint for the user-visible
label only; it never decides). Every regular file under `upload/` is tried; a file matching nothing is listed under
"unknown" with its first bytes, and is not an error. `.gz` is undone first (one level) and the inner bytes decide.
(controller call) A `.txt` file is never a font: it is listed as a "list file" (a character list, see "Settings") or,
when the licence search claims it, as a licence text.

| Format | Rule | Metadata | Sizes | Coverage | Jamo availability |
|---|---|---|---|---|---|
| TTF/OTF | bytes 0-3 `00 01 00 00`, `true`, `OTTO` | fontTools name IDs 16/17, else 1/2 | any; default 16 | cmap (`getBestCmap`) | composite test (below) |
| TTC | `ttcf` | per face (`fontNumber`); each face is a list entry | as TTF | as TTF, per face | as TTF |
| BDF | starts `STARTFONT` | `FAMILY_NAME`, `WEIGHT_NAME`; registry `CHARSET_REGISTRY`/`ENCODING` properties | `PIXEL_SIZE`, else the box height | `bdfface.read_bdf` encodings: ISO10646-1 direct; KSC5601 via `cp949` decode of the 2-byte code; johab (registry containing `johab`, or hanterm) = native jamo | native when johab |
| PCF | bytes 0-3 `01 66 63 70` (`\x01fcp`) | Pillow `getname()` | probe: `ImageFont.truetype(path, s)` for s in 4..96, keep those that open | picture test at the strike (mkfont's `absent` rule, `tools/mkfont.py:1034`: a glyph whose image equals `.notdef`'s) over ASCII, the 2,350, the 11,172 and U+3131..3163 | compat only |
| Windows FNT | u16 at 0 is `0x0200` or `0x0300` and bytes 6-65 printable | Pillow `getname()` | probe as PCF | picture test | compat only |
| Windows FON | `MZ` and Pillow opens it (`index` 0.. until it fails) | per face | probe | picture test | compat only |
| HBF | starts `HBF_START_FONT` | `HBF_FAMILY`/`FONT` line | from `HBF_BITMAP_BOUNDING_BOX` | `bdfface.read_hbf` ranges | none |
| DOS Johab raw (probable) | exact byte size in `jamoset.py`'s tables and `check_blank_slots` passes: 11520, 11522, 25920, 72000, 103680, 15584 -> `844`; 243900 -> `844-hbios24`; 12800 -> `1044-san`; 6144 -> `621`; 11550 -> `kyra-lok`; 15360, 34560 -> `dkb-printer-7x2x2`; 176000, 253440 -> `dkb-printer-12x4x4` | the file stem | the layout's px | all 11,172 by construction; ASCII none | native, once confirmed (below) |
| SVF | `SVFN`, version 2 (version 1 is listed as "v1: convert from the original font", not convertible) | the stem; family and style for the lines are the stem | the cell | `parse_svfn` code points; a jamo set covers all 11,172 | native when flags bit 1 and the JSET unpacks |
| Archive | zip `PK\x03\x04`, tar (ustar at 257), gzip, xz | unpacked, not listed | | | |

(controller call) A DOS raw match rests on size alone, so it is shown as "probable DOS Johab (<layout>)" with a
confirm box in the list, unselected until the owner ticks it; a size with several candidates (11520 is `844` or
`844-ihnm`; 15360 is `dkb-printer-7x2x2` or an HBIOS 12x24 English font) shows a picker of the candidates instead of
one layout. A file of exactly 2048 or 4096 bytes is offered as a Latin companion (`--eng`) only when a DOS Johab font
sits in the same folder; otherwise it is "unknown".

Composite test (design call, for TTF/OTF/TTC with a `glyf` table; a CFF font is never composite): count the drawn
syllables whose glyph is a composite of 2 or 3 components (`jamovec.composite_parts` returns parts); the font is
"native jamo (composite)" when that is at least 95% of the drawn syllables, else "precomposed". Jamo availability is
shown as one of `native (<layout or composite>)`, `compat N/51` (how many of U+3131..3163 are drawn), `none`.

Licence search (design call): for each font, files in its own folder and every parent folder up to the upload root
whose name matches, case-insensitively, `LICENSE*`, `LICENCE*`, `OFL*`, `COPYING*`, or `*.txt` containing the word
`license`/`licence` within the first 4 KB; the nearest folder wins, several in one folder are all listed and the user
picks. A font with none shows a warning and two remedies: pick an existing `svf/**/*.TXT` from `GET /api/repo`, or paste
a text. The same picker and paste serve every source, an existing SVF included (controller call). A font with no
licence cannot be selected (anti-goal 3).

Source preview (design call): a 1-line PNG, `다람쥐 헌 쳇바퀴에 타고파 ABC xyz 0123`, drawn with Pillow at the first
requested size (bitmap: the strike) for TTF/OTF/BDF/PCF/FNT/FON; for a confirmed DOS raw font and an SVF (v3, or v2 converted by `svf2to3.py`),
`svfline.layout` on the SVF (the raw font is baked once, at its native size, `--layout <confirmed>`, into
`work/preview/`, the same command the conversion runs). The result preview is the same line through `svfline` on
each produced face. Geometry (controller call): `width, ascent, descent = svfline.measure(chain, text)`, then
`svfline.layout(chain, text, x=1, y_baseline=ascent + 1, w=width + 2, h=ascent + descent + 2)`, the GRAY8 bytes to a
PNG with Pillow (`Image.frombytes("L", (w, h), buf)`), as `svfline.main` draws `line W H X Y`. The chain is
`[face]`, or `[face, latin]` for a face without ASCII (a jamo set from a DOS raw source, a jamo-only SVF): `latin` is
the batch's precomposed face of the same font at the same size when one exists, else the repository's
`svf/dos/NEODG16.SVF` (design call; `svfline` takes the first face that has the code point). (design call) The WASM
renderer is not used: the server has Python and the reference, and one renderer in the pipeline is enough.

## Settings and the routes

Batch settings, each overridable per font (the override has the same keys): `selected`, `dest` (`dos`, `jamo-extra`,
`games/<game>`, or `new/<name>`; a folder name is `[a-z0-9-]+`), `kinds` (subset of `precomposed`, `jamo`),
`layout` (for jamo), `sizes` (list of ints 6..96), `bpp` (subset of `1`, `2`), `range` (`11172`, `2350`, or a list
file's path in the upload), `experimental` (per font only), `names` (per font, size, bpp, kind), `latin_companion` (a
font or `--eng` file in the batch; it is what `--eng` and `bdfface --ascii` receive), `preset` (a name from the table
below; default `plain`), and `options` (the advanced panel: `{"mkfont": {"cell": int|null, "ascent": int|null,
"mono_hint": bool, "clip_cell": bool, "space_advance": int|null}, "jamoset": {"embolden": bool, "symbols": bool}}`;
null or false means "not passed"). A per-font override carries the same keys; an option set there wins over the
batch, and an option set anywhere wins over the preset's value for the same flag. The final argument list, the preset
name and the preset's full option list go to the build log.

Presets (`maker/presets.py`; each is `{route kind: [argv fragments]}`, verified against the scripts and `--help`):

| Preset | Options | Reproduces |
|---|---|---|
| `plain` | the route table's commands as they stand | nothing in particular (the tools' defaults) |
| `dos-l-1bpp` | precomposed: `--cell 16 --bpp 1 --unicode ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D` (the range replaces the `range` setting; `--size` from `sizes`) | `svf/dos/NEODG16.SVF` (`bake-dos-fonts.sh` L preset; today's rebuild from `ttf/neodgm/neodgm.ttf` has one glyph fewer than the shipped file, 127,812 against 127,856 bytes: the shipped face gained a glyph after the script, so "closest the tools allow") |
| `dos-u-2bpp` | precomposed: `--cell 16 --clip-cell --ascent A --bpp 2 --unicode ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D`, A = `size - 2` unless the panel sets `ascent` | `svf/dos/GBATB17.SVF` (size 17, ascent 15: **byte-identical**, verified 2026-10-21 by running the script) and `svf/dos/NGOTB16.SVF` (size 16, ascent 14: one glyph fewer, as NEODG16) |
| `latin-18cell-2bpp` | precomposed: `--cell 18 --width 18 --bpp 2 --clip-cell --ascent 14 --unicode ascii,2026,2122,3131-318e --only-listed --space-advance 6 --punct-extra 1` | `svf/dos/PAPLG16.SVF` (`bake-paperlogy.sh`; its source TTF is outside the repository) |
| `jamo-844` | DOS raw jamo: `--layout 844 --check`, `--eng` from `latin_companion` | `svf/iolo/*8J.SVF` (`iolo_jset.py`; sources external) |
| `jamo-844-symbols` | DOS raw jamo: `--layout 844 --symbols --check` | `svf/dos/SANGAM16.SVF` (**byte-identical**, `SAN10.TXT`); `IYAGI16.SVF` needs ascent 15, which the panel's options cannot set (only `jamoset --ascent`, outside the panel, reaches it) |
| `jamo-844-hbios24` | DOS raw jamo: `--layout 844-hbios24 --symbols --check` | `svf/dos/TBMY24.SVF` (closest: 1 byte differs at offset 3575) and `TBGOB24.SVF` (with the panel's `--embolden`; closest: 1 byte at offset 3575) (`TAEBAEK.TXT`) |
| `jamo-621` | DOS raw jamo: `--layout 621 --check`, `--eng` from `latin_companion` | `svf/iolo/*6J.SVF` |

A preset that names a layout sets the `layout` field and is offered only for sources that can take it; a preset
whose route the font lacks is refused by validation with the reason.

Advanced panel options (names and defaults from `--help`; the Modes column of `docs/tools.md` decides visibility, and
the server refuses what it would not show):

| Option | Tool | Shown when | Value |
|---|---|---|---|
| `--cell N` | mkfont | any precomposed mkfont route | int 4..255 (cell height; default = size) |
| `--ascent N` | mkfont | any precomposed mkfont route | int 0..cell (default chosen by the tool) |
| `--mono-hint` | mkfont | bpp 1 only | flag |
| `--clip-cell` | mkfont | any precomposed mkfont route | flag |
| `--space-advance N` | mkfont | any precomposed mkfont route (v3 is variable width) | int 0..255 |
| `--embolden` | jamoset | `source` modes (DOS raw, hanterm BDF) only; ignored by the fit modes and refused with `--bpp 2`, so hidden there | flag |
| `--symbols` | jamoset, jamovec render | `source` modes, `--from-ttf --bpp 2`, and `jamovec render`; ignored by 1 bpp `--from-ttf`/`--from-svf`, so hidden there | flag |
| `--eng FILE` | jamoset | `source`, `--from-ttf` 1 bpp, `--from-svf`; refused with `--bpp 2`; the value is `latin_companion` (a 2048/4096-byte file) | file in the batch |

Defaults after `detect` (controller call): every font with a licence starts `selected`; one without, or a probable
DOS raw font, starts unselected; `kinds` is `["precomposed"]`, and `["jamo"]` is preselected only for native-jamo
sources (a DOS raw font or jamo-set SVF, which have no precomposed route, gets `["jamo"]` alone; a composite TTF gets
both); `experimental` is off; `dest` is `jamo-extra` for jamo kinds and `dos` for precomposed; `layout` is the
detected one for DOS raw, `adaptive` for composite TTF, `844` for experimental fits; `sizes` is `[16]` for outline
fonts and the strikes for bitmap ones; `bpp` is `[1, 2]` for outline fonts, `[1]` otherwise; `range` is `2350`.
Validation refuses a setting the font's routes cannot honour and says why (for example `bpp 2` on a bitmap source, a
size that is not a strike, `jamo` on a precomposed font without `experimental`).

A list file (controller call) is UTF-8 text whose characters are taken in order, newlines and spaces ignored. Verified:
`mkfont.parse_ranges` (`tools/mkfont.py:413`) sends `file:PATH` to `collect_chars_from_files`, which for a plain text
file takes every character and drops those below U+0020 (`_drop_layout_controls`); `bdfface.py --chars-from` calls the
same function (`tools/bdfface.py:315`). One file serves both; a space in it is U+0020, which every route keeps anyway.
The maker writes the `11172`/`2350` ranges as such a file too, so `bdfface.py` takes them.

`maker/routes.py` is the plug-in point: `routes(font) -> list[Route]`, a `Route` being `kind`, `label`, `native`
(bool), `layouts` (the valid choices), `bpps`, `sizes` (None = any), `commands(font, size, bpp, layout, range,
paths) -> list[list[str]]` and `reference` (the precomposed face the quality numbers compare against, or None). The
segmentation project adds one `Route` (`kind="jamo"`, `label="segmented"`) and touches nothing else.

| Source | Kind | Commands (exact flags; every path absolute) |
|---|---|---|
| TTF/OTF/TTC, BDF (ISO10646), PCF, FNT, FON | precomposed | `mkfont.py IN OUT --size S --bpp B --unicode ascii,hangul` (11,172) or `--unicode ascii,ksx1001-hangul` (2,350) or `--unicode ascii,file:LIST`; LIST is the maker's copy under `work/`, never the upload's own name (`--unicode` is comma-split, so a name with a comma or a space would inject a range); TTC/FON faces other than index 0 are not supported by `mkfont.py` (it opens index 0) and are listed as "face index N: not convertible in v1" |
| TTF/OTF composite | jamo (native) | once per font and layout (controller call; the layout belongs to `master`, `render` has none, verified with `--help`): `jamovec.py master IN -o M.json --components` for `844`, `jamovec.py master IN -o M.json --components --adaptive` for `adaptive`; then per size and bpp `jamovec.py render M.json --size S --bpp B --binarize threshold --check -o OUT` |
| TTF/OTF precomposed | jamo (experimental) | 1 bpp: `jamoset.py --layout L --from-ttf IN --size S --binarize threshold --check -o OUT [--eng ENG]`; 2 bpp: `jamoset.py --layout L --from-ttf IN --size S --bpp 2 --check -o OUT` (no `--binarize`: refused at 2 bpp); layouts `844`, `adaptive` |
| DOS Johab raw (confirmed) | jamo (native) | `jamoset.py IN --layout L --check -o OUT`, plus `--eng ENG` when a companion is chosen and `--face N` (0 or 1, both offered as two list entries) for the Dokkaebi printer layouts; 1 bpp only (the source is 1 bpp) |
| BDF johab/hanterm | jamo (native) | `jamoset.py IN --layout hanterm-johab --check -o OUT [--eng ENG]` |
| BDF KSC5601 | precomposed | `bdfface.py --hangul IN --ascii LATIN --cell WxH --chars-from LIST -o OUT` where LATIN is the chosen Latin companion (an ISO10646/ISO8859 BDF or an HBF in the batch; without one the font is "needs a Latin companion"), WxH the BDF's box, LIST the range file |
| SVF v3 precomposed | precomposed | copy (re-homed: name, licence, lines); `range`, `sizes` and `bpp` do not apply; a v2 face is converted instead: `svf2to3.py IN OUT --check` |
| SVF v3 precomposed 1 bpp | jamo (experimental) | `jamoset.py --layout L --from-svf IN --check -o OUT [--eng ENG]` (a v2 IN is first converted to `source-v3.svf` in the step's work directory with `svf2to3.py --check`) |
| SVF v3 jamo set | jamo (native) | copy (a v2 face: `svf2to3.py IN OUT --check`) |
| HBF | - | listed; a Latin companion only |

(design call) Not offered, and said so on the page: 2 bpp from any bitmap source or SVF (no tool makes coverage from a
stencil); jamo from a 2 bpp precomposed SVF (`--from-svf` refuses it); every tool option not in the presets or the
panel (`--width`, `--punct-extra`, `--only-listed`, `--limit`, `--require`, `--fit-cell`, `--base`, `--advance`,
`--ascent` of jamoset, `--cell`/`--baseline` of the fit modes, ...). The range setting applies to precomposed routes
only; a jamo set always holds all 11,172.

### Quality numbers (controller call)

`maker/quality.py` computes `quality_all` and `quality_ks2350` as a library call, never from stdout or a report file:
compose every syllable of the produced jamo set (`jamoset.parse_svfn`, `unpack`, `compose`) and compare with the
precomposed reference rendered at the same cell: for a TTF/OTF source the reference is the route's own raster of each
drawn syllable (`jamoset.ttf_targets` for 1 bpp; for 2 bpp the `jamoaa` coverage raster quantised as `mkfont.py`
does); for `--from-svf` the input face's glyphs. 1 bpp: `jamofit.quality_report(targets, composed, w, h)["iou_mean"]`
over all drawn syllables and over the KS X 1001 ones; 2 bpp: mean absolute level difference / 3 (the FACES.TSV
definition). Routes without a precomposed reference (DOS raw, hanterm BDF, SVF jamo-set copy) leave both empty, and
the lines say so with an empty cell. The page shows the number next to every experimental result.

## The file-name suggestion (`maker/naming.py`)

(controller call) The repository's names are hand-picked (`NGOTB16`, `GOTHA16A`, `OFLNANUM.TXT`) and no rule
reproduces them, so the maker only **suggests** a name from a literal rule and the page always lets the owner edit
every name before `run`. The rule (design call): `ABBR` = the first 5 letters and digits of the family, upper-cased,
spaces removed (NanumGothic -> `NANUM`, Gothic A1 -> `GOTHI`); a precomposed face is `ABBR + px + ("A" if 2 bpp)`;
a jamo set is `ABBR[:4] + px + "J" + ("A" if 2 bpp)`; px is 2 digits (3 above 99); for an SVF source the stem is
kept. Names are 8.3 upper case, `[A-Z0-9]{1,8}\.SVF`, unique within the batch. Before the zip is written each face is
checked against the destination folder in the checkout: a name that exists there with different bytes is refused (the
page shows the clash and asks for another name); a face whose bytes equal an existing file anywhere under `svf/` is
**not** written, the log says which file it equals, and the lines refer to the existing one ("identical bytes share
one file"). Licence texts: suggested `OFL + ABBR` + `.TXT` when the text contains "SIL OPEN FONT LICENSE", else
`LIC + ABBR` + `.TXT`, and a note `ABBR + .TXT` whose first line is "<Family Style> faces (<names>)" (the stem for an
SVF source), then the source file, the version from the name table, the date and the maker's commands; both names are
editable. A licence or note text byte-equal to any `.TXT` already under `svf/` is not written and that file is named
instead, whatever its name.

## The output zip, with a worked example

The zip is `svf-maker-<id>.zip`; every entry's mtime is 1980-01-01 00:00 (controller call: reproducible bytes). Its
root holds `svf/...` and one sidecar folder `svf-maker-<id>/` (design call: the lines cannot be merged into the
repository's TSVs by unpacking, and the log must not land under `svf/`; `.gitignore` gets `svf-maker-*/`). The owner
unpacks it in the checkout, appends the `.lines` files to the three TSVs, runs `python3 web/mkindex.py svf --check`,
commits, and deletes the sidecar.

Example: NanumGothic-Bold.ttf (precomposed, with its OFL beside it) and a composite Gothic A1 Regular TTF, sizes 16
and 18, bpp 1 and 2, defaults otherwise (precomposed to `dos`, jamo sets to `jamo-extra`). The suggested names were
`NANUM16`, `NANUM16A`, ..., `GOTH16J`, `GOTH16JA`, ...; the owner edited them to the repository's style:

    svf/dos/NGOTB16L.SVF           mkfont --size 16 --bpp 1 --unicode ascii,ksx1001-hangul (owner's name; NGOTB16
                                   exists in svf/dos with different bytes and was refused)
    svf/dos/NGOTB16X.SVF           mkfont --size 16 --bpp 2 (owner's name; written, its bytes equal no file)
    svf/dos/NGOTB18L.SVF
    svf/dos/NGOTB18X.SVF
    svf/dos/NGOTBM.TXT             the note (owner's name; dos/NANUMGOT.TXT is not byte-equal)
    (svf/dos/OFLNANUM.TXT)         not written: the OFL text is byte-equal to it; the lines name it
    svf/jamo-extra/GOTHA16N.SVF    jamovec render --size 16 --bpp 1 (owner's name; GOTHA16 exists with different
                                   bytes: the shipped faces were built with usage weights, so it was refused)
    svf/jamo-extra/GOTHA16M.SVF    jamovec render --size 16 --bpp 2 (owner's name)
    svf/jamo-extra/GOTHA18N.SVF
    svf/jamo-extra/GOTHA18M.SVF
    svf/jamo-extra/GOTHAN.TXT      the note (owner's name)
    (svf/jamo-extra/OFLGOTHA.TXT)  not written: the OFL text is byte-equal to it; the lines name it
    svf-maker-3f9c2b7a1d04/BUILD.md
    svf-maker-3f9c2b7a1d04/FACES.TSV.lines
    svf-maker-3f9c2b7a1d04/LICENCES.tsv.lines
    svf-maker-3f9c2b7a1d04/FAMILIES.tsv.lines

The lines (controller call; formats checked against `web/mkindex.py` `read_licences`, `read_families`,
`read_faces_tsv` and the three headers):
- `FACES.TSV.lines`: one row per jamo-set face whose destination is `jamo-extra` only, in `FACES.TSV`'s 16 columns
  `file family px bpp cell sets_ini_med_fin classes_lead_tail bytes quality_all quality_ks2350 quality_freq
  quality_top500 syllables_compared licence hangul_baseline_row latin_baseline_row`: `file` the bare name, `family`
  the detected family and style, sets and classes from the JSET header (`NI/NM/NF`, `LCxTC`), the two quality cells
  from `maker/quality.py` or empty, `quality_freq` and `quality_top500` always empty (they need the game corpus),
  `syllables_compared` the count compared or empty, `licence` the licence file name, `hangul_baseline_row` the face's
  ascent - 1 (the 0-based baseline row, as every existing FACES.TSV row; amended 2026-10-21, Task 9 review), `latin_baseline_row` empty.
- `LICENCES.tsv.lines`: one row `<dest>/<NAME>.SVF<TAB>note,licence` per face in the zip, and also per face skipped
  as byte-identical, naming the existing file it equals (so a new row still covers it; `mkindex.py` wants exactly one
  matching row per face, so the owner drops the duplicate when the existing face already has one, and the log says
  which rows duplicate).
- `FAMILIES.tsv.lines`: one row `svf/<dest>/<NAME>.SVF<TAB>family<TAB>style<TAB>` with the detected family and
  style (the stem and an empty style for an SVF source) and an empty variant.
- `BUILD.md` is `log.md`: the job id, date, repo HEAD (`git -C REPO rev-parse HEAD`; "unknown" when git is missing or
  fails, controller call), every font with its detection facts and chosen settings, then every step's command line,
  exit code, seconds, stdout, stderr, and the facts read back from the file (version, flags, bpp, cell, ascent, glyph
  count, JSET sets/classes, bytes, quality).

What "passes `facecheck.py`" means here (design call): unpacking the zip over a copy of the checkout changes no
existing face (`facecheck.py verify` on the baseline, with the `--map` pairs in the test below, prints nothing and
exits 0), and every produced face is v3, opens in `svfline.py`, draws the sample with ink, and has its licence lines.

## Error handling

- Upload: a request body over 64 MB, a job over 256 MB or 2,000 files, a path with `..`, an absolute path, a
  backslash, a control character or over 255 bytes a component is refused with 413/400 and a message; the job stays
  usable. Archives are unpacked by streaming each member through a counter: a member over 128 MB, an archive whose
  unpacked total passes 512 MB or 50 times its packed size, a member that is not a regular file or directory (symlink,
  device), a name failing the path rules, or an archive inside an archive (listed, not opened) stops the unpack of
  that archive with the reason; what was unpacked before stays and is listed.
- Detection never raises: a file whose detector raises is listed as "unreadable: <exception class>: <message>" and the
  traceback goes to `log.md`.
- A step has a timeout: 600 s (design call: 7 times the slowest measured step), and a job 4 h. A timeout or non-zero
  exit fails the step; the page shows the stderr tail; the zip is still written with the faces that succeeded, and the
  log names the failed steps first. A job with no successful step ends `failed`.
- The subprocess's output is captured whole (the tools print a few lines); a tool that prints over 4 MB is killed.
- An API error is `{error: "<message>"}` with 400/404/409/411/413/500; the page shows it in a notice element and
  never leaves a job in a state the owner cannot read.

## Testing approach

`maker/test/test_maker.py` runs under the existing gate `python3 -m unittest discover -s tools -p 'test_*.py'`
extended by a second line `python3 -m unittest discover -s maker/test -p 'test_*.py'` in `README.md` (design call;
the `tools` line stays as it is).

Fixtures, `maker/test/fixtures/` (written by `maker/test/fixtures.py`, an explicit fixture task; nothing is taken
from `cjk/fonts-cjk.dat`, controller call):
- TTF: `ttf/nanumgothic/NanumGothic-Bold.ttf` from the checkout (precomposed).
- Composite TTF: synthetic, built with `fontTools.fontBuilder.FontBuilder`: ASCII letters as simple glyphs, a few jamo
  component glyphs, and a few syllables as composites of 2 or 3 of them (so the composite test and the `jamovec
  --components` route run).
- OTF: synthetic CFF, built with `FontBuilder` (`setupCFF`); the repository has no `.otf` (verified: `find` found
  none outside `web/`).
- SVF: `svf/dos/NEODG16.SVF` (precomposed 1 bpp) and `svf/iolo/HGKEY6J.SVF` (jamo set) from the checkout.
- BDF, HBF: synthetic, as `tools/test_bdfface.py` writes them (an ISO10646 BDF with ASCII and a few syllables; a
  KSC5601 BDF; a hanterm johab BDF; an HBF with its `.bin`).
- DOS Johab raw: synthetic 11520 bytes with the `844` fill slots blank and a few pieces drawn, and a 2048-byte `--eng`
  beside it.
- Windows FNT: synthetic minimal header (detection only).
- PCF: `/usr/share/fonts/X11/misc/18x18ko.pcf.gz` when present on the host, else that case skips with a message (the
  pattern of `TestModule` in `tools/test_web_picker.py`).
- An OFL text beside each, one font deliberately without a licence, and one `list.txt` (a character list).
- Archives: the fixture folder zipped and tarred (gz, xz) by the test, plus a zip with `../x` and one with a 1 GB zero
  member for the guards.

Unit tests: detection per fixture (format, sizes, coverage counts, jamo availability, licence found or not, the
probable-DOS state, `.txt` never a font); the composite test; naming (the rule, clash, identical bytes, licence reuse
by bytes); the archive guards; settings defaults and validation (every refused combination above); `routes()` per
source kind gives exactly the commands of the table; `quality.py` on a jamo set against its own reference gives
1.0; the lines' formats parse with `mkindex.read_licences` / `read_families` / `read_faces_tsv`; `cmap_has` on a BDF
returns `None` (the `mkfont.py` fix); the lifecycle rules (re-queue at restart, interrupted, cancel queued,
retention); `PUT` without `Content-Length` is 411; zip mtimes are 1980-01-01.

End-to-end test: start the server on `127.0.0.1:0` with a temp data root and `SVF_MAKER_REPO` = the checkout the test
runs in; upload the fixture folder as a zip; `detect`; confirm the DOS raw font and select it; `run` with the defaults
(the licence-less font stays unselected); poll until `done`; download the zip; unzip it into a temp copy of the
checkout's `svf/`; run, from the checkout, `facecheck.py verify manifest/baseline-2026-10-19.tsv --map
dists/engine-data/hires_text/dos=<tmp>/svf/dos --map dists/engine-data/hires_text/jamo-extra=<tmp>/svf/jamo-extra
--map dists/engine-data/hires_text/fonts=ttf --map dists/engine-data/fonts-cjk.dat=cjk/fonts-cjk.dat` (verified on
the checkout at c88f72a: exit 0, no output; `remap` in `facecheck.py` replaces a row's path prefix, so a whole-file
row maps too) and require exit 0 and no output; for every face in the zip: version 2, `svfline.py measure` works and
`line` draws ink; append the three `.lines` files to temp copies of `web/LICENCES.tsv`, `web/FAMILIES.tsv` and
`<tmp>/svf/jamo-extra/FACES.TSV` and run `web/mkindex.py <tmp>/svf --check --licences ... --families ...` requiring
exit 0; `BUILD.md` names every command. The 2 bpp fitted step is not in the end-to-end run (84 s); it is covered by one
unit test that is skipped unless `SVF_MAKER_SLOW=1`.

Preset acceptance (the owner's decision 10): the end-to-end run also uploads `ttf/gowunbatang/GowunBatang-Bold.ttf`
with its `OFLGOWUN.TXT`, preset `dos-u-2bpp`, sizes `[17]`, bpp `[2]`, kind precomposed, and asserts that the step's
output in `work/` is byte-identical to `svf/dos/GBATB17.SVF` (verified achievable on 2026-10-21: `OUT=/tmp/...
bash tools/bake-dos-fonts.sh` then `cmp` reported no difference for GBATB17; NEODG16 and NGOTB16 differed by one
glyph, see the preset table), and that the zip therefore does not carry the face but names
`svf/dos/GBATB17.SVF` as the identical file in its lines and log. The test fails if the tools ever stop reproducing
it; the reason then goes in the preset table, not in the test.

UI smoke test (controller call): `maker/test/smoke.mjs`, one headless run with `playwright-core` from `web/test`
(`cd web/test && npm ci`, as the picker tests) that opens the page, uploads the fixture folder, confirms the DOS font,
runs, waits for `done` and downloads the zip; `test_maker.py` runs it and checks the zip, skipping when node,
`playwright-core` or a browser is missing. The browser is the system Chrome as in `tools/test_web_picker.py`;
`MAKER_BROWSER` overrides the executable (the controller named `/opt/pw-browsers/chromium`; it is not present on this
host today, `~/.cache/ms-playwright/chromium-1217` is, so the override is an env var, not a fixed path). `maker/README.md`
carries a short manual check list: open the page, upload a folder, see the list, edit a name, run, reload mid-job,
download, unpack, `mkindex.py --check`.

## Deployment: the systemd unit

`~/.config/systemd/user/svf-maker.service` (the repository ships it as `maker/svf-maker.service` to copy):

    [Unit]
    Description=svf-fonts SVF maker on the tailnet
    After=network-online.target

    [Service]
    Environment=SVF_MAKER_REPO=%h/work/svf-fonts
    Environment=SVF_MAKER_DATA=%h/.local/share/svf-maker
    Environment=SVF_MAKER_BIND=100.78.108.85:8766
    ExecStart=/usr/bin/python3 -P %h/work/svf-fonts/maker/server.py
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=default.target

`systemctl --user enable --now svf-maker.service`; the page is `http://100.78.108.85:8766/?job=<id>`. The service
reads the checkout at `SVF_MAKER_REPO` (its `tools/` and `svf/`) and writes only under `SVF_MAKER_DATA`.

## Left to the builder

- The HTML layout and CSS, within the picker's house style (one page, a font table with a row expander for the
  per-font overrides, a settings panel, a job panel).
- The exact JSON shape of `job.json` and the API bodies, documented in `maker/README.md` once chosen.
- The `.notdef` picture test's implementation for PCF/FNT (reusing `mkfont.py`'s rule, as a function in `detect.py`).
- Whether Windows FNT/FON opens at all in this Pillow build (no sample: detection is required, conversion is best
  effort and must fail cleanly).
- The 2 bpp reference raster in `quality.py` (which `jamoaa` function gives the per-syllable coverage at a cell).
