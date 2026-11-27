**English** | [한국어](recipes.ko.md)

# Recipes: from a font to an SVF face

Build a precomposed SVF face or a jamo set from outline fonts, bitmap fonts, raw jamo files and font ROMs.
Start with the input-format table below. For jamo-set design see [jamo sets](jamo-sets.md); for anti-aliasing see [anti-aliasing](anti-aliasing.md). See the [tool reference](tools.md) for options and the [SVF format](../spec/SVF.md)
for the binary format and [glossary](../spec/SVF.md#glossary).

Commands run from the project root. Set an output directory first; replace uppercase input names with your own files:

    OUT=${TMPDIR:-/tmp}/svf-recipes
    mkdir -p "$OUT"

Outline conversions need Pillow and fontTools in the selected Python environment. With `python3 -I`, user-site
packages are excluded; jamo tools can load an existing dependency directory through `--pylib DIR`.

Conversion commands write to the output paths shown. Brackets in command templates mark optional arguments; do not type
the brackets or alternatives literally. Source files for proprietary fonts must be supplied separately.

After `mkfont.py`, use `svf2to3.py --profile default --check` to select the `default` record layout and check pixel equality
([Precomposed faces](#precomposed-faces-mkfontpy)). Other target profiles are described in the
[renderer design](../spec/renderer-design.md).

Numerical examples are measurements for the named inputs and settings. Sizes and run times can change with tool and
font versions. *Synthetic* examples use test-generated inputs. A fit's IoU comes from the fit report; `--check` checks
composition and table consistency, without imposing a minimum IoU.

Contents:

- [Quick start: by input kind](#quick-start-by-input-kind)
- [Checking a face](#checking-a-face)
- [Outline fonts](#outline-fonts)
- [Bitmap fonts](#bitmap-fonts)
- [DOS-era raw fonts](#dos-era-raw-fonts)
- [Finding a font inside a program or data file, with Claude](#finding-a-font-inside-a-program-or-data-file-with-claude)
- [Korean MSX fonts (MSX2 and MSX1)](#korean-msx-fonts-msx2-and-msx1)
- [Korean font ROMs in MAME sets](#korean-font-roms-in-mame-sets)
- [OS/2 Korean fonts (완성형) to a precomposed face and a jamo set](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set)
- [A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font)
- [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts)
- [An existing SVF](#an-existing-svf)
- [An SVF face back to a TTF bitmap font](#an-svf-face-back-to-a-ttf-bitmap-font)
- [Choosing the number of sets (벌 수)](#choosing-the-number-of-sets-벌-수)
- [Desktop app and maker routes](#desktop-app-and-maker-routes)
- [Faces of svf/](#faces-of-svf)
- [Reference](#reference)
- [Adding a face to svf/](#adding-a-face-to-svf)
- [References](#references)

<a id="quick-start-by-input-kind"></a>

## 1. Quick start: by input kind

Find what you hold; the row names the way and the section with the commands. "Pre" is a precomposed face (every
syllable a glyph, 1 or 2 bpp), "jamo" a jamo set (pieces and a table, 1 bpp or 2 bpp; about a sixth of the size).

| You hold | Pre | Jamo | Section |
|---|---|---|---|
| TTF, or OTF (CFF) with a Unicode cmap | `mkfont.py` (1, 2 bpp), then `svf2to3.py --profile default` | `jamoset.py --from-ttf` (1 bpp: `--binarize threshold --mask-font none`; 2 bpp: `--bpp 2`); `jamovec.py` for a font of composite syllables | [Outline fonts](#outline-fonts) |
| TTC / OTC (Noto CJK) | `srcprep.py ttc-face` to a plain font, then as above | as above | [TTC and OTC](#ttc-and-otc) |
| Variable font | `fontTools.varLib.instancer`, then as above | as above | [Variable fonts](#variable-fonts) |
| Mac TrueType (`.dfont`, suitcase, a Korean-only cmap) | `macsfnt.py extract` / `unicode`, then as above | as above | [Mac-format TrueType](#mac-format-truetype) |
| Outline font with embedded strikes (`EBDT`, `bdat`) | `mkfont.py --size` the strike's size, 1 bpp | no | [Embedded bitmap strikes](#embedded-bitmap-strikes) |
| BDF or PCF in Unicode (`ISO10646`) | `mkfont.py` at the file's own pixel size, 1 bpp | fit with `jamoset.py --from-svf` | [ISO 10646 BDF and PCF](#iso-10646-bdf-and-pcf) |
| BDF or PCF in KS C 5601 / KS X 1001 (X Window) | `srcprep.py pcf-bdf` (PCF only), then `bdfface.py` | `jamoset.py --from-svf` | [KS C 5601 BDF and PCF](#ks-c-5601-bdf-and-pcf) |
| hanterm johab BDF | no | `jamoset.py --layout hanterm-johab` | [hanterm](#hanterm) |
| HBF | only as the ASCII half of `bdfface.py` | no | [HBF](#hbf) |
| Windows `.FNT` / `.FON` | no reader (FreeType gives it no Unicode map; convert it to a BDF with an outside tool first) | no | [Windows FNT and FON](#windows-fnt-and-fon) |
| DOS raw jamo-piece font (8x4x4 `HANGUL.FNT`, san, Dokkaebi, Kyra...) | `johab844.py` (16 px 8x4x4) | `jamoset.py --layout L` | [DOS-era raw fonts](#dos-era-raw-fonts) |
| HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT` | `hwpfont.py bdf --face N`, then `mkfont.py` | `jamoset.py --layout hwp1 --face N` (HWP's own rule, exact) | [HWP 1.x and 2.x fonts](#hwp-1x-and-2x-fonts) |
| HWP 3.0 `HAN*.FNT` (2,350 syllables, + an 8x4x4 set at 16 px) | `hwpfont.py bdf`, then `mkfont.py` | `jamoset.py --layout 844-hwp3` (16 px), else `--from-svf` | [HWP 3.0 FNT fonts](#hwp-30-fnt-fonts) |
| KS X 1001 raw dump (2,350 syllables in code order, or a 94 x 94 table) | `hwpfont.py bdf` (16-48 px dumps), or `rawcarve.py bdf --dense` / `--grid`; then `mkfont.py` or `bdfface.py` | `jamoset.py --from-svf` | [KS X 1001 raw dumps](#ks-x-1001-raw-dumps) |
| A font inside a program or ROM (DOS driver or TSR, word processor, Korean VGA BIOS + font ROM) | `binscan.py` to find, `rawcarve.py` to cut (raw, BDF, or composed by the driver's rule), then `bdfface.py` | `jamoset.py --layout 844` on a cut raw font, or `--from-svf` | [Finding a font inside a program or data file, with Claude](#finding-a-font-inside-a-program-or-data-file-with-claude) |
| Korean MSX ROMs (Daewoo, Goldstar: MSX2 SUB-ROM, CPC-400S font ROM, MSX1 BIOS) | `rawcarve.py compose` + `bdfface.py` (MSX2), `msxfont.py kfn-map` + `rawcarve.py bdf --chars map` + `bdfface.py` (CPC-400S), `msxfont.py msx1` + `mkfont.py` (MSX1) | `jamoset.py --layout spec --spec tools/specs/msx2-daewoo.json` (MSX2, exact) | [Korean MSX fonts](#korean-msx-fonts-msx2-and-msx1) |
| A Korean machine's or arcade game's ROMs in a MAME set (inverted jamo ROMs, multi-bit sprite tiles) | `rawcarve.py region` + `ink --gfx` (or `--invert`), `rawcarve.py bdf --dense`, then `bdfface.py` | `jamoset.py --layout spec` (a font with its own rule, exact), `--layout 844` on a cut 8x4x4 font, or `--from-svf` | [Korean font ROMs in MAME sets](#korean-font-roms-in-mame-sets) |
| OS/2 Korean System DBCS font (`$korZN16.FNT`, `$korZN24.FNT`; 완성형) | `os2dbcs.py table`, `rawcarve.py bdf --grid 0xA1,0xA1,94`, `bdfface.py` | `jamoset.py --from-svf` | [OS/2 Korean fonts (완성형)](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set) |
| TTF with jamo glyphs (conjoining jamo, PUA pieces, GSUB `ljmo`) | as any TTF | composites `jamovec.py --components`; variants `--mask-font`; else a fit | [TrueType fonts that already carry jamo](#truetype-fonts-that-already-carry-jamo) |
| A 24-48 px bitmap face wanted at 16 px or 2 bpp | `svfscale.py --size 16 [--bpp 2]` | `jamoset.py --from-svf` (1 bpp result) | [A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font) |
| Mac HangulTalk 1.0 `fbit` (45 sets + `fdef`) | no | `jamoset.py --layout mac-fbit-45sets` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| Mac HangulTalk 7.1 type-3 `fbit` + HTBL 1 | `macfbit3.py bdf` + `mkfont.py` | `macfbit_svf.py build` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| An SVF face | `svfdy.py`, `svf2to3.py` | `jamoset.py --from-svf` (1 bpp source) | [An existing SVF](#an-existing-svf) |
| An SVF face, wanted back as a TTF (or BDF) bitmap font | `svf2ttf.py ttf` (or `bdf`) | the same: every syllable composed, a precomposed font (`--composite`: the pieces shared, syllables composite glyphs) | [An SVF face back to a TTF bitmap font](#an-svf-face-back-to-a-ttf-bitmap-font) |

How many sets a jamo set should have: [Choosing the number of sets](#choosing-the-number-of-sets). Anti-aliased faces:
[2 bpp anti-aliased faces](#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font).

The check for every row is the same: [Checking a face](#checking-a-face) (sample-line measure and ink, fit IoU for
a jamo set). Encoding monochrome source pixels at the same size adds no intermediate coverage; resampling to a smaller size (`svfscale.py --bpp 2`) can produce intermediate levels. Choose the jamo set when the
target has little memory (the 2,350-syllable 16 px examples are about 115 KB and their jamo sets about 20 KB), the precomposed face
when every syllable must be exactly the source's.

<a id="checking-a-face"></a>

## 2. Checking a face

<a id="checks-for-a-new-face"></a>

Every recipe below ends with the same checks. The sample line is `안녕하세요 ABC 123`; the faces are 16 px in a 16x16 cell
unless stated.

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF       # width=W ascent=A descent=D
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray   # a 200x24 GRAY8 buffer
    python3 tools/fontmetrics.py FACE.SVF                                 # glyphs whose ink reaches past the advance
    python3 tools/svf2to3.py FACE.SVF $OUT/x.SVF --check                  # re-layout and compare every glyph
    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf -o $OUT/m.tsv
    python3 tools/facecheck.py verify $OUT/m.tsv

- The size of the file and the glyph count (the code point table's entries) come from the tool's own summary line;
  `mkfont.py` prints it in Korean (`글리프 2446개 ... 125,520 바이트`).
- The ink is the number of non-zero bytes of the `line` buffer: `python3 -c "import sys;print(sum(1 for b in open(sys.argv[1],'rb').read() if b))" $OUT/out.gray`.
  A face that draws nothing has ink 0.
  The 200x24 buffer and baseline 16 above fit a 16 px cell. For a face whose cell C is not 16 (12, 15, 24, 40, 48 px) the
  recipes' ink numbers are from `line 400 C+8 0 C` (a 400-wide buffer, the baseline at the cell height, C+8 rows: the
  buffer must be at least as wide as the measured width and as tall as the cell plus descent, or the line is clipped):
  `python3 tools/svfline.py line 400 32 0 24 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray` for a 24 px face. Use a wider buffer for measured widths above 200 (or 400 in the larger-cell template); those exceptions are shown below.
- A jamo set is judged by `--check` (on `jamoset.py` and `jamovec.py`): it composes all 11,172 syllables from the pieces
  and fails on a table error; the fit line before it prints the IoU of the pieces against the source's syllables
  (`fit: 11172 syllables, IoU 0.817`). `--check` does not fail on a poor fit: read the IoU, and look at the result
  (`svfline.py line`, or the `web/` picker).
- `svf2to3.py --check` compares glyph by glyph through `svfline`. The `facecheck.py` commands above record committed
  files at `HEAD`, then compare working files with that manifest; they do not validate a new `FACE.SVF`.
  `tools/build/build_faces.py` rebuilds the faces of `svf/` (see [Faces of svf/](#faces-of-svf)).

Reference run (verified), NanumGothic Bold at 16 px (below): 1 bpp `125,520` bytes, 2,446 glyphs, `width=146 ascent=14
descent=2`, ink 677.

<a id="outline-fonts"></a>

## 3. Outline fonts

FreeType reads TrueType and CFF (OpenType `.otf`) alike, so a static TTF or OTF with a Unicode cmap goes straight into
the tools; `jamoset.py --from-ttf`, `jamoaa.py`, `jamovec.py` and `--binarize threshold|ridge` flatten the outlines
themselves (fontTools pen, exact-area coverage), the same for both. Collections, variable fonts and Mac-format fonts need
one step first (below).

<a id="precomposed-faces-mkfontpy"></a>

### 3.1. Precomposed faces (`mkfont.py`)

Source: `ttf/nanumgothic/NanumGothic-Bold.ttf`. Precomposed, 1 bpp, then the canonical layout step:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-1bpp.svf \
        --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/ng16-1bpp.svf $OUT/NG16.SVF --profile default --check

Verified: `125,520 bytes` (the tmp from `mkfont.py`), 2,446 glyphs (2,350 Hangul syllables); renders `width=146 ascent=14
descent=2`, ink 677. `svf2to3.py ... --profile default --check` writes 125,520 bytes again (the same glyphs; only the record order differs, byte 813 is the first byte that does) and reports `data_in=86332 data_out=86332`.

`mkfont.py` writes the records in its own order; `svf2to3.py --profile default` re-lays them out in the canonical order of
the `default` profile (the shipped faces, `tools/build/build_faces.py` and the maker all end with this step), proving
pixel equality with `--check`. Use `--profile` of another target (`mcu-strict`, `dos`, `wasm`, `full`, `simd16`) to lay
the face out for it.

Anti-aliased (2 bpp): the same command with `--bpp 2` (`195,760 bytes`, 2,446 glyphs, `width=146 ascent=14 descent=2`,
ink 847; coverage is quantised to four levels). The canonical step again keeps the size (195,760 bytes) and proves the pixels equal. `--bpp 8` keeps full coverage (8 bpp faces are for hosts). The
`mkfont.py` options that choose size, cell, ascent and clipping are in
[Baseline, vertical shift and clipping](#baseline-vertical-shift-and-clipping); the full row recipe of `svf/` is in
[The precomposed recipe](#the-precomposed-recipe-mkfont-rows).

**A character set is required** (`--unicode SET`, or `--chars-from FILE`): without either, `mkfont.py` exits 2. The names
are in [Reference](#reference).

<a id="opentype-cff-otf"></a>

### 3.2. OpenType CFF (`.otf`)

Noto Sans CJK KR is a CFF font a reader can get (SIL OFL 1.1; Debian's `fonts-noto-cjk` ships it as
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`, a collection of the KR, JP, SC, TC and HK faces: see
[TTC and OTC](#ttc-and-otc)). Save the KR face as a plain `.otf` and bake it ([Font sources and licences](#ref-fonts)):

    python3 maker/srcprep.py ttc-face /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc $OUT/NotoSansCJKkr.otf --index 1
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-2bpp.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --binarize threshold \
        --mask-font none --check -o $OUT/noto16-jamo-1bpp.svf
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --bpp 2 --check -o $OUT/noto16-jamo-2bpp.svf

Verified (the full font, not a subset): the face is named "Noto Sans CJK KR"; 1 bpp `125,196 bytes`, 2,446 glyphs, `width=141
ascent=11 descent=5`, ink 472; 2 bpp `197,992 bytes`, ink 700; the jamo set `19,040 bytes`, 439 glyphs, 344 pieces,
IoU 0.786 over 11,172 syllables (6.9 s), `width=146 ascent=14 descent=2`, ink 477; the 2 bpp jamo set `23,268 bytes`, 439 glyphs, level error 0.208, IoU at level 2 0.781, 62 s, `width=141 ascent=14 descent=2`, ink 722 (these Noto fits score 0.786 and 0.781, compared with 0.817 and 0.822 for NanumGothic; this comparison does not establish a difference between outline formats). The `mkfont.py` faces use the font's metrics to choose ascent, so
another font's faces differ in baseline: see [Baseline, vertical shift and clipping](#baseline-vertical-shift-and-clipping).

<a id="jamo-sets-from-truetype-and-opentype-fonts"></a>

### 3.3. Jamo sets from TrueType and OpenType fonts

A jamo set (조합형) holds pieces and a table. At 1 bpp, a composed syllable is the OR of two or three pieces;
at 2 bpp, composition takes the maximum level at each pixel. See [Jamo sets](jamo-sets.md). From an outline font there
are three ways to get the pieces, by what the font holds.

**1. Composite glyphs (TrueType `glyf`).** Some fonts store a syllable as a composite of its jamo glyphs. Then the
components *are* the pieces:

    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 1 --check -o $OUT/NEOVEC16.SVF
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

Verified: neodgm.ttf has 11,172 composite syllables; `master` took 25 s (344 pieces, 0 bad shapes), the 1 bpp render
15,724 bytes and the 2 bpp render 19,452 bytes, both 11,172 syllables composed. The vector render differs from the
raster fit NEODG16A in 2,633 of 11,172 syllables (measurement of 2026-11-03; FreeType's pixel snapping of a pixel font against `jamovec`'s exact-area
rasteriser). Check a font first:

    python3 -c "from fontTools.ttLib import TTFont; f=TTFont('FONT.ttf'); c=f.getBestCmap(); g=f['glyf']; print(sum(g[c[x]].isComposite() for x in c if 0xAC00<=x<=0xD7A3))"

In `ttf/`: neodgm 11,172 composite syllables; NanumGothic Regular/Bold and NanumMyeongjo Bold 8,822 (the syllables
outside KS X 1001 are composites, the 2,350 are not); NanumPenScript 8,693; the others none. `--components` with a
partly composite font uses the composites only (the Python API's `components="auto"` picks components when most syllables are composite; the CLI requires `--components`).
**CFF / CFF2 has no TrueType `glyf` composite structure for this route.** The tools treat the syllables as outlines,
so use one of the next two routes.

**2. Conjoining-jamo shaping (GSUB `ljmo` / `vjmo` / `tjmo`).** A font with these features draws the conjoining jamo
U+1100.. in positional variants. `jamoset.py --from-ttf ... --mask-font FONT` shapes each syllable as conjoining jamo with
HarfBuzz and uses the variants as masks that confine the fitted pieces (needs `freetype-py` and `uharfbuzz`;
`--pylib DIR` points at them). Run here with the two modules installed into a scratch folder
(`pip install --target $OUT/pylib freetype-py uharfbuzz`, then `--pylib` that folder; nothing is installed into
the system or the user site):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/neodgm/neodgm.ttf --size 16 --binarize threshold \
        --mask-font ttf/neodgm/neodgm.ttf --no-clean --check --pylib $OUT/pylib -o $OUT/NEO16M.SVF

neodgm.ttf (`ttf/`) has the three features and serves as its own mask font: `15,740 bytes`, 439 glyphs, 344 pieces, IoU
1.000 over 11,172 syllables (3.6 s), 11,008 of them exact, `width=144 ascent=12 descent=4`, ink 559. The free fit of the
same font (`--mask-font none`) is `16,376 bytes`, 11,172 exact, in 3.6 s too: the mask spends fewer bytes (the pieces
are confined to their variants) and gives up some exact syllables to do it. On fonts whose conjoining pieces differ
from their precomposed syllables the mask fits worse than it helps: Noto Sans CJK KR (the OFL font of the
[OpenType CFF](#opentype-cff-otf) recipe) `16,396 bytes`, IoU 0.752 (free fit 0.786), 6.5 s, ink 450; Malgun Gothic
(Microsoft, Windows; proprietary) `16,212 bytes`, IoU 0.753 (free fit 0.766, `18,368 bytes`), 5.7 s, ink 413. With the
modules present the default `--binarize mono` runs too (neodgm: IoU 1.000, 0.8 s, `16,376 bytes`). The maker offers the
`mask fit` route only when the server finds the two modules (`/api/caps` `mask_libs`); with them the routes of neodgm.ttf,
Noto Sans CJK KR and Malgun Gothic include it (checked with `routes.routes` on `detect.scan` entries whose `mask_ok` was set).
`jamoset.py --from-ttf` and `--from-svf` also use a mask font on their own when `$JAMOSET_MASK_FONT`
names one (or a NotoSansKR sits beside the ScummVM tree) and both modules are present: the free fit comes first, and the
mask is used only when that fit's mean IoU is below 0.995 (`AUTO_EXACT`; a face that already is an OR of pieces keeps the
free fit); without the modules it prints a note on stderr and fits freely. Pass `--mask-font none` to force the free fit,
as the 1 bpp commands of this chapter do. The maker passes it on its `experimental fit` route only; its `from-svf fit` and
`bdfface + from-svf fit` routes leave it automatic.

**3. Fitting to the precomposed syllables** (any font, TrueType or CFF):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 \
        --binarize threshold --mask-font none --check -o $OUT/NG16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-ttf ttf/gowunbatang/GowunBatang-Bold.ttf --size 20 \
        --binarize threshold --mask-font none --check -o $OUT/GB20J.SVF

Verified (2026-11-22): NanumGothic Bold 16 px into 8x4x4 took 12 s, 20,064 bytes, 344 pieces, IoU 0.817 over 11,172 syllables;
Gowun Batang Bold 20 px adaptive took 89 s, 73,220 bytes, 32/24/12 sets and 12 x 12 classes, IoU 0.934. `jamofit.py`
fits the pieces (coordinate descent over the 1 bpp syllables), `jamoadapt.py` splits sets where the syllables sharing a
piece disagree (`--layout adaptive[:NI,NM,NF]`), `jamoseg.py` separates a syllable's outline into its jamo as outlines
(used by `jamoaa.py` and `jamovec.py`), and `jamovec.py master` without `--components` separates once at a decision size
and renders every size from the same pieces. `--binarize mono` (the default) needs freetype-py; `threshold` and `ridge`
use the exact-area rasteriser (fontTools pen, so TrueType and CFF alike). A fit is an approximation:
read the IoU, and look at the result (`web/` picker, or `svfline.py line`).

**Pitfalls.** A font that draws few syllables (Black Han Sans: 2,581) fits only those (`--present-only`, the default);
the rest compose from the nearest pieces. `--check` composes all 11,172 syllables and fails on a table error, not on
a poor fit.

<a id="truetype-fonts-that-already-carry-jamo"></a>

### 3.4. TrueType fonts that already carry jamo

Some Korean fonts carry jamo glyphs besides their syllables. Whether a tool can use them depends on how the font links
them to the syllables. Survey a folder first (`fontTools`: the cmap entries in U+1100-11FF, in the Private Use Area
U+E000-F8FF, the composite syllables, the GSUB features `ljmo` / `vjmo` / `tjmo`); the following cases need different routes:

| What the font holds | Example (here) | Route | Section |
|---|---|---|---|
| GSUB `ljmo`/`vjmo`/`tjmo`: positional variants of U+1100.. | NanumMyeongjo / NanumBarunGothic YetHangul (250 variants reached), UnBatang (164) | the variants as masks (`--mask-font FONT`) | [way 2](#jamo-sets-from-truetype-and-opentype-fonts) |
| composite syllables whose components are PUA piece glyphs | the Un fonts (UnDotum, UnBatang, UnGraphic, UnDinaru, UnGungseo, UnPilgi: 11,172 composites each) | `jamovec.py master --components` | [way 1](#jamo-sets-from-truetype-and-opentype-fonts), below |
| conjoining jamo U+1100.. drawn to overlap (vowel and final advance 0, placed left of the pen) and no variants | UnDotum (U+1100 advance 1000, U+1161 and U+11A8 advance 0 with negative x) | way 2 with one shape a jamo, or way 3 | below |
| PUA positional jamo variants, no composites, no GSUB | MiraeroNormal (2,544 PUA glyphs at U+E000-E9EF: old and modern jamo in several positions each) | none: the rule is not in the font | below |

**(a) Conjoining jamo drawn for composition.** UnDotum (Un fonts 1.0.2, `fonts-unfonts-core` of Debian; GPL 2) has the 67
modern conjoining jamo (146 with old ones) and no GSUB: HarfBuzz shapes 가 as U+1100 + U+1161, one glyph a jamo, the
vowel drawn over the consonant because its advance is 0. Way 2 takes those as masks (one mask a jamo, so every set of a
role gets the same mask) and way 3 fits freely:

    python3 tools/jamoset.py --layout 844 --from-ttf UnDotum.ttf --size 16 --binarize threshold \
        --mask-font UnDotum.ttf --no-clean --check --pylib $OUT/pylib -o $OUT/UND16M.SVF
    python3 tools/jamoset.py --layout 844 --from-ttf UnDotum.ttf --size 16 --binarize threshold \
        --mask-font none --no-clean --check -o $OUT/UND16F.SVF

Mask fit `15,620 bytes`, IoU 0.761 (p5 0.518), 0 exact, 7.5 s, `width=149 ascent=13 descent=3`, ink 371; free fit
`17,908 bytes`, IoU 0.840, 776 exact, 7.8 s, ink 493 (the precomposed `mkfont.py` face: `124,480 bytes`, ink 472). One
mask a jamo confines the pieces of all eight initial sets to the same shape, which the syllables do not have: for a font
like this the free fit is the better jamo set, and the composites read with `--adaptive` below are better still.

**(b) PUA piece glyphs.** The Un fonts store every syllable as a composite of two or three PUA glyphs named `jamo0000`
.. (UnDotum: 2,048 PUA glyphs at U+EA60-F25F, 1,991 of them used by the 11,172 composites: 가 = `jamo0000` +
`jamo0019`, 과 = `jamo0220` + `jamo0239`): the PUA glyphs are the font's own piece sets, and the composites are the rule.
Way 1 reads them:

    python3 tools/jamovec.py master UnDotum.ttf -o $OUT/undotum.json --components
    python3 tools/jamovec.py render $OUT/undotum.json --size 16 --bpp 1 --check -o $OUT/UNDVEC16.SVF
    python3 tools/jamovec.py render $OUT/undotum.json --size 16 --bpp 2 --check -o $OUT/UNDVEC16A.SVF

`master` took 36 s: the 1,991 components were sorted into the 8x4x4 slots (344 pieces, the medoid of each slot's
components; 5,576 donor shapes were outliers of their slot, as the font has more variants than 8x4x4 has sets). The
1 bpp render is `16,356 bytes`, `--check` composes all 11,172 syllables, `width=149 ascent=13 descent=3`, ink 472; the
2 bpp render `21,348 bytes`, ink 716. With `master --components --adaptive` (124 s) the pieces keep more of the font's
own variants: 1,436 pieces in the default adaptive budget, 1 bpp `62,976 bytes`, ink 476; 2 bpp `79,088 bytes`, ink 728.
Against the precomposed `mkfont.py` face of the same font (`svfscale.overlap`, mean IoU of the 2,350 syllables; the two
rasterisers differ, so exact agreement is not guaranteed): mask fit 0.648, 8x4x4 components 0.734, free fit 0.755, adaptive
components 0.840.

A font whose PUA holds positional jamo but whose syllables are plain outlines and which has no GSUB reaching the PUA
(MiraeroNormal: no composite syllable, no GSUB) gives no tool the rule that picks a variant for a syllable: the PUA
code assignment (which code is which jamo in which position) and the selection by vowel and final are the font maker's
scheme, written nowhere in the file. Such a font goes through way 3 like any other; using its PUA pieces would need
that scheme as a table (in the shape of a `rawcarve.py compose` spec, but drawing outline glyphs by code point, which
no tool does).

**(c) GSUB `ljmo` / `vjmo` / `tjmo`.** The mask fit of [way 2](#jamo-sets-from-truetype-and-opentype-fonts) (neodgm,
Noto Sans CJK KR, Malgun Gothic measured there).

<a id="2-bpp-anti-aliased-faces-from-a-truetypeopentype-font"></a>

### 3.5. 2 bpp anti-aliased faces from a TrueType/OpenType font

<a id="anti-aliased-2-bpp-faces"></a>

A 2 bpp face stores four levels per pixel (0, 1, 2, 3; coverage = level × 85). The outline-font routes below
produce these levels from rasterised outlines. A monochrome bitmap has only coverage 0 and 255 at its own size;
a grayscale bitmap may already have intermediate coverage. Downsampling a larger bitmap can also produce intermediate
levels ([A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font)).
Three outline-font routes:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-2.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 --bpp 2 \
        --check -o $OUT/NG16JA.SVF
    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

**What shapes the levels.** `mkfont.py --bpp 2` draws each glyph with FreeType's anti-aliased renderer through Pillow
(the font's hinting as FreeType applies it by default) and quantises the 8-bit coverage as `(coverage x 3 + 127) // 255`;
it has no gamma, threshold, oversampling or hinting option for 2 bpp (`--mono-hint` is for `--bpp 1` and is refused
otherwise), so the size (`--size`, and `--cell` / `--ascent` for placement) is the only control. `jamoset.py --bpp 2`
(`jamoaa.py`) rasterises the syllables with its own exact-area coverage (no hinting), lets the regions of a 1 bpp fit
decide which piece owns each pixel, sets each piece's levels to the median over the syllables sharing it and then
refines them against the level error: `--aa-refine N` (2 passes; 0 = the median only), `--clean` / `--no-clean` (on for
2 bpp: pieces confined to where their jamo's contours put ink, faint levels only where half the syllables have them),
and the set system (`--layout 844` or `adaptive[:NI,NM,NF]`, [Choosing the number of sets](#choosing-the-number-of-sets)).
`jamovec.py render --bpp 2` (the default) draws a vector master's pieces with the same exact-area coverage.

**Measured** (2026-11-22; ink by the chapter's rule, "levels" = the share of the inked pixels of the 2,350 syllables at
level 1 / 2 / 3, drawn through `svfline.py`):

| Font, size | Face | Bytes | Fit | Levels 1/2/3 | measure | Ink |
|---|---|---|---|---|---|---:|
| NanumGothic Bold 16 | `mkfont.py --bpp 1` | `125,520` | | (1 bpp) | `width=146 ascent=14 descent=2` | 677 |
| | `mkfont.py --bpp 2` | `195,760` | | 23 / 18 / 59 % | the same | 847 |
| | `jamoset.py --bpp 1` (threshold) | `20,064` | IoU 0.817, 12 s | (1 bpp) | `width=151 ascent=13 descent=3` | 672 |
| | `jamoset.py --bpp 2 --aa-refine 0` | `23,692` | level error 0.269, IoU at level 2 0.783, 69 s | 30 / 31 / 39 % | `width=146 ascent=13 descent=3` | 869 |
| | `jamoset.py --bpp 2` (refine 2) | `24,960` | level error 0.233, IoU at level 2 0.822, 72 s | 27 / 32 / 41 % | the same | 879 |
| Gowun Batang Bold 20 (rule `line 400 28 0 20`) | `mkfont.py --bpp 1` | `170,924` | | (1 bpp) | `width=175 ascent=18 descent=2` | 727 |
| | `mkfont.py --bpp 2` | `264,376` | | 25 / 20 / 55 % | the same | 955 |
| | `jamoset.py --bpp 1` (threshold) | `23,316` | IoU 0.807, 21 s | (1 bpp) | `width=184 ascent=17 descent=3` | 776 |
| | `jamoset.py --bpp 2` | `28,940` | level error 0.193, IoU at level 2 0.805, 94 s | 27 / 30 / 43 % | `width=174 ascent=17 descent=3` | 1,020 |
| Neo Dunggeunmo 16 | `jamovec.py render --bpp 2` | `19,452` | 11,172 composed; master 24 s | 0 / 0 / 100 % | `width=144 ascent=12 descent=4` | 559 |

In these measurements, a 2 bpp precomposed face is 1.5-1.6× its 1 bpp face, and a 2 bpp jamo set about 1.2× its 1 bpp set. The jamo sets carry
more middle levels than the precomposed glyphs (a piece's level is a median over many syllables, and composition takes the
maximum level); `--aa-refine 2` lowers the level error and raises the level-2 IoU at the cost of 1 KB here. Neo Dunggeunmo has no partial coverage in this render at 16 px: its 2 bpp face is the 1 bpp face at level 3 and only costs
bytes. The jamo sets' baseline comes from the fit (ink box centred), not from the font's ascent, so it can differ by a
row from the `mkfont.py` face (set `--baseline`).

**Choosing the size.** In the precomposed 2 bpp examples above, 55-59 % of inked pixels are at level 3. Smaller sizes were not measured
here; at 12-14 px compare the 2 bpp face with a 1 bpp `--mono-hint` face of a hinted font
([The precomposed recipe](#the-precomposed-recipe-mkfont-rows)) on the target before choosing. Bake at the size the
target draws rather than scaling a face at draw time. Check every result by its numbers (ink, the levels, and for a
jamo set the `aa:` line's level error and IoU at level 2) and by looking at it: `svfline.py line` writes GRAY8, and the
`web/` picker shows a face at its levels.

**Pitfalls.** An anti-aliased piece over another piece takes the maximum, not the sum: crossing strokes can look lighter
than in the precomposed glyph. A monochrome target (`SVF_T_MONO_PAGE` or `SVF_T_MONO_ROW`) thresholds 2 bpp faces at draw time (`svf_target.mono_threshold`, default 128); give a mono display a 1 bpp face. `--bpp 8` (mkfont only) keeps full coverage for hosts.

Background (coverage, gamma, why no subpixel rendering), the level-to-colour rules of each target, the maximum against
OR in jamo sets, and a table of which bpp to choose: [Anti-aliasing](anti-aliasing.md). For previewing, see the
[web renderer guide](web-renderer-guide.md).

<a id="baseline-vertical-shift-and-clipping"></a>

### 3.6. Baseline, vertical shift and clipping

The ascent field is the baseline row measured from the cell top. At scale 1, the C renderer places the cell top at
`y_baseline - ascent + dy`: positive per-glyph `dy` moves it down. See [SVF metrics](../spec/SVF.md) and the
[C renderer guide](c-renderer-guide.md).

How `mkfont.py` chooses it: `--ascent N` sets it. Without it, when the font's ascent + descent fit the cell it is the
font's ascent; when they do not, the ink of a probe ("한글AQg", or "AQgjy" with `--latin`) is centred in the cell; with
`--latin` the cap height goes to the top. Then, per glyph:

- default: negative left bearings are shifted right, and ink above the cell is shifted down (that glyph then sits
  off the baseline); ink beyond the right or bottom edge is cut;
- `--clip-cell`: every glyph stays on one vertical baseline; top and bottom overflow is cut and counted on stdout.
  Negative left bearings are still shifted right, and right overflow is cut;
- `--fit-cell`: the size is lowered 1 px at a time, down to 8 px, until the measured glyph boxes fit the cell on one
  baseline; it fails if no size fits.

Worked example (verified), NanumGothic Bold drawn at 18 px into a 16x16 cell, ASCII and the 2,350 syllables:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/c.svf --size 18 --cell 16 --bpp 1 \
        --unicode ascii,ksx1001-hangul [--clip-cell | --fit-cell | --ascent 14 --clip-cell]

| Options | Ascent | Result |
|---|---|---|
| none | 13 (ink centred) | glyphs moved into the cell one by one, 126,048 bytes |
| `--clip-cell` | 15 (fewest glyphs cut) | 2,300 of 2,445 glyphs cut (368 at the top, 2,299 at the bottom) |
| `--ascent 14 --clip-cell` | 14 | 2,327 cut (2,321 top, 36 bottom) |
| `--fit-cell` | 13, at 15 px | 0 cut, 118,116 bytes |

`--probe`: instead of choosing a cell yourself, bake in the tall cell that cuts nothing: the cell height and the ascent come from the ink boxes of the glyphs asked for, and `--report FILE.json` writes the boxes (`--probe-cell H` measures the `auto_ascent` a cell of height H would get; `--probe` refuses `--cell`, `--ascent`, `--clip-cell` and `--fit-cell`).

Verified: `mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/p.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul --probe --report $OUT/probe.json` gives an 18x18 cell, ascent 15, `123,116 bytes`, nothing cut (mode `clip`), `width=146 ascent=15 descent=3`, ink 678. The cell is as tall as the font's ink, so it is a measurement, not a design choice: a game's own line pitch still decides the cell.

`tools/fontmetrics.py $OUT/c.svf` lists glyphs whose ink reaches past their advance (here one, `\`). To lower descenders
(or raise a glyph) after the fact, set a per-glyph dy:

    python3 tools/svfdy.py $OUT/c.svf $OUT/c-dy.svf --range 0x67,0x6a,0x70,0x71,0x79 --dy 1    # g j p q y one row lower
    python3 tools/svfdy.py $OUT/c-dy.svf --show

`--dy` moves the glyph at draw time; the dy range (header bytes 17/18) is recomputed. A line's extents depend on the dy values of the glyphs it uses.
An engine without dy support draws those glyphs at their cell position.

**Pitfalls.** A cell smaller than the font's line pitch may cut ink: prefer `--fit-cell`, or a larger cell
with a fixed advance. Changing the ascent of a face changes where every line's ink lands (the MCU examples place a
line's baseline at its top row + the face's ascent).

<a id="ttc-and-otc"></a>

### 3.7. TTC and OTC

<a id="opentype-cff-collections-and-variable-fonts"></a>

`mkfont.py` opens index 0 of a collection (synthetic: a TTC of Galmuri9 + Galmuri7 bakes exactly as Galmuri9). For
another face, save it out as a plain font first (the same step the maker's `ttc-face` does; TrueType or CFF faces alike; name the output `.otf` for a CFF face, as the OpenType CFF recipe above does):

    python3 maker/srcprep.py ttc-face F.ttc $OUT/F1.ttf --index 1

Pick by name, not by position: in the Noto CJK collections KR is not index 0. List the names:

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; [print(i, f['name'].getDebugName(4)) for i, f in enumerate(C('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').fonts)]"

Verified on the host's Noto Sans CJK Regular collection: ten faces, index 0 Noto Sans CJK JP, 1 KR, 2 SC, 3 TC, 4 HK, then 5-9 Noto Sans Mono CJK JP, KR, SC, TC, HK. The face then goes into the recipes as any static font
([OpenType CFF](#opentype-cff-otf) above is exactly this).

<a id="variable-fonts"></a>

### 3.8. Variable fonts

`mkfont.py` draws the default instance. For another, cut a static instance first (fontTools, the maker's `instance`
step) ([fontTools variable-font instancer](#ref-fonttools)):

    python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o $OUT/Caveat-Bold.ttf
    python3 tools/mkfont.py $OUT/Caveat-Bold.ttf $OUT/CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/mkfont.py ttf/caveat/Caveat-VF.ttf $OUT/CAV24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAVB24.SVF     # one face per call: several faces are a fallback chain
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAV24.SVF

Verified: the default instance (Regular 400) bakes to 6,760 bytes and the 700 instance to 7,192 bytes (95 glyphs each,
"Hamburgefonstiv" 141 px wide in the Bold, 136 in the Regular; the summary's one omitted code point is a requested one the font lacks). Named instances are in the `fvar` table (`Caveat`: Regular, Bold; `EB Garamond`: Regular ..
ExtraBold).

<a id="mac-format-truetype"></a>

### 3.9. Mac-format TrueType

**Resource-fork fonts** (.dfont, suitcases, a fork copied out of HFS): the TrueType data is an 'sfnt' resource.

    python3 tools/macsfnt.py list Font.dfont                 # type, id, name, bytes of sfnt / NFNT / FOND / fbit
    python3 tools/macsfnt.py extract Font.dfont $OUT/Font.ttf [--id N]

`macsfnt.py` also unwraps AppleDouble (`._Font`) and MacBinary files. FreeType opens a .dfont directly as well, so
`mkfont.py Font.dfont ...` works for the first face of a Unicode-mapped font (synthetic .dfont). Not run: no `.dfont` was
found; the Korean Mac fonts on hand are classic resource-fork files (`Seoul[FFIL]`), which the `list` / `extract` run
below read.

**Mac Korean cmaps.** A font for the Korean Mac (and some Windows fonts) has only a platform 1 / script 3 (Mac Korean) or
platform 3 / encoding 5 (Wansung) cmap: two-byte KS X 1001 codes. FreeType and the SVF tools select a Unicode cmap, so
such a font draws nothing until it has one:

    python3 tools/macsfnt.py cmap $OUT/Font.ttf                   # platform=1 encoding=3 format=2 entries=... hangul=...
    python3 tools/macsfnt.py unicode $OUT/Font.ttf $OUT/FontU.ttf      # adds (3,1) format 4 [+ (3,10) format 12]

Each code is decoded as EUC-KR (KS X 1001); Apple's own additions to Mac Korean have no KS X 1001 meaning and are counted
as unmapped. Synthetic (`tools/test_macsfnt.py`): a font with only a (1,3) format 2 cmap is listed, extracted from a
resource fork, AppleDouble and MacBinary, gains a Unicode subtable, and `mkfont.py` then draws its syllable.

Run on a real font: Seoul from the Mac OS 7.6.1 Korean CD (`Font Folder/Seoul[FFIL]`, Apple Korea / Elex Computer 1994-1995,
proprietary). `list` shows eight `NFNT`, the `FOND` 17408 "Seoul" and the `sfnt` 17408 (6,159,836 bytes); `extract` writes those
6,159,836 bytes as `Seoul.ttf`; `cmap` prints `platform=1 encoding=0 format=0 entries=232 hangul=0` and
`platform=1 encoding=3 format=2 entries=9799 hangul=2350`. `mkfont.py` on `Seoul.ttf` as extracted draws nothing (it writes
one glyph, 72 bytes: no code point of the set is in the font). `unicode` reports `8329 code points in the Unicode subtable,
1470 codes not in KS X 1001`, and then

    python3 tools/mkfont.py $OUT/SeoulU.ttf $OUT/seoul16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/seoul16.svf $OUT/SEOUL16.SVF --profile default --check

gives `124,868 bytes`, 2,446 glyphs, `width=156 ascent=13 descent=3`, ink 346. Seoul carries hand-made `bdat` strikes
(9 to 24 ppem), so at 16 px FreeType draws the strike, not the outline ([Embedded bitmap
strikes](#embedded-bitmap-strikes)); at 17 px, which has no strike, the outline is rasterised (`125,164 bytes`, 2,444
glyphs: two code points the outline lacks are left out, `width=164 ascent=14 descent=3`). The maker reads the resource fork
directly: `detect.scan` on `Seoul[FFIL]` gives kind `outline`, label "resource fork: sfnt 17408; bitmap strikes 9, 10, 12,
14, 16, 18, 20, 24; Mac Korean cmap", routes `mkfont`, `experimental fit` and `vector fit`. The classic bitmap fonts of the
Korean Mac are in [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts).

<a id="bitmap-fonts"></a>

## 4. Bitmap fonts

<a id="x-window-korean-fonts"></a>

Two kinds of bitmap fonts reach the tools by different paths: Unicode-encoded ones (`CHARSET_REGISTRY "ISO10646"`, or a
TrueType with embedded strikes) go through `mkfont.py` and FreeType; KS C 5601 / KS X 1001 encoded ones (`ENCODING` = the
GL code, the X Window Korean fonts) go through `bdfface.py`.

<a id="iso-10646-bdf-and-pcf"></a>

### 4.1. ISO 10646 BDF and PCF

`mkfont.py` reads a BDF or PCF through Pillow's FreeType, at the file's built-in pixel size only (its strike); any other
size is `OSError: invalid pixel size`, and the maker's `detect.bitmap_strikes` names the sizes a font offers. There is no
shim or workaround: `mkfont.py` asks fontTools whether a code point is in the cmap and treats a non-sfnt file (BDF, PCF,
FNT) as unknown, not as an error (`cmap_has` returns None). The examples use `/usr/share/dosbox-x/wqy_12pt.bdf` (WenQuanYi Bitmap Song, 16 px, Unicode) and
`/usr/share/fonts/X11/misc/18x18ko.pcf.gz` (Misc Fixed Wide, 18 px) [BDF format](#ref-bdf).

    python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf $OUT/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-2bpp.svf --size 18 --bpp 2 --unicode ascii,ksx1001-hangul

Verified, without any shim: BDF `115,684 bytes`, 2,446 glyphs, `width=156 ascent=12 descent=4`, ink 348; PCF 1 bpp
`116,552 bytes`, 2,446 glyphs (18x18 cell), `width=234 ascent=15 descent=3`, ink 366; PCF 2 bpp `181,108 bytes`. These bitmaps carry
only monochrome coverage, so `--bpp 2` only has levels 0 and 3: the same monochrome pixels at 2 bpp, not a smooth face. A jamo set from
these faces is a fit to the precomposed result: `jamoset.py --layout 844 --from-svf $OUT/bdf16-1bpp.svf --mask-font none --check -o ...`
(the next subsection shows the numbers for a bdfface face).

<a id="ks-c-5601-bdf-and-pcf"></a>

### 4.2. KS C 5601 BDF and PCF

An X Window Korean font (`CHARSET_REGISTRY "KSC5601.1987"` or `"KSX1001"`, `ENCODING` = the GL code: `-baekmuk-*`,
`-daewoo-*`, `hanglm16`) goes through `bdfface.py`, which reads BDF only. A PCF is converted by the maker's
`srcprep.py pcf-bdf` (stdlib only, gz accepted; no external `pcf2bdf` is needed), then the precomposed face is made, then
a jamo set is fitted to it:

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))" $OUT/ks.txt
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/hanglm16.pcf.gz $OUT/hanglm16.bdf
    python3 tools/bdfface.py --hangul $OUT/hanglm16.bdf --ascii /usr/share/dosbox-x/wqy_12pt.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/KS16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/KS16.SVF --mask-font none --check -o $OUT/KS16J.SVF

Verified: the BDF has `FONTBOUNDINGBOX 16 16 0 -2`, `PIXEL_SIZE 16`, `CHARSET_REGISTRY "KSC5601.1987"`; `bdfface.py` writes
`125,096 bytes`, 2,350 syllables (2,447 glyphs: the syllables, ASCII 0x20-0x7E and its own U+2026 / U+25A1), 7 glyphs
clipped, `width=156 ascent=14 descent=2`, ink 354; the jamo set `18,436 bytes`, 441 glyphs, 344 pieces, IoU 0.826 over the
2,350 syllables (p5 0.511), `--check` composes all 11,172 syllables, ink 361. The same chain with the Unicode BDF as both
halves (`--hangul wqy_12pt.bdf --ascii wqy_12pt.bdf`): face `115,700 bytes`, jamo set `16,272 bytes`, IoU 1.000.

`bdfface.py` keeps only the Hangul syllables `--chars-from` names (any text; `mkfont.py`'s rules), ASCII 0x20-0x7E from
`--ascii`, and its own U+2026 / U+25A1: no symbols or jamo come from the BDF. The cell defaults to 24x24 whatever the BDF's
box is, so give `--cell`; `--ascent` / `--hangul-ascent` place the baselines. Synthetic (`tools/test_recipes.py`): a KS C
5601 BDF of 10 syllables and an ISO 10646 ASCII BDF give a face with exactly those syllables, rows in place.

<a id="hanterm"></a>

### 4.3. hanterm

hanterm fonts (johab-1 encoding, glyph numbers as `ENCODING`, 10x(3|4)x4 sets, 529 glyphs) are read directly:

    python3 tools/jamoset.py --layout hanterm-johab johabm16.bdf --check -o $OUT/HTERM16J.SVF

Run on KAIST Myeongjo and KAIST Gothic, the 16 px Johab fonts of the hanterm 3.0.4 font set (`johabm16.bdf`,
`johabg16.bdf`; 529 glyphs each, `CHARSET_REGISTRY "JOHAB-1"`; KAIST; redistribution terms not stated), with the command above:

Myeongjo: `13,740 bytes`, 368 pieces, `check: composed 11172 syllables from 368 glyphs, JSET 1303 bytes`, `width=80 ascent=14
descent=2` (the five syllables of the sample; the BDF has no ASCII, give `--eng` a raw 8x16 English font for it), ink 310;
Gothic: `13,180 bytes`, ink 214. The maker's `detect.scan` gives both kind `bdf-johab`, label "BDF (johab)", sizes [16] and the
route `hanterm`. The same set's `10-6-6` folder (10x6x6 sets) is another layout and was not run. Synthetic
(`tools/test_recipes.py`): a 529-glyph hanterm BDF composes all 11,172 syllables in 10/4/4 sets.

<a id="hbf"></a>

### 4.4. HBF

`bdfface.py --ascii` reads an HBF (the `.hbf` with its `.bin` or `.bin.gz` beside it), but only as the ASCII half of a
face; the Hangul half must be a BDF. Run with Sony Fixed 12x24 (`12x24.hbf` with `12x24.bin.gz`, the X11 Sony font as the
ibiblio HBF collection holds it; Sony, free to use with its notice) as the ASCII half and Baekmuk Batang 24 (`batang24.bdf`
of the Baekmuk 2.0 X11 BDF set, KS C 5601) as the Hangul half:

    python3 tools/bdfface.py --hangul batang24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HBF24.SVF

`206,872 bytes`, 2,350 syllables, ascent 22, step 24, no glyph clipped, `width=216 ascent=22 descent=2` (five 24 px syllables
and seven 12 px characters), ink 746; with the `.bin` unzipped beside the `.hbf` the face is byte for byte the same. The
maker's `detect.scan` (checked on copies, upload and local mode alike) lists `12x24.hbf` with its `12x24.bin.gz` as format
`hbf`, label "HBF", 24 px, ASCII coverage 95 and no route of its own: an HBF is only the Latin half of a face. HBFs it
cannot use as one get a label that says why: a two-byte code range (`uni24.hbf`, `unihan16.hbf`: "HBF: two-byte code range
not supported"), a gzipped HBF itself ("HBF: gzipped HBF not supported"), a bitmap file that is not there ("HBF: bitmap
file missing"). Synthetic
(`tools/test_bdfface.py`): a synthetic HBF as the ASCII half.

<a id="windows-fnt-and-fon"></a>

### 4.5. Windows FNT and FON

FreeType has a winfnt driver and `mkfont.py` opens a Windows `.FNT` (or the `.FON` that holds several) at the font's own
pixel size, the way it opens a BDF or PCF, but it cannot draw from one: the driver gives these fonts a single charmap of
`FT_ENCODING_NONE`, no Unicode, so every code point falls on glyph 0. Run on the Windows 95 Korean system fonts (Microsoft,
proprietary): VGAFIX.FON "Fixedsys" 16 px, VGASYS.FON "System" 13 px, SERIFF.FON "MS Serif" 13 px, 8514FIX.FON ([FreeType bitmap and Windows FNT support](#ref-freetype)):

    python3 tools/mkfont.py VGAFIX.FON $OUT/fon.svf --size 16 --bpp 1 --unicode ascii

exits with `--unicode 의 글자가 글꼴에 하나도 없다` ("no character of --unicode is in the font"), and the same with
`--unicode ascii,ksx1001-hangul`; Pillow draws "A", "B" and "가" as one and the same notdef glyph. The maker's `detect.scan`
(upload and local mode) names them and offers no route: VGAFIX.FON and VGASYS.FON "Windows FON face 0; no Unicode
character map, mkfont cannot read it" (sizes [16] and [13]), MODERN.FON "Windows FON; no openable face"; a bare
Windows `.FNT` is labelled the same way ("Windows FNT; no Unicode character map, mkfont cannot read it"). Treat them as
unsupported, or convert them first. No
Windows FNT or FON with Hangul glyphs was found: the Windows 95 Korean disks carry only Latin and OEM ones (Fixedsys,
System, Terminal, MS Serif, MS Sans Serif, Courier, Small Fonts; 25 FONs), and the Korean glyphs of that system are
TrueType (`gulim.ttc`, with strikes: [Embedded bitmap strikes](#embedded-bitmap-strikes)). A FON would have to be converted
to a BDF with an outside tool first; no such converter is provided.

Not to be mixed up with DOS Johab `.FNT` files, which are jamo-piece fonts: see [DOS-era raw fonts](#dos-era-raw-fonts).

<a id="embedded-bitmap-strikes"></a>

### 4.6. Embedded bitmap strikes

An outline font with embedded bitmaps (TrueType `bdat`/`bloc`, OpenType `EBDT`/`EBLC`) is used by FreeType only at the
strike's own pixel size: run `mkfont.py --size N` with the strike's size and `--bpp 1`; at other sizes the outlines are
used, or the open fails for a bitmap-only font (`OSError: invalid pixel size`). The maker's `detect.bitmap_strikes` lists a
font's strikes and offers them as sizes. Run on two real fonts [OpenType glyphs, shaping and bitmap strikes](#ref-opentype).

*Seoul* of the Mac OS 7.6.1 Korean CD (`Font Folder/Seoul[FFIL]`, Apple Korea / Elex, proprietary; strikes 9, 10, 12, 14, 16,
18, 20, 24 ppem, see [Mac-format TrueType](#mac-format-truetype)): after `macsfnt.py extract` and `unicode`, `mkfont.py --size 16
--bpp 1 --unicode ascii,ksx1001-hangul` writes the strike's pixels (`124,868 bytes`, ink 346); at `--size 17` it draws the outline.
The CD's bitmap-only copy of the same family (`CD Extras/Bitmap 서체 설치/Seoul/Seoul[FFIL]`, 2,626,404 bytes, `bdat` + `bloc` +
`bhed`, no `glyf`, maker kind `bitmap`, sizes [9, 10, 12, 14, 16, 18, 20, 24]) gives the same glyph bytes at 16 px
(`124,868 bytes`), 12 px (`105,972 bytes`) and 24 px (`219,116 bytes`), and `--size 17` stops with `폰트를 17px 로 열 수 없다:
invalid pixel size`. It has no `head` (Apple's `bhed` instead), so Pillow measures every advance as 0; `mkfont.py` takes
each glyph's advance from the strike's own metrics instead, so the bitmap-only copy bakes as the full font does: 16 px `width=156 ascent=13 descent=3`,
ink 346, and `fontmetrics.py` finds every glyph inside its advance; 12 px `width=111 ascent=10 descent=2`, ink 252.

*Gulim* (굴림) of Windows (`GULIM.TTC`, Microsoft with HanYang I&C, proprietary; `EBLC` strikes 11 to 25 ppem):

    python3 maker/srcprep.py ttc-face GULIM.TTC $OUT/Gulim.ttf --index 0
    python3 tools/mkfont.py $OUT/Gulim.ttf $OUT/gu16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

16 px `125,288 bytes`, 2,446 glyphs, `width=149 ascent=14 descent=2`, ink 371; 12 px `106,208 bytes`, `width=114 ascent=10
descent=2`, ink 298; `svf2to3.py --profile default --check` keeps both sizes. A size with no strike (26) rasterises the outline
(`202,144 bytes`); `--bpp 2` also takes the outline even at a strike size (16 px: `182,604 bytes`), so only `--bpp 1` gives the
strike's own pixels. The maker's `detect.scan` on the extracted font gives kind `outline-composite`, label "TTF; bitmap strikes 11, 12,
13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25", sizes [16], routes `mkfont`, `composite` and `vector fit`.

<a id="dos-era-raw-fonts"></a>

## 5. DOS-era raw fonts

DOS Hangul systems (Hangul BIOS, 이야기, 한메, san, Dokkaebi, games) stored jamo pieces, not syllables; a syllable was the
OR of an initial, a medial and an optional final, the set chosen by the other jamo. The tools read these raw files **by
exact byte size** (the maker's `detect.py` does the same, and a file of an unlisted size is "unknown") and by layout; there
is no header to sniff.

<a id="other-dos-era-korean-fonts"></a>

### 5.1. Other DOS-era Korean fonts

| `--layout` | File | Bytes | Pieces |
|---|---|---|---|
| `844` | raw 8x4x4 (`HANGUL.FNT`, `*.KOR`, `$K*ZN16`), 16/24/40/48 px | 11,520 (or 11,522 with a 2-byte header), 25,920, 72,000, 103,680; 15,584 (DKB2, read as 16 px) | 360: 8 initial sets of 20, 4 medial of 22, 4 final of 28; slot 0 of each set blank |
| `844-ihnm` | SAGA IHNM 8x4x4 (medial sets swapped for ㄱ ㅋ) | 11,520+ | 360 |
| `844-hbios24` | HBIOS / Taebaek 3.5 24x30 (`GOTHIC24.FNT`, `MY24.FNT`) | 243,900 | the first 360 |
| `1044-san` | san 1.0 10x4x4 | 12,800 | 400 |
| `621` | 6x2x1 (Apple II era), byte-column glyphs | 6,144 | 192 |
| `dkb-printer-7x2x2` / `dkb-printer-12x4x4` | Dokkaebi printer `HANGUL16/24.FNT` / `HANGUL40/48.FNT` (`--face 0|1`) | 15,360 / 34,560; 176,000 / 253,440 | 240 / 440 a face |
| `kyra-lok` | Kyra LoK `MK15.BIT`, 15x15 | 11,550 | 385 |

    python3 tools/jamoset.py --layout 844 HANGUL.FNT --eng ENGLISH.FNT --symbols --check -o $OUT/MYFONT16J.SVF
    python3 tools/johab844.py HANGUL.FNT svf/dos/NEODG16.SVF $OUT/MYFONT16.SVF --eng ENGLISH.FNT     # precomposed instead

`--eng` takes a raw English font for ASCII (8×16 files: 2,048 or 4,096 bytes; larger companions are described below), scaled by whole numbers to the cell; `--base
FACE.SVF` keeps another face's non-syllable glyphs. The ascent defaults to 7/8 of the cell (`--ascent N`); 8x16 DOS
fonts put the baseline at row 13 or 14. `--check` composes all 11,172 syllables. `johab844.py` redraws the syllables of a
16x16 1 bpp base with the raw pieces and keeps the base's other glyphs. Synthetic (`tools/test_recipes.py`): a raw 8x4x4 font with an 8x16 English font (가 composed = the OR of raw slots 1 and 161, byte
for byte), a 6x2x1 font (1 lead / 2 tail classes, 6/2/1 sets), and a refit of a precomposed face (`--from-svf` over
NEODG16J, IoU 1.000).

Run on real fonts (2026-11-22; `--symbols --check` on every line, `--eng` where named; the sample line `안녕하세요 ABC 123`; "ink" is the
count of the render check; ASCII is drawn only when `--eng` is given, so a face without it measures five syllables):

| `--layout` | Source (font, product; proprietary unless noted) | Result |
|---|---|---|
| `844` | GOTHIC16.FNT, 11,520 bytes (Taebaek 3.5.1 Gothic 16), `--eng ROMAN16.FNT` of the same package | `15,756 bytes`, 344 pieces, 441 glyphs, identical to `johab844.py`'s syllables; `width=144 ascent=14 descent=2`, ink 566 |
| `844` | TBG1.FNT, 11,522 bytes with the 2-byte header (T-Hangul, an early Taebaek), `--eng ROMAN16.FNT` | `15,712 bytes`, the same 344 pieces and ink 566 |
| `844` | DKBBM.FNT, 15,584 bytes (Hangul Dokkaebi B Myeongjo), `--eng ROMAN16.FNT` | `15,744 bytes`, 441 glyphs, identical to `johab844.py`; ink 512 |
| `844` | MHANC24.PFT, 25,920 bytes (Taebaek 3.5.1 Myeongjo 24 px), `--eng MASCII24.PFT` (12,288 bytes, the 12x24 English font) | `23,088 bytes`, 344 pieces; `width=216 ascent=20 descent=4`, ink 916 |
| `844` | GHANC40.PFT, 72,000 bytes (Taebaek 3.5.1 Gothic 40 px), `--eng GASCII40.PFT` (30,720 bytes, the 20x40 English font) | `42,716 bytes`, 441 glyphs; `width=360 ascent=34 descent=6`, ink 3,078 |
| `844` | GHANC48.PFT, 103,680 bytes (Taebaek 3.5.1 Gothic 48 px), `--eng GASCII48.PFT` (49,152 bytes, 24x48) | `51,972 bytes`; `width=432 ascent=40 descent=8`, ink 3,921 (`line 440 56 0 48`: the line is wider than 400) |
| `844` | MHANC48.PFT, 103,680 bytes (Taebaek 3.5.1 Myeongjo 48 px), `--eng MASCII48.PFT` (49,152 bytes) | `54,112 bytes`; `width=432 ascent=40 descent=8`, ink 3,573 (`line 440 56 0 48`) |
| `844-hbios24` | GOTHIC24.FNT, 243,900 bytes (Taebaek 3.5.1, the HBIOS 24x30 layout) | `17,776 bytes`, 346 glyphs; `width=120 ascent=21 descent=3`, ink 551 |
| `844-hbios24` | MY24.FNT, 243,900 bytes (Taebaek 3.5.1 Myeongjo 24), `--eng GASCII24.PFT` | `23,136 bytes`; `width=216 ascent=20 descent=4`, ink 964 |
| `1044-san` | HANPL.KOR, 12,800 bytes (san 1.0, `font-kor/`; the san project on GitHub) | `13,988 bytes`, 382 pieces, 384 glyphs; `width=80 ascent=14 descent=2`, ink 328 |
| `621` | han_woori.fnt, 6,144 bytes ("Woori", iolo's 6x2x1-fonts on GitHub, Apple II era) | `6,584 bytes`, 183 pieces, 185 glyphs; ink 204 |
| `dkb-printer-7x2x2` | HANGUL16.FNT 15,360 bytes and HANGUL24.FNT 34,560 bytes (Hangul Dokkaebi 5.1, printer fonts), `--face 0` / `--face 1` | 16 px `8,928` / `8,868 bytes`, 229 pieces, ink 367 / 363; 24 px `12,068` / `11,872 bytes`, ink 542 / 537 |
| `dkb-printer-12x4x4` | HANGUL40.FNT 176,000 bytes and HANGUL48.FNT 253,440 bytes (the same), `--face 0` / `--face 1` | 40 px `38,704` / `38,624 bytes`, 420 pieces (422 glyphs), ink 1,595 / 1,766; 48 px `52,932` / `48,908 bytes`, ink 2,472 / 2,538 |
| `kyra-lok` | MK15.BIT, 11,550 bytes (The Legend of Kyrandia, Korean release) | `14,036 bytes`, 382 pieces, 15x15; `width=80 ascent=13 descent=2`, ink 344 |
| `844-ihnm` | none: no SAGA IHNM data was found | not run |

Every face composes all 11,172 syllables (`--check`); the piece counts are the used pieces, below the table's counts
because unused slots are dropped. `johab844.py` over the same GOTHIC16.FNT (`--eng ROMAN16.FNT`, base `svf/dos/NEODG16.SVF`):
`133,688 bytes`, 2,357 syllables from the raw font, 94 ASCII glyphs from ROMAN16.FNT, 454 other glyphs from the base,
`width=144 ascent=12 descent=4`, ink 566, and `svf2to3.py --check` keeps the size. The maker's `detect.scan` on copies of these
files gives kind `dos-raw` with the sizes 16 / 24 / 40 / 48 / 15 and the route `dos raw` for every one; GOTHIC16.FNT (labelled
"844, 844-ihnm", the two layouts share the size) also gets `johab844`, the 11,522-byte TBG1.FNT and the 15,584-byte DKBBM.FNT only `dos raw`;
the Dokkaebi printer files give one entry per face; GASCII24.PFT / MASCII24.PFT and ROMAN16.FNT are listed as "Latin companion".

**Pitfalls.** A file of the right size in another layout passes the size check; `jamoset.py` refuses it when the slot-0
fill pieces are not blank, but look at the result (`svfline.py line ... "가나다"`). Fonts with a 2-byte header
(T-Hangul) are read at offset 2. A 24 px or larger source needs a matching English font or `--base`: `--eng` takes the 8x16 fonts and the 12x24, 20x40
(30,720 bytes) and 24x48 (49,152 bytes) PFT English fonts of the same package, each scaled by whole numbers to the cell;
the desktop app pairs a 40 or 48 px face with the English font of its own height, the same family (G / M) first.

<a id="hwp-1x-and-2x-fonts"></a>

### 5.2. HWP 1.x and 2.x fonts

Hangul and Computer's DOS word processor shipped its own bitmap fonts. `tools/hwpfont.py` reads them - HWP 1.x `.SFT`
(screen) and `.PFT` (printer), and HWP 3.0 `.FNT` ([below](#hwp-30-fnt-fonts)) - and writes Unicode BDFs;
`jamoset.py --layout hwp1` makes an HWP 1.x Hangul face a jamo set by HWP's own composition rule. The supported layouts are described in [hwpfont.py](../tools/hwpfont.py):

- HWP 1.x (1989-1990): a 32-byte "HWP Font Editor v1.0" header (the `HANGUL3.PFT` of `HPFT3.LZH` has "FE" instead), the
  glyph count (big-endian 16 bits) at 0x1C, (width - 1, height - 1) at 0x1E, then the glyphs; the file is exactly 32 +
  count x glyph bytes. Screen fonts (16 rows) are row-major, printer fonts (24 rows, a 24-pin head) column-major, three
  bytes a column, MSB at the top.
- `HANGUL.SFT` (16x16, 1,193 glyphs) and `HANGUL1/2/3.PFT` (24x24, 980) hold three faces (HWP's style 0, 1, 2: Myeongjo,
  Gothic, Saemmul by its menu order, not proven). A face is its initial, vowel and final piece sets (31, 29 and 31 pieces a
  set): 10/4/4, 7/2/2 and 6/2/2 sets in the SFT, 7/2/3, 7/2/2 and 5/2/2 in a PFT.
- `ASCII.SFT` (8x16) and `ASCII.PFT` (14x24): 991 glyphs, 109 others and then six faces of the codes 0x20-0xB2
  (Myeongjo, Gothic, superscript, subscript, italic, script). `HANJA.SFT`: the 4,888 KS X 1001 hanja. The symbol files
  (`SPECIAL1/2`, `JAPAN`, `USER1/2`, `SYSTEM.PFT`) are recognised (`hwpfont.py info`) and not converted.

**A jamo set, not a fit.** HWP.EXE composes a syllable as the OR of three pieces whose sets it picks from the initial's
class (ㄱ ㅋ or the rest), whether there is a final, and the vowel's shape class. That is a set rule of the JSET kind, and
with 2 x 2 classes and at most 10/4/4 sets it fits the standard JSET limits as it is: `--layout hwp1` writes HWP.EXE's
tables of the chosen face (`--face 0..2`), and every syllable composes bit for bit. `--check` composes all 11,172
syllables from the written face and compares each with `hwpfont.py`'s own composition, which reads the pieces through
HWP's tables directly. So the jamo set is the native form of these fonts (10-18 KB instead of about 120 KB at 16 px); a
precomposed face of the same syllables comes from `hwpfont.py bdf` and `mkfont.py` (the maker's `hwp bdf + mkfont`).
The pieces HWP keeps for old Hangul (initials 20-31, vowels 22-29, finals 28-31) belong to no modern precomposed Unicode Hangul syllable and are
left out.

    python3 -I tools/hwpfont.py info HANGUL.SFT
    python3 -I tools/jamoset.py --layout hwp1 --face 1 HANGUL.SFT --eng ASCII.SFT --check -o $OUT/HWPS1J.SVF
    python3 -I tools/hwpfont.py bdf HANGUL1.PFT --face 1 --ascii ASCII.PFT -o $OUT/hwp24.bdf
    python3 tools/mkfont.py $OUT/hwp24.bdf $OUT/hwp24.tmp --size 24 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/hwp24.tmp $OUT/HWP24.SVF --profile default

`--eng` (jamoset.py) and `--ascii` (hwpfont.py) take an HWP English file as it is, face 0 of its six unless `--eng-face N`
/ `--ascii-face N` says otherwise, besides every English font `--eng` read before; `hwpfont.py bdf --syllables all`
writes all 11,172 syllables of an HWP 1.x face instead of the 2,350 of KS X 1001. A precomposed BDF takes the English
face's baseline as its ascent (12 for `ASCII.SFT`, 20 for `ASCII.PFT`; `--ascent` sets another); `jamoset.py` puts an
8x16 English font in a 16 px cell at 7/8 (ascent 14) as for every DOS font.

Run on HWP 1.20 for DOS (Hangul and Computer, 1989-1990; archive.org `hwp-120`; proprietary) on 2026-11-23, the English
font of the same folder, face 0:

| Source | Command | Result |
|---|---|---|
| `HANGUL.SFT` (38,208 bytes), faces 0 / 1 / 2, `--eng ASCII.SFT` | `jamoset.py --layout hwp1 --face N --check` | `16,996` / `11,188` / `10,468 bytes`, 382 / 229 / 210 pieces (10/4/4, 7/2/2, 6/2/2 sets); `width=144 ascent=14 descent=2`, ink 497 / 403 / 363 |
| `HANGUL1.PFT` (70,592 bytes), faces 0 / 1 / 2, `--eng ASCII.PFT` | the same | `18,224` / `16,712` / `14,252 bytes`, 256 / 229 / 191 pieces; `width=232 ascent=20 descent=4`, ink 886 / 886 / 818 |
| `HANGUL.SFT` face 1 and `ASCII.SFT` | `hwpfont.py bdf --face 1`, `mkfont.py --size 16`, `svf2to3.py` | `122,440 bytes`, 2,350 syllables; `width=144 ascent=12 descent=4`, ink 403 |
| `HANGUL1.PFT` face 1 and `ASCII.PFT` | the same at `--size 24` | `218,748 bytes`; `width=232 ascent=20 descent=4`, ink 886 |

Every jamo line printed `hwp1: 11172 syllables identical to the HWP 1.x rule (hwpfont.py)`. `tools/test_hwpfont.py` also checks recorded syllable hashes when `JOHAB_FONTS` supplies the optional source files.

HWP 2.x for DOS keeps its fonts as `.HFT` files (below); the one HWP 2.x screen font that is a plain raw 8x4x4 is
`HMJ.FNT` (11,520 bytes) of the Hangul 2.1 PRO disks (disk 13), read as any `844` font: `python3 tools/jamoset.py
--layout 844 HMJ.FNT --eng ROMAN16.FNT --check -o $OUT/HMJ.SVF` writes `15,700 bytes` and composes all 11,172 syllables,
identical to `johab844.py`.

**Not read:** the `.HFT` fonts of HWP 2.0 ("HWP 2.0 font file" header), 2.1 and 3.0 ("Han Unified Font File 1.0"; the
HWP 3.0 CD's `HNC/FONT` has 160 of them). Their headers were looked at: they are scalable outline or stroke fonts (the HWP
2.0 header names a 1,200-unit square), not bitmaps, and no tool here decodes them. The HWP 1.x symbol files are listed
and not converted; `HANJA.SFT` (and HWP 3.0's `HAJ16_0.FNT`) becomes a BDF of the 4,888 hanja at their Unicode code
points (`hwpfont.py bdf`), which the maker does not offer as a Hangul-face route; `mkfont.py --unicode ksx1001` can select Hanja from the BDF.

**The maker** (local mode only, as for the Mac fonts: an upload job lists each HWP file as "HWP font: not converted here
(local-only mode)") lists an HWP 1.x Hangul file as three `hwp1` entries, one a face ("HWP 1.x Hangul (printer .PFT,
24x24), face 1 of 3 (Gothic by HWP's menu order)"), with the routes `hwp1` (jamo, native) and `hwp bdf + mkfont`
(precomposed), and the English files as Latin companions ("HWP 1.x English (--eng, 14x24; face 0 of 6)"), offered to HWP and KS faces only (a DOS raw font's routes read the raw English fonts); the other
files are `other` ("HWP 1.x font: 4888 hanja of 16x16, not a Hangul face"). Checked with `detect.scan(..., local=True)`
and `routes.routes` on copies of the files above, and every route's commands run on them (2026-11-23): the `hwp1` route
writes the 16,712-byte face of the table, `hwp bdf + mkfont` the 218,748-byte one.

<a id="hwp-30-fnt-fonts"></a>

### 5.3. HWP 3.0 FNT fonts

HWP 3.0 for DOS (1995; `HNCAPP/HDR30/FONT` of the CD) keeps its bitmap fonts as `.FNT` files with a 72-byte header:
"FNT" 01, a type byte (0 English, 1 Hangul, 2 hanja), 01, the width and height (little-endian 16 bits) at 6 and 8, the
glyph count (32 bits) at 0x10 and the font's name in Johab at 0x14 ("고딕체 16*16"); then row-major glyphs. A Hangul FNT
holds the 2,350 KS X 1001 syllables in code order, precomposed, from 가; a 16 px one (`HAN16_*.FNT`, 86,792 bytes) adds an
8x4x4 set of 360 jamo pieces after them for the other syllables, which `jamoset.py --layout 844-hwp3` reads (its fill
slots checked, `--check` equal to `johab844.py`). `HAN24_*` / `HAN40_0` / `96MT` hold the 2,350 only (HAN24's header
still counts 2,710). The English FNTs hold the codes from 0x20 (147 glyphs; `ENG40_0` 96).

    python3 -I tools/hwpfont.py bdf HAN16_0.FNT --ascii ENG16_3.FNT -o $OUT/han16.bdf
    python3 tools/mkfont.py $OUT/han16.bdf $OUT/han16.tmp --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/han16.tmp $OUT/HAN16.SVF --profile default
    python3 -I tools/jamoset.py --layout 844-hwp3 HAN16_0.FNT --eng ENG16_3.FNT --check -o $OUT/HAN16J.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/HAN24.SVF --mask-font none --check -o $OUT/HAN24J.SVF

Run on the HWP 3.0 DOS CD (Hangul and Computer, 1995; archive.org `hwp-30-dos`; proprietary) on 2026-11-23, the precomposed
faces with `hwpfont.py bdf`, `mkfont.py` at the cell size and `svf2to3.py --profile default`:

| Source | Command | Result |
|---|---|---|
| `HAN16_0.FNT` ("고딕체 16*16"), `--ascii ENG16_3.FNT` ("고딕체 8*16") | precomposed | `115,112 bytes`, 2,350 syllables; `width=144 ascent=12 descent=4`, ink 523 |
| the same, `--eng ENG16_3.FNT` | `jamoset.py --layout 844-hwp3 --check` | `15,432 bytes`, 344 pieces, identical to `johab844.py`; `width=144 ascent=14 descent=2`, ink 523 |
| the precomposed `HAN16_0` face | `jamoset.py --layout 844 --from-svf --mask-font none` | `16,308 bytes`, IoU 0.994 (2,166 of 2,350 exact) |
| `HAN16_1` / `_2` / `_3` / `_4` (명조체, 샘물체, 필기체, 모양체), `--ascii ENG16_0.FNT` | precomposed | `118,020` / `122,100` / `123,468` / `115,272 bytes`; ink 496 / 363 / 521 / 501 |
| `HAN24_0.FNT` ("고딕체 24*24", 169,272 bytes), `--ascii ENG24_0.FNT` (12x24) | precomposed | `218,472 bytes`; `width=216 ascent=22 descent=2`, ink 972 |
| `HAN24_1.FNT` ("명조체 24*24"), `--ascii ENG24_0.FNT` | precomposed | `220,044 bytes`, ink 984 |
| `HAN40_0.FNT` ("명조체 40*40", 470,072 bytes), `--ascii ENG40_0.FNT` (20x40) | precomposed | `492,420 bytes`; `width=360 ascent=34 descent=6`, ink 2,289 |
| `96MT.FNT` ("문화부 바탕체 96*96", 2,707,272 bytes), no English font | precomposed, `--size 96` | `2,154,232 bytes`, all 2,350 syllables; `width=576 ascent=84 descent=12`, ink 6,058 (`line 576 104 0 96`; the BDF's blank U+0020 steps 48) |
| the `HAN24_0` / `HAN40_0` faces | `jamoset.py --layout 844 --from-svf --mask-font none` | `28,928` / `64,904 bytes`, IoU 0.819 / 0.687 |

The 16 px FNTs' 2,350 syllables are not all their jamo set's composition: 2,083 (`HAN16_0`), 1,788 (`_1`), 2,221 (`_2`),
375 (`_3`, the handwriting face) and 1,700 (`_4`) of them equal what the 8x4x4 set composes; the others were drawn whole.
So the precomposed face is the better 2,350 and the jamo set the way to all 11,172. The maker (local mode) lists a Hangul
FNT as `ks-raw` ("HWP 3.0 FNT Hangul 16x16: 2,350 KS X 1001 syllables + an 8x4x4 jamo set") with `hwp bdf + mkfont`,
`hwp3 844` (a 16 px one only) and the experimental `hwp bdf + from-svf fit`, and the English FNTs as Latin companions
("HWP 3.0 English (--eng, 12x24)"); `HAJ16_0.FNT` is `other`.

<a id="ks-x-1001-raw-dumps"></a>

### 5.4. KS X 1001 raw dumps

A raw dump of the 2,350 precomposed KS X 1001 syllables (one bitmap per syllable in code order, row-major, no header, as
some DOS and embedded systems keep them) is read by `hwpfont.py` by its size: 2,350 x the bytes of a 16, 24, 32, 40 or
48 px square glyph (75,200, 169,200, 300,800, 470,000 or 676,800 bytes), its first and last glyph inked and different.
It writes the dump as a Unicode BDF, with the ASCII of any English font `--eng` reads; the maker lists such a file as
`ks-raw` ("KS X 1001 raw dump Hangul 24x24: 2,350 KS X 1001 syllables", in upload and local mode, as it reads DOS raw
fonts by size) with `hwp bdf + mkfont` and the experimental `hwp bdf + from-svf fit`. `jamoset.py --layout 844` still
refuses one (`size 169200 is not an 8x4x4 size`): a dump is precomposed, and its jamo set is a fit.

    python3 -I tools/hwpfont.py bdf GHAN24.PFT --ascii GASCII24.PFT -o $OUT/ghan24.bdf
    python3 tools/mkfont.py $OUT/ghan24.bdf $OUT/ghan24.tmp --size 24 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/ghan24.tmp $OUT/GHAN24.SVF --profile default
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/GHAN24.SVF --mask-font none --check -o $OUT/GHAN24J.SVF

Run on Taebaek 3.5.1 (`FNT/`, proprietary) on 2026-11-23, each with the English font of its own family and height:

| Source | Result |
|---|---|
| `GHAN24.PFT` (Gothic 24 px, 169,200 bytes), `--ascii GASCII24.PFT` (12x24) | `216,192 bytes`, 2,350 syllables; `width=216 ascent=20 descent=4`, ink 1,133; the jamo set `33,428 bytes`, 344 pieces, IoU 0.710, ink 1,096 |
| `MHAN24.PFT` (Myeongjo 24 px), `--ascii MASCII24.PFT` | `213,812 bytes`; `width=216 ascent=20 descent=4`, ink 907; the jamo set `31,664 bytes`, IoU 0.623 |
| `GHAN40.PFT` (470,000 bytes), `--ascii GASCII40.PFT` (20x40) | `487,808 bytes`; `width=360 ascent=34 descent=6`, ink 3,112 |
| `GHAN48.PFT` (676,800 bytes), `--ascii GASCII48.PFT` (24x48) | `663,328 bytes`; `width=432 ascent=40 descent=8`, ink 3,926 (`line 440 56 0 48`) |

The fit is poor (IoU 0.710) because the face is a whole-syllable design, not an OR of pieces; the same IoU came from
the BDF `rawcarve.py` cut before `hwpfont.py` existed. `rawcarve.py bdf --dense` still cuts a dump that sits inside a
bigger file (`--offset`), and a dump of the whole 94 x 94 table takes `--grid 0xA1,0xA1,94` instead
([OS/2 Korean fonts](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set)):

    python3 -I tools/rawcarve.py bdf GHAN24.PFT --glyph 24x24 --chars ks-hangul --dense --ascent 22 -o $OUT/ghan24.bdf

<a id="finding-a-font-inside-a-program-or-data-file-with-claude"></a>

## 6. Finding a font inside a program or data file, with Claude

DOS Hangul drivers, word processors, games and the font ROMs of Korean VGA cards keep their fonts as bare bytes inside a
program (`.COM`, `.EXE`, a TSR) or a ROM image: no header, no name, often no file of their own. Two tools find and cut them, and an assistant such as Claude does the reading in between (where a font starts, which
layout it has, what rule the driver composes it by):

- `tools/binscan.py` looks: `info` (size, kind, an entropy map that shows packed data, the size signatures below),
  `runs` (runs of glyph-like windows), `sets` (offsets where a raw jamo-piece font's blank fill slots line up), `ascii`
  (8xH English fonts), `render` (any offset as text or as a PNG, in row, strip, column or byte-column order);
- `tools/rawcarve.py` cuts: `cut` (bytes as they are: a raw 8x4x4 font for `jamoset.py`), `eng` (an 8xH English font as
  the 4,096-byte 8x16 file `--eng` reads), `bdf` (glyphs at an offset as a Unicode BDF: ASCII, or the KS X 1001 syllables
  of a dense 2,350-glyph dump or of a code grid), `compose` (a jamo-piece font with its own set rule, written as a small
  JSON spec, composed into syllables as a Unicode BDF).

The BDF goes on through `bdfface.py` to a precomposed face and through `jamoset.py --from-svf` to a jamo set; a cut raw
8x4x4 font goes straight to `jamoset.py --layout 844` ([Other DOS-era Korean fonts](#other-dos-era-korean-fonts)). Both
tools only read bytes and never run the file's code; run them with `python3 -I` on downloads. Use the [7-Zip output-directory switch](#ref-7zip) to unpack an archive first
(`binscan.py info` names ARJ and ZIP; `7z x -oNEWDIR FILE.ARJ`), into a folder of its own; never run a DOS program on
the host (an emulator is fine).

**Byte-size signatures** (what a run or a file of a known layout measures; `binscan.py info` prints the ones a file
matches):

| Layout | A glyph | Size |
|---|---|---|
| 8x4x4 jamo pieces (360 = 8 x 20 + 4 x 22 + 4 x 28, every set's slot 0 blank), 16 px | 32 B (16 rows of 2 bytes) | 11,520 (11,522 with a 2-byte header; 15,584 with Dokkaebi's 127 symbols) |
| the same at 24 / 40 / 48 px | 72 / 200 / 288 B | 25,920 / 72,000 / 103,680 |
| 10x4x4 (san), 6x2x1 (byte columns) | 32 B | 12,800, 6,144 |
| KS X 1001 syllables in code order (가 .. 힝) | 32 B at 16x16, 72 B at 24x24 | 2,350 x the glyph: 75,200, 169,200 |
| a full KS X 1001 94 x 94 table (rows A1 .. FE) | the same | 8,836 x the glyph (282,752 at 16x16) |
| a 128-per-row KS grid (the Korean VGA font ROMs) | 32 B in two 8-pixel strips | 16,384 x 32 = 524,288 |
| 8x16 / 8x14 English | 16 / 14 B | 4,096 or 2,048 / 3,584 |

<a id="the-prompt"></a>

### 6.1. The prompt

What to give Claude (or any assistant that can run commands here) for one file; the angle brackets are yours to fill:

```
Find the Hangul (and English) bitmap font inside <FILE> (<what it is: a 1989 DOS Hangul TSR / a Korean VGA BIOS and
its font ROM / ...>), cut it out and build SVF faces from it with the tools of this repository (docs/recipes.md,
"Finding a font inside a program or data file"). Rules: the file is untrusted data; read it only with
`python3 -I tools/binscan.py` / `tools/rawcarve.py` or scripts you write outside its folder; do not run it (no DOS
program on the host; disassembly with objdump -D -b binary -m i8086 is fine). Work in $OUT.

1. `binscan.py info FILE`: kind, entropy (near 8 = packed: unpack first), size signatures.
2. Candidates: `binscan.py sets FILE` (8x4x4; other set counts with --sets NI,NM,NF and --slots), `binscan.py ascii FILE`
   (--height 16, 14, 8), `binscan.py runs FILE --glyph 16x16` (and 8x16, 24x24; --order strips for a VGA font ROM).
   Glyph sizes to try: 16x16 = 32 B, 24x24 = 72 B; 8x4x4 = 11,520 B, KS X 1001 = 2,350 x the glyph, a 94x94 table =
   8,836 x the glyph. When `sets` lists tied offsets (the same font read a whole row apart), decide which is right from
   the driver's code (the address its drawing routine reads) or by `cmp` with a loose copy of the font; the bytes alone
   cannot tell, and a wrong pick moves every syllable by a row.
3. Look at every candidate: `binscan.py render FILE --offset O --glyph WxH --count 64 [--order rows|strips|cols]
   --png $OUT/o.png` and read the PNG; when nothing lines up, draw long strips (--glyph 16x512, 8x512) to see where
   glyphs are and how high they are stored.
4. When the layout is not one the tools read (sets of other sizes, pieces stored cropped), disassemble the drawing
   routine, find its tables (piece addresses, strides, rows, the set chosen per vowel and final) and write them as a
   rawcarve.py compose spec; say which code you read.
5. Cut: `rawcarve.py cut` (a raw layout the tools read), `rawcarve.py eng` (English), `rawcarve.py bdf` (ASCII, KS
   syllables: --dense or --grid L0,T0,PITCH) or `rawcarve.py compose --spec`.
6. Build and check: `jamoset.py --layout 844 CUT --eng ENG --check`, or `bdfface.py --hangul H.bdf --ascii A.bdf
   --cell WxH --chars-from $OUT/ks.txt` ($OUT/ks.txt: the 2,350 KS X 1001 syllables as text, written with mkfont.py's
   NAMED_RANGES['ksx1001-hangul'] as in docs/recipes.md, KS C 5601 BDF and PCF; WxH = the font's cell) then
   `jamoset.py --layout 844 --from-svf FACE --mask-font none --check` (also --layout adaptive); report size, glyph
   count, `svfline.py measure` and ink of "안녕하세요 ABC 123" (docs/recipes.md, Checking a face) and the fit IoU, and
   show the line drawn.
Report the offsets, the commands and the numbers; say what you could not resolve.
```

`$OUT/ks.txt`, the syllable list every `bdfface.py` line below reads, is written once:

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))" $OUT/ks.txt

The three examples below were worked with this prompt (2026-11-22). They use proprietary programs and ROM dumps supplied separately.

<a id="nkp-a-hercules-hangul-tsr-with-cropped-pieces"></a>

### 6.2. NKP: a Hercules Hangul TSR with cropped pieces

Source: NKP.COM V3.00 "(C) S.H.OH 06/01,89" (38,184 bytes, inside `NKP26.ARJ`, 18,308 bytes) and NKP3.COM (1989-07, 37,375
bytes, inside `NKP3.ARJ`), Hercules Hangul TSRs of 1989 (the 삼보 조합형 한글 sets; no licence stated). `binscan.py info` on
the ARJ: "ARJ archive", entropy 7.9 in every block (packed: `7z l -slt` shows method 1), so `7z x` first; the
extracted files are byte for byte the copies already on disk. Then:

    python3 -I tools/binscan.py info NKP.COM --block 2048      # .COM (file offset F loads at F + 0x100); entropy 0.5-4.8 at 0x2800-0x6000
    python3 -I tools/binscan.py ascii NKP.COM                  # offset 0x39a0, edge 0
    python3 -I tools/binscan.py sets NKP.COM                   # none (also with --sets 8,2,1)
    python3 -I tools/binscan.py render NKP.COM --offset 0x3800 --glyph 16x512 --count 16 --cols 16 --scale 2 --png $OUT/strip.png

The English font is at 0x39a0 (128 glyphs of 8x16). No raw 8x4x4 font is there: the strip shows the pieces from 0x41a0
on, 16 pixels wide but only 5 to 14 rows high each, packed one after another (the inventory's "8/2/1 sets, row-cropped").
The rule is in the code: `objdump -D -b binary -m i8086 --adjust-vma=0x100 NKP.COM` (a .COM loads at 0x100, so the
addresses the code names are memory addresses: file offset = address - 0x100). It shows the ASCII routine loading
`mov ax,0x3aa0` (file 0x39a0), and the Hangul routine (at 0x1ea9) splitting the Johab code with three 32-byte tables
(initial at 0x1bd6, vowel at 0x1bf6, final at 0x1c14: 5-bit code to the driver's own jamo number, 31 = none), picking the
initial set from a 42-byte table at 0x1c34 (21 vowels without a final, then 21 with one; each value is the byte offset
of a piece-set record, record = value / 6), the medial piece from an 84-byte table at 0x1c5e of (`u8` piece, `u8`
record byte offset) pairs (21 without a final, 21 with), the final from record 96, and drawing each piece through the
17 six-byte records at 0x1b0c: `u16` address of the set's first piece, `u8` stride, `u8` first and `u8` end byte of the
32-byte cell (2 bytes a row) it is ORed into, `u8` flags. Flag bit 0 set: 16 pixels wide, cell bytes first .. end - 1,
so (end - first) / 2 = stride / 2 rows from row first / 2. Bit 0 clear: one byte a row into every other cell byte
(first, first + 2, ... below end; the right 8 pixels when first is odd), so stride = (end - first + 1) / 2 rows of 8
pixels from row first // 2. NKP thus has 8 initial sets (no final: ㅏ-type vowels, ㅗㅛㅡ, ㅜㅠ, compound vowels; the
same four with a final), 2 medial sets (without / with a final; each split into four crops by vowel shape) and one final
set, and numbers its vowels in its own order (ㅏㅑㅓㅕㅣㅐㅒㅔㅖㅗㅛㅡㅜㅠㅘㅚㅝㅟㅢㅙㅞ). `tools/nkpspec.py` reads these
tables (found by the instruction bytes that use them; `find` prints the addresses) and writes the compose spec:

    python3 -I tools/nkpspec.py find NKP.COM                   # desc 0x1b0c, cho 0x1bd6, jung 0x1bf6, jong 0x1c14, iset 0x1c34, med 0x1c5e, ascii 0x3aa0
    python3 -I tools/nkpspec.py spec NKP.COM -o $OUT/NKP.json  # 17 piece sets; the English font at file 0x39a0
    python3 -I tools/rawcarve.py compose NKP.COM --spec $OUT/NKP.json --syllables all \
        --eng NKP.COM --eng-offset 0x39a0 --ascent 12 -o $OUT/nkp-all.bdf
    python3 tools/bdfface.py --hangul $OUT/nkp-all.bdf --ascii $OUT/nkp-all.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/NKP16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/NKP16.SVF --mask-font none --check -o $OUT/NKP16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/NKP16.SVF --mask-font none --check -o $OUT/NKP16JA.SVF

The spec is offsets and rules only (its first set: `"d0": {"offset": 16800, "stride": 18, "x": 0, "y": 3, "width": 16,
"height": 9}`; the right-half one `"d48": {..., "stride": 14, "x": 8, "y": 1, "width": 8, "height": 14}`). A spec
that gives the right-half records (end - first) / 2 rows draws a wrong face without an error (121,680 bytes, ink 464):
check the numbers. Results:
precomposed `122,276 bytes`, 2,447 glyphs (2,350 syllables, ASCII, U+2026, U+25A1), `width=144 ascent=12 descent=4`, ink
467; the 8x4x4 jamo set `16,452 bytes`, 441 glyphs, 344 pieces, IoU 0.998 over the 2,350 syllables (2,324 exact), 0.2 s;
the adaptive set `28,204 bytes`, 11/5/4 sets and 12 x 12 classes, IoU 1.000 (all 2,350 exact), 2 s; both ink 467, and
`--check` composes all 11,172 syllables. Fitted to all 11,172 composed syllables instead (`--chars-from` a list of all
of them: a 573,076-byte precomposed face): 8x4x4 IoU 0.997 (10,848 exact), adaptive `28,164 bytes`, every syllable
exact, 9 s. The 8x4x4 set misses a few syllables because NKP picks a with-final initial set by vowel shape (four sets)
where 8x4x4 has three.

NKP3.COM is another build of the same driver: `nkpspec.py find` locates its tables (records 0x193e, initial 0x1a08,
vowel 0x1a28, final 0x1a46, initial sets 0x1a66, medial 0x1a90, English 0x6070 = file 0x5f70, as `binscan.py ascii`
finds too), and the same commands (`--eng-offset 0x5f70`) give `122,344 bytes`, ink 494 (a Myeongjo-like face); 8x4x4 `16,432 bytes`, IoU 0.997 (2,282 exact);
adaptive `26,688 bytes`, 9/5/4 sets, IoU 1.000.

<a id="dokkaebi-the-font-inside-the-driver"></a>

### 6.3. Dokkaebi: the font inside the driver

Source: the Hangul Dokkaebi B drivers DKBB.COM (22,035 bytes) and DKBII.COM (20,355 bytes) of a Hangul Dokkaebi B
distribution (`dkbb.rar`, with the driver source DKBB.ASM and DKBBG.FNT / DKBBM.FNT; proprietary). The loose DKBBG.FNT is read in [Other DOS-era Korean fonts](#other-dos-era-korean-fonts); here
the font comes out of the drivers themselves.

    python3 -I tools/binscan.py sets DKBB.COM
    #   offsets 0x5e, 0x60 tie (seam 0.66, 4 nearby reads pass): the same font read a whole row apart; ...
    python3 -I tools/binscan.py ascii DKBB.COM       # offset 0x4cce (19662), edge 0 (fewer than 256 glyphs left in the file)
    python3 -I tools/binscan.py sets DKBII.COM       # offsets 0x105c, 0x105e, 0x1060 tie (seam 0.67, ...)
    python3 -I tools/binscan.py ascii DKBII.COM      # offset 0x5f

`sets` finds an 8x4x4 font in each, but a read shifted by whole rows passes as well when the bytes before the font are
zero. It keeps the reads whose 16-bit rows hold together (the "seam": strokes crossing x = 7 / 8) and lists the ones a
whole row apart together, unranked: the bytes cannot tell them apart. Decide from outside the bytes: in DKBB.COM the
driver source DKBB.ASM puts `han1` at 0x60 (`cmp` finds DKBBG.FNT there, all 15,584 bytes); for DKBII.COM, whose 11,520
bytes at 0x1060 differ from DKBBG.FNT in only 71 (a revised face), the same-layout loose file decides it (0x105c and
0x105e differ from it in 3,372 and 2,768 bytes). Without a source or a loose copy, read the address the drawing routine
uses in the disassembly; a wrong pick moves every syllable by a row.

    python3 -I tools/rawcarve.py cut DKBII.COM --offset 0x1060 --length 11520 -o $OUT/dkbii.fnt
    python3 -I tools/rawcarve.py eng DKBII.COM --offset 0x5f -o $OUT/dkbii-eng.raw
    python3 tools/jamoset.py --layout 844 $OUT/dkbii.fnt --eng $OUT/dkbii-eng.raw --symbols --check -o $OUT/DKBII16J.SVF
    python3 tools/johab844.py $OUT/dkbii.fnt svf/dos/NEODG16.SVF $OUT/DKBII16.SVF --eng $OUT/dkbii-eng.raw

DKBII: jamo set `15,556 bytes`, 441 glyphs, 344 pieces, `check: composed 11172 syllables ... identical to johab844.py`,
`width=144 ascent=14 descent=2`, ink 501; precomposed with `johab844.py` `133,576 bytes`, 2,905 glyphs, ink 501. DKBB (cut at
0x60, English at 0x4cce: 148 glyphs before the file ends, padded to 4,096 bytes): `15,556 bytes`, ink 501. The Dokkaebi 5.1
screen drivers (VDKB5.EXE, MDKB5.EXE, EDKB5.EXE, VDKB24.EXE) hold no font: `sets`, `ascii` and `runs` find nothing,
and they load DKB16.FNT / DKB24.FNT (524,288 and 698,184 bytes, in the shareware `DKB5.ZIP`; row-major 16x16 starting
with the CP437 symbols, in a code order not resolved here).

<a id="korean-vga-font-roms-86box"></a>

### 6.4. Korean VGA font ROMs (86Box)

Source: the 86Box ROM set (https://github.com/86Box/roms, commit 1ac40f2 of 2026-11-14), downloaded file by file (url,
bytes and sha256 recorded beside the files). Its tree lists three Korean VGA
cards, each a 32 KB VGA BIOS and a 512 KB KS C 5601 font ROM: Trigem Korean VGA (ET4000, `video/et4000/tgkorvga.bin`,
`tg_ksc5601.rom`), Kasan ET4000 (`et4000_kasan16.bin`, `kasan_ksc5601.rom`) and ATI 28800 Korean (`video/ati28800/
atikorvga.bin`, `ati_ksc5601.rom`); the other Korean entries are machine BIOSes (Samsung Deskmaster 286, Hyundai Super-16T,
LG IBM, TriGem 286M / 486G) with no Hangul font. The ROMs are dumps of proprietary chips [86Box Korean VGA ROM metadata and rendering](#ref-86box).

    python3 -I tools/binscan.py info tg_ksc5601.rom      # 524288 bytes; size = 16384 x 32 B: 16,384 slots
    python3 -I tools/binscan.py render tg_ksc5601.rom --offset $((0x1821*32)) --glyph 16x16 --order strips --count 4

16,384 slots of 32 bytes is a 128 x 128 grid: the emulator's own source (`src/video/vid_svga_render.c`) indexes it by
`((lead & 0x7F) << 7) | (trail & 0x7F)` and draws byte `scanline` for the left 8 pixels and `scanline + 16` for the right:
two 8-pixel strips of 16 rows (`--order strips`). 가 (B0A1) is slot 0x1821, and the render shows 가 각 간 갇 in all three
ROMs (three different designs). The English font is the BIOS's 8x16 VGA font:

    python3 -I tools/binscan.py ascii tgkorvga.bin                   # offset 0x4a2d, edge 3 (Kasan 0x499a, ATI 0x4d59)
    python3 -I tools/rawcarve.py bdf tg_ksc5601.rom --glyph 16x16 --order strips --chars ks-hangul \
        --grid 0x80,0x80,128 --ascent 12 -o $OUT/tg-hangul.bdf
    python3 -I tools/rawcarve.py bdf tgkorvga.bin --offset 0x4a2d --glyph 8x16 --chars ascii --ascent 12 -o $OUT/tg-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/tg-hangul.bdf --ascii $OUT/tg-ascii.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/TGVGA16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/TGVGA16.SVF --mask-font none --check -o $OUT/TGVGA16J.SVF

`--ascent 12` on both BDFs keeps the ROM's cell as it is (the VGA font's capitals end on row 11). Results (each face 2,447
glyphs; every line `width=144 ascent=12 descent=4`):

| ROM | Precomposed | Ink | 8x4x4 jamo set | IoU (exact of 2,350) | Ink |
|---|---|---:|---|---|---:|
| Trigem (`tg_ksc5601.rom` + `tgkorvga.bin`) | `122,392 bytes` | 476 | `17,172 bytes` | 0.968 (1,576) | 476 |
| Kasan (`kasan_ksc5601.rom` + `et4000_kasan16.bin`) | `124,968 bytes` | 557 | `18,576 bytes` | 0.872 (290) | 566 |
| ATI (`ati_ksc5601.rom` + `atikorvga.bin`) | `123,188 bytes` | 517 | `17,596 bytes` | 0.919 (644) | 517 |

The ROMs hold the whole KS X 1001 table: `--chars ks-nonhanja` adds the symbols and jamo, `ks-all` the Hanja (for
`mkfont.py` on the BDF, which keeps them; `bdfface.py` keeps only syllables and ASCII). `rawcarve.py eng tgkorvga.bin
--offset 0x4a2d` gives the same English font as a raw `--eng` file.

Other ROM sets checked: the openMSX system ROM set (file-hunter's RomDB, 1,241 files) holds three Korean fonts,
the jamo-set font in the Daewoo MSX2 SUB-ROMs, the 256 KB precomposed font of the CPC-400S and the 8x8 jamo cells of the
Korean MSX1 BIOS; the Hangul BASIC ROMs (`cpc-300_hangul`, `dpc-200_hangul`) hold the drivers, no glyphs
([Korean MSX fonts](#korean-msx-fonts-msx2-and-msx1)).
An 88emuplayer ROM pack (`88emuplayer-roms.zip`) holds Roland sound-module ROMs (SC-55, SC-88, SC-8850, CM-300) and no font. The MAME romsets
are in [Korean font ROMs in MAME sets](#korean-font-roms-in-mame-sets).

The desktop app knows the three pairs by size and SHA-256 (the built-in recipes `maker/recipes/86box-tgkorvga.json`,
`86box-kasan16.json`, `86box-atikorvga.json`: names, sizes, hashes and offsets, ROM data supplied separately): pick the folder holding both
files and the font ROM is one row with the faces `TGVGA16` / `KASAN16` / `ATIVGA16` (route `bdfface`) and the jamo sets
`TGVGA16J` / `KASAN16J` / `ATIVG16J` (`bdfface + from-svf fit`, experimental), made by the commands above. A run with
`SVF_MAKER_REAL_86BOX` pointing at the downloaded files (`maker/test/test_recipe.py`) gives every face of the table byte
for byte its size.

<a id="korean-msx-fonts-msx2-and-msx1"></a>

### 6.5. Korean MSX fonts (MSX2 and MSX1)

The Korean MSX computers (Daewoo, Goldstar; 1984-1988) keep three Hangul fonts in ROM, each drawn by a different
rule:

| Machines | Where the font is | Kind | Result |
|---|---|---|---|
| Daewoo CPC-300, CPC-300E, CPC-330K, CPC-400S (MSX2) | upper 16 KB of the SUB-ROM (`cpc-300_msx2sub.rom`), on the CPC-400S the first 16 KB of `CPC-400S.U44` | 16x16 jamo pieces: 6 initial sets x 20, 2 medial x 28, 2 final x 29 | exact jamo set, all 11,172 syllables |
| Daewoo CPC-400, CPC-400S (MSX2) | 256 KB font ROM `cpc-400s_hangulfont.rom` behind I/O ports D8h/D9h | 16x16 precomposed, the machine's own order; code -> slot tables in the "Kanji control ROM" (last 16 KB of `CPC-400S.U44`) | precomposed face of the 2,591 syllables the driver can draw |
| Daewoo DPC-100, DPC-180, DPC-200, Goldstar FC-80U (MSX1) | BIOS character table at 0x1B49 (`dpc-200_basic-bios1.rom`) | 8x8 jamo cells, a syllable = 2 text rows x 1 or 2 columns | precomposed face; the layout rule was read off the running machine |

The Hangul BASIC ROMs (`cpc-300_hangul.rom`, `dpc-200_hangul.rom`, `fc-80u_hangul.rom`) hold the drivers (the
composing code and the MSX-TUTOR program), no glyphs. The recommended path is to give the work to a coding agent with
the prompts of [With a coding agent](#msx-with-a-coding-agent-recommended); the commands after them are the by-hand
path. File names below are the openMSX system ROM names; `$ROMS` is the
folder holding them.

**Source and licence.** The fonts are Daewoo and Goldstar firmware designs in dumps of proprietary ROM chips. Use them
for research; no face of `svf/` is made from them. The openMSX system ROM set is on file-hunter's download server
(folder `System ROMs/RomDB SystemROMs OpenMSX`; the server refuses curl's default User-Agent with HTTP 405, a browser
User-Agent with the folder as Referer works). The openMSX machine files (`share/machines/Daewoo_CPC-300.xml`,
`Daewoo_CPC-400S.xml`, `Daewoo_DPC-200.xml`, `Goldstar_FC-80U.xml`) give each ROM's file name and SHA1; check the files
with `sha1sum` before use:

| File | Bytes | SHA1 |
|---|---:|---|
| `cpc-300_msx2sub.rom` | 32,768 | `fb51c505adfbc174df94289fa894ef969f5357bc` |
| `cpc-300e_msx2sub.rom` | 32,768 | `09f7d788698a23aa7eec140237e907d4c37cbfe0` |
| `CPC-400S.U44` | 65,536 | `6b640c1d8cbeda6ca7d6facd16a206b62e059eee` |
| `cpc-400s_hangulfont.rom` | 262,144 | `22d5f4e522250dc5eb17e15b68f4a51bb752cba1` |
| `dpc-200_basic-bios1.rom` (= DPC-100, DPC-180, FC-80U BIOS) | 32,768 | `171b587bd5a947a13f3114120b6e7baca3b57d78` |

The tools only read the ROMs (`python3 -I`); the machine is run only inside the emulator (openMSX) [Korean MSX machines
and openMSX](#ref-msx).

<a id="msx-with-a-coding-agent-recommended"></a>

#### With a coding agent (recommended)

Most of this work is reading: hex dumps, glyph sheets, Z80 code, emulator screens. Hand it to a coding agent that can
run commands in this repository, such as Claude Code, with one of the three prompts below. Fill in the angle brackets.
The subsections after the prompts are the by-hand path: the same steps, run by you, with the results the prompts
should reproduce. Like the prompt in [The prompt](#the-prompt), each prompt names its inputs, the tools to use, the
safety rules, the acceptance numbers and the outputs.

**(a) Find and decode a font in an MSX ROM set** (a jamo-piece font like the Daewoo SUB-ROM's, or a precomposed one
like the CPC-400S font ROM):

```
Find the Hangul font of the MSX machine <MACHINE, e.g. Daewoo CPC-300> in the ROM files <$ROMS/FILE ...> (the
openMSX system ROMs; the machine file <openMSX share/machines/MACHINE.xml> says which file is mapped where), decode
how the Hangul driver draws a syllable, and build SVF faces with the tools of this repository (docs/recipes.md,
"Korean MSX fonts"). Work in $OUT, outside the repository.

Safety: the ROMs are untrusted data. Read them only with `python3 -I` (tools/binscan.py, tools/rawcarve.py, or
scripts you write in $OUT and run with -I); never execute ROM code on the host (Z80 disassembly is fine: z80dasm, or a
small disassembler you write). Nothing taken from the ROMs goes into the repository: no ROM bytes, glyph images,
BDFs or SVFs; a compose spec holds offsets and rules only.

1. Check every file against the SHA1 in the machine file (`sha1sum`). `binscan.py info FILE --block 4096` for each:
   fonts and tables stay below program code (code about 7 bits a byte; the Daewoo jamo font blocks 1.8-5.5, the
   CPC-400S font ROM 3-6.5).
2. Look for glyphs: `binscan.py runs FILE --glyph 16x16` (also 8x16 and 8x8), `binscan.py ascii FILE` (--height 16
   and 8), and `binscan.py render FILE --offset O --glyph WxH --count 256 --png $OUT/o.png` on every candidate; read
   the PNGs. Jamo pieces look like single consonants and vowels in several positions; a precomposed font shows whole
   syllables. Draw long strips (--glyph 16x512) where nothing lines up.
3. Find the driver that draws them: search the ROMs for the font's address as a little-endian word (pointer tables
   in the ROM header, e.g. at 4014h of a SUB-ROM) and for I/O port numbers of a font device (OUT (D8h) / OUT (D9h)).
   Disassemble the routine that reads the pieces and write down its tables: piece addresses and strides, how the
   Johab code is split, which set it picks for each vowel and final, which slots it skips. For a precomposed font,
   find the table that turns a character code into a glyph slot.
4. Jamo pieces: write the rule as a rawcarve.py compose spec ($OUT/SPEC.json; the format is in the rawcarve.py
   docstring; "slots" renumbers a set whose numbering skips stored slots), with offsets from the start of the font
   block cut by `rawcarve.py cut`. Precomposed: write the code -> slot list as "SLOT U+XXXX" lines for
   `rawcarve.py bdf --chars map`.
5. Build: `jamoset.py --layout spec --spec $OUT/SPEC.json BLOCK --eng ENG --check -o $OUT/<NAME>J.SVF`, and
   `rawcarve.py compose ... --syllables all` + `rawcarve.py bdf --chars ascii` + `bdfface.py` for the precomposed face
   (or `rawcarve.py bdf --chars map` + `bdfface.py`).

Acceptance (report each number):
- `jamoset.py --check` prints "all 11172 syllables identical to rawcarve.py compose";
- a second implementation of the driver's routine, written by you straight from the disassembly in a script of its
  own (not from the spec), composes the same pixels: 0 of 11,172 syllables differ (for a precomposed font: the slot
  list equals the driver's table for every code it accepts, and no listed glyph is blank);
- the machine draws the same glyphs: check a few syllables on the emulator screen as in prompt (c).
Outputs: $OUT/SPEC.json (or the slot list), the SVF faces, and a short report: the files and their SHA1, the offsets
and tables found (with the routine addresses), the commands, the sizes and glyph counts, `svfline.py measure` and the
ink of "안녕하세요 ABC 123", the acceptance numbers, and what you could not resolve.
```

**(b) The emulator method, for a layout no table holds** (the Korean MSX1, where the Hangul ROM arranges BIOS cells by
code):

```
Find out how the Korean MSX1 <MACHINE, e.g. Daewoo_DPC-200> lays out each Hangul syllable in 모아쓰기 mode, by
running the machine in openMSX, and then build the font from the BIOS character table alone (docs/recipes.md,
"Korean MSX fonts", MSX1). Work in $OUT, outside the repository.

Safety: the ROMs are untrusted data. Run their code only inside openMSX (headless: `xvfb-run -a openmsx -machine
MACHINE -script $OUT/s.tcl`, always under `timeout`); read ROM files on the host only with `python3 -I`. Nothing from
the ROMs goes into the repository (no ROM bytes, dumps, screenshots, BDFs or SVFs).

For a machine of the Daewoo / Goldstar family start with `python3 -I tools/msx1_harvest.py MACHINE $OUT/h --emu EMU`
(or `--openmsx BIN`), which does steps 1, 3 and 4 below, and go on at step 5. For another machine, read
tools/msx1_harvest.py and adapt its stored bytes (step 2) and screen geometry in a script of your own in $OUT.

1. Boot the machine from a Tcl script. `set throttle off` makes emulated time run as fast as the host allows (use it
   for typing and dumping; no frames are drawn, so switch it on again before a `screenshot`). Write results to files
   from Tcl: `puts` output does not reach the shell. RAM is the debuggable "Main RAM".
2. Find how a typed syllable is stored: `type "poke -851,0\r"` (모아쓰기), type `10 rem ` and 2-set keys in Hangul
   mode (the Han/Eng key is key matrix row 6 bit 4: `keymatrixdown 6 0x10`, then `after time 0.3 { keymatrixup 6
   0x10 }`: a press shorter than a keyboard scan is missed), dump RAM
   (`debug read_block "Main RAM" 0 0x10000`) and read the BASIC line (the program starts at the word at F676h).
3. Type a BASIC program that waits for a flag in RAM, PRINTs the syllables a Tcl procedure has written at C000h (one
   length byte and the jamo bytes per syllable), 77 to a screen at LOCATE positions (the text window starts 2 columns
   in, so 7 slots of 4 columns a row), then sets a done flag. For each screen dump the SCREEN 1 name table
   (`debug read_block VRAM 0x1800 768`) and once the pattern table (`debug read_block VRAM 0 2048`); 146 screens
   cover all 11,172 syllables (145 x 77 + 7: pad the last batch to 77 with copies of its last syllable, or the
   program prints stale bytes from the batch before). Take one `screenshot` (throttle on) as a visual check.
4. Write $OUT/h.index (the syllables in order, one hex code point a line), $OUT/h.names and $OUT/h.patterns, and
   derive the rule: group the syllables by vowel kind (vertical, ㅗㅛㅜㅠㅡ, compound) and by final (none, one cell,
   two cells) and read which cell codes fill each position.
5. Check the rule with `python3 -I tools/msxfont.py msx1-verify $OUT/h --bios BIOS`. If it differs from
   tools/msxfont.py's layout(), say where and why (another machine may use another rule); do not change the tool to
   fit unexplained data.
6. Build without the emulator: `python3 -I tools/msxfont.py msx1 BIOS -o $OUT/msx1.bdf`, then
   `python3 tools/mkfont.py $OUT/msx1.bdf $OUT/MSX1.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul`.

Acceptance: "layout rule vs the machine: 11172 of 11172 syllables identical"; the VRAM pattern table equals the BIOS
table in 255 of 256 cells (0xFF is the cursor); the same counts on a second machine of the family if you have its
ROMs. Outputs: the Tcl script and the harvest files in $OUT, $OUT/MSX1.SVF, and a short report: the stored bytes found
in step 2, the rule as a table, the verify output, the face's size, glyph count, `svfline.py measure` and ink of
"안녕하세요 ABC 123", the run time, and the pitfalls you hit.
```

**(c) Check a decoded font against the machine screen:**

```
Check the face <$OUT/FACE.SVF>, decoded from the ROMs of <MACHINE>, against what the machine itself draws, in openMSX
(docs/recipes.md, "Korean MSX fonts", "The emulator as ground truth"). Work in $OUT, outside the repository.

Safety: run ROM code only inside openMSX under `xvfb-run` and `timeout`; read files on the host only with `python3 -I`;
nothing from the ROMs, the screens or the dumps goes into the repository.

1. Boot the machine (throttle on for screenshots; the CPC-400S needs about 20 s, the others about 12 s) and make it
   draw known text: a screen the firmware shows by itself (the CPC-300's MSX-TUTOR), or `type` a PRINT of syllables
   (Daewoo MSX2: Hangul in SCREEN 9, strings are Johab codes, `print chr$(&H88)+chr$(&H61)` is 가; in Tcl escape `$` as
   `\$` and `&` as `\&`; MSX1: 모아쓰기 after `poke -851,0`). Pick 20 syllables or more that use every set the rule
   distinguishes (each vowel kind with and without a final, double finals, ㅍ/ㅎ initials).
2. Read what was drawn exactly: in a text mode the name and pattern tables (`debug read_block VRAM ...`); in a bitmap
   mode (SCREEN 5-8; the Daewoo SCREEN 9 is built on SCREEN 6) the VRAM pixels of the text area. `screenshot -raw
   FILE.png` gives the raw MSX screen at 320x240, `screenshot -raw -doublesize FILE.png` at 640x480, which keeps
   every pixel of a 512-wide mode (SCREEN 6, 7 and the Daewoo SCREEN 9; the CPC-300's MSX-TUTOR runs in SCREEN 7);
   a plain `screenshot` is scaled and filtered, use it only to look.
3. Draw the same text from the face (`svfline.py line`, or the glyph rows from jamoset.parse_svfn) and compare pixel
   by pixel at the position the machine used.

Acceptance: for each syllable the number of differing pixels, 0 for all of them; if not, show the difference (both
bitmaps) and say whether the face or the comparison is wrong (screen position, scaling, a cell the screen mode
crops). Outputs: the Tcl script, the dumps and screenshots in $OUT, and a short report with the table of syllables
and differing pixels.
```

#### MSX2: the Daewoo jamo-set font (exact)

By hand, from here on: the commands the prompts above run, with the measured results.

The SUB-ROM's header holds four pointer words at 4014h, 4016h, 4018h and 401Ah (CPU address = file offset): the initial
pieces at 0x59DE, the medial at 0x68DE, the final at 0x6FDE and the 8x16 English font at 0x771E (code 0x10, so code 0
is at 0x761E; `binscan.py ascii` finds 0x761e). Pieces are 32 bytes (16x16, row-major, MSB left) and a syllable is the
OR of three. The Hangul BASIC routine 4DC4h of `cpc-300_hangul.rom` picks the sets by Johab code (M = the medial code):

| Syllable | Initial set | Medial set | Final set |
|---|---|---|---|
| no final, vertical vowel (ㅏ .. ㅣ) | 1 | 7 | - |
| no final, ㅗ ㅛ ㅜ ㅠ ㅡ | 2 | 7 | - |
| no final, ㅘ ㅙ ㅚ ㅝ ㅞ ㅟ ㅢ | 5 | 7 | - |
| final, vertical vowel | 3 | 8 | 10 for ㅏ ㅑ ㅣ, else 9 |
| final, ㅗ ㅛ ㅜ ㅠ ㅡ | 4 | 8 | 9 |
| final, ㅘ ㅙ ㅚ ㅝ ㅞ ㅟ ㅢ | 6 | 8 | 10 for ㅘ ㅚ ㅟ ㅢ, else 9 |

Piece numbers: initial (set - 1) x 20 + code - 1 (Johab initial 2 .. 20), medial (set - 7) x 28 + M - 2, final
(set - 9) x 29 + code - 1. Johab final codes skip 18, so a final set has 29 slots for 27 finals. The whole font block
is 0x59DE .. 0x7E1E, 9,280 bytes: the 234 pieces (7,488 bytes, to 0x771E), then the 8x16 English font (codes
0x10-0x7F, 1,792 bytes). The rule is the compose spec `tools/specs/msx2-daewoo.json`: its
offsets are from the block's start, its final sets list their used slots (`"slots"`), so the one spec reads the block
of every model:

    python3 -I tools/rawcarve.py cut $ROMS/cpc-300_msx2sub.rom --offset 0x59DE --length 9280 -o $OUT/cpc300-font.bin
    python3 -I tools/rawcarve.py cut $ROMS/CPC-400S.U44 --offset 0x19E8 --length 9280 -o $OUT/cpc400s-font.bin
    cmp $OUT/cpc300-font.bin $OUT/cpc400s-font.bin        # identical (also the CPC-300E's at 0x59DE)
    python3 -I tools/rawcarve.py eng $ROMS/cpc-300_msx2sub.rom --offset 0x761E -o $OUT/cpc300-eng.bin
    python3 -I tools/jamoset.py --layout spec --spec tools/specs/msx2-daewoo.json $OUT/cpc300-font.bin \
        --eng $OUT/cpc300-eng.bin --check -o $OUT/CPC300J.SVF
    #   ... 10584 bytes, 210 pieces of 16x16 ... by the spec's rule (6/2/2 sets, 1x2 classes)
    #   check: all 11172 syllables identical to rawcarve.py compose
    python3 -I tools/rawcarve.py compose $OUT/cpc300-font.bin --spec tools/specs/msx2-daewoo.json --syllables all \
        --ascent 14 -o $OUT/cpc300-hangul.bdf
    python3 -I tools/rawcarve.py bdf $ROMS/cpc-300_msx2sub.rom --offset 0x761E --glyph 8x16 --chars ascii --ascent 14 \
        -o $OUT/cpc300-ascii.bdf
    python3 -I tools/bdfface.py --hangul $OUT/cpc300-hangul.bdf --ascii $OUT/cpc300-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/CPC300.SVF

On the CPC-400S the same block sits 10 bytes further in its copy of the SUB-ROM half (pointers 59E8h, 68E8h, 6FE8h,
7728h), which is the first 16 KB of `CPC-400S.U44`, mapped at 4000h: hence 0x19E8. Results (2026-11-27): jamo set
`10,584 bytes`, 305 glyphs (210 pieces, 95 ASCII), JSET 707 bytes, `width=144 ascent=14 descent=2`, ink 333;
precomposed `125,012 bytes`, 2,447 glyphs, the same line and ink. All 11,172 syllables composed by the spec are
identical to an independent implementation of routine 4DC4h, for the CPC-300 and the CPC-400S ROM alike.

#### MSX2: the CPC-400S precomposed font

`cpc-400s_hangulfont.rom` is 262,144 bytes, 8,192 slots of 32 bytes (16x16, row-major). The driver writes the slot's
low 6 bits to port D8h and the high 7 bits to D9h and reads 32 bytes from D9h (openMSX's `MSXKanji` device, type
`hangul`). Slot map: 0-1408 KS X 1001 symbols (slot = (row - 1) x 94 + column - 1, rows 1-15), 1410-2725 Hangul list A
(1,316 syllables), 2726-4416 hanja group 1, 4417-5693 Hangul list B (1,275 syllables), then two more hanja groups.
The syllables are in the machine's own order, so the font is read through the driver's tables: routine 8A96h of the
Kanji control ROM (the last 16 KB of `CPC-400S.U44`, mapped at 8000h) takes the Johab code, finds the trail byte in
list A (start offsets per lead byte 88h .. D3h at 97BFh, trail bytes at 98F3h) or list B (9859h, 9E18h), and draws slot
0581h + index (A) or 1141h + index (B). `tools/msxfont.py kfn-map` reads those tables into a slot list and
`rawcarve.py bdf --chars map` cuts the glyphs:

    python3 -I tools/msxfont.py kfn-map $ROMS/CPC-400S.U44 -o $OUT/cpc400s-map.txt
    #   2591 syllables (2217 of the 2,350 KS X 1001), slots 1410..5692
    python3 -I tools/rawcarve.py bdf $ROMS/cpc-400s_hangulfont.rom --glyph 16x16 --chars map --map $OUT/cpc400s-map.txt \
        --ascent 14 -o $OUT/cpc400s-hangul.bdf
    python3 -I tools/rawcarve.py bdf $ROMS/CPC-400S.U44 --offset 0x3628 --glyph 8x16 --chars ascii --ascent 14 \
        -o $OUT/cpc400s-ascii.bdf
    python3 -c "import sys; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in range(0xAC00, 0xD7A4)))" $OUT/all.txt
    python3 -I tools/bdfface.py --hangul $OUT/cpc400s-hangul.bdf --ascii $OUT/cpc400s-ascii.bdf --cell 16x16 \
        --chars-from $OUT/all.txt -o $OUT/CPC400S.SVF

Results: `137,416 bytes`, 2,688 glyphs (2,591 syllables, 95 ASCII, U+2026, U+25A1), `width=144 ascent=14 descent=2`,
ink 437. With `--chars-from $OUT/ks.txt`: 2,217 syllables, `117,976 bytes` (133 of the 2,350 KS syllables, among them 갊 걜 곌,
are not in the ROM; of the syllables outside KS X 1001 it has only those its lists name, so 뷁 and 힣 are absent too). An 8x4x4 fit of the face (`jamoset.py --layout 844 --from-svf`) reaches only IoU 0.794 (`19,900
bytes`, 83 syllables exact): the precomposed design is not built from jamo pieces. The hanja groups use the driver's
own codes (lead byte D4h and up), not KS X 1001, and are left out.

#### MSX1: the jamo cells of the BIOS, laid out as the machine does

The Korean MSX1 BIOS replaces the standard character table (0x1BBF) with its own at 0x1B49: 256 cells of 8x8, Latin at
0x20-0x7E, the 19 initials at 0x86-0x98, the vowels at 0x99-0xA6 and 85 "initial over ㅗ ㅛ ㅜ ㅠ ㅡ" cells at
0xA7-0xFB (the last 10 continue at 0x02-0x0B), stem pieces at 0x0C-0x0E. In 모아쓰기 mode (`POKE -851,0`) the Hangul ROM
prints a syllable as 2 text rows of these cells, 1 column wide for a ㅗ ㅛ ㅜ ㅠ ㅡ syllable without a double final, 2
otherwise. Which cells go where is not stored in a table: it was read from the running machine.

The method (openMSX 19.1, machine `Daewoo_DPC-200`, headless under Xvfb), run by `tools/msx1_harvest.py`. `$EMU` is
an openMSX unpacked without installing it (the Debian package `dpkg -x` into `$EMU/root`, the system ROMs in
`$EMU/userdata/share/systemroms`); with an installed openMSX give `--openmsx $(which openmsx)` instead of `--emu`.
`$HARVEST` is a folder outside the repository:

    python3 -I tools/msx1_harvest.py Daewoo_DPC-200 $HARVEST/dpc200 --emu $EMU
    #   wrote .../dpc200.tcl and .../dpc200.index: 11172 syllables in 146 screens
    #   openMSX exit 0; screens dumped 146 of 146; screenshot .../dpc200.png
    python3 -I tools/msxfont.py msx1-verify $HARVEST/dpc200 --bios $ROMS/dpc-200_basic-bios1.rom
    #   layout rule vs the machine: 11172 of 11172 syllables identical
    #   VRAM pattern table vs the BIOS table: 255 of 256 cells identical (differ: 0xff)

The harvest takes 5 seconds of real time (2026-11-27). Cell 0xFF is the cursor. `Goldstar_FC-80U` gives the same
counts and a byte-identical `.names` file. What the script does, step by step (its Tcl is `$HARVEST/dpc200.tcl`;
`--script-only` writes it without running the emulator):

1. It runs `timeout 600 xvfb-run -a openmsx -machine Daewoo_DPC-200 -script $HARVEST/dpc200.tcl` (`--timeout`
   changes the 600). The script starts with `set throttle off`: emulated time runs as fast as the host allows, and
   no frames are drawn; it turns throttle on again before its one screenshot and ends with `exit`.
2. The bytes typed for each syllable were found first by hand: type 2-set keys into a BASIC `REM` line (Han/Eng is key
   matrix row 6, bit 4: `keymatrixdown 6 0x10`, then `after time 0.3 { keymatrixup 6 0x10 }`, held across a keyboard
   scan) and read the program back from RAM (`debug read_block "Main RAM" 0 0x10000`, the program from the address
   at F676h). A syllable is stored as jamo bytes: the initial 0x86 + L, the vowel cell (ㅏ 99 ㅐ 9A ㅑ 9B ㅒ 9C ㅓ 9D
   ㅔ 9E ㅕ 9F ㅖ A0 ㅗ A1 ㅛ A2 ㅜ A3 ㅠ A4 ㅡ A5 ㅣ A6; a compound vowel is two: ㅘ = A1 99, ㅢ = A5 A6), the final as its
   consonant cells (ㄳ = 86 8F). The ROM composes at print time. The script writes these bytes directly.
3. It types `poke -851,0` (모아쓰기) and this program, then `run`: `10 defint a-z`, `20 if peek(&hbffe)=0 then 20`,
   `30 poke &hbffe,0:poke &hbfff,0:cls:a=&hc000`, `40 for k=0 to 76`, `50 locate (k mod 7)*4,(k\7)*2`,
   `60 n=peek(a):a=a+1`, `70 for j=1 to n:print chr$(peek(a));:a=a+1:next`, `80 print " ";`, `90 next`,
   `100 poke &hbfff,1`, `110 goto 20`. 77 syllables a screen (7 to a row: the text window starts 2 columns in, so a
   row holds 7 slots of 4 columns, not 8).
4. For each screen it writes 77 syllables (a length byte and the jamo bytes each) at C000h with `debug write_block
   "Main RAM" 0xC000 ...`, sets BFFEh to 1, waits until the program sets BFFFh to 1, and appends the SCREEN 1 name
   table to `.names` (`debug read_block VRAM 0x1800 768`); once, the pattern table to `.patterns` (`debug read_block
   VRAM 0 2048`). 146 screens cover the 11,172 syllables (145 x 77 + 7: the last screen is padded to 77 with copies of
   its last syllable, else the program would print stale bytes). Results go to files: `puts` output does not reach
   the shell.
5. Visual check: the last screen as `screenshot -raw -doublesize` in `.png`.
6. The rule was derived from the name tables (cell codes per syllable, sorted by vowel kind and final);
   `msxfont.py msx1-verify` checks it against every syllable (above).

The rule (L = initial cell 0x86 + L; v, h = vowel cells; T1, T2 = final cells; _ = blank 0xFC; M(L, h) = merged cell
0xA7 + 5L + h, h = 0 .. 4 for ㅗ ㅛ ㅜ ㅠ ㅡ, wrapping to 0x02 for ㅍ ㅎ; ext(v) = stem 0C for ㅏ ㅑ ㅣ, 0D for ㅓ ㅕ, 0E for
ㅐ ㅒ ㅔ ㅖ):

| Vowel | No final | Final |
|---|---|---|
| vertical v | `[L v] / [_ ext(v)]` | `[L v] / [T1 T2 or _]` |
| ㅗ ㅛ ㅜ ㅠ ㅡ (h) | `[L] / [h]` | one cell `[M(L,h)] / [T1]`, two `[M(L,h) _] / [T1 T2]` |
| compound h + v | `[L v] / [h ext(v)]` | `[M(L,h) v] / [T1 T2 or _]` |

With the rule the emulator is no longer needed: `tools/msxfont.py msx1` builds the font from the BIOS table alone, and
`mkfont.py` keeps each glyph's own advance (8 or 16):

    python3 -I tools/msxfont.py msx1 $ROMS/dpc-200_basic-bios1.rom -o $OUT/msx1.bdf
    #   11172 syllables (1615 8x16, 9557 16x16) + 95 ASCII (8x8 at row 8), ascent 16
    python3 tools/mkfont.py $OUT/msx1.bdf $OUT/MSX1.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

Results: `106,504 bytes`, 2,445 glyphs, `width=136 ascent=16 descent=0`, ink 238. ASCII is the machine's 8x8 cell on
the baseline (`--ascii-top 8`), next to 16-row Hangul, as the screen draws it. `bdfface.py` would step every syllable
by 16 pixels; use `mkfont.py` here. The DPC-100, DPC-180 and FC-80U BIOS ROMs are byte-identical to the DPC-200's.

#### TrueType files

Each face goes on to a TrueType bitmap font ([An SVF face back to a TTF bitmap font](#an-svf-face-back-to-a-ttf-bitmap-font)):

    python3 tools/svf2ttf.py ttf $OUT/CPC300J.SVF $OUT/CPC300J.ttf --composite --licence none
    python3 tools/svf2ttf.py ttf $OUT/CPC400S.SVF $OUT/CPC400S.ttf --licence none
    python3 tools/svf2ttf.py ttf $OUT/MSX1.SVF $OUT/MSX1.ttf --licence none

Results: `671,640 bytes` (210 pieces, 11,172 composite syllables, 11,318 glyphs), `623,164 bytes` (2,688 glyphs),
`374,680 bytes` (2,445 glyphs), each with a 16 px strike. `--licence none` because no licence note goes with these
fonts.

#### The emulator as ground truth

A decoded ROM font is checked against what the machine draws:

- **Screenshot of typed text.** A Tcl script that types and shoots (`set renderer SDL`, `after time 12 { type
  "print 1\r"; after time 3 { screenshot OUT.png; exit } }`; times are emulated seconds, keep throttle on). The CPC-300
  boots into MSX-TUTOR, whose first screen ("아이큐 교실은 컴퓨터를 처음 배우는 분을 위하여 ...") is drawn with the
  SUB-ROM jamo font: compare it with `svfline.py line` of the same text from `CPC300J.SVF`. The CPC-400S needs about 20
  seconds to boot and Hangul output needs SCREEN 9; strings are Johab codes, so `type "screen 9\rprint
  chr\$(\&H88)+chr\$(\&H61)+chr\$(\&H88)+chr\$(\&H62)+chr\$(\&HB7)+chr\$(\&H65)\r"` (in Tcl `$` and `&` escaped) prints
  가각은 from the 256 KB font. The screenshot is scaled (640 x 480 from 512-pixel lines), so compare shapes by eye.
- **VRAM dump.** For a text screen, the name table and pattern table give the cells exactly (`debug read_block VRAM
  ...`, as in the MSX1 harvest): this is pixel-exact where a screenshot is not.
- **RAM dump.** `debug read_block "Main RAM" ...` shows what the driver stored for typed keys (step 2 above).

<a id="korean-font-roms-in-mame-sets"></a>

## 7. Korean font ROMs in MAME sets

Korean home computers and Korean arcade games keep their Hangul fonts in ROM chips, and MAME's romsets hold dumps of
them. None is 24x24: the fonts found are 16x16, one a jamo-piece set (the Samsung SPC-1500), the others precomposed
(완성형) sets of game sprites. The tools: `rawcarve.py region` joins a game's ROM files into the region the MAME driver
loads; `binscan.py` / `rawcarve.py` read inverted fonts (`--invert`) and multi-bit sprite tiles (`--gfx`, with the
driver's own `gfx_layout` numbers, reduced to 1 bpp by a pen rule: `--bg PEN`, or `--fg PENS`); `rawcarve.py ink` writes
the 1 bpp glyphs the other tools read; `jamoset.py --layout spec` builds an exact jamo set from a compose spec; and
`rawcarve.py eng --width 16` / `jamoset.py --eng` take 16-wide English cells. Like the drivers of [Finding a font inside a
program or data file](#finding-a-font-inside-a-program-or-data-file-with-claude), the ROMs are only read: no game is run
(an emulator would be fine; the drawing rules below were read from MAME's source and from the game's 68000 code,
disassembled) [MAME machine metadata, ROM loading and tile layouts](#ref-mame).

**Source and licence.** The MAME 0.289 romsets on archive.org (item `mame-roms-non-merged`, the zip of each set, e.g.
`spc1500.zip`): dumps of proprietary ROM chips. Obtain the files under their applicable terms. Check every file against the driver before use: the SHA1 in its `ROM_LOAD` line (MAME source
`src/mame/samsung/spc1500.cpp`, `dataeast/tumbleb.cpp`, `seibu/raiden2.cpp`, `snk/midas.cpp`, `snk/neogeo.cpp`) must
equal `sha1sum FILE`. Below, `$MAME` is a folder holding each set unpacked as `$MAME/<set>/<file>`; the same folder in
`MAME_ROMS` turns on the real-ROM checks of `tools/test_tiles.py` (hashes only). The driver's `ROM_LOAD` lines say how
the region is built:

| Driver line | `rawcarve.py region` |
|---|---|
| `ROM_LOAD` of several files at consecutive offsets | `region A B C D` (one after another) |
| `ROM_LOAD16_BYTE` A at 0, B at 1 (and C, D at the next offset) | `region A,B C,D` (`--unit 1`: a byte of each in turn) |
| `ROM_LOAD32_WORD` A at 0, B at 2; `ROM_LOAD64_WORD` A, B, C, D at 0, 2, 4, 6 | `region --unit 2 A,B` / `A,B,C,D` |
| `ROM_LOAD16_WORD_SWAP` (a 68000 program) | `region --swap A` |

A path with a comma in it (a folder named `ROMs, Korean`) is one file with `--group`: `region --group A B --group C D`
(the same region as `region A,B C,D`; the desktop app always writes this form).

The tile layout is the driver's `gfx_layout` (or a `gfx_WxHxN_packed_lsb` / `_msb` preset), copied into `--gfx` as
`planes=..;x=..;y=..;inc=N`: the same numbers, `STEP8(...)` and `RGN_FRAC(1,2)` included, without the braces and any C
comments.

<a id="samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact"></a>

### 7.1. Samsung SPC-1500: a jamo set in four inverted ROMs (exact)

Source: set `spc1500` (Samsung SPC-1500, 1987), files `ss150fnt.bin` (English: 8x8 at 0, 8x16 at 0x1000),
`ss151fnt.bin`, `ss152fnt.bin`, `ss153fnt.bin` (initial, medial and final pieces), 8,192 bytes each. MAME loads them one
after another as the 32 KB region `font1` and draws a syllable in `crtc_update_row`: it splits the Samsung code into h1
(initial, 1 = ㄱ), h2 (the Johab vowel code) and h3 (final, 0 = none), and ANDs three 16x16 pieces stored in 8-pixel
strips (left byte n, right byte n + 16):

    initial  0x2000 + h1 * 32 + (cho[h2] + (h3 != 0) - 1) * 0x400
    medial   0x4000 + h2 * 32 + (h3 != 0) * 0x400
    final    0x6000 + h3 * 32 + (jong[h2] - 1) * 0x400

ANDing means the ink is the 0 bits: every ROM is inverted (`--invert`). `cho[]` (1, 3 or 5) and `jong[]` (1 or 2) are
two 30-entry tables in the driver: 6 of the 8 initial sets are used (vertical, horizontal and compound vowels, each
without and with a final), 2 medial sets, 2 final sets. That rule is `rawcarve.py`'s built-in compose spec `spc1500`,
and the jamo set takes it as it is (a JSET with one lead class and 6/2/2 sets expresses it exactly, so nothing is
fitted):

    python3 -I tools/rawcarve.py region $MAME/spc1500/ss150fnt.bin $MAME/spc1500/ss151fnt.bin \
        $MAME/spc1500/ss152fnt.bin $MAME/spc1500/ss153fnt.bin -o $OUT/spc1500-font.bin     # 32768 bytes
    python3 -I tools/rawcarve.py eng $OUT/spc1500-font.bin --offset 0x1000 --invert -o $OUT/spc1500-eng.bin
    python3 tools/jamoset.py --layout spec --spec spc1500 $OUT/spc1500-font.bin --eng $OUT/spc1500-eng.bin \
        --check -o $OUT/SPC1500J.SVF
    #   ... 210 pieces of 16x16 ... by the spec's rule (6/2/2 sets, 1x2 classes)
    #   check: all 11172 syllables identical to rawcarve.py compose
    python3 -I tools/rawcarve.py compose $OUT/spc1500-font.bin --spec spc1500 --ascent 14 -o $OUT/spc1500-hangul.bdf
    python3 -I tools/rawcarve.py bdf $OUT/spc1500-font.bin --offset 0x1000 --glyph 8x16 --chars ascii --invert \
        --ascent 14 -o $OUT/spc1500-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/spc1500-hangul.bdf --ascii $OUT/spc1500-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/SPC1500.SVF

Verified (2026-11-23): jamo set `10,652 bytes`, 305 glyphs (210 pieces, 95 ASCII), `width=144 ascent=14 descent=2`, ink
470; precomposed `122,636 bytes`, 2,447 glyphs, the same line and ink. Every one of the 11,172 syllables of the jamo set
equals MAME's AND of the three pieces (`tools/test_tiles.py` reads the driver's formula independently; slot 0 of each
final set is blank, so a syllable without a final draws the same). The 8x4x4 fit of the precomposed face (`--layout 844
--from-svf`) reaches only IoU 0.987 (16,468 bytes): without a final, the SPC-1500 picks its initial set
from three vowel shapes, where 8x4x4 has five.

<a id="date-quiz-go-go-a-2350-syllable-sprite-font"></a>

### 7.2. Date Quiz Go Go: a 2,350-syllable sprite font

Source: set `dquizgo` (SemiCom / AceVer, 1998, Korea), sprite ROMs `uor1` .. `uor4` (524,288 bytes each), loaded
`ROM_LOAD16_BYTE` in pairs (uor1/uor2 at 0, uor3/uor4 at 0x100000) and drawn with `tlayout` of
`dataeast/tumbleb.cpp`: 16x16, 4 planes, two in each half of the region. Pen 0 is transparent, so ink = pen != 0
(the default `--bg 0`): the OR of the four planes. The font is a dense KS X 1001 table of 2,350 syllables at sprite
13347; the English font (16 wide, ink up to column 9) is sprites 0.. from the space.

    python3 -I tools/rawcarve.py region $MAME/dquizgo/uor1,$MAME/dquizgo/uor2 \
        $MAME/dquizgo/uor3,$MAME/dquizgo/uor4 -o $OUT/dquizgo-spr.bin                          # 2,097,152 bytes
    python3 -I tools/rawcarve.py ink $OUT/dquizgo-spr.bin \
        --gfx 'planes=RGN_FRAC(1,2)+8,RGN_FRAC(1,2)+0,8,0;x=STEP8(16*8*2,1),STEP8(0,1);y=STEP16(0,8*2);inc=64*8' \
        -o $OUT/dquizgo-ink.bin                                                              # 16384 glyphs, 15684 inked
    python3 -I tools/rawcarve.py bdf $OUT/dquizgo-ink.bin --offset $((13347*32)) --glyph 16x16 --chars ks-hangul \
        --dense --ascent 14 -o $OUT/dquizgo-hangul.bdf
    python3 -I tools/rawcarve.py bdf $OUT/dquizgo-ink.bin --glyph 16x16 --chars ascii --first 0x20 --count 95 \
        --ascent 14 -o $OUT/dquizgo-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/dquizgo-hangul.bdf --ascii $OUT/dquizgo-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/DQUIZGO.SVF
    python3 -I tools/rawcarve.py eng $OUT/dquizgo-ink.bin --offset 0 --width 16 --first 0x20 -o $OUT/dquizgo-eng16.bin
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/DQUIZGO.SVF --mask-font none --eng $OUT/dquizgo-eng16.bin \
        --check -o $OUT/DQUIZGOJ.SVF

(`rawcarve.py bdf $OUT/dquizgo-spr.bin --gfx '...' --offset $((13347*64))` reads the tiles directly, the same BDF.)
Verified: precomposed `115,916 bytes`, 2,447 glyphs, `width=208 ascent=14 descent=2` (the English cells step 16), ink
573 (wider than 200: `line 220 24 0 16`, as for every 208-wide line here); jamo set `16,864 bytes`, 441 glyphs, IoU
1.000 (2,347 of 2,350 exact: the font was itself drawn from 8x4x4 pieces, of a design none of the known DOS fonts has),
`width=160` (the 16x16 `--eng` steps 10: the ink of its letters and digits ends at column 9 and the leftmost starts at
column 0), ink 573.

<a id="x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check"></a>

### 7.3. X Se Dae Quiz: Taebaek GOTHIC16 in the sprites (a cross-check)

Source: set `xsedae` (Dream Island, 1995), `obj-1.u0811` and `obj-2.u082` (2 MB each), `ROM_LOAD32_WORD` and
`gfx_16x16x4_packed_lsb` (`seibu/raiden2.cpp`). Here the background is the last pen: ink = pen != 15. The first 360
sprites are a raw 8x4x4 font, and the English font (16 wide: a few glyphs reach column 15) follows from `!`.

    python3 -I tools/rawcarve.py region --unit 2 $MAME/xsedae/obj-1.u0811,$MAME/xsedae/obj-2.u082 -o $OUT/xsedae-obj.bin
    python3 -I tools/rawcarve.py ink $OUT/xsedae-obj.bin --gfx 16x16x4_packed_lsb --bg 15 --count 600 -o $OUT/xsedae-ink.bin
    python3 -I tools/binscan.py sets $OUT/xsedae-ink.bin              # offsets 0x0, 0x2 tie: the font starts at 0
    python3 -I tools/rawcarve.py cut $OUT/xsedae-ink.bin --offset 0 --length 11520 -o $OUT/xsedae.fnt
    python3 -I tools/rawcarve.py eng $OUT/xsedae-ink.bin --offset $((360*32)) --width 16 --first 0x21 -o $OUT/xsedae-eng16.bin
    python3 tools/jamoset.py --layout 844 $OUT/xsedae.fnt --eng $OUT/xsedae-eng16.bin --check -o $OUT/XSEDAE16J.SVF

`xsedae.fnt` is byte for byte Taebaek 3.5.1's `GOTHIC16.FNT` (the [Other DOS-era Korean fonts](#other-dos-era-korean-fonts)
source), so the game adds no design; it checks the tile path. Verified: `15,780 bytes`, 439 glyphs, `check: ...
identical to johab844.py`, `width=144 ascent=14 descent=2` (the 16x16 English font measures a step of 8), ink 617.

<a id="quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen"></a>

### 7.4. Quiz King of Fighters (Korea): a 2,350-syllable font with an outline pen

Source: set `quizkofk` (Saurus / Viccom, 1996, Neo Geo), sprite ROMs `vic-080-c1.c1` .. `vic-080-c4.c4` (2 MB each),
`ROM_LOAD16_BYTE` pairs c1/c2 and c3/c4. Neo Geo sprite tiles are 16x16, 4 bpp, 128 bytes: the left 8 pixels at byte
0x40, the right 8 at 0; a row is 4 bytes; pen bits 3, 2, 1, 0 in bytes 3, 1, 2, 0; bit x is pixel x (MAME
`snk/neogeo_spr.cpp`, `optimize_helper`). The Korean version keeps the Japanese font's layout (JIS order: symbols,
digits at sprite 108, A-Z at 118, a-z at 144, kana, Greek, Cyrillic) and puts a dense KS X 1001 table of 2,350
syllables at sprite 512 where the kanji were. Each glyph is pen 1 drawn with an outline of pen 3: `--fg 1` takes the
body without the outline.

    NEO='planes=24,8,16,0;x=STEP8(0x40*8+7,-1),STEP8(7,-1);y=STEP16(0,32);inc=1024'
    python3 -I tools/rawcarve.py region $MAME/quizkofk/vic-080-c1.c1,$MAME/quizkofk/vic-080-c2.c2 \
        $MAME/quizkofk/vic-080-c3.c3,$MAME/quizkofk/vic-080-c4.c4 -o $OUT/quizkofk-spr.bin   # 8,388,608 bytes
    python3 -I tools/rawcarve.py ink $OUT/quizkofk-spr.bin --gfx "$NEO" --fg 1 --count 4096 -o $OUT/quizkofk-ink.bin
    python3 -I tools/rawcarve.py bdf $OUT/quizkofk-ink.bin --offset $((512*32)) --glyph 16x16 --chars ks-hangul \
        --dense --ascent 14 -o $OUT/quizkofk-hangul.bdf
    python3 -I tools/rawcarve.py eng $OUT/quizkofk-ink.bin --offset $((108*32)) --width 16 --first 0x30 --count 10 -o $OUT/e1
    python3 -I tools/rawcarve.py eng $OUT/quizkofk-ink.bin --offset $((118*32)) --width 16 --first 0x41 --count 26 -o $OUT/e2
    python3 -I tools/rawcarve.py eng $OUT/quizkofk-ink.bin --offset $((144*32)) --width 16 --first 0x61 --count 26 -o $OUT/e3
    python3 -c "import sys; a=[open(f,'rb').read() for f in sys.argv[2:]]; open(sys.argv[1],'wb').write(bytes(x|y|z for x,y,z in zip(*a)))" \
        $OUT/quizkofk-eng16.bin $OUT/e1 $OUT/e2 $OUT/e3
    python3 -I tools/rawcarve.py bdf $OUT/quizkofk-eng16.bin --glyph 16x16 --chars ascii --ascent 14 -o $OUT/quizkofk-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/quizkofk-hangul.bdf --ascii $OUT/quizkofk-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/QUIZKOFK.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/QUIZKOFK.SVF --mask-font none --check -o $OUT/QUIZKOFKJ.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/QUIZKOFK.SVF --mask-font none --check -o $OUT/QUIZKOFKJA.SVF

The English letters and digits are full-width JIS glyphs in 16-pixel cells; punctuation is left blank (the JIS symbol
row is in another order). Verified (ink from `line 220 24 0 16`: the line is 208 wide): precomposed `123,640 bytes`, 2,447 glyphs, `width=208
ascent=14 descent=2`, ink 477; 8x4x4 jamo set `19,620 bytes`, IoU 0.835 (271 exact), ink 494; adaptive `62,084 bytes`,
32/13/12 sets, 12 x 12 classes, IoU 0.975 (1,522 exact), ink 477. The font is not drawn from pieces: keep the precomposed face.

<a id="live-quiz-show-the-rule-read-the-pieces-not-aligned-not-built"></a>

### 7.5. Live Quiz Show: the rule read, the pieces not aligned (not built)

Source: set `livequiz` (Andamiro, 1999), program `flash.u1` (`ROM_LOAD16_WORD_SWAP`), sprites `flash.u15`, `u19`, `u16`,
`u20` (`ROM_LOAD64_WORD`, `layout16x16x8` of `snk/midas.cpp`, ink = pen != 0):

    python3 -I tools/rawcarve.py region --unit 2 $MAME/livequiz/flash.u15,$MAME/livequiz/flash.u19,$MAME/livequiz/flash.u16,$MAME/livequiz/flash.u20 \
        -o $OUT/livequiz-spr.bin
    python3 -I tools/rawcarve.py ink $OUT/livequiz-spr.bin \
        --gfx 'planes=56,48,40,32,24,16,8,0;x=16*64+7,16*64+6,16*64+5,16*64+4,16*64+3,16*64+2,16*64+1,16*64,7,6,5,4,3,2,1,0;y=STEP16(0,64);inc=16*128' \
        -o $OUT/livequiz-ink.bin
    python3 -I tools/rawcarve.py region --swap $MAME/livequiz/flash.u1 -o $OUT/livequiz-prg.bin

The quiz text is Johab. The drawing routine (68000 code at 0x1f06; two more routines with the same tables at 0x2154 and 0x22e4) splits a Johab code into
its fields, maps them with four word tables (initial at 0x1dec: Johab code - 1, so 0 = none and ㄱ = 1; vowel at 0x1e18:
0 = none, ㅏ = 1 .. ㅣ = 21; final at 0x1e58: Unicode T; final set by vowel at 0x1e98: 84, 0, 56, 0, 56, 28, 56, 28, 56,
84, 0, 56, 28, 84, 84, 28, 56, 28, 84, 84, 28, 28 for none, ㅏ .. ㅣ) and draws two sprites at the same place, the
initial+vowel ("CV") tile `base + vowel * 20 + initial` (+ 440 with a final) and the final tile `base + 880 + T +
set`; the symbols follow at `base + 992`. So the font is 22 groups of 20 CV tiles without a final, the same with one,
and four final sets of 28. The sprite ROM holds one such font from sprite 4840, but packed without the slots no syllable
draws: the CV set without a final matches the rule at base 4840 (가 = 4861), the CV set with a final starts one tile
early (5279 + vowel * 20 + initial), the final sets two (ㄱ of the first at 5719), only three final sets are whole (27
tiles each) and a fourth holds 8 finals, and the symbols start at 5806, not 5832. With this placement the syllables
without a final compose right; the vowel-to-final-set assignment of the code does not fit the three whole sets, and the
finals of ㅜ / ㅠ overlap their CV tiles in every set. Either the dump's sprite flash and the program are of different
revisions, or a translation step was not found; no face is built until the final sets are placed.

The desktop app knows the four sets by size and SHA-256 (and the SHA1 of MAME's `ROM_LOAD` lines), from the built-in
recipes `maker/recipes/mame-spc1500.json`, `mame-dquizgo.json`, `mame-xsedae.json` and `mame-quizkofk.json` (names, sizes,
hashes, offsets and the drivers' layouts, ROM data supplied separately). Pick the set's folder (unpacked: a zip is not read yet);
the files the recipe names are one row, the set's other ROMs stay unknown. The faces and routes: `SPC1500` (`bdfface` of
the composed syllables) and `SPC1500J` (route `spec`, exact); `DQUIZGO` and `DQUIZGOJ` (`bdfface + from-svf fit`, with
the 16-wide English); `XSEDA16J` (route `dos raw`: the 8x4x4 font cut from the inked sprites, the doc's `XSEDAE16J`,
named within 8 characters); `QUIZKOFK` and `QUIZKOFJ` (the 8x4x4 fit). The commands are the ones above, with `rawcarve.py
ink --offset O --count N` before an English font or a raw set read from tiles (the same glyphs as inking the whole region
and cutting at the glyph offset), and Quiz King of Fighters' three English runs OR-ed by `maker/srcprep.py or-files`
(the `python3 -c` line above). With `SVF_MAKER_REAL_MAME` pointing at `$MAME` (`maker/test/test_recipe.py`) every face
has the size given above.

<a id="sets-with-no-font-or-with-a-font-not-resolved"></a>

### 7.6. Sets with no font, or with a font not resolved

- `quizdaisk` (Quiz Salibtamjeong, Neo Geo, 1995): its sprites (c1/c2, the Neo Geo layout above, `--fg 1`) hold a 16x16
  Hangul set from sprite 4097 in KS X 1001 order with gaps (가 각 간 갇 갈 감 ..., no 갉 갊; about 1,467 tiles are
  glyphs, the others pictures or blank): the game's own character list, which its program did not show (no KS table
  in `123-p1.p1`). The fix-layer `123-s1.s1` (8x8, `--gfx 'planes=0,1,2,3;x=132,128,196,192,4,0,68,64;y=STEP8(0,8);inc=256'`)
  holds only words drawn as pictures. `quizkofk`'s fix layer holds no Hangul.
- `shangha3` (Shanghai III, `27c4000.ic44`): about 90 Korean message syllables drawn as 16x16x4 tiles, whole messages,
  not a font.
- `quizchqk` (Quiz Channel Question, Korean): the Dynax blitter data is packed; no raw 1 bpp font at 12-24 px.
- `spc800` (`spc800han.rom`: Hangul BASIC code), `spc1000`, `fc100`, `cpc61`, `cpg120` (8x8 / 8x12 character ROMs, a few
  Hangul pictograph cells on the SPC-1000): no Hangul font.

<a id="os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set"></a>

## 8. OS/2 Korean fonts (완성형) to a precomposed face and a jamo set

OS/2's Korean "System DBCS" fonts (`$korZN16.FNT`, `$korZN24.FNT`) are precomposed (완성형): the whole KS X 1001 table
(1,128 symbols, the 2,350 syllables, 4,888 Hanja) in code order, every glyph compressed (a Huffman code of nibbles, then
a prediction from the two rows above through a context table). `tools/os2dbcs.py` decodes them into the 94 x 94 table;
from there the route is the one of any KS X 1001 dump: a BDF, `bdfface.py`, and a jamo set fitted to the face.

    python3 -I tools/os2dbcs.py info '$korZN16.FNT'
    python3 -I tools/os2dbcs.py table '$korZN16.FNT' -o $OUT/zn16.bin
    python3 -I tools/rawcarve.py bdf $OUT/zn16.bin --glyph 16x16 --chars ks-hangul --grid 0xA1,0xA1,94 -o $OUT/zn16.bdf
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/8x16.pcf.gz $OUT/8x16.bdf   # Misc Fixed 8x16, Debian xfonts-base
    python3 tools/bdfface.py --hangul $OUT/zn16.bdf --ascii $OUT/8x16.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/OS2ZN16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/OS2ZN16.SVF --mask-font none --check -o $OUT/OS2ZN16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/OS2ZN16.SVF --mask-font none --check -o $OUT/OS2ZN16JA.SVF

Run on OS/2 Warp 4 Korean (IBM; the CD's FTCOMP bundles unpacked by the johab-fonts research, `D28REQ.004` = `$korZN16.FNT`,
220,160 bytes, and `D28REQ.002` = `$korZN24.FNT`, 346,624 bytes; proprietary). `info`: "System DBCS 16", 16x16, 32 bytes a
glyph, lead bytes A1-AC, B0-C8, CA-FD, 8,224 glyph records, all 2,350 syllables present; `table` writes 8,742 slots
(279,744 bytes; the same bytes as the research decoder's dump). The English half is the X11 "Misc Fixed" 8x16 and 12x24
of this host (`xfonts-base`, public domain); OS/2's DBCS files carry no ASCII. For the 24 px face the same commands with
`--glyph 24x24 --ascent 22`, `12x24.pcf.gz` and `--cell 24x24`:

| Face | Bytes | Glyphs | Fit | measure | Ink |
|---|---|---:|---|---|---:|
| `OS2ZN16.SVF`, precomposed 16 px | `123,328` | 2,447 | | `width=144 ascent=14 descent=2` | 469 |
| 8x4x4 jamo set of it | `17,264` | 441 | IoU 0.984 (p5 0.898), 1,753 of 2,350 exact, 0.3 s | the same | 470 |
| adaptive jamo set | `42,140` | 858 | 14/12/9 sets, IoU 0.999, 2,299 exact, 3 s | the same | 469 |
| `OS2ZN24.SVF`, precomposed 24 px | `220,164` | 2,447 | | `width=216 ascent=22 descent=2` (rule `line 400 32 0 24`) | 922 |
| 8x4x4 jamo set of it | `30,544` | 441 | IoU 0.720 (p5 0.457), 17 exact, 0.8 s | the same | 909 |
| adaptive jamo set | `100,740` | 1,533 | 32/24/12 sets, IoU 0.883, 548 exact, 11 s | the same | 921 |

`--check` composes all 11,172 syllables in every jamo set. The 16 px design is close to an OR of pieces (8x4x4 already
fits 0.984); the 24 px one is drawn syllable by syllable and fits poorly even with the default adaptive budget (32/24/12 sets): keep the
precomposed face where it fits the budget, or see [Choosing the number of sets](#choosing-the-number-of-sets).
`--chars ks-nonhanja` on the `rawcarve.py bdf` line keeps the symbols and the compatibility jamo as well (3,334 glyphs);
`bdfface.py` keeps only the syllables, `mkfont.py` reads the BDF at its own size: `mkfont.py $OUT/zn16-nh.bdf ... --size 16
--bpp 1 --unicode ksx1001-hangul,jamo` writes `123,880 bytes`, 2,444 glyphs, five syllables of the sample line `width=80`,
ink 310. `--unicode ksx1001-nohanja` stops there with Pillow's `raqm_get_glyphs() failed`: KS X 1001 A1A9 is U+00AD, the
soft hyphen, which the shaper drops; leave it out of the list (`--chars-from`). The `$SYS1Z16/24.FNT` files of the same CD are not syllables
(an IBM user area of pieces) and are not read.

<a id="a-low-resolution-face-from-a-high-resolution-bitmap-font"></a>

## 9. A low-resolution face from a high-resolution bitmap font

A 24, 40 or 48 px bitmap font (a DOS or printer font, a BDF, a ROM) is wanted at 16 px, or as a 2 bpp face. What the
tools do today: `mkfont.py` opens a BDF or PCF only at its own size (`OSError: invalid pixel size` at any other,
[ISO 10646 BDF and PCF](#iso-10646-bdf-and-pcf)); `jamoset.py --from-svf` keeps the source's cell; the C renderer and
`svfline.py` scale a face at draw time (`scale_num / scale_den`, a box filter into 8-bit coverage), and `tools/svfscale.py` writes a
smaller face: it draws selected glyphs of a 1 bpp face (a jamo set's syllables composed) or a BDF,
box-filters it to the new cell (each output pixel is the exact inked share of its source footprint) and writes a
precomposed face, 1 bpp by a threshold or 2 bpp in four levels:

    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 -o $OUT/ZN24TO16.SVF --compare $OUT/OS2ZN16.SVF   # 1 bpp, share >= 0.5
    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 --bpp 2 -o $OUT/ZN24TO16A.SVF                     # 2 bpp
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/ZN24TO16.SVF --mask-font none --check -o $OUT/ZN24TO16J.SVF

The other two sources go the same way: `bdfface.py --hangul dotum24.bdf --ascii $OUT/12x24.bdf --cell 24x24 ...` (and
`dotum16.bdf` with `8x16.bdf` for the face to compare), and `jamoset.py --layout 844 GHANC40.PFT --eng GASCII40.PFT
--symbols --check -o $OUT/GHANC40J.SVF` (and `GOTHIC16.FNT --eng ROMAN16.FNT` for the comparison), each then through `svfscale.py --size 16`.

The 2 bpp result is exactly what the renderer draws when it scales the 24 px face by 2/3 and the coverage is quantised
to four levels (checked on all 2,350 syllables of the OS/2 face below: every one equal), in this comparison, a stored 2 bpp face and
quantised draw-time scaling give the same pixels; the stored face costs memory, the scaled draw costs time. A jamo set can be
fitted only to the 1 bpp result: `jamoset.py --bpp 2` takes outline fonts only (`--bpp 2 works from an outline font
(--from-ttf)`), so there is no 2 bpp jamo set from a bitmap source.

Run here (2026-11-22) on three sources, each against a 16 px face of the same family or maker drawn by hand. "Overlap"
is what `--compare` prints: the mean IoU of the 2,350 syllables of the 1 bpp result against that face, at the best
common shift within 2 pixels, both faces on one baseline (how far a resampled face is from a drawn one, not a quality
score):

| Source | 1 bpp result | Ink | 2 bpp result | Ink | 8x4x4 fit of the 1 bpp result | Overlap with the drawn 16 px face |
|---|---|---:|---|---:|---|---|
| Baekmuk Dotum 24 (`dotum24.bdf` of Baekmuk BDF 2.2 + Misc Fixed 12x24, through `bdfface.py`, `216,196 bytes`) | `122,016 bytes`, 2,447 glyphs, `width=144 ascent=15 descent=1` | 330 | `194,208 bytes` | 612 | `18,292 bytes`, IoU 0.597 | 0.520 against `dotum16.bdf` (`122,804 bytes`, ink 411) |
| OS/2 `$korZN24.FNT` ([OS/2 Korean fonts](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set), `220,164 bytes`) | `125,084 bytes`, 2,447 glyphs, `width=144 ascent=15 descent=1` | 410 | `200,760 bytes` | 691 | `18,596 bytes`, IoU 0.710 | 0.387 against `$korZN16.FNT` |
| Taebaek 3.5.1 Gothic 40 (`GHANC40.PFT` with `--eng GASCII40.PFT`, the 8x4x4 face of [Other DOS-era Korean fonts](#other-dos-era-korean-fonts), `42,716 bytes`) | `124,940 bytes`, 2,447 glyphs, `width=144 ascent=14 descent=2` | 476 | `197,288 bytes` | 764 | `17,088 bytes`, IoU 0.990 | 0.471 against GOTHIC16.FNT |

The 40 px source is itself an OR of 8x4x4 pieces, so its 16 px resample still nearly is (IoU 0.990); the two whole-
syllable designs fit 8x4x4 poorly. The threshold trades strokes for blobs: the OS/2 face at `--threshold 0.25` has ink
615 (`0.5`: 410) and overlaps the drawn 16 px face 0.489. With `svfscale.py dotum24.bdf`, `--chars face` selects every glyph in the BDF (8,226 including Hanja in this example);
the default `--chars ks` selects KS syllables, ASCII and available non-syllable characters. The BDF supplies its ascent; go through `bdfface.py` first for a face with ASCII and
the cell you want.

**Pitfalls.** A 1-pixel stroke at 24 px covers two thirds of a 16 px pixel and survives a 0.5 threshold only where it
lines up; at 40 or 48 px thin strokes become 0.4-share pixels and vanish at 1 bpp. Resampling does not redraw: a drawn
16 px face (the last column above) is crisper, and a 2 bpp face from an outline font
([2 bpp anti-aliased faces](#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font)) has real coverage, not the
coverage of a bitmap's staircase.

<a id="classic-mac-korean-bitmap-fonts"></a>

## 10. Classic Mac Korean bitmap fonts

Supply your own source files. The maker's local mode ([maker desktop guide](maker-desktop.md)) reads these fonts in place from your disk, through the same tools, and writes the faces only into a folder you
choose [Apple font tables and resource forks](#ref-apple).

**HangulTalk 1.0 'fbit' fonts** (Korean System 4.1: Gotic12/16, Munjo12/16/24). Input: the font's resource fork as a
file (copied out of a Mac volume, or the fork of an archive; `tools/macsfnt.py list` shows its 'fbit' resource). The
fork holds an 'fbit' resource of 45 glyph sets and the 'fdef' driver resource with its 18 lookup tables. The set system is
derived from the font's own rule, so every syllable composes as the Mac draws it:

    python3 tools/jamoset.py --layout mac-fbit-45sets Munjo24.rsrc --symbols --check -o $OUT/MUNJO24J.SVF

Output: a 1 bpp jamo set of all 11,172 syllables (8 lead classes, 4 tail classes, 20 initial sets for these fonts),
cell = the font's size. `--check` composes everything and compares with jamoset's own copy of the 'fdef' rule; a golden
file (`tools/testdata/mac-fbit-golden.json`, not shipped: it would hold Apple bitmaps) adds an independent comparison
when you make one. Tests on the real files run when `JOHAB_FONTS` names a tree holding
`mac/extracted/kh10_system_disk/System Folder/*.rsrc` and the reference renderer; they skip otherwise.

Run on the System Disk of Korean System 4.1 / HangulTalk 1.0 (Jan 1988, Apple Korea / Elex Computer; proprietary), whose
`System Folder` holds the four fonts as resource-fork files. `Munjo24` (24 px Myeongjo; `list` shows `fbit` 17409, 47,714
bytes, and its `fdef` 3, 2,398 bytes): `36,660 bytes`, 653 pieces of 24x24, 8 lead x 4 tail classes, 20/15/4 sets, `check:
composed 11172 syllables from 655 glyphs`, and the self-consistency line `IoU 1.000, exact 11172` against jamoset's copy of the
`fdef` rule (no golden file), 1.0 s; `width=120 ascent=24 descent=0` for the sample line (these fonts hold no Latin: only the five
syllables are drawn), ink 591. `Gotic12` (12 px Gothic): `23,368 bytes`, the same sets, `width=60 ascent=12 descent=0`. The
maker's local mode (`detect.scan(..., local=True)`, on copies of the four fonts) reads them as "HangulTalk 1.0 fbit (45
sets), 24 x 24" (Munjo24; Munjo12, Gotic12 12 x 12, Munjo16 16 x 16), source kind `mac-fbit1`, coverage 2,350 KS / 11,172
syllables and 51 compatibility jamo, and offers the `mac fbit 1.0` route, which runs the command above; upload mode
says "Mac bitmap font (NFNT/fbit): not converted here (local-only mode)".

**HangulTalk 7.1.x type-3 'fbit' fonts** (Seoul12, AppleGothic12/24, AppleMyungjo12/24): the planes are composed by a
table, InputBackSupport 'HTBL' 1, and only the 2,350 KS X 1001 syllables and 51 compatibility jamo exist.

    python3 maker/srcprep.py mac-htbl "InputBackSupport[INIT].rsrc" $OUT/HTBL1.bin     # the HTBL 1 of the extension (7.1.2 CD), 9,816 bytes
    python3 tools/macfbit3.py unpack Seoul12.splt.data $OUT/Seoul12.rsrc     # the 7.1.2 Installer's 'splt' "JM" archive
    python3 tools/macfbit3.py fbit $OUT/Seoul12.rsrc $OUT/Seoul12.fbit
    python3 tools/macfbit3.py bdf $OUT/Seoul12.fbit $OUT/HTBL1.bin Seoul12 $OUT/seoul12.bdf          # 2,401 glyphs, Unicode BDF
    python3 tools/macfbit_svf.py build $OUT/Seoul12.fbit $OUT/HTBL1.bin -o $OUT/SEOUL12J.SVF         # direct: the Mac structure (JMAP)
    python3 tools/macfbit_svf.py build $OUT/Seoul12.fbit $OUT/HTBL1.bin --mode derived -o $OUT/SEOUL12D.SVF   # a JSET face, all 11,172
    python3 tools/macfbit_svf.py verify $OUT/SEOUL12J.SVF $OUT/Seoul12.fbit $OUT/HTBL1.bin

`direct` keeps the Mac planes as pieces and composes only the KS syllables exactly; `derived` fits a JSET whose 8,822
extra syllables are extrapolated (not Mac output). For a precomposed face with Latin, pass that BDF as `bdfface.py --hangul`, supply a separate `--ascii` font,
and set `--cell 12x12 --chars-from $OUT/ks.txt`. The `mkfont.py` route below needs no Latin companion. To shrink a many-variant face for an MCU budget:

    python3 tools/jamomerge.py merge --face $OUT/SEOUL12D.SVF --points 8192 7168 --prefix SM -o $OUT/SMALL

(keeps every piece as drawn and merges variants, sets and classes by a pixel objective). Tests: `tools/test_macfbit3.py`
and `tools/test_macfbit_svf.py` run on synthetic fbit / HTBL / NFNT data built in the tests; `MACFBIT3_CD712=<CD tree>`
and `SVF_MAC71_INPUTS=<dir of Name.fbit and Name.htbl1>` add the checks on your files. Outline Mac TrueType fonts: see
[Mac-format TrueType](#mac-format-truetype). The maker's routes for these fonts are in the
[route table](#desktop-app-and-maker-routes).

Run on Seoul12 of Korean System 7.1.2 / HangulTalk 7.1.2 (Apple Korea / Elex Computer; proprietary): `Seoul12[splt]` from the
CD's `More Additions` folder (the HangulTalk 7.5.1 installer's `Seoul12[fbit]` fork gives the same 8,760-byte `fbit`, `cmp`
identical) and the HTBL 1 of that CD's `InputBackSupport` extension. The HTBL is one more step the commands above did not
show, now the first line of the block above (`srcprep.py mac-htbl`, 9,816 bytes); the 7.5.1 copy of the extension is compressed
and `srcprep.py` answers "not an HTBL 1 table". With that `$OUT/HTBL1.bin` the chapter's commands run as written: `unpack` `JM 1843 -> 9673 bytes`, `fbit` 8,760 bytes, `bdf` 2,401
glyphs; `direct` `15,016 bytes`, 207 pieces, `verify` ks_bad 0, compat_bad 0, non_ks_present 0; `derived` `9,716 bytes`, 219 pieces,
8 x 4 classes, 9/6/3 sets (`7,928 bytes` as JSET v2), with the KS syllables and compatibility jamo verified; both draw the five syllables of the sample line as
`width=60 ascent=10 descent=2`, ink 142. The BDF route (`macfbit3.py bdf`, then `srcprep.py bdf-pixel-size seoul12.bdf
seoul12-sized.bdf --size 12`, then `mkfont.py ... --size 12 --bpp 1 --unicode ascii,ksx1001-hangul` and the canonical step) gives
`103,012 bytes`, 2,350 glyphs, the same `width=60 ascent=10 descent=2` and ink 142. With the family suitcase for the Latin letters
(`--latin "Seoul[FFIL].rsrc"`: a `FOND` and two `NFNT` strikes, 9 and 12 pt, from the same CD) `direct` is `17,924 bytes` (1,388 of
Latin) and `derived` `12,624 bytes`, both `width=111 ascent=10 descent=2`, ink 253, `verify` clean. `jamomerge.py merge --points 8192
7168` (about 2 minutes) writes `SM8K.SVF` `7,964 bytes` and `SM7K.SVF` `7,032 bytes` (191 pieces, 7/6/3 sets), verified. The maker's
local mode reads the files (`detect.scan(..., local=True)`): the `Seoul12` fork, the `splt` file and a raw fork are "HangulTalk 7.1
type-3 fbit, 12 px, 482 planes (needs HTBL 1)" with the routes `mac fbit 7.1 direct`, `derived` and `bdf + mkfont`; the extension
is "HangulTalk 7.1 HTBL 1 (InputBackSupport): the composition table"; `Seoul[FFIL]` is "Mac bitmap suitcase (FOND + NFNT): Latin
strikes at 9, 12 pt".

<a id="an-existing-svf"></a>

## 11. An existing SVF

Source: `svf/dos/NEODG16.SVF` (a precomposed 1 bpp face, 16x16, 2,905 glyphs, with a metrics table).

Set a dy (glyph pixels and other metrics are preserved; the file is repacked):

    python3 tools/svfdy.py svf/dos/NEODG16.SVF $OUT/neodg16-dy.svf --range 0x20-0x7e --dy 3

Verified: `133,720 bytes` (unchanged), 2,905 glyphs, dy set on 95 glyphs, range 0..3; renders `width=144 ascent=12 descent=7`
(the descent grew by the dy), ink 559.

Re-bake as a jamo set (a fit to the precomposed syllables of a 1 bpp face; the pieces and the face's other glyphs are kept):

    python3 tools/jamoset.py --layout 844 --from-svf svf/dos/NEODG16.SVF --mask-font none -o $OUT/neodg16-from-svf.svf

Verified: `34,332 bytes`, 892 glyphs, 344 pieces; fit: 2,357 syllables, IoU 1.000 (Neo Dunggeunmo is itself an OR of
pieces); renders `width=144 ascent=12 descent=4`, ink 559. An existing SVF is not a source for anti-aliasing at its own size: no tool converts a 1 bpp face
to 2 bpp of the same size (`svfscale.py --bpp 2` resamples it to a smaller one), and `svfdy.py` changes only the dy.

**Version and profile.** SVFN v2 is retired; `svf2to3.py` reads v2 and re-lays a v3 face out. The maker's "copy" route
does this for an uploaded SVF (`svf2to3.py SRC OUT --jset-version V --check`: a v2 face packed as v3, or a v3 face whose JSET
block is rewritten). A jamo set holds its tables as JSET v1 (the default) or v2 (smaller for a memory-limited target;
`--jset-version auto` picks v2 when the v1 block is at least 1,024 bytes larger); a JMAP block (JSET version 3) is copied
verbatim and the flag does nothing there.

    python3 tools/svf2to3.py $OUT/NG16J.SVF $OUT/NG16J-v2.SVF --jset-version 2 --check
    python3 tools/svf2to3.py svf/dos/NEODG16A.SVF $OUT/NEODG16A-v2.SVF --jset-version 2 --check
    python3 tools/svf2to3.py svf/dos/NEODG16.SVF $OUT/NEODG16-canon.SVF --profile default --check

Verified: NanumGothic Bold's 1 bpp jamo set `20,064` -> `19,232 bytes` with `--jset-version 2` (JSET block 1,101 -> 272 bytes, glyph data 11,884 unchanged, every glyph compared equal); the shipped NEODG16A `16,408` -> `15,576 bytes`; with `--jset-version auto` NEODG16A stays v1 (`jset=1`, the v1 block is only 829 bytes larger than v2, under the 1,024 threshold). The last command re-lays out a shipped face with the `default` profile and the bytes are identical:
133,720 bytes in and out (`cmp` reports no difference). `--profile` picks the layout for a target (`mcu-strict`, `default`, `dos`, `wasm`, `full`, `simd16`); `--check` proves the
pixels did not change.

<a id="an-svf-face-back-to-a-ttf-bitmap-font"></a>

## 12. An SVF face back to a TTF bitmap font

The other way: `tools/svf2ttf.py` turns an SVF face, precomposed or a jamo set, back into a TrueType font an OS or an
application can install, and into a BDF. The face is read as the C library loads it (`svfline.Face`), so a jamo set gives
every syllable its table composes (all 11,172 for a full table, composed by `jamoset.compose` as `svfline.py` draws them)
and the compatibility jamo it maps, besides its other glyphs; the default output is a precomposed font either way. Every glyph
stands where `svfline.py` draws it: the cell's left column at the pen, its top row `ascent - dy` rows above the baseline,
a combining mark at its origin with advance 0, the advance the face's own [OpenType glyphs, shaping and bitmap strikes](#ref-opentype).

    python3 tools/svf2ttf.py ttf svf/dos/NEODG16.SVF $OUT/NEODG16.ttf
    python3 tools/svf2ttf.py ttf svf/dos/NEODG16A.SVF $OUT/NEODG16A.ttf --family "My Pixel" --style Regular --version 1.001
    python3 tools/svf2ttf.py bdf svf/dos/NEODG16A.SVF $OUT/NEODG16A.bdf

**What the TTF holds.**

- **Outlines** (`glyf`): the pixels of each glyph traced along their edges into contours (holes kept, diagonal neighbours
  kept apart, no hinting; the only bytecode is a `prep` of one no-op, `PUSHB 0, POP`: FreeType hands a TrueType with no
  bytecode at all to its autohinter, which moved NEODG16's outlines by up to a full pixel at 1.5 x (591 pixels of the
  sample line at 24 px), and with the prep it draws the exact area coverage, within 1 level of `svfline.py`'s 3/2
  scale), with `unitsPerEm` = ppem x 64, so one pixel is 64 units and the outline covers exactly the
  face's pixels at ppem and at whole multiples of it; the font is scalable and installable. ppem defaults to the cell
  height (`--ppem N` for another, e.g. 17 for a face baked at 17 px in a 24-row cell); the line is the cell (ascent +
  descent = the cell height).
- **An embedded bitmap strike** (`EBLC`/`EBDT`, image format 1, index format 1) at ppem with the face's own bit depth:
  1 bpp faces a 1-bit strike, 2 bpp faces a 2-bit strike (the four levels as they are), 8 bpp an 8-bit one. Renderers
  that use embedded bitmaps (FreeType, Windows) draw the face's own pixels and levels at ppem and the outlines at every
  other size. `--no-strike` writes the outlines only; `--apple` adds the same strike as `bloc`/`bdat`.
- **2 bpp faces.** An outline has no levels, so the outline of a 2 bpp face takes the pixels of coverage >= 128 (levels 2
  and 3, the C library's mono-target rule; `--threshold C` sets another): at ppem the strike gives the levels, at other
  sizes the outline is that 1-bit cut.
- **Metrics**: `hmtx` advance = the face's advance x 64; `hhea` and OS/2 typo ascender / descender = the face's ascent and
  cell height - ascent (`USE_TYPO_METRICS`); OS/2 win ascent / descent also cover ink a dy moves past the cell; the
  strike's own small metrics carry each glyph's bearings and advance.
- **cmap** (format 4, and 12 past U+FFFF), `post` format 3 (no glyph names), `head`, `maxp`, `gasp`, OS/2 (weight 400,
  or 700 and the bold bits for a `--style` with "Bold"; code page bits Latin 1, Korean Wansung and, with all 11,172
  syllables, Johab), a `.notdef` box.
- **name**: family `--family` (default `<FACE STEM> SVF`, e.g. `NEODG16 SVF`: never the source font's own name, which an
  OFL Reserved Font Name may forbid for a modified version), style `--style` (default Regular), version `--version`
  (default 1.000), a description naming the face (`Generated by svf2ttf.py from NEODG16.SVF (16x16 cell, 1 bpp,
  precomposed, 2905 glyphs, 16 px strike)`), and the licence. A face of this repository's `svf/` gets the licence
  files its row of `web/LICENCES.tsv` names (the note and the OFL file, e.g. `NEODGM.TXT` and `OFL.TXT` for `NEODG*`;
  `PAPMARU.TXT` and `OFLPAPLG.TXT` for `PAPER*`, `OFLMARU.TXT` for `MARU*`; the OFL file alone for `BHSAN28`,
  `NSQR*`, ...), and a face under `svf/` that no row covers is an error unless `--licence` is given. A face elsewhere
  gets the `*.TXT` beside it whose title line names its file or a pattern matching it, with the licence files that note
  names (all of them: a note covering two fonts gives both, with a warning), else the licence column of a `FACES.TSV`
  beside it. The texts go into the licence description; the copyright paragraph of the OFL file (the paragraph above
  its `SIL OPEN FONT LICENSE` header that says "Copyright" or "(c)", else its first paragraph, as Neo Dunggeunmo Pro's
  public-domain attribution) into the copyright; the OFL URL only when an OFL text is embedded. `--licence FILE` names
  the note; `--licence none` writes none. A face outside the repository with no note (one you made in `$OUT`) gets a
  line saying the source font's licence applies, and a warning: give it `--licence`.
- **Code points**: a jamo set's pieces (the plane U+F0000..U+FFFFF) are not exported; a precomposed face keeps its
  private-use glyphs there and past it. Surrogates and U+FFFF never become characters. A face with nothing to export,
  or a TTF requiring more than 65,535 total glyphs (including `.notdef` and shared component glyphs), is an error.
- **Not produced**: conjoining-jamo (U+1100) shaping, GSUB or GPOS, kerning, hinting instructions, vertical metrics. The timestamps are `$SOURCE_DATE_EPOCH` when set, else now.

**The BDF** (`bdf`): every code point a glyph (BBX the ink box, DWIDTH the advance), `FONT_ASCENT` / `FONT_DESCENT` the
face's, `PIXEL_SIZE` ppem at 72 dpi (`SIZE ppem 72 72`, `POINT_SIZE` ppem x 10, `SWIDTH` advance x 1000 / ppem),
`AVERAGE_WIDTH` the mean advance x 10, the licence note as `COMMENT` lines and the copyright as `COPYRIGHT`, written in
UTF-8 (a note's Korean text is kept as it is; FreeType reads it). A 1 bpp face writes BDF
2.1; a 2 or 8 bpp face writes BDF 2.3 with its bit depth as the fourth field of `SIZE` (FreeType reads it), or 1 bpp with
`--bpp1` (pixels >= `--threshold`).

**Round trip.** Bake the TTF back with `mkfont.py` at the strike size and the face's bit depth, and compare:

    python3 tools/mkfont.py $OUT/NEODG16A.ttf $OUT/back.svf --size 16 --bpp 1 --probe --width 16 --only-listed \
        --unicode $(python3 tools/svf2ttf.py cps svf/dos/NEODG16A.SVF)
    python3 tools/svf2ttf.py compare svf/dos/NEODG16A.SVF $OUT/back.svf

`cps` prints the face's code points as `--unicode` ranges (`20-7e,25a1,3131-3163,ac00-d7a3` for NEODG16A), and
`--only-listed` bakes those and no more; `--probe` takes a cell tall enough to cut nothing and keeps one baseline;
`--width` is the face's cell width. `compare` places every glyph of both faces as
`svfline.py` does and counts glyphs whose pixels (as coverage) or advance differ, and inked glyphs only one face has;
blank glyphs only one face has are counted apart, as `mkfont.py` drops every blank glyph but the spaces (U+0020,
U+00A0 and U+3000 only one face has are mismatches: `mkfont.py` keeps them). Exit 0 when the mismatches are 0; an
unreadable face exits 1.

Verified (2026-11-23), every face through `ttf` and `bdf`, each output baked back by `mkfont.py` as above (`--bpp 2`
for the 2 bpp faces) and compared; rendered by Pillow (FreeType) at ppem and at 2 x ppem, the line `가각간한글 ABC 123`
compared with `svfline.py` (at 2 x, with the 2 bpp line cut at 128, in 2 x 2 blocks); OTS 9.2.0 (`ots-sanitize`)
passes every TTF; `fc-scan` reads every TTF (scalable, outline, its family and style):

| Face | Kind | Glyphs | SVF | TTF | BDF | TTF / BDF round trip | Render 1 x / 2 x |
|---|---|---|---|---|---|---|---|
| `svf/dos/NEODG16.SVF` | precomposed 1 bpp 16x16 | 2,905 | `133,720` | `481,800` | `440,766` | 0 / 0 mismatches of 2,905 | identical / identical |
| `svf/dos/NEODG16A.SVF` | jamo set 1 bpp 16x16 | 11,319 | `16,408` | `2,038,968` | `1,745,233` | 0 / 0 of 11,318 (1 blank: U+3161) | identical / identical |
| `svf/jamo-extra/GOTHA16A.SVF` | jamo set 2 bpp 16x16 | 11,319 | `73,752` | `2,418,300` | `2,519,856` | 0 / 0 of 11,319 | identical levels / identical |
| `svf/dos/NGOTB16.SVF` | precomposed 2 bpp 16x16 | 2,880 | `219,480` | `563,900` | `621,422` | 0 / 0 of 2,880 | identical levels / identical |
| `svf/jamo-extra/GOTHB24.SVF` | jamo set 1 bpp 24x24 | 11,319 | `96,180` | `2,796,288` | `2,757,257` | 0 / 0 of 11,319 | identical / identical |
| HWP 1.x `HANGUL1.PFT` face 1 + `ASCII.PFT` (`jamoset.py --layout hwp1`, [HWP 1.x](#hwp-1x-and-2x-fonts)) | jamo set 1 bpp 24x24 | 11,318 | `16,712` | `2,849,128` | `2,726,291` | 0 / 0 of 11,318 | identical / identical |

An 8 bpp face (`mkfont.py --bpp 8` of `ttf/nanumgothic/NanumGothic-Bold.ttf` at 16 px, `ascii,ksx1001-hangul`, 2,446
glyphs, `579,152 bytes`) gets an 8-bit strike: TTF `876,820`, BDF `1,307,960 bytes`, both round trips (`--bpp 8`) 0
mismatches. The HWP 1.x face (HWP 1.20, proprietary) has no licence note beside it, so its TTF says the source font's
licence applies and stays in `$OUT`, as the face does.

`ttf` takes 2.5-4.8 s for a jamo set of 11,172 syllables and under 1 s for a precomposed face of 2,905 glyphs. Most of
a TTF is the outlines (`glyf`: 1,561,590 of NEODG16A's 2,038,968 bytes; the strike 348,244 + 45,352), so a TTF is 2.5-3.6
times the precomposed face and 29-170 times a jamo set. NEODG16A draws U+3161 (ㅡ) blank (its compatibility piece is empty), so `mkfont.py`
drops it and `compare` counts it as the one blank glyph.

**Installing.** See [fontconfig](#ref-fontconfig). Linux: copy the `.ttf` to `~/.local/share/fonts/` and run `fc-cache`; checked with a private fontconfig
configuration (a `<dir>` and `<cachedir>` under `$OUT`, `FONTCONFIG_FILE` pointing at it): `fc-list` lists `NEODG16A SVF`
and `GOTHA16A SVF`, and `fc-match "NEODG16A SVF:pixelsize=16"` picks the file. fontconfig lists the language `ko` only
for a face that has every character of its Korean orthography, compatibility jamo U+3165-U+318E included (NGOTB16 does;
NEODG16 and the jamo sets do not), which matters only to font fallback by language. Windows and macOS: not tested here
(install as any `.ttf`; whether a program draws the strike or the outline at ppem is up to its renderer; Windows
reads `EBLC`/`EBDT` strikes, but whether it draws a 2 or 8 bit strike as levels is untested; `--apple` adds the Apple
names of the same tables, `bloc`/`bdat`, untested on a Mac).

**Limits.** The strike holds the face's size only; at other sizes the outlines draw blocky pixels (exact at whole
multiples), anti-aliased by the renderer at the rest. A 2 bpp face's levels exist only in its strike. The output is
precomposed: a jamo set's small size does not survive the conversion (`--composite`, below, keeps its pieces shared:
a quarter to under half of the plain TTF). The strike's metrics are bytes: the advance
0..255 (every SVF advance fits) and the ascent, descent, each glyph's bearing x and ink top and the strike's extremes (least left and right side
bearing, highest and lowest ink; a glyph's own right side bearing is not stored, so a 200-wide cell with wide and
narrow glyphs fits, and a least right side bearing past 127, such as a 200-wide cell whose only glyph is a '.', is stored
as 127, still a lower bound: the only extreme that can pass 127 when every glyph's bearing x and ink top fit) signed, -128..127, so a face whose
ascent or ink reaches more than 127 rows from the baseline (a cell over about 127 rows) stops with an error naming the
field; `--no-strike` converts it to outlines only, and its BDF is not limited. The licence of the face's source font applies to the TTF; an
OFL font's Reserved Font Names must not be the new family name (the default name avoids them).

<a id="composite-glyphs---composite"></a>

### 12.1. Composite glyphs (`--composite`)

`ttf --composite` keeps a jamo set's structure in the TTF: each jamo piece is written once as a glyph (its outline and
its strike bitmap, placed as a composed syllable places it), every composed syllable is a composite of its pieces, and
each compatibility jamo maps (cmap) to its piece glyph itself. The other glyphs (ASCII and the rest) stay plain. A
precomposed face has nothing to share: `--composite` then writes the plain TTF and prints a note.

    python3 tools/svf2ttf.py ttf svf/dos/NEODG16A.SVF $OUT/NEODG16A-c.ttf --composite

- **Outlines** (`glyf`): a composite glyph of the syllable's non-blank pieces, each at offset (0, 0) (a piece is a whole
  cell and carries no dy), with the syllable's own advance in `hmtx`. TrueType draws the union of the components, and
  the union of the pieces' outlines is the outline of the composed syllable's pixels at `--threshold` (taking the
  maximum of levels and then cutting at a threshold is the same as cutting each piece and joining them), so the
  outlines are exact for 1, 2 and 8 bpp. The first component has `OVERLAP_COMPOUND` (FreeType then rasterises the
  composite oversampled, so an edge pixel two pieces share is not covered twice at sizes between the multiples). The
  no-op `prep` every TTF carries (above) matters more here: without it FreeType's autohinter moves the overlapping
  contours of a composite by up to half a pixel, at 2 x ppem too (6,463 of NEODG16A's syllables at 32 px). `maxp`'s
  component fields are recalculated (`maxComponentElements` 3, `maxComponentDepth` 1).
- **Strike** (`EBDT`): a syllable is a compound bitmap, image format 8 (small metrics, a pad byte, then each piece's
  glyph id with its x / y offset from the compound's top-left), in its own index subtable after the format 1 glyphs.
  Format 9 (big metrics) would add 3 bytes a syllable for vertical metrics the font does not have. FreeType reads
  compound bitmaps (`ttsbit.c`): it ORs each component's rows into the compound's bitmap. For 1 bpp that is the SVF
  rule. For 2 and 8 bpp two things differ: FreeType shifts a component by its x offset in bits, not pixels, so every
  piece bitmap of a 2 or 8 bpp face starts at the pen (its x offset is then 0), and the OR of two levels is not their
  maximum (2 bpp: 1 | 2 = 3 where the face draws 2). A syllable whose pieces overlap at a pixel with levels a and b where
  a | b != max(a, b) keeps an expanded format 1 bitmap (its outline stays a composite); the summary line counts them
  (`strike: 6091 compound, 5081 expanded bitmaps` for GOTHA16A). Built with no expanded bitmaps, GOTHA16A draws
  exactly those 5,081 syllables wrong in FreeType (9,487 pixels at level 3 instead of 2), and NSQRB36A its 5,831.
  A component offset is a signed byte, so in a cell over 128 px a syllable whose pieces lie more than 127 pixels apart
  also keeps an expanded bitmap, and a piece whose ink starts past x 127 has its own bitmap start at the pen (its
  bearing x would not fit a byte): `--composite` converts every face the plain strike does.

Verified (2026-11-23), each face through `ttf` and `ttf --composite`, the composite TTF baked back by `mkfont.py` and
compared as above; every glyph rendered by Pillow at ppem and 2 x ppem and by freetype-py at ppem (the strike, and the
outline with `FT_LOAD_NO_BITMAP`) equal to the same glyph of the plain TTF; fontTools reads, decompiles every table and
recompiles; `fc-query` / `fc-scan` read it (scalable, outline); OTS (`ots-sanitize` 9.2.0) passes. OTS drops
`EBLC`/`EBDT` from what it passes (as for the plain TTF), so a browser that sanitises web fonts with OTS draws the outlines
only; the strike is checked by FreeType above. The HWP 1.x face has no licence note, so both its TTFs carry the line
saying its source font's licence applies, as in the table above:

| Face | Pieces | Plain TTF | Composite TTF | Strike: compound / expanded | Round trip | Renders, OTS |
|---|---|---|---|---|---|---|
| `svf/dos/NEODG16A.SVF` (1 bpp 16x16, 8/4/4 sets) | 344 | `2,038,968` | `694,384` (34 %) | 11,172 / 0 | 0 mismatches of 11,318 (1 blank: U+3161) | identical, pass |
| `svf/jamo-extra/GOTHA16A.SVF` (2 bpp 16x16, 24/16/16) | 1,224 | `2,418,300` | `1,037,104` (43 %) | 6,091 / 5,081 | 0 of 11,319 | identical levels, pass |
| `svf/jamo-extra/GOTHB24.SVF` (1 bpp 24x24, 24/16/16) | 1,224 | `2,796,288` | `844,780` (30 %) | 11,172 / 0 | 0 of 11,319 | identical, pass |
| `svf/dos/MARUS24.SVF` (1 bpp 24x24, 24/16/16) | 1,178 | `3,415,744` | `854,684` (25 %) | 11,172 / 0 | 0 of 11,335 | identical, pass |
| `svf/dos/NSQRB36A.SVF` (2 bpp 36x36, 24/16/16) | 1,070 | `5,901,072` | `2,432,800` (41 %) | 5,341 / 5,831 | 0 of 11,319 | identical levels, pass |
| HWP 1.x `HANGUL1.PFT` face 1 + `ASCII.PFT` (1 bpp 24x24, 7/2/2) | 229 | `2,849,128` | `684,916` (24 %) | 11,172 / 0 | 0 of 11,318 | identical, pass |

The floor is the per-syllable records: a composite of 3 pieces is about 30 bytes of `glyf`, 4 of `loca`, 4 of `hmtx`,
20 of `EBDT` and 4 of `EBLC` (NEODG16A: `glyf` 334,881, `EBDT` 227,283 bytes), so a composite TTF of 11,172 syllables
stays near 0.7 MB in this example even with small pieces; expanded 2 bpp bitmaps and large cells add to it. `--composite` builds
in 0.5-1.2 s at 16-24 px (4.0 s for NSQRB36A; the plain TTF 2.4-4.4 s and 8.7 s), faster than the plain TTF, as it traces each piece once.

**Limits of `--composite`.** Only FreeType (Pillow, fontconfig, freetype-py) was checked; whether Windows (GDI,
DirectWrite) or a Mac (`--apple`: `bdat` with the format 8 compounds) draws the compound bitmaps is not tested, and a
renderer that ignores them draws the outlines at ppem. Between the whole multiples of ppem, FreeType's oversampling of
an `OVERLAP_COMPOUND` glyph is not the exact area coverage the plain TTF gets: at 20 and 24 px every sampled syllable
(every 7th) of NEODG16A and GOTHA16A draws as in the plain TTF; at 17 px 303 of 1,596 (19 %, NEODG16A) and 454 of
1,596 (28 %, GOTHA16A) differ in edge pixels, by up to 32 and 42 of 255. 2 and 8 bpp
syllables with overlapping levels keep expanded bitmaps (above). The pieces carry no Unicode (no shaping of conjoining
jamo, as before).

<a id="choosing-the-number-of-sets-벌-수"></a>

## 13. Choosing the number of sets (벌 수)

<a id="choosing-the-number-of-sets"></a>

A jamo set draws a syllable from one initial, one medial and an optional final piece; the *sets* (벌) are the variants
of each jamo, and the set system picks one per syllable by the vowel, the final and the initial's class. More sets
follow the font more closely and cost bytes (every set holds a piece for every jamo it is used for) and table size.

**The set systems** (`jamoset.py --layout`; the JSET block allows up to 32 initial, 24 medial and 16 final sets and
12 x 12 lead / tail classes, `--jset-big` up to 128 / 128 / 64 and 19 x 28):

| Layout | Sets (initial / medial / final) | Where it comes from | From a fit (`--from-ttf`, `--from-svf`) |
|---|---|---|---|
| `621` | 6 / 2 / 1 | Apple II era 6x2x1 fonts | yes (NEODG16G of `svf/` is one) |
| `844`, `844-ihnm`, `844-hbios24` | 8 / 4 / 4 | the DOS standard (`HANGUL.FNT`); IHNM swaps the medial sets of ㄱ ㅋ; HBIOS is its 24x30 file | yes |
| `1044-san` | 10 / 4 / 4 | san 1.0 | yes |
| `hanterm-johab` | 10 / 4 / 4 (3 for some files) | hanterm's johab BDFs | yes |
| `dkb-printer-7x2x2`, `dkb-printer-12x4x4` | 7 / 2 / 2, 12 / 4 / 4 | Dokkaebi printer fonts | yes |
| `kyra-lok` | 10 / 4 / 4 | Kyrandia's MK15.BIT | yes |
| `hwp1` | face-dependent: 10/4/4, 7/2/2 or 6/2/2 (SFT); 7/2/3, 7/2/2 or 5/2/2 (PFT) | HWP 1.x Hangul files | source files only |
| `844-hwp3` | 8 / 4 / 4 | appended jamo set in HWP 3.0 16 px Hangul FNT | yes |
| `spec` | derived from the compose spec (SPC-1500: 6 / 2 / 2) | `rawcarve.py compose` spec | source files only |
| `mac-fbit-45sets` | derived from the font (Munjo24: 20 / 15 / 4, 8 x 4 classes) | HangulTalk 1.0 `fbit` | source files only |
| `adaptive[:NI,NM,NF]` | from 8 / 4 / 4 up to NI / NM / NF (default 32 / 24 / 12; NI 8-32, NM 4-24, NF 4-16), 12 x 12 classes | `jamoadapt.py`: splits a set where the syllables that share a piece disagree | yes |

**The options that change the counts.** `--layout adaptive:NI,NM,NF` caps the sets (it stops earlier when a split no
longer gains: at least 0.05 % of the starting cost, at least 4 syllables a side, fixed in `jamoadapt.py`); the class limits
are 12 × 12 for `jamoset.py --layout adaptive` (even with `--jset-big`, which only lets a source's own larger tables be written).
`jamovec.py master --adaptive NI,NM,NF` and `--class-limit N` do the same for a vector master (counts above the standard limits require `jamovec.py render --jset-big` and a renderer built with `SVF_JSET_BIG`;
counts beyond the BIG limits can only be simulated). After a fit, `jamomerge.py merge --points BYTES ...` merges variants, sets and classes
down to byte budgets ([Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) has a run), and
`jamoexc.py` stores a few frequent syllables whole (LIST exceptions) instead of adding sets.

**Measured** (2026-11-22): every layout fitted with `jamoset.py --layout L --from-svf FACE --mask-font none --check` to
two 16 px precomposed faces: NanumGothic Bold (`mkfont.py ... --size 16 --bpp 1`, an outline font's raster) and OS/2's
`$korZN16.FNT` ([OS/2 Korean fonts](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set), a hand-drawn bitmap
face). Bytes of the whole face (ASCII included), IoU over the 2,350 syllables (exact of 2,350), and the ink of the
sample line (the precomposed faces: 677 and 469):

| Layout | Sets used | NanumGothic Bold: bytes | IoU (exact) | Ink | OS/2 ZN16: bytes | IoU (exact) | Ink |
|---|---|---:|---|---:|---:|---|---:|
| `621` | 6 / 2 / 1 | 12,788 | 0.743 (25) | 673 | 11,544 | 0.889 (206) | 471 |
| `844` | 8 / 4 / 4 | 20,648 | 0.795 (126) | 681 | 17,264 | 0.984 (1,753) | 470 |
| `1044-san` | 10 / 4 / 4 | 22,504 | 0.799 (118) | 681 | 18,788 | 0.991 (1,823) | 470 |
| `hanterm-johab` | 10 / 4 / 4 | 21,992 | 0.798 (110) | 676 | 18,608 | 0.981 (1,501) | 468 |
| `adaptive:8,4,4` | 8 / 4 / 4 | 29,544 | 0.796 (135) | 680 | 25,972 | 0.992 (2,171) | 469 |
| `adaptive:12,8,6` | 12 / 8 / 6 | 39,176 | 0.857 (205) | 678 | 33,924 | 0.999 (2,273) | 469 |
| `adaptive:16,12,8` | 16 / 12 / 8 (ZN16: 14 / 12 / 8) | 48,156 | 0.875 (291) | 672 | 41,008 | 0.999 (2,299) | 469 |
| `adaptive:24,16,12` | 24 / 16 / 12 (ZN16: 14 / 12 / 9) | 65,412 | 0.905 (414) | 677 | 42,140 | 0.999 (2,299) | 469 |
| `adaptive` (32,24,12) | 32 / 24 / 12 (ZN16: 14 / 12 / 9) | 77,560 | 0.918 (576) | 669 | 42,140 | 0.999 (2,299) | 469 |

Each fit took 0.3-0.5 s (fixed layouts) or 2-7 s (adaptive). The precomposed faces are 125,520 and 123,328 bytes.

**Reading it.** The fixed layouts cost what their piece count costs (621: 279 / 280 glyphs on the two faces, 844: 440 / 441, the 10x4x4 layouts: 464-479),
and they gain little over each other. `adaptive:8,4,4` has the 844 counts but 12 x 12 classes: its tables cost 8.8 KB
more (a 9,921-byte JSET block against 1,101; 2,844 as JSET v2: `--jset-version 2` or `auto`, every adaptive
face above shrinks by 6-7 KB that way) for a better choice of which syllables share a piece (OS/2: 2,171 exact against
1,753). The hand-drawn bitmap face is already close to an OR of pieces and stops splitting at 14 / 12 / 9 with IoU
0.999; the outline raster keeps gaining up to the cap (0.918 at 32 / 24 / 12) and is never exact, because a scaled
outline draws every syllable a little differently.

**Recommendation.** Fit `844` first and read the IoU. Above about 0.98 (a bitmap face designed on pieces, a DOS font,
a ROM) keep `844`: more sets buy almost nothing. Between that and about 0.9, try `adaptive:12,8,6`, which gains most
of what more sets give at about twice the 844 size; a raster of an outline font, at 0.8 with 844, needs the full
`adaptive` budget to reach 0.9 and then costs over 60 % of the precomposed face: there the precomposed face, or a few
LIST exceptions (`jamoexc.py`) on an 844 set, is usually the better use of the bytes. For a target with a hard budget,
fit generously and let `jamomerge.py merge --points` cut down to it. Look at the result in every case
(`svfline.py line`, the `web/` picker): IoU does not show which syllables went wrong.

<a id="desktop-app-and-maker-routes"></a>

## 14. Desktop app and maker routes

For the UI workflow, see [Maker desktop](maker-desktop.md); for render previews, see [Desktop app](desktop-app.md).

The maker ([maker desktop](maker-desktop.md), [desktop app](desktop-app.md), [maker server](../maker/README.md))
detects each file's kind (`maker/detect.py`) and offers the routes of `maker/routes.py` for it; every route is a command
line made of the tools above. A run writes `svf/<dest>/<NAME>.SVF` and `build-<id>/BUILD.md` in the output folder:
BUILD.md lists, for every face, the source steps and the commands that were run, with the real paths, so any result can
be reproduced by hand from this chapter. The routes, by the labels the page shows (`native` = the source is exactly
what the route makes; the others are fits and are marked experimental):

| Route (kind, label) | Source kind | Commands (argv of `routes.py`) | Recipe |
|---|---|---|---|
| precomposed, `mkfont` | outline, outline-composite, bitmap, bdf-iso10646 | `mkfont.py SRC mkfont.tmp --size S --bpp B --unicode R`, then `svf2to3.py mkfont.tmp OUT --profile default` (bitmaps: 1 bpp at their strike sizes) | [Precomposed faces](#precomposed-faces-mkfontpy), [ISO 10646 BDF and PCF](#iso-10646-bdf-and-pcf) |
| jamo, `composite` | outline-composite (a TrueType whose syllables are composites) | `jamovec.py master SRC -o M.json --components [--adaptive]`, then `jamovec.py render M.json --size S --bpp B --binarize threshold --check -o OUT` | [Jamo sets from TrueType and OpenType fonts, way 1: composite glyphs](#jamo-sets-from-truetype-and-opentype-fonts) |
| jamo, `experimental fit` | outline (not composite) | 1 bpp: `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --check -o OUT [--eng E] --mask-font none`; 2 bpp: `jamoset.py ... --bpp 2 --check -o OUT` | [Jamo sets from TrueType and OpenType fonts, way 3: fitting to the precomposed syllables](#jamo-sets-from-truetype-and-opentype-fonts) |
| jamo, `mask fit` | outline or outline-composite with GSUB jamo and a usable mask (1 bpp) | `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --mask-font SRC --no-clean --check -o OUT [--pylib DIR]` | [Jamo sets from TrueType and OpenType fonts, way 2: conjoining-jamo shaping](#jamo-sets-from-truetype-and-opentype-fonts) |
| jamo, `vector fit` | outline, outline-composite | `jamovec.py master SRC -o M.json [--adaptive]` (no `--components`), then the same `render` | [Jamo sets from TrueType and OpenType fonts, way 3: fitting to the precomposed syllables](#jamo-sets-from-truetype-and-opentype-fonts) (`jamovec.py master` without `--components`) |
| precomposed, `johab844` | dos-raw, exactly 11,520 bytes (16 px 8x4x4) | `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng E]` (the maker resolves the base under `svf/`) | [Other DOS-era Korean fonts](#other-dos-era-korean-fonts) |
| jamo, `dos raw` | dos-raw | `jamoset.py SRC --layout L --check -o OUT [--eng E] [--face 0\|1]` (`--face` for the Dokkaebi printer layouts) | [Other DOS-era Korean fonts](#other-dos-era-korean-fonts) |
| jamo, `hanterm` | bdf-johab | `jamoset.py SRC --layout hanterm-johab --check -o OUT [--eng E]` | [hanterm](#hanterm) |
| precomposed, `bdfface` | bdf-ksc5601 (a BDF, or a PCF through the `pcf-bdf` step) | `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST -o OUT` (`WxH` = the BDF's box) | [KS C 5601 BDF and PCF](#ks-c-5601-bdf-and-pcf) |
| jamo, `bdfface + from-svf fit` | bdf-ksc5601 | the `bdfface.py` face, then `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS C 5601 BDF and PCF](#ks-c-5601-bdf-and-pcf) |
| jamo, `mac fbit 1.0` | mac-fbit1 | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| jamo, `hwp1` | hwp1 (an HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT` face; local mode) | `jamoset.py SRC --layout hwp1 --face N --check -o OUT [--eng E]` | [HWP 1.x and 2.x fonts](#hwp-1x-and-2x-fonts) |
| precomposed, `hwp bdf + mkfont` | hwp1, ks-raw (an HWP 3.0 Hangul FNT, local mode; a headerless KS X 1001 dump) | `hwpfont.py bdf SRC [--face N] [--syllables all] [--ascii E] -o hwp.bdf`, `mkfont.py hwp.bdf mkfont.tmp --size S --bpp 1 --unicode R`, `svf2to3.py mkfont.tmp OUT --profile default` (without `E` the range drops `ascii`) | [HWP 1.x and 2.x fonts](#hwp-1x-and-2x-fonts), [KS X 1001 raw dumps](#ks-x-1001-raw-dumps) |
| jamo, `hwp3 844` | ks-raw with an 8x4x4 set (an HWP 3.0 `HAN16_*.FNT`) | `jamoset.py SRC --layout 844-hwp3 --check -o OUT [--eng E]` | [HWP 3.0 FNT fonts](#hwp-30-fnt-fonts) |
| jamo, `hwp bdf + from-svf fit` | ks-raw | the `hwp bdf + mkfont` face as `precomposed.svf`, then `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS X 1001 raw dumps](#ks-x-1001-raw-dumps) |
| jamo, `mac fbit 7.1 direct` / `derived` | mac-fbit3 + HTBL 1 | `macfbit_svf.py build FBIT HTBL -o OUT --mode direct\|derived [--latin SUITCASE]` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| precomposed, `mac fbit 7.1 bdf + mkfont` | mac-fbit3 + HTBL 1 | `macfbit3.py bdf FBIT HTBL NAME mac.bdf`, `srcprep.py bdf-pixel-size mac.bdf mac-sized.bdf --size S`, `mkfont.py mac-sized.bdf mkfont.tmp --size S --bpp 1 --unicode ...`, `svf2to3.py ... --profile default` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| precomposed or jamo, `copy` | svf-precomposed, svf-jamo | none when used as uploaded; `svf2to3.py SRC OUT --jset-version V --check` for a v2 face or a requested JSET change | [An existing SVF](#an-existing-svf) |
| precomposed or jamo, `svf2ttf` | svf-precomposed, svf-jamo | the face as `copy` reads it, written only as its exports (below): no SVF | [An SVF face back to a TTF bitmap font](#an-svf-face-back-to-a-ttf-bitmap-font) |
| precomposed, `bdfface`; jamo, `bdfface + from-svf fit` | recipe (a known ROM set of `maker/recipes/`, local mode) | `rawcarve.py bdf` of the recipe's Hangul and English items, `bdfface.py --hangul H --ascii A --cell WxH --chars-from LIST -o OUT`; the fit makes that face as `precomposed.svf`, then `jamoset.py --layout L --from-svf precomposed.svf --mask-font none [--eng E] --check -o OUT`; before them `rawcarve.py region --group ...` of a set's files (each path whole: a comma in a folder name stays), and `rawcarve.py compose` for a composed item or `ink` + `eng` for an English font in tiles | [Korean VGA font ROMs (86Box)](#korean-vga-font-roms-86box), [Korean font ROMs in MAME sets](#korean-font-roms-in-mame-sets) |
| jamo, `spec` | recipe (SPC-1500) | `rawcarve.py region ...`, `rawcarve.py eng REGION ...`, `jamoset.py --layout spec --spec spc1500 REGION --eng E --check -o OUT` | [Samsung SPC-1500](#samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact) |
| jamo, `dos raw` | recipe (a raw set in a ROM: X Se Dae Quiz) | `rawcarve.py region`, `ink`, `cut` (the raw font), `ink` + `eng` (the English font), `jamoset.py RAW --layout L --eng E --check -o OUT` | [X Se Dae Quiz](#x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check) |
| jamo, `from-svf fit` | svf-precomposed, 1 bpp | `[svf2to3.py ... source-v3.svf]`, then `jamoset.py --layout L --from-svf SRC --check -o OUT [--eng E]` | [An existing SVF](#an-existing-svf) |

`L` is `844` or `adaptive` for the fits and the layout the source kind names otherwise; `[--eng E]` is the English
companion the page paired with the font.

With "also write TTF / BDF" (`options.export`) every face step is followed by one `export` step a format:
`svf2ttf.py ttf|bdf FACE OUT [--licence FILE]`, `OUT` the face's name with `.ttf` / `.bdf`, written beside the face;
`FILE` is the licence the job knows for the font (none: svf2ttf.py says the source font's licence applies); "TTF as
composites" adds `--composite` to a jamo set's TTF.

Some sources need a conversion first; BUILD.md lists these steps before the route's commands (each reads the file the
step before it wrote):

| Step | Command |
|---|---|
| `rsrc-sfnt` | `macsfnt.py extract SRC OUT --id N` |
| `mac-cmap` | `macsfnt.py unicode SRC OUT` |
| `ttc-face` | `srcprep.py ttc-face SRC OUT --index N` |
| `instance` | `python3 -m fontTools.varLib.instancer SRC AXIS=VALUE ... -o OUT` |
| `pcf-bdf` | `srcprep.py pcf-bdf SRC OUT` |
| `mac-fork`, `mac-fork-named` (macOS only), `mac-htbl` | `srcprep.py mac-fork SRC OUT` etc.: the resource fork of an AppleDouble / MacBinary file, the native fork, the HTBL 1 table |
| `mac-fbit3` | `macfbit3.py fbit SRC OUT` |

Verified: the route labels and kinds of this table were read from `routes.py` and checked by running `detect.scan` and
`routes.routes` on a folder of copies of fonts of this host: NanumGothic Bold, Caveat-VF and each of the ten faces of Noto Sans CJK Regular (index 0-9) are `outline` and get the route `mkfont` (Caveat, NanumGothic and each Noto CJK face also `experimental fit` and `vector fit`); neodgm.ttf is `outline-composite` with `mkfont`, `composite` (native) and `vector fit`; `wqy_12pt.bdf` (kind `bdf-iso10646`) and `18x18ko.pcf.gz` (`bitmap`, sizes [18]) get `mkfont` only; `hanglm16.pcf.gz` is `bdf-ksc5601` with `bdfface` and `bdfface + from-svf fit`; NEODG16.SVF (`svf-precomposed`) gets `copy` and `from-svf fit`, NEODG16A.SVF (`svf-jamo`) `copy`.

The same check on copies of the proprietary sources of the recipes above (2026-11-22; details in each recipe): raw DOS fonts
are `dos-raw` with `dos raw` (11,520-byte ones also `johab844`); `johabm16.bdf` is `bdf-johab` with `hanterm`; `batang24.bdf`
is `bdf-ksc5601` with `bdfface` and `bdfface + from-svf fit`; Gulim and Mac Seoul with strikes are `outline-composite` / `outline`
with `mkfont` (the bitmap-only Seoul `bitmap`, `mkfont` only); Windows FONs labelled with no route ("no Unicode character map, mkfont cannot read it");
the HWP 1.x, HWP 3.0 and KS X 1001 dump files as in their recipes (2026-11-23: `hwp1` three entries a Hangul file with `hwp1` and `hwp bdf + mkfont`, `ks-raw` with `hwp bdf + mkfont`, `hwp3 844` for the 16 px HWP 3.0 FNTs, and the experimental `hwp bdf + from-svf fit`; a `.PFT` of no layout read here, such as Taebaek's `HANJA24.PFT`, `hwp-pft` "other"); the Mac fonts in local mode as above (the 1.0 fonts as `mac-fbit1` with `mac fbit 1.0`). The `mask fit` row appears for neodgm.ttf, Noto Sans CJK KR and Malgun Gothic once `mask_ok` is set (the server sets it
when `freetype-py` and `uharfbuzz` import).

<a id="faces-of-svf"></a>

## 15. Faces of svf/

<a id="rebuilding-the-faces-of-svf"></a>

`tools/build/faces.tsv` holds one row for every face of `svf/` (117 rows); `tools/build/build_faces.py` runs them and
compares each result with the shipped face:

    python3 tools/build/build_faces.py --out $OUT/rebuild                      # every row with a recipe
    python3 tools/build/build_faces.py --out $OUT/rebuild NGOTB15 GBATB23      # some faces
    python3 tools/build/build_faces.py --out $OUT/rebuild --ext nanumgothic-nhn=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf

Each line of the output is `FACE identical`, `FACE pixels` (same glyphs and header values, another byte order) or
`FACE differs: ...`; the run exits 1 when a row marked `identical` is not.

**Coverage (verified, 2026-11-22).** 117 faces:

| Status | Faces | Count |
|---|---|---:|
| rebuilt byte for byte from a font in `ttf/` | the mkfont and jamoset rows below except those listed next | 45 |
| rebuilt byte for byte with an external OFL font (`--ext nanumgothic-nhn=`, the hinted NanumGothicBold.ttf 3.021 of NAVER's original release, as Debian's `fonts-nanum` ships it) | NGOTB17, NGO17X1, NGO17X2 (`--mono-hint`), NGO15X2, NGO16BX2, NGO21AX2 (two glyphs from it with `--fallback-ttf`) | 6 |
| rebuilt, one glyph differs | NEODG16 (the shipped face also has U+212B, which neodgm.ttf lacks), NGOTB16 (also U+3000, which this NanumGothic-Bold.ttf lacks); every other glyph identical | 2 |
| documented only (no recipe with this repository's tools) | see [Faces without a recipe](#faces-without-a-recipe) | 64 |

<a id="the-precomposed-recipe-mkfont-rows"></a>

### 15.1. The precomposed recipe (`mkfont` rows)

    python3 tools/mkfont.py SOURCE.ttf OUT.tmp --size S --cell H --width W --bpp B --ascent A --clip-cell \
        [--mono-hint] [--fallback-ttf OTHER.ttf] --only-listed --unicode CODEPOINTS
    python3 tools/svf2to3.py OUT.tmp OUT.SVF --profile default

- `--size S`: the pixel size the font is drawn at (Pillow/FreeType `truetype(font, S)`); the face name carries it
  (`GBATB23` = Gowun Batang Bold at 23 px).
- `--cell H --width W`: the cell; it can be larger than the size (a game's line pitch, `GBATB17B` is 17 px in 26x24).
- `--bpp B`: 1 (a cut at half coverage, or FreeType's monochrome renderer with `--mono-hint`) or 2 (four coverage levels:
  `level = (coverage * 3 + 127) // 255`).
- `--ascent A`: the baseline row from the cell top. `--clip-cell`: every glyph stands on that baseline and ink outside the
  cell is cut (counted on stdout); without it a glyph that leaks above is moved down instead (see
  [Baseline, vertical shift and clipping](#baseline-vertical-shift-and-clipping)).
- `--mono-hint`: 1 bpp with the font's TrueType hinting (FreeType `FT_LOAD_TARGET_MONO` through Pillow's `fontmode "1"`):
  stems snap to whole pixels. It needs a hinted font; the NHN original NanumGothicBold.ttf is, the Google Fonts build is not.
- `--fallback-ttf`: code points the font lacks are drawn from a second font (here â and é of the NGO*X2 supplements).
- `--only-listed --unicode CODEPOINTS`: exactly the listed code points (the row's `tools/build/cps/FACE.txt`, the
  face's own list; for subset faces the list came from a game's text, which is not in this repository).
- `svf2to3.py --profile default`: mkfont writes its records in its own order; the shipped faces went through the
  v2 -> v3 conversion, which writes them in the canonical order of the `default` profile. Re-laying out a fresh bake
  gives the same bytes.

<a id="the-jamo-set-from-precomposed-recipe-jamoset-rows"></a>

### 15.2. The jamo-set-from-precomposed recipe (`jamoset` rows)

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf $OUT/PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf $OUT/PRE.svf --mask-font none -o $OUT/NEODG16A.SVF --layout 844

`--from-svf` decomposes the precomposed syllables of a 1 bpp face into the pieces of a set system (here 8x4x4) and keeps
its other glyphs. Neo Dunggeunmo is itself drawn as an OR of 8x4x4 pieces, so the fit is exact (IoU 1.000) and every one
of the 11,172 syllables composes. NEODG16D/E/F/32/32A are the same with other cells (22x22, 18x24, 20x24; 32 px in
36x36 and 46x54). NEODG16G is the 6x2x1 set system (`--layout 621 --advance 0 --check`, no `--ascent`/`--clip-cell`:
mkfont's ascent 12), 10,684 bytes: a small face for the MCU examples (IoU 0.958 against the precomposed bake).

<a id="families"></a>

### 15.3. Families

| Family | Faces | Upstream, version | Licence | Recipe status |
|---|---|---|---|---|
| NanumGothic Bold | NGOTB*, NGO*X? | Google Fonts `ofl/nanumgothic` (3.020), in `ttf/nanumgothic`; NHN original 3.021 for the 1 bpp hinted faces | OFL 1.1, RFN "Nanum", "NanumGothic" ... | verified (16 + 6 external), NGOTB16 one glyph |
| Gowun Batang Bold | GBATB*, GBA*X? | https://github.com/yangheeryu/Gowun-Batang (Google Fonts `ofl/gowunbatang`, 2.000), in `ttf/gowunbatang` | OFL 1.1 | verified (16); GBATB17O documented only |
| Neo Dunggeunmo | NEODG*, NEO16BX2 | https://github.com/neodgm/neodgm v1.601, in `ttf/neodgm` | OFL 1.1, RFN "Neo둥근모", "NeoDunggeunmo" ... | verified (5 precomposed, 7 jamo sets), NEODG16 one glyph; NEODG16B/C/O documented only |
| Black Han Sans | BHSAN28 | https://github.com/zesstype/Black-Han-Sans (1.001), in `ttf/blackhansans` | OFL 1.1 | verified |
| Coustard | COUSB24 | https://github.com/googlefonts/coustardFont (1.100), in `ttf/coustard` | OFL 1.1 | verified |
| Diphylleia | DIPHY36 | https://github.com/JAMO-TYPEFACE/Diphylleia | OFL 1.1 | documented only |
| Paperlogy | PAPLG16, PAPLG18, PAPER*, PAPLB* | https://github.com/fonts-archive/Paperlogy (designptn.com), 1.000 | OFL 1.1 | documented only |
| MaruBuri | MARU* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 | documented only |
| NanumSquareRound | NSQR* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 (NAVER's Nanum licence) | documented only |
| Gothic A1 | GOTHB18A, GOTHA*, GOTHB* | HanYang I&C (Google Fonts `ofl/gothica1`, 2.50) | OFL 1.1 | documented only |
| Single Day | SGDAY* | DXKorea (Google Fonts `ofl/singleday`, 1.00) | OFL 1.1 | documented only |
| Neo Dunggeunmo Pro | NDGPR* | https://github.com/neodgm/neodgm-pro 1.020 | OFL 1.1 | documented only |

Every face keeps its licence text beside it in `svf/` (`web/LICENCES.tsv` names it); the notes `svf/dos/*.TXT` and
`svf/jamo-extra/FACES.TSV` describe each face.

<a id="faces-without-a-recipe"></a>

### 15.4. Faces without a recipe

- `svf/iolo/SANS8J.SVF`: external conversion of iolo's legacy 8x4x4 SANS `.fnt`; source file is not included here.

These faces are kept as built; the row of `tools/build/faces.tsv` says why. These are reproduction limits.
For each source's licence, follow its row in [LICENCES.tsv](../web/LICENCES.tsv);
iolo's dual-licence ambiguity is described in [IOLO.TXT](../svf/iolo/IOLO.TXT).

- **Research-pipeline jamo sets** (PAPER*, PAPLB*, PAPLG18, MARU*, GOTHB18A, NSQR* in `svf/dos`, and every face of
  `svf/jamo-extra`): the syllable outlines were separated into initial / medial / final vector pieces, rasterised, and
  merged to 24/16/16 sets and up to 12 x 12 classes with usage weights by a research pipeline that is not part of this
  repository (`svf/dos/PAPLG.TXT`, `PAPMARU.TXT` and `svf/jamo-extra/FACES.TSV` record the runs and their quality). The
  closest tools here are `jamovec.py` (vector separation) and `jamoset.py --layout adaptive` (split sets): see
  [Jamo sets from TrueType and OpenType fonts](#jamo-sets-from-truetype-and-opentype-fonts).
- **Outline faces** NEODG16O, GBATB17O: the 16 / 17 px glyphs dilated by 2 px (drawn black under narration) by a
  game-specific decoration script that is not in this repository.
- **NEODG16B, NEODG16C**: 8x4x4 sets of Neo Dunggeunmo whose precomposed source was a bake of one game's characters;
  `jamoset.py --from-svf` over the full KS X 1001 set fits other pieces (71 of 441 glyphs of NEODG16B differ).
- **DIPHY36**: Diphylleia Regular at 36 px 1 bpp, rasterised by an external pipeline; `mkfont.py` with Diphylleia's
  current release draws other pixels (2,358 of 2,359 glyphs).
- **PAPLG16**: `mkfont.py Paperlogy-4Regular.ttf --size 16 --cell 18 --width 18 --bpp 2 --clip-cell --ascent 14
  --unicode ascii,2026,2122,3131-318e --only-listed --space-advance 6 --punct-extra 1` on Paperlogy 1.000; the 1.001
  release draws 81 of the 149 glyphs otherwise, and neither is in `ttf/`.

<a id="reference"></a>

## 16. Reference

<a id="ks-x-1001"></a>

### 16.1. KS X 1001

KS X 1001 (formerly KS C 5601) has 2,350 precomposed Hangul syllables (rows 0xB0-0xC8, 94 each), 51 compatibility jamo
(row 0xA4: U+3131..U+3163), symbols and Hanja. Tools:

- `mkfont.py --unicode` names: `ksx1001-hangul` (the 2,350), `ksx1001-nohanja` (symbols, jamo and the 2,350),
  `ksx1001-symbols`, `ksx1001` (with Hanja), `hangul` / `cp949-hangul` (all 11,172), `cp949` (everything CP949 decodes),
  `jamo` (U+3131..U+318E, 94); `--limit` intersects a `--chars-from` list with any of them, `--require` refuses a
  code point the font lacks.
- `jamoset.ks_x_1001_syllables()` (syllable indices) and the quality reports (`ks2350` columns) use the same set.
  `tools/test_recipes.py` checks that both equal the euc_kr codec's rows.
- A full JSET table composes all 11,172 syllables; direct JMAP faces may cover only a subset; compatibility jamo are drawn by a piece when the table names one, else by
  a whole glyph. `jamoset.py --blank-compat` rewrites a face to use whole glyphs where it has them.
- `facecheck.py` checks faces against a manifest (`verify`) and maps (`mapfaces`); coverage per face is in the web
  index (`web/mkindex.py`: `hangul` = KS syllables drawn, `subset` = a non-jamo, non-Latin-only face with fewer than 2,350).

<a id="encodings"></a>

### 16.2. Encodings

EUC-KR / wansung byte pair = GL code + 0x8080 (`가` = B0A1 = GL 3021); Python: `bytes((0xB0,0xA1)).decode("euc_kr")`.
Johab (Python `johab` codec): a 16-bit code `1 iiiii mmmmm fffff` with fill values (initial 2 = ㄱ, medial 3 =
ㅏ, final 1 = none), `가` = 8861; `bytes((0x88,0x61)).decode("johab")`. Unicode syllable = 0xAC00 + (initial x 21 + medial)
x 28 + final with 0-based jamo indices. See [Hangul composition and encodings](#ref-encoding). `tools/test_recipes.py` checks these examples.

<a id="known-limits"></a>

### 16.3. Known limits

- The default `--binarize mono` of `jamoset.py` needs `freetype-py` (a mask font also needs `uharfbuzz`): the recipes use `--binarize threshold`, and `--mask-font none`
  keeps a 1 bpp fit independent of `$JAMOSET_MASK_FONT`; see [Jamo sets](#jamo-sets-from-truetype-and-opentype-fonts).
- Run time (this host, one core): a 1 bpp `threshold` fit of a 16 px outline font about 12 s, a 2 bpp one about 73 s,
  Gowun Batang adaptive at 20 px about 90 s. A 2 bpp face is about 1.5-1.6x its 1 bpp face; a jamo set about a sixth.
- `mkfont.py --bpp 2` can encode a monochrome bitmap at its own size, but that adds no intermediate coverage; `svfscale.py --bpp 2` makes one at a smaller
  size ([A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font)), and no tool makes a 2 bpp jamo set from a bitmap.
- `mkfont.py` prints its summary in Korean: do not parse its stdout for field names.
- Known gaps of the tools in general: [tools.md](tools.md#remaining-gaps-of-the-tools), "Remaining gaps of the tools".

<a id="adding-a-face-to-svf"></a>

## 17. Adding a face to svf/

Make the face with a recipe above, check it ([Checking a face](#checking-a-face)), and add:

- its licence text beside it in `svf/`;
- a row in `web/LICENCES.tsv` and one in `web/FAMILIES.tsv`;
- a row in `tools/build/faces.tsv` (with a recipe, or method `none` and the reason).

`tools/test_build_faces.py` and `tools/test_web_picker.py` fail otherwise. The maker writes ready-made lines for these
tables (`build-<id>/LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`).

<a id="references"></a>

## 18. References

- <a id="ref-opentype"></a>**OpenType glyphs, shaping and bitmap strikes**: [glyf](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf), [EBDT](https://learn.microsoft.com/en-us/typography/opentype/spec/ebdt), [EBLC](https://learn.microsoft.com/en-us/typography/opentype/spec/eblc), [Hangul shaping](https://learn.microsoft.com/en-us/typography/script-development/hangul).
- <a id="ref-freetype"></a>**FreeType bitmap and Windows FNT support**: [Font formats](https://freetype.org/freetype2/docs/reference/ft2-font_formats.html), [Windows FNT driver](https://gitlab.freedesktop.org/freetype/freetype/-/blob/master/src/winfonts/winfnt.c), [TrueType bitmap loader](https://gitlab.freedesktop.org/freetype/freetype/-/blob/master/src/sfnt/ttsbit.c).
- <a id="ref-fonttools"></a>**fontTools variable-font instancer**: [varLib.instancer](https://fonttools.readthedocs.io/en/latest/varLib/instancer.html).
- <a id="ref-encoding"></a>**Hangul composition and encodings**: [Unicode Hangul algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/), [Python standard encodings](https://docs.python.org/3/library/codecs.html#standard-encodings), [KS C 5601 mapping](https://www.unicode.org/Public/MAPPINGS/OBSOLETE/EASTASIA/KSC/KSC5601.TXT).
- <a id="ref-bdf"></a>**BDF format**: [Adobe BDF 2.2](https://adobe-type-tools.github.io/font-tech-notes/pdfs/5005.BDF_Spec.pdf).
- <a id="ref-apple"></a>**Apple font tables and resource forks**: [TrueType reference manual](https://developer.apple.com/fonts/TrueType-Reference-Manual/), [Resource Manager](https://dev.os9.ca/techpubs/mac/MoreToolbox/MoreToolbox-9.html).
- <a id="ref-86box"></a>**86Box Korean VGA ROM metadata and rendering**: [ROM set](https://github.com/86Box/roms), [SVGA renderer](https://raw.githubusercontent.com/86Box/86Box/master/src/video/vid_svga_render.c).
- <a id="ref-msx"></a>**Korean MSX machines and openMSX**: MSX Wiki [Daewoo CPC-300](https://www.msx.org/wiki/Daewoo_CPC-300), [Daewoo CPC-400S](https://www.msx.org/wiki/Daewoo_CPC-400S), [Daewoo DPC-200](https://www.msx.org/wiki/Daewoo_DPC-200), [Goldstar FC-80U](https://www.msx.org/wiki/Goldstar_FC-80U), [Daewoo machines](https://www.msx.org/wiki/Category:Daewoo); [openMSX MSXKanji.cc](https://raw.githubusercontent.com/openMSX/openMSX/master/src/MSXKanji.cc) (the `hangul` font device), [openMSX console commands](https://openmsx.org/manual/commands.html); msx.org forum [Daewoo CPC-400S hanja display bug](https://www.msx.org/forum/msx-talk/openmsx/daewoo-cpc-400s-hanja-display-bug) (the 256 KB font ROM); [file-hunter system ROMs](https://download.file-hunter.com/System%20ROMs/).
- <a id="ref-mame"></a>**MAME machine metadata, ROM loading and tile layouts**: [SPC-1500](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/samsung/spc1500.cpp), [tumbleb](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/dataeast/tumbleb.cpp), [raiden2](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/seibu/raiden2.cpp), [midas](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/snk/midas.cpp), [neogeo](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/snk/neogeo.cpp), [Neo Geo sprites](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/snk/neogeo_spr.cpp).
- <a id="ref-fonts"></a>**Font sources and licences**: [Noto CJK](https://github.com/notofonts/noto-cjk), [Google Fonts](https://github.com/google/fonts/tree/main/ofl), [Un fonts (Debian)](https://sources.debian.org/src/fonts-unfonts-core/), [X11 bitmap fonts](https://www.cl.cam.ac.uk/~mgk25/ucs-fonts.html), [HBF](https://www.ibiblio.org/pub/packages/ccic/software/fonts/README), [SIL OFL 1.1](https://openfontlicense.org/open-font-license-official-text/).
- <a id="ref-fontconfig"></a>**fontconfig installation and language matching**: [User guide](https://fontconfig.pages.freedesktop.org/fontconfig/fontconfig-user.html), [Korean orthography](https://gitlab.freedesktop.org/fontconfig/fontconfig/-/blob/main/fc-lang/ko.orth).
- <a id="ref-7zip"></a>**7-Zip output-directory switch**: [7-Zip -o](https://7-zip.opensource.jp/chm/cmdline/switches/output_dir.htm).
- Other family sources: [Gowun Batang](https://github.com/yangheeryu/Gowun-Batang), [Neo Dunggeunmo](https://github.com/neodgm/neodgm), [Black Han Sans](https://github.com/zesstype/Black-Han-Sans), [Coustard](https://github.com/googlefonts/coustardFont), [Diphylleia](https://github.com/JAMO-TYPEFACE/Diphylleia), [Paperlogy](https://github.com/fonts-archive/Paperlogy), [NAVER](https://hangeul.naver.com), [Neo Dunggeunmo Pro](https://github.com/neodgm/neodgm-pro).
- Historical input descriptions: [HWP 1.20](https://archive.org/details/hwp-120), [HWP 3.0 DOS](https://archive.org/details/hwp-30-dos), [MAME ROM set metadata](https://archive.org/details/mame-roms-non-merged), [iolo 8x4x4](https://github.com/iolo/8x4x4-fonts).

[Project overview](../README.md) · [Tool reference](tools.md)
