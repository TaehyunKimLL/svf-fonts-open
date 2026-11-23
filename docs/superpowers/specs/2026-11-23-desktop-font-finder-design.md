# Desktop font finder: fonts hidden in programs, data files and ROMs (design)

Card t_235403fe: "desktop app: font finder for unknown programs/ROMs (binscan/rawcarve interactive) - design". Written
2026-11-23 on branch `finder-design` of `svf-fonts-open` (base `5dbf399`), for a builder who has not seen the
repository. This is a design only: no code is changed by this card, and no implementation card is created before the
owner has approved it. Facts below were read from the tree (main, and branch `mame-roms` at `55c0be1` where said) or
run on this host; what was not run says "not verified" or "target". Where a choice is the owner's I decided for the
builder, marked "(design call)". The owner answered the ten questions of the first draft on 2026-11-23, every one as
recommended (section 15). Revised the same day after two rounds of two independent reviews; section 17 lists every
finding and what was done with it, and section 15.1 the points where a finding touches a decision. Card t_97acecf9
implemented the recipe subset meanwhile (`maker/recipe.py`, `maker/recipes/` on branch `desktop-export`, read at `9be5fc7` and again at `a103f56`);
sections 8 and 9 describe that code where it exists and say what the finder adds (9.5).

Read with this document: `docs/recipes.md` "Finding a font inside a program or data file, with Claude" (the prompt, the
byte-size signatures, the NKP / Dokkaebi / 86Box examples) and, on `mame-roms`, "Korean font ROMs in MAME sets";
`tools/binscan.py`, `tools/rawcarve.py`, `tools/nkpspec.py` (on `mame-roms`: `--invert`, `--gfx`, `--bg` / `--fg`,
`rawcarve.py region` / `ink`, `eng --first / --count / --width / --invert`, `jamoset.py --layout spec`);
`maker/README.md`, `docs/desktop-app.md`, `maker/server.py` (`_ROUTES`, `_sweep_idle`, `_kept_settings`),
`maker/detect.py` (entries, `prep` ops, companions), `maker/settings.py` (`plan_steps`, `companion_file`),
`maker/routes.py` (`source_commands`), `maker/jobs.py` (`_finish_local`), `maker/sources.py`, `maker/preview.py`,
`maker/zipout.py` (`_OutputTree`), `maker/static/maker.js` / `svfview.js`, `desktop/main.js`; the designs
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
  a raw 8x4x4 (or other known-size) jamo set, an 8xH / 16x16 English font, a dense KS X 1001 syllable dump, a KS code
  grid, 1 bpp in any stored order, inverted, multi-bit tiles with a pen rule, a region interleaved from several ROM
  files, and a font with its own compose rule given as a `rawcarve.py compose` spec.
- Every pixel rule stays in the Python tools. The finder adds no decoder and no composer of its own: the page draws what
  the sidecar decoded (candidate grids) or what the WASM renderer draws from a built face (results).
- What the viewer shows is what the conversion reads: every parameter of a reading reaches the carve commands
  (section 8.2), and a test compares converted pixels with independently built glyphs.
- Local mode only: files are read where they are, never uploaded or copied into the data directory; derived files live
  in the job's `.svf-maker-<id>/` inside the output folder and go when the job ends.
- The input is untrusted and is never executed, unpacked by an external program or parsed beyond bounded byte reads.
- A run is reproducible by hand: `BUILD.md` lists the `rawcarve.py` / `jamoset.py` / `bdfface.py` commands, and the
  recipe JSON and every parameter file a command names are written beside it.
- A recipe library (built-in and the user's) recognises known files by size and hash at detection; the known ROMs of
  card t_97acecf9 are built-in recipes.
- The proofs run on synthetic fixtures; checks on real files are environment-gated.

## 3. Non-goals

- Disassembly, emulation or any execution of the file; unpacking LZEXE / PKLITE / ARJ / RAR / 7z / LHA (the finder
  names them and says "unpack first"). Reading a driver's code stays with a person or an assistant; section 10 says
  how the app hands that over.
- An automatic answer. The finder ranks and draws; the user decides. Where the bytes cannot decide (tied `sets`
  offsets, a KS order with gaps), it says so.
- A JavaScript or WASM port of `binscan.py` / `rawcarve.py` (owner, 2026-11-05: the Python tools stay).
- New glyph layouts in the tools beyond what `mame-roms` has. Not read, and said so by the viewer's help: rows stored
  bottom-up, rotated or transposed glyphs, rows packed without byte padding (a 12-bit row in 1.5 bytes), 16-bit word
  swap of a single file in phase 1 (`region --swap` does it from phase 2).
- Character sets other than ASCII 0x20..0x7E and KS X 1001: JIS X 0208, Big5, GB 2312, CP437 above 0x7E. A 94 x 94
  table of 8,836 glyphs has one size whatever its set; the signature line says "94 x 94 table (KS X 1001 or another
  set: look)". A KS font in an order of its own (quizdaisk) is not resolved either. Faces of the KS symbols and Hanja
  (`ks-nonhanja`, `ks-all`) are not built in version 1 (section 8.3).
- Compressed font formats. The repository's own (`os2dbcs.py`, the Mac JM archive) keep their routes; the finder does
  not decompress, and a file it sees as packed is told so.
- Upload mode. The finder is offered only when `/api/caps` says `local`.
- A network feature of any kind: no recipe download, no call to an assistant's API.

## 4. Constraints and facts

1. **The tools on main.** `binscan.py`: `info` (kind from the first 0x60 bytes: MZ with LZEXE / PKLITE marks, ARJ,
   ZIP, option ROM, `.COM`; nothing for RAR, 7z, gzip, xz or LHA; entropy per block; size signatures), `runs`, `sets`,
   `ascii`, `render` (text, or a PNG with a 1-pixel gap between cells, written by its own zlib level 9 writer; no
   Pillow). `rawcarve.py`: `cut` (bytes as they are), `eng` (`--offset`, `--height`, `--top` only), `bdf` (`--glyph`,
   `--stride`, `--order`, `--lsb`, `--first`, `--count`, `--dense` / `--grid`; `--chars ascii` keeps codes 0x20..0x7E),
   `compose`. No `--invert` anywhere. All print text; all open files with a plain `open()`; `nkpspec.py` reads the
   whole file without a cap.
2. **The tools on `mame-roms`** (card t_c1eca08f; not on main, and main has `svf2ttf.py` since the fork): `--invert` on
   `binscan.py` and on `rawcarve.py eng / bdf / ink / compose`; `rawcarve.py ink` (any 1 bpp reading, or tiles by a pen
   rule, rewritten as plain row-major MSB-first 1 bpp glyphs; takes `--glyph`, `--stride`, `--order`, `--lsb`,
   `--invert`, `--gfx`, `--bg` / `--fg`, `--offset`, `--count`); `eng --first / --count / --width 16 / --invert`;
   `region` (`--unit 1|2|4`, `--swap`); `--gfx` layouts parsed with bounds; the built-in spec `spc1500`; `jamoset.py
   --layout spec` and a 16x16 `--eng` file of 8,192 bytes (main's `read_eng` refuses that size; `johab844.py` reads
   8x16 only). Caps: `binscan.MAX_SCAN` 16 MiB a scan, `rawcarve.MAX_FILE` and `MAX_REGION` 64 MiB.
   **The finder is built on `mame-roms` merged into main**: without `--invert`, `ink` and the `eng` options the viewer
   could show readings no command can carve.
3. **Scan cost (measured here, pure Python, one core).** On a 524,288-byte synthetic file: `info` 0.03 s, `ascii`
   0.06 s, `sets` 0.11 s, `runs --glyph 16x16` with its default of one phase a row 9.65 s, `runs --order strips --step
   32` (one phase) 0.63 s; `render` of 256 glyphs to a PNG 0.06 s including the interpreter start. `runs` is the cost:
   about 1.2 s a MiB a phase at 16x16 (the fixture is all glyphs: a worst case), and 8x8 decodes four times as many
   glyphs a MiB. Every geometry at every phase of a 16 MiB window is several minutes; the analysis therefore runs in
   a priority order inside a budget and says what it did not scan (section 6).
4. **Detection.** `detect.py` `sniff` returns `fon` for any file that starts with `MZ` (a DOS `.EXE` driver becomes an
   entry of kind `other` labelled "Windows FON; no openable face"), `archive` for zip / tar / xz, `hwp-pft` for a
   `.PFT` no tool reads, and decides `dos-raw`, `eng` and `ks-raw` by byte size alone (`DOS_SIZES`, the sizes 2,048 /
   4,096 / 12,288 / 30,720 / 49,152, the KS dump sizes): a ROM of 4,096 bytes is "a Latin companion". Only what is
   left is `unknown`. A `POST detect` replaces `job["fonts"]` wholesale and keeps settings by the key `(root path,
   path, face_index)` (`_kept_settings`).
5. **Planning and companions.** A font entry has one `(root, path)`; `routes.source_commands` chains its `prep` ops
   from that one file. `settings.plan_steps` gives a companion a source step of its own only for `mac-fbit3`
   (`companion_file`); every other companion is passed by its original path (`settings.py` line 1563, `server.py`
   `_companion_abs`). `detect.py` pairs an `eng` entry only with `dos-raw`, `hwp1` and `ks-raw` fonts of the same
   folder, and a `bdf-ksc5601` font only with BDF / HBF entries; `bdfface` refuses to run without a Latin companion.
   `_bdfface_fit_commands` does not pass `--mask-font none`, and `jamoset.py` then takes `$JAMOSET_MASK_FONT` or a
   sibling NotoSansKR when one exists. Detection runs `srcprep.prepared_bytes` in-process on entries with `prep`.
   Every command line of a note is at most `naming.MAX_FIELD_BYTES` = 512 bytes (`_check_notes` refuses the run
   otherwise).
6. **Files directory.** `.svf-maker-<id>/` is swept when a `detected` local job is idle for 30 minutes
   (`_sweep_idle`, which holds the fonts' preview locks only), unconditionally when a run finishes (`_finish_local`),
   at job delete and at start and stop. `Worker.stop()` kills the children of `preview.run_bounded` (`kill_all`).
   `PUT settings` and `POST run` need the job in state `detected`.
7. **The page and the shell.** One page, English only, no string table. `test_page_js_tables_match_python` holds
   `maker.js`'s tables (`ROUTES`, `OPTION_VISIBLE`, `PREVIEW_KINDS`, `SOURCE_WORDS`, ...) equal to Python's. The shell's
   session is `session.fromPartition('maker')` without `persist:` (its `localStorage` does not survive a quit) and
   denies every permission (`navigator.clipboard` included). The bridge is four functions; there is no save dialog.
   Byte-serving GETs are host-checked (`_HOST_CHECKED`) and a local job's are `Cache-Control: no-store`.
8. **Packaging.** `sidecar.spec` bundles `maker/static` only; `build-sidecar.sh` stages `svf/`, three `web/` files,
   `tools/*.py` and `maker/*.py`. `binscan` and `rawcarve` are in the sidecar's module graph, not in its `TOOLS`
   table; `test_frozen.py` holds `GRAPH_MODULES` / `TOOLS` / `SMOKE` in step. The sidecar has Pillow and fontTools, no
   numpy.
9. **`maker/archive.py` extracts** (guarded: member and total size, ratio, count, names, nested archives) into a
   destination; it has no reader of a member in place, and `binscan.py` / `rawcarve.py` take file paths.
10. **The examples' facts the UI must cover**: tied `sets` offsets a row apart (Dokkaebi: decided by source or a loose
    copy); a `.COM` loads at 0x100; a wrong compose spec draws a wrong face without an error (NKP); a KS table at a
    sprite index inside a larger tile ROM (Date Quiz Go Go: sprite 13347); an outline pen (Quiz KOF: `--fg 1`); a
    background pen that is not 0 (X Se Dae: `--bg 15`); 가 at slot 0x1821 = 6177 of the VGA ROMs' 128 x 128 grid.

## 5. The user flow

1. **Enter.** The finder opens on entries of a detected local job, so its files are already checked sources of the job
   (the sources panel's "find a font in a file..." is "choose files" + "detect" + open the finder on what was picked).
   Two ways in from the fonts table:
   - **look inside** (KO "안쪽 살펴보기") on every readable single-file entry that has no route: kind `other`
     (`unknown`, an `MZ` file with no openable face, `hwp-pft`, a lone `eng`; from phase 2 a zip archive), and an FNT
     or FON face with no openable size (`detect.py` gives that one the kind `bitmap` with an empty size list, so the
     rule is `source_kind == "other"` or `format in ("fnt", "fon")` with no sizes). Not on licence texts, list files
     and unreadable files. Several such entries can be ticked and opened together.
   - **open in the finder** in the row menu of every other single-file entry whose kind was decided by size alone
     (`dos-raw`, `eng`, `ks-raw`): a ROM that happens to be 4,096 bytes long is not lost to its misreading.
2. **Known file.** If the library holds a recipe whose files match (section 9), detection already shows the entry as
   `known: <recipe title>` with the recipe's faces as routes; the finder is not needed, and opens prefilled when the
   user wants to look.
3. **Analyse.** The finder starts the analysis (section 6): facts at once (size, kind, signatures, entropy map), scans
   as they finish, in priority order within the budget. A packed file (entropy near 8 everywhere, or an LZEXE / PKLITE
   / ARJ / RAR / 7z / gzip / xz / LHA mark) is said to be packed and offered the manual viewer only.
4. **Candidates.** A ranked list; each row has a thumbnail (the first 32 glyphs), the facts that made it a candidate
   and a proposed meaning ("8x4x4 set, 16 px", "8x16 English", "2,350 glyphs: KS dense?"). Tied offsets are one row
   with every tie drawn side by side.
5. **Look and adjust.** Picking a candidate (or any place on the overview strip) loads the viewer. Every parameter
   redraws at once: offset, glyph WxH, stride, order (rows / strips / cols / bytecols), lsb, invert; from phase 2 the
   gfx layout, the pen view and the pen rule, and the region (which files, interleave unit, swap).
6. **Mark.** The user selects a span of glyphs and says what it is (section 5.3). An **anchor** (section 5.4) makes the
   mapping without arithmetic: click a glyph, type its character ("가", "A").
7. **Trial.** "Try" plans the marks exactly as a run would (section 8) and builds their faces in the scratch; the page
   polls, can cancel, and shows the sample line through the WASM renderer with the numbers of `docs/recipes.md`
   "Checking a face": glyph count, `--check` result, `svfline.py measure`, the ink (section 8.5), the fit IoU.
8. **Apply.** The marks become font entries of the job (section 8). From here it is the usual maker: settings, run,
   steps table, faces in `svf/<dest>/`, `BUILD.md`.
9. **Save the recipe.** Written into `build-<id>/` on every run; "save to my recipes" adds it to the user library.

A session may hold several files; each is a region of its own. Phase 1 has no assembled region (one mark reads one
file as it is), so the 86Box pair (the font ROM for Hangul, the VGA BIOS for English) is two files in one phase-1
session.

### 5.1 The finder view (wireframe)

The finder replaces the main layout while it is open (the top bar stays; "back to the job" returns).

    +-- SVF maker ------------------------------------------ [finder: NKP.COM]  [back to the job] ---+
    | FILES / REGION     | VIEWER                                             | READING             |
    | (a) NKP.COM        | overview: [entropy+ink strip of the region, a    ] | offset  [0x39a0 ] +- |
    |   38,184 B  .COM   |           [marker at the offset, marks numbered  ] | address 0x3aa0 (.COM)|
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
- **Grid**: the server's PNG is **gapless, one pixel a glyph pixel, glyphs `cols` a row** (a new helper, 7.5: the gap
  and the scale of `binscan.py render --png` are not used); the page scales it with `image-rendering: pixelated` and
  draws the cell lines, index labels, hover and selection itself (it knows the geometry). "Show as text" puts
  `binscan.py render`'s `#` / `.` form of the selection into a read-only text box with its content selected; the user
  copies it with the system's own copy (the shell denies `navigator.clipboard`; no permission is added).
- **Long-strip mode** (the recipe's "draw long strips when nothing lines up"): one toggle sets the glyph to W x 512,
  16 columns, at most 16 glyphs (a 16 x 512 strip set is 256 x 512 pixels; the count is clamped so that no side
  passes `preview.MAX_CANVAS`); clicking two rows sets the glyph height from their distance.
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

| Mark | Parameters | Recipe item (9.4) | Faces it can give (routes) |
|---|---|---|---|
| raw jamo set | a `jamoset.py` raw layout and its length; the reading the layout allows (8.2) | `raw-set` | `dos raw` (jamo); `johab844` (precomposed, a 16 px 8x4x4 set of 11,520 bytes) |
| English 8xH | H 8..16, top, first code, count | `english` | the English of other marks' faces; several English marks of one glyph width can be joined (digits and letters kept apart in a ROM) |
| English 16x16 (phase 2) | first, count | `english` | as above, for `dos raw`, `spec` and `bdfface`; not for `johab844` |
| KS dense | 2,350 syllables in KS order from a start glyph | `ks-dense` | `bdfface` (precomposed), `bdfface + from-svf fit` (jamo) |
| KS grid | `L0,T0,PITCH` (presets: 94 x 94 `0xA1,0xA1,94`; VGA ROM `0x80,0x80,128`) | `ks-grid` | as above |
| compose spec (phase 3; the built-in `spc1500` exists) | a spec (inline, built-in, or derived by `nkpspec`), syllables `ks` / `all` | `compose` | `spec` (jamo, native, exact), `bdfface` (precomposed), `bdfface + from-svf fit` |

Every mark carries the reading it was made with and an ascent (default the tools': 7/8 of the height, rounded up; the
recipes' `--ascent 12` for VGA ROMs is a field of the mark).

### 5.4 Anchors

`POST .../anchor` takes the reading, the mark kind and one or more `(glyph index, character)` pairs, and answers the
solved parameters or 422 with a `code`:

- **English**: `first` = code - glyph index; 422 `anchor.range` when that is not 0..255. More anchors must agree.
- **KS dense**: the start glyph = glyph index - (the character's place in KS order); 422 when negative or when the
  2,350 glyphs then pass the region's end.
- **KS grid**: the mapping is `index = (lead - L0) x PITCH + (trail - T0)`, so one anchor fixes it only when `PITCH` is
  known. The request must give `pitch` (a preset or a typed number), **or** two anchors on different lead bytes, from
  which `PITCH = (index2 - index1 - (trail2 - trail1)) / (lead2 - lead1)` must be a whole number of at least 94 (422
  `anchor.pitch` otherwise). With `PITCH`, `K = lead x PITCH + trail - index` and the answer is the one `(L0, T0)` with
  `L0 x PITCH + T0 = K` whose `T0` puts every trail byte 0xA1..0xFE inside `T0 .. T0 + PITCH - 1` (what `rawcarve.py bdf
  --grid` demands); 422 `anchor.no_grid` when there is none. Every further anchor is checked against the answer (422
  `anchor.conflict`, naming the pair). Example: reading 16x16 strips at offset 0, `pitch` 128, glyph 6177 = "가"
  (B0A1) gives `K` = 0xB0 x 128 + 0xA1 - 6177 = 16,512 and the grid `[0x80, 0x80, 128]`.
- The page says after one anchor of a grid "one more character on another row confirms it", and draws the characters
  the solved mapping expects under the next 16 glyphs so a wrong mapping is seen at once.

## 6. Automatic analysis

The analysis is a job of the finder session with a total budget (default 60 s; "analyse again" offers 300 s, a window,
or one named scan) and a budget a scan (20 s); every scan is a `binscan.py` subprocess through the bounded runner of
7.2, killed on cancel, on timeout and when the session closes. Results arrive as they finish. Scans run in the
priority order below until the budget is spent; what was not reached, or timed out, is listed as "not scanned: <what>"
with a button to run it alone, never as "nothing found".

- **Stage 0, at once (in-process, bounded reads).** Size, `kind_of`, size signatures, the entropy map (streamed, a
  block at a time), the library match (section 9).
- **Stage 1, cheap scans over the whole region.** `ascii` at heights 16, 14 and 8, plain and inverted; `sets` for
  8,4,4 at 16x16 and 24x24, plain and inverted (and the other set counts the tools know). No block is left out: these
  scans cost about 0.2 s a MiB (4.3), and a set's blank fill slots, or the blank rows of a sparse grid, lie in blocks
  of one byte value. A region larger than `binscan.MAX_SCAN` (16 MiB) is scanned in windows of at most that size
  (`--start` / `--length`), each **overlapping the next by the scan's whole candidate span minus one byte**: for
  `sets` the bytes of the whole set (11,520 for 8x4x4 at 16 px, 25,920 at 24 px), for `ascii` 256 x H bytes, for
  `runs` (stage 2) one glyph. A run cut by a window edge may be shorter than `--min` on both sides and would be
  dropped before it could be joined, so a windowed `runs` also reports the unfinished runs that touch its window's
  first or last glyph, whatever their length, marked as such (in `--json`; 7.5); the analysis joins fragments of one
  phase that meet, and only then applies `--min` and the choice among overlapping runs. Offsets are
  absolute (the tools print `--start` + offset), and a candidate found in two windows is kept once.
- **Stage 2, `runs`, coarse then fine**, in this order: 16x16 rows, 16x16 strips, 8x16, 24x24 rows, 8x8.
  - **Windows.** Only blocks at 7.5 bits or more are left out, and only of `runs`; blocks of one byte value stay (a
    run counts blank glyphs, and a 128 x 128 KS grid is mostly blank between its rows). A window is widened by one
    glyph on each side, and windows less than 64 KiB apart are joined. Results of overlapping windows are deduplicated
    by offset and reading.
  - **Coarse phases**: one a byte of a stored row, `range(ceil(W / 8))`: 0 for 8-wide glyphs, 0 and 1 for 16, 0 to 2
    for 24 (a read shifted by whole rows still looks like glyphs; a read shifted inside a row does not). For `strips`,
    `cols` and `bytecols` the right coarse set is not known: the builder measures it on the fixtures, and until then
    those orders run every phase on windows of at most 1 MiB.
  - **Fine**: all phases, only around the runs the coarse pass found.
  - **Cost** from 4.3: a coarse pass is about 1.2 s a MiB a phase at 16x16 on the worst case, so 16x16 rows on 8 MiB
    is about 20 s: one scan's budget. The default 60 s therefore reaches the first geometries on a large region and
    all of them on a file of a few hundred KiB; that is the stated behaviour, not a failure (not verified beyond 4.3).
- **Stage 3, tiles (phase 2).** When a region is larger than 256 KiB and stage 2 found no long 1 bpp run, `runs` with
  the packed presets (`16x16x4` lsb / msb, `8x8x4`) at one phase.
- **Stage 4, meaning.** A run of 2,350 or more 16x16 or 24x24 glyphs gets a **KS-order score** (phase 2, experimental):
  in KS X 1001 order the initial consonant changes at known glyph indices (가 .. 깊 share ㄱ, then ㄲ, ...); the score
  is how well the breaks in top-left-quadrant similarity between consecutive glyphs line up with those indices, tried
  at every start within the run. A good score proposes "KS dense, 가 at glyph N". It is a hint, shown as a hint; the
  anchor is the user's answer.

**Ranking** (highest first): a library recipe match; a file whose size is a signature; a single `sets` hit; an `ascii`
hit with a low edge count; runs by inked glyph count (KS-order score first when present); tied `sets` offsets; near
matches. Every row says why it is there, in the tools' own numbers (seam, edge, inked count): numbers and fixed words
only, never bytes of the file.

## 7. Where computation runs, and the API

### 7.1 Decision: the sidecar decodes, the page draws

| Work | Where | Why |
|---|---|---|
| Live grid render | sidecar, **in-process** (`binscan.decode` on a bounded window, a gapless PNG) | no port of the decoder (non-goal); a process start a redraw is too slow for a slider. The decode is arithmetic on a byte window, the same class of in-process reading `detect.py` already does |
| Scans, region assembly, ink maps, carving, trial and final builds | sidecar, **subprocess** tools with a time budget | long, killable, the same argv `BUILD.md` prints |
| Result preview (trial and built faces) | page, the WASM renderer (`svfview.js`) | as every other preview of the maker |
| Grid overlay, selection, anchors, recipe form | page | no pixel rule involved |

Redraw target: under 100 ms for a 256-glyph 1 bpp grid, under 300 ms for 256 tiles of a gfx layout (not verified;
the page debounces 30 ms, numbers its requests and drops answers that are not the latest; the server renders at most
two requests at a time and answers 429 to more). If the gfx target is missed, the tile view is drawn from the
session's ink map (`rawcarve.py ink`, written once a pen rule) instead.

### 7.2 Session, files and scratch

**Session.** A finder session belongs to a local job in state `detected` and is made from entries of that job
(`{"fonts": ["f3", "f4"]}`), so every file is already one of the job's checked sources and resolves through
`Sources.abs_of`; the endpoint takes no path. The font ids of the request are only how the page names the entries:
`detect` numbers entries in scan order, so an id means another file after a file is added or removed. The session
stores each file by a **stable identity**, `{root path, relative path, member}` (the key `_kept_settings` uses, plus
the zip member of 7.6), under a session file id of its own (`a`, `b`, ...); every later request resolves that
identity against the job's current roots, and a `POST detect` or a change of sources re-resolves it: a file that is
still among the sources stays bound whatever its font id or root index now is, a file that left is marked missing
(its marks are kept, not applied, and say why). `job.json` gets `finders: {n1: {...}}`: those identities, sizes,
hashes, regions, candidates (numbers only: no thumbnail, no bytes), marks, and which marks are applied.

**Opening a file.** Every in-process read opens with `os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK`, requires
`S_ISREG` of `os.fstat(fd)` and compares `(st_dev, st_ino, st_size, st_mtime_ns)` of that descriptor with the values
taken when the session opened the file (the pattern of `bdfface.open_regular`); a difference answers 409 "the file
changed: open it again". Bytes are read with `os.pread` of a bounded length: **a user's file is never `mmap`ed** (a
truncation under a mapping is a SIGBUS that would take the sidecar down). A gfx layout whose planes span the whole
region is rendered from a bounded whole read (at most 64 MiB, one region held at a time for a session) or from the
ink map. SHA-256 is computed once in the background through the same descriptor rule; `apply`, `trial`, `GET recipe`,
`export` and "save" need the hashes of the files their marks read and wait for them (the page shows "hashing"; a
request that would wait past its timeout answers 409 `finder.hashing`).

**Scratch** is `.svf-maker-<id>/finder/<n>/` in the output folder: assembled regions, extracted zip members, ink
maps, trial work. It is **disposable**: everything in it can be written again from `job.json` and the sources, and
each use goes through one `ensure(...)` step under the session's lock. That is what makes the sweeps of 4.6 safe:

- every finder request touches `server.touched[job]`; a job with a running finder tool is skipped by `_sweep_idle`,
  and `_sweep_locks` takes the job's finder session locks with the preview locks;
- a sweep of an idle job, and the sweep after a run (`_finish_local`), remove the scratch; the session stays in
  `job.json`, and its next request rebuilds what it needs (the page shows "preparing" meanwhile);
- `POST run` and `PUT settings` answer 409 `finder.busy` while a finder tool of the job runs (cancel it or wait);
  a finder request answers 409 while a run is queued or running;
- finder tools run through one bounded runner that registers each child in `preview`'s live table and in `toolreg`, so
  `preview.kill_all()` at `Worker.stop()`, job delete and session delete stop them, and the next start reaps any
  that outlived a killed sidecar.

### 7.3 Endpoints

The `/api/jobs/<id>/finder...` endpoints need the token and a local job. `/api/recipes...` and `/api/prefs` belong to
no job: they need local mode and the token (403 otherwise), nothing else. Errors are JSON with the English `error`
and a stable `code`. The GETs that serve bytes (`map`, `render`, `trial/<face>.svf`) are in `_HOST_CHECKED` and
answer `Cache-Control: no-store`.

    POST   /api/jobs/<id>/finder                  {"fonts": ["f3", "f4"]}                       -> {"finder": "n1"}
    GET    /api/jobs/<id>/finder/<n>              files, regions, analysis and trial progress, candidates, marks, match
    DELETE /api/jobs/<id>/finder/<n>              stops its tools, removes its scratch, un-applies its marks
    PUT    /api/jobs/<id>/finder/<n>/regions      [{"id": "r1", "groups": [["a","b"],["c","d"]], "unit": 1, "swap": false}]
    POST   /api/jobs/<id>/finder/<n>/analyse      {"region": "r1", "budget_s": 60, "start": 0, "length": null, "scan": null}
    POST   /api/jobs/<id>/finder/<n>/cancel       the running analysis or trial
    GET    /api/jobs/<id>/finder/<n>/map?region=  the overview strip (PNG, one column a block)
    GET    /api/jobs/<id>/finder/<n>/render?region=&offset=&glyph=16x16&stride=&order=&lsb=&invert=&gfx=&bg=&fg=
                                                   &count=&cols=&view=ink|pens|text      -> image/png (or text/plain)
    POST   /api/jobs/<id>/finder/<n>/anchor       {"reading": {...}, "offset": 0, "as": "ks-grid", "pitch": 128,
                                                   "anchors": [{"glyph": 6177, "char": "가"}]}
                                                   -> {"grid": [128, 128, 128]} (section 5.4) or 422
    PUT    /api/jobs/<id>/finder/<n>/marks        the whole list of marks (section 9.4 `items`) and face pairings
    POST   /api/jobs/<id>/finder/<n>/trial        starts the trial build (202); its state and numbers are in the GET above
    GET    /api/jobs/<id>/finder/<n>/trial/<face>.svf
    POST   /api/jobs/<id>/finder/<n>/apply        the marks become font entries of the job (section 8) -> the job
    GET    /api/jobs/<id>/finder/<n>/recipe       the recipe of the current marks
    PUT    /api/jobs/<id>/finder/<n>/recipe       load a recipe or a compose spec (validated; prefills regions and marks)
    POST   /api/jobs/<id>/finder/<n>/export       {"what": "recipe" | "prompt", "renders": false} -> a path in the output folder
    GET    /api/recipes                           the library: built-in and the user's (id, title, files' names and sizes)
    PUT    /api/recipes/<rid>                     save a recipe to the user library
    DELETE /api/recipes/<rid>                     a user recipe only
    GET    /api/prefs   PUT /api/prefs            {"lang": "en" | "ko"} in <data root>/prefs.json (section 11)

`render` answers with the PNG and the headers `X-Finder-Count` (glyphs really drawn before the region ends) and
`X-Finder-Pens` (the pens present, for the legend). A candidate is `{id, region, kind, offset, reading, count, score,
why, ties, suggest}`; `reading` is the same object a mark and the `render` query carry. `<rid>` must match the id
rule of 9.4 and equal the recipe's `id`; the file is `<data root>/recipes/<rid>.json`, written through a temporary file
in that folder and `os.replace`, never through a path taken from the request; a built-in id is refused; the user
library holds at most 500 recipes. `PUT /api/prefs` takes a body of at most 1 KiB that is exactly `{"lang": "en"}` or
`{"lang": "ko"}` (any other key or value is 400) and writes `prefs.json` the same way (a temporary file in the data
root, then `os.replace`); `GET` answers `{"lang": null}` when the file is absent or does not validate.

### 7.4 Limits and untrusted input

| Limit | Value | Source |
|---|---|---|
| files a session | 16 | (design call; `MAX_SOURCE_PATHS` is 64) |
| a file | 64 MiB | `rawcarve.MAX_FILE` (the maker's 256 MiB local cap is higher; the finder refuses earlier, with the reason) |
| an assembled region | 64 MiB counted from the bound files' sizes before anything is written, and free space in the output folder checked first | `rawcarve.MAX_REGION`, `LOCAL_FREE_MIN` |
| a scan window | 16 MiB | `binscan.MAX_SCAN` |
| a render | 4,096 glyphs, glyph sides 1..1024, 64 columns, canvas within `preview.MAX_CANVAS` / `MAX_PIXELS`, two at a time | `binscan.py render`, `preview.py` |
| analysis | 60 s total, 20 s a scan by default; 300 s at most | (design call) |
| trial build | 60 s a tool, 300 s in all, cancellable | `preview.TIMEOUT_S` |
| sessions a job, candidates a session, marks | 8, 200, 64 | (design call) |
| a recipe or spec loaded | 256 KiB of JSON, 16 files, 64 items, 16 faces, 64 piece sets a compose spec | (design call) |
| user recipes | 500 | (design call) |

- **Never executed**: no code path starts the file, an emulator, a disassembler or an unpacker.
- **Archives**: named, not opened, except a zip from phase 2 (section 7.6).
- **Bounded reads**: the in-process render reads `count x stride` bytes plus one glyph footprint by `pread`. Every
  number of a request is range-checked before any allocation; a gfx string goes through `binscan.parse_gfx` only.
- **The tools** get the same opening rule (7.5), because a subprocess is handed a path: a FIFO or a link swapped in
  after the server's check must fail in the tool, not hang it until the timeout.
- **A recipe is untrusted too**: it carries parameters, never a command, a path or a tool name outside the fixed set;
  the server builds every argv itself. File names in a recipe are labels: files are bound by the user's pick and
  matched by size and hash. Face names and `dest` go through `maker/naming.py`.
- **Writing**: everything the finder writes into the output folder (scratch, `build-<id>/`, an export) goes through
  `zipout._OutputTree` (descriptors under the verified folder, `O_NOFOLLOW`, the folder re-proved before each landing).
- **Privacy**: no byte of a source file in `job.json`, the logs, a recipe or an error text (`binscan.py --json` gives
  numbers and fixed words; a test greps for the fixture's bytes); renders are served to the page of the same launch
  only, `no-store`, and are never written outside the scratch (the prompt bundle of section 10 is the one opt-in
  exception, into the output folder).
- **Local only**: nothing new listens or connects; the existing no-network tests are extended to the new modules.

### 7.5 Tool and packaging changes the finder needs (each with its own tests)

Before phase 0: `mame-roms` merged into main (4.2). Then:

| Where | Change | Phase |
|---|---|---|
| `binscan.py` | `--json` on `info`, `runs`, `sets`, `ascii` (numbers and fixed words, one object) | 0 |
| | `runs --phases a,b,...` and `--around OFFSET,LENGTH` (the coarse and fine passes of section 6); with `--start` / `--length`, the unfinished runs at the window's edges below `--min`, marked | 0 |
| | `grid_png(glyphs, w, h, cols)`: gapless, one pixel a glyph pixel, zlib level 1; `pens` variant (phase 2) | 0 |
| | `kind_of`: RAR (`Rar!`), 7z, gzip, xz, LHA (`-lh?-` at 2) named as archives or packed data | 0 |
| | the 94 x 94 signature line worded for any 94 x 94 set (section 3) | 0 |
| `binscan.py`, `rawcarve.py`, `nkpspec.py` | every input opened as `bdfface.open_regular` does (no link followed, regular files only, non-blocking), and `nkpspec.py` refuses a file over `rawcarve.MAX_FILE` | 0 |
| `rawcarve.py` | `--gfx @FILE` and `region --files @FILE` (a parameter file in place of a long argument: a note line is at most 512 bytes, 4.5), also `binscan.py --gfx @FILE` | 2 |
| | `compose --check-spec`: a spec validated against a file's size, every set's extent reported, before it draws a wrong face | 3 |
| | no `--top` for `rawcarve.py bdf`: an English BDF is made from the padded raw form instead (8.2) | - |
| `jamoset.py` | nothing: a raw set reaches it in its layout's own storage (8.2) | - |
| `maker/srcprep.py` | `or-files OUT A B ...` (exists on `desktop-export`); `zip-member ZIP NAME OUT` (section 7.6) | 2 |
| `maker/sidecar.py`, `sidecar.spec`, `build-sidecar.sh` | `binscan`, `rawcarve`, `nkpspec` in `TOOLS` and `SMOKE`; a `recipe` command; `maker/recipes/*.json` bundled as data and staged into the packaged repo tree; `test_frozen.py` parity (t_97acecf9 does part of this first) | 0 |
| `maker/static/maker.js` | the `recipe` kind's routes (there since t_97acecf9) and `johab844` for it in `ROUTES`, `PREVIEW_KINDS`, `SOURCE_WORDS` ...; `test_page_js_tables_match_python` covers them | 1 |

### 7.6 Zip sets (phase 2)

MAME sets are zips, and the tools read file paths (4.9). Until phase 2 a set must be an unpacked folder: that is what
t_97acecf9's recipes read, and a zip is labelled "archive: extract it first, then choose the folder" as today. From
phase 2 a zip entry opened in the finder lists its members from the
central directory (count checked against the cap before any member is read; encrypted members, names
`check_rel_path` refuses and nested archives are refused; at most 64 MiB a member). The members the user ticks, or a
library recipe matches by size, are **extracted into the scratch** (`finder/<n>/zip/<k>.bin`, names of the finder's
own making) under `archive.py`'s size and ratio guards, hashed, and from then on are files like any other.

- Addressing: a session file is `{"font": "f7"}` or `{"font": "f7", "member": "ss151fnt.bin"}`.
- A recipe does not change: its `files` are matched by size and SHA-256 whether a file is loose or a zip member, and
  `recipe run` accepts zips among its FILE arguments and looks inside them the same way.
- `BUILD.md` lists the extraction as a source step (`srcprep.py zip-member ZIP NAME OUT`), so the run can be repeated
  by hand; the extracted bytes go with the scratch.

## 8. From marks to faces: a session recipe

The first draft said "marks become entries with `prep` ops and today's routes run unchanged", and the first revision
generalised the maker's companion steps to make that true. t_97acecf9 has since built a simpler thing that this
design now takes over: **a recipe is one font entry, and each of its face steps carves what it needs itself**
(`maker/recipe.py` `face_commands`, `routes.recipe_routes`, `detect._recipe_entries`). The finder's marks are a recipe
that is not saved yet; nothing else about them is special.

### 8.1 Finder entries are recipe entries

- **Apply** turns the session's marks and face pairings into **session recipes** in schema version 1, one a Hangul
  mark (its faces: at most one precomposed and one jamo, the page having one route a kind and font; the English marks
  its faces name are copied into each). They are kept in `job["finders"][n]["applied"]`, validated by the same
  `recipe.validate` as a library recipe.
- **Entries.** As for a known set, the file the recipe's faces read their Hangul from (`recipe.host_file`) carries an
  entry of kind `recipe` with `recipe: {id, files: {file id: [root, path]}, routes}`; here it also has `finder:
  {session, item}`, and its label is "found: <mark>". `detect._recipe_entries` appends these on **every** `POST
  detect` and on `apply` (which, like detect, clears steps and results), from the stable identities of 7.2; a session
  recipe whose file left the sources gives no entry and a notice. The host file's own entry (`unknown`, or a kind
  decided by size) stays in the table beside it. Detection does not run `srcprep.prepared_bytes` on recipe entries:
  their facts (cell, sizes, coverage) come from the recipe.
- **Which recipe.** `routes.recipe_routes` and `settings.py` look a recipe up with `recipe.get(id)`, which knows the
  built-in folder only: a session or user recipe would get no route. They resolve through one lookup instead,
  `recipe.resolve(font, job)`: the job's applied session recipes by `finder: {session, item}`, then the user
  library, then the built-in one (the recipe object holds no source byte, so keeping it in `job.json` is within 7.4).
  How the lookup is passed down is phase 0's to settle.
- **Appended, not relabelled.** For a known set `_recipe_entries` relabels the host file's entry in place. A session
  recipe's entry is **added** by a helper of its own, with a new font id and the host entry's `file_id` (so
  `_check_unchanged` sees the same file), and the host's own entry stays; code that maps `(root, path)` to one font
  (`_inputs_of_selected`) must take several. From phase 2 a `files` value may be `[root, path, member]` (7.6), and
  the three places that unpack the pair (`settings.py`, `server.py`, the planner) take the third element.
- **Identity.** `_kept_settings` keys such an entry by `(root path, path, face_index, session, item)`, so two marks of
  one file keep their own settings and a re-detect does not move them. A library recipe's entry is keyed by the recipe
  id in the same place.
- **Inputs.** Every file of `recipe.files` is checked by `_check_local_inputs` through `Sources.abs_of` (as
  `server.py` does for a known set), and `settings.plan_steps` hands the planner their absolute paths
  (`recipe_files`).
- **State.** The finder exists only on a `detected` job (7.2), so `apply`, `PUT settings` and `POST run` meet the
  state they expect.
- **No companion entries.** A face's English is part of its recipe and is carved inside the face's own step, so the
  maker's companion pairing (`detect.py`) and its planner branch (4.5) are not touched, and the whole `.COM` can
  never be passed as `--eng`. The price: a finder face cannot take a Latin BDF of the job as its English; that is
  what the ordinary `bdf-ksc5601` route is for.

### 8.2 How a reading reaches the commands

`recipe.face_commands` builds, in the step's work folder (`recipe-*` files, cleared before a run), the regions and
items a face reads and then the route's command. A reading is **plain** when it is row-major, MSB-first, with the
default stride and no gfx layout: what `rawcarve.py eng` and `cut` read.

| What | Command | When |
|---|---|---|
| a zip member (phase 2) | `srcprep.py zip-member ZIP NAME member.bin` | a file inside a zip |
| a region | `rawcarve.py region --group A B --group C D [--unit N] [--swap] -o recipe-region-R.bin` (the comma-free form t_97acecf9 added: a comma in a path cannot split a group) | an assembled region |
| ink | `rawcarve.py ink SRC [--offset O] --count N (--glyph WxH [--order R] [--stride B] [--lsb] \| --gfx L [--bg P \| --fg P,..]) [--invert] -o recipe-I-ink.bin` | a reading that is not plain, before `eng` or `cut` (tiles included: `ink --offset --count`, then `eng` / `cut` at offset 0) |
| English, raw form | `rawcarve.py eng SRC --offset O [--height H] [--top T] [--width 16] [--first C] [--count N] [--invert] -o recipe-I-eng.bin` | plain (or plain and inverted): straight from the file; otherwise from the ink file |
| several English items | `srcprep.py or-files recipe-english-merged.bin E1 E2 ...` | a face whose `english` is a list: the raw forms OR-ed (one glyph width) |
| English, BDF form | `rawcarve.py bdf I-eng.bin --glyph 8x16 (or 16x16) --chars ascii [--ascent A] -o recipe-english.bdf` | from the **raw form**, whenever the item is not already a 16-row cell at `top` 0, or is a list (see below) |
| | `rawcarve.py bdf SRC --offset O [reading] --chars ascii [--first C] [--count N] [--ascent A]` | an 8x16 or 16x16 item with `top` 0: straight from the file |
| KS dense / grid | `rawcarve.py bdf SRC [--offset O] [reading] --chars SET (--dense \| --grid L0,T0,P) [--ascent A] -o recipe-I.bdf` | `bdf` takes the whole reading itself (order, stride, lsb, invert, gfx) |
| a raw set | `rawcarve.py cut SRC --offset O --length N -o recipe-I.fnt` | see the layout table below |
| a compose spec | `rawcarve.py compose SRC --spec SPEC [--syllables all] [--ascent A] -o recipe-I.bdf`; `jamoset.py --layout spec --spec SPEC SRC` | built-in `spc1500` today; a file from phase 3 |

**English: one placement for both forms.** `rawcarve.py eng` pads an 8xH glyph into the 16-row cell with `top` blank
rows above; `rawcarve.py bdf` has no such padding and puts a glyph at its cell top, and `bdfface.py` takes its ascent
from the ASCII BDF, so a BDF cut straight from an 8x8 font at `top` 4 would sit four rows higher than the same mark
through `--eng` (and t_97acecf9's code refuses `top` on a `bdfface` face for that reason). Rule: **the BDF form of an
English item that is not already a 16-row cell at `top` 0 is cut from its padded raw form** (`eng`, then `bdf --glyph
8x16`), exactly as the code already does for a list of items. Both forms then hold the same 16 rows. The `--ascent`
of that 16-row BDF is counted in the 16-row cell, not in the item's own H rows: the Hangul item's ascent when the
face has one, else `top` + the English item's `ascent`, else the tool's default for 16 rows (14); the built face's
header ascent is part of the test. No `--top` is
added to `rawcarve.py bdf`; finder phase 0 replaces the refusal with this rule.

**Raw sets: selection is not storage.** `jamoset.py` reads each raw layout in that layout's own storage (`844`,
`1044-san` row-major; `621` through `g_bytecols`, which is `binscan.py`'s `strips`; the printer layouts column-major;
some sizes carry a header or two cell sizes), so "rewrite as plain rows, then cut" is right only for the layouts whose
storage is plain rows. The contract, by layout:

| Layout (length) | Storage `jamoset.py` reads | Reading a mark may have | Carve |
|---|---|---|---|
| `844` (11,520 / 25,920 / 72,000 / 103,680), `1044-san` (12,800) | rows, MSB-first, headerless, one cell size | any (order, lsb, stride, invert, tiles): the viewer's reading is rewritten | plain: `cut`; else `ink` then `cut` at offset 0, length = glyphs x plain glyph bytes |
| `621` (6,144) | `strips` of a 16x16 cell | exactly `{"glyph": [16, 16], "order": "strips"}`, no lsb, stride, invert or gfx | `cut` of the bytes as they are |
| `844` with a header or symbols (11,522; 15,584), `844-ihnm`, `844-hbios24`, `kyra-lok` | rows, in the file's own framing | plain only (rows, MSB-first, default stride, not inverted, no gfx) | `cut` of the bytes as they are |
| `dkb-printer-7x2x2`, `dkb-printer-12x4x4` | column-major, two cell sizes | not offered as a mark in version 1 (a loose file of these sizes keeps its `dos-raw` route) | - |

A reading outside its row is refused when the mark is made (422 `mark.reading`, naming the layout's storage) and when
a recipe is validated; choosing a layout in the mark panel sets the viewer to the layout's storage. (t_97acecf9's
validator has this rule since `a103f56`.)

- Two faces of one recipe run in separate step folders, so no two steps write one file; inside a step each region and
  item is made once.
- A parameter a command names by file (a compose `SPEC.json`, a gfx `@FILE`, a region `@LIST`: 7.5) is written to
  `build-<id>/finder/<recipe id>/<item>.<what>` by the run and the command line names that copy: it stays when the
  scratch goes. A session recipe's id is unique in the job (`found-<session>-<item>`), so two sessions that both
  call an item `hangul` do not share a file; a parameter belongs to an item, not to a face or a form.
- **Proof** (section 13): for every order, bit order, inversion and stride, and for every raw layout of the table, the
  glyphs of the built face equal glyphs the test built itself, not glyphs read back through the tools.

### 8.3 Routes

| Route | Kind | Hangul item | Command (after the carving of 8.2) |
|---|---|---|---|
| `bdfface` | precomposed | `ks-grid`, `ks-dense`, `compose` | `bdfface.py --hangul H.bdf --ascii E.bdf --cell WxH --chars-from KS -o OUT` (`WxH` the Hangul item's glyph); needs an English |
| `bdfface + from-svf fit` | jamo | through `from`, or its own `hangul` + `english` | the `bdfface` face made in the step as `precomposed.svf`, then `jamoset.py --layout L --from-svf precomposed.svf --mask-font none [--eng E.raw] --check -o OUT` |
| `spec` | jamo | `compose` | `jamoset.py --layout spec --spec SPEC SRC [--eng E.raw] --check -o OUT` |
| `dos raw` | jamo | `raw-set` | `jamoset.py --layout L RAW [--eng E.raw] --check -o OUT` |
| `johab844` (finder phase 1) | precomposed | `raw-set`, 11,520 bytes | `johab844.py RAW svf/dos/NEODG16.SVF OUT [--eng E.raw]` (8x16 English only) |

- **A fit is self-contained.** Its step builds the precomposed face it reads as `precomposed.svf` in its own work
  folder, whether that face is named by `from` (an earlier face of the recipe: the same items, no second description)
  or given directly by `hangul` + `english` (a recipe with a jamo face only). Deselecting the precomposed face in the
  fonts table therefore changes nothing for the jamo face, and the step graph is the same in the app, the trial and
  `recipe run`. `--mask-font none` is always passed, so the fit does not depend on a font that happens to be on the
  host. (The existing `bdf-ksc5601` fit does not pass it: a note for that route's owner, not changed here.)
- `chars` may be `ks-hangul`, `ks-nonhanja` or `ks-all` (the BDF keeps what the set has), but every route above builds
  syllables and ASCII only: `bdfface.py` keeps nothing else. There is no `mkfont` route (`--unicode ksx1001-nohanja`
  stops in Pillow on U+00AD, and FreeType takes a BDF's first glyph as `.notdef`); faces of the symbols and Hanja wait
  for a card that settles both.
- **One planner.** The trial, the run and `recipe run` all call `recipe.face_commands` and run its argv lists; the
  trial only writes into the scratch instead of `svf/`. A trial that passes and a run that draws something else is
  thereby a planner bug a test can see (section 13, equivalence).
- A recipe's `faces` preselect names, layouts and `dest`; the user can change them in the fonts table as for any
  entry. The page shows the first face of each kind (`recipe.offered_faces`).

### 8.4 What a run writes

`svf/<dest>/<NAME>.SVF` and its note as today, and in `build-<id>/`: `BUILD.md` (with the carving commands),
`RECIPE-<recipe id>.json` for each recipe run, and `finder/<recipe id>/` with the parameter files of 8.2. An export (section 10) writes
`finder-export-<job>-<k>/` at the top of the output folder, `k` the first number not taken (nothing is replaced).
`docs/desktop-app.md` section 6 lists both.

### 8.5 The numbers

The trial, `recipe run` and `expect` use the sample line of `docs/recipes.md` "Checking a face", fixed here so the
numbers agree everywhere: the text `안녕하세요 ABC 123`; `svfline.py measure` for width, ascent and descent; the ink =
the non-zero bytes of `svfline.py line W H 0 B`, with `W` x `H` = 200 x 24 and baseline `B` = 16 for a 16 px cell and
400 x (C + 8) with `B` = C for any other cell height C, and `W` raised to the measured width rounded up to a multiple
of 20 when the line is wider (the recipes' 220 for the 208-wide lines). The page's own sample text
(`detect.SAMPLE_TEXT`) stays what it is for previews; it is not the text of the numbers.

### 8.6 Headless

    svf-maker-sidecar recipe check RECIPE.json FILE...            which files match (size, sha256), what is missing
    svf-maker-sidecar recipe run   RECIPE.json FILE... --out DIR  the recipe's faces, BUILD.md and RECIPE json in DIR
    svf-maker-sidecar recipe list                                 the built-in and user recipes

(`python3 -P maker/recipe.py ...` from a checkout.) `run` refuses files that do not match unless `--unverified`; its
faces are byte-identical to the app's run of the same recipe (a test). These commands are the finder's (phase 0);
t_97acecf9 has the library and the planner, not the command line.

## 9. Recipes

### 9.1 Example

    {
      "recipe": 1,
      "id": "86box-tgkorvga",
      "title": {"en": "Trigem Korean VGA font ROM (ET4000)", "ko": "삼보 한글 VGA 글꼴 ROM (ET4000)"},
      "notes": "128 x 128 KS grid, two 8-pixel strips (86Box vid_svga_render.c).",
      "refs": ["86Box/roms 1ac40f2 video/et4000/tg_ksc5601.rom", "docs/recipes.md#korean-vga-font-roms-86box"],
      "files": [
        {"id": "font", "name": "tg_ksc5601.rom", "size": 524288, "sha256": "<64 hex>", "sha1": "<40 hex, optional>"},
        {"id": "bios", "name": "tgkorvga.bin", "size": 32768, "sha256": "<64 hex>"}
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
        "items": {"hangul": {"glyphs": 2350, "sha256": "<of hangul.bdf>"}},
        "faces": {"TGVGA16": {"bytes": 122392, "glyphs": 2447, "ink": 476}}
      }
    }

Both files are required here: `bdfface` cannot build a face without its ASCII (4.5), and the jamo face reads the
precomposed one. (The first draft marked `bios` optional while every face needed it.) A recipe holds **no font byte
and no path**: names, sizes, hashes, offsets, rules, numbers. A compose spec is offsets and rules (as `nkpspec.py`
says of its output). A hash of a carved file identifies it without revealing it.

### 9.2 The library and detection

- **Built-in**: `maker/recipes/*.json` in the repository and the sidecar (hashes and offsets only, so the OFL-only
  repository can carry them). **User**: `<data root>/recipes/*.json` (`~/.config/svf-maker/maker/recipes/` in the
  desktop app); a user recipe never shadows a built-in id.
- **Matching at detect**: the library is indexed by file size. A file whose size matches no recipe file is not hashed
  (ordinary fonts cost nothing). A size match is hashed, whatever kind `sniff` gave the file (4.4). The states are
  - **known**: every required file of a recipe is among the job's sources with its hash. The entry of the recipe's
    first file is labelled `known: <title>`, takes the others as its inputs and companions, and offers the recipe's
    faces. A face is offered only when every file its items read (through `hangul`, `english` and `from`) is present;
    a face left out names the missing optional file ("TGVGA16: also pick tgkorvga.bin");
  - **part of a set**: some required files match, others are missing: "part of <title>: also needs <names>; pick the
    folder". No face is offered; "look inside" still works, and the Hangul mark can be paired with any other English
    companion of the job;
  - **similar**: name and size match, hash differs: "looks like <title>, another revision: opens in the finder with
    the recipe's parameters, unverified" (`expect` is not applied).
- A known entry needs no finder session: it is the `recipe` entry of 8.1, made by `detect._recipe_entries`.
- `optional: true` is for a file that only some faces read (an English ROM beside a compose-spec set whose jamo face
  does not need it). A recipe in which every face needs an optional file is refused at load: the file is required.
- Until phase 2 a set is matched as loose files (an unpacked folder); a zip is not looked into (7.6).

### 9.3 Card t_97acecf9's known ROMs

Decided (section 15, 3): the known ROMs **are** recipes, and t_97acecf9 has built them (branch `desktop-export`, in
review): `maker/recipe.py` (validator, library, `match`, the planner `face_commands`), `maker/recipes/` with the three
86Box VGA ROMs, the SPC-1500 set, Date Quiz Go Go, Quiz King of Fighters (Korea) and X Se Dae, `srcprep.py or-files`,
the `recipe` entry kind in `detect.py` / `routes.py` / `settings.py`. The finder extends that module (the validator,
the planner, the library folders); it does not replace it. A key or an item kind the code does not read yet is refused
by name ("not supported yet: ..."), never ignored, so a recipe of a later phase cannot half-run. 9.5 lists where the
code and this schema differ today. The other worked examples (NKP, NKP3, DKBB, DKBII) become built-in recipes as the
finder's phases land; the unresolved ones (livequiz, quizdaisk) do not.

### 9.4 Schema version 1: field reference

A recipe is one JSON object in UTF-8, at most 256 KiB. Integers are JSON numbers without a fraction; an offset or a
size is 0 .. 2^26 (64 MiB). "id" below means `[a-z0-9][a-z0-9-]{0,47}`. Keys not listed are refused (a typo must not
be silently ignored); `recipe` other than 1 is refused with the version. R = required, O = optional (default in
brackets).

| Object | Key | | Type and rule |
|---|---|---|---|
| recipe | `recipe` | R | the integer 1 |
| | `id` | R | id; the file is `<id>.json`; unique in a library |
| | `title` | R | `{"en": text, "ko": text}`, `en` required, each 1..120 characters |
| | `notes` | O | text, at most 2,000 characters [""] |
| | `refs` | O | list of at most 16 texts of at most 200 characters (where the layout was read from; never opened) |
| | `files` | R | list of 1..16 file objects, ids distinct |
| | `regions` | O | list of at most 16 region objects [none]; phase 2 |
| | `items` | R | list of 1..64 item objects, ids distinct |
| | `faces` | R | list of 1..16 face objects, names distinct |
| | `expect` | O | `{"items": {item id: {...}}, "faces": {face name: {...}}}` |
| file | `id` | R | id, distinct from every region id |
| | `name` | R | the usual base name: a label and the tie-breaker of "similar"; no `/`, `\\` or control character, 1..255 bytes |
| | `size` | R | integer, 1 .. 2^26 |
| | `sha256` | R | 64 lower-case hex characters of the whole file |
| | `sha1` | O | 40 lower-case hex characters (the MAME `ROM_LOAD` hash; checked when present) |
| | `optional` | O | boolean [false]; see 9.2 |
| region | `id` | R | id |
| | `groups` | R | list of 1..16 lists of 1..8 file ids: the files of a group interleaved, the groups one after another. A file id appears once in a region; the files of a group have one size; the sum of all sizes is at most 2^26 (checked on the recipe's own `size` fields at load) |
| | `unit` | O | 1, 2 or 4 [1] |
| | `swap` | O | boolean [false] |
| item | `id` | R | id |
| | `kind` | R | `raw-set`, `english`, `ks-dense`, `ks-grid` or `compose` |
| | `region` | R | a file id or a region id |
| | `offset` | O | integer byte offset of glyph 0 in the region [0] |
| | `reading` | R | reading object |
| | `ascent` | O | integer 1..height, counted from the top of the item's own glyph [the tool's default: 7/8 of the height, rounded up]; for a padded English BDF see 8.2 |
| | `decided` | O | `by eye`, `loose copy` or `driver code` |
| reading | `glyph` | R | `[W, H]`, each 1..1024 |
| | `order` | O | `rows`, `strips`, `cols` or `bytecols` [`rows`] |
| | `stride` | O | integer bytes from one glyph to the next, 1 .. 2^26 [the glyph's bytes in that order] |
| | `lsb`, `invert` | O | booleans [false] |
| | `gfx`, `bg`, `fg` | O | a `binscan.py --gfx` layout text (1..2,000 characters, parsed by `binscan.parse_gfx` against the region's size; its tile must be `glyph`), a pen 0..255, a list of 1..16 pens. `bg` or `fg`, not both, and only with `gfx`; `order`, `stride` and `lsb` are refused beside `gfx` (the layout gives the tile) |

Keys of each item kind, beside the common ones:

| Kind | Key | | Type and rule |
|---|---|---|---|
| `ks-grid` | `chars` | R | `ks-hangul`, `ks-nonhanja` or `ks-all` (what the BDF keeps; the faces are syllables and ASCII, 8.3) |
| | `grid` | R | `[L0, T0, PITCH]`: glyph index = (lead - L0) x PITCH + (trail - T0); L0 and T0 0..255, PITCH 1..256; when the files are bound, every code of `chars` must lie inside the grid (lead >= L0, T0 <= trail < T0 + PITCH: `recipe.check_fit`) |
| `ks-dense` | `chars` | R | as above: glyph i is the i-th code of the set in KS order |
| `english` | `first` | O | the code of glyph 0, 0..255 [0] |
| | `count` | O | glyphs, 1..256, `first` + `count` <= 256 [256 - `first`] |
| | `top` | O | blank rows above an 8xH glyph in the 16-row cell, 0..15, `top` + H <= 16 [0]; both forms place it alike (8.2) |
| | (`reading.glyph`) | | `[8, H]` with H 8..16, or `[16, 16]` (phase 2) |
| `raw-set` | `layout` | R | `844`, `844-ihnm`, `844-hbios24`, `1044-san`, `621` or `kyra-lok`; the reading must be one the layout's row of 8.2 allows |
| | `length` | R | integer bytes cut from `offset`: a size `detect.DOS_SIZES` lists for that layout |
| `compose` | `spec` | R | `{"builtin": "spc1500"}` (implemented); `{"derive": "nkpspec"}` or an inline compose spec object (phase 3) |
| | `syllables` | O | `ks` or `all` [`ks`] |

An inline compose spec is the object `rawcarve.py compose` documents, bounded here: `cell` `[W, H]` each 8..64; at most
64 `sets`, each with `offset` 0 .. 2^26, `stride` 1..4,096, `x` / `y` >= 0, `width` / `height` >= 1 with `x + width <=
W` and `y + height <= H`, the reading keys above; `vowel_order` 21 distinct integers 0..20; every vowel table exactly
21 entries naming existing sets; a medial entry `[set, k]` with k 0..255; unknown keys refused.

| Object | Key | | Type and rule |
|---|---|---|---|
| face | `name` | R | the face's file stem: `[A-Z0-9]{1,8}` (`naming.NAME_RE` without `.SVF`; `XSEDA16J`, `QUIZKOFJ`) |
| | `kind` | R | `precomposed` or `jamo`; it must be the kind the route makes |
| | `route` | R | `bdfface`, `bdfface + from-svf fit`, `spec`, `dos raw` (implemented), `johab844` (finder phase 1). A closed list: another value is refused |
| | `hangul` | R, or `from` on a fit | item id of the Hangul source, of a kind the route takes (8.3) |
| | `english` | O | an item id of kind `english`, or a list of 1..8 of them: the items are OR-ed into one English font (digits and letters kept apart in a ROM), so they have one glyph width and their codes should not overlap. Required by `bdfface`; on the other routes it is the `--eng` companion |
| | `from` | O | fits only: the name of an earlier precomposed face of this recipe whose items the fit reads; the step builds that face itself (8.3). A fit has `from` or `hangul` (+ `english` for the precomposed face it builds), not both |
| | `layout` | O | fits only: `844` or `adaptive` [`844`] |
| | `dest` | O | the output subfolder, `naming.DEST_RE` (`dos`, `jamo-extra`, `games/<name>`, `new/<name>`) [`new/<recipe id>`]; the app's batch setting replaces the default |
| expect item | `glyphs`, `sha256` | O | of the item's **canonical file**, whichever faces are selected and in whatever order they run: `english` the raw form (`rawcarve.py eng`), `raw-set` the cut file, `ks-dense` / `ks-grid` / `compose` the BDF. `glyphs` = its inked glyphs (0 .. 2^26). A run checks an item once, in the first step that makes that file; a form the run did not make is not checked (and said so) |
| expect face | `bytes`, `glyphs`, `ink` | O | the SVF's size, its glyph count, the ink of 8.5 (each 0 .. 2^26) |

Rules across objects: every id an item, a region or a face names exists; `from` names an earlier precomposed face (no
cycle); an item's reading must fit its region (`offset` + the bytes its glyphs span <= the region's size, checked when
the files are bound: a `ks-grid` item spans up to the highest index of its `chars`; a tile layout is checked by
`binscan` when it reads); a face's `hangul` item is of a kind its `route` takes (8.3). `expect` is what makes a re-run
self-checking; a mismatch is reported, not hidden, and the faces are still written.

The 86Box example of 9.1 is a complete, valid recipe of the t_97acecf9 subset once its hashes are filled in; its
commands are those of `docs/recipes.md` "Korean VGA font ROMs (86Box)": `rawcarve.py bdf FONT --glyph 16x16 --stride 32
--order strips --chars ks-hangul --grid 0x80,0x80,128 --ascent 12`, `rawcarve.py bdf BIOS --offset 0x4a2d --glyph 8x16
--chars ascii --first 0 --count 256 --ascent 12`, `bdfface.py --hangul H --ascii A --cell 16x16 --chars-from KS`, then
`jamoset.py --layout 844 --from-svf precomposed.svf --mask-font none --check` (the fit's step makes `precomposed.svf`
with the first three commands again).

### 9.5 The code of t_97acecf9 and this schema

`maker/recipe.py` on `desktop-export` (read at `9be5fc7`, again at `a103f56` after its first review round) is the
schema above, with these differences. The first group is in
the code and now in the schema; the second is what the finder's phase 0 adds to the code.

| | Point | Where |
|---|---|---|
| in the code, folded into 9.4 | a face's `english` may be a list of 1..8 items, OR-ed by `srcprep.py or-files` | 8.2, 9.4 |
| | `chars` takes the three KS sets; `fg` is 1..16 pens; `stride` up to 2^26; `gfx` excludes `order` / `stride` / `lsb` and fixes `glyph` | 9.4 |
| | `bdfface` reads a `compose` item too (no separate "compose bdf" routes); a fit builds its own `precomposed.svf` and passes `--mask-font none` and `--eng` | 8.3 |
| | tiled or otherwise non-plain items: `ink --offset --count`, then `eng` / `cut` at offset 0 | 8.2 |
| | one `recipe` entry a set, on the file the first face's Hangul item reads; the first face of each kind is offered | 8.1 |
| | MAME sets as unpacked folders (no zip) | 7.6, 9.2 |
| | the raw-set storage contract of 8.2 and `rawcarve.py region --group` (both since `a103f56`) | 8.2 |
| the finder adds | `top` on a `bdfface` face (refused today): the BDF from the padded raw form | 8.2 |
| | a fit with `hangul` + `english` instead of `from` (refused by name since `a103f56`) | 8.3, 9.4 |
| | the ascent of a padded English BDF in 16-row coordinates; `expect` items by canonical file | 8.2, 9.4 |
| | `recipe.resolve` in place of the built-in-only `recipe.get` in `routes.py` and `settings.py`; appended session entries with the host's `file_id`; `files` values with a zip member (phase 2) | 8.1 |
| | `dest` on a face (an unknown key today); the route `johab844`; inline and derived compose specs; `regions` rules beyond the code's (a file id once a region) | 9.4 |
| | the user library, session recipes, `expect` checked at run, the rule that a face is offered only when its files are present, `recipe check / run / list` | 8.6, 9.2 |

## 10. Compose rules, and help from an assistant

A font with its own compose rule (NKP's 17 cropped piece sets and driver tables, the SPC-1500's 6 / 2 / 2 sets) cannot
be found by looking at glyph grids: the rule is in code. The design keeps the app honest about that:

- **In the app (phase 3)**: "load a compose spec" (a file or pasted JSON, or the built-in `spc1500`, or "derive with
  nkpspec" which runs `nkpspec.py find` / `spec` on the file and shows the table addresses it found). The spec is
  validated (9.4's bounds, then `rawcarve.py compose --check-spec`: every set inside the file, strides and crops
  consistent) and then **inspected**, not edited: each piece set drawn as a strip at its place in the cell; a matrix
  of 19 initials x 21 vowels without and with a final; the sample line; the jamo set's `--check` ("all 11,172
  syllables identical to rawcarve.py compose"). The NKP lesson (a wrong crop draws a wrong face without an error) is
  why the set strips are shown with the cell outline.
- **Not in the app**: a table editor for compose rules. It is a large UI for a handful of files, and whoever can fill
  it can write the JSON. Phase 4, only if asked.
- **Export for an assistant**: writes `finder-export-<job>-<k>/` (8.4) into the output folder: `PROMPT.md` (the
  prompt of `docs/recipes.md` filled in: the file's name, kind, size and hash, what the analysis found and what the
  user tried and marked, what is unresolved, and the exact form of the answer wanted: a compose spec or a recipe of
  schema 1); `session.json` (candidates and marks); `recipe-draft.json`; with "include renders" ticked (off by
  default), the PNGs of the candidates (derived bitmaps of the source: said so in the dialog, written nowhere else).
  The source file is named by path, not copied. The app contacts no one: the user takes the folder to Claude Code (or
  any assistant that can run the tools), and loads the returned spec or recipe with "load recipe or spec". The same
  export is the bug-report form for a file the finder does not resolve.

## 11. Internationalisation

The page is English only today. The finder brings a string table: `maker/static/strings.js` (`{en: {...}, ko:
{...}}`, `t(key, values)`). The language is `navigator.language` (`ko*` -> Korean) until the user switches it in the
top bar; the choice is kept by the server in `<data root>/prefs.json` (`GET` / `PUT /api/prefs`), because the shell's
session keeps no `localStorage` across a quit (4.7). All finder strings go through the table from the first commit;
finder endpoints answer errors with a stable `code` beside the English `error` text so the page can show its own
sentence. Tool output (the `why` facts, `--check` lines) stays as the tools print it. Moving the rest of the page onto
the table is not part of this design (section 15, 6). Docs: `docs/desktop-app.md` gets a chapter "Finding a font
inside a file" and `docs/recipes.md` a paragraph pointing from the prompt section to the app, each with its `.ko.md`.

## 12. Accessibility

- Everything works from the keyboard: the candidate list is a list of buttons; in the grid the arrow keys move the
  selection by glyph, `Shift` extends it, `Alt` + arrows move the offset by a byte (left / right) or a stored row
  (up / down), `PageUp` / `PageDown` by a page, `[` / `]` change the glyph width and `{` / `}` its height; every
  shortcut is also a labelled button, and the list is shown by `?`.
- The grid is a picture, so it has a text side: an `aria-label` that states the reading ("64 glyphs of 8x16 from
  0x39a0, rows"), a live `role="status"` line for the hovered or focused glyph (index, offset, and for a mapped mark
  its character), and "show as text" (5.1).
- No meaning by colour alone: marks carry their number in the overview strip and the grid; ink is drawn at full
  contrast in both themes; the scale control goes to 8 for low vision; focus is always visible and returns to the
  finder button when the view closes.
- Long work is announced: analysis and trial progress, "preparing" after a sweep and "not scanned" results through the
  same `role="status"` line pattern the page already uses for notices.

## 13. Tests

- **Synthetic fixtures** (`maker/test/finderfx.py`, bytes built in the test from the OFL faces of `svf/` and seeded
  noise, nothing proprietary): (1) a `.COM`-like file: noise, an 8x16 ASCII font, zero padding, an 8x4x4 set (the tie
  case); (1b) an 8x4x4 set starting at 0xFE0 of a file whose first 4 KiB block is otherwise zero (the blank slot 0 in
  a block of one byte value); (1c) an `MZ` file, a 4,096-byte ROM and a `.PFT`-named file holding a font (the ways in
  of 5 step 1), and an FNT with no openable size; (2) a 2,350-glyph KS dense table inside a larger file, plain and
  inverted; (3) a 128-grid font in strips with its blank rows; (3b) a 24x24 font at an offset of 2 modulo 3; (4) a
  four-file inverted piece-set region with a compose spec (SPC-1500-like; `tools/test_tiles.py` on `mame-roms` builds
  such regions); (5) a `ROM_LOAD16_BYTE` pair of 4 bpp tiles with an outline pen and a non-zero background; (6) a
  packed file (zlib of the above) and files with RAR / 7z / gzip magic; (7) hostile cases: over the caps, a symlink, a
  FIFO, a file truncated or rewritten during the session (the sidecar must answer 409 and stay up), zero length, a
  recipe with unknown keys, absurd numbers, a 10 MB gfx string; (8) phase 2 zips: a zip bomb, a member name with `..`,
  an encrypted member, a nested archive, a central directory over the count.
- **Readings** (8.2): one font written in every order x lsb x invert x a padded stride, carved as a raw set, as
  English (first code 0x20) and as a KS grid, and the built faces' glyphs compared with the glyphs the fixture was
  built from. The raw-set oracle runs for each layout of 8.2's table: `844` and `1044-san` in every reading; `621` in
  its `strips` storage (and refused in any other reading); a headered `844` plain (and refused inverted). English
  placement: an 8x8 font at `top` 4 beside a 16x16 KS-grid Hangul, through `bdfface` (BDF form) and through `dos raw`
  and the fit's `--eng` (raw form): the letters' ink is in rows 4..11 of the cell in every face, and the same for an
  8x14 font at `top` 1; a list of two English items equals the one font they were split from.
- **Units**: candidate ranking; anchors (English first code; dense start; a grid with a pitch; two grids that agree on
  one anchor and differ on the next, so one anchor without a pitch is refused and the second anchor decides;
  conflicts); the recipe schema including every bound of 9.4; the planner's argv against the command lines of
  `docs/recipes.md`; `test_page_js_tables_match_python` with the new kinds and routes.
- **Planner**: each face step carves its own regions and items and no step reads another's work folder; a jamo fit
  gives the same bytes with its precomposed face selected, deselected, and given by `hangul` instead of `from`; a
  failed carve command fails its face with the tool's message; two marks of one file keep separate settings across
  `POST detect`; a recipe with a missing optional file offers only the faces that do not need it, in the app, the
  trial and `recipe run`; a `part of a set` entry offers none.
- **Identity** (7.2): a session open on a file, then a file that sorts earlier is added, one is removed, and the roots
  are reordered, each followed by `POST detect`: every mark is still bound to its original file (by content), its
  entry and settings are kept, and a mark whose file was removed is reported missing, not rebound.
- **Windows** (6): a sparse region of 32 MiB with an 8x4x4 set and an 8x16 ASCII font each lying across the 16 MiB
  boundary, and a run of 40 glyphs crossing it with 20 on each side (each half under `--min` 32): each is found once,
  at its absolute offset.
- **Session recipes** (8.1): an applied mark and a user-library recipe each get their routes and run (not only a
  built-in one); the host file's own entry is still there and `POST run` passes `_check_unchanged`; two sessions with
  an item `hangul` and different parameter files reproduce from `build-<id>/finder/`; an English item used by a
  `bdfface` face and its fit has one `expect` hash that holds with either face deselected and in either order; the
  8x8 `top` 4 face's header ascent is the Hangul item's; `apply` during hashing waits or answers 409.
- **Server**: every endpoint with and without the token and with a foreign `Host`; `no-store` on the byte GETs; bounds
  before allocation; the analysis and trial budgets kill their tools (no process left in `tools.pids`); cancel of a
  trial; `PUT /api/recipes/<rid>` with `..`, a built-in id, a mismatched id, the 501st recipe; `/api/recipes` and
  `/api/prefs` without local mode or the token (403) and with no job; `PUT /api/prefs` with another key, another
  value, an oversized body, and a kill between the write and the replace (the old file stays); an export into a
  folder where `finder-export-*` exists, and where it is a symlink; no source byte pattern of the fixture in
  `job.json`, the logs, the recipe or any error; nothing written outside the output folder; the no-network scan
  covers the new modules.
- **Lifecycle**: an idle sweep while a scan runs (skipped) and after it (scratch gone, the next render rebuilds it);
  a run finishing with a session open; `POST run` during a scan (409); server stop during a scan (the tool is gone).
- **Equivalence**: app run == trial == `recipe run` == the hand-run commands of `BUILD.md`, byte for byte, for each
  fixture, also with `JAMOSET_MASK_FONT` set in the environment; a saved recipe recognises the same fixture in a new
  job (`known`), a one-byte change makes it `similar`, a missing file `part of a set`.
- **Page** (`pagedrive.mjs`, Chrome): open fixture (1), the two expected candidates appear, pick, mark both, try (the
  sample line is drawn and equals the byte oracle), apply, run; fixture (5) through the region editor, pen view and
  pen rule; keyboard-only run of the same; every string key exists in `en` and `ko`, and `finder.js` holds no
  user-visible literal (a scan); the language survives a restart of the server.
- **Desktop**: one step in `desktop/test/e2e.js` (open a fixture, apply a built-in test recipe, faces written, "show
  as text" filled without a permission request); the frozen sidecar's smoke check runs `binscan`, `rawcarve`,
  `nkpspec` and `recipe list` and finds the bundled recipes.
- **Real files** (environment-gated, hashes checked, skipped here): `MAME_ROMS` as in `tools/test_tiles.py`, the 86Box
  ROMs, `SVF_MAKER_REAL_NKP`, `_DKB`: each built-in recipe reproduces the numbers `docs/recipes.md` records.
- **Performance** (recorded, not gated at first): the redraw and scan targets of 6 and 7.1 on fixture sizes 38 KiB,
  512 KiB and 8 MiB, and the coarse phase sets of `strips`, `cols` and `bytecols`.

## 14. Phases

| Phase | Content | Needs |
|---|---|---|
| 0 | The phase-0 rows of 7.5; `maker/recipe.py` extended by the "finder adds" rows of 9.5 (English placement, the raw-set contract, direct fits, `dest`, the user library, `expect`); session recipes as entries (8.1); `recipe check / run / list` | `mame-roms` merged into main (t_c1eca08f); t_97acecf9 merged (`maker/recipe.py`, `maker/recipes/`) |
| 1 (MVP) | The finder view for **1 bpp, each mark reading one file as it is** (several independent files a session; no assembled region, no tiles): analysis stages 0-2, candidates, viewer with every 1 bpp parameter, long-strip mode, anchors, marks `raw-set` / `english` 8xH / `ks-dense` / `ks-grid`, trial, apply, recipe save / load, the user library and detection states, string table EN + KO and `prefs`, keyboard and status lines, docs | phase 0 |
| 2 | ROM sets: region editor and suggestions, tiles panel (presets and pasted `gfx_layout`), pen view and rule, English 16x16, zip members (7.6), compare with a loose file, KS-order score, the built-in recipes of the MAME sets | phase 1 |
| 3 | Compose specs: load / `nkpspec` derive / inline (`spc1500` is built in already), `--check-spec`, the inspector, export for an assistant | phase 2 |
| 4 (only if asked) | Compose table editor; pasted `ROM_LOAD` lines to a region; recogniser-assisted labelling of an unknown order (`SVF_RECOG_DIR`); executable unpackers; KS symbols and Hanja | - |

Phase 1 covers the Dokkaebi drivers (one file: the set and the English font) and the 86Box VGA ROMs (two files, one
mark each) end to end, and NKP's English font; phase 2 the MAME quiz sets and X Se Dae; phase 3 NKP and the SPC-1500.

## 15. Decisions (user, 2026-11-23)

The ten questions the first draft left to the owner were all answered "as recommended" on 2026-11-23.

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

### 15.1 Where the review touches a decision (the owner's nod wanted)

All ten decisions stand. Two are now worded more exactly than they were answered, and two facts under them changed:

1. **Decision 9, "in place".** `archive.py` cannot read a member in place and the tools need file paths (4.9). The
   revision keeps what the decision is for (the user picks the zip, unpacks nothing by hand, and nothing leaves the
   output folder) but the ticked members are **extracted into the job's scratch** under `archive.py`'s guards (7.6),
   and go with the scratch. Proposed: accept this reading. The alternative, a member reader every tool understands,
   is a larger change to `binscan.py` / `rawcarve.py` for no gain the user would see.
2. **Decision 8, "one file".** Read as: each mark reads one file as it is (no interleaved region, no tiles). A phase-1
   session may still hold several independent files, because the 86Box case the phase claims is a pair (font ROM and
   BIOS). Proposed: accept this reading. The alternative, strictly one file a session, makes phase 1 Hangul-only for
   the VGA ROMs.
3. **Under decision 3**: t_97acecf9 has implemented the recipes (9.3), and the schema was brought in line with its
   code where the code went further (9.5, first group). What the code does not have yet is the second group of 9.5.
   The two corrections the second round asked of that card (the raw-set storage rule, a fit's `hangul` refused by
   name) are in its `a103f56`. Nothing of the third round has to change before it merges: its recipes are built-in,
   16-row English and loose files, so `recipe.get`, the BDF ascent and the two-element `files` are right for it; one
   thing is worth doing there because it is cheap now and a migration later: defining `expect.items.*.sha256` as the
   canonical file of 9.4, if that card checks or records item hashes at all.
4. **Under decision 8**: the finder now needs `mame-roms` on main before phase 0, not only from phase 2 (4.2): main's
   tools have no `--invert`, no `ink` and no `eng --first`, so a phase 1 on main alone would show readings it cannot
   convert.

## 16. Not verified, and risks

- The redraw targets (7.1) and the coarse / fine `runs` cost (6) are estimates from the one measurement of 4.3; the
  fine pass and the gapless PNG helper do not exist yet. If pure Python misses the tile target, the fallback is the
  ink map of 7.1, not a new dependency.
- The coarse phase sets for `strips`, `cols` and `bytecols` are unknown (6); until measured those orders scan every
  phase on small windows.
- The KS-order score (6, stage 4) is an idea, not a measured method; it ships as a hint or not at all.
- "Show as text" relies on the system copy of selected text working in the shell without a permission (4.7): expected,
  not run.
- Whether a `rawcarve.py region` line with the absolute paths of a ROM set stays under 512 bytes in a note
  (`zipout.note_commands` may shorten paths) was not checked; `--files @LIST` (7.5) is there if it does not.
- Section 8 follows `maker/recipe.py` as read on `desktop-export` at `9be5fc7`, a branch still in review: it was read,
  not run, and may change before it merges. The session-recipe entries of 8.1 (several `recipe` entries on one host
  file, the settings key) are new and not prototyped.
- That `621`'s storage is `binscan.py`'s `strips` was read from `g_bytecols` and the tools' docstrings, not run.
- `mame-roms` and main have diverged (4.2); everything here is written against `mame-roms` at `55c0be1` and must be
  re-read after its merge.
- Nothing here was run in the app: this is a design. The wireframe is a layout proposal, not a tested one; the
  narrowest supported window of the desktop app has to fit it (the right column folds under the viewer below that).

## 17. Review disposition (2026-11-23)

Two reviews of commits `fd36958` .. `2900c32`: SOL (approve with changes: 2 High, 4 Medium) and agy Neon (reject: 15
numbered findings in 9 groups). Each finding was checked against the code on main and, where it concerns them, the
tools on `mame-roms`. **fixed** = the spec was wrong or silent and now says the right thing; **changed** = the design
itself changed; **rejected** = not taken, with the reason. The rows are the first round's and say what was done then;
where they name `companion_file`, `carved-bdf` or companion source steps (SOL 2, Neon 2.1, 2.3, 2.5), the second round
replaced that mechanism with session recipes (17.1, last row), and the section numbers they cite are today's 8.1-8.3.

| Finding | Checked | Disposition |
|---|---|---|
| SOL 1 (High): phase 1 cannot carry a reading through conversion; `eng --first / --count / --invert` do not exist | True on main: `cut` copies bytes, `eng` takes offset / height / top only, no `--invert` anywhere. On `mame-roms` `eng` has them and `ink` rewrites any reading | **changed**: the finder is built on `mame-roms` merged (4.2, 14, 15.1); 8.2 says how every reading parameter reaches each command (`ink` before `cut` / `eng` when the reading is not plain; `bdf` takes the reading itself, with `--stride` and `--lsb` written out); a readings test compares pixels with independently built glyphs (13) |
| SOL 2 (High): prepared English companions are bypassed by the planner | True: `settings.py` prepares a companion only for `mac-fbit3`; others go by `path` | **changed**: 8.3: `companion_file` for every companion with `prep`, two forms of an English mark (`raw`, `bdf`), `needs` and failure propagation, `_companion_abs`, one planner for trial, run and headless; tests in 13 |
| SOL 3 (Medium): zip "in place" has no interface | True: `archive.py` only extracts; the tools take paths | **changed**: 7.6: bounded extraction of ticked members into the scratch, addressing, hash binding, `zip-member` source step in `BUILD.md`. Touches decision 9: 15.1 |
| SOL 4 (Medium): entropy windows can cut off the start of a font | True for blocks of one byte value | **fixed**: 6: `ascii` and `sets` scan the whole region; `runs` skips only blocks at 7.5 bits or more, keeps blank blocks, widens and joins windows, deduplicates; fixture (1b) |
| SOL 5 (Medium): the optional BIOS is needed by every face | True; `bdfface` refuses without a Latin companion | **fixed**: the BIOS is required in the example (9.1); 9.2 defines `optional` (a face is offered only when the files it reads are present; a recipe whose every face needs an optional file is refused); tests in 13 |
| SOL 6 (Medium): one anchor does not determine a KS grid | True | **fixed**: 5.4: a pitch or two anchors on different lead bytes, the unique `(L0, T0)` or 422, further anchors checked; test with two grids that agree on one anchor |
| Neon 1: the way in (`other` + `unknown`) locks out `.EXE`, zip, `.PFT`, size collisions | True: `MZ` is `fon`, a zip `archive`, and `dos-raw` / `eng` / `ks-raw` go by size | **fixed**: 5 step 1: "look inside" on every readable single-file `other` entry, "open in the finder" on size-decided kinds; the library hashes on a size match whatever the kind (9.2); fixture (1c) |
| Neon 2.1: companions never run `prep`; `eng` does not pair with a BDF route | True | **changed**: as SOL 2; pairing by session, not by folder (8.3) |
| Neon 2.2: phase 1 cites flags that are not on main | True for `eng` and `--invert`. Not true of `bdf`: main's `bdf` has `--first`, `--count`, `--lsb`, `--stride`, `--order` (`rawcarve.py` lines 308-320) | **changed**: as SOL 1; 4.1 and 4.2 now list what each branch has |
| Neon 2.3: single-source pipeline, settings key, re-detect wiping marks, in-process `prepared_bytes`, the 512-byte field cap | True, each of them | **changed**: 8.1 (entries rebuilt from applied marks on every detect, keyed with session and item, `inputs` checked like `path`, no `prepared_bytes`); 8.2 and 7.5 (`@FILE` parameter files persisted in `build-<id>/finder/`). Whether a region line passes 512 bytes is not verified (16) |
| Neon 2.4: 16x16 English raw files are refused downstream | True on main; `mame-roms` `jamoset.py` reads the 8,192-byte form, `johab844.py` does not | **fixed**: 5.3: phase 2, a companion of `dos raw` and `bdfface` (as a BDF), not of `johab844` |
| Neon 2.5: `carved-bdf` + `mkfont` meets two known problems | True (U+00AD in `ksx1001-nohanja`; the first BDF glyph as `.notdef`) | **changed**: no `mkfont` route and `chars` = `ks-hangul` only in version 1 (3, 8.3, 9.4) |
| Neon 3.1: `mmap` and truncation = SIGBUS | True in principle | **changed**: 7.2: never `mmap` a user's file; `pread` of bounded lengths; two renders at a time |
| Neon 3.2: FIFO hang, symlink TOCTOU | True for a plain `open()`; the tools use one | **fixed**: 7.2 (the opening rule on the descriptor), 7.5 (the same rule in the three tools) |
| Neon 3.3: no in-place zip reader | True | **changed**: as SOL 3 |
| Neon 4.1-4.2: idle sweep and run completion remove the scratch | True | **changed**: 7.2: the scratch is disposable and rebuilt, finder requests touch the job, running tools block the sweep, session locks join `_sweep_locks`; lifecycle tests |
| Neon 4.3: shutdown leaks finder tools | True as designed (my text named `toolreg` only) | **fixed**: 7.2: one bounded runner in `preview`'s live table and `toolreg` |
| Neon 4.4: `paths` outside the job's roots; job state | True | **changed**: the endpoint takes entries of a detected job only (7.2, 7.3); "find a font in a file" is choose + detect + open (5) |
| Neon 5: "one file" against the 86Box pair; the optional BIOS | True | **fixed**: phase 1 = one file a mark, several files a session (5, 14, 15.1); the BIOS as SOL 5 |
| Neon 6: 4129 is wrong (6177); the grid solver is underdetermined | True: (0xB0 - 0x80) x 128 + 0x21 = 6177 | **fixed**: 4.10, 5.4, 7.3 |
| Neon 7.1: coarse phases miss 24x24 at offset 2 mod 3 | True | **fixed**: 6: one phase a byte of a stored row; other orders unmeasured, said so; fixture (3b) |
| Neon 7.2: the scan budget | True that all geometries do not fit 60 s on a large region | **fixed** by saying what happens: a priority order, "not scanned" with a button, the arithmetic in 6. **rejected**: a smaller default window; the order and the report do the same without hiding part of the file |
| Neon 7.3: dropping blank blocks splits sparse grids | True | **fixed**: as SOL 4; fixture (3) with blank rows |
| Neon 7.4: `render --png` has gaps and zlib level 9 | True | **fixed**: a gapless level-1 helper (5.1, 7.5) |
| Neon 8.1: `localStorage` does not survive a quit | True (`fromPartition('maker')`) | **changed**: `prefs.json` through `/api/prefs` (11) |
| Neon 8.2: the clipboard is denied | True | **changed**: "show as text" in a selectable box, no permission added (5.1); not run (16) |
| Neon 8.3: `maker/recipes` is not packaged, no `recipe` command | True | **fixed**: 7.5 |
| Neon 8.4: drift tests | True | **fixed**: 7.5, 13 |
| Neon 9.1: `nkpspec.py` reads without a cap | True | **fixed**: 7.5 |
| Neon 9.2: export confinement and overwrite | True as written | **fixed**: `_OutputTree`, a name of the finder's own making, nothing replaced, listed in the desktop doc (7.4, 8.4) |
| Neon 9.3: recipe endpoints, inline compose bounds, region size, `route` enum | True | **fixed**: 7.3 (`PUT /api/recipes/<rid>`, containment, 500), 9.4 (compose bounds, region rules, closed `route` and `layout` lists) |
| Neon 9.4: host checks, `no-store`, nothing derived in `job.json` | True | **fixed**: 7.2, 7.3, 7.4, 6 |
| Neon 10.1: compressed OS/2 fonts shown as "packed" | True that the finder would say so | **rejected** as a feature (non-goal, section 3: the finder does not decompress and `os2dbcs.py` keeps its own recipe); the "packed" message is the honest one |
| Neon 10.2: `kind_of` does not know RAR / 7z / gzip / xz / LHA | True | **fixed**: 7.5 |
| Neon 10.3: word swap, bottom-up, rotated, bit-packed rows | True that they were unnamed | **fixed** as non-goals (3) |
| Neon 10.4: JIS / Big5 / CP437 | True that they were unnamed | **fixed** as non-goals, and the 94 x 94 signature reworded (3, 7.5) |
| Neon 11.1: `--mask-font none` drift | True: `_bdfface_fit_commands` omits it | **fixed** for the finder's fit route (8.3) and tested with the variable set (13). **rejected**: changing the existing `bdf-ksc5601` route here; it is noted for that route's owner |
| Neon 11.2: sample text and canvas | True: the page's sample differs from the recipes' | **fixed**: 8.5 |
| Neon 11.3: a synchronous trial | True | **changed**: the trial is started, polled and cancellable (5, 7.3, 7.4) |
| Neon 11.4: `SPEC.json` only in the scratch; colliding file names | True | **fixed**: 8.2, 8.4 |
| Neon 12: the line reference | True (`_ROUTES` is at 639) | **fixed**: named by symbol |
| Neon 13: no `dest` in a face | True | **fixed**: 9.4 |
| Neon 14: long strips against `MAX_CANVAS` | True for one column | **fixed**: 5.1 |
| Neon 15: test gaps | True | **fixed**: 13 |
| SOL note: the `mame-roms` APIs were not in the reviewed checkout | - | The branch is `mame-roms` at `55c0be1` of the same repository (`git show mame-roms:tools/rawcarve.py`); 4.2 lists what was read there |

### 17.1 Second round (2026-11-23, on `4c23535`)

SOL: approve with changes (its six first-round findings addressed, the first partly). agy Neon: approve with changes
(all fifteen addressed, the rejections accepted). New findings, and what t_97acecf9's code showed when it was read for
this round:

| Finding | Checked | Disposition |
|---|---|---|
| SOL r2 1 (High): rewriting every raw set as plain rows breaks `621` | True: `jamoset.py` `open_621` reads `g_bytecols` (= `strips`), and the headered and printer layouts are not uniform plain glyphs either | **changed**: 8.2's per-layout contract (selection is not storage): `ink` + `cut` only for `844` / `1044-san` at their headerless sizes; `621` only in its own storage; the others plain only; printer layouts not offered; refused at the mark and at validation; the pixel oracle covers each row (13). `jamoset.py` is not changed |
| SOL r2 2 (Medium): session sources as positional `fNN` ids | True: `detect` numbers in scan order | **fixed**: 7.2: stable identity (root path, relative path, member), re-resolved on detect and source changes; identity test (13) |
| SOL r2 3 (Medium), Neon r2 1 (Important): the two English forms disagree when `top` is not 0 | True: `rawcarve.py bdf` has no padding and `bdfface.py` takes the ASCII BDF's ascent | **changed**: 8.2: the BDF form is cut from the padded raw form (no `--top` added to `rawcarve.py bdf`; `--ascent` juggling rejected as the more fragile of the two fixes offered); tests with 8x8 at `top` 4 and 8x14 at `top` 1 beside 16x16 Hangul through both routes |
| SOL r2 4 (Medium): whole-region scans against the 16 MiB cap | True | **fixed**: 6: windows within the cap overlapping by the candidate span minus one, absolute offsets, deduplication, joined runs; a 32 MiB fixture |
| Neon r2 2 (Important): `from` required on a fit blocks jamo-only recipes and diverges from the self-contained route | True of the schema text. The code already builds `precomposed.svf` inside the fit's step, so deselecting the precomposed face is harmless there | **fixed**: 8.3, 9.4: a fit is self-contained and takes `from` or `hangul` + `english`; the example command names `precomposed.svf` |
| Neon r2 3 (Minor): FNT / FON "no openable size" is `bitmap`, not `other` | True (`detect.py` lines 678, 692) | **fixed**: 5 step 1; fixture (1c) |
| Neon r2 4 (Minor): `ink` then `cut` on headered or dual-size layouts | True | **fixed**: with SOL r2 1 |
| Neon r2 5 (Minor): `/api/recipes` and `/api/prefs` wording and hardening | True | **fixed**: 7.3; tests in 13 |
| t_97acecf9's code goes further than 9.4 (`english` lists, `or-files`, value ranges, `bdfface` on `compose`, one `recipe` entry a set, per-step carving) | Read in `maker/recipe.py`, `routes.py`, `detect.py`, `settings.py` on `desktop-export` | **changed**: section 8 rewritten on that model (a session recipe, no companion entries, no `carved-bdf` / `carved-spec` kinds: this withdraws the first-round answer to SOL 2 / Neon 2.1, which generalised `companion_file`); 9.4 brought in line; 9.5 lists both directions |

### 17.2 Third round (2026-11-23, on `3adb284`)

SOL: approve with changes (its four second-round findings addressed). agy Neon: approve with changes (all addressed).
New findings; the Neon ones were checked against `desktop-export`, which moved to `a103f56` meanwhile.

| Finding | Checked | Disposition |
|---|---|---|
| SOL r3 1 (Medium): a run split by a window edge is dropped below `--min` before it can be joined | True: `binscan.py` emits only runs of `--min` inked glyphs | **fixed**: 6 and 7.5: windowed `runs` reports unfinished edge runs, joined before `--min`; fixture with 20 + 20 glyphs |
| SOL r3 2 (Medium): persisted parameter files collide across sessions | True | **fixed**: 8.2, 8.4: `build-<id>/finder/<recipe id>/<item>.<what>`, session recipe ids unique in the job. Face or form in the name **rejected**: a parameter file belongs to an item |
| SOL r3 3 (Medium): an item's `expect` hash is ambiguous with two forms | True | **fixed**: 9.4: one canonical file an item kind, checked once, independent of selection and order |
| Neon r3 1 (Important): `recipe_routes` finds built-in recipes only | True (`routes.py` 425, `settings.py` 327 call `recipe.get`) | **fixed**: 8.1: one `recipe.resolve`; how it is passed down is left to phase 0 |
| Neon r3 2 (Important): the padded English BDF's ascent in the wrong coordinates | True: `ascent` is bounded by the item's H and passed to a 16-row BDF | **fixed**: 8.2, 9.4: the 16-row BDF's ascent is the Hangul item's (else `top` + the item's, else 14); tested |
| Neon r3 3 (Important): `_recipe_entries` relabels in place; `files` pairs have no zip member | True | **fixed**: 8.1: session entries appended with the host's `file_id`; a three-element `files` value from phase 2; the unpacking sites named |
| Neon r3 4 (Minor): the `region` command's syntax | True; t_97acecf9 moved to `--group` | **fixed**: 8.2 |
| Neon r3 5 (Minor): requests racing the background hash | True | **fixed**: 7.2 |

