**English** | [한국어](maker-audit.ko.md)

# SVF maker capability audit

This page describes the maker's inputs, routes, controls, previews and runtime boundaries.
See the [desktop app](desktop-app.md) for use, [desktop implementation](maker-desktop.md) for packaging,
[recipes](recipes.md#desktop-app-and-maker-routes) for command-line equivalents, and
[the maker guide](../maker/README.md) for the HTTP API.

## 1. Inputs and conversion routes

`routes()` in `maker/routes.py` offers the routes. **Native** classifies a default route for that input kind;
it does not promise lossless preservation of the entire source. Non-native routes need the font's `experimental` permission.

| Input | Precomposed route | Jamo-set routes and conditions |
|---|---|---|
| Outline TTF/OTF | `mkfont` | `composite` for composite-glyph fonts; otherwise `experimental fit`; `mask fit` for fonts with GSUB jamo substitution; `vector fit` |
| TTC, variable fonts, Mac cmaps/containers | Prepare the selected face, instance or character mapping, then use its route | Routes above according to the prepared font's kind |
| Bitmap-only sfnt, ISO 10646 BDF/PCF | `mkfont`, existing sizes, 1 bpp | No direct route |
| KS C 5601 BDF/PCF | `bdfface`, needs a Latin companion | `bdfface + from-svf fit` (experimental) |
| Hanterm Johab BDF/PCF | No direct route | `hanterm`, layout `hanterm-johab` |
| ISO 8859 BDF, HBF | No independent route | Used only as a Latin companion for KS C 5601 |
| DOS raw Johab fonts | `johab844` for supported 16 px 8x4x4 input | `dos raw`; confirm a layout from the candidates inferred from file size |
| HWP 1.x `.SFT`/`.PFT` | `hwp bdf + mkfont` | `hwp1`; local mode only |
| HWP 3.0 `.FNT`, headerless KS X 1001 dumps | `hwp bdf + mkfont` | `hwp3 844` for 16 px HWP 3.0; `hwp bdf + from-svf fit` (experimental) |
| Mac HangulTalk 1.0 | No direct route | `mac fbit 1.0`; needs a resource fork with `fdef`, local only |
| Mac HangulTalk 7.1 type-3 `fbit` | `mac fbit 7.1 bdf + mkfont` | `mac fbit 7.1 direct`, `mac fbit 7.1 derived` (experimental); needs HTBL, local only |
| Existing SVF v2/v3 (1 or 2 bpp) | `copy`, or `svf2ttf` for TTF/BDF only | `copy`/`svf2ttf` for jamo faces; `from-svf fit` for 1 bpp precomposed faces (experimental) |
| Known ROM sets | `bdfface` or another recipe-specified route | Recipe-specific `spec`, `dos raw`, fit, etc.; local only, with size/SHA-256 and companion-file checks |

HWP 1.x and header-identified HWP 3.0 convert only in local mode. Headerless KS dumps also work in upload mode.
The `copy` route converts SVF v2 to v3; SVF v1 and 8 bpp SVF have no maker route.
HWP `.HFT` and `.PFT` layouts without a decoder have no conversion route. Unrecognised inputs or missing companions
are shown with a reason; rows without a route cannot be selected. ROM recipes live in `maker/recipes/`.

`maker/detect.py` handles detection, `maker/srcprep.py` prepares fonts, and `maker/settings.py` validates routes.
Synthetic input checks include `test_detect_inputs.py`, `test_plan_inputs.py`, `test_hwp_inputs.py` and
`test_recipe.py` under `maker/test/`. Real-file checks require the corresponding `SVF_MAKER_REAL_*` variables.

## 2. Controls and tool mapping

| Control | Current behaviour | Implementation |
|---|---|---|
| Batch defaults | `dest=dos`, precomposed, `layout=844`, size 16, bpp 1 and 2, range `2350`, preset `plain` | `settings.BATCH_DEFAULTS` |
| Range | `2350`, `11172`, `ksx1001-nohanja`, `ksx1001-symbols`, `ksx1001`, `jamo`, `cp949`, or a list file in the batch; ASCII added to generated ranges | `settings.RANGE_FILES`, `routes.py` |
| Cell, ascent, advance | `mkfont` cell/ascent/width/space advance; `jamoset` header ascent/fit baseline; `bdfface` Latin/Hangul ascent | `presets.panel_argv()` |
| Clipping | `clip_cell`, `fit_cell`, pre-build probe and clipped-row display; mkfont report shows cuts, nudges and fitted size | `settings.py`, `maker/static/clip.js`, `tools/mkfont.py` |
| Jamo fitting | `aa_refine`, 2 bpp `clean`, 1 bpp `binarize` (threshold/ridge/mono); only values supported by the route are accepted | `presets.py`, `settings.py` |
| Per-glyph vertical shift | Applies a precomposed face's dy table through an `svfdy.py` step; can be tried in preview | `settings.py`, `maker/static/svfview.js` |
| Export | TTF/BDF and jamo TTF `--composite`; all off by default, per-font overrides allowed | `settings.DEFAULT_OPTIONS`, `jobs.py`, `tools/svf2ttf.py` |
| Piece identity | Scores from an optional external recogniser; no bundled model | `caps.py`, `recog_score.py` |

Not every font can use these batch defaults unchanged. Bitmap routes, for example, restrict sizes and bpp;
settings are validated before saving or running. Advanced options override presets; per-font values override batch values.
The UI does not expose every command-line flag, including `--punct-extra`, `--ink-advance` and `--fallback-ttf`.
See the [tool reference](tools.md) for the full options.

`mask fit` and `binarize mono` require freetype-py and uharfbuzz; `JAMOSET_PYLIB` can name their directory.
`JAMOSET_MASK_FONT` names the mask font. Recognition uses `recog.py` under `SVF_RECOG_DIR` and optionally
`SVF_RECOG_PYTHON`. An external interpreter must pass imports of numpy, torch, PIL and fontTools.

## 3. Preview and quality checks

The page draws produced faces with a WASM build of the C renderer. `maker/build-wasm.sh` and `web/build.sh` share
`c/ports/web/emcc-flags.sh`. See the [SVF specification](../spec/SVF.md) for structure and metrics,
[jamo sets](jamo-sets.md) for composition, and [anti-aliasing](anti-aliasing.md) for coverage and target colours.

`maker/static/svfview.js` provides text, scale, GRAY8/MONO/RGB565 targets, threshold, guides and a glyph grid.
The page's glyph compositor implements ascent/dy trials. `preview.source_png()` on the server creates source PNGs
for FreeType-readable fonts; the page's result SVF display does not depend on server PNGs.

Under `/api/jobs/<id>/`, endpoints include `face/<step>.svf`, `source/<font>.svf`, `report/<step>.json`,
`probe/<font>/<size>/<bpp>.svf`/`.json` and `identity/<step>.json`.
The four public `/api/caps` keys are `wasm`, `mask_libs`, `recog` and `local`.
C/WASM exports are in `c/ports/web/svf_web.c`; see the [web renderer guide](web-renderer-guide.md) for use.

Checking composition of all 11,172 modern Hangul syllables with `--check` differs from deciding whether each piece
is the intended jamo. IoU measures overlap with a reference bitmap and does not guarantee readability.
TTF/BDF exports are read back to check their character sets; re-rasterising a TTF for a round trip is not part of every run.

## 4. Local mode and desktop boundaries

Token-enabled local mode allows loopback binding only. It reads selected sources in place and writes results and
temporary files under the output folder without copying sources into the data folder. Job metadata is stored
separately in the data folder. Path checks cover absolute paths, symlinks, input/output overlap, the data folder and
the `SVF_MAKER_ROOTS` allow-list. Temporary `.svf-maker-<id>/` directories are cleaned up; failed cleanup leaves a
record for retry on the next start.

Without a token, the server uses upload mode. Limits are 64 MiB per request body, 256 MiB and 2,000 files per job,
and 128 MiB for gzip decompression. Local mode avoids upload-copy limits but retains format-specific read limits.
The server prunes old finished jobs using a 20-job limit and a 7-day age from creation. A detected local job untouched
for 30 minutes can lose its working-files directory (`server.LOCAL_IDLE_SWEEP_S`).

Electron creates a token per launch, chooses a data folder under `userData` and manages the sidecar lifecycle.
See the [desktop app](desktop-app.md) for security, failure handling and paths.
A directly launched server forwards `SOURCE_DATE_EPOCH` to tools; the desktop shell's environment allow-list omits it.

## 5. Verification boundaries

- Automated input tests use synthetic files. Users must provide real Mac, HWP and ROM sources separately.
- Command-line mask-fit runs are recorded in [recipes](recipes.md); these do not establish an end-to-end maker `mask fit` run.
- A real piece-recognition model is unverified; integration tests use a stub.
- Desktop automation stubs dialogs and disables the GPU. Real dialogs, file-manager integration, a window manager, GPU and sandbox need separate checks.
- Windows/macOS packages and older glibc compatibility are unverified. No server-deployment systemd unit is supplied.

See [packaging](maker-desktop.md#5-automated-checks-and-recorded-runs) for tests and package verification,
the [C guide](c-renderer-guide.md) for integration, the [renderer design](../spec/renderer-design.md) for architecture,
and the [README](../README.md) for the document overview.

## 6. 참고 문헌 / References

- Unicode Hangul composition — <https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/>
- OpenType Hangul shaping — <https://learn.microsoft.com/en-us/typography/script-development/hangul>
