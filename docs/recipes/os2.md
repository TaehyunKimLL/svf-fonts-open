**English** | [한국어](os2.ko.md)

# Recipes: OS/2 Korean fonts (완성형)

The OS/2 Korean System DBCS fonts (`$korZN16.FNT`, `$korZN24.FNT`; 완성형): decoding the 94 x 94 table, a precomposed face, and a jamo set fitted to it.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The fonts are proprietary and supplied separately. `$OUT/ks.txt` is written as in [Fonts inside programs and drivers](programs-and-drivers.md#the-prompt).

Up: [Recipes index](../recipes.md) · Related: [Fonts inside programs and drivers](programs-and-drivers.md), [Bitmap fonts](bitmap-fonts.md), [Choosing the number of sets (벌 수)](sets.md).

<a id="os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set"></a>

## OS/2 Korean fonts (완성형) to a precomposed face and a jamo set

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
precomposed face where it fits the budget, or see [Choosing the number of sets](sets.md#choosing-the-number-of-sets).
`--chars ks-nonhanja` on the `rawcarve.py bdf` line keeps the symbols and the compatibility jamo as well (3,334 glyphs);
`bdfface.py` keeps only the syllables, `mkfont.py` reads the BDF at its own size: `mkfont.py $OUT/zn16-nh.bdf ... --size 16
--bpp 1 --unicode ksx1001-hangul,jamo` writes `123,880 bytes`, 2,444 glyphs, five syllables of the sample line `width=80`,
ink 310. `--unicode ksx1001-nohanja` stops there with Pillow's `raqm_get_glyphs() failed`: KS X 1001 A1A9 is U+00AD, the
soft hyphen, which the shaper drops; leave it out of the list (`--chars-from`). The `$SYS1Z16/24.FNT` files of the same CD are not syllables
(an IBM user area of pieces) and are not read.

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
