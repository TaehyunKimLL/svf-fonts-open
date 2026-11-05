# SVF maker desktop app (Electron shell + frozen sidecar + AppImage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A double-clickable Linux AppImage of the SVF maker: an Electron shell that spawns a frozen Python sidecar
(the maker server and every tool in one PyInstaller one-dir bundle) on 127.0.0.1, adds the per-launch token itself,
gives the page the `window.svfMaker` bridge, and stops the sidecar cleanly; a generated `THIRD-PARTY.txt`; Windows and
macOS steps written down as UNVERIFIED. Cards t_f04f1355 (shell) and t_e64a56a7 (packaging), goal t_afb4689b.

**Architecture:** Four layers, landed in this order. (1) `maker/toolrun.py` becomes the one place that knows how a
tool is launched (`python3 -P tools/X.py` in source mode, `<sidecar> run-tool X` frozen); every launch site, note and
log goes through it, and the optional recogniser moves to an external interpreter (S1). (2) Server lifecycle for a
shell: `--exit-with-parent`, the tool registry and its reap, a no-op second `Worker.stop`; then `maker/sidecar.py`,
the PyInstaller spec and the build script, proven by a frozen test under `env -i` (S2). (3) `desktop/`: pure helpers
with node unit tests, then `main.js`/`preload.js` driven under `xvfb-run` (S3). (4) The licence generator, the
electron-builder AppImage and its release check, then the documents (S4, S5).

**Tech Stack:** Python 3.12 stdlib, Pillow 10.2.0 and fontTools 4.66.1 (the PyPI wheels in the build), PyInstaller
6.22.3, unittest; node 22 (`node --test`), Electron 45.2.3, electron-builder 26.18.0, `xvfb-run`; emsdk (emcc 6.0.13)
for the WASM module. No new runtime dependency in `desktop/` (Electron is a devDependency).

**Spec:** `docs/superpowers/specs/2026-11-05-maker-desktop-design.md` at `5d040e2`: sections 6-10, the slices (11),
the decisions (14), the rulings (15, and 17 which wins over 15 for D7/D8/D14/D15) and the review dispositions (16).
Section numbers below ("7.2", "10.3") are the spec's. All commands run from the worktree root
`/home/thkim/work/svf-fonts-open-wt/desktop` (branch `desktop`, base `94011ff`). No push.

**Rulings that bind this plan:** D1 message box + restart (new token, new port), at most 3 restarts in 5 minutes. D2
`window-all-closed` quits everywhere. D3 the last output folder path persisted in `shell-state.json`. D4 `run-tool`
only, no `-P` shim. D5 recogniser through `SVF_RECOG_PYTHON` running the shipped `repo/maker/recog_score.py`. D6 the
pinned versions above. D7 (section 17) ship electron-builder's `AppRun` unchanged; log and show the sandbox state. D8
(section 17) GPL forbidden by the generator; LGPL distribution record + source archive are a RELEASE GATE, not a gate
of this plan's build. D9 build on this host (glibc 2.39 floor). D10 window size/zoom persisted. D11 `getppid` polling
plus `PR_SET_PDEATHSIG` on Linux. D12 data root `<userData>/maker`. D13 `.deb` later (docs only). D14 registry in both
modes, PDEATHSIG frozen-only for tools. D15 "open folder" reveals the open job's folder, only if the shell handed it
out.

## Global Constraints

- **`c/src` and `c/include` unchanged.** Gate G1 at the end of every task.
- **Gates at the end of every task** (before its commit), in this order:
  - G1 `git diff --exit-code 94011ff -- c/src c/include` -> exit 0, no output.
  - G2 `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'` -> `OK` and `Ran N tests`.
    At `94011ff` the suite is **914 tests, OK (skipped=14)**. Each task states its expected N (a plan estimate); a
    different observed N goes into the commit body with the reason. G2 stays green at every task.
  - G3 `python3 -m unittest discover -s maker/test -p test_server.py -k test_page_js_tables_match_python` -> `OK`
    (the python and `maker.js` tables in sync; no task here changes either side, the gate proves it).
  - G4 (tasks touching `desktop/`) `cd desktop && node --test test/` -> all pass.
- **Full runs are announced.** Before and after every full G2 run (and every `run-e2e.sh`, `build-sidecar.sh`,
  `build-appimage.sh`), the implementer sends the controller one line: `START <what> <task>` / `FINISH <what> <task>
  <result>`. **One Chrome at a time:** never run G2 (which runs `test_page_dom.py` in Chrome) while another lane's G2,
  `smoke_dom.py` or an Electron e2e is running; parallel lanes take turns.
- **Long runs through the OOM guard:** G2, `tools/test_*.py`, `make -C c check`, PyInstaller and electron-builder
  builds, the frozen test and the e2e run under `~/.local/bin/heavy`.
- **No proprietary data.** Fixtures are synthetic (`maker/test/inputfx.py`, `fixtures.py`, `localfx.py`) or OFL files
  of this repository (`ttf/neodgm/neodgm.ttf`, `ttf/nanumgothic/NanumGothic-Bold.ttf`). The bundle carries OFL assets
  only (`svf/` copied whole, `web/` index files); no other font enters `desktop/build/out/`.
- **Pinned versions (D6):** `pyinstaller==6.22.3 pillow==10.2.0 fonttools==4.66.1` in
  `desktop/build/requirements-sidecar.txt`; `"electron": "45.2.3"`, `"electron-builder": "26.18.0"` exact in
  `desktop/package.json` devDependencies with `desktop/package-lock.json` committed; `build.electronVersion "45.2.3"`.
  A version moves only with a full release check (Task 8) run.
- **Build environment as verified here:** `python3 -m venv` does not work on this host; the build uses
  `python3 -m pip install --target desktop/build/out/pysite -r desktop/build/requirements-sidecar.txt` and runs Python
  as `PYTHONPATH=<pysite> python3 -S` (no `site`, so Debian's dist-packages - wx, setuptools - stay out of the graph and
  out of the reference). npm 12 blocks Electron's postinstall: after `npm ci` run `node node_modules/electron/install.js`.
- **The tool launch is byte-identical in effect** between modes (spec section 2): same argv after the launcher prefix,
  cwd, scrubbed environment, process group, exit codes, the same note/`BUILD.md`/`log.md` text.
- **No bare `git stash`.** Set work aside with a WIP commit on the branch.
- **Spikes stay under `desktop/spike/`** (throw-away, never imported by product code or tests). Promoting a spike file
  means copying its logic into the product file the task names; the spike file stays as it is.
- **Tools unchanged.** No file under `tools/` changes (`git diff --exit-code 94011ff -- tools` at Task 9).
- **The page unchanged.** No file under `maker/static/` changes (`git diff --exit-code 94011ff -- maker/static` at
  Task 9).
- **Commits** end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and name the card in
  the subject: `(t_f04f1355)` for Tasks 1-6, `(t_e64a56a7)` for Tasks 7-9 (both when a commit serves both).
- **Serialization.** No two tasks edit `maker/jobs.py`, `maker/preview.py`, `maker/server.py`, `maker/caps.py` or
  `maker/test/localfx.py` at the same time; tasks sharing a file land in plan order. Parallel lanes use their own
  worktree (`superpowers:using-git-worktrees`) and rebase before landing.

## Review Focus

1. **Tool launch parity: a launch that only fails frozen.** A site left on the old prefix, a positional consumer that
   slices `argv[2]`, or a note that shows `/tmp/.mount_svf-XYZ/resources/sidecar/svf-maker-sidecar run-tool mkfont`
   instead of `python3 -P tools/mkfont.py`. Pinned by `test_no_stray_launcher` and
   `test_every_builder_uses_toolrun_both_modes` (Task 1), `test_note_and_build_md_equal_both_modes` (Task 1),
   `test_frozen_jobs_byte_equal` and `test_frozen_notes_equal_source` (Task 4).
2. **Orphan processes: a tool or a sidecar that outlives its parent.** Cases: the sidecar SIGKILLed mid-tool, the
   shell SIGKILLed, PDEATHSIG's SIGTERM arriving while stdout/stderr lead to a dead pipe (a `BrokenPipeError` on the
   stop path), a restart whose sweep races a tool of the dead sidecar, a second instance. Pinned by
   `test_exit_with_parent_poll` / `test_exit_with_parent_pdeathsig` (Task 3), `test_reap_before_cleanup` (Task 3),
   `test_sigkill_sidecar_kills_tool` / `test_sigkill_without_pdeathsig_reaped_on_restart` (Task 4), and
   `lifecycle.test.js` (Task 6: close, SIGTERM, SIGKILL of the shell, `pgrep` empty afterwards).
3. **Token and header handling.** Cases: a request to an old port after a restart, a second `x-maker-token` spelling
   injected by the page, a non-`/api/` request, the token in a tool's environment, a log line, the command line or
   `shell-state.json`. Pinned by `withToken` unit tests (Task 5), `test_tool_env_has_no_maker_keys` (Task 1), the e2e
   restart check and the log scan in `e2e.js` (Task 6).
4. **Privacy of logs.** `shell.log` must hold no token, no picked path (counts only), no request URL beyond start/stop,
   no input byte; `BUILD.md` must not carry the AppImage mount path. Pinned by `log.test` cases (Task 5), the e2e
   `shell.log` scan (Task 6), and `test_note_and_build_md_equal_both_modes` (Task 1).
5. **Licence generation.** Cases: a `.so` in `_internal/` no map entry matches (must fail closed), a GPL entry, an LGPL
   entry without a distribution record, a non-OFL file under `repo/svf`, Electron's `libffmpeg.so`. Pinned by
   `third-party.test.js` (Task 7) and the release check's licence step (Task 8).

## Verified while planning (this host, `94011ff`)

- `grep -n 'PY\b\|SRCPREP\|sys.executable' maker/*.py`: `routes.py` 27 launch sites (lines 135-324 and 379-396),
  `settings.py:1446` (`_dy_argv`), `jobs.py:1514` (`_identity`): 29, as spec 7.3 says. `sys.executable` otherwise only
  at `routes.py:20` and `zipout.py:419`.
- `settings.probe_argv` (`:1402`) slices `mkfont_argv[2]`, `[5:]`, `[:2]`; `zipout.note_commands` (`:434`) tests
  `basename == "johab844.py"` over `argv[:4]`; `_johab844_comment` (`:457`) reads `argv[4]` - with
  `routes.py:196` `PY + [johab844.py, src, base, out]` that is the **base** face.
- Test steps run `[sys.executable, "-c", script, ...]` argvs through `log_step`/notes (`test_jobs.py:291,811,835`,
  `test_server_signals.py:65`, `test_page_dom.py:220`): an argv that is not a launcher shape reaches `_command_lines`.
- `server.Handler._caps` (`:1772`) serves `{key: bool(value) for every key of server.caps}`.
- `make_server` order: store, `caps.compute`, `Worker(...)`, `worker.recover()`, `worker.start()`, bind,
  `startup_cleanup()`; `main()` takes no arguments and ignores `sys.argv`.
- Tests patch `caps.recog_dir` to drive `_identity`: `test_jobs.py:658,689`, `test_local.py:527`.
- `jobs.run_command` and `preview.run_bounded` are module functions with no data root in scope.
- `python3 -S -c 'import sys; print(sys.path)'` has no dist-packages; plain `python3` imports `wx` (Debian).
- `~/.cache/electron` and `~/.cache/electron-builder/appimage-12.0.1` hold the spike's downloads; `xvfb-run`,
  `google-chrome`, node 22, npm present. `def test_` count in `maker/test` is 914.
- Page ids the e2e uses: `#choose-files`, `#choose-folder`, `#choose-output`, `#detect-local`, `#run`, `#open-folder`,
  `#state`, `#jobs`, `#ack-ok`; drawn canvases carry `data-drawn="1"` (`test_page_dom.py:159`); the page writes
  `?job=<id>` with `history.replaceState` and calls `openOutputFolder()` with no argument.

## File map

| File | Status | Responsibility (task) |
|---|---|---|
| `maker/toolrun.py` | create | launcher shapes, note prefix, base env (1); `recog_argv` (2); `launcher`, `set_pdeathsig` (3) |
| `maker/routes.py`, `maker/settings.py`, `maker/zipout.py` | modify | launch sites and positional consumers on `toolrun`; `repo_head` + `BUILD_ID` (1) |
| `maker/jobs.py` | modify | `ENV` from `toolrun.base_env`, `_identity` argv (1); `_identity` on `self.caps` (2); registry in `run_command`, `Worker.stop` once (3) |
| `maker/preview.py` | modify | `ENV` (1); registry in `run_bounded` (3) |
| `maker/caps.py` | modify | the external recogniser probe, `PUBLIC_KEYS` (2) |
| `maker/server.py` | modify | `_caps` serves `PUBLIC_KEYS` (2); `main(argv)`, `--exit-with-parent`, PDEATHSIG, reap before `recover` (3) |
| `maker/toolreg.py` | create | `<data_root>/tools.pids` registry and reap (3) |
| `maker/sidecar.py`, `maker/sidecar.spec`, `maker/build-sidecar.sh` | create | frozen entry point, PyInstaller spec, build + staging (4) |
| `desktop/build/requirements-sidecar.txt` | create | the three pinned wheels (4) |
| `maker/test/test_toolrun.py`, `test_sidecar_imports.py` | create | (1); roots switched to `sidecar` (4) |
| `maker/test/test_toolreg.py`, `test_sidecar.py`, `test_frozen.py` | create | (3), (4), (4) |
| `maker/test/localfx.py`, `maker/test/inputfx.py` | modify | `SubprocessLocalBase` (4); `big_composite_ttf(n)` (4) |
| `maker/test/test_routes.py`, `test_zipout.py`, `test_plan_inputs.py`, `test_jobs.py`, `test_preview.py`, `test_local.py`, `test_server.py`, `test_server_signals.py` | modify | per task |
| `desktop/package.json`, `package-lock.json`, `desktop/lib/*.js`, `desktop/test/unit.test.js` | create | helpers and unit tests (5) |
| `desktop/main.js`, `preload.js`, `starting.html`, `desktop/build/icon.png`, `desktop/build/make-icon.py`, `desktop/test/{e2e.js,run-e2e.sh,lifecycle.test.js}` | create | the shell (6) |
| `desktop/build/third-party.mjs`, `third-party-map.json`, `desktop/build/licences/`, `desktop/test/third-party.test.js` | create | THIRD-PARTY generation (7) |
| `desktop/build/build-appimage.sh`, `desktop/build/release-check.sh` | create | AppImage + release check (8); `package.json` "build" block (8) |
| `.gitignore` | modify | `desktop/build/out/`, `desktop/node_modules/`, `desktop/dist/` (4, 5) |
| `docs/maker-desktop.md`, `maker/README.md`, `NOTICE.md`, `docs/maker-audit.md`, `docs/STATUS.md` | create/modify | (9) |

---

# Group A: the launcher helper (slice S1)

Tasks 1 -> 2, sequential (both edit `maker/jobs.py`). One review after Task 2.

### Task 1: `maker/toolrun.py`, every launch site, notes and logs, `BUILD_ID`, `JAMOSET_PYLIB` (slice S1, part 1)

**Files:**
- Create: `maker/toolrun.py`, `maker/test/test_toolrun.py`, `maker/test/test_sidecar_imports.py`
- Modify: `maker/routes.py` (delete `PY`, `SRCPREP`, `_tool`; 27 sites), `maker/settings.py` (`probe_argv`,
  `_dy_argv`), `maker/jobs.py` (`ENV`; `_identity`'s argv line only), `maker/preview.py` (`ENV`), `maker/zipout.py`
  (`repo_head`, `_command_lines`, `note_commands`, `_johab844_comment`)
- Test (modify): `maker/test/test_routes.py` (`PY` and its 13 uses), `test_zipout.py` (`:115-131`, `:550`, note
  expectations), `test_plan_inputs.py` (`routes.PY`/`routes.SRCPREP` uses), `test_jobs.py`, `test_preview.py`

**Interfaces:**
- Produces (`maker/toolrun.py`, stdlib only, importable from `maker/` and `tools/` on `sys.path`):
  - `FROZEN: bool = bool(getattr(sys, "frozen", False))`, `MAKER_DIR`, `MAKER_SCRIPTS = ("srcprep", "recog_score")`,
    `MODULE_NAMES = {"fontTools.varLib.instancer": "instancer"}`.
  - `tool(name: str, tools_dir: str) -> list[str]`: source `[sys.executable, "-P", <tools_dir>/<name>.py]`, frozen
    `[sys.executable, "run-tool", name]`. `name` has no `.py`.
  - `maker_script(name: str) -> list[str]`: source `[sys.executable, "-P", <MAKER_DIR>/<name>.py]`, frozen
    `[sys.executable, "run-tool", name]`.
  - `module(dotted: str) -> list[str]`: source `[sys.executable, "-P", "-m", dotted]`, frozen
    `[sys.executable, "run-tool", MODULE_NAMES[dotted]]`.
  - `split_prefix(argv: list) -> tuple[list, list]`: recognises, whatever `FROZEN` is, `[x, "-P", "<...>.py", ...]`
    (3), `[x, "-P", "-m", dotted, ...]` (4), `[x, "run-tool", name, ...]` (3); `ValueError` otherwise.
  - `prefix_name(prefix: list) -> str`: the run-tool name of a prefix: `"mkfont"`, `"srcprep"`, `"instancer"`.
  - `note_prefix(argv: list) -> tuple[list, list]`: the prefix as the note shows it in both modes
    (`["python3", "-P", "tools/<name>.py"]`, `["python3", "-P", "maker/<name>.py"]` for `MAKER_SCRIPTS`,
    `["python3", "-P", "-m", dotted]`), and the rest; for an argv `split_prefix` refuses, `([], list(argv))`
    (pass-through: test steps and copy steps are not launches - design issue 2).
  - `note_argv(argv: list) -> list`: `prefix + rest` of `note_prefix`.
  - `base_env(environ: Mapping) -> dict`: `{"PATH": environ.get("PATH", "/usr/bin:/bin"), "HOME":
    environ.get("HOME", "/"), "LANG": "C.UTF-8"}` plus `"JAMOSET_PYLIB"` when set and non-empty in `environ`.
    `jobs.ENV = toolrun.base_env(os.environ)` and `preview.ENV = toolrun.base_env(os.environ)` (spec 7.4).
- Produces (`maker/zipout.py`): `repo_head(repo_dir) -> str`: `<repo_dir>/BUILD_ID` first line stripped, at most 200
  characters, when the file exists and the line is non-empty; else `"unknown"` when `toolrun.FROZEN`; else git as
  today.

- [ ] **Step 1: Write the failing tests** in `maker/test/test_toolrun.py`:

```python
class ShapesTest(unittest.TestCase):
    def test_source_shapes(self):
        self.assertEqual(toolrun.tool("mkfont", "/T"), [sys.executable, "-P", "/T/mkfont.py"])
        self.assertEqual(toolrun.maker_script("srcprep"), [sys.executable, "-P", os.path.join(toolrun.MAKER_DIR, "srcprep.py")])
        self.assertEqual(toolrun.module("fontTools.varLib.instancer"), [sys.executable, "-P", "-m", "fontTools.varLib.instancer"])
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
    def test_base_env(self):
        self.assertEqual(toolrun.base_env({"PATH": "/b", "HOME": "/h", "SVF_MAKER_TOKEN": "x" * 32, "PYTHONPATH": "/e"}),
                         {"PATH": "/b", "HOME": "/h", "LANG": "C.UTF-8"})
        self.assertEqual(toolrun.base_env({"JAMOSET_PYLIB": "/lib"})["JAMOSET_PYLIB"], "/lib")
        self.assertNotIn("JAMOSET_PYLIB", toolrun.base_env({"JAMOSET_PYLIB": ""}))
    def test_tool_env_has_no_maker_keys(self):
        for env in (jobs.ENV, preview.ENV):
            self.assertFalse([k for k in env if k.startswith("SVF_") or k.startswith("PYTHON")])

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
        # ast/regex over maker/*.py (not test_*.py): "sys.executable" occurs only in toolrun.py and zipout.py;
        # no module defines a name PY or SRCPREP; no string literal ending in ".py" is joined into an argv in routes.py
        # (regex r'"[a-z0-9_]+\.py"' finds nothing in routes.py, settings.py, jobs.py)
```

  In `maker/test/test_zipout.py` (new class `LauncherNotesTest`):

```python
def test_note_and_build_md_equal_both_modes(self):
    # one mkfont step and one johab844 step (argv built with toolrun.tool(..., "/T") under FROZEN False, then True);
    # for an upload job (sources=None) AND a local job (a Sources with one root):
    #   note_commands(...) equal between modes; _command_lines(step) equal; log_step(step, "", "") equal;
    #   each mkfont line starts with "python3 -P tools/mkfont.py "; no line contains sys.executable or "run-tool"
def test_johab844_comment_both_modes(self):
    # argv = toolrun.tool("johab844", "/T") + ["/u/H.FNT", "/R/svf/dos/NEODG16.SVF", "/w/OUT.SVF"] in both modes:
    # the line before the command is "# johab844: Hangul redrawn on the base face svf/dos/NEODG16.SVF (OFL); the chosen range is ignored"
def test_repo_head_build_id(self):
    # tmp/BUILD_ID "abc1234 2026-11-05 sidecar 0.1.0\n" -> repo_head(tmp) == "abc1234 2026-11-05 sidecar 0.1.0";
    # a 300-char line -> the first 200; an empty file -> falls through;
    # no BUILD_ID, toolrun.FROZEN patched True and subprocess.run patched to fail the test if called -> "unknown";
    # no BUILD_ID, not frozen, a non-git dir -> "unknown" (today's behaviour)
```

  In `test_jobs.py` and `test_preview.py`: `test_env_from_base_env`: `jobs.ENV == toolrun.base_env(os.environ)` and
  the same for `preview.ENV`.

  In `maker/test/test_sidecar_imports.py` (promoting `desktop/spike/import_graph.py`'s `modules`/`imports`/`reachable`
  into the test file; the spike file is not imported):

```python
ROOTS = ["server", "jamoset", "jamovec", "mkfont", "macfbit_svf", "macfbit3", "macsfnt", "bdfface", "johab844",
         "svf2to3", "svfdy", "svfline", "srcprep"]
EXPECTED = {"archive", "bdfface", "caps", "detect", "jamoaa", "jamoadapt", "jamofit", "jamoset", "jamovec", "jobs",
            "johab844", "macfbit3", "macfbit_svf", "macsfnt", "mkfont", "naming", "presets", "preview", "quality",
            "routes", "server", "settings", "sources", "srcprep", "svf2to3", "svfdy", "svfline", "toolrun", "zipout"}
def test_reachable_set(self):           # == EXPECTED (the spec's 28 + toolrun)
def test_third_party(self):             # third-party names == {"PIL", "fontTools", "freetype", "uharfbuzz"}
def test_no_file_relative_data(self):   # every os.path.join(os.path.dirname(__file__), ...) in a reachable module
                                        # (ast) is listed in KNOWN_DATA = {"jamoset": ["testdata/mac-fbit-golden.json"]}
                                        # and each listed path's existence is printed (spec 7.5)
```

- [ ] **Step 2: Run** `python3 -m unittest maker.test.test_toolrun maker.test.test_sidecar_imports -v` (from the root,
  or `discover -s maker/test -p 'test_toolrun.py'`). Expected: FAIL (`No module named 'toolrun'`).
- [ ] **Step 3: Implement** `maker/toolrun.py` to the interface; then the sites of spec 7.3: each
  `PY + [_tool(paths, "X.py"), ...]` -> `toolrun.tool("X", paths["tools"]) + [...]`; each `PY + [SRCPREP, ...]` ->
  `toolrun.maker_script("srcprep") + [...]`; `PY + [os.path.join(tools_dir, "X.py"), ...]` ->
  `toolrun.tool("X", tools_dir) + [...]`; `routes.py:386` -> `toolrun.module("fontTools.varLib.instancer") + [...]`;
  `settings.py:1446` -> `toolrun.tool("svfdy", tools_dir) + [...]`; `jobs.py:1514` ->
  `toolrun.maker_script("recog_score") + [...]` (Task 2 replaces it). Delete `routes.PY`, `routes.SRCPREP`,
  `routes._tool` in the same commit. `probe_argv`: `prefix, rest = toolrun.split_prefix(mkfont_argv)`; source
  `rest[0]`, output `rest[1]`, flags `rest[2:]`; the result is `prefix + [src, out_svf, "--size", ...]`.
  `_command_lines`: `shlex.join(toolrun.note_argv(argv))`. `note_commands`: in both branches each argv goes through
  `toolrun.note_prefix` first; the local branch then applies `_note_token` to `rest` only; the johab844 test is
  `prefix and toolrun.prefix_name(<the split prefix>) == "johab844"` (split before the note rewrite);
  `_johab844_comment(rest)` reads the base face from `rest[1]` and `--eng` from `rest` (design issue 1).
- [ ] **Step 4: Fix the existing tests** named in Files: `test_routes.py` builds expectations with
  `toolrun.tool("X", "/T") + [...]` (delete its `PY`); `test_plan_inputs.py` replaces `routes.PY + ["/T/X.py", ...]`
  with `toolrun.tool("X", "/T") + [...]` and `routes.PY + [routes.SRCPREP, ...]` with
  `toolrun.maker_script("srcprep") + [...]`; `test_zipout.py` notes of upload jobs now read
  `python3 -P tools/<name>.py ...` (rewrite those expected strings; every other assertion unchanged).
- [ ] **Step 5: Run** the new and touched modules:
  `python3 -m unittest discover -s maker/test -p 'test_toolrun.py'` and the same for `test_sidecar_imports.py`,
  `test_routes.py`, `test_zipout.py`, `test_plan_inputs.py`, `test_settings.py`, `test_jobs.py`, `test_preview.py`.
  Expected: `OK`.
- [ ] **Step 6: Review diff of every argv prefix** (the S1 review asks for it): `git diff 94011ff -- maker/routes.py
  maker/settings.py maker/jobs.py | grep '^[-+].*argv\|^[-+].*first\|^[-+].*second\|^[-+].*third' > /tmp/s1-argv.diff`
  and attach the line count of removed vs added launch lines (29 and 29) to the commit body.
- [ ] **Step 7: Gates** G1, G2 (expected 914 + 16 = **930**, skipped 14), G3; plus
  `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_*.py'` -> `OK`.
- [ ] **Step 8: Commit** `git add maker/toolrun.py maker/routes.py maker/settings.py maker/jobs.py maker/preview.py
  maker/zipout.py maker/test/test_toolrun.py maker/test/test_sidecar_imports.py maker/test/test_routes.py
  maker/test/test_zipout.py maker/test/test_plan_inputs.py maker/test/test_jobs.py maker/test/test_preview.py &&
  git commit -m "maker: toolrun is the one launcher (source -P / frozen run-tool); notes, BUILD.md and logs show python3 -P in both modes; BUILD_ID; JAMOSET_PYLIB forwarded (t_f04f1355)"`.

Cannot verify here: nothing beyond the frozen run itself (Task 4 runs every launcher form frozen). How the test
degrades: the frozen shape is checked with `mock.patch.object(toolrun, "FROZEN", True)`, which proves the argv and
note text but not that the frozen executable accepts it.

### Task 2: the optional recogniser through an external interpreter (slice S1, part 2; D5)

**Files:**
- Modify: `maker/caps.py`, `maker/toolrun.py` (`recog_argv`), `maker/jobs.py` (`Worker._identity`),
  `maker/server.py` (`Handler._caps` only)
- Test (modify): `maker/test/test_server.py` (caps tests near `:1349`), `test_jobs.py` (`:650-700`, the identity
  tests), `test_local.py` (`:527`)

**Interfaces:**
- Consumes: `toolrun.maker_script`, `toolrun.base_env` (Task 1).
- Produces:
  - `caps.PUBLIC_KEYS = ("wasm", "mask_libs", "recog", "local")`; `caps.RECOG_PROBE_S = 20`.
  - `caps.recog_python(environ) -> str | None`: `SVF_RECOG_PYTHON` when it names an executable file (`os.access(p,
    os.X_OK)`) **and** `recog_dir(environ, probe=False)` is a directory with `recog.py`, and
    `subprocess.run([p, "-I", "-c", "import numpy, torch, PIL, fontTools"], env={"PATH": environ.get("PATH",
    "/usr/bin:/bin"), "HOME": environ.get("HOME", "/"), "LANG": "C.UTF-8"}, stdin=DEVNULL, stdout=DEVNULL,
    stderr=DEVNULL, timeout=RECOG_PROBE_S)` returns 0; else None (a timeout or `OSError` is None).
  - `caps.recog_dir(environ, probe=True)`: today's rule when `probe` (the `find_spec` of numpy and torch in this
    process); with `probe=False` only the directory test.
  - `caps.compute(static_dir, environ, local=False) -> dict`: the four public keys plus private `"recog_python": str
    | None` and `"recog_dir": str | None`. With `SVF_RECOG_PYTHON` set: `recog_python = recog_python(environ)`,
    `recog_dir = <the dir>` when that succeeded, `recog = recog_python is not None`. Without it: `recog_dir =
    recog_dir(environ)` (today), `recog_python = None`, `recog = recog_dir is not None`.
  - `server.Handler._caps` -> `{key: bool(self.server.caps.get(key)) for key in caps.PUBLIC_KEYS}`.
  - `toolrun.recog_argv(caps: dict, repo_dir: str) -> list | None`: None when not `caps.get("recog")`;
    `[caps["recog_python"], "-P", <repo_dir>/maker/recog_score.py]` when `recog_python` is set; else
    `toolrun.maker_script("recog_score")` (source mode; frozen without an external interpreter is never `recog`).
  - `Worker._identity`: `prefix = toolrun.recog_argv(self.caps, self.repo_dir)`; None -> today's structural result;
    the step env adds `SVF_RECOG_DIR=self.caps["recog_dir"]`. No `caps.recog_dir` call per step.

- [ ] **Step 1: Write the failing tests** (`test_server.py`, new class `RecogCapsTest`; a temp dir holds a stub
  `recog.py` and executable shell stubs written by the test):

```python
def test_external_interpreter_probe_ok(self):        # stub "#!/bin/sh\nexit 0": compute(...)["recog"] is True,
                                                     # ["recog_python"] == stub, ["recog_dir"] == the dir
def test_external_interpreter_probe_fails(self):     # stub exit 1 -> recog False, recog_python None
def test_external_interpreter_probe_times_out(self): # stub "sleep 30", RECOG_PROBE_S patched to 0.5: False within 3 s
def test_external_interpreter_needs_recog_py(self):  # SVF_RECOG_DIR without recog.py: the stub is never run (a stub that
                                                     # writes a marker file; the marker is absent), recog False
def test_probe_env_is_scrubbed(self):                # a stub that dumps `env` to a file: keys == {PATH, HOME, LANG}
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

  `test_jobs.py`: rewrite the two identity tests that patch `caps.recog_dir` (`:658`, `:689`) to build the Worker with
  `caps={"recog": True, "recog_dir": stub, "recog_python": None}`, and add `test_identity_no_per_step_probe`:
  `caps.recog_dir` patched to raise; a jamo step's identity still runs. `test_local.py:527`: the same rewrite.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_server.py -k RecogCapsTest` and
  `-p test_toolrun.py -k recog`. Expected: FAIL.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run** `test_server.py`, `test_jobs.py`, `test_local.py`, `test_toolrun.py`, `test_recog_score.py`.
  Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (expected **938**), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: optional recogniser through SVF_RECOG_PYTHON (probed once at start, four packages, scrubbed env); /api/caps serves the public keys only (t_f04f1355)"`.

Cannot verify here: a real recogniser (numpy/torch are not installed). How it degrades: the probe is driven with shell
stubs; Task 4 runs a stub interpreter against the frozen sidecar end to end.

**Group A review gate.** The reviewer diffs every argv prefix before/after (Task 1 Step 6 output), runs
`test_toolrun.py` with `FROZEN` patched, and checks `GET /api/caps` keys.

---

# Group B: the sidecar (slice S2)

Tasks 3 -> 4, sequential, after Group A (S2 rebased on S1; `jobs.py`, `preview.py`, `server.py`). One review after
Task 4; the reviewer runs the frozen test themselves.

### Task 3: server lifecycle for a shell: `--exit-with-parent`, the tool registry, one stop (slice S2, part 1)

**Files:**
- Create: `maker/toolreg.py`, `maker/test/test_toolreg.py`
- Modify: `maker/server.py` (`main`, `make_server`, `terminate`), `maker/jobs.py` (`run_command`, `Worker.stop`),
  `maker/preview.py` (`run_bounded`), `maker/toolrun.py` (`launcher`, `set_pdeathsig`)
- Test (modify): `maker/test/test_server_signals.py`, `test_jobs.py`, `test_preview.py`,
  `maker/test/test_sidecar_imports.py` (`EXPECTED` gains `toolreg`)

**Interfaces:**
- Produces:
  - `toolrun.launcher() -> str` (`sys.executable`); `toolrun.set_pdeathsig(sig: int) -> bool`: Linux only, `ctypes`
    `prctl(PR_SET_PDEATHSIG=1, sig)`; False (no exception) elsewhere or on failure, and False without calling prctl
    when `os.environ.get("SVF_MAKER_NO_PDEATHSIG") == "1"` (test-only knob, spec 7.10).
  - `toolreg.REAP_EACH_S = 5.0`, `toolreg.REAP_TOTAL_S = 10.0`; `toolreg.configure(data_root: str | None)` sets the
    module's registry path `<data_root>/tools.pids` (None: no registry; the runners called by unit tests without a
    server keep today's behaviour - design issue 7).
  - `toolreg.start_time(pid: int) -> str | None`: `/proc/<pid>/stat` field 22 (parse after the last `)`), else
    `ps -o lstart= -p <pid>` on darwin, else None.
  - `toolreg.register(proc: subprocess.Popen)` / `toolreg.unregister(proc)`: append / remove the line
    `"<pgid> <pid> <start time> <argv0>\n"` (`argv0 = proc.args[0]`; pgid = pid since `start_new_session`), under
    `fcntl.flock` on `<data_root>/tools.pids.lock`; no-op when unconfigured; any `OSError` is printed with
    `jobs.print_exc`-style one line to stderr and ignored (a registry failure never fails a tool).
  - `toolreg.reap(launcher: str) -> dict`: `{"killed": n, "stale": n, "stuck": n}`; for each line whose pid's
    `start_time` equals the recorded one and whose argv0 equals `launcher`: `os.killpg(pgid, SIGKILL)` and wait for the
    pid to vanish (poll `/proc/<pid>` or `os.kill(pid, 0)`, `REAP_EACH_S`), all within `REAP_TOTAL_S`; then truncate
    the file. A line that does not match is `stale` and left alone (not killed).
  - `jobs.run_command` / `preview.run_bounded`: `toolreg.register(proc)` right after `Popen`, `toolreg.unregister(proc)`
    when the child is reaped (`run_command`'s `finally` after the last `_signal_group`; `run_bounded`'s `finally`).
  - `make_server(...)`: `toolreg.configure(store.data_root)` and `toolreg.reap(toolrun.launcher())` right after
    `store = jobs.Store(data_root)`, before `caps.compute`, `worker.recover()` and `startup_cleanup()` (design issue 5).
  - `Worker.stop(timeout=30)`: a completed stop sets `self._stopped = True`; a later call returns the first call's
    result at once (no second sweep).
  - `server.main(argv=None)`: `argparse.ArgumentParser(prog="server.py")` with `--exit-with-parent PID` (int);
    unknown option -> exit 2 (argparse). With the option: before `make_server`, start daemon thread
    `svf-maker-parent-watch` polling `os.getppid() != PID` every 2 s, and `toolrun.set_pdeathsig(signal.SIGTERM)`.
    `server._detach_stdio()`: `os.dup2` of `/dev/null` onto fds 1 and 2 (once). The watch thread calls
    `_detach_stdio()` then `os.kill(os.getpid(), SIGTERM)`. **`terminate()` also calls `_detach_stdio()` when
    `--exit-with-parent` was given and `os.getppid() != PID`** - PDEATHSIG's SIGTERM arrives without the watch thread
    (design issue 6).

- [ ] **Step 1: Write the failing tests.** `maker/test/test_toolreg.py`:

```python
def test_line_while_running_none_after(self):     # configure(tmp); a run_command child sleeping 2 s on a thread:
                                                  # tools.pids has 1 line naming its pid while it runs; 0 lines after
def test_run_bounded_registers(self):             # same for preview.run_bounded
def test_unconfigured_is_noop(self):              # configure(None): run_command works, no file anywhere
def test_reap_kills_matching_group(self):         # a sleeper Popen([sys.executable, "-c", "time.sleep(60)"],
                                                  # start_new_session=True) + its own child; line written with the real
                                                  # start time: reap(sys.executable) -> killed 1; both pids gone; file empty
def test_reap_leaves_stale_line(self):            # the same sleeper with start time "1": stale 1, still alive (killed in cleanup)
def test_reap_leaves_other_launcher(self):        # argv0 "/usr/bin/other": stale 1, alive
def test_reap_bounded(self):                      # killpg patched to do nothing: reap returns within REAP_TOTAL_S + 1 s, stuck 1
```

  `test_jobs.py`: `test_stop_twice_sweeps_once` (`sweep_local_files` patched to count; `stop()` twice -> count 1,
  second call returns in under 0.1 s). `test_server_signals.py`:

```python
def test_main_refuses_unknown_option(self):     # python3 -P maker/server.py --nope -> exit 2, stdout empty
def test_reap_before_cleanup(self):             # a data root whose tools.pids names a live sleeper group (real start time,
                                                # argv0 sys.executable): start the server subprocess with the token; when the
                                                # port line arrives the sleeper is gone and tools.pids is empty
def test_exit_with_parent_pdeathsig(self):      # see below; default env
def test_exit_with_parent_poll(self):           # the same with SVF_MAKER_NO_PDEATHSIG=1 (the 2 s poll path alone)
```

  The two exit-with-parent tests: the test process makes itself a child subreaper (`ctypes` `prctl(36, 1)`;
  `skipTest` off Linux) so the orphaned server is reparented to it and `os.waitpid` gives its exit status. A helper
  `python3 -c` process starts `python3 -P maker/server.py --exit-with-parent=<helper pid>` with the token,
  `SVF_MAKER_BIND=127.0.0.1:0` and stdout/stderr pipes **to the helper**, relays the port line and the server pid on
  its own stdout, then sleeps. The test creates a local job through HTTP (its files directory exists), SIGKILLs the
  helper (the pipes' read ends close), and asserts: `os.waitpid(server_pid, 0)` within 5 s, exit status 0, the job's
  `.svf-maker-<id>/` gone.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_toolreg.py'` and `-p
  test_server_signals.py`. Expected: FAIL (`No module named 'toolreg'`, unknown option accepted).
- [ ] **Step 3: Implement** to the interfaces. The registry line format and lock are as stated (spec 12 left them to
  the builder).
- [ ] **Step 4: Run** `test_toolreg.py`, `test_server_signals.py`, `test_jobs.py`, `test_preview.py`, `test_local.py`,
  `test_sidecar_imports.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (expected **950**), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: --exit-with-parent (getppid poll + PR_SET_PDEATHSIG, stdio detached before the stop), tool registry reaped before recover, Worker.stop sweeps once (t_f04f1355)"`.

Cannot verify here: macOS `ps -o lstart` start times (the darwin branch is untested); a `D`-state process during the
reap. How it degrades: the reap's bound is tested with `killpg` patched.

### Task 4: `maker/sidecar.py`, the PyInstaller spec, the build script, the frozen test (slice S2, part 2)

**Files:**
- Create: `maker/sidecar.py`, `maker/sidecar.spec`, `maker/build-sidecar.sh`, `desktop/build/requirements-sidecar.txt`,
  `maker/test/test_sidecar.py`, `maker/test/test_frozen.py`
- Modify: `maker/test/localfx.py` (`SubprocessLocalBase`), `maker/test/inputfx.py` (`big_composite_ttf`),
  `maker/test/test_sidecar_imports.py` (roots), `.gitignore` (`desktop/build/out/`)

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
  - `run_tool(name: str, args: list) -> NoReturn`: frozen and on Linux, `ppid = os.getppid()`,
    `toolrun.set_pdeathsig(signal.SIGKILL)`, then `os._exit(1)` if `os.getppid() != ppid` (the parent died before the
    prctl); unknown name -> stderr `run-tool: unknown tool 'X'`, exit 2; `sys.argv = [name + ".py", *args]` (bare:
    `main(); sys.exit(0)`; exit: `sys.exit(main())`; args: `sys.exit(main(args))`); any exception other than
    `SystemExit` -> `traceback.print_exc()`, exit 1.
  - `GRAPH_MODULES: tuple[str, ...]`: the reachable set of `test_sidecar_imports.reachable(["sidecar"])`, sorted.
  - `selfcheck() -> dict`: `{"frozen", "version", "build_id" (BUILD_ID beside `SVF_MAKER_REPO` or "unknown"),
    "python", "flags": {"isolated", "ignore_environment", "safe_path", "no_site"}, "path", "tools": sorted(TOOLS),
    "modules": {name: null | "<error>"} for every GRAPH_MODULES name imported, "budget": {"startup_cleanup_s",
    "stop_timeout_s" (Worker.stop's default via inspect), "stop_sweep_s", "reap_total_s", "recog_probe_s"}}`.
  - `main(argv=None)`: `serve [ARGS]` -> `server.main(ARGS)`; `run-tool NAME ARGS...`; `selfcheck` (JSON, exit 0 when
    every module imported, else 1); `--version` -> `svf-maker-sidecar 0.1.0 <build id> python <x.y.z>`; anything else
    -> usage on stderr, exit 2. Source mode inserts `maker/` and `tools/` into `sys.path` first (as `server.py`).
- Produces (`maker/build-sidecar.sh [--no-test]`): steps in order, `set -euo pipefail`, run from the checkout root:
  `bash maker/build-wasm.sh` (stops with its own message without emsdk); `pip install --target
  desktop/build/out/pysite -r desktop/build/requirements-sidecar.txt` (skipped when `pysite/.ok` names the same
  requirements sha256); export `SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)`; `PYTHONPATH=desktop/build/out/pysite
  python3 -S -m PyInstaller --noconfirm --clean --workpath desktop/build/out/pyi-work --distpath
  desktop/build/out/sidecar maker/sidecar.spec`; stage `desktop/build/out/repo/` = `svf/` whole, `web/mkindex.py`,
  `web/LICENCES.tsv`, `web/FAMILIES.tsv`, `tools/*.py` and `maker/*.py` without `test_*.py`, no `__pycache__`, no
  `testdata/`; write `desktop/build/out/repo/BUILD_ID` = `"<git describe --always --dirty> <commit date
  YYYY-MM-DD> sidecar 0.1.0"`; run `selfcheck` under `env -i`; unless `--no-test`, run `test_frozen.py` with
  `SVF_MAKER_SIDECAR`, `SVF_MAKER_REF_SITE=desktop/build/out/pysite`, `SVF_MAKER_STAGED_REPO=desktop/build/out/repo`.
- Produces (`maker/test/localfx.py`): `SubprocessLocalBase(LocalBase)` whose `setUp` starts `[SVF_MAKER_SIDECAR,
  "serve"]` under `env -i`-like `{PATH: <empty dir>, HOME, LANG, SVF_MAKER_TOKEN, SVF_MAKER_BIND=127.0.0.1:0,
  SVF_MAKER_DATA, SVF_MAKER_REPO}`, reads the port line (2 s), sets `self.port`, `self.proc`; `_stop` SIGTERMs and
  waits; `owns(jid)` (a new `LocalBase` method, in-process: `self.srv.worker.owns(jid)`) returns False after the
  job's state has been final on two polls 0.2 s apart. `wait_done` calls `self.owns`.
- Produces (`maker/test/inputfx.py`): `big_composite_ttf(n: int) -> bytes`: the composite fixture with `n`
  composite Hangul glyphs (the implementer picks `n` so that `jamovec master` runs at least 20 s here, and records the
  measured seconds in a comment; spec 12 leaves the size open).

- [ ] **Step 1: Write the failing source-mode tests** `maker/test/test_sidecar.py` (run `python3 -P
  maker/sidecar.py ...` as a subprocess):

```python
def test_table_is_the_spec_table(self):     # sorted(sidecar.TOOLS) == ["bdfface","instancer","jamoset","jamovec","johab844",
                                            #  "macfbit3","macfbit_svf","macsfnt","mkfont","srcprep","svf2to3","svfdy","svfline"]
def test_every_tool_help(self):             # for each name: run-tool <name> --help -> exit 0, stdout starts "usage: <name>.py"
                                            # ("usage: fonttools varLib.instancer" for instancer)
def test_unknown_tool(self):                # run-tool nosuch -> exit 2, stderr "run-tool: unknown tool 'nosuch'"
def test_traceback_exit_1(self):            # run-tool svfline <a directory as input> -> exit 1 (or the tool's own code if it
                                            # catches it: the implementer picks an input that raises uncaught and names it),
                                            # "Traceback" in stderr
def test_bare_main_exit_code(self):         # run-tool mkfont with valid args -> exit 0 and the output equals
                                            # python3 -P tools/mkfont.py with the same args (cmp)
def test_selfcheck_source(self):            # selfcheck JSON: frozen False, tools == the table, every modules value null,
                                            # budget == {30.0, 30, 8.0, 10.0, 20}
def test_version(self):                     # --version matches r"^svf-maker-sidecar 0\.1\.0 .+ python 3\.\d+\.\d+$"
def test_serve_passes_args(self):           # serve --nope -> exit 2 (server.main's parser)
```

  `test_sidecar_imports.py`: `ROOTS = ["sidecar"]`; `test_reachable_set` asserts the computed set ==
  `set(sidecar.GRAPH_MODULES)` and that it contains `EXPECTED | {"sidecar", "toolreg"}`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_sidecar*.py'`. Expected: FAIL.
- [ ] **Step 3: Implement** `maker/sidecar.py`. Run Step 2 again: `OK`.
- [ ] **Step 4: Write** `maker/sidecar.spec` exactly as spec 8.3 (the `HIDDEN` lists computed before `Analysis`,
  `pathex` maker + tools, `datas` static, the full `excludes` list, `upx=False`, `strip=False`, `console=True`,
  name `svf-maker-sidecar`), `desktop/build/requirements-sidecar.txt`, `maker/build-sidecar.sh`; add
  `desktop/build/out/` to `.gitignore`.
- [ ] **Step 5: Build** `~/.local/bin/heavy bash maker/build-sidecar.sh --no-test` (announce START/FINISH). Expected:
  `desktop/build/out/sidecar/svf-maker-sidecar/svf-maker-sidecar` exists; `du -sm` of its directory <= 60; the
  `selfcheck` line printed with every module `null`; `ls desktop/build/out/sidecar/svf-maker-sidecar/_internal` has no
  `wx`, `numpy`, `setuptools`, `pkg_resources`, `libreadline*`, `libtinfo*`. If `python3 -S -m PyInstaller` itself
  fails, record the error, retry with plain `python3 -m PyInstaller` (the excludes still apply) and write it under
  "Design issues" in the commit body.
- [ ] **Step 6: Write the frozen tests** `maker/test/test_frozen.py`, every class skipped unless `SVF_MAKER_SIDECAR`
  names an executable (skip message names the variable). `S` = the sidecar; `ENVI` = `{"PATH": <empty tmp dir>,
  "HOME": home, "LANG": "C.UTF-8", "PYTHONPATH": <tmp dir holding a planted json.py that raises>}`; `REPO` =
  `SVF_MAKER_STAGED_REPO` or the checkout. Reference = `[python3, "-S", "-P", <checkout>/tools/X.py]` with
  `PYTHONPATH=$SVF_MAKER_REF_SITE` (skip the byte-equal class without it):

```python
class FrozenSelfcheckTest:
    def test_selfcheck(self):                  # frozen True; the four flags True; every path entry under dirname(S);
                                               # tools == test_sidecar's table; set(modules) == set(sidecar.GRAPH_MODULES),
                                               # all null; budget == the Python constants imported in this test process
class FrozenRunToolTest:
    def test_every_tool_help_isolated(self):   # each name, env ENVI, cwd = a dir holding a planted jamoset.py that raises:
                                               # exit 0, "usage: <name>.py"; nothing shadowed
    def test_unknown_and_traceback(self):      # nosuch -> 2; the Task 4 Step 1 raising input -> 1, "Traceback", no "[PYI-"
class FrozenByteEqualTest:                     # the OFL sample set, frozen output cmp-equal to the reference
    def test_mkfont_neodgm_16_1(self):         # ttf/neodgm/neodgm.ttf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul (115,460 bytes)
    def test_mkfont_nanumgothic_17_2(self):    # ttf/nanumgothic/NanumGothic-Bold.ttf --size 17 --bpp 2 (207,684 bytes)
    def test_jamoset_dos_844(self):            # inputfx.dos844_24() fixture, --layout 844 --check
    def test_jamoset_from_ttf_adaptive(self):  # inputfx.ttf(...) composite-capable fixture, --layout adaptive --from-ttf
    def test_srcprep_ttc_face(self):           # inputfx.ttc([...]) --index 1
    def test_instancer_real_op(self):          # inputfx.variable_ttf() with wght=400 -o OUT
    def test_macsfnt_extract_unicode(self):    # inputfx.fork([...sfnt...]) extract --id 128, then unicode
    def test_johab844(self):                   # inputfx.dos844_24()-family 16 px fixture + REPO/svf/dos/NEODG16.SVF
    def test_debian_pillow_informational(self):# the same mkfont 16/1 with plain python3 -P: prints "equal" or "differs: <sizes>"; never fails
class FrozenServeTest(localfx.SubprocessLocalBase):
    def test_port_line_fast(self):             # the port line within 2 s on a clean data root
    def test_stale_files_swept_before_port(self):  # a planted pending-sweeps record + stale .svf-maker-<id>/: gone when the line arrives
    def test_http_basics(self):                # / 200; /static/wasm/svf.wasm 200 application/wasm; /api/caps 403 then 200
                                               # {"wasm": true, "mask_libs": false, "recog": false, "local": true}
    def test_frozen_jobs_byte_equal(self):     # LocalRunBase's select() job run here and in an in-process LocalBase server:
                                               # every written face cmp-equal; result.files equal
    def test_frozen_notes_equal_source(self):  # NEODU.TXT-style notes and build-<id>/BUILD.md command lines equal to the
                                               # source run's; no line contains dirname(S) or "run-tool"; a johab844 step's
                                               # comment line present
    def test_jamo_adaptive_job(self):          # a jamo adaptive job -> done
    def test_recog_both_ways(self):            # (a) no SVF_RECOG_*: caps recog false, jamo step identity {"available": false};
                                               # (b) SVF_RECOG_PYTHON = a shell stub that exits 0 for "-I -c ..." and otherwise
                                               #     execs python3 (design issue 3), SVF_RECOG_DIR = test_recog_score's stub
                                               #     recog.py dir: caps recog true, the step's identity.json exists
    def test_sigterm_cancels_tool(self):       # a job on big_composite_ttf; once the step runs, SIGTERM the sidecar: exit 0,
                                               # `pgrep -g <tool pgid>` empty, the files dir gone, tools.pids empty
    def test_sigkill_sidecar_kills_tool(self): # the same job, SIGKILL the sidecar: the tool pid gone within 3 s
    def test_sigkill_without_pdeathsig_reaped_on_restart(self):  # SVF_MAKER_NO_PDEATHSIG=1 in the sidecar env: after
                                               # SIGKILL the tool is alive and named in tools.pids; a new serve on the same
                                               # data root: the tool gone before the port line, the files dir gone, the job
                                               # state "failed" with error "interrupted"
    def test_bad_token_and_bind(self):         # SVF_MAKER_TOKEN=xyz -> exit 2 "SVF_MAKER_TOKEN: 32 hex characters";
                                               # good token + 0.0.0.0:0 -> exit 2 "local mode binds 127.0.0.1 or ::1 only"; stdout empty
```

- [ ] **Step 7: Run** `~/.local/bin/heavy bash maker/build-sidecar.sh` (announce). Expected: the frozen test `OK`
  with no skip except the informational test's print; `selfcheck` clean. Then run the suite once without the
  variable: every `test_frozen` class skipped with the message.
- [ ] **Step 8: Gates** G1, G2 (expected **~981**: +8 `test_sidecar`, +1 imports, ~22 `test_frozen` skipped; record
  the observed N and skips), G3.
- [ ] **Step 9: Commit** `git add maker/sidecar.py maker/sidecar.spec maker/build-sidecar.sh
  desktop/build/requirements-sidecar.txt maker/test/test_sidecar.py maker/test/test_frozen.py maker/test/localfx.py
  maker/test/inputfx.py maker/test/test_sidecar_imports.py .gitignore && git commit -m "maker: frozen sidecar (serve | run-tool | selfcheck), PyInstaller one-dir spec and build script; frozen test byte-equal to the pinned wheels under env -i (t_e64a56a7, t_f04f1355)"`.
  The commit body records: sidecar size, build seconds, frozen test counts, the Debian-Pillow comparison result.

Cannot verify here: macOS/Windows freezes (8.11); glibc < 2.39; `JAMOSET_PYLIB` with real 3.12 freetype-py/uharfbuzz
in the frozen process (no such libs here: `mask_libs` stays false and the test asserts that); a real recogniser. How
it degrades: the recogniser runs through a stub interpreter; the byte-equal reference is the pinned wheels through
`python3 -S`, not a venv.

**Group B review gate.** The reviewer runs `~/.local/bin/heavy bash maker/build-sidecar.sh` and the frozen test
themselves, opens `selfcheck` output, and checks `ps -eo pid,pgid,args | grep run-tool` is empty after the run.

---

# Group C: the shell (slice S3)

Task 5 may be developed in its own worktree as soon as Group A has landed (it touches `desktop/` only); it **lands
after Task 3** (its budget test reads `toolreg.REAP_TOTAL_S`). Task 6 starts after Task 5 and Task 3 have landed (its
dev command relies on `--exit-with-parent`) and lands after Task 4 (its packaged pass and its version test need
`maker/sidecar.py`). One review after Task 6; the
reviewer runs the xvfb tests.

### Task 5: `desktop/` package and pure helpers with node unit tests (slice S3, part 1)

**Files:**
- Create: `desktop/package.json`, `desktop/package-lock.json`, `desktop/lib/{env,portline,guard,budget,shutdown,
  restart,sandbox,paths,log,state}.js`, `desktop/test/unit.test.js`
- Modify: `.gitignore` (`desktop/node_modules/`, `desktop/dist/`)

Module form (spec 12 leaves it to the builder): **CommonJS everywhere** (`.js`, no `"type"` field), so `main.js`,
the sandboxed `preload.js` and the helpers share one form and `node --test` imports them directly (design issue 10).

**Interfaces (produced):**
- `package.json`: `name "svf-maker"`, `version "0.1.0"`, `private true`, `main "main.js"`, `license "MIT"`, no
  `dependencies`, `devDependencies {"electron": "45.2.3", "electron-builder": "26.18.0"}`, `scripts {"test": "node
  --test test/", "e2e": "bash test/run-e2e.sh"}`.
- `env.js`: `ENV_KEYS = ["PATH","HOME","LANG","SVF_MAKER_TOKEN","SVF_MAKER_BIND","SVF_MAKER_DATA","SVF_MAKER_REPO",
  "SVF_MAKER_ROOTS","JAMOSET_PYLIB","SVF_RECOG_DIR","SVF_RECOG_PYTHON"]`, `PASS_KEYS` = the last four;
  `buildEnv(parentEnv, {repo, data}) -> {env, token}`: `token = crypto.randomBytes(16).toString("hex")`,
  `LANG "C.UTF-8"`, `SVF_MAKER_BIND "127.0.0.1:0"`, `PATH`/`HOME` from `parentEnv` (defaults `/usr/bin:/bin`,
  `os.homedir()`), pass-throughs only when set and non-empty.
- `portline.js`: `parsePortLine(text) -> {host, port} | null` with `/^svf-maker listening on (127\.0\.0\.1|::1):(\d+)\r?\n/m`.
- `guard.js`: `isOurs(origin, url, {startingUrl, devtools}) -> bool` (spec 6.3: `url === origin + "/"` or
  `startsWith(origin + "/")`, the exact `startingUrl`, `devtools://` only when `devtools`);
  `withToken(url, headers, sidecar) -> headers` (a new object: every key equal to `x-maker-token` case-insensitively
  removed; `X-Maker-Token = sidecar.token` only when `url.startsWith(sidecar.origin + "/")` and the URL's pathname
  starts with `/api/`).
- `budget.js`: `SERVER = {startupCleanupS: 30, recogProbeS: 20, reapTotalS: 10, stopTimeoutS: 30, joinS: 1,
  stopSweepS: 8}`, `HANDSHAKE_S = 75`, `STOP_WAIT_S = 45`, `KILL_WAIT_S = 5`, `STARTING_PAGE_S = 2`.
- `shutdown.js`: `stopSidecar(child, {termWaitS, killWaitS, kill = process.kill}) -> Promise<{code, signal,
  escalated}>`: `kill(-child.pid, "SIGTERM")`, wait for `exit` up to `termWaitS`, then `kill(-child.pid, "SIGKILL")`
  and wait `killWaitS`; resolves at once when the child has already exited; `ESRCH` ignored.
- `restart.js`: `restartAllowed(history: number[], now: number) -> boolean` (fewer than 3 entries within 300,000 ms).
- `sandbox.js`: `readSandbox(pid, readFile = fs.readFileSync) -> {seccomp, noNewPrivs} | null` (`/proc/<pid>/status`
  `Seccomp:` and `NoNewPrivs:`; null off Linux or on error); `sandboxText(state, noSandboxSwitch) -> "renderer
  sandbox: off (user namespaces unavailable)" | "renderer sandbox: on" | "renderer sandbox: unknown"`.
- `paths.js`: `resolveLaunch({resourcesPath, appDir, env, pid, userData, exists = fs.existsSync}) -> {mode, cmd, args,
  repo, data}`: packaged when `<resourcesPath>/sidecar/svf-maker-sidecar/svf-maker-sidecar` exists and
  `env.SVF_MAKER_DEV !== "1"`: `cmd` that path, `args ["serve", "--exit-with-parent=" + pid]`, `repo
  <resourcesPath>/repo`, `data <userData>/maker`; else dev: `cmd "python3"`, `args ["-P", <checkout>/maker/server.py,
  "--exit-with-parent=" + pid]`, `checkout = env.SVF_MAKER_DEV_REPO || path.dirname(appDir)`, `repo checkout`, `data
  <userData>/maker-dev`.
- `log.js`: `createLog({dir, toStderr, maxBytes = 1 << 20}) -> {line(text), path}`: appends `<ISO time> <text>\n` to
  `<dir>/shell.log`, rotates to `shell.log.1` past `maxBytes` (two files kept); `toStderr` mirrors to stderr.
  `pathsLine(channel, paths) -> "<channel>: <n>"` (counts only).
- `state.js`: `loadState(file) -> {bounds, zoom, lastInputDir, lastOutputDir, handedOut: string[]}` (defaults on a
  missing or bad file), `saveState(file, state)` (atomic rename; never a token key: `saveState` drops any key not in
  that list).

- [ ] **Step 1: Write the failing tests** `desktop/test/unit.test.js` (`node:test`, `node:assert/strict`):

```js
test("parsePortLine", () => {
  assert.deepEqual(parsePortLine("svf-maker listening on 127.0.0.1:38253\n"), {host: "127.0.0.1", port: 38253});
  assert.equal(parsePortLine("svf-maker listening on 127.0.0.1:382"), null);          // no newline yet
  assert.equal(parsePortLine("noise\nsvf-maker listening on 127.0.0.1:5\nmore\n").port, 5);
  assert.deepEqual(parsePortLine("svf-maker listening on ::1:9\n"), {host: "::1", port: 9});
  assert.equal(parsePortLine("svf-maker listening on 0.0.0.0:9\n"), null);
});
test("isOurs", () => { const o = "http://127.0.0.1:4000", s = "file:///app/starting.html";
  // true: o + "/", o + "/api/caps", s; false: "http://127.0.0.1:4001/", "http://localhost:4000/", o (no slash),
  // "http://127.0.0.1:4000.evil/", "file:///etc/passwd", "devtools://devtools/x" (true only with {devtools: true})
});
test("withToken", () => { const sc = {origin: "http://127.0.0.1:4000", token: "a".repeat(32)};
  // /api/x -> exactly one key matching /x-maker-token/i, value sc.token, even when the input had "x-maker-token": "evil"
  //   and "X-MAKER-TOKEN": "evil2"; "/" and "/static/maker.js" -> no token key (and an injected one removed);
  // "http://127.0.0.1:4001/api/x" (old port) -> no token key
});
test("buildEnv", () => { const parent = {...process.env, SVF_MAKER_TOKEN: "decoy", PYTHONPATH: "/x", SVF_RECOG_PYTHON: "/py"};
  // Object.keys(env) ⊆ ENV_KEYS; token matches /^[0-9a-f]{32}$/ and !== "decoy"; env.SVF_MAKER_TOKEN === token;
  // no PYTHONPATH; SVF_RECOG_PYTHON === "/py"; JAMOSET_PYLIB absent when unset or ""; two calls give different tokens
});
test("budget derives from the server", () => {
  // HANDSHAKE_S === 75 >= startupCleanupS + recogProbeS + reapTotalS; STOP_WAIT_S === 45 >= stopTimeoutS + joinS + stopSweepS;
  // and SERVER matches the Python source by regex: maker/server.py STARTUP_CLEANUP_S = 30.0; maker/jobs.py
  // STOP_SWEEP_TOTAL_S = 8.0 and "def stop(self, timeout=30)"; maker/caps.py RECOG_PROBE_S = 20; maker/toolreg.py REAP_TOTAL_S = 10.0
});
test("stopSidecar", async () => {
  // a real child: spawn(process.execPath, ["-e", "process.on('SIGTERM',()=>process.exit(0)); setInterval(()=>{},1e3)"], {detached: true})
  //   -> {code: 0, escalated: false} within 2 s;
  // a child ignoring SIGTERM with termWaitS 0.3 -> escalated true, signal "SIGKILL"; an already-exited child resolves at once
});
test("restartAllowed", () => { /* [] true; [t-1,t-2] true; [t-1,t-2,t-3] false; three entries older than 300 s true */ });
test("readSandbox / sandboxText", () => { /* a fake status text "Seccomp:\t0\nNoNewPrivs:\t1\n" -> {seccomp: 0, noNewPrivs: 1};
  sandboxText({seccomp: 0}, true) === "renderer sandbox: off (user namespaces unavailable)"; {seccomp: 2} -> "renderer sandbox: on" */ });
test("resolveLaunch", () => { /* packaged (exists stub true) and dev (false, or SVF_MAKER_DEV=1) shapes exactly as the interface */ });
test("log rotation and privacy helpers", () => { /* maxBytes 100: three writes of 60 bytes -> shell.log and shell.log.1 only;
  pathsLine("pick-files", ["/home/u/a.ttf", "/b"]) === "pick-files: 2" */ });
test("state never stores a token", () => { /* saveState(f, {zoom: 1.1, token: "x", handedOut: ["/o"]}); the file has no "token" */ });
test("no outbound code (spec 6.9)", () => {
  // over main.js, preload.js, lib/**/*.js (those that exist): no require/import of "electron-updater", "http", "https", "net",
  // "node:http", "node:https", "node:net"; no "autoUpdater"; no "XMLHttpRequest"; no fetch( whose first argument starts with a
  // string or template literal beginning "http" (main.js's one fetch is built from sidecar.origin - design issue 8)
});
```

- [ ] **Step 2: Run** `cd desktop && node --test test/`. Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** the helpers. `cd desktop && npm install --no-audit --no-fund --save-exact -D
  electron@45.2.3 electron-builder@26.18.0 && node node_modules/electron/install.js`; commit the lockfile.
- [ ] **Step 4: Run** G4. Expected: all pass.
- [ ] **Step 5: Gates** G1, G4 (G2 unchanged by this task: run it once after rebasing onto Task 3; expected the
  Task 3 count).
- [ ] **Step 6: Commit** `git add desktop/package.json desktop/package-lock.json desktop/lib desktop/test/unit.test.js
  .gitignore && git commit -m "desktop: shell helpers (env, handshake, guard + token header, budget, shutdown, restart, sandbox, paths, log, state) with node tests (t_f04f1355)"`.

Cannot verify here: nothing beyond the helpers' own logic (Electron is not loaded by these tests).

### Task 6: `main.js`, `preload.js`, the starting page, the icon, the xvfb end-to-end tests (slice S3, part 2)

**Files:**
- Create: `desktop/main.js`, `desktop/preload.js`, `desktop/starting.html`, `desktop/build/make-icon.py`,
  `desktop/build/icon.png`, `desktop/test/e2e.js`, `desktop/test/run-e2e.sh`, `desktop/test/lifecycle.test.js`
- Modify: `desktop/test/unit.test.js` (version equality)

**Interfaces:**
- Consumes: every `desktop/lib` export (Task 5); `server.py --exit-with-parent` (Task 3); the sidecar (Task 4).
- Produces (`main.js`, CommonJS; runs `start()` when `require.main === module`, exports `{start, state}` always):
  - `start({smoke = process.env.SVF_MAKER_SMOKE === "1"} = {}) -> Promise<{win, sidecar}>`: single-instance lock
    first (the loser `app.quit()` before any spawn); session `fromPartition("maker")`; spawn per 6.2 with
    `buildEnv`/`resolveLaunch`, `{detached: true, stdio: ["ignore", "pipe", "pipe"], windowsHide: true, cwd:
    os.homedir()}`; handshake bounded by `HANDSHAKE_S`, `starting.html` after `STARTING_PAGE_S`; the one mutable
    `sidecar = {child, port, origin, token, pid}` read at call time by every handler; `onBeforeSendHeaders({urls:
    ["http://127.0.0.1/*"]})` using `withToken`; `onBeforeRequest({urls: ["<all_urls>"]})` cancelling `!isOurs`;
    `will-download` prevented; the three permission handlers deny; `webPreferences` exactly spec 6.4 with
    `devTools: process.env.SVF_MAKER_DEVTOOLS === "1"`; navigation guards and `web-contents-created`; IPC handlers
    `maker:pick-files`, `maker:pick-folder`, `maker:pick-output-dir`, `maker:open-output` with the sender check
    (`event.senderFrame` non-null and its origin === `sidecar.origin`); `maker:open-output` reads `?job=` from
    `win.webContents.getURL()`, `fetch(sidecar.origin + "/api/jobs/" + id, {headers: {"X-Maker-Token":
    sidecar.token}})`, and calls `shell.showItemInFolder(output_dir)` only when `handedOut` includes it;
    `before-quit` -> `stopSidecar(sidecar.child, {termWaitS: STOP_WAIT_S, killWaitS: KILL_WAIT_S})` then
    `app.exit(0)`; `process.on("SIGINT"|"SIGTERM"|"SIGHUP", () => app.quit())`; sidecar exit while not quitting ->
    `dialog.showMessageBox(win, {buttons: ["Restart", "Quit"]})` with `restartAllowed`; `render-process-gone`
    reload once; the menu of 6.8; About with versions, `BUILD_ID`, `sandboxText(...)` and the THIRD-PARTY button
    (`shell.openPath(<resources>/THIRD-PARTY.txt)`, the one `openPath`).
  - Log lines the tests rely on (exact prefixes): `shell pid=<n>`, `sidecar start mode=<packaged|dev> pid=<n>`,
    `sidecar port=<p>`, `sidecar exit code=<c> signal=<s>`, `sandbox <sandboxText>`, `<channel>: <count>`. With
    `smoke`: after the page's `fetch("/api/caps")` (run through `executeJavaScript`) answers 200 the shell prints
    `svf-maker smoke ok <document.title>` on stdout and calls `win.close()` (the normal close path).
  - `preload.js`: exactly the spec 6.5 block.
  - `starting.html`: static text "starting the maker...", no script, no external reference.
  - `build/make-icon.py`: Pillow draws "ㅅ" from `ttf/neodgm/neodgm.ttf` (OFL) white on a dark square, 512x512, into
    `desktop/build/icon.png` (run once, both files committed).

- [ ] **Step 1: Write the failing tests.** `desktop/test/e2e.js` (the Electron main script; `node:assert`; prints
  `E2E PASS <name>` / `E2E FAIL <name> <message>` and exits 1 on any failure) stubs `dialog.showOpenDialog` (a queue
  of `{canceled, filePaths}`), `dialog.showMessageBox` (resolves `{response: 0}` = Restart) and
  `shell.showItemInFolder` (records the path) on `require("electron")` **before** `require("../main.js").start()`,
  with `SVF_MAKER_DEV=1` (the dev command; `SVF_MAKER_SIDECAR` set -> a second pass with `resourcesPath` pointed at a
  temp dir holding `sidecar -> $SVF_MAKER_SIDECAR`'s directory and `repo -> $SVF_MAKER_STAGED_REPO`):

```text
handshake            sidecar.port > 0 within HANDSHAKE_S; the log has "sidecar port="
title                document.title === "SVF maker"
bridge               typeof each of pickFiles, pickFolder, pickOutputDir, openOutputFolder === "function"; platform === "linux";
                     typeof window.require === "undefined"; typeof window.ipcRenderer === "undefined"
header               page fetch("/api/caps") -> 200; page fetch("/api/caps", {headers: {"X-Maker-Token": "0".repeat(32)}}) -> 200
                     (the shell's value replaced the page's)
outbound             page fetch("http://127.0.0.1:1/x") rejects; window.open("http://example.invalid/") === null;
                     location = "http://example.invalid/" leaves location.origin === sidecar.origin after 1 s
download             an injected <a download href="/static/maker.js"> clicked: no "will-download" save (a counter in the test's
                     own will-download listener registered after the shell's stays 0 saves; no file in ~/Downloads newer than start)
flow                 two local jobs: dialog queue = [tmpA (folder with neodgm.ttf)], [outA], [tmpB], [outB]; for each:
                     #choose-folder, #choose-output, #ack-ok if shown, #detect-local, then a page fetch PUT settings selecting
                     the font (dest dos, precomposed, 16 px, 1 bpp), #run; wait #state contains "written to"; a
                     canvas[data-step][data-drawn="1"] exists
open-folder          load "/?job=<job A id>" (the older job), click #open-folder -> showItemInFolder called with outA
                     (not outB, the last dialog's); a job whose output was not handed out (created by a direct API call)
                     -> not called, the log has "open-output: refused"
ipc-sender           an IPC invoke from a second BrowserWindow loading "about:blank" in the same session is rejected
restart              process.kill(sidecar.pid, "SIGKILL"): the message box stub called; within HANDSHAKE_S a new sidecar
                     with a different token (and pid); the page reloads; page fetch("/api/caps") -> 200
log privacy          shell.log contains neither the old nor the new token, nor tmpA/tmpB/outA/outB, nor "/api/jobs/";
                     it has "pick-folder: 1" lines and one "sandbox renderer sandbox: off (user namespaces unavailable)" line
                     (recorded, not asserted as "on": this host has no userns; spec 8.7)
```

  `desktop/test/lifecycle.test.js` (`node --test`; skipped with a message when `xvfb-run` or the electron binary is
  missing): spawns `xvfb-run -a <electron> --no-sandbox <desktop>` with `SVF_MAKER_DEV=1`,
  `SVF_MAKER_SHELL_LOG=stderr`, a temp `--user-data-dir`, and reads `shell pid=` and `sidecar start ... pid=` from
  stderr:

```js
test("close: smoke ok, sidecar exit 0, nothing left", ...);  // SVF_MAKER_SMOKE=1: stdout "svf-maker smoke ok SVF maker";
                                                             // stderr "sidecar exit code=0"; both pids gone; `pgrep -f run-tool` none
test("SIGTERM to the shell stops the sidecar", ...);         // after the port line: kill(shellPid, "SIGTERM"): "sidecar exit code=0",
                                                             // the shell exits within STOP_WAIT_S + 5
test("SIGKILL of the shell: the sidecar exits by itself", ...); // kill(shellPid, "SIGKILL"): sidecar pid gone within 5 s
                                                             // (--exit-with-parent; a local job created first: its files dir gone)
test("second instance quits at once", ...);                  // a second launch with the same user-data-dir exits within 5 s and
                                                             // spawns no sidecar (no new "sidecar start" line)
```

  `run-e2e.sh`: `cd "$(dirname "$0")/.."`; exits 0 printing `SKIP: <reason>` when `xvfb-run` or
  `node_modules/.bin/electron` is missing; else `xvfb-run -a node_modules/.bin/electron --no-sandbox test/e2e.js`.
  `unit.test.js` gains `test("versions agree")`: `package.json` version === the `VERSION = "..."` of
  `maker/sidecar.py`.
- [ ] **Step 2: Run** `~/.local/bin/heavy bash desktop/test/run-e2e.sh` (announce; no other Chrome running).
  Expected: FAIL (`Cannot find module '../main.js'`).
- [ ] **Step 3: Implement** `main.js`, `preload.js`, `starting.html`; run `python3 desktop/build/make-icon.py`.
- [ ] **Step 4: Run** `~/.local/bin/heavy bash desktop/test/run-e2e.sh`, then `cd desktop && node --test test/`
  (includes `lifecycle.test.js`). Expected: every `E2E PASS`, every node test passes; `pgrep -f svf-maker-sidecar`
  and `pgrep -f 'maker/server.py'` empty afterwards.
- [ ] **Step 5: Packaged pass** (after Task 4 landed): `SVF_MAKER_SIDECAR=$PWD/desktop/build/out/sidecar/svf-maker-sidecar/svf-maker-sidecar
  SVF_MAKER_STAGED_REPO=$PWD/desktop/build/out/repo ~/.local/bin/heavy bash desktop/test/run-e2e.sh`. Expected: both
  passes `E2E PASS`.
- [ ] **Step 6: Gates** G1, G2 (unchanged count; it also proves the page is untouched), G3, G4.
- [ ] **Step 7: Commit** `git add desktop/main.js desktop/preload.js desktop/starting.html desktop/build/make-icon.py
  desktop/build/icon.png desktop/test && git commit -m "desktop: Electron shell (sidecar spawn + handshake, token header, request and navigation guards, four-function bridge, restart, quit sequence, log) with xvfb e2e and lifecycle tests (t_f04f1355)"`.

Cannot verify here: real native file dialogs with a desktop session (stubbed; the manual check goes into
`docs/maker-desktop.md`); a sandboxed renderer (`--no-sandbox` under xvfb; the run records `Seccomp 0`); macOS/Windows
menus, `activate`, `showItemInFolder` in Finder/Explorer. How it degrades: `xvfb-run -a electron --no-sandbox` runs
the real main process code with stubbed dialogs; whether Electron's `http://127.0.0.1/*` filter matches every port is
proven by the restart check (new port, header present), not assumed.

**Group C review gate.** The reviewer runs `run-e2e.sh` (both passes) and `node --test desktop/test/` and reads
`shell.log` of the run for tokens and paths.

---

# Group D: packaging and documents (slices S4, S5)

After Groups B and C. Task 7 -> Task 8 -> Task 9, sequential (`desktop/package.json` in 8; 9 cites 8's numbers). One
review after Task 9 against the cards' closing measurements.

### Task 7: `THIRD-PARTY.txt` generation (slice S4, part 1; spec 8.9, 8.10, D8 per section 17)

**Files:**
- Create: `desktop/build/third-party.mjs`, `desktop/build/third-party-map.json`, `desktop/build/licences/` (upstream
  licence texts the wheels and dpkg do not provide), `desktop/test/third-party.test.js`

**Interfaces:**
- Produces: `node desktop/build/third-party.mjs --sidecar DIR --electron DIR --pysite DIR --repo DIR --out FILE
  [--record FILE]` -> exit 0 and the file; exit 1 with one line per problem on stderr. The module also exports
  `generate({sidecar, electron, pysite, repo, map, dpkg}) -> {text, problems, components}` for the test (`dpkg` an
  injectable `(file) -> {package, version, copyright} | null`, default runs `dpkg -S` and reads
  `/usr/share/doc/<pkg>/copyright`).
- Map entry: `{"match": "<glob over basenames>", "component", "version" | "from": "dpkg" | "wheel", "licence": SPDX,
  "source_url", "copyleft": "none" | "lgpl" | "gpl" | "gcc-rle", "record"?: {"source", "replace"}}`; one entry for
  the AppImage runtime (`appimage-12.0.1`: MIT + squashfuse BSD-2 + static libfuse LGPL-2.1, with the
  electron-builder-binaries URL and the static-link note).
- Rules: every regular file under `<sidecar>/_internal` matching `*.so*` and every `*.so*` under `<electron>` must
  match an entry (fail closed: `unattributed: <path>`); a matching `gpl` entry -> `gpl forbidden: <file>`; an `lgpl`
  entry without `record` -> `lgpl without distribution record: <component>`; `<repo>/svf` must hold only files listed
  in `<repo>/web/LICENCES.tsv`'s globs or licence texts (`not OFL-listed: <path>`); `package.json` `dependencies`
  non-empty -> problem. Sections in the output, in order: the maker (MIT, `LICENSE`), the faces (OFL 1.1, `NOTICE.md`'s
  table), Electron (its `LICENSE` inlined) + Chromium (pointer to `LICENSES.chromium.html`), CPython, Pillow,
  fontTools (from `pysite/*.dist-info`), each native library (component, version, licence, source URL, record, text),
  the AppImage runtime. A trailing "Copyleft check" block lists every `lgpl`/`gcc-rle` component and the line
  `release gate (D8): corresponding sources archived: NO (private build)` unless `--record` names a manifest of
  `desktop/build/out/sources/` that covers each `lgpl` component (then `YES`).

- [ ] **Step 1: Write the failing tests** `desktop/test/third-party.test.js` over a temp fixture tree (fake `.so`
  files, a fake `dist-info`, a mini `repo/svf` + `LICENCES.tsv`, a stub `dpkg`):

```js
test("complete tree -> no problems, every component in the text", ...);
test("an unmatched .so fails closed", ...);            // problems includes "unattributed: _internal/libmystery.so.1"
test("a gpl entry fails", ...);                        // map entry copyleft gpl matched -> "gpl forbidden: ..."
test("lgpl needs a record", ...);                      // libffmpeg.so entry without record -> "lgpl without distribution record: ffmpeg"
test("non-OFL file under repo/svf fails", ...);        // repo/svf/x/FOO.SVF not in LICENCES.tsv globs
test("runtime entry present with its static-link note", ...);
test("gate line says NO without a sources manifest", ...);
```

- [ ] **Step 2: Run** `cd desktop && node --test test/third-party.test.js`. Expected: FAIL.
- [ ] **Step 3: Implement**; then fill `third-party-map.json` against the real build: run `node
  desktop/build/third-party.mjs --sidecar desktop/build/out/sidecar/svf-maker-sidecar --electron
  desktop/node_modules/electron/dist --pysite desktop/build/out/pysite --repo desktop/build/out/repo --out
  desktop/build/out/THIRD-PARTY.txt` and add entries until it exits 0. For each wheel-vendored library, check whether
  `pysite/pillow-10.2.0.dist-info/` carries its licence text; where not, commit the upstream text under
  `desktop/build/licences/<component>.txt` (spec 8.9 "not verified" item). Find which collected library pulls
  `libglib-2.0` (`ldd` over `_internal/*.so*`); if a spec `excludes` entry removes it without breaking `selfcheck`
  and the frozen test, add it to `maker/sidecar.spec` and say so in the commit body; else keep it as `lgpl` with a
  record.
- [ ] **Step 4: Run** G4 and the real generation above. Expected: pass; exit 0; the final copyleft list printed.
- [ ] **Step 5: Gates** G1, G4 (G2 only if `maker/sidecar.spec` changed: then also rebuild and rerun the frozen test).
- [ ] **Step 6: Commit** `git commit -m "desktop: THIRD-PARTY.txt generator (fail closed, GPL forbidden, LGPL distribution records, AppImage runtime entry) (t_e64a56a7)"`; the body lists the copyleft components found.

Cannot verify here: the AppImage runtime's composition beyond its file names (8.9 item 4); the exact Debian source
package URLs resolving (recorded, not fetched). How it degrades: the record carries the URL; fetching sources is the
release gate (D8), documented in Task 9.

### Task 8: electron-builder AppImage and the release check (slice S4, part 2)

**Files:**
- Create: `desktop/build/build-appimage.sh`, `desktop/build/release-check.sh`
- Modify: `desktop/package.json` (the `"build"` block)

**Interfaces:**
- `package.json` `"build"`: `appId "org.svf-fonts.maker"`, `productName "svf-maker"`, `electronVersion "45.2.3"`,
  `npmRebuild false`, `publish null`, `directories {"output": "dist"}`, `files ["main.js", "preload.js",
  "starting.html", "lib/**", "package.json"]`, `extraResources [{"from": "build/out/sidecar/svf-maker-sidecar", "to":
  "sidecar/svf-maker-sidecar"}, {"from": "build/out/repo", "to": "repo"}, {"from": "build/out/THIRD-PARTY.txt", "to":
  "THIRD-PARTY.txt"}]`, `linux {"target": ["AppImage"], "category": "Utility", "icon": "build/icon.png", "desktop":
  {"Name": "SVF maker"}, "syncDesktopName": true}`, `desktopName "svf-maker.desktop"` (the `build/out` paths are
  relative to `desktop/`; `build-sidecar.sh` writes `desktop/build/out/`).
- `build-appimage.sh [--release]` (from the checkout root, `set -euo pipefail`): `maker/build-sidecar.sh` (frozen test
  included); `node desktop/build/third-party.mjs ...` (Task 7's arguments; `--record desktop/build/out/sources/MANIFEST`
  with `--release`); `cd desktop && npx electron-builder --linux AppImage --publish never`; then
  `desktop/build/release-check.sh desktop/dist/svf-maker-0.1.0.AppImage [--release]`.
- `release-check.sh APPIMAGE [--release]` prints one `CHECK <name> ok|FAIL <why>` line per check and exits 1 on any
  FAIL: `size` (AppImage <= 170 MB; `resources/sidecar` <= 60 MB); `extract` (`--appimage-extract` into a temp dir);
  `layout` (spec 8.4: `resources/app.asar`, `resources/sidecar/svf-maker-sidecar/svf-maker-sidecar`,
  `resources/repo/{svf,web,BUILD_ID,tools,maker}`, `resources/THIRD-PARTY.txt`; no `test_*.py`, no `__pycache__`,
  no `testdata` under `resources/repo`); `apprun` (electron-builder's `AppRun` unchanged: it contains `unshare -Ur`
  and `--no-sandbox`; D7 per section 17); `frozen` (`test_frozen.py` with `SVF_MAKER_SIDECAR` and
  `SVF_MAKER_STAGED_REPO` pointing into the extraction); `wasm` (`cmp` of `resources/sidecar/.../_internal/static/wasm/svf.wasm`
  with a fresh `bash maker/build-wasm.sh` output); `licences` (re-run the generator over the extracted tree: exit 0,
  no `gpl`); `smoke` (`xvfb-run -a <extract>/squashfs-root/AppRun` with `SVF_MAKER_SMOKE=1`,
  `SVF_MAKER_SHELL_LOG=stderr`, a temp `--user-data-dir`: stdout has `svf-maker smoke ok SVF maker`, exit 0 within
  60 s, stderr has `sidecar start mode=packaged` and `sidecar exit code=0`, then `pgrep -f svf-maker-sidecar` empty);
  `sources` (`--release` only: `desktop/build/out/sources/MANIFEST` covers every `lgpl` component; without
  `--release` it prints `CHECK sources skipped (private build; D8 release gate)`); `contents` (writes
  `desktop/build/out/release-<BUILD_ID first word>.txt`: file list with sizes of the extraction, the Debian-Pillow
  comparison line of the frozen test, the sandbox line of the smoke run).

- [ ] **Step 1: Write** `release-check.sh` first and run it against a missing file: `bash
  desktop/build/release-check.sh /nonexistent.AppImage`. Expected: `CHECK size FAIL ...`, exit 1.
- [ ] **Step 2: Write** the `"build"` block and `build-appimage.sh`.
- [ ] **Step 3: Run** `~/.local/bin/heavy bash desktop/build/build-appimage.sh` (announce; no other Chrome).
  Expected: every `CHECK ... ok`, `sources skipped`; the AppImage around 151 MB; exit 0.
- [ ] **Step 4: Record** in the commit body: AppImage size, `linux-unpacked` size, build seconds, the `CHECK` lines,
  the smoke's sandbox line.
- [ ] **Step 5: Gates** G1, G4 (G2 unchanged).
- [ ] **Step 6: Commit** `git add desktop/package.json desktop/build/build-appimage.sh desktop/build/release-check.sh
  && git commit -m "desktop: AppImage through electron-builder with a release check (extract, frozen test, wasm cmp, licences, smoke via AppRun, size budget) (t_e64a56a7)"`.

Cannot verify here: a FUSE-mounted AppImage start (no FUSE: the check runs the extracted `AppRun`); a sandboxed
renderer on a userns-capable system (here `AppRun` adds `--no-sandbox`); glibc < 2.39; `SOURCE_DATE_EPOCH`
determinism; `electronLanguages` pruning (not used). How it degrades: `--appimage-extract` + `xvfb-run AppRun`, the
frozen test against the extracted sidecar, and a recorded sandbox state.

### Task 9: documents and closing gates (slice S5)

**Files:**
- Create: `docs/maker-desktop.md`
- Modify: `maker/README.md` ("Desktop app" section, spec 13), `NOTICE.md` (spec 13 sentence), `docs/maker-audit.md`
  (section 9: the two cards' closing evidence), `docs/STATUS.md`, `maker/test/test_server.py`
  (`test_readme_and_notice_wording`)

- [ ] **Step 1: Extend** `test_readme_and_notice_wording`: `maker/README.md` contains "## Desktop app",
  "run-tool", "SVF_RECOG_PYTHON", "JAMOSET_PYLIB", "~/.config/svf-maker/maker", "makes no network connection", "not
  built or verified" (Windows/macOS); `NOTICE.md` contains "THIRD-PARTY.txt" and "It contains no font that is not in
  `svf/`." Run it: FAIL.
- [ ] **Step 2: Write** `docs/maker-desktop.md`: prerequisites and the build command sequence with the versions last
  used (emsdk/emcc 6.0.13, Python 3.12.3, PyInstaller 6.22.3, Pillow 10.2.0, fontTools 4.66.1, node, npm, Electron
  45.2.3, electron-builder 26.18.0); the measured numbers from Tasks 4 and 8; the sandbox state per system (D7 per
  section 17, D13 `.deb` later) and the `--no-sandbox` facts; the glibc floor (D9); the manual checks a human runs
  with a real desktop (native dialogs, FUSE start, "open folder" in a file manager); the LGPL release gate and how to
  fill `desktop/build/out/sources/MANIFEST` (D8); **"Windows and macOS (UNVERIFIED)"** with spec 8.11 verbatim and the
  Windows server-port blockers; the not-verified list of spec 10.4. Then the README, NOTICE, audit and STATUS edits.
- [ ] **Step 3: Run the closing gates** and record each in the commit body:
  - G1; G2 (expected the Task 4 count + 0); G3; G4.
  - `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_*.py'`.
  - `~/.local/bin/heavy make -C c check`.
  - `python3 maker/test/smoke_dom.py`.
  - `git diff --exit-code 94011ff -- tools maker/static c/src c/include` -> exit 0.
  - `~/.local/bin/heavy bash desktop/build/build-appimage.sh` (fresh) -> every `CHECK ok`.
- [ ] **Step 4: Commit** `git add docs/maker-desktop.md maker/README.md NOTICE.md docs/maker-audit.md docs/STATUS.md
  maker/test/test_server.py && git commit -m "docs: desktop app build, sandbox state, release gate, Windows/macOS UNVERIFIED steps; audit section 9 (t_f04f1355, t_e64a56a7)"`.

**Group D review gate.** The reviewer runs Step 3's list and checks each closing measurement:
- The shell opens the app on Linux, picks files/folders through the bridge, converts a sample into an output folder
  and quits cleanly with no orphan: `e2e.js` (`bridge`, `flow`, `open-folder`) and `lifecycle.test.js` (Task 6);
  the release check's `smoke` (Task 8).
- A frozen sidecar converts the OFL sample set byte-identically to source mode in a clean environment without python
  on PATH: `FrozenByteEqualTest` and `test_frozen_jobs_byte_equal` under `PATH=<empty dir>` (Task 4), again on the
  extracted AppImage (Task 8 `frozen`).
- An AppImage builds with a local script and runs (extracted `AppRun`, no FUSE here): `build-appimage.sh` (Task 8).
- THIRD-PARTY generation: Task 7 tests and the `licences` check (Task 8). The reviewer opens THIRD-PARTY.txt against
  `ls resources/sidecar/svf-maker-sidecar/_internal/*.so*` and the map.
- Windows/macOS steps documented as UNVERIFIED: `docs/maker-desktop.md` (Task 9).

---

## Review groups

| Group | Tasks | Order and parallelism | Review |
|---|---|---|---|
| A launcher (S1) | 1, 2 | 1 -> 2 (both `jobs.py`) | after 2: every argv prefix before/after; `/api/caps` keys |
| B sidecar (S2) | 3, 4 | after A; 3 -> 4 (`server.py`, `jobs.py`, `preview.py`, `localfx.py`) | after 4: the reviewer builds and runs the frozen test; no `run-tool` process left |
| C shell (S3) | 5, 6 | 5 developed in its own worktree after A, alongside B, lands after 3; 6 starts after 5 and 3, lands after 4 | after 6: `run-e2e.sh` both passes, `node --test`, `shell.log` read |
| D packaging + docs (S4, S5) | 7, 8, 9 | after B and C; 7 -> 8 -> 9 | after 9: the closing measurements |

Landing order: 1, 2, 3, 5, 4, 6, 7, 8, 9 (5 may land before or after 4: disjoint files). G2 counts assume it; a task
landing in another order states its observed count. Only one full G2 / e2e / AppImage build runs at a time on this
host (one Chrome), announced to the controller.

## Design issues found while planning

1. **johab844 positions (7.2/7.3 vs the code).** Spec 7.3 says the johab844 test becomes "`rest[0]`'s name after
   `split_prefix`" and `_johab844_comment` reads the base from "`rest[2]`". After `split_prefix`, `rest` is `[src,
   base, out]` (`routes.py:196`): `rest[0]` is the input font and `rest[2]` the output. The plan detects johab844 by
   `toolrun.prefix_name(prefix) == "johab844"` (the frozen token is `johab844`, not `johab844.py`) and reads the base
   from `rest[1]` (Task 1).
2. **`split_prefix` raises, but `note_prefix` is applied to every argv.** Test steps run `[python, "-c", ...]` argvs
   through `log_step` and notes (`test_jobs.py:291` and others); a raising `note_prefix` would break them. The plan's
   `note_prefix` passes an unrecognised argv through unchanged; `split_prefix` keeps raising for the positional
   consumers (`probe_argv`) where a wrong shape is a bug (Task 1).
3. **The recogniser stub of 10.2/7.7 cannot pass the 7.7 probe.** The test is to use "the host's `python3` plus a stub
   `recog.py`", but the probe imports `numpy, torch, PIL, fontTools` and this host has no numpy/torch, so `recog` would
   stay false. The plan uses a shell stub interpreter that exits 0 for the probe and execs `python3` otherwise (Task 4).
4. **`/api/caps` would leak the private keys as booleans.** `Handler._caps` serves `{key: bool(value)}` for **every**
   key of `server.caps` (`server.py:1772`), so adding `recog_python` (7.7) adds `"recog_python": true` to the API. The
   plan filters to `caps.PUBLIC_KEYS` in `server.py` in Task 2 - a one-line `server.py` edit in S1, although spec 11
   gives `server.py` to S2 only (harmless: S1 and S2 are serial). Spec 7.3 also names `toolrun.recog_argv(self.caps)`
   while 7.7 says `recog_argv(caps, repo_dir)`; the plan uses the latter, and `compute` keeps `recog_dir` too, since
   `_identity` needs it for `SVF_RECOG_DIR` once the per-step `caps.recog_dir` call is gone.
5. **`make_server`'s order (section 4).** Section 4 says start-up cleanup, then `recover`, then bind; the code runs
   `recover`, `start`, bind, then `startup_cleanup` (`server.py:479-530`). The reap of 7.10 must precede both
   `recover` and the cleanup; the plan places it right after `jobs.Store(...)`, before `caps.compute` (Task 3).
6. **PDEATHSIG bypasses the stdio detach.** 7.9 detaches fds 1-2 in the polling thread before it signals itself, but
   the Linux `PR_SET_PDEATHSIG(SIGTERM)` it also installs delivers SIGTERM straight to the `terminate` handler, with
   stdout/stderr still leading to the dead shell. The plan makes `terminate` detach stdio when the expected parent is
   gone, and tests both paths (Task 3). Related: `PR_SET_PDEATHSIG` fires when the **thread** that forked the child
   exits; the runners block on their child in the forking thread, so this holds today - a future runner that hands a
   child to another thread would break layer 2.
7. **The runners have no data root.** 7.10 puts the registry at `<data_root>/tools.pids` and the writes in
   `jobs.run_command`/`preview.run_bounded`, which are module functions with no data root in scope. The plan adds
   `toolreg.configure(data_root)` called by `make_server`; unconfigured (unit tests calling the runners directly) the
   registry is a no-op (Task 3).
8. **The static no-outbound scan vs the main-process request.** 6.9's test fails on `fetch` "with an absolute URL",
   while 6.5 makes the main process `GET /api/jobs/<id>` itself. The plan's scan forbids `http`/`https`/`net` modules
   and `fetch` with a literal `http...` first argument; the one main-process `fetch` builds its URL from
   `sidecar.origin` (Task 5).
9. **Where the version lives.** 8.8 has `build-sidecar.sh` write a `maker/VERSION` file (a generated file in a
   tracked directory). The plan keeps `VERSION = "0.1.0"` in `maker/sidecar.py` and a unit test pins it equal to
   `desktop/package.json` (Tasks 4, 6). Similarly 8.3 has the build script "create a venv"; venv does not work here,
   so the plan uses `pip --target` + `python3 -S` (allowed by section 12), which also serves as the 8.10 reference.
10. **`.mjs` names vs a sandboxed CJS preload.** 6.1/10.3 name `desktop/lib/*.mjs` and `unit.test.mjs`; section 12
    leaves ESM/CJS to the builder and the preload must be CJS. The plan uses CommonJS `.js` throughout (Task 5).
11. **Lifecycle cases cannot run inside the e2e's own main process.** 10.3 lists "closing the window", "SIGTERM to the
    main process" and "SIGKILL of the main process" in the one Electron e2e, which ends the process that asserts. The
    plan moves them to `lifecycle.test.js`, a node test that launches the shell under `xvfb-run` and reads its log
    (Task 6), and adds `SVF_MAKER_SMOKE=1` (also the AppImage smoke of Task 8).
12. **Suite counts.** Sections 2 and 10.1 say "909 tests at `1513dd2`" and "909 tests OK at `94011ff`"; at `94011ff`
    the count is 914 (14 skipped). The plan uses 914.
13. **The import-graph oracle grows.** 7.1/10.1 pin "28 modules today"; `toolrun` (Task 1), `toolreg` (Task 3) and
    `sidecar` (Task 4) join the reachable set. The plan pins the set per task and, from Task 4, takes the roots as
    `["sidecar"]` with `sidecar.GRAPH_MODULES` as the list `selfcheck` imports.
14. **The handshake budget and the reap.** `HANDSHAKE_S = 75` is derived as 30 + 20 + 25 margin (6.2), but the reap
    of 7.10 (`REAP_TOTAL_S` 10 s) also runs before the port line. 75 still covers 30 + 20 + 10; the plan keeps 75 and
    asserts `HANDSHAKE_S >= startup + probe + reap` (Task 5).
15. **D7 in section 15 vs section 17.** Section 15 says "no `--no-sandbox` by default"; section 17 ships `AppRun`
    unchanged (which adds it when user namespaces are unavailable). The plan follows 17 and the release check asserts
    `AppRun` is unchanged (Task 8).
16. **The source archive (8.10) vs the D8 ruling (17).** 8.10 has the release archive the LGPL sources next to the
    AppImage; 17 makes it a release gate for a private bundle. The plan's check skips it without `--release` and
    enforces it with `--release` (Tasks 7, 8).
