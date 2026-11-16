# SVF maker audit: input kinds, controls, preview, desktop readiness

Card t_c3d8c80b. A read-only audit of `maker/` (detect.py, jobs.py, routes.py, presets.py, settings.py, naming.py,
preview.py, server.py, static/*) against [recipes.md](recipes.md), run on 2026-11-03 at `ec5c6b3` (the curated OFL-only
repository). Evidence is `file:line` at that commit (rows rewritten for this branch cite symbol names, because line numbers drift). "Not verified" marks what was read but not run.

How the maker works, in one paragraph: `detect.sniff` (maker/detect.py:84) tags a file by magic and size,
`_detect_file` (detect.py:331) turns it into font entries with a `source_kind`, `routes.routes` (maker/routes.py:253)
maps a `source_kind` to tool argv, `settings.plan_steps` (maker/settings.py:1036) builds the steps, `jobs.run_command`
(maker/jobs.py:160) runs each tool as a subprocess, `zipout` writes a zip in `svf/` layout. After branch maker-controls
the page draws every produced face and every baked source face itself with the C renderer built to WebAssembly (section
3); the server only draws the source PNG of FreeType-readable sources (`preview.source_png` with Pillow). Sections 1
and 2 below were audited at `ec5c6b3` and are kept as the rows they were, each updated where the branch changed it
("Now:" marks the current state); sections 3 and 7 are the current state.

## 1. Recipe input kinds

Columns: **Detect** = a `source_kind` with a route; **Convert** = the command the route runs; **Preview** = the source
preview (as audited; the result preview of any produced face is now drawn in the page by WASM, section 3).

| Recipe input (recipes.md) | Detect | Convert (tool/command) | Preview | Evidence |
|---|---|---|---|---|
| TTF (static) | yes: `ttf` -> `outline`; composite syllables -> `outline-composite` | precomposed: `mkfont.py SRC TMP --size S --bpp B --unicode ascii,ksx1001-hangul` (or `ascii,hangul`, or a list file), then `svf2to3.py TMP OUT --profile default` as `tools/build/build_faces.py` does (a face equal to a shipped one is byte-equal to it). Jamo: composite -> `jamovec.py master --components [--adaptive]` then `jamovec.py render --binarize threshold --check`; non-composite -> "experimental fit" `jamoset.py --layout 844\|adaptive --from-ttf --binarize threshold\|--bpp 2 --check` | yes, Pillow `source_png` at the first size | detect.py:91, 346-350, 851, 1108; routes.py:113-117, 119-130, 132-141, 263-272; preview.py:118 |
| OTF (CFF) | yes: `otf` -> `outline` (never composite: CFF has none) | same as TTF: mkfont; jamo only via the experimental fit | yes (Pillow/FreeType) | detect.py:93, 346; routes.py:263-272 |
| TTC / OTC | yes: every face (up to 64) is listed; a face after the first, or a face with a Mac-only cmap, carries a `prep` list (`ttc-face`) | a `source` step first: `maker/srcprep.py ttc-face SRC OUT --index N` saves the face as a plain sfnt (`.otf` for CFF), then the TTF/OTF routes read it | yes for every face (`preview.source_png` takes the face index); Now: the preview and the clipping probe read the prepared face (`settings.source_ops`) | maker/detect.py `_ttc_entries`; maker/srcprep.py; routes.py `source_commands`; branch maker-inputs, A3/B1 |
| Variable font | yes: `fvar` axes and named instances are read (`variable` on the entry, label `; variable (wght 100..900)`) | one instance per font per job: setting `instance` adds a `fontTools.varLib.instancer` source op pinning every axis (default overlaid by the choice); the page has an instance select | Now yes: the preview and the probe read the instanced copy (`work/preview/<font>/source.ttf`); as audited: the default instance | settings.py `instance`, `instance_coords`; routes.py `source_commands`; maker.js `perFontInstance`; B2/C1 |
| GSUB-decomposable outline (`ljmo`/`vjmo`/`tjmo`) | Now yes: the GSUB FeatureList is read (`gsub_jamo`, label "; conjoining jamo (GSUB)") | Now a `mask fit` route (`jamoset.py --from-ttf --mask-font SRC --no-clean`, `--pylib DIR`), offered when the font has the jamo features and the libraries load, and a `vector fit` route (`jamovec.py master` without `--components`). The free fit passes `--mask-font none`, so the worker's environment cannot turn the mask on. **No mask-fit job has ever run: freetype-py and uharfbuzz are not installed on the host that built this, so only its argv, offering and refusals are tested.** The vector fit ran on a synthetic font (1.1 s) and its master was timed once outside the maker on NanumGothic Regular: 172 s under heavy | as TTF | routes.py:132-141; jobs.py:66; tools/jamoset.py:2297-2302, 2855 |
| BDF ISO 10646 (Unicode) | yes: `bdf-iso10646`, sizes = the strike FreeType opens | precomposed: mkfont at the strike, 1 bpp only | yes (Pillow) | detect.py:355-373, 516; routes.py:273-276 |
| BDF ISO 8859 | yes: `bdf-iso8859`, used only as a Latin companion | no route of its own | no | detect.py:516; routes.py (no branch); settings companions detect.py:1120-1130 |
| hanterm (johab BDF) | yes: `bdf-johab` (registry contains `johab`/`hanterm`) | `jamoset.py SRC --layout hanterm-johab --check [--eng]` | no: FreeType gives no Unicode charmap, `_draws_sample` refuses | detect.py:516-525; routes.py:153-158, 280-281; preview.py:236 |
| KS X 1001 BDF (KSC5601.1987 / KSX1001) | yes: `bdf-ksc5601` | precomposed: `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST`; needs a Latin companion. Experimental jamo route "bdfface + from-svf fit": `bdfface.py -o precomposed.svf` then `jamoset.py --layout 844\|adaptive --from-svf precomposed.svf --check` | no (same reason) | routes.py `_bdfface_fit_commands`; B4 |
| PCF | yes. A KSC5601/KSX1001 or johab PCF is read by `srcprep.pcf_properties` and becomes `bdf-ksc5601` / `bdf-johab` with a `pcf-bdf` prep op; any other PCF stays a generic `bitmap` (`.pcf.gz` read by FreeType) | `source` step `srcprep.py pcf-bdf IN OUT` (the maker's own reader, no `pcf2bdf`), then the BDF routes; other PCF: mkfont at the strike | KSC/johab: no; other: yes | detect.py `_ksc_pcf_entry`; srcprep.py `pcf_to_bdf`; B3 |
| HBF | yes: `hbf`, as a Latin companion only | no route | no | detect.py:101, 375-383; routes.py (no branch) |
| DOS johab raw (`.FNT`, `*.KOR`, HBIOS, san, 621, Dokkaebi, Kyra) | yes: by exact size (`DOS_SIZES`), candidates filtered by the layout opener; the owner confirms the layout | `jamoset.py SRC --layout L --check [--eng ENG] [--face 0\|1]`; `--eng` = a 2048/4096-byte file beside it | yes: baked with the same command at the first size, then `svfline` | detect.py:29-33, 241-253, 417-436; routes.py:144-150, 277-279; preview.py:146-197; server.py:906-913 |
| DOS `johab844.py` (precomposed from raw pieces) | yes: an 11,520-byte raw font with candidate `844` (`dos_bytes`) | precomposed route `johab844`: `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng ENG]`; layout 844 and an 8x16 English font only; the chosen range is ignored and the note names the base face | n/a | routes.py `_johab844_commands`; settings.py `_route_errors`; B5 |
| HWP `ASCII.PFT` (12x24 English, 12,288 bytes) / HBIOS 12x24 English (15,360) | yes: both are `eng` entries (`eng` = bytes and cell); a 15,360-byte file is HBIOS English only when `hbios_eng_like` (blank margin rows, 12 px cell, ink in `A`), else a Dokkaebi face; no UI override | `jamoset.py --eng FILE` on a DOS jamo route; refused below a 24 px face | no | detect.py `hbios_eng_like`; settings.py `_route_errors`; A5/B6 |
| HWP Hangul `.PFT` | Local mode only (Task 14): an `other` entry, format `hwp-pft`, named by its `.pft` extension (no byte rule) when its size is not an `eng` size, with the label that says to convert it elsewhere and add that file; an upload keeps `unknown (...)`. `ASCII.PFT` (12x24 `eng`) pairs with a 24 px DOS raw face from any folder of the batch (`detect.detect_file`, `HWP_PFT_LABEL`, `scan`) | none: the repository has no reader (recipes: feed a BDF or precomposed SVF) | no | `test_hwp_pft_label`, `test_ascii_pft_from_another_folder`, `test_8x16_eng_keeps_the_folder_rule` (test_detect_inputs.py); no real HWP file was run (`SVF_MAKER_REAL_PFT`) |
| Windows `.FNT` / `.FON` | yes: `fnt`/`fon` -> `bitmap`; FON face 0 only | mkfont at the strike, 1 bpp | yes | detect.py:109-112, 391-415; routes.py:273-276 |
| Mac TrueType with a Unicode cmap (`true` magic) | yes: `ttf` | as TTF | yes | detect.py:90-91 |
| Mac TrueType with only a Mac Korean (1,3) or Wansung (3,5) cmap | yes: `mac_cmap_only` gives the entry a `mac-cmap` prep op and coverage is read through it (a font that also has a Unicode subtable gets none) | `source` step: `macsfnt.py unicode IN OUT`, then the TTF routes | Now yes (the prepared copy is drawn) | detect.py `_sfnt_entry`; srcprep.py `mac_cmap_only`; B1 |
| `.dfont`, suitcase, resource fork, AppleDouble, MacBinary | yes: `mac-rsrc`; one entry per `sfnt` resource (`rsrc-sfnt` op, plus `mac-cmap` when needed); only `NFNT`/`fbit` resources: one `other` entry; a corrupt map: one `unknown` entry | `source` step: `macsfnt.py extract IN OUT --id N` (then `unicode`) | Now yes (the prepared copy is drawn) | detect.py `_mac_head`, `_mac_entries`; B1 |
| Mac HangulTalk 1.0 `fbit` (`--layout mac-fbit-45sets`) | Local mode only (Task 12): `mac-fbit1`, a fork with an `fbit` of 45 sets and its `fdef` 3 (raw fork, AppleDouble, MacBinary); a bare `fbit` resource is an `other` entry that names the missing `fdef` (`detect._mac_fbit1_entry`) | route `mac fbit 1.0`: `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` (`routes._mac10_commands`); a wrapped source ends in `<stem>.rsrc` for jamoset's golden lookup | yes: baked source face | `MacEndToEndTest.test_mac10_end_to_end_and_prepared_name`; Task 12 Step 1 outcome (a) held: the synthetic fixture (`macfx.fbit1_fork`, an all-zero `fdef`) passes `--check`. A real 1.0 font and its golden are not run (`SVF_MAKER_REAL_MAC1`, `RealMac1Test`) |
| Mac HangulTalk 7.1 type-3 `fbit` (+ HTBL) | Local mode only (Task 11): `mac-fbit3` (resource fork, AppleDouble, MacBinary, JM archive, raw `fbit`), `mac-htbl` (the HTBL 1 table, 9,612 or 9,816 bytes raw) and `mac-suitcase` (FOND + NFNT with its strikes); the HTBL and an optional suitcase are companions, each planned as its own source step once, with `needs` on the face steps | routes `mac fbit 7.1 direct` / `derived`: `macfbit_svf.py build SRC HTBL -o OUT --mode ... [--latin]`; `mac fbit 7.1 bdf + mkfont`: `macfbit3.py bdf`, `srcprep.py bdf-pixel-size` (the tool's BDF has no `PIXEL_SIZE`), `mkfont.py`, `svf2to3.py --profile default` | yes: baked source face (needs the HTBL; a chosen suitcase is baked in) | `MacEndToEndTest` (direct verified with `macfbit_svf.py verify` and facecheck, wrapped and JM, derived and bdf + mkfont, gz fork, companion cascade, source face), `LocalKindsTest`, `MacRoutesTest`, `LocalSettingsTest`. A real 7.1.2 font and HTBL are not run (`SVF_MAKER_REAL_MAC3`, `RealMac3Test`) |
| Embedded bitmap strikes (`EBDT`/`bdat`) | yes: `EBLC`/`bloc` strike sizes are listed (`strikes`); an sfnt with strikes and no outlines is a `bitmap` source at those sizes (`sizes_fixed`) | mkfont at the strike (planned and tested; a real bitmap-only font is run only by `SVF_MAKER_REAL_EBDT`) | yes for outline fonts | detect.py `_sfnt_entry`; srcprep.py `embedded_strikes`; A3/B1 |
| WOFF / WOFF2 | no: `unknown` (not a recipe input either) | none | no | detect.py:84-117 |
| SVF v3 (precomposed / jamo) | yes: `svf-precomposed` / `svf-jamo`, with JSET version and JMAP mode | copy, or `svf2to3.py --jset-version V --check`; precomposed 1 bpp also "from-svf fit" `jamoset.py --layout 844\|adaptive --from-svf --check` | yes: copied, then `svfline` | detect.py:438-451; routes.py:224-250, 286-296; preview.py:173-179 |
| SVF v2 | yes: converted to v3 | `svf2to3.py --jset-version 1 --check` | yes | detect.py:103-105, 438-451; routes.py:200-221 |
| SVF v1 | refused ("convert from the original font") | none | no | detect.py:440-441 |
| Archives (zip/tar/gz/xz) | unpacked on upload with guards; `.gz` single files decompressed (128 MiB cap) | n/a | n/a | detect.py:106-107, 120-134; maker/archive.py |

Summary (after branch maker-inputs, card t_f3ef3189): the maker covers static and variable TTF/OTF (one instance per font
per job), every TTC/OTC face, Mac-cmap TTF, dfont/suitcase/AppleDouble/MacBinary, Unicode BDF/PCF/FNT/FON, KSC/johab PCF,
hanterm, KS X 1001 BDF (precomposed, and an experimental `--from-svf` jamo route), all DOS raw layouts of `jamoset.py`,
`johab844.py`, 12x24 English companions and SVF v2/v3. It still has nothing for Mac `fbit` (both generations) and HWP
Hangul `.PFT`. Now (branch maker-controls): GSUB-decomposable fonts get the `mask fit` and `vector fit` routes (the mask
fit never ran here), and the source previews and probes show a chosen variable instance, a TTC face and a Mac font.

## 2. Controls missing compared with the recipes

**As audited at `ec5c6b3`** (the table below keeps the gaps as found; the "Now" column says what the branch added, the
gap list in section 7 says which task closed each): what the page offered then (maker/static/index.html;
maker/static/maker.js:62-83; maker/settings.py:32-37; maker/presets.py:16-60, 63-90): batch kinds (precomposed / jamo), layout (844 / adaptive), sizes (list), bpp (1, 2),
range (2350 / 11172 / an uploaded list), preset, and an advanced panel with `cell`, `ascent`, `space_advance`,
`mono_hint`, `clip_cell` (mkfont) and `embolden`, `symbols`, `jset_version` (jamoset).

| Recipe control | In maker? | Gap (as audited) | Now |
|---|---|---|---|
| AA 2 bpp, precomposed | yes: bpp 2 for outline sources (mkfont `--bpp 2`) | bitmap/BDF/DOS sources are 1 bpp only (routes.py:273-284), which is correct. `--bpp 8` (host faces) not offered | unchanged |
| AA 2 bpp, jamo set | yes for outline: composite route `jamovec.py render --bpp 2`, fit route `jamoset.py --bpp 2` (routes.py:126-141) | `--aa-refine N`, `--clean/--no-clean` not exposed; no level-error number shown beyond `quality.py`'s IoU (maker/quality.py) | `--aa-refine` and `clean` are options (`clean` at 2 bpp only); `binarize` threshold/ridge/mono |
| Baseline / ascent | `--ascent` for mkfont only (presets.py:69-70) | no `--ascent` for jamoset routes (DOS raw, hanterm, fit, from-svf; tools/jamoset.py:2839) nor for bdfface (`--ascent` / `--hangul-ascent`); `--latin` (cap height to the top) not exposed | ascent keys per tool (`ascent`, `jamo_ascent`, `fit_baseline`, `latin_ascent`, `hangul_ascent`), `latin`, an ascent to try in the preview |
| Vertical shift per glyph (`svfdy.py --range --dy`) | no | no step, no control; `svfdy.py` never named in maker/ | a per-font dy table and an `svfdy.py` step on precomposed faces, a dy to try in the preview |
| Top/bottom clipping | `--clip-cell` only | `--fit-cell` (lower size until no ink is cut) not exposed; the cut counts mkfont prints on stdout are only in the build log, not shown per step; no "clipped rows" view before a build | `fit_cell`; cut counts per step from mkfont `--report`; the clipping panel shows the cut rows for any ascent before the build |
| Cell width / fixed advance | only through presets (`--width` in `latin-18cell-2bpp`) | no `--width` field; `--punct-extra`, `--ink-advance`, `--only-listed`, `--fallback-ttf`, `--limit`, `--require` not in the panel; jamoset `--advance`, `--cell` (from-ttf) not exposed | `width` is an option; the other flags are still not exposed |
| Size / bpp / charset | sizes, bpp 1/2, range 2350 / 11172 / list file | named ranges past these two (`ksx1001-nohanja`, `ksx1001-symbols`, `jamo`, `cp949`, `ksx1001`) only via presets; ASCII is always added (`ascii,` prefix, routes.py:98-110) | the five named ranges are selectable (seven in all) |
| Jamo set from decomposable fonts | composite TTF route (`jamovec.py --components`) and a non-native "experimental fit" | no GSUB-mask route (`--mask-font`, `--mask-radius`, `--pylib`), no `jamovec.py master` without `--components` (vector separation at a decision size), no `--binarize mono\|ridge` choice (always `threshold`, routes.py:128, 135) | `mask fit` (never run here), `vector fit` (a master takes minutes: NanumGothic 172 s), `binarize` choice, a `jamo_route` select |
| Piece identity check | no | the routes run `--check`, which proves the table composes all 11,172 syllables, not that each piece is its jamo. `quality.py` scores IoU against the reference only. No jamo recogniser is in this repository (grep for "recogni" in tools/ finds only JMAP_RECOG flag handling); the card t_9acea7ab requirement needs one brought in or written | `maker/recog_score.py` per jamo step when `SVF_RECOG_DIR` names a recogniser; **no real recogniser was run: a stub only** (none is in this repository) |
| Mac/HWP options (`--symbols` for fbit, `--mode derived`, `jamomerge.py`, `jamoexc.py`) | no | none of these tools is called | unchanged |

## 3. Preview: the browser draws with the WASM renderer

**State (card t_9acea7ab).** Every produced face and every baked source face is drawn in the page by the C renderer
built to WebAssembly (`maker/build-wasm.sh` into `maker/static/wasm/`, the compile line shared with `web/build.sh`
through `c/ports/web/emcc-flags.sh`). `svfline.py` stays the byte-for-byte oracle (`tools/test_web_picker.py`
`TestModule`, which also pins the page's per-glyph compositor and its target decoders). The worker no longer writes a
result PNG.

- **Endpoints that serve bytes** (`maker/server.py`, all GET, `no-cache`, host-checked; the byte files carry an ETag and answer `If-None-Match` with 304, the generated probe JSON does not): `face/<step>.svf`
  (a done face step only), `source/<font>.svf` (the baked source of a DOS raw or SVF entry), `repo/face/<group>/<FILE>`
  (the Latin companion `dos/NEODG16.SVF`), `report/<step>.json`, `probe/<font>/<size>/<bpp>.(svf|json)`,
  `identity/<step>.json`; `/api/caps` says which optional parts exist.
- **Exports** of `c/ports/web/svf_web.c` beyond the draw path: `svfw_metrics`, `svfw_cell_bytes`, `svfw_glyph`,
  `svfw_pieces`, `svfw_cmap_cp`, `svfw_line_box` (thin calls into `svf.h`; `c/src` is unchanged).
- **The page** (`maker/static/svfview.js`, `maker.js`): a result cell per done step with the sample text, scale, target
  (GRAY8, MONO, RGB565), threshold, guides, the glyph grid, and an ascent to try (`dos raw`/`hanterm`) or a dy to try
  (precomposed) that the per-glyph compositor draws without a rebuild (`drawGlyphsInto`, which follows `walk_next`);
  applying one re-opens a finished job and saves it. The step row shows the mkfont report (`cut N`, `nudged N`, `fit at
  S px`); a jamo step shows the identity verdict and, opened, its pieces.
- **Clipping before the build** (`mkfont --probe` / `--report`, `clip.js`): the probe is baked from the step's own
  argv (`settings.face_argv` / `probe_argv`) in a cell that cuts nothing; the "clipping" panel computes the rows any
  ascent would cut with `fit_counts`' rule and draws them over the probe face.
- **What stays server-drawn:** the source PNG of FreeType-readable sources (Pillow, `preview.source_png`); the PNG of
  baked sources is still written by the server (and tested) but the page draws those with WASM.
- **Caps:** `wasm` (the module is built), `mask_libs` (freetype-py and uharfbuzz for `mask fit` and `binarize mono`),
  `recog` (`SVF_RECOG_DIR` with numpy and torch for the identity check).

## 4. Electron shell with a Python sidecar on 127.0.0.1

What exists and what would change:

| Area | Today | Change for Electron + sidecar |
|---|---|---|
| Bind | `SVF_MAKER_BIND`, default `127.0.0.1:8766`; no host means 127.0.0.1 (server.py:118-125, 993-997) | bind `127.0.0.1:0` and print the real port (the server already prints "listening on host:port", server.py:999); Electron reads it from stdout |
| Tailnet | only the spec says tailnet (`docs/superpowers/specs/2026-10-21-svf-maker-design.md:80-81, 504-523`, 100.78.108.85); no code assumes it | none in code; the unit/README of T15 would be the only place |
| Auth | none; state-changing requests check `Host` in {127.0.0.1, localhost, ::1, bound host} and `Origin` same host+port (server.py:380-403) | add a per-launch token (env from Electron, header on every request) since any local process can reach 127.0.0.1; a `file://` page sends `Origin: null` and would be refused, so the window must load `http://127.0.0.1:PORT/` (verified: a foreign Origin gets 403) |
| Repo dir | `SVF_MAKER_REPO`, default the checkout above `maker/` (server.py:994); the server needs `tools/` (every tool), `svf/` (name clashes, licence texts, NEODG16 Latin fallback), `web/mkindex.py` and `web/LICENCES.tsv`/`FAMILIES.tsv` readers (maker/zipout.py:273-292, 409-420; maker/naming.py:129-142; preview.py:202-216), and `git rev-parse HEAD` (zipout.py:78-88, "unknown" without git) | ship `tools/`, `svf/`(or a subset), `web/mkindex.py` as data; make the "repo head" a build id |
| Tool launch | every tool is `[sys.executable, "-P", tools/X.py]` (routes.py:20) | under PyInstaller `sys.executable` is the frozen sidecar, not python: either ship a real python, or give the sidecar a `run-tool NAME ARGS` entry point and build argv from it (card t_e64a56a7) |
| Data / temp dirs | `SVF_MAKER_DATA`, default `~/.local/share/svf-maker`; per job `upload/ work/ out/`; at most 20 jobs, 7 days (server.py:995; jobs.py:42-48) | use Electron's `app.getPath('userData')`; keep the retention |
| Upload limits | body 64 MiB, job 256 MiB, 2,000 files (server.py:41-43); `.gz` 128 MiB decompressed (detect.py:44) | keep for uploads; a path mode needs none of the copy limits but keeps the decompression cap |
| Subprocess env | explicit `ENV` with PATH/HOME/LANG only (jobs.py:66; preview.py:48) | add `JAMOSET_PYLIB`/`JAMOSET_MASK_FONT` pass-through if the GSUB route is added |
| systemd | no unit in the repository (plan Task 15 not done) | not needed for Electron (Electron owns the sidecar's life); keep the unit for the server use |
| Page | `static/` served by the sidecar, `<input type=file webkitdirectory>` uploads (static/index.html:38) | works inside Electron unchanged; native dialogs and drag-and-drop would pass paths (below) |
| Output | a zip download from `GET /api/jobs/<id>/zip` (server.py:974-983) | Electron saves it, or the sidecar writes into a chosen folder (path mode) |

**Local-only mode for proprietary inputs** (Mac fbit, HWP, other non-OFL fonts): today every input is copied into the
job's `upload/` through `PUT /api/jobs/<id>/files?path=` (server.py:567-632); previews and the zip are written under
the job directory. A local mode would: accept a list of absolute paths (from Electron's dialog) through a new endpoint
that only the token holder may call; detect and convert from those paths in place (detect already works on paths;
`plan_steps` takes `upload_dir`, settings.py:1016-1027, which would become a per-font source root); write outputs only
into the chosen output folder, with work files in a temp dir removed after the job; never copy a source into the data
dir, never write it into the zip (the zip today holds only produced faces and licence texts, zipout.py). Its test must
show the listen socket is 127.0.0.1 only and that nothing is written outside the output folder and the temp dir.

## 5. The web UI v1 plan and the open cards

Plan `docs/superpowers/plans/2026-10-21-svf-maker.md` (16 tasks). Its checkboxes are all unticked (82 `- [ ]`, 0 `- [x]`)
and it carries no "Implemented" notes; the state below comes from the files and `docs/STATUS.md:29, 120`
("대부분 done, systemd unit·문서·end-to-end 시험과 web UI v1 남음"; merged 837f525 on 10-23, LIST support 0d73568 on
10-28; neither commit is in this curated history).

| Plan task | State in this tree |
|---|---|
| 1-13 (cmap_has, fixtures, detect, scan, presets/routes, naming, settings, quality, zip, previews, archive, jobs, server) | done: modules and tests present; tests green (below) |
| 14 the page | done: `maker/static/index.html`, `maker.js` (1,327 lines), `style.css`; the ids the plan lists are present (`files`, `folder`, `upload`, `state`, `notice`, `fonts`, `settings`, `advanced`, `save`, `run`, `cancel`, `download`, `steps`, `jobs`, `position`) |
| 15 systemd unit, README, `.gitignore`, docs line | **not done**: no `maker/svf-maker.service`, no `maker/README.md` |
| 16 end-to-end, preset acceptance, slow fit, UI smoke | **not done**: no `maker/test/test_maker.py`, no `maker/test/smoke.mjs` |

Cards: t_a1cf496b (web UI v1 goal; close needs a systemd service on the tailnet converting a TTF+BDF+PCF+DOS test
folder into a zip that passes `facecheck.py`, plus reviews) is open because T15 (t_bbceabe9) and T16 (t_e073891a)
remain. With the 2026-11-03 direction (Electron, local), the tailnet-service half of t_a1cf496b's closing measurement
is out of date; T16's end-to-end and preset tests stay useful as written; T15's unit and README are needed only if the
server deployment is kept.

## 6. Run state (2026-11-03, this worktree)

- `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`: **Ran 431 tests in 77.3 s, OK**
  (one ResourceWarning from tools/jamoset.py:1808, an unclosed file in a test).
- `tools/test_web_picker.py` (the WASM vs svfline oracle): 44 tests OK, 1 skipped (TestPage, no playwright-core).
- Server: `SVF_MAKER_REPO=<worktree> SVF_MAKER_DATA=<tmp> SVF_MAKER_BIND=127.0.0.1:18766 python3 -P maker/server.py`
  printed "svf-maker listening on 127.0.0.1:18766"; `GET /` 200, 4,910 bytes, title "SVF maker"; `GET /api/repo`
  200 (folders `dos`, `jamo-extra`); `POST /api/jobs` 200 `{"id": ...}`; the same POST with `Origin:
  http://evil.example` 403 "cross-origin request". No upload or conversion was run through the server.

**Closing run state (Task 15, branch maker-controls).** maker suite via heavy: 666 tests OK (10 skipped: no playwright,
freetype-py/uharfbuzz, numpy, `SVF_MAKER_REAL_*`); `tools/test_*.py` via heavy: 967 tests OK (17 skipped), `test_web_picker`
included; `make -C c check` via heavy: exit 0; `sh c/cross/test-check-features.sh`: OK; `maker/test/smoke_dom.py`: exit 0
under google-chrome; `git diff 01a943f -- c/src c/include`: empty.

## 7. Gap list (priority order) and the card each belongs to

1. **t_9acea7ab** - DONE (Tasks 6-8): the page draws produced faces with the WASM renderer; `GET .../face/<step>.svf`;
   `svfline` PNG is only the test oracle.
2. **t_9acea7ab** - DONE (Tasks 1, 7): the exports `svfw_metrics`, `svfw_glyph`, `svfw_pieces`, `svfw_cmap_cp`,
   `svfw_line_box`; the ascent and dy overrides are done by the page's compositor (no hook in `c/src`).
3. **t_9acea7ab** - DONE (Tasks 4, 5, 9, 10, 11): ascent keys per tool, `--fit-cell`, `--width`, `--latin`, the
   `svfdy.py` step with a dy table, the mkfont `--report` and cut counts per step, the clipping probe and panel,
   `--aa-refine`, `--binarize`, `clean`, the seven named ranges.
4. **t_9acea7ab** - DONE (Tasks 3, 12, 14): the `mask fit` route (`--mask-font`, `--pylib`) and the `vector fit` route
   (`jamovec.py master` without `--components`); the identity check runs `maker/recog_score.py` when `SVF_RECOG_DIR`
   names a recogniser (none is in this repository; only a stub ran). **Not verified:** no mask-fit job has run (no freetype-py/uharfbuzz on this host); the vector fit ran on a synthetic fixture (1.1 s) and its master on NanumGothic took 172 s under heavy. Source previews and the probe read the
   prepared font (Task 13).
5. **t_f3ef3189** - input kinds: done on branch maker-inputs (see section 1: VF instance, TTC faces, Mac TTF and containers,
   KSC/johab PCF, `johab844.py`, 12x24 `--eng`, `--from-svf` after `bdfface`, strike sizes). What remains of it: source and
   instance previews (t_9acea7ab), local-only mode and Mac `fbit` (t_cbd14d61), Electron, packaging, the jamo recogniser.
6. **t_cbd14d61** - DONE (Tasks 1-15, branch maker-local): local-only mode with path-based sources, Mac `fbit` (both
   generations) and the HWP lines only there; outputs only in the chosen folder; 127.0.0.1 proven by test. Closing
   evidence and the open items are in section 8.
7. **t_f04f1355** - Electron: port 0 + stdout handshake, per-launch token, load over http (not file://), userData as
   data root, native dialogs passing paths to the local mode, sidecar stops with the window.
8. **t_e64a56a7** - packaging: replace `[sys.executable, "-P", tool]` (routes.py:20) with a sidecar tool entry
   point; ship `tools/`, the `svf/` subset and `web/mkindex.py`; repo head as a build id; Pillow/FreeType/fontTools in
   the bundle.
9. **t_bbceabe9 / t_e073891a / t_a1cf496b** - T16 tests are still worth landing (they exercise the routes end to
   end); T15's unit/README and the tailnet clause of t_a1cf496b should be re-scoped to the desktop direction.

## 8. Local mode: closing evidence, the shell contract and what was not verified (card t_cbd14d61)

**The card's closing measurement, mapped to tests** (all synthetic; no proprietary byte is in the repository):

| Closing measurement | Evidence |
|---|---|
| Synthetic Mac/HWP-like files convert through local mode | `MacEndToEndTest` (test_plan_inputs.py: 7.1 direct, derived, bdf + mkfont, wrapped, JM, gz, companion failure cascade, 1.0 end to end); `test_ascii_pft_from_another_folder` (detection) and the DOS raw job of `LocalRunTest` |
| Network off, 127.0.0.1 only | `LocalBindTest` (token, loopback-only bind, `main()` refusals); `NoNetworkTest.test_static_no_network_imports`, `test_network_off_in_process`, `test_network_off_namespace` (skips where `unshare -rn` is refused) |
| README states no proprietary font is distributed | `test_readme_and_notice_wording` (test_server.py) |
| Nothing is written outside the chosen output folder | `LocalSweepTest.test_no_write_outside_output`, `WriteTreeTest` (descriptor-relative writes, linked or swapped folders, replaced or removed output folder) |
| Inputs never copied into the data directory | `LocalJobTest.test_no_upload_copy`, `LocalSweepTest.test_final_no_upload_copy`, `LocalPrivacyTest` (no input byte or exception message in any persistent artifact) |

**What the Electron shell (card t_f04f1355) must do with this server**
- Start `python3 -P maker/server.py` with `SVF_MAKER_TOKEN` (32 lower-case hex characters, new each launch),
  `SVF_MAKER_BIND=127.0.0.1:0` (a non-loopback bind is refused, exit 2), `SVF_MAKER_DATA` under `userData`, optionally
  `SVF_MAKER_ROOTS` (a colon-separated allow-list for sources and the output folder). Read the port from the stdout
  line `svf-maker listening on 127.0.0.1:<port>`.
- Load the page from `http://127.0.0.1:<port>/` (never `file://`: the `Host`/`Origin` checks refuse it) and add
  `X-Maker-Token: <token>` to every request to `/api/` (exactly one header; `/` and `/static/*` need none but must carry
  a `Host` naming the server). The page and the token never meet: the shell adds the header, the page never sends it.
- Expose `window.svfMaker` (preload, `contextIsolation`-safe) with `pickFiles()` and `pickFolder()` (each resolves to an
  array of absolute paths, `[]`/`null` for a cancelled dialog), `pickOutputDir()` (a path string or `null`) and
  `openOutputFolder()` (called with no argument; the shell opens the job's output folder itself). With the bridge the page
  hides its typed-path fields; without it the page takes typed paths.
- Stop the server with SIGTERM (or SIGINT): the running job is cancelled, its tool processes killed, every files
  directory swept. Do not SIGKILL it if it can be avoided: a killed run leaves `.svf-maker-<id>/` until the next start
  (the start-up sweep removes it, and a pending-sweeps record keeps a failed removal).
- The page asks once per session for the acknowledgement that converting a font is the user's responsibility; the shell
  need not.

**Not verified** (no way to run it on the host that built this; each is stated where it matters in the code and tests):
the `unshare -rn` run (refused on the host; the static import scan and the in-process socket guard are the gate, and
the guard cannot see tool subprocesses nor the user's own `recog.py` named by `SVF_RECOG_DIR`); real Apple HangulTalk
7.1.2 and 1.0 files, real HWP `.PFT` files and a real 7.1.2 HTBL (the `SVF_MAKER_REAL_*` tests skip); macOS named
resource forks on a Mac; Electron, its preload, `contextIsolation`, native dialogs and `shell.showItemInFolder` (a fake
`window.svfMaker` stands in); FAT, exFAT and SMB/NAS mounts (the no-hard-link fallback and a refused `chmod` are
exercised by mocks); a real disk-full condition (mocked); a case-insensitive filesystem; an inode overlap spelled any way
but a symlinked parent; sync clients reading `.svf-maker-<id>/`; and `sessionStorage` persistence across a real
Electron relaunch.

**Bounded lifecycle (t_d1aba4b8).** This replaces the earlier "accepted trade-off (lifecycle lock)" and "known limits of
the cleanup". What is bounded now, and what is not.

- **Per section.** Every lifecycle-lock section of a request or of the idle sweeper (`ensure_files_dir`'s calls, the
  stats and the rename of `_rename_away`, the pending record a local `delete` writes, the commit check of a run) has one
  `Deadline` of `LOCKED_IO_S` (5 s) for all its calls together, not per call. A job-lock wait taken under the lifecycle
  lock and the I/O that follows it each get `LOCKED_IO_S`; a preview lock is only try-locked (`PREVIEW_TRY_S`). A second
  request on the same hung path shares the call already in flight, inside its own section's bound.
- **Exceptions.** Start-up cleanup uses `STARTUP_CLEANUP_S` (30 s) and stop uses `STOP_SWEEP_TOTAL_S` (8 s) as their one
  deadline for every wait (lifecycle lock, preview locks, stats, renames, removals, pending records); they are not capped
  at `LOCKED_IO_S`. A pass overruns its deadline by at most a few pending floors (about 2 s: the records of one pass, then the flush), inside the
  margins of `desktop/lib/budget.js`. The data root (`job.json`, `Store.list`, `log.md`) is assumed to be a local disk
  and is not bounded.
- **The fence.** A rename that is abandoned (timed out) stays registered as in flight and keeps its path fenced:
  `ensure_files_dir` refuses to make a new generation at that name, and the sweeps record it as pending, so a late
  rename can only move the generation it was issued for. Read-only calls (stat, listdir) share the one in flight.
  **Accepted limit:** a rename or mkdir that never returns (a dead hard mount) keeps that one job's files directory
  fenced until the process restarts: its previews answer 404 with "the files directory is still being moved or made on
  a slow or hung volume". Nothing else is held.
- **The pending record.** Every read and write of `pending-sweeps.json` goes through one writer thread; a caller waits
  until its deadline, but at least `PENDING_FLOOR_S` (0.5 s) when the writer is idle, and no floor while an earlier
  operation is unfinished. An operation not waited for still runs later, in order. Stop and start-up flush the writer
  before they return. `delete` of a local job saves its cleanup record before it removes the metadata; when the record
  cannot be saved the job stays and DELETE answers 409 busy.
- **A local `POST run` has three sections.** Prepare (short, under the lifecycle lock: checks, the files directory, the
  preview try-locks, the `preparing` marker), read and plan (no store lock: input stats, licence hashing, planning,
  range copies), commit (under the lifecycle lock: files directory still current, then the state and a fingerprint of the
  job re-checked inside the job lock). A hung input volume therefore no longer delays creates, activations or sweeps of
  other jobs.
- **Lock order restored.** lifecycle lock -> job lock -> preview locks -> pending lock, everywhere. `PUT settings`
  saves under the job lock and clears the changed fonts' previews afterwards, outside it; `_preview_dir` makes the
  directory before it takes the preview lock.
- **Client-visible changes (accepted).** 409 `"job X is busy; try again"` when a job lock or the cleanup record is not
  available in time (DELETE, create takeover, run activation, ensure); 409 `"a run of job X is being prepared"` (a preview adds
  "; try again"); 409 `"the job changed while the run was being prepared: run again"`; 409 `"job X is busy: a
  preview is being made; try again"`
  from `POST run` when a bake holds a preview lock longer than `LOCKED_IO_S`; DELETE may answer 409 busy when its cleanup
  record cannot be saved (the job stays; a retry works once the writer recovers); a create takeover that fails with a
  busy holder answers 409 busy and leaves the holder (swept when idle); a bake that lands between saving settings and
  clearing previews is dropped and redrawn (the W2 window, narrowed). The page shows the error text; automatic retry of
  these 409s is a separate card.
- **Not bounded.** The data root; a never-returning rename or mkdir (above); the volume's own recovery (a hung call keeps
  its daemon thread until it returns).

Evidence (tests in `maker/test/test_local_bounds.py` unless named):

| Bound | Tests |
|---|---|
| fence, shared reads, pending writer | `test_rename_bounded_abandons_a_hung_rename_and_fences_the_path`, `test_a_read_only_call_waits_for_the_one_in_flight`, `test_pending_op_returns_by_the_deadline_while_the_pending_lock_is_held`, `test_pending_op_returns_by_the_deadline_while_fsync_hangs`, `test_pending_op_with_an_expired_deadline_still_lands_on_a_healthy_disk`, `test_records_after_a_stalled_one_do_not_wait_the_floor`, `test_the_pending_writer_exits_when_idle_and_restarts` |
| stop and sweeps | `test_stop_returns_by_the_deadline_although_a_rename_hangs`, `test_an_abandoned_rename_never_moves_a_later_generation`, `test_stop_returns_by_the_deadline_while_fsync_hangs`, `test_stop_lands_its_pending_records_before_returning`, `test_an_idle_sweep_does_not_wait_beyond_its_deadline_for_the_lifecycle_lock`, `test_a_retry_starts_no_filesystem_call_after_its_deadline` |
| delete records before it forgets | `test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job`, `test_the_only_job_of_a_folder_leaves_a_findable_tombstone_when_deleted`, `test_a_failed_takeover_that_cannot_record_answers_409_busy_and_keeps_the_job` |
| start-up | `test_startup_returns_by_the_deadline_although_a_rename_hangs`, `test_startup_with_several_hung_tombstones_returns_by_the_single_deadline`, `test_startup_returns_by_the_deadline_although_listdir_hangs`, `test_startup_with_hung_tombstones_and_a_stalled_writer_returns_by_the_deadline`, `test_an_orphan_tombstone_is_swept_at_start_up` |
| locked I/O, lock order | `test_a_create_is_not_held_by_a_hung_output_stat_in_ensure`, `test_a_create_is_not_held_by_a_hung_mkdir`, `test_a_lifecycle_holder_does_not_wait_for_a_held_job_lock`, `test_a_preview_and_a_settings_change_of_one_font_do_not_deadlock`, `test_a_settings_put_never_waits_for_a_preview_lock_under_the_job_lock`, `test_after_a_settings_put_returns_the_old_preview_is_never_served` |
| run prepare and commit | `test_a_create_is_not_held_by_a_run_reading_a_hung_input`, `test_a_create_is_not_held_by_a_run_hashing_a_hung_licence`, `test_a_create_is_not_held_by_a_run_planning_on_a_hung_volume`, `test_run_preparation_holds_no_lifecycle_lock`, `test_a_run_whose_job_changed_while_preparing_is_refused`, `test_a_second_run_during_preparation_is_refused`, `test_a_run_waits_a_bounded_time_for_a_preview_lock` |

## 9. Desktop app: closing evidence (cards t_f04f1355 shell, t_e64a56a7 packaging)

| Closing measurement | Evidence |
|---|---|
| The shell opens the app on Linux, picks files and folders through the bridge, converts a sample into an output folder and quits cleanly with no orphan | `desktop/test/e2e.js` (`bridge`, `flow`, `open-folder`, guards, restart, privacy; dev and packaged passes, 30 checks) and `desktop/test/lifecycle.test.js` (close, SIGTERM, SIGKILL of the shell, second instance); the release check's `smoke` |
| A frozen sidecar converts the OFL sample set byte-identically to source mode in a clean environment without python on PATH | `maker/test/test_frozen.py` (26 tests, `FrozenByteEqualTest`, `test_frozen_jobs_match_source`, `test_frozen_notes_equal_source` under an empty PATH and `env -i`), again on the extracted AppImage with no skip (`release-check.sh` `frozen`) |
| An AppImage builds with a local script and runs | `desktop/build/build-appimage.sh`; the extracted `AppRun` smoke (no FUSE on the host) |
| THIRD-PARTY generation | `desktop/test/third-party.test.js` (12 tests) and the `licences` check over the extraction |
| Windows and macOS steps documented as UNVERIFIED | `docs/maker-desktop.md` |

Orphan and lifecycle rules (`maker/toolreg.py`, `--exit-with-parent`, `instance.lock`) are tested in `test_toolreg.py`,
`test_server_signals.py` and `test_frozen.py`. Not verified: see `docs/maker-desktop.md`.
