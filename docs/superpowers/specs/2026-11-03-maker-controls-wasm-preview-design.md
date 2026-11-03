# Maker controls and the WASM preview: design

Card t_9acea7ab: "maker: controls and preview for AA 2 bpp, baseline shift and top/bottom clipping, jamo-set from
decomposable fonts with piece identity check". Written 2026-11-03 on branch `maker-controls` of the OFL-only repository
(`svf-fonts-open`, base `01a943f`) for a builder who has not seen the repository. Every fact below was read from the
tree at that commit or run on this host today; what was not run says "not verified". Choices the owner has not made
are marked "(design call)" where I decided for the builder and collected again under "Decisions needed" at the end.

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
  round trip (sample text, scale, target, threshold, colours, baseline guides, per-glyph dy and an ascent to try).
- Per-glyph inspection: a glyph grid, the pieces of a syllable, the metrics of a glyph, all from the module.
- The controls of recipes.md reachable from the page, validated before a run, carried into the job's argv and build log
  exactly as a command line would: ascent on every route that takes one, `--width`, `--latin`, `--fit-cell`, a dy table
  applied by `tools/svfdy.py`, `--aa-refine`, `--no-clean`, `--binarize`, the named ranges of `mkfont.py`.
- Top/bottom clipping visible before the build: which glyphs a cell at an ascent cuts, by how many rows, with the ink
  drawn and the cell outlined, for any ascent the user types.
- A jamo set from a decomposable font: the GSUB-mask route (`jamoset.py --from-ttf --mask-font`) when the optional
  libraries are present, and `jamovec.py master` without `--components` (vector separation) always.
- A piece identity check: with the optional recogniser, a per-piece score and a pass/warn/fail flag; without it, the
  structural check the routes already run (`--check`: all 11,172 syllables compose) and the words "identity check
  unavailable".
- Source previews that show the prepared font (the chosen variable instance, a Mac font after `macsfnt.py unicode`, a
  TTC face after `ttc-face`), not the uploaded file's default face.
- All of it provable with synthetic or OFL fixtures; the existing gates stay green.

## 3. Non-goals

- Changing a pixel the renderer draws: `c/src` is not touched (section 6.3 shows every override is a pen offset in the
  glue or page). The byte-for-byte oracle `tools/test_web_picker.py TestModule` (WASM vs `tools/svfline.py`) stays the
  proof; `svfline.py` is not a preview path any more.
- Shipping a recogniser, its weights or training data in this repository, or training anything.
- Editing glyphs, 8 bpp faces, Mac `fbit`, HWP `.PFT`, local path mode (card t_cbd14d61), Electron (t_f04f1355),
  packaging (t_e64a56a7). Nothing here may assume a tailnet or systemd; every endpoint binds as today (127.0.0.1).
- Live re-fitting: a jamo fit takes 12-92 s (recipes.md, verified there); a fit result is a job step, never a preview.
- Kerning, shaping, combining marks beyond what `svf_draw_utf8` does (the page draws what the renderer draws).

## 4. Constraints and facts (checked 2026-11-03 on this host unless marked)

Renderer and module:

- `c/ports/web/svf_web.c` exports `svfw_open`, `svfw_target`, `svfw_target2`, `svfw_scale`, `svfw_measure`,
  `svfw_draw`, `svfw_reset`, `svfw_info`, `svfw_has`, `svfw_order` (4 slots; JS owns the face bytes and the pixel
  buffer; the glue mallocs scratch, `c/src` never allocates). `web/build.sh OUT` builds `svf.js` (ES6 module,
  `MODULARIZE`, `EXPORT_NAME=SvfModule`, `ENVIRONMENT=web,node`, `ALLOW_MEMORY_GROWTH`, runtime methods `HEAPU8`,
  `HEAP16`, `HEAP32`) and `svf.wasm`; the audit built it in 2 s (39,234 + 6,623 bytes). emcc is at
  `~/opt/emsdk/upstream/emscripten/emcc` (not on PATH; `build.sh` finds it through `EMSDK`). `web/dist/` is gitignored.
- `c/include/svf.h` has, not exported yet: `svf_metrics_of(f, cp, svf_metrics*)` (advance, bearing_x, ink_w, dy;
  returns 1/0/-1), `svf_cmap_cp(f, i)`, `svf_cell_bytes(f)`, `svf_glyph(f, cp, cell, len)` (composes a syllable of a
  jamo face), `svf_jamo_pieces(f, cp, out[3])`, `svf_compose`, `svf_is_jamo`. The draw path places a cell's top row at
  `y_baseline - S(ascent) + S(dy)` and the pen advances by the metrics advance (`c/src/svf_draw.c:196-205, 1277`);
  `svf_measure_utf8` derives a line's ascent/descent from each face's ascent and the glyph's dy (`:219-220`). The face
  header's ascent is byte 16 (`c/src/svf_face.c:97`); the open validates no relation between ascent and cell height.
- The size gates of the MCU profiles (`c/ports/profiles.txt`, the tables of `c/bench/MEASUREMENTS.md`, the CH582
  `image_sizes.py` gate) measure `c/src` builds; the web port is in none of them. `make -C c check` is the library
  gate (`c/check.sh`: no allocator symbol, ASan run, all 1024 `SVF_TARGETS` masks compile).

Maker:

- Previews today: `preview.source_png` (Pillow) for FreeType-readable sources at the first size; DOS raw and SVF sources
  are baked into `work/preview/<font id>.svf` by `preview.bake_source_face` and drawn by `svfline`; result faces are
  drawn by `svfline` in the worker (`jobs.Worker._read_back` -> `preview.result_png`), served by
  `GET /api/jobs/<id>/preview/<font>/<step>.png`. Settings changes drop a font's previews
  (`server._changed_preview_fonts` + `_remove_preview`, keyed on the effective preview inputs, `instance` included).
- Static files are served from `maker/static/` with `STATIC_TYPES` = html, js, css, png (`server.py:46`); every state
  change checks `Host` and `Origin` (127.0.0.1 / localhost / ::1 / the bound host).
- Settings (`maker/settings.py`): batch keys `dest kinds layout sizes bpp range preset options`; per-font keys add
  `selected experimental dos_layout latin_companion licence names licence_name note_name instance`;
  `DEFAULT_OPTIONS = {"mkfont": {cell, ascent, mono_hint, clip_cell, space_advance}, "jamoset": {embolden, symbols,
  jset_version}}`; a value is an int-or-null or a bool, nothing else (`_options_type_errors`); `_option_errors` ranges;
  `_ascent_cell_errors` cross-checks ascent against cell/size. `presets.panel_argv(options, kind, route_label, bpp)`
  turns options into flags; `routes.apply_flags` merges a preset's fragment and the panel; `routes.VALUED` lists the
  flags that take a value. `maker/static/maker.js` mirrors `ROUTES`, `PRESETS`, `OPTION_VISIBLE`, `PREVIEW_KINDS`,
  `SOURCE_WORDS` as strict JSON, and `maker/test/test_server.py test_page_js_tables_match_python` reads them back:
  `OPTION_VISIBLE[label][bpp]` must equal the option keys whose flags `panel_argv` emits for that label and bpp (its
  `flags` map names each flag's key), `PREVIEW_KINDS` must classify every `presets.ALL_SOURCES` kind and its `bake`
  set must equal the kinds `server._make_source_preview` bakes (read out of the source).
- The worker's subprocess env is `ENV = {PATH, HOME, LANG}` (`jobs.py:66`, `preview.py:48`): `JAMOSET_PYLIB` and
  `JAMOSET_MASK_FONT` do not reach a tool.
- Tests: `maker/test` has 539 `test_` functions (the audit counted 431 passing before branch maker-inputs; the suite
  is run through `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`). Fixtures are built
  in the tests (`maker/test/fixtures.py`, `inputfx.py`, `inputkinds.py`) or taken from `svf/` and `ttf/` (OFL).

Tools (the options this design exposes; `python3 tools/X.py --help` is authoritative):

- `mkfont.py`: `--cell H` (default = size), `--width W` (default = cell), `--bpp 1|2|8`, `--ascent N`, `--clip-cell`,
  `--fit-cell` (lowers the size until no ink is cut; when both are given `--clip-cell`'s counting is skipped:
  `mkfont.py:877`), `--latin`, `--mono-hint`, `--space-advance`, `--punct-extra`, `--ink-advance`, `--only-listed`,
  `--fallback-ttf`, `--limit`, `--require`, `--unicode` with the names `ascii`, `ksx1001-hangul`, `ksx1001-nohanja`,
  `ksx1001-symbols`, `ksx1001`, `hangul`/`cp949-hangul`, `cp949`, `jamo`, `file:PATH` (`NAMED_RANGES`). Clipping is
  reported on stdout only: `fit_counts` (code points over the top / bottom / too wide), `clipped_ink` (full and fringe
  pixels cut), the first 40 cut characters; `measure_boxes` gives each glyph's ink box relative to the pen
  (`(left, top, right, bottom)`, y down from the baseline) and is what every count is derived from.
- `jamoset.py`: `--ascent N` (DOS raw, hanterm, `--from-svf`, `--base`; `jamoset.py:3107`), `--baseline N` for
  `--from-ttf` (the fit's frame, `:3055`), `--bpp 2`, `--aa-refine N` (default 2), `--clean/--no-clean` (default on for
  2 bpp and adaptive), `--binarize mono|threshold|ridge` (1 bpp `--from-ttf`; `mono` needs freetype-py), `--threshold`,
  `--mask-font FONT|none`, `--mask-radius`, `--pylib DIR`, `--report FILE.json`, `--advance`, `--cell WxH` (from-ttf).
  The mask path needs `freetype` and `uharfbuzz` importable (`jamofit.load_libs`, `JAMOSET_PYLIB`); without them
  jamoset prints "no freetype/uharfbuzz, fitting without the mask font" and goes on (`:3038-3041`). Neither module is
  installed here, nor numpy or torch.
- `jamovec.py master FONT -o M.json [--adaptive] [--decision-px 48] [--components] [--pylib]` and `render M.json
  --size N --bpp 1|2 --binarize threshold|ridge [--cell] [--baseline] [--check]`. `master` without `--components` is the
  raster separation at the decision size through `jamoaa.OutlineFace`, which loads fontTools only (`jamoaa.py:197-198`;
  `pylib` is passed on but not needed for that path). Timing of that mode: not verified (recipes.md verified
  `--components` only: 25 s for neodgm).
- `bdfface.py`: `--ascent N`, `--hangul-ascent N`, `--hangul-advance`, `--cell WxH`, `--chars-from FILES`.
- `svfdy.py IN OUT --json dy.json` (`{"0x67": 1, "106": 1, "y": 1}`), refuses a dy on a jamo piece and a dy outside
  -128..127, keeps everything else of the face, re-verifies (`verify`). Reading IN fully before writing OUT, so
  `IN == OUT` is safe (`_run` reads `data` first); the builder keeps a separate output anyway (section 7.5).
- `jamomerge.py --recog` is the only recogniser hook: `Scorer.__init__` inserts `$SVF_RECOG_DIR` (or `.`) into
  `sys.path`, imports `recog`, calls `recog.load("11-12")`, `recog.split(syllable_indices)` -> (L, V, T) and
  `recog._heads(net, bool_array[n, h, w])` -> three log-probability arrays; a syllable is "read" when each head's
  argmax is its jamo (`jamomerge.py:918-960`). Whether those weights take any cell size is not verifiable here (no
  weights on this host); `tools/` has no other "recog" code.

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
  drift. `maker/static/wasm/` is gitignored like `web/dist/`.
- `STATIC_TYPES` gains `".wasm": "application/wasm"` (streaming compile needs that MIME type) and `".json":
  "application/json"`. Static files are served with `Cache-Control: no-cache` plus an `ETag` of size+mtime (section 6.5).
- The page imports it as the picker does: `const M = await (await import("/static/wasm/svf.js")).default();` from a
  new module `maker/static/svfview.js` (the drawing layer, section 6.4). A 404 on `svf.js` is a page notice "preview
  module not built: run maker/build-wasm.sh" and every preview cell shows that text; no PNG fallback is kept (decision
  5.1), and the worker stops writing `preview.png` (section 6.5 removes `preview.result_png` from the run path).
- Packaging (t_e64a56a7) ships the two files as data; nothing here depends on the repo checkout at run time beyond
  `maker/static/`.

### 6.2 Endpoints that serve bytes

All GET, read-only, under the job, path-checked with `_inside` like the PNGs, served `application/octet-stream` with
`Cache-Control: no-cache`, `ETag: "<size>-<mtime_ns>"` and `If-None-Match` -> 304.

| Endpoint | Serves | 404 when |
|---|---|---|
| `GET /api/jobs/<id>/face/<step>.svf` | the step's `output` file of a `done` face step (kind `precomposed`/`jamo`) | the step is not that job's, not done, kind `source`/`prepare`, or the file is gone |
| `GET /api/jobs/<id>/source/<font>.svf` | `work/preview/<font id>.svf`: the baked source face of a `dos-raw` / `svf-*` entry (today's `bake_source_face`, under the same per-font preview lock; baked on demand as the PNG is today) | the kind has no baked face (then the page uses the source PNG, section 10) |
| `GET /api/jobs/<id>/probe/<font>/<size>.svf` and `.json` | the clipping probe of section 8 | the font's route is not mkfont, or the probe failed |
| `GET /api/jobs/<id>/identity/<step>.json` | the identity report of section 9.4 | the step has none |
| `GET /api/repo/face/<group>/<FILE>.SVF` | a face of `svf/` (only `dos/NEODG16.SVF` is needed: the Latin companion `preview.LATIN_FALLBACK`), path checked against `svf/` | not a file under `svf/` |
| `GET /api/caps` | `{"wasm": bool, "mask_libs": bool, "recog": bool, "recog_dir": str|null}`: the module files exist; `jamofit.libs_available(os.environ.get("JAMOSET_PYLIB"))`; `SVF_RECOG_DIR` names a dir with `recog.py` and numpy+torch import (checked once at server start, cached) | never |

The source preview PNG endpoint stays for FreeType-readable sources (section 10). `_changed_preview_fonts` and
`_remove_preview` already cover `work/preview/<font id>*`; the probe cache lives under `work/preview/<font id>/probe/`
so the same glob clears it.

### 6.3 Exports to add to `c/ports/web/svf_web.c`

Only the glue changes; every new export is a thin call into the existing public API of `svf.h`. Signatures (all
`EMSCRIPTEN_KEEPALIVE int`, returning an `svf_err` unless said otherwise; a slot not open is `SVF_E_ARG`):

```
svfw_metrics(int slot, uint32_t cp, int32_t out[4])   out = advance, bearing_x, ink_w, dy; returns svf_metrics_of's
                                                      1 / 0 / -1 (-1 also for a slot not open; out untouched)
svfw_cell_bytes(int slot)                             svf_cell_bytes, 0 for a slot not open
svfw_glyph(int slot, uint32_t cp, uint8_t *cell, uint32_t len)
                                                      svf_glyph into JS memory: the stored rows (MSB first, rows padded
                                                      to a byte); a syllable of a jamo face composed. len must be
                                                      >= svfw_cell_bytes (SVF_E_NOMEM otherwise, as the core says)
svfw_pieces(int slot, uint32_t cp, uint16_t out[3])   svf_jamo_pieces: returns the count 0..3 (0 = not composed)
svfw_cmap_cp(int slot, int i)                         svf_cmap_cp as int32: the code point, or -1 past the count
svfw_line_box(const char *text, int len, int x, int baseline, int32_t out[4])
                                                      the scaled line's box for the current chain and scale:
                                                      out = left (x), top (baseline - extent.ascent), width, bottom
                                                      (baseline + extent.descent), from svf_measure_utf8; returns
                                                      svf_measure_utf8's error. A convenience over svfw_measure so the
                                                      page draws guides with the numbers the draw uses
```

Rules: no new state in the glue (the four slots, one target, one scale as today); `svfw_glyph` reads into a JS-owned
buffer, so the composed cell of a streamed face is not a concern (the web glue opens mapped faces only). No ascent or
dy setter is added: there is no hook in `c/src` for one, and adding one would touch the AVR/M0+ readers. The two
overrides are done by the page (6.4); `svfw_metrics` and `svfw_line_box` are what they need.

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
  `svfw_draw`. With `guides`, the page strokes the cell top (baseline - ascent of slot 0), the baseline and the cell
  bottom over the pixels (CSS layer, never in the module's buffer).
- `drawGlyphs(canvas, codePoints, {ascentOverride, dy, pitch, ...})` -> the per-glyph compositor: for each code point
  it draws **one glyph per `svfw_draw` call** (the UTF-8 of that code point) at a pen the page computes:
  `x += advance` from `svfw_metrics` (marks advance 0, `svf_is_mark_default`'s U+0300..036F range mirrored in JS);
  `y = baseline + (ascent - ascentOverride) + dy[cp]`. Because the core places a cell at `y_baseline - ascent + dy`,
  drawing at `baseline + (ascent - A') + d` puts the cell's top at `baseline - A' + d_stored + d`: exactly where a face
  with header ascent `A'` and a glyph dy of `d_stored + d` would put it. The pixels are the renderer's; only the pen
  moved. This is the baseline-shift and dy preview, and the glyph grid (a fixed `pitch` instead of the advance).
- `glyphCell(slot, cp)` -> `svfw_glyph` unpacked to a `Uint8Array` of levels (for the piece view and the identity
  panel); `pieces(slot, cp)` -> `svfw_pieces`; `codePoints(slot)` -> every `svfw_cmap_cp`.
- `lineBox(text, x, baseline)` -> `svfw_line_box`.

Memory: face bytes are `_malloc`ed once per fetch and freed after `svfw_reset` when the chain changes (the picker's
rule, `c/ports/web/README.md`: bytes must stay while a slot uses them); the pixel buffer is reallocated when the
canvas grows. A face over 16 MiB is refused by the page (the server never writes one; `MAX_GLYPHS` bounds it).

Equivalence the tests pin (section 11): with no overrides, `drawGlyphs` of a text equals `drawLine` of the same text
byte for byte (same pen arithmetic as `walk_next`), and `drawLine` equals `svfline.py line` (the existing oracle).
`svf_measure_utf8` is not used by `drawGlyphs` for a line with overrides: the page computes the box from `svfw_info`
ascent/cell_h, the override and the dy table (the same formula as `svf_measure_utf8`, `svf_draw.c:219-220`), so a
descender lowered by dy enlarges the canvas as the spec says the line's descent grows.

What a result cell shows (the steps table's `result` column becomes a `<svf-preview>` block): the sample line
(`detect.SAMPLE_TEXT`, editable, kept per page), the scale (1/1 .. 4/1), target GRAY8 | MONO (threshold) | RGB565,
guides on/off, and a "glyphs" toggle that opens the grid (every code point of the face, 16 per row, pitch = cell_w + 2;
a click selects a glyph: metrics, the dy field, the pieces of a syllable drawn side by side from `svfw_glyph` of
`SVF_PIECE_BASE + piece`). The face facts (`step.facts`) stay as text beside it.

### 6.5 Caching and invalidation

- Face bytes are immutable for a step id once the step is `done`; the page keeps them in memory per `(job, step)` and
  refetches when `job.steps[i].state` or `seconds` changes after a re-run (`?job=` reload refetches everything). The
  server's `ETag`/304 makes a reload cheap.
- The baked source face and the probe are invalidated by the settings PUT path that exists (`_changed_preview_fonts`
  keys gain the new keys that change a bake: section 7.2 lists which).
- Worker: `_read_back` stops calling `preview.result_png`; `step["preview"]` is dropped from the Step dict
  (`settings._step`) and from `zipout`'s log heading if it names it (it does not today: checked, only the server
  reads `step["preview"]`). `preview.result_png`, `svf_png` and `chain_for` stay in `preview.py` as the oracle helpers
  the tests use (`test_preview.py` keeps its 19 tests). `PREVIEW_KINDS` in `maker.js` stays the source-preview table.

## 7. Controls (B)

### 7.1 Which flag, which route

| Control (recipes.md) | Setting | Flag | Routes (label) | Validation |
|---|---|---|---|---|
| ascent (mkfont) | `options.mkfont.ascent` (exists) | `--ascent N` | mkfont | 0..cell (exists) |
| ascent (jamoset) | `options.jamoset.ascent` int/null | `--ascent N` on `dos raw`, `hanterm`, `from-svf fit`, `bdfface + from-svf fit`; `--baseline N` on `experimental fit`, `mask fit`, `vector fit` (render) | those | 0..cell_h of the face (DOS: the layout's cell; from-ttf: size or `cell`) |
| ascent (bdfface) | `options.bdfface.ascent`, `options.bdfface.hangul_ascent` int/null | `--ascent N`, `--hangul-ascent N` | bdfface, bdfface + from-svf fit (first argv) | 0..box height |
| cell width | `options.mkfont.width` int/null | `--width W` | mkfont | 1..255 |
| Latin top | `options.mkfont.latin` bool | `--latin` | mkfont | - |
| fit cell | `options.mkfont.fit_cell` bool | `--fit-cell` | mkfont | not with `clip_cell` ("%s: fit_cell and clip_cell: choose one"; mkfont would silently skip the clip counts) |
| AA refine | `options.jamoset.aa_refine` int/null | `--aa-refine N` | experimental fit, mask fit, vector fit (render has none: omitted), bpp 2 only | 0..9 |
| noise clean | `options.jamoset.clean` bool (default true) | `--no-clean` when false | experimental fit, mask fit, bpp 2 or layout adaptive | - |
| binarize | `options.jamoset.binarize` choice `threshold`/`ridge`/`mono`, default `threshold` | `--binarize X` | experimental fit, mask fit, vector fit (render), composite (render) at 1 bpp | `mono` only when `caps.mask_libs` ("%s: binarize mono needs freetype-py") |
| named ranges | batch/per-font `range` gains `ksx1001-nohanja`, `ksx1001-symbols`, `ksx1001`, `jamo`, `cp949` | `--unicode ascii,<name>` (mkfont); a list file for bdfface/`--chars-from` (`RANGE_FILES` writes one per name, as it does for 2350/11172) | mkfont, bdfface | a jamo route ignores the range as today |
| per-glyph dy | per-font key `dy`: `{"<cp>": int}` (keys `"0x67"` or decimal strings; the page writes hex), null = none | an appended `svfdy.py` argv (7.5) | every face step | -128..127; not on `U+F0000..` (pieces); a cp the face lacks is reported by svfdy on stdout and not an error |
| ascent override (preview only) | page state, not a setting | - | - | the "apply" button copies it into `options.<tool>.ascent` of that font |

Not exposed (design call, out of the card's list and low value in a page): `--punct-extra`, `--ink-advance`,
`--only-listed`, `--fallback-ttf`, `--limit`, `--require`, jamoset `--advance`/`--cell`, `--bpp 8`, `--threshold`,
`--mask-radius` (left at jamoset's auto value), `--passes`. Presets can still carry them.

### 7.2 Settings schema and validation

`DEFAULT_OPTIONS` becomes:

```python
DEFAULT_OPTIONS = {
    "mkfont": {"cell": None, "ascent": None, "width": None, "mono_hint": False, "clip_cell": False,
               "fit_cell": False, "latin": False, "space_advance": None},
    "jamoset": {"embolden": False, "symbols": False, "jset_version": None, "ascent": None, "aa_refine": None,
                "clean": True, "binarize": "threshold"},
    "bdfface": {"ascent": None, "hangul_ascent": None},
}
OPTION_CHOICES = {("jamoset", "binarize"): ("threshold", "ridge", "mono")}
```

`_options_type_errors` learns the third value type: a key in `OPTION_CHOICES` takes one of its strings (message
`"%s: option jamoset.binarize is not one of threshold, ridge, mono"`); a bool default whose value is `True` by default
(`clean`) is still a bool. `_option_errors` gains the ranges of the table above; `_ascent_cell_errors` is applied to
`jamoset.ascent` against the route's cell (the DOS layout's cell height from `detect`'s `dos` facts, else the size)
and to `bdfface.*` against `font["bdf"]["box"][1]`. `BATCH_DEFAULTS["range"]` stays `"2350"`; `RANGE_FILES` becomes the
seven names with their `mkfont.NAMED_RANGES` key. `FONT_ONLY_KEYS` gains `"dy"` (`_FONT_ONLY_DEFAULTS["dy"] = None`);
its type rule: `"%s: dy is not an object of code point -> int"`, key parse `int(k, 0)` or a single character (the
`svfdy.json_dy` rule), values ints in -128..127, no key at or above `0xF0000`.

`_changed_preview_fonts` keys gain `dy` (the source bake does not use it, but the probe does not either: only the
result preview, which the page applies live; so in fact nothing new invalidates a bake). The probe (section 8) is keyed
on `sizes`, `range`, `options.mkfont.{cell,width,latin,mono_hint}` and `instance`/`prep`; `ascent`, `clip_cell` and
`fit_cell` are applied by the page to the probe data, not baked in.

### 7.3 `panel_argv` and `OPTION_VISIBLE`

`presets.panel_argv` grows by the rows of 7.1; it is the one place that knows which label takes which flag. The page's
`OPTION_VISIBLE` must then be exactly:

```
"mkfont":                 {"1": ["cell","ascent","width","mono_hint","clip_cell","fit_cell","latin","space_advance"],
                           "2": ["cell","ascent","width","clip_cell","fit_cell","latin","space_advance"]}
"johab844":               {"1": []}
"dos raw":                {"1": ["embolden","symbols","jset_version","ascent"]}
"hanterm":                {"1": ["embolden","symbols","jset_version","ascent"]}
"composite":              {"1": ["symbols","jset_version","binarize"], "2": ["symbols","jset_version"]}
"experimental fit":       {"1": ["jset_version","ascent","binarize"], "2": ["symbols","jset_version","ascent","aa_refine","clean"]}
"mask fit":               {"1": ["jset_version","ascent","binarize"], "2": ["symbols","jset_version","ascent","aa_refine","clean"]}
"vector fit":             {"1": ["jset_version","ascent","binarize"], "2": ["jset_version","ascent"]}
"copy":                   {"1": ["jset_version"], "2": ["jset_version"]}
"from-svf fit":           {"1": ["jset_version","ascent"]}
"bdfface":                {"1": ["ascent","hangul_ascent"]}
"bdfface + from-svf fit": {"1": ["jset_version","ascent","hangul_ascent"]}
```

where `ascent` under a jamoset label is `options.jamoset.ascent` and under bdfface `options.bdfface.ascent`: the page's
`ADVANCED` list gains entries `{key: "ascent", group: "jamoset", label: "ascent (jamo)"}`, `{key: "ascent", group:
"bdfface", ...}`, `{key: "hangul_ascent", group: "bdfface", ...}`, and the drift test's `flags` map becomes
`{flag: (group, key)}` with `--baseline` -> `("jamoset", "ascent")` and `--no-clean` -> `("jamoset", "clean")`, so
`OPTION_VISIBLE[label][bpp]` entries become `"group.key"` strings where a bare key is ambiguous. (design call) To keep
the JSON readable, `OPTION_VISIBLE` values are `"key"` for mkfont-only keys and `"group.key"` for the rest; the test
normalises both sides the same way. `readOptions`/`readPerPanel`/`fillOptions` learn the `<select>` of a choice key
(value string) and that `clean` is a flag whose batch default is on (the per-font select shows "(batch: on)").

The `mask fit` and `vector fit` labels appear in `ROUTES["outline"]` only; their `offeredRoutes` rules are in 9.1.

### 7.4 The experimental-fit command line at 1 bpp

`_fit_commands` today hard-codes `--binarize threshold` for 1 bpp; it keeps that default and `apply_flags` replaces it
when the panel says otherwise (`--binarize` is in `VALUED`). `--ascent` is added to `VALUED` already; `--baseline`,
`--width`, `--aa-refine`, `--mask-font`, `--mask-radius`, `--hangul-ascent` join it.

### 7.5 The dy step

(design call) Not a step kind of its own: `plan_steps` appends to every face step whose font has a non-empty effective
`dy` one more argv, after the route's commands: `PY + [tools/svfdy.py, <out>, <out>, "--json", work/sNN/dy.json]`, with
`dy.json` written by `plan_steps` (`{"0xAC00": 1, ...}`, sorted). The step's log then shows the exact command; the
worker's "no output" and exit checks apply unchanged; `_read_back` reads the face svfdy wrote. A `jamo` face whose dy
names a piece is refused at validation, never at the tool. `svfdy.py` keeps its own verification (`verify`), which
proves only dy and the header range changed.

Alternative considered: a separate `dy` step kind reading the face step's output. Rejected: a second step per face
doubles the table rows and the zip's log blocks for a one-second tool, and the face's step id is what the page draws.

### 7.6 Keeping Python and `maker.js` in step

`test_page_js_tables_match_python` is extended, not duplicated: `every` carries a value for every new key (`width: 18,
fit_cell: True, latin: True, aa_refine: 3, clean: False, binarize: "ridge"`, the two bdfface ints, `jamoset.ascent`),
the `flags` map carries the new flags, and `canonical_fonts()` gains a `gsub_jamo: True` outline entry so `mask fit`
and `vector fit` are iterated. The `caps` gating (`mono`, the mask route) is a page rule, not a table: the test
asserts the strings `caps.mask_libs` appear in `offeredRoutes` and in the binarize option builder (the same style as
`test_page_offers_the_instance_select_and_source_rows`).

## 8. Clipping before the build (C)

### 8.1 Choice: a probe bake with a per-glyph box report, read by the page for any ascent

Two ways were on the table (audit section 3): bake once unclipped into a tall cell and overlay the cell, or make mkfont
report per-glyph cut rows. (design call) Both, in one run, because each alone is not enough: counts without ink are
abstract; ink without numbers cannot drive a list. The run is a **probe**: `mkfont.py` with a new `--report FILE.json`
flag that writes, in every mode, the data the page needs, plus the face it bakes anyway. The probe is baked **unclipped
and tall** so the page can show what any ascent would cut without another run:

```
mkfont.py SRC work/preview/<fid>/probe/<size>.svf --size S --bpp B --unicode ascii,<range> [--width W] [--latin]
          [--mono-hint] --cell <span> --ascent <A0> --clip-cell --report work/preview/<fid>/probe/<size>.json
```

with `span = max_bottom - min_top` over the measured boxes and `A0 = -min_top` (so no glyph is cut and every glyph
stands on the one baseline: with `--clip-cell` mkfont does not nudge, and at that cell nothing is clipped). The page
then draws the probe face with `drawGlyphs` and strokes the user's cell `[baseline - ascent, baseline - ascent +
cell_h)` over it; the rows outside the rectangle are the rows that would be cut. The probe's `.json` holds the
numbers; the page computes `top_cut = max(0, -top - ascent)` and `bottom_cut = max(0, bottom + ascent - cell_h)` per
glyph for the ascent typed, which is `fit_counts`'s rule, so the list, the counts and the overlay agree with what the
real build (with `--clip-cell --ascent`) will cut. `fit_cell`'s answer (the largest size that fits) is also derivable
from the report only if several sizes are probed; the page does not pretend: it shows mkfont's `--fit-cell` result
after the run (the report of the real step carries it).

### 8.2 The report format (`mkfont.py --report`)

```json
{"tool": "mkfont", "size": 16, "requested_size": 18, "cell": [16, 16], "ascent": 13, "mode": "clip|nudge|fit",
 "latin": false, "bpp": 1,
 "boxes": {"0x41": [1, -11, 9, 0], "0xAC00": [0, -13, 16, 2]},
 "cut": {"0xAC00": {"top": 0, "bottom": 2, "full": 9, "fringe": 4}},
 "wide": ["0x5C"], "nudged": ["0x7B"], "counts": {"glyphs": 2445, "top": 368, "bottom": 2299, "wide": 1}}
```

`boxes` = `measure_boxes` (ink box relative to the pen, y down, baseline at 0; a glyph without ink or absent is
omitted); `cut` only in clip mode (`clipped_ink`'s full/fringe per cut glyph, today summed on stdout); `nudged` in
default mode (the glyphs `render(... nudge=True)` moved); `size` after `--fit-cell`. Keys are `"0x%X"`. The report is
written beside the face in every mode, so the real build's step also carries it (`step["report"] = "work/sNN/report.json"`
set by `plan_steps` for mkfont steps; the page reads it through `GET /api/jobs/<id>/report/<step>.json` and shows the
counts in the step row: "cut 2,300 (368 top, 2,299 bottom)" instead of only the stdout tail). `tools/test_mkfont.py`
gains the report tests (section 11); `docs/tools.md` gets the flag (its census test demands a section per tool, not per
flag; the builder adds a sentence).

### 8.3 Cost and UI

Cost: one Pillow pass over the range (`measure_boxes` renders every glyph once) plus the bake: a few seconds for
2,446 glyphs at 16 px (the recipes' precomposed bake; not timed with `--report`). The probe runs on demand when the
clipping panel opens (`GET .../probe/<font>/<size>.json` bakes under the font's preview lock, like the source PNG;
`TIMEOUT_S` 60 as for a bake), once per font and size, cached until a keyed setting changes (7.2). It uses the prepared
source (section 10). Only the mkfont route has a probe: for a jamo set the cell is the layout's and nothing is cut by
construction (jamoset composes inside the cell); for bdfface the BDF's box is the cell.

UI, a "clipping" disclosure under each outline font's override panel: the size select (the font's effective sizes),
the ascent field (prefilled with the probe's `ascent`, i.e. mkfont's own choice for that mode), cell height (the
effective `cell` or size), a live count line "N glyphs cut: T at the top, B at the bottom; W wider than the cell", the
overlay canvas (`drawGlyphs` of the sample text plus the 12 worst-cut glyphs, cell rectangle stroked, cut rows tinted),
and the per-glyph list (code point, character, top rows, bottom rows; sorted by rows cut, capped at 200 rows with
"and N more") that scrolls the overlay to a glyph on click. "Apply" writes the ascent into `options.mkfont.ascent` and
ticks `clip_cell` (the user keeps `fit_cell` as an alternative; the live count under `fit_cell` is shown as "the run
decides the size").

## 9. Jamo sets from decomposable fonts and the identity check (D)

### 9.1 Routes

Two new jamo routes for `outline` sources (never `outline-composite`, which has `composite`; CFF fonts qualify for
both):

- `Route("jamo", "mask fit", False, ["844", "adaptive"], [1, 2], None, "outline", None, _mask_fit_commands)`:
  `jamoset.py --layout L --from-ttf SRC --size S [--binarize threshold | --bpp 2] --mask-font SRC --check -o OUT`.
  Offered when the entry carries `gsub_jamo: true` (new detect fact: the font's `GSUB` FeatureList has `ljmo`, `vjmo`
  and `tjmo`, read with fontTools in `detect._sfnt_facts`; the label gets "; conjoining jamo (GSUB)") **and**
  `caps.mask_libs` is true. The mask font is the source itself (the point of the route: the font's own positional
  variants confine the pieces); a separate mask font is not offered (its data would have to be uploaded and licensed
  too). The worker passes `--pylib $JAMOSET_PYLIB` when set, and `ENV` gains `JAMOSET_PYLIB` and `JAMOSET_MASK_FONT`
  from `os.environ` when present (they are paths, no shell). The route is `experimental` like the fit: the page's
  `experimental` box enables it, and `route_for` prefers it over `experimental fit` when offered (design call: a font
  that shapes jamo should be fitted under its own masks; the user can still pick "experimental fit" per font through a
  new per-font `jamo_route` key, label-valued, default null = the first usable). Validation: `"%s: mask fit needs
  freetype-py and uharfbuzz (JAMOSET_PYLIB)"` when selected without caps.
- `Route("jamo", "vector fit", False, ["844", "adaptive"], [1, 2], None, "outline", _vector_prepare,
  _vector_commands)`: prepare `jamovec.py master SRC -o master.json [--adaptive]` (no `--components`), then
  `jamovec.py render master.json --size S --bpp B --binarize threshold --check -o OUT` (exactly `_composite_*` without
  the flag). Always offered for `outline`; needs fontTools only. Cost: unknown here (the composite master took 25 s; the
  raster separation renders every drawn syllable at 48 px first: expect minutes; the plan's end-to-end test uses the
  synthetic 2-syllable fixture, section 11).

`experimental fit` stays as it is. `presets.ALL_SOURCES` does not change (no new source kind); `ROUTES["outline"]`
lists the four jamo routes in order `experimental fit`, `mask fit`, `vector fit`, and `offeredRoutes` filters `mask
fit` by `font.gsub_jamo && caps.mask_libs`. `quality.measure` scores both against the `outline` reference as it does
the fit (same reference semantics: the face's header ascent is the Hangul baseline).

### 9.2 Degrading without the optional libraries

`jamofit.libs_available(pylib)` is the one check, run at server start with `JAMOSET_PYLIB` from the environment and
exposed as `caps.mask_libs`. `binarize mono` and `mask fit` are hidden (not disabled) without it; a saved setting that
needs them is a validation error naming the fix (`--pylib`/`JAMOSET_PYLIB`). jamoset's own "fitting without the mask
font" fallback is never relied on: the maker refuses rather than silently fitting free.

### 9.3 The identity check: what is scored

The structural check is `--check` (every route runs it): the table composes all 11,172 syllables and every piece the
table names has a glyph; it says nothing about a piece looking like its jamo. The identity check asks, per piece,
whether the syllables composed with it are read as their jamo by a recogniser. With `caps.recog`:

- Scope: `jamo` steps whose face `quality.face_facts(...)["jset"]` is a JSET with sets and classes (not a JMAP/LIST
  face, whose pieces are not per-jamo in the same way; a LIST face gets "identity check: not applicable (LIST)").
  1 bpp faces are scored as they are; a 2 bpp face is thresholded at level 2 (`quality.compare`'s "IoU at level 2"
  convention) before scoring, and the report says so.
- Input: `quality.composed_syllables(face)` (every syllable's cell, the engine's own composition); the pieces of each
  syllable from `jamoset.pieces_of` (the same numbers `svfw_pieces` returns).
- Model: `maker/recog_score.py` wraps exactly the calls `jamomerge.Scorer` makes (`sys.path.insert(0, SVF_RECOG_DIR)`,
  `import recog`, `recog.load("11-12")`, `recog.split`, `recog._heads(net, bool[n, h, w])`), batched (256 cells a
  call), `torch.set_num_threads(2)`, with a 180 s budget after which the report is "identity check: timed out"
  (design call; a 2,446-glyph face is not the question, 11,172 composed cells are).
- Per syllable: `ok_head[s] = (argmax_L == L, argmax_V == V, argmax_T == T)` and the three log-probabilities.
- Per piece p (initial/medial/final slot k, jamo j, set n): `users` = the syllables whose slot k is p; `read` = the
  share of users whose head k is correct; `nll` = the mean of `-log p_k` over users; `worst` = the five users with the
  largest `-log p_k`. Flag: `pass` when `read >= 0.95`, `warn` when `0.80 <= read < 0.95`, `fail` below, and `fail`
  also when a piece has no users (unused pieces are listed, not scored) is **not** a fail (listed as `unused`).
  Thresholds are a decision needed (D4); they are constants in `recog_score.py`, reported in the JSON so a later change
  is visible.
- Face level: `recog_ks` = share of the 2,350 KS syllables read on all three heads, `recog_all` over 11,172,
  `pieces: {pass, warn, fail, unused}` counts, `identity: "pass" | "warn" | "fail"` = the worst piece flag.

Without `caps.recog`: `identity = {"available": false, "structural": "<the --check line of the step's stdout>"}` and
the UI shows "identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; numpy and torch
needed)". The run is never blocked by it.

### 9.4 Where it runs and what it writes

In the worker, in `_read_back`, after `quality.measure` for `jamo` steps: `step["identity"]` gets the face-level
summary (small: it is in the job JSON the page polls), and the full per-piece table goes to
`work/sNN/identity.json` (`{"available": true, "model": "11-12", "recog_dir": ..., "thresholds": {...},
"bpp_note": ..., "face": {...}, "pieces": [{"piece": 161, "slot": "m", "jamo": "ㅏ", "set": 0, "users": 588,
"read": 0.991, "nll": 0.03, "flag": "pass", "worst": [44032, ...]}, ...]}`), served by
`GET /api/jobs/<id>/identity/<step>.json`. The zip's build log gets one line per jamo step (`identity: pass, 344
pieces, 2 warn, 0 fail, ks 0.97` or `identity check unavailable`); nothing of it goes into the face. A scorer
exception (bad weights, an import error after the caps check) is `{"available": false, "error": "<message>"}` and the
step stays `done`.

### 9.5 The UI

A "pieces" panel under a jamo step's preview: the summary line with the flag coloured (pass green, warn amber, fail
red, unavailable grey), then the per-piece table (slot, jamo, set, users, read %, flag; sorted fail first, then warn,
then by read ascending), each row drawing the piece from `svfw_glyph(slot, 0xF0000 + piece)` at 2x and, on expansion,
its five worst syllables composed by `svfw_glyph` beside the same syllables drawn from the job's precomposed face at
that size when one is done (the reference the eye compares against; else the outline source's PNG is not drawn, the
column is left empty). A failing piece's row carries "fix: fit again with a mask (mask fit), more sets (adaptive), or a
LIST exception for its worst syllables (jamoexc.py, not in the maker)". The panel also shows the structural line.

## 10. Source previews for prepared fonts (E)

`server._make_source_preview` draws `preview.source_png` from the uploaded path with `face_index`; it must draw the
prepared font. (design call) The server prepares in-process, not through the `source` step: `srcprep.prepared_bytes(
data, ops)` applied to the entry's `prep` plus the planned `instance` op (the same list `plan_steps` builds, factored
into `settings.source_ops(font, eff)` so both use one function), written to `work/preview/<font id>/source.<ext>` under
the font's preview lock, and that path given to `source_png` with `face_index` 0. `prepared_bytes` learns the
`instance` op (`fontTools.varLib.instancer.instantiateVariableFont(TTFont, coords, inplace=False)`, the in-process
twin of the CLI the step runs; the `PrepError` it raises today becomes the implementation). The `pcf-bdf` op produces a
BDF Pillow reads at its strike; a KSC/johab BDF still has no Unicode charmap and stays "none" (`PREVIEW_KINDS`
unchanged). The probe (section 8) and the on-demand source bake use the same prepared path. The prepared file is
dropped with the font's previews (the glob covers `<font id>/`). Cost: the instancer on a large VF takes seconds; it
runs once per settings change under the lock, as the PNG does.

`PREVIEW_KINDS` and the drift test's `bake` extraction do not change; the test gains
`test_source_preview_draws_the_prepared_font` (section 11).

## 11. Tests (F)

Fixtures are synthetic (built in the test with fontTools / `fixtures.py` / `inputfx.py`) or OFL (`ttf/`, `svf/`). No
new dependency; tests needing emcc, node, chromium, the optional libraries or a recogniser skip with a message that
names what is missing (`unittest.SkipTest`), as `test_web_picker.py` does. Gates that must stay green: the maker suite
(539 tests today, run through `heavy`), `make -C c check`, `tools/test_web_picker.py` (TestModule: the oracle),
`web/test/check.mjs` where playwright-core exists (not here; its cases are the picker's and this design does not touch
`web/picker.js` or `web/index.html`; the shared `emcc-flags.sh` must keep `web/build.sh`'s output identical: the test
compares the two scripts' `svf.wasm` bytes), the MCU size gates (unchanged by construction: `c/src` is not touched;
`git diff --stat c/src` empty is asserted in the plan's review gate).

| Slice | Test (file) | Fixture | Proves |
|---|---|---|---|
| A exports | `tools/test_web_picker.py TestModule.test_glyph_metrics_pieces_cmap` | `svf/dos/NEODG16.SVF` (precomposed), `NEODG16A.SVF` (jamo), a 2 bpp face from `ttf/` baked in the test | `svfw_glyph` == `jamoset.parse_svfn(...).glyphs[cp]` bytes and == `jamoset.compose` for a syllable; `svfw_metrics` == the parsed metrics (advance, bearing, ink_w, dy); `svfw_pieces` == `jamoset.pieces_of`; `svfw_cmap_cp` lists the parsed code points in file order; `svfw_line_box` == `svfline.measure` |
| A compositor | `TestModule.test_glyph_compositor_equals_line` (render.mjs gains a `glyphs` spec: per-glyph draws with a pen computed as 6.4) | the same faces, `detect.SAMPLE_TEXT`, a text with U+0301 | no overrides: byte-equal to `svfw_draw`; `ascentOverride = ascent + 2`: equal to `svfw_draw` of the same face with header byte 16 patched to `ascent + 2` (a copy, reopened); `dy {0x67: 1}`: equal to `svfw_draw` of the face after `svfdy.apply` |
| A endpoints | `maker/test/test_server.py` `FaceBytesTest` | a job with one done mkfont step (the existing `run_batch` helper) | `/face/<step>.svf` bytes == the step's output; ETag/304; 404 for `source`/`prepare` steps, another job's step, a path escape; `/api/repo/face/dos/NEODG16.SVF` served, `../` refused; `/api/caps` keys and the `mask_libs`/`recog` values follow the environment (monkeypatched) |
| A page | `test_server.py test_page_js_tables_match_python` (extended) and `test_page_wires_the_preview` (`node --check` on `svfview.js`, the import string present, no `preview.png` reference left in `maker.js`) | - | the mirror tables, the module path |
| A browser | `maker/test/smoke_dom.py` (not in the unittest discovery; run by the plan's review gate): starts the server on port 0, uploads `ttf/neodgm/neodgm.ttf` + its OFL, runs, then `chromium --headless=new --disable-gpu --virtual-time-budget=10000 --dump-dom http://127.0.0.1:PORT/?job=ID` and asserts the DOM holds a `<canvas data-step="s01" data-drawn="1">` whose `data-ink` attribute (the page sets the count of non-zero bytes after drawing) is > 0 and no `data-error` | OFL neodgm | the module loads and draws in a real browser; skipped when no chromium/google-chrome is found |
| B schema | `test_settings.py` `ControlsTest` | synthetic entries | each new key's type and range message (exact strings), `fit_cell`+`clip_cell` refused, `binarize mono` refused without caps, `dy` shape and the piece refusal, the seven range names accepted and `write_range_files` writing seven files whose contents equal `mkfont.NAMED_RANGES` |
| B argv | `test_routes.py` `PanelArgvTest` (extended) | - | every (label, bpp) emits exactly the flags of 7.3; `apply_flags` replaces `--binarize threshold`; `VALUED` holds the new flags |
| B dy step | `test_plan_inputs.py` `DyStepTest` | `inputfx.ttf` + dy `{"0x41": 1}` | the mkfont step's argv list ends with the svfdy argv naming `dy.json`; end to end the face parses with `dy == {0x41: 1}` and `facecheck` passes; a dy on `0xF0000` is a validation error |
| B fit/width/latin | `test_plan_inputs.py` end to end on `inputfx.ttf` | synthetic | `--fit-cell` run exits 0 and the report's `mode` is `fit`; `--width 20` gives cell_w 20; `--latin` changes the ascent of a Latin-only bake (two bakes differ) |
| C report | `tools/test_mkfont.py test_report_json` | a synthetic TTF with one glyph whose ink spans -12..+3 at 16 px (fontTools pen box) | `boxes` carries it; with `--cell 12 --ascent 10 --clip-cell` `cut` says top 2 bottom 1 and `counts` match `fit_counts`; nudge mode lists it under `nudged`; `--fit-cell` reports the lowered `size` |
| C probe | `test_server.py` `ProbeTest` | the same synthetic TTF | `GET .../probe/f01/16.json` bakes once (a second GET does not re-run: the mtime is unchanged), the `.svf` draws through the module with no row cut (ink rows == span), a settings PUT changing `width` removes both |
| C page math | `maker/test/test_clip_math.mjs` run by `node --test` from a unittest wrapper | the report JSON above | the page's `cutRows(box, ascent, cell_h)` equals `fit_counts`'s rule for a table of ascents (the Python side computed in the test and embedded) |
| D detect | `test_detect_inputs.py test_gsub_jamo_fact` | `inputfx.ttf` + a GSUB table with `ljmo`/`vjmo`/`tjmo` features built with `fontTools.otlLib.builder` | `gsub_jamo` true, the label suffix; a font with only `ljmo` is false |
| D routes | `test_routes.py` `DecomposableRoutesTest` | - | `mask fit` offered only with `gsub_jamo` and caps; argv has `--mask-font SRC`; `vector fit` always; `route_for` precedence and the `jamo_route` override |
| D vector e2e | `test_plan_inputs.py test_vector_fit_end_to_end` | `fixtures._composite_ttf`'s outlines flattened to plain glyphs (2 syllables, no components) | `jamovec master` without `--components` then render, job done, `facecheck`, `quality` not None |
| D mask e2e | `test_real_inputs.py test_mask_fit` | `ttf/neodgm/neodgm.ttf` (OFL, has the three features: recipes.md) | skipped unless `jamofit.libs_available()`; job done, the step's stdout names the mask font, not the "fitting without the mask font" line |
| D identity | `maker/test/test_recog_score.py` | a fake `recog.py` written into a temp dir by the test (`load` returns a stub; `split` the arithmetic; `_heads` returns one-hot log-probabilities that read every syllable correctly except those using piece 161), `SVF_RECOG_DIR` pointed at it; numpy and torch are **not** needed by the stub (the wrapper imports them only through `recog`); `svf/dos/NEODG16A.SVF` | piece 161 `fail`, every other piece `pass`, `recog_ks` matches, the JSON shape; with `SVF_RECOG_DIR` unset: `available false`; a raising stub: `available false` with `error`, the step `done` |
| D worker | `test_jobs.py test_identity_written_for_jamo_steps` | the stub above + a DOS raw fixture job | `step["identity"]` summary, `work/sNN/identity.json`, the log line |
| E prepared preview | `test_server.py test_source_preview_draws_the_prepared_font` | `inputfx.variable_ttf()` with instance `{"wght": 700}`; `inputfx.mac_cmap_ttf()` | the PNG differs from the default-instance PNG (the gvar delta moves `ga`); the Mac font gets a PNG at all (today none); the prepared file is under `work/preview/<fid>/` and removed on an instance change |
| F regression | the full suite through `heavy`; `make -C c check`; `tools/test_web_picker.py`; `cmp` of `web/build.sh` and `maker/build-wasm.sh` wasm outputs | - | nothing else moved |

## 12. Task decomposition hint (G)

Independent slices, each a commit series with its own tests, in the order that keeps the suite green at every commit:

1. **A1 glue exports + oracle tests** (`svf_web.c`, `render.mjs`, `test_web_picker.py`, `emcc-flags.sh`,
   `maker/build-wasm.sh`). No maker change. Risk: none to `c/src`; the review gate asserts `git diff c/src` empty.
2. **A2 face endpoints + caps** (`server.py`, `test_server.py`). Independent of A1.
3. **A3 `svfview.js` + the result preview in the page**, removing `preview.png` from the worker (`maker.js`,
   `svfview.js`, `jobs.py`, `settings._step`, `smoke_dom.py`). Depends on A1, A2. Risk: the page is the least tested
   layer; the `--dump-dom` smoke and the node compositor test are the proof, and the glyph compositor must be written
   from `svf_draw.c`'s pen rule, not from `svfline.py`.
4. **B1 schema + panel_argv + OPTION_VISIBLE** (settings, presets, routes `VALUED`, maker.js tables, the drift test).
   Independent of A. Risk: the drift test's key naming change (`group.key`); do it in one commit with both sides.
5. **B2 dy step + named ranges** (`plan_steps`, `RANGE_FILES`, tests). Depends on B1.
6. **C1 `mkfont.py --report`** (tools + `tools/test_mkfont.py` + `docs/tools.md`). Independent.
7. **C2 probe endpoint + clipping panel** (server, page). Depends on C1, A3, B1.
8. **D1 `gsub_jamo` detect fact + routes `mask fit`/`vector fit` + ENV passthrough** (detect, routes, jobs, settings
   `jamo_route`, maker.js ROUTES/offeredRoutes). Depends on B1 (the binarize/ascent flags) only for the panel rows.
   Risk: `vector fit` run time on a real font is unknown; the e2e test uses the 2-syllable fixture; a real-font run is
   env-gated (`SVF_MAKER_REAL_VF`-style variable `SVF_MAKER_REAL_VECTOR`) and recorded in the commit body.
9. **D2 `recog_score.py` + worker + identity endpoint + panel**. Depends on A3 (the piece drawing). Risk: the real
   recogniser's input contract is inferred from `jamomerge.Scorer` only; the stub test pins the wrapper, and the first
   run against real weights is a manual step the plan records (what `SVF_RECOG_DIR` was, the model's cell size).
10. **E prepared source preview** (`srcprep.prepared_bytes` instance op, `settings.source_ops`, server). Independent.
11. **F closing**: the full gates, the audit's section 3 and gap list rewritten to the new state, `maker/README.md`
    (still missing from T15) gets the build step for the module.

Parallelisable: {1, 2, 4, 6, 10} first; then {3, 5}; then {7, 8}; then 9; then 11.

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

Each with my recommendation; the design above assumes the recommendation.

- **D1. Source preview of outline/bitmap sources: keep Pillow PNG, or bake a quick 1-size SVF and draw it with WASM
  too?** Recommendation: keep the PNG for the "source" column (it answers "what does this font look like", and the C
  renderer has no outline path), and let the probe face (section 8, mkfont at one size) be the WASM-drawn "what the
  converter makes" view; that keeps one renderer for every face while not waiting seconds for a thumbnail. Alternative:
  replace the PNG by the probe everywhere (one fewer code path, slower first paint).
- **D2. `mask fit` precedence over `experimental fit`** when a font shapes jamo and the libraries are present
  (section 9.1): recommended yes, with the per-font `jamo_route` override.
- **D3. `--report` as a flag of `tools/mkfont.py`** (section 8.2; the only change to `tools/` in this card besides
  none): recommended yes, it is the data the page needs and a CLI user wants it too; the alternative is a maker-side
  re-implementation of `measure_boxes`, which would drift from mkfont.
- **D4. Identity thresholds** pass >= 0.95, warn >= 0.80 of a piece's users read correctly on that head (section 9.3):
  I have no calibration (no recogniser here); the numbers are constants to tune after the first real run. Recommended:
  accept as placeholders, report them in the JSON, revisit with real faces.
- **D5. Dropping the PNG result preview entirely** (section 6.5) rather than keeping it as a fallback when the module
  is not built: recommended drop, per decision 5.1 (one renderer); the page says how to build the module.
- **D6. Which named ranges to list** (section 7.1: the five more of `mkfont.NAMED_RANGES`; `cp949` is 17,048
  syllables and Hanja-sized bakes): recommended all five, since the tool has them; `ascii` stays always on (today's
  rule).
- **D7. The vector-fit route always on for outline fonts** although its run time is unmeasured here: recommended on,
  behind `experimental` like the fit, with a note on the page ("minutes per font"); measure on the first real run and
  decide whether to drop it.
