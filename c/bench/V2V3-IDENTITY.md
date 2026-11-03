# v2 / v3 identity of the 153 faces of svf/

(Record from the original working repository, whose `svf/` held 153 faces; the rows of faces this repository does not
publish stay as part of that record.)

Provenance (Task 6 fix round 1; the table below is the script's output, this header is written by hand):

- v2 tree: the 153 `.SVF` faces of `svf/` at commit 3e25fba (identical to `svf/` at 4453856, the last commit with the
  v2-only C reader).
- v3 tree: `svf/` of this branch (the 153 converted faces, `default` profile; commit 5f264c7 and its descendants, the
  face bytes unchanged since).
- v2 binary: `c/build/v2/bin/svfdump-asan`, `make svfdump-asan` of the v2-only C library, whose sources are those of
  commit 4453856 (`c/src`, `c/include`, `c/tests/svfdump.c`).
- v3 binary: `c/build/svfdump-asan` built from this commit's sources (`make -C c check` builds it).
- Command (repository root; the script imports `LINE_TEXTS` from `tools/test_c_renderer.py`, all 6 texts, and matches
  `*.svf` case-insensitively, failing on a path present in only one tree):

      python3 c/bench/v2v3-identity.py c/build/v2/bin/svfdump-asan c/build/svfdump-asan c/build/v2/src/svf svf c/bench/V2V3-IDENTITY.md

  Result: exit 0, `total faces=153 identical=153 different=0 glyphs=159680 ... unmatched=0`.
- The three sha256 columns are truncated to the first 16 hex digits (64 bits). Glyph dump: sha256 over the code
  points in order, each as 4 bytes little endian plus its record (metrics bytes and cell). Syllables: sha256 of the
  `syllables` dump. Lines: sha256 of the `line` dumps of all 6 texts concatenated, drawn at `400 40 2 28`.

| face | glyphs | v2 bytes | v3 bytes | glyph dump sha256 | syllables sha256 | lines sha256 | identical |
|---|---:|---:|---:|---|---|---|---|
| dos/AMYJO18.SVF | 2359 | 169884 | 150856 | a468dd3e05553e58 | 283d73b150f27834 | b1e520b409408aef | yes |
| dos/BHSAN28.SVF | 1214 | 252548 | 175616 | a4e16227e41a2b07 | 26897799740daa91 | 6a3ebd15a4ded119 | yes |
| dos/COUSB24.SVF | 95 | 19796 | 8788 | 114b47388aeae0d5 | 30a1584e80c15b9e | 93da75b8e0458b73 | yes |
| dos/DIPHY36.SVF | 2359 | 452964 | 368676 | 9f3057e2537adc34 | 299cf727a0263589 | adda8193395ed760 | yes |
| dos/DKBHG24.SVF | 325 | 28081 | 18632 | 554558a6a0746d64 | 0e7a104ff08707be | 1752a4c6567d8068 | yes |
| dos/GBA14X2.SVF | 4 | 340 | 212 | 96fff83ead7723aa | 49679d80200f544c | 55873fecc61a79e8 | yes |
| dos/GBA17BX1.SVF | 3 | 576 | 220 | 2363050c200d0727 | fa31a50ff9435b97 | 55873fecc61a79e8 | yes |
| dos/GBA23AX2.SVF | 4 | 756 | 316 | dc5a539acc3055e9 | e95a18e508d020dc | 55873fecc61a79e8 | yes |
| dos/GBA23X2.SVF | 4 | 660 | 316 | 5fa4b3dfb8104019 | 7a5276746434856a | 55873fecc61a79e8 | yes |
| dos/GBATB14.SVF | 2446 | 185932 | 162268 | 1c13590b97661a2f | bf15b7c9ab5a0c6e | 942f68c2b541b14b | yes |
| dos/GBATB17.SVF | 3155 | 239816 | 245564 | 1390729bf0979079 | 3f330332d808be77 | b67972180513f42a | yes |
| dos/GBATB17B.SVF | 2446 | 440316 | 205844 | 3a6c01eef28bb6d6 | 9b0d41e7a10a4668 | b9b4a25b3b156317 | yes |
| dos/GBATB17O.SVF | 1231 | 137908 | 142824 | f8bef600110d82bf | 140442e7acfcbded | 32262350bec54717 | yes |
| dos/GBATB18.SVF | 942 | 96120 | 86800 | dcca5772352dcd51 | ce094085a1183c77 | c985b6472d7770f6 | yes |
| dos/GBATB18A.SVF | 1216 | 124068 | 113860 | ef436c86aa4bef62 | 1f1be795a1c495c9 | 89cd733f806ca381 | yes |
| dos/GBATB21.SVF | 1216 | 175140 | 138984 | 532f0509a088c986 | 940fd231aba7986d | 0e248bfe204a82b4 | yes |
| dos/GBATB23.SVF | 2446 | 381612 | 338948 | da14c11b22c8a51c | 3be484f717ade3c5 | b02653a1584a1e70 | yes |
| dos/GBATB23A.SVF | 2446 | 440316 | 336584 | 3db07dd9da12c9ae | 6921cad1cee8871b | b02653a1584a1e70 | yes |
| dos/GBATB31.SVF | 1121 | 300464 | 245304 | 1156c7399d94d20a | 98be53ebf0b9ff7d | 8ac04a043b00b06d | yes |
| dos/GBATB35.SVF | 2446 | 821892 | 682276 | 7a70d2d3d8fa93cb | 1380d2d53fff1fa8 | 71d188d034790816 | yes |
| dos/GBATB47.SVF | 2446 | 1614396 | 1162764 | 27fbfe444926ace7 | eeaddef6a14998f2 | ffd9bffa06028ec4 | yes |
| dos/GOTHB18A.SVF | 1320 | 146357 | 84492 | 50ccfb24d188ae5f | cca62a266a4c7a1b | 160ff035bc7b3898 | yes |
| dos/HTERM16.SVF | 440 | 20497 | 16668 | ec0650d22cad0ede | 16472a0b9a9f8df7 | 3c585965a4f0199c | yes |
| dos/HWPHG24.SVF | 440 | 38097 | 26848 | 1cd57fb8102d7a86 | c4ac09cceef615c9 | 2ddca5d46f23e1d9 | yes |
| dos/HWPHM24.SVF | 440 | 38097 | 25692 | 34f9755c7fc77472 | aed0e10ae7f3796a | 5d51e4bb90c47386 | yes |
| dos/IYAGI16.SVF | 441 | 20541 | 15772 | 5a207c49fb70c5dc | ffe6ca4047653b4b | 6a6e790dd094eed9 | yes |
| dos/JGODK18.SVF | 2359 | 155730 | 151048 | d7d389906b690063 | 371f2a7e3cce03ce | 6037ec66bd0cfdd1 | yes |
| dos/MARUB20A.SVF | 1294 | 156645 | 91380 | 4ccb412b9524bdc2 | dfa96aa7da5de5dc | 1d4e9e82927619b8 | yes |
| dos/MARUB24A.SVF | 1288 | 212645 | 110104 | 68144554d195f426 | 85ac0d897fae0909 | c9d5f373a28604a9 | yes |
| dos/MARUS20.SVF | 1289 | 104525 | 75096 | e02d0b0b6f0725a6 | c4d00860e84efdb5 | f900f2c59a4a022a | yes |
| dos/MARUS24.SVF | 1290 | 120077 | 87956 | 73f147f9ae1136d8 | bb1733f431cbb8dc | 6e089145d680df29 | yes |
| dos/MARUS24A.SVF | 1290 | 212957 | 107508 | 883b2c2f788e0ab2 | b7d4bd4495db601d | d747f0904885e811 | yes |
| dos/MUNJO24.SVF | 655 | 58839 | 36660 | 121fdb667a2eb8b4 | 49d61ae41da16c8e | 927a7407f9df835d | yes |
| dos/NEO16BX2.SVF | 2 | 124 | 116 | 12f89e62ed267efa | 5e7847d821e8b866 | 55873fecc61a79e8 | yes |
| dos/NEODG16.SVF | 2905 | 127856 | 133720 | a3cbfe018825508e | c87b57281e5cbe80 | bc733a6b0073655f | yes |
| dos/NEODG16A.SVF | 440 | 20497 | 16408 | 05f2b1ccbd793b84 | 7b4ba24e546483c3 | 9b39fba36e47da5f | yes |
| dos/NEODG16B.SVF | 441 | 20541 | 16152 | 01af3e0825302943 | bbb84931fbbeef75 | d1057f18fa325bff | yes |
| dos/NEODG16C.SVF | 538 | 24809 | 20164 | d0519be661e1aeb2 | 4600f0d8786f1bdf | d188495912669bf5 | yes |
| dos/NEODG16D.SVF | 440 | 35457 | 16328 | 12f302d7f4a1ab2a | 317d051e1fd6d3b1 | 9b39fba36e47da5f | yes |
| dos/NEODG16E.SVF | 440 | 38097 | 16328 | 10ebb9a7574d052c | a0487aedb46e4498 | 9b39fba36e47da5f | yes |
| dos/NEODG16F.SVF | 440 | 38097 | 16328 | a7115cc3d43e95dd | a0487aedb46e4498 | 9b39fba36e47da5f | yes |
| dos/NEODG16J.SVF | 779 | 51450 | 35544 | ed08eaaf13834001 | e6b8fac7cc47a749 | 73fb3034496cfbba | yes |
| dos/NEODG16K.SVF | 942 | 62208 | 43332 | 1a3102576b0cb0d7 | be5493eeced9a2d0 | 69cc92489d4d2ea5 | yes |
| dos/NEODG16L.SVF | 1120 | 73956 | 51820 | b17aa95d162e17d2 | d4e263f3b8a772ec | ea6c86396211a241 | yes |
| dos/NEODG16O.SVF | 1231 | 137908 | 128000 | 08822156cc510285 | 7984e5407cc76e35 | e7cedc7932dc294f | yes |
| dos/NEODG32.SVF | 440 | 85617 | 31496 | e27deae40e868504 | 2e76837af9665b35 | 4cfd6574d07f26ea | yes |
| dos/NEODG32A.SVF | 440 | 148977 | 31496 | af16212f5c0d5805 | f3e3fc46803bf066 | 4cfd6574d07f26ea | yes |
| dos/NEODG32B.SVF | 1120 | 156836 | 131264 | 66c89b5af85f9a2f | 4a9c89c5b0761ed4 | cc60440d70dc8dde | yes |
| dos/NGO15X1.SVF | 3 | 264 | 196 | 313853a0852ea73b | 7ad32d5ebdf9b27d | 55873fecc61a79e8 | yes |
| dos/NGO15X2.SVF | 4 | 340 | 204 | cc6868dd439f1b67 | 49679d80200f544c | 55873fecc61a79e8 | yes |
| dos/NGO16BX1.SVF | 3 | 342 | 204 | 732bcbf90be1d8c1 | 738baf3fe392c9d2 | 55873fecc61a79e8 | yes |
| dos/NGO16BX2.SVF | 4 | 444 | 208 | 724a6ac119e6da66 | 22077425bf5dff47 | 55873fecc61a79e8 | yes |
| dos/NGO17X1.SVF | 2 | 168 | 136 | 9d2ee3caf8cdd315 | 165953448645adcb | 55873fecc61a79e8 | yes |
| dos/NGO17X2.SVF | 3 | 234 | 164 | 917b99bc70cb2d54 | 11f7cfa38241b730 | 55873fecc61a79e8 | yes |
| dos/NGO21AX1.SVF | 3 | 504 | 264 | 8484b9328250fd31 | 0edec93cefa1d0e6 | 55873fecc61a79e8 | yes |
| dos/NGO21AX2.SVF | 4 | 660 | 280 | 11e4093a6d970d29 | 7a5276746434856a | 55873fecc61a79e8 | yes |
| dos/NGOTB14.SVF | 1216 | 82724 | 80076 | 700fb29e4ed02437 | 0b2f5b04f7302a3d | 245430dfa46ae80e | yes |
| dos/NGOTB15.SVF | 2446 | 185932 | 183244 | d9e06224334a7c4b | 2ce6189ac347e112 | 7e441e63ac8f26f3 | yes |
| dos/NGOTB15A.SVF | 942 | 71628 | 68256 | 6a6f044e5dbacd70 | 6efe209a8ec3a414 | 6d95fe8c310b1087 | yes |
| dos/NGOTB15B.SVF | 1123 | 85384 | 81924 | 37fc59ba3d9e6a0f | 9240ded16c63bb41 | 0ed14ff37cdd08b9 | yes |
| dos/NGOTB15C.SVF | 781 | 59392 | 56000 | d2b766cd19085d58 | df854522c8c0b5ab | dac966c862d6f79d | yes |
| dos/NGOTB16.SVF | 2880 | 218916 | 219480 | 736a485931ca0303 | fb54ab750d6c0b18 | 41f2d1fdbcaa0e65 | yes |
| dos/NGOTB16B.SVF | 2446 | 249528 | 196468 | ecd0925d8f3d726f | cb2075dc348f159b | 8eaad6acd8eca3e6 | yes |
| dos/NGOTB16D.SVF | 781 | 79698 | 60288 | 63e357fe5a788a99 | 46bf4bc8423dc9f1 | 916ed09d7ea1725d | yes |
| dos/NGOTB16E.SVF | 1123 | 114582 | 88100 | d895614045933314 | 6536ece548eaa3ee | a2c02ae8184c3bc4 | yes |
| dos/NGOTB17.SVF | 2446 | 161472 | 125692 | 8a49110c4d492963 | c954c780348f226d | 1c01e1fa1eab16b0 | yes |
| dos/NGOTB17A.SVF | 2446 | 322908 | 208420 | 06ed203dd0907f26 | 28c22f90ca4197ba | 15883de09d2381c2 | yes |
| dos/NGOTB19.SVF | 2446 | 322908 | 259252 | 58d117290c8451e3 | 8250bde5114454f9 | 84404f0c3f5f3f5a | yes |
| dos/NGOTB21.SVF | 2446 | 352260 | 290688 | 5a4da85326e6b28d | 72a1b2ae4c61f1e8 | 58143e4b913953e6 | yes |
| dos/NGOTB21A.SVF | 2446 | 381612 | 290688 | ec97092c60b7ec13 | 26f103510c7a00ad | 58143e4b913953e6 | yes |
| dos/NGOTB22.SVF | 1216 | 175140 | 160504 | 3d0d23e3da65fc5a | aae0e2b1120fcd78 | 9518f93c3a82f2d6 | yes |
| dos/NSQRB36.SVF | 1166 | 235589 | 127776 | d02cd37c3bf393e9 | ce9ad674a9e19a91 | 0a6b5c6c86a59406 | yes |
| dos/NSQRB36A.SVF | 1166 | 403493 | 162124 | d6049652304d3031 | 06c7e387f3029c98 | 211f0b3a548f6971 | yes |
| dos/NSQRR16A.SVF | 1167 | 100409 | 67208 | ad01cc4bb9e519cd | 0f151227af7731f8 | dd2edcce42cd24f1 | yes |
| dos/NSQRR36.SVF | 1163 | 235013 | 121440 | 6f7f40fb7e4bde80 | 17b7bf86778bd47b | 0156a32c0d48c5c6 | yes |
| dos/NSQRR36A.SVF | 1163 | 402485 | 156760 | b7501dee36445125 | 918b72c3f99622ca | f91333b02907a062 | yes |
| dos/PAPER16A.SVF | 1234 | 105501 | 69956 | b1a81ddf5d2bc915 | 1430f797c4b0372f | 4f393a079fdf827c | yes |
| dos/PAPER18A.SVF | 1215 | 135647 | 75172 | 4fc7633d73c45333 | cb43972e980a2dfa | e7ee073a01db8d1d | yes |
| dos/PAPLB16A.SVF | 1237 | 105729 | 71172 | 3fe8a4bca1e41a9c | 6a2cf4e8b3ddbe0d | ad6f8dab039ce0c6 | yes |
| dos/PAPLB18A.SVF | 1222 | 136361 | 73704 | b5b8d22a1be65a0a | 5e9aa0bdc4bc5fe5 | cb477b8d5d5ab72e | yes |
| dos/PAPLB20A.SVF | 1227 | 149141 | 89336 | 0f53a61b66c221c7 | d679f89d945ccfc3 | 10985868f5789f57 | yes |
| dos/PAPLG16.SVF | 149 | 15234 | 7760 | 56f4be4145f3adaa | 653053e07948ecc6 | c0a49dec2c5fa226 | yes |
| dos/PAPLG18.SVF | 1103 | 124223 | 69408 | ab4571f9ddaa0f3d | cb43972e980a2dfa | 88fe39002c957b59 | yes |
| dos/SANGAM16.SVF | 441 | 20541 | 15872 | 94cae635683d1d49 | 2fca2a44e41e9c5e | 9cdd987f959fcde1 | yes |
| dos/SMYJO18.SVF | 2359 | 155730 | 150804 | 6adc2a48d10992fd | b658644532013992 | b1e520b409408aef | yes |
| dos/TBG24X2.SVF | 2 | 204 | 164 | 0f64b77b0f12d4fc | 690a76bb5a28768c | 55873fecc61a79e8 | yes |
| dos/TBGHC48.SVF | 440 | 133137 | 56860 | 5331ee8233b523a0 | 5b271aac71e4b6ef | 4fd2ac7a5426918a | yes |
| dos/TBGHN40.SVF | 2351 | 498448 | 479296 | 25aa87d980791904 | d1fd0ca19aaa18af | 9670301f415f3598 | yes |
| dos/TBGOB24.SVF | 441 | 38181 | 22660 | 71e4a7e08008f30b | 660e697c265be23d | eae169d6d4167081 | yes |
| dos/TBM24X2.SVF | 2 | 204 | 160 | 2cfaf0b383100e6f | 690a76bb5a28768c | 55873fecc61a79e8 | yes |
| dos/TBMY24.SVF | 441 | 38181 | 23088 | 1feb1c4a735299da | 42d30518803820b7 | 2a8b8b0f553e19b3 | yes |
| dos/TBTHG16.SVF | 440 | 20497 | 16408 | 741b5ef48b004e7f | 972028d453f94143 | 46451d1a37c3124f | yes |
| dos/WCOMM16.SVF | 440 | 20497 | 16384 | ba6d96f30b9ba1cd | a90b35b6742b3c97 | 86204d4513a0deab | yes |
| dos/YOUTH36.SVF | 2359 | 452964 | 350236 | 0b2bd71099a74696 | 97a91e906dc42d2d | 40d8f59249880dc2 | yes |
| games/lb1/DKBHG40.SVF | 2351 | 489044 | 481980 | 00bc905db45deb67 | 6f8da8b4afef4b40 | 401e8e27a560bcb3 | yes |
| iolo/AD248J.SVF | 439 | 20453 | 14952 | 6b2e45f5b9283a5a | c9240301b3787780 | 8953f8199bb4b44a | yes |
| iolo/DKBY8J.SVF | 439 | 20453 | 15544 | c92955dc15ea4d31 | ca190dfc3e8af585 | 8f071ededcb4db04 | yes |
| iolo/HANME8J.SVF | 439 | 20453 | 15548 | 0974115a7c110d76 | 13a5e7ee52caaaf6 | e174c7f23051ab44 | yes |
| iolo/HGKEY6J.SVF | 278 | 12921 | 9272 | ef65451243174e0a | 3c89600aa6530e9d | 5fe3cbbbc1fa61e9 | yes |
| iolo/HLINK6J.SVF | 278 | 12921 | 9288 | c48e33f1193d0787 | c7777f471571213e | 48559e16c14d0144 | yes |
| iolo/JOONG6J.SVF | 278 | 12921 | 9756 | ab12eab2fd869fe2 | 043216116f1845de | 94a3bf097917d031 | yes |
| iolo/MR1286J.SVF | 278 | 12921 | 9408 | 6dc290d19c829fe2 | bd27d8cd40d0a49f | 74a4af537b7746e9 | yes |
| iolo/PILGI8J.SVF | 439 | 20453 | 15732 | 0a4fe058e8156848 | b584697d38511489 | 3625ceef69d2f057 | yes |
| iolo/ROMAX6J.SVF | 278 | 12921 | 9436 | 005c35a66fb073a0 | c1713615781bf3d0 | 8970b08c60a4ff8f | yes |
| iolo/SAM8J.SVF | 439 | 20453 | 14500 | 9ffa93e887b87bc6 | a2b9e303153d1c11 | 56a72937991647c8 | yes |
| iolo/SAN8J.SVF | 439 | 20453 | 15784 | ff5b1e5f4ee7ff7a | ca7e77ee7e75dc91 | faad6eb8c8a2c75a | yes |
| iolo/SANS8J.SVF | 439 | 20453 | 15740 | 43371dc64652c466 | bade713bf26ef4b4 | f15acd59f941f38b | yes |
| iolo/SCRN96J.SVF | 278 | 12921 | 9064 | 49ab23cb54ffceed | 1d486d868949f9f8 | 1717d32328d616c8 | yes |
| iolo/SERIF8J.SVF | 439 | 20453 | 16020 | b6d3c7ce03ec1467 | 402278d4059c072f | 47ba67338a690af8 | yes |
| iolo/THIN8J.SVF | 439 | 20453 | 15392 | 99e3bc1a34aa1329 | 26f26ebbd715e505 | b675cc48234fd646 | yes |
| iolo/U4K8J.SVF | 439 | 20453 | 15712 | eb2eebcfda680a63 | ffb02d625fb09436 | 9c5bc34da9a88de7 | yes |
| iolo/WCOMM6J.SVF | 278 | 12921 | 9560 | 40d214c4d6255466 | 51bbc10e0375bc9f | 1c921e2ef976d0b7 | yes |
| iolo/WOORI6J.SVF | 278 | 12921 | 9360 | 59dd97acabf29252 | cacfd877ae7d1e05 | cdec1a2c18f2b6a2 | yes |
| jamo-extra/GOTHA16.SVF | 1320 | 69797 | 60992 | 0406624cca41f7ae | adb0cd3f5e3739f4 | 0753341a89fb156d | yes |
| jamo-extra/GOTHA16A.SVF | 1320 | 112037 | 73752 | 47877c4dd9d1a6cc | 6d4afd6d517b9941 | 43ec9ccbf1c7032c | yes |
| jamo-extra/GOTHA18.SVF | 1320 | 98837 | 64468 | d11749ed936876c7 | 2853ba401498502d | 00068b998a708fd0 | yes |
| jamo-extra/GOTHA18A.SVF | 1320 | 146357 | 78964 | 0b9a201f02bd008e | a7073daf64ce62d8 | 9b9c20c9dea9dbe2 | yes |
| jamo-extra/GOTHA20.SVF | 1320 | 106757 | 74788 | df5bee89171a9db6 | 36ebe2fbc87248ab | ab58f2fd34e0c5c5 | yes |
| jamo-extra/GOTHA20A.SVF | 1320 | 159557 | 90568 | ef985ca02f8eb474 | 9119e7b623b6540c | 44125a0bbadb9672 | yes |
| jamo-extra/GOTHA24.SVF | 1320 | 122597 | 86464 | c5a54f5860f2407a | 107c8ad1b884af0f | a01b34e957b43179 | yes |
| jamo-extra/GOTHA24A.SVF | 1320 | 217637 | 105836 | e5ca5e93bd496ff9 | c56b8bb0231c0b65 | 55a47d7d38a605da | yes |
| jamo-extra/GOTHB16.SVF | 1320 | 69797 | 64956 | 29e3fca1b71e67d0 | fefc4e8d7d6996ae | f90be32dcbd2587a | yes |
| jamo-extra/GOTHB16A.SVF | 1320 | 112037 | 76040 | 6097c9fcdab0ed04 | 8431598889668fab | 716dbcd75ace4c76 | yes |
| jamo-extra/GOTHB18.SVF | 1320 | 98837 | 71156 | 53743a438ef8fe02 | 1e525263d4e01d37 | b6ae1a7f1324ace4 | yes |
| jamo-extra/GOTHB20.SVF | 1320 | 106757 | 83276 | 8465cefe7746a3c4 | 200e6413efe49fd5 | 3708d2bab1e74cb1 | yes |
| jamo-extra/GOTHB20A.SVF | 1320 | 159557 | 95064 | 5cfb8bc3599b44f3 | 5fe2ff76d70d378b | 8244a5445423ae70 | yes |
| jamo-extra/GOTHB24.SVF | 1320 | 122597 | 96180 | 3a2a35c25275cfab | 6d460ed9467f2f60 | 4c64b6d3bfaa7435 | yes |
| jamo-extra/GOTHB24A.SVF | 1320 | 217637 | 113796 | 06b2008e574ef3b3 | 5ec1d2577a65075b | 586e48473cff45b8 | yes |
| jamo-extra/NDGPR16.SVF | 616 | 32791 | 26764 | 2c5c241bbdc37283 | f18875d8c685b976 | c70334665ec49155 | yes |
| jamo-extra/NDGPR32.SVF | 618 | 92169 | 45004 | 8b3e9a505f29f5b7 | 1b3a78c3ace43189 | 097bcdb405719bcc | yes |
| jamo-extra/NSQRB16.SVF | 1169 | 63153 | 56856 | 8b940dfb38c91c63 | 23eb2b939fe64c03 | 9ba3e3235cc76121 | yes |
| jamo-extra/NSQRB16A.SVF | 1169 | 100561 | 68088 | 79a4eb520d0b6918 | ec8250f2e60784a0 | 5baf3d9d9a674e9a | yes |
| jamo-extra/NSQRB18.SVF | 1167 | 88739 | 58148 | 435c728d3602d8f7 | 701d998e73b5fa13 | 5ca63849e0fe2cda | yes |
| jamo-extra/NSQRB18A.SVF | 1167 | 130751 | 71576 | d5437dcf2fe17bfd | d7a429cc77e9a1b4 | 696e6ae2e43c4ff5 | yes |
| jamo-extra/NSQRB20.SVF | 1180 | 96677 | 71608 | 5c1caaac8af9971e | 574ce4a12f5fe0e7 | 3a94949efd35cab3 | yes |
| jamo-extra/NSQRB20A.SVF | 1180 | 143877 | 84132 | 494a611bb1049b33 | db3e07ba28c4b2d8 | 44d291e1f4d838f2 | yes |
| jamo-extra/NSQRB24.SVF | 1151 | 108401 | 78772 | 711b7535fd40be14 | 7a7cce8d3bcc8cdb | ea1161c19ea17989 | yes |
| jamo-extra/NSQRB24A.SVF | 1151 | 191273 | 97656 | d7577283b5a561fd | f085c61842b86102 | 61c2076f1ae27326 | yes |
| jamo-extra/NSQRR16.SVF | 1167 | 63065 | 55540 | 6aedd93b1249577b | e816c7e9caac793f | 8718719f8d9e5864 | yes |
| jamo-extra/NSQRR18.SVF | 1182 | 89729 | 58628 | b4d4cc42f08815a2 | f7658b9126891f1f | 5c3735db4d025345 | yes |
| jamo-extra/NSQRR18A.SVF | 1182 | 132281 | 71368 | 5d49eb613d1a98aa | 37ee5b8efa2ad948 | 0b9a1051d1eac192 | yes |
| jamo-extra/NSQRR20.SVF | 1170 | 95957 | 69392 | 4c6023bfaed504ec | 8c2652eaedceb5bf | bf07105ff1d04044 | yes |
| jamo-extra/NSQRR20A.SVF | 1170 | 142757 | 81428 | 083db40394988668 | af3b5b4d8e28b90b | 6b6e1c2205253d14 | yes |
| jamo-extra/NSQRR24.SVF | 1179 | 110753 | 77972 | 50ba55c1532bfea9 | 176b72164897967b | 0d9dece1faa5b8be | yes |
| jamo-extra/NSQRR24A.SVF | 1179 | 195641 | 96472 | 122dfb8f92d0d39d | a3103f14cb0400b4 | e3715480bdc25633 | yes |
| jamo-extra/SGDAY16.SVF | 1029 | 51953 | 40264 | af3c896cc07fd5de | c3c818ded672ea7f | c91c77e9e0a559db | yes |
| jamo-extra/SGDAY16A.SVF | 1029 | 84881 | 48804 | 780992e575e2dbc7 | cd1d76e458845260 | 9244c2305b0e80d8 | yes |
| jamo-extra/SGDAY18.SVF | 1012 | 73277 | 41024 | ba71195e6ca37da1 | 0f78aef0718ea262 | 61adc18a86aeffa2 | yes |
| jamo-extra/SGDAY18A.SVF | 1012 | 109709 | 52208 | 22a8597069a4c357 | 188d0f40e0931cd3 | 18ad47593dac3d48 | yes |
| jamo-extra/SGDAY20.SVF | 927 | 73055 | 40988 | f8fbe7d79e92150c | a221eb7c76c4d76f | 9d0f3ec9b8b7dd60 | yes |
| jamo-extra/SGDAY20A.SVF | 927 | 110135 | 51892 | b68b3cb9895cd7f4 | 2a55947e985b5e7c | cdf6df990c2d5ebd | yes |
| jamo-extra/SGDAY24.SVF | 928 | 84413 | 47624 | b836a436c28db50c | 5a74d480205ce6b7 | 864d62ce57f309e3 | yes |
| jamo-extra/SGDAY24A.SVF | 928 | 151229 | 62428 | 0f37f65e7b04b089 | e39e3f143579fa03 | 055d7dc9ecc1b132 | yes |

total faces=153 identical=153 different=0 glyphs=159680 v2_bytes=19920435 v3_bytes=14200840 unmatched=0

The same identity over every face in the other profiles (run at Task 6 with the first three texts only; uncommitted per-face tables under c/build/v3/ident-*):

- profile mcu-strict: total faces=153 identical=153 different=0 glyphs=159680 v2_bytes=19920435 v3_bytes=13919772
- profile dos: total faces=153 identical=153 different=0 glyphs=159680 v2_bytes=19920435 v3_bytes=13825899
- profile full: total faces=153 identical=153 different=0 glyphs=159680 v2_bytes=19920435 v3_bytes=21249364

Bite test: the top bit of the first row byte of the record of U+0021 in dos/PAPLG16.SVF flipped in a copy of the proven
tree, the script pointed at the copy: exit 1, "DIFFERENT dos/PAPLG16.SVF: glyphs differ at 1 code points, first U+0021;
--stream glyphs differ; --stream=4:512 glyphs differ".
