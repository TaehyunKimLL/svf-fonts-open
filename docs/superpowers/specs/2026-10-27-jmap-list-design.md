# JMAP-LIST: a sorted exception list over a shared piece pool (JSET version 3, flag LIST) - design

> **Implemented (2026-10-28)** by `docs/superpowers/plans/2026-10-27-jmap-list.md` (card t_455b15cb) on branch `jmap-list`
> (from fa76afb; merged to main as ca86268). Where this design and the plan differ, the plan's rulings (PL-1..PL-16) and the
> user's decisions below win.
>
> Commits (`git log fa76afb..jmap-list`): spec `cc2763a`; Python reference `3ade087` (`Jmap.list_mode`, codec, size,
> `jset_line`), `a7c2825` (`jmap_list` builder); `svf_synth` `41ee204`; Group A fixes `211fe80`, `72b87eb`, `8bf5995`,
> `34cd8ab`; C reader `f33f4b0` (lookup, L-rules, trusted); LIST=0 and RECOG arms `c2cd4fe`, `ac88310`; defaults, feature
> rows, size budgets `50df1a9`; Group B fixes `6733915`, `af339fa`, `57677b2`; tools `ee5db51` (`svfline`, `maker`,
> `svf2to3`, `mkindex`, `macfbit_svf`), `jamoexc.py` `47cc044`; Group C fixes `0d73568`, `ba5c38a`; fuzz seeds and
> `fuzz-nolist` `448b61c`; Task 11: this note, `c/bench/JSET2-IDENTITY.md` section, `c/cross/SIZES.md` record.
>
> Measured LIST rows (text bytes, AVR / Cortex-M0+, `~/.local/bin/heavy sh c/cross/check-features.sh /tmp/feat` ->
> `features: OK`; `check-features.sh` enforces the budgets with `-gt`):
>
> | row | measured | budget |
> |---|---|---|
> | `minimal+JMAP` (LIST on) | 15370 / 7646 | 15532 / 7688 |
> | `minimal+JMAP+nolist` | 15002 / 7398 | 15032 / 7398 |
> | `ksonly` | 13460 / 6822 | 13648 / 6900 |
> | `ksonly+nolist` | 13118 / 6606 | 13148 / 6610 |
> | `minimal+RECOG` | 13238 / 6358 | 13250 / 6366 |
>
> The gated rows did not move (`avr minimal` 12930, `m0plus minimal` 6162, `m0plus default` 7381). The `+nolist` M0+ row has
> **zero headroom**: any byte added to the shared LIST=0 arm or the JMAP reader fails the next gate. No `jlist_` symbol
> survives `-Os` (every `jlist_*` static is inlined, even with LIST on), so `check_absent ... jlist` is vacuous; the
> `+nolist` size rows and `test_jmap_nolist_identical` are the leak guard.
>
> Rulings that deviate from this design (r3) or add to it: PL-1 (LIST default 0 in Tasks 5-6, final default follows
> `SVF_JMAP` in Task 7); PL-4 (kinds `unpack_jmap` passes: `jlist_field_noglyph`, `jlist_field_fffe`,
> `jlist_compat_noglyph`, `jlist_region_max`); PL-5 (whole-glyph numbering above the highest plane-15 code point,
> 0xFFFF refused); PL-6 (budgets enforced by `check-features.sh`, `minimal+RECOG` +40 B is the plan's); PL-9 (a LIST's
> advance is the fallback's byte 11; the fallback is verbatim; a version 3 source or one without a usable JSET is refused;
> a version change re-encodes through `pack_fallback`, numbers kept); PL-10 (the 255 refusal text); PL-11 (`list_big`
> verdicts per build); PL-12 (`jamoexc` takes hex rows only, PNG is a follow-up); PL-14 (`LIST_VARIANTS` and
> `LIST_BAD_KINDS` are separate tuples, `JMAP_VARIANTS` keeps 15 and `JMAP_BAD_KINDS` 23); PL-15 (LIST/4B and LIST/SPARSE
> fail R1' with the existing text); PL-16 (`jamoexc` keeps layout, JSET version and every glyph's metrics); PL-2, PL-3,
> PL-7, PL-8, PL-13 are process or naming rulings. User decisions that stand: N <= 255 stored as one byte; plane 15
> only; LIST=0 builds and RECOG apply the header rules only (R1', L2, L3, R4); 9.11 (no LIST reader without `SVF_JMAP`,
> `-DSVF_JMAP_LIST=1` without it is an `#error`).
>
> Fuzz (Task 10, `448b61c`): 16 LIST variant and 44 LIST bad seeds (60) in the corpus (1136, strict 369); five 1 h
> libFuzzer runs, all clean (no crash, leak, oom or timeout): `fuzz-open` 220,004 execs, `fuzz-open-rd` 104,441,
> `fuzz-open-nojmap` 221,678, `fuzz-open-mcu` 937,504, `fuzz-open-nolist` 181,305.
>
> Why LIST (Malgun study, local Windows-derived data, no byte in git; card t_d3b86fee, `docs/experiments/research-backlog.md`
> R10): the usage-weighted IoU gain per KB of whole-glyph exceptions is .134 as LIST against .045 for a uniform
> allocation, and LIST beats JSET class isolation at every N.
>
> Follow-ups:
>
> - (a) A LIST reader without `SVF_JMAP` (9.11), when an MCU exception face is wanted.
> - (b) ScummVM `jamo_set.h` refuses version 3 until t_5a7bcd78; scummvm-korean `facecoverage.py` must be checked against list mode.
> - (c) Re-run the Malgun study with LIST prices (8 B a recombination, 8 + ~37 B a whole glyph; local, no bytes in git) before the user decides on a Malgun exception face.
> - (d) "POOL fields on SPARSE" (9.6) only if a shared-pool map above 255 is asked.
> - (e) PNG input for `jamoexc` (PL-12).
> - (f) The optional miss shortcut (3.1).
> - (g) Plan wording fix: `face_facts` emits `pool` for a LIST only, and `jmap_mode` lives in `entry['svf']` (next to `jset_version`; `detect.jmap_mode` takes the block bytes since `0d73568`), not at the top level.
> - (h) The zero-headroom `m0plus` `minimal+JMAP+nolist` budget (7398): the next change to the LIST=0 arm or the JMAP reader needs a re-measure and an explicit budget ruling, not a silent bump.
> - (i) A hash or index for LIST misses only if the research R9 micro-benchmark shows the lookup cost matters (a miss costs 13-17 reads, 3.1).
> - (j) `jamoexc` on a dos-style (u16 offset) face: the overflow path exits 1 with a hint (`--profile dos`, or u32/auto offsets); keeping the layout and still adding cells is open.
> - (k) The `check_absent ... jlist` symbol rule and its self test cannot fail on a real build (no `jlist_` symbol survives `-Os`): either give it a target (a noinline check build) or drop it. Until then the `+nolist` size budgets and `test_jmap_nolist_identical` are the real leak guard.


Card t_455b15cb (svf-fonts), 2026-10-27, branch `jmap-list` from main f880976. Written from `spec/SVF.md` ("Version 3:
mapping table (JMAP)"), `docs/superpowers/specs/2026-10-26-jset-limits-design.md` (with its "Implemented" note and
rulings), `docs/superpowers/plans/2026-10-26-jset-v3-jmap-big.md` (Global Constraints, PR-1..PR-22), `tools/jamoset.py`
(`Jmap`, `pack_jmap`, `unpack_jmap`, `jmap_from_tables`, `shift_pieces`, `pack_fallback`), `c/src/svf_jamo.c`
(`jmap_valid`, `jmap_fields`, `jmap_pieces`, `jmap_fallback`, `svf_jamo_pieces`, `svf__composed`), `c/include/svf.h`,
`c/src/svf_internal.h`, `c/src/svf_stream.c`, `tools/macfbit_svf.py`, `tools/svf_synth.py`, `tools/test_c_renderer.py`,
`c/cross/SIZES.md`, `c/cross/check-features.sh`, `docs/tools.md`, and the local Malgun study
`<workdir>/hinting/out/malgun-sets/REPORT.md` with `jmapb.py` / `jmapb2.py` (Windows-derived data: read only, no byte of it
enters the repository). Numbers marked *measured* were read from those files or computed from their formulas today;
*estimate* marks an extrapolation; **(design call)** marks my own call. Design only: no product code, no tests.

Revision 2 (this commit) folds in three reviews of 06e29a7 (Claude, agy, opencode lanes; the ledger is the last section) and
the user's decisions of 2026-10-27: **NS is at most 255, stored as one byte**, and every other open decision of section 9
follows the recommendation given there. Section 9 keeps the decisions as a record, marked decided.

## 1. Intent

**Problem (user, 2026-10-27).** A combination face (JSET version 1 or 2: a few hundred pieces, every syllable composed)
sometimes needs a few dozen exceptions: a whole precomposed glyph for a syllable the pieces draw badly, or a syllable
composed from pieces the face already has but which the set tables cannot select for it. Today the only per-syllable
mechanism is the version 3 JMAP with SPARSE + FALLBACK, and it costs (*measured*, `spec/SVF.md`): a fixed 1,604 B (header
118, rank table 88, bitmap 1,397, pad 1) before the first entry, 3 B per entry, and - because the JMAP's planes and the
fallback's pieces are disjoint number ranges (R-I/R-J: fallback pieces >= PI + PM + PF) - an entry cannot name a piece the
fallback already stores: a recombination of two or three existing pieces must copy them into the planes. The Malgun
study measured the consequence: a 5,112 B jamo-only face plus 36 whole-glyph exceptions is 8,160 B (+3,048 B: 1,712 B of
JMAP block and about 37 B per whole glyph: cmap 8, u16 offset 2, record 4 + rows), and recombination entries "do not pay"
(each needs 2-3 plane copies at 26-38 B).

**Goals.**

- G1 An exception table whose cost is a small constant plus about 8 B per exception, below the SPARSE cost at every
  legal N (section 2.5: the table crossover against 3 B SPARSE entries would be N = 297; the cap is 255).
- G2 Entries name pieces in the face's one piece space (U+F0000 + n), the fallback's pieces included, so a recombination
  costs its entry and nothing else; a whole-glyph exception costs its entry plus one glyph. Limitation: a whole glyph is
  a piece, so it is drawn at dy 0 with the cell's metrics (no dy, no bearing of its own: `check_dy` refuses a piece dy),
  and it must be a plane-15 piece even when the same bitmap exists in the cmap at U+AC00 + s (a LIST hit wins over the
  cmap; nothing in the entry can point at a cmap glyph).
- G3 The fallback JSET block keeps its own piece numbers: the exception face is the original face plus the exception
  glyphs plus a small block in front of its JSET. The writer copies the source face's JSET bytes verbatim (any version);
  only a requested version change re-encodes it, through `pack_fallback` (piece numbers kept), and `blank_compat` on the
  result re-encodes a version 2 fallback the same way (numbers kept, bytes not identical).
- G4 Same reader architecture as the JMAP: one region, one block, one verdict in every build that reads LIST;
  `svf_compose` and the merge untouched; a LIST face loads plain on every reader that does not know LIST. (Builds that
  recognise LIST without reading it apply the header rules only; section 3.2 says which, and section 4 names the
  divergence that buys.)
- G5 Zero bytes in builds without the reader (the minimal Uno build stays at AVR 12930 / Cortex-M0+ 6162 text).

**Non-goals.** No change to the JSET version 1 or 2 formats; no change to the composition rule (OR / maximum); no new
header flag; no full-KS map (that is SPARSE/DENSE's job; section 2.5 shows the table crossover at N = 297, and the user
capped LIST at 255 for that reason); no LIST reader without the JMAP reader (asked as 9.11, not designed).

**Anti-goals.** A second way to express a whole-glyph exception (section 8, alternatives 4 and 5 are rejected for that
reason); a LIST that duplicates the planes (an entry that can mean a plane index in one mode and a piece number in
another); `svf_face` growth (the host struct is at its 96 B cap, `SIZES.md` Task 7).

**Readers and who gets LIST.**

| reader class | today | LIST |
|---|---|---|
| Uno / AVR minimal (`SVF_JSET_V1` only, `SVF_JMAP` 0, `SVF_JMAP_RECOG` 0) | a version 3 block is `JSET_BAD`, plain face | the same: plain face. Gate: `check-features.sh` rows `avr minimal` 12930 and `m0plus minimal` 6162 unchanged to the byte; `m0plus default` 7381 unchanged (`SVF_JMAP` is 0 there) |
| MCU opt-in (`-DSVF_JMAP=1` on Pico / ESP32 / M33 images; `SVF_JMAP_RECOG` builds) | read JMAP | read LIST when `SVF_JMAP_LIST` is 1 (default: follows `SVF_JMAP`, section 4); a RECOG build, or a JMAP build with `SVF_JMAP_LIST=0`, uses a LIST face's fallback (section 4; a streamed region over that build's `SVF__JSET_LOAD_MAX` excepted) |
| host / DOS / WASM / SDL (`SVF_JMAP` 1 by PR-13) | read JMAP | read LIST by default |

## 2. Format

### 2.1 Flags and header

The block is a JSET version 3 block with flag bit 3 set. Nothing before offset 118 moves. **(design call)**: a flag bit,
not a version 4 (section 4 compares).

| offset | size | field (LIST) |
|---|---|---|
| 0 | 4 | `"JSET"` |
| 4 | u16 | version = 3 |
| 6 | u8 | flags: 0x08 **LIST**; 0x04 FALLBACK as today; **0x01 (4B) and 0x02 (SPARSE) must be 0 with LIST**; bits 4-7 zero |
| 7 | u8 | advance (px; 0 = the cell width), as today |
| 8 | u16 | NS, the number of list entries; **LIST range 1..255** (user decision 2026-10-27: the count fits one byte, so byte 9 is 0 in every valid LIST). One field definition for all three modes, one u16 read |
| 10 | u16 x 3 | PI, PM, PF: **must be 0 with LIST** (a LIST has no planes; section 2.3) |
| 16 | u16[51] | compat piece numbers for U+3131 + k: 0xFFFF blank, else a piece number of the pool (section 2.4) |
| 118 | NS x 8 | the entries, sorted by key, strictly increasing: `u16 key, u16 i, u16 m, u16 f` |
| F = 118 + 8 NS | rest | FALLBACK only: a JSET version 1 or 2 block to the end of the region, as today; **F <= 2,158** |

The cap fits the existing header without moving anything: NS stays the u16 at offset 8 (`rd16p(b + 8)` in `jmap_valid`,
`RD(b + 8) | RD(b + 9) << 8` in `jmap_fallback`, `<HHHH` in `unpack_jmap`), its LIST range is 1..255, and
`ns - 1u >= 255u` on that u16 is the whole range test (it rejects 0 and any non-zero high byte in one compare; a reader
reads the low byte alone only after L3 has run). F is at most 118 + 8 x 255 = 2,158,
below every 16-bit bound (`unsigned` arithmetic on AVR is safe; the 16-bit overflow class of r1's F = 118 + 8 x 11,172
is gone), and a LIST region is at most 2,158 + the largest fallback (47,373, version 1 under BIG) = 49,531 < 65,534, so
R4's region cap never binds a well-formed LIST (the 0xFFFF clip rule still applies).

The three modes are mutually exclusive: dense (flags & 0x0A == 0), SPARSE (0x02), LIST (0x08); `0x0A` (both) and LIST
with 4B are reserved combinations and `JMAP_BAD` (R1' below: one test, `(fl & 8) && (fl & 3)`). Bits 4-7 stay reserved,
so R1's mask changes from `0xF8` to `0xF0` plus that test.

### 2.2 The key: syllable index

`key = cp - 0xAC00`, 0..11,171, the same `s` the bitmap, the ranks and every JSET decomposition use. **(design call)**
Rejected: the code point (U+AC00..U+D7A3 fits a u16 too, but every other table in the block is indexed by `s`, and a
reader would subtract 0xAC00 anyway before the fallback); a key space that also covers the compat jamo U+3131..U+3163
(they already have a 51-entry table at offset 16 that answers in one read; adding them as keys would cost 8 B each and a
second range test). Keys are unique in 0..11,171; the count cap (255) is the user's, from the crossover of section 2.5.

### 2.3 Entries and the shared pool

An entry is `key, i, m, f`, each a u16 **piece number** in the face's own piece space: the glyph at U+F0000 + n, the same
space the fallback's piece tables and compat tables use, 0xFFFF = `SVF_PIECE_BLANK` (no piece). This is the version 1
piece-table convention, not the JMAP's 1-based plane index. Semantics:

- The pieces of a hit are `[i, m, f]` when `f != 0xFFFF`, else `[i, m]` (the entry decides the count, as PR-9; `i` and `m`
  may be blank: `svf_compose` skips blank pieces). A whole-glyph exception is `i = the glyph's piece number, m = f =
  0xFFFF`. An entry with all three blank is a deliberately blank syllable (allowed, as an all-zero SPARSE entry is today).
- A "piece" is any glyph at U+F0000 + n, whoever stores it: one of the fallback's set-table pieces, a compat piece, or a
  glyph that exists only for the LIST (a whole precomposed cell, or a new piece variant). The writer numbers LIST-only
  glyphs after the **highest U+F0000 + n code point present in the face's cmap** (not after the highest piece the
  tables reach: `used_pieces` lists reachable pieces only, and an unreferenced plane-15 glyph above them must not be
  overwritten), in sorted-syllable order so the output is deterministic for one exception set (**(design call)**; any
  free number is legal), and the fallback block's bytes are those of the plain face. Piece 0 is an ordinary pool piece
  (the lowest one, in every face `jamoset` writes); only 0xFFFF is blank.
- No planes: PI = PM = PF = 0. The pool needs no plane counts (there is no index-to-number mapping), and R8's "every piece
  below PI + PM + PF has a glyph" is replaced by a check of the numbers the entries and compat table actually name (L7).
  Rejected: allowing planes beside a LIST (two numbering rules in one block; the only gain, contiguous R8, is worth
  nothing at N of a few dozen).
- Field width: u16 everywhere. Compared: (a) 16-bit, 8 B an entry, any piece number, one two-byte read per field;
  (b) 12-bit packed (key 16 + 3 x 12 = 52 bits, 6.5 B -> 7 B with padding, cap 4,095 pieces, a bit decoder: *estimate*
  +60 B of code; saves 1 B an entry, 36 B on the Malgun face); (c) a pool table (u16 pool[NP] + key and 3 x u8 pool
  indices, 5 B an entry + 2 B a pooled piece; 7 B an entry when every piece is distinct, cap 255 pieces, a second table
  to validate). (a) **(design call, decided by the user)**: the saving of (b) or (c) is under 1 B an entry at the N
  where LIST applies.
- Interaction with the fallback: unchanged. A key miss goes to the fallback (if any) through `svf_jamo_pieces`' existing
  `if (n || !f->jset_lc) return n;`; a LIST without FALLBACK composes only what it lists (`svf__composed`, PR-5).
- The fallback's piece numbers are **not** shifted and **not** required to be disjoint from anything: sharing is the
  point. The spec's "writer shifts the fallback's pieces up by PI + PM + PF" is vacuous at PI + PM + PF = 0;
  `pack_jmap`'s overlap refusal is skipped for a LIST.
- Advance: R4's rule stays (the fallback's byte 11 equals the LIST's byte 7). A whole-glyph exception is drawn as a
  piece: into the cell at dy 0, advancing by the JSET advance; its own metrics entry, if any, is not consulted (as for
  every piece), and `jamoset.py check`'s "a piece must not carry a dy" applies to it.

### 2.4 Compat jamo

The 51-entry table stays at offset 16 with pool semantics: blank, or a piece number with a glyph (L5). PR-10 holds: the
LIST's entry wins when not blank, else the fallback's compat, else the cmap glyph. So a LIST face can also give a compat
jamo a whole glyph (or point it at any existing piece) for 2 B. Keeping the table costs 102 B of every LIST block; a
"no compat table" flag would have saved them at the price of a second header layout (decision 9.5: kept).

### 2.5 Sizes

`size = 118 + 8 NS (+ fallback length)`. Block bytes alone (no fallback; *measured* by the formulas of `spec/SVF.md`):

| N | SPARSE 3B | SPARSE 4B | LIST | DENSE 3B |
|---:|---:|---:|---:|---:|
| 5 | 1,619 | 1,624 | 158 | 33,634 |
| 10 | 1,634 | 1,644 | 198 | 33,634 |
| 30 | 1,694 | 1,724 | 358 | 33,634 |
| 36 | 1,712 | 1,748 | 406 | 33,634 |
| 60 | 1,784 | 1,844 | 598 | 33,634 |
| 200 | 2,204 | 2,404 | 1,718 | 33,634 |
| **255 (cap)** | 2,369 | 2,624 | **2,158** | 33,634 |
| 297 (over the cap) | 2,495 | 2,792 | 2,494 | 33,634 |
| 298 (over the cap) | 2,498 | 2,796 | 2,502 | 33,634 |
| 2,350 (over the cap) | 8,654 | 11,004 | 18,918 | 33,634 |

Crossovers of the table formulas (the header is the real 118 B in every column; the cap changes no size): LIST is
smaller than SPARSE 3B for N <= 297 (`118 + 8N < 1,604 + 3N`), than SPARSE 4B for N <= 371, than DENSE for N <= 4,189.
The brief's "list wins below N ~ 800" does not hold: with the brief's 16 B header the break-even against 3 B entries
would be N = 317, with the real header 297. **The user set the cap at 255 from this**, so within the format LIST is
always the smaller table: at the cap 2,158 B against 2,369 (SPARSE 3B), a margin of 211 B that shrinks by 5 B an entry
towards 297. Per exception on top of the table, both forms pay the same for a whole glyph (about 37 B *measured* on the
12 x 17 Malgun face: cmap 8, offset 2 in `mcu-strict`, record 4 + rows; 4 B more with u32 offsets), and only SPARSE pays
for a recombination (2-3 plane copies, 52-114 B each, less where entries share copies).

Worked example, the Malgun face (*measured* base, *estimate* result): 5,112 B jamo-only face (JSET version 1 of 4 x 2
classes, 6/3/1 sets: 1,073 B by the version 1 formula) + 36 whole glyphs: SPARSE form 8,160 B (measured); LIST form
8,160 - (1,712 - 406) = **6,854 B**; a LIST that adds, say, 40 recombination entries on top costs 320 B more (SPARSE:
120 B of entries + 40 x 52..114 B of copies = 2,200..4,680 B more, an upper bound since copies are shared). The study's
full-KS point (2,350 SPARSE entries with private pieces, 17,724 B) is not a LIST case: over the cap, and 18,918 B of
table alone.

**Maximum N: 255** (user decision). Writer rule (section 5): more than 255 exceptions is an error naming SPARSE and its
size (`1,604 + 3 N` B plus plane copies for recombinations); no crossover warning is needed inside the cap (LIST is the
smaller table at every legal N), but the writer prints the SPARSE size beside its own when N >= 200 so the margin is
visible. The former discussion of NS up to 8,177 and the region-bound cap is withdrawn. **What the cap costs:** it is a
table-size argument (whole-glyph lists), not a total-cost one. A face with, say, 300 recombination exceptions would be
smaller as a LIST (118 + 2,400 = 2,518 B, no copies) than as SPARSE (2,504 B of table plus 300 x up to 52..114 B of
plane copies), yet the writer refuses it; its routes are the SPARSE form with copies today, or the future "POOL fields
on SPARSE" flag of decision 9.6 (1,604 + 4 N, no copies). G1 holds for the lists the format admits.

**Alignment.** None needed: byte reads only, as every JSET block (`spec/SVF.md` "Nothing inside the block is aligned").
118 is even, so the keys happen to lie at even offsets, which a future word-reading host could use; not a rule.

## 3. Lookup and validation

### 3.1 Lookup (C, `jmap_pieces` with `fl & 8`)

```
s = cp - 0xAC00;  if (s > 11,171) miss
lo = 0; hi = NS (byte 8; L3 made byte 9 zero at open, so one read)
while (lo < hi): mid = (lo + hi) >> 1; k = rd16(b + 118 + mid * 8)
    if (k == s) hit: i, m, f = rd16 x 3 at +2, +4, +6;  out = i, m[, f when f != 0xFFFF]; return 2 or 3
    if (k < s) lo = mid + 1 else hi = mid
miss -> the fallback (svf_jamo_pieces), as a SPARSE miss today
```

- Bounded reads: every probe is at `118 + 8 mid + 7 <= 118 + 8 NS - 1 < F <= region` (mid < NS) by R4 (length == F, or
  >= F + 12 with a fallback), the same bound a SPARSE entry read has. Under `SVF_JSET_TRUSTED` R1-R4 are kept (PR-20), so
  the search never leaves the region even with trusted contents (unsorted keys only make it miss). L6 reads keys only
  after R4 has bounded NS against the region (not folded into an earlier loop).
- 16-bit cores: with NS <= 255 every quantity is small: `lo + hi <= 510`, the last probe offset is 118 + 8 x 254 + 7 =
  2,157, F <= 2,158, all in `unsigned` on AVR; no `uint32_t` cast is needed for correctness (the implementer may keep
  `jmap_fields`' style).
- Mapped and streamed faces read the same way: a streamed face's tables buffer holds the whole region (every valid
  version 3 region is <= 65,534 = `SVF__JSET_LOAD_MAX` in `SVF_JMAP` builds, `svf_stream.c` `jset_bytes`), so the probes
  are RAM reads, and the tables buffer size does not change for a given face.
- Cost per lookup (byte reads; corrected in r2: a SPARSE **miss** is one bitmap byte, `jmap_pieces` returns before the
  rank): LIST miss `1 + 2 ceil(log2(NS + 1))`: N = 36 -> 13, N = 255 -> 17; LIST hit +6: 19 / 23. SPARSE miss 1; SPARSE
  hit 1 + 2 + up to 31 (popcount run) + 3 = 6..37. So on a LIST + fallback face every non-exception syllable (the common
  case: 99.7 % of them at N = 36) pays 13-17 reads where SPARSE pays 1; LIST is justified by size and by the shared pool,
  not by lookup speed. The reads are RAM or mapped-flash bytes and the search is at most 8 probes; on the host, where LIST
  runs by default, this is not measurable. Who pays it how often: `svf_draw.c` evaluates `svf__composed` before its
  composed-cell cache, and for a LIST **without** fallback (`jset_lc` 0) `svf__composed` is a full `svf_jamo_pieces`
  search, so such a face searches once per drawn syllable on a cache hit and twice on a miss (`svf__composed`, then
  `svf_compose`); `svf_has`, `svf_metrics_of` and `svf_glyph` each search again. With a fallback `svf__composed`
  answers the syllable range without searching, and the cache saves the composition. An optional miss shortcut (read
  `key[0]` and `key[NS-1]` first, 4 reads) helps only when the exceptions cluster; not a format rule.

### 3.2 Validation rules (L-rules; each reads only bytes earlier rules bounded)

| rule | check | status |
|---|---|---|
| R1' | length >= 118, magic, version 3; `flags & 0xF0 == 0`; **with LIST: `flags & 0x03 == 0`** | `JMAP_BAD` |
| L2 (replaces R2) | PI = PM = PF = 0 (R2's `PI + PM + PF >= 1` does not apply to a LIST: the spec text must say so) | `JMAP_BAD` |
| L3 (replaces R3) | byte 8 (NS) in 1..255 and byte 9 == 0; as one test on the u16 at offset 8: `ns - 1u >= 255u`. The existing R3 expression `fl & 2 ? ns - 1u >= 11172u : ns != 11172u` would send a LIST down the dense arm: it becomes a three-way test on `fl & 0x0A` | `JMAP_BAD` |
| R4 | region <= 65,534; F = 118 + 8 NS (<= 2,158); without FALLBACK length == F; with it length >= F + 12, fallback magic, version 1 or 2, advance byte equal; then the fallback well-formed in a build that reads its version | `JMAP_BAD` (a malformed fallback included: one block, one verdict); a well-formed fallback whose reader is not compiled: the LIST stays usable, fallback `JSET_UNREAD` (as today) |
| L5 (replaces R5) | every compat entry is 0xFFFF or a piece number whose glyph exists | `JMAP_BAD` |
| L6 (replaces R6) | keys strictly increasing: `key[j] > key[j-1]` for j >= 1, and `key[NS-1] <= 11,171` (hence every key); read after R4 | `JMAP_BAD` |
| L7 (replaces R7 + R8) | every entry field is 0xFFFF or a piece number whose glyph exists (`svf__glyph_index(SVF_PIECE_BASE + p) >= 0`); 3 NS lookups, in the same pass as L6 | `JMAP_BAD` |

Header rules are R1', L2, L3, R4; content rules are L5, L6, L7. The content rules are what `SVF_JSET_TRUSTED` skips
(R5-R8 are trusted today, PR-20; L6 is safe to trust: a wrong order cannot read out of bounds, section 3.1). Which of
the header rules a build that recognises LIST without reading it applies differs between the two such builds
(section 4, "Builds after LIST"): a `SVF_JMAP=1 SVF_JMAP_LIST=0` build has `jmap_valid` and applies all four, a malformed
fallback included (one verdict, as for SPARSE today); a RECOG build keeps the recognition's own rule set, which never
reads past byte 9 before it has located the fallback. Open
cost of L5 + L7: at most 51 + 3 x 255 = 816 cmap lookups at open (N = 36: 51 + 108), each about 9 probes of 8 B on a
300-glyph face with a sorted cmap; on a face whose cmap is not strictly increasing (`SVF_FACE_CMAP_LINEAR`,
`svf__glyph_index` scans linearly) that is up to 816 x glyph count reads, which the cap keeps below a quarter million
on a 300-glyph face; SPARSE's R8 is `PI + PM + PF` lookups instead. The Python reference `unpack_jmap` raises `JMAP R1`,
`JMAP L2`, `JMAP L3`, `JMAP R4`, `JMAP L6` (L5 and L7 are `parse_svfn`'s, as R8 is), so the existing "first rule the
message names" convention of `svf_synth` holds.

Statuses: a LIST block that fails any rule is `SVF_FACE_JMAP_BAD` (0x20), a plain face; no new status bit. A LIST block
in a build that reads JMAP but not LIST, or in a `SVF_JMAP_RECOG` build, is `SVF_FACE_JMAP_UNREAD` (0x40) with its
fallback used when the header rules pass (section 4); in a build with neither it is `SVF_FACE_JSET_BAD` as every version
3 block is there.

## 4. Compatibility and versioning

**Flag bit, not version 4 (design call).** Both make every reader built before this see a plain face (version 4 is
`JSET_BAD` everywhere; flag 0x08 is `JMAP_BAD` in `SVF_JMAP` and RECOG builds, `JSET_BAD` without them). The flag keeps
one header, one `jmap_valid`, one RECOG parser and one `Jmap` class; a version 4 would duplicate the dispatch in
`jset_version` / `jset_valid` / `jmap_fallback` / `unpack` and the "version 0 or >= 4 is JSET_BAD" text. The spec already
reserves bits 3-7 for exactly this.

**Readers built before LIST.** None is deployed: the JMAP reader exists only on the unmerged, unpushed `jset-limits`
branch and its successors (main f880976 of this tree), ScummVM's own reader refuses every version 3 block until
t_5a7bcd78, and no face in `svf/` has a version 3 block (identity sweep: 153 faces, 95 jamo, 0 with JMAP). So the
back-compat cost of LIST is confined to this tree's own builds: a LIST face is a plain face there, **its fallback
included** (R1 fails before R4 finds the fallback). That is the one real loss against the SPARSE form, which those
builds read whole; it is accepted because nothing ships them.

**Builds after LIST.**

| build | LIST face |
|---|---|
| `SVF_JMAP=1 SVF_JMAP_LIST=1` | read; miss -> fallback |
| `SVF_JMAP=1 SVF_JMAP_LIST=0` | `jmap_valid` runs with its LIST arm reduced to the **header rules** R1' (length >= 118 first), L2 (two u16 compares at bytes 10-15, inside the 118 bytes R1' bounded; this arm skips R2's `!total` test), L3, R4 including the fallback's own well-formedness through `jset_part` (exactly what `jmap_valid` does for a SPARSE block today: `if (!r) goto bad`); the L5-L7 loops are compiled out of this arm. Pass: `JMAP_UNREAD`, the fallback composes as the plain face the LIST face was built from; any header-rule failure, a malformed fallback included: `JMAP_BAD`, plain (one verdict for the header rules). *Estimate* 30-40 B (**decided**, 9.4). The content rules L5-L7 are **not** applied: a block with unsorted keys or a field without a glyph is `JMAP_BAD` in a LIST=1 build and "fallback used" here. This is an exemption like the one the spec grants RECOG builds; the spec text must name `SVF_JMAP_LIST=0` beside it, and "one block, one verdict" is promised for builds that read the block |
| `SVF_JMAP=0 SVF_JMAP_RECOG=1` | `jmap_fallback` keeps **its own rule set and read pattern** (bytes 6-9, then one byte at F + 11 once F + 12 <= region; it never reads bytes 10-15, so a streamed region of 12..117 bytes, which `jset_bytes` loads exactly, is never overrun) and learns three things: the R1' mask and combination test; the three-way R3/L3 (`fl & 8 ? ns - 1u >= 255u : fl & 2 ? ns - 1u >= 11172u : ns != 11172u`; its present `fl & 2 ? ... : ns != 11172u` would send every LIST down the dense arm and refuse it); and `F = 118 + ns * 8` for a LIST (F <= 2,158, since L3 has bounded `ns`). It does **not** gain R1's length test, L2 or R4's exact length: those are not applied to SPARSE there either (`jmap_short`, `jmap_length`, `jmap_zero_pieces` are `JMAP_UNREAD`, plain, in a RECOG build today; verified by the Claude lane with ASan builds), and adding them would change the existing SPARSE recognition or split it into two arms. So in RECOG: `JMAP_BAD` for R1' / L3 / the advance comparison / a region of 0xFFFF; `JMAP_UNREAD`, plain, for a block without the FALLBACK flag or for a streamed region over `SVF__JSET_LOAD_MAX`; `JMAP_UNREAD` + `JSET_BAD` for a region ending before F + 12 or a malformed fallback (the JSET part's verdict, as the spec's "Reader statuses" says); `JMAP_UNREAD` + fallback used for everything else, planes included (`jlist_planes_*` are "fallback used" here, as R2 kinds are for SPARSE). *Estimate* +24..40 B, desktop builds with an explicit `-DSVF_JMAP=0` only (RECOG defaults to 0 on every MCU, `svf.h`), so no gated row moves. The `SVF__JSET_LOAD_MAX` case (12,321 with the version 1 reader and no BIG; 47,373 with BIG): a LIST of 2,158 B over a version 1 fallback larger than 10,163 B is such a region on a narrow streamed build, plain there; mapped faces are unaffected; the Malgun case (1,073 B fallback) is far below |
| `SVF_JMAP=0 SVF_JMAP_RECOG=0` (AVR, MCU defaults) | `JSET_BAD`, plain: unchanged code, 0 B |

**Switch.** `SVF_JMAP_LIST` (new, `svf.h` "Size switches"): 1 compiles the LIST lookup and L-rules inside `#if SVF_JMAP`;
default = the value of `SVF_JMAP` (so the PR-13 positive list gets it, every MCU stays at 0, `SVF_SMALL` 0); `#error`
when `SVF_JMAP_LIST=1` without `SVF_JMAP`; an explicit `-DSVF_JMAP_LIST=0/1` wins. **(design call)** A sub-switch rather
than folding LIST into `SVF_JMAP`: the Pico/ESP32 images that may turn `SVF_JMAP` on later (follow-up (d) of the limits
design) can keep the 200-500 B out; the cost is two more `check-features.sh` rows and a defaults-test column. No new
`svf_face` field: NS is read from the header at each lookup (1 byte), `jmap_flags` already holds the mode. A LIST
reader **without** `SVF_JMAP` (an MCU exception face that skips the rank/popcount/4B code) is not designed here; it would
need `jmap_off` (4 B) in the MCU `svf_face` under that switch and its own header parse, and is asked as 9.11.

**Spec text changes (`spec/SVF.md`, "Version 3").** The table row for offset 8 (u16 NS; LIST: byte 8 NS 1..255, byte 9
zero) and the flags row (0x08 LIST, bits 4-7 zero, the exclusions); the **Limits** sentence "PI + PM + PF >= 1" and R2
gain "dense and SPARSE; a LIST has PI = PM = PF = 0 (L2)"; a LIST paragraph after **Lookup** (the search, pool
semantics, no shift of the fallback, a whole glyph is a piece); **Fallback**'s "must be BLANK or at least PI + PM + PF"
and the `shift_pieces` sentence marked "dense and SPARSE; a LIST shares the pool"; **Validation** gains the L-rules
table, R1's new mask and L3; **Reader statuses** gains the `SVF_JMAP_LIST=0` row and names it beside RECOG in the "one
block, one verdict" sentence; the `SVF_JSET_TRUSTED` paragraph names L5-L7 as trusted; "Which build reads which" gains
`SVF_JMAP_LIST`; the "Sizes" sentence gains `LIST 118 + 8 NS, at most 2,158`. Code comments to follow: `svf.h`
(`jmap_flags` "1 4B, 2 SPARSE, 4 FALLBACK, 8 LIST"; `SVF_FACE_JMAP_UNREAD`'s text gains "or a LIST block without
`SVF_JMAP_LIST`"; the `SVF_JMAP` / `SVF_JMAP_RECOG` switch docs), `svf_internal.h`'s status comment, `jmap_fallback`'s
header comment ("F is below 46,293" stays true: a LIST's F is at most 2,158).

**Mutual exclusion.** DENSE, SPARSE and LIST are three exclusive modes of one block. A face wanting both a dense part and
an exception part over the same fallback cannot have two version 3 blocks (one region); decision 9.6 (no combination)
stands, with the "POOL fields on SPARSE" flag named there as the future route for a full shared-pool map.

## 5. Writer and tools

- `tools/jamoset.py`: `JMAP_FLAG_LIST = 0x08`, `JMAP_LIST_MAX = 255`; `Jmap` gains `list_mode: bool`, and **every**
  method that interprets entries or counts branches on it explicitly at its top (the r1 text "one class, fewer branches"
  understated what the existing code does with PI = PM = PF = 0): `pieces` (today `BLANK if not i else i - 1` would read
  piece 0 as blank; in list mode the fields are piece numbers and only 0xFFFF is blank), `pack_jmap` (today refuses
  `total < 1`, bounds compat by `c < total`, derives `four` from the counts and `sparse` from `ns < 11,172`: in list
  mode it writes flag 0x08, byte 8 = NS and byte 9 = 0, refuses NS > 255 with an error that names SPARSE and its size,
  refuses planes, checks key range and strictly increasing order (it sorts), bounds compat by "a piece number", and
  skips the overlap refusal; `blank_whole_compat` re-packs through `pack_jmap`, so this path is on the ordinary tooling
  route), `unpack_jmap` (`JMAP L2` / `JMAP L3` / `JMAP L6` texts), `init_piece`/`med_piece`/`fin_piece` (what
  `parse_svfn`, `detect.usable_jset` and `used_pieces` enumerate for glyph checks: today `range(0, pi)` and so on, empty
  for a LIST; in list mode the entries' and compat's named pieces plus the fallback's), `jmap_size(ns, four, sparse,
  fallback_len, list_mode=False)`; `jset_line` prints `jset=v3 jmap=BYTES ns=NS list=1 fallback=v1|v2|none`;
  `blank_compat` keeps working (it blanks the LIST's compat and the fallback's; a version 2 fallback is re-encoded by
  `pack_fallback`, numbers kept, G3 qualified); `jmap_from_tables` is unchanged (SPARSE/DENSE from set tables); new
  `jmap_list(face, exceptions)` builds a `Jmap` in list mode from `{s: [piece numbers]}` or `{s: cell bytes}` (a whole
  glyph: a new piece numbered after the highest U+F0000 + n code point in the cmap, in sorted-syllable order) and
  returns the new glyphs. **The fallback block is the source face's JSET bytes verbatim, version 1 or 2** (G3;
  `pack_fallback(t, 1, 0)` equals `pack_v1(t)` for version 1, and a verbatim copy needs no equality at all); a source
  face whose region is itself version 3 (a JMAP of any mode) is refused with a message naming the plain face to start
  from (R4 admits only a version 1 or 2 fallback; `_jmap_fallback_check` would refuse it anyway, this is the clearer
  error). Only an
  explicit `--jset-version` that changes the version re-encodes it, and then through `pack_fallback(t, v, 0)`, which
  keeps the piece numbers (`pack_jset`/`pack` renumber: `pack` builds `piece_map` in order of first sight and returns
  it; on `svf/dos/GOTHB18A.SVF` it renumbers 1,216 of 1,224 used pieces, so entries numbered against the source pool
  would point at the wrong glyphs; r1 prescribed `pack_jset(t, 2)` and was wrong). The larger alias-walk block is the
  price of a version change; the implementer may instead apply the returned `piece_map` to the glyphs, the entries and
  the compat table, as `svf_synth --jset-version 2` does with `renumber_glyphs`, and must then say so and test it.
- `tools/macfbit_svf.py`: nothing to learn (direct mode writes SPARSE; `verify` tests `version == 3` only). A guard that
  `verify_direct` refuses a LIST face with a clear message is enough.
- Consumers (Task 11 precedent, `docs/tools.md`): `svfline.py` (composes through `jamoset.compose` -> `Jmap.pieces`: works
  once `pieces` handles list mode; its usable rule and the "a JMAP-only miss is not composed" line unchanged),
  `maker/detect.py` (`usable_jset`: the usable rule, every non-blank piece glyph present, through the `Jmap` properties
  above; kind `svf-jamo`, `jset_version` 3; add `jmap_mode` dense/sparse/list to its report), `maker/quality.py` (reports
  `"pieces": [t.pi, t.pm, t.pf]` for a `Jmap`, `[0, 0, 0]` for a LIST: report the mode and the distinct pool count
  instead), `maker/zipout.py` (writes `-`: fine), `svf2to3.py` (verbatim copy already; `--check` through svfline; the
  output line `jset=3 jmap=BYTES` adds ` list=1`), `tools/test_svf2to3.py` (constructs `Jmap`s: a list-mode case),
  `web/mkindex.py` (jamo true: no change), `jamoset.py check` (dy rule on whole-glyph pieces), `bdfface.py` and
  scummvm-korean's `facecoverage.py` (read `unpack`'s return: no change if `pieces_of` works). `tools/facecheck.py` is
  **not** a consumer (r1 misattributed it: it checks manifests and map faces and never imports `jamoset`). `jamoset.py`
  itself still writes no JMAP; the exception writer is a new CLI (below).
- `tools/svf_synth.py`: `JMAP_VARIANTS` += `list1` (every 300th syllable, 38 entries: half whole glyphs copied from the
  face's composed cells, half recombinations naming the fallback's pieces; version 1 fallback), `list2` (the same over a
  version 2 fallback whose piece numbers are deliberately non-canonical, e.g. 5, 3, 9 first, so a renumbering writer
  would be caught), `list_nofb` (no fallback), `list_blank` (one all-BLANK entry and one with `i` only), `list_zero` (an
  entry naming piece 0), `list_compat` (a LIST compat entry naming a fallback piece, and a blank one answered by the
  fallback: PR-10), `list_max` (NS 255, no fallback: F = 2,158), `list_big` (over the `limits_big` tables: the LIST part
  readable without `SVF_JSET_BIG`, fallback `JSET_UNREAD`). `JMAP_BAD_KINDS` += `jlist_short` (the `list1` block cut to
  100 bytes: 12..117, so `jset_version` still reads the version word; below 12 bytes is `JSET_BAD` in every build and
  tests nothing of LIST) and `jlist_short_nofb` (the same cut of `list_nofb`: the RECOG verdict differs, below),
  `jlist_sparse` (0x0A), `jlist_4b` (0x09), `jlist_flags` (bit 4), `jlist_planes_i` / `_m` / `_f` (PI, PM or PF = 1),
  `jlist_ns0`, `jlist_ns256` (the u16 NS 256, i.e. byte 9 = 1: L3), `jlist_length` (`list_nofb` one byte longer than
  F),
  `jlist_fallback_short` / `_bad` / `_v3` / `_adv` (R4's fallback branch on the LIST path), `jlist_key_equal`,
  `jlist_key_desc`, `jlist_key_over` (last key 11,172), `jlist_region_max` (65,535), and the R8-type kinds
  `jlist_field_noglyph`, `jlist_field_fffe` (a field of 0xFFFE, the edge next to BLANK, without a glyph) and
  `jlist_compat_noglyph` (valid block, a named piece without a glyph: plain, `JMAP_BAD`; `unpack_jmap` **passes**,
  `parse_svfn` refuses; the Python tests exempt them as they exempt `jmap_missing_piece` today, and the module docstring's
  "every kind breaks a rule of `unpack_jmap`" sentence gains that exception). The module docstring names the rule of
  each; `docs/tools.md` lists them (`tools.test_tools_doc` census). With these the seed count is 2 x (8 variants + 22
  kinds) = 60.
- `docs/tools.md`: the JMAP paragraph (`jamoset` library), the `svf_synth` synopsis and kind lists, the new exception
  writer's section, `svf2to3`/`svfline`/`detect` notes.
- **Exception writer (sketch; the Malgun study would use it):** `tools/jamoexc.py build FACE.SVF EXC.json OUT.SVF`
  where EXC maps a syllable (or compat jamo) to either `{"whole": "path.png|hex rows"}` or `{"pieces": [n, n, n]}`;
  it appends whole glyphs as pieces after the highest plane-15 code point of the cmap (a `"whole"` input with a dy or
  metrics of its own is refused: a piece carries none, G2), builds the LIST with `jmap_list`, keeps the face's JSET
  bytes as the fallback (version kept; `--jset-version` re-encodes through `pack_fallback` as above), refuses more than
  255 exceptions naming SPARSE and its size, prints the SPARSE size beside its own from N >= 200, and reports `jmap=BYTES
  ns=N whole=W recomb=R total=BYTES`. `jmapb2.py`'s greedy (usage-weighted IoU gain per byte) then prices a recombination
  at 8 B and a whole glyph at 8 + about 37 B, instead of 3 + copies; the study's "plane pieces do not pay" conclusion
  should be re-run with those prices (local, no bytes into the repo).

## 6. Reader size and cost per target

*Measured* today (`SIZES.md` "Minimal config", rows at 4ef4398, text bytes): `minimal` AVR 12930 / M0+ 6162;
`minimal+JMAP` 14932 / 7338 (+2,002 / +1,176, rodata 16 for `pop4`); `ksonly` 13048 / 6550; `minimal+RECOG`
13210 / 6326 (+280 / +164). The Task 6 note attributes the JMAP cost to R1-R8 inlined into `svf__jset_check` (~340 B
M0+), the entry decoder (100 B) and the lookup (+228 B).

LIST adds (*estimate*, by analogy with those parts), in a `SVF_JMAP_LIST=1` build: the binary search and the three
field reads (about the size of the SPARSE lookup branch: M0+ 100..160 B, AVR 170..280 B) and L2/L3/L6/L7 with the flag
tests (M0+ 80..140 B, AVR 130..250 B): **M0+ +180..300 B, AVR +300..530 B over the pre-LIST `minimal+JMAP` row**. In a
`SVF_JMAP_LIST=0` build the fallback-finding branch with its header rules instead: M0+ 30..40 B, AVR 40..60 B (the two
are `#if` arms; r1 summed them into one range). 0 B over `minimal`, `default` (M0+) and every port image (LIST follows
`SVF_JMAP`, which is 0 there). `svf_face` unchanged (host 96 B cap, `-m32` 76 B). Host rows are not gated; expect a few
hundred bytes on `host-gcc P1` and `port-web svf.wasm`, reported.

Measurement plan and gate: `check-features.sh` gains the info rows `minimal+JMAP+nolist` (`-DSVF_JMAP=1
-DSVF_JMAP_LIST=0`) beside `minimal+JMAP` (which now includes LIST by default) and `ksonly+nolist`; the gated rows stay
`avr minimal` 12930, `m0plus minimal` 6162, `m0plus default` 7381, exact. **Both new rows are measured against the
recorded pre-LIST `minimal+JMAP` row (AVR 14932 / M0+ 7338)**, not against each other (the difference of the two would
subtract the LIST=0 branch and understate LIST). The symbol rule gains `check_absent ... jlist` (LIST statics prefixed
`jlist_`) for `minimal`, `default`, `minimal+BIG`, `minimal+BIG+V2` and `minimal+JMAP+nolist` (the existing `jmap`
prefix rules do not match `jlist_`); the defaults rule's `case` gains `minimal+JMAP -> JMAP 1 LIST 1` and
`minimal+JMAP+nolist -> 1 0` (its catch-all would otherwise skip the new switch; the probe prints `SVF_JMAP_LIST` too);
the strings rule is unchanged (no new literal). **Proposed gate**: LIST=1 cost at most **+350 B M0+ / +600 B AVR**
over 7338 / 14932, LIST=0 cost at most +60 / +100; above is report-and-ask (the JMAP reader itself overran its estimate
band by 2.5 x, R-Q; the gate is the top of the band, not the middle). Hot path: Pico MONO_PAGE `-Os` `syl_ga` 6049 /
`syl_bwelk` 7279 / `screen32` 187299 cycles (R-T reference) equal, since `SVF_JMAP` is 0 there; a LIST face's own
composition speed is measured on the host only (a miss costs at most 8 probes, section 3.1).

## 7. Test, fuzz and identity plan

- `tools/test_jamoset.py`: `pack_jmap`/`unpack_jmap` round trip of every `list*` variant; `jmap_size` with list mode;
  the bad kinds raise with the named rule; `compose` of a LIST face equals composing the fallback for every non-listed
  syllable and the listed pieces for listed ones (11,172 + 51); `pack_jmap` refuses planes / 4B / SPARSE with LIST and
  NS 256 (message names SPARSE); the fallback bytes equal the source face's JSET bytes for a version 1 **and** a version
  2 source (G3); a `--jset-version 2` re-encode of a version 1 source with non-canonical piece numbers composes
  identically (the renumbering trap of section 5); `list_zero` draws piece 0.
- `tools/test_c_renderer.py` `TestJamo`: `test_jmap_list_compose` (every `list*` variant: `svfdump syllables` ==
  `jamoset.compose` for 11,172 + 51, mapped and every `STREAM_CONFIGS`, with and without TRUSTED);
  `test_jmap_list_status_matrix`: every `jlist_*` kind and every `list*` variant x the four builds {LIST=1, `SVF_JMAP=1
  SVF_JMAP_LIST=0`, `SVF_JMAP=0 SVF_JMAP_RECOG=1`, neither} with the expected `jmap_bad` / `jmap_unread` / `jset_bad` /
  `jset_unread` / `jamo` values and, where `jamo=1`, whether the listed syllables come from the LIST or the fallback
  (expected per kind, from the real reader paths of section 4: LIST=1: every `jlist_*` kind `jmap_bad=1`, plain.
  `SVF_JMAP=1 SVF_JMAP_LIST=0`: header-rule kinds (`jlist_short`, `jlist_short_nofb`, `jlist_sparse`, `jlist_4b`,
  `jlist_flags`, `jlist_planes_*`, `jlist_ns0`, `jlist_ns256`, `jlist_length`, `jlist_fallback_*`, `jlist_region_max`) `jmap_bad=1`, plain; content-rule kinds (`jlist_key_*`, `jlist_*_noglyph`,
  `jlist_field_fffe`) `jmap_unread=1`, fallback used. RECOG: `jmap_bad=1` for `jlist_sparse`, `jlist_4b`, `jlist_flags`,
  `jlist_ns0`, `jlist_ns256`, `jlist_fallback_adv`, `jlist_region_max`; `jmap_unread=1` plain for `jlist_short_nofb` and
  `jlist_length` (no FALLBACK flag); `jmap_unread=1 jset_bad=1` for `jlist_short` (region ends before F + 12),
  `jlist_fallback_short` / `_bad` / `_v3`; `jmap_unread=1`, fallback used, for `jlist_planes_*` and every content-rule
  kind. Neither: `jset_bad=1` throughout. The two divergences, content rules in both recognising builds and the
  header rules in RECOG, are pinned by this test); `test_jmap_list_big_fallback_by_build` (the `list_big`
  variant: LIST usable, fallback `JSET_UNREAD` without BIG); `test_jset_defaults_per_target` gains the `SVF_JMAP_LIST`
  column (host 1, AVR 0, `SVF_SMALL` 0, explicit wins, `#error` without JMAP); `test_jmap_list_max` (`list_max` mapped
  and streamed: 2,158 B region) and `test_jmap_list_recog_stream_load_max` (a LIST over a version 1 fallback above 10,163 B, e.g. the 11,681 B 12 x 12 class, 24/16/16 set table,
  streamed, in the narrow RECOG build: plain, the documented `SVF__JSET_LOAD_MAX` case; mapped: fallback used).
- Mutation / identity checks: `test_narrow_hot_path_identical` (object code of `-DSVF_JMAP=0 -DSVF_JSET_BIG=0` against
  `HOTPATH_BASELINE`) must still pass with its baseline **unchanged** (no-JMAP code does not move; the RECOG change is
  outside `SVF_JMAP=0 SVF_JMAP_RECOG=0`); a new `test_jmap_nolist_identical`: the `svf_jamo.o` disassembly of
  `-DSVF_JMAP=1 -DSVF_JMAP_LIST=0` against the pre-LIST commit for `jmap_pieces`, `jmap_fields`, `jmap_valid`,
  `svf_jamo_pieces` - expected to differ only in `jmap_valid` where the fallback-finding branch was added (recorded as
  the baseline of that function; the other three identical); `c/bench/jset2-identity.py` over `svf/` in the default
  build: `faces=153 jamo=95 different=0`; `presets.sh build` and `build-all.sh --ports` (43 OK lines) unchanged.
- Fuzz: `fuzz_corpus.sh` seeds every `list*` variant and `jlist_*` kind from HGKEY6J in both profiles (+2 x (8 + 22) = 60
  seeds); runs of one hour each: `fuzz-open`, `fuzz-open-rd`, `fuzz-open-nojmap` (the RECOG path with LIST), `fuzz-open-mcu`
  (must stay plain), and a new `fuzz-open-nolist` (`-DSVF_JMAP=1 -DSVF_JMAP_LIST=0`); the harnesses still refuse TRUSTED.
- Goldens: a synthetic LIST face from `svf/` pieces (no Apple or Windows bytes) composed by Python and C identically; the
  Malgun LIST face is verified locally by the study scripts (`ccheck.py` pattern: `svfdump syllables` == `compose`).

## 8. Alternatives considered and rejected

1. **SPARSE with a coarse rank-only index** (keep the rank table, drop the bitmap, keep 3 B entries, search within a
   256-syllable bucket): 118 + 88 + 3 N plus a key per entry (the bitmap was the key) = 206 + 5 N with u16 keys, 206 +
   4 N with a u8 in-bucket key; cheaper than LIST from N = 30 (u16) or N = 23 (u8), costlier than SPARSE above N = 699.
   Size is not the reason to reject it: its fields are still plane indices, so it has no shared pool (G2) and every
   recombination still copies pieces; and it is a third index structure. Below 255 the binary search needs no index.
2. **A second JSET-style "override set"** (a version 1/2 block whose classes name single syllables): a class per
   exception syllable needs LC x TC cells of 3 x 21 bytes each; 36 exceptions as lead classes alone are 36 x 21 x TC x 3
   = 4,536 B at TC 2. Sets cannot address one syllable without a class, by construction.
3. **Per-syllable override planes**: keep SPARSE and let a field above the plane count mean "fallback piece
   `k - P - 1`": 1,604 + 3 N (3B: fallback pieces up to 254 - P reachable) or 1,604 + 4 N (4B); for N = 36 that is 1,712
   / 1,748 against LIST's 406; keeps the 1,604 B bitmap the exceptions do not need. (Its 4B form is the route for a
   shared-pool map **above the LIST cap**, where no LIST exists: N = 2,350 -> 11,004 B, against 8,654 B of SPARSE 3B
   table plus plane copies; the formula 118 + 8 N would give 18,918 there, but such a LIST is not legal. See 9.6.)
4. **Exceptions as cmap glyphs at U+AC00 + s with a fallback-exempt key list** ("a syllable in the cmap is drawn whole"):
   118 + 2 N plus the glyph (the same 37 B); Malgun 6,638 B (*estimate*, 216 B under LIST: 6 B an entry). No recombinations (the user's
   second case), a precedence change (JMAP-then-fallback-then-cmap becomes cmap-first for listed syllables), and a
   second way to say "whole glyph". No face in `svf/` has a syllable glyph beside a JSET (0 of 95, *measured*), so the
   change would be safe for shipped faces, but it buys 8 B an exception.
5. **A cmap-first precedence rule for every jamo face, no table at all** (a syllable found in the cmap is drawn from it):
   0 table bytes, Malgun 6,448 B (*estimate*), and an old reader degrades to composing the syllable instead of drawing
   nothing. Rejected: it costs a cmap binary search per composed syllable on every jamo face (about 9 probes on a
   300-glyph face), which breaks "JMAP = 0 hot path identical" unless gated by a per-face bit (no free `svf_face` byte on
   the host), and it still cannot express a recombination.
6. **12-bit packed fields** and **pool-indexed u8 fields**: section 2.3 (saves 1-1.5 B an entry, adds a cap and a decoder).
7. **Delta-coded keys** (u8 key deltas, 7 B an entry): no binary search; a miss scans all N (36 reads per
   non-exception syllable) - the common case pays for the rare one.
8. **Version 4 instead of flag 0x08**: section 4 (same compatibility outcome, duplicated dispatch).

## 9. Decisions (decided by the user 2026-10-27 unless marked open)

1. **Key type** - decided: syllable index (0 B, one code path with the bitmap/rank arithmetic; the code point would
   save one subtraction in the writer and cost one in the reader).
2. **Field width** - decided: u16 x 3, 8 B an entry (12-bit packed: 7 B, cap 4,095 pieces, +~60 B of code; a pool
   table: 5 B + 2 B a pooled piece, cap 255). Cost: 1-1.5 B an entry.
3. **Maximum N** - decided by the user: **255** (the u16 NS field kept, LIST range 1..255, so byte 9 is 0). It removes the 16-bit overflow class
   of r1's F, bounds the open cost of L5 + L7 at 816 lookups, and sits under the table crossover (297). The r1
   recommendation (nominal 11,172) is withdrawn.
4. **`SVF_JMAP=1 SVF_JMAP_LIST=0` and RECOG builds** - decided: find and use the fallback; the LIST=0 build after the
   header rules R1', L2, L3, R4, the RECOG build after the recognition's own rules (flags, L3, advance, clip; no length
   test, no L2, as for SPARSE today) (*estimate* 30-40 B and 24-40 B), accepting that the content rules L5-L7 are then
   build-dependent in both, and L2 / lengths in RECOG (section 4 states it; the status matrix test pins it). The 0 B
   alternative (0x08 reserved, plain, no Hangul on an image that left LIST out) is rejected.
5. **Compat table in a LIST block** - decided: keep the 102 B table with pool semantics (one header, compat exceptions
   for 2 B each).
6. **Combining with SPARSE** - decided: no; three exclusive modes. If a full exception map over a shared pool is ever
   wanted (N in the thousands), the right addition is alternative 3's 4B form as a separate flag ("POOL fields" on a
   SPARSE block: 1,604 + 4 N, pieces up to 2,047 reachable), not a larger LIST.
7. **Exception whole glyphs in the cmap instead of plane 15** - decided: plane 15 only (the same 8 B cmap entry either
   way, a second mechanism otherwise, and `svf_compose` would need a non-piece path). Consequence (G2): a LIST entry
   cannot select a cmap glyph at U+AC00 + s; a whole-glyph exception is a pool piece even when that bitmap also exists
   in the cmap.
8. **Name** - decided: `LIST` (flag `JMAP_FLAG_LIST`, switch `SVF_JMAP_LIST`, Python `list_mode`): it names the
   structure, as SPARSE and DENSE do.
9. **Default of `SVF_JMAP_LIST`** - decided: follows `SVF_JMAP` (host/DOS/WASM on, MCUs off).
10. **Writer threshold** - decided, adapted to the cap: more than 255 exceptions is an error naming SPARSE and its size;
    inside the cap LIST is always the smaller table, so no crossover warning exists; the writer prints the SPARSE size
    beside its own from N >= 200 (the margin is 211 B at the cap and visible).
11. **Open (new, from review): a LIST reader without `SVF_JMAP`** for MCU exception faces (`SVF_JMAP=0 SVF_JMAP_LIST=1`,
    today an `#error`). An Uno or Pico image that wants a few whole-glyph exceptions over its derived face would
    otherwise pay the whole JMAP reader first (+2,002 B AVR / +1,176 B M0+, then LIST). A stand-alone LIST reader is
    *estimated* at AVR +350..650 B / M0+ +220..380 B (header parse, the search, L-rules, status) plus `jmap_off` (4 B)
    in the MCU `svf_face` under that switch; the host struct is not involved. **Recommendation: not now.** The Malgun
    exception face is a host/DOS target in the study, the Uno true-minimal work is its own card (t_52f677aa), and
    designing the switch later costs nothing in the format (the block is the same). Ask again when an MCU exception face
    is wanted; the switch doc should say `SVF_JMAP_LIST` needs `SVF_JMAP` "for now".

## 10. Risks, rollout, work breakdown

**Risks.**

- Size of the reader: the JMAP reader came in at 2.5 x its estimate (R-Q); LIST is smaller and simpler, but the gate of
  section 6 is the top of the band, and anything above it is a stop.
- Loss of the fallback on pre-LIST JMAP builds (section 4): only this tree's unmerged builds; acceptable, stated in the
  spec so a face author does not expect SPARSE-like degradation.
- Build-dependent verdicts for the content rules in LIST=0 and RECOG builds (decision 9.4): pinned by the status matrix
  test and named in the spec; a face that passes the Python reference never meets it.
- Open-time cost of L5 + L7 (at most 816 cmap lookups; linear on a `CMAP_LINEAR` face): bounded by the cap.
- Two numbering conventions in one spec (plane index in dense/SPARSE, piece number in LIST), and existing code that
  treats field 0 as blank and PI + PM + PF = 0 as invalid: the main source of reader and tool bugs; every consumer that
  reads `Jmap.entries`, `pi`/`pm`/`pf` or the piece properties directly (not through `pieces`) must be found (`grep` in
  `tools/`, `maker/`, `web/`, scummvm-korean) in the implementation plan's first task; `maker/quality.py` and
  `tools/test_svf2to3.py` are two already known.
- The writer's fallback handling: a version change through `pack`/`pack_jset` renumbers pieces silently; the plan must
  keep verbatim copy as the default and test the re-encode path with non-canonical numbers.
- The Malgun study's benefit is an estimate (6,854 B); the study must be re-run with LIST prices before the user decides
  on a Malgun exception face.
- ScummVM's own reader (`jamo_set.h`) refuses every version 3 block until t_5a7bcd78: a LIST face is plain in the engine
  until then, like every JMAP face.

**Rollout.** Default off everywhere except the PR-13 positive list (host, DOS, WASM, SDL), where `SVF_JMAP_LIST` follows
`SVF_JMAP`; no MCU image changes; `svf/` gains no LIST face (exception faces are per-game packs or local studies); the
spec section lands with the Python reference in the same commit as the C reader's switch doc. No push, no merge of
`jmap-list` without the identity sweep and the one-hour fuzz runs.

**Work breakdown (future plan tasks, titles only).**

1. Spec: LIST mode in `spec/SVF.md` (flags, L-rules, statuses, sizes) and the `docs/tools.md` census entries.
2. `jamoset`: list mode in `Jmap`, `pack_jmap`/`unpack_jmap`/`jmap_size`/`pieces`/`jset_line`/`used_pieces`, `jmap_list`
   builder, tests.
3. `svf_synth`: `list*` variants and `jlist_*` bad kinds; `fuzz_corpus.sh` seeds.
4. C reader: `SVF_JMAP_LIST` switch and defaults, LIST lookup and L-rules in `svf_jamo.c`, the LIST=0 and RECOG
   fallback-finding branches, `svfdump info` fields.
5. `check-features.sh` rows and gate, `SIZES.md` records, `test_jset_defaults_per_target`, hot-path and no-LIST identity
   tests.
6. Tool consumers: `svfline`, `maker/detect`, `maker/quality`, `svf2to3` (+ its tests), `mkindex`, `jamoset.py check` on
   LIST faces.
7. Exception writer `tools/jamoexc.py` and its docs; synthetic golden from `svf/` pieces.
8. Fuzz runs (one hour each, five harnesses), identity sweep, Malgun re-run (local), records and follow-ups.

## Summary

1. LIST = JSET version 3 with flag 0x08: a sorted `u16 key (syllable index), u16 i, u16 m, u16 f` list at offset 118,
   8 B an entry, **NS 1..255 in byte 8 (byte 9 zero)**, binary search of at most 8 probes; fields are piece numbers of
   the face's one pool (the fallback's pieces included; piece 0 is a piece, 0xFFFF blank), PI = PM = PF = 0, the fallback
   unshifted and copied verbatim; header, compat table and FALLBACK as today; F <= 2,158.
2. Sizes: 118 + 8 N; at the cap 2,158 B against SPARSE 3B's 2,369 (the table crossover would be N = 297, SPARSE 4B 371;
   the brief's ~800 is wrong); Malgun 36 whole glyphs: 8,160 -> ~6,854 B (estimate), recombinations 8 B each instead of
   3 B + up to 52..114 B of copies. Lookup: a LIST miss is 13-17 byte reads where a SPARSE miss is 1; LIST wins on size
   and the shared pool, not speed.
3. Rules R1' (mask 0xF0, LIST excludes 4B and SPARSE), L2 (no planes), L3 (NS 1..255, byte 9 zero), R4 (F = 118 + 8 NS),
   L5 (compat has a glyph), L6 (strictly increasing keys <= 11,171), L7 (every field blank or a piece with a glyph); one
   verdict `JMAP_BAD` in builds that read LIST; a LIST=0 build applies the header rules only, a RECOG build the
   recognition's own subset (no length test, no L2), both then use the fallback.
4. Switch `SVF_JMAP_LIST` under `SVF_JMAP`, default follows it; minimal rows unchanged; estimate M0+ +180..300 B, AVR
   +300..530 B over the pre-LIST `minimal+JMAP` row (7338 / 14932); gate +350 / +600; LIST=0 branch +30..40 / +40..60.
5. Pre-LIST readers (this tree only; nothing shipped) see a plain face, fallback included.
6. Decisions 1-10 of section 9 are the user's (2026-10-27); one new question, 9.11 (a LIST reader without `SVF_JMAP`),
   is open with the recommendation "not now".

## Changes since 06e29a7 (review round 1; finding id -> action)

Claude lane: **I1** accepted (section 3.1 rewritten: SPARSE miss is 1 read, LIST miss 13-17; the cache sentence replaced by
the `svf__composed`-before-cache facts; "cheaper" dropped). **I2** accepted (section 4 table and 3.2 name the header rules a
LIST=0/RECOG build applies, the divergence is stated, 9.4 reframed, status matrix test added, spec sentence to name
`SVF_JMAP_LIST=0`). **I3** accepted and made moot by the cap (F <= 2,158; the 8,177 discussion removed; `jlist_ns256` kind
instead of `jlist_ns_wrap`). **I4** accepted (verbatim fallback copy by default; `pack_fallback` on a version change;
new glyphs numbered after the highest plane-15 cmap code point; tests). **I5** accepted as new open decision 9.11 with
an estimate and a recommendation. **M1** accepted (2,200..4,680, upper bound). **M2** accepted (gate against the recorded
pre-LIST row). **M3** accepted (streamed RECOG `SVF__JSET_LOAD_MAX` clause and a test). **M4** accepted (`quality.py`,
`zipout.py`, code comments listed). **M5** accepted (all kinds added; `jlist_ns_wrap` replaced by `jlist_ns256`).
**M6** superseded by the user's cap of 255. **M7** accepted (alternative 1 rejected on G2, u8-key figure added). **M8**
accepted (G3 qualified). **M9** accepted (L6 after R4 sentence).

agy lane: **Important 1** accepted (same as ocd 5: explicit list-mode branches in the `Jmap` properties and consumers).
**Important 2** accepted (same as I4). **Important 3** moot by the cap (816 lookups; linear-cmap case noted). **Minor 1**
accepted (same as M1). **Minor 2** accepted (`facecheck.py` removed from the consumers and the task list). **Minor 3**
accepted (LIST=1 and LIST=0 costs split).

opencode lane: **1** accepted (same as I4; `list2` gets non-canonical numbers and a byte-identity test). **2** accepted
(same as I1; the min/max shortcut noted as optional, not a rule). **3** accepted and moot by the cap (no 32-bit product
needed; said so). **4** accepted (L2 in both branches; `jlist_planes_*` in the status matrix). **5** accepted (explicit
branches in `pieces`, `pack_jmap`, `unpack_jmap`, the properties; `list_zero` variant). **6** accepted (`jlist` prefix
rules on every no-LIST row). **7** accepted (51 compat lookups counted; `CMAP_LINEAR` case stated). **8** accepted.
**9** accepted (`quality.py`, `test_svf2to3.py`). **10** accepted (L3 spelled out; the dense-arm trap named). **11**
accepted. **12** accepted (exempt kinds named; docstring sentence). **13** accepted (rows renamed `+nolist`; defaults
rule cases added). **14** accepted (R2 / "PI + PM + PF >= 1" and `svf.h` comment in the spec-change list). **15**
accepted (2.6 -> 2.5). **16** accepted (G2 limitation, `jamoexc` refuses a dy, 9.7 consequence). **17** accepted (same as
M3). The "miss shortcut" suggestion is recorded as optional. Nothing was rejected outright; every finding was checked
against the code named (`svf_jamo.c:522-526`, `svf_draw.c:1292`, `jamoset.py:777-837` and `:1117-1130`,
`check-features.sh:286-306`, `svf_face.c:236-331`, `maker/quality.py:36`, `tools/facecheck.py` imports) before acceptance.
User decisions folded in: cap 255 / u8 count (header unchanged: byte 8 count, byte 9 zero), and every section 9
recommendation adopted as written, the writer threshold adapted to the cap.

## Changes since 43242f6 (review round 2; finding id -> action)

Claude lane: **N1** accepted. The matrix is split: a `SVF_JMAP=1 SVF_JMAP_LIST=0` build has `jmap_valid` and gives
`JMAP_BAD` for every header kind, a malformed fallback included; a RECOG build keeps the recognition's existing rules
(`JMAP_BAD` for R1' / L3 / advance / 0xFFFF; `JMAP_UNREAD` plain without the FALLBACK flag; `JMAP_UNREAD` + `JSET_BAD`
for a region ending before F + 12 or a malformed fallback; fallback used otherwise, `jlist_planes_*` included). Decided:
RECOG does **not** check L2 (R2 is not checked for SPARSE there either; consistency over a few bytes). The §4 RECOG row
no longer claims the fallback's well-formedness as a `JMAP_BAD` cause; §7 lists the per-kind expectations. **N2**
accepted: the count is now 2 x (8 + 22) = 60 after `jlist_short_nofb` was added (58 before it). **N3** accepted: the
three-way R3/L3 is spelled out for `jmap_fallback`. **N4** accepted: bytes 8-9 are "u16 NS, LIST range 1..255"
throughout; the "u8 + reserved" wording is gone.

opencode lane: **Important (RECOG matrix + read bound)** accepted in substance, with one part rejected: RECOG does not
gain R1's length test and L2 (the proposed "R1' in full, length first, then L2") because that changes the existing
SPARSE recognition (or splits it into two arms) for no verdict the LIST=0 build does not already give; the read-bound
hazard is removed the other way, by RECOG never reading bytes 10-15 (its read pattern is unchanged: bytes 6-9, then one
byte at F + 11 after `F + 12 <= region`, with F <= 2,158 because L3 bounds `ns` first). The fallback's well-formedness
stays the JSET part's `JSET_BAD` in RECOG, as asked. **Minor jlist_short** accepted (100 bytes, 12..117; `jlist_length`
= F + 1 on `list_nofb`). **Minor seed count** accepted (see N2). **Minor svf_glyph** accepted. **Minor cap cost**
accepted (section 2.5: the cap is a table argument; a recombination-heavy list over 255 goes to SPARSE with copies or
the future POOL flag). **Minor jamoexc v3 base** accepted (refused with a message naming the plain face). **Minor alt 3**
accepted (reworded: the 18,918 B LIST is not legal; the comparison is with SPARSE plus copies).

agy lane: APPROVE, no new findings. Verified against the code before acceptance: `jmap_fallback`'s reads and verdicts
(`svf_jamo.c:721-747`), `jset_version`'s 12-byte rule (`:545-553`), `jmap_valid`'s `if (!r) goto bad` for a malformed
fallback (`:683-697`), `jset_bytes` loading exactly the region (`svf_stream.c:95-99`), `svf_glyph` (`svf.h:200`).
