**English** | [한국어](NOTICE.ko.md)

# Notice: licences of this repository

The code, the format specification and the documentation written for this repository (`c/`, `tools/`, `maker/`, `web/`,
`spec/`, `docs/`, the notes beside the faces) are under the MIT licence in [LICENSE](LICENSE), copyright Taehyun Kim.

The sample images in `docs/images/recipes/` are excluded from that licence. They are small illustration samples, made
with the owner's approval, of faces the recipes built from third-party fonts: Microsoft's Korean Windows fonts (glyph
design HanYang I&C), IBM Korea's HBIOS fonts, the font ROMs of Korean MSX computers and the like. Those fonts belong to
their owners and are not licensed here; the images show a few lines of text only, and neither the fonts nor the faces
made from them are in this repository.

The fonts and the faces made from them are **not** covered by that licence. Every font and face in this repository is
under the **SIL Open Font License 1.1**, and its licence text sits beside it. A face in `svf/` is a Modified Version of
its source font (rasterised, subset, or split into jamo pieces). `web/LICENCES.tsv` maps every face to its licence files
(`tools/test_web_picker.py` fails if a face has none), and `tools/build/faces.tsv` with [docs/recipes/svf-faces.md](docs/recipes/svf-faces.md)
says how each face is made from its upstream font.

## Faces (`svf/`)

| Faces | Source font | Copyright | Licence file |
|---|---|---|---|
| `svf/dos/BHSAN28` | Black Han Sans | 2015 The Black Han Sans Project Authors | `svf/dos/OFLBHS.TXT` |
| `svf/dos/COUSB24` | Coustard | 2011 The Coustard Project Authors | `svf/dos/OFLCOUS.TXT` |
| `svf/dos/DIPHY36` | Diphylleia | 2022 The Diphylleia Project Authors | `svf/dos/OFLDIPHY.TXT`, `DIPHY.TXT` |
| `svf/dos/GBATB*`, `GBA*X?` | Gowun Batang Bold | 2021 The Gowun Batang Project Authors | `svf/dos/OFLGOWUN.TXT`, `GOWUNBAT.TXT` |
| `svf/dos/GOTHB18A`, `svf/jamo-extra/GOTHA*`, `GOTHB*` | Gothic A1 | HanYang I&C Co., Ltd. | `OFLGOTHA.TXT` (both folders) |
| `svf/dos/MARU*` | MaruBuri | NAVER Corp., NAVER Cultural Foundation | `svf/dos/OFLMARU.TXT`, `PAPMARU.TXT` |
| `svf/iolo/SANS8J.SVF` | iolo 8x4x4-fonts SANS8J | Copyright (c) 2025 Dongsu Jang | `svf/iolo/IOLO.TXT`, `LICENSE-OFL.txt`, `LICENSE-MIT.txt` |
| `svf/dos/NEODG*`, `NEO*X?` | Neo Dunggeunmo 1.601 | 2017-2021 Eunbin Jeong (Dalgona.) | `svf/dos/OFL.TXT`, `NEODGM.TXT` |
| `svf/jamo-extra/NDGPR*` | Neo Dunggeunmo Pro 1.020 | Dalgona (original Dunggeunmo by Jungtae Kim, public domain) | `svf/jamo-extra/OFLNDGPR.TXT` |
| `svf/dos/NGOT*`, `NGO*X?` | NanumGothic Bold | 2010 NHN Corporation | `svf/dos/OFLNANUM.TXT`, `NANUMGOT.TXT` |
| `svf/dos/NSQR*`, `svf/jamo-extra/NSQR*` | NanumSquareRound | 2017 NAVER Corporation | `OFLNSQR.TXT` (both folders) |
| `svf/dos/PAPLG*`, `PAPER*`, `PAPLB*` | Paperlogy | 2024 PT& (designptn.com) | `svf/dos/OFLPAPLG.TXT`, `PAPLG.TXT`, `PAPMARU.TXT` |
| `svf/jamo-extra/SGDAY*` | Single Day | 2015 DXKorea Inc. | `svf/jamo-extra/OFLSGDAY.TXT` |

## TrueType sources (`ttf/`)

Unmodified upstream files (two variable fonts renamed, see `ttf/FONTS.md`), each with its licence text beside it.

| Folder | Font | Copyright | Licence |
|---|---|---|---|
| `ttf/blackhansans` | Black Han Sans | 2015 The Black Han Sans Project Authors | SIL OFL 1.1 |
| `ttf/caveat` | Caveat | 2014 The Caveat Project Authors | SIL OFL 1.1 |
| `ttf/coustard` | Coustard | 2011 The Coustard Project Authors | SIL OFL 1.1 |
| `ttf/ebgaramond` | EB Garamond | 2017 The EB Garamond Project Authors | SIL OFL 1.1 |
| `ttf/galmuri` | Galmuri | 2019-2025 Lee Minseo | SIL OFL 1.1 |
| `ttf/gowunbatang` | Gowun Batang | 2021 The Gowun Batang Project Authors | SIL OFL 1.1 |
| `ttf/nanumgothic`, `ttf/nanummyeongjo`, `ttf/nanumpenscript` | NanumGothic, NanumMyeongjo, Nanum Pen Script | 2010 NHN Corporation | SIL OFL 1.1 |
| `ttf/neodgm` | Neo Dunggeunmo | 2017-2021 Eunbin Jeong (Dalgona.) | SIL OFL 1.1 |

## Reserved Font Names: how this repository reads the OFL

Two source fonts declare Reserved Font Names: NanumGothic / NanumMyeongjo / Nanum Pen Script ("Nanum", "Naver Nanum",
"NanumGothic", "NanumMyeongjo", ...) and Neo Dunggeunmo ("Neo둥근모", "Neo둥근모 Code", "NeoDunggeunmo",
"NeoDunggeunmo Code"). OFL condition 3 says that no Modified Version may use a Reserved Font Name; the OFL defines the
Font Name as the name(s) declared for the Font Software, i.e. the name a font presents as its own (its name table, the
name it is installed or selected under). Reading it so:

- The faces in `svf/` are Modified Versions. They carry no font name inside (the SVFN format has no name field), and
  their file names (`NGOTB16.SVF`, `NEODG16G.SVF`) are abbreviations, not the reserved names. The licence notes beside
  them say this.
- `web/FAMILIES.tsv` gives each face the family of its **source** font, and the WASM picker shows it as the row label
  together with the licence note, as attribution of where the face comes from (OFL condition 2 makes the copyright notice
  travel with the font; condition 4 allows the authors' names to acknowledge their contribution). It does not present the face as the original
  font. This reading keeps the labels as they are.

This is a point for the owner to confirm before publishing: if the labels should not show a reserved name at all, the
`family` column of `web/FAMILIES.tsv` for the `NGOT*`, `NGO*X?`, `NEODG*` and `NEO*X?` faces is the one place to change
(for example "Nanum-derived Gothic", "Dunggeunmo-derived pixel"); the picker tests read the table, not fixed names,
except a few that name "NanumGothic Bold" as the default row.

## Upstream licence records checked

Every TrueType file in `ttf/` declares the SIL OFL 1.1 in its name table (ID 13) except the NanumGothic and
NanumMyeongjo files, whose name table says only "NHN Corporation"; their `OFL.txt` comes from the distributor
(Google Fonts) and NAVER publishes the Nanum fonts under the SIL OFL 1.1. The NanumSquareRound faces rest on the same
NAVER publication (the font files carry only the copyright line; `OFLNSQR.TXT` says so). Neo Dunggeunmo Pro and
Paperlogy state the OFL in their font files. Six faces (`NGOTB17`, `NGO17X1`, `NGO17X2`, and the fallback glyphs of
`NGO15X2`, `NGO16BX2`, `NGO21AX2`) were drawn from NHN's hinted NanumGothicBold.ttf (Debian `fonts-nanum`, SIL OFL
1.1), which is not in this repository.

## Desktop package

The desktop package bundles Electron/Chromium, CPython, Pillow, fontTools and the shared libraries they need; their
licences are listed in the package's THIRD-PARTY.txt (generated from the bundle by `desktop/build/third-party.mjs`,
which fails on any unattributed library and on any GPL one). It contains no font that is not in `svf/`.

## Model weights (`tools/models/`)

`tools/models/jamohybrid-v1.npz` holds the weights of the jamo split model of `tools/jamohybrid.py`. It is under the MIT
licence like the code. It is listed here separately because of what it was trained on:

- bitmaps of proprietary fonts: Apple HangulTalk 7.1.2 jamo planes with the System 7.5.3 strikes of the same families
  (Seoul, AppleMyungjo, AppleGothic), Apple HangulTalk 1.0 fonts (Gotic, Munjo), and the Windows 95 Gulim bitmap strikes;
- the open jamo-set faces of `svf/` (OFL-1.1; SANS8J also MIT).

No bitmap of the proprietary training fonts is included in this repository. [tools/models/jamohybrid-v1.md](tools/models/jamohybrid-v1.md) lists
every training source with its sha256, the training script, the seed and the evaluation. Licence questions about using
the weights are the user's responsibility, as with the fonts used in this project.

## Converters for proprietary formats

Some tools read font formats of commercial systems: `tools/macfbit3.py` and `tools/macfbit_svf.py` (classic Mac
HangulTalk 'fbit' fonts), `jamoset.py --layout mac-fbit-45sets` (HangulTalk 1.0), `tools/macsfnt.py` (TrueType in Mac
resource forks and .dfont files, Mac Korean cmaps), and the DOS / X11 raw layouts of
`jamoset.py` and `johab844.py`. They are original code and read **user-supplied** font files only. No such font, no
bitmap taken from one (apart from the sample images of `docs/images/recipes/` above) and no golden data derived from one
is distributed here; their tests use synthetic fixtures made
in the tests, and the checks against real files run only when an environment variable points at the user's own copies.

The maker (`maker/`) has a local mode for such fonts: the desktop app passes it the paths of files or folders the
user picked and an output folder; the fonts are read in place, converted, and the faces are written only into that
folder. In that mode nothing is uploaded, nothing is copied into the maker's data directory, no zip is made, and
the files the conversion needs on the way are kept inside the output folder and removed when the job ends. The
maker has no code that connects anywhere but to its own local page on 127.0.0.1 (the tests check its imports and its own sockets; docs/maker-audit.md section 8 says what they do not cover). No proprietary font or table is in this
repository, and no proprietary bitmap apart from those sample images; the local-mode tests build synthetic inputs in the test and the checks on real files run only where an
environment variable names the user's own copies. Having the right to convert a font is the user's own responsibility
(the maker checks no licence in local mode and asks for an acknowledgement); anyone who publishes a result should check
the font's licence.

## Left out of this repository

This repository is a curated copy of a private working repository. Left out on purpose: faces whose source licence is
not stated or is not the SIL OFL 1.1 (DOS, Mac, HWP and printer bitmap fonts, the iolo collections, the san 1.0 faces,
one game's own face) and the supplements of such faces; TrueType candidates (one bundles fonts under other licences, the
others have no licence record); the Arduino Uno presets derived from Apple data; the ScummVM `fonts-cjk.dat` builder and
file; the game-specific bake scripts, plans and map writers.
