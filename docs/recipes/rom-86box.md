**English** | [한국어](rom-86box.ko.md)

# Recipes: Korean VGA font ROMs (86Box)

The three Korean VGA cards of the 86Box ROM set (Trigem, Kasan ET4000, ATI 28800): a 512 KB KS C 5601 font ROM read as a 128 x 128 grid and the VGA BIOS's English font, to a precomposed face and a jamo set, by hand or with the maker's built-in recipes.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The ROMs are dumps of proprietary chips, supplied separately. The method is the one of [Fonts inside programs and drivers](programs-and-drivers.md), which also writes `$OUT/ks.txt`.

Up: [Recipes index](../recipes.md) · Related: [Fonts inside programs and drivers](programs-and-drivers.md), [Korean font ROMs in MAME sets](rom-mame.md), [Desktop app and maker routes](desktop-routes.md).

<a id="korean-vga-font-roms-86box"></a>

## Korean VGA font ROMs (86Box)

Source: the 86Box ROM set (https://github.com/86Box/roms, commit 1ac40f2 of 2026-11-14), downloaded file by file (url,
bytes and sha256 recorded beside the files). Its tree lists three Korean VGA
cards, each a 32 KB VGA BIOS and a 512 KB KS C 5601 font ROM: Trigem Korean VGA (ET4000, `video/et4000/tgkorvga.bin`,
`tg_ksc5601.rom`), Kasan ET4000 (`et4000_kasan16.bin`, `kasan_ksc5601.rom`) and ATI 28800 Korean (`video/ati28800/
atikorvga.bin`, `ati_ksc5601.rom`); the other Korean entries are machine BIOSes (Samsung Deskmaster 286, Hyundai Super-16T,
LG IBM, TriGem 286M / 486G) with no Hangul font. The ROMs are dumps of proprietary chips [86Box Korean VGA ROM metadata and rendering](../recipes.md#ref-86box).

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

Other ROM sets checked: the openMSX system ROM set (file-hunter's RomDB, 1,241 files) holds three Korean fonts,
the jamo-set font in the Daewoo MSX2 SUB-ROMs, the 256 KB precomposed font of the CPC-400S and the 8x8 jamo cells of the
Korean MSX1 BIOS; the Hangul BASIC ROMs (`cpc-300_hangul`, `dpc-200_hangul`) hold the drivers, no glyphs
([Korean MSX fonts](rom-msx.md#korean-msx-fonts-msx2-and-msx1)).
An 88emuplayer ROM pack (`88emuplayer-roms.zip`) holds Roland sound-module ROMs (SC-55, SC-88, SC-8850, CM-300) and no font. The MAME romsets
are in [Korean font ROMs in MAME sets](rom-mame.md#korean-font-roms-in-mame-sets).

The desktop app knows the three pairs by size and SHA-256 (the built-in recipes `maker/recipes/86box-tgkorvga.json`,
`86box-kasan16.json`, `86box-atikorvga.json`: names, sizes, hashes and offsets, ROM data supplied separately): pick the folder holding both
files and the font ROM is one row with the faces `TGVGA16` / `KASAN16` / `ATIVGA16` (route `bdfface`) and the jamo sets
`TGVGA16J` / `KASAN16J` / `ATIVG16J` (`bdfface + from-svf fit`, experimental), made by the commands above. A run with
`SVF_MAKER_REAL_86BOX` pointing at the downloaded files (`maker/test/test_recipe.py`) gives every face of the table byte
for byte its size.

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
