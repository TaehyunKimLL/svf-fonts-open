# Maker local-only mode for proprietary inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The SVF maker gets a local mode, switched on by a per-launch token. In that mode it reads inputs the user
picked by path and writes faces, notes and the build record only into an output folder the user picked. Nothing is
uploaded or copied into the data directory, no zip is made, and the only network traffic is to 127.0.0.1. The Mac
HangulTalk `fbit` fonts (both generations) and the HWP-derived inputs are accepted in this mode only. Card t_cbd14d61.

**Architecture:** Five layers, in this order. (1) Hardening that needs no local job: the token, the loopback-only
bind, `no-store`, the CSP and `caps.local` (S2). (2) The `Sources` object replaces the `upload_dir` string. It is
threaded through detect, settings, jobs, zipout and server for upload jobs, with no change in behaviour (S1). (3) The
local job: path rules, the files directory under the output folder, the scan over roots, the run that writes a folder
tree, and the sweeps (S3). (4) The page's sources panel (S4) and the Mac kinds (S5), which run in parallel. (5) The HWP
lines and the documents (S6), the network proofs (S7), and closing.

**Tech Stack:** Python 3 stdlib, fontTools, Pillow, unittest. node 22 and `google-chrome` for the page and DOM tests
(`maker/test/pagedrive.mjs`, no playwright). No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-04-maker-local-mode-design.md` at `fa0c087`: sections 6-13, the rulings
(the first "16"), the changes list (the second "16") and the review dispositions (17). Section numbers below ("7.1",
"9.2") are the spec's. All commands run from the worktree root `~/work/svf-fonts-open-wt/maker-local` (branch
`maker-local`, base `ce976f8`). No push.

**Rulings (controller, spec section 16):** D1 server mode, no CLI. D2 the presence of the token is the single switch.
D3 intermediates go under `<output_dir>/.svf-maker-<id>/` and are swept. D4 full paths in `log.md`/`BUILD.md`,
basenames in notes. D5 `report.json`/`identity.json` are kept in the metadata directory. D6 collision rule as stated.
D7 a prefilled "proprietary, own use" text licence. D8 archives are listed, not unpacked. D9 no HWP Hangul `.PFT`
reader. D10 uploads stay available. D11 macOS named forks as an optional, env-gated commit (Task 13). D12 a
non-loopback bind is refused only with the token. D13 no zip for local jobs. D14 all three Mac 7.1 routes. D15 the
12x24 `ASCII.PFT` companion from anywhere in the batch. These stand. Where this plan has to choose inside a ruling, it
says so, and the choice is listed again under "Design issues found while planning".

## Global Constraints

- **`c/src` and `c/include` are unchanged.** Gate G1 runs at the end of every task.
- **Gates run at the end of every task** (before its commit), in this order:
  - G1 `git diff --exit-code ce976f8 -- c/src c/include` -> exit 0, no output.
  - G2 `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'` -> `OK` (skips allowed) and
    `Ran N tests`, where N is the count the task states. The suite is 682 tests at `ce976f8`
    ("Ran 682 tests ... OK (skipped=10)") and stays green at every task. A stated count is a plan estimate. If the
    observed N differs, the implementer writes the observed N and the reason in the commit body.
  - G3 `python3 -m unittest discover -s maker/test -p 'test_server.py' -k test_page_js_tables_match_python` -> `OK`.
- **Drift tables move together.** A change to `routes.routes`, `presets.panel_argv`, `presets.ALL_SOURCES`,
  `settings._SOURCE_WORDS`/`_SOURCE_ARTICLES` or the literals of `server.Handler._make_source_preview` ships its
  `maker.js` rows (`ROUTES`, `OPTION_VISIBLE`, `PREVIEW_KINDS`, `SOURCE_WORDS`, `SOURCE_ARTICLES`, `LAYOUTS`) and the
  drift test's `TOOL_OF_LABEL`/`canonical_fonts()` in the **same commit**.
- **No proprietary data.** Every fixture is synthetic and built inside the test (`maker/test/inputfx.py`, the new
  `maker/test/macfx.py`, `tools/test_macfbit3.py`, `tools/test_macfbit_svf.py`). Real-file tests are gated by
  environment variables and skip with a message that names the variable. No golden file from a real font enters the
  repository.
- **Long runs go through the OOM guard:** the full maker suite, `tools/test_macfbit3.py`, `tools/test_macfbit_svf.py`,
  `tools/test_jamoset.py` and `make -C c check` run under `~/.local/bin/heavy`.
- **No bare `git stash`.** Set work aside with a WIP commit on the branch.
- **Tools unchanged.** No file under `tools/` changes. The new `srcprep.py` subcommands call the tools' library
  functions.
- **Upload jobs behave exactly as before.** Every test that exists at `ce976f8` passes unmodified. The exceptions are
  the Step-shape literals that gain `"needs"` (Task 7) and the assertions this plan rewrites by name.
- **Serialization.** No two tasks edit `maker/settings.py`, `maker/detect.py`, `maker/jobs.py` or `maker/server.py`
  at the same time. Tasks that share any file run in plan order. "Review groups" names the parallel windows.
- **Commits** end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and name the card
  `(t_cbd14d61)` in the subject.

## Licence ruling (user, 2026-11-04; amends this plan, wins over everything below it)

Font licences matter only when WE publish (upload to GitHub and the like). Converting a font in the maker is the
user's own responsibility. The maker does not police licences; it shows one acknowledgement and records what the user
chose.

- **No licence is required to convert in local mode.** A selected font with no licence file runs. `check_face`,
  `_licence_present_ok`, `_clash_errors` (licence part) and `_text_entry` never block a **local** job for a missing
  licence, and `settings.run_ready` adds no "needs a licence" error for it. **Upload jobs behave exactly as before**:
  this card changes no upload behaviour (the switch is `Sources.kind == "local"` / `job["source"] == "local"`).
- **Optional licence selection.** When the user picks a licence (an `upload` licence file, a `repo` file or a `text`),
  it is copied into the output notes as today (`LICENCE` text file, `LICENCES.tsv.lines`). When none is given, the
  notes and `BUILD.md` say `licence: not checked (user's responsibility)` and no licence text file is written.
- **Dropped:** the prefilled "proprietary, own use" text licence (**D7**) and `settings.defaults(local=True)`'s default
  licence. A local font's default `licence` is `{"kind": "upload", "root": r, "path": p}` only when the scan found a
  licence file the user picked, else `None`. Sibling-licence pairing for file roots is no longer a requirement (the
  Task 2 behaviour stays because it is trivial and green; it is never relied on).
- **Acknowledgement popup (page, Task 9).** The first time a local job is created in a page session, a modal shows:
  "You are responsible for having the right to convert the fonts you choose. Converted faces are written only to your
  chosen output folder. If you publish them, check each font's licence." with an OK button. The acknowledgement is
  remembered for the page session (and the launch), not on the server. The CDP harness test: the popup shows on the
  first local job, and does not show again after OK.
- **README and NOTICE** keep "no proprietary font is distributed" and gain one sentence: converting a font you do not
  own the rights to is your own responsibility; if you publish the result, check the font's licence.

**Superseded by this ruling** (the text below stays for history; implement the ruling instead):
D7 (Rulings paragraph); the file-map settings row's "default text licence (6)"; Task 2's file-root licence pairing text
and `test_file_roots_in_one_folder_pair_up` (kept: trivial and green); Task 5's licence fallback to the "fresh default"
(now `None` for a local font without a picked licence) and Task 6's `local=True` default-licence case in
`test_kept_settings_by_root_path_for_local`; Task 6's "Produces (`settings.defaults(fonts, local=False, today=None)`)"
block and `test_local_default_text_licence` (replaced by `test_local_no_default_licence`: no licence is selected for
a font without one, and such a font runs); Task 7's `own_earlier` exemptions for `_licence_present_ok` /
`_clash_errors` / `_text_entry` apply to faces and notes only (a missing licence is never an error in a local job);
design issues 6 and 15; review dispositions "SOL b" and "Opus m2"'s `first_line` clause (the `first_line` metadata
stays only because it is trivial).

## Review Focus

1. **Privacy leaks: an input's bytes reach `job.json`, the API, a note or the data directory by an indirect road.**
   The roads are an exception message in a label (`UnicodeDecodeError` quotes the byte), a traceback in
   `GET /api/jobs/<id>`, a note command line with a home directory, a `.gz` decompressed into `/tmp`, and a Python
   bytecode cache written beside the tools. Pinned by `test_unreadable_label_names_the_type_only` (Task 6),
   `test_notes_and_logs` (Task 7), `test_scan_temp_copies_stay_in_tmp_dir` (Task 6),
   `test_run_env_has_tmpdir_and_no_bytecode` (Task 7), and `test_no_upload_copy` / `test_no_write_outside_output`
   (Task 8).
2. **Path rules: an overlap spelled through a symlinked parent.** An example: the source `/t/in` with the output
   `/t/alias/in/out`, where `/t/alias -> /t`. The last component is not a link, but `realpath` lands inside the
   source. The overlap must be refused by inode, not slipped past a string check. Pinned by
   `test_path_rules_overlap_by_inode` (Task 6).
3. **Collisions: a re-run replaces a file the job no longer owns.** Job A wrote `svf/dos/X.SVF`. The user deleted
   it, and job B wrote another `X.SVF`. A re-run of A must refuse with a name clash, not replace B's file. The same
   goes for a re-run after a run that found the face identical. Pinned by
   `test_own_earlier_replaced_only_when_unchanged`, `test_rerun_after_identical_keeps_ownership` and
   `test_detect_keeps_owned` (Task 7). Ownership lives in the top-level `job["owned"]`, which `POST detect` and
   `POST run` never reset (Tasks 6, 7). See design issues 5 and 16.
4. **Token: a token that does not come in the one header.** Cases: a second `X-Maker-Token` header, a non-ASCII
   value, `?token=` in the URL, a 404 route that would leak whether a job id exists. Each must be 403 before
   routing. Pinned by `test_token_compare_is_bytes` and `test_token_check_runs_before_routing` (Task 1).
5. **Drift tables: a table the drift test does not compare.** `maker.js` `LAYOUTS` is a fixed list. A Mac route
   whose layout is missing from it would make the page's per-font layout select reset the layout. Pinned by
   `test_page_layouts_cover_route_layouts` (Task 11), next to the extended `test_page_js_tables_match_python`.

## Verified while planning (this host, `fa0c087`)

- `grep -n 'upload_dir\|job_dir\|store.path(' maker/*.py` finds 175 hits: server 61, jobs 50, settings 40, zipout 14,
  detect 10. The full list with each hit's new form is under Task 2-5's "S1 hit list".
- `def test_` counts sum to 682. `~/.local/bin/heavy` exists. `index.html` has no inline `style=` attribute.
- No `maker/*.py` or `tools/*.py` imports `socket`, `ssl`, `smtplib`, `ftplib`, `xmlrpc`, `requests`, `http.client`,
  `urllib.request` or `asyncio`, except `maker/server.py` (`socket`).
- `detect.scan` gives `eng` companions to `dos-raw` entries only (`detect.py:1368-1376`). `bdf-johab` and
  `svf-*` entries always get `companions = []`.
- `tools/test_macfbit_svf.synthetic(seed)` returns an HTBL of 4 + 204 + 4 + 9,400 = **9,612** bytes. Its second
  length word is `len(t2)` and there is no trailing copy. `tools/test_macfbit3.make_htbl` makes the **9,816**-byte
  form (`0x2468`, trailing copy). `macfbit_svf.Htbl1` reads both (`t2 = data[8 + l1:]`).
- `naming.suggest_face_name("Munjo24", 24, 1, "jamo")` is `"MUNJ24J.SVF"` (abbr `MUNJO`, first 4 for a jamo set).
- `routes.route_for` picks the first native route of a kind, and `settings._route_errors` checks a jamo layout
  against `route.layouts` for every kind but `dos-raw` (`settings.py:911`). `maker.js` `LAYOUTS` is
  `["844", "adaptive", "hanterm-johab"]` and no test compares it.
- `jamoset.MacFbit` needs a **resource fork** holding both `fbit` and `fdef` 3. A raw `fbit` resource alone cannot be
  read (`jamoset.py:2563`).
- `preview.run_bounded(argv, cwd, timeout, env=None)` and `jobs.run_command(argv, cwd, timeout, cancel, env=None)`
  already take an `env`.
- `pagedrive.mjs` takes `CHROME URL SCRIPT_FILE` positionally.

Not verified (the named tests or gates verify them): the HangulTalk 1.0 synthetic font passing `jamoset --check`
(Task 12 says what happens if it cannot), and the real 7.1.2 HTBL size (`SVF_MAKER_REAL_MAC3`, Task 15).

## File map

| File | Status | Responsibility (task) |
|---|---|---|
| `maker/server.py` | modify | token, loopback, CSP, no-store, caps (1); `Sources`/files dir in every handler (5); local job endpoints, path checks (6); run/tree, note check (7); sweeps, serving from the output (8); Mac preview kinds, prepared-source ext table (11, 12) |
| `maker/caps.py` | modify | `local` (1) |
| `maker/sources.py` | create | `Sources`, path rules, inode overlap (2, 6) |
| `maker/detect.py` | modify | scan over `Sources` (2); local labels, `tmp_dir`, archive label (6); Mac sniff tags and rows (11, 12, 13); `hwp-pft`, the 12x24 rule (14) |
| `maker/settings.py` | modify | `Sources` and roots (3); default text licence (6); `own_earlier` in `run_ready` (7); `htbl_companion`, Mac words, companion source steps, `needs` planning (11); 1.0 ascent cell (12) |
| `maker/jobs.py` | modify | `Store.files_dir`/`sources` and the worker (4); `Store.create(local)` (6); `needs` cascade, `write_tree`, env (7); sweeps, `steps/` reports, recover/stop/retain (8) |
| `maker/zipout.py` | modify | `files_dir`/`sources` (4); `collect`/`write_zip`/`write_tree`, notes without absolute paths (7) |
| `maker/preview.py` | modify | `env` with `TMPDIR` passed through (6); Mac bakes (11, 12) |
| `maker/srcprep.py` | modify | `mac-fork`, `mac-htbl`, `_apply_op` (10); `mac-fork-named` (13) |
| `maker/routes.py` | modify | Mac source ops, `OP_EXT`, four Mac routes (11, 12) |
| `maker/presets.py` | modify | `ALL_SOURCES`, `panel_argv` Mac branches (11, 12) |
| `maker/static/maker.js`, `index.html` | modify | Mac tables and the HTBL select (11, 12); sources panel, bridge, open folder (9) |
| `maker/test/pagedrive.mjs` | modify | `--header NAME:VALUE` (9) |
| `maker/test/macfx.py` | create | synthetic Mac fixtures (10, 12) |
| `maker/test/localfx.py` | create | `local_tree`, `read_only`, `LocalServer` test base (6) |
| `maker/test/test_sources.py`, `test_local.py`, `test_macfx.py` | create | (2), (6-8, 15), (10) |
| `maker/test/test_server.py`, `test_detect_inputs.py`, `test_settings.py`, `test_routes.py`, `test_srcprep.py`, `test_plan_inputs.py`, `test_jobs.py`, `test_zipout.py`, `test_page_dom.py`, `test_real_inputs.py`, `test_server_signals.py` | modify | per task |
| `maker/README.md`, `NOTICE.md`, `docs/recipes.md`, `docs/maker-audit.md` | modify | (1 token lines), (14), (16) |

---

# Group A: hardening and the `Sources` refactor

Task 1 (S2) runs alongside the chain 2 -> 3 -> 4, which touches disjoint files. Task 5 starts after Task 1 and
Task 4 have both landed, so only one commit to `server.py` is in flight at a time. **Every parallel lane has its own
worktree** (one for Task 1, one for the chain 2-4), rebased onto the branch before it lands. G2 in a shared tree would
run over the other lane's half-made edits. Land order: Task 1, then 2, 3, 4 (rebased), then 5.

### Task 1: token, loopback bind, `no-store`, CSP, `caps.local` (slice S2)

**Files:**
- Modify: `maker/server.py`, `maker/caps.py`, `maker/README.md` (a "Token and loopback" paragraph: what
  `SVF_MAKER_TOKEN` does, the loopback rule, `X-Maker-Token`), `maker/test/test_server.py`

**Interfaces:**
- Produces:
  - `make_server(host, port, repo_dir, data_root, token=None)`. With a token: `ValueError("local mode binds
    127.0.0.1 or ::1 only")` raised **first**, before the store, `worker.recover()`, `worker.start()` and the socket
    (no worker thread leaks), unless `_is_loopback(host)`. Sets `server.token` (bytes or None) and
    `server.caps["local"] = token is not None`.
  - `_is_loopback(host: str) -> bool`. True for `ipaddress.ip_address(host).is_loopback` after the bracket strip.
    For `localhost`, true only when every address `socket.getaddrinfo(host, None)` returns is loopback. Any other
    name is False.
  - `_parse_token(value: str | None) -> bytes | None`. `None`/`""` gives None. Otherwise it must match
    `\A[0-9a-f]{32}\Z` (lower-case hex, 16 bytes), else `ValueError("SVF_MAKER_TOKEN: 32 hex characters")`. Returns
    `value.encode("ascii")`.
  - `main()` reads `SVF_MAKER_TOKEN` through `_parse_token`. A `ValueError` from it or from `make_server` prints the
    message to stderr and exits 2. The token is never printed.
  - `caps.compute(static_dir, environ, local=False)` -> adds `"local": bool`.
  - `Handler._check_token()`. With `server.token` set and the path under `/api/`, it requires exactly one
    `X-Maker-Token` header (`self.headers.get_all`). It compares `value.encode("latin-1")` with `server.token` using
    `hmac.compare_digest`, and any exception is a refusal. A refusal is 403 `"missing or wrong token"`.
  - `Handler._handle` order with a token: `_check_same_origin()` for **every** request (the `Host` check covers `/`,
    `/static/*` and every route), then `_check_token()`, then route matching. Without a token, the order and scope are
    today's.
  - `Handler._serve_bytes(path, content_type, no_store=False)`. With `no_store`, the header is
    `Cache-Control: no-store` (the `ETag` stays). `Handler._no_store(job: dict) -> bool` is
    `job.get("source") == "local"`. `_job_face`, `_job_source_face`, `_job_report`, `_job_identity` and `_job_probe`
    `.svf` pass it to `_serve_bytes`. The probe `.json` goes out through `_send(...)` (`server.py:1073`), so it gets
    its own branch: `{"Cache-Control": "no-store" if no_store else "no-cache"}`. `_job_preview` sends `.png` with
    `_serve_file(..., extra={"Cache-Control": "no-store"})` when `_no_store(job)`. For an upload job, `_job_preview`
    keeps sending no `Cache-Control` (see design issue 4).
  - `CSP = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; img-src 'self' blob:
    data:; font-src 'self'; style-src 'self'"`. `_static` sends it as `Content-Security-Policy` on every static
    answer, token or not.

- [ ] **Step 1: Write the failing tests** in `test_server.py`, in a new `class LocalBindTest(unittest.TestCase)` with
  `TOKEN = "0123456789abcdef0123456789abcdef"`, a temp data root, and two helpers of its own (it is not an
  `ApiBase`): `start(self, host="127.0.0.1", token=TOKEN) -> server` returns a started server (stopped in
  `tearDown`), and `raw(self, srv, method, path, body=None, headers=None) -> Reply` sends to `srv.port` the way
  `ApiBase.raw` does. `setUp` saves `os.umask` and `tearDown` restores it (the token makes `make_server` set
  `0o077`, Task 6):

```python
def test_non_loopback_host_is_refused_with_the_token(self):
    for host in ("0.0.0.0", "192.0.2.1", "example.org"):
        with self.assertRaisesRegex(ValueError, r"local mode binds 127\.0\.0\.1 or ::1 only"):
            server.make_server(host, 0, fixtures.REPO_DIR, self.data, token=self.TOKEN)

def test_loopback_hosts_bind(self):
    srv = self.start("127.0.0.1"); self.assertEqual(srv.socket.getsockname()[0], "127.0.0.1")
    # ::1 the way ApiTest's IPv6 test does (skipped when the host has no IPv6 loopback)

def test_localhost_needs_every_address_loopback(self):
    with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0)), (2, 1, 6, "", ("192.0.2.1", 0))]):
        self.assertFalse(server._is_loopback("localhost"))
    with mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0)), (10, 1, 6, "", ("::1", 0, 0, 0))]):
        self.assertTrue(server._is_loopback("localhost"))

def test_token_on_every_api_request(self):
    srv = self.start()
    for method, path in (("GET", "/api/jobs"), ("GET", "/api/caps"), ("GET", "/api/jobs/0123456789ab/face/s01.svf"),
                         ("POST", "/api/jobs"), ("GET", "/api/no-such-route")):
        r = self.raw(srv, method, path)
        self.assertEqual((r.status, json.loads(r.read())["error"]), (403, "missing or wrong token"), path)
    self.assertEqual(self.raw(srv, "GET", "/").status, 200)
    self.assertEqual(self.raw(srv, "GET", "/static/maker.js").status, 200)
    self.assertEqual(self.raw(srv, "GET", "/api/jobs", headers={"X-Maker-Token": self.TOKEN}).status, 200)

def test_token_compare_is_bytes(self):
    srv = self.start()
    # a latin-1 header value of 32 non-ASCII characters: 403, never 500
    # two X-Maker-Token headers (the right one first, a wrong one second): 403
    # GET /api/jobs?token=<TOKEN> with no header: 403

def test_token_check_runs_before_routing(self):
    srv = self.start()   # no header: an existing job id and a made-up one answer the same 403 body
    jid = self.raw(srv, "POST", "/api/jobs", headers={"X-Maker-Token": self.TOKEN})...  # id
    a = self.raw(srv, "GET", "/api/jobs/%s" % jid); b = self.raw(srv, "GET", "/api/jobs/000000000000")
    self.assertEqual((a.status, a.read()), (b.status, b.read()))

def test_bad_host_403_on_every_route(self):
    srv = self.start()
    for method, path in (("GET", "/"), ("GET", "/static/maker.js"), ("GET", "/api/jobs"), ("GET", "/api/caps"),
                         ("POST", "/api/jobs")):
        r = self.raw(srv, method, path, headers={"Host": "evil.example", "X-Maker-Token": self.TOKEN})
        self.assertEqual(r.status, 403, path)

def test_caps_local(self):
    srv = self.start()
    self.assertIs(json.loads(self.raw(srv, "GET", "/api/caps", headers={"X-Maker-Token": self.TOKEN}).read())["local"], True)
    # and in ApiTest (no token): GET /api/caps -> "local": False

def test_main_refuses_a_bad_token_or_bind(self):
    # python3 -P maker/server.py with SVF_MAKER_TOKEN=xyz, SVF_MAKER_BIND=127.0.0.1:0, SVF_MAKER_DATA=tmp:
    #   exit 2, stderr contains "SVF_MAKER_TOKEN: 32 hex characters", stdout has no "listening"
    # the good token and SVF_MAKER_BIND=0.0.0.0:0: exit 2, stderr contains "local mode binds 127.0.0.1 or ::1 only"
```

  In `ApiTest`:

```python
def test_csp_and_static_urls(self):
    for path in ("/", "/static/maker.js"):
        self.assertEqual(self.raw("GET", path).getheader("Content-Security-Policy"), server.CSP)
    # every file under maker/static/ except wasm/: after stripping /* */ and // comments (JS/CSS) and <!-- --> (HTML),
    # no match of r"https?://" and no match of r"""(?<![:\w])//[A-Za-z0-9.-]+\.[A-Za-z]{2,}""" (a protocol-relative URL)

def test_no_store_follows_the_predicate(self):
    jid = self.minimal_job(); job = self.run_to_done(jid)
    # GET face (first done step), report, probe .json and .svf (size/bpp of the step), preview/<fid>/source.png:
    #   collect the Cache-Control of each 200 answer: each is "no-cache" (the png: None)
    with mock.patch.object(server.Handler, "_no_store", lambda self, job: True):
        # the same GETs: each Cache-Control is "no-store"
```

  The job stays an upload job. Only the predicate is patched, so the test stays valid once Task 6 gives local jobs
  their own files directory. Task 8's `test_no_store_headers` proves the header on a real local job.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_server.py -k LocalBindTest -k test_csp -k no_store_follows -v`.
  Expected: FAIL (`make_server() got an unexpected keyword argument 'token'`, no CSP header).
- [ ] **Step 3: Implement** to the interface. `_HOST_CHECKED` stays for the no-token path. With a token, the `Host`
  check runs before `_route`.
- [ ] **Step 4: Run** the new tests, then `python3 -m unittest discover -s maker/test -p test_page_dom.py`. Expected:
  `OK`. With Chrome on this host, the page must still load and draw under the CSP. If a page test fails on the CSP,
  widen only `style-src` (the spec allows that) and say so in the commit body.
- [ ] **Step 5: Gates** G1, G2 (693), G3.
- [ ] **Step 6: Commit** `git add maker/server.py maker/caps.py maker/README.md maker/test/test_server.py && git commit -m "maker: per-launch token on every /api request, loopback-only bind with it, no-store for local bytes, CSP (t_cbd14d61)"`.

Cannot verify here: the Electron shell adding the header (it does not exist yet). The tests send the header
themselves, as the shell will.

### S1 hit list (the conversion Tasks 2-5 carry out)

Each hit of `grep -n 'upload_dir\|job_dir\|store.path(' maker/*.py` at `ce976f8` is in one of four classes:

- **M** is the metadata directory (`log.md`, `job.json`). It stays `store.path(job_id)` / `job_dir`.
- **F** is the files directory (`work/`, `out/` of an upload). It becomes `files_dir = store.files_dir(job)`, which
  is `job_dir` for an upload job.
- **U** is an input path. It becomes a `Sources` call, `sources = store.sources(job)` (or the `Sources.coerce`'d
  argument).
- **X** is an upload-only path (`PUT files`, unpack, zip). It stays as it is, and a local job never reaches it
  (Task 6 refuses `PUT files`, Task 8 makes `GET zip` 404).

For an upload job, every new form computes the same path as the old one. That is the "no behaviour change by
construction" of 8.1.

| File:lines | Function | Class | New form |
|---|---|---|---|
| detect 1196-1198 | `_rel(upload_dir, path)` | U | `_rel(root_abs, path)`, the same body, called per root |
| detect 1274-1275 | `scan(upload_dir)` | U | `scan(sources, local=False)`; `sources = Sources.coerce(sources)` |
| detect 1291, 1294 | the walk | U | `files, refused = sources.walk()`; a refused `symlink, skipped` becomes today's `other` entry |
| detect 1301 | `abs_of` dict | U | keyed by `(root, rel)` |
| detect 1322 | `licence_root` | U | per root: `sources.roots[i]` (a dir root) or its parent (a file root) is the ceiling of `_licence_folders`/`find_licences` |
| detect 1363 | `entry["licences"]` | U | `{"path": rel, "first_line": ...}` plus `"root": i` when `sources.kind == "local"` |
| settings 674, 712 | `_shape_errors`, the range `isfile` | U | param `sources`; `sources.abs_of(eff.get("range_root", 0), rng)` in a `try` (a `ValueError` is the existing "not an uploaded list" error) |
| settings 737, 739 | `_shape_errors`, the licence `getsize` | U | `sources.abs_of(licence.get("root", 0), licence["path"])` |
| settings 759, 794 | `_batch_shape_errors` | U | param `sources`; the batch `range_root` |
| settings 964, 972, 1009, 1020 | `validate(fonts, settings, upload_dir=None)` | U | `validate(fonts, settings, sources=None)`; coerced |
| settings 1029, 1033, 1034, 1057, 1058 | `_licence_sha` | U | param `sources`; `abs_path = sources.abs_of(root, path)` replaces the `realpath`/`startswith` pair (which `abs_of` performs) |
| settings 1075, 1095 | `_licence_present_ok` | U | param `sources` |
| settings 1098, 1132 | `_clash_errors` | U | param `sources` |
| settings 1141, 1144, 1149-1151 | `run_ready(fonts, settings, index, upload_dir)` | U | `run_ready(fonts, settings, index, sources, own_earlier=())` (the `own_earlier` keyword lands in Task 7); `TypeError("run_ready needs upload_dir")` is kept word for word for `None` |
| settings 1208, 1215 | `run_ready` body | U | pass `sources` |
| settings 1222, 1227 | `range_spec(eff, upload_dir)` | U | `range_spec(eff, sources)`; `("file", sources.abs_of(root, rng))`, or `("file", None)` when `abs_of` raises |
| settings 1250, 1251, 1256, 1257 | `_upload_path(fid, rel, upload_dir)` | U | `_upload_path(fid, rel, sources, root=0)` -> `sources.abs_of(root, rel)`; a `ValueError` becomes today's `"%s: %s is outside the upload"` |
| settings 1336, 1343 | `plan_steps(job, job_dir, tools_dir, upload_dir, pylib)` | F+U | `plan_steps(job, files_dir, tools_dir, sources, pylib=None)` (positional, so the existing callers' strings still work) |
| settings 1351 | `work_root` | F | `os.path.join(files_dir, "work")` |
| settings 1364 | `src` | U | `_upload_path(fid, font["path"], sources, font.get("root", 0))` |
| settings 1365, 1367 | the range check | U | `range_spec(eff, sources)`; `rabs is None` -> the existing `"range %s is not under the upload directory"` |
| settings 1393 | `companion_abs` | U | `_upload_path(fid, companion["path"], sources, companion.get("root", 0))` |
| settings 1437 | `paths["report"]` | F | `os.path.join(files_dir, report)` |
| jobs 238, 244, 247 | `materialized_argv(steps, upload_dir, work_dir)` | U | `materialized_argv(steps, sources, work_dir)`; `_materialized_token(token, sources, work_dir, font_id)` tests `sources.inside(token)` |
| jobs 546 | `_log_failure` | M | unchanged |
| jobs 561, 569 | `run_job` | M | `job_dir` stays; adds `files_dir = store.files_dir(job)`, `sources = store.sources(job)`; `_run_steps(job, job_dir, files_dir, sources, cancel)` |
| jobs 571 | `_job_failed` | M | unchanged |
| jobs 573, 575 | `_run_steps`, the log header | M | signature as above |
| jobs 578, 582 | `upload_dir`, `gz_upload` | U | removed; `gz_upload[os.path.realpath(sources.abs_of(font.get("root", 0), font["path"]))] = font` |
| jobs 591, 597, 604, 609 | `_fail_steps`/`_fail_step` | M | unchanged |
| jobs 600 | `_run_step(...)` | F+U | `_run_step(job, job_dir, files_dir, sources, gz_upload, plain, fonts_by_id, step, cancel)` |
| jobs 615 | `_write_zip(job, job_dir, ...)` | M+F+U | `_write_output(job, job_dir, files_dir, sources, fonts, fonts_by_id, steps)` (Task 7 branches it to the tree) |
| jobs 617, 628, 632, 641 | `_job_failed`/`_fail_job` | M | unchanged |
| jobs 645, 651, 655 | `_run_step` body | F+U | `_execute(files_dir, sources, ...)`, `_read_back(job, files_dir, sources, ...)` |
| jobs 662 | `append_log` | M | unchanged |
| jobs 665, 674 | `_execute`, `out_abs` | F | `os.path.join(files_dir, step["output"])` |
| jobs 678, 687 | `_plain_source`/`_plain_token` calls | F+U | `(font, files_dir, sources, plain)` / `(token, files_dir, sources, gz_upload, plain)` |
| jobs 725, 732, 740, 741, 748 | `_read_back` | F | `files_dir` for `out_abs`, `_prepared_source(job, files_dir, ...)`, `_identity(files_dir, ...)` |
| jobs 751, 761, 770 | `_identity` | F | `step_dir`/face under `files_dir` |
| jobs 804, 808 | `_prepared_source(job, job_dir, font_id)` | F | `files_dir` |
| jobs 811, 819, 824 | `_plain_source` | U+F | `sources.abs_of(font.get("root", 0), font["path"])`; the copy under `files_dir/work/<font id>` |
| jobs 829, 838 | `_plain_token` | U+F | as above |
| jobs 840, 856 | `_write_zip` | M+F+U | `zipout.write_zip(job, job_dir, index, fonts_by_id, effective, repo_dir, files_dir=files_dir, sources=sources)` |
| jobs 873, 877, 880, 884 | `_fail_step(s)` | M | unchanged |
| zipout 72-74 | `append_log(job_dir, ...)` | M | unchanged |
| zipout 292, 297, 317 | `_licence_bytes(job_dir, repo_dir, eff)` | U | `_licence_bytes(sources, repo_dir, eff)`; `upload` -> `sources.abs_of(licence.get("root", 0), path)`, a `ValueError` re-raised with today's `"zipout: licence path %r is outside the upload directory"` |
| zipout 468, 492, 499 | `write_zip`/`_write_zip` | M+F+U | `write_zip(job, job_dir, index, fonts_by_id, effective, repo_dir, files_dir=None, sources=None)`; the defaults are `job_dir` and `Sources("upload", [job_dir + "/upload"])` |
| zipout 516 | the face read | F | `os.path.join(files_dir, step["output"])` |
| zipout 555 | `_licence_bytes` call | U | `(sources, repo_dir, eff)` |
| zipout 569, 598 | log append/read | M | unchanged |
| zipout 608 | `out_dir` | X | unchanged (an upload job's zip) |
| server 172, 176 | `_preview_glob(store, job_id, font_id)`, `_remove_preview` | F | `(store, job, font_id)` with the loaded job; `store.files_dir(job)/work/preview` |
| server 628 | `_scan_fonts` | U | `detect.scan(store.sources(current), local=current.get("source") == "local")` |
| server 655 | `_clear_previews` | F | `store.files_dir(job)/work/preview` (it loads the job) |
| server 668-670, 695, 698, 769, 790, 807, 810, 812 | `_job_files`, `_unpack`, `_record_counts` | X | unchanged |
| server 863, 869 | `_job_settings` | U | `settings.validate(fonts, body, store.sources(current))` |
| server 881, 882, 889, 893, 897, 898 | `_job_run` | F+U | `job_dir` is dropped (it is only used as F after the conversion); `files_dir`, `sources`; `run_ready(..., sources)`, `plan_steps(..., files_dir, tools_dir, sources, ...)`, `_check_steps(files_dir, sources, fonts, steps)`, `_check_notes(fonts, steps, sources, files_dir)` |
| server 906, 915, 919 | `_check_steps` | F+U | the output `_inside(files_dir, ...)`; the font path: `sources.abs_of(font.get("root", 0), path)` must not raise |
| server 922, 931, 938 | `_check_notes` | F+U | `work_dir = files_dir/work`; `materialized_argv([step], sources, work_dir)` |
| server 958, 965, 973 | `_job_preview` | F | `files_dir` |
| server 985, 990, 991 | `_job_face` | F | `files_dir` (Task 8 adds the output-folder branch) |
| server 998, 1002, 1003 | `_job_report` | F | `files_dir` (Task 8 adds `steps/` through `store.meta_dir(job)`) |
| server 1014, 1024, 1025, 1030, 1031, 1034 | `_job_probe` | F+U | `files_dir`; `_prepared_source(entry, eff, sources, out_dir)`; `range_spec(eff, sources)`; `sources.inside(rabs)` replaces `_inside(upload_dir, rabs)` |
| server 1094, 1098, 1099 | `_job_identity` | F | `files_dir` (Task 8 adds `steps/` through `store.meta_dir(job)`) |
| server 1106, 1110, 1119, 1124 | `_job_source_face` | F | `files_dir` |
| server 1138, 1142, 1143, 1147, 1148, 1155 | `_make_source_preview(job, job_dir, font)` | F+U | `(job, files_dir, font)`; `sources = store.sources(job)`; the plain path `sources.abs_of(font.get("root", 0), font["path"])`; `_companion_abs(eff, fonts, sources, out_dir)` |
| server 1169, 1174 | `_prepared_source(font, eff, upload_dir, out_dir)` | U | `(font, eff, sources, out_dir)` |
| server 1243, 1250 | `_companion_abs` | U | `sources.abs_of(companion.get("root", 0), companion["path"])` |
| server 1270, 1271 | `_job_zip` | X | unchanged |

Count: detect 10, settings 40, jobs 50, zipout 14, server 61 = 175. The review of Group A diffs every `realpath`
check in this list before and after.

### Task 2: `maker/sources.py` and the scan over `Sources` (slice S1, part 1)

**Files:**
- Create: `maker/sources.py`, `maker/test/test_sources.py`
- Modify: `maker/detect.py` (the 10 detect hits), `maker/test/test_detect_inputs.py`

**Interfaces:**
- Produces (`maker/sources.py`, stdlib only):
  - `FILE_CAP = 2000`, `LOCAL_FILE_CAP = 256 << 20`, `LOCAL_BYTES_CAP = 1 << 30`, `LOCAL_FREE_MIN = 256 << 20`
    (used by Task 7's free-space check; `server.py` imports it from here).
  - `class Sources(kind: str, roots: list[str], tmp_dir: str | None = None)`. `kind` is `"upload" | "local"`, and
    `ValueError` for any other value. `roots` is a list of absolute paths. An upload root is kept as given, and its
    checks compare `realpath`s exactly as today's code does. `tmp_dir` None means the system temp dir (upload jobs).
  - `Sources.coerce(value) -> Sources | None`. A `Sources` passes through, a `str` is `Sources("upload", [value])`,
    and None stays None. Every public function that took `upload_dir` accepts both forms through this, so the tests
    that pass strings stay as they are.
  - `abs_of(root: int, rel: str) -> str`. `root` must be an `int` (not `bool`) in range, and `rel` a non-empty `str`
    that is not absolute and contains no NUL. For a directory root: `os.path.join(roots[root], rel)`, whose
    `realpath` must be **strictly** under `realpath(roots[root]) + os.sep` (today's `_upload_path` rule; the root
    itself is refused). For a file root: `rel` must equal
    `os.path.basename(roots[root])`, and the root itself is returned. Anything else raises `ValueError("outside")`
    (callers keep their own messages).
  - `is_file_root(i) -> bool`.
  - `inside(abs_path: str) -> bool`. True when `realpath` is under one of the roots, or equal to a file root.
  - `rel_of(abs_path) -> tuple[int, str]`. The first root that contains it, with a `/`-separated rel, or
    `ValueError`.
  - `walk() -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]`. Returns `(files, refused)`, both in
    `(root, rel)` order. `files` are regular files: `(root, rel, abs)`. A file root yields
    `(i, basename, root)`. `os.walk(followlinks=False)`: a symlinked file goes into `refused` with
    `"symlink, skipped"` (both kinds, today's scan rule). A symlinked **directory** goes into `refused` for a local
    root only; an upload root keeps omitting it silently, as `os.walk` does today. Device, socket and FIFO entries are
    dropped silently. For `kind == "local"` the caps
    apply. A file over `LOCAL_FILE_CAP` is refused with `"too large, skipped"`. The walk stops at `FILE_CAP` files,
    or once `LOCAL_BYTES_CAP` bytes are passed, adding one refusal `(root, "", "more than %d files: choose a smaller
    folder" % FILE_CAP)` (bytes: `"more than 1 GiB: choose a smaller folder"`). An upload root walks without caps,
    as `scan` did.
- Produces (`maker/detect.py`): `scan(sources, local=False)`. With an upload `Sources`, the entries are byte-for-byte
  today's (no `root` key). With a local `Sources`, every entry has `"root": i`, its `path` is root-relative, and
  `entry["licences"][]` carry `"root"`. `abs_of` and `groups` are keyed by `(root, rel)`. Ids are positional in
  `(root, rel)` order.
  - **Folder key.** The "same folder" tables (`dos_folders`, the `eng` folder rule, the licence folders) are keyed by
    `folder_of(abs) = os.path.realpath(os.path.dirname(abs))`. This is the same for an upload (one root). Two
    directory roots stay two folders, since their real directories differ. Two **file** roots picked from one
    directory share a folder, so `/fonts/Munjo.ttf` and `/fonts/OFL.txt` picked together pair up.
  - **Licence ceiling.** `find_licences` walks upward from a file's folder to the ceiling of its root and no
    further. The ceiling is the root itself for a directory root, and the file's own parent for a file root (it
    does not walk up). A file root's licence is therefore only a licence file the user **also picked**, as another
    file root in the same directory (design issue 15). The server never lists or opens a sibling it was not given
    (spec 10.6).
  - `local=True` changes nothing else yet (Task 6).

- [ ] **Step 1: Write the failing tests.** `test_sources.py`, `class SourcesTest`:

```python
def test_upload_abs_of_matches_the_old_rule(self):
    # upload dir U with a/b.ttf and a symlink U/out -> /etc: abs_of(0, "a/b.ttf") == os.path.join(U, "a/b.ttf");
    # ValueError for "../x", "/etc/passwd", "out/passwd", "", "a\0b", root 1, root True
def test_file_root(self):
    s = Sources("local", [F])                       # F = tmp/in/Seoul12.rsrc
    self.assertEqual(s.abs_of(0, "Seoul12.rsrc"), F)
    with self.assertRaises(ValueError): s.abs_of(0, "other.rsrc")
    self.assertTrue(s.inside(F)); self.assertEqual(s.rel_of(F), (0, "Seoul12.rsrc"))
def test_two_roots_same_rel(self):
    s = Sources("local", [A, B])                    # both hold OFL.txt
    self.assertEqual((s.abs_of(0, "OFL.txt"), s.abs_of(1, "OFL.txt")), (A + "/OFL.txt", B + "/OFL.txt"))
    with self.assertRaises(ValueError): s.abs_of(0, ".")                              # the root itself: refused
    self.assertEqual(s.rel_of(B + "/OFL.txt"), (1, "OFL.txt"))
def test_walk_skips_links_and_devices(self):
    # dir root with x.ttf, link -> x.ttf, sub -> (a dir symlink), fifo (os.mkfifo):
    # files == [(0, "x.ttf", abs)]; refused == [(0, "link", "symlink, skipped"), (0, "sub", "symlink, skipped")]
def test_walk_caps(self):
    # with mock.patch.object(sources, "FILE_CAP", 3) over 5 files: 3 files, refused ends with
    #   (0, "", "more than 3 files: choose a smaller folder")
    # with LOCAL_FILE_CAP 10 and a 20-byte file: refused (0, "big.bin", "too large, skipped")
def test_upload_walk_has_no_caps(self):
    # FILE_CAP 1 patched, an upload Sources over 3 files: 3 files, refused []
def test_coerce(self):
    self.assertEqual(Sources.coerce("/u").roots, ["/u"]); self.assertEqual(Sources.coerce("/u").kind, "upload")
    s = Sources("local", ["/a"]); self.assertIs(Sources.coerce(s), s); self.assertIsNone(Sources.coerce(None))
```

  `test_detect_inputs.py`:

```python
def test_scan_two_roots_keeps_folders_apart(self):
    # roots A, B: each holds OFL.txt and a TTF (inputfx.ttf) at top level
    fonts = detect.scan(Sources("local", [A, B]))
    ttfs = [f for f in fonts if f["format"] == "ttf"]
    self.assertEqual([(f["root"], f["id"]) for f in ttfs], [(0, ttfs[0]["id"]), (1, ttfs[1]["id"])])
    for f in ttfs:
        self.assertEqual([(l["root"], l["path"]) for l in f["licences"]], [(f["root"], "OFL.txt")])
def test_file_roots_in_one_folder_pair_up(self):
    # tmp/fonts/Munjo.ttf (inputfx.ttf), tmp/fonts/OFL.txt, tmp/fonts/NOTES.txt (licence text, not picked)
    with mock.patch("builtins.open", wraps=open) as spy:
        fonts = detect.scan(Sources("local", [fonts_dir + "/Munjo.ttf", fonts_dir + "/OFL.txt"]))
    ttf = next(f for f in fonts if f["format"] == "ttf")
    self.assertEqual(ttf["licences"], [{"root": 1, "path": "OFL.txt", "first_line": mock.ANY}])
    self.assertNotIn(fonts_dir + "/NOTES.txt", [c.args[0] for c in spy.call_args_list])   # never opened
    fonts = detect.scan(Sources("local", [fonts_dir + "/Munjo.ttf"]))
    self.assertEqual(fonts[0]["licences"], [])                                      # alone: no licence found
```

  The proof that the upload scan is unchanged is the unmodified `test_detect.py` and `test_detect_inputs.py` (91 +
  34 tests), not a comparison of the new code with itself.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_sources.py' -v` and
  `... -p test_detect_inputs.py -k two_roots -k file_roots_in_one_folder`. Expected: FAIL (`No module named 'sources'`).
- [ ] **Step 3: Implement** `sources.py` and the detect rows of the S1 hit list.
- [ ] **Step 4: Run** `test_sources.py`, `test_detect.py`, `test_detect_inputs.py`. Expected: `OK`, with every
  existing detect test unchanged.
- [ ] **Step 5: Gates** G1, G2 (702), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: Sources, the one resolver for input paths; scan walks it (t_cbd14d61)"`.

Cannot verify here: nothing beyond Linux symlink semantics. A macOS firmlink is resolved by `realpath` the same way,
but that is not tested on macOS.

### Task 3: settings over `Sources`, roots on every path-valued field (slice S1, part 2)

**Files:**
- Modify: `maker/settings.py` (the 40 settings hits), `maker/test/test_settings.py`

**Interfaces:**
- Consumes: `Sources`, `Sources.coerce`, `abs_of` (Task 2).
- Produces:
  - Every function in the S1 hit list takes `sources` (a `Sources` or a string) where it took `upload_dir`.
  - A licence choice `{"kind": "upload", "root": i, "path": rel}`, a per-font or batch `range_root: int`, and an
    entry's `root`. On a **local** job, a missing or out-of-range root is an error. On an **upload** job, any `root`
    or `range_root` key is an error. Messages: `"%s: licence root %s is not a source" % (fid, root)` and
    `"%s: range root %s is not a source" % (fid, root)` (`fid` is `"batch"` for the batch range). `range_root` is
    **not** added to `BATCH_KEYS` (that would make every stored batch "missing key"). It is read with
    `.get("range_root", 0)` from the batch and per-font dicts, and its type is checked where `range` is (an int or
    absent).
  - `_upload_path(fid, rel, sources, root=0)` keeps the message `"%s: %s is outside the upload"`.

- [ ] **Step 1: Write the failing tests** in `test_settings.py`, `class SourcesSettingsTest`. A local `Sources` over
  two roots A and B is used directly. Each root holds `OFL.txt` (different texts) and a TTF. The fonts come from
  `detect.scan(Sources("local", [A, B]))`.

```python
def test_licence_resolves_to_its_own_root(self):
    st = settings.defaults(fonts)          # Task 6 adds root to the default; here set it by hand
    for fid, per in st["fonts"].items():
        per["licence"] = {"kind": "upload", "root": fmap[fid]["root"], "path": "OFL.txt"}
    shas = {fid: settings._licence_sha(index, per["licence"], src, settings._licence_paths(fonts)) for ...}
    self.assertEqual(shas[f_a], sha256(A_OFL)); self.assertEqual(shas[f_b], sha256(B_OFL))
def test_licence_root_errors(self):
    # local: root 2 -> "f01: licence root 2 is not a source"; root missing -> "f01: licence root None is not a source"
    # upload (a string dir): root 0 present -> "f01: licence root 0 is not a source"
def test_range_root_errors(self):
    # local: range "list.txt" with range_root 5 -> "f01: range root 5 is not a source"; batch -> "batch: range root 5 ..."
    # upload: range_root present -> refused the same way
def test_plan_steps_reads_each_root(self):
    steps = settings.plan_steps(job, files_dir, TOOLS, Sources("local", [A, B]))
    # the mkfont argv of f_a names A/<ttf>, of f_b names B/<ttf>; work/ under files_dir
def test_upload_path_message_unchanged(self):
    with self.assertRaisesRegex(ValueError, r"^f01: \.\./x is outside the upload$"):
        settings._upload_path("f01", "../x", "/tmp/u")
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_settings.py -k SourcesSettings -v`.
  Expected: FAIL.
- [ ] **Step 3: Implement** the settings rows of the S1 hit list and the root validation.
- [ ] **Step 4: Run** `test_settings.py`, `test_plan_inputs.py`. Expected: `OK`, the existing tests untouched.
- [ ] **Step 5: Gates** G1, G2 (707), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: settings resolve every input path through Sources with its root (t_cbd14d61)"`.

Cannot verify here: nothing; all of it is in-process.

### Task 4: jobs and zipout over `Sources` and the files directory (slice S1, part 3)

**Files:**
- Modify: `maker/jobs.py` (50 hits), `maker/zipout.py` (14 hits), `maker/test/test_jobs.py`, `maker/test/test_zipout.py`

**Interfaces:**
- Produces (`jobs.Store`):
  - `meta_dir(job_id: str) -> str` is `self.path(job_id)`: the name every **metadata-directory** read in a handler
    uses from now on (`log.md`, `steps/`), so a handler never calls `store.path(` itself.
  - `files_dir(job: dict) -> str`. Returns `self.path(job["id"])` for `job.get("source", "upload") == "upload"`.
    (Task 6 adds the local branch.)
  - `sources(job: dict) -> Sources`. Returns `Sources("upload", [self.path(job["id"], "upload")])`. (Task 6 adds the
    local branch.)
- Produces (`jobs.Worker`): the signatures in the S1 hit list (`_run_steps(job, job_dir, files_dir, sources, cancel)`,
  `_write_output(...)` which calls `write_zip` here). `materialized_argv(steps, sources, work_dir)` accepts a string.
- Produces (`zipout`): `write_zip(job, job_dir, index, fonts_by_id, effective, repo_dir, files_dir=None,
  sources=None)` and `_licence_bytes(sources, repo_dir, eff)`.

- [ ] **Step 1: Write the failing tests.**

```python
# test_jobs.py StoreTest
def test_files_dir_and_sources_of_an_upload_job(self):
    job = self.store.create()
    self.assertEqual(self.store.files_dir(job), self.store.path(job["id"]))
    src = self.store.sources(job)
    self.assertEqual((src.kind, src.roots), ("upload", [self.store.path(job["id"], "upload")]))
def test_materialized_argv_takes_sources(self):
    s = Sources("local", [A, B])          # B holds x.bdf.gz
    argv = jobs.materialized_argv([{"font": "f02", "argv": [["t", B + "/x.bdf.gz"]]}], s, "/w")
    self.assertEqual(argv, [["t", "/w/f02/x.bdf"]])
# test_zipout.py
def test_licence_bytes_by_root(self):
    s = Sources("local", [A, B])
    eff = {"licence": {"kind": "upload", "root": 1, "path": "OFL.txt"}}
    self.assertEqual(zipout._licence_bytes(s, REPO, eff), B_OFL)
    with self.assertRaisesRegex(ValueError, "outside the upload directory"):
        zipout._licence_bytes(s, REPO, {"licence": {"kind": "upload", "root": 1, "path": "../A/OFL.txt"}})
def test_write_zip_reads_faces_from_files_dir(self):
    # a done step whose output exists only under files_dir/work/s01/: write_zip(..., files_dir=fd) zips its bytes;
    # log.md is read from job_dir (the zip's svf-maker-<id>/BUILD.md starts with job_dir/log.md's text)
```

- [ ] **Step 2: Run** them. Expected: FAIL (`Store has no attribute files_dir`).
- [ ] **Step 3: Implement** the jobs and zipout rows of the S1 hit list.
- [ ] **Step 4: Run** `test_jobs.py`, `test_zipout.py`, `test_plan_inputs.py`, `test_v3_output.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (711), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: the worker and the zip read inputs through Sources and work files from the files directory (t_cbd14d61)"`.

Cannot verify here: nothing.

### Task 5: the server over `Sources` and the files directory (slice S1, part 4)

**Files:**
- Modify: `maker/server.py` (61 hits), `maker/test/test_server.py`

**Interfaces:**
- Consumes: `Store.files_dir`, `Store.sources` (Task 4); the settings signatures (Task 3).
- Produces: `_preview_glob(store, job, font_id)`, `_remove_preview(store, job, font_id)`,
  `_check_steps(files_dir, sources, fonts, steps)`, `_check_notes(fonts, steps, sources, files_dir)`,
  `_make_source_preview(job, files_dir, font)`, `_prepared_source(font, eff, sources, out_dir)`,
  `_companion_abs(eff, fonts, sources, out_dir)`.
  `_kept_settings(old, fonts, old_fonts, roots=None, old_roots=None)`: for local jobs (`roots` given), the key is
  `(old_roots[e["root"]]["path"], e["path"], e["face_index"])`, mapped onto
  `(roots[f["root"]]["path"], f["path"], f["face_index"])`. For upload jobs it stays `(path, face_index)`.
  Root-indexed settings are remapped through `old index -> old root path -> new index`: a kept per-font
  `licence: {"kind": "upload", "root": i}`, a per-font `range_root`, and the batch `range_root`. When the old root
  is gone, the licence falls back to the font's fresh default, and a range falls back to no range (`range` and
  `range_root` dropped). The full signature is `_kept_settings(old, fonts, old_fonts, roots=None, old_roots=None,
  local=False)`, and it calls `settings.defaults(fonts, local=local)` (the `local` keyword exists from Task 6; Task 5
  passes it through, and `defaults` ignores it until then).

- [ ] **Step 1: Write the failing tests** in `test_server.py`:

```python
# KeptCompanionTest
def test_kept_settings_by_root_path_for_local(self):
    old_roots = [{"path": "/a"}, {"path": "/b"}]; roots = [{"path": "/b"}, {"path": "/c"}, {"path": "/a"}]
    # old f01 = (/a, x.ttf), f02 = (/b, x.ttf) with per-font dest "games/a" / "games/b"
    # new scan: f01 = (root 0 -> /b, x.ttf), f02 = (/c, x.ttf), f03 = (/a, x.ttf)
    kept = server._kept_settings(old, new_fonts, old_fonts, roots=roots, old_roots=old_roots)
    self.assertEqual([kept["fonts"][f]["dest"] for f in ("f01", "f03")], ["games/b", "games/a"])
    self.assertEqual(kept["fonts"]["f02"]["dest"], settings.defaults(new_fonts)["fonts"]["f02"].get("dest", "dos"))
def test_kept_settings_remaps_root_indices(self):
    # old f01 (root 0 = /a) has licence {"kind": "upload", "root": 0, "path": "OFL.txt"} and range_root 0, batch
    #   range_root 1 (/b); after the roots are reordered to [/b, /c, /a]: f03's licence root == 2, range_root == 2,
    #   batch range_root == 0; with /a removed from the roots: the licence is the fresh default, range and range_root
    #   are gone
# ApiTest
def test_files_dir_is_the_only_work_root(self):
    other = tempfile.mkdtemp()
    with mock.patch.object(jobs.Store, "files_dir", lambda self, job: other):
        jid = self.minimal_job()
        # GET preview/<fid>/source.png, the probe, POST run to done
    # every work/ file is under `other`; data/jobs/<jid>/ holds job.json, log.md, upload/, out/ (the zip) and nothing else
def test_no_upload_path_outside_the_upload_handlers(self):
    # inspect.getsource of every Handler method except _job_files, _unpack, _record_counts, _reserve_upload,
    # _release_upload, _receive, _job_zip: no match of r"""(store\.path|os\.path\.join)\([^)]*["']upload["']"""
    # (an upload directory built by hand) and no "store.path(" call (metadata reads go through store.meta_dir)
```

  This rule stays true in every later task. Task 6's `_job_create` compares the string `"upload"` but builds no
  path. Task 8's `steps/` reads go through `store.meta_dir(job)`. `_job_run` no longer holds `job_dir`.

- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** the server rows of the S1 hit list.
- [ ] **Step 4: Run** `test_server.py`, `test_server_signals.py`, `test_page_dom.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (715), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: every handler resolves inputs through Sources and work files through the files directory (t_cbd14d61)"`.

Cannot verify here: nothing.

**Group A review gate.** One review after Task 5, focused on Review Focus 4 (token) and on the S1 hit list. Diff
every `realpath`/`startswith`/`_inside` check at `ce976f8` against its new form, and confirm that no existing test was
edited (`git diff ce976f8 -- maker/test` shows only additions in Tasks 1-5).

---

# Group B: the local job

Tasks 6 -> 7 -> 8 run in order (they share `server.py`, `jobs.py`, `settings.py`). Task 10 (unwired Mac code: only
`macfx.py`, `srcprep.py` and their tests) may run alongside them **in its own worktree**, and lands after Task 8,
rebased.

### Task 6: create, sources, detect (slice S3, part 1)

**Files:**
- Modify: `maker/sources.py` (path rules), `maker/jobs.py` (`Store.create`, `files_dir`, `sources`),
  `maker/server.py` (`_job_create`, `_job_sources`, `_job_files` 409, `_job_detect`, `_job_get`, umask),
  `maker/detect.py` (local labels, archive label, `tmp_dir`), `maker/settings.py` (default text licence, licence root
  in defaults), `maker/preview.py` (`env` passthrough in `bake_source_face`)
- Create: `maker/test/localfx.py`, `maker/test/test_local.py`
- Modify: `maker/test/test_detect_inputs.py`, `maker/test/test_server.py` (`LocalBindTest.test_origin_null_on_put_sources`;
  `test_kept_settings_by_root_path_for_local` gains the `local=True` default-licence case)

**Interfaces:**
- Produces (`maker/sources.py`):
  - `class PathRefused(ValueError)` carrying `.reason`.
  - `stat_id(path) -> tuple[int, int]` is `(st_dev, st_ino)` of `os.stat`.
  - `ancestors_ids(path) -> list[tuple[int, int]]` lists the ids of the path, its parent, and so on up to `/`.
  - `overlaps(a, b) -> bool`. True when `stat_id(a)` is in `ancestors_ids(b)` or the reverse. A cheap string-prefix
    pass on `realpath`s runs first.
  - `check_path(path, *, want: str, data_root: str, allowed: list[str] | None) -> tuple[str, str]`. Returns
    `(realpath, "file"|"dir")`. `want` is `"source"` or `"output"`. Refusals, in this order, with these reasons:
    `"not an absolute path"`, `"path too long"` (over 4,096 UTF-8 bytes), `"NUL in path"`, `"no such file or
    folder"` (`not os.path.lexists`), `"the path is a symlink"`, `"/ cannot be chosen"`, `"not a regular file or
    folder"` (a source) / `"not a folder"` (an output), `"the data folder cannot be chosen"` (it overlaps
    `data_root`), `"outside SVF_MAKER_ROOTS"`.
  - `allowed_roots(environ) -> list[str] | None` reads `SVF_MAKER_ROOTS`, colon-separated, with each entry
    realpath'd. Unset or empty gives None.
- Produces (`jobs`):
  - `Store.create(source="upload", output_dir=None, output_id=None)`. A local job gets `source`, `output_dir`,
    `output_id` (a list of 2 ints), `roots: []`, `owned: {}`, `upload: {"files": 0, "bytes": 0, "refused": []}`,
    and **no** `upload/ work/ out/`. Only `job.json` is written. `owned` is the job's ownership record
    (output-relative path -> sha256 of the bytes this job wrote there). It is a **top-level** key that no state
    transition resets: `POST detect` and `POST run` both set `result=None` (`server.py:607-609`, `:899`), so
    ownership cannot live in `result` (Task 7 fills it).
  - `Store.list()` items gain `"source"` (default `"upload"`) and `"output_id"` (or None), so the one-active-job
    check, `recover` and the sweeps need no per-job `load` to find local jobs.
  - `Store.files_dir(job)` is `<output_dir>/.svf-maker-<id>` for a local job.
  - `Store.ensure_files_dir(job) -> str` checks `stat_id(output_dir) == tuple(job["output_id"])`, else raises
    `OutputGone("output folder is gone or changed")`. It then runs `os.makedirs(files_dir/work/tmp, mode=0o700)` and
    `os.chmod`s each level it made to 0o700. Never the output folder itself.
  - `Store.sources(job)` is `Sources("local", [r["path"] for r in job["roots"]], tmp_dir=files_dir/work/tmp)`.
  - `class OutputGone(Exception)`.
- Produces (`server`):
  - `POST /api/jobs` with body `{"source": "local", "output_dir": "/abs"}`. Without the token: 403
    `"local mode is off"`. A bad path: 400 `"output folder: <reason>"`. Another active job (`uploading`, `detected`,
    `queued`, `running`) with the same `output_id`: 409 `"output folder is in use by job <id>"`. It then runs
    `ensure_files_dir` and answers `{"id"}`. An empty body or `{"source": "upload"}` is today's upload job.
  - `PUT /api/jobs/<id>/sources` with `{"paths": [...]}`. A local job in `uploading`/`detected` state only, else 409
    (`"job <id> is <state>"`). On an upload job: 409 `"job <id> is an upload job"`. Each path goes through
    `check_path(want="source")` plus the overlap rules: a source must not overlap the output folder (`"the output
    folder must not overlap an input"`). Refused paths go into `refused`, and the accepted ones become
    `job["roots"] = [{"path", "kind", "name"}]`. The walk (`Sources.walk`) gives `files`, `bytes` and further
    refusals. The answer is `{"roots", "files", "bytes", "refused": [{"path", "reason"}]}`. The job's previews are
    cleared.
  - `PUT /api/jobs/<id>/files` on a local job: 409 `"job <id> is a local job"`.
  - `POST detect` on a local job scans `store.sources(job)` with `local=True`, records
    `font["file_id"] = [st_dev, st_ino, st_size]` per entry (from `os.lstat`), and keeps settings through
    `_kept_settings(..., roots=..., old_roots=..., local=True)`. The transition keeps `job["owned"]` untouched.
    For a local job, each entry's `error` (a traceback) is appended to `log.md` in the metadata directory at detect
    time, and `job.json` keeps only `font["error_type"]` (the exception class name).
  - `GET /api/jobs/<id>` of a local job adds `source`, `output_dir` and `roots`, and drops every `font["error"]`.
  - `make_server(..., token)` calls `os.umask(0o077)` once when the token is set. The umask is process-global, so
    `LocalBase` and `LocalBindTest` save it in `setUp` and restore it in `tearDown`, and the rest of the discovery
    run keeps the default.
  - `_tool_env(job)` is `dict(preview.ENV, TMPDIR=files_dir/work/tmp, PYTHONDONTWRITEBYTECODE="1")` for a local job
    (design issue 10), else `None`. It reaches **every** tool start of a request thread:
    - `preview.bake_source_face(..., env=None)` gains the keyword and passes it to its `run_bounded` calls;
    - `Handler._run_probe(argv, cwd, out_svf, out_json, env=None)`;
    - `Handler._prepared_source(font, eff, sources, out_dir, env=None)`'s conversion loop;
    - `preview.source_png` starts no tool (Pillow in-process) and needs nothing.
  - Every preview, probe and source-face path of a local job first calls `ensure_files_dir`, and turns `OutputGone`
    into 404 `"output folder is gone or changed"`.
- Produces (`detect.scan(sources, local=True)`):
  - `"unknown (%s)" % hex` becomes `"unknown"`.
  - `_mac_entries`' `"unknown (Mac resource fork: %s)" % e` becomes `"unknown (Mac resource fork: %s)" %
    type(e).__name__`, since a `PrepError` text can quote resource types read from the file.
  - The `TooLarge` label `str(e)` stays: it is the maker's own message (a size and a cap), with no input bytes.
  - `unreadable: <Type>: <message>` becomes `unreadable: <Type>`.
  - `"; cannot prepare: %s"` becomes `"; cannot prepare (%s)" % type(ex).__name__`.
  - An archive is a kept entry with `format: "archive"`, `source_kind: "other"`, label `"archive: extract it first,
    then choose the folder"`.
  - `_bdf_glyphs(path, unicode_enc=None, data=None, tmp_dir=None)` passes `dir=tmp_dir` to `mkstemp`, and `scan`
    passes `sources.tmp_dir`.
  - `font["error"]` (the traceback) stays in the scan's entry; the server moves it to `log.md` (above).
  - `licences[].first_line` (the first 120 characters of a text accepted as a licence) is kept in `job.json`. It is
    the one piece of an input's text that reaches the data directory, as spec 8.2 item 3 states and accepts; the user
    needs it to choose.
- Produces (`settings.defaults(fonts, local=False, today=None)`):
  - With `local=True`, a font with no licence file gets `licence = {"kind": "text", "text": "%s: proprietary font,
    converted on %s for the owner's own use; not for redistribution." % (family, today)}`, where `today` defaults to
    the UTC date ISO. Its `licence_name` is `naming.suggest_licence_name(family, text)` (a `LIC...` name).
    `selected` stays False.
  - A font with a licence file gets `{"kind": "upload", "root": l["root"], "path": l["path"]}`.
- Produces (`maker/test/localfx.py`):
  - `local_tree(tmp) -> dict`. It writes `tmp/in/a/` (a TTF, `inputfx.ttf`, + `OFL.txt`), `tmp/in/b/` (a DOS raw
    844 16 px `fixtures._dos_raw` + an 8x16 `eng`), and `tmp/in/c/hanterm.bdf.gz` (gzip of `fixtures._bdf`'s johab
    BDF): five files. It returns `{"in": ..., "out": tmp/out (made), "roots": [tmp/in/a, tmp/in/b, tmp/in/c]}`.
    Task 11 extends it with the Mac files.
  - `walk_rel(root, skip_prefix=None) -> set[str]` returns the `/`-separated relative paths of every file under
    `root`, leaving out a top-level directory whose name starts with `skip_prefix`.
  - `read_only(test, path)` chmods dirs 0o555 and files 0o444, and registers a cleanup that restores 0o755/0o644.
  - `class LocalBase(unittest.TestCase)` runs `setUp` with `make_server("127.0.0.1", 0, REPO, data, token=TOKEN)`.
    `setUp` and `tearDown` save and restore `os.umask`. Helpers: `api(method, path, obj=None) -> (status, json)`
    sends the header; `local_job(roots, out) -> id` creates, puts the sources and detects; `run_to_done(jid)`;
    `rerun(jid, edit=None)` does `POST detect`, applies `edit(settings)` through `PUT settings`, then `POST run` and
    waits (a done job takes neither `PUT settings` nor `POST run`, `server.py:859, 885`).

- [ ] **Step 1: Write the failing tests** in `test_local.py` (`class LocalJobTest(LocalBase)`):

```python
def test_create_local_job(self):
    st, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
    jid = body["id"]; job = self.srv.store.load(jid)
    self.assertEqual((job["source"], job["output_dir"], job["roots"]), ("local", self.out, []))
    self.assertEqual(sorted(os.listdir(self.srv.store.path(jid))), ["job.json"])
    fd = os.path.join(self.out, ".svf-maker-" + jid)
    self.assertEqual(stat.S_IMODE(os.stat(fd).st_mode), 0o700)
def test_path_rules(self):
    # each with its reason, through PUT sources (refused[]) or POST /api/jobs (400): relative "in/a"; a symlink root;
    # a path under data_root; data_root's parent (contains it); the output folder under a source (400 at create when
    # the source exists? no: refused at PUT sources: "the output folder must not overlap an input"); a source under
    # the output folder; "/"; a non-existent path; a FIFO; SVF_MAKER_ROOTS=<tmp/in/a> set: tmp/in/b refused
    # "outside SVF_MAKER_ROOTS"; PUT files on a local job 409 "is a local job"; PUT sources on an upload job 409;
    # POST /api/jobs {"source": "local"} on ApiBase's no-token server 403 "local mode is off"
def test_path_rules_overlap_by_inode(self):
    # tmp/alias -> tmp (symlink); sources [tmp/in]; output tmp/alias/in/out (made): refused
    # "the output folder must not overlap an input" (POST /api/jobs accepted it; PUT sources refuses the source)
def test_one_job_per_output_folder_at_create(self):
    a = self.local_job(roots, out)            # detected
    st, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": out})
    self.assertEqual((st, body["error"]), (409, "output folder is in use by job %s" % a))
    self.api("DELETE", "/api/jobs/%s" % a)
    self.assertEqual(self.api("POST", "/api/jobs", {"source": "local", "output_dir": out})[0], 200)
def test_put_sources_and_detect(self):
    # answer: roots == [{"path": realpath, "kind": "dir", "name": "a"}, ...], files == 5, refused == []
    # GET job: every font has root and a root-relative path; no font has "error"; ids f01.. in (root, rel) order
def test_unreadable_label_names_the_type_only(self):
    # tmp/in/d/bad.ttf = b"\x00\x01\x00\x00" + b"\xff\xfe" * 40 (fontTools fails); tmp/in/d/x.bin = 64 random bytes;
    # tmp/in/d/z.zip (a zipfile): labels "unreadable: <Type>" exactly (re r"^unreadable: [A-Za-z_]+$"), "unknown",
    # "archive: extract it first, then choose the folder"; GET job JSON text contains no hex of x.bin's head and no ': '
    # after the type; job.json holds error_type, not error; log.md holds the traceback
def test_local_default_text_licence(self):
    # the DOS raw font of tmp/in/b (no licence beside it): licence kind "text", text matches
    # r"^\S+: proprietary font, converted on \d{4}-\d\d-\d\d for the owner's own use; not for redistribution\.$",
    # licence_name starts "LIC", selected False; the TTF of tmp/in/a: {"kind": "upload", "root": 0, "path": "OFL.txt"}
def test_previews_of_a_local_job_stay_in_files_dir(self):
    seen = []
    real = preview.run_bounded
    with mock.patch.object(preview, "run_bounded", lambda argv, cwd, timeout, env=None: (seen.append((cwd, env)), real(argv, cwd, timeout, env))[1]):
        # GET preview/<ttf>/source.png, GET probe/<ttf>/16/1.json, GET source/<dos>.svf (after setting dos_layout 844)
    self.assertTrue(seen)                         # the probe and the DOS bake both started tools
    for cwd, env in seen:
        self.assertTrue(cwd.startswith(fd)); self.assertIsNotNone(env)
        self.assertEqual(env["TMPDIR"], os.path.join(fd, "work", "tmp")); self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(env["HOME"], os.environ.get("HOME", "/"))
def test_no_upload_copy(self):
    # first form: after sources, detect and the three previews above: data/jobs/<id>/ is a subset of
    # {"job.json", "log.md"}; no file under data_root has the sha256 of an input; job.json text has no input's head hex
    # or base64
```

  `test_detect_inputs.py`:

```python
def test_scan_temp_copies_stay_in_tmp_dir(self):
    sentinel = tempfile.mkdtemp(); tmpd = tempfile.mkdtemp()
    with mock.patch.object(tempfile, "tempdir", sentinel):
        fonts = detect.scan(Sources("local", [root_with_ksc_bdf_gz], tmp_dir=tmpd), local=True)
    self.assertIsNotNone(fonts[0]["coverage"]); self.assertEqual(os.listdir(sentinel), []); self.assertEqual(os.listdir(tmpd), [])
```

  `LocalBindTest`:

```python
def test_origin_null_on_put_sources(self):
    # with the token: PUT /api/jobs/<local id>/sources with "Origin: null" -> 403 "cross-origin request"
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local.py -v` and the two others. Expected:
  FAIL.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run** `test_local.py`, `test_detect_inputs.py`, `test_server.py`, `test_settings.py`. Expected:
  `OK`.
- [ ] **Step 5: Gates** G1, G2 (729), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: local jobs: path-checked sources and output folder, files directory, scan over roots without input bytes in labels (t_cbd14d61)"`.

Cannot verify here: a case-insensitive filesystem or a bind mount (the inode rule covers both, but only the symlink
spelling is tested), a removable drive, and macOS `/tmp -> /private/tmp`.

### Task 7: run and the output tree (slice S3, part 2)

**Files:**
- Modify: `maker/jobs.py`, `maker/zipout.py`, `maker/settings.py` (`own_earlier`, `_step` gains `needs`),
  `maker/server.py` (`_job_run` checks, `_check_steps` on `needs`, `_check_notes` rewrite)
- Modify tests: `test_local.py`, `test_jobs.py` (the Step literal at :277 gains `"needs": []`), `test_zipout.py`
  (:78), `test_server_signals.py` (:67)

**Interfaces:**
- Produces (`settings`):
  - `_step(...)` gains `"needs": []`.
  - `run_ready(fonts, settings, index, sources, own_earlier=())`. `own_earlier` is a set of `svf/`-relative
    `"<dest>/<NAME>"` paths. A face, note or licence name in it is exempt from `"already exists in svf/<dest>;
    choose another name"`, `_clash_errors` and `_licence_present_ok`.
- Produces (`zipout`):
  - `collect(job, job_dir, files_dir, index, fonts_by_id, effective, repo_dir, sources, own_earlier=frozenset(),
    tools_dir=None) -> (entries: dict[str, bytes], sidecar: list[tuple[str, bytes]], result: dict, faces: list)`.
    This is today's `_write_zip` up to the sidecar texts. `job_dir` is the metadata directory: `log.md` is read
    from it for `BUILD.md` (`zipout.py:598`), and a refused note is appended to it (`:569`). `files_dir` is where the
    faces are read. `check_face`'s `"clash"` and `_text_entry`'s `NameClash` are skipped for a
    rel in `own_earlier`. Sidecar names are bare (`"BUILD.md"`, ...). `write_zip` prefixes `svf-maker-<id>/`.
  - `write_zip(...)` is `collect` + today's archive write. Unchanged output: every `test_zipout` assertion stays.
  - `write_tree(job, entries, sidecar, output_dir, output_id, owned: dict[str, str], on_landed) -> list[str]`.
    `owned` is `job["owned"]` (output-relative path -> the sha256 this job wrote there). `on_landed(rel, sha256)` is
    called as each file lands; the worker records it in `job["owned"]` and saves, so a partial landing is owned too.
    For each entry it writes `<path>.tmp` (fsynced) and then:
    - if `path` is in `owned` and the current file's sha256 equals `owned[path]` (or the file is absent):
      `os.replace(tmp, path)`;
    - if it is in `owned` with other current bytes: `NameClash` (someone else's file now);
    - otherwise, a new name: `os.link(tmp, path)`, where `FileExistsError` is a `NameClash`; then remove the tmp.
    - **No hard links** (FAT/exFAT sticks, many SMB/NAS mounts): when `os.link` raises `OSError` with `errno` in
      `(EPERM, ENOTSUP, EOPNOTSUPP, ENOSYS, EMLINK)`, the fallback is "claim, copy, verify, rename". It claims the
      name with `os.open(path, O_CREAT | O_EXCL | O_WRONLY, 0o600)`, where `FileExistsError` is a `NameClash` (the
      same atomic no-clobber guarantee `link` gave), and closes it empty. Then `os.replace(tmp, path)` swaps in the
      content atomically over its own claim. Then it re-reads `path` and requires its sha256 to equal the entry's.
      Otherwise it raises `OSError(EIO, "verify failed")`. On any failure after the claim, it removes `path` only if
      the path still holds its own claim or its own bytes.
    `build-<id>/*` is always `os.replace`d. It runs `os.stat(output_dir)` against `output_id` first (raising
    `jobs.OutputGone`). It creates `svf/<dest>/` and `build-<id>/` only. On any exception it removes the `.tmp`
    files. Returns the list of output-relative paths that landed, with partial results kept on failure (attached to
    the exception as `.landed`).
  - `note_commands(steps, font, sources=None, files_dir=None, tools_dir=None)`. With `sources`, each token that is
    under a root or under `files_dir` becomes its basename. `argv[0] == sys.executable` becomes `"python3"`. A token
    under `tools_dir` becomes `"tools/" + basename`, and under `maker/` `"maker/" + basename`. A copy step names the
    basename of the font's path.
- Produces (`jobs.Worker`, a local job):
  - `own_earlier(job) -> frozenset[str]` (in `jobs`, used by the worker and by `server._job_run`) is
    `{rel[len("svf/"):] for rel in job.get("owned", {}) if rel.startswith("svf/")}`. It is read from the top-level
    `job["owned"]` of Task 6, which `POST detect` and `POST run` never reset. The previous `result` is gone by then.
  - `_write_output` uses `naming.RepoIndex(<output_dir>/svf)`, calls `collect(..., own_earlier(job))`, then
    `write_tree(..., job["owned"], on_landed)`.
  - `result = {"files": landed + kept, "written": [...faces...], "skipped": [...], "failed_steps": [...],
    "output_dir": ...}`. `kept` is every owned path a step of this run found `identical_to` (the job still owns it,
    and `job["owned"]` keeps its sha256). A done step gains `"written": "svf/<dest>/<NAME>"`, or keeps
    `identical_to`. An owned path the user deleted stays in `owned`, and `write_tree` treats an absent file as
    replaceable.
  - A `NameClash` or `OutputGone` fails the job with its message. An `OSError` in `write_tree` fails it with
    `"%s: %s" % (type, strerror)` and `result.files` = what landed.
  - `Worker._job_env(job) -> dict | None` is `dict(ENV, TMPDIR=files_dir/work/tmp, PYTHONDONTWRITEBYTECODE="1")`
    for a local job, else None. It is passed to every `run_command` of the job, **including** `_identity`'s
    recogniser run, which today builds its own `dict(ENV, SVF_RECOG_DIR=recog)` (`jobs.py:771`) and now uses
    `dict(self._job_env(job) or ENV, SVF_RECOG_DIR=recog)`.
  - `_run_steps` fails a step whose `needs` names a step in state `failed` with `"companion source failed"` before
    running it.
- Produces (`server._job_run`, a local job, under the job lock):
  - `ensure_files_dir`, where `OutputGone` is 409 `"output folder is gone or changed"`.
  - Every root still passes `check_path`.
  - Every entry a planned step reads must have a `file_id` equal to a fresh `os.lstat` (same dev, ino, size,
    regular). That means each selected font, its `latin_companion` and (Task 11) `htbl_companion` entries, the entry
    of an `upload` licence it names, and the list entry of a `file` range. A change is 409 `"%s: the input changed
    since detection: detect again" % entry["path"]`.
  - The one-active-job rule is checked again (409).
  - `shutil.disk_usage(output_dir).free >= sources.LOCAL_FREE_MIN + sum(selected input sizes)`, else 409 `"not
    enough free space in %s" % output_dir`.
  - `run_ready(..., own_earlier=jobs.own_earlier(j))` against `RepoIndex(<output_dir>/svf)`.
  - `_check_steps` refuses a `needs` id that is not an earlier step (500-style `ValueError`, as the output check
    does).
  - `_check_notes` uses the `note_commands` rewrite.

- [ ] **Step 1: Write the failing tests** (`test_local.py`, `class LocalRunTest(LocalBase)`). Each selects the TTF of
  `tmp/in/a` (mkfont 16 px 1 bpp, dest `dos`) and the DOS raw font of `tmp/in/b` (`dos_layout` 844, jamo, dest
  `jamo-extra`, its text licence), and runs. Every "re-run" below is `self.rerun(jid, edit)`: `POST detect`,
  `PUT settings`, `POST run`, the only path the server offers from `done`.

```python
def test_run_writes_the_tree(self):
    job = self.run_to_done(jid)
    self.assertNotIn("zip", job["result"])
    self.assertEqual(sorted(job["result"]["files"]), sorted(walk_rel(self.out, skip_prefix=".svf-maker-")))
    self.assertEqual(set(self.srv.store.load(jid)["owned"]), set(job["result"]["files"]))
    # walk_rel(out) == {svf/dos/<TTF face>, svf/dos/<note>, svf/dos/OFL<..>.TXT, svf/jamo-extra/<DOS face>,
    #   svf/jamo-extra/<note>, svf/jamo-extra/LIC<..>.TXT, build-<id>/BUILD.md, build-<id>/LICENCES.tsv.lines,
    #   build-<id>/FAMILIES.tsv.lines, build-<id>/FACES.TSV.lines}
    self.assertEqual(self.api("GET", "/api/jobs/%s/zip" % jid)[0], 404)
def test_detect_keeps_owned(self):
    owned = self.srv.store.load(jid)["owned"]        # after run 1
    self.api("POST", "/api/jobs/%s/detect" % jid)
    self.assertEqual(self.srv.store.load(jid)["owned"], owned); self.assertIsNone(self.srv.store.load(jid)["result"])
def test_collisions(self):
    # self.rerun with the clock a day later (mock zipout._utc_now): run_ready passes, face and note rewritten,
    #   build-<id>/BUILD.md rewritten; self.rerun with a changed setting (mkfont ascent) likewise;
    # a second job B (after A is done), same folder, same face name, other bytes (another TTF): POST run is refused
    #   synchronously by run_ready: status 400, error == "f01: <NAME> already exists in svf/dos; choose another name";
    #   B stays "detected"; A's face bytes and build-<A>/ unchanged
    # a third job whose face bytes equal A's face under another name: done, step identical_to == "dos/<NAME>"
def test_rerun_after_identical_keeps_ownership(self):
    # run 1 writes X; rerun unchanged -> identical_to own X, X in result.files and in owned;
    # rerun with a changed ascent -> X replaced (new bytes, owned[X] updated)
def test_own_earlier_replaced_only_when_unchanged(self):
    # run 1 writes X; the test overwrites X with other bytes (as another job would); rerun -> POST run passes
    #   run_ready (X is owned), the job ends failed with "name clash: svf/dos/<NAME>", X keeps the other bytes"
def test_one_job_per_output_folder_two_servers(self):
    # a second LocalBase server (own data root) runs a job writing the same new name concurrently: the os.link of
    # the later one fails -> its job failed with "name clash", the first file's bytes untouched (sequence it with
    # mock: the second server's write_tree runs after the first wrote, its index built before)
def test_write_tree_without_hard_links(self):
    # mock os.link to raise OSError(errno.EPERM): the run is done, the tree as in test_run_writes_the_tree, every
    #   written file's sha256 equals owned[...]; no "*.tmp" left; with a planted file at the target name created between
    #   the index and the write (mock): failed "name clash", the planted bytes untouched
def test_notes_and_logs(self):
    # roots under a 300-byte path (nested dirs of 50-char names, the first one a unique name such as
    # "local-notes-<uuid4 hex>"): every note line <= 512 bytes; no note line contains that unique component, the
    # test's tmp prefix, $HOME, nor a token starting with os.sep; the command lines start "python3 -P tools/" or
    # "python3 -P maker/"; log.md (metadata dir) contains the full root path (D4)
def test_input_changed_since_detection(self):
    # append a byte to the TTF after detect: POST run 409, error "<ttf name>: the input changed since detection: detect
    #   again" (the root-relative path); the same for the DOS font's eng companion (8x16 file in tmp/in/b) and for the
    #   TTF's OFL.txt licence
def test_not_enough_free_space(self):
    with mock.patch("shutil.disk_usage", return_value=(0, 0, 1)):  # POST run 409 "not enough free space in <out>"
def test_run_env_has_tmpdir_and_no_bytecode(self):
    # mock jobs.run_command to record env: every call has TMPDIR == fd/work/tmp and PYTHONDONTWRITEBYTECODE == "1";
    # with the stub recogniser of test_jobs (SVF_RECOG_DIR stub, RECOG_ARRAYS "lists", caps recog on) the identity
    # run's env has both too, plus SVF_RECOG_DIR
def test_write_tree_disk_full(self):
    # mock os.link to raise OSError(errno.ENOSPC) on the second call: job failed, error starts "OSError", result.files
    #   lists the first face only, no "*.tmp" under out
```

  `test_jobs.py`:

```python
def test_needs_cascade(self):
    # steps s01 source (font f02, fails: argv runs `false`), s02 jamo font f01 with needs ["s01"]:
    # s02 failed, error "companion source failed", its argv never ran (no stdout.txt in work/s02)
def test_check_steps_refuses_a_later_needs(self):
    # server._check_steps with s01.needs == ["s02"] raises ValueError
```

- [ ] **Step 2: Run** `test_local.py -k LocalRun`, `test_jobs.py -k needs -k later_needs`. Expected: FAIL.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run** `test_local.py`, `test_jobs.py`, `test_zipout.py`, `test_server.py`, `test_server_signals.py`.
  Expected: `OK`. Every `test_zipout` assertion on the zip's layout is unchanged.
- [ ] **Step 5: Gates** G1, G2 (745), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: a local run writes svf/ and build-<id>/ into the output folder; own-earlier replace, link for new names, notes without paths (t_cbd14d61)"`.

Cannot verify here: a real disk-full condition (mocked); a real FAT/exFAT stick or SMB/NAS mount without hard links
(the fallback is exercised by mocking `os.link` to raise `EPERM`); and two maker launches on two machines over a
network share (two servers in one process stand in).

### Task 8: sweeps and serving from the output folder (slice S3, part 3)

**Files:**
- Modify: `maker/jobs.py` (sweeps, `steps/`, recover/stop/retain/delete), `maker/server.py` (serving, the idle
  sweeper, the start-up thread), `maker/test/test_local.py`

**Interfaces:**
- Produces (`jobs`):
  - `Store.sweep_files(job) -> bool`. If `output_id` matches, it runs `shutil.rmtree(files_dir)`, holding the job's
    preview locks (`server._preview_lock` for each font id, through a `store.on_sweep` hook the server sets as it
    sets `on_delete`). That way a preview GET cannot re-make the directory while `rmtree` runs, from the start-up
    thread or the idle sweeper. On failure, or when the folder is gone or changed, it appends
    `{"path": files_dir, "output_dir": output_dir, "output_id": [dev, ino], "job": id}` to
    `<data_root>/pending-sweeps.json` (a JSON list, written through `.tmp` + `os.replace` under a store-wide lock)
    and logs `"sweep: <path>: <reason>"` to `log.md` when the metadata directory exists. It never raises. It returns
    True when the directory is gone.
  - `Store.retry_pending_sweeps()` retries each entry. It deletes **only** when all of these hold:
    - the basename is `".svf-maker-" + entry["job"]` and matches `^\.svf-maker-[0-9a-f]{12}$`;
    - `os.path.dirname(path) == entry["output_dir"]`;
    - `stat_id(entry["output_dir"]) == tuple(entry["output_id"])`, so an output folder that was replaced, re-created
      or re-mounted elsewhere is never touched;
    - the path itself is a real directory (`lstat`, not a link).
    It drops an entry when the directory is gone, when the retry succeeds, or when any check fails (a replaced output
    folder will never become the original again, so the entry is stale). A failed check is logged to stderr with the
    path and is never deleted.
  - `Store.delete(job_id)` runs, for a local job, `sweep_files` **before** the `rmtree` of the metadata directory.
  - At the end of `run_job` (in a `finally`, after `_write_output`), for a local job: move each `work/sNN/report.json`
    -> `<store.meta_dir(id)>/steps/sNN.report.json` and `work/sNN/identity.json` ->
    `<store.meta_dir(id)>/steps/sNN.identity.json`, set `step["report"] = "steps/sNN.report.json"`, then
    `sweep_files`.
  - `Worker.recover()`: a `running` local job becomes `failed`/`"interrupted"`, as today. A **queued local job** also
    becomes `failed`/`"interrupted"` and is not re-enqueued (design issue 9). The sweeps of every local job and
    `retry_pending_sweeps` run on a daemon thread `make_server` starts after the bind
    (`server.startup_sweep: threading.Thread`).
  - `Worker.stop()` runs `sweep_files` for every local job after the running one has ended.
  - `retain()` works through `delete`, unchanged.
- Produces (`server`):
  - `_job_face` of a `done` local job serves `<output_dir>/<step["written"]>`, or `<output_dir>/svf/<identical_to>`,
    after `_inside(output_dir, ...)`, a regular file, and `output_id` unchanged. Otherwise 404 `"face not in the
    output folder"`. For any other state, it serves the files directory as before.
  - `_job_report`/`_job_identity` of a local job read `<store.meta_dir(job)>/steps/sNN.{report,identity}.json` when
    the step has them (through `meta_dir`, so Task 5's `test_no_upload_path_outside_the_upload_handlers` holds).
  - `_job_zip` of a local job: 404 `"a local job writes a folder"`.
  - Every preview, probe or source GET of a local job re-makes the files directory through `ensure_files_dir` and
    records `server.touched[job_id] = time.monotonic()`.
  - `_prepared_source(..., keep=True)`: a local job passes `keep=False` when baking (`_make_source_preview`), and
    removes `<font id>/source*` after the bake. The probe keeps `keep=True`, since its prepared copy is under the
    probe's own lock and is removed with `work/preview` (spec 8.3 names the bake only).
  - `LOCAL_IDLE_SWEEP_S = 1800`. `server.sweep_idle(now=None)` sweeps the files directory of every `detected` local
    job untouched for longer than that. A daemon thread calls it every 60 s.

- [ ] **Step 1: Write the failing tests** (`test_local.py`, `class LocalSweepTest(LocalBase)`):

```python
def test_sweep_points(self):
    # fd exists after POST /api/jobs; holds work/preview/<fid>/probe after a probe GET; gone after run ends;
    # re-made by GET source/<dos>.svf on the done job; gone after DELETE; a second make_server on the same data root
    # with a planted out/.svf-maker-<id>/ of a stored local job (state done): gone once srv.startup_sweep.join(10);
    # Worker.stop() removes one a GET re-made
def test_pending_sweeps_retried(self):
    # mock shutil.rmtree to raise OSError once: DELETE succeeds, pending-sweeps.json lists fd; the next sweep point
    #   (srv.store.retry_pending_sweeps()) removes fd and empties the list; a planted entry "/tmp/x" (wrong name) stays
    #   untouched and is dropped from the list
def test_pending_sweep_of_a_replaced_output_folder(self):
    # mock shutil.rmtree to fail once: DELETE leaves an entry for out/.svf-maker-<id>; the test renames out ->
    #   out.old and makes a new out holding a directory .svf-maker-<id>/ with a file keep.txt (the same basename);
    #   retry_pending_sweeps(): out/.svf-maker-<id>/keep.txt still exists, the entry is dropped; the same with out
    #   replaced by a symlink to another folder holding that name: untouched
def test_idle_sweep(self):
    # detected local job, a probe GET, then srv.sweep_idle(now=time.monotonic() + LOCAL_IDLE_SWEEP_S + 1): fd gone;
    #   a later probe GET re-makes it and answers 200
def test_results_served_from_output(self):
    # GET face/<dos step>.svf == bytes of out/svf/jamo-extra/<NAME>.SVF, Cache-Control no-store; rename out ->
    #   GET 404 "face not in the output folder"; GET zip 404 "a local job writes a folder"
def test_reports_moved_to_steps(self):
    # after done: data/jobs/<id>/steps/ holds sNN.report.json for the mkfont step; GET report/sNN.json 200 with it;
    #   no report.json left under out
def test_output_folder_gone(self):
    # after POST /api/jobs: rename out -> out.moved, mkdir out: probe GET 404 "output folder is gone or changed";
    #   POST run 409 the same; nothing created under the new out; rename back -> the run proceeds to done
def test_no_store_headers(self):
    # local job: face, source (DOS raw bake), probe .svf and .json, preview .png, report: Cache-Control "no-store";
    #   identity: with the stub recogniser of test_jobs (SVF_RECOG_DIR + RECOG_ARRAYS "lists") the same
def test_no_write_outside_output(self):
    # local_tree; read_only(tmp/in); HOME, TMPDIR, XDG_CACHE_HOME, XDG_CONFIG_HOME of os.environ, tempfile.tempdir,
    # jobs.ENV["HOME"], preview.ENV["HOME"] -> empty sentinel dirs under tmp; the .bdf.gz hanterm font selected too;
    # snapshot (relpath, size, mtime_ns, sha256) of tmp/in before == after; the sentinels empty; tmp/out holds exactly
    # the Task 7 tree (no .svf-maker-*); while fd existed it was 0700 and its files 0600 (checked at a probe GET);
    # after srv.worker.stop() and server_close(): os.walk(tmp) == in (unchanged), out (as listed),
    # data/jobs/<id>/{job.json, log.md, steps/*}, the empty sentinels, and nothing else
def test_no_upload_copy(self):            # final form: the full job; data/jobs/<id>/ == {job.json, log.md, steps/}
```

- [ ] **Step 2: Run** `test_local.py -k LocalSweep`. Expected: FAIL.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run** `test_local.py`, `test_jobs.py`, `test_server.py`, `test_server_signals.py`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (755), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: local files directory swept at job end, delete, stop, start and idle; results served from the output folder (t_cbd14d61)"`.

Cannot verify here: a dead network mount at start-up (the thread is tested with a planted directory), a sync client
picking up `.svf-maker-<id>/` (the 0700/0600 modes are tested, the client is not), and a forced quit (`recover` is
tested by a second server on the same data root).

### Task 10: unwired Mac code: `macfx.py` and the `srcprep` subcommands (slice S5, drafted alongside S3)

**Files:**
- Create: `maker/test/macfx.py`, `maker/test/test_macfx.py`
- Modify: `maker/srcprep.py`, `maker/test/test_srcprep.py`

**Interfaces:**
- Produces (`maker/test/macfx.py`, importing `tools/test_macfbit3.py` and `tools/test_macfbit_svf.py` by path the way
  `inputfx` imports helpers):
  - `fbit3_raw(seed=1) -> bytes` is `synthetic(seed)[0]`. `htbl_raw(seed=1) -> bytes` is `synthetic(seed)[1]`
    (9,612 bytes). `htbl_raw_padded(seed=1)` is the same table in `make_htbl`'s 9,816-byte form (second length
    `0x2468`, the 51 entries appended).
  - `fbit3_fork(seed=1) = resource_fork({("fbit", 17408): fbit3_raw(seed)})`, and
    `htbl_fork(seed=1) = resource_fork({("HTBL", 1): htbl_raw(seed)})`.
  - `jm(fork) = jm_archive(<lh5 literal payload of fork>, len(fork))`, built with `lh5_block` as
    `TestJM` builds its payload.
  - `appledouble(fork)` and `macbinary(fork)` re-export `inputfx` (whose fork builder is `inputfx.fork`).
  - `suitcase(size=12)` builds the FOND inline, the way `tools/test_macfbit_svf.py:244` (`TestLatin`) does:
    `bytearray(52) + struct.pack(">HHHH", 0, size, 0, 300)` (one plain-style entry: size `size`, NFNT id 300). It
    returns `test_macfbit_svf._fork({("FOND", 1): fond, ("NFNT", 300): test_macfbit_svf._nfnt(CHARS)})` with
    `CHARS` the two-glyph table of `TestLatin` (`0x41`, `0x67`). The NFNT strike itself is 5 rows high (that is
    `_nfnt`'s fixed height). The FOND's listed size (12, matching `synthetic`'s `H`) is what
    `macfbit_svf.nfnt_for_size` and the maker's `mac["strikes"]` read.
  - `nfnt_only() = test_macfbit_svf._fork({("NFNT", 300): test_macfbit_svf._nfnt(CHARS)})`.
  - `fbit1_fork() -> bytes` is the HangulTalk 1.0 font of spec 12.1. The fixture is drafted here and is not
    required to pass `--check` until Task 12.
  - `hangul_pft() = bytes(range(256)) * 156 + bytes(64)` (40,000 bytes, written as `HANGUL24.PFT`).
- Produces (`maker/srcprep.py`):
  - CLI `srcprep.py mac-fork IN OUT`. `macsfnt.resource_fork(data)`, `_fork_guard`, then `macsfnt.resources`
    must parse it, else exit 2. OUT is the raw fork.
  - CLI `srcprep.py mac-htbl IN OUT`. `macfbit3.load_htbl1(data)`, then it requires
    `struct.unpack(">I", t[:4])[0] == 204` and `len(t) >= 8 + 204 + 4 * 2350`, else exit 2 `"not an HTBL 1 table"`.
  - `_apply_op` gains `"mac-fork"` (the fork bytes), `"mac-fbit3"` (`macfbit3.load_fbit(data)`), `"mac-htbl"` (as
    the CLI) and `"mac-fork-named"`, which raises `PrepError("named forks are read by the CLI only")` (Task 13).

- [ ] **Step 1: Write the failing tests:**

```python
# test_srcprep.py MacPrepTest; helper cli(self, sub, data) -> (exit code, OUT bytes or b"") writes data to a temp IN,
# runs `python3 -P maker/srcprep.py <sub> IN OUT`, reads OUT when it exists
def test_mac_fork_unwraps(self):
    for wrapped in (macfx.appledouble(f), macfx.macbinary(f)):        # f = macfx.fbit3_fork()
        self.assertEqual(self.cli("mac-fork", wrapped), (0, f))
    self.assertEqual(self.cli("mac-fork", f), (0, f))
def test_mac_fork_refuses_oversized(self):
    with mock.patch.object(srcprep, "MAX_BYTES", 100):
        with self.assertRaises(srcprep.PrepError): srcprep._apply_op(f, {"op": "mac-fork"})
    # the CLI cannot be patched in a subprocess; the in-process _apply_op path is the same _fork_guard call
def test_mac_htbl(self):
    self.assertEqual(self.cli("mac-htbl", macfx.htbl_fork()), (0, macfx.htbl_raw()))
    self.assertEqual(self.cli("mac-htbl", macfx.htbl_raw()), (0, macfx.htbl_raw()))
    bad = struct.pack(">I", 200) + macfx.htbl_raw()[4:]
    self.assertEqual(self.cli("mac-htbl", bad)[0], 2)
def test_apply_op_mac(self):
    self.assertEqual(srcprep.prepared_bytes(macfx.jm(macfx.fbit3_fork()), [{"op": "mac-fbit3"}]), macfx.fbit3_raw())
    self.assertEqual(srcprep.prepared_bytes(macfx.appledouble(macfx.fbit3_fork()), [{"op": "mac-fork"}, {"op": "mac-fbit3"}]), macfx.fbit3_raw())
# test_macfx.py
def test_fixtures_parse(self):
    self.assertEqual(len(macfx.htbl_raw()), 9612); self.assertEqual(len(macfx.htbl_raw_padded()), 9816)
    macfbit_svf.Fbit3(macfx.fbit3_raw()); macfbit_svf.Htbl1(macfx.htbl_raw_padded())     # no exception
    self.assertEqual(macfbit3.jm_unpack(macfx.jm(macfx.fbit3_fork())), macfx.fbit3_fork())
def test_fbit1_header(self):
    m = jamoset.MacFbit(macfx.fbit1_fork()); self.assertEqual((m.w, m.h, len(m.sets)), (16, 16, 45))
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_srcprep.py -k MacPrep -v` and
  `-p test_macfx.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the subcommands, `_apply_op` and `macfx.py`.
- [ ] **Step 4: Run** `test_srcprep.py`, `test_macfx.py`, then `~/.local/bin/heavy python3 -m unittest discover -s
  tools -p 'test_macfbit*.py'`. Expected: `OK` (tools untouched).
- [ ] **Step 5: Gates** G1, G2 (761 if it lands after Task 8; 6 tests of its own), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: srcprep mac-fork and mac-htbl, synthetic Mac fixtures (t_cbd14d61)"`.

Cannot verify here: a real fork from a HangulTalk disk (`SVF_MAKER_REAL_MAC1`/`MAC3`, Task 15).

**Group B review gate.** One review after Tasks 8 and 10. Focus: Review Focus 1-3. Check `test_no_write_outside_output`
and `test_no_upload_copy` against spec 8.3 and 10.4, and check the sweep list in 8.3 point by point (made / swept /
re-made / pending).

---

# Group C: the page and the Mac kinds

Tasks 11 -> 12 -> 13 run in order. Task 9 (page files only: `index.html`, the sources-panel region of `maker.js`,
`pagedrive.mjs`, `test_page_dom.py`) may run in a **separate worktree** alongside them. It lands after Task 13 and is
rebased onto it. Both edit `maker.js` in disjoint regions (Task 11: the JSON tables and the HTBL select; Task 9: the
upload/sources panel and the state line), and G3 runs at each commit.

### Task 9: the sources panel, the bridge hooks, "open folder" (slice S4)

**Files:**
- Modify: `maker/static/index.html`, `maker/static/maker.js`, `maker/static/style.css` (if the panel needs a rule),
  `maker/test/pagedrive.mjs`, `maker/test/test_page_dom.py`

**Interfaces:**
- Consumes: `GET /api/caps` `local` (Task 1); the local endpoints (Tasks 6-8).
- Produces (page):
  - At load the page calls `fetch("/api/caps")` and sets `state.local = caps.local === true`.
  - `index.html` has no upload panel element today: the `<aside>` holds the upload controls and `#jobs` together.
    Task 9 wraps the upload rows (not `#jobs`) in a new `<div id="upload-panel">` and adds a sibling
    `<div id="sources-panel" hidden>`.
  - With `state.local`, `#upload-panel` is hidden and `#sources-panel` is shown, holding a `<ul id="source-roots">`
    and the buttons `#choose-files`, `#choose-folder`, `#choose-output`. When `window.svfMaker` exists they call
    `pickFiles()`, `pickFolder()` and `pickOutputDir()`. `[]`/`null` changes nothing.
  - When `window.svfMaker` is absent, the buttons are hidden and `<textarea id="source-paths">` (one absolute path per
    line) and `<input id="output-dir">` are shown. When the bridge exists, those two fields are hidden.
  - `#detect-local` posts `/api/jobs` `{"source": "local", "output_dir"}`, then `PUT sources`, then `POST detect`.
    A refusal shows each `refused` item.
  - After `done`, the state line reads `"written to " + job.output_dir`. `#download` stays hidden and
    `#open-folder` is shown, enabled only with the bridge, and calls `window.svfMaker.openOutputFolder()` with **no**
    argument.
  - Next to the output chooser, the text: `intermediate files are kept in .svf-maker-<id>/ inside this folder while
    the maker runs; choose a folder that is not synced`.
  - The fonts table shows `roots[font.root].name + "/" + font.path` for a local job.
- Produces (`pagedrive.mjs`): any number of `--header NAME:VALUE` arguments after `SCRIPT_FILE`, applied with
  `Network.enable` + `Network.setExtraHTTPHeaders` before navigation.

- [ ] **Step 1: Write the failing tests** in `test_page_dom.py`, `class LocalPageTest`. It skips like `PageDomTest`.
  Its server has the token and `self.drive(job, script, headers=["X-Maker-Token:" + TOKEN])`.

```python
def test_without_the_header_every_api_call_is_403(self):
    # drive without --header: the script fetches /api/caps and returns its status -> 403
def test_sources_panel_with_typed_paths(self):
    # page script: no window.svfMaker; asserts #upload-panel hidden, #sources-panel shown, no visible input[type=file],
    # #source-paths and #output-dir visible, #choose-files hidden; fills the localfx roots and out, clicks
    # #detect-local; waits for the fonts table; returns its rows' labels -> contain "a/<ttf name>" and the DOS row
def test_run_says_written_and_open_folder_disabled(self):
    # select the TTF (dest dos), run, wait: state line == "written to " + out; #open-folder visible and disabled;
    # #download hidden
def test_bridge_fills_and_opens(self):
    # script installs window.svfMaker = {pickFolder: async () => [root], pickFiles: async () => [], pickOutputDir:
    #   async () => out, openOutputFolder: async (...a) => { window.__opened = a.length; }, platform: "linux"} before
    #   the page's load handler (Page.addScriptToEvaluateOnNewDocument through a pagedrive option --preload FILE);
    #   asserts #source-paths hidden, "choose folder" lists root in #source-roots, after a run "open folder" enabled
    #   and a click sets window.__opened === 0
def test_sync_caveat_is_shown(self):  # the caveat text is in index.html's sources panel (static read, no Chrome)
```

  `pagedrive.mjs` also gains `--preload FILE` (its text goes to `Page.addScriptToEvaluateOnNewDocument`), which the
  bridge test needs. Spec 12.4 says "a fake window.svfMaker injected by the script", and a preload is how the fake
  exists before the page's own load handler reads it.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_page_dom.py -k LocalPage -v`. Expected:
  FAIL.
- [ ] **Step 3: Implement** to the interfaces. `smoke_dom.py` is unchanged.
- [ ] **Step 4: Run** `test_page_dom.py` (all of it: the upload-mode tests must still pass), `python3
  maker/test/smoke_dom.py`, and `node --check maker/static/maker.js`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (791, landing after Task 13), G3.
- [ ] **Step 6: Commit** `git commit -m "maker page: sources panel for local mode, shell bridge hooks, written-to line and open folder (t_cbd14d61)"`.

Cannot verify here: Electron, its preload and `contextIsolation`, native dialogs, and `shell.showItemInFolder`. The
fake bridge stands in for all of them. Without Chrome or node the tests skip (both exist on this host).

### Task 11: Mac 7.1 kinds wired end to end (slice S5, 7.1 route group)

**Files:**
- Modify: `maker/detect.py`, `maker/routes.py`, `maker/settings.py`, `maker/presets.py`, `maker/server.py`,
  `maker/preview.py`, `maker/static/maker.js`, `maker/test/localfx.py`, `maker/test/inputkinds.py`
- Modify tests: `test_detect_inputs.py`, `test_routes.py`, `test_settings.py`, `test_server.py` (drift test,
  `canonical_fonts`, `test_page_layouts_cover_route_layouts`), `test_plan_inputs.py`

**Interfaces:**
- Consumes: `srcprep` ops, `macfx` (Task 10); `Sources`, local scan, `needs` cascade (Tasks 2-8).
- Produces (`detect`):
  - `sniff(head, size, name=None)` tests, **before** `DOS_SIZES` and the `eng` sizes:
    - `"mac-jm"`: `head[:2] == b"JM"`, `jm_header` parses, `file_len == size`, `unpacked_len <= JM_CAP`
      (`JM_CAP = 4 << 20`).
    - `"mac-fbit-raw"`: `head[2:6] == b"fbit"`.
    - `"mac-htbl-raw"`: `u32 at 0 == 204` and `size in (8 + 204 + 9400, 8 + 204 + 9400 + 204)` (9,612 or 9,816;
      design issue 1).
  - `_mac_entries(..., local)` produces the rows of the spec 9.2 table for `mac-fbit3`, `mac-htbl` and
    `mac-suitcase`, and the `other` row.
    - JM: the scan unpacks in memory, classifies the fork, and the entry keeps `prep=[{"op": "mac-fbit3"}]`.
    - A raw `fbit` of type 3: `mac-fbit3` with `prep=[{"op": "mac-fbit3"}]`.
    - A raw HTBL file: `mac-htbl` with no prep.
    - A fork holding **both** `fbit` 17408-17410 and `HTBL` 1: two entries.
    - `mac` dicts as in the table. `sizes=[H]`, `sizes_fixed: True`. `family = _stem(rel)`.
  - With `local=False`, every one of these files is today's single `other` entry "not converted here (local-only
    mode)". A raw `fbit`/HTBL/JM file that is not a container gives the same label.
  - `_coverage_of_entry` returns the fixed coverage for `mac-fbit3` (`{"ascii": 0, "ks2350": 2350, "all": 2350,
    "compat": 51}`). For `mac-htbl` and `mac-suitcase` it returns None.
  - Companions: a `mac-fbit3` entry's `companions` are the `mac-htbl` ids of the batch. Its Latin candidates
    (`latin_candidates`) are the `mac-suitcase` ids whose `mac["strikes"]` include H.
- Produces (`routes`):
  - `OP_EXT = {"rsrc-sfnt": None, "ttc-face": None, "mac-cmap": None, "instance": None, "pcf-bdf": "bdf",
    "mac-fork": "rsrc", "mac-fbit3": "fbit", "mac-htbl": "htbl1"}`, where None means `sfnt_ext`.
  - `op_ext(op, sfnt_ext) -> str`.
  - `source_commands(ops, src, work, tools_dir, sfnt_ext="ttf", last_name=None)` names intermediates
    `source-<i>.<ext>` and the last `last_name or "source.<ext>"`.
    - `mac-fork` -> `PY + [SRCPREP, "mac-fork", cur, out]`
    - `mac-fbit3` -> `PY + [tools/macfbit3.py, "fbit", cur, out]`
    - `mac-htbl` -> `PY + [SRCPREP, "mac-htbl", cur, out]`
  - Routes for `mac-fbit3`, in this order:
    - `Route("jamo", "mac fbit 7.1 direct", True, ["mac-htbl1"], [1], sizes, None, None, _mac71_commands("direct"))`
    - `Route("jamo", "mac fbit 7.1 derived", False, ["mac-htbl1"], [1], sizes, None, None, _mac71_commands("derived"))`
    - `Route("precomposed", "mac fbit 7.1 bdf + mkfont", True, [], [1], sizes, None, None, _mac71_bdf_commands)`

    The commands:
    - direct/derived: `PY + [macfbit_svf.py, "build", src, paths["htbl"], "-o", out, "--mode", mode]`, plus
      `["--latin", paths["latin"]]` when it is set.
    - bdf + mkfont: `[PY + [macfbit3.py, "bdf", src, paths["htbl"], font["family"], <work>/mac.bdf],
      PY + [mkfont.py, <work>/mac.bdf, out, "--size", str(size), "--bpp", "1", "--unicode", <_mkfont_unicode>]]`.
    The panel extras go on the last command.
- Produces (`settings`):
  - `FONT_ONLY_KEYS` and `_FONT_ONLY_DEFAULTS` gain `htbl_companion: None`. The default is the first `companions`
    id of a `mac-fbit3` font.
  - Validation: `"%s: htbl_companion %s is not a companion of this font"`. `latin_companion` of a `mac-fbit3` must be
    in `latin_candidates`, with the existing message.
  - `run_ready`: `"%s: needs an HTBL 1 table (InputBackSupport or <Name>.htbl1): add it to the sources"`.
  - `_font_layout(mac-fbit3) = "mac-htbl1"`. `_SOURCE_WORDS` gains `"mac-fbit3": "Mac fbit"`,
    `"mac-htbl": "Mac table"` and `"mac-suitcase": "Mac suitcase"`. `_SOURCE_ARTICLES` is unchanged ("a").
  - `plan_steps` plans each companion's own source step (its `prep`) **once** per companion id, before the first face
    step that uses it. The step kind is `source` and its `font` is the companion's id. The face steps carry
    `"needs": [sid, ...]`. `paths["htbl"]` / `paths["latin"]` are the prepared files (or the plain path without
    prep).
- Produces (`presets`): `ALL_SOURCES += ["mac-fbit3", "mac-htbl", "mac-suitcase"]`. `panel_argv`:
  `"mac fbit 7.1 derived"` joins the `--jset-version` label tuple. `"mac fbit 7.1 bdf + mkfont"` emits `--cell`,
  `--ascent`, `--width` and `--space-advance` (the `mkfont` branch without `--mono-hint`, `--clip-cell`,
  `--fit-cell` and `--latin`). `"mac fbit 7.1 direct"` emits nothing.
- Produces (`server`):
  - `_prepared_source` derives `target` from `routes.op_ext(ops[-1]["op"], sfnt_ext)`.
  - `_make_source_preview` gains `if source_kind == "mac-fbit3":`. It bakes with the HTBL companion's prepared path
    or answers 409 `"choose the HTBL table"`, then `self._render_preview(None, out_svf, out_png)`.
  - `_job_source_face`'s kinds gain `"mac-fbit3"`. `_kept_settings` remaps `htbl_companion` as it remaps
    `latin_companion`.
- Produces (`preview.bake_source_face(font, abs_path, layout, eng_abs, out_svf, tools_dir, extra=(), env=None, htbl_abs=None)`,
  keeping Task 6's `env`):
  for `mac-fbit3` it runs the direct route's command at the first size (no `htbl_abs`: False).
- Produces (`maker.js`):
  - `ROUTES["mac-fbit3"]` (the three rows).
  - `OPTION_VISIBLE`:
    - `"mac fbit 7.1 direct": {"1": []}`
    - `"mac fbit 7.1 derived": {"1": ["jset_version"]}`
    - `"mac fbit 7.1 bdf + mkfont": {"1": ["cell", "ascent", "width", "space_advance"]}`
  - `PREVIEW_KINDS` gains `"mac-fbit3": "bake"`, `"mac-htbl": "none"` and `"mac-suitcase": "none"`.
  - `SOURCE_WORDS` gains the three words. `LAYOUTS` gains `"mac-htbl1"`.
  - A per-font `htbl_companion` select is shown for a `mac-fbit3` font (`perFontSelect`, options = its companions'
    paths).
- Produces (drift test): `TOOL_OF_LABEL["mac fbit 7.1 bdf + mkfont"] = "ascent"`. `canonical_fonts()` adds
  `mac={"generation": 3}` to its base and a `mac-suitcase`/`mac-htbl` entry each, through `ALL_SOURCES`.
- Produces (`maker/test/inputkinds.py`): `assert_facecheck_tree(test, out_dir)`, the tree form of
  `assert_facecheck` (which takes a zip path). It copies `out_dir/svf` into a temp git checkout as `svf/`, then
  runs the same `git init/add/commit`, `manifest` and `verify` and the version-3 parse.
- Produces (`localfx.local_tree(tmp, mac=True)`): `in/mac/` holds `Seoul12.rsrc` (= `fbit3_fork(1)`),
  `InputBackSupport.rsrc` (= `htbl_fork(1)`), `Suitcase.rsrc` (= `suitcase(12)`), `ad/._Seoul12` +
  `ad/._InputBackSupport` (AppleDouble), `mb/Seoul12.bin` + `mb/IBS.bin` (MacBinary), `jm/Seoul12` (= `jm(...)`, no
  extension), `raw/Seoul12.fbit` (= `fbit3_raw`), `raw/Seoul12.htbl1` (= `htbl_raw`), `nfnt/Only.rsrc`
  (= `nfnt_only()`), and `gz/Seoul12.rsrc.gz`.

- [ ] **Step 1: Write the failing tests.**

```python
# test_detect_inputs.py LocalKindsTest (7.1 rows)
def test_mac71_entries(self):
    fonts = detect.scan(Sources("local", [mac_dir]), local=True); by = {f["path"]: f for f in fonts}
    self.assertEqual((by["Seoul12.rsrc"]["source_kind"], by["Seoul12.rsrc"]["prep"], by["Seoul12.rsrc"]["sizes"]),
                     ("mac-fbit3", [{"op": "mac-fbit3"}], [12]))
    self.assertEqual(by["ad/._Seoul12"]["prep"], [{"op": "mac-fork"}, {"op": "mac-fbit3"}])
    self.assertEqual(by["jm/Seoul12"]["prep"], [{"op": "mac-fbit3"}])
    self.assertEqual(by["raw/Seoul12.htbl1"]["source_kind"], "mac-htbl"); self.assertNotIn("prep", by["raw/Seoul12.htbl1"])
    self.assertEqual(by["ad/._InputBackSupport"]["prep"], [{"op": "mac-fork"}, {"op": "mac-htbl"}])
    self.assertEqual((by["Suitcase.rsrc"]["source_kind"], by["Suitcase.rsrc"]["mac"]["strikes"]), ("mac-suitcase", [12]))
    self.assertEqual(by["nfnt/Only.rsrc"]["source_kind"], "other")
    self.assertEqual(by["Seoul12.rsrc"]["coverage"], {"ascii": 0, "ks2350": 2350, "all": 2350, "compat": 51})
    self.assertEqual(sorted(by["Seoul12.rsrc"]["companions"]), sorted(f["id"] for f in fonts if f["source_kind"] == "mac-htbl"))
def test_mac71_in_upload_mode_is_other(self):
    # detect.scan(mac_dir) (upload): every Mac file is source_kind "other" with "not converted here (local-only mode)"
def test_mac_tags_before_size_rules(self):
    # a JM archive padded to a DOS_SIZES length (pad inside the archive body so file_len == size): sniff -> "mac-jm"
# test_routes.py MacRoutesTest
def test_mac71_routes_and_argv(self):
    # routes(mac-fbit3 entry) == labels/kinds/native in order; direct argv == PY + [tools/macfbit_svf.py, "build", SRC,
    #   HTBL, "-o", OUT, "--mode", "direct"]; with paths["latin"]: + ["--latin", L]; derived "--mode", "derived";
    #   route_for(font, "jamo", False).label == "mac fbit 7.1 direct"; route_for(font, "jamo", True, "mac fbit 7.1
    #   derived").label == "mac fbit 7.1 derived"; bdf + mkfont: two argvs, the first ".../macfbit3.py", "bdf", ...
def test_source_commands_mac_ops(self):
    argvs, last = routes.source_commands([{"op": "mac-fork"}, {"op": "mac-fbit3"}], "/s", "/w", "/t")
    self.assertEqual([a[2:4] for a in argvs], [[routes.SRCPREP, "mac-fork"], ["/t/macfbit3.py", "fbit"]])
    self.assertEqual(last, "/w/source.fbit"); self.assertEqual(argvs[0][-1], "/w/source-1.rsrc")
# test_routes.py PanelArgvTest
def test_panel_argv_mac71(self):
    # every option set: direct -> [[]]; derived -> [["--jset-version", "2"]];
    #   bdf + mkfont -> [["--cell", "18", "--ascent", "12", "--width", "18", "--space-advance", "5"]]
# test_settings.py LocalSettingsTest
def test_htbl_companion(self):
    # default == the HTBL id; a TTF id -> "f01: htbl_companion f05 is not a companion of this font"; None selected ->
    #   run_ready "f01: needs an HTBL 1 table (InputBackSupport or <Name>.htbl1): add it to the sources"
def test_suitcase_latin_only_at_a_listed_strike(self):
    # suitcase(12) is a latin candidate of the 12 px font; suitcase(14) is not
def test_companion_source_planned_once(self):
    # two mac-fbit3 fonts (Seoul12.rsrc and raw/Seoul12.fbit), one HTBL (ad/._InputBackSupport): exactly one source
    #   step with font == the HTBL id; both face steps' needs contain its id
# test_server.py
def test_page_layouts_cover_route_layouts(self):
    # every layout of every route of canonical_fonts() whose source_kind is not "dos-raw" (route.layouts) is in
    # maker.js LAYOUTS; dos-raw is exempt as in settings._route_errors (its layout is dos_layout, and canonical_fonts
    # holds a 844-ihnm candidate that LAYOUTS rightly does not list)
# test_plan_inputs.py MacEndToEndTest (local jobs through localfx.LocalBase + HTTP)
def test_mac71_direct_written_and_verified(self):
    # Seoul12.rsrc + InputBackSupport.rsrc, direct: done; `macfbit_svf.py verify <out face> <fbit3_raw file> <htbl_raw
    #   file>` exits 0 (both files written by the test into tmp/check); inputkinds.assert_facecheck_tree(self, out)
    #   passes
def test_mac71_wrapped_and_jm(self):
    # AppleDouble pair, MacBinary pair, JM font + raw htbl1: each done; their source steps' tools are
    #   ["srcprep.py mac-fork", "macfbit3.py"] / ["srcprep.py mac-fork", "srcprep.py mac-htbl"] (step_tools)
def test_companion_failure_cascades(self):
    # two 7.1 fonts sharing ad/._InputBackSupport; after detect the test replaces that file with one whose fork map is
    #   corrupt (same size) and rewrites the entry's file_id in job.json to the new lstat, so the run-time change check
    #   passes and the srcprep step itself fails: the HTBL source step failed, both face steps failed
    #   "companion source failed", no stdout.txt in their work dirs
def test_mac71_derived_and_bdf_mkfont(self):
    # derived (experimental): the face composes all 11,172 (jamoset.check on the parsed face); bdf + mkfont: the face
    #   has 2,350 syllables + 51 compatibility jamo, no ASCII
def test_mac71_gz_fork(self):
    # gz/Seoul12.rsrc.gz decompresses under fd/work/<fid>/ (assert the path in the source step's argv)
def test_mac71_source_face(self):
    # GET source/<fid>.svf with the HTBL chosen: 200, a v3 SVF; with htbl_companion None: 404 "choose the HTBL table"
```

- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement** to the interfaces, with the `maker.js` tables in the same commit.
- [ ] **Step 4: Run** `test_detect_inputs.py`, `test_routes.py`, `test_settings.py`, `test_server.py`,
  `test_plan_inputs.py -k Mac`, then `~/.local/bin/heavy python3 -m unittest discover -s tools -p
  'test_macfbit*.py'`. Expected: `OK`.
- [ ] **Step 5: Gates** G1, G2 (778), G3.
- [ ] **Step 6: Commit** `git commit -m "maker: Mac HangulTalk 7.1 type-3 fbit in local mode: detection, HTBL and suitcase companions, three routes, page tables (t_cbd14d61)"`.

Cannot verify here: a real 7.1.2 CD tree and a real `HTBL` table (`MACFBIT3_CD712`, `SVF_MAKER_REAL_MAC3`, Task 15),
and the 9,816-byte raw table size on a real file.

### Task 12: Mac HangulTalk 1.0 `fbit` (slice S5, 1.0 route group)

**Files:**
- Modify: `maker/detect.py`, `maker/routes.py`, `maker/settings.py`, `maker/presets.py`, `maker/server.py`,
  `maker/preview.py`, `maker/static/maker.js`, `maker/test/macfx.py`, `maker/test/localfx.py`, and the tests of
  Task 11

**Interfaces:**
- Produces:
  - `detect`: the `mac-fbit1` row of 9.2. `u16@0x0c != 3`, `u16@0x54 // 12 == 45`, and `fdef` 3 of at least 0x716
    bytes in the same fork. The label is `"HangulTalk 1.0 fbit (45 sets), %d x %d"` (W = set 0's `w0 * 4`, H = its
    `h`). Other fields: `prep=[{"op": "mac-fork"}]` only for AppleDouble/MacBinary, `coverage = {"ascii": 0,
    "ks2350": 2350, "all": 11172, "compat": 51}`, `mac={"generation": 1}`.
  - A raw `fbit` resource of the 1.0 shape (no fork, so no `fdef`) is `other`, labelled `"HangulTalk 1.0 fbit
    resource without its fdef: choose the font's resource fork"` (design issue 3).
  - `routes`: `Route("jamo", "mac fbit 1.0", True, ["mac-fbit-45sets"], [1], sizes, None, None, _mac10_commands)`.
    The command is `PY + [jamoset.py, "--layout", "mac-fbit-45sets", src, "--check", "-o", out]` + the extras.
  - The source step's last file for `mac-fbit1` is `<original stem>.rsrc` (`source_commands(..., last_name=)`).
    `original stem` is `_stem(rel)` with an AppleDouble `._` prefix removed and a MacBinary `.bin` suffix removed
    (`_stem` already drops the last extension): `ad/._Munjo16` -> `Munjo16.rsrc`, `mb/Munjo16.bin` -> `Munjo16.rsrc`.
  - `server._job_source_face`'s kinds gain `"mac-fbit1"` (as Task 11 does for `mac-fbit3`), or the GET is 404.
  - `settings`: `_font_layout(mac-fbit1) = "mac-fbit-45sets"`. `_SOURCE_WORDS["mac-fbit1"] = "Mac fbit"`.
    `jamo_ascent` is validated against `jamo_cell = sizes[0]` for `mac-fbit1`, and `used & {"dos raw", "hanterm",
    "mac fbit 1.0"}`.
  - `presets`: `ALL_SOURCES += ["mac-fbit1"]`. `"mac fbit 1.0"` joins the `("dos raw", "hanterm")` tuples for
    `--embolden`, `--symbols`, `--jset-version` and `--ascent`.
  - `server._bake_flags` treats `mac-fbit1` like `dos-raw`. `_make_source_preview` adds `"mac-fbit1"` to the bake
    branch. `preview.bake_source_face` adds the `mac-fbit1` route.
  - `maker.js`: `ROUTES["mac-fbit1"]`, `OPTION_VISIBLE["mac fbit 1.0"] = {"1": ["embolden", "symbols",
    "jset_version", "jamo_ascent"]}`, `PREVIEW_KINDS["mac-fbit1"] = "bake"`, `SOURCE_WORDS`, and `LAYOUTS` gains
    `"mac-fbit-45sets"`. The drift test's `TOOL_OF_LABEL["mac fbit 1.0"] = "jamo_ascent"`.

- [ ] **Step 1: Bounded fixture attempt.** Make `macfx.fbit1_fork()` pass `jamoset.py --layout mac-fbit-45sets
  --check`, following spec 12.1, within **one working session (about 2 hours)**. Record in the commit body which of
  these held:
  - (a) the fixture passes `--check`, and `test_mac10_end_to_end` runs;
  - (b) it does not, so `test_mac10_end_to_end` is `@unittest.skipUnless(os.environ.get("SVF_MAKER_REAL_MAC1"), ...)`
    on the real file, and the detection, argv, panel and refusal tests run on the header-only fixture.
- [ ] **Step 2: Write the failing tests:**

```python
def test_mac10_entry(self):        # LocalKindsTest: raw fork -> mac-fbit1, label "HangulTalk 1.0 fbit (45 sets), 16 x 16",
                                   # sizes [16], no prep; AppleDouble -> prep [{"op": "mac-fork"}]; coverage all 11172
def test_mac10_raw_resource_is_other(self):   # the bare fbit resource bytes -> other with the fdef message
def test_mac10_route_and_panel(self):         # MacRoutesTest: argv; panel_argv(every, "jamo", "mac fbit 1.0", 1) ==
                                              # [["--embolden", "--symbols", "--jset-version", "2", "--ascent", "12"]]
def test_mac10_wrapped_prepared_name(self):   # AppleDouble ._Munjo16: the source step's output "work/sNN/Munjo16.rsrc";
                                              # the face step reads it; suggested name "MUNJ16J.SVF"
def test_mac10_jamo_ascent_bound(self):       # jamo_ascent 17 on a 16 px font -> the existing "1..cell" error
def test_mac10_end_to_end(self):              # (a) or env-gated (b): done; --check passed (step stdout "check:")
```

- [ ] **Step 3: Run** them. Expected: FAIL.
- [ ] **Step 4: Implement** to the interfaces, with the tables in the same commit.
- [ ] **Step 5: Run** the Task 11 test list again, plus `~/.local/bin/heavy python3 -m unittest discover -s tools -p
  test_jamoset.py`. Expected: `OK`.
- [ ] **Step 6: Gates** G1, G2 (784), G3.
- [ ] **Step 7: Commit** `git commit -m "maker: Mac HangulTalk 1.0 fbit in local mode (jamoset mac-fbit-45sets) (t_cbd14d61)"`.

Cannot verify here: a real HangulTalk 1.0 font (`JOHAB_FONTS`, `SVF_MAKER_REAL_MAC1`) and its golden file. Under (b),
the composition itself on any 1.0 font.

### Task 13 (optional, D11): macOS named resource forks

**Files:** `maker/detect.py`, `maker/srcprep.py`, `maker/routes.py` (`OP_EXT["mac-fork-named"] = "rsrc"`),
`maker/test/test_real_inputs.py`

**Interfaces:**
- Produces: behind `sys.platform == "darwin"` only, a local scan entry whose data fork sniffs `unknown` or is empty
  gets a second look at `path + "/..namedfork/rsrc"`. When `_mac_entries` finds rows there, they get
  `prep=[{"op": "mac-fork-named"}, ...]`. `srcprep.py mac-fork-named IN OUT` reads `IN + "/..namedfork/rsrc"`.
- [ ] **Step 1: Write** `test_real_inputs.py test_named_fork`, skipped unless `sys.platform == "darwin"` and
  `SVF_MAKER_REAL_NAMEDFORK` names a file: a local job on it ends `done`. Also write
  `test_detect_inputs.test_named_fork_off_elsewhere`: with `sys.platform` patched to `"linux"`, a file with an empty
  data fork is `unknown`, and no `..namedfork` path is opened (`builtins.open` spy).
- [ ] **Step 2: Run, implement, run.** On this host the real-file test skips and the "off elsewhere" test passes.
- [ ] **Step 3: Gates** G1, G2 (786), G3. **Commit** `git commit -m "maker: macOS named resource forks in local mode, darwin only, env-gated test (t_cbd14d61)"`.

Cannot verify here: all of it (no macOS). If the reviewer prefers not to ship unverifiable code, Task 13 is dropped,
and later counts are one lower.

**Group C review gate.** One review after Tasks 9, 11, 12 (13). Focus: Review Focus 5 (drift tables). Check
`canonical_fonts()` against the spec 9.2 tables row by row, and the page's hiding rule (6.3: the typed fields are
hidden whenever the bridge exists).

---

# Group D: HWP lines, proofs, closing

Tasks 14 -> 15 -> 16 run in order.

### Task 14: HWP and hanterm lines, the 12x24 relaxation, NOTICE/README/recipes (slice S6)

**Files:**
- Modify: `maker/detect.py`, `maker/test/test_detect_inputs.py`, `maker/README.md`, `NOTICE.md`, `docs/recipes.md`,
  `maker/test/test_server.py` (a static wording test)

**Interfaces:**
- Produces (`detect.scan(..., local=True)`):
  - A file whose name ends in `.pft` (case-insensitive) and whose size is not an `eng` size (2048, 4096, 12288) is
    one `other` entry with `format: "hwp-pft"` and the label of spec 9.4: `"HWP Hangul .PFT: not read by this
    repository's tools; convert it to a 1 bpp precomposed SVF or a BDF with an external tool (recipes.md, HWP 1.x and
    2.x fonts) and add that file"`.
  - A 12x24 `eng` entry (12,288 bytes, or the HBIOS 15,360 English) stays an `eng` when **any** `dos-raw` entry is in
    the batch. A `dos-raw` entry of 24 px or more lists every 12x24 `eng` of the batch in `companions` (spec 9.4,
    D15). For dos-raw this is the only change, and 8x16 keeps the same-folder rule. hanterm and from-svf are not
    given new companion lists (design issue 2).
  - With `local=False`, both rules are today's.
- Produces (docs): the NOTICE paragraph of spec 11, word for word. `maker/README.md` section "Local mode (desktop
  app)" with the content of spec 11, including:
  - the sentence `No proprietary font is distributed: no proprietary font, bitmap or table is in this repository or in
    the maker.`
  - the sentence `the maker makes no outbound connection and sends nothing anywhere (no telemetry, no crash upload,
    no update check); the tests pin that.`
  - the Mac rows of 9.2, and the HWP line `HANGUL*.PFT is not read; ASCII.PFT is a companion`.
  - one line on the optional identity check: `SVF_RECOG_DIR` names the user's own `recog.py`. The maker's
    no-network tests do not cover that external code.
  - one line on file roots: a licence file next to a font picked as a single file is used only when it is picked
    too (or the folder is chosen).
  `docs/recipes.md` "Classic Mac Korean bitmap fonts" gets one line pointing at the maker's local mode.

- [ ] **Step 1: Write the failing tests:**

```python
def test_hwp_pft_label(self):          # local: HANGUL24.PFT (macfx.hangul_pft()) -> format "hwp-pft", the label;
                                        # upload: "unknown" (no hex check here: upload labels keep today's form)
def test_ascii_pft_from_another_folder(self):
    # local roots: hwp/ASCII.PFT (inputfx.pft_eng()), dos/<24 px DOS raw> (inputfx.dos844_24()): the eng entry is kept
    #   and is in the DOS font's companions; upload of the same tree: the eng entry is "unknown (... no DOS Johab font
    #   beside it)"
def test_8x16_eng_keeps_the_folder_rule(self):   # local: an 8x16 eng in another folder than the 16 px DOS font is unknown
def test_readme_and_notice_wording(self):
    # maker/README.md contains "No proprietary font is distributed" and "the maker makes no outbound connection";
    # NOTICE.md contains the spec 11 paragraph's first and last sentences
```

- [ ] **Step 2: Run, implement, run** `test_detect_inputs.py` and `test_server.py -k wording`. Expected: `OK`.
- [ ] **Step 3: Gates** G1, G2 (795), G3.
- [ ] **Step 4: Commit** `git add maker/detect.py maker/test maker/README.md NOTICE.md docs/recipes.md && git commit -m "maker: HWP .PFT named in local mode, 12x24 ASCII.PFT from anywhere in the batch; NOTICE and README local mode (t_cbd14d61)"`.

Cannot verify here: a real HWP `HANGUL*.PFT` or `ASCII.PFT` (`SVF_MAKER_REAL_PFT` exists and still gates it), and the
`.pft` name rule on real HWP distributions.

### Task 15: the network proofs and the real-file gates (slice S7)

**Files:**
- Modify: `maker/test/test_local.py`, `maker/test/test_real_inputs.py`

**Interfaces:** none produced.

- [ ] **Step 1: Write the tests:**

```python
def test_static_no_network_imports(self):
    # ast-parse every maker/*.py and tools/*.py except test_*.py: no Import/ImportFrom of socket (except maker/server.py),
    # ssl, smtplib, ftplib, xmlrpc*, requests, http.client, urllib.request, asyncio; no call to
    # asyncio.open_connection / socket.create_connection anywhere
def test_network_off_in_process(self):
    # wrap socket.socket.connect, connect_ex, socket.create_connection and socket.getaddrinfo for the test: record the
    # address; run the full local job of Task 8 (detect, previews, probe, run, tree, GET face) through the HTTP client;
    # every connect address is_loopback; every getaddrinfo name in ("127.0.0.1", "localhost"); the count of connects
    # equals the client's requests (each through a fresh http.client.HTTPConnection)
def test_network_off_namespace(self):
    if subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode != 0:
        self.skipTest("unshare -rn is not permitted on this host: the static scan and the in-process guard are the gate")
    # unshare -rn python3 -P -m unittest maker.test.test_local.LocalJobInNetns -> exit 0
# test_real_inputs.py
def test_real_mac1(self):   # SVF_MAKER_REAL_MAC1=<Munjo24.rsrc>: local job done, jamoset --check line in stdout,
                            # golden compared when tools/testdata/mac-fbit-golden.json exists; the no-write snapshot of
                            # Task 8 applied to the real input's folder
def test_real_mac3(self):   # SVF_MAKER_REAL_MAC3=<dir with Seoul12.fbit or the splt, and HTBL 1 (.htbl1 or a fork)>:
                            # done, macfbit_svf.py verify exits 0, facecheck; asserts the raw table length is 9,612 or 9,816
```

  `LocalJobInNetns` is a `LocalBase` subclass holding one test, the Task 8 full job. Plain discovery runs it as well,
  which is harmless and fast enough.
- [ ] **Step 2: Run** `test_local.py -k network -k static_no`, then `test_real_inputs.py`. Expected: `OK`. The netns
  test skips here with its message, and the real tests skip naming their variables.
- [ ] **Step 3: Gates** G1, G2 (801), G3.
- [ ] **Step 4: Commit** `git commit -m "maker: no-network proofs (static imports, in-process socket guard, netns where permitted) and real Mac gates (t_cbd14d61)"`.

Cannot verify here: the network namespace run (`unshare -rn` is refused on this host), the real Mac files, and the
shell's request filter (10.6, card t_f04f1355). How the gate degrades here: the in-process socket guard cannot see
tool **subprocesses**, so on this host "no network" for the tool children rests on the static import scan alone.
Neither the scan nor the guard covers the external `recog.py` that `recog_score.py` loads from `SVF_RECOG_DIR`. That
file is the user's own and outside this repository; the README says so.

### Task 16: closing gates and the audit

**Files:**
- Modify: `docs/maker-audit.md` (section 1 rows "Mac HangulTalk 1.0 fbit", "Mac HangulTalk 7.1 type-3 fbit", "HWP
  Hangul .PFT", and gap item 6, all rewritten to the new state; cite symbol names, not line numbers)

- [ ] **Step 1: Rewrite** the audit rows and gap 6. Name the task that closed each, and say for 1.0 which outcome of
  Task 12 Step 1 held.
- [ ] **Step 2: Run the closing gates:**
  - G1, then G2 (expected 801), G3.
  - `~/.local/bin/heavy make -C c check`.
  - `~/.local/bin/heavy python3 -m unittest discover -s tools -p 'test_macfbit*.py'`, and `tools -p
    test_jamoset.py`.
  - `~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py`.
  - `python3 maker/test/smoke_dom.py`.
  - `git diff --stat ce976f8 -- c/src c/include tools` (empty).

  Record each result in the commit body.
- [ ] **Step 3: Commit** `git add docs/maker-audit.md && git commit -m "docs: audit rows for Mac fbit and HWP in local mode; gap 6 closed (t_cbd14d61)"`.

**Group D review gate.** The reviewer runs the Task 16 Step 2 list and checks it against the card's closing
measurement:
- A test with synthetic Mac/HWP-like files converts via local mode: `MacEndToEndTest` (Tasks 11, 12) and
  `test_ascii_pft_from_another_folder` with a DOS raw run (Task 14).
- Network off (127.0.0.1 only) is proven by test: `LocalBindTest` (Task 1), `test_static_no_network_imports` and
  `test_network_off_in_process` (Task 15); the netns run where permitted.
- The README states that no proprietary font is distributed: `test_readme_and_notice_wording` (Task 14).
- Nothing is written outside the chosen output folder: `test_no_write_outside_output` (Task 8).
- Inputs are never copied into the data dir: `test_no_upload_copy` (Task 8).

---

## Review groups

| Group | Tasks | Order and parallelism | Review |
|---|---|---|---|
| A hardening and Sources | 1, 2, 3, 4, 5 | 1 alongside the chain 2 -> 3 -> 4 (disjoint files, separate worktrees); 5 after 1 and 4 (`server.py`) | one review after 5: token, every `realpath` check before/after |
| B local job | 6, 7, 8, 10 | 6 -> 7 -> 8 sequential (`server.py`, `jobs.py`, `settings.py`); 10 alongside in its own worktree (only `macfx.py`, `srcprep.py`, their tests), landed after 8 | one review after 8 and 10: privacy, path rules, collisions and ownership across detect/run (`job["owned"]`), sweeps |
| C page and Mac kinds | 11, 12, 13, 9 | 11 -> 12 -> 13 sequential; 9 in a separate worktree alongside, landed after 13 and rebased (disjoint `maker.js` regions; G3 at each commit) | one review after all four: drift tables, page hiding rule |
| D HWP, proofs, closing | 14, 15, 16 | sequential (14 edits `detect.py` after 11/12) | one review after 16 against the closing measurement |

This is the spec's order (section 13): S2 with S1, S2 landed first; then S3 split by endpoint; then S4 alongside S5's
wiring, with S5's unwired code drafted alongside S3; then S6, S7, and the closing commit. No two tasks edit
`settings.py`, `detect.py`, `jobs.py` or `server.py` at the same time. G2 counts assume the landing order 1-8, 10, 11,
12, 13, 9, 14, 15, 16 (Task 6 removes no test: Task 1's no-store test is written to survive it). A task that lands in another order states its observed count.

## Design issues found while planning

1. **Raw `HTBL` size.** Spec 9.2 sniffs a raw table by `size == 9816 and L1 == 204`, and 12.1's `htbl_raw` is
   `synthetic(seed)[1]`. That table is **9,612** bytes: its second length word is `len(t2)` and it has no trailing
   copy. Only `test_macfbit3.make_htbl` makes 9,816. `macfbit_svf.Htbl1` reads both. The plan's sniff accepts
   `L1 == 204` with size 9,612 or 9,816 (Task 11). Task 15's real-file gate records which one a real table has.
2. **12x24 companions of hanterm and from-svf.** Spec 9.4 says `ASCII.PFT` is "usable as `--eng` of a DOS raw,
   hanterm or `--from-svf` face ... as today", and that the companions list of a 24 px "DOS raw/hanterm/from-svf
   font" lists every 12x24 `eng` of the batch. But today only `dos-raw` entries get `eng` companions
   (`detect.py:1368-1376`): `bdf-johab` and `svf-*` always get `[]`, and the `eng` demotion asks for a DOS Johab font.
   Giving hanterm and from-svf fonts `eng` companions would be new behaviour, which the spec does not state as new.
   The plan relaxes D15 for `dos-raw` only (Task 14). Widening it needs a ruling.
3. **A raw HangulTalk 1.0 `fbit` resource.** Spec 9.2 says "a raw `fbit` file is a `mac-fbit1`/`mac-fbit3` entry
   without the fork step". But `jamoset.MacFbit` needs a fork holding `fbit` and `fdef` 3, so a bare 1.0 `fbit`
   resource cannot be converted. The plan makes it an `other` entry that names the missing `fdef` (Task 12).
4. **`Cache-Control` of an upload job's preview PNG.** 12.3 `test_no_store_headers` says the upload job's endpoints
   "keep `no-cache`". But 10.4 says `_job_preview` sends no `Cache-Control` at all today. The plan keeps the upload PNG
   unchanged (no header) and asserts only that it is not `no-store` (Task 1).
5. **`own_earlier` by path alone.** Under 7.3/D6, a re-run replaces any path in its previous `result.files`, whatever
   its current bytes, so it would replace a file another job wrote after the user deleted the original. And after a
   run in which the face was `identical_to` its own earlier file, that path is not in `result.files` (`written` lists
   new writes), so the next run would clash with its own file. The plan keeps D6's rule and adds two things. First,
   ownership is checked by the sha256 the job wrote (`job["owned"]`). Second, `own_earlier` paths a run found
   identical stay owned (Task 7, Review Focus 3). This is a reading of "this job wrote it", not a new rule; say so if
   the controller reads D6 otherwise.
6. **"A local kind" in 8.6.** The default text licence applies to "a local kind that has no licence file beside it".
   The plan applies it to every font of a local job without a licence file (Task 6), since every input of a local
   job is treated as possibly proprietary.
7. **Mac route layouts.** The spec gives the Mac jamo routes no `layouts`, and `settings._route_errors` checks a jamo
   layout against `route.layouts` for every kind but `dos-raw`. `maker.js` `LAYOUTS` is fixed and is not in the
   drift test. The plan names them `"mac-fbit-45sets"` (1.0) and `"mac-htbl1"` (7.1), sets `_font_layout` for both
   kinds, and adds a test that `LAYOUTS` covers every route layout (Tasks 11, 12).
8. **Host check order.** 10.2 says the `Host`/`Origin` check "stays as it is and runs first", and that the token check
   runs "before route matching". But today the `Host` check runs only for state changers and `_HOST_CHECKED` GETs,
   which are chosen **after** routing (it needs the handler name). 10.3's test wants a bad `Host` refused "on every
   route". The plan runs `_check_same_origin` on every request before routing when the token is set, and keeps
   today's order without the token (Task 1).
9. **`recover` re-enqueue against the start-up sweep.** 8.3 sweeps every local job's files directory at start
   "whatever its state", but `recover` re-enqueues `queued` jobs, whose planned `work/sNN/` and copied range files
   would be gone. The plan fails a queued **local** job as `"interrupted"` at start, so the user re-runs it and the
   steps are re-planned (Task 8).
10. **Bytecode outside the output folder.** The tools run as `python3 -P tools/X.py`. Their imports of sibling
    modules can write `tools/__pycache__/*.pyc` beside the checkout. That is not input-derived data, but it is a
    write outside the output folder that `test_no_write_outside_output` cannot see (the checkout is not under the
    test's `tmp`). The plan adds `PYTHONDONTWRITEBYTECODE=1` to a local job's tool environment (Task 7).
11. **The suggested name example.** 9.2 says `Munjo24` gives `MUNJO24J`. `naming.suggest_face_name` gives
    `MUNJ24J.SVF` (a jamo set uses the first 4 abbreviation characters). The plan's tests assert the code's form.
12. **The idle sweep needs a request clock.** 8.3 sweeps a `detected` job idle for `LOCAL_IDLE_SWEEP_S` "without a
    request" but names no store for the time of the last request. The plan keeps it in memory
    (`server.touched[job_id]`) and starts a 60 s sweeper thread. After a restart every job counts as idle, which is
    harmless: the start-up sweep already removed the directories.
13. **The run-time input check needs stored file ids.** 7.1's re-`lstat` at `POST run` compares with "the same
    `(st_dev, st_ino)` as at scan", but no entry field holds them. The plan stores `font["file_id"] = [dev, ino,
    size]` at detect (Task 6).
14. **Two sections numbered 16** (the rulings and the changes list). This is cosmetic, but the plan cites "the
    rulings (the first 16)".
15. **Licences of a file root.** Spec 8.2 item 5 runs licence detection "over the roots" with each root as the
    ceiling. For a root that is a single file, that finds nothing: a picked `/fonts/Munjo.ttf` would never see
    `/fonts/OFL.txt`. Reading the sibling without being given it would break 10.6 ("never reads a path it was not
    given"). The plan keys the "same folder" rules by the real parent directory, so file roots picked together from
    one directory pair up (the font and its `OFL.txt` picked in one `pickFiles` dialog). A font picked alone gets
    the default text licence (D7). The README and the page say "pick the licence file too, or choose the folder"
    (Tasks 2, 9, 14).
16. **Where ownership lives.** Spec 7.3 says the exemption comes from "this job's own `result.files` from its
    previous run". But a done job can only be re-run through `POST detect` and then `POST run`
    (`server.py:859, 885`), and both set `result=None` (`server.py:607-609`, `:899`). The previous run's files are
    always gone by the time `run_ready` looks. The plan keeps ownership in a top-level `job["owned"]` (path ->
    sha256) that no transition resets, and that `write_tree` updates as files land (Tasks 6, 7). This replaces the
    spec's wording, not its rule.
17. **Hard links on removable media.** Spec 7.3 and 8.5 write new names with `os.link`. That fails on FAT/exFAT and
    many SMB/NAS mounts, which are the usual way faces reach a DOS machine. The plan defines a fallback with the same
    no-clobber guarantee: claim with `O_CREAT|O_EXCL`, copy through a tmp, `os.replace` over its own claim, and
    verify by sha256 (Task 7).
18. **Pending sweeps after the output folder is replaced.** Spec 8.3's `pending-sweeps.json` is "a list of
    directory paths". A retry by path alone would delete a directory of the same name in a **new** folder at the old
    path (for example a re-created folder, or another drive mounted at the same point). The plan stores the output
    folder's `(st_dev, st_ino)` with each entry, deletes only when it still matches, and drops stale entries untouched
    (Task 8).

## Review dispositions

Three reviews of `939cf9a`: Opus (`/home/thkim/work/scratch/review-lanes/maker-local-plan/opus-report.md`:
Critical 1, Important 7, Minor 16), agy (`.../maker-local-plan-agy/out.md`: 1 critical, 2 important, 3 minor), and SOL
(two High items, relayed by the coordinator). Each finding was checked against the tree at `939cf9a`. Duplicates are
merged.

| Finding | Verified | Done |
|---|---|---|
| Opus C1 / agy 1: `POST detect` and `POST run` set `result=None`, so the run never sees the previous `result.files`/`owned` | yes (`server.py:607-609, 859, 885, 899`) | Top-level `job["owned"]` made at create (Task 6), kept by detect and run, filled by `write_tree`'s `on_landed`, read by `jobs.own_earlier(job)` in `_job_run` and the worker (Task 7). Re-runs in the tests go through `LocalBase.rerun` (detect, settings, run). New `test_detect_keeps_owned`. Design issue 16. |
| Opus I1: `bake_source_face`, `_run_probe`, `_prepared_source` start tools with no env | yes (`server.py:1077, 1188`, `preview.py:191`) | Task 6: `env` keyword on all three, `preview.py` moved to "modify", the preview test asserts a non-None env for every start. Task 11's signature keeps `env`. |
| Opus I2: `_identity` builds its own env | yes (`jobs.py:771`) | Task 7: `Worker._job_env(job)` used by every `run_command`, identity included; the env test covers the stub recogniser. |
| Opus I3: `test_page_layouts_cover_route_layouts` fails on `844-ihnm` | yes (`test_server.py:126`) | Task 11: dos-raw routes exempt, as `_route_errors` does. |
| Opus I4: Task 1's no-store test breaks once local jobs need an output folder | yes | Task 1: the test patches `Handler._no_store` on an upload job, so it holds at every task; Task 8's test covers real local jobs. |
| Opus I5: `test_no_upload_path_outside_the_upload_handlers` breaks on `_job_run`, `_job_create`, `steps/` reads | yes | Task 4 adds `Store.meta_dir`; Task 5's test forbids only hand-built upload paths and `store.path(`; `_job_run` drops `job_dir` (S1 table); Task 8 reads `steps/` through `meta_dir`. |
| Opus I6: `_kept_settings` keeps stale root indices; no `local=True` | yes (`server.py:227-268`) | Task 5: licence `root`, per-font and batch `range_root` remapped by root path (fallbacks defined), `local` passed to `defaults`; `test_kept_settings_remaps_root_indices`; Task 6 passes `local=True`. |
| Opus I7: `os.link` fails on FAT/exFAT/SMB | yes (by filesystem semantics; not testable here) | Task 7: fallback (O_EXCL claim, tmp, `os.replace`, sha256 verify), `test_write_tree_without_hard_links`; "Cannot verify" updated. Design issue 17. |
| agy 2: `collect` lacks `job_dir` for `log.md` | yes (`zipout.py:569, 598`) | Task 7: `collect(job, job_dir, files_dir, ...)`. |
| agy 3: the second conflicting job is refused by `run_ready`, not failed at write | yes (`server.py:889`) | Task 7 `test_collisions`: 400 with "already exists in svf/dos; choose another name", job stays `detected`. The write-time clash stays in `test_own_earlier_replaced_only_when_unchanged` and the two-server test. |
| agy 4 / Opus m7: `local_tree` writes 5 files, not 6 | yes | Task 6: `files == 5`, "five files" stated in `local_tree`. |
| agy 5: `LOCAL_FREE_MIN` undefined | yes | Task 2 defines it in `sources.py`; Task 7 imports it. |
| agy 6: `LocalBindTest` helper signature | yes (`ApiBase.raw` has no `srv`) | Task 1: `start` and `raw(self, srv, method, path, body=None, headers=None)` defined. |
| SOL a: pending sweep by path alone could delete an unrelated directory | yes (spec 8.3 stores paths only) | Task 8: entries carry `output_dir`, `output_id`, `job`; retry checks basename, parent, folder identity, no link; `test_pending_sweep_of_a_replaced_output_folder`. Design issue 18. |
| SOL b: a file root cannot find an adjacent `OFL.txt` | yes (`find_licences` ceiling) | Task 2: folder key = real parent dir, file-root ceiling = its parent, siblings never opened unless picked; `test_file_roots_in_one_folder_pair_up`; README line (Task 14). Design issue 15 (explicit selection chosen over sibling reading, per 10.6). |
| Opus m1: the change check covers selected fonts only | yes | Task 7: every entry a planned step reads (companions, licence file, range list); the test covers the eng companion and the licence. |
| Opus m2: `_mac_entries` label quotes `PrepError`; traceback stored in `job.json` | yes (`detect.py:674`) | Task 6: type-only Mac label, `TooLarge` named as harmless, `error` moved to `log.md` with `error_type` in `job.json`, `first_line` named as accepted metadata. |
| Opus m3: `abs_of` accepts the root itself; walk would list dir links for uploads | yes (`settings.py:1256-1260`) | Task 2: strictly under; upload walk omits dir links silently; a test for `abs_of(0, ".")`. |
| Opus m4: `os.umask` is process-global in tests | yes | Tasks 1, 6: `LocalBindTest` and `LocalBase` save and restore it. |
| Opus m5: the loopback refusal must precede `recover`/`start` | yes (`server.py:313-323`) | Task 1: raised first. |
| Opus m6: sweeps race a preview GET re-making the directory | yes | Task 8: `sweep_files` holds the job's preview locks via `store.on_sweep`. |
| Opus m8: cited names that do not exist (`#upload-panel`, `cli`, `srcprep_apply`, `walk_rel`, tree facecheck, `fond`, `_nfnt` rows, `_fork` home) | yes | Tasks 6, 9, 10, 11: `walk_rel` and `assert_facecheck_tree` defined, `#upload-panel` wrapper specified, `cli` helper defined, pseudo-call replaced, FOND built inline as `TestLatin` does, 5-row NFNT stated, builder homes named. |
| Opus m9: probe `.json` goes through `_send`, not `_serve_bytes` | yes (`server.py:1073`) | Task 1: its own `no_store` branch. |
| Opus m10: `_stem("ad/._Munjo16")` keeps `._` | yes (`detect.py:183`) | Task 12: `._` and `.bin` stripped for the prepared name. |
| Opus m11: `_job_source_face` lacks `mac-fbit1` | yes (`server.py:1108`) | Task 12 adds it. |
| Opus m12: counts off; Task 9's landing point ambiguous | yes | Counts recomputed (693 ... 801); Task 9 lands after Task 13 everywhere. |
| Opus m13: parallel lanes in one tree | yes | Groups A, B, C: each parallel lane in its own worktree, rebased before landing. |
| Opus m14: a self-comparing test; a fragile note assertion | yes | Task 2: the self-comparison replaced by the file-root test, the unmodified detect tests named as the proof; Task 7: a unique `uuid4` component. |
| Opus m15: the socket guard misses subprocesses; external `recog.py` | yes | Task 15 "Cannot verify" states the degradation; README line (Task 14). |
| Opus m16: `Store.list` lacks `source`/`output_id` | yes (`jobs.py:342`) | Task 6: `list()` items gain both. |
| Opus "server 176 is not a hit" | yes (harmless) | Kept: the signature changes there; the 175 count stands. |
