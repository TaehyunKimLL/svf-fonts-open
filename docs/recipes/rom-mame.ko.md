[English](rom-mame.md) | **한국어**

# 레시피: MAME 세트의 한글 폰트 ROM

MAME 세트 ROM 속의 한글 폰트: 반전된 ROM 네 개에 든 삼성 SPC-1500의 자모 세트(정확), Date Quiz Go Go, X Se Dae Quiz, Quiz King of Fighters(한국판)의 스프라이트 폰트, Live Quiz Show(규칙은 읽었고 만들지 않음), 그리고 폰트가 없거나 풀지 못한 세트.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. ROM은 독점 파일이라 따로 마련한다. 방법은 [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md)와 같고, `$OUT/ks.txt`도 거기서 쓴다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md), [한글 VGA 폰트 ROM (86Box)](rom-86box.ko.md), [데스크톱 앱과 maker 경로](desktop-routes.ko.md).

<a id="mame-세트의-한글-폰트-rom"></a>

## MAME 세트의 한글 폰트 ROM

한국 가정용 컴퓨터와 한국 아케이드 게임은 한글 폰트를 ROM 칩에 두며, MAME의 롬셋에 그 덤프가 있다. 24x24는 없다: 찾은 폰트는
16x16이고, 하나는 자모 조각 세트(삼성 SPC-1500), 나머지는 게임 스프라이트로 된 완성형 세트다. 도구: `rawcarve.py region`은 게임의
ROM 파일들을 MAME 드라이버가 올리는 영역으로 잇는다. `binscan.py` / `rawcarve.py`는 반전된 폰트(`--invert`)와 여러 비트 스프라이트
타일(`--gfx`, 드라이버 자신의 `gfx_layout` 숫자로, 펜 규칙 `--bg PEN` 또는 `--fg PENS`로 1 bpp로 줄인다)을 읽는다. `rawcarve.py ink`는
다른 도구가 읽는 1 bpp 글리프를 쓴다. `jamoset.py --layout spec`은 compose 명세에서 정확한 자모 세트를 만든다. `rawcarve.py eng
--width 16` / `jamoset.py --eng`는 16 너비 영문 셀을 받는다. [Claude와 함께 프로그램이나 데이터 파일 안의 폰트
찾기](programs-and-drivers.ko.md#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기)의 드라이버처럼 ROM은 읽기만 한다: 게임은 실행하지 않는다(에뮬레이터는
괜찮다. 아래 그리기 규칙은 MAME 소스와, 역어셈블한 게임의 68000 코드에서 읽었다)([MAME 기종 정보, ROM 로드, 타일 배치](../recipes.ko.md#ref-mame) 참고).

**원본과 라이선스.** archive.org의 MAME 0.289 롬셋(항목 `mame-roms-non-merged`, 세트마다 zip 하나, 예: `spc1500.zip`): 독점 ROM 칩의
덤프이다. 각 파일에 적용되는 조건에 따라 원본을 마련한다. 쓰기 전에 모든 파일을 드라이버와 대조하라: 그
`ROM_LOAD` 줄의 SHA1(MAME 소스 `src/mame/samsung/spc1500.cpp`, `dataeast/tumbleb.cpp`, `seibu/raiden2.cpp`, `snk/midas.cpp`,
`snk/neogeo.cpp`)이 `sha1sum FILE`과 같아야 한다. 아래에서 `$MAME`은 세트마다 `$MAME/<set>/<file>`로 푼 폴더다. 같은 폴더를
`MAME_ROMS`에 주면 `tools/test_tiles.py`의 실제 ROM 테스트가 켜진다(해시만). 드라이버의 `ROM_LOAD` 줄이 영역을 만드는 법을 말한다:

| 드라이버 줄 | `rawcarve.py region` |
|---|---|
| 연속한 오프셋에 여러 파일의 `ROM_LOAD` | `region A B C D` (차례로) |
| A는 0, B는 1에 `ROM_LOAD16_BYTE` (C, D는 다음 오프셋에) | `region A,B C,D` (`--unit 1`: 번갈아 한 바이트씩) |
| A는 0, B는 2에 `ROM_LOAD32_WORD`; A, B, C, D를 0, 2, 4, 6에 `ROM_LOAD64_WORD` | `region --unit 2 A,B` / `A,B,C,D` |
| `ROM_LOAD16_WORD_SWAP` (68000 프로그램) | `region --swap A` |

쉼표가 든 경로(`ROMs, Korean` 같은 폴더)는 `--group`으로 한 파일이 된다: `region --group A B --group C D`(`region A,B C,D`와 같은
영역. 데스크톱 앱은 늘 이 형식을 쓴다).

타일 배치는 드라이버의 `gfx_layout`(또는 `gfx_WxHxN_packed_lsb` / `_msb` 프리셋)이고, `--gfx`에 `planes=..;x=..;y=..;inc=N`으로
옮겨 적는다: `STEP8(...)`과 `RGN_FRAC(1,2)`까지 같은 숫자이며, 중괄호와 C 주석은 뺀다.

<a id="삼성-spc-1500-반전된-rom-네-개의-자모-세트정확"></a>

### 삼성 SPC-1500: 반전된 ROM 네 개의 자모 세트(정확)

원본: 세트 `spc1500`(삼성 SPC-1500, 1987), 파일 `ss150fnt.bin`(영문: 0에 8x8, 0x1000에 8x16), `ss151fnt.bin`, `ss152fnt.bin`,
`ss153fnt.bin`(초성, 중성, 종성 조각), 각 8,192 바이트. MAME은 이것들을 차례로 32 KB 영역 `font1`으로 올리고 `crtc_update_row`에서
음절을 그린다: 삼성 코드를 h1(초성, 1 = ㄱ), h2(조합형 중성 코드), h3(종성, 0 = 없음)로 나누고, 8 픽셀 스트립(왼쪽 바이트 n, 오른쪽
n + 16)으로 저장한 16x16 조각 셋을 AND한다:

    initial  0x2000 + h1 * 32 + (cho[h2] + (h3 != 0) - 1) * 0x400
    medial   0x4000 + h2 * 32 + (h3 != 0) * 0x400
    final    0x6000 + h3 * 32 + (jong[h2] - 1) * 0x400

AND한다는 것은 잉크가 0 비트라는 뜻이다: 모든 ROM이 반전되어 있다(`--invert`). `cho[]`(1, 3, 5)와 `jong[]`(1, 2)은 드라이버의 30칸
표 둘이다: 초성 8벌 가운데 6벌(세로, 가로, 겹모음 각각 종성 없을 때와 있을 때), 중성 2벌, 종성 2벌을 쓴다. 이 규칙이 `rawcarve.py`의
내장 compose 명세 `spc1500`이고, 자모 세트는 그것을 그대로 받는다(초성 부류 하나와 6/2/2 벌의 JSET이 정확히 표현하므로 아무것도
맞추지 않는다):

    python3 -I tools/rawcarve.py region $MAME/spc1500/ss150fnt.bin $MAME/spc1500/ss151fnt.bin \
        $MAME/spc1500/ss152fnt.bin $MAME/spc1500/ss153fnt.bin -o $OUT/spc1500-font.bin     # 32768 bytes
    python3 -I tools/rawcarve.py eng $OUT/spc1500-font.bin --offset 0x1000 --invert -o $OUT/spc1500-eng.bin
    python3 tools/jamoset.py --layout spec --spec spc1500 $OUT/spc1500-font.bin --eng $OUT/spc1500-eng.bin \
        --check -o $OUT/SPC1500J.SVF
    #   ... 210 pieces of 16x16 ... by the spec's rule (6/2/2 sets, 1x2 classes)
    #   check: all 11172 syllables identical to rawcarve.py compose
    python3 -I tools/rawcarve.py compose $OUT/spc1500-font.bin --spec spc1500 --ascent 14 -o $OUT/spc1500-hangul.bdf
    python3 -I tools/rawcarve.py bdf $OUT/spc1500-font.bin --offset 0x1000 --glyph 8x16 --chars ascii --invert \
        --ascent 14 -o $OUT/spc1500-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/spc1500-hangul.bdf --ascii $OUT/spc1500-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/SPC1500.SVF

검증함(2026-11-23): 자모 세트 `10,652 bytes`, 글리프 305개(조각 210, ASCII 95), `width=144 ascent=14 descent=2`, 잉크 470. 완성형
`122,636 bytes`, 글리프 2,447개, 같은 줄과 잉크. 자모 세트의 11,172 음절 하나하나가 MAME이 세 조각을 AND한 것과 같다
(`tools/test_tiles.py`가 드라이버의 식을 따로 읽는다. 종성 벌마다 슬롯 0이 비어 있어서 종성 없는 음절도 똑같이 그려진다). 완성형
페이스의 8x4x4 맞춤(`--layout 844 --from-svf`)은 IoU 0.987(16,468 바이트)에 그친다: 종성이 없을 때 SPC-1500은 초성 벌을 모음
모양 셋에서 고르는데, 8x4x4에는 다섯이 있다.

<a id="date-quiz-go-go-음절-2350자의-스프라이트-폰트"></a>

### Date Quiz Go Go: 음절 2,350자의 스프라이트 폰트

원본: 세트 `dquizgo`(SemiCom / AceVer, 1998, 한국), 스프라이트 ROM `uor1` .. `uor4`(각 524,288 바이트). 둘씩 `ROM_LOAD16_BYTE`로
올리고(uor1/uor2는 0, uor3/uor4는 0x100000) `dataeast/tumbleb.cpp`의 `tlayout`으로 그린다: 16x16, 평면 4개, 영역의 각 절반에 둘씩.
펜 0이 투명이므로 잉크 = 펜 != 0(기본 `--bg 0`): 네 평면의 OR. 폰트는 스프라이트 13347에 있는 음절 2,350자의 빽빽한 KS X 1001
표다. 영문 폰트(16 너비, 잉크는 9열까지)는 스프라이트 0의 공백부터다.

    python3 -I tools/rawcarve.py region $MAME/dquizgo/uor1,$MAME/dquizgo/uor2 \
        $MAME/dquizgo/uor3,$MAME/dquizgo/uor4 -o $OUT/dquizgo-spr.bin                          # 2,097,152 bytes
    python3 -I tools/rawcarve.py ink $OUT/dquizgo-spr.bin \
        --gfx 'planes=RGN_FRAC(1,2)+8,RGN_FRAC(1,2)+0,8,0;x=STEP8(16*8*2,1),STEP8(0,1);y=STEP16(0,8*2);inc=64*8' \
        -o $OUT/dquizgo-ink.bin                                                              # 16384 glyphs, 15684 inked
    python3 -I tools/rawcarve.py bdf $OUT/dquizgo-ink.bin --offset $((13347*32)) --glyph 16x16 --chars ks-hangul \
        --dense --ascent 14 -o $OUT/dquizgo-hangul.bdf
    python3 -I tools/rawcarve.py bdf $OUT/dquizgo-ink.bin --glyph 16x16 --chars ascii --first 0x20 --count 95 \
        --ascent 14 -o $OUT/dquizgo-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/dquizgo-hangul.bdf --ascii $OUT/dquizgo-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/DQUIZGO.SVF
    python3 -I tools/rawcarve.py eng $OUT/dquizgo-ink.bin --offset 0 --width 16 --first 0x20 -o $OUT/dquizgo-eng16.bin
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/DQUIZGO.SVF --mask-font none --eng $OUT/dquizgo-eng16.bin \
        --check -o $OUT/DQUIZGOJ.SVF

(`rawcarve.py bdf $OUT/dquizgo-spr.bin --gfx '...' --offset $((13347*64))`는 타일을 바로 읽어 같은 BDF를 쓴다.) 검증함: 완성형
`115,916 bytes`, 글리프 2,447개, `width=208 ascent=14 descent=2`(영문 셀은 16씩 나아간다), 잉크 573(200보다 넓다: 여기의 208 너비 줄은
모두 `line 220 24 0 16`). 자모 세트 `16,864 bytes`, 글리프 441개, IoU 1.000(2,350 중 2,347 정확: 이 폰트 자체가 8x4x4 조각으로 그린
것이며, 그 디자인은 알려진 DOS 폰트 어디에도 없다), `width=160`(16x16 `--eng`는 10씩 나아간다: 글자와 숫자의 잉크가 9열에서 끝나고 가장
왼쪽 것은 0열에서 시작한다), 잉크 573.

<a id="x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용"></a>

### X Se Dae Quiz: 스프라이트 속의 태백 GOTHIC16(대조용)

원본: 세트 `xsedae`(Dream Island, 1995), `obj-1.u0811`과 `obj-2.u082`(각 2 MB), `ROM_LOAD32_WORD`와 `gfx_16x16x4_packed_lsb`
(`seibu/raiden2.cpp`). 여기서는 바탕이 마지막 펜이다: 잉크 = 펜 != 15. 처음 스프라이트 360개가 원시 8x4x4 폰트이고, 영문 폰트(16
너비: 몇 글리프는 15열까지 간다)가 `!`부터 뒤따른다.

    python3 -I tools/rawcarve.py region --unit 2 $MAME/xsedae/obj-1.u0811,$MAME/xsedae/obj-2.u082 -o $OUT/xsedae-obj.bin
    python3 -I tools/rawcarve.py ink $OUT/xsedae-obj.bin --gfx 16x16x4_packed_lsb --bg 15 --count 600 -o $OUT/xsedae-ink.bin
    python3 -I tools/binscan.py sets $OUT/xsedae-ink.bin              # offsets 0x0, 0x2 tie: the font starts at 0
    python3 -I tools/rawcarve.py cut $OUT/xsedae-ink.bin --offset 0 --length 11520 -o $OUT/xsedae.fnt
    python3 -I tools/rawcarve.py eng $OUT/xsedae-ink.bin --offset $((360*32)) --width 16 --first 0x21 -o $OUT/xsedae-eng16.bin
    python3 tools/jamoset.py --layout 844 $OUT/xsedae.fnt --eng $OUT/xsedae-eng16.bin --check -o $OUT/XSEDAE16J.SVF

`xsedae.fnt`는 태백 3.5.1의 `GOTHIC16.FNT`([그 밖의 DOS 시대 한글 폰트](dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트)의 원본)와 바이트 단위로 같다. 게임이
더한 디자인은 없고, 타일 경로를 점검하는 데 쓴다. 검증함: `15,780 bytes`, 글리프 439개, `check: ... identical to johab844.py`,
`width=144 ascent=14 descent=2`(16x16 영문 폰트의 이동 폭은 8로 잰다), 잉크 617.

<a id="quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트"></a>

### Quiz King of Fighters(한국판): 외곽선 펜이 있는 음절 2,350자 폰트

원본: 세트 `quizkofk`(Saurus / Viccom, 1996, 네오지오), 스프라이트 ROM `vic-080-c1.c1` .. `vic-080-c4.c4`(각 2 MB), c1/c2와 c3/c4 쌍의
`ROM_LOAD16_BYTE`. 네오지오 스프라이트 타일은 16x16, 4 bpp, 128 바이트다: 왼쪽 8 픽셀은 바이트 0x40, 오른쪽 8은 0. 한 행은 4 바이트,
펜 비트 3, 2, 1, 0은 바이트 3, 1, 2, 0, 비트 x가 픽셀 x(MAME `snk/neogeo_spr.cpp`, `optimize_helper`). 한국판은 일본어 폰트의 배치(JIS
순서: 기호, 스프라이트 108에 숫자, 118에 A-Z, 144에 a-z, 가나, 그리스, 키릴)를 그대로 두고, 한자가 있던 스프라이트 512에 음절 2,350자의
빽빽한 KS X 1001 표를 넣었다. 글리프마다 펜 1을 펜 3 외곽선과 함께 그렸다: `--fg 1`은 외곽선 없는 몸통을 고른다.

    NEO='planes=24,8,16,0;x=STEP8(0x40*8+7,-1),STEP8(7,-1);y=STEP16(0,32);inc=1024'
    python3 -I tools/rawcarve.py region $MAME/quizkofk/vic-080-c1.c1,$MAME/quizkofk/vic-080-c2.c2 \
        $MAME/quizkofk/vic-080-c3.c3,$MAME/quizkofk/vic-080-c4.c4 -o $OUT/quizkofk-spr.bin   # 8,388,608 bytes
    python3 -I tools/rawcarve.py ink $OUT/quizkofk-spr.bin --gfx "$NEO" --fg 1 --count 4096 -o $OUT/quizkofk-ink.bin
    python3 -I tools/rawcarve.py bdf $OUT/quizkofk-ink.bin --offset $((512*32)) --glyph 16x16 --chars ks-hangul \
        --dense --ascent 14 -o $OUT/quizkofk-hangul.bdf
    python3 -I tools/rawcarve.py eng $OUT/quizkofk-ink.bin --offset $((108*32)) --width 16 --first 0x30 --count 10 -o $OUT/e1
    python3 -I tools/rawcarve.py eng $OUT/quizkofk-ink.bin --offset $((118*32)) --width 16 --first 0x41 --count 26 -o $OUT/e2
    python3 -I tools/rawcarve.py eng $OUT/quizkofk-ink.bin --offset $((144*32)) --width 16 --first 0x61 --count 26 -o $OUT/e3
    python3 -c "import sys; a=[open(f,'rb').read() for f in sys.argv[2:]]; open(sys.argv[1],'wb').write(bytes(x|y|z for x,y,z in zip(*a)))" \
        $OUT/quizkofk-eng16.bin $OUT/e1 $OUT/e2 $OUT/e3
    python3 -I tools/rawcarve.py bdf $OUT/quizkofk-eng16.bin --glyph 16x16 --chars ascii --ascent 14 -o $OUT/quizkofk-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/quizkofk-hangul.bdf --ascii $OUT/quizkofk-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/QUIZKOFK.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/QUIZKOFK.SVF --mask-font none --check -o $OUT/QUIZKOFKJ.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/QUIZKOFK.SVF --mask-font none --check -o $OUT/QUIZKOFKJA.SVF

영문 글자와 숫자는 16 픽셀 셀의 JIS 전각 글리프다. 문장 부호는 비워 둔다(JIS 기호 행은 순서가 다르다). 검증함(잉크는 `line 220 24 0 16`: 줄이 208 너비다): 완성형
`123,640 bytes`, 글리프 2,447개, `width=208 ascent=14 descent=2`, 잉크 477. 8x4x4 자모 세트 `19,620 bytes`, IoU 0.835(정확 271), 잉크
494. adaptive `62,084 bytes`, 32/13/12 벌, 12 x 12 부류, IoU 0.975(정확 1,522), 잉크 477. 이 폰트는 조각으로 그린 것이 아니다: 완성형
페이스를 쓰라.

<a id="live-quiz-show-규칙은-읽었고-조각은-맞지-않는다만들지-않음"></a>

### Live Quiz Show: 규칙은 읽었고 조각은 맞지 않는다(만들지 않음)

원본: 세트 `livequiz`(Andamiro, 1999), 프로그램 `flash.u1`(`ROM_LOAD16_WORD_SWAP`), 스프라이트 `flash.u15`, `u19`, `u16`, `u20`
(`ROM_LOAD64_WORD`, `snk/midas.cpp`의 `layout16x16x8`, 잉크 = 펜 != 0):

    python3 -I tools/rawcarve.py region --unit 2 $MAME/livequiz/flash.u15,$MAME/livequiz/flash.u19,$MAME/livequiz/flash.u16,$MAME/livequiz/flash.u20 \
        -o $OUT/livequiz-spr.bin
    python3 -I tools/rawcarve.py ink $OUT/livequiz-spr.bin \
        --gfx 'planes=56,48,40,32,24,16,8,0;x=16*64+7,16*64+6,16*64+5,16*64+4,16*64+3,16*64+2,16*64+1,16*64,7,6,5,4,3,2,1,0;y=STEP16(0,64);inc=16*128' \
        -o $OUT/livequiz-ink.bin
    python3 -I tools/rawcarve.py region --swap $MAME/livequiz/flash.u1 -o $OUT/livequiz-prg.bin

퀴즈 문장은 조합형이다. 그리기 루틴(0x1f06의 68000 코드. 같은 표를 쓰는 루틴이 0x2154와 0x22e4에 둘 더 있다)은 조합형 코드를 필드로 나누어 워드 표 넷으로
바꾸고(0x1dec의 초성: 조합형 코드 - 1, 그래서 0 = 없음, ㄱ = 1. 0x1e18의 중성: 0 = 없음, ㅏ = 1 .. ㅣ = 21. 0x1e58의 종성: 유니코드 T.
0x1e98의 모음별 종성 벌: 없음, ㅏ .. ㅣ에 대해 84, 0, 56, 0, 56, 28, 56, 28, 56, 84, 0, 56, 28, 84, 84, 28, 56, 28, 84, 84, 28, 28),
같은 자리에 스프라이트 둘을 그린다: 초성+중성("CV") 타일 `base + vowel * 20 + initial`(종성이 있으면 + 440)과 종성 타일 `base + 880 +
T + set`. 기호는 `base + 992`부터다. 그러니 폰트는 종성 없는 CV 타일 20개짜리 묶음 22개, 종성 있는 것도 같은 수, 28개짜리 종성 벌
넷이다. 스프라이트 ROM에는 스프라이트 4840부터 그런 폰트가 하나 있지만, 어떤 음절도 그리지 않는 슬롯을 뺀 채 채워져 있다: 종성 없는 CV
벌은 base 4840에서 규칙과 맞고(가 = 4861), 종성 있는 CV 벌은 한 타일 일찍(5279 + vowel * 20 + initial), 종성 벌은 두 타일 일찍
시작하며(첫 벌의 ㄱ이 5719), 온전한 종성 벌은 셋뿐(각 27 타일)이고 넷째에는 종성 8개만 있으며, 기호는 5832가 아니라 5806에서
시작한다. 이 배치로는 종성 없는 음절은 바르게 조합되지만, 코드의 모음-종성 벌 대응은 온전한 세 벌과 맞지 않고, ㅜ / ㅠ의 종성은
어느 벌에서나 CV 타일과 겹친다. 덤프의 스프라이트 플래시와 프로그램의 판이 다르거나, 찾지 못한 변환 단계가 있다. 종성 벌의 자리가
정해질 때까지 페이스는 만들지 않는다.

데스크톱 앱은 네 세트를 크기와 SHA-256으로(MAME `ROM_LOAD` 줄의 SHA1도) 알아본다. 내장 레시피는 `maker/recipes/mame-spc1500.json`,
`mame-dquizgo.json`, `mame-xsedae.json`, `mame-quizkofk.json`이다(이름, 크기, 해시, 오프셋, 드라이버의 배치만 있고 ROM의 바이트는
없다). 세트의 폴더를 고른다(풀어 둔 것: zip은 아직 읽지 않는다). 레시피가 이름 붙인 파일이 한 행이 되고, 세트의 다른 ROM은
unknown으로 남는다. 페이스와 경로: `SPC1500`(조합한 음절의 `bdfface`)과 `SPC1500J`(경로 `spec`, 정확), `DQUIZGO`와
`DQUIZGOJ`(`bdfface + from-svf fit`, 16폭 영문 포함), `XSEDA16J`(경로 `dos raw`: 잉크로 바꾼 스프라이트에서 자른 8x4x4 폰트, 위의
`XSEDAE16J`를 8자 안으로 줄인 이름), `QUIZKOFK`와 `QUIZKOFJ`(8x4x4 fit). 명령은 위와 같고, 타일에서 읽는 영문 폰트나 raw 세트
앞에는 `rawcarve.py ink --offset O --count N`이 온다(영역 전체를 잉크로 바꾸고 글리프 오프셋에서 자르는 것과 같은 글리프).
Quiz King of Fighters의 영문 세 구간은 `maker/srcprep.py or-files`로 OR한다(위의 `python3 -c` 줄). `SVF_MAKER_REAL_MAME`이
`$MAME`을 가리키게 하고 실행하면(`maker/test/test_recipe.py`) 모든 페이스가 위에 적힌 크기가 된다.

<a id="폰트가-없거나-풀지-못한-세트"></a>

### 폰트가 없거나 풀지 못한 세트

- `quizdaisk`(Quiz 사립탐정, 네오지오, 1995): 스프라이트(c1/c2, 위의 네오지오 배치, `--fg 1`)에 스프라이트 4097부터 KS X 1001 순서에
  빈틈이 있는 16x16 한글 세트가 있다(가 각 간 갇 갈 감 ..., 갉 갊 없음. 약 1,467 타일이 글리프이고 나머지는 그림이나 빈 칸): 게임 자신의
  글자 목록이며, 프로그램에서는 찾지 못했다(`123-p1.p1`에 KS 표가 없다). 픽스 레이어 `123-s1.s1`(8x8, `--gfx 'planes=0,1,2,3;x=132,128,196,192,4,0,68,64;y=STEP8(0,8);inc=256'`)에는
  그림으로 그린 낱말만 있다. `quizkofk`의 픽스 레이어에는 한글이 없다.
- `shangha3`(Shanghai III, `27c4000.ic44`): 16x16x4 타일로 그린 한국어 메시지 음절 약 90개. 메시지 통째이지 폰트가 아니다.
- `quizchqk`(Quiz Channel Question, 한국어): Dynax 블리터 데이터가 압축되어 있다. 12-24 px의 원시 1 bpp 폰트는 없다.
- `spc800`(`spc800han.rom`: 한글 BASIC 코드), `spc1000`, `fc100`, `cpc61`, `cpg120`(8x8 / 8x12 문자 ROM, SPC-1000에 한글 그림 셀 몇 개):
  한글 폰트 없음.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
