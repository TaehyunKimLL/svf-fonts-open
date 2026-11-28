# jamohybrid-v1 weights

`jamohybrid-v1.npz` is the jamo split model of `tools/jamohybrid.py` (format `jamonet-1`, read by `tools/jamonet.py`).
Licence: MIT, like the code. [NOTICE](../../NOTICE.md#model-weights-toolsmodels) says what it was trained on.

| Item | Value |
|---|---|
| file | `jamohybrid-v1.npz`, 910,733 bytes |
| sha256 | `9cfc3547d894e98ef66113f6956a22d5465fa9376ba400e54d0bb649a67e016a` |
| model | U-Net, base 16 channels, 487,347 parameters as shipped (BatchNorm folded; 488,755 in torch), conditioned on L / V / T (embedding 16); fp16 |
| training command | `python3 tools/train_jamohybrid.py --manifest manifest-v1.tsv --epochs 20 --base 16 --seed 0 --out runs/b16-ship3 --eval apple-seoul12 gulim sans8j` (89.4 s on one GPU, 591 MiB peak) |
| numpy vs torch | on 2,944 training syllables: largest probability difference 3.7e-06 with float32 weights (the numpy code), 0.0040 with the shipped fp16 weights; 15 of 1,918,350 slot pixels change label at 0.5 |
| inference (numpy, 4 CPU threads) | 3.2 s for 2,357 syllables, 14.8 s for 11,172 |

The fp16 rounding of the weights is the only source of the difference; the torch side runs with TF32 off for the comparison.

## Training sources

No bitmap of the proprietary sources (kind `npz`) is in this repository. The `svf` sources are this repository's faces. The sha256 is that of the file the training script read.

| name | kind | group | licence | file | sha256 | syllables |
|---|---|---|---|---|---|---|
| Seoul12 | npz | apple-seoul12 | proprietary (Apple): HangulTalk 7.1.2 planes = System 7.5.3 strikes | `Seoul12.npz` | `f900697f6ddff5c7f9d7483be324fe4c827e5f25d6fdaf6f39fd128be417a63f` | 2,350 |
| AppleMyungjo12 | npz | apple-am12 | proprietary (Apple): HangulTalk 7.1.2 planes = System 7.5.3 strikes | `AppleMyungjo12.npz` | `d6acca98786bf4f76ea20f8f0a80518e483f034385b25948b3b56eb5de50c190` | 2,350 |
| AppleMyungjo24 | npz | apple-am24 | proprietary (Apple): HangulTalk 7.1.2 planes = System 7.5.3 strikes | `AppleMyungjo24.npz` | `227a077d1aec710d272abbdf06df48db520280e67056f3f98fe839b631226fec` | 2,350 |
| AppleGothic24 | npz | apple-ag24 | proprietary (Apple): HangulTalk 7.1.2 planes = System 7.5.3 strikes | `AppleGothic24.npz` | `cce19195f9bcbc2fb5ad392321fd6c554c7767b46ba27871a28222a8a84a9153` | 2,349 |
| Gulim12 | npz | gulim | proprietary (Microsoft): Windows 95 gulim.ttc EBDT component strikes | `Gulim12.npz` | `ea495fbb93791b50efdde559bc987cbdec681267f5ca985e8851f05b94b46c02` | 1,928 |
| Gulim16 | npz | gulim | proprietary (Microsoft): Windows 95 gulim.ttc EBDT component strikes | `Gulim16.npz` | `d6b5e78a2c0fd0a2b8e056ccf54af06ef7cda91dfba0f4cc30aba90651b05c99` | 1,928 |
| Gotic12 | npz | ht10 | proprietary (Apple): HangulTalk 1.0 fbit composition | `Gotic12.npz` | `ea84282d19b22b1b4ef175c84abd154cbf106a6eaa664af2e114942a8f90c1b3` | 2,350 |
| Munjo12 | npz | ht10 | proprietary (Apple): HangulTalk 1.0 fbit composition | `Munjo12.npz` | `f65cd0a76211b232abc16a5ad285b69d72c6bc981d741938f1261696e93831b8` | 2,350 |
| Munjo16 | npz | ht10 | proprietary (Apple): HangulTalk 1.0 fbit composition | `Munjo16.npz` | `d56671be81e010cd72cd5c9af3e267f2b2e813830253a01a7bd0bac432731690` | 2,350 |
| Munjo24 | npz | ht10 | proprietary (Apple): HangulTalk 1.0 fbit composition | `Munjo24.npz` | `6af0db37fd745143032de2c77a838a81165e1707fbb5e5cdbec7e3828b7f43db` | 2,350 |
| MARUS20 | svf | maru | OFL-1.1 (MaruBuri) | `MARUS20.SVF` | `8ef71d81b0cce93d1af77e2b57806842b1c2b71d771907edbefec2fd7deb3f4d` | 2,350 |
| MARUS24 | svf | maru | OFL-1.1 (MaruBuri) | `MARUS24.SVF` | `8f5edb2f114955c1f59c31cff2701c16baadf7105e844da71b96f24579295014` | 2,350 |
| NEODG16A | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16A.SVF` | `ed5771be5ca55d7dedd3066d24db6bc4af397e3d3cc23f14d4a22e32a0f898ed` | 2,350 |
| NEODG16B | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16B.SVF` | `443d825f7e5d471ab11cc8bfa2dd6db1b3167a00a54b282483bbb4d0e60c8cc5` | 2,350 |
| NEODG16C | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16C.SVF` | `3b4d56ce7c2f4ec563db96a5f756edbcea5b0969eb17e93b01dbd138980d370a` | 2,350 |
| NEODG16D | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16D.SVF` | `7d97f0dba946d5ff93e733582aa6339f7928fd6a6f7024c6c13688272e2d9b91` | 2,350 |
| NEODG16E | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16E.SVF` | `7e3d6065d110be17c5f19bd5738601b17b50c4d90c6c20247f4a1a1df72f3749` | 2,350 |
| NEODG16F | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16F.SVF` | `4225caeeaab9a51022b96ae02ecff4ac76e5f4b54e8c4925fa981cbd150a4853` | 2,350 |
| NEODG16G | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG16G.SVF` | `e3c7d0209bf9c92eacd0402bc848a7a14aa6635f06fbebc439a293cec71765a7` | 2,350 |
| NEODG32 | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG32.SVF` | `a85e642724beedd7b07f476cefcf5567d8e79bc7c8a13c2c9a274f2f82323cbf` | 2,350 |
| NEODG32A | svf | neodg | OFL-1.1 (Neo Dunggeunmo) | `NEODG32A.SVF` | `be375f9cd4729a5e76efa21e4fc2777ecb783ee095fe5448a9c0a542ba6dd2cf` | 2,350 |
| NSQRB36 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRB36.SVF` | `e5473c10969f7efd7c9e2e201897bd498c79550ce11072d2f7abc37a0eb9cb85` | 2,350 |
| NSQRR36 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRR36.SVF` | `29c96b72d5e42957f617a118ceb9d6d8f5694e0536861627b430e786d9b0b83a` | 2,350 |
| SANS8J | svf | sans8j | OFL-1.1 / MIT (iolo SANS8J) | `SANS8J.SVF` | `18954398d318e7d54a5754b21ddcacdf8f667700b677bcb0f89e3ba48c14908d` | 2,350 |
| GOTHA16 | svf | gotha | OFL-1.1 (Gothic A1) | `GOTHA16.SVF` | `1b7835cf78e40cae34f7c023d44b81b12fdc0d49882ca726cdf4c04ccd675426` | 2,350 |
| GOTHA18 | svf | gotha | OFL-1.1 (Gothic A1) | `GOTHA18.SVF` | `b3241346f4830b1c983b80f183ed8fcab040deafcd3253ff852fb0f62c06c245` | 2,350 |
| GOTHA20 | svf | gotha | OFL-1.1 (Gothic A1) | `GOTHA20.SVF` | `457dafd4bf6735b5214122e68403e10f054d52fe14b8d91196c8248bb03c4351` | 2,350 |
| GOTHA24 | svf | gotha | OFL-1.1 (Gothic A1) | `GOTHA24.SVF` | `ca71204358649540a4fbf1b4ccc044d30fe8c95c45e59353c985840e4843216a` | 2,350 |
| GOTHB16 | svf | gothb | OFL-1.1 (Gothic A1) | `GOTHB16.SVF` | `c3e3fad04a0a6b5fa455048be9d3b742dbc94156dd7a03982ad84dab93c5caab` | 2,350 |
| GOTHB18 | svf | gothb | OFL-1.1 (Gothic A1) | `GOTHB18.SVF` | `8c22f7cdc19e78abeeb74a714ca4749e935858fa5e321c116f01ea53e73d22e0` | 2,350 |
| GOTHB20 | svf | gothb | OFL-1.1 (Gothic A1) | `GOTHB20.SVF` | `b37852e99c0e0bd820f547bb2b963200f01174cb3ff8f3289831144db0d7a775` | 2,350 |
| GOTHB24 | svf | gothb | OFL-1.1 (Gothic A1) | `GOTHB24.SVF` | `255d80b6b20fca24a45a59de0c98e8e22d52b32f145cb37e5cfcce32eeb9b604` | 2,350 |
| NDGPR16 | svf | ndgpr | OFL-1.1 (Neo Dunggeunmo Pro) | `NDGPR16.SVF` | `6756bdee2345bee22e4412f7b1f7ae1de69292bf412aeb63515fecb25fd46f70` | 2,350 |
| NDGPR32 | svf | ndgpr | OFL-1.1 (Neo Dunggeunmo Pro) | `NDGPR32.SVF` | `835f6ad25964fa72abf0f79747963bd27ae492610da070fb7260dd22417fd872` | 2,350 |
| NSQRB16 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRB16.SVF` | `d10b31699a52df8cf917ba4c840ab94a82189e8bfae4b57729c0ceb3b59ec134` | 2,350 |
| NSQRB18 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRB18.SVF` | `e548133a8d0c5c751a15b6e2560dde43270960d2a63e7358377c3facd7e8bf90` | 2,350 |
| NSQRB20 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRB20.SVF` | `53037329756a0ca3b282c3c277f0e45911b7a39f0f517405871d445ec71e2220` | 2,350 |
| NSQRB24 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRB24.SVF` | `a4defde68c1fd1798349dcf3a4f281b97a97328a023a7b46a72c6e2dd64868f1` | 2,350 |
| NSQRR16 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRR16.SVF` | `9267d4f09781db3e588743605ff535122a2d4da4d219e7326c905fae5f80e66b` | 2,350 |
| NSQRR18 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRR18.SVF` | `d45568c73d90c8f5fd4b458d2389feee4f7698d4d45438e4d52a3b012483573e` | 2,350 |
| NSQRR20 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRR20.SVF` | `fc6228234d8322b79b3cc7ac2c19d3ce2fc2a4b1734da78d99f5868dedcbd7d5` | 2,350 |
| NSQRR24 | svf | nsqr | OFL-1.1 (NanumSquareRound) | `NSQRR24.SVF` | `bbfc697c89c7974c806ee9e801293a6814afe2f96143eb6868bbad211cc5c9d1` | 2,350 |
| SGDAY16 | svf | sgday | OFL-1.1 (Single Day) | `SGDAY16.SVF` | `70ce173fc98285bfeb10847a5db8f1cd42bb33ce865437ab124d398f6a79256c` | 2,350 |
| SGDAY18 | svf | sgday | OFL-1.1 (Single Day) | `SGDAY18.SVF` | `bc8fff7cb6cd2b668f28e06fe14d10b8a39c3be8395780ef5d0820d1cc2a3b0d` | 2,350 |
| SGDAY20 | svf | sgday | OFL-1.1 (Single Day) | `SGDAY20.SVF` | `b89e63fd0e44a923f697accd117f3dba8432daa5d2df2e27532a2c0cd51faa05` | 2,350 |
| SGDAY24 | svf | sgday | OFL-1.1 (Single Day) | `SGDAY24.SVF` | `0dc8b9c7da13174552a4f02a7b39380450fb7f728b8c297ef86f531cfe875a81` | 2,350 |

- Kind `npz`: ground-truth sets prepared outside this repository from the fonts named in the licence column.
  - Apple: HangulTalk 7.1.2 jamo planes, equal to the System 7.5.3 strikes of the same family.
  - Gulim: the Windows 95 strike syllables built from jamo component bitmaps (1,928 per size).
  - HangulTalk 1.0: compositions by the fonts' own rule.
- Kind `svf`: this repository's 1 bpp jamo-set faces (composed syllables and their pieces).

## Evaluation (held-out folds)

Each fold trains without one group (same command with `--holdout GROUP --eval GROUP`) and measures it: the share of ink pixels in the right slot (label accuracy) of the model's planes.

| held-out group | base 16 | base 32 |
|---|---|---|
| Seoul 12 | 0.998 | 0.997 |
| AppleMyungjo 12 | 0.988 | 0.989 |
| AppleMyungjo 24 | 0.994 | 0.995 |
| AppleGothic 24 | 0.997 | 0.996 |
| Windows 95 Gulim 12 / 16 | 0.991 / 0.986 | 0.991 / 0.986 |
| SANS8J | 0.997 | 0.998 |
| Neo Dunggeunmo Pro 16 / 32 | 0.955 / 0.962 | 0.949 / 0.951 |
| Single Day 16 / 18 / 20 / 24 | 0.970 / 0.949 / 0.976 / 0.987 | 0.972 / 0.945 / 0.976 / 0.987 |

Base 16 is never more than 0.002 below base 32 on a held-out face, and is shipped.

Faces built by `jamohybrid.py` with the fold model of each held-out face: bytes, composed IoU against the precomposed face, label accuracy of the built face's pieces.

| face | standard limits | `--big` |
|---|---|---|
| Seoul 12 | 14,088 B, 0.993, 0.995 | 17,920 B, 0.998, 1.000 |
| AppleMyungjo 12 | 18,160 B, 0.982, 0.984 | 34,980 B, 0.995, 0.992 |
| AppleMyungjo 24 | 29,784 B, 0.985, 0.990 | 44,592 B, 0.998, 0.997 |
| AppleGothic 24 | 28,096 B, 0.995, 0.996 | 44,732 B, 0.998, 0.998 |
| Gulim 12 | 23,736 B, 0.949, 0.958 | 35,172 B, 0.982, 0.984 |
| Gulim 16 | 26,220 B, 0.931, 0.948 | 42,980 B, 0.979, 0.982 |

For comparison, `jamoset.py --layout adaptive` on the same faces: 43-96 KB, IoU 0.973-0.999, label accuracy 0.66-0.73 (Gulim, on its 1,928 component syllables: 0.68 / 0.70).
