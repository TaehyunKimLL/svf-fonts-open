**English** | [한국어](bitmap-fonts.ko.md)

# Recipes: Bitmap fonts

Bitmap font files to SVF faces: BDF and PCF in ISO 10646 or KS C 5601 (the X Window Korean fonts themselves, hanterm's johab fonts among them, have [their own document](x-window.md)), HBF, Windows FNT and FON, the bitmap strikes embedded in outline fonts, and a low-resolution (or 2 bpp) face scaled down from a high-resolution bitmap font.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The KS C 5601 recipe writes `$OUT/ks.txt` (the 2,350 KS X 1001 syllables) that the `bdfface.py` lines of every document read.

Up: [Recipes index](../recipes.md) · Related: [Korean fonts from X Window and Unix](x-window.md), [Outline fonts](outline-fonts.md), [DOS-era raw fonts](dos-fonts.md), [Anti-aliasing](../anti-aliasing.md).

<a id="bitmap-fonts"></a>

## Bitmap fonts

<a id="x-window-korean-fonts"></a>

Two kinds of bitmap fonts reach the tools by different paths: Unicode-encoded ones (`CHARSET_REGISTRY "ISO10646"`, or a
TrueType with embedded strikes) go through `mkfont.py` and FreeType; KS C 5601 / KS X 1001 encoded ones (`ENCODING` = the
GL code, the X Window Korean fonts) go through `bdfface.py`. The X Window and Unix Korean fonts family by family
(Daewoo, Baekmuk, Hanyang, KAIST, Mizi, hanterm), with commands, measurements, licences and samples, are in
[Korean fonts from X Window and Unix](x-window.md).

<a id="iso-10646-bdf-and-pcf"></a>

### ISO 10646 BDF and PCF

`mkfont.py` reads a BDF or PCF through Pillow's FreeType, at the file's built-in pixel size only (its strike); any other
size is `OSError: invalid pixel size`, and the maker's `detect.bitmap_strikes` names the sizes a font offers. There is no
shim or workaround: `mkfont.py` asks fontTools whether a code point is in the cmap and treats a non-sfnt file (BDF, PCF,
FNT) as unknown, not as an error (`cmap_has` returns None). The examples use `/usr/share/dosbox-x/wqy_12pt.bdf` (WenQuanYi Bitmap Song, 16 px, Unicode) and
`/usr/share/fonts/X11/misc/18x18ko.pcf.gz` (Misc Fixed Wide, 18 px) [BDF format](../recipes.md#ref-bdf).

    python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf $OUT/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-2bpp.svf --size 18 --bpp 2 --unicode ascii,ksx1001-hangul

Verified, without any shim: BDF `115,684 bytes`, 2,446 glyphs, `width=156 ascent=12 descent=4`, ink 348; PCF 1 bpp
`116,552 bytes`, 2,446 glyphs (18x18 cell), `width=234 ascent=15 descent=3`, ink 366; PCF 2 bpp `181,108 bytes`. These bitmaps carry
only monochrome coverage, so `--bpp 2` only has levels 0 and 3: the same monochrome pixels at 2 bpp, not a smooth face. A jamo set from
these faces is a fit to the precomposed result: `jamoset.py --layout 844 --from-svf $OUT/bdf16-1bpp.svf --mask-font none --check -o ...`
(the next subsection shows the numbers for a bdfface face).

<a id="ks-c-5601-bdf-and-pcf"></a>

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
`--ascii`, and its own U+2026 / U+25A1: no symbols or jamo come from the BDF unless `--symbols` is given, which also
takes the other characters `--chars-from` names (KS X 1001 symbols, jamo, Hanja) from the Hangul BDF
([the X Window recipe](x-window.md#preparing-the-syllable-list-the-ascii-half-and-pcf) uses it). The cell defaults to 24x24 whatever the BDF's
box is, so give `--cell`; `--ascent` / `--hangul-ascent` place the baselines. Synthetic (`tools/test_recipes.py`): a KS C
5601 BDF of 10 syllables and an ISO 10646 ASCII BDF give a face with exactly those syllables, rows in place.

<a id="hanterm"></a>

**hanterm** (moved). The hanterm johab BDFs (the johab-1 fonts of hanterm 3.0.4 and the johab844-1 fonts of
hanterm-font 3.1, with `jamoset.py --layout hanterm-johab` and `--layout hanterm-844`) are now in
[hanterm johab fonts](x-window.md#hanterm) of [Korean fonts from X Window and Unix](x-window.md).

<a id="hbf"></a>

### HBF

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

### Windows FNT and FON

FreeType has a winfnt driver and `mkfont.py` opens a Windows `.FNT` (or the `.FON` that holds several) at the font's own
pixel size, the way it opens a BDF or PCF, but it cannot draw from one: the driver gives these fonts a single charmap of
`FT_ENCODING_NONE`, no Unicode, so every code point falls on glyph 0. Run on the Windows 95 Korean system fonts (Microsoft,
proprietary): VGAFIX.FON "Fixedsys" 16 px, VGASYS.FON "System" 13 px, SERIFF.FON "MS Serif" 13 px, 8514FIX.FON ([FreeType bitmap and Windows FNT support](../recipes.md#ref-freetype)):

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

Not to be mixed up with DOS Johab `.FNT` files, which are jamo-piece fonts: see [DOS-era raw fonts](dos-fonts.md#dos-era-raw-fonts).

<a id="embedded-bitmap-strikes"></a>

### Embedded bitmap strikes

An outline font with embedded bitmaps (TrueType `bdat`/`bloc`, OpenType `EBDT`/`EBLC`) is used by FreeType only at the
strike's own pixel size: run `mkfont.py --size N` with the strike's size and `--bpp 1`; at other sizes the outlines are
used, or the open fails for a bitmap-only font (`OSError: invalid pixel size`). The maker's `detect.bitmap_strikes` lists a
font's strikes and offers them as sizes. Run on two real fonts [OpenType glyphs, shaping and bitmap strikes](../recipes.md#ref-opentype).

*Seoul* of the Mac OS 7.6.1 Korean CD (`Font Folder/Seoul[FFIL]`, Apple Korea / Elex, proprietary; strikes 9, 10, 12, 14, 16,
18, 20, 24 ppem, see [Mac-format TrueType](outline-fonts.md#mac-format-truetype)): after `macsfnt.py extract` and `unicode`, `mkfont.py --size 16
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


<a id="a-low-resolution-face-from-a-high-resolution-bitmap-font"></a>

## A low-resolution face from a high-resolution bitmap font

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
to four levels (checked on all 2,350 syllables of the [OS/2 face](os2.md): every one equal), in this comparison, a stored 2 bpp face and
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
| OS/2 `$korZN24.FNT` ([OS/2 Korean fonts](os2.md#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set), `220,164 bytes`) | `125,084 bytes`, 2,447 glyphs, `width=144 ascent=15 descent=1` | 410 | `200,760 bytes` | 691 | `18,596 bytes`, IoU 0.710 | 0.387 against `$korZN16.FNT` |
| Taebaek 3.5.1 Gothic 40 (`GHANC40.PFT` with `--eng GASCII40.PFT`, the 8x4x4 face of [Other DOS-era Korean fonts](dos-fonts.md#other-dos-era-korean-fonts), `42,716 bytes`) | `124,940 bytes`, 2,447 glyphs, `width=144 ascent=14 descent=2` | 476 | `197,288 bytes` | 764 | `17,088 bytes`, IoU 0.990 | 0.471 against GOTHIC16.FNT |

The 40 px source is itself an OR of 8x4x4 pieces, so its 16 px resample still nearly is (IoU 0.990); the two whole-
syllable designs fit 8x4x4 poorly. The threshold trades strokes for blobs: the OS/2 face at `--threshold 0.25` has ink
615 (`0.5`: 410) and overlaps the drawn 16 px face 0.489. With `svfscale.py dotum24.bdf`, `--chars face` selects every glyph in the BDF (8,226 including Hanja in this example);
the default `--chars ks` selects KS syllables, ASCII and available non-syllable characters. The BDF supplies its ascent; go through `bdfface.py` first for a face with ASCII and
the cell you want.

**Pitfalls.** A 1-pixel stroke at 24 px covers two thirds of a 16 px pixel and survives a 0.5 threshold only where it
lines up; at 40 or 48 px thin strokes become 0.4-share pixels and vanish at 1 bpp. Resampling does not redraw: a drawn
16 px face (the last column above) is crisper, and a 2 bpp face from an outline font
([2 bpp anti-aliased faces](outline-fonts.md#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font)) has real coverage, not the
coverage of a bitmap's staircase.

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
