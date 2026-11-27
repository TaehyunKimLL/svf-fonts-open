[English](rom-msx.md) | **한국어**

# 레시피: 한국 MSX 폰트 (MSX2와 MSX1)

한국 MSX 기종(대우, 금성)의 한글 폰트: SUB-ROM 속 MSX2 대우 자모 세트 폰트(정확), CPC-400S의 256 KB 완성형 폰트 ROM, 그리고 openMSX 수집으로 찾은, 기계처럼 배치한 MSX1 BIOS 자모 셀. 코딩 에이전트 프롬프트가 먼저, 손으로 하는 명령이 그 뒤에 온다.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. ROM은 독점 파일이라 따로 마련한다. MSX1 수집에는 openMSX가 필요하다. 방법은 [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md)와 같고, `$OUT/ks.txt`도 거기서 쓴다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md), [벌 수 정하기](sets.ko.md), [자모 세트](../jamo-sets.ko.md), [도구 설명서](../tools.ko.md).

<a id="한국-msx-폰트-msx2와-msx1"></a>

## 한국 MSX 폰트 (MSX2와 MSX1)

한국 MSX 컴퓨터(대우, 금성. 1984-1988)는 한글 폰트 세 가지를 ROM에 두고, 저마다 다른 규칙으로 그린다.

| 기종 | 폰트의 위치 | 종류 | 결과 |
|---|---|---|---|
| 대우 CPC-300, CPC-300E, CPC-330K, CPC-400S (MSX2) | SUB-ROM(`cpc-300_msx2sub.rom`)의 위쪽 16 KB. CPC-400S는 `CPC-400S.U44`의 앞 16 KB | 16x16 자모 조각: 초성 6벌 x 20, 중성 2벌 x 28, 종성 2벌 x 29 | 정확한 자모 세트, 11,172자 전부 |
| 대우 CPC-400, CPC-400S (MSX2) | I/O 포트 D8h/D9h 뒤의 256 KB 폰트 ROM `cpc-400s_hangulfont.rom` | 16x16 완성형, 기계 자신의 순서. 코드 -> 슬롯 표는 "Kanji control ROM"(`CPC-400S.U44`의 마지막 16 KB)에 | 드라이버가 그릴 수 있는 2,591자의 완성형 페이스 |
| 대우 DPC-100, DPC-180, DPC-200, 금성 FC-80U (MSX1) | BIOS 문자 표 0x1B49(`dpc-200_basic-bios1.rom`) | 8x8 자모 셀, 음절 하나 = 텍스트 2행 x 1열 또는 2열 | 완성형 페이스. 배치 규칙은 실행 중인 기계에서 읽었다 |

한글 BASIC ROM(`cpc-300_hangul.rom`, `dpc-200_hangul.rom`, `fc-80u_hangul.rom`)에는 드라이버(조합 코드와 MSX-TUTOR 프로그램)가 있고
글리프는 없다. 권장하는 길은 [코딩 에이전트로](#msx-코딩-에이전트로-권장)의 프롬프트로 코딩 에이전트에게 맡기는 것이고, 그 뒤의
명령은 손으로 하는 길이다. 아래 파일 이름은 openMSX 시스템 ROM의 이름이고, `$ROMS`는 그 파일들이 든 폴더다.

**출처와 라이선스.** 이 폰트들은 독점 ROM 칩의 덤프에 든 대우와 금성의 펌웨어 디자인이다. 연구용으로만 쓰며, `svf/`의 페이스는
이것으로 만들지 않는다. openMSX 시스템 ROM 묶음은 file-hunter의 내려받기 서버(폴더 `System ROMs/RomDB SystemROMs OpenMSX`)에 있다.
서버는 curl의 기본 User-Agent를 HTTP 405로 거부하고, 브라우저 User-Agent에 그 폴더를 Referer로 주면 받을 수 있다. openMSX의 기종
파일(`share/machines/Daewoo_CPC-300.xml`, `Daewoo_CPC-400S.xml`, `Daewoo_DPC-200.xml`, `Goldstar_FC-80U.xml`)에 ROM마다 파일 이름과
SHA1이 있으니, 쓰기 전에 `sha1sum`으로 확인한다.

| 파일 | 바이트 | SHA1 |
|---|---:|---|
| `cpc-300_msx2sub.rom` | 32,768 | `fb51c505adfbc174df94289fa894ef969f5357bc` |
| `cpc-300e_msx2sub.rom` | 32,768 | `09f7d788698a23aa7eec140237e907d4c37cbfe0` |
| `CPC-400S.U44` | 65,536 | `6b640c1d8cbeda6ca7d6facd16a206b62e059eee` |
| `cpc-400s_hangulfont.rom` | 262,144 | `22d5f4e522250dc5eb17e15b68f4a51bb752cba1` |
| `dpc-200_basic-bios1.rom` (= DPC-100, DPC-180, FC-80U BIOS) | 32,768 | `171b587bd5a947a13f3114120b6e7baca3b57d78` |

도구는 ROM을 읽기만 한다(`python3 -I`). 기계는 에뮬레이터(openMSX) 안에서만 돌린다([한국 MSX 기종과 openMSX](../recipes.ko.md#ref-msx) 참고).

<a id="msx-코딩-에이전트로-권장"></a>

### 코딩 에이전트로 (권장)

이 일은 대부분 읽기다: 헥스 덤프, 글리프 시트, Z80 코드, 에뮬레이터 화면. 이 저장소에서 명령을 실행할 수 있는 코딩 에이전트(Claude
Code 같은)에게 아래 세 프롬프트 가운데 하나로 맡긴다. 꺾쇠 안은 직접 채운다. 프롬프트 다음의 절들은 손으로 하는 길이다: 같은 단계를
직접 실행하는 명령과, 프롬프트가 다시 얻어야 할 결과가 있다. [프롬프트](programs-and-drivers.ko.md#프롬프트)처럼 각 프롬프트는 입력, 쓸 도구, 안전 규칙,
합격 수치, 출력을 적는다.

**(a) MSX ROM 묶음에서 폰트를 찾아 풀기** (대우 SUB-ROM 같은 자모 조각 폰트, 또는 CPC-400S 폰트 ROM 같은 완성형):

```
ROM 파일 <$ROMS/FILE ...>(openMSX 시스템 ROM. 기종 파일 <openMSX share/machines/MACHINE.xml>에 어느 파일이 어디에
놓이는지 있다)에서 MSX 기종 <MACHINE, 예: Daewoo CPC-300>의 한글 폰트를 찾고, 한글 드라이버가 음절을 어떻게 그리는지 풀어서,
이 저장소의 도구로 SVF 페이스를 만들어라(docs/recipes/rom-msx.ko.md, "한국 MSX 폰트"). 작업은 저장소 밖의 $OUT에서 한다.

안전: ROM은 신뢰할 수 없는 데이터다. `python3 -I`로만 읽는다(tools/binscan.py, tools/rawcarve.py, 또는 $OUT에 직접 쓴
스크립트를 -I로). ROM 코드를 호스트에서 실행하지 않는다(Z80 역어셈블은 괜찮다: z80dasm, 또는 직접 쓴 작은 역어셈블러).
ROM에서 얻은 것은 저장소에 넣지 않는다: ROM 바이트, 글리프 그림, BDF, SVF 모두. compose 명세에는 오프셋과 규칙만 있다.

1. 모든 파일을 기종 파일의 SHA1과 대조한다(`sha1sum`). 파일마다 `binscan.py info FILE --block 4096`: 폰트와 표는 프로그램 코드보다
   낮다(코드는 바이트당 약 7비트, 대우 자모 폰트 블록은 1.8-5.5, CPC-400S 폰트 ROM은 3-6.5).
2. 글리프를 찾는다: `binscan.py runs FILE --glyph 16x16`(8x16, 8x8도), `binscan.py ascii FILE`(--height 16과 8), 그리고 후보마다
   `binscan.py render FILE --offset O --glyph WxH --count 256 --png $OUT/o.png`. PNG를 읽는다. 자모 조각은 여러 자리의 낱자로
   보이고, 완성형은 온전한 음절로 보인다. 맞는 것이 없으면 긴 띠(--glyph 16x512)를 그린다.
3. 그것을 그리는 드라이버를 찾는다: 폰트 주소를 리틀 엔디언 워드로 검색하고(ROM 머리의 포인터 표, 예: SUB-ROM의 4014h), 폰트
   장치의 I/O 포트(OUT (D8h) / OUT (D9h))를 검색한다. 조각을 읽는 루틴을 역어셈블하고 그 표를 적는다: 조각 주소와 간격, 조합형
   코드를 나누는 방법, 모음과 받침마다 고르는 벌, 건너뛰는 칸. 완성형이면 문자 코드를 글리프 슬롯으로 바꾸는 표를 찾는다.
4. 자모 조각: 규칙을 rawcarve.py compose 명세($OUT/SPEC.json. 형식은 rawcarve.py의 docstring. "slots"는 번호가 저장된 칸을
   건너뛰는 벌의 번호를 다시 매긴다)로 쓰고, 오프셋은 `rawcarve.py cut`으로 잘라 낸 폰트 블록의 시작에서 잰다. 완성형:
   코드 -> 슬롯 목록을 `rawcarve.py bdf --chars map`용 "SLOT U+XXXX" 줄로 쓴다.
5. 만든다: `jamoset.py --layout spec --spec $OUT/SPEC.json BLOCK --eng ENG --check -o $OUT/<NAME>J.SVF`, 완성형 페이스는
   `rawcarve.py compose ... --syllables all` + `rawcarve.py bdf --chars ascii` + `bdfface.py`(또는 `rawcarve.py bdf --chars map`
   + `bdfface.py`).

합격(수치를 하나씩 보고한다):
- `jamoset.py --check`가 "all 11172 syllables identical to rawcarve.py compose"를 찍는다.
- 명세가 아니라 역어셈블에서 바로, 따로 된 스크립트로 드라이버 루틴을 한 번 더 구현해서 같은 픽셀을 얻는다: 11,172자 가운데
  다른 음절 0(완성형이면: 드라이버가 받는 모든 코드에서 슬롯 목록이 드라이버의 표와 같고, 목록의 글리프 가운데 빈 것이 없다).
- 기계도 같은 글리프를 그린다: 프롬프트 (c)처럼 에뮬레이터 화면에서 몇 음절을 확인한다.
출력: $OUT/SPEC.json(또는 슬롯 목록), SVF 페이스, 짧은 보고: 파일과 SHA1, 찾은 오프셋과 표(루틴 주소와 함께), 명령, 크기와
글리프 수, "안녕하세요 ABC 123"의 `svfline.py measure`와 잉크, 합격 수치, 풀지 못한 것.
```

**(b) 표로 남아 있지 않은 배치를 위한 에뮬레이터 방법** (한글 ROM이 코드로 BIOS 셀을 배치하는 한국 MSX1):

```
한국 MSX1 <MACHINE, 예: Daewoo_DPC-200>이 모아쓰기 모드에서 한글 음절을 어떻게 배치하는지 openMSX에서 기계를 돌려 알아내고,
그 뒤 BIOS 문자 표만으로 폰트를 만들어라(docs/recipes/rom-msx.ko.md, "한국 MSX 폰트", MSX1). 작업은 저장소 밖의 $OUT에서 한다.

안전: ROM은 신뢰할 수 없는 데이터다. 그 코드는 openMSX 안에서만 실행한다(화면 없이: `xvfb-run -a openmsx -machine MACHINE
-script $OUT/s.tcl`, 언제나 `timeout`과 함께). 호스트에서는 ROM 파일을 `python3 -I`로만 읽는다. ROM에서 얻은 것은 저장소에
넣지 않는다(ROM 바이트, 덤프, 스크린샷, BDF, SVF 모두).

대우 / 금성 계열 기종이면 `python3 -I tools/msx1_harvest.py MACHINE $OUT/h --emu EMU`(또는 `--openmsx BIN`)로 시작한다. 이것이
아래 1, 3, 4단계를 하므로 5단계로 넘어간다. 다른 기종이면 tools/msx1_harvest.py를 읽고, 저장 바이트(2단계)와 화면 배치를 $OUT에
쓴 자신의 스크립트에서 맞춘다.

1. Tcl 스크립트로 기계를 켠다. `set throttle off`이면 에뮬레이션 시간이 호스트가 허락하는 만큼 빨리 간다(입력과 덤프에 쓴다.
   프레임을 그리지 않으므로 `screenshot` 전에는 다시 켠다). 결과는 Tcl에서 파일로 쓴다: `puts` 출력은 셸에 오지 않는다.
   RAM의 디버그 이름은 "Main RAM"이다.
2. 입력한 음절이 어떻게 저장되는지 찾는다: `type "poke -851,0\r"`(모아쓰기), `10 rem `과 한글 모드의 두벌식 키를 친다(한/영 키는
   키 행렬 6행 비트 4: `keymatrixdown 6 0x10`, 이어서 `after time 0.3 { keymatrixup 6 0x10 }`. 키보드 검사 한 번보다 짧게 누르면
   놓친다). RAM을 덤프하고(`debug read_block "Main RAM" 0
   0x10000`) BASIC 줄을 읽는다(프로그램은 F676h의 워드가 가리키는 곳에서 시작한다).
3. BASIC 프로그램을 친다: RAM의 깃발을 기다리고, Tcl 프로시저가 C000h에 써 둔 음절(음절마다 길이 바이트와 자모 바이트)을 화면마다
   77자씩 LOCATE 자리에 PRINT하고(텍스트 창이 2열 안쪽에서 시작하므로 한 행에 4열짜리 칸 7개), 끝 깃발을 놓는다. 화면마다 SCREEN 1
   이름 표(`debug read_block VRAM 0x1800 768`)를, 한 번은 패턴 표(`debug read_block VRAM 0 2048`)를 덤프한다. 화면 146개가
   11,172자를 모두 덮는다(145 x 77 + 7. 마지막 묶음은 그 마지막 음절을 되풀이해 77자로 채운다. 아니면 프로그램이 앞 묶음의
   남은 바이트를 찍는다). 눈으로 확인할 `screenshot`을 하나 찍는다(throttle 켬).
4. $OUT/h.index(음절 순서, 한 줄에 16진 코드 하나), $OUT/h.names, $OUT/h.patterns를 쓰고 규칙을 이끌어 낸다: 음절을 모음 종류(세로,
   ㅗㅛㅜㅠㅡ, 겹모음)와 받침(없음, 셀 하나, 셀 둘)으로 모아서 자리마다 어떤 셀 코드가 오는지 읽는다.
5. `python3 -I tools/msxfont.py msx1-verify $OUT/h --bios BIOS`로 규칙을 확인한다. tools/msxfont.py의 layout()과 다르면 어디가 왜
   다른지 말한다(다른 기종은 다른 규칙을 쓸 수 있다). 설명되지 않은 데이터에 맞추려고 도구를 고치지 않는다.
6. 에뮬레이터 없이 만든다: `python3 -I tools/msxfont.py msx1 BIOS -o $OUT/msx1.bdf`, 그리고
   `python3 tools/mkfont.py $OUT/msx1.bdf $OUT/MSX1.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul`.

합격: "layout rule vs the machine: 11172 of 11172 syllables identical". VRAM 패턴 표가 BIOS 표와 256셀 가운데 255셀에서 같다
(0xFF는 커서). 같은 계열의 다른 기종 ROM이 있으면 그 기종에서도 같은 수치. 출력: $OUT의 Tcl 스크립트와 수집 파일, $OUT/MSX1.SVF,
짧은 보고: 2단계에서 찾은 저장 바이트, 표로 적은 규칙, verify 출력, 페이스의 크기와 글리프 수, "안녕하세요 ABC 123"의
`svfline.py measure`와 잉크, 걸린 시간, 겪은 함정.
```

**(c) 풀어 낸 폰트를 기계 화면과 대어 보기:**

```
<MACHINE>의 ROM에서 풀어 낸 페이스 <$OUT/FACE.SVF>를 openMSX에서 기계가 직접 그리는 것과 대어 보라(docs/recipes/rom-msx.ko.md, "한국 MSX
폰트", "정답으로서의 에뮬레이터"). 작업은 저장소 밖의 $OUT에서 한다.

안전: ROM 코드는 `xvfb-run`과 `timeout` 아래의 openMSX 안에서만 실행한다. 호스트에서는 파일을 `python3 -I`로만 읽는다. ROM,
화면, 덤프에서 얻은 것은 저장소에 넣지 않는다.

1. 기계를 켜고(스크린샷에는 throttle 켬. CPC-400S는 약 20초, 다른 기종은 약 12초) 알려진 글을 그리게 한다: 펌웨어가 스스로 보이는
   화면(CPC-300의 MSX-TUTOR), 또는 음절 PRINT를 `type`한다(대우 MSX2: 한글은 SCREEN 9, 문자열은 조합형 코드, `print
   chr$(&H88)+chr$(&H61)`은 가. Tcl에서 `$`는 `\$`, `&`는 `\&`로. MSX1: `poke -851,0` 뒤 모아쓰기). 규칙이 가르는 모든 벌을 쓰는
   음절을 20자 이상 고른다(모음 종류마다 받침 있고 없음, 겹받침, 초성 ㅍ/ㅎ).
2. 그려진 것을 정확히 읽는다: 텍스트 모드는 이름 표와 패턴 표(`debug read_block VRAM ...`), 비트맵 모드(SCREEN 5-8. 대우 SCREEN 9는
   SCREEN 6 위에 만든 것)는 글이 있는 곳의 VRAM 픽셀. `screenshot -raw FILE.png`는 날 MSX 화면을 320x240으로,
   `screenshot -raw -doublesize FILE.png`는 640x480으로 찍으며, 후자는 너비 512 모드(SCREEN 6, 7, 대우 SCREEN 9. CPC-300의
   MSX-TUTOR는 SCREEN 7)의 픽셀을 모두 지킨다. 그냥 `screenshot`은 크기가 바뀌고 걸러지므로 보는 데만 쓴다.
3. 같은 글을 페이스로 그리고(`svfline.py line`, 또는 jamoset.parse_svfn의 글리프 행) 기계가 쓴 자리에서 픽셀마다 비교한다.

합격: 음절마다 다른 픽셀 수, 모두 0. 아니면 차이를 보이고(두 비트맵) 페이스가 틀렸는지 비교가 틀렸는지(화면 위치, 확대,
화면 모드가 자르는 셀) 말한다. 출력: $OUT의 Tcl 스크립트, 덤프, 스크린샷, 그리고 음절과 다른 픽셀 수의 표가 든 짧은 보고.
```

### MSX2: 대우 자모 세트 폰트(정확)

여기서부터는 손으로 하는 길이다: 위 프롬프트가 실행하는 명령과 측정한 결과.

SUB-ROM 머리의 4014h, 4016h, 4018h, 401Ah에 포인터 워드 네 개가 있다(CPU 주소 = 파일 오프셋): 초성 조각 0x59DE, 중성 0x68DE,
종성 0x6FDE, 8x16 영문 폰트 0x771E(코드 0x10부터라서 코드 0은 0x761E. `binscan.py ascii`도 0x761e를 찾는다). 조각은 32바이트(16x16,
행 우선, MSB가 왼쪽)이고 음절은 세 조각의 OR이다. `cpc-300_hangul.rom`의 한글 BASIC 루틴 4DC4h가 조합형 코드로 벌을 고른다(M = 중성
코드).

| 음절 | 초성 벌 | 중성 벌 | 종성 벌 |
|---|---|---|---|
| 받침 없음, 세로 모음(ㅏ .. ㅣ) | 1 | 7 | - |
| 받침 없음, ㅗ ㅛ ㅜ ㅠ ㅡ | 2 | 7 | - |
| 받침 없음, ㅘ ㅙ ㅚ ㅝ ㅞ ㅟ ㅢ | 5 | 7 | - |
| 받침, 세로 모음 | 3 | 8 | ㅏ ㅑ ㅣ는 10, 그 밖은 9 |
| 받침, ㅗ ㅛ ㅜ ㅠ ㅡ | 4 | 8 | 9 |
| 받침, ㅘ ㅙ ㅚ ㅝ ㅞ ㅟ ㅢ | 6 | 8 | ㅘ ㅚ ㅟ ㅢ는 10, 그 밖은 9 |

조각 번호: 초성 (벌 - 1) x 20 + 코드 - 1(조합형 초성 2 .. 20), 중성 (벌 - 7) x 28 + M - 2, 종성 (벌 - 9) x 29 + 코드 - 1. 조합형
종성 코드는 18을 건너뛰므로 종성 벌은 받침 27개에 칸이 29개다. 폰트 블록 전체는 0x59DE .. 0x7E1E, 9,280바이트다: 조각 234개(7,488바이트, 0x771E까지), 그 뒤 8x16 영문 폰트(코드 0x10-0x7F, 1,792바이트).
이 규칙이 compose 명세 `tools/specs/msx2-daewoo.json`이다. 오프셋은 블록 시작에서 재고, 종성 벌은 쓰는 칸을 적어 두므로(`"slots"`)
명세 하나로 모든 기종의 블록을 읽는다.

    python3 -I tools/rawcarve.py cut $ROMS/cpc-300_msx2sub.rom --offset 0x59DE --length 9280 -o $OUT/cpc300-font.bin
    python3 -I tools/rawcarve.py cut $ROMS/CPC-400S.U44 --offset 0x19E8 --length 9280 -o $OUT/cpc400s-font.bin
    cmp $OUT/cpc300-font.bin $OUT/cpc400s-font.bin        # 같다(CPC-300E의 0x59DE도)
    python3 -I tools/rawcarve.py eng $ROMS/cpc-300_msx2sub.rom --offset 0x761E -o $OUT/cpc300-eng.bin
    python3 -I tools/jamoset.py --layout spec --spec tools/specs/msx2-daewoo.json $OUT/cpc300-font.bin \
        --eng $OUT/cpc300-eng.bin --check -o $OUT/CPC300J.SVF
    #   ... 10584 bytes, 210 pieces of 16x16 ... by the spec's rule (6/2/2 sets, 1x2 classes)
    #   check: all 11172 syllables identical to rawcarve.py compose
    python3 -I tools/rawcarve.py compose $OUT/cpc300-font.bin --spec tools/specs/msx2-daewoo.json --syllables all \
        --ascent 14 -o $OUT/cpc300-hangul.bdf
    python3 -I tools/rawcarve.py bdf $ROMS/cpc-300_msx2sub.rom --offset 0x761E --glyph 8x16 --chars ascii --ascent 14 \
        -o $OUT/cpc300-ascii.bdf
    python3 -I tools/bdfface.py --hangul $OUT/cpc300-hangul.bdf --ascii $OUT/cpc300-ascii.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/CPC300.SVF

CPC-400S에서는 같은 블록이 SUB-ROM 절반의 사본에서 10바이트 뒤에 있고(포인터 59E8h, 68E8h, 6FE8h, 7728h), 그 사본이 4000h에 놓이는
`CPC-400S.U44`의 앞 16 KB이므로 0x19E8이다. 결과(2026-11-27): 자모 세트 `10,584 bytes`, 글리프 305개(조각 210, ASCII 95), JSET
707바이트, `width=144 ascent=14 descent=2`, 잉크 333. 완성형 `125,012 bytes`, 글리프 2,447개, 같은 줄과 잉크. 명세로 조합한 11,172자는
루틴 4DC4h를 따로 구현한 것과 모두 같다(CPC-300과 CPC-400S ROM 모두).

### MSX2: CPC-400S 완성형 폰트

`cpc-400s_hangulfont.rom`은 262,144바이트, 32바이트 슬롯 8,192개(16x16, 행 우선)다. 드라이버는 슬롯의 아래 6비트를 포트 D8h에,
위 7비트를 D9h에 쓰고 D9h에서 32바이트를 읽는다(openMSX의 `MSXKanji` 장치, 종류 `hangul`). 슬롯 배치: 0-1408 KS X 1001 기호(슬롯 =
(행 - 1) x 94 + 열 - 1, 1-15행), 1410-2725 한글 목록 A(1,316자), 2726-4416 한자 1군, 4417-5693 한글 목록 B(1,275자), 그 뒤 한자 두 군.
음절이 기계 자신의 순서로 있으므로 드라이버의 표를 거쳐 읽는다. Kanji control ROM(`CPC-400S.U44`의 마지막 16 KB, 8000h에 놓임)의
루틴 8A96h는 조합형 코드를 받아 trail 바이트를 목록 A(lead 88h .. D3h별 시작 오프셋 97BFh, trail 바이트 98F3h)나 목록 B(9859h, 9E18h)에서
찾고, 슬롯 0581h + 순번(A) 또는 1141h + 순번(B)을 그린다. `tools/msxfont.py kfn-map`이 그 표를 슬롯 목록으로 읽고
`rawcarve.py bdf --chars map`이 글리프를 잘라 낸다.

    python3 -I tools/msxfont.py kfn-map $ROMS/CPC-400S.U44 -o $OUT/cpc400s-map.txt
    #   2591 syllables (2217 of the 2,350 KS X 1001), slots 1410..5692
    python3 -I tools/rawcarve.py bdf $ROMS/cpc-400s_hangulfont.rom --glyph 16x16 --chars map --map $OUT/cpc400s-map.txt \
        --ascent 14 -o $OUT/cpc400s-hangul.bdf
    python3 -I tools/rawcarve.py bdf $ROMS/CPC-400S.U44 --offset 0x3628 --glyph 8x16 --chars ascii --ascent 14 \
        -o $OUT/cpc400s-ascii.bdf
    python3 -c "import sys; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in range(0xAC00, 0xD7A4)))" $OUT/all.txt
    python3 -I tools/bdfface.py --hangul $OUT/cpc400s-hangul.bdf --ascii $OUT/cpc400s-ascii.bdf --cell 16x16 \
        --chars-from $OUT/all.txt -o $OUT/CPC400S.SVF

결과: `137,416 bytes`, 글리프 2,688개(음절 2,591, ASCII 95, U+2026, U+25A1), `width=144 ascent=14 descent=2`, 잉크 437.
`--chars-from $OUT/ks.txt`로는 음절 2,217자, `117,976 bytes`(KS 음절 2,350자 가운데 갊 걜 곌 등 133자가 ROM에 없다.
KS X 1001 밖의 음절은 목록에 든 것만 있으므로 뷁과 힣도 없다). 이 페이스의 8x4x4 맞춤
(`jamoset.py --layout 844 --from-svf`)은 IoU 0.794(`19,900 bytes`, 정확히 맞은 음절 83자)에 그친다. 완성형 디자인이 자모 조각으로
짜여 있지 않기 때문이다. 한자 군은 KS X 1001이 아닌 드라이버 자신의 코드(lead 바이트 D4h 이상)를 쓰며, 여기서는 뺀다.

### MSX1: BIOS의 자모 셀을 기계처럼 배치하기

한국 MSX1 BIOS는 표준 문자 표(0x1BBF) 대신 0x1B49에 자신의 표를 둔다: 8x8 셀 256개, 0x20-0x7E에 라틴 문자, 0x86-0x98에 초성 19개,
0x99-0xA6에 모음, 0xA7-0xFB에 "ㅗ ㅛ ㅜ ㅠ ㅡ 위의 초성" 셀 85개(마지막 10개는 0x02-0x0B로 이어진다), 0x0C-0x0E에 획 끝 조각.
모아쓰기 모드(`POKE -851,0`)에서 한글 ROM은 음절을 이 셀들의 텍스트 2행으로 찍는다. 너비는 겹받침이 없는 ㅗ ㅛ ㅜ ㅠ ㅡ 음절이면
1열, 그 밖은 2열이다. 어느 셀이 어디에 가는지는 표로 저장되어 있지 않아서, 실행 중인 기계에서 읽었다.

방법(openMSX 19.1, 기종 `Daewoo_DPC-200`, Xvfb에서 화면 없이)은 `tools/msx1_harvest.py`가 실행한다. `$EMU`는 설치하지 않고 푼
openMSX다(데비안 꾸러미를 `dpkg -x`로 `$EMU/root`에, 시스템 ROM은 `$EMU/userdata/share/systemroms`에). 설치된 openMSX라면 `--emu`
대신 `--openmsx $(which openmsx)`를 준다. `$HARVEST`는 저장소 밖의 폴더다.

    python3 -I tools/msx1_harvest.py Daewoo_DPC-200 $HARVEST/dpc200 --emu $EMU
    #   wrote .../dpc200.tcl and .../dpc200.index: 11172 syllables in 146 screens
    #   openMSX exit 0; screens dumped 146 of 146; screenshot .../dpc200.png
    python3 -I tools/msxfont.py msx1-verify $HARVEST/dpc200 --bios $ROMS/dpc-200_basic-bios1.rom
    #   layout rule vs the machine: 11172 of 11172 syllables identical
    #   VRAM pattern table vs the BIOS table: 255 of 256 cells identical (differ: 0xff)

수집에는 실제 시간 5초가 걸린다(2026-11-27). 셀 0xFF는 커서다. `Goldstar_FC-80U`도 같은 수치와 바이트까지 같은 `.names` 파일을
낸다. 스크립트가 하는 일을 단계별로 적으면 다음과 같다(Tcl은 `$HARVEST/dpc200.tcl`. `--script-only`는 에뮬레이터를 돌리지 않고 이것만
쓴다).

1. `timeout 600 xvfb-run -a openmsx -machine Daewoo_DPC-200 -script $HARVEST/dpc200.tcl`을 실행한다(600은 `--timeout`으로 바꾼다).
   스크립트는 `set throttle off`로 시작한다: 에뮬레이션 시간이 호스트가 허락하는 만큼 빨리 가고 프레임은 그리지 않는다. 스크린샷
   하나를 찍기 전에 throttle을 다시 켜고, `exit`로 끝난다.
2. 음절마다 넣을 바이트는 먼저 손으로 찾았다: BASIC `REM` 줄에 두벌식 키를 치고(한/영은 키 행렬 6행 비트 4: `keymatrixdown 6 0x10`,
   이어서 키보드 검사를 넘기도록 `after time 0.3 { keymatrixup 6 0x10 }`) 프로그램을 RAM에서 읽는다(`debug read_block "Main RAM" 0
   0x10000`, 프로그램은 F676h의 주소부터). 음절은 자모 바이트로 저장된다: 초성 0x86 + L, 모음 셀(ㅏ 99 ㅐ 9A ㅑ 9B ㅒ 9C ㅓ 9D ㅔ 9E
   ㅕ 9F ㅖ A0 ㅗ A1 ㅛ A2 ㅜ A3 ㅠ A4 ㅡ A5 ㅣ A6. 겹모음은 둘: ㅘ = A1 99, ㅢ = A5 A6), 받침은 그 자음의 셀(ㄳ = 86 8F). ROM은 찍을 때
   조합한다. 스크립트는 이 바이트를 바로 쓴다.
3. `poke -851,0`(모아쓰기)과 다음 프로그램을 치고 `run`한다: `10 defint a-z`, `20 if peek(&hbffe)=0 then 20`,
   `30 poke &hbffe,0:poke &hbfff,0:cls:a=&hc000`, `40 for k=0 to 76`, `50 locate (k mod 7)*4,(k\7)*2`,
   `60 n=peek(a):a=a+1`, `70 for j=1 to n:print chr$(peek(a));:a=a+1:next`, `80 print " ";`, `90 next`,
   `100 poke &hbfff,1`, `110 goto 20`. 화면마다 77자(한 행에 7자: 텍스트 창이 2열 안쪽에서 시작하므로 4열짜리 칸이 한 행에 8개가
   아니라 7개 들어간다).
4. 화면마다 77자(음절마다 길이 바이트와 자모 바이트)를 `debug write_block "Main RAM" 0xC000 ...`로 C000h에 쓰고, BFFEh를 1로
   놓고, 프로그램이 BFFFh를 1로 놓을 때까지 기다린 뒤, SCREEN 1 이름 표를 `.names`에 덧붙인다(`debug read_block VRAM 0x1800 768`).
   패턴 표는 한 번만 `.patterns`에(`debug read_block VRAM 0 2048`). 화면 146개가 11,172자를 덮는다(145 x 77 + 7. 마지막 화면은 그
   마지막 음절을 되풀이해 77자로 채운다. 아니면 프로그램이 남은 바이트를 찍는다). 결과는 파일로 쓴다: `puts` 출력은 셸에 오지 않는다.
5. 눈으로 확인: 마지막 화면을 `screenshot -raw -doublesize`로 `.png`에.
6. 규칙은 이름 표에서 이끌어 냈고(음절마다 셀 코드, 모음 종류와 받침별로 모아서), `msxfont.py msx1-verify`가 모든 음절에 대어
   본다(위).

규칙(L = 초성 셀 0x86 + L. v, h = 모음 셀. T1, T2 = 받침 셀. _ = 빈 셀 0xFC. M(L, h) = 합친 셀 0xA7 + 5L + h, ㅗ ㅛ ㅜ ㅠ ㅡ에 h = 0 .. 4,
ㅍ ㅎ은 0x02로 넘어간다. ext(v) = 획 끝 0C는 ㅏ ㅑ ㅣ, 0D는 ㅓ ㅕ, 0E는 ㅐ ㅒ ㅔ ㅖ):

| 모음 | 받침 없음 | 받침 |
|---|---|---|
| 세로 v | `[L v] / [_ ext(v)]` | `[L v] / [T1 T2 또는 _]` |
| ㅗ ㅛ ㅜ ㅠ ㅡ (h) | `[L] / [h]` | 셀 하나 `[M(L,h)] / [T1]`, 둘 `[M(L,h) _] / [T1 T2]` |
| 겹모음 h + v | `[L v] / [h ext(v)]` | `[M(L,h) v] / [T1 T2 또는 _]` |

규칙을 얻은 뒤에는 에뮬레이터가 필요 없다. `tools/msxfont.py msx1`이 BIOS 표만으로 폰트를 만들고, `mkfont.py`는 글리프마다 자신의
진행 폭(8 또는 16)을 지킨다.

    python3 -I tools/msxfont.py msx1 $ROMS/dpc-200_basic-bios1.rom -o $OUT/msx1.bdf
    #   11172 syllables (1615 8x16, 9557 16x16) + 95 ASCII (8x8 at row 8), ascent 16
    python3 tools/mkfont.py $OUT/msx1.bdf $OUT/MSX1.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

결과: `106,504 bytes`, 글리프 2,445개, `width=136 ascent=16 descent=0`, 잉크 238. ASCII는 화면이 그리는 대로 16행 한글 옆 기준선에 놓인
8x8 셀이다(`--ascii-top 8`). `bdfface.py`는 음절마다 16픽셀씩 나아가므로 여기서는 `mkfont.py`를 쓴다. DPC-100, DPC-180, FC-80U의 BIOS
ROM은 DPC-200의 것과 바이트까지 같다.

### TrueType 파일

페이스마다 TrueType 비트맵 폰트로 이어 갈 수 있다([SVF 페이스를 다시 TTF 비트맵 폰트로](svf-and-ttf.ko.md#svf-페이스를-다시-ttf-비트맵-폰트로)).

    python3 tools/svf2ttf.py ttf $OUT/CPC300J.SVF $OUT/CPC300J.ttf --composite --licence none
    python3 tools/svf2ttf.py ttf $OUT/CPC400S.SVF $OUT/CPC400S.ttf --licence none
    python3 tools/svf2ttf.py ttf $OUT/MSX1.SVF $OUT/MSX1.ttf --licence none

결과: `671,640 bytes`(조각 210, 합성 음절 11,172, 글리프 11,318개), `623,164 bytes`(글리프 2,688개), `374,680 bytes`(글리프 2,445개).
모두 16 px 스트라이크가 있다. 이 폰트들에는 따라갈 라이선스 문서가 없으므로 `--licence none`이다.

### 정답으로서의 에뮬레이터

풀어 낸 ROM 폰트는 기계가 그리는 것과 대어 본다.

- **입력한 글의 스크린샷.** 입력하고 찍는 Tcl 스크립트(`set renderer SDL`, `after time 12 { type "print 1\r"; after time 3 { screenshot
  OUT.png; exit } }`. 시간은 에뮬레이션 초이고 throttle은 켜 둔다). CPC-300은 MSX-TUTOR로 부팅하고, 그 첫 화면("아이큐 교실은 컴퓨터를
  처음 배우는 분을 위하여 ...")을 SUB-ROM의 자모 폰트로 그린다. 같은 글을 `CPC300J.SVF`로 `svfline.py line`해 비교한다. CPC-400S는
  부팅에 약 20초가 걸리고 한글은 SCREEN 9에서 나온다. 문자열은 조합형 코드이므로 `type "screen 9\rprint
  chr\$(\&H88)+chr\$(\&H61)+chr\$(\&H88)+chr\$(\&H62)+chr\$(\&HB7)+chr\$(\&H65)\r"`(Tcl에서 `$`와 `&`는 이스케이프)가 256 KB 폰트로
  가각은을 찍는다. 스크린샷은 크기가 바뀐 화면이므로(512픽셀 줄에서 640 x 480으로) 모양은 눈으로 비교한다.
- **VRAM 덤프.** 텍스트 화면이라면 이름 표와 패턴 표가 셀을 정확히 준다(`debug read_block VRAM ...`, MSX1 수집처럼). 스크린샷과 달리
  픽셀까지 정확하다.
- **RAM 덤프.** `debug read_block "Main RAM" ...`이 입력한 키에 대해 드라이버가 저장한 것을 보여 준다(위 2단계).

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
