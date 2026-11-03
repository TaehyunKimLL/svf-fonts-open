# JSET pixel identity per block version

(Record from the original working repository, whose `svf/` held 153 faces; the rows of faces this repository does not
publish stay as part of that record.)

`svf/` stays JSET version 1 (spec amendment 3: v1 is the standard, v2 an exception format chosen per build or pack). The
version 2 faces below are **build outputs** of `svf2to3 --jset-version auto` in `c/build/jset2/` (not committed, not
shipped); they exist to prove the v2 reader and the v2 writer pixel for pixel. `git diff --quiet c592140 -- svf` holds.

Provenance (BASE b2c17a1; sources of the C library unchanged since):

- old reader: `c/build/jset1/bin/svfdump-asan` (Task 1: the version 1 reader of c592140), old faces `c/build/jset1/src/svf`
  (identical to `svf/`).
- new reader: `c/build/svfdump-asan` (all readers), `c/build/jset2/o1/svfdump-asan` (`-DSVF_JSET_V2=0`, v1 alone),
  `c/build/jset2/o2/svfdump-asan` (`-DSVF_JSET_V1=0`, v2 alone).
- v2 copies: `svf2to3.py --tree svf c/build/jset2/svf --profile default --jset-version auto --check` (153 faces, failed=0;
  auto writes v2 where the v1 block is >= 1024 B larger: 58 faces, the other 37 jamo faces stay v1). `diff -rq svf
  c/build/jset2/svf` names 58 `.SVF` files (each a jamo face now v2) and the `.TXT` files the tree conversion does not copy.
- Compared per face (script `c/bench/jset2-identity.py`): `info` (all INFO_KEYS; jamo faces `jamo=1 jset_bad=0` on both
  sides), `syllables` (mapped, and with `--stream` and `--stream=4:512` on both sides, all equal to the old mapped dump), `glyphs` by code point without plane 15, the plane-15 records as a sorted multiset, `--stream` and
  `--stream=4:512` glyphs equal to the mapped ones, every `LINE_TEXTS` line (6 texts) at `400 40 2 28`.
- Columns: JSET version of the new face, bytes of the old (v1) block, bytes of the new block, NA (alias count; `-` for v1),
  geometry lc x tc x ni x nm x nf, truncated sha256 of the syllable dump and of the six line dumps (old = new).

Other passes (every exit 0, `different=0`; the script proves it bites: a v2 copy with one plane-15 bit flipped exits 1 and
names the face):

- `svf/` against itself, default build: `faces=153 jamo=95 different=0 v1_faces=95 v1_bytes=652431 v2_faces=0 v2_bytes=0 jset_before=652431 jset_after=652431`
- `svf/` against itself, v1-only build (`-DSVF_JSET_V2=0`): the same line.
- copies, v2-only build (`-DSVF_JSET_V1=0`, `--only-version 2`): `faces=58 jamo=58 different=0 v1_faces=0 v1_bytes=0 v2_faces=58 v2_bytes=300898 jset_before=615634 jset_after=300898`
- every jamo face of `svf/` forced to v2 (`svf2to3.py --tree svf c/build/jset2all/svf --profile default --jset-version 2 --check`: 153 faces, failed=0), compared against `svf/` in the default build: `faces=153 jamo=95 different=0 v1_faces=0 v1_bytes=0 v2_faces=95 v2_bytes=310160 jset_before=652431 jset_after=310160`, and in the v2-only build (`--only-version 2`): `faces=95 jamo=95 different=0 v1_faces=0 v1_bytes=0 v2_faces=95 v2_bytes=310160 jset_before=652431 jset_after=310160`. This covers the 37 small faces `auto` leaves at v1 (the 8x4x4 and 6x2x1 geometries and the 7/2/2 face DKBHG24) in their v2 form.
- forced `--jset-version 2` of iolo/HGKEY6J.SVF alone (default build): `faces=1 jamo=1 different=0 v1_faces=0 v1_bytes=0 v2_faces=1 v2_bytes=181 jset_before=653 jset_after=181`

The table and total below are the auto copies against `svf/` in the default build (the numbers are deterministic):

| face | JSET version | v1 bytes | new bytes | NA | geometry | syllables sha256 | lines sha256 | identical |
|---|---:|---:|---:|---:|---|---|---|---|
| dos/AMYJO18.SVF | - | - | - | - | - | 283d73b150f27834 | b1e520b409408aef | yes |
| dos/BHSAN28.SVF | - | - | - | - | - | 26897799740daa91 | 6a3ebd15a4ded119 | yes |
| dos/COUSB24.SVF | - | - | - | - | - | 30a1584e80c15b9e | 93da75b8e0458b73 | yes |
| dos/DIPHY36.SVF | - | - | - | - | - | 299cf727a0263589 | adda8193395ed760 | yes |
| dos/DKBHG24.SVF | 1 | 745 | 745 | - | 1x2x7x2x2 | 0e7a104ff08707be | 1752a4c6567d8068 | yes |
| dos/GBA14X2.SVF | - | - | - | - | - | 49679d80200f544c | 55873fecc61a79e8 | yes |
| dos/GBA17BX1.SVF | - | - | - | - | - | fa31a50ff9435b97 | 55873fecc61a79e8 | yes |
| dos/GBA23AX2.SVF | - | - | - | - | - | e95a18e508d020dc | 55873fecc61a79e8 | yes |
| dos/GBA23X2.SVF | - | - | - | - | - | 7a5276746434856a | 55873fecc61a79e8 | yes |
| dos/GBATB14.SVF | - | - | - | - | - | bf15b7c9ab5a0c6e | 942f68c2b541b14b | yes |
| dos/GBATB17.SVF | - | - | - | - | - | 3f330332d808be77 | b67972180513f42a | yes |
| dos/GBATB17B.SVF | - | - | - | - | - | 9b0d41e7a10a4668 | b9b4a25b3b156317 | yes |
| dos/GBATB17O.SVF | - | - | - | - | - | 140442e7acfcbded | 32262350bec54717 | yes |
| dos/GBATB18.SVF | - | - | - | - | - | ce094085a1183c77 | c985b6472d7770f6 | yes |
| dos/GBATB18A.SVF | - | - | - | - | - | 1f1be795a1c495c9 | 89cd733f806ca381 | yes |
| dos/GBATB21.SVF | - | - | - | - | - | 940fd231aba7986d | 0e248bfe204a82b4 | yes |
| dos/GBATB23.SVF | - | - | - | - | - | 3be484f717ade3c5 | b02653a1584a1e70 | yes |
| dos/GBATB23A.SVF | - | - | - | - | - | 6921cad1cee8871b | b02653a1584a1e70 | yes |
| dos/GBATB31.SVF | - | - | - | - | - | 98be53ebf0b9ff7d | 8ac04a043b00b06d | yes |
| dos/GBATB35.SVF | - | - | - | - | - | 1380d2d53fff1fa8 | 71d188d034790816 | yes |
| dos/GBATB47.SVF | - | - | - | - | - | eeaddef6a14998f2 | ffd9bffa06028ec4 | yes |
| dos/GOTHB18A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | cca62a266a4c7a1b | 160ff035bc7b3898 | yes |
| dos/HTERM16.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 16472a0b9a9f8df7 | 3c585965a4f0199c | yes |
| dos/HWPHG24.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | c4ac09cceef615c9 | 2ddca5d46f23e1d9 | yes |
| dos/HWPHM24.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | aed0e10ae7f3796a | 5d51e4bb90c47386 | yes |
| dos/IYAGI16.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | ffe6ca4047653b4b | 6a6e790dd094eed9 | yes |
| dos/JGODK18.SVF | - | - | - | - | - | 371f2a7e3cce03ce | 6037ec66bd0cfdd1 | yes |
| dos/MARUB20A.SVF | 2 | 11681 | 5704 | 42 | 12x12x24x16x16 | dfa96aa7da5de5dc | 1d4e9e82927619b8 | yes |
| dos/MARUB24A.SVF | 2 | 11681 | 5716 | 48 | 12x12x24x16x16 | 85ac0d897fae0909 | c9d5f373a28604a9 | yes |
| dos/MARUS20.SVF | 2 | 11681 | 5714 | 47 | 12x12x24x16x16 | c4d00860e84efdb5 | f900f2c59a4a022a | yes |
| dos/MARUS24.SVF | 2 | 11681 | 5712 | 46 | 12x12x24x16x16 | bb1733f431cbb8dc | 6e089145d680df29 | yes |
| dos/MARUS24A.SVF | 2 | 11681 | 5712 | 46 | 12x12x24x16x16 | b7d4bd4495db601d | d747f0904885e811 | yes |
| dos/MUNJO24.SVF | 2 | 3783 | 1488 | 26 | 8x4x20x15x4 | 49d61ae41da16c8e | 927a7407f9df835d | yes |
| dos/NEO16BX2.SVF | - | - | - | - | - | 5e7847d821e8b866 | 55873fecc61a79e8 | yes |
| dos/NEODG16.SVF | - | - | - | - | - | c87b57281e5cbe80 | bc733a6b0073655f | yes |
| dos/NEODG16A.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 7b4ba24e546483c3 | 9b39fba36e47da5f | yes |
| dos/NEODG16B.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | bbb84931fbbeef75 | d1057f18fa325bff | yes |
| dos/NEODG16C.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 4600f0d8786f1bdf | d188495912669bf5 | yes |
| dos/NEODG16D.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 317d051e1fd6d3b1 | 9b39fba36e47da5f | yes |
| dos/NEODG16E.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | a0487aedb46e4498 | 9b39fba36e47da5f | yes |
| dos/NEODG16F.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | a0487aedb46e4498 | 9b39fba36e47da5f | yes |
| dos/NEODG16J.SVF | - | - | - | - | - | e6b8fac7cc47a749 | 73fb3034496cfbba | yes |
| dos/NEODG16K.SVF | - | - | - | - | - | be5493eeced9a2d0 | 69cc92489d4d2ea5 | yes |
| dos/NEODG16L.SVF | - | - | - | - | - | d4e263f3b8a772ec | ea6c86396211a241 | yes |
| dos/NEODG16O.SVF | - | - | - | - | - | 7984e5407cc76e35 | e7cedc7932dc294f | yes |
| dos/NEODG32.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 2e76837af9665b35 | 4cfd6574d07f26ea | yes |
| dos/NEODG32A.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | f3e3fc46803bf066 | 4cfd6574d07f26ea | yes |
| dos/NEODG32B.SVF | - | - | - | - | - | 4a9c89c5b0761ed4 | cc60440d70dc8dde | yes |
| dos/NGO15X1.SVF | - | - | - | - | - | 7ad32d5ebdf9b27d | 55873fecc61a79e8 | yes |
| dos/NGO15X2.SVF | - | - | - | - | - | 49679d80200f544c | 55873fecc61a79e8 | yes |
| dos/NGO16BX1.SVF | - | - | - | - | - | 738baf3fe392c9d2 | 55873fecc61a79e8 | yes |
| dos/NGO16BX2.SVF | - | - | - | - | - | 22077425bf5dff47 | 55873fecc61a79e8 | yes |
| dos/NGO17X1.SVF | - | - | - | - | - | 165953448645adcb | 55873fecc61a79e8 | yes |
| dos/NGO17X2.SVF | - | - | - | - | - | 11f7cfa38241b730 | 55873fecc61a79e8 | yes |
| dos/NGO21AX1.SVF | - | - | - | - | - | 0edec93cefa1d0e6 | 55873fecc61a79e8 | yes |
| dos/NGO21AX2.SVF | - | - | - | - | - | 7a5276746434856a | 55873fecc61a79e8 | yes |
| dos/NGOTB14.SVF | - | - | - | - | - | 0b2f5b04f7302a3d | 245430dfa46ae80e | yes |
| dos/NGOTB15.SVF | - | - | - | - | - | 2ce6189ac347e112 | 7e441e63ac8f26f3 | yes |
| dos/NGOTB15A.SVF | - | - | - | - | - | 6efe209a8ec3a414 | 6d95fe8c310b1087 | yes |
| dos/NGOTB15B.SVF | - | - | - | - | - | 9240ded16c63bb41 | 0ed14ff37cdd08b9 | yes |
| dos/NGOTB15C.SVF | - | - | - | - | - | df854522c8c0b5ab | dac966c862d6f79d | yes |
| dos/NGOTB16.SVF | - | - | - | - | - | fb54ab750d6c0b18 | 41f2d1fdbcaa0e65 | yes |
| dos/NGOTB16B.SVF | - | - | - | - | - | cb2075dc348f159b | 8eaad6acd8eca3e6 | yes |
| dos/NGOTB16D.SVF | - | - | - | - | - | 46bf4bc8423dc9f1 | 916ed09d7ea1725d | yes |
| dos/NGOTB16E.SVF | - | - | - | - | - | 6536ece548eaa3ee | a2c02ae8184c3bc4 | yes |
| dos/NGOTB17.SVF | - | - | - | - | - | c954c780348f226d | 1c01e1fa1eab16b0 | yes |
| dos/NGOTB17A.SVF | - | - | - | - | - | 28c22f90ca4197ba | 15883de09d2381c2 | yes |
| dos/NGOTB19.SVF | - | - | - | - | - | 8250bde5114454f9 | 84404f0c3f5f3f5a | yes |
| dos/NGOTB21.SVF | - | - | - | - | - | 72a1b2ae4c61f1e8 | 58143e4b913953e6 | yes |
| dos/NGOTB21A.SVF | - | - | - | - | - | 26f103510c7a00ad | 58143e4b913953e6 | yes |
| dos/NGOTB22.SVF | - | - | - | - | - | aae0e2b1120fcd78 | 9518f93c3a82f2d6 | yes |
| dos/NSQRB36.SVF | 2 | 11681 | 5928 | 154 | 12x12x24x16x16 | ce9ad674a9e19a91 | 0a6b5c6c86a59406 | yes |
| dos/NSQRB36A.SVF | 2 | 11681 | 5928 | 154 | 12x12x24x16x16 | 06c7e387f3029c98 | 211f0b3a548f6971 | yes |
| dos/NSQRR16A.SVF | 2 | 11681 | 5926 | 153 | 12x12x24x16x16 | 0f151227af7731f8 | dd2edcce42cd24f1 | yes |
| dos/NSQRR36.SVF | 2 | 11681 | 5934 | 157 | 12x12x24x16x16 | 17b7bf86778bd47b | 0156a32c0d48c5c6 | yes |
| dos/NSQRR36A.SVF | 2 | 11681 | 5934 | 157 | 12x12x24x16x16 | 918b72c3f99622ca | f91333b02907a062 | yes |
| dos/PAPER16A.SVF | 2 | 11681 | 5824 | 102 | 12x12x24x16x16 | 1430f797c4b0372f | 4f393a079fdf827c | yes |
| dos/PAPER18A.SVF | 2 | 11681 | 5862 | 121 | 12x12x24x16x16 | cb43972e980a2dfa | e7ee073a01db8d1d | yes |
| dos/PAPLB16A.SVF | 2 | 11681 | 5818 | 99 | 12x12x24x16x16 | 6a2cf4e8b3ddbe0d | ad6f8dab039ce0c6 | yes |
| dos/PAPLB18A.SVF | 2 | 11681 | 5848 | 114 | 12x12x24x16x16 | 5e9aa0bdc4bc5fe5 | cb477b8d5d5ab72e | yes |
| dos/PAPLB20A.SVF | 2 | 11681 | 5838 | 109 | 12x12x24x16x16 | d679f89d945ccfc3 | 10985868f5789f57 | yes |
| dos/PAPLG16.SVF | - | - | - | - | - | 653053e07948ecc6 | c0a49dec2c5fa226 | yes |
| dos/PAPLG18.SVF | 2 | 11681 | 5862 | 121 | 12x12x24x16x16 | cb43972e980a2dfa | 88fe39002c957b59 | yes |
| dos/SANGAM16.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 2fca2a44e41e9c5e | 9cdd987f959fcde1 | yes |
| dos/SMYJO18.SVF | - | - | - | - | - | b658644532013992 | b1e520b409408aef | yes |
| dos/TBG24X2.SVF | - | - | - | - | - | 690a76bb5a28768c | 55873fecc61a79e8 | yes |
| dos/TBGHC48.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 5b271aac71e4b6ef | 4fd2ac7a5426918a | yes |
| dos/TBGHN40.SVF | - | - | - | - | - | d1fd0ca19aaa18af | 9670301f415f3598 | yes |
| dos/TBGOB24.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 660e697c265be23d | eae169d6d4167081 | yes |
| dos/TBM24X2.SVF | - | - | - | - | - | 690a76bb5a28768c | 55873fecc61a79e8 | yes |
| dos/TBMY24.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 42d30518803820b7 | 2a8b8b0f553e19b3 | yes |
| dos/TBTHG16.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 972028d453f94143 | 46451d1a37c3124f | yes |
| dos/WCOMM16.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | a90b35b6742b3c97 | 86204d4513a0deab | yes |
| dos/YOUTH36.SVF | - | - | - | - | - | 97a91e906dc42d2d | 40d8f59249880dc2 | yes |
| games/lb1/DKBHG40.SVF | - | - | - | - | - | 6f8da8b4afef4b40 | 401e8e27a560bcb3 | yes |
| iolo/AD248J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | c9240301b3787780 | 8953f8199bb4b44a | yes |
| iolo/DKBY8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | ca190dfc3e8af585 | 8f071ededcb4db04 | yes |
| iolo/HANME8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 13a5e7ee52caaaf6 | e174c7f23051ab44 | yes |
| iolo/HGKEY6J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | 3c89600aa6530e9d | 5fe3cbbbc1fa61e9 | yes |
| iolo/HLINK6J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | c7777f471571213e | 48559e16c14d0144 | yes |
| iolo/JOONG6J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | 043216116f1845de | 94a3bf097917d031 | yes |
| iolo/MR1286J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | bd27d8cd40d0a49f | 74a4af537b7746e9 | yes |
| iolo/PILGI8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | b584697d38511489 | 3625ceef69d2f057 | yes |
| iolo/ROMAX6J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | c1713615781bf3d0 | 8970b08c60a4ff8f | yes |
| iolo/SAM8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | a2b9e303153d1c11 | 56a72937991647c8 | yes |
| iolo/SAN8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | ca7e77ee7e75dc91 | faad6eb8c8a2c75a | yes |
| iolo/SANS8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | bade713bf26ef4b4 | f15acd59f941f38b | yes |
| iolo/SCRN96J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | 1d486d868949f9f8 | 1717d32328d616c8 | yes |
| iolo/SERIF8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 402278d4059c072f | 47ba67338a690af8 | yes |
| iolo/THIN8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | 26f26ebbd715e505 | b675cc48234fd646 | yes |
| iolo/U4K8J.SVF | 1 | 1101 | 1101 | - | 2x2x8x4x4 | ffb02d625fb09436 | 9c5bc34da9a88de7 | yes |
| iolo/WCOMM6J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | 51bbc10e0375bc9f | 1c921e2ef976d0b7 | yes |
| iolo/WOORI6J.SVF | 1 | 653 | 653 | - | 1x2x6x2x1 | cacfd877ae7d1e05 | cdec1a2c18f2b6a2 | yes |
| jamo-extra/GOTHA16.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | adb0cd3f5e3739f4 | 0753341a89fb156d | yes |
| jamo-extra/GOTHA16A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 6d4afd6d517b9941 | 43ec9ccbf1c7032c | yes |
| jamo-extra/GOTHA18.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 2853ba401498502d | 00068b998a708fd0 | yes |
| jamo-extra/GOTHA18A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | a7073daf64ce62d8 | 9b9c20c9dea9dbe2 | yes |
| jamo-extra/GOTHA20.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 36ebe2fbc87248ab | ab58f2fd34e0c5c5 | yes |
| jamo-extra/GOTHA20A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 9119e7b623b6540c | 44125a0bbadb9672 | yes |
| jamo-extra/GOTHA24.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 107c8ad1b884af0f | a01b34e957b43179 | yes |
| jamo-extra/GOTHA24A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | c56b8bb0231c0b65 | 55a47d7d38a605da | yes |
| jamo-extra/GOTHB16.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | fefc4e8d7d6996ae | f90be32dcbd2587a | yes |
| jamo-extra/GOTHB16A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 8431598889668fab | 716dbcd75ace4c76 | yes |
| jamo-extra/GOTHB18.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 1e525263d4e01d37 | b6ae1a7f1324ace4 | yes |
| jamo-extra/GOTHB20.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 200e6413efe49fd5 | 3708d2bab1e74cb1 | yes |
| jamo-extra/GOTHB20A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 5fe2ff76d70d378b | 8244a5445423ae70 | yes |
| jamo-extra/GOTHB24.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 6d460ed9467f2f60 | 4c64b6d3bfaa7435 | yes |
| jamo-extra/GOTHB24A.SVF | 2 | 11681 | 5324 | 0 | 12x12x24x16x16 | 5ec1d2577a65075b | 586e48473cff45b8 | yes |
| jamo-extra/NDGPR16.SVF | 2 | 5651 | 2742 | 209 | 8x8x21x8x6 | f18875d8c685b976 | c70334665ec49155 | yes |
| jamo-extra/NDGPR32.SVF | 2 | 5613 | 2690 | 188 | 8x8x20x8x6 | 1b3a78c3ace43189 | 097bcdb405719bcc | yes |
| jamo-extra/NSQRB16.SVF | 2 | 11681 | 5922 | 151 | 12x12x24x16x16 | 23eb2b939fe64c03 | 9ba3e3235cc76121 | yes |
| jamo-extra/NSQRB16A.SVF | 2 | 11681 | 5922 | 151 | 12x12x24x16x16 | ec8250f2e60784a0 | 5baf3d9d9a674e9a | yes |
| jamo-extra/NSQRB18.SVF | 2 | 11681 | 5926 | 153 | 12x12x24x16x16 | 701d998e73b5fa13 | 5ca63849e0fe2cda | yes |
| jamo-extra/NSQRB18A.SVF | 2 | 11681 | 5926 | 153 | 12x12x24x16x16 | d7a429cc77e9a1b4 | 696e6ae2e43c4ff5 | yes |
| jamo-extra/NSQRB20.SVF | 2 | 11681 | 5900 | 140 | 12x12x24x16x16 | 574ce4a12f5fe0e7 | 3a94949efd35cab3 | yes |
| jamo-extra/NSQRB20A.SVF | 2 | 11681 | 5900 | 140 | 12x12x24x16x16 | db3e07ba28c4b2d8 | 44d291e1f4d838f2 | yes |
| jamo-extra/NSQRB24.SVF | 2 | 11681 | 5958 | 169 | 12x12x24x16x16 | 7a7cce8d3bcc8cdb | ea1161c19ea17989 | yes |
| jamo-extra/NSQRB24A.SVF | 2 | 11681 | 5958 | 169 | 12x12x24x16x16 | f085c61842b86102 | 61c2076f1ae27326 | yes |
| jamo-extra/NSQRR16.SVF | 2 | 11681 | 5926 | 153 | 12x12x24x16x16 | e816c7e9caac793f | 8718719f8d9e5864 | yes |
| jamo-extra/NSQRR18.SVF | 2 | 11681 | 5896 | 138 | 12x12x24x16x16 | f7658b9126891f1f | 5c3735db4d025345 | yes |
| jamo-extra/NSQRR18A.SVF | 2 | 11681 | 5896 | 138 | 12x12x24x16x16 | 37ee5b8efa2ad948 | 0b9a1051d1eac192 | yes |
| jamo-extra/NSQRR20.SVF | 2 | 11681 | 5920 | 150 | 12x12x24x16x16 | 8c2652eaedceb5bf | bf07105ff1d04044 | yes |
| jamo-extra/NSQRR20A.SVF | 2 | 11681 | 5920 | 150 | 12x12x24x16x16 | af3b5b4d8e28b90b | 6b6e1c2205253d14 | yes |
| jamo-extra/NSQRR24.SVF | 2 | 11681 | 5902 | 141 | 12x12x24x16x16 | 176b72164897967b | 0d9dece1faa5b8be | yes |
| jamo-extra/NSQRR24A.SVF | 2 | 11681 | 5902 | 141 | 12x12x24x16x16 | a3103f14cb0400b4 | e3715480bdc25633 | yes |
| jamo-extra/SGDAY16.SVF | 2 | 6641 | 3472 | 291 | 8x8x24x16x16 | c3c818ded672ea7f | c91c77e9e0a559db | yes |
| jamo-extra/SGDAY16A.SVF | 2 | 6641 | 3472 | 291 | 8x8x24x16x16 | cd1d76e458845260 | 9244c2305b0e80d8 | yes |
| jamo-extra/SGDAY18.SVF | 2 | 6449 | 3270 | 212 | 8x8x24x14x14 | 0f78aef0718ea262 | 61adc18a86aeffa2 | yes |
| jamo-extra/SGDAY18A.SVF | 2 | 6449 | 3270 | 212 | 8x8x24x14x14 | 188d0f40e0931cd3 | 18ad47593dac3d48 | yes |
| jamo-extra/SGDAY20.SVF | 2 | 6275 | 3228 | 210 | 8x8x24x15x10 | a221eb7c76c4d76f | 9d0f3ec9b8b7dd60 | yes |
| jamo-extra/SGDAY20A.SVF | 2 | 6275 | 3228 | 210 | 8x8x24x15x10 | 2a55947e985b5e7c | cdf6df990c2d5ebd | yes |
| jamo-extra/SGDAY24.SVF | 2 | 6425 | 3410 | 284 | 8x8x24x16x12 | 5a74d480205ce6b7 | 864d62ce57f309e3 | yes |
| jamo-extra/SGDAY24A.SVF | 2 | 6425 | 3410 | 284 | 8x8x24x16x12 | e39e3f143579fa03 | 055d7dc9ecc1b132 | yes |

faces=153 jamo=95 different=0 v1_faces=37 v1_bytes=36797 v2_faces=58 v2_bytes=300898 jset_before=652431 jset_after=337695

| new version | geometry lc x tc x ni x nm x nf | faces | mean v1 bytes | mean new bytes |
|---:|---|---:|---:|---:|
| 1 | 1 x 2 x 6 x 2 x 1 | 8 | 653.0 | 653.0 |
| 1 | 1 x 2 x 7 x 2 x 2 | 1 | 745.0 | 745.0 |
| 1 | 2 x 2 x 8 x 4 x 4 | 28 | 1101.0 | 1101.0 |
| 2 | 12 x 12 x 24 x 16 x 16 | 47 | 11681.0 | 5685.5 |
| 2 | 8 x 4 x 20 x 15 x 4 | 1 | 3783.0 | 1488.0 |
| 2 | 8 x 8 x 20 x 8 x 6 | 1 | 5613.0 | 2690.0 |
| 2 | 8 x 8 x 21 x 8 x 6 | 1 | 5651.0 | 2742.0 |
| 2 | 8 x 8 x 24 x 14 x 14 | 2 | 6449.0 | 3270.0 |
| 2 | 8 x 8 x 24 x 15 x 10 | 2 | 6275.0 | 3228.0 |
| 2 | 8 x 8 x 24 x 16 x 12 | 2 | 6425.0 | 3410.0 |
| 2 | 8 x 8 x 24 x 16 x 16 | 2 | 6641.0 | 3472.0 |

Known limit: the libFuzzer runs (Task 10: `fuzz-open`, `fuzz-open-rd`, 1 h each) use the default build only (both readers, `SVF_JSET_POP4` on). The v1-only and v2-only builds differ from it in the version dispatch and `SVF__JSET_LOAD_MAX`; the deterministic bad-kind tests (`test_c_renderer.py`) cover both of them, and the trusted builds are not fuzzed (the harnesses refuse to compile with `SVF_JSET_TRUSTED`).

## Identity sweep for JSET v3 (JMAP) and BIG (Task 18, card t_380104f8, 2026-10-27)

Branch `jset-limits` at 84ae0cf against the base 2fb312d (the tree before the plan `docs/superpowers/plans/2026-10-26-jset-v3-jmap-big.md`).
Nothing in `svf/` has a JMAP block or a BIG-sized table, so the branch must read every face of `svf/` (and its v2 copies) to
the pixels of the base reader, and the writer must emit the base's bytes.

Commands (`$B` = the base svfdump, `$N` = a branch svfdump; the builds are `make -C c O=DIR CFLAGS="-O2 FLAGS" svfdump` in a
tree extracted with `git archive 2fb312d | tar -x -C /tmp/base-src` for the base, in this worktree for the branch):

- base: `make -C /tmp/base-src/c O=/tmp/t18/base svfdump`
- branch builds: default (JMAP and BIG on, host), `-DSVF_JSET_V2=0` (v1-only), `-DSVF_JSET_V1=0` (v2-only), `-DSVF_JMAP=0`
  (JMAP-off), `-DSVF_JSET_BIG=0` (BIG-off).
- reader identity: `python3 c/bench/jset2-identity.py $B $N svf svf OUT.md` (default, v1-only, JMAP-off, BIG-off), the v2
  copies `python3 c/bench/jset2-identity.py $B $N svf COPIES OUT.md [--only-version 2]`, with `COPIES` from
  `python3 tools/svf2to3.py --tree svf COPIES --profile default --jset-version auto --check` (branch tree).

Results (every exit 0):

| pass | build | totals |
|---|---|---|
| `svf/` against itself | default | `faces=153 jamo=95 different=0 v1_faces=95 v1_bytes=652431 v2_faces=0 v2_bytes=0 jset_before=652431 jset_after=652431` |
| `svf/` against itself | v1-only | the same line |
| `svf/` against itself | JMAP-off | the same line |
| `svf/` against itself | BIG-off | the same line |
| auto copies (58 v2, 37 v1) | default | `faces=153 jamo=95 different=0 v1_faces=37 v1_bytes=36797 v2_faces=58 v2_bytes=300898 jset_before=652431 jset_after=337695` |
| auto copies, `--only-version 2` | v2-only | `faces=58 jamo=58 different=0 v1_faces=0 v1_bytes=0 v2_faces=58 v2_bytes=300898 jset_before=615634 jset_after=300898` |
| auto copies | JMAP-off | the default line |
| auto copies | BIG-off | the default line |
| every jamo face forced to v2 (`--jset-version 2`) | default | `faces=153 jamo=95 different=0 v1_faces=0 v1_bytes=0 v2_faces=95 v2_bytes=310160 jset_before=652431 jset_after=310160` |

Writer identity: `python3 tools/svf2to3.py --tree svf OUT [--profile default --jset-version auto|2 --check]` run in the base
tree and in this worktree gives `diff -rq` empty for the default (no option), `--jset-version auto` and `--jset-version 2`
(153 `.SVF` files each, byte-identical).

Not covered here: the JMAP and BIG readers on faces that use them (their tests are `tools.test_c_renderer`, the type-3 and
HangulTalk goldens and the fuzz runs of Tasks 8 and 17); the trusted builds.

## Identity sweep for JMAP-LIST (Task 11, card t_3a5f76a5, parent t_455b15cb, 2026-10-28)

Branch `jmap-list` at 448b61c against the base fa76afb (the tree before the plan `docs/superpowers/plans/2026-10-27-jmap-list.md`).
Nothing in `svf/` has a LIST block, so the branch must read every face of `svf/` to the pixels of the base reader in every
build, and the writers must emit the base's bytes.

Commands (`$B` = the base svfdump, `$N` = a branch svfdump; the base is built in a tree extracted with `git archive fa76afb |
tar -x -C /tmp/base-fa76afb`, the branch builds in this worktree):

- base: `make -C /tmp/base-fa76afb/c O=/tmp/t11/base svfdump`
- branch builds: `make -C c O=/tmp/t11/nK CFLAGS="-O2 FLAGS" svfdump` with FLAGS empty (default: JMAP and LIST on, host),
  `-DSVF_JMAP_LIST=0`, `-DSVF_JSET_V2=0`, `-DSVF_JMAP=0`.
- reader identity: `python3 c/bench/jset2-identity.py $B $N /tmp/base-fa76afb/svf svf OUT.md`.

Results (every exit 0):

| pass | build | totals |
|---|---|---|
| `svf/` against the base | default | `faces=153 jamo=95 different=0 v1_faces=95 v1_bytes=652431 v2_faces=0 v2_bytes=0 jset_before=652431 jset_after=652431` |
| `svf/` against the base | `-DSVF_JMAP_LIST=0` | the same line |
| `svf/` against the base | `-DSVF_JSET_V2=0` | the same line |
| `svf/` against the base | `-DSVF_JMAP=0` | the same line |

Writer identity: `python3 tools/svf2to3.py --tree svf OUT --profile P [--jset-version 2]` run in the base tree and in this
worktree; `diff -rq` empty, 153 `.SVF` files each, for profile `default`, `dos`, and both with `--jset-version 2`.

Not covered here: the LIST reader on faces that use it (`tools.test_c_renderer` `test_jmap_list_*`, the status matrix, the
`jamoexc` C golden and the Task 10 fuzz runs: five 1 h libFuzzer runs, clean) and the trusted builds.
