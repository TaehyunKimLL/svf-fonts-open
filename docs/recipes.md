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
([Precomposed faces](recipes/outline-fonts.md#precomposed-faces-mkfontpy)). Other target profiles are described in the
[renderer design](../spec/renderer-design.md).

Numerical examples are measurements for the named inputs and settings. Sizes and run times can change with tool and
font versions. *Synthetic* examples use test-generated inputs. A fit's IoU comes from the fit report; `--check` checks
composition and table consistency, without imposing a minimum IoU.

Contents:

- [Recipe documents](#recipe-documents)
- [Quick start: by input kind](#quick-start-by-input-kind)
- [Checking a face](#checking-a-face)
- [Reference](#reference)
- [References](#references)
- [Moved sections](#moved-sections)

<a id="recipe-documents"></a>

## Recipe documents

Each recipe document covers one kind of source, with its commands and measured results. The quick start below names the document and section for every input kind; the checks, the KS X 1001 and encoding reference and the references are on this page.

| Document | Covers |
|---|---|
| [Outline fonts](recipes/outline-fonts.md) | TTF, OTF, TTC/OTC, variable and Mac TrueType fonts; jamo sets from outline fonts and from fonts that carry jamo; 2 bpp anti-aliasing; baseline and clipping |
| [Bitmap fonts](recipes/bitmap-fonts.md) | BDF/PCF (ISO 10646, KS C 5601), HBF, Windows FNT/FON, embedded strikes; a low-resolution face from a high-resolution bitmap font |
| [Korean fonts from X Window and Unix](recipes/x-window.md) | The X and Unix Korean fonts family by family: Daewoo, Baekmuk, Hanyang, KAIST, Mizi, jfbterm and zhcon (KS C 5601 BDF/PCF), hanterm's johab844-1 and johab-1 jamo-set fonts; licences and samples |
| [DOS-era raw fonts](recipes/dos-fonts.md) | Raw jamo-piece fonts (8x4x4, san, Dokkaebi, Kyrandia), HWP 1.x/2.x and 3.0 fonts, KS X 1001 raw dumps |
| [Fonts inside programs and drivers](recipes/programs-and-drivers.md) | Finding a font inside a program or data file with Claude: the tools, the prompt, NKP, Dokkaebi |
| [Korean VGA font ROMs (86Box)](recipes/rom-86box.md) | The Korean VGA font ROMs of the 86Box ROM set (Trigem, Kasan, ATI) |
| [Korean MSX fonts (MSX2 and MSX1)](recipes/rom-msx.md) | MSX2 Daewoo jamo set, CPC-400S precomposed font, MSX1 BIOS cells and the openMSX harvest |
| [Korean font ROMs in MAME sets](recipes/rom-mame.md) | MAME sets: the SPC-1500 jamo set, quiz-game sprite fonts, unresolved sets |
| [OS/2 Korean fonts (완성형)](recipes/os2.md) | OS/2 System DBCS fonts (완성형) to a precomposed face and a jamo set |
| [Classic Mac Korean bitmap fonts](recipes/classic-mac.md) | HangulTalk 1.0 and 7.1 `fbit` bitmap fonts |
| [Existing SVF faces, and SVF back to TTF](recipes/svf-and-ttf.md) | An existing SVF (dy, re-bake as a jamo set); an SVF face back to a TTF or BDF font, composite glyphs |
| [Choosing the number of sets (벌 수)](recipes/sets.md) | How many sets (벌) a jamo set should have, and what they cost |
| [Jamo splitting](jamo-split.md) | Background for every jamo-set fit: how a jamo set is fitted to a precomposed font, case by case, and what fits poorly |
| [Desktop app and maker routes](recipes/desktop-routes.md) | The maker's route table: each route and its command line |
| [Faces of svf/](recipes/svf-faces.md) | How the faces of svf/ are made and rebuilt; adding a face to svf/ |

<a id="quick-start-by-input-kind"></a>

<a id="1-quick-start-by-input-kind"></a>

## Quick start: by input kind

Find what you hold; the row names the way and the section with the commands. "Pre" is a precomposed face (every
syllable a glyph, 1 or 2 bpp), "jamo" a jamo set (pieces and a table, 1 bpp or 2 bpp; about a sixth of the size).

| You hold | Pre | Jamo | Section |
|---|---|---|---|
| TTF, or OTF (CFF) with a Unicode cmap | `mkfont.py` (1, 2 bpp), then `svf2to3.py --profile default` | `jamoset.py --from-ttf` (1 bpp: `--binarize threshold --mask-font none`; 2 bpp: `--bpp 2`); `jamovec.py` for a font of composite syllables | [Outline fonts](recipes/outline-fonts.md#outline-fonts) |
| TTC / OTC (Noto CJK) | `srcprep.py ttc-face` to a plain font, then as above | as above | [TTC and OTC](recipes/outline-fonts.md#ttc-and-otc) |
| Variable font | `fontTools.varLib.instancer`, then as above | as above | [Variable fonts](recipes/outline-fonts.md#variable-fonts) |
| Mac TrueType (`.dfont`, suitcase, a Korean-only cmap) | `macsfnt.py extract` / `unicode`, then as above | as above | [Mac-format TrueType](recipes/outline-fonts.md#mac-format-truetype) |
| Outline font with embedded strikes (`EBDT`, `bdat`) | `mkfont.py --size` the strike's size, 1 bpp | no | [Embedded bitmap strikes](recipes/bitmap-fonts.md#embedded-bitmap-strikes) |
| BDF or PCF in Unicode (`ISO10646`) | `mkfont.py` at the file's own pixel size, 1 bpp | fit with `jamoset.py --from-svf` | [ISO 10646 BDF and PCF](recipes/bitmap-fonts.md#iso-10646-bdf-and-pcf) |
| BDF or PCF in KS C 5601 / KS X 1001 (X Window) | `srcprep.py pcf-bdf` (PCF only), then `bdfface.py` (`--symbols` for the symbols) | `jamoset.py --from-svf` | [KS C 5601 BDF and PCF](recipes/bitmap-fonts.md#ks-c-5601-bdf-and-pcf); the fonts family by family: [Korean fonts from X Window and Unix](recipes/x-window.md#korean-fonts-from-x-window-and-unix) |
| hanterm johab-1 BDF (`10-6-6`, 529 glyphs) | no | `jamoset.py --layout hanterm-johab` | [hanterm johab fonts](recipes/x-window.md#hanterm) |
| hanterm johab844-1 BDF (`8-4-4`, 360 glyphs) | no | `jamoset.py --layout hanterm-844` (exact) | [hanterm johab fonts](recipes/x-window.md#hanterm) |
| HBF | only as the ASCII half of `bdfface.py` | no | [HBF](recipes/bitmap-fonts.md#hbf) |
| Windows `.FNT` / `.FON` | no reader (FreeType gives it no Unicode map; convert it to a BDF with an outside tool first) | no | [Windows FNT and FON](recipes/bitmap-fonts.md#windows-fnt-and-fon) |
| DOS raw jamo-piece font (8x4x4 `HANGUL.FNT`, san, Dokkaebi, Kyra...) | `johab844.py` (16 px 8x4x4) | `jamoset.py --layout L` | [DOS-era raw fonts](recipes/dos-fonts.md#dos-era-raw-fonts) |
| HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT` | `hwpfont.py bdf --face N`, then `mkfont.py` | `jamoset.py --layout hwp1 --face N` (HWP's own rule, exact) | [HWP 1.x and 2.x fonts](recipes/dos-fonts.md#hwp-1x-and-2x-fonts) |
| HWP 3.0 `HAN*.FNT` (2,350 syllables, + an 8x4x4 set at 16 px) | `hwpfont.py bdf`, then `mkfont.py` | `jamoset.py --layout 844-hwp3` (16 px), else `--from-svf` | [HWP 3.0 FNT fonts](recipes/dos-fonts.md#hwp-30-fnt-fonts) |
| KS X 1001 raw dump (2,350 syllables in code order, or a 94 x 94 table) | `hwpfont.py bdf` (16-48 px dumps), or `rawcarve.py bdf --dense` / `--grid`; then `mkfont.py` or `bdfface.py` | `jamoset.py --from-svf` | [KS X 1001 raw dumps](recipes/dos-fonts.md#ks-x-1001-raw-dumps) |
| A font inside a program or ROM (DOS driver or TSR, word processor, Korean VGA BIOS + font ROM) | `binscan.py` to find, `rawcarve.py` to cut (raw, BDF, or composed by the driver's rule), then `bdfface.py` | `jamoset.py --layout 844` on a cut raw font, or `--from-svf` | [Finding a font inside a program or data file, with Claude](recipes/programs-and-drivers.md#finding-a-font-inside-a-program-or-data-file-with-claude) |
| Korean MSX ROMs (Daewoo, Goldstar: MSX2 SUB-ROM, CPC-400S font ROM, MSX1 BIOS) | `rawcarve.py compose` + `bdfface.py` (MSX2), `msxfont.py kfn-map` + `rawcarve.py bdf --chars map` + `bdfface.py` (CPC-400S), `msxfont.py msx1` + `mkfont.py` (MSX1) | `jamoset.py --layout spec --spec tools/specs/msx2-daewoo.json` (MSX2, exact) | [Korean MSX fonts](recipes/rom-msx.md#korean-msx-fonts-msx2-and-msx1) |
| A Korean machine's or arcade game's ROMs in a MAME set (inverted jamo ROMs, multi-bit sprite tiles) | `rawcarve.py region` + `ink --gfx` (or `--invert`), `rawcarve.py bdf --dense`, then `bdfface.py` | `jamoset.py --layout spec` (a font with its own rule, exact), `--layout 844` on a cut 8x4x4 font, or `--from-svf` | [Korean font ROMs in MAME sets](recipes/rom-mame.md#korean-font-roms-in-mame-sets) |
| OS/2 Korean System DBCS font (`$korZN16.FNT`, `$korZN24.FNT`; 완성형) | `os2dbcs.py table`, `rawcarve.py bdf --grid 0xA1,0xA1,94`, `bdfface.py` | `jamoset.py --from-svf` | [OS/2 Korean fonts (완성형)](recipes/os2.md#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set) |
| TTF with jamo glyphs (conjoining jamo, PUA pieces, GSUB `ljmo`) | as any TTF | composites `jamovec.py --components`; variants `--mask-font`; else a fit | [TrueType fonts that already carry jamo](recipes/outline-fonts.md#truetype-fonts-that-already-carry-jamo) |
| A 24-48 px bitmap face wanted at 16 px or 2 bpp | `svfscale.py --size 16 [--bpp 2]` | `jamoset.py --from-svf` (1 bpp result) | [A low-resolution face from a high-resolution bitmap font](recipes/bitmap-fonts.md#a-low-resolution-face-from-a-high-resolution-bitmap-font) |
| Mac HangulTalk 1.0 `fbit` (45 sets + `fdef`) | no | `jamoset.py --layout mac-fbit-45sets` | [Classic Mac Korean bitmap fonts](recipes/classic-mac.md#classic-mac-korean-bitmap-fonts) |
| Mac HangulTalk 7.1 type-3 `fbit` + HTBL 1 | `macfbit3.py bdf` + `mkfont.py` | `macfbit_svf.py build` | [Classic Mac Korean bitmap fonts](recipes/classic-mac.md#classic-mac-korean-bitmap-fonts) |
| An SVF face | `svfdy.py`, `svf2to3.py` | `jamoset.py --from-svf` (1 bpp source) | [An existing SVF](recipes/svf-and-ttf.md#an-existing-svf) |
| An SVF face, wanted back as a TTF (or BDF) bitmap font | `svf2ttf.py ttf` (or `bdf`) | the same: every syllable composed, a precomposed font (`--composite`: the pieces shared, syllables composite glyphs) | [An SVF face back to a TTF bitmap font](recipes/svf-and-ttf.md#an-svf-face-back-to-a-ttf-bitmap-font) |

How many sets a jamo set should have: [Choosing the number of sets](recipes/sets.md#choosing-the-number-of-sets). Anti-aliased faces:
[2 bpp anti-aliased faces](recipes/outline-fonts.md#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font).

The check for every row is the same: [Checking a face](#checking-a-face) (sample-line measure and ink, fit IoU for
a jamo set). Encoding monochrome source pixels at the same size adds no intermediate coverage; resampling to a smaller size (`svfscale.py --bpp 2`) can produce intermediate levels. Choose the jamo set when the
target has little memory (the 2,350-syllable 16 px examples are about 115 KB and their jamo sets about 20 KB), the precomposed face
when every syllable must be exactly the source's.

<a id="checking-a-face"></a>

<a id="2-checking-a-face"></a>

## Checking a face

<a id="checks-for-a-new-face"></a>

Every recipe document ends with the same checks. The sample line is `안녕하세요 ABC 123`; the faces are 16 px in a 16x16 cell
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
  `python3 tools/svfline.py line 400 32 0 24 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray` for a 24 px face. Use a wider buffer for measured widths above 200 (or 400 in the larger-cell template); those exceptions are shown in the recipes.
- A jamo set is judged by `--check` (on `jamoset.py` and `jamovec.py`): it composes all 11,172 syllables from the pieces
  and fails on a table error; the fit line before it prints the IoU of the pieces against the source's syllables
  (`fit: 11172 syllables, IoU 0.817`). `--check` does not fail on a poor fit: read the IoU, and look at the result
  (`svfline.py line`, or the `web/` picker).
- `svf2to3.py --check` compares glyph by glyph through `svfline`. The `facecheck.py` commands above record committed
  files at `HEAD`, then compare working files with that manifest; they do not validate a new `FACE.SVF`.
  `tools/build/build_faces.py` rebuilds the faces of `svf/` (see [Faces of svf/](recipes/svf-faces.md#faces-of-svf)).

Reference run (verified), NanumGothic Bold at 16 px ([Precomposed faces](recipes/outline-fonts.md#precomposed-faces-mkfontpy)): 1 bpp `125,520` bytes, 2,446 glyphs, `width=146 ascent=14
descent=2`, ink 677.

<a id="reference"></a>

<a id="16-reference"></a>

## Reference

<a id="ks-x-1001"></a>

<a id="161-ks-x-1001"></a>

### KS X 1001

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

<a id="162-encodings"></a>

### Encodings

EUC-KR / wansung byte pair = GL code + 0x8080 (`가` = B0A1 = GL 3021); Python: `bytes((0xB0,0xA1)).decode("euc_kr")`.
Johab (Python `johab` codec): a 16-bit code `1 iiiii mmmmm fffff` with fill values (initial 2 = ㄱ, medial 3 =
ㅏ, final 1 = none), `가` = 8861; `bytes((0x88,0x61)).decode("johab")`. Unicode syllable = 0xAC00 + (initial x 21 + medial)
x 28 + final with 0-based jamo indices. See [Hangul composition and encodings](#ref-encoding). `tools/test_recipes.py` checks these examples.

<a id="known-limits"></a>

<a id="163-known-limits"></a>

### Known limits

- The default `--binarize mono` of `jamoset.py` needs `freetype-py` (a mask font also needs `uharfbuzz`): the recipes use `--binarize threshold`, and `--mask-font none`
  keeps a 1 bpp fit independent of `$JAMOSET_MASK_FONT`; see [Jamo sets](recipes/outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts).
- Run time (this host, one core): a 1 bpp `threshold` fit of a 16 px outline font about 12 s, a 2 bpp one about 73 s,
  Gowun Batang adaptive at 20 px about 90 s. A 2 bpp face is about 1.5-1.6x its 1 bpp face; a jamo set about a sixth.
- `mkfont.py --bpp 2` can encode a monochrome bitmap at its own size, but that adds no intermediate coverage; `svfscale.py --bpp 2` makes one at a smaller
  size ([A low-resolution face from a high-resolution bitmap font](recipes/bitmap-fonts.md#a-low-resolution-face-from-a-high-resolution-bitmap-font)), and no tool makes a 2 bpp jamo set from a bitmap.
- `mkfont.py` prints its summary in Korean: do not parse its stdout for field names.
- Known gaps of the tools in general: [tools.md](tools.md#remaining-gaps-of-the-tools), "Remaining gaps of the tools".

<a id="references"></a>

<a id="18-references"></a>

## References

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

<a id="moved-sections"></a>

## Moved sections

Until 2026-11-27 the recipes were one document. A link to a section anchor that moved still lands here, on that section's row, which links on to its new place.

| Old anchor of docs/recipes.md | Now in |
|---|---|
| <a id="outline-fonts"></a><a id="3-outline-fonts"></a>`#outline-fonts`, `#3-outline-fonts` | [Outline fonts](recipes/outline-fonts.md#outline-fonts) |
| <a id="precomposed-faces-mkfontpy"></a><a id="31-precomposed-faces-mkfontpy"></a>`#precomposed-faces-mkfontpy`, `#31-precomposed-faces-mkfontpy` | [Precomposed faces (`mkfont.py`)](recipes/outline-fonts.md#precomposed-faces-mkfontpy) |
| <a id="opentype-cff-otf"></a><a id="32-opentype-cff-otf"></a>`#opentype-cff-otf`, `#32-opentype-cff-otf` | [OpenType CFF (`.otf`)](recipes/outline-fonts.md#opentype-cff-otf) |
| <a id="jamo-sets-from-truetype-and-opentype-fonts"></a><a id="33-jamo-sets-from-truetype-and-opentype-fonts"></a>`#jamo-sets-from-truetype-and-opentype-fonts`, `#33-jamo-sets-from-truetype-and-opentype-fonts` | [Jamo sets from TrueType and OpenType fonts](recipes/outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts) |
| <a id="truetype-fonts-that-already-carry-jamo"></a><a id="34-truetype-fonts-that-already-carry-jamo"></a>`#truetype-fonts-that-already-carry-jamo`, `#34-truetype-fonts-that-already-carry-jamo` | [TrueType fonts that already carry jamo](recipes/outline-fonts.md#truetype-fonts-that-already-carry-jamo) |
| <a id="2-bpp-anti-aliased-faces-from-a-truetypeopentype-font"></a><a id="anti-aliased-2-bpp-faces"></a><a id="35-2-bpp-anti-aliased-faces-from-a-truetypeopentype-font"></a>`#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font`, `#anti-aliased-2-bpp-faces`, `#35-2-bpp-anti-aliased-faces-from-a-truetypeopentype-font` | [2 bpp anti-aliased faces from a TrueType/OpenType font](recipes/outline-fonts.md#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font) |
| <a id="baseline-vertical-shift-and-clipping"></a><a id="36-baseline-vertical-shift-and-clipping"></a>`#baseline-vertical-shift-and-clipping`, `#36-baseline-vertical-shift-and-clipping` | [Baseline, vertical shift and clipping](recipes/outline-fonts.md#baseline-vertical-shift-and-clipping) |
| <a id="ttc-and-otc"></a><a id="opentype-cff-collections-and-variable-fonts"></a><a id="37-ttc-and-otc"></a>`#ttc-and-otc`, `#opentype-cff-collections-and-variable-fonts`, `#37-ttc-and-otc` | [TTC and OTC](recipes/outline-fonts.md#ttc-and-otc) |
| <a id="variable-fonts"></a><a id="38-variable-fonts"></a>`#variable-fonts`, `#38-variable-fonts` | [Variable fonts](recipes/outline-fonts.md#variable-fonts) |
| <a id="mac-format-truetype"></a><a id="39-mac-format-truetype"></a>`#mac-format-truetype`, `#39-mac-format-truetype` | [Mac-format TrueType](recipes/outline-fonts.md#mac-format-truetype) |
| <a id="bitmap-fonts"></a><a id="4-bitmap-fonts"></a>`#bitmap-fonts`, `#4-bitmap-fonts` | [Bitmap fonts](recipes/bitmap-fonts.md#bitmap-fonts) |
| <a id="x-window-korean-fonts"></a>`#x-window-korean-fonts` | [Korean fonts from X Window and Unix](recipes/x-window.md#x-window-korean-fonts) |
| <a id="iso-10646-bdf-and-pcf"></a><a id="41-iso-10646-bdf-and-pcf"></a>`#iso-10646-bdf-and-pcf`, `#41-iso-10646-bdf-and-pcf` | [ISO 10646 BDF and PCF](recipes/bitmap-fonts.md#iso-10646-bdf-and-pcf) |
| <a id="ks-c-5601-bdf-and-pcf"></a><a id="42-ks-c-5601-bdf-and-pcf"></a>`#ks-c-5601-bdf-and-pcf`, `#42-ks-c-5601-bdf-and-pcf` | [KS C 5601 BDF and PCF](recipes/bitmap-fonts.md#ks-c-5601-bdf-and-pcf) |
| <a id="hanterm"></a><a id="43-hanterm"></a>`#hanterm`, `#43-hanterm` | [hanterm johab fonts](recipes/x-window.md#hanterm) |
| <a id="hbf"></a><a id="44-hbf"></a>`#hbf`, `#44-hbf` | [HBF](recipes/bitmap-fonts.md#hbf) |
| <a id="windows-fnt-and-fon"></a><a id="45-windows-fnt-and-fon"></a>`#windows-fnt-and-fon`, `#45-windows-fnt-and-fon` | [Windows FNT and FON](recipes/bitmap-fonts.md#windows-fnt-and-fon) |
| <a id="embedded-bitmap-strikes"></a><a id="46-embedded-bitmap-strikes"></a>`#embedded-bitmap-strikes`, `#46-embedded-bitmap-strikes` | [Embedded bitmap strikes](recipes/bitmap-fonts.md#embedded-bitmap-strikes) |
| <a id="a-low-resolution-face-from-a-high-resolution-bitmap-font"></a><a id="9-a-low-resolution-face-from-a-high-resolution-bitmap-font"></a>`#a-low-resolution-face-from-a-high-resolution-bitmap-font`, `#9-a-low-resolution-face-from-a-high-resolution-bitmap-font` | [A low-resolution face from a high-resolution bitmap font](recipes/bitmap-fonts.md#a-low-resolution-face-from-a-high-resolution-bitmap-font) |
| <a id="dos-era-raw-fonts"></a><a id="5-dos-era-raw-fonts"></a>`#dos-era-raw-fonts`, `#5-dos-era-raw-fonts` | [DOS-era raw fonts](recipes/dos-fonts.md#dos-era-raw-fonts) |
| <a id="other-dos-era-korean-fonts"></a><a id="51-other-dos-era-korean-fonts"></a>`#other-dos-era-korean-fonts`, `#51-other-dos-era-korean-fonts` | [Other DOS-era Korean fonts](recipes/dos-fonts.md#other-dos-era-korean-fonts) |
| <a id="hwp-1x-and-2x-fonts"></a><a id="52-hwp-1x-and-2x-fonts"></a>`#hwp-1x-and-2x-fonts`, `#52-hwp-1x-and-2x-fonts` | [HWP 1.x and 2.x fonts](recipes/dos-fonts.md#hwp-1x-and-2x-fonts) |
| <a id="hwp-30-fnt-fonts"></a><a id="53-hwp-30-fnt-fonts"></a>`#hwp-30-fnt-fonts`, `#53-hwp-30-fnt-fonts` | [HWP 3.0 FNT fonts](recipes/dos-fonts.md#hwp-30-fnt-fonts) |
| <a id="ks-x-1001-raw-dumps"></a><a id="54-ks-x-1001-raw-dumps"></a>`#ks-x-1001-raw-dumps`, `#54-ks-x-1001-raw-dumps` | [KS X 1001 raw dumps](recipes/dos-fonts.md#ks-x-1001-raw-dumps) |
| <a id="finding-a-font-inside-a-program-or-data-file-with-claude"></a><a id="6-finding-a-font-inside-a-program-or-data-file-with-claude"></a>`#finding-a-font-inside-a-program-or-data-file-with-claude`, `#6-finding-a-font-inside-a-program-or-data-file-with-claude` | [Finding a font inside a program or data file, with Claude](recipes/programs-and-drivers.md#finding-a-font-inside-a-program-or-data-file-with-claude) |
| <a id="the-prompt"></a><a id="61-the-prompt"></a>`#the-prompt`, `#61-the-prompt` | [The prompt](recipes/programs-and-drivers.md#the-prompt) |
| <a id="nkp-a-hercules-hangul-tsr-with-cropped-pieces"></a><a id="62-nkp-a-hercules-hangul-tsr-with-cropped-pieces"></a>`#nkp-a-hercules-hangul-tsr-with-cropped-pieces`, `#62-nkp-a-hercules-hangul-tsr-with-cropped-pieces` | [NKP: a Hercules Hangul TSR with cropped pieces](recipes/programs-and-drivers.md#nkp-a-hercules-hangul-tsr-with-cropped-pieces) |
| <a id="dokkaebi-the-font-inside-the-driver"></a><a id="63-dokkaebi-the-font-inside-the-driver"></a>`#dokkaebi-the-font-inside-the-driver`, `#63-dokkaebi-the-font-inside-the-driver` | [Dokkaebi: the font inside the driver](recipes/programs-and-drivers.md#dokkaebi-the-font-inside-the-driver) |
| <a id="korean-vga-font-roms-86box"></a><a id="64-korean-vga-font-roms-86box"></a>`#korean-vga-font-roms-86box`, `#64-korean-vga-font-roms-86box` | [Korean VGA font ROMs (86Box)](recipes/rom-86box.md#korean-vga-font-roms-86box) |
| <a id="korean-msx-fonts-msx2-and-msx1"></a><a id="65-korean-msx-fonts-msx2-and-msx1"></a>`#korean-msx-fonts-msx2-and-msx1`, `#65-korean-msx-fonts-msx2-and-msx1` | [Korean MSX fonts (MSX2 and MSX1)](recipes/rom-msx.md#korean-msx-fonts-msx2-and-msx1) |
| <a id="msx-with-a-coding-agent-recommended"></a><a id="with-a-coding-agent-recommended"></a>`#msx-with-a-coding-agent-recommended`, `#with-a-coding-agent-recommended` | [With a coding agent (recommended)](recipes/rom-msx.md#msx-with-a-coding-agent-recommended) |
| <a id="msx2-the-daewoo-jamo-set-font-exact"></a>`#msx2-the-daewoo-jamo-set-font-exact` | [MSX2: the Daewoo jamo-set font (exact)](recipes/rom-msx.md#msx2-the-daewoo-jamo-set-font-exact) |
| <a id="msx2-the-cpc-400s-precomposed-font"></a>`#msx2-the-cpc-400s-precomposed-font` | [MSX2: the CPC-400S precomposed font](recipes/rom-msx.md#msx2-the-cpc-400s-precomposed-font) |
| <a id="msx1-the-jamo-cells-of-the-bios-laid-out-as-the-machine-does"></a>`#msx1-the-jamo-cells-of-the-bios-laid-out-as-the-machine-does` | [MSX1: the jamo cells of the BIOS, laid out as the machine does](recipes/rom-msx.md#msx1-the-jamo-cells-of-the-bios-laid-out-as-the-machine-does) |
| <a id="truetype-files"></a>`#truetype-files` | [TrueType files](recipes/rom-msx.md#truetype-files) |
| <a id="the-emulator-as-ground-truth"></a>`#the-emulator-as-ground-truth` | [The emulator as ground truth](recipes/rom-msx.md#the-emulator-as-ground-truth) |
| <a id="korean-font-roms-in-mame-sets"></a><a id="7-korean-font-roms-in-mame-sets"></a>`#korean-font-roms-in-mame-sets`, `#7-korean-font-roms-in-mame-sets` | [Korean font ROMs in MAME sets](recipes/rom-mame.md#korean-font-roms-in-mame-sets) |
| <a id="samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact"></a><a id="71-samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact"></a>`#samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact`, `#71-samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact` | [Samsung SPC-1500: a jamo set in four inverted ROMs (exact)](recipes/rom-mame.md#samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact) |
| <a id="date-quiz-go-go-a-2350-syllable-sprite-font"></a><a id="72-date-quiz-go-go-a-2350-syllable-sprite-font"></a>`#date-quiz-go-go-a-2350-syllable-sprite-font`, `#72-date-quiz-go-go-a-2350-syllable-sprite-font` | [Date Quiz Go Go: a 2,350-syllable sprite font](recipes/rom-mame.md#date-quiz-go-go-a-2350-syllable-sprite-font) |
| <a id="x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check"></a><a id="73-x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check"></a>`#x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check`, `#73-x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check` | [X Se Dae Quiz: Taebaek GOTHIC16 in the sprites (a cross-check)](recipes/rom-mame.md#x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check) |
| <a id="quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen"></a><a id="74-quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen"></a>`#quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen`, `#74-quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen` | [Quiz King of Fighters (Korea): a 2,350-syllable font with an outline pen](recipes/rom-mame.md#quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen) |
| <a id="live-quiz-show-the-rule-read-the-pieces-not-aligned-not-built"></a><a id="75-live-quiz-show-the-rule-read-the-pieces-not-aligned-not-built"></a>`#live-quiz-show-the-rule-read-the-pieces-not-aligned-not-built`, `#75-live-quiz-show-the-rule-read-the-pieces-not-aligned-not-built` | [Live Quiz Show: the rule read, the pieces not aligned (not built)](recipes/rom-mame.md#live-quiz-show-the-rule-read-the-pieces-not-aligned-not-built) |
| <a id="sets-with-no-font-or-with-a-font-not-resolved"></a><a id="76-sets-with-no-font-or-with-a-font-not-resolved"></a>`#sets-with-no-font-or-with-a-font-not-resolved`, `#76-sets-with-no-font-or-with-a-font-not-resolved` | [Sets with no font, or with a font not resolved](recipes/rom-mame.md#sets-with-no-font-or-with-a-font-not-resolved) |
| <a id="os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set"></a><a id="8-os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set"></a>`#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set`, `#8-os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set` | [OS/2 Korean fonts (완성형) to a precomposed face and a jamo set](recipes/os2.md#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set) |
| <a id="classic-mac-korean-bitmap-fonts"></a><a id="10-classic-mac-korean-bitmap-fonts"></a>`#classic-mac-korean-bitmap-fonts`, `#10-classic-mac-korean-bitmap-fonts` | [Classic Mac Korean bitmap fonts](recipes/classic-mac.md#classic-mac-korean-bitmap-fonts) |
| <a id="an-existing-svf"></a><a id="11-an-existing-svf"></a>`#an-existing-svf`, `#11-an-existing-svf` | [An existing SVF](recipes/svf-and-ttf.md#an-existing-svf) |
| <a id="an-svf-face-back-to-a-ttf-bitmap-font"></a><a id="12-an-svf-face-back-to-a-ttf-bitmap-font"></a>`#an-svf-face-back-to-a-ttf-bitmap-font`, `#12-an-svf-face-back-to-a-ttf-bitmap-font` | [An SVF face back to a TTF bitmap font](recipes/svf-and-ttf.md#an-svf-face-back-to-a-ttf-bitmap-font) |
| <a id="composite-glyphs---composite"></a><a id="121-composite-glyphs---composite"></a>`#composite-glyphs---composite`, `#121-composite-glyphs---composite` | [Composite glyphs (`--composite`)](recipes/svf-and-ttf.md#composite-glyphs---composite) |
| <a id="choosing-the-number-of-sets-벌-수"></a><a id="choosing-the-number-of-sets"></a><a id="13-choosing-the-number-of-sets-벌-수"></a>`#choosing-the-number-of-sets-벌-수`, `#choosing-the-number-of-sets`, `#13-choosing-the-number-of-sets-벌-수` | [Choosing the number of sets (벌 수)](recipes/sets.md#choosing-the-number-of-sets-벌-수) |
| <a id="desktop-app-and-maker-routes"></a><a id="14-desktop-app-and-maker-routes"></a>`#desktop-app-and-maker-routes`, `#14-desktop-app-and-maker-routes` | [Desktop app and maker routes](recipes/desktop-routes.md#desktop-app-and-maker-routes) |
| <a id="faces-of-svf"></a><a id="rebuilding-the-faces-of-svf"></a><a id="15-faces-of-svf"></a>`#faces-of-svf`, `#rebuilding-the-faces-of-svf`, `#15-faces-of-svf` | [Faces of svf/](recipes/svf-faces.md#faces-of-svf) |
| <a id="the-precomposed-recipe-mkfont-rows"></a><a id="151-the-precomposed-recipe-mkfont-rows"></a>`#the-precomposed-recipe-mkfont-rows`, `#151-the-precomposed-recipe-mkfont-rows` | [The precomposed recipe (`mkfont` rows)](recipes/svf-faces.md#the-precomposed-recipe-mkfont-rows) |
| <a id="the-jamo-set-from-precomposed-recipe-jamoset-rows"></a><a id="152-the-jamo-set-from-precomposed-recipe-jamoset-rows"></a>`#the-jamo-set-from-precomposed-recipe-jamoset-rows`, `#152-the-jamo-set-from-precomposed-recipe-jamoset-rows` | [The jamo-set-from-precomposed recipe (`jamoset` rows)](recipes/svf-faces.md#the-jamo-set-from-precomposed-recipe-jamoset-rows) |
| <a id="families"></a><a id="153-families"></a>`#families`, `#153-families` | [Families](recipes/svf-faces.md#families) |
| <a id="faces-without-a-recipe"></a><a id="154-faces-without-a-recipe"></a>`#faces-without-a-recipe`, `#154-faces-without-a-recipe` | [Faces without a recipe](recipes/svf-faces.md#faces-without-a-recipe) |
| <a id="adding-a-face-to-svf"></a><a id="17-adding-a-face-to-svf"></a>`#adding-a-face-to-svf`, `#17-adding-a-face-to-svf` | [Adding a face to svf/](recipes/svf-faces.md#adding-a-face-to-svf) |

[Project overview](../README.md) · [Tool reference](tools.md)
