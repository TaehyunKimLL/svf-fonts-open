# Cross review: Argon's JMAP / JSET-big design against mine (card t_380104f8)

2026-10-26. Reviewed: `<workdir>/scratch/review-lanes/jset-limits-argon/argon-design.md` (Gemini 4 Argon,
"Argon") against `docs/superpowers/specs/2026-10-26-jset-limits-design.md` at 2ff39ad ("mine") and the sources
`c/src/svf_jamo.c`, `c/include/svf.h`, `c/src/svf_internal.h`, `spec/SVF.md`, `tools/jamoset.py` (incl. its
`mac-fbit-45sets` layout, `:1877-2130`), `<workdir>/johab-fonts/tools/mac_kfont.py`. Every number marked *measured* was
computed today with `jamoset` formulas or the fonts; nothing in Argon's file was edited. New user input taken as
given: the Mac faces are to be stored in their original structure (direct mapping); the goal is that HangulTalk 1.0
fbit (Gotic12, Munjo12/16/24) and 7.1.x type-3 fonts are accepted; Galmuri decomposition is abandoned, Track B on
demand only.

## (a) Where Argon is better, where mine is

**Argon better (adopt):**

1. **Block identity.** Argon keeps the `"JSET"` magic and uses **version 3 for JMAP** (`§2.1`); mine used a new
   `"JMAP"` magic in the same region. Both reject cleanly on old readers (`jset_valid`, `svf_jamo.c:444-455`, accepts
   only 1 and 2 -> `SVF_FACE_JSET_BAD`, plain face). Argon's is cheaper: the magic compare exists, `svf_jamo_pieces`'
   `!= 1` test (`:512`) already routes version 3 to the packed side, and the 16-byte header the stream loader keeps
   (`svf_stream.c:94-101`) is the same. Mine needed a second magic compare in builds without `SVF_JMAP` (my 5.4,
   +16..24 B); Argon's needs nothing there.
2. **Piece numbering by plane, contiguous** (`§2.3.1` P1/P2: piece = `base_t + idx - 1`, `PI/PM/PF` in the header).
   Mine stored explicit per-plane u16 piece lists (946 B on SEOUL12J) because JSET pieces are arbitrarily numbered;
   Argon lets the writer renumber (as `jamoset.pack` already does for v2) and drops the lists. Smaller and one
   indirection less per lookup.
3. **Byte-aligned entries** (3 B when every plane has <= 255 pieces, 4 B with 3+3+2 high bits otherwise) instead of my
   bit-packed `WI+WM+WF` (23 bits on SEOUL12J). Cost: 7,050 vs 6,757 B on SEOUL12J (+293 B); gain: no 32-bit bit-offset
   multiply on AVR, no two-byte fetch, `idx * 3` or `idx << 2`. For the HangulTalk 1.0 dense table (11,172 entries,
   widths 9/8/7 = 24 bits, *measured* below) the 3 B form is exactly as big as bit-packing (33,516 B). Adopt P1/P2.
4. **The hybrid is the same block** (`§2.3.4`): bitmap of exception syllables + fallback JSET. Mine dismissed the
   hybrid as "derived + empty list"; Argon's framing makes it free and gives Track C a home later.
5. **Compat as `u16[51]` piece numbers** (102 B) rather than my bit-packed compat entries (147 B): smaller *and*
   simpler. Adopt.
6. **R7 overflow sites named concretely** (`§3.2`: `cell_set` bit offset, `final_classes` shift, compat mask), with
   the `#if SVF_JSET_BIG` type gating so the narrow build's code is byte-identical. Mine said the same in prose; Argon's
   is the implementable form.

**Mine better (keep):**

1. **Verified premise.** Mine records that all five Mac faces are inside the v1 limits and composes identically in the
   C reader (*measured*, 5 x 11,172 syllables), and that the ScummVM reader (24/16 caps, `jamo_set.h:39-40`) rejects
   the 24 px faces today. Argon's R3 still motivates `SVF_JSET_BIG` with "AGOTH24J 12x8, 32/15/7", which fits v1 (its
   own table row says "Yes").
2. **Status bits distinct per cause** (`JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD`, my 5.4; the user's R-sw4). Argon
   folds everything into `SVF_FACE_JSET_BAD` (R2), so a host cannot tell "malformed" from "this build lacks the
   feature".
3. **Feature x target matrix with defaults per target class and the CI script** (`check-features.sh`: minimal /
   single-feature / all-on, 0 B growth of the minimal build, Uno images <= 21,488 / 21,160 B, `nm`/`strings` checks;
   my 5.2-5.3, the user's R-sw1..3). Argon's `§6` table is of `svf_jamo.o` sizes it presents as measured
   (`1,588 B`, `2,718 B` ...) with no command, no commit and no row in `SIZES.md` that holds them: unverifiable; its
   guard (`§6`) names `build-all.sh --check`, which does not exist (the script has `--ports`, `--port`, `--switches`
   hooks; `build-all.sh:76, 139`).
4. **Writers and golden tests tied to existing tools** (`macfbit_svf.py build --mode direct`, `verify` extended;
   `svf_synth` kinds by name; `fuzz_corpus.sh` seeds; the identity script totals). Argon names functions that do not
   exist (below).
5. **Track separation and order** (A, then B on demand, C separate) matches the new user input; Argon designs B as
   mandatory with Galmuri as a driver.
6. **The HangulTalk 1.0 fonts are already expressible**: `jamoset.py --layout mac-fbit-45sets` (`:1877-2130`,
   `mac_layout`) derives exact JSET tables from the `fdef` rule; neither design said so, mine at least kept the Mac
   readers out of Track B's motivation. Section (c) quantifies it.

**Disagreements to settle:** Argon widens v1 *and* v2 in place under `SVF_JSET_BIG` (no new version word); mine made the
lift a version 3 of the packed block and now (per Argon's choice) version 3 is JMAP. With the corrected Galmuri sizes
(below) in-place widening is viable: a wide face is rejected by a narrow reader through its count check, which is the
same clean path. Remaining cost of in-place widening: a tool cannot tell from the version word that a face needs
`SVF_JSET_BIG` (it must read the counts: `jset_line` and `svf2to3 --check` can). Recommendation (d): accept Argon's
in-place widening, keep version 3 for JMAP.

## (b) Factual errors and inconsistencies

**In Argon's design** (verified against the sources):

- `SVF_FACE_JSET_BAD` is `0x0008` (`svf.h:75`), not `0x1` (R2, `§2.1`).
- JSET v2 rows carry 3- or 4-byte presence bitmaps (`PB`, `spec/SVF.md` "Set rows"; `slot_piece`, `svf_jamo.c:145`),
  not "`u64` presence bitmaps" (`§2.1` item 2).
- Line references are off throughout: `limits[5]` is at `svf_jamo.c:59` (`:243-245` are the v1 literal checks);
  `jset_valid` at `:444-455` (not `:401-426`); `pieces_v2` at `:472-502` (not `:131-188`); `svf__merge` at `:602`;
  `svf_compose` at `:660` (not `:604-691`). No function `jset_header`, `piece_Range_ok` (`§3.3` step 3), `extract_jset`,
  `_validate_jset_fields`, `unpack_jset`, `pack_jset_v1`, `resolve_syllable`, `write_jamo_svf` (`§4`) exists in
  `jamoset.py`/`svf_jamo.c`; the real names are `pack`, `pack_v1`, `pack_jset`, `unpack`, `_unpack_v1`, `decode_jset2`,
  `_check_counts`, `compose`, `write_svfn`. No `svf_open_progmem` exists (`§8`).
- `svf_face` has no `jset_row[]` field (`svf.h:121-122`: `jset_lc, jset_tc, jset_adv, jset_na, jset_w[3]`); the
  `§3.1` field reuse (`jset_na` holding a u16 `PI`) does not fit a `uint8_t`. "`sizeof(svf_face)` kept at 64 B on AVR"
  is unmeasured.
- SEOUL12J JSET v1 is **2,933 B** (*measured* file and `_jset_size_v1(8,4,9,6,3)`), not 3,273; v2 at NA = 0 is 963 B
  (`jset_size`), the written v2 block 1,146 B (aliases), not 981/1,158. AGOTH12J v2 NA = 0 is 2,152 B (not 2,140),
  written 2,440; AGOTH24J v2 NA = 0 3,415 (not 3,388), written 4,006. Argon's v1/v2 formulas (`§2.2`) are right; the
  table rows were not computed with them.
- `§2.2` max v2 with every slot an alias at 19x28, 96/96/64 is 41,868 B (`jset_size(..., NA=4,704)`), not 41,492.
- `advance == 0` is **valid** ("0 = cell width", `spec/SVF.md`, `svf_face.c:367`); `§3.3` step 1 rejects it.
- `§3.3` step 3 requires pieces contiguous at U+F0000..; existing v1 faces number pieces arbitrarily, so this can only
  be a JMAP-writer rule, not a check reused from JSET (`svf__glyph_index` per piece is the existing check).
- "Uno Minimal (No Jamo): `SVF_JSET_V2=0, V1=0`" (`§6`) is a compile error today (`svf.h:372-374`); relaxing that
  `#error` is a change the design must name (mine 5.1 names it for the KS-only build).
- `§2.3.5`/`§6` present `SVF_KS_ONLY` as a separate switch that also compiles out the fallback dispatch; fine, but the
  "-336 B / -608 B smaller than JSET v2" rows are estimates presented as measurements.
- `§7` item 1 rejects a header flag bit for the reason mine gives; agreed, but `svf__open_header` is at
  `svf_face.c:~91-160`, and the refusal is `SVF_E_LAYOUT` for "other bits set" (`spec/SVF.md:224`): correct.

**In my design** (2ff39ad):

- **The Galmuri figures are file sizes, not block sizes.** The handoff's "v1 108,008 B / v2 96,188 B" are the face
  files; the honest-split JSET block is **40,986 B (v1) / 29,165 B (v2)** (*measured* from the headers of
  `faces9h/v1|v2/GALM9J.SVF`, counts 19/27/65/91/41), exactly `_jset_size_v1`/`jset_size` + aliases. So my claims
  "the Galmuri face does not fit a 16-bit `jset_len`" (3.2, 3.9, 7.3, summary 4 and 8) and the `uint32_t jset_len`
  question are **wrong**; a 16-bit length holds it with room. Argon's R7 bound (`< 65,535`) is right and sufficient.
- Consequently my rejection of "widening v1" lost one of its two reasons (the 108 KB one); the other (the AVR v1
  reader's literals) is met by Argon's `#if SVF_JSET_BIG` gating.
- My cap 32/32/127 with the 65,535 rule still works but is larger than needed; Argon's 19/28 classes are the
  linguistic maximum (19 initials, 28 tail states) and cannot be exceeded by any decomposition, so **19 x 28 is the
  right class cap** (my 32 x 32 bought nothing). Sets: 96 or 128 vs my 127; see (d).
- My JMAP size table (2.4) used explicit plane lists and bit-packed entries; with Argon's layout SEOUL12J direct is
  smaller: block 16 + 102 + 1,486 + 2,350 x 3 = **8,654 B** (vs my 9,353), face totals ~17.9 KB (dedup 206 pieces) /
  ~26.0 KB (473 slots as they are) instead of 18.6 / 26.7 KB (*estimate*, glyph records at the measured 14.4 B average).
- My 5.4 "JMAP-magic recognition in the minimal build" item disappears with Argon's version-3 choice.

## (c) HangulTalk 1.0 Gotic12 computed from `mac_kfont.compose()` (*measured*)

Font `<workdir>/johab-fonts/mac/extracted/kh10_system_disk/System Folder/Gotic12.rsrc`: cell 12 x 12, 45 sets, **653
glyphs** over the sets (`jamoset.MacSource.count`). All 11,172 syllables composed through `compose(tb, L, V, T)`
(Johab fields via `jamoset.JUNG_FIELD`): 10,773 use three planes, 399 two (no final).

| quantity | initial | medial | final |
|---|---:|---:|---:|
| distinct Mac sets used | 18 (sets 0-17) | 23 (18-40) | 4 (41-44) |
| distinct (set, glyph) pieces | 354 | 191 | 108 |
| distinct bitmaps among them | 285 | 91 | 92 |

**JSET representation.** The minimal classes under which the Mac rule is a function of (lead class, vowel, tail
class) — computed from the 11,172 results with the signature method of `jamoset.mac_layout` — are **8 lead classes**
(`[0,1,2,2,3,4,4,4,4,3,5,4,3,5,6,0,4,4,7]`) and **4 tail classes** (`[0,1,1,1,2,1,...,3 at ㅅ,1,...]`), and
`jamoset.mac_layout(MacFbit)` gives **8 x 4 classes, 20 / 15 / 4 sets** (its tables reproduce every syllable bit for
bit; `jamoset.py` `--layout mac-fbit-45sets` check). That is **inside JSET v1** (<= 12 x 12, 32/24/16): no v3/BIG is
needed for any HangulTalk 1.0 font. Block sizes: **v1 3,783 B, v2 1,237 B** (NA = 0; `_jset_size_v1(8,4,20,15,4)`,
`jset_size`). The 653 original glyphs remain the pieces (354 + 191 + 108 = 653 referenced; `MacSource` numbers them
set by set, so the "original slots as pieces" requirement is met by the existing layout, only the *selector* is
derived).

**JMAP direct table** for the same font: all 11,172 syllables -> dense mode (no bitmap), per-plane widths
`ceil(log2(354+1)) = 9`, 8, 7 = 24 bits = exactly Argon's 3 B entries: **33,516 B of entries + 16 header + 102 compat
= 33,634 B** (4 B entries: 44,806 B). So for HangulTalk 1.0 the direct table is **8.9 x the v1 JSET block** and
27 x the v2 block, for identical pixels and identical pieces. The glyph side is the same in both (653 pieces; 285+91+92
= 468 distinct bitmaps if deduplicated).

Conclusion for (c): a HangulTalk 1.0 font is "accepted in its original structure" by JSET v1 already — its glyph sets
are kept as they are and its own `fdef` rule *is* a class/set selector (8 x 4 classes, 20/15/4 sets, exact). JMAP
buys nothing for it except a literal transcription of a rule table that the Mac itself computes. The 7.1.x type-3
fonts are the opposite case: their table is the composition (no rule), and the derived 8x4..12x8 selectors are
re-decompositions with residual transfer — there JMAP is the faithful form (2,350 entries, 8,654 B on SEOUL12J).

## (d) Merged recommendation

1. **Track A, JMAP = JSET block version 3** (Argon `§2.3.3` layout: `"JSET"`, version 3, flags 4B/SPARSE/FALLBACK,
   advance (0 = cell width, correcting Argon), NS, PI/PM/PF, `u16[51]` compat pieces, optional 1,397 B bitmap + 44 u16
   ranks, 3 B or 4 B entries, optional embedded fallback JSET v1/v2). Pieces contiguous by plane at U+F0000 (writer
   rule). Switch `SVF_JMAP` (0 on AVR/`SVF_SMALL`, 1 elsewhere); status bits `JSET_UNREAD` / `JMAP_BAD` / `JMAP_UNREAD`
   (mine 5.4) kept so hosts can print the cause. Golden: the five type-3 faces direct = `mac_fbit3` for 2,350 + 51.
   Use for: 7.1.x type-3 fonts (direct), and as the hybrid container if Track C ever needs exceptions.
2. **HangulTalk 1.0 fonts: JSET v1 via `--layout mac-fbit-45sets`** (exists; 8 x 4, 20/15/4, exact, 3,783 B). No
   format work. Add them to the golden set (bit-identical to `mac_kfont.HfntFont.johab` over 11,172) and to the
   Uno/MCU face list if wanted (653 pieces x 24 B = 15.7 KB of glyphs at 12 px, *estimate* full-cell).
3. **Track B = `SVF_JSET_BIG` widening v1 and v2 in place** (Argon `§2.2`, `§3.2`) with class caps **19 x 28** and set
   caps **128/128/64** (power-of-two; 7+7+6 bits; v1 max 47,373 B, v2 max with every slot an alias 45,068 B — Argon's
   figure; both under 65,535), 7-bit compat set, `#if`-gated `uint32_t` sites, no new version word. On demand only
   (Galmuri abandoned); the honest Galmuri block (40,986 / 29,165 B) fits if it ever returns.
4. **Switches and CI** as in mine 5.1-5.3 (feature x target table, `check-features.sh`, minimal-build 0 B gate, Uno
   image caps, `nm`/`strings`), plus the `#error` relaxation so `V1=0 V2=0 JMAP=1` (KS-only) builds. Argon's separate
   `SVF_KS_ONLY` define is accepted only if it compiles out the fallback dispatch inside the JMAP reader (its one
   distinct effect); otherwise it is the combination.
5. **Order:** A (JMAP for type-3) -> golden for HangulTalk 1.0 under existing v1 -> switch/CI work -> B on demand.

## Questions for the user

1. Mac type-3 faces: ship **direct** (JMAP, SEOUL12J ~17.9 KB dedup / ~26.0 KB slots-as-is) as the primary form, with
   the derived v1 face (12,624 B) kept as a named "compressed derivative" for MCUs — or direct only?
2. Dedup of identical slot bitmaps in direct faces (473 -> 206 pieces on Seoul12; no pixel change): on by default?
3. HangulTalk 1.0 (Gotic12 etc.): accept the existing exact v1 layout (3,783 B selector) as "original structure", or
   do you want the 33.6 KB literal table anyway?
4. Fallback JSET inside a direct face for the 8,822 non-KS syllables: on by default (+2.9 KB on SEOUL12J) or off (those
   syllables absent)?
5. Track B caps if/when started: 128/128/64 (Argon) vs 127 (mine, avoids the 0xFF compat corner) — and do it now or
   leave parked?
6. Defaults of `SVF_JMAP` / `SVF_JSET_BIG` on the small-MCU images (off until measured, as both designs propose)?

Summary: adopt Argon's block identity (JSET version 3), contiguous per-plane pieces, byte entries, u16 compat and the
in-place BIG widening at 19 x 28 / 128/128/64; keep my verified premise, distinct status bits, switch matrix + CI
script, tool/golden bindings and track order; correct my Galmuri block size (40,986 / 29,165 B, fits u16) and Argon's
constants (JSET_BAD 0x0008, PB 3/4 B, SEOUL12J 2,933 B, advance 0 valid) and nonexistent function names; HangulTalk
1.0 fits JSET v1 exactly (8 x 4, 20/15/4, 3,783 B) against a 33,634 B direct table.
