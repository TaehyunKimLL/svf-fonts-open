# Desktop font finder, phases 0 and 1: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 0 makes the recipe module, the scan tools and the sidecar ready for the finder (session recipes as
entries, the user library, `recipe check / run / list`); phase 1 adds the finder view for 1 bpp files (each mark
reading one file as it is), from "an unknown file" to faces in the output folder and a saved recipe.

**Architecture:** Every pixel rule stays in `tools/binscan.py` / `tools/rawcarve.py` / `tools/jamoset.py`. The
sidecar decodes the live grid in-process (`binscan.decode` on a bounded `pread` window, a gapless PNG), runs scans,
trials and builds as bounded subprocesses, and keeps the session in `job.json`; the page (`finder.js`) draws the
overlay and the WASM previews. Marks become **session recipes** (schema version 1) that are font entries like a known
ROM set's, so the run, the trial and `recipe run` share one planner (`recipe.face_plan`).

**Tech Stack:** Python 3 standard library (+ Pillow and fontTools already in the sidecar; no numpy), plain ES modules
in `maker/static/`, Electron 45 shell (unchanged except its e2e), PyInstaller sidecar.

**Spec:** `docs/superpowers/specs/2026-11-23-desktop-font-finder-design.md` (approved 2026-11-24, with the 15.1
readings of decisions 8 and 9). Section numbers below ("spec 8.2") are that document's. Sections 13 (tests) and 17
(review dispositions) bind every task.

**Base:** `main` at `fa632ac` (mame-roms `9ddfe90`, svf2ttf-composite `ef41805`, desktop-export `fa632ac`). Branch
`finder-design` was rebased onto it; implementation branches start from `finder-design`.

## Where the merged code and the spec differ (plan against the code)

The spec's sections 8 and 9.5 were read against desktop-export `a103f56`; `main` has later fixes. What this plan
assumes, checked in the tree at `fa632ac`:

| Spec says | Code at `fa632ac` | Plan |
|---|---|---|
| 4.1 / 4.2: main's tools have no `--invert`, `ink`, `region`, `eng --first` | mame-roms is merged: `binscan.py` has `--invert`, `--gfx`, `--bg/--fg`; `rawcarve.py` has `ink`, `region --group`, `eng --first/--count/--width/--invert`; `jamoset.py --layout spec` | spec 16 "mame-roms re-read after merge" is settled; no task |
| 7.5: `binscan`, `rawcarve`, `nkpspec` into the sidecar's `TOOLS` | `rawcarve` is in `TOOLS` already; `binscan`, `nkpspec` are not; `maker/recipes` is bundled by `sidecar.spec` but `build-sidecar.sh` does not stage it into `$OUT/repo/maker/recipes` | F0.12 adds what is missing |
| 9.5: `recipe.get` built-in only; refusals of `optional`, a fit's `hangul`, `top` on `bdfface`, unknown `dest`; no `johab844` route | as said; plus `_copied_as_is` (the raw-set storage rule) and `--group` are in | F0.5, F0.6, F0.9 |
| 9.4 `expect` "checked at run" | nothing reads `expect` at run (only `RealRomTest` compares bytes) | F0.7 |
| 8.4 `RECIPE-<id>.json` in `build-<id>/` | not written | F0.11 |
| 8.1 `_inputs_of_selected` "must take several" | `by_key = {(root, path): font}` keeps the **last** entry of a key | F0.10: keep the first (the host's scanned entry, which carries `file_id`) |
| 8.1 settings key | `_kept_settings` keys `(root path, path, face_index)` | F0.9 (library id), F0.10 (session, item) |
| 4.5 notes over 512 bytes | `zipout.note_commands` writes a local job's paths as basenames (`_note_token`) | spec 16's 512-byte risk does not arise for phase-1 commands; F0.11 tests a deep path |
| licence staging, `writes_face`, `delivered()` | a `recipe` entry is a face-writing entry like any other; exports (`options.export`) stage the chosen licence as for a known set | finder entries reuse it unchanged; F0.10 runs a TTF export of a session face |
| 7.3 "save" waits for hashes, `PUT /api/recipes/<rid>` must equal the recipe's id | a session recipe's id is `found-...` | design call (F1.11): a session's save is `POST .../finder/<n>/save`, which allocates the library id (spec 7.3 rule) and writes; `PUT /api/recipes/<rid>` stays for a whole recipe object (a loaded file) |
| 8.1 "how the lookup is passed down is phase 0's to settle" | `routes.routes(font)` and `settings` see the entry only | design call (F0.9): a user or session recipe's entry carries the validated recipe object as `recipe.body`; `recipe.resolve(font)` = body, else built-in by id. The body holds no source byte (spec 7.4) |

## Global Constraints

- No font or ROM byte in the repository: fixtures are built in the test from OFL faces of `svf/` (`svf/dos/NEODG16.SVF`
  through `svf2ttf.load_face`, as `maker/test/test_recipe.py` does) and seeded noise.
- Untrusted input: the file is never executed, unpacked or parsed beyond bounded reads; every in-process read opens with
  `os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK`, requires `S_ISREG` of `os.fstat(fd)`, compares `(st_dev, st_ino,
  st_size, st_mtime_ns)` with the session's values (409 "the file changed: open it again") and reads with `os.pread`;
  **never `mmap`** a user's file. Every number of a request is range-checked before any allocation.
- A recipe is untrusted: parameters only; the server builds every argv; file names are labels; face names and `dest`
  go through `maker/naming.py`.
- Privacy: no byte of a source file in `job.json`, logs, a recipe or an error text; render GETs are `Cache-Control:
  no-store`, in `_HOST_CHECKED`, served to the same launch only, never written outside the scratch.
- Writes into the output folder go through `zipout._OutputTree`; user recipes and `prefs.json` through a temporary file
  in the same folder and `os.replace`, never a path taken from a request.
- Local only: nothing new listens or connects. `test_local.py`'s `test_static_no_network_imports` scans every
  `maker/*.py` and `tools/*.py`, so new modules are covered by existing tests; no new import of `socket` outside
  `server.py`.
- Limits (spec 7.4, exact): files a session 16; a file 64 MiB (`rawcarve.MAX_FILE`); a scan window 16 MiB
  (`binscan.MAX_SCAN`); a render 4,096 glyphs, glyph sides 1..1024, 64 columns, canvas within `preview.MAX_CANVAS`
  (4096) / `preview.MAX_PIXELS` (4,000,000), two renders at a time; analysis 60 s total and 20 s a scan by default,
  300 s at most; trial 60 s a tool, 300 s in all; sessions a job 8, candidates a session 200, marks 64; a recipe or
  spec loaded 256 KiB, 16 files, 64 items, 16 faces; user recipes 500.
- Errors of `/api/jobs/<id>/finder...`, `/api/recipes...` and `/api/prefs` are JSON `{"error": <English>, "code":
  <stable code>}`; codes used in this plan: `finder.changed`, `finder.hashing`, `finder.busy`, `finder.limit`,
  `finder.missing`, `finder.state`, `finder.invalid`, `finder.packed` (a notice), `render.busy` (429), `render.bounds`, `render.unsupported`, `anchor.range`,
  `anchor.pitch`, `anchor.no_grid`, `anchor.conflict`, `mark.reading`, `mark.invalid`, `recipe.invalid`,
  `recipe.exists`, `recipe.builtin`, `recipe.limit`, `prefs.invalid`.
- Page strings: every finder string through `maker/static/strings.js` `t(key, values)`, EN and KO; the language is
  kept by the server in `<data root>/prefs.json` (the shell's `localStorage` does not survive a quit); no clipboard
  permission is added (the shell denies them all).
- Python tools stay: no JS or WASM decoder, no new Python dependency.
- Scratch for tests and runs under `~/work/tmp/<project>-<purpose>` (`export TMPDIR=$HOME/work/tmp/finder-<task>`),
  never `/tmp`. Heavy runs under `~/.local/bin/heavy` (16 GiB memory cap, two slots). Load and stress runs (the
  32 MiB windows fixture, the performance record) run once per task, never in a loop; full gate suites are not run
  as load tests on hpz2.

### Gates (named once; each task's gate line says which apply)

    export TMPDIR=$HOME/work/tmp/finder-<task>; mkdir -p "$TMPDIR"
    G-tools:   ~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_*.py'
    G-maker:   flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'
    G-frozen:  ~/.local/bin/heavy bash maker/build-sidecar.sh             # includes test_frozen.py, 0 skipped
    G-e2e:     flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh
    G-appimage: ~/.local/bin/heavy bash desktop/build/build-appimage.sh   # takes the browser lock itself

G-tools and G-maker run for every task (the task's own test file first, then the suite). G-frozen, G-e2e and
G-appimage run only where a task says so (packaging or the page flow).

## Review Focus

The inputs the spec implies but section 13 does not test, most likely first; each has its test in the owning task.

1. **Apply twice, or apply after editing the marks** (a double click, a second tab): the job must hold one entry per
   Hangul mark, the old entries replaced, unchanged items keeping their settings. Test in F1.9
   (`test_apply_twice_and_reapply_after_edit`).
2. **A sidecar restart while an analysis or trial was running**: the session must come back with that work marked
   `interrupted` (a button to run it again), never `running` forever, and the next render rebuilds the scratch. Test in
   F1.7 (`test_restart_marks_running_analysis_interrupted`) and F1.10 (`test_restart_marks_trial_interrupted`).
3. **Deleting the session or the job while a scan or trial runs**: the tools are killed, nothing is written into a
   removed scratch, the server logs no traceback. Test in F1.4 (`test_delete_session_during_tool`).
4. **Non-ASCII, comma and long paths** (a folder `글꼴, ROMs` 250 bytes deep): session identity, the carve commands,
   `BUILD.md` lines (512-byte cap) and the recipe's file names all work. Test in F0.11
   (`test_deep_korean_path_run_and_notes`) and F1.3 (`test_session_on_korean_comma_path`).
5. **A render at the end of a file** (offset within the last glyph, count past the end, a file shorter than one
   glyph): the PNG holds only the glyphs that fit, `X-Finder-Count` says how many, zero glyphs is a 200 with count 0,
   never a 500. Test in F1.5 (`test_render_at_the_end`).

---

# Phase 0

Phase 0 changes no page. Its tasks are independent of the finder view and land on `main` before phase 1 starts.

### F0.1: The opening rule in binscan, rawcarve and nkpspec

Spec 7.5 row 3, 7.4 "The tools". Size S.

**Files:**
- Modify: `tools/binscan.py` (`window`, `cmd_info`, `cmd_runs`, `cmd_render`: every `open(a.file)` and
  `os.path.getsize(a.file)`)
- Modify: `tools/rawcarve.py` (`read`, `read_range`, `cmd_cut`, `cmd_region`, `load_spec`, every input `open`)
- Modify: `tools/nkpspec.py` (`main`)
- Modify: `docs/tools.md`, `docs/tools.ko.md` (one sentence each in the three tools' sections)
- Create: `tools/test_open_rule.py`

**Interfaces:**
- Produces: `binscan.open_regular(path, tool="binscan.py") -> io.BufferedReader` (opened `O_RDONLY | O_NOFOLLOW |
  O_NONBLOCK`, `S_ISREG` of `fstat`, else `SystemExit("<tool>: <path>: not a regular file")` or `SystemExit("<tool>:
  <path>: <strerror>")`); `binscan.size_of(fh) -> int` (`os.fstat(fh.fileno()).st_size`). Every tool reads sizes from
  the open descriptor, not from the path.
- `nkpspec.py` refuses a file over `rawcarve.MAX_FILE` before reading it.

- [ ] **Step 1: Write the failing tests** (`tools/test_open_rule.py`, each command run as a subprocess with
  `timeout=20`):

```python
CMDS = [["binscan.py", "info"], ["binscan.py", "ascii"], ["binscan.py", "sets"],
        ["binscan.py", "runs", "--glyph", "8x16"], ["binscan.py", "render", "--glyph", "8x16"],
        ["rawcarve.py", "cut", "--offset", "0", "--length", "16", "-o", OUT],
        ["rawcarve.py", "eng", "--offset", "0", "-o", OUT], ["rawcarve.py", "bdf", "--glyph", "8x16", "--chars", "ascii", "-o", OUT],
        ["rawcarve.py", "ink", "--glyph", "8x16", "-o", OUT], ["rawcarve.py", "region", "--group", "{F}", "-o", OUT],
        ["rawcarve.py", "compose", "--spec", "spc1500", "-o", OUT], ["nkpspec.py", "find"]]

def test_symlink_is_refused(self):      # for every CMDS row with the input a symlink to a good 8 KiB file
    self.assertNotEqual(proc.returncode, 0); self.assertIn(link_name, proc.stderr)
def test_fifo_does_not_hang(self):      # a mkfifo input: every row returns within 20 s, non-zero, "not a regular file"
def test_directory_is_refused(self):
def test_good_file_still_works(self):   # the same rows on the regular file: return codes as before this change
def test_nkpspec_over_the_cap(self):    # a sparse file of rawcarve.MAX_FILE + 1 bytes (truncate, no data written)
    self.assertIn("larger than", proc.stderr)
def test_compose_spec_file_link_is_refused(self):   # --spec pointing at a symlinked JSON file
```

- [ ] **Step 2: Run them; they fail** — `python3 -m unittest discover -s tools -p test_open_rule.py` (the FIFO rows
  time out today: the test's own 20 s timeout reports it).
- [ ] **Step 3: Implement** `open_regular` / `size_of` in `binscan.py` and route every input of the three tools
  through it (rawcarve's `CarveError` path stays for its own messages). `-o` outputs are unchanged.
- [ ] **Step 4: Run the file, then G-tools** — expected PASS, `tools/test_tiles.py` unchanged.
- [ ] **Step 5: Commit** `tools: binscan, rawcarve and nkpspec open inputs without following links, regular files only,
  non-blocking; nkpspec refuses a file over 64 MiB (finder phase 0)`.

Gate: G-tools, G-maker.

### F0.2: binscan `--json`, archive kinds, the 94 x 94 wording, `render_text`

Spec 7.5 rows 1, 4, 5; 6 stage 0. Size M. Depends: F0.1.

**Files:**
- Modify: `tools/binscan.py`
- Modify: `docs/tools.md`, `docs/tools.ko.md` (`binscan.py` section: `--json`, the new kinds)
- Create: `tools/test_binscan.py`

**Interfaces:**
- Produces: `binscan.kind_info(data, path) -> dict` with keys `word` (`mz`, `com`, `arj`, `zip`, `rar`, `7z`, `gzip`,
  `xz`, `lha`, `option-rom`, `raw`), `packed` (`lzexe`, `pklite` or None), `archive` (bool), `header` (MZ header
  bytes or None), `image_end` (int or None), `load` (256 for `.COM`, else None); `kind_of(data, path)` keeps its text
  and is built from `kind_info`. Magic: RAR `Rar!\x1a\x07`, 7z `7z\xbc\xaf\x27\x1c`, gzip `\x1f\x8b`, xz
  `\xfd7zXZ\x00`, LHA `-lh?-` / `-lz?-` at offset 2. The text for each new kind ends "packed: unpack it before
  scanning" (archives: "an archive: unpack it first").
- Produces: `--json` on `info`, `runs`, `sets`, `ascii`: one JSON object on stdout, numbers and fixed words only:
  - info: `{"cmd": "info", "size", "kind": kind_info, "signatures": [{"size", "what"}], "multiples": [{"n", "size",
    "what"}], "block", "entropy": [float rounded to 3 places]}`
  - runs: `{"cmd": "runs", "start", "length", "glyph": [w, h], "order", "stride", "invert", "min", "phases": [..],
    "runs": [{"offset", "glyphs", "blank", "end"}]}` (offsets absolute)
  - sets: `{"cmd": "sets", "sets": [ni, nm, nf], "stride", "span", "hits": [{"offsets": [..], "inked", "of",
    "seam", "end", "nearby", "tie": bool}], "more": int}`
  - ascii: `{"cmd": "ascii", "height", "invert", "hits": [{"offset", "edge", "short": bool}]}`
- Produces: `binscan.render_text(glyphs, w, h, offset, stride, cols) -> str` (the `#` / `.` form `cmd_render` prints
  today; `cmd_render` calls it).
- The 94 x 94 lines: `SIGNATURES` entry 282752 reads `"a 94 x 94 table, 16x16 (8,836 x 32 B): KS X 1001 or another
  set: look"`, and the computed line `"a 94 x 94 table (KS X 1001 or another set: look)"` (spec 3).

- [ ] **Step 1: Write the failing tests** (`tools/test_binscan.py`; fixtures built in the test: an 8x16 ASCII font from
  `NEODG16.SVF` at 0x3a0 in seeded noise, an 8x4x4 set, files that start with each magic):

```python
def test_json_info_has_no_file_bytes(self):     # parse stdout; json.dumps(obj) contains no 16-byte run of the file
def test_json_matches_text(self):              # runs/sets/ascii: every offset of the text output is in the JSON, same order
def test_kind_info_archives(self):             # each magic -> word, archive/packed; kind_of text names it
    self.assertEqual(binscan.kind_info(b"Rar!\x1a\x07\x00" + bytes(64), "x.rar")["word"], "rar")
def test_com_load_and_mz_header(self):         # .COM -> load 256; an MZ header of 2 paragraphs -> header 32
def test_94x94_wording(self):                  # a file of 282,752 bytes: "KS X 1001 or another set: look"
def test_render_text_is_the_old_output(self):  # render without --png prints exactly render_text(...)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s tools -p test_binscan.py` — FAIL (no `--json`).
- [ ] **Step 3: Implement.** The text output of every command stays byte-identical (the test pins it against a copy
  of today's output captured in the test from `git show fa632ac:tools/binscan.py` run on the same fixture).
- [ ] **Step 4: Run the file, then G-tools** — PASS.
- [ ] **Step 5: Commit** `binscan: --json on info, runs, sets and ascii; RAR, 7z, gzip, xz and LHA named; 94 x 94
  wording for any set; render_text (finder phase 0)`.

Gate: G-tools, G-maker.

### F0.3: binscan `runs --phases`, `--around`, and edge runs of a window

Spec 6 stage 1 and 2, 7.5 row 2, 13 "Windows". Size M. Depends: F0.2.

**Files:**
- Modify: `tools/binscan.py` (`cmd_runs`, argument parser)
- Modify: `docs/tools.md`, `docs/tools.ko.md`
- Test: `tools/test_binscan.py` (class `RunsWindows`)

**Interfaces:**
- `runs --phases P,P,...`: absolute residues: an offset `off` is scanned when `off % stride` is in the list (each 0 ..
  stride-1); refused with `--step`. Without `--phases` the behaviour is today's.
- `runs --around OFFSET,LENGTH`: the scanned file range is `[OFFSET - stride, OFFSET + LENGTH + stride)` clipped to the
  file, with absolute phases (so results of two windows line up); refused with `--start` / `--length`.
- With `--json`, a window that does not start at 0 or does not reach the file's end also reports, under `"edges":
  [{"offset", "glyphs", "blank", "end", "edge": "start" | "end" | "both"}]`, every run that touches its first or last
  glyph slot **whatever its length**, before `--min` and before the choice among overlapping runs; `"runs"` keeps
  today's rule. The analysis (F1.6) joins them.

- [ ] **Step 1: Write the failing tests:**

```python
def test_phases_are_absolute(self):        # an 8x16 run at 0x1003: --phases 3 finds it from --start 0 and --start 0x800
def test_around_widens_by_one_glyph(self):
def test_edge_runs_below_min(self):        # 40 glyphs at 0x10000 - 20*16: window [0, 0x10000) -> edge "end", 20 glyphs, min 32
    self.assertEqual(obj["edges"][0]["edge"], "end"); self.assertEqual(obj["runs"], [])
def test_no_edges_at_file_bounds(self):    # a run at offset 0 with --start 0: no "start" edge
def test_phases_and_step_refused(self):
```

- [ ] **Step 2: Run, FAIL.** **Step 3: Implement.** **Step 4: Run the file and G-tools, PASS.**
- [ ] **Step 5: Commit** `binscan runs: --phases (absolute), --around, and a window's edge runs in --json (finder
  phase 0)`.

Gate: G-tools, G-maker.

### F0.4: binscan `grid_png`

Spec 5.1 "Grid", 7.5 row 3. Size S. Depends: F0.3.

**Files:** Modify `tools/binscan.py` (`png_bytes` gets `level=9`), `docs/tools.md`, `docs/tools.ko.md`; Test
`tools/test_binscan.py` (class `GridPng`).

**Interfaces:**
- Produces: `binscan.grid_png(glyphs, w, h, cols) -> bytes`: an 8-bit grey PNG, `cols * w` wide, `ceil(n / cols) *
  h` high, one pixel a glyph pixel, no gap; ink 0, paper 255, the unused cells of the last row 128; zlib level 1.
  `n == 0` gives a 1 x 1 PNG of value 128. `w * cols` and the height must be within `preview.MAX_CANVAS` (4096) and the
  product within 4,000,000: `ValueError` otherwise (the caller bounds first; this is the last guard).

- [ ] **Step 1: Write the failing tests:** `test_pixels_equal_decode` (decode the PNG with `zlib` in the test, every
  pixel equals `decode(...)` of the fixture), `test_level_1` (the IDAT stream's zlib header is `78 01`),
  `test_bounds` (`ValueError` at 4097 wide), `test_empty`, and `test_time_256_glyphs` (records the time of 256 16x16
  glyphs, `decode` + `grid_png`; asserts under 2 s and prints the number; the 100 ms target is recorded in F1.17).
- [ ] **Steps 2-4: Run FAIL, implement, run PASS.**
- [ ] **Step 5: Commit** `binscan: grid_png, a gapless one-pixel-a-pixel grey PNG at zlib level 1 (finder phase 0)`.

Gate: G-tools, G-maker.

### F0.5: Recipes: English placement (`top` on a BDF route) and the test encoder

Spec 8.2 "English: one placement for both forms", 9.4 `ascent`, 9.5 "finder adds" rows 1 and 3, 13 "Readings"
(English placement). Size M. Depends: none (parallel with F0.1-F0.4).

**Files:**
- Modify: `maker/recipe.py` (`_face`: drop the `top` refusal; `_Plan.english_bdf`, `_Plan.bdf`)
- Create: `maker/test/finderfx.py` (the encoder and glyph sources; F0.8 and F1.1 extend it)
- Modify: `maker/test/test_recipe.py` (class `EnglishPlacementTest`)

**Interfaces:**
- Produces (`finderfx.py`): `glyphs_from_svf(cps, w=16, h=16, path=NEODG16) -> {cp: rows}` (rows of 0/1 from
  `svf2ttf._levels`, as `test_recipe.synthetic_pair`); `encode(rows, w, h, order="rows", lsb=False, invert=False,
  stride=None) -> bytes`, the exact inverse of `binscan.decode` for one glyph (padding bytes of a stride are seeded
  noise from `random.Random(seed)`); `english_font(h, top_rows_cut=0) -> {code: rows}` (8xH glyphs cut from the
  8x16 face: rows `[top_rows_cut, top_rows_cut + h)`).
- `recipe._Plan.english_bdf(ids, hangul=None)`: the BDF is cut from the **raw form** (`eng`, then `rawcarve.py bdf
  RAW --glyph Wx16 --chars ascii`) whenever the face has more than one English item, or its one item is not a 16-row
  glyph at `top` 0. Its `--ascent` (16-row coordinates): the Hangul item's `ascent` when it has one, else `top` + the
  English item's `ascent` when it has one, else none (the tool's 14). A 16-row item at `top` 0 keeps today's direct
  `rawcarve.py bdf SRC` with the item's own `ascent` (the built-in recipes' argv must not change: the planner tests of
  `LibraryTest` pin them).
- `face_plan` passes the face's Hangul item to `english_bdf`.

- [ ] **Step 1: Write the failing tests** (`EnglishPlacementTest`; a 16x16 KS-grid Hangul as `synthetic_pair` builds
  it, beside an English font written by `finderfx`):

```python
def test_8x8_top4_rows_4_to_11_in_every_face(self):
    # recipe: hangul ks-grid 16x16 ascent 12; ascii english reading [8, 8], top 4; faces bdfface (BDF form) and
    # bdfface + from-svf fit with `from` (its --eng is the raw form). Run face_commands, read each SVF with
    # jamoset.parse_svfn: for "AHgy" every inked row of the letter is in 4..11 of the 16-row cell, in both faces.
    # (The dos raw route's --eng gets the same check in F0.8, which has a raw-set fixture.)
def test_8x14_top1(self):                 # rows 1..14
def test_padded_bdf_header_ascent_is_the_hangul_items(self):   # built face's header ascent == 12
def test_ascent_falls_back_to_top_plus_item_ascent(self):     # no Hangul ascent: top 4 + item ascent 7 -> 11
def test_list_of_two_equals_the_whole(self):  # digits and letters split into two items == one item of the whole font
def test_builtin_argv_unchanged(self):        # every built-in recipe's face_commands equal a copy recorded from fa632ac
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_recipe.py -k EnglishPlacement` — FAIL
  (`top` refused).
- [ ] **Step 3: Implement.** **Step 4: Run test_recipe.py, PASS.**
- [ ] **Step 5: Commit** `recipe: an English item with top on a BDF route is cut from its padded raw form, its ascent
  counted in the 16-row cell; finderfx encoder (finder phase 0)`.

Gate: G-maker.

### F0.6: Recipes: direct fits, `dest`, the `johab844` route, optional files

Spec 8.3 ("A fit is self-contained", the `johab844` row), 9.2 (`optional`, a face offered only with its files), 9.4
(`dest`, `from` or `hangul`), 9.5 rows 2, 5, 6. Size M. Depends: F0.5.

**Files:**
- Modify: `maker/recipe.py` (`FACE_KEYS`, `ROUTES`, `NATIVE`, `_face`, `validate`, `face_plan`, `offered_faces`)
- Modify: `maker/routes.py` (`recipe_routes`: the `johab844` route; `paths["base"]` reaches the planner)
- Modify: `maker/static/maker.js` (`ROUTES["recipe"]` gets `{"kind": "precomposed", "label": "johab844", "native":
  true, "bpps": [1]}`; `test_page_js_tables_match_python` binds it)
- Modify: `maker/detect.py` (`_recipe_entries`: a face left out names its missing optional file in the label)
- Test: `maker/test/test_recipe.py` (classes `DirectFitTest`, `OptionalFilesTest`, `Johab844RouteTest`)

**Interfaces:**
- Face key `dest` (validated by `naming.DEST_RE`), default `new/<recipe id>`; the batch `dest` setting replaces the
  default as today (settings unchanged; `recipe.face_dest(rec, face_name) -> str` for `recipe run`).
- Route `johab844`: `("precomposed", ("raw-set",))`, native; the Hangul item must be `raw-set` layout `844` of 11,520
  bytes; an English item must be 8 wide (a `[16, 16]` English is refused by name). Command: `johab844.py RAW BASE OUT
  [--eng E]`, `BASE` = `paths["base"]` (the `svf/dos/NEODG16.SVF` path `settings.plan_steps` passes today).
- A fit takes `from` **or** `hangul` (+ `english`): with `hangul`, the step builds `precomposed.svf` from an implicit
  `bdfface` face of those items (same planner, same files); `from` and `hangul` together are refused.
- `optional: true` accepted on a file. `recipe.face_files(rec, face_name) -> set[file id]` (through `hangul`,
  `english`, `from` and regions). `validate` refuses a recipe in which every face needs an optional file ("file X is
  read by every face: it is required"). `recipe.available_faces(rec, bound_ids) -> (faces, missing)` where `missing`
  is `{face name: [file names]}`; `offered_faces(rec, bound_ids=None)` offers the first face of each kind among the
  available ones.
- `validate` also refuses a file id named twice in one region (spec 9.4 `groups`: "a file id appears once in a
  region"; the code checks sizes only).
- `match` is unchanged in its states; a `known` entry's `recipe` gets `"missing_faces": {name: [file names]}` and its
  label `"known: <title>; <NAME>: also pick <file>"` when a face is left out.

- [ ] **Step 1: Write the failing tests:**

```python
def test_fit_bytes_equal_with_from_and_with_hangul(self):   # synthetic TG pair: from TGVGA16 vs hangul+english
def test_fit_unchanged_when_precomposed_deselected(self):   # local job: kinds ["jamo"] only, same SVF bytes as both
def test_from_and_hangul_refused(self):
def test_dest_on_a_face(self):          # "games/x-y" accepted, "../x" refused, written under svf/games/x-y/
def test_johab844_route_argv_and_face(self):   # an 8x4x4 raw set (finderfx) + 8x16 English -> johab844.py argv;
                                              # the built face equals johab844.py run by hand on the same files
def test_johab844_refuses_16x16_english(self):
def test_optional_file_offers_only_faces_without_it(self):  # spc1500-like: jamo face (spec) without the English ROM
def test_every_face_needs_optional_is_refused(self):
def test_file_twice_in_a_region_refused(self):
def test_page_routes_table(self):        # covered by test_server.test_page_js_tables_match_python: run it here too
```

- [ ] **Step 2: Run, FAIL.** **Step 3: Implement.** **Step 4: Run `test_recipe.py`, `test_routes.py`,
  `test_server.py -k page_js_tables`, PASS.**
- [ ] **Step 5: Commit** `recipe: a fit by hangul + english, dest on a face, the johab844 route, optional files and
  faces offered only with their files (finder phase 0)`.

Gate: G-maker.

### F0.7: Recipes: `expect` checked at run, by canonical file, with the numbers of 8.5

Spec 8.5, 9.4 `expect` rows, 13 "Session recipes" (one `expect` hash with either face deselected and in either
order). Size M. Depends: F0.6.

**Files:**
- Modify: `maker/recipe.py` (`_Plan.raw` registers its file in `made`; `face_plan` returns `roles["canonical"]`;
  new `sample_numbers`, `item_numbers`, `check_expect`)
- Modify: `maker/jobs.py` (after a `recipe` entry's face step is done, next to `quality.face_facts`: run
  `check_expect`, store `step["expect"]`; the job keeps `checked` item ids for the run)
- Modify: `maker/zipout.py` (`BUILD.md`: one line a step, `expect: ok` or `expect: <what> differs (got X, want Y)` or
  `expect: <item> not made by this run`)
- Test: `maker/test/test_recipe.py` (class `ExpectTest`)

**Interfaces:**
- `roles["canonical"] = {item id: abs path}` of each item file the step made: `english` the raw form
  (`recipe-<id>-eng.bin`), `raw-set` the cut (`recipe-<id>.fnt`), `ks-dense` / `ks-grid` / `compose` the BDF.
- `recipe.item_numbers(kind, path, reading=None) -> {"glyphs": int, "sha256": str}`: inked glyphs of the canonical
  file (raw English: 256 cells of 16 rows x `ceil(w/8)` bytes; raw set: cells of its layout's glyph bytes; BDF:
  glyphs whose bitmap has a non-zero row).
- `recipe.sample_numbers(svf_path) -> {"bytes", "glyphs", "width", "ascent", "descent", "ink"}`: text `안녕하세요 ABC
  123`; `svfline.measure`; ink = non-zero bytes of `svfline.layout` at `W x H` = 200 x 24, baseline 16 for a 16 px
  cell, else 400 x (C + 8), baseline C; W raised to the measured width rounded up to a multiple of 20 when wider.
- `recipe.check_expect(rec, face_name, canonical, face_path, checked) -> {"items": {id: {"state": "ok" | "differs" |
  "not made", "got": {...}, "want": {...}}}, "faces": {name: {...}}}`; adds the item ids it checked to `checked`.
  A mismatch never fails the step (spec 9.4: reported, faces still written).

- [ ] **Step 1: Write the failing tests:**

```python
def test_sample_numbers_match_recipes_md(self):   # NEODG16-based TGVGA16 synthetic: width/ascent/descent as
                                                  # `svfline.py measure` run as a CLI on the same face
def test_one_hash_either_face_and_order(self):    # expect.items.ascii.sha256 recorded once; job runs:
    # (precomposed only), (jamo only), (both): step["expect"]["items"]["ascii"]["state"] == "ok" in the first step
    # that made it, absent from the second
def test_mismatch_reported_face_written(self):    # wrong expect.faces.TGVGA16.ink -> step done, BUILD.md line names it
def test_not_made_is_said(self):                  # a bdfface face with a direct 8x16 English never makes the raw form
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `recipe: expect checked at run by each item's canonical file and the sample-line numbers;
  reported in the step and BUILD.md (finder phase 0)`.

Gate: G-maker.

### F0.8: The readings oracle

Spec 8.2 "Proof", 13 "Readings", 16 "621's storage is strips: read, not run". Size M. Depends: F0.7.

**Files:**
- Modify: `maker/test/finderfx.py` (`raw_set(layout, length, glyphs)`: an 8x4x4 / 10x4x4 / 6x2x1 set drawn from
  `NEODG16`'s pieces by `jamoset`'s own slot order; `ks_grid_file(...)`)
- Create: `maker/test/test_finder_readings.py`
- Modify only if a test finds a planner bug: `maker/recipe.py`

**Interfaces:** consumes `finderfx.encode`, `recipe.face_commands`.

- [ ] **Step 1: Write the tests** (all synthetic; each builds the file, a recipe, runs `face_commands` in
  `$TMPDIR`, and compares the built face's glyph bitmaps with the glyphs the fixture was built from, never with a
  read back through the tools):

```python
READINGS = [dict(order=o, lsb=l, invert=i, stride=s) for o in ORDERS for l in (False, True)
            for i in (False, True) for s in (None, "padded")]          # 32 readings
def test_raw_844_every_reading(self):        # 844 at 11,520: dos raw face == the oracle in each of 32 readings
def test_raw_1044_san_every_reading(self):
def test_621_strips_only(self):              # {"glyph": [16,16], "order": "strips"} builds; any other reading refused
def test_headered_844_plain_only(self):      # 11,522 plain builds; inverted refused by name
def test_english_every_reading(self):        # first code 0x20: the face's ASCII glyphs == oracle
def test_english_top_through_dos_raw(self):   # 8x8 at top 4 and 8x14 at top 1 as the --eng of a dos raw 844 face:
                                              # letters' ink in rows 4..11 / 1..14, as F0.5 checks the BDF route
def test_ks_grid_every_reading(self):        # ks-grid 16x16: bdfface face's syllables == oracle
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_finder_readings.py`. Every failure is a
  planner bug: fix it in `recipe.py` with a one-line note in the commit, never by changing the oracle.
- [ ] **Step 3: Commit** `finder readings oracle: every order, bit order, inversion and stride through the planner,
  per raw layout, against the fixture's own glyphs (finder phase 0)`.

Gate: G-maker. Resolves spec 16 "621's storage".

### F0.9: User library, `recipe.resolve`, detection over both libraries

Spec 8.1 "Which recipe", "Identity" (library id), 9.2. Size M. Depends: F0.6.

**Files:**
- Modify: `maker/recipe.py` (user library functions, `resolve`)
- Modify: `maker/routes.py` (`recipe_routes`: `recipe.resolve(font)`), `maker/settings.py` (lines 332 and 626:
  `recipe.resolve(font)`)
- Modify: `maker/detect.py` (`scan(sources, local=False, library=None)`, `_recipe_entries(..., lib)`: a user recipe's
  entry carries `recipe.body`)
- Modify: `maker/server.py` (`_scan_fonts` passes `recipe.combined(self.server.data_root)` for a local job;
  `_kept_settings.key_of` appends the recipe id for a library `recipe` entry)
- Test: `maker/test/test_recipe.py` (classes `UserLibraryTest`, `ResolveTest`)

**Interfaces:**
- `recipe.user_dir(data_root) -> str` = `<data_root>/recipes`.
- `recipe.user_library(data_root) -> (recipes: {id: rec}, errors: [(file name, message)])`: never raises on a user
  file (skips it, reports it); skips ids of built-in recipes; at most `USER_MAX = 500` files read (more: an error).
- `recipe.combined(data_root) -> {id: rec}`: built-in first, then the user's.
- `recipe.save_user(data_root, rec, replace=False) -> str`: validates; `RecipeError(code="recipe.builtin")` for a
  built-in id, `code="recipe.exists"` when the file exists and not `replace`, `code="recipe.limit"` at 500; writes
  `<id>.json.<random>.tmp` in the folder (`O_CREAT | O_EXCL | O_NOFOLLOW`), fsync, `os.replace`. The folder is made
  with mode 0700 when missing; a symlinked folder is refused.
- `recipe.delete_user(data_root, rid)`.
- `RecipeError` gets `code` (default `"recipe.invalid"`).
- `recipe.resolve(font) -> rec | None`: `font["recipe"]["body"]` when present (validated once, cached by the SHA-256
  of `json.dumps(body, sort_keys=True)`, its `id` equal to `font["recipe"]["id"]`), else `get(id)`.
- Detection: a known **user** recipe's entry is as a built-in one's plus `"body": rec` and `"source": "user"`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_user_recipe_known_in_a_job(self):    # the synthetic TG pair saved as user recipe "my-tg": local job ->
    # host entry known: <title>, routes from resolve(), run writes TGVGA16.SVF
def test_user_never_shadows_builtin(self):    # user file 86box-tgkorvga.json is skipped, error reported
def test_bad_user_file_skipped(self):         # invalid JSON, unknown key, 300 KiB: skipped, others load
def test_save_user_atomic_and_rules(self):    # builtin id -> recipe.builtin; exists -> recipe.exists; replace=True ok;
    # 501st -> recipe.limit; os.replace mocked to raise -> the old file is intact, no .tmp left
def test_save_user_refuses_symlinked_folder(self):
def test_settings_survive_redetect_by_recipe_id(self):  # PUT settings on the known entry, POST detect, kept
```

- [ ] **Steps 2-4: FAIL, implement, PASS** (`test_recipe.py`, `test_routes.py`, `test_settings.py`).
- [ ] **Step 5: Commit** `recipe: the user library (<data root>/recipes), resolve() for user and session recipes,
  detection over both libraries (finder phase 0)`.

Gate: G-maker.

### F0.10: Session recipes as appended entries

Spec 7.2 "stable identity", 8.1 (all bullets), 13 "Planner" (two marks of one file keep separate settings),
"Identity", "Session recipes", 16 "session-recipe entries not prototyped". Size L. Depends: F0.9.

**Files:**
- Modify: `maker/detect.py` (new `session_entries`)
- Modify: `maker/server.py` (`_job_detect` transition appends them; `_kept_settings.key_of` adds `(session, item)`;
  `_inputs_of_selected` keeps the first entry of a `(root, path)`)
- Create: `maker/test/test_finder_entries.py`

**Interfaces:**
- `job["finders"]` (written by phase 1; by the tests here directly through the store): `{"n1": {"files": {"a":
  {"root": <root path>, "path": <relative path>, "member": None, "size": int, "sha256": hex | None}}, "applied":
  [{"item": <hangul item id>, "recipe": <recipe>}], "notices": [...]}}`. A session recipe's `files[*].id` are the
  session file ids (`a`, `b`, ...).
- `detect.session_entries(fonts, finders, roots) -> (entries, notices)`: for each applied recipe, its files are bound
  by identity: `root` path → the current root index (`roots[i]["path"]`), `path` equal; a file not found → no entry
  and a notice `{"session", "item", "code": "finder.missing", "file": name}`. The entry: `id` continuing the `fNN`
  numbering after the last of `fonts`; `root`, `path`, `face_index` 0 and `file_id` copied from the **host file's
  scanned entry** (`recipe.host_file`); `source_kind` `recipe`, `format` `rom`, `label` `"found: <item> in <file
  name>"`, `family` the recipe title, `sizes` `[recipe.item_height(rec)]`, `sizes_fixed` True; `recipe = {"id",
  "files": {fid: [root, path]}, "routes", "body": rec, "finder": {"session", "item"}}`. The host's own entry stays.
- `_kept_settings` key: `(root path, path, face_index, ("finder", session, item))` for a finder entry, `(...,
  ("recipe", id))` for a library one, today's triple otherwise.
- `_inputs_of_selected`: `by_key.setdefault(...)` (the scanned entry with the file's `file_id`).

- [ ] **Step 1: Write the failing tests** (`LocalBase`; a session written into the job with `store.update`, then `POST
  detect`):

```python
def test_two_marks_of_one_file_two_entries(self):   # finderfx 8x4x4 + 8x16 English in one .COM-like file:
    # applied: raw-set "set" (dos raw) and a second session with raw-set at another offset -> two entries + the host
def test_settings_kept_per_mark_across_detect(self):
def test_identity_survives_add_remove_reorder(self):   # spec 13 "Identity": add a file that sorts earlier, remove
    # an unrelated one, reorder roots; each followed by POST detect: the entry is bound to its file (by sha256), its
    # settings kept; then remove the host file: no entry, notice finder.missing
def test_run_passes_check_unchanged_and_writes_face(self):   # select the found entry, run: done, face written
def test_ttf_export_of_a_found_face(self):         # options.export.ttf: the .ttf lands, licence staged as for a known set
def test_found_entry_routes_from_body(self):       # routes.routes(entry) gives the session recipe's faces
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `detect: session recipes as appended recipe entries bound by stable identity, the host's
  file_id, settings kept by session and item (finder phase 0)`.

Gate: G-maker.

### F0.11: `RECIPE-<id>.json` in the run, `recipe check / run / list`, equivalence

Spec 8.4, 8.6, 13 "Equivalence", Review Focus 4. Size L. Depends: F0.7, F0.10.

**Files:**
- Modify: `maker/zipout.py` (`collect`: `RECIPE-<id>.json` in the sidecar list for each recipe entry that ran:
  `json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True)`)
- Modify: `maker/recipe.py` (`main(argv)`, `if __name__ == "__main__"` setting `sys.path` as `sidecar.py` does)
- Create: `maker/test/test_recipe_cli.py`

**Interfaces:**
- `python3 -P maker/recipe.py check RECIPE.json FILE...`: one line a recipe file (`<id> <name>: <FILE>` | `missing` |
  `similar: <FILE> (sha256 differs)`), then `faces: <NAME>, ...` (available) and `not offered: <NAME>: also needs
  <name>`; exit 0 when every required file matched, 3 otherwise.
- `recipe.py run RECIPE.json FILE... --out DIR [--unverified] [--face NAME]...`: binds by size and SHA-256 (with
  `--unverified`, by size then name, and `expect` is not applied); refuses a missing required file (exit 3); runs each
  available face's `face_commands` in `DIR/work/<NAME>/` (600 s a command), writes `DIR/svf/<dest>/<NAME>.SVF`,
  `DIR/BUILD.md` (the commands in `zipout._command_lines` form, the expect lines of F0.7), `DIR/RECIPE-<id>.json`.
  Refuses a `DIR` that is a symlink or holds `svf/` already (exit 2).
- `recipe.py list [--data DIR]`: `<id>  built-in|user  <title>  <name> (<size>), ...`; `--data` default
  `$SVF_MAKER_DATA` or `~/.local/share/svf-maker`; user-file errors on stderr.

- [ ] **Step 1: Write the failing tests:**

```python
def test_run_equals_app_run(self):            # synthetic TG pair as a user recipe: app job vs recipe run: SVF bytes equal
def test_equal_with_jamoset_mask_font_set(self):  # the same with JAMOSET_MASK_FONT naming a TTF of ttf/: still equal
def test_build_md_commands_by_hand(self):     # copy the sources into a folder with links to tools/ maker/ svf/;
    # run BUILD.md's command lines of each face (shlex.split, cwd that folder) -> the same SVF bytes
def test_session_recipes_reproduce_from_build(self):   # two sessions each with an item "hangul": two RECIPE json files
def test_check_states(self):                  # known exit 0; one byte changed -> "similar", exit 3; file missing
def test_unverified(self):
def test_list(self):                          # 7 built-in + 1 user
def test_deep_korean_path_run_and_notes(self):   # sources under "글꼴, ROMs/<250 bytes of folders>/": the app run
    # passes _check_notes (every line <= 512 bytes) and the faces equal recipe run's
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `recipe: check / run / list on the command line; RECIPE-<id>.json beside BUILD.md; app run ==
  recipe run == BUILD.md by hand (finder phase 0)`.

Gate: G-maker. Settles spec 16 "512 bytes" for phase-1 commands (basenames in notes); phase 2's `region` lines keep
the risk.

### F0.12: Sidecar packaging

Spec 7.5 row "maker/sidecar.py ...", 13 "Desktop" (smoke). Size M. Depends: F0.4, F0.11.

**Files:**
- Modify: `maker/sidecar.py` (`TOOLS` adds `binscan` and `nkpspec` as `("tools", "bare")`; `_entry_binscan`,
  `_entry_nkpspec`; `main`: `recipe ARGS...` → `sys.exit(recipe.main(ARGS))`; `USAGE`; `selfcheck` adds
  `"recipe_list": <exit code of recipe.main(["list"]) with stdout captured>`)
- Modify: `maker/build-sidecar.sh` (stage `maker/recipes/*.json` into `$OUT/repo/maker/recipes/`)
- Modify: `maker/test/test_frozen.py` (smoke of `binscan`, `nkpspec`; `recipe list` lists the 7 built-in ids;
  `recipe run` of a synthetic recipe in the frozen build equals the source run), `maker/test/test_sidecar.py`,
  `maker/test/test_sidecar_imports.py` (`GRAPH_MODULES` unchanged unless the import graph says otherwise)

- [ ] **Step 1: Write the failing tests** in `test_sidecar.py` (source mode): `test_tools_table_has_finder_tools`,
  `test_recipe_command_lists_builtin`, `test_selfcheck_recipe_list`; in `test_frozen.py`:
  `test_recipe_list_frozen`, `test_recipe_run_frozen_equals_source`.
- [ ] **Steps 2-4: FAIL, implement, PASS** (source tests; then G-frozen).
- [ ] **Step 5: Commit** `sidecar: binscan and nkpspec tools, the recipe command, recipes staged into the packaged
  tree (finder phase 0)`.

Gate: G-maker, G-frozen, G-appimage (packaging).

---

# Phase 1 (MVP)

Starts when phase 0 is on `main`. New Python modules, each with one job:

| File | Responsibility |
|---|---|
| `maker/finderio.py` | the opening rule, bounded `pread`, identity, hashing |
| `maker/finder.py` | the session model in `job.json`, limits, scratch, binding, marks → session recipes |
| `maker/finderapi.py` | `FinderMixin`: the HTTP handlers of `/api/jobs/<id>/finder...` and `/api/recipes...` |
| `maker/finderrun.py` | the bounded runner of finder tools (registered with `preview` and `toolreg`), per-session cancel |
| `maker/finderscan.py` | the analysis: scan planning (pure) and its executor, candidates and ranking |
| `maker/finderanchor.py` | the anchor solver (pure) |
| `maker/prefs.py` | `<data root>/prefs.json` |
| `maker/static/finder.js`, `maker/static/strings.js` | the finder view; the string table |

`server.Handler` becomes `class Handler(finderapi.FinderMixin, http.server.BaseHTTPRequestHandler)`; the new patterns
join `_ROUTES`, the byte GETs `_HOST_CHECKED`.

### F1.1: Fixtures

Spec 13 "Synthetic fixtures" (1), (1b), (1c), (2), (3), (3b), (6), (7); the windows fixture. Size M. Depends: F0.8.

**Files:** Modify `maker/test/finderfx.py`; Create `maker/test/test_finderfx.py`.

**Interfaces** (each writes into a folder and returns `{"path", "facts"}`, `facts` the offsets and readings the
fixture placed, so tests assert against them):
- `com_file(folder)` (1): seeded noise, 8x16 ASCII at a known offset, zero padding, an 8x4x4 set whose `sets` hit
  ties a row apart; name `NKPLIKE.COM`.
- `set_after_zero_block(folder)` (1b): an 8x4x4 set at 0xFE0, the first 4 KiB otherwise zero.
- `ways_in(folder)` (1c): an `MZ` file holding a font, a 4,096-byte ROM, a `.PFT`-named file holding a font, an FNT
  with no openable size.
- `ks_dense_in_file(folder, invert=False)` (2), `ks_grid_strips(folder)` (3: 512 KiB, 128 x 128 strips, blank rows),
  `font_24_at_2_mod_3(folder)` (3b).
- `packed(folder)` (6): zlib of (1); files starting with RAR / 7z / gzip magic.
- `hostile(folder)` (7): over 64 MiB (sparse), a symlink, a FIFO, zero length, a recipe with unknown keys, absurd
  numbers, a 10 MB gfx string; `truncate_later(path)` / `rewrite_later(path)` helpers.
- `windows_32mib(folder)`: sparse 32 MiB with an 8x4x4 set and an 8x16 ASCII font each across the 16 MiB boundary and
  a 40-glyph 16x16 run with 20 glyphs on each side (built by seeks; the file is sparse).
- `bytes_patterns(path) -> [bytes]`: 16-byte windows of the fixture's font areas, for privacy greps.

- [ ] **Step 1: Tests** (`test_finderfx.py`): each fixture's `facts` hold when read back with `binscan.decode`;
  `windows_32mib` allocates under 1 MiB on disk (`st_blocks`); the sources are only `svf/` faces and seeded noise.
- [ ] **Step 2: Implement, run PASS.** **Step 3: Commit** `finderfx: the finder's synthetic fixtures (finder phase 1)`.

Gate: G-maker.

### F1.2: `finderio`: opening rule, bounded reads, hashing

Spec 7.2 "Opening a file", 7.4 "Bounded reads". Size S. Depends: F0.1.

**Files:** Create `maker/finderio.py`, `maker/test/test_finderio.py`.

**Interfaces:**
- `ident_of(abs_path) -> [dev, ino, size, mtime_ns]` (through the opening rule).
- `class FileChanged(Exception)`; `class NotRegular(Exception)`.
- `pread(abs_path, ident, offset, length, cap) -> bytes`: opens by the rule, compares `fstat` with `ident`
  (`FileChanged`), refuses `length > cap` (`ValueError`), `os.pread` loop to `length` or EOF, closes. Never `mmap`.
- `hashes(abs_path, ident, chunk=1 << 20, stop=None) -> (sha256, sha1)`: the same rule; compares `fstat` again at the
  end (`FileChanged`); `stop` an `Event` checked each chunk.
- `class Hasher`: one daemon thread; `submit(key, abs_path, ident, on_done)`; `wait(key, timeout) -> bool`.

- [ ] **Step 1: Tests:** symlink, FIFO (returns within 2 s), directory → `NotRegular`; a file truncated, rewritten
  with the same size (mtime differs), replaced by rename → `FileChanged`; `pread` past EOF returns the bytes there are;
  a 64 MiB sparse file hashed in under the test's 30 s; `test_no_mmap` (`mmap.mmap` patched to raise: every function
  still works).
- [ ] **Step 2: Implement, PASS.** **Step 3: Commit** `finderio: the finder's opening rule, bounded pread and
  background hashing (finder phase 1)`.

Gate: G-maker.

### F1.3: Sessions: create, get, delete; identity across detect

Spec 7.2 "Session", 7.3 (POST, GET, DELETE), 7.4 (files 16, a file 64 MiB, sessions 8), 13 "Identity", "Server" (token
and Host on every endpoint). Size L. Depends: F1.2, F0.10.

**Files:**
- Create: `maker/finder.py`, `maker/finderapi.py`, `maker/test/test_finder_session.py`
- Modify: `maker/server.py` (`Handler` bases, `_ROUTES`, `_HOST_CHECKED`, `_job_detect` re-binds sessions)

**Interfaces:**
- `finder.create(job, font_ids, sources) -> (n, session)`: each font id must be an entry of the job that is a single
  readable file (not a licence / list / refused entry) — else 422 `finder.invalid`; the job must be local and
  `detected` (409 `finder.state`); at most 8 sessions (409 `finder.limit`), 16 files, 64 MiB a file (422
  `finder.limit`, naming the file and the limit). Session ids `n1`, `n2`, ... never reused within a job. Files get ids
  `a`, `b`, ... in request order. Session:
  `{"files": {fid: {"root": <root path>, "path", "member": None, "size", "ident": [...], "sha256": None, "sha1": None,
  "missing": False}}, "analysis": {"state": "idle"}, "candidates": [], "marks": {"items": [], "faces": []},
  "applied": [], "library_ids": {}, "trial": {"state": "idle"}, "notices": []}`.
- `finder.rebind(job, fonts, roots)`: called inside `_job_detect`'s transition: each file's `(root path, path)` looked
  up among the new entries; gone → `missing: True` (marks kept, not applied).
- `finder.abs_of(job, session, fid, sources) -> (abs_path, ident)` via `Sources.abs_of`; `missing` → 409
  `finder.missing`.
- `finder.scratch(store, job, n) -> str` = `.svf-maker-<id>/finder/<n>/` (made through the job's files directory
  rules); `finder.lock(job_id, n) -> threading.Lock` (module table like `_PREVIEW_LOCKS`).
- `FinderMixin._finder_create`, `_finder_get`, `_finder_delete` for `POST /api/jobs/<id>/finder`, `GET` / `DELETE
  /api/jobs/<id>/finder/<n>` (`<n>` matches `n[1-9][0-9]{0,2}`). Errors via `_HttpError(status, message, {"code": ..})`.
  `GET` answers the session (files without `ident`), analysis and trial state, candidates, marks, notices.
- Every finder request sets `server.touched[job]`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_create_get_delete(self):              # fixture (1): 200 {"finder": "n1"}; GET files a: size, no sha256 yet
def test_needs_token_local_and_detected(self):   # no token 403; upload job 409 finder.state; foreign Host on GET 403
def test_limits(self):                         # 9th session, 17 files, a 64 MiB + 1 sparse file -> codes
def test_identity_across_detect(self):         # spec 13 Identity through the API: add earlier file, remove one, reorder
    # roots, POST detect each time: GET shows files bound to the same (root path, path); removed -> missing
def test_session_on_korean_comma_path(self):   # Review Focus 4
def test_no_source_bytes_in_job_json(self):    # bytes_patterns(fixture) not in job.json
def test_errors_have_codes(self):              # every non-2xx JSON body has "code"
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `finder: sessions on a detected local job, bound by stable identity across detect (finder
  phase 1)`.

Gate: G-maker.

### F1.4: The finder runner and the lifecycle

Spec 7.2 "Scratch" bullets, 13 "Lifecycle", Review Focus 3. Size M. Depends: F1.3.

**Files:**
- Create: `maker/finderrun.py`, `maker/test/test_finder_lifecycle.py`
- Modify: `maker/preview.py` (`run_bounded(argv, cwd, timeout, env=None, on_start=None)`: `on_start(proc)` after
  registration), `maker/server.py` (`_sweep_idle` skips a job with a running finder tool; `_sweep_locks` also takes
  the job's finder session locks; `_job_run` and `_job_settings` answer 409 `finder.busy`; `_job_delete` and
  `Worker.stop` paths kill finder tools), `maker/jobs.py` (`_finish_local` keeps working: the scratch goes with the
  files directory)

**Interfaces:**
- `finderrun.run(job_id, n, argv, cwd, timeout) -> CompletedProcess` (raises `TimeoutExpired`, `Cancelled`): through
  `preview.run_bounded` with `on_start` recording the process under `(job_id, n)`.
- `finderrun.cancel(job_id, n=None) -> int` (SIGKILL the process groups; `Cancelled` in their callers).
- `finderrun.busy(job_id) -> bool`.
- `finder.ensure(store, job, n, what) -> path`: makes a scratch artefact again when it is gone (phase 1: the entropy
  file of F1.7 and the trial folder), under the session lock.
- A finder request answers 409 `finder.state` while the job's run is queued or running.

- [ ] **Step 1: Write the failing tests:**

```python
def test_idle_sweep_skips_running_tool(self):    # a stub tool sleeping 30 s via finderrun.run; _sweep_idle(now+2h): kept
def test_sweep_after_tool_rebuilds(self):         # tool done, sweep: scratch gone; next GET render works (F1.5 later:
                                                  # here ensure() rebuilds the entropy file)
def test_run_and_settings_during_tool_409(self):  # finder.busy
def test_finder_request_during_run_409(self):
def test_server_stop_kills_tool(self):            # SubprocessLocalBase: stop the server; tools.pids empty, pid gone
def test_delete_session_during_tool(self):        # Review Focus 3: DELETE finder/n1 while the stub runs: killed, the
                                                  # scratch removed, no traceback in the server's stderr
def test_job_delete_during_tool(self):
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `finder: one bounded runner for finder tools; sweeps, run and settings respect them; stop and
  delete kill them (finder phase 1)`.

Gate: G-maker.

### F1.5: Render and the overview map

Spec 5.1 "Grid", "Long-strip mode", "Offset steps", 7.1, 7.3 `render`, `map`, 7.4 render limits, Review Focus 5.
Size M. Depends: F1.3, F0.4.

**Files:** Modify `maker/finder.py`, `maker/finderapi.py`, `maker/server.py` (`_ROUTES`, `_HOST_CHECKED`); Create
`maker/test/test_finder_render.py`.

**Interfaces:**
- `finder.parse_reading(query) -> dict`: `offset` 0 .. size, `glyph` `WxH` 1..1024, `stride` 1 .. 2^26, `order`,
  `lsb`, `invert`, `count` 1..4096 (default as `binscan.py render`), `cols` 1..64, `view` `ink` | `text`; `gfx`,
  `bg`, `fg`, `view=pens` → 400 `render.unsupported` (phase 2); out of range → 400 `render.bounds`; canvas `cols * W`
  and rows `* H` within 4096 and 4,000,000 pixels → else the count is clamped and `X-Finder-Count` says so.
- `GET .../finder/<n>/render?region=<file id>&...` → `image/png` from `binscan.grid_png`, or `text/plain` from
  `binscan.render_text`; headers `X-Finder-Count` (glyphs drawn before the region ends), `Cache-Control: no-store`.
  Reads `(count - 1) * stride + footprint` bytes by `finderio.pread`. Two at a time (a semaphore across the server);
  a third answers 429 `render.busy`.
- `GET .../finder/<n>/map?region=<file id>` → PNG, one column a block, 16 rows, grey = `255 - round(entropy * 28)`;
  block = `max(4096, ceil(size / 4096))` bytes (at most 4,096 columns); header `X-Finder-Block`. The entropy is computed
  once per file into the scratch (`entropy-<fid>.bin`, one byte a block = `round(e * 31)`) and rebuilt by `ensure`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_png_equals_decode(self):          # fixture (1) at the ASCII offset: PNG pixels == binscan.decode
def test_every_order_and_flag(self):       # strips / cols / bytecols, lsb, invert: same check
def test_bounds_before_allocation(self):   # glyph 2000x2000, count 5000, cols 65, offset > size -> 400 render.bounds;
                                           # tracemalloc peak under 1 MiB for each refused request
def test_long_strip_clamped(self):         # glyph 64x512 count 16 cols 16 -> count clamped to fit 4096 wide
def test_render_at_the_end(self):          # Review Focus 5: offset size-3; a file shorter than one glyph; count past end
def test_429_third_render(self):           # two renders held on a barrier: the third gets 429 render.busy
def test_text_view(self):                  # equals binscan.py render's text for the same reading
def test_file_changed_409(self):           # truncate between two renders -> 409 finder.changed; server answers next GET
def test_map_columns_and_no_store(self):
def test_redraw_time_recorded(self):       # prints ms for 256 glyphs 8x16 and 16x16 (target 100 ms, not gated here)
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `finder: in-process render of a reading as a gapless PNG or text, and the overview map
  (finder phase 1)`.

Gate: G-maker.

### F1.6: The analysis plan (pure)

Spec 6 (stages 0-2, windows, coarse and fine, ranking), 13 "Units" (candidate ranking), "Windows". Size M. Depends:
F0.3.

**Files:** Create `maker/finderscan.py` (pure part), `maker/test/test_finderscan.py`.

**Interfaces:**
- `Scan = namedtuple("Scan", "name stage args start length priority")`; `args` the binscan argv after the file.
- `scan_windows(size, span, cap=binscan.MAX_SCAN) -> [(start, length)]`: windows of at most `cap`, each overlapping the
  next by `span - 1`.
- `runs_windows(entropy, block, size, glyph_bytes) -> [(start, length)]`: blocks at 7.5 bits or more left out; each
  window widened by one glyph on each side; windows less than 64 KiB apart joined; then cut by `scan_windows`.
- `coarse_phases(w, h, order) -> list | None`: rows `list(range(ceil(w / 8)))`; `strips`, `cols`, `bytecols` → None
  (every phase, windows of at most 1 MiB, until F1.17 records better sets: `COARSE_MEASURED = {}` is where they go).
- `plan(size, entropy, block) -> [Scan]` in priority order: stage 1 `ascii` at 16, 14, 8, plain and inverted; `sets`
  8,4,4 at 16x16 and 24x24 (`--glyph 24x24`), plain and inverted, plus the other set counts `binscan` knows (10,4,4;
  6,2,1 at 16x16); stage 2 `runs` 16x16 rows, 16x16 strips, 8x16, 24x24 rows, 8x8, each coarse then (added by
  `fine_scans`) fine. Every scan with `--json`.
- `fine_scans(coarse_runs, w, h, order, gb) -> [Scan]`: all phases `--around` each run.
- `join_runs(results, gb, min_inked=32) -> [run]`: fragments of one phase (`offset % gb`) that meet are joined
  (edge runs included), then `--min` and binscan's overlap choice (longest inked first) are applied; deduplicated by
  `(offset, reading)`.
- `candidates(stage0, results) -> [candidate]` and `rank(cands) -> [candidate]` (at most 200). A candidate `{id, region,
  kind, offset, reading, count, score, why, ties, suggest}`; `kind` one of `library`, `signature`, `sets`, `ascii`,
  `run`, `sets-tie`, `near`; ranking order exactly: library match, size signature, single `sets` hit, `ascii` with a
  low edge count (edge ascending), runs by inked count (descending), tied `sets`, near matches. `why`: a list of
  `[word, number]` pairs (`["seam", 0.91]`, `["edge", 0]`, `["inked", 214]`); `suggest`: `{"as": "raw-set" | "english"
  | "ks-dense" | "ks-grid", ...}` (an 8x4x4 hit at 16 px suggests `raw-set` `844` 11,520; 2,350 or more 16x16 glyphs
  suggest `ks-dense`).

- [ ] **Step 1: Write the failing tests:**

```python
def test_windows_overlap_by_span_minus_one(self):
def test_runs_windows_keep_blank_blocks(self):   # entropy 0 blocks stay; 7.6 bits blocks go; joins under 64 KiB
def test_coarse_phases(self):                    # 8 -> [0]; 16 -> [0, 1]; 24 -> [0, 1, 2]; strips -> None
def test_join_edge_runs(self):                   # 20 + 20 glyph fragments of one phase across a window edge -> one run
                                                 # of 40 at its absolute offset; two phases do not join
def test_dedupe_across_windows(self):
def test_ranking_order(self):                    # one candidate of each kind, shuffled -> the spec's order
def test_why_has_no_bytes(self):                 # every why value is a word from WHY_WORDS or a number
def test_cap_200(self):
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `finderscan: the analysis plan, windows, coarse and fine phases, run joining and ranking
  (finder phase 1)`.

Gate: G-maker.

### F1.7: The analysis: executor, `analyse`, `cancel`, candidates

Spec 5 step 3, 6 (budget, "not scanned"), 7.3 `analyse`, `cancel`, 13 "Windows", "Server" (budgets kill tools),
Review Focus 2. Size L. Depends: F1.4, F1.6, F1.1.

**Files:** Modify `maker/finderscan.py` (executor), `maker/finderapi.py`, `maker/finder.py`; Create
`maker/test/test_finder_analysis.py`.

**Interfaces:**
- `finderscan.stage0(abs_path, ident, size, library) -> dict`: `size`, `kind_info` (first 0x60 bytes by `pread`),
  `signatures`, the entropy file (F1.5), the library match (`recipe.match` over the session's files with
  `recipe.combined`); a packed file (`kind_info.packed` or `archive`, or entropy of 7.5 bits or more on 95 % of the
  blocks) sets `"packed": true` and the analysis stops after stage 0 with the notice `finder.packed`.
- `finderscan.Analysis(job_id, n, fid, budget_s=60, scan_s=20, start=0, length=None, only=None)`: a thread; runs
  `plan` then `fine_scans` through `finderrun.run(..., timeout=min(scan_s, remaining))`; parses each `--json`; after
  each scan updates the session under its lock (`analysis.done`, `analysis.not_scanned` = `[{"scan": name,
  "why": "budget" | "timeout" | "cancelled"}]`, `candidates`).
- `POST .../analyse {"region": fid, "budget_s": 1..300, "start", "length", "scan": null | name}` → 202; 409
  `finder.state` when one runs. `POST .../cancel` stops the analysis (and the trial, F1.10).
- At server start, a session whose `analysis.state` is `running` becomes `interrupted` (in `make_server`, after the
  store loads; `_sweep_idle` is not involved).

- [ ] **Step 1: Write the failing tests:**

```python
def test_fixture_1_candidates(self):       # the 8x16 English and the tied 8x4x4 set are the top two, ties drawn as one row
def test_fixture_1b_set_after_zero_block(self):
def test_fixture_2_dense_plain_and_inverted(self):
def test_fixture_3_grid_strips(self):      # a 16x16 strips run covering the grid with its blank rows
def test_fixture_3b_24_at_2_mod_3(self):
def test_packed_and_archives(self):        # fixture (6): packed, analysis stops after stage 0 with finder.packed
def test_windows_32mib(self):              # heavy: each placed font found once at its absolute offset
def test_budget_kills_and_lists_not_scanned(self):   # budget_s 1 on fixture (3): not_scanned non-empty, no pid left
def test_cancel(self):
def test_restart_marks_running_analysis_interrupted(self):   # Review Focus 2 (SubprocessLocalBase: SIGKILL the server
                                                             # mid-scan, restart: state interrupted, analyse works)
def test_candidates_hold_no_bytes(self):   # bytes_patterns not in job.json, nor in the server log
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `finder: the analysis (stages 0-2) in a budget, cancellable, its candidates ranked (finder
  phase 1)`.

Gate: G-maker (the 32 MiB test under `heavy`).

### F1.8: Anchors

Spec 5.4, 7.3 `anchor`, 13 "Units" (anchors). Size S. Depends: F1.3.

**Files:** Create `maker/finderanchor.py`, `maker/test/test_finderanchor.py`; Modify `maker/finderapi.py`.

**Interfaces:**
- `class AnchorError(ValueError)` with `code` (`anchor.range`, `anchor.pitch`, `anchor.no_grid`, `anchor.conflict`)
  and `pair` (the anchor that conflicts, or None).
- `solve(kind, anchors, region_glyphs, pitch=None, chars="ks-hangul") -> dict`; `anchors` a list of `(index, char)`.
  - `english` → `{"first": code - index}`; 0..255 else `anchor.range`; every anchor agrees, else `anchor.conflict`.
  - `ks-dense` → `{"start": index - place}` (place = the char's index in `rawcarve.ks_codes(chars)`); negative, or
    `start + len(codes) > region_glyphs` → `anchor.range`.
  - `ks-grid` → `{"grid": [L0, T0, PITCH]}`: `PITCH` = `pitch`, or from two anchors on different lead bytes
    `(i2 - i1 - (t2 - t1)) / (l2 - l1)`, a whole number of at least 94 (else `anchor.pitch`); one anchor and no pitch →
    `anchor.pitch`. `K = lead * PITCH + trail - index`; the one `(L0, T0)` with `L0 * PITCH + T0 = K`, `0 <= L0, T0
    <= 255`, `T0 <= 0xA1` and `T0 + PITCH - 1 >= 0xFE`, and `L0 <= ` the lowest lead of `chars` (else
    `anchor.no_grid`); every further anchor checked (`anchor.conflict`, naming it).
  - A char is mapped to its KS code by `char.encode("euc-kr")`; a char outside `chars` → `anchor.range`.
- `expected_chars(kind, solved, start_index, n=16) -> [str | None]`: the characters the mapping expects under the next
  16 glyphs (the page draws them).
- `POST .../anchor {"reading", "offset", "region", "as", "pitch", "anchors": [{"glyph", "char"}]}` → solved, or 422
  with the code.

- [ ] **Step 1: Write the failing tests:**

```python
def test_vga_example(self):    # strips, pitch 128, glyph 6177 = "가" -> grid [128, 128, 128]
    self.assertEqual(solve("ks-grid", [(6177, "가")], 16384, pitch=128)["grid"], [0x80, 0x80, 128])
def test_one_anchor_without_pitch_refused(self):
def test_two_grids_agree_then_differ(self):   # grid A (pitch 94) and grid B (pitch 128) share an anchor; the second
                                              # anchor (another lead) decides which
def test_pitch_not_whole_or_small(self):
def test_conflict_names_the_pair(self):
def test_english_and_dense(self):
def test_endpoint_codes(self):
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `finder: anchors for English, KS dense and KS grid
  (finder phase 1)`.

Gate: G-maker.

### F1.9: Marks, session recipes, apply

Spec 5.3 (phase-1 rows), 7.3 `marks`, `recipe` (GET), `apply`, `DELETE` (un-applies), 8.1 "Apply", 13 "Session
recipes" (`apply` during hashing), Review Focus 1. Size L. Depends: F1.3, F0.10.

**Files:** Modify `maker/finder.py`, `maker/finderapi.py`, `maker/recipe.py` (raw-set reading refusals carry
`code="mark.reading"`); Create `maker/test/test_finder_marks.py`.

**Interfaces:**
- `PUT .../marks {"items": [...], "faces": [...]}`: 9.4 item and face objects; an item's `region` is a session file
  id; kinds `raw-set`, `english` (reading `[8, H]`, H 8..16), `ks-dense`, `ks-grid` only (others 422 `mark.invalid`,
  "not in this version"); at most 64 items; item ids at most 39 characters (so `found-<n>-<item>` fits the 48 of the
  id rule). Validated by building the session recipes with placeholder hashes (`"0" * 64`) through
  `recipe.validate`; a `RecipeError` answers 422 with its `code`.
- `finder.session_recipes(job, n, session) -> [rec]`: one recipe a Hangul item that some face names (by `hangul` or
  through `from`); `id` `found-<n>-<item>`; `title` `{"en": "found: <item> in <file name>", "ko": "찾음: <file name>의
  <item>"}`; `files` the session files the recipe's items read (`name` the base name, `size`, `sha256`); `items` the
  Hangul item and the English items its faces name; `faces` at most one precomposed and one jamo. Needs every file's
  hash: waits through `finderio.Hasher.wait` up to 10 s, then 409 `finder.hashing`.
- `GET .../recipe` → `{"recipes": [...]}`.
- `POST .../apply` → the job: `session["applied"] = [{"item", "recipe"}]` replaced wholesale, then the entries rebuilt
  as `POST detect` does (`detect.session_entries`, steps and result cleared, settings kept by key); 409 `finder.state`
  unless `detected`.
- `DELETE` of a session removes its applied entries the same way.

- [ ] **Step 1: Write the failing tests:**

```python
def test_marks_validated(self):            # 621 read as rows -> 422 mark.reading; kind compose -> mark.invalid
def test_recipe_of_marks(self):            # fixture (1): English + 844 set, faces dos raw + johab844 -> one recipe
def test_apply_adds_entries_keeps_host(self):
def test_apply_twice_and_reapply_after_edit(self):   # Review Focus 1: same marks twice -> one entry; edit the English
    # offset and apply -> one entry, its settings kept, the face uses the new offset
def test_apply_waits_for_hashes(self):     # Hasher slowed by a patch: 409 finder.hashing within 10 s, then 200
def test_delete_unapplies(self):
def test_applied_entry_runs(self):         # select, run: faces written, RECIPE-found-n1-set.json in build-<id>/
def test_86box_pair_two_files_one_session(self):   # synthetic pair: grid mark on the ROM + English on the BIOS (spec 15.1)
```

- [ ] **Steps 2-4: FAIL, implement, PASS.**
- [ ] **Step 5: Commit** `finder: marks, session recipes and apply (finder phase 1)`.

Gate: G-maker.

### F1.10: Trial

Spec 5 step 7, 7.3 `trial`, 7.4 trial limits, 8.3 "One planner", 8.5, 13 "Equivalence" (trial == run), "Server"
(cancel of a trial). Size M. Depends: F1.9, F1.4.

**Files:** Modify `maker/finder.py`, `maker/finderapi.py`; Create `maker/test/test_finder_trial.py`.

**Interfaces:**
- `POST .../trial` → 202; a thread runs, for each face of `session_recipes`, `recipe.face_plan(rec, face, files,
  {"work": <scratch>/trial/<NAME>/, "out": <scratch>/trial/<NAME>.svf, "base": ...}, range-2350, tools)` through
  `finderrun.run` (60 s a command, 300 s in all). Numbers in `session["trial"]["faces"][NAME]`: `recipe.sample_numbers`,
  the `--check` line (the last stdout line of a `jamoset.py ... --check` command), and for a fit `quality.measure(face,
  precomposed.svf, None, size)`'s IoU. `state`: `running`, `done`, `failed` (the tool's last stderr line), `cancelled`,
  `interrupted` (at server start, as F1.7).
- `GET .../trial/<NAME>.svf` (`NAME` `[A-Z0-9]{1,8}`): the built face, `no-store`, host-checked.

- [ ] **Step 1: Write the failing tests:**

```python
def test_trial_equals_run(self):           # fixture (1) marks: trial SVF bytes == the app run's == recipe run's
def test_numbers(self):                    # glyph count, check line, width/ascent/descent, ink as sample_numbers
def test_cancel_kills(self):
def test_budget(self):                     # per-command timeout patched to 0.1 s: failed with "timeout", no pid left
def test_restart_marks_trial_interrupted(self):   # Review Focus 2
def test_svf_get_no_store_and_host(self):
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `finder: the trial, through the run's planner, with
  the sample-line numbers (finder phase 1)`.

Gate: G-maker.

### F1.11: The user library over HTTP; save, load, prefill

Spec 5 step 2 ("opens prefilled"), 9 (save to my recipes), 7.3 `/api/recipes`, `PUT .../recipe`, 9.2 states, 13
"Server" (recipe endpoints, two jobs with the same names), "Equivalence" (saved recipe known in a new job, one byte
`similar`, a missing file `part of a set`). Size M. Depends: F1.9, F0.9.

**Files:** Modify `maker/finderapi.py`, `maker/finder.py`; Create `maker/test/test_finder_library.py`.

**Interfaces:**
- `GET /api/recipes` → `{"recipes": [{"id", "source": "builtin" | "user", "title", "files": [{"name", "size"}]}],
  "errors": [...]}`; local mode and token only (403 otherwise), no job.
- `PUT /api/recipes/<rid> {"recipe": rec, "replace": false}`: `<rid>` matches `recipe.ID_RE` and equals `rec["id"]`
  (400 otherwise); `recipe.save_user` (codes `recipe.builtin`, `recipe.exists`, `recipe.limit`).
  `DELETE /api/recipes/<rid>`: user recipes only (403 `recipe.builtin`).
- `POST /api/jobs/<id>/finder/<n>/save {"item": <hangul item>, "name": null | <id>, "replace": false}` → `{"id": rid}`
  (design call: the session save; see the differences table). Under one process-wide library lock: when the session
  has no `library_ids[item]`, allocate the user's `name` when free, else `<stem of the host file's name, lower-cased,
  [^a-z0-9-] → ->-<first 8 hex of its sha256>`, cut to 48, with `-2`, `-3`, ... while taken (built-in or user);
  remember it in `session["library_ids"]`. Writing to an existing id is allowed only for the session that allocated
  it or with `replace` (409 `recipe.exists`).
- `PUT .../finder/<n>/recipe {"recipe": rec}`: validated (256 KiB, the 9.4 bounds); items of kinds this version marks;
  each recipe file is bound to a session file by size and SHA-256 (unbound → notice, its items kept unbound); prefills
  `marks`. `POST .../finder` accepts `"recipe": <id>` to open a known or similar entry prefilled (similar: `expect`
  dropped, a notice "unverified").

- [ ] **Step 1: Write the failing tests:**

```python
def test_put_recipe_rules(self):           # "..", a built-in id, a mismatched id, the 501st, existing without replace
def test_endpoints_need_local_and_token(self):   # /api/recipes and /api/prefs: 403 without token or in upload mode
def test_two_jobs_same_session_names(self):   # both save item "hangul" of session n1: two files, two ids; both known in
                                              # a third job; a second save from each job updates its own file only
def test_saved_known_similar_part(self):   # known in a new job; one byte changed -> similar; a file missing -> part
def test_load_recipe_prefills_marks(self):
def test_open_known_entry_prefilled(self):
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `finder: the user library over HTTP, the session's
  save with an allocated library id, recipes loaded into a session (finder phase 1)`.

Gate: G-maker.

### F1.12: Strings and the language preference

Spec 11, 7.3 `/api/prefs`, 13 "Page" (every key in `en` and `ko`; no user-visible literal in `finder.js`; the
language survives a restart), "Server" (`PUT /api/prefs` rules, a kill between write and replace). Size M. Depends:
F1.3.

**Files:**
- Create: `maker/prefs.py`, `maker/static/strings.js`, `maker/test/test_finder_strings.py`
- Modify: `maker/server.py` (`GET` / `PUT /api/prefs`, `STATIC_TYPES` unchanged), `maker/static/index.html` (a
  language select in the top bar: `<select id="lang">` with `English` / `한국어`), `maker/static/maker.js` (loads the
  preference: `GET /api/prefs`, else `navigator.language` `ko*` → `ko`; `PUT` on change)

**Interfaces:**
- `prefs.read(data_root) -> {"lang": "en" | "ko" | None}` (None when absent or invalid); `prefs.write(data_root,
  body: bytes)`: at most 1,024 bytes, exactly `{"lang": "en"}` or `{"lang": "ko"}` (any other key or value →
  `ValueError` → 400 `prefs.invalid`); temp file in the data root + `os.replace`.
- `strings.js`: `export const STRINGS = {en: {...}, ko: {...}}`; `export function t(key, values = {})` (`{name}`
  placeholders; a missing key returns the key and logs once); `export function setLang(lang)`, `export function
  lang()`. Keys are namespaced `finder.*`, `codes.*` (one per error code of the Global Constraints, so the page shows
  its own sentence for each `code`).

- [ ] **Step 1: Write the failing tests:**

```python
def test_prefs_rules(self):                # other key, other value, 1,025 bytes -> 400; GET absent -> {"lang": null}
def test_prefs_kill_between_write_and_replace(self):   # os.replace patched to raise: the old file stays, no temp left
def test_every_key_in_both_languages(self):   # node: Object.keys(STRINGS.en) == Object.keys(STRINGS.ko), none empty
def test_every_code_has_a_string(self):     # each code string in finderapi.py / finder*.py has codes.<code>
def test_language_survives_restart(self):   # PUT ko, restart the server, GET -> ko
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `maker: the finder's string table (EN, KO) and the
  language preference in prefs.json (finder phase 1)`.

Gate: G-maker.

### F1.13: The page: finder view, ways in, files and candidates

Spec 5 steps 1-4, 5.1 (layout), 12 (candidate list is buttons; focus returns), 16 (narrowest window). Size M.
Depends: F1.7, F1.12, F1.11.

**Files:**
- Create: `maker/static/finder.js`, `maker/test/test_finder_page.py`
- Modify: `maker/static/index.html` (`<section id="finder" hidden>` with `#finder-files`, `#finder-candidates`,
  `#finder-viewer`, `#finder-reading`, `#finder-marks`, `#finder-trial`, `#finder-actions`), `maker/static/maker.js`
  (fonts table: "look inside" (`finder.lookInside`) on rows where `source_kind == "other"` or `format in ("fnt",
  "fon")` with no sizes, single-file, not a licence / list / unreadable entry; several ticked open together; "open in
  the finder" in the row menu of `dos-raw`, `eng`, `ks-raw` entries and of `known` / `similar` recipe entries; the
  sources panel's "find a font in a file..." = choose files + detect + open the finder on what was picked; the finder
  is offered only when `/api/caps` says `local`), `maker/static/style.css` (three columns; below 1,000 px the
  reading column folds under the viewer; no horizontal scroll at 800 px)

**Interfaces:**
- `finder.js` exports `openFinder(jobId, fontIds, {recipe})`, `closeFinder()` (focus returns to the button that opened
  it); polls `GET .../finder/<n>` every 1 s while an analysis or trial runs.
- Candidate rows: `<button class="cand" data-cand="<id>">` with a thumbnail (`render` of the first 32 glyphs),
  `why` as words from `strings.js` and numbers, the suggestion; tied offsets as one row with each tie's thumbnail.
  "not scanned: <scan>" rows with a "scan it" button (`analyse` with `scan`). A packed file shows the packed sentence
  and the manual viewer only.

- [ ] **Step 1: Write the failing page tests** (`pagedrive.mjs`, the pattern of `test_page_dom.py`):

```python
def test_look_inside_offered_on_the_ways_in(self):   # fixture (1c): MZ, .PFT, FNT without sizes: "look inside";
                                                     # 4,096-byte ROM: "open in the finder" in the row menu
def test_open_shows_two_candidates(self):    # fixture (1): the English and the tied set rows appear, ties side by side
def test_packed_file(self):
def test_not_scanned_row_and_button(self):
def test_back_returns_focus(self):
def test_layout_folds_at_narrow_width(self):   # viewport 800x700: scrollWidth == clientWidth; reading below viewer
def test_ko_strings(self):                   # lang ko: the candidate header is the KO string
def test_finder_js_has_no_literal(self):     # spec 13 "Page": no quoted text of 2+ letters in finder.js outside t("...")
                                             # keys, class names, ids and the test's allowlist
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `maker page: the finder view, its ways in, files
  and candidates (finder phase 1)`.

Gate: G-maker. Resolves spec 16 "the narrowest window" for the layout.

### F1.14: The page: viewer and reading panel

Spec 5 step 5, 5.1 (grid, long strip, offset steps, address line, "show as text", overview strip), 7.1 (debounce 30
ms, numbered requests, latest wins). Size L. Depends: F1.13, F1.5.

**Files:** Modify `maker/static/finder.js`, `maker/static/index.html`, `maker/static/style.css`; Test
`maker/test/test_finder_page.py` (class `ViewerTest`).

**Interfaces:**
- Reading object (the same as a mark's and `render`'s query): `{glyph: [W, H], order, stride, lsb, invert}` plus
  `offset`, `cols`, `scale` (1..8), `count`.
- The grid `<img>` is the server's PNG scaled by CSS `image-rendering: pixelated`; cell lines, index labels, hover
  (glyph index and offset) and the selection are drawn by the page on a canvas above it from the geometry.
- Offset steps: byte, stored row (`ceil(W / 8)` bytes; `strips` one byte), glyph (stride), page (`count * stride`);
  first / last. Address line: `.COM` load address (offset + 0x100) from `kind_info.load`; MZ header size.
- Long-strip toggle: glyph `W x 512`, 16 columns, at most 16 glyphs (the server clamps); clicking two rows sets H to
  their distance and leaves long-strip mode.
- "Show as text": a read-only `<textarea>` filled from `view=text` of the selection, its content selected.
- Overview strip: the `map` PNG; the current window and the marks outlined with their numbers; a click seeks.

- [ ] **Step 1: Write the failing page tests:**

```python
def test_redraw_follows_every_parameter(self):   # change offset, W, H, stride, order, lsb, invert: the img src query
                                                 # equals the reading; only the latest answer is shown (requests slowed)
def test_offset_steps_and_address(self):         # NKPLIKE.COM: address = offset + 0x100
def test_long_strip_two_clicks_set_height(self):
def test_show_as_text_selected(self):            # textarea value == render text, selectionEnd == length
def test_overview_click_seeks(self):
def test_429_is_retried_quietly(self):
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `maker page: the finder's viewer and reading panel,
  long strips and the text view (finder phase 1)`.

Gate: G-maker.

### F1.15: The page: marks, anchors, trial, apply, save and load

Spec 5 steps 6-9, 5.3, 5.4 (the page's sentences after one grid anchor; expected characters under the next 16 glyphs),
8.3 (the page shows the first face of each kind). Size L. Depends: F1.14, F1.8, F1.10, F1.11.

**Files:** Modify `maker/static/finder.js`, `maker/static/index.html`, `maker/static/style.css`; Test
`maker/test/test_finder_page.py` (class `MarkFlowTest`).

**Interfaces:**
- Mark panel: kind select (`raw-set` with the layouts of `recipe.RAW_STORAGE` that a phase-1 reading allows, `english
  8xH`, `ks-dense`, `ks-grid` with presets `0xA1,0xA1,94` and `0x80,0x80,128`); choosing a raw layout sets the
  viewer to the layout's storage; ascent field (default empty = the tool's); "add mark" → `PUT marks` (the whole
  list); face pairing per Hangul mark (routes by item kind: `raw-set` → `dos raw`, `johab844`; KS → `bdfface`, `bdfface
  + from-svf fit`) with its English marks.
- Anchor input: clicking a glyph and typing one character posts `anchor`; after one grid anchor without pitch the
  sentence `finder.anchor.one_more`; the expected characters under the next 16 glyphs (`expected_chars`).
- Trial line: "try", progress, cancel, the sample line drawn with `svfview.js` from `trial/<NAME>.svf`, the numbers.
- "apply to the job" → `POST apply`, then back to the job with the fonts table showing "found: ...".
- "save recipe" → `POST .../save` (a name field, the replace question on `recipe.exists`); "load recipe or spec..." →
  a file input read as text → `PUT .../recipe` (spec files are phase 3: a compose spec answers `mark.invalid` and the
  page says so).

- [ ] **Step 1: Write the failing page tests:**

```python
def test_fixture_1_mark_try_apply_run(self):   # spec 13 "Page": pick, mark both, try (sample drawn; its ink equals
                                               # sample_numbers of the same face), apply, run: faces in svf/
def test_grid_anchor_one_more_then_confirmed(self):   # fixture (3)
def test_raw_layout_sets_storage(self):          # 621 -> strips 16x16
def test_save_and_load(self):                    # save, reload page, load the file: marks prefilled
def test_422_shows_code_sentence(self):          # mark.reading in EN and KO
```

- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `maker page: marks, anchors, trial, apply, save and
  load in the finder (finder phase 1)`.

Gate: G-maker, G-e2e (page flow).

### F1.16: Keyboard and status lines

Spec 12. Size M. Depends: F1.15.

**Files:** Modify `maker/static/finder.js`, `maker/static/index.html`, `maker/static/style.css`,
`maker/static/strings.js`; Test `maker/test/test_finder_page.py` (class `KeyboardTest`).

**Interfaces:** keys in the grid: arrows move the selection by glyph, `Shift` extends, `Alt` + left / right the offset
by a byte, `Alt` + up / down by a stored row, `PageUp` / `PageDown` by a page, `[` / `]` glyph width, `{` / `}` its
height, `?` the shortcut list; each is also a labelled button. The grid's `aria-label` states the reading (`t
("finder.grid.label", {n, w, h, offset, order})`); one `role="status"` line for the hovered or focused glyph (index,
offset, the mapped character of a mark) and one for analysis / trial progress, "preparing" and "not scanned"; scale
control up to 8; focus always visible.

- [ ] **Step 1: Write the failing page tests:** `test_keyboard_only_flow` (fixture (1): open, pick, select, mark,
  try, apply with keys only), `test_status_lines`, `test_aria_label_states_reading`, `test_shortcut_list`.
- [ ] **Steps 2-4: FAIL, implement, PASS.** **Step 5: Commit** `maker page: the finder from the keyboard, its status
  lines (finder phase 1)`.

Gate: G-maker, G-e2e.

### F1.17: Performance record and the coarse phases of strips, cols, bytecols

Spec 6 ("the builder measures it on the fixtures"), 7.1 targets, 13 "Performance", 16 risks 1 and 2. Size S.
Depends: F1.7, F1.5.

**Files:** Create `maker/test/finderperf.py` (a script, not a unittest: `python3 maker/test/finderperf.py --out
FILE`); Modify `maker/finderscan.py` (`COARSE_MEASURED`); Modify `docs/desktop-app.md` section 13 (the numbers);
Test `maker/test/test_finderscan.py` (`test_measured_coarse_sets_find_the_fixtures`).

- [ ] **Step 1:** Run under `~/.local/bin/heavy` on fixtures of 38 KiB, 512 KiB and 8 MiB: the redraw of 256 glyphs
  (8x16, 16x16; target 100 ms) through `GET render`; each stage-1 and stage-2 scan's time; for `strips`, `cols` and
  `bytecols` at 16x16 and 8x16, the smallest phase set that finds every font placed at every phase of one glyph.
- [ ] **Step 2:** Write the measured sets into `COARSE_MEASURED` (or leave the every-phase fallback for an order
  whose smallest set is all phases) and add the test that the sets find the fixtures.
- [ ] **Step 3: Commit** `finder: performance record; measured coarse phase sets (finder phase 1)` with the table in
  the commit message and in `docs/desktop-app.md` section 13.

Gate: G-maker. Resolves spec 16 risks 1 and 2 (measured, recorded; a missed target is recorded, not hidden).

### F1.18: End to end: page flow, desktop step, server-wide checks

Spec 13 "Server" (every endpoint with and without token and with a foreign Host; no source byte anywhere; nothing
written outside the output folder), "Desktop", 16 risk 4 (show as text without a permission). Size M. Depends: F1.16,
F0.12.

**Files:** Create `maker/test/test_finder_server.py`; Modify `desktop/test/e2e.js` (one step); Modify
`maker/test/test_frozen.py` (a finder session through the frozen server: create, analyse fixture (1), render).

- [ ] **Step 1: Write the tests:**

```python
def test_every_finder_endpoint_token_and_host(self):   # table of every route of FinderMixin: no token 403, foreign
                                                       # Host 403 on state changers and byte GETs, no-store on byte GETs
def test_no_fixture_bytes_anywhere(self):    # full flow on fixture (1): bytes_patterns absent from job.json, log.md,
                                             # BUILD.md, RECIPE json, every error body, the server's stderr
def test_nothing_outside_output_folder(self):   # walk the data root and the output folder before/after
```

  `desktop/test/e2e.js` step `finder`: open fixture (1) in a local job, apply a built-in test recipe through the
  finder's load, run, faces written; open "show as text": the textarea is filled, no permission request is logged,
  and `webContents.copy()` puts its text on `clipboard.readText()` in the main process (the system copy works
  without a permission).
- [ ] **Step 2: Run** G-maker, G-e2e, G-frozen; fix what fails in the owning module.
- [ ] **Step 3: Commit** `finder: end-to-end checks (server-wide, page flow, desktop step) (finder phase 1)`.

Gate: G-maker, G-e2e, G-frozen, G-appimage. Resolves spec 16 risk 4.

### F1.19: Documentation

Spec 11 "Docs", 8.4 (`docs/desktop-app.md` section 6). Size M. Depends: F1.18.

**Files:** Modify `docs/desktop-app.md` + `docs/desktop-app.ko.md` (chapter "Finding a font inside a file" / "파일
안에서 글꼴 찾기": ways in, the view, reading parameters, marks, anchors, trial, apply, recipes, limits, what phase 1
does not read; section 6 lists `RECIPE-<id>.json`; section 13 the performance record of F1.17), `docs/recipes.md` +
`docs/recipes.ko.md` (one paragraph from "Finding a font inside a program or data file, with Claude" to the app, and
`recipe check / run / list`), `maker/README.md` + `maker/README.ko.md` (the new modules and test files),
`docs/tools.md` + `docs/tools.ko.md` if a tool option changed after F0.4.

- [ ] **Step 1:** Write both languages; the Korean is a translation of the English, same headings order.
- [ ] **Step 2:** `python3 -m unittest discover -s tools -p test_tools_doc.py` passes; every code name in the chapter
  exists (`grep` each against the tree).
- [ ] **Step 3: Commit** `docs: the finder in the desktop app (EN, KO), recipes on the command line (finder phase 1)`.

Gate: G-tools.

---

## Task summary

| Id | Title | Depends | Size |
|---|---|---|---|
| F0.1 | Opening rule in binscan, rawcarve, nkpspec | - | S |
| F0.2 | binscan `--json`, archive kinds, 94 x 94 wording, `render_text` | F0.1 | M |
| F0.3 | binscan `runs --phases / --around`, edge runs | F0.2 | M |
| F0.4 | binscan `grid_png` | F0.3 | S |
| F0.5 | Recipe English placement; `finderfx` encoder | - | M |
| F0.6 | Direct fits, `dest`, `johab844` route, optional files | F0.5 | M |
| F0.7 | `expect` at run by canonical file; 8.5 numbers | F0.6 | M |
| F0.8 | Readings oracle | F0.7 | M |
| F0.9 | User library, `recipe.resolve`, detection over both | F0.6 | M |
| F0.10 | Session recipes as appended entries | F0.9 | L |
| F0.11 | `RECIPE-<id>.json`, `recipe check / run / list`, equivalence | F0.7, F0.10 | L |
| F0.12 | Sidecar packaging | F0.4, F0.11 | M |
| F1.1 | Fixtures | F0.8 | M |
| F1.2 | `finderio` | F0.1 | S |
| F1.3 | Sessions, identity across detect | F1.2, F0.10 | L |
| F1.4 | Finder runner, lifecycle | F1.3 | M |
| F1.5 | Render and overview map | F1.3, F0.4 | M |
| F1.6 | Analysis plan (pure) | F0.3 | M |
| F1.7 | Analysis executor, candidates | F1.4, F1.6, F1.1 | L |
| F1.8 | Anchors | F1.3 | S |
| F1.9 | Marks, session recipes, apply | F1.3, F0.10 | L |
| F1.10 | Trial | F1.9, F1.4 | M |
| F1.11 | User library over HTTP, save, load, prefill | F1.9, F0.9 | M |
| F1.12 | Strings, language preference | F1.3 | M |
| F1.13 | Page: view, ways in, candidates | F1.7, F1.12, F1.11 | M |
| F1.14 | Page: viewer, reading panel | F1.13, F1.5 | L |
| F1.15 | Page: marks, anchors, trial, apply, save / load | F1.14, F1.8, F1.10, F1.11 | L |
| F1.16 | Keyboard, status lines | F1.15 | M |
| F1.17 | Performance record, coarse phases | F1.7, F1.5 | S |
| F1.18 | End to end | F1.16, F0.12 | M |
| F1.19 | Documentation | F1.18 | M |

Parallel lanes: F0.1-F0.4 (tools) beside F0.5-F0.11 (recipes); in phase 1, F1.2, F1.6 and F1.12 can start together,
F1.5 / F1.8 / F1.9 after F1.3.

## Spec section 16 risks and where each is settled

| Risk (spec 16) | Task |
|---|---|
| Redraw targets and `runs` cost are estimates | F0.4 and F1.5 record times; F1.17 records the 38 KiB / 512 KiB / 8 MiB table; a missed target stays recorded (the tile fallback is phase 2) |
| Coarse phase sets of `strips`, `cols`, `bytecols` unknown | F1.6 ships the every-phase fallback; F1.17 measures and sets them |
| KS-order score | phase 2; not in this plan |
| "Show as text" copy without a permission | F1.18 desktop step |
| `region` line over 512 bytes | phase-1 commands: F0.11 (notes use basenames); `region` is phase 2 |
| Section 8 read on an unmerged branch; session entries not prototyped | this plan reads `fa632ac`; F0.10 builds and tests the entries |
| `621` storage = `strips` read, not run | F0.8 |
| mame-roms diverged | merged at `9ddfe90`; checked while writing this plan |
| Nothing run in the app; narrowest window | F1.13 (narrow layout test), F1.15 / F1.18 (the flow in Chrome and Electron) |
