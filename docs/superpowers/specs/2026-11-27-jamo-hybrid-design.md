# Learned jamo split in this repository (`tools/jamohybrid.py`) - design

> **Phase B implemented (2026-11-28)** on branch `jamo-hybrid`: `tools/jamohybrid.py`, `tools/jamonet.py`,
> `tools/train_jamohybrid.py`, `tools/test_jamohybrid.py`, `tools/models/jamohybrid-v1.npz` with
> `tools/models/jamohybrid-v1.md`. Owner decisions: train on everything available (section 1); the weights are MIT like
> the code, listed separately in NOTICE with their training provenance. Measured against this design:
>
> | Item | Design | Result |
> |---|---|---|
> | model | smallest within 0.003 of base 32 | base 16 (487,347 parameters as shipped), never more than 0.002 below base 32 on a held-out face |
> | weights | about 1 MB, fp16 | 910,733 bytes, fp16 |
> | numpy vs torch | max probability difference < 1e-3 | 3.7e-6 with float32 weights (TF32 off in torch); 0.0040 with the shipped fp16 weights, 15 of 1,918,350 slot pixels flipping at 0.5; fp32 weights would double the file |
> | speed | 2,350 syllables <= 5 s, 11,172 <= 20 s | 3.2 s and 14.8 s for the model (4 CPU threads); a standard face builds in about 6 s |
> | training data | section 1 table | as listed; composite TrueType fonts (1.2) left for a later version |
> | maker | follow-up | not done |

## Goal

A tool that builds a jamo-set face from a precomposed one, as `jamoset.py --from-svf` / `--from-ttf` do. The difference
is that it gets the **split** right as well as the composition. A per-pixel model proposes each syllable's initial,
medial and final. Sets are chosen top-down from the Korean layout rules, and pieces are voted bottom-up under identity
gates. [Jamo splitting](../../jamo-split.md) (its chapter on the 2026-11 learned split, under review) has the method and the measurements; this note covers what moves
into the repository and how.

Measured in research, for reference:

| | `jamoset adaptive` | Learned split (hybrid) |
|---|---|---|
| pixels in the right slot (Apple GT faces) | 0.66-0.73 | 0.98-0.995 |
| pixels in the right slot (Windows 95 Gulim, unseen designer) | 0.68-0.70 | 0.955-0.983 |
| composed IoU at a similar size (9-16 px strikes) | 0.86-0.90 | 0.90-0.96 |

## 1. Training data

**Rule (owner, 2026-11-27):** ship the best model, trained on everything available. Record the provenance honestly. Put
no font bitmaps in the repository.

| Source | Syllables with exact pieces | Kind |
|---|---|---|
| HangulTalk 7.1.2 jamo planes = System 7.5.3 strikes: Seoul 12, AppleMyungjo 12 / 24, AppleGothic 24 | 4 x 2,350 | real precomposed = composition (proprietary, Apple) |
| Windows 95 Gulim 12 / 16 ppem strikes, `EBDT` component composites | 2 x 1,928 (the 422 whole-bitmap syllables masked out) | real precomposed = composition (proprietary, Microsoft) |
| HangulTalk 1.0 `fbit` fonts: Gotic12, Munjo12 / 16 / 24 | 4 x 2,350 | synthetic composition (proprietary, Apple) |
| svf/ 1 bpp jamo-set faces: 36 faces, 16-54 px (NEODG16*, NEODG32*, SANS8J, MARUS20 / 24, NSQR*, GOTH*, SGDAY*, NDGPR*) | 36 x 2,350, or all 11,172 where useful | synthetic composition (OFL-1.1; SANS8J OFL / MIT) |

The training samples are composed in memory by the training script from the source files. Nothing derived from them is
written into the repository.

- **Composite TrueType fonts** are a further source with many designers and every size (1.2).
- **Augmentation:** a shift of ±1 source pixel only, as in research.

### 1.1 Evaluation

| Set | How | Committed? |
|---|---|---|
| leave-one-font-out over the 4 Apple GT faces | train without the face, test on it (as research: 0.988-0.995) | numbers only |
| held-out designer: Gulim 12 / 16 | one fold trained without Gulim (research: 0.986-0.989) | numbers only |
| held-out open families | folds without SANS8J, without NDGPR*, without SGDAY* | numbers only |
| held-out composite TrueType families | per family or foundry (1.2) | numbers only |
| the shipped model | trained on all of the above; its numbers are the folds' | weights only |

Metrics: pixels in the right slot (label accuracy), syllables whose pieces are all exact, and the built face's composed
IoU and bytes against `adaptive`. The private evaluation sets and their bitmaps stay outside the repository.

### 1.2 Composite TrueType fonts (assessment)

A scan of the TrueType fonts available for training found **69 families** that draw Hangul syllables as `glyf`
composites. Each component glyph is one of the designer's jamo variants.

| Coverage | Families (licence) |
|---|---|
| 11,172 of 11,172 (the 399 two-component syllables are the ones without a final) | Un fonts: UnBatang, UnDotum, UnGraphic, UnGungseo, UnPilgi, UnShinmun, UnJamo* (GPL); Neo Dunggeunmo and Pro, ThinMulmaru, Single Day, Sahmyook, WenQuanYi Zen Hei (open licences); Windows New Gulim, Pyunji, Magic, Headline (proprietary) |
| 10,750 | Gulim, Dotum, Batang, Gungsuh and their Che variants (proprietary) |
| 8,822 | the Nanum families (OFL) |
| partial | D2Coding, Gothic A1, KoPub Batang, NEXON Lv1 / Lv2, Kakao Big / Small Sans, Mabinogi Classic, Iropke Batang, HSSaemaeul, Dovemayo, Tuktakpotato, goorm Sans Code, NanumSquareRound, NanumBarunGothic, and others |

**What each composite gives.**
- **Labels:** each component rasterised at the target size is one exact plane, at any size from 9 to 24 px.
- **Grouping ground truth:** the component glyph id is the designer's variant. A family's (slot, jamo, context) → glyph id
  table is its set rule. It can be scored with the ARI as Apple's was, and it is training data for a learned rule
  (`--rule derived`).

**Slots.** Component order is not always initial, medial, final.
- Slots are assigned by the component glyph itself: a glyph id must be used by one slot and one jamo only, as Gulim's
  `EBDT` components are (0 clashes).
- Where the file order is not consistent, `jamovec.py composite_parts`' position rule decides.
- Families with any clash are left out.

**Rasterisation.** The target is what a precomposed face would hold: the whole composite rendered by FreeType mono, as
`mkfont.py` renders.
- Labels are the components rendered alone, at their offsets, by the same renderer.
- A pixel of the whole raster that two component rasters cover is in both planes (overlap, as in the Apple ground truth).
- A pixel no component raster covers goes to the component with the largest exact-area coverage (`jamoaa.py`'s
  rasteriser).
- A component pixel outside the whole raster is dropped.
- Per family and size, the share of pixels decided by these rules is recorded. A (family, size) where it exceeds 2 % is
  not used.

**Hinting.**
- A composite and its components are hinted separately, so the union of the component rasters can differ from the
  whole raster at 9-12 px.
- Both hinted and unhinted renders are measured, and training uses the one that `mkfont.py` uses for faces.
- The model must still see real hand-drawn strikes (the Apple and Gulim ground truth): outline renders do not show the
  per-syllable tuning of a bitmap strike.

**Hold-out.** Folds are by family: all weights, sizes and Che / proportional variants of a family stay together.
- Families of one foundry are held out together: Gulim, Dotum, Batang and Gungsuh as one fold, and the Un fonts as one
  fold.
- Reported per fold: label accuracy against the component planes, ARI against the component grouping, and the built
  face's IoU and bytes against `adaptive`.

**Volume.** Up to 69 families x 11,172 syllables x 8 sizes, about 6 M samples. Each epoch samples (family, size) pairs
uniformly, so no family dominates. The data is rendered on the fly by the training script. Nothing rendered is stored in
the repository; the font list with hashes goes into the provenance file (4).

## 2. Inference without torch

- **Model.** The research U-Net: a 32 x 32 canvas, 3 sigmoid planes, and L / V / T embeddings.
  - The research model had base 32 channels and 1.94 M parameters. Phase B also trains base 16 (about 0.5 M) and ships
    the smallest model within 0.003 label accuracy of base 32 on the folds.
- **Weights.** One `tools/models/jamohybrid-v1.npz`.
  - BatchNorm is folded into the convolutions at export. Arrays are stored as fp16 and computed in float32.
  - Size: about 1 MB for base 16, about 4 MB for base 32. int8 only if fp16 is over 4 MB.
- **Forward pass in numpy.**
  - 3x3 convolution by `numpy.lib.stride_tricks.sliding_window_view` plus `tensordot` (im2col).
  - 2x2 max-pool and the 2x2 stride-2 transposed convolution by reshapes.
  - Batches of 512 syllables.
  - Target: a face of 2,350 syllables in at most 5 s, and 11,172 in at most 20 s, on one desktop CPU. Research shapes
    estimate 60 M multiply-adds per syllable at base 32, a quarter of that at base 16.
- **Dependencies.**
  - `jamohybrid.py` needs numpy only, an optional dependency like freetype / uharfbuzz for `--from-ttf`.
  - `jamoset.py` stays stdlib-only.
  - The research code's scipy uses (linkage on at most 28 items; 4-connected hole labelling) are rewritten in numpy.
- **Training** is a separate script, `tools/train_jamohybrid.py`. It needs torch and is never imported by the tool or
  the tests.

## 3. CLI: a new `tools/jamohybrid.py`

I chose a separate tool, not `jamoset.py --layout hybrid`:
- `jamoset.py` is stdlib-only and 3,500 lines. The hybrid needs numpy and a model file, and is built from proposals, not
  from a layout's tables.
- It reuses jamoset's writer and checks (`build_from_source`, `check`, `ttf_targets`, `svf_targets`) and jamofit's refit,
  as `jamovec.py` and `jamomerge.py` already do.

```
python3 tools/jamohybrid.py (--from-svf FACE.SVF | --from-ttf FONT --size N [--cell WxH] [--baseline R])
    -o OUT.SVF [--rule structural|derived] [--max-bytes N | --min-iou X | --limits NI,NM,NF]
    [--big] [--model PATH] [--report OUT.json] [--check] [--jset-version 1|2|auto]
```

| Option | Meaning |
|---|---|
| default | the standard JSET face: 32 / 24 / 16 sets, 12 x 12 classes |
| `--big` | opt-in BIG limits: 64 / 48 / 32 sets, 19 x 28 classes; engines built with `SVF_JSET_BIG` (owner's rule) |
| `--max-bytes N` | the most accurate point of the limit ladder within N bytes |
| `--min-iou X` | the smallest point that reaches composed IoU X |
| `--rule` | `derived` (default): vowel groups, initial classes and final kinds learned from the face's own proposals; `structural`: the fixed groups of the layout rules (in research called "apple") |
| `--report` | JSON: the chosen point and the whole ladder, sets, classes, gates, disagreements |
| `--check` | compose all 11,172 syllables (jamoset `check`); the build also runs the `svf2to3` check |

The ladder points are as in research:
- standard: 16 / 21 / 8, 20 / 22 / 10, 24 / 22 / 12, 28 / 23 / 14, 32 / 24 / 16;
- BIG: 40 / 30 / 20 up to 96 / 72 / 48.

Identity gates (mass, extent, holes, serif-tolerant ticks / stubs, ㅅ / ㅈ slant) are calibrated on the face's own
proposals.

## 4. Weights: provenance and licence

- **`tools/models/jamohybrid-v1.md`** (next to the weights) records:
  - every training face, with its source description, format, size, sha256 of the source file, and licence;
  - the training script and its git commit, the seed, the epochs, and the fold results.
- **The plain statement**, in that file and in NOTICE: "The weights were trained on bitmaps of proprietary fonts (Apple
  HangulTalk 7.1.2 / System 7.5.3 and HangulTalk 1.0 fonts; Microsoft Windows 95 Gulim) and on the open faces of `svf/`.
  No font bitmap is included. Licence questions about using the weights are the user's responsibility, as with the
  fonts in this project."
- **Licence.** I propose no new licence grant beyond the repository's terms for code. The weights file is listed in
  NOTICE as a separate item with the statement above, the way `docs/images/recipes/` is set apart today. Your decision
  is needed here: MIT like the code, or "no licence granted beyond what the training data allows".
- **NOTICE.md / NOTICE.ko.md** get a section "Model weights (`tools/models/`)" with the statement and a pointer to
  `jamohybrid-v1.md`.

## 5. Tests (synthetic only, seconds)

`tools/test_jamohybrid.py` uses no font bitmaps beyond the repository's open faces:

1. **numpy convolution:** im2col conv, pool and transposed conv match naive loops on random small tensors.
2. **forward pass:** a tiny random model (generated in the test, base 4) gives the right shapes, is deterministic, and
   loads from the fp16 `.npz` format.
3. **end to end:** the shipped model on 300 KS syllables composed from `svf/iolo/SANS8J.SVF`. The face builds, `check`
   composes all 11,172, and the label accuracy against SANS8J's own planes is ≥ 0.9 (a smoke threshold: SANS8J is in
   training).
4. **knobs:** ladder selection for `--max-bytes` / `--min-iou` on stubbed points; `--big` off by default.
5. **provenance:** the weights' sha256 is listed in `jamohybrid-v1.md`, and NOTICE names the file.

Total under 30 s. Tests needing torch do not exist.

## 6. Maker integration

A follow-up, not this card. After the tool and its report format settle, the desktop route list gets "learned split
(jamohybrid)" next to "bdfface + from-svf fit". It needs a numpy check in `/api/caps`, the model path, and the
size / accuracy choice in the UI.

## Phase B outline

1. Port the research code (`hybrid2`, gates, refit) to `tools/jamohybrid.py` with numpy-only inference.
2. Add `tools/train_jamohybrid.py` (torch); train the folds on a GPU machine, then the shipped model.
3. Export with BatchNorm folded and fp16; check that numpy and torch outputs agree (max abs diff < 1e-3 on the folds).
4. Run the evaluation of 1.1 and compare against `adaptive`.
5. Tests; then the documentation: [Jamo splitting](../../jamo-split.md) chapter 7 and [Choosing the number of
   sets](../../recipes/sets.md) move from "research only" to "available", plus a `tools.md` entry.
