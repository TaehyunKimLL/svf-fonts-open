[English](programs-and-drivers.md) | **한국어**

# 레시피: 프로그램과 드라이버 안의 폰트

Claude 같은 도우미와 함께 프로그램이나 데이터 파일(DOS 드라이버나 TSR, 워드프로세서) 안의 폰트를 찾는다: `binscan.py`와 `rawcarve.py`, 도우미에게 줄 프롬프트, 그리고 두 실행 예(드라이버의 규칙으로 조합하는 잘린 조각의 NKP 허큘리스 TSR, 도깨비 드라이버).

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. 프로그램은 독점 파일이라 따로 마련한다. 같은 도구와 프롬프트로 폰트 ROM도 읽는다: [한글 VGA 폰트 ROM](rom-86box.ko.md), [한국 MSX 폰트](rom-msx.ko.md), [MAME 세트](rom-mame.ko.md).

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [DOS 시대 원시 폰트](dos-fonts.ko.md), [한글 VGA 폰트 ROM (86Box)](rom-86box.ko.md), [한국 MSX 폰트 (MSX2와 MSX1)](rom-msx.ko.md), [MAME 세트의 한글 폰트 ROM](rom-mame.ko.md), [도구 설명서](../tools.ko.md).

<a id="claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기"></a>

## Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기

DOS 한글 드라이버, 워드프로세서, 게임, 한글 VGA 카드의 폰트 ROM은 폰트를 프로그램(`.COM`, `.EXE`, TSR)이나 ROM 이미지 안에 날
바이트로 담는다. 헤더도 이름도 없고, 따로 된 파일이 없을 때도 많다. 두 도구가 그것을 찾아 잘라 내고, 그 사이의
판독(폰트가 어디서 시작하는지, 어떤 배치인지, 드라이버가 어떤 규칙으로 조합하는지)은 Claude 같은 어시스턴트가 한다.

- `tools/binscan.py`는 살펴본다: `info`(크기, 종류, 압축된 데이터를 드러내는 엔트로피 지도, 아래의 크기 시그니처), `runs`(글리프처럼
  보이는 창의 연속 구간), `sets`(원시 자모 조각 폰트의 빈 채움 슬롯이 맞아떨어지는 오프셋), `ascii`(8xH 영문 폰트), `render`(어느
  오프셋이든 텍스트나 PNG로, 행·스트립·열·바이트 열 순서로).
- `tools/rawcarve.py`는 잘라 낸다: `cut`(바이트 그대로: `jamoset.py`용 원시 8x4x4 폰트), `eng`(8xH 영문 폰트를 `--eng`가 읽는 4,096
  바이트 8x16 파일로), `bdf`(오프셋의 글리프를 유니코드 BDF로: ASCII, 또는 2,350 글리프 밀집 덤프나 코드 격자의 KS X 1001 음절),
  `compose`(자기 벌 규칙을 가진 자모 조각 폰트를, 작은 JSON 명세로 적은 규칙대로 음절로 조합해 유니코드 BDF로).

BDF는 `bdfface.py`를 거쳐 완성형 페이스가 되고 `jamoset.py --from-svf`를 거쳐 자모 세트가 된다. 잘라 낸 원시 8x4x4 폰트는 곧바로
`jamoset.py --layout 844`로 간다([그 밖의 DOS 시대 한글 폰트](dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트)). 두 도구는 바이트만 읽고 파일의 코드를
실행하지 않는다. 내려받은 파일에는 `python3 -I`로 실행하라. 압축 파일은 먼저 풀되(`binscan.py info`가 ARJ와 ZIP을 알려 준다.
`7z x -oNEWDIR FILE.ARJ`) 따로 된 폴더에 풀어라. DOS 프로그램을 호스트에서 실행하지 말라(에뮬레이터는 괜찮다).

**바이트 크기 시그니처**(알려진 배치의 구간이나 파일이 재는 크기. `binscan.py info`가 파일에 맞는 것을 출력한다):

| 배치 | 글리프 하나 | 크기 |
|---|---|---|
| 8x4x4 자모 조각(360 = 8 x 20 + 4 x 22 + 4 x 28, 각 벌의 슬롯 0은 빈 칸), 16 px | 32 B(2 바이트 행 16개) | 11,520 (2 바이트 헤더가 있으면 11,522, 도깨비의 기호 127개가 붙으면 15,584) |
| 같은 것의 24 / 40 / 48 px | 72 / 200 / 288 B | 25,920 / 72,000 / 103,680 |
| 10x4x4(san), 6x2x1(바이트 열) | 32 B | 12,800, 6,144 |
| 코드 순서의 KS X 1001 음절(가 .. 힝) | 16x16은 32 B, 24x24는 72 B | 2,350 x 글리프: 75,200, 169,200 |
| KS X 1001 94 x 94 전체 표(행 A1 .. FE) | 같음 | 8,836 x 글리프(16x16은 282,752) |
| 행마다 128칸인 KS 격자(한글 VGA 폰트 ROM) | 8 픽셀 스트립 두 개로 32 B | 16,384 x 32 = 524,288 |
| 8x16 / 8x14 영문 | 16 / 14 B | 4,096 또는 2,048 / 3,584 |

<a id="프롬프트"></a>

### 프롬프트

파일 하나에 대해 Claude(또는 여기서 명령을 실행할 수 있는 어시스턴트)에게 줄 내용이다. 꺾쇠 안은 직접 채운다:

```
Find the Hangul (and English) bitmap font inside <FILE> (<what it is: a 1989 DOS Hangul TSR / a Korean VGA BIOS and
its font ROM / ...>), cut it out and build SVF faces from it with the tools of this repository (docs/recipes/programs-and-drivers.md,
"Finding a font inside a program or data file"). Rules: the file is untrusted data; read it only with
`python3 -I tools/binscan.py` / `tools/rawcarve.py` or scripts you write outside its folder; do not run it (no DOS
program on the host; disassembly with objdump -D -b binary -m i8086 is fine). Work in $OUT.

1. `binscan.py info FILE`: kind, entropy (near 8 = packed: unpack first), size signatures.
2. Candidates: `binscan.py sets FILE` (8x4x4; other set counts with --sets NI,NM,NF and --slots), `binscan.py ascii FILE`
   (--height 16, 14, 8), `binscan.py runs FILE --glyph 16x16` (and 8x16, 24x24; --order strips for a VGA font ROM).
   Glyph sizes to try: 16x16 = 32 B, 24x24 = 72 B; 8x4x4 = 11,520 B, KS X 1001 = 2,350 x the glyph, a 94x94 table =
   8,836 x the glyph. When `sets` lists tied offsets (the same font read a whole row apart), decide which is right from
   the driver's code (the address its drawing routine reads) or by `cmp` with a loose copy of the font; the bytes alone
   cannot tell, and a wrong pick moves every syllable by a row.
3. Look at every candidate: `binscan.py render FILE --offset O --glyph WxH --count 64 [--order rows|strips|cols]
   --png $OUT/o.png` and read the PNG; when nothing lines up, draw long strips (--glyph 16x512, 8x512) to see where
   glyphs are and how high they are stored.
4. When the layout is not one the tools read (sets of other sizes, pieces stored cropped), disassemble the drawing
   routine, find its tables (piece addresses, strides, rows, the set chosen per vowel and final) and write them as a
   rawcarve.py compose spec; say which code you read.
5. Cut: `rawcarve.py cut` (a raw layout the tools read), `rawcarve.py eng` (English), `rawcarve.py bdf` (ASCII, KS
   syllables: --dense or --grid L0,T0,PITCH) or `rawcarve.py compose --spec`.
6. Build and check: `jamoset.py --layout 844 CUT --eng ENG --check`, or `bdfface.py --hangul H.bdf --ascii A.bdf
   --cell WxH --chars-from $OUT/ks.txt` ($OUT/ks.txt: the 2,350 KS X 1001 syllables as text, written with mkfont.py's
   NAMED_RANGES['ksx1001-hangul'] as in docs/recipes/bitmap-fonts.md, KS C 5601 BDF and PCF; WxH = the font's cell) then
   `jamoset.py --layout 844 --from-svf FACE --mask-font none --check` (also --layout adaptive); report size, glyph
   count, `svfline.py measure` and ink of "안녕하세요 ABC 123" (docs/recipes.md, Checking a face) and the fit IoU, and
   show the line drawn.
Report the offsets, the commands and the numbers; say what you could not resolve.
```

(프롬프트는 영어 문서와 같은 영문 그대로 둔다. 한국어로 옮겨 줘도 된다.) 아래의 모든 `bdfface.py` 줄이 읽는 음절 목록
`$OUT/ks.txt`는 한 번 만들어 둔다:

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))" $OUT/ks.txt

아래 세 예는 이 프롬프트로 작업했다(2026-11-22).
원본은 별도로 마련한 독점 프로그램과 ROM 덤프이다.

<a id="nkp-조각을-잘라-저장한-허큘리스-한글-tsr"></a>

### NKP: 조각을 잘라 저장한 허큘리스 한글 TSR

원본: NKP.COM V3.00 "(C) S.H.OH 06/01,89"(38,184 바이트, `NKP26.ARJ` 18,308 바이트 안)와 NKP3.COM(1989-07, 37,375 바이트,
`NKP3.ARJ` 안). 1989년의 허큘리스 한글 TSR이다(삼보 조합형 한글 묶음, 라이선스 표기 없음). ARJ에 `binscan.py info`를 하면 "ARJ archive",
모든 블록의 엔트로피가 7.9이다(압축됨: `7z l -slt`가 method 1을 보인다). 그래서 먼저 `7z x`로 푼다. 풀린 파일은 이미 디스크에 있던
사본과 바이트 단위로 같다. 그다음:

    python3 -I tools/binscan.py info NKP.COM --block 2048      # .COM (파일 오프셋 F는 F + 0x100에 적재), 0x2800-0x6000의 엔트로피 0.5-4.8
    python3 -I tools/binscan.py ascii NKP.COM                  # offset 0x39a0, edge 0
    python3 -I tools/binscan.py sets NKP.COM                   # none (--sets 8,2,1로도)
    python3 -I tools/binscan.py render NKP.COM --offset 0x3800 --glyph 16x512 --count 16 --cols 16 --scale 2 --png $OUT/strip.png

영문 폰트는 0x39a0에 있다(8x16 글리프 128개). 원시 8x4x4 폰트는 없다. 스트립을 보면 0x41a0부터 조각이 있는데, 너비는 16 픽셀이지만
높이는 5행에서 14행뿐이고 차례로 빽빽하게 붙어 있다(인벤토리의 "8/2/1 sets, row-cropped"). 규칙은 코드에 있다. `objdump -D -b binary -m i8086 --adjust-vma=0x100 NKP.COM`(.COM은 0x100에 적재되므로 코드가 가리키는 주소는
메모리 주소다: 파일 오프셋 = 주소 - 0x100). ASCII 루틴은 `mov ax,0x3aa0`(파일 0x39a0)을 읽고, 한글 루틴(0x1ea9)은 조합형 코드를
32 바이트 표 셋(초성 0x1bd6, 중성 0x1bf6, 종성 0x1c14: 5비트 코드를 드라이버 자신의 자모 번호로, 31 = 없음)으로 나누며, 초성 벌은
42 바이트 표 0x1c34(종성 없는 모음 21개, 그다음 있는 모음 21개. 값마다 조각 벌 레코드의 바이트 오프셋, 레코드 = 값 / 6)에서,
중성 조각은 0x1c5e의 84 바이트 (`u8` 조각, `u8` 레코드 바이트 오프셋) 쌍 표(종성 없음 21개, 있음 21개)에서, 종성은 레코드 96에서
고르고, 각 조각을 0x1b0c의 6 바이트 레코드 17개로 그린다: `u16` 벌 첫 조각의 주소, `u8` 간격, 조각을 OR하는 32 바이트 셀(행마다
2 바이트)의 `u8` 첫 바이트와 `u8` 끝 바이트, `u8` 플래그. 플래그 비트 0이 켜지면 16 픽셀 너비로 셀 바이트 첫 .. 끝 - 1이니, 행 첫 / 2부터
(끝 - 첫) / 2 = 간격 / 2 행이다. 꺼지면 행마다 한 바이트를 셀 바이트 하나 건너 하나씩(첫, 첫 + 2, ... 끝 미만. 첫이 홀수면 오른쪽
8 픽셀) 넣으니, 행 첫 // 2부터 8 픽셀 행 간격 = (끝 - 첫 + 1) / 2 개다. 그러니 NKP에는 초성 벌 8개(종성 없음: ㅏ류 모음, ㅗㅛㅡ,
ㅜㅠ, 겹모음, 종성 있을 때 같은 넷), 중성 벌 2개(종성 없음 / 있음, 각각 모음 모양에 따라 네 가지로 잘림), 종성 벌 1개가 있고,
모음은 자기 순서(ㅏㅑㅓㅕㅣㅐㅒㅔㅖㅗㅛㅡㅜㅠㅘㅚㅝㅟㅢㅙㅞ)로 번호를 매긴다. `tools/nkpspec.py`가 이 표들을 읽어(그것을 쓰는
명령어 바이트로 찾는다. `find`가 주소를 출력한다) compose 명세를 쓴다:

    python3 -I tools/nkpspec.py find NKP.COM                   # desc 0x1b0c, cho 0x1bd6, jung 0x1bf6, jong 0x1c14, iset 0x1c34, med 0x1c5e, ascii 0x3aa0
    python3 -I tools/nkpspec.py spec NKP.COM -o $OUT/NKP.json  # 17 piece sets; the English font at file 0x39a0
    python3 -I tools/rawcarve.py compose NKP.COM --spec $OUT/NKP.json --syllables all \
        --eng NKP.COM --eng-offset 0x39a0 --ascent 12 -o $OUT/nkp-all.bdf
    python3 tools/bdfface.py --hangul $OUT/nkp-all.bdf --ascii $OUT/nkp-all.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/NKP16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/NKP16.SVF --mask-font none --check -o $OUT/NKP16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/NKP16.SVF --mask-font none --check -o $OUT/NKP16JA.SVF

명세는 오프셋과 규칙뿐이다(첫 벌: `"d0": {"offset": 16800, "stride": 18, "x": 0, "y": 3, "width": 16, "height": 9}`, 오른쪽 절반
벌: `"d48": {..., "stride": 14, "x": 8, "y": 1, "width": 8, "height": 14}`). 오른쪽 절반 레코드에 (끝 - 첫) / 2 행을 주는 명세는
오류 없이 틀린 페이스를 그린다(121,680 바이트, 잉크 464). 숫자를 점검하라. 결과: 완성형 `122,276 bytes`, 글리프
2,447개(음절 2,350, ASCII, U+2026, U+25A1), `width=144 ascent=12 descent=4`, 잉크 467. 8x4x4 자모 세트 `16,452 bytes`, 글리프 441개,
조각 344개, 음절 2,350개에 대해 IoU 0.998(2,324개 정확), 0.2 s. adaptive 자모 세트 `28,204 bytes`, 벌 11/5/4와 12 x 12 클래스, IoU
1.000(2,350개 모두 정확), 2 s. 둘 다 잉크 467이고, `--check`는 11,172 음절을 모두 조합한다. 대신 조합한 11,172 음절 전부에 맞추면
(`--chars-from`에 그 전부를 준 573,076 바이트 완성형 페이스): 8x4x4 IoU 0.997(10,848개 정확), adaptive `28,164 bytes`, 모든 음절이
정확, 9 s. 8x4x4 벌 체계가 몇 음절을 놓치는 것은 NKP가 종성 있는 초성 벌을 모음 모양에 따라 넷 중에서 고르는데 8x4x4에는 셋뿐이기
때문이다.

NKP3.COM은 같은 드라이버의 다른 빌드다. `nkpspec.py find`가 표를 찾고(레코드 0x193e, 초성 0x1a08, 중성 0x1a28, 종성 0x1a46, 초성
벌 0x1a66, 중성 0x1a90, 영문 0x6070 = 파일 0x5f70. `binscan.py ascii`도 찾는다), 같은 명령(`--eng-offset 0x5f70`)으로 `122,344 bytes`, 잉크 494(명조 비슷한 페이스), 8x4x4
`16,432 bytes`, IoU 0.997(2,282개 정확), adaptive `26,688 bytes`, 벌 9/5/4, IoU 1.000을 얻는다.

<a id="도깨비-드라이버-안의-폰트"></a>

### 도깨비: 드라이버 안의 폰트

원본: 한글 도깨비 B 배포본(`dkbb.rar`. 드라이버 소스 DKBB.ASM과 DKBBG.FNT / DKBBM.FNT가 함께 있다, 독점)에 든 한글 도깨비 B 드라이버 DKBB.COM(22,035 바이트)과 DKBII.COM(20,355 바이트).
따로 된 DKBBG.FNT는 [그 밖의 DOS 시대 한글 폰트](dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트)에서 읽는다. 여기서는 드라이버 자체에서 폰트를 꺼낸다.

    python3 -I tools/binscan.py sets DKBB.COM
    #   offsets 0x5e, 0x60 tie (seam 0.66, 4 nearby reads pass): the same font read a whole row apart; ...
    python3 -I tools/binscan.py ascii DKBB.COM       # offset 0x4cce (19662), edge 0 (fewer than 256 glyphs left in the file)
    python3 -I tools/binscan.py sets DKBII.COM       # offsets 0x105c, 0x105e, 0x1060 tie (seam 0.67, ...)
    python3 -I tools/binscan.py ascii DKBII.COM      # offset 0x5f

`sets`는 둘 다에서 8x4x4 폰트를 찾지만, 폰트 앞의 바이트가 0이면 몇 행 어긋나게 읽어도 통과한다. 도구는 16비트 행이 한데 붙어 있는
읽기(x = 7 / 8의 "seam"을 가로지르는 획)를 남기고, 한 행씩 떨어진 읽기들을 순위 없이 함께 나열한다. 바이트만으로는 가를 수 없다.
바이트 밖에서 정하라: DKBB.COM은 드라이버 소스 DKBB.ASM이 `han1`을 0x60에 둔다(`cmp`로 DKBBG.FNT 15,584 바이트 전부가 거기 있다).
DKBII.COM은 0x1060의 11,520 바이트가 DKBBG.FNT와 71 바이트만 다르니(고친 페이스) 같은 배치의 따로 된 파일이 정해 준다(0x105c와
0x105e는 각각 3,372, 2,768 바이트가 다르다). 소스도 따로 된 사본도 없으면 디스어셈블리에서 그리기 루틴이 읽는 주소를 보라. 잘못 고르면
모든 음절이 한 행씩 밀린다.

    python3 -I tools/rawcarve.py cut DKBII.COM --offset 0x1060 --length 11520 -o $OUT/dkbii.fnt
    python3 -I tools/rawcarve.py eng DKBII.COM --offset 0x5f -o $OUT/dkbii-eng.raw
    python3 tools/jamoset.py --layout 844 $OUT/dkbii.fnt --eng $OUT/dkbii-eng.raw --symbols --check -o $OUT/DKBII16J.SVF
    python3 tools/johab844.py $OUT/dkbii.fnt svf/dos/NEODG16.SVF $OUT/DKBII16.SVF --eng $OUT/dkbii-eng.raw

DKBII: 자모 세트 `15,556 bytes`, 글리프 441개, 조각 344개, `check: composed 11172 syllables ... identical to johab844.py`,
`width=144 ascent=14 descent=2`, 잉크 501. `johab844.py`로 만든 완성형은 `133,576 bytes`, 글리프 2,905개, 잉크 501. DKBB(0x60에서 자르고
영문은 0x4cce: 파일이 끝나기 전 글리프 148개, 4,096 바이트로 채움): `15,556 bytes`, 잉크 501. 도깨비 5.1의 화면 드라이버(VDKB5.EXE,
MDKB5.EXE, EDKB5.EXE, VDKB24.EXE)에는 폰트가 없다. `sets`, `ascii`, `runs`가 아무것도 찾지 못하며, 이들은 DKB16.FNT / DKB24.FNT(524,288,
698,184 바이트, 셰어웨어 `DKB5.ZIP` 안. CP437 기호로 시작하는 행 우선 16x16, 여기서 풀지 못한 코드 순서)를 읽어 들인다.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
