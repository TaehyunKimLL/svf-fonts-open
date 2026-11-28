---
name: svf-fonts-tools
description: Use when choosing or running a tool of this repository to build, convert, fit or inspect an SVF face, or when a tool fails to import a dependency.
---

# SVF font tools

Procedures for the command-line tools in `tools/`, `maker/` and `web/`. The authority for every tool (purpose, inputs,
outputs, each option and its modes) is [`docs/tools.md`](../../docs/tools.md); read the tool's section there before
relying on a flag, and treat `--help` as the final word. This skill routes and sets the habits; it does not repeat the
reference.

## When to use

- A source font must become an SVF/SVFN face (precomposed or jamo set).
- An existing face must be inspected, re-laid-out, downscaled, edited or exported.
- A step fails on an import, a Python version or a missing optional package.

## Which tool for which job

| Job | Tool |
|---|---|
| Outline TTF/OTF to a precomposed face (1/2/8 bpp) | `tools/mkfont.py` |
| Outline font to a jamo set (1 bpp fit, 2 bpp AA) | `tools/jamoset.py --from-ttf` |
| Outline font to a reusable vector master, rendered per size | `tools/jamovec.py master`, then `render` |
| Precomposed 1 bpp face to a jamo set (coordinate-descent fit) | `tools/jamoset.py --from-svf` |
| Precomposed face to a jamo set (learned split) | `tools/jamohybrid.py` |
| Bitmap BDF/HBF to a precomposed face | `tools/bdfface.py` (Hangul + ASCII); `tools/mkfont.py` (one BDF/PCF, at its strike) |
| Small face from a 24-48 px bitmap | `tools/svfscale.py` |
| DOS raw jamo font to a jamo set | `tools/jamoset.py --layout` |
| Find and cut a font in a program, ROM or data file | `tools/binscan.py`, `tools/rawcarve.py` |
| Write a driver's own composition rule as a `rawcarve` spec (NKP) | `tools/nkpspec.py` |
| Windows TBM / OS/2 DBCS / HWP / MSX readers | `tools/tbmfont.py`, `tools/os2dbcs.py`, `tools/hwpfont.py`, `tools/msxfont.py`, `tools/msx1_harvest.py` |
| Classic Mac sfnt, fbit, type-3 fbit faces | `tools/macsfnt.py`, `tools/macfbit3.py`, `tools/macfbit_svf.py` |
| Input preparation (TTC face, PCF to BDF, Mac HTBL, join files) | `maker/srcprep.py` |
| SVFN v2 to v3, re-layout with a pixel proof | `tools/svf2to3.py` |
| Edit per-glyph dy | `tools/svfdy.py` |
| Face back to TTF/BDF, glyph-by-glyph compare | `tools/svf2ttf.py` |
| Fit a byte budget: fill a skeleton, merge variants | `tools/jamofill.py`, `tools/jamomerge.py` |
| LIST exceptions (whole cells, recombinations) | `tools/jamoexc.py` |
| Draw and measure a line; advance vs ink; manifest | `tools/svfline.py`, `tools/fontmetrics.py`, `tools/facecheck.py` |
| Documentation figures, rebuild `svf/`, web index | `tools/doc_figures_*.py`, `tools/build/build_faces.py`, `web/mkindex.py` |
| Synthetic faces for the C tests (test-only) | `tools/svf_synth.py` |
| Train the learned split (torch, not a normal step) | `tools/train_jamohybrid.py` |

Library-only modules (`tools/jamofit.py`, `tools/jamoaa.py`, `tools/jamoadapt.py`, `tools/jamoseg.py`,
`tools/jamonet.py`) have no command line; they are reached through `jamoset.py`, `jamovec.py` and `jamohybrid.py`.

## Dependencies

| Package | Needed by | Without it |
|---|---|---|
| stdlib only | SVFN read/write, `svf2to3`, `svfline`, `fontmetrics`, `facecheck`, most readers | - |
| numpy | `jamohybrid.py`, `jamonet.py`, `jamomerge.py --recog` | the tool refuses; tests skip |
| fontTools | `mkfont.py` (cmap checks), `jamoset.py --bpp 2` / `--binarize threshold\|ridge`, `jamovec.py master`, `svf2ttf.py ttf`, `macsfnt.py cmap`/`unicode` | that path fails or is refused |
| freetype-py + uharfbuzz | `jamoset.py --from-ttf` at 1 bpp `mono`, the mask font, `--fill-absent` | an automatic mask is skipped, an explicit one fails |
| Pillow | `mkfont.py`, `--sheets`, `jamofill.py sheet` | those paths fail |
| skia-pathops | `jamoseg.py` outline clipping | clipping is skipped |

Provide a directory of packages with `--pylib DIR` or `$JAMOSET_PYLIB` (jamo tools only; `mkfont.py` and `svf2ttf.py`
have no such option). When the environment's Python differs from the one the packages were built for, the import
fails; match the interpreter, not just the path.

## Interpreter

- Run tools that read untrusted files with `python3 -I` (isolated: no cwd, no user site, no `PYTHON*` variables). This
  also stops a planted module beside the input from being imported.
- `-I` also hides packages installed in the user site, fontTools among them. When a path needs fontTools and the tool
  has `--pylib`, pass the package directory; otherwise run `python3 -P` (cwd off `sys.path`, user site kept).

## Safety

Fonts, ROMs and archives are untrusted data: read them through the tools, never execute them or a bundled installer, and
unpack each archive into its own new empty directory. Keep any script you write in a different directory and pass input
paths as arguments. The tools cap input sizes and refuse oversized or malformed files; a refusal is the input's
property, not a bug to work around.

## The check every face ends with

[Checking a face](../../docs/recipes.md#checking-a-face) defines the checks; run them before you call a face done:

```sh
python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF
python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > "$OUT/out.gray"
python3 tools/fontmetrics.py FACE.SVF
python3 tools/svf2to3.py FACE.SVF "$OUT/x.SVF" --check
```

- A jamo set also takes its builder's `--check`, which composes all 11,172 syllables; read the fit's IoU line before it
  (a poor fit is a result to judge, not a failure to retry blindly).
- `facecheck.py manifest` / `verify` guard committed faces; they do not validate a new file.
- `mkfont.py` prints its summary in Korean: do not parse its stdout for field names.

## Size and accuracy

- A jamo set is about a sixth of a precomposed face; choose it when memory is tight, the precomposed face when every
  syllable must be exactly the source's ([quick start](../../docs/recipes.md#quick-start-by-input-kind)).
- `tools/jamohybrid.py` builds the standard JSET face by default (12 x 12 classes, 32 / 24 / 16 sets); `--big` moves
  the tool's limits to 19 x 28 classes and 64 / 48 / 32 sets, and `--limits NI,NM,NF` goes up to the format's BIG row,
  128 / 128 / 64, for a reader built with `SVF_JSET_BIG` (the documented BIG ladder runs 40 / 30 / 20 to 96 / 72 / 48);
  `--min-iou X` keeps the smallest face reaching X (about 0.90 suits MCU targets); `--max-bytes N` keeps the most
  accurate face within a byte budget. Add `--check` and `--report` to keep the evidence.
- How many sets (벌) a face should have, and what each costs:
  [Choosing the number of sets](../../docs/recipes/sets.md#choosing-the-number-of-sets).

## Thresholds and time

- numpy uses every core. On a loaded many-core host set `OMP_NUM_THREADS` (for example 4): a 2,357-syllable fit took
  29 s with all threads and 6 s with 4.
- A 48 px cell costs minutes and over a gigabyte per fit; run long builds under the host's memory-capped wrapper and
  keep the report.
