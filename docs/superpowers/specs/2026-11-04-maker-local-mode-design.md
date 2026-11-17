# Maker local-only mode for proprietary inputs: design

Card t_cbd14d61: "maker: local-only mode for proprietary inputs (Mac fbit, HWP): no upload, path-based CLI bridge,
nothing written outside the chosen output folder". Written 2026-11-04 on branch `maker-local` of the OFL-only
repository (`svf-fonts-open`, base `ce976f8`) for a builder who has not seen the repository. Every fact below was read
from the tree or run on this host; what was not run says "not verified". Where a choice is the owner's I decided for
the builder, marked "(design call)", and collected the choice again under "Decisions needed" (section 15) with my
recommendation. The owner was not available for questions. Revised the same day after two independent reviews
(section 17 lists every finding and what was done with it).

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
- 127.0.0.1 only (tested: loopback-only bind, a static import scan and an in-process socket guard; not the tool subprocesses, see docs/maker-audit.md section 8); a per-launch token hook the Electron shell will use; no outbound connection ever,
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
  and a per-job sidecar folder `svf-maker-<id>/` holding `BUILD.md` (= `log.md` plus the summary),
  `LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines` (`zipout.py:601-606`), writes `out/<id>.zip`
  through a `.tmp` and `os.replace`. `naming.RepoIndex.check_face(dest, name, data)` says `identical` when the
  **bytes** exist under any name in the index (`by_sha`), `clash` when the **name** exists in `dest` with other
  bytes, else `ok`; `zipout._text_entry` applies the same to notes and licences (an equal text anywhere is reused,
  a same-named other text is `NameClash`); `result.written` lists faces only. `settings.run_ready` refuses any
  face, note or licence name the index already lists in `dest` ("already exists in svf/<dest>; choose another
  name"), whatever its bytes. `GET /api/jobs/<id>/zip` serves the zip.
- Notes and logs: `naming.note_text` puts one line per command (`shlex.join(argv)`, so **absolute paths** of the
  upload and the work directory appear in the note; `zipout.note_commands` writes `upload/<path>` for a copy step),
  caps every line at `naming.MAX_FIELD_BYTES` = 512 bytes; `zipout.log_header` writes every font's `path`, `label`,
  family, style, sizes, coverage and effective settings; a detection failure's traceback is in `font["error"]` and
  in the log. `detect._detect_file` labels an unknown file `"unknown (%s)" % head[:8].hex()`: eight bytes of the
  file's head go into the label, hence into `job.json` and the log; an `unreadable: <Type>: <message>` label and
  a `; cannot prepare: <message>` suffix carry exception messages, which can quote input (a `UnicodeDecodeError`
  names the byte); `entry["licences"][].first_line` holds the first 120 characters of a `.txt` `is_licence_text`
  accepts.
- Temp files of the server process: `detect._bdf_glyphs` writes a `.gz` BDF's decompressed bytes to
  `tempfile.mkstemp()` in the **system temp directory** to parse it (`detect.py:1209`; removed in a `finally`, so a
  kill mid-parse leaves the whole font in `/tmp`); `preview.materialize` writes under the directory it is given;
  `preview.run_bounded` runs previews, probes, source conversions and bakes with `preview.ENV` (`PATH, HOME, LANG`:
  no `TMPDIR`), `jobs.run_command` with `jobs.ENV` (the same three).
- The page and the shell: nothing in the server stops the page's own JavaScript from fetching a remote URL; no
  `Content-Security-Policy` header is sent today.
- Server: `make_server(host, port, repo_dir, data_root)`; `SVF_MAKER_BIND` default `127.0.0.1:8766`, no host means
  127.0.0.1 (`_bind`); **any host is accepted** (the old tailnet use; `::1` is bound through `AF_INET6`).
  `_check_same_origin` runs on `PUT`/`POST`/`DELETE` and on the byte-serving GETs (`_HOST_CHECKED`): `Host` must be
  the bound host, `127.0.0.1`, `localhost` or `::1`, and an `Origin`, when sent, must be `http(s)` on that host and
  port (a `file://` page sends `Origin: null` and is refused). There is no token. Static files are served with
  `Cache-Control: no-cache` + `ETag`; the byte endpoints too; the probe JSON with `no-cache` only.
- `GET /api/caps` is `{"wasm", "mask_libs", "recog"}` (booleans), computed once at start (`caps.compute`); the page
  calls it once at load, for the `local` flag this branch adds (`maker/README.md`).
- The page tables and their drift test (`test_server.py test_page_js_tables_match_python`, `:869`): `ROUTES` is
  compared with `routes.routes` over `canonical_fonts()`; `OPTION_VISIBLE` is derived from the flags
  `presets.panel_argv(options, kind, label, bpp)` emits with every option set, and `panel_argv` branches on
  **exact route labels** (`"dos raw"`, `"hanterm"`, `"mkfont"`, ...: `presets.py:80-126`), so a new label emits
  nothing until it is added there; the test's `TOOL_OF_LABEL` maps a label that emits `--ascent` to its key and
  raises `KeyError` for an unknown one; `PREVIEW_KINDS` must list exactly `presets.ALL_SOURCES` and its `bake`
  kinds must equal the literals in `server._make_source_preview`; `SOURCE_WORDS`/`SOURCE_ARTICLES` must equal
  `settings._SOURCE_WORDS`/`_SOURCE_ARTICLES`. `srcprep._apply_op` raises `"unsupported prep op"` for an unknown
  op, and `scan` runs `prepared_bytes` on every entry with `prep` (so an unknown op gives "; cannot prepare" and
  coverage None); `_coverage_of_entry` returns None for a kind it does not list; `server._prepared_source` derives
  the prepared file's extension itself (`bdf`/`otf`/`ttf`).
- `sniff` tests `DOS_SIZES` and the `eng` sizes before `_mac_head` (`detect.py:118-123`).
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
  (8,822 extrapolated, "never presented as Mac output"); **`--jset-version` has no effect on `--mode direct`
  without `--with-jset`** (`macfbit_svf.py:1180-1199`: the JSET is only the JMAP's fallback). `verify FACE FBIT
  HTBL` re-composes. `jamoset.mac_golden` keys the golden file by the **source file's stem** (`Munjo24.rsrc` ->
  `munjo24`, `jamoset.py:2710`). Synthetic fixtures
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
`unshare -rn true` fails here ("write failed /proc/self/uid_map: Operation not permitted"), so an unprivileged
network namespace is not available on this host. The server uses `os.killpg` and `start_new_session`: it is
POSIX-only today (Linux and macOS are the targets; Windows is not). No Electron. No proprietary font file of any kind.

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
"sources" panel: a read-only list of the chosen roots and three buttons "choose files", "choose folder", "output
folder" that call `window.svfMaker.pickFiles()`, `pickFolder()`, `pickOutputDir()` (section 10.6; a cancelled dialog
resolves to `[]`/`null` and changes nothing). When `window.svfMaker` is **absent** (a test or a developer without
the shell) the buttons are hidden and a `<textarea id="source-paths">` and an `<input id="output-dir">` take typed
absolute paths instead; when the bridge exists those two fields are hidden (decided here, not left open: the
consent argument of 7.1 rests on the dialog being the only way in the product). A "detect" button creates the job
(`POST /api/jobs` with the output folder), `PUT`s the sources and `POST`s detect. After a run the status line says
"written to <output_dir>" and the "download zip" link is replaced by "open folder" (`openOutputFolder()`, enabled
only with the bridge). The per-font table shows the root's name and the root-relative path (section 7.2). The page
sends no token header itself (the shell adds it, section 10.2) and makes no request to any other origin (10.5).

## 7. The path model (B)

### 7.1 Which paths are accepted

A source path or output folder sent by the client is accepted only if all of these hold (checked in `PUT sources`
and `POST /api/jobs`, re-checked under the job lock at `POST run`):

- it is an absolute path (`os.path.isabs`), at most 4,096 bytes in UTF-8, with no NUL;
- `os.path.lexists` and **the path itself is not a symlink** (`os.path.islink` false); it is then resolved once,
  `root = os.path.realpath(path)`, and that spelling is stored and used for every later check (so `/home ->
  /var/home` on an OSTree system, macOS `/tmp -> /private/tmp` and firmlinks, a symlinked `Downloads` are all
  accepted: the chosen folder is what is read, wherever it really is). Symlinks **below** a root are skipped by the
  walk (7.2), never followed;
- a source is a regular file or a directory; the output folder is a directory. Its identity is recorded as
  `(st_dev, st_ino)` in `job["output_id"]` at `POST /api/jobs`; every later write, sweep or re-make first
  `os.stat`s the output folder and requires the same pair (an unmounted USB drive whose mount point reappears on the
  system disk, or a folder removed and re-created, fails with `"output folder is gone or changed"`; the job is
  `failed` with that error, and nothing is written). The output folder itself is **never** created by the maker;
  only children under it;
- (design call, D11 alternative) no launch-time allowlist: the paths the shell hands over *are* the consent, since the
  shell's native dialog is the only way a path reaches the server in the product. An optional
  `SVF_MAKER_ROOTS=/a:/b` environment (colon-separated) bounds them further when set (every accepted path must be
  under one of them); it is for an operator who wants to pin the app to a folder, off by default;
- a source is not under the data root and does not contain it, not under the output folder, and the output folder
  is not under any directory source (reason "the output folder must not overlap an input"); the data root is never a
  source nor an output folder; `/` is refused as either. These overlap checks are done by **inode**, not by string:
  for each pair the ancestors of one (itself, its parent, ... up to `/`, by `os.stat` of each) are compared with the
  other's `(st_dev, st_ino)`, so a case-insensitive filesystem or a bind mount cannot hide an overlap (the string
  prefix check is kept as a first, cheap refusal);
- at `POST run` every entry file is `lstat`ed again (still a regular file, same `(st_dev, st_ino)` as at scan,
  size unchanged); one that changed is refused with `"%s: the input changed since detection: detect again"`;
- a source file is at most `LOCAL_FILE_CAP` = 256 MiB (larger ones are listed as `other` "too large, skipped",
  since detection reads whole files for Mac containers, DOS raw and SVF: `_read_bytes`);
- a folder walk yields at most `FILE_CAP` = 2,000 regular files and `LOCAL_BYTES_CAP` = 1 GiB (the walk stops at the
  cap and the `refused` list says "more than 2000 files: choose a smaller folder"; nothing is copied, so the upload
  byte caps do not apply, but `POST detect` reads synchronously in a request thread, so the byte cap bounds that
  read and detection time is bounded by `SCAN_COVERAGE_BUDGET_S` as today).

The server never browses on its own: it lists nothing outside the registered roots, offers no directory listing
endpoint, and `GET` of any path-derived resource goes through `_inside(root, path)` for the root the entry names.

### 7.2 Roots and relative paths

`job["roots"]` is the ordered list of accepted sources, each `{"path": "/abs/path", "kind": "file" | "dir", "name":
"<basename>"}`. A font entry of a local job carries `"root": i` (index into `roots`) and `"path"` = the path relative
to that root (`"."`'s basename for a file root: `"Seoul12.rsrc"`; for a directory root, `"System Folder/Munjo24.rsrc"`).
Ids stay positional (`f01, f02, ...`) in `(root index, relative path)` order, so `_kept_settings`'s remap by
`(path, face_index)` must include the root: the key becomes `(root realpath, path, face_index)` for local jobs
(the root's **path string**, not its index, so that adding, removing or reordering roots in a later `PUT sources`
keeps the per-font settings of the roots that stayed; upload jobs keep `(path, face_index)`). `_kept_settings` also
remaps `htbl_companion` (9.2) as it remaps `latin_companion`. Inside `detect.scan` every table keyed by `rel` today
(`abs_of`, `groups`, `dos_folders`, the `eng` folder rule, the licence folders) is keyed by `(root, rel)`, so two
directory roots that each hold top-level files are two folders, not one `""` folder (an 8x16 `eng` pairs only with a
DOS font of the same root and folder, 9.5).

A directory root is walked with `os.walk(followlinks=False)`; symlinks (to files or directories) are skipped and
listed under `refused` with the reason "symlink, skipped" (the scan's existing rule, now also for directory links);
device, socket and FIFO entries are skipped silently; hidden names are **not** skipped: on a Mac tree extracted to
Linux the resource forks are `._Name` AppleDouble files or `Name.rsrc` files, and the Installer's `splt` data forks
have no extension.

### 7.3 The output folder

The output folder is where every write goes. Inside it the maker creates:

- `svf/<dest>/<NAME>.SVF`, `svf/<dest>/<NAME>.TXT` (the note), `svf/<dest>/<LICENCE>.TXT` (section 8.6) - the
  zip's face entries, unzipped;
- `build-<id>/BUILD.md`, `build-<id>/LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines` - the zip's
  per-job sidecar folder (`svf-maker-<id>/` in the zip), renamed so it is not confused with the files directory; a
  second job into the same folder keeps the first job's record;
- `.svf-maker-<id>/` - the job's files directory (`work/`, and the probe/preview cache under it), present only
  while the server runs (section 8.3).

Collision rules (design call, D6), in the terms `naming.RepoIndex.check_face` uses, with the output folder's own
`svf/` tree as the index (`RepoIndex(<output_dir>/svf)`, section 8.5): bytes that already exist under **any** name
in that tree make the step `identical_to` that path and nothing is written for it (the zip's rule; the note names
the existing file); a **name** that exists in `dest` with other bytes is a `NameClash` (`"name clash:
svf/<dest>/<NAME>"`, the job fails before any face is replaced) - **unless** that path is in this job's own
`result.files` from its previous run (every file the job wrote: faces, notes, licences - not only the faces
`result.written` lists today), in which case it is replaced through `<name>.tmp` + `os.replace`. The same
`own_earlier` set is passed into `settings.run_ready` (its "already exists in svf/<dest>; choose another name" rule,
`_clash_errors`, `_licence_present_ok`) and into `zipout._text_entry`, so the "edit and re-run" loop passes
validation at `POST run` and the note (which carries the date and the command lines, so it differs on every re-run)
is rewritten rather than refused. A new name is written with `os.link(tmp, target)` (which fails if the target
appeared since the check) and only an `own_earlier` path with `os.replace`, so two launches writing one folder
cannot silently cross. `build-<id>/*` is always rewritten (the job's own record). **One active job per output
folder**: `POST /api/jobs` and `POST run` refuse with 409 `"output folder is in use by job <id>"` while another job
of this server is `uploading`, `detected`, `queued` or `running` with the same `output_id` (a finished job releases
it; the user may still create a new job into the folder, where the clash rule governs). Free space: `POST run`
refuses with `"not enough free space in <output_dir>"` when `shutil.disk_usage(output_dir).free` is under
`LOCAL_FREE_MIN` = 256 MiB plus the sum of the input files selected (an upper bound for the intermediates: no step
writes more than its source's size times a small factor; the mkfont probe is bounded by `MAX_GLYPHS`). A disk-full
or any `OSError` inside `write_tree` fails the job with the error and `result.files` listing what landed. Nothing
else: no per-run subfolder, no timestamped names (the face names are the user's, as today).

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
    tmp_dir: str                      # where the server process may write a bounded temp copy (8.3)
    def abs_of(self, root, rel) -> str                # THE resolver: the absolute path of (root index, rel);
                                                      # ValueError when the root index is out of range or the rel
                                                      # does not resolve under that root (the H4 rule, same message).
                                                      # An upload job has one root, index 0.
    def inside(self, abs_path) -> bool                # realpath under one of the roots (or equal to a file root)
    def rel_of(self, abs_path) -> tuple[int, str]     # (root index, rel) for display and notes
    def walk(self) -> list[tuple[int, str, str]]      # (root index, rel, abs) of every regular file, no symlinks,
                                                      # the caps of 7.1 applied; an upload root walks as scan does
```

There is no "find a rel under whichever root" form: a relative path alone is ambiguous across roots (`/a/OFL.txt`
and `/b/OFL.txt` are both `OFL.txt`), so **every path-valued field carries its root**: a font entry (`root`,
`path`), `entry["licences"][]` (`root`, `path`, `first_line`), a licence choice `{"kind": "upload", "root": i,
"path": ...}`, a list-file range (`range` stays the rel, a new per-font/batch `range_root` names the root), and the
scan's internal tables (7.2). `validate` refuses a missing or out-of-range root on a local job and a root on an
upload job (`"%s: licence root %s is not a source"`, `"%s: range root ..."`). The functions that take `upload_dir`
today take `Sources` instead; the S1 plan carries the **complete list from `grep -n "upload_dir\|job_dir\|store.path("
maker/*.py`** (175 hits at `ce976f8`: server 61, jobs 50, settings 40, zipout 14, detect 10) with each hit's new
form, and its review diffs every `realpath` check before and after. Named here so none is forgotten: settings
`_upload_path`, `range_spec`, `plan_steps`, `_shape_errors` and `_batch_shape_errors` (the range `isfile` and the
licence `getsize`), `_licence_paths`, `_licence_sha`, `_licence_present_ok`, `_clash_errors`, `validate`,
`run_ready`; server `_check_steps` (font path and step output), `_check_notes`, `_job_probe`, `_job_preview`,
`_job_source_face`, `_job_face`, `_job_report`, `_job_identity`, `_make_source_preview`, `_prepared_source`,
`_plain_source`, `_companion_abs`, `_clear_previews`, `_preview_glob`/`_remove_preview`; jobs
`_materialized_token`, `materialized_argv`, `_run_steps` (`gz_upload`), `_execute`, `_read_back`, `_identity`,
`_prepared_source`, `_plain_source`, `_plain_token`; zipout `_licence_bytes`, `_write_zip`'s face reads,
`note_commands`; detect `scan`, `_rel`, `find_licences`. The upload job's behaviour is unchanged by construction
(`Sources("upload", [upload_dir])` reproduces every present check: the tests of those checks stay as they are and
must still pass after the slice). `jobs.Store.create(source="local", output_dir=...)` writes `source`,
`output_dir`, `output_id`, `roots: []`; `Store.sources(job)` builds the object.

### 8.2 Detection

`detect.scan(upload_dir)` becomes `detect.scan(sources, local=False)`: it walks `sources.walk()` and builds the same
entries; `path` is the root-relative path and `root` the index. `local=True` (a local job) changes four things:

1. the Mac bitmap containers, raw `fbit` resources, `JM` archives, `HTBL` tables and suitcases become real entries
   with routes (section 9); with `local=False` they keep today's `other` labels;
2. archives are **not** unpacked (`format: "archive"`, label "archive: extract it first, then choose the folder"; an
   upload job unpacks on upload, before the scan, so `scan` itself never unpacked anything - this is only the label);
   `.gz` single files stay as today (decompressed into the files directory on demand);
3. no file bytes go into a label: `"unknown (%s)" % head[:8].hex()` becomes `"unknown"` for local jobs; the
   `unreadable: <Type>: <message>` label and the `; cannot prepare: <message>` suffix become `unreadable: <Type>`
   and `; cannot prepare (<Type>)` (an exception message can quote input bytes); the full message and traceback go
   to `log.md` only (`font["error"]` holds the traceback, which prints no locals, and is written to the log as
   today but is not returned by `GET /api/jobs/<id>` for a local job: the page shows the type);
   `licences[].first_line` is kept (it is the first line of a text `is_licence_text` accepted as licence prose, and
   the user must see it to choose), stated here as the one piece of a source file's text that reaches `job.json`;
4. the scan's temp copies: `_bdf_glyphs` gets `tmp_dir=sources.tmp_dir` and passes it as `dir=` to `mkstemp`, so a
   `.gz` BDF (hanterm ships as `.bdf.gz`) is parsed from a file under the files directory (8.3), never the system
   temp dir; the same `tmp_dir` goes to every `mkstemp`/`materialize` the server process makes for a local job;
5. licence detection (`find_licences`, `is_licence_text`) runs as today over the roots (a user may keep a licence
   or a notes file beside a font); `_licence_folders` takes each root as its ceiling, never the filesystem root
   (today it is `commonpath` of the upload's files).

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
`<output_dir>/.svf-maker-<id>` for a local one, and every join that uses `job_dir` today uses it (the list in 8.1;
`_check_steps`' `_inside(job_dir, output)` becomes `_inside(files_dir, output)`). The files directory and
everything under it are created with mode 0700 / files 0600: the server process calls `os.umask(0o077)` once at
start when the token is set (its tool children inherit the umask), and `os.makedirs(..., mode=0o700)` makes the
directory, since the output folder may be shared.

**The sync caveat, weighed (review I6).** The output folder is the folder most likely to be under a sync client
(Dropbox, iCloud Desktop & Documents, OneDrive) or a backup, and `.svf-maker-<id>/` holds byte-identical copies of
inputs (`source.fbit`, `source.rsrc`, `source.htbl1`, a decompressed `.gz`) from `POST /api/jobs` to the end of the
run, which a sync client can upload within seconds - that is the same objection D3 raises against the data
directory. The card's title fixes the folder ("nothing written outside the chosen output folder"), so the
intermediates stay there, with these mitigations: the 0700/0600 modes above; the prepared copy a preview needs is
removed right after its bake (the baked face stays, the raw fork/fbit/HTBL copy does not: `_prepared_source` is
given `keep=False` for local jobs, and the next preview re-prepares from the input); a job left `detected` is swept
of its files directory after `LOCAL_IDLE_SWEEP_S` = 30 minutes without a request (re-made on demand); the page
says, next to the output-folder chooser, "intermediate files are kept in `.svf-maker-<id>/` inside this folder while
the maker runs; choose a folder that is not synced"; and D3 records the trade-off for the owner.

The subprocess environment of a local job's tools (`jobs.run_command` **and** `preview.run_bounded`, which runs every
preview, probe, source conversion and bake with `preview.ENV`) adds `TMPDIR=<files dir>/work/tmp` (made per job),
so a tool or a library that writes a temp file (none known; Pillow and fontTools do not) writes it inside the
folder too; the server process's own temp copies use `sources.tmp_dir` = the same directory (8.2 item 4); `HOME`
stays the user's (section 12.3's test asserts it is untouched).

Lifecycle of the files directory ("precisely"):

- **made** by `POST /api/jobs` (local) - it must exist before any preview or probe;
- **swept** (removed whole, `shutil.rmtree`, after the move below) at: the end of `run_job` (done, failed,
  cancelled, interrupted; in a `finally`, after the tree write of 8.5 has moved the faces out), `Store.delete`
  (which, for a local job, reads `output_dir` from `job.json` and sweeps **before** removing the metadata directory,
  so `DELETE` and `retain` never orphan a files directory), `Worker.stop` (server shutdown: every local job's files
  directory that exists), `Worker.recover` (server start: every local job's, whatever its state - a crash left it),
  and the idle sweep of a `detected` job (above). A sweep that cannot complete (a drive absent, a file held open)
  appends the directory's path to `<data_root>/pending-sweeps.json` (separate from the jobs, so a metadata directory
  removed meanwhile does not lose it) and is retried at every later sweep point until it succeeds; the start-up
  sweep runs on a thread after the bind, so a dead network mount cannot hold up the "listening on" line;
- **re-made on demand** after a sweep by a preview, probe or source-face GET on a finished job (the user is still
  looking at the page), under the same name, swept again at the next of the points above; so after the server
  stops nothing derived remains anywhere but the results in `svf/`;
- a sweep failure is logged to `log.md` (when the metadata directory still exists) and recorded as above; it never
  fails a job.

Before the end-of-job sweep, two small files are **moved** into the metadata directory: `work/sNN/report.json` ->
`steps/sNN.report.json` and `work/sNN/identity.json` -> `steps/sNN.identity.json` (design call, D5): they hold the
mkfont box report (per-code-point ink boxes and cut counts: metrics, no bitmap) and the identity scores (numbers per
piece), which the page's step rows and the clipping panel read after the job. `GET report/` and `identity/` of a
local job serve from `steps/`. If the owner rules otherwise (D5) they are swept with the rest and those two GETs are
404 after the job.

*Later bounds (t_d1aba4b8).* The sentence above, "the start-up sweep runs on a thread after the bind", is historical: the
start-up sweep now runs BEFORE the "listening on" line, bounded in all by `STARTUP_CLEANUP_S` plus the pending floor and
the flush of the pending records; its deadlines, the fence on an abandoned rename, the single writer of
`pending-sweeps.json`, the three sections of a local `POST run` (prepare, read and plan outside the lifecycle lock,
commit) and the restored lock order are described in `docs/maker-audit.md` section 8, "Bounded lifecycle".

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
  token that resolves under a root or under the files directory is written as its **basename**, `argv[0]`
  (`sys.executable`) as `python3` and a tool path under `tools_dir` as `tools/<name>.py` (`note_commands` gets
  `sources` and `tools_dir` and rewrites those tokens; a copy step's line names the basename too, today
  `upload/<path>`), so a note never carries a home directory, a volume name or an AppImage mount; the 512-byte line
  cap then holds for any path length. `_check_notes` at `POST run` uses the same rewrite, so what it accepts is
  what is written.
- stderr of the server: the 500 path prints a traceback (no data); `log_message` stays silent.

### 8.5 The run and the output tree

`plan_steps` is unchanged in logic: it gets `Sources` and the files directory (`work_root` = `<files dir>/work`).
`settings.source_ops` and `routes.source_commands` gain the Mac ops of section 9.2; `plan_steps` resolves the new
companions (`htbl_companion`, the Mac Latin suitcase) the way it resolves `latin_companion`.

`zipout._write_zip` is split into `collect(job, files_dir, index, fonts_by_id, effective, repo_dir, sources,
own_earlier) -> (entries, sidecar_entries, result, faces)` (everything up to building the entry dict and the
`.lines`/`BUILD.md` texts; unchanged rules, plus `own_earlier` exempting a same-named other-bytes entry from
`NameClash` in `check_face`'s and `_text_entry`'s paths) and two writers: `write_zip` (today's, upload jobs;
`own_earlier` empty) and `write_tree(entries, sidecar_entries, output_dir, output_id, own_earlier)` (local jobs).
`write_tree` first checks `os.stat(output_dir)` against `output_id` (7.1), then writes each entry to
`<output_dir>/<entry>` (`svf/...`) and each sidecar entry to `<output_dir>/build-<id>/...`, each through
`<path>.tmp` then `os.link` for a new name or `os.replace` for an `own_earlier` name (7.3), creating `svf/<dest>/`
and `build-<id>/` as needed (never the output folder itself); on any failure the `.tmp` files are removed and
nothing already placed is rolled back (the faces are independent files; `result.files` lists what landed). The
index used for the identical/clash check is `naming.RepoIndex(<output_dir>/svf)` (the class reads a directory of
`<dest>/<NAME>.SVF` and `.TXT`; built on the output folder's own `svf/`, so bytes already in the folder are
"identical" and the step says so) - the repository's `svf/` index is **not** consulted for clashes of a local job
(the user is not writing into the repository); `run_ready`'s name rules are applied to that output index with the
same `own_earlier` exemption.

`result` of a local job: `{"files": ["svf/dos/SEOUL12J.SVF", "svf/dos/SEOUL12J.TXT", "svf/dos/LICSEOUL.TXT",
"build-<id>/BUILD.md", ...], "written": [the faces, as today], "skipped": [...], "failed_steps": [...],
"output_dir": "/abs/dir"}` (no `zip`). A done step gains `"written": "svf/<dest>/<NAME>.SVF"` (output-relative), or
`"identical_to"` as today. `GET face/<step>.svf` of a done local job serves `<output_dir>/<written>`, or
`<output_dir>/svf/<identical_to>` for an identical step (checked with `_inside(output_dir, ...)`, a regular file,
and `output_id` unchanged) - the face the user has, not a copy; if the user moved the folder it is 404 `"face not
in the output folder"`. For a job in any other state the face is in `work/` as today.

What is written, exactly: the faces; per font with a written or identical face its note and its licence text
(8.6); under `build-<id>/`: `LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines` (the rows a maintainer
would paste into the repository's tables; they name faces, licence files and families, no bytes) and `BUILD.md`.
Nothing else: no zip (D13), no copy of an input, no `job.json`.

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

Sniffing from a path uses the head and the size as today (`detect.sniff(head, size)`) plus three new tags, tested
**before** the `DOS_SIZES`/`eng` size rules (a JM archive or a raw resource of a coincidental size must not become a
DOS font):

- `"mac-jm"`: `head[:2] == b"JM"` and `jm_header` parses with `file_len == size` and `unpacked_len <= JM_CAP` (4
  MiB: the 7.1.2 fonts are tens of KB and the LHA decoder is pure Python running in a synchronous `POST detect`).
  The scan unpacks it **in memory** (`macfbit3.jm_unpack`) and classifies the fork it yields; the bytes are dropped
  after the file's entries are built (the `.gz` rule). The archive is unpacked again by the source step and by each
  preview that needs it (acceptable at that size).
- `"mac-fbit-raw"`: `head[2:6] == b"fbit"` (a raw resource saved by `macfbit3.py fbit`).
- `"mac-htbl-raw"`: `size == 9816 and u32 at 0 == 204` (section 4's arithmetic; the builder verifies the number on
  the synthetic table of `test_macfbit3.make_htbl` and, when `MACFBIT3_CD712` is set, on the real one; if the real
  table differs the rule becomes "`L1 == 204` and `size == 8 + L1 + 4 * 2401`" and the doc line is corrected).

`_mac_entries` (a container with no `sfnt`; also a raw fork, `.dfont`, AppleDouble, MacBinary, or the fork a `JM`
archive unpacked to) inspects the resources:

| Resources found | `source_kind` | label | entry extras |
|---|---|---|---|
| `fbit` with `u16@0x0c != 3`, `u16@0x54 // 12 == 45`, and `fdef` id 3 of >= 0x716 bytes | `mac-fbit1` | "HangulTalk 1.0 fbit (45 sets), W x H" (W, H from set 0's descriptor) | `sizes=[H]`, `sizes_fixed`, `prep=[{"op": "mac-fork"}]` when the container is AppleDouble or MacBinary (jamoset reads a raw fork), `coverage = {"ascii": 0, "ks2350": 2350, "all": 11172, "compat": 51}` (a fact of the format, as `DOS_COVERAGE`), `mac={"generation": 1}` |
| `fbit` with `u16@0x0c == 3` (any id) | `mac-fbit3` | "HangulTalk 7.1 type-3 fbit, H px, N planes (needs HTBL 1)" | `sizes=[H]`, `prep=[{"op": "mac-fbit3"}]` for a raw fork, a raw resource or a JM archive (`macfbit3.load_fbit` takes those three), `prep=[{"op": "mac-fork"}, {"op": "mac-fbit3"}]` for an AppleDouble or MacBinary container (`load_fbit` cannot unwrap them), `coverage = {"ascii": 0, "ks2350": 2350, "all": 2350, "compat": 51}`, `mac={"generation": 3, "id": rid}` |
| `HTBL` id 1 | `mac-htbl` (format `mac-rsrc`) | "HangulTalk 7.1 HTBL 1 (InputBackSupport): the composition table" | `other`-like: no route; `prep=[{"op": "mac-htbl"}]` for a raw fork, `[mac-fork, mac-htbl]` for a wrapped one (`load_htbl1` silently returns a fork it cannot parse as "the raw table", so the unwrap must happen first); a raw 9,816-byte table has no prep; `mac={"table": "htbl1"}` |
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
there is one parser. The per-op output extension becomes one table used by **both** `routes.source_commands` (the
step's argv) and `server._prepared_source` (which derives the extension itself today and checks `produced ==
target`): `{"rsrc-sfnt": sfnt_ext, "ttc-face": sfnt_ext, "mac-cmap": sfnt_ext, "instance": sfnt_ext, "pcf-bdf":
"bdf", "mac-fork": "rsrc", "mac-fbit3": "fbit", "mac-htbl": "htbl1"}`, intermediates named `source-<i>.<ext of op
i>`, the last `source.<ext>`; for a `mac-fbit1` font the last file is named `<original stem>.rsrc` instead of
`source.rsrc` so that `jamoset.mac_golden` (keyed by the source stem) still finds a golden entry for a wrapped
input. `srcprep._apply_op` learns the three ops too (the scan runs `prepared_bytes` on every entry with `prep` for
its coverage; without them every Mac entry would be "cannot prepare"), and `detect._coverage_of_entry` returns the
fixed coverage of the two Mac kinds (as it does for `dos-raw`) instead of None. `settings._SOURCE_WORDS` gains
`"mac-fbit1": "Mac fbit"`, `"mac-fbit3": "Mac fbit"`, `"mac-htbl": "Mac table"`, `"mac-suitcase": "Mac suitcase"`
(article "a"), `presets.ALL_SOURCES` the four kinds, and `maker.js` `SOURCE_WORDS`, `PREVIEW_KINDS` (`mac-fbit1`,
`mac-fbit3`: `"bake"`; `mac-htbl`, `mac-suitcase`: `"none"`) in the same commit (the drift test compares all three).

Routes (`routes.routes`), in page order, with the `OPTION_VISIBLE` row each needs:

| `source_kind` | kind / label | native | command (after the source step; `paths["src"]` is the prepared file) | options |
|---|---|---|---|---|
| `mac-fbit1` | jamo / `mac fbit 1.0` | yes | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | `["embolden", "symbols", "jset_version", "jamo_ascent"]` (the `dos raw` row: `--embolden`, `--symbols`, `--jset-version V`, `--ascent N`; `jamo_ascent` validated 1..H) |
| `mac-fbit3` | jamo / `mac fbit 7.1 direct` | yes | `macfbit_svf.py build SRC HTBL -o OUT --mode direct [--latin SUITCASE]` | `[]` (a direct face is a JMAP: `--jset-version` has no effect without `--with-jset`, section 4; `jamoset`'s `--symbols`/`--embolden` do not exist here) |
| `mac-fbit3` | jamo / `mac fbit 7.1 derived` | no (experimental: 8,822 syllables are extrapolated, never Mac output) | `macfbit_svf.py build SRC HTBL -o OUT --mode derived [--latin SUITCASE]` | `["jset_version"]` (`--jset-version V`) |
| `mac-fbit3` | precomposed / `mac fbit 7.1 bdf + mkfont` | yes | `macfbit3.py bdf SRC HTBL <NAME> work/sNN/mac.bdf` then `mkfont.py work/sNN/mac.bdf OUT --size H --bpp 1 --unicode <range>` (a BDF strike through FreeType at its own size, the `bdf-iso10646` rule; the BDF holds no ASCII, so the Latin comes from nothing - the page's note says so; `bpps=[1]`, `sizes=[H]`) | `["cell", "ascent", "width", "space_advance"]` (the mkfont keys that apply to a bitmap strike; no `mono_hint`) |

The panel flags come from `presets.panel_argv`, which branches on exact labels: `"mac fbit 1.0"` joins the
`"dos raw"`/`"hanterm"` branches for `--embolden`, `--symbols`, `--jset-version` and `--ascent` (`jamo_ascent`);
`"mac fbit 7.1 derived"` joins the `--jset-version` branch; `"mac fbit 7.1 bdf + mkfont"` takes the `mkfont`
branch minus `--mono-hint`, `--clip-cell`, `--fit-cell`, `--latin` (a bitmap strike: `cell`, `ascent`, `width`,
`space_advance`); `"mac fbit 7.1 direct"` emits nothing. The drift test's `TOOL_OF_LABEL` gains `"mac fbit 1.0":
"jamo_ascent"` and `"mac fbit 7.1 bdf + mkfont": "ascent"` in the same commit as the routes (without it the test
raises `KeyError`), and `maker.js` `OPTION_VISIBLE` the four rows above.

Companions: a `mac-fbit3` entry's `companions` are every `mac-htbl` entry of the batch (the table is a separate file
and need not sit beside the font); a new per-font key `htbl_companion` (font id or null; `FONT_ONLY_KEYS`,
`_FONT_ONLY_DEFAULTS` null, default the first candidate; validated as `latin_companion` is: must be in
`companions`; remapped by `_kept_settings` on re-detect as `latin_companion` is) feeds `paths["htbl"]`. The Mac
Latin suitcase reuses `latin_companion`: for `mac-fbit3` its candidates are the `mac-suitcase` entries whose
strikes include H (the FOND's plain-style sizes; `macfbit_svf` refuses any other), default none (`--latin` is
optional). `run_ready` adds `"%s: needs an HTBL 1 table (InputBackSupport or <Name>.htbl1): add it to the sources"`
when a `mac-fbit3` font is selected without one.

Companion source steps: `plan_steps` plans the HTBL's and the suitcase's own `source` steps (their `prep`)
**before** the first face step that uses them, **once per companion entry** however many fonts use it (a dict
companion id -> step id; today a companion's `prep` is not planned because `eng` files and BDF companions have
none; the Mac companions are the first with one). Each such step has `font` = the companion's id and kind
`source`; every face step that reads a companion's prepared file carries `"needs": ["sNN", ...]` (the step ids of
the companion source steps it depends on; absent or `[]` today). `jobs._run_steps` fails a step whose `needs`
names a failed step with `"companion source failed"` before running it (today's cascade is by `step.font` only,
which would let the face step run and crash on the missing file); `_check_steps` verifies every `needs` id is an
earlier step of the job. The Step shape gains the key (`settings._step`), and `test_jobs.py`'s shape assertions are
updated in the same commit.

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
  <token>` equal to the environment's: the header value is taken as `http.server` decoded it (latin-1), encoded
  back to bytes, and compared with `hmac.compare_digest(header_bytes, token_bytes)` (a `str` compare raises
  `TypeError` on a non-ASCII header; any exception in the compare is a 403 too); otherwise 403 `"missing or wrong
  token"`. The check runs **before route matching**, so an unauthenticated client cannot tell a 404 route from a
  403 one and no job id is confirmed or denied. `/` and `/static/*` need no token (the page and its module are
  public code; the shell loads them). The `Host`/`Origin` check stays as it is and runs first.
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

- Every GET that serves bytes derived from a local job answers `Cache-Control: no-store`: `face`, `source`,
  `probe` (`.svf` **and** `.json`: the ink boxes; today `no-cache`), `preview .png` (today served by `_serve_file`
  with **no** `Cache-Control` at all), `report`, `identity` (the `repo/face` fallback is OFL and keeps `no-cache`).
  `no-store` tells the browser and Electron's disk cache to keep nothing, so a client never sends `If-None-Match`
  for them; the `ETag` stays as a harmless header and the page keeps face bytes in memory per `(job, step)` as
  before (6.5 of the previous design), so nothing is refetched needlessly. The test asserts the header on each of
  the six endpoints. The shell card should use an in-memory session partition (no `persist:` prefix) - noted in
  10.6 as a contract line.
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
namespace run of 12.3 where the host permits it (**not this host**, section 4: here the gate is the pair (1)+(2) and
the static scan is what covers the tools); (4) the page: `/` and `/static/*` are served with
`Content-Security-Policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; img-src
'self' blob: data:; font-src 'self'; style-src 'self'` (the module needs `wasm-unsafe-eval`; the page uses no inline
script or style today - the builder confirms with the DOM test and adjusts `style-src` if `index.html` has an
inline style), and a static test asserts that no file under `maker/static/` (the built `wasm/` excluded) contains
an absolute `http(s)://` or protocol-relative `//` URL outside comments; (5) the shell (10.6) cancels every request
of its window whose URL is not `http://127.0.0.1:<port>/...` and refuses navigation and new windows. The server
never resolves a name but `localhost` at bind time. There is no crash reporter, update check or usage ping, and
`maker/README.md` says so (section 11).

### 10.6 The contract with the Electron shell (fixed here, built in t_f04f1355)

The shell:

1. starts `python3 -P maker/server.py` (or the packaged sidecar) with `SVF_MAKER_BIND=127.0.0.1:0`,
   `SVF_MAKER_TOKEN=<hex>`, `SVF_MAKER_DATA=<app.getPath("userData")>/svf-maker`, `SVF_MAKER_REPO=<resources>`, and
   reads the line `svf-maker listening on 127.0.0.1:<port>` from stdout (today's line; the port is `server.port`);
2. loads `http://127.0.0.1:<port>/` in a window whose session is in-memory (`partition: "maker"` without `persist:`),
   adds `X-Maker-Token` to every request to that origin (`onBeforeSendHeaders`), cancels every other request of
   the window (`webRequest.onBeforeRequest` on `<all_urls>` minus the sidecar origin), refuses navigation
   (`will-navigate`) and new windows (`setWindowOpenHandler` -> deny); never `file://`;
3. exposes in the page, through a preload script (`contextIsolation` on), `window.svfMaker = {pickFiles():
   Promise<string[]>, pickFolder(): Promise<string[]>, pickOutputDir(): Promise<string|null>, openOutputFolder():
   Promise<void>, platform: string}` - two source dialogs because Electron cannot combine `openFile` and
   `openDirectory` in one dialog on Linux and Windows; a cancelled dialog resolves to `[]` / `null` and the page
   changes nothing; the dialogs return absolute paths and the page passes them to the server unchanged;
   `openOutputFolder` takes **no path**: the shell reveals, with `shell.showItemInFolder` (never `openPath`, which
   executes files), the folder its own `pickOutputDir` returned in this launch (the page's `job.output_dir` is only
   shown as text);
4. stops the sidecar with SIGTERM when the window closes and waits up to 35 s for it to exit (the server's
   `Worker.stop` sweeps every local job's files directory, 8.3, and kills the tool children - already in place)
   before killing it. A forced quit or a crash leaves the sweep to the next start (`recover`, 8.3). The server is
   POSIX-only (section 4), so the shell's targets are Linux and macOS.

The server never opens a dialog, never browses, never reads a path it was not given through `POST /api/jobs` or
`PUT sources`, and never writes outside the output folder and the metadata directory. The page shows the shell's
buttons only when `window.svfMaker` exists and hides the typed-path fields then (6.3).

## 11. README and NOTICE wording (F)

`NOTICE.md`, section "Converters for proprietary formats", gains one paragraph after the existing one:

> The maker (`maker/`) has a local mode for such fonts: the desktop app passes it the paths of files or folders the
> user picked and an output folder; the fonts are read in place, converted, and the faces are written only into that
> folder. In that mode nothing is uploaded, nothing is copied into the maker's data directory, no zip is made, and
> the files the conversion needs on the way are kept inside the output folder and removed when the job ends. The
> maker has no code that connects anywhere but to its own local page on 127.0.0.1 (the tests check its imports and its own
> sockets; `docs/maker-audit.md` section 8 says what they do not cover). No proprietary font, bitmap or table is in this
> repository; the local-mode tests build synthetic inputs in the test and the checks on real files run only where an
> environment variable names the user's own copies.

`maker/README.md` gains a section "Local mode (desktop app)": what `SVF_MAKER_TOKEN` does (local mode on, every
`/api` request needs `X-Maker-Token`), the loopback rule, `POST /api/jobs {"source": "local", "output_dir"}` and
`PUT /api/jobs/<id>/sources {"paths": [...]}`, what is written into the output folder and what `.svf-maker-<id>/` is,
the Mac rows of 9.2 with their tools, the HWP line ("`HANGUL*.PFT` is not read; `ASCII.PFT` is a companion"), and
the sentence "has no code that makes an outbound connection and sends nothing anywhere (no telemetry, no crash upload, no
update check)" followed by what the tests check and do not (the closing slice replaced the stronger "the tests pin that"). `docs/maker-audit.md` section 1 rows for Mac fbit (both) and HWP `.PFT` and the
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
| `test_settings.py LocalSettingsTest` | `htbl_companion` type/offer errors, the "needs an HTBL 1 table" run_ready message, the suitcase as `latin_companion` only at a listed strike, `jamo_ascent` 1..H on `mac fbit 1.0`, the default text licence of 8.6 and its name; a licence or range with a missing/out-of-range root on a local job and with a root on an upload job are refused with the 8.1 messages; two roots each holding `OFL.txt`: each font's licence resolves to its own root's file |
| `test_routes.py PanelArgvTest` (extended) | `panel_argv` for the four Mac labels emits exactly the flags of the 9.2 rows per bpp and nothing for `mac fbit 7.1 direct` |
| `test_srcprep.py` | `mac-fork` unwraps AppleDouble and MacBinary to the raw fork bytes and refuses an oversized fork; `mac-htbl` extracts `HTBL` 1 from a fork and passes a raw table through, refusing `L1 != 204` |
| `test_server.py test_page_js_tables_match_python` (extended `canonical_fonts()`) | the Mac entries in both `local` forms; `OPTION_VISIBLE` rows of 9.2 |
| `test_plan_inputs.py MacEndToEndTest` | a local job over `local_tree`: the 7.1 `direct` face is written, `macfbit_svf.py verify` on it exits 0 (run as a subprocess on the written face, the fixture's fbit and HTBL), `facecheck` passes; the same from an AppleDouble font + AppleDouble HTBL, from a MacBinary pair, and from the JM archive (the source steps chain `mac-fork` then `mac-fbit3`/`mac-htbl`); two 7.1 fonts sharing one HTBL plan **one** HTBL source step and both face steps carry its id in `needs`; a corrupted HTBL fails its source step and both face steps end `failed` with "companion source failed" without running; the `derived` face composes all 11,172 (`jamoset.check`); the `bdf + mkfont` face holds 2,350 syllables + 51 jamo; the 1.0 face passes `--check` (or is env-gated, 12.1); the `.gz`-wrapped fork decompresses under the files directory; `panel_argv` with `jamo_ascent` set reaches the 1.0 argv as `--ascent` |
| `test_detect_inputs.py test_scan_temp_copies_stay_in_tmp_dir` | a `.bdf.gz` hanterm/KSC BDF | `tempfile.tempdir` is pointed at a sentinel; a local scan parses the BDF (coverage is read) and the sentinel stays empty; the copy went under `sources.tmp_dir` and is gone after the scan |

### 12.3 The proofs of the card

| Test (file) | Fixture | Proves |
|---|---|---|
| `test_local.py test_no_upload_copy` | `local_tree`, a local job through `make_server("127.0.0.1", 0, ..., token=T)` and HTTP with the token | after `PUT sources`, `POST detect`, every preview/probe/source-face GET and `POST run` to `done`: the metadata directory holds exactly `job.json`, `log.md`, `steps/` (JSON only); no file under `data_root` has the sha256 of any input; `job.json` text contains no input's head hex and no base64 of it; no `upload/`, `work/`, `out/` under `data_root/jobs/<id>/` |
| `test_local.py test_no_write_outside_output` | the same, inputs under `tmp/in` made read-only (0o555/0o444), `HOME`, `TMPDIR`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME` of the test process, `tempfile.tempdir`, and the worker's and `preview`'s `ENV` pointed at empty sentinel dirs under `tmp`; one input is a `.bdf.gz` | a snapshot `(relpath, size, mtime_ns, sha256)` of `tmp/in` before equals the one after; the sentinel dirs are empty after; `tmp/out` holds exactly `svf/<dest>/{faces, notes, licence}`, `build-<id>/{BUILD.md, the three .lines}` and, while the server runs, nothing else (`.svf-maker-<id>/` was swept at job end: asserted absent); the files directory, while it exists, is mode 0700 and its files 0600; after `server.worker.stop()` and `server_close()` the whole `tmp` tree is: `in` (unchanged), `out` (as listed), `data/jobs/<id>/{job.json, log.md, steps/*}`, the empty sentinels - **nothing else** (an `os.walk` of `tmp` compared with the expected set) |
| `test_local.py test_output_folder_gone` | - | after `POST /api/jobs` the test renames the output folder and creates an empty one at the old path: a probe GET is 404 "output folder is gone or changed", `POST run` is refused, nothing is created at the old path; with the folder restored the run proceeds |
| `test_local.py test_one_job_per_output_folder` | two jobs | a second `POST /api/jobs` with the same output folder while the first is `detected` is 409 "output folder is in use by job <id>"; after the first is `done` it is accepted; a second server instance (own data root, same folder) writing the same new name gets the `os.link` failure as a name clash, the first file's bytes untouched |
| `test_local.py test_sweep_points` | - | the files directory exists after `POST /api/jobs`, holds the probe after a probe GET, is gone after `run` ends, re-made by a source-face GET on the done job, gone after `DELETE`; a second server started on the same data root with a leftover `.svf-maker-<id>/` (planted by the test) removes it in `recover`; `Worker.stop` removes one that a GET re-made |
| `test_local.py test_results_served_from_output` | - | `GET face/<step>.svf` of the done job equals the bytes of `tmp/out/svf/dos/<NAME>.SVF` and carries `Cache-Control: no-store`; after the test renames the output folder the GET is 404 "face not in the output folder"; `GET zip` is 404 |
| `test_local.py test_collisions` | two runs | a re-run of the same job through `POST run` (not `write_tree` alone) passes `run_ready`, overwrites its own face **and its note** (the test moves the clock a day: the note differs) and its `build-<id>/` record; a re-run with a changed setting likewise; a second job into the same folder with the same face name and other bytes fails with the clash message and leaves the first face's bytes and record; equal bytes under another name mark `identical_to` and `GET face` serves that path |
| `test_local.py test_path_rules` | - | every refusal of 7.1 with its message: relative path, symlink root, a path under `data_root`, the output folder under a source, a source under the output folder, `/`, a non-existent path, a FIFO; `SVF_MAKER_ROOTS` set: a path outside it; `PUT files` on a local job 409; `PUT sources` on an upload job 409; `POST /api/jobs {"source": "local"}` without the token 403 |
| `test_local.py test_notes_and_logs` | - | the written note's command lines contain **no absolute path at all** (`python3 -P tools/<name>.py <basenames...>`), every line <= 512 bytes with a 300-byte root path; `log.md` contains the full paths (D4); `job.json` holds `roots` and relative paths, no `unknown (<hex>)`, no exception message in a label; `GET /api/jobs/<id>` of a local job carries no `error` traceback text |
| `test_local.py test_no_store_headers` | - | each of `face`, `source`, `probe .svf`, `probe .json`, `preview .png`, `report`, `identity` of a local job answers `Cache-Control: no-store`; the same endpoints of an upload job keep `no-cache` |
| `test_server.py test_csp_and_static_urls` | - | `/` and `/static/maker.js` carry the CSP of 10.5; no file under `maker/static/` (except `wasm/`) holds an absolute or protocol-relative URL outside a comment |
| `test_server.py LocalBindTest` | - | section 10.3's list |
| `test_local.py test_network_off_in_process` | the same job | `socket.socket.connect`, `connect_ex` and `socket.create_connection` are wrapped for the test's duration to assert `is_loopback` on the address and count calls; the only connections are the test client's; no `getaddrinfo` for a non-`localhost` name |
| `test_local.py test_network_off_namespace` | - | skipped unless `unshare -rn true` exits 0 (an unprivileged user netns; **it does not on this host**, section 4); then the whole local job (in-process server, tools as subprocesses) runs under `unshare -rn python3 -P -m unittest ...LocalJobInNetns` with only `lo` up, and passes - proving no tool child needs a network either. Where it is not permitted the skip message says so and the static scan plus the in-process guard are the gate |
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
unaffected by construction (no file under `c/` is named by this design). On this host `unshare -rn` is refused, so
the network-namespace proof of 12.3 will skip here; the gate for "no outbound connection" on this host is the static
import scan, the in-process socket guard, the CSP/static-URL test and the shell contract (10.5).

## 13. Task decomposition hint (H)

Slices, each a commit series with its tests; the drift test runs at every commit, so a slice that adds a route or an
entry shape ships the `maker.js` rows and `canonical_fonts()` in the same commit.

1. **S1 `sources.py`** - the abstraction of 8.1 threaded through settings, server, jobs, zipout, detect for upload
   jobs only (`Sources("upload", ...)`), every path-valued field with its root; no behaviour change; the suite stays
   at 682 plus the module's own tests (abs_of / inside / rel_of / walk on symlinks and escapes). The S1 plan lists
   every hit of `grep -n "upload_dir\|job_dir\|store.path(" maker/*.py` with its new form (8.1), and the review
   diffs each `realpath` check before and after. Risk: this touches every path check; keep each existing escape
   test and add none that relaxes one.
2. **S2 token + loopback + no-store + CSP + caps.local** (`server.py`, `caps.py`, `README`): 10.2, 10.3, 10.4,
   10.5 (4), `LocalBindTest` without its `PUT sources` case, `test_csp_and_static_urls`, the header on every `/api`
   request when the token is set, `caps["local"]`. Independent of S1.
3. **S3 the local job** (`jobs.Store` source/output_dir/output_id/roots/files_dir, `POST /api/jobs` body, the
   one-job-per-folder rule, `PUT sources`, scan over roots with `tmp_dir`, the files directory (0700, `TMPDIR` for
   both subprocess runners, the server's temp copies) and its sweeps (`Store.delete`, `pending-sweeps.json`, the
   start-up thread, the idle sweep), `collect`/`write_tree` with `own_earlier`, `result.files`, `os.link`,
   `build-<id>/`, the output-folder identity check, results served from the output (`written` and
   `identical_to`), reports moved to `steps/`, `retain`, notes without absolute paths, labels without hex or
   exception messages, the default text licence, the `needs` key on steps and the cascade in `_run_steps`,
   `_kept_settings` by root path): sections 7, 8; tests 12.3 except the Mac rows, plus `LocalBindTest`'s `Origin:
   null` on `PUT sources`. Depends on S1, S2. This is the biggest slice; split by endpoint (create+sources+detect /
   run+tree / sweeps+serving) with the no-write test growing per commit.
4. **S4 the page** (`index.html`, `maker.js`: the sources panel, the bridge hooks and the hiding rule, "open folder",
   the status line, the sync caveat; `pagedrive.mjs --header`; `LocalPageTest`). Depends on S3.
5. **S5 Mac kinds** (`detect.py` sniff tags before the size rules and `_mac_entries` rows, `_coverage_of_entry`,
   `srcprep.py mac-fork`/`mac-htbl` CLI and `_apply_op`, the per-op extension table shared by `routes.source_commands`
   and `server._prepared_source`, `settings.source_ops` + `htbl_companion` + run_ready + `_SOURCE_WORDS`,
   `presets.ALL_SOURCES` + `panel_argv` branches, `routes.py` four routes, `maker.js ROUTES`/`OPTION_VISIBLE`/
   `PREVIEW_KINDS`/`SOURCE_WORDS`, the drift test's `TOOL_OF_LABEL` and `canonical_fonts()`, companion source steps
   planned once with `needs`, `preview.bake_source_face` kinds, `macfx.py`, `MacEndToEndTest`). Two commits: 7.1
   (the fixture exists) then 1.0 (the fixture is the risk, 12.1). Depends on S1 and **S3** (it edits `detect.scan`,
   `settings.py` and `server.py`, which S3 changes: it runs after S3, not beside it). Only `macfx.py`, the
   `srcprep.py` subcommands and the `routes.py` route functions may be drafted in parallel with S3, as unwired code
   with their own unit tests; the wiring and every table change land after S3 in one two-sided commit per route
   group.
6. **S6 HWP and hanterm lines + docs** (`hwp-pft` label, the 12x24 companion relaxation, NOTICE/README/audit/recipes
   wording). Depends on S3.
7. **S7 proofs** (`test_network_off_*`, `test_static_no_network_imports`, the real-file gates `SVF_MAKER_REAL_MAC1/
   MAC3`, the sweep, collision, output-folder-gone and concurrency tests if not already in S3). Depends on S3, S5.

Order: S1 and S2 in parallel (S2 touches `server.py` only in the request path: the token/CSP/header code; S1 touches
`server.py` in the path-resolution code - still, land S2 first, then rebase S1, so no two commits to `server.py`
are in flight); then S3; then S4 (page files) in parallel with S5's wiring (Python and the page **tables** only -
`maker.js` edits of S4 and S5 are in different regions, and the drift test runs at each commit); S6; S7; a closing
commit with the gates run and the audit updated. No two slices edit `settings.py`, `detect.py` or `jobs.py` at the
same time.

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
- The exact shape of `result.files` entries when `write_tree` fails part-way (a list of landed paths is the minimum).
- The page's layout of the sources panel and the wording of its notices (the hiding rule for the typed-path fields
  is decided in 6.3).
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
  delete, stop, start and when idle (8.3), so the data directory never holds a derived byte. Weighed against it
  (review I6): the output folder is the one most likely under a sync client or backup, and the intermediates sit
  there for the job's life; the mitigations of 8.3 (0700/0600, prepared copies removed after each bake, the idle
  sweep, the page's caveat) reduce but do not remove that exposure. Alternative: under the data directory with the
  same sweeps (simpler joins; a crash or a backup of `~/.local/share` can then carry bitmaps instead). The card's
  title ("nothing written outside the chosen output folder") is why the recommendation stands.
- **D4. Paths in `BUILD.md`/`log.md`.** Recommendation: full paths in the log and `BUILD.md` (the user's own record),
  basenames in the notes (`<NAME>.TXT`, which travel with a face). Alternative: basenames everywhere.
- **D5. The numeric per-step reports (`report.json`, `identity.json`) kept in the metadata directory after the job**
  so the step rows and the clipping panel keep working. Recommendation: keep (numbers, no bitmap). Alternative: sweep
  them; those two GETs are 404 after the job.
- **D6. Collisions in the output folder.** Recommendation (7.3, in `check_face`'s terms): bytes already present
  under any name are `identical_to` and not written; a name present with other bytes is a clash unless this job
  wrote it in its previous run (faces, notes and licences alike, from `result.files`), in which case it is
  replaced; one active job per output folder. Alternative: a per-run subfolder (no clashes, no re-run in place).
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

## 16. Changes made in the revision (2026-11-04)

For the plan writer: what moved between the first commit (`5271e8b`) and this one. Symlink rule relaxed to "the root
itself is not a link; resolve once; links below are skipped" and overlap checks by inode (7.1); the output folder's
identity pinned by `(st_dev, st_ino)` and never created (7.1, 8.5); `_kept_settings` and the scan keyed by root path
(7.2); the build record moved into `build-<id>/`, the collision rule restated in `check_face` terms with
`own_earlier` through `run_ready`/`_text_entry`, `result.files`, `os.link` for new names, one active job per folder,
disk-full semantics (7.3, 8.5); `Sources.abs_of(root, rel)` as the only resolver with a root on every path-valued
field and the complete conversion list (8.1); labels without exception messages, the scan's temp copies under
`sources.tmp_dir`, `TMPDIR` for `preview.run_bounded` too, 0700/0600, the sync caveat and the idle sweep,
`Store.delete` sweeping first, `pending-sweeps.json`, the start-up sweep on a thread (8.2, 8.3); notes without any
absolute path (8.4); wrapped Mac containers get `mac-fork` first, the shared per-op extension table,
`srcprep._apply_op`, `_coverage_of_entry`, `_SOURCE_WORDS`/`ALL_SOURCES`/`PREVIEW_KINDS`, `panel_argv` branches and
`TOOL_OF_LABEL`, `jset_version` dropped from the direct row, the golden stem kept, companion source steps once with
`needs` and a cascade, sniff order and `JM_CAP` 4 MiB (9.2); the token compared as bytes before route matching
(10.2); `no-store` on all six byte endpoints and the 304 wording (10.4); CSP, the static-URL test, the shell's
request filter and the netns caveat (10.5); the bridge API `pickFiles`/`pickFolder`/`pickOutputDir`/
`openOutputFolder` with cancellation and `showItemInFolder`, the 35 s stop wait, POSIX-only (10.6); the typed-path
fields hidden with the bridge (6.3); tests for each (12); S5 after S3 and the S1 grep list (13); D3 and D6 restated.

## 17. Review dispositions (2026-11-04)

Two independent reviews of commit `5271e8b`: Opus lane (`/home/thkim/work/scratch/review-lanes/maker-local-design/
opus-report.md`: 0 critical, 7 important, 16 minor) and the agy lane (`.../maker-local-design-agy/out.md`: 3
critical, 4 important, 3 minor). Every finding was checked against the tree at `ce976f8` before the design changed;
the code citations below are what I verified. Duplicates are merged.

| Finding | Verified | Done |
|---|---|---|
| Opus I1 / agy 7: `detect._bdf_glyphs` writes a `.gz` BDF to the system temp dir; `preview.ENV` has no `TMPDIR` | yes (`detect.py:1209`, `preview.py:49`) | 8.2 item 4, 8.3: `sources.tmp_dir`, `TMPDIR` for both runners, `test_scan_temp_copies_stay_in_tmp_dir`, the sentinel in `test_no_write_outside_output` |
| Opus I2: `run_ready` and `_text_entry` refuse same-named files whatever the bytes; `result.written` lists faces only; `identical_to` means bytes under any name | yes (`settings.py:1191-1205`, `zipout.py:361-377`, `naming.py:219-227`) | 7.3, 8.5, D6: `own_earlier` from `result.files` through `run_ready`, `_clash_errors`, `_licence_present_ok`, `_text_entry`; rule restated; `test_collisions` through `POST run`, next day, changed setting |
| Opus I3 / agy 2: a rel path alone is ambiguous across roots (licence, range, `licences[]`, scan tables, `gz_upload`) | yes (`settings.py:712, 739, 794, 1057`, `detect.py:1317, 1340, 1363`, `jobs.py:582`) | 8.1: `abs_of(root, rel)` the only resolver, a root on every path-valued field, validation of roots; 7.2: scan keyed by `(root, rel)`; the complete grep list for S1 |
| Opus I4: `load_fbit`/`load_htbl1` take a raw fork only; AppleDouble/MacBinary need an unwrap first; `load_htbl1` silently passes a fork through | yes (`macfbit3.py:198-213`) | 9.2 table: `[mac-fork, mac-fbit3]` / `[mac-fork, mac-htbl]` for wrapped containers; e2e cases for AppleDouble, MacBinary, JM |
| Opus I5: a removed or unmounted output folder would be re-created by `makedirs` and later writes land elsewhere | yes (`server.py:1029, 1144, 1184, 1231`, `settings.py:1352`) | 7.1, 8.5: `output_id` `(st_dev, st_ino)` checked before every write/sweep/re-make, the folder never created, "output folder is gone or changed"; `test_output_folder_gone`; disk-full semantics in 7.3 |
| Opus I6: the intermediates in the output folder are exposed to sync clients for the job's life | yes (by design) | 8.3: 0700/0600, prepared preview copies removed after the bake, idle sweep, page caveat; D3 records the trade-off; the folder stays per the card's title |
| Opus I7: no proof covers the page's own network use; the netns test skips here | yes (`unshare -rn` refused on this host; no CSP today) | 10.5: CSP header, static-URL test, the shell's request filter; 12.5 and the table say the netns proof is unavailable here |
| agy 1: `panel_argv` branches on exact labels; `TOOL_OF_LABEL` raises for a new `--ascent` label; `SOURCE_WORDS`/`PREVIEW_KINDS` are compared | yes (`presets.py:80-126`, `test_server.py:915-946`) | 9.2: the `panel_argv` branches per label, `TOOL_OF_LABEL`, `_SOURCE_WORDS`, `ALL_SOURCES`, `PREVIEW_KINDS` in the same commit; `PanelArgvTest` row; S5 file list |
| agy 3 / Opus M14: a failed companion source step does not fail the face steps of another font; one HTBL for two fonts; `htbl_companion` remap | yes (`jobs.py:601-604`, `server.py:260`) | 9.2: companion steps planned once, `needs` on steps, the cascade "companion source failed", `_check_steps` on `needs`, `_kept_settings` remaps `htbl_companion`; e2e cases |
| agy 4 / Opus M10: `Store.delete` removes only the metadata directory; sweeps can be lost after a crash; `rmtree` on a dead mount at start | yes (`jobs.py:347-365`) | 8.3: `Store.delete` sweeps the files directory first; `pending-sweeps.json`; start-up sweep on a thread |
| agy 5 / Opus M16: two jobs with one output folder overwrite each other's record; clash check and replace not atomic | yes (by design) | 7.3: one active job per folder (409), `os.link` for new names, `build-<id>/` per job; `test_one_job_per_output_folder` |
| agy 6 / Opus M8: 6.3 buttons vs 10.6 `pickSources()`; cancellation undefined; `openPath` executes files; no SIGTERM on a forced quit; POSIX-only | yes | 6.3, 10.6: `pickFiles`/`pickFolder`/`pickOutputDir`/`openOutputFolder` (no path; `showItemInFolder`), cancellation resolves to `[]`/`null`, 35 s stop wait, POSIX-only stated |
| agy 8 / Opus M7: `_job_preview` has no `Cache-Control`; the probe JSON is `no-cache`; `no-store` never 304s | yes (`server.py:976, 1073`) | 10.4: `no-store` on all six endpoints, the 304 text corrected; `test_no_store_headers` |
| agy 9 / Opus M4: "no symlink component" rejects `/home -> /var/home`, macOS `/tmp`; string overlap checks miss case folding and bind mounts | yes | 7.1: the root itself not a link, resolved once, links below skipped; overlap by inode; entries re-`lstat`ed at run |
| agy 10: `_kept_settings` keyed by root index breaks on reordering | yes (`server.py:227-268` keys by path) | 7.2: keyed by root realpath |
| Opus M1: the zip's `BUILD.md` and `.lines` are under `svf-maker-<id>/`, not at the top | yes (`zipout.py:601-606`) | 7.3, 8.5: `build-<id>/` per job; section 4 corrected; the expected set in `test_no_write_outside_output` |
| Opus M2: the conversion lists were incomplete ("seven joins" naming eleven) | yes (grep: 175 hits) | 8.1 names every function; the S1 plan carries the grep list |
| Opus M3: `srcprep._apply_op`, `_coverage_of_entry`, `_prepared_source`'s extension, `TOOL_OF_LABEL`, `_SOURCE_WORDS` | yes (`srcprep.py:179-216`, `detect.py:1224-1257`, `server.py:1179`) | 9.2 (merged with agy 1) |
| Opus M5: labels and `first_line` can carry input text | yes (`detect.py:327, 1356, 1363`) | 8.2 item 3: type-only labels, traceback not returned for local jobs, `first_line` kept and stated |
| Opus M6: `hmac.compare_digest` on `str` raises for non-ASCII; the token check should precede routing | yes | 10.2 |
| Opus M9: the typed-path fields undercut the consent argument | yes | 6.3: hidden when the bridge exists (decided) |
| Opus M11: S5 in parallel with S3 edits the same files; the `Origin: null` test needs S3 | yes | 13: S5 after S3 (only unwired code in parallel), the test moved to S3 |
| Opus M12: `sniff` tests sizes before Mac tags; 64 MiB JM cap too large; JM re-unpacked per step | yes (`detect.py:118-123`) | 9.2: Mac tags first, `JM_CAP` 4 MiB, the re-unpack noted |
| Opus M13: `--jset-version` is inert on `--mode direct`; `mac_golden` keys by the source stem | yes (`macfbit_svf.py:1180-1199`, `jamoset.py:2710`) | 9.2: `jset_version` dropped from the direct row; the prepared 1.0 fork named `<stem>.rsrc` |
| Opus M15: `sys.executable` and the tool path stay absolute in the note | yes (`zipout._command_lines`) | 8.4: `python3 -P tools/<name>.py`; `test_notes_and_logs` asserts no absolute path |
| Opus M16 (rest): `GET face` of an `identical_to` step; the detect byte cap vs a synchronous request | yes | 8.5: serves `svf/<identical_to>`; 7.1: `LOCAL_BYTES_CAP` 1 GiB with the reason |
| Opus M4 (rest): refuse a source that contains the data root | yes | 7.1 |

Not changed, with the reason: Opus I6's option (b) "do not persist prepared sources for previews when an in-memory
form exists" is taken only as "remove the prepared copy after the bake" (the tools are subprocesses and read files;
an in-memory bake would need a second code path per tool). Opus M10's thread for the start-up sweep is taken; its
`pending-sweeps.json` is kept minimal (a list of directory paths). agy 2's alternative "search every root for a
rel" is rejected in favour of a root on every field (ambiguity is refused, not resolved). No finding was found not
applicable.
