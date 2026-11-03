# WASM Font Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static page under `web/` that renders every face in `svf/` through the C renderer built to WebAssembly, with a
Latin + Hangul face chain, scale ratio, sample presets, GRAY8 / MONO / RGB565 previews, per-face licence text, and a JSON
export of picker choices in the `scummvm-ko-font-pairing/1` shape `tools/pairing2svf.py` reads. Card t_fe9f6c30; close:
the page renders every face and a Playwright check screenshots three faces and the export.

**Architecture:** `c/ports/web/svf_web.c` (the existing emscripten glue) gains reset / info / has / any-target functions
and a growing scratch; `web/build.sh` compiles it with the pinned emsdk, runs `web/mkindex.py` (faces.json from
`jamoset.parse_svfn` + `web/LICENCES.tsv`) and copies faces and licences into `web/dist/` (not committed). `web/picker.js`
is one ES module that exposes `window.picker`; the UI and the Playwright check (`web/test/check.mjs`) both call it. Tests
live in `tools/test_web_picker.py` under the existing unittest gate: index checks (always), node byte-identity against
`tools/svfline.py` (needs emsdk + node), the Playwright run (needs `web/test/node_modules` + a Chrome); each class skips
with a message when its tool is missing.

**Tech Stack:** C99 glue (emcc 6.0.13 from `~/opt/emsdk`, `c/cross/install-toolchains.sh`); plain HTML/CSS/ES2022, no
framework, no CDN; Python 3 unittest (`tools/jamoset.py`, `tools/svfline.py` as references); node 24
(`~/opt/node-v24.13.0-linux-x64/bin/node`); `playwright-core` 1.62.1 driving Google Chrome 152 (`channel: "chrome"`).

**Spec:** `docs/superpowers/specs/2026-10-20-wasm-picker-design.md` (read it first). Glue and API:
`c/ports/web/svf_web.c`, `c/ports/web/README.md`, `c/include/svf.h`. Export consumer: `tools/pairing2svf.py` (`main`,
`make_map`, `TEMPLATES`). Earlier UX notes: `research/jamo-studio/brief.md` (presets, scale, variant selector).

## Global Constraints

- No change to `c/src/` or `c/include/svf.h`; the no-malloc gate (`make -C c check`) stays green; `c/cross/build-all.sh
  --ports` still builds `web` from the same `svf_web.c` (the five existing exports keep their signatures).
- `web/` holds no server-side code and loads nothing from outside its own directory at run time; `index.html` has no
  inline script, `picker.js` is the only module, `svf.js` the only generated script.
- Generated files are never committed: `web/dist/`, `web/test/node_modules/`, `web/test/out/` are in `.gitignore`.
  Committed sources under `web/` stay under 400 KB in total with the tests, and the page sources (`index.html`,
  `picker.js`, `style.css`, `mkindex.py`) under 150 KB (amended in Task 5 fix round 1; now measured 344,846 B with tests and 109,796 B page sources at the final fix, the face-selection redesign having grown both; the two limits stay as they were ruled).
- `build.sh` and the tests write only under the OUT directory they are given (default `web/dist`, `web/test/out`).
- Pixels are the renderer's: JS never draws text, only converts a GRAY8 / MONO / RGB565 buffer to canvas pixels. Any
  rendering test compares bytes with `tools/svfline.py`, never with a stored golden image.
- Every face shown has its licence text reachable from the page; `mkindex.py` fails on a face without a licence row.
- Export: `format` is exactly `scummvm-ko-font-pairing/1`; `korean.key` is the repository path of the Hangul face.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. The scratch growth in the glue: a scale that needs more than the current buffer must get a buffer of exactly
   `svf_chain_scratch_bytes` or more before `svf_draw_utf8` runs, and a failed `malloc` must return `SVF_E_NOMEM`, not
   draw with the old buffer — Task 2 `test_scratch_grows_for_gbatb47_16x`.
2. Face memory handed to the module stays valid while a slot uses it: the page never frees a face pointer that is open
   in a slot, and `svfw_reset` before freeing — Task 3 reviews `picker.js` `select()` for the free-after-reset order.
3. The licence mapping cannot silently drop a face: a new file under `svf/` with no `LICENCES.tsv` row fails the build
   (Task 1 `test_unmapped_face_fails`), and the page shows every licence file of a face, not the first.
4. The export must be readable by `pairing2svf.main` without edits: the Task 5 test feeds the exported file through the
   same expressions `main` uses (`format`, `games[].game`, `fonts[].korean.key`, `picked`, `lineh`).
5. Playwright runs headless against a browser newer than its bundled revision (Chrome 152 vs Chromium 151): the check
   records the browser version it used in `browser.txt` and fails clearly (not hangs) when no browser launches — Task 3
   `test_page_reports_browser`.

---

## File structure

```
c/ports/web/svf_web.c          existing glue + svfw_reset, svfw_info, svfw_has, svfw_target2, growing scratch (Task 2)
c/ports/web/README.md          the new exports documented (Task 2)
web/LICENCES.tsv               face glob -> licence files, relative to svf/ (Task 1)
web/mkindex.py                 writes faces.json from svf/ + LICENCES.tsv; exit 2 on an unmapped face (Task 1)
web/build.sh                   emcc build + mkindex + copies into OUT (Task 2)
web/index.html, web/style.css  the page (Task 3, 4, 5)
web/picker.js                  the module: window.picker + the UI bindings (Task 3, 4, 5)
web/test/render.mjs            node: draw a chain/text/scale/target to stdout (Task 2)
web/test/serve.mjs             node: static server for a directory on 127.0.0.1:0 (Task 3)
web/test/check.mjs             node + playwright-core: the page check, artifacts in OUT (Task 3, 4, 5)
web/test/package.json          playwright-core 1.62.1 pinned (Task 3)
web/README.md                  build, serve, test, export notes (Task 6)
tools/test_web_picker.py       TestIndex, TestModule, TestPage (Tasks 1-5)
```

`tools/test_web_picker.py` finds tools at `EMSDK` (default `~/opt/emsdk`), `NODE` (default
`~/opt/node-v24.13.0-linux-x64/bin/node`, then `node` on PATH) and `web/test/node_modules/playwright-core`; it builds
with `web/build.sh` into a temp dir once per run (`TestModule`, `TestPage`), and skips a class with a one-line reason.

---

### Task 1: Face index and licence table

**Files:** Create `web/LICENCES.tsv`, `web/mkindex.py`, `tools/test_web_picker.py`; modify `.gitignore`.

**Interfaces — Produces:**
```
mkindex.py SVF_DIR OUT_JSON [--check]     writes faces.json (svf-fonts-web-index/1); exit 2 naming the first face no
                                          LICENCES.tsv row covers or whose licence file is missing; --check writes nothing
LICENCES.tsv: glob<TAB>licence[,licence]  globs relative to SVF_DIR (fnmatch, case-sensitive), licences relative to it
faces.json entry: key, url, group, label, cell [w,h], px, bpp, ascent, glyphs, jamo, flags, bytes, licences [urls]
```
`label`: jamo-extra from FACES.TSV `family` + ` {px} px` (+ ` AA` at 2 bpp); dos/iolo/games from the first licence note's
first line without its parenthesis + ` {px} px`; otherwise the stem. Rows for `svf/dos` follow the notes' first lines
(`GBATB*.SVF,GBA*X?.SVF` -> `dos/GOWUNBAT.TXT,dos/OFLGOWUN.TXT`, `PAPLG1?.SVF` -> `dos/PAPLG.TXT,dos/OFLPAPLG.TXT`,
`PAPER*,PAPLB*` -> `dos/PAPMARU.TXT,dos/OFLPAPLG.TXT`, `MARU*` -> `dos/PAPMARU.TXT,dos/OFLMARU.TXT`, `NSQR*` ->
`dos/OFLNSQR.TXT`, `BHSAN28` -> `dos/OFLBHS.TXT`, `COUSB24` -> `dos/OFLCOUS.TXT`, `GOTHB18A` -> `dos/OFLGOTHA.TXT`,
`NEODG*,NEO*X?` -> `dos/NEODGM.TXT,dos/OFL.TXT`, `NGOT*,NGO*X?` -> `dos/NANUMGOT.TXT,dos/OFLNANUM.TXT`, and one row each
for the single-face notes), `jamo-extra/*` from FACES.TSV column `licence`, `iolo/*` ->
`iolo/IOLO.TXT,iolo/LICENSE-MIT.txt,iolo/LICENSE-OFL.txt`, `games/lb1/DKBHG40.SVF` -> `dos/DKBHG.TXT`.

- [ ] **Step 1: Failing tests** `tools/test_web_picker.py::TestIndex`: `test_lists_every_face` (the set of `key` equals
  every `svf/**/*.SVF|svf` relative path, 153 today, and `len(faces) == 153`), `test_header_fields_match_jamoset` (for
  every entry: `cell`, `bpp`, `ascent`, `glyphs`, `flags`, `jamo` equal `parse_svfn` + `unpack` on the file; `bytes` the
  file size), `test_every_licence_exists` (every `licences` url resolves under `svf/` and no entry has an empty list),
  `test_unmapped_face_fails` (a temp copy of `svf/iolo` plus a `ZZZ.SVF` copied from `HGKEY6J.SVF`: exit 2 and the
  name `ZZZ.SVF` in stderr), `test_label_examples` (`svf/dos/PAPLG18.SVF` -> `Paperlogy faces 18 px`,
  `svf/jamo-extra/GOTHA16A.SVF` -> `Gothic A1 Regular 2.50 (HanYang I&C) 16 px AA`).
- [ ] **Step 2: Run** `python3 -m unittest tools.test_web_picker -k TestIndex` → FAIL (no `web/mkindex.py`).
- [ ] **Step 3: Implement** `web/LICENCES.tsv`, `web/mkindex.py` (imports `tools/jamoset.py` by path; stdlib only);
  add `web/dist/`, `web/test/node_modules/`, `web/test/out/` to `.gitignore`.
- [ ] **Step 4: Run** → PASS (5 tests); `python3 web/mkindex.py svf /tmp/faces.json` prints `153 faces, 0 unmapped`.
- [ ] **Step 5: Commit** `web: face index generator and the face-to-licence table (153 faces, every one with a licence)`.

### Task 2: Glue extensions, build script, node byte-identity against svfline

**Files:** Modify `c/ports/web/svf_web.c`, `c/ports/web/README.md`; create `web/build.sh`, `web/test/render.mjs`;
modify `tools/test_web_picker.py`.

**Interfaces — Consumes:** `svf.h` (unchanged), Task 1. **Produces:**
```c
EMSCRIPTEN_KEEPALIVE int svfw_reset(void);                       /* closes every slot: chain count 0; SVF_OK */
EMSCRIPTEN_KEEPALIVE int svfw_info(int slot, int32_t out[8]);   /* bpp, cell_w, cell_h, ascent, flags, status, glyphs, is_jamo; SVF_E_ARG for an unopened slot */
EMSCRIPTEN_KEEPALIVE int svfw_has(int slot, uint32_t cp);       /* svf_has; 0 for an unopened slot */
EMSCRIPTEN_KEEPALIVE int svfw_target2(int kind, uint8_t *buf, uint32_t buf_len, int w, int h, int stride,
                                      int fg565, int bg565, int threshold, int flags);  /* kinds 0..3; SVF_T_COVERAGE_CB is SVF_E_ARG */
/* svfw_draw: before drawing, if svf_chain_scratch_bytes(&chain) > the current scratch, malloc a new one (free the old);
 * a failed malloc returns SVF_E_NOMEM and leaves the old buffer. The static 64 KB stays the first buffer. */
```
```
render.mjs MODULE_DIR SPEC_JSON     SPEC: {faces: [paths], text, scale: [n, d], kind: "gray8"|"mono_row"|"rgb565",
                                    w, h, x, baseline, fg565, bg565, threshold}; writes the buffer bytes to stdout;
                                    exit 3 with the svf_err name on a failed call
build.sh [OUT]                      OUT default web/dist; EMSDK default ~/opt/emsdk; -sENVIRONMENT=web,node;
                                    prints "svf.wasm N bytes, svf.js N bytes, 153 faces, N MB copied"
```

- [ ] **Step 1: Failing tests** `TestModule` (skip without `$EMSDK/upstream/emscripten/emcc` or node):
  `test_gray8_matches_svfline` (chains `[PAPLG16, PAPLG18]` at 1/1, 2/1, 3/2 with text
  `Web: 다람쥐 헌 쳇바퀴에 타고파!`, `[HGKEY6J]` at 1/1 and 3/1 with `삶닭값읊핥`, `[GOTHA24A]` at 1/1 with `국궉귁개객게각`,
  `[GBATB47]` at 1/2 with `뛔횰쓿긹`: `assertEqual(render(...), svfline.layout(...))` on a `measure.width + 4` by
  `ascent + descent + 2` buffer, baseline `ascent + 1`), `test_mono_row_matches_svfline` (the PAPLG chain at 2/1 with
  thresholds 128 and 1 against `svfline.to_target(gray, Target(mono_row, ...))`), `test_rgb565_matches_svfline` (fg
  0xFFFF/bg 0x0000 and fg 0xF800/bg 0x07E0, both byte orders), `test_scratch_grows_for_gbatb47_16x` (`[GBATB47]` at
  16/1 draws `가` with err 0 and the bytes equal svfline; a 1/1 draw afterwards still matches), `test_reset_and_info`
  (open PAPLG16 in slot 0, `svfw_info` gives `[2, 18, 18, 14, flags, status, 149, 0]` per `parse_svfn`; after
  `svfw_reset` a draw returns `SVF_E_ARG` (a chain without faces) and `svfw_has(0, 0x41)` is 0), `test_build_all_ports_web`
  (`c/cross/build-all.sh --ports` output still has `port-web: OK`; skipped when the other toolchains are absent, so it
  runs the web case alone through the same emcc line).
- [ ] **Step 2: Run** `python3 -m unittest tools.test_web_picker -k TestModule` → FAIL (no `web/build.sh`).
- [ ] **Step 3: Implement** the four functions and the scratch growth in `svf_web.c` (`<stdlib.h>` allowed there),
  `web/build.sh`, `web/test/render.mjs`; document the exports and the scratch rule in `c/ports/web/README.md`.
- [ ] **Step 4: Run** → PASS; `make -C c check` → `no-malloc: OK` (unchanged objects).
- [ ] **Step 5: Commit** `web: build script and glue extensions (reset, info, has, every buffer target); node draw equals svfline`.

### Task 3: The page: face list, lazy loading, preview; Playwright harness over every face

**Files:** Create `web/index.html`, `web/style.css`, `web/picker.js`, `web/test/serve.mjs`, `web/test/check.mjs`,
`web/test/package.json`; modify `tools/test_web_picker.py`.

**Interfaces — Consumes:** Tasks 1-2. **Produces (`window.picker`, all async where they fetch):**
```js
picker.ready                                   // resolves after svf.js and faces.json are loaded
picker.faces()                                 // the index entries
picker.select({latin: key|null, hangul: key})  // fetches (once) and opens the chain [latin, hangul]; returns {latin: info|null, hangul: info}
picker.setText(str); picker.setScale(num, den); picker.setTarget({kind: "gray8"|"mono"|"rgb565", fg, bg, threshold, zoom, grid})
picker.render()                                // -> {err, errName, width, ascent, descent, ink, ms}; repaints the canvas
```
`serve.mjs DIR` prints `http://127.0.0.1:PORT/` and serves DIR (`.wasm` as `application/wasm`, `.json`, `.SVF` as
`application/octet-stream`, `.TXT` as `text/plain; charset=utf-8`). `check.mjs DIST OUT` launches
`chromium.launch({channel: "chrome", headless: true})` (or `executablePath: process.env.PICKER_BROWSER`), writes
`OUT/browser.txt` (`browser.version()`, playwright-core version), runs the cases below, exits 1 with the failing case
named, 2 when no browser launches. Case A (this task): for every face of the index, `select({latin: null, hangul: key})`,
text = pangram + ASCII preset, scale 1/1, GRAY8: append `key err ink ms` to `OUT/faces-report.tsv`; screenshot the
preview element for `svf/dos/PAPLG18.SVF` (with latin `svf/dos/NGOTB16.SVF`, 2/1) to `OUT/paplg18-chain.png`.

Page behaviour: the list is built from `faces.json` with filters (group, px, bpp, jamo, name); clicking a row selects it
as the Hangul face (the Latin select stays), the card shows its info; a face is fetched once, put in the module heap and
kept in a `Map`; `select` calls `svfw_reset()` before opening the new order and never frees a pointer. The canvas is
`width + 2` by `ascent + descent + 2` per line at the render scale, drawn with `image-rendering: pixelated` at the view
zoom; the status line shows the measure, ms, ink count and the `svf_err` name on failure. Layout and colours follow
`research/jamo-studio/src/page.html` (tokens on `:root`, dark by `prefers-color-scheme`).

- [ ] **Step 1: Failing tests** `TestPage` (skip without node, `web/test/node_modules/playwright-core` or a launchable
  browser): `test_every_face_renders` (`faces-report.tsv` has 153 rows, every `err` 0 and `ink > 0`),
  `test_page_reports_browser` (`browser.txt` names a Chrome/Chromium version and `playwright-core 1.62.1`),
  `test_first_screenshot` (`paplg18-chain.png` is a PNG wider than 200 px with more than one distinct pixel value).
- [ ] **Step 2: Run** `(cd web/test && npm ci)` once (writes `package-lock.json`, committed; `node_modules` ignored);
  `python3 -m unittest tools.test_web_picker -k TestPage` → FAIL (no page).
- [ ] **Step 3: Implement** the page files, `serve.mjs`, `check.mjs` case A; `web/test/package.json`
  (`"devDependencies": {"playwright-core": "1.62.1"}`, `"private": true`).
- [ ] **Step 4: Run** → PASS (3 tests); open `python3 -m http.server -d web/dist` by hand once and note in the commit
  message which faces were looked at.
- [ ] **Step 5: Commit** `web: picker page (face list, lazy faces, GRAY8 preview) and the Playwright check over all 153 faces`.

### Task 4: Controls: chain, scale, presets, targets, licence pane

**Files:** Modify `web/index.html`, `web/style.css`, `web/picker.js`, `web/test/check.mjs`, `tools/test_web_picker.py`.

**Interfaces — Consumes:** Task 3. **Produces:** the controls of the spec: Latin select + Hangul select, "use as Latin /
Hangul" row buttons; scale select (1/2, 2/3, 1, 3/2, 2, 3, 4, 6, 8) + two number inputs (1..16) with the resulting px;
view zoom 1-8 + grid; preset buttons writing the textarea (pangram, boundary clash, rare, double finals, ASCII, mixed game
line, compat jamo, marks); target radio GRAY8 / MONO / RGB565 with ink and paper colour pickers, MONO threshold slider,
RGB565 fg/bg (quantised: the picker value is shown re-expanded from 5/6/5); the licence pane (`<pre>` per licence file,
fetched once, file name as heading). The face list marks a face that lacks a code point of the current text (`svfw_has`)
with a count, e.g. `-3`. check.mjs case B: screenshots `OUT/hgkey6j-mono.png` (HGKEY6J, 3/1, MONO threshold 128,
`삶닭값읊핥`) and `OUT/gbatb47-rgb565.png` (GBATB47 over NGOTB16, 1/2, RGB565 fg #FFE000 bg #203040, mixed game line);
asserts `render().width` at 2/1 is twice the 1/1 width for the ASCII preset on PAPLG16 (`S(advance)` with den 1);
asserts the licence pane text for PAPLG18 contains `Paperlogy faces (PAPLG18.SVF, PAPLG16.SVF)` and the OFL first line;
asserts MONO at threshold 1 has at least as many ink pixels as at 255 for GOTHA24A (2 bpp).

- [ ] **Step 1: Failing tests** `TestPage::test_controls_report` (check.mjs writes `OUT/controls.json` with
  `{width1, width2, mono1, mono255, licence_ok}`: `width2 == 2 * width1`, `mono1 >= mono255`, `licence_ok` true),
  `TestPage::test_three_face_screenshots` (`paplg18-chain.png`, `hgkey6j-mono.png`, `gbatb47-rgb565.png` exist, each a
  PNG with more than one distinct pixel value; the RGB565 one contains a pixel equal to the 5/6/5 expansion of #FFE000).
- [ ] **Step 2: Run** `-k TestPage` → FAIL (no case B).
- [ ] **Step 3: Implement** the controls and case B.
- [ ] **Step 4: Run** → PASS (5 TestPage tests); `TestModule` still PASS.
- [ ] **Step 5: Commit** `web: chain, scale, presets, MONO/RGB565 targets and the licence pane; screenshots of three faces`.

### Task 5: Picker choices and the JSON export

**Files:** Modify `web/index.html`, `web/picker.js`, `web/test/check.mjs`, `tools/test_web_picker.py`.

**Interfaces — Consumes:** Task 4, `tools/pairing2svf.py` (`TEMPLATES` names for the datalist, written into `picker.js`
by hand as a constant with a comment naming the source). **Produces:**
```js
picker.addChoice({game, id, lineh})   // captures the current chain + scale; -> the choice object
picker.choices(); picker.removeChoice(i)
picker.exportJSON()                   // -> the string of the spec's shape (games grouped by name, fonts in insertion order)
```
`korean`: `key` and `file` = the Hangul face key, `label` from the index, `w`/`h` = `ceil(cell * num / den)`, `ascent` =
`S(ascent)`, `bpp`, `latin` = the Latin key or null, `scale` = `[num, den]`; `picked: true`; `lineh` only when given.
UI: game input with the datalist, font id, line height, "Add choice", a table (game, id, lineh, Hangul, Latin, scale, px,
remove), export textarea, "Copy", "Download selection.json". Choices persist in `localStorage` (`svfpicker.choices`, in
try/catch). check.mjs case C: adds `{game: "KQ4", id: "300", lineh: 12}` with PAPLG18 over NGOTB16 at 1/1 and
`{game: "KQ4", id: "600", lineh: 24}` with GBATB47 at 1/2, writes `exportJSON()` to `OUT/selection.json` and screenshots
the choices + export panel to `OUT/export.png`.

- [ ] **Step 1: Failing tests** `TestPage::test_export_shape` (`selection.json`: `format == "scummvm-ko-font-pairing/1"`,
  one game `KQ4` with two fonts, `{f["korean"]["key"] for g in sel["games"] for f in g["fonts"] if f.get("korean")} ==
  {"svf/dos/PAPLG18.SVF", "svf/dos/GBATB47.SVF"}`, the second font's `korean.h == 27` and `w == 23` (GBATB47's cell is
  46 x 54, ceil at 1/2), `ascent == 23` (`S(45)` at 1/2, round half up),
  `lineh` 12 and 24, `picked` true, `latin` `svf/dos/NGOTB16.SVF` then null), `test_export_screenshot` (`export.png`
  exists, a PNG with more than one distinct pixel value), and a pure-Python `TestExportShape::test_pairing2svf_reads_it`
  (the same file through `pairing2svf.main` with `--data` a temp dir holding no `korean*.json`: it exits with the
  message `faces not in` naming both keys, which is the first check after the shape is accepted, so the shape passed).
- [ ] **Step 2: Run** `-k TestPage -k TestExportShape` → FAIL.
- [ ] **Step 3: Implement** choices, export, case C.
- [ ] **Step 4: Run** → PASS; the whole file `python3 -m unittest tools.test_web_picker` → PASS (TestIndex 5, TestModule
  6, TestPage 7, TestExportShape 1).
- [ ] **Step 5: Commit** `web: picker choices and the scummvm-ko-font-pairing/1 export (read by pairing2svf)`.

### Task 6: README, gate and card evidence

**Files:** Create `web/README.md`; modify `README.md` (layout table row `web/`, drop the WASM line of "Later"),
`c/ports/web/README.md` (link), `c/check.sh` (no change unless it lists test files).

- [ ] **Step 1:** `web/README.md`: build (`web/build.sh`), serve (`python3 -m http.server -d web/dist`), tests (the three
  classes, their tools and skip reasons, `npm ci` in `web/test`, `PICKER_BROWSER`, `NODE`, `EMSDK`), the export's extra
  keys and that today's `pairing2svf --data` looks up `korean*.json` by key (an SVF-reading `--data` is a later card),
  the `window.picker` API, and what is generated vs committed.
- [ ] **Step 2: Verify** `python3 -m unittest discover -s tools -p 'test_*.py'` → every test PASS (none skipped on this
  host); `make -C c check` → OK; `git status` shows nothing under `web/dist`, `web/test/out`, `web/test/node_modules`.
- [ ] **Step 3: Commit** `web: README and gate notes for the picker`; then `agentws complete t_fe9f6c30` with the
  evidence: the unittest summary line, `web/test/out/faces-report.tsv` (153 rows, all err 0), the four PNG names and
  `browser.txt` contents, and the `cases.txt` lines of the delivered Task 5 cases (`case export`, `case choices`) beside
  the `mkindex.py` counts line.
