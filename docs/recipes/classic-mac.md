**English** | [한국어](classic-mac.ko.md)

# Recipes: Classic Mac Korean bitmap fonts

Convert HangulTalk 1.0 `fbit`, HangulTalk 7.1.x type-3 `fbit`, and System 7.5.3–Mac OS 8.5 TrueType bitmap strikes to SVF.

**Before you start.** Run commands from the project root with `$OUT` set as in the [index](../recipes.md). Source fonts are proprietary and supplied separately. Every face ends with the checks of [Checking a face](../recipes.md#checking-a-face): `measure`, `line`, `fontmetrics.py`, `svf2to3.py --check` and `facecheck.py`. The check lines below use its sample line `안녕하세요 ABC 123`.

Up: [Recipes index](../recipes.md) · Related: [Outline fonts](outline-fonts.md), [Choosing the number of sets (벌 수)](sets.md), [Jamo sets](../jamo-sets.md).

<a id="classic-mac-font-inventory"></a>

## Font inventory

Every Korean font found in the font suitcases, font files and System files of each disk or CD, and the Latin bitmap fonts paired with them, measured from the files. Sizes are pixels (a Mac point is a pixel at 72 dpi).

**Codes.** **J** jamo-composed `fbit` (조합형: pieces composed into syllables). **P** precomposed `bloc`/`bdat` strikes (완성형: one bitmap per glyph). **O** TrueType outlines with no strikes. **L** Latin-only bitmap (`NFNT` or `FONT`): no Hangul at that size. **X** archive the tools do not convert. **=** the same font resources as the previous version. **—** not on the disk or CD.

<a id="classic-mac-overview"></a>

### Overview

| Family | HangulTalk 1.0 (1988) | 7.1.2 (1994) | 7.5.3 (1996) | 7.6.1 (1997) | 8.5 (1998) | 8.6 (1999) |
| --- | --- | --- | --- | --- | --- | --- |
| Gotic | J 12; L 12 | — | — | — | — | — |
| Munjo | J 12, 16, 24; L 12, 18, 24 | — | — | — | — | — |
| Seoul | — | J 12; L 9, 12 | P 9, 10, 12, 14, 16, 18, 20, 24; L 9, 10, 12, 14, 16, 18, 20, 24; J 12 (installer, = 7.1.2) | = (no J 12) | P 9, 10, 12, 14, 16, 18, 20, 24 (redrawn); L 9, 10, 12, 14, 16, 18, 20, 24 (new) | = |
| AppleGothic | — | J 12, 24; O; L 12, 24 | P 9, 10, 12, 14, 16, 18, 20, 24; L 9, 10, 12, 14, 16, 18, 20, 24 | = | P = (new cmap); L = | — |
| AppleMyungjo | — | J 12, 24; O; L 9, 12, 24 | P 9, 10, 12, 14, 16, 18, 20, 24; L 9, 10, 12, 14, 16, 18, 20, 24 | = | P = (new cmap); L = | — |
| #PC명조, #신명조, #궁서체, #중고딕, #필기체, #공작체, #태그래픽 | — | — | P 9, 10, 12, 14, 16, 18, 20, 24; L 9, 10, 12, 14, 16, 18, 20, 24 | = | — | — |
| #헤드라인A | — | — | P 18, 20, 24; L 18, 20, 24 | = | — | — |
| 한강체 (Hangang) | — | — | — | — | P 9, 10, 12, 14, 16, 18, 20, 24; L 9, 10, 12, 14, 16, 18, 20, 24 | — |
| KSSymbol | — | 12 (`fbit` type 0, not read); X 24 | — | — | — | — |
| Hanja24, GHanja24, GSymbol24 | — | X 24 | — | — | — | — |

<a id="classic-mac-pixel-sizes"></a>

### Pixel sizes

One cell answers "does family F exist at N px?". Hangul sizes are J or P; L alone means a Latin-only bitmap. Every 7.5.3–8.5 suitcase also carries L at each of its P sizes (not repeated below).

| px | Gotic | Munjo | Seoul | AppleGothic | AppleMyungjo | #PC명조, #신명조, #궁서체, #중고딕, #필기체, #공작체, #태그래픽 | #헤드라인A | 한강체 | KSSymbol, Hanja |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 | — | — | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 =; 7.1.2 L only | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 =, 8.5 =; 7.1.2 L only | 7.5.3 P, 7.6.1 = | — | 8.5 P | — |
| 10 | — | — | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | — | 8.5 P | — |
| 12 | 1.0 J and L | 1.0 J and L | 7.1.2 J (7.5.3 installer =); 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 =; 7.1.2 L | 7.1.2 J and L; 7.5.3 P, 7.6.1 =, 8.5 = | 7.1.2 J and L; 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | — | 8.5 P | KSSymbol12 7.1.2 (not read) |
| 14 | — | — | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | — | 8.5 P | — |
| 16 | — | 1.0 J | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | — | 8.5 P | — |
| 18 | — | 1.0 L only | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | 7.5.3 P, 7.6.1 = | 8.5 P | — |
| 20 | — | — | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | 7.5.3 P, 7.6.1 = | 8.5 P | — |
| 24 | — | 1.0 J and L | 7.5.3 P, 7.6.1 =, 8.5 P (redrawn), 8.6 = | 7.1.2 J and L; 7.5.3 P, 7.6.1 =, 8.5 = | 7.1.2 J and L; 7.5.3 P, 7.6.1 =, 8.5 = | 7.5.3 P, 7.6.1 = | 7.5.3 P, 7.6.1 = | 8.5 P | 7.1.2 X (KSSymbol24Disk, Hanja24Disk, GHanja24Disk, GSymbol24Disk) |

**How measured.** `fbit` fonts by the conversion commands below (`jamoset.py --check`, `macfbit3.py info`, `macfbit_svf.py build` and `verify`). TrueType fonts with fontTools: `maxp`, the `bloc` strikes (ppem, glyphs per strike) and the `bdat` image formats. Only formats 2, 5 and 6 (whole glyph bitmaps) occur, never the component formats 8 and 9, so every strike is precomposed. Syllable, jamo and Hanja counts come from the cmap: the Mac Korean (1,3) subtable decoded as KS X 1001 (as `macsfnt.py unicode` does), or the font's own Unicode subtable. `FOND`, `NFNT` and `FONT` are read from the resource forks; "=" compares the font resources (`FOND`, `NFNT`, `FONT`, `sfnt`, `fbit`, `fdef`) byte for byte.

### HangulTalk 1.0 (Korean System 4.1, 1988)

Where: the System Disk's `System Folder`.

| File | Resources | Holds | Bytes |
| --- | --- | --- | --- |
| `Gotic12` | `fbit` 17408 (12,380 B), `fdef` 3 (2,398 B) | J 12 | 15,587 |
| `Munjo12` | `fbit` 17409 (12,380 B), `fdef` 3 (2,398 B) | J 12 | 15,587 |
| `Munjo16` | `fbit` 17409 (21,554 B), `fdef` 3 (2,398 B) | J 16 | 24,761 |
| `Munjo24` | `fbit` 17409 (47,714 B), `fdef` 3 (2,398 B) | J 24 | 50,921 |
| `System` | `FOND` 17408 Gotic: 12 pt `FONT` 23052 (236 glyphs, codes 0–255); `FOND` 17409 Munjo: 12, 18, 24 pt `FONT` 14220, 14226, 14232 (231 glyphs each) | L 12 (Gotic); L 12, 18, 24 (Munjo) | 319,117 |
| two extension files | `fbit` records of 76–232 B; `fdef` 0, 1, 2 (in the first) | no glyphs | 33,392; 13,694 |

| Font | Glyphs | Hangul | Hanja |
| --- | --- | --- | --- |
| `Gotic12`, `Munjo12`, `Munjo16`, `Munjo24` | 653 pieces each, sets 20/15/4 (`fdef` rule) | 11,172 syllables + 51 jamo | 0 |

- No Hanja and no Latin in the `fbit` fonts. The Utilities disk's `Fonts` suitcase holds Latin fonts only.

### HangulTalk 7.1.2 CD (1994)

| File | Folder | Resources | Holds | Bytes |
| --- | --- | --- | --- | --- |
| `Seoul12` | `Hangul System Install/Disk Tools/한글 시스템/자형 폴더` | `fbit` 17408 (8,760 B) | J 12 | 9,669 |
| `Seoul12`, `AppleGothic12`, `AppleGothic24`, `AppleMyungjo12`, `AppleMyungjo24` `[splt]` | More Additions font files | `JM` archive of an `fbit` (8,760 B at 12 px, 34,788 B at 24 px); `Seoul12` equals the installed one | J 12, 12, 24, 12, 24 | 1,843; 2,707; 5,095; 3,194; 6,464 (data forks) |
| `Seoul` suitcase | More Additions | `FOND` 17408; `NFNT` 1025 (9 pt, 231 glyphs), 1026 (12 pt, 232) | L 9, 12 | 5,824 |
| `AppleGothic` suitcase | More Additions | `FOND` 17410; `NFNT` 1025 (12 pt), 1026 (24 pt), 231 glyphs each | L 12, 24 | 13,014 |
| `AppleMyungjo` suitcase | More Additions | `FOND` 17409; `NFNT` 1025 (9 pt), 1026 (12 pt), 1027 (24 pt), 231 glyphs each | L 9, 12, 24 | 16,617 |
| `System` | `Disk Tools/한글 시스템`, `InstallMeFirst` | `FOND` 17408 Seoul: `NFNT` 7545 (9 pt, 231 glyphs, = suitcase 1025), 5828 (12 pt, 232) | L 9, 12 | 722,913; 881,097 |
| `InputBackSupport` | `More Additions/Extensions`, `Disk Tools/한글 시스템/확장 파일` | `HTBL` 1 (9,816 B, the same in both), `fbit` records of 40–232 B | composition table | 107,626; 80,180 |
| AppleGothic, AppleMyungjo TrueType | installer `part` resources (joined) | `sfnt`, no `bloc`/`bdat` | O | 3,233,432; 4,767,960 |
| `KSSymbol12` `[splt]` | More Additions | `fbit` handler type 0, 12 px, codes A141–ADFE | not read | 22,640 |
| `KSSymbol24Disk`, `Hanja24Disk`, `GHanja24Disk`, `GSymbol24Disk` `[splt]` | More Additions | `JM` archives | X 24 | 51,504; 231,388; 211,152; 51,510 |

| Font | Glyphs | Hangul | Hanja |
| --- | --- | --- | --- |
| `Seoul12` | 482 planes, 207 pieces | 2,350 syllables + 51 jamo | 0 |
| `AppleGothic12` | 482 planes, 364 pieces | 2,350 + 51 | 0 |
| `AppleGothic24` | 482 planes, 455 pieces | 2,350 + 51 | 0 |
| `AppleMyungjo12` | 482 planes, 395 pieces | 2,350 + 51 | 0 |
| `AppleMyungjo24` | 482 planes, 465 pieces | 2,350 + 51 | 0 |
| AppleGothic (O) | 9,924 | 2,350 syllables | 4,888 |
| AppleMyungjo (O) | 9,926 | 2,350 syllables | 4,888 |

- Pieces are the distinct bitmaps of the `direct` face; `verify` composes all 2,350 + 51 exactly. Every J font here is type 3 and needs the `HTBL` 1.
- Archives: `KSSymbol24Disk` unpacks to 176,091 bytes that are not a resource fork; `Hanja24Disk`, `GHanja24Disk` and `GSymbol24Disk` fail in the `JM` decoder. The headers of both Hanja archives give 353,300 unpacked bytes (24 px Hanja, by name). No 12 px Hanja archive is on the CD.
- The TrueType Hanja are exactly the 4,888 KS X 1001 Hanja (rows CA–FD).

### Korean System 7.5.3 CD (1996)

| File | Folder | Resources | Holds |
| --- | --- | --- | --- |
| `NAME[FFIL]` (11 families) | `Bitmap 서체 설치/NAME` | `FOND`; `NFNT` at each strike size (232 glyphs; 233 in AppleGothic 24 pt and #궁서체 20 pt); `sfnt` with `bloc`/`bdat`, no `glyf` | P and L |
| `NAME [fbit]` (11) | `Bitmap 서체 설치/NAME` | 8 `fbit` records (3 for #헤드라인A) of 401–1,463 B, `fdef` 42 (6,418 B) | strike descriptors, no glyphs |
| `NAME[FFIL]`, `NAME [fbit]` (11) | `한글 시스템 설치/Font Folder` | as above, `sfnt` with `glyf` and the same `bdat` | P, O and L |
| AppleGothic, AppleMyungjo, Seoul `[FFIL]` and `[fbit]` | `한글 시스템/자형 폴더` | = the Font Folder copies | P, O and L |
| `Seoul12` | `한글 시스템 설치/Install Disk 1/자형 폴더` | `fbit` 17408, = 7.1.2 | J 12 |
| `InputBackSupport` | `한글 시스템/확장 파일`, `Install Disk 1/확장 파일` | `fbit` records of 40–232 B | no glyphs |
| `빛한글` | `한글 시스템/확장 파일` | `fdef` 42 (6,418 B) | no glyphs |

The `System` file has no Korean `FOND` or `sfnt`.

| Font | Strikes (ppem) | Glyphs | Hangul syllables | Hanja | KS X 1001 codes | Bitmap-only sfnt | Font Folder sfnt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AppleGothic | 9, 10, 12, 14, 16, 18, 20, 24 | 10,553 | 2,350 | 4,888 | 8,329 | 4,081,028 B | 8,475,352 B |
| AppleMyungjo | 9, 10, 12, 14, 16, 18, 20, 24 | 10,553 | 2,350 | 4,888 | 8,329 | 4,081,884 B | 10,353,128 B |
| Seoul | 9, 10, 12, 14, 16, 18, 20, 24 | 9,889 | 2,350 | 4,888 | 8,329 | 2,626,404 B | 6,159,836 B |
| #PC명조 | 9, 10, 12, 14, 16, 18, 20, 24 | 9,889 | 2,350 | 4,888 | 8,329 | 2,624,600 B | 7,789,420 B |
| #신명조 | 9, 10, 12, 14, 16, 18, 20, 24 | 9,889 | 2,350 | 4,888 | 8,329 | 2,627,040 B | 7,799,156 B |
| #궁서체 | 9, 10, 12, 14, 16, 18, 20, 24 | 9,889 | 2,350 | 4,888 | 8,329 | 2,624,992 B | 8,925,292 B |
| #중고딕 | 9, 10, 12, 14, 16, 18, 20, 24 | 9,889 | 2,350 | 4,888 | 8,329 | 2,625,516 B | 6,316,044 B |
| #필기체 | 9, 10, 12, 14, 16, 18, 20, 24 | 5,001 | 2,350 | 0 | 3,441 | 1,316,028 B | 3,005,080 B |
| #공작체 | 9, 10, 12, 14, 16, 18, 20, 24 | 5,001 | 2,350 | 0 | 3,441 | 1,315,032 B | 2,553,292 B |
| #태그래픽 | 9, 10, 12, 14, 16, 18, 20, 24 | 5,001 | 2,350 | 0 | 3,441 | 1,315,024 B | 2,572,344 B |
| #헤드라인A | 18, 20, 24 | 2,768 | 2,350 | 0 | 2,547 | 448,400 B | 1,091,116 B |

- Every strike holds every glyph. The Font Folder `bdat` and `bloc` equal the bitmap-only copies' byte for byte.
- KS X 1001 codes are the Mac Korean (1,3) entries that decode as KS X 1001 (Seoul: 8,329 of 9,799). Every font has 93 compatibility jamo. Codes outside KS X 1001 (Apple additions): 1,470 in the fonts with Hanja, 1,522 in #필기체, #공작체, #태그래픽, 195 in #헤드라인A.
- Hanja are exactly the 4,888 KS X 1001 Hanja (rows CA–FD); no other code decodes to Hanja. #필기체, #공작체, #태그래픽 and #헤드라인A have none.

Why Seoul has 9,889 glyphs:

| Glyphs | Count |
| --- | --- |
| Hangul syllables | 2,350 |
| Hanja | 4,888 |
| KS X 1001 symbols | 894 |
| Compatibility jamo | 93 |
| ASCII (104 codes) | 103 |
| Apple extension symbols (lead A1–AD, trail 41–A0) | 1,197 |
| KS-range codes with no Unicode mapping | 235 |
| Single-byte Mac characters | 38 |
| Blank, no code reaches them | 91 |
| **Total** | **9,889** |

AppleGothic and AppleMyungjo (10,553) have the same coded glyphs and 755 that no code reaches: 664 proportional forms and 91 others, blank except one inked glyph in AppleGothic (glyph 198).

Proportional forms (only AppleGothic and AppleMyungjo have a `mort` table; the other nine faces have `feat` only):

| Item | AppleGothic | AppleMyungjo |
| --- | --- | --- |
| `feat` | Vertical Substitution; Text Spacing Type → Proportional Text | the same |
| `mort` flag 0x1 (proportional) | 2 noncontextual subtables, 664 substitutions each | the same |
| `mort` flag 0x2 (vertical) | 1 subtable, 83 substitutions | the same |
| Proportional targets narrower than the full width | 572 | 525 |
| Example | A1A4: advance 1,024 → 244 (of 1,024 units) | the same |

| KS lead row | A1 | A2 | A3 (full-width ASCII) | A5 (Roman numerals, Greek) | A7 (units) | A8 | A9 | AA (hiragana) | AB (katakana) | AC (Cyrillic) | AD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Proportional forms | 85 | 75 | 89 | 70 | 79 | 9 | 9 | 80 | 86 | 66 | 16 |

- None are in rows A4 (jamo) or A6 (box drawing), or among syllables and Hanja. No code reaches them, so the tools, which take glyphs through the cmap, leave them out; a tool option for them is planned.
- Vertical: 42 substitutions map codes in rows A1, A2, A3 and A5 to vertical forms reached through Apple extension codes (A1A2 → A250); 41 map proportional forms to proportional vertical forms.

### Mac OS 7.6.1 (1997), 8.5 (1998), 8.6 (1999)

| Version | File | Folder | Resources | Against the previous version |
| --- | --- | --- | --- | --- |
| 7.6.1 | 11 `NAME[FFIL]`, `NAME [fbit]` | `CD Extras/Bitmap 서체 설치/NAME` | as 7.5.3 | = (only `fwst`, `movp`, `vers` differ) |
| 7.6.1 | 11 `NAME[FFIL]`, `NAME [fbit]` | `소프트웨어 설치/Mac OS 7.6/Font Folder` | as 7.5.3 | = |
| 7.6.1 | AppleGothic, AppleMyungjo, Seoul, #신명조, #궁서체, #필기체 | `한글 시스템/자형 폴더` | as the Font Folder | = |
| 8.5 | `AppleGothic[FFIL]` (8,555,706 B) | `한글 시스템/자형 폴더` | `sfnt` 8,522,116 B; `NFNT` = 7.5.3 (10 pt renumbered 1030 → 32763) | `bdat`, `bloc` =; `cmap` (Unicode subtable added), `head`, `hhea` changed |
| 8.5 | `AppleMyungjo[FFIL]` (10,435,418 B) | `한글 시스템/자형 폴더` | `sfnt` 10,399,888 B; `NFNT` = | `bdat`, `bloc` =; `cmap`, `head`, `hhea` changed |
| 8.5 | `Seoul[FFIL]` (6,254,122 B) | `한글 시스템/자형 폴더` | `sfnt` 6,216,700 B; `NFNT` 32698–32705 (255 glyphs) | redrawn: 9,912 glyphs, new `bdat`; 13 tables differ |
| 8.5 | `한강체[FFIL]` (7,303,606 B) | `한글 시스템/자형 폴더` | `sfnt` 7,263,828 B; `NFNT` 32747–32754 (255 glyphs) | new |
| 8.5 | `AppleGothic [fbit]`, `AppleMyungjo [fbit]`, `Seoul [fbit]`, `한강체 [fbit]` (18,821; 18,833; 16,358; 18,017 B) | `한글 시스템/자형 폴더` | 8 `fbit` records of 1,367–1,966 B; `fdef` 42 `Main` (6,418 B) except Seoul | strike descriptors, no glyphs |
| 8.5 | `.Last Resort` | `한글 시스템/System`, `한글 소프트웨어 설치/시스템 소프트웨어/Mac OS 8.5/System Extras` | `sfnt` −4 (262,500 B), 247 glyphs | not a Korean face: maps all 11,172 syllables to placeholder glyphs |
| 8.6 | `Seoul[FFIL]`, `Seoul [fbit]` | `한글 시스템/자형 폴더` | as 8.5 | = |
| 8.6 | `.Last Resort` | `한글 시스템/System`, `한글 소프트웨어 설치/시스템 소프트웨어/Mac OS 8.6/System Morsels` | `sfnt` −4 (262,500 B) | same size, other bytes; not a Korean face |

- The 8.5 `NFNT` ids 32698–32705 (Seoul) and 32747–32754 (한강체) are the strikes 9, 10, 12, 14, 16, 18, 20, 24 pt.
- 한강체: precomposed, strikes 9, 10, 12, 14, 16, 18, 20, 24; 9,914 glyphs; 2,350 syllables, 94 jamo, 4,888 Hanja (the KS X 1001 set), 8,474 Unicode codes. Its Mac cmap also has 2 codes in the Hanja rows outside KS X 1001 (DBA0, E162): glyphs `uniDBA0`/`uniE162`, not reached by the Unicode cmap, so not extra Hanja.
- 8.5 and 8.6: of the font suitcases and System files, only the faces above are Korean. 8.6 has no AppleGothic, AppleMyungjo or 한강체 among them.

<a id="classic-mac-korean-bitmap-fonts"></a>

## HangulTalk 1.0 `fbit` fonts

Bitmap fonts from Korean System 4.1 / HangulTalk 1.0 (1988, Apple Korea / Elex Computer). Each resource fork holds an `fbit` resource of 45 glyph sets and an `fdef` driver with 18 lookup tables, composing all 11,172 syllables as the Mac draws them. The fonts hold Hangul only, with no space glyph and no Latin letters.

**Input:** resource fork file (`Gotic12.rsrc`, `Munjo12.rsrc`, `Munjo16.rsrc`, `Munjo24.rsrc`).

```sh
python3 tools/jamoset.py --layout mac-fbit-45sets Munjo24.rsrc --symbols --check -o $OUT/MUNJO24J.SVF
```

Omit `--symbols` to keep only the font's own glyphs without the `…` and `□` drawn by `jamoset.py`.

- `Munjo24.rsrc`: `macsfnt.py list` shows `fbit` 17409 (47,714 B) and `fdef` 3 (2,398 B). With `--symbols`, `--check` prints `composed 11172 syllables from 655 glyphs`, in about 1.0 s.
- Maker local mode (`detect.scan(..., local=True)`): "HangulTalk 1.0 fbit (45 sets), 24 x 24" (Munjo24; 12 x 12 for Gotic12 and Munjo12, 16 x 16 for Munjo16), source kind `mac-fbit1`, coverage 2,350 KS / 11,172 syllables + 51 jamo, route `mac fbit 1.0`. Upload mode: "Mac bitmap font (NFNT/fbit): not converted here (local-only mode)".

| Font | Size | Glyphs / pieces | Cell | Ascent / descent | Check line (`안녕하세요 ABC 123`) |
| --- | --- | --- | --- | --- | --- |
| `Munjo24` (`--symbols`) | 36,660 B | 653 pieces (20/15/4 sets, 8x4 classes, 11,172 syllables) | 24x24 | 24 / 0 | `width=120`, ink 591, `IoU 1.000` |
| `Gotic12` (`--symbols`) | 23,368 B | 653 pieces (20/15/4 sets, 8x4 classes, 11,172 syllables) | 12x12 | 12 / 0 | `width=60`, ink 175, `IoU 1.000` |

![Gotic12 of HangulTalk 1.0 as a 12x12 jamo set: two Korean lines only, x2](../images/recipes/mac/ht10-gotic12.png)

*Korean System 4.1 / HangulTalk 1.0 (1988) `Gotic12`, built without `--symbols` (`23,304 B`, 12x12, ascent 12, descent 0). Hangul only, so only the two Korean lines appear; space advances half a cell because the font has no space glyph. x2.*

![Munjo24 of HangulTalk 1.0 as a 24x24 jamo set: two Korean lines only, x2](../images/recipes/mac/ht10-munjo24.png)

*`Munjo24` from the same disk (1988), built without `--symbols` (`36,564 B`, 24x24, ascent 24, descent 0). Hangul only, with no Latin, space, or symbols. x2.*

<a id="classic-mac-hangultalk-71"></a>

## HangulTalk 7.1.x type-3 `fbit` fonts

Type-3 `fbit` fonts (`Seoul12`, `AppleGothic12/24`, `AppleMyungjo12/24`) from Korean System 7.1.2 / HangulTalk 7.1.2 (1994, Apple Korea / Elex Computer). They compose the 2,350 KS X 1001 syllables and 51 compatibility jamo using the `HTBL` 1 table from `InputBackSupport`. KS X 1001 symbols live in separate `KSSymbol12` / `KSSymbol24Disk` archives that these tools do not read.

**Input:** `InputBackSupport[INIT].rsrc`, the font `[splt]` data fork (for example `Seoul12[splt].data`), and optionally the family suitcase (`Seoul[FFIL].rsrc`, etc.) for Latin `NFNT` strikes.

```sh
python3 maker/srcprep.py mac-htbl "InputBackSupport[INIT].rsrc" $OUT/HTBL1.bin
python3 tools/macfbit3.py unpack "Seoul12[splt].data" $OUT/Seoul12.rsrc
python3 tools/macfbit3.py fbit $OUT/Seoul12.rsrc $OUT/Seoul12.fbit
python3 tools/macfbit3.py bdf $OUT/Seoul12.fbit $OUT/HTBL1.bin Seoul12 $OUT/seoul12.bdf
python3 tools/macfbit_svf.py build $OUT/Seoul12.fbit $OUT/HTBL1.bin -o $OUT/SEOUL12J.SVF
python3 tools/macfbit_svf.py build $OUT/Seoul12.fbit $OUT/HTBL1.bin --mode derived -o $OUT/SEOUL12D.SVF
python3 tools/macfbit_svf.py verify $OUT/SEOUL12J.SVF $OUT/Seoul12.fbit $OUT/HTBL1.bin
```

- `direct` (default) keeps the Mac structure as a JMAP and composes only the 2,350 KS syllables exactly.
- `derived` fits a JSET for all 11,172 syllables; the 8,822 non-KS syllables are extrapolated, not Mac output.
- Pass `--latin "Seoul[FFIL].rsrc"` to `macfbit_svf.py build` to include Latin letters from the family suitcase.
- For a precomposed face, run `srcprep.py bdf-pixel-size` and `mkfont.py` on the BDF below, or pass the BDF to `bdfface.py --hangul` with a separate `--ascii` font and `--cell 12x12 --chars-from $OUT/ks.txt`.

```sh
# Precomposed BDF route (no Latin companion needed)
python3 maker/srcprep.py bdf-pixel-size $OUT/seoul12.bdf $OUT/seoul12-sized.bdf --size 12
python3 tools/mkfont.py $OUT/seoul12-sized.bdf $OUT/seoul12.svf --size 12 --bpp 1 --unicode ascii,ksx1001-hangul

# Shrink a derived face for an MCU budget (takes about 2 minutes)
python3 tools/jamomerge.py merge --face $OUT/SEOUL12D.SVF --points 8192 7168 --prefix SM -o $OUT/SMALL
```

| Font / mode | Size | Glyphs / pieces | Cell | Ascent / descent | Check line (`안녕하세요 ABC 123`) |
| --- | --- | --- | --- | --- | --- |
| `Seoul12` direct | 15,016 B | 207 pieces (KS 2,350 + 51 jamo) | 12x12 | 10 / 2 | `width=60`, ink 142, `ks_bad 0` |
| `Seoul12` derived | 9,716 B (v2: 7,928 B) | 219 pieces (9/6/3 sets, 8x4, 11,172 syllables) | 12x12 | 10 / 2 | `width=60`, ink 142, `ks_bad 0` |
| `Seoul12` direct + Latin | 17,924 B | 207 pieces + ASCII | 12x12 | 10 / 2 | `width=111`, ink 253, `ks_bad 0` |
| `Seoul12` derived + Latin | 12,624 B | 219 pieces + ASCII | 12x12 | 10 / 2 | `width=111`, ink 253, `ks_bad 0` |
| `Seoul12` BDF + `mkfont.py` | 103,012 B | 2,350 glyphs | 12x12 | 10 / 2 | `width=60`, ink 142 |
| `Seoul12` `jamomerge` 8K / 7K | 7,964 B / 7,032 B | 191 pieces (7K, 7/6/3 sets) | 12x12 | 10 / 2 | verified |
| `AppleGothic12` direct + Latin | 22,860 B | 364 pieces + ASCII | 12x12 | 10 / 2 | `width=122`, ink 285, `ks_bad 0` |
| `AppleMyungjo24` direct + Latin | 37,244 B | 465 pieces + ASCII | 24x24 | 20 / 4 | `width=242`, ink 944, `ks_bad 0` |

- Seoul12 run: `HTBL1.bin` 9,816 B; `unpack` prints `JM 1843 -> 9673 bytes`; `fbit` 8,760 B; `bdf` 2,401 glyphs. The Latin letters add 1,388 B to the direct face.
- Maker local mode: the `splt` file, the font fork and a raw fork read as "HangulTalk 7.1 type-3 fbit, 12 px, 482 planes (needs HTBL 1)" (source kind `mac-fbit3`, coverage 2,350 + 51), routes `mac fbit 7.1 direct`, `derived` and `bdf + mkfont`. The extension reads as "HangulTalk 7.1 HTBL 1 (InputBackSupport): the composition table", `Seoul[FFIL]` as "Mac bitmap suitcase (FOND + NFNT): Latin strikes at 9, 12 pt".

![Seoul12 of HangulTalk 7.1.2, direct face with Latin from Seoul suitcase, x2](../images/recipes/mac/ht712-seoul12.png)

*Korean System 7.1.2 / HangulTalk 7.1.2 CD (1994) `Seoul12`, `direct` with 12 pt `NFNT` from `Seoul[FFIL]` (`17,924 B`, 12x12, ascent 10, descent 2). No KS X 1001 symbols. x2.*

![AppleGothic12 of HangulTalk 7.1.2, direct face with Latin from AppleGothic suitcase, x2](../images/recipes/mac/ht712-applegothic12.png)

*`AppleGothic12` from the same CD (1994), `direct` with 12 pt `NFNT` from `AppleGothic[FFIL]` (`22,860 B`, 12x12, ascent 10, descent 2). No KS X 1001 symbols. x2.*

![AppleMyungjo24 of HangulTalk 7.1.2, direct face with Latin from AppleMyungjo suitcase, x2](../images/recipes/mac/ht712-applemyungjo24.png)

*`AppleMyungjo24` from the same CD (1994), `direct` with 24 pt `NFNT` from `AppleMyungjo[FFIL]` (`37,244 B`, 24x24, ascent 20, descent 4). No KS X 1001 symbols, and the backtick (`` ` ``) is blank in the 24 pt `NFNT`. x2.*

<a id="classic-mac-truetype-bitmap-strikes"></a>

## TrueType bitmap strikes (System 7.5.3–Mac OS 8.5)

Starting with Korean System 7.5.3 (1996, earliest examined; 7.5.1 still ships the `fbit` Seoul12) through Mac OS 8.5 (1998), Korean fonts are TrueType in `FFIL` suitcases. Their `bloc`/`bdat` tables hold 1 bpp bitmap strikes at 9, 10, 12, 14, 16, 18, 20, and 24 ppem; convert them via the [Mac-format TrueType](outline-fonts.md#mac-format-truetype) route ([Embedded bitmap strikes](bitmap-fonts.md#embedded-bitmap-strikes)).

**Input:** `FFIL` resource fork (bitmap-only copies in the 7.5.3 CD's `Bitmap 서체 설치` folder, or `한강체[FFIL].rsrc` in Mac OS 8.5's `자형 폴더`).

```sh
python3 tools/macsfnt.py extract "AppleGothic[FFIL].rsrc" $OUT/AppleGothic.ttf
python3 tools/macsfnt.py unicode $OUT/AppleGothic.ttf $OUT/AppleGothicU.ttf
python3 tools/mkfont.py $OUT/AppleGothicU.ttf $OUT/agothic16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
```

- `--size` must be one of the font's strikes: 9, 10, 12, 14, 16, 18, 20, 24 (#헤드라인A: 18, 20, 24).
- Off-strike sizes: a full font (outlines plus strikes, such as 한강체) is rasterised from its outlines (17 px: `133,288 B`); a bitmap-only copy does not open (`invalid pixel size`).
- Mac OS 8.5 `한강체` (Hangang) already has a Unicode cmap, so skip `macsfnt.py unicode`.
- Hanja: `--unicode ascii,ksx1001` (the `ksx1001` preset holds symbols, jamo, 2,350 syllables and 4,888 Hanja) takes them. 7.5.3 bitmap-only Seoul at 16 px: `424,316 B`, 8,319 glyphs (2 of the preset are not in the font).

Source: Korean System 7.5.3, the CD for the Power Macintosh 7220 (1996); the fonts say "1994-1995 Elex Computer". Running the commands above on 7.5.3 bitmap-only `AppleGothic` 16 px produces a precomposed face of `123,360 B` with 2,446 glyphs. The table below lists sample faces holding only the characters of the four sample lines (`--unicode file:`).

| Font (strike) | Size | Cell | Ascent / descent | Missing |
| --- | --- | --- | --- | --- |
| AppleGothic 12 (7.5.3) | 4,828 B | 12x12 | 9 / 3 | `_` (falls below the cell) |
| AppleGothic 16 (7.5.3) | 5,596 B | 16x16 | 13 / 3 | none |
| AppleMyungjo 16 (7.5.3) | 5,844 B | 16x16 | 13 / 3 | none |
| AppleMyungjo 24 (7.5.3) | 8,824 B | 24x24 | 19 / 5 | none |
| Seoul 12 (7.5.3) | 4,772 B | 12x12 | 10 / 2 | none |
| Seoul 16 (7.5.3) | 5,536 B | 16x16 | 13 / 3 | none |
| #신명조 16 (7.5.3) | 5,368 B | 16x16 | 12 / 4 | none |
| #궁서체 16 (7.5.3) | 5,228 B | 16x16 | 12 / 4 | none |
| 한강체 (Hangang) 16 (Mac OS 8.5) | 5,748 B | 16x16 | 13 / 3 | none |

![Seoul of Korean System 7.5.3 at its strikes, one line per size (9, 10, 12, 14, 16, 18, 20, 24 px): the size, a Korean pangram, ABC 123, x2](../images/recipes/mac/kh753-seoul-sizes.png)

*Korean System 7.5.3 (1996) Seoul, bitmap-only copy, at its strikes (9, 10, 12, 14, 16, 18, 20, 24 ppem); each line is drawn on that strike's face. The space advance is 2 px at 9 ppem and 3 px at 10 and 12 ppem, so the word gaps there are narrow. x2.*

![AppleGothic 12 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-applegothic12.png)

*Korean System 7.5.3 (1996) AppleGothic 12 ppem bitmap-only strike. `_` is omitted because it lies below the 12x12 cell. x2.*

![AppleGothic 16 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-applegothic16.png)

*Korean System 7.5.3 (1996) AppleGothic 16 ppem strike. x2.*

![AppleMyungjo 16 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-applemyungjo16.png)

*Korean System 7.5.3 (1996) AppleMyungjo 16 ppem strike. x2.*

![AppleMyungjo 24 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-applemyungjo24.png)

*Korean System 7.5.3 (1996) AppleMyungjo 24 ppem strike. x2.*

![Seoul 12 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-seoul12.png)

*Korean System 7.5.3 (1996) Seoul 12 ppem strike. x2.*

![Seoul 16 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-seoul16.png)

*Korean System 7.5.3 (1996) Seoul 16 ppem strike. x2.*

![#신명조 (Shin Myeongjo) 16 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-shinmyungjo16.png)

*Korean System 7.5.3 (1996) #신명조 (Shin Myeongjo) 16 ppem strike. x2.*

![#궁서체 (Gungseo) 16 px strike of Korean System 7.5.3, x2](../images/recipes/mac/kh753-gungseo16.png)

*Korean System 7.5.3 (1996) #궁서체 (Gungseo) 16 ppem strike. x2.*

![Hangang 16 px strike of Mac OS 8.5 Korean, x2](../images/recipes/mac/kh85-hangang16.png)

*Mac OS 8.5 Korean (1998) 한강체 (Hangang) 16 ppem strike. x2.*

<a id="classic-mac-samples"></a>

## Making the samples

The 15 sample images above (38,050 B total) render at x2 scale; all but the Seoul sizes image draw four lines: two Korean pangrams, one English line, and ASCII plus KS X 1001 symbols (`※☆★○●◎◇◆□■△▲→←↑↓`). Characters missing from a face are omitted. `tools/doc_figures_mac.py` draws them directly from your source folders without storing font copies in the repository.

```sh
python3 -I tools/doc_figures_mac.py --ht10 "$SRC/HT10/System Folder" --ht712 "$SRC/HT712/More Additions" \
    --htbl "$SRC/HT712/InputBackSupport[INIT].rsrc" --kh753 "$SRC/KH753/Bitmap 서체 설치" \
    --kh85 "$SRC/KH85/한글 시스템/자형 폴더" [--check]
```

`--check` compares against the committed PNGs byte for byte and fails if any face is skipped ([tool reference](../tools.md#toolsdoc_figures_macpy)).

## Notes

- **Maker local mode:** The desktop app reads these fonts in place and writes faces only to the folder you choose. See the [maker desktop guide](../maker-desktop.md), [route table](desktop-routes.md#desktop-app-and-maker-routes), and [Apple font tables and resource forks](../recipes.md#ref-apple).
- **HangulTalk 7.5.1 differences:** `Seoul12[fbit]` on the 7.5.1 installer disk is byte-identical to 7.1.2 (8,760 B). The 7.5.1 copy of `InputBackSupport` is compressed, so `srcprep.py mac-htbl` refuses it.
- **Bitmap-only TrueType:** The 7.5.3 `Bitmap 서체 설치` copies have no outlines and no `head` table. `mkfont.py` reads per-glyph advances from strike metrics via fontTools, and non-strike sizes fail to open.
- **NFNT shifts:** `macfbit_svf.py` shifts Latin glyphs that extend past the cell back inside (`AppleGothic12` `W` -1 px, `AppleMyungjo24` `j` +1 px).
- **Real-file tests:** `tools/test_macfbit3.py` and `tools/test_macfbit_svf.py` run on synthetic `fbit`, `HTBL` and `NFNT` data. Real files add checks: `JOHAB_FONTS` names a tree holding `mac/extracted/kh10_system_disk/System Folder/*.rsrc` and the reference renderer (1.0, in `tools/test_jamoset.py`); `MACFBIT3_CD712` the 7.1.2 CD tree; `SVF_MAC71_INPUTS` a folder of `Name.fbit` and `Name.htbl1` files. The 1.0 golden file (`tools/testdata/mac-fbit-golden.json`) is not shipped.
- **Sample reproducibility:** `fbit` images depend only on the font files; strike images also depend on Pillow and FreeType (built with Pillow 10.2.0 and FreeType 2.13.2).

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
