**English** | [한국어](recipes.ko.md)

# Recipes: from a font to an SVF face

How the faces of `svf/` are made from their upstream fonts, and how to make faces from every kind of Korean font source
the tools of this repository can read. Every tool is described in [tools.md](tools.md); the format is `spec/SVF.md`.

No font data other than the OFL fonts in `ttf/` and the faces in `svf/` is in this repository. The how-tos for
proprietary fonts (classic Mac, HWP, other DOS-era fonts) describe the method and the commands; you supply the files.

**Conventions.** Commands run from the repository root. `$OUT` is a scratch folder of your own
(`OUT=$HOME/work/tmp/recipes; mkdir -p $OUT`); no command here writes anywhere else. Names in capitals (`NG16J.SVF`,
`FACE.SVF`) are outputs you name yourself.

**The canonical step.** Every `mkfont.py` command below writes a face that `svf2to3.py --profile default` then re-lays out (shown
once, in [Precomposed faces](#precomposed-faces-mkfontpy)); the other commands leave it out for brevity. For a face you keep, add it. Run here: it
keeps the size of the Noto 1 bpp face (125,196 bytes) and of the BDF 1 bpp face (115,684 bytes).

**What "verified" means.** Every command block says one of three things. *Verified* (or *run here*): run as written on
2026-11-22 with the repository's own fonts, fonts of this host (Debian's `fonts-noto-cjk`, `xfonts-*`, DOSBox-X) or
proprietary fonts the maintainer holds (each is named where it is used, with the product it comes from; none of them,
and no byte of one, is in this repository), and the numbers quoted are from that run: the face's size in bytes, its glyph count, the render check of
[Checking a face](#checking-a-face) (`svfline.py measure` width / ascent / descent and the count of inked pixels of the
sample line), or for a jamo set the `--check` IoU. *Synthetic*: run only by the tests (`tools/test_recipes.py`,
`tools/test_build_faces.py`, `tools/test_macsfnt.py`, `tools/test_extract.py` and the maker's tests), on fonts built in the test. *Not run:
reason*: no source of that kind was found. Sizes drift with the tools' versions: quote them as "about",
and trust the run.

Contents:

- [Quick start: by input kind](#quick-start-by-input-kind)
- [Checking a face](#checking-a-face)
- [Outline fonts](#outline-fonts)
- [Bitmap fonts](#bitmap-fonts)
- [DOS-era raw fonts](#dos-era-raw-fonts)
- [Finding a font inside a program or data file, with Claude](#finding-a-font-inside-a-program-or-data-file-with-claude)
- [OS/2 Korean fonts (완성형) to a precomposed face and a jamo set](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set)
- [A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font)
- [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts)
- [An existing SVF](#an-existing-svf)
- [Choosing the number of sets (벌 수)](#choosing-the-number-of-sets-벌-수)
- [Desktop app and maker routes](#desktop-app-and-maker-routes)
- [Faces of svf/](#faces-of-svf)
- [Reference](#reference)
- [Adding a face to svf/](#adding-a-face-to-svf)

## Quick start: by input kind

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
| Windows `.FNT` / `.FON` | `mkfont.py` at its pixel size (opens, but FreeType gives it no Unicode map: draws nothing) | no | [Windows FNT and FON](#windows-fnt-and-fon) |
| DOS raw jamo-piece font (8x4x4 `HANGUL.FNT`, san, Dokkaebi, Kyra...) | `johab844.py` (16 px 8x4x4) | `jamoset.py --layout L` | [DOS-era raw fonts](#dos-era-raw-fonts) |
| HWP `.PFT` Hangul | no reader | no reader | [HWP 1.x and 2.x fonts](#hwp-1x-and-2x-fonts) |
| KS X 1001 raw dump (2,350 syllables in code order, or a 94 x 94 table) | `rawcarve.py bdf --dense`, then `bdfface.py` | `jamoset.py --from-svf` | [KS X 1001 raw dumps](#ks-x-1001-raw-dumps) |
| A font inside a program or ROM (DOS driver or TSR, word processor, Korean VGA BIOS + font ROM) | `binscan.py` to find, `rawcarve.py` to cut (raw, BDF, or composed by the driver's rule), then `bdfface.py` | `jamoset.py --layout 844` on a cut raw font, or `--from-svf` | [Finding a font inside a program or data file, with Claude](#finding-a-font-inside-a-program-or-data-file-with-claude) |
| OS/2 Korean System DBCS font (`$korZN16.FNT`, `$korZN24.FNT`; 완성형) | `os2dbcs.py table`, `rawcarve.py bdf --grid 0xA1,0xA1,94`, `bdfface.py` | `jamoset.py --from-svf` | [OS/2 Korean fonts (완성형)](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set) |
| TTF with jamo glyphs (conjoining jamo, PUA pieces, GSUB `ljmo`) | as any TTF | composites `jamovec.py --components`; variants `--mask-font`; else a fit | [TrueType fonts that already carry jamo](#truetype-fonts-that-already-carry-jamo) |
| A 24-48 px bitmap face wanted at 16 px or 2 bpp | `svfscale.py --size 16 [--bpp 2]` | `jamoset.py --from-svf` (1 bpp result) | [A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font) |
| Mac HangulTalk 1.0 `fbit` (45 sets + `fdef`) | no | `jamoset.py --layout mac-fbit-45sets` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| Mac HangulTalk 7.1 type-3 `fbit` + HTBL 1 | `macfbit3.py bdf` + `mkfont.py` | `macfbit_svf.py build` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| An SVF face | `svfdy.py`, `svf2to3.py` | `jamoset.py --from-svf` (1 bpp source) | [An existing SVF](#an-existing-svf) |

How many sets a jamo set should have: [Choosing the number of sets](#choosing-the-number-of-sets). Anti-aliased faces:
[2 bpp anti-aliased faces](#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font).

The check for every row is the same: [Checking a face](#checking-a-face) (sample-line measure and ink, `--check` IoU for
a jamo set). A 1 bpp face from a bitmap source stays 1 bpp at its own size; only a resample to a smaller size (`svfscale.py --bpp 2`) gives it levels. Choose the jamo set when the
target has little memory (a 2,350-syllable 16 px face is about 115 KB, its jamo set about 20 KB), the precomposed face
when every syllable must be exactly the source's.

## Checking a face

<a id="checks-for-a-new-face"></a>

Every recipe below ends with the same checks. The sample line is `안녕하세요 ABC 123`; the faces are 16 px in a 16x16 cell
unless stated.

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF       # width=W ascent=A descent=D
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray   # a 200x24 GRAY8 buffer
    python3 tools/fontmetrics.py FACE.SVF                                 # glyphs whose ink reaches past the advance
    python3 tools/svf2to3.py FACE.SVF $OUT/x.SVF --check                  # re-layout and compare every glyph
    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf -o $OUT/m.tsv

- The size of the file and the glyph count (the code point table's entries) come from the tool's own summary line;
  `mkfont.py` prints it in Korean (`글리프 2446개 ... 125,520 바이트`).
- The ink is the number of non-zero bytes of the `line` buffer: `python3 -c "import sys;print(sum(1 for b in open(sys.argv[1],'rb').read() if b))" $OUT/out.gray`.
  A face that draws nothing has ink 0.
  The 200x24 buffer and baseline 16 above fit a 16 px cell. For a face whose cell C is not 16 (12, 15, 24, 40, 48 px) the
  recipes' ink numbers are from `line 400 C+8 0 C` (a 400-wide buffer, the baseline at the cell height, C+8 rows: the
  buffer must be at least as wide as the measured width and as tall as the cell plus descent, or the line is clipped):
  `python3 tools/svfline.py line 400 32 0 24 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray` for a 24 px face. Every 16 px
  number reproduces with the 200x24 command and every other cell with this rule.
- A jamo set is judged by `--check` (on `jamoset.py` and `jamovec.py`): it composes all 11,172 syllables from the pieces
  and fails on a table error; the fit line before it prints the IoU of the pieces against the source's syllables
  (`fit: 11172 syllables, IoU 0.817`). `--check` does not fail on a poor fit: read the IoU, and look at the result
  (`svfline.py line`, or the `web/` picker).
- `svf2to3.py --check` compares glyph by glyph through `svfline`; `facecheck.py` checks faces against a manifest.
  `tools/build/build_faces.py` rebuilds the faces of `svf/` (see [Faces of svf/](#faces-of-svf)).

Reference run (verified), NanumGothic Bold at 16 px (below): 1 bpp `125,520` bytes, 2,446 glyphs, `width=146 ascent=14
descent=2`, ink 677.

## Outline fonts

FreeType reads TrueType and CFF (OpenType `.otf`) alike, so a static TTF or OTF with a Unicode cmap goes straight into
the tools; `jamoset.py --from-ttf`, `jamoaa.py`, `jamovec.py` and `--binarize threshold|ridge` flatten the outlines
themselves (fontTools pen, exact-area coverage), the same for both. Collections, variable fonts and Mac-format fonts need
one step first (below).

### Precomposed faces (`mkfont.py`)

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

### OpenType CFF (`.otf`)

Noto Sans CJK KR is a CFF font a reader can get (SIL OFL 1.1; Debian's `fonts-noto-cjk` ships it as
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`, a collection of the KR, JP, SC, TC and HK faces: see
[TTC and OTC](#ttc-and-otc)). Save the KR face as a plain `.otf` and bake it:

    python3 maker/srcprep.py ttc-face /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc $OUT/NotoSansCJKkr.otf --index 1
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-2bpp.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --binarize threshold \
        --mask-font none --check -o $OUT/noto16-jamo-1bpp.svf
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --bpp 2 --check -o $OUT/noto16-jamo-2bpp.svf

Verified (the full font, not a subset): the face is named "Noto Sans CJK KR"; 1 bpp `125,196 bytes`, 2,446 glyphs, `width=141
ascent=11 descent=5`, ink 472; 2 bpp `197,992 bytes`, ink 700; the jamo set `19,040 bytes`, 439 glyphs, 344 pieces,
IoU 0.786 over 11,172 syllables (6.9 s), `width=146 ascent=14 descent=2`, ink 477; the 2 bpp jamo set `23,268 bytes`, 439 glyphs, level error 0.208, IoU at level 2 0.781, 62 s, `width=141 ascent=14 descent=2`, ink 722 (a CFF font's jamo sets fit worse than a TrueType font's: 0.786 and 0.781 against 0.817 and 0.822 for NanumGothic). The ascent is the font's own, so
another font's faces differ in baseline: see [Baseline, vertical shift and clipping](#baseline-vertical-shift-and-clipping).

### Jamo sets from TrueType and OpenType fonts

A jamo set (조합형) holds pieces and a table; every syllable is the OR of two or three pieces. From an outline font there
are three ways to get the pieces, by what the font holds.

**1. Composite glyphs (TrueType `glyf`).** Some fonts store a syllable as a composite of its jamo glyphs. Then the
components *are* the pieces:

    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 1 --check -o $OUT/NEOVEC16.SVF
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

Verified: neodgm.ttf has 11,172 composite syllables; `master` took 25 s (344 pieces, 0 bad shapes), the 1 bpp render
15,724 bytes and the 2 bpp render 19,452 bytes, both 11,172 syllables composed. The vector render differs from the
raster fit NEODG16A in 2,633 of 11,172 syllables (counted on 2026-11-03, not re-counted; FreeType's pixel snapping of a pixel font against `jamovec`'s exact-area
rasteriser). Check a font first:

    python3 -c "from fontTools.ttLib import TTFont; f=TTFont('FONT.ttf'); c=f.getBestCmap(); g=f['glyf']; print(sum(g[c[x]].isComposite() for x in c if 0xAC00<=x<=0xD7A3))"

In `ttf/`: neodgm 11,172 composite syllables; NanumGothic Regular/Bold and NanumMyeongjo Bold 8,822 (the syllables
outside KS X 1001 are composites, the 2,350 are not); NanumPenScript 8,693; the others none. `--components` with a
partly composite font uses the composites only ("auto" picks components when most syllables are composite).
**CFF / CFF2 (OpenType `.otf`) has no composite glyphs**: every syllable is a flat outline there, so the pieces must come
from the next two ways.

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
`bdfface + from-svf fit` routes leave it automatic. A separate research repository measured the pieces those features return, at
12 px with hinting: Malgun Gothic gives 5/2/1 sets (164 pieces), Noto Sans CJK KR 6/2/4 (264 pieces; in the Noto TTC,
KR is index 1); faces made straight from them read well but differ from the precomposed glyphs by a pixel or two (mean
IoU about 0.58), because the font's conjoining pieces are laid out differently from its precomposed syllables. That work
also found that in the same byte budget a few dozen frequent syllables stored as LIST exceptions (`jamoexc.py`) improve
more than more sets do. No data of those fonts is in this repository.

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
use the repository's own exact-area rasteriser (fontTools pen, so TrueType and CFF alike). A fit is an approximation:
read the IoU, and look at the result (`web/` picker, or `svfline.py line`).

**Pitfalls.** A font that draws few syllables (Black Han Sans: 2,581) fits only those (`--present-only`, the default);
the rest compose from the nearest pieces. `--check` composes all 11,172 syllables and fails on a table error, not on
a poor fit.

### TrueType fonts that already carry jamo

Some Korean fonts carry jamo glyphs besides their syllables. Whether a tool can use them depends on how the font links
them to the syllables. Survey a folder first (`fontTools`: the cmap entries in U+1100-11FF, in the Private Use Area
U+E000-F8FF, the composite syllables, the GSUB features `ljmo` / `vjmo` / `tjmo`); run here over the maintainer's
download collection (Korean web fonts, Debian font packages, the johab-fonts research set; 375 fonts with 50 or more conjoining jamo or 100 or more
PUA glyphs), three kinds turned up:

| What the font holds | Example (here) | Route | Section |
|---|---|---|---|
| GSUB `ljmo`/`vjmo`/`tjmo`: positional variants of U+1100.. | NanumMyeongjo / NanumBarunGothic YetHangul (250 variants reached), UnBatang (164) | the variants as masks (`--mask-font FONT`) | [way 2](#jamo-sets-from-truetype-and-opentype-fonts) |
| composite syllables whose components are PUA piece glyphs | the Un fonts (UnDotum, UnBatang, UnGraphic, UnDinaru, UnGungseo, UnPilgi: 11,172 composites each) | `jamovec.py master --components` | [way 1](#jamo-sets-from-truetype-and-opentype-fonts), below |
| conjoining jamo U+1100.. drawn to overlap (vowel and final zero-width, placed left of the pen) and no variants | UnDotum (U+1100 advance 1000, U+1161 and U+11A8 advance 0 with negative x) | way 2 with one shape a jamo, or way 3 | below |
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
rasterisers differ, so 1.000 is not reachable): mask fit 0.648, 8x4x4 components 0.734, free fit 0.755, adaptive
components 0.840.

A font whose PUA holds positional jamo but whose syllables are plain outlines and which has no GSUB reaching the PUA
(MiraeroNormal: no composite syllable, no GSUB) gives no tool the rule that picks a variant for a syllable: the PUA
code assignment (which code is which jamo in which position) and the selection by vowel and final are the font maker's
scheme, written nowhere in the file. Such a font goes through way 3 like any other; using its PUA pieces would need
that scheme as a table (in the shape of a `rawcarve.py compose` spec, but drawing outline glyphs by code point, which
no tool does).

**(c) GSUB `ljmo` / `vjmo` / `tjmo`.** The mask fit of [way 2](#jamo-sets-from-truetype-and-opentype-fonts) (neodgm,
Noto Sans CJK KR, Malgun Gothic measured there).

### 2 bpp anti-aliased faces from a TrueType/OpenType font

<a id="anti-aliased-2-bpp-faces"></a>

A 2 bpp face stores four levels a pixel (0, 1, 2, 3; the reader expands a level to level x 85). It comes from an outline
font only (a bitmap source has no coverage; a larger bitmap can be resampled to 2 bpp, see
[A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font)).
Three routes:

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

A 2 bpp precomposed face is 1.5-1.6x its 1 bpp face, a 2 bpp jamo set about 1.2x its 1 bpp set. The jamo sets carry
more middle levels than the precomposed glyphs (a piece's level is a median over many syllables, and pieces OR by the
maximum); `--aa-refine 2` lowers the level error and raises the level-2 IoU at the cost of 1 KB here. A pixel font
(Neo Dunggeunmo) has no partial coverage at its own size: its 2 bpp face is the 1 bpp face at level 3 and only costs
bytes. The jamo sets' baseline comes from the fit (ink box centred), not from the font's ascent, so it can differ by a
row from the `mkfont.py` face (set `--baseline`).

**Choosing the size.** Anti-aliasing needs strokes about one to two pixels wide to carry levels; at the sizes above
two thirds of the inked pixels of the precomposed faces are already full (level 3). Smaller sizes were not measured
here; at 12-14 px compare the 2 bpp face with a 1 bpp `--mono-hint` face of a hinted font
([The precomposed recipe](#the-precomposed-recipe-mkfont-rows)) on the target before choosing. Bake at the size the
target draws rather than scaling a face at draw time. Check every result by its numbers (ink, the levels, and for a
jamo set the `aa:` line's level error and IoU at level 2) and by looking at it: `svfline.py line` writes GRAY8, and the
`web/` picker shows a face at its levels.

**Pitfalls.** An anti-aliased piece over another piece takes the maximum, not the sum: thin crossing strokes look lighter
than in the precomposed glyph. A 1 bpp target (MONO_PAGE) thresholds 2 bpp faces at draw time (`threshold` of the
target); give a mono display a 1 bpp face. `--bpp 8` (mkfont only) keeps full coverage for hosts.

### Baseline, vertical shift and clipping

The ascent field of a face is the baseline row from the cell top; the renderer puts a line's baseline at the pen y and
draws each glyph `dy` rows lower (per-glyph dy, `spec/SVF.md`).

How `mkfont.py` chooses it: `--ascent N` sets it. Without it, when the font's ascent + descent fit the cell it is the
font's ascent; when they do not, the ink of a probe ("한글AQg", or "AQgjy" with `--latin`) is centred in the cell; with
`--latin` the cap height goes to the top. Then, per glyph:

- default: a glyph whose ink would leave the cell at the top or the sides is moved into it (a per-glyph shift: that glyph
  then sits off the baseline); ink below the cell is cut;
- `--clip-cell`: every glyph stays on the one baseline and ink outside the cell is cut; stdout counts the glyphs cut
  above and below;
- `--fit-cell`: the size is lowered 1 px at a time until every glyph's ink fits the cell on one baseline.

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

`--dy` moves the glyph at draw time; the face's dy range (header bytes 17/18) widens, and a line's descent grows by it.
An engine without dy support draws those glyphs at their cell position.

**Pitfalls.** A cell smaller than the font's line pitch always cuts something: prefer `--fit-cell`, or a larger cell
with a fixed advance. Changing the ascent of a face changes where every line's ink lands (the MCU examples place a
line's baseline at its top row + the face's ascent).

### TTC and OTC

<a id="opentype-cff-collections-and-variable-fonts"></a>

`mkfont.py` opens index 0 of a collection (synthetic: a TTC of Galmuri9 + Galmuri7 bakes exactly as Galmuri9). For
another face, save it out as a plain font first (the same step the maker's `ttc-face` does; TrueType or CFF faces alike; name the output `.otf` for a CFF face, as the OpenType CFF recipe above does):

    python3 maker/srcprep.py ttc-face F.ttc $OUT/F1.ttf --index 1

Pick by name, not by position: in the Noto CJK collections KR is not index 0. List the names:

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; [print(i, f['name'].getDebugName(4)) for i, f in enumerate(C('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').fonts)]"

Verified on the host's Noto Sans CJK Regular collection: ten faces, index 0 Noto Sans CJK JP, 1 KR, 2 SC, 3 TC, 4 HK, then 5-9 Noto Sans Mono CJK JP, KR, SC, TC, HK. The face then goes into the recipes as any static font
([OpenType CFF](#opentype-cff-otf) above is exactly this).

### Variable fonts

`mkfont.py` draws the default instance. For another, cut a static instance first (fontTools, the maker's `instance`
step):

    python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o $OUT/Caveat-Bold.ttf
    python3 tools/mkfont.py $OUT/Caveat-Bold.ttf $OUT/CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/mkfont.py ttf/caveat/Caveat-VF.ttf $OUT/CAV24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAVB24.SVF     # one face per call: several faces are a fallback chain
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAV24.SVF

Verified: the default instance (Regular 400) bakes to 6,760 bytes and the 700 instance to 7,192 bytes (95 glyphs each,
"Hamburgefonstiv" 141 px wide in the Bold, 136 in the Regular; the summary's one omitted code point is a requested one the font lacks). Named instances are in the `fvar` table (`Caveat`: Regular, Bold; `EB Garamond`: Regular ..
ExtraBold).

### Mac-format TrueType

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

## Bitmap fonts

<a id="x-window-korean-fonts"></a>

Two kinds of bitmap fonts reach the tools by different paths: Unicode-encoded ones (`CHARSET_REGISTRY "ISO10646"`, or a
TrueType with embedded strikes) go through `mkfont.py` and FreeType; KS C 5601 / KS X 1001 encoded ones (`ENCODING` = the
GL code, the X Window Korean fonts) go through `bdfface.py`.

### ISO 10646 BDF and PCF

`mkfont.py` reads a BDF or PCF through Pillow's FreeType, at the file's built-in pixel size only (its strike); any other
size is `OSError: invalid pixel size`, and the maker's `detect.bitmap_strikes` names the sizes a font offers. There is no
shim or workaround: `mkfont.py` asks fontTools whether a code point is in the cmap and treats a non-sfnt file (BDF, PCF,
FNT) as unknown, not as an error (`cmap_has` returns None; since ec5c6b3). No BDF or PCF is in this repository; the runs below use fonts of
this host (not in the repository): `/usr/share/dosbox-x/wqy_12pt.bdf` (WenQuanYi Bitmap Song, 16 px, Unicode) and
`/usr/share/fonts/X11/misc/18x18ko.pcf.gz` (Misc Fixed Wide, 18 px).

    python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf $OUT/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-2bpp.svf --size 18 --bpp 2 --unicode ascii,ksx1001-hangul

Verified, without any shim: BDF `115,684 bytes`, 2,446 glyphs, `width=156 ascent=12 descent=4`, ink 348; PCF 1 bpp
`116,552 bytes`, 2,446 glyphs (18x18 cell), `width=234 ascent=15 descent=3`, ink 366; PCF 2 bpp `181,108 bytes`. A bitmap carries
no coverage, so `--bpp 2` only has levels 0 and 3: the same monochrome pixels at 2 bpp, not a smooth face. A jamo set from
these faces is a fit to the precomposed result: `jamoset.py --layout 844 --from-svf $OUT/bdf16-1bpp.svf --mask-font none --check -o ...`
(the next subsection shows the numbers for a bdfface face).

### KS C 5601 BDF and PCF

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

### hanterm

hanterm fonts (johab-1 encoding, glyph numbers as `ENCODING`, 10x(3|4)x4 sets, 529 glyphs) are read directly:

    python3 tools/jamoset.py --layout hanterm-johab johabm16.bdf --check -o $OUT/HTERM16J.SVF

Run on KAIST Myeongjo and KAIST Gothic, the 16 px Johab fonts of the hanterm 3.0.4 font set (`johabm16.bdf`,
`johabg16.bdf`; 529 glyphs each, `CHARSET_REGISTRY "JOHAB-1"`; KAIST; redistribution terms not stated), with the command above:

Myeongjo: `13,740 bytes`, 368 pieces, `check: composed 11172 syllables from 368 glyphs, JSET 1303 bytes`, `width=80 ascent=14
descent=2` (the five syllables of the sample; the BDF has no ASCII, give `--eng` a raw 8x16 English font for it), ink 310;
Gothic: `13,180 bytes`, ink 214. The maker's `detect.scan` gives both kind `bdf-johab`, label "BDF (johab)", sizes [16] and the
route `hanterm`. The same set's `10-6-6` folder (10x6x6 sets) is another layout and was not run. Synthetic
(`tools/test_recipes.py`): a 529-glyph hanterm BDF composes all 11,172 syllables in 10/4/4 sets.

### HBF

`bdfface.py --ascii` reads an HBF (the `.hbf` with its `.bin` or `.bin.gz` beside it), but only as the ASCII half of a
face; the Hangul half must be a BDF. Run with Sony Fixed 12x24 (`12x24.hbf` with `12x24.bin.gz`, the X11 Sony font as the
ibiblio HBF collection holds it; Sony, free to use with its notice) as the ASCII half and Baekmuk Batang 24 (`batang24.bdf`
of the Baekmuk 2.0 X11 BDF set, KS C 5601) as the Hangul half:

    python3 tools/bdfface.py --hangul batang24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HBF24.SVF

`206,872 bytes`, 2,350 syllables, ascent 22, step 24, no glyph clipped, `width=216 ascent=22 descent=2` (five 24 px syllables
and seven 12 px characters), ink 746; with the `.bin` unzipped beside the `.hbf` the face is byte for byte the same. The
maker lists a bare `12x24.hbf` as kind `hbf` with no route (an HBF is only a companion), and refuses one whose bitmap is
only `.bin.gz` on disk (label "HBF: unsafe bitmap reference"): unzip the `.bin` first. Synthetic
(`tools/test_bdfface.py`): a synthetic HBF as the ASCII half.

### Windows FNT and FON

FreeType has a winfnt driver and `mkfont.py` opens a Windows `.FNT` (or the `.FON` that holds several) at the font's own
pixel size, the way it opens a BDF or PCF, but it cannot draw from one: the driver gives these fonts a single charmap of
`FT_ENCODING_NONE`, no Unicode, so every code point falls on glyph 0. Run on the Windows 95 Korean system fonts (Microsoft,
proprietary): VGAFIX.FON "Fixedsys" 16 px, VGASYS.FON "System" 13 px, SERIFF.FON "MS Serif" 13 px, 8514FIX.FON:

    python3 tools/mkfont.py VGAFIX.FON $OUT/fon.svf --size 16 --bpp 1 --unicode ascii

exits with `--unicode 의 글자가 글꼴에 하나도 없다` ("no character of --unicode is in the font"), and the same with
`--unicode ascii,ksx1001-hangul`; Pillow draws "A", "B" and "가" as one and the same notdef glyph. The maker detects them
(`detect.scan`: kind `bitmap`, label "Windows FON face 0", sizes [16] or [13], route `mkfont`; the later faces `other`,
"face index 1: not convertible in v1"; MODERN.FON "no openable face"), so the route it offers fails on these files. No
Windows FNT or FON with Hangul glyphs was found: the Windows 95 Korean disks carry only Latin and OEM ones (Fixedsys,
System, Terminal, MS Serif, MS Sans Serif, Courier, Small Fonts; 25 FONs), and the Korean glyphs of that system are
TrueType (`gulim.ttc`, with strikes: [Embedded bitmap strikes](#embedded-bitmap-strikes)). A FON would have to be converted
to a BDF with an outside tool first; none is in this repository.

Not to be mixed up with DOS Johab `.FNT` files, which are jamo-piece fonts: see [DOS-era raw fonts](#dos-era-raw-fonts).

### Embedded bitmap strikes

An outline font with embedded bitmaps (TrueType `bdat`/`bloc`, OpenType `EBDT`/`EBLC`) is used by FreeType only at the
strike's own pixel size: run `mkfont.py --size N` with the strike's size and `--bpp 1`; at other sizes the outlines are
used, or the open fails for a bitmap-only font (`OSError: invalid pixel size`). The maker's `detect.bitmap_strikes` lists a
font's strikes and offers them as sizes. Run on two real fonts.

*Seoul* of the Mac OS 7.6.1 Korean CD (`Font Folder/Seoul[FFIL]`, Apple Korea / Elex, proprietary; strikes 9, 10, 12, 14, 16,
18, 20, 24 ppem, see [Mac-format TrueType](#mac-format-truetype)): after `macsfnt.py extract` and `unicode`, `mkfont.py --size 16
--bpp 1 --unicode ascii,ksx1001-hangul` writes the strike's pixels (`124,868 bytes`, ink 346); at `--size 17` it draws the outline.
The CD's bitmap-only copy of the same family (`CD Extras/Bitmap 서체 설치/Seoul/Seoul[FFIL]`, 2,626,404 bytes, `bdat` + `bloc` +
`bhed`, no `glyf`, maker kind `bitmap`, sizes [9, 10, 12, 14, 16, 18, 20, 24]) gives the same glyph bytes at 16 px, 12 px
(`105,972 bytes`) and 24 px (`219,116 bytes`), and `--size 17` stops with `폰트를 17px 로 열 수 없다: invalid pixel size`. But its
metrics are lost: it has no `head` (Apple's `bhed` instead), `mkfont.py` writes advance 0 for every glyph, `svfline.py measure`
says `width=0` and `fontmetrics.py` flags 2,445 of 2,446 glyphs as reaching past their advance. Bake the strikes from the
full font, not from the bitmap-only copy.

*Gulim* (굴림) of Windows (`GULIM.TTC`, Microsoft with HanYang I&C, proprietary; `EBLC` strikes 11 to 25 ppem):

    python3 maker/srcprep.py ttc-face GULIM.TTC $OUT/Gulim.ttf --index 0
    python3 tools/mkfont.py $OUT/Gulim.ttf $OUT/gu16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

16 px `125,288 bytes`, 2,446 glyphs, `width=149 ascent=14 descent=2`, ink 371; 12 px `106,208 bytes`, `width=114 ascent=10
descent=2`, ink 298; `svf2to3.py --profile default --check` keeps both sizes. A size with no strike (26) rasterises the outline
(`202,144 bytes`); `--bpp 2` also takes the outline even at a strike size (16 px: `182,604 bytes`), so only `--bpp 1` gives the
strike's own pixels. The maker's `detect.scan` on the extracted font gives kind `outline-composite`, label "TTF; bitmap strikes 11, 12,
13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25", sizes [16], routes `mkfont`, `composite` and `vector fit`.

## DOS-era raw fonts

DOS Hangul systems (Hangul BIOS, 이야기, 한메, san, Dokkaebi, games) stored jamo pieces, not syllables; a syllable was the
OR of an initial, a medial and an optional final, the set chosen by the other jamo. The tools read these raw files **by
exact byte size** (the maker's `detect.py` does the same, and a file of an unlisted size is "unknown") and by layout; there
is no header to sniff.

### Other DOS-era Korean fonts

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

`--eng` takes a raw 8x16 English font (2,048 or 4,096 bytes; scaled by whole numbers to the cell) for ASCII; `--base
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
| `844` | GHANC40.PFT, 72,000 bytes (Taebaek 3.5.1 Gothic 40 px), no `--eng` | `34,040 bytes`, 346 glyphs; `width=200 ascent=35 descent=5`, ink 1,751 |
| `844` | MHANC48.PFT, 103,680 bytes (Taebaek 3.5.1 Myeongjo 48 px), no `--eng` | `42,020 bytes`; `width=240 ascent=42 descent=6`, ink 1,865 |
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
(T-Hangul) are read at offset 2. A 24 px or larger source needs a matching English font or `--base`: the 40 and 48 px lines above have no ASCII, because `--eng` takes only 8x16 and the 12x24 fonts, not the 40 / 48 px English fonts (GASCII40.PFT, 30,720 bytes) of the same package.

### HWP 1.x and 2.x fonts

Hangul and Computer's DOS word processor shipped printer and screen fonts (`HANGUL*.PFT`, `ASCII.PFT`, `*.FNT`). What
this repository reads directly:

- the 12x24 English fonts: `jamoset.py ... --eng GASCII24.PFT` or `MASCII24.PFT` (Taebaek 3.5.1; 12,288 bytes, 256 glyphs of
  48 bytes: used in the table above) and HBIOS 12x24 (15,360 bytes). HWP 1.20's own `ASCII.PFT` is a different file (41,654
  bytes: a 32-byte "HWP Font Editor v1.0" header and 991 glyphs of 14x24, 42 bytes each, column-major) and is refused:
  `an English font has 2048 or 4096 bytes (8x16), 15360 (HBIOS 12x24) or 12288 (PFT 12x24), not 41654`;
- HWP 2.x screen fonts that are plain raw 8x4x4: `HMJ.FNT` (11,520 bytes) of the Hangul 2.1 PRO disks (disk 13), read
  as any `844` font: `python3 tools/jamoset.py --layout 844 HMJ.FNT --eng ROMAN16.FNT --check -o $OUT/HMJ.SVF` writes `15,700 bytes`
  and composes all 11,172 syllables, identical to `johab844.py`;
- any precomposed 1 bpp face you made of the Hangul, refitted to pieces: `jamoset.py --layout 844 --from-svf
  FACE.SVF --mask-font none --check`;
- a BDF of the composed syllables: `bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf --cell 24x24 --chars-from LIST`.

Run on HWP 1.20 for DOS (Hangul and Computer, 1989-1990; `HANGUL1.PFT`, 70,592 bytes, three faces of 24x24 in 7/2/3, 7/2/2 and
5/2/2 sets, 72 bytes a glyph, column-major; proprietary), face 1 (Gothic by menu order): the research tool `hwp1_fnt.py` of
the johab-fonts notes composes the syllables; a 30-line script wrote its 2,350 KS X 1001 syllables and its `ASCII.PFT` as two BDFs
(`ENCODING` = the GL code; 24x24 and 14x24), and then

    python3 tools/bdfface.py --hangul hwp-gothic.bdf --ascii hwp-ascii.bdf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HWP24.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/HWP24.SVF --mask-font none --check -o $OUT/HWP24J.SVF

`218,848 bytes`, 2,350 syllables, `width=232 ascent=21 descent=3`, ink 886; the jamo set `24,264 bytes`, 344 pieces, IoU 1.000
over the 2,350 syllables (all exact), ink 886: the fit is exact for these 24 px faces, as the HWP rule composes every syllable
from three pieces.

What it does **not** read: the HWP `.PFT` Hangul files themselves. `python3 tools/jamoset.py --layout 844 HANGUL1.PFT -o $OUT/rejected.SVF` stops (exit 1) with `size 70592
is not an 8x4x4 size`. Their glyphs are composed by HWP's own rules, which a separate research tool (`hwp1_fnt.py` and `kfont.py`
of the johab-fonts research notes) decodes; that reader is not part of this repository, and its output (a BDF or a
precomposed face) is the input of the routes above. The maker's `detect.scan` gives these files kind `other`, label
"unknown".

### KS X 1001 raw dumps

A raw dump of the 2,350 precomposed KS X 1001 syllables (one bitmap per syllable in code order, as some DOS and embedded
systems keep them) has no builder that reads it directly: there is no layout for it in `jamoset.py`, `bdfface.py` or the
maker, and a file of such a size is not recognised. Run on `GHAN24.PFT` of Taebaek 3.5.1 (Gothic 24 px; 169,200 bytes = 2,350
x 72, no header, 24x24 row-major with three bytes a row, in KS order from 가): `python3 tools/jamoset.py --layout 844 GHAN24.PFT -o $OUT/rejected.SVF` stops (exit 1) with
`size 169200 is not an 8x4x4 size`, and the maker's `detect.scan` calls it `other`, "unknown". `rawcarve.py bdf --dense`
cuts it into a Unicode BDF (`binscan.py info` names the size: "KS X 1001 syllables, 24x24 (2,350 x 72 B)"), and
[KS C 5601 BDF and PCF](#ks-c-5601-bdf-and-pcf) goes on from there; with Sony Fixed 12x24 for ASCII:

    python3 -I tools/rawcarve.py bdf GHAN24.PFT --glyph 24x24 --chars ks-hangul --dense --ascent 22 -o $OUT/ghan24.bdf
    python3 tools/bdfface.py --hangul $OUT/ghan24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/GHAN24.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/GHAN24.SVF --mask-font none --check -o $OUT/GHAN24J.SVF

The face is `216,448 bytes`, 2,350 syllables, `width=216 ascent=22 descent=2`, ink 1,074; the jamo set `33,684 bytes`, 344 pieces, IoU
0.710 over the 2,350 syllables (the face is a whole-syllable design, not an OR of pieces, so the fit is poor). The same
face came from a 15-line script before `rawcarve.py` existed; the tool's BDF gives a face of the same size and ink (216,448 bytes, ink
1,074). A dump of the whole 94 x 94 table takes `--grid 0xA1,0xA1,94` instead of `--dense`
([OS/2 Korean fonts](#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set)).

## Finding a font inside a program or data file, with Claude

DOS Hangul drivers, word processors, games and the font ROMs of Korean VGA cards keep their fonts as bare bytes inside a
program (`.COM`, `.EXE`, a TSR) or a ROM image: no header, no name, often no file of their own. Two tools of this
repository find and cut them, and an assistant such as Claude does the reading in between (where a font starts, which
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
tools only read bytes and never run the file's code; run them with `python3 -I` on downloads. Unpack an archive first
(`binscan.py info` names ARJ and ZIP; `7z x -o NEWDIR FILE.ARJ`), into a folder of its own; never run a DOS program on
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

### The prompt

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

The three examples below were worked with this prompt (2026-11-22). Their sources are proprietary programs and ROM dumps
the maintainer holds; no byte of them is in this repository.

### NKP: a Hercules Hangul TSR with cropped pieces

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

### Dokkaebi: the font inside the driver

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

### Korean VGA font ROMs (86Box)

Source: the 86Box ROM set (https://github.com/86Box/roms, commit 1ac40f2 of 2026-11-14), downloaded file by file (url,
bytes and sha256 recorded beside the files). Its tree lists three Korean VGA
cards, each a 32 KB VGA BIOS and a 512 KB KS C 5601 font ROM: Trigem Korean VGA (ET4000, `video/et4000/tgkorvga.bin`,
`tg_ksc5601.rom`), Kasan ET4000 (`et4000_kasan16.bin`, `kasan_ksc5601.rom`) and ATI 28800 Korean (`video/ati28800/
atikorvga.bin`, `ati_ksc5601.rom`); the other Korean entries are machine BIOSes (Samsung Deskmaster 286, Hyundai Super-16T,
LG IBM, TriGem 286M / 486G) with no Hangul font. The ROMs are dumps of proprietary chips.

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

Other ROM sets checked: the openMSX system ROM set (file-hunter's RomDB, 1,241 files) holds one Korean font,
the Daewoo CPC-400S `400skfn.rom` (131,072 bytes: 16x16, 32 bytes a glyph, the first half of a 256 KB font, KS symbols
and 1,316 syllables in the machine's own order; johab-fonts `notes/msx.md`); the other Korean MSX ROMs (`cpc-300_hangul`,
`dpc-200_hangul`, `cpc-400s_hangul`) are Hangul BASIC code, and the MSX1 jamo font is the BIOS's 8x8 character table.
An 88emuplayer ROM pack (`88emuplayer-roms.zip`) holds Roland sound-module ROMs (SC-55, SC-88, SC-8850, CM-300) and no font. No MAME-style
set with a Korean font was found.

## OS/2 Korean fonts (완성형) to a precomposed face and a jamo set

OS/2's Korean "System DBCS" fonts (`$korZN16.FNT`, `$korZN24.FNT`) are precomposed (완성형): the whole KS X 1001 table
(1,128 symbols, the 2,350 syllables, 4,888 Hanja) in code order, every glyph compressed (a Huffman code of nibbles, then
a prediction from the two rows above through a context table). `tools/os2dbcs.py` decodes them into the 94 x 94 table;
from there the route is the one of any KS X 1001 dump: a BDF, `bdfface.py`, and a jamo set fitted to the face.

    python3 -I tools/os2dbcs.py info '$korZN16.FNT'
    python3 -I tools/os2dbcs.py table '$korZN16.FNT' -o $OUT/zn16.bin
    python3 -I tools/rawcarve.py bdf $OUT/zn16.bin --glyph 16x16 --chars ks-hangul --grid 0xA1,0xA1,94 -o $OUT/zn16.bdf
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/8x16.pcf.gz $OUT/8x16.bdf
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

## A low-resolution face from a high-resolution bitmap font

A 24, 40 or 48 px bitmap font (a DOS or printer font, a BDF, a ROM) is wanted at 16 px, or as a 2 bpp face. What the
tools do today: `mkfont.py` opens a BDF or PCF only at its own size (`OSError: invalid pixel size` at any other,
[ISO 10646 BDF and PCF](#iso-10646-bdf-and-pcf)); `jamoset.py --from-svf` keeps the source's cell; the C renderer and
`svfline.py` scale a face at draw time (`scale_num / scale_den`, a box filter into 8-bit coverage), but nothing wrote a
smaller face. `tools/svfscale.py` does: it draws every glyph of a 1 bpp face (a jamo set's syllables composed) or a BDF,
box-filters it to the new cell (each output pixel is the exact inked share of its source footprint) and writes a
precomposed face, 1 bpp by a threshold or 2 bpp in four levels:

    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 -o $OUT/ZN24TO16.SVF --compare $OUT/OS2ZN16.SVF   # 1 bpp, share >= 0.5
    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 --bpp 2 -o $OUT/ZN24TO16A.SVF                     # 2 bpp
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/ZN24TO16.SVF --mask-font none --check -o $OUT/ZN24TO16J.SVF

The other two sources go the same way: `bdfface.py --hangul dotum24.bdf --ascii $OUT/12x24.bdf --cell 24x24 ...` (and
`dotum16.bdf` with `8x16.bdf` for the face to compare), and `jamoset.py --layout 844 GHANC40.PFT --check -o
$OUT/GHANC40J.SVF` (and `GOTHIC16.FNT --eng ROMAN16.FNT` for the comparison), each then through `svfscale.py --size 16`.

The 2 bpp result is exactly what the renderer draws when it scales the 24 px face by 2/3 and the coverage is quantised
to four levels (checked on all 2,350 syllables of the OS/2 face below: every one equal), so a stored 2 bpp face and
draw-time scaling give the same pixels; the stored face costs memory, the scaled draw costs time. A jamo set can be
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
| Taebaek 3.5.1 Gothic 40 (`GHANC40.PFT`, the 8x4x4 face of [Other DOS-era Korean fonts](#other-dos-era-korean-fonts), `33,944 bytes`) | `121,772 bytes`, 2,350 syllables (no ASCII: `--eng` reads the 40 px English font GASCII40.PFT only once card t_262e222d merges), `width=80 ascent=14 descent=2` | 259 | `192,800 bytes` | 451 | `13,920 bytes`, IoU 0.990 | 0.471 against GOTHIC16.FNT |

The 40 px source is itself an OR of 8x4x4 pieces, so its 16 px resample still nearly is (IoU 0.990); the two whole-
syllable designs fit 8x4x4 poorly. The threshold trades strokes for blobs: the OS/2 face at `--threshold 0.25` has ink
615 (`0.5`: 410) and overlaps the drawn 16 px face 0.489. A BDF read directly (`svfscale.py dotum24.bdf`) takes every
glyph the BDF has (8,226 with the Hanja) and its own ascent; go through `bdfface.py` first for a face with ASCII and
the cell you want.

**Pitfalls.** A 1-pixel stroke at 24 px covers two thirds of a 16 px pixel and survives a 0.5 threshold only where it
lines up; at 40 or 48 px thin strokes become 0.4-share pixels and vanish at 1 bpp. Resampling does not redraw: a drawn
16 px face (the last column above) is crisper, and a 2 bpp face from an outline font
([2 bpp anti-aliased faces](#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font)) has real coverage, not the
coverage of a bitmap's staircase.

## Classic Mac Korean bitmap fonts

No Apple data is in this repository; the tools read your own files. The maker's local mode (`maker/README.md`, "Local
mode") reads these fonts in place from your disk, through the same tools, and writes the faces only into a folder you
choose.

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
maker reads these fonts as "HangulTalk 7.1 type-3 fbit, 24 px, 661 planes (needs HTBL 1)", not as 1.0: a real 1.0 `fbit` header
carries generation 3 like the 7.1 ones, and `detect.py` tests the generation before the 45 sets (its tests build 1.0 fonts
with generation 0). The command above is right for them, but the `mac fbit 1.0` route is not offered for a real font.

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
extra syllables are extrapolated (not Mac output). The BDF route goes on with `bdfface.py --cell 12x12 --chars-from
<the 2,350 syllables>` to a precomposed face. To shrink a many-variant face for an MCU budget:

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
8 x 4 classes, 9/6/3 sets (`7,928 bytes` as JSET v2), every syllable verified; both draw the five syllables of the sample line as
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

## An existing SVF

Source: `svf/dos/NEODG16.SVF` (a precomposed 1 bpp face, 16x16, 2,905 glyphs, with a metrics table).

Set a dy (no other byte changes):

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

## Choosing the number of sets (벌 수)

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
| `dkb-printer-7x2x2`, `dkb-printer-12x4x4` | 7 / 2 / 2, 12 / 4 / 4 | Dokkaebi printer fonts | source files only |
| `kyra-lok` | its own, 385 pieces | Kyrandia's MK15.BIT | source files only |
| `mac-fbit-45sets` | derived from the font (Munjo24: 20 / 15 / 4, 8 x 4 classes) | HangulTalk 1.0 `fbit` | source files only |
| `adaptive[:NI,NM,NF]` | from 8 / 4 / 4 up to NI / NM / NF (default 32 / 24 / 12; NI 8-32, NM 4-24, NF 4-16), 12 x 12 classes | `jamoadapt.py`: splits a set where the syllables that share a piece disagree | yes |

**The options that change the counts.** `--layout adaptive:NI,NM,NF` caps the sets (it stops earlier when a split no
longer gains: at least 0.05 % of the starting cost, at least 4 syllables a side, fixed in `jamoadapt.py`); the classes
are always 12 x 12 for `adaptive` (even with `--jset-big`, which only lets a source's own larger tables be written).
`jamovec.py master --adaptive NI,NM,NF` and `--class-limit N` do the same for a vector master (`--class-limit` above 12
only simulates a bigger table). After a fit, `jamomerge.py merge --points BYTES ...` merges variants, sets and classes
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

## Desktop app and maker routes

The maker (`maker/`, the desktop app of [desktop-app.md](desktop-app.md), the server of [maker/README.md](../maker/README.md))
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
| jamo, `mac fbit 7.1 direct` / `derived` | mac-fbit3 + HTBL 1 | `macfbit_svf.py build FBIT HTBL -o OUT --mode direct\|derived [--latin SUITCASE]` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| precomposed, `mac fbit 7.1 bdf + mkfont` | mac-fbit3 + HTBL 1 | `macfbit3.py bdf FBIT HTBL NAME mac.bdf`, `srcprep.py bdf-pixel-size mac.bdf mac-sized.bdf --size S`, `mkfont.py mac-sized.bdf mkfont.tmp --size S --bpp 1 --unicode ...`, `svf2to3.py ... --profile default` | [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts) |
| precomposed or jamo, `copy` | svf-precomposed, svf-jamo | none when used as uploaded; `svf2to3.py SRC OUT --jset-version V --check` for a v2 face or a requested JSET change | [An existing SVF](#an-existing-svf) |
| jamo, `from-svf fit` | svf-precomposed, 1 bpp | `[svf2to3.py ... source-v3.svf]`, then `jamoset.py --layout L --from-svf SRC --check -o OUT [--eng E]` | [An existing SVF](#an-existing-svf) |

`L` is `844` or `adaptive` for the fits and the layout the source kind names otherwise; `[--eng E]` is the English
companion the page paired with the font.

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
with `mkfont` (the bitmap-only Seoul `bitmap`, `mkfont` only); Windows FONs `bitmap` with `mkfont` (which fails on them);
`GHAN24.PFT` and the HWP `.PFT` files `other`, "unknown"; the Mac fonts in local mode as above, where the 1.0 fonts show as
type 3. The `mask fit` row appears for neodgm.ttf, Noto Sans CJK KR and Malgun Gothic once `mask_ok` is set (the server sets it
when `freetype-py` and `uharfbuzz` import).

## Faces of svf/

<a id="rebuilding-the-faces-of-svf"></a>

`tools/build/faces.tsv` holds one row for every face of `svf/` (116 rows); `tools/build/build_faces.py` runs them and
compares each result with the shipped face:

    python3 tools/build/build_faces.py --out $OUT/rebuild                      # every row with a recipe
    python3 tools/build/build_faces.py --out $OUT/rebuild NGOTB15 GBATB23      # some faces
    python3 tools/build/build_faces.py --out $OUT/rebuild --ext nanumgothic-nhn=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf

Each line of the output is `FACE identical`, `FACE pixels` (same glyphs and header values, another byte order) or
`FACE differs: ...`; the run exits 1 when a row marked `identical` is not.

**Coverage (verified, 2026-11-22).** 116 faces:

| Status | Faces | Count |
|---|---|---:|
| rebuilt byte for byte from a font in `ttf/` | the mkfont and jamoset rows below except those listed next | 45 |
| rebuilt byte for byte with an external OFL font (`--ext nanumgothic-nhn=`, the hinted NanumGothicBold.ttf 3.021 of NAVER's original release, as Debian's `fonts-nanum` ships it) | NGOTB17, NGO17X1, NGO17X2 (`--mono-hint`), NGO15X2, NGO16BX2, NGO21AX2 (two glyphs from it with `--fallback-ttf`) | 6 |
| rebuilt, one glyph differs | NEODG16 (the shipped face also has U+212B, which neodgm.ttf lacks), NGOTB16 (also U+3000, which this NanumGothic-Bold.ttf lacks); every other glyph identical | 2 |
| documented only (no recipe with this repository's tools) | see [Faces without a recipe](#faces-without-a-recipe) | 63 |

### The precomposed recipe (`mkfont` rows)

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

### The jamo-set-from-precomposed recipe (`jamoset` rows)

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf $OUT/PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf $OUT/PRE.svf --mask-font none -o $OUT/NEODG16A.SVF --layout 844

`--from-svf` decomposes the precomposed syllables of a 1 bpp face into the pieces of a set system (here 8x4x4) and keeps
its other glyphs. Neo Dunggeunmo is itself drawn as an OR of 8x4x4 pieces, so the fit is exact (IoU 1.000) and every one
of the 11,172 syllables composes. NEODG16D/E/F/32/32A are the same with other cells (22x22, 18x24, 20x24; 32 px in
36x36 and 46x54). NEODG16G is the 6x2x1 set system (`--layout 621 --advance 0 --check`, no `--ascent`/`--clip-cell`:
mkfont's ascent 12), 10,684 bytes: a small face for the MCU examples (IoU 0.958 against the precomposed bake).

### Families

| Family | Faces | Upstream, version | Licence | Recipe status |
|---|---|---|---|---|
| NanumGothic Bold | NGOTB*, NGO*X? | Google Fonts `ofl/nanumgothic` (3.020), in `ttf/nanumgothic`; NHN original 3.021 for the 1 bpp hinted faces | OFL 1.1, RFN "Nanum", "NanumGothic" ... | verified (16 + 6 external), NGOTB16 one glyph |
| Gowun Batang Bold | GBATB*, GBA*X? | https://github.com/yangheeryu/Gowun-Batang (Google Fonts `ofl/gowunbatang`, 2.000), in `ttf/gowunbatang` | OFL 1.1 | verified (16); GBATB17O documented only |
| Neo Dunggeunmo | NEODG*, NEO16BX2 | https://github.com/neodgm/neodgm v1.601, in `ttf/neodgm` | OFL 1.1, RFN "Neo둥근모", "NeoDunggeunmo" ... | verified (5 precomposed, 7 jamo sets), NEODG16 one glyph; NEODG16B/C/O documented only |
| Black Han Sans | BHSAN28 | https://github.com/zesstype/Black-Han-Sans (1.001), in `ttf/blackhansans` | OFL 1.1 | verified |
| Coustard | COUSB24 | https://github.com/googlefonts/coustardFont (1.100), in `ttf/coustard` | OFL 1.1 | verified |
| Diphylleia | DIPHY36 | https://github.com/JAMO-TYPEFACE/Diphylleia | OFL 1.1 | documented only |
| Paperlogy | PAPLG16, PAPLG18, PAPER*, PAPLB* | https://freesentation.blog/paperlogy (designptn.com), 1.000 | OFL 1.1 | documented only |
| MaruBuri | MARU* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 | documented only |
| NanumSquareRound | NSQR* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 (NAVER's Nanum licence) | documented only |
| Gothic A1 | GOTHB18A, GOTHA*, GOTHB* | HanYang I&C (Google Fonts `ofl/gothica1`, 2.50) | OFL 1.1 | documented only |
| Single Day | SGDAY* | DXKorea (Google Fonts `ofl/singleday`, 1.00) | OFL 1.1 | documented only |
| Neo Dunggeunmo Pro | NDGPR* | https://github.com/neodgm/neodgm-pro 1.020 | OFL 1.1 | documented only |

Every face keeps its licence text beside it in `svf/` (`web/LICENCES.tsv` names it); the notes `svf/dos/*.TXT` and
`svf/jamo-extra/FACES.TSV` describe each face.

### Faces without a recipe

These faces are kept as built; the row of `tools/build/faces.tsv` says why. None of the reasons is a licence question:
the source fonts are OFL, only the making step is not in this repository or not reproducible here.

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

## Reference

### KS X 1001

KS X 1001 (formerly KS C 5601) has 2,350 precomposed Hangul syllables (rows 0xB0-0xC8, 94 each), 51 compatibility jamo
(row 0xA4: U+3131..U+3163), symbols and Hanja. Tools:

- `mkfont.py --unicode` names: `ksx1001-hangul` (the 2,350), `ksx1001-nohanja` (symbols, jamo and the 2,350),
  `ksx1001-symbols`, `ksx1001` (with Hanja), `hangul` / `cp949-hangul` (all 11,172), `cp949` (everything CP949 decodes),
  `jamo` (U+3131..U+318E, 94); `--limit` intersects a `--chars-from` list with any of them, `--require` refuses a
  code point the font lacks.
- `jamoset.ks_x_1001_syllables()` (syllable indices) and the quality reports (`ks2350` columns) use the same set.
  `tools/test_recipes.py` checks that both equal the euc_kr codec's rows.
- A jamo set composes all 11,172 syllables; compatibility jamo are drawn by a piece when the table names one, else by
  a whole glyph. `jamoset.py --blank-compat` rewrites a face to use whole glyphs where it has them.
- `facecheck.py` checks faces against a manifest (`verify`) and maps (`mapfaces`); coverage per face is in the web
  index (`web/mkindex.py`: `hangul` = KS syllables drawn, `subset` = fewer than the 2,350).

### Encodings

EUC-KR / wansung byte pair = GL code + 0x8080 (`가` = B0A1 = GL 3021); Python: `bytes((0xB0,0xA1)).decode("euc_kr")`.
Johab (KS X 1001 annex 3, `johab` codec): a 16-bit code `1 iiiii mmmmm fffff` with fill values (initial 2 = ㄱ, medial 3 =
ㅏ, final 1 = none), `가` = 8861; `bytes((0x88,0x61)).decode("johab")`. Unicode syllable = 0xAC00 + (initial x 21 + medial)
x 28 + final with 0-based jamo indices. Synthetic (`tools/test_recipes.py`).

### Known limits

- The default `--binarize mono` of `jamoset.py` needs `freetype-py` (and `--mask-font` also `uharfbuzz`): neither is
  installed on this host (`cannot import freetype`), so the recipes use `--binarize threshold`, and `--mask-font none`
  keeps a 1 bpp fit independent of `$JAMOSET_MASK_FONT`; see [Jamo sets](#jamo-sets-from-truetype-and-opentype-fonts).
- Run time (this host, one core): a 1 bpp `threshold` fit of a 16 px outline font about 12 s, a 2 bpp one about 73 s,
  Gowun Batang adaptive at 20 px about 90 s. A 2 bpp face is about 1.5-1.6x its 1 bpp face; a jamo set about a sixth.
- No tool makes a 2 bpp face from a bitmap or a 1 bpp face of the same size; `svfscale.py --bpp 2` makes one at a smaller
  size ([A low-resolution face from a high-resolution bitmap font](#a-low-resolution-face-from-a-high-resolution-bitmap-font)), and no tool makes a 2 bpp jamo set from a bitmap.
- `mkfont.py` prints its summary in Korean: do not parse its stdout for field names.
- Known gaps of the tools in general: [tools.md](tools.md#remaining-gaps-of-the-tools), "Remaining gaps of the tools".

## Adding a face to svf/

Make the face with a recipe above, check it ([Checking a face](#checking-a-face)), and add:

- its licence text beside it in `svf/`;
- a row in `web/LICENCES.tsv` and one in `web/FAMILIES.tsv`;
- a row in `tools/build/faces.tsv` (with a recipe, or method `none` and the reason).

`tools/test_build_faces.py` and `tools/test_web_picker.py` fail otherwise. The maker writes ready-made lines for these
tables (`build-<id>/LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`).
