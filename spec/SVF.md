**English** | [한국어](SVF.ko.md)

# SVF (SVFN) bitmap font format

Copied on 2026-10-19 from ScummVM branch `jamo` at 40ffd1479a4, `graphics/hires_text/README.md`, sections "Bitmap fonts
(G2)" through "Per-glyph dy", and maintained here since. This file is the master copy of the format; the ScummVM README
links here.
How ScummVM loads a face (`[load]`, `[preload]` in a map) is in the appendix at the end. The portable C renderer's API
is `c/include/svf.h`; it reads version 3 files only.

SVFN is at **version 3**. Versions 1 and 2 are retired (see "Retired: versions 1 and 2" below); `tools/svf2to3.py`
converts a v2 face.

## Bitmap fonts (G2)

`HiResBitmapFont` reads the "SVFN" bitmap font format: 1bpp stencil, or 8bpp or
2bpp coverage, optional per-glyph metrics. The coverage forms carry anti-aliased
shapes baked by a tool, so a build without FreeType renders the same glyphs; that
makes it the primary format rather than a fallback.

Lookup is by Unicode code point through the file's own code point table (a
version 1 file ordered its glyphs by a code page instead; that form is retired).

The CJK block decoding uses ScummVM's shared conversion tables, so
`encoding.dat` must be reachable at run time. Without it every CJK lookup
returns -1 and the engine already warns "Support for CJK is disabled".
Single byte fonts do not depend on it.

These fonts hold only their double byte block: ASCII resolves to -1 in a Korean
font and belongs to a separate single byte font. Header offsets are all checked
against the file, `load` bounds its allocation with a caller-supplied limit, and
a metrics table that does not fit is dropped without losing the glyphs.

Verified against the shipped fonts inside a running engine (MI2 and Indy3
Korean targets): U+AC00 maps to glyph 0 and U+D79D to glyph 2349 in the 2350
glyph Korean sets, 'A' maps to glyph 65 in the Latin sets, and the engine's own
legacy `.fnt` files are rejected so the caller can fall back.

### Jamo-set fonts (flags bit 1)

A face holding every syllable precomposed is large (DOTT's 1bpp faces total
1,954 KB); a DOS Hangul system held positional jamo pieces and drew a syllable
as the OR of two or three. An SVFN whose header flags carry bit 1 (0x2)
is such a font: the header names a **JSET** block (offset and size), and `createSvfnSource()` returns a `JamoGlyphSource` for it, so a map
names the file like any face (`ui=data:DOTTJ0.SVF`). An older reader ignores
the bit and the block and sees a plain font.

See also [docs/jamo-sets.md](../docs/jamo-sets.md): the background (johab as a character set and as a font technique,
the DOS set systems), a worked example through a real face, and the MCU constraints of each form.

- The pieces are glyphs at code point U+F0000 + piece number (plane 15, private
  use). The numbers are the font's own; the JSET tables name them.
- Any other glyph (ASCII, symbols, compatibility jamo stored whole) is looked
  up as in any SVFN.
- The block is where header bytes 36 (offset) and 40 (size) say; both are 0 without the flag. The offset is a
  multiple of the table unit and lies at or after byte 48 and inside the file together with the size. The size must
  equal what the block's counts give. A block that fails validation (counts, classes, sets out of range, a size that
  does not add up or is 0 with the flag set, a piece number with no glyph) makes the face load as a plain SVFN
  (`SVF_FACE_JSET_BAD` in the C renderer; the engine warns once naming the file). Only a JSET range outside the
  file or inside the header is a range error.
- U+AC00..U+D7A3 are composed from the pieces by the maximum coverage at each
  pixel (the OR of a 1bpp stencil; 2bpp and 8bpp work too); U+3131..U+3163 with
  a compatPiece are that piece alone. A composed glyph fills one cell (the
  stored glyph box) and advances by the JSET advance, or the cell width when
  that is 0. (The engine calls a syllable "two cells wide"; there a cell is
  its own row-buffer unit, half a syllable, not the stored glyph box.)

JSET block, little-endian. Two block versions exist; the block's own version word says which. **Version 1 is the standard
format** and what every tool writes by default; version 2 (below) is an exception-only format for memory-constrained
targets. Version 1:

```
4  "JSET"
2  version (1)
1  LC  lead classes   (1..12; BIG 1..19)
1  TC  tail classes   (1..12; BIG 1..28)
1  NI  initial sets   (1..32; BIG 1..128)
1  NM  medial sets    (1..24; BIG 1..128)
1  NF  final sets     (1..16; BIG 1..64)
1  advance            syllable advance in px; 0 = the cell width
19 leadClass[19]      class of each initial (ㄱ..ㅎ), < LC
28 tailClass[28]      class of each tail, index 0 = no tail, < TC
LC*21*TC initSet      set of the initial for (leadClass, vowel, tailClass), < NI
LC*21*TC medSet       set of the medial
LC*21*TC finSet       set of the final (read only when tail != 0)
NI*19 u16 initPiece   piece number per (set, initial); 0xFFFF = blank
NM*21 u16 medPiece    per (set, vowel)
NF*27 u16 finPiece    per (set, tail 1..27)
51 u16 compatPiece    U+3131..U+3163 drawn from one piece; 0xFFFF = not by piece
```

The three set tables are indexed `(leadClass * 21 + vowel) * TC + tailClass`
(vowel 0..20 in Unicode order, ㅏ..ㅣ); a piece table is indexed
`set * 19 + initial`, `set * 21 + vowel`, `set * 27 + tail - 1`. A final set
is validated and read only for tail classes some tail 1..27 belongs to. The
DOS set systems (8x4x4, 10x4x4, hanterm's 10x(3|4)x4, 6x2x1, the Dokkaebi
printer sets, Kyra's jamo-major order, and the Mac HangulTalk 1.0 'fbit' fonts with their 8 lead classes and
20 initial sets) are all expressible; `tools/korean/jamoset.py`
writes such fonts, also at 2 bpp from an outline font (`--bpp 2`, anti-aliased
pieces composed by the maximum) and with set systems fitted to the font
(`--layout adaptive`, up to the limits above).

The class limits were 8 and 8 until 2026-10 (largest block 6641 bytes); they
are 12 and 12 then (11681 bytes), with the version still 1 since the layout did
not change. An engine built before that rejects a block with more than 8
classes of either kind (the font then loads as a plain SVFN, its syllables
from the next source), so faces with 9..12 classes need a current engine;
every older face loads unchanged.

In 2026-10 (v3) the set limits rose from 24 / 16 / 16 to 32 / 24 / 16 (initial / medial / final); the largest block is
12321 bytes (12 x 12 classes, 32 / 24 / 16 sets). The adaptive default budget is 32 / 24 / 12. An out-of-range count
is still a bad JSET (the face loads plain; `SVF_FACE_JSET_BAD`). Every face with up to 24 / 16 / 16 sets stays valid.

`SVF_JSET_BIG` widens the limits of versions 1 and 2 in place (no new version word): 19 lead x 28 tail classes and
128 / 128 / 64 initial / medial / final sets; the largest blocks are 47,373 bytes (version 1) and 29,708 bytes (version 2, NA = 0;
45,068 with every slot an alias). A reader built without it treats counts over 12 x 12 / 32 / 24 / 16 as a bad JSET. Writers
(`--jset-big`) and `jamoset.pack` refuse a table over the standard row unless asked; `jamoset.unpack` reads both. Output within the
standard limits is byte-identical either way.
Version 1 sizes: `12 + 19 + 28 + 3 * LC * 21 * TC + 2 * (NI*19 + NM*21 + NF*27 + 51)` bytes.

#### JSET block version 2 (compact; exception-only)

Version 2 holds the same tables in fewer bytes: the three set tables are bit-packed, the piece numbers are implicit
(a presence bit per slot, a base per set, pieces numbered in order) with an alias escape for a piece shared between
slots, and the compat table is one byte per jamo. It changes no bitmap, glyph record, cell or composition rule and no
limit (LC, TC <= 12; NI <= 32, NM <= 24, NF <= 16; BIG: 19, 28; 128, 128, 64, as for version 1); the SVFN header and its JSET offset (36) and size (40) fields are as
for version 1. Nothing inside the block is aligned; bits are numbered LSB first within a little-endian byte stream
(bit `b` is bit `b & 7` of byte `b >> 3`).

```
off  size            field
0    4               "JSET"
4    u16             version = 2
6    1               LC  lead classes (1..12; BIG 1..19)
7    1               TC  tail classes (1..12; BIG 1..28)
8    1               NI  initial sets (1..32; BIG 1..128)
9    1               NM  medial sets  (1..24; BIG 1..128)
10   1               NF  final sets   (1..16; BIG 1..64)
11   1               advance (px; 0 = cell width)
12   u16             NA  alias entries (0..NI*19+NM*21+NF*27)
14   u16             reserved, 0
16   19              leadClass[19]  < LC
35   28              tailClass[28]  < TC, index 0 = no tail
63   S               set table: LC*21*TC cells of W bits each, S = ceil(LC*21*TC*W / 8)
63+S NI*RI           initial set rows
     NM*RM           medial set rows
     NF*RF           final set rows
     NA*2            alias table: u16 piece numbers
     51              compat[51]: one byte per U+3131..U+3163
```

**Set table.** Cell `c = (leadClass[lead]*21 + vowel)*TC + tailClass[tail]`, as in version 1. `width(n)` is 0 for n = 1,
else `ceil(log2 n)` (2 -> 1, 32 -> 5); `WI = width(NI)`, `WM = width(NM)`, `WF = width(NF)`, `W = WI + WM + WF`
(0..14; BIG 0..20). Cell `c` occupies bits `c*W .. c*W + W - 1`: the initial set in the low WI bits, the medial set in the next
WM, the final set in the top WF. A width of 0 reads as set 0. A reader takes each field with one two-byte fetch at
the byte offset (bit offset `>> 3`), a shift by the bit offset `& 7` and a mask (a field is at most 5 bits wide; BIG 7: a 7-bit field at bit offset 7 still fits the two-byte fetch).

**Set rows.** One row per set, a fixed size per table, so row `s` is at `rows + s*R`. PB is the presence width in
bytes: 3 for initial (19 slots) and medial (21), 4 for final (27).

```
NA = 0:  u16 base | presence PB bytes                                  RI = RM = 5, RF = 6
NA > 0:  u16 base | u16 abase | presence PB bytes | alias PB bytes     RI = RM = 10, RF = 12
```

Slot `j` (initial 0..18, vowel 0..20, tail index 1..27 stored at bit `tail - 1`) is drawn when presence bit `j` is set.
Bits at and above the slot count are padding and must be 0. An alias bit may be set only where the presence bit is.
The piece of a drawn slot is `alias[abase + popcount(aliasBits & below(j))]` when its alias bit is set (NA > 0 only),
else `base + popcount((presenceBits & ~aliasBits) & below(j))`, where `below(j)` is the mask of bits 0..j-1. So a
set's fresh pieces are `base, base+1, ...` in jamo order, and an alias names any piece by number; the reader never
assumes bases are cumulative or disjoint. 0xFFFF is never a valid alias entry (a blank slot is a clear presence bit).

**Compat.** `compat[k]` for U+3131 + k: 0xFF = not drawn by piece; else bits 0-6 a set number and bit 7 a table
switch (the set must be below its table's count: at most 31 in the standard row, 127 for initial and medial tables under BIG;
the bit 7 form names a final set, at most `0x80 | 63 = 0xBF`, so 0xFF never names a set). The natural table of k: k >= 30 is vowel `k - 30` in the medial table; a consonant
with a lead index uses the initial table at that lead; a cluster consonant uses the final table at its tail index.
Bit 7 on a consonant that has a lead index selects the final table at its tail index instead (bit 7 on a vowel, a
cluster, or one of ㄸ ㅃ ㅉ is invalid). The drawn piece is that set's slot for that jamo, which must be present. The
reader's constant map for k = 0..29 (lead index, or `T` + tail index):

```
ㄱ0 ㄲ1 ㄳT3 ㄴ2 ㄵT5 ㄶT6 ㄷ3 ㄸ4 ㄹ5 ㄺT9 ㄻT10 ㄼT11 ㄽT12 ㄾT13 ㄿT14 ㅀT15 ㅁ6 ㅂ7 ㅃ8 ㅄT18 ㅅ9 ㅆ10 ㅇ11 ㅈ12 ㅉ13 ㅊ14 ㅋ15 ㅌ16 ㅍ17 ㅎ18
```

and the tail index of a lead-capable consonant for the bit 7 form: ㄱ1 ㄲ2 ㄴ4 ㄷ7 ㄹ8 ㅁ16 ㅂ17 ㅅ19 ㅆ20 ㅇ21 ㅈ22
ㅊ23 ㅋ24 ㅌ25 ㅍ26 ㅎ27.

**Size.** `size = 63 + S + NI*RI + NM*RM + NF*RF + 2*NA + 51`. The largest valid block (12 x 12 classes, 32 / 24 / 16
sets, every slot an alias, NA = 1,544) is 9,246 bytes; under BIG (19 x 28 classes, 128 / 128 / 64 sets) 29,708 bytes with NA = 0
and 45,068 with every slot an alias. Examples (NA = 0): 6 / 2 / 1 sets in 1 x 2 classes, 181 bytes
(version 1: 653); 8 / 4 / 4 sets in 2 x 2 classes, 272 (1,101); 32 / 24 / 12 sets in 8 x 8 classes, 2,818 (7,065);
24 / 16 / 16 sets in 12 x 12 classes, 5,324 plus the aliases (11,681).

**Validation** (everything below makes the face load plain, `SVF_FACE_JSET_BAD`, never an error; each check reads
only bytes the earlier ones have bounded): (1) length >= 16, magic, version 2, the five counts inside the limits,
reserved == 0, NA <= NI*19 + NM*21 + NF*27; (2) length == the size formula; (3) `leadClass[i] < LC`,
`tailClass[i] < TC`; (4) every cell's initial set < NI and medial set < NM, final set < NF only in cells of a tail
class some tail 1..27 belongs to; (5) every row: padding bits of presence and alias 0, alias bits a subset of the
presence bits, `abase + popcount(alias) <= NA`; (6) every drawn slot (fresh or alias) resolves, in 32 bits, to a piece number below
0xFFFF whose glyph exists, and no alias table entry is 0xFFFF (alias entries no slot uses are not checked for a glyph);
(7) every compat byte is 0xFF or has `c & 0x7F` below its table's count, with bit 7 only on a lead-capable consonant
with a final form (not ㄸ ㅃ ㅉ), and that set's slot for the character is present.

#### When to use version 2

Version 1 is the standard: every writer and `tools/svf2to3.py` write it unless asked, the maker keeps an uploaded face's
version (version 2 only through its explicit `--jset-version` option), and `svf/` stays version 1. Use version 2 only

- for a build or pack aimed at a memory-constrained target, where the JSET bytes in flash or the streamed tables in
  RAM matter;
- for large faces: 12 x 12 classes and most 8 x 8 classes. `--jset-version auto` writes version 2 only when it saves at
  least `JSET_V2_MIN_SAVING` (1,024 bytes, `tools/jamoset.py`); over the 95 shipped jamo faces that is 58 faces, and
  the JSET bytes fall from 652,431 to 337,695 (all 95 in version 2 would be 310,160);
- when the reader is compiled in: the dual reader costs about +1.2 KB on Cortex-M0+ (+1,247 B; version 2 alone +535 B,
  `c/cross/SIZES.md`), and AVR builds (and the CH582 port, which embeds a v1 face) read version 1 only;
- accepting that composing a syllable from a version 2 face is slower: measured on the Pico (`syl_ga`, `syl_bwelk`,
  `screen32`) it was 5-7 % over the version 1 reader of the main branch before the change (BASE), not over a version 1 face
  of the current build.

Which build reads which (C renderer, `c/include/svf.h`): `SVF_JSET_V1` (default 1) and `SVF_JSET_V2` (default 1, except builds
that leave it at 0: AVR by default, and the CH582 port, pinned to v1 because it embeds a v1 face) compile the readers; a face of a version the build does not read loads plain (`SVF_FACE_JSET_UNREAD`; `SVF_FACE_JSET_BAD` is kept for a malformed block), and at
least one must be 1. `SVF_JSET_POP4` (default 1; 0 under `SVF_SMALL` and on AVR) picks a 16-entry nibble table over a
bit-clearing loop for the version 2 reader's popcount; the pixels do not change. `SVF_JMAP_LIST` (default: the value of `SVF_JMAP`, so on for host, DOS, WASM and SDL builds and off for every MCU; an explicit `-DSVF_JMAP_LIST=0/1` wins, and 1 without `SVF_JMAP` is an `#error`) compiles the reader of a LIST block (flag 0x08) inside `SVF_JMAP`; without it a LIST block is `SVF_FACE_JMAP_UNREAD` (see "Reader statuses"). `SVF_JSET_TRUSTED` (default 0) skips
the validation of the table contents. **Warning:** it is only for faces the developer builds into flash; a hostile or
corrupt JSET (counts, classes, sets, pieces) then reads out of bounds. Only the header length, the magic, the version and
the block size the counts give against the region length are still checked (the version 1 reader also its count limits; the
version 2 reader trusts its counts), so a streamed face loads no more than its region; in a 16-bit build (AVR) with both
`SVF_JSET_V2` and `SVF_JSET_TRUSTED` the size product of a corrupt count can wrap. With `SVF_JMAP` a version 3 block keeps only its header rules (R1-R4; for a LIST R1', L2, L3, R4) under `SVF_JSET_TRUSTED`: its rank table, bitmap, entries, compat entries and the glyph of every piece (R5-R8; for a LIST L5, L6, L7) are trusted, and a corrupt rank or bitmap drives an entry read far outside the block (about 264 KB); only for faces the toolchain wrote. The fuzz harnesses refuse to compile with it. The
Python `jamoset.unpack` reads all three versions (1, 2 and the JMAP of version 3). Every writer takes `--jset-version 1|2|auto` (default 1; see
`docs/tools.md`).

#### Version 3: mapping table (JMAP)

Version 3 replaces the class and set tables by a direct map from a syllable to its pieces, for faces whose selection
rule is not a function of the jamo classes (the Mac HangulTalk 7.1.x faces, or a font with an exception list). All
numbers are little-endian; a reader uses byte reads only.

| offset | size | field |
|---|---|---|
| 0 | 4 | `"JSET"` |
| 4 | u16 | version = 3 |
| 6 | u8 | flags: 0x01 4B (entries are 4 bytes, else 3), 0x02 SPARSE (a bitmap and NS entries, else dense, NS = 11,172), 0x04 FALLBACK (a JSET version 1 or 2 block follows the entries and runs to the end of the region), 0x08 LIST (NS entries of 8 bytes, sorted by key, over a shared piece pool; excludes 0x01 and 0x02); bits 4-7 zero |
| 7 | u8 | advance in px (0 = the cell width) |
| 8 | u16 | NS, the number of entries; LIST: 1..255, so byte 9 is zero |
| 10 | u16 | PI, initial pieces, U+F0000 + 0 .. PI-1 (LIST: 0) |
| 12 | u16 | PM, medial pieces, U+F0000 + PI .. PI+PM-1 (LIST: 0) |
| 14 | u16 | PF, final pieces, U+F0000 + PI+PM .. PI+PM+PF-1 (LIST: 0) |
| 16 | u16[51] | compat piece numbers for U+3131 + k: 0xFFFF blank, else below PI+PM+PF (LIST: a piece of the pool that has a glyph) |
| 118 | u16[44] | SPARSE only: `rank[b]`, the set bits of the bitmap below bit `b * 256` |
| 206 | u8[1397] | SPARSE only: presence bitmap over U+AC00..U+D7A3, bit `s` is byte `s >> 3`, bit `s & 7`; bits 11,172..11,175 are zero |
| 1603 | u8 | SPARSE only: pad, zero |
| E | NS x 3, 4 or 8 | the entries; E = 1,604 (SPARSE) or 118 (dense, LIST). LIST: 8 bytes, `u16 key, u16 i, u16 m, u16 f`, sorted by key, strictly increasing, `key = cp - 0xAC00`; the three fields are piece numbers (the glyph at U+F0000 + n), 0xFFFF blank. Dense and SPARSE, 3B: `[i, m, f]`. 4B: `[b0, i_lo, m_lo, f_lo]` with `b0 = i_hi (bits 0-2) \| m_hi (bits 3-5) << 3 \| f_hi (bits 6-7) << 6`. In dense and SPARSE entries a field 0 means no piece of that plane, k means the k-th piece of the plane (a LIST field is a piece number: 0 is piece 0) |
| F | rest | FALLBACK only: F = E + NS x (3 or 4), or 118 + 8 NS for a LIST (at most 2,158); a JSET version 1 or 2 block, whose length is the region minus F |

Limits: 3B: PI, PM, PF <= 255; 4B: PI, PM <= 2,047 and PF <= 1,023; PI + PM + PF >= 1 (dense and SPARSE; a LIST has PI = PM = PF = 0, rule L2); SPARSE: 1 <= NS <= 11,172
(11,172 is valid: an exception list may cover everything); dense: NS = 11,172; LIST: 1 <= NS <= 255; the region is at most 65,534 bytes (the
JSET size is clipped to 0xFFFF at open, so a region of exactly 65,535 is never valid). Sizes: sparse 3B for 2,350
syllables without fallback is 16 + 102 + 1,486 + 2,350 x 3 = 8,654; dense 3B 33,634; dense 4B 44,806; sparse 4B with
11,172 entries 46,292; LIST 118 + 8 NS, at most 2,158 (NS 36: 406), plus the fallback block.

**Lookup.** Syllable index `s = cp - 0xAC00`. Dense: `idx = s`. SPARSE: the syllable is present when bit `s` of the
bitmap is set, and `idx = rank[s >> 8] + popcount(bitmap bytes (s >> 8) * 32 .. (s >> 3) - 1) + popcount(byte (s >> 3) &
((1 << (s & 7)) - 1))`. The pieces of a hit with fields `i, m, f`: initial `i - 1`, medial `PI + m - 1`, final
`PI + PM + f - 1`; a 0 field is `SVF_PIECE_BLANK` (0xFFFF). The entry decides the count: 3 pieces when `f != 0`,
else 2, whatever the syllable's final. Pieces are numbered per plane; a glyph two planes share is stored twice.

**LIST lookup.** With flag 0x08 the syllable index `s = cp - 0xAC00` (0..11,171; any other `s` is a miss) is searched by
binary search over the NS entries (key at 118 + 8 j, strictly increasing). The fields of a hit are piece numbers of one
shared pool, not plane indices: the glyph at U+F0000 + n, whoever stores it (a piece of the fallback's tables, a compat
piece, or a glyph that exists only for the LIST), and 0xFFFF is blank. Piece 0 is a piece, not "none". The pieces of a hit
are `[i, m, f]` when `f != 0xFFFF`, else `[i, m]` (the entry decides the count; a blank `i` or `m` is skipped when
composing). A whole glyph (a precomposed cell) is an entry with `i` = its piece number and `m = f = 0xFFFF`: it is drawn
as a piece, into the cell at dy 0, advancing by the JSET advance; its own metrics entry is not consulted. A key miss
goes to the fallback exactly as a SPARSE miss does; without a fallback the syllable is not composed. The fallback's piece
numbers are not shifted: it names pieces in the same pool, and sharing a piece with the entries is the point.

**Compat.** The JMAP's own compat entry wins when it is not blank; a blank one falls to the fallback's compat
entry (if there is a fallback), else the cmap glyph. A Mac compat jamo of more than one plane is a whole glyph at
U+3131 + k with a blank JMAP compat.

**Fallback.** A miss (a syllable the bitmap does not list) is answered by the fallback JSET, version 1 or 2
only; without one the syllable is not composed (the cmap glyph, or the missing glyph, as in a plain face). The
fallback's advance byte must equal the JMAP advance. The fallback names pieces in the same U+F0000 + n space as the
JMAP's planes, so, in a dense or SPARSE block, every piece number it names (its piece lists and compat) must be BLANK or at least PI + PM + PF; a
writer shifts the fallback's pieces up by PI + PM + PF and writes the block with `jamoset.pack_fallback(tables,
version, base)`, which keeps the piece numbers it is given (version 2 stores a drawn slot as a fresh piece when it
counts up from its row's first piece and as an alias otherwise, so any numbers fit, at the cost of a larger block than
`pack`'s); `jamoset.pack_jmap` refuses an overlap. The disjointness is a writer rule only: readers do not check it (a
piece number stays inside the glyph table whatever it is, under R8), so a reader adds no such check. This holds for dense and
SPARSE; a LIST has PI + PM + PF = 0, shifts nothing and shares the pool with its fallback (no overlap refusal).

**Validation.** A reader checks in this order, each rule reading only bytes the earlier ones bounded:

- R1: length >= 118, magic `JSET`, version 3, `flags & 0xF8 == 0` for a dense or SPARSE block. For a LIST the rule is R1':
  length >= 118, magic, version 3, `flags & 0xF0 == 0`, and not `(flags & 0x08) && (flags & 0x03)` (LIST with 4B or SPARSE).
- R2 (dense and SPARSE): PI, PM, PF within the 3B or 4B limits, PI + PM + PF >= 1.
- L2 (LIST, in place of R2): PI = PM = PF = 0; R2's `PI + PM + PF >= 1` does not apply.
- R3: NS in 1..11,172 (SPARSE) or == 11,172 (dense).
- L3 (LIST, in place of R3): NS in 1..255 and byte 9 is 0 (one test on the u16 at offset 8: the block fails when `ns - 1u >= 255u`).
- R4: the region is at most 65,534 bytes (F = 118 + 8 NS, at most 2,158, for a LIST); without FALLBACK the length is exactly F; with it the length is at least
  F + 12 and the fallback header is readable (magic, version 1 or 2); the advance byte of the fallback (byte 11 of the fallback header) equals the JMAP advance (byte 7 of the JMAP
  header), in every build that can read the header; then, when the build reads that
  version, the fallback is well-formed. So one face is never bad in one build and usable in another because of the
  advance.
- R5: every compat entry is 0xFFFF or below PI + PM + PF (dense and SPARSE).
- L5 (LIST, in place of R5): every compat entry is 0xFFFF or a piece number whose glyph exists.
- R6: SPARSE only: the pad byte is 0, bitmap bits 11,172..11,175 are 0, `rank[b]` equals the set bits below `b * 256`
  for b = 0..43, and the total equals NS.
- L6 (LIST, in place of R6): the keys are strictly increasing and the last is at most 11,171 (read only after R4 has bounded NS against the region).
- R7: every entry field is at most its plane's count.
- L7 (LIST, in place of R7 and the entry part of R8): every entry field is 0xFFFF or a piece number whose glyph exists.
- R8 (the caller's, as for JSET; dense and SPARSE): every piece number below PI + PM + PF, every piece the fallback names and every
  non-blank compat piece has a glyph. A fallback's own pieces can be checked only by a build that can read the fallback: in a build
  that cannot (`SVF_FACE_JSET_UNREAD`) the JMAP part stays usable while Python, which reads every version, marks a block whose fallback
  names a piece without a glyph bad (build-dependent by design; the plane pieces and the compat pieces are checked everywhere).

For a LIST the header rules are R1', L2, L3 and R4, and the content rules are L5, L6 and L7. L5 and L7 are the caller's check, like R8: the Python `jamoset.unpack_jmap` does not make them (`parse_svfn`'s usable rule does).

**Reader statuses.** One cause bit per part: `SVF_FACE_JSET_BAD` (0x0008) for a JSET-part block that is malformed,
or of version 0 or >= 4; `SVF_FACE_JSET_UNREAD` (0x0010) for a well-formed version 1 or 2 header whose reader is not
compiled; `SVF_FACE_JMAP_BAD` (0x0020) for a version 3 block that fails any rule above, a malformed fallback included
(one block, one verdict); `SVF_FACE_JMAP_UNREAD` (0x0040) for a version 3 block in a build without `SVF_JMAP` but
with `SVF_JMAP_RECOG`, and for a LIST block in a build with `SVF_JMAP` and `SVF_JMAP_LIST=0` when its header rules pass, else `SVF_FACE_JMAP_BAD` (see the table below; for the RECOG build, the recognition: it reads the flags and NS, and with FALLBACK reads a well-formed version 1 or 2
fallback in the JMAP's place; default on for desktop builds, off on AVR, `SVF_SMALL` and other MCUs). A build with neither
`SVF_JMAP` nor `SVF_JMAP_RECOG` treats version 3 like any unknown version: `SVF_FACE_JSET_BAD`, a plain face, no fallback
use. In a build with `SVF_JMAP_RECOG` and without `SVF_JMAP` the fallback is the JSET part: its verdict is `SVF_FACE_JSET_BAD` / `SVF_FACE_JSET_UNREAD` (beside `SVF_FACE_JMAP_UNREAD`); only the advance comparison (R4), the flag and NS rules (R1, R3; for a LIST R1' and L3) and a region of exactly 65,535 bytes (R4) set `SVF_FACE_JMAP_BAD` there (a region cut short of the fallback header is a malformed fallback: `SVF_FACE_JSET_BAD` beside `SVF_FACE_JMAP_UNREAD`), so "one block, one verdict" holds for builds that read the block (`SVF_JMAP`, and for a LIST also `SVF_JMAP_LIST`), not for `SVF_JMAP_LIST=0` or RECOG builds. A well-formed fallback whose version 1 or 2 reader is not compiled does not make the block bad: the JMAP part stays
usable and the fallback part is `SVF_FACE_JSET_UNREAD`. The same holds in a build with `SVF_JMAP` and without
`SVF_JSET_BIG` for a fallback whose five counts are within the BIG row but one over the build's row: the fallback is
`SVF_FACE_JSET_UNREAD` (only its counts are read) and the JMAP part stays usable; a stand-alone JSET of such counts is
`SVF_FACE_JSET_BAD`. A face whose JMAP part is not usable loads as a plain face.

| build | LIST face (flag 0x08) |
|---|---|
| `SVF_JMAP=1`, `SVF_JMAP_LIST=1` (default with `SVF_JMAP`) | read: a key miss goes to the fallback; a failed rule (R1', L2, L3, R4, L5, L6, L7): `SVF_FACE_JMAP_BAD`, plain |
| `SVF_JMAP=1`, `SVF_JMAP_LIST=0` | the header rules R1', L2, L3 and R4 only, the fallback's own well-formedness included: a failure is `SVF_FACE_JMAP_BAD`, plain; a pass is `SVF_FACE_JMAP_UNREAD` and the fallback is used. L5-L7 are not applied here, so a block with unsorted keys or a field without a glyph is `SVF_FACE_JMAP_BAD` with `SVF_JMAP_LIST=1` and "fallback used" here (an exemption of the kind RECOG builds have; "one block, one verdict" is promised for builds that read the block) |
| `SVF_JMAP=0`, `SVF_JMAP_RECOG=1` | the recognition keeps its own rule set and read pattern: it reads bytes 6-9, then one byte at F + 11 once F + 12 <= the region, and never reads bytes 10-15 (so L2 and R2 are not applied). It learns R1' (the mask and the combination test), L3 (NS in 1..255) and F = 118 + 8 NS for a LIST. `SVF_FACE_JMAP_BAD` for R1', L3, the advance comparison or a region of exactly 65,535 bytes; otherwise `SVF_FACE_JMAP_UNREAD`, with the fallback used when the block has a well-formed one. A streamed region longer than the build's `SVF__JSET_LOAD_MAX` is not loaded: the face stays plain with `SVF_FACE_JMAP_UNREAD` alone (the same for a SPARSE block) |
| neither switch | `SVF_FACE_JSET_BAD`, plain, as for every version 3 block |

A build of this tree that predates LIST sees a LIST face as plain, its fallback included (R1 fails before R4 finds the fallback); the JMAP reader is not deployed outside this tree. The Python reference is `jamoset.unpack_jmap`, whose ValueError text starts
`JMAP Rn` (for a LIST `JMAP R1`, `JMAP L2`, `JMAP L3`, `JMAP R4` or `JMAP L6`).

### Per-glyph dy (header bytes 17 and 18, metrics byte 3)

The SVFN v3 header is 48 bytes, little-endian:

```
0  "SVFN"   4 u16 version (3)   6 u16 flags (bit 0 metrics table, bit 1 JSET, bit 2 marks at origin; others 0, and a reader refuses a face with other bits set)
8  bpp (1, 2, 8)   9 layout: record and row units   10 layout: table unit and offset width   11 reserved (0)
12 u16 glyphs (1..65535)
14 cell width   15 cell height   16 ascent (baseline row)   17 dy_min (int8, <= 0)   18 dy_max (int8, >= 0)   19 reserved (0)
20 u32 metrics table offset      24 u32 glyph data offset        28 u32 glyph data size
32 u32 code point table offset   36 u32 JSET offset              40 u32 JSET size
44 u32 glyph offset table offset
```

A metrics entry is 4 bytes: advance, left bearing (int8), ink width, and **dy**
(int8): the glyph is drawn `dy` rows below its cell position (negative: above),
`dy_min <= dy <= dy_max`. The glyph's rows are stored in the cell as always; dy
only moves where they are drawn, and ink that then lies outside the cell is
drawn, not clipped. A Latin face whose letters must stand on a Hangul baseline
near the bottom of the cell stores them high enough for their descenders and
draws them lower by dy (`tools/korean/svfdy.py` sets it; `jamoset.py` reads and
keeps it).

- Every file written before this had a meaning holds 0 in all of these bytes,
  and draws exactly as before. An engine that predates it ignores them: every
  glyph is drawn at its cell position (a face that uses dy should say so where
  it ships).
- Only a font with a metrics table has a dy per glyph. A range given without
  one, a range with `dy_min > 0` or `dy_max < 0`, or one reaching more than the
  cell height above or below the cell is ignored with a warning (dy 0 for
  every glyph). A glyph whose dy lies outside the range is drawn at dy 0; one
  warning at load counts them.
- `GlyphMetrics::dy` is the glyph's dy, `bearingY` (baseline to the top of the
  stored glyph as drawn) is `ascent - dy`. The cell keeps its meaning:
  `baselineRow()`, the face chain layout, line heights and the cell-height
  checks of a map all use the cell, not the range.
- Buffer rule: `UnicodeGlyphSource::inkRowsAbove()` / `inkRowsBelow()` are
  `-dy_min` / `dy_max` (0 for every other source; a chain takes the largest of
  its faces, a `NormalizedGlyphSource` what leaves its own cell). `row(cp, y)`
  answers `y` from `-inkRowsAbove()` to `cellHeight() + inkRowsBelow() - 1`,
  the glyph already moved by its dy; a drawer sizes its glyph buffer once per
  face as `inkRowsAbove() + cellHeight() + inkRowsBelow()` rows and draws it
  `inkRowsAbove()` rows above the cell top (a null row outside the cell is
  blank). SCUMM (a vertical mirror turns the glyph within its cell), SCI, AGI
  (within its 16-row box), AGS and `HiResGlyphRenderer::drawGlyph(font)` do;
  SCI's placement path still clips to the text line, and Grim draws the cell
  rows only (the glyph moved, clipped to the cell).
- A jamo-set face composes its syllables at dy 0; a piece must not carry a dy
  (`jamoset.py check` refuses one). Its other glyphs (Latin) may.

### Cells, layout bytes and reserved bytes

A **cell** is the glyph box a reader hands back: cell width (byte 14) by cell
height (byte 15) pixels, `pitch * cell height` bytes with
`pitch = (cell width * bpp + 7) / 8`, rows MSB first. Bits past the cell width
in the last byte of a row are written 0 and masked by readers.

**Layout bytes (9 and 10)** give the alignment units, each a power of two stored
as its log2, 0..6 (1..64 bytes):

```
byte 9   bits 0-2  REC  log2 of the record unit: every glyph record starts at a multiple of 2^REC from the file start
         bits 3-5  ROW  log2 of the row unit: each row of a record takes wb rounded up to 2^ROW bytes
         bits 6-7  0
byte 10  bits 0-2  TAB  log2 of the table unit: the code point table, metrics table, JSET, glyph offset table and glyph
                        data start at multiples of 2^TAB (the glyph data also at a multiple of 2^REC)
         bit 3     OFF  glyph offset table entries: 0 = u16 counting in units of 2^REC, 1 = u32 counting bytes
         bits 4-7  0
```

`REC, ROW, TAB <= 6` and `ROW <= REC`; the reserved bits are 0. Byte 11 and byte
19 are reserved: written 0, ignored by every reader. (Bytes 9..11 were the shadow
and the code page of version 1 and 2; nothing reads those now.)

**Tables.** All offsets are file offsets, at or after byte 48, and each table lies
inside the file.

- Code point table (byte 32): `glyphs` entries of `u32 code point, u32 glyph
  index`, normally sorted by code point; a code point listed twice resolves to
  its last entry.
- Metrics table (flags bit 0, byte 20): `glyphs` entries of 4 bytes, `advance,
  bearing_x (int8), ink_w, dy (int8)` (see "Per-glyph dy"). A reader takes
  advance, bearing and ink width from here, never from a record's box.
- JSET (flags bit 1, bytes 36 and 40): see "Jamo-set fonts". Both fields are 0
  without the flag.
- Glyph offset table (byte 44): `glyphs + 1` entries; entry `i` is the start of
  record `i` relative to the glyph data offset (u16 in units of 2^REC, or u32
  bytes, per OFF), entry `glyphs` equals the glyph data size, entries do not
  decrease, and each, in bytes, is a multiple of 2^REC. The length of record `i`
  is `off[i+1] - off[i]`.
- Glyph data (byte 24, size at 28): the records in index order.

The five offsets of bytes 20..47 are multiples of 2^TAB, the glyph data offset
also of 2^REC, and the glyph data size of 2^REC.

**Glyph record.**

```
0  x0   left edge of the box, in BYTES of a cell row
1  y0   top row of the box in the cell
2  wb   box width in BYTES (0 = blank glyph, no rows follow)
3  h    box rows (0 = blank glyph)
4  phase bytes (below), then h rows of rp bytes, rp = wb rounded up to 2^ROW,
   then padding to the next multiple of 2^REC
```

`x0 + wb <= pitch` and `y0 + h <= cell height`. Rows are the cell's own row bytes
cut at byte boundaries, so a reader clears the cell and copies (or, for a
composed syllable piece, takes the byte maximum of) each of the `h` rows into
`cell + (y0 + r) * pitch + x0`. A blank glyph is `wb == 0` or `h == 0`: a
4-byte record, the cell stays clear. **Phase:** when `REC >= 2` and `ROW == 0`, a
record with `wb == pitch` starts its rows at `4 + ((y0 * pitch) & 3)`, so the
rows lie at the same offset modulo 4 as their place in the cell; every other
record has phase 0. Which box a writer chooses (the whole cell, whole rows, or
the ink columns and rows in bytes) is its policy; a reader does not know.

**Profiles.** The writers (`--profile`, default `default`) take a named set of
units; the pixels of a face are the same in every profile:

| profile | REC / ROW / TAB (bytes) | box | offsets |
|---|---|---|---|
| `mcu-strict` | 4 / 1 / 4 | x-boxed | u16 (u32 when the data passes `65535 << REC`) |
| `default` | 4 / 1 / 4 | x-boxed | u32 (the form `svf/` is in) |
| `dos`, `wasm` | 1 / 1 / 1 | x-boxed | u16 (u32 past 64 KB) |
| `full` | 4 / 1 / 4 | full cells | u32 |
| `simd16` | 16 / 1 / 16 | x-boxed | u32 |

**Supported sets.** A reader build may accept only some valid layouts and refuses
the rest with `SVF_E_LAYOUT` before reading any table: the C library takes every
valid layout unless built with `SVF_LAYOUTS` (the Cortex-M0+ P1/P2 and AVR builds
accept exactly the `mcu-strict` units); the Python tools and ScummVM read every
valid layout.

Design and measurements: `docs/superpowers/specs/2026-10-21-svf-v3-design.md`.

### Validation

What a reader checks (`jamoset.parse_svfn` and the C renderer; the engine's
`readLayout` follows), in this order:

- Magic `SVFN`, then version 3 (`SVF_E_VERSION` otherwise), then the layout
  bytes (reserved bits 0, units at most 6, `ROW <= REC`) and the build's
  supported set (`SVF_E_LAYOUT`).
- `bpp` 1, 2 or 8; a glyph count of 0 or an empty glyph box (cell width or height
  0) is refused.
- The code point table, the glyph offset table and the glyph data lie inside the
  file and after the header (`SVF_E_RANGE`), as does a JSET block that has a size.
- The alignment masks and the glyph offset table (entries multiples of 2^REC,
  non-decreasing, the last equal to the glyph data size) hold (`SVF_E_LAYOUT`).
- Every glyph index of the code point table is below `glyphs`. A mapped face has
  every record checked at open (box inside the cell, rows inside the record's
  length: `SVF_E_RANGE`); a streamed face when a record is read, the cell then left
  blank.
- A metrics table (flags bit 0) that does not fit in the file or lies inside the
  header is dropped and the glyphs are kept: every glyph then advances by the cell
  width.
- A code point listed twice in the code point table resolves to its last entry.

### Retired: versions 1 and 2

Version 1 ordered its glyphs by a code page and had no code point table. Version
2 had a 36-byte header with the code point table at byte 32, shadow and code page
at bytes 9..11, fixed-stride full-cell glyph data and its JSET block right after
the code point table. Neither is read any more: the C renderer returns
`SVF_E_VERSION`, `jamoset.parse_svfn` raises `ValueError("SVFN version 2: convert
with tools/svf2to3.py")`. `tools/svf2to3.py` (its private `_parse_v2` is the one
v2 reader left) converts a v2 face to v3 in any profile and proves the pixels did
not change; all faces of `svf/` were converted that way, with the identity
recorded in `c/bench/V2V3-IDENTITY.md`.

### Combining marks (flags bit 2)

A file whose header flags carry bit 2 (0x4) stores each combining mark with
its ink left of the pen inside the cell. A reader draws a mark this way:

- The mark advances 0.
- It is drawn at `anchorX - originX`. `anchorX` is the current pen: the pen
  after the previous glyph that is not a mark, or, for a mark first in the
  line, the pen where the line starts. This is the portable rule (the C
  renderer).
- `originX` is `min(-bearing_x, cell width)` when the face has flags bit 2 and
  the mark's left bearing (metrics byte 1) is negative, else 0.

Without bit 2 `originX` is always 0: the mark's rows start at the pen. Which
code points are marks is the reader's choice, not the file's. The engine
takes it from its glyph source; the C renderer defaults to U+0300..U+036F and
takes a caller predicate (`svf_is_mark_fn` in `c/include/svf.h`).

The engine computes `originX` the same way (`glyph_source_svfn.cpp:384-390`)
but its anchor can differ from the pen. After each glyph that is not a mark
it sets `_anchorX = drawX + originX + own` (`engines/scumm/hires_text.cpp:1356`),
where `drawX` includes the slack it adds to centre a glyph in a game cell
(line 1354) and `own` is the glyph's own advance (its source's advance, else
its metrics advance), which need not be what the pen moves by. A mark with no
anchor on its row yet is drawn at the pen less `originX` there too
(line 1328).

## ScummVM loading (appendix)

How ScummVM loads a face is not part of the format. These sections describe that engine's map keys and are kept for
reference. The portable renderer's API (open a face whole or streamed, draw a line) is `c/include/svf.h`.

### Whole or streamed: the `[load]` section

An SVF is either read into memory whole, or only its tables are (4 and 8 bytes a
glyph) and each glyph is read from the file as it is drawn (a cache of
`HIRES_SVF_CACHE_KB`, a per-line prefetch). By default the size decides: glyph
data up to the threshold is read whole (64 KB, `HIRES_SVF_STREAM_MIN`; the DOS
port raises it to 512 KB, `dos_svf_preload_kb`), anything larger streams. A map
can decide per face instead, because it knows which faces carry the dialogue
every second and which are drawn once, on a title card:

```ini
[fonts]
dlg=NGOTB21A.SVF
card=GBATB23A.SVF

[load]
dlg=whole        ; always in memory, however large
card=stream      ; always read from the file, however small
[load:clut8]
card=auto        ; the size rule again for the 8-bit set
```

The keys are `[fonts]` names (a face is not named by a path here), the values:

| value | the face |
|-------|----------|
| `whole` | is read into memory whatever its size; when the allocation fails it still falls back to streaming |
| `stream` | stays in its file whatever its size |
| `auto` | follows the size rule above; the default for every face the section does not name |

`[load:<qualifier>]` follows the rules of `[fonts]`: the bare section and then
each qualifier, least specific first, so a qualified entry replaces the bare one
for that name (`auto` included, which undoes a bare `whole`/`stream`). The
choice belongs to the file, not the name: two names that resolve to one file
share one loaded face, and if they disagree the first one in the section wins and
a warning says so. A name the map's `[fonts]` does not hold, or a value that is
not `whole`, `stream` or `auto`, is warned about once and means `auto`. A map
without `[load]` loads exactly as before. A jamo-set face (below) honours the
choice as well, as it wraps the same font. SCUMM, SCI and AGI read the section;
AGS loads every face whole and warns that it does not use it. A face reached by
a path in an ini key (`hires_text_face`) rather than a `[fonts]` name is always
`auto`.

### Preloading the glyphs a game draws: the `[preload]` section

A streamed face costs a disk read the first time each glyph is drawn. A map can
say which characters a face is expected to draw, so they are read once, when the
map is loaded, instead of one by one during play:

```ini
[fonts]
dlg=NGOTB16B.SVF
card=GBATB23.SVF

[preload]
dlg=NGOTB16B.HOT       ; characters to keep in memory for this face
card=data:GBATB23.HOT  ; a path next to the map, or data:
```

A `.HOT` file is UTF-8 text: the characters in any order with any line breaks;
a line whose first character is `#` is a comment; whitespace and a byte order
mark are skipped. `tools/korean/charsetchars.py --hot-dir` writes one for every
face of a map from the game's scripts and translation (union of the charsets
whose chain uses the face, plus ASCII); it can be edited by hand. Keys and
qualifiers follow `[load]`: keys are `[fonts]` names, `[preload:clut8]` overlays
the bare section (an empty value drops a list), a face has one list (two names on
one file: the first wins, with a warning), an unknown name is a warning, and a
list file that cannot be read is one warning and no preload. A map without
`[preload]` loads exactly as before.

What the engine does, when it opens a face that streams (`stream`, or `auto`
above the threshold): the face's glyph cache is sized to the list - the stored
bytes of the glyphs of the list that the face has, rounded up to
`HIRES_SVF_READ_BLOCK`, as that many cache entries, never fewer than 32 - and the
glyphs are read into it right away, sorted by their place in the file so that
glyphs in one read block cost one read. After that the cache is the usual LRU one:
a glyph outside the list pushes out the least recently used, which can be a listed
one (read again on its next use). A face held whole ignores the list. A jamo-set
face expands the list's syllables to the pieces the file holds and preloads those.
When the memory for the cache is not there, the face keeps the cache it has, reads
nothing and one warning says so. SCUMM, SCI and AGI read the section; AGS warns
that it does not use it.

The debug socket's `caches all` shows, per face, `list` (glyphs the list named that
the face has), `preloaded` (of those, read at open), `misses` (lookups that were not
hits) and `listevict` (listed glyphs pushed out since); `hits`, `reads` and `read`
count as before from the first draw on, the preload's own reads included in `reads`.
