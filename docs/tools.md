**English** | [한국어](tools.ko.md)

# Tools

Reference for command-line tools that read fonts, create or convert SVFN faces, and inspect them.
For the format and terminology, see the [SVF specification](../spec/SVF.md) and [glossary](../spec/SVF.md#glossary);
for composition, see [jamo sets](jamo-sets.md); for coverage and bit depth, see [anti-aliasing](anti-aliasing.md).

For examples by input type, see [recipes](recipes.md). To use the resulting faces, see the
[C renderer guide](c-renderer-guide.md), [renderer design](../spec/renderer-design.md), and
[web renderer guide](web-renderer-guide.md). For conversion through a GUI, see the
[desktop app](desktop-app.md) and [Maker desktop](maker-desktop.md).
The [README](../README.md) lists the documentation.

Some tools also serve as libraries imported by other tools. The fitting modules
`jamofit.py`, `jamoaa.py`, `jamoadapt.py`, and `jamoseg.py` have no command line of their own.

## 1. The SVFN kinds the tools produce

An **SVFN** file (magic `SVFN`, little-endian) is a bitmap font with a header, a code point table, optional
per-glyph metrics, and glyph records. SVFN writers use **version 3** through `jamoset.pack_svfn` ([specification](../spec/SVF.md)); version 2 (fixed cells) is converted by `svf2to3.py` (`jamoset.parse_svfn` refuses a v2 face with the convert message), and version 1 (code page order) is gone. Writers with selectable layouts take `--profile NAME` and `--box x|y|full`.
See each tool's options and the `svf2to3.py` table for profile names, `REC,ROW,TAB,OFF`, and defaults.
`macfbit_svf.py`, `jamofill.py`, and `jamomerge.py` do not expose these options. Header bytes 17 and 18 hold the font-wide **dy** range and metrics byte 3 holds each glyph's dy (a
glyph is drawn dy rows below its cell position); only a font with a metrics table can carry one.

The tools write two kinds:

- A **precomposed face** holds one stored glyph per code point (a Hangul syllable, an ASCII letter, a symbol). It is
  written at **1, 2 or 8 bpp** (1 bpp is a stencil, 2 bpp holds four coverage levels, 8 bpp holds 256). There is no
  4 bpp. A face may have
  a metrics table (header flag bit 0) with per-glyph advance, left bearing and ink width, making it variable width.
  Faces written by `mkfont.py` from a code point list also set flag bit 2 (combining marks stored with the pen at
  `max(0, -bearingX)`).
- A **jamo set** (header flag bit 1) stores positional jamo **pieces** as glyphs at
  `U+F0000 + piece number` and composes syllables through a **JSET** block immediately after the code point table.
  Version 1 and 2 blocks use class and set tables; version 3 (JMAP) uses syllable mappings. Pieces combine by
  per-pixel maximum (equivalent to bitwise OR at 1 bpp). A JMAP may provide only some syllables.
  For example, the 16 px, 1 bpp `svf/dos/NEODG16G.SVF` composes all 11,172 syllables in 10,684 bytes (references 1–2).
  Piece builders support 1 or 2 bpp. ASCII, symbols, and individual precomposed glyphs may also be stored.
  Compatibility jamo U+3131..U+3163 use a piece when the block names one.
  An SVFN v3 reader without JSET support can use only the stored ordinary glyphs.

Both kinds may carry a **dy** range; a jamo set composes its syllables at dy 0 (a piece may not carry a dy).

A **layout** is a jamo set's set system: the lead and tail classes, the initial/medial/final set tables, and the piece
tables. The named layouts are `844` (the DOS 8x4x4 standard), `844-ihnm`, `844-hbios24`, `844-hwp3`, `hwp1`, `1044-san`, `621`, `hanterm-johab`,
`hanterm-844`, `dkb-printer-7x2x2`, `dkb-printer-12x4x4`, `kyra-lok`, `mac-fbit-45sets`, `spec` and `adaptive[:NI,NM,NF]`.

The one-paragraph map: `mkfont.py` bakes **precomposed faces** from an outline font and `bdfface.py`/`johab844.py`
from a bitmap one;
`jamoset.py`, `jamovec.py` and `svf_synth.py` write **jamo sets** and synthetic faces; `svfdy.py` edits an existing
face's **dy**; and `tools/build/build_faces.py` and the `web/` tools rebuild and serve faces. The details, one tool at a time:

- `mkfont.py` writes **precomposed faces** from a TTF/OTF (1/2/8 bpp, SVFN v3, a code point list is required).
- `bdfface.py` writes a **precomposed 1 bpp face** from a Hangul BDF plus an ASCII BDF/HBF; `johab844.py` redraws the
  Hangul of a **precomposed 16x16 1 bpp face** from a raw 8x4x4 Johab font.
- `jamoset.py` writes **jamo sets** (1 or 2 bpp) from a DOS Johab raw font, a hanterm BDF, a Dokkaebi printer FNT, a
  Kyra `.BIT`, a Mac HangulTalk `fbit` resource fork, or by fitting an outline font (`--from-ttf`) or a precomposed
  1 bpp face (`--from-svf`); `jamovec.py` writes **jamo sets** by separating a font's jamo once and rendering any size.
- `svfdy.py` edits the **dy** of an existing face; `svf_synth.py` writes synthetic faces for the C tests.
- `tools/build/build_faces.py` rebuilds the faces of `svf/` from their upstream fonts (`tools/build/faces.tsv`, [recipes/svf-faces.md](recipes/svf-faces.md)).
- The `web/` tools index and copy the faces that the WASM picker serves.

## 2. Core builders

### `tools/jamoset.py`

**Purpose.** Build a jamo-set SVF (flag bit 1 plus a JSET block) from a DOS-era source font, or fit the pieces to an
outline font or an existing precomposed face. It also writes SVFN v3 (`write_svfn`, `pack_svfn`, `--profile`, `--box`) and reads v3 (a v2 face is refused with the convert message, `tools/svf2to3.py`), packs and unpacks JSET blocks, and
composes syllables for checking.

**Status.** General-purpose. It names game-specific set systems (SAGA IHNM, hanterm, Dokkaebi printer, Kyra LoK, Mac
HangulTalk, HWP 1.x) but is not tied to one game.

**Inputs.** Depends on the mode:
- a DOS Johab raw font read by its own parser: raw 8x4x4 (`844`, 16/24/40/48 px, 11520/11522/25920/72000/103680/15584
  bytes), 10x4x4 (`1044-san`, 12800 bytes), 6x2x1 (`621`, 6144 bytes, byte-column order), HBIOS/Taebaek 24x30
  (`844-hbios24`, 243900 bytes), SAGA IHNM (`844-ihnm`), Kyra `MK15.BIT` (11550 bytes), Dokkaebi printer
  `HANGUL16/24.FNT` (15360/34560, column-major) and `HANGUL40/48.FNT` (176000/253440);
- a hanterm BDF (`hanterm-johab`) whose `ENCODING` is the johab-1 glyph number, parsed with a regular-expression
  reader; a hanterm johab844-1 BDF (`hanterm-844`: 360 glyphs, `ENCODING` = the glyph number of the DOS 8x4x4
  order, read by the same reader and composed by the `844` tables);
- a Mac HangulTalk 1.0 `fbit` resource fork (`mac-fbit-45sets`), parsed from its raw resource map;
- an HWP 1.x `HANGUL.SFT` / `HANGUL1/2/3.PFT` (`hwp1`, `--face 0..2`): the JSET tables are HWP.EXE's own rule for the
  face, read through `hwpfont.py`; an HWP 3.0 `HAN16_*.FNT` (`844-hwp3`: the 360-glyph 8x4x4 set after its 2,350
  syllables);
- any font a `rawcarve.py` compose spec describes (`spec`, with `--spec SPEC.json` or the built-in `spc1500`): the
  positional file is the bytes the spec's offsets point into, and the JSET is the spec's own rule, exact;
- `--eng` a raw 8x16 DOS English font (2048 or 4096 bytes), a 16x16 one (8192 bytes: 256 glyphs of 16 rows of 2 bytes, as
  `rawcarve.py eng --width 16` writes; it steps by the right edge of the ink of 0-9, A-Z and a-z plus their smallest left
  margin (16 when none has ink), or by `--eng-advance`), or an HBIOS 12x24 (15360) / PFT 12x24 (12288) / Taebaek PFT 20x40 (30720, GASCII40) / 24x48 (49152, GASCII48), or an HWP English font: an HWP 1.x `ASCII.SFT` (8x16) / `ASCII.PFT` (14x24, step 14; face `--eng-face` of six) or an HWP 3.0 `ENG*.FNT` (8x16, 12x24, 20x40), recognised by its header;
- `--base` an SVFN v3 face (its non-syllable glyphs are kept; a v2 face is refused with the convert message (`tools/svf2to3.py`));
- `--from-ttf` an outline TTF/OTF, read with freetype-py for 1 bpp `mono` targets and with fontTools (via `jamoaa.py`)
  for 2 bpp and for `--binarize threshold|ridge`;
- `--from-svf` a precomposed 1 bpp SVFN v3 face (a v2 face is refused with the convert message (`tools/svf2to3.py`)).

**Outputs.** An SVFN v3 jamo-set face (flag bit 1, and bit 0 when it has metrics), 1 bpp by default or 2 bpp with
`--bpp 2`. The pieces are at `U+F0000 + n`; `--from-ttf`/`--from-svf` also carry ASCII glyphs. `--blank-compat`
rewrites an existing jamo set instead.

**Synopsis.**

    python3 tools/jamoset.py SOURCE --layout LAYOUT -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --from-ttf FONT --size N -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --from-svf FACE.SVF -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --blank-compat FACE.SVF -o OUT.SVF

Options (default in parentheses). The **Modes** column says which mode the option belongs to: `source` (a positional
DOS Johab, hanterm BDF, Kyra `.BIT`, Dokkaebi FNT or HWP 3.0 HAN16 FNT file), `mac-fbit-45sets` (a positional Mac
HangulTalk `fbit` resource fork, a mode of its own: it takes no `--from-*`, `--eng` or `--base`), `hwp1` (a positional HWP
1.x Hangul file, a mode of its own: no `--from-*`; it takes `--eng` and `--base` as `source` does), `--from-ttf`,
`--from-svf`, `--bpp 2` (only with `--from-ttf`) and `--blank-compat`. Options not listed for a mode may have no effect on its output. Inputs such as `--eng` and `--base` are still read before use and can fail on invalid files. Explicit refusals are noted in the table.

| Option (default) | Modes | Meaning |
|---|---|---|
| `--layout` (required) | all | a set system: `1044-san`, `621`, `844`, `844-hbios24`, `844-hwp3`, `844-ihnm`, `dkb-printer-12x4x4`, `dkb-printer-7x2x2`, `hanterm-844`, `hanterm-johab`, `hwp1`, `kyra-lok`, `mac-fbit-45sets`, `spec`, `adaptive[:NI,NM,NF]`. `adaptive` needs `--from-ttf` or `--from-svf`; `mac-fbit-45sets` and `hwp1` are modes of their own (the positional file is the `fbit` resource fork, the HWP 1.x Hangul file) |
| `--face N` (0) | `source`, `hwp1` | typeface of a Dokkaebi printer font (0 or 1), of an HWP 1.x Hangul file (0, 1, 2) |
| `--eng FILE` (none) | `source`, `hwp1`, `--from-ttf`, `--from-svf` | raw 8x16 English font for ASCII (2048 or 4096 bytes; the 12x24, 20x40 and 24x48 faces and the HWP English fonts above also read); refused with `--bpp 2` and with `mac-fbit-45sets` |
| `--spec SPEC.json\|spc1500` (none) | `spec` | the `rawcarve.py` compose spec of the positional file (a JSON file, or the built-in `spc1500`: that name always means the built-in, a file of that name is given as `./spc1500`); a JSET initial set per initial piece set the spec names (its `novowel` set first), a medial set per medial table (`nofinal`, `final`, and the `*_kk` tables, which make two lead classes), a final set per final piece set, two tail classes; refused with another layout |
| `--eng-advance N` (none) | where `--eng` is | the step of the `--eng` glyphs of a 16x16, 12x24, 20x40 or 24x48 English font (1..255; refused for an 8x16 one, which steps by 8) |
| `--eng-face N` (0) | where `--eng` is | the face of an HWP 1.x `ASCII.SFT` / `ASCII.PFT` given as `--eng` (0..5: Myeongjo, Gothic, superscript, subscript, italic, script by HWP's menu) |
| `--base FILE` (none) | `source`, `hwp1`, `--from-ttf` | SVFN v3 whose non-syllable glyphs are kept (same cell, 1 bpp); ignored by `--from-svf` (the input face is the base); refused with `--bpp 2` and with `mac-fbit-45sets` |
| `-o`, `--output` (required) | all | output path |
| `--profile NAME` (`default`), `--box x\|y\|full` (the profile's) | all | the SVFN v3 layout profile and ink box policy of the output (see `svf2to3.py`) |
| `--jset-version 1\|2\|auto` (1; `--blank-compat`: the input's) | all | the JSET block version written (see "JSET versions" below) |
| `--jset-big` (off) | all | allow a JSET over the standard limits (12 x 12 classes, 32/24/16 sets), up to the BIG limits (19 x 28 classes, 128/128/64 sets; the reader needs `SVF_JSET_BIG`); output within the standard limits is identical with or without it (see "JSET versions") |
| `--advance N` (none) | `source`, `mac-fbit-45sets`, `hwp1`, `--from-ttf`, `--from-svf`, `--bpp 2` | the composed syllable's step (JSET advance byte; the layout's value, 0 = cell width) |
| `--ascent N` (none) | `source`, `mac-fbit-45sets`, `hwp1` | the SVF's baseline row (the `--eng` face's baseline for a 12x24, 14x24, 20x40 or 24x48 face, else 7/8 of the cell); ignored by the fit modes, which take it from the fitted face |
| `--embolden` (off) | `source`, `mac-fbit-45sets`, `hwp1` | OR every piece and ASCII glyph with itself shifted right 1 px; ignored by the fit modes, refused with `--bpp 2` |
| `--symbols` (off) | `source`, `mac-fbit-45sets`, `hwp1`, `--bpp 2` | add U+2026 and U+25A1; ignored by 1 bpp `--from-ttf`/`--from-svf` |
| `--check` (off) | `source`, `mac-fbit-45sets`, `hwp1`, `--from-ttf`, `--from-svf`, `--bpp 2` | compose all 11,172 syllables from the output and verify (`844` and `844-hwp3` at 16 px: also against `johab844.py`; `hwp1`: also against `hwpfont.py`'s HWP rule, printing `hwp1: 11172 syllables identical to the HWP 1.x rule (hwpfont.py)`; `spec`: also every syllable against `rawcarve.py compose`, printing `all 11172 syllables identical to rawcarve.py compose`) |
| `--from-ttf FONT` (none) | mode | fit the pieces to the outline font's syllables at `--size` |
| `--from-svf FACE.SVF` (none) | mode | decompose a 1 bpp precomposed SVFN face (refused at any other bpp) |
| `--size N` (none) | `--from-ttf` | pixel size |
| `--cell WxH` (none) | `--from-ttf` | cell (default `SIZExSIZE`) |
| `--baseline N` (none) | `--from-ttf` | baseline row (default ink box centred) |
| `--present-only` / `--no-present-only` (on) | `--from-ttf` 1 bpp `mono` | fit only syllables the font draws, or also `.notdef`; `--binarize threshold\|ridge` fits the drawn syllables only and refuses `--no-present-only`; refused with `--bpp 2` |
| `--blank-compat FACE.SVF` (none) | mode | rewrite a jamo set leaving compat jamo that have a whole glyph to that glyph |
| `--mask-font FONT\|none` (alias `--mask`) | `--from-ttf`, `--from-svf` 1 bpp | mask font with OpenType `ljmo`/`vjmo`/`tjmo`; default `$JAMOSET_MASK_FONT` or the shipped NotoSansKR when freetype/uharfbuzz import, else free pieces |
| `--mask-radius N` (auto) | `--from-ttf`, `--from-svf` 1 bpp | mask dilation (1 up to 16 px, 2 up to 24, else 3) |
| `--passes N` (12) | `--from-ttf`, `--from-svf`, `--bpp 2` | most coordinate-descent passes |
| `--pylib DIR` (none) | `--from-ttf`, `--from-svf`, `--bpp 2` | directory holding freetype and uharfbuzz (also `$JAMOSET_PYLIB`) |
| `--report FILE.json` (none) | `mac-fbit-45sets`, `--from-ttf`, `--from-svf`, `--bpp 2` | write the quality report |
| `--bpp {1,2}` (1) | `--from-ttf` | 2 = anti-aliased pieces (needs fontTools) |
| `--aa-refine N` (2) | `--from-ttf --bpp 2` | level-error refinement passes (0 = median only) |
| `--binarize {mono,threshold,ridge}` (mono) | `--from-ttf` 1 bpp | FreeType monochrome, exact-area coverage, or that plus faint ridges (fontTools) |
| `--threshold F` (0.5) | `--from-ttf --binarize threshold\|ridge` | coverage cut |
| `--clean` / `--no-clean` (auto) | `--from-ttf`, `--from-svf`, `--bpp 2` | noise cleanup (on for `--bpp 2` and `--layout adaptive`, else off) |

**JSET versions.** Version 1 is the default of the general builders (`svf_synth.py` defaults to 2 for testing); version 2 (compact) is for builds and
packs aimed at memory-constrained targets ([SVF specification](../spec/SVF.md), "When to use version 2"). `--jset-version` takes `1`, `2` or
`auto`: `auto` writes version 2 when the face's version 1 block is at least `JSET_V2_MIN_SAVING` (1,024) bytes larger
than its version 2 block, else version 1. The same flag is on `jamovec.py render` and `svf2to3.py`; `jamoaa.py` (a
library) takes it as the `jset_version` argument of its builder, which `jamoset.py --bpp 2` passes on; `jamovec.py` calls `pack_jset` itself.
As a library `jamoset.py` has: `pack(tables, big=False)` (the version 2 block, returned as `Packed(block, piece_map)`; the map
renumbers the pieces: first sight fresh, a later sight an alias), `pack_v1(tables, big=False)` (the version 1 block), `pack_jset(tables,
version, big=False)` (1, 2 or `"auto"`; the same `Packed`, with an identity map for version 1), `choose_jset_version(tables, big=False)` (what `auto` picks),
`renumber_glyphs(glyphs, piece_map)` (applies the map to the plane-15 code points of a glyph dict or list, so a
block and its glyphs cannot disagree), `jset_size(...)` (the version 2 size), `jset_line(face_bytes)` (version and both sizes) and
`unpack(block)`, which reads **both** versions (and the BIG counts, always) and returns the same `Tables` (resolved per-slot piece lists, `BLANK`
for an empty slot; compat as 51 piece numbers) for either. The SVF maker passes `--jset-version 1|2` as an extra flag
on the route it runs; without it an uploaded jamo-set face keeps its block's version.

**BIG (`--jset-big`).** The JSET limits are `jamoset.JSET_LIMITS`: standard 12 x 12 classes, 32 / 24 / 16 sets; BIG 19 x 28 classes,
128 / 128 / 64 sets (largest blocks: version 1 47,373 bytes; version 2 29,708 with NA = 0, 45,068 with every slot an alias).
`unpack` reads both rows always; a writer (`pack`, `pack_v1`, `pack_jset`, `pack_fallback`, and every CLI with `--jset-version`: `jamoset.py`,
`jamovec.py render`, `svf2to3.py`; `jamoaa.py` as `jset_big`) refuses a table over the standard row with
`JSET {name} {v} is not 1..{hi} (--jset-big allows 19 x 28 classes, 128/128/64 sets)` unless `--jset-big` / `big=True`; `svf2to3.py` applies the rule to a verbatim copy of a v2 block (or of a JMAP region's fallback) as well as to a re-encode. `--jset-big` on `jamoset.py --layout adaptive` and on `jamovec.py` only permits a BIG table to be written; the adaptive search limits are not widened by it (they follow `--adaptive` / `--class-limit`). `jamomerge.py` and `jamofill.py` have no such option and refuse a BIG table. `jamofill.py` (the skeleton read), `jamomerge.py` (`read_face`) and `jamovec.py` (`tables_json`) refuse a JMAP or LIST face (JSET version 3) with a ValueError: it has no set tables. Output within the
standard limits is byte-identical with or without the flag. `needs_big(tables)` tells whether a table needs it, `class_limits(big)` gives
the (lead, tail) class limit, and `jset_line` appends ` big=1` for such a face. `jamoadapt.FORMAT_LIMITS` / `CLASS_LIMITS` carry both rows and
`adapt(..., class_limit=)` takes an int or a (lead, tail) pair.

**JMAP (JSET version 3).** As a library `jamoset.py` also reads and writes the mapping-table block of [SVF specification](../spec/SVF.md)
("Version 3: mapping table (JMAP)"): `Jmap` (advance, plane counts `pi`/`pm`/`pf`, `entries` syllable index -> plane
indices, `block_compat`, the effective `compat`, `fallback` Tables, `pieces(cp)`), `jmap_size(ns, four, sparse,
fallback_len)`, `pack_jmap(jmap, fallback_block)` (4B when a count is over 255, SPARSE when fewer than 11,172 entries; refuses
anything over a limit or past 65,534 bytes), `unpack_jmap(block)` (rules R1-R7 in the spec's order; ValueError text
`JMAP Rn ...`) and `jmap_from_tables(tables, syllables, glyphs, pad)` (per-plane contiguous pieces from a JSET face, and the
new piece glyphs, keyed by U+F0000 + number; the input glyphs may be keyed by piece number or by code point: a face's whole glyph dict works, its low keys ignored), and
`shift_pieces(tables, delta)` (a copy with every piece number raised: a JMAP fallback must name pieces at or above PI+PM+PF,
and `pack_jmap` refuses an overlap). `pack_fallback(tables, version, base=0, big=False)` writes a version 1 or 2 block that keeps the given piece numbers (plus `base`) for
use as a JMAP fallback; version 2 walks each row greedily from its first piece, storing the slots that count up one by one as fresh pieces and every other drawn slot as an alias (not a longest-run search), so it is larger than `pack`'s. `renumber`, `pack_v1`, `pack`, `pack_jset` and `choose_jset_version` refuse a `Jmap`
("a JMAP block has no set tables"); `blank_compat` and `blank_whole_compat` blank a JMAP's own compat entries and its fallback's (`blank_compat` re-encodes `fallback_block` with `pack_fallback`, same version and numbering, when that changed the fallback (a BIG fallback is re-encoded with its own size whether or not `--jset-big` is given, so `jamoset.py --blank-compat` preserves it); `blank_whole_compat` keeps every piece of a JMAP and drops unused pieces of set tables only). LIST mode (flag 0x08): `Jmap(..., list_mode=True)` keeps `entries` as syllable index -> three piece numbers of one shared pool (BLANK = none; `pi`/`pm`/`pf` are 0); constants `JMAP_FLAG_LIST`, `JMAP_LIST_MAX` (255), `JMAP_LIST_ENTRIES` (118), `JMAP_LIST_ENTRY` (8); `jmap_size(ns, four, sparse, fallback_len, list_mode)`; `pack_jmap` writes a LIST for a list-mode `Jmap` (no overlap refusal, over 255 entries refused with a SPARSE hint), `unpack_jmap` reads it (rules R1', L2, L3, R4, L6; L5/L7 are `parse_svfn`'s usable rule) and `jset_line` prints `list=1`. `unpack` returns a `Jmap` for a version 3 block, `pieces_of`, `used_pieces`, `compose` and
`jset_line` (`jset=v3 jmap=BYTES ns=NS fallback=v1|v2|none`, then ` big=1` when the fallback needs BIG) accept one. `jmap_list(f, exceptions, compat=None, jset_version=None, fallback=True, advance=0)` builds a LIST over a parsed jamo face `f`: `exceptions` maps a syllable index (0..11171) to 1-3 piece numbers (padded with BLANK) or a whole cell (bytes, packed rows), `compat` maps a compat index (0..50) to one piece number or a whole cell (every other k stays BLANK and falls to the fallback). A whole cell becomes a new piece numbered above the highest U+F0000 + n code point of the face (syllables in ascending s, then compat in ascending k); a number that would reach 0xFFFF is refused. With `fallback` the face's JSET (version 1 or 2) is kept verbatim as the fallback (or re-encoded by `pack_fallback`, numbers kept, when `jset_version` differs) and the LIST advance is its advance byte, `advance` being ignored; `fallback=False` builds a LIST without one, with `advance`. A field may be BLANK (0xFFFF; a compat given as the number BLANK means not given); a piece number without a glyph in the face is refused. It refuses over 255 entries, a version 3 source (also with `fallback=False`), `jset_version` with `fallback=False`, a face without a usable JSET (unless `fallback=False`), an s or k out of range, a value that is neither a cell nor a list of 1-3 pieces, and a cell of the wrong size. It returns `(Jmap, {cp: cell})`; the caller writes `pack_jmap(jm, jm.fallback_block)`. `jamoset.py` has no option that writes JMAP; `jamoexc.py build` writes a LIST.

**Repository modules imported.** `johab844.py` (for the 844 identity check), `hwpfont.py` (`hwp1`, `844-hwp3` and the
HWP English fonts), `rawcarve.py` (`spec`), `jamoaa.py`, `jamofit.py`, `jamoadapt.py`. **Third-party.** fontTools (for `--bpp 2`, `--binarize threshold|ridge`, and the `--clean` contour
donors), freetype-py and uharfbuzz (for the mask font and for `--from-ttf` at 1 bpp `mono`). These dependencies are optional:
without them, `mono` outline fitting fails. An automatic mask is skipped with a message; an explicitly requested mask fails.

**Test.** `tools/test_jamoset.py`; `tools/test_hwpfont.py` (`hwp1`, `844-hwp3`, the HWP `--eng`); `tools/test_tiles.py`
(`spec`: the built-in `spc1500` spec against an independent reading of MAME's drawing code, an 8x4x4 spec with two lead
classes against `johab844.py`, a spec with its own vowel order and a half-cell set; the 16x16 `--eng`, `--eng-advance`).

### `tools/mkfont.py`

**Purpose.** Bake a TTF or OTF into a precomposed SVFN v3 face with Pillow's FreeType rasteriser (references 3–4), from an explicit
code point list (`--unicode` or `--chars-from`; without one it exits 2 with `mkfont: version 1 (code page order) is gone:
pass --unicode SET`). A bitmap BDF or PCF also opens
through FreeType, but only at the pixel size built into the file.

**Status.** General-purpose.

**Inputs.** A TTF, OTF, BDF or PCF read with Pillow's FreeType (`PIL.ImageFont.truetype`). A bitmap BDF or PCF opens
only at the pixel size built into the file (its strike); any other size is `OSError: invalid pixel size`. `fontTools` checks the cmap (`cmap_has`), supports `--fallback-ttf`, decides which requested code points to keep,
and reads strike advances for bitmap-only TrueType fonts (`strike_advance`); `cmap_has` returns None (unknown) for a file that is not an sfnt (BDF, PCF, FNT), so those
are not rejected by the cmap check; actual loading still depends on FreeType. `--chars-from` reads files written by the games (see below).

**Outputs.** A precomposed SVFN v3 face, 1, 2 or 8 bpp, variable width (a metrics table), flag bit 2 set, in the
`--profile` layout. The v1 options `--codepage`, `--count`, `--shadow`, `--center`, `--fixed`, `--fullwidth` and
`--variable` are gone (argparse refuses them).

**Synopsis.** `python3 tools/mkfont.py INPUT OUTPUT --size N [options]`

| Option | Default | Meaning |
|---|---|---|
| `--size N` (required) | - | pixel size to render at |
| `--cell N` | 0 (= `--size`) | cell height |
| `--width N` | 0 (= cell height) | cell width |
| `--bpp {1,2,8}` | 8 | 1 stencil, 2 four levels, 8 coverage |
| `--mono-hint` | off | 1 bpp: FreeType monochrome renderer and the font's hinting |
| `--latin` | off | pick the Latin baseline rule (ascent), also under `--fit-cell`/`--clip-cell` |
| `--ink-advance` | off | take variable width from the ink, not the font metric |
| `--space-advance N` | none | variable width: fix U+0020/U+00A0 advance |
| `--punct-extra N` | 0 | variable width: add N px to `. , : ; ! ? ' …` |
| `--ascent N` | 0 (= chosen) | baseline row from the cell top |
| `--fit-cell` | off | shrink the size until all ink fits the cell |
| `--clip-cell` | off | keep one baseline, clip ink outside the cell |
| `--report FILE.json` | none | write a JSON report beside the face: per-glyph ink boxes, the rows a cell cuts (`--clip-cell`) or nudges, the counts and the chosen size/ascent (any mode); a glyph the cell cuts whole is marked `gone` (the build drops it) |
| `--probe` | off | bake in a tall cell that cuts nothing (cell height and ascent come from the ink boxes) and write the `--report`; past 255 rows only the report is written; refuses `--cell`, `--ascent`, `--clip-cell`, `--fit-cell` (exit 2) |
| `--probe-cell H` | none | with `--probe`: the caller's cell height (1..255), so the report's `auto_ascent` is the baseline `--clip-cell` would choose for that cell |
| `--unicode SPEC` | "" | the code point list (this or `--chars-from` is required): hex ranges, a named set (`ascii`, `latin1`, `hangul`, `jamo`, `cjk-punct`, `kana`, `thai`, `ksx1001`, `ksx1001-nohanja`, `ksx1001-hangul`, `ksx1001-symbols`, `cp949`, `cp949-hangul`) or `file:PATH` |
| `--chars-from FILE...` | none | union of the code points those files use |
| `--limit SPEC` | "" | intersect the result with this code point set |
| `--only-listed` | off | do not always keep ASCII and U+25A1 |
| `--fallback-ttf FILE` | "" | draw code points the main font lacks from this TTF |
| `--fail-on-drop` | off | fail if `--limit` dropped a `--chars-from` character |
| `--require` | off | fail if a requested code point is missing from the font |
| `--profile NAME` | `default` | the SVFN v3 layout profile (name or `REC,ROW,TAB,OFF` units) |
| `--box x\|y\|full` | the profile's | ink box policy of the glyph records |

`--chars-from` recognizes these four formats by file name and reads other files as plain UTF-8: `TEXT.nnn`/`text.nnn` (SCI TEXT patch: a 2-byte header then NUL-separated
UTF-8 strings), `*.str`/`sci-ko.str` (`script<TAB>id[<TAB>room]<TAB>text`, UTF-8), `*.map` (a hires_text INI's `missing=`
and `[glyphs]` absolute codes), `*.trs` (a SCUMM `SCVMTRS` bundle: UTF-8 if the body starts with a BOM, else CP949),
and otherwise plain UTF-8 text.

**Repository modules imported.** `jamoset.py` (SVFN writing and profiles); `bdfface.py` and others import this module. **Third-party.** Pillow (required);
fontTools (optional).

**Test.** `tools/test_mkfont.py`.

### `tools/bdfface.py`

**Purpose.** Bake a precomposed 1 bpp SVF from a precomposed Hangul bitmap font (a BDF) and an ASCII bitmap font (a BDF
or an HBF). It was written for the MI1/MI2 "L" faces but is not game-specific.

**Status.** General-purpose.

**Inputs.** Its own regular-expression BDF reader (KS X 1001 `ENCODING` or Unicode) and HBF reader (single-byte code
ranges with the bitmap files beside them, optionally gzipped). A Hangul BDF and an ASCII BDF/HBF. It keeps only the
Hangul syllables `--chars-from` names (so it needs a text file listing them), ASCII 0x20-0x7E from `--ascii`, and its
own U+2026/U+25A1; it takes no symbols or jamo from either bitmap face unless `--symbols` is given, which also keeps
the other characters `--chars-from` names (KS X 1001 symbols, jamo, Hanja) where the Hangul BDF has them. The cell
defaults to 24x24 whatever the BDF's own box is. An `ENCODING` outside two bytes (the -1 of an unencoded glyph) is
skipped.

**Outputs.** A precomposed SVFN v3 face, 1 bpp, variable width, flags 5 (variable width + marks at origin). It writes
U+2026 (three dots) and U+25A1 (the missing-glyph box) itself. With `--fill-absent` it composes the requested syllables
the face lacks from jamo pieces fitted to the face (through `jamoset.fit_font`).

**Synopsis.**

    python3 tools/bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf|.hbf --chars-from FILE... -o OUT.SVF [options]

| Option | Default | Meaning |
|---|---|---|
| `--hangul FILE` (required) | - | Hangul BDF |
| `--ascii FILE` (required) | - | ASCII BDF or HBF |
| `--cell WxH` | `24x24` | cell |
| `--ascent N` | ASCII face's FONT_ASCENT | cell row of the ASCII baseline |
| `--hangul-ascent N` | Hangul face's FONT_ASCENT | cell row of the Hangul baseline |
| `--chars-from FILE...` (required) | - | files naming the characters (`mkfont.py` rules) |
| `--hangul-advance N` | the BDF's DWIDTH | syllable advance |
| `--fill-absent` | off | compose the requested syllables the face lacks |
| `--symbols` | off | also take the other characters `--chars-from` names (symbols, jamo, Hanja) from the Hangul BDF, on its baseline with its DWIDTH; its own U+2026 / U+25A1 then replace the drawn ones |
| `--mask-font FILE` | `$JAMOSET_MASK_FONT` / shipped NotoSansKR | `--fill-absent` mask font (`none` = free pieces) |
| `--pylib DIR` | `$JAMOSET_PYLIB` | directory holding freetype and uharfbuzz |
| `--profile NAME`, `--box x\|y\|full` | `default`, the profile's | the SVFN v3 layout profile and ink box policy |
| `-o`, `--output` (required) | - | output path |

**Repository modules imported.** `jamoset.py` (and `mkfont.py`, for `collect_chars_from_files`). **Third-party.** None
(the BDF/HBF readers are its own; `--fill-absent` with a mask font uses freetype/uharfbuzz through `jamoset.py`).

**Test.** `tools/test_bdfface.py`.

### `tools/johab844.py`

**Purpose.** Put the Hangul of a raw 8x4x4 Johab bitmap font into an existing 16x16 1 bpp SVFN base, redrawing each stored
syllable as the OR of its pieces and keeping the base's other glyphs.

**Status.** General-purpose.

**Inputs.** A raw 8x4x4 Johab font (11520 bytes, 360 pieces; read by its own reader) and an SVFN v3 16x16 1 bpp base (`jamoset.parse_svfn`; a v2 face is refused with the convert message (`tools/svf2to3.py`)).
`--eng` reads a raw 8x16 DOS English font (2048 or 4096 bytes).

**Outputs.** The base as SVFN v3 (`jamoset.pack_svfn`) with its Hangul syllables redrawn (still a precomposed 1 bpp face); glyphs are stored in code point order.

**Synopsis.** `python3 tools/johab844.py JOHAB.KOR BASE.SVF OUTPUT [--eng ENG] [--profile NAME] [--box x|y|full]`

| Option | Default | Meaning |
|---|---|---|
| `--eng FILE` | none | raw 8x16 English font for ASCII 0x21-0x7E |
| `--profile NAME`, `--box x\|y\|full` | the base's layout, the profile's box | the SVFN v3 layout profile and ink box policy (without `--profile` the base's own layout is kept) |

**Repository modules imported.** `jamoset.py`. **Third-party.** None. **Test.** `tools/test_jamoset.py`.

### `tools/macfbit_svf.py`

**Purpose.** Convert a Mac HangulTalk 7.1.x type-3 'fbit' jamo-plane font (Seoul12, AppleGothic12/24, AppleMyungjo12/24)
into an SVF v3 jamo-set face, with every KS X 1001 syllable exactly as the Mac draws it.

**Status.** Special-purpose (HangulTalk type-3 fbit). Reads resources supplied by the user.

**Inputs.** The 'fbit' resource (482 glyph slots, 2 banks x 241) and InputBackSupport 'HTBL' 1 (4 bytes per KS code:
bank and three glyph bytes; the format is described in `tools/macfbit3.py` and [recipes/classic-mac.md](recipes/classic-mac.md#classic-mac-korean-bitmap-fonts)). `--latin` reads
the family suitcase's resource fork ('FOND' + 'NFNT') for ASCII 0x20-0x7E at the cell's point size.

**Method.** The Mac picks its medial (and the ㄱ ㄹ ㅇ finals) by the initial more finely than 12 lead classes allow
when every Mac slot is one piece (`slot_conflicts`), so pieces are cell caps of the Mac planes: medial = AND of the
cell's Mac medials, final = AND of its Mac finals, initial = the rest of each syllable (the Mac initial plus the
lead-specific strokes the shared medial leaves out; reported as residual pixels). `search_classes` merges lead and tail
classes while no KS syllable stops being exact and no residual pixel is added (or a count is above 12);
`fit_limits` moves single jamo between classes when a table needs more than 32 / 24 / 16 sets. Sets: per domain
(lead class / vowel / tail class) the cells' partial rows merge where they agree (`cluster`). The 8,822 syllables
outside KS are extrapolated: "regular" when each of the syllable's cells holds KS syllables and the set fixes its jamo
from KS data, "guess" otherwise (a cell no KS syllable reaches takes the nearest observed cell's set; a jamo a set
lacks is filled with a plain Mac glyph of the nearest context). Extrapolated syllables are not Mac output.

**Direct mode (default, `--mode direct`).** The Mac structure itself, no extrapolation: a JMAP block (JSET version 3,
spec "Jamo-set fonts") whose pieces are the Mac slots (`direct_jmap`): per plane in slot order (initial, medial, final;
a slot referenced in two planes is refused), byte-identical bitmaps of one plane folded (never across planes) unless
`--no-dedup`, an entry per KS syllable (field = piece in the plane, 0 = no plane), the one-plane compat jamo as a piece
of their kind's plane, a compat jamo with more than one plane stored whole at U+3131 + k. Only the 2,350 KS syllables and
the 51 compat jamo compose (the other syllables are plain missing glyphs); `--with-jset` also derives the extrapolated
JSET as above (`--classes` or the search) and stores it as the JMAP fallback (`--jset-version` applies to it; its pieces
are numbered above the JMAP's, its compat entries blank), so all 11,172 compose (sizes of `--with-jset` on real Mac faces have not been measured); the JMAP block (fallback included)
must stay within 65,534 bytes. `--mode derived` writes the extrapolated face of the Method section above, byte for
byte what the tool wrote before direct mode. `verify` takes the mode from the face (a direct face needs no
`--classes`) and compares every code of `macfbit3.Fbit3(fbit, htbl).compose` (2,350 + 51) in Python and, with
`--svfdump`, in the C reader (build it with `-DSVF_JMAP=1`); the report of `build` gains `mode`, `jmap` (block bytes),
`pieces` (plane pieces), `fallback_pieces`, `pieces_as_slots` (one plane piece per referenced Mac slot) and `fallback`
(bytes). `verify_direct` refuses a LIST face (`verify: a LIST face (JSET version 3 flag 0x08) is not a direct-mode face`; the builder here is plane-only) and reports `non_ks_present` (syllables outside KS the face has pieces for), the C check
`non_ks_ink` (those whose cell has ink). `--sheets` / `--name` belong to `--mode derived`; direct refuses them.

**Optional tests with real inputs.** `tools/test_macfbit_svf.py` class `RealFaces` runs the five faces when `SVF_MAC71_INPUTS` names a
directory holding `Seoul12`, `AppleGothic12`, `AppleGothic24`, `AppleMyungjo12`, `AppleMyungjo24` as `<Name>.fbit` (the
decoded 'fbit' resource) and `<Name>.htbl1` (InputBackSupport 'HTBL' 1, the same file for every face). Fill it from your own decoded resources: the 'fbit' resource of
each font's resource fork (`python3 tools/macfbit3.py fbit FORK OUT`) and the 'HTBL' 1 resource of InputBackSupport:

```sh
DST=/path/to/mac71-inputs; mkdir -p "$DST"
for n in Seoul12 AppleGothic12 AppleGothic24 AppleMyungjo12 AppleMyungjo24; do
  python3 tools/macfbit3.py fbit "/path/to/forks/$n.rsrc" "$DST/$n.fbit"; cp /path/to/HTBL1.bin "$DST/$n.htbl1"; done
SVF_MAC71_INPUTS=$DST python3 -m unittest tools.test_macfbit_svf.RealFaces
```

**Outputs.** SVFN v3, 1 bpp, cell h x h (12 or 24), ascent h - h/6, JSET flag; pieces at U+F0000 + n; the
compatibility jamo by compat piece where the Mac glyph is a piece of its natural table, else stored whole; Latin with
per-glyph dy (a glyph wider than the cell is shifted into it, noted). `--report` writes JSON (classes, sets, sizes for
JSET v1 and v2, extrapolation counts, verification); `--sheets` writes PNG sheets (Mac vs face vs XOR, KS 1x/3x,
extrapolated samples, pieces; needs PIL).

**Synopsis.**
`python3 tools/macfbit_svf.py analyse FBIT HTBL1 [-o OUT.json]`
`python3 tools/macfbit_svf.py build FBIT HTBL1 -o FACE.SVF [--mode direct|derived] [--no-dedup] [--with-jset] [--classes OUT.json] [--latin SUITCASE.rsrc] [--latin-size N] [--report R.json] [--sheets DIR] [--name P] [--jset-version 1|2|auto] [--jset-big]`
`python3 tools/macfbit_svf.py verify FACE.SVF FBIT HTBL1 [--classes OUT.json] [--svfdump PATH ...]`

| Option | Default | Meaning |
|---|---|---|
| `--mode direct\|derived` | direct | JMAP face of the Mac structure (KS only), or the extrapolated JSET face |
| `--no-dedup` | dedup on | direct: one piece per Mac slot instead of one per distinct bitmap of a plane |
| `--with-jset` | off | direct: the derived JSET becomes the JMAP fallback (all 11,172 syllables compose) |
| `--classes FILE` | search | take `lc` / `tc` from an `analyse` JSON (derived, `--with-jset`, verify of a derived face) |
| `--latin FILE`, `--latin-size N` | none, the cell size | ASCII from the family's 'NFNT' strike |
| `--jset-version 1\|2\|auto` | 1 | JSET block version (`jamoset.pack_jset`; direct: of the `--with-jset` fallback; auto = `jamoset.choose_jset_version`) |
| `--jset-big` | off | derived and `--with-jset`: search up to 19 x 28 classes and fit to 128 / 128 / 64 sets; the JSET is written with `big=True` |
| `--svfdump PATH` | none | also compare the C renderer's syllables (`c/tests/svfdump.c`), repeatable |

`analyse` and `build` also accept `--out` for `-o`.

**Repository modules imported.** `jamoset`, `macfbit3`. **Third-party.** PIL for `--sheets` only. **Test.** `tools/test_macfbit_svf.py` (synthetic fbit / HTBL / NFNT fixtures).


### `tools/jamovec.py`

**Purpose.** Separate a font's jamo once, as outlines, into a master JSON, then render any size from it without fitting
again.

**Status.** General-purpose.

**Inputs.** `master` reads a TTF/OTF with fontTools (via `jamoaa.OutlineFace`; `--components` reads the `glyf`
composite components). `render` reads the master JSON.

**Outputs.** `master` writes a JSON master; `render` writes an SVFN v3 jamo-set face at 1 or 2 bpp.

**Synopsis.**

    python3 tools/jamovec.py master FONT -o MASTER.json [options]
    python3 tools/jamovec.py render MASTER.json --size N -o OUT.SVF [options]

`master` options: `-o`/`--output` (required); `--adaptive [NI,NM,NF]` (none; const `32,24,12`);
`--decision-px N` (48); `--class-limit N` (12, the engine's limit); `--components` (off); `--pylib DIR` (none).
`render` options: `--size N` (required); `--bpp {1,2}` (2); `--binarize {threshold,ridge}` (threshold);
`--cell WxH` (none); `--baseline N` (none); `--symbols` (off); `--check` (off); `--profile NAME` (`default`);
`--box x|y|full` (the profile's); `--jset-version 1|2|auto` (1); `--jset-big` (off); `-o`/`--output` (required).

**Repository modules imported.** `jamoaa.py`, `jamoset.py`, `jamoadapt.py`, `jamofit.py`. **Third-party.** fontTools
(required for `master`; the rasteriser is its own).

**Test.** `tools/test_jamoaa.py`.

### `tools/svfdy.py`

**Purpose.** Set or clear the per-glyph dy of an existing SVFN face: read with `jamoset.parse_svfn`, rewritten as v3 with `jamoset.pack_svfn`, so every glyph, metric, JSET block and flag is kept and only the dy fields change (glyphs end up in code point order, in the `--profile` layout).

**Status.** General-purpose.

**Inputs.** An SVFN v3 face with a metrics table, read with `jamoset.py` (a v2 face is refused with the convert message (`tools/svf2to3.py`)). `--json` reads a JSON object of code point to
dy.

**Outputs.** The face as v3 with the dy bytes and header range changed (same kind, bpp and pixels as the input).

**Synopsis.**

    python3 tools/svfdy.py INPUT [OUTPUT] [--range CPS --dy N] [--set CPS=N]... [--json FILE] [--clear] [--show] [--profile NAME] [--box x|y|full]

| Option | Default | Meaning |
|---|---|---|
| `--range CPS` | none | code points (e.g. `0x20-0x7e,0x2026`) given `--dy` |
| `--dy N` | none | the dy for `--range` |
| `--set CPS=DY` | none (repeatable) | code points and their dy |
| `--json FILE` | none | a JSON object `{code point: dy}` |
| `--clear` | off | every glyph's dy to 0 first |
| `--show` | off | print the range and the glyphs with a dy (no output needed) |
| `--profile NAME`, `--box x\|y\|full` | the input's layout, the profile's box | the SVFN v3 layout profile and ink box policy of the output (without `--profile` the input's own layout is kept) |

A dy on a jamo piece (`U+F0000..`) is refused. Code points the font lacks are counted and skipped.

**Repository modules imported.** `jamoset.py`. **Third-party.** None. **Test.** `tools/test_jamoset.py`.

### `tools/svfscale.py`

**Purpose.** Draw a bitmap face at a smaller pixel size (a 40 / 48 px DOS or printer face, a 24 px BDF, down to 16 px),
1 bpp by a threshold or 2 bpp by quantizing coverage to four levels. Downsampling a bitmap creates intermediate coverage.

**Status.** General-purpose.

**Inputs.** A 1 bpp SVFN v3 face (precomposed or a jamo set: every glyph is drawn through `svfline.py`, so a jamo set's
syllables are composed first) or a BDF (`bdfface.read_bdf`: KS X 1001 or Unicode encoding).

**Outputs.** A precomposed SVFN v3 face (variable width; flag bit 2, marks at origin, only when the source SVF has it,
since without it a negative bearing_x is no mark origin) of cell w x h, w = `round(W x h / H)`. Heights (ascent, per-glyph dy)
scale by h / H, widths (advances, a combining mark's negative bearing_x) by w / W, each rounded. Each glyph is resampled
from its own bitmap (`svfline.Face.coverage`: no dy shift, no mark origin, nothing clipped). An output pixel is the
exact share of its source footprint that is inked; 1 bpp keeps share >= `--threshold` (0 < threshold <= 1), 2 bpp
rounds the share to a coverage c of 0..255 and stores `(c x 3 + 127) // 255` (mkfont's rule). Sources over 64 MiB are
refused. `--compare` draws both faces on one baseline on a canvas that also holds every glyph's dy.

**Synopsis.** `python3 tools/svfscale.py SRC --size H [--bpp 1|2] [--threshold 0.5] [--chars ks|face|all|FILE] [--compare FACE.SVF] [--profile NAME] -o OUT.SVF`

| Option | Default | Meaning |
|---|---|---|
| `--size H` | required | the new cell height (below the source's) |
| `--bpp 1\|2` | 1 | threshold or four levels |
| `--threshold F` | 0.5 | 1 bpp: the inked share that keeps a pixel |
| `--chars` | `ks` | `ks`: ASCII 0x20-0x7E, the 2,350 KS X 1001 syllables and the source's other code points (not a jamo set's pieces in plane 15); `face`: what the source lists; `all`: with all 11,172 syllables; or a file of characters |
| `--compare FACE.SVF` | none | after writing a 1 bpp result, print its overlap with another 1 bpp face (mean IoU of the KS syllables both draw, both faces on one baseline, at the best shift within 2 px) |
| `--profile NAME`, `--box x\|y\|full` | `default`, the profile's | v3 layout profile and ink box policy |

Exit 1 with a message (not 1 bpp, `--size` below 1 or not below the source, a threshold outside (0, 1], `--compare`
with `--bpp 2`, a BDF `bdfface.py` cannot read). **Repository modules imported.** `jamoset.py`,
`svfline.py`, `bdfface.py`. **Third-party.** None. **Test.** `tools/test_extract.py` (box-filter levels of a synthetic
32 px BDF at 16 px, the 2 bpp level rule at 48 to 16 px, 24 to 16 px with a rounded ascent, scaled advances and a
dy, advances by w / W and a mark's bearing_x on a 29-wide cell, the overlap of faces of different ascent and of ink a
dy moves below the cell).

### `tools/svf2to3.py`

**Purpose.** Convert SVFN v2 faces to v3, and re-layout v3 faces into another profile, with a proof that no pixel,
metric or composed syllable changed.

**Status.** General-purpose. Every other writer writes v3 only; `jamoset.parse_svfn` reads v3 only (a v2 face is refused with the convert message, which names this tool); `svf2to3.py` holds the only v2 parser.

**Inputs.** An SVFN v2 or v3 face, or with `--tree` a folder searched recursively for `*.SVF` (any case).

**Outputs.** A v3 face written by `jamoset.pack_svfn`; with `--tree` the same relative paths below DST (SRC may equal
DST; other files are not copied). Each face is written to a temporary file beside its target, checked there when
`--check` is given, and renamed over the target only if the check passed.

**JSET version.** `--jset-version` defaults to 1 (v2 is for memory-constrained targets only): a v1 block stays v1 and a v2 block is written as v1; `2` writes v2, `auto` writes v2 when it is at least 1024 B smaller; an existing v2 block stays byte-identical under `2` or `auto`; `--jset-big` lets a re-encoded or verbatim-copied block (a v2 block, or the fallback of a JMAP region) exceed the standard limits. `--check` reports a face whose jamo set the parser refused as `composed=unchecked`. A JMAP region (JSET version 3) is copied verbatim (the output's region bytes equal the input's, piece numbers and all); `--jset-version` applies to nothing there and a note on stderr says so; `--check` composes both faces through `svfline.py` (a JMAP-only miss is not composed: the cmap glyph or none, as for a plain face) and the output line reads `jset=3 jmap=BYTES` (` list=1` more for a LIST region, flag 0x08, which is copied the same way and never re-encoded). The same reading applies in `svfline.py`, `maker/detect.py` (kind `svf-jamo`, `jset_version` 3, `jmap_mode` `dense` / `sparse` / `list`, usable only when plane pieces, fallback pieces and compat all have glyphs; `maker/quality.py` `face_facts` reports `pool` for a LIST: the number of distinct pieces the LIST block itself names, its entries and its own compat entries, not the fallback's) and `web/mkindex.py` (`jamo` true for such a face).

**Synopsis.**

    python3 -I tools/svf2to3.py IN OUT [--profile P | --units R,W,T,O] [--box x|y|full] [--jset-version 1|2|auto] [--jset-big] [--check]
    python3 -I tools/svf2to3.py --tree SRC DST [same options]

| Option | Default | Meaning |
|---|---|---|
| `--profile P` | `default` | a writer preset from the table below |
| `--units R,W,T,O` | none | log2 record, row and table units and the offset width 16 or 32 (box `x`) |
| `--box B` | the profile's | box policy: `x` (x-boxed), `y`, `full` (full cells) |
| `--check` | off | compare output with input through `svfline.Face`: has, metrics and cell of every code point and every composed syllable (U+AC00..U+D7A3, U+3131..U+3163) |
| `--tree` | off | convert a folder; prints `REL in= out= data_in= data_out=` per face and a last `total faces= ... data_out= v3_faces= v3_jset= v1_faces= ... failed=` line (`v3_*`: JMAP faces and their region bytes; a LIST region, copied verbatim like any version 3 block, adds ` list=1` to its line: ` jset=3 jmap=BYTES list=1`) |

| Profile | REC / ROW / TAB (log2) | Box | Offsets |
|---|---|---|---|
| `mcu-strict` | 4 / 1 / 4 bytes (2 / 0 / 2) | x | u16, u32 when the data passes `65535 << REC` |
| `default` | 4 / 1 / 4 bytes | x | u32 |
| `dos` | 1 / 1 / 1 bytes | x | u16, u32 past 64 KB |
| `wasm` | 1 / 1 / 1 bytes | x | u16, u32 past 64 KB |
| `full` | 4 / 1 / 4 bytes | full cells | u32 |
| `simd16` | 16 / 1 / 16 bytes | x | u32 |

Exit status: 0 every face passed; 1 a check difference (naming the first differing code point, or the marks-at-origin
flag); 2 an unreadable or invalid input, a SRC that is not a directory, or an unreadable subdirectory. A face that fails
leaves its target untouched and the run goes on. The last line's `faces=`, `in=`, `out=`, `data_in=` and `data_out=`
count converted faces only; `failed=` counts the others. SIGTERM removes the temporary file before exiting.

**Repository modules imported.** `jamoset.py`, `svfline.py`. **Third-party.** None. **Test.** `tools/test_svf2to3.py`
(fixtures in `tools/testdata/v2/`).

### `tools/svf2ttf.py`

**Purpose.** Turn an SVF face, precomposed or a jamo set, back into a bitmap font: a TrueType font (pixel outlines and
an embedded bitmap strike; references 5–8) or a BDF (reference 11); and compare two faces glyph by glyph (the round-trip check).

**Status.** General-purpose.

**Inputs.** An SVFN v3 face, read as the C library loads it (`svfline.Face`): its glyphs (a jamo set's pieces in U+F0000..U+FFFFF
left out, a precomposed face's private-use glyphs kept; surrogates and U+FFFF never) and, for a jamo set, every syllable
and compatibility jamo its table gives (composed by `jamoset.compose`). A face with nothing to export is an error. The licence note beside the
face (see Outputs) unless `--licence` names one.

**Outputs.**

- `ttf`: a TrueType font with `unitsPerEm` = ppem x 64 (ppem defaults to the cell height). `glyf`: each glyph's pixels
  of coverage >= `--threshold` (default 128: every 1 bpp pixel, 2 bpp levels 2 and 3) traced into contours, exact at ppem
  and its multiples, no hinting (a `prep` of one no-op keeps FreeType from autohinting it, so other sizes render the
  outlines with FreeType). `EBLC`/`EBDT`: one strike at ppem in the face's bit depth (1, 2 or 8; image format 1,
  index format 1), each glyph cut to its ink box with its bearings and advance (signed bytes: an ascent, descent, glyph
  bearing x or ink top, or a strike-wide least side bearing or ink extreme past -128..127 is an error that names the field and suggests `--no-strike`, which leaves the strike out, except a least right side bearing above 127, stored as 127;
  `--apple` adds it as `bloc`/`bdat` too). At most 65,534 glyphs. `cmap` (4, and 12 past U+FFFF), `hmtx` (the face's advances; a combining mark advance 0
  at its origin, as `svfline.py` places it), `hhea` / OS/2 typo metrics = ascent and cell height - ascent, OS/2 win
  metrics covering ink moved by a dy, `post` format 3, `head`, `maxp`, `gasp`, `name` (family, style, version, a
  description naming the face, and the licence: for a face of `svf/` the files its row of
  `web/LICENCES.tsv` names (a face under `svf/` with no row is an error unless `--licence` is given); elsewhere the
  `*.TXT` beside the face whose title line names its file or a pattern matching it plus the licence files it names,
  else the licence column of a `FACES.TSV` beside it; as name 13; the OFL file's copyright paragraph above its header
  as name 0; the OFL URL as name 14 when an OFL text is embedded). No GSUB, GPOS or conjoining-jamo
  shaping: the output is precomposed. Timestamps from `$SOURCE_DATE_EPOCH` when set. `--composite` (a jamo set): each
  jamo piece one glyph, every syllable a `glyf` composite of its pieces (`OVERLAP_COMPOUND`) and an `EBDT` compound
  bitmap (image format 8, its own index subtable); the compatibility jamo map to their piece glyphs. 2 and 8 bpp: piece bitmaps start at the pen, and a syllable whose
  pieces overlap with levels whose OR is not their maximum keeps an expanded bitmap (FreeType ORs compound
  components), as does one whose component offset would pass a signed byte (a cell over 128 px); the summary line
  counts them.
- `bdf`: BDF 2.1 (1 bpp) or 2.3 (2 / 8 bpp: the bit depth as the fourth field of `SIZE`; `--bpp1` cuts it to 1 bpp),
  ISO10646-1, each glyph its ink box (BBX) and advance (DWIDTH), `FONT_ASCENT` / `FONT_DESCENT` the face's, 72 dpi
  (`SIZE ppem 72 72`, `POINT_SIZE` ppem x 10, `SWIDTH` advance x 1000 / ppem), `AVERAGE_WIDTH`, the licence note as
  `COMMENT` lines and the copyright as `COPYRIGHT`, in UTF-8.
- `compare`: one line, `compared N glyphs: mismatches M (pixels P, advance A, inked only in A X, only in B Y); blank
  glyphs only one face has Z`, then the first differing code points. Glyphs are placed as `svfline.py` places them
  (pixels as coverage relative to the pen and baseline, and the advance); a blank glyph only one face has counts apart,
  except U+0020, U+00A0 and U+3000, which are mismatches.
- `cps`: the face's code points as `mkfont.py --unicode` ranges.

**Synopsis.**

    python3 tools/svf2ttf.py ttf FACE.SVF OUT.ttf [--family F] [--style S] [--version V] [--ppem N] [--threshold C]
                                                  [--licence FILE|none] [--no-strike] [--apple] [--composite]
    python3 tools/svf2ttf.py bdf FACE.SVF OUT.bdf [--family F] [--style S] [--version V] [--ppem N] [--threshold C]
                                                  [--licence FILE|none] [--bpp1]
    python3 tools/svf2ttf.py compare A.SVF B.SVF
    python3 tools/svf2ttf.py cps FACE.SVF

| Option | Default | Meaning |
|---|---|---|
| `--family F` | `<FACE STEM> SVF` | family name (the default never repeats the source font's name, which an OFL Reserved Font Name may forbid) |
| `--style S` | `Regular` | style name; "Bold" / "Italic" / "Oblique" set the corresponding OS/2 and `head` style bits; weight is 700 for Bold, otherwise 400 |
| `--version V` | `1.000` | name 5; numeric versions also set `head.fontRevision`, otherwise it is 1.0 |
| `--ppem N` | the cell height | the strike's size and the em (1..255) |
| `--threshold C` | 128 (1..255) | coverage a pixel needs to be in the outline (and in a `--bpp1` BDF) |
| `--licence FILE\|none` | the note beside the face | the licence note to embed; `none` embeds none |
| `--no-strike` (ttf) | off | outlines only |
| `--apple` (ttf) | off | also write the strike as `bloc`/`bdat` |
| `--composite` (ttf) | off | a jamo set: pieces once, syllables composite glyphs (glyf composites, EBDT format 8); a no-op with a note for a precomposed face |
| `--bpp1` (bdf) | off | a 2 or 8 bpp face as a 1 bpp BDF |

Exit status: 0; 1 an unreadable face (every subcommand), a value out of range (`--ppem` outside 1..255, a strike
field), a face with nothing to export (`compare`: 1 when mismatches > 0); 2 a usage error. A face
under `svf/` that `web/LICENCES.tsv` does not cover exits 1 unless `--licence` is given; a face
elsewhere with no licence note beside it prints a warning and gets a line saying its source font's licence applies.

The round trip and its results on six faces (precomposed and jamo sets, 1 and 2 bpp, 16 and 24 px, an HWP 1.x face):
[recipes/svf-and-ttf.md, An SVF face back to a TTF bitmap font](recipes/svf-and-ttf.md#an-svf-face-back-to-a-ttf-bitmap-font); `--composite`
on six jamo sets (sizes, expanded bitmaps, limits): [Composite glyphs](recipes/svf-and-ttf.md#composite-glyphs---composite).

**Repository modules imported.** `jamoset.py`, `svfline.py`. **Third-party.** fontTools (`ttf`). **Test.**
`tools/test_svf2ttf.py` (on faces of `svf/`: glyph set and composition count, metrics and names, the strike against the
face, 2-bit strike, FreeType renders at 1 x, 1.5 x (unhinted) and 2 x, the `mkfont.py` round trip with and without the strike, dy, BDF;
`--composite`: component counts and offsets, `maxp`, the compound strike resolved as FreeType does, the 2 bpp
expanded-bitmap set, renders, the 2 bpp round trip, fontTools recompile, the precomposed no-op).


### `tools/svf_synth.py`

**Purpose.** Write synthetic SVFN faces for the C renderer's tests, built with `jamoset.write_svfn`.

**Status.** Test/support-only.

**Inputs.** `--from` a valid jamo-set face for every kind but `--marks`.

**Outputs.** A synthetic SVFN face: a jamo set with a broken JSET block (one bad kind), a valid face with a JMAP (JSET
version 3) block or a broken one, an 8 bpp face, or a 16 px 1 bpp flag-bit-2 marks face.

**Synopsis.** `python3 tools/svf_synth.py (--jset-bad KIND | --reencode | --jset-variant V | --jmap-variant V | --jmap-bad KIND |
--jset-unused-finset | --jset-cut N | --bpp8 | --marks | --layout-bad KIND) [--from FACE] [--jset-version 1|2] OUT`

`--jset-version` is the JSET block version of every JSET written and, unlike the shipped writers, **defaults to 2**:
this is a test tool and most of its cases exercise the version 2 reader and its refusals. `--jset-bad KIND` breaks one
rule of the block: the version 2 kinds are `lc13`, `tc13`, `ni33`, `nm25`, `nf17`, `length`, `leadclass`, `finset`,
`initset`, `missing_piece`, `magic`, `version`, `version4`, `short`, `na_over`, `reserved`, `pad_bits`,
`alias_no_presence`, `abase_over`, `alias_blank`, `missing_alias_piece`, `base_wrap`, `compat_set_over`,
`compat_slot_blank`, `compat_bits56` and the `compat_*_bit7` kinds; with `--jset-version 1` the version 1 kinds are
`lc13`, `tc13`, `ni33`, `nm25`, `nf17`, `length`, `leadclass`, `finset`, `missing_piece`, `magic`, `version`, `short`.
The five count kinds `lc13` ... `nf17` (`BAD_KINDS_STD`) are bad only for the narrow readers: a BIG reader and
`jamoset.unpack` read them as valid tables. The BIG kinds `lc20`, `tc29`, `ni129`, `nm129`, `nf65` (`BAD_KINDS_BIG`,
both versions) are one past one BIG cap each and refused by every reader
(`python3 tools/svf_synth.py --help` and the module docstring describe each). `--reencode` rewrites FACE's JSET block in
the `--jset-version` (1: `pack_v1`, piece numbers kept; 2: `pack`, pieces renumbered). `--jset-variant V` writes a
valid version 2 block of another shape (`alias`, `bit7`, `overlap`, `limits`, `w0`; version 2 only) or, for
BIG readers, `limits_big` (19 x 28 classes, 128/128/64 sets, no alias: 29,708 B in version 2, 47,373 B with
`--jset-version 1`) and `limits_big_alias` (the same with every slot an alias, 45,068 B; version 2 only), each with a
glyph for every piece.
`--jmap-variant V` writes a valid JSET version 3 (JMAP) block built from FACE's tables by `jamoset.jmap_from_tables`
(`sparse3`, `sparse4`, `dense3`, `dense4`, `hybrid1`, `hybrid2` with 16 exception syllables over a version 1 or 2
fallback, `dhybrid1` / `dhybrid2` (dense, 3 / 4 byte entries, over a version 1 / 2 fallback: a 34 / 45 KB region), `hybrid_big1`, `hybrid_big2` (BIG fallbacks), `adv0`, `adv0fb` (advance 0 in the JMAP and in its version 1 fallback), `sparse_full` (the SPARSE flag with all 11,172 entries, assembled by hand because `pack_jmap` writes that count dense), `blanks`, `pi2047`); `--jmap-bad KIND` breaks one JMAP rule (the 23 `JMAP_BAD_KINDS`, the module
docstring names the rule of each; `jmap_missing_piece` and `jmap_region_max` have a valid block and fail the piece-glyph
rule and the 65,534 byte region cap in the reader; `v2_as_v3` is the first rule its fields break, R3 for NEODG16G).
LIST variants and kinds are their own lists (`LIST_VARIANTS`, `LIST_BAD_KINDS`; `JMAP_VARIANTS` and `JMAP_BAD_KINDS` keep their 15 and 23 names, `--jmap-variant` / `--jmap-bad` accept both): `--jmap-variant list1` (38 entries, s = 0, 300, ..., 11,100: whole cells and recombinations differing from the fallback's own, over the source's own fallback version re-encoded with advance 16), `list2` (version 2 fallback, pieces renumbered 5, 3, 9, ...), `list_nofb` (one entry, no fallback), `list_blank`, `list_zero`, `list_compat`, `list_max` (255 entries, keys 0 and 11,171, no fallback, 2,158 bytes) and `list_big` (over the `limits_big` tables); `--jmap-bad` takes 22 `jlist_*` kinds, byte edits of `list1` (`jlist_short_nofb`, `jlist_length` of `list_nofb`), each breaking one rule of `unpack_jmap` (R1, L2, L3, R4, L6; the module docstring names them) except `jlist_field_noglyph`, `jlist_field_fffe`, `jlist_compat_noglyph` (`parse_svfn` marks the face bad) and `jlist_region_max` (header JSET size 0x10000).
Both ignore `--jset-version`, need a FACE with JSET tables (not itself a JMAP face), and drop the piece glyphs' dy (the
planes are written without dy); the 3 byte kinds refuse a FACE that gives a 4 byte block and the 4 byte kinds one that gives
a 3 byte block (a clear error). `sparse4`/`dense4` pad all three planes past 255 and name padded pieces from index 256;
`pi2047` is built by hand; `hybrid1` blanks one JMAP compat entry so the fallback's answers it. `--from FACE` is required by every kind but `--marks`. `--profile P` / `--units R,W,T,O` and `--box`
choose the v3 layout (default: the `default` profile; not with `--layout-bad`). There is no default output path.

**Repository modules imported.** `jamoset.py`. **Third-party.** None. **Test.** `tools/test_c_renderer.py`.

### `tools/jamofill.py`

**Purpose.** Build a small jamo-set face at a bitmap reference's own size: keep a set skeleton (classes, set tables,
optionally which slots share a piece) and take every piece from the reference's syllables. Used to build 12 px faces within a byte budget.

**Status.** Research builder.

**Inputs.** `--strike` a bitmap survey strike (`NAME-PX.npz`: `cp`, `glyphs`, `meta`, optional `adv`; read without
numpy). `--skeleton` `FACE.SVF` (its classes and set tables, every slot its own piece), `FACE.SVF:tied` (also its
sharing: slots whose pieces are one bitmap stay one piece), or a named structure: `111`, `224` (initial and medial by
final or not, final by the 8x4x4 vowel group), `621`, `844` (jamoset.py's layouts), `fine` (a 2 x 3 class, 63 / 6 / 42
set start for `sweep`, over the format limits until merged). `--pieces` optional extra jamo libraries
(`pieces-NAME.json` of `galmuri_jamo.py analyse`).

**Method.** The strike's syllables are split into initial, medial and final (`decompose_strike`: per-context cores, the
long horizontal runs of a horizontal or mixed vowel's bar as the vowel's, the rest by geodesic growth over inked
neighbours), the variants used at least three times are kept, and a variant with more horizontal or vertical strokes
than the strike's own compatibility jamo is dropped (`stroke_filter`: a neighbour's stroke taken in). Each piece
(unit) then takes, by coordinate descent, the variant that best composes the units' syllables against the strike's
own: a missing reference pixel costs `MISS` (2), an extra one 1, a pixel two pieces both ink `OVERLAP` (3), a pixel
touching another piece `TOUCH` (0.25); weights 1.0 for the 2,350 KS X 1001 syllables, 0.2 for the rest. Two hard
gates: a candidate piece whose parallel strokes differ in width (`width_violation`: ㅍ with a 1 px and a 2 px stem, a
crushed ㅃ) or a medial whose tick is missing or on the wrong side of its bar (`tick_ok`: ㅗ ㅛ ㅘ ㅙ ㅚ above, ㅜ ㅠ ㅝ ㅞ
ㅟ below, ㅡ none), or a ㅊ / ㅎ that lost its cap, bar or body (`cap_ok`), is refused (`shape_filter`,
`stroke_filter`, and for pixel-best pieces); and medial distinctness
(`Fill.medial_violations`) costs `MEDIAL_PENALTY` (30, unweighted) per violation: a syllable closer than min(2, the
reference's own distance) pixels to the syllable with another vowel of its group (ㅗㅛㅜㅠㅡ, ㅏㅑㅓㅕㅣ, ㅐㅒㅔㅖ,
ㅘㅙㅚㅝㅞㅟㅢ) under the same initial and final, or whose tick is covered by another jamo (a tick that only touches
one costs a fifth). Stroke completeness (`complete_ok`, table `COMPLETE`): a single consonant keeps its horizontal
and vertical strokes of 2+ pixels, ㄲ ㄸ ㅃ keep two separate bars in their top / bottom ink rows; a ㄲ ㄸ ㅃ whose bars
run together (Galmuri9 draws its 12 px ㄲ so) is offered repaired, one pixel cut between the bars (`split_double`).
Leaks (`leak_masks`, `Fill.leak_mask`): in a context (vowel shape, final group) a pixel the jamo inks in under 5 % of
its syllables of the reference split while another jamo there inks it in 30 % or more is a leak, `LEAK_PENALTY` (40)
per pixel per user. A caller can ban bitmaps per unit (`Fill.banned`, {unit: set}): a banned candidate never wins (the
recogniser gate of the Uno work runs this way: misread piece banned, fill re-run). With `--pixel`
each unit may also take its pixel-by-pixel best bitmap (only pixels the split gives its jamo), added to the pool. Set
tables are compacted on writing (sets whose pieces agree merge, then lead and tail classes whose set columns agree;
`build_face(fill, compact=False)` / `plain_tables` keep the sets and classes as they are).
`--budget N` ties units of one jamo (least loss per byte saved) until the file fits.

**Outputs.** `fill`: one face (`-o`), SVFN v3 `mcu-strict`, JSET version 1, the strike's printable ASCII (proportional,
from its `adv`) and the distinct pieces; read back and every syllable checked against the fill. `--report` JSON:
`bytes`, `pieces`, `jset_bytes`, classes and set counts, `exact` / `exact_ks`, `mean_dist_ks`, `confuse_ks` (syllables
within 2 pixels of a syllable one jamo away where the reference's two differ more, by category: `oug` ㅗ ㅛ ㅜ ㅠ ㅡ,
`hieuh` initial ㅎ, `final`, `initial`, `vowel`), `overlap_ks` (final piece sharing pixels with the vowel piece),
`missing3_ks`, `extra4_ks`, `medial_violations(_ks)`, `medial_pairs` (per vowel pair: contexts, violations, smallest
distance, worst contexts), `tick_merged_ks` (missing or covered), `tick_touch_ks`, `width_violation_count`,
`width_violations` (jamo), `stem_widths` (vertical stroke widths per jamo), `incomplete_pieces` (ㄲ first),
`leak_units` and `leak_pairs` (piece>neighbour: pixels), with KS examples. `sweep`: greedy set merges from the skeleton (the merge that loses
least), a face and report at the first state at or below each `--points NI,NM,NF`, and `PREFIX-curve.json`. `sheet`:
`PREFIX-ks-{1,4}x.png` (the 2,350 KS syllables, 50 a row), `PREFIX-text-{1,4}x.png` (a sample text) and, with
`--strike`, `PREFIX-vs-ref-4x.png` (20 common syllables over the reference's).

**Synopsis.** `python3 tools/jamofill.py fill --strike S.npz --skeleton SK [--pixel] [--budget N] [--pieces J ...]
-o FACE.SVF [--report R.json]`; `python3 tools/jamofill.py sweep --strike S.npz --skeleton SK [--pixel] [--budget N]
--points NI,NM,NF ... [--prefix P] -o DIR`; `python3 tools/jamofill.py sheet FACE.SVF [--strike S.npz] -o PREFIX`.
The weights can be changed for experiments through `JAMOFILL_MISS`, `JAMOFILL_OVERLAP`, `JAMOFILL_TOUCH` and
`JAMOFILL_OWN` (default 1; 0: `--pixel` may take any pixel), `JAMOFILL_MEDIAL_PENALTY` and `JAMOFILL_LEAK_PENALTY`.

`fill` and `sweep` also accept `--no-decompose` (off), `--raw-variants` (off), `--no-stroke-filter` (off),
and `--per-jamo N` (40): skip strike decomposition, add raw variants, skip stroke filtering, and limit variants per library and jamo.
`sweep --prefix` defaults to `SWP`. `sheet --text FILE` reads UTF-8 sample text (default: built-in text).
The long form of `-o` is `--out` for `fill`, `--outdir` for `sweep`, and `--prefix` for `sheet`.

**Repository modules imported.** `jamoset.py`. **Third-party.** Pillow (`sheet` only). **Test.**
`tools/test_jamofill.py` (a synthetic strike of context-free jamo: split, exact 1/1/1 and 8x4x4 fills, compaction,
set merges, budget ties, stroke widths, ticks, the ㅊ/ㅎ cap, stroke completeness and the ㄲ repair, leak masks,
the medial gate, the command line).

### `tools/jamomerge.py`

**Purpose.** Make a many-variant jamo-set face smaller by merging its variants, keeping every piece as drawn. Written
for many-variant faces (for example 13 initial sets by vowel class and final, many medial runs) that must fit an
Arduino Uno budget (8,192 B, JSET version 1, ASCII included).

**Status.** Research builder.

**Inputs.** `--face` a jamo-set SVF (JSET version 1 or 2; JMAP/LIST is refused, and output tables must fit the standard limits). `--ref` the reference face (default: the face
itself; give the unmerged face to continue from a merged one). `--planes` optional reference jamo planes JSON (written
by the `planes` subcommand from a Mac type-3 `fbit` and its `HTBL` 1; the KS reference syllables then come from them).

**Method.** The face is a merge state: lead and tail classes, the three set tables and a bitmap per used slot. Moves:
`tie` (every slot of one jamo drawing bitmap x draws y, another variant of that jamo), `set` (two sets of one kind
become one; per jamo the variant, among all the jamo's present variants, with the least objective over both sets'
users), and lead / tail `class` merges (per (vowel, other class) cell and kind the set of either side; for the
initial in a lead merge and the final in a tail merge also a union set holding both sides' pieces, since their jamo
are disjoint; an empty slot is filled with the syllable's present bitmap). After each move unused slots and sets are
dropped and sets that agree, then lead and tail classes whose rows agree, are merged for free. Greedy: every move is
scored by the pixel objective against the reference (a lost reference pixel `MISS` 2, an extra one 1, a pixel two
pieces share `OVERLAP` 1; KS X 1001 syllables weight 1.0, the others `JAMOMERGE_OTHER`, default 0.1) per byte saved;
with `--recog` the best `JAMOMERGE_RECOG_TOP` (16) are re-scored by recog-11-12 (weighted top-1 errors + 0.2 x
log-loss over the changed syllables; the separately supplied `recog.py`, found through `SVF_RECOG_DIR`, inference only) and the best per byte is applied. Hard
gates, per syllable and only against what the move makes worse: `tick` (a ㅗ/ㅛ/ㅜ/ㅠ/ㅡ-type medial's tick missing or
covered by another piece, all syllables), `medial` (two KS syllables of one medial group with the same initial and
final closer than min(2, reference distance) pixels), `stroke` (a reference run of 2+ pixels in a KS syllable with no
counterpart on its line or a neighbouring one covering all but one pixel), `leak` (a component of the KS syllable
joining two components of the reference: ink bridging a gap), and with `--recog` `recog` (a changed slot's most
neutral syllable, read correctly on that jamo before, misread after). With `--soft`, once no gated move is left (the
gated floor, written as `PREFIX-floor.SVF`), `stroke` and `leak` become costs (`JAMOMERGE_SOFT`, 40 per KS syllable);
`tick` and `medial` stay hard. Non-KS syllables are composed from the merged tables like the KS ones; their stroke
and leak flags only cost (20 x weight).

**Outputs.** In `-o DIR`: per `--points` budget the face `PREFIXnK.SVF` (SVFN v3 `mcu-strict`, JSET version 1, the
face's ASCII with its metrics and dy; read back and every syllable checked) and `PREFIXnK.json` (bytes, parts, sets,
classes, pieces, gate counts, stem widths per jamo as drawn, recogniser top-1 with `--recog`, `soft_gates`);
`PREFIX-steps.json` (every applied move: kind, saved bytes, pixel and recogniser deltas, changed syllables, refusals
by gate); `PREFIX-stop.SVF/.json` where no move is left. `baseline` prints (or `-o`) the face's size parts in
`mcu-strict` / JSET v1, the fixed part (header, ASCII, smallest JSET), the gate counts and stem widths.

**Synopsis.** `python3 tools/jamomerge.py baseline --face F.SVF [--planes P.json] [-o R.json]`;
`python3 tools/jamomerge.py merge --face F.SVF [--ref UNMERGED.SVF] [--planes P.json] --points 8192 7168 ... [--recog
[--threads N]] [--soft | --start-soft] [--batch] [--prefix P] -o DIR` (`--batch`: far over the next point, several
ties of distinct jamo with disjoint syllables per step, pixel objective only; the batch is undone to its best move when
together they break a gate); `python3 tools/jamomerge.py planes FBIT.bin HTBL1.bin -o
P.json`.

The long form of `-o` is `--out` for `baseline` and `planes`, and `--outdir` for `merge`.

**Repository modules imported.** `jamoset.py`, `jamofill.py`. **Third-party.** None (numpy and torch with `--recog`).
**Test.** `tools/test_jamomerge.py` (synthetic faces: build / read round trip and size, normalisation, every move
composing as it promises, a greedy step, the leak, stroke and tick gates).

### `tools/jamoexc.py`

**Purpose.** Write a LIST exception face: a jamo-set face plus whole glyphs and piece recombinations for chosen
syllables and compat jamo, as a JMAP block in list mode ([SVF specification](../spec/SVF.md), JMAP LIST). The face's own JSET bytes stay as the
fallback, so every syllable not listed draws as before.

**Synopsis.** `python3 tools/jamoexc.py build FACE.SVF EXC.json OUT.SVF [--jset-version 1|2] [--profile P] [--box B]`.

**EXC format.** A JSON object keyed by a syllable or a compat jamo, as the character (`"가"`, `"ㄱ"`) or `"U+AC00"`; a key
named twice is refused. A value is `{"whole": "HEX"}` (`cell_h` rows of `ceil(cell_w * bpp / 8)` bytes as hex; hex rows
only, no PNG input) or `{"pieces": [n, n, n]}` (piece numbers of the face: 1 to 3 for a syllable, exactly one for a
compat key). A `whole` cell becomes a new piece glyph numbered above the highest U+F0000 + n code point of the face
(syllables ascending, then compat jamo ascending); a number 0xFFFF (BLANK) is never given out. Any other key in a value
(`dy`, `advance`, ...) is refused: exception entries cannot specify dy or metrics. Composition does not use piece-glyph metrics.

**Output.** One line, `jmap=BYTES ns=N whole=W recomb=R total=BYTES`: `jmap` the byte size of the JMAP block (LIST
header, entries, compat and the verbatim fallback), `ns` the number of syllable entries in the LIST, `whole` the new
whole glyphs written (one per `"whole"` value, syllables and compat jamo), `recomb` the entries given as `"pieces"`
(syllables and compat jamo; a `"whole"` is not counted there), `total` the byte size of the output file. From N >= 200
the line ends ` sparse=BYTES` (1604 + 3 N: the size of a SPARSE block of N entries, to weigh against the LIST).
Example on `svf/dos/NEODG16G.SVF` with `{"가": {"pieces": [1, 2]}, "ㄱ": {"pieces": [3]}}`:
`jmap=779 ns=1 whole=0 recomb=2 total=10808`.

**Fidelity.** The output keeps the source's layout (rec/row/tab/off units kept; the box policy is x unless `--box` is given, pixels
identical; `--profile` changes the layout on request), its JSET version and bytes (`--jset-version 1|2` re-encodes the
fallback through `pack_fallback`, piece numbers kept, only when the version changes; nothing else ever re-encodes it), and every source glyph's cell, advance, bearing, ink width and dy. A new
piece gets the metrics of the face's first piece glyph and dy 0. The output file is written only on success, through a temporary file followed by a rename.

**Refusals (exit 1, text on stderr; usage errors exit 2).** More than 255 entries: `jmap_list: N LIST entries is over
255: use SPARSE (1604 + 3N B plus plane copies for recombinations)`. A version 3 source (`the face already has a JSET
version 3 block; start from the plain face`). A face without a usable JSET (`the face has no usable JSET block; start
from a jamo face whose JSET parses`). A `whole` of the wrong length (names the expected byte count) or not hex, a compat
key with other than one piece or with 65535 (BLANK; omit the key to keep the fallback's), a key written twice (also
literally in the JSON), keys other than one character or `U+` plus 4 to 6 hex digits, an EXC with no syllable entry
(`a LIST needs at least one syllable entry (L3); compat jamo alone cannot be listed`), glyph data that outgrows u16
offsets (the text names the way out: drop whole cells, or `--profile` with u32 or auto offsets), a syllable with 0 or more than 3, a piece number without a glyph, a key outside
U+AC00..U+D7A3 and U+3131..U+3163, an unknown key in a value.

**Repository modules imported.** `jamoset.py`. **Third-party.** None.
**Test.** `tools/test_jamoexc.py` (synthetic cells over `svf/dos/NEODG16G.SVF`: Python `compose` equals `svfdump
syllables` of the LIST reader build, mapped and streamed; layout, metrics and dy fidelity for a `default` and a `dos`
source; the sparse note at 200; the refusals; the version re-encode).

## 3. Fitting and separation modules (no command line)

`jamofit.py`, `jamoaa.py` and `jamoadapt.py` are imported by `jamoset.py` and `jamovec.py`; `jamoseg.py` is imported
by no tool, only by `tools/test_jamoaa.py`. None of them has a `main`.

### `tools/jamoaa.py`

**Purpose.** Anti-aliased (2 bpp) jamo sets from an outline font, and the shared outline rasteriser/contour logic for
`jamoset.py --from-ttf --bpp 2` and `jamovec.py`.

**Status.** General-purpose.

**Inputs.** An outline font read with fontTools (glyf or CFF, composites decomposed), through a fontTools pen.

**Outputs.** None directly; it returns coverage rasters, packed levels, fitted pieces and tables that the callers write.

**CLI.** None. Its functions are called by `jamoset.main_aa` and `jamovec.py`.

**Repository modules imported.** `jamofit.py`, `jamoset.py`, `jamoadapt.py` (lazily). **Third-party.** fontTools
(required for its outline paths; looked up via `--pylib` or `$JAMOSET_PYLIB`).

**Test.** `tools/test_jamoaa.py`.

### `tools/jamoadapt.py`

**Purpose.** Adaptive set systems for fitted jamo sets: start from 844 and split sets where the syllables that share a
piece disagree, up to the engine's JSET limits (12 lead and 12 tail classes, 32/24/16 sets).

**Status.** General-purpose.

**Inputs.** "Donors": each present syllable's own raster per slot, from `jamoaa.contour_donors` (outline) or
`jamoaa.pixel_donors` (bitmap).

**Outputs.** A `jamoset.Layout` named `adaptive` whose tables encode the mapping (no file).

**CLI.** None; reached through `jamoset.py --layout adaptive` and `jamovec.py --adaptive`.

**Repository modules imported.** `jamoset.py`. **Third-party.** None.

**Test.** Exercised by `tools/test_jamoaa.py` (the `--layout adaptive` cases).

### `tools/jamofit.py`

**Purpose.** Fit jamo-set pieces to precomposed 1 bpp syllables with a masked coordinate descent, and score the fit
(IoU, 1 px tolerant F1, blob and stray-ink metrics).

**Status.** General-purpose.

**Inputs.** Glyph rasters as Python integers ("gints"); an optional outline mask font (NotoSansKR with OpenType jamo
variants) read with freetype-py and shaped with uharfbuzz.

**Outputs.** Fitted pieces and quality numbers (no file).

**CLI.** None; used by `jamoset.py --from-ttf`/`--from-svf` and `bdfface.py --fill-absent`.

**Repository modules imported.** None. **Third-party.** freetype-py and uharfbuzz (optional: only the mask font and the
outline `mono` targets need them).

**Test.** `tools/test_jamoset.py` (imports it directly) and `tools/test_jamoaa.py`.

### `tools/jamoseg.py`

**Purpose.** Vector jamo segmentation: split a syllable's outline into its initial, medial and final as outlines, in
font units, by contour grouping, peers and region clipping.

**Status.** General-purpose.

**Inputs.** Syllable outlines in font units (from a fontTools pen).

**Outputs.** Per-syllable lists of closed polylines per slot and how each group was decided (no file).

**CLI.** None. **Repository modules imported.** None. **Third-party.** skia-pathops (`pathops`, optional: its
`load_pathops` returns None without it) for clipping merged outlines.

**Test.** `tools/test_jamoaa.py`.

## 4. Inspection and checking

### `tools/facecheck.py`

**Purpose.** Face manifest and map-face checks: record the sha256 of every committed face, verify a manifest after a
move, and check that every face a map names can be found.

**Status.** General-purpose.

**Inputs.** Git blobs (`manifest`), a manifest TSV (`verify`), map files and optionally a builtin zip (`mapfaces`).

**Outputs.** A manifest TSV, or `MISSING`/`CHANGED` lines and an exit code. It writes no font.

**Synopsis.**

    python3 tools/facecheck.py manifest --git REPO --rev REV --path DIR [--path DIR ...] [--exclude GLOB] [--exclude GLOB ...] -o OUT.tsv
    python3 tools/facecheck.py verify MANIFEST.tsv [--map OLD_PREFIX=NEW_DIR] [--map OLD_PREFIX=NEW_DIR ...]
    python3 tools/facecheck.py mapfaces --maps DIR [--maps DIR ...] --root PREFIX=DIR [--root PREFIX=DIR ...] [--builtin-zip FILE] [--builtin-zip FILE ...]

Every list option is `action="append"`: give one value per flag and repeat the flag. `manifest`: `--git`, `--rev`,
`--path` (required), `--exclude`, `-o` (required). `verify`: `MANIFEST.tsv`, `--map`. `mapfaces`: `--maps` (required),
`--root` (required), `--builtin-zip`.

**Repository modules imported.** None. **Third-party.** None (git, zipfile). **Test.** `tools/test_facecheck.py`.

### `tools/fontmetrics.py`

**Purpose.** Report whether a face's advances clear its glyphs: print the header, the advances and ink widths seen, and
list glyphs whose `bearingX + inkWidth` reaches past the advance.

**Status.** General-purpose.

**Inputs.** SVFN v3 faces, read with `jamoset.parse_svfn`.

**Outputs.** A text report (no file).

**Synopsis.** `python3 tools/fontmetrics.py FACE [FACE ...]` (no options).

**Repository modules imported.** `jamoset.py`. **Third-party.** None. **Test.** None.

### `tools/svfline.py`

**Purpose.** The Python reference for the C renderer's line drawing: decode UTF-8, pick each code point's face from a
chain, draw cells on one baseline with advances, dy and combining marks, and measure a line.

**Status.** General-purpose.

**Inputs.** SVFN faces, read with `jamoset.parse_svfn` and the engine's load rules (a dy range only when valid, a
metrics table only when it fits, a JSET block only when it unpacks and every piece has a glyph).

**Outputs.** A GRAY8 buffer on stdout (`line`) or a one-line measure (`measure`). Also a library: `layout`, `measure`,
`placements`, and the `Target` conversions.

**Synopsis.**

    python3 tools/svfline.py line W H X Y TEXT FACE...
    python3 tools/svfline.py measure TEXT FACE...

No options. `TEXT` is the argument's bytes, decoded as UTF-8 (invalid subparts become U+FFFD, or are skipped when no
face has it). The library takes `scale=(num, den)` for the renderer's scaling.

**Repository modules imported.** `jamoset.py`. **Third-party.** None. **Test.** `tools/test_c_renderer.py` and
`tools/test_web_picker.py`.

### `tools/vesa_lines.py`

**Purpose.** The Python reader of `c/ports/dos/vesa-lines.txt` (the DOS VESA example's table of colours and lines) and
the oracle of that example: the back buffer `c/ports/dos/svfvesa.c` should hold after drawing the file's lines. Its
parser matches `c/ports/dos/vesa_lines.c` (same table, palette and refusal message at the same line); change the two
together.

**Status.** Special-purpose (the DOS VESA example).

**Inputs.** A `vesa-lines.txt` file (format in `c/ports/dos/vesa_lines.h` and `c/ports/dos/README.md`) and, for
`--expect`, a directory of the faces it names (8.3 upper-case `.SVF` names).

**Outputs.** `--print-table`: the parsed table and palette as `c/tests/vesa-lines-dump` prints it. `--expect`:
`sum=<FNV-1a of the expected back buffer, 8 hex digits>`. A refusal prints `line N: message` and exits non-zero.

**Synopsis.**

    python3 tools/vesa_lines.py --print-table FILE [--dac 6|8]
    python3 tools/vesa_lines.py --expect FILE --faces DIR W H BPP

`BPP` is 8, 15, 16, 24 or 32 (INDEXED8, RGB555, RGB565, RGB888, XRGB8888).

**Repository modules imported.** `svfline.py` (and through it `jamoset.py`). **Third-party.** None. **Test.**
`tools/test_c_renderer.py` (`TestVesaLines`); used by `c/ports/dos/vesa-shots.sh`.

### `tools/doc_figures_jamo.py`

**Purpose.** Draws the pixel figures of [jamo-sets.md](jamo-sets.md) (pieces and composition, the sets of one jamo,
precomposed against jamo set, the JSET version 1 lookup of one syllable).

**Status.** Special-purpose (documentation).

**Inputs.** Only the OFL faces `svf/iolo/SANS8J.SVF` (reference 12) (8x4x4 jamo set) and `svf/dos/NEODG16.SVF` (precomposed); it
refuses any other path, so no Apple or ROM data can reach a published figure.

**Outputs.** `compose.png`, `sets.png`, `precomposed.png`, `lookup.png` in `docs/images/jamo-sets/` (indexed PNG, fixed
palette: the same bytes on every run), and one line comparing the two faces over the 2,350 KS X 1001 syllables.

**Synopsis.**

    python3 -I tools/doc_figures_jamo.py [--out DIR] [--check]

`--check` renders in memory and compares with the files in `DIR` byte for byte (exit 1 on a difference).

**Repository modules imported.** `jamoset.py`. **Third-party.** Pillow. **Test.** `--check`.

### `tools/doc_figures_split.py`

**Purpose.** Draws the pixel figures of [jamo-split.md](jamo-split.md) (a precomposed syllable with its fitted pieces,
recomposition and difference; an exact against an approximate fit; the blank medial ㅡ pieces of `NEODG16A`; touching
strokes of an outline font at 12, 16 and 24 px; mean IoU against bytes for each set system) and prints the measurements
the document quotes. The set-system chart plots the fit results recorded in the script's `BUDGET` table (measured with
`jamoset.py --from-ttf`, about 10 minutes); it does not re-run those fits.

**Status.** Special-purpose (documentation).

**Inputs.** Only the allowed OFL fonts: `ttf/nanumgothic/NanumGothic-Regular.ttf` (baked by `mkfont.py`'s `render()` at
16 px, `--clip-cell`, and fitted to 8x4x4 by `jamoset.fit_font` in memory), `svf/dos/NEODG16.SVF` (comparison and
labels), `svf/dos/NEODG16A.SVF` and `svf/jamo-extra/NDGPR16.SVF`; it refuses any other path, so no Apple, ROM or
proprietary data can reach a published figure.

**Outputs.** `split.png`, `exact.png`, `blank.png`, `touch.png` (indexed PNG, fixed palette) and `budget.png` (RGB) in
`docs/images/jamo-split/` (no metadata: the same bytes on every run with the same Pillow and FreeType, both printed), and lines with the fit's bytes,
exact count and mean IoU over the 2,350 KS X 1001 syllables, the comparison of `NEODG16A` with `NEODG16`, the syllables
whose medial ㅡ piece is inkless, and the ink component counts of the touch figure.

**Synopsis.**

    python3 -I tools/doc_figures_split.py [--out DIR] [--check]

`--check` renders in memory and compares with the files in `DIR` byte for byte (exit 1 on a difference or a missing file).
It takes about a second.

**Repository modules imported.** `jamoset.py`, `jamofit.py` (through `jamoset`), `mkfont.py`. **Third-party.** Pillow.
**Test.** `--check`.

### `tools/doc_figures_aa.py`

**Purpose.** Draws the pixel figures of [anti-aliasing.md](anti-aliasing.md) (one syllable at 1/2/8 bpp, the 2 bpp
levels on each target, 2 bpp jamo composition by maximum against OR, outline to coverage to levels, downscaling from a
36 px face, one line on MONO, GRAY, GRAY8, RGB565 and XRGB8888).

**Status.** Special-purpose (documentation).

**Inputs.** Only the allowed OFL fonts: `svf/jamo-extra/GOTHA16.SVF`, `GOTHA16A.SVF`, `SGDAY16A.SVF`,
`NSQRR16.SVF`, `svf/dos/NSQRR36.SVF`, `NSQRR16A.SVF`, `PAPLG16.SVF`, `PAPLG18.SVF`, `NEODG16.SVF` (labels) and
`ttf/nanumgothic/NanumGothic-Regular.ttf`; it refuses any other path, so no Apple or ROM data can reach a published
figure. Glyphs are read and drawn through `svfline.py` (faces, line layout, `Target`) and, for the outline figures,
`mkfont.py`'s `render()` packed by `jamoset.pack_svfn`.

**Outputs.** `bpp.png`, `levels.png`, `compose.png`, `outline.png`, `downscale.png`, `targets.png` in
`docs/images/anti-aliasing/` (RGB PNG, no metadata: the same bytes on every run with the same Pillow and FreeType,
both printed), and one line saying whether the 2 bpp downscale equals the draw-time scale quantised to 4 levels.

**Synopsis.**

    python3 -I tools/doc_figures_aa.py [--out DIR] [--check]

`--check` renders in memory and compares with the files in `DIR` byte for byte (exit 1 on a difference).

**Repository modules imported.** `jamoset.py`, `svfline.py`, `mkfont.py`, `svfscale.py`. **Third-party.** Pillow.
**Test.** `--check`.

### `tools/doc_figures_x11.py`

**Purpose.** Draws the sample images of [recipes/x-window.md](recipes/x-window.md): one per face the recipe builds
(Daewoo Gothic 16, Daewoo Mincho 16 and 24, Baekmuk Gulim, Batang and Dotum 16 and Gulim 12, the hanterm johab844-1
font `dkbgoth` and johab-1 font `johabm16`, Hanyang Gothic 16, KAIST newmj 16, iyagi 16 and philgi 16).

**Status.** Special-purpose (documentation).

**Inputs.** Folders and files as arguments: `--misc DIR` (the X11 core fonts folder: the Daewoo PCFs and the ASCII fonts
`8x16.pcf.gz`, `12x24.pcf.gz`, `6x12.pcf.gz`, required), `--baekmuk DIR`, `--hanterm DIR`, `--hanyang DIR`, `--newmj F`,
`--iyagi F`, `--philgi F`; no path to a font is written in the script, and a face whose files are not there is
skipped. Each face is built in a temporary directory by the recipe's commands (`maker/srcprep.py pcf-bdf`,
`bdfface.py --symbols`; `mkfont.py` for the ASCII face and `jamoset.py --layout hanterm-844 / hanterm-johab --base
--check` for the hanterm fonts), run with `python3 -I`.

**Outputs.** PNG files in `docs/images/recipes/x-window/` (8-bit grey, black on white, every pixel doubled, no
metadata): per face four lines, two Korean pangrams, an English line, the ASCII symbols and the KS X 1001 symbols
`※☆★○●◎◇◆□■△▲→←↑↓`. A character the face lacks is left out of its line and printed (the jamo sets have no symbols).

**Synopsis.**

    python3 -I tools/doc_figures_x11.py --misc DIR [--baekmuk DIR] [--hanterm DIR] [--hanyang DIR] [--newmj F] [--iyagi F] [--philgi F] [--out DIR] [--check]

`--check` renders in memory and compares with the files in `DIR` byte for byte (exit 1 on a difference or a missing
file, and when a face was skipped because its option was not given or its file is not there; it lists them, so a
partial run never reports `ok`). The images depend only on the font files.

**Repository modules imported.** `svfline.py`, `binscan.py` (and the tools it runs). **Third-party.** Pillow (through
`mkfont.py`, for the ASCII face of the hanterm fonts). **Test.** `--check`.

### `tools/doc_figures_mac.py`

**Purpose.** Draws the sample images of [recipes/classic-mac.md](recipes/classic-mac.md): one per face (the HangulTalk 1.0
'fbit' fonts Gotic12 and Munjo24; the HangulTalk 7.1.2 type-3 'fbit' fonts Seoul12, AppleGothic12 and AppleMyungjo24;
the 'bloc'/'bdat' strikes of the Korean System 7.5.3 bitmap-only fonts AppleGothic 12 and 16, AppleMyungjo 16 and 24,
Seoul 12 and 16, #신명조 16 and #궁서체 16; Hangang 16 of Mac OS 8.5).

**Status.** Special-purpose (documentation).

**Inputs.** Folders as arguments: `--ht10 DIR` (the HangulTalk 1.0 System Folder: `Gotic12.rsrc`, `Munjo24.rsrc`),
`--ht712 DIR` with `--htbl FILE` (the 7.1.2 CD's `[splt]` archives and family suitcases, and its
`InputBackSupport[INIT].rsrc`), `--kh753 DIR` (the 7.5.3 CD's bitmap font install folder, `NAME/NAME[FFIL].rsrc`),
`--kh85 DIR` (the Mac OS 8.5 font folder, `한강체[FFIL].rsrc`). No path to a font is written in the script, and a face
whose files are not there is skipped. Each face is built in a temporary directory by the recipes' commands
(`jamoset.py --layout mac-fbit-45sets --check`; `srcprep.py mac-htbl`, `macfbit3.py unpack` / `fbit`,
`macfbit_svf.py build --latin` and `verify`; `macsfnt.py extract` / `unicode` and `mkfont.py --size N --bpp 1` at a
strike's size, which the script reads from the font's `bloc` / `EBLC` table with a bounds-checked reader), run with
`python3 -I`; a short bootstrap adds the user site-packages to the tools' path so that `macsfnt.py` and `mkfont.py`
find a user-installed fontTools (the font folders and the working directory never enter the path).

**Outputs.** PNG files in `docs/images/recipes/mac/` (8-bit grey, black on white, every pixel doubled, no metadata): per
face the four lines of `tools/doc_figures_x11.py`. A character the face lacks is left out of its line and printed, and
a line left empty is dropped (the HangulTalk 1.0 fonts hold Hangul only; the 7.1.2 faces have no KS X 1001 symbols). A
face without U+0020 advances half a cell at a space. Each line printed gives the face's cell, size in bytes and the
first line's `width ascent descent`.

**Synopsis.**

    python3 -I tools/doc_figures_mac.py [--ht10 DIR] [--ht712 DIR --htbl F] [--kh753 DIR] [--kh85 DIR] [--out DIR] [--check]

`--check` renders in memory and compares with the files in `DIR` byte for byte (exit 1 on a difference or a missing
file, and when a face was skipped because its option was not given or its file is not there; it lists them, so a
partial run never reports `ok`). The 'fbit' images depend only on the font files; the strike images also on Pillow and
its FreeType (printed); the images in the repository were made with Pillow 10.2.0 and FreeType 2.13.2.

**Repository modules imported.** `doc_figures_x11.py`, `svfline.py`, `binscan.py` (and the tools it runs).
**Third-party.** Pillow and fontTools (through `mkfont.py` and `macsfnt.py`). **Test.** `tools/test_doc_figures_mac.py`
(the strike reader on synthetic and truncated tables, the skip report), `--check`.

## 5. Build scripts

### `tools/build/build_faces.py`

**Purpose.** Rebuild the faces of `svf/` from their upstream fonts with the tools above, as the recipe table
`tools/build/faces.tsv` says, and compare each result with the face in `svf/`.

**Status.** General-purpose (the provenance check of the shipped faces; [recipes/svf-faces.md](recipes/svf-faces.md) explains every recipe).

**Inputs.** `tools/build/faces.tsv` (face, method, source, args, codepoints, expect, note; one row for every face of
`svf/`), the code point lists under `tools/build/cps/`, and the source fonts in `ttf/`. A row whose source is
`ext:NAME` names an externally supplied font; `--ext NAME=PATH` supplies it, else the row is reported
`skipped`.

**Outputs.** `OUT/<face>` for every row it builds, and one line a face on stdout: `identical` (the same bytes as
`svf/`), `pixels` (the same glyphs, metrics and header values in another byte layout) or `differs: ...` (what differs),
then a `build_faces:` total line. Writes nothing outside `OUT`.

**Synopsis.** `python3 tools/build/build_faces.py --out DIR [FACE ...] [--ext NAME=PATH ...] [--list]`. FACE is a row's
face (`dos/NGOTB15.SVF`) or its file name; none means every row with a recipe. Exit 0 when every built face matches its
row's `expect` (an `identical` row must be identical), 1 otherwise, 2 for a usage error. `mkfont` rows run
`tools/mkfont.py SOURCE OUT ARGS --unicode CODEPOINTS` and then `tools/svf2to3.py --profile default` (the canonical
record order of `svf/`); `jamoset` rows run `mkfont.py` with the arguments before `|` and `tools/jamoset.py --from-svf`
with those after it.

**Repository modules imported.** `tools/jamoset.py` (and it runs `mkfont.py`, `svf2to3.py`, `jamoset.py`).
**Third-party.** Those of `mkfont.py` (Pillow, fontTools). **Test.** `tools/test_build_faces.py`.

### `tools/build/faces.tsv`

**Purpose.** The recipe table of `tools/build/build_faces.py`: one row for every face of `svf/` (face, method, source,
args, codepoints, expect, note). `method` is `mkfont`, `jamoset` or `none` (no recipe with the tools above;
the note says why). `codepoints` names a `mkfont.py --unicode` set or a file under `tools/build/cps/` (one hex code point
or range a line, the face's own code point list). [recipes/svf-faces.md](recipes/svf-faces.md) explains every row; `tools/test_build_faces.py`
keeps the table complete.

## 6. Web (WASM picker)

### `web/build.sh`

**Purpose.** Build the WASM font picker: the C renderer as `svf.js` + `svf.wasm`, the face index, and the face and
licence files.

**Status.** General-purpose.

**Inputs.** The C sources under `c/`, `svf/`, and the page sources. It needs emcc from emsdk.

**Outputs.** Under `OUT` (default `web/dist`): `svf.js`, `svf.wasm`, `faces.json`, `faces/<group>/<FILE>.SVF`,
`licences/<group>/<FILE>`, and copies of `index.html`, `picker.js`, `style.css`.

**Synopsis.** `bash web/build.sh [OUT]`. Env: `EMSDK` (default `~/opt/emsdk`). It calls `web/mkindex.py` and
`web/copyfaces.py`.

**Repository modules imported.** None (it runs `web/mkindex.py` and `web/copyfaces.py`). **Third-party.** emscripten
(`emcc` from emsdk). **Test.** `tools/test_web_picker.py` (through `web/build.sh`).

### `web/copyfaces.py`

**Purpose.** Copy the faces and licence files a `faces.json` names from `SVF_DIR` into `OUT`, checking every path
stays under the roots.

**Status.** General-purpose.

**Inputs.** `SVF_DIR` and a `faces.json` (read with the standard `json` module).

**Outputs.** The copied face and licence files under `OUT` (no font is changed).

**Synopsis.** `python3 web/copyfaces.py SVF_DIR FACES_JSON OUT` (no options). It prints `F faces, N MB copied` and
exits 2 on the first bad path.

**Repository modules imported.** None. **Third-party.** None. **Test.** `tools/test_web_picker.py` (through
`web/build.sh`).

### `web/mkindex.py`

**Purpose.** Write `faces.json` (format `svf-fonts-web-index/1`), the face index of the picker, from `svf/` and the
licence and family tables.

**Status.** General-purpose.

**Inputs.** Every `svf/**/*.SVF`, read with `tools/jamoset.py parse_svfn` and `tools/svfline.py Face` (loaded by path);
`LICENCES.tsv` and `FAMILIES.tsv` (and `svf/jamo-extra/FACES.TSV`).

**Outputs.** `faces.json`, one entry per face (key, url, group, label, cell, px, bpp, ascent, glyphs, jamo, flags,
bytes, licences, hangul, latin_only, subset, family, style, variant). It writes no font.

**Synopsis.** `python3 web/mkindex.py SVF_DIR OUT_JSON [--licences TSV] [--families TSV]` or
`python3 web/mkindex.py SVF_DIR --check [--licences TSV] [--families TSV]`.

| Option | Default | Meaning |
|---|---|---|
| `--check` | off | run every check, write nothing |
| `--licences TSV` | `LICENCES.tsv` beside this script | face-to-licence table |
| `--families TSV` | `FAMILIES.tsv` beside this script | face-to-family table |

**Repository modules imported.** `tools/svfline.py` (and through it `tools/jamoset.py`). **Third-party.** None.
**Test.** `tools/test_web_picker.py`.

## 7. Finding and cutting fonts out of files

The worked examples are in [recipes/programs-and-drivers.md](recipes/programs-and-drivers.md#finding-a-font-inside-a-program-or-data-file-with-claude) (a
DOS TSR, a DOS driver), [recipes/rom-86box.md](recipes/rom-86box.md#korean-vga-font-roms-86box) (Korean VGA font ROMs) and [recipes/os2.md](recipes/os2.md#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set)
(OS/2). These tools read bytes and never run the file's code; run them with `python3 -I` on downloads.

### `tools/binscan.py`

**Purpose.** Find where a bitmap font sits inside any file (a `.COM`/`.EXE`, a TSR, a ROM dump) and draw what is at an
offset, so a person or an assistant can see where a font starts and how it is stored.

**Status.** General-purpose.

**Inputs.** Any file. Glyph geometry: `--glyph WxH`, `--stride B` (default the glyph's bytes), `--order rows` (row-major,
ceil(W/8) bytes a row), `strips` (8-pixel-wide strips of H bytes one after another: the Korean VGA font ROMs and the
6x2x1 fonts, jamoset's `g_bytecols`), `cols` (column-major, MSB at the top: the Dokkaebi printer layout), `bytecols`
(8-row bands of W bytes, one byte a column, bit 7 the band's top row), `--lsb` (bit 0 = the left pixel, or the top one
in `cols` / `bytecols`), `--invert` (ink is the 0 bits: ROMs stored as paper, such as the Samsung SPC-1500's).
Multi-bit tiles (arcade sprite and tile ROMs): `--gfx LAYOUT`, a preset `WxHxN_packed_lsb` / `WxHxN_packed_msb` (N bits a
pixel row after row; `_lsb` puts a byte's first pixel in its low bits, MAME's `gfx_16x16x4_packed_lsb`) or the driver's
MAME `gfx_layout` as `planes=..;x=..;y=..;inc=N` (bit offsets from the tile's start, bit 0 the MSB of its first byte,
`planes` from the pen's high bit; MAME's `STEP2` .. `STEP1024(start,step)` and their `_INV` forms (the same offsets
reversed; MAME defines `STEP2_INV` and `STEP4_INV`, the larger ones are accepted too), `RGN_FRAC(a,b)` = a/b of the file in bits, `+ - * /`, decimal numbers without a leading 0 and 0x hex; copy
the lists without their braces and without C comments; at most 1,024 offsets a list and 32 levels of nesting, offsets
up to 2^36); the file is then the ROM region (`rawcarve.py region`). A pixel is ink when its pen is not `--bg PEN` (0), or, with
`--fg PEN[,PEN...]`, when it is one of those (the body of an outlined glyph; `--bg` and `--fg` are two rules: give one,
and only with `--gfx`); `--invert` swaps ink and paper. `--glyph`
defaults to the tile's size and `--stride` to its `inc`. `render` reads only the bytes it draws (`--count` 1..4096, `--cols` 1..64, `--scale` 1..32),
`info` a block at a time.

**Outputs.** Text on stdout; `render --png` writes a grey PNG (zlib, no Pillow).

**Synopsis.**

    python3 tools/binscan.py info FILE [--block B]
    python3 tools/binscan.py runs FILE (--glyph WxH | --gfx LAYOUT [--bg PEN | --fg PENS]) [--invert] [--min N] [--max-change C] [--start O] [--length N]
    python3 tools/binscan.py sets FILE [--sets NI,NM,NF] [--slots SI,SM,SF] [--glyph WxH] [--invert] [--min-inked F] [--start O] [--length N]
    python3 tools/binscan.py ascii FILE [--height H] [--invert] [--start O] [--length N]
    python3 tools/binscan.py render FILE --offset O (--glyph WxH | --gfx LAYOUT [--bg PEN | --fg PENS]) [--invert] [--count N] [--cols C] [--png OUT --scale S]

Defaults: `info --block 4096`, `runs --max-change 2.5`, `sets --sets 8,4,4 --slots 20,22,28`,
`ascii --height 16`. `--limit N` on `sets` and `ascii` limits the candidate groups printed (20).
`render` defaults to offset 0, up to 64 glyphs, 8 columns above 12 px width (otherwise 16), and scale 3.

| Command | What it prints |
|---|---|
| `info` | size, kind (DOS MZ with its load image and an LZEXE / PKLITE mark, `.COM`, ARJ, ZIP, option ROM `55 AA`), the layouts whose byte size the file matches, an entropy map a block (near 8 bits a byte = packed) |
| `runs` | runs of at least `--min` (32) inked glyph-like windows (ink 2-60 %, rows that change little) |
| `sets` | offsets where every set's slot 0 of a raw jamo-piece font is blank and at least `--min-inked` (0.8) of the other slots have ink; of a cluster of nearby passing reads the one whose rows hold together across the byte seams (x = 7 / 8), listing reads a whole row apart, which score the same, together and unranked (decide from the driver's code or a loose copy) |
| `ascii` | offsets of 8xH English fonts: space blank, `_` in the bottom third, `-` in the middle, 0x21-0x7E inked; of a cluster the alignment with the fewest glyphs inked in their first or last row |
| `render` | the glyphs from an offset, as `#`/`.` text labelled with index and file offset, or as a PNG |

`sets` and `ascii` try every byte offset of the scan window. `runs` tries phases spaced by `--step`: by default `ceil(W/8)` for `rows`, `ceil(H/8)` for the other 1 bpp orders, and one tile stride for `--gfx`. Use `--step 1` to try every byte offset: `--start O` / `--length N` name the window (offsets
printed stay file offsets), and a window above 16 MiB is refused (scan a large file in overlapping windows); `runs --gfx` reads the whole file (also limited to 16 MiB) and scans the window; `runs` and `render` (its default
`--count`) take only tiles whose whole footprint is in the file; `sets` refuses `--gfx`, `--bg` and `--fg` (write an
ink map with `rawcarve.py ink` first). Use `--order strips` for the Korean VGA font ROMs. Exit 0; argparse errors
(a `--gfx` layout that does not parse, lacks one of its four keys, has an `inc` that is not whole bytes, a background or
ink pen outside the planes, a `--glyph` that is not the tile's, `--fg` without `--gfx`; a zero or negative `--block`, `--step`,
`--stride`, `--glyph`, `--count`, ...) exit 2. **Repository modules imported.** None. **Third-party.** None. **Test.**
`tools/test_extract.py`; `tools/test_tiles.py` (`--invert`, `--gfx` presets and a driver's layout string against tiles
built by hand, `--bg`, `--fg`, the refusals).

### `tools/msx1_harvest.py`

**Purpose.** Read the syllable layout of a Korean MSX1 Hangul ROM (모아쓰기 mode) off the running machine in openMSX:
the emulator types a BASIC program that prints every syllable, and the name table of each screen is dumped (recipes/rom-msx.md,
Korean MSX fonts, MSX1).

**Status.** Special-purpose (the Daewoo / Goldstar MSX1 family); a template for other machines.

**Inputs.** An openMSX machine name and an output prefix outside the repository; the emulator as `--emu DIR` (an
openMSX unpacked into `DIR/root`, system ROMs in `DIR/userdata/share/systemroms`) or `--openmsx BIN`. `--first`,
`--count` pick the syllables (all 11,172 by default).

**Outputs.** `PREFIX.tcl` (the openMSX script), `PREFIX.index` (one hex code point a line), `PREFIX.names` (768 bytes a
screen of 77 syllables, the last screen padded with its last syllable), `PREFIX.patterns` (2,048 bytes), `PREFIX.png`
(a raw screenshot of the last screen), for `msxfont.py msx1-verify`.

**Synopsis.** `python3 tools/msx1_harvest.py MACHINE PREFIX (--emu DIR | --openmsx BIN) [--first N] [--count N]
[--timeout 600] [--script-only]`. It runs `timeout T xvfb-run -a openmsx -machine MACHINE -script PREFIX.tcl`; ROM code
runs only inside the emulator. Exit 1 with a message on a prefix inside the repository or with a space or Tcl special
character, no emulator given, or an incomplete harvest (with the emulator's last lines).

**Repository modules imported.** None. **Third-party.** openMSX and `xvfb-run` (the run only). **Test.**
`tools/test_msx1_harvest.py` (stored bytes, screens and padding, the typed program and the Tcl script, refusals; no
emulator).

### `tools/msxfont.py`

**Purpose.** The Korean MSX fonts that are not a plain glyph table: the code-to-slot map of the Daewoo CPC-400 / 400S
precomposed font ROM, and the Korean MSX1 syllables built from the BIOS's 8x8 cells by the Hangul ROM's layout rule
(recipes/rom-msx.md, Korean MSX fonts).

**Status.** Special-purpose (one machine family).

**Inputs.** `kfn-map`: the 64 KB `CPC-400S.U44` image (or its last 16 KB, the "Kanji control ROM"). `msx1`: a Korean
MSX1 BIOS (the character table at `--offset`, default 0x1B49). `msx1-verify`: an emulator harvest `PREFIX.index`,
`PREFIX.names`, `PREFIX.patterns` (and `--bios` for the cell check).

**Outputs.** `kfn-map`: `SLOT U+XXXX` lines (the syllables the driver's lists A and B reach) for `rawcarve.py bdf
--chars map`. `msx1`: a Unicode BDF of the 11,172 syllables (8x16 or 16x16, advance = width) and ASCII 0x20-0x7E (the
8x8 cells, `--ascii-top` rows down, default 8; `--ascent` 16). `msx1-verify`: the number of syllables whose cells the
machine drew as the rule says, and the pattern-table cells equal to the BIOS's.

**Synopsis.** `python3 tools/msxfont.py kfn-map U44 -o MAP.txt`, `python3 tools/msxfont.py msx1 BIOS [--offset O]
[--ascii-top N] -o OUT.bdf`, `python3 tools/msxfont.py msx1-verify PREFIX [--bios BIOS]`. Exit 1 with a message on a
file of the wrong size (refused before it is read), start offsets that are not a sorted list, an `--ascii-top` outside
0..8 or `--ascent` outside 0..16, an empty harvest index or one naming a code point that is not a syllable, short name
tables, a pattern table that is not 2,048 bytes, a syllable that differs, or (with `--bios`) a cell other than the
cursor 0xFF that differs.

**Repository modules imported.** `binscan.py`, `rawcarve.py`. **Third-party.** None. **Test.** `tools/test_msxfont.py`
(synthetic control ROM, cell table and harvest; the layout cases; `rawcarve.py bdf --chars map`).

### `tools/nkpspec.py`

**Purpose.** Write the `rawcarve.py compose` spec of an NKP Hangul TSR (the 1989 Hercules Hangul drivers NKP.COM V3.00,
NKP3.COM) from the driver's own tables: the piece-set records, the jamo tables and the initial-set and medial selection
tables of its Hangul routine (recipes/programs-and-drivers.md, NKP).

**Status.** Special-purpose (one driver family); it shows the shape of a driver-table-to-spec script for other drivers.

**Inputs.** The driver's .COM image. Table addresses are found by the instruction bytes that use them (`find`), or given
as memory addresses (`--desc`, `--cho`, `--jung`, `--jong`, `--iset`, `--med`; file offset = address - 0x100).

**Outputs.** `find`: one line a table (memory address, file offset; the English font's too). `spec`: the JSON spec
(offsets and rules only): a record with flag bit 0 set is a 16-pixel piece of (end - first) / 2 rows, one with it clear
a right- (or left-) half piece of (end - first + 1) / 2 rows of one byte; the initial-set and medial tables name records
by byte offset (record = value / 6); the final set is record 96.

**Synopsis.** `python3 tools/nkpspec.py find FILE`, `python3 tools/nkpspec.py spec FILE [--desc A ...] -o SPEC.json`. Exit
1 with a message when a table is missing, outside the file, or not in the NKP shape (jamo tables not in Unicode order,
a record offset not a multiple of 6, a piece address below 0x100, a 16-pixel record of no row).

**Repository modules imported.** None. **Third-party.** None. **Test.** `tools/test_extract.py` (a synthetic .COM with the
instruction patterns and tables; the spec's geometry and a composed syllable).

### `tools/rawcarve.py`

**Purpose.** Cut a font found with `binscan.py` out of its file into what the other tools read: raw bytes, a raw 8x16
English font, a Unicode BDF of ASCII or of KS X 1001 syllables, or the syllables of a jamo-piece font composed by a
rule written as a JSON spec.

**Status.** General-purpose.

**Inputs.** Any file; for `region` the ROM files of a MAME region; for `compose` a spec (below). Geometry options as
`binscan.py` (with `--invert`, `--gfx`, `--bg`, `--fg`).

**Outputs.** `cut`: the bytes. `eng`: 4,096 bytes (256 glyphs of 8x16; an 8xH font padded to 16 rows, `--top` rows
above), or with `--width 16` 8,192 bytes (256 glyphs of 16x16, 2 bytes a row); `--first C` is the code of the glyph at
the offset and `--count N` how many are read (the other codes stay blank), `--invert` reads the 0 bits as ink. `region`: the files of each group (`A,B[,C,D]`) interleaved `--unit` 1, 2
or 4 bytes at a time (MAME's `ROM_LOAD16_BYTE` / `ROM_LOAD32_BYTE` = 1, `ROM_LOAD32_WORD` / `ROM_LOAD64_WORD` = 2), the
groups one after another, `--swap` swapping the bytes of each word (`ROM_LOAD16_WORD_SWAP`); files of a group must have
the same size, a whole number of units; at most 64 MiB (checked from the files' sizes before reading; an empty group is refused). `ink`: the glyphs from
`--offset` (`--count`, default all that fit; more than fit is refused) as plain 1 bpp row-major glyphs one after another, ceil(W/8) x H bytes each: an inverted, strip-ordered or
multi-bit font made into the bytes `binscan.py sets`, `rawcarve.py cut` / `eng` / `bdf` and `jamoset.py --layout 844`
read. `bdf`, `compose`: a BDF with `CHARSET_REGISTRY "ISO10646"`, `CHARSET_ENCODING "1"`, `PIXEL_SIZE` = the glyph
height, `FONT_ASCENT` = `--ascent` (default 7/8 of the height, rounded up), every glyph the full cell; blank KS glyphs
are left out.

**Synopsis.**

    python3 tools/rawcarve.py cut FILE --offset O --length N -o OUT
    python3 tools/rawcarve.py eng FILE --offset O [--height H] [--top T] [--first C] [--count N] [--width 8|16] [--invert] -o OUT
    python3 tools/rawcarve.py region FILE[,FILE...] [FILE[,FILE...] ...] [--unit 1|2|4] [--swap] -o OUT
    python3 tools/rawcarve.py ink FILE (--glyph WxH [--order O] | --gfx LAYOUT [--bg PEN | --fg PENS]) [--invert] \
        [--offset O] [--count N] -o OUT
    python3 tools/rawcarve.py bdf FILE [--offset O] (--glyph WxH | --gfx LAYOUT) [--invert] \
        --chars ascii|ks-hangul|ks-nonhanja|ks-all [--first C] [--count N] [--dense | --grid L0,T0,PITCH] [--ascent A] -o OUT.bdf
    python3 tools/rawcarve.py bdf FILE [--offset O] --glyph WxH --chars map --map MAP.txt [--ascent A] -o OUT.bdf
    python3 tools/rawcarve.py compose FILE --spec SPEC.json|spc1500 [--invert] [--syllables ks|all] \
        [--eng FILE2 --eng-offset O --eng-height H --eng-top T] [--ascent A] -o OUT.bdf

`bdf --chars ks-*` places each KS X 1001 code by `--dense` (glyph i = the i-th code of the set: a 2,350-syllable dump)
or `--grid L0,T0,PITCH` (glyph = (lead - L0) x PITCH + (trail - T0): `0xA1,0xA1,94` a full table, `0x80,0x80,128` the
Korean VGA ROMs; a code whose lead is below L0 or whose trail is outside T0 .. T0 + PITCH - 1 is refused); `--chars map`
places glyph GLYPH at U+XXXX for each `GLYPH U+XXXX` line of `--map` (a font in a machine's own order; `msxfont.py
kfn-map` writes one; UTF-8, `#` comments; a malformed line or a glyph past the file's end is refused with the file and
line). Negative
offsets, a `--length` / `--stride` / `--count` below 1, a negative `--first` and `--top` + `--height` past 16 rows are
refused; `cut`, `eng` and `bdf` read only the bytes they use (through the last glyph's whole footprint, also with a
`--stride` shorter than a glyph), `compose` reads the whole file (up to 64 MiB). A compose
spec with a cell outside 1..256, a negative piece, an unknown set or `--eng-top` + `--eng-height` past the cell is
refused with a message. The compose spec names piece sets (`offset`, `stride`, and where the stored piece goes in the cell:
`x`, `y`, `width`, `height`, `order`, and optionally `lsb`, `invert`, `gfx` with `bg` / `fg`, and `slots`, a list
that renumbers the set's pieces when the font's numbering skips stored slots; a top-level `"invert": true`
or `--invert` inverts every set that does not say `"invert": false`, and the `--eng` font), the initial set per vowel without and with a final, the medial (set, piece) per
vowel (optionally another table for ㄱ / ㅋ, the 8x4x4 rule), the final set per vowel or one set, and the font's own
vowel order; jamo are numbered as Unicode numbers them (the module docstring has the format). `--spec spc1500` (the name always
means it; a JSON file of that name is `./spc1500`) is the built-in spec of the Samsung SPC-1500 Hangul ROMs (`spc1500_spec`, from MAME's
`spc1500.cpp`), for the 32 KB region of `ss150fnt.bin` .. `ss153fnt.bin` one after another; `tools/specs/msx2-daewoo.json`
is the spec of the Daewoo MSX2 jamo-set font (the 9,280-byte block cut from a CPC-300 / 400S ext ROM, see the recipes);
`jamoset.py --layout spec` reads the same specs. Exit 1 with a message on
a bad offset, spec or empty result.

`region --group FILE...` is a repeatable group input. `bdf --name` defaults to `carved`;
`compose --name` defaults to `composed`. `bdf` and `ink` also accept `--stride`, `--order`, and `--lsb`
(defaults: glyph byte size, `rows`, off). Writing commands also accept `--output` for `-o`.

**Repository modules imported.** `binscan.py`. **Third-party.** None. **Test.** `tools/test_extract.py` (a carved
8x4x4 font builds with `jamoset.py`; a KS grid ROM; a compose spec of the 8x4x4 rule equals jamoset's composition;
`tools/specs/msx2-daewoo.json` equals the Daewoo rule written out independently on a synthetic block, `slots`);
`tools/test_tiles.py` (inverted fonts through `eng`, `ink`, `bdf` and `compose`; `region` interleaves, groups and swaps;
`ink` and `bdf` of packed and planar tiles; the built-in `spc1500` spec; with `MAME_ROMS` set, the real SPC-1500, Date
Quiz Go Go and X Se Dae Quiz ROMs by hash).

### `tools/os2dbcs.py`

**Purpose.** Decode an OS/2 "System DBCS" font (`$korZN16.FNT`, `$korZN24.FNT`; the Japanese and Chinese ones share the
format) into its glyph table.

**Status.** General-purpose. The module docstring describes the decoding format.

**Inputs.** A System DBCS file (header "System DBCS NN"): 512-byte blocks of records from 0x1A00, each a Huffman-coded
nibble stream undone through a context table of the two rows above. A record never crosses its block, and the rest of a
block is 0xFF padding (glyph number 0xFFFF). The header is checked from the first 0x1A00 bytes before the rest is read
(files over 16 MiB are refused). Refused with a message: a file shorter than its tables, a cell outside 1..64 or bytes
a glyph other than ceil(w / 8) x h, a record running past its block or the file, glyph numbers out of order, a code
running past its record's payload or ending before its last byte (a record length that does not match its data:
the length of every record of the two OS/2 Warp 4 fonts matches), bytes other than 0xFF after a block's padding mark
or a record header cut off by the block end. A corrupted length that still matches some valid code stream cannot be
told from a real one.

**Outputs.** `info`: the header (cell, bytes a glyph, lead bytes, glyph number ranges, records, syllables present).
`table`: every glyph number 256..8997 in order (8,742 slots, absent ones blank), row-major: the KS X 1001 94 x 94 table
from A1A1, for `rawcarve.py bdf --grid 0xA1,0xA1,94`.

**Synopsis.** `python3 tools/os2dbcs.py info FILE`, `python3 tools/os2dbcs.py table FILE -o OUT.bin`. Exit 1 with a
message for a file without the header.

**Repository modules imported.** None. **Third-party.** None. **Test.** `tools/test_extract.py` (a synthetic font with
its own code table: escape-coded nibbles, a context table that is not the identity, sparse glyph numbers over several
blocks, and the bad-file refusals; with `JOHAB_FONTS` naming the research tree, hashes of the decoded real
`$korZN16.FNT` and of 가, 각, 힝, and 가 / 힝 against the renders in its notes).

### `tools/tbmfont.py`

**Purpose.** Read the header of a Korean Windows 3.1 / Windows 95 `.TBM` bitmap font (`BT16.TBM`, `BT20.TBM`,
`GULIM16.TBM`, `GULIM12.TBM`) and print where its glyph blocks start, for `rawcarve.py bdf`; write the KS X 1001 slot
map of its symbol and hanja blocks. Worked example: [recipes/windows.md](recipes/windows.md).

**Status.** Special-purpose (one font format). The module docstring describes the file layout.

**Inputs.** A TBM file (signature "TTBITMAP VARIABLE-PITCH HANGEUL", files over 16 MiB are refused): the cell size,
the range records and the 7-byte glyph table. Refused with a message: no signature, a range whose two size fields
differ, that runs past the file or does not follow the one before, a glyph table that is not whole entries, a glyph
that does not fit its range or does not follow the one before.

**Outputs.** `info`: the size, cell, ranges, glyphs, the data's span and the bytes after it, the glyphs grouped by
size, and for the 128 + 8,366 layout the offset of the ASCII, symbol, syllable and hanja blocks. `map`: "GLYPH U+XXXX"
lines for `rawcarve.py bdf --chars map` over the named blocks (`--blocks symbols,hangul,hanja`, the default; slots no
code point decodes to are left out).

**Synopsis.** `python3 -I tools/tbmfont.py info FILE`, `python3 -I tools/tbmfont.py map [--blocks B,...] -o MAP.txt`.
Exit 1 with a message for a file it refuses.

**Repository modules imported.** None. **Third-party.** None. **Test.** `tools/test_tbmfont.py` (synthetic 12, 16 and
20 px TBM files: the layout, the refusals, the slot map, the recipe's commands to a face, and
`doc_figures_windows.py --check`).

### `tools/doc_figures_windows.py`

**Purpose.** Draws the sample images of [recipes/windows.md](recipes/windows.md): one per face the recipe builds (the
Windows 3.1 TBM fonts BT16 and BT20, the Windows 95 TBM fonts GULIM16 and GULIM12, Gulim 16 and 12 px strikes of the
Windows 95 `gulim.ttc`, the Gulim 12 px and Batang 16 px strikes of the Windows XP fonts).

**Status.** Special-purpose (documentation).

**Inputs.** The font files as arguments (`--bt16`, `--bt20`, `--gulim16`, `--gulim12`, `--win95-gulim`, `--xp-gulim`,
`--xp-batang`); no path to a font is written in the script, and only the fonts given are drawn. Each face is built in
a temporary directory by the recipe's commands (`tbmfont.py`, `rawcarve.py bdf --invert`, `bdfface.py`, `mkfont.py`),
run with `python3 -I`.

**Outputs.** PNG files in `docs/images/recipes/windows/` (8-bit grey, black on white, every pixel doubled, no
metadata): four lines (two Korean pangrams, an English line, ASCII symbols and 16 KS X 1001 symbols) per face, and one
line per image with its size and any sample character the face lacks.

**Synopsis.**

    python3 -I tools/doc_figures_windows.py [--bt16 F] [--bt20 F] [--gulim16 F] [--gulim12 F] [--win95-gulim F] [--xp-gulim F] [--xp-batang F] [--out DIR] [--check]

`--check` renders in memory and compares with the files in `DIR` byte for byte (exit 1 on a difference or a missing
file). The TTC images depend on Pillow and its FreeType (printed); the images in the repository were made with Pillow
10.2.0 and FreeType 2.13.2.

**Repository modules imported.** `tbmfont.py`, `svfline.py`, `binscan.py` (and the tools it runs). **Third-party.**
Pillow (through `mkfont.py`). **Test.** `tools/test_tbmfont.py` (a synthetic BT16), `--check`.

### `tools/doc_figures_hbios.py`

**Purpose.** Draws the sample images of the "IBM PC DOS 한글 (HBIOS V3.0)" section of
[recipes/dos-fonts.md](recipes/dos-fonts.md#ibm-pc-dos-한글-hbios-v30): the gothic 16 px, myeongjo 16 px and myeongjo
24 px jamo sets of an IBM Korea HBIOS V3.0 disk, and the 2,350 precomposed syllables of the same 24 px file.

**Status.** Special-purpose (documentation). A sibling of `tools/doc_figures_windows.py`: the same four lines, drawing
and `--check` (its `draw` and `write_or_check`).

**Inputs.** `--disk DIR`, the folder with the disk's font files under their own names (`$KGOZN16.FNT`, `$KMYZN16.FNT`,
`$KMYZN24.FNT`, `$KSAHN16.FNT`, `$KROHN16.FNT`, `$KROHN24.FNT`, `$KSPHJ16.FNT`, `$KSPHJ24.FNT`); no path is written in
the script, and an image whose files are missing is skipped. Each face is built in a temporary directory by the
recipe's commands (`jamoset.py --layout 844` / `844-hbios24 --eng ... --symbols`, `rawcarve.py bdf`, `bdfface.py`, and
`tbmfont.py map` + `rawcarve.py bdf --chars map` + `mkfont.py --only-listed` for the symbols), run with `python3 -I`.
`HBIOS.EXE` and the drivers are never read.

**Outputs.** `hbios-gothic16.png`, `hbios-myeongjo16.png`, `hbios-myeongjo24.png`, `hbios-myeongjo24-precomposed.png`
in `docs/images/recipes/dos/` (8-bit grey, black on white, x2, no metadata), and one line per image.

**Synopsis.**

    python3 -I tools/doc_figures_hbios.py --disk DIR [--out DIR] [--check]

`--check` renders in memory and compares with the files in `--out` byte for byte (exit 1 on a difference or a missing
file).

**Repository modules imported.** `doc_figures_windows.py` (and through it `tbmfont.py`, `svfline.py`, `binscan.py`).
**Third-party.** Pillow (through `mkfont.py`). **Test.** `tools/test_tbmfont.py` (a synthetic HBIOS disk), `--check`.

## 8. Legacy format readers

### `tools/macfbit3.py`

**Purpose.** Read the HangulTalk 7.1.x jamo-plane bitmap fonts - Seoul12, AppleGothic12, AppleMyungjo12 and
the 24 px AppleGothic24 / AppleMyungjo24 - from the 7.1.2 Installer's 'splt' "JM" archives or from an installed
resource fork, compose their KS X 1001 syllables, and write sheets and a BDF that `bdfface.py` takes.

**Status.** Research reader. Reads resources supplied by the user.

**Inputs.** A JM archive (the data fork of `<Font>[splt]`), a resource fork, or a raw 'fbit' resource; for
composition, the InputBackSupport resource fork of the 7.1.2 CD (its 'HTBL' 1, uncompressed there) or a raw HTBL 1.
The formats are in the module docstring: JM = LHA -lh5- (ar002) stream at 0x1e with a byte-sum checksum; fbit type 3 =
482 h x h planes (2 banks x 241) from `0x4E + 6 * range_count` (0x54 for one range); HTBL 1 = one 4-byte entry [bank][g1][g2][g3] per code, the planes OR-ed.
There is no rule to recover: the table is the composition, and only the 2,350 KS syllables and 51 compatibility jamo
(A4A1..A4D3) exist.

**Outputs.** `unpack`: the unpacked resource fork. `fbit`: the 'fbit' resource. `info`: one line (type, cell, plane
count, composable codes). `sheets`: four greyscale PNGs, `PREFIX_glyphs_x1/_x4.png` (every plane, 32 a row) and
`PREFIX_ks2350_x1/_x4.png` (the 2,350 syllables composed, 94 / 47 a row). `bdf`: 2,401 glyphs, h x h cells,
`CHARSET_REGISTRY "ISO10646"`, Unicode `ENCODING`, `STARTCHAR KS<code>`.

**Synopsis.**

    python3 tools/macfbit3.py unpack SPLT.data OUT
    python3 tools/macfbit3.py fbit SRC OUT
    python3 tools/macfbit3.py info FONT [HTBLSRC]
    python3 tools/macfbit3.py sheets FONT HTBLSRC OUTPREFIX
    python3 tools/macfbit3.py bdf FONT HTBLSRC NAME OUT.bdf

**Repository modules imported.** None. **Third-party.** None.
**Test.** `tools/test_macfbit3.py` (synthetic data; `MACFBIT3_CD712=<extracted CD tree>` adds the checks on the CD
files).


### `tools/hwpfont.py`

**Purpose.** Read the bitmap fonts of Hangul (HWP) 1.x and 3.0 for DOS and headerless KS X 1001 syllable dumps: say
what a file is, compose an HWP 1.x face's syllables by HWP.EXE's rule, and write a file's glyphs as a Unicode BDF that
`mkfont.py` and `bdfface.py` take. `jamoset.py --layout hwp1` / `844-hwp3` and its HWP `--eng` read the files through it.

**Status.** Research reader. Reads bytes from user-supplied files (run with `python3 -I`). The HWP 1.x composition rules are defined by `L_CLS`, `V_CLS`, `T_CLS`, and `SEL`.

**Inputs.** HWP 1.x `.SFT` / `.PFT` (a 32-byte "HWP Font Editor v1.0" or "FE" header, the size exactly 32 + count x glyph
bytes; screen fonts row-major, printer fonts column-major): `HANGUL.SFT` (16x16, 1,193 glyphs, three faces of 10/4/4,
7/2/2, 6/2/2 initial/vowel/final sets of 31/29/31 pieces), `HANGUL1/2/3.PFT` (24x24, 980; 7/2/3, 7/2/2, 5/2/2),
`ASCII.SFT` / `ASCII.PFT` (8x16 / 14x24, 991: six faces of 147), `HANJA.SFT` (4,888), the symbol files (`other`). HWP 3.0
`.FNT` (a 72-byte "FNT" 01 header: type 0 English, 1 Hangul, 2 hanja; LE16 width and height at 6 and 8; row-major
glyphs): `HAN*.FNT` the 2,350 KS X 1001 syllables (+ a 360-glyph 8x4x4 set at 16 px), `ENG*.FNT` codes from 0x20,
`HAJ16_0.FNT` the hanja; the glyph count is the body's, and one that differs from the header's is reported by `info`
(HAN24 declares 2,710 and holds 2,350, ENG40 declares 147 and holds 96), an English FNT under the 95 codes 0x20-0x7E
refused. The glyph order follows the height, not the file name: 24-row HWP 1.x fonts are column-major. KS raw: a headerless file of exactly 2,350 square glyphs of 16, 24, 32, 40 or 48 px (75,200 /
169,200 / 300,800 / 470,000 / 676,800 bytes), its first and last glyph inked and different. Anything else is refused,
as is a file over 16 MiB. `--ascii` takes any English font `jamoset.py --eng` reads.

**Outputs.** `info`: one line (family `HWP 1.x font` / `HWP 3.0 FNT` / `KS X 1001 raw dump`, kind, glyph count and size,
the faces' set counts, an HWP 3.0 font's name, the 8x4x4 tail). `bdf`: a BDF 2.1 (`CHARSET_REGISTRY "ISO10646"`,
`PIXEL_SIZE` = the cell height, `ENCODING` = the code point, `STARTCHAR U+XXXX`): a Hangul file's syllables (the 2,350
of KS X 1001; `--syllables all` all 11,172 of an HWP 1.x face), an English file's U+0020..U+007E (advance = glyph width),
a hanja file's 4,888 hanja; with `--ascii` the English font's ASCII too (centred in height when shorter than the cell, its
own advance). The ascent is `--ascent`, else the English face's baseline (the row below the ink of `H`), else 7/8 of the
cell. A blank U+0020 (half the cell wide) is written when the file brings none: FreeType takes a BDF's first glyph as
`.notdef` and `mkfont.py` drops every glyph equal to it, which would drop U+AC00. One summary line (`wrote OUT: 2350 Hangul syllables, 95 ASCII of 14x24 from ASCII.PFT; cell 24x24, ascent 20`).

**Synopsis.**

    python3 -I tools/hwpfont.py info FILE
    python3 -I tools/hwpfont.py bdf FILE [--face N] [--syllables ks|all] [--ascii ENG [--ascii-face N]] [--ascent A] [--name NAME] -o OUT.bdf

`--face` is the Hangul face (0..2) of an HWP 1.x Hangul file or the face (0..5) of an HWP 1.x ASCII file. Exit 0, or 1
with `hwpfont.py: <reason>` (not one of the formats, a size that does not match the header, a face out of range, a
file with nothing to write).

As a library: `read(data)` (a `Font`: `family`, `kind`, `w`, `h`, `count`, `glyph(i)` as row ints, `jamo844`, `table`),
`Hwp1Hangul(font, face)` (`pieces(cp)`, `syllable(cp)`, and the rule as JSET set functions `lead_class`, `init_set`,
`med_set`, `fin_set`, `init_src`, `med_src`, `fin_src`), `syllables`, `ascii_glyphs`, `hanja_glyphs`, `english(path)`,
`ks_hangul()`, `ks_hanja()`, `ks_raw_px(size)`.

**Repository modules imported.** `rawcarve.py` (`bdf_text`), `jamoset.py` (`read_eng`, for `--ascii`). **Third-party.**
None. **Test.** `tools/test_hwpfont.py` (synthetic files; `JOHAB_FONTS=<research tree>` adds hash checks of the real
HWP 1.20, HWP 3.0 and Taebaek files).

### `tools/macsfnt.py`

**Purpose.** Make Mac-format TrueType usable by the other tools: list and extract the 'sfnt' resources of a resource fork
(.dfont, a suitcase's fork, AppleDouble `._` files, MacBinary), report a font's cmap subtables, and add a Unicode cmap
to a font that has only a Mac Korean (platform 1, script 3) or Windows Wansung (3, 5) one.

**Status.** General-purpose. Reads files supplied by the user.

**Inputs.** A resource fork as a plain file (or wrapped in AppleDouble / MacBinary); an sfnt font for `cmap` and `unicode`.

**Outputs.** `list`: one line a font resource (`TYPE<TAB>ID<TAB>NAME<TAB>BYTES`, types sfnt, NFNT, FONT, FOND, fbit).
`extract`: the 'sfnt' resource as a .ttf. `cmap`: `platform=P encoding=E format=F entries=N hangul=H` a subtable.
`unicode`: a copy of the font with a (3,1) format 4 subtable (and (3,10) format 12 when a code point is past U+FFFF)
built by decoding each two-byte code as EUC-KR (KS X 1001); refused when the font already has a Unicode subtable.

**Synopsis.**

    python3 tools/macsfnt.py list FILE
    python3 tools/macsfnt.py extract FILE OUT.ttf [--id N]
    python3 tools/macsfnt.py cmap FONT
    python3 tools/macsfnt.py unicode FONT OUT.ttf

Exit 0, or 1 with a message (not a resource fork, no 'sfnt' resource, no Korean cmap, a Unicode cmap already there).

**Repository modules imported.** None. **Third-party.** fontTools (`cmap`, `unicode`). **Test.** `tools/test_macsfnt.py`
(a synthetic font with a Mac Korean cmap and a resource fork built in the test; also checked against fontTools'
own resource reader).

## 9. Recipes: input format to SVF

For supported inputs, examples, and Maker conversion routes, see [recipes](recipes.md).
They cover TTF/OTF, TTC, variable fonts, Mac fonts, BDF/PCF/HBF, DOS raw fonts, and existing SVF faces.

<a id="remaining-gaps-of-the-tools"></a>

## 10. Tool limitations

- `mkfont.py` requires `--unicode` or `--chars-from` and always writes a metrics table,
  even when every glyph has the same advance.
- `jamoset.py` options apply according to the selected mode; see the modes table above.
- `jamoset.py --from-ttf --binarize mono` and the mask-font path need both freetype-py and uharfbuzz.
  Outline paths using `--binarize threshold|ridge` or `--bpp 2` without a mask use fontTools.
- Bitmap fonts opened by `mkfont.py` through FreeType use a built-in strike size.
  Use `svfscale.py` for smaller bitmaps. `maker/detect.py` provides strike detection through `bitmap_strikes`.
- `hwpfont.py` does not support HWP `.HFT`. See above for the accepted `.SFT`, `.PFT`, `.FNT`, and raw-dump conditions.
- `svfscale.py --bpp 2` downsamples a larger 1 bpp bitmap. It cannot recover intermediate coverage from a 1 bpp bitmap
  at the same size. `mkfont.py --bpp 2` also opens BDF/PCF, but does not recover edge information absent from the binary
  source. `jamoset.py --bpp 2` accepts only `--from-ttf`, so it cannot directly fit a 2 bpp jamo set to a bitmap source.
- `mkfont.py --probe` finds a cell for the ink at a given size; `--fit-cell` shrinks the size to fit a given cell.
  The caller must choose the target display's line spacing and cell size.
- There is no common library API. Individual functions such as `bdfface.build`, `jamoexc.build`, and
  `svf2ttf.build_ttf` do return results. Maker runs the tools as subprocesses through `maker/toolrun.py`.
  For input detection and coverage reports, see `maker/detect.py` and [Maker desktop](maker-desktop.md).

## 11. References

1. [Unicode Standard: Hangul syllables](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/#G3307)
2. [Unicode: CP949 mapping](https://www.unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WINDOWS/CP949.TXT)
3. [Pillow: ImageFont.truetype](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype)
4. [FreeType: Glyph Retrieval](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html)
5. [OpenType: EBDT](https://learn.microsoft.com/en-us/typography/opentype/spec/ebdt)
6. [OpenType: EBLC](https://learn.microsoft.com/en-us/typography/opentype/spec/eblc)
7. [OpenType: cmap](https://learn.microsoft.com/en-us/typography/opentype/spec/cmap)
8. [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/)
9. [MAME: graphics layout definitions](https://raw.githubusercontent.com/mamedev/mame/master/src/emu/drawgfx.h)
10. [MAME: SPC-1500 driver](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/samsung/spc1500.cpp)
11. [Adobe: Glyph Bitmap Distribution Format (BDF) 2.2](https://adobe-type-tools.github.io/font-tech-notes/pdfs/5005.BDF_Spec.pdf)
12. [iolo: 8x4x4 fonts](https://github.com/iolo/8x4x4-fonts)
