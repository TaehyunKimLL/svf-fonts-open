# Desktop font finder: fonts hidden in programs, data files and ROMs (design)

Card t_235403fe: "desktop app: font finder for unknown programs/ROMs (binscan/rawcarve interactive) - design". Written
2026-11-23 on branch `finder-design` of `svf-fonts-open` (base `5dbf399`), for a builder who has not seen the
repository. This is a design only: no code is changed by this card, and no implementation card is created before the
owner has approved it. Facts below were read from the tree (main, and branch `mame-roms` at `55c0be1` where said) or
run on this host; what was not run says "not verified" or "target". Where a choice is the owner's I decided for the
builder, marked "(design call)", and collected it again in section 15; the owner answered all ten on 2026-11-23, every
one as recommended, and section 15 now records the answers.

Read with this document: `docs/recipes.md` "Finding a font inside a program or data file, with Claude" (the prompt, the
byte-size signatures, the NKP / Dokkaebi / 86Box examples) and, on `mame-roms`, "Korean font ROMs in MAME sets";
`tools/binscan.py`, `tools/rawcarve.py`, `tools/nkpspec.py` (on `mame-roms`: `--invert`, `--gfx`, `--bg` / `--fg`,
`rawcarve.py region` / `ink`, `jamoset.py --layout spec`); `maker/README.md`, `docs/desktop-app.md`, `maker/server.py`
(the route table at line 642), `maker/detect.py` (entries, `prep` ops), `maker/routes.py`, `maker/sources.py`,
`maker/preview.py`, `maker/static/maker.js` / `svfview.js`; the designs
`2026-11-04-maker-local-mode-design.md` and `2026-11-05-maker-desktop-design.md`.

## 1. Intent

Finding a font inside a DOS driver, a game's data file or a ROM set is today a session with an assistant: the prompt
of `docs/recipes.md`, `binscan.py info / sets / ascii / runs / render` to look, `rawcarve.py` to cut, `bdfface.py` /
`jamoset.py` to build, and a person reading PNGs in between. The finder puts that loop into the desktop app: pick a
file (or the files of a ROM set), let the app scan it, look at ranked candidates drawn as glyph grids, adjust the
reading with an instant redraw, say what each region is, and convert it through the routes the maker already has. What
was found is saved as a **recipe**: a small JSON of file hashes and parameters, without one byte of the font, that the
maker recognises next time, re-runs headless, and that can be passed to someone who holds the same files.

## 2. Goals

- One flow in the app from "an unknown file" to "SVF faces in the output folder", for the cases the recipes have worked:
  a raw 8x4x4 (or other known-size) jamo set, an 8xH / 16x16 English font, a dense KS X 1001 dump, a KS code grid,
  1 bpp in any stored order, inverted, multi-bit tiles with a pen rule, a region interleaved from several ROM files, and
  a font with its own compose rule given as a `rawcarve.py compose` spec.
- Every pixel rule stays in the Python tools. The finder adds no decoder and no composer of its own: the page draws what
  the sidecar decoded (candidate grids) or what the WASM renderer draws from a built face (results).
- Local mode only: files are read where they are, never uploaded or copied into the data directory; derived files live
  in the job's `.svf-maker-<id>/` inside the output folder and go when the job ends.
- The input is untrusted and is never executed, unpacked by an external program or parsed beyond bounded byte reads.
- A run is reproducible by hand: `BUILD.md` lists the `rawcarve.py` / `jamoset.py` / `bdfface.py` commands, and the
  recipe JSON is written beside it.
- A recipe library (built-in and the user's) recognises known files by size and hash at detection; the known ROMs of
  card t_97acecf9 are expressible as built-in recipes.
- The proofs run on synthetic fixtures; checks on real files are environment-gated.

## 3. Non-goals

- Disassembly, emulation or any execution of the file; unpacking LZEXE / PKLITE / ARJ / RAR / 7z (the finder names them
  and says "unpack first"). Reading a driver's code stays with a person or an assistant; section 10 says how the app
  hands that over.
- An automatic answer. The finder ranks and draws; the user decides. Where the bytes cannot decide (tied `sets`
  offsets, a KS order with gaps), it says so.
- A JavaScript or WASM port of `binscan.py` / `rawcarve.py` (owner, 2026-11-05: the Python tools stay).
- New glyph layouts in the tools beyond what `mame-roms` has. Small tool changes this design needs are listed in 7.5.
- Upload mode. The finder is offered only when `/api/caps` says `local`.
- A network feature of any kind: no recipe download, no call to an assistant's API.

## 4. Constraints and facts

1. **The tools.** `binscan.py`: `info` (kind from the first 0x60 bytes: MZ with LZEXE / PKLITE marks, ARJ, ZIP, option
   ROM, `.COM`; entropy per block; size signatures), `runs`, `sets`, `ascii`, `render` (text or PNG through its own
   zlib PNG writer, no Pillow). `rawcarve.py`: `cut`, `eng`, `bdf` (`--dense` / `--grid L0,T0,PITCH`), `compose`; on
   `mame-roms` also `region` (interleave `--unit 1|2|4`, `--swap`), `ink`, `--gfx` layouts (presets and MAME
   `gfx_layout` lists, parsed with bounds: 1,024 offsets a list, nesting 32, numbers of 12 characters), `--bg` / `--fg`,
   `--invert`, the built-in spec `spc1500`, and `jamoset.py --layout spec` (an exact jamo set from a compose spec).
   Caps in the tools: `binscan.MAX_SCAN` 16 MiB a scan, `rawcarve.MAX_FILE` and `MAX_REGION` 64 MiB. Both print text.
2. **`mame-roms` is not on main** (card t_c1eca08f; it diverges from main, which has `svf2ttf.py` since). The finder's
   phases 2 and 3 need it merged; phase 1 needs only what main has.
3. **Scan cost (measured here, pure Python, one core).** On a 524,288-byte synthetic file: `info` 0.03 s, `ascii`
   0.06 s, `sets` 0.11 s, `runs --glyph 16x16` with its default of one phase a row 9.65 s, `runs --order strips --step
   32` (one phase) 0.63 s; `render` of 256 glyphs to a PNG 0.06 s including the interpreter start. `runs` is the cost:
   about 19 s a MiB at all 16 phases, about 1.2 s a MiB a phase. An 8 MiB sprite region cannot be scanned at every
   phase inside a budget a person waits for.
4. **The maker.** One page (`maker/static/index.html`, `maker.js`), English only, no string table. Local mode: a job
   has an output folder; `PUT /api/jobs/<id>/sources` checks each path (`maker/sources.py`: absolute, not a link, not
   the data folder, no overlap, optional `SVF_MAKER_ROOTS`; a file over 256 MiB is skipped). `detect.py` turns files
   into font entries with a `kind`, optional `prep` ops (source steps such as `pcf-bdf`, listed in `BUILD.md`) and
   routes (`routes.py`). A file it cannot read is an entry of kind `other` labelled `unknown`. A DOS raw font is
   recognised by exact size only (`DOS_SIZES`), an English companion by size (`ENG_SIZES`). Source previews of baked
   kinds are drawn by the page from a baked SVF through the WASM renderer (`svfview.js`).
5. **Tools run as bounded subprocesses** (`toolrun`, `toolreg`, `preview.run_bounded` with a 60 s timeout), but
   `detect.py` already imports tool modules and reads untrusted files in-process with caps. `binscan` and `rawcarve`
   are already in the frozen sidecar's module graph (`maker/sidecar.py` `GRAPH_MODULES`), not in its `TOOLS` table.
6. **The shell bridge** is four functions (`pickFiles`, `pickFolder`, `pickOutputDir`, `openOutputFolder`); there is
   no save dialog. The page's CSP allows its own origin only.
7. **The sidecar bundles** Pillow and fontTools, no numpy (`desktop/build/requirements-sidecar.txt`).
8. **The examples' facts the UI must cover**: tied `sets` offsets a row apart (Dokkaebi: decided by source or a loose
   copy); a `.COM` loads at 0x100; a wrong compose spec draws a wrong face without an error (NKP); a KS table at a
   sprite index inside a larger tile ROM (Date Quiz Go Go: sprite 13347); an outline pen (Quiz KOF: `--fg 1`); a
   background pen that is not 0 (X Se Dae: `--bg 15`); a font whose order is not KS (quizdaisk: not resolved).

## 5. The user flow

1. **Enter.** In local mode, after `detect`, every entry of kind `other` with format `unknown` gets a button "look
   inside" (KO "안쪽 살펴보기"); several unknown entries can be ticked and opened together as one ROM set. The sources
   panel also gets "find a font in a file..." which picks files and opens the finder at once. The job and its output
   folder exist first, as for any local job (the scratch lives there).
2. **Known file.** If the library holds a recipe whose files match (section 9), detection already shows the entry as
   `known: <recipe title>` with the recipe's faces as routes; the finder is not needed, and opens prefilled when the
   user wants to look.
3. **Analyse.** The finder opens and starts the analysis (section 6): facts at once (size, kind, signatures, entropy
   map), scans as they finish, each within its budget. A packed file (entropy near 8 everywhere, an LZEXE / PKLITE /
   ARJ mark) is said to be packed and offered nothing else but the manual viewer.
4. **Candidates.** A ranked list; each row has a thumbnail (the first 32 glyphs), the facts that made it a candidate
   and a proposed meaning ("8x4x4 set, 16 px", "8x16 English", "2,350 glyphs: KS dense?"). Tied offsets are one row
   with every tie drawn side by side.
5. **Look and adjust.** Picking a candidate (or any place on the overview strip) loads the viewer. Every parameter
   redraws at once: offset, glyph WxH, stride, order (rows / strips / cols / bytecols), lsb, invert; for tiles the gfx
   layout, the pen view and the pen rule; for a ROM set the region (which files, interleave unit, swap).
6. **Mark.** The user selects a span of glyphs and says what it is (section 5.3). An **anchor** makes the mapping
   without arithmetic: click a glyph, type its character ("가", "A"), and the finder solves the first code, the dense
   start or the grid origin.
7. **Trial.** "Try" builds the faces of the marks into the scratch with the real tools and shows the sample line
   through the WASM renderer, with the numbers of `docs/recipes.md` "Checking a face": glyph count, `--check` result,
   `svfline.py measure`, ink of the sample line, and the fit IoU for a jamo-set fit.
8. **Apply.** The marks become font entries of the job (section 8). From here it is the usual maker: settings, run,
   steps table, faces in `svf/<dest>/`, `BUILD.md`.
9. **Save the recipe.** Written into `build-<id>/` on every run; "save to my recipes" adds it to the user library.

### 5.1 The finder view (wireframe)

The finder replaces the main layout while it is open (the top bar stays; "back to the job" returns).

    +-- SVF maker ------------------------------------------ [finder: NKP.COM]  [back to the job] ---+
    | FILES / REGION     | VIEWER                                             | READING             |
    | (a) NKP.COM        | overview: [entropy+ink strip of the region, a    ] | offset  [0x39a0 ] +- |
    |   38,184 B  .COM   |           [marker at the offset, marks coloured  ] | address 0x3aa0 (.COM)|
    |   sha256 3f1c...   |                                                    | glyph   [ 8]x[16]    |
    | region: [file a v] | +--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+  | stride  [16] B       |
    | [edit region...]   | | 0| 1| 2| 3| 4| 5| 6| 7| 8| 9| a| b| c| d| e| f|  | order   (rows v)     |
    |--------------------| +--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+  | [ ] lsb [ ] invert   |
    | CANDIDATES         | |  glyph grid: 16 columns, scale 3, index labels |  | tiles   (none v)     |
    | 1 8x16 English     | |  hover: glyph 65, offset 0x3db0                |  | columns [16] scale[3]|
    |   0x39a0 edge 0    | |  drag: select a span                           |  |---------------------|
    | 2 run 16xN 0x41a0  | +------------------------------------------------+  | MARK the selection   |
    |   214 glyphs       | [|<] [< page] [< glyph] [< row] [< byte] ... [>|]   | (English 8xH v)      |
    | 3 ...              | selection: glyphs 0..127 (0x39a0..0x41a0)           | first code [0x00]    |
    | [analyse again]    | [type a character for the clicked glyph: [A] ]      | [add mark]           |
    +--------------------+----------------------------------------------------+---------------------+
    | MARKS  1 English 8x16 at 0x39a0, 128 glyphs   2 compose spec NKP.json (17 sets)   [remove]     |
    | TRIAL  [try]  안녕하세요 ABC 123  (WASM)   2,447 glyphs, check ok, width=144 ascent=12, ink 467 |
    | [apply to the job]   [save recipe]   [load recipe or spec...]   [export for an assistant...]   |
    +------------------------------------------------------------------------------------------------+

- **Overview strip**: one column a block of the region (entropy as lightness, glyph-like blocks tinted, marks and the
  current window outlined); a click seeks. It is the entropy map of `binscan.py info` as a picture.
- **Grid**: the server's 1-pixel-a-pixel PNG scaled by the page with `image-rendering: pixelated`; the page draws the
  cell lines, index labels, hover and selection itself (it knows the geometry). "Copy as text" gives `binscan.py
  render`'s `#` / `.` form of the selection.
- **Long-strip mode** (the recipe's "draw long strips when nothing lines up"): one toggle sets the glyph to W x 512 so
  the stored height and the start of a font can be seen; clicking two rows sets the glyph height from their distance.
- **Offset steps**: byte, stored row (ceil(W/8) bytes; for strips one byte), glyph (stride), page; the address line
  shows the load address for a `.COM` (+0x100) and the header size for an MZ file.
- **Tiles panel** (phase 2): preset (`16x16x4_packed_lsb`, ...) or a pasted `gfx_layout` (the `planes=..;x=..;y=..;inc=N`
  form `binscan.py` parses; a paste of the C braces is normalised by the page and validated by the server). The **pen
  view** draws pens as grey levels with a legend of the pens present in the window and their counts; clicking pens sets
  the rule (background pen, or the ink pens), and the grid switches back to ink.
- **Region editor** (phase 2): the files as chips in ordered groups, `unit` 1 / 2 / 4, `swap`; presets named as the
  MAME macros of the recipes table (`ROM_LOAD` one after another, `ROM_LOAD16_BYTE`, `ROM_LOAD32_WORD`,
  `ROM_LOAD64_WORD`, `ROM_LOAD16_WORD_SWAP`). Suggestions: files of equal size whose names differ in one digit or letter
  are proposed as a group, each proposal with the thumbnail its best scan gives.

### 5.2 Ties and help from outside the bytes

A tied `sets` candidate shows each offset's reading as the same six composed syllables (through the trial path) and the
sentence of `binscan.py`: the bytes cannot tell; decide from the driver's code or a loose copy. Two aids:

- **Compare with a file I have** (phase 2): the user picks a loose font file; the finder reports where its bytes occur
  in the region (exact search) and, for each tied offset, how many bytes differ (the `cmp` of the Dokkaebi example).
- The recipe records how a tie was decided (`"decided": "by eye" | "loose copy" | "driver code"`), so a reader of the
  recipe knows how far to trust it.

### 5.3 What a region can be marked as

| Mark | Parameters | Carve (prep ops, section 8) | Entry it becomes | Routes |
|---|---|---|---|---|
| raw jamo set | layout by length (`DOS_SIZES`: 8x4x4 at 16 / 24 / 40 / 48 px, 10x4x4, 6x2x1, ...) | `[region] [ink] cut` | `dos-raw` (existing) | `dos raw`, `johab844` (existing) |
| English 8xH | H 8..16, top, first code, count | `[region] [ink] eng` (+ `rawbdf --chars ascii` when a route needs a BDF) | `eng` companion (existing) | paired by the page as today |
| English 16x16 (phase 2) | first, count | `eng --width 16` | `eng`, cell `16x16` | as above |
| KS dense | chars `ks-hangul`; start glyph | `[region] rawbdf --dense` | `carved-bdf` (new) | `bdfface`, `bdfface + from-svf fit`; `mkfont` when chars is `ks-nonhanja` / `ks-all` |
| KS grid | `L0,T0,PITCH` (presets: 94 x 94 `0xA1,0xA1,94`; VGA ROM `0x80,0x80,128`), chars | `[region] rawbdf --grid` | `carved-bdf` | as above |
| compose spec (phase 3) | a spec (inline, built-in `spc1500`, or derived by `nkpspec`), syllables `ks` / `all` | `compose` | `carved-spec` (new) | `spec` (jamo, native, exact: `jamoset.py --layout spec`), `compose bdf + bdfface` (precomposed), `+ from-svf fit` |

Every mark carries the reading it was made with (geometry, invert, gfx and pen rule) and an ascent (default the
tools': 7/8 of the height; the recipes' `--ascent 12` for VGA ROMs is a field of the mark).

## 6. Automatic analysis

The analysis is a job of the finder session with a total budget (default 60 s, the user may run it again with 300 s or
on a window) and a budget a scan (20 s); every scan is a `binscan.py` subprocess registered in `toolreg`, killed on
cancel, on timeout and when the session closes. Results arrive as they finish; an exceeded budget is shown as "not
scanned: <what>", never as "nothing found".

- **Stage 0, at once (in-process, bounded reads).** Size, `kind_of`, size signatures, the entropy map (streamed, a
  block at a time), the library match (section 9). Windows are derived from the map: blocks at 7.5 bits or more, and
  blocks of one byte value, are left out of every scan.
- **Stage 1, cheap scans on the windows.** `ascii` at heights 16, 14 and 8, plain and inverted; `sets` for 8,4,4 at
  16x16 and 24x24, plain and inverted (and the other set counts the tools know).
- **Stage 2, `runs`, coarse then fine.** For 16x16 rows, 16x16 strips, 24x24 rows, 8x16 and 8x8: first two phases
  only (byte 0 and byte 1: a read shifted by whole rows still looks like glyphs, a read shifted by one byte does
  not); then all phases, but only around the runs the coarse pass found. Target from the measurement of 4.3: about
  2.5 s a MiB a geometry (not verified; the fine pass is a tool change, 7.5).
- **Stage 3, tiles (phase 2).** When a region is larger than 256 KiB and stage 2 found no long 1 bpp run, `runs` with
  the packed presets (`16x16x4` lsb / msb, `8x8x4`) at one phase.
- **Stage 4, meaning.** A run of 2,350 or more 16x16 or 24x24 glyphs gets a **KS-order score** (phase 2, experimental):
  in KS X 1001 order the initial consonant changes at known glyph indices (가 .. 깊 share ㄱ, then ㄲ, ...); the score
  is how well the breaks in top-left-quadrant similarity between consecutive glyphs line up with those indices, tried
  at every start within the run. A good score proposes "KS dense, 가 at glyph N". It is a hint, shown as a hint; the
  anchor of 5 step 6 is the user's answer.

**Ranking** (highest first): a library recipe match; a file whose size is a signature; a single `sets` hit; an `ascii`
hit with a low edge count; runs by inked glyph count (KS-order score first when present); tied `sets` offsets; near
matches. Every row says why it is there, in the tools' own numbers (seam, edge, inked count).

## 7. Where computation runs, and the API

### 7.1 Decision: the sidecar decodes, the page draws

| Work | Where | Why |
|---|---|---|
| Live grid render | sidecar, **in-process** (`binscan.decode` on a bounded window, PNG by `binscan.png_bytes`) | no port of the decoder (non-goal); a process start a redraw is too slow for a slider. The decode is arithmetic on a byte window, the same class of in-process reading `detect.py` already does |
| Scans, region assembly, ink maps, carving, trial and final builds | sidecar, **subprocess** tools with a time budget | long, killable, the same argv `BUILD.md` prints |
| Result preview (trial and built faces) | page, the WASM renderer (`svfview.js`) | as every other preview of the maker |
| Grid overlay, selection, anchors, recipe form | page | no pixel rule involved |

Redraw target: under 100 ms for a 256-glyph 1 bpp grid, under 300 ms for 256 tiles of a gfx layout (not verified;
the page debounces 30 ms, numbers its requests and drops answers that are not the latest). If the gfx target is
missed, the tile view is drawn from the session's ink map (`rawcarve.py ink`, written once a pen rule) instead.

### 7.2 Session and files

A finder session belongs to a local job: `job.json` gets `finders: {n1: {...}}` (file ids, sizes, hashes, regions,
candidates, marks; no bytes, and paths only where a local job already keeps them). Scratch is
`.svf-maker-<id>/finder/<n>/` in the output folder (assembled regions, ink maps, carved files, trial faces), removed
with the job's files directory as today.

A file is opened by the path rules of `sources.py`, must be a regular file, and is identified by `(st_dev, st_ino,
size, mtime_ns)` taken at open; every later read re-checks it and answers 409 "the file changed: open it again"
otherwise. SHA-256 is computed once in the background (streamed) and is part of the session state when ready.

### 7.3 Endpoints (all under the token, local jobs only, JSON errors with a stable `code`)

    POST   /api/jobs/<id>/finder                  {"paths": [...]} or {"fonts": ["f3", "f4"]}   -> {"finder": "n1"}
    GET    /api/jobs/<id>/finder/<n>              files, regions, analysis progress, candidates, marks, recipe match
    DELETE /api/jobs/<id>/finder/<n>              stops its tools, removes its scratch
    PUT    /api/jobs/<id>/finder/<n>/regions      [{"id": "r1", "groups": [["a","b"],["c","d"]], "unit": 1, "swap": false}]
    POST   /api/jobs/<id>/finder/<n>/analyse      {"region": "r1", "budget_s": 60, "start": 0, "length": null}
    POST   /api/jobs/<id>/finder/<n>/cancel
    GET    /api/jobs/<id>/finder/<n>/map?region=  the overview strip (PNG, one column a block)
    GET    /api/jobs/<id>/finder/<n>/render?region=&offset=&glyph=16x16&stride=&order=&lsb=&invert=&gfx=&bg=&fg=
                                                   &count=&cols=&view=ink|pens|text      -> image/png (or text/plain)
    POST   /api/jobs/<id>/finder/<n>/anchor       {"reading": {...}, "glyph": 4129, "char": "가", "as": "ks-grid"}
                                                   -> the solved parameters ({"grid": [128,128,128]} ...) or 422
    PUT    /api/jobs/<id>/finder/<n>/marks        the whole list of marks (section 9.1 `items`)
    POST   /api/jobs/<id>/finder/<n>/trial        builds the marks' faces in the scratch -> {"faces": [...], "numbers": {...}}
    GET    /api/jobs/<id>/finder/<n>/trial/<face>.svf
    POST   /api/jobs/<id>/finder/<n>/apply        the marks become font entries of the job (section 8) -> the job
    GET    /api/jobs/<id>/finder/<n>/recipe       the recipe of the current marks
    PUT    /api/jobs/<id>/finder/<n>/recipe       load a recipe or a compose spec (validated; prefills regions and marks)
    POST   /api/jobs/<id>/finder/<n>/export       {"what": "recipe" | "prompt", "renders": false} -> a path in the output folder
    GET    /api/recipes                           the library: built-in and the user's (id, title, files' names and sizes)
    POST   /api/recipes                           save a recipe to the user library
    DELETE /api/recipes/<rid>                     a user recipe only

`render` answers with the PNG and the headers `X-Finder-Count` (glyphs really drawn before the region ends) and
`X-Finder-Pens` (the pens present, for the legend). A candidate is `{id, region, kind, offset, reading, count, score,
why, ties, suggest}`; `reading` is the same object a mark and the `render` query carry.

### 7.4 Limits and untrusted input

| Limit | Value | Source |
|---|---|---|
| files a session | 16 | (design call; `MAX_SOURCE_PATHS` is 64) |
| a file | 64 MiB | `rawcarve.MAX_FILE` (the maker's 256 MiB local cap is higher; the finder refuses earlier, with the reason) |
| an assembled region | 64 MiB, and free space in the output folder checked first | `rawcarve.MAX_REGION`, `LOCAL_FREE_MIN` |
| a scan window | 16 MiB | `binscan.MAX_SCAN` |
| a render | 4,096 glyphs, glyph sides 1..1024, 64 columns, canvas within `preview.MAX_CANVAS` / `MAX_PIXELS` | `binscan.py render`, `preview.py` |
| analysis | 60 s total, 20 s a scan by default; 300 s at most | (design call) |
| trial build | 60 s a tool | `preview.TIMEOUT_S` |
| sessions a job, candidates a session, marks | 8, 200, 64 | (design call) |
| a recipe or spec loaded | 256 KiB of JSON, 16 files, 64 items, 16 faces | (design call) |

- **Never executed**: no code path starts the file, an emulator, a disassembler or an unpacker. Archives are named,
  not opened (phase 2 reads the members of a zip in place through `maker/archive.py`'s guards, because MAME sets come
  as zips; other archives stay "unpack first, into a folder of its own").
- **Bounded reads**: the in-process render reads `count x stride` bytes plus one glyph footprint by seek; a gfx layout
  whose planes span the region reads through a read-only `mmap`. Every number of a request is range-checked before any
  allocation; a gfx string goes through `binscan.parse_gfx` only.
- **A recipe is untrusted too**: it carries parameters, never a command, a path or a tool name outside the fixed set;
  the server builds every argv itself. File names in a recipe are labels: files are bound by the user's pick and
  matched by size and hash. Face names go through `maker/naming.py`.
- **Privacy**: no byte of a source file in `job.json`, the logs, a recipe or an error text; renders are served to the
  page of the same launch only and are never written outside the scratch (the prompt bundle of section 10 is the one
  opt-in exception, into the output folder).
- **Local only**: nothing new listens or connects; the existing no-network tests are extended to the new modules.

### 7.5 Tool changes the finder needs (small, each with its own tests)

- `binscan.py`: `--json` on `info`, `runs`, `sets`, `ascii` (the same facts as the text, one object); `runs
  --phases a,b` and `--around OFFSET,LENGTH` for the coarse and fine passes; library entry points for `decode` of a
  window and the PNG (they exist; the server calls them instead of the CLI).
- `rawcarve.py`: nothing for phase 1; phase 3 adds `compose --check-spec` (validate a spec against a file's size and
  report every set's extent) so a wrong spec is refused before it draws a wrong face.
- `maker/sidecar.py`: `binscan`, `rawcarve`, `nkpspec` in `TOOLS` (card t_97acecf9 adds some of them first).

## 8. From marks to faces: the existing pipeline

`apply` writes nothing but entries: each mark becomes a font entry whose `prep` is the list of carve ops, so the worker
prepares it like a `pcf-bdf` source and `BUILD.md` prints the commands.

| Prep op | Command |
|---|---|
| `region` | `rawcarve.py region A,B C,D [--unit N] [--swap] -o region.bin` |
| `ink` | `rawcarve.py ink region.bin --gfx LAYOUT [--bg P \| --fg P,...] [--invert] -o ink.bin` (or `--glyph WxH --order O` for 1 bpp orders the next tool does not read) |
| `cut` | `rawcarve.py cut SRC --offset O --length N -o font.fnt` |
| `eng` | `rawcarve.py eng SRC --offset O [--height H] [--top T] [--first C] [--count N] [--width 16] [--invert] -o eng.raw` |
| `rawbdf` | `rawcarve.py bdf SRC --offset O --glyph WxH [--order O] --chars SET (--dense \| --grid L0,T0,P) [--ascent A] -o carved.bdf` |
| `compose` | `rawcarve.py compose SRC --spec SPEC.json [--syllables all] [--eng ...] [--ascent A] -o composed.bdf` |

- A `cut` result is a `dos-raw` entry with its layout given by the mark (not guessed from the size again), an `eng`
  result an `eng` entry; both use today's routes unchanged.
- `carved-bdf` is a new kind for the Unicode BDFs `rawcarve.py` writes: the `bdfface` route takes it as `--hangul` with
  the paired English mark's BDF as `--ascii`, `--cell` from the mark and `--chars-from` the KS list, exactly the
  command lines of the 86Box recipe; `bdfface + from-svf fit` follows as for `bdf-ksc5601`.
- `carved-spec` (phase 3) gets the route `spec` (`jamoset.py --layout spec --spec SPEC SRC [--eng E] --check`, native
  and exact) and the precomposed route through `compose`.
- A recipe's `faces` only preselect routes, layouts and names; the user can change them in the fonts table as for any
  entry.
- The run writes `build-<id>/RECIPE-<name>.json` beside `BUILD.md`.

**Headless.** The same planner (recipe + bound files -> entries with prep ops -> argv list) is reachable without the
page:

    svf-maker-sidecar recipe check RECIPE.json FILE...            which files match (size, sha256), what is missing
    svf-maker-sidecar recipe run   RECIPE.json FILE... --out DIR  the recipe's faces, BUILD.md and RECIPE json in DIR
    svf-maker-sidecar recipe list                                 the built-in and user recipes

(`python3 -P maker/recipe.py ...` from a checkout.) `run` refuses files that do not match unless `--unverified`; its
faces are byte-identical to the app's run of the same recipe (a test).

## 9. Recipes

### 9.1 Schema (version 1)

    {
      "recipe": 1,
      "id": "86box-tgkorvga",                        // [a-z0-9-]{1,48}; unique in a library
      "title": {"en": "Trigem Korean VGA font ROM (ET4000)", "ko": "삼보 한글 VGA 글꼴 ROM (ET4000)"},
      "notes": "128 x 128 KS grid, two 8-pixel strips (86Box vid_svga_render.c).",
      "refs": ["86Box/roms 1ac40f2 video/et4000/tg_ksc5601.rom", "docs/recipes.md#korean-vga-font-roms-86box"],
      "files": [
        {"id": "font", "name": "tg_ksc5601.rom", "size": 524288, "sha256": "<64 hex>", "sha1": "<40 hex, optional>"},
        {"id": "bios", "name": "tgkorvga.bin", "size": 32768, "sha256": "<64 hex>", "optional": true}
      ],
      "regions": [                                    // optional; a file id is itself a region
        {"id": "spr", "groups": [["c1", "c2"], ["c3", "c4"]], "unit": 1, "swap": false}
      ],
      "items": [
        {"id": "hangul", "kind": "ks-grid", "region": "font", "offset": 0,
         "reading": {"glyph": [16, 16], "order": "strips", "stride": 32, "lsb": false, "invert": false},
         "chars": "ks-hangul", "grid": [128, 128, 128], "ascent": 12},
        {"id": "ascii", "kind": "english", "region": "bios", "offset": 18989,
         "reading": {"glyph": [8, 16]}, "first": 0, "count": 256, "top": 0, "ascent": 12}
      ],
      "faces": [
        {"name": "TGVGA16", "kind": "precomposed", "route": "bdfface", "hangul": "hangul", "english": "ascii"},
        {"name": "TGVGA16J", "kind": "jamo", "route": "bdfface + from-svf fit", "layout": "844", "from": "TGVGA16"}
      ],
      "expect": {
        "items": {"hangul": {"glyphs": 2350, "sha256": "<of the carved file>"}},
        "faces": {"TGVGA16": {"bytes": 122392, "glyphs": 2447, "ink": 476}}
      }
    }

- `items[].kind`: `raw-set` (`layout`, `length`), `english` (`width` 8 | 16, `height`, `top`, `first`, `count`),
  `ks-dense` (`chars`), `ks-grid` (`chars`, `grid`), `compose` (`spec`: an inline compose spec object, `{"builtin":
  "spc1500"}` or `{"derive": "nkpspec"}`; `syllables`). `reading` may also hold `gfx`, `bg`, `fg`. An item may carry
  `"decided"` (5.2).
- `expect` is optional and is what makes a re-run self-checking: counts, the hash of each carved file and the numbers
  of each face. A mismatch is reported, not hidden; the faces are still written.
- A recipe holds **no font byte and no path**: names, sizes, hashes, offsets, rules, numbers. A compose spec is offsets
  and rules (as `nkpspec.py` says of its output). A hash of a carved file identifies it without revealing it.
- Unknown keys are refused (a typo must not be silently ignored); `recipe` other than 1 is refused with the version.

### 9.2 The library and detection

- **Built-in**: `maker/recipes/*.json` in the repository and the sidecar (hashes and offsets only, so the OFL-only
  repository can carry them). **User**: `<data root>/recipes/*.json` (`~/.config/svf-maker/maker/recipes/` in the
  desktop app); a user recipe never shadows a built-in id.
- **Matching at detect**: the library is indexed by file size. A file whose size matches no recipe file is not hashed
  (ordinary fonts cost nothing). A size match is hashed; the states are
  - **known**: every non-optional file of a recipe is among the job's sources with its hash: the entry is labelled
    `known: <title>`, lists a missing optional file as a hint ("for English also pick tgkorvga.bin") and offers the
    recipe's faces;
  - **part of a set**: some files match, others are missing: "part of <title>: also needs <names>; pick the folder";
  - **similar**: name and size match, hash differs: "looks like <title>, another revision: opens in the finder with
    the recipe's parameters, unverified" (`expect` is not applied).
- A known entry needs no finder session: the recipe's planner makes its prep ops directly.

### 9.3 Card t_97acecf9's known ROMs

That card detects the 86Box Trigem / Kasan / ATI ROMs, the SPC-1500 set and the Date Quiz Go Go, Quiz KOF and X Se
Dae sets by size and hash. Decided (section 15, 3): those routes **are** recipes. t_97acecf9 stores its table as
`maker/recipes/*.json` in schema version 1 from the start, beginning with the three 86Box ROMs, and implements the
subset of 9.4 that they need: `files`, `items` of kind `ks-grid` and `english`, `faces`, optional `expect`. The planner
(recipe + bound files -> entries with prep ops -> argv) is the piece both cards share: t_97acecf9 writes it for its
subset, the finder's phase 0 extends it and does not replace it. A key or an item kind the implementation does not read
yet is refused by name ("not supported yet: regions"), never ignored, so a recipe of a later phase cannot half-run.
Every worked example of the recipes that was resolved (NKP, NKP3, DKBB, DKBII; the three VGA ROMs; SPC-1500; dquizgo,
xsedae, quizkofk) becomes a built-in recipe as its phase lands; the unresolved ones (livequiz, quizdaisk) do not.

### 9.4 Schema version 1: field reference

A recipe is one JSON object in UTF-8 (the `//` comments of 9.1 are the document's, not the format's), at most 256 KiB.
Integers are JSON numbers without a fraction; an offset or a size is 0 .. 2^26 (64 MiB). "id" below means
`[a-z0-9][a-z0-9-]{0,47}`. Keys not listed are refused. R = required, O = optional (default in brackets).

| Object | Key | | Type and rule |
|---|---|---|---|
| recipe | `recipe` | R | the integer 1 |
| | `id` | R | id; the file is `<id>.json`; unique in a library |
| | `title` | R | `{"en": text, "ko": text}`, `en` required, each 1..120 characters |
| | `notes` | O | text, at most 2,000 characters [""] |
| | `refs` | O | list of at most 16 texts of at most 200 characters (where the layout was read from; never opened) |
| | `files` | R | list of 1..16 file objects, ids distinct |
| | `regions` | O | list of at most 16 region objects [none] |
| | `items` | R | list of 1..64 item objects, ids distinct |
| | `faces` | R | list of 1..16 face objects, names distinct |
| | `expect` | O | `{"items": {item id: {...}}, "faces": {face name: {...}}}` |
| file | `id` | R | id, distinct from every region id |
| | `name` | R | the usual base name: a label and the tie-breaker of "similar"; no `/`, `\` or control character, 1..255 bytes |
| | `size` | R | integer, 1 .. 2^26 |
| | `sha256` | R | 64 lower-case hex characters of the whole file |
| | `sha1` | O | 40 lower-case hex characters (the MAME `ROM_LOAD` hash; informational, checked when present) |
| | `optional` | O | boolean [false]; a face whose item reads a missing optional file is not offered |
| region | `id` | R | id |
| | `groups` | R | list of 1..16 lists of 1..8 file ids: the files of a group interleaved, the groups one after another |
| | `unit` | O | 1, 2 or 4 [1] |
| | `swap` | O | boolean [false] |
| item | `id` | R | id |
| | `kind` | R | `raw-set`, `english`, `ks-dense`, `ks-grid` or `compose` |
| | `region` | R | a file id or a region id |
| | `offset` | O | integer byte offset of glyph 0 in the region [0] |
| | `reading` | R | reading object |
| | `ascent` | O | integer 1..height [the tool's default: 7/8 of the height, rounded up] |
| | `decided` | O | `by eye`, `loose copy` or `driver code` |
| reading | `glyph` | R | `[W, H]`, each 1..1024 |
| | `order` | O | `rows`, `strips`, `cols` or `bytecols` [`rows`] |
| | `stride` | O | integer bytes from one glyph to the next [the glyph's bytes in that order] |
| | `lsb`, `invert` | O | booleans [false] |
| | `gfx`, `bg`, `fg` | O | a `binscan.py --gfx` layout text (at most 2,000 characters), a pen, a list of pens; phase 2 |

Keys of each item kind, beside the common ones:

| Kind | Key | | Type and rule |
|---|---|---|---|
| `ks-grid` | `chars` | R | `ks-hangul`, `ks-nonhanja` or `ks-all` |
| | `grid` | R | `[L0, T0, PITCH]`: glyph index = (lead - L0) x PITCH + (trail - T0); each 0..255, PITCH 1..256 |
| `ks-dense` | `chars` | R | as above: glyph i is the i-th code of the set in KS order |
| `english` | `first` | O | the code of glyph 0, 0..255 [0] |
| | `count` | O | glyphs, 1..256, `first` + `count` <= 256 [256 - `first`] |
| | `top` | O | blank rows above an 8xH glyph in the 16-row cell, 0..15 [0] |
| | (`reading.glyph`) | | `[8, H]` with H 8..16, or `[16, 16]` (phase 2) |
| `raw-set` | `layout` | R | a `jamoset.py` raw layout name (`844`, `1044-san`, `621`, ...) |
| | `length` | R | integer bytes cut from `offset` |
| `compose` | `spec` | R | a compose spec object, `{"builtin": "spc1500"}` or `{"derive": "nkpspec"}`; phase 3 |
| | `syllables` | O | `ks` or `all` [`ks`] |

| Object | Key | | Type and rule |
|---|---|---|---|
| face | `name` | R | the face's file stem, as `maker/naming.py` accepts it (`[A-Z0-9_]{1,8}` for `svf/` names) |
| | `kind` | R | `precomposed` or `jamo` |
| | `route` | R | a route label of `routes.py` that the item's entry kind offers (`bdfface`, `bdfface + from-svf fit`, `dos raw`, `johab844`, `spec`, ...) |
| | `hangul` | R unless `from` | item id of the Hangul source |
| | `english` | O | item id of kind `english` (the `--ascii` BDF or the `--eng` companion) |
| | `from` | O | the name of an earlier face of this recipe that a fit reads (`--from-svf`) |
| | `layout` | O | for a jamo fit: `844` or `adaptive` [`844`] |
| expect item | `glyphs`, `sha256` | O | inked glyphs carved; the SHA-256 of the carved file the prep op wrote |
| expect face | `bytes`, `glyphs`, `ink` | O | the SVF's size, its glyph count, the ink of "안녕하세요 ABC 123" (`docs/recipes.md`, Checking a face) |

Rules that hold across objects: every id an item, a region or a face names exists; an item's reading must fit its
region (`offset` + the bytes its glyphs span <= the region's size, checked when the files are bound, not at load); the
bytes a `ks-grid` item reads are those of the highest code of its `chars`; a face's `hangul` item is of a kind its
`route` takes (`bdfface`: `ks-dense`, `ks-grid` or `compose`; `dos raw` / `johab844`: `raw-set`; `spec`: `compose`).
The 86Box example of 9.1 is a complete, valid recipe of the t_97acecf9 subset once its two hashes are filled in; its
commands are the ones of `docs/recipes.md` "Korean VGA font ROMs (86Box)": `rawcarve.py bdf FONT --glyph 16x16 --order
strips --chars ks-hangul --grid 0x80,0x80,128 --ascent 12`, `rawcarve.py bdf BIOS --offset 0x4a2d --glyph 8x16 --chars
ascii --ascent 12`, `bdfface.py --hangul H --ascii A --cell 16x16 --chars-from KS`, then `jamoset.py --layout 844
--from-svf FACE --mask-font none --check`.

## 10. Compose rules, and help from an assistant

A font with its own compose rule (NKP's 17 cropped piece sets and driver tables, the SPC-1500's 6 / 2 / 2 sets) cannot
be found by looking at glyph grids: the rule is in code. The design keeps the app honest about that:

- **In the app (phase 3)**: "load a compose spec" (a file or pasted JSON, or the built-in `spc1500`, or "derive with
  nkpspec" which runs `nkpspec.py find` / `spec` on the file and shows the table addresses it found). The spec is
  validated (`rawcarve.py compose --check-spec`: every set inside the file, strides and crops consistent, 21-entry
  tables) and then **inspected**, not edited: each piece set drawn as a strip at its place in the cell; a matrix of
  19 initials x 21 vowels without and with a final; the sample line; the jamo set's `--check` ("all 11,172 syllables
  identical to rawcarve.py compose"). The NKP lesson (a wrong crop draws a wrong face without an error) is why the
  set strips are shown with the cell outline.
- **Not in the app**: a table editor for compose rules (sets by vowel and final as an editable grid). It is a large UI
  for a handful of files, and whoever can fill it can write the JSON. Phase 4, only if asked for.
- **Export for an assistant**: writes `finder-<name>/` into the output folder: `PROMPT.md` (the prompt of
  `docs/recipes.md` filled in: the file's name, kind, size and hash, what the analysis found and what the user tried
  and marked, what is unresolved, and the exact form of the answer wanted: a compose spec or a recipe of schema 1);
  `session.json` (candidates and marks); `recipe-draft.json`; with "include renders" ticked, the PNGs of the
  candidates (derived bitmaps of the source: said so in the dialog, written nowhere else). The source file is named
  by path, not copied. The app contacts no one: the user takes the folder to Claude Code (or any assistant that can
  run the tools), and loads the returned spec or recipe with "load recipe or spec". The same export is the bug-report
  form for a file the finder does not resolve.

## 11. Internationalisation

The page is English only today. The finder brings a string table: `maker/static/strings.js` (`{en: {...}, ko:
{...}}`, `t(key, values)`), the language from `navigator.language` (`ko*` -> Korean) with a switch in the top bar kept
in `localStorage`. All finder strings go through it from the first commit; finder endpoints answer errors with a
stable `code` beside the English `error` text so the page can show its own sentence. Tool output (the `why` facts,
`--check` lines) stays as the tools print it. Moving the rest of the page onto the table is not part of this design
(section 15, 6). Docs: `docs/desktop-app.md` gets a chapter "Finding a font inside a file" and `docs/recipes.md` a
paragraph pointing from the prompt section to the app, each with its `.ko.md`.

## 12. Accessibility

- Everything works from the keyboard: the candidate list is a list of buttons; in the grid the arrow keys move the
  selection by glyph, `Shift` extends it, `Alt` + arrows move the offset by a byte (left / right) or a stored row
  (up / down), `PageUp` / `PageDown` by a page, `[` / `]` change the glyph width and `{` / `}` its height; every
  shortcut is also a labelled button, and the list is shown by `?`.
- The grid is a picture, so it has a text side: an `aria-label` that states the reading ("64 glyphs of 8x16 from
  0x39a0, rows"), a live `role="status"` line for the hovered or focused glyph (index, offset, and for a mapped mark
  its character), and "copy as text".
- No meaning by colour alone: marks carry their number in the overview strip and the grid; ink is drawn at full
  contrast in both themes; the scale control goes to 8 for low vision; focus is always visible and returns to the
  finder button when the view closes.
- Long work is announced: analysis progress and "not scanned" results through the same `role="status"` line pattern
  the page already uses for notices.

## 13. Tests

- **Synthetic fixtures** (`maker/test/finderfx.py`, bytes built in the test from the OFL faces of `svf/` and seeded
  noise, nothing proprietary): (1) a `.COM`-like file: noise, an 8x16 ASCII font, zero padding, an 8x4x4 set (the tie
  case); (2) a 2,350-glyph KS dense table inside a larger file, plain and inverted; (3) a 128-grid font in strips;
  (4) a four-file inverted piece-set region with a compose spec (SPC-1500-like; `tools/test_tiles.py` on `mame-roms`
  already builds such regions); (5) a `ROM_LOAD16_BYTE` pair of 4 bpp tiles with an outline pen and a non-zero
  background; (6) a packed file (zlib of the above); (7) hostile cases: over the caps, a symlink, a FIFO, a file
  truncated or rewritten during the session, zero length, a recipe with unknown keys, absurd numbers, a 10 MB gfx
  string.
- **Units**: candidate ranking; anchor solving (ASCII first code, dense start, grid origin; refusals when the anchor
  contradicts the reading); the recipe schema; the planner's argv against the command lines of `docs/recipes.md`.
- **Server**: every endpoint with and without the token; bounds before allocation; the analysis budget kills its
  tools (no process left in `tools.pids`); the 409 on a changed file; scratch removed on job end, delete and server
  stop; no source byte pattern of the fixture in `job.json`, the logs, the recipe or any error; nothing written
  outside the output folder; the no-network scan covers the new modules.
- **Equivalence**: app run == `recipe run` == the hand-run commands of `BUILD.md`, byte for byte, for each fixture;
  a saved recipe recognises the same fixture in a new job (`known`), a one-byte change makes it `similar`, a missing
  file `part of a set`.
- **Page** (`pagedrive.mjs`, Chrome): open fixture (1), the two expected candidates appear, pick, mark both, try (the
  sample line is drawn and equals the byte oracle), apply, run; fixture (5) through the region editor, pen view and
  pen rule; keyboard-only run of the same; every string key exists in `en` and `ko`, and `finder.js` holds no
  user-visible literal (a scan).
- **Desktop**: one step in `desktop/test/e2e.js` (open a fixture, apply a built-in test recipe, faces written); the
  frozen sidecar's smoke check runs `binscan`, `rawcarve`, `nkpspec` and `recipe list`.
- **Real files** (environment-gated, hashes checked, skipped here): `MAME_ROMS` as in `tools/test_tiles.py`, the 86Box
  ROMs, `SVF_MAKER_REAL_NKP`, `_DKB`: each built-in recipe reproduces the numbers `docs/recipes.md` records.
- **Performance** (recorded, not gated at first): the redraw and scan targets of 6 and 7.1 on fixture sizes 38 KiB,
  512 KiB and 8 MiB.

## 14. Phases

| Phase | Content | Needs |
|---|---|---|
| 0 | Tool changes of 7.5 for phase 1 (`--json`, coarse / fine `runs`); the recipe schema, validator and planner; `recipe check / run / list`; `sidecar` `TOOLS` | main only |
| 1 (MVP) | The finder view for **one file, 1 bpp**: analysis stages 0-2, candidates, viewer with every 1 bpp parameter, long-strip mode, anchors, marks `raw-set` / `english` 8xH / `ks-dense` / `ks-grid`, trial, apply, `carved-bdf` kind and routes, recipe save / load, the user library and detection states, string table EN + KO, keyboard and status lines, docs | phase 0 |
| 2 | ROM sets: region editor and suggestions, tiles panel (presets and pasted `gfx_layout`), pen view and rule, `ink`, English 16x16, zip members in place, compare with a loose file, KS-order score, the built-in recipes (with or instead of t_97acecf9's table) | `mame-roms` merged (t_c1eca08f) |
| 3 | Compose specs: load / built-in / `nkpspec` derive, `--check-spec`, the inspector, `carved-spec` kind and routes, export for an assistant | phase 2 |
| 4 (only if asked) | Compose table editor; pasted `ROM_LOAD` lines to a region; recogniser-assisted labelling of an unknown order (`SVF_RECOG_DIR`); executable unpackers | - |

Phase 1 alone covers the Dokkaebi drivers and the 86Box VGA ROMs end to end, and NKP's English font; phase 2 the MAME
quiz sets and X Se Dae; phase 3 NKP and the SPC-1500.

## 15. Decisions (user, 2026-11-23)

The ten questions this design left to the owner were all answered "as recommended" on 2026-11-23. None is open.

| # | Question | Decision |
|---|---|---|
| 1 | Who renders the live grid (7.1) | The sidecar, in-process, as a 1-pixel-a-pixel PNG; the page draws only the overlay. No JS decoder |
| 2 | When the output folder is chosen (7.2) | First: a finder session belongs to a local job, and its scratch is in that job's folder inside the output folder |
| 3 | t_97acecf9's known ROMs (9.3) | Built-in recipes now: that card stores its table in schema version 1 (the subset of 9.4) under `maker/recipes/`, starting with the 86Box ROMs |
| 4 | What a built-in recipe may carry | Names, sizes, SHA-256 / SHA-1 and offsets of proprietary files; never a byte of them |
| 5 | Compose rules in the app (10) | Inspect only: a spec by file, paste, built-in or `nkpspec`; no table editor |
| 6 | Korean and English strings (11) | A string table for the finder only; the rest of the page stays English until its own card |
| 7 | Renders in the export for an assistant (10) | Allowed, opt-in, off by default, written only into the output folder |
| 8 | The first delivery (14) | Phase 1 as written: one file, 1 bpp |
| 9 | Archives | Zip members are read in place from phase 2, through `archive.py`'s guards; no other archive kind is opened |
| 10 | Default limits (7.4) | Kept: analysis 60 s (300 s on request), a file 64 MiB, 16 files a session |

The alternatives that were not taken, for the record: decoding raw windows in the page (faster to scrub, but a second
decoder and gfx parser); choosing the output folder only at "apply" (needs in-memory regions or a second scratch
rule); converting t_97acecf9's table in finder phase 2 (two planners for a while); a compose table editor (phase 4,
only if asked).

## 16. Not verified, and risks

- The redraw targets (7.1) and the coarse / fine `runs` cost (6) are estimates from the one measurement of 4.3; the
  fine pass does not exist yet. If pure Python misses the tile target, the fallback is the ink map of 7.1, not a new
  dependency.
- The KS-order score (6, stage 4) is an idea, not a measured method; it ships as a hint or not at all.
- The coarse `runs` pass assumes a row-aligned misread still looks glyph-like; true for `rows`, to be checked for
  `strips`, `cols` and `bytecols`, where the fine pass may need more phases.
- `mame-roms` and main have diverged (4.2); phases 2 and 3 are written against `mame-roms` at `55c0be1` and must be
  re-read after its merge.
- Nothing here was run in the app: this is a design. The wireframe is a layout proposal, not a tested one; the
  narrowest supported window of the desktop app has to fit it (the right column folds under the viewer below that).
