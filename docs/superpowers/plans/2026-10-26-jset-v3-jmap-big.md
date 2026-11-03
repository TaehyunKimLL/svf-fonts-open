# JSET block v3 (`JMAP`, Mac mapping table) and the JSET limit lift (`SVF_JSET_BIG`): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A JSET block version 3 (`JMAP`: per-syllable plane entries over contiguous per-plane pieces, optional KS
bitmap, optional fallback JSET) read by a C reader behind `SVF_JMAP` and written by `macfbit_svf.py --mode direct`
for the five Mac type-3 faces; then the in-place JSET v1/v2 limit lift behind `SVF_JSET_BIG`; every capability a
compile-time switch with a size gate, and the Seoul Uno presets (S8K..S5K) as the default Uno configuration.

**Architecture:** Phase 0 integrates the three source branches and builds the size gate (`check-features.sh`) before any
reader change. Track A goes Python format first (the reference every C test compares against), then synthetic faces,
then the C status split and the no-`JMAP` recognition, then the reader, then switch defaults/sizes, fuzz, the Mac writer
and its goldens, and the tool consumers. The Uno presets follow (independent of both tracks). Track B (in-place widening
of v1 and v2) runs the same order: Python, synth, C, sizes/fuzz/bench. One closing task re-takes the size and identity
records.

**Tech Stack:** C99 (`-Wall -Wextra -Werror`), GNU make, POSIX sh, avr-gcc 16.1.0, arm-none-eabi-gcc 15.2.1, clang
(libFuzzer), Python 3 (`-I`, unittest), rp2040js (bench).

**Spec:** `docs/superpowers/specs/2026-10-26-jset-limits-design.md` (2ff39ad, "the design"), as corrected and merged by
`docs/superpowers/specs/2026-10-26-jset-limits-crossreview.md` (dab67a3, section (d) "Merged recommendation", section (b)
error list), and the JMAP block layout of the Argon design
`<workdir>/scratch/review-lanes/jset-limits-argon/argon-design.md` §2.3.3 (outside the repo; its byte table is
copied into Global Constraints below so implementers need not open it). **User decisions of 2026-10-26 override all
three** (listed in Global Constraints). Executors read the plan and the design + cross review; where they disagree, the
plan's "Plan rulings" win.

All commands run from `<workdir>/svf-fonts-wt/jset-limits` (branch `jset-limits`, card t_380104f8). Heavy builds
(`build-all.sh`, `make -C c check`, fuzz, `check-features.sh`) run as `~/.local/bin/heavy CMD...`. SDD ledgers go under
`.superpowers/sdd/2026-10-26-jset-v3-jmap-big/` and are never staged. No push.

## Commands verified to exist (2026-10-26, this worktree or the Task 1 merge)

| command | what it is |
|---|---|
| `python3 -m unittest tools.test_jamoset` | jamoset unit tests |
| `python3 -m unittest tools.test_c_renderer` | C library vs Python reference (builds `c/` itself; long) |
| `python3 -m unittest tools.test_c_renderer.<Class>.<test>` | one C test (classes: grep `^class ` in the file) |
| `python3 -m unittest tools.test_tools_doc tools.test_macfbit_svf tools.test_macfbit3 tools.test_jamomerge` | ran on the merged tree: 45 tests OK (2 skipped) |
| `python3 -m unittest tools.test_svf2to3 tools.test_facecheck` | consumers |
| `make -C c check` | library gate (`check.sh --asan`, runs test_c_renderer under ASan, clang, target masks) |
| `make -C c fuzz fuzz-strict fuzz-rd fuzz-corpus fuzz-smoke` | libFuzzer targets and seed corpus (`c/tests/fuzz_corpus.sh`) |
| `sh c/cross/build-all.sh [OUT]`, `sh c/cross/build-all.sh --ports [OUT]` | size tables (`check-sizes-md.sh` gates them; full `--ports` prints 43 OK lines) |
| `sh c/cross/test-build-all.sh` | unit test of build-all's gates |
| `python3 c/bench/jset2-identity.py OLD_DUMP NEW_DUMP OLD_DIR NEW_DIR OUT.md` | pixel identity over `svf/` (totals line `faces=153 jamo=95 different=0`) |
| `sh c/bench/run-pico.sh [OUT]` | rp2040js cycle bench (P1 flags, MONO_PAGE) |
| `python3 tools/macfbit_svf.py build|verify ...` | Mac type-3 converter (after Task 1) |
| `python3 tools/jamomerge.py planes|merge ...` | variant merger (after Task 1) |

## Global Constraints

User decisions 2026-10-26 (binding):

- Order: Track A (JMAP as JSET block version 3) first; Track B (`SVF_JSET_BIG`) right after; Track C (reduction /
  re-decomposition of other fonts) is not in this plan.
- `--dedup` is ON by default in the direct (JMAP) writer.
- Fonts the existing format accepts stay on it: HangulTalk 1.0 (Gotic12, Munjo12/16/24) via `--layout mac-fbit-45sets`,
  JSET v1, with a golden test against the Mac composer over all 11,172 syllables. The 7.1.x type-3 faces (Seoul12,
  AppleGothic12/24, AppleMyungjo12/24) are produced in their original structure via JMAP (`macfbit_svf.py` direct mode);
  golden: byte-identical to `tools/macfbit3.py` `Fbit3.compose` for 2,350 KS + 51 compat.
- Uno ships the derived form; the Seoul presets S8K 8,136 B, S7K 7,012 B, S6K 6,144 B, S5K 5,548 B (built by
  `tools/jamomerge.py`, files in `<workdir>/hinting/out/uno-seoul/final/`) are the default Uno configuration set, S8K the
  default; the face files stay out of git (proprietary-derived, research only); a hash/size manifest is in git.
- Every capability is a compile-time switch (`SVF_JMAP`, `SVF_JSET_BIG`, existing `SVF_JSET_V1/V2/POP4/TRUSTED`,
  `SVF_NO_STREAM`, `SVF_TARGETS`), default OFF on AVR/small MCUs, ON for desktop/DOS. The minimal Uno build may spend
  ~16-40 B to recognise a JMAP face's fallback JSET; otherwise it must not grow.
- Status bits: `SVF_FACE_JSET_UNREAD 0x0010u`, `SVF_FACE_JMAP_BAD 0x0020u`, `SVF_FACE_JMAP_UNREAD 0x0040u` (verified
  free: `svf.h` uses 0x0001, 0x0002, 0x0004, 0x0008 = `SVF_FACE_JSET_BAD`).
- Existing faces: byte-identical writer output and pixels; v1/v2 readers unchanged in behaviour; v3 faces open as plain
  faces in readers without v3 (through `jset_valid`).
- ScummVM `graphics/hires_text/jamo_set.h` is not edited (follow-up note only, Task 18).

JMAP block (JSET version 3; little-endian; byte reads only):

```
off   size     field
0     4        "JSET"
4     u16      version = 3
6     u8       flags: 0x01 4B (entries 4 bytes, else 3), 0x02 SPARSE (bitmap + NS entries, else dense NS = 11,172),
               0x04 FALLBACK (a JSET v1/v2 block follows the entries and runs to the region end); bits 3-7 zero
7     u8       advance (px; 0 = cell width)
8     u16      NS   entries
10    u16      PI   initial pieces  U+F0000 + 0 .. PI-1
12    u16      PM   medial pieces   U+F0000 + PI .. PI+PM-1
14    u16      PF   final pieces    U+F0000 + PI+PM .. PI+PM+PF-1
16    u16[51]  compat piece numbers (0xFFFF blank, else < PI+PM+PF)          (U+3131 + k)
118   u16[44]  SPARSE only: rank[b] = set bits of the bitmap below bit b*256
206   u8[1397] SPARSE only: presence bitmap over U+AC00..U+D7A3, bit s = byte s>>3 bit s&7; bits 11,172..11,175 zero
1603  u8       SPARSE only: pad, zero
E     NS x 3|4 entries, E = 1604 (SPARSE) or 118 (dense); 3B: [i, m, f]; 4B: [b0, i_lo, m_lo, f_lo] with
               b0 = i_hi(bits 0-2) | m_hi(bits 3-5) << 3 | f_hi(bits 6-7) << 6; field 0 = no plane, k = plane index k
F     rest     FALLBACK only: F = E + NS x (3|4); a JSET version 1 or 2 block, length = region - F
```

- Limits: 3B: PI, PM, PF <= 255; 4B: PI, PM <= 2047, PF <= 1023; 1 <= PI+PM+PF; SPARSE: 1 <= NS <= 11,172; dense:
  NS == 11,172; region <= 65,534 B.
- Piece of a hit: initial `i - 1`, medial `PI + m - 1`, final `PI + PM + f - 1`; a 0 field is `SVF_PIECE_BLANK`;
  count 3 when `f != 0`, else 2.
- Lookup index (SPARSE): `idx = rank[s >> 8] + popcount(bitmap bytes (s >> 8) * 32 .. (s >> 3) - 1) + popcount(byte
  (s >> 3) & ((1 << (s & 7)) - 1))`; dense: `idx = s`.
- Sizes: SEOUL12J-shaped sparse 3B no fallback `16 + 102 + 1486 + 2350 x 3 = 8,654`; dense 3B `33,634`; dense 4B
  `44,806`; sparse 4B NS 11,172 `46,292`.

Track B (in-place widening of v1 and v2, no new version word):

- `SVF_JSET_BIG` caps: LC <= 19, TC <= 28, NI <= 128, NM <= 128, NF <= 64 (narrow caps 12, 12, 32, 24, 16 unchanged).
- Maxima: v1 `47,373` B; v2 NA = 0 `29,708` B; v2 every slot an alias `45,068` B (computed with `jamoset._jset_size_v1`
  and `jset_size` on 2026-10-26; the Argon table's `29,668` is wrong).
- v2 compat byte under BIG: bit 7 final-table switch, set = `c & 0x7F`, `0xFF` blank (the bit-7 form is at most
  `0x80 | 63 = 0xBF`, so 0xFF never names a set).
- 16-bit sites typed `uint32_t` under `#if SVF_JSET_BIG` only: `cell_set` bit offset, `row_at`'s set-table length,
  v1 and v2 `final_classes` and their `1u << c` shifts.

Size and speed:

- Minimal (Uno) flags: `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02
  -DSVF_JSET_V2=0`. Baselines (`c/cross/SIZES.md`, P1 probe, text): AVR **12920**, Cortex-M0+ minimal **6146** (P1 +
  `-DSVF_JSET_V2=0`, the "JSET_V1" column), Cortex-M0+ default P1 **7441**. Growth allowed: the no-JMAP recognition
  only, at most **40 B AVR / 24 B M0+**; more is report-and-ask.
- Hot path (Pico MONO_PAGE `-Os`, `c/bench/MEASUREMENTS.md` today): `syl_ga` **6091**, `syl_bwelk` **7321**,
  `screen32` **188251** cycles; equal (not within a tolerance) with `SVF_JMAP`/`SVF_JSET_BIG` at their M-profile
  default (0), and with `-DSVF_JSET_BIG=1` on the same face.
- Uno port image today: 22,266 B flash (text 22,248 + data 18), 1,100 B RAM (HGKEY6J, `build-all.sh --ports`).

Process:

- Commits: one per task (fix rounds may add more), message names card t_380104f8 and ends with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; `.superpowers/` never staged; no push.
- No Apple-derived byte enters git (Mac fonts, SEOUL12J/S8K..S5K, their sheets); tests that need them skip when absent.
- Every new CLI option or tool is documented in `docs/tools.md` in the same task (`tools.test_tools_doc` enforces the
  section census).

## Plan rulings

Residual questions of the design, cross review and user decisions, decided here:

- **PR-1 Paths.** "docs/SIZES.md" and "MEASUREMENTS.md" of the brief are `c/cross/SIZES.md` and
  `c/bench/MEASUREMENTS.md` (no `docs/SIZES.md` exists).
- **PR-2 Integration first.** `macfbit_svf.py` (branch `mac-fbit-svf`, 33deba5), `macfbit3.py` (main, 241a929) and
  `jamomerge.py`/`jamofill.py` (branch `uno-seoul`, d157e95) are not on this branch; Task 1 merges `main`,
  `mac-fbit-svf`, `uno-seoul` (all three merge without conflict, checked 2026-10-26).
- **PR-3 One source file.** The JMAP reader lives in `c/src/svf_jamo.c` under `#if SVF_JMAP` (it shares `RD`,
  `rd16p`, `popcount`/`pop4` and the region dispatch); no new `.c` file, so no build list changes in six build systems.
  The `#if SVF_JSET_V2` guard around `rd16p`/`popcount` becomes `#if SVF_JSET_V2 || SVF_JMAP`.
- **PR-4 One cause bit per part.** `JSET_BAD`: a JSET-part block that is malformed, or of version 0 or >= 4.
  `JSET_UNREAD`: a well-formed header (magic, length >= 12) of version 1 or 2 whose reader is not compiled.
  `JMAP_BAD`: a version 3 block that fails any JMAP rule, its fallback included (one block, one verdict).
  `JMAP_UNREAD`: a version 3 block in a build without `SVF_JMAP`. Counts above the narrow caps in a build without
  `SVF_JSET_BIG` are `JSET_BAD` (the count check is validation; telling them apart would cost a second limits row in
  the minimal build). Behaviour change: a v2 face in a v1-only build moves from `JSET_BAD` to `JSET_UNREAD`.
- **PR-5 `svf_is_jamo`.** True when a JSET part is usable (`jset_lc != 0`; every failure path already clears it) or a
  JMAP is usable (`jmap_off != 0`, `SVF_JMAP` builds). `svf__composed` for a syllable: JMAP hit, else a usable JSET
  part; a JMAP-only miss is not composed (the cmap glyph or the missing glyph, as a plain face).
- **PR-6 Recognition in no-JMAP builds is unconditional.** A build without `SVF_JMAP` reads flags/NS of a version 3
  header, and with `FALLBACK` set and `F + 12 <= region` re-points `jset_off`/`jset_len` at the fallback and validates
  it with the compiled JSET readers. No switch; its cost is the only growth the minimal build may show (Global
  Constraints). A streamed region longer than `SVF__JSET_LOAD_MAX` is loaded to its 16-byte header only, so its fallback
  is not reachable there (plain, `JMAP_UNREAD`).
- **PR-7 Region cap 65,534.** `jset_len` is clipped to 0xFFFF at open (`svf_face.c:160`); a region of exactly 0xFFFF is
  therefore never valid (JSET_BAD / JMAP_BAD). `SVF__JSET_LOAD_MAX` is 65534 in `SVF_JMAP` builds.
- **PR-8 Pieces.** Per-plane contiguous numbering is a writer rule; the reader requires every piece number below
  PI+PM+PF to have a glyph (no reference tracking). Dedup folds byte-identical bitmaps within a plane only.
- **PR-9 Entries decide the count.** A hit returns 3 when `f != 0`, else 2, whatever the syllable's tail; zero fields
  are `SVF_PIECE_BLANK`. Mac entries are kept literally.
- **PR-10 Compat.** JMAP's own compat entry wins when not blank; a blank one falls to the fallback's compat (if any),
  else the cmap glyph. A Mac compat entry with more than one plane is stored whole at U+3131 + k with a blank JMAP compat.
- **PR-11 Fallback.** Version 1 or 2 only; its advance byte must equal the JMAP advance (`JMAP_BAD` otherwise).
- **PR-12 Synthetic kinds.** `svf_synth` bad kind `version3` becomes `version4` (still `JSET_BAD` everywhere); a v2 block
  relabelled version 3 is the new JMAP kind `v2_as_v3`.
- **PR-13 Defaults by a positive list.** `SVF_JMAP` and `SVF_JSET_BIG` default to 1 only when not `__AVR__`, not
  `SVF_SMALL`, and one of `__unix__ _WIN32 __APPLE__ __DJGPP__ __EMSCRIPTEN__` is defined; else 0. Cortex-M, ESP32,
  CH582 and AVR images are therefore unchanged; DOS, WASM, SDL and host builds get both. An explicit `-DSVF_X=0/1` wins.
- **PR-14 No `SVF_KS_ONLY`.** The KS-only build is `-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0`; the `#error` becomes
  "at least one of SVF_JSET_V1, SVF_JSET_V2, SVF_JMAP". In it a fallback is `JSET_UNREAD`.
- **PR-15 `SVF_JSET_BIG` does not need `SVF_JSET_V2`** (in-place widening applies to v1 too); no `#error` pairing.
- **PR-16 Python reads wide, writes narrow by default.** `jamoset.unpack` accepts BIG counts always; writers refuse a
  table over the narrow caps unless `--jset-big` (every CLI that has `--jset-version`) / `big=True`; output within the
  narrow caps is byte-identical whatever the flag. `jset_line` prints ` big=1` for a table that needs BIG.
- **PR-17 Mac writer defaults.** `macfbit_svf.py build --mode direct` is the default (decision 3); `--mode derived` is
  today's path and must write bytes identical to 33deba5's for the same inputs; dedup on (`--no-dedup` off); no fallback
  JSET unless `--with-jset` (original structure, no extrapolation unless asked).
- **PR-18 Uno presets.** `build-all.sh --ports` keeps its in-git HGKEY6J build (43 OK lines unchanged); the presets have
  their own `c/ports/arduino/presets.sh` (verify / regen / build) and a "Uno presets" table in `SIZES.md`. Regeneration
  needs `--recog` (torch, recog-11-12) and may not be bit-reproducible; the pinned manifest is the reference and the
  user-supplied files are verified against it.
- **PR-19 Hot-path reference** is today's `MEASUREMENTS.md` (6091 / 7321 / 188251), not the design's pre-speedup
  6,143 / 7,500 / 194,583.
- **PR-20 TRUSTED covers JMAP.** Kept with `SVF_JSET_TRUSTED`: header length, magic, version, flags reserved bits,
  count limits, NS rule, size == region, the 65,534 cap; the fallback keeps its own trusted rules.
- **PR-21 SPARSE with NS = 11,172 is valid** (an exception list may cover everything).
- **PR-22 Uno image gates** of the design (SAM12U 21,488 / MR12G 21,160 B) become optional `check-features.sh`
  arguments (faces outside the repo); the preset images are gated by `presets.sh build` against the SIZES.md table.

## Review Focus

Inputs the spec implies and a user meets; each is pinned to the task whose tests carry it.

1. **A v3 face opened by a reader built without `SVF_JMAP`** (the Uno minimal flags): opens, `jmap_unread=1`; a
   hybrid face's fallback v1 JSET composes; a fallback v2 in a v1-only build is `jset_unread=1`, plain. Task 5
   `test_jmap_unread_*`.
2. **Entry pointing past its plane** (3B `i = PI + 1`; 4B `f` high bits making `PF + 1`; compat `= PI+PM+PF`): JMAP_BAD,
   plain, ASan clean. Task 3 `test_rules_refused`, Task 6 `test_jmap_bad_kinds_plain`.
3. **KS bitmap with a wrong rank table** (rank[10] + 1; bit 11,172 set; pad byte 1; NS one more than the popcount):
   JMAP_BAD. Task 3, Task 6.
4. **v3 header with zero planes or zero entries** (PI = PM = PF = 0; SPARSE NS = 0; dense NS = 11,171; region 117 B;
   region 0xFFFF): JMAP_BAD, never a crash. Task 3, Task 6 (`jmap_zero_pieces`, `jmap_ns0`, `jmap_dense_ns`,
   `jmap_short`, `jmap_region_max`).
5. **Set count at limit + 1**: narrow build `lc13 tc13 ni33 nm25 nf17` JSET_BAD and BIG build valid; BIG build `lc20
   tc29 ni129 nm129 nf65` JSET_BAD. Task 15 (Python), Task 16 (C).
6. **advance 0**: valid in JMAP and fallback; the composed glyph advances by the cell width. Task 6
   `test_jmap_advance_zero`.
7. **Fallback mismatch**: fallback version 3, advance differing, a fallback cut short: JMAP_BAD in JMAP builds; in
   no-JMAP builds JMAP_UNREAD (+ JSET_BAD for a malformed fallback). Task 5, Task 6.

## Task overview and pre-flight conflicts

| # | task | size | model | depends |
|---|---|---|---|---|
| 1 | integrate source branches | S | cheap | - |
| 2 | `check-features.sh` + "Minimal config" table | M | standard | 1 |
| 3 | Python JMAP format + `spec/SVF.md` | M | standard | 1 |
| 4 | `svf_synth` JMAP variants and bad kinds | M | standard | 3 |
| 5 | C status split + no-JMAP recognition | M | standard | 2, 4 |
| 6 | C JMAP reader | L | standard | 5 |
| 7 | switch defaults, KS-only, feature rows, port sizes | M | standard | 6 |
| 8 | fuzz seeds and runs (JMAP) | S | cheap | 7 |
| 9 | `macfbit_svf.py --mode direct` + goldens | M | standard | 3 |
| 10 | HangulTalk 1.0 goldens (Python + C) | S | cheap | 1 |
| 11 | tool consumers (svfline, facecheck, maker, svf2to3, mkindex) | S | standard | 3 |
| 12 | Uno preset manifest, verify and regen | S | standard | 1 |
| 13 | Uno sketch presets + sizes | M | standard | 12, 7 |
| 14 | Python BIG (jamoset, writers, jamoadapt, macfbit_svf, spec) | M | standard | 11 |
| 15 | `svf_synth` BIG kinds | S | standard | 14 |
| 16 | C BIG reader | M | standard | 15, 7 |
| 17 | BIG defaults, feature rows, sizes, fuzz, bench | M | standard | 16 |
| 18 | identity sweep, records, follow-ups | S | cheap | all |

Execution is strictly sequential (one implementer at a time). Shared files, which is why:

| files / interfaces | tasks |
|---|---|
| `c/src/svf_jamo.c`, `c/include/svf.h` (status bits, switches, `svf_face` fields) | 5, 6, 7, 16, 17 |
| `c/src/svf_internal.h` (`SVF__JSET_MAX`, `SVF__JSET_LOAD_MAX`) | 6, 16 |
| `c/tests/svfdump.c` (`info` keys) | 5 |
| `tools/test_c_renderer.py` (`READER_FLAGS`, `expected_syllables`, kind lists) | 5, 6, 7, 8, 10, 16, 17 |
| `tools/jamoset.py` (`unpack`, `pieces_of`, `jset_line`, `Jmap`, limits) | 3, 9, 11, 14 |
| `tools/svf_synth.py` (`BAD_KINDS*`, `VARIANTS`, `JMAP_*`) | 4, 15 |
| `tools/macfbit_svf.py` | 9, 14 |
| `c/cross/check-features.sh`, `c/cross/SIZES.md` | 2, 7, 13, 17, 18 |
| `c/tests/fuzz_corpus.sh` | 8, 17 |
| `spec/SVF.md` | 3, 14 |
| `docs/tools.md` | 3, 4, 9, 11, 12, 14, 15 |
| `c/ports/arduino/*` | 13 |

---

### Task 1: Integrate the source branches

**Files:** merge commits only (`tools/macfbit3.py`, `tools/macfbit_svf.py`, `tools/jamofill.py`, `tools/jamomerge.py`,
their tests, `docs/tools.md`).

**Interfaces:** Produces on this branch: `tools/macfbit3.py` (`Fbit3(fbit, htbl).compose(hi, lo)`, `.codes()`,
`load_fbit`, `load_htbl1`), `tools/macfbit_svf.py` (`Fbit3`, `Htbl1`, `Build`, `face_glyphs`, `write_face`, `verify`,
`cverify`, `SET_LIMITS = (32, 24, 16)`, `CLASS_LIMIT = 12`), `tools/jamomerge.py` (`planes`, `merge`).

- [ ] **Step 1:** `git merge --no-edit main`, then `git merge --no-edit mac-fbit-svf`, then `git merge --no-edit
  uno-seoul` (each must report no conflict; a conflict is a stop-and-report).
- [ ] **Step 2:** Run `python3 -m unittest tools.test_tools_doc tools.test_macfbit_svf tools.test_macfbit3
  tools.test_jamomerge tools.test_jamofill tools.test_jamoset` - expected OK (skips allowed).
- [ ] **Step 3:** Run `~/.local/bin/heavy make -C c check` - expected exit 0 (no C file changed; sanity of the merge).
- [ ] **Step 4:** The merges are the commits (message of the last: "integrate main, mac-fbit-svf, uno-seoul for
  t_380104f8").

Reviewer checks: no file outside the three branches' diffs changed; `git diff 2fb312d --stat -- c/` empty.

### Task 2: `c/cross/check-features.sh` and the "Minimal config" table

**Files:**
- Create: `c/cross/check-features.sh`, `c/cross/test-check-features.sh`
- Modify: `c/cross/check-sizes-md.sh` (new mode `--features`), `c/cross/SIZES.md` (new section "Minimal config")

**Interfaces:**
- Produces: `sh c/cross/check-features.sh [OUT] [--uno NAME:FACE.SVF:MAXFLASH ...]` - prints one `features: OK` line
  and writes `OUT/features/rows.txt`, one line a build: `TOOLCHAIN CONFIG text rodata data bss` (TOOLCHAIN `avr` |
  `m0plus`; CONFIG `minimal`, `default`, `allon`, and later tasks add `minimal+JMAP`, `minimal+BIG`, `ksonly`). Configs
  are a table at the top of the script (`CONFIGS="name:flags ..."`), so Tasks 7 and 17 add rows, not code.
- Produces: `check-sizes-md.sh --features ROWS SIZES.md` compares the gated rows (`minimal` both toolchains,
  `default` m0plus) with the "Minimal config" table; `allon` rows are printed as `info` (not gated).
- Symbol rule: `check_absent CONFIG PREFIX...` runs `nm --defined-only` on the linked probe; a config lists the prefixes
  that must not appear (`pop4` without POP4; `svf_open_stream` with `SVF_NO_STREAM`; `svf__scale` with `SVF_NO_SCALE`;
  Tasks 7/17 add theirs). Strings rule: the linked probe's `.rodata*`/`.data` (`objcopy -O binary -j`) contain none
  of `JMAP`, `jmap`, `BIG` (the library has no strings; the 4-byte magic is compared byte by byte, never stored).

- [ ] **Step 1: Write the failing gate test** `c/cross/test-check-features.sh` (pattern of `test-build-all.sh`: fake
  rows/`nm` output through env hooks `FEATURES_ROWS_HOOK`, `FEATURES_NM_HOOK`):
  - rows equal to the table -> `features: OK`, exit 0;
  - `avr minimal` text 12921 -> exit 1, message names `avr minimal 12920 -> 12921 (+1)`;
  - nm output with `pop4` in a config that forbids it -> exit 1 naming the symbol;
  - `allon` growth -> exit 0 and an `info` line.
- [ ] **Step 2:** `sh c/cross/test-check-features.sh` - FAIL (script missing).
- [ ] **Step 3:** Implement `check-features.sh` with the toolchains, `COMMON` flags and P1 probe link of `build-all.sh`
  (`-Os -ffunction-sections -fdata-sections`, `--gc-sections`, `c/cross/probe.c` `-DPROFILE=P1`); configs: `minimal` =
  the Uno flags; `default` = P1 (`build-all.sh`'s P1 flags); `allon` = every switch 1, `SVF_TARGETS` default. `--uno`
  rebuilds the Arduino image of `build-all.sh`'s `port arduino` with FACE and fails above MAXFLASH (PR-22).
- [ ] **Step 4:** Add "Minimal config" to `SIZES.md` with the measured rows; they must equal AVR **12920**, M0+
  minimal **6146**, M0+ default **7441** (a difference is a stop-and-report: the flags differ from P1's).
- [ ] **Step 5:** `sh c/cross/test-check-features.sh` -> `check-features-gates: OK`; `~/.local/bin/heavy sh
  c/cross/check-features.sh /tmp/feat` -> `features: OK`; `sh c/cross/test-build-all.sh` still OK.
- [ ] **Step 6: Commit** `c/cross/check-features.sh c/cross/test-check-features.sh c/cross/check-sizes-md.sh
  c/cross/SIZES.md` - "c/cross: check-features.sh - minimal/default/all-on size gate and symbol checks (t_380104f8)".

Reviewer checks: the minimal flags equal the Arduino README line verbatim; a missing toolchain fails (never skips);
the gate compares text by exact equality.

### Task 3: Python JMAP format (`jamoset.py`) and `spec/SVF.md`

**Files:**
- Modify: `tools/jamoset.py` (after the JSET v1 section), `tools/test_jamoset.py` (class `JmapFormat`),
  `spec/SVF.md` ("Jamo sets": a "Version 3: mapping table (JMAP)" subsection), `docs/tools.md` (jamoset section)

**Interfaces (Produces):**
- Constants: `JMAP_VERSION = 3`, `JMAP_FLAG_4B = 0x01`, `JMAP_FLAG_SPARSE = 0x02`, `JMAP_FLAG_FALLBACK = 0x04`,
  `JMAP_COMPAT_OFF = 16`, `JMAP_RANK_OFF = 118`, `JMAP_BITMAP_OFF = 206`, `JMAP_PAD_OFF = 1603`,
  `JMAP_SPARSE_ENTRIES = 1604`, `JMAP_DENSE_ENTRIES = 118`, `JMAP_REGION_MAX = 65534`.
- `class Jmap`: `advance: int`, `pi, pm, pf: int`, `entries: dict[int, tuple[int, int, int]]` (syllable index s ->
  plane indices, 0 = none), `block_compat: list[int]` (51, `BLANK` = 0xFFFF), `fallback: Tables | None`,
  `compat: list[int]` (effective: `block_compat[k]` unless blank, else `fallback.compat[k]`, PR-10), `version = 3`.
  Method `pieces(cp: int) -> list[int] | None` (PR-9; a miss returns `pieces_of(self.fallback, cp)` or None).
- `jmap_size(ns: int, four: bool, sparse: bool, fallback_len: int = 0) -> int`.
- `pack_jmap(jm: Jmap, fallback_block: bytes | None = None) -> bytes`: chooses 4B iff any count > 255, SPARSE iff
  `len(entries) < 11172`; ValueError over any limit or past `JMAP_REGION_MAX`.
- `unpack_jmap(data: bytes) -> Jmap`: rules R1-R7 below, ValueError whose text starts `JMAP ` and names the rule.
- `jmap_from_tables(t: Tables, syllables: Iterable[int], glyphs: dict[int, bytes], pad=(0, 0, 0)) -> tuple[Jmap,
  dict[int, bytes]]`: per-plane contiguous pieces from a JSET face (a glyph used in two planes is copied, `pad` adds
  unused distinct pieces per plane), the new `{cp: cell}` piece glyphs; used by `svf_synth` and tests.
- Changed: `unpack(data)` returns `unpack_jmap(data)` for version 3; `pieces_of(t, cp)` returns `t.pieces(cp)` for a
  `Jmap`; `used_pieces(t)` and `jset_line(data)` accept a `Jmap` (`jset_line` -> `jset=v3 jmap=<bytes> ns=<NS>
  fallback=v1|v2|none`). `compose` is unchanged (it calls `pieces_of`).
- Validation rules (the C reader of Task 6 implements the same, same order):
  R1 length >= 118, magic, version 3, flags & 0xF8 == 0; R2 counts per 3B/4B limits, PI+PM+PF >= 1; R3 NS (SPARSE
  1..11,172, dense == 11,172); R4 length: region <= 65,534; no FALLBACK: length == F; FALLBACK: length >= F + 12, the
  fallback unpacks as version 1 or 2 and its advance byte equals the JMAP advance; R5 compat blank or < PI+PM+PF; R6
  SPARSE: pad 0, bits 11,172..11,175 zero, `rank[b]` == bits below `b * 256` for b = 0..43, total == NS; R7 every
  entry field <= its plane count. (R8 "every piece below PI+PM+PF has a glyph" is the caller's, as for JSET.)

- [ ] **Step 1: Write the failing tests** in `tools/test_jamoset.py` class `JmapFormat`:
  - `test_sizes`: `jmap_size(2350, False, True) == 8654`; `jmap_size(11172, False, False) == 33634`;
    `jmap_size(11172, True, False) == 44806`; `jmap_size(11172, True, True) == 46292`.
  - `test_round_trip`: for (sparse 3B, 2,350 KS syllables), (dense 4B, PI 300), (SPARSE + FALLBACK v1), (SPARSE +
    FALLBACK v2) built with `jmap_from_tables` from `tools/testdata` or `svf/iolo/HGKEY6J.SVF`:
    `pack_jmap(unpack_jmap(b), ...) == b` and `unpack(b)` is a `Jmap` with equal `entries`.
  - `test_pack_chooses_flags`: PI 255 -> flags & 1 == 0; PI 256 -> 1; 2,350 entries -> SPARSE; 11,172 -> dense.
  - `test_rules_refused`: one mutated block per rule, `assertRaisesRegex(ValueError, "^JMAP ")`: length 117; flags
    0x08; 3B PI 256; 4B PI 2048; 4B PF 1024; PI = PM = PF = 0; SPARSE NS 0; dense NS 11,171; length F + 1 without
    FALLBACK; FALLBACK with 11 bytes; fallback version 3; fallback advance + 1; compat = PI+PM+PF; pad 1; bitmap bit
    11,172 set; rank[10] + 1; NS = popcount + 1 (length adjusted); entry i = PI + 1; 4B entry f = PF + 1 via b0 bits 6-7;
    a FALLBACK region of 65,535 B.
  - `test_pieces_and_compose`: for a SPARSE face, `pieces_of(jm, 0xAC00 + s)` equals `[i - 1, PI + m - 1] + ([PI + PM +
    f - 1] if f else [])` with 0 -> `BLANK`; a miss without fallback is None; with fallback equals the fallback's
    `pieces_of`; advance 0 survives the round trip.
  - `test_jset_line_v3`: `jset_line` of a written face starts `jset=v3 jmap=8654 ns=2350 fallback=none` for the
    SEOUL12J-shaped case.
- [ ] **Step 2:** `python3 -m unittest tools.test_jamoset.JmapFormat` - FAIL (names undefined).
- [ ] **Step 3:** Implement the interfaces above in `tools/jamoset.py`; `spec/SVF.md` gets the byte table, rules
  R1-R8, the lookup formula, PR-9/PR-10/PR-11 behaviour and the reader statuses (PR-4); `docs/tools.md` lists the new
  functions.
- [ ] **Step 4:** `python3 -m unittest tools.test_jamoset tools.test_tools_doc` - PASS (the old tests unchanged).
- [ ] **Step 5: Commit** - "jamoset: JSET block version 3 (JMAP) pack/unpack/size/compose; spec/SVF.md (t_380104f8)".

Reviewer checks: rule order matches the list (each rule reads only bytes earlier rules bounded); no change to any v1/v2
function's output (`git diff` touches only dispatch lines there); the 4B bit split is b0 bits 0-2 / 3-5 / 6-7.

### Task 4: `svf_synth.py` JMAP variants and bad kinds

**Files:** Modify `tools/svf_synth.py`, `docs/tools.md`; Test: `tools/test_c_renderer.py` (Python-only checks in
class `SynthJmap`, no C).

**Interfaces:**
- Consumes: `jamoset.jmap_from_tables`, `pack_jmap`, `unpack_jmap`.
- Produces: `JMAP_VARIANTS = ("sparse3", "sparse4", "dense3", "dense4", "hybrid1", "hybrid2", "adv0", "blanks",
  "pi2047")` (hybrid1/2: 16 exception syllables + fallback v1/v2 of the base; sparse4/dense4: `pad` to PI 300;
  blanks: some entries with m = 0 and tail syllables with f = 0; pi2047: 4B at PI 2047, PM 1, PF 1).
  `JMAP_BAD_KINDS = ("jmap_short", "jmap_flags", "jmap_pi256_3b", "jmap_pi2048_4b", "jmap_pf1024_4b",
  "jmap_zero_pieces", "jmap_ns0", "jmap_dense_ns", "jmap_length", "jmap_fallback_short", "jmap_fallback_bad",
  "jmap_fallback_v3", "jmap_fallback_adv", "jmap_compat_over", "jmap_pad", "jmap_bitmap_tail", "jmap_rank_wrong",
  "jmap_ns_popcount", "jmap_entry_over", "jmap_entry_over_4b", "jmap_missing_piece", "jmap_region_max", "v2_as_v3")`.
  CLI `--jmap-variant V`, `--jmap-bad KIND` (both `--from FACE`). `BAD_KINDS`: `version3` -> `version4` (PR-12).
- `jmap_region_max` sets the header's JSET size to 0x10000 over a file that holds it (the clip case, PR-7).

- [ ] **Step 1: Failing tests** `SynthJmap.test_variants_unpack`: every variant's face -> `jamoset.unpack` is a `Jmap`;
  `test_bad_kinds_refused`: every JMAP bad kind but `jmap_missing_piece` and `jmap_region_max` -> `unpack_jmap` raises
  (those two: unpack passes; R8 / the clip are reader rules); `test_version4_kind`: `version4` block refused by
  `unpack` with "JSET version 4".
- [ ] **Step 2:** run `python3 -m unittest tools.test_c_renderer.SynthJmap` - FAIL.
- [ ] **Step 3:** implement; rename every `version3` use (`grep -rn version3 tools c`).
- [ ] **Step 4:** PASS; also `python3 -m unittest tools.test_tools_doc`.
- [ ] **Step 5: Commit** - "svf_synth: JMAP variants and bad kinds; version3 kind is version4 (t_380104f8)".

Reviewer checks: every kind breaks exactly one rule (unpack's message names that rule); no Apple data; variants built
from `svf/iolo/HGKEY6J.SVF` only.

### Task 5: C status split and the no-JMAP recognition

**Files:** Modify `c/include/svf.h` (three status bits, `svf_is_jamo` comment), `c/src/svf_jamo.c` (`jset_valid`,
`svf__jset_check`, `svf_is_jamo`, recognition), `c/tests/svfdump.c` (`info` keys), `tools/test_c_renderer.py`,
`c/cross/SIZES.md` ("Minimal config" rows updated with the measured recognition cost).

**Interfaces:**
- `#define SVF_FACE_JSET_UNREAD 0x0010u`, `SVF_FACE_JMAP_BAD 0x0020u`, `SVF_FACE_JMAP_UNREAD 0x0040u`.
- `static int jset_valid(svf_face *f)` returns 1 usable, 0 bad, -1 unread (PR-4).
- `static int jmap_fallback(svf_face *f)` (`#if !SVF_JMAP`): sets `JMAP_UNREAD`; returns 1 after re-pointing
  `jset_off`/`jset_len` at a fallback (PR-6), else 0.
- `svf_is_jamo(f)` = `f && (f->jset_lc != 0)` in this task (Task 6 adds `|| f->jmap_off`).
- `svfdump FACE info` appends ` jset_unread=%d jmap_bad=%d jmap_unread=%d` at the end of its line.

- [ ] **Step 1: Failing tests** in `tools/test_c_renderer.py`:
  New `READER_FLAGS`: `"nojmap": "-DSVF_JMAP=0"`, `"v1nojmap": "-DSVF_JSET_V2=0 -DSVF_JMAP=0"` (explicit, so these
  tests keep their meaning after Task 7 turns JMAP on for host builds).
  - `test_status_unread_bits`: v1-only build (`build_reader("v1only")`) on the v2 re-encode of `SYNTH_BASE`: `jamo=0
    jset_bad=0 jset_unread=1`; v2-only build on `SYNTH_BASE`: same; `version4` kind: `jset_bad=1 jset_unread=0`.
  - `test_jmap_unread_plain`: `build_reader("nojmap")` on `sparse3`, `dense4`: `jamo=0 jmap_unread=1
    jset_bad=0`, syllables equal `expected_syllables(data, plain=True)`; mapped, every `STREAM_CONFIGS`, rd8.
  - `test_jmap_unread_fallback`: `hybrid1` on `nojmap` and `v1nojmap`: `jamo=1 jmap_unread=1`, syllables equal the
    fallback's composition (`expected_syllables(data, jmap=False)`, a new keyword that composes from
    `jm.fallback` alone); `hybrid2` on `v1nojmap`: `jamo=0 jmap_unread=1 jset_unread=1`.
  - `test_jmap_unread_bad_fallback`: `jmap_fallback_bad` on `nojmap`: `jamo=0 jmap_unread=1 jset_bad=1`.
  - Update `assert_plain_everywhere(..., unread=True)` callers to expect `jset_unread=1` instead of `jset_bad=1`.
- [ ] **Step 2:** run the four tests - FAIL.
- [ ] **Step 3:** implement; `expected_syllables` gains `jmap=True`.
- [ ] **Step 4:** tests PASS; `~/.local/bin/heavy make -C c check` exit 0; `~/.local/bin/heavy sh
  c/cross/check-features.sh /tmp/feat`: record the minimal growth (AVR <= 40 B, M0+ <= 24 B; above = stop and report);
  update the "Minimal config" table and its note "includes the JMAP recognition (+N B)".
- [ ] **Step 5: Commit** - "c: distinct JSET_UNREAD / JMAP_UNREAD status; JMAP fallback recognition (t_380104f8)".

Reviewer checks: recognition reads nothing past 16 bytes before `F + 12 <= jset_len` is proven (`uint32_t` F); no new
symbol in the minimal build except inside existing functions; `svf_is_jamo` callers (`test_args.c`, `fuzz_open.c`,
`svf_web.c`, `svfdump.c`) still compile and mean "composes something".

### Task 6: C JMAP reader (`SVF_JMAP`)

**Files:** Modify `c/include/svf.h` (switch doc + temporary default 0 everywhere until Task 7, `svf_face` fields),
`c/src/svf_jamo.c`, `c/src/svf_internal.h`, `tools/test_c_renderer.py` (`READER_FLAGS["jmap"] = "-DSVF_JMAP=1"`,
`"jmap_trusted"`, `"ksonly"`), `c/tests/test_args.c` (one JMAP case).

**Interfaces:**
- `svf_face` under `#if SVF_JMAP`: `uint32_t jmap_off;` (block start in `data`, 0 = none usable) `uint16_t jmap_pi,
  jmap_pm;` `uint8_t jmap_flags;` (+9 B).
- `static int jmap_valid(svf_face *f)` (R1-R8 of Task 3; TRUSTED keeps R1-R4, PR-20); on success records the fields,
  sets `jset_adv` to the JMAP advance and, with FALLBACK, re-points `jset_off`/`jset_len` at the fallback and runs
  `jset_valid` on it (failure -> the whole block `JMAP_BAD`, PR-4).
- `static int jmap_pieces(const svf_face *f, uint32_t cp, uint16_t out[3])` returns 0 miss, 1 compat, 2 or 3.
- `svf_jamo_pieces` tries `jmap_pieces` first, then the JSET part; `svf__composed` per PR-5.
- `svf_internal.h`: `SVF__JSET_LOAD_MAX` is `65534u` under `SVF_JMAP` (PR-7).
- `svf.h` `#error` text: "SVF_JSET_V1, SVF_JSET_V2 and SVF_JMAP are all 0: at least one reader is needed" (PR-14).

- [ ] **Step 1: Failing tests** (all on `build_reader("jmap")`, ASan, mapped + every `STREAM_CONFIGS` + rd8):
  - `test_jmap_variants_compose`: each `JMAP_VARIANTS` face: `jamo=1 jmap_bad=0`, `syllables` == `expected_syllables`
    (which now composes through `Jmap`), `glyphs` == `expected_glyphs`.
  - `test_jmap_bad_kinds_plain`: each `JMAP_BAD_KINDS` face: `jamo=0 jmap_bad=1`, plain syllables, no sanitizer line.
  - `test_jmap_advance_zero`: `adv0`: a composed syllable's `svfdump glyphs` advance == `cell_w`.
  - `test_jmap_trusted_draws_identically`: `build_reader("jmap_trusted")` == `build_reader("jmap")` on every variant.
  - `test_jmap_ks_only_build`: `ksonly` (`-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0`): `sparse3` composes; `hybrid1`:
    `jamo=1 jset_unread=1`, KS hits only; `SYNTH_BASE`: `jamo=0 jset_unread=1`.
  - `test_jmap_reader_off_unchanged`: the default build (JMAP 0 here) still gives Task 5's results.
- [ ] **Step 2:** run them - FAIL.
- [ ] **Step 3:** implement. Lookup uses `popcount(RD(byte))` over at most 32 bytes; 4B fields from b0 as in Global
  Constraints; every multiply in `uint32_t`.
- [ ] **Step 4:** PASS; `~/.local/bin/heavy make -C c check` exit 0.
- [ ] **Step 5: Commit** - "c: JMAP reader behind SVF_JMAP (validation, lookup, trusted, KS-only build) (t_380104f8)".

Reviewer checks: rules in Task 3's order, each reading only bounded bytes (the rank loop never reads past byte 1602);
`jmap_off` cleared and `JMAP_BAD` set on every failure path; with `SVF_JMAP=0` the object has no `jmap` symbol and no
extra `svf_face` byte (`face_size.c`).

### Task 7: Switch defaults, KS-only, feature rows, port sizes

**Files:** Modify `c/include/svf.h` (PR-13 defaults), `tools/test_c_renderer.py` (`test_jset_defaults_per_target`),
`c/cross/check-features.sh` (configs `minimal+JMAP`, `ksonly`, `allon` with JMAP; absent-symbol rule `jmap_` when
JMAP 0), `c/cross/build-all.sh` (`--switches` columns `JMAP` for M0+ and AVR), `c/cross/SIZES.md` (Size switches
columns, port rows dos/web/sdl re-measured, Minimal config), `c/ports/arduino/README.md` (flags note).

**Interfaces:** svf.h after the change: `SVF_JMAP` 1 iff not `__AVR__`, not `SVF_SMALL` and one of `__unix__ _WIN32
__APPLE__ __DJGPP__ __EMSCRIPTEN__`; else 0; `-DSVF_JMAP=` wins.

- [ ] **Step 1: Failing test** `test_jset_defaults_per_target` prints `JSET SVF_JSET_V1 SVF_JSET_V2 SVF_JSET_POP4
  SVF_JSET_TRUSTED SVF_JMAP`; assertions: host `(1, 1, 1, 0, 1)`; `-DSVF_SMALL` `(1, 1, 0, 0, 0)`; `-D__AVR__` `(1, 0,
  0, 0, 0)`; `-U__unix__ -U__linux__ -Uunix -Ulinux` `(1, 1, 1, 0, 0)`; `-D__AVR__ -DSVF_JMAP=1` JMAP 1; `-D__AVR__
  -DSVF_JSET_V1=0` fails with "at least one reader"; `-D__AVR__ -DSVF_JSET_V1=0 -DSVF_JMAP=1` preprocesses.
- [ ] **Step 2:** FAIL; **Step 3:** implement the defaults; tests that used `build_reader("jmap")` keep it (explicit).
- [ ] **Step 4:** `python3 -m unittest tools.test_c_renderer` PASS; `~/.local/bin/heavy sh c/cross/check-features.sh
  /tmp/feat` -> `features: OK` (minimal and M0+ default unchanged since Task 5); `~/.local/bin/heavy sh
  c/cross/build-all.sh /tmp/ba` and `--ports /tmp/bp` exit 0 after the SIZES.md update (expected movers: `port-dos`
  SVFDEMO.EXE, `port-web` svf.wasm, `port-sdl` programs; every AVR, Cortex-M, ESP32, CH582 row unchanged - a mover
  there is a stop-and-report). Record `minimal+JMAP` and `ksonly` rows (estimates: JMAP M0+ +300..450 B, AVR
  +450..700 B; outside the band = report).
- [ ] **Step 5: Commit** - "c: SVF_JMAP defaults (desktop/DOS on, MCU off), feature rows, sizes (t_380104f8)".

Reviewer checks: the arm/avr/esp/riscv defaults are 0 (`check-features.sh` asserts `arm-none-eabi-gcc -dM -E` and
`avr-gcc -dM -E` print `SVF_JMAP 0`); EXPECT_OK of `build-all.sh` stays 43.

### Task 8: Fuzz seeds and runs (JMAP)

**Files:** Modify `c/tests/fuzz_corpus.sh` (seeds: every `JMAP_VARIANTS` and `JMAP_BAD_KINDS` face from HGKEY6J, in
the default and mcu-strict profiles), `c/tests/fuzz_open.c` (nothing if it already compiles every source; else the
`-DSVF_JMAP=1` line), `c/Makefile` (fuzz targets built with `-DSVF_JMAP=1`; `fuzz-open-strict` also a `-DSVF_JMAP=0`
twin `fuzz-open-nojmap` for the recognition path).

- [ ] **Step 1:** `make -C c fuzz-corpus` prints the seed counts; the count line grows by `2 x (9 + 23)` = 64 seeds.
- [ ] **Step 2:** `~/.local/bin/heavy make -C c fuzz-smoke` exit 0.
- [ ] **Step 3:** one hour each: `fuzz-open`, `fuzz-open-rd`, `fuzz-open-nojmap` (`-max_total_time=3600`), no crash;
  record execs and coverage lines in the commit message.
- [ ] **Step 4: Commit** - "c/tests: JMAP fuzz seeds, no-JMAP fuzz twin; 1 h runs clean (t_380104f8)".

Reviewer checks: the corpus script stays `set -e` and deterministic; no seed larger than `-max_len`.

### Task 9: `macfbit_svf.py --mode direct` and the type-3 goldens

**Files:** Modify `tools/macfbit_svf.py`, `tools/test_macfbit_svf.py`, `docs/tools.md`.

**Interfaces:**
- `def direct_jmap(fb: Fbit3, ht: Htbl1, dedup: bool = True) -> tuple[jamoset.Jmap, dict[int, int]]`: plane lists in
  slot order (initial, medial, final; a slot belongs to the plane it is referenced in, a slot in two planes is a stop -
  the Mac's are disjoint), dedup within a plane (PR-8), entries for the 2,350 KS syllables, compat per PR-10;
  returns the Jmap and `{piece number: slot}`.
- `def write_direct(fb, ht, latin=None, dedup=True, with_jset=None, ascent=None) -> tuple[bytes, dict]`; `with_jset`
  is the derived `Build` whose JSET becomes the fallback (`--with-jset`, `--jset-version` applies to it).
- `def verify_direct(data: bytes, fb_bytes: bytes, htbl_bytes: bytes) -> dict` compares with
  `macfbit3.Fbit3(fbit, htbl).compose(hi, lo)` for every `codes()` entry (2,350 + 51): `{"ks_bad": [...],
  "compat_bad": [...], "non_ks_present": n}` (n = 0 without fallback).
- CLI: `build ... --mode direct|derived` (default direct, PR-17) `--no-dedup` `--with-jset`; `verify FACE FBIT HTBL
  [--classes C] [--svfdump PATH ...]` detects the mode from the face; the report gains `mode`, `jmap` (bytes),
  `pieces_as_slots`, `pieces`.

- [ ] **Step 1: Failing tests** (synthetic fixture `synthetic()` of the existing test file, no Apple data):
  - `test_direct_golden`: `verify_direct` -> `ks_bad == []`, `compat_bad == []`, `non_ks_present == 0`; a plane slot
    count equals the referenced slots of the fixture per plane.
  - `test_direct_dedup_default`: default pieces == distinct bitmaps per plane; `--no-dedup` pieces == referenced slots;
    both compose identically for 2,401 codes.
  - `test_direct_with_jset`: `--with-jset` -> FALLBACK set; non-KS syllables compose to the derived face's pixels.
  - `test_derived_unchanged`: `--mode derived` bytes == the bytes `write_face` gave before this task (the test builds
    both from the fixture through the old function kept as `write_face`).
  - `test_direct_c_reader` (skip without a C compiler): `cverify`-style run of a `-DSVF_JMAP=1` svfdump: 2,350 KS + 51
    compat equal the Mac composition, mapped and `--stream=4:512`.
  - `RealFaces` class (skip unless `SVF_MAC71_INPUTS` names a directory holding `<Name>.fbit` and `<Name>.htbl1` for
    Seoul12, AppleGothic12, AppleGothic24, AppleMyungjo12, AppleMyungjo24): each `ks_bad == compat_bad == []` in
    Python and C. Document in `docs/tools.md` how the user fills that directory from
    `<workdir>/hinting/out/mac-fbit-svf/scratch/InputBackSupport[INIT].rsrc__fbit_*.bin` and `..._HTBL_1.bin`.
- [ ] **Step 2:** FAIL; **Step 3:** implement; **Step 4:** PASS, and once locally with `SVF_MAC71_INPUTS` set: record
  in the commit message the five faces' sizes (SEOUL12J direct dedup *estimate* ~17.9 KB; out of band = note) and
  `ks_bad 0 compat_bad 0`.
- [ ] **Step 5: Commit** - "macfbit_svf: --mode direct (JMAP, dedup on) and type-3 goldens vs macfbit3 (t_380104f8)".

Reviewer checks: the 0x0E glyph byte is "no plane" as in `Htbl1`; entries are KS only (PR-17: no extrapolation);
faces written to the repo: none.

### Task 10: HangulTalk 1.0 goldens (all four fonts, Python + C)

**Files:** Modify `tools/test_jamoset.py` (class `MacFbit45Sets` generalised over `Gotic12`, `Munjo12`, `Munjo16`,
`Munjo24`), `tools/test_c_renderer.py` (`test_mac_fbit45_c_reader`).

- [ ] **Step 1: Failing tests:** for each font present under `<workdir>/johab-fonts/mac/extracted/kh10_system_disk/System
  Folder/` (skip per font when absent): the `--layout mac-fbit-45sets` face's 11,172 syllables equal
  `mac_kfont.HfntFont(...).johab(...)` (the existing `mac_glyph` method, cell size from the font); `(lc, tc, ni, nf)
  == (8, 4, 20, 4)` for Gotic12 (cross review (c)); the JSET is version 1 and `len(jset) == 3783` for Gotic12. C: the
  v1-only build (`build_reader("v1only")`) `svfdump syllables` equals the Python composition for all 11,172.
- [ ] **Step 2:** FAIL (Gotic12/Munjo12/16 not yet run); **Step 3:** parameterise; **Step 4:** PASS locally (4 fonts).
- [ ] **Step 5: Commit** - "tests: HangulTalk 1.0 goldens for Gotic12/Munjo12/16/24, Python and C v1 reader (t_380104f8)".

Reviewer checks: no font bytes copied into the repo; skips name the missing path.

### Task 11: Tool consumers of a JMAP face

**Files:** Modify `tools/svfline.py` (if it reads `t.lc`/tables directly), `tools/facecheck.py` (usable rule: R8 for
a `Jmap`), `maker/detect.py` (`usable_jset` returns a `Jmap` too; `jset_version` 3), `tools/svf2to3.py` (a v3 region
is copied verbatim; `--jset-version` applies to nothing there and prints a note; `--check` composes through svfline),
`web/mkindex.py` (jamo true for a JMAP face), tests in `tools/test_facecheck.py`, `tools/test_svf2to3.py`,
`tools/test_web_picker.py`.

- [ ] **Step 1: Failing tests:** `facecheck` of `sparse3` reports a jamo face with the KS syllables composed and
  non-KS absent; of `jmap_missing_piece` a plain face; `svf2to3 --profile mcu-strict --check` on `hybrid2` exits 0 and
  the output's JSET region bytes == the input's; maker detect kind `svf-jamo`, `jset_version` 3; `mkindex` jamo true.
- [ ] **Step 2:** FAIL; **Step 3:** implement; **Step 4:** PASS: `python3 -m unittest tools.test_facecheck
  tools.test_svf2to3 tools.test_web_picker tools.test_jamoset`.
- [ ] **Step 5: Commit** - "tools: svfline/facecheck/maker/svf2to3/mkindex read JMAP faces (t_380104f8)".

Reviewer checks: nothing re-encodes a JMAP block; pixel output of every existing face unchanged (tests unchanged).

### Task 12: Uno preset manifest, verify and regeneration

**Files:**
- Create: `c/ports/arduino/presets/seoul12.manifest`, `c/ports/arduino/presets.sh`, `c/ports/arduino/.gitignore` entry
  `presets/faces/`, `c/ports/arduino/test-presets.sh`
- Modify: `docs/tools.md` (no new tools/*.py), `c/ports/arduino/README.md` (section "Seoul presets")

**Interfaces:**
- Manifest lines `NAME BYTES SHA256 ORIGIN`:
  `S8K 8136 76b8877b4babd0a1b0169ffab93c005316e6ff434af1f21da9233ad33b21f0d9 rec1/SM8K`,
  `S7K 7012 2018ed8ac6a8111181ef696aa737e0181159cf1889f59c3602708b9551724576 rec2/SM7K`,
  `S6K 6144 dcd1b3bac68ba6530d6a561040d9736f298ba765e3e3e84dd4590077ecbed8aa rec2/SM6K`,
  `S5K 5548 70e91e565827be527e31cbc8e5e8256f774beec19bb7c0a4afdadafdf874da29 rec2/SM-stop`, and the inputs
  `SEOUL12J 12624 17e621c3cc6ec2da3ebe467626b4e6d726e20ba9fc1d769148841ea409d5b1c1 input`,
  `PLANES - ab6f5b9e9638dee321752d9b7cb8bc0b91293538a8f1ae4d661514d34a429021 input` (seoul12-planes.json).
- `presets.sh verify DIR` - each of S8K..S5K present in DIR as `NAME.SVF` with the manifest's bytes and sha256:
  `presets: OK 4 faces`; else exit 1 naming the face and the field.
- `presets.sh regen SEOUL12J.SVF PLANES.json OUTDIR` - verifies both inputs against the manifest, then runs
  `python3 tools/jamomerge.py merge --face SEOUL12J --planes PLANES --points 8192 --recog --prefix SM -o OUTDIR/rec1`
  and `... merge --face OUTDIR/rec1/SM8K.SVF --ref SEOUL12J --planes PLANES --soft --recog --points 7168 6144 --prefix
  SM -o OUTDIR/rec2`, copies SM8K/SM7K/SM6K/SM-stop to `OUTDIR/S8K..S5K.SVF`, then `verify OUTDIR`. Step 4 confirms the
  exact arguments by re-running once; if the logs of `<workdir>/hinting/out/uno-seoul/rec1|rec2` imply other arguments
  (step lines, `--batch`), use those and say so in the README.
- `presets.sh build DIR [OUT]` is added in Task 13.

- [ ] **Step 1: Failing test** `c/ports/arduino/test-presets.sh`: a temp DIR with four fake faces whose manifest is a
  temp copy (`PRESETS_MANIFEST` env override): `verify` -> OK; one byte flipped -> exit 1 naming `sha256`; one face
  missing -> exit 1 naming it; size wrong -> names `bytes`.
- [ ] **Step 2:** FAIL; **Step 3:** implement (POSIX sh, `sha256sum`); **Step 4:** PASS; `presets.sh verify
  <workdir>/hinting/out/uno-seoul/final` -> `presets: OK 4 faces`; run `regen` once (heavy, CPU 2 threads) and record
  in the README whether the four outputs reproduce the manifest (yes/no; no = the pinned files stay the reference).
- [ ] **Step 5: Commit** - "ports/arduino: Seoul preset manifest, verify and regeneration (faces stay out of git)
  (t_380104f8)".

Reviewer checks: `git ls-files c/ports/arduino` holds no `.SVF` and no generated face C file; the script never
writes into the repo tree except under the gitignored `presets/faces/`.

### Task 13: Uno sketch presets and sizes

**Files:** Modify `c/ports/arduino/arduino.ino`, `c/ports/arduino/presets.sh` (`build`), `c/ports/arduino/README.md`,
`c/cross/SIZES.md` (table "Uno presets"); Create `c/ports/arduino/uno_preset.h`.

**Interfaces:**
- `uno_preset.h`: `#define SVF_UNO_CUSTOM 0`, `SVF_UNO_S8K 1`, `SVF_UNO_S7K 2`, `SVF_UNO_S6K 3`, `SVF_UNO_S5K 4`;
  `#ifndef SVF_UNO_PRESET` -> `SVF_UNO_S8K`. The sketch keeps `extern const uint8_t svf_face_data[] PROGMEM;`.
- `presets.sh gen DIR` verifies DIR (Task 12), then writes `c/ports/arduino/face-S8K.c` .. `face-S5K.c` (gitignored
  `face-*.c`): each is `c/bench/mkface.py NAME.SVF ... --name svf_face_data --profile mcu-strict` output wrapped in
  `#include "uno_preset.h"` / `#if SVF_UNO_PRESET == SVF_UNO_<NAME>` ... `#endif`, so arduino-cli compiles all four and
  the macro picks one (default S8K). `SVF_UNO_CUSTOM` is the README's existing `face.c` path (unwrapped, any face);
  `build-all.sh --ports` keeps compiling its own HGKEY6J face from its out dir and is unaffected (PR-18).
  `scratch[32]` already covers the 12 x 12 cells (24 B).
- `presets.sh build` flags = the Uno flags of `build-all.sh` `port arduino`, the link and `avr-size -A` awk of
  `<workdir>/hinting/out/uno-sam12/scripts/cbuild.sh`; output one line a preset `NAME face text data bss flash ram`;
  compares with the "Uno presets" table and exits 1 on a difference; with no DIR faces it prints `presets: SKIPPED (no
  faces)` and exits 0.

- [ ] **Step 1: Failing check:** add the "Uno presets" table to `SIZES.md` with the reference values measured by
  uno-seoul's `cbuild.sh` (flash / RAM): S8K 21,696 / 1,103; S7K 20,572 / 1,103; S6K 19,704 / 1,103; S5K 19,108 /
  1,103; run `presets.sh build <workdir>/hinting/out/uno-seoul/final` - FAIL (no `build`).
- [ ] **Step 2:** implement; re-measure; the table takes the measured numbers (a difference from the references above
  of more than the scratch buffer change is a note in the README, not a stop).
- [ ] **Step 3:** `presets.sh build` exit 0 for all four; `~/.local/bin/heavy sh c/cross/build-all.sh --ports /tmp/bp`
  exit 0 with the arduino row unchanged (22,266 B) and 43 OK lines; host `svfdump-v1` (Uno flags, `cbuild.sh` line 1)
  `syllables` of each preset equals `jamoset.compose` (11,172).
- [ ] **Step 4: Commit** - "ports/arduino: Seoul presets S8K (default) .. S5K by SVF_UNO_PRESET; sizes (t_380104f8)".

Reviewer checks: default preset is S8K when no macro is given; the README says where the faces come from and that
they are research-only; no face bytes committed.

### Task 14: Python BIG (jamoset, writers, jamoadapt, macfbit_svf, spec)

**Files:** Modify `tools/jamoset.py`, `tools/jamoadapt.py`, `tools/macfbit_svf.py`, `tools/svf2to3.py`, every CLI that
calls `add_jset_version_arg` (`grep -n add_jset_version_arg tools/*.py`), `spec/SVF.md` (limits paragraph and the v2
compat byte), `docs/tools.md`, `tools/test_jamoset.py`.

**Interfaces:**
- `JSET_LIMITS = {"std": (12, 12, 32, 24, 16), "big": (19, 28, 128, 128, 64)}`; `_check_counts(lc, tc, ni, nm, nf,
  big=False)`; refusal text `JSET {name} {v} is not 1..{hi}` + ` (--jset-big allows 19 x 28 classes, 128/128/64
  sets)` when the BIG row would accept it.
- `pack(t, big=False)`, `pack_v1(t, big=False)`, `pack_jset(t, version, big=False)`; `unpack(data)` accepts BIG
  counts (PR-16); `needs_big(t) -> bool`; `class_limits(big: bool) -> tuple[int, int]`; `MAX_LEAD_CLASSES`,
  `MAX_TAIL_CLASSES` stay 12. v2 compat decode: `c & 0x7F` < the count of its table (one rule for both rows).
- `add_jset_version_arg(ap, default=1)` also adds `--jset-big` (store_true); writers pass `big=args.jset_big`.
- `jset_line` appends ` big=1` when `needs_big`.
- `jamoadapt.py`: `FORMAT_LIMITS = {"std": (32, 24, 16), "big": (128, 128, 64)}`, `CLASS_LIMITS = {"std": (12, 12),
  "big": (19, 28)}`, `CLASS_LIMIT = 12` kept; `adapt(..., class_limit=None)` takes an int or a (lead, tail) pair.
- `macfbit_svf.py`: `--jset-big` sets `search_classes(max_lc=19, max_tc=28)` and `fit_limits(limits=(128, 128,
  64))` for `--mode derived` and `--with-jset`.

- [ ] **Step 1: Failing tests** (`test_jamoset.py` class `JsetBig`):
  - `test_big_sizes`: `_jset_size_v1(19, 28, 128, 128, 64) == 47373`; `jset_size(19, 28, 128, 128, 64) == 29708`;
    `jset_size(19, 28, 128, 128, 64, na=6848) == 45068`.
  - `test_pack_refuses_without_big`: tables at (13, 12, 32, 24, 16) and (12, 12, 33, 24, 16): `pack`, `pack_v1` raise
    with "--jset-big"; with `big=True` they pack and `unpack` round-trips.
  - `test_big_limits_round_trip_and_compose`: `limits_tables(19, 28, 128, 128, 64)` (helper copied from
    `test_c_renderer.py` into a shared spot or imported) packs v1 and v2 with `big=True`; `unpack` + `compose` of all
    11,172 syllables equals the tables' own `pieces_of`.
  - `test_big_plus_one_refused`: (20, 28, ...), (19, 29, ...), (.., 129, ..), (.., .., 129, ..), (.., .., .., 65)
    refused even with `big=True`.
  - `test_compat_7bit`: a v2 compat byte `0x40` (set 64 of an initial table of 128 sets) decodes; `0xBF` (final set 63,
    bit-7 form) decodes; `0xFF` is blank.
  - `test_narrow_bytes_unchanged`: for every face under `svf/` (`faces()` of test_c_renderer), `pack_jset(t, v,
    big=True) == pack_jset(t, v)` for v in (1, 2).
  - `test_jset_line_big`: ` big=1` present for a BIG face, absent for HGKEY6J.
  - `jamoadapt`: `FORMAT_LIMITS["big"] == (128, 128, 64)`, `CLASS_LIMITS["big"] == (19, 28)`.
- [ ] **Step 2:** FAIL; **Step 3:** implement; **Step 4:** PASS: `python3 -m unittest tools.test_jamoset
  tools.test_macfbit_svf tools.test_svf2to3 tools.test_tools_doc`; `python3 tools/svf2to3.py --tree svf /tmp/t14`
  produces bytes identical to the same command at the Task 13 commit (`cmp -r` style loop, 153 files).
- [ ] **Step 5: Commit** - "jamoset: JSET limit lift (19 x 28, 128/128/64) behind --jset-big; tools follow
  (t_380104f8)".

Reviewer checks: no writer emits a BIG table without the flag; the narrow-caps refusal still triggers in narrow mode
at exactly 13/13/33/25/17; spec text and Global Constraints numbers agree.

### Task 15: `svf_synth` BIG kinds

**Files:** Modify `tools/svf_synth.py`, `docs/tools.md`, `tools/test_c_renderer.py` (`SynthBig`, Python only).

**Interfaces:** `BAD_KINDS_STD = ("lc13", "tc13", "ni33", "nm25", "nf17")` (bad on narrow readers, valid on BIG);
`BAD_KINDS_BIG = ("lc20", "tc29", "ni129", "nm129", "nf65")`; `BAD_KINDS` = the other existing kinds + `BAD_KINDS_BIG`
(no longer containing the STD five); `VARIANTS` + `"limits_big"` (19 x 28, 128/128/64, NA 0) and `"limits_big_alias"`
(every slot an alias, 45,068 B); `--jset-version 1|2` both supported for the BIG kinds and variants.

- [ ] **Step 1: Failing tests** `SynthBig`: `limits_big` v2 block length 29,708, v1 47,373; `limits_big_alias` 45,068;
  each `BAD_KINDS_BIG` refused by `jamoset.unpack`; each `BAD_KINDS_STD` accepted by `unpack` (BIG read) and refused by
  `pack(t)` narrow.
- [ ] **Step 2:** FAIL; **Step 3:** implement; update the `test_c_renderer` lists that iterate `BAD_KINDS` (Task 16
  moves the STD five into the narrow-build tests).
- [ ] **Step 4:** PASS; **Step 5: Commit** - "svf_synth: BIG limit kinds and variants (t_380104f8)".

Reviewer checks: every BIG kind is exactly one past one cap; the STD kinds keep their bytes.

### Task 16: C BIG reader (`SVF_JSET_BIG`)

**Files:** Modify `c/include/svf.h` (switch doc; temporary default 0 until Task 17), `c/src/svf_jamo.c`,
`c/src/svf_internal.h`, `tools/test_c_renderer.py` (`READER_FLAGS["big"] = "-DSVF_JSET_BIG=1"`, `"big_v1"`,
`"big_trusted"`, `"narrow"`).

**Interfaces:**
- `limits[5]` is `{19, 28, 128, 128, 64}` under `SVF_JSET_BIG`, else `{12, 12, 32, 24, 16}` (one row either way);
  the v1 literal checks (`svf_jamo.c:243-245`) read the same five numbers under `#if SVF_JSET_BIG`.
- `#if SVF_JSET_BIG` typedef `svf__bits_t` = `uint32_t`, else `unsigned`, used for `cell_set`'s `bit`, `row_at`'s
  set-table length and both `final_classes` (with `(svf__bits_t)1 << c`).
- v2 compat under BIG: `(c & 0x7F) >= RD(b + 8 + t)` (bit-5/6 test dropped, Global Constraints); narrow code unchanged.
- `SVF__JSET_MAX` 45068 under BIG; `SVF__JSET_LOAD_MAX` 47373 (BIG + V1) / 45068 (BIG, no V1), JMAP's 65534 wins.

- [ ] **Step 1: Failing tests:**
  - `test_set_limits_big`: on `big` and `big_v1` builds, `limits_big` (v2) and its v1 re-encode: `jamo=1`, 11,172
    syllables + 51 compat == `expected_syllables`, mapped, every `STREAM_CONFIGS`, rd8; `limits_big_alias` the same.
  - `test_big_plus_one_plain`: each `BAD_KINDS_BIG` on `big`: `jamo=0 jset_bad=1`.
  - `test_std_kinds_by_build`: each `BAD_KINDS_STD` plain (`jset_bad=1`) on `narrow`, jamo on `big`.
  - `test_set_limits_32_24_16` runs on `narrow` (its 33/25/17 cases are BIG-valid).
  - `test_big_trusted_draws_identically`: `big_trusted` == `big` on the valid faces + `limits_big`.
  - `test_narrow_hot_path_identical`: `arm-none-eabi-gcc -mcpu=cortex-m0plus -Os -ffunction-sections` objdump of the
    function symbols of `svf_jamo.o` that hold the v1/v2 lookup (`svf_jamo_pieces` and whichever of `pieces_v2`,
    `cell_set`, `slot_piece`, `row_at`, `pieces_v1` are not inlined) built `-DSVF_JMAP=0 -DSVF_JSET_BIG=0` equals the
    same at the Task 15 commit, i.e. before any BIG code (skip without the toolchain; a function inlined on one side
    only is a finding). Pixel/behaviour identity with 2fb312d is Task 18's sweep.
- [ ] **Step 2:** FAIL; **Step 3:** implement; **Step 4:** PASS; `~/.local/bin/heavy make -C c check` exit 0.
- [ ] **Step 5: Commit** - "c: SVF_JSET_BIG - 19 x 28 classes, 128/128/64 sets, 32-bit offsets on 16-bit cores
  (t_380104f8)".

Reviewer checks: every overflow site of Global Constraints is typed under the switch; AVR build with `-DSVF_JSET_BIG=1
-DSVF_JSET_V2=1` compiles `-Werror` and composes `limits_big` in `c/bench/avr-run.c`-style simulation if available (else
the 16-bit `test-open-size16` pattern: `make -C c test-open-size16` with the BIG flag).

### Task 17: BIG defaults, feature rows, sizes, fuzz, bench

**Files:** Modify `c/include/svf.h` (PR-13 for `SVF_JSET_BIG`), `tools/test_c_renderer.py`
(`test_jset_defaults_per_target` + BIG column), `c/cross/check-features.sh` (`minimal+BIG`, `minimal+BIG+V2`; allon),
`c/cross/build-all.sh` (`--switches` column `JSET_BIG`), `c/cross/SIZES.md`, `c/tests/fuzz_corpus.sh` (BIG variants
and kinds, v1 and v2), `c/Makefile` (fuzz targets `-DSVF_JSET_BIG=1`), `c/bench/MEASUREMENTS.md`.

- [ ] **Step 1: Failing test** defaults tuple `(V1, V2, POP4, TRUSTED, JMAP, BIG)`: host `(1, 1, 1, 0, 1, 1)`;
  `-DSVF_SMALL` `(1, 1, 0, 0, 0, 0)`; `-D__AVR__` `(1, 0, 0, 0, 0, 0)`; non-unix host `(1, 1, 1, 0, 0, 0)`;
  `-D__AVR__ -DSVF_JSET_BIG=1` BIG 1.
- [ ] **Step 2:** FAIL; **Step 3:** implement defaults.
- [ ] **Step 4:** sizes: `check-features.sh` `features: OK` (minimal unchanged since Task 5; record `minimal+BIG`:
  estimate AVR +60..120 B, M0+ +24..64 B; outside = report); `build-all.sh` and `--ports` exit 0 with SIZES.md updated
  (movers only dos/web/sdl rows; M0+ P1 stays 7441).
- [ ] **Step 5:** fuzz: `make -C c fuzz-corpus fuzz-smoke`, then 1 h each `fuzz-open`, `fuzz-open-rd` clean.
- [ ] **Step 6:** bench: `sh c/bench/run-pico.sh` at the defaults: `syl_ga 6091`, `syl_bwelk 7321`, `screen32
  188251` equal; the same with `-DSVF_JSET_BIG=1` added to the build (the script's flag hook; read its header) equal
  too. Record both runs in MEASUREMENTS.md.
- [ ] **Step 7: Commit** - "c: SVF_JSET_BIG defaults, feature rows, sizes, fuzz seeds; hot path unchanged
  (t_380104f8)".

Reviewer checks: nm rule for BIG=0 (no symbol is BIG-only; the check is the objdump identity of Task 16); EXPECT_OK 43.

### Task 18: Identity sweep, records, follow-ups

**Files:** Modify `c/cross/SIZES.md`, `c/bench/MEASUREMENTS.md` (only if the sweep re-takes rows), `c/bench/
JSET2-IDENTITY.md` (append a section), `docs/superpowers/specs/2026-10-26-jset-limits-design.md` (an "Implemented"
note at the top naming the plan and the rulings that changed it).

- [ ] **Step 1:** pixel identity: `svfdump` of the base (2fb312d, built into `/tmp/base`) vs the branch default build
  over `svf/`: `python3 c/bench/jset2-identity.py /tmp/base/svfdump <branch svfdump> svf svf /tmp/id.md` -> totals
  `faces=153 jamo=95 different=0`; the same with the v1-only and v2-only builds.
- [ ] **Step 2:** writer identity: `python3 tools/svf2to3.py --tree svf /tmp/w-branch` vs the same at 2fb312d: 153
  files byte-identical (`cmp`); `--jset-version 2` likewise.
- [ ] **Step 3:** `make -C c check`, `build-all.sh`, `--ports` (43 OK), `check-features.sh`, `test-build-all.sh`,
  `test-check-features.sh`, `presets.sh build` (local faces), `python3 -m unittest discover -s tools -p 'test_*.py'`:
  all exit 0.
- [ ] **Step 4:** follow-ups appended to the design's "Implemented" note: (a) ScummVM `jamo_set.h` - until t_5a7bcd78
  swaps in the C renderer, `kJamoMaxInitSets`/`kJamoMaxMedSets` (`:39-40`, 24/16) must become 32/24 to read the v1
  limits (AGOTH24J, AMYUNG24J have 32 initial sets), `kJamoSetMaxSize` (`:79`) 12,321, version 2 and the BIG caps need
  the C reader, a version 3 (JMAP) block is refused (plain face) until then; (b) derived-form faces for the other
  fonts after v3 is final (decision 4); (c) Track C reduction; (d) `SVF_JMAP`/`SVF_JSET_BIG` on the Pico/ESP32 images
  once the user decides from the measured rows.
- [ ] **Step 5: Commit** - "docs: JSET v3/BIG identity sweep, size records, follow-ups (t_380104f8)".

Reviewer checks: every gate run in Step 3 is quoted with its OK line; no number in SIZES.md without its command.

---

## Self-review notes

- Spec coverage: A1-A7 -> Tasks 3, 5, 6, 9 (A1 superseded by version 3 in the JSET magic, cross review (d)1); B1-B7 ->
  Tasks 14-18 (B7's `galmuri_jamo` item dropped: Galmuri abandoned, not on this branch); 5.1-5.6 -> Tasks 2, 5, 7, 17;
  user decision 3 HangulTalk 1.0 -> Task 10; decision 4 -> Tasks 12-13; ScummVM note -> Task 18.
- Proportion: the plan carries signatures, values and test assertions; no function bodies.

## Execution handoff

Execution is subagent-driven (superpowers:subagent-driven-development): one Sonnet implementer per task, sequential
(pre-flight table above); each task reviewed by Claude (Opus) plus the read-only lanes
`<workdir>/scratch/review-lanes/review-agy.sh` (agy, `gemini-3.8-flash-high`) and `review-ocd.sh` (opencode), named
`jset3-tN`, in parallel and isolated; review fixes go back to the same implementer by resume and re-reviews resume the
same reviewer sessions (`--resume`). A finding a later task can fix is folded into that task's dispatch. Stop and report
to the user at: a merge conflict (Task 1), any gated size over its rule (Tasks 5, 7, 17), a type-3 golden mismatch
(Task 9), a hot-path cycle difference (Task 17).
