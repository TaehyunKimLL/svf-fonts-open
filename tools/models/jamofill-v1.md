# jamofill-v1 weights

`jamofill-v1.npz` is the cross-font group ranker of `tools/jamohybrid.py --fill` (format `jamofill-1`, the `FillModel`
class in `jamohybrid.py`). Licence: MIT, like the code. [NOTICE](../../NOTICE.md#model-weights-toolsmodels) says what it
was trained on.

| Item | Value |
|---|---|
| file | `jamofill-v1.npz`, 32,928 bytes |
| sha256 | `8baf7e7639f38c862e8a8ac908c38b2a2d5b06b436938701cffe4c11c1ff82f5` |
| model | 60-64-64-1 MLP, ReLU, float32, 8,309 parameters |
| inputs | 60 features (below), NaNs replaced by the training median, then standardised with the training mean / sd |
| inference | numpy only, about 1.5 ms for the candidate rows of one context |
| validation | loaded with `allow_pickle=False`; exact array names, shapes and float dtype; at most 1 MiB and 65,536 parameters |
| training rows | 603,156 rows from 16 faces (12 and 16 px) |
| seed | 0 (`random_state=0`) |
| training command | `pipeline.py --sizes 12,16` then `mlp.py --save mlp` (the research scripts, not part of this repository): scikit-learn `MLPRegressor(hidden_layer_sizes=(64, 64), activation="relu", alpha=1e-4, max_iter=60, batch_size=4096, learning_rate_init=1e-3, early_stopping=True, n_iter_no_change=5, random_state=0)` |

The label of a training row is the mean IoU of the candidate group's piece with the true piece the font draws in that
context, over the syllables of the context. The model is fitted on the raw IoU and the highest score wins.

## Training sources

Only the fonts below are in the training lineages; no proprietary font is. The sha256 is that of the font file the
research pipeline rendered. The research drop list (Neo Dunggeunmo Pro, Thin Mulmaru Mono, WenQuanYi Mono and
WenQuanYi Sharp) removes those faces from training; they are not rows below.

| font | lineage | licence | sha256 | faces | rows (12 px / 16 px) |
|---|---|---|---|---|---|
| Single Day | singleday | OFL-1.1 | `716ff67a4b0675b35c26d60a4bb83173f7d153ab754474ed36c3369593ca1ca8` | 12, 16 | 29,376 / 32,209 |
| Neo Dunggeunmo | neodgm | OFL-1.1 | `77305267996073aae07bad9313dad2e306a4128e55bfafbed4c41558fee57b4d` | 12, 16 | 18,388 / 19,208 |
| DovemayoGothic | dovemayo | OFL-1.1 | `48258ec1ef82bc6ae19c206923bb1f2a6f173f34fa0242c3ac75cfdd5c1d604d` | 12, 16 | 32,273 / 40,618 |
| Sahmyook Light | sahmyook | OFL-1.1 | `9caabd06e30d698643d3068ae7d88631569b7ea06be45aaf2904832c16b31758` | 12, 16 | 50,303 / 67,374 |
| Sahmyook Regular | sahmyook | OFL-1.1 | `9f5b6a58d2c7e83e02abc7e03a4a5eaecea836b8f8104fc2b1cf8cd1e6b94250` | 12, 16 | 58,464 / 70,176 |
| Thin Mulmaru | thinmulmaru | OFL-1.1 | `267478c4398e4cae8296c3893132d8f0cd7ce9383c917a1004597dfd9445beaf` | 12, 16 | 11,763 / 12,211 |
| WenQuanYi Zen Hei | wqy | GPL-2.0 with font exception | `79c18ebe7b811951e8311bad7103ebeae8c337ed9988ea69e8a78a66cfe029b9` | 12, 16 | 61,240 / 73,170 |
| Exqt | exqt | OFL-1.1 | `da1ca59c4c5b51e6ecb00d464a0bd1c94a243555f4038ef602165103039ee95d` | 12, 16 | 13,018 / 13,365 |

Total: 603,156 rows. No bitmap of any training font is in this repository.

## The 60 features

All are scale-free (boxes divided by the cell side). One row per (unseen context, candidate group):

| # | Feature |
|---|---|
| 1-3 | slot one-hot (initial, medial, final) |
| 4-24 | vowel one-hot (21) |
| 25-28 | predicted ink box: top, height, width, left |
| 29-32 | lead-class mean ink box: height, width, area, right |
| 33-36 | tail-class mean ink box: the same four |
| 37 | share of the source's syllables without a final |
| 38 | candidate member count / 20 |
| 39-41 | context distance to the group: minimum, relative, mean |
| 42-43 | the group's box against the prediction (L1), and its relative rank |
| 44 | the group's sibling-vote share, relative to the best candidate |
| 45 | same vowel as a member (initial / final problems) or the same tail class |
| 46-49 | the group's box minus the predicted box (top, left, bottom, right) |
| 50-53 | the group's box: left, width, height, area |
| 54-57 | the group's box minus the mean candidate box (four coordinates) |
| 58-60 | share of the 1, 3 and 8 nearest seen contexts that are in the group |

The tail-class box's second term is `b[2] - b[1]` (the research code's definition, not `b[3] - b[1]`); the model was
trained with it and the port keeps it. The layout feature's additive box models are fitted to the pieces the source
has; the research code fitted them to the full label set of a composite face, which a KS-only source does not have, so
the held-out numbers below use the source-only fit, i.e. what the tool computes. The feature port is checked against a
fixture computed by the research code, `tools/testdata/jamofill-parity.json` (18 rows across all three slots, keys and
numbers only, no glyph bitmap).

## Held-out results

The held-out lineages (Gothic A1, Windows, Un, iolo) never appear in training. Each face was built from its KS 2,350
syllables only, with and without `--fill`, and scored against the font's own bitmaps over the 8,822 non-KS syllables;
the proposals are the shipped `jamohybrid-v1.npz` run on the KS source. Bytes, sets, pieces, KS IoU and gate failures
are identical with and without the fill on every face; the fill only changes which stored group an unseen context
joins.

| face | lineage | non-KS IoU, KS-built | with `--fill` | gain | bytes, sets (I/M/F) |
|---|---|---|---|---|---|
| GothicA1 12 | gothica1 | 0.7138 | 0.7397 | +0.0259 | 31,504 B, 32/19/12 |
| GothicA1 Bold 12 | gothica1 | 0.6997 | 0.7259 | +0.0262 | 35,660 B, 32/23/13 |
| GulimXP 12 | windows | 0.8165 | 0.8537 | +0.0372 | 26,044 B, 31/20/7 |
| Magic 12 | windows | 0.8100 | 0.8339 | +0.0239 | 12,332 B, 10/15/9 |
| Pyunji 12 | windows | 0.7680 | 0.8469 | +0.0789 | 18,100 B, 25/12/6 |
| UnBatang 12 | un | 0.6600 | 0.7050 | +0.0450 | 35,256 B, 32/23/15 |
| UnDotum 12 | un | 0.7811 | 0.8240 | +0.0429 | 29,540 B, 32/22/11 |
| UnGungseo 12 | un | 0.7705 | 0.8315 | +0.0610 | 28,900 B, 32/20/7 |
| UnPilgi 12 | un | 0.8141 | 0.8533 | +0.0392 | 15,756 B, 20/10/5 |
| UnShinmun 12 | un | 0.7655 | 0.7990 | +0.0335 | 30,964 B, 32/23/8 |

Mean **+0.0414** (min +0.0239, max +0.0789); 0 pieces fail a gate on any face, with or without the fill. With the
label splitter's true pieces as proposals (the research setup) the mean is +0.0411, the same faces. Galmuri11 12 px
built from its KS 2,350: non-KS IoU 0.8565 to 0.8687 (exact 2,754 to 3,022), bytes 24,576 and KS IoU 0.9838 unchanged.

The fill only acts on contexts with no source syllable. A source that shows every context builds byte-identically:
Galmuri11 12 px from all 11,172 syllables has the same sha256 with and without the fill
(`16bfa1fd466fe6edb9474c68fa87660e0317830ad4c1bd908abdb4056da2bdae`, 26,176 B).

The held-out evaluation scored Microsoft Gulim (XP), Magic and Pyunji, the Un faces and Gothic A1. No bitmap of those
fonts is in this repository and none was used for training.
