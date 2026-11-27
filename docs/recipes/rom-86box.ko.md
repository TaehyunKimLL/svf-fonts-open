[English](rom-86box.md) | **한국어**

# 레시피: 한글 VGA 폰트 ROM (86Box)

86Box ROM 세트의 한글 VGA 카드 셋(Trigem, 가산 ET4000, ATI 28800): 128 x 128 격자로 읽는 512 KB KS C 5601 폰트 ROM과 VGA BIOS의 영문 폰트에서, 직접 또는 maker의 내장 레시피로 완성형 페이스와 자모 세트를 만든다.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. ROM은 독점 칩의 덤프라 따로 마련한다. 방법은 [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md)와 같고, `$OUT/ks.txt`도 거기서 쓴다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md), [MAME 세트의 한글 폰트 ROM](rom-mame.ko.md), [데스크톱 앱과 maker 경로](desktop-routes.ko.md).

<a id="한글-vga-폰트-rom-86box"></a>

## 한글 VGA 폰트 ROM (86Box)

원본: 86Box ROM 묶음(https://github.com/86Box/roms, 2026-11-14의 커밋 1ac40f2). 파일별로 내려받았고 url, 바이트, sha256을 파일
곁에 적었다. 그 트리에는 한글 VGA 카드가 셋 있고, 각각 32 KB VGA BIOS와 512 KB
KS C 5601 폰트 ROM이다: 삼보 트라이젬 한글 VGA(ET4000, `video/et4000/tgkorvga.bin`, `tg_ksc5601.rom`), 가산 ET4000(`et4000_kasan16.bin`,
`kasan_ksc5601.rom`), ATI 28800 한글(`video/ati28800/atikorvga.bin`, `ati_ksc5601.rom`). 그 밖의 한국 항목은 한글 폰트가 없는 기계 BIOS다
(삼성 Deskmaster 286, 현대 Super-16T, LG IBM, 트라이젬 286M / 486G). ROM은 독점 칩의 덤프다([86Box 한글 VGA ROM 메타데이터와 렌더링](../recipes.ko.md#ref-86box) 참고).

    python3 -I tools/binscan.py info tg_ksc5601.rom      # 524288 bytes; size = 16384 x 32 B: 16,384 slots
    python3 -I tools/binscan.py render tg_ksc5601.rom --offset $((0x1821*32)) --glyph 16x16 --order strips --count 4

32 바이트 슬롯 16,384개는 128 x 128 격자다. 에뮬레이터 자신의 소스(`src/video/vid_svga_render.c`)가 `((lead & 0x7F) << 7) | (trail &
0x7F)`로 색인하고, 왼쪽 8 픽셀은 바이트 `scanline`, 오른쪽은 `scanline + 16`으로 그린다. 16행짜리 8 픽셀 스트립 두 개다(`--order
strips`). 가(B0A1)는 슬롯 0x1821이며, 세 ROM 모두 렌더가 가 각 간 갇을 보인다(디자인은 셋이 다 다르다). 영문 폰트는 BIOS의 8x16 VGA
폰트다:

    python3 -I tools/binscan.py ascii tgkorvga.bin                   # offset 0x4a2d, edge 3 (Kasan 0x499a, ATI 0x4d59)
    python3 -I tools/rawcarve.py bdf tg_ksc5601.rom --glyph 16x16 --order strips --chars ks-hangul \
        --grid 0x80,0x80,128 --ascent 12 -o $OUT/tg-hangul.bdf
    python3 -I tools/rawcarve.py bdf tgkorvga.bin --offset 0x4a2d --glyph 8x16 --chars ascii --ascent 12 -o $OUT/tg-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/tg-hangul.bdf --ascii $OUT/tg-ascii.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/TGVGA16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/TGVGA16.SVF --mask-font none --check -o $OUT/TGVGA16J.SVF

두 BDF에 모두 `--ascent 12`를 주면 ROM의 셀이 그대로 유지된다(VGA 폰트의 대문자는 11행에서 끝난다). 결과(각 페이스 글리프 2,447개,
모든 줄이 `width=144 ascent=12 descent=4`):

| ROM | 완성형 | 잉크 | 8x4x4 자모 세트 | IoU (2,350 중 정확) | 잉크 |
|---|---|---:|---|---|---:|
| 트라이젬 (`tg_ksc5601.rom` + `tgkorvga.bin`) | `122,392 bytes` | 476 | `17,172 bytes` | 0.968 (1,576) | 476 |
| 가산 (`kasan_ksc5601.rom` + `et4000_kasan16.bin`) | `124,968 bytes` | 557 | `18,576 bytes` | 0.872 (290) | 566 |
| ATI (`ati_ksc5601.rom` + `atikorvga.bin`) | `123,188 bytes` | 517 | `17,596 bytes` | 0.919 (644) | 517 |

ROM에는 KS X 1001 표 전체가 있다. `--chars ks-nonhanja`는 기호와 자모를, `ks-all`은 한자까지 더한다(BDF를 그대로 두는 `mkfont.py`용.
`bdfface.py`는 음절과 ASCII만 남긴다). `rawcarve.py eng tgkorvga.bin --offset 0x4a2d`는 같은 영문 폰트를 원시 `--eng` 파일로 준다.

확인한 다른 ROM 묶음: openMSX 시스템 ROM 묶음(file-hunter의 RomDB, 파일 1,241개)에는 한글 폰트가 셋 있다. 대우 MSX2 SUB-ROM의
자모 세트 폰트, CPC-400S의 256 KB 완성형 폰트, 한국 MSX1 BIOS의 8x8 자모 셀이다. 한글 BASIC ROM(`cpc-300_hangul`, `dpc-200_hangul`)에는
드라이버만 있고 글리프는 없다([한국 MSX 폰트](rom-msx.ko.md#한국-msx-폰트-msx2와-msx1)). 88emuplayer ROM 묶음(`88emuplayer-roms.zip`)에는 Roland 음원 모듈 ROM(SC-55, SC-88, SC-8850, CM-300)만 있고 폰트는
없다. MAME 롬셋은 [MAME 세트의 한글 폰트 ROM](rom-mame.ko.md#mame-세트의-한글-폰트-rom)에 있다.

데스크톱 앱은 세 쌍을 크기와 SHA-256으로 알아본다(내장 레시피 `maker/recipes/86box-tgkorvga.json`, `86box-kasan16.json`,
`86box-atikorvga.json`: 이름, 크기, 해시, 오프셋만 있고 ROM의 바이트는 없다). 두 파일이 든 폴더를 고르면 글꼴 ROM이 한 행이 되어
페이스 `TGVGA16` / `KASAN16` / `ATIVGA16`(경로 `bdfface`)과 자모 세트 `TGVGA16J` / `KASAN16J` / `ATIVG16J`(`bdfface + from-svf fit`,
experimental)를 위의 명령으로 만든다. `SVF_MAKER_REAL_86BOX`가 내려받은 파일을 가리키게 하고 실행하면(`maker/test/test_recipe.py`)
표의 모든 페이스가 바이트 단위로 그 크기가 된다.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
