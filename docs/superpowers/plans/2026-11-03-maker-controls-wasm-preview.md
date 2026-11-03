# Maker controls and the WASM preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The SVF maker draws every face in the browser with the C renderer built to WebAssembly, exposes the
recipes' controls (ascents, width, Latin, fit/clip cell, per-glyph dy, AA refine, clean, binarize, named ranges),
shows which rows a cell cuts before the build, builds jamo sets from decomposable OFL fonts, and scores pieces with an
optional recogniser. Card t_9acea7ab.

**Architecture:** Four layers, in this order. (1) Foundations with no maker coupling: new exports in the WASM glue
`c/ports/web/svf_web.c` (no `c/src` change), `tools/mkfont.py --report/--probe`, and a standalone
`maker/recog_score.py` CLI. (2) Settings: the options schema, per-command panel fragments, and the routes' argv.
(3) The browser preview: byte-serving GET endpoints, `maker/static/svfview.js` (the drawing layer and the per-glyph
compositor that mirrors `walk_next`), the page wiring, and the end of the server-drawn result PNG. (4) Features on
top: the dy step and named ranges, the build report and the clipping probe, the `mask fit` / `vector fit` routes, the
prepared-source preview, and the identity check in the worker.

**Tech Stack:** Python 3 stdlib, fontTools 4.66.1, Pillow 10.2.0, unittest; emscripten (`~/opt/emsdk`, not on PATH)
for the module; node 22 (`/usr/bin/node`) for module tests, `node --check` and `node --test`; `google-chrome` /
`chromium-browser` for the one headless DOM smoke run. The page is plain ES modules.

**Spec:** `docs/superpowers/specs/2026-11-03-maker-controls-wasm-preview-design.md` at `98e8dad` (sections 6-12; rulings
in 15; review dispositions in 16). Read with `docs/maker-audit.md`. Section numbers below ("6.4", "7.1") are the
spec's. All commands run from the worktree root `~/work/svf-fonts-open-wt/maker-controls` (branch `maker-controls`,
base `01a943f`). No push.

## Global Constraints

- **`c/src` and `c/include` are unchanged.** Every task's last step runs gate G1; any output fails the task.
- **Gates run at the end of every task** (before its commit), in this order:
  - G1 `git diff --exit-code 01a943f -- c/src c/include` -> exit 0, no output.
  - G2 `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'` -> `OK` (skips allowed), and
    `Ran N tests` with N = the task's stated count. The suite is 539 tests at `98e8dad`; it stays green at every task.
    If the observed N differs from the stated count, the implementer writes the observed N and the reason in the
    commit body (a stated count is a plan estimate, the green suite is the requirement).
  - G3 `python3 -m unittest discover -s maker/test -p 'test_server.py' -k test_page_js_tables_match_python` -> `OK`.
    Every change to `routes.py`, `presets.panel_argv` or the settings keys ships its `maker.js` rows and the drift
    test's `every`/`flags` update in the same commit (spec 7.6, 12).
- **Serialization.** No two tasks that edit `maker/settings.py`, `maker/routes.py` or `maker/server.py` run at the same
  time; tasks sharing any file run in plan order. The parallel windows are named in "Review groups".
- **Data.** No proprietary data. Fixtures are synthetic (built in the test with fontTools, `maker/test/fixtures.py`,
  `inputfx.py`) or OFL from `ttf/` and `svf/`. No recogniser, weights or training data enter the repository.
- **No new dependency.** Not on this host and never required by a test: playwright-core (`web/test/node_modules`),
  numpy, torch, freetype-py, uharfbuzz. A test that needs one skips with `unittest.SkipTest("<what is missing>")`.
  On this host emcc (`~/opt/emsdk/upstream/emscripten/emcc`), node and Chrome exist, so the WASM tests run here.
- **`tools/` changes only where the spec says:** `tools/mkfont.py` (`--report`, `--probe`, `--probe-cell`) and its
  test, `tools/test_web_picker.py` (module tests), `docs/tools.md` (the two flags). `tools/svfdy.py` is used as is.
- **Long runs through the OOM guard:** the full maker suite, `tools/test_web_picker.py`, `tools/test_mkfont.py`, and
  `make -C c check` run under `~/.local/bin/heavy`.
- **No bare `git stash`.** Set work aside with a WIP commit on the branch.
- **Server binding and origins unchanged:** 127.0.0.1, the `Host`/`Origin` rule of `_check_same_origin`; nothing
  assumes a tailnet or systemd.
- **Commits** end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and name the card
  `(t_9acea7ab)` in the subject.

## Review Focus

1. **A step re-run while the page fetches its face.** `GET .../face/<step>.svf` must 404 for a step that is not
   `done` even when an old output file is still on disk, never serve the previous run's bytes. Pinned by
   `FaceBytesTest.test_face_404_while_the_step_is_not_done` (Task 6).
2. **A combining mark with a dy, after a code point no slot has, in a two-slot chain at 3/2.** The compositor must
   still equal the core's draw of the patched face (one `svfw_draw` per code point, marks at the pen). Pinned by
   `TestModule.test_compositor_mark_after_a_missing_code_point` (Task 7).
3. **A dy on a face `svfdy.py` refuses** (a precomposed upload with no metrics table on the copy route). The step must
   fail with the tool's own message, not pass with the dy silently dropped. Pinned by
   `DyStepTest.test_dy_on_a_face_without_metrics_fails_with_the_tool_message` (Task 9).
4. **A probe whose ink span passes 255 rows.** The probe JSON is served with `probe_face: false`, the `.svf` URL is a
   404, and the page shows the list without the overlay. Pinned by `ProbeTest.test_probe_without_face` (Task 11).
5. **A saved `jamo_route: "mask fit"` after the libraries went away** (server restarted without `JAMOSET_PYLIB`).
   The job loads with `mask_ok: false`, validation names the fix, and `run` is refused. Pinned by
   `DecomposableRoutesTest.test_saved_mask_route_without_libs_is_refused` (Task 12).

## Verified while planning (this host, `98e8dad`)

- emcc exists at `~/opt/emsdk/upstream/emscripten/emcc`; node v22.23.2; `google-chrome` and `chromium-browser` on
  PATH; numpy not importable; `maker/README.md` does not exist; `ttf/ebgaramond/EBGaramond-VF.ttf`,
  `ttf/neodgm/neodgm.ttf`, `svf/dos/MARUS20.SVF`, `NEODG16.SVF`, `NEODG16A.SVF` exist.
- `routes.Route.commands(font, size, bpp, layout, range_spec, paths, extra)`; `plan_steps` builds `extra` as
  `apply_flags(presets.argv_for(preset, kind, size), presets.panel_argv(options, kind, label, bpp))`.
- `run_command(argv, cwd, timeout, cancel)` writes `stdout.txt`/`stderr.txt` into `cwd`, so the identity run uses its
  own subdirectory (Task 14).
- `jamoset.py` parses `--mask-font` in the same parser as `--bpp 2`, but `main_aa` never reads it.
- `TestModule.run_script(body, *args)` runs a node ES-module script with the built module dir as argv[1].

Not verified (the named tests verify them): `jamovec.py master` without `--components` on a 2-syllable flattened font
(Task 12 `test_vector_fit_end_to_end`); the recogniser's numpy/torch contract (Task 3 `test_numpy_path`, skipped
here); a mask fit run (Task 12 `test_real_inputs.test_mask_fit`, skipped here); the page in a browser beyond the DOM
smoke run (playwright absent).

## File map

| File | Status | Responsibility (task) |
|---|---|---|
| `c/ports/web/svf_web.c` | modify | six exports (1) |
| `c/ports/web/emcc-flags.sh` | create | the one compile line, sourced by both build scripts (1) |
| `c/ports/web/README.md` | modify | the six exports (1) |
| `web/build.sh` | modify | sources `emcc-flags.sh` (1) |
| `maker/build-wasm.sh` | create | builds `maker/static/wasm/svf.{js,wasm}` (1) |
| `.gitignore` | modify | `maker/static/wasm/` (1) |
| `tools/test_web_picker.py` | modify | export oracle tests (1), compositor tests (7) |
| `tools/mkfont.py`, `tools/test_mkfont.py`, `docs/tools.md` | modify | `--report`, `--probe`, `--probe-cell` (2) |
| `maker/recog_score.py` | create | identity scoring CLI (3) |
| `maker/caps.py` | create | `wasm` / `mask_libs` / `recog` capability checks (6) |
| `maker/settings.py` | modify | schema (4), extras (5), `_step` (8, 10, 14), dy/ranges (9), report/`face_argv` (10, 11), routes (12), `source_ops` (13) |
| `maker/presets.py` | modify | `panel_argv` per command (5) |
| `maker/routes.py` | modify | `route_for(jamo_route)` (4), `_with_extra`, `VALUED`, fit argv (5), named ranges (9), new routes (12) |
| `maker/server.py` | modify | GET endpoints, caps, invalidation, `mask_ok` (6), drop step PNG (8), report (10), probe (11), prepared source (13), identity (14) |
| `maker/jobs.py` | modify | drop `preview.png` (8), stale report (10), `_reference` (12), identity (14) |
| `maker/detect.py` | modify | `gsub_jamo` (12) |
| `maker/srcprep.py` | modify | `instance` op in `prepared_bytes` (13) |
| `maker/zipout.py` | modify | identity log line (14) |
| `maker/static/svfview.js` | create | module loader, drawing layer, compositor (7) |
| `maker/static/clip.js` | create | the page's cut-row math (11) |
| `maker/static/maker.js` | modify | panel inputs (4, 5), result preview (8), dy/range UI (9), report row (10), clipping panel (11), routes rows (12), pieces panel (14) |
| `maker/test/smoke_dom.py` | create | headless DOM smoke run, outside discovery (8) |
| `maker/test/test_recog_score.py`, `test_svfview.py`, `test_clip_math.py`, `test_clip_math.mjs` | create | (3), (7), (11), (11) |
| `maker/README.md` | create | how to run the maker and build the module (15) |
| `docs/maker-audit.md` | modify | section 3 and the gap list to the new state (15) |

---

# Group 1: foundations

Tasks 1, 2 and 3 touch disjoint files and may run in parallel with each other and with Task 4. Task 5 starts after
Task 4.

### Task 1: WASM glue exports, the shared compile line, `maker/build-wasm.sh` (slice A1)

**Files:**
- Modify: `c/ports/web/svf_web.c`, `c/ports/web/README.md`, `web/build.sh`, `.gitignore`, `tools/test_web_picker.py`
- Create: `c/ports/web/emcc-flags.sh`, `maker/build-wasm.sh`

**Interfaces:**
- Produces (`svf_web.c`, all `EMSCRIPTEN_KEEPALIVE`, spec 6.3):
  - `int svfw_metrics(int slot, uint32_t cp, int32_t *out)` - `svf_metrics_of`'s 1 / 0 / -1; `out[0..3]` = advance,
    bearing_x, ink_w, dy; -1 for a slot not open or `out == NULL` (out untouched).
  - `int svfw_cell_bytes(int slot)` - `svf_cell_bytes`, 0 for a slot not open.
  - `int svfw_glyph(int slot, uint32_t cp, uint8_t *cell, uint32_t len)` - `svf_glyph`'s `svf_err`; `SVF_E_ARG` for a
    slot not open or `cell == NULL`.
  - `int svfw_pieces(int slot, uint32_t cp, uint16_t *out)` - `svf_jamo_pieces`' count 0..3 (piece numbers,
    `0xFFFF` = blank); 0 for a slot not open or `out == NULL`.
  - `int svfw_cmap_cp(int slot, int i)` - the code point of entry i; -1 when `i < 0`, `i >= svf_glyph_count`, or the
    slot is not open (checked before the `uint16_t` cast).
  - `int svfw_line_box(const char *text, int len, int x, int baseline, int32_t *out)` - `svf_measure_utf8` on the
    chain: `out = {x, baseline - ascent, width, baseline + descent}`; returns its `svf_err` (`SVF_E_ARG` for
    `len < 0` or `out == NULL`).
- Produces (`c/ports/web/emcc-flags.sh`, sourced, defines no output path itself):
  `svf_web_compile ROOT OUT_DIR` - runs `EM_CONFIG="$EMSDK/.emscripten" "$EMSDK/upstream/emscripten/emcc"` with exactly
  today's `web/build.sh` flags over `$ROOT/c/ports/web/svf_web.c $ROOT/c/src/*.c`, writing `OUT_DIR/svf.js` and
  `OUT_DIR/svf.wasm`; exits 1 with today's "no emcc at ..." message when emcc is missing. `EMSDK` defaults to
  `~/opt/emsdk`.
- Produces: `maker/build-wasm.sh` - sources `emcc-flags.sh`, `svf_web_compile "$ROOT" "$ROOT/maker/static/wasm"`, prints
  `svf.wasm N bytes, svf.js N bytes`; writes nothing else.

- [ ] **Step 1: Write the failing tests** in `tools/test_web_picker.py` `TestModule` (each uses `run_script`; a JS
  helper string `EXPORTS_JS` opens the faces given as args and prints, per code point asked, `metrics` (`[rc, a, b, w,
  dy]`), `glyph` (hex of `svfw_cell_bytes` bytes, or the error number), `pieces` (the returned count of numbers), and
  the full `cmap` list plus the out-of-range probes):

```python
def test_glyph_metrics_pieces_cmap(self):
    # faces: NEODG16.SVF (precomposed), NEODG16A.SVF (jamo), MARUS20.SVF (stored dy), and a 2 bpp face baked here by
    # mkfont from ttf/nanumgothic at 16 px, --unicode ascii,AC00-AC0F
    for path in faces:
        f = jamoset.parse_svfn(read(path))
        out = self.run_script(EXPORTS_JS, path, json.dumps(sample_cps(f)))
        self.assertEqual(out["cmap"], cmap_in_file_order(f))
        self.assertEqual([out["cmap_m1"], out["cmap_count"], out["cmap_65536"]], [-1, -1, -1])
        for cp in stored_sample(f):
            self.assertEqual(bytes.fromhex(out["glyph"][str(cp)]), f.glyphs[cp])
            self.assertEqual(out["metrics"][str(cp)], [1, *f.metrics[cp], f.dy.get(cp, 0)])
    a = jamoset.parse_svfn(read(face_path("dos/NEODG16A.SVF"))); t = jamoset.unpack(a.jset)
    out = self.run_script(EXPORTS_JS, face_path("dos/NEODG16A.SVF"), json.dumps([0xAC00, 0xD7A3, 0x3131]))
    for cp in (0xAC00, 0xD7A3):
        self.assertEqual(bytes.fromhex(out["glyph"][str(cp)]), jamoset.compose(a, t, cp))
        self.assertEqual(out["pieces"][str(cp)], jamoset.pieces_of(t, cp))      # numbers; piece 0 is real here
        self.assertEqual(out["metrics"][str(cp)],
                         [1, svfline.measure([face_path("dos/NEODG16A.SVF")], chr(cp))[0], 0, a.cell_w, 0])

def test_unopened_slot_answers(self):
    # slot 1 never opened: metrics -1, cell_bytes 0, glyph 7 (SVF_E_ARG), pieces 0, cmap_cp -1, has 0

def test_line_box_matches_svfline(self):
    for scale in ((1, 1), (2, 1), (3, 2)):
        paths = [face_path("dos/MARUS20.SVF"), face_path("dos/NEODG16.SVF")]
        w, asc, desc = svfline.measure(paths, "Ag가 gy", scale=scale)
        self.assertEqual(self.line_box(paths, "Ag가 gy", scale, x=1, baseline=40), [1, 40 - asc, w, 40 + desc])

def test_maker_build_matches_web_build(self):
    # runs maker/build-wasm.sh with ROOT pointing at a temp copy's output dir override (env SVF_WASM_OUT, see Step 3)
    # and compares svf.wasm bytes with built_dist()'s svf.wasm: equal; svf.js equal
```

  `maker/build-wasm.sh` honours `SVF_WASM_OUT` (default `$ROOT/maker/static/wasm`) so the test never writes into the
  tree.

- [ ] **Step 2: Run** `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py -k "glyph_metrics or unopened_slot or line_box or maker_build" -v`. Expected: FAIL (`_svfw_metrics is not a function`,
  no `maker/build-wasm.sh`).
- [ ] **Step 3: Implement** the six exports (thin calls, the argument checks of the existing exports; no new state),
  `emcc-flags.sh`, `web/build.sh` sourcing it, `maker/build-wasm.sh`, `.gitignore` line `maker/static/wasm/`, the
  README rows.
- [ ] **Step 4: Run** `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py -v`. Expected: `OK`; `TestPage`
  skips ("no playwright-core"); every existing `TestModule` test still passes (the oracle). Then
  `~/.local/bin/heavy make -C c check` -> exit 0.
- [ ] **Step 5: Gates** G1, G2 (539), G3.
- [ ] **Step 6: Commit** `git add c/ports/web tools/test_web_picker.py web/build.sh maker/build-wasm.sh .gitignore && git commit -m "web: glue exports for metrics, glyphs, pieces, cmap and the line box; one compile line for the picker and the maker (t_9acea7ab)"`.

Cannot verify here: nothing beyond the page tests (playwright absent; they skip and are untouched by this task).

### Task 2: `mkfont.py --report` and `--probe` (slice C1)

**Files:**
- Modify: `tools/mkfont.py`, `tools/test_mkfont.py`, `docs/tools.md` (mkfont section: one sentence per flag)

**Interfaces:**
- Produces (`tools/mkfont.py`):
  - CLI `--report FILE.json` (any mode), `--probe`, `--probe-cell H` (int, only with `--probe`; `--probe` refuses
    `--cell`, `--ascent`, `--clip-cell`, `--fit-cell` with exit 2 `"--probe sets the cell and ascent itself"`).
  - `probe_cell(boxes: dict) -> tuple[int, int]` - `(A0, cell_h)` with `A0 = max(1, -min_top)`,
    `cell_h = A0 + max(0, max_bottom)`; `(1, 1)` for no boxes.
  - `build_report(*, size, requested_size, cell_w, cell_h, ascent, auto_ascent, mode, latin, bpp, boxes, cut, nudged,
    probe, probe_face) -> dict` - the JSON of spec 8.2 with keys `tool, probe, probe_face, size, requested_size, cell,
    ascent, auto_ascent, mode, latin, bpp, boxes, cut, wide, nudged, counts`; `boxes` keys `"0x%X"`, values
    `[left, top, right, bottom]`; `cut` present only when `mode == "clip"` (`{"0x..": {"top", "bottom", "full",
    "fringe"}}`); `nudged` present only when `mode == "nudge"`; `counts = {"glyphs", "top", "bottom", "wide", "cut"}`
    from `fit_counts` at the final ascent (`cut` = size of top ∪ bottom).
  - `mode`: `"fit"` with `--fit-cell`, `"clip"` with `--clip-cell` (and in probe mode), else `"nudge"`. A glyph is
    `nudged` when `font.getbbox(ch, anchor="ls")[1] + ascent < 0` (exactly `render`'s vertical nudge condition).
  - Probe: measure boxes over the `--unicode` set at `--size`/`--bpp`; `A0, cell_h = probe_cell(boxes)`; when
    `cell_h <= 255` bake with that cell, ascent `A0` and `nudge=False`, report `"probe": true, "probe_face": true`;
    else write only the report with `"probe_face": false` and exit 0. With `--probe-cell H`,
    `auto_ascent = fit_ascent(boxes, H, choose_ascent(font, H, latin))[0]`; without it `auto_ascent = ascent`.
    `--width` stays the caller's (the maker always passes it).

- [ ] **Step 1: Write the failing tests** in `tools/test_mkfont.py`, class `ReportTest`, with a module helper
  `tall_ttf(path)` (FontBuilder, unitsPerEm 1000, glyph `ga` at U+AC00 and `A` at U+0041, both a rectangle x 100..600,
  y -180..740; at 16 px 1 bpp its box rows are -12..3):

```python
def test_report_json(self):
    rep = self.bake("--size", "16", "--bpp", "1", "--cell", "12", "--ascent", "10", "--clip-cell")
    self.assertEqual(rep["boxes"]["0xAC00"][1:4:2], [-12, 3])
    self.assertEqual(rep["cut"]["0xAC00"]["top"], 2)
    self.assertEqual(rep["cut"]["0xAC00"]["bottom"], 1)
    top, bottom, wide = mkfont.fit_counts({int(k, 16): v for k, v in rep["boxes"].items()}, 12, 12, 10)
    self.assertEqual(rep["counts"], {"glyphs": len(rep["boxes"]), "top": len(top), "bottom": len(bottom),
                                     "wide": len(wide), "cut": len(set(top) | set(bottom))})
    self.assertEqual((rep["mode"], rep["ascent"], rep["cell"]), ("clip", 10, [12, 12]))

def test_nudge_mode_lists_nudged(self):
    rep = self.bake("--size", "16", "--bpp", "1", "--cell", "12", "--ascent", "10")
    self.assertEqual(rep["mode"], "nudge"); self.assertIn("0xAC00", rep["nudged"]); self.assertNotIn("cut", rep)

def test_fit_cell_reports_the_lowered_size(self):
    rep = self.bake("--size", "16", "--bpp", "1", "--cell", "12", "--fit-cell")
    self.assertEqual((rep["mode"], rep["requested_size"]), ("fit", 16)); self.assertLess(rep["size"], 16)

def test_probe_mode(self):
    rep, face = self.probe("--size", "16", "--bpp", "1", "--width", "16", "--probe", "--probe-cell", "12")
    f = jamoset.parse_svfn(face)
    self.assertEqual((f.cell_h, f.ascent, rep["probe"], rep["probe_face"]), (15, 12, True, True))
    boxes = {int(k, 16): v for k, v in rep["boxes"].items()}
    font = ImageFont.truetype(self.src, 16)
    self.assertEqual(rep["auto_ascent"], mkfont.fit_ascent(boxes, 12, mkfont.choose_ascent(font, 12, False))[0])
    self.assertEqual(mkfont.fit_counts(boxes, 16, 15, 12), ([], [], []))        # nothing cut by construction

def test_probe_past_255_rows_writes_only_the_report(self):
    rep, face = self.probe("--size", "300", "--bpp", "1", "--width", "300", "--probe")
    self.assertEqual((rep["probe_face"], face), (False, None))

def test_probe_refuses_cell_flags(self):
    # each of --cell 12, --ascent 9, --clip-cell, --fit-cell with --probe: exit 2, stderr names "--probe"
```

  `self.bake(*flags)` runs `python3 -P tools/mkfont.py SRC OUT --unicode ascii,AC00 --report R *flags`, asserts exit
  0, returns the JSON; `self.probe` returns `(json, face bytes or None)`.

- [ ] **Step 2: Run** `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_mkfont.py -k Report -v`. Expected:
  FAIL (`unrecognized arguments: --report`).
- [ ] **Step 3: Implement** to the interface; stdout lines stay as they are (the report is an extra file); the
  `docs/tools.md` sentences.
- [ ] **Step 4: Run** `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_mkfont.py' -v` and
  `python3 -m unittest discover -s tools -p test_tools_doc.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (539), G3.
- [ ] **Step 6: Commit** `git commit -m "mkfont: --report JSON of boxes and cuts, --probe bake in a cell that cuts nothing (t_9acea7ab)"`.

Cannot verify here: nothing; all of it runs on fontTools and Pillow.

### Task 3: `maker/recog_score.py`, the identity scoring CLI (slice D2, first half)

**Files:**
- Create: `maker/recog_score.py`, `maker/test/test_recog_score.py`

**Interfaces:**
- Produces (`maker/recog_score.py`, puts `tools/` on `sys.path` itself, runs under `-P`):
  - CLI `recog_score.py FACE.SVF -o OUT.json [--threads N] [--batch 256] [--arrays numpy|lists]`. Reads
    `$SVF_RECOG_DIR` (exit 2 `"SVF_RECOG_DIR is not a directory with recog.py"` when unset or without `recog.py`).
    `--threads` calls `torch.set_num_threads` only when `importlib.util.find_spec("torch")`. Exit 1 with
    `"recog: <exception>"` on stderr when `recog` raises; exit 0 after writing OUT.
  - `THRESHOLDS = {"pass": 0.95, "warn": 0.80}`; `MODEL = "11-12"`.
  - `score_face(face_bytes: bytes, R, net, to_array, batch=256) -> dict` - the JSON below. Cells are passed to
    `R._heads(net, to_array(cells, h, w))` in ascending syllable index, `batch` at a time (the stub relies on it).
  - `lists_array(cells: list[bytes], h: int, w: int, bpp: int) -> list` (nested `bool`), `numpy_array(...)` (numpy
    `bool[n, h, w]`); a 2 bpp cell is thresholded at level 2 (`>= 2`) and the JSON then has
    `"bpp_note": "2 bpp thresholded at level 2"`, else `null`.
  - JSON: `{"available": true, "applicable": true, "model": "11-12", "thresholds": THRESHOLDS, "bpp_note": ...,
    "face": {"recog_ks", "recog_all", "pieces": {"pass", "warn", "fail", "unused"}, "identity"},
    "pieces": [{"piece", "slot" ("i"|"m"|"f"), "jamo" (compat letter), "set", "users", "read", "nll", "flag",
    "worst": [{"cp", "got"}]}]}` (spec 9.3). Grouping key `(slot, piece)`; `set` = the table's set number at the first
    user's cell. `pieces` sorted fail, warn, pass, unused, then `read` ascending. A face whose JSET is a LIST/JMAP
    (`detect.usable_jset` is a `jamoset.Jmap`) gives `{"available": true, "applicable": false, "reason":
    "not applicable (LIST)"}`, exit 0. `recog_ks` is over `mkfont.NAMED_RANGES["ksx1001-hangul"]()`.

- [ ] **Step 1: Write the failing tests** (`RecogScoreTest`; `setUp` writes a stub `recog.py` into a temp dir: `load(m)`
  returns `"net"`; `split(idx)` returns `(L, V, T)` lists by arithmetic; `_heads(net, arr)` returns one-hot log
  probabilities (0 for the right jamo, -20 elsewhere) for each row, reading every syllable correctly except those
  listed in `bad.json` (written by the test: the syllable indices whose slot-k piece is 161 in NEODG16A, and k), whose
  head k gets argmax = (right + 1) mod n; the stub counts rows across calls to map row -> syllable index):

```python
def test_piece_161_fails_every_other_passes(self):
    out = self.run_cli(face_path("dos/NEODG16A.SVF"), "--arrays", "lists")
    flags = {(p["slot"], p["piece"]): p["flag"] for p in out["pieces"]}
    self.assertEqual(flags[(self.slot, 161)], "fail")
    self.assertEqual({f for key, f in flags.items() if key != (self.slot, 161)} - {"unused"}, {"pass"})
    self.assertEqual(out["face"]["identity"], "fail")

def test_face_summary_and_json_shape(self):
    out = self.run_cli(face_path("dos/NEODG16A.SVF"), "--arrays", "lists")
    ks = set(cp - 0xAC00 for cp in mkfont.NAMED_RANGES["ksx1001-hangul"]())
    self.assertAlmostEqual(out["face"]["recog_ks"], 1 - len(ks & set(self.bad)) / 2350)
    self.assertEqual((out["model"], out["thresholds"], out["bpp_note"]), ("11-12", {"pass": 0.95, "warn": 0.80}, None))
    self.assertEqual(sorted(out["pieces"][0]), ["flag", "jamo", "nll", "piece", "read", "set", "slot", "users", "worst"])
    self.assertLessEqual(len(out["pieces"][0]["worst"]), 5)

def test_a_raising_recogniser_exits_1(self):
    # stub whose load raises RuntimeError("no weights"): exit 1, stderr "recog: no weights", no OUT

def test_no_recog_dir_exits_2(self):
    # SVF_RECOG_DIR unset, then a dir without recog.py: exit 2 with the message

@unittest.skipUnless(importlib.util.find_spec("numpy"), "numpy is not installed: the numpy path is unverified")
def test_numpy_path(self):
    # the same stub with --arrays numpy gives the same JSON as --arrays lists
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_recog_score.py -v`. Expected: ERROR (no
  `recog_score.py`).
- [ ] **Step 3: Implement** `maker/recog_score.py`.
- [ ] **Step 4: Run** the same. Expected: `OK` with `test_numpy_path` skipped.
- [ ] **Step 5: Gates** G1, G2 (544 = 539 + 5), G3.
- [ ] **Step 6: Commit** `git add maker/recog_score.py maker/test/test_recog_score.py && git commit -m "maker: recog_score.py scores jamo pieces with an optional recogniser (t_9acea7ab)"`.

Cannot verify here: the numpy/torch path and the real recogniser's input contract (cell size, `_heads` shapes); the
first run against real weights is a manual step recorded on the card (the `SVF_RECOG_DIR` used, the model's cell size).

### Task 4: options schema, choice values, ascent keys, `dy` and `jamo_route` (slice B1, first half)

**Files:**
- Modify: `maker/settings.py` (`DEFAULT_OPTIONS`, `FONT_ONLY_KEYS`, `_FONT_ONLY_DEFAULTS`, `_options_type_errors`,
  `_option_errors`, `_ascent_cell_errors`, `_type_errors`, `_route_errors`), `maker/routes.py` (`route_for`),
  `maker/static/maker.js` (`ADVANCED`, `FLAG_KEYS`, `CHOICE_KEYS`, `readOptions`, `readPerPanel`, `fillOptions`,
  `advancedFieldset`), `maker/test/test_settings.py`, `maker/test/test_server.py`

**Interfaces:**
- Produces (`settings.py`):
  - `DEFAULT_OPTIONS` exactly spec 7.2 (three groups `mkfont`, `jamoset`, `bdfface`), `OPTION_CHOICES =
    {"binarize": ("threshold", "ridge", "mono")}`. Keys stay unique across groups.
  - `FONT_ONLY_KEYS += ("dy", "jamo_route")`, both default `None`.
  - Type messages: `"%s: option jamoset.binarize is not one of threshold, ridge, mono"`;
    `"%s: dy is not an object of code point -> int"` (keys parse with `int(k, 0)` or are one character, values ints);
    `"%s: jamo_route %s is not a route label"` (not a string or null).
  - Range messages (`_option_errors`, every ascent-like key is `1..`): `"%s: width %s is not 1..255"`,
    `"%s: aa_refine %s is not 0..9"`, `"%s: jamo_ascent %s is not 1..cell"`, `"%s: fit_baseline %s is not 1..size"`,
    `"%s: latin_ascent %s is not 1..box"`, `"%s: hangul_ascent %s is not 1..box"`, and mkfont `ascent` 0 now refused
    as `"%s: ascent 0 is not 1..cell"` (the existing `"is not 0..cell"` wording becomes `"is not 1..cell"`; existing
    assertions on it are updated in place).
  - `_ascent_cell_errors` covers four keys, each against its own cell: `ascent` (`cell` or every size, unchanged);
    `jamo_ascent` (`font["sizes"][0]` for `dos-raw`, `font["bdf"]["box"][1]` for `bdf-johab`); `fit_baseline` (every
    size); `latin_ascent`/`hangul_ascent` (`font["bdf"]["box"][1]`). Message `"%s: <key> %s is over the cell %s"`.
  - dy rules (`_route_errors`): key `>= 0xF0000` -> `"%s: dy %s names a jamo piece"`; value outside
    `-L..L` with `L = min(127, cell_h)` (`cell_h` = `options.mkfont.cell` or each effective size) ->
    `"%s: dy %s of %s is not -%d..%d"` (fid, value, key as written, L, L); `"%s: dy needs a precomposed face"` when
    `dy` is non-empty and `"precomposed"` is not in the effective kinds.
  - jamo_route rules: `"%s: jamo_route %s is not offered"` (no jamo route of that label for the font);
    `"%s: jamo_route %s needs experimental"` (a non-native label without `experimental`).
- Produces (`routes.py`): `route_for(font, kind, experimental, jamo_route=None) -> Route | None` - with `kind ==
  "jamo"` and a label, the route of that label when offered and (`native` or `experimental`), else None; otherwise
  today's rule. `plan_steps`, `_route_errors` and `jobs._reference` pass `eff.get("jamo_route")`.
- Produces (`maker.js`): `ADVANCED` gains `{key, group, label}` rows for `width, fit_cell, latin` (mkfont),
  `jamo_ascent, fit_baseline, aa_refine, clean, binarize` (jamoset), `latin_ascent, hangul_ascent` (bdfface);
  `FLAG_KEYS` gains `fit_cell, latin, clean`; `CHOICE_KEYS = {"binarize": ["threshold", "ridge", "mono"]}` drawn as
  a `<select data-option="binarize">`; `readOptions` / `readPerPanel` / `fillOptions` read and fill a choice select by
  its string value, and treat `clean` as a flag whose default is on. No `OPTION_VISIBLE` change (Task 5).

- [ ] **Step 1: Write the failing tests** (`test_settings.py` class `ControlsTest`, synthetic entries in the file's
  existing style; `test_server.py` one test):

```python
def test_new_defaults_and_unique_keys(self):
    keys = [k for group in settings.DEFAULT_OPTIONS.values() for k in group]
    self.assertEqual(len(keys), len(set(keys)))
    self.assertEqual(settings.DEFAULT_OPTIONS["jamoset"]["clean"], True)
    self.assertEqual(settings.DEFAULT_OPTIONS["bdfface"], {"latin_ascent": None, "hangul_ascent": None})

def test_choice_value_type(self):
    errs = self.errors(options={"jamoset": {"binarize": "otsu"}})
    self.assertIn("f01: option jamoset.binarize is not one of threshold, ridge, mono", errs)

def test_int_ranges(self):
    for key, group, bad, msg in (("width", "mkfont", 0, "f01: width 0 is not 1..255"),
                                 ("aa_refine", "jamoset", 10, "f01: aa_refine 10 is not 0..9")):
        self.assertIn(msg, self.errors(options={group: {key: bad}}))

def test_ascent_zero_refused_on_every_ascent_key(self):
    # ascent (outline font), jamo_ascent (dos-raw), fit_baseline (outline, experimental), latin_ascent and
    # hangul_ascent (bdf-ksc5601): each 0 gives "f01: <key> 0 is not 1..<word>"

def test_ascent_keys_against_their_cells(self):
    # jamo_ascent 17 on a 16 px DOS raw font -> "f01: jamo_ascent 17 is over the cell 16";
    # hangul_ascent 25 with bdf box [24, 24] -> "... is over the cell 24"; fit_baseline 17 with sizes [16]

def test_dy_shape_and_bounds(self):
    self.assertIn("f01: dy is not an object of code point -> int", self.errors(dy={"0x41": "1"}))
    self.assertIn("f01: dy 0xF0001 names a jamo piece", self.errors(dy={"0xF0001": 1}))
    self.assertIn("f01: dy 17 of 0x41 is not -16..16", self.errors(dy={"0x41": 17}))     # sizes [16]
    self.assertEqual(self.errors(dy={"0x41": -2, "g": 1}), [])

def test_dy_needs_a_precomposed_face(self):
    self.assertIn("f01: dy needs a precomposed face", self.errors(kinds=["jamo"], experimental=True, dy={"0x41": 1}))

def test_jamo_route_rules(self):
    self.assertIn("f01: jamo_route hanterm is not offered", self.errors(kinds=["jamo"], jamo_route="hanterm"))
    self.assertIn("f01: jamo_route experimental fit needs experimental",
                  self.errors(kinds=["jamo"], jamo_route="experimental fit"))

def test_route_for_with_jamo_route(self):
    self.assertEqual(routes.route_for(OUTLINE_COMPOSITE, "jamo", True, "composite").label, "composite")
    self.assertIsNone(routes.route_for(OUTLINE, "jamo", False, "experimental fit"))

# test_server.py
def test_page_advanced_lists_the_new_keys(self):
    js = read_text(MAKER_JS)
    for key in ("width", "fit_cell", "latin", "jamo_ascent", "fit_baseline", "aa_refine", "clean", "binarize",
                "latin_ascent", "hangul_ascent"):
        self.assertRegex(js, r'\{key: "%s", group: "(mkfont|jamoset|bdfface)"' % key)
    self.assertIn('const CHOICE_KEYS = {"binarize": ["threshold", "ridge", "mono"]}', js)
    if shutil.which("node"):
        self.assertEqual(subprocess.run(["node", "--check", MAKER_JS]).returncode, 0)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_settings.py -k Controls -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Existing assertions that compare `DEFAULT_OPTIONS`-derived dicts or the old `"0..cell"`
  wording are updated in place (no test removed).
- [ ] **Step 4: Run** `test_settings.py`, `test_routes.py`, `test_server.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (554 = 544 + 10; 549 if Task 3 has not landed yet), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: options schema for the recipes' controls, dy and jamo_route keys (t_9acea7ab)"`.

Cannot verify here: nothing.

### Task 5: per-command panel fragments, `VALUED`, the fit's `--mask-font none`, the visibility table (slice B1, second half)

**Files:**
- Modify: `maker/presets.py` (`panel_argv`), `maker/routes.py` (`VALUED`, `_with_extra`, every `_*_commands`,
  `_fit_commands`), `maker/settings.py` (`plan_steps` extras, `_route_errors` merged-flag rules),
  `maker/static/maker.js` (`OPTION_VISIBLE`), `maker/test/test_routes.py`, `maker/test/test_plan_inputs.py`,
  `maker/test/test_v3_output.py`, `maker/test/test_server.py` (drift test), `maker/test/test_settings.py`

**Interfaces:**
- Consumes: Task 4 keys, `OPTION_CHOICES`.
- Produces:
  - `presets.panel_argv(options, kind, route_label, bpp) -> list[list[str]]` - one fragment per command the panel
    addresses: `[[...]]` for every route but `"bdfface + from-svf fit"`, which gets `[argv0_flags, argv1_flags]`. Rows
    (spec 7.1/7.3, today's labels only): mkfont `--cell`, `--ascent`, `--width`, `--mono-hint` (bpp 1), `--clip-cell`,
    `--fit-cell`, `--latin`, `--space-advance`; `dos raw`/`hanterm` today's plus `--ascent <jamo_ascent>`;
    `composite` today's plus `--baseline <fit_baseline>`, `--binarize X` (bpp 1); `experimental fit` today's plus
    `--baseline`, `--binarize X` (bpp 1), `--aa-refine N` (bpp 2), `--no-clean` when `clean` is false (both bpps);
    `bdfface` `--ascent <latin_ascent>`, `--hangul-ascent N`; `bdfface + from-svf fit` those on argv 0 and
    `--jset-version` on argv 1. `--binarize` is emitted only when the value is not `"threshold"` (every route's own
    default), so a default panel changes no argv.
  - `routes._with_extra(commands, extras: list[list[str]])` - `extras` aligned with the **last** `len(extras)`
    commands; `[]` = no change. Every `commands(..., extra)` parameter is now this list of fragments.
  - `routes.VALUED` gains `--baseline --width --aa-refine --mask-font --mask-radius --hangul-ascent --pylib --report`.
  - `_fit_commands` at bpp 1 appends `--mask-font none` (bpp 2 unchanged: `main_aa` never reads it).
  - `plan_steps`: `panel = presets.panel_argv(...)`; `panel[-1] = apply_flags(presets.argv_for(preset, kind, size),
    panel[-1])`; `route.commands(..., panel)`.
  - `_route_errors` merged rules (on `apply_flags(preset fragment, panel[-1])` of each selected size):
    `"%s: fit_cell and clip_cell: choose one"`; `"%s: binarize mono needs freetype-py"` (font lacks `mask_ok`);
    `"%s: binarize mono is not a jamovec choice"` (`composite`).
  - `OPTION_VISIBLE` = spec 7.3 without the `mask fit` and `vector fit` rows.
  - Drift test: `flags` resolves a flag by the label's tool (`TOOL_OF_LABEL` table in the test: `--ascent` -> `ascent`
    under mkfont, `jamo_ascent` under `dos raw`/`hanterm`, `latin_ascent` under the two bdfface labels; the rest
    one-to-one); `every` sets every key (`width: 18, latin: True, aa_refine: 3, clean: False, binarize: "ridge",
    jamo_ascent: 12, fit_baseline: 12, latin_ascent: 12, hangul_ascent: 13`) and runs twice (`clip_cell: True,
    fit_cell: False`, then the reverse), the union per (label, bpp); fragments are flattened before mapping.

- [ ] **Step 1: Write the failing tests** (`test_routes.py` class `PanelArgvTest`, extended):

```python
EVERY = {"mkfont": {"cell": 18, "ascent": 12, "width": 18, "mono_hint": True, "clip_cell": True, "fit_cell": False,
                    "latin": True, "space_advance": 5},
         "jamoset": {"embolden": True, "symbols": True, "jset_version": 2, "jamo_ascent": 12, "fit_baseline": 12,
                     "aa_refine": 3, "clean": False, "binarize": "ridge"},
         "bdfface": {"latin_ascent": 12, "hangul_ascent": 13}}

def test_per_command_fragments(self):
    self.assertEqual(presets.panel_argv(EVERY, "jamo", "bdfface + from-svf fit", 1),
                     [["--ascent", "12", "--hangul-ascent", "13"], ["--jset-version", "2"]])
    self.assertEqual(presets.panel_argv(EVERY, "jamo", "experimental fit", 2),
                     [["--symbols", "--jset-version", "2", "--baseline", "12", "--aa-refine", "3", "--no-clean"]])
    self.assertEqual(presets.panel_argv(EVERY, "jamo", "dos raw", 1),
                     [["--embolden", "--symbols", "--jset-version", "2", "--ascent", "12"]])

def test_bdfface_flags_land_on_argv_0(self):
    cmds = routes.route_for(FONT_KSC, "jamo", True).commands(FONT_KSC, 24, 1, "844", ("file", "/u/c.txt"), P,
                                                             presets.panel_argv(EVERY, "jamo", "bdfface + from-svf fit", 1))
    self.assertIn("--hangul-ascent", cmds[0]); self.assertNotIn("--hangul-ascent", cmds[1])
    self.assertEqual(cmds[1][-2:], ["--jset-version", "2"])

def test_binarize_replaces_the_default(self):
    argv = routes.route_for(FONT_TTF, "jamo", True).commands(FONT_TTF, 16, 1, "844", ("2350", None), P, [["--binarize", "ridge"]])[0]
    self.assertEqual(argv.count("--binarize"), 1); self.assertEqual(argv[argv.index("--binarize") + 1], "ridge")

def test_valued_holds_the_new_flags(self):
    self.assertTrue({"--baseline", "--width", "--aa-refine", "--mask-font", "--mask-radius", "--hangul-ascent",
                     "--pylib", "--report"} <= routes.VALUED)

def test_fit_passes_mask_font_none_at_1_bpp(self):
    one = routes.route_for(FONT_TTF, "jamo", True).commands(FONT_TTF, 16, 1, "844", ("2350", None), P, [])[0]
    two = routes.route_for(FONT_TTF, "jamo", True).commands(FONT_TTF, 16, 2, "844", ("2350", None), P, [])[0]
    self.assertEqual(one[one.index("--mask-font") + 1], "none"); self.assertNotIn("--mask-font", two)

# test_settings.py ControlsTest
def test_fit_cell_against_the_merged_clip_cell(self):
    self.assertIn("f01: fit_cell and clip_cell: choose one", self.errors(options={"mkfont": {"fit_cell": True, "clip_cell": True}}))
    self.assertIn("f01: fit_cell and clip_cell: choose one",
                  self.errors(preset="dos-u-2bpp", bpp=[2], options={"mkfont": {"fit_cell": True}}))

def test_binarize_mono_refusals(self):
    self.assertIn("f01: binarize mono needs freetype-py",
                  self.errors(kinds=["jamo"], experimental=True, bpp=[1], options={"jamoset": {"binarize": "mono"}}))
    self.assertIn("f01: binarize mono is not a jamovec choice",
                  self.errors(font=OUTLINE_COMPOSITE, kinds=["jamo"], bpp=[1], options={"jamoset": {"binarize": "mono"}}))
```

  Existing assertions moved in this commit (no test removed): every `presets.panel_argv(...) == [...]` in
  `test_routes.py` becomes `== [[...]]`; every `commands(..., <flat list>)` call in `test_routes.py`,
  `test_plan_inputs.py` (lines near 310, 320) and `test_v3_output.py:70` wraps its fragment as `[<list>]`; every
  exact 1 bpp experimental-fit argv in `test_routes.py`/`test_plan_inputs.py` gains `"--mask-font", "none"` after
  `-o OUT` (or `--eng ENG`).

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_routes.py -k PanelArgv -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `panel_argv`, `_with_extra`, `VALUED`, the fit argv, `plan_steps`, the merged rules, the
  `OPTION_VISIBLE` rows and the drift test's `every`/`flags` in one commit.
- [ ] **Step 4: Run** `test_routes.py`, `test_settings.py`, `test_plan_inputs.py`, `test_v3_output.py`, `test_server.py`.
  Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (561 = 554 + 7), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: per-command panel flags for every recipe control, --mask-font none on the free fit (t_9acea7ab)"`.

Cannot verify here: `binarize mono` cannot run (freetype-py absent); only its refusal is tested.

**Group 1 review gate.** Reviewer runs G1-G3, `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py`,
`~/.local/bin/heavy python3 -m unittest discover -s tools -p test_mkfont.py`, `~/.local/bin/heavy make -C c check`,
and checks: the six exports are thin and stateless; `web/build.sh`'s output is byte-identical before and after (the
test); `OPTION_VISIBLE` equals spec 7.3 minus two rows; a default panel leaves every existing argv unchanged except the
fit's `--mask-font none`; no key name is shared across option groups.

---

# Group 2: the preview in the browser

Task 6 and Task 7 touch disjoint files and may run in parallel; Task 8 starts after both.

### Task 6: byte-serving endpoints, caps, the GET host check, invalidation keys, `mask_ok` (slice A2)

**Files:**
- Create: `maker/caps.py`
- Modify: `maker/server.py` (`STATIC_TYPES`, `_ROUTES`, `_handle`, `_static`, `_serve_file`, `_load`,
  `_changed_preview_fonts`, `_jset_flags` -> `_bake_flags`, `make_server`), `maker/jobs.py` (`Worker.__init__`
  takes `caps=None`), `maker/test/test_server.py`

**Interfaces:**
- Consumes: Task 4 key names (`jamo_route`, `options.*`).
- Produces (`maker/caps.py`):
  - `wasm_built(static_dir) -> bool` - `wasm/svf.js` and `wasm/svf.wasm` are files.
  - `mask_libs(environ) -> bool` - `jamofit.libs_available(environ.get("JAMOSET_PYLIB"))`.
  - `recog_dir(environ) -> str | None` - `SVF_RECOG_DIR` when it is a directory holding `recog.py` and
    `importlib.util.find_spec` finds `numpy` and `torch` (nothing imported).
  - `compute(static_dir, environ) -> {"wasm": bool, "mask_libs": bool, "recog": bool}`.
- Produces (`server.py`):
  - `make_server` stores `server.caps = caps.compute(static_dir, os.environ)` once and passes it to the Worker
    (`worker.caps`).
  - `STATIC_TYPES[".wasm"] = "application/wasm"`.
  - `Handler._serve_bytes(path, content_type)` - `Cache-Control: no-cache`, `ETag: "<size>-<mtime_ns>"`,
    `If-None-Match` equal -> 304 with no body; used by `_static` and every new GET.
  - Routes (regexes exactly): `^/api/jobs/JOB/face/(?P<step>s\d+)\.svf$` -> `_job_face`;
    `^/api/jobs/JOB/source/(?P<font>f\d+)\.svf$` -> `_job_source_face`;
    `^/api/repo/face/(?P<group>[A-Za-z0-9_-]+)/(?P<file>[A-Z0-9_]+\.SVF)$` -> `_repo_face`; `^/api/caps$` -> `_caps`.
    `_HOST_CHECKED = {"_job_face", "_job_source_face", "_repo_face", "_job_report", "_job_probe", "_job_identity"}`;
    `_handle` runs `_check_same_origin` for those handler names too (the last three land in Tasks 10, 11, 14).
  - `_job_face`: the step's `output` when the step is that job's, `state == "done"`, `kind in ("precomposed",
    "jamo")`, and the path is `_inside(job_dir)`; else 404.
  - `_job_source_face`: `work/preview/<fid>.svf` for `dos-raw`, `svf-precomposed`, `svf-jamo` entries, baked on
    demand by calling `_make_source_preview` under `_preview_lock` (exactly as the source PNG GET does); 404 otherwise.
  - `_load(job_id)` stamps `font["mask_ok"] = self.server.caps["mask_libs"]` into every `outline` /
    `outline-composite` entry of the loaded job (not saved; every load re-stamps).
  - `_changed_preview_fonts` compares `preview_inputs(eff)` - a dict of exactly the keys of spec 6.5:
    `dos_layout, sizes, kinds, bpp, range, preset, latin_companion, instance, experimental, jamo_route`,
    `options.mkfont.{cell, width, latin, mono_hint, space_advance}`, `options.jamoset.{jset_version, jamo_ascent,
    embolden, symbols}`.
  - `_bake_flags(eff, source_kind) -> list[str]`: `--jset-version V` for every bake; for `dos-raw` also `--ascent N`
    (jamo_ascent), `--embolden`, `--symbols`. `_make_source_preview` passes it to `preview.bake_source_face`.

- [ ] **Step 1: Write the failing tests** (`test_server.py` class `FaceBytesTest(ApiTest)`, using `minimal_job` and
  `run_to_done`):

```python
def test_face_bytes_and_etag(self):
    jid = self.minimal_job(); job = self.run_to_done(jid); step = job["steps"][0]
    r = self.raw("GET", "/api/jobs/%s/face/%s.svf" % (jid, step["id"]))
    self.assertEqual((r.status, r.getheader("Content-Type"), r.getheader("Cache-Control")),
                     (200, "application/octet-stream", "no-cache"))
    self.assertEqual(r.read(), read(self.srv.store.path(jid, step["output"])))
    again = self.raw("GET", "/api/jobs/%s/face/%s.svf" % (jid, step["id"]), headers={"If-None-Match": r.getheader("ETag")})
    self.assertEqual((again.status, again.read()), (304, b""))

def test_face_404s(self):
    # another job's step id, s99, a "prepare" step (forced into the job JSON), "../" in the path: all 404

def test_face_404_while_the_step_is_not_done(self):
    # after run_to_done, set the step's state to "running" through the store (the output file stays): 404

def test_new_gets_check_host(self):
    # Host: evil.example on /face/, /source/, /api/repo/face/dos/NEODG16.SVF -> 403; /api/caps and /static/maker.js stay 200

def test_repo_face(self):
    self.assertEqual(self.raw("GET", "/api/repo/face/dos/NEODG16.SVF").read(), read(os.path.join(REPO, "svf/dos/NEODG16.SVF")))
    for bad in ("/api/repo/face/dos/neodg16.svf", "/api/repo/face/../NEODG16.SVF", "/api/repo/face/dos/NOPE.SVF"):
        self.assertEqual(self.raw("GET", bad).status, 404)

def test_caps_are_booleans_and_follow_the_environment(self):
    self.assertEqual({k: type(v) for k, v in self.get("/api/caps").items()}, {"wasm": bool, "mask_libs": bool, "recog": bool})
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "recog.py"), "w").close()
        self.assertEqual(caps.recog_dir({"SVF_RECOG_DIR": d}),
                         d if importlib.util.find_spec("numpy") and importlib.util.find_spec("torch") else None)
    self.assertIsNone(caps.recog_dir({}))

def test_source_face_served_for_a_dos_raw_font(self):
    # job with fixtures' DOS raw font + eng, dos_layout 844: GET /source/<fid>.svf -> 200, parses as a jamo face;
    # an outline font's /source/<fid>.svf -> 404

def test_mask_ok_stamped_on_every_load(self):
    jid = self.minimal_job()
    with mock.patch.dict(self.srv.caps, {"mask_libs": True}):
        self.assertTrue(all(f["mask_ok"] for f in self.get("/api/jobs/%s" % jid)["fonts"] if f["source_kind"].startswith("outline")))
    with mock.patch.dict(self.srv.caps, {"mask_libs": False}):
        self.assertFalse(any(f.get("mask_ok") for f in self.get("/api/jobs/%s" % jid)["fonts"]))

def test_changed_preview_fonts_new_keys(self):
    # for each of bpp, range, preset, experimental, jamo_route, options.mkfont.width, options.jamoset.jamo_ascent:
    # a settings pair differing only there -> ["f01"]; differing only in options.mkfont.ascent, clip_cell, fit_cell,
    # dy, options.jamoset.aa_refine, options.bdfface.latin_ascent -> []

def test_static_wasm_type_and_cache(self):
    # sets self.srv.static_dir to a temp copy of maker/static holding wasm/svf.wasm (a few bytes):
    # Content-Type application/wasm, Cache-Control no-cache, ETag present
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_server.py -k FaceBytes -v`. Expected: FAIL (404s).
- [ ] **Step 3: Implement.** The page is untouched in this task.
- [ ] **Step 4: Run** `test_server.py`. Expected: `OK` (the existing source-PNG tests unchanged).
- [ ] **Step 5: Gates** G1, G2 (571 = 561 + 10), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: face, source and repo face bytes, /api/caps, host check on byte GETs, preview keys, mask_ok on load (t_9acea7ab)"`.

Cannot verify here: `caps.mask_libs` true and `caps.recog` true (the libraries are absent); both are covered by
monkeypatching.

### Task 7: `maker/static/svfview.js`, the drawing layer and the per-glyph compositor (slice A3, first half)

**Files:**
- Create: `maker/static/svfview.js`, `maker/test/test_svfview.py`
- Modify: `tools/test_web_picker.py` (`TestModule` compositor tests)

**Interfaces:**
- Consumes: Task 1 exports.
- Produces (`maker/static/svfview.js`, an ES module with no DOM access at import time):
  - `NOTICE = "preview module not built: run maker/build-wasm.sh"`.
  - `init(M)` - use an instantiated module; `load(url = "/static/wasm/svf.js") -> Promise<M>` - imports and inits
    once; rejects with `new Error(NOTICE)` when the import fails.
  - `openChain(byteArrays: Uint8Array[]) -> info[]` - `svfw_reset`, frees the previous face buffers, mallocs and opens
    up to 4 in slot order; `info = {bpp, cellW, cellH, ascent, flags, status, count, jamo}` (`svfw_info`). Faces over
    16 MiB throw `Error("face over 16 MiB")`.
  - `setScale(num, den)`; `S(v) -> int` - `SCALE_LEN` with the reduced ratio: `Math.trunc((v * num +
    Math.trunc(den / 2)) / den)` for `v >= 0`, `-S(-v)` below.
  - `drawLineInto(text, {target = "gray8", threshold = 128, fg = 0xFFFF, bg = 0}) -> {w, h, baseline, pixels}` -
    `svfw_measure`; `w = width + 2`, `h = ascent + descent + 2`, pen x 1, `baseline = ascent + 1`; one `svfw_draw`.
  - `drawGlyphsInto(text, {ascentOverride = null, dy = {}, pitch = null, symbolsFixed = false, target, threshold, fg,
    bg}) -> {w, h, baseline, pixels}` - spec 6.4: one `svfw_draw` per code point (marks included), face = first slot
    with `svfw_has`; a code point no slot has advances 0 and draws nothing; pen `x += S(advance)` after a non-mark
    (`U+0300..036F` advance 0), or `x += pitch` when `pitch` is set; slot-0 glyphs at `y = baseline + S(A) - S(A') +
    S(d_new) - S(d_stored)`; other slots at `baseline`; composed code points of a jamo face have no dy term but take
    the ascent term; with `symbolsFixed`, U+2026 and U+25A1 get no ascent term. The line box follows
    `svf_measure_utf8` over the placed code points (ascent up `S(A') - S(d)`, descent down `S(cell_h) - S(A') + S(d)`,
    each slot with its own ascent), then the same `+2`/`+1` geometry as `drawLineInto`. `dy` keys are code point
    numbers.
  - `drawLine(canvas, text, opts)`, `drawGlyphs(canvas, text, opts)` - size the canvas, convert to ImageData (GRAY8
    -> grey on `bg`, MONO kinds and RGB565 decoded as the picker does), set `canvas.dataset.drawn = "1"` and
    `canvas.dataset.ink` = the count of non-zero pixels; on error set `canvas.dataset.error`.
  - `glyphCell(slot, cp) -> {w, h, bpp, levels: Uint8Array}`; `pieces(slot, cp) -> number[]` (trusts the count;
    piece 0 is real); `drawPiece(canvas, slot, p, scale)` draws `glyphCell(slot, 0xF0000 + p)`;
    `codePoints(slot) -> number[]` (every `svfw_cmap_cp`); `syllables(slot) -> number[]` (U+AC00..D7A3 with
    `svfw_has`); `has(slot, cp) -> bool` (`svfw_has`); `metrics(slot, cp) -> {rc, advance, bearing, inkW, dy}`; `lineBox(text, x, baseline) -> number[4]`.

- [ ] **Step 1: Write the failing tests.** `tools/test_web_picker.py` `TestModule` gains a JS body `GLYPHS_JS` that
  imports `maker/static/svfview.js` by file URL (argv), `init(M)`, opens the faces given, sets the scale and prints
  `{line: {w, h, hex}, glyphs: {w, h, hex}}` for the options given as JSON. Python builds the comparison faces:

```python
CHAIN = ["dos/MARUS20.SVF", "dos/NEODG16.SVF"]        # stored dy over a second slot
TEXT = "Ag가 gyé"                                     # Latin, a syllable, a glyph only slot 1 has
SCALES = ((1, 1), (2, 1), (3, 2))

def test_compositor_equals_line_without_overrides(self):
    for scale in SCALES:
        out = self.glyphs(CHAIN, TEXT, scale, {})
        self.assertEqual(out["glyphs"], out["line"])

def test_compositor_ascent_override_equals_the_patched_header(self):
    for scale in SCALES:
        a = jamoset.parse_svfn(read(face_path(CHAIN[0]))).ascent
        patched = self.tmp_face(CHAIN[0], header_byte_16=a + 2)
        self.assertEqual(self.glyphs(CHAIN, TEXT, scale, {"ascentOverride": a + 2})["glyphs"],
                         self.glyphs([patched, CHAIN[1]], TEXT, scale, {})["line"])

def test_compositor_dy_equals_svfdy(self):
    for scale in SCALES:
        for dy in ({0x67: 1, 0x41: -1}, {0x67: 1, 0x41: -1, "ascent": 2}):   # dy, then dy with an ascent override
            fixed = self.tmp_bytes(svfdy.apply(read(face_path(CHAIN[0])), {0x67: 1, 0x41: -1})[0], dy.get("ascent"))
            # compare drawGlyphsInto(dy, ascentOverride) on CHAIN with drawLineInto on [fixed, CHAIN[1]]

def test_compositor_marks(self):
    # face baked here: mkfont ttf/ebgaramond/EBGaramond-VF.ttf --size 20 --bpp 1
    # --unicode 0020-007E,00A1,00E9,00F2,0300-0304 (MARKS_AT_ORIGIN), chained over NEODG16; text "Aéò̂ gy ¡";
    # dy on a base (0x65), on a mark (0x301), on both: each equals drawLineInto of the svfdy-applied face, at SCALES

def test_compositor_mark_after_a_missing_code_point(self):
    # the marks chain, text "A\U0001F600́g" at 3/2 with dy {0x301: 1}: equal to the svfdy-applied line

def test_compositor_dos_raw_symbols_under_an_ascent_override(self):
    # jamoset.py <fixtures._dos_raw> --layout 844 --symbols --check -o A.svf, then the same with --ascent A+2 -o B.svf;
    # text "가…□A": drawGlyphsInto(A, ascentOverride=A+2, symbolsFixed=True) == drawLineInto(B)
```

  `maker/test/test_svfview.py` `SvfviewTest.test_module_parses_and_has_no_dom_at_import`: `node --check` on
  `svfview.js` exits 0, and `node --input-type=module -e "await import(<file url>)"` exits 0 (no `document` or
  `window` touched at import); the export names above are all present (`Object.keys` of the import).

- [ ] **Step 2: Run** `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py -k compositor -v` and
  `python3 -m unittest discover -s maker/test -p test_svfview.py`. Expected: FAIL (no `svfview.js`).
- [ ] **Step 3: Implement** `svfview.js` from `walk_next`'s rules (`c/src/svf_draw.c`), not from `svfline.py`.
- [ ] **Step 4: Run** both again and the whole `TestModule`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (572 = 571 + 1), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: svfview.js draws faces with the WASM renderer, per-glyph compositor for ascent and dy (t_9acea7ab)"`.

Decision recorded: the compositor tests drive `svfview.js` through `TestModule.run_script` (the spec's table names a
`glyphs` spec in `render.mjs`; `render.mjs` stays the picker's line oracle and is not changed).

Cannot verify here: `drawLine`/`drawGlyphs` on a real `<canvas>` (only the `*Into` buffer functions run under node);
Task 8's DOM smoke run is the browser check.

### Task 8: the result preview in the page, no more `preview.png` (slice A3, second half)

**Files:**
- Create: `maker/test/smoke_dom.py` (not matched by `test_*.py`)
- Modify: `maker/static/maker.js` (`stepRow`'s result cell, a `previewCell(step)` block, `fontMainRow` for baked
  sources, `previewSrc` kept for the source PNG only), `maker/static/index.html` (nothing else than the notice slot if
  needed), `maker/jobs.py` (`_read_back`), `maker/settings.py` (`_step`), `maker/server.py` (`_job_preview` serves
  `kind == "source"` only), `maker/test/test_jobs.py`, `maker/test/test_zipout.py`, `maker/test/test_server.py`

**Interfaces:**
- Consumes: Task 6 endpoints and `/api/caps`, Task 7 `svfview.js`.
- Produces:
  - `settings._step(...)` has no `preview` key; `jobs.Worker._read_back` no longer calls `preview.result_png`.
    `preview.result_png`, `svf_png`, `chain_for` stay (oracle helpers; `test_preview.py` unchanged).
  - `maker.js`: `import * as svfview from "./svfview.js"`; `previewCell(step)` for a `done` `precomposed`/`jamo`
    step: fetches `/api/jobs/<id>/face/<step>.svf` (cached per `(job, step, state, seconds)`), the companion =
    the same font's done precomposed face at that size, else `/api/repo/face/dos/NEODG16.SVF` (used when
    `!svfview.has(0, 0x41)`), and draws into `<canvas data-step="<id>">` with controls: sample text
    (`detect.SAMPLE_TEXT` default, kept per page), scale 1/1..4/1, target GRAY8 | MONO | RGB565, threshold, guides,
    a "glyphs" toggle (grid 16 a row, pitch `cell_w + 2`; a click shows metrics and, for a jamo face, the pieces).
    The ascent-to-try field exists only for `dos raw`/`hanterm` steps (apply -> `options.jamoset.jamo_ascent`); the
    dy-to-try field only for `precomposed` steps (apply -> per-font `dy`; Task 9 adds the setting's UI elsewhere).
    A rejected `svfview.load()` shows `svfview.NOTICE` in the page notice and every preview cell.
  - Baked sources (`PREVIEW_KINDS` `"bake"`): the source column draws `/api/jobs/<id>/source/<fid>.svf` with
    `drawLine`; `"draw"` kinds keep the PNG.
  - `maker/test/smoke_dom.py`: `main() -> int` - starts `server.make_server("127.0.0.1", 0, REPO, tmp)`, builds the
    module with `maker/build-wasm.sh` into the tree's ignored `maker/static/wasm/` when missing, uploads
    `ttf/neodgm/neodgm.ttf` + `LICENSE.txt`, selects it (precomposed, 16, bpp 1), runs, then up to 10 times 2 s
    apart runs `google-chrome` (else `chromium-browser`) `--headless=new --disable-gpu --dump-dom
    http://127.0.0.1:PORT/?job=ID` until the DOM holds `data-step="s01"` with `data-drawn="1"`, `data-ink` > 0 and no
    `data-error`; exit 0, 1 on timeout, 77 when no browser or emcc (skip).

- [ ] **Step 1: Write the failing tests** and rewrite the seven preview assertions in place (spec 6.5):

```python
# test_server.py
def test_page_wires_the_preview(self):
    js = read_text(MAKER_JS)
    self.assertIn('import * as svfview from "./svfview.js"', js)
    self.assertNotIn("preview.png", js)
    self.assertIn('"/face/"', js); self.assertIn('"/api/repo/face/dos/NEODG16.SVF"', js)
    self.assertIn('/static/wasm/svf.js', read_text(SVFVIEW_JS))
    if shutil.which("node"):
        for path in (MAKER_JS, SVFVIEW_JS):
            self.assertEqual(subprocess.run(["node", "--check", path]).returncode, 0)

# test_server.py:576-579 rewritten: test_step_previews_are_per_font -> test_the_step_png_route_is_gone
#   GET /api/jobs/<id>/preview/<font>/<step>.png -> 404 for the step's own font; the source PNG GET still 200
# test_jobs.py:268 the Step literal without "preview"; :309 and :566 -> self.assertNotIn("preview", step) and
#   quality.face_facts(read(output)) is not None; :333 and :371 -> self.assertNotIn("preview", step)
# test_zipout.py:78 the Step literal without "preview"
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_server.py' -k "wires_the_preview or step_png" -v`
  and `-p test_jobs.py`. Expected: FAIL (the import line is missing; steps still carry `preview`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_jobs.py`, `test_zipout.py`, `test_server.py`, `test_preview.py`. Expected: `OK`. Then
  `maker/build-wasm.sh && python3 maker/test/smoke_dom.py`. Expected: exit 0 (record the DOM line in the commit
  body). Exit 77 is acceptable only on a host without Chrome or emcc (not this one).
- [ ] **Step 5: Gates** G1, G2 (573 = 572 + 1; the 7 rewrites keep their test count), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: result faces drawn in the page by the WASM renderer; the worker no longer writes preview.png (t_9acea7ab)"`.

Cannot verify here: the page's interactive controls in a real browser beyond the DOM smoke run (playwright absent,
`web/test/check.mjs` exits 2). The reviewer opens the page by hand once (`SVF_MAKER_REPO=$PWD
SVF_MAKER_DATA=$(mktemp -d) SVF_MAKER_BIND=127.0.0.1:18766 python3 -P maker/server.py`) and records what was seen.

**Group 2 review gate.** Reviewer runs G1-G3, the whole `tools/test_web_picker.py` under `heavy`, and
`python3 maker/test/smoke_dom.py`; checks: `svfview.js` places by `walk_next`'s rules (one draw per code point, slot 0
only for the overrides, `S()` per term); no endpoint serves a file outside the job or `svf/`; every new GET carries
the host check; `preview.png` appears nowhere in `maker/` code but `preview.py`'s oracle helpers.

---

# Group 3: controls and clipping

Tasks 9, 10 and 11 run in sequence (all edit `settings.py`; 10 and 11 edit `server.py`).

### Task 9: the dy step and the named ranges (slice B2)

**Files:**
- Modify: `maker/settings.py` (`RANGE_FILES`, `range_spec`, the range type messages, `write_range_files`,
  `plan_steps`), `maker/routes.py` (`_mkfont_unicode`, `_bdfface_commands`'s list file choice),
  `maker/static/maker.js` (`rangeOptions`, a per-font dy table editor in the override panel), `maker/test/test_plan_inputs.py`,
  `maker/test/test_settings.py`

**Interfaces:**
- Consumes: Task 4 `dy` key and rules.
- Produces:
  - `RANGE_FILES = (("11172", "hangul"), ("2350", "ksx1001-hangul"), ("ksx1001-nohanja", "ksx1001-nohanja"),
    ("ksx1001-symbols", "ksx1001-symbols"), ("ksx1001", "ksx1001"), ("jamo", "jamo"), ("cp949", "cp949"))`;
    `NAMED_RANGE_NAMES = tuple(name for name, _ in RANGE_FILES)`; `write_range_files` writes all seven
    (`range-<name>.txt`); `range_spec` returns `(name, None)` for any of them.
  - Range messages become `"%s: range %s is not a named range (11172, 2350, ksx1001-nohanja, ksx1001-symbols,
    ksx1001, jamo, cp949) or a list file in the batch"` (and the `batch:` twin); existing assertions updated in place.
  - `routes._mkfont_unicode`: `11172` -> `ascii,hangul`, `2350` -> `ascii,ksx1001-hangul`, any other named range ->
    `"ascii," + name`; bdfface reads `range-<name>.txt` through `paths["range_file"]` as today.
  - `plan_steps`: for a `precomposed` step whose font has a non-empty effective `dy`, writes
    `work/sNN/dy.json` (`{"0x%X": n}` sorted by code point) and appends
    `PY + [tools/svfdy.py, <in>, <out>, "--json", <dy.json>]` to the step's argv list, with `<in>` = `<out>` when the
    route has commands, else the font's upload path token (the copy route; the worker's `_plain_token` rewrites a
    `.gz`).
  - `maker.js`: `rangeOptions` lists the seven names with labels; the override panel has a dy table (rows code point
    / char, int) written as `per.dy` (hex keys), shown only when `precomposed` is among the effective kinds.

- [ ] **Step 1: Write the failing tests** (`test_plan_inputs.py` class `DyStepTest`, `NamedRangeTest`; `run_batch`
  from `inputkinds`):

```python
def test_mkfont_step_ends_with_svfdy(self):
    step = self.plan(inputfx.ttf("D", BOX1), dy={"0x41": 1})[0]
    self.assertEqual([os.path.basename(a[2]) for a in step["argv"]], ["mkfont.py", "svfdy.py"])
    out = os.path.join(self.job_dir, step["output"])
    self.assertEqual(step["argv"][-1][3:], [out, out, "--json", os.path.join(self.job_dir, "work", step["id"], "dy.json")])
    self.assertEqual(json.load(open(os.path.join(self.job_dir, "work", step["id"], "dy.json"))), {"0x41": 1})

def test_copy_step_reads_the_upload(self):
    # an uploaded v3 precomposed SVF (NEODG16 copy), dy {"0x41": 1}: argv == [PY + [svfdy, <upload path>, <out>, "--json", <dy.json>]]

def test_dy_end_to_end(self):
    for files, kind in ((ttf_files, "mkfont"), (svf_files, "copy")):
        job, zip_path = inputkinds.run_batch(self, self.tmp(), files, choose_with_dy({"0x41": 1}))
        face = jamoset.parse_svfn(inputkinds.zip_face(zip_path))
        self.assertEqual(face.dy, {0x41: 1}); inputkinds.assert_facecheck(self, zip_path)

def test_dy_on_a_face_without_metrics_fails_with_the_tool_message(self):
    # upload: jamoset.pack_svfn(...) precomposed v3 with metrics=None; dy {"0x41": 1}: the step is "failed",
    # its stderr_tail holds svfdy's refusal, the job has no zip face for it

def test_seven_named_ranges(self):
    paths = settings.write_range_files(self.tmp())
    self.assertEqual(sorted(paths), sorted(settings.NAMED_RANGE_NAMES))
    for name, named in settings.RANGE_FILES:
        chars = read_text(paths[name]).replace("\n", "")
        self.assertEqual([ord(c) for c in chars], mkfont.NAMED_RANGES[named]())

def test_named_range_reaches_mkfont(self):
    step = self.plan(inputfx.ttf("D", BOX1), range="ksx1001-symbols")[0]
    self.assertEqual(step["argv"][0][step["argv"][0].index("--unicode") + 1], "ascii,ksx1001-symbols")

def test_width_and_latin_end_to_end(self):
    # mkfont on inputfx.ttf: options.mkfont.width 20 -> the face's cell_w 20; two bakes, latin True vs False, of a
    # Latin-only range differ in ascent (header byte 16)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_plan_inputs.py -k "DyStep or NamedRange" -v`.
  Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_plan_inputs.py`, `test_settings.py`, `test_routes.py`, `test_server.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (580 = 573 + 7), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: per-glyph dy through svfdy.py on precomposed faces, five more named ranges (t_9acea7ab)"`.

Cannot verify here: nothing.

### Task 10: the build's `--report`, the report endpoint, the step-row counts (slice C2, build side)

**Files:**
- Modify: `maker/settings.py` (`plan_steps`, `_step`), `maker/jobs.py` (`_clear_outputs`), `maker/server.py`
  (`_ROUTES`, `_job_report`), `maker/static/maker.js` (`reportText`, the step row), `maker/test/test_plan_inputs.py`,
  `maker/test/test_jobs.py`, `maker/test/test_zipout.py`, `maker/test/test_server.py`, `maker/test/test_routes.py`

**Interfaces:**
- Consumes: Task 2 `--report`.
- Produces:
  - `_step(...)` gains `"report": None`; `plan_steps` sets `step["report"] = "work/sNN/report.json"` for every step
    whose route label is `mkfont` and appends `--report <abs work/sNN/report.json>` to that step's mkfont argv (the
    route's command, before any svfdy argv).
  - `Worker._clear_outputs` also removes `cwd/report.json`.
  - `GET ^/api/jobs/JOB/report/(?P<step>s\d+)\.json$` -> `_job_report`: the step's `report` file when the step is
    `done`; 404 otherwise; `_serve_bytes`, `application/json`, host-checked.
  - `maker.js` `reportText(report) -> string`: clip `"cut N (T top, B bottom)"` (numbers with `toLocaleString("en")`),
    nudge `"nudged N"`, fit `"fit at S px"`; the step row shows it under the face facts.

- [ ] **Step 1: Write the failing tests:**

```python
# test_plan_inputs.py
def test_mkfont_argv_and_step_carry_the_report(self):
    step = self.plan(inputfx.ttf("R", BOX1))[0]
    self.assertEqual(step["report"], "work/%s/report.json" % step["id"])
    argv = step["argv"][0]
    self.assertEqual(argv[argv.index("--report") + 1], os.path.join(self.job_dir, step["report"]))

def test_fit_cell_report_mode_fit(self):
    job, _ = inputkinds.run_batch(self, self.tmp(), ttf_files, choose(options={"mkfont": {"cell": 12, "fit_cell": True}}))
    rep = json.load(open(self.store_path(job, job["steps"][0]["report"])))
    self.assertEqual(rep["mode"], "fit")

# test_jobs.py
def test_a_stale_report_is_removed_before_a_rerun(self):
    # a report.json left in work/s01/ and a tool that exits 1: the step fails and report.json is gone

# test_server.py
def test_report_endpoint(self):
    # done mkfont step: 200 application/json equal to the file; a jamo step, s99, a running step: 404; foreign Host: 403

def test_page_report_text(self):
    # node runs maker.js's reportText (extracted like offeredRoutes in the drift test) on the three modes:
    # "cut 2,300 (368 top, 2,299 bottom)", "nudged 3", "fit at 14 px"
```

  The Step literals at `test_jobs.py:268` and `test_zipout.py:78` gain `"report": None`; exact mkfont argv
  assertions in `test_routes.py`/`test_plan_inputs.py` that go through `plan_steps` gain the `--report` pair.

- [ ] **Step 2: Run** the new tests by name. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_plan_inputs.py`, `test_jobs.py`, `test_zipout.py`, `test_server.py`, `test_routes.py`.
  Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (585 = 580 + 5), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: mkfont steps write --report, served per step and summarised in the row (t_9acea7ab)"`.

Cannot verify here: nothing.

### Task 11: the clipping probe and the clipping panel (slice C2, probe side)

**Files:**
- Create: `maker/static/clip.js`, `maker/test/test_clip_math.mjs`, `maker/test/test_clip_math.py`
- Modify: `maker/settings.py` (`face_argv`, `probe_argv`), `maker/server.py` (`_ROUTES`, `_job_probe`),
  `maker/static/maker.js` (the "clipping" disclosure), `maker/test/test_server.py`, `maker/test/test_plan_inputs.py`

**Interfaces:**
- Consumes: Task 2 `--probe`, Task 6 `_serve_bytes` / preview lock / invalidation, Task 7 `drawGlyphs`.
- Produces:
  - `settings.face_argv(font, eff, route, kind, size, bpp, step_layout, range_arg, paths) -> list[list[str]]` - the
    step's commands exactly as `plan_steps` builds them (panel + preset merge, `--report`); `plan_steps` calls it.
  - `settings.probe_argv(mkfont_argv: list[str], src, out_svf, out_json, size) -> list[str]` - keeps
    `--unicode --latin --mono-hint --only-listed --space-advance --punct-extra --bpp --size` with their values, sets
    `--width` to the argv's `--width`, else its `--cell`, else `size`; drops `--cell --ascent --clip-cell --fit-cell
    --report`; adds `--probe --probe-cell <argv's --cell, else size>`, `--report out_json`; input/output = `src`,
    `out_svf`.
  - `GET ^/api/jobs/JOB/probe/(?P<font>f\d+)/(?P<size>\d+)/(?P<bpp>\d+)\.(?P<ext>svf|json)$` -> `_job_probe`: 404
    unless the font's precomposed route is `mkfont`, `size` is an effective size and `bpp` an effective bpp; under the
    font's preview lock, runs the probe once into `work/preview/<fid>/probe/<size>-<bpp>.{svf,json}` (`preview.ENV`,
    `preview.TIMEOUT_S`); `.svf` 404 when the JSON says `probe_face: false`; a failed probe is 404 with no file kept.
    The source is `_plain_source` here (Task 13 switches it to the prepared source). The `.json` response is the
    report with one key added, `"step_ascent"`: the merged argv's `--ascent` as an int, or null (the page's prefill).
  - `maker/static/clip.js` (pure ES module): `cutRows(box, ascent, cellH) -> {top, bottom}` with `top = max(0, -box[1]
    - ascent)`, `bottom = max(0, box[3] + ascent - cellH)`; `cutList(report, ascent, cellH, cellW) -> {rows:
    [{cp, top, bottom}], top, bottom, wide}` sorted by `top + bottom` descending then code point; `wide` = boxes with
    `right - left > cellW`.
  - `maker.js` clipping panel per outline font (spec 8.3): size select, bpp select, ascent (prefill: the probe
    JSON's `step_ascent`, else `auto_ascent`), cell height, the live count line, the
    overlay canvas (`drawGlyphs` of the probe face over sample text plus the 12 worst, cell rectangle stroked, cut rows
    tinted), the list capped at 200 with "and N more"; "Apply" writes `options.mkfont.ascent` and ticks `clip_cell`
    (unticks `fit_cell`). Without a probe face, list and counts only.

- [ ] **Step 1: Write the failing tests:**

```python
# test_server.py ProbeTest(ApiTest), job with inputkinds' tall TTF (the Task 2 fixture shape built by inputfx.tall_ttf())
def test_probe_bakes_once(self):
    r1 = self.raw("GET", "/api/jobs/%s/probe/f01/16/1.json" % jid); path = probe_json_path(jid)
    m1 = os.stat(path).st_mtime_ns; self.raw("GET", "/api/jobs/%s/probe/f01/16/1.json" % jid)
    self.assertEqual((r1.status, os.stat(path).st_mtime_ns), (200, m1))
    self.assertTrue(json.loads(r1.read())["probe"])

def test_probe_argv_is_derived_from_the_merged_step_argv(self):
    # settings.probe_argv on face_argv for preset dos-u-2bpp at size 17, bpp 2: --unicode is the preset's list,
    # --width 16, --probe-cell 16, no --clip-cell / --ascent / --cell; and with the plain preset and options width 20,
    # cell 18: --width 20 --probe-cell 18 --unicode ascii,ksx1001-hangul

def test_probe_face_draws_with_nothing_cut(self):
    # skip without emcc/node (TestModule's built_dist rule): the probe .svf through svfview.drawLineInto at 1/1 has
    # ink in its first and last rows only where the report's boxes reach them; fit_counts(boxes, w, cell_h, ascent) is empty

def test_keyed_put_drops_the_probe(self):
    # for width, then each other key of preview_inputs that changes a probe (cell, latin, mono_hint, space_advance,
    # range, preset, instance): PUT -> work/preview/f01/probe/ gone

def test_ascent_put_keeps_the_probe(self):
    # PUT changing options.mkfont.ascent, clip_cell, fit_cell: the probe files stay

def test_probe_without_face(self):
    # size 300 in the font's sizes: .json 200 with probe_face false, .svf 404

def test_probe_404s(self):
    # a DOS raw font, a size not selected, bpp 3, a foreign Host (403)

# test_plan_inputs.py
def test_face_argv_equals_plan_steps(self):
    # for mkfont, experimental fit, bdfface + from-svf fit: face_argv(...) == the planned step's argv

# test_clip_math.py ClipMathTest.test_node_clip_math: computes fit_counts in Python for ascents 6..16, cell 12, width
# 16 over the boxes of a probe report, writes cases JSON to a temp file, runs `node --test maker/test/test_clip_math.mjs`
# with CLIP_CASES=<file>; skip without node. The .mjs asserts cutList counts == the Python top/bottom/wide lengths and
# cutRows per glyph == max(0, ...) of the same boxes.
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_server.py' -k Probe -v`,
  `-p test_clip_math.py`, `-p test_plan_inputs.py -k face_argv`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_server.py`, `test_plan_inputs.py`, `test_clip_math.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (594 = 585 + 9), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: clipping probe from the step's own argv, cut rows shown for any ascent before the build (t_9acea7ab)"`.

Cannot verify here: the panel's interaction in a browser (only the math and the endpoints are tested); the reviewer
checks it by hand with the Group 2 server command.

**Group 3 review gate.** Reviewer runs G1-G3 and `python3 maker/test/smoke_dom.py`; checks: the probe argv is built
from `face_argv` (never from the options alone); the page's cut rule is `fit_counts`'s; `dy` reaches only precomposed
steps; the seven range files equal `mkfont.NAMED_RANGES`; no `--ascent 0` can be sent.

---

# Group 4: decomposable fonts, prepared sources, identity, closing

Tasks 12, 13, 14, 15 run in sequence.

### Task 12: `gsub_jamo`, the `mask fit` and `vector fit` routes (slice D1)

**Files:**
- Modify: `maker/detect.py` (`_sfnt_facts`, the label suffix), `maker/routes.py` (`_mask_fit_commands`,
  `_vector_prepare`, `_vector_commands`, `routes`), `maker/presets.py` (`panel_argv` rows of the two labels),
  `maker/settings.py` (`plan_steps` `paths["pylib"]`, `_route_errors`), `maker/jobs.py` (`_reference` with
  `jamo_route`), `maker/server.py` (`plan_steps(..., pylib=os.environ.get("JAMOSET_PYLIB"))` in `_job_run`),
  `maker/static/maker.js` (`ROUTES`, `OPTION_VISIBLE`, `offeredRoutes`, a per-font `jamo_route` select, the "minutes
  per font" note on `vector fit`), `maker/test/test_detect_inputs.py`, `maker/test/test_routes.py`,
  `maker/test/test_plan_inputs.py`, `maker/test/test_real_inputs.py`, `maker/test/test_server.py`
  (`canonical_fonts`), `maker/test/inputfx.py`

**Interfaces:**
- Consumes: Task 4 `route_for(..., jamo_route)`, Task 5 per-command extras, Task 6 `mask_ok` stamping.
- Produces:
  - Entry fact `gsub_jamo: True` (only when present) when the `GSUB` FeatureList has `ljmo`, `vjmo` and `tjmo`;
    label suffix `"; conjoining jamo (GSUB)"`.
  - `Route("jamo", "mask fit", False, ["844", "adaptive"], [1], None, "outline", None, _mask_fit_commands)`, offered
    when `gsub_jamo and mask_ok`; argv `PY + [jamoset.py, "--layout", L, "--from-ttf", SRC, "--size", S,
    "--binarize", "threshold", "--mask-font", SRC, "--no-clean", "--check", "-o", OUT]` + `["--pylib", DIR]` when
    `paths.get("pylib")`.
  - `Route("jamo", "vector fit", False, ["844", "adaptive"], [1, 2], None, "outline", _vector_prepare,
    _vector_commands)`: prepare `jamovec.py master SRC -o master.json [--adaptive]`; render exactly
    `_composite_commands` (`--binarize threshold --check`).
  - Page order: `outline`: mkfont, experimental fit, mask fit, vector fit; `outline-composite`: mkfont, composite,
    mask fit, vector fit. `ROUTES` in `maker.js` lists them; `offeredRoutes` drops `mask fit` unless
    `font.gsub_jamo && font.mask_ok`.
  - `panel_argv`: `mask fit` bpp 1 `--jset-version`, `--baseline`, `--binarize X` (no `--no-clean`: the command
    carries it); `vector fit` `--symbols`, `--jset-version`, `--baseline`, `--binarize X` (bpp 1). `OPTION_VISIBLE`
    gains spec 7.3's two rows. `binarize mono` on `vector fit` -> `"%s: binarize mono is not a jamovec choice"`.
  - `_route_errors`: `"%s: mask fit needs freetype-py and uharfbuzz (JAMOSET_PYLIB)"` when `jamo_route == "mask fit"`
    and the entry lacks `mask_ok`.
  - `canonical_fonts()` gains outline and outline-composite entries with `gsub_jamo: True` and `mask_ok` True and
    False.
  - `inputfx.flat_composite_ttf() -> bytes` - `fixtures._composite_ttf`'s font with every composite glyph replaced
    by its decomposed outline (`DecomposingRecordingPen` -> `TTGlyphPen`), so detect calls it `outline`.
  - `inputfx.gsub_jamo_ttf(features=("ljmo", "vjmo", "tjmo")) -> bytes` - `inputfx.ttf` plus a GSUB with those
    features (single substitutions built with `fontTools.otlLib.builder`).

- [ ] **Step 1: Write the failing tests:**

```python
# test_detect_inputs.py
def test_gsub_jamo_fact(self):
    e = detect.detect_file(self.put("G.ttf", inputfx.gsub_jamo_ttf()), "G.ttf")[0]
    self.assertTrue(e["gsub_jamo"]); self.assertTrue(e["label"].endswith("; conjoining jamo (GSUB)"))
    e = detect.detect_file(self.put("L.ttf", inputfx.gsub_jamo_ttf(("ljmo",))), "L.ttf")[0]
    self.assertNotIn("gsub_jamo", e)

# test_routes.py DecomposableRoutesTest
def test_mask_fit_offered_only_with_both(self):
    labels = lambda f: [r.label for r in routes.routes(f) if r.kind == "jamo"]
    self.assertEqual(labels(dict(OUTLINE, gsub_jamo=True, mask_ok=True)), ["experimental fit", "mask fit", "vector fit"])
    self.assertEqual(labels(dict(OUTLINE, gsub_jamo=True, mask_ok=False)), ["experimental fit", "vector fit"])
    self.assertEqual(labels(dict(OUTLINE_COMPOSITE, gsub_jamo=True, mask_ok=True)), ["composite", "mask fit", "vector fit"])

def test_mask_fit_argv(self):
    r = routes.route_for(dict(OUTLINE, gsub_jamo=True, mask_ok=True), "jamo", True, "mask fit")
    self.assertEqual(r.bpps, [1])
    argv = r.commands(OUTLINE, 16, 1, "844", ("2350", None), P, [])[0]
    self.assertEqual(argv[argv.index("--mask-font") + 1], "/u/in.ttf"); self.assertIn("--no-clean", argv)
    self.assertNotIn("--pylib", argv)
    argv = r.commands(OUTLINE, 16, 1, "844", ("2350", None), dict(P, pylib="/opt/py"), [])[0]
    self.assertEqual(argv[-2:], ["--pylib", "/opt/py"])

def test_vector_fit_argv(self):
    r = routes.route_for(OUTLINE, "jamo", True, "vector fit")
    self.assertEqual(r.prepare_commands(OUTLINE, "844", P), [PY + ["/T/jamovec.py", "master", "/u/in.ttf", "-o", "/w/master.json"]])
    self.assertEqual(r.commands(OUTLINE, 16, 2, "844", ("2350", None), P, [])[0][-5:],
                     ["--binarize", "threshold", "--check", "-o", P["out"]])

def test_saved_mask_route_without_libs_is_refused(self):
    # entry gsub_jamo True, mask_ok False, settings jamo_route "mask fit", experimental: validate contains
    # "f01: mask fit needs freetype-py and uharfbuzz (JAMOSET_PYLIB)"; through the server (caps mask_libs False)
    # POST run -> 409/400 with that reason

def test_reference_uses_jamo_route(self):
    # jobs.Worker._reference for a jamo step of an outline font with jamo_route "vector fit" -> "outline"

# test_plan_inputs.py
def test_vector_fit_end_to_end(self):
    job, zip_path = inputkinds.run_batch(self, self.tmp(), {"v/F.ttf": inputfx.flat_composite_ttf()},
                                         choose(kinds=["jamo"], experimental=True, jamo_route="vector fit", layout="844"))
    self.assertEqual(job["state"], "done"); inputkinds.assert_facecheck(self, zip_path)
    self.assertIsNotNone([s for s in job["steps"] if s["kind"] == "jamo"][0]["quality"])

# test_real_inputs.py
@unittest.skipUnless(jamofit.libs_available(os.environ.get("JAMOSET_PYLIB")), "freetype-py/uharfbuzz absent")
def test_mask_fit(self): ...    # neodgm; argv holds --mask-font and --no-clean; stderr lacks "fitting without the
                                # mask font"; the face differs from the experimental fit at the same size
@unittest.skipUnless(os.environ.get("SVF_MAKER_REAL_VECTOR"), "set SVF_MAKER_REAL_VECTOR to a TTF")
def test_real_vector(self): ... # records the seconds in the test output
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_routes.py -k Decomposable -v` and
  `-p test_detect_inputs.py -k gsub`. Expected: FAIL.
- [ ] **Step 3: Implement** in one commit, with the `maker.js` rows and the drift fixtures.
- [ ] **Step 4: Run** `test_routes.py`, `test_detect_inputs.py`, `test_plan_inputs.py`, `test_server.py`,
  `test_real_inputs.py`. Expected: `OK` (the two real tests skip).
- [ ] **Step 5: Gates** G1, G2 (603 = 594 + 9; the two real-input tests count as skips), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: mask fit and vector fit jamo routes for decomposable outline fonts (t_9acea7ab)"`. If
  `SVF_MAKER_REAL_VECTOR` was run, the seconds go in the commit body.

Cannot verify here: a mask fit run (freetype-py, uharfbuzz absent; `test_mask_fit` skips) and the real-font vector-fit
time (unknown; ruling D7). If `test_vector_fit_end_to_end` shows `jamovec.py master` without `--components` cannot fit
a 2-syllable font, stop and report (the route stays out until the owner decides; see the open points).

### Task 13: source previews of the prepared font (slice E)

**Files:**
- Modify: `maker/srcprep.py` (`prepared_bytes` `instance` op), `maker/settings.py` (`source_ops`, `plan_steps` uses
  it), `maker/server.py` (`_prepared_source`, `_make_source_preview` reads it, `_job_probe` reads it),
  `maker/test/test_srcprep.py`, `maker/test/test_server.py`, `maker/test/test_plan_inputs.py`

**Interfaces:**
- Produces:
  - `srcprep.prepared_bytes(data, [..., {"op": "instance", "coords": {tag: n}}])` - `instantiateVariableFont(TTFont,
    coords, inplace=False)` saved to bytes (the `PrepError` for `instance` is gone).
  - `settings.source_ops(font, eff) -> list[dict]` - `font["prep"]` plus the planned `ttc-face` (face 0 of a TTC with
    an instance) and `instance` ops, exactly today's inline list in `plan_steps`, which now calls it.
  - `server.Handler._prepared_source(job, job_dir, font) -> str` - with no ops, `_plain_source(...)`; else
    `work/preview/<fid>/source.<ext>` (`bdf` after `pcf-bdf`, `otf` for a CFF entry, else `ttf`) written once under
    the font's preview lock from `prepared_bytes(plain bytes, ops)`. `_make_source_preview` replaces its
    `_plain_source` call with it and passes `dict(font, face_index=0)` to `preview.source_png` when ops exist. **No
    `source_kind` literal is added to `_make_source_preview`** (the drift test reads its source).

- [ ] **Step 1: Write the failing tests:**

```python
# test_srcprep.py
def test_prepared_bytes_instance_op(self):
    out = TTFont(io.BytesIO(srcprep.prepared_bytes(inputfx.variable_ttf(), [{"op": "instance", "coords": {"wght": 700}}])))
    self.assertNotIn("fvar", out)

# test_server.py
def test_source_preview_draws_the_prepared_font(self):
    # job with inputfx.variable_ttf(): source PNG with instance None, then PUT instance {"wght": 900}: the PNG bytes
    # differ (the gvar delta moves ga); work/preview/<fid>/source.ttf exists; PUT instance None -> that file is gone.
    # job with inputfx.mac_cmap_ttf(): the source PNG GET is 200 (404 before this task)

# test_plan_inputs.py
def test_source_ops_shared_with_plan_steps(self):
    # for a TTC face 0 with an instance and a Mac-cmap font: plan_steps' source step argv == routes.source_commands(settings.source_ops(...))
```

- [ ] **Step 2: Run** the three by name. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_srcprep.py`, `test_server.py` (the drift test included), `test_plan_inputs.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (606 = 603 + 3), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: source previews and probes read the prepared font (instance, Mac cmap, TTC face) (t_9acea7ab)"`.

Cannot verify here: nothing.

### Task 14: the identity check in the worker, its endpoint and the pieces panel (slice D2, second half)

**Files:**
- Modify: `maker/jobs.py` (`run_command` `env` parameter, `_run_step`, `_read_back(..., cancel)`, `RECOG_TIMEOUT`),
  `maker/settings.py` (`_step` gains `"identity": None`), `maker/server.py` (`_ROUTES`, `_job_identity`),
  `maker/zipout.py` (`log_step` identity line), `maker/static/maker.js` (pieces panel), `maker/test/test_jobs.py`,
  `maker/test/test_zipout.py`, `maker/test/test_server.py`

**Interfaces:**
- Consumes: Task 3 CLI, Task 6 `worker.caps` and `caps.recog_dir`, Task 7 `pieces`/`drawPiece`/`glyphCell`.
- Produces:
  - `jobs.run_command(argv, cwd, timeout, cancel, env=None)` - `None` = `ENV` (unchanged for every other caller).
  - `jobs.RECOG_TIMEOUT = 180`; `Worker._identity(job_dir, step, cancel) -> dict` - only for `jamo` steps when
    `self.caps["recog"]`: runs `PY + [maker/recog_score.py, <out>, "-o", <work/sNN/identity.json>, "--threads", "2"]`
    in `work/sNN/identity/` with `dict(ENV, SVF_RECOG_DIR=caps.recog_dir(os.environ))` and `RECOG_TIMEOUT`; returns
    the JSON's `face` (plus `available: true`), or `{"available": false, "error": "<stderr tail or 'timed out'>"}`;
    without caps `{"available": false, "structural": "<the 'check:' line of the step's stdout or ''>"}`. Never fails
    the step. `step["identity"]` holds the result.
  - `GET ^/api/jobs/JOB/identity/(?P<step>s\d+)\.json$` -> `_job_identity`: `work/sNN/identity.json` of a done step,
    else 404; host-checked.
  - `zipout.log_step` adds one line for a jamo step: `identity: pass, 344 pieces, 2 warn, 0 fail, ks 0.97`, or
    `identity check unavailable`, or `identity: error <text>`.
  - `maker.js` pieces panel under a jamo step's preview (spec 9.5); the unavailable text exactly
    `"identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; numpy and torch needed)"`.

- [ ] **Step 1: Write the failing tests** (`test_jobs.py`; the stub `recog.py` from Task 3's test module is reused via
  a helper `test_recog_score.write_stub(dir, bad=..., sleep=0)`; the DOS raw fixture job):

```python
def test_identity_written_for_jamo_steps(self):
    with stub_recog() as d, mock.patch.dict(os.environ, {"SVF_RECOG_DIR": d}), mock.patch.object(caps, "recog_dir", return_value=d):
        worker.caps = {"wasm": False, "mask_libs": False, "recog": True}
        j = run(job_with_dos_raw_jamo_step)
    step = j["steps"][0]
    self.assertEqual(step["identity"]["identity"], "pass")
    self.assertTrue(os.path.isfile(self.store.path(j["id"], "work", step["id"], "identity.json")))
    self.assertIn("identity: pass", read_text(self.store.path(j["id"], "log.md")))

def test_identity_timeout_keeps_the_step_done(self):
    # stub sleeps 5 s, jobs.RECOG_TIMEOUT patched to 1: step "done", identity {"available": false, "error": ... "timed out"}

def test_identity_unavailable_without_recog(self):
    # caps recog False: no identity.json, step["identity"]["available"] is False, log line "identity check unavailable"

# test_server.py
def test_identity_endpoint(self):
    # identity.json written into a done jamo step's dir: 200 application/json; a precomposed step and s99: 404; foreign Host 403

def test_page_pieces_panel(self):
    js = read_text(MAKER_JS)
    self.assertIn("identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; numpy and torch needed)", js)
    self.assertIn('"/identity/"', js); self.assertIn("svfview.drawPiece", js)
```

  The Step literals at `test_jobs.py:268` and `test_zipout.py:78` gain `"identity": None`.

- [ ] **Step 2: Run** the new tests by name. Expected: FAIL.
- [ ] **Step 3: Implement**, `cancel` plumbed from `_run_step` into `_read_back` and `_identity`.
- [ ] **Step 4: Run** `test_jobs.py`, `test_zipout.py`, `test_server.py`, `test_recog_score.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (611 = 606 + 5), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: optional piece identity check per jamo step, served and shown with the pieces (t_9acea7ab)"`.

Cannot verify here: a real recogniser (none on this host, none may be added); the stub pins the CLI and the worker
path only.

### Task 15: closing gates and documents (slice F)

**Files:**
- Create: `maker/README.md`
- Modify: `docs/maker-audit.md` (section 3 and section 7 gap items 1-4 rewritten to the new state; rows cite symbol
  names, not line numbers)

**Interfaces:** none produced.

- [ ] **Step 1: Write** `maker/README.md`: what the maker is (two lines), how to run it (`python3 -P maker/server.py`
  with `SVF_MAKER_REPO`, `SVF_MAKER_DATA`, `SVF_MAKER_BIND`), `maker/build-wasm.sh` (needs emsdk; without it the page
  says "preview module not built"), the optional environment (`JAMOSET_PYLIB` for mask fit and binarize mono,
  `SVF_RECOG_DIR` for the identity check, with "scoring only; no weights in this repository"), how to run the tests
  (G2 command, `tools/test_web_picker.py`, `maker/test/smoke_dom.py`).
- [ ] **Step 2: Rewrite** `docs/maker-audit.md` section 3 (the preview is the WASM module; the endpoints; what stays
  PNG: FreeType-readable sources, and the server-side PNG of baked sources kept for its tests) and the gap list items
  1-4 (done, with the task that closed each).
- [ ] **Step 3: Run the closing gates:** G1; G2 (expected 611); G3; `~/.local/bin/heavy make -C c check`;
  `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py` (TestPage skips);
  `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_*.py'`; `python3 maker/test/smoke_dom.py`;
  `git diff --stat 01a943f -- c/src c/include` (empty). Record each result in the commit body.
- [ ] **Step 4: Commit** `git add maker/README.md docs/maker-audit.md && git commit -m "docs: maker README with the module build; audit section 3 and gaps 1-4 closed (t_9acea7ab)"`.

**Group 4 review gate.** Reviewer runs the Task 15 Step 3 list and checks against the card's closing measurement:
UI exposes size/bpp/baseline/clip and the jamo-set mode (`jamo_route`) - Tasks 4, 5, 11, 12; the preview is drawn in
the browser by the C renderer built to WASM and matches `tools/svfline.py` byte for byte on the test set - Tasks 1, 7
(`TestModule`), Task 8 smoke; clipped rows visible before the build - Task 11; tests cover each option - Tasks 4, 5,
9, 10; a decomposable OFL font yields a jamo-set face - Task 12 (`test_vector_fit_end_to_end`; the mask route on
neodgm where the libraries exist); the piece identity check is optional (`SVF_RECOG_DIR`) - Tasks 3, 14.

---

## Review groups

| Group | Tasks | Order and parallelism | Review |
|---|---|---|---|
| 1 foundations | 1, 2, 3, 4, 5 | 1, 2, 3 in parallel with each other and with 4 (disjoint files); 5 after 4 | one review after 5 |
| 2 browser preview | 6, 7, 8 | 6 and 7 in parallel (7 touches only `svfview.js`, `test_svfview.py`, `tools/test_web_picker.py`); 8 after both | one review after 8 |
| 3 controls and clipping | 9, 10, 11 | sequential (`settings.py`, `server.py`) | one review after 11 |
| 4 decomposable, sources, identity, closing | 12, 13, 14, 15 | sequential (`routes.py`/`settings.py`/`server.py`/`jobs.py`) | one review after 15 |

This is the spec's order (section 12: A1 and C1 alongside B1; then A2; then A3; then B2; then C2, D1, E; then D2;
then F) with D2's standalone CLI moved forward (Task 3, new files only) and E placed after C2 and D1 as the spec
orders.

## Open points for the user

1. **Baked-source PNGs.** The spec keeps "the source-PNG tests", but for DOS raw and SVF sources that PNG is drawn by
   `svfline` (`_render_preview`). The plan has the page draw those sources with WASM from `/source/<fid>.svf` and
   leaves the server-side PNG (unused by the page) in place so those tests stay. Say if the server should stop drawing
   it (then the source-PNG tests for baked kinds are rewritten).
2. **Slice splits.** B1, A3, C2 and D2 are each two tasks (two independent test cycles); D1 stays one task (the spec
   requires one commit). Fifteen tasks in four review groups.
3. **Compositor test harness.** The spec names a `glyphs` spec in `web/test/render.mjs`; the plan drives `svfview.js`
   through `TestModule.run_script` instead and leaves `render.mjs` as the picker's oracle. Same assertions.
4. **Plan-level choices the spec left open:** `--binarize` is emitted only when not `threshold` (no argv change for a
   default panel); `--mask-font none` at 1 bpp only (`main_aa` never reads it); extras align with the last commands;
   the report's `counts` gains `cut` (the union) for the row text; a LIST/JMAP face gets
   `{"applicable": false, "reason": "not applicable (LIST)"}`; dy bound messages and the `jamo_route` "not a route
   label" type message are this plan's wording.
5. **The `--fit-cell` "mode is fit" assertion** (spec 11, B fit/width/latin row) moves from the dy slice to Task 10,
   because the build writes `--report` only from Task 10.
6. **Vector fit on the 2-syllable flattened fixture is unverified.** If `jamovec.py master` without `--components`
   cannot separate it, Task 12 stops and reports; the route then needs a larger synthetic fixture or an OFL font run
   (neodgm is composite, so it already takes `composite`).
