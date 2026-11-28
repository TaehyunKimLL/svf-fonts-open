**English** | [한국어](sets.ko.md)

# Recipes: Choosing the number of sets (벌 수)

How many sets (벌) a jamo set should have: the set systems `jamoset.py --layout` offers, adaptive sets and class limits, and what each costs in bytes and fidelity, with measured examples.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face). The jamo-set format and design are in [Jamo sets](../jamo-sets.md); the fits themselves are in the recipe documents of each source.

Up: [Recipes index](../recipes.md) · Related: [Jamo sets](../jamo-sets.md), [Jamo splitting](../jamo-split.md), [Outline fonts](outline-fonts.md), [Existing SVF faces, and SVF back to TTF](svf-and-ttf.md).

<a id="choosing-the-number-of-sets-벌-수"></a>

## Choosing the number of sets (벌 수)

<a id="choosing-the-number-of-sets"></a>

A jamo set draws a syllable from one initial, one medial and an optional final piece; the *sets* (벌) are the variants
of each jamo, and the set system picks one per syllable by the vowel, the final and the initial's class. More sets
follow the font more closely and cost bytes (every set holds a piece for every jamo it is used for) and table size.

**The set systems** (`jamoset.py --layout`; the JSET block allows up to 32 initial, 24 medial and 16 final sets and
12 x 12 lead / tail classes, `--jset-big` up to 128 / 128 / 64 and 19 x 28):

| Layout | Sets (initial / medial / final) | Where it comes from | From a fit (`--from-ttf`, `--from-svf`) |
|---|---|---|---|
| `621` | 6 / 2 / 1 | Apple II era 6x2x1 fonts | yes (NEODG16G of `svf/` is one) |
| `844`, `844-ihnm`, `844-hbios24` | 8 / 4 / 4 | the DOS standard (`HANGUL.FNT`); IHNM swaps the medial sets of ㄱ ㅋ; HBIOS is its 24x30 file | yes |
| `1044-san` | 10 / 4 / 4 | san 1.0 | yes |
| `hanterm-johab` | 10 / 4 / 4 (3 for some files) | hanterm's johab BDFs | yes |
| `dkb-printer-7x2x2`, `dkb-printer-12x4x4` | 7 / 2 / 2, 12 / 4 / 4 | Dokkaebi printer fonts | yes |
| `kyra-lok` | 10 / 4 / 4 | Kyrandia's MK15.BIT | yes |
| `hwp1` | face-dependent: 10/4/4, 7/2/2 or 6/2/2 (SFT); 7/2/3, 7/2/2 or 5/2/2 (PFT) | HWP 1.x Hangul files | source files only |
| `844-hwp3` | 8 / 4 / 4 | appended jamo set in HWP 3.0 16 px Hangul FNT | yes |
| `spec` | derived from the compose spec (SPC-1500: 6 / 2 / 2) | `rawcarve.py compose` spec | source files only |
| `mac-fbit-45sets` | derived from the font (Munjo24: 20 / 15 / 4, 8 x 4 classes) | HangulTalk 1.0 `fbit` | source files only |
| `adaptive[:NI,NM,NF]` | from 8 / 4 / 4 up to NI / NM / NF (default 32 / 24 / 12; NI 8-32, NM 4-24, NF 4-16), 12 x 12 classes | `jamoadapt.py`: splits a set where the syllables that share a piece disagree | yes |

**The options that change the counts.** `--layout adaptive:NI,NM,NF` caps the sets (it stops earlier when a split no
longer gains: at least 0.05 % of the starting cost, at least 4 syllables a side, fixed in `jamoadapt.py`); the class limits
are 12 × 12 for `jamoset.py --layout adaptive` (even with `--jset-big`, which only lets a source's own larger tables be written).
`jamovec.py master --adaptive NI,NM,NF` and `--class-limit N` do the same for a vector master (counts above the standard limits require `jamovec.py render --jset-big` and a renderer built with `SVF_JSET_BIG`;
counts beyond the BIG limits can only be simulated). After a fit, `jamomerge.py merge --points BYTES ...` merges variants, sets and classes
down to byte budgets ([HangulTalk 7.1.x type-3 `fbit` fonts](classic-mac.md#classic-mac-hangultalk-71) has a run), and
`jamoexc.py` stores a few frequent syllables whole (LIST exceptions) instead of adding sets.

**Measured** (2026-11-22): every layout fitted with `jamoset.py --layout L --from-svf FACE --mask-font none --check` to
two 16 px precomposed faces: NanumGothic Bold (`mkfont.py ... --size 16 --bpp 1`, an outline font's raster) and OS/2's
`$korZN16.FNT` ([OS/2 Korean fonts](os2.md#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set), a hand-drawn bitmap
face). Bytes of the whole face (ASCII included), IoU over the 2,350 syllables (exact of 2,350), and the ink of the
sample line (the precomposed faces: 677 and 469):

| Layout | Sets used | NanumGothic Bold: bytes | IoU (exact) | Ink | OS/2 ZN16: bytes | IoU (exact) | Ink |
|---|---|---:|---|---:|---:|---|---:|
| `621` | 6 / 2 / 1 | 12,788 | 0.743 (25) | 673 | 11,544 | 0.889 (206) | 471 |
| `844` | 8 / 4 / 4 | 20,648 | 0.795 (126) | 681 | 17,264 | 0.984 (1,753) | 470 |
| `1044-san` | 10 / 4 / 4 | 22,504 | 0.799 (118) | 681 | 18,788 | 0.991 (1,823) | 470 |
| `hanterm-johab` | 10 / 4 / 4 | 21,992 | 0.798 (110) | 676 | 18,608 | 0.981 (1,501) | 468 |
| `adaptive:8,4,4` | 8 / 4 / 4 | 29,544 | 0.796 (135) | 680 | 25,972 | 0.992 (2,171) | 469 |
| `adaptive:12,8,6` | 12 / 8 / 6 | 39,176 | 0.857 (205) | 678 | 33,924 | 0.999 (2,273) | 469 |
| `adaptive:16,12,8` | 16 / 12 / 8 (ZN16: 14 / 12 / 8) | 48,156 | 0.875 (291) | 672 | 41,008 | 0.999 (2,299) | 469 |
| `adaptive:24,16,12` | 24 / 16 / 12 (ZN16: 14 / 12 / 9) | 65,412 | 0.905 (414) | 677 | 42,140 | 0.999 (2,299) | 469 |
| `adaptive` (32,24,12) | 32 / 24 / 12 (ZN16: 14 / 12 / 9) | 77,560 | 0.918 (576) | 669 | 42,140 | 0.999 (2,299) | 469 |

Each fit took 0.3-0.5 s (fixed layouts) or 2-7 s (adaptive). The precomposed faces are 125,520 and 123,328 bytes.

**Reading it.** The fixed layouts cost what their piece count costs (621: 279 / 280 glyphs on the two faces, 844: 440 / 441, the 10x4x4 layouts: 464-479),
and they gain little over each other. `adaptive:8,4,4` has the 844 counts but 12 x 12 classes: its tables cost 8.8 KB
more (a 9,921-byte JSET block against 1,101; 2,844 as JSET v2: `--jset-version 2` or `auto`, every adaptive
face above shrinks by 6-7 KB that way) for a better choice of which syllables share a piece (OS/2: 2,171 exact against
1,753). The hand-drawn bitmap face is already close to an OR of pieces and stops splitting at 14 / 12 / 9 with IoU
0.999; the outline raster keeps gaining up to the cap (0.918 at 32 / 24 / 12) and is never exact, because a scaled
outline draws every syllable a little differently.

**Recommendation.** Fit `844` first and read the IoU. Above about 0.98 (a bitmap face designed on pieces, a DOS font,
a ROM) keep `844`: more sets buy almost nothing. Between that and about 0.9, try `adaptive:12,8,6`, which gains most
of what more sets give at about twice the 844 size; a raster of an outline font, at 0.8 with 844, needs the full
`adaptive` budget to reach 0.9 and then costs over 60 % of the precomposed face: there the precomposed face, or a few
LIST exceptions (`jamoexc.py`) on an 844 set, is usually the better use of the bytes. For a target with a hard budget,
fit generously and let `jamomerge.py merge --points` cut down to it. Look at the result in every case
(`svfline.py line`, the `web/` picker): IoU does not show which syllables went wrong.

<a id="size-and-accuracy"></a>

### Size and accuracy

A jamo set trades bytes for fidelity. Plot the composed IoU against the face's bytes for a few caps: the curve rises
fast, then flattens. The **knee** is where doubling the bytes gains less than about 0.02 IoU; beyond it, extra sets buy
little.

Measured in 2026-11 with `jamoset.py --from-svf FACE --layout L`:
- `844` with `--mask-font none`; `adaptive` with its defaults (it confines the pieces with its own donor masks, not the mask
  font).
- The source and the jamo faces hold only the 2,350 KS syllables (no ASCII); bytes are the whole file, IoU is over those
  syllables. Each cell is bytes: IoU.
- Gulim and Seoul are proprietary fonts: their rows cannot be re-run from this repository.

| Face | `844` | `adaptive:8,4,4` | `adaptive:12,6,6` | `adaptive:16,8,8` | `adaptive:24,12,12` | `adaptive` (default) | Precomposed |
|---|---|---|---|---|---|---|---|
| Galmuri11, 16 px | 13,436: 0.913 | 22,300: 0.913 | 28,132: 0.958 | 34,088: 0.972 | 46,492: 0.981 | 58,844: 0.985 | 103,452 |
| Baekmuk Gulim 16 | 15,476: 0.782 | 24,156: 0.788 | 30,884: 0.844 | 37,912: 0.876 | 53,396: 0.908 | 66,516: 0.931 | 121,836 |
| Windows 95 Gulim, 16 ppem strike | 14,872: 0.825 | 23,596: 0.861 | 30,452: 0.913 | 37,408: 0.940 | 51,148: 0.961 | 64,724: 0.973 | 121,836 |
| Mac Seoul, 10 ppem strike | 11,328: 0.864 | 19,956: 0.893 | 25,348: 0.913 | 30,860: 0.932 | 40,988: 0.942 | 49,824: 0.954 | 83,660 |

**Which point.**

| Use | Point | With today's tools |
|---|---|---|
| MCU | the smallest face whose IoU stays at about 0.90 or more, checked by eye | the first cap that reaches 0.90 for that face: above, `844` for Galmuri11, `adaptive:12,6,6` for Gulim and Seoul, `adaptive:24,12,12` for Baekmuk; then `jamomerge.py merge --points` to the budget; or `jamohybrid.py --min-iou 0.9` |
| Desktop / web | near the knee | `adaptive:16,8,8` up to the default; or `jamohybrid.py` (standard limits, `--big` where the engine reads BIG) |

A learned split (`tools/jamohybrid.py`) reaches the same IoU in fewer bytes: 0.89-0.96 at 18-36 KB with the standard JSET limits
(Baekmuk is the low end, 0.894 at 35.7 KB) ([Jamo splitting, 7.6](../jamo-split.md#76-size-and-accuracy)). Its `--max-bytes` / `--min-iou` knobs pick a point
on that curve directly: `tools/jamohybrid.py --from-svf FACE.SVF -o OUT.SVF --min-iou 0.9` (or `--max-bytes N`; `--big`
for BIG limits).

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
