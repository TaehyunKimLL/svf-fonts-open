**English** | [한국어](FACES.ko.md)

| face file | derived from (source, version) | copyright / author | licence | licence file | how it was made |
|---|---|---|---|---|---|
| `svf/dos/PAPLG16.SVF` (ASCII, 2 bpp, 18 px cell, 149 glyphs) | Paperlogy-4Regular.ttf, Paperlogy 4 Regular version 1.000 | Copyright (c) 2024 PT& (www.designptn.com); Paperlogy redesigned by Lee Juim, Hangul glyphs from Gmarket Sans, Latin from Montserrat (the font's name table, quoted in `OFLPAPLG.TXT`) | SIL OFL 1.1, no Reserved Font Name claimed | `svf/dos/OFLPAPLG.TXT` | rasterised at 16 px by `mkfont.py` (the exact command in `svf/dos/PAPLG.TXT`): a Modified Version under the OFL |
| `svf/dos/PAPLG18.SVF` (2 bpp jamo set, 18 x 18, 24/16/16 piece sets) | the same font, version 1.000 | the same | the same | the same | Paperlogy's syllable outlines separated into initial/medial/final vector pieces, rasterised at 18 px and merged to 24/16/16 sets by `fontbuild2.py` (research run `seg-night/F`; `svf/dos/PAPLG.TXT` records the run, hashes and IoU): a Modified Version under the OFL |
| `svf/dos/NEODG16G.SVF` (16 px 1 bpp jamo set, 6x2x1 layout) | `ttf/neodgm/neodgm.ttf`, Neo Dunggeunmo version 1.601 | Copyright (c) 2017-2021, Eunbin Jeong (Dalgona.) | SIL OFL 1.1; Reserved Font Names "Neo둥근모", "Neo둥근모 Code", "NeoDunggeunmo", "NeoDunggeunmo Code" (not used by the face) | `svf/dos/OFL.TXT` (`svf/dos/NEODGM.TXT`) | rasterised at 16 px 1 bpp by `mkfont.py` (ASCII and the 2,350 KS X 1001 syllables), then split into 6x2x1 pieces by `jamoset.py --layout 621 --from-svf --check` (`tools/build/faces.tsv`, `docs/recipes.md`): a Modified Version under the OFL |

The ports and the bench embed these faces re-laid out by `c/bench/mkface.py --profile mcu-strict` (record and table
unit 4 bytes, offsets 16 bit where they fit; the pixels are the same). Sizes of the embedded arrays, whole file and
glyph data (`svfdump info` `data_size`): `NEODG16G` 10,124 and 5,512 bytes (10,684 in the `default` file), `PAPLG16` 7,460 and 5,324 (spec 5,324), `PAPLG18` 67,200 and 40,024
(spec 39,800, +0.6 %); the PAPLG faces are within 1 % of the spec's estimates. The Pico and ESP32 colour and grey images embed `PAPLG16` +
`PAPLG18` (74,660 bytes), the mono images and the Arduino sketch `NEODG16G`.

> Copyright (c) 2024 PT& (www.designptn.com), Paperlogy; redesigned by Lee Juim, Hangul glyphs from
> Gmarket Sans, Latin from Montserrat (as stated in the font file's name table: copyright, designer and
> licence entries of Paperlogy-4Regular.ttf, version 1.000).
