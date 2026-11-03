# Compact JSET: block version 2 inside SVF v3 — design

Card t_559aeb6a (svf-fonts), 2026-10-23. Written from `spec/SVF.md` (JSET section), `c/src/svf_jamo.c`, `svf_face.c`,
`svf_stream.c`, `svf_internal.h`, `tools/jamoset.py` (`Tables`, `pack`, `unpack`, `pieces_of`, `compose`,
`write_svfn`), `tools/jamoadapt.py`, `tools/svf2to3.py`, `tools/svf_synth.py`, `c/tests/fuzz_open.c`,
`c/bench/v2v3-identity.py`, `c/cross/SIZES.md`, `c/bench/MEASUREMENTS.md`, the SVF v3 design
(`2026-10-21-svf-v3-design.md`) and cards t_559aeb6a and t_5a7bcd78. Every number below marked *measured* comes from
throw-away scripts run over the 95 jamo-set faces of `svf/` at main 4539e42 (the scripts are not kept; the builder's
identity report re-derives the sizes). My own calls are marked **(design call)**.

**User decision (2026-10-23): "JSET 줄이기 진행" — reduce the JSET.** The user cares about MCU flash (an Uno has about
16 KB left after the library) and has accepted P1* growth so far only with explicit sign-off.

**Base and order (controller, 2026-10-23, builder-check answers).** This branch was written at main 4539e42; main is
now beebbff (the SVF maker, card t_a0a737c9, landed: `maker/` reads v3 faces and `maker/detect.py usable_jset()` walks
`jamoset.unpack`'s piece lists). The branch is rebased onto the main that exists when implementation starts. The C
speedups Tasks 6-10 (branch c-speedups, card t_662ef38c, already running) land **first**; this work starts after they
merge, and its before/after baseline is main at that point, not 4539e42: the first measurement step re-takes the
code-size rows and re-checks the estimates below (code size, the divide-removal figure) against that baseline.

## Intent

A jamo-set face stores its JSET block as byte-per-cell set tables and u16-per-slot piece tables. On the shipped
faces that is 652,431 bytes of JSET over 95 faces (*measured*): 11,681 B in each of the 47 adaptive 12 x 12-class
faces (14-20 % of a 60-80 KB face), 1,101 B in each 8x4x4 face, 653 B in the 6x2x1 faces the Uno and Pico benches
embed. The block is read once per syllable (three set numbers, two or three piece numbers), so it can be packed as
long as a lookup stays O(1) and cheap on a Cortex-M0+ and an ATmega328P.

## Goals, non-goals, anti-goals

Goals: the same syllables from a block of roughly half to a quarter of the bytes; the card's two size criteria
(a 32/24/12-set, 8 x 8-class block <= 3 KB; the 8x4x4 2 x 2-class block <= 300 B); no measurable slowdown of a drawn
syllable from a v1 face on the Pico (a v2 face's cost is reported, amendment); code size on M0+ and AVR measured and
inside the gates of the amendment; every shipped face written in the version `auto` picks (superseded by Amendment 3: default 1, `svf/` stays v1), with a pixel-identity proof;
hostile blocks still leave a plain face.

Non-goals: piece bitmaps, glyph records, the cell, the composition rule (maximum coverage), the limits (LC, TC <= 12,
NI <= 32, NM <= 24, NF <= 16), the SVFN v3 header, the header's JSET offset and size fields, and ScummVM's own reader
(it goes away with t_5a7bcd78; its v2 packs are untouched until then) are not changed.

Anti-goals: any pixel change in any syllable, compat jamo or other glyph; a reader that crashes, reads outside the
block or draws from an unvalidated number on a hostile JSET (the opt-in `SVF_JSET_TRUSTED` build of the amendment is
for faces the developer builds into flash, and is never a fuzz or `make check` build); a JSET reader an MCU build does
not use compiled into it (amendment: each build picks its readers by define).

## What was measured, and what it decides

- **Set tables** are LC*21*TC bytes each, holding numbers below 32 / 24 / 16: 5 + 5 + 4 = 14 bits a cell at the
  limits, 13 bits in the 12 x 12 faces (24/16/16 sets), 7 bits in 8x4x4, 4 bits in 6x2x1. Bit-packing (A) is the
  biggest single saving: 9,072 -> 4,914 B in a 12 x 12 face.
- **Piece tables**: 37 of 95 faces already number their pieces in table order (piece k is the k-th non-blank slot of
  initial, then medial, then final sets), so implicit numbering (B) is natural. But 42 faces (every adaptive one)
  **share pieces between slots**: 6,324 shared slots in all, almost all inside one table (the same final piece in
  several final sets, the same medial in several medial sets: NSQRB36A 154 shared slots, SGDAY16 291, NDGPR16 209).
  Numbering every slot afresh would duplicate those glyph records: 302,040 bytes of glyph data against a 371,702 B JSET
  saving over the tree, and NSQRB36A would *grow* (17,912 B of duplicates against 6,453 B saved). So B needs an alias
  escape; its cost must stay O(1) per lookup, which rules out a searched alias list and asks for a bit per slot.
- **compatPiece**: all 4,803 non-blank entries name the piece of **set 0** of the character's own table (a consonant
  with a lead index: initial set 0; the 11 cluster consonants ㄳ ㄵ ㄶ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅄ: final set 0; a vowel:
  medial set 0). The 42 blank entries (NEODG16C) are `--blank-compat` on a face with whole compat glyphs. So a compat
  entry can be one byte naming a set, not a u16 naming a piece.
- **Per-slot reduced axes (C)**: 57 faces (every adaptive one) have all three set tables depending on all three of
  lead class, vowel and tail class; the 38 faces whose tables depend on fewer axes have 42-84-cell tables already.
  C would save 2,000 B over the whole tree (280,729 -> 278,729 B after A+B), 0.7 %. **(design call) C is out.**
- No shipped face carries an unused plane-15 glyph (*measured*: 0), and no face aliases a whole set.

## Format: JSET block version 2

Little-endian; nothing inside the block is aligned, readers use byte reads (`rd8`/`rd16` as today); the block itself
starts on the header's table unit as before. Bits are numbered LSB first within a little-endian byte stream: bit `b`
of a stream is bit `b & 7` of byte `b >> 3`.

```
off  size            field
0    4               "JSET"
4    u16             version = 2
6    1               LC  lead classes (1..12)
7    1               TC  tail classes (1..12)
8    1               NI  initial sets (1..32)
9    1               NM  medial sets  (1..24)
10   1               NF  final sets   (1..16)
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

**Set table.** Cell `c = (leadClass[lead]*21 + vowel)*TC + tailClass[tail]` as today. Field widths come from the counts:
`width(n) = 0` for n = 1, else `ceil(log2 n)` (2 -> 1, 32 -> 5). `WI = width(NI)`, `WM = width(NM)`, `WF = width(NF)`,
`W = WI + WM + WF` (0..14). Cell `c` occupies bits `c*W .. c*W + W - 1`: the initial set in the low WI bits, the
medial set in the next WM, the final set in the top WF. A reader fetches, per field, the two bytes at the field's bit offset `>> 3`,
shifts by the offset `& 7` and masks (a field is at most 5 bits wide and the shift at most 7, so two bytes always
suffice; the byte after the table's end is inside the block, which continues with at least 16 bytes of rows and 51 of
compat). A width of 0 reads as set 0. *(Corrected after the Task 3 review, M3: the text said one three-byte fetch.)*

**Set rows.** One row per set, fixed size per table, so row `s` is at `rows + s*R`. PB is the presence width in
bytes: 3 for initial (19 slots) and medial (21), 4 for final (27).

```
NA = 0:  u16 base | presence PB bytes                                  RI = RM = 5, RF = 6
NA > 0:  u16 base | u16 abase | presence PB bytes | alias PB bytes     RI = RM = 10, RF = 12
```

Slot `j` (initial 0..18, vowel 0..20, tail index 1..27 stored at bit `tail - 1`) is drawn when presence bit `j` is set.
Bits at and above the slot count are padding and must be 0. A set alias bit may be set only where the presence bit
is. The piece of a drawn slot is

- `alias[abase + popcount(aliasBits & below(j))]` when the alias bit is set (NA > 0 only), else
- `base + popcount((presenceBits & ~aliasBits) & below(j))`, where `below(j)` is the mask of bits 0..j-1 and
  `aliasBits` is 0 when NA = 0.

So a set's fresh pieces are `base, base+1, ...` in jamo order, and an alias names any piece by number. `base` and
`abase` are the writer's; the reader never assumes bases are cumulative or disjoint. Pieces are still glyphs at
U+F0000 + number; 0xFFFF is never a valid alias entry (a blank slot is a clear presence bit).

**Compat.** `compat[k]` for U+3131 + k: 0xFF = not drawn by piece; else bits 0-4 a set number and bit 7 a table
switch. The natural table and jamo index of k: k >= 30 is vowel `k - 30` in the medial table; a consonant with a lead
index uses the initial table at that lead; a cluster consonant uses the final table at its tail index. Bit 7 set on a
consonant that has a lead index selects the final table at its tail index instead (bit 7 on a vowel or a cluster is
invalid). The drawn piece is that set's slot for that jamo, which must be present. The reader's constant map for
k = 0..29 (lead index, or `T` + tail index):

```
ㄱ0 ㄲ1 ㄳT3 ㄴ2 ㄵT5 ㄶT6 ㄷ3 ㄸ4 ㄹ5 ㄺT9 ㄻT10 ㄼT11 ㄽT12 ㄾT13 ㄿT14 ㅀT15 ㅁ6 ㅂ7 ㅃ8 ㅄT18 ㅅ9 ㅆ10 ㅇ11 ㅈ12 ㅉ13 ㅊ14 ㅋ15 ㅌ16 ㅍ17 ㅎ18
```

and the tail index of a lead-capable consonant for the bit 7 form: ㄱ1 ㄲ2 ㄴ4 ㄷ7 ㄹ8 ㅁ16 ㅂ17 ㅅ19 ㅆ20 ㅇ21 ㅈ22
ㅊ23 ㅋ24 ㅌ25 ㅍ26 ㅎ27 (ㄸ ㅃ ㅉ have none: bit 7 on them is invalid). One 30-byte table holds both (lead index in
bits 0-4, tail index in a second nibble-packed byte or a second table; builder's choice, about 60 bytes of rodata).

**Size.** `size = 63 + S + NI*RI + NM*RM + NF*RF + 2*NA + 51`. The largest valid block is 12/12 classes, 32/24/16
sets, NA = 1,544 (every slot an alias): **9,246 B**; `SVF__JSET_MAX` is 9246. The streamed face's tables buffer bound (`SVF__JSET_LOAD_MAX`, `svf_stream.c`,
`spec/renderer-design.md`) is the largest block the build reads: 12,321 (the largest v1 block) when `SVF_JSET_V1` is
compiled, 9,246 in a v2-only build (amendment).

| geometry (classes; sets) | today | v2 (NA = 0) | note |
|---|---:|---:|---|
| 1 x 2; 6/2/1 (iolo 6J faces, the bench face) | 653 | 181 | *measured* on 8 faces |
| 2 x 2; 8/4/4 (844) | 1,101 | 272 | card criterion <= 300 B; 28 faces |
| 4 x 4; 10/4/4 | 1,933 | 544 | |
| 8 x 8; 16/8/8 | 5,569 | 1,962 | |
| 8 x 8; 32/24/12 | 7,065 | 2,818 | card criterion <= 3 KB; with aliases 3,170 + 2*NA |
| 8 x 8; 24/16/16 (SGDAY16, NA 291) | 6,641 | 3,472 | *measured* |
| 12 x 12; 24/16/16 (47 faces, NA 42..169) | 11,681 | 5,324 + aliases: mean 5,685, max 5,958 | *measured* |
| 12 x 12; 32/24/16 | 12,321 | 5,782 | the limits, no aliases |
| all 95 shipped faces | 652,431 | 310,160 | 47.5 %, *measured* |

The 32/24/12 criterion holds as stated for a face without aliases; an adaptive face of that geometry carries 352 B
of alias bitmaps and bases plus 2 B an alias, which the card did not know about when it was written. The identity
report records the real number per face; the builder quotes it on the card.

## Reading a syllable (the C v2 reader, `svf_jamo_pieces`)

1. Decompose (the v1-only build keeps its three divisions; a build with both readers decomposes v1 faces with the same multiply-shifts, amendment and Task 3 review M3): `s = cp - 0xAC00`; `lead = (s * 14267) >> 23`; `r = s - lead*588`; `vowel = (r * 2341) >> 16`;
   `tail = r - vowel*28`. **(design call)** The two multiply-shifts replace the three software divisions
   (`__aeabi_uidiv`/`uidivmod` on M0+, 32-bit helpers on AVR); both constants are exact over all 11,172 syllables
   (*verified by exhaustive check*; the builder's unit test repeats it). This belongs in this card because the
   packed lookup costs cycles and the Pico `syl_ga` line has 71 cycles of headroom (below).
2. Cell `c` from the class tables; one two-byte fetch per field (at most 5 bits wide), a shift and a mask give each of the three set numbers.
3. For the initial, medial and (tail != 0) final: the row at `rows_t + set*R_t`; presence word (PB bytes); clear bit
   -> `SVF_PIECE_BLANK`; alias bit -> alias table entry; else `base + popcount` of the masked fresh bits. Popcount of
   a value below 2^27 is a 16-entry nibble table (`SVF_JSET_POP4`, default 1, 0 under `SVF_SMALL`: +24 B, about 90
   fewer instructions a 3-piece syllable on M33) or, with the switch 0, clearing the lowest set bit in a loop; not
   libgcc's `__popcountsi2` (amendment).
4. Compat: index k, the 30-byte map, the set from `compat[k]`, then step 3 for that one slot.

`svf_compose`, `svf__merge`, `svf__composed`, metrics and the chain are untouched: they consume piece numbers.

## Validation (hostile input: everything below is `SVF_FACE_JSET_BAD`, a plain face, never an error)

In this order, every check reading only bytes the earlier checks have bounded: (1) length >= 16, magic, version == 2,
the five counts inside the unchanged limits, reserved u16 == 0, NA <= NI*19 + NM*21 + NF*27; (2) length == the size
formula; (3) `leadClass[i] < LC`, `tailClass[i] < TC`; (4) every cell's initial set < NI and medial set < NM, final
set < NF only in cells of a tail class some tail 1..27 belongs to (today's rule); (5) every row: padding bits of
presence and alias 0, alias bits a subset of presence bits, `abase + popcount(alias) <= NA`; (6) every drawn slot
resolves to a piece number < 0xFFFF (computed in 32 bits: `base + rank` can exceed u16) whose glyph exists
(`svf__glyph_index(SVF_PIECE_BASE + piece) >= 0`), alias entries included; (7) every compat byte is 0xFF or names a
set below its table's count, with bit 7 only on a lead-capable consonant, and that set's slot for the character is
present. Counts are recorded in the face only when all pass (`svf__jset_check` as today). Only a JSET range outside
the file or inside the header stays `SVF_E_RANGE`. `jamoset.unpack` applies the same rules with a `ValueError` naming
the field. `jamoset.unpack` reads both versions (the version word dispatches; a v1 block keeps today's rules);
a C build refuses (plain face) a version it does not compile.

## Amendment 3, 2026-10-24: v2 only on request, for memory-constrained targets (user decision)

The user decided: "V2는 메모리 부족한 것에서만 쓰는 것으로" and chose "기본 v1, v2는 요청 시만". This replaces the
writer default of the 2026-10-23 amendment (`auto`):

- **v1 is the standard format; v2 is an exception-only format** (user: "예외적으로 쓰는 모델로 정하자"): used only when a
  target's memory forces it, chosen per build/pack, never as a default anywhere.
- Every writer, `tools/svf2to3.py` and the maker default to `--jset-version 1`. `2` and `auto` are explicit options used
  when building a face or pack for a memory-constrained target.
- `svf/` stays v1 (no repository-wide conversion). The identity proof and the v2 measurements run on v2 copies generated
  under `c/build/`; the fuzz corpus still holds both versions.
- The maker keeps an uploaded face's version; converting to v2 (or back to v1) is an explicit choice.
- Readers are unchanged (AVR v1 only, every other target both), so a v2 pack made for a small target opens everywhere
  except builds that leave `SVF_JSET_V2` at 0: AVR by default, and the CH582 port (pinned to v1 because it embeds a v1
  face).

## Amendment 2026-10-23: both versions stay, chosen by define and per face (user decisions)

Task 3 measured the v2-only C reader at +616 B on Cortex-M0+ P1/P1* and +570 / +638 B on AVR P1 / P1*; on an Uno with
one small (6x2x1) face that is 100-170 B worse than v1, and AVR P4 no longer links. The user decided (2026-10-23):
"AVR은 define으로 선택하게 하자. 작은 폰트는 v1으로 하고 큰폰트는 v2로 가면 될듯. 트레이드 오프가 있으면 그때 그때
선택하게 하자." After the shrink pass (7a8c2d6, numbers below) the user chose the defaults, the popcount table and a
trusted-faces switch (decisions 2-4). This amendment replaces design call 2's "readers accept version 2 only; version 1
is retired" and every section below that followed from it.

**Decision 1: both versions stay; readers by define, writers per face.**

- **Both JSET block versions are valid in SVFN v3.** The block's own version word says which one it is.
- **Readers choose by define.** `SVF_JSET_V1` and `SVF_JSET_V2` (each 0/1, public, in `svf.h`'s "Size switches" block)
  compile the v1 and the v2 reader; a face whose version the build does not read opens as a plain face
  (`SVF_FACE_JSET_BAD`), never an error. At least one must be 1 (both 0 is a compile error; `SVF_NO_JSET`-style removal
  is out of scope). `jamoset.unpack` (Python) always reads both.
- **Writers choose per face.** Every writer takes `--jset-version 1|2|auto` (default `auto`) (superseded by Amendment 3: default 1, `svf/` stays v1). `auto` writes v2 when the
  face's v1 block is at least `JSET_V2_MIN_SAVING` bytes larger than its v2 block (1024 B, about the v2 reader's code
  cost plus margin; a named constant in `tools/jamoset.py`), else v1. `--jset-version 1|2` forces a version; the choice
  and both block sizes are printed. The converter (`svf2to3.py`) and the maker upgrade a v1 block only when `auto` (or
  `--jset-version 2`) says v2; they never turn a v2 block back into v1 unless `--jset-version 1` is given.
- **What `auto` does to `svf/`** (superseded by Amendment 3: default 1, `svf/` stays v1) (*measured* at 7a8c2d6 over the 95 jamo faces, throw-away script): 58 faces go v2
  (the 47 12 x 12 faces, 10 8 x 8 faces, 1 8 x 4 face: 300,898 B of JSET), 37 stay v1 and byte-identical (28 844 faces,
  8 6x2x1 faces, 1 7/2/2 face: 36,797 B). Total 337,695 B against 652,431 B today (all-v2 would be 310,160 B).
- Trade-offs (a face near the threshold, a target over a budget) are decided by the user case by case.

**Decision 2: reader defaults per target.** On AVR (`__AVR__`) `SVF_JSET_V2` defaults to 0 (v1 only); every other target
defaults to both. Either is overridable with `-D`. The Uno example and the CH582 port build with an explicit `-DSVF_JSET_V2=0` and a v1
face.

**Decision 3: popcount table.** The v2 reader's 16-entry nibble popcount table (`SVF_JSET_POP4`, +24 B on M0+, about 90
fewer instructions a 3-piece syllable on M33) is on by default and 0 under `SVF_SMALL` (in the "Size switches" block,
like `SVF_GRAY8_LUT1`; an explicit `-DSVF_JSET_POP4=1` wins over `SVF_SMALL`). The name is the builder's choice.

**Decision 4: trusted faces.** `SVF_JSET_TRUSTED` (default 0: validation on) skips JSET validation: the check keeps only
what the lookup needs to dispatch (magic, version, the counts and derived widths it records) and returns. `svf.h` warns
that it is only for faces the developer builds into flash: a hostile or corrupt JSET then reads out of bounds. Fuzz
builds and `make check` always validate (a fuzz harness compiled with it is a compile error); tests also build it and
prove that valid faces (v1 and v2) draw identically with and without it.

**Measured (Task 3 shrink pass, 7a8c2d6, `build-all.sh` flags, text bytes, delta to BASE c592140).** Popcount by bit
clearing (no table yet), the v2 reader with the multiply-shift decomposition (Task 4), v1 keeping its divisions.

| reader build | M0+ P1 | M0+ P1* | AVR P1 | AVR P1* | AVR P4 (ATmega328P, 32 KB) |
|---|---:|---:|---:|---:|---|
| BASE (v1 reader) | 6194 | 9190 | 12914 | 20986 | links, 62 B free |
| v1 only (`SVF_JSET_V2=0`) | 6146 (-48) | 9142 (-48) | 12910 (-4) | 20982 (-4) | links, 70 B free |
| v2 only (`SVF_JSET_V1=0`) | 6710 (+516) | 9706 (+516) | 13394 (+480) | 21534 (+548) | over by 640 B |
| both | 7418 (+1224) | 10414 (+1224) | 15278 (+2364) | 23350 (+2364) | over by 2574 B |
| scratch: v2 only, no validation | 6164 (-30) | 9160 | 12518 (-396) | 20658 | links, 372 B free |

The trusted switch saves (scratch, against the rows above) M0+ / AVR P1: v1 only -384 / -900, v2 only -546 / -876,
both -882 / -1736. Validation cost per rule in the v2 reader, M0+ / AVR: length 36 / 40, classes 100 / 132, cells
118 / 176, rows and pieces 160 / 176, alias entries 48 / 32, compat 44 / 110. Speed (Cortex-M33 QEMU instructions,
-Os MONO_PAGE): a 3-piece composition costs 380-470 more instructions from a v2 face than from a v1 face (+25-31 %:
`syl_ga` 3303 -> 3482, `syl_bwelk` 3868 -> 4322, `screen32` 102,730 -> 113,615); the nibble table gives back about 90.

With decision 2 the default builds are: AVR = the v1-only row (P4 links); every other target = both (M0+ P1 7418 + the
24 B table, inside the 8,192 B budget). Task 4's multiply-shift decomposition is in the v2 reader (and, in a build with both readers, applied to v1 faces too): in the v1-only
reader it saved 16 B on M0+ but cost 54 B on AVR, which breaks the v1-only rule below, so the v1-only build keeps its divisions (Task 3 review M3).

**Size gate (replaces the +200 B P1* stop).**

- A v1-only build stays within +20 B of BASE on M0+ and AVR (now -48 / -4). This is the only automatic gate.
- The default-per-target builds (AVR v1 only, M0+ and the rest both, table on) are reported and become the
  `c/cross/SIZES.md` main rows; the V1-only, V2-only, both and trusted variants are reported as "Size switches" rows.
- Anything over a budget (M0+ P1/P2 8,192 B) or a link that stops fitting (AVR P4 in any default build) is a user
  decision, reported on the card with the rows; it is not fixed by the builder on its own.

**Cycle gate.** The Pico rows (`syl_ga`, `syl_bwelk`, `screen32`, MONO_PAGE `-Os`) are measured on the default build for
a v1 face (the bench face, which `auto` keeps v1; now simply v1 by default: must be <= BASE) and for the same face forced to v2 (reported). A v2
row over BASE is a report-and-ask point, as is any Uno or DOS row slower than BASE (the DOS bench face PAPLG18 goes v2
under `auto` (superseded by Amendment 3: default 1, `svf/` stays v1)).

**What changes in the rest of this design.** Design call 2 is amended below; the Migration, Measurements, Tests and
Tools sections now describe both versions. Rejected parts of the original call that stay rejected: none — the dual
reader's cost (estimated 300-500 B in that call, measured +1224 B M0+ / +2364 B AVR) is opt-in per build.

## Design calls

1. **JSET block version 2 inside SVFN v3.** The block has its own version field and the SVFN header does not change
   (flags bit 1, offset 36, size 40 as before). A new SVFN version would make every reader refuse files whose glyph
   records it reads fine.
2. **Both block versions are read and written; the build and the face choose (amended 2026-10-23, see the
   amendment).** C readers are compiled by `SVF_JSET_V1` / `SVF_JSET_V2` (AVR default v1 only, every other target
   both); a version the build does not read opens plain. Writers pick per face with `--jset-version 1|2|auto`.
   (Originally: v2 only, v1 retired; the dual reader's measured cost, +1224 B M0+ / +2364 B AVR in the both build,
   made it a per-build choice instead.) SVFN v3 has not been distributed, so no compatibility promise forces either
   way. **The maker** keeps an uploaded face's JSET version (Amendment 3; originally it kept the version unless `auto` said v2);
   v2 only through the explicit `--jset-version`, and it then converts the face through
   `svf2to3.py --check`, the way it already converts an SVFN v2 upload (`maker/routes.py _svf2to3_argv`,
   `_svf_version`); it never treats a face with a valid v1 or v2 JSET as precomposed (`maker/detect.py` reports the
   JSET version beside `usable_jset()`). **`jamoset.unpack` keeps its public return shape** for both versions: a
   `Tables` whose `init_piece`, `med_piece`, `fin_piece` are resolved per-slot piece-number lists (`BLANK` for a clear
   presence bit) and whose `compat` is 51 piece numbers (`BLANK` for 0xFF), so `maker/detect.py usable_jset()`,
   `svfline`, `svf_synth`, `bdfface` and scummvm-korean's `tools/korean/facecoverage.py` keep working unchanged; the
   packed v2 encoding (widths, rows, bases, aliases, compat set bytes) is internal to `pack`/`unpack`. `pack` resolves
   the lists back into rows and aliases (first occurrence fresh, later ones aliases) and returns the renumbering map as
   described under Migration; `pack_v1` stays as the v1 writer.
3. **A + B in, C out** (measured above). Within B: explicit per-set bases (no prefix popcount beyond one row, no
   RAM table in `svf_face`), alias bits plus a u16 alias table (sharing kept, O(1) lookup), rows gated by NA so a face
   without aliases pays nothing.
4. **Compat as a set byte** with the home-table rule and the bit 7 switch; the 51 u16 table was the largest item of a
   small face after A + B (102 of 320 B), and the reader's map is about 60 B of flash.
5. **Interleaved cell fields** (the three sets of a cell side by side, one two-byte fetch each) rather than three packed tables.
6. **Division removal in the same card**, measured separately from the format so the format's own cost is on
   record. In the v2 reader (a1a3430), which a build with both readers also uses for v1 faces: the v1-only build keeps its divisions (AVR +54 B otherwise, amendment; Task 3 review M3), and
   libgcc's divide routine stays in P1 for `svf_draw_utf8` (Task 1 ruling J1-C1).
7. **No alignment rules inside the block.** Byte reads only; the block's start keeps the header's table-unit rule.

Rejected: a 1-byte relative piece index per slot (no popcount, but 560 B for the 844 block, over the criterion, and
aliases still need an escape); a searched alias list (about 9 probes per alias lookup, 3 lookups a syllable, a
measurable regression); nibble/byte set fields (3,360 B of set table for 32/24/12 at 8 x 8, over 3 KB); deriving compat
without a table (cannot express `--blank-compat`); a build switch that refuses alias faces (the alias path is about
40 B).

## Migration

*[Superseded in part by Amendment 3: the writers' default is 1 and `svf/` is not regenerated; the identity proof runs on v2 copies under `c/build/`.]*

- **Converter.** `tools/svf2to3.py` gains `--jset-version 1|2|auto` (default `auto` (superseded by Amendment 3: default 1, `svf/` stays v1)) on both its paths (an SVFN v2
  input, whose block is v1, and an SVFN v3 input). A v1 block is upgraded to v2 only when `auto` or `2` says so; a v2
  block is turned into v1 only with `--jset-version 1` (`unpack` then `pack_v1`; piece numbers kept). The upgrade walks
  the piece tables in order (initial sets, medial, final; set by set, jamo by jamo), gives each first-seen piece the
  next number and makes each later occurrence an alias to it, sets `base[s]` to the running count at the row's first
  fresh slot and `abase[s]` to the alias count at the row start, encodes each compat entry as the set of its home table
  whose slot holds that piece (the bit 7 form when only the final table of a lead-capable consonant holds it), and
  **refuses** with a message naming the code point when no set does (no shipped face hits this: measured). Plane-15
  code points are renumbered by the resulting map; unused plane-15 glyphs (none today) follow after the last fresh
  number in their old order; glyph record bytes do not change. `--check` compares, through `svfline.Face`, every
  non-plane-15 glyph by code point (has, metrics, cell), every composed syllable U+AC00..U+D7A3 and compat
  U+3131..U+3163, and the plane-15 records as a sorted multiset. The v1 codec (`pack_v1`, `_unpack_v1`) stays in
  `jamoset.py`.
- **One writer path.** `jamoset.pack_jset(t, version)` (`version` 1, 2 or `"auto"`) returns the block together with the
  old-to-new piece map (the identity for v1); `write_svfn` and every caller (`jamoset` build paths, `jamoaa`,
  `jamovec`, `bdfface`, `svfdy`, `svf_synth`, `tools/build/iolo_jset.py`, the bake scripts) take `--jset-version` and
  apply the map to their glyph lists through one helper, so a block and its glyphs can never disagree. `auto` uses
  `JSET_V2_MIN_SAVING = 1024`. `jamoadapt`'s `check` compares resolved slot glyphs, not piece numbers.
- **Regenerate** `svf/` in one commit (superseded by Amendment 3: default 1, `svf/` stays v1) (`svf2to3.py --tree svf svf --check`, default profile, `auto`): 58 faces become v2,
  37 stay v1 and byte-identical (amendment), then the test fixtures (`tools/testdata`, `web/test`, the fuzz corpus)
  and the bench face (`c/bench/mkface.py`; HGKEY6J stays v1, so its pixel checksums and size do not move).
- **Identity proof**, the v2v3 pattern: `c/bench/jset2-identity.py` (from `v2v3-identity.py`), the old `svfdump-asan`
  built from BASE into `c/build/jset1/`, the new one from the branch (default build, both readers); per face it
  compares `info` (both `jamo=1 jset_bad=0`), the `syllables` dump, the `line` dumps of all `LINE_TEXTS`,
  non-plane-15 glyphs by code point and plane-15 records as a multiset, and records the JSET version, v1 and new
  bytes; output `c/bench/JSET2-IDENTITY.md` with a total line (95 jamo faces, 0 different; faces and JSET bytes per
  version: v1 37 / 36,797 B, v2 58 / 300,898 B). A second pass runs the v2-only build over the v2 faces and the
  v1-only build over the v1 faces, so each single-reader build is proven on the faces it reads.
- **Spec and docs.** `spec/SVF.md`: the JSET section documents both block versions (v1 as today, v2 from this design's
  "Format" and "Validation"), the reader switches and the writers' `--jset-version`; no "Retired" paragraph.
  `c/include/svf.h` and `svf_internal.h` comments, `SVF__JSET_MAX` and `SVF__JSET_LOAD_MAX`; `spec/renderer-design.md`
  (the bound: 12,321 with the v1 reader, 9,246 v2 only); `docs/tools.md` (`svf2to3.py`, `jamoset.py`,
  `svf_synth.py` kinds, `--jset-version`); `web/README.md` if it states JSET sizes. The research copies of
  `jamoset.py` under `research/` are frozen and stay.
- **ScummVM.** Nothing now; card t_5a7bcd78 already notes the raised set limits and will rebuild the packs through
  the C renderer (with the readers its targets choose). scummvm-korean's `tools/korean/facecoverage.py` reads faces
  through `jamoset.unpack` and needs no change because `unpack`'s return shape is kept for both versions.
- **Maker.** `maker/detect.py` records the JSET version of an uploaded v3 face; `maker/routes.py` runs
  `svf2to3.py --check` on a v3 face with a v1 JSET only when `auto` says v2 (superseded by Amendment 3: the maker keeps an uploaded face's version; v2 only through the explicit `--jset-version`) (as it does on an SVFN v2 upload), and
  otherwise keeps the face's version; `maker/test` covers a small v1 upload kept v1, a large v1 upload converted to v2,
  and the `svf-jamo` classification of both.

## Measurements and acceptance

*[Superseded in part by Amendment 3: the v2 rows are measured on v2 copies generated under `c/build/` and on a face forced to v2; `svf/` stays v1.]*

Before/after at the baseline (BASE c592140, main after the C speedups merged) and the branch head, the same
toolchains and scripts as `SIZES.md` and `MEASUREMENTS.md`. **Order**: the C reader change (`svf_jamo.c` and its tests
on synthetic v2 faces) is measured for code size and cycles **first**, before the tree regeneration and the tool
migration, so a stop for the user's ruling comes early and cheaply:

1. **JSET bytes**: the identity report's columns, per version; the two card figures from `jamoset.jset_size` in a unit
   test (8 x 8, 32/24/12, NA 0 = 2,818 B; 2 x 2, 8/4/4 = 272 B).
2. **Code size** (`c/cross/build-all.sh`, which runs `check-sizes-md.sh --switches`): the default-per-target rows
   (AVR v1 only; M0+ and the rest both, popcount table on) and the variants V1-only, V2-only, both, trusted and
   `SVF_SMALL`. Gates per the amendment: the v1-only build within +20 B of BASE on M0+ and AVR; M0+ P1/P2 <= 8,192 B and
   every link that fits at BASE (AVR P4) fitting in the default build, else the user decides. The Uno net figure is
   reported.
3. **Uno fit** (`run-avr.sh`): flash total (27,434 B at BASE: code 18,718 + face 8,716) before and after; the bench face
   stays v1 under `auto`, so the face does not shrink; the code may (v1-only, -4 B).
4. **Cycles** (`run-pico.sh` all six builds, `run-avr.sh`, `run-dos.sh`; ESP32/M33/RP2350): `syl_ga`, `syl_bwelk`,
   `compose_bwelk`, `screen32`, `line8`, every checksum `ok` (the sums are the pixel proof on hardware emulators). Pico
   MONO_PAGE `-Os` on the default build: from the v1 bench face <= BASE (6,143 / 7,500 / 194,583, ruling R2); from the
   same face forced to v2, reported, with a report-and-ask point when over BASE. Uno (v1 only) not slower; DOS
   `line40_mapped` / `line40_stream_warm` (PAPLG18 becomes v2) reported against BASE, report-and-ask when slower.
5. **Gates unchanged in meaning**: `make -C c check` (ASan/UBSan, no-malloc, the target masks; validation always on),
   `tools/test_*.py`, `web/test/check.mjs`, `vesa-shots` PNGs identical, `build-all --ports`.

## Tests and fuzz

- `svf_synth.py --jset-bad` keeps its kinds (the `version` kind now writes 1 on a v2 body, plus `version3`) and adds:
  `na_over`, `reserved`, `length`, `pad_bits`, `alias_no_presence`, `abase_over`, `alias_blank`, `base_wrap`,
  `initset` (initSet = NI, which a field can hold only when NI is not a power of two: HGKEY6J has NI = 6) and `finset`
  (NF widened to 3 first, then finSet = 3: the largest value a 2-bit field holds; both are bad kinds only on such a
  count, Task 3 review M6), `compat_set_over`,
  `compat_slot_blank`, `compat_bits56`, `compat_vowel_bit7`, `compat_tt_bit7`, `compat_pp_bit7`, `compat_jj_bit7`,
  `compat_cluster_bit7`, `missing_alias_piece`; `jset_size`, `jset_zero` as today. `test_c_renderer.py` takes each as
  `jset_bad=1` on a face that opens plain, mapped and streamed alike, in the default, v2-only and v1-only builds.
- The v1 bad kinds keep running against the v1 reader (`svf_synth --jset-version 1`), so both readers' validation is
  covered.
- Positive cases: a face with NA > 0 (NSQRB16) and one with NA = 0 (HGKEY6J forced v2) in `test_c_renderer.py`
  composing all 11,172 syllables against `svfline`; the same faces in v1; a face with a bit 7 compat entry written by
  `svf_synth`; width 0 tables (6x2x1).
- **Trusted switch**: a `-DSVF_JSET_TRUSTED=1` build draws every valid variant and the real v1 and v2 faces identically
  to the validating build (syllables and glyph dumps); no bad kind is run against it.
- **Fuzz**: `c/tests/fuzz_corpus.sh` reseeds from the faces of both versions (NSQRB16 and a 6J face in each version, so
  alias, width-0 and v1 paths are hit) and the bad kinds; the fuzz harnesses refuse to compile with `SVF_JSET_TRUSTED`;
  `make fuzz` and `make fuzz-rd` for at least an hour each under ASan; `fuzz_replay.py` over the saved corpus stays
  in `make check`. `exercise()` already composes hash-picked syllables and every compat jamo, which covers both
  readers; the digest rules (mapped = streamed, cache = no cache) stand.

## Tools and files touched

`c/src/svf_jamo.c` (both readers, validation, the v2 decomposition, the trusted path), `svf_internal.h`
(`SVF__JSET_MAX`, `SVF__JSET_LOAD_MAX`), `svf_stream.c` (buffer bound), `c/include/svf.h` (the switches
`SVF_JSET_V1`, `SVF_JSET_V2`, `SVF_JSET_POP4`, `SVF_JSET_TRUSTED` and their per-target defaults; comments),
`c/cross/build-all.sh` (variant rows), `c/cross/SIZES.md`, `c/ports/arduino` (`-DSVF_JSET_V2=0`),
`c/tests/fuzz_open.c` (the trusted refusal), `fuzz_corpus.sh`; `tools/jamoset.py` (`pack`, `pack_v1`, `pack_jset`,
`JSET_V2_MIN_SAVING`, `unpack`, `jset_size`, `pieces_of`, `compose`, `check`, `renumber`, `write_svfn`), `jamoadapt.py`
(`check`), `svf2to3.py` (`--jset-version`, converter, `--check`), `svf_synth.py`, `svfline.py` (through `unpack`),
`facecheck.py` and `web/mkindex.py` (through `svfline`; the picker's WASM library rebuilt by `web/build.sh`, both
readers), `tools/test_jamoset.py`, `test_svf2to3.py`, `test_c_renderer.py`, `test_web_picker.py`; `maker/detect.py`
(JSET version in the detected entry), `maker/routes.py` (the explicit-version conversion step beside the SVFN v2 one; was `auto`, superseded by Amendment 3: default 1, `svf/` stays v1),
`maker/test/*`; `c/bench/mkface.py`, `jset2-identity.py`, `JSET2-IDENTITY.md`, `MEASUREMENTS.md`; `spec/SVF.md`,
`spec/renderer-design.md`, `docs/tools.md`.

## What stays for the builder

- Whether the row's presence word is read whole or only up to the slot's byte (the popcount form is decided:
  amendment, decision 3).
- The compat map's exact packing (one or two 30-byte tables).
- Whether `pack` returns the map or takes a pre-numbered `Tables`; the helper that applies it to glyph lists.
- The order of the validation loops when one pass over the rows can do (5) and (6) together.
- The exact M0+, AVR and Uno numbers, and the card comment quoting the alias-bearing 32/24/12 figure.
- `svfdump` output for the new fields (NA, widths) if `info` is to show them.
