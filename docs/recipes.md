# Recipes: from a font to an SVF face

How the faces of `svf/` are made from their upstream fonts, and how to make faces from other kinds of Korean fonts with
the tools of this repository. Every tool is described in [tools.md](tools.md); the format is `spec/SVF.md`.

No font data other than the OFL fonts in `ttf/` and the faces in `svf/` is in this repository. The how-tos for
proprietary fonts (classic Mac, HWP, other DOS-era fonts) describe the method and the commands; you supply the files.
The how-tos marked **verified** were run as written; their tests are `tools/test_recipes.py`, `tools/test_build_faces.py`
and `tools/test_macsfnt.py` (synthetic fonts built in the test, and OFL fonts from `ttf/`). Numbers quoted below come
from real runs on 2026-11-03 (outputs in `/tmp`); anything not run says so.

Contents:

- [Rebuilding the faces of svf/](#rebuilding-the-faces-of-svf)
- [Jamo sets from TrueType and OpenType fonts](#jamo-sets-from-truetype-and-opentype-fonts)
- [Anti-aliased (2 bpp) faces](#anti-aliased-2-bpp-faces)
- [Baseline, vertical shift and clipping](#baseline-vertical-shift-and-clipping)
- [Classic Mac Korean bitmap fonts](#classic-mac-korean-bitmap-fonts)
- [HWP 1.x and 2.x fonts](#hwp-1x-and-2x-fonts)
- [Other DOS-era Korean fonts](#other-dos-era-korean-fonts)
- [X Window Korean fonts](#x-window-korean-fonts)
- [KS X 1001](#ks-x-1001)
- [Mac-format TrueType](#mac-format-truetype)
- [OpenType CFF, collections and variable fonts](#opentype-cff-collections-and-variable-fonts)
- [Checks for a new face](#checks-for-a-new-face)

## Rebuilding the faces of svf/

`tools/build/faces.tsv` holds one row for every face of `svf/` (116 rows); `tools/build/build_faces.py` runs them and
compares each result with the shipped face:

    python3 tools/build/build_faces.py --out /tmp/rebuild                      # every row with a recipe
    python3 tools/build/build_faces.py --out /tmp/rebuild NGOTB15 GBATB23      # some faces
    python3 tools/build/build_faces.py --out /tmp/rebuild --ext nanumgothic-nhn=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf

Each line of the output is `FACE identical`, `FACE pixels` (same glyphs and header values, another byte order) or
`FACE differs: ...`; the run exits 1 when a row marked `identical` is not.

**Coverage (verified, 2026-11-03).** 116 faces:

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

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf PRE.svf -o NEODG16A.SVF --layout 844

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

## Jamo sets from TrueType and OpenType fonts

A jamo set (조합형) holds pieces and a table; every syllable is the OR of two or three pieces. From an outline font there
are three ways to get the pieces, by what the font holds.

**1. Composite glyphs (TrueType `glyf`).** Some fonts store a syllable as a composite of its jamo glyphs. Then the
components *are* the pieces:

    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o neodgm.json --components
    python3 tools/jamovec.py render neodgm.json --size 16 --bpp 1 --check -o NEOVEC16.SVF
    python3 tools/jamovec.py render neodgm.json --size 16 --bpp 2 --check -o NEOVEC16A.SVF

Verified: neodgm.ttf has 11,172 composite syllables; `master` took 25 s (344 pieces, 0 bad shapes), the 1 bpp render
15,724 bytes and the 2 bpp render 19,452 bytes, both 11,172 syllables composed. The vector render differs from the
raster fit NEODG16A in 2,633 of 11,172 syllables (FreeType's pixel snapping of a pixel font against `jamovec`'s exact-area
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
`--pylib DIR` points at them). Not run here (neither module is installed on this host); neodgm.ttf in `ttf/` has the three
features and can serve as a mask font. A separate research repository measured the pieces those features return, at
12 px with hinting: Malgun Gothic gives 5/2/1 sets (164 pieces), Noto Sans CJK KR 6/2/4 (264 pieces; in the Noto TTC,
KR is index 1); faces made straight from them read well but differ from the precomposed glyphs by a pixel or two (mean
IoU about 0.58), because the font's conjoining pieces are laid out differently from its precomposed syllables. That work
also found that in the same byte budget a few dozen frequent syllables stored as LIST exceptions (`jamoexc.py`) improve
more than more sets do. No data of those fonts is in this repository.

**3. Fitting to the precomposed syllables** (any font, TrueType or CFF):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 \
        --binarize threshold --check -o NG16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-ttf ttf/gowunbatang/GowunBatang-Bold.ttf --size 20 \
        --binarize threshold --check -o GB20J.SVF

Verified: NanumGothic Bold 16 px into 8x4x4 took 12 s, 20,064 bytes, 344 pieces, IoU 0.817 over 11,172 syllables;
Gowun Batang Bold 20 px adaptive took 92 s, 73,220 bytes, 32/24/12 sets and 12 x 12 classes, IoU 0.934. `jamofit.py`
fits the pieces (coordinate descent over the 1 bpp syllables), `jamoadapt.py` splits sets where the syllables sharing a
piece disagree (`--layout adaptive[:NI,NM,NF]`), `jamoseg.py` separates a syllable's outline into its jamo as outlines
(used by `jamoaa.py` and `jamovec.py`), and `jamovec.py master` without `--components` separates once at a decision size
and renders every size from the same pieces. `--binarize mono` (the default) needs freetype-py; `threshold` and `ridge`
use the repository's own exact-area rasteriser (fontTools pen, so TrueType and CFF alike). A fit is an approximation:
read the IoU, and look at the result (`web/` picker, or `svfline.py line`).

**Pitfalls.** A font that draws few syllables (Black Han Sans: 2,581) fits only those (`--present-only`, the default);
the rest compose from the nearest pieces. `--check` composes all 11,172 syllables and fails on a table error, not on
a poor fit.

## Anti-aliased (2 bpp) faces

Precomposed (verified, `tools.md` "Recipes"): `mkfont.py FONT OUT --size 16 --bpp 2 --unicode ascii,ksx1001-hangul`
(NanumGothic Bold: 185,932 bytes, 2,446 glyphs). Coverage is quantised to 4 levels; the reader expands level x 85. A
2 bpp face is about 1.7x its 1 bpp face. `--bpp 8` keeps full coverage (8 bpp faces are for hosts).

Jamo sets:

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 --bpp 2 \
        --check -o NG16JA.SVF                     # verified: 73 s, 24,960 bytes, level error 0.233, IoU at level 2 0.822
    python3 tools/jamovec.py render MASTER.json --size 16 --bpp 2 -o OUT.SVF      # from a vector master

`--bpp 2` runs `jamoaa.py`: the syllables are rasterised with exact-area coverage, the regions of the 1 bpp fit decide
which piece owns each pixel, and each piece's levels are the median over the syllables sharing it, then refined
(`--aa-refine N`, 2 passes) against the level error. `--clean` (on for 2 bpp) removes isolated noise. The pieces OR as
the per-pixel maximum. 2 bpp needs fontTools only.

**Pitfalls.** An anti-aliased piece over another piece takes the maximum, not the sum: thin crossing strokes look lighter
than in the precomposed glyph. A 1 bpp target (MONO_PAGE) thresholds 2 bpp faces at draw time (`threshold` of the
target); give a mono display a 1 bpp face.

## Baseline, vertical shift and clipping

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

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf c.svf --size 18 --cell 16 --bpp 1 \
        --unicode ascii,ksx1001-hangul [--clip-cell | --fit-cell | --ascent 14 --clip-cell]

| Options | Ascent | Result |
|---|---|---|
| none | 13 (ink centred) | glyphs moved into the cell one by one, 126,048 bytes |
| `--clip-cell` | 15 (fewest glyphs cut) | 2,300 of 2,445 glyphs cut (368 at the top, 2,299 at the bottom) |
| `--ascent 14 --clip-cell` | 14 | 2,327 cut (2,321 top, 36 bottom) |
| `--fit-cell` | 13, at 15 px | 0 cut, 118,116 bytes |

`tools/fontmetrics.py FACE.SVF` lists glyphs whose ink reaches past their advance (here one, `\`). To lower descenders
(or raise a glyph) after the fact, set a per-glyph dy:

    python3 tools/svfdy.py IN.SVF OUT.SVF --range 0x67,0x6a,0x70,0x71,0x79 --dy 1    # g j p q y one row lower
    python3 tools/svfdy.py OUT.SVF --show

`--dy` moves the glyph at draw time; the face's dy range (header bytes 17/18) widens, and a line's descent grows by it.
An engine without dy support draws those glyphs at their cell position.

**Pitfalls.** A cell smaller than the font's line pitch always cuts something: prefer `--fit-cell`, or a larger cell
with a fixed advance. Changing the ascent of a face changes where every line's ink lands (the MCU examples place a
line's baseline at its top row + the face's ascent).

## Classic Mac Korean bitmap fonts

No Apple data is in this repository; the tools read your own files. The maker's local mode (`maker/README.md`, "Local
mode") reads these fonts in place from your disk, through the same tools, and writes the faces only into a folder you
choose.

**HangulTalk 1.0 'fbit' fonts** (Korean System 4.1: Gotic12/16, Munjo12/16/24). Input: the font's resource fork as a
file (copied out of a Mac volume, or the fork of an archive; `tools/macsfnt.py list` shows its 'fbit' resource). The
fork holds an 'fbit' resource of 45 glyph sets and the 'fdef' driver resource with its 18 lookup tables. The set system is
derived from the font's own rule, so every syllable composes as the Mac draws it:

    python3 tools/jamoset.py --layout mac-fbit-45sets Munjo24.rsrc --symbols --check -o MUNJO24J.SVF

Output: a 1 bpp jamo set of all 11,172 syllables (8 lead classes, 4 tail classes, 20 initial sets for these fonts),
cell = the font's size. `--check` composes everything and compares with jamoset's own copy of the 'fdef' rule; a golden
file (`tools/testdata/mac-fbit-golden.json`, not shipped: it would hold Apple bitmaps) adds an independent comparison
when you make one. Tests on the real files run when `JOHAB_FONTS` names a tree holding
`mac/extracted/kh10_system_disk/System Folder/*.rsrc` and the reference renderer; they skip otherwise.

**HangulTalk 7.1.x type-3 'fbit' fonts** (Seoul12, AppleGothic12/24, AppleMyungjo12/24): the planes are composed by a
table, InputBackSupport 'HTBL' 1, and only the 2,350 KS X 1001 syllables and 51 compatibility jamo exist.

    python3 tools/macfbit3.py unpack Seoul12.splt.data Seoul12.rsrc     # the 7.1.2 Installer's 'splt' "JM" archive
    python3 tools/macfbit3.py fbit Seoul12.rsrc Seoul12.fbit
    python3 tools/macfbit3.py bdf Seoul12.fbit HTBL1.bin Seoul12 seoul12.bdf          # 2,401 glyphs, Unicode BDF
    python3 tools/macfbit_svf.py build Seoul12.fbit HTBL1.bin -o SEOUL12J.SVF         # direct: the Mac structure (JMAP)
    python3 tools/macfbit_svf.py build Seoul12.fbit HTBL1.bin --mode derived -o SEOUL12D.SVF   # a JSET face, all 11,172
    python3 tools/macfbit_svf.py verify SEOUL12J.SVF Seoul12.fbit HTBL1.bin

`direct` keeps the Mac planes as pieces and composes only the KS syllables exactly; `derived` fits a JSET whose 8,822
extra syllables are extrapolated (not Mac output). The BDF route goes on with `bdfface.py --cell 12x12 --chars-from
<the 2,350 syllables>` to a precomposed face. To shrink a many-variant face for an MCU budget:

    python3 tools/jamomerge.py merge --face SEOUL12D.SVF --points 8192 7168 --prefix SM -o OUTDIR

(keeps every piece as drawn and merges variants, sets and classes by a pixel objective). Tests: `tools/test_macfbit3.py`
and `tools/test_macfbit_svf.py` run on synthetic fbit / HTBL / NFNT data built in the tests; `MACFBIT3_CD712=<CD tree>`
and `SVF_MAC71_INPUTS=<dir of Name.fbit and Name.htbl1>` add the checks on your files. Outline Mac TrueType fonts: see
[Mac-format TrueType](#mac-format-truetype).

## HWP 1.x and 2.x fonts

Hangul and Computer's DOS word processor shipped printer and screen fonts (`HANGUL*.PFT`, `ASCII.PFT`, `*.FNT`). What
this repository reads directly:

- the 12x24 English fonts: `jamoset.py ... --eng ASCII.PFT` (12,288 bytes, 256 glyphs of 48 bytes) and HBIOS 12x24
  (15,360 bytes);
- any precomposed 1 bpp face you made of the Hangul, refitted to pieces: `jamoset.py --layout 844 --from-svf
  FACE.SVF --check` (for the HWP 1.20 24 px faces this fit was exact);
- a BDF of the composed syllables: `bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf --cell 24x24 --chars-from LIST`.

What it does **not** read: the HWP `.PFT` Hangul files themselves. Their glyphs are composed by HWP's own rules, which
a separate research tool (`kfont.py` of the johab-fonts research notes) decodes; that reader is not part of this
repository, and its output (a BDF or a precomposed face) is the input of the two routes above. No HWP font is in this
repository.

## Other DOS-era Korean fonts

DOS Hangul systems (Hangul BIOS, 이야기, 한메, san, Dokkaebi, games) stored jamo pieces, not syllables; a syllable was the
OR of an initial, a medial and an optional final, the set chosen by the other jamo. `jamoset.py` reads these raw files
by size and layout and writes a jamo set whose tables reproduce the original selection rules:

| `--layout` | File | Bytes | Pieces |
|---|---|---|---|
| `844` | raw 8x4x4 (`HANGUL.FNT`, `*.KOR`, `$K*ZN16`), 16/24/40/48 px | 11,520 (or 11,522 with a 2-byte header), 25,920, 72,000, 103,680 | 360: 8 initial sets of 20, 4 medial of 22, 4 final of 28; slot 0 of each set blank |
| `844-ihnm` | SAGA IHNM 8x4x4 (medial sets swapped for ㄱ ㅋ) | 11,520+ | 360 |
| `844-hbios24` | HBIOS / Taebaek 3.5 24x30 (`GOTHIC24.FNT`, `MY24.FNT`) | 243,900 | the first 360 |
| `1044-san` | san 1.0 10x4x4 | 12,800 | 400 |
| `621` | 6x2x1 (Apple II era), byte-column glyphs | 6,144 | 192 |
| `dkb-printer-7x2x2` / `dkb-printer-12x4x4` | Dokkaebi printer `HANGUL16/24.FNT` / `HANGUL40/48.FNT` (`--face 0|1`) | 15,360 / 34,560; 176,000 / 253,440 | 240 / 440 a face |
| `kyra-lok` | Kyra LoK `MK15.BIT`, 15x15 | 11,550 | 385 |

    python3 tools/jamoset.py --layout 844 HANGUL.FNT --eng ENGLISH.FNT --symbols --check -o MYFONT16J.SVF
    python3 tools/johab844.py HANGUL.FNT svf/dos/NEODG16.SVF MYFONT16.SVF --eng ENGLISH.FNT     # precomposed instead

`--eng` takes a raw 8x16 English font (2,048 or 4,096 bytes; scaled by whole numbers to the cell) for ASCII; `--base
FACE.SVF` keeps another face's non-syllable glyphs. The ascent defaults to 7/8 of the cell (`--ascent N`); 8x16 DOS
fonts put the baseline at row 13 or 14. `--check` composes all 11,172 syllables. `johab844.py` redraws the syllables of a
16x16 1 bpp base with the raw pieces and keeps the base's other glyphs. Verified on synthetic files built in
`tools/test_recipes.py`: a raw 8x4x4 font with an 8x16 English font (가 composed = the OR of raw slots 1 and 161, byte
for byte), a 6x2x1 font (1 lead / 2 tail classes, 6/2/1 sets), and a refit of a precomposed face (`--from-svf` over
NEODG16J, IoU 1.000).

**Pitfalls.** A file of the right size in another layout passes the size check; `jamoset.py` refuses it when the slot-0
fill pieces are not blank, but look at the result (`svfline.py line ... "가나다"`). Fonts with a 2-byte header
(T-Hangul) are read at offset 2. A 24 px or larger source needs a matching English font or `--base`.

## X Window Korean fonts

**hanterm** (johab-1 encoding, glyph numbers as `ENCODING`, 10x(3|4)x4 sets, 529 glyphs):

    python3 tools/jamoset.py --layout hanterm-johab johabm16.bdf --check -o HTERM16J.SVF

**KS X 1001 (wansung) BDF/PCF** (`CHARSET_REGISTRY "KSC5601.1987"` or `"KSX1001"`, `ENCODING` = the GL code,
e.g. `-baekmuk-*`, `-daewoo-*`, `hanglm16.bdf`) or Unicode BDF (`ISO10646`): precomposed through `bdfface.py`, then a
jamo set through `--from-svf`:

    python3 tools/bdfface.py --hangul hanglm16.bdf --ascii 8x16.bdf --cell 16x16 --chars-from CHARS.txt -o KS16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf KS16.SVF --check -o KS16J.SVF

`--chars-from` names the syllables to take (any text; `mkfont.py`'s rules), `--ascent` / `--hangul-ascent` place the
baselines. Verified on synthetic BDFs (`tools/test_recipes.py`): a KS C 5601 BDF of 10 syllables and an ISO 10646 ASCII
BDF give a face with exactly those syllables, rows in place; a synthetic hanterm BDF of 529 glyphs composes all 11,172
syllables in 10/4/4 sets.

**PCF.** `bdfface.py` and the hanterm reader read BDF only. Convert with an external tool, e.g. `pcf2bdf` (Debian package
`pcf2bdf`): `pcf2bdf -o font.bdf font.pcf.gz` (not run here: not installed on this host). `mkfont.py` reads a PCF or BDF
directly through FreeType, at its built-in pixel size only (tools.md "Recipes", PCF).

**Encodings.** EUC-KR / wansung byte pair = GL code + 0x8080 (`가` = B0A1 = GL 3021); Python: `bytes((0xB0,0xA1)).decode
("euc_kr")`. Johab (KS X 1001 annex 3, `johab` codec): a 16-bit code `1 iiiii mmmmm fffff` with fill values (initial 2 =
ㄱ, medial 3 = ㅏ, final 1 = none), `가` = 8861; `bytes((0x88,0x61)).decode("johab")`. Unicode syllable =
0xAC00 + (initial x 21 + medial) x 28 + final with 0-based jamo indices. Verified in `tools/test_recipes.py`.

## KS X 1001

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

## Mac-format TrueType

**Resource-fork fonts** (.dfont, suitcases, a fork copied out of HFS): the TrueType data is an 'sfnt' resource.

    python3 tools/macsfnt.py list Font.dfont                 # type, id, name, bytes of sfnt / NFNT / FOND / fbit
    python3 tools/macsfnt.py extract Font.dfont Font.ttf [--id N]

`macsfnt.py` also unwraps AppleDouble (`._Font`) and MacBinary files. FreeType opens a .dfont directly as well, so
`mkfont.py Font.dfont ...` works for the first face of a Unicode-mapped font (verified on a synthetic .dfont).

**Mac Korean cmaps.** A font for the Korean Mac (and some Windows fonts) has only a platform 1 / script 3 (Mac Korean) or
platform 3 / encoding 5 (Wansung) cmap: two-byte KS X 1001 codes. FreeType and the SVF tools select a Unicode cmap, so
such a font draws nothing until it has one:

    python3 tools/macsfnt.py cmap Font.ttf                   # platform=1 encoding=3 format=2 entries=... hangul=...
    python3 tools/macsfnt.py unicode Font.ttf FontU.ttf      # adds (3,1) format 4 [+ (3,10) format 12]

Each code is decoded as EUC-KR (KS X 1001); Apple's own additions to Mac Korean have no KS X 1001 meaning and are counted
as unmapped. Verified (`tools/test_macsfnt.py`): a synthetic font with only a (1,3) format 2 cmap is listed, extracted
from a resource fork, AppleDouble and MacBinary, gains a Unicode subtable, and `mkfont.py` then draws its syllable.

**TTC.** `mkfont.py` opens index 0 of a collection (verified: a TTC of Galmuri9 + Galmuri7 bakes exactly as Galmuri9).
For another face, save it out first:

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; C('F.ttc').fonts[1].save('F1.ttf')"

Pick by name (`fonts[i]['name'].getDebugName(4)`), not by position: in the Noto CJK collections KR is not index 0.

**Embedded bitmaps (`bdat`/`bloc`, `EBDT`/`EBLC`).** FreeType uses a strike only at its own pixel size: run `mkfont.py
--size N` with the strike's size and `--bpp 1`; at other sizes the outlines are used, or the open fails for a bitmap-only
font (`OSError: invalid pixel size`). Not run here (no such font in `ttf/`).

## OpenType CFF, collections and variable fonts

- **Rasterising.** `mkfont.py` draws with Pillow's FreeType binding: anti-aliased coverage (cut at 128 for 1 bpp, or
  quantised for 2 bpp), or with `--mono-hint` FreeType's monochrome renderer with the font's hinting
  (`FT_LOAD_TARGET_MONO`). FreeType reads TrueType and CFF/CFF2 alike (OTF needs no conversion). `jamoaa.py` /
  `jamovec.py` / `--binarize threshold|ridge` flatten the outlines themselves (fontTools pen, curves flattened, exact-area
  coverage), the same for TrueType and CFF.
- **CFF has no composite glyphs**, so a jamo set from an OTF comes from GSUB shaping (mask font) or from fitting; see
  [Jamo sets from TrueType and OpenType fonts](#jamo-sets-from-truetype-and-opentype-fonts).
- **OTC** collections: as TTC above.
- **Variable fonts.** `mkfont.py` draws the default instance. For another, cut a static instance first (fontTools, an
  external step):

      python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o Caveat-Bold.ttf
      python3 tools/mkfont.py Caveat-Bold.ttf CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin

  Verified: the default instance (Regular 400) bakes to 6,760 bytes and the 700 instance to 7,192 bytes (95 glyphs each,
  "Hamburgefonstiv" 136 vs 141 px wide). Named instances are in the `fvar` table (`Caveat`: Regular, Bold; `EB Garamond`:
  Regular .. ExtraBold).
- **Feeding the recipes.** Any of these, once a static TrueType or CFF font with a Unicode cmap, goes into `mkfont.py`
  (precomposed), `jamoset.py --from-ttf` / `jamovec.py` (jamo sets), or `mkfont.py` then `jamoset.py --from-svf`.

## Checks for a new face

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF       # width, ascent, descent
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > out.gray
    python3 tools/fontmetrics.py FACE.SVF                                 # ink past the advance
    python3 tools/svf2to3.py FACE.SVF /tmp/x.SVF --check                  # re-layout and compare every glyph
    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf -o /tmp/m.tsv

A face added to `svf/` needs its licence text beside it, a row in `web/LICENCES.tsv` and `web/FAMILIES.tsv`, and a row in
`tools/build/faces.tsv` (with a recipe, or `none` and the reason); `tools/test_build_faces.py` and
`tools/test_web_picker.py` fail otherwise.
