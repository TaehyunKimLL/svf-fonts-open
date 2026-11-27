**English** | [한국어](svf-and-ttf.ko.md)

# Recipes: Existing SVF faces, and SVF back to TTF

Working from an SVF face: setting a vertical shift (dy), re-baking a precomposed face as a jamo set, and writing a face back out as a TTF (or BDF) bitmap font, including composite glyphs that keep a jamo set's pieces shared.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The input is any SVF face, for example one of `svf/`.

Up: [Recipes index](../recipes.md) · Related: [Faces of svf/](svf-faces.md), [Choosing the number of sets (벌 수)](sets.md), [Tool reference](../tools.md).

<a id="an-existing-svf"></a>

## An existing SVF

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

## An SVF face back to a TTF bitmap font

The other way: `tools/svf2ttf.py` turns an SVF face, precomposed or a jamo set, back into a TrueType font an OS or an
application can install, and into a BDF. The face is read as the C library loads it (`svfline.Face`), so a jamo set gives
every syllable its table composes (all 11,172 for a full table, composed by `jamoset.compose` as `svfline.py` draws them)
and the compatibility jamo it maps, besides its other glyphs; the default output is a precomposed font either way. Every glyph
stands where `svfline.py` draws it: the cell's left column at the pen, its top row `ascent - dy` rows above the baseline,
a combining mark at its origin with advance 0, the advance the face's own [OpenType glyphs, shaping and bitmap strikes](../recipes.md#ref-opentype).

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
| HWP 1.x `HANGUL1.PFT` face 1 + `ASCII.PFT` (`jamoset.py --layout hwp1`, [HWP 1.x](dos-fonts.md#hwp-1x-and-2x-fonts)) | jamo set 1 bpp 24x24 | 11,318 | `16,712` | `2,849,128` | `2,726,291` | 0 / 0 of 11,318 | identical / identical |

An 8 bpp face (`mkfont.py --bpp 8` of `ttf/nanumgothic/NanumGothic-Bold.ttf` at 16 px, `ascii,ksx1001-hangul`, 2,446
glyphs, `579,152 bytes`) gets an 8-bit strike: TTF `876,820`, BDF `1,307,960 bytes`, both round trips (`--bpp 8`) 0
mismatches. The HWP 1.x face (HWP 1.20, proprietary) has no licence note beside it, so its TTF says the source font's
licence applies and stays in `$OUT`, as the face does.

`ttf` takes 2.5-4.8 s for a jamo set of 11,172 syllables and under 1 s for a precomposed face of 2,905 glyphs. Most of
a TTF is the outlines (`glyf`: 1,561,590 of NEODG16A's 2,038,968 bytes; the strike 348,244 + 45,352), so a TTF is 2.5-3.6
times the precomposed face and 29-170 times a jamo set. NEODG16A draws U+3161 (ㅡ) blank (its compatibility piece is empty), so `mkfont.py`
drops it and `compare` counts it as the one blank glyph.

**Installing.** See [fontconfig](../recipes.md#ref-fontconfig). Linux: copy the `.ttf` to `~/.local/share/fonts/` and run `fc-cache`; checked with a private fontconfig
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

### Composite glyphs (`--composite`)

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

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
