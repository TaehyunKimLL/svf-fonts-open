# Maker controls and the WASM preview: design

Card t_9acea7ab: "maker: controls and preview for AA 2 bpp, baseline shift and top/bottom clipping, jamo-set from
decomposable fonts with piece identity check". Written 2026-11-03 on branch `maker-controls` of the OFL-only repository
(`svf-fonts-open`, base `01a943f`) for a builder who has not seen the repository; revised the same day after two
independent reviews (section 16 lists every finding and what was done with it). Every fact below was read from the tree
or run on this host; what was not run says "not verified". Choices the owner has not made are marked "(design call)"
where I decided for the builder and collected again under "Decisions needed" (section 14; section 15 holds the
controller's rulings on the first list).

Read with this document: `docs/maker-audit.md` (what the maker is, the gap list; its section 3 is the preview audit
this design answers), `docs/recipes.md` (the methods the controls expose: "Jamo sets from TrueType and OpenType fonts",
"Anti-aliased (2 bpp) faces", "Baseline, vertical shift and clipping"), `docs/superpowers/plans/2026-11-03-maker-input-kinds.md`
(what was just built: the `source` step, `prep` ops, the instance choice), `spec/SVF.md` (the face format),
`c/include/svf.h` (the renderer API) and `c/ports/web/README.md` (the WASM glue).

## 1. Intent

The maker (`maker/`, a stdlib HTTP server plus one ES-module page) converts uploaded fonts into SVF faces by running the
repository's tools as subprocesses. After card t_f3ef3189 it reads every input kind the recipes name except GSUB-mask
jamo sets and Mac `fbit`, but it still shows a face only as a server-drawn PNG after a run, and it exposes a fraction of
the controls the recipes use: no ascent for the jamo routes, no `--fit-cell`, `--width`, `--latin`, no per-glyph dy, no
`--aa-refine` or `--binarize` choice, two named ranges, no view of what a cell cuts, no jamo set from a decomposable
font, and no check that a fitted piece is the jamo it stands for. This design closes those gaps (audit gap list items
1-4) and moves the preview into the browser, drawn by the C renderer compiled to WebAssembly, so that what the page shows
is what every port draws.

## 2. Goals

- Every produced face is drawn in the page by the WASM build of `c/src` (`c/ports/web/svf_web.c`), from the face's
  bytes fetched from the server: any bpp, any target kind, scaled, re-drawn on every control change without a server
  round trip (sample text, scale, target, threshold, colours, baseline guides, a per-glyph dy to try, and, on the routes
  where the ascent is only the header's baseline row, an ascent to try).
- Per-glyph inspection: a glyph grid, the pieces of a syllable, the metrics of a glyph, all from the module.
- The controls of recipes.md reachable from the page, validated before a run, carried into the job's argv and build log
  exactly as a command line would: ascent on every route that honours one, `--width`, `--latin`, `--fit-cell`, a dy
  table applied by `tools/svfdy.py`, `--aa-refine`, `--no-clean`, `--binarize`, the named ranges of `mkfont.py`.
- Top/bottom clipping visible before the build: which glyphs a cell at an ascent cuts, by how many rows, with the ink
  drawn and the cell outlined, for any ascent the user types, computed by the same rule as the build.
- A jamo set from a decomposable font: the GSUB-mask route (`jamoset.py --from-ttf --mask-font`, 1 bpp) when the optional
  libraries are present, and `jamovec.py master` without `--components` (vector separation) always.
- A piece identity check: with the optional recogniser, a per-piece score and a pass/warn/fail flag; without it, the
  structural check the routes already run (`--check`: all 11,172 syllables compose) and the words "identity check
  unavailable".
- Source previews that show the prepared font (the chosen variable instance, a Mac font after `macsfnt.py unicode`, a
  TTC face after `ttc-face`), not the uploaded file's default face.
- All of it provable with synthetic or OFL fixtures; the existing gates stay green.

## 3. Non-goals

- Changing a pixel the renderer draws: `c/src` is not touched (section 6.4 shows every override is a pen offset in the
  page). The byte-for-byte oracle `tools/test_web_picker.py TestModule` (WASM vs `tools/svfline.py`) stays the proof;
  `svfline.py` is not a preview path any more.
- Shipping a recogniser, its weights or training data in this repository, or training anything.
- A mask fit at 2 bpp (`jamoset.py` has none: section 4), a per-glyph dy on jamo faces (section 7.5), editing glyphs,
  8 bpp faces, Mac `fbit`, HWP `.PFT`, local path mode (card t_cbd14d61), Electron (t_f04f1355), packaging
  (t_e64a56a7). Nothing here may assume a tailnet or systemd; every endpoint binds as today (127.0.0.1).
- Live re-fitting: a jamo fit takes 12-92 s (recipes.md, verified there); a fit result is a job step, never a preview.
- Shifting a built outline face against its companion after the build (a header-ascent patch tool): not in this card,
  see D8.

## 4. Constraints and facts (checked 2026-11-03 on this host unless marked)

Renderer and module:

- `c/ports/web/svf_web.c` exports `svfw_open`, `svfw_target`, `svfw_target2`, `svfw_scale`, `svfw_measure`,
  `svfw_draw`, `svfw_reset`, `svfw_info`, `svfw_has`, `svfw_order` (4 slots; JS owns the face bytes and the pixel
  buffer; the glue mallocs scratch, `c/src` never allocates). `web/build.sh OUT` builds `svf.js` (ES6 module,
  `MODULARIZE`, `EXPORT_NAME=SvfModule`, `ENVIRONMENT=web,node`, `ALLOW_MEMORY_GROWTH`, runtime methods `HEAPU8`,
  `HEAP16`, `HEAP32`) and `svf.wasm`; built in 2-2.5 s (39,234 + 6,623 bytes), byte-identical across output paths
  (review probe). emcc is at `~/opt/emsdk/upstream/emscripten/emcc` (not on PATH; `build.sh` finds it through
  `EMSDK`). `web/dist/` is gitignored.
- `c/include/svf.h` has, not exported yet: `svf_metrics_of(f, cp, svf_metrics*)` (advance, bearing_x, ink_w, dy;
  returns 1/0/-1; **a composed syllable or compat jamo of a jamo face returns 1 with `{JSET advance or cell_w, 0,
  cell_w, 0}`**, `c/src/svf_face.c:365-372`, so no synthesis is needed in the glue), `svf_cmap_cp(f, i)` (`uint16_t`
  index), `svf_cell_bytes(f)`, `svf_glyph(f, cp, cell, len)` (composes a syllable of a jamo face itself),
  `svf_jamo_pieces(f, cp, out[3])` (**piece numbers**, `SVF_PIECE_BLANK` included; the glyph of piece p is at code
  point `SVF_PIECE_BASE + p`, `svf_jamo.c:1117`), `svf_compose`, `svf_is_jamo`, `svf_has` (true for composed code
  points too).
- Placement (`c/src/svf_draw.c`): the line is walked by `walk_next`: the face of a code point is the first slot in
  chain order with `svf_has` (`face_for`); a code point no face has moves the pen by `missing_advance`; the pen advances
  by `SCALE_LEN(advance)` after a non-mark glyph; a mark (`svf_is_mark_default`: U+0300..036F, or the chain's
  predicate) advances 0 and is placed at the current pen minus its scaled negative bearing when the face has
  `SVF_FLAG_MARKS_AT_ORIGIN`; the cell's top row is `y_baseline - SCALE_LEN(ascent) + SCALE_LEN(dy)` (`:1277`).
  `SCALE_LEN(v) = (v * num + den / 2) / den` after the ratio is reduced (`svf_scale.c:17`, half away from zero for
  negative dy), so `S(a) + S(b) != S(a + b)` in general. `svf_measure_utf8` derives the line's ascent/descent from
  each placed face's ascent and the glyph's dy (`:219-220`). The face header's ascent is byte 16
  (`svf_face.c:97`); the open validates no relation between ascent and cell height.
- The size gates of the MCU profiles (`c/ports/profiles.txt`, the tables of `c/bench/MEASUREMENTS.md`, the CH582
  `image_sizes.py` gate) measure `c/src` builds; the web port is in none of them, and `make -C c check` does not
  compile `c/ports/web`.

Maker:

- Previews today: `preview.source_png` (Pillow) for FreeType-readable sources at the first size; DOS raw and SVF sources
  are baked into `work/preview/<font id>.svf` by `preview.bake_source_face` and drawn by `svfline`; result faces are
  drawn by `svfline` in the worker (`jobs.Worker._read_back` -> `preview.result_png`), served by
  `GET /api/jobs/<id>/preview/<font>/<step>.png`. A settings PUT drops a font's previews when one of
  `dos_layout, sizes, kinds, latin_companion, instance` changed (`server._changed_preview_fonts`, `server.py:184`);
  `options` is not a key today, although `_jset_flags` feeds the bake.
- Static files are served from `maker/static/` with `STATIC_TYPES` = html, js, css, png (`server.py:46`); the `Host`
  and `Origin` check (`_check_same_origin`) runs for PUT, POST and DELETE only (`_STATE_CHANGERS`).
- Settings (`maker/settings.py`): batch keys `dest kinds layout sizes bpp range preset options`; per-font keys add
  `selected experimental dos_layout latin_companion licence names licence_name note_name instance`;
  `DEFAULT_OPTIONS = {"mkfont": {cell, ascent, mono_hint, clip_cell, space_advance}, "jamoset": {embolden, symbols,
  jset_version}}`; a value is an int-or-null or a bool, nothing else (`_options_type_errors`); **option keys are
  unique across tools**: `_own_option_keys` flattens them ("the two tools' keys are disjoint, so the tool name does not
  matter", `settings.py:374`), `_option_errors` reads them flat, and `maker.js` addresses a panel field by
  `data-field="<key>"`. `_ascent_cell_errors` checks the ascent against the cell when set, else against **every** size.
  `presets.panel_argv(options, kind, route_label, bpp)` turns options into flags; `routes.apply_flags` merges a
  preset's fragment and the panel; `routes.VALUED` lists the flags that take a value; `routes._with_extra` applies the
  merged flags to the **last** argv of a route (`_bdfface_fit_commands` builds two). `maker/static/maker.js` mirrors
  `ROUTES`, `PRESETS`, `OPTION_VISIBLE`, `PREVIEW_KINDS`, `SOURCE_WORDS` as strict JSON, and
  `maker/test/test_server.py test_page_js_tables_match_python` runs `offeredRoutes(font)` under node against
  `routes.routes(font)` for `canonical_fonts()` and derives `OPTION_VISIBLE[label][bpp]` from the flags
  `panel_argv` emits with every option set (`every`), mapping each flag to its key (`flags`).
- The worker's subprocess env is `ENV = {PATH, HOME, LANG}` (`jobs.py:66`, `preview.py:48`): `JAMOSET_PYLIB`,
  `JAMOSET_MASK_FONT` and `SVF_RECOG_DIR` do not reach a tool. A note's command lines are capped at
  `naming.MAX_FIELD_BYTES` = 512 bytes a line (`zipout`, `server._check_notes`).
- Tests: `maker/test` has 539 `test_` functions (run through `~/.local/bin/heavy python3 -m unittest discover -s
  maker/test -p 'test_*.py'`). Fixtures are built in the tests (`maker/test/fixtures.py`, `inputfx.py`,
  `inputkinds.py`) or taken from `svf/` and `ttf/` (OFL). `detect.composite_test` classifies `ttf/neodgm/neodgm.ttf`
  as `outline-composite` (11,172 composite syllables); it is the only font in `ttf/` with the `ljmo`/`vjmo`/`tjmo`
  GSUB features (review probe).

Tools (the options this design exposes; `python3 tools/X.py --help` is authoritative):

- `mkfont.py`: `--cell H` (default = size), `--width W` (default = cell: `cell_w = args.width or cell_h`, `:803`),
  `--bpp 1|2|8`, `--ascent N` (**0 means "choose"**: `if args.ascent:`, `:880, :898`), `--clip-cell`, `--fit-cell`
  (lowers the size until no ink is cut; with both flags the clip counting is skipped, `:877`), `--latin`,
  `--mono-hint`, `--space-advance`, `--punct-extra`, `--ink-advance`, `--only-listed`, `--fallback-ttf`, `--limit`,
  `--require`, `--unicode` with names from `NAMED_RANGES` (among them `ascii`, `ksx1001-hangul`, `ksx1001-nohanja`,
  `ksx1001-symbols`, `ksx1001`, `hangul`/`cp949-hangul`, `cp949`, `jamo`, `latin1`, and `file:PATH`). Clipping is
  reported on stdout only: `fit_counts` (code points over the top / bottom / too wide: `top + ascent < 0`,
  `bottom + ascent > cell_h`, `right - left > cell_w`), `clipped_ink` (full and fringe pixels cut), the first 40 cut
  characters; `measure_boxes` gives each glyph's ink box relative to the pen (`(left, top, right, bottom)`, y down
  from the baseline, at the bake's bpp cut) and is what every count is derived from; `render()` nudges a glyph that
  leaks above or past the right edge unless `--clip-cell`. The face is packed by `jamoset.pack_svfn`: cell sides and
  ascent are bytes (0..255). Probe cost (review): `--clip-cell` over `ascii,ksx1001-hangul` 0.51 s, over `ascii,cp949`
  2.35 s, 35-50 MB.
- `jamoset.py`: `--ascent N` is honoured by `build_from_source` only (DOS raw, hanterm; `:3107`, **0 means the
  default**: `ascent = ascent or ...`, `:2112`); **`--from-svf` ignores it** (`fit_font(..., face.ascent, ...)`,
  `:3084-3086`); `--baseline N` is the frame of `--from-ttf` (`:3055`); `--bpp 2` **branches to `main_aa` before
  `--mask-font` is read** (`:3029-3030`; `jamoaa.build` has no mask parameter), so a mask fit exists at 1 bpp only;
  at 1 bpp, when `clean` is on (`--clean`, or the default for `adaptive`), `fit_prep` builds donor masks and
  `fit_font` **discards the mask font for them** (`if piece_masks is not None: mask_font = None`, `:2371-2374`), so a
  mask fit needs `--no-clean`; without `--mask-font`, a 1 bpp fit uses `$JAMOSET_MASK_FONT` or a NotoSansKR outside
  this repository whenever `freetype` and `uharfbuzz` import (`:3034-3041`, `mask_auto`), and `--mask-font none`
  turns that off; `--aa-refine N` (default 2), `--clean/--no-clean`, `--binarize mono|threshold|ridge` (1 bpp
  `--from-ttf`; `mono` needs freetype-py), `--threshold`, `--mask-radius`, `--pylib DIR`, `--report FILE.json`,
  `--advance`, `--cell WxH` (from-ttf). The mask path needs `freetype` and `uharfbuzz` importable
  (`jamofit.load_libs`, `JAMOSET_PYLIB`). Neither module is installed here, nor numpy or torch.
- `jamovec.py master FONT -o M.json [--adaptive] [--decision-px 48] [--components] [--pylib]` and `render M.json
  --size N --bpp 1|2 --binarize threshold|ridge [--cell] [--baseline] [--symbols] [--check]` (**no `mono`**:
  `choices=("threshold", "ridge")`, `:401`). `master` without `--components` is the raster separation at the decision
  size through `jamoaa.OutlineFace`, which loads fontTools only (`jamoaa.py:197-198`). Timing of that mode: not
  verified (recipes.md verified `--components` only: 25 s for neodgm).
- `bdfface.py`: `--ascent N`, `--hangul-ascent N`, `--hangul-advance`, `--cell WxH`, `--chars-from FILES`.
- `svfdy.py IN OUT --json dy.json` (`{"0x67": 1, "106": 1, "y": 1}`) **sets** each named glyph's dy (it does not
  add), refuses a dy on a jamo piece and a dy outside -128..127 or past the cell height (`jamoset.dy_range`), refuses
  a face without a metrics table, keeps everything else, re-verifies (`verify`). A code point the face lacks is only
  counted (`missing`, `:92-105`; the tool exits 0), and a jamo face's composed syllables and compat jamo are not in
  `f.glyphs`, so a dy on them is silently dropped.
- `jamomerge.py --recog` is the only recogniser hook: `Scorer.__init__` inserts `$SVF_RECOG_DIR` (or `.`) into
  `sys.path`, imports `recog`, calls `recog.load("11-12")`, `recog.split(syllable_indices)` -> (L, V, T) and
  `recog._heads(net, numpy bool[n, h, w])` -> three log-probability arrays; a syllable is "read" when each head's
  argmax is its jamo (`jamomerge.py:918-960`; `Scorer.arr` builds the numpy array). Whether those weights take any
  cell size is not verifiable here (no weights on this host); `tools/` has no other "recog" code.

Host: python3 with fontTools 4.66.1 and Pillow 10.2.0; `node` at `/usr/bin/node`; `chromium-browser`, `chromium`
(snap) and `google-chrome` on PATH; `web/test/node_modules` absent (no playwright-core: `web/test/check.mjs` exits 2,
`TestPage` skips).

## 5. Binding decisions (the owner, 2026-11-03)

1. One renderer. The maker's preview is the browser, drawing with the WASM build of the C renderer. `tools/svfline.py`
   remains the test oracle (the WASM-vs-svfline byte test exists) and is not a preview path.
2. The identity check is optional. The maker and the tools use a recogniser only when `SVF_RECOG_DIR` names a folder
   holding `recog.py` and its weights (numpy + torch, scoring only, never training). Without it the UI says "identity
   check unavailable" and the structural check stands (the table composes all syllables). No recogniser or weights are
   added to this repository now (their training data provenance is unverified).
3. The repository stays OFL-only and free of proprietary data: tests use synthetic or OFL fixtures. The app will be
   wrapped in Electron with a Python sidecar on 127.0.0.1 (cards t_f04f1355, t_e64a56a7): no design choice may assume
   a tailnet or systemd.

## 6. The WASM preview (A)

### 6.1 Where the module lives and how the page gets it

- (design call) The maker serves the built module from its own static tree: `maker/static/wasm/svf.js` and
  `svf.wasm`, produced by a new `maker/build-wasm.sh` that runs the same `emcc` line as `web/build.sh` (same flags, same
  `c/src/*.c` + `c/ports/web/svf_web.c`) into `maker/static/wasm/` and nothing else (no faces, no index). Both scripts
  share the compile line through one file, `c/ports/web/emcc-flags.sh` (sourced), so the picker and the maker cannot
  drift; the build is path-independent (verified), so the two outputs are byte-identical. `maker/static/wasm/` is
  gitignored like `web/dist/`.
- `STATIC_TYPES` gains `".wasm": "application/wasm"` (streaming compile needs that MIME type). Static files are served
  with `Cache-Control: no-cache` plus an `ETag` of size+mtime (section 6.5).
- The page imports it as the picker does: `const M = await (await import("/static/wasm/svf.js")).default();` from a
  new module `maker/static/svfview.js` (the drawing layer, section 6.4). A 404 on `svf.js` is a page notice "preview
  module not built: run maker/build-wasm.sh" and every preview cell shows that text; no PNG fallback is kept (decision
  5.1 and ruling D5), and the worker stops writing `preview.png` (section 6.5).
- Packaging (t_e64a56a7) ships the two module files and `svf/dos/NEODG16.SVF` (the Latin companion the page falls
  back to, section 6.2) as data; nothing here depends on the repo checkout at run time beyond `maker/static/`. The
  Electron shell (t_f04f1355) must load the page from the sidecar's own origin (`http://127.0.0.1:PORT/`), as a
  browser does today: the `Host`/`Origin` check, which 6.2 extends to the byte-serving GETs, accepts only `http(s)`
  origins on the bound host, so a page loaded from `file://` or a custom scheme would have every request refused
  (the audit's section 4 says the same for the state changers).

### 6.2 Endpoints that serve bytes

All GET, read-only, under the job, path-checked with `_inside` like the PNGs, served `application/octet-stream` (JSON
ones `application/json`) with `Cache-Control: no-cache`, `ETag: "<size>-<mtime_ns>"` and `If-None-Match` -> 304.
(design call, review M5) The new GET routes run `_check_same_origin` too: they hand out font bytes, and a GET needs
the `Host` check against DNS rebinding; the regex of each route admits only `[0-9a-f]{12}` jobs, `f\d+` fonts, `s\d+`
steps, `\d+` sizes and bpps.

| Endpoint | Serves | 404 when |
|---|---|---|
| `GET /api/jobs/<id>/face/<step>.svf` | the step's `output` file of a `done` face step (kind `precomposed`/`jamo`) | the step is not that job's, not done, kind `source`/`prepare`, or the file is gone |
| `GET /api/jobs/<id>/source/<font>.svf` | `work/preview/<font id>.svf`: the baked source face of a `dos-raw` / `svf-*` entry (today's `bake_source_face`, under the same per-font preview lock; baked on demand as the PNG is today) | the kind has no baked face (then the page uses the source PNG, section 10) |
| `GET /api/jobs/<id>/probe/<font>/<size>/<bpp>.svf` and `.json` | the clipping probe of section 8 | the font's precomposed route is not mkfont, or the probe failed |
| `GET /api/jobs/<id>/report/<step>.json` | the `--report` JSON of a done mkfont step (section 8.2) | the step has none |
| `GET /api/jobs/<id>/identity/<step>.json` | the identity report of section 9.4 | the step has none |
| `GET /api/repo/face/<group>/<FILE>.SVF` | a face of `svf/` (only `dos/NEODG16.SVF` is needed: the Latin companion `preview.LATIN_FALLBACK`); the route regex is `[A-Za-z0-9_-]+/[A-Z0-9_]+\.SVF`, then `_inside(svf_dir)` | not a file under `svf/` |
| `GET /api/caps` | `{"wasm": bool, "mask_libs": bool, "recog": bool}` (booleans only, no paths), computed once at server start without importing anything heavy: `wasm` = the two module files exist; `mask_libs` = `jamofit.libs_available(os.environ.get("JAMOSET_PYLIB"))` (it imports freetype/uharfbuzz, which are light, and is what the tool does); `recog` = `SVF_RECOG_DIR` names a directory with `recog.py` and `importlib.util.find_spec` finds `numpy` and `torch` (no import) | never |

The source preview PNG endpoint stays for FreeType-readable sources (section 10). `_changed_preview_fonts` and
`_remove_preview` already cover `work/preview/<font id>*`; the probe cache lives under `work/preview/<font id>/probe/`
so the same glob clears it (the key list is in 6.5).

### 6.3 Exports to add to `c/ports/web/svf_web.c`

Only the glue changes; every new export is a thin call into the existing public API of `svf.h` with the argument
checks the glue already does for its other exports. Signatures (all `EMSCRIPTEN_KEEPALIVE int`, returning an
`svf_err` unless said otherwise; a slot not open is `SVF_E_ARG`):

```
svfw_metrics(int slot, uint32_t cp, int32_t out[4])   out = advance, bearing_x, ink_w, dy; returns svf_metrics_of's
                                                      1 / 0 / -1 (-1 also for a slot not open; out untouched). A composed
                                                      syllable returns 1 with the JSET advance (the core does that)
svfw_cell_bytes(int slot)                             svf_cell_bytes, 0 for a slot not open
svfw_glyph(int slot, uint32_t cp, uint8_t *cell, uint32_t len)
                                                      svf_glyph into JS memory: the stored rows (MSB first, rows padded
                                                      to a byte); a syllable or compat jamo of a jamo face is composed
                                                      by the core. len must be >= svfw_cell_bytes (SVF_E_NOMEM)
svfw_pieces(int slot, uint32_t cp, uint16_t out[3])   svf_jamo_pieces: returns the count 0..3 (0 = not composed); out
                                                      holds PIECE NUMBERS (SVF_PIECE_BLANK = 0xFFFF for a blank slot);
                                                      the page adds SVF_PIECE_BASE once to draw a piece
svfw_cmap_cp(int slot, int i)                         the code point of table entry i, or -1 when i < 0, i >= the
                                                      glyph count or the slot is not open (checked before the uint16
                                                      cast, so no index wraps)
svfw_line_box(const char *text, int len, int x, int baseline, int32_t out[4])
                                                      the scaled line's box for the current chain and scale:
                                                      out = x, baseline - extent.ascent, extent.width,
                                                      baseline + extent.descent, from svf_measure_utf8; returns its
                                                      error. A convenience over svfw_measure so the page draws guides
                                                      with the numbers the draw uses
```

Rules: no new state in the glue (the four slots, one target, one scale as today); `svfw_glyph` reads into a JS-owned
buffer (the web glue opens mapped faces only, so `svf_compose`'s streamed-face scratch rule does not apply). No ascent
or dy setter is added: there is no hook in `c/src` for one, and adding one would touch the AVR/M0+ readers. The two
overrides are done by the page (6.4); `svfw_metrics`, `svfw_has` and `svfw_line_box` are what it needs.

### 6.4 The page's drawing layer: `maker/static/svfview.js`

One ES module that owns the module instance and draws into `<canvas>` elements through `svfw_target2` GRAY8 (the page
converts to ImageData; RGB565 and the mono kinds are offered as "target" choices the way the picker does, drawn by the
module, so a 1 bpp target shows the renderer's own threshold of a 2 bpp face). Exported functions:

- `load()` -> the module (once; rejects with the notice text when the files are missing).
- `openChain(byteArrays)` -> opens up to 4 faces in slot order, returns `[info...]` (`svfw_info` per slot). The page
  passes `[face, latin]` where `latin` is the job's companion precomposed face when one is done, else
  `/api/repo/face/dos/NEODG16.SVF`, exactly `preview.chain_for`'s rule, decided by `svfw_has(0, 0x41)`.
- `drawLine(canvas, text, {scale, target, threshold, fg, bg, guides})` -> `svfw_measure`, size the canvas (width + 2,
  ascent + descent + 2, the picker's and `preview.svf_png`'s geometry: pen at x 1, baseline at ascent + 1), draw with
  one `svfw_draw`. With `guides`, the page strokes the cell top (baseline - S(ascent) of slot 0), the baseline and
  the cell bottom over the pixels (CSS layer, never in the module's buffer).
- `drawGlyphs(canvas, text, {scale, ascentOverride, dy, pitch, ...})` -> the per-glyph compositor, the one path that
  previews a header ascent or a dy without a rebuild. It mirrors `walk_next` (`svf_draw.c`) in JS:
  - `S(v)` = `SCALE_LEN` with the chain's reduced ratio: `Math.trunc((v * num + Math.trunc(den / 2)) / den)` for
    `v >= 0`, `-S(-v)` for `v < 0`.
  - **One `svfw_draw` call per code point**, marks included: the core places a combining mark (U+0300..036F, the
    default predicate the chain uses) at the current pen, never relative to its base (`walk_next`: `p->dx = w->pen`,
    minus the scaled negative bearing for a `MARKS_AT_ORIGIN` face), so a per-code-point call reproduces a line
    exactly, and a mark gets its own face, its own dy and advances 0 (review probe: 6/6 dy-on-mark cases, 9/9 ascent
    cases; a "base plus marks in one call" rule fails every dy case and was dropped).
  - The face of a code point is the first open slot with `svfw_has(slot, cp)` in slot order (`svfw_order` is never
    changed by the page); a code point no slot has advances the pen by 0 (the chain's `missing_advance`) and draws
    nothing; an invalid UTF-8 sequence is U+FFFD as the core does (the page validates its text before, so this does
    not arise).
  - Pen: `x += S(advance)` from `svfw_metrics(slot, cp)` after each non-mark code point.
  - Vertical: for a code point drawn by slot 0 only, `y = baseline + S(A) - S(A') + S(d_new) - S(d_stored)`, where
    `A` is slot 0's header ascent, `A'` the override (`A` when none), `d_stored` the glyph's dy from `svfw_metrics`,
    and `d_new` the page's dy for that code point when it has one, else `d_stored` (a dy **replaces** the stored one,
    as `svfdy.py` does). Every other slot draws at `y = baseline`. Because the core places a cell at
    `y_baseline - S(ascent) + S(dy)`, this is exactly where a face with header ascent `A'` and a stored dy of `d_new`
    puts the cell (verified by the review's probe: 20 of 20 cases over scales 1/1, 2/1, 3/2, 5/4, a face with stored
    dy and a two-slot chain, composed syllables under an ascent override included). The pixels are the renderer's;
    only the pen moved.
  - A composed code point of a jamo face (a syllable, a compat jamo drawn from a piece) has **no dy term**
    (`d_new = d_stored = 0`: its metrics dy is 0 and `svfdy.py` cannot set one) but takes the **ascent term like any
    slot-0 glyph**: on `dos raw`/`hanterm`, the routes with an ascent-to-try, nearly every drawn glyph is composed.
  - Limitation on `dos raw`/`hanterm` with `symbols` on: U+2026 and U+25A1 are drawn by `jamoset.symbol_glyphs(w, h,
    ascent, adv)`, i.e. the ascent is their frame, so a rebuild at `A'` keeps those two on the baseline while the
    pieces and the `--eng` glyphs move with the header. The page therefore draws those two code points **without**
    the ascent term when `symbols` is set (at `y = baseline + S(d_new) - S(d_stored)`), which matches the rebuild.
  - The `pitch` option replaces the advance by a fixed step (the glyph grid).
- `glyphCell(slot, cp)` -> `svfw_glyph` unpacked to a `Uint8Array` of levels (for the piece view and the identity
  panel); `pieces(slot, cp)` -> `svfw_pieces` (piece numbers; `drawPiece(slot, p)` draws `glyphCell(slot,
  0xF0000 + p)`); `codePoints(slot)` -> every `svfw_cmap_cp` (for a jamo face: its ASCII, symbols, compat jamo whole
  glyphs and the pieces at U+F0000+, **not** the syllables, which are composed; the grid offers a "syllables" view
  that lists U+AC00..D7A3 through `svfw_has`); `lineBox(text, x, baseline)` -> `svfw_line_box`.
- The line box of `drawGlyphs` is computed in JS by `svf_measure_utf8`'s rule over the placed code points (ascent up =
  `S(A') - S(d)`, descent down = `S(cell_h) - S(A') + S(d)`, each slot with its own ascent), so a descender lowered
  by dy enlarges the canvas as the spec says the line's descent grows.

Memory: face bytes are `_malloc`ed once per fetch and freed after `svfw_reset` when the chain changes (the picker's
rule, `c/ports/web/README.md`: bytes must stay while a slot uses them); the pixel buffer is reallocated when the
canvas grows. A face over 16 MiB is refused by the page (the server never writes one; `MAX_GLYPHS` bounds it).

**What the two overrides mean, per route (review C1).** The pen offset is exactly a header-ascent patch: the cell and
its ink move together. That is what `--ascent` does on the routes where the raster is fixed and the ascent is only the
header's baseline row: `dos raw` and `hanterm` (`build_from_source`). On every other route the ascent is the frame the
outline or bitmap is placed in (`mkfont --ascent`, jamoset `--baseline`, jamovec `--baseline`, bdfface `--ascent` /
`--hangul-ascent`): a rebuild at another ascent keeps every glyph on the baseline and changes only which rows the cell
cuts (review measurement: rebake 8..21 vs 7..21 ink rows, the pen-offset view 6..19). Therefore:

- the **ascent-to-try** control exists only on the `dos raw` and `hanterm` previews (header ascent); "apply" writes
  `options.jamoset.jamo_ascent`, and the next build draws what was shown (the raster is unchanged, the header byte is
  the typed value; the two `--symbols` glyphs are the exception handled above);
- on mkfont, the fits and bdfface the typed ascent drives only the clipping overlay of section 8, which is computed
  from the probe by the build's own rule; "apply" writes the route's ascent flag (and `clip_cell` for mkfont) and the
  build then cuts what the overlay showed. Glyphs are never shifted in those previews.
- the **dy-to-try** control exists on precomposed faces (section 7.5); "apply" writes the font's `dy` table, and the
  rebuilt face (svfdy sets exactly that dy) draws as shown.

Equivalence the tests pin (section 11): with no overrides, `drawGlyphs` of a text equals `drawLine` of the same text
byte for byte; with an override it equals `drawLine` of the face with header byte 16 patched and/or `svfdy.apply`
applied, at scales 1/1, 2/1 and 3/2, on a face with stored dy and a two-slot chain, and on a face that holds marks
(none in `svf/` has U+0300..036F: the test bakes one from `ttf/` with mkfont, as the review's probe did with
EB Garamond and U+0300..0304); `drawLine` equals `svfline.py line` (the existing oracle). `svfw_pieces` can return
piece number 0 (a real piece on NEODG16A): the page trusts the returned count, never a "0 means none" test.

What a result cell shows (the steps table's `result` column becomes a `<svf-preview>` block): the sample line
(`detect.SAMPLE_TEXT`, editable, kept per page), the scale (1/1 .. 4/1), target GRAY8 | MONO (threshold) | RGB565,
guides on/off, and a "glyphs" toggle that opens the grid (16 per row, pitch = cell_w + 2; a click selects a glyph:
metrics, the dy field on precomposed faces, the pieces of a syllable drawn side by side). The face facts
(`step.facts`) stay as text beside it; an mkfont step also shows its report's cut counts (section 8.2).

### 6.5 Caching and invalidation

- Face bytes are immutable for a step id once the step is `done`; the page keeps them in memory per `(job, step)` and
  refetches when `job.steps[i].state` or `seconds` changes after a re-run (`?job=` reload refetches everything). The
  server's `ETag`/304 makes a reload cheap.
- Server-side derived files of a font (`work/preview/<font id>*`: the source PNG, the baked source face, the prepared
  source of section 10, the probe) are dropped on a settings PUT when any of these effective values changed. The key
  list replaces today's tuple in `_changed_preview_fonts`:
  `dos_layout, sizes, kinds, bpp, range, preset, latin_companion, instance, experimental, jamo_route,
  options.mkfont.{cell, width, latin, mono_hint, space_advance}, options.jamoset.{jset_version, jamo_ascent, embolden,
  symbols}`. Not keys: `options.mkfont.{ascent, clip_cell, fit_cell}` (the page applies them to the probe data),
  `dy` (applied live to a result face), `options.jamoset.{aa_refine, clean, binarize}`, `options.bdfface.*` (none
  feeds a preview or probe). `_jset_flags` grows into `_bake_flags(eff)`: `--jset-version`, `--ascent` (jamo_ascent),
  `--embolden`, `--symbols` for the DOS-raw bake, so the baked source face shows the panel's values (today only the
  JSET version reaches it).
- Worker: `_read_back` stops calling `preview.result_png`; `step["preview"]` leaves the Step dict (`settings._step`)
  and the job JSON. Existing tests that assert it are rewritten in the same commit: `test_jobs.py` at lines 268, 309,
  333, 371, 566 (the Step shape and "a preview PNG exists / is None" assertions become "`step` has no `preview` key"
  and, where the PNG proved the face was readable, `quality.face_facts` of the output), `test_zipout.py:78` (the Step
  shape), `test_server.py:576-579` (the step-PNG GET: replaced by the `face/<step>.svf` tests of section 11). The
  source-PNG tests stay. `preview.result_png`, `svf_png` and `chain_for` remain in `preview.py` as oracle helpers for
  `test_preview.py` (its tests keep passing). `PREVIEW_KINDS` in `maker.js` stays the source-preview table.

## 7. Controls (B)

### 7.1 Which flag, which route

Option keys are unique across tools (the invariant of section 4), so the three ascents have three names.

| Control (recipes.md) | Setting | Flag | Routes (label) | Validation |
|---|---|---|---|---|
| ascent (mkfont) | `options.mkfont.ascent` (exists) | `--ascent N` | mkfont | 1..cell (0 means "choose" to the tool: refused) |
| header ascent (jamoset) | `options.jamoset.jamo_ascent` int/null | `--ascent N` | `dos raw`, `hanterm` | 1..the face's cell height: the font's effective size (`font["sizes"]` is the layout's pixel size from `detect.layout_px`; `font["dos"]` holds only candidates and faces), the BDF box for hanterm |
| frame baseline (fits) | `options.jamoset.fit_baseline` int/null | `--baseline N` | `experimental fit`, `mask fit`, `composite`, `vector fit` (the render command) | 1..size (the fit's cell is `size x size`) |
| ascent (bdfface) | `options.bdfface.latin_ascent`, `options.bdfface.hangul_ascent` int/null | `--ascent N`, `--hangul-ascent N` | `bdfface`, and the **first** argv of `bdfface + from-svf fit` | 1..box height |
| cell width | `options.mkfont.width` int/null | `--width W` | mkfont | 1..255 |
| Latin top | `options.mkfont.latin` bool | `--latin` | mkfont | - |
| fit cell | `options.mkfont.fit_cell` bool | `--fit-cell` | mkfont | not with `clip_cell`, checked on the **merged** flags (preset + panel: `dos-u-2bpp` carries `--clip-cell`): `"%s: fit_cell and clip_cell: choose one"` |
| AA refine | `options.jamoset.aa_refine` int/null | `--aa-refine N` | `experimental fit`, `mask fit` at bpp 2 (jamovec has none) | 0..9 |
| noise clean | `options.jamoset.clean` bool, default true | `--no-clean` when false | `experimental fit` (both bpps: jamoset cleans by default at 2 bpp and for adaptive at 1 bpp) | - |
| binarize | `options.jamoset.binarize` choice, default `threshold` | `--binarize X` | 1 bpp: `experimental fit`, `mask fit` (`threshold`/`ridge`/`mono`), `composite`, `vector fit` (`threshold`/`ridge` only) | `mono` only when `caps.mask_libs` and never on a jamovec route (`"%s: binarize mono needs freetype-py"`, `"%s: binarize mono is not a jamovec choice"`) |
| named ranges | batch/per-font `range` gains `ksx1001-nohanja`, `ksx1001-symbols`, `ksx1001`, `jamo`, `cp949` | `--unicode ascii,<name>` (mkfont); a list file for bdfface `--chars-from` (`RANGE_FILES` writes one per name, as for 2350/11172) | mkfont, bdfface | a jamo route ignores the range as today |
| per-glyph dy | per-font key `dy`: `{"<cp>": int}` (keys `"0x67"` or decimal strings; the page writes hex), null = none | an appended `svfdy.py` argv (7.5) | `precomposed` steps only | -cell_h..cell_h and -128..127 per the effective cell; no key at or above `0xF0000`; refused when the font has no precomposed kind selected |
| dy / ascent to try (preview only) | page state | - | - | "apply" copies into `dy` or `options.jamoset.jamo_ascent` (6.4) |

From-svf routes take no ascent: jamoset `--from-svf` ignores `--ascent` (section 4), and the jamo face inherits the
precomposed face's ascent (for `bdfface + from-svf fit`, bdfface's own). Not exposed (design call, out of the card's
list and low value in a page): `--punct-extra`, `--ink-advance`, `--only-listed`, `--fallback-ttf`, `--limit`,
`--require`, jamoset `--advance`/`--cell`/`--threshold`/`--mask-radius`/`--passes`, `--bpp 8`. Presets can still carry
them.

### 7.2 Settings schema and validation

`DEFAULT_OPTIONS` becomes:

```python
DEFAULT_OPTIONS = {
    "mkfont": {"cell": None, "ascent": None, "width": None, "mono_hint": False, "clip_cell": False,
               "fit_cell": False, "latin": False, "space_advance": None},
    "jamoset": {"embolden": False, "symbols": False, "jset_version": None, "jamo_ascent": None, "fit_baseline": None,
                "aa_refine": None, "clean": True, "binarize": "threshold"},
    "bdfface": {"latin_ascent": None, "hangul_ascent": None},
}
OPTION_CHOICES = {"binarize": ("threshold", "ridge", "mono")}
```

Every key is unique across the three groups, so `_own_option_keys`, `_option_errors` and `data-field` keep working
flat. `_options_type_errors` learns the third value type: a key in `OPTION_CHOICES` takes one of its strings (message
`"%s: option jamoset.binarize is not one of threshold, ridge, mono"`); a bool default of `True` (`clean`) is still a
bool. `_option_errors` gains the ranges of 7.1 (every ascent-like value is `1..`, never 0). `_ascent_cell_errors`
keeps its per-size rule (an ascent must fit **every** effective size when no cell is set) and is applied to each of
the four ascent keys against its own cell (mkfont: `cell` or each size; `jamo_ascent`: the DOS layout's cell height
or the hanterm BDF box; `fit_baseline`: each size; bdfface: `font["bdf"]["box"][1]`). The route-level rules
(`_route_errors`): `fit_cell` vs the merged `--clip-cell`; `mono` vs caps and vs jamovec routes; `jamo_route`
(below) naming a route the font does not offer. `BATCH_DEFAULTS["range"]` stays `"2350"`; `RANGE_FILES` becomes the
seven names with their `mkfont.NAMED_RANGES` key. `FONT_ONLY_KEYS` gains `"dy"` and `"jamo_route"`
(`_FONT_ONLY_DEFAULTS` both `None`); `dy`'s type rule: `"%s: dy is not an object of code point -> int"`, key parse
`int(k, 0)` or a single character (the `svfdy.json_dy` rule); `jamo_route` is a route label string or null
(`"%s: jamo_route %s is not offered"`).

Caps in entries (review I8): the server stamps `font["mask_ok"] = caps["mask_libs"]` into every outline entry of a
job **each time it loads the job** (`_load`, so a detect, a settings PUT, a run and a page GET all see the live value;
a server restarted with another `JAMOSET_PYLIB` cannot serve a stale flag), so `routes.routes(font)` (Python) and
`offeredRoutes(font)` (JS) decide `mask fit` from the entry alone and the drift harness needs no global;
`canonical_fonts()` carries both values; `run_ready` re-checks `jamo_route == "mask fit"` against the live caps.

`jamo_route` and `experimental`: `mask fit` and `vector fit` are non-native, so a `jamo_route` naming either (or
`experimental fit`) **requires** `experimental` on that font (`"%s: jamo_route %s needs experimental"`); it never
overrides the flag. With `experimental` and no `jamo_route`, `route_for` keeps today's rule (the first native route,
else the first non-native in page order).

### 7.3 `panel_argv` and `OPTION_VISIBLE`

`presets.panel_argv(options, kind, route_label, bpp)` grows by the rows of 7.1 and returns, for the two-command
route, a **per-command** fragment: its signature becomes `panel_argv(options, kind, route_label, bpp) -> list[list[str]]`
aligned with the route's commands (one list for one-command routes), and `routes._with_extra(commands, extras)`
applies `extras[i]` to `commands[i]` (the preset fragment goes with the last command as today). For `bdfface + from-svf
fit` the bdfface flags go to argv 0, `--jset-version` to argv 1. The page's `OPTION_VISIBLE` must then be exactly:

```
"mkfont":                 {"1": ["cell","ascent","width","mono_hint","clip_cell","fit_cell","latin","space_advance"],
                           "2": ["cell","ascent","width","clip_cell","fit_cell","latin","space_advance"]}
"johab844":               {"1": []}
"dos raw":                {"1": ["embolden","symbols","jset_version","jamo_ascent"]}
"hanterm":                {"1": ["embolden","symbols","jset_version","jamo_ascent"]}
"composite":              {"1": ["symbols","jset_version","fit_baseline","binarize"], "2": ["symbols","jset_version","fit_baseline"]}
"experimental fit":       {"1": ["jset_version","fit_baseline","binarize","clean"],
                           "2": ["symbols","jset_version","fit_baseline","aa_refine","clean"]}
"mask fit":               {"1": ["jset_version","fit_baseline","binarize"]}
"vector fit":             {"1": ["symbols","jset_version","fit_baseline","binarize"], "2": ["symbols","jset_version","fit_baseline"]}
"copy":                   {"1": ["jset_version"], "2": ["jset_version"]}
"from-svf fit":           {"1": ["jset_version"]}
"bdfface":                {"1": ["latin_ascent","hangul_ascent"]}
"bdfface + from-svf fit": {"1": ["jset_version","latin_ascent","hangul_ascent"]}
```

`mask fit` has no `clean` (it always passes `--no-clean`, section 9.1) and no 2 bpp. The page's `ADVANCED` list gains
one entry per new key with its group; `readOptions`/`readPerPanel`/`fillOptions` learn the `<select>` of a choice key
(value string) and that `clean` is a flag whose batch default is on. `visibleOptions` and `jobs._reference` use the
font's effective `jamo_route` when set (else the first usable jamo route, `route_for`'s rule, which gains the
`jamo_route` argument).

### 7.4 The experimental-fit command line at 1 bpp

`_fit_commands` keeps `--binarize threshold` as its default at 1 bpp and `apply_flags` replaces it when the panel says
otherwise. It now also passes **`--mask-font none`** explicitly, so an experimental fit is the free fit whatever the
worker's environment holds (section 9.1). `VALUED` gains `--baseline`, `--width`, `--aa-refine`, `--mask-font`,
`--mask-radius`, `--hangul-ascent`, `--pylib`, `--report` (the flags `apply_flags` may meet from a preset or the
panel; `--probe-cell` and `--json` never pass through it: the server builds the probe argv and `plan_steps` appends
the svfdy argv whole).

### 7.5 The dy step (precomposed faces only)

(design call) Not a step kind of its own, and not on jamo faces: a jamo face's syllables and compat jamo are composed
(no dy can be stored for them, and `svfdy.py` would silently skip them), and the dy of the few whole glyphs it holds
is not worth a second code path. `plan_steps` appends to every `precomposed` face step whose font has a non-empty
effective `dy` one more argv after the route's commands:

- route with commands: `PY + [tools/svfdy.py, <out>, <out>, "--json", work/sNN/dy.json]`;
- the `copy` route (commands `[]`, the worker would copy the source itself): `PY + [tools/svfdy.py, <src token>,
  <out>, "--json", work/sNN/dy.json]`, where `<src token>` is the upload path the worker rewrites to its plain copy for
  a `.gz` (`_plain_token`), so the copy is the tool's read and the worker's own copy is not needed (`_execute` sees a
  non-empty argv). The zip note shows the real command.

`dy.json` is written by `plan_steps` (`{"0xAC00": 1, ...}`, sorted), so the argv stays short (well under the 512-byte
note line cap whatever the table's size). The worker's "no output" and exit checks apply unchanged; `_read_back`
reads the face svfdy wrote; the tool's own refusals (a face without a metrics table, e.g. a copied upload; a dy past
the cell) fail the step with the tool's message, which the page shows. A font whose selected kinds hold no
`precomposed` is refused a dy at validation (`"%s: dy needs a precomposed face"`).

Alternative considered: a separate `dy` step kind reading the face step's output. Rejected: a second step per face
doubles the table rows and the zip's log blocks for a one-second tool, and the face's step id is what the page draws.

### 7.6 Keeping Python and `maker.js` in step

`test_page_js_tables_match_python` is extended, not duplicated: `every` sets every new key to a value that emits its
flag (`width: 18, fit_cell: True` with `clip_cell: False` in a second pass, `latin: True, aa_refine: 3, clean: False,
binarize: "ridge", jamo_ascent: 12, fit_baseline: 12, latin_ascent: 12, hangul_ascent: 13`), the `flags` map carries
the new flags (`--ascent` maps to `ascent` under a mkfont label, to `jamo_ascent` under `dos raw`/`hanterm`, to
`latin_ascent` under a bdfface label: the test resolves a flag by the label's tool, a small table in the test), and
`canonical_fonts()` gains outline entries with `gsub_jamo: True` and `mask_ok` both true and false, so `mask fit` is
iterated and filtered on both sides. The rule "the JS tables change in the same commit as the Python tables" is a
plan rule: every slice that touches `routes.py` or `presets.panel_argv` ships its `maker.js` rows (section 12).

## 8. Clipping before the build (C)

### 8.1 Choice: a probe bake with a per-glyph box report, read by the page for any ascent

Two ways were on the table (audit section 3): bake once unclipped into a tall cell and overlay the cell, or make mkfont
report per-glyph cut rows. (design call) Both, in one run, because each alone is not enough: counts without ink are
abstract; ink without numbers cannot drive a list. The run is a **probe**: a new `mkfont.py --probe` mode that
measures the boxes first, chooses the tall cell and the ascent itself (the server cannot know them before the run), writes
the report and bakes the face unclipped:

```
mkfont.py SRC work/preview/<fid>/probe/<size>-<bpp>.svf --size S --bpp B --unicode <the step's --unicode value>
          --width <effective cell_w> [--latin] [--mono-hint] --probe --probe-cell <effective cell_h>
          --report work/preview/<fid>/probe/<size>-<bpp>.json
```

The probe argv is derived from the **step's own merged argv**, not from the options: the server calls
`route.commands(font, size, bpp, ...)` with the same `apply_flags(presets.argv_for(preset, kind, size),
panel_argv(...))` that `plan_steps` uses (factored into `settings.face_argv(font, eff, size, bpp, paths)` so both
call one function), then keeps `--unicode`, `--latin`, `--mono-hint`, `--only-listed`, `--space-advance`,
`--punct-extra` and the resolved `--width` (the argv's `--width`, else its `--cell`, else the size, as mkfont resolves
it) and **replaces** `--cell`, `--ascent`, `--clip-cell` and `--fit-cell` by `--probe --probe-cell <the argv's cell_h,
else the size>` and the output/report paths. Presets rewrite exactly those flags (`dos-l-1bpp`/`dos-u-2bpp` replace
`--unicode` and `--cell`, `dos-u-2bpp` adds `--clip-cell --ascent {size-2}`, `latin-18cell-2bpp` sets `--cell 18
--width 18 --only-listed`), so a probe built from the options alone would measure another glyph set and cell than
the build. The ascent prefill is the merged argv's `--ascent` when it has one, else the report's `auto_ascent`.

`--probe` means: after `measure_boxes` over the range, `A0 = max(1, -min_top)` and `cell_h = A0 + max(0, max_bottom)`;
when `cell_h <= 255` bake with that cell, that ascent and the clip rule (no nudge; nothing is cut by construction) and
write the report with `"probe": true`; when `cell_h > 255` (a size whose ink span does not fit a byte) write the report
only (`"probe_face": false`) and exit 0. `--probe-cell H` is the user's effective cell height: the report then also
carries `auto_ascent` = `fit_ascent(boxes, H, choose_ascent(font, H, latin))[0]`, mkfont's own choice for that cell
(what `--clip-cell` without `--ascent` would use), the page's prefill. `--unicode` is exactly the step's value
(the merged argv's: the named range, the copied list file, or a preset's own list), `--width` is always explicit
(`cell_w = width or cell_h` would otherwise make the tall cell wide and change `fit_counts`' width judgement), and
the raster flags that change ink are the step's. The page then draws the probe face with `drawGlyphs` and strokes the user's cell `[baseline - ascent,
baseline - ascent + cell_h)` over it; the rows outside the rectangle are the rows that would be cut. The probe's
`.json` holds the numbers; the page computes `top_cut = max(0, -top - ascent)` and `bottom_cut = max(0, bottom +
ascent - cell_h)` per glyph for the ascent typed, which is `fit_counts`'s rule, so the list, the counts and the overlay
agree with what the real build (`--clip-cell --ascent`) will cut. `fit_cell`'s answer (the largest size that fits) is
not derivable from one probe; the page does not pretend: it shows mkfont's `--fit-cell` result after the run (the
report of the real step carries it).

### 8.2 The report format (`mkfont.py --report`)

```json
{"tool": "mkfont", "probe": false, "probe_face": true, "size": 16, "requested_size": 18, "cell": [16, 16],
 "ascent": 13, "auto_ascent": 13, "mode": "clip|nudge|fit", "latin": false, "bpp": 1,
 "boxes": {"0x41": [1, -11, 9, 0], "0xAC00": [0, -13, 16, 2]},
 "cut": {"0xAC00": {"top": 0, "bottom": 2, "full": 9, "fringe": 4}},
 "wide": ["0x5C"], "nudged": ["0x7B"], "counts": {"glyphs": 2445, "top": 368, "bottom": 2299, "wide": 1}}
```

`boxes` = `measure_boxes` (ink box relative to the pen, y down, baseline at 0, at the bake's bpp; a glyph without ink
or absent is omitted); `cut` only in clip mode (`clipped_ink`'s full/fringe per cut glyph, today summed on stdout);
`nudged` in default mode (the glyphs `render(... nudge=True)` moved); `size` after `--fit-cell`; `auto_ascent` present
when `--probe-cell` was given, else equal to `ascent`. Keys are `"0x%X"`. The report is written beside the face in
every mode, so the real build's step carries it too (`step["report"] = "work/sNN/report.json"` set by `plan_steps` for
mkfont steps, which adds `--report <that path>` to every mkfont argv; `jobs._clear_outputs` removes a stale
`report.json` with the output, so a failed rerun cannot show the last run's counts; the page reads it through
`GET /api/jobs/<id>/report/<step>.json` and shows the counts in the step row: "cut 2,300 (368 top, 2,299 bottom)"
instead of only the stdout tail). This build-side half (the `plan_steps` change, the Step key, the endpoint, the row
counts, and the mkfont argv and Step-shape test updates it entails) is slice C2's (section 12). `--ascent`'s `default=0` stays (0 = choose) and
the maker never sends 0. `tools/test_mkfont.py` gains the report and probe tests (section 11); `docs/tools.md` gets
the two flags (the builder adds a sentence to the mkfont section).

### 8.3 Cost and UI

Cost: one Pillow pass over the range plus the bake: 0.5 s for `ascii,ksx1001-hangul`, 2.4 s for `ascii,cp949` at 16 px
(review measurement of `--clip-cell`, the same work). The probe runs on demand when the clipping panel opens
(`GET .../probe/<font>/<size>/<bpp>.json` bakes under the font's preview lock, like the source PNG; `TIMEOUT_S` 60 as
for a bake), once per font, size and bpp, cached until a keyed setting changes (6.5). It uses the prepared source
(section 10). Only the mkfont route has a probe: for a jamo set the cell is the layout's and nothing is cut by
construction (jamoset composes inside the cell); for bdfface the BDF's box is the cell.

UI, a "clipping" disclosure under each outline font's override panel: the size select (the font's effective sizes),
the bpp (the font's first effective bpp, switchable), the ascent field (prefilled with `auto_ascent`), cell height
(the effective `cell` or size), a live count line "N glyphs cut: T at the top, B at the bottom; W wider than the
cell", the overlay canvas (`drawGlyphs` of the sample text plus the 12 worst-cut glyphs, cell rectangle stroked, cut
rows tinted), and the per-glyph list (code point, character, top rows, bottom rows; sorted by rows cut, capped at 200
rows with "and N more") that scrolls the overlay to a glyph on click. "Apply" writes the ascent into
`options.mkfont.ascent` and ticks `clip_cell` (the user keeps `fit_cell` as an alternative; the live count under
`fit_cell` is shown as "the run decides the size"). When the probe reports `probe_face: false` the panel shows the
list and counts without the overlay.

## 9. Jamo sets from decomposable fonts and the identity check (D)

### 9.1 Routes

Two new jamo routes for outline sources (`outline` and `outline-composite`; CFF fonts qualify for both):

- `Route("jamo", "mask fit", False, ["844", "adaptive"], [1], None, "outline", None, _mask_fit_commands)`:
  `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --mask-font SRC --no-clean --check -o OUT
  [--pylib DIR]`. **1 bpp only** (jamoset has no mask at 2 bpp) and **always `--no-clean`** (the donor masks of
  `clean` replace the mask font: section 4), so the route does what its name says or is not offered. Offered when the
  entry carries `gsub_jamo: true` (new detect fact: the font's `GSUB` FeatureList has `ljmo`, `vjmo` and `tjmo`, read
  with fontTools in `detect._sfnt_facts`; the label gets "; conjoining jamo (GSUB)") **and** `mask_ok` (7.2). On
  `outline-composite` it sits after `composite` (neodgm, the OFL fixture, is composite). The mask font is the source
  itself; a separate mask font is not offered. `--pylib` carries `JAMOSET_PYLIB` from the server's environment when set;
  `ENV` is **not** widened (`JAMOSET_MASK_FONT` must never reach a tool: it would change every free fit). The route is
  experimental like the fit; with several jamo routes offered the per-font `jamo_route` picks one (default: the first
  usable in page order: `composite`, `experimental fit`, `mask fit`, `vector fit`). Validation:
  `"%s: mask fit needs freetype-py and uharfbuzz (JAMOSET_PYLIB)"` when `jamo_route` names it without `mask_ok`.
- `Route("jamo", "vector fit", False, ["844", "adaptive"], [1, 2], None, "outline", _vector_prepare,
  _vector_commands)`: prepare `jamovec.py master SRC -o master.json [--adaptive]` (no `--components`), then
  `jamovec.py render master.json --size S --bpp B --binarize threshold --check -o OUT` (exactly `_composite_*` without
  the flag). Offered for `outline` and `outline-composite`; needs fontTools only. Cost: unknown here (the composite
  master took 25 s; the raster separation renders every drawn syllable at 48 px first: expect minutes; the plan's
  end-to-end test uses the synthetic 2-syllable fixture and a real-font run is env-gated, section 11). Ruling D7 keeps
  it, behind `experimental`, with a "minutes per font" note on the page.

`experimental fit` stays as it is but passes `--mask-font none` (7.4). `presets.ALL_SOURCES` does not change;
`ROUTES["outline"]` lists `mkfont`, `experimental fit`, `mask fit`, `vector fit` and `ROUTES["outline-composite"]`
lists `mkfont`, `composite`, `mask fit`, `vector fit`; `offeredRoutes` filters `mask fit` by `font.gsub_jamo &&
font.mask_ok`. `quality.measure` scores both against the `outline` reference as it does the fit.

### 9.2 Degrading without the optional libraries

`jamofit.libs_available(pylib)` is the one check, run at server start with `JAMOSET_PYLIB` from the environment and
exposed as `caps.mask_libs` and stamped as `mask_ok`. `binarize mono` and `mask fit` are hidden (not disabled)
without it; a saved setting that needs them is a validation error naming the fix. jamoset's own "fitting without the
mask font" fallback is never relied on: the maker refuses rather than silently fitting free, and the experimental fit
says `none` outright.

### 9.3 The identity check: what is scored

The structural check is `--check` (every route runs it): the table composes all 11,172 syllables and every piece the
table names has a glyph; it says nothing about a piece looking like its jamo. The identity check asks, per piece,
whether the syllables composed with it are read as their jamo by a recogniser. With `caps.recog`:

- Scope: every `jamo` step (whatever its route's `reference`) whose face `quality.face_facts(...)["jset"]` is a JSET
  with sets and classes (not a JMAP/LIST face, whose pieces are not per-jamo in the same way; a LIST face gets
  "identity check: not applicable (LIST)"). 1 bpp faces are scored as they are; a 2 bpp face is thresholded at level 2
  (`quality.compare`'s "IoU at level 2" convention) before scoring, and the report says so.
- Input: `quality.composed_syllables(face)` (every syllable's cell, the engine's own composition); the pieces of each
  syllable from `jamoset.pieces_of` (the same numbers `svfw_pieces` returns).
- Model: `maker/recog_score.py`, a **CLI run as a subprocess** (`recog_score.py FACE.SVF -o identity.json
  [--threads 2]`) through `jobs.run_command` with `ENV` plus `SVF_RECOG_DIR`, a 180 s timeout and the job's cancel
  (a Python thread cannot be killed, and torch must not be loaded into the server). It wraps exactly the calls
  `jamomerge.Scorer` makes (`sys.path.insert(0, SVF_RECOG_DIR)`, `import recog`, `recog.load("11-12")`,
  `recog.split`, `recog._heads(net, bool[n, h, w])`), batched 256 cells a call, with an injectable array builder
  (numpy in production, nested lists in the stub test). The numpy/torch path is **unverified** here and stays so until
  a real run (section 11).
- Per syllable: `ok_head[s] = (argmax_L == L, argmax_V == V, argmax_T == T)` and the three log-probabilities.
- Per piece p (initial/medial/final slot k, jamo j, set n): `users` = the syllables whose slot k is p; `read` = the
  share of users whose head k is correct; `nll` = the mean of `-log p_k` over users; `worst` = the five users with the
  largest `-log p_k`, each with the jamo the head read (`{"cp": 44032, "got": "ㄲ"}`). Flag: `pass` when `read >=
  0.95`, `warn` when `0.80 <= read < 0.95`, `fail` below; a piece with no users is listed as `unused` and never
  flagged. Thresholds are ruling D4's placeholders; they are constants in `recog_score.py`, reported in the JSON.
- Face level: `recog_ks` = share of the 2,350 KS syllables read on all three heads, `recog_all` over 11,172,
  `pieces: {pass, warn, fail, unused}` counts, `identity: "pass" | "warn" | "fail"` = the worst piece flag.

Without `caps.recog`: `identity = {"available": false, "structural": "<the check: line of the step's stdout>"}` and
the UI shows "identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; numpy and torch
needed)". The run is never blocked by it.

### 9.4 Where it runs and what it writes

In the worker, in `_read_back`, after `quality.measure` for `jamo` steps and only when `caps.recog`: `_run_step`
passes its `cancel` event into `_read_back` (today only `_execute` gets it), and the subprocess, run through
`run_command(argv, cwd, 180, cancel)`, writes `work/sNN/identity.json` (`{"available": true, "model": "11-12", "thresholds": {...}, "bpp_note": ...,
"face": {...}, "pieces": [{"piece": 161, "slot": "m", "jamo": "ㅏ", "set": 0, "users": 588, "read": 0.991,
"nll": 0.03, "flag": "pass", "worst": [...]}, ...]}`), served by `GET /api/jobs/<id>/identity/<step>.json`;
`step["identity"]` gets the face-level summary (small: it is in the job JSON the page polls). A non-zero exit, a
timeout or an unreadable JSON is `{"available": false, "error": "<stderr tail>"}` and the step stays `done`. The zip's
build log gets one line per jamo step (`identity: pass, 344 pieces, 2 warn, 0 fail, ks 0.97`, or `identity check
unavailable`, or the error); nothing of it goes into the face.

### 9.5 The UI

A "pieces" panel under a jamo step's preview: the summary line with the flag coloured (pass green, warn amber, fail
red, unavailable grey), then the per-piece table (slot, jamo, set, users, read %, flag; sorted fail first, then warn,
then by read ascending), each row drawing the piece with `drawPiece` at 2x and, on expansion, its five worst syllables
composed by `svfw_glyph` with what the head read, beside the same syllables drawn from the job's precomposed face at
that size when one is done (the reference the eye compares against; else the column is left empty). A failing
piece's row carries "fix: fit again with a mask (mask fit, 1 bpp), more sets (adaptive), or a LIST exception for its
worst syllables (jamoexc.py, not in the maker)". The panel also shows the structural line.

## 10. Source previews for prepared fonts (E)

`server._make_source_preview` draws `preview.source_png` from the uploaded path with `face_index`; it must draw the
prepared font. (design call) The server prepares in-process, not through the `source` step: `srcprep.prepared_bytes(
data, ops)` applied to the entry's `prep` plus the planned `instance` op (the same list `plan_steps` builds, factored
into `settings.source_ops(font, eff)` so both use one function), written to `work/preview/<font id>/source.<ext>` under
the font's preview lock, and that path given to `source_png` with `face_index` 0. `prepared_bytes` learns the
`instance` op (`fontTools.varLib.instancer.instantiateVariableFont(TTFont, coords, inplace=False)`, the in-process
twin of the CLI the step runs; the `PrepError` it raises today becomes the implementation). The decision "does this
font need preparing" lives in `settings.source_ops` and a server helper `_prepared_source(job, font)`, **not** as a
`source_kind` test inside `_make_source_preview`: the drift test reads that function's source and counts every
`source_kind == "..."` / `source_kind in (...)` literal as a baked kind, so a new literal there would make `outline`
count as baked and fail the `PREVIEW_KINDS` check (review N7). The `pcf-bdf` op produces a
BDF Pillow reads at its strike; a KSC/johab BDF still has no Unicode charmap and stays "none" (`PREVIEW_KINDS`
unchanged). The probe (section 8) and the on-demand source bake use the same prepared path. The prepared file is
dropped with the font's previews (the glob covers `<font id>/`; `instance` is already a key). Cost: the instancer on a
large VF takes seconds; it runs once per settings change under the lock, as the PNG does.

## 11. Tests (F)

Fixtures are synthetic (built in the test with fontTools / `fixtures.py` / `inputfx.py`) or OFL (`ttf/`, `svf/`). No
new dependency; tests needing emcc, node, chromium, the optional libraries or a recogniser skip with a message that
names what is missing (`unittest.SkipTest`), as `test_web_picker.py` does. Gates that must stay green: the maker suite
(539 tests today; slice A3 rewrites 7 assertions in place, so the count after it is 539 minus any test it merges plus
the new ones, stated per slice in the plan), `make -C c check`, `tools/test_web_picker.py` (TestModule: the oracle),
`web/test/check.mjs` where playwright-core exists (not here; its cases are the picker's and this design does not touch
`web/picker.js` or `web/index.html`; the shared `emcc-flags.sh` must keep `web/build.sh`'s output identical: the test
compares the two scripts' `svf.wasm` bytes), the MCU size gates (unchanged by construction: `c/src` is not touched;
`git diff --stat 01a943f -- c/src c/include` empty is asserted in every review gate).

| Slice | Test (file) | Fixture | Proves |
|---|---|---|---|
| A exports | `tools/test_web_picker.py TestModule.test_glyph_metrics_pieces_cmap` | `svf/dos/NEODG16.SVF` (precomposed), `NEODG16A.SVF` (jamo), `MARUS20.SVF` (stored dy), a 2 bpp face from `ttf/` baked in the test | `svfw_glyph` == `jamoset.parse_svfn(...).glyphs[cp]` bytes and == `jamoset.compose` for a syllable; `svfw_metrics` == the parsed `f.metrics[cp]` 3-tuple (advance, bearing, ink_w) plus `f.dy.get(cp, 0)`, and the JSET advance for a syllable; `svfw_pieces` == `jamoset.pieces_of` (numbers); `svfw_cmap_cp` lists the parsed code points in file order and -1 for -1 / count / 65536; `svfw_line_box` == `svfline.measure` |
| A compositor | `TestModule.test_glyph_compositor_equals_line` (render.mjs gains a `glyphs` spec: the per-code-point draws of 6.4) | `MARUS20.SVF` over `NEODG16.SVF` (two slots, stored dy), text with Latin, a syllable, a glyph only slot 1 has; scales 1/1, 2/1, 3/2. Marks: a face baked in the test by mkfont from `ttf/ebgaramond` with U+0300..0304 (`MARKS_AT_ORIGIN`) over NEODG16, text `Aéò̂ gy ¡` (the review's probe fixture; no `svf/` face draws a mark) | no overrides: byte-equal to `svfw_draw`; `ascentOverride = A + 2`: equal to `svfw_draw` of a copy with header byte 16 patched; `dy {0x67: 1, 0x41: -1}`: equal to `svfw_draw` of the face after `svfdy.apply`; both at once; dy on a base (`e`), on a mark (U+0301) and on both; a DOS raw face with `--symbols` under an ascent override: U+2026 stays on the baseline |
| A endpoints | `maker/test/test_server.py` `FaceBytesTest` | a job with one done mkfont step (the existing `run_batch` helper) | `/face/<step>.svf` bytes == the step's output; ETag/304; 404 for `source`/`prepare` steps, another job's step, a path escape; a foreign `Host` is 403 on the new GETs; `/api/repo/face/dos/NEODG16.SVF` served, `../` and lowercase names refused; `/api/caps` keys are booleans and follow a monkeypatched environment |
| A page | `test_server.py test_page_js_tables_match_python` (extended) and `test_page_wires_the_preview` (`node --check` on `svfview.js`, the import string present, no `preview.png` reference left in `maker.js`) | - | the mirror tables, the module path |
| A browser | `maker/test/smoke_dom.py` (not in the unittest discovery; run by the plan's review gate; skipped without a browser): starts the server on port 0, uploads `ttf/neodgm/neodgm.ttf` + its OFL, runs, then polls `google-chrome` or `chromium-browser` `--headless=new --disable-gpu --dump-dom http://127.0.0.1:PORT/?job=ID` (up to 10 times, 2 s apart, `--virtual-time-budget` alone does not wait for the wasm fetch) until the DOM holds `<canvas data-step="s01" data-drawn="1">` with `data-ink > 0` and no `data-error` | OFL neodgm | the module loads and draws in a real browser |
| B schema | `test_settings.py` `ControlsTest` | synthetic entries | each new key's type and range message (exact strings), ascent 0 refused on every ascent key, `fit_cell` + merged `--clip-cell` refused (panel and the `dos-u-2bpp` preset), `binarize mono` refused without `mask_ok` and on jamovec routes, `dy` shape, the piece refusal, the cell-height bound, "needs a precomposed face", `jamo_route` not offered, the seven range names and `write_range_files` writing seven files whose contents equal `mkfont.NAMED_RANGES` |
| B argv | `test_routes.py` `PanelArgvTest` (extended) | - | every (label, bpp) emits exactly the flags of 7.3 per command (bdfface flags on argv 0 of the two-command route); `apply_flags` replaces `--binarize threshold`; `VALUED` holds the new flags; the experimental fit carries `--mask-font none` |
| B dy step | `test_plan_inputs.py` `DyStepTest` | `inputfx.ttf` + dy `{"0x41": 1}`; an uploaded v3 SVF (copy route) | the mkfont step's argv list ends with the svfdy argv naming `dy.json`; the copy step's single argv reads the upload and writes `out`; end to end both faces parse with `dy == {0x41: 1}` and `facecheck` passes; a jamo-only selection with dy is a validation error |
| B fit/width/latin | `test_plan_inputs.py` end to end on `inputfx.ttf` | synthetic | `--fit-cell` run exits 0 and the report's `mode` is `fit`; `--width 20` gives cell_w 20; `--latin` changes the ascent of a Latin-only bake (two bakes differ) |
| C report | `tools/test_mkfont.py test_report_json`, `test_probe_mode` | a synthetic TTF with one glyph whose ink spans -12..+3 at 16 px (fontTools pen box) | `boxes` carries it; with `--cell 12 --ascent 10 --clip-cell` `cut` says top 2 bottom 1 and `counts` match `fit_counts`; nudge mode lists it under `nudged`; `--fit-cell` reports the lowered `size`; `--probe --probe-cell 12` bakes a 15-row cell at ascent 12 with no cut rows and reports `auto_ascent` == `fit_ascent(...)`; a glyph set whose span passes 255 gives `probe_face: false` and no face |
| C probe | `test_server.py` `ProbeTest` | the same synthetic TTF | `GET .../probe/f01/16/1.json` bakes once (a second GET does not re-run: the mtime is unchanged), its argv carries `--width`, the step's `--unicode` value and `--probe-cell`; the `.svf` draws through the module with no row cut; a settings PUT changing `width` (and each key of 6.5 in turn) removes both; a PUT changing `ascent` does not |
| C page math | `maker/test/test_clip_math.mjs` run by `node --test` from a unittest wrapper | the report JSON above | the page's `cutRows(box, ascent, cell_h)` equals `fit_counts`'s rule for a table of ascents (the Python side computed in the test and embedded) |
| D detect | `test_detect_inputs.py test_gsub_jamo_fact` | `inputfx.ttf` + a GSUB table with `ljmo`/`vjmo`/`tjmo` features built with `fontTools.otlLib.builder` | `gsub_jamo` true, the label suffix; a font with only `ljmo` is false; `mask_ok` stamped from caps |
| D routes | `test_routes.py` `DecomposableRoutesTest` | - | `mask fit` offered only with `gsub_jamo` and `mask_ok`, 1 bpp only, argv has `--mask-font SRC --no-clean` and `--pylib` only when the environment names one; `vector fit` always; `route_for` with `jamo_route` |
| D vector e2e | `test_plan_inputs.py test_vector_fit_end_to_end` | `fixtures._composite_ttf`'s outlines flattened to plain glyphs (2 syllables, no components) | `jamovec master` without `--components` then render, job done, `facecheck`, `quality` not None; `test_real_inputs.test_real_vector` (`SVF_MAKER_REAL_VECTOR`) records the time of a real font |
| D mask e2e | `test_real_inputs.py test_mask_fit` | `ttf/neodgm/neodgm.ttf` (OFL, composite, has the three features) | skipped unless `jamofit.libs_available()`; `jamo_route: "mask fit"`; the executed argv holds `--mask-font` and `--no-clean`, stderr lacks "fitting without the mask font", the face differs from the experimental fit of the same font and size |
| D identity | `maker/test/test_recog_score.py` | a fake `recog.py` written into a temp dir by the test (`load` returns a stub; `split` the arithmetic; `_heads` returns one-hot log-probabilities that read every syllable correctly except those using piece 161), `SVF_RECOG_DIR` pointed at it, the nested-list array builder; `svf/dos/NEODG16A.SVF` | run as the CLI: piece 161 `fail`, every other piece `pass`, `recog_ks` matches, the JSON shape; a raising stub exits non-zero with the message; `test_numpy_path` is skipped unless numpy imports (the real contract is **unverified** until then) |
| D worker | `test_jobs.py test_identity_written_for_jamo_steps` | the stub above + a DOS raw fixture job, `caps.recog` monkeypatched true | `step["identity"]` summary, `work/sNN/identity.json`, the log line; a stub that sleeps past a 1 s test timeout gives `available false` with "timed out" and the step `done`; with `caps.recog` false nothing runs and the summary says unavailable |
| E prepared preview | `test_server.py test_source_preview_draws_the_prepared_font` | `inputfx.variable_ttf()` with instance `{"wght": 700}`; `inputfx.mac_cmap_ttf()` | the PNG differs from the default-instance PNG (the gvar delta moves `ga`); the Mac font gets a PNG at all (today none); the prepared file is under `work/preview/<fid>/` and removed on an instance change |
| F regression | the full suite through `heavy`; `make -C c check`; `tools/test_web_picker.py`; `cmp` of `web/build.sh` and `maker/build-wasm.sh` wasm outputs; `git diff --stat 01a943f -- c/src c/include` empty | - | nothing else moved |

## 12. Task decomposition hint (G)

Slices, each a commit series with its own tests. The drift test `test_page_js_tables_match_python` runs at every
commit, so a slice that changes `routes.py`, `presets.panel_argv` or the settings keys ships the matching `maker.js`
rows and the test's `every`/`flags` updates in the same commit (never a Python-only or JS-only table change).

1. **A1 glue exports + oracle tests** (`svf_web.c`, `render.mjs`, `test_web_picker.py`, `emcc-flags.sh`,
   `maker/build-wasm.sh`). No maker change. Risk: none to `c/src`; the review gate asserts the empty diff.
2. **B1 schema + panel_argv + per-command extras + the `jamo_route`/`dy` keys** (settings, presets, routes
   `VALUED`/`_with_extra`, `--mask-font none` on the fit, maker.js `ADVANCED`/panel inputs and the `OPTION_VISIBLE`
   rows **of the labels that exist today only** (`experimental fit`, `composite`, `bdfface`, ... with
   `fit_baseline`, `clean`, `binarize`, the bdfface keys), the drift test's `every`/`flags`). The `mask fit` and
   `vector fit` rows are **not** in B1: the drift test demands every route label and no other, so those rows land with
   their routes (slice 8). B1 also moves every exact-argv assertion of the fit in `test_routes.py`/`test_plan_inputs.py`
   (`--mask-font none`). Independent of A1. Risk: the biggest table change; one commit per tool group is fine as long
   as each is two-sided.
3. **A2 face endpoints + caps + GET host check + invalidation keys + `mask_ok` stamping on load** (`server.py`,
   `test_server.py`). Depends on B1 for the key names in the invalidation list.
4. **A3 `svfview.js` + the result preview in the page**, removing `preview.png` from the worker and rewriting the 7
   assertions named in 6.5 (`maker.js`, `svfview.js`, `jobs.py`, `settings._step`, `test_jobs.py`, `test_zipout.py`,
   `test_server.py`, `smoke_dom.py`). Depends on A1, A2. Risk: the page is the least tested layer; the node compositor
   test is the proof, and the compositor must be written from `walk_next`'s rules (6.4), not from `svfline.py`.
5. **B2 dy step + named ranges** (`plan_steps`, `RANGE_FILES`, tests). Depends on B1 and runs **after** 4 (both edit
   `settings.py`: 4 changes `_step`, 5 changes `plan_steps`).
6. **C1 `mkfont.py --report` and `--probe`** (tools + `tools/test_mkfont.py` + `docs/tools.md`). Independent.
7. **C2 the build's `--report` + probe endpoint + clipping panel**: `plan_steps` adds `--report` to every mkfont argv
   and `step["report"]`, `_clear_outputs` drops a stale `report.json`, `settings.face_argv` is factored out, the
   `report/<step>.json` endpoint, the step-row counts, the probe endpoint, the page panel, and the mkfont argv and
   Step-shape test updates these entail (server, settings, jobs, page). Depends on C1, A3, B1, and runs after 5.
8. **D1 `gsub_jamo` detect fact + `mask fit`/`vector fit` routes + `--pylib` + their `ROUTES`/`OPTION_VISIBLE` rows,
   `offeredRoutes` filter and canonical fonts** in one commit (detect, routes, jobs `_reference`, settings
   `run_ready`, maker.js, drift test fixtures). Depends on B1 and 3. Risk: `vector fit` run time on a real font is
   unknown; the e2e test uses the 2-syllable fixture; the real-font run is env-gated and recorded in the commit body.
9. **D2 `recog_score.py` CLI + worker subprocess (with `cancel` plumbed into `_read_back`) + identity endpoint +
   panel**. Depends on A3 (the piece drawing). Risk: the real recogniser's input contract is inferred from
   `jamomerge.Scorer` only; the stub test pins the CLI and the arithmetic, and the first run against real weights is
   a manual step the plan records (what `SVF_RECOG_DIR` was, the model's cell size).
10. **E prepared source preview** (`srcprep.prepared_bytes` instance op, `settings.source_ops`,
    `server._prepared_source`; no new `source_kind` literal inside `_make_source_preview`, or the drift test's
    extraction changes in the same commit). Depends on nothing but edits `server.py`: run after 3.
11. **F closing**: the full gates, the audit's section 3 and gap list rewritten to the new state, `maker/README.md`
    (still missing from T15) gets the build step for the module.

Order: 1 and 6 in parallel with 2; then 3; then 4; then 5; then 7, 8, 10 in sequence (all touch `server.py`,
`settings.py` or `routes.py`); then 9; then 11. No two slices that edit `server.py`, `settings.py` or `routes.py` run
at the same time, and the drift test is green after every commit by construction (every table change is two-sided
and lands with its route).

## 13. Left to the builder

- The exact look of the panels (CSS), the canvas sizes, debounce timing of live redraws, the grid's row length.
- `svfview.js`'s internal memory management (one arena per chain vs per face).
- The `boxes` key format in the report could carry glyph advances too if the page needs them; the page uses
  `svfw_metrics` of the probe face instead.
- How the ETag is computed (size+mtime is enough; a hash is not required).
- Whether `maker/build-wasm.sh` is called by `make -C c` or stays manual (it stays out of the gates either way: the
  gates build their own module in a temp dir).
- The wording of every notice; the exact column order of tables.

## 14. Decisions needed (the owner)

Each with my recommendation; the design above assumes the recommendation. D1-D7 were ruled on in section 15; D8 is
new (review C1).

- **D1. Source preview of outline/bitmap sources: keep Pillow PNG, or bake a quick 1-size SVF and draw it with WASM
  too?** Recommendation: keep the PNG for the "source" column, and let the probe face (section 8) be the WASM-drawn
  "what the converter makes" view.
- **D2. `mask fit` precedence** (section 9.1): recommended last in page order with the per-font `jamo_route` override
  (revised from "before the experimental fit": a composite font's native route stays first).
- **D3. `--report` and `--probe` as flags of `tools/mkfont.py`** (section 8): recommended yes; the alternative
  re-implements `measure_boxes` in the maker, which would drift.
- **D4. Identity thresholds** pass >= 0.95, warn >= 0.80 (section 9.3): placeholders, reported in the JSON.
- **D5. Dropping the PNG result preview entirely** (section 6.5): recommended drop, per decision 5.1.
- **D6. Which named ranges to list** (section 7.1: the five more): recommended all five, `ascii` always on.
- **D7. The vector-fit route always on for outline fonts** although its run time is unmeasured: recommended on,
  behind `experimental`, with a "minutes per font" note; measure on the first real run and decide whether to drop it.
- **D8. A header-ascent patch after the build for outline faces?** The pen-offset preview cannot be "applied" on mkfont
  and fit routes (6.4): their `--ascent`/`--baseline` is a frame, not a shift. If the owner wants to move a built
  outline face against its companion (the picker use), that needs a small tool step rewriting header byte 16 (an
  `svfdy.py --ascent N` option, which already rewrites the header range and re-verifies) and an "ascent to try" on
  those previews too. Recommendation: not in this card; the clipping overlay answers the question the recipes ask
  ("what does this cell cut"), and dy covers single glyphs.

## 15. Rulings on section 14 (2026-11-03, controller)

D1 keep the Pillow PNG for the source column and use the WASM-drawn probe face for the converter view. D2 yes, with the per-font
`jamo_route` override. D3 yes, `mkfont.py --report FILE.json`. D4 accept the placeholder thresholds (pass >= 0.95, warn >= 0.80),
reported in the JSON, to be revisited after the first real run. D5 drop the PNG result preview. D6 yes, all five extra named ranges,
ASCII always on. D7 yes, behind `experimental` with a "minutes per font" note. Recorded as rulings, not user decisions: each is
reversible by editing this section and the plan.

## 16. Review dispositions (2026-11-03)

Two reviews of the first version (Opus lane, `review-lanes/maker-ctl-design/opus-report.md`: C1, I1-I12, M1-M12;
AGY lane, `review-lanes/maker-ctl-design-agy/out.md`: 1-16). Each finding was checked against the code; duplicates
are merged. "Changed" names the section that now holds the fix.

| Finding | Verified | Disposition |
|---|---|---|
| Opus C1: the ascent override previews a header patch, which only `dos raw`/`hanterm` build | yes (`build_from_source` vs `render(... ascent)`, the review's rebake rows) | Changed: 6.4 splits header ascent (pen shift, apply writes `jamo_ascent`) from frame ascent (clipping overlay only, apply writes the flag + `clip_cell`); D8 added |
| Opus I1 / AGY 2: pen formula unscaled, dy additive, applied to every slot, marks | yes (`SCALE_LEN`, `svfdy.apply` sets, `face_for`, `draw_mark`) | Changed: 6.4 uses `S()` per term, absolute dy, slot 0 only; test uses MARUS20 over NEODG16 at 1/1, 2/1, 3/2 (the "base+marks units" rule this round added was wrong and is replaced by per-code-point calls in round 1, N1) |
| Opus I2 / AGY 6.1: dy on composed code points silently dropped; jamo faces | yes (`svfdy` counts `missing`, exits 0; AGY's "exit 2" is wrong) | Changed: 7.5 restricts dy to `precomposed` steps; jamo-only selection refused |
| Opus I3 / AGY 6.2: the copy route's empty argv plus svfdy | yes (`_execute` copies only when `argv` is empty) | Changed: 7.5 the svfdy argv reads the source token and writes `out` |
| AGY 6.3: 512-byte note line cap | the cap exists; the `--range` argv AGY quotes is not in this design (`--json dy.json` is) | Not applicable; 7.5 notes the argv stays short |
| Opus I4a / AGY 4: `--from-svf` ignores `--ascent`; `--ascent 0` is "choose" | yes (`fit_font(..., face.ascent)`, `ascent or ...`, `if args.ascent:`) | Changed: from-svf routes take no ascent (7.1); every ascent key is `1..` (7.2); the probe never sends 0 |
| Opus I4b-c / AGY 5: bdfface flags land on the jamoset argv; `--ascent` shared | yes (`_with_extra` -> last argv) | Changed: 7.3 per-command fragments; unique keys `latin_ascent`/`hangul_ascent`/`jamo_ascent`/`fit_baseline` |
| Opus I11 / AGY 8: option keys must stay disjoint | yes (`_own_option_keys`, `data-field`) | Changed: 7.2 unique keys; the `group.key` scheme of the first version is dropped |
| Opus I5a / AGY 3.1-3.2: no mask at 2 bpp; `clean` discards the mask | yes (`main_aa` before `--mask-font`; `piece_masks` overrides) | Changed: 9.1 `mask fit` is 1 bpp only, always `--no-clean`, no `clean` option |
| Opus I5b: neodgm is `outline-composite`, the route never offered to it | yes | Changed: 9.1 offers `mask fit`/`vector fit` on `outline-composite` too |
| AGY 3.3: the e2e assertion checked the wrong stream | yes (stderr) | Changed: 11 D mask e2e asserts the argv, stderr and a differing face |
| Opus I6: ENV passthrough changes the free fit | yes (`mask_auto` + `DEFAULT_MASK_FONT`) | Changed: 7.4 `--mask-font none`; 9.1 `--pylib` only, `ENV` not widened |
| Opus I7: jamovec has no `mono` | yes (`choices=("threshold","ridge")`) | Changed: 7.1/7.2 per-route choices and a validation message |
| Opus I8 / AGY 8.3 / AGY 16: caps vs the drift harness and `route_for`; slices split tables | yes (the harness runs `offeredRoutes` under node with the font only) | Changed: 7.2 `mask_ok` stamped into entries; 7.6 canonical entries for both values; 12 two-sided table rule and new order |
| Opus I9a-e / AGY 7: probe needs `--width`, bpp, the boxes before the run, auto ascent, ascent 0, the step's range | yes (`cell_w = width or cell_h`, `pack_svfn` bytes, `if args.ascent:`) | Changed: 8.1 `--probe` mode chooses the cell and `A0` itself, `--probe-cell` gives `auto_ascent`, `--width` explicit, bpp in the key and URL, `--unicode` = the step's value, `probe_face: false` past 255 rows |
| Opus I9f / AGY 14 / Opus M8: invalidation keys incomplete and 7.2 self-contradictory | yes (`_changed_preview_fonts` keys; `_jset_flags`) | Changed: 6.5 explicit key list, `_bake_flags`; 7.2 paragraph removed |
| Opus I10 / AGY 13.3: the scorer in the worker thread, torch in the server, `ENV` strips `SVF_RECOG_DIR`, the stub is not the numpy path | yes (`Scorer.arr` builds numpy; threads cannot be killed) | Changed: 9.3-9.4 subprocess CLI with timeout and cancel, `find_spec` caps, injectable array builder, numpy path marked unverified and its test skipped |
| AGY 13.1: identity skipped on `reference=None` routes | the first version already scored every jamo step; made explicit | Changed: 9.3 "whatever its route's reference" |
| AGY 13.2: "confused pairs" vs `worst` | AGY quotes text not in this design | Not applicable; `worst` now carries what the head read |
| Opus I12: tests broken by the preview drop not listed | yes (`test_jobs` 268/309/333/371/566, `test_zipout` 78, `test_server` 576-579) | Changed: 6.5 names them; slice 4 owns the rewrites |
| AGY 1: `svfw_metrics` returns `SVF_E_RANGE` on composed syllables | **no**: `svf_metrics_of` returns 1 with the JSET advance for a composed code point (`svf_face.c:365-372`) | Not applicable; 4 and 6.3 state the fact |
| AGY 9: `svf_jamo_pieces` returns plane-15 code points | **no**: it returns piece numbers (`svf_jamo.c:1117` adds `SVF_PIECE_BASE`) | Not applicable; 6.3 says the page adds the base once |
| AGY 10: `svfw_cmap_cp` index wraps through `uint16_t` | yes for a naive cast | Changed: 6.3 checks the index before the cast |
| AGY 11: `VALUED` misses the new flags | yes | Changed: 7.4 lists them (`--advance` is not exposed) |
| AGY 12: `ascent <= max(sizes)` contradicts `_ascent_cell_errors` | AGY quotes text not in this design; the per-size rule was and is the design's | Changed only in wording: 7.2 says "every size" explicitly |
| AGY 15: `vector fit` lacks `symbols`; `jamo_route` ignored by `visibleOptions` and `_reference` | yes (`jamovec render --symbols`) | Changed: 7.3 table and the `jamo_route` sentence |
| Opus M1: table inconsistencies (aa_refine row, composite baseline, clean by bpp, "four routes") | yes | Changed: 7.1/7.3 (composite gets `fit_baseline`; `clean` on both bpps of the fit; "three" routes) |
| Opus M2: unused pieces sentence | yes | Changed: 9.3 |
| Opus M3: `NAMED_RANGES` list incomplete | yes | Changed: 4 says "among them" |
| Opus M4: preset `--clip-cell` + `fit_cell` | yes (`dos-u-2bpp`) | Changed: 7.1 validates the merged flags |
| Opus M5: GET host check, `recog_dir` leak, repo-face regex | yes (`_STATE_CHANGERS`) | Changed: 6.2 |
| Opus M6: `.json` static type unneeded | yes | Changed: 6.1 drops it |
| Opus M7: dy vs cell height and the metrics table | yes (`dy_range`, `svfdy.read`) | Changed: 7.1 cell bound; 7.5 the tool's message stands for the metrics case |
| Opus M9 / AGY 16: parallel slices overlap files | yes | Changed: 12 order |
| Opus M10: `--virtual-time-budget` and the snap browser | plausible, not run | Changed: 11 A browser polls `--dump-dom`, HTTP only, `google-chrome`/`chromium-browser` named |
| Opus M11: packaging needs NEODG16 | yes | Changed: 6.1 |
| Opus M12: a jamo face's grid has no syllables | yes (`svf_cmap_cp` lists the table) | Changed: 6.4 syllables view |
| AGY "security already enforced by `_local_only`/`_safe_id`" | those names do not exist (`_check_same_origin`, the route regexes do) | Not applicable beyond M5 |

Round 1 (Opus re-review of `69f6ffc`, `opus-report-r1.md`; AGY approved): the review built the proposed exports as a
scratch glue (composed metrics, piece numbers, cmap index all as section 6.3 says), reran the pen formula (20/20),
tested marks (per-code-point 6/6 and 9/9; the "units" rule 0/6 on dy) and matched the page's cut rule against
mkfont's `--clip-cell` at 1 and 2 bpp (exact; 583 vs 105 cut glyphs between the bpps, so bpp belongs in the key).

| Finding | Verified | Disposition |
|---|---|---|
| N1: base+marks units break dy; U+0301 on MARUS20/NEODG16 draws nothing | yes (`walk_next` places a mark at the pen) | Changed: 6.4 one `svfw_draw` per code point; 11 A compositor uses a mark face baked from `ttf/ebgaramond`, dy on base/mark/both |
| N2: "never offsets a composed code point" could drop the ascent term | yes (probe 2 includes a composed syllable) | Changed: 6.4 "no dy term, the ascent term applies" |
| N3: `--symbols` glyphs are framed by the ascent on DOS raw/hanterm | yes (`symbol_glyphs(w, h, ascent, adv)`) | Changed: 6.4 those two code points get no ascent term when `symbols` is set; test case added |
| N4: the probe must take the step's merged preset+panel argv | yes (presets rewrite `--unicode`, `--cell`, `--width`, add `--clip-cell --ascent`) | Changed: 8.1 probe argv from `settings.face_argv` with `--cell/--ascent/--clip-cell/--fit-cell` replaced; prefill from the argv's `--ascent` |
| N5: B1 shipping the final `OPTION_VISIBLE` fails the drift test; the fit's argv assertions move | yes (the test demands every label and no other) | Changed: 12 B1 ships today's labels only, D1 lands `mask fit`/`vector fit` rows with the routes; B1 owns the `--mask-font none` assertions |
| N6: slices 4 and 5 both edit `settings.py` | yes | Changed: 12 runs 5 after 4 |
| N7: a `source_kind` literal in `_make_source_preview` breaks the drift test's bake extraction | yes (the test regexes that function's source) | Changed: 10 keeps the decision in `settings.source_ops`/`_prepared_source`; slice 10 notes it |
| N8: the build's `--report` had no slice; stale `report.json` | yes | Changed: 8.2 `_clear_outputs`; 12 C2 owns the build side and its test updates |
| M-r1: `font["dos"]` holds no cell height | yes (`{"candidates", "faces"}`; `detect.layout_px`) | Changed: 7.1 uses the effective size |
| M-r2: `--probe-cell`/`--json` in `VALUED` | yes | Changed: 7.4 drops them with the reason |
| M-r3: `mask_ok` stale across a restart | yes | Changed: 7.2 re-stamped on every job load, `run_ready` re-checks |
| M-r4: `_read_back` has no `cancel` | yes (`_run_step` passes it to `_execute` only) | Changed: 9.4 plumbs it; slice 9 |
| M-r5: `jamo_route` vs `experimental` | yes (`route_for` returns non-native routes only with `experimental`) | Changed: 7.2 a non-native `jamo_route` requires `experimental` (message) |
| M-r6: `f.metrics[cp]` is a 3-tuple, dy in `f.dy` | yes (`svfdy._write`) | Changed: 11 A exports wording |
| M-r7: Electron must load the page from the sidecar origin | yes (`_check_same_origin` accepts http(s) on the bound host) | Changed: 6.1 |
| Piece number 0 is a real piece | yes (NEODG16A) | Changed: 6.4 "trust the count" |

Group 1 review (Opus and AGY lanes, rulings of the controller): the `clean` control is offered only where it has an
effect. jamoset cleans by default at 2 bpp, and at 1 bpp only for `--layout adaptive`, so at 1 bpp `--no-clean` is not
a safe control (unticking does nothing at 844, and no `--clean` is ever emitted to turn it on). `OPTION_VISIBLE`
lists `clean` for `experimental fit` at 2 bpp only and `panel_argv` emits `--no-clean` at 2 bpp only (this overrides the
7.1 row "both bpps" and the 7.3 table). The report marks a glyph the cell cuts away entirely `"gone": true` (the build
drops it, `unicode_keep`) and counts it in `counts.gone`. `dy` keys are read as `tools/svfdy.json_dy` reads them (a
one-character key is that character) and must be code points; the cell rules of `jamo_ascent`, `fit_baseline`,
`latin_ascent` and `hangul_ascent` apply only to a font whose selected route reads the key.
