**English** | [한국어](outline-fonts.ko.md)

# Recipes: Outline fonts

TrueType and OpenType fonts (TTF, OTF with CFF outlines, TTC/OTC, variable fonts, Mac-format TrueType) to precomposed faces and jamo sets: jamo sets fitted to the font or read from its own jamo glyphs, 2 bpp anti-aliased faces, and the baseline, vertical shift and clipping every outline route shares.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The outline routes need Pillow and fontTools in the selected Python environment (the jamo tools also take `--pylib DIR`).

Up: [Recipes index](../recipes.md) · Related: [Choosing the number of sets (벌 수)](sets.md), [Existing SVF faces, and SVF back to TTF](svf-and-ttf.md), [Jamo sets](../jamo-sets.md), [Jamo splitting](../jamo-split.md), [Anti-aliasing](../anti-aliasing.md).

<a id="outline-fonts"></a>

## Outline fonts

FreeType reads TrueType and CFF (OpenType `.otf`) alike, so a static TTF or OTF with a Unicode cmap goes straight into
the tools; `jamoset.py --from-ttf`, `jamoaa.py`, `jamovec.py` and `--binarize threshold|ridge` flatten the outlines
themselves (fontTools pen, exact-area coverage), the same for both. Collections, variable fonts and Mac-format fonts need
one step first (below).

<a id="precomposed-faces-mkfontpy"></a>

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
[The precomposed recipe](svf-faces.md#the-precomposed-recipe-mkfont-rows).

**A character set is required** (`--unicode SET`, or `--chars-from FILE`): without either, `mkfont.py` exits 2. The names
are in [Reference](../recipes.md#reference).

<a id="opentype-cff-otf"></a>

### OpenType CFF (`.otf`)

Noto Sans CJK KR is a CFF font a reader can get (SIL OFL 1.1; Debian's `fonts-noto-cjk` ships it as
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`, a collection of the KR, JP, SC, TC and HK faces: see
[TTC and OTC](#ttc-and-otc)). Save the KR face as a plain `.otf` and bake it ([Font sources and licences](../recipes.md#ref-fonts)):

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

### Jamo sets from TrueType and OpenType fonts

A jamo set (조합형) holds pieces and a table. At 1 bpp, a composed syllable is the OR of two or three pieces;
at 2 bpp, composition takes the maximum level at each pixel. See [Jamo sets](../jamo-sets.md). From an outline font there
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

### TrueType fonts that already carry jamo

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

### 2 bpp anti-aliased faces from a TrueType/OpenType font

<a id="anti-aliased-2-bpp-faces"></a>

A 2 bpp face stores four levels per pixel (0, 1, 2, 3; coverage = level × 85). The outline-font routes below
produce these levels from rasterised outlines. A monochrome bitmap has only coverage 0 and 255 at its own size;
a grayscale bitmap may already have intermediate coverage. Downsampling a larger bitmap can also produce intermediate
levels ([A low-resolution face from a high-resolution bitmap font](bitmap-fonts.md#a-low-resolution-face-from-a-high-resolution-bitmap-font)).
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
and the set system (`--layout 844` or `adaptive[:NI,NM,NF]`, [Choosing the number of sets](sets.md#choosing-the-number-of-sets)).
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
([The precomposed recipe](svf-faces.md#the-precomposed-recipe-mkfont-rows)) on the target before choosing. Bake at the size the
target draws rather than scaling a face at draw time. Check every result by its numbers (ink, the levels, and for a
jamo set the `aa:` line's level error and IoU at level 2) and by looking at it: `svfline.py line` writes GRAY8, and the
`web/` picker shows a face at its levels.

**Pitfalls.** An anti-aliased piece over another piece takes the maximum, not the sum: crossing strokes can look lighter
than in the precomposed glyph. A monochrome target (`SVF_T_MONO_PAGE` or `SVF_T_MONO_ROW`) thresholds 2 bpp faces at draw time (`svf_target.mono_threshold`, default 128); give a mono display a 1 bpp face. `--bpp 8` (mkfont only) keeps full coverage for hosts.

Background (coverage, gamma, why no subpixel rendering), the level-to-colour rules of each target, the maximum against
OR in jamo sets, and a table of which bpp to choose: [Anti-aliasing](../anti-aliasing.md). For previewing, see the
[web renderer guide](../web-renderer-guide.md).

<a id="baseline-vertical-shift-and-clipping"></a>

### Baseline, vertical shift and clipping

The ascent field is the baseline row measured from the cell top. At scale 1, the C renderer places the cell top at
`y_baseline - ascent + dy`: positive per-glyph `dy` moves it down. See [SVF metrics](../../spec/SVF.md) and the
[C renderer guide](../c-renderer-guide.md).

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

### TTC and OTC

<a id="opentype-cff-collections-and-variable-fonts"></a>

`mkfont.py` opens index 0 of a collection (synthetic: a TTC of Galmuri9 + Galmuri7 bakes exactly as Galmuri9). For
another face, save it out as a plain font first (the same step the maker's `ttc-face` does; TrueType or CFF faces alike; name the output `.otf` for a CFF face, as the OpenType CFF recipe above does):

    python3 maker/srcprep.py ttc-face F.ttc $OUT/F1.ttf --index 1

Pick by name, not by position: in the Noto CJK collections KR is not index 0. List the names:

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; [print(i, f['name'].getDebugName(4)) for i, f in enumerate(C('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').fonts)]"

Verified on the host's Noto Sans CJK Regular collection: ten faces, index 0 Noto Sans CJK JP, 1 KR, 2 SC, 3 TC, 4 HK, then 5-9 Noto Sans Mono CJK JP, KR, SC, TC, HK. The face then goes into the recipes as any static font
([OpenType CFF](#opentype-cff-otf) above is exactly this).

<a id="variable-fonts"></a>

### Variable fonts

`mkfont.py` draws the default instance. For another, cut a static instance first (fontTools, the maker's `instance`
step) ([fontTools variable-font instancer](../recipes.md#ref-fonttools)):

    python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o $OUT/Caveat-Bold.ttf
    python3 tools/mkfont.py $OUT/Caveat-Bold.ttf $OUT/CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/mkfont.py ttf/caveat/Caveat-VF.ttf $OUT/CAV24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAVB24.SVF     # one face per call: several faces are a fallback chain
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAV24.SVF

Verified: the default instance (Regular 400) bakes to 6,760 bytes and the 700 instance to 7,192 bytes (95 glyphs each,
"Hamburgefonstiv" 141 px wide in the Bold, 136 in the Regular; the summary's one omitted code point is a requested one the font lacks). Named instances are in the `fvar` table (`Caveat`: Regular, Bold; `EB Garamond`: Regular ..
ExtraBold).

<a id="mac-format-truetype"></a>

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
strikes](bitmap-fonts.md#embedded-bitmap-strikes)); at 17 px, which has no strike, the outline is rasterised (`125,164 bytes`, 2,444
glyphs: two code points the outline lacks are left out, `width=164 ascent=14 descent=3`). The maker reads the resource fork
directly: `detect.scan` on `Seoul[FFIL]` gives kind `outline`, label "resource fork: sfnt 17408; bitmap strikes 9, 10, 12,
14, 16, 18, 20, 24; Mac Korean cmap", routes `mkfont`, `experimental fit` and `vector fit`. The classic bitmap fonts of the
Korean Mac are in [Classic Mac Korean bitmap fonts](classic-mac.md#classic-mac-korean-bitmap-fonts).

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
