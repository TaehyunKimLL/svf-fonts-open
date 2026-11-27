**English** | [한국어](rom-mame.ko.md)

# Recipes: Korean font ROMs in MAME sets

Korean fonts in the ROMs of MAME sets: the Samsung SPC-1500's jamo set in four inverted ROMs (exact), the sprite fonts of Date Quiz Go Go, X Se Dae Quiz and Quiz King of Fighters (Korea), Live Quiz Show (the rule read, not built), and the sets with no font or a font not resolved.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The ROMs are proprietary and supplied separately. The method is the one of [Fonts inside programs and drivers](programs-and-drivers.md), which also writes `$OUT/ks.txt`.

Up: [Recipes index](../recipes.md) · Related: [Fonts inside programs and drivers](programs-and-drivers.md), [Korean VGA font ROMs (86Box)](rom-86box.md), [Desktop app and maker routes](desktop-routes.md).

<a id="korean-font-roms-in-mame-sets"></a>

## Korean font ROMs in MAME sets

Korean home computers and Korean arcade games keep their Hangul fonts in ROM chips, and MAME's romsets hold dumps of
them. None is 24x24: the fonts found are 16x16, one a jamo-piece set (the Samsung SPC-1500), the others precomposed
(완성형) sets of game sprites. The tools: `rawcarve.py region` joins a game's ROM files into the region the MAME driver
loads; `binscan.py` / `rawcarve.py` read inverted fonts (`--invert`) and multi-bit sprite tiles (`--gfx`, with the
driver's own `gfx_layout` numbers, reduced to 1 bpp by a pen rule: `--bg PEN`, or `--fg PENS`); `rawcarve.py ink` writes
the 1 bpp glyphs the other tools read; `jamoset.py --layout spec` builds an exact jamo set from a compose spec; and
`rawcarve.py eng --width 16` / `jamoset.py --eng` take 16-wide English cells. Like the drivers of [Finding a font inside a
program or data file](programs-and-drivers.md#finding-a-font-inside-a-program-or-data-file-with-claude), the ROMs are only read: no game is run
(an emulator would be fine; the drawing rules below were read from MAME's source and from the game's 68000 code,
disassembled) [MAME machine metadata, ROM loading and tile layouts](../recipes.md#ref-mame).

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

### Samsung SPC-1500: a jamo set in four inverted ROMs (exact)

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

### Date Quiz Go Go: a 2,350-syllable sprite font

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

### X Se Dae Quiz: Taebaek GOTHIC16 in the sprites (a cross-check)

Source: set `xsedae` (Dream Island, 1995), `obj-1.u0811` and `obj-2.u082` (2 MB each), `ROM_LOAD32_WORD` and
`gfx_16x16x4_packed_lsb` (`seibu/raiden2.cpp`). Here the background is the last pen: ink = pen != 15. The first 360
sprites are a raw 8x4x4 font, and the English font (16 wide: a few glyphs reach column 15) follows from `!`.

    python3 -I tools/rawcarve.py region --unit 2 $MAME/xsedae/obj-1.u0811,$MAME/xsedae/obj-2.u082 -o $OUT/xsedae-obj.bin
    python3 -I tools/rawcarve.py ink $OUT/xsedae-obj.bin --gfx 16x16x4_packed_lsb --bg 15 --count 600 -o $OUT/xsedae-ink.bin
    python3 -I tools/binscan.py sets $OUT/xsedae-ink.bin              # offsets 0x0, 0x2 tie: the font starts at 0
    python3 -I tools/rawcarve.py cut $OUT/xsedae-ink.bin --offset 0 --length 11520 -o $OUT/xsedae.fnt
    python3 -I tools/rawcarve.py eng $OUT/xsedae-ink.bin --offset $((360*32)) --width 16 --first 0x21 -o $OUT/xsedae-eng16.bin
    python3 tools/jamoset.py --layout 844 $OUT/xsedae.fnt --eng $OUT/xsedae-eng16.bin --check -o $OUT/XSEDAE16J.SVF

`xsedae.fnt` is byte for byte Taebaek 3.5.1's `GOTHIC16.FNT` (the [Other DOS-era Korean fonts](dos-fonts.md#other-dos-era-korean-fonts)
source), so the game adds no design; it checks the tile path. Verified: `15,780 bytes`, 439 glyphs, `check: ...
identical to johab844.py`, `width=144 ascent=14 descent=2` (the 16x16 English font measures a step of 8), ink 617.

<a id="quiz-king-of-fighters-korea-a-2350-syllable-font-with-an-outline-pen"></a>

### Quiz King of Fighters (Korea): a 2,350-syllable font with an outline pen

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

### Live Quiz Show: the rule read, the pieces not aligned (not built)

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

### Sets with no font, or with a font not resolved

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

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
