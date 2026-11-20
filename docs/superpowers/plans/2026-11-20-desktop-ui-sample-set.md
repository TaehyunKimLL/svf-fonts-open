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

## Global Constraints

- Test code and docs only: `maker/test/uisample.py` (new), `maker/test/test_uisample.py` (new), `desktop/test/e2e.js`,
  `docs/maker-desktop.md`. **No change** to `maker/*.py`, `maker/static/*`, `tools/`, `c/`, `desktop/main.js`,
  `desktop/preload.js`, `desktop/lib/`. If the UI cannot do something the table needs, stop and report (that is a
  product bug for its own card), do not work around it with a `fetch` that writes.
- Inputs: OFL files of this repository (`ttf/`) read in place, and synthetic files built by the existing fixture
  builders. No proprietary data, no download.
- Scratch only under `$HOME/work/tmp`: `export TMP_DIR=$HOME/work/tmp/svf-uis TMPDIR=$HOME/work/tmp/svf-uis`
  (`mkdir -p` it; keep it short, Chrome's socket path limit). Never `/tmp`.
- Every Chrome/Electron run: `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy ...`.
  `build-appimage.sh` takes the lock itself: run it under `~/.local/bin/heavy` only, never under `flock`.
- The helper runs as `python3 -P` (not `-I`: on this host fontTools is in the user site, which `-I` drops); it calls
  `facecheck.py` and `mkindex.py` with `sys.executable -I` as `inputkinds`/`e2efx` already do.
- Commit messages end with `(t_30b843b8)` and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.

### Prerequisites (once, Task 0)

`cd desktop && npm ci && node node_modules/electron/install.js && cd ..`; `bash maker/build-wasm.sh` (G2 counts
assume the built module); `~/.local/bin/heavy bash desktop/build/build-appimage.sh` (stages
`desktop/build/out/{sidecar,repo}` for the packaged pass; every CHECK ok).

### Gates

- **G1** `git diff --exit-code 587dfb5 -- c/src c/include` - exit 0.
- **G2** `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
  - base `Ran 1144 ... OK (skipped=25)` with the built WASM; after Task 1 **1154**, skipped 25.
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

### The OFL sample set: 4 fonts of `ttf/`, read in place

| Key | Picked as (dialog) | Font | UI settings | Expected face |
|---|---|---|---|---|
| `neodgm` | folder `ttf/neodgm` | `neodgm.ttf` (pixel, GSUB jamo) | precomposed, 16, bpp 1, dest dos | `svf/dos/NEODU16.SVF` |
| `nanum` | folder `ttf/nanumgothic` | `NanumGothic-Bold.ttf` (untick `NanumGothic-Regular.ttf`) | precomposed, 17, bpp 2, dest dos | `svf/dos/NANUM17A.SVF` |
| `gowun` | folder `ttf/gowunbatang` | `GowunBatang-Bold.ttf` | precomposed, 17, bpp 2, dest dos, preset `dos-u-2bpp` | `svf/dos/GOWUN17A.SVF`, **byte-equal to `svf/dos/GBATB17.SVF`** |
| `caveat` | folder `ttf/caveat` | `Caveat-VF.ttf` (variable, Latin only) | precomposed, 16, bpp 1, dest dos, instance `Bold` (`{"wght": 700}`) | `svf/dos/CAVEA16.SVF` |

Why these four, not all 13 files of `ttf/`: they cover every outline route the maker has for OFL fonts (plain TTF,
GSUB-jamo composite, a preset, a variable instance with its `instancer` source step) and both bpp; neodgm 16/1 and
NanumGothic-Bold 17/2 are the "OFL sample set" `test_frozen.py` already uses for frozen-vs-source byte equality; GowunBatang
with `dos-u-2bpp` at 17 px reproduces a shipped face byte for byte (the only absolute correctness pin a UI run can have,
mirrored from `PresetAcceptanceTest`). All of `ttf/` would add 9 near-identical mkfont runs and three name clashes
(Galmuri x3, Nanum x3) whose fix in the UI is renaming, not conversion. Measured (source mode, in-process, this host):
detect over these 4 folders plus the synthetic ones 4.1 s; the whole run 7.7 s (all of `ttf/`: detect 9.4 s alone).

### The synthetic sample: built by `uisample.py make DIR` under `DIR/in/` (OFL-derived or invented bytes only)

| Key | Picked as | Files (builder) | UI settings | Expected face |
|---|---|---|---|---|
| `seoul` (Mac fbit) | folder `in/mac` | `Seoul12.rsrc` (`macfx.fbit3_fork(1)`), `InputBackSupport.rsrc` (`macfx.htbl_fork(1)`), `Suitcase.rsrc` (`macfx.suitcase(12)`), `LICENSE.txt` (`fixtures.SIL_LICENCE`) | Seoul12: jamo, dest jamo-extra, HTBL table = InputBackSupport, latin companion = Suitcase | `svf/jamo-extra/SEOU12J.SVF` |
| `dfont` (Mac dfont) | **file** `in/dfont/Synth.dfont` (choose files) | `inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())])`, no licence | tick it (no licence: off by default), precomposed, 16, bpp 1, dest dos | `svf/dos/SYNTH16.SVF` |
| `hwp` (HWP) | folder `in/hwp` | `HAN24.FNT` (`inputfx.dos844_24()`), `ASCII.PFT` (`inputfx.pft_eng()`), `HANGUL24.PFT` (`macfx.hangul_pft()`), `LICENSE.txt` | HAN24: DOS layout 844, jamo, dest jamo-extra, latin companion = ASCII.PFT; HANGUL24.PFT listed with the "HWP Hangul .PFT: not read" label and no usable tick | `svf/jamo-extra/HAN224J.SVF` |
| `ksc` (BDF) | folder `in/bdf` | `ksc.bdf` (KSC5601 BDF of the 2350 NEODG16 syllables: `fixtures._bdf` over `inputfx.ksc_glyphs_from_neodg()`, as `test_ksc_bdf_jamo_set_end_to_end`), `latin.bdf` (`inputfx.latin_bdf_from_neodg`), `LICENSE.txt` | ksc: precomposed, dest dos, latin companion = latin.bdf; untick latin.bdf | `svf/dos/KSC16.SVF` |
| `johab` (BDF) | same folder | `johab.bdf` (`fixtures._bdf(..., fixtures._johab_glyphs(), 16, 13, 3, "johab", (16, 16))`) | jamo, dest jamo-extra | `svf/jamo-extra/JOHA16J.SVF` |

`HAN24.FNT` + `ASCII.PFT` is the HWP input the repository reads (README "Local mode": HANGUL*.PFT is not read, ASCII.PFT
is the 12x24 companion of a 24 px DOS raw face); `HANGUL24.PFT` is there to show the UI lists it as not read.

### The expected output (pinned in `uisample.EXPECTED`, measured with the API run above)

Exactly these 30 files and nothing else in the output folder (`<id>` = the job id):

- `svf/dos/`: `NEODU16.SVF NEODU.TXT LICNEODU.TXT NANUM17A.SVF NANUM.TXT OFLNANUM.TXT GOWUN17A.SVF GOWUN.TXT
  OFLGOWUN.TXT CAVEA16.SVF CAVEA.TXT OFLCAVEA.TXT SYNTH16.SVF SYNTH.TXT KSC16.SVF KSC.TXT OFLKSC.TXT`
- `svf/jamo-extra/`: `SEOU12J.SVF SEOUL.TXT OFLSEOUL.TXT HAN224J.SVF HAN24.TXT OFLHAN24.TXT JOHA16J.SVF JOHAB.TXT
  OFLJOHAB.TXT`
- `build-<id>/`: `BUILD.md LICENCES.tsv.lines FAMILIES.tsv.lines FACES.TSV.lines`

The steps run (for the record, asserted only in `test_uisample.py`): mkfont+svf2to3 for the four OFL fonts and the
dfont (after `macsfnt.py extract`+`unicode`), an `instancer` source step for Caveat, `macfbit3.py` + `srcprep.py` source
steps and `macfbit_svf.py` for Seoul12, `jamoset.py` for HAN24 and johab, `bdfface.py` for ksc. Measured on the probe
tree: facecheck tree 0.3 s, standalone `mkindex --check` 0.4 s, every face draws (`e2efx.assert_draws`; CAVEA16 has no
Hangul, so it is drawn with `A` only).

## The checks (`uisample.check(sample, out_dir, job)`; each failure is one line naming the file)

1. **Expected faces and only them:** the set of files under `out_dir` equals `EXPECTED` with `build-<id>/` for the
   given job id, and equals the job's `result["files"]`; every expected `.SVF` is in some step's `written`; no
   `.svf-maker-*` left (the caller waits up to 10 s for the sweep first, as `LocalEndToEndTest` does).
2. **facecheck:** `inputkinds._facecheck`'s logic on a temp git copy of `out_dir/svf` (`manifest` + `verify` with
   `sys.executable -I tools/facecheck.py`, every SVF `parse_svfn(...).version == 3`) - called as a function on a
   minimal `unittest.TestCase` shim so the existing code is reused, not copied.
3. **mkindex:** `e2efx.merge_check(..., base_repo=False)` (the standalone tree: `LICENCES/FAMILIES` from the
   `build-<id>/*.lines`, FACES.TSV rows for every jamo face, `web/mkindex.py --check`).
4. **Pins:** `GOWUN17A.SVF` == `svf/dos/GBATB17.SVF` bytes; every face draws (`e2efx.assert_draws`, `A` only for
   CAVEA16).
5. **Inputs unchanged:** sha256 of every file under every picked root (the four `ttf/` folders, `in/mac`, `in/hwp`,
   `in/bdf`, and the dfont file) equals the map `make` printed, file set included.
6. **(e2e only) Cross-pass:** the packaged pass's `.SVF` bytes equal the dev pass's (`check --same-as DIR`).

## The helper interface (what `e2e.js` calls)

- `python3 -P maker/test/uisample.py make DIR` -> `DIR/in/...` built (DIR must be new or empty); stdout one JSON:
  `{"dialog": [{"button": "choose-folder"|"choose-files", "path": ABS}...], "output": DIR/out, "fonts": {key: {"root_path": ABS, "path": REL, "ui": {...}}}, "untick": [REL...], "not_read": [REL...], "inputs": {ABS: sha256}}`.
  `dialog` is in pick order: the four `ttf/` folders, `in/mac`, `in/hwp`, `in/bdf` (choose-folder), then the dfont
  (choose-files). `ui` holds exactly what the page must set: `kinds`, `sizes`, `bpp`, `dest`, `preset`, `instance`,
  `dos_layout`, `htbl` / `latin` (as the companion's relative path; the page maps path -> font id).
- `python3 -P maker/test/uisample.py check DIR JOB_JSON [--same-as OTHER_OUT]` -> exit 0 and `{"ok": true}`, or exit 1
  and `{"ok": false, "failures": [...]}`. `JOB_JSON` is a file holding `GET /api/jobs/<id>` (written by e2e.js).
- Both honour `TMPDIR` (temp git copy, merge scratch under `DIR/check/`); `make` refuses a `DIR` under `/tmp`.

## How the e2e drives the UI (one step `T('sample set')` per pass, after `flow`, before `open-folder`)

1. `assert TMP` under `$HOME/work/tmp` (fail with that message otherwise). `spawnSync(PY, ['-P', REPO/maker/test/uisample.py, 'make', TMP/<pass>/sample], {env: {...process.env, TMPDIR: TMP}, timeout: 60 s})`,
   `PY = process.env.SVF_E2E_PYTHON || 'python3'`; parse the JSON.
2. `handle.win.loadURL(origin + '/')`. Push the dialog answers in order (`{canceled: false, filePaths: [p]}` per
   `dialog` entry, then the output folder), and in the page click `#choose-folder` / `#choose-files` once per entry,
   waiting each time until `#source-roots` shows that path; then `#choose-output` and wait for `#sources-panel` to show
   the output folder name; then `#detect-local`; if `#ack` is visible click `#ack-ok`; wait for `#fonts tr[data-font]`.
   Assert `dialogQueue.length === 0`.
3. Map relative path -> font id with a **read-only** `GET /api/jobs/<id>`. In the page, through the controls only
   (set `.value`/`.checked`, dispatch `input` + `change`, as `test_ui_smoke.py`'s `fire`): tick `input.selected` of
   each sample font, untick it for every other row (`NanumGothic-Regular.ttf`, `latin.bdf`, licence rows have none);
   tick the row's `input.override` and, inside `tr.override[data-for=<fid>]`, set `select.ov-kinds`, `input.ov-sizes`,
   `select.ov-bpp`, the dest / preset selects (`aria-label` `dest for ...`, `preset for ...`),
   `select[data-field=instance]`, `select[data-field=htbl_companion]`, the latin companion select
   (`aria-label` `latin companion for ...`); the DOS layout is `select.dos-layout` in the main row. Assert the
   `HANGUL24.PFT` row exists, its label contains `not read`, and its `input.selected` is disabled.
4. Click `#save`; wait until `GET /api/jobs/<id>` shows, for every font, `selected` as intended and the `ui` values
   (this proves the UI wrote them). Click `#run`; wait (page timeout 180 s) for `#state` to contain `written to`, then
   for one `canvas[data-step][data-drawn="1"]` per face step (9).
5. Wait (<= 10 s) for no `.svf-maker-*` in the output folder; write the job JSON to `TMP/<pass>/sample/job.json`; run
   `uisample.py check` (with `--same-as TMP/dev/sample/out` in the packaged pass); on exit 1 fail the step with the
   first three failure lines.
6. Log privacy (existing step): add `TMP/<pass>/sample` and `REPO/ttf/neodgm` to the paths that must not be in the
   shell log (the shell logs path counts only).

## Time budget

- Measured in source mode: detect 4.1 s, run 7.7 s, checks ~1.5 s, `make` ~2 s (the KSC BDF from NEODG16 dominates).
- Expected per pass with the page (source previews of 11 fonts, 9 result canvases): dev ~30-45 s, packaged ~45-70 s
  (each frozen `run-tool` spawn adds start-up; about 17 tool runs). Hard bound of the step: 300 s
  (`waitUntil`), page waits 180 s.
- Effect on G5: about +1.5 to +2 min on the whole e2e (two passes). Task 0 records today's wall time of G5, Task 2 the
  new one; both go into the report and into `docs/maker-desktop.md` "Measured". If a pass takes over 120 s, report it
  instead of raising the bounds.

## Tasks

### Task 0: baseline (no commit)

- [ ] Prerequisites above. Record `git rev-parse HEAD` (eab664a), G1, G2 (`Ran 1144`, skipped 25), G4, and G5 with
  `/usr/bin/time -f %e` around it (`pass=31 fail=0`, lifecycle 4/4, wall time).

### Task 1: `maker/test/uisample.py` + `maker/test/test_uisample.py` (TDD)

**Files:** create `maker/test/uisample.py`, `maker/test/test_uisample.py`.

- [ ] **Step 1: tests first.** `test_uisample.py` (10 tests; one class-level run in `setUpClass`, every mutation on a
  `shutil.copytree` copy of its output):
  1. `test_make_builds_the_synthetic_tree` - `make` into a fresh dir: the files and sizes of the tables above, every
     `dialog` path absolute and existing, the four OFL roots under `REPO/ttf`, nothing written outside `DIR`;
     `make` into a non-empty dir raises.
  2. `test_api_run_writes_exactly_the_expected_tree` - an in-process `e2efx.Server(..., token=localfx.TOKEN)` local job:
     sources = the `dialog` paths, detect, settings built **from the same `ui` table** (`uisample.apply_ui(job)`, the API
     twin of the page script), run, `wait_done`; `check()` returns no failure; step tools as listed above.
  3. `test_check_flags_a_missing_face` - delete `svf/jamo-extra/SEOU12J.SVF` (and its two texts): failure names it.
  4. `test_check_flags_an_extra_file` - add `svf/dos/STRAY.SVF` (a copy of a face): failure names it.
  5. `test_check_flags_a_leftover_work_dir` - add `.svf-maker-<id>/x`.
  6. `test_check_flags_a_changed_input` - append a byte to `in/hwp/ASCII.PFT` after `make` (on a second `make` dir, so
     the class run stays clean): failure names the file.
  7. `test_check_flags_a_corrupt_face` - truncate `KSC16.SVF` to 100 bytes: the parse/facecheck failure names it.
  8. `test_check_flags_a_gbatb17_mismatch` - flip one byte past the header of `GOWUN17A.SVF`.
  9. `test_check_flags_a_missing_faces_row` - drop `JOHA16J.SVF`'s row from `build-<id>/FACES.TSV.lines`: the mkindex
     check fails.
  10. `test_cli_make_and_check` - `python3 -P uisample.py make` / `check` as subprocesses: JSON shape, exit 0 on the
      class run's tree, exit 1 with a `failures` list on a mutated copy; `--same-as` a differing tree fails.
- [ ] **Step 2: run, expect FAIL** (`ModuleNotFoundError: No module named 'uisample'`):
  `cd maker/test && TMPDIR=$HOME/work/tmp/svf-uis python3 -m unittest test_uisample -v`.
- [ ] **Step 3: implement `uisample.py`.** `SAMPLE` (the two tables as data), `EXPECTED` (the 30 paths, `build-{id}/`
  templated), `make(dir)`, `apply_ui(job)` (API twin; pure function over the detected job), `check(sample, out_dir, job,
  same_as=None)` -> list of failure strings (reusing `inputkinds._facecheck`, `e2efx.merge_check`,
  `e2efx.assert_draws` through a `unittest.TestCase` shim whose `fail*`/`assert*` raise and are caught per check), the
  `main()` CLI. Path setup as in `e2efx.py` (insert `TEST_DIR`, `MAKER_DIR`, `REPO/tools`).
- [ ] **Step 4: run, expect PASS** (the Step 2 command, 10 OK, under ~30 s). If the API run's tree differs from
  `EXPECTED`, stop and report the difference: the table above is a measurement, not a guess, and a change means the
  maker changed.
- [ ] **Step 5:** G1, G2 (**1154**, skipped 25). Commit `maker test: the desktop UI sample set (OFL + synthetic
  Mac/HWP/BDF) with its expected tree and checks (t_30b843b8)`.

### Task 2: the `sample set` e2e step (dev and packaged)

**Files:** modify `desktop/test/e2e.js`.

- [ ] **Step 1: red - the step with checks, no UI drive.** Add `T('sample set')`: `make`, pick roots and output,
  detect, then directly `check` (no ticks, no run). Run G5 dev-only: expect `E2E FAIL dev: sample set missing
  svf/dos/NEODU16.SVF ...` and `pass=16 fail=1` (load-failure + 15 dev steps pass; packaged skipped).
- [ ] **Step 2: green - the UI drive** (steps 3-4 of "How the e2e drives the UI"), then the sweep wait and `check`.
  Run G5 dev-only: `pass=17 fail=0`.
- [ ] **Step 3: mutations prove the step bites (temporary edits, not committed; record each FAIL line in the report):**
  (a) skip ticking `Seoul12.rsrc` -> FAIL naming `SEOU12J.SVF`; (b) after the run, truncate `KSC16.SVF` in the
  output folder before `check` -> FAIL naming it; (c) after the run, write `out/svf/dos/X.SVF` -> FAIL naming it;
  (d) packaged pass only: flip one byte past the header of `NEODU16.SVF` before `check` -> the `--same-as`
  failure names it (GBATB17 aside, the cross-pass equality is what catches a wrong-but-valid face). Revert; `git diff` shows only the
  committed step.
- [ ] **Step 4:** add the log-privacy paths (section above, item 6). Full G5 (both passes): `pass=33 fail=0`,
  lifecycle 4/4, the packaged pass's `--same-as` check green. Record wall times per pass (the `E2E PASS` lines'
  timestamps: print `Date.now()` deltas for the new step as `E2E NOTE sample set <pass> <s> s`).
- [ ] **Step 5:** G1, G2 (1154), G4 (`npm test` 56/56; build-appimage every CHECK ok). Commit `desktop e2e: convert
  the OFL sample set and the synthetic Mac/HWP/BDF sample through the UI in both passes, facecheck + mkindex on the
  written tree (t_30b843b8)`.

### Task 3: docs and review

**Files:** modify `docs/maker-desktop.md` (a short "Sample set (e2e)" paragraph: the definition table by reference to
`maker/test/uisample.py`, what is checked, the measured times; one row in "Measured").

- [ ] Commit `docs: the desktop sample-set e2e (t_30b843b8)`. Review (Opus + one independent lane, isolated) of the
  whole branch diff against eab664a; fixes go back to the implementer by resume; re-run G2 and G5 after fixes.
- [ ] Card evidence: `commit:<sha>` of the merge, `test:maker/test/test_uisample.py`, `test:desktop/test/e2e.js`.

## Open questions (for the controller)

1. **HWP sample.** The repository cannot read HWP Hangul `.PFT` files (recipes.md); the HWP sample is therefore a 24 px
   DOS Johab raw face with the HWP `ASCII.PFT` companion, plus `HANGUL24.PFT` shown as "not read". Is that the HWP
   sample the goal means? (No alternative exists without a new reader.)
2. **OFL set size.** Four fonts of `ttf/` (justified above). Say if "the OFL sample set" must be all 13 files: that
   adds about 20-30 s per pass and needs three renames in the UI (Galmuri x3, Nanum x3 clash on `GALMU16*`/`NANUM16*`
   and their notes), which the step would then also drive.
3. **Content pins.** Only GOWUN17A has an absolute byte pin (GBATB17); the others are checked by facecheck, mkindex,
   draws, and the packaged-vs-dev equality. Pinning sha256 of every face in `uisample.py` would catch a wrong font
   choice in dev too, at the cost of updating the pins whenever a tool's output changes. Default in this plan: no
   per-face sha pins.
4. **HangulTalk 1.0** (`macfx.fbit1_fork`, `mac-fbit1`) is left out (the card says fbit and/or dfont). Adding it is one
   more folder and one face (~1 s).
