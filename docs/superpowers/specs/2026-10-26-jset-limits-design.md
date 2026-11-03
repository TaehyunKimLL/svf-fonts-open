# Jamo composition tracks: Mac mapping-table mode (A), JSET limit lift (B), feature switches — design

> **Implemented (2026-10-27)** by `docs/superpowers/plans/2026-10-26-jset-v3-jmap-big.md` (card t_380104f8) on branch
> `jset-limits` (not merged or pushed). Where this design and the plan differ, the plan's rulings (PR-1..PR-22) and the
> controller rulings below win.
>
> Commits per group (`git log 2fb312d..jset-limits`):
>
> - A, base (Tasks 1-5): integration `ecda358`..`693a45d` (main, mac-fbit-svf, uno-seoul); `check-features.sh` `6130f49`,
>   `70c7ab7`; JMAP in Python `67aee43`, `0bb70f5`, `3f74da8`; `svf_synth` `9a22291`, `53cce0a`; C status split and no-JMAP
>   recognition `450b776`, `65297d6`.
> - B, C JMAP reader (Tasks 6-8): `51a4020` reader, `fc818ca` defaults and feature rows, `1cbe1f2` fuzz seeds, fix rounds
>   `1cc8647`, `4eb4eaf`.
> - C, Mac and Uno (Tasks 9-13): `ed144af` direct writer and type-3 goldens, `92aeb19` HangulTalk 1.0 goldens, `c5f4efa` tool
>   consumers, `268fbe0` preset manifest, `a069570` sketch presets; fix round `f2b06ce`, `60b69ba`, `5492b6a`, `0c3de9a`.
> - D, BIG (Tasks 14-17): `a7ca1a1` Python BIG, `a0a6144` `svf_synth` BIG kinds, `51c02a0` C BIG reader, `6e4317d` defaults,
>   rows, fuzz seeds.
> - After the plan's tasks: `b05d946` (S8K preset is S8K1), `84ae0cf` (Arduino Mega rows), `67a8ae0` (original ESP32 rows). Commit trailers name the model that authored the commit (R-AD); no rewrite.
> - Task 18: this note, the identity sweep (`c/bench/JSET2-IDENTITY.md`) and `c/cross/SIZES.md` records.
>
> Rulings that changed the plan (rulings only; reasons are in the SDD ledger):
>
> - R-A: the preset manifest ORIGIN column is filled from the actual logs; hashes and sizes of the plan stay.
> - R-B: Task 1's merges into `jset-limits` are inside this branch (executed by an implementer).
> - R-C: standard and cheap implementer model both Sonnet where turn count matters (Tasks 1, 8, 10, 18).
> - R-D: the final whole-branch review is Opus plus the agy and opencode lanes.
> - R-E: Task 1's review is the Claude lane only (pure merge).
> - R-F: AVR configs also scan `.text` for JMAP/jmap strings; an objcopy failure is a hard failure.
> - R-G: Uno MAXFLASH figures use 22,276 B for HGKEY6J (the tree measure), not the plan's 22,266.
> - R-H: a review finding on the hook-variable leak was refuted by execution (dash and bash).
> - R-I, R-J: fallback piece numbers must be >= PI+PM+PF; public `pack_fallback` keeps the caller's numbering.
> - R-K, R-L, R-O: Tasks 3, 4, 5 closed after their fix rounds; the remaining minors were carried to the next task that edits the code.
> - R-M: new switch `SVF_JMAP_RECOG` (default on only on the PR-13 positive list; compiled out with `SVF_JMAP=1`);
>   PR-6's "unconditional recognition" is superseded, only the status split stays in the minimal build.
> - R-N: a fallback flag set with the region ending before the 12-byte fallback header is `JMAP_UNREAD` + `JSET_BAD` in
>   RECOG builds, `JMAP_BAD` in JMAP builds.
> - R-P, R-P': per-task verification runs on host x86-64 (ASan), AVR (simavr) and RP2040 (rp2040js); DOS, ESP32, M33 and
>   WASM at group boundaries.
> - R-Q: the JMAP reader's size is accepted (opt-in switch; the estimate band was a guess); a size-optimisation follow-up is recorded below.
> - R-R: the `jmap_off` regression test is added (Task 8); the per-switch columns in the records are carried to Task 18; Tasks 14 and 16 must not grow `svf_face` past its 96 B cap.
> - R-S: the Group B boundary-check hypothesis was accepted as verified.
> - R-T: the hot-path speed-up of Task 5 is accepted; the reference becomes 6049 / 7279 / 187299 cycles (not 6091 / 7321 / 188251).
> - R-U, R-V: Group B fix round 1 went to the Task 6 implementer for the whole group; round 2 was re-reviewed by the Claude lane only.
> - R-W: Group C fix round 1 was split by file ownership among the original implementers.
> - R-X: `final_classes` uses a separate typedef `svf__cls_t` (u16 narrow / u32 BIG), keeping narrow object code identical.
> - R-Y: minimal+BIG is below the plan's estimate band (AVR +26, M0+ -4); accepted; test builds pin `-DSVF_JSET_BIG=0` through `reader_flag`.
>
> Follow-ups (not done by the plan):
>
> - (a) ScummVM `graphics/hires_text/jamo_set.h`, until t_5a7bcd78 swaps in the C renderer: `kJamoMaxInitSets` and
>   `kJamoMaxMedSets` (`:39-40`, 24/16) must become 32/24 to read the v1 limits (AGOTH24J and AMYUNG24J have 32 initial
>   sets), `kJamoSetMaxSize` (`:79`) 12,321; version 2 and the BIG caps need the C reader; a version 3 (JMAP) block is
>   refused (plain face) until then.
> - (b) Derived-form faces for the other fonts after v3 is final (decision 4).
> - (c) Track C: set reduction / re-decomposition of other fonts.
> - (d) `SVF_JMAP` / `SVF_JSET_BIG` on the Pico and ESP32 images once the user decides from the measured rows.
> - (e) JMAP reader size optimisation (R-Q): the TRUSTED path drops R5-R7 loops (PR-20), a shared popcount, fewer 32-bit
>   ops on AVR.
> - (f) HangulTalk 1.0 as JSET v3 / BIG only if a font needs it (the four fonts fit the v1 limits through `--layout mac-fbit-45sets`).
> - (g) JMAP / BIG columns for atmega2560 in the `build-all.sh` variant rows (the Mega rows have the `JSET_BIG` variant but no JMAP column).
> - (h) Mega far reads: faces over 64 KB are not supported (near PROGMEM reads only).
> - (i) `presets.sh regen` does not reproduce S8K (now S8K1, `b05d946`); the pinned manifest is the reference.
> - (j) Uno true-minimal card t_52f677aa (a hardcoded Seoul JSET was abandoned 2026-10-27).
> - (k) ESP32 original (Odroid-Go) was hardware-verified by the user without a `build-all` row (card t_e8bb0eed).
> - (l) Real-hardware confirmations by the user, 2026-10-27: Korean text legible with S8K on a real Uno (sketch and commit not
>   recorded); Odroid-Go ESP32 16 bpp.
> - (m) Group D review follow-ups: the narrow hot-path identity test has a baseline constant that must be re-baselined when the
>   narrow code changes on purpose; the narrow reader (`-DSVF_JSET_BIG=0`) gets its own fuzz build (`fuzz-open-strict`); the
>   `svf2to3` BIG rule (a verbatim copy of a BIG table needs `--jset-big`) is fixed in the same review round (P section; its JMAP-fallback and `macfbit_svf verify` leftovers in round 2). BIG + SVF_NO_STREAM/MCU_STRICT (an AVR BIG port) is not fuzzed by any target since fuzz-open-strict became BIG=0.

Card t_380104f8 (svf-fonts), 2026-10-26, branch `jset-limits` from main 2fb312d. Written from
`docs/superpowers/specs/2026-10-23-jset-compact-design.md`, `spec/SVF.md` ("Jamo sets", both block versions, the v3
header and layout bytes), `c/src/svf_jamo.c`, `c/src/svf_internal.h`, `c/src/svf_stream.c`, `c/include/svf.h`,
`tools/jamoset.py`, `tools/jamoadapt.py`, `tools/svf_synth.py`, `c/tests/fuzz_corpus.sh`, `c/cross/SIZES.md`,
`c/cross/build-all.sh`, `c/bench/MEASUREMENTS.md`, the Mac conversion (branch `mac-fbit-svf`, card t_1dc5bd99, commit
33deba5, `tools/macfbit_svf.py`, reports `<workdir>/hinting/out/mac-fbit-svf/*.report.json`, `*.analyse.log`, the HTBL
dumps `<workdir>/hinting/out/mac-seoul12/*_htbl.tsv` and `seoul12_fbit.bin`), the Galmuri branch (`galmuri-jamo`,
`tools/galmuri_jamo.py relax_jamoset`, `<workdir>/hinting/out/galmuri-jamo/HANDOFF-pause-2026-10-26.md`), the Uno
example builds `<workdir>/hinting/out/uno-sam12/build/{SAM12U,MR12G}.txt` and ScummVM
`<workdir>/scummvm-korean/graphics/hires_text/jamo_set.h`. Numbers marked *measured* were taken on this worktree today;
*estimate* marks a computed or extrapolated figure; my own calls are **(design call)**.

User inputs folded in (2026-10-26, via the controller): (1) the Mac conversion finished and all five faces fit the
current limits; (2) SVF v3 shall also support a **Mac-style mapping-table composition mode** that keeps the original
structure (per-syllable glyph slots, original glyph sets as they are, no merge, no re-decomposition, no extrapolation
unless the face supplies a fallback), and the set limits rise as needed (벌수 상향); set **reduction** by
re-decomposition (Galmuri/Seoul/SAM) is a separate track; (3) every new capability is a **compile-time switch**, default
off on AVR, on in the desktop build, with nothing of a disabled feature left in the binary.

Document map: section 1 the finding; 2 Track A (mapping table, `JMAP`); 3 Track B (limit lift, `JSET` v3); 4 Track C
(reduction, out of scope, named); 5 feature switches, size matrix, CI check, error codes; 6 recommended order; 7 open
questions; summary.

## 1. Finding first: every Mac-converted face is inside the current limits

The card was opened because the Mac-converted faces were expected to exceed the JSET limits (the brief quoted
AppleGothic 12 with 48 final sets). The finished conversion (`macfbit_svf.py search_classes` + `fit_limits`, which
merges classes and sets until nothing is over while every KS X 1001 syllable stays exact) lands every face inside the
version 1 limits (LC, TC <= 12; NI/NM/NF <= 32/24/16):

| face | classes LC x TC | sets NI/NM/NF | pieces | JSET v1 B (as written) | v2 B | file B | KS exact | residual px (extrapolated syllables) |
|---|---|---|---|---:|---:|---:|---|---:|
| SEOUL12J | 8 x 4 | 9/6/3 | 219 | 2,933 | 1,146 | 12,624 | 2,350 | 0 |
| AGOTH12J | 12 x 6 | 19/7/3 | 378 | 5,875 | 2,440 | 20,560 | 2,350 | 6 |
| AMYUNG12J | 12 x 7 | 20/10/3 | — | 6,795 | 2,982 | 23,972 | 2,350 | — |
| AGOTH24J | 12 x 8 | **32**/15/7 | 606 | 8,433 | 4,006 | 43,948 | 2,350 | 1,004 |
| AMYUNG24J | 12 x 8 | **32**/19/7 | — | 8,601 | 4,274 | 47,552 | 2,350 | — |

(report fields `sets`, `within_v1_limits: true`, `syllables.over_limit_domains: []` in every report; `size_v1`,
`size_v2`.) The "48 final / 21 initial sets" of the brief appear in no report, analyse log or build log of the
finished run; they were a pre-`fit_limits` state. The two 24 px faces sit exactly on two caps: 12 lead classes and 32
initial sets.

**Verified with the C reader of this worktree** (*measured*, `make -C c svfdump` at 2fb312d, default build, both JSET
readers): `svfdump FACE info` prints `jamo=1 jset_bad=0` for all five (glyphs 316 / 475 / 559 / 703 / 744, `flags=3`,
`version=3`), and `svfdump FACE syllables` composes all 11,172 syllables of each face byte-identically to
`jamoset.compose` (5 x 11,172 cells compared, 0 different; the 51 compat cells after them were not compared by me;
`macfbit_svf.py verify` reports `compat_bad 0` for each). `jamoset.unpack` reads the five blocks and `pack_v1`
reproduces their bytes.

So **no change to the C renderer, the spec or the tools is needed for the Mac faces to be read.** What remains is
(a) the user's structural requirement (Track A: the Mac table as it is, no derived selector); (b) headroom: the 24 px
faces are at two caps, and `AppleGothic12.analyse.log` lines 19-23 show the fit cost (16 x 12 classes: residual 0 px,
374 pieces; forced to 12 x 12: 6 px, 378 pieces; AGOTH24J keeps 1,004 residual px in extrapolated, non-KS syllables);
(c) the Galmuri-type many-variant faces (honest split: 11,172 exact, **19 x 27 classes, 65/91/41 sets, 2,081 pieces,
v1 108,008 B / v2 96,188 B**; per-jamo-variant form 65/155/53, v1 119,812 B), paused.

Pre-existing gap: ScummVM's own reader (`jamo_set.h:37-41`, `kJamoMaxInitSets = 24`, `kJamoMaxMedSets = 16`) is behind
the *current* v1 limits (32/24/16), so it rejects AGOTH24J and AMYUNG24J (32 initial sets) today, and it reads version 1
only (`jamo_set.cpp:79-81`). Card t_5a7bcd78 replaces it with the C renderer (section 3.8).

## 2. Track A: mapping-table composition mode (block `JMAP`)

### 2.1 What the Mac table is (*measured* on `seoul12_htbl.tsv` + `seoul12_fbit.bin`; the five HTBL dumps are identical)

- 2,350 KS syllables + 51 compat jamo, each an entry of up to three glyph slots (initial, medial, final plane), planes
  OR-ed; 2,001 entries use 3 planes, 349 use 2 (no final). 482 slots (2 banks x 241), 479 non-empty, 473 referenced;
  per plane the referenced slots are disjoint: **253 initial, 152 medial, 68 final** (no slot serves two planes).
- Seoul12 cell 12 x 12, 18 B a slot in the fbit (482 x 18 = 8,676 B); only **206 distinct bitmaps** among the 473
  referenced slots (initial 90, medial 64, final 52): the Mac stores many identical glyphs under different slots.
- The derived SEOUL12J face reproduces all 2,350 KS syllables and 51 compat jamo pixel-exactly (`verify ks_bad 0,
  compat_bad 0`). So for the five Mac faces the direct and derived forms differ in *structure and size*, and in the
  8,822 non-KS syllables (derived: extrapolated; direct: blank or a fallback), not in any KS pixel.

### 2.2 Requirements

- A1 A face may carry a `JMAP` block **in the existing composition region** (header flag bit 1, offset 36, size 40;
  the 48-byte SVFN header has no free word: bytes 20-47 are all assigned, `spec/SVF.md` byte map). The region's
  4-byte magic tells `JSET` from `JMAP`. **(design call)** This needs no header change and no new flag bit, and every
  reader built before this spec already treats a region whose magic is not `JSET` as a bad JSET: the face opens plain
  (`SVF_FACE_JSET_BAD`), never an error (`svf_jamo.c:220, 349`; `jamoset.unpack` "JSET magic is wrong"). A JMAP face
  that also wants the derived selector as its non-KS fallback carries the JSET block **inside** the region after the
  JMAP block (the JMAP header names its offset), so one region holds both.
- A2 An entry names, per plane, a **piece number** (glyph at U+F0000 + n, as JSET pieces) or "no plane"; the planes are
  composed in order initial, medial, final by `svf_compose`'s existing maximum-coverage merge (OR at 1 bpp, `svf__merge`,
  `svf_internal.h:183`), which equals `mac_compose` (`macfbit_svf.py:103-107`) for 1 bpp. No new composition code; the
  "maximum coverage" rule and the OR rule coincide at 1 bpp and the maximum is the natural extension at 2/8 bpp.
- A3 Original slots are kept **as the writer stores them**: the `direct` exporter writes one piece per referenced slot
  (473 for Seoul12) by default; `--dedup` folds byte-identical bitmaps (206) and is a writer option, never a reader
  concern. No merge, no re-decomposition, no residual transfer, no extrapolation.
- A4 Non-KS syllables: a face with only a `JMAP` has them **absent** (`svf_has` 0, drawn from the next source or the
  missing glyph, as a plain face does); a face with `JMAP` + `JSET` composes a `JMAP` miss from the `JSET` (the
  fallback selector the brief allows). `JMAP` always wins on a hit.
- A5 Reader cost: table in the face (flash / PROGMEM / mapped file), no RAM table, no cell or page buffer growth;
  streamed faces load the block into the tables buffer as the JSET is (caller-sized, `svf_stream_tables_size`).
- A6 Golden: the five Mac faces written in direct form render byte-identically to `mac_fbit3`'s composition for all
  2,350 KS syllables and 51 compat jamo (`macfbit_svf.py verify` extended to direct faces; the C reader's `svfdump
  syllables` for those 2,401 code points vs the Python composer; mapped and streamed; with and without TRUSTED).
- A7 Validation like the JSET's: every rule reads bytes earlier rules bounded; a bad block leaves a plain face with a
  distinct status bit (5.4); fuzz seeds and bad kinds for every rule.

### 2.3 Block format **(design call)**

Little-endian, byte reads only, bits LSB-first in a byte stream as in JSET v2.

```
off  size        field
0    4           "JMAP"
4    u16         version = 1
6    u8          flags: bit 0 compat entries present; bit 1 presence bitmap present (else dense, N = 11,172); bits 2-7 0
7    u8          advance (px; 0 = cell width)
8    u16 x 3     PI, PM, PF: plane list lengths (piece numbers per plane; 1..65,534)
14   u16         N entries (2,350 for KS; up to 11,172)
16   u16         FB: offset of a fallback JSET block inside the region (0 = none; it starts there and runs to the
                 region's end, read by the JSET readers as today)
18   bitmap      flags bit 1: 1,397 B presence bitmap over U+AC00..U+D7A3 (bit s set = syllable s has an entry) and
                 44 x u16 ranks (entries before each 256-syllable block)
     lists       PI + PM + PF u16 piece numbers (plane lists, initial then medial then final; 0xFFFF invalid)
     entries     N x (WI + WM + WF) bits; field value 0 = no plane, k = plane list index k - 1;
                 width(n) = ceil(log2 (n + 1)), WI = width(PI) ...; a field <= 9 bits is one two-byte fetch
     compat      flags bit 0: 51 x (WI + WM + WF) bits, same encoding, U+3131 + k
```

Lookup: `s = cp - 0xAC00`; bitmap bit s clear -> miss; `i = rank[s >> 8] + popcount(bitmap bytes (s >> 8) * 32 .. s >> 3
masked)` (at most 32 bytes; the JSET's `popcount` and `SVF_JSET_POP4` table are reused); entry i's three fields ->
plane list -> piece numbers -> `svf_compose` as today (`svf_jamo_pieces` returns them; `svf__composed` reports a hit).
Rejected: a dense 11,172-entry table (32 KB at 23 bits); a sorted u16 code point list (4,700 B, binary search per
lookup); raw slot numbers (9 + 9 + 9 bits over a 482-slot list) instead of per-plane lists (per-plane lists are
disjoint on the Mac and give 8 + 8 + 7 bits; raw costs 4 bits an entry and ties the block to the Mac bank layout).
Size: `18 + 1,485 [bitmap] + 2 (PI + PM + PF) + ceil(N (WI + WM + WF) / 8) + ceil(51 (WI + WM + WF) / 8)`.

### 2.4 Size impact (SEOUL12J; *estimate* for glyph records, which are boxed and average 14.4 B a piece in the derived face: 3,164 B / 219)

Derived form today (*measured*, `size_v1`): header 48, cmap 2,528 (316 x 8), metrics 1,264, offsets 1,268, JSET 2,933,
glyph data 4,580 (pieces 3,164 + compat 28 + Latin 1,388), padding 3 = **12,624 B**.

| direct form | pieces | JMAP block | cmap/metrics/offsets (8 + 4 + 4 B a glyph, 97 Latin glyphs included) | glyph data | total |
|---|---:|---:|---:|---:|---:|
| slots as they are (`direct`) | 473 | 18 + 1,485 + 946 + 6,757 (2,350 x 23 bits) + 147 = 9,353 | 570 x 16 = 9,120 | 473 x 14.4 + 1,388 = 8,200 | **~26,700 B** |
| `--dedup` (206 distinct bitmaps) | 206 | 18 + 1,485 + 946 + 6,757 + 147 = 9,353 | 303 x 16 = 4,848 | 206 x 14.4 + 1,388 = 4,355 | **~18,600 B** |
| Mac's own representation, for scale | 482 x 18 = 8,676 | HTBL 2,401 x 4 = 9,604 | — | — | 18,280 B |

So the direct form of SEOUL12J is about 1.5 x (dedup) to 2.1 x (as-is) the derived face; the table alone is 9.4 KB
against the 2.9 KB JSET, because the derived selector *is* a compression of this table. A 24 px face scales the glyph
part by 4 (AGOTH24J derived 43,948 B; direct as-is *estimate* ~70 KB). Hybrid (class selector for regular syllables +
exception list) is **not** proposed: for the five Mac faces the derived selector is already exact on every KS
syllable, so the exception list would be empty and the hybrid is the derived face; the hybrid only pays where a derived
form has KS errors, which is Track C's question.

### 2.5 Reader (`SVF_JMAP`, section 5)

`c/src/svf_jmap.c` (new, compiled only with `SVF_JMAP`): `svf__jmap_check` (validation at open: header, counts, size by
the formula == region, every plane list entry a piece with a glyph, every entry field <= its list length, bitmap rank
table consistent with the bitmap — the ranks are redundant and must match: `rank[b] == popcount(bits of blocks < b)`,
checked in one pass; every compat field likewise), `svf__jmap_pieces(f, cp, out[3])`. `svf_jamo_pieces` tries JMAP
first (hit -> return), then the JSET readers. `svf_face` gains `jmap_off`, `jmap_len` (u16; the KS block is 9.4 KB,
a dense 11,172-entry block at 27 bits is 37.7 KB: fits) and three widths (3 B) — **+9 B per face struct on every
build that compiles JMAP; 0 B otherwise** (fields under `#if SVF_JMAP`). Validation cost per rule follows the JSET's
(*estimate* from the measured JSET v2 rules, `SIZES.md` "Validation cost per rule": header 40, lists 60, entries 120,
bitmap/ranks 100, compat 60 B on AVR). Reader *estimate*: Cortex-M0+ 300-450 B text (lookup 180, validation 200), AVR
450-700 B; measured in Task 2 of the plan.

Trusted mode (`SVF_JSET_TRUSTED` extends to JMAP; **(design call)** no separate switch: the meaning "faces the
developer builds into flash" is the same): header, version, counts and the size-equals-region check stay; lists,
ranks and fields are trusted.

### 2.6 Writers and tools

- `tools/macfbit_svf.py build --mode direct|derived` (default `direct` per PR-17 and user decision 3; `derived` is today's path): `direct` writes the referenced
  slots as pieces (plane lists in slot order), the 2,350 entries, the 51 compat entries, Latin as today, no JSET;
  `--dedup`, `--with-jset` (adds the derived JSET as the non-KS fallback, A4), `--jset-version` as today. The report
  gains `mode`, `jmap` bytes, `pieces_as_slots`.
- `tools/jamoset.py`: `Jmap` (fields), `pack_jmap`, `unpack_jmap`, `jmap_size`, `parse_svfn` reads the new header
  words/flag, `pack_svfn`/`write_svfn` take `jmap=`; `compose(f, t, cp)` takes a JMAP first when the face has one
  (`svfline.Face`, the picker's `mkindex`, `facecheck`, the maker's `detect.usable_jset` -> `usable_jmap` beside it:
  classification `svf-jamo` for either).
- `tools/svf_synth.py`: `--jmap-bad KIND` (`magic`, `version`, `flags`, `length`, `list_piece_missing`,
  `field_over`, `rank_wrong`, `compat_field_over`, `reserved`) and `--jmap-variant` (`dense`, `nocompat`,
  `with_jset`); `fuzz_corpus.sh` seeds them and a direct SEOUL12J-shaped synthetic face (no Apple bytes enter the
  repository: the seed is built from `svf/` pieces).
- `svf2to3.py --check` compares composed syllables through `svfline` for either block.

### 2.7 Risks

- Size: a direct 12 px face is 1.5-2.1 x the derived one (2.4), a 24 px face ~70 KB; on the Uno (16 KB left after the
  library) only derived faces fit. The structural requirement costs flash; the user should see 2.4 before choosing
  `direct` as the Mac default.
- Region sharing: the JSET region fields now hold either block (or JMAP + fallback JSET); every reader (C, Python,
  picker WASM, maker, the ScummVM reader until t_5a7bcd78) dispatches on the magic. Old readers already open such a
  face plain (bad JSET), so the only cost is that a JMAP-only face has no syllables on them.
- Non-KS behaviour: a `JMAP`-only face draws no non-KS syllable; a game text with one shows the fallback glyph. The
  `--with-jset` form covers it at +JSET bytes.

### 2.8 Questions for the user (Track A)

- Default export mode for the Mac faces: `direct` (structure) or `derived` (size)? Both can be kept under different names
  (e.g. `SEOUL12M.SVF` direct, `SEOUL12J.SVF` derived).
- `--dedup` on by default? (No visible change; 206 vs 473 pieces for Seoul12.)
- Should a direct face carry the derived JSET as the non-KS fallback by default (+2.9 KB on SEOUL12J)?

## 3. Track B: the JSET limit lift (block version 3), optional

Needed now (Mac faces): nothing (section 1). Headroom for the 24 px Mac faces: LC up to 16 (the exact 16 x 12 fit), NI
up to about 40. Speculative (Galmuri honest split): LC 19, TC 27, NI 65, NM 91 (155), NF 41 (53).

### 3.1 Requirements

- B1 Faces inside the old limits keep reading and writing **byte-identically** (golden: `c/bench/jset2-identity.py`
  over `svf/`, totals `faces=153 jamo=95 different=0`; the five Mac faces; the `uno-sam12` faces built by
  `tools/jamofill.py build_face`; `tools/testdata`; `cmp` of every writer's output).
- B2 The AVR default build (v1 reader alone) does not grow by a byte (rows in 5.2).
- B3 Other default builds: at most +64 B text on Cortex-M0+ P1 (7441) when `SVF_JSET_BIG` is on; the P1/P2 budget
  8,192 B holds; larger is report-and-ask.
- B4 A build without the wide reader opens a wide face as a plain face with the distinct status bit (5.4), never an
  error; fuzz (new seeds at the limits and one past, `make fuzz`/`fuzz-rd` 1 h each under ASan).
- B5 The wide reader composes the synthetic limits face (and the Galmuri face when one fits) identically to
  `jamoset.compose` for 11,172 syllables + 51 compat, mapped and every `STREAM_CONFIGS`, with and without TRUSTED.
- B6 Hot path unchanged for existing faces: Pico MONO_PAGE `-Os` `syl_ga` 6,143 / `syl_bwelk` 7,500 / `screen32`
  194,583 cycles from the v1 bench face (ruling R2 of the compact design) and the v2 rows of `MEASUREMENTS.md` from the
  same face forced to v2; identical QEMU M33 instruction counts.
- B7 Python: `pack_jset(t, 3)` / `unpack` round trip, `jset_size`, `jset_line`; `pack(t)` (v2) refuses over-limit
  tables with the same message; `jamoadapt` keeps the old limits as a named profile; `galmuri_jamo.relax_jamoset` is
  deleted and the branch builds through `pack_jset(t, 3)`.

### 3.2 Limits **(design call)**: LC, TC <= 32; NI, NM, NF <= 127; block size by the formula <= 65,535

- `width(127) = 7`, W <= 21 bits; a field read stays one two-byte fetch (`cell_set`, `svf_jamo.c:89-100`: 7 + 7 <= 16).
  128 would put set 127 under the compat byte's 0xFF blank in the bit 7 form; 127 removes the case.
- Classes 32 cover 19 x 27 with margin; `leadClass`/`tailClass` are bytes already. `final_classes` and the `1u << n`
  shifts (`svf_jamo.c:263, 270, 400, 408`) and the cell bit offset (`cell_set`; 32 x 21 x 32 cells x 21 bits = 451,584)
  become `uint32_t`.
- The face's `jset_len` is `uint16_t` (`svf.h:108`; `svf_face.c:160` clips a longer header size to 0xFFFF, which then
  fails the length check), so the joint rule is honest: largest block without aliases 63 + 56,448 + 127 x 16 + 51 =
  **58,594 B**; with aliases the formula can pass 65,535 and is refused. `SVF__JSET_MAX` and `SVF__JSET_LOAD_MAX`
  (`svf_internal.h:32, 49-53`) are 65,535 in a build with the wide reader. RAM effect: streamed faces only, whose tables
  buffer the caller sizes (`svfdemo.c:60`, `svfvesa.c:162`); the 16-bit `size_t` guard (`svf_stream.c:121-123`) still
  refuses on AVR.
- The Galmuri honest face (96,188 B in the v2 layout) **does not fit a 16-bit `jset_len` at all**; carrying it needs
  `jset_len` -> `uint32_t` (+2 B per `svf_face` on every build that compiles it; a separate decision, 7).
- Rejected: 64/32/32 (Galmuri's 65 initial / 91 medial do not fit; 7 vs 6 bits is one bit a field); 255 (compat byte
  cannot name it; 255 x 67 rows plus aliases exceed 65,535 anyway).

### 3.3 Compat byte **(design call)**: bits 0-6 the set (0..126), bit 7 the final-table switch, 0xFF blank

The layout of the Galmuri relaxation (`galmuri_jamo.py:2117-2149`). Existing v2 faces read identically (their bits 5-6
are 0). `compat_piece` (`svf_jamo.c:163-186`) masks `c & 0x7F` and drops the `(c & 0x60)` test: for a version 2 block
the count limit (<= 32) makes a byte with bits 5-6 set fail `s >= count` exactly as before, so **one compat path serves
both versions** and the `compat_bits56` bad kind still fails. Python `unpack` (`jamoset.py:812-820`) the same. Rejected:
a u16 compat table (+51 B on every wide face, a second path); a per-face compat-width field.

### 3.4 Versioning **(design call)**: block version word 3, v2 layout unchanged; `SVF_JSET_BIG` reads it

- Writers: v1 by default, v2 on request, **v3 only on explicit `--jset-version 3`**; a table over the v1/v2 limits
  under `1|2|auto` is an error naming `--jset-version 3`; `auto` never picks 3 (B1 holds by construction).
- Readers: `SVF_JSET_BIG` (needs `SVF_JSET_V2`; `#error` otherwise) accepts version 3 in `jset_valid`
  (`svf_jamo.c:444-455`; `svf_jamo_pieces`' `!= 1` test at `:512` is already right for 3) and selects the wide limits
  row. **A v1-limit-only build keeps the narrow path**: without `SVF_JSET_BIG` the limits table has one row, the
  locals stay `unsigned`, and the version test is `== 2` as today, so the compiled v2 reader is byte-identical to
  2fb312d's (checked by the nm/size gate of 5.3).
- Rejected: widening v2 in place (a wide and a narrow face would share a version word: `svf2to3 --check`, the maker and
  `jset_line` could not warn before a narrow target refuses it; the frozen "v2 limits" text would change
  retroactively); widening v1 (u8 cell tables at 32 x 32 classes are 64,512 B alone, the Galmuri v1 face is 108,008 B,
  and the v1 reader is the AVR default whose literals at `svf_jamo.c:243-245` must not move); a header flag bit
  (unknown SVFN flags refuse the whole face).

### 3.5 Reader shape (`c/src/svf_jamo.c`)

`ROM_TABLE limits[5]` (`:59`) becomes `limits[1 + SVF_JSET_BIG][5]` indexed by `version - 2`; `jset_valid_v2` becomes the
one packed validator taking the version; rule (2) computes the size in `uint32_t` and adds `<= 65,535` under
`SVF_JSET_BIG`; `(1u << j) < n` already handles n <= 255; `slots`/`na` stay below 65,536 (127 x 67 = 8,509). Hot path
(`pieces_v2`, `slot_piece`, `cell_set`, `row_at`): no new branch; the version is not consulted after open. TRUSTED
keeps its meaning (packed counts are trusted today, `:360-363`; the `uint32_t` types keep "no lookup leaves the region").

### 3.6 Tests, fuzz, `svf_synth` (Track B)

`svf_synth.py --jset-version 3`: bad kinds `lc33`, `tc33`, `ni128`, `nm128`, `nf128`, `size_over_u16` (aliases pushing
the formula past 65,535 with the length matching), `compat_set_over` at 127; the five v2 kinds `lc13`..`nf17` become
*valid* on a v3 block; `BAD_KINDS_V3` beside `BAD_KINDS`/`BAD_KINDS_V1` (`svf_synth.py:121-127`). Variants `limits3`
(32 x 32, 127/127/127, NA 0: 58,594 B, W 21), `limits3_alias` (largest block under 65,535 B), `w14_v3` (v3 word on v2-sized
counts: reads as its v2 twin). `test_jamoset.py`: `test_sizes` (+ 58,594, the 65,535 rule),
`test_pack_refuses_tables_over_the_limits` (v2 unchanged; v3 at 33/128), a v3 sibling of
`test_set_limits_32_24_16_round_trip_compose_and_33_25_17_refused`. `test_c_renderer.py`: `test_set_limits_32_24_16`
(`:1224`) unchanged, `test_set_limits_v3` new, `test_jset2_width_edges` (`:830`) + W 21, `test_jset_defaults_per_target`
(`:1037`) + the BIG column, the `*_reader_alone` tests + "v3 opens plain with the UNREAD bit", `test_trusted_draws_identically`
+ the v3 limits face. `fuzz_corpus.sh`: `jset3-bad-*`, `jset3-variant-*`, v3 copies of NSQRB16 and HGKEY6J.

### 3.7 Python tools (Track B)

`jamoset.py`: `_JSET_LIMITS` (`:518`) -> `JSET_LIMITS = {1: (12,12,32,24,16), 2: (12,12,32,24,16), 3: (32,32,127,127,127)}`;
`_check_counts(..., version)`; `decode_jset2` reads 2 and 3 and records `b.version`; `encode_jset2` writes it;
`pack(t, version=2)` (the v3 writer is the same encoder with the v3 row and the 65,535 check); `pack_jset(t, 3)`;
`choose_jset_version` unchanged; `jset_size` unchanged; `jset_line` prints `v3=`; `unpack` dispatches 1/2/3 with the
same return shape (so `svfline`, `maker/detect.usable_jset`, `facecheck`, `svf_synth`, `bdfface`, scummvm-korean's
`facecoverage.py` are untouched); `MAX_LEAD_CLASSES`/`MAX_TAIL_CLASSES` (`:60-61`) stay the v1 values behind a
`class_limit(version)` helper. `jamoadapt.py`: `FORMAT_LIMITS` (`:34`) -> `{"v1": (32,24,16), "v3": (127,127,127)}`,
`CLASS_LIMITS = {"v1": 12, "v3": 32}`; `adapt(..., limits=LIMITS, class_limit=None)` keeps its default budget 32/24/12
and the v1 class limit; `--format v1|v3` on `jamovec master --adaptive` and `jamoaa`; `macfbit_svf.py SET_LIMITS`,
`CLASS_LIMIT` take the profile. `svf2to3.py --jset-version 1|2|3|auto`. `galmuri_jamo.py`: delete `relax_jamoset` and
`docs/tools.md:580-586`; `jamo_face(..., jset_version=3)`; blocks over 65,535 B refused with the size.
`docs/tools.md` `:137-148`, `:347`, `:419-428`, `:459`.

### 3.8 ScummVM `jamo_set.h`

Nothing in this card (edits there are out of scope; t_5a7bcd78 replaces `JamoSetTable` with the C renderer, whose
readers its targets choose by define). For that card: `jamo_set.h:39-40` are 24/16 against the spec's v1 32/24, so the
engine refuses AGOTH24J/AMYUNG24J (32 initial sets) and any v2/v3 or JMAP face until the swap; if the swap slips, the two
constants become 32/24 and `kJamoSetMaxSize` (`:79`) follows (12,321).

### 3.9 Risks (Track B)

No known face needs it; the one over-limit face (Galmuri honest split, 96 KB) does not fit the 16-bit length even
after the lift; the cost is a second limits row, three `uint32_t` locals and the fuzz/synth matrix growth.

## 4. Track C: set reduction by re-decomposition (separate, later)

Named here so the planner does not fold it in: merging variants, residual transfer, class/set search (`fit_limits`,
`jamoadapt.adapt`, `galmuri_jamo` split/sweep, `jamofill`) are **tool-side** work on how a face is derived; they need
Track B only when the honest result exceeds 32/24/16, and nothing in the reader. Not designed here.

## 5. Feature switches (user requirement: compile-time, minimal binary on small devices)

### 5.1 Principle

Every capability is a `-D` switch in `svf.h`'s "Size switches" block (`svf.h:329-392`), exactly as `SVF_JSET_V1`,
`SVF_JSET_V2`, `SVF_JSET_POP4`, `SVF_JSET_TRUSTED`, `SVF_TARGETS`, `SVF_NO_STREAM`, `SVF_NO_SCALE`, `SVF_LAYOUTS`,
`SVF_MERGE_WORDS`, `SVF_GRAY8_LUT1`, `SVF_SCALE_FAST`, `SVF_SMALL` are today. A disabled feature leaves **no code,
table, string or struct field** in the binary: its source file (or `#if` region) compiles to nothing, its `svf_face`
fields are under `#if`, its tables are `#if`-guarded `ROM_TABLE`s. The library has no strings at all (the host prints
from status bits/error codes), so the "no strings" rule is already met and stays a gate.

New switches **(design call)**:

| switch | track | what it compiles | what a build without it does |
|---|---|---|---|
| `SVF_JMAP` | A | `svf_jmap.c` (check + lookup), the magic dispatch in the composition region, `jmap_*` face fields (+9 B struct) | a region with the `JMAP` magic opens plain with `SVF_FACE_JMAP_UNREAD` (5.4); a fallback JSET inside it is still used if the build reads JSET (5.4) |
| `SVF_JSET_BIG` | B | the second limits row, version 3 acceptance, `uint32_t` locals, the 65,535 rule | a version 3 block opens plain with `SVF_FACE_JSET_UNREAD`; the v2 reader is byte-identical to today's |
| `SVF_KS_ONLY` | A | **not a switch**: the KS-only build is `SVF_JMAP=1 SVF_JSET_V1=0 SVF_JSET_V2=0` (the `#error` at `svf.h:372` becomes "at least one of V1, V2, JMAP"); it drops the whole JSET path (v1 reader + validation: AVR *estimate* 1.1-1.3 KB from `SIZES.md` TRUSTED delta 556 B + lookup/compose; M0+ *measured* v1-only vs v2-only differ by 583 B) | — |

A separate `SVF_KS_ONLY` define would only alias that combination; rejected to keep one knob per feature.

### 5.2 Feature x target matrix (R-sw1): defaults

Target classes: **AVR** (ATmega328P; Arduino and CH582 ports pin their flags explicitly), **small ARM/RISC-V MCU** (Pico
RP2040/RP2350, ESP32-C3/S3, Cortex-M33; the pico/esp32 port images), **DOS** (DJGPP, 32-bit protected mode; there is no
16-bit DOS build in the tree: `c/ports/dos` is DJGPP only, `SIZES.md:108-115`), **desktop** (host gcc/clang, WASM
picker, SDL).

| switch | AVR | small MCU | DOS | desktop | removes when off |
|---|---|---|---|---|---|
| `SVF_TARGETS` | `0x02` (ports) / `0x1FF` (P4 probe) | per image (`profiles.txt`) | all | all | blitters of other kinds |
| `SVF_NO_STREAM` | set | unset (images may stream) | unset | unset | `svf_stream.c` |
| `SVF_NO_SCALE` | set | per image | unset | unset | `svf_scale.c` |
| `SVF_JSET_V1` | 1 | 1 | 1 | 1 | v1 reader |
| `SVF_JSET_V2` | **0** | 1 | 1 | 1 | packed reader |
| `SVF_JSET_POP4` | 0 | 1 | 1 | 1 | 16 B nibble table |
| `SVF_JSET_TRUSTED` | 0 (a flash-face build may set 1) | 0 | 0 | 0 | validation (never in fuzz/check) |
| GRAY kind (`SVF_TARGET_GRAY` in `SVF_TARGETS`) | off (does not fit, `SIZES.md` P4+GRAY) | per image | on | on | the GRAY blitters |
| **`SVF_JMAP`** (new) | **0** | **0 until measured, then the user decides per image** | 1 | 1 | `svf_jmap.c`, header words, 9 B of face |
| **`SVF_JSET_BIG`** (new) | **0** | **0 until measured** | 1 | 1 | limits row 2, v3 acceptance, wide locals |
| KS-only combination | available (`-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0`) | available | n/a | n/a | the JSET readers |

Defaults are set in `svf.h` the way `SVF_JSET_V2` is (`#if defined(__AVR__)` 0, else 1), plus `SVF_SMALL` turning
`SVF_JMAP` and `SVF_JSET_BIG` off (an explicit `-DSVF_X=1` wins, as for `SVF_JSET_POP4`).
`test_jset_defaults_per_target` (`test_c_renderer.py:1037`) gets both columns: host `JMAP 1 BIG 1`, `__AVR__` `0 0`,
`SVF_SMALL` `0 0`, explicit `=1` wins.

### 5.3 CI-style check (R-sw2, R-sw3): `c/cross/check-features.sh`

Builds, with the AVR and the Cortex-M0+ toolchains of `build-all.sh` (`-Os`, `-ffunction-sections -fdata-sections`,
linked with `--gc-sections` the way the ports and `SIZES.md` rows are), the matrix:

1. **minimal** (Uno-style) = the Arduino port's flags (`build-all.sh:483`, `c/ports/arduino/README.md:14`):
   `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0` (JSET v1 only,
   no stream, no POP4, mono target only, no JMAP, no BIG);
2. minimal + each single new switch (`SVF_JMAP`, `SVF_JSET_BIG` (+V2, which it needs), the KS-only combination);
3. all-on (every switch 1, every target kind).

For each build it records `text`, `rodata` (and `data`, `bss`) of the library archive linked into the P1 probe into
`OUT/features/rows.txt` and fails when:

- the **minimal** row exceeds the committed baseline: the `SIZES.md` AVR P1 row (**12920 B text** today) and the
  Cortex-M0+ P1 row (**7441**), by more than 0 B (the user's rule; the +20 B v1-only gate of the compact design is
  superseded by this stricter one for the minimal config);
- the two Uno example images rebuilt with the branch exceed their recorded flash: **SAM12U 21,488 B (text 21,470, data
  18, bss 1,085), MR12G 21,160 B (text 21,142)** (`<workdir>/hinting/out/uno-sam12/build/*.txt`; the script takes the
  sketch dir and face by argument, so the numbers live in `SIZES.md`'s new "Minimal config" table, not in the script);
- a disabled feature leaves a symbol: `nm --defined-only` of the linked probe must contain none of the feature's symbol
  prefixes (`svf__jmap_`, `jmap_` statics; for BIG the `limits` table must be 5 B not 10 — checked by `nm -S`;
  `pop4` when POP4 is 0; `svf_open_stream` when NO_STREAM; `svf__scale` when NO_SCALE), and `strings` of the archive
  must stay empty of the words `JMAP`/`JSET` beyond the 4-byte magics;
- the all-on row grows a reported amount against the committed row (reported, not gated: the user judges).

`check-sizes-md.sh` reads the new tables like the Size switches table. `build-all.sh --switches` gains the `JMAP`,
`JSET_BIG` and `KS_ONLY` columns on Cortex-M0+ and AVR.

### 5.4 Reader behaviour when a face needs a disabled feature (R-sw4)

Today a JSET of a version the build does not read sets `SVF_FACE_JSET_BAD` (`svf.h:75`), the same bit as a malformed
block. **(design call)** Split the two cases with new status bits in `svf_status()` (`uint16_t status`, bits 0-3 used):

```
SVF_FACE_JSET_UNREAD 0x0010  the JSET block is of a version this build does not compile (header well-formed): plain face
SVF_FACE_JMAP_BAD    0x0020  flags name a JMAP block that fails validation: no JMAP composition (JSET still used if valid)
SVF_FACE_JMAP_UNREAD 0x0040  a JMAP block in a build without SVF_JMAP: plain for KS lookups (JSET still used if valid)
```

The face still opens (never an error, as today for JSET_BAD), `svf_is_jamo` is true only when some reader is usable, and
a host prints its own text per bit (the library carries no strings; `svfdump info` gains `jset_unread=`, `jmap_bad=`,
`jmap_unread=`). A build without `SVF_JMAP` recognises the `JMAP` magic with four byte compares (the cost of the
distinct bit; *estimate* 16-24 B) and sets `JMAP_UNREAD`; with a fallback JSET inside the region (`FB`) such a build
cannot find it without the JMAP header, so **(design call)** the four compares also read `FB` and hand that offset to
the JSET readers: a JMAP + JSET face composes from its JSET on every build that reads JSET (about 40 B more, measured
in Task 2; the user may drop this to keep the minimal build at 0 B growth, in which case the fallback is not seen
there). Readers older than this spec open the face plain (bad JSET magic), the pre-existing rule.

### 5.5 Measured and estimated sizes per feature

*Measured* today (`SIZES.md` Size switches, text bytes): Cortex-M0+ P1 default 7441; `JSET_V1` only 6146 (-1,295 =
the packed reader + both-reader glue); `JSET_V2` only 6729; `JSET_TRUSTED` 6764 (validation 677); `JSET_POP4=0` 7413
(28). AVR P1 default (v1 only) 12920; `JSET_BOTH` 15342 (+2,422); `JSET_V2` only 13414; `JSET_TRUSTED` 12364 (validation
556). Uno bench image 27430 B (code 18714 + face 8716), RAM 1224. *Estimates* for the new features (to be measured in the
first task of each track, before any tool work): `SVF_JMAP` M0+ +300..450 B, AVR +450..700 B, +9 B `svf_face`;
`SVF_JSET_BIG` M0+ +24..64 B, AVR (on top of V2) +60..120 B (the `uint32_t` locals cost on an 8-bit core), +0 B
`svf_face`; KS-only on AVR -1,100..-1,300 B against the minimal build (v1 reader + its validation + `pieces_v1`), then
+JMAP; the JMAP-magic recognition in a no-JMAP build +16..24 B (+~40 B with the fallback offset, 5.4) — the one item
that touches the minimal build, and therefore a user decision (7.6). A measured figure outside its estimate band is a
report-and-ask point.

### 5.6 Acceptance for the switch work

- S1 `check-features.sh` passes on the branch: minimal rows equal 2fb312d's (0 B growth), nm/strings checks clean.
- S2 The Uno images SAM12U / MR12G rebuilt <= 21,488 / 21,160 B flash.
- S3 `test_jset_defaults_per_target` extended passes; `build-all.sh` and `--ports` (43 OK lines) pass; `check-sizes-md.sh`
  reads the new tables.
- S4 `svf_synth` faces needing a disabled feature open plain with the right bit in every single-feature build
  (`test_c_renderer.py` new `test_feature_unread_bits`).

## 6. Recommended order

**A first, then B only on demand; C separate.** Track A is the user's stated requirement and is independent of the JSET
limits (its block names pieces directly; no class or set count exists in it). Track B has no face that needs it today
(section 1), and its one known candidate does not fit the 16-bit length field even after the lift; it stays drafted
(section 3) and is started when a face needs it or the user decides. Within A: Task 1 the switch scaffolding and
`check-features.sh` (5.3) with the baseline rows committed, Task 2 the C reader behind `SVF_JMAP` with size
measurements, Task 3 `jamoset` + `macfbit_svf.py --mode direct` + golden (A6), Task 4 synth/fuzz/tests, Task 5 spec and
docs (`spec/SVF.md` header bytes, flag bit 3, the JMAP section; `docs/tools.md`; `SIZES.md`, `MEASUREMENTS.md`).

## 7. Open questions for the user

1. (Resolved: `direct` is the default, PR-17.) Track A export default for the Mac faces: `direct` (structure, ~1.5-2.1 x the size) or `derived` (12,624 B for
   SEOUL12J)? Keep both under different names?
2. `--dedup` default (206 vs 473 pieces for Seoul12; no visible change) and whether direct faces carry the derived JSET
   as the non-KS fallback.
3. Track B: start now or park? If started: 32/32/127 with the 65,535 B rule (recommended) or round 64/32/32; and
   whether `jset_len` becomes 32-bit (+2 B per face struct) so the 96 KB Galmuri block becomes possible on 32-bit targets.
4. `SVF_JMAP` / `SVF_JSET_BIG` defaults on the small-MCU images once measured (off until then).
5. Classes above 12 for the 24 px Mac faces: worth it only for the extrapolated (non-KS) syllables' 1,004 residual px.
6. The new status bits (5.4), and whether the minimal (no-JMAP) build may spend ~40-60 B to recognise the JMAP magic
   and find the fallback JSET inside a shared region, or must stay at 0 B growth (then a JMAP + JSET face is plain on
   the Uno; a JSET-only face is unaffected either way).

## Summary

Commit: this document only (branch `jset-limits`; no code).

1. All five Mac faces are inside the current v1 limits and open in the C reader (`jamo=1 jset_bad=0`), 11,172 syllables
   each identical to the Python composer; no reader change is needed for them.
2. AGOTH24J/AMYUNG24J sit on the 12-lead-class / 32-initial-set caps; ScummVM's own reader (24 initial sets) rejects
   them until t_5a7bcd78.
3. Track A (`JMAP`, `SVF_JMAP`): per-syllable plane entries over per-plane piece lists, KS presence bitmap + ranks,
   OR = the existing maximum-coverage merge; SEOUL12J direct ~18.6 KB (dedup) / ~26.7 KB (slots as-is) vs 12,624 B derived.
4. Track B (`JSET` v3, `SVF_JSET_BIG`): v2 layout, LC/TC <= 32, sets <= 127, block <= 65,535 B, 7-bit compat set; v1
   reader untouched; the Galmuri honest face needs a 32-bit `jset_len` beyond it.
5. Track C (reduction) is separate and not designed here.
6. Switches: `SVF_JMAP`, `SVF_JSET_BIG` (off on AVR and small MCUs until measured, on for DOS/desktop), KS-only as the
   combination `JMAP=1 V1=0 V2=0`; distinct status bits `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD`.
7. `check-features.sh`: minimal / single-feature / all-on matrix on AVR and M0+, 0 B growth of the minimal build (AVR
   P1 12920, M0+ 7441), Uno images <= 21,488 / 21,160 B, nm/strings checks for disabled features.
8. Estimates to be measured first: JMAP M0+ +300..450 B, AVR +450..700 B; BIG M0+ +24..64 B.
9. Order: A, then B on demand; C separate.
10. User decisions: direct vs derived default, dedup/fallback defaults, B now or parked, cap and `jset_len` width,
    small-MCU defaults, whether the minimal build may spend ~40 B to see a JMAP face's fallback JSET.
