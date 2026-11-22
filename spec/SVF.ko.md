[English](SVF.md) | **한국어**

# SVF (SVFN) 비트맵 폰트 형식

2026-10-19에 ScummVM 브랜치 `jamo`의 40ffd1479a4, `graphics/hires_text/README.md`의 "Bitmap fonts
(G2)"부터 "Per-glyph dy"까지의 절을 복사해 왔으며, 이후 여기서 관리한다. 이 파일이 형식의 마스터 사본이고,
ScummVM README가 이 파일로 링크한다.
ScummVM이 페이스(face)를 불러오는 방식(맵의 `[load]`, `[preload]`)은 끝의 부록에 있다. 이식 가능한 C 렌더러의 API는
`c/include/svf.h`이며, 버전 3 파일만 읽는다.

SVFN은 **버전 3**이다. 버전 1과 2는 폐기되었다(아래 "폐기: 버전 1과 2" 참고). `tools/svf2to3.py`가 v2 페이스를
변환한다.

## 비트맵 폰트 (G2)

`HiResBitmapFont`는 "SVFN" 비트맵 폰트 형식을 읽는다. 1bpp 스텐실, 또는 8bpp나 2bpp coverage이며, 글리프별 메트릭은
선택 사항이다. coverage 형식은 도구가 미리 구워 둔 안티앨리어싱 모양을 담으므로, FreeType 없이 빌드해도 같은 글리프를
렌더링한다. 그래서 이 형식은 대체 수단이 아니라 기본 형식이다.

조회는 파일 자체의 코드 포인트 테이블을 통한 유니코드 코드 포인트로 한다(버전 1 파일은 글리프를 코드 페이지 순서로
두었으며, 그 형태는 폐기되었다).

CJK 블록 디코딩은 ScummVM의 공유 변환 테이블을 쓰므로 실행 시 `encoding.dat`에 접근할 수 있어야 한다. 없으면 모든
CJK 조회가 -1을 반환하고 엔진은 이미 "Support for CJK is disabled"라고 경고한다. 단일 바이트 폰트는 이에 의존하지
않는다.

이 폰트들은 더블 바이트 블록만 담는다. 한국어 폰트에서 ASCII는 -1로 해석되며 별도의 단일 바이트 폰트에 속한다. 헤더
오프셋은 모두 파일에 대해 검사하고, `load`는 호출자가 준 한도로 할당을 제한하며, 들어맞지 않는 메트릭 테이블은 글리프를
잃지 않고 버려진다.

실행 중인 엔진(MI2와 Indy3 한국어 타깃)에서 배포된 폰트에 대해 검증했다. 2350 글리프 한국어 세트에서 U+AC00은 글리프
0, U+D79D는 글리프 2349로 매핑되고, 라틴 세트에서 'A'는 글리프 65로 매핑되며, 엔진 자체의 레거시 `.fnt` 파일은 호출자가
대체 수단을 쓸 수 있도록 거부된다.

### 자모 세트 폰트 (플래그 비트 1)

모든 음절을 완성형으로 담은 페이스는 크다(DOTT의 1bpp 페이스는 합계 1,954 KB). DOS 한글 시스템은 위치별 자모 조각을
담고 음절을 둘 또는 셋의 OR로 그렸다. 헤더 플래그에 비트 1(0x2)이 있는 SVFN이 그런 폰트이다. 헤더가 **JSET** 블록(오프셋과
크기)을 지정하고, `createSvfnSource()`가 이를 위한 `JamoGlyphSource`를 반환하므로, 맵은 다른 페이스와 똑같이 파일을
지정한다(`ui=data:DOTTJ0.SVF`). 오래된 리더는 이 비트와 블록을 무시하고 일반 폰트로 본다.

- 조각은 코드 포인트 U+F0000 + 조각 번호(평면 15, 사용자 정의 영역)의 글리프이다. 번호는 폰트 고유이며 JSET 테이블이
  그것을 지명한다.
- 그 밖의 글리프(ASCII, 기호, 통째로 저장된 호환 자모)는 다른 SVFN과 같이 조회한다.
- 블록은 헤더 바이트 36(오프셋)과 40(크기)이 가리키는 곳에 있으며, 플래그가 없으면 둘 다 0이다. 오프셋은 테이블 단위의
  배수이고 바이트 48 이후에 있으며 크기와 함께 파일 안에 있다. 크기는 블록의 개수들이 주는 값과 같아야 한다. 검증에
  실패한 블록(개수, 클래스, 범위 밖의 세트, 맞지 않거나 플래그가 설정되었는데 0인 크기, 글리프 없는 조각 번호)은 페이스를
  일반 SVFN으로 불러오게 한다(C 렌더러의 `SVF_FACE_JSET_BAD`, 엔진은 파일 이름과 함께 한 번 경고한다). 파일 밖이거나 헤더
  안인 JSET 범위만 범위 오류이다.
- U+AC00..U+D7A3은 조각들로부터 픽셀별 최대 coverage로 합성한다(1bpp 스텐실의 OR이며 2bpp와 8bpp도 동작한다).
  compatPiece가 있는 U+3131..U+3163은 그 조각 하나이다. 합성된 글리프는 셀 하나(저장된 글리프 상자)를 채우고 JSET
  advance만큼, 그것이 0이면 셀 폭만큼 전진한다. (엔진은 음절을 "셀 두 개 폭"이라고 부르는데, 거기서 셀은 엔진 자체의
  행 버퍼 단위로 음절의 절반이지 저장된 글리프 상자가 아니다.)

JSET 블록은 리틀 엔디언이다. 블록 버전은 두 가지이며 블록 자체의 버전 워드가 어느 쪽인지 알려 준다. **버전 1이 표준
형식**이며 모든 도구가 기본으로 쓰는 것이고, 버전 2(아래)는 메모리가 제한된 대상을 위한 예외 전용 형식이다. 버전 1:

```
4  "JSET"
2  version (1)
1  LC  lead classes   (1..12; BIG 1..19)
1  TC  tail classes   (1..12; BIG 1..28)
1  NI  initial sets   (1..32; BIG 1..128)
1  NM  medial sets    (1..24; BIG 1..128)
1  NF  final sets     (1..16; BIG 1..64)
1  advance            syllable advance in px; 0 = the cell width
19 leadClass[19]      class of each initial (ㄱ..ㅎ), < LC
28 tailClass[28]      class of each tail, index 0 = no tail, < TC
LC*21*TC initSet      set of the initial for (leadClass, vowel, tailClass), < NI
LC*21*TC medSet       set of the medial
LC*21*TC finSet       set of the final (read only when tail != 0)
NI*19 u16 initPiece   piece number per (set, initial); 0xFFFF = blank
NM*21 u16 medPiece    per (set, vowel)
NF*27 u16 finPiece    per (set, tail 1..27)
51 u16 compatPiece    U+3131..U+3163 drawn from one piece; 0xFFFF = not by piece
```

세 세트 테이블은 `(leadClass * 21 + vowel) * TC + tailClass`로 인덱싱한다(vowel 0..20은 유니코드 순서, ㅏ..ㅣ).
조각 테이블은 `set * 19 + initial`, `set * 21 + vowel`, `set * 27 + tail - 1`로 인덱싱한다. 종성 세트는 tail 1..27 중
어느 하나가 속한 종성 클래스에 대해서만 검증하고 읽는다. DOS 세트 체계(8x4x4, 10x4x4, hanterm의 10x(3|4)x4, 6x2x1,
Dokkaebi 프린터 세트, Kyra의 자모 우선 순서, 그리고 초성 클래스 8개와 초성 세트 20개를 가진 Mac HangulTalk 1.0 'fbit'
폰트)는 모두 표현할 수 있다. `tools/korean/jamoset.py`가 이런 폰트를 쓰며, 윤곽 폰트로부터 2 bpp로도 쓰고(`--bpp 2`,
최댓값으로 합성한 안티앨리어싱 조각), 폰트에 맞춘 세트 체계로도 쓴다(`--layout adaptive`, 위 한도까지).

클래스 한도는 2026-10까지 8과 8이었고(가장 큰 블록 6641바이트), 이후 12와 12이다(11681바이트). 레이아웃이 바뀌지 않았으므로
버전은 여전히 1이다. 그 이전에 빌드한 엔진은 어느 종류든 클래스가 8개를 넘는 블록을 거부하므로(그러면 폰트는 일반
SVFN으로 불러와지고 음절은 다음 소스에서 온다), 클래스가 9..12개인 페이스는 현재 엔진이 필요하다. 그보다 오래된 페이스는
모두 그대로 불러와진다.

2026-10(v3)에 세트 한도가 24 / 16 / 16에서 32 / 24 / 16(초성 / 중성 / 종성)으로 올랐으며, 가장 큰 블록은 12321바이트이다
(12 x 12 클래스, 32 / 24 / 16 세트). adaptive 기본 예산은 32 / 24 / 12이다. 범위를 벗어난 개수는 여전히 잘못된 JSET이다
(페이스는 일반으로 불러와진다. `SVF_FACE_JSET_BAD`). 세트가 24 / 16 / 16까지인 페이스는 모두 계속 유효하다.

`SVF_JSET_BIG`은 버전 1과 2의 한도를 제자리에서 넓힌다(새 버전 워드 없음). 초성 19 x 종성 28 클래스와 초성 / 중성 / 종성
세트 128 / 128 / 64이며, 가장 큰 블록은 47,373바이트(버전 1)와 29,708바이트(버전 2, NA = 0; 모든 슬롯이 별칭이면
45,068)이다. 이것 없이 빌드한 리더는 12 x 12 / 32 / 24 / 16을 넘는 개수를 잘못된 JSET으로 취급한다. 작성기
(`--jset-big`)와 `jamoset.pack`은 요청이 없으면 표준 행을 넘는 테이블을 거부하고, `jamoset.unpack`은 둘 다 읽는다. 표준
한도 안의 출력은 어느 쪽이든 바이트가 같다.
버전 1 크기: `12 + 19 + 28 + 3 * LC * 21 * TC + 2 * (NI*19 + NM*21 + NF*27 + 51)` 바이트.

#### JSET 블록 버전 2 (압축형, 예외 전용)

버전 2는 같은 테이블을 더 적은 바이트로 담는다. 세 세트 테이블은 비트 패킹하고, 조각 번호는 암묵적이며(슬롯별 존재 비트,
세트별 base, 순서대로 매긴 조각) 슬롯 사이에서 공유되는 조각을 위한 별칭 이스케이프가 있고, 호환 테이블은 자모당
1바이트이다. 비트맵, 글리프 레코드, 셀, 합성 규칙, 한도(LC, TC <= 12; NI <= 32, NM <= 24, NF <= 16; BIG: 19, 28; 128,
128, 64, 버전 1과 같다)는 바꾸지 않으며, SVFN 헤더와 그 JSET 오프셋(36)과 크기(40) 필드는 버전 1과 같다. 블록 안의 어떤
것도 정렬되지 않으며, 비트는 리틀 엔디언 바이트 스트림에서 LSB부터 번호를 매긴다(비트 `b`는 바이트 `b >> 3`의 비트
`b & 7`).

```
off  size            field
0    4               "JSET"
4    u16             version = 2
6    1               LC  lead classes (1..12; BIG 1..19)
7    1               TC  tail classes (1..12; BIG 1..28)
8    1               NI  initial sets (1..32; BIG 1..128)
9    1               NM  medial sets  (1..24; BIG 1..128)
10   1               NF  final sets   (1..16; BIG 1..64)
11   1               advance (px; 0 = cell width)
12   u16             NA  alias entries (0..NI*19+NM*21+NF*27)
14   u16             reserved, 0
16   19              leadClass[19]  < LC
35   28              tailClass[28]  < TC, index 0 = no tail
63   S               set table: LC*21*TC cells of W bits each, S = ceil(LC*21*TC*W / 8)
63+S NI*RI           initial set rows
     NM*RM           medial set rows
     NF*RF           final set rows
     NA*2            alias table: u16 piece numbers
     51              compat[51]: one byte per U+3131..U+3163
```

**세트 테이블.** 셀 `c = (leadClass[lead]*21 + vowel)*TC + tailClass[tail]`이며 버전 1과 같다. `width(n)`은 n = 1이면
0이고, 아니면 `ceil(log2 n)`이다(2 -> 1, 32 -> 5). `WI = width(NI)`, `WM = width(NM)`, `WF = width(NF)`,
`W = WI + WM + WF`(0..14; BIG 0..20). 셀 `c`는 비트 `c*W .. c*W + W - 1`을 차지한다. 초성 세트는 하위 WI비트, 중성 세트는
그다음 WM비트, 종성 세트는 최상위 WF비트이다. 폭 0은 세트 0으로 읽는다. 리더는 각 필드를 바이트 오프셋(비트 오프셋
`>> 3`)에서 2바이트 읽기 한 번, 비트 오프셋 `& 7`만큼의 시프트, 마스크로 얻는다(필드는 최대 5비트 폭이다. BIG은 7:
비트 오프셋 7의 7비트 필드도 2바이트 읽기에 들어간다).

**세트 행.** 세트마다 한 행이며 테이블별로 크기가 고정이므로, 행 `s`는 `rows + s*R`에 있다. PB는 바이트 단위의 존재 폭이다.
초성(19슬롯)과 중성(21)은 3, 종성(27)은 4이다.

```
NA = 0:  u16 base | presence PB bytes                                  RI = RM = 5, RF = 6
NA > 0:  u16 base | u16 abase | presence PB bytes | alias PB bytes     RI = RM = 10, RF = 12
```

슬롯 `j`(초성 0..18, 중성 0..20, 종성 인덱스 1..27은 비트 `tail - 1`에 저장)는 존재 비트 `j`가 설정되어 있을 때 그려진다.
슬롯 개수 이상의 비트는 패딩이며 0이어야 한다. 별칭 비트는 존재 비트가 있는 곳에만 설정할 수 있다. 그려지는 슬롯의
조각은 별칭 비트가 설정되어 있으면(NA > 0일 때만) `alias[abase + popcount(aliasBits & below(j))]`, 아니면
`base + popcount((presenceBits & ~aliasBits) & below(j))`이며, `below(j)`는 비트 0..j-1의 마스크이다. 따라서 세트의 새
조각은 자모 순서로 `base, base+1, ...`이고, 별칭은 아무 조각이나 번호로 지명할 수 있다. 리더는 base가 누적적이거나
서로소라고 가정하지 않는다. 0xFFFF는 유효한 별칭 항목이 아니다(빈 슬롯은 존재 비트가 꺼진 것이다).

**호환.** U+3131 + k의 `compat[k]`: 0xFF는 조각으로 그리지 않음을 뜻한다. 그 외에는 비트 0-6이 세트 번호이고 비트 7이
테이블 전환이다(세트는 해당 테이블의 개수보다 작아야 한다. 표준 행에서는 최대 31, BIG에서 초성과 중성 테이블은 127이다.
비트 7 형식은 종성 세트를 지명하며 최대 `0x80 | 63 = 0xBF`이므로 0xFF는 세트를 지명하지 않는다). k의 자연스러운 테이블:
k >= 30은 중성 테이블의 vowel `k - 30`이고, 초성 인덱스가 있는 자음은 그 초성의 초성 테이블을, 겹받침 자음은 그 종성
인덱스의 종성 테이블을 쓴다. 초성 인덱스가 있는 자음에 비트 7이 있으면 대신 그 종성 인덱스의 종성 테이블을 고른다(모음,
겹받침, ㄸ ㅃ ㅉ 중 하나에 비트 7이 있으면 무효이다). 그려지는 조각은 그 세트의 해당 자모 슬롯이며 존재해야 한다.
리더의 상수 맵(k = 0..29, 초성 인덱스 또는 `T` + 종성 인덱스):

```
ㄱ0 ㄲ1 ㄳT3 ㄴ2 ㄵT5 ㄶT6 ㄷ3 ㄸ4 ㄹ5 ㄺT9 ㄻT10 ㄼT11 ㄽT12 ㄾT13 ㄿT14 ㅀT15 ㅁ6 ㅂ7 ㅃ8 ㅄT18 ㅅ9 ㅆ10 ㅇ11 ㅈ12 ㅉ13 ㅊ14 ㅋ15 ㅌ16 ㅍ17 ㅎ18
```

그리고 비트 7 형식에서 초성이 될 수 있는 자음의 종성 인덱스: ㄱ1 ㄲ2 ㄴ4 ㄷ7 ㄹ8 ㅁ16 ㅂ17 ㅅ19 ㅆ20 ㅇ21 ㅈ22
ㅊ23 ㅋ24 ㅌ25 ㅍ26 ㅎ27.

**크기.** `size = 63 + S + NI*RI + NM*RM + NF*RF + 2*NA + 51`. 가장 큰 유효한 블록(12 x 12 클래스, 32 / 24 / 16 세트, 모든
슬롯이 별칭, NA = 1,544)은 9,246바이트이다. BIG(19 x 28 클래스, 128 / 128 / 64 세트)에서는 NA = 0일 때 29,708바이트,
모든 슬롯이 별칭이면 45,068바이트이다. 예(NA = 0): 1 x 2 클래스의 6 / 2 / 1 세트는 181바이트(버전 1: 653), 2 x 2 클래스의
8 / 4 / 4 세트는 272(1,101), 8 x 8 클래스의 32 / 24 / 12 세트는 2,818(7,065), 12 x 12 클래스의 24 / 16 / 16 세트는 5,324에
별칭을 더한 값(11,681).

**검증** (아래의 모든 것은 페이스를 일반으로 불러오게 하며 `SVF_FACE_JSET_BAD`이고 오류는 아니다. 각 검사는 앞선 검사가 범위를
확정한 바이트만 읽는다): (1) 길이 >= 16, 매직, 버전 2, 다섯 개수가 한도 안, reserved == 0, NA <= NI*19 + NM*21 + NF*27;
(2) 길이 == 크기 공식; (3) `leadClass[i] < LC`, `tailClass[i] < TC`; (4) 모든 셀의 초성 세트 < NI, 중성 세트 < NM이고,
종성 세트 < NF는 tail 1..27 중 어느 하나가 속한 종성 클래스의 셀에서만; (5) 모든 행: 존재와 별칭의 패딩 비트가 0, 별칭
비트는 존재 비트의 부분집합, `abase + popcount(alias) <= NA`; (6) 그려지는 모든 슬롯(새 것이든 별칭이든)이 32비트 계산으로
0xFFFF보다 작고 글리프가 존재하는 조각 번호로 해석되며, 별칭 테이블 항목이 0xFFFF가 아닐 것(어느 슬롯도 쓰지 않는 별칭
항목은 글리프를 검사하지 않는다); (7) 모든 호환 바이트가 0xFF이거나 `c & 0x7F`가 해당 테이블의 개수보다 작고, 비트 7은
종성 형태가 있고 초성이 될 수 있는 자음(ㄸ ㅃ ㅉ 제외)에만 있으며, 그 세트의 해당 문자 슬롯이 존재할 것.

#### 버전 2를 쓸 때

버전 1이 표준이다. 모든 작성기와 `tools/svf2to3.py`는 요청이 없으면 이를 쓰고, maker는 업로드된 페이스의 버전을
유지하며(버전 2는 명시적 `--jset-version` 옵션을 통해서만), `svf/`는 버전 1로 남는다. 버전 2는 다음의 경우에만 쓴다.

- 플래시의 JSET 바이트나 RAM의 스트리밍 테이블이 문제가 되는, 메모리가 제한된 대상을 겨냥한 빌드나 팩;
- 큰 페이스: 12 x 12 클래스와 대부분의 8 x 8 클래스. `--jset-version auto`는 `JSET_V2_MIN_SAVING`(1,024바이트,
  `tools/jamoset.py`) 이상을 절약할 때만 버전 2를 쓴다. 출하된 자모 페이스 95개 중 58개가 그러하며 JSET 바이트는
  652,431에서 337,695로 줄어든다(95개 모두 버전 2이면 310,160);
- 리더가 컴파일되어 들어가는 경우: 이중 리더는 Cortex-M0+에서 약 +1.2 KB(+1,247 B, 버전 2 단독 +535 B,
  `c/cross/SIZES.md`)가 들며, AVR 빌드(와 v1 페이스를 내장하는 CH582 포트)는 버전 1만 읽는다;
- 버전 2 페이스에서 음절을 합성하는 것이 더 느리다는 점을 받아들일 것. Pico에서 측정하면(`syl_ga`, `syl_bwelk`,
  `screen32`) 변경 전 메인 브랜치의 버전 1 리더(BASE)보다 5-7 % 느렸으며, 현재 빌드의 버전 1 페이스보다가 아니다.

어느 빌드가 무엇을 읽는지(C 렌더러, `c/include/svf.h`): `SVF_JSET_V1`(기본 1)과 `SVF_JSET_V2`(기본 1, 0으로 두는 빌드는
제외: AVR은 기본으로, 그리고 v1 페이스를 내장하므로 v1로 고정된 CH582 포트)가 리더를 컴파일하며, 빌드가 읽지 않는 버전의
페이스는 일반으로 불러와진다(`SVF_FACE_JSET_UNREAD`. `SVF_FACE_JSET_BAD`는 잘못된 블록을 위해 남겨 둔다). 둘 중 적어도 하나는 1이어야
한다. `SVF_JSET_POP4`(기본 1, `SVF_SMALL`과 AVR에서는 0)는 버전 2 리더의 popcount에 비트 지우기 루프 대신 16항목 니블
테이블을 고른다. 픽셀은 바뀌지 않는다. `SVF_JMAP_LIST`(기본값은 `SVF_JMAP`의 값이므로 호스트, DOS, WASM, SDL 빌드에서는 켜지고
모든 MCU에서는 꺼진다. 명시적 `-DSVF_JMAP_LIST=0/1`이 우선하며 `SVF_JMAP` 없이 1이면 `#error`)는 `SVF_JMAP` 안에서 LIST 블록(플래그
0x08)의 리더를 컴파일한다. 이것이 없으면 LIST 블록은 `SVF_FACE_JMAP_UNREAD`이다("리더 상태" 참고). `SVF_JSET_TRUSTED`(기본 0)는
테이블 내용의 검증을 건너뛴다. **경고:** 개발자가 플래시에 내장하는 페이스 전용이다. 악의적이거나 손상된 JSET(개수, 클래스,
세트, 조각)은 이때 범위 밖을 읽는다. 헤더 길이, 매직, 버전, 개수가 주는 블록 크기와 영역 길이의 비교만 여전히 검사하므로
(버전 1 리더는 개수 한도도 검사하고, 버전 2 리더는 개수를 신뢰한다), 스트리밍 페이스는 자신의 영역보다 많이 불러오지
않는다. `SVF_JSET_V2`와 `SVF_JSET_TRUSTED`가 모두 켜진 16비트 빌드(AVR)에서는 손상된 개수의 크기 곱이 랩어라운드할 수 있다.
`SVF_JMAP`에서는 버전 3 블록이 `SVF_JSET_TRUSTED` 아래에서 헤더 규칙(R1-R4. LIST는 R1', L2, L3, R4)만 유지한다. 그 rank
테이블, 비트맵, 항목, 호환 항목, 모든 조각의 글리프(R5-R8. LIST는 L5, L6, L7)는 신뢰하며, 손상된 rank나 비트맵은 블록
훨씬 바깥(약 264 KB)의 항목 읽기를 일으킨다. 툴체인이 쓴 페이스 전용이다. 퍼즈 하니스는 이것을 켜고는 컴파일을 거부한다.
Python `jamoset.unpack`은 세 버전(1, 2, 버전 3의 JMAP)을 모두 읽는다. 모든 작성기는 `--jset-version 1|2|auto`를 받는다(기본
1, `docs/tools.md` 참고).

#### 버전 3: 매핑 테이블 (JMAP)

버전 3은 클래스 테이블과 세트 테이블을 음절에서 그 조각으로 가는 직접 맵으로 대체하며, 선택 규칙이 자모 클래스의 함수가
아닌 페이스(Mac HangulTalk 7.1.x 페이스나 예외 목록이 있는 폰트)를 위한 것이다. 모든 수는 리틀 엔디언이며 리더는 바이트
읽기만 쓴다.

| offset | size | field |
|---|---|---|
| 0 | 4 | `"JSET"` |
| 4 | u16 | version = 3 |
| 6 | u8 | flags: 0x01 4B (항목이 4바이트, 아니면 3), 0x02 SPARSE (비트맵과 NS개 항목, 아니면 dense이며 NS = 11,172), 0x04 FALLBACK (항목 뒤에 JSET 버전 1 또는 2 블록이 오고 영역 끝까지 이어진다), 0x08 LIST (공유 조각 풀 위의, 키로 정렬된 8바이트 항목 NS개. 0x01과 0x02를 배제한다). 비트 4-7은 0 |
| 7 | u8 | advance (px, 0 = 셀 폭) |
| 8 | u16 | NS, 항목 수. LIST: 1..255이므로 바이트 9는 0 |
| 10 | u16 | PI, 초성 조각, U+F0000 + 0 .. PI-1 (LIST: 0) |
| 12 | u16 | PM, 중성 조각, U+F0000 + PI .. PI+PM-1 (LIST: 0) |
| 14 | u16 | PF, 종성 조각, U+F0000 + PI+PM .. PI+PM+PF-1 (LIST: 0) |
| 16 | u16[51] | U+3131 + k의 호환 조각 번호: 0xFFFF는 빈 것, 아니면 PI+PM+PF보다 작음 (LIST: 글리프가 있는 풀의 조각) |
| 118 | u16[44] | SPARSE 전용: `rank[b]`, 비트맵에서 비트 `b * 256` 아래의 설정된 비트 수 |
| 206 | u8[1397] | SPARSE 전용: U+AC00..U+D7A3에 대한 존재 비트맵. 비트 `s`는 바이트 `s >> 3`의 비트 `s & 7`이며 비트 11,172..11,175는 0 |
| 1603 | u8 | SPARSE 전용: 패드, 0 |
| E | NS x 3, 4 또는 8 | 항목. E = 1,604 (SPARSE) 또는 118 (dense, LIST). LIST: 8바이트, `u16 key, u16 i, u16 m, u16 f`이며 key로 엄격히 증가하도록 정렬, `key = cp - 0xAC00`. 세 필드는 조각 번호(U+F0000 + n의 글리프)이며 0xFFFF는 빈 것. Dense와 SPARSE, 3B: `[i, m, f]`. 4B: `[b0, i_lo, m_lo, f_lo]`, `b0 = i_hi (bits 0-2) \| m_hi (bits 3-5) << 3 \| f_hi (bits 6-7) << 6`. dense와 SPARSE 항목에서 필드 0은 그 평면의 조각이 없다는 뜻이고, k는 그 평면의 k번째 조각을 뜻한다 (LIST 필드는 조각 번호이며 0은 조각 0) |
| F | rest | FALLBACK 전용: F = E + NS x (3 또는 4), LIST는 118 + 8 NS (최대 2,158). JSET 버전 1 또는 2 블록이며 길이는 영역에서 F를 뺀 것 |

한도: 3B: PI, PM, PF <= 255; 4B: PI, PM <= 2,047, PF <= 1,023; PI + PM + PF >= 1 (dense와 SPARSE. LIST는 PI = PM = PF = 0,
규칙 L2); SPARSE: 1 <= NS <= 11,172 (11,172도 유효하다. 예외 목록이 전부를 덮을 수 있다); dense: NS = 11,172; LIST:
1 <= NS <= 255; 영역은 최대 65,534바이트이다(JSET 크기는 열 때 0xFFFF로 잘리므로 정확히 65,535인 영역은 유효하지 않다).
크기: 폴백 없이 음절 2,350개를 담은 sparse 3B는 16 + 102 + 1,486 + 2,350 x 3 = 8,654, dense 3B는 33,634, dense 4B는
44,806, 항목 11,172개의 sparse 4B는 46,292, LIST는 118 + 8 NS로 최대 2,158 (NS 36: 406)에 폴백 블록을 더한다.

**조회.** 음절 인덱스 `s = cp - 0xAC00`. Dense: `idx = s`. SPARSE: 비트맵의 비트 `s`가 설정되어 있으면 음절이 있으며,
`idx = rank[s >> 8] + popcount(bitmap bytes (s >> 8) * 32 .. (s >> 3) - 1) + popcount(byte (s >> 3) &
((1 << (s & 7)) - 1))`이다. 필드 `i, m, f`를 가진 히트의 조각: 초성 `i - 1`, 중성 `PI + m - 1`, 종성
`PI + PM + f - 1`. 필드 0은 `SVF_PIECE_BLANK`(0xFFFF)이다. 조각 수는 항목이 정한다. 음절의 종성과 무관하게 `f != 0`이면 3개,
아니면 2개이다. 조각은 평면별로 번호를 매기며, 두 평면이 공유하는 글리프는 두 번 저장된다.

**LIST 조회.** 플래그 0x08이면 음절 인덱스 `s = cp - 0xAC00`(0..11,171. 그 외의 `s`는 미스)을 NS개 항목(키는 118 + 8 j,
엄격히 증가)에 대한 이진 탐색으로 찾는다. 히트의 필드는 평면 인덱스가 아니라 하나의 공유 풀의 조각 번호이다. 누가
저장하든 U+F0000 + n의 글리프(폴백 테이블의 조각, 호환 조각, 또는 LIST만을 위해 존재하는 글리프)이며 0xFFFF는 빈 것이다.
조각 0은 조각이지 "없음"이 아니다. 히트의 조각은 `f != 0xFFFF`이면 `[i, m, f]`, 아니면 `[i, m]`이다(조각 수는 항목이 정하며,
빈 `i`나 `m`은 합성할 때 건너뛴다). 통글리프(완성형 셀)는 `i`가 그 조각 번호이고 `m = f = 0xFFFF`인 항목이다. 이는 조각으로서
셀의 dy 0에 그려지고 JSET advance만큼 전진하며, 자체 메트릭 항목은 참조하지 않는다. 키 미스는 SPARSE 미스와 똑같이 폴백으로
간다. 폴백이 없으면 음절은 합성되지 않는다. 폴백의 조각 번호는 옮겨지지 않는다. 같은 풀의 조각을 지명하며, 항목과
조각을 공유하는 것이 요점이다.

**호환.** JMAP 자체의 호환 항목이 비어 있지 않으면 그것이 우선한다. 비어 있으면 폴백의 호환 항목으로(폴백이 있다면),
없으면 cmap 글리프로 간다. 둘 이상의 평면으로 된 Mac 호환 자모는 JMAP 호환이 비어 있는 U+3131 + k의 통글리프이다.

**폴백.** 미스(비트맵이 나열하지 않은 음절)는 폴백 JSET, 버전 1 또는 2에서만 답한다. 없으면 음절은 합성되지 않는다
(일반 페이스처럼 cmap 글리프 또는 없는 글리프). 폴백의 advance 바이트는 JMAP advance와 같아야 한다. 폴백은 JMAP 평면과 같은
U+F0000 + n 공간의 조각을 지명하므로, dense나 SPARSE 블록에서는 그것이 지명하는 모든 조각 번호(조각 목록과 호환)가 BLANK이거나 최소
PI + PM + PF여야 한다. 작성기는 폴백의 조각을 PI + PM + PF만큼 올리고 `jamoset.pack_fallback(tables,
version, base)`로 블록을 쓰는데, 이는 주어진 조각 번호를 유지한다(버전 2는 그려지는 슬롯이 행의 첫 조각에서부터 세어 올라가면
새 조각으로, 아니면 별칭으로 저장하므로 어떤 번호든 들어맞으며, 그 대가로 `pack`의 것보다 블록이 커진다). `jamoset.pack_jmap`은 겹침을
거부한다. 서로소 조건은 쓰기 쪽 규칙일 뿐이며 리더는 검사하지 않는다(R8에 따라 조각 번호는 무엇이든 글리프 테이블 안에 머문다). 따라서
리더는 이런 검사를 더하지 않는다. 이는 dense와 SPARSE에 적용된다. LIST는 PI + PM + PF = 0이라 아무것도 옮기지 않으며 폴백과 풀을
공유한다(겹침 거부 없음).

**검증.** 리더는 이 순서로 검사하며, 각 규칙은 앞선 규칙이 범위를 확정한 바이트만 읽는다.

- R1: 길이 >= 118, 매직 `JSET`, 버전 3, dense나 SPARSE 블록은 `flags & 0xF8 == 0`. LIST의 규칙은 R1'이다. 길이 >= 118, 매직,
  버전 3, `flags & 0xF0 == 0`, 그리고 `(flags & 0x08) && (flags & 0x03)`가 아닐 것(4B나 SPARSE와 함께인 LIST).
- R2 (dense와 SPARSE): PI, PM, PF가 3B 또는 4B 한도 안, PI + PM + PF >= 1.
- L2 (LIST, R2 대신): PI = PM = PF = 0. R2의 `PI + PM + PF >= 1`은 적용되지 않는다.
- R3: NS가 1..11,172 (SPARSE) 또는 == 11,172 (dense).
- L3 (LIST, R3 대신): NS가 1..255이고 바이트 9가 0이다(오프셋 8의 u16에 대한 한 번의 검사. `ns - 1u >= 255u`이면 블록은 실패한다).
- R4: 영역은 최대 65,534바이트이다(LIST는 F = 118 + 8 NS, 최대 2,158). FALLBACK이 없으면 길이는 정확히 F이고, 있으면 길이는 최소
  F + 12이며 폴백 헤더를 읽을 수 있어야 한다(매직, 버전 1 또는 2). 폴백의 advance 바이트(폴백 헤더의 바이트 11)가 JMAP
  advance(JMAP 헤더의 바이트 7)와 같아야 하며, 헤더를 읽을 수 있는 모든 빌드에서 그러하다. 그다음 빌드가 그 버전을 읽으면
  폴백이 올바르게 구성되어 있어야 한다. 따라서 advance 때문에 한 빌드에서는 잘못되고 다른 빌드에서는 쓸 수 있는 페이스는
  없다.
- R5: 모든 호환 항목이 0xFFFF이거나 PI + PM + PF보다 작다(dense와 SPARSE).
- L5 (LIST, R5 대신): 모든 호환 항목이 0xFFFF이거나 글리프가 존재하는 조각 번호이다.
- R6: SPARSE 전용: 패드 바이트가 0, 비트맵 비트 11,172..11,175가 0, b = 0..43에 대해 `rank[b]`가 `b * 256` 아래의 설정된
  비트 수와 같고, 총합이 NS와 같다.
- L6 (LIST, R6 대신): 키는 엄격히 증가하며 마지막은 최대 11,171이다(R4가 NS를 영역에 대해 확정한 뒤에만 읽는다).
- R7: 모든 항목 필드가 그 평면의 개수 이하이다.
- L7 (LIST, R7과 R8의 항목 부분 대신): 모든 항목 필드가 0xFFFF이거나 글리프가 존재하는 조각 번호이다.
- R8 (JSET과 마찬가지로 호출자의 것. dense와 SPARSE): PI + PM + PF보다 작은 모든 조각 번호, 폴백이 지명하는 모든 조각, 빈 것이
  아닌 모든 호환 조각에 글리프가 있다. 폴백 자체의 조각은 폴백을 읽을 수 있는 빌드에서만 검사할 수 있다. 읽을 수 없는
  빌드(`SVF_FACE_JSET_UNREAD`)에서는 JMAP 부분은 계속 쓸 수 있고, 모든 버전을 읽는 Python은 폴백이 글리프 없는 조각을 지명하는 블록을
  잘못된 것으로 표시한다(설계상 빌드에 따라 다르다. 평면 조각과 호환 조각은 어디서나 검사한다).

LIST의 헤더 규칙은 R1', L2, L3, R4이고 내용 규칙은 L5, L6, L7이다. L5와 L7은 R8처럼 호출자의 검사이다. Python
`jamoset.unpack_jmap`은 이를 하지 않는다(`parse_svfn`의 usable 규칙은 한다).

**리더 상태.** 부분마다 원인 비트가 하나씩 있다. `SVF_FACE_JSET_BAD`(0x0008)는 잘못되었거나 버전이 0 또는 >= 4인 JSET 부분
블록이다. `SVF_FACE_JSET_UNREAD`(0x0010)는 헤더가 올바른 버전 1 또는 2인데 리더가 컴파일되지 않은 경우이다.
`SVF_FACE_JMAP_BAD`(0x0020)는 위의 어느 규칙에든 실패한 버전 3 블록이며 잘못된 폴백도 포함한다(블록 하나, 판정 하나).
`SVF_FACE_JMAP_UNREAD`(0x0040)는 `SVF_JMAP` 없이 `SVF_JMAP_RECOG`가 있는 빌드의 버전 3 블록, 그리고 `SVF_JMAP`이 있고
`SVF_JMAP_LIST=0`인 빌드에서 헤더 규칙을 통과한 LIST 블록이며, 아니면 `SVF_FACE_JMAP_BAD`이다(아래 표 참고. RECOG 빌드의 경우 인식은
플래그와 NS를 읽고, FALLBACK이 있으면 올바른 버전 1 또는 2 폴백을 JMAP 대신 읽는다. 데스크톱 빌드에서는 기본 켜짐이고 AVR,
`SVF_SMALL`, 다른 MCU에서는 꺼짐). `SVF_JMAP`도 `SVF_JMAP_RECOG`도 없는 빌드는 버전 3을 다른 알 수 없는 버전처럼 다룬다.
`SVF_FACE_JSET_BAD`, 일반 페이스이며 폴백은 쓰이지 않는다.
`SVF_JMAP_RECOG`이 있고 `SVF_JMAP`이 없는 빌드에서는 폴백이 JSET 부분이다. 그 판정은 `SVF_FACE_JSET_BAD` / `SVF_FACE_JSET_UNREAD`이며(`SVF_FACE_JMAP_UNREAD`와 함께), 거기서 `SVF_FACE_JMAP_BAD`를 설정하는 것은 advance 비교(R4), 플래그와 NS 규칙(R1, R3. LIST는 R1'과 L3), 정확히 65,535바이트인 영역(R4)뿐이다(폴백 헤더에 못 미치게 잘린 영역은 잘못된 폴백이다. `SVF_FACE_JMAP_UNREAD`와 함께 `SVF_FACE_JSET_BAD`). 따라서 "블록 하나, 판정 하나"는 블록을 읽는 빌드(`SVF_JMAP`, LIST는 `SVF_JMAP_LIST`도)에서 성립하며, `SVF_JMAP_LIST=0`이나 RECOG 빌드에서는 성립하지 않는다. 올바르게 구성된 폴백이라도 그 버전 1 또는 2 리더가 컴파일되어 있지 않으면 블록을 잘못된 것으로 만들지 않는다. JMAP 부분은 계속
쓸 수 있고 폴백 부분은 `SVF_FACE_JSET_UNREAD`이다. `SVF_JMAP`이 있고 `SVF_JSET_BIG`이 없는 빌드에서, 다섯 개수가 BIG 행 안에
있지만 빌드의 행을 하나 넘는 폴백에도 같은 것이 적용된다. 그 폴백은 `SVF_FACE_JSET_UNREAD`이고(개수만 읽는다) JMAP 부분은
계속 쓸 수 있다. 그런 개수를 가진 단독 JSET은 `SVF_FACE_JSET_BAD`이다. JMAP 부분을 쓸 수 없는 페이스는 일반 페이스로
불러와진다.

| build | LIST face (flag 0x08) |
|---|---|
| `SVF_JMAP=1`, `SVF_JMAP_LIST=1` (`SVF_JMAP`의 기본값) | 읽는다. 키 미스는 폴백으로 간다. 규칙(R1', L2, L3, R4, L5, L6, L7) 실패: `SVF_FACE_JMAP_BAD`, 일반 |
| `SVF_JMAP=1`, `SVF_JMAP_LIST=0` | 헤더 규칙 R1', L2, L3, R4만, 폴백 자체의 올바른 구성도 포함한다. 실패는 `SVF_FACE_JMAP_BAD`, 일반. 통과는 `SVF_FACE_JMAP_UNREAD`이며 폴백을 쓴다. 여기서는 L5-L7을 적용하지 않으므로 키가 정렬되지 않았거나 글리프 없는 필드가 있는 블록은 `SVF_JMAP_LIST=1`에서는 `SVF_FACE_JMAP_BAD`이고 여기서는 "폴백 사용"이다(RECOG 빌드에 있는 것과 같은 종류의 예외이며, "블록 하나, 판정 하나"는 블록을 읽는 빌드에 대한 약속이다) |
| `SVF_JMAP=0`, `SVF_JMAP_RECOG=1` | 인식은 자체의 규칙 집합과 읽기 패턴을 유지한다. 바이트 6-9를 읽고, F + 12 <= 영역이 되면 F + 11의 한 바이트를 읽으며, 바이트 10-15는 읽지 않는다(그래서 L2와 R2는 적용되지 않는다). R1'(마스크와 조합 검사), L3(NS 1..255), LIST의 F = 118 + 8 NS는 안다. R1', L3, advance 비교, 정확히 65,535바이트인 영역에는 `SVF_FACE_JMAP_BAD`, 그 외에는 `SVF_FACE_JMAP_UNREAD`이며 블록에 올바르게 구성된 폴백이 있으면 그것을 쓴다. 빌드의 `SVF__JSET_LOAD_MAX`보다 긴 스트리밍 영역은 불러오지 않는다. 페이스는 일반으로 남고 `SVF_FACE_JMAP_UNREAD`만 설정된다(SPARSE 블록도 같다) |
| 둘 다 없음 | `SVF_FACE_JSET_BAD`, 일반. 모든 버전 3 블록과 같다 |

LIST 이전에 빌드된 이 트리의 빌드는 LIST 페이스를 폴백까지 포함해 일반으로 본다(R4가 폴백을 찾기 전에 R1이 실패한다).
JMAP 리더는 이 트리 밖에 배포되지 않았다. Python 레퍼런스는 `jamoset.unpack_jmap`이며 그 ValueError 텍스트는
`JMAP Rn`으로 시작한다(LIST는 `JMAP R1`, `JMAP L2`, `JMAP L3`, `JMAP R4`, `JMAP L6`).

### 글리프별 dy (헤더 바이트 17과 18, 메트릭 바이트 3)

SVFN v3 헤더는 48바이트이며 리틀 엔디언이다.

```
0  "SVFN"   4 u16 version (3)   6 u16 flags (bit 0 metrics table, bit 1 JSET, bit 2 marks at origin; others 0, and a reader refuses a face with other bits set)
8  bpp (1, 2, 8)   9 layout: record and row units   10 layout: table unit and offset width   11 reserved (0)
12 u16 glyphs (1..65535)
14 cell width   15 cell height   16 ascent (baseline row)   17 dy_min (int8, <= 0)   18 dy_max (int8, >= 0)   19 reserved (0)
20 u32 metrics table offset      24 u32 glyph data offset        28 u32 glyph data size
32 u32 code point table offset   36 u32 JSET offset              40 u32 JSET size
44 u32 glyph offset table offset
```

메트릭 항목은 4바이트이다. advance, 왼쪽 bearing(int8), 잉크 폭, **dy**(int8). 글리프는 셀 위치보다 `dy`행 아래에 그려지며
(음수: 위), `dy_min <= dy <= dy_max`이다. 글리프의 행은 언제나처럼 셀 안에 저장되며, dy는 그려지는 위치만 옮긴다. 그래서
셀 밖에 놓이게 된 잉크도 잘리지 않고 그려진다. 셀 아래쪽 근처의 한글 베이스라인에 글자가 서야 하는 라틴 페이스는 글자를
디센더가 들어갈 만큼 높게 저장하고 dy만큼 낮게 그린다(`tools/korean/svfdy.py`가 설정하고 `jamoset.py`가 읽어서 유지한다).

- 이것이 의미를 갖기 전에 쓴 모든 파일은 이 바이트들이 모두 0이며 이전과 똑같이 그려진다. 이보다 오래된 엔진은 이를
  무시하므로 모든 글리프가 셀 위치에 그려진다(dy를 쓰는 페이스는 배포하는 곳에서 그렇게 밝혀야 한다).
- 글리프별 dy는 메트릭 테이블이 있는 폰트만 갖는다. 테이블 없이 주어진 범위, `dy_min > 0`이거나 `dy_max < 0`인 범위, 셀 높이보다
  많이 셀 위나 아래에 닿는 범위는 경고와 함께 무시된다(모든 글리프의 dy 0). dy가 범위 밖인 글리프는 dy 0으로 그려지며, 불러올
  때 경고 하나가 그 수를 센다.
- `GlyphMetrics::dy`는 글리프의 dy이고, `bearingY`(베이스라인에서 그려진 저장된 글리프의 위까지)는 `ascent - dy`이다. 셀은
  의미를 유지한다. `baselineRow()`, 페이스 체인 레이아웃, 줄 높이, 맵의 셀 높이 검사는 모두 범위가 아니라 셀을 쓴다.
- 버퍼 규칙: `UnicodeGlyphSource::inkRowsAbove()` / `inkRowsBelow()`는 `-dy_min` / `dy_max`이다(다른 모든 소스는 0. 체인은
  페이스들 중 가장 큰 값을 취하고, `NormalizedGlyphSource`는 자신의 셀을 벗어나는 만큼을 취한다). `row(cp, y)`는 `-inkRowsAbove()`부터
  `cellHeight() + inkRowsBelow() - 1`까지의 `y`에 답하며 글리프는 이미 dy만큼 옮겨져 있다. 그리는 쪽은 글리프 버퍼를 페이스마다
  한 번 `inkRowsAbove() + cellHeight() + inkRowsBelow()`행으로 잡고 셀 윗변보다 `inkRowsAbove()`행 위에 그린다(셀 밖의 null
  행은 빈 것). SCUMM(세로 미러가 글리프를 셀 안에서 돌린다), SCI, AGI(16행 상자 안), AGS, `HiResGlyphRenderer::drawGlyph(font)`가
  그렇게 한다. SCI의 배치 경로는 여전히 텍스트 줄로 클리핑하고, Grim은 셀 행만 그린다(옮겨진 글리프를 셀로 클리핑).
- 자모 세트 페이스는 음절을 dy 0으로 합성한다. 조각은 dy를 가져서는 안 된다(`jamoset.py check`가 이를 거부한다). 그 밖의 글리프
  (라틴)는 가질 수 있다.

### 셀, 레이아웃 바이트, 예약 바이트

**셀**은 리더가 돌려주는 글리프 상자이다. 셀 폭(바이트 14) x 셀 높이(바이트 15) 픽셀이며 `pitch * cell height` 바이트,
`pitch = (cell width * bpp + 7) / 8`, 행은 MSB 우선이다. 행의 마지막 바이트에서 셀 폭을 넘는 비트는 0으로 쓰고 리더가
마스킹한다.

**레이아웃 바이트(9와 10)**는 정렬 단위를 주며, 각각 2의 거듭제곱을 log2로 저장한 0..6(1..64바이트)이다.

```
byte 9   bits 0-2  REC  log2 of the record unit: every glyph record starts at a multiple of 2^REC from the file start
         bits 3-5  ROW  log2 of the row unit: each row of a record takes wb rounded up to 2^ROW bytes
         bits 6-7  0
byte 10  bits 0-2  TAB  log2 of the table unit: the code point table, metrics table, JSET, glyph offset table and glyph
                        data start at multiples of 2^TAB (the glyph data also at a multiple of 2^REC)
         bit 3     OFF  glyph offset table entries: 0 = u16 counting in units of 2^REC, 1 = u32 counting bytes
         bits 4-7  0
```

`REC, ROW, TAB <= 6`이고 `ROW <= REC`이며 예약 비트는 0이다. 바이트 11과 바이트 19는 예약이며 0으로 쓰고 모든 리더가
무시한다. (바이트 9..11은 버전 1과 2의 그림자와 코드 페이지였으며, 지금은 어떤 것도 이를 읽지 않는다.)

**테이블.** 모든 오프셋은 파일 오프셋이며 바이트 48 이후이고, 각 테이블은 파일 안에 있다.

- 코드 포인트 테이블(바이트 32): `u32 code point, u32 glyph index` 항목 `glyphs`개이며 보통 코드 포인트로 정렬된다. 두 번
  나열된 코드 포인트는 마지막 항목으로 해석된다.
- 메트릭 테이블(플래그 비트 0, 바이트 20): 4바이트 항목 `glyphs`개, `advance, bearing_x (int8), ink_w, dy (int8)`("글리프별
  dy" 참고). 리더는 advance, bearing, 잉크 폭을 여기서 가져오며, 레코드의 상자에서 가져오지 않는다.
- JSET(플래그 비트 1, 바이트 36과 40): "자모 세트 폰트"를 참고한다. 플래그가 없으면 두 필드 모두 0이다.
- 글리프 오프셋 테이블(바이트 44): `glyphs + 1`개 항목. 항목 `i`는 글리프 데이터 오프셋에 대한 레코드 `i`의 시작이며(OFF에 따라
  2^REC 단위의 u16 또는 u32 바이트), 항목 `glyphs`는 글리프 데이터 크기와 같고, 항목은 감소하지 않으며, 바이트로 환산한 각각은
  2^REC의 배수이다. 레코드 `i`의 길이는 `off[i+1] - off[i]`이다.
- 글리프 데이터(바이트 24, 크기는 28): 인덱스 순서의 레코드.

바이트 20..47의 다섯 오프셋은 2^TAB의 배수이고, 글리프 데이터 오프셋은 2^REC의 배수이기도 하며, 글리프 데이터 크기는
2^REC의 배수이다.

**글리프 레코드.**

```
0  x0   left edge of the box, in BYTES of a cell row
1  y0   top row of the box in the cell
2  wb   box width in BYTES (0 = blank glyph, no rows follow)
3  h    box rows (0 = blank glyph)
4  phase bytes (below), then h rows of rp bytes, rp = wb rounded up to 2^ROW,
   then padding to the next multiple of 2^REC
```

`x0 + wb <= pitch`이고 `y0 + h <= cell height`이다. 행은 셀 자체의 행 바이트를 바이트 경계에서 자른 것이므로, 리더는 셀을
비우고 `h`개 행 각각을 `cell + (y0 + r) * pitch + x0`에 복사한다(합성된 음절 조각이면 바이트별 최댓값을 취한다). 빈 글리프는
`wb == 0` 또는 `h == 0`이다. 4바이트 레코드이며 셀은 비어 있다. **Phase:** `REC >= 2`이고 `ROW == 0`일 때 `wb == pitch`인 레코드는
행을 `4 + ((y0 * pitch) & 3)`에서 시작하므로 행은 셀 안의 위치와 4로 나눈 나머지가 같은 오프셋에 놓인다. 그 밖의 모든 레코드는
phase가 0이다. 쓰는 쪽이 어떤 상자(셀 전체, 전체 행, 또는 바이트 단위의 잉크 열과 행)를 고를지는 그쪽의 정책이며, 리더는
알지 못한다.

**프로파일.** 작성기(`--profile`, 기본 `default`)는 이름 붙은 단위 집합을 받는다. 페이스의 픽셀은 어느 프로파일에서나
같다.

| profile | REC / ROW / TAB (bytes) | box | offsets |
|---|---|---|---|
| `mcu-strict` | 4 / 1 / 4 | x-boxed | u16 (데이터가 `65535 << REC`를 넘으면 u32) |
| `default` | 4 / 1 / 4 | x-boxed | u32 (`svf/`의 형태) |
| `dos`, `wasm` | 1 / 1 / 1 | x-boxed | u16 (64 KB를 넘으면 u32) |
| `full` | 4 / 1 / 4 | full cells | u32 |
| `simd16` | 16 / 1 / 16 | x-boxed | u32 |

**지원 집합.** 리더 빌드는 유효한 레이아웃 중 일부만 받아들이고 나머지는 테이블을 읽기 전에 `SVF_E_LAYOUT`으로 거부할 수 있다.
C 라이브러리는 `SVF_LAYOUTS`로 빌드하지 않는 한 모든 유효한 레이아웃을 받는다(Cortex-M0+ P1/P2와 AVR 빌드는 정확히
`mcu-strict` 단위를 받는다). Python 도구와 ScummVM은 모든 유효한 레이아웃을 읽는다.

설계와 측정: `docs/superpowers/specs/2026-10-21-svf-v3-design.md`.

### 검증

리더가 검사하는 것(`jamoset.parse_svfn`과 C 렌더러. 엔진의 `readLayout`이 따른다)을 순서대로 적는다.

- 매직 `SVFN`, 다음으로 버전 3(아니면 `SVF_E_VERSION`), 다음으로 레이아웃 바이트(예약 비트 0, 단위는 최대 6, `ROW <= REC`)와
  빌드의 지원 집합(`SVF_E_LAYOUT`).
- `bpp`는 1, 2, 8. 글리프 수 0이나 빈 글리프 상자(셀 폭 또는 높이 0)는 거부한다.
- 코드 포인트 테이블, 글리프 오프셋 테이블, 글리프 데이터는 파일 안에 있고 헤더 뒤에 있으며(`SVF_E_RANGE`), 크기가 있는 JSET
  블록도 그렇다.
- 정렬 마스크와 글리프 오프셋 테이블(항목은 2^REC의 배수, 감소하지 않음, 마지막은 글리프 데이터 크기와 같음)이 성립한다
  (`SVF_E_LAYOUT`).
- 코드 포인트 테이블의 모든 글리프 인덱스는 `glyphs`보다 작다. mapped 페이스는 열 때 모든 레코드를 검사한다(상자가 셀 안에
  있고, 행이 레코드 길이 안에 있음: `SVF_E_RANGE`). 스트리밍 페이스는 레코드를 읽을 때 검사하며 그때 셀은 빈 채로 남는다.
- 파일에 들어맞지 않거나 헤더 안에 놓인 메트릭 테이블(플래그 비트 0)은 버려지고 글리프는 유지된다. 이후 모든 글리프는 셀 폭만큼
  전진한다.
- 코드 포인트 테이블에 두 번 나열된 코드 포인트는 마지막 항목으로 해석된다.

### 폐기: 버전 1과 2

버전 1은 글리프를 코드 페이지 순서로 두었고 코드 포인트 테이블이 없었다. 버전 2는 헤더가 36바이트였으며 코드 포인트 테이블이
바이트 32에, 그림자와 코드 페이지가 바이트 9..11에, 고정 stride의 전체 셀 글리프 데이터가 있었고, JSET 블록은 코드 포인트
테이블 바로 뒤에 있었다. 둘 다 더는 읽지 않는다. C 렌더러는 `SVF_E_VERSION`을 반환하고, `jamoset.parse_svfn`은
`ValueError("SVFN version 2: convert
with tools/svf2to3.py")`를 일으킨다. `tools/svf2to3.py`(비공개 `_parse_v2`가 남은 유일한 v2 리더이다)는 v2 페이스를 어느
프로파일의 v3로든 변환하며 픽셀이 바뀌지 않았음을 증명한다. `svf/`의 모든 페이스를 그렇게 변환했고, 동일성은
`c/bench/V2V3-IDENTITY.md`에 기록했다.

### 결합 부호 (플래그 비트 2)

헤더 플래그에 비트 2(0x4)가 있는 파일은 각 결합 부호를, 잉크가 셀 안에서 펜의 왼쪽에 오도록 저장한다. 리더는 부호를 이렇게
그린다.

- 부호는 advance가 0이다.
- `anchorX - originX`에 그린다. `anchorX`는 현재 펜이다. 부호가 아닌 직전 글리프 뒤의 펜이며, 줄 맨 앞의 부호라면 줄이 시작되는
  펜이다. 이것이 이식 가능한 규칙이다(C 렌더러).
- `originX`는 페이스에 플래그 비트 2가 있고 부호의 왼쪽 bearing(메트릭 바이트 1)이 음수이면 `min(-bearing_x, cell width)`,
  아니면 0이다.

비트 2가 없으면 `originX`는 언제나 0이다. 부호의 행은 펜에서 시작한다. 어떤 코드 포인트가 부호인지는 파일이 아니라 리더의
선택이다. 엔진은 이를 자신의 글리프 소스에서 가져오고, C 렌더러는 기본으로 U+0300..U+036F를 쓰며 호출자의 판정
함수(`c/include/svf.h`의 `svf_is_mark_fn`)를 받는다.

엔진도 `originX`를 같은 방식으로 계산하지만(`glyph_source_svfn.cpp:384-390`) 그 앵커는 펜과 다를 수 있다. 부호가 아닌 각 글리프 뒤에
`_anchorX = drawX + originX + own`으로 설정하는데(`engines/scumm/hires_text.cpp:1356`), `drawX`는 글리프를 게임 셀 안에서 가운데
맞추려고 더하는 여유분(1354행)을 포함하고, `own`은 글리프 자신의 advance(소스의 advance, 없으면 메트릭 advance)로 펜이 움직이는
양과 같을 필요가 없다. 그 행에 아직 앵커가 없는 부호도 거기서는 펜에서 `originX`를 뺀 곳에 그려진다(1328행).

## ScummVM 불러오기 (부록)

ScummVM이 페이스를 불러오는 방식은 형식의 일부가 아니다. 이 절들은 그 엔진의 맵 키를 설명하며 참고용으로 유지한다. 이식
가능한 렌더러의 API(페이스를 통째로 또는 스트리밍으로 열고 한 줄을 그린다)는 `c/include/svf.h`이다.

### 통째로 또는 스트리밍: `[load]` 절

SVF는 통째로 메모리에 읽거나, 테이블만 읽고(글리프당 4바이트와 8바이트) 각 글리프는 그릴 때 파일에서 읽는다(`HIRES_SVF_CACHE_KB`
크기의 캐시, 줄 단위 프리페치). 기본으로는 크기가 결정한다. 글리프 데이터가 임계값(64 KB, `HIRES_SVF_STREAM_MIN`. DOS 포트는 이를
512 KB, `dos_svf_preload_kb`로 올린다) 이하이면 통째로 읽고, 그보다 크면 스트리밍한다. 맵은 페이스별로 대신 정할 수 있다. 어느
페이스가 매초 대사를 싣고 어느 것이 타이틀 카드에 한 번 그려지는지 맵은 알기 때문이다.

```ini
[fonts]
dlg=NGOTB21A.SVF
card=GBATB23A.SVF

[load]
dlg=whole        ; always in memory, however large
card=stream      ; always read from the file, however small
[load:clut8]
card=auto        ; the size rule again for the 8-bit set
```

키는 `[fonts]` 이름이다(여기서 페이스는 경로로 지명하지 않는다). 값은 다음과 같다.

| value | the face |
|-------|----------|
| `whole` | 크기와 무관하게 메모리에 읽는다. 할당이 실패해도 스트리밍으로 대체한다 |
| `stream` | 크기와 무관하게 파일에 남는다 |
| `auto` | 위의 크기 규칙을 따른다. 절이 지명하지 않은 모든 페이스의 기본값 |

`[load:<qualifier>]`는 `[fonts]`의 규칙을 따른다. 한정자 없는 절, 그다음 각 한정자를 덜 구체적인 것부터 적용하므로, 한정된 항목은
그 이름에 대해 한정 없는 항목을 대체한다(`auto` 포함. 한정 없는 `whole`/`stream`을 되돌린다). 선택은 이름이 아니라 파일에
속한다. 하나의 파일로 해석되는 두 이름은 불러온 페이스 하나를 공유하며, 둘이 어긋나면 절에서 먼저 나온 것이 이기고 경고가 이를
알린다. 맵의 `[fonts]`에 없는 이름이나 `whole`, `stream`, `auto`가 아닌 값은 한 번 경고하고 `auto`를 뜻한다. `[load]`가 없는
맵은 이전과 똑같이 불러온다. 자모 세트 페이스(아래)도 같은 폰트를 감싸므로 이 선택을 따른다. SCUMM, SCI, AGI가 이 절을 읽으며,
AGS는 모든 페이스를 통째로 불러오고 이를 쓰지 않는다고 경고한다. ini 키(`hires_text_face`)의 경로로 닿는 페이스는 `[fonts]`
이름이 아니므로 언제나 `auto`이다.

### 게임이 그리는 글리프 미리 불러오기: `[preload]` 절

스트리밍 페이스는 각 글리프를 처음 그릴 때 디스크 읽기 비용이 든다. 맵은 페이스가 그릴 것으로 예상되는 문자를 알려 줄 수 있으며,
그러면 문자들은 플레이 중에 하나씩이 아니라 맵을 불러올 때 한 번에 읽힌다.

```ini
[fonts]
dlg=NGOTB16B.SVF
card=GBATB23.SVF

[preload]
dlg=NGOTB16B.HOT       ; characters to keep in memory for this face
card=data:GBATB23.HOT  ; a path next to the map, or data:
```

`.HOT` 파일은 UTF-8 텍스트이다. 문자들이 임의의 순서와 임의의 줄바꿈으로 들어 있고, 첫 문자가 `#`인 줄은 주석이며, 공백과
바이트 순서 표시는 건너뛴다. `tools/korean/charsetchars.py --hot-dir`는 게임의 스크립트와 번역으로부터 맵의 모든 페이스에 대해
하나씩 쓴다(그 페이스를 체인에 쓰는 문자 집합의 합집합에 ASCII를 더한 것). 손으로 편집할 수 있다. 키와 한정자는 `[load]`를
따른다. 키는 `[fonts]` 이름이고, `[preload:clut8]`은 한정 없는 절 위에 덧씌우며(빈 값은 목록을 버린다), 페이스는 목록 하나를
갖고(한 파일의 두 이름: 먼저 나온 것이 이기며 경고), 알 수 없는 이름은 경고이고, 읽을 수 없는 목록 파일은 경고 하나와 미리 불러오기
없음이다. `[preload]`가 없는 맵은 이전과 똑같이 불러온다.

엔진은 스트리밍 페이스(`stream`, 또는 임계값을 넘는 `auto`)를 열 때 다음을 한다. 페이스의 글리프 캐시를 목록에 맞춰 잡는다. 목록의
글리프 중 페이스가 가진 것의 저장 바이트를 `HIRES_SVF_READ_BLOCK`으로 올림한 만큼의 캐시 항목이며 32개 이상이다. 그리고 글리프를
곧바로 그곳에 읽는데, 파일 안의 위치로 정렬하므로 하나의 읽기 블록에 든 글리프는 읽기 한 번 값이다. 이후 캐시는 평소의 LRU이다.
목록 밖의 글리프는 가장 오래 쓰이지 않은 것을 밀어내며, 그것이 목록에 있던 것일 수 있다(다음에 쓸 때 다시 읽는다). 통째로 가진
페이스는 목록을 무시한다. 자모 세트 페이스는 목록의 음절을 파일이 가진 조각으로 풀어서 그것들을 미리 불러온다. 캐시용 메모리가
없으면 페이스는 가진 캐시를 유지하고 아무것도 읽지 않으며 경고 하나가 이를 알린다. SCUMM, SCI, AGI가 이 절을 읽고, AGS는 이를
쓰지 않는다고 경고한다.

디버그 소켓의 `caches all`은 페이스별로 `list`(목록이 지명한 글리프 중 페이스가 가진 것), `preloaded`(그중 열 때 읽은 것),
`misses`(히트가 아니었던 조회), `listevict`(이후 밀려난 목록 글리프)를 보여 준다. `hits`, `reads`, `read`는 첫 그리기부터 이전처럼
세며, 미리 불러오기 자체의 읽기도 `reads`에 포함된다.
