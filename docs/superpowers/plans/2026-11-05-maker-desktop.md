# SVF maker desktop app (Electron shell + frozen sidecar + AppImage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A double-clickable Linux AppImage of the SVF maker: an Electron shell that spawns a frozen Python sidecar
(the maker server and every tool in one PyInstaller one-dir bundle) on 127.0.0.1, adds the per-launch token itself,
gives the page the `window.svfMaker` bridge, and stops the sidecar cleanly; a generated `THIRD-PARTY.txt`; Windows and
macOS steps written down as UNVERIFIED. Cards t_f04f1355 (shell) and t_e64a56a7 (packaging), goal t_afb4689b.

**Architecture:** Four layers, landed in this order. (1) `maker/toolrun.py` becomes the one place that knows how a
tool is launched (`python3 -P tools/X.py` in source mode, `<sidecar> run-tool X` frozen); every launch site, note and
log goes through it, and the optional recogniser moves to an external interpreter (S1). (2) Server lifecycle for a
shell: signal handling from the first line of `main`, `--exit-with-parent`, the tool registry and its reap, a no-op
second `Worker.stop`; then `maker/sidecar.py`, the PyInstaller spec and the build script, proven by a frozen test under
`env -i` (S2). (3) `desktop/`: pure helpers with node unit tests, then `main.js`/`preload.js` driven under `xvfb-run`
(S3). (4) The licence generator, the electron-builder AppImage and its release check, then the documents (S4, S5).

**Tech Stack:** Python 3.12 stdlib, Pillow 10.2.0 and fontTools 4.66.1 (the PyPI wheels in the build), PyInstaller
6.22.3, unittest; node 22 (`node --test`), Electron 45.2.3, electron-builder 26.18.0, `xvfb-run`; emsdk (emcc 6.0.13)
for the WASM module. No new runtime dependency in `desktop/` (Electron is a devDependency).

**Spec:** `docs/superpowers/specs/2026-11-05-maker-desktop-design.md` at `5d040e2`: sections 6-10, the slices (11),
the decisions (14), the rulings (15, and 17 which wins over 15 for D7/D8/D14/D15) and the review dispositions (16).
Section numbers below ("7.2", "10.3") are the spec's. All commands run from the worktree root
`/home/thkim/work/svf-fonts-open-wt/desktop` (branch `desktop`, base `94011ff`). No push. Revised 2026-11-06 after two
reviews (Opus, SOL); "Review dispositions" at the end lists every finding.

**Rulings that bind this plan:** D1 message box + restart (new token, new port), at most 3 restarts in 5 minutes. D2
`window-all-closed` quits everywhere. D3 the last output folder path persisted in `shell-state.json` (and nothing else
that is a path: see `state.js`). D4 `run-tool` only, no `-P` shim. D5 recogniser through `SVF_RECOG_PYTHON` running the
shipped `repo/maker/recog_score.py`. D6 the pinned versions above. D7 (section 17) ship electron-builder's `AppRun`
unchanged; log and show the sandbox state. D8 (section 17) GPL forbidden by the generator; LGPL distribution record +
source archive are a RELEASE GATE, not a gate of this plan's private build. D9 build on this host (glibc 2.39 floor).
D10 window size/zoom persisted. D11 `getppid` polling plus `PR_SET_PDEATHSIG` on Linux. D12 data root
`<userData>/maker`. D13 `.deb` later (docs only). D14 registry in both modes, PDEATHSIG frozen-only for tools. D15
"open folder" reveals the open job's folder, only if the shell handed it out.

## Global Constraints

- **`c/src` and `c/include` unchanged.** Gate G1 at the end of every task.
- **Scratch space (project rule, user 2026-11-05).** Every scratch file, `mkdtemp` result, build work directory,
  extraction and download lives under an explicit `TMP_DIR=$HOME/work/tmp/svf-desktop-<purpose>`, never loose in
  `/tmp`. Each task's shell starts with:
  ```bash
  export TMP_DIR=$HOME/work/tmp/svf-desktop-t<N>-<purpose>; mkdir -p "$TMP_DIR"
  echo "made by <agent> for task <N> of docs/superpowers/plans/2026-11-05-maker-desktop.md (<card>): <purpose>; delete when the task has landed" > "$TMP_DIR/README"
  export TMPDIR=$TMP_DIR
  ```
  Python `tempfile` and node `os.tmpdir()` honour `TMPDIR`, so tests that create temp directories (new and existing)
  land there; **no new test or script hard-codes `/tmp`** (a check in `test_toolrun.py`, Task 1, scans the new
  files). Build scripts take `SVF_DESKTOP_TMP` (default `$HOME/work/tmp/svf-desktop-build`, created with its README)
  for the pip download (`pysite/`), PyInstaller's work directory, the WASM comparison build and AppImage extractions.
  The deliverables stay in the gitignored `desktop/build/out/` and `desktop/dist/`.
- **Gates at the end of every task** (before its commit), in this order:
  - G1 `git diff --exit-code 94011ff -- c/src c/include` -> exit 0, no output.
  - G2 `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
    -> `OK` and `Ran N tests`. At `94011ff`: **914 tests, OK (skipped=14)**. Each task states its expected N and skips
    (plan estimates); a different observed N goes into the commit body with the reason. G2 stays green at every task.
  - G3 `python3 -m unittest discover -s maker/test -p test_server.py -k test_page_js_tables_match_python` -> `OK`
    (the python and `maker.js` tables in sync; no task changes either side, the gate proves it).
  - G4 (tasks touching `desktop/`) `cd desktop && node --test test/unit.test.js` (Task 7 onward: `node --test
    test/unit.test.js test/third-party.test.js`) -> all pass. **Explicit files only:** node 22 rejects a directory
    argument (`node --test test/` -> `Cannot find module`), and a bare `node --test` would also load the Electron-only
    `test/e2e.js` and `test/lifecycle.test.js`. `package.json` `"test"` is the same explicit list.
  - G5 (tasks touching the shell, Task 6 onward) the Electron runs, each its own announced step:
    `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh` and
    `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy node --test desktop/test/lifecycle.test.js`.
- **One browser at a time, under the guard.** Every run that starts Chrome or Electron (G2, `smoke_dom.py`, G5, the
  AppImage smoke) takes the host-wide lock `$HOME/work/tmp/svf-browser.lock` (`flock`) and runs under
  `~/.local/bin/heavy` (all heavy jobs share 256 tasks). Measured here (2026-11-06, Electron 45.2.3 under
  `xvfb-run`, a one-window app): one instance 143 tasks with the GPU process, **87 with `--disable-gpu`**; the
  second-instance case (a loser that quits at its lock) peaks at 170 with the GPU and **114 with `--disable-gpu`**. So
  every Electron run in this plan passes `--no-sandbox --disable-gpu`, and `lifecycle.test.js` never runs more than two
  Electron instances (the second only in the second-instance case) - about 114 tasks plus the dev sidecar's threads,
  inside the slice, but not beside a Chrome G2 run, hence the lock.
- **Full runs are announced.** Before and after every G2, G5, `build-sidecar.sh` and `build-appimage.sh` run, the
  implementer sends the controller one line: `START <what> <task>` / `FINISH <what> <task> <result>`.
- **Long runs through the OOM guard:** G2, G5, `tools/test_*.py`, `make -C c check`, PyInstaller and electron-builder
  builds, the frozen test.
- **No proprietary data.** Fixtures are synthetic (`maker/test/inputfx.py`, `fixtures.py`, `localfx.py`) or OFL files
  of this repository (`ttf/neodgm/neodgm.ttf`, `ttf/nanumgothic/NanumGothic-Bold.ttf`). The bundle carries OFL assets
  only (`svf/` copied whole, `web/` index files).
- **Pinned versions (D6):** `pyinstaller==6.22.3 pillow==10.2.0 fonttools==4.66.1` in
  `desktop/build/requirements-sidecar.txt`; `"electron": "45.2.3"`, `"electron-builder": "26.18.0"` exact in
  `desktop/package.json` devDependencies with `desktop/package-lock.json` committed; `build.electronVersion "45.2.3"`.
  A version moves only with a full release check (Task 8) run.
- **Build environment as verified here:** `python3 -m venv` does not work on this host; the build installs the pinned
  wheels with `python3 -m pip install --target $SVF_DESKTOP_TMP/pysite -r desktop/build/requirements-sidecar.txt` and
  runs Python as `PYTHONPATH=<pysite> python3 -S` (no `site`: Debian's dist-packages - wx, setuptools - stay out of the
  graph and out of the reference; the Opus review built a one-dir binary this way here). npm 12 blocks Electron's
  postinstall: after `npm ci` run `node node_modules/electron/install.js`.
- **The tool launch is byte-identical in effect** between modes (spec section 2): same argv after the launcher prefix,
  cwd, scrubbed environment, process group, exit codes, the same note/`BUILD.md`/`log.md` text.
- **No bare `git stash`.** Set work aside with a WIP commit on the branch.
- **Spikes stay under `desktop/spike/`** (throw-away, never imported by product code or tests).
- **Tools unchanged.** No file under `tools/` changes (`git diff --exit-code 94011ff -- tools` at Task 9).
- **The page unchanged.** No file under `maker/static/` changes (`git diff --exit-code 94011ff -- maker/static` at
  Task 9).
- **Process checks are scoped.** A test asserts on the pids/pgids it recorded itself (`shell pid=`, `sidecar start
  ... pid=`, `tools.pids`, `Popen.pid`), zombie-aware (`/proc/<pid>/stat` state `Z`/`X` counts as gone), never with a
  host-wide `pgrep -f` (other worktrees run maker servers too).
- **Commits** end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and name the card in
  the subject: `(t_f04f1355)` for Tasks 1-6, `(t_e64a56a7)` for Tasks 7-9 (both when a commit serves both).
- **Serialization.** No two tasks edit `maker/jobs.py`, `maker/preview.py`, `maker/server.py`, `maker/caps.py`,
  `maker/test/localfx.py` or `.gitignore` at the same time; tasks sharing a file land in plan order. All ignore rules
  for the whole plan are added in Task 1, so later lanes never touch `.gitignore`. A parallel lane uses its own
  worktree (`superpowers:using-git-worktrees`) and **rebases onto the current `desktop` branch and reruns its gates
  before landing**.

## Review Focus

1. **Tool launch parity: a launch that only fails frozen.** A site left on the old prefix, a positional consumer that
   slices `argv[2]`, or a note that shows `/tmp/.mount_svf-XYZ/resources/sidecar/svf-maker-sidecar run-tool mkfont` or
   `/tmp/.mount_svf-XYZ/resources/repo/svf/dos/NEODG16.SVF` instead of `python3 -P tools/mkfont.py` / `svf/dos/...`.
   Pinned by `test_no_stray_launcher`, `test_every_builder_uses_toolrun_both_modes` and
   `test_note_and_build_md_equal_both_modes` (Task 1), `test_frozen_jobs_match_source` and
   `test_frozen_notes_equal_source` (Task 4).
2. **Orphan processes: a tool, a recogniser or a sidecar that outlives its parent.** Cases: the sidecar SIGKILLed
   mid-tool, the shell SIGKILLed, the shell dying during the sidecar's start-up (probe, cleanup), PDEATHSIG's SIGTERM
   arriving while stdout/stderr lead to a dead pipe, a restart whose sweep races a tool of the dead sidecar (an external
   recogniser interpreter, or a frozen tool launched from an AppImage mounted at another path), a zombie counted as
   alive, a second instance. Pinned by `test_exit_with_parent_*` and `test_reap_*` (Task 3),
   `test_sigkill_sidecar_kills_tool` / `test_sigkill_without_pdeathsig_reaped_on_restart` (Task 4), and
   `lifecycle.test.js` (Task 6).
3. **Token and header handling.** Cases: a request to an old port after a restart, a second `x-maker-token` spelling
   injected by the page, a non-`/api/` request, the token in a tool's environment, a log line, the command line or
   `shell-state.json`. Pinned by `withToken` unit tests (Task 5), `test_tool_env_has_no_maker_keys` (Task 1), the e2e
   restart check and the log scan in `e2e.js` (Task 6).
4. **Privacy of logs.** `shell.log` must hold no token, no picked path (counts only), no request URL beyond start/stop,
   no input byte, and no path the sidecar printed on stderr (`sweep: <output path>`); `BUILD.md` must not carry the
   AppImage mount path. Pinned by `redactLine`/log tests (Task 5), the e2e `shell.log` scan with a planted `sweep:` line
   (Task 6), and `test_note_and_build_md_equal_both_modes` (Task 1).
5. **Licence generation.** Cases: a `.so` in `_internal/` or in the AppImage's `usr/lib` no map entry matches (fails
   closed), a GPL entry, the PyInstaller bootloader (GPL with exception), an LGPL entry without a distribution record,
   a non-OFL file under `repo/svf`, Electron's `libffmpeg.so`, a sources manifest naming a missing or altered archive.
   Pinned by `third-party.test.js` (Task 7) and the release check's `licences` step (Task 8).

## Verified while planning (this host, `94011ff`; revision checks 2026-11-06)

- `grep -n 'PY\b\|SRCPREP\|sys.executable' maker/*.py`: `routes.py` 27 launch sites (lines 135-324 and 379-396),
  `settings.py:1446` (`_dy_argv`), `jobs.py:1514` (`_identity`): 29, as spec 7.3 says. `sys.executable` otherwise only
  at `routes.py:20` and `zipout.py:419`. `test_routes.py` uses `routes.SRCPREP` at `:486`, `:510`, `:514` (with
  `a[2:4]` slices).
- `settings.probe_argv` (`:1402`) slices `mkfont_argv[2]`, `[5:]`, `[:2]`; `zipout.note_commands` (`:434`) tests
  `basename == "johab844.py"` over `argv[:4]`; `_johab844_comment` (`:457`) reads `argv[4]` - with `routes.py:196`
  `PY + [johab844.py, src, base, out]` that is the **base** face. The johab844 route is `Route("precomposed",
  "johab844", ..., [1], [16], ...)` (`routes.py:436`) for a DOS raw 844 font with an 8x16 English font (`settings.py:1009-1020`):
  `localfx.local_tree`'s `b/HAN.FNT` + `b/ENG.FNT`.
- Test steps run `[sys.executable, "-c", script, ...]` argvs through `log_step`/notes (`test_jobs.py:291,811,835`,
  `test_server_signals.py:65`, `test_page_dom.py:220`).
- `server.Handler._caps` (`:1772`) serves `{key: bool(value)}` for every key of `server.caps`.
- `make_server` order: store, `caps.compute`, `Worker(...)`, `worker.recover()`, `worker.start()`, bind,
  `startup_cleanup()`. `main()` takes no arguments; it installs `terminate()` for SIGTERM/SIGINT and its `finally`
  only after `make_server` returns (`server.py:1982-2003`).
- `jobs.RECOG_ARRAYS = "numpy"` (`jobs.py:148`); `recog_score.py --arrays numpy` imports numpy (`:249`); tests use
  `lists`. The `run_identity` helper (`test_jobs.py:650`) patches `caps.recog_dir` and `jobs.RECOG_ARRAYS`.
- `python3 -P tools/svfline.py --help` exits **1** with its usage on stderr (`  svfline.py line W H X Y TEXT FACE...`);
  every other tool prints `usage: <name>.py` on stdout and exits 0; instancer prints `usage: fonttools varLib.instancer`.
- `jamoset.DEFAULT_MASK_FONT = mask_font_beside(os.path.dirname(os.path.abspath(__file__)))` (`tools/jamoset.py:2282`),
  overridden by `JAMOSET_MASK_FONT` (`:2299`).
- `svf/` holds 116 `.SVF`, 20 `.TXT` licence/notes texts and one other file, `svf/jamo-extra/FACES.TSV`.
- `maker/build-wasm.sh` honours `SVF_WASM_OUT`. `index.html` has `<link rel="icon" href="data:,">`.
- `node --test test/` on node v22.23.4 fails with `Cannot find module '<dir>/test'` (Opus review probe).
- electron-builder 26.18.0 `scheme.json`: `LinuxDesktopFile` is `{entry, desktopActions}` with
  `additionalProperties: false`; `desktopName` is not a key of the `build` configuration (it is a `package.json`
  field); `linux.executableArgs` and `linux.artifactName` exist. The legacy AppImage toolset
  (`~/.cache/electron-builder/appimage-12.0.1/.../lib/x64`) holds `libappindicator.so.1 libgconf-2.so.4
  libindicator.so.7 libnotify.so.4 libXss.so.1 libXtst.so.6`, copied into the AppImage's `usr/lib`.
- Electron task counts under `xvfb-run` (measured 2026-11-06 in `$HOME/work/tmp/svf-desktop-plan-measure`): see
  "One browser at a time" above. `def test_` count in `maker/test` is 914. Page ids the e2e uses: `#choose-files`,
  `#choose-folder`, `#choose-output`, `#detect-local`, `#run`, `#open-folder`, `#state`, `#jobs`, `#ack-ok`; drawn
  canvases carry `data-drawn="1"`; the page writes `?job=<id>` and calls `openOutputFolder()` with no argument.

## File map

| File | Status | Responsibility (task) |
|---|---|---|
| `maker/toolrun.py` | create | launcher shapes, note prefix, base env (1); `recog_argv` (2); `set_pdeathsig`, `alive` (3) |
| `maker/routes.py`, `maker/settings.py`, `maker/zipout.py` | modify | launch sites and positional consumers on `toolrun`; `repo_head` + `BUILD_ID`; repo-rooted note tokens (1) |
| `maker/jobs.py` | modify | `ENV`, `_identity` argv, `log_step` repo dir (1); `_identity` on `self.caps` (2); registry in `run_command`, `Worker.stop` once (3) |
| `maker/preview.py` | modify | `ENV` (1); registry in `run_bounded` (3) |
| `maker/caps.py` | modify | the external recogniser probe, `PUBLIC_KEYS` (2) |
| `maker/server.py` | modify | `_caps` serves `PUBLIC_KEYS` (2); `main(argv)`, early signal handling, `--exit-with-parent`, registry activation and reap, partial-construction cleanup (3) |
| `maker/toolreg.py` | create | `<data_root>/tools.pids` registry and reap (3) |
| `maker/sidecar.py`, `maker/sidecar.spec`, `maker/build-sidecar.sh` | create | frozen entry point, PyInstaller spec, build + staging (4); provenance call (7) |
| `desktop/build/requirements-sidecar.txt` | create | the three pinned wheels (4) |
| `maker/test/test_toolrun.py`, `test_sidecar_imports.py` | create | (1); roots switched to `sidecar` (4) |
| `maker/test/test_toolreg.py`, `test_sidecar.py`, `test_frozen.py`, `maker/test/parent_harness.py` | create | (3), (4), (4), (3) |
| `maker/test/localfx.py`, `maker/test/inputfx.py`, `maker/test/test_local.py` | modify | `LocalRunBase` moved to `localfx`, `owns()`, `SubprocessLocalBase` (4); `big_composite_ttf(n)` (4) |
| `maker/test/test_routes.py`, `test_zipout.py`, `test_plan_inputs.py`, `test_jobs.py`, `test_preview.py`, `test_server.py`, `test_server_signals.py` | modify | per task |
| `.gitignore` | modify | `desktop/build/out/`, `desktop/node_modules/`, `desktop/dist/` (1, all of them) |
| `desktop/package.json`, `package-lock.json`, `desktop/lib/*.js`, `desktop/test/unit.test.js` | create | helpers and unit tests (5) |
| `desktop/main.js`, `preload.js`, `starting.html`, `desktop/build/icon.png`, `desktop/build/make-icon.py`, `desktop/test/{e2e.js,probe-preload.js,run-e2e.sh,lifecycle.test.js}` | create | the shell (6) |
| `desktop/build/third-party.mjs`, `third-party-map.json`, `desktop/build/licences/`, `desktop/build/sidecar-provenance.py`, `desktop/test/third-party.test.js` | create | THIRD-PARTY generation and the sources gate (7) |
| `desktop/build/build-appimage.sh`, `desktop/build/release-check.sh` | create | AppImage + release check (8); `package.json` "build" block (8) |
| `docs/maker-desktop.md`, `maker/README.md`, `NOTICE.md`, `docs/maker-audit.md`, `docs/STATUS.md`, `desktop/spike/README.md`, `desktop/spike/spawn-probe.mjs` | create/modify | (9) |

---

# Group A: the launcher helper (slice S1)

Tasks 1 -> 2, sequential (both edit `maker/jobs.py`). One review after Task 2.

### Task 1: `maker/toolrun.py`, every launch site, notes and logs, `BUILD_ID`, forwarded keys (slice S1, part 1)

**Files:**
- Create: `maker/toolrun.py`, `maker/test/test_toolrun.py`, `maker/test/test_sidecar_imports.py`
- Modify: `maker/routes.py` (delete `PY`, `SRCPREP`, `_tool`; 27 sites), `maker/settings.py` (`probe_argv`,
  `_dy_argv`), `maker/jobs.py` (`ENV`; `_identity`'s argv line; the two `log_step` calls pass `self.repo_dir`),
  `maker/preview.py` (`ENV`), `maker/zipout.py` (`repo_head`, `_command_lines`, `log_step`, `note_commands`,
  `_johab844_comment`), `.gitignore` (`desktop/build/out/`, `desktop/node_modules/`, `desktop/dist/`)
- Test (modify): `maker/test/test_routes.py` (`PY` and its 13 uses; `routes.SRCPREP` at `:486`, `:510`, `:514`),
  `test_zipout.py` (`:115-131`, `:550`, note expectations), `test_plan_inputs.py` (`routes.PY`/`routes.SRCPREP`
  uses), `test_jobs.py`, `test_preview.py`

**Interfaces:**
- Produces (`maker/toolrun.py`, stdlib only, importable from `maker/` and `tools/` on `sys.path`):
  - `FROZEN: bool = bool(getattr(sys, "frozen", False))`, `PYTHON: str = sys.executable` (the interpreter of
    source-mode launches; a test seam - Task 4's reference job patches it to a wrapper that runs the pinned wheels),
    `MAKER_DIR`, `MAKER_SCRIPTS = ("srcprep", "recog_score")`, `MODULE_NAMES = {"fontTools.varLib.instancer":
    "instancer"}`.
  - `tool(name: str, tools_dir: str) -> list[str]`: source `[PYTHON, "-P", <tools_dir>/<name>.py]`, frozen
    `[sys.executable, "run-tool", name]`. `name` has no `.py`.
  - `maker_script(name: str) -> list[str]`: source `[PYTHON, "-P", <MAKER_DIR>/<name>.py]`, frozen
    `[sys.executable, "run-tool", name]`.
  - `module(dotted: str) -> list[str]`: source `[PYTHON, "-P", "-m", dotted]`, frozen
    `[sys.executable, "run-tool", MODULE_NAMES[dotted]]`.
  - `split_prefix(argv: list) -> tuple[list, list]`: recognises, whatever `FROZEN` is, `[x, "-P", "<...>.py", ...]`
    (3), `[x, "-P", "-m", dotted, ...]` (4), `[x, "run-tool", name, ...]` (3); `ValueError` otherwise.
  - `prefix_name(prefix: list) -> str`: the run-tool name of a prefix: `"mkfont"`, `"srcprep"`, `"instancer"`.
  - `note_prefix(argv: list) -> tuple[list, list]`: the prefix as the note shows it in both modes
    (`["python3", "-P", "tools/<name>.py"]`, `["python3", "-P", "maker/<name>.py"]` for `MAKER_SCRIPTS`,
    `["python3", "-P", "-m", dotted]`), and the rest; for an argv `split_prefix` refuses, `([], list(argv))`
    (pass-through: test steps and copy steps are not launches - design issue 2).
  - `note_argv(argv: list, repo_dir: str | None = None) -> list`: `prefix + rest` of `note_prefix`, with every token
    of `rest` that is an absolute path under `os.path.realpath(repo_dir)` rewritten to its repo-relative form
    (`svf/dos/NEODG16.SVF`), so the base face of a johab844 step reads the same from a checkout and from an AppImage
    mount.
  - `FORWARD_KEYS = ("JAMOSET_PYLIB", "JAMOSET_MASK_FONT")`; `TEST_KEYS = ("SVF_MAKER_NO_PDEATHSIG",)`.
  - `base_env(environ: Mapping) -> dict`: `{"PATH": environ.get("PATH", "/usr/bin:/bin"), "HOME":
    environ.get("HOME", "/"), "LANG": "C.UTF-8"}`, plus each `FORWARD_KEYS` key set and non-empty in `environ`
    (spec 7.4; `JAMOSET_MASK_FONT` added - design issue 25), plus `SVF_MAKER_NO_PDEATHSIG` **only when its value is
    exactly `"1"`** (the test-only knob of Task 3/4; design issue 17). `jobs.ENV = toolrun.base_env(os.environ)` and
    `preview.ENV = toolrun.base_env(os.environ)`.
- Produces (`maker/zipout.py`): `repo_head(repo_dir) -> str`: `<repo_dir>/BUILD_ID` first line stripped, at most 200
  characters, when the file exists and the line is non-empty; else `"unknown"` when `toolrun.FROZEN`; else git as
  today. `_command_lines(step, src=None, repo_dir=None)` and `log_step(step, stdout, stderr, repo_dir=None)` join
  `toolrun.note_argv(argv, repo_dir)`; `note_commands(..., repo_dir=None)` likewise (callers pass the server's/worker's
  `repo_dir`).

- [ ] **Step 1: Write the failing tests** in `maker/test/test_toolrun.py`:

```python
class ShapesTest(unittest.TestCase):
    def test_source_shapes(self):
        self.assertEqual(toolrun.tool("mkfont", "/T"), [sys.executable, "-P", "/T/mkfont.py"])
        self.assertEqual(toolrun.maker_script("srcprep"), [sys.executable, "-P", os.path.join(toolrun.MAKER_DIR, "srcprep.py")])
        self.assertEqual(toolrun.module("fontTools.varLib.instancer"), [sys.executable, "-P", "-m", "fontTools.varLib.instancer"])
    def test_python_seam(self):
        with mock.patch.object(toolrun, "PYTHON", "/w/ref-python"):
            self.assertEqual(toolrun.tool("mkfont", "/T")[0], "/w/ref-python")
    def test_frozen_shapes(self):
        with mock.patch.object(toolrun, "FROZEN", True):
            self.assertEqual(toolrun.tool("mkfont", "/T"), [sys.executable, "run-tool", "mkfont"])
            self.assertEqual(toolrun.maker_script("srcprep"), [sys.executable, "run-tool", "srcprep"])
            self.assertEqual(toolrun.module("fontTools.varLib.instancer"), [sys.executable, "run-tool", "instancer"])
    def test_split_prefix_all_shapes_either_mode(self):
        for frozen in (False, True):
            with mock.patch.object(toolrun, "FROZEN", frozen):
                self.assertEqual(toolrun.split_prefix(["/p", "-P", "/T/mkfont.py", "a", "b"]), (["/p", "-P", "/T/mkfont.py"], ["a", "b"]))
                self.assertEqual(toolrun.split_prefix(["/p", "-P", "-m", "fontTools.varLib.instancer", "x"])[1], ["x"])
                self.assertEqual(toolrun.split_prefix(["/s", "run-tool", "mkfont", "a"]), (["/s", "run-tool", "mkfont"], ["a"]))
        for bad in ([], ["/p"], ["/p", "-c", "print(1)"], ["/p", "-P"], ["/p", "-P", "notpy"], ["/s", "run-tool"]):
            with self.assertRaises(ValueError): toolrun.split_prefix(bad)
    def test_note_prefix_same_text_both_modes(self):
        cases = [(lambda: toolrun.tool("mkfont", "/T"), ["python3", "-P", "tools/mkfont.py"]),
                 (lambda: toolrun.maker_script("srcprep"), ["python3", "-P", "maker/srcprep.py"]),
                 (lambda: toolrun.module("fontTools.varLib.instancer"), ["python3", "-P", "-m", "fontTools.varLib.instancer"])]
        for make, want in cases:
            for frozen in (False, True):
                with mock.patch.object(toolrun, "FROZEN", frozen):
                    self.assertEqual(toolrun.note_prefix(make() + ["a"]), (want, ["a"]))
    def test_note_prefix_passes_non_launchers(self):
        argv = [sys.executable, "-c", "print(1)", "/w/out"]
        self.assertEqual(toolrun.note_prefix(argv), ([], argv))
    def test_note_argv_repo_relative(self):
        a = toolrun.tool("johab844", "/R1/tools") + ["/u/H.FNT", "/R1/svf/dos/NEODG16.SVF", "/w/O.SVF"]
        with mock.patch.object(toolrun, "FROZEN", True):
            b = toolrun.tool("johab844", "/mnt/X/resources/repo/tools") + ["/u/H.FNT", "/mnt/X/resources/repo/svf/dos/NEODG16.SVF", "/w/O.SVF"]
        self.assertEqual(toolrun.note_argv(a, "/R1"), toolrun.note_argv(b, "/mnt/X/resources/repo"))
        self.assertEqual(toolrun.note_argv(a, "/R1")[4], "svf/dos/NEODG16.SVF")
    def test_base_env(self):
        self.assertEqual(toolrun.base_env({"PATH": "/b", "HOME": "/h", "SVF_MAKER_TOKEN": "x" * 32, "PYTHONPATH": "/e",
                                           "SVF_MAKER_NO_PDEATHSIG": "yes"}),
                         {"PATH": "/b", "HOME": "/h", "LANG": "C.UTF-8"})
        self.assertEqual(toolrun.base_env({"JAMOSET_PYLIB": "/lib"})["JAMOSET_PYLIB"], "/lib")
        self.assertEqual(toolrun.base_env({"JAMOSET_MASK_FONT": "/f.ttf"})["JAMOSET_MASK_FONT"], "/f.ttf")
        self.assertNotIn("JAMOSET_PYLIB", toolrun.base_env({"JAMOSET_PYLIB": ""}))
        self.assertEqual(toolrun.base_env({"SVF_MAKER_NO_PDEATHSIG": "1"})["SVF_MAKER_NO_PDEATHSIG"], "1")
    def test_tool_env_has_no_maker_keys(self):
        # the token, the bind, the data root and every PYTHON* key never reach a tool; the one SVF_ key ever allowed is
        # the test knob, and only as "1"
        for env in (jobs.ENV, preview.ENV, toolrun.base_env({**os.environ, "SVF_MAKER_TOKEN": "a" * 32, "PYTHONHOME": "/x"})):
            self.assertEqual([k for k in env if k.startswith("PYTHON")], [])
            self.assertEqual([k for k in env if k.startswith("SVF_") and k not in toolrun.TEST_KEYS], [])
            self.assertIn(env.get("SVF_MAKER_NO_PDEATHSIG", "1"), ("1",))
    def test_new_files_use_no_bare_tmp(self):
        # regex r"['\"]/tmp" over maker/toolrun.py, maker/toolreg.py, maker/sidecar.py, maker/build-sidecar.sh,
        # maker/test/test_toolrun.py, test_toolreg.py, test_sidecar.py, test_frozen.py, parent_harness.py,
        # desktop/**/*.{js,mjs,sh,py} (those that exist): no match (the TMP_DIR rule)

class BuildersTest(unittest.TestCase):
    def test_every_builder_uses_toolrun_both_modes(self):
        # for FROZEN in (False, True): every argv from
        #   each route's commands(...) and prepare_commands(...) over test_server.canonical_fonts() (the drift test's fonts),
        #   routes.source_commands for one op of each kind: rsrc-sfnt, ttc-face, mac-cmap, instance, pcf-bdf, mac-fork,
        #   mac-fbit3, mac-htbl, mac-fork-named,
        #   routes.svf_commands, settings._dy_argv (a dy table), settings.probe_argv (fed a mkfont argv of that mode)
        # -> toolrun.split_prefix(argv) succeeds and prefix[1] == ("run-tool" if frozen else "-P")
    def test_probe_argv_keeps_prefix_and_flags_frozen(self):
        with mock.patch.object(toolrun, "FROZEN", True):
            mk = toolrun.tool("mkfont", "/T") + ["/u/a.ttf", "/w/O.SVF", "--size", "16", "--bpp", "2", "--unicode", "ascii", "--cell", "18"]
            got = settings.probe_argv(mk, "/u/a.ttf", "/w/p.svf", "/w/p.json", 16)
        self.assertEqual(got[:3], [sys.executable, "run-tool", "mkfont"])
        self.assertEqual(got[3:5], ["/u/a.ttf", "/w/p.svf"])
        self.assertIn("--probe-cell", got); self.assertEqual(got[got.index("--probe-cell") + 1], "18")
    def test_no_stray_launcher(self):
        # over maker/*.py (not test_*.py): "sys.executable" occurs only in toolrun.py and zipout.py;
        # no module defines a name PY or SRCPREP; regex r'"[a-z0-9_]+\.py"' finds nothing in routes.py, settings.py, jobs.py
```

  In `maker/test/test_zipout.py` (new class `LauncherNotesTest`):

```python
def test_note_and_build_md_equal_both_modes(self):
    # one mkfont step and one johab844 step: source argvs built with toolrun.tool(..., "/R1/tools") and base face
    # "/R1/svf/dos/NEODG16.SVF"; frozen argvs (FROZEN patched True) with repo "/mnt/X/resources/repo";
    # for an upload job (sources=None) AND a local job (a Sources with one root):
    #   note_commands(..., repo_dir=<that mode's repo>) equal between modes; _command_lines(step, repo_dir=...) equal;
    #   log_step(step, "", "", repo_dir=...) equal; each mkfont line starts with "python3 -P tools/mkfont.py ";
    #   no line contains sys.executable, "run-tool", "/R1" or "/mnt/X"
def test_johab844_comment_both_modes(self):
    # the line before each johab844 command is
    # "# johab844: Hangul redrawn on the base face svf/dos/NEODG16.SVF (OFL); the chosen range is ignored"
def test_repo_head_build_id(self):
    # tmp/BUILD_ID "abc1234 2026-11-05 sidecar 0.1.0\n" -> that string; a 300-char line -> its first 200; an empty file
    # -> falls through; no BUILD_ID + toolrun.FROZEN True + subprocess.run patched to fail if called -> "unknown";
    # no BUILD_ID, not frozen, a non-git dir -> "unknown"
```

  In `test_jobs.py` and `test_preview.py`: `test_env_from_base_env`: `jobs.ENV == toolrun.base_env(os.environ)`, the
  same for `preview.ENV`.

  In `maker/test/test_sidecar_imports.py` (the logic of `desktop/spike/import_graph.py` copied in; the spike is not
  imported):

```python
ROOTS = ["server", "jamoset", "jamovec", "mkfont", "macfbit_svf", "macfbit3", "macsfnt", "bdfface", "johab844",
         "svf2to3", "svfdy", "svfline", "srcprep"]
EXPECTED = {"archive", "bdfface", "caps", "detect", "jamoaa", "jamoadapt", "jamofit", "jamoset", "jamovec", "jobs",
            "johab844", "macfbit3", "macfbit_svf", "macsfnt", "mkfont", "naming", "presets", "preview", "quality",
            "routes", "server", "settings", "sources", "srcprep", "svf2to3", "svfdy", "svfline", "toolrun", "zipout"}
FILE_USES = {   # every __file__ use in a reachable module, with why it is right frozen (spec 7.5/7.6)
    ("server", "MAKER_DIR"): "static/ is bundled as <_internal>/static",
    ("jamoset", "mask_font_beside"): "DEFAULT_MASK_FONT; JAMOSET_MASK_FONT is forwarded (base_env)",
    # ... one entry per hit the implementer finds; each tools' sys.path.insert(0, HERE) is one entry per module
}
def test_reachable_set(self):           # == EXPECTED (the spec's 28 + toolrun)
def test_third_party(self):             # third-party names == {"PIL", "fontTools", "freetype", "uharfbuzz"}
def test_file_uses_listed(self):        # ast: every Name/Attribute "__file__" in a reachable module maps to a FILE_USES key
                                        # (module, enclosing assignment target or function); an unlisted use fails
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_toolrun.py'` and `-p
  'test_sidecar_imports.py'`. Expected: FAIL (`No module named 'toolrun'`).
- [ ] **Step 3: Implement** `maker/toolrun.py` to the interface; then the sites of spec 7.3: each
  `PY + [_tool(paths, "X.py"), ...]` -> `toolrun.tool("X", paths["tools"]) + [...]`; each `PY + [SRCPREP, ...]` ->
  `toolrun.maker_script("srcprep") + [...]`; `PY + [os.path.join(tools_dir, "X.py"), ...]` ->
  `toolrun.tool("X", tools_dir) + [...]`; `routes.py:386` -> `toolrun.module("fontTools.varLib.instancer") + [...]`;
  `settings.py:1446` -> `toolrun.tool("svfdy", tools_dir) + [...]`; `jobs.py:1514` ->
  `toolrun.maker_script("recog_score") + [...]` (Task 2 replaces it). Delete `routes.PY`, `routes.SRCPREP`,
  `routes._tool` in the same commit. `probe_argv`: `prefix, rest = toolrun.split_prefix(mkfont_argv)`; source
  `rest[0]`, output `rest[1]`, flags `rest[2:]`; result `prefix + [src, out_svf, "--size", ...]`. `note_commands`: in
  both branches split first; johab844 is `toolrun.prefix_name(prefix) == "johab844"`; `_johab844_comment(rest)` reads
  the base face from `rest[1]` and `--eng` from `rest` (design issue 1); then `note_argv(argv, repo_dir)`; the local
  branch then applies `_note_token` to the remaining absolute tokens. Add the three ignore lines to `.gitignore`.
- [ ] **Step 4: Fix the existing tests** named in Files: `test_routes.py` builds expectations with
  `toolrun.tool("X", "/T") + [...]` and `toolrun.maker_script("srcprep") + [...]` (the `a[2:4]` slices at `:510`/`:514`
  become `toolrun.split_prefix(a)` + `prefix_name`); `test_plan_inputs.py` replaces `routes.PY + ["/T/X.py", ...]`
  with `toolrun.tool("X", "/T") + [...]` and `routes.PY + [routes.SRCPREP, ...]` with
  `toolrun.maker_script("srcprep") + [...]`; `test_zipout.py` upload-job notes now read `python3 -P tools/<name>.py ...`
  with repo-relative repo tokens (rewrite those expected strings; every other assertion unchanged).
- [ ] **Step 5: Run** `python3 -m unittest discover -s maker/test -p <module>` for `test_toolrun.py`,
  `test_sidecar_imports.py`, `test_routes.py`, `test_zipout.py`, `test_plan_inputs.py`, `test_settings.py`,
  `test_jobs.py`, `test_preview.py`. Expected: `OK`.
- [ ] **Step 6: Count the launch lines** (the S1 review reads it): `git diff 94011ff -- maker/routes.py
  maker/settings.py maker/jobs.py | grep -c '^-.*\bPY +'` -> 29 and `grep -c '^+.*toolrun\.\(tool\|maker_script\|module\)('`
  -> 29; both counts and the diff path (`$TMP_DIR/s1-argv.diff`) go into the commit body.
- [ ] **Step 7: Gates** G1, G2 (expected 914 + 21 = **935**, skipped 14), G3; plus
  `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_*.py'` -> `OK`.
- [ ] **Step 8: Commit** `git add maker/toolrun.py maker/routes.py maker/settings.py maker/jobs.py maker/preview.py
  maker/zipout.py maker/test/test_toolrun.py maker/test/test_sidecar_imports.py maker/test/test_routes.py
  maker/test/test_zipout.py maker/test/test_plan_inputs.py maker/test/test_jobs.py maker/test/test_preview.py
  .gitignore && git commit -m "maker: toolrun is the one launcher (source -P / frozen run-tool); notes, BUILD.md and logs show python3 -P and repo-relative paths in both modes; BUILD_ID; JAMOSET_* forwarded (t_f04f1355)"`.

Cannot verify here: nothing beyond the frozen run itself (Task 4 runs every launcher form frozen). How the test
degrades: the frozen shape is checked with `mock.patch.object(toolrun, "FROZEN", True)`, which proves the argv and
note text but not that the frozen executable accepts it.

### Task 2: the optional recogniser through an external interpreter (slice S1, part 2; D5)

**Files:**
- Modify: `maker/caps.py`, `maker/toolrun.py` (`recog_argv`), `maker/jobs.py` (`Worker._identity`),
  `maker/server.py` (`Handler._caps` only)
- Test (modify): `maker/test/test_server.py` (caps tests near `:1349`), `test_jobs.py` (`run_identity` `:650` and the
  identity tests `:650-740`), `test_local.py` (`:527`)

**Interfaces:**
- Consumes: `toolrun.maker_script`, `toolrun.base_env` (Task 1).
- Produces:
  - `caps.PUBLIC_KEYS = ("wasm", "mask_libs", "recog", "local")`; `caps.RECOG_PROBE_S = 20`.
  - `caps.recog_python(environ) -> str | None`: `SVF_RECOG_PYTHON` when it names an executable file (`os.access(p,
    os.X_OK)`) **and** `recog_dir(environ, probe=False)` is a directory with `recog.py`, and
    `subprocess.run([p, "-I", "-c", "import numpy, torch, PIL, fontTools"], env={"PATH": environ.get("PATH",
    "/usr/bin:/bin"), "HOME": environ.get("HOME", "/"), "LANG": "C.UTF-8"}, stdin=DEVNULL, stdout=DEVNULL,
    stderr=DEVNULL, timeout=RECOG_PROBE_S)` returns 0; else None (a timeout or `OSError` is None).
  - `caps.recog_dir(environ, probe=True)`: today's rule when `probe`; with `probe=False` only the directory test.
  - `caps.compute(static_dir, environ, local=False) -> dict`: the four public keys plus private `"recog_python": str
    | None` and `"recog_dir": str | None`. With `SVF_RECOG_PYTHON` set: `recog_python = recog_python(environ)`,
    `recog_dir = <the dir>` when that succeeded, `recog = recog_python is not None`. Without it: `recog_dir =
    recog_dir(environ)` (today), `recog_python = None`, `recog = recog_dir is not None`.
  - `server.Handler._caps` -> `{key: bool(self.server.caps.get(key)) for key in caps.PUBLIC_KEYS}`.
  - `toolrun.recog_argv(caps: dict, repo_dir: str) -> list | None`: None when not `caps.get("recog")`;
    `[caps["recog_python"], "-P", <repo_dir>/maker/recog_score.py]` when `recog_python` is set; else
    `toolrun.maker_script("recog_score")`.
  - `Worker._identity`: `prefix = toolrun.recog_argv(self.caps, self.repo_dir)`; None -> today's structural result;
    the step env adds `SVF_RECOG_DIR=self.caps.get("recog_dir")` (a missing value is the structural result, never
    `None` in an env). No `caps.recog_dir` call per step.

- [ ] **Step 1: Write the failing tests** (`test_server.py`, new class `RecogCapsTest`; a temp dir under `TMPDIR` holds
  a stub `recog.py` and executable shell stubs written by the test):

```python
def test_external_interpreter_probe_ok(self):        # stub "#!/bin/sh\nexit 0": compute(...)["recog"] is True,
                                                     # ["recog_python"] == stub, ["recog_dir"] == the dir
def test_external_interpreter_probe_fails(self):     # stub exit 1 -> recog False, recog_python None
def test_external_interpreter_probe_times_out(self): # stub "exec sleep 30", RECOG_PROBE_S patched to 0.5: False within 3 s
def test_external_interpreter_needs_recog_py(self):  # SVF_RECOG_DIR without recog.py: the stub never runs (a marker file
                                                     # it would write is absent), recog False
def test_probe_env_is_scrubbed(self):                # a stub that writes `env` to a file: keys == {PATH, HOME, LANG}
def test_api_caps_public_keys_only(self):            # ApiTest server with caps patched to include recog_python="/x":
                                                     # GET /api/caps keys == set(caps.PUBLIC_KEYS), all booleans
```

  `test_toolrun.py`:

```python
def test_recog_argv(self):
    self.assertIsNone(toolrun.recog_argv({"recog": False}, "/R"))
    self.assertEqual(toolrun.recog_argv({"recog": True, "recog_python": "/py"}, "/R"), ["/py", "-P", "/R/maker/recog_score.py"])
    self.assertEqual(toolrun.recog_argv({"recog": True, "recog_python": None}, "/R"), toolrun.maker_script("recog_score"))
```

  `test_jobs.py`: `run_identity(caps_value, ...)` (`:650`) drops the `caps.recog_dir` patch and merges
  `{"recog_dir": stub, "recog_python": None}` into `caps_value` when `caps_value.get("recog")`; every caller
  (`:693,709,718,726,735`) keeps passing `{"recog": True}`. New `test_identity_no_per_step_probe`: `caps.recog_dir`
  patched to raise; a jamo step's identity still runs. `test_local.py:527`: the same change.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_server.py -k RecogCapsTest` and `-p
  test_toolrun.py -k recog`. Expected: FAIL.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run** `test_server.py`, `test_jobs.py`, `test_local.py`, `test_toolrun.py`, `test_recog_score.py`.
  Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (expected **943**), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: optional recogniser through SVF_RECOG_PYTHON (probed once at start, four packages, scrubbed env); /api/caps serves the public keys only (t_f04f1355)"`.

Cannot verify here: a real recogniser (numpy/torch are not installed). How it degrades: the probe is driven with shell
stubs; Task 4 runs a stub interpreter against the frozen sidecar end to end.

**Group A review gate.** The reviewer reads Task 1 Step 6's counts and diff, runs `test_toolrun.py` with `FROZEN`
patched, and checks `GET /api/caps` keys.

---

# Group B: the sidecar (slice S2)

Tasks 3 -> 4, sequential, after Group A (`jobs.py`, `preview.py`, `server.py`, `localfx.py`). One review after Task
4; the reviewer runs the frozen test themselves.

### Task 3: server lifecycle for a shell: early signals, `--exit-with-parent`, the tool registry, one stop (slice S2, part 1)

**Files:**
- Create: `maker/toolreg.py`, `maker/test/test_toolreg.py`, `maker/test/parent_harness.py`
- Modify: `maker/server.py` (`main`, `make_server`, `_Server.server_close`, `terminate`), `maker/jobs.py`
  (`run_command`, `Worker.stop`), `maker/preview.py` (`run_bounded`), `maker/toolrun.py` (`set_pdeathsig`, `alive`)
- Test (modify): `maker/test/test_server_signals.py`, `test_jobs.py`, `test_preview.py`,
  `maker/test/test_sidecar_imports.py` (`EXPECTED` gains `toolreg`)

**Interfaces:**
- Produces (`maker/toolrun.py`):
  - `set_pdeathsig(sig: int) -> bool`: Linux only, `ctypes` `prctl(PR_SET_PDEATHSIG=1, sig)`; False (no exception)
    elsewhere or on failure, and False without calling prctl when `os.environ.get("SVF_MAKER_NO_PDEATHSIG") == "1"`.
    The knob reaches a tool because `base_env` forwards it (Task 1); it is set only by tests.
  - `alive(pid: int) -> bool`: `/proc/<pid>/stat` exists and its state field (after the last `)`) is not `Z` or `X`;
    off Linux `os.kill(pid, 0)` succeeds (a zombie then counts as alive: darwin limitation, noted).
- Produces (`maker/toolreg.py`):
  - `REAP_EACH_S = 5.0`, `REAP_TOTAL_S = 10.0`.
  - `class Registry(path: str)`: the file `<data_root>/tools.pids` and its lock `tools.pids.lock` (`fcntl.flock`).
    `register(proc)` appends `"<pgid> <pid> <start time> <basename(argv0)>\n"` (pgid = pid: `start_new_session`; the
    basename is informational and never decides a kill) and stores the registry on the object (`proc._svf_registry =
    self`); `unregister(proc)` removes that line from **the registry recorded on `proc`** (a later activation of
    another registry never strands it). An `OSError` prints one line `toolreg: <errno name>` to stderr and is ignored.
  - `activate(reg: Registry | None)`, `deactivate(reg)` (clears only when `reg` is the active one), `active() ->
    Registry | None`: the process-wide registry the runners use. Nothing is active at import, so unit tests that call
    the runners directly are unregistered by construction.
  - `register(proc)` / `unregister(proc)` (module functions): `active().register(proc)` when one is active, and
    `proc._svf_registry.unregister(proc)` when `proc` carries one; else no-op.
  - `start_time(pid) -> str | None`: `/proc/<pid>/stat` field 22 (parsed after the last `)`), else `ps -o lstart= -p`
    on darwin, else None.
  - `Registry.reap() -> dict`: `{"killed": n, "stale": n, "stuck": n}`. A line is **live** when `toolrun.alive(pid)` and
    `start_time(pid)` equals the recorded value - **whatever its argv0**: an external recogniser interpreter, a
    source-mode `python3`, or a frozen tool of an AppImage mounted at another path are all reaped (design issue 18).
    Live: `os.killpg(pgid, SIGKILL)`, then wait until `not toolrun.alive(pid)` (`REAP_EACH_S` each, `REAP_TOTAL_S`
    overall); still alive -> `stuck`. Not live -> `stale` (not signalled). Then the file is truncated.
- Produces (runners): `jobs.run_command` / `preview.run_bounded` call `toolreg.register(proc)` right after `Popen` and
  `toolreg.unregister(proc)` when the child is reaped (`run_command`'s `finally` after the last `_signal_group`;
  `run_bounded`'s `finally`).
- Produces (`maker/server.py`):
  - `make_server(...)`: right after `store = jobs.Store(data_root)`: `reg = toolreg.Registry(<data_root>/tools.pids)`;
    `reg.reap()`; `toolreg.activate(reg)`; `server.toolreg = reg` - all before `caps.compute`, `worker.recover()` and
    `startup_cleanup()` (design issue 5). **Partial construction:** everything after the worker exists runs inside
    `try/except BaseException`: on any exception (a `KeyboardInterrupt` from `terminate` included) it calls
    `worker.stop()`, closes the socket if bound, `toolreg.deactivate(reg)`, and re-raises.
  - `_Server.server_close()` (and `_Server6`'s) calls `toolreg.deactivate(self.toolreg)` after the base close.
  - `Worker.stop(timeout=30)`: a completed stop sets `self._stopped = True`; a later call returns the first call's
    result at once (no second sweep).
  - `main(argv=None)`: (1) parse `argparse.ArgumentParser(prog="server.py")` with `--exit-with-parent PID` (int;
    unknown option -> exit 2); (2) **install `terminate` for SIGTERM/SIGINT first** (it raises `KeyboardInterrupt` as
    today, and calls `_detach_stdio()` when `--exit-with-parent` was given and `os.getppid() != PID`); (3) with the
    option: `toolrun.set_pdeathsig(signal.SIGTERM)`, then start daemon thread `svf-maker-parent-watch` (every 2 s:
    `os.getppid() != PID` -> `_detach_stdio()`, `os.kill(os.getpid(), SIGTERM)`), and check `os.getppid() != PID`
    once right away (the parent may already be gone); (4) `make_server` inside `try/except KeyboardInterrupt: exit 0`
    (no port line, the partial-construction cleanup has run); (5) the port line, `atexit`, `serve_forever` and the
    `finally` as today. `server._detach_stdio()`: `os.dup2` of `/dev/null` onto fds 1 and 2, once.
- Produces (`maker/test/parent_harness.py`, a script): `python3 -P parent_harness.py OUT.json -- CMD...` makes itself a
  child subreaper (`prctl(PR_SET_CHILD_SUBREAPER=36, 1)`), forks a **helper** that starts `CMD` with stdout/stderr
  piped to the helper and `--exit-with-parent=<helper pid>` appended, relays the server's lines to the harness, and
  sleeps; the harness writes `{"helper": pid, "server": pid}` as soon as both exist, waits for the test's `kill`
  file, SIGKILLs the helper, `waitpid`s the reparented server (bounded 10 s) and writes `{"status": <exit code or
  -signal>, "seconds": s, "lines": [...]}`. The subreaper flag lives in the harness, never in the unittest process.

- [ ] **Step 1: Write the failing tests.** `maker/test/test_toolreg.py` (each test `addCleanup(toolreg.deactivate,
  reg)`; `tearDown` asserts `toolreg.active() is None`):

```python
def test_line_while_running_none_after(self):     # activate(Registry(tmp)); a run_command child sleeping 2 s on a thread:
                                                  # one line naming its pid while it runs; 0 lines after
def test_run_bounded_registers(self):             # same for preview.run_bounded
def test_inactive_is_noop(self):                  # nothing active: run_command works, no tools.pids anywhere under TMPDIR
def test_unregister_uses_the_registering_registry(self):  # register under A, activate B, unregister: A empty, B untouched
def test_reap_kills_matching_group(self):         # a sleeper Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                                  # start_new_session=True) + a grandchild; line with the real start time:
                                                  # reap() -> killed 1, stuck 0 (zombie counts as gone); proc.wait() after;
                                                  # the grandchild gone; file empty
def test_reap_ignores_argv0(self):                # the same with argv0 "python3-external" and with
                                                  # "/tmp/.mount_old/resources/sidecar/svf-maker-sidecar" (as text): killed
def test_reap_external_interpreter(self):         # a shell-script "interpreter" (#!/bin/sh exec sleep 60) started through
                                                  # run_command on a thread with Registry active, then the registry file is
                                                  # read by a fresh Registry(...).reap(): killed 1
def test_reap_leaves_stale_line(self):            # the same sleeper with start time "1": stale 1, still alive (killed in cleanup)
def test_reap_bounded(self):                      # killpg patched to do nothing: returns within REAP_TOTAL_S + 1 s, stuck 1
def test_alive_zombie(self):                      # a child that exited and is not waited: toolrun.alive(pid) False
def test_server_close_deactivates(self):          # make_server(...) then server_close(): toolreg.active() is None
```

  `test_jobs.py`: `test_stop_twice_sweeps_once` (`sweep_local_files` patched to count; `stop()` twice -> count 1, the
  second call under 0.1 s). `test_server.py` (`LocalBindTest` neighbour): `test_make_server_cleans_up_on_interrupt`:
  `jobs.Store.retry_pending_sweeps` patched to raise `KeyboardInterrupt` (with the token, so `startup_cleanup` runs):
  `make_server` raises it; no thread named like the worker is alive; `toolreg.active() is None`.
  `test_server_signals.py` (the exit-with-parent tests run through `parent_harness.py`; `skipTest` off Linux):

```python
def test_main_refuses_unknown_option(self):        # python3 -P maker/server.py --nope -> exit 2, stdout empty
def test_reap_before_cleanup(self):                # tools.pids names a live sleeper group (real start time); start the server
                                                   # subprocess with the token: at the port line the sleeper is not alive
                                                   # (toolrun.alive) and tools.pids is empty; the test waits its own child
def test_exit_with_parent_pdeathsig(self):         # after the port line, a local job created over HTTP; harness kills the
                                                   # helper: status 0 within 5 s, the job's .svf-maker-<id>/ gone
def test_exit_with_parent_poll(self):              # the same with SVF_MAKER_NO_PDEATHSIG=1 (the 2 s poll path alone)
def test_exit_with_parent_during_startup(self):    # SVF_RECOG_PYTHON = a stub "exec sleep 60" (+ a recog.py dir): the probe
                                                   # blocks start-up; the helper is killed 1 s after start: status 0 within
                                                   # 5 s, no port line, the stub sleeper's pid (it writes it to a file) not alive
def test_sigterm_during_startup_cleanup(self):     # SIGTERM to the server (no exit-with-parent) while the same stub blocks:
                                                   # exit 0, no traceback on stderr, no port line
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_toolreg.py'` and `-p
  test_server_signals.py`. Expected: FAIL (`No module named 'toolreg'`, unknown option accepted).
- [ ] **Step 3: Implement** to the interfaces (the registry line format and lock as stated; spec 12 left them open).
- [ ] **Step 4: Run** `test_toolreg.py`, `test_server_signals.py`, `test_server.py`, `test_jobs.py`,
  `test_preview.py`, `test_local.py`, `test_sidecar_imports.py`. Expected: `OK`; `find $TMPDIR -name tools.pids` after
  the run lists no file outside directories the tests removed (registry hygiene).
- [ ] **Step 5: Gates** G1, G2 (expected **964**), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: signals from the first line of main, --exit-with-parent (getppid poll + PR_SET_PDEATHSIG, stdio detached), partial-construction cleanup, tool registry by pid + start time reaped before recover, Worker.stop sweeps once (t_f04f1355)"`.

Cannot verify here: macOS `ps -o lstart` start times and zombie detection (the darwin branches are untested); a
`D`-state process during the reap. How it degrades: the reap's bound is tested with `killpg` patched.

### Task 4: `maker/sidecar.py`, the PyInstaller spec, the build script, the frozen test (slice S2, part 2)

**Files:**
- Create: `maker/sidecar.py`, `maker/sidecar.spec`, `maker/build-sidecar.sh`, `desktop/build/requirements-sidecar.txt`,
  `maker/test/test_sidecar.py`, `maker/test/test_frozen.py`
- Modify: `maker/test/localfx.py` (`LocalRunBase` moved here from `test_local.py`, `LocalBase.owns`,
  `SubprocessLocalBase`), `maker/test/test_local.py` (imports `LocalRunBase` from `localfx`),
  `maker/test/inputfx.py` (`big_composite_ttf`), `maker/test/test_sidecar_imports.py` (roots)

**Interfaces:**
- Consumes: `toolrun.*`, `toolrun.set_pdeathsig`, `server.main(argv)`, `toolreg.REAP_TOTAL_S`,
  `server.STARTUP_CLEANUP_S`, `jobs.STOP_SWEEP_TOTAL_S`, `caps.RECOG_PROBE_S` (Tasks 1-3).
- Produces (`maker/sidecar.py`):
  - `VERSION = "0.1.0"` (the same string as `desktop/package.json` `version`; Task 6 pins the equality - design
    issue 9).
  - `TOOLS: dict[str, tuple[str, str]]`: name -> (`"tools"` | `"maker"` | `"module"`, `"bare"` | `"exit"` |
    `"args"`), exactly the spec 7.1 table: `jamoset jamovec mkfont bdfface johab844` bare; `macfbit_svf macfbit3
    macsfnt svf2to3 svfdy svfline` exit; `srcprep` (`maker`, exit); `instancer` (`module`, args). One function
    `_entry_<name>()` per name holds that entry's import and returns its `main`.
  - `run_tool(name: str, args: list) -> NoReturn`: frozen and on Linux, `toolrun.set_pdeathsig(signal.SIGKILL)` first;
    when it returned True and `os.path.realpath("/proc/%d/exe" % os.getppid()) != os.path.realpath(sys.executable)`,
    `os._exit(1)` (the sidecar died before the prctl: the tool's only legitimate parent is the sidecar executable);
    unknown name -> stderr `run-tool: unknown tool 'X'`, exit 2; `sys.argv = [name + ".py", *args]` (bare: `main();
    sys.exit(0)`; exit: `sys.exit(main())`; args: `sys.exit(main(args))`); any exception other than `SystemExit` ->
    `traceback.print_exc()`, exit 1.
  - `SMOKE: dict[str, tuple[list, int, str, str]]`: per name the smoke argv, exit code, stream and expected prefix:
    every name `(["--help"], 0, "stdout", "usage: <name>.py")`, instancer `(..., "usage: fonttools varLib.instancer")`,
    **`svfline` `(["--help"], 1, "stderr", "  svfline.py line W H X Y")`** (it has no argparse).
  - `GRAPH_MODULES: tuple[str, ...]`: the reachable set of `test_sidecar_imports.reachable(["sidecar"])`, sorted.
  - `selfcheck() -> dict`: `{"frozen", "version", "build_id" (BUILD_ID beside `SVF_MAKER_REPO` or "unknown"),
    "python", "flags": {"isolated", "ignore_environment", "safe_path", "no_site"}, "path", "tools": sorted(TOOLS),
    "modules": {name: null | "<error>"} for every GRAPH_MODULES name imported, "budget": {"startup_cleanup_s",
    "stop_timeout_s" (Worker.stop's default via inspect), "stop_sweep_s", "reap_total_s", "recog_probe_s"}}`.
  - `main(argv=None)`: `serve [ARGS]` -> `server.main(ARGS)`; `run-tool NAME ARGS...`; `selfcheck` (JSON, exit 0 when
    every module imported, else 1); `--version` -> `svf-maker-sidecar 0.1.0 <build id> python <x.y.z>`; anything else
    -> usage on stderr, exit 2. Source mode inserts `maker/` and `tools/` into `sys.path` first (as `server.py`).
- Produces (`maker/build-sidecar.sh [--no-test]`), `set -euo pipefail`, from the checkout root, `T=${SVF_DESKTOP_TMP:-$HOME/work/tmp/svf-desktop-build}`
  (created with its README): `bash maker/build-wasm.sh` (stops with its own message without emsdk); `pip install
  --target $T/pysite -r desktop/build/requirements-sidecar.txt` (skipped when `$T/pysite/.ok` holds the requirements'
  sha256); `SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)`; `TMPDIR=$T PYTHONPATH=$T/pysite python3 -S -m PyInstaller
  --noconfirm --clean --workpath $T/pyi-work --distpath desktop/build/out/sidecar maker/sidecar.spec`; stage
  `desktop/build/out/repo/` = `svf/` whole, `web/mkindex.py`, `web/LICENCES.tsv`, `web/FAMILIES.tsv`, `tools/*.py`
  and `maker/*.py` without `test_*.py`, no `__pycache__`, no `testdata/`; write `desktop/build/out/repo/BUILD_ID` =
  `"<git describe --always --dirty> <commit date YYYY-MM-DD> sidecar 0.1.0"`; `selfcheck` under `env -i`; unless
  `--no-test`, run `python3 -m unittest discover -s maker/test -p test_frozen.py` (plain host `python3`: the test
  process only drives subprocesses) with `SVF_MAKER_SIDECAR=<abs path>`, `SVF_MAKER_REF_SITE=$T/pysite` (absolute),
  `SVF_MAKER_STAGED_REPO=<abs desktop/build/out/repo>`, `SVF_MAKER_FROZEN_REQUIRED=1`.
- Produces (`maker/test/localfx.py`):
  - `LocalRunBase` (moved verbatim from `test_local.py`, so `test_frozen.py` can subclass it without unittest
    collecting `test_local`'s tests there) gains `select_johab844(jid)`: `b/HAN.FNT` also `precomposed` 16 px 1 bpp
    with `eng` `b/ENG.FNT` (the johab844 route, `routes.py:436`), dest `dos`.
  - `LocalBase.owns(jid)` (in-process: `self.srv.worker.owns(jid)`); `wait_done` calls `self.owns`.
  - `SubprocessLocalBase(LocalBase)`: `setUp` starts `[SVF_MAKER_SIDECAR, "serve"]` with `{PATH: <empty dir under
    TMPDIR>, HOME, LANG, SVF_MAKER_TOKEN, SVF_MAKER_BIND=127.0.0.1:0, SVF_MAKER_DATA, SVF_MAKER_REPO}` plus
    `self.extra_env()` (overridable), reads the port line (2 s), sets `self.port`, `self.proc`; `_stop` SIGTERMs and
    waits; `owns(jid)` is False once the job's state has been final on two polls 0.2 s apart.
  - `normalise_job(out_dir, job) -> dict`: `{"files": sorted paths of result.files with build-<12 hex> -> build-<id>
    and .svf-maker-<12 hex> -> .svf-maker-<id>}`, `"faces": {rel path: sha256}` for every written `.SVF`,
    `"commands": [toolrun.note_argv(argv, repo) with the same two substitutions for every step argv]}`.
- Produces (`maker/test/inputfx.py`): `big_composite_ttf(n: int) -> bytes`: the composite fixture with `n` composite
  Hangul glyphs (the implementer picks `n` so that `jamovec master` runs at least 20 s here, and records the measured
  seconds in a comment; spec 12 leaves the size open).

- [ ] **Step 1: Write the failing source-mode tests** `maker/test/test_sidecar.py` (run `python3 -P maker/sidecar.py
  ...` as a subprocess):

```python
def test_table_is_the_spec_table(self):     # sorted(sidecar.TOOLS) == ["bdfface","instancer","jamoset","jamovec","johab844",
                                            #  "macfbit3","macfbit_svf","macsfnt","mkfont","srcprep","svf2to3","svfdy","svfline"]
def test_every_tool_smoke(self):            # for each name, sidecar.SMOKE[name]: exit code and the stream's prefix as stated
def test_unknown_tool(self):                # run-tool nosuch -> exit 2, stderr "run-tool: unknown tool 'nosuch'"
def test_traceback_exit_1(self):            # run-tool mkfont <a directory>.ttf OUT --size 16 --bpp 1 -> exit 1 and "Traceback"
                                            # in stderr (the implementer confirms mkfont does not catch it; if it does,
                                            # the test uses the first tool that does not and names it here)
def test_bare_main_exit_code(self):         # run-tool mkfont with valid args -> exit 0, output cmp-equal to python3 -P tools/mkfont.py
def test_selfcheck_source(self):            # frozen False, tools == the table, every modules value null,
                                            # budget == {30.0, 30, 8.0, 10.0, 20}
def test_version(self):                     # --version matches r"^svf-maker-sidecar 0\.1\.0 .+ python 3\.\d+\.\d+$"
def test_serve_passes_args(self):           # serve --nope -> exit 2 (server.main's parser)
```

  `test_sidecar_imports.py`: `ROOTS = ["sidecar"]`; `test_reachable_set` asserts the computed set ==
  `set(sidecar.GRAPH_MODULES)` and that it contains `EXPECTED | {"sidecar", "toolreg"}`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_sidecar*.py'`. Expected: FAIL.
- [ ] **Step 3: Implement** `maker/sidecar.py`; move `LocalRunBase` to `localfx` (and `test_local.py`'s import). Run
  Step 2 again and `-p test_local.py`: `OK`.
- [ ] **Step 4: Write** `maker/sidecar.spec` exactly as spec 8.3 (the `HIDDEN` lists computed before `Analysis`,
  `pathex` maker + tools, `datas` static, the full `excludes` list, `upx=False`, `strip=False`, `console=True`,
  name `svf-maker-sidecar`), `desktop/build/requirements-sidecar.txt`, `maker/build-sidecar.sh`.
- [ ] **Step 5: Build** `~/.local/bin/heavy bash maker/build-sidecar.sh --no-test` (announce). Expected:
  `desktop/build/out/sidecar/svf-maker-sidecar/svf-maker-sidecar` exists; `du -sm` of its directory <= 60; the
  `selfcheck` line with every module `null`; `_internal` has no `wx`, `numpy`, `setuptools`, `pkg_resources`,
  `libreadline*`, `libtinfo*`.
- [ ] **Step 6: Write the frozen tests** `maker/test/test_frozen.py`. Every class needs `SVF_MAKER_SIDECAR` (an
  executable); the byte-equal classes also need `SVF_MAKER_REF_SITE`. A missing variable is `skipTest` naming it,
  **unless `SVF_MAKER_FROZEN_REQUIRED=1`, which turns it into a failure** (the build script and the release check set
  it, so a required class can never pass by skipping). `S` = the sidecar; `ENVI` = `{"PATH": <empty dir under
  TMPDIR>, "HOME": home, "LANG": "C.UTF-8", "PYTHONPATH": <dir holding a planted json.py that raises>}`; `REPO` =
  `SVF_MAKER_STAGED_REPO` or the checkout. Reference = `[/usr/bin/python3 (shutil.which at test time), "-S", "-P",
  <checkout>/tools/X.py]` with `PYTHONPATH=$SVF_MAKER_REF_SITE`; `ref_python` = an executable wrapper written under
  `TMPDIR`: `#!/bin/sh\nPYTHONPATH=<ref site> exec <abs python3> -S "$@"`:

```python
class FrozenSelfcheckTest:
    def test_selfcheck(self):                  # frozen True; the four flags True; every path entry under dirname(S);
                                               # tools == the table; set(modules) == set(sidecar.GRAPH_MODULES), all null;
                                               # budget == the Python constants imported in this test process
class FrozenRunToolTest:
    def test_every_tool_smoke_isolated(self):  # each name, env ENVI, cwd = a dir holding a planted jamoset.py that raises:
                                               # sidecar.SMOKE expectations; nothing shadowed
    def test_unknown_and_traceback(self):      # nosuch -> 2; Step 1's raising input -> 1, "Traceback", no "[PYI-"
class FrozenByteEqualTest:                     # the OFL sample set + fixtures, frozen output cmp-equal to the reference
    def test_mkfont_neodgm_16_1(self):         # ttf/neodgm/neodgm.ttf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul (115,460 bytes)
    def test_mkfont_nanumgothic_17_2(self):    # ttf/nanumgothic/NanumGothic-Bold.ttf --size 17 --bpp 2 (207,684 bytes)
    def test_jamoset_dos_844(self):            # localfx's b/HAN.FNT (fixtures._dos_raw), --layout 844 --check -o OUT
    def test_jamoset_from_ttf_adaptive(self):  # fixtures._composite_ttf, --layout adaptive --from-ttf --size 16
    def test_srcprep_ttc_face(self):           # inputfx.ttc([...]) ttc-face --index 1
    def test_instancer_real_op(self):          # inputfx.variable_ttf() wght=400 -o OUT
    def test_macsfnt_extract_unicode(self):    # inputfx.fork([...sfnt...]) extract --id 128, then unicode
    def test_johab844(self):                   # b/HAN.FNT + REPO/svf/dos/NEODG16.SVF + --eng b/ENG.FNT
    def test_debian_pillow_informational(self):# mkfont 16/1 with plain python3 -P: prints "equal" or "differs: <sizes>"; never fails
class FrozenServeTest(localfx.SubprocessLocalBase):
    def test_port_line_fast(self):             # the port line within 2 s on a clean data root
    def test_stale_files_swept_before_port(self):  # a planted pending-sweeps record + stale .svf-maker-<id>/: gone at the line
    def test_http_basics(self):                # / 200; /static/wasm/svf.wasm 200 application/wasm; /api/caps 403 then 200
                                               # {"wasm": true, "mask_libs": false, "recog": false, "local": true}
    def test_bad_token_and_bind(self):         # SVF_MAKER_TOKEN=xyz -> exit 2 "SVF_MAKER_TOKEN: 32 hex characters";
                                               # good token + 0.0.0.0:0 -> exit 2 "local mode binds 127.0.0.1 or ::1 only"; stdout empty
class FrozenJobTest(localfx.SubprocessLocalBase, localfx.LocalRunBase):
    # the reference: an in-process localfx.LocalBase server (REPO as repo) with toolrun.PYTHON patched to ref_python, so
    # its tools run the pinned wheels; both runs: select() + select_johab844(), run_to_done
    def test_frozen_jobs_match_source(self):   # normalise_job(...) of both runs equal ("files", "faces", "commands");
                                               # a johab844 step present (prefix_name)
    def test_frozen_notes_equal_source(self):  # every *.TXT note and build-<id>/BUILD.md equal after the build-<id> /
                                               # .svf-maker-<id> substitution; no line contains dirname(S), REPO or "run-tool";
                                               # the johab844 comment line present in both
    def test_jamo_adaptive_job(self):          # a jamo adaptive job of a/Munjo.ttf -> done
    def test_sigterm_cancels_tool(self):       # a job on big_composite_ttf; once its step runs (its pid from tools.pids),
                                               # SIGTERM the sidecar: exit 0; the tool pid not alive; the files dir gone;
                                               # tools.pids empty
    def test_sigkill_sidecar_kills_tool(self): # the same job, SIGKILL the sidecar: the tool pid not alive within 3 s
    def test_sigkill_without_pdeathsig_reaped_on_restart(self):  # extra_env {"SVF_MAKER_NO_PDEATHSIG": "1"} (it reaches
                                               # the tool through base_env): after SIGKILL the tool is alive and named in
                                               # tools.pids; a new serve on the same data root: the tool not alive at its
                                               # port line, the files dir gone, the job "failed" with error "interrupted"
class FrozenRecogTest(localfx.SubprocessLocalBase, localfx.LocalRunBase):
    def test_recog_unconfigured(self):         # no SVF_RECOG_*: caps recog false; a jamo step's identity {"available": false}
    def test_recog_external_stub(self):        # extra_env: SVF_RECOG_DIR = a dir with test_recog_score.write_stub(...);
                                               # SVF_RECOG_PYTHON = a stub script under TMPDIR:
                                               #   #!/bin/sh
                                               #   [ "$1" = -I ] && [ "$2" = -c ] && exit 0      # the 7.7 probe
                                               #   for a; do [ "$a" = numpy ] && a=lists; set -- "$@" "$a"; shift; done
                                               #   exec <abs /usr/bin/python3> "$@"               # an absolute path: PATH is empty
                                               # (the stub selects --arrays lists for this subprocess only: jobs.RECOG_ARRAYS
                                               # stays "numpy" - design issue 20); REPO is the staged repo with maker/ and
                                               # tools/ sources: caps recog true, the step's identity.json exists
```

- [ ] **Step 7: Run** `~/.local/bin/heavy bash maker/build-sidecar.sh` (announce). Expected: `test_frozen` `OK`,
  **0 skipped** (it runs with `SVF_MAKER_FROZEN_REQUIRED=1`), `selfcheck` clean. Then run the suite without the
  variables: every `test_frozen` class skipped with its message.
- [ ] **Step 8: Gates** G1, G2 (expected **~996**: +8 `test_sidecar`, ~24 `test_frozen` all skipped -> skipped ~38;
  record the observed N and skips), G3.
- [ ] **Step 9: Commit** `git add maker/sidecar.py maker/sidecar.spec maker/build-sidecar.sh
  desktop/build/requirements-sidecar.txt maker/test/test_sidecar.py maker/test/test_frozen.py maker/test/localfx.py
  maker/test/test_local.py maker/test/inputfx.py maker/test/test_sidecar_imports.py && git commit -m "maker: frozen sidecar (serve | run-tool | selfcheck), PyInstaller one-dir spec and build script; frozen test byte-equal to the pinned wheels under env -i (t_e64a56a7, t_f04f1355)"`.
  The commit body records: sidecar size, build seconds, frozen test counts, the Debian-Pillow comparison result.

Cannot verify here: macOS/Windows freezes (8.11); glibc < 2.39; `JAMOSET_PYLIB` with real 3.12 freetype-py/uharfbuzz
in the frozen process (`mask_libs` stays false and the test asserts that); a real recogniser. How it degrades: the
recogniser runs through a stub interpreter in lists mode; the byte-equal reference is the pinned wheels through
`python3 -S`, not a venv.

**Group B review gate.** The reviewer runs `~/.local/bin/heavy bash maker/build-sidecar.sh` and the frozen test
themselves (0 skipped), opens `selfcheck`, and checks that no pid recorded in the run's `tools.pids` files is alive
and that the runner has no zombie children afterwards.

---

# Group C: the shell (slice S3)

Task 5 starts after Task 3 has landed (its budget test reads `toolreg.REAP_TOTAL_S` and `caps.RECOG_PROBE_S`), in its
own worktree alongside Task 4 (`desktop/` only; `.gitignore` already done in Task 1); it rebases and reruns G1/G4
before landing. Task 6 starts after Tasks 4 and 5 have both landed, in the main worktree (its dev command needs Task
3's flag; its packaged pass and version test need Task 4's sidecar, rebuilt in this worktree with
`build-sidecar.sh`). One review after Task 6; the reviewer runs G5.

### Task 5: `desktop/` package and pure helpers with node unit tests (slice S3, part 1)

**Files:**
- Create: `desktop/package.json`, `desktop/package-lock.json`, `desktop/lib/{env,portline,guard,budget,shutdown,
  restart,sandbox,paths,log,state}.js`, `desktop/test/unit.test.js`

Module form (spec 12 leaves it to the builder): **CommonJS everywhere** (`.js`, no `"type"` field), so `main.js`,
the sandboxed `preload.js` and the helpers share one form and `node --test` loads them directly (design issue 10).

**Interfaces (produced):**
- `package.json`: `name "svf-maker"`, `version "0.1.0"`, `description`, `author`, `private true`, `main "main.js"`,
  `license "MIT"`, `desktopName "svf-maker.desktop"` (a `package.json` field, not a `build` key), no `dependencies`,
  `devDependencies {"electron": "45.2.3", "electron-builder": "26.18.0"}`, `scripts {"test": "node --test
  test/unit.test.js", "e2e": "bash test/run-e2e.sh"}` (Task 7 appends `test/third-party.test.js`).
- `env.js`: `ENV_KEYS = ["PATH","HOME","LANG","SVF_MAKER_TOKEN","SVF_MAKER_BIND","SVF_MAKER_DATA","SVF_MAKER_REPO",
  "SVF_MAKER_ROOTS","JAMOSET_PYLIB","JAMOSET_MASK_FONT","SVF_RECOG_DIR","SVF_RECOG_PYTHON"]`, `PASS_KEYS` = the last
  five; `buildEnv(parentEnv, {repo, data}) -> {env, token}`: `token = crypto.randomBytes(16).toString("hex")`,
  `LANG "C.UTF-8"`, `SVF_MAKER_BIND "127.0.0.1:0"`, `PATH`/`HOME` from `parentEnv` (defaults `/usr/bin:/bin`,
  `os.homedir()`), pass-throughs only when set and non-empty.
- `portline.js`: `parsePortLine(text) -> {host, port} | null` with `/^svf-maker listening on (127\.0\.0\.1|::1):(\d+)\r?\n/m`.
- `guard.js`: `isOurs(origin, url, {startingUrl, devtools}) -> bool` (spec 6.3: `url === origin + "/"` or
  `startsWith(origin + "/")`, the exact `startingUrl`, `data:` URLs (the page's `<link rel="icon" href="data:,">`),
  `devtools://` only when `devtools`); `withToken(url, headers, sidecar) -> headers` (a new object: every key equal to
  `x-maker-token` case-insensitively removed; `X-Maker-Token = sidecar.token` only when `url.startsWith(sidecar.origin
  + "/")` and the pathname starts with `/api/`).
- `budget.js`: `SERVER = {startupCleanupS: 30, recogProbeS: 20, reapTotalS: 10, stopTimeoutS: 30, joinS: 1,
  stopSweepS: 8}`, `HANDSHAKE_S = 75`, `STOP_WAIT_S = 45`, `KILL_WAIT_S = 5`, `STARTING_PAGE_S = 2`.
- `shutdown.js`: `stopSidecar(child, {termWaitS, killWaitS, kill = process.kill}) -> Promise<{code, signal,
  escalated}>`: `kill(-child.pid, "SIGTERM")`, wait for `exit` up to `termWaitS`, then `kill(-child.pid, "SIGKILL")`
  and wait `killWaitS`; resolves at once when the child has already exited; `ESRCH` ignored.
- `restart.js`: `restartAllowed(history: number[], now: number) -> boolean` (fewer than 3 entries within 300,000 ms).
- `sandbox.js`: `readSandbox(pid, readFile = fs.readFileSync) -> {seccomp, noNewPrivs} | null`;
  `sandboxText(state, {noSandboxSwitch, userns}) -> string`: `"renderer sandbox: off (--no-sandbox; user namespaces
  <available|unavailable|unknown>)"`, `"renderer sandbox: on"` or `"renderer sandbox: unknown"` (the cause is not
  inferred from the switch; `userns` comes from one `unshare -Ur true` probe at start, its exit status only).
- `paths.js`: `resolveLaunch({resourcesPath, appDir, env, pid, userData, exists = fs.existsSync}) -> {mode, cmd, args,
  repo, data}`: packaged when `<resourcesPath>/sidecar/svf-maker-sidecar/svf-maker-sidecar` exists and
  `env.SVF_MAKER_DEV !== "1"`: `cmd` that path, `args ["serve", "--exit-with-parent=" + pid]`, `repo
  <resourcesPath>/repo`, `data <userData>/maker`; else dev: `cmd "python3"`, `args ["-P", <checkout>/maker/server.py,
  "--exit-with-parent=" + pid]`, `checkout = env.SVF_MAKER_DEV_REPO || path.dirname(appDir)`, `repo checkout`, `data
  <userData>/maker-dev`. `appDir` is always the directory of `main.js` (never `app.getAppPath()`).
- `log.js`: `createLog({dir, toStderr, maxBytes = 1 << 20}) -> {line(text), path}` (append `<ISO time> <text>\n` to
  `<dir>/shell.log`, rotate to `shell.log.1` past `maxBytes`, two files kept; `toStderr` mirrors); `pathsLine(channel,
  paths) -> "<channel>: <n>"`; `redactLine(text) -> string`: every run of `/` followed by non-space characters ->
  `<path>`, every 32-hex run -> `<hex>`, cut to 300 characters; `Ring(n)` with `push(line)` and `lines()` (the last
  `n`).
- `state.js`: `loadState(file) -> {bounds, zoom, lastOutputDir, handedOut: string[]}` (defaults on a missing or bad
  file), `saveState(file, state)` (atomic rename; writes only those four keys - no token, no input directory: D3 rules
  only the output folder; `handedOut` capped to the last 32 entries, stored as realpaths).

- [ ] **Step 1: Write the failing tests** `desktop/test/unit.test.js` (`node:test`, `node:assert/strict`; temp files
  under `os.tmpdir()`, which is `TMP_DIR`):

```js
test("parsePortLine", () => {
  assert.deepEqual(parsePortLine("svf-maker listening on 127.0.0.1:38253\n"), {host: "127.0.0.1", port: 38253});
  assert.equal(parsePortLine("svf-maker listening on 127.0.0.1:382"), null);          // no newline yet
  assert.equal(parsePortLine("noise\nsvf-maker listening on 127.0.0.1:5\nmore\n").port, 5);
  assert.deepEqual(parsePortLine("svf-maker listening on ::1:9\n"), {host: "::1", port: 9});
  assert.equal(parsePortLine("svf-maker listening on 0.0.0.0:9\n"), null);
});
test("isOurs", () => { const o = "http://127.0.0.1:4000", s = "file:///app/starting.html";
  // true: o + "/", o + "/api/caps", s, "data:,"; false: "http://127.0.0.1:4001/", "http://localhost:4000/", o (no slash),
  // "http://127.0.0.1:4000.evil/", "file:///etc/passwd", "devtools://devtools/x" (true only with {devtools: true})
});
test("withToken", () => { const sc = {origin: "http://127.0.0.1:4000", token: "a".repeat(32)};
  // /api/x -> exactly one key matching /x-maker-token/i, value sc.token, even when the input had "x-maker-token": "evil"
  //   and "X-MAKER-TOKEN": "evil2"; "/" and "/static/maker.js" -> no token key (an injected one removed);
  // "http://127.0.0.1:4001/api/x" (old port) -> no token key
});
test("buildEnv", () => { const parent = {...process.env, SVF_MAKER_TOKEN: "decoy", PYTHONPATH: "/x", SVF_RECOG_PYTHON: "/py"};
  // Object.keys(env) ⊆ ENV_KEYS; token matches /^[0-9a-f]{32}$/ and !== "decoy"; env.SVF_MAKER_TOKEN === token;
  // no PYTHONPATH; SVF_RECOG_PYTHON === "/py"; JAMOSET_PYLIB absent when unset or ""; two calls give different tokens
});
test("budget derives from the server", () => {
  // HANDSHAKE_S === 75 >= startupCleanupS + recogProbeS + reapTotalS; STOP_WAIT_S === 45 >= stopTimeoutS + joinS + stopSweepS;
  // SERVER matches the Python source by regex: maker/server.py STARTUP_CLEANUP_S = 30.0; maker/jobs.py STOP_SWEEP_TOTAL_S = 8.0
  // and "def stop(self, timeout=30)"; maker/caps.py RECOG_PROBE_S = 20; maker/toolreg.py REAP_TOTAL_S = 10.0
});
test("stopSidecar", async () => {
  // spawn(process.execPath, ["-e", "process.on('SIGTERM',()=>process.exit(0)); setInterval(()=>{},1e3)"], {detached: true})
  //   -> {code: 0, escalated: false} within 2 s; a child ignoring SIGTERM with termWaitS 0.3 -> escalated, signal "SIGKILL";
  // an already-exited child resolves at once
});
test("restartAllowed", () => { /* [] true; [t-1,t-2] true; [t-1,t-2,t-3] false; three entries older than 300 s true */ });
test("readSandbox / sandboxText", () => { /* "Seccomp:\t0\nNoNewPrivs:\t1\n" -> {seccomp: 0, noNewPrivs: 1};
  sandboxText({seccomp: 0}, {noSandboxSwitch: true, userns: "unavailable"}) ===
  "renderer sandbox: off (--no-sandbox; user namespaces unavailable)"; {seccomp: 2} -> "renderer sandbox: on" */ });
test("resolveLaunch", () => { /* packaged (exists stub true) and dev (false, or SVF_MAKER_DEV=1) shapes as the interface */ });
test("log rotation, redaction, ring", () => { /* maxBytes 100: three 60-byte writes -> shell.log + shell.log.1 only;
  pathsLine("pick-files", ["/home/u/a.ttf", "/b"]) === "pick-files: 2";
  redactLine("sweep: /home/u/out/.svf-maker-0123456789ab") === "sweep: <path>"; redactLine("tok " + "a".repeat(32)) === "tok <hex>";
  a Ring(50) fed 60 lines keeps the last 50 */ });
test("state keeps only the four keys", () => { /* saveState(f, {zoom: 1.1, token: "x", lastInputDir: "/in", handedOut: 40 paths});
  the file has no "token" and no "lastInputDir"; handedOut has the last 32 */ });
test("no outbound code (spec 6.9)", () => {
  // over main.js, preload.js, lib/**/*.js (those that exist): no require of "electron-updater", "http", "https", "net",
  // "node:http", "node:https", "node:net"; no "autoUpdater"; no "XMLHttpRequest"; no fetch( whose first argument starts
  // with a string or template literal beginning "http" (main.js's one fetch is built from sidecar.origin - design issue 8)
});
```

- [ ] **Step 2: Run** `cd desktop && node --test test/unit.test.js`. Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** the helpers. `cd desktop && npm install --no-audit --no-fund --save-exact -D
  electron@45.2.3 electron-builder@26.18.0 && node node_modules/electron/install.js`; commit the lockfile.
- [ ] **Step 4: Run** G4. Expected: all pass.
- [ ] **Step 5: Gates** G1, G4, and G2 once after rebasing (expected: the count of the tasks landed before it).
- [ ] **Step 6: Commit** `git add desktop/package.json desktop/package-lock.json desktop/lib desktop/test/unit.test.js
  && git commit -m "desktop: shell helpers (env, handshake, guard + token header, budget, shutdown, restart, sandbox, paths, log + redaction, state) with node tests (t_f04f1355)"`.

Cannot verify here: nothing beyond the helpers' own logic (Electron is not loaded by these tests).

### Task 6: `main.js`, `preload.js`, the starting page, the icon, the xvfb end-to-end tests (slice S3, part 2)

**Files:**
- Create: `desktop/main.js`, `desktop/preload.js`, `desktop/starting.html`, `desktop/build/make-icon.py`,
  `desktop/build/icon.png`, `desktop/test/e2e.js`, `desktop/test/probe-preload.js`, `desktop/test/run-e2e.sh`,
  `desktop/test/lifecycle.test.js`
- Modify: `desktop/test/unit.test.js` (version equality)

**Interfaces:**
- Consumes: every `desktop/lib` export (Task 5); `server.py --exit-with-parent` (Task 3); the sidecar (Task 4).
- Produces (`main.js`, CommonJS; runs `start()` when `require.main === module`, exports `{start}`):
  - `start({smoke, resourcesPath, env, userData} = {}) -> Promise<{win, sidecar, log}>`: `smoke` defaults to
    `process.env.SVF_MAKER_SMOKE === "1"`, `resourcesPath` to `process.resourcesPath` (read-only in Electron; the e2e
    passes its own), `env` to `process.env`, `userData` to `app.getPath("userData")`. Single-instance lock first (the
    loser `app.quit()` before any spawn); session `fromPartition("maker")`; launch from `resolveLaunch({resourcesPath,
    appDir: __dirname, env, pid: process.pid, userData})` and `buildEnv`, spawned `{detached: true, stdio: ["ignore",
    "pipe", "pipe"], windowsHide: true, cwd: os.homedir()}`.
  - **The sidecar's pipes:** both streams are read for the sidecar's whole life (never paused, so a full pipe never
    blocks the server's prints); stdout feeds `parsePortLine` until the line, then is discarded; stderr lines go into a
    `Ring(50)`. On an exit or a start failure the shell logs the ring through `redactLine`, line by line; nothing from
    either stream is logged otherwise (design issue 26).
  - Handshake bounded by `HANDSHAKE_S`, `starting.html` after `STARTING_PAGE_S`; the one mutable `sidecar = {child,
    port, origin, token, pid, mode}` read at call time by every handler; `onBeforeSendHeaders({urls:
    ["http://127.0.0.1/*"]})` using `withToken`; `onBeforeRequest({urls: ["<all_urls>"]})` cancelling `!isOurs`;
    `will-download` prevented; the three permission handlers deny; `webPreferences` exactly spec 6.4 with `devTools:
    env.SVF_MAKER_DEVTOOLS === "1"`; navigation guards and `web-contents-created`.
  - IPC handlers `maker:pick-files`, `maker:pick-folder`, `maker:pick-output-dir`, `maker:open-output`, each first
    checking `event.senderFrame` non-null and its origin === `sidecar.origin`. `maker:pick-output-dir` adds
    `fs.realpathSync(picked)` to `handedOut` (the server stores the realpath, `server.py:821-851`; design issue 27).
    `maker:open-output` reads `?job=` from `win.webContents.getURL()`, `fetch(sidecar.origin + "/api/jobs/" + id,
    {headers: {"X-Maker-Token": sidecar.token}})`, and calls `shell.showItemInFolder(output_dir)` only when
    `handedOut` includes `fs.realpathSync(output_dir)` (refused: log `open-output: refused`).
  - `before-quit` -> `stopSidecar(sidecar.child, {termWaitS: STOP_WAIT_S, killWaitS: KILL_WAIT_S})` then `app.exit(0)`;
    `process.on("SIGINT"|"SIGTERM"|"SIGHUP", () => app.quit())`; sidecar exit while not quitting ->
    `dialog.showMessageBox(win, {buttons: ["Restart", "Quit"]})` with `restartAllowed`; `render-process-gone` reload
    once; the menu of 6.8; About with versions, `BUILD_ID`, `sandboxText(...)` and the THIRD-PARTY button
    (`shell.openPath(<resources>/THIRD-PARTY.txt)`, the one `openPath`).
  - Log lines the tests rely on (exact prefixes): `shell pid=<n>`, `sidecar start mode=<packaged|dev> pid=<n>`,
    `sidecar port=<p>`, `sidecar exit code=<c> signal=<s>`, `sandbox <sandboxText>`, `<channel>: <count>`,
    `open-output: refused`. With `smoke`: after the page's `fetch("/api/caps")` (through `executeJavaScript`) answers 200
    the shell prints `svf-maker smoke ok <document.title>` on stdout and calls `win.close()` (the normal close path).
  - `preload.js`: exactly the spec 6.5 block. `test/probe-preload.js`: exposes `window.probeInvoke(channel)` =
    `ipcRenderer.invoke(channel)` (test-only; loaded only by the e2e's second window).
  - `starting.html`: static text "starting the maker...", no script, no external reference.
  - `build/make-icon.py`: Pillow draws "ㅅ" from `ttf/neodgm/neodgm.ttf` (OFL) white on a dark square, 512x512, into
    `desktop/build/icon.png` (run once, both files committed).
- Every Electron launch in the tests: `xvfb-run -a <electron> --no-sandbox --disable-gpu ... --user-data-dir=<TMP_DIR>/...`.

- [ ] **Step 1: Write the failing tests.** `desktop/test/e2e.js` (the Electron main script; `node:assert`; prints
  `E2E PASS <name>` / `E2E FAIL <name> <message>`, exits 1 on any failure) stubs `dialog.showOpenDialog` (a queue of
  `{canceled, filePaths}`), `dialog.showMessageBox` (resolves `{response: 0}` = Restart) and `shell.showItemInFolder`
  (records the path) on `require("electron")` **before** `require("../main.js").start(...)`. Pass 1 (always): `start({env:
  {...process.env, SVF_MAKER_DEV: "1"}, userData: <TMP_DIR>/ud1})` and asserts the log has `mode=dev`. Pass 2 (only when
  `SVF_MAKER_SIDECAR` and `SVF_MAKER_STAGED_REPO` are set): the e2e builds `<TMP_DIR>/res/` with the exact packaged
  layout - `res/sidecar/svf-maker-sidecar` -> a symlink to `dirname($SVF_MAKER_SIDECAR)` (the one-dir directory, so
  `res/sidecar/svf-maker-sidecar/svf-maker-sidecar` is the executable), `res/repo` -> `$SVF_MAKER_STAGED_REPO` - and
  calls `start({resourcesPath: <TMP_DIR>/res, env: <process.env without SVF_MAKER_DEV>, userData: <TMP_DIR>/ud2})`,
  asserting the log has `sidecar start mode=packaged`. Each pass runs:

```text
handshake            sidecar.port > 0 within HANDSHAKE_S; the log has "sidecar port="
title                document.title === "SVF maker"
bridge               typeof each of pickFiles, pickFolder, pickOutputDir, openOutputFolder === "function"; platform === "linux";
                     typeof window.require === "undefined"; typeof window.ipcRenderer === "undefined"
header               page fetch("/api/caps") -> 200; page fetch("/api/caps", {headers: {"X-Maker-Token": "0".repeat(32)}}) -> 200
outbound             page fetch("http://127.0.0.1:1/x") rejects; window.open("http://example.invalid/") === null;
                     location = "http://example.invalid/" leaves location.origin === sidecar.origin after 1 s
download             an injected <a download href="/static/maker.js"> clicked: the test's own will-download listener (added
                     after the shell's) sees the item with defaultPrevented true; no new file in the download directory
flow                 two local jobs: dialog queue = [tmpA (a folder with neodgm.ttf)], [outA], [tmpB], [outB]; for each:
                     #choose-folder, #choose-output, #ack-ok if shown, #detect-local, a page fetch PUT settings selecting the
                     font (dest dos, precomposed, 16 px, 1 bpp), #run; wait #state contains "written to"; a
                     canvas[data-step][data-drawn="1"] exists
open-folder          load "/?job=<job A id>" (the older job), click #open-folder -> showItemInFolder called with outA (not outB);
                     a third job whose output was picked through a symlink outC-link -> outC: called with the realpath outC;
                     a job created by a direct API call with an output never handed out -> not called, log "open-output: refused"
ipc-sender           a second BrowserWindow (same session) loading "about:blank" with test/probe-preload.js:
                     probeInvoke("maker:pick-files") rejects; the dialog stub was not called
restart              before the kill, plant <outA>/.svf-maker-0123456789ab/ (a stale files directory: the next start prints
                     "sweep: <path>" on stderr); process.kill(sidecar.pid, "SIGKILL"): the message box stub called; within
                     HANDSHAKE_S a new sidecar with a different token and pid; the page reloads; page fetch("/api/caps") -> 200
log privacy          shell.log contains neither token, nor tmpA/tmpB/outA/outB/outC (or their realpaths), nor "/api/jobs/",
                     nor "sweep: /"; it has "pick-folder: 1" lines and one "sandbox renderer sandbox: off (--no-sandbox; ...)"
                     line (recorded: this host has no userns; spec 8.7)
```

  `desktop/test/lifecycle.test.js` (`node --test`; skips with a message when `xvfb-run` or the electron binary is
  missing): spawns `xvfb-run -a <electron> --no-sandbox --disable-gpu <desktop> --user-data-dir=<TMP_DIR>/<case>` with
  `SVF_MAKER_DEV=1`, `SVF_MAKER_SHELL_LOG=stderr`, and reads `shell pid=` and `sidecar start ... pid=` from stderr; the
  cases run **one after another** (never more than two Electron instances at once):

```js
test("close: smoke ok, sidecar exit 0, nothing left", ...);  // SVF_MAKER_SMOKE=1: stdout "svf-maker smoke ok SVF maker";
                                                             // stderr "sidecar exit code=0"; both recorded pids not alive
test("SIGTERM to the shell stops the sidecar", ...);         // after the port line: kill(shellPid, "SIGTERM"): "sidecar exit code=0",
                                                             // the shell exits within STOP_WAIT_S + 5
test("SIGKILL of the shell: the sidecar exits by itself", ...); // a local job created first; kill(shellPid, "SIGKILL"):
                                                             // the sidecar pid not alive within 5 s; its files dir gone
test("second instance quits at once", ...);                  // a second launch with the same user-data-dir exits within 5 s and
                                                             // logs no "sidecar start"; the first is then closed (smoke path)
```

  `run-e2e.sh`: `cd "$(dirname "$0")/.."`; requires `TMP_DIR` (exits 2 without it); exits 0 printing `SKIP: <reason>`
  when `xvfb-run` or `node_modules/.bin/electron` is missing; else `xvfb-run -a node_modules/.bin/electron --no-sandbox
  --disable-gpu test/e2e.js`. `unit.test.js` gains `test("versions agree")`: `package.json` version === the `VERSION =
  "..."` of `maker/sidecar.py`.
- [ ] **Step 2: Run** G5's e2e command (announce). Expected: FAIL (`Cannot find module '../main.js'`).
- [ ] **Step 3: Implement** `main.js`, `preload.js`, `starting.html`, `test/probe-preload.js`; run `python3
  desktop/build/make-icon.py`.
- [ ] **Step 4: Measure, then run G5.** While the lifecycle "second instance" case runs, sample the task count of its
  processes (`ps -eLo args | grep -c "user-data-dir=$TMP_DIR"` every 0.25 s) and record the peak in the commit body
  (expected about 114 + the dev sidecar; must stay under 200, else stop and report). Then run both G5 commands (each
  announced, under the lock). Expected: every `E2E PASS`, every lifecycle test passes; no pid the runs recorded is
  alive afterwards.
- [ ] **Step 5: Packaged pass:** `~/.local/bin/heavy bash maker/build-sidecar.sh --no-test` in this worktree if
  `desktop/build/out/` is absent, then `SVF_MAKER_SIDECAR=$PWD/desktop/build/out/sidecar/svf-maker-sidecar/svf-maker-sidecar
  SVF_MAKER_STAGED_REPO=$PWD/desktop/build/out/repo flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash
  desktop/test/run-e2e.sh`. Expected: both passes `E2E PASS`, pass 2 with `mode=packaged`.
- [ ] **Step 6: Gates** G1, G2 (unchanged count), G3, G4, G5 (Step 4's runs count).
- [ ] **Step 7: Commit** `git add desktop/main.js desktop/preload.js desktop/starting.html desktop/build/make-icon.py
  desktop/build/icon.png desktop/test && git commit -m "desktop: Electron shell (sidecar spawn + handshake, drained pipes, token header, request and navigation guards, four-function bridge, restart, quit sequence, redacted log) with xvfb e2e and lifecycle tests (t_f04f1355)"`.

Cannot verify here: real native file dialogs with a desktop session (stubbed; the manual check goes into
`docs/maker-desktop.md`); a sandboxed renderer (`--no-sandbox` under xvfb; the run records `Seccomp 0`); the GPU path
(`--disable-gpu` in tests; the AppImage smoke too); macOS/Windows menus, `activate`, `showItemInFolder` in
Finder/Explorer. How it degrades: `xvfb-run -a electron --no-sandbox --disable-gpu` runs the real main process code
with stubbed dialogs; whether Electron's `http://127.0.0.1/*` filter matches every port is proven by the restart check
(new port, header present), not assumed.

**Group C review gate.** The reviewer runs G5 (both e2e passes, lifecycle) and G4, and reads `shell.log` of the run
for tokens and paths.

---

# Group D: packaging and documents (slices S4, S5)

After Groups B and C. Task 7 -> Task 8 -> Task 9, sequential (`desktop/package.json` in 7 and 8;
`maker/build-sidecar.sh` in 7; 9 cites 8's numbers). One review after Task 9 against the cards' closing measurements.

### Task 7: `THIRD-PARTY.txt` generation and the sources gate (slice S4, part 1; spec 8.9, 8.10, D8 per section 17)

**Files:**
- Create: `desktop/build/third-party.mjs`, `desktop/build/third-party-map.json`, `desktop/build/licences/`,
  `desktop/build/sidecar-provenance.py`, `desktop/test/third-party.test.js`
- Modify: `maker/build-sidecar.sh` (writes the provenance file after PyInstaller), `desktop/package.json` (`"test"`
  list), `maker/sidecar.spec` **only if** Step 4 excludes a library puller (then also the rebuild, the frozen test
  and G2)

**Interfaces:**
- `desktop/build/sidecar-provenance.py WORKPATH OUT.json`: reads PyInstaller's `COLLECT-00.toc` (`ast.literal_eval`)
  under `WORKPATH`; for every binary entry writes `{dest: {"source": <original path>, "sha256", "origin": "wheel" |
  "dpkg" | "python", "package", "version"}}` - `wheel` when the source is under the pip target directory
  (`<dist>.libs/` or a package directory; package/version from the matching `*.dist-info`), `dpkg` from `dpkg -S
  <original path>` + `dpkg-query -W -f '${Version}'`, else `python` for the interpreter's own files. Run by
  `build-sidecar.sh` into `desktop/build/out/sidecar-provenance.json` (design issue 23: `dpkg -S` of a bundled copy
  finds nothing; the original path is known only at build time).
- `node desktop/build/third-party.mjs --sidecar DIR --provenance FILE --electron DIR --usrlib DIR --pysite DIR --repo
  DIR --meta DIR --out FILE [--sources DIR]` -> exit 0 and the file; exit 1 with one line per problem on stderr. Module
  export `generate({sidecar, provenance, electron, usrlib, pysite, repo, meta, map, sources, readCopyright}) -> {text,
  problems, components}` for the test.
  - `--electron DIR`: Electron's own files - `node_modules/electron/dist` at build time, the extraction root
    `squashfs-root/` in the release check; the licence is `LICENSE` or `LICENSE.electron.txt`, the Chromium notices
    `LICENSES.chromium.html` (both names accepted; design section 8.9).
  - `--usrlib DIR`: the AppImage's `usr/lib` (at build time the toolset's `~/.cache/electron-builder/appimage-12.0.1/*/lib/x64`;
    in the release check `squashfs-root/usr/lib`), design issue 22.
  - `--meta DIR`: the checkout (source metadata: `LICENSE`, `NOTICE.md`), separate from the bundled inputs.
- Map entry: `{"match": "<glob over basenames>", "component", "version" | "from": "dpkg" | "wheel", "licence": SPDX,
  "source_url", "class": "none" | "lgpl" | "gpl" | "gpl-exception" | "gcc-rle", "record"?: {"source", "replace"},
  "note"?}`. Classes: `gpl-exception` for the PyInstaller bootloader inside `svf-maker-sidecar` (GPL-2.0-or-later WITH
  Bootloader-exception, plus its runtime hooks) and anything else whose licence carries a linking exception; FreeType
  from the wheel is recorded as `FTL` (its dual licence, the chosen side); one entry for the AppImage runtime
  (`appimage-12.0.1`: MIT + squashfuse BSD-2 + static libfuse LGPL-2.1, the electron-builder-binaries URL, the
  static-link note).
- Rules: every `*.so*` under `<sidecar>/_internal`, under `<electron>` and under `<usrlib>` must match an entry (fail
  closed: `unattributed: <path>`); a sidecar library must also have a provenance entry whose sha256 equals the file's
  (`provenance mismatch: <path>`); class `gpl` -> `gpl forbidden: <file>`; `lgpl` without `record` -> `lgpl without
  distribution record: <component>`; `<repo>/svf` may hold only `.SVF` files matched by a `<repo>/web/LICENCES.tsv`
  glob, the `.TXT` files those rows name, and the metadata allowlist `["jamo-extra/FACES.TSV"]` (`not OFL-listed:
  <path>`); `package.json` `dependencies` non-empty -> problem.
- Output sections, in order: the maker (MIT, `<meta>/LICENSE`), the faces (OFL 1.1, `<meta>/NOTICE.md`'s table),
  Electron + Chromium, CPython, Pillow, fontTools (from `pysite/*.dist-info`), PyInstaller's bootloader, each native
  library (component, version, licence, source URL, record, text), the AppImage `usr/lib` libraries, the AppImage
  runtime; then the "Copyleft check" block listing every `lgpl`/`gpl-exception`/`gcc-rle` component and the line
  `release gate (D8): corresponding sources archived: YES|NO`.
- **The sources gate (`--sources DIR`):** `DIR/MANIFEST.json` = `[{"component", "version", "kind": "source" |
  "recipe", "archive": "<path relative to DIR>", "sha256"}]`. YES only when every `lgpl` component (and the AppImage
  runtime) has a `source` entry whose component and version equal the map/provenance values, the runtime also has a
  `recipe` entry, and every named archive exists, is non-empty and has that sha256; otherwise NO with one problem per
  gap (`sources: missing archive <c>`, `sources: digest mismatch <path>`, `sources: version mismatch <c>`, `sources:
  no recipe for appimage runtime`). Without `--sources`: NO, and no problem (private build).

- [ ] **Step 1: Write the failing tests** `desktop/test/third-party.test.js` over an **extraction-shaped** temp
  fixture (under `os.tmpdir()`): `squashfs-root/{LICENSE.electron.txt, LICENSES.chromium.html, libffmpeg.so,
  usr/lib/libXtst.so.6, resources/sidecar/svf-maker-sidecar/_internal/{libpython3.12.so.1.0,
  libfreetype-abc.so.6.20.1}, resources/repo/{svf/dos/A.SVF, svf/dos/OFL.TXT, svf/jamo-extra/FACES.TSV,
  web/LICENCES.tsv}}`, a provenance file, a fake `pysite/*.dist-info`, a meta dir with `LICENSE`/`NOTICE.md`, and a
  build-time variant (`dist/LICENSE`):

```js
test("extraction-shaped tree -> no problems, every component in the text", ...);
test("build-time tree (LICENSE, toolset usr/lib) -> no problems", ...);
test("an unmatched .so fails closed (sidecar, electron and usr/lib each)", ...);
test("a sidecar .so whose sha256 differs from its provenance fails", ...);
test("a gpl entry fails; a gpl-exception entry (bootloader) is attributed", ...);
test("lgpl needs a record", ...);                       // libffmpeg.so entry without record -> "lgpl without distribution record: ffmpeg"
test("non-OFL file under repo/svf fails; FACES.TSV and listed .TXT pass", ...);
test("sources: YES with a complete manifest", ...);
test("sources: missing archive / digest mismatch / version mismatch / no runtime recipe each -> NO + its problem", ...);
test("no --sources -> NO without a problem", ...);
```

- [ ] **Step 2: Run** `cd desktop && node --test test/third-party.test.js`. Expected: FAIL.
- [ ] **Step 3: Implement** the generator and `sidecar-provenance.py`; add the provenance call to `build-sidecar.sh`;
  append `test/third-party.test.js` to G4 and `package.json` `"test"`.
- [ ] **Step 4: Fill the map against the real build:** `~/.local/bin/heavy bash maker/build-sidecar.sh --no-test`,
  then `node desktop/build/third-party.mjs --sidecar desktop/build/out/sidecar/svf-maker-sidecar --provenance
  desktop/build/out/sidecar-provenance.json --electron desktop/node_modules/electron/dist --usrlib
  ~/.cache/electron-builder/appimage-12.0.1/<dir>/lib/x64 --pysite $SVF_DESKTOP_TMP/pysite --repo
  desktop/build/out/repo --meta . --out desktop/build/out/THIRD-PARTY.txt`, adding entries until it exits 0. For each
  wheel-vendored library, check whether `pysite/pillow-10.2.0.dist-info/` carries its licence text; where not, commit
  the upstream text under `desktop/build/licences/<component>.txt` (spec 8.9 "not verified" item). Classify the six
  toolset `usr/lib` libraries from their Debian/Ubuntu origin (the toolset README or `strings` version tags) and record
  in the commit body whether any is `gpl` (then the generator fails and Task 8 must drop them: see Task 8 Step 2). Find
  which collected library pulls `libglib-2.0` (`ldd` over `_internal/*.so*`); if a spec `excludes` entry removes it
  without breaking `selfcheck` and the frozen test, add it to `maker/sidecar.spec` (then rebuild, run the frozen test
  with `SVF_MAKER_FROZEN_REQUIRED=1`, and run G2); else keep it as `lgpl` with a record.
- [ ] **Step 5: Run** G4 and the real generation. Expected: pass; exit 0; the final copyleft list printed.
- [ ] **Step 6: Gates** G1, G4 (G2 only if `maker/sidecar.spec` changed).
- [ ] **Step 7: Commit** `git commit -m "desktop: THIRD-PARTY.txt generator (fail closed over sidecar, Electron and AppImage usr/lib; build-time provenance; GPL forbidden; LGPL records; sources manifest gate) (t_e64a56a7)"`; the body lists the copyleft components found.

Cannot verify here: the AppImage runtime's composition beyond its file names (8.9 item 4); the exact Debian source
package URLs resolving (recorded, not fetched). How it degrades: the record carries the URL; fetching and archiving
sources is the release gate (D8), documented in Task 9.

### Task 8: electron-builder AppImage and the release check (slice S4, part 2)

**Files:**
- Create: `desktop/build/build-appimage.sh`, `desktop/build/release-check.sh`
- Modify: `desktop/package.json` (the `"build"` block)

**Interfaces:**
- `package.json` `"build"` (validated against 26.18.0's schema): `appId "org.svf-fonts.maker"`, `productName
  "svf-maker"`, `electronVersion "45.2.3"`, `npmRebuild false`, `publish null`, `directories {"output": "dist"}`,
  `files ["main.js", "preload.js", "starting.html", "lib/**", "package.json"]`, `extraResources [{"from":
  "build/out/sidecar/svf-maker-sidecar", "to": "sidecar/svf-maker-sidecar"}, {"from": "build/out/repo", "to": "repo"},
  {"from": "build/out/THIRD-PARTY.txt", "to": "THIRD-PARTY.txt"}]`, `linux {"target": ["AppImage"], "category":
  "Utility", "icon": "build/icon.png", "desktop": {"entry": {"Name": "SVF maker"}}, "syncDesktopName": true,
  "artifactName": "${productName}-${version}.${ext}"}`. `desktopName` stays a top-level `package.json` field (Task 5).
  `linux.executableArgs` is **not** set: electron-builder's default writes `Exec=AppRun --no-sandbox %U` into the
  embedded `.desktop` entry (with the legacy toolset); D7 per section 17 ships that unchanged, and the release check
  records it (design issue 22).
- `build-appimage.sh [--release]` (from the checkout root, `set -euo pipefail`, `T=${SVF_DESKTOP_TMP:-...}`):
  `maker/build-sidecar.sh` (frozen test included, `SVF_MAKER_FROZEN_REQUIRED=1`); the Task 7 generator with its
  build-time arguments (`--sources desktop/build/out/sources` with `--release`); `cd desktop && npx electron-builder
  --linux AppImage --publish never`; then `desktop/build/release-check.sh desktop/dist/svf-maker-0.1.0.AppImage
  [--release]`.
- `release-check.sh APPIMAGE [--release]` extracts into `$T/release-<epoch>/` and prints one `CHECK <name> ok|FAIL
  <why>` line per check, exit 1 on any FAIL: `size` (AppImage <= 170 MB; `resources/sidecar` <= 60 MB); `extract`
  (`--appimage-extract`); `layout` (spec 8.4: `resources/app.asar`, `resources/sidecar/svf-maker-sidecar/svf-maker-sidecar`,
  `resources/repo/{svf,web,BUILD_ID,tools,maker}`, `resources/THIRD-PARTY.txt`; no `test_*.py`, `__pycache__` or
  `testdata` under `resources/repo`); `apprun` (electron-builder's `AppRun` unchanged: contains `unshare -Ur` and
  `--no-sandbox`); `desktop-entry` (records the embedded `.desktop` `Exec=` line; FAIL only if it lacks `AppRun`);
  `frozen` (`python3 -m unittest discover -s maker/test -p test_frozen.py` with **absolute**
  `SVF_MAKER_SIDECAR=<extract>/resources/sidecar/svf-maker-sidecar/svf-maker-sidecar`,
  `SVF_MAKER_STAGED_REPO=<extract>/resources/repo`, `SVF_MAKER_REF_SITE=$T/pysite`, `SVF_MAKER_FROZEN_REQUIRED=1`;
  FAIL on any failure **or any skip**: the output's `skipped=` must be absent); `wasm` (`cmp` of the extracted
  `_internal/static/wasm/svf.wasm` with `SVF_WASM_OUT=$T/wasm-cmp bash maker/build-wasm.sh`); `licences` (the generator
  over the extraction: `--sidecar <extract>/resources/sidecar/svf-maker-sidecar --provenance
  desktop/build/out/sidecar-provenance.json --electron <extract> --usrlib <extract>/usr/lib --pysite $T/pysite --repo
  <extract>/resources/repo --meta .`; exit 0 and no `gpl` class); `smoke` (under the browser lock: `xvfb-run -a
  <extract>/AppRun --disable-gpu --user-data-dir=$T/release-ud` with `SVF_MAKER_SMOKE=1`, `SVF_MAKER_SHELL_LOG=stderr`:
  stdout has `svf-maker smoke ok SVF maker`, exit 0 within 60 s, stderr has `sidecar start mode=packaged` and `sidecar
  exit code=0`, and the logged shell and sidecar pids are not alive afterwards); `sources` (`--release` only: the
  generator's gate line is `YES`; without `--release` it prints `CHECK sources skipped (private build; D8 release
  gate)`); `contents` (writes `desktop/build/out/release-<BUILD_ID first word>.txt`: the extraction's file list with
  sizes, the Debian-Pillow comparison line, the sandbox line of the smoke run, the `.desktop` Exec line).

- [ ] **Step 1: Write** `release-check.sh` first and run it against a missing file: `bash
  desktop/build/release-check.sh $TMP_DIR/none.AppImage`. Expected: `CHECK size FAIL ...`, exit 1.
- [ ] **Step 2: Write** the `"build"` block and validate the configuration before any AppImage build: `cd desktop &&
  npx electron-builder --linux dir --publish never` (electron-builder validates the configuration against its schema
  first; expected exit 0 and `dist/linux-unpacked/`). If Task 7 found a `gpl` library among the toolset's `usr/lib`
  files, check whether electron-builder 26.18.0 builds the AppImage with the newer toolset that omits them
  (`"toolsets": {"appimage": "<version>"}` per its docs); record the outcome; if neither works, stop and report.
- [ ] **Step 3: Run** `~/.local/bin/heavy bash desktop/build/build-appimage.sh` (announce; the smoke takes the browser
  lock). Expected: every `CHECK ... ok`, `sources skipped`; the AppImage around 151 MB; exit 0.
- [ ] **Step 4: Record** in the commit body: AppImage size, `linux-unpacked` size, build seconds, the `CHECK` lines,
  the smoke's sandbox line, the `.desktop` Exec line.
- [ ] **Step 5: Gates** G1, G4 (G2 unchanged).
- [ ] **Step 6: Commit** `git add desktop/package.json desktop/build/build-appimage.sh desktop/build/release-check.sh
  && git commit -m "desktop: AppImage through electron-builder with a release check (extract, frozen test with no skips, wasm cmp, licences over the extraction, smoke via AppRun, size budget) (t_e64a56a7)"`.

Cannot verify here: a FUSE-mounted AppImage start (no FUSE: the check runs the extracted `AppRun`); a sandboxed
renderer on a userns-capable system (here `AppRun` adds `--no-sandbox`); glibc < 2.39; `SOURCE_DATE_EPOCH`
determinism; `electronLanguages` pruning (not used). How it degrades: `--appimage-extract` + `xvfb-run AppRun`, the
frozen test against the extracted sidecar, and a recorded sandbox state.

### Task 9: documents, the spike's scratch paths, closing gates (slice S5)

**Files:**
- Create: `docs/maker-desktop.md`
- Modify: `maker/README.md` ("Desktop app" section, spec 13), `NOTICE.md` (spec 13 sentence), `docs/maker-audit.md`
  (section 9: the two cards' closing evidence), `docs/STATUS.md`, `maker/test/test_server.py`
  (`test_readme_and_notice_wording`), `desktop/spike/README.md` and `desktop/spike/spawn-probe.mjs` (every `/tmp/...`
  path becomes `$TMP_DIR/...` with the TMP_DIR preamble at the top of the README; the measured numbers stay as
  recorded)

- [ ] **Step 1: Extend** `test_readme_and_notice_wording`: `maker/README.md` contains "## Desktop app", "run-tool",
  "SVF_RECOG_PYTHON", "JAMOSET_PYLIB", "~/.config/svf-maker/maker", "makes no network connection", "not built or
  verified" (Windows/macOS); `NOTICE.md` contains "THIRD-PARTY.txt" and "It contains no font that is not in `svf/`."
  Run it: FAIL.
- [ ] **Step 2: Write** `docs/maker-desktop.md`: prerequisites and the build command sequence with the versions last
  used (emsdk/emcc 6.0.13, Python 3.12.3, PyInstaller 6.22.3, Pillow 10.2.0, fontTools 4.66.1, node, npm, Electron
  45.2.3, electron-builder 26.18.0) and the scratch convention (`SVF_DESKTOP_TMP`, `TMP_DIR`); the measured numbers
  from Tasks 4 and 8 and the Electron task counts; the sandbox state per system (D7 per section 17, the `.desktop`
  Exec line, D13 `.deb` later); the glibc floor (D9); the manual checks a human runs with a real desktop (native
  dialogs, FUSE start, "open folder" in a file manager, the GPU path); the LGPL release gate and how to fill
  `desktop/build/out/sources/MANIFEST.json` (D8); **"Windows and macOS (UNVERIFIED)"** with spec 8.11 verbatim and the
  Windows server-port blockers; the not-verified list of spec 10.4. Then the README, NOTICE, audit, STATUS and spike
  edits; `grep -n '/tmp' desktop/spike/*` -> no hit outside quoted historical output.
- [ ] **Step 3: Run the closing gates** and record each in the commit body:
  - G1; G2 (expected the Task 4 count + 0); G3; G4; G5.
  - `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_*.py'`.
  - `~/.local/bin/heavy make -C c check`.
  - `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 maker/test/smoke_dom.py`.
  - `git diff --exit-code 94011ff -- tools maker/static c/src c/include` -> exit 0.
  - `~/.local/bin/heavy bash desktop/build/build-appimage.sh` (fresh) -> every `CHECK ok`.
- [ ] **Step 4: Commit** `git add docs/maker-desktop.md maker/README.md NOTICE.md docs/maker-audit.md docs/STATUS.md
  maker/test/test_server.py desktop/spike && git commit -m "docs: desktop app build, sandbox state, release gate, Windows/macOS UNVERIFIED steps; audit section 9; spike paths under TMP_DIR (t_f04f1355, t_e64a56a7)"`.

**Group D review gate.** The reviewer runs Step 3's list and checks each closing measurement:
- The shell opens the app on Linux, picks files/folders through the bridge, converts a sample into an output folder
  and quits cleanly with no orphan: `e2e.js` (`bridge`, `flow`, `open-folder`, both passes) and `lifecycle.test.js`
  (Task 6); the release check's `smoke` (Task 8).
- A frozen sidecar converts the OFL sample set byte-identically to source mode in a clean environment without python
  on PATH: `FrozenByteEqualTest` and `test_frozen_jobs_match_source` under `PATH=<empty dir>` (Task 4), again on the
  extracted AppImage with no skip (Task 8 `frozen`).
- An AppImage builds with a local script and runs (extracted `AppRun`, no FUSE here): `build-appimage.sh` (Task 8).
- THIRD-PARTY generation: Task 7 tests and the `licences` check over the extraction (Task 8). The reviewer opens
  THIRD-PARTY.txt against `ls _internal/*.so* usr/lib/*.so*` of the extraction and the map.
- Windows/macOS steps documented as UNVERIFIED: `docs/maker-desktop.md` (Task 9).

---

## Review groups

| Group | Tasks | Order and parallelism | Review |
|---|---|---|---|
| A launcher (S1) | 1, 2 | 1 -> 2 (both `jobs.py`; Task 1 also owns every `.gitignore` change) | after 2: launch-line counts and diff; `/api/caps` keys |
| B sidecar (S2) | 3, 4 | after A; 3 -> 4 (`server.py`, `jobs.py`, `preview.py`, `localfx.py`) | after 4: the reviewer builds and runs the frozen test (0 skipped); recorded pids not alive; no zombies |
| C shell (S3) | 5, 6 | 5 starts after 3, in its own worktree alongside 4, rebases and reruns G1/G4 before landing; 6 starts after 4 and 5 have landed | after 6: G5 (both e2e passes, lifecycle), G4, `shell.log` read |
| D packaging + docs (S4, S5) | 7, 8, 9 | after B and C; 7 -> 8 -> 9 | after 9: the closing measurements |

Landing order: 1, 2, 3, then 4 and 5 in either order (no shared file once `.gitignore` is Task 1's; the second to land
rebases onto the first and reruns its gates), then 6, 7, 8, 9. G2 counts assume 4 before 5; a task landing in another
order states its observed count. Every browser/Electron run takes `$HOME/work/tmp/svf-browser.lock` and is announced.

## Design issues found while planning

1. **johab844 positions (7.2/7.3 vs the code).** Spec 7.3 says the johab844 test becomes "`rest[0]`'s name after
   `split_prefix`" and `_johab844_comment` reads the base from "`rest[2]`". After `split_prefix`, `rest` is `[src,
   base, out]` (`routes.py:196`). The plan detects johab844 by `toolrun.prefix_name(prefix) == "johab844"` and reads
   the base from `rest[1]` (Task 1).
2. **`split_prefix` raises, but `note_prefix` is applied to every argv.** Test steps run `[python, "-c", ...]` argvs
   through `log_step` and notes. The plan's `note_prefix` passes an unrecognised argv through unchanged (Task 1).
3. **The recogniser stub of 10.2/7.7 cannot pass the 7.7 probe** with "the host's `python3`" (no numpy/torch here).
   The plan uses a shell-stub interpreter (Task 4).
4. **`/api/caps` would leak the private keys as booleans** (`server.py:1772`). Task 2 filters to `caps.PUBLIC_KEYS`
   (a one-line `server.py` edit in S1, although spec 11 gives `server.py` to S2). 7.3 names `recog_argv(self.caps)`,
   7.7 `recog_argv(caps, repo_dir)`; the plan uses the latter, and `compute` keeps `recog_dir`.
5. **`make_server`'s order (section 4)** is `recover`, `start`, bind, `startup_cleanup`; the reap goes right after
   `jobs.Store(...)` (Task 3).
6. **PDEATHSIG bypasses the stdio detach** of 7.9; `terminate` detaches stdio when the expected parent is gone (Task
   3). `PR_SET_PDEATHSIG` fires when the forking **thread** exits; the runners block on their child in that thread.
7. **The runners have no data root** (7.10). The plan adds `toolreg.Registry` activated by `make_server` and
   deactivated by `server_close`; nothing is active in unit tests (Task 3).
8. **The static no-outbound scan vs the main-process request** (6.9 vs 6.5). The scan forbids literal `http...` URLs
   only; the one `fetch` builds its URL from `sidecar.origin` (Task 5).
9. **Where the version lives** (8.8 `maker/VERSION`): a constant in `maker/sidecar.py`, pinned equal to
   `package.json` (Tasks 4, 6). The venv of 8.3 becomes `pip --target` + `python3 -S` (section 12 allows it).
10. **`.mjs` names vs a sandboxed CJS preload** (6.1/10.3): CommonJS `.js` throughout (Task 5).
11. **Lifecycle cases cannot run inside the e2e's own main process** (10.3): they move to `lifecycle.test.js`, with
    `SVF_MAKER_SMOKE=1` (Task 6, also Task 8's smoke).
12. **Suite counts.** Sections 2 and 10.1 say 909 at `94011ff`; it is 914 (14 skipped).
13. **The import-graph oracle grows** past "28 modules": `toolrun`, `toolreg`, `sidecar` join it (Tasks 1, 3, 4).
14. **The handshake budget and the reap.** 75 s still covers 30 + 20 + 10 (`REAP_TOTAL_S`); asserted (Task 5).
15. **D7 in section 15 vs section 17:** the plan follows 17 (Task 8).
16. **The source archive (8.10) vs the D8 ruling (17):** enforced only with `--release`, with a real manifest check
    (Tasks 7, 8).
17. **`SVF_MAKER_NO_PDEATHSIG` cannot reach a tool** (7.10): the tool environment is scrubbed to PATH/HOME/LANG. The
    plan forwards exactly that key, only with the value `"1"`, through `base_env`, and the env assertions name it as
    the one allowed `SVF_` key (Tasks 1, 3, 4).
18. **The reap's argv0 match (7.10) misses tools it must kill:** an external recogniser interpreter (`SVF_RECOG_PYTHON`)
    never equals `sys.executable`, and an AppImage mounted at a new path changes the frozen launcher path between
    launches. The plan identifies a registered child by pid + start time (+ pgid) only (Task 3).
19. **Signal handling during start-up (7.9):** `terminate` and the `finally` are installed after `make_server` returns
    (`server.py:1982-2003`), so a parent death during the probe or the start-up cleanup would take the default SIGTERM
    action. The plan installs them first and cleans up a partly built server (Task 3).
20. **The frozen recogniser test needs numpy** (10.2): `jobs.RECOG_ARRAYS = "numpy"`. The test's stub interpreter
    rewrites `--arrays numpy` to `lists` for its own subprocess; production keeps `numpy` (Task 4).
21. **Electron's task count vs the shared heavy slice** (not in the design): one instance 143 tasks (87 with
    `--disable-gpu`), the second-instance case 170 (114). Tests run with `--disable-gpu`, one at a time, under a
    host-wide lock (Global Constraints).
22. **electron-builder's legacy AppImage toolset** copies six 2019 libraries (`libappindicator`, `libgconf-2`,
    `libindicator`, `libnotify`, `libXss`, `libXtst`) into `usr/lib`, which 8.9 does not list, and writes
    `Exec=AppRun --no-sandbox %U` into the embedded `.desktop` entry. The plan attributes or removes the libraries
    (Tasks 7, 8) and records the Exec line under D7.
23. **`dpkg -S` on bundled copies (8.9)** finds no package; provenance is taken from PyInstaller's TOC at build time
    (Task 7).
24. **The electron-builder configuration of 8.7** (`linux.desktop.Name`, `desktopName` in `build`) fails 26.18.0's
    schema; the plan uses `linux.desktop.entry` and `desktopName` as a `package.json` field (Tasks 5, 8).
25. **`JAMOSET_MASK_FONT` (not in 7.4):** `jamoset.DEFAULT_MASK_FONT` is resolved beside `__file__` (`_internal/`
    when frozen), and the override key is stripped from the tool environment. The plan forwards it with
    `JAMOSET_PYLIB` and adds it to the shell's pass-through list (Tasks 1, 5) - a change to the pinned `ENV_KEYS` of
    6.2.
26. **The sidecar's stderr tail (6.7) can carry the user's paths** (`sweep: <output path>`, `jobs.py:915,947,967`),
    and 6.2 does not say the pipes are drained after the port line. The plan drains both for the sidecar's life and
    logs the tail only redacted (Tasks 5, 6).
27. **`handedOut` vs the server's realpath (6.5):** the server stores `realpath(output_dir)`; the shell compares
    realpaths (Task 6).
28. **`shell-state.json` paths:** 6.4 says "sizes only; no paths", D3 allows the last output folder; the plan stores
    no input directory and caps `handedOut` (persisted, as 6.5 says) at 32 realpaths (Task 5).
29. **The PyInstaller bootloader's licence** (GPL-2.0-or-later WITH Bootloader-exception) and the wheel's FreeType
    (FTL/GPL-2 dual) need classes 8.9 does not define; the plan adds `gpl-exception` and records FTL (Task 7).
30. **`svfline` has no `--help`** (10.2 says "`run-tool <name> --help` exits 0" for every name): it exits 1 with its
    usage on stderr. The plan uses a per-tool smoke table (Task 4).
31. **Upload-job notes keep absolute repo paths** (7.2's "same text in both modes" holds for the prefix only): the
    johab844 base face would carry the checkout or AppImage mount path. The plan relativizes repo-rooted tokens in
    notes, `BUILD.md` and `log.md` (Task 1).

## Review dispositions

Reviews of `c65abbc`: Opus (APPROVE WITH CHANGES: Major M1-M9, Minor m1-m15, Nit n1-n6) and SOL (REJECT: P1 1-3,
P2 4-11); AGY unavailable (quota). Each finding was checked against the tree before the change; duplicates are merged.

| Finding | Checked | Disposition |
|---|---|---|
| Opus M1 + SOL P1-3 (G4 command invalid; e2e/lifecycle picked up; Electron outside heavy) | confirmed: `node --test test/` fails on node 22; measured Electron tasks (143/170, 87/114 with `--disable-gpu`) | fixed: G4 explicit file list, `"test"` the same; G5 = e2e and lifecycle as announced steps under `heavy` + `flock`; `--disable-gpu`; at most two instances; Task 6 Step 4 measures the peak; design issue 21 |
| Opus M2 + SOL P2-4 (`SVF_MAKER_NO_PDEATHSIG` stripped) | confirmed: `base_env` keeps PATH/HOME/LANG only | fixed: `base_env` forwards that one key only as `"1"`; `test_tool_env_has_no_maker_keys` names it as the one allowed `SVF_` key; Tasks 1, 3, 4; design issue 17 |
| Opus M3 (zombies counted alive) | confirmed: `/proc/<pid>` and `kill(pid, 0)` succeed for a zombie | fixed: `toolrun.alive` reads the state field; `test_alive_zombie`, `killed 1` with `proc.wait()` after (Task 3) |
| Opus M4 (process-global `configure`, never reset) | confirmed: 15 `make_server` call sites in tests | fixed: `Registry` objects, `activate`/`deactivate` in `make_server`/`server_close`, unregister through the registering registry, hygiene checks (Task 3) |
| SOL P1-1 (reap excludes the external recogniser; mount path changes) | confirmed: argv0 of `SVF_RECOG_PYTHON` != `sys.executable`; the AppImage mount path is random per launch | fixed: identity by pid + start time only; `test_reap_ignores_argv0`, `test_reap_external_interpreter` (Task 3); design issue 18 |
| SOL P1-2 + Opus m2 (signals installed after `make_server`) | confirmed `server.py:1982-2003` | fixed: `terminate` first, partial-construction cleanup, startup tests (`test_exit_with_parent_during_startup`, `test_sigterm_during_startup_cleanup`, `test_make_server_cleans_up_on_interrupt`) (Task 3); design issue 19 |
| Opus M5 (`svfline --help` exits 1) | confirmed (stderr usage, exit 1) | fixed: `sidecar.SMOKE` per-tool table (Task 4); design issue 30 |
| Opus M6 (`build` block fails the schema) | confirmed in `scheme.json` | fixed: `linux.desktop.entry`, `desktopName` top-level, `artifactName`; Task 8 Step 2 validates with `electron-builder --linux dir` first; design issue 24 |
| Opus M7 (AppImage `usr/lib` libraries unseen) | confirmed: six libraries in the cached toolset's `lib/x64` | fixed: `--usrlib` scanned at build time and in the release check; Task 8 Step 2 toolset fallback if one is GPL; design issue 22 |
| Opus M8 (pipes after the port line; paths in the stderr tail) | confirmed: `sweep:` prints in `jobs.py` | fixed: pipes drained for life, `Ring(50)`, `redactLine`, unit test, e2e planted `sweep:` line (Tasks 5, 6); design issue 26 |
| Opus M9 (`handedOut` vs realpath) | confirmed `server.py:821-851` | fixed: realpaths on both sides; symlinked `outC` e2e case (Task 6); design issue 27 |
| Opus m1 (race guard never fires) | agreed: `getppid()` after the fact is already the reaper | fixed: compare `/proc/<ppid>/exe` with the sidecar executable after the prctl (Task 4) |
| Opus m3 + SOL P2-6 (job parity cannot match; reference not on the pinned wheels; johab844 absent; `LocalRunBase` location) | confirmed: `build-<id>` in `result.files`; `select()` has no johab844; `LocalRunBase` in `test_local.py` | fixed: `normalise_job`, `select_johab844`, `toolrun.PYTHON` seam + `ref_python` wrapper for the reference, `LocalRunBase` moved to `localfx`, the test interpreter stated (Tasks 1, 4) |
| SOL P2-5 (recogniser stub needs numpy; empty PATH) | confirmed `jobs.py:148`, `recog_score.py:249` | fixed: absolute interpreter in the stub, `--arrays lists` rewritten by the stub only (Task 4); design issue 20 |
| SOL P2-7 (extracted check can skip byte-equal tests) | confirmed: `REF_SITE` not passed | fixed: absolute `SVF_MAKER_REF_SITE`, `SVF_MAKER_FROZEN_REQUIRED=1` turns skips into failures, the check FAILs on any skip (Tasks 4, 8) |
| SOL P2-8 + Opus m11 (packaged e2e has no launch selection; symlink level; `SVF_MAKER_DEV`; ipc-sender preload; `appDir`) | confirmed: `process.resourcesPath` is read-only | fixed: `start({resourcesPath, env, userData})`, exact `res/` layout, dev key removed, `mode=packaged` asserted, `probe-preload.js`, `appDir = __dirname` (Task 6) |
| SOL P2-9 + Opus m13 (dpkg on copies; `LICENSE.electron.txt`; staged repo lacks LICENSE/NOTICE; `FACES.TSV`; bootloader; FreeType) | confirmed: `svf/jamo-extra/FACES.TSV` exists; no package owns a bundled copy | fixed: build-time provenance from PyInstaller's TOC + digest check, both Electron licence names, `--meta`, metadata allowlist, `gpl-exception` class, FTL recorded, extraction-shaped fixture (Task 7); design issues 23, 29 |
| SOL P2-10 (sources gate does not verify archives) | agreed | fixed: `MANIFEST.json` schema (component, version, kind, archive, sha256), runtime recipe, negative tests (Task 7) |
| SOL P2-11 + Opus m6 (Task 4/5 both edit `.gitignore`; Task 5 red until rebase; Task 6 needs the build) | confirmed | fixed: all ignore rules in Task 1; Task 5 starts after Task 3; the second of 4/5 rebases and reruns its gates; Task 6 starts after both and rebuilds the sidecar in its worktree |
| Opus m4 (subreaper in the unittest process) | agreed | fixed: `parent_harness.py` holds the subreaper (Task 3) |
| Opus m5 (host-wide `pgrep`) | agreed | fixed: Global Constraint "process checks are scoped"; tests use recorded pids, zombie-aware |
| Opus m7 (`routes.SRCPREP` uses in `test_routes.py`) | confirmed `:486,:510,:514` | fixed: named in Task 1 Step 4 |
| Opus m8 (`_identity` `.get`; `run_identity` helper) | confirmed `test_jobs.py:650-662` | fixed: `.get("recog_dir")`, `run_identity` merges the keys (Task 2) |
| Opus m9 (upload notes keep absolute repo paths) | confirmed: the upload branch keeps raw tokens | fixed: `note_argv(argv, repo_dir)` in notes, `BUILD.md` and `log.md`; tested with different roots per mode (Task 1); design issue 31 |
| Opus m10 (`__file__` scan too narrow; `JAMOSET_MASK_FONT`) | confirmed `jamoset.py:2282,2299` | fixed: `test_file_uses_listed` allowlist with reasons; `JAMOSET_MASK_FONT` forwarded (Tasks 1, 5); design issue 25 |
| Opus m12 (state holds more paths than D3) | agreed (6.4 says no paths) | fixed: no `lastInputDir` on disk, `handedOut` capped at 32 (Task 5); design issue 28 |
| Opus m14 (`.desktop` Exec always `--no-sandbox`) | confirmed from electron-builder's `AppImageTarget.js` per the review | kept under D7 (section 17 ships electron-builder's defaults); recorded and checked by `desktop-entry` (Task 8); design issue 22 |
| Opus m15 (`sidecar.spec` change unlisted in Task 7) | agreed | fixed: listed as conditional with rebuild, frozen test and G2 |
| Opus n1 (test counts) | agreed | fixed: counts re-estimated (935, 943, 964, ~996 with ~38 skipped) |
| Opus n2 (launch-line grep misses `settings.py:1446`) | confirmed | fixed: count `PY +` lines (29) and `toolrun.` calls (Task 1 Step 6) |
| Opus n3 (wasm compare writes into `maker/static`) | confirmed `SVF_WASM_OUT` exists | fixed: `SVF_WASM_OUT=$T/wasm-cmp` (Task 8) |
| Opus n4 (no 16 px dos844 fixture in `inputfx`) | confirmed | fixed: `localfx`'s `b/HAN.FNT`/`ENG.FNT` (Task 4) |
| Opus n5 (`sandboxText` infers the cause) | agreed | fixed: "off (--no-sandbox; user namespaces <measured>)" (Task 5) |
| Opus n6 (`data:,` favicon cancelled) | confirmed `index.html:7` | fixed: `isOurs` allows `data:` (Task 5) |
| Opus Q4 (announcements alone do not serialize browsers) | agreed | fixed: host-wide `flock $HOME/work/tmp/svf-browser.lock` around every browser/Electron run |
| Controller rule 2026-11-05 (scratch under `TMP_DIR`) | `desktop/spike/README.md` has 15 `/tmp` paths, `spawn-probe.mjs` one; tests use `tempfile` | applied: Global Constraint, `SVF_DESKTOP_TMP` in the build scripts, `test_new_files_use_no_bare_tmp`, spike paths rewritten in Task 9 |
