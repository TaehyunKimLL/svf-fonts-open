---
name: svf-fonts-hangul-basics
description: Use when you need the Hangul and SVF background for a font task: syllable structure, encodings, precomposed faces against jamo sets, sets and classes, the JSET/JMAP limits and the usual surprises.
---

# Hangul and SVF basics

A concept primer for the tasks in this repository. Each point links to the document that explains it; read that before
going deeper. The numbers are the format's, not one face's.

## Syllable structure

| Fact | Value |
|---|---|
| Modern jamo | 19 initials (초성) x 21 medials (중성) x 28 finals (종성, "no final" included) |
| Syllables | 19 x 21 x 28 = 11,172 |
| Unicode block | U+AC00..U+D7A3, grouped by initial, then medial, then final |
| Formula | U = 0xAC00 + (L x 21 + V) x 28 + T, with L 0..18, V 0..20, T 0..27 (0 = no final) |
| Inverse | s = U - 0xAC00; L = s / 588; V = (s / 28) % 21; T = s % 28 |
| KS X 1001 | 2,350 syllables only, 94 a row in rows 0xB0-0xC8 |
| Johab code | 16 bits: bit 15 = 1, initial 5 bits, medial 5, final 5; fill values initial 1, medial 2, final 1 |

Sources: [Two ways: 2,350 and 11,172 syllables](../../docs/jamo-sets.md#11-two-ways-2350-and-11172-syllables),
[The Unicode formula](../../docs/jamo-sets.md#13-the-unicode-formula-and-its-relation-to-johab),
[The bit layout of the johab code](../../docs/jamo-sets.md#12-the-bit-layout-of-the-16-bit-johab-code).

Example: 한 = ㅎ (18), ㅏ (0), ㄴ (4) → 0xAC00 + (18 x 21 + 0) x 28 + 4 = **U+D55C**; johab 0xD065; EUC-KR C7D1.

Compatibility jamo are standalone characters, not composed syllables: 51 modern ones, U+3131..U+3163 (KS X 1001 row
0xA4), and 94 in U+3131..U+318E. A jamo-set face draws one from a single piece when its compat entry names one, else
from a whole glyph when the face stores one ([compat entries](../../spec/SVF.md#term-compat)).

## Encodings and what each covers

| Form | Syllables | Shape |
|---|---:|---|
| KS X 1001 precomposed / EUC-KR | 2,350 | two bytes 0xA1-0xFE, dictionary order |
| CP949 / UHC (Windows Korean) | 11,172 | two bytes: the KS 2,350 at their own codes, 8,822 extensions interleaved |
| Johab (KS X 1001 annex 3, CP1361) | 11,172 | 16-bit initial/medial/final fields |
| Commercial johab (1980s) | 11,172 | the same field form, vendor variants (Sambo/KSSM, others); standardized in 1992, dropped by Windows 95 |
| Unicode | 11,172 | U+AC00..U+D7A3; UTF-8/16/32 are byte forms of the code points |

Sources: [EUC-KR and CP949](../../docs/jamo-sets.md#111-euc-kr-and-cp949),
[Unicode and encoding forms](../../docs/jamo-sets.md#112-unicode-and-encoding-forms),
[Commercial johab](../../docs/jamo-sets.md#141-commercial-johab-and-the-ks-precomposed-code-dispute).

A document in KS X 1001 can write only 2,350 syllables; the others need CP949, johab or Unicode. A source that draws
the 2,350 has no data for the other 8,822, which matters for a fit (see the pitfalls).

## Precomposed face or jamo set

| | Precomposed face | Jamo set |
|---|---|---|
| Draws | one stored glyph per code point | pieces at U+F0000+n, composed by per-pixel maximum (the OR at 1 bpp) |
| Exactness | exact for every syllable it holds | exact only where the font is an OR of pieces; otherwise an approximation, measured by IoU |
| Size | 16x16 1 bpp: 32 B a glyph; 11,172 = 357,504 B, the KS 2,350 = 75,200 B | 8x4x4: 360 pieces = 11,520 B at 16 px, and all 11,172 compose |

Measured in this repository: `NEODG16.SVF` is 133,720 B precomposed; `SANS8J.SVF` is 15,740 B (8x4x4, draws all
11,172). Sources: [Why pieces: memory](../../docs/jamo-sets.md#21-why-pieces-memory),
[the jamo block](../../spec/SVF.md#jamo-block).

## Sets and classes

- A **set** (벌) is one bundle of variants for a jamo, drawn for one position. **8x4x4** means 8 initial, 4 medial and 4
  final sets.
- The set of each jamo is chosen from the others: the **initial's** set from the medial's shape (vertical, horizontal or
  compound vowel) and whether a final is present; the **medial's** set from whether the initial is ㄱ/ㅋ and whether a
  final is present; the **final's** set from the medial's shape
  ([Sets: a jamo's shape depends on where it sits](../../docs/jamo-sets.md#22-sets-a-jamos-shape-depends-on-where-it-sits)).
- 8x4x4 in practice: initials 0-4 without a final by vowel kind, 5-7 with a final; medials 0-1 without a final by ㄱ/ㅋ,
  2-3 with a final; finals 0-3 by vowel
  ([The selection rule of 8x4x4](../../docs/jamo-sets.md#23-the-selection-rule-of-8x4x4)).
- A set holds 20 (initial), 22 (medial) or 28 (final) slots; slot 0 of each set is blank. Other systems (6x2x1, 10x4x4,
  the printer sets) select by the same idea with different tables
  ([Set systems compared](../../docs/jamo-sets.md#24-set-systems-compared)).
- More sets follow the font more closely and cost bytes and table size; how many to use:
  [Choosing the number of sets](../../docs/recipes/sets.md#choosing-the-number-of-sets).

## SVF essentials

| Concept | What it is |
|---|---|
| SVFN face | header, code point table, optional metrics, glyph records; jamo block flag bit 1 ([structure](../../spec/SVF.md#bitmap-fonts)) |
| bpp | 1 (stencil), 2 (four levels) or 8 (coverage); no 4 bpp. Composition takes the maximum, not a sum ([bpp](../../spec/SVF.md#term-bpp), [coverage](../../spec/SVF.md#term-coverage)) |
| JSET v1 | class and set tables: `leadClass[19]`, `tailClass[28]`, three set tables indexed `(leadClass x 21 + vowel) x TC + tailClass`; the standard writer ([jamo-set fonts](../../spec/SVF.md#jamo-set-fonts-flags-bit-1)) |
| JSET v2 | the same tables bit-packed; a compact choice for constrained targets ([version 2](../../spec/SVF.md#jset-v2)) |
| JMAP (v3) | a mapping per syllable (dense, sparse or LIST) with an optional v1/v2 fallback; for choices class rules cannot express ([JMAP](../../spec/SVF.md#jmap)) |
| Standard limits | 12 x 12 lead/tail classes and 32 / 24 / 16 initial/medial/final sets ([limits](../../spec/SVF.md#jamo-set-fonts-flags-bit-1)) |
| BIG | `SVF_JSET_BIG` / `--jset-big`: 19 x 28 classes and 128 / 128 / 64 sets; the reader must be built for it ([BIG](../../docs/jamo-sets.md#52-big-only-the-limits)) |

A syllable is read as a cell of (lead class, vowel, tail class), so the set limits hold per lead class for the initial,
per vowel for the medial and per tail class for the final
([Grouping into sets](../../docs/jamo-split.md#74-grouping-into-sets)). A JMAP region stays within 65,534 bytes.

## Pitfalls

| Symptom | Why | Do instead |
|---|---|---|
| The 8,822 syllables outside KS look wrong | a KS-only source gives no data for them; the fit extrapolates every one | build from a source that draws all 11,172 (a CP949/Unicode TTF, a full strike); read the per-face numbers ([Size and accuracy](../../docs/recipes/sets.md#size-and-accuracy)) |
| A compatibility jamo draws blank | its compat entry points at an inkless piece (the ㅡ bar can live in the initial pieces) and no whole glyph is stored | bake the compat jamo as whole glyphs, or add a `"whole"` LIST entry ([the blank medial ㅡ](../../docs/jamo-split.md#43-small-pixel-fonts-the-blank-medial-ㅡ)) |
| One context is copied from another | the source never draws that (lead class, vowel, tail class); the fit borrows another set or stays blank (`unseen_pieces`) | give the fit every syllable it can, and look at `unseen_pieces` in the report ([What we do poorly](../../docs/jamo-split.md#5-what-we-do-poorly)) |
| `--check` passes but the face is poor | it proves the tables compose all 11,172 syllables, not that each piece is its jamo | read the IoU, draw a line, and check the compatibility jamo ([Checking a face](../../docs/recipes.md#checking-a-face)) |

## Where to go next

- A hands-on walkthrough with three OFL fonts: [`docs/jamo-split-guide.md`](../../docs/jamo-split-guide.md).
- The fit case by case and what fits poorly: [`docs/jamo-split.md`](../../docs/jamo-split.md).
- The character set and the set systems in full: [`docs/jamo-sets.md`](../../docs/jamo-sets.md).
