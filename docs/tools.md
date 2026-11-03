# Tools

This is the reference for the programs in this repository that read fonts, write SVF (SVFN) faces, and check them.
It is what the SVF maker's design is planned from, so every option and behaviour below comes from the tool's code or
from running it; none is inferred from a name. The format itself is `spec/SVF.md`; the C renderer is
`spec/renderer-design.md` and `c/include/svf.h`.

How each face of `svf/` is made, and how-tos for other kinds of Korean fonts: [recipes.md](recipes.md).

The tools are written for the command line. One tool can be a library for another: `jamoset.py` is imported by
`bdfface.py`, `jamoaa.py`, `jamoadapt.py`, `svfdy.py`, `svfline.py`, `svf_synth.py`, `jamovec.py` and
`web/mkindex.py`, and the fitting modules (`jamofit.py`, `jamoaa.py`, `jamoadapt.py`, `jamoseg.py`) have no command
line of their own.

## The SVFN kinds the tools produce

An **SVFN** file (magic `SVFN`, little-endian) is a bitmap font with a header, a code point table, optional
per-glyph metrics, and glyph records. Every writer here writes **version 3** through `jamoset.pack_svfn` (spec:
`docs/superpowers/specs/2026-10-21-svf-v3-design.md`, `spec/SVF.md`); version 2 (fixed cells) is converted by `svf2to3.py` (`jamoset.parse_svfn` refuses a v2 face with the convert message), and version 1 (code page order) is gone. **Every writer takes `--profile NAME`
(default `default`; a profile name from the table under `svf2to3.py`, or `REC,ROW,TAB,OFF` units) and `--box x|y|full`
(the ink box policy of the glyph records; default: the profile's).** Header bytes 17 and 18 hold the font-wide **dy** range and metrics byte 3 holds each glyph's dy (a
glyph is drawn dy rows below its cell position); only a font with a metrics table can carry one.

The tools write two kinds:

- A **precomposed face** holds one stored glyph per code point (a Hangul syllable, an ASCII letter, a symbol). It is
  written at **1, 2 or 8 bpp** (1 bpp is a stencil, 2 bpp holds four coverage levels, 8 bpp holds 256). There is no
  4 bpp. A face may have
  a metrics table (header flag bit 0) with per-glyph advance, left bearing and ink width, making it variable width.
  Faces written by `mkfont.py` from a code point list also set flag bit 2 (combining marks stored with the pen at
  `max(0, -bearingX)`).
- A **jamo set** (header flag bit 1) holds no syllables: it holds positional jamo **pieces** as glyphs at
  `U+F0000 + piece number`, plus a **JSET** block (right after the code point table) that says, per syllable, which
  pieces to compose (the OR, or per-pixel maximum, of two or three). It holds all 11,172 Hangul syllables from about
  11 KB (16 px, 1 bpp, pieces only) upward: the 66 jamo sets in `svf/` run from 10,684 bytes (`svf/dos/NEODG16G.SVF`)
  to 162,124 (`svf/dos/NSQRB36A.SVF`), larger with 2 bpp, bigger cells or kept glyphs. The pieces are written at 1 bpp
  or 2 bpp; a set has a metrics table (flag bit 0). Compatibility jamo U+3131..U+3163 are drawn by a piece when
  the block names one. A jamo set is still a valid plain face to an older reader.

Both kinds may carry a **dy** range; a jamo set composes its syllables at dy 0 (a piece may not carry a dy).

A **layout** is a jamo set's set system: the lead and tail classes, the initial/medial/final set tables, and the piece
tables. The named layouts are `844` (the DOS 8x4x4 standard), `844-ihnm`, `844-hbios24`, `1044-san`, `621`, `hanterm-johab`,
`dkb-printer-7x2x2`, `dkb-printer-12x4x4`, `kyra-lok`, `mac-fbit-45sets` and `adaptive[:NI,NM,NF]`.

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
- `tools/build/build_faces.py` rebuilds the faces of `svf/` from their upstream fonts (`tools/build/faces.tsv`, `docs/recipes.md`).
- The `web/` tools index and copy the faces that the WASM picker serves.

## Core builders

### `tools/jamoset.py`

**Purpose.** Build a jamo-set SVF (flag bit 1 plus a JSET block) from a DOS-era source font, or fit the pieces to an
outline font or an existing precomposed face. It also writes SVFN v3 (`write_svfn`, `pack_svfn`, `--profile`, `--box`) and reads v3 (a v2 face is refused with the convert message, `tools/svf2to3.py`), packs and unpacks JSET blocks, and
composes syllables for checking.

**Status.** General-purpose. It names game-specific set systems (SAGA IHNM, hanterm, Dokkaebi printer, Kyra LoK, Mac
HangulTalk) but is not tied to one game.

**Inputs.** Depends on the mode:
- a DOS Johab raw font read by its own parser: raw 8x4x4 (`844`, 16/24/40/48 px, 11520/11522/25920/72000/103680/15584
  bytes), 10x4x4 (`1044-san`, 12800 bytes), 6x2x1 (`621`, 6144 bytes, byte-column order), HBIOS/Taebaek 24x30
  (`844-hbios24`, 243900 bytes), SAGA IHNM (`844-ihnm`), Kyra `MK15.BIT` (11550 bytes), Dokkaebi printer
  `HANGUL16/24.FNT` (15360/34560, column-major) and `HANGUL40/48.FNT` (176000/253440);
- a hanterm BDF (`hanterm-johab`) whose `ENCODING` is the johab-1 glyph number, parsed with a regular-expression
  reader;
- a Mac HangulTalk 1.0 `fbit` resource fork (`mac-fbit-45sets`), parsed from its raw resource map;
- `--eng` a raw 8x16 DOS English font (2048 or 4096 bytes), or an HBIOS 12x24 (15360) / PFT 12x24 (12288);
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
DOS Johab, hanterm BDF, Kyra `.BIT` or Dokkaebi FNT file), `mac-fbit-45sets` (a positional Mac HangulTalk `fbit`
resource fork, a mode of its own: it takes no `--from-*`, `--eng` or `--base`), `--from-ttf`, `--from-svf`, `--bpp 2`
(only with `--from-ttf`) and `--blank-compat`. An option not listed for a mode is ignored there (not refused), except
where the table says "refused".

| Option (default) | Modes | Meaning |
|---|---|---|
| `--layout` (required) | all | a set system: `1044-san`, `621`, `844`, `844-hbios24`, `844-ihnm`, `dkb-printer-12x4x4`, `dkb-printer-7x2x2`, `hanterm-johab`, `kyra-lok`, `mac-fbit-45sets`, `adaptive[:NI,NM,NF]`. `adaptive` needs `--from-ttf` or `--from-svf`; `mac-fbit-45sets` is a mode of its own (the positional file is the `fbit` resource fork) |
| `--face N` (0) | `source` | typeface of a printer font (0 or 1) |
| `--eng FILE` (none) | `source`, `--from-ttf`, `--from-svf` | raw 8x16 English font for ASCII (2048 or 4096 bytes); refused with `--bpp 2` and with `mac-fbit-45sets` |
| `--base FILE` (none) | `source`, `--from-ttf` | SVFN v3 whose non-syllable glyphs are kept (same cell, 1 bpp); ignored by `--from-svf` (the input face is the base); refused with `--bpp 2` and with `mac-fbit-45sets` |
| `-o`, `--output` (required) | all | output path |
| `--profile NAME` (`default`), `--box x\|y\|full` (the profile's) | all | the SVFN v3 layout profile and ink box policy of the output (see `svf2to3.py`) |
| `--jset-version 1\|2\|auto` (1; `--blank-compat`: the input's) | all | the JSET block version written (see "JSET versions" below) |
| `--jset-big` (off) | all | allow a JSET over the standard limits (19 x 28 classes, 128/128/64 sets; the reader needs `SVF_JSET_BIG`); output within the standard limits is identical with or without it (see "JSET versions") |
| `--advance N` (none) | `source`, `mac-fbit-45sets`, `--from-ttf`, `--from-svf`, `--bpp 2` | the composed syllable's step (JSET advance byte; the layout's value, 0 = cell width) |
| `--ascent N` (none) | `source`, `mac-fbit-45sets` | the SVF's baseline row (the `--eng` face's baseline for a 12x24 face, else 7/8 of the cell); ignored by the fit modes, which take it from the fitted face |
| `--embolden` (off) | `source`, `mac-fbit-45sets` | OR every piece and ASCII glyph with itself shifted right 1 px; ignored by the fit modes, refused with `--bpp 2` |
| `--symbols` (off) | `source`, `mac-fbit-45sets`, `--bpp 2` | add U+2026 and U+25A1; ignored by 1 bpp `--from-ttf`/`--from-svf` |
| `--check` (off) | `source`, `mac-fbit-45sets`, `--from-ttf`, `--from-svf`, `--bpp 2` | compose all 11,172 syllables from the output and verify |
| `--from-ttf FONT` (none) | mode | fit the pieces to the outline font's syllables at `--size` |
| `--from-svf FACE.SVF` (none) | mode | decompose a 1 bpp precomposed SVFN face (refused at any other bpp) |
| `--size N` (none) | `--from-ttf` | pixel size |
| `--cell WxH` (none) | `--from-ttf` | cell (default `SIZExSIZE`) |
| `--baseline N` (none) | `--from-ttf` | baseline row (default ink box centred) |
| `--present-only` / `--no-present-only` (on) | `--from-ttf` 1 bpp `mono` | fit only syllables the font draws, or also `.notdef`; `--binarize threshold\|ridge` fits the drawn syllables only and refuses `--no-present-only`; refused with `--bpp 2` |
| `--blank-compat FACE.SVF` (none) | mode | rewrite a jamo set leaving compat jamo that have a whole glyph to that glyph |
| `--mask-font FONT\|none` (alias `--mask`) | `--from-ttf`, `--from-svf` 1 bpp | mask font with OpenType `ljmo`/`vjmo`/`tjmo`; default `$JAMOSET_MASK_FONT` or the shipped NotoSansKR when freetype/uharfbuzz import, else free pieces |
| `--mask-radius N` (none) | `--from-ttf`, `--from-svf` 1 bpp | mask dilation (1 up to 16 px, 2 up to 24, else 3) |
| `--passes N` (12) | `--from-ttf`, `--from-svf`, `--bpp 2` | most coordinate-descent passes |
| `--pylib DIR` (none) | `--from-ttf`, `--from-svf`, `--bpp 2` | directory holding freetype and uharfbuzz (also `$JAMOSET_PYLIB`) |
| `--report FILE.json` (none) | `mac-fbit-45sets`, `--from-ttf`, `--from-svf`, `--bpp 2` | write the quality report |
| `--bpp {1,2}` (1) | `--from-ttf` | 2 = anti-aliased pieces (needs fontTools) |
| `--aa-refine N` (2) | `--from-ttf --bpp 2` | level-error refinement passes (0 = median only) |
| `--binarize {mono,threshold,ridge}` (mono) | `--from-ttf` 1 bpp | FreeType monochrome, exact-area coverage, or that plus faint ridges (fontTools) |
| `--threshold F` (0.5) | `--from-ttf --binarize threshold\|ridge` | coverage cut |
| `--clean` / `--no-clean` (off) | `--from-ttf`, `--from-svf`, `--bpp 2` | noise cleanup (on for `--bpp 2` and `--layout adaptive`, else off) |

**JSET versions.** Version 1 is the standard and the default of every writer; version 2 (compact) is for builds and
packs aimed at memory-constrained targets (`spec/SVF.md`, "When to use version 2"). `--jset-version` takes `1`, `2` or
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

**JMAP (JSET version 3).** As a library `jamoset.py` also reads and writes the mapping-table block of `spec/SVF.md`
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

**Repository modules imported.** `johab844.py` (for the 844 identity check), `jamoaa.py`, `jamofit.py`,
`jamoadapt.py`. **Third-party.** fontTools (for `--bpp 2`, `--binarize threshold|ridge`, and the `--clean` contour
donors), freetype-py and uharfbuzz (for the mask font and for `--from-ttf` at 1 bpp `mono`). Both are optional:
without them, `--from-ttf` fails unless `--binarize threshold|ridge` or `--bpp 2` is given, and the mask font is
skipped with a message.

**Test.** `tools/test_jamoset.py`.

### `tools/mkfont.py`

**Purpose.** Bake a TTF or OTF into a precomposed SVFN v3 face with Pillow's FreeType rasteriser, from an explicit
code point list (`--unicode` or `--chars-from`; without one it exits 2 with `mkfont: version 1 (code page order) is gone:
pass --unicode SET`). A bitmap BDF or PCF also opens
through FreeType, but only at the pixel size built into the file.

**Status.** General-purpose.

**Inputs.** A TTF, OTF, BDF or PCF read with Pillow's FreeType (`PIL.ImageFont.truetype`). A bitmap BDF or PCF opens
only at the pixel size built into the file (its strike); any other size is `OSError: invalid pixel size`. `fontTools`
is used only to ask whether the font's cmap has a code point (`cmap_has`), for `--fallback-ttf` and for deciding which
`--unicode` code points to drop; `cmap_has` assumes an sfnt and raises
`fontTools.ttLib.TTLibError: Not a TrueType or OpenType font (bad sfntVersion)` on a BDF or PCF when fontTools is
installed (bug; see the BDF and PCF recipes). `--chars-from` reads files written by the games (see below).

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
| `--unicode SPEC` | "" | the code point list (this or `--chars-from` is required): hex ranges, a named set (`ascii`, `latin1`, `hangul`, `jamo`, `cjk-punct`, `kana`, `thai`, `ksx1001`, `ksx1001-nohanja`, `ksx1001-hangul`, `ksx1001-symbols`, `cp949`, `cp949-hangul`) or `file:PATH` |
| `--chars-from FILE...` | none | union of the code points those files use |
| `--limit SPEC` | "" | intersect the result with this code point set |
| `--only-listed` | off | do not always keep ASCII and U+25A1 |
| `--fallback-ttf FILE` | "" | draw code points the main font lacks from this TTF |
| `--fail-on-drop` | off | fail if `--limit` dropped a `--chars-from` character |
| `--require` | off | fail if a requested code point is missing from the font |
| `--profile NAME` | `default` | the SVFN v3 layout profile (name or `REC,ROW,TAB,OFF` units) |
| `--box x\|y\|full` | the profile's | ink box policy of the glyph records |

`--chars-from` reads four kinds by file name: `TEXT.nnn`/`text.nnn` (SCI TEXT patch: a 2-byte header then NUL-separated
UTF-8 strings), `*.str`/`sci-ko.str` (`script<TAB>id[<TAB>room]<TAB>text`, UTF-8), `*.map` (a hires_text INI's `missing=`
and `[glyphs]` absolute codes), `*.trs` (a SCUMM `SCVMTRS` bundle: UTF-8 if the body starts with a BOM, else CP949),
and otherwise plain UTF-8 text.

**Repository modules imported.** None (standalone); `bdfface.py` imports it. **Third-party.** Pillow (required);
fontTools (optional).

**Test.** `tools/test_mkfont.py`.

### `tools/bdfface.py`

**Purpose.** Bake a precomposed 1 bpp SVF from a precomposed Hangul bitmap font (a BDF) and an ASCII bitmap font (a BDF
or an HBF). It was written for the MI1/MI2 "L" faces but is not game-specific.

**Status.** General-purpose.

**Inputs.** Its own regular-expression BDF reader (KS X 1001 `ENCODING` or Unicode) and HBF reader (single-byte code
ranges with the bitmap files beside them, optionally gzipped). A Hangul BDF and an ASCII BDF/HBF. It keeps only the
Hangul syllables `--chars-from` names (so it needs a text file listing them), ASCII 0x20-0x7E from `--ascii`, and its
own U+2026/U+25A1; it takes no symbols or jamo from either bitmap face. The cell defaults to 24x24 whatever the BDF's
own box is.

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
| `--mask-font FILE` | `$JAMOSET_MASK_FONT` / shipped NotoSansKR | `--fill-absent` mask font (`none` = free pieces) |
| `--pylib DIR` | `$JAMOSET_PYLIB` | directory holding freetype and uharfbuzz |
| `--profile NAME`, `--box x\|y\|full` | `default`, the profile's | the SVFN v3 layout profile and ink box policy |
| `-o`, `--output` (required) | - | output path |

**Repository modules imported.** `jamoset.py` (and `mkfont.py`, for `collect_chars_from_files`). **Third-party.** None
(the BDF/HBF readers are its own; `--fill-absent` with a mask font uses freetype/uharfbuzz through `jamoset.py`).

**Test.** `tools/test_bdfface.py`.

### `tools/johab844.py`

**Purpose.** Put the Hangul of a raw 8x4x4 Johab bitmap font into an existing 16x16 1 bpp SVFN base, redrawing every
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

**Repository modules imported.** None. **Third-party.** None. **Test.** `tools/test_jamoset.py`.

### `tools/macfbit_svf.py`

**Purpose.** Convert a Mac HangulTalk 7.1.x type-3 'fbit' jamo-plane font (Seoul12, AppleGothic12/24, AppleMyungjo12/24)
into an SVF v3 jamo-set face, with every KS X 1001 syllable exactly as the Mac draws it.

**Status.** Special-purpose (one font family). The Apple fonts are proprietary: the tool reads the user's own decoded
copies; no Apple byte is in this repository.

**Inputs.** The 'fbit' resource (482 glyph slots, 2 banks x 241) and InputBackSupport 'HTBL' 1 (4 bytes per KS code:
bank and three glyph bytes; the format is described in `tools/macfbit3.py` and `docs/recipes.md`). `--latin` reads
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

**Real-face golden.** `tools/test_macfbit_svf.py` class `RealFaces` runs the five faces when `SVF_MAC71_INPUTS` names a
directory holding `Seoul12`, `AppleGothic12`, `AppleGothic24`, `AppleMyungjo12`, `AppleMyungjo24` as `<Name>.fbit` (the
decoded 'fbit' resource) and `<Name>.htbl1` (InputBackSupport 'HTBL' 1, the same file for every face). Fill it from your own decoded resources (outside git; no Apple data is in this repository): the 'fbit' resource of
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

### `tools/svf2to3.py`

**Purpose.** Convert SVFN v2 faces to v3, and re-layout v3 faces into another profile, with a proof that no pixel,
metric or composed syllable changed.

**Status.** General-purpose. Every other writer writes v3 only; `jamoset.parse_svfn` reads v3 only (a v2 face is refused with the convert message, which names this tool); `svf2to3.py` holds the only v2 parser.

**Inputs.** An SVFN v2 or v3 face, or with `--tree` a folder searched recursively for `*.SVF` (any case).

**Outputs.** A v3 face written by `jamoset.pack_svfn`; with `--tree` the same relative paths below DST (SRC may equal
DST; other files are not copied). Each face is written to a temporary file beside its target, checked there when
`--check` is given, and renamed over the target only if the check passed.

**JSET version.** `--jset-version` defaults to 1 (v2 is for memory-constrained targets only): a v1 block stays v1 and a v2 block is written as v1; `2` writes v2, `auto` writes v2 when it is at least 1024 B smaller; `--jset-big` lets a re-encoded or verbatim-copied block (a v2 block, or the fallback of a JMAP region) exceed the standard limits. `--check` reports a face whose jamo set the parser refused as `composed=unchecked`. A JMAP region (JSET version 3) is copied verbatim (the output's region bytes equal the input's, piece numbers and all); `--jset-version` applies to nothing there and a note on stderr says so; `--check` composes both faces through `svfline.py` (a JMAP-only miss is not composed: the cmap glyph or none, as for a plain face) and the output line reads `jset=3 jmap=BYTES` (` list=1` more for a LIST region, flag 0x08, which is copied the same way and never re-encoded). The same reading applies in `svfline.py`, `maker/detect.py` (kind `svf-jamo`, `jset_version` 3, `jmap_mode` `dense` / `sparse` / `list`, usable only when plane pieces, fallback pieces and compat all have glyphs; `maker/quality.py` `face_facts` reports `pool` for a LIST: the number of distinct pieces the LIST block itself names, its entries and its own compat entries, not the fallback's) and `web/mkindex.py` (`jamo` true for such a face).

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
fallback, `dhybrid1` / `dhybrid2` (dense, 3 / 4 byte entries, over a version 1 / 2 fallback: a 34 / 45 KB region), `adv0`, `adv0fb` (advance 0 in the JMAP and in its version 1 fallback), `sparse_full` (the SPARSE flag with all 11,172 entries, assembled by hand because `pack_jmap` writes that count dense), `blanks`, `pi2047`); `--jmap-bad KIND` breaks one JMAP rule (the 23 `JMAP_BAD_KINDS`, the module
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
optionally which slots share a piece) and take every piece from the reference's syllables. Written for the Arduino Uno
12 px faces (card t_304228de: SAM8J's 8x4x4 skeleton, MR1286J's 6x2x1, with Galmuri9 as the reference), within a byte
budget.

**Status.** Research builder; its outputs are local (the reference strikes are not in the repository).

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
`JAMOFILL_OWN` (0: `--pixel` may take any pixel), `JAMOFILL_MEDIAL_PENALTY` and `JAMOFILL_LEAK_PENALTY`.

**Repository modules imported.** `jamoset.py`. **Third-party.** Pillow (`sheet` only). **Test.**
`tools/test_jamofill.py` (a synthetic strike of context-free jamo: split, exact 1/1/1 and 8x4x4 fills, compaction,
set merges, budget ties, stroke widths, ticks, the ㅊ/ㅎ cap, stroke completeness and the ㄲ repair, leak masks,
the medial gate, the command line).

### `tools/jamomerge.py`

**Purpose.** Make a many-variant jamo-set face smaller by merging its variants, keeping every piece as drawn. Written
for many-variant faces (for example 13 initial sets by vowel class and final, many medial runs) that must fit an
Arduino Uno budget (8,192 B, JSET version 1, ASCII included).

**Status.** Research builder; it ships no face of its own.

**Inputs.** `--face` a jamo-set SVF (any JSET version `jamoset.py` reads). `--ref` the reference face (default: the face
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
log-loss over the changed syllables; `recog.py` of the research repository, found through `SVF_RECOG_DIR`, inference only) and the best per byte is applied. Hard
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

**Repository modules imported.** `jamoset.py`, `jamofill.py`. **Third-party.** None (numpy and torch with `--recog`).
**Test.** `tools/test_jamomerge.py` (synthetic faces: build / read round trip and size, normalisation, every move
composing as it promises, a greedy step, the leak, stroke and tick gates).

### `tools/jamoexc.py`

**Purpose.** Write a LIST exception face: a jamo-set face plus whole glyphs and piece recombinations for chosen
syllables and compat jamo, as a JMAP block in list mode (spec/SVF.md, JMAP LIST). The face's own JSET bytes stay as the
fallback, so every syllable not listed draws as before.

**Synopsis.** `python3 tools/jamoexc.py build FACE.SVF EXC.json OUT.SVF [--jset-version 1|2] [--profile P] [--box B]`.

**EXC format.** A JSON object keyed by a syllable or a compat jamo, as the character (`"가"`, `"ㄱ"`) or `"U+AC00"`; a key
named twice is refused. A value is `{"whole": "HEX"}` (`cell_h` rows of `ceil(cell_w * bpp / 8)` bytes as hex; hex rows
only, no PNG input) or `{"pieces": [n, n, n]}` (piece numbers of the face: 1 to 3 for a syllable, exactly one for a
compat key). A `whole` cell becomes a new piece glyph numbered above the highest U+F0000 + n code point of the face
(syllables ascending, then compat jamo ascending); a number 0xFFFF (BLANK) is never given out. Any other key in a value
(`dy`, `advance`, ...) is refused: a piece carries no dy or metrics.

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
piece gets the metrics of the face's first piece glyph and dy 0. Nothing is read from or written to the board or the
repository; the output path is the only file written, and only on success, written through a temp file and renamed.

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

## Fitting and separation modules (no command line)

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

## Inspection and checking

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

**Inputs.** SVFN faces, read with its own `struct` header reader.

**Outputs.** A text report (no file).

**Synopsis.** `python3 tools/fontmetrics.py FACE [FACE ...]` (no options).

**Repository modules imported.** None. **Third-party.** None. **Test.** None.

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

## Build scripts

### `tools/build/build_faces.py`

**Purpose.** Rebuild the faces of `svf/` from their upstream fonts with the repository's own tools, as the recipe table
`tools/build/faces.tsv` says, and compare each result with the face in `svf/`.

**Status.** General-purpose (the provenance check of the shipped faces; `docs/recipes.md` explains every recipe).

**Inputs.** `tools/build/faces.tsv` (face, method, source, args, codepoints, expect, note; one row for every face of
`svf/`), the code point lists under `tools/build/cps/`, and the source fonts in `ttf/`. A row whose source is
`ext:NAME` names a font that is not in this repository; `--ext NAME=PATH` supplies it, else the row is reported
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
args, codepoints, expect, note). `method` is `mkfont`, `jamoset` or `none` (no recipe with this repository's tools;
the note says why). `codepoints` names a `mkfont.py --unicode` set or a file under `tools/build/cps/` (one hex code point
or range a line, the face's own code point list). `docs/recipes.md` explains every row; `tools/test_build_faces.py`
keeps the table complete.

## Web (WASM picker)

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

## Legacy format readers

### `tools/macfbit3.py`

**Purpose.** Read the HangulTalk 7.1.x (1992) jamo-plane bitmap fonts - Seoul12, AppleGothic12, AppleMyungjo12 and
the 24 px AppleGothic24 / AppleMyungjo24 - from the 7.1.2 Installer's 'splt' "JM" archives or from an installed
resource fork, compose their KS X 1001 syllables, and write sheets and a BDF that `bdfface.py` takes.

**Status.** Research reader. The fonts are Apple/Elex proprietary: the tool reads the user's own copies and no face or
bitmap from them is in this repository.

**Inputs.** A JM archive (the data fork of `<Font>[splt]`), a resource fork, or a raw 'fbit' resource; for
composition, the InputBackSupport resource fork of the 7.1.2 CD (its 'HTBL' 1, uncompressed there) or a raw HTBL 1.
The formats are in the module docstring: JM = LHA -lh5- (ar002) stream at 0x1e with a byte-sum checksum; fbit type 3 =
482 h x h planes (2 banks x 241) from 0x54; HTBL 1 = one 4-byte entry [bank][g1][g2][g3] per code, the planes OR-ed.
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

Run on the user's 7.1.2 CD (2026-10-26): Seoul12 (1,843 B), AppleGothic12 (2,707 B), AppleMyungjo12 (3,194 B) unpack to 9,673
/ 9,673 / 9,617 B forks with an 8,760 B fbit each (482 planes, 12 px); Seoul12's equals the uncompressed
`Seoul12[fbit]` of the CD byte for byte. The BDFs go through `bdfface.py --cell 12x12 --chars-from <2,350 KS
syllables>` to 2,350 syllables, 0 absent, 0 clipped.

**Repository modules imported.** None. **Third-party.** None.
**Test.** `tools/test_macfbit3.py` (synthetic data; `MACFBIT3_CD712=<extracted CD tree>` adds the checks on the CD
files).


### `tools/macsfnt.py`

**Purpose.** Make Mac-format TrueType usable by the other tools: list and extract the 'sfnt' resources of a resource fork
(.dfont, a suitcase's fork, AppleDouble `._` files, MacBinary), report a font's cmap subtables, and add a Unicode cmap
to a font that has only a Mac Korean (platform 1, script 3) or Windows Wansung (3, 5) one.

**Status.** General-purpose. Reads the user's own files; no Mac font is in this repository.

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

## Recipes: input format to SVF

Each recipe below was run for real, writing to `/tmp`, except FNT and HBF: no input for those exists in this
repository or on this host, so their recipes were **not run** and are marked so. The output size, the glyph count (the
code point table's entry count) and the render check are given. TTF and SVF run on a repository font; OTF, BDF and PCF
have none in the repository, so those three use a font elsewhere on this host and say so. The render check uses
`tools/svfline.py` on the sample `안녕하세요 ABC 123` (Hangul and ASCII):

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > out.gray

`measure` prints `width=W ascent=A descent=D`; `line` writes a 200x24 GRAY8 buffer, and the count of non-zero bytes is
the ink drawn. The faces are at 16 px in a 16x16 cell unless stated.

### TTF

Source: `ttf/nanumgothic/NanumGothic-Bold.ttf`.

Precomposed, 1 bpp:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf /tmp/svf-tools-doc/ng16-1bpp.svf \
        --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

`107660 bytes`, `2446` glyphs (2350 Hangul syllables). Renders: `width=146 ascent=14 descent=2`, 677 inked pixels.

Precomposed, anti-aliased (2 bpp):

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf /tmp/svf-tools-doc/ng16-2bpp.svf \
        --size 16 --bpp 2 --unicode ascii,ksx1001-hangul

`185932 bytes`, `2446` glyphs. Renders: `width=146 ascent=14 descent=2`, 847 inked pixels.

Jamo set, 1 bpp:

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf \
        --size 16 --binarize threshold -o /tmp/svf-tools-doc/ng16-jamo-1bpp.svf

`20453 bytes`, `439` cmap glyphs, `344` pieces; fit: 11172 syllables, IoU 0.817. Renders:
`width=151 ascent=13 descent=3`, 672 inked pixels.

Jamo set, anti-aliased (2 bpp):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf \
        --size 16 --bpp 2 -o /tmp/svf-tools-doc/ng16-jamo-2bpp.svf

`34501 bytes`, `439` cmap glyphs, `344` pieces. Renders: `width=146 ascent=13 descent=3`, 879 inked pixels.

### OTF

The repository has no OTF. The runs below used Noto Sans KR Regular (SIL OFL 1.1, from the Noto CJK project) as
`/tmp/svf-tools-doc/NotoSansKR-Regular.otf`, a subset cut to KS X 1001 (ASCII, Latin-1, punctuation, the 2,350
syllables, jamo, symbols and Hanja); a full Noto Sans KR gives the same commands with other counts.

Precomposed, 1 bpp:

    python3 tools/mkfont.py /tmp/svf-tools-doc/NotoSansKR-Regular.otf /tmp/svf-tools-doc/noto16-1bpp.svf \
        --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

`107660 bytes`, `2446` glyphs (2350 Hangul syllables; the subset carries exactly the KS X 1001 ones). Renders:
`width=141 ascent=10 descent=6`, 464 inked pixels.

Precomposed, anti-aliased (2 bpp): the same command with `--bpp 2` gives `185932 bytes`, `2446` glyphs; renders
`width=141 ascent=10 descent=6`, 700 inked pixels.

Jamo set, 1 bpp:

    python3 tools/jamoset.py --layout 844 --from-ttf /tmp/svf-tools-doc/NotoSansKR-Regular.otf \
        --size 16 --binarize threshold -o /tmp/svf-tools-doc/noto16-jamo-1bpp.svf

`20453 bytes`, `439` cmap glyphs, `344` pieces; fit: 2350 syllables, IoU 0.818. Renders:
`width=146 ascent=14 descent=2`, 462 inked pixels.

Jamo set, anti-aliased (2 bpp): `--bpp 2` gives `34501 bytes`, `439` cmap glyphs, `344` pieces; renders
`width=141 ascent=14 descent=2`, 704 inked pixels.

### BDF

**Not supported in this repository: no `.bdf` is here** (`ttf/`, `svf/` and `tools/testdata/` hold none), so no BDF
recipe can be run on a repository font; the readers are exercised with synthetic BDFs by `tools/test_bdfface.py` and
`tools/test_jamoset.py`. The only Unicode BDF on this host is `/usr/share/dosbox-x/wqy_12pt.bdf` (WenQuanYi Bitmap
Song); it is **not in the repo**, so the runs below are external.

`tools/bdfface.py` reads a Hangul BDF plus an ASCII BDF/HBF. The external BDF can serve as both halves; `--chars-from`
needs a text file naming the syllables, which the repo's own `ksx1001-hangul` set supplies:

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open('/tmp/svf-tools-doc/ks.txt', 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))"
    python3 tools/bdfface.py --hangul /usr/share/dosbox-x/wqy_12pt.bdf --ascii /usr/share/dosbox-x/wqy_12pt.bdf \
        --cell 16x16 --chars-from /tmp/svf-tools-doc/ks.txt -o /tmp/svf-tools-doc/wqy.svf

`107704 bytes`, `2350` syllables (`2447` glyphs: the syllables, ASCII 0x20-0x7E and bdfface's own U+2026/U+25A1),
7 glyphs clipped. Renders `width=156 ascent=14 descent=2`, 348 inked pixels. Its output feeds `jamoset.py`:

    python3 tools/jamoset.py --layout 844 --from-svf /tmp/svf-tools-doc/wqy.svf -o /tmp/svf-tools-doc/wqy-jamo.svf

`20541 bytes`, `441` cmap glyphs, `344` pieces; fit: 2350 syllables, IoU 1.000. Renders `width=156 ascent=14
descent=2`, 348 inked pixels. bdfface keeps only the Hangul syllables `--chars-from` names, ASCII 0x20-0x7E from
`--ascii`, and its own U+2026/U+25A1: no symbols or jamo come from the BDF, and the cell defaults to 24x24 whatever
the BDF's own box is. `tools/jamoset.py --layout hanterm-johab` reads a hanterm johab-1 BDF directly (no such file
here).

`mkfont.py` also reads a BDF, through Pillow's FreeType, at the BDF's built-in pixel size only (16 px for this file)
and only once `cmap_has` is fixed (see PCF); verified with fontTools hidden:

    PYTHONPATH=/tmp/svf-tools-doc/nofonttools python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf \
        /tmp/svf-tools-doc/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

`107660 bytes`, `2446` glyphs; renders `width=156 ascent=12 descent=4`, 348 inked pixels. Anti-aliased: a bitmap
BDF carries no coverage, so `--bpp 2` gives `185932 bytes` whose only levels are 0 and 3 — the same monochrome
pixels at 2 bpp, not a smooth face.

### PCF

**Not supported in this repository: no PCF is here**, so the run below uses
`/usr/share/fonts/X11/misc/18x18ko.pcf.gz` (Misc Fixed Wide, **not in the repo**).

`mkfont.py` reads PCF through Pillow's FreeType, at the font's built-in pixel size only: 18 px for this file. Any
other size fails:

    python3 -c "from PIL import ImageFont; ImageFont.truetype('/usr/share/fonts/X11/misc/18x18ko.pcf.gz', 16)"
    OSError: invalid pixel size

With `--unicode`, `cmap_has` calls `fontTools.TTFont()` on the file and catches only `ImportError`, so with fontTools
installed the path does not work as checked out:

    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz /tmp/svf-tools-doc/pcf18-1bpp.svf \
        --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    fontTools.ttLib.TTLibError: Not a TrueType or OpenType font (bad sfntVersion)

Once `cmap_has` returns None on `TTLibError` (the SVF maker plan's one-line fix; this repository does not fix it) the
same command works. It was verified with fontTools hidden, by putting a module that raises `ImportError` on
`PYTHONPATH`:

    mkdir -p /tmp/svf-tools-doc/nofonttools
    printf 'raise ImportError("fontTools hidden for this run")\n' > /tmp/svf-tools-doc/nofonttools/fontTools.py
    PYTHONPATH=/tmp/svf-tools-doc/nofonttools python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz \
        /tmp/svf-tools-doc/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul

`161472 bytes`, `2446` glyphs; renders `width=234 ascent=15 descent=3`, 366 inked pixels. The BDF run in the previous
section used the same shim. Anti-aliased: as with the BDF, `--bpp 2` only has levels 0 and 3 (`249528 bytes`).

### FNT

There are two different FNTs:

- **DOS Johab `.fnt`**. `tools/jamoset.py` reads them with `--layout 844`,
  `844-ihnm`, `844-hbios24`, `1044-san`, `621`, `dkb-printer-7x2x2`, `dkb-printer-12x4x4` or `kyra-lok`, and
  `tools/johab844.py` reads a raw 8x4x4 file. **Not supported in this repository: no DOS Johab `.fnt` is here**, so no
  recipe could be run.
- **Windows `.FNT`.** FreeType has a winfnt driver, so `mkfont.py` (which renders through FreeType) could read a
  Windows FNT the way it reads a BDF or PCF, at the font's own pixel size. It is untested: **the repository has no
  sample**, and a search of `/usr/share/fonts` and `~` for `.FNT`/`.FON` found no Windows FNT (the files with those
  names are FONTX2 fonts or DOS bitmaps, not Windows FNT).

### HBF

**Not supported in this repository: no HBF and no Hangul BDF to pair it with.** `tools/bdfface.py --ascii` reads an
HBF (with its `.bin` or `.bin.gz` beside it), but only as the ASCII half of a face; the Hangul half must be a BDF, and
there is no `.hbf` here. The reader is exercised with a synthetic HBF by `tools/test_bdfface.py`.

### An existing SVF

Source: `svf/dos/NEODG16.SVF` (a precomposed 1 bpp face, 16x16, 2905 glyphs, with a metrics table).

Set a dy (no other byte changes):

    python3 tools/svfdy.py svf/dos/NEODG16.SVF /tmp/svf-tools-doc/neodg16-dy.svf --range 0x20-0x7e --dy 3

`127856 bytes` (unchanged), `2905` glyphs, dy set on 95 glyphs, range 0..3. Renders:
`width=144 ascent=12 descent=7` (the descent grew by the dy), 559 inked pixels.

Re-bake as a jamo set:

    python3 tools/jamoset.py --layout 844 --from-svf svf/dos/NEODG16.SVF -o /tmp/svf-tools-doc/neodg16-from-svf.svf

`40385 bytes`, `892` cmap glyphs, `344` pieces; fit: 2357 syllables, IoU 1.000 (neodgm is itself an OR of pieces).
Renders: `width=144 ascent=12 descent=4`, 559 inked pixels.

An existing SVF is not a source for an anti-aliased bake: no tool converts a 1 bpp face to 2 bpp, and `svfdy.py`
changes only the dy.

## Gaps for the SVF maker

What the SVF maker would need that no tool does today. Each line names what is missing.

- **Format detection.** No tool identifies an uploaded file's format; `mkfont.py` hands the bytes to Pillow, and
  `jamoset.py` needs `--layout` to name the source kind. There is no sniffing of TTF/OTF/BDF/PCF/FNT/HBF/SVF.
- **`cmap_has` crashes on a non-sfnt file.** `mkfont.py` reads PCF and BDF through Pillow's FreeType, but with
  `--unicode` `cmap_has` calls `fontTools.TTFont()` and catches only `ImportError`, so a BDF or PCF dies with
  `fontTools.ttLib.TTLibError: Not a TrueType or OpenType font (bad sfntVersion)` when fontTools is installed. The
  path does not work as checked out; returning None on `TTLibError` is a one-line fix (the SVF maker plan's, not this
  repository's).
- **Bitmap fonts open only at their strike size.** A PCF or BDF opens at the pixel size built into the file and at no
  other (`OSError: invalid pixel size`), and nothing lists the strikes a bitmap font offers.
- **Windows `.FNT` reading.** FreeType has a winfnt driver, so `mkfont.py` should read a Windows FNT the way it reads
  a BDF/PCF, but there is no sample here to test it with, so it is unverified; the DOS Johab raw formats and the
  Dokkaebi printer FNTs are the only FNTs any tool reads today.
- **A character set is required.** `mkfont.py` has no code page (version 1) order any more: without `--unicode` or
  `--chars-from` it exits 2 (`mkfont: version 1 (code page order) is gone: pass --unicode SET`).
- **No fixed-width face.** `mkfont.py` always writes a metrics table; `--fixed`, `--center` and `--variable` are gone.
- **Mode-dependent jamoset options.** `--embolden`, `--symbols`, `--ascent`, `--eng` and `--base` are ignored in some
  `jamoset.py` modes (see its Modes column); a maker toggle wired to the wrong mode would silently do nothing.
- **Run time.** A 2 bpp jamo set from a 16 px outline face took about 84 s and a 1 bpp `threshold` fit about 13 s on
  this host, which a web request must allow for.
- **Korean stdout.** `mkfont.py` prints its summary in Korean, so a wrapper must not parse its stdout for field names.
- **The default `--binarize mono` needs freetype-py and uharfbuzz.** Those are absent on this host
  (`cannot import freetype`), which is why the recipes use `--binarize threshold`; a maker must ship them or take the
  threshold path.
- **Metadata reporting.** No tool prints an input font's family or style (the name table), its available sizes, or its
  glyph coverage. `web/mkindex.py` reports coverage for SVF faces it indexes, and `mkfont.py` prints how many requested
  code points it kept, but neither reports on an arbitrary TTF/OTF.
- **Hangul coverage reporting.** No tool reports how many of the 11,172 syllables (or the 2,350 KS X 1001 ones) and
  which jamo an input font covers. `mkfont.py` drops absent code points and counts them; `mkindex.py` counts coverage
  of a baked face.
- **Automatic cell size.** No tool chooses a cell size from a font. `mkfont.py --fit-cell` shrinks the size to fit a
  cell the caller gives, but it does not pick a cell.
- **BDF/PCF/FNT/HBF inputs for the maker.** The BDF and HBF readers exist only inside `bdfface.py` (and the hanterm
  layout inside `jamoset.py`); PCF and BDF reach `mkfont.py` only through FreeType, at one strike size; the DOS Johab
  readers exist only in `jamoset.py`/`johab844.py`. There is no single "read any bitmap font" entry point, and Windows
  FNT has no verified reader.
- **1 bpp to anti-aliased conversion.** No tool makes a 2 bpp face from a 1 bpp face or from a bitmap source; 2 bpp
  faces come only from an outline font (`mkfont.py --bpp 2`, `jamoset.py --bpp 2`, `jamovec.py render --bpp 2`).
- **A page-facing bake API.** The bakes are command-line programs that write a path; nothing exposes them as a library
  call with a return value, which a server-side SVF maker needs.
