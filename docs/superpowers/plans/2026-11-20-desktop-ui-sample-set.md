# Desktop app: the sample set through the UI - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close card t_30b843b8 (goal t_afb4689b, criterion 2): in **both** passes of the Electron e2e (dev sidecar and
packaged layout) the app converts the OFL sample set and a synthetic Mac/HWP/BDF sample **through its UI** in local
mode (inputs read in place, faces written into the chosen output folder), and the written tree passes
`tools/facecheck.py` and `web/mkindex.py --check`, with the inputs unchanged and nothing else written.

**Architecture:** One Python test helper, `maker/test/uisample.py`, owns the sample: it builds the synthetic inputs at
test time, holds the selection table (what the UI must set per font) and the exact expected output, and checks an output
folder (`make` and `check` subcommands, JSON on stdout). Its own unit test, `maker/test/test_uisample.py`, runs the same
table through the HTTP API in-process (the ground truth for the expectations) and proves every check fails on a
mutation. `desktop/test/e2e.js` gains one step per pass, `sample set`, that calls `uisample.py make`, drives the page
with the stubbed dialogs and the page's own controls (no settings `PUT` by `fetch`), waits for the run, then calls
`uisample.py check`.

**Tech Stack:** Python 3 `unittest` (maker suite), Node + Electron 45 under xvfb (`desktop/test/e2e.js`), the existing
fixture builders (`maker/test/{fixtures,inputfx,macfx,e2efx,inputkinds}.py`).

**Base:** worktree `/home/thkim/work/svf-fonts-open-wt/fu-uisample`, branch `fu-uisample` from `main` eab664a.

**Revision 2** (after the plan reviews of 61a5146; the disposition table is at the end): HangulTalk 1.0 added; the
expected tree re-derived from a measured API run (33 files, 14 steps, 10 faces); M1-M4, the bytecode rule and L1-L7
written into the tasks.

## Global Constraints

- Test code and docs only: `maker/test/uisample.py` (new), `maker/test/test_uisample.py` (new), `desktop/test/e2e.js`,
  `docs/maker-desktop.md`. **No change** to `maker/*.py`, `maker/static/*`, `tools/`, `c/`, `desktop/main.js`,
  `desktop/preload.js`, `desktop/lib/`, and none to `maker/test/e2efx.py` / `inputkinds.py` (reuse, do not edit). If the
  UI cannot do something the table needs, stop and report (a product bug for its own card); never work around it with a
  `fetch` that writes.
- Inputs: OFL files of this repository (`ttf/`) read in place, and synthetic files built by the existing fixture
  builders. No proprietary data, no download.
- Scratch only under `$HOME/work/tmp`: `export TMP_DIR=$HOME/work/tmp/svf-uis TMPDIR=$HOME/work/tmp/svf-uis`
  (`mkdir -p` it; keep it short, Chrome's socket path limit). Never `/tmp`.
- Every Chrome/Electron run: `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy ...`.
  `build-appimage.sh` takes the lock itself: run it under `~/.local/bin/heavy` only, never under `flock`.
- **Interpreter flags.** The helper runs as `python3 -B -P` (`-P`, not `-I`: on this host fontTools is in the user site,
  which `-I` drops; `-B`: its imports of `maker/test/*`, `maker/*` and `tools/*` write no `__pycache__`). Its own
  subprocesses are started with `sys.executable -B ...` (its `facecheck.py` / `mkindex.py` calls add `-B` to `-I`).
  The calls reused unchanged from `inputkinds` / `e2efx` run `-I` scripts that import only the standard library and
  their own file, so they write no bytecode either; Task 1 test 1 asserts no new file (no `__pycache__`) appears under
  `maker/`, `tools/`, `web/` or `ttf/` after `make` + `check`.
- Commit messages end with `(t_30b843b8)` and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.

### Prerequisites (once, Task 0)

`cd desktop && npm ci && node node_modules/electron/install.js && cd ..`; `bash maker/build-wasm.sh` (G2 counts
assume the built module); `~/.local/bin/heavy bash desktop/build/build-appimage.sh` (stages
`desktop/build/out/{sidecar,repo}` for the packaged pass; every CHECK ok).

### Gates

- **G1** `git diff --exit-code 587dfb5 -- c/src c/include` - exit 0.
- **G2** `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
  - base `Ran 1144 ... OK (skipped=25)` with the built WASM; after Task 1 **1155**, skipped 25.
- **G4** `cd desktop && npm test` - green, count unchanged (56); then
  `~/.local/bin/heavy bash desktop/build/build-appimage.sh` - every `CHECK` ok.
- **G5** e2e both passes + lifecycle:
  `S=$PWD/desktop/build/out; SVF_MAKER_SIDECAR=$S/sidecar/svf-maker-sidecar/svf-maker-sidecar SVF_MAKER_STAGED_REPO=$S/repo flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh`
  - today `E2E DONE pass=31 fail=0` (1 load-failure case + 15 steps x 2 passes); after Task 2 **`pass=33 fail=0`**
  (one `sample set` step per pass). Then
  `cd desktop && flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy node --test test/lifecycle.test.js` - 4/4.
  For red/green iterations a dev-only run is enough: the same command without the two `SVF_MAKER_*` variables (the
  packaged pass is skipped then).

## The sample (definition)

### The OFL sample set: 4 fonts of `ttf/`, read in place (accepted by the controller)

| Key | Picked as (dialog) | Font | UI settings | Expected face |
|---|---|---|---|---|
| `neodgm` | folder `ttf/neodgm` | `neodgm.ttf` (pixel, GSUB jamo) | precomposed, 16, bpp 1, dest dos | `svf/dos/NEODU16.SVF` |
| `nanum` | folder `ttf/nanumgothic` | `NanumGothic-Bold.ttf` (untick `NanumGothic-Regular.ttf`) | precomposed, 17, bpp 2, dest dos | `svf/dos/NANUM17A.SVF` |
| `gowun` | folder `ttf/gowunbatang` | `GowunBatang-Bold.ttf` | precomposed, 17, bpp 2, dest dos, preset `dos-u-2bpp` | `svf/dos/GOWUN17A.SVF`, **byte-equal to `svf/dos/GBATB17.SVF`** |
| `caveat` | folder `ttf/caveat` | `Caveat-VF.ttf` (variable, Latin only) | precomposed, 16, bpp 1, dest dos, instance `Bold` (`{"wght": 700}`) | `svf/dos/CAVEA16.SVF` |

Why these four, not all 13 files of `ttf/`: they cover every outline route the maker has for OFL fonts (plain TTF,
GSUB-jamo composite, a preset, a variable instance with its `instancer` source step) and both bpp; neodgm 16/1 and
NanumGothic-Bold 17/2 are the "OFL sample set" `test_frozen.py` already uses for frozen-vs-source byte equality;
GowunBatang with `dos-u-2bpp` at 17 px reproduces a shipped face byte for byte (mirrored from `PresetAcceptanceTest`).
All of `ttf/` would add 9 near-identical mkfont runs and name clashes (Galmuri x3, Nanum x3).

### The synthetic sample: built by `uisample.py make DIR` under `DIR/in/` (OFL-derived or invented bytes only)

| Key | Picked as | Files (builder) | UI settings | Expected face |
|---|---|---|---|---|
| `seoul` (Mac 7.1 fbit) | folder `in/mac` | `Seoul12.rsrc` (`macfx.fbit3_fork(1)`), `InputBackSupport.rsrc` (`macfx.htbl_fork(1)`), `Suitcase.rsrc` (`macfx.suitcase(12)`), `LICENSE.txt` (`fixtures.SIL_LICENCE`) | Seoul12: jamo, dest jamo-extra, HTBL table = InputBackSupport, latin companion = Suitcase | `svf/jamo-extra/SEOU12J.SVF` |
| `munjo` (Mac HangulTalk 1.0) | folder `in/v1` | `Munjo16.rsrc` (`macfx.fbit1_fork()`, the fbit with its fdef), `LICENSE.txt` | jamo, dest jamo-extra (everything else default) | `svf/jamo-extra/MUNJ16J.SVF` |
| `dfont` (Mac dfont) | **file** `in/dfont/Synth.dfont` (choose files) | `inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())])`, no licence | tick it (no licence: off by default), precomposed, 16, bpp 1, dest dos | `svf/dos/SYNTH16.SVF` |
| `hwp` (HWP) | folder `in/hwp` | `HAN24.FNT` (`inputfx.dos844_24()`), `ASCII.PFT` (`inputfx.pft_eng()`), `HANGUL24.PFT` (`macfx.hangul_pft()`), `LICENSE.txt` | HAN24: DOS layout 844, jamo, dest jamo-extra, latin companion = ASCII.PFT; HANGUL24.PFT listed with the "HWP Hangul .PFT: not read" label and no usable tick | `svf/jamo-extra/HAN224J.SVF` |
| `ksc` (BDF) | folder `in/bdf` | `ksc.bdf` (KSC5601 BDF of the 2350 NEODG16 syllables: `fixtures._bdf` over `inputfx.ksc_glyphs_from_neodg()`, as `test_ksc_bdf_jamo_set_end_to_end`), `latin.bdf` (`inputfx.latin_bdf_from_neodg`), `LICENSE.txt` | ksc: precomposed, dest dos, latin companion = latin.bdf; untick latin.bdf | `svf/dos/KSC16.SVF` |
| `johab` (BDF) | same folder | `johab.bdf` (`fixtures._bdf(..., fixtures._johab_glyphs(), 16, 13, 3, "johab", (16, 16))`) | jamo, dest jamo-extra | `svf/jamo-extra/JOHA16J.SVF` |

`HAN24.FNT` + `ASCII.PFT` is the HWP input the repository reads (README "Local mode": HANGUL*.PFT is not read, ASCII.PFT
is the 12x24 companion of a 24 px DOS raw face); `HANGUL24.PFT` is there to show the UI lists it as not read (accepted
by the controller as the HWP sample).

`make` also writes `DIR/sample.json` (its stdout JSON, L1); `DIR/out/` is the output folder. `check` reads only
`DIR/out/` and the picked roots, so `sample.json`, `DIR/job.json` and `DIR/check/` are never part of a checked tree.

### The expected output (pinned in `uisample.EXPECTED`; measured, see below)

**33 files, 10 faces, from 14 steps**, and nothing else in the output folder (`<id>` = the job id):

- `svf/dos/` (17): `CAVEA16.SVF CAVEA.TXT OFLCAVEA.TXT GOWUN17A.SVF GOWUN.TXT OFLGOWUN.TXT KSC16.SVF KSC.TXT OFLKSC.TXT
  NANUM17A.SVF NANUM.TXT OFLNANUM.TXT NEODU16.SVF NEODU.TXT LICNEODU.TXT SYNTH16.SVF SYNTH.TXT`
- `svf/jamo-extra/` (12): `HAN224J.SVF HAN24.TXT OFLHAN24.TXT JOHA16J.SVF JOHAB.TXT OFLJOHAB.TXT MUNJ16J.SVF MUNJO.TXT
  OFLMUNJO.TXT SEOU12J.SVF SEOUL.TXT OFLSEOUL.TXT`
- `build-<id>/` (4): `BUILD.md LICENCES.tsv.lines FAMILIES.tsv.lines FACES.TSV.lines`

17 + 12 + 4 = 33. The faces (10): NEODU16, NANUM17A, GOWUN17A, CAVEA16, SYNTH16, KSC16 (dos); SEOU12J, MUNJ16J, HAN224J,
JOHA16J (jamo-extra). `EXPECTED` is written from the measured run, not typed from this list; Task 1 test 2 asserts
`len(EXPECTED) == 33` and the API run equals it.

The 14 steps (asserted in `test_uisample.py`, name -> tools): NEODU16, NANUM17A, GOWUN17A `mkfont.py`+`svf2to3.py`;
Caveat `source` (`python3 -m` instancer) then CAVEA16 `mkfont.py`+`svf2to3.py`; Seoul12 `source` (`macfbit3.py`),
InputBackSupport `source` (`srcprep.py`), SEOU12J `macfbit_svf.py`; HAN224J `jamoset.py`; JOHA16J `jamoset.py`; KSC16
`bdfface.py`; MUNJ16J `jamoset.py` (layout `mac-fbit-45sets`, no source step: a raw fork); Synth.dfont `source`
(`macsfnt.py extract`, `unicode`) then SYNTH16 `mkfont.py`+`svf2to3.py`.

Measured (2026-11-20, source mode, in-process `e2efx.Server` local job, this host): detect 4.1 s; run 4.9-7.7 s;
GOWUN17A identical to GBATB17; on the tree without HangulTalk 1.0, facecheck tree 0.3 s, standalone `mkindex --check`
0.4 s, every face draws (CAVEA16 with `A` only).

## The checks (`uisample.check(sample, out_dir, job, same_as=None)` -> list of failure lines, each naming its file)

1. **Expected files and only them:** the set of files under `out_dir` equals `EXPECTED` with `build-<id>/` for the
   job's id, and equals `job["result"]["files"]`; every expected `.SVF` is some step's `written`; no `.svf-maker-*`
   left (the caller waits up to 10 s for the sweep first, as `LocalEndToEndTest` does). When the job has no `result`
   yet (or no id), report `job has no result` plus one `missing <path>` line per absent file instead of raising (L4).
2. **facecheck:** `inputkinds._facecheck` (manifest + verify on a temp git copy of `out_dir/svf`, every SVF
   `parse_svfn(...).version == 3`), called on a minimal `unittest.TestCase` shim.
3. **mkindex:** `e2efx.merge_check(..., base_repo=False)` (the standalone tree: `LICENCES/FAMILIES` from the
   `build-<id>/*.lines`, a FACES.TSV row for every jamo face, `web/mkindex.py --check`), scratch under `DIR/check/`.
4. **Pins and ink:** `GOWUN17A.SVF` == `svf/dos/GBATB17.SVF` bytes (hard, the only per-face byte pin); every face
   draws ink: `e2efx.assert_draws` for faces that have U+AC00, and for a Latin-only face (CAVEA16) a helper-local
   variant that draws `A` with `svfline` and fails on a blank (L2; `e2efx.py` is not edited).
5. **Inputs unchanged:** sha256 of every file under every picked root (the four `ttf/` folders, `in/mac`, `in/v1`,
   `in/hwp`, `in/bdf`, and the dfont file) equals the map `make` printed, file set included.
6. **(e2e, packaged pass) Cross-pass `--same-as DEV_OUT`:** byte equality with the dev pass's faces. **Hard** for the
   pure-Python faces `SEOU12J`, `HAN224J`, `JOHA16J`, `KSC16`, `MUNJ16J` (a difference is a failure line). For the
   outline faces `NEODU16`, `NANUM17A`, `GOWUN17A`, `CAVEA16`, `SYNTH16` a difference is a **note**, not a failure
   (the dev pass renders with the host's Pillow/FreeType, the packaged one with the pinned wheels; D8 caveat): `check`
   returns it in `"notes"` and e2e.js prints `E2E NOTE sample set: <face> differs from the dev pass (host Pillow vs
   pinned wheels, D8)`. GOWUN17A is still held to GBATB17 by check 4 in both passes.

The shim's `fail`/`assert*` raise; `check` runs each of the six checks in its own `try` and catches **any**
`Exception` (L3), turning it into one failure line `<check>: <type>: <first line>`, so one broken check never hides
the others.

## The helper interface (what `e2e.js` calls)

- `python3 -B -P maker/test/uisample.py make DIR` -> `DIR/in/...` built (DIR must be new or empty), `DIR/out/` made
  empty, `DIR/sample.json` written; stdout the same JSON:
  `{"dialog": [{"button": "choose-folder"|"choose-files", "path": ABS}...], "output": ABS DIR/out, "fonts": {key: {"root_path": ABS, "path": REL, "ui": {...}}}, "untick": [REL...], "not_read": [REL...], "faces": 10, "inputs": {ABS: sha256}}`.
  `dialog` in pick order: `ttf/neodgm`, `ttf/nanumgothic`, `ttf/gowunbatang`, `ttf/caveat`, `in/mac`, `in/v1`,
  `in/hwp`, `in/bdf` (choose-folder, 8), then `in/dfont/Synth.dfont` (choose-files, 1). `ui` holds exactly what the
  page must set: `kinds`, `sizes`, `bpp`, `dest`, `preset`, `instance`, `dos_layout`, `htbl` / `latin` (the
  companion's relative path; the page maps path -> font id).
- `python3 -B -P maker/test/uisample.py check DIR JOB_JSON [--same-as OTHER_OUT]` -> exit 0 and
  `{"ok": true, "notes": [...]}`, or exit 1 and `{"ok": false, "failures": [...], "notes": [...]}`.
  `JOB_JSON` holds `GET /api/jobs/<id>` (written by e2e.js to `DIR/job.json`).
- **The `/tmp` refusal lives in the CLI only (M4):** `main()` exits 2 with `uisample: refusing a directory under /tmp`
  when `DIR` resolves under `/tmp`. The library functions (`make`, `check`, `apply_ui`) never refuse; the unit tests
  pass them an explicit base `$HOME/work/tmp/svf-uisample-test-<pid>` (made and removed by the test, the way
  `test_page_dom.py` builds its long path), so the maker suite runs whatever TMPDIR is. Temp git copies and merge
  scratch go under `DIR/check/`, so nothing follows TMPDIR at all.

## How the e2e drives the UI (one step `T('sample set')` per pass, after `flow`, before `open-folder`)

1. Assert `TMP` does not resolve under `/tmp` (M4: "not /tmp", not "under `$HOME/work/tmp`"). Run
   `PY -B -P REPO/maker/test/uisample.py make TMP/<pass>/sample` with `util.promisify(execFile)` (async, L6; env
   `{...process.env, TMPDIR: TMP}`, timeout 60 s), `PY = process.env.SVF_E2E_PYTHON || 'python3'`; parse the JSON.
2. `handle.win.loadURL(origin + '/')`. Push the dialog answers in order (`{canceled: false, filePaths: [p]}` per
   `dialog` entry, then the output folder). In the page click `#choose-folder` / `#choose-files` once per entry and
   wait each time until `#source-roots` shows that path; then click `#choose-output` and wait until
   **`#output-shown` textContent equals the full output path** (M1; `#sources-panel` always holds the button text, so
   it proves nothing). Then `#detect-local`; if `#ack` is visible click `#ack-ok`; wait for `#fonts tr[data-font]`.
   Assert `dialogQueue.length === 0`.
3. Map relative path -> font id with a **read-only** `GET /api/jobs/<id>`. In the page, through the controls only:
   one page-side helper `choose(control, value)` that **first asserts the control exists and is enabled and, for a
   `<select>`, that an `<option value=value>` exists and is not `disabled`** (M2: the e2e only does what a user can),
   then sets `.value`/`.checked` and dispatches `input` + `change` (as `test_ui_smoke.py`'s `fire`). Used for every
   change: the row tick `input.selected` (on for each sample font, off for every other row with a tick:
   `NanumGothic-Regular.ttf`, `latin.bdf`); the row's `input.override`; inside `tr.override[data-for=<fid>]`
   `select.ov-kinds` (e.g. value `precomposed` / `jamo`), `input.ov-sizes`, `select.ov-bpp` (`1` / `2`), the dest and
   preset selects (`aria-label` `dest for ...`, `preset for ...`), `select[data-field=instance]`
   (`{"wght":700}` as JSON), `select[data-field=htbl_companion]`, the latin companion select (`aria-label`
   `latin companion for ...`); in the main row `select.dos-layout` (`844`). Assert the `HANGUL24.PFT` row exists, its
   label contains `not read`, and its `input.selected` is disabled.
4. Click `#save`; wait until `GET /api/jobs/<id>` shows, for every font, `selected` as intended and the `ui` values (the
   UI wrote them). Click `#run`; wait (page timeout 180 s) for `#state` to contain `written to`, then for **10**
   `canvas[data-step][data-drawn="1"]` (one per face step). (The page has no ink attribute on its canvases; L7's
   optional `dataset.ink` check would need a page change and is not done here: blank faces are caught by check 4.)
5. Wait (<= 10 s) for no `.svf-maker-*` in the output folder; write the job JSON to `DIR/job.json`; run
   `uisample.py check` (async, with `--same-as TMP/dev/sample/out` in the packaged pass); print every note as
   `E2E NOTE sample set: ...`; on exit 1 fail the step with the first three failure lines. Print
   `E2E NOTE sample set <pass> <s> s` (the step's wall time).
6. Log privacy (existing step): add `TMP/<pass>/sample` and `REPO/ttf/neodgm` to the paths that must not be in the shell
   log (the shell logs path counts only). If the dev log carries the checkout path for another reason, keep the
   sample path and report the `ttf/` one instead of dropping the step's assertion silently.

## Time budget

- Measured in source mode: detect 4.1 s, run 4.9-7.7 s (14 steps), checks ~1.5 s, `make` ~2 s (the KSC BDF from
  NEODG16 dominates).
- Expected per pass with the page (source previews of 12 fonts, 10 result canvases): dev ~30-45 s, packaged ~45-75 s
  (each frozen `run-tool` spawn adds start-up; about 18 tool runs). Hard bound of the step: 300 s (`waitUntil`), page
  waits 180 s.
- Effect on G5: about +1.5 to +2 min on the whole e2e. Task 0 records today's wall time of G5, Task 2 the new one; both
  go into the report and into `docs/maker-desktop.md` "Measured". A pass over 120 s is reported, not hidden by raising
  the bounds.

## Tasks

### Task 0: baseline (no commit)

- [ ] Prerequisites above. Record `git rev-parse HEAD` (eab664a), G1, G2 (`Ran 1144`, skipped 25), G4, and G5 with
  `/usr/bin/time -f %e` around it (`pass=31 fail=0`, lifecycle 4/4, wall time).

### Task 1: `maker/test/uisample.py` + `maker/test/test_uisample.py` (TDD)

**Files:** create `maker/test/uisample.py`, `maker/test/test_uisample.py`.

- [ ] **Step 1: tests first.** `test_uisample.py`, 11 tests. Base dir `$HOME/work/tmp/svf-uisample-test-<pid>`
  (explicit, removed in `tearDownClass`; M4). One class-level `make` + API run in `setUpClass`; every mutation works on
  a `shutil.copytree` copy of its output (and, for inputs, on a second `make` dir), so the class run stays clean.
  1. `test_make_builds_the_synthetic_tree` - the files and sizes of the tables above (`in/v1/Munjo16.rsrc` included),
     `sample.json` equal to the returned JSON, 9 `dialog` entries in the order above, every path absolute and
     existing, the four OFL roots under `REPO/ttf`; nothing written outside `DIR` (snapshot of `maker/`, `tools/`, `web/`
     and `REPO/ttf` before/after: no new file, no `__pycache__` from the helper's subprocesses); `make` into a non-empty
     dir raises.
  2. `test_api_run_writes_exactly_the_expected_tree` - an in-process `e2efx.Server(..., token=localfx.TOKEN)` local
     job: sources = the `dialog` paths, detect, settings from the **same `ui` table** (`uisample.apply_ui(job)`, the
     API twin of the page script), run, `wait_done`; `len(EXPECTED) == 33`; `check()` returns no failure and no note;
     the 14 steps and their tools as listed above; 10 faces.
  3. `test_check_flags_a_missing_face` - delete `svf/jamo-extra/MUNJ16J.SVF`, `MUNJO.TXT`, `OFLMUNJO.TXT`: failures
     name each.
  4. `test_check_flags_an_extra_file` - add `svf/dos/STRAY.SVF` (a copy of a face): a failure names it.
  5. `test_check_flags_a_leftover_work_dir` - add `.svf-maker-<id>/x`.
  6. `test_check_flags_a_changed_input` - append a byte to `in/hwp/ASCII.PFT` of a second `make` dir: some failure line
     contains `ASCII.PFT` (L5).
  7. `test_check_flags_a_corrupt_face` - truncate `KSC16.SVF` to 100 bytes: the parse/facecheck failure names it.
  8. `test_check_flags_a_gbatb17_mismatch` - flip one byte past the header of `GOWUN17A.SVF`.
  9. `test_check_flags_a_blank_face` - zero the glyph bitmap bytes of `JOHA16J.SVF` so it still parses (find the
     bitmap range with `jamoset.parse_svfn`; assert the mutated file still parses as v3) and check reports it draws
     blank (L7).
  10. `test_check_flags_a_missing_faces_row` - drop `JOHA16J.SVF`'s row from `build-<id>/FACES.TSV.lines`: the
      mkindex check fails.
  11. `test_cli_make_and_check` - `python3 -B -P uisample.py make` / `check` as subprocesses: JSON shape, exit 0 on the
      class run's tree; exit 1 with a `failures` list on a mutated copy; a job JSON without `result` gives exit 1 with
      `job has no result` and `missing` lines, no traceback (L4); `--same-as` a tree whose `JOHA16J.SVF` differs ->
      exit 1, whose `NEODU16.SVF` differs -> exit 0 with a note naming it (M3); `make /tmp/x` -> exit 2 (M4, nothing
      created).
- [ ] **Step 2: run, expect FAIL** (`ModuleNotFoundError: No module named 'uisample'`):
  `cd maker/test && TMPDIR=$HOME/work/tmp/svf-uis python3 -B -m unittest test_uisample -v`.
- [ ] **Step 3: implement `uisample.py`.** `SAMPLE` (the two tables as data), `EXPECTED` (the 33 paths, `build-{id}/`
  templated, `HARD_SAME` / `NOTE_SAME` face sets for M3), `make(dir)`, `apply_ui(job)` (API twin; pure function over the
  detected job), `check(...)` (the six checks above, each in its own `try ... except Exception`), the Latin-only draw
  helper, and `main()` (CLI, the `/tmp` refusal, `sys.dont_write_bytecode = True`). Path setup as in `e2efx.py`
  (insert `TEST_DIR`, `MAKER_DIR`, `REPO/tools`).
- [ ] **Step 4: run, expect PASS** (the Step 2 command, 11 OK, under ~30 s). If the API run's tree differs from
  `EXPECTED`, stop and report the difference: the expected tree is a measurement.
- [ ] **Step 5:** G1, G2 (**1155**, skipped 25). Commit `maker test: the desktop UI sample set (OFL + synthetic
  Mac/HWP/BDF) with its expected tree and checks (t_30b843b8)`.

### Task 2: the `sample set` e2e step (dev and packaged)

**Files:** modify `desktop/test/e2e.js`.

- [ ] **Step 1: red - the step with checks, no UI drive.** Add `T('sample set')`: `make`, pick roots and output
  (with the M1 wait), detect, then directly `check` (no ticks, no run). Run G5 dev-only: expect
  `E2E FAIL dev: sample set ... job has no result ...` / `missing svf/dos/CAVEA16.SVF ...` and `pass=16 fail=1`
  (load-failure + 15 dev steps pass; packaged skipped).
- [ ] **Step 2: green - the UI drive** (steps 3-4 above, `choose()` with the M2 asserts), then the sweep wait and
  `check`. Run G5 dev-only: `pass=17 fail=0`.
- [ ] **Step 3: mutations prove the step bites (temporary edits, not committed; record each FAIL line in the report):**
  (a) skip ticking `Munjo16.rsrc` -> FAIL naming `MUNJ16J.SVF`; (b) after the run, truncate `KSC16.SVF` in the output
  folder before `check` -> FAIL naming it; (c) after the run, write `out/svf/dos/X.SVF` -> FAIL naming it;
  (d) choose a disabled option (e.g. `ov-bpp` `2` on `Seoul12.rsrc` if the page disables it, else any `<option>` value
  that does not exist) -> FAIL from `choose()` before anything is set (M2); (e) packaged pass only: flip one byte past
  the header of `JOHA16J.SVF` before `check` -> FAIL from `--same-as`; the same flip on `NEODU16.SVF` -> an `E2E NOTE`,
  step still PASS (M3). Revert; `git diff` shows only the committed step.
- [ ] **Step 4:** add the log-privacy paths (step 6 above). Full G5 (both passes): `pass=33 fail=0`, lifecycle 4/4,
  the packaged pass's `--same-as` check green (notes, if any, listed in the report). Record the per-pass
  `E2E NOTE sample set <pass> <s> s` lines and G5's wall time.
- [ ] **Step 5:** G1, G2 (1155), G4 (`npm test` 56/56; build-appimage every CHECK ok). Commit `desktop e2e: convert
  the OFL sample set and the synthetic Mac/HWP/BDF sample through the UI in both passes, facecheck + mkindex on the
  written tree (t_30b843b8)`.

### Task 3: docs and review

**Files:** modify `docs/maker-desktop.md` (a short "Sample set (e2e)" paragraph: the definition by reference to
`maker/test/uisample.py`, what is checked, the M3 note rule, the measured times; one row in "Measured").

- [ ] Commit `docs: the desktop sample-set e2e (t_30b843b8)`. Review (Opus + one independent lane, isolated) of the
  whole branch diff against eab664a; fixes go back to the implementer by resume; re-run G2 and G5 after fixes.
- [ ] Card evidence: `commit:<sha>` of the merge, `test:maker/test/test_uisample.py`, `test:desktop/test/e2e.js`.

## Decisions (controller, 2026-11-20)

- Q1: the HWP sample as defined (HAN24.FNT + ASCII.PFT, HANGUL24.PFT shown as not read) is accepted.
- Q2: the 4 `ttf/` files are the OFL sample set.
- Q3: no per-face sha256 pins except GOWUN17A == GBATB17.
- Q4: HangulTalk 1.0 is added (`in/v1`).
- M3: cross-pass equality hard for the pure-Python faces only; outline faces give a note (D8 Pillow caveat).

## Review disposition (plan reviews of 61a5146: Opus APPROVE WITH CHANGES, SOL REJECT)

| Finding | Source | Disposition |
|---|---|---|
| Add HangulTalk 1.0 | HIGH, both | Done: `in/v1/Munjo16.rsrc` + LICENSE.txt, jamo / jamo-extra; dialog 9 entries (`in/v1` after `in/mac`); faces 10, canvas wait 10; inputs roots include `in/v1`; step list with `jamoset.py` (mac-fbit-45sets, no source step); mutations 3 and e2e (a) use it; timings re-measured (run 4.9 s, 14 steps). |
| Expected count 30 vs listed 31 | HIGH, SOL | Re-derived from a measured API run with HangulTalk 1.0: 33 files (17 + 12 + 4), listed per folder with counts; `EXPECTED` is written from the measurement and test 2 asserts 33. (The old list was 30 = 17 + 9 + 4, as measured then; the count is now stated once, per folder, so it can be recounted.) |
| M1 vacuous output-folder wait | Opus | Done: wait for `#output-shown` textContent == the full output path. |
| M2 assert options exist / enabled | Opus | Done: one `choose()` that asserts control, option and not-disabled before setting; e2e mutation (d). |
| M3 cross-pass strictness | Opus, controller | Done as decided: hard for SEOU12J, HAN224J, JOHA16J, KSC16, MUNJ16J; note for NEODU16, NANUM17A, GOWUN17A, CAVEA16, SYNTH16; GBATB17 pin stays hard; tests 11 and e2e (e). |
| M4 `/tmp` refusal breaks the suite | Opus | Done: refusal in the CLI only; tests use an explicit `$HOME/work/tmp/...` base; e2e asserts "not /tmp". |
| No bytecode outside DIR | MEDIUM, SOL | Done: `python3 -B -P` for the helper, `-B` on its subprocesses / `sys.dont_write_bytecode`; test 1 asserts no new file under `maker/`, `tools/`, `web/`, `ttf/`. |
| L1 name the make result file | Opus | Done: `DIR/sample.json`, outside the checked tree. |
| L2 Latin-only draw variant | Opus | Done: helper-local, `e2efx.py` untouched. |
| L3 shim catches any Exception | Opus | Done: each check in its own `try ... except Exception`. |
| L4 job without result | Opus | Done: `job has no result` + `missing` lines; test 11; e2e red step. |
| L5 mutation 6 names ASCII.PFT | Opus | Done. |
| L6 async execFile | Opus | Done: `promisify(execFile)`. |
| L7 parses-but-blank mutation; canvas ink | Opus | Mutation done (test 9). `canvas.dataset.ink` is not done: the page sets no ink attribute and page code is out of scope; check 4 covers blank faces. |
