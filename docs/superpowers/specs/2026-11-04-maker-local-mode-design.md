# Maker local-only mode for proprietary inputs: design

Card t_cbd14d61: "maker: local-only mode for proprietary inputs (Mac fbit, HWP): no upload, path-based CLI bridge,
nothing written outside the chosen output folder". Written 2026-11-04 on branch `maker-local` of the OFL-only
repository (`svf-fonts-open`, base `ce976f8`) for a builder who has not seen the repository. Every fact below was read
from the tree or run on this host; what was not run says "not verified". Where a choice is the owner's I decided for
the builder, marked "(design call)", and collected the choice again under "Decisions needed" (section 15) with my
recommendation. The owner was not available for questions.

Read with this document: `docs/maker-audit.md` (what the maker is; section 4 "Electron shell with a Python sidecar"
and its paragraph "Local-only mode for proprietary inputs" are the brief this design answers; section 1 rows "Mac
HangulTalk 1.0 fbit", "Mac HangulTalk 7.1 type-3 fbit", "HWP Hangul .PFT"), `docs/recipes.md` ("Classic Mac Korean
bitmap fonts", "HWP 1.x and 2.x fonts", "X Window Korean fonts"), `maker/README.md`, `NOTICE.md` ("Converters for
proprietary formats"), the previous design `docs/superpowers/specs/2026-11-03-maker-controls-wasm-preview-design.md`
(the shipped controls, the byte-serving endpoints, the drift test), `tools/macfbit3.py`, `tools/macfbit_svf.py`,
`tools/jamoset.py` (the `mac-fbit-45sets` section, line 2471 on), `tools/macsfnt.py`, `maker/server.py`,
`maker/jobs.py`, `maker/detect.py`, `maker/settings.py`, `maker/routes.py`, `maker/srcprep.py`, `maker/zipout.py`.

## 1. Intent

Today every input of the maker is a browser upload: the page `PUT`s each file into the job's `upload/` directory
under the data root (`~/.local/share/svf-maker/jobs/<id>/`), the server detects, plans and runs the tools on those
copies, writes intermediates into `work/` and a zip into `out/`, and the page downloads the zip. That is right for
OFL fonts and wrong for the fonts the recipes call proprietary: classic Mac HangulTalk `fbit` fonts taken from a
Mac CD image or a resource fork, HWP printer fonts, hanterm's BDFs. Those must never be copied into the maker's job
store, never land in this repository, and their derived bitmaps must not linger in caches. The app is about to become
an Electron desktop app wrapping `maker/` with the Python server as a sidecar on 127.0.0.1 (cards t_f04f1355 shell,
t_e64a56a7 packaging, both after this card). This design adds a *local mode*: the shell hands the server paths the
user picked in native dialogs (input files or folders, an output folder); the server reads the inputs in place,
converts, and writes only into the output folder; nothing of the inputs is uploaded, copied into the data directory
or put in a zip. The two Mac `fbit` generations and the HWP-derived inputs are accepted in that mode only.

## 2. Goals

- A job whose sources are paths: the user picks files or a folder and an output folder; the maker detects from the
  paths, the page shows the same font table, settings, previews and result previews as for an upload job; the run
  writes the faces, the notes and the build record into the output folder as a tree in the `svf/` layout.
- The inputs are read only: never modified, never copied into the data directory, never zipped, never served to
  anything but the local page of the same launch.
- Every derived file (prepared sources, decompressed copies, probe faces, baked source faces, intermediates, the
  faces themselves) lives inside the chosen output folder, and the ones that are not results are removed when the
  job ends, when it is deleted, and when the server stops or starts.
- Mac HangulTalk 1.0 `fbit` (`jamoset.py --layout mac-fbit-45sets`) and HangulTalk 7.1.x type-3 `fbit` with its
  `HTBL` table (`macfbit3.py`, `macfbit_svf.py`), from a resource fork, an AppleDouble or MacBinary file, a raw
  resource, or the 7.1.2 Installer's `JM` archive; the HWP `ASCII.PFT` companion and HWP-derived BDF/SVF; hanterm
  BDF - all by path, in local mode.
- 127.0.0.1 only, proven by test; a per-launch token hook the Electron shell will use; no outbound connection ever,
  proven by test; no proprietary bytes in `job.json`, the logs or the shipped notes.
- The proofs run on synthetic fixtures built inside the tests; the real-file checks are env-gated and skip here.
- The existing gates stay green: the maker suite (682 tests at `ce976f8`), `make -C c check`, `c/src` untouched,
  `test_page_js_tables_match_python`.

## 3. Non-goals

- The Electron shell itself (window, native dialogs, the sidecar's launch, `userData`), its packaging and the tool
  entry point for a frozen sidecar: cards t_f04f1355 and t_e64a56a7. This design fixes the contract they implement
  (section 10.6) and tests the server's side of it with plain HTTP requests.
- A reader for HWP Hangul `.PFT` files: none is in this repository (recipes.md: the research tool `kfont.py` is not
  here). Local mode accepts what the recipes say the repository reads (section 9.4) and names the gap in the page.
- Reading a CD image (ISO 9660 / HFS) or a live HFS volume: no HFS reader is in the repository; the user extracts
  the volume with an external tool first (section 9.6).
- A second output format (no zip for local jobs, section 8.5), remote use, a tailnet, systemd, multi-user access
  control (section 10.1 says what the token does and does not guard).
- Any change to `c/src`, to the WASM module or to the page's drawing layer; any new pixel rule in a tool. The routes
  added here call the tools as `docs/recipes.md` does.
- Converting hanterm or HWP data that the user does not have; shipping any such file, fixture or golden data.

## 4. Constraints and facts (checked 2026-11-04 on this host unless marked)

The maker today (`ce976f8`):

- Jobs: `jobs.Store` keeps `<data_root>/jobs/<id>/job.json` plus `upload/ work/ out/` (`Store.create`); ids are 12
  hex digits (`_ID_RE`). `Worker` runs one job at a time; `run_command` runs each tool with `ENV = {PATH, HOME,
  LANG}`, no shell, `cwd` = the step's work directory, `STEP_TIMEOUT` 600 s, output capped at 4 MiB; every tool
  argv is `[sys.executable, "-P", tools/X.py, ...]` (`routes.PY`).
- Uploads: `PUT /api/jobs/<id>/files?path=` writes into `upload/` (`server._job_files`), caps `BODY_CAP` 64 MiB,
  `JOB_CAP` 256 MiB, `FILE_CAP` 2000 files; archives are unpacked on upload (`archive.unpack`). `detect.scan(upload_dir)`
  walks the directory, never follows a symlink (an `other` entry "symlink, skipped"), and gives positional ids
  `f01, f02, ...` in relative-path order.
- Every place that resolves a font's path checks it against the upload directory by `realpath`:
  `settings._upload_path` (`"%s: %s is outside the upload"`), `settings.range_spec` and `plan_steps` (a list file),
  `settings.validate`'s licence rules (`_licence_paths`, an `upload` licence), `server._check_steps` (a step's
  `output` inside the job directory, a font's `path` inside the upload), `jobs._materialized_token` /
  `Worker._plain_token` (the `.gz` rewrite, matched by realpath), `zipout._licence_bytes` (an `upload` licence).
  `plan_steps(job, job_dir, tools_dir, upload_dir, pylib)` takes the upload directory as one root.
- Steps: `step["output"]` is `"work/sNN/<NAME>"`, joined onto the job directory by the worker (`_execute`), by
  `server._job_face`, `_job_report`, `_job_identity`, `_job_zip` (all `_inside(job_dir, ...)`); `work/preview/<font
  id>*` holds the source PNG, the baked source face, the prepared source copy and the probe (`server._preview_glob`,
  dropped by a settings change through `_changed_preview_fonts`, section 6.5 of the previous design).
- Output: `zipout.write_zip` collects entries `svf/<dest>/<NAME>.SVF`, the licence and the note (`<NAME>.TXT`),
  `BUILD.md` (= `log.md` plus the summary), `LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`, writes
  `out/<id>.zip` through a `.tmp` and `os.replace`; a name `svf/` already holds with other bytes is `NameClash`, with
  equal bytes the step is marked `identical_to`. `GET /api/jobs/<id>/zip` serves it.
- Notes and logs: `naming.note_text` puts one line per command (`shlex.join(argv)`, so **absolute paths** of the
  upload and the work directory appear in the note; `zipout.note_commands` writes `upload/<path>` for a copy step),
  caps every line at `naming.MAX_FIELD_BYTES` = 512 bytes; `zipout.log_header` writes every font's `path`, `label`,
  family, style, sizes, coverage and effective settings; a detection failure's traceback is in `font["error"]` and
  in the log. `detect._detect_file` labels an unknown file `"unknown (%s)" % head[:8].hex()`: eight bytes of the
  file's head go into the label, hence into `job.json` and the log.
- Server: `make_server(host, port, repo_dir, data_root)`; `SVF_MAKER_BIND` default `127.0.0.1:8766`, no host means
  127.0.0.1 (`_bind`); **any host is accepted** (the old tailnet use; `::1` is bound through `AF_INET6`).
  `_check_same_origin` runs on `PUT`/`POST`/`DELETE` and on the byte-serving GETs (`_HOST_CHECKED`): `Host` must be
  the bound host, `127.0.0.1`, `localhost` or `::1`, and an `Origin`, when sent, must be `http(s)` on that host and
  port (a `file://` page sends `Origin: null` and is refused). There is no token. Static files are served with
  `Cache-Control: no-cache` + `ETag`; the byte endpoints too; the probe JSON with `no-cache` only.
- `GET /api/caps` is `{"wasm", "mask_libs", "recog"}` (booleans), computed once at start (`caps.compute`); the page
  does not call it yet (`maker/README.md`).
- Network: `maker/*.py` and `tools/*.py` import no `urllib.request`, `http.client`, `requests` or socket client;
  the only `import socket` is `server.py` (the bind) (grep, this host). There is no telemetry, crash reporter or
  update check anywhere in `maker/`.
- `detect._mac_entries`: a Mac container (`.dfont`, raw fork, AppleDouble, MacBinary; `_mac_head`) with no `sfnt`
  but an `NFNT`/`FONT`/`fbit` resource gives one `other` entry labelled "Mac bitmap font (NFNT/fbit): not converted
  here (local-only mode)". `srcprep.mac_resources` guards a fork (`MAX_RESOURCES`, `MAX_BYTES`) before
  `macsfnt.resources` parses it. A 12,288-byte file is an `eng` entry (HWP `ASCII.PFT`, 12x24; `ENG_SIZES`); a
  15,360-byte one is HBIOS English when `hbios_eng_like`, else a Dokkaebi face. An `eng` entry with no DOS Johab
  font in its folder becomes `unknown` (`scan`). A 12x24 companion is refused for a face under 24 px
  (`settings._route_errors`).
- Tests: 682 `def test_` in `maker/test/test_*.py`; the last commit's gate says "Ran 682 tests OK (skipped=10)"
  (my own run of the suite is reported in section 12.5). Fixtures: `maker/test/fixtures.py`, `inputfx.py`
  (synthetic TTF/OTF/TTC/VF/Mac-cmap/PCF/eng/DOS fixtures; `fork`, `appledouble`, `macbinary` wrap a fork),
  `inputkinds.py` (`plan_batch`, `run_batch`: an in-process job without HTTP; `assert_facecheck`). The server tests
  bind `127.0.0.1:0` in-process (`test_server.py:185`) and `::1` when it binds (`:769`). Browser tests drive headless
  Chrome through `maker/test/pagedrive.mjs` (DevTools protocol over node's WebSocket, no playwright); they skip
  without `google-chrome`/`chromium-browser`, `node` or the built module. Real-file tests are gated by
  `SVF_MAKER_REAL_{TTC,TTC_FACE,MACTTF,DFONT,VF,PCF_KSC,PFT,EBDT,VECTOR}` (`test_real_inputs.py`).

The tools (what the local routes call):

- **HangulTalk 1.0 `fbit`** (`tools/jamoset.py`, `MAC_LAYOUT = "mac-fbit-45sets"`, `MacFbit`, `mac_layout`,
  `main_mac`): the source is **a raw resource fork file** holding an `fbit` resource (45 glyph sets: `u16 at 0x54 //
  12 == 45`, set descriptors from 0x56, 12 bytes each: `w0*4` = bytes per row, a 32-bit offset, `h`) and the `fdef`
  resource **id 3** of at least 0x716 bytes (the 18 lookup tables at `MAC_PLANE_TABLES`). `mac_resources(d)` parses a
  raw fork only: an AppleDouble or MacBinary wrapper must be unwrapped first (`macsfnt.resource_fork` does that).
  Command: `jamoset.py --layout mac-fbit-45sets SRC.rsrc [--symbols] [--embolden] [--ascent N] [--advance N]
  [--jset-version V] [--report F] --check -o OUT.SVF`; no `--eng`, `--base`, `--from-*` (`main_mac` refuses them).
  Output: a 1 bpp jamo set of all 11,172 syllables, cell = the font's `w x h`; `--check` composes every syllable and
  compares with the tool's own copy of the Mac rule; a golden file (`tools/testdata/mac-fbit-golden.json`) is not
  shipped. Tests on real files need `JOHAB_FONTS` (`mac/extracted/kh10_system_disk/System Folder/*.rsrc`) and the
  research renderer `mac_kfont.py`, both outside this repository; `MacFbitValidation` fakes headers only. **No
  synthetic full 1.0 font exists in the tests** (section 12.2 builds one).
- **HangulTalk 7.1.x type-3 `fbit`** (`tools/macfbit3.py`, `tools/macfbit_svf.py`): the font is an `fbit` resource
  with `u16 at 0x0c == 3` (ids 17408 Seoul, 17409 AppleMyungjo, 17410 AppleGothic), cell `h` at 0x16, 482 planes
  of `(h*h+7)//8` bytes from `0x4e + 6*n_ranges`. `macfbit3.load_fbit(data)` takes a raw `fbit` resource, a resource
  fork, **or a `JM` splt archive** (`jm_unpack`: header `JM | u32 x5 | ...`, LHA `-lh5-` stream from 0x1e, checked
  by length and checksum) and returns the resource; a `dcmp`-compressed resource is refused ("use the 7.1.2 copy").
  The composition table is `HTBL` id 1 of InputBackSupport (`load_htbl1`: a fork holding `HTBL` 1, else the data
  itself as a raw table: `u32 L1` (51 x 4 bytes), then `u32 0x2468`, then 2,350 x 4 bytes and a copy of the 51 jamo
  entries; by that arithmetic a raw table is 4 + 204 + 4 + 2401 x 4 = **9,816 bytes with `L1 == 204`** - from the
  docstring, not verified on a real file). CLI: `macfbit3.py unpack SPLT OUT` (JM -> fork), `fbit SRC OUT` (the
  resource), `info`, `sheets`, `bdf FONT HTBL NAME OUT.bdf` (2,401 glyphs, Unicode BDF, `FONT_ASCENT = h - h//6`).
  There is **no `htbl` extraction subcommand**. `macfbit_svf.py build FBIT HTBL -o OUT [--mode direct|derived]
  [--latin SUITCASE.rsrc [--latin-size N]] [--jset-version V|auto] [--jset-big] [--report F] [--classes JSON]`
  reads **raw** `fbit` and `HTBL` bytes (`Fbit3`, `Htbl1`; `load` opens the two paths as they are), and `--latin`
  parses a **raw** fork with its own `resource_fork` (a `FOND` naming an `NFNT`/`FONT` strike at the cell size).
  `direct` keeps the Mac planes as a JMAP face (KS syllables only, exact); `derived` fits a JSET of all 11,172
  (8,822 extrapolated, "never presented as Mac output"). `verify FACE FBIT HTBL` re-composes. Synthetic fixtures
  exist: `tools/test_macfbit3.py` (`make_fbit`, `make_htbl`, `resource_fork`, `jm_archive`),
  `tools/test_macfbit_svf.py` (`synthetic(seed)` -> fbit + HTBL + rule, `_nfnt`, `_fork` for a suitcase). Real
  files: `MACFBIT3_CD712` (the extracted 7.1.2 CD tree), `SVF_MAC71_INPUTS` (`<Name>.fbit` + `<Name>.htbl1`).
- **"Both generations"** therefore means: generation 1 = HangulTalk 1.0 (Korean System 4.1) `fbit` with 45 sets and
  the `fdef` driver tables, composed by rule (`jamoset.py`); generation 2 = HangulTalk 7.1.x type-3 `fbit` with 482
  planes composed by the `HTBL` table (`macfbit3.py`, `macfbit_svf.py`). They are told apart by the `fbit` header:
  `u16 at 0x0c == 3` is type 3; otherwise 45 sets at 0x54 plus an `fdef` 3 resource is generation 1.
- **HWP**: the repository reads `ASCII.PFT` (12,288 bytes, 256 glyphs of 12x24) as `jamoset.py --eng` and HBIOS
  12x24 (15,360); a precomposed 1 bpp face of the Hangul made elsewhere goes through `jamoset.py --layout 844
  --from-svf`; a BDF of the composed syllables through `bdfface.py`. It does **not** read `HANGUL*.PFT`
  (recipes.md "HWP 1.x and 2.x fonts"). No size table for those files is in the tree (not verifiable here).
- **hanterm** (`bdf-johab`, `jamoset.py --layout hanterm-johab`) and the DOS raw layouts are already upload kinds.
- `jamoset.py`'s Mac path and `macfbit_svf.py` write only `-o`/`--report`/`--sheets` paths; `macfbit3.py` "reads
  the files named on the command line and writes only the output path given" (docstrings; `--sheets` is never passed
  by the maker).

Host: Linux (no macOS resource forks, no HFS mounts), python3 with fontTools and Pillow, `node`, `google-chrome`;
`unshare` exists (`util-linux`) but whether an unprivileged user network namespace is permitted here was not tested.
No Electron. No proprietary font file of any kind.

## 5. Binding decisions (the owner, 2026-11-03/04)

1. The app becomes an Electron desktop app wrapping `maker/` with a Python sidecar on 127.0.0.1 (t_f04f1355,
   t_e64a56a7, after this card). Nothing here may assume a tailnet or systemd.
2. Proprietary fonts (classic Mac HangulTalk/fbit from a CD image or resource forks, HWP `HANGUL*.PFT`/`ASCII.PFT`,
   and the like) never leave the user's machine, are never uploaded into the job store, never copied into the
   repository; they are read from a path the user picks, converted, and the result is written only into an output
   folder the user picks.
3. The repository stays OFL-only: tests use synthetic fixtures built inside the test (`maker/test/inputfx.py`'s way);
   real-file tests are env-gated.
4. Mac `fbit` (both generations) and HWP-derived inputs are accepted in local mode only (audit, section 1 and gap 6).

## 6. What local mode is (A)

### 6.1 Choice: a mode of the existing server, not a separate CLI

(design call, D1) Local mode is a per-job source kind of the existing server, switched on for the whole process by
the per-launch token (section 10.2); there is no second program. Reasons: the page, the settings validation, the
previews (the WASM byte endpoints of the previous design), the probe, the worker and the result preview are all
HTTP-bound and would have to be duplicated or bypassed by a CLI; the shell has to talk to the server anyway (port
handshake, the page); the in-process test harness (`inputkinds.plan_batch`/`run_batch`, `make_server` on
`127.0.0.1:0`) already drives both the pipeline and the HTTP layer without a browser. The "path-based CLI bridge" of
the card is therefore two things: the sidecar's launch contract (environment and stdout handshake, section 10.6) and
the path endpoints below; both are driven by the shell, never by the page's own file inputs. A headless command
(`python3 -P maker/server.py --job PATHS... --out DIR`) is not built in this card; the functions it would call are
the ones section 8 factors out, so it can be added later without a second pipeline (D1 lists it as the alternative).

### 6.2 What the user does

In the Electron window (or, for tests, any client holding the token):

1. Picks the inputs with the shell's native dialog: one or more files, or a folder (a folder is walked, section 7.2).
2. Picks the output folder with the shell's native directory dialog (it may be empty or hold earlier results).
3. The page shows the detected fonts as today (same table, same settings, same previews, the same "edit and re-run").
4. Runs. The faces, notes and the build record are written into the output folder (section 8.5); the page's result
   previews draw the written faces; an "open folder" button asks the shell to reveal the folder (section 10.6).

In a plain browser (no shell, no token) nothing changes: uploads as today, and the local kinds keep their "not
converted here (local-only mode)" labels.

### 6.3 The job and its endpoints

A job carries `"source": "upload" | "local"` (new key; absent in old `job.json` files = `"upload"`). The state names
stay (`uploading` means "sources being registered" for a local job; the page wording changes, the API does not).

| Endpoint | Local-mode meaning |
|---|---|
| `POST /api/jobs` with JSON body `{"source": "local", "output_dir": "/abs/dir"}` | creates a local job: `output_dir` is realpath'd and checked (section 7.3); the job's files directory is made under it (section 8.3). Without a body, or `"source": "upload"`, an upload job as today. A local body when local mode is off is 403 `"local mode is off"`. |
| `PUT /api/jobs/<id>/sources` body `{"paths": ["/abs/file", "/abs/folder", ...]}` | replaces the job's source roots (state `uploading` or `detected`); each path is checked by section 7.1 and walked by 7.2; the answer is `{"roots": [...], "files": N, "bytes": M, "refused": [{"path": ..., "reason": ...}]}`. `PUT files` on a local job is 409 `"job <id> is a local job"`; `sources` on an upload job is 409 too. |
| `POST /api/jobs/<id>/detect` | for a local job scans the roots (section 8.1) instead of `upload/`. |
| `PUT settings`, `POST run`, `POST cancel`, `DELETE` | unchanged in shape; the path checks resolve against the roots and the files directory (section 8.2). `DELETE` removes the metadata directory and the job's files directory under the output folder, never the results. |
| `GET /api/jobs/<id>` | adds `"source"`, `"output_dir"`, `"roots"` and, when done, `result.written` as output-folder-relative paths. |
| `GET .../zip` | 404 `"a local job writes a folder"` (section 8.5). |
| `GET .../face/<step>.svf`, `report/`, `identity/`, `probe/`, `source/`, `preview/` | as today; a done local job's face is read from the output folder (section 8.4); every byte answer of a local job carries `Cache-Control: no-store` (section 10.4). |
| `GET /api/caps` | gains `"local": bool` (the token is set). |

The page (`maker/static/maker.js`, `index.html`) reads `caps.local` at load. When true, the "upload" panel becomes a
"sources" panel: a read-only list of the chosen roots, buttons "choose files", "choose folder", "output folder" that
call the shell bridge (section 10.6) when `window.svfMaker` exists, and - so that a test or a developer without the
shell can drive it - a `<textarea id="source-paths">` and an `<input id="output-dir">` for typed absolute paths; a
"detect" button creates the job (`POST /api/jobs` with the output folder), `PUT`s the sources and `POST`s detect.
After a run the status line says "written to <output_dir>" and the "download zip" link is replaced by "open folder".
The per-font table shows the root-relative path and the root's name (section 7.2), never the full path twice. The
page sends no token header itself (the shell adds it, section 10.2).

## 7. The path model (B)

### 7.1 Which paths are accepted

A source path or output folder sent by the client is accepted only if all of these hold (checked in `PUT sources`
and `POST /api/jobs`, re-checked under the job lock at `POST run`):

- it is an absolute path (`os.path.isabs`), at most 4,096 bytes in UTF-8, with no NUL;
- `os.path.lexists` and it is not a symlink itself (`os.path.islink` false), and `os.path.realpath(path) == path`
  after normalisation, i.e. **no component of it is a symlink** (the shell's dialogs return real paths; a symlinked
  Downloads folder is refused with the reason "symlink in path: choose the real folder"), so the realpath checks
  below have one spelling to compare;
- a source is a regular file or a directory; the output folder is a directory;
- (design call, D11 alternative) no launch-time allowlist: the paths the shell hands over *are* the consent, since the
  shell's native dialog is the only way a path reaches the server in the product. An optional
  `SVF_MAKER_ROOTS=/a:/b` environment (colon-separated) bounds them further when set (every accepted path must be
  under one of them); it is for an operator who wants to pin the app to a folder, off by default;
- a source is not under the data root, not under the output folder, and the output folder is not under any source
  (reason "the output folder must not overlap an input"); the data root is never a source nor an output folder;
  `/` is refused as either;
- a source file is at most `LOCAL_FILE_CAP` = 256 MiB (larger ones are listed as `other` "too large, skipped",
  since detection reads whole files for Mac containers, DOS raw and SVF: `_read_bytes`);
- a folder walk yields at most `FILE_CAP` = 2,000 regular files and `LOCAL_BYTES_CAP` = 4 GiB (the walk stops at the
  cap and the `refused` list says "more than 2000 files: choose a smaller folder"; nothing is copied, so the upload
  byte caps do not apply, but detection time is bounded by `SCAN_COVERAGE_BUDGET_S` as today).

The server never browses on its own: it lists nothing outside the registered roots, offers no directory listing
endpoint, and `GET` of any path-derived resource goes through `_inside(root, path)` for the root the entry names.

### 7.2 Roots and relative paths

`job["roots"]` is the ordered list of accepted sources, each `{"path": "/abs/path", "kind": "file" | "dir", "name":
"<basename>"}`. A font entry of a local job carries `"root": i` (index into `roots`) and `"path"` = the path relative
to that root (`"."`'s basename for a file root: `"Seoul12.rsrc"`; for a directory root, `"System Folder/Munjo24.rsrc"`).
Ids stay positional (`f01, f02, ...`) in `(root index, relative path)` order, so `_kept_settings`'s remap by
`(path, face_index)` must include the root: the key becomes `(root, path, face_index)` for local jobs (upload jobs
keep `(path, face_index)`, root `None`).

A directory root is walked with `os.walk(followlinks=False)`; symlinks (to files or directories) are skipped and
listed under `refused` with the reason "symlink, skipped" (the scan's existing rule, now also for directory links);
device, socket and FIFO entries are skipped silently; hidden names are **not** skipped: on a Mac tree extracted to
Linux the resource forks are `._Name` AppleDouble files or `Name.rsrc` files, and the Installer's `splt` data forks
have no extension.

### 7.3 The output folder

The output folder is where every write goes. Inside it the maker creates:

- `svf/<dest>/<NAME>.SVF`, `svf/<dest>/<NAME>.TXT` (the note), `svf/<dest>/<LICENCE>.TXT` (section 8.6), and the
  three `.lines` files and `BUILD.md` at the folder's top (the zip's layout, unzipped; `zipout` entries map 1:1);
- `.svf-maker-<id>/` - the job's files directory (`work/`, and the probe/preview cache under it), present only
  while the server runs (section 8.3).

Collision rules (design call, D6): a target file that exists with equal bytes is left alone and the step is marked
`identical_to` (the zip's rule, with the output folder's own `svf/` tree as the index, section 8.5); one that
exists with other bytes is a `NameClash` and fails the job with `"name clash: svf/<dest>/<NAME>"` - **unless** the
path is in this job's own earlier `result.written` (the "edit and re-run" loop writes over what the same job wrote
before, through `<name>.tmp` + `os.replace`). `BUILD.md` and the `.lines` files are always rewritten (they are the
job's own record). Free space: `POST run` refuses with `"not enough free space in <output_dir>"` when
`shutil.disk_usage(output_dir).free` is under `LOCAL_FREE_MIN` = 256 MiB plus the sum of the input files selected
(an upper bound for the intermediates: no step writes more than its source's size times a small factor; the mkfont
probe is bounded by `MAX_GLYPHS`). Nothing else: no per-run subfolder, no timestamped names (the face names are the
user's, as today).

### 7.4 Read-only inputs

Inputs are opened for reading only (`open(path, "rb")`, Pillow/FreeType/fontTools open read-only). No tool the maker
runs takes an input path as an output (`macfbit3.py fbit SRC OUT`, `jamoset.py SRC -o OUT`, ...: the outputs are
always under the files directory). The only copies of input bytes the maker makes are the bounded, deleted
intermediates of section 8.3: a decompressed `.gz` (`preview.materialize`, under `MAX_DECOMPRESSED`), a prepared
source (`source.fbit`, `source.ttf`, a raw fork), the TTC face, the instanced VF, the PCF-as-BDF - all under
`.svf-maker-<id>/work/`, never under the data root. The list `job["roots"]` plus the entries' relative paths are the
only record of the inputs; the metadata directory never holds a byte of them (section 8.4).

## 8. The pipeline on path-based sources (C)

### 8.1 `maker/sources.py`: one object for "where the inputs are"

(design call) The refactor every other slice rests on. Today `upload_dir` is passed around as a string and each
module does its own `realpath(...).startswith(root + os.sep)`. A new module `maker/sources.py` replaces that with:

```python
class Sources:
    kind: str                         # "upload" | "local"
    roots: list[str]                  # upload: [<job_dir>/upload]; local: the accepted realpaths, in order
    def abs_of(self, font_or_rel, root=None) -> str   # the absolute path of an entry (root index + rel), or of a
                                                      # rel under the single upload root; ValueError when it does
                                                      # not resolve under its root (the H4 rule, same message)
    def inside(self, abs_path) -> bool                # realpath under one of the roots (or equal to a file root)
    def rel_of(self, abs_path) -> tuple[int, str]     # (root index, rel) for display and notes
    def walk(self) -> list[tuple[int, str, str]]      # (root index, rel, abs) of every regular file, no symlinks,
                                                      # the caps of 7.1 applied; an upload root walks as scan does
```

`settings._upload_path`, `range_spec`, `plan_steps`, `validate`/`run_ready` (licence paths), `server._check_steps`,
`_check_notes`, `_job_probe`, `_make_source_preview`, `_companion_abs`, `jobs.materialized_argv`,
`Worker._plain_source`/`_plain_token`, `zipout._licence_bytes` take a `Sources` instead of `upload_dir`. The upload
job's behaviour is unchanged by construction (`Sources("upload", [upload_dir])` reproduces every present check: the
tests of those checks stay as they are and must still pass after the slice). `jobs.Store.create(source="local",
output_dir=...)` writes `source`, `output_dir`, `roots: []`; `Store.sources(job)` builds the object.

### 8.2 Detection

`detect.scan(upload_dir)` becomes `detect.scan(sources, local=False)`: it walks `sources.walk()` and builds the same
entries; `path` is the root-relative path and `root` the index. `local=True` (a local job) changes four things:

1. the Mac bitmap containers, raw `fbit` resources, `JM` archives, `HTBL` tables and suitcases become real entries
   with routes (section 9); with `local=False` they keep today's `other` labels;
2. archives are **not** unpacked (`format: "archive"`, label "archive: extract it first, then choose the folder"; an
   upload job unpacks on upload, before the scan, so `scan` itself never unpacked anything - this is only the label);
   `.gz` single files stay as today (decompressed into the files directory on demand);
3. no file bytes go into a label: `"unknown (%s)" % head[:8].hex()` becomes `"unknown"` for local jobs (and a
   detection traceback is kept, it holds no data: Python tracebacks print no locals);
4. licence detection (`find_licences`, `is_licence_text`) runs as today over the roots (a user may keep a licence
   or a notes file beside a font); `_licence_folders` takes the roots' common path as its ceiling, never the
   filesystem root (today it is `commonpath` of the upload's files; with several roots the ceiling is each root).

Companion discovery for the local kinds (`companions`) is in section 9.3.

### 8.3 The files directory and what lives where

(design call, D3) A local job has two directories:

- the **metadata directory** `<data_root>/jobs/<id>/`: `job.json`, `job.json.tmp`, `log.md`, and after the job the
  numeric per-step reports `steps/sNN.report.json`, `steps/sNN.identity.json` (section 8.4). **No other file, ever**:
  no `upload/`, no `work/`, no `out/` are created for a local job (`Store.create` makes them for upload jobs only).
- the **files directory** `<output_dir>/.svf-maker-<id>/`: `work/sNN/` (each step's cwd, its `stdout.txt`,
  `stderr.txt`, its output face, `report.json`, `identity.json`, `dy.json`, `master.json`, prepared sources
  `source*.{fbit,ttf,otf,bdf,rsrc}`, `precomposed.svf`, `source-v3.svf`, `mac.bdf`), `work/<font id>/` (the
  decompressed `.gz` copy, the copied list file `range.txt`), `work/range-<name>.txt`, `work/preview/<font id>*`
  (the source PNG, the baked source face, the prepared copy, the probe).

So every byte derived from an input is inside the folder the user chose, and `data_root` can be backed up, synced or
inspected without ever holding a proprietary bitmap. The worker joins `step["output"]` (`"work/sNN/NAME"`, unchanged
form) onto the files directory: `Store.files_dir(job)` returns `<job_dir>` for an upload job and
`<output_dir>/.svf-maker-<id>` for a local one, and the seven joins that use `job_dir` today (`jobs._execute`,
`_read_back`, `_identity`, `_prepared_source`, `server._job_face`, `_job_report`, `_job_identity`, `_job_probe`,
`_make_source_preview`, `_prepared_source`, `zipout` reads) use it.

Lifecycle of the files directory ("precisely"):

- **made** by `POST /api/jobs` (local) - it must exist before any preview or probe;
- **swept** (removed whole, `shutil.rmtree`, after the sweep below) at: the end of `run_job` (done, failed,
  cancelled, interrupted; in a `finally`, after the tree write of 8.5 has moved the faces out), `DELETE`,
  `Worker.stop` (server shutdown: every local job's files directory that exists), `Worker.recover` (server start:
  every local job's, whatever its state - a crash left it), and `retain` (when it deletes the job);
- **re-made on demand** after a sweep by a preview, probe or source-face GET on a finished job (the user is still
  looking at the page), under the same name, swept again at the next of the points above; so after the server
  stops nothing derived remains anywhere but the results in `svf/`;
- a sweep failure (a file held open, a removed drive) is logged to `log.md` and the sweep is retried at the next
  point; it never fails a job.

Before the end-of-job sweep, two small files are **moved** into the metadata directory: `work/sNN/report.json` ->
`steps/sNN.report.json` and `work/sNN/identity.json` -> `steps/sNN.identity.json` (design call, D5): they hold the
mkfont box report (per-code-point ink boxes and cut counts: metrics, no bitmap) and the identity scores (numbers per
piece), which the page's step rows and the clipping panel read after the job. `GET report/` and `identity/` of a
local job serve from `steps/`. If the owner rules otherwise (D5) they are swept with the rest and those two GETs are
404 after the job.

The subprocess environment of a local job's tools adds `TMPDIR=<files dir>/work/tmp` (made per job) so a tool or a
library that writes a temp file (none known; Pillow and fontTools do not) writes it inside the folder too;
`HOME` stays the user's (section 12.3's test asserts it is untouched).

### 8.4 `job.json`, the log, the notes

- `job.json` (metadata directory): holds `roots` (absolute paths), every entry's root index and relative path,
  labels, family/style/version strings read from the fonts' name tables, sizes, coverage counts, the settings, the
  steps with their argvs (absolute paths into the roots and the files directory), facts and quality numbers, the
  result. **Allowed: paths and names. Not allowed: file bytes** (the `unknown (...)` hex is gone, the `error` field
  is a traceback). The owner can read the job list; it names what was converted and where.
- `log.md` / `BUILD.md`: the same header and step blocks as today (`zipout.log_header`, `log_step`), with the
  command lines as run (absolute paths) and the tools' stdout/stderr tails. (design call, D4) The paths stay: it is
  the user's own record on the user's own machine; `BUILD.md` goes into the output folder, which is theirs. Tool
  output never contains bitmap bytes (the tools print counts, sizes and names; `jamoset --check` prints the first
  differing code point as `U+XXXX`).
- the note `<NAME>.TXT` beside the faces (the one file meant to travel with a face): for a local job every argv
  token that resolves under a root or under the files directory is written as its **basename** (`note_commands`
  gets `sources` and replaces such tokens; a copy step's line names the basename too, today `upload/<path>`), so a
  note never carries a home directory or a volume name; the 512-byte line cap then holds for any path length.
  `_check_notes` at `POST run` uses the same rewrite, so what it accepts is what is written.
- stderr of the server: the 500 path prints a traceback (no data); `log_message` stays silent.

### 8.5 The run and the output tree

`plan_steps` is unchanged in logic: it gets `Sources` and the files directory (`work_root` = `<files dir>/work`).
`settings.source_ops` and `routes.source_commands` gain the Mac ops of section 9.2; `plan_steps` resolves the new
companions (`htbl_companion`, the Mac Latin suitcase) the way it resolves `latin_companion`.

`zipout._write_zip` is split into `collect(job, files_dir, index, fonts_by_id, effective, repo_dir, sources) ->
(entries, result, faces)` (everything up to building the entry dict and the `.lines`/`BUILD.md` texts; unchanged
rules) and two writers: `write_zip` (today's, upload jobs) and `write_tree(entries, output_dir, own_earlier)` (local
jobs). `write_tree` writes each entry to `<output_dir>/<entry>` through `<path>.tmp` + `os.replace`, creating
`svf/<dest>/` as needed, applying 7.3's collision rule with `own_earlier = set(previous result.written)`; on any
failure the `.tmp` files are removed and nothing already replaced is rolled back (the faces are independent files;
the result lists what landed). The index used for the identical/clash check is `naming.RepoIndex(<output_dir>/svf)`
(the class reads a directory of `<dest>/<NAME>.SVF` and `.TXT`; it is built on the output folder's own `svf/`, so a
face already in the folder with equal bytes is "identical" and the step says so) - the repository's `svf/` index is
**not** consulted for clashes of a local job (the user is not writing into the repository), but `run_ready`'s
"already exists in svf/<dest>" rule is applied to the output folder's names instead.

`result` of a local job: `{"written": ["svf/dos/SEOUL12J.SVF", ...], "skipped": [...], "failed_steps": [...],
"output_dir": "/abs/dir"}` (no `zip`). A done step gains `"written": "svf/<dest>/<NAME>.SVF"` (output-relative), or
`"identical_to"` as today. `GET face/<step>.svf` of a done local job serves `<output_dir>/<written>` (checked with
`_inside(output_dir, ...)` and that it is a regular file) - the face the user has, not a copy; if the user moved
the folder it is 404 `"face not in the output folder"`. For a job in any other state the face is in `work/` as
today.

What is written, exactly: the faces; per font with a written or identical face its note and its licence text
(8.6); `LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines` (the rows a maintainer would paste into the
repository's tables; they name faces, licence files and families, no bytes); `BUILD.md`. Nothing else: no zip (D13),
no copy of an input, no `job.json`.

### 8.6 Licence of a proprietary font

`run_ready` refuses a selected font without a licence (`"%s: no licence"`); `licence` is `{"kind": "upload" |
"repo" | "text"}`. For a local job `"upload"` is renamed in meaning only: `{"kind": "upload", "path": ...}` resolves
through `Sources` (a licence file found beside the font, section 8.2); the page keeps the "text" choice. (design
call, D7) The default for a local kind that has no licence file beside it is a `text` licence the page prefills:
`"<family>: proprietary font, converted on <date> for the owner's own use; not for redistribution."` with
`licence_name` `naming.suggest_licence_name` (it yields a `LIC...` name for a non-OFL text). The default `selected`
stays `False` for a font without a licence file (today's rule), so the user sees and confirms the text once.

## 9. The input kinds of local mode (D)

### 9.1 Which of today's kinds work by path

All of them, unchanged: TTF/OTF (static and variable, with the instance op), TTC/OTC faces, Mac TrueType with a Mac
cmap and the resource containers' `sfnt` faces (`macsfnt.py extract`/`unicode`), BDF (ISO 10646, KSC5601, johab =
hanterm, ISO 8859 companion), PCF (KSC/johab through `srcprep pcf-bdf`, others through FreeType), HBF, Windows
FNT/FON, DOS raw layouts and `johab844`, the 8x16 and 12x24 `--eng` companions (HWP `ASCII.PFT`, HBIOS), SVF v2/v3,
`.gz` single files. The tools read a path; the realpath checks go through `Sources`; the routes' argvs are built the
same way. Archives: listed, not unpacked (8.2).

### 9.2 Mac `fbit`: detection, entries, ops, routes

Sniffing from a path uses the head and the size as today (`detect.sniff(head, size)`) plus two new tags:

- `"mac-jm"`: `head[:2] == b"JM"` and `jm_header` parses with `file_len == size` and `unpacked_len <= JM_CAP` (64
  MiB). The scan unpacks it **in memory** (`macfbit3.jm_unpack`; pure Python, the 7.1.2 fonts are tens of KB) and
  classifies the fork it yields; the bytes are dropped after the file's entries are built (the `.gz` rule).
- `"mac-fbit-raw"`: `head[2:6] == b"fbit"` (a raw resource saved by `macfbit3.py fbit`).
- `"mac-htbl-raw"`: `size == 9816 and u32 at 0 == 204` (section 4's arithmetic; the builder verifies the number on
  the synthetic table of `test_macfbit3.make_htbl` and, when `MACFBIT3_CD712` is set, on the real one; if the real
  table differs the rule becomes "`L1 == 204` and `size == 8 + L1 + 4 * 2401`" and the doc line is corrected).

`_mac_entries` (a container with no `sfnt`; also a raw fork, `.dfont`, AppleDouble, MacBinary, or the fork a `JM`
archive unpacked to) inspects the resources:

| Resources found | `source_kind` | label | entry extras |
|---|---|---|---|
| `fbit` with `u16@0x0c != 3`, `u16@0x54 // 12 == 45`, and `fdef` id 3 of >= 0x716 bytes | `mac-fbit1` | "HangulTalk 1.0 fbit (45 sets), W x H" (W, H from set 0's descriptor) | `sizes=[H]`, `sizes_fixed`, `prep=[{"op": "mac-fork"}]` when the container is AppleDouble or MacBinary (jamoset reads a raw fork), `coverage = {"ascii": 0, "ks2350": 2350, "all": 11172, "compat": 51}` (a fact of the format, as `DOS_COVERAGE`), `mac={"generation": 1}` |
| `fbit` with `u16@0x0c == 3` (any id) | `mac-fbit3` | "HangulTalk 7.1 type-3 fbit, H px, N planes (needs HTBL 1)" | `sizes=[H]`, `prep=[{"op": "mac-fbit3"}]` always (the tools read the raw resource), `coverage = {"ascii": 0, "ks2350": 2350, "all": 2350, "compat": 51}`, `mac={"generation": 3, "id": rid}` |
| `HTBL` id 1 | `mac-htbl` (format `mac-rsrc`) | "HangulTalk 7.1 HTBL 1 (InputBackSupport): the composition table" | `other`-like: no route; `prep=[{"op": "mac-htbl"}]`; `mac={"table": "htbl1"}` |
| `FOND` and an `NFNT`/`FONT` | `mac-suitcase` | "Mac bitmap suitcase (FOND + NFNT): Latin strikes at N, M pt" (the plain-style sizes the FOND lists) | no route of its own; `prep=[{"op": "mac-fork"}]` when wrapped; `mac={"strikes": [sizes]}` |
| `fbit` of neither shape, or `NFNT` only without `FOND` | `other` | "Mac bitmap font (NFNT/fbit): not converted" | - |

A raw `fbit` file is a `mac-fbit1`/`mac-fbit3` entry without the fork step; a raw `HTBL` file a `mac-htbl` entry
without prep. With `local=False` (an upload job) every row above stays today's one `other` entry labelled "not
converted here (local-only mode)", so no upload job can run these routes (the drift test's `canonical_fonts()`
carries both forms).

New source ops (`settings.source_ops` adds them from `prep`; `routes.source_commands` builds the argv; both run as a
`source` step before the face steps, exactly like `rsrc-sfnt`/`ttc-face`):

| op | command | writes |
|---|---|---|
| `mac-fork` | `maker/srcprep.py mac-fork IN OUT` (new subcommand: `macsfnt.resource_fork(data)`; refuses a fork past `MAX_BYTES`) | `work/sNN/source.rsrc` - the raw fork |
| `mac-fbit3` | `tools/macfbit3.py fbit IN OUT` (exists: raw, fork or JM in) | `work/sNN/source.fbit` |
| `mac-htbl` | `maker/srcprep.py mac-htbl IN OUT` (new: `macfbit3.load_htbl1(data)`; refuses when the result is not `L1 == 204`) | `work/sNN/source.htbl1` |

(design call) The two new subcommands go into `srcprep.py` (the maker's own prep CLI, which already does `ttc-face`
and `pcf-bdf`) rather than adding an `htbl` subcommand to `macfbit3.py`; both call the tool's library functions, so
there is one parser. `source_commands` gets a `sfnt_ext` of `"rsrc"`/`"fbit"`/`"htbl1"` for these ops (the extension
table in `source_commands` becomes a dict keyed by op).

Routes (`routes.routes`), in page order, with the `OPTION_VISIBLE` row each needs:

| `source_kind` | kind / label | native | command (after the source step; `paths["src"]` is the prepared file) | options |
|---|---|---|---|---|
| `mac-fbit1` | jamo / `mac fbit 1.0` | yes | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | `["embolden", "symbols", "jset_version", "jamo_ascent"]` (the `dos raw` row: `--embolden`, `--symbols`, `--jset-version V`, `--ascent N`; `jamo_ascent` validated 1..H) |
| `mac-fbit3` | jamo / `mac fbit 7.1 direct` | yes | `macfbit_svf.py build SRC HTBL -o OUT --mode direct [--latin SUITCASE]` | `["jset_version"]` (`--jset-version V`; `jamoset`'s `--symbols`/`--embolden` do not exist here) |
| `mac-fbit3` | jamo / `mac fbit 7.1 derived` | no (experimental: 8,822 syllables are extrapolated, never Mac output) | `macfbit_svf.py build SRC HTBL -o OUT --mode derived [--latin SUITCASE]` | `["jset_version"]` |
| `mac-fbit3` | precomposed / `mac fbit 7.1 bdf + mkfont` | yes | `macfbit3.py bdf SRC HTBL <NAME> work/sNN/mac.bdf` then `mkfont.py work/sNN/mac.bdf OUT --size H --bpp 1 --unicode <range>` (a BDF strike through FreeType at its own size, the `bdf-iso10646` rule; the BDF holds no ASCII, so the Latin comes from nothing - the page's note says so; `bpps=[1]`, `sizes=[H]`) | `["cell", "ascent", "width", "space_advance"]` (the mkfont keys that apply to a bitmap strike; no `mono_hint`) |

Companions: a `mac-fbit3` entry's `companions` are every `mac-htbl` entry of the batch (the table is a separate file
and need not sit beside the font); a new per-font key `htbl_companion` (font id or null; `FONT_ONLY_KEYS`,
`_FONT_ONLY_DEFAULTS` null, default the first candidate; validated as `latin_companion` is: must be in
`companions`) feeds `paths["htbl"]`. The Mac Latin suitcase reuses `latin_companion`: for `mac-fbit3` its candidates
are the `mac-suitcase` entries whose strikes include H (the FOND's plain-style sizes; `macfbit_svf` refuses any
other), default none (`--latin` is optional). `run_ready` adds `"%s: needs an HTBL 1 table (InputBackSupport or
<Name>.htbl1): add it to the sources"` when a `mac-fbit3` font is selected without one. `plan_steps` plans the
HTBL's and the suitcase's own `source` steps (their `prep`) **before** the font's face steps when the companion is
used (they are not selected fonts; the step's `font` is the companion's id, kind `source`, as a prepared companion
would be - today a companion's `prep` is not planned: `companion_abs` is the raw path, which is right for `eng` files
and BDFs that need none; the Mac companions are the first with a `prep`).

`settings.effective_names`/`suggested_names` apply: a `mac-fbit1` or `mac-fbit3` jamo face gets a suggested name from
family + size the way a DOS raw face does (the family is the file's stem: `Munjo24` -> `MUNJO24J`); the user may
rename.

`jobs._reference` (the quality score of a jamo step): the Mac routes carry `reference=None` - `quality.measure`
compares a fit against an outline or a precomposed SVF source; the Mac routes are exact by construction and their
tools verify themselves (`--check`, `verify_direct`). The step shows the tool's own verdict line (`check:` /
`"verify": {...}` from stdout) in `facts`, as the identity line does for `dos raw`.

The previews: a `mac-fbit1`/`mac-fbit3` source has no FreeType face, so `preview.source_png` cannot draw it; the
baked source face (`GET source/<font>.svf`, `preview.bake_source_face`) is extended to these kinds: it runs the
route's own command at the first size into `work/preview/<font id>.svf` (as it does for `dos-raw`), so the page
draws the source with WASM; `_job_source_face`'s kind list gains the two kinds. A `mac-fbit3` bake needs the HTBL:
without an `htbl_companion` the bake is 409 "choose the HTBL table" (the DOS "confirm the layout" path).

### 9.3 The JM archive and the CD tree

A `JM` archive is just a container that unpacks to a resource fork (9.2); its entries are those of the fork, with
`prep=[{"op": "mac-fbit3"}]` (`macfbit3.py fbit` unpacks JM itself, so no `unpack` step is planned; the `info`
subcommand is not used). On the 7.1.2 CD the Installer's `splt` files hold the fonts; `MACFBIT3_CD712` in
`tools/test_macfbit3.py` names such an extracted tree and `test_seoul12_splt_equals_uncompressed` is the real-file
check that the JM path equals the uncompressed copy (not run here).

### 9.4 HWP-derived inputs and hanterm

- `ASCII.PFT` (12,288 bytes) and HBIOS 12x24 (15,360): `eng` entries as today; usable as `--eng` of a DOS raw,
  hanterm or `--from-svf` face of 24 px or more. In local mode the "needs a DOS Johab font beside it" demotion
  (`scan`) is relaxed to "beside it **or anywhere in the batch**" so an `ASCII.PFT` picked from an HWP folder
  pairs with a 24 px face picked elsewhere (the companions list of a 24 px DOS raw/hanterm/from-svf font lists every
  12x24 `eng` of the batch).
- `HANGUL*.PFT` (and any file matching `*.PFT` that is not a known `eng` size): a new `other` entry, format
  `"hwp-pft"`, label "HWP Hangul .PFT: not read by this repository's tools; convert it to a 1 bpp precomposed SVF or
  a BDF with an external tool (recipes.md, HWP 1.x and 2.x fonts) and add that file". Detection is by **name**
  (`.pft` extension) when the size is not an `eng` size; there is no byte rule (section 4: not verifiable here).
- A precomposed 1 bpp SVF or a KSC/ISO10646 BDF made from HWP fonts elsewhere: the existing `from-svf fit`,
  `bdfface`, `bdfface + from-svf fit` and `mkfont` routes by path. Nothing new.
- hanterm (`bdf-johab`): the existing `hanterm` route by path; nothing new. Whether a given hanterm BDF is
  proprietary is the user's question (the hanterm-font package's licence is not in this tree); local mode makes no
  licence judgement, it only never uploads.

### 9.5 The DOS kinds, SVF and everything else

By path, as 9.1. The DOS raw `--eng` companion rule "in the same folder" stays for 8x16 fonts (two 2,048-byte files
in different folders of one batch are not necessarily a pair); only the 12x24 rule relaxes (9.4).

### 9.6 Addressing a CD image or a Mac folder tree

(design call) The maker reads files, not images or volumes. A CD image (`.iso`, `.toast`, `.dmg`, HFS) is extracted
by the user with an external tool - `hfsutils` (`hmount IMAGE; hcopy -r ...`), `7z x`, or macOS itself - into a
folder; the Mac files' resource forks arrive as `._Name` AppleDouble files, `Name.rsrc` raw forks, or MacBinary
`.bin` files, all of which `_mac_head` recognises. The user then picks that folder as a source root; the walk lists
every file and the Mac rows of 9.2 appear for the forks, the `HTBL` and the suitcases. On macOS a native resource
fork is reachable as `<file>/..namedfork/rsrc`: (design call, D11) the builder may add, behind `sys.platform ==
"darwin"`, a second look at a file whose data fork sniffs `unknown` or is empty - open `path + "/..namedfork/rsrc"`
and classify those bytes with `prep=[{"op": "mac-fork-named"}]` (srcprep reads the named fork into `source.rsrc`).
Not verifiable on this host; it ships only with its own env-gated test (`SVF_MAKER_REAL_NAMEDFORK=<file>`) and is
off on other platforms. An `.iso`/`.dmg` picked as a file gets an `other` entry "disk image: extract it first".

## 10. Security and privacy (E)

### 10.1 Threat model, stated plainly

The server runs as the user, on the user's machine. What local mode guards against: (a) a web page in any browser on
the machine (cross-origin requests, DNS rebinding) reading or driving the maker; (b) a stray browser tab or another
local HTTP client of the same user reaching the job's proprietary faces without the shell's token; (c) the maker's
own files (data directory, caches, temp files, zips, notes) carrying proprietary bytes off the output folder; (d)
anything leaving the machine. What it does not guard against: another process of the same user reading the output
folder or the files directory (it can read the input fonts too), or root. The token is not a secret from the user.

### 10.2 The per-launch token (the hook the Electron shell will use)

- The sidecar is started with `SVF_MAKER_TOKEN=<32 hex chars>` in its environment (the shell generates it with
  `crypto.randomBytes(16)` per launch; a value under 16 bytes or not hex is refused at start: the server exits 2 with
  "SVF_MAKER_TOKEN: 32 hex characters"). (design call, D2) **The token's presence is the local-mode switch**: with it,
  `caps.local` is true and the local endpoints exist; without it the server is today's upload server and the local
  endpoints answer 403 `"local mode is off"`. One switch, so a server that can take paths always requires the token.
- With the token set, **every request under `/api/`** (all methods, GET included) must carry `X-Maker-Token:
  <token>` equal to the environment's (`hmac.compare_digest`); otherwise 403 `"missing or wrong token"` and nothing
  else is looked at (no job id is confirmed or denied). `/` and `/static/*` need no token (the page and its module
  are public code; the shell loads them). The `Host`/`Origin` check stays as it is and runs first.
- The shell adds the header to every request its window makes
  (`session.webRequest.onBeforeSendHeaders({urls: ["http://127.0.0.1:PORT/*"]}, ...)`), so the page never holds the
  token, it is not in the URL, not in `localStorage`, not in the HTML. `maker.js` does not change for this.
- A test's client sends the header itself. The token is never printed (the "listening on" line stays as it is) and
  never written to `job.json` or the log.

### 10.3 Loopback only, proven

- `make_server(host, ...)` with the token set **refuses a non-loopback host** (`ValueError("local mode binds
  127.0.0.1 or ::1 only")`) before the socket is made; `main` prints the message and exits 2. Loopback means
  `ipaddress.ip_address(host).is_loopback` after `_bind`'s bracket strip (`127.0.0.0/8`, `::1`); `localhost` as a
  host is resolved by `socket.getaddrinfo` and accepted only when every address is loopback. Without the token the
  server keeps today's behaviour (any host; D12 asks whether to drop it).
- Test (`test_server.py LocalBindTest`): `make_server("0.0.0.0", 0, ..., token=T)` raises; `("127.0.0.1", 0)` and
  `("::1", 0)` start and `server.socket.getsockname()[0]` is that address; a request with `Host: evil.example` is
  403 on every route including the new ones; `Origin: null` is 403 on `PUT sources`; a request without the token
  header is 403 on `GET /api/jobs`, `GET face/...`, `GET /api/caps`, and 200 on `/` and `/static/maker.js`.

### 10.4 No proprietary bytes beyond the job and the output folder

- Byte-serving GETs of a local job (`face`, `source`, `probe .svf`, `preview .png`, `report`, `identity`, and the
  `repo/face` fallback is OFL and keeps `no-cache`) answer `Cache-Control: no-store` (today `no-cache`; `no-store`
  tells the browser and Electron's disk cache not to keep a copy). `ETag`/304 still work on `no-store` responses
  within a page session (the page keeps bytes in memory, 6.5 of the previous design); the test asserts the header.
  The shell card should use an in-memory session partition (no `persist:` prefix) - noted in 10.6 as a contract line.
- The data directory never holds a derived byte (8.3); temp files of the server itself (`_receive`'s `.upload-*`)
  exist only for uploads; `Store._write`'s `job.json.tmp` holds JSON; `preview.materialize`'s `.tmp` is under the
  files directory; the subprocess `TMPDIR` is under it too (8.3).
- No zip, no download, no copy of an input (8.5); the note shows basenames (8.4); labels show no file bytes (8.2).
- `retain` (20 jobs / 7 days) deletes a local job's metadata directory and sweeps its files directory; it never
  touches `svf/` in the output folder.

### 10.5 No outbound connection, no telemetry

There is none to remove (section 4). The design pins it: (1) a static test, `test_no_network_code`, fails when any
module under `maker/` or `tools/` (the ones the maker runs: `routes.py`'s list plus `srcprep.py`, `recog_score.py`)
imports `urllib.request`, `http.client`, `socket` (except `server.py`), `ssl`, `smtplib`, `ftplib`, `xmlrpc`,
`asyncio` network APIs or `requests`; (2) the in-process guard of 12.3 wraps `socket.socket.connect`/`connect_ex`
and `socket.create_connection` during a full local job (detect, previews, probe, run, tree) and fails on any address
that is not loopback - this covers the server's own threads; (3) the subprocess tools are covered by the network
namespace run of 12.3 where the host permits it. The server never resolves a name but `localhost` at bind time.
There is no crash reporter, update check or usage ping, and `maker/README.md` says so (section 11).

### 10.6 The contract with the Electron shell (fixed here, built in t_f04f1355)

The shell:

1. starts `python3 -P maker/server.py` (or the packaged sidecar) with `SVF_MAKER_BIND=127.0.0.1:0`,
   `SVF_MAKER_TOKEN=<hex>`, `SVF_MAKER_DATA=<app.getPath("userData")>/svf-maker`, `SVF_MAKER_REPO=<resources>`, and
   reads the line `svf-maker listening on 127.0.0.1:<port>` from stdout (today's line; the port is `server.port`);
2. loads `http://127.0.0.1:<port>/` in a window whose session is in-memory (`partition: "maker"` without `persist:`)
   and adds `X-Maker-Token` to every request to that origin (`onBeforeSendHeaders`); never `file://`;
3. exposes in the page, through a preload script, `window.svfMaker = {pickSources(): Promise<string[]>,
   pickOutputDir(): Promise<string|null>, openFolder(path): Promise<void>, platform: string}` - the dialogs return
   absolute paths; the page passes them to the server unchanged; `openFolder` is `shell.showItemInFolder` /
   `shell.openPath` on the output folder the server reported (the page never invents a path: it passes back
   `job.output_dir`);
4. stops the sidecar with SIGTERM when the window closes (the server's `Worker.stop` sweeps every local job's files
   directory, 8.3, and kills the tool children - already in place).

The server never opens a dialog, never browses, never reads a path it was not given through `POST /api/jobs` or
`PUT sources`, and never writes outside the output folder and the metadata directory. The page shows the shell's
buttons only when `window.svfMaker` exists; the typed-path fields of 6.3 remain for tests.

## 11. README and NOTICE wording (F)

`NOTICE.md`, section "Converters for proprietary formats", gains one paragraph after the existing one:

> The maker (`maker/`) has a local mode for such fonts: the desktop app passes it the paths of files or folders the
> user picked and an output folder; the fonts are read in place, converted, and the faces are written only into that
> folder. In that mode nothing is uploaded, nothing is copied into the maker's data directory, no zip is made, and
> the files the conversion needs on the way are kept inside the output folder and removed when the job ends. The
> maker never connects to anything but the local page on 127.0.0.1. No proprietary font, bitmap or table is in this
> repository; the local-mode tests build synthetic inputs in the test and the checks on real files run only where an
> environment variable names the user's own copies.

`maker/README.md` gains a section "Local mode (desktop app)": what `SVF_MAKER_TOKEN` does (local mode on, every
`/api` request needs `X-Maker-Token`), the loopback rule, `POST /api/jobs {"source": "local", "output_dir"}` and
`PUT /api/jobs/<id>/sources {"paths": [...]}`, what is written into the output folder and what `.svf-maker-<id>/` is,
the Mac rows of 9.2 with their tools, the HWP line ("`HANGUL*.PFT` is not read; `ASCII.PFT` is a companion"), and
the sentence "the maker makes no outbound connection and sends nothing anywhere (no telemetry, no crash upload, no
update check); the tests pin that". `docs/maker-audit.md` section 1 rows for Mac fbit (both) and HWP `.PFT` and the
gap list item 6 are updated at the closing slice; `docs/recipes.md` "Classic Mac Korean bitmap fonts" gets one line
pointing at the maker's local mode.

## 12. Tests (G)

Fixtures are built in the tests (no new dependency); every real-file test is env-gated and skips with a message that
names the variable. Gates that must stay green: the maker suite (682 at `ce976f8`; each slice states its count),
`make -C c check` and `git diff ce976f8 -- c/src c/include` empty (nothing here touches `c/`),
`tools/test_web_picker.py`, `test_page_js_tables_match_python` (the Mac routes land with their `maker.js` rows),
`tools/test_macfbit3.py`, `tools/test_macfbit_svf.py`, `tools/test_jamoset.py` (the tools are not changed; the new
`srcprep` subcommands call them).

### 12.1 Synthetic fixtures (`maker/test/macfx.py`, new)

- `fbit3_fork(seed)`: `tools/test_macfbit_svf.synthetic(seed)` (482 planes, 12 px, a rule) wrapped by
  `tools/test_macfbit3.resource_fork({("fbit", 17408): fbit})`; `htbl_fork` = `resource_fork({("HTBL", 1): htbl})`;
  `htbl_raw` = the table bytes; `jm(fork)` = `tools/test_macfbit3.jm_archive(payload, len)` (the fixture's own LHA
  block writer; tested there); `appledouble(fork)`, `macbinary(fork)` from `inputfx`; `suitcase(size)` =
  `tools/test_macfbit_svf._fork({("FOND", 1): fond, ("NFNT", 2): _nfnt(...)})` at 12 pt.
- `fbit1_fork()`: a HangulTalk 1.0 font built in the test - an `fbit` resource (header 0x56 bytes, `u16@0x54 =
  45*12`, 45 descriptors `w0=4 (16 px), hi/off, h=16`, then the glyph data of every set) and an `fdef` 3 resource of
  0x716 bytes whose 18 tables at `jamoset.MAC_PLANE_TABLES` encode one consistent rule (e.g. `A[L] = L`, `B[V] = 2*(V
  % 8)`, `C[V] = 2*(V % 10)`, `D[T] = 0`, `Gm[V] = V`, `S[V] = 0`, `F[L] = 0`, `J[L] = 0`, `O[L] = 0`, `P[V] = 0`,
  `Q[L] = 0`, `R[T] = T`, the rest zero), with every set holding enough glyphs that `mac_compose` never indexes past a
  set (the set sizes follow from the rule). `jamoset.MacFbit` and `mac_layout` derive the layout from the rule and
  `--check` compares the composition with the same rule, so the fixture passes by construction once its sets are
  consistent. **Risk**: `mac_layout` needs the sets the rule reaches to fit JSET limits (it derives up to 20 initial
  sets for the real fonts); the simple rule above uses far fewer. If a fixture that passes `--check` cannot be made
  in a bounded effort, the slice ships the detection, argv and refusal tests on a header-only fixture and the
  end-to-end run stays env-gated (`JOHAB_FONTS`, as `tools/test_jamoset.py`); the plan records which.
- `pft_eng()`, `hbios_eng()`, `dos844_24()` (exist in `inputfx`); `hangul_pft()` = 40,000 arbitrary bytes named
  `HANGUL24.PFT` (the name-only rule); a johab BDF from `fixtures._bdf` (hanterm).
- `local_tree(tmp)`: writes the fixtures into `tmp/in/<folders>` and returns the roots; `read_only(path)` chmods
  the tree 0o555/0o444 and registers a cleanup that restores it.

### 12.2 Detection, routes, settings, page tables

| Test (file) | Proves |
|---|---|
| `test_detect_inputs.py LocalKindsTest` | with `local=True`: the 1.0 fork is `mac-fbit1` (label, sizes [16], coverage, no prep for a raw fork, `mac-fork` prep for AppleDouble/MacBinary); the 7.1 fork, the raw `fbit`, the JM archive are `mac-fbit3` with `mac-fbit3` prep; the HTBL fork and the raw 9,816-byte table are `mac-htbl`; the suitcase is `mac-suitcase` with strikes [12]; a fork with `NFNT` only is `other`; `HANGUL24.PFT` is `hwp-pft` with the message; an `ASCII.PFT` in another folder is a companion of a 24 px DOS font; with `local=False` every Mac row is today's one `other` entry and the PFT line is `unknown`; no label of a local scan contains the file's head hex |
| `test_routes.py MacRoutesTest` | the four routes of 9.2 with their exact argvs (`--mode`, `--latin` only with a suitcase, `--check`), `bpps`, `sizes`, `native`; `source_commands` for `mac-fork`, `mac-fbit3`, `mac-htbl` name `srcprep.py`/`macfbit3.py` and the output extensions; `route_for` with `experimental` for `derived` |
| `test_settings.py LocalSettingsTest` | `htbl_companion` type/offer errors, the "needs an HTBL 1 table" run_ready message, the suitcase as `latin_companion` only at a listed strike, `jamo_ascent` 1..H on `mac fbit 1.0`, the default text licence of 8.6 and its name |
| `test_srcprep.py` | `mac-fork` unwraps AppleDouble and MacBinary to the raw fork bytes and refuses an oversized fork; `mac-htbl` extracts `HTBL` 1 from a fork and passes a raw table through, refusing `L1 != 204` |
| `test_server.py test_page_js_tables_match_python` (extended `canonical_fonts()`) | the Mac entries in both `local` forms; `OPTION_VISIBLE` rows of 9.2 |
| `test_plan_inputs.py MacEndToEndTest` | a local job over `local_tree`: the 7.1 `direct` face is written, `macfbit_svf.py verify` on it exits 0 (run as a subprocess on the written face, the fixture's fbit and HTBL), `facecheck` passes; the `derived` face composes all 11,172 (`jamoset.check`); the `bdf + mkfont` face holds 2,350 syllables + 51 jamo; the 1.0 face passes `--check` (or is env-gated, 12.1); the `.gz`-wrapped fork decompresses under the files directory |

### 12.3 The proofs of the card

| Test (file) | Fixture | Proves |
|---|---|---|
| `test_local.py test_no_upload_copy` | `local_tree`, a local job through `make_server("127.0.0.1", 0, ..., token=T)` and HTTP with the token | after `PUT sources`, `POST detect`, every preview/probe/source-face GET and `POST run` to `done`: the metadata directory holds exactly `job.json`, `log.md`, `steps/` (JSON only); no file under `data_root` has the sha256 of any input; `job.json` text contains no input's head hex and no base64 of it; no `upload/`, `work/`, `out/` under `data_root/jobs/<id>/` |
| `test_local.py test_no_write_outside_output` | the same, inputs under `tmp/in` made read-only (0o555/0o444), `HOME`, `TMPDIR`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME` of the test process and of the worker's `ENV` pointed at empty sentinel dirs under `tmp` | a snapshot `(relpath, size, mtime_ns, sha256)` of `tmp/in` before equals the one after; the sentinel dirs are empty after; `tmp/out` holds exactly `svf/<dest>/{faces, notes, licence}`, `BUILD.md`, the three `.lines` and, while the server runs, nothing else (`.svf-maker-<id>/` was swept at job end: asserted absent); after `server.worker.stop()` and `server_close()` the whole `tmp` tree is: `in` (unchanged), `out` (as listed), `data/jobs/<id>/{job.json, log.md, steps/*}`, the empty sentinels - **nothing else** (an `os.walk` of `tmp` compared with the expected set) |
| `test_local.py test_sweep_points` | - | the files directory exists after `POST /api/jobs`, holds the probe after a probe GET, is gone after `run` ends, re-made by a source-face GET on the done job, gone after `DELETE`; a second server started on the same data root with a leftover `.svf-maker-<id>/` (planted by the test) removes it in `recover`; `Worker.stop` removes one that a GET re-made |
| `test_local.py test_results_served_from_output` | - | `GET face/<step>.svf` of the done job equals the bytes of `tmp/out/svf/dos/<NAME>.SVF` and carries `Cache-Control: no-store`; after the test renames the output folder the GET is 404 "face not in the output folder"; `GET zip` is 404 |
| `test_local.py test_collisions` | two runs | a re-run of the same job overwrites its own face; a second job into the same folder with the same name and other bytes fails with the clash message and leaves the first face's bytes; equal bytes mark `identical_to` |
| `test_local.py test_path_rules` | - | every refusal of 7.1 with its message: relative path, symlink root, a path under `data_root`, the output folder under a source, a source under the output folder, `/`, a non-existent path, a FIFO; `SVF_MAKER_ROOTS` set: a path outside it; `PUT files` on a local job 409; `PUT sources` on an upload job 409; `POST /api/jobs {"source": "local"}` without the token 403 |
| `test_local.py test_notes_and_logs` | - | the written note's command lines contain no `/` before a tool name's basename other than the tool path itself (every source and work token is a basename), every line <= 512 bytes with a 300-byte root path; `log.md` contains the full paths (D4); `job.json` holds `roots` and relative paths |
| `test_server.py LocalBindTest` | - | section 10.3's list |
| `test_local.py test_network_off_in_process` | the same job | `socket.socket.connect`, `connect_ex` and `socket.create_connection` are wrapped for the test's duration to assert `is_loopback` on the address and count calls; the only connections are the test client's; no `getaddrinfo` for a non-`localhost` name |
| `test_local.py test_network_off_namespace` | - | skipped unless `unshare -rn true` exits 0 (an unprivileged user netns); then the whole local job (in-process server, tools as subprocesses) runs under `unshare -rn python3 -P -m unittest ...LocalJobInNetns` with only `lo` up, and passes - proving no tool child needs a network either. Where it is not permitted the skip message says so and the in-process guard stands |
| `test_local.py test_static_no_network_imports` | - | section 10.5 (1) |
| `test_real_inputs.py` (gated) | `SVF_MAKER_REAL_MAC1=<Munjo24.rsrc>`, `SVF_MAKER_REAL_MAC3=<dir with Seoul12.fbit or the splt + HTBL1.bin>`, `SVF_MAKER_REAL_PFT` (exists) | a local job on the real file ends `done`, `facecheck` passes, `macfbit_svf.py verify` exits 0 (7.1), `jamoset --check` with the golden when `tools/testdata/mac-fbit-golden.json` exists (1.0); the no-write snapshot of 12.3 applies to the real input too |

### 12.4 Browser checks (pagedrive, no playwright)

`maker/test/test_page_dom.py LocalPageTest` (skips without Chrome, node or the module): the server is started with a
token and the test's `pagedrive.mjs` run gets a small addition - a `--header NAME:VALUE` argument it applies through
`Network.setExtraHTTPHeaders` (DevTools) so the page's requests carry the token like the shell's would (the one
change to the driver; without it every `/api` call is 403, which is the first assertion of the test). Cases: with
`caps.local` the page shows the sources panel and no `<input type=file>`; typing the fixture roots and the output
folder into the fields and clicking detect lists the Mac rows with their labels; the run ends with "written to
<dir>" and an "open folder" button that is disabled without `window.svfMaker`; a fake `window.svfMaker` injected by
the script makes "choose folder" fill the field with what the fake returns and "open folder" call the fake with
`job.output_dir`. `smoke_dom.py` is unchanged (upload mode).

### 12.5 Run state of the gates (this host)

Maker suite via `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'` at `ce976f8`, run
for this document on 2026-11-04: **Ran 682 tests in 877.5 s, OK (skipped=10)** (the 10 skips are the known ones:
no playwright, no freetype-py/uharfbuzz, no numpy, no `SVF_MAKER_REAL_*`; the wall time is the OOM guard's queue,
the audit measured 77 s unqueued). Nothing else was run: no local job exists yet, and `make -C c check` is
unaffected by construction (no file under `c/` is named by this design).

## 13. Task decomposition hint (H)

Slices, each a commit series with its tests; the drift test runs at every commit, so a slice that adds a route or an
entry shape ships the `maker.js` rows and `canonical_fonts()` in the same commit.

1. **S1 `sources.py`** - the abstraction of 8.1 threaded through settings, server, jobs, zipout for upload jobs only
   (`Sources("upload", ...)`); no behaviour change; the suite stays at 682 plus the module's own tests (abs_of /
   inside / rel_of / walk on symlinks and escapes). Risk: this touches every path check; keep each existing escape
   test and add none that relaxes one.
2. **S2 token + loopback + no-store + caps.local** (`server.py`, `caps.py`, `README`): 10.2, 10.3, `LocalBindTest`,
   the header on every `/api` request when the token is set, `caps["local"]`. Independent of S1.
3. **S3 the local job** (`jobs.Store` source/output_dir/roots/files_dir, `POST /api/jobs` body, `PUT sources`, scan
   over roots, the files directory and its sweeps, `collect`/`write_tree`, results served from the output, reports
   moved to `steps/`, `retain`, notes as basenames, labels without hex, the default text licence): sections 7, 8;
   tests 12.3 except the Mac rows. Depends on S1, S2. This is the biggest slice; split by endpoint (create+sources+
   detect / run+tree / sweeps+serving) with the no-write test growing per commit.
4. **S4 the page** (`index.html`, `maker.js`: the sources panel, the bridge hooks, "open folder", the status line;
   `pagedrive.mjs --header`; `LocalPageTest`). Depends on S3.
5. **S5 Mac kinds** (`detect.py` sniff tags and `_mac_entries` rows, `srcprep.py mac-fork`/`mac-htbl`,
   `settings.source_ops` + `htbl_companion` + run_ready, `routes.py` four routes and `source_commands`, `presets`
   `OPTION_VISIBLE` rows, `maker.js ROUTES`/`OPTION_VISIBLE`, `preview.bake_source_face` kinds, `macfx.py`,
   `MacEndToEndTest`). Two commits: 7.1 (the fixture exists) then 1.0 (the fixture is the risk, 12.1). Depends on S1
   for the path objects and on S3 for the end-to-end run in local mode; the detection/route/argv parts can be
   written in parallel with S3 behind `local=True`.
6. **S6 HWP and hanterm lines + docs** (`hwp-pft` label, the 12x24 companion relaxation, NOTICE/README/audit/recipes
   wording). Depends on S3.
7. **S7 proofs** (`test_network_off_*`, `test_static_no_network_imports`, the real-file gates `SVF_MAKER_REAL_MAC1/
   MAC3`, the sweep and collision tests if not already in S3). Depends on S3, S5.

Order: S1, then S2 in parallel with S5's detection/routes part; S3; S4 and S5's end-to-end in parallel (S4 touches
`maker.js`/`index.html`/`pagedrive.mjs`, S5's e2e touches `test_plan_inputs.py` and `preview.py`); S6; S7; a closing
commit with the gates run and the audit updated. No two slices edit `server.py` or `settings.py` at the same time.

Risks and what this host cannot verify:

- No proprietary file is here: every Mac, HWP and hanterm run in these tests is on synthetic data; the real-file
  tests are written but cannot be run before the owner sets the variables on a machine with the files.
- The HangulTalk 1.0 synthetic font (12.1) may not satisfy `mac_layout` in a bounded effort.
- The raw `HTBL` size (9,816) and the `hwp-pft` name rule are inferred, not measured.
- No Electron: the bridge (10.6) is tested only from the server's side and with a fake `window.svfMaker`; the
  `no-store` + in-memory partition advice for the shell is unverified until t_f04f1355.
- macOS named forks (9.6, D11) and an unprivileged network namespace (12.3) may be unavailable; both tests skip.
- The `Sources` refactor is security-relevant: a review should diff every `realpath` check before and after S1.

## 14. Left to the builder

- The exact shape of `maker/sources.py` (a dataclass or a class with properties), the names of the new `Store`
  helpers, where `files_dir` is stored in `job.json`.
- How `write_tree` reports partial failures (which files landed) in `result`.
- The page's layout of the sources panel, the wording of its notices, whether the typed-path fields are hidden when
  the shell bridge exists.
- The `OPTION_VISIBLE` keys for `mac fbit 7.1 bdf + mkfont` beyond the four listed (any mkfont key that applies to a
  bitmap strike may be offered; the drift test decides the final row).
- The size cap values (`LOCAL_FILE_CAP`, `LOCAL_BYTES_CAP`, `LOCAL_FREE_MIN`, `JM_CAP`): the numbers above are
  starting points; a test pins whatever is chosen.
- Whether the sweep runs on a background thread at `Worker.stop` or inline (it is a few `rmtree` calls).
- The JM in-memory unpack's time bound at scan (the LHA decoder is pure Python; the 7.1.2 fonts are small; a cap on
  `unpacked_len` is the bound chosen here).

## 15. Decisions needed (the owner)

Each with my recommendation; the design above assumes the recommendation.

- **D1. A mode of the existing server, or a separate path-based CLI?** Recommendation: the server mode (6.1); no
  CLI in this card. Alternative: `maker/server.py --job PATHS --out DIR` built on the same functions, later.
- **D2. The token as the local-mode switch.** Recommendation: `SVF_MAKER_TOKEN` set = local mode on and every `/api`
  request needs the header; no second flag. Alternative: `SVF_MAKER_LOCAL=1` plus an optional token (weaker: a
  path-taking server without a token).
- **D3. Where the job's intermediates live.** Recommendation: `<output_dir>/.svf-maker-<id>/`, swept at job end,
  delete, stop and start (8.3), so the data directory never holds a derived byte. Alternative: under the data
  directory with the same sweeps (simpler joins; a crash or a backup of `~/.local/share` can then carry bitmaps).
- **D4. Paths in `BUILD.md`/`log.md`.** Recommendation: full paths in the log and `BUILD.md` (the user's own record),
  basenames in the notes (`<NAME>.TXT`, which travel with a face). Alternative: basenames everywhere.
- **D5. The numeric per-step reports (`report.json`, `identity.json`) kept in the metadata directory after the job**
  so the step rows and the clipping panel keep working. Recommendation: keep (numbers, no bitmap). Alternative: sweep
  them; those two GETs are 404 after the job.
- **D6. Collisions in the output folder.** Recommendation: never overwrite another job's file (clash), overwrite the
  same job's own earlier output on re-run, skip equal bytes (7.3). Alternative: a per-run subfolder.
- **D7. The default licence of a proprietary font.** Recommendation: a prefilled `text` licence "proprietary, for the
  owner's own use" the user confirms (8.6). Alternative: require the user to type or pick one (today's "no licence"
  refusal with no default).
- **D8. Archives picked as sources are listed, not unpacked.** Recommendation: yes (8.2); the user extracts.
  Alternative: unpack into the files directory under `archive.LIMITS` (more code on the proprietary path).
- **D9. HWP Hangul `.PFT`.** Recommendation: no reader in this card (3; 9.4): the entry names the method. The reader
  (`kfont.py` of the research notes) would have to be brought into this repository first, with its own card.
- **D10. Uploads stay available in local mode** (a job is either upload or local; the page keeps the upload panel
  for OFL files). Recommendation: yes. Alternative: a local-mode server takes paths only.
- **D11. macOS named resource forks** (`..namedfork/rsrc`), behind `sys.platform == "darwin"` with an env-gated
  test. Recommendation: build it in S5 as an optional commit; it cannot be verified here.
- **D12. Refuse a non-loopback bind always, or only in local mode?** Recommendation: only with the token (10.3), so
  the plain server keeps its old use; if the tailnet use is dead (audit section 5 says it is out of date), refuse
  always and drop the `_Server6`-on-any-host path in the same commit.
- **D13. No zip for local jobs.** Recommendation: none (the folder is the deliverable; "open folder" instead).
  Alternative: also a zip written into the output folder (never under the data directory).
- **D14. Which Mac 7.1 routes to offer.** Recommendation: all three of 9.2 (`direct` native, `derived` behind
  `experimental`, `bdf + mkfont` for a precomposed face). Alternative: `direct` only in this card.
- **D15. The 12x24 `ASCII.PFT` companion from any folder of the batch** (9.4). Recommendation: yes for 12x24 only.

## 16. Rulings on section 15 (2026-11-04, controller)

D1 server mode, no CLI this card. D2 token presence is the single local-mode switch. D3 intermediates under
`<output_dir>/.svf-maker-<id>/`, swept at job end/delete/stop/start. D4 full paths in `log.md`/`BUILD.md`, basenames in notes.
D5 keep numeric `report.json`/`identity.json` in the metadata dir. D6 collision rule as stated. D7 prefilled
"proprietary, own use" text licence. D8 archives listed, not unpacked. D9 no HWP `.PFT` Hangul reader in this card (named
"not read by this repository" entry). D10 uploads stay available in local mode. D11 macOS named-fork reading as an optional,
env-gated, unverifiable commit. D12 non-loopback bind refused only when the token is set (the tailnet use is not a target of
the desktop direction, but is not removed here). D13 no zip for local jobs. D14 all three Mac 7.1 routes. D15 12x24
`ASCII.PFT` companion from anywhere in the batch. Rulings of the controller, reversible by editing this section and the plan.
