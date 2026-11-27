**English** | [한국어](programs-and-drivers.ko.md)

# Recipes: Fonts inside programs and drivers

Finding a font inside a program or data file (a DOS driver or TSR, a word processor) with an assistant such as Claude: `binscan.py` and `rawcarve.py`, the prompt to give it, and two worked examples, the NKP Hercules TSR (cropped pieces composed by the driver's rule) and the Dokkaebi driver.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The programs are proprietary and supplied separately. The same tools and prompt read font ROMs: [Korean VGA font ROMs](rom-86box.md), [Korean MSX fonts](rom-msx.md), [MAME sets](rom-mame.md).

Up: [Recipes index](../recipes.md) · Related: [DOS-era raw fonts](dos-fonts.md), [Korean VGA font ROMs (86Box)](rom-86box.md), [Korean MSX fonts (MSX2 and MSX1)](rom-msx.md), [Korean font ROMs in MAME sets](rom-mame.md), [Tool reference](../tools.md).

<a id="finding-a-font-inside-a-program-or-data-file-with-claude"></a>

## Finding a font inside a program or data file, with Claude

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
8x4x4 font goes straight to `jamoset.py --layout 844` ([Other DOS-era Korean fonts](dos-fonts.md#other-dos-era-korean-fonts)). Both
tools only read bytes and never run the file's code; run them with `python3 -I` on downloads. Use the [7-Zip output-directory switch](../recipes.md#ref-7zip) to unpack an archive first
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

### The prompt

What to give Claude (or any assistant that can run commands here) for one file; the angle brackets are yours to fill:

```
Find the Hangul (and English) bitmap font inside <FILE> (<what it is: a 1989 DOS Hangul TSR / a Korean VGA BIOS and
its font ROM / ...>), cut it out and build SVF faces from it with the tools of this repository (docs/recipes/programs-and-drivers.md,
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
   NAMED_RANGES['ksx1001-hangul'] as in docs/recipes/bitmap-fonts.md, KS C 5601 BDF and PCF; WxH = the font's cell) then
   `jamoset.py --layout 844 --from-svf FACE --mask-font none --check` (also --layout adaptive); report size, glyph
   count, `svfline.py measure` and ink of "안녕하세요 ABC 123" (docs/recipes.md, Checking a face) and the fit IoU, and
   show the line drawn.
Report the offsets, the commands and the numbers; say what you could not resolve.
```

`$OUT/ks.txt`, the syllable list every `bdfface.py` line below reads, is written once:

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))" $OUT/ks.txt

The three examples below were worked with this prompt (2026-11-22). They use proprietary programs and ROM dumps supplied separately.

<a id="nkp-a-hercules-hangul-tsr-with-cropped-pieces"></a>

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

<a id="dokkaebi-the-font-inside-the-driver"></a>

### Dokkaebi: the font inside the driver

Source: the Hangul Dokkaebi B drivers DKBB.COM (22,035 bytes) and DKBII.COM (20,355 bytes) of a Hangul Dokkaebi B
distribution (`dkbb.rar`, with the driver source DKBB.ASM and DKBBG.FNT / DKBBM.FNT; proprietary). The loose DKBBG.FNT is read in [Other DOS-era Korean fonts](dos-fonts.md#other-dos-era-korean-fonts); here
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

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
