[English](tools.md) | **한국어**

# 도구

폰트 읽기, SVFN 페이스 생성·변환, 검사에 쓰는 명령줄 도구의 참조 문서이다.
포맷과 용어는 [SVF 명세](../spec/SVF.ko.md)와 [용어집](../spec/SVF.ko.md#glossary),
조합 원리는 [자모 세트](jamo-sets.ko.md), 커버리지와 비트 깊이는 [안티앨리어싱](anti-aliasing.ko.md)을 참고한다.

입력 종류별 실행 예는 [레시피](recipes.ko.md)에 있다. 생성한 페이스를 사용하는 방법은
[C 렌더러 가이드](c-renderer-guide.ko.md), [렌더러 설계](../spec/renderer-design.ko.md),
[웹 렌더러 가이드](web-renderer-guide.ko.md)를 참고한다. GUI로 변환하려면
[데스크톱 앱](desktop-app.ko.md)과 [Maker 데스크톱](maker-desktop.ko.md)을 참고한다.
전체 문서 안내는 [README](../README.ko.md)에 있다.

일부 도구는 다른 도구가 import하는 라이브러리로도 쓰인다. 맞춤 모듈
`jamofit.py`, `jamoaa.py`, `jamoadapt.py`, `jamoseg.py`에는 자체 명령줄이 없다.

## 1. 도구가 만드는 SVFN 종류

**SVFN** 파일(매직 `SVFN`, 리틀 엔디언)은 헤더, 코드 포인트 표, 선택적인 글리프별 메트릭, 글리프 레코드로 이루어진
비트맵 폰트이다. SVFN 작성기는 `jamoset.pack_svfn`을 통해 **버전 3**을 쓴다([명세](../spec/SVF.ko.md)). 버전 2(고정 셀)는 `svf2to3.py`가 변환하며
(`jamoset.parse_svfn`은 v2 페이스를 변환 안내 메시지와 함께 거부한다), 버전 1(코드 페이지 순서)은 없어졌다. 레이아웃을 선택할 수 있는 작성기는 `--profile NAME`과 `--box x|y|full`을 받는다.
프로파일 이름, `REC,ROW,TAB,OFF`의 의미와 기본값은 각 도구의 옵션 및 `svf2to3.py` 표를 참고한다.
`macfbit_svf.py`, `jamofill.py`, `jamomerge.py`는 이 옵션을 제공하지 않는다. 헤더 바이트 17과 18은 폰트 전체의 **dy** 범위를 담고,
메트릭 바이트 3은 각 글리프의 dy를 담는다(글리프는 셀 위치보다 dy행 아래에 그려진다). 메트릭 표가 있는 폰트만 dy를 가질 수 있다.

도구는 두 종류를 쓴다.

- **완성형 페이스**는 코드 포인트마다 글리프 하나를 저장한다(한글 음절, ASCII 문자, 기호). **1, 2, 8 bpp**로
  쓴다(1 bpp는 스텐실, 2 bpp는 4단계 커버리지, 8 bpp는 256단계). 4 bpp는 없다. 페이스는 글리프별 advance, 왼쪽 베어링,
  잉크 폭을 가진 메트릭 표(헤더 플래그 비트 0)를 가질 수 있으며, 이 경우 가변 폭이 된다.
  코드 포인트 목록에서 `mkfont.py`가 쓴 페이스는 플래그 비트 2도 설정한다(결합 표시는 펜을
  `max(0, -bearingX)`에 둔 채 저장된다).
- **자모 세트(jamo set)**(헤더 플래그 비트 1)는 위치별 자모 **조각(piece)**을
  `U+F0000 + 조각 번호`의 글리프로 저장하고, 코드 포인트 표 바로 뒤의 **JSET** 블록으로 음절을 조합한다.
  버전 1·2 블록은 클래스·벌 표를, 버전 3(JMAP)은 음절 매핑을 쓴다. 음절의 조각은 픽셀별 최댓값으로
  합친다(1 bpp에서는 비트 OR와 같다). JMAP은 일부 음절만 제공할 수도 있다.
  예를 들어 16 px, 1 bpp인 `svf/dos/NEODG16G.SVF`는 10,684바이트로 11,172개 음절을 합성한다(참고 문헌 1·2).
  조각을 만드는 빌더는 1 또는 2 bpp를 지원한다. ASCII, 기호와 개별 완성형 글리프도 함께 저장할 수 있다.
  호환 자모 U+3131..U+3163은 블록이 조각을 지정하면 그 조각으로 그려진다.
  JSET을 지원하지 않는 SVFN v3 리더는 저장된 일반 글리프만 사용할 수 있다.

두 종류 모두 **dy** 범위를 가질 수 있다. 자모 세트는 음절을 dy 0에서 합성한다(조각은 dy를 가질 수 없다).

**레이아웃(layout)**은 자모 세트의 벌 체계이다. 초성/종성 클래스, 초성/중성/종성 벌 표, 조각 표로 이루어진다. 이름이
있는 레이아웃은 `844`(DOS 8x4x4 표준), `844-ihnm`, `844-hbios24`, `844-hwp3`, `hwp1`, `1044-san`, `621`, `hanterm-johab`,
`hanterm-844`, `dkb-printer-7x2x2`, `dkb-printer-12x4x4`, `kyra-lok`, `mac-fbit-45sets`, `spec`, `adaptive[:NI,NM,NF]`이다.

한 문단으로 보는 지도: `mkfont.py`는 아웃라인 폰트에서 **완성형 페이스**를 굽고, `bdfface.py`/`johab844.py`는
비트맵 폰트에서 굽는다.
`jamoset.py`, `jamovec.py`, `svf_synth.py`는 **자모 세트**와 합성 페이스를 쓰고, `svfdy.py`는 기존 페이스의 **dy**를
편집하며, `tools/build/build_faces.py`와 `web/` 도구는 페이스를 다시 빌드하고 서비스한다. 도구별 자세한 내용은 다음과 같다.

- `mkfont.py`는 TTF/OTF에서 **완성형 페이스**를 쓴다(1/2/8 bpp, SVFN v3, 코드 포인트 목록 필요).
- `bdfface.py`는 한글 BDF와 ASCII BDF/HBF에서 **완성형 1 bpp 페이스**를 쓴다. `johab844.py`는 원시 8x4x4 Johab
  폰트로 **완성형 16x16 1 bpp 페이스**의 한글을 다시 그린다.
- `jamoset.py`는 DOS Johab 원시 폰트, hanterm BDF, Dokkaebi 프린터 FNT, Kyra `.BIT`, Mac HangulTalk `fbit` 리소스
  포크에서, 또는 아웃라인 폰트(`--from-ttf`)나 완성형 1 bpp 페이스(`--from-svf`)를 맞춰서 **자모 세트**(1 또는 2 bpp)를
  쓴다. `jamovec.py`는 폰트의 자모를 한 번 분리해 어떤 크기로든 렌더링하는 방식으로 **자모 세트**를 쓴다.
- `svfdy.py`는 기존 페이스의 **dy**를 편집한다. `svf_synth.py`는 C 테스트용 합성 페이스를 쓴다.
- `tools/build/build_faces.py`는 `svf/`의 페이스를 업스트림 폰트에서 다시 빌드한다(`tools/build/faces.tsv`, [recipes/svf-faces.ko.md](recipes/svf-faces.ko.md)).
- `web/` 도구는 WASM 선택기가 서비스하는 페이스를 인덱싱하고 복사한다.

## 2. 핵심 빌더

### `tools/jamoset.py`

**목적.** DOS 시대 원본 폰트에서 자모 세트 SVF(플래그 비트 1과 JSET 블록)를 만들거나, 조각을 아웃라인 폰트나 기존의
완성형 페이스에 맞춘다. SVFN v3도 쓰고(`write_svfn`, `pack_svfn`, `--profile`, `--box`) 읽으며(v2 페이스는 변환 안내
메시지와 함께 거부된다, `tools/svf2to3.py`), JSET 블록을 묶고 풀며, 검사를 위해 음절을 합성한다.

**상태.** 범용이다. 게임 전용 벌 체계(SAGA IHNM, hanterm, Dokkaebi 프린터, Kyra LoK, Mac
HangulTalk, HWP 1.x)의 이름을 갖지만 특정 게임에 묶여 있지 않다.

**입력.** 모드에 따라 다르다.
- 자체 파서로 읽는 DOS Johab 원시 폰트: 원시 8x4x4(`844`, 16/24/40/48 px, 11520/11522/25920/72000/103680/15584
  바이트), 10x4x4(`1044-san`, 12800바이트), 6x2x1(`621`, 6144바이트, 바이트 열 순서), HBIOS/Taebaek 24x30
  (`844-hbios24`, 243900바이트), SAGA IHNM(`844-ihnm`), Kyra `MK15.BIT`(11550바이트), Dokkaebi 프린터
  `HANGUL16/24.FNT`(15360/34560, 열 우선)와 `HANGUL40/48.FNT`(176000/253440);
- `ENCODING`이 johab-1 글리프 번호인 hanterm BDF(`hanterm-johab`). 정규식 리더로 파싱한다. hanterm johab844-1 BDF(`hanterm-844`:
  글리프 360개, `ENCODING` = DOS 8x4x4 순서의 글리프 번호. 같은 리더로 읽고 `844` 표로 조합한다);
- Mac HangulTalk 1.0 `fbit` 리소스 포크(`mac-fbit-45sets`). 원시 리소스 맵에서 파싱한다;
- HWP 1.x `HANGUL.SFT` / `HANGUL1/2/3.PFT`(`hwp1`, `--face 0..2`): JSET 표는 그 페이스에 대한 HWP.EXE 자체의 규칙이며 `hwpfont.py`를
  통해 읽는다. HWP 3.0 `HAN16_*.FNT`(`844-hwp3`: 음절 2,350자 뒤의 360개 조각으로 이루어진 8x4x4 벌 체계);
- `rawcarve.py` compose 명세가 설명하는 모든 폰트(`spec`, `--spec SPEC.json` 또는 내장 `spc1500`): 위치 인자 파일은 명세의
  오프셋이 가리키는 바이트이고, JSET은 명세 자신의 규칙 그대로다(정확);
- `--eng` 원시 8x16 DOS 영문 폰트(2048 또는 4096바이트), 16x16 영문 폰트(8192바이트: 2바이트 16행짜리 글리프 256개,
  `rawcarve.py eng --width 16`이 쓰는 것. 전진 폭은 0-9, A-Z, a-z 잉크의 오른쪽 끝에 그들의 가장 작은 왼쪽 여백을 더한 값(잉크가 없으면 16), 또는
  `--eng-advance`), 또는 HBIOS 12x24(15360) / PFT 12x24(12288) / Taebaek PFT 20x40(30720, GASCII40) / 24x48(49152, GASCII48), 또는 HWP 영문 폰트: HWP 1.x `ASCII.SFT`(8x16) / `ASCII.PFT`(14x24, 전진 폭 14. 여섯 페이스 중 `--eng-face`) 또는 HWP 3.0 `ENG*.FNT`(8x16, 12x24, 20x40). 헤더로 알아본다;
- `--base` SVFN v3 페이스(음절이 아닌 글리프를 유지한다. v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`));
- `--from-ttf` 아웃라인 TTF/OTF. 1 bpp `mono` 대상은 freetype-py로, 2 bpp와 `--binarize threshold|ridge`는
  fontTools(`jamoaa.py`를 통해)로 읽는다;
- `--from-svf` 완성형 1 bpp SVFN v3 페이스(v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`)).

**출력.** SVFN v3 자모 세트 페이스(플래그 비트 1, 메트릭이 있으면 비트 0도). 기본은 1 bpp이고 `--bpp 2`이면 2 bpp이다.
조각은 `U+F0000 + n`에 있으며, `--from-ttf`/`--from-svf`는 ASCII 글리프도 담는다. `--blank-compat`는 대신 기존 자모 세트를
다시 쓴다.

**사용법.**

    python3 tools/jamoset.py SOURCE --layout LAYOUT -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --from-ttf FONT --size N -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --from-svf FACE.SVF -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --blank-compat FACE.SVF -o OUT.SVF

옵션(기본값은 괄호 안). **모드** 열은 옵션이 어느 모드에 속하는지 나타낸다. `source`(위치 인자로 주는 DOS Johab,
hanterm BDF, Kyra `.BIT`, Dokkaebi FNT, HWP 3.0 HAN16 FNT 파일), `mac-fbit-45sets`(위치 인자로 주는 Mac HangulTalk `fbit`
리소스 포크. 독자적인 모드로, `--from-*`, `--eng`, `--base`를 받지 않는다), `hwp1`(위치 인자로 주는 HWP 1.x 한글 파일. 독자적인
모드로 `--from-*`는 받지 않고, `--eng`와 `--base`는 `source`처럼 받는다), `--from-ttf`, `--from-svf`, `--bpp 2`
(`--from-ttf`와 함께일 때만), `--blank-compat`. 모드에 나열되지 않은 옵션은 결과에 적용되지 않을 수 있다. 다만 `--eng`와 `--base`처럼 사용 전에 읽는 입력은 잘못된 파일이면 오류가 날 수 있다.
단, 표에 "refused"라고 적힌 경우는 예외이다.

| 옵션(기본값) | 모드 | 의미 |
|---|---|---|
| `--layout` (필수) | 모든 모드 | 벌 체계: `1044-san`, `621`, `844`, `844-hbios24`, `844-hwp3`, `844-ihnm`, `dkb-printer-12x4x4`, `dkb-printer-7x2x2`, `hanterm-844`, `hanterm-johab`, `hwp1`, `kyra-lok`, `mac-fbit-45sets`, `spec`, `adaptive[:NI,NM,NF]`. `adaptive`는 `--from-ttf` 또는 `--from-svf`가 필요하다. `mac-fbit-45sets`와 `hwp1`은 독자적인 모드이다(위치 인자 파일이 `fbit` 리소스 포크, HWP 1.x 한글 파일) |
| `--face N` (0) | `source`, `hwp1` | Dokkaebi 프린터 폰트의 서체(0 또는 1), HWP 1.x 한글 파일의 페이스(0, 1, 2) |
| `--eng FILE` (없음) | `source`, `hwp1`, `--from-ttf`, `--from-svf` | ASCII용 원시 8x16 영문 폰트(2048 또는 4096바이트; 12x24, 20x40, 24x48 페이스와 위의 HWP 영문 폰트도 읽는다). `--bpp 2` 및 `mac-fbit-45sets`와 함께면 거부된다 |
| `--spec SPEC.json\|spc1500` (없음) | `spec` | 위치 인자 파일의 `rawcarve.py` compose 명세(JSON 파일, 또는 내장 `spc1500`: 이 이름은 언제나 내장 명세이고, 그 이름의 파일은 `./spc1500`으로 준다). 명세가 이름 붙인 초성 조각 벌마다 JSET 초성 벌 하나(`novowel` 벌이 먼저), 중성 표마다 중성 벌 하나(`nofinal`, `final`, 그리고 초성 부류를 둘로 만드는 `*_kk` 표), 종성 조각 벌마다 종성 벌 하나, 종성 부류 둘. 다른 배치와 함께 주면 거부한다 |
| `--eng-advance N` (없음) | `--eng`가 있는 곳 | 16x16, 12x24, 20x40, 24x48 영문 폰트의 `--eng` 글리프 전진 폭(1..255. 전진 폭이 8인 8x16 폰트에는 거부한다) |
| `--eng-face N` (0) | `--eng`가 있는 곳 | `--eng`로 준 HWP 1.x `ASCII.SFT` / `ASCII.PFT`의 페이스(0..5: HWP 메뉴의 명조, 고딕, 위첨자, 아래첨자, 이탤릭, 필기체) |
| `--base FILE` (없음) | `source`, `hwp1`, `--from-ttf` | 음절이 아닌 글리프를 유지하는 SVFN v3(같은 셀, 1 bpp). `--from-svf`는 무시한다(입력 페이스가 base이다). `--bpp 2` 및 `mac-fbit-45sets`와 함께면 거부된다 |
| `-o`, `--output` (필수) | 모든 모드 | 출력 경로 |
| `--profile NAME` (`default`), `--box x\|y\|full` (프로파일의 값) | 모든 모드 | 출력의 SVFN v3 레이아웃 프로파일과 잉크 상자 정책(`svf2to3.py` 참고) |
| `--jset-version 1\|2\|auto` (1; `--blank-compat`: 입력의 값) | 모든 모드 | 쓰는 JSET 블록의 버전(아래 "JSET 버전" 참고) |
| `--jset-big` (꺼짐) | 모든 모드 | 표준 한계(12 x 12 클래스, 32/24/16 벌)를 넘어 BIG 한계(19 x 28 클래스, 128/128/64 벌)까지 허용한다(리더에 `SVF_JSET_BIG`가 필요하다). 표준 한계 안의 출력은 이 옵션이 있든 없든 같다("JSET 버전" 참고) |
| `--advance N` (없음) | `source`, `mac-fbit-45sets`, `hwp1`, `--from-ttf`, `--from-svf`, `--bpp 2` | 합성된 음절의 전진 폭(JSET advance 바이트. 레이아웃의 값, 0 = 셀 폭) |
| `--ascent N` (없음) | `source`, `mac-fbit-45sets`, `hwp1` | SVF의 기준선 행(12x24, 14x24, 20x40, 24x48 페이스는 `--eng` 페이스의 기준선, 그 외에는 셀의 7/8). 맞춤 모드는 맞춘 페이스에서 가져오므로 무시한다 |
| `--embolden` (꺼짐) | `source`, `mac-fbit-45sets`, `hwp1` | 모든 조각과 ASCII 글리프를 오른쪽으로 1 px 민 자기 자신과 OR한다. 맞춤 모드는 무시하고, `--bpp 2`와 함께면 거부된다 |
| `--symbols` (꺼짐) | `source`, `mac-fbit-45sets`, `hwp1`, `--bpp 2` | U+2026과 U+25A1을 추가한다. 1 bpp `--from-ttf`/`--from-svf`는 무시한다 |
| `--check` (꺼짐) | `source`, `mac-fbit-45sets`, `hwp1`, `--from-ttf`, `--from-svf`, `--bpp 2` | 출력에서 11,172개 음절 전부를 합성해 검증한다(16 px의 `844`와 `844-hwp3`는 `johab844.py`와도, `hwp1`은 `hwpfont.py`의 HWP 규칙과도 비교해 `hwp1: 11172 syllables identical to the HWP 1.x rule (hwpfont.py)`를 출력한다. `spec`은 모든 음절을 `rawcarve.py compose`와도 비교해 `all 11172 syllables identical to rawcarve.py compose`를 출력한다) |
| `--from-ttf FONT` (없음) | mode | 조각을 `--size`에서의 아웃라인 폰트 음절에 맞춘다 |
| `--from-svf FACE.SVF` (없음) | mode | 1 bpp 완성형 SVFN 페이스를 분해한다(다른 bpp는 거부된다) |
| `--size N` (없음) | `--from-ttf` | 픽셀 크기 |
| `--cell WxH` (없음) | `--from-ttf` | 셀(기본 `SIZExSIZE`) |
| `--baseline N` (없음) | `--from-ttf` | 기준선 행(기본: 잉크 상자 중앙) |
| `--present-only` / `--no-present-only` (켜짐) | `--from-ttf` 1 bpp `mono` | 폰트가 그리는 음절만 맞출지, `.notdef`도 맞출지. `--binarize threshold\|ridge`는 그려진 음절만 맞추며 `--no-present-only`를 거부한다. `--bpp 2`와 함께면 거부된다 |
| `--blank-compat FACE.SVF` (없음) | mode | 온전한 글리프가 있는 호환 자모는 그 글리프에 맡기도록 자모 세트를 다시 쓴다 |
| `--mask-font FONT\|없음` (별칭 `--mask`) | `--from-ttf`, `--from-svf` 1 bpp | OpenType `ljmo`/`vjmo`/`tjmo`가 있는 마스크 폰트. 기본은 `$JAMOSET_MASK_FONT` 또는 freetype/uharfbuzz를 import할 수 있을 때 동봉된 NotoSansKR, 그렇지 않으면 자유 조각 |
| `--mask-radius N` (auto) | `--from-ttf`, `--from-svf` 1 bpp | 마스크 팽창(1은 16 px까지, 2는 24까지, 그 이상은 3) |
| `--passes N` (12) | `--from-ttf`, `--from-svf`, `--bpp 2` | 좌표 하강(coordinate-descent)의 최대 패스 수 |
| `--pylib DIR` (없음) | `--from-ttf`, `--from-svf`, `--bpp 2` | freetype과 uharfbuzz가 있는 디렉터리(`$JAMOSET_PYLIB`도 가능) |
| `--report FILE.json` (없음) | `mac-fbit-45sets`, `--from-ttf`, `--from-svf`, `--bpp 2` | 품질 보고서를 쓴다 |
| `--bpp {1,2}` (1) | `--from-ttf` | 2 = 안티앨리어싱된 조각(fontTools 필요) |
| `--aa-refine N` (2) | `--from-ttf --bpp 2` | 레벨 오차 개선 패스(0 = 중앙값만) |
| `--binarize {mono,threshold,ridge}` (mono) | `--from-ttf` 1 bpp | FreeType 모노크롬, 정확한 면적 커버리지, 또는 그것에 희미한 능선을 더한 것(fontTools) |
| `--threshold F` (0.5) | `--from-ttf --binarize threshold\|ridge` | 커버리지 컷 |
| `--clean` / `--no-clean` (auto) | `--from-ttf`, `--from-svf`, `--bpp 2` | 노이즈 정리(`--bpp 2`와 `--layout adaptive`에서는 켜짐, 그 외에는 꺼짐) |

**JSET 버전.** 버전 1은 일반 빌더의 기본값이다(`svf_synth.py`는 테스트용으로 기본값 2를 쓴다). 버전 2(compact)는 메모리가 제한된 대상을 겨냥한 빌드와
팩용이다([SVF 명세](../spec/SVF.ko.md), "버전 2를 쓸 때"). `--jset-version`은 `1`, `2`, `auto`를 받는다. `auto`는 페이스의 버전 1
블록이 버전 2 블록보다 `JSET_V2_MIN_SAVING`(1,024)바이트 이상 크면 버전 2를 쓰고, 아니면 버전 1을 쓴다. 같은 플래그가
`jamovec.py render`와 `svf2to3.py`에도 있다. `jamoaa.py`(라이브러리)는 빌더의 `jset_version` 인자로 받으며, `jamoset.py --bpp 2`가 이를
넘긴다. `jamovec.py`는 `pack_jset`을 직접 호출한다.
라이브러리로서 `jamoset.py`에는 다음이 있다. `pack(tables, big=False)`(버전 2 블록. `Packed(block, piece_map)`로 반환되며, 맵은
조각 번호를 다시 매긴다: 처음 보면 새 번호, 나중에 보면 별칭), `pack_v1(tables, big=False)`(버전 1 블록), `pack_jset(tables,
version, big=False)`(1, 2 또는 `"auto"`. 같은 `Packed`이며 버전 1은 항등 맵), `choose_jset_version(tables, big=False)`(`auto`가 고르는 것),
`renumber_glyphs(glyphs, piece_map)`(글리프 딕셔너리나 리스트의 plane-15 코드 포인트에 맵을 적용하므로 블록과 글리프가
어긋날 수 없다), `jset_size(...)`(버전 2 크기), `jset_line(face_bytes)`(버전과 두 크기), 그리고
`unpack(block)`. `unpack`은 **두** 버전을 모두 읽고(BIG 개수도 항상) 어느 쪽이든 같은 `Tables`(슬롯별로 풀어낸 조각 목록.
빈 슬롯은 `BLANK`, 호환은 51개 조각 번호)를 돌려준다. SVF Maker는 실행하는 경로에 추가 플래그로 `--jset-version 1|2`를 넘기며,
넘기지 않으면 업로드된 자모 세트 페이스는 블록의 버전을 그대로 유지한다.

**BIG (`--jset-big`).** JSET 한계는 `jamoset.JSET_LIMITS`이다. 표준은 12 x 12 클래스, 32 / 24 / 16 벌이고, BIG은 19 x 28 클래스,
128 / 128 / 64 벌이다(가장 큰 블록: 버전 1은 47,373바이트, 버전 2는 NA = 0일 때 29,708, 모든 슬롯이 별칭이면 45,068).
`unpack`은 항상 두 행을 모두 읽는다. 작성기(`pack`, `pack_v1`, `pack_jset`, `pack_fallback`, 그리고 `--jset-version`이 있는 모든 CLI인 `jamoset.py`,
`jamovec.py render`, `svf2to3.py`. `jamoaa.py`는 `jset_big`)는 표준 행을 넘는 표를 `--jset-big` / `big=True` 없이는
`JSET {name} {v} is not 1..{hi} (--jset-big allows 19 x 28 classes, 128/128/64 sets)`라는 메시지로 거부한다. `svf2to3.py`는 이 규칙을 재인코딩뿐 아니라 v2 블록(또는 JMAP 영역의 폴백)의 그대로 복사에도 적용한다. `jamoset.py --layout adaptive`와 `jamovec.py`의 `--jset-big`는 BIG 표를 쓰는 것만 허용할 뿐이며, 적응형(adaptive) 탐색 한계는 이로 인해 넓어지지 않는다(`--adaptive` / `--class-limit`를 따른다). `jamomerge.py`와 `jamofill.py`에는 그런 옵션이 없으며 BIG 표를 거부한다. `jamofill.py`(골격 읽기), `jamomerge.py`(`read_face`), `jamovec.py`(`tables_json`)는 JMAP 또는 LIST 페이스(JSET 버전 3)를 ValueError로 거부한다. 벌 표가 없기 때문이다. 표준 한계 안의 출력은 플래그가 있든 없든
바이트 단위로 같다. `needs_big(tables)`는 표에 BIG이 필요한지 알려 주고, `class_limits(big)`는
(초성, 종성) 클래스 한계를 주며, `jset_line`은 그런 페이스에 ` big=1`을 덧붙인다. `jamoadapt.FORMAT_LIMITS` / `CLASS_LIMITS`는 두 행을 모두 담고
`adapt(..., class_limit=)`는 정수 또는 (초성, 종성) 쌍을 받는다.

**JMAP (JSET 버전 3).** 라이브러리로서 `jamoset.py`는 [SVF 명세](../spec/SVF.ko.md)("버전 3: 매핑 테이블 (JMAP)")의 매핑 표 블록도 읽고 쓴다.
`Jmap`(advance, plane 개수 `pi`/`pm`/`pf`, `entries` 음절 인덱스 -> plane 인덱스, `block_compat`, 유효한 `compat`, `fallback` Tables, `pieces(cp)`), `jmap_size(ns, four, sparse,
fallback_len)`, `pack_jmap(jmap, fallback_block)`(개수가 255를 넘으면 4B, 항목이 11,172개보다 적으면 SPARSE. 한계를 넘거나 65,534바이트를 넘는 것은 거부한다), `unpack_jmap(block)`(규칙 R1-R7을 명세의 순서대로. ValueError 메시지는
`JMAP Rn ...`), `jmap_from_tables(tables, syllables, glyphs, pad)`(JSET 페이스에서 plane별로 연속된 조각과, U+F0000 + 번호를 키로 하는 새 조각 글리프. 입력 글리프는 조각 번호 또는 코드 포인트를 키로 쓸 수 있다. 페이스의 글리프 딕셔너리 전체가 통하며 낮은 키는 무시된다), 그리고
`shift_pieces(tables, delta)`(모든 조각 번호를 올린 사본. JMAP 폴백은 PI+PM+PF 이상의 조각을 지정해야 하며,
`pack_jmap`은 겹침을 거부한다). `pack_fallback(tables, version, base=0, big=False)`는 JMAP 폴백으로 쓰도록 주어진 조각 번호(에 `base`를 더한 것)를 유지하는 버전 1 또는 2 블록을 쓴다. 버전 2는 각 행을 첫 조각에서 시작해 탐욕적으로 걸으며, 하나씩 증가하는 슬롯은 새 조각으로 저장하고 그 밖의 그려진 슬롯은 모두 별칭으로 저장하므로(가장 긴 연속 탐색이 아니다) `pack`의 것보다 크다. `renumber`, `pack_v1`, `pack`, `pack_jset`, `choose_jset_version`은 `Jmap`을 거부한다
("a JMAP block has no set tables"). `blank_compat`와 `blank_whole_compat`는 JMAP 자체의 호환 항목과 폴백의 호환 항목을 비운다(`blank_compat`는 그 결과 폴백이 바뀌었으면 `fallback_block`을 같은 버전과 번호 체계로 `pack_fallback`으로 다시 인코딩한다(BIG 폴백은 `--jset-big` 여부와 관계없이 자신의 크기로 다시 인코딩되므로 `jamoset.py --blank-compat`는 이를 보존한다). `blank_whole_compat`는 JMAP의 모든 조각을 유지하고 벌 표의 쓰이지 않는 조각만 버린다). LIST 모드(플래그 0x08): `Jmap(..., list_mode=True)`는 `entries`를 음절 인덱스 -> 하나의 공유 풀에 있는 조각 번호 셋(BLANK = 없음. `pi`/`pm`/`pf`는 0)으로 유지한다. 상수 `JMAP_FLAG_LIST`, `JMAP_LIST_MAX`(255), `JMAP_LIST_ENTRIES`(118), `JMAP_LIST_ENTRY`(8). `jmap_size(ns, four, sparse, fallback_len, list_mode)`. `pack_jmap`은 list-mode `Jmap`에 대해 LIST를 쓰고(겹침 거부 없음, 255개 항목 초과는 SPARSE 힌트와 함께 거부), `unpack_jmap`은 그것을 읽으며(규칙 R1', L2, L3, R4, L6. L5/L7은 `parse_svfn`의 사용 가능 규칙이다) `jset_line`은 `list=1`을 출력한다. `unpack`은 버전 3 블록에 `Jmap`을 돌려주며, `pieces_of`, `used_pieces`, `compose`, `jset_line`(`jset=v3 jmap=BYTES ns=NS fallback=v1|v2|없음`, 폴백에 BIG이 필요하면 이어서 ` big=1`)이 이를 받는다. `jmap_list(f, exceptions, compat=None, jset_version=None, fallback=True, advance=0)`는 파싱된 자모 페이스 `f` 위에 LIST를 만든다. `exceptions`는 음절 인덱스(0..11171)를 1-3개의 조각 번호(BLANK로 채움) 또는 온전한 셀(바이트, 묶인 행)에 대응시키고, `compat`는 호환 인덱스(0..50)를 조각 번호 하나 또는 온전한 셀에 대응시킨다(나머지 k는 BLANK로 남아 폴백으로 간다). 온전한 셀은 페이스의 가장 높은 U+F0000 + n 코드 포인트보다 위의 번호를 가진 새 조각이 된다(음절은 s 오름차순, 그다음 호환은 k 오름차순). 0xFFFF에 이르게 되는 번호는 거부된다. `fallback`이 켜져 있으면 페이스의 JSET(버전 1 또는 2)이 그대로 폴백으로 유지되고(`jset_version`이 다르면 번호를 유지한 채 `pack_fallback`으로 다시 인코딩된다) LIST advance는 그 advance 바이트이며 `advance`는 무시된다. `fallback=False`는 폴백 없이 `advance`로 LIST를 만든다. 필드는 BLANK(0xFFFF)일 수 있다(BLANK 번호로 준 호환은 주지 않은 것을 뜻한다). 페이스에 글리프가 없는 조각 번호는 거부된다. 255개 초과 항목, 버전 3 원본(`fallback=False`여도), `fallback=False`와 함께 준 `jset_version`, 쓸 수 있는 JSET이 없는 페이스(`fallback=False`가 아니면), 범위를 벗어난 s 또는 k, 셀도 아니고 1-3개 조각의 목록도 아닌 값, 크기가 잘못된 셀을 거부한다. `(Jmap, {cp: cell})`을 돌려주며, 호출자가 `pack_jmap(jm, jm.fallback_block)`을 쓴다. `jamoset.py`에는 JMAP을 쓰는 옵션이 없고, `jamoexc.py build`가 LIST를 쓴다.

**내부 모듈.** `johab844.py`(844 동일성 검사용), `hwpfont.py`(`hwp1`, `844-hwp3`, HWP 영문 폰트), `rawcarve.py`(`spec`), `jamoaa.py`, `jamofit.py`,
`jamoadapt.py`. **서드파티.** fontTools(`--bpp 2`, `--binarize threshold|ridge`, `--clean` 윤곽 도너용), freetype-py와
uharfbuzz(마스크 폰트와 1 bpp `mono`의 `--from-ttf`용). 둘 다 선택 사항이다.
없으면 `mono` 아웃라인 맞춤은 실패한다. 자동 마스크는 메시지와 함께 생략되고, 명시적으로 지정한 마스크는 실패한다.

**테스트.** `tools/test_jamoset.py`. `tools/test_hwpfont.py`(`hwp1`, `844-hwp3`, HWP `--eng`). `tools/test_tiles.py`(`spec`: 내장
`spc1500` 명세를 MAME 그리기 코드의 독립된 읽기와, 초성 부류가 둘인 8x4x4 명세를 `johab844.py`와, 자체 모음 순서와 반 셀 벌이 있는
명세. 16x16 `--eng`, `--eng-advance`).

### `tools/mkfont.py`

**목적.** TTF 또는 OTF를 명시적인 코드 포인트 목록(`--unicode` 또는 `--chars-from`. 없으면 `mkfont: version 1 (code page order) is gone:
pass --unicode SET`과 함께 종료 코드 2로 끝난다)에서 Pillow의 FreeType 래스터라이저(참고 문헌 3·4)로 완성형 SVFN v3 페이스로 굽는다. 비트맵 BDF나 PCF도
FreeType을 통해 열리지만, 파일에 내장된 스트라이크 크기에서만 열린다.

**상태.** 범용이다.

**입력.** Pillow의 FreeType(`PIL.ImageFont.truetype`)으로 읽는 TTF, OTF, BDF, PCF. 비트맵 BDF나 PCF는
파일에 내장된 픽셀 크기(스트라이크)에서만 열리며, 다른 크기는 `OSError: invalid pixel size`이다. `fontTools`는 cmap 확인(`cmap_has`), `--fallback-ttf`, 요청한 코드 포인트의 유지 여부 판단,
비트맵 전용 TrueType의 스트라이크 전진 폭 읽기(`strike_advance`)에 쓰인다. `cmap_has`는 sfnt가 아닌 파일(BDF, PCF, FNT)에는 None(알 수 없음)을 돌려주므로 그런 파일도
cmap 검사에서 거부되지 않는다. 실제 로드 가능 여부는 FreeType에 달려 있다. `--chars-from`은 게임이 쓴 파일을 읽는다(아래 참고).

**출력.** 완성형 SVFN v3 페이스. 1, 2, 8 bpp이고 가변 폭(메트릭 표), 플래그 비트 2 설정, `--profile` 레이아웃이다.
v1 옵션 `--codepage`, `--count`, `--shadow`, `--center`, `--fixed`, `--fullwidth`, `--variable`은 없어졌다(argparse가 거부한다).

**사용법.** `python3 tools/mkfont.py INPUT OUTPUT --size N [options]`

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--size N` (필수) | - | 렌더링할 픽셀 크기 |
| `--cell N` | 0 (= `--size`) | 셀 높이 |
| `--width N` | 0 (= 셀 높이) | 셀 폭 |
| `--bpp {1,2,8}` | 8 | 1 스텐실, 2 네 단계, 8 커버리지 |
| `--mono-hint` | 꺼짐 | 1 bpp: FreeType 모노크롬 렌더러와 폰트의 힌팅 |
| `--latin` | 꺼짐 | Latin 기준선 규칙(ascent)을 고른다. `--fit-cell`/`--clip-cell`에서도 적용된다 |
| `--ink-advance` | 꺼짐 | 가변 폭을 폰트 메트릭이 아니라 잉크에서 가져온다 |
| `--space-advance N` | 없음 | 가변 폭: U+0020/U+00A0의 advance를 고정한다 |
| `--punct-extra N` | 0 | 가변 폭: `. , : ; ! ? ' …`에 N px를 더한다 |
| `--ascent N` | 0 (= 자동 선택) | 셀 위에서부터의 기준선 행 |
| `--fit-cell` | 꺼짐 | 모든 잉크가 셀에 들어올 때까지 크기를 줄인다 |
| `--clip-cell` | 꺼짐 | 기준선 하나를 유지하고 셀 밖의 잉크를 잘라낸다 |
| `--report FILE.json` | 없음 | 페이스 옆에 JSON 보고서를 쓴다: 글리프별 잉크 상자, 셀이 자르거나(`--clip-cell`) 밀어내는 행, 개수, 선택된 크기/ascent(어느 모드든). 셀이 통째로 잘라내는 글리프는 `gone`으로 표시된다(빌드가 버린다) |
| `--probe` | 꺼짐 | 아무것도 자르지 않는 키 큰 셀로 굽고 `--report`를 쓴다(셀 높이와 ascent는 잉크 상자에서 나온다). 255행을 넘으면 보고서만 쓴다. `--cell`, `--ascent`, `--clip-cell`, `--fit-cell`을 거부한다(종료 코드 2) |
| `--probe-cell H` | 없음 | `--probe`와 함께: 호출자의 셀 높이(1..255). 보고서의 `auto_ascent`가 `--clip-cell`이 그 셀에 대해 고를 기준선이 된다 |
| `--unicode SPEC` | "" | 코드 포인트 목록(이것 또는 `--chars-from`이 필요하다): 16진 범위, 이름 있는 세트(`ascii`, `latin1`, `hangul`, `jamo`, `cjk-punct`, `kana`, `thai`, `ksx1001`, `ksx1001-nohanja`, `ksx1001-hangul`, `ksx1001-symbols`, `cp949`, `cp949-hangul`), 또는 `file:PATH` |
| `--chars-from FILE...` | 없음 | 그 파일들이 쓰는 코드 포인트의 합집합 |
| `--limit SPEC` | "" | 결과를 이 코드 포인트 집합과 교집합한다 |
| `--only-listed` | 꺼짐 | ASCII와 U+25A1을 항상 유지하지 않는다 |
| `--fallback-ttf FILE` | "" | 주 폰트에 없는 코드 포인트를 이 TTF에서 그린다 |
| `--fail-on-drop` | 꺼짐 | `--limit`이 `--chars-from`의 문자를 버렸으면 실패한다 |
| `--require` | 꺼짐 | 요청한 코드 포인트가 폰트에 없으면 실패한다 |
| `--profile NAME` | `default` | SVFN v3 레이아웃 프로파일(이름 또는 `REC,ROW,TAB,OFF` 단위) |
| `--box x\|y\|full` | 프로파일의 값 | 글리프 레코드의 잉크 상자 정책 |

`--chars-from`은 파일 이름으로 다음 네 형식을 구분하며, 나머지 파일은 평문 UTF-8로 읽는다. `TEXT.nnn`/`text.nnn`(SCI TEXT 패치: 2바이트 헤더 뒤에 NUL로 구분된
UTF-8 문자열), `*.str`/`sci-ko.str`(`script<TAB>id[<TAB>room]<TAB>text`, UTF-8), `*.map`(hires_text INI의 `missing=`
과 `[glyphs]` 절대 코드), `*.trs`(SCUMM `SCVMTRS` 번들: 본문이 BOM으로 시작하면 UTF-8, 아니면 CP949),
그리고 그 외에는 평문 UTF-8 텍스트이다.

**내부 모듈.** `jamoset.py`(SVFN 작성과 프로파일). `bdfface.py` 등이 이 모듈을 import한다. **서드파티.** Pillow(필수),
fontTools(선택).

**테스트.** `tools/test_mkfont.py`.

### `tools/bdfface.py`

**목적.** 완성형 한글 비트맵 폰트(BDF)와 ASCII 비트맵 폰트(BDF 또는 HBF)에서 완성형 1 bpp SVF를 굽는다.
MI1/MI2 "L" 페이스용으로 작성되었으나 게임 전용은 아니다.

**상태.** 범용이다.

**입력.** 자체 정규식 BDF 리더(KS X 1001 `ENCODING` 또는 유니코드)와 HBF 리더(비트맵 파일이 옆에 있는 단일 바이트 코드
범위. gzip 가능). 한글 BDF와 ASCII BDF/HBF. `--chars-from`이 지정한 한글 음절(그래서 그것을 나열한 텍스트
파일이 필요하다), `--ascii`의 ASCII 0x20-0x7E, 그리고 자체 U+2026/U+25A1만 유지하며, `--symbols`가 없으면 어느 비트맵 페이스에서도
기호나 자모를 가져오지 않는다. `--symbols`가 있으면 `--chars-from`이 지정한 다른 문자(KS X 1001 기호, 자모, 한자)도 한글 BDF에
있는 것은 가져온다. 셀은 BDF 자체의 박스와 관계없이 기본 24x24이다. 2바이트 범위 밖의 `ENCODING`(인코딩 없는 글리프의 -1)은 건너뛴다.

**출력.** 완성형 SVFN v3 페이스. 1 bpp, 가변 폭, 플래그 5(가변 폭 + 원점의 표시). U+2026(점 셋)과 U+25A1(누락 글리프 상자)을
스스로 쓴다. `--fill-absent`가 있으면 페이스에 없는, 요청된 음절을 페이스에 맞춘 자모 조각으로 합성한다(`jamoset.fit_font`를 통해).

**사용법.**

    python3 tools/bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf|.hbf --chars-from FILE... -o OUT.SVF [options]

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--hangul FILE` (필수) | - | 한글 BDF |
| `--ascii FILE` (필수) | - | ASCII BDF 또는 HBF |
| `--cell WxH` | `24x24` | 셀 |
| `--ascent N` | ASCII 페이스의 FONT_ASCENT | ASCII 기준선의 셀 행 |
| `--hangul-ascent N` | 한글 페이스의 FONT_ASCENT | 한글 기준선의 셀 행 |
| `--chars-from FILE...` (필수) | - | 문자를 지정하는 파일(`mkfont.py` 규칙) |
| `--hangul-advance N` | BDF의 DWIDTH | 음절 advance |
| `--fill-absent` | 꺼짐 | 페이스에 없는, 요청된 음절을 합성한다 |
| `--symbols` | 꺼짐 | `--chars-from`이 지정한 다른 문자(기호, 자모, 한자)도 한글 BDF에서 가져온다. 한글 기준선에 그 DWIDTH로 놓으며, BDF의 U+2026 / U+25A1이 그려 넣는 것을 대신한다 |
| `--mask-font FILE` | `$JAMOSET_MASK_FONT` / 동봉된 NotoSansKR | `--fill-absent` 마스크 폰트(`없음` = 자유 조각) |
| `--pylib DIR` | `$JAMOSET_PYLIB` | freetype과 uharfbuzz가 있는 디렉터리 |
| `--profile NAME`, `--box x\|y\|full` | `default`, 프로파일의 값 | SVFN v3 레이아웃 프로파일과 잉크 상자 정책 |
| `-o`, `--output` (필수) | - | 출력 경로 |

**내부 모듈.** `jamoset.py`(그리고 `collect_chars_from_files`를 위한 `mkfont.py`). **서드파티.** 없음
(BDF/HBF 리더는 자체 것이다. 마스크 폰트를 쓰는 `--fill-absent`는 `jamoset.py`를 통해 freetype/uharfbuzz를 쓴다).

**테스트.** `tools/test_bdfface.py`.

### `tools/johab844.py`

**목적.** 원시 8x4x4 Johab 비트맵 폰트의 한글을 기존 16x16 1 bpp SVFN base에 넣어, base에 저장된
음절을 조각의 OR로 다시 그리고 base의 다른 글리프는 유지한다.

**상태.** 범용이다.

**입력.** 원시 8x4x4 Johab 폰트(11520바이트, 조각 360개. 자체 리더로 읽는다)와 SVFN v3 16x16 1 bpp base(`jamoset.parse_svfn`. v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`)).
`--eng`는 원시 8x16 DOS 영문 폰트(2048 또는 4096바이트)를 읽는다.

**출력.** 한글 음절이 다시 그려진 SVFN v3 형태의 base(`jamoset.pack_svfn`. 여전히 완성형 1 bpp 페이스이다). 글리프는 코드 포인트 순서로 저장된다.

**사용법.** `python3 tools/johab844.py JOHAB.KOR BASE.SVF OUTPUT [--eng ENG] [--profile NAME] [--box x|y|full]`

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--eng FILE` | 없음 | ASCII 0x21-0x7E용 원시 8x16 영문 폰트 |
| `--profile NAME`, `--box x\|y\|full` | base의 레이아웃, 프로파일의 상자 정책 | SVFN v3 레이아웃 프로파일과 잉크 상자 정책(`--profile`이 없으면 base 자체의 레이아웃을 유지한다) |

**내부 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_jamoset.py`.

### `tools/macfbit_svf.py`

**목적.** Mac HangulTalk 7.1.x type-3 'fbit' 자모 plane 폰트(Seoul12, AppleGothic12/24, AppleMyungjo12/24)를
SVF v3 자모 세트 페이스로 변환한다. 모든 KS X 1001 음절이 Mac이 그리는 그대로 나온다.

**상태.** 특수 목적(HangulTalk type-3 fbit). 사용자가 제공한 리소스를 읽는다.

**입력.** 'fbit' 리소스(글리프 슬롯 482개, 241개씩 2 bank)와 InputBackSupport 'HTBL' 1(KS 코드당 4바이트:
bank와 글리프 바이트 셋. 포맷은 `tools/macfbit3.py`와 [recipes/classic-mac.ko.md](recipes/classic-mac.ko.md#클래식-mac-hangultalk-71)에 설명되어 있다). `--latin`은
패밀리 suitcase의 리소스 포크('FOND' + 'NFNT')에서 셀의 포인트 크기로 ASCII 0x20-0x7E를 읽는다.

**방법.** Mac은 모든 Mac 슬롯이 조각 하나일 때(`slot_conflicts`) 중성(그리고 ㄱ ㄹ ㅇ 종성)을 초성에 따라 12개 초성 클래스가 허용하는 것보다 더 세밀하게
고르므로, 조각은 Mac plane의 셀 상한(cap)이다. 중성 = 셀의 Mac 중성들의 AND, 종성 = 셀의 Mac 종성들의 AND, 초성 = 각 음절의 나머지(Mac 초성에
공유 중성이 빠뜨리는 초성 고유의 획을 더한 것. 잔여 픽셀로 보고된다)이다. `search_classes`는 어떤 KS 음절도 정확하지 않게 되지 않고 잔여 픽셀이 더해지지 않는 동안(또는 개수가 12를 넘을 때까지) 초성과 종성
클래스를 병합한다.
`fit_limits`는 표에 32 / 24 / 16개보다 많은 벌이 필요할 때 개별 자모를 클래스 사이에서 옮긴다. 벌: 영역(초성
클래스 / 모음 / 종성 클래스)별로 셀의 부분 행들이 일치하는 곳에서 병합된다(`cluster`). KS 밖의 8,822개 음절은
외삽한다. 음절의 각 셀이 KS 음절을 담고 벌이 KS 데이터에서 그 자모를 확정하면 "regular", 아니면 "guess"이다(어떤 KS 음절도 닿지 않는 셀은
가장 가까운 관측 셀의 벌을 취하고, 벌에 없는 자모는 가장 가까운 문맥의 평범한 Mac 글리프로 채운다). 외삽된 음절은 Mac의 출력이 아니다.

**direct 모드(기본, `--mode direct`).** 외삽 없이 Mac의 구조 자체를 쓴다. 조각이 Mac 슬롯인 JMAP 블록(JSET 버전 3,
명세 [SVF 명세](../spec/SVF.ko.md)의 "자모 세트 폰트 (플래그 비트 1)")이다(`direct_jmap`). plane별로 슬롯 순서대로(초성, 중성, 종성.
두 plane에서 참조되는 슬롯은 거부된다), `--no-dedup`이 아니면 한 plane의 바이트 단위로 같은 비트맵은 하나로 접히고(plane을 가로지르지는 않는다),
KS 음절마다 항목이 하나(필드 = plane 안의 조각, 0 = plane 없음)이며, 한 plane짜리 호환 자모는 자기 종류 plane의 조각으로, plane이 둘 이상인 호환 자모는 U+3131 + k에 통째로 저장된다.
2,350개 KS 음절과 51개 호환 자모만 합성된다(다른 음절은 단순한 누락 글리프이다). `--with-jset`은 위와 같이 외삽된
JSET도 도출해(`--classes` 또는 탐색) JMAP 폴백으로 저장하므로(`--jset-version`이 여기에 적용되고, 조각은
JMAP의 것보다 위에 번호가 매겨지며 호환 항목은 비어 있다) 11,172개 전부가 합성된다(실제 Mac 페이스에 대한 `--with-jset`의 크기는 측정되지 않았다). JMAP 블록(폴백 포함)은
65,534바이트 이내여야 한다. `--mode derived`는 위 방법 절의 외삽된 페이스를 쓰며, direct 모드 이전에 도구가 쓰던 것과
바이트 단위로 같다. `verify`는 모드를 페이스에서 가져오며(direct 페이스는 `--classes`가 필요 없다) Python에서, 그리고 `--svfdump`가 있으면 C 리더에서(`-DSVF_JMAP=1`로 빌드) `macfbit3.Fbit3(fbit, htbl).compose`의 모든 코드(2,350 + 51)를 비교한다. `build`의 보고서에는 `mode`, `jmap`(블록 바이트),
`pieces`(plane 조각), `fallback_pieces`, `pieces_as_slots`(참조된 Mac 슬롯당 plane 조각 하나), `fallback`
(바이트)이 추가된다. `verify_direct`는 LIST 페이스를 거부하며(`verify: a LIST face (JSET version 3 flag 0x08) is not a direct-mode face`. 여기의 빌더는 plane 전용이다) `non_ks_present`(페이스에 조각이 있는 KS 밖 음절)를 보고하고, C 검사는
`non_ks_ink`(셀에 잉크가 있는 것들)를 보고한다. `--sheets` / `--name`은 `--mode derived`에 속하며 direct는 이를 거부한다.

**실제 입력을 사용하는 선택적 테스트.** `tools/test_macfbit_svf.py`의 `RealFaces` 클래스는 `SVF_MAC71_INPUTS`가 `Seoul12`, `AppleGothic12`, `AppleGothic24`, `AppleMyungjo12`, `AppleMyungjo24`를 `<Name>.fbit`(디코딩된
'fbit' 리소스)와 `<Name>.htbl1`(InputBackSupport 'HTBL' 1. 모든 페이스에 같은 파일)로 담은 디렉터리를 가리킬 때 다섯 페이스를 실행한다. 직접 디코딩한 리소스로 채운다. 각
폰트의 리소스 포크에서 'fbit' 리소스(`python3 tools/macfbit3.py fbit FORK OUT`)와 InputBackSupport의 'HTBL' 1 리소스를 쓴다.

```sh
DST=/path/to/mac71-inputs; mkdir -p "$DST"
for n in Seoul12 AppleGothic12 AppleGothic24 AppleMyungjo12 AppleMyungjo24; do
  python3 tools/macfbit3.py fbit "/path/to/forks/$n.rsrc" "$DST/$n.fbit"; cp /path/to/HTBL1.bin "$DST/$n.htbl1"; done
SVF_MAC71_INPUTS=$DST python3 -m unittest tools.test_macfbit_svf.RealFaces
```

**출력.** SVFN v3, 1 bpp, 셀 h x h(12 또는 24), ascent h - h/6, JSET 플래그. 조각은 U+F0000 + n에 있다. 호환
자모는 Mac 글리프가 자기 자연 표의 조각이면 호환 조각으로, 아니면 통째로 저장된다. Latin은
글리프별 dy를 가진다(셀보다 넓은 글리프는 셀 안으로 밀어 넣으며, 기록된다). `--report`는 JSON(클래스, 벌, JSET v1과 v2의 크기,
외삽 개수, 검증)을 쓴다. `--sheets`는 PNG 시트(Mac 대 페이스 대 XOR, KS 1x/3x,
외삽 샘플, 조각. PIL 필요)를 쓴다.

**사용법.**
`python3 tools/macfbit_svf.py analyse FBIT HTBL1 [-o OUT.json]`
`python3 tools/macfbit_svf.py build FBIT HTBL1 -o FACE.SVF [--mode direct|derived] [--no-dedup] [--with-jset] [--classes OUT.json] [--latin SUITCASE.rsrc] [--latin-size N] [--report R.json] [--sheets DIR] [--name P] [--jset-version 1|2|auto] [--jset-big]`
`python3 tools/macfbit_svf.py verify FACE.SVF FBIT HTBL1 [--classes OUT.json] [--svfdump PATH ...]`

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--mode direct\|derived` | direct | Mac 구조의 JMAP 페이스(KS만), 또는 외삽된 JSET 페이스 |
| `--no-dedup` | 중복 제거 켜짐 | direct: plane의 서로 다른 비트맵마다 하나가 아니라 Mac 슬롯마다 조각 하나 |
| `--with-jset` | 꺼짐 | direct: 도출된 JSET이 JMAP 폴백이 된다(11,172개 음절 전부 합성된다) |
| `--classes FILE` | 탐색 | `analyse` JSON의 `lc` / `tc`를 쓴다(derived, `--with-jset`, derived 페이스의 verify) |
| `--latin FILE`, `--latin-size N` | 없음, 셀 크기 | 패밀리의 'NFNT' 스트라이크에서 가져오는 ASCII |
| `--jset-version 1\|2\|auto` | 1 | JSET 블록 버전(`jamoset.pack_jset`. direct: `--with-jset` 폴백의 것. auto = `jamoset.choose_jset_version`) |
| `--jset-big` | 꺼짐 | derived와 `--with-jset`: 19 x 28 클래스까지 탐색하고 128 / 128 / 64 벌에 맞춘다. JSET은 `big=True`로 쓰인다 |
| `--svfdump PATH` | 없음 | C 렌더러의 음절도 함께 비교한다(`c/tests/svfdump.c`). 반복 가능 |

`analyse`와 `build`의 `-o`는 `--out`으로도 지정할 수 있다.

**내부 모듈.** `jamoset`, `macfbit3`. **서드파티.** `--sheets`에만 PIL. **테스트.** `tools/test_macfbit_svf.py`(합성 fbit / HTBL / NFNT 픽스처).


### `tools/jamovec.py`

**목적.** 폰트의 자모를 아웃라인으로 한 번 분리해 마스터 JSON에 담고, 이후 어떤 크기든 다시 맞추지 않고 그것에서
렌더링한다.

**상태.** 범용이다.

**입력.** `master`는 fontTools(`jamoaa.OutlineFace`를 통해)로 TTF/OTF를 읽는다(`--components`는 `glyf`
합성 컴포넌트를 읽는다). `render`는 마스터 JSON을 읽는다.

**출력.** `master`는 JSON 마스터를 쓰고, `render`는 1 또는 2 bpp의 SVFN v3 자모 세트 페이스를 쓴다.

**사용법.**

    python3 tools/jamovec.py master FONT -o MASTER.json [options]
    python3 tools/jamovec.py render MASTER.json --size N -o OUT.SVF [options]

`master` 옵션: `-o`/`--output`(필수), `--adaptive [NI,NM,NF]`(없음. 상수 `32,24,12`),
`--decision-px N`(48), `--class-limit N`(12, 엔진의 한계), `--components`(꺼짐), `--pylib DIR`(없음).
`render` 옵션: `--size N`(필수), `--bpp {1,2}`(2), `--binarize {threshold,ridge}`(threshold),
`--cell WxH`(없음), `--baseline N`(없음), `--symbols`(꺼짐), `--check`(꺼짐), `--profile NAME`(`default`),
`--box x|y|full`(프로파일의 값), `--jset-version 1|2|auto`(1), `--jset-big`(꺼짐), `-o`/`--output`(필수).

**내부 모듈.** `jamoaa.py`, `jamoset.py`, `jamoadapt.py`, `jamofit.py`. **서드파티.** fontTools
(`master`에 필수. 래스터라이저는 자체 것이다).

**테스트.** `tools/test_jamoaa.py`.

### `tools/svfdy.py`

**목적.** 기존 SVFN 페이스의 글리프별 dy를 설정하거나 지운다. `jamoset.parse_svfn`으로 읽고 `jamoset.pack_svfn`으로 v3로 다시 쓰므로, 모든 글리프, 메트릭, JSET 블록, 플래그는 유지되고 dy 필드만 바뀐다(글리프는 `--profile` 레이아웃에서 코드 포인트 순서로 끝난다).

**상태.** 범용이다.

**입력.** 메트릭 표가 있는 SVFN v3 페이스. `jamoset.py`로 읽는다(v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`)). `--json`은 코드 포인트를
dy에 대응시킨 JSON 객체를 읽는다.

**출력.** dy 바이트와 헤더 범위가 바뀐 v3 페이스(입력과 같은 종류, bpp, 픽셀).

**사용법.**

    python3 tools/svfdy.py INPUT [OUTPUT] [--range CPS --dy N] [--set CPS=N]... [--json FILE] [--clear] [--show] [--profile NAME] [--box x|y|full]

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--range CPS` | 없음 | `--dy`를 줄 코드 포인트(예: `0x20-0x7e,0x2026`) |
| `--dy N` | 없음 | `--range`의 dy |
| `--set CPS=DY` | 없음 (repeatable) | 코드 포인트와 그 dy |
| `--json FILE` | 없음 | JSON 객체 `{code point: dy}` |
| `--clear` | 꺼짐 | 먼저 모든 글리프의 dy를 0으로 한다 |
| `--show` | 꺼짐 | 범위와 dy가 있는 글리프를 출력한다(출력 파일은 필요 없다) |
| `--profile NAME`, `--box x\|y\|full` | 입력의 레이아웃, 프로파일의 상자 정책 | 출력의 SVFN v3 레이아웃 프로파일과 잉크 상자 정책(`--profile`이 없으면 입력 자체의 레이아웃을 유지한다) |

자모 조각(`U+F0000..`)에 dy를 주는 것은 거부된다. 폰트에 없는 코드 포인트는 세어서 건너뛴다.

**내부 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_jamoset.py`.

### `tools/svfscale.py`

**목적.** 비트맵 페이스를 더 작은 픽셀 크기로 그린다(40 / 48 px DOS나 프린터 페이스, 24 px BDF를 16 px로). 1 bpp는 임계값으로, 2 bpp는
커버리지를 네 단계로 양자화한다. 비트맵 축소로 중간 커버리지를 만든다.

**상태.** 범용이다.

**입력.** 1 bpp SVFN v3 페이스(완성형 또는 자모 세트: 모든 글리프를 `svfline.py`로 그리므로 자모 세트의 음절은 먼저 조합된다) 또는
BDF(`bdfface.read_bdf`: KS X 1001 또는 유니코드 인코딩).

**출력.** 셀이 `round(W x h / H)` x `h`인 완성형 SVFN v3 페이스(가변 폭. 플래그 비트 2, 원점의 표시는 원본 SVF에 있을 때만: 없으면 음수 bearing_x는 표시의 원점이
아니다). 높이(ascent, 글리프별 dy)는 h / H, 너비(전진 폭, 결합 부호의 음수
bearing_x)는 w / W로 비례해 반올림한다(w = `round(W x h / H)`). 글리프마다 자기 비트맵(`svfline.Face.coverage`: dy 이동도 부호 원점도
없고 잘리지도 않는다)에서 다시 샘플링한다. 출력 픽셀은 원본 영역 중 잉크가 차지한 정확한 비율이다. 1 bpp는 비율 >= `--threshold`
(0 < threshold <= 1)를 남기고, 2 bpp는 비율을 0..255의 커버리지 c로 반올림한 뒤 `(c x 3 + 127) // 255`를 저장한다(mkfont의 규칙).
64 MiB를 넘는 원본은 거부한다. `--compare`는 두 페이스를 한 기준선에, 모든 글리프의 dy까지 담는 화면에 그린다.

**사용법.** `python3 tools/svfscale.py SRC --size H [--bpp 1|2] [--threshold 0.5] [--chars ks|face|all|FILE] [--compare FACE.SVF] [--profile NAME] -o OUT.SVF`

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--size H` | 필수 | 새 셀 높이(원본보다 작게) |
| `--bpp 1\|2` | 1 | 임계값 또는 네 단계 |
| `--threshold F` | 0.5 | 1 bpp: 픽셀을 남기는 잉크 비율 |
| `--chars` | `ks` | `ks`: ASCII 0x20-0x7E, KS X 1001 음절 2,350개, 원본의 다른 코드 포인트(평면 15에 있는 자모 세트의 조각은 빼고). `face`: 원본이 나열하는 것. `all`: 11,172 음절 전부와 함께. 또는 문자 파일 |
| `--compare FACE.SVF` | 없음 | 1 bpp 결과를 쓴 뒤, 다른 1 bpp 페이스와의 겹침(둘 다 그리는 KS 음절의 평균 IoU, 두 페이스를 한 기준선에, 2 px 안의 가장 좋은 이동)을 출력 |
| `--profile NAME`, `--box x\|y\|full` | `default`, 프로파일의 값 | v3 레이아웃 프로파일과 잉크 상자 정책 |

메시지와 함께 종료 코드 1(1 bpp가 아님, `--size`가 1보다 작거나 원본보다 작지 않음, (0, 1] 밖의 임계값, `--bpp 2`와 `--compare`,
`bdfface.py`가 읽지 못하는 BDF). **내부 모듈.** `jamoset.py`, `svfline.py`,
`bdfface.py`. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(합성 32 px BDF를 16 px로 줄인 박스 필터 단계, 48에서 16 px로의 2 bpp 단계 규칙, 반올림한 ascent와 비례한 전진 폭과 dy가 있는
24에서 16 px, 너비 29 셀에서 w / W로 줄인 전진 폭과 부호의 bearing_x, ascent가 다른 페이스와 dy가 셀 아래로 미는 잉크의 겹침).

### `tools/svf2to3.py`

**목적.** SVFN v2 페이스를 v3로 변환하고, v3 페이스를 다른 프로파일로 다시 레이아웃하며, 픽셀, 메트릭,
합성된 음절이 하나도 바뀌지 않았다는 증명을 함께 낸다.

**상태.** 범용이다. 다른 모든 작성기는 v3만 쓰고, `jamoset.parse_svfn`은 v3만 읽는다(v2 페이스는 이 도구를 지목하는 변환 안내 메시지와 함께 거부된다). v2 파서는 `svf2to3.py`에만 있다.

**입력.** SVFN v2 또는 v3 페이스. 또는 `--tree`로 `*.SVF`(대소문자 무관)를 재귀적으로 찾는 폴더.

**출력.** `jamoset.pack_svfn`이 쓴 v3 페이스. `--tree`이면 DST 아래의 같은 상대 경로(SRC가 DST와 같을 수
있다. 다른 파일은 복사하지 않는다). 각 페이스는 대상 옆의 임시 파일에 쓰이고, `--check`가 주어지면 거기서 검사한 뒤
검사를 통과했을 때만 대상 위로 이름을 바꾼다.

**JSET 버전.** `--jset-version`의 기본은 1이다(v2는 메모리가 제한된 대상 전용). v1 블록은 v1으로 남고 v2 블록은 v1으로 쓰인다. `2`는 v2를 쓰고, `auto`는 1024 B 이상 작을 때 v2를 쓴다. 단, 입력 블록이 이미 v2이면 `2`와 `auto` 모두 그 바이트를 유지한다. `--jset-big`은 다시 인코딩되거나 그대로 복사되는 블록(v2 블록, 또는 JMAP 영역의 폴백)이 표준 한계를 넘는 것을 허용한다. `--check`는 파서가 자모 세트를 거부한 페이스를 `composed=unchecked`로 보고한다. JMAP 영역(JSET 버전 3)은 그대로 복사된다(출력의 영역 바이트가 입력과, 조각 번호까지 모두 같다). `--jset-version`은 거기에 아무것도 적용되지 않으며 stderr의 메모가 그렇게 알린다. `--check`는 `svfline.py`를 통해 두 페이스를 모두 합성하며(JMAP에만 있는 누락은 합성되지 않는다: 일반 페이스처럼 cmap 글리프이거나 없음) 출력 줄은 `jset=3 jmap=BYTES`로 읽힌다(LIST 영역, 플래그 0x08은 같은 방식으로 복사되고 다시 인코딩되지 않으며 ` list=1`이 더 붙는다). 같은 해석이 `svfline.py`, `maker/detect.py`(종류 `svf-jamo`, `jset_version` 3, `jmap_mode` `dense` / `sparse` / `list`. plane 조각, 폴백 조각, 호환이 모두 글리프를 가질 때만 사용 가능. `maker/quality.py`의 `face_facts`는 LIST에 대해 `pool`을 보고한다: LIST 블록 자체가 지명하는 서로 다른 조각의 수로, 그 항목과 자체 호환 항목을 센 것이며 폴백의 것은 아니다), `web/mkindex.py`(그런 페이스에 `jamo`가 true)에도 적용된다.

**사용법.**

    python3 -I tools/svf2to3.py IN OUT [--profile P | --units R,W,T,O] [--box x|y|full] [--jset-version 1|2|auto] [--jset-big] [--check]
    python3 -I tools/svf2to3.py --tree SRC DST [same options]

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--profile P` | `default` | 아래 표의 작성기 프리셋 |
| `--units R,W,T,O` | 없음 | 레코드, 행, 표 단위의 log2와 오프셋 폭 16 또는 32(박스 `x`) |
| `--box B` | 프로파일의 값 | 박스 정책: `x`(x-boxed), `y`, `full`(전체 셀) |
| `--check` | 꺼짐 | 출력을 입력과 `svfline.Face`로 비교한다: 모든 코드 포인트의 has, 메트릭, 셀과 합성된 모든 음절(U+AC00..U+D7A3, U+3131..U+3163) |
| `--tree` | 꺼짐 | 폴더를 변환한다. 페이스마다 `REL in= out= data_in= data_out=`를 출력하고 마지막에 `total faces= ... data_out= v3_faces= v3_jset= v1_faces= ... failed=` 줄을 출력한다(`v3_*`: JMAP 페이스와 그 영역 바이트. LIST 영역은 다른 버전 3 블록처럼 그대로 복사되며 그 줄에 ` list=1`을 더한다: ` jset=3 jmap=BYTES list=1`) |

| 프로파일 | REC / ROW / TAB (log2) | 상자 | 오프셋 |
|---|---|---|---|
| `mcu-strict` | 4 / 1 / 4 bytes (2 / 0 / 2) | x | u16, u32 when the data passes `65535 << REC` |
| `default` | 4 / 1 / 4 bytes | x | u32 |
| `dos` | 1 / 1 / 1 bytes | x | u16, u32 past 64 KB |
| `wasm` | 1 / 1 / 1 bytes | x | u16, u32 past 64 KB |
| `full` | 4 / 1 / 4 bytes | 전체 셀 | u32 |
| `simd16` | 16 / 1 / 16 bytes | x | u32 |

종료 상태: 0은 모든 페이스 통과, 1은 검사 차이(처음 다른 코드 포인트나 marks-at-origin 플래그를 지목한다), 2는 읽을 수 없거나 잘못된 입력, 디렉터리가 아닌 SRC, 읽을 수 없는 하위 디렉터리이다. 실패한
페이스는 대상을 건드리지 않고 두며 실행은 계속된다. 마지막 줄의 `faces=`, `in=`, `out=`, `data_in=`, `data_out=`는
변환된 페이스만 센다. `failed=`는 나머지를 센다. SIGTERM은 종료 전에 임시 파일을 제거한다.

**내부 모듈.** `jamoset.py`, `svfline.py`. **서드파티.** 없음. **테스트.** `tools/test_svf2to3.py`
(픽스처는 `tools/testdata/v2/`).

### `tools/svf2ttf.py`

**목적.** 완성형이든 자모 세트든 SVF 페이스를 비트맵 폰트로 되돌린다: TrueType 폰트(픽셀 아웃라인과 내장 비트맵 스트라이크; 참고 문헌 5–8)나
BDF(참고 문헌 11). 그리고 두 페이스를 글리프마다 비교한다(왕복 점검).

**상태.** 범용이다.

**입력.** SVFN v3 페이스. C 라이브러리가 읽는 방식(`svfline.Face`)으로 읽는다: 글리프(자모 세트의 U+F0000..U+FFFFF 조각은 빼고, 완성형
페이스의 사용자 정의 영역 글리프는 지킨다. 서로게이트와 U+FFFF는 내보내지 않는다)와, 자모 세트라면 그 표가 주는 모든 음절과 호환
자모(`jamoset.compose`로 합성). 내보낼 것이 없는 페이스는 오류이다. `--licence`가 지정하지 않으면 페이스 옆의 라이선스 노트(출력 참고).

**출력.**

- `ttf`: `unitsPerEm` = ppem x 64인 TrueType 폰트(ppem의 기본은 셀 높이). `glyf`: 각 글리프에서 커버리지가 `--threshold`(기본
  128: 1 bpp는 모든 픽셀, 2 bpp는 단계 2와 3) 이상인 픽셀을 윤곽선으로 추적한 것. ppem과 그 정수배에서 정확하며 힌팅은 없다(no-op 하나의
  `prep`이 FreeType의 자동 힌팅을 막아 다른 크기의 아웃라인은 FreeType의 래스터라이저로 그려진다).
  `EBLC`/`EBDT`: 페이스의 비트 깊이(1, 2, 8)로 ppem의 스트라이크 하나(이미지 형식 1, 인덱스 형식 1). 각 글리프는 잉크 상자로
  잘리고 bearing과 advance를 가진다(부호 있는 바이트: -128..127을 넘는 ascent, descent, 글리프의 bearing x나 잉크 위끝, 스트라이크 전체의 최소 side bearing이나 잉크 극값은 그 필드를 밝히고 `--no-strike`를
  권하는 오류. 단 127을 넘는 최소 오른쪽 side bearing은 127로 저장한다. `--no-strike`는 스트라이크를 빼고, `--apple`은 `bloc`/`bdat`으로도 쓴다). 글리프는 65,534개까지. `cmap`(4, U+FFFF를 넘으면 12),
  `hmtx`(페이스의 advance. 결합 부호는 `svfline.py`가 놓는 대로 원점에 advance 0), `hhea` / OS/2 typo 메트릭 = ascent와 셀 높이 -
  ascent, dy가 옮긴 잉크까지 덮는 OS/2 win 메트릭, `post` 형식 3, `head`, `maxp`, `gasp`, `name`(패밀리, 스타일, 버전, 페이스를
  밝히는 설명, 그리고 라이선스: `svf/`의 페이스는 `web/LICENCES.tsv`의 해당 행이 지명하는 파일(`svf/` 아래에서 행이 없는
  페이스는 `--licence`가 없으면 오류), 그 밖에는 페이스 옆에서 제목 줄이 그 파일 이름이나 그에 맞는 패턴을 적은 `*.TXT`와 그것이
  이름을 든 라이선스 파일, 없으면 옆 `FACES.TSV`의 licence 열. 이를 name 13으로. OFL 파일 머리 위의 저작권 문단은 name 0, OFL
  URL은 OFL 텍스트가 들어갈 때만 name 14).
  GSUB, GPOS, 첫가끝 자모 셰이핑은 없다: 출력은 완성형이다. 타임스탬프는 `$SOURCE_DATE_EPOCH`가 있으면 그 값. `--composite`(자모
  세트): 자모 조각마다 글리프 하나, 음절마다 그 조각들의 `glyf` 합성 글리프(`OVERLAP_COMPOUND`)와 `EBDT` 복합 비트맵(이미지 형식 8, 별도 인덱스
  하위 테이블). 호환 자모는 조각 글리프를 가리킨다. 2와 8 bpp: 조각 비트맵은 펜에서 시작하고, 조각들이 OR가 최댓값이 아닌 단계로 겹치는 음절은 펼친 비트맵을 유지한다(FreeType은 복합 구성요소를 OR한다).
  구성요소 오프셋이 부호 있는 바이트를 넘을 음절(128 px를 넘는 셀)도 그렇다. 요약 줄이 그 수를 센다.
- `bdf`: BDF 2.1(1 bpp) 또는 2.3(2 / 8 bpp: 비트 깊이를 `SIZE`의 네 번째 필드에. `--bpp1`은 1 bpp로 자른다), ISO10646-1,
  글리프마다 잉크 상자(BBX)와 advance(DWIDTH), `FONT_ASCENT` / `FONT_DESCENT`는 페이스의 값, 72 dpi(`SIZE ppem 72 72`,
  `POINT_SIZE`는 ppem x 10, `SWIDTH`는 advance x 1000 / ppem), `AVERAGE_WIDTH`, 라이선스 노트는 `COMMENT` 줄, 저작권은 `COPYRIGHT`, UTF-8로.
- `compare`: 한 줄 `compared N glyphs: mismatches M (pixels P, advance A, inked only in A X, only in B Y); blank glyphs only
  one face has Z`와, 이어서 처음 다른 코드 포인트들. 글리프는 `svfline.py`가 놓는 대로 놓는다(펜과 기준선에 대한 픽셀의
  커버리지, 그리고 advance). 한쪽에만 있는 빈 글리프는 따로 세지만 U+0020, U+00A0, U+3000은 불일치이다.
- `cps`: 페이스의 코드 포인트를 `mkfont.py --unicode` 범위로.

**사용법.**

    python3 tools/svf2ttf.py ttf FACE.SVF OUT.ttf [--family F] [--style S] [--version V] [--ppem N] [--threshold C]
                                                  [--licence FILE|없음] [--no-strike] [--apple] [--composite]
    python3 tools/svf2ttf.py bdf FACE.SVF OUT.bdf [--family F] [--style S] [--version V] [--ppem N] [--threshold C]
                                                  [--licence FILE|없음] [--bpp1]
    python3 tools/svf2ttf.py compare A.SVF B.SVF
    python3 tools/svf2ttf.py cps FACE.SVF

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--family F` | `<FACE STEM> SVF` | 패밀리 이름(기본값은 원본 폰트의 이름을 되풀이하지 않는다: OFL의 Reserved Font Name이 이를 금할 수 있다) |
| `--style S` | `Regular` | 스타일 이름. "Bold" / "Italic" / "Oblique"에 따라 OS/2와 `head`의 스타일 비트를 설정한다. 굵기는 Bold일 때 700, 그 외에는 400 |
| `--version V` | `1.000` | name 5. 숫자 형식이면 `head.fontRevision`도 그 값, 그 외에는 1.0 |
| `--ppem N` | 셀 높이 | 스트라이크의 크기이자 em(1..255) |
| `--threshold C` | 128 (1..255) | 아웃라인(과 `--bpp1` BDF)에 들어갈 픽셀의 커버리지 |
| `--licence FILE\|없음` | 페이스 옆의 노트 | 넣을 라이선스 노트. `없음`은 넣지 않는다 |
| `--no-strike` (ttf) | 꺼짐 | 아웃라인만 |
| `--apple` (ttf) | 꺼짐 | 스트라이크를 `bloc`/`bdat`으로도 쓴다 |
| `--composite` (ttf) | 꺼짐 | 자모 세트: 조각은 한 번, 음절은 합성 글리프(glyf 합성, EBDT 형식 8). 완성형 페이스에는 안내만 찍고 그대로 |
| `--bpp1` (bdf) | 꺼짐 | 2 또는 8 bpp 페이스를 1 bpp BDF로 |

종료 상태: 0. 1은 읽을 수 없는 페이스(모든 하위 명령), 범위를 벗어난 값(1..255 밖의 `--ppem`, 스트라이크 필드), 내보낼 것이 없는 페이스(`compare`: 불일치가 있으면 1). 2는 사용법 오류. `svf/` 아래에서
`web/LICENCES.tsv`가 다루지 않는 페이스는 `--licence`가 없으면 1로 끝난다. 그 밖에서 옆에 라이선스 노트가 없는 페이스는 경고를
찍고, 원본 폰트의 라이선스가 적용된다는 한 줄을 받는다.

왕복 점검과 여섯 페이스(완성형과 자모 세트, 1과 2 bpp, 16과 24 px, HWP 1.x 페이스)의 결과:
[recipes/svf-and-ttf.ko.md, SVF 페이스를 다시 TTF 비트맵 폰트로](recipes/svf-and-ttf.ko.md#svf-페이스를-다시-ttf-비트맵-폰트로). 자모 세트 여섯의
`--composite`(크기, 펼친 비트맵, 한계): [합성 글리프](recipes/svf-and-ttf.ko.md#합성-글리프--composite).

**내부 모듈.** `jamoset.py`, `svfline.py`. **서드파티.** fontTools(`ttf`). **테스트.** `tools/test_svf2ttf.py`(`svf/`의
페이스로: 글리프 집합과 합성 수, 메트릭과 이름, 페이스와 대조한 스트라이크, 2비트 스트라이크, 1 x, 1.5 x(힌팅 없음), 2 x의 FreeType 렌더, 스트라이크가
있을 때와 없을 때의 `mkfont.py` 왕복, dy, BDF. `--composite`: 구성요소 수와 오프셋, `maxp`, FreeType처럼 풀어 본 복합 스트라이크, 2 bpp의
펼친 비트맵 집합, 렌더, 2 bpp 왕복, fontTools 재컴파일, 완성형에서의 no-op).

### `tools/svf_synth.py`

**목적.** `jamoset.write_svfn`으로 만든, C 렌더러 테스트용 합성 SVFN 페이스를 쓴다.

**상태.** 테스트/지원 전용.

**입력.** `--marks`를 뺀 모든 종류에서 `--from`은 유효한 자모 세트 페이스이다.

**출력.** 합성 SVFN 페이스: 깨진 JSET 블록(잘못된 종류 하나)을 가진 자모 세트, JMAP(JSET
버전 3) 블록을 가진 유효한 페이스 또는 깨진 것, 8 bpp 페이스, 또는 16 px 1 bpp 플래그 비트 2 marks 페이스.

**사용법.** `python3 tools/svf_synth.py (--jset-bad KIND | --reencode | --jset-variant V | --jmap-variant V | --jmap-bad KIND |
--jset-unused-finset | --jset-cut N | --bpp8 | --marks | --layout-bad KIND) [--from FACE] [--jset-version 1|2] OUT`

`--jset-version`은 쓰이는 모든 JSET의 JSET 블록 버전이며, 동봉된 작성기와 달리 **기본값이 2**이다.
이것은 테스트 도구이고 대부분의 경우가 버전 2 리더와 그 거부를 테스트하기 때문이다. `--jset-bad KIND`는 블록의
규칙 하나를 깨뜨린다. 버전 2 종류는 `lc13`, `tc13`, `ni33`, `nm25`, `nf17`, `length`, `leadclass`, `finset`,
`initset`, `missing_piece`, `magic`, `version`, `version4`, `short`, `na_over`, `reserved`, `pad_bits`,
`alias_no_presence`, `abase_over`, `alias_blank`, `missing_alias_piece`, `base_wrap`, `compat_set_over`,
`compat_slot_blank`, `compat_bits56`과 `compat_*_bit7` 종류이다. `--jset-version 1`이면 버전 1 종류는
`lc13`, `tc13`, `ni33`, `nm25`, `nf17`, `length`, `leadclass`, `finset`, `missing_piece`, `magic`, `version`, `short`이다.
다섯 개 개수 종류 `lc13` ... `nf17`(`BAD_KINDS_STD`)은 좁은 리더에게만 잘못된 것이다. BIG 리더와
`jamoset.unpack`은 이를 유효한 표로 읽는다. BIG 종류 `lc20`, `tc29`, `ni129`, `nm129`, `nf65`(`BAD_KINDS_BIG`,
두 버전 모두)는 BIG 상한 하나씩을 하나 넘는 것이며 모든 리더가 거부한다
(`python3 tools/svf_synth.py --help`와 모듈 docstring이 각각을 설명한다). `--reencode`는 FACE의 JSET 블록을
`--jset-version`으로 다시 쓴다(1: `pack_v1`, 조각 번호 유지. 2: `pack`, 조각 번호 재부여). `--jset-variant V`는 다른 모양의
유효한 버전 2 블록(`alias`, `bit7`, `overlap`, `limits`, `w0`. 버전 2만)을, 또는 BIG
리더용으로 `limits_big`(19 x 28 클래스, 128/128/64 벌, 별칭 없음: 버전 2에서 29,708 B, `--jset-version 1`이면 47,373 B)과 `limits_big_alias`(같되 모든 슬롯이 별칭. 45,068 B. 버전 2만)를 쓰며, 각각 모든 조각에
글리프가 있다.
`--jmap-variant V`는 `jamoset.jmap_from_tables`로 FACE의 표에서 만든 유효한 JSET 버전 3(JMAP) 블록을 쓴다
(`sparse3`, `sparse4`, `dense3`, `dense4`, `hybrid1`, `hybrid2`(버전 1 또는 2 폴백 위에 16개 예외 음절), `dhybrid1` / `dhybrid2`(dense, 3 / 4바이트 항목, 버전 1 / 2 폴백 위: 34 / 45 KB 영역), `hybrid_big1`, `hybrid_big2`(BIG 폴백), `adv0`, `adv0fb`(JMAP과 그 버전 1 폴백의 advance가 0), `sparse_full`(11,172개 항목 전부를 가진 SPARSE 플래그. `pack_jmap`은 그 개수를 dense로 쓰므로 손으로 조립했다), `blanks`, `pi2047`). `--jmap-bad KIND`는 JMAP 규칙 하나를 깨뜨린다(23개의 `JMAP_BAD_KINDS`. 각각의 규칙은 모듈
docstring이 알려 준다. `jmap_missing_piece`와 `jmap_region_max`는 블록은 유효하되 리더에서 조각 글리프
규칙과 65,534바이트 영역 상한에 실패한다. `v2_as_v3`는 그 필드가 처음 깨뜨리는 규칙이며 NEODG16G에서는 R3이다).
LIST 변형과 종류는 별도의 목록이다(`LIST_VARIANTS`, `LIST_BAD_KINDS`. `JMAP_VARIANTS`와 `JMAP_BAD_KINDS`는 15개와 23개 이름을 유지하며 `--jmap-variant` / `--jmap-bad`는 둘 다 받는다). `--jmap-variant list1`(38개 항목, s = 0, 300, ..., 11,100: 폴백 자체와 다른 온전한 셀과 재조합. 원본 자신의 폴백 버전을 advance 16으로 다시 인코딩한 것 위), `list2`(버전 2 폴백, 조각 번호 5, 3, 9, ... 재부여), `list_nofb`(항목 하나, 폴백 없음), `list_blank`, `list_zero`, `list_compat`, `list_max`(255개 항목, 키 0과 11,171, 폴백 없음, 2,158바이트), `list_big`(`limits_big` 표 위). `--jmap-bad`는 22개의 `jlist_*` 종류를 받는다. `list1`의 바이트 편집(`jlist_short_nofb`, `list_nofb`의 `jlist_length`)이며 각각 `unpack_jmap`의 규칙 하나(R1, L2, L3, R4, L6. 모듈 docstring이 이름을 알려 준다)를 깨뜨린다. 단 `jlist_field_noglyph`, `jlist_field_fffe`, `jlist_compat_noglyph`(`parse_svfn`이 페이스를 나쁜 것으로 표시한다)와 `jlist_region_max`(헤더 JSET 크기 0x10000)는 예외이다.
둘 다 `--jset-version`을 무시하고, JSET 표가 있는 FACE(그 자체로 JMAP 페이스는 아님)가 필요하며, 조각 글리프의 dy를 버린다(plane은
dy 없이 쓰인다). 3바이트 종류는 4바이트 블록을 주는 FACE를, 4바이트 종류는 3바이트 블록을 주는 FACE를 거부한다(명확한 오류).
`sparse4`/`dense4`는 세 plane 모두를 255 너머까지 패딩하고 패딩된 조각을 인덱스 256부터 지명한다.
`pi2047`은 손으로 만든다. `hybrid1`은 JMAP 호환 항목 하나를 비워 폴백이 답하게 한다. `--from FACE`는 `--marks`를 뺀 모든 종류에 필요하다. `--profile P` / `--units R,W,T,O`와 `--box`는
v3 레이아웃을 고른다(기본: `default` 프로파일. `--layout-bad`와는 함께 쓸 수 없다). 기본 출력 경로는 없다.

**내부 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_c_renderer.py`.

### `tools/jamofill.py`

**목적.** 비트맵 레퍼런스 자신의 크기로 작은 자모 세트 페이스를 만든다. 벌 골격(클래스, 벌 표,
선택적으로 어느 슬롯이 조각을 공유하는지)을 유지하고 모든 조각을 레퍼런스의 음절에서 가져온다. 바이트
예산 안에서 12 px 페이스를 만들 때 쓴다.

**상태.** 연구용 빌더.

**입력.** `--strike` 비트맵 조사 스트라이크(`NAME-PX.npz`: `cp`, `glyphs`, `meta`, 선택적인 `adv`. numpy 없이 읽는다). `--skeleton`은 `FACE.SVF`(그 클래스와 벌 표. 모든 슬롯이 각자의 조각), `FACE.SVF:tied`(그 공유도 함께: 조각이 하나의 비트맵인 슬롯은 하나의 조각으로 남는다), 또는 이름 있는 구조이다. `111`, `224`(초성과 중성은 종성 유무에 따라, 종성은 8x4x4 모음 그룹에 따라), `621`, `844`(jamoset.py의 레이아웃), `fine`(2 x 3 클래스, `sweep`의 63 / 6 / 42
벌 시작점. 병합되기 전까지는 포맷 한계를 넘는다). `--pieces`는 선택적인 추가 자모 라이브러리
(`galmuri_jamo.py analyse`의 `pieces-NAME.json`)이다.

**방법.** 스트라이크의 음절을 초성, 중성, 종성으로 나누고(`decompose_strike`: 문맥별 코어, 가로형 또는 혼합형 모음의 막대에 있는 긴 수평 구간은 모음의 것으로, 나머지는 잉크가 있는 이웃을 따라 geodesic 성장으로), 세 번 이상 쓰인 변형을 유지하며, 스트라이크 자체의 호환 자모보다 수평 또는 수직 획이 더 많은 변형은 버린다(`stroke_filter`: 이웃의 획을 가져온 것). 그런 다음 각 조각
(unit)은 좌표 하강으로, 그 unit들의 음절을 스트라이크 자체의 것과 비교해 가장 잘 합성하는 변형을 취한다. 빠진 레퍼런스 픽셀은 `MISS`(2), 남는 픽셀은 1, 두 조각 모두 잉크인 픽셀은 `OVERLAP`(3), 다른 조각에 닿는 픽셀은 `TOUCH`(0.25)의 비용이다. 가중치는 2,350개 KS X 1001 음절에 1.0, 나머지에 0.2이다. 형태를 검사하는 하드 게이트: 평행한 획의 폭이 다른 후보 조각(`width_violation`: 1 px와 2 px 줄기를 가진 ㅍ, 뭉개진 ㅃ), 또는 틱이 없거나 막대의 잘못된 쪽에 있는 중성(`tick_ok`: ㅗ ㅛ ㅘ ㅙ ㅚ는 위, ㅜ ㅠ ㅝ ㅞ
ㅟ는 아래, ㅡ는 없음), 또는 캡, 막대, 몸통을 잃은 ㅊ / ㅎ(`cap_ok`)은 거부된다(`shape_filter`,
`stroke_filter`, 그리고 픽셀 최선 조각에 대해). 그리고 중성 구별성(`Fill.medial_violations`)은 위반마다 `MEDIAL_PENALTY`(30, 가중 없음)의 비용이 든다. 같은 초성과 종성 아래에서 같은 그룹(ㅗㅛㅜㅠㅡ, ㅏㅑㅓㅕㅣ, ㅐㅒㅔㅖ,
ㅘㅙㅚㅝㅞㅟㅢ)의 다른 모음을 가진 음절과 min(2, 레퍼런스 자신의 거리) 픽셀보다 가까운 음절, 또는 틱이 다른 자모에 덮인 음절(다른 자모에 닿기만 하는 틱은 5분의 1의 비용)이다. 획 완전성(`complete_ok`, 표 `COMPLETE`): 단자음은 2픽셀 이상의 수평과
수직 획을 유지하고, ㄲ ㄸ ㅃ는 위 / 아래 잉크 행에 분리된 두 막대를 유지한다. 막대가
붙어 버린 ㄲ ㄸ ㅃ(Galmuri9는 12 px ㄲ를 그렇게 그린다)는 막대 사이를 한 픽셀 잘라 복구한 것이 제공된다(`split_double`).
누출(`leak_masks`, `Fill.leak_mask`): 문맥(모음 모양, 종성 그룹)에서 레퍼런스의 음절 5 % 미만에서만 자모가 잉크로 채우는 픽셀을, 거기서 다른 자모가 30 % 이상 채운다면 누출이며, 사용자당 픽셀마다 `LEAK_PENALTY`(40)이다. 호출자는 unit별로 비트맵을 금지할 수 있다(`Fill.banned`, {unit: set}). 금지된 후보는 절대 이기지 않는다(Uno 작업의 인식기 게이트가 이렇게 돈다: 잘못 읽힌 조각을 금지하고 fill을 다시 실행). `--pixel`이면
각 unit은 픽셀 단위 최선의 비트맵(분할이 그 자모에 준 픽셀만)도 취할 수 있으며, 풀에 추가된다. 벌
표는 쓸 때 압축된다(조각이 일치하는 벌이 병합되고, 그다음 벌 열이 일치하는 초성과 종성 클래스가 병합된다.
`build_face(fill, compact=False)` / `plain_tables`는 벌과 클래스를 그대로 둔다).
`--budget N`은 파일이 들어맞을 때까지 한 자모의 unit들을 묶는다(절약된 바이트당 손실이 가장 적은 것부터).

**출력.** `fill`: 페이스 하나(`-o`), SVFN v3 `mcu-strict`, JSET 버전 1, 스트라이크의 인쇄 가능한 ASCII(비례 폭,
`adv`에서)와 서로 다른 조각. 다시 읽어 모든 음절을 fill과 대조한다. `--report` JSON:
`bytes`, `pieces`, `jset_bytes`, 클래스와 벌 개수, `exact` / `exact_ks`, `mean_dist_ks`, `confuse_ks`(자모 하나 떨어진 음절과 2픽셀 이내인데 레퍼런스의 두 음절은 더 많이 다른 음절, 범주별: `oug` ㅗ ㅛ ㅜ ㅠ ㅡ,
`hieuh` 초성 ㅎ, `final`, `initial`, `vowel`), `overlap_ks`(모음 조각과 픽셀을 공유하는 종성 조각),
`missing3_ks`, `extra4_ks`, `medial_violations(_ks)`, `medial_pairs`(모음 쌍별: 문맥, 위반, 최소
거리, 최악의 문맥), `tick_merged_ks`(없거나 덮임), `tick_touch_ks`, `width_violation_count`,
`width_violations`(자모), `stem_widths`(자모별 수직 획 폭), `incomplete_pieces`(ㄲ 먼저),
`leak_units`와 `leak_pairs`(조각>이웃: 픽셀)이며 KS 예시가 붙는다. `sweep`: 골격에서 시작하는 탐욕적 벌 병합(손실이
가장 적은 병합), 각 `--points NI,NM,NF` 이하에 처음 이르는 상태의 페이스와 보고서, 그리고 `PREFIX-curve.json`. `sheet`:
`PREFIX-ks-{1,4}x.png`(2,350개 KS 음절, 한 줄에 50개), `PREFIX-text-{1,4}x.png`(샘플 텍스트), 그리고 `--strike`가 있으면
`PREFIX-vs-ref-4x.png`(레퍼런스 위에 올린 흔한 음절 20개).

**사용법.** `python3 tools/jamofill.py fill --strike S.npz --skeleton SK [--pixel] [--budget N] [--pieces J ...]
-o FACE.SVF [--report R.json]`; `python3 tools/jamofill.py sweep --strike S.npz --skeleton SK [--pixel] [--budget N]
--points NI,NM,NF ... [--prefix P] -o DIR`; `python3 tools/jamofill.py sheet FACE.SVF [--strike S.npz] -o PREFIX`.
실험을 위해 가중치는 `JAMOFILL_MISS`, `JAMOFILL_OVERLAP`, `JAMOFILL_TOUCH`,
`JAMOFILL_OWN`(기본 1; 0이면 `--pixel`이 어떤 픽셀이든 취할 수 있다), `JAMOFILL_MEDIAL_PENALTY`, `JAMOFILL_LEAK_PENALTY`로 바꿀 수 있다.

`fill`과 `sweep`은 `--no-decompose`(꺼짐), `--raw-variants`(꺼짐), `--no-stroke-filter`(꺼짐),
`--per-jamo N`(40)도 받는다. 각각 스트라이크 분리 생략, 원시 변형 추가, 획 필터 생략, 라이브러리별·자모별 변형 상한이다.
`sweep --prefix`의 기본값은 `SWP`이다. `sheet --text FILE`은 UTF-8 샘플 텍스트를 읽는다(기본: 내장 텍스트).
`-o`의 긴 이름은 `fill`에서 `--out`, `sweep`에서 `--outdir`, `sheet`에서 `--prefix`이다.

**내부 모듈.** `jamoset.py`. **서드파티.** Pillow(`sheet`만). **테스트.**
`tools/test_jamofill.py`(문맥에 무관한 자모의 합성 스트라이크: 분할, 정확한 1/1/1과 8x4x4 fill, 압축,
벌 병합, 예산 묶기, 획 폭, 틱, ㅊ/ㅎ 캡, 획 완전성과 ㄲ 복구, 누출 마스크,
중성 게이트, 명령줄).

### `tools/jamomerge.py`

**목적.** 변형이 많은 자모 세트 페이스의 변형을 병합해 더 작게 만들되, 모든 조각은 그린 그대로 유지한다. 변형이
많은 페이스(예: 모음 클래스와 종성에 따른 13개 초성 벌, 많은 중성 구간)를 Arduino Uno 예산(8,192 B, JSET 버전 1, ASCII 포함)에
맞춰야 해서 작성되었다.

**상태.** 연구용 빌더.

**입력.** `--face` 자모 세트 SVF(JSET 버전 1 또는 2; JMAP/LIST는 거부하며 출력 표는 표준 한계 안이어야 한다). `--ref` 레퍼런스 페이스(기본: 페이스
자신. 병합된 것에서 이어 가려면 병합되지 않은 페이스를 준다). `--planes` 선택적인 레퍼런스 자모 plane JSON(
`planes` 하위 명령이 Mac type-3 `fbit`와 그 `HTBL` 1에서 쓴다. KS 레퍼런스 음절은 그때 그것에서 온다).

**방법.** 페이스는 병합 상태이다. 초성과 종성 클래스, 세 벌 표, 쓰이는 슬롯마다의 비트맵으로 이루어진다. 이동(move):
`tie`(한 자모의 모든 슬롯에서 비트맵 x를 그리던 것이 그 자모의 다른 변형 y를 그린다), `set`(한 종류의 두 벌이
하나가 된다. 자모마다 그 자모의 존재하는 모든 변형 중에서 두 벌 사용자 전체에 대한 목적 함수가 가장 작은 변형을 취한다), 그리고 초성 / 종성 `class` 병합(
(모음, 다른 클래스) 셀과 종류별로 어느 한쪽의 벌. 초성 병합에서의 초성과 종성 병합에서의 종성은 양쪽 자모가 서로소이므로 양쪽 조각을 모두 담은 합집합 벌도 만든다. 빈 슬롯은 그 음절의 존재하는 비트맵으로 채운다). 각 이동 뒤에 쓰이지 않는 슬롯과 벌은
버려지고, 일치하는 벌이, 그다음 행이 일치하는 초성과 종성 클래스가 공짜로 병합된다. 탐욕적이다. 모든 이동은
절약된 바이트당 레퍼런스에 대한 픽셀 목적 함수(잃은 레퍼런스 픽셀 `MISS` 2, 남는 픽셀 1, 두 조각이 공유하는 픽셀 `OVERLAP` 1. KS X 1001 음절의 가중치는 1.0, 나머지는 `JAMOMERGE_OTHER`, 기본 0.1)로
점수가 매겨진다. `--recog`이면 상위 `JAMOMERGE_RECOG_TOP`(16)개를 recog-11-12(바뀐 음절에 대한 가중 top-1 오류 + 0.2 x
log-loss. 별도로 제공하는 `recog.py`, `SVF_RECOG_DIR`로 찾으며 추론만 한다)로 다시 채점하고 바이트당 최선을 적용한다. 하드
게이트는 음절별로, 그리고 이동이 더 나쁘게 만드는 것에 대해서만 적용된다. `tick`(ㅗ/ㅛ/ㅜ/ㅠ/ㅡ 유형 중성의 틱이 없거나
다른 조각에 덮임. 모든 음절), `medial`(같은 중성 그룹의 두 KS 음절이 같은 초성과
종성을 가지면서 min(2, 레퍼런스 거리) 픽셀보다 가까움), `stroke`(KS 음절의 레퍼런스에 있는 2픽셀 이상의 구간이 그 줄이나 이웃 줄에 대응물이 없거나, 한 픽셀을 뺀 전부를 덮는 대응물만 있음), `leak`(KS 음절의 한 컴포넌트가
레퍼런스의 두 컴포넌트를 잇는 것: 틈을 가로지르는 잉크), 그리고 `--recog`이면 `recog`(바뀐 슬롯의 가장
중립적인 음절이 전에는 그 자모로 올바르게 읽혔는데 후에는 잘못 읽힘). `--soft`이면 게이트가 걸리는 이동이 남지 않았을 때(
게이트 바닥. `PREFIX-floor.SVF`로 쓴다) `stroke`와 `leak`이 비용이 된다(`JAMOMERGE_SOFT`, KS 음절당 40).
`tick`과 `medial`은 계속 하드이다. KS가 아닌 음절은 KS 음절처럼 병합된 표에서 합성되며, 이들의 stroke
와 leak 플래그는 비용만 든다(20 x 가중치).

**출력.** `-o DIR`에: `--points` 예산마다 페이스 `PREFIXnK.SVF`(SVFN v3 `mcu-strict`, JSET 버전 1,
메트릭과 dy가 있는 페이스의 ASCII. 다시 읽어 모든 음절을 검사한다)와 `PREFIXnK.json`(바이트, 부분, 벌,
클래스, 조각, 게이트 개수, 그려진 자모별 줄기 폭, `--recog`이면 인식기 top-1, `soft_gates`).
`PREFIX-steps.json`(적용된 모든 이동: 종류, 절약된 바이트, 픽셀과 인식기 델타, 바뀐 음절, 게이트별
거부). 이동이 남지 않은 곳의 `PREFIX-stop.SVF/.json`. `baseline`은 페이스의 크기 부분을
`mcu-strict` / JSET v1로, 고정 부분(헤더, ASCII, 가장 작은 JSET), 게이트 개수, 줄기 폭을 출력한다(또는 `-o`).

**사용법.** `python3 tools/jamomerge.py baseline --face F.SVF [--planes P.json] [-o R.json]`;
`python3 tools/jamomerge.py merge --face F.SVF [--ref UNMERGED.SVF] [--planes P.json] --points 8192 7168 ... [--recog
[--threads N]] [--soft | --start-soft] [--batch] [--prefix P] -o DIR`(`--batch`: 다음 지점을 훨씬 넘을 때, 단계마다 음절이 서로소인 서로 다른 자모의 여러
tie를 묶어서 처리하며 픽셀 목적 함수만 쓴다. 함께 적용했을 때 게이트를 깨면 배치는 가장 좋은 이동까지 되돌려진다). `python3 tools/jamomerge.py planes FBIT.bin HTBL1.bin -o
P.json`.

`-o`의 긴 이름은 `baseline`과 `planes`에서 `--out`, `merge`에서 `--outdir`이다.

**내부 모듈.** `jamoset.py`, `jamofill.py`. **서드파티.** 없음(`--recog`이면 numpy와 torch).
**테스트.** `tools/test_jamomerge.py`(합성 페이스: 빌드 / 읽기 왕복과 크기, 정규화, 모든 이동이
약속대로 합성되는지, 탐욕 단계 하나, leak, stroke, tick 게이트).

### `tools/jamohybrid.py`

**목적.** 학습한 분리로 완성형 페이스에서 자모 세트 페이스를 만든다([자모 분리](jamo-split.ko.md)의 학습한 분리). 조합한 음절은
원본을 따르고, 각 조각은 그 자모다.

**상태.** 빌더. numpy가 필요하다(경로에 없으면 `--pylib DIR`이나 `$JAMOSET_PYLIB`). 가중치는 `tools/models/jamohybrid-v1.npz`다.
`--from-ttf`에는 freetype-py가 필요하다. torch는 필요 없다.

**입력.** `--from-svf FACE.SVF`(1 bpp 완성형 페이스. 다른 글리프, 메트릭, 플래그는 유지한다) 또는
`--from-ttf FONT --size N [--cell WxH] [--baseline R]`(`jamoset.py --from-ttf`와 같이 렌더링한다). 입력 페이스는
파싱하기 전에 확인한다. 최대 16 MiB, 셀 64 x 64 이하, 글리프 70,000개 이하, 음절 픽셀 11,172 x 64 x 64 이하다. 한글 음절이 없는
페이스는 메시지와 함께 거부한다.

**방법.**
1. `tools/jamonet.py`가 음절마다 초성, 중성, 종성 판을 준다. 음절의 자모를 조건으로 받는다. 원본에 있는 음절을 모두 쓴다.
   `--from-ttf`는 글꼴이 그리는 음절 전부, `--from-svf`는 SVF 페이스에 든 음절 전부다.
2. 초성 갈래와 종성 갈래(받침 없음은 혼자)를 정한다. 초성, 종성마다 다른 칸이 어떻게 보이는지를 Ward 군집으로
   묶거나(`--rule derived`), 고정 갈래를 쓴다(`--rule structural`).
3. JSET 구조 그대로 그 안에서 묶는다. 표는 음절을 셀 = (초성 갈래, 모음, 종성 갈래)로 읽으므로, 벌 한도는 초성은 초성 갈래마다,
   중성은 모음마다, 종성은 종성 갈래마다 따로 적용된다. 각각에서 문맥을 따로 둔 채 시작해 가장 싼 쌍부터 합친다(비용은 합친
   묶음의 확률 가중 다수결 조각과 어긋나는 픽셀 수). 먼저 벌 한도까지 합치고, 이어서 작은 쪽 묶음의 음절당 `--tol` 픽셀
   이하만 늘어나는 동안 더 합친다.
4. 정체 관문은 페이스 자신의 판으로 정한다. 잉크와 크기, 구멍, 단순 모음의 곁획과 꼭지(세리프 허용), ㅅ과 ㅈ이다. 통과하던
   조각을 실패로 바꾸는 합치기는 하지 않는다(벌 한도 때문에 다른 길이 없을 때만 예외다). 묶음의 조각이 실패하면 그 조각에
   가장 가까우면서 통과하는 구성 음절의 판으로 바꾸고, 그것도 없으면 다른 묶음에 있는 같은 자모의 통과 조각 가운데 가장
   가까운 것을 쓴다.
5. `jamofit.fit_pieces`가 조각을 원본에 다시 맞춘다. 픽셀은 모델이 준 칸으로만 간다. 관문에 실패한 재맞춤은 버린다.
6. 원본이 그리지 않는 문맥은 글꼴 간 순위 모델 `--fill`이 먼저 정한다(기본은 켜짐. `--fill none`이면 끈다). 후보 묶음마다 페이스
   자신의 조각과 기하에서 얻은 크기 없는 수 60개(칸과 모음, 배치 예측, 초성·종성 갈래 평균 상자, 받침 없는 음절의 비율, 묶음의
   구성원 수·문맥 거리·상자·형제 투표·가까운 이웃 비율)를 계산하고, 60-64-64-1 float32 MLP(`tools/models/jamofill-v1.npz`)가
   글꼴이 실제로 그릴 조각에 가장 잘 맞을 묶음을 고른다. 페이스에 이미 있는 묶음만 고를 수 있어 바이트, 조각, 벌, 관문은
   바뀌지 않는다. 후보가 둘 미만이거나 답이 잘못됐거나 모델이 없으면 다음 단계의 순서로 돌아간다.
7. 기준 배치: 그 (모음, 종성)에서 초성의 잉크가 어디에 놓이는지로 정한다. 원본이 가진 음절에 맞춘 초성 칸 상자(위, 왼쪽,
   아래, 오른쪽)의 가산 모델이 그 문맥의 조각이 가장 가까운 묶음을 고른다. 원본에 그 짝이 아예 없어도 빠진 음절의 종성은
   알 수 있고, KS 2,350음절 페이스가 주로 빠뜨리는 것이 그 짝이다. 초성만 모델로 삼는다. 같은 모델을 중성에 쓰면 기본 갈래
   상한에서 얻는 것보다 잃는 것이 많았고, 종성은 제 칸에서 더 잘 정해진다. 원본의 칸으로 모델을 식별할 수 없으면 쓰지 않는다.
   모델이 없으면 다른 초성 갈래(모음, 종성 갈래)가 그 문맥을 가장 자주 함께 둔 묶음에 넣고, 그런 근거도 없으면 가장 가까운
   문맥의 묶음에 넣는다. 그 초성 갈래(모음, 종성 갈래)의 어느 음절도 보여 주지 않는 자모는 조각이 없어 빈 칸으로 그려진다.
8. 멈춤 규칙. (초성 갈래, 종성 갈래) 쌍 하나는 표 63바이트, 조각 하나는 그 비트맵만큼 든다. 기본 페이스는 갈래 상한 12x12,
   12x6, 8x8, 6x6, 4x4마다 기본 허용치(셀 높이 / 12 픽셀)로 만들고, 가장 정확한 것과 조합 IoU 차이가 0.005 안인 것 가운데 가장
   작은 것을 남긴다.

**옵션.**

| 옵션 | 뜻 |
|---|---|
| (기본) | 표준 JSET 페이스: 32 / 24 / 16벌, 12 x 12 갈래까지. 위의 멈춤 규칙을 쓴다 |
| `--big` | JSET BIG: 도구의 기본 한도가 64 / 48 / 32벌, 19 x 28 갈래가 된다(형식의 BIG 행은 128 / 128 / 64까지 허용한다). `SVF_JSET_BIG`으로 빌드한 엔진이 읽는다 |
| `--limits NI,NM,NF` | 벌 한도: 각각 1 이상, 최대 32 / 24 / 16(`--big`이면 128 / 128 / 64) |
| `--tol PX` | 합치기 허용치, 음절당 픽셀(기본은 셀 높이 / 12. 0이면 한도가 허용하는 묶음을 모두 남긴다) |
| `--classes LC,TC` | 여러 상한을 시험하지 않고 초성, 종성 갈래 상한을 고정한다(`--big` 사다리의 표준 지점은 최대 12,12). `--rule structural`과 함께 쓸 수 없다 |
| `--max-bytes N` | 사다리에서 N바이트 안에 드는 가장 정확한 페이스. 사다리는 갈래 상한마다 기본 허용치의 6, 4, 3, 2, 1, 0.5배이고, `--big`이면 BIG 지점도 더한다 |
| `--min-iou X` | 사다리에서 조합 IoU가 X에 이르는 가장 작은 페이스 |
| `--rule derived\|structural` | 초성, 종성 갈래를 페이스에서 군집으로 정하거나(기본) 고정 갈래(초성 7, 종성 4)를 쓴다 |
| `--model PATH` | 다른 가중치 |
| `--fill [MODEL.npz]` | 원본이 그리지 않는 문맥의 묶음을 글꼴 간 순위 모델로 고른다(기본 `tools/models/jamofill-v1.npz`. `--fill none`이면 끈다). 그런 문맥이 어느 저장된 묶음에 드는지만 바꾸므로 바이트, 조각, 벌, 관문은 그대로다 |
| `--report OUT.json` | 고른 지점, 시험한 지점, 벌, 갈래, 조각, 관문, 원본 음절 전체와 KS X 1001 음절의 조합 IoU |
| `--check` | 출력의 11,172자를 모두 조합한다 |
| `--jset-version 1\|2\|auto` | `jamoset.py`와 같다 |

**출력.** `-o OUT.SVF`(JSET 블록이 있는 SVFN v3). 요약 한 줄(바이트, 원본 음절 전체의 조합 IoU와 다를 때는 KS 음절의 IoU,
정확한 음절, 조각, 벌, 갈래, 관문에 실패한 조각). 원본 음절이 하나도 보여 주지 않는 자모가 있으면 경고 한 줄(그 자모는 빈 칸으로
그려진다. 보고서의 `blank_jamo`).

**사용법.** `python3 tools/jamohybrid.py --from-svf FACE.SVF -o OUT.SVF [--min-iou 0.9 | --max-bytes N] [--tol PX]
[--classes LC,TC] [--fill [MODEL.npz]|none] [--big] [--report R.json] [--check]`.

**가져오는 저장소 모듈.** `jamoset.py`, `jamofit.py`, `jamonet.py`. **외부 의존성.** numpy. `--from-ttf`에는 freetype-py.
**테스트.** `tools/test_jamohybrid.py`: 저장소 루트에서 `JAMOSET_PYLIB=DIR python3 -B -m unittest tools.test_jamohybrid`
(`DIR`에 같은 파이썬용 numpy가 있다. 없으면 테스트를 건너뛴다).

**속도.** 스레드 4개로 11,172자: 모델이 약 15초, 이어서 한 번 만들기 1.5-4초, 기본값(갈래 상한 다섯 가지) 7-15초,
`--max-bytes` / `--min-iou` 사다리 30-90초. KS만 있는 원본은 보이지 않는 문맥이 약 4,300개이고 fill이 만들기마다 약 2초를
더한다(기본값의 갈래 상한 다섯 가지면 약 10초. 문맥마다 후보 몇 개를 채점한다). 모든 문맥이 보이는 원본은 fill 작업을
하지 않는다. 이 수치는 셀이 약
24 px까지일 때다. 시간과 메모리는 셀 픽셀 수와 함께
늘어서, 48 px 셀의 기본값은 약 2분, 최대 메모리 1.4 GB(v1은 약 1분, 1.6 GB)였다. numpy는 기본으로 모든 코어를 쓴다. 부하가 큰 다코어 기계에서는
`OMP_NUM_THREADS`(예: 4)를 정한다. 그런 기계에서 2,357자 페이스가 모든 스레드로 29초, 4개로 6초 걸렸다.

### `tools/jamonet.py`

**목적.** 자모 분리 모델의 numpy 순전파. 32 x 32 캔버스(더 큰 셀은 다음 8의 배수)의 작은 U-Net이며, 시그모이드 판 셋을 내고
음절의 자모를 조건으로 받는다. BatchNorm은 합성곱에 접어 넣었다. `jamohybrid.py`가 import하며 명령줄은 없다.

**가중치 형식.** `.npz` 하나. `meta`(JSON: `format` `jamonet-1`, `base`, `cdim`)와 합성곱, 전치 합성곱, 임베딩 배열(fp16).
`tools/train_jamohybrid.py`가 쓴다.

**외부 의존성.** numpy. **테스트.** `tools/test_jamohybrid.py`(합성곱, 풀링, 전치 합성곱을 반복문과 비교, 무작위 작은 모델).

### `tools/train_jamohybrid.py`

**목적.** 자모 분리 모델을 학습하고 가중치를 내보낸다. 학습할 때만 쓴다. torch와 numpy가 필요하며, 어떤 도구나 테스트도
import하지 않는다.

**입력.** `--manifest SOURCES.tsv`: 한 줄에 원본 하나(`name kind path group weight licence note`). 종류는 `svf`(이 저장소의
1 bpp 조합형 페이스: 조합한 음절과 그 조각)와 `npz`(다른 곳에서 준비한 정답 자료: `cps`, `jamo`, `pre`, `planes`, 선택적
`has_planes`)다. 다른 종류는 `SOURCES`에 끼워 넣는다. `--sizes`는 렌더링하는 로더에 넘긴다.

**옵션.** `--holdout GROUP ...`(묶음을 뺀다), `--eval GROUP ...`(그 묶음에서 잰다), `--base`(채널 수, 16 또는 32),
`--epochs`, `--seed`, `--out DIR`.

**출력.** `DIR/jamohybrid.npz`(fp16 가중치), `DIR/provenance.json`(원본마다 sha256과 라이선스, 시드, 에포크, numpy와 torch의
확률 차이 최댓값), `DIR/eval.json`.

**외부 의존성.** torch, numpy. **테스트.** 없음(학습 전용).

### `tools/jamoexc.py`

**목적.** LIST 예외 페이스를 쓴다. 자모 세트 페이스에 선택한 음절과 호환 자모를 위한 온전한 글리프와 조각 재조합을 더한 것이며, list 모드의 JMAP 블록([SVF 명세](../spec/SVF.ko.md), JMAP LIST)이다. 페이스 자신의 JSET 바이트는
폴백으로 남으므로 목록에 없는 모든 음절은 전과 같이 그려진다.

**사용법.** `python3 tools/jamoexc.py build FACE.SVF EXC.json OUT.SVF [--jset-version 1|2] [--profile P] [--box B]`.

**EXC 형식.** 음절 또는 호환 자모를 키로 하는 JSON 객체. 키는 문자(`"가"`, `"ㄱ"`) 또는 `"U+AC00"`이며, 두 번 쓴
키는 거부된다. 값은 `{"whole": "HEX"}`(`ceil(cell_w * bpp / 8)`바이트의 행 `cell_h`개를 16진수로. 16진 행만
받으며 PNG 입력은 없다) 또는 `{"pieces": [n, n, n]}`(페이스의 조각 번호: 음절은 1개에서 3개, 호환 키는 정확히 1개)이다. `whole` 셀은
페이스의 가장 높은 U+F0000 + n 코드 포인트보다 위의 번호를 가진 새 조각 글리프가 된다
(음절 오름차순, 그다음 호환 자모 오름차순). 번호 0xFFFF(BLANK)는 절대 부여되지 않는다. 값의 다른 키
(`dy`, `advance`, ...)는 거부된다. 예외 항목에는 dy나 메트릭을 지정할 수 없다. 합성은 조각 글리프의 메트릭을 사용하지 않는다.

**출력.** 한 줄, `jmap=BYTES ns=N whole=W recomb=R total=BYTES`. `jmap`은 JMAP 블록의 바이트 크기(LIST
헤더, 항목, 호환, 그대로 복사한 폴백), `ns`는 LIST의 음절 항목 수, `whole`은 쓴 새 온전한
글리프(`"whole"` 값마다 하나. 음절과 호환 자모), `recomb`는 `"pieces"`로 준 항목(
음절과 호환 자모. `"whole"`은 거기에 세지 않는다), `total`은 출력 파일의 바이트 크기이다. N >= 200이면
줄 끝에 ` sparse=BYTES`가 붙는다(1604 + 3 N: 항목 N개의 SPARSE 블록 크기이며 LIST와 견주기 위한 것).
`svf/dos/NEODG16G.SVF`에 `{"가": {"pieces": [1, 2]}, "ㄱ": {"pieces": [3]}}`를 준 예:
`jmap=779 ns=1 whole=0 recomb=2 total=10808`.

**충실도.** 출력은 원본의 레이아웃(rec/row/tab/꺼짐 단위 유지. `--box`가 없으면 박스 정책은 x, 픽셀은
동일. `--profile`은 요청 시 레이아웃을 바꾼다), JSET 버전과 바이트(`--jset-version 1|2`는 버전이 바뀔 때만 폴백을 `pack_fallback`으로 다시 인코딩하며 조각 번호는 유지한다. 그 밖에는 절대 다시 인코딩하지 않는다), 그리고 모든 원본 글리프의 셀, advance, 베어링, 잉크 폭, dy를 유지한다. 새
조각은 페이스의 첫 조각 글리프의 메트릭과 dy 0을 받는다. 출력 파일은 성공했을 때만, 임시 파일에 쓰고 이름을 바꾸는 방식으로 쓴다.

**거부(종료 코드 1, 텍스트는 stderr. 사용법 오류는 종료 코드 2).** 255개 초과 항목: `jmap_list: N LIST entries is over
255: use SPARSE (1604 + 3N B plus plane copies for recombinations)`. 버전 3 원본(`the face already has a JSET
version 3 block; start from the plain face`). 쓸 수 있는 JSET이 없는 페이스(`the face has no usable JSET block; start
from a jamo face whose JSET parses`). 길이가 잘못되었거나(기대하는 바이트 수를 알려 준다) 16진수가 아닌 `whole`, 조각이 하나가 아니거나 65535(BLANK. 폴백의 것을 유지하려면 키를 생략한다)인 호환
키, 두 번 쓴 키(JSON에 문자 그대로 두 번 쓴 경우도), 한 문자 또는 `U+` 뒤에 16진수 4에서 6자리가 아닌 키, 음절 항목이 없는 EXC
(`a LIST needs at least one syllable entry (L3); compat jamo alone cannot be listed`), u16
오프셋을 넘는 글리프 데이터(메시지가 해결책을 알려 준다: 온전한 셀을 줄이거나, u32 또는 auto 오프셋의 `--profile`), 조각이 0개이거나 3개를 넘는 음절, 글리프가 없는 조각 번호, 
U+AC00..U+D7A3과 U+3131..U+3163 밖의 키, 값 안의 알 수 없는 키.

**내부 모듈.** `jamoset.py`. **서드파티.** 없음.
**테스트.** `tools/test_jamoexc.py`(`svf/dos/NEODG16G.SVF` 위의 합성 셀: Python `compose`가 LIST 리더 빌드(매핑 및 스트리밍)의 `svfdump
syllables`와 같음. `default`와 `dos` 원본에 대한 레이아웃, 메트릭, dy 충실도. 200에서의 sparse 메모. 거부.
버전 재인코딩).

## 3. 맞춤 및 분리 모듈(명령줄 없음)

`jamofit.py`, `jamoaa.py`, `jamoadapt.py`는 `jamoset.py`와 `jamovec.py`가 import한다. `jamoseg.py`는
어떤 도구도 import하지 않고 `tools/test_jamoaa.py`만 import한다. 이들 중 `main`을 가진 것은 없다.

### `tools/jamoaa.py`

**목적.** 아웃라인 폰트에서 안티앨리어싱된(2 bpp) 자모 세트를 만든다. 그리고 `jamoset.py --from-ttf --bpp 2`와 `jamovec.py`가 쓰는 공유 아웃라인 래스터라이저/윤곽 로직이다.

**상태.** 범용이다.

**입력.** fontTools로 읽는 아웃라인 폰트(glyf 또는 CFF, 컴포짓 분해). fontTools pen을 통한다.

**출력.** 직접 쓰는 것은 없다. 호출자가 쓰는 커버리지 래스터, 묶인 레벨, 맞춘 조각, 표를 돌려준다.

**명령줄.** 없음. 함수는 `jamoset.main_aa`와 `jamovec.py`가 호출한다.

**내부 모듈.** `jamofit.py`, `jamoset.py`, `jamoadapt.py`(지연 import). **서드파티.** fontTools
(아웃라인 경로에 필수. `--pylib` 또는 `$JAMOSET_PYLIB`로 찾는다).

**테스트.** `tools/test_jamoaa.py`.

### `tools/jamoadapt.py`

**목적.** 맞춘 자모 세트를 위한 적응형(adaptive) 벌 체계. 844에서 시작해 조각을 공유하는 음절들이 서로 어긋나는 곳에서 벌을 쪼개며, 엔진의 JSET 한계(초성 12개와 종성 12개 클래스, 32/24/16 벌)까지 간다.

**상태.** 범용이다.

**입력.** "도너(donor)": `jamoaa.contour_donors`(아웃라인) 또는
`jamoaa.pixel_donors`(비트맵)에서 가져온, 슬롯별로 존재하는 각 음절 자신의 래스터.

**출력.** 표가 매핑을 인코딩하는 `adaptive`라는 이름의 `jamoset.Layout`(파일 없음).

**명령줄.** 없음. `jamoset.py --layout adaptive`와 `jamovec.py --adaptive`를 통해 쓰인다.

**내부 모듈.** `jamoset.py`. **서드파티.** 없음.

**테스트.** `tools/test_jamoaa.py`가 테스트한다(`--layout adaptive` 경우들).

### `tools/jamofit.py`

**목적.** 마스크가 있는 좌표 하강으로 자모 세트 조각을 완성형 1 bpp 음절에 맞추고, 그 맞춤에 점수를 매긴다
(IoU, 1 px 허용 F1, blob과 stray-ink 메트릭).

**상태.** 범용이다.

**입력.** Python 정수("gints")로 된 글리프 래스터. 선택적인 아웃라인 마스크 폰트(OpenType 자모
변형이 있는 NotoSansKR)는 freetype-py로 읽고 uharfbuzz로 셰이핑한다.

**출력.** 맞춘 조각과 품질 수치(파일 없음).

**명령줄.** 없음. `jamoset.py --from-ttf`/`--from-svf`와 `bdfface.py --fill-absent`가 쓴다.

**내부 모듈.** 없음. **서드파티.** freetype-py와 uharfbuzz(선택: 마스크 폰트와
아웃라인 `mono` 대상만 필요로 한다).

**테스트.** `tools/test_jamoset.py`(직접 import한다)와 `tools/test_jamoaa.py`.

### `tools/jamoseg.py`

**목적.** 벡터 자모 분할: 윤곽 그룹화, peer, 영역 클리핑으로 음절의 아웃라인을 초성, 중성, 종성의 아웃라인으로
폰트 단위에서 나눈다.

**상태.** 범용이다.

**입력.** 폰트 단위의 음절 아웃라인(fontTools pen에서).

**출력.** 음절별로 슬롯마다의 닫힌 폴리라인 목록과 각 그룹이 어떻게 결정되었는지(파일 없음).

**명령줄.** 없음. **내부 모듈.** 없음. **서드파티.** 병합된 아웃라인을 클리핑하는 skia-pathops(`pathops`, 선택: 없으면
`load_pathops`가 None을 돌려준다).

**테스트.** `tools/test_jamoaa.py`.

## 4. 검사와 확인

문서와 에이전트 스킬은 테스트로 검사한다. `python3 -B -m unittest tools.test_tools_doc tools.test_recipes
tools.test_skills`를 실행한다. `tools/test_skills.py`는 `skills/*/SKILL.md`를 읽어 프런트매터, 존재하는 도구 파일,
`jamohybrid.py`와 `jamoset.py`가 정의한 옵션, 해석되는 링크와 앵커, 로컬 절대 경로가 없음을 확인한다. 테스트 파일은
이 문서의 집계 대상이 아니므로 절로 두지 않고 여기서 설명한다.

### `tools/facecheck.py`

**목적.** 페이스 매니페스트와 맵 페이스 검사: 커밋된 모든 페이스의 sha256을 기록하고, 이동 후 매니페스트를 검증하며,
맵이 지명하는 모든 페이스를 찾을 수 있는지 검사한다.

**상태.** 범용이다.

**입력.** git blob(`manifest`), 매니페스트 TSV(`verify`), 맵 파일, 그리고 선택적으로 builtin zip(`mapfaces`).

**출력.** 매니페스트 TSV, 또는 `MISSING`/`CHANGED` 줄과 종료 코드. 폰트는 쓰지 않는다.

**사용법.**

    python3 tools/facecheck.py manifest --git REPO --rev REV --path DIR [--path DIR ...] [--exclude GLOB] [--exclude GLOB ...] -o OUT.tsv
    python3 tools/facecheck.py verify MANIFEST.tsv [--map OLD_PREFIX=NEW_DIR] [--map OLD_PREFIX=NEW_DIR ...]
    python3 tools/facecheck.py mapfaces --maps DIR [--maps DIR ...] --root PREFIX=DIR [--root PREFIX=DIR ...] [--builtin-zip FILE] [--builtin-zip FILE ...]

모든 목록 옵션은 `action="append"`이다. 플래그마다 값 하나를 주고 플래그를 반복한다. `manifest`: `--git`, `--rev`,
`--path`(필수), `--exclude`, `-o`(필수). `verify`: `MANIFEST.tsv`, `--map`. `mapfaces`: `--maps`(필수),
`--root`(필수), `--builtin-zip`.

**내부 모듈.** 없음. **서드파티.** 없음(git, zipfile). **테스트.** `tools/test_facecheck.py`.

### `tools/fontmetrics.py`

**목적.** 저장된 메트릭에서 잉크가 전진 폭을 넘는지 보고한다. 헤더, 관찰된 advance와 잉크 폭을 출력하고,
`bearingX + inkWidth`가 advance를 넘는 글리프를 나열한다.

**상태.** 범용이다.

**입력.** SVFN v3 페이스. `jamoset.parse_svfn`으로 읽는다.

**출력.** 텍스트 보고서(파일 없음).

**사용법.** `python3 tools/fontmetrics.py FACE [FACE ...]`(옵션 없음).

**내부 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** 없음.

### `tools/svfline.py`

**목적.** C 렌더러의 줄 그리기를 위한 Python 레퍼런스: UTF-8을 디코딩하고, 체인에서 각 코드 포인트의 페이스를 고르며,
advance, dy, 결합 표시와 함께 한 기준선에 셀을 그리고, 한 줄을 측정한다.

**상태.** 범용이다.

**입력.** SVFN 페이스. `jamoset.parse_svfn`과 엔진의 로드 규칙으로 읽는다(dy 범위는 유효할 때만, 메트릭 표는
맞을 때만, JSET 블록은 풀리고 모든 조각에 글리프가 있을 때만).

**출력.** stdout의 GRAY8 버퍼(`line`) 또는 한 줄 측정값(`measure`). 라이브러리로도 쓰인다. `layout`, `measure`,
`placements`, 그리고 `Target` 변환.

**사용법.**

    python3 tools/svfline.py line W H X Y TEXT FACE...
    python3 tools/svfline.py measure TEXT FACE...

옵션 없음. `TEXT`는 인자의 바이트이며 UTF-8로 디코딩된다(잘못된 부분은 U+FFFD가 되거나, 어떤
페이스에도 없으면 건너뛴다). 라이브러리는 렌더러의 스케일링을 위해 `scale=(num, den)`을 받는다.

**내부 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_c_renderer.py`와
`tools/test_web_picker.py`.

### `tools/vesa_lines.py`

**목적.** `c/ports/dos/vesa-lines.txt`(DOS VESA 예제의 색과 줄 표)의 Python 리더이며
그 예제의 오라클이다. 파일의 줄을 그린 뒤 `c/ports/dos/svfvesa.c`의 백 버퍼가 담아야 할 내용이다. 이 파서는 `c/ports/dos/vesa_lines.c`와 일치한다(같은 표, 팔레트, 같은 줄에서의 거부 메시지). 둘을
함께 바꾼다.

**상태.** 특수 목적(DOS VESA 예제).

**입력.** `vesa-lines.txt` 파일(형식은 `c/ports/dos/vesa_lines.h`와 `c/ports/dos/README.md`에 있다)과, `--expect`에서는 그것이 지명하는 페이스의 디렉터리(8.3 대문자 `.SVF` 이름).

**출력.** `--print-table`: `c/tests/vesa-lines-dump`가 출력하는 형태의 파싱된 표와 팔레트. `--expect`:
`sum=<예상 백 버퍼의 FNV-1a, 16진수 8자리>`. 거부는 `line N: message`를 출력하고 0이 아닌 값으로 종료한다.

**사용법.**

    python3 tools/vesa_lines.py --print-table FILE [--dac 6|8]
    python3 tools/vesa_lines.py --expect FILE --faces DIR W H BPP

`BPP`는 8, 15, 16, 24, 32이다(INDEXED8, RGB555, RGB565, RGB888, XRGB8888).

**내부 모듈.** `svfline.py`(그리고 그것을 통해 `jamoset.py`). **서드파티.** 없음. **테스트.**
`tools/test_c_renderer.py`(`TestVesaLines`). `c/ports/dos/vesa-shots.sh`가 쓴다.

### `tools/doc_figures_jamo.py`

**목적.** [jamo-sets.ko.md](jamo-sets.ko.md)의 픽셀 그림(조각과 조합, 한 자모의 벌들, 완성형과 조합형의 비교, 한 음절의
JSET 버전 1 조회)을 그린다.

**상태.** 특수 목적(문서).

**입력.** OFL 페이스 `svf/iolo/SANS8J.SVF`(참고 문헌 12)(8x4x4 자모 세트)와 `svf/dos/NEODG16.SVF`(완성형)만 읽는다. 다른 경로는
거부하므로 Apple 데이터나 ROM 데이터가 공개 그림에 들어갈 수 없다.

**출력.** `docs/images/jamo-sets/`의 `compose.png`, `sets.png`, `precomposed.png`, `lookup.png`(인덱스 PNG, 고정 팔레트:
실행할 때마다 같은 바이트)와, 두 페이스를 KS X 1001 음절 2,350자에서 비교한 한 줄.

**사용법.**

    python3 -I tools/doc_figures_jamo.py [--out DIR] [--check]

`--check`는 메모리에서 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르면 종료 코드 1).

**내부 모듈.** `jamoset.py`. **서드파티.** Pillow. **테스트.** `--check`.

### `tools/doc_figures_split.py`

**목적.** [jamo-split.ko.md](jamo-split.ko.md)의 픽셀 그림(완성형 음절과 맞춘 조각, 다시 합친 결과, 차이; 정확한 맞춤과 근사한
맞춤의 비교; `NEODG16A`의 빈 중성 ㅡ 조각; 윤곽 글꼴의 12, 16, 24 px에서 닿는 획; 벌 체계마다 바이트에 대한 평균 IoU)을 그리고, 문서가 인용하는 측정값을 출력한다.
벌 체계 그래프는 스크립트의 `BUDGET` 표에 적어 둔 맞춤 결과(`jamoset.py --from-ttf`로 측정, 약 10분)를 그릴 뿐 그 맞춤을
다시 돌리지는 않는다.

**상태.** 특수 목적(문서).

**입력.** 허용 목록의 OFL 글꼴만 읽는다. `ttf/nanumgothic/NanumGothic-Regular.ttf`(`mkfont.py`의 `render()`로 16 px,
`--clip-cell`처럼 굽고 메모리에서 `jamoset.fit_font`로 8x4x4에 맞춘다), `svf/dos/NEODG16.SVF`(비교와 라벨),
`svf/dos/NEODG16A.SVF`, `svf/jamo-extra/NDGPR16.SVF`. 다른 경로는 거부하므로 Apple, ROM, 독점 글꼴의 데이터가 공개 그림에
들어갈 수 없다.

**출력.** `docs/images/jamo-split/`의 `split.png`, `exact.png`, `blank.png`, `touch.png`(인덱스 PNG, 고정 팔레트)와
`budget.png`(RGB)(메타데이터 없음: 같은 Pillow와 FreeType이면 실행할 때마다 같은 바이트, 두 버전을 출력한다)와, KS X 1001 음절 2,350자에서 맞춤의
바이트·정확 개수·평균 IoU, `NEODG16A`와 `NEODG16`의 비교, 중성 ㅡ 조각에 잉크가 없는 음절 수, 닿는 획 그림의 잉크 덩어리
수를 알리는 줄들.

**사용법.**

    python3 -I tools/doc_figures_split.py [--out DIR] [--check]

`--check`는 메모리에서 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르거나 파일이 없으면 종료 코드 1). 1초 남짓 걸린다.

**내부 모듈.** `jamoset.py`, `jamofit.py`(`jamoset`을 거쳐), `mkfont.py`. **서드파티.** Pillow. **테스트.** `--check`.

### `tools/doc_figures_jamoguide.py`

**목적.** [jamo-split-guide.ko.md](jamo-split-guide.ko.md)와 [jamo-split-guide.md](jamo-split-guide.md)의 샘플 및 조각 그림을 그린다. Neo둥근모 16, 나눔고딕 12 / 16 px, Galmuri11 12 px에 대한 원본·분리 비교와 초성·중성·종성 조각 분해 표를 만든다.

**상태.** 특수 목적(문서).

**입력.** OFL 폰트 경로를 인수로 받는다. `--neodg`(기본 `svf/dos/NEODG16.SVF`), `--nanumgothic FILE`(`NanumGothic.ttf`), `--galmuri11 FILE`(`Galmuri11.ttf`), 그리고 선택적으로 `numpy` / `freetype-py`용 `--pylib DIR`. 스크립트에 사설 폰트 경로는 없으며, 지정하지 않거나 파일이 없는 사례는 건너뛴다. 각 페이스는 임시 디렉터리에서 가이드의 명령(`jamohybrid.py`, `jamoset.py`, `mkfont.py`)을 `-I`로 실행해 만든다.

**출력.** `docs/images/jamo-split-guide/`에 인덱스 PNG 6장(고정 팔레트, 메타데이터 없음): `case1-neodg16-sample.png`, `case1-neodg16-pieces.png`, `case2-nanumgothic-sample.png`, `case2-nanumgothic-pieces.png`, `case3-galmuri11-sample.png`, `case3-galmuri11-pieces.png`. 샘플 그림은 흰 바탕 검정 글자 2배 확대이고, 조각 표는 초성·중성·종성을 색으로 구분해 4배 확대하며 라벨은 `NEODG16.SVF`로 그린다.

**사용법.**

    OMP_NUM_THREADS=4 python3 -I tools/doc_figures_jamoguide.py --nanumgothic FONT --galmuri11 FONT [--neodg FILE] [--pylib DIR] [--out DIR] [--check]

`--check`는 메모리에서 다시 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르거나 파일이 없거나 건너뛴 페이스가 하나라도 있으면 종료 코드 1이며, 건너뛴 페이스를 출력해 일부 실행이 `ok`를 내지 않게 한다).

**내부 모듈.** `jamoset.py`, `svfline.py`(그리고 `jamohybrid.py`, `jamoset.py`, `mkfont.py`를 실행한다). **서드파티.** Pillow, numpy, freetype-py. **테스트.** `--check`.

### `tools/doc_figures_aa.py`

**목적.** [anti-aliasing.ko.md](anti-aliasing.ko.md)의 픽셀 그림(한 음절의 1/2/8 bpp, 타깃별 2 bpp 단계, 2 bpp 자모 조합의 최댓값과
OR, 윤곽에서 커버리지와 단계로, 36 px 페이스의 축소, MONO, GRAY, GRAY8, RGB565, XRGB8888에 그린 한 줄)을 그린다.

**상태.** 특수 목적(문서).

**입력.** 허용 목록의 OFL 글꼴만 읽는다. `svf/jamo-extra/GOTHA16.SVF`, `GOTHA16A.SVF`, `SGDAY16A.SVF`, `NSQRR16.SVF`,
`svf/dos/NSQRR36.SVF`, `NSQRR16A.SVF`, `PAPLG16.SVF`, `PAPLG18.SVF`, `NEODG16.SVF`(라벨),
`ttf/nanumgothic/NanumGothic-Regular.ttf`. 다른 경로는 거부하므로 Apple 데이터나 ROM 데이터가 공개 그림에 들어갈 수 없다.
글리프는 `svfline.py`(페이스, 줄 배치, `Target`)로 읽고 그리며, 윤곽 그림은 `mkfont.py`의 `render()`로 그려
`jamoset.pack_svfn`으로 묶는다.

**출력.** `docs/images/anti-aliasing/`의 `bpp.png`, `levels.png`, `compose.png`, `outline.png`, `downscale.png`, `targets.png`
(RGB PNG, 메타데이터 없음: 같은 Pillow와 FreeType이면 실행할 때마다 같은 바이트, 두 버전을 출력한다)와, 2 bpp 축소 결과가
그릴 때 축소한 커버리지를 4단계로 양자화한 것과 같은지 알리는 한 줄.

**사용법.**

    python3 -I tools/doc_figures_aa.py [--out DIR] [--check]

`--check`는 메모리에서 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르면 종료 코드 1).

**내부 모듈.** `jamoset.py`, `svfline.py`, `mkfont.py`, `svfscale.py`. **서드파티.** Pillow. **테스트.** `--check`.

### `tools/doc_figures_x11.py`

**목적.** [recipes/x-window.ko.md](recipes/x-window.ko.md)의 샘플 그림을 그린다. 레시피가 만드는 페이스마다 하나: 대우 고딕 16,
대우 명조 16과 24, 백묵 굴림, 바탕, 돋움 16과 굴림 12, hanterm johab844-1 폰트 `dkbgoth`와 johab-1 폰트 `johabm16`, 한양 고딕 16,
KAIST newmj 16, iyagi 16, philgi 16.

**상태.** 특수 목적(문서).

**입력.** 폴더와 파일을 인수로 받는다. `--misc DIR`(X11 기본 폰트 폴더: 대우 PCF와 ASCII 폰트 `8x16.pcf.gz`, `12x24.pcf.gz`,
`6x12.pcf.gz`, 필수), `--baekmuk DIR`, `--hanterm DIR`, `--hanyang DIR`, `--newmj F`, `--iyagi F`, `--philgi F`. 스크립트에는
폰트 경로가 없고, 파일이 없는 페이스는 건너뛴다. 페이스마다 임시 폴더에서 레시피의 명령(`maker/srcprep.py pcf-bdf`,
`bdfface.py --symbols`; hanterm 폰트는 ASCII 페이스용 `mkfont.py`와 `jamoset.py --layout hanterm-844 / hanterm-johab --base
--check`)을 `python3 -I`로 실행해 만든다.

**출력.** `docs/images/recipes/x-window/`의 PNG 파일(8비트 회색, 흰 바탕에 검은 글자, 픽셀마다 2배, 메타데이터 없음): 페이스마다
네 줄, 한국어 팬그램 두 줄, 영어 한 줄, ASCII 기호와 KS X 1001 기호 `※☆★○●◎◇◆□■△▲→←↑↓`. 페이스에 없는 문자는 그 줄에서
빼고 출력한다(자모 세트에는 기호가 없다).

**사용법.**

    python3 -I tools/doc_figures_x11.py --misc DIR [--baekmuk DIR] [--hanterm DIR] [--hanyang DIR] [--newmj F] [--iyagi F] [--philgi F] [--out DIR] [--check]

`--check`는 메모리에서 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르거나 파일이 없으면 종료 코드 1. 옵션을 주지 않았거나
파일이 없어 건너뛴 페이스가 있어도 1이고 그 목록을 출력하므로, 일부만 돌린 실행은 `ok`를 내지 않는다). 그림은 폰트 파일에만 달려 있다.

**내부 모듈.** `svfline.py`, `binscan.py`(그리고 실행하는 도구들). **서드파티.** Pillow(hanterm 폰트의 ASCII 페이스를 만드는
`mkfont.py`를 거쳐). **테스트.** `--check`.

### `tools/doc_figures_mac.py`

**목적.** [recipes/classic-mac.ko.md](recipes/classic-mac.ko.md)의 샘플 그림을 그린다. 페이스마다 하나: HangulTalk 1.0 'fbit'
폰트 Gotic12와 Munjo24, HangulTalk 7.1.2 type-3 'fbit' 폰트 Seoul12, AppleGothic12, AppleMyungjo24, 한글 시스템 7.5.3 비트맵 전용
폰트의 'bloc'/'bdat' 스트라이크 AppleGothic 12와 16, AppleMyungjo 16과 24, Seoul 12와 16, #신명조 16, #궁서체 16, Mac OS 8.5의
한강체 16. 그리고 7.5.3 Seoul의 스트라이크 여덟 개.

**상태.** 특수 목적(문서).

**입력.** 폴더를 인수로 받는다. `--ht10 DIR`(HangulTalk 1.0 System Folder: `Gotic12.rsrc`, `Munjo24.rsrc`), `--ht712 DIR`와
`--htbl FILE`(7.1.2 CD의 `[splt]` 아카이브와 패밀리 suitcase, 그리고 그 CD의 `InputBackSupport[INIT].rsrc`), `--kh753 DIR`(7.5.3
CD의 비트맵 서체 설치 폴더, `NAME/NAME[FFIL].rsrc`), `--kh85 DIR`(Mac OS 8.5 자형 폴더, `한강체[FFIL].rsrc`). 스크립트에는 폰트
경로가 없고, 파일이 없는 페이스는 건너뛴다. 페이스마다 임시 폴더에서 레시피의 명령(`jamoset.py --layout mac-fbit-45sets --check`;
`srcprep.py mac-htbl`, `macfbit3.py unpack` / `fbit`, `macfbit_svf.py build --latin`과 `verify`; `macsfnt.py extract` / `unicode`와
스트라이크 크기에서의 `mkfont.py --size N --bpp 1`. 스트라이크 크기는 스크립트가 폰트의 `bloc` / `EBLC` 표를 경계 검사하는
읽기 함수로 읽는다)을 `python3 -I`로 실행해 만든다. 짧은 부트스트랩이 도구의 경로 맨 앞에 도구 자신의 폴더를,
맨 뒤에 사용자 site-packages 폴더를 넣어 `macsfnt.py`와 `mkfont.py`가 사용자 설치 fontTools를 찾게 한다. 그 폴더는 스크립트가
계산해(`site.getusersitepackages()`. `PYTHONUSERBASE`와 홈 폴더를 따르므로 호출한 쪽의 환경에서 온다) 인수로 넘긴다. 작업 폴더는
경로에 들어가지 않는다.

**출력.** `docs/images/recipes/mac/`의 PNG 파일(8비트 회색, 흰 바탕에 검은 글자, 픽셀마다 2배, 메타데이터 없음): 페이스마다
`tools/doc_figures_x11.py`의 네 줄. 페이스에 없는 문자는 그 줄에서 빼고 출력하며, 비게 된 줄은 뺀다(HangulTalk 1.0 폰트에는 한글만
있고, 7.1.2 페이스에는 KS X 1001 기호가 없다). U+0020이 없는 페이스는 공백에서 반 셀을 띄운다. 출력하는 줄마다 페이스의 셀,
바이트 크기, 첫 줄의 `width ascent descent`를 보여 준다. 그림 하나 더, `kh753-seoul-sizes.png`는 7.5.3 Seoul의 스트라이크(9, 10, 12, 14, 16, 18, 20, 24)마다
`<ppem> 다람쥐 헌 쳇바퀴에 타고파 ABC 123`을 그 스트라이크의 페이스로 한 줄씩 그린다.

**사용법.**

    python3 -I tools/doc_figures_mac.py [--ht10 DIR] [--ht712 DIR --htbl F] [--kh753 DIR] [--kh85 DIR] [--out DIR] [--check]

`--check`는 메모리에서 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르거나 파일이 없으면 종료 코드 1. 옵션을 주지 않았거나
파일이 없어 건너뛴 페이스가 있어도 1이고 그 목록을 출력하므로, 일부만 돌린 실행은 `ok`를 내지 않는다). 'fbit' 그림은 폰트 파일에만
달려 있고, 스트라이크 그림은 Pillow와 그 FreeType에도 달려 있다(출력한다). 저장소의 그림은 Pillow 10.2.0, FreeType 2.13.2로 만들었다.

**내부 모듈.** `doc_figures_x11.py`, `svfline.py`, `binscan.py`(그리고 실행하는 도구들). **서드파티.** Pillow와
fontTools(`mkfont.py`와 `macsfnt.py`를 거쳐). **테스트.** `tools/test_doc_figures_mac.py`(합성 표와 잘린 표에 대한 스트라이크
읽기, 건너뜀 보고, 합성 페이스 둘로 그린 크기 그림의 높이, 부트스트랩의 경로: 모듈을 심어 둔 작업 폴더에서 실행해도 그 폴더가 경로에 없고 사용자 site가 맨 뒤에 온다), `--check`.

## 5. 빌드 스크립트

### `tools/build/build_faces.py`

**목적.** 위 도구로 `svf/`의 페이스를 업스트림 폰트에서 다시 빌드하되, 레시피 표
`tools/build/faces.tsv`가 정한 대로 하고, 각 결과를 `svf/`의 페이스와 비교한다.

**상태.** 범용(동봉된 페이스의 출처 검사. [recipes/svf-faces.ko.md](recipes/svf-faces.ko.md)가 모든 레시피를 설명한다).

**입력.** `tools/build/faces.tsv`(face, method, source, args, codepoints, expect, note. `svf/`의 모든 페이스마다 한 행), `tools/build/cps/` 아래의 코드 포인트 목록, `ttf/`의 원본 폰트. source가
`ext:NAME`인 행은 외부에서 공급할 폰트를 지정한다. `--ext NAME=PATH`가 그것을 공급하며, 없으면 그 행은
`skipped`로 보고된다.

**출력.** 빌드하는 모든 행에 대한 `OUT/<face>`와, stdout에 페이스당 한 줄: `identical`(`svf/`와 같은 바이트),
`pixels`(같은 글리프, 메트릭, 헤더 값이 다른 바이트 레이아웃으로) 또는 `differs: ...`(무엇이 다른지).
그다음 `build_faces:` 합계 줄. `OUT` 밖에는 아무것도 쓰지 않는다.

**사용법.** `python3 tools/build/build_faces.py --out DIR [FACE ...] [--ext NAME=PATH ...] [--list]`. FACE는 행의
face(`dos/NGOTB15.SVF`) 또는 그 파일 이름이다. 없으면 레시피가 있는 모든 행을 뜻한다. 빌드된 모든 페이스가 행의 `expect`와 일치하면 종료 코드 0(`identical` 행은 동일해야 한다), 아니면 1, 사용법 오류는 2이다. `mkfont` 행은
`tools/mkfont.py SOURCE OUT ARGS --unicode CODEPOINTS`를 실행한 다음 `tools/svf2to3.py --profile default`(
`svf/`의 표준 레코드 순서)를 실행한다. `jamoset` 행은 `|` 앞의 인자로 `mkfont.py`를, 뒤의 인자로 `tools/jamoset.py --from-svf`를
실행한다.

**내부 모듈.** `tools/jamoset.py`(그리고 `mkfont.py`, `svf2to3.py`, `jamoset.py`를 실행한다).
**서드파티.** `mkfont.py`의 것(Pillow, fontTools). **테스트.** `tools/test_build_faces.py`.

### `tools/build/faces.tsv`

**목적.** `tools/build/build_faces.py`의 레시피 표. `svf/`의 모든 페이스마다 한 행(face, method, source,
args, codepoints, expect, note). `method`는 `mkfont`, `jamoset`, `없음`(위 도구로는 레시피 없음.
note가 이유를 말한다)이다. `codepoints`는 `mkfont.py --unicode` 세트 또는 `tools/build/cps/` 아래 파일(한 줄에 16진 코드 포인트
하나 또는 범위. 페이스 자체의 코드 포인트 목록)을 지명한다. [recipes/svf-faces.ko.md](recipes/svf-faces.ko.md)가 모든 행을 설명하며, `tools/test_build_faces.py`가
표를 완전하게 유지한다.

## 6. 웹(WASM 선택기)

### `web/build.sh`

**목적.** WASM 폰트 선택기를 빌드한다: `svf.js` + `svf.wasm`으로서의 C 렌더러, 페이스 인덱스, 페이스와
라이선스 파일.

**상태.** 범용이다.

**입력.** `c/` 아래의 C 소스, `svf/`, 페이지 소스. emsdk의 emcc가 필요하다.

**출력.** `OUT`(기본 `web/dist`) 아래에: `svf.js`, `svf.wasm`, `faces.json`, `faces/<group>/<FILE>.SVF`,
`licences/<group>/<FILE>`, 그리고 `index.html`, `picker.js`, `style.css`의 사본.

**사용법.** `bash web/build.sh [OUT]`. 환경 변수: `EMSDK`(기본 `~/opt/emsdk`). `web/mkindex.py`와
`web/copyfaces.py`를 호출한다.

**내부 모듈.** 없음(`web/mkindex.py`와 `web/copyfaces.py`를 실행한다). **서드파티.** emscripten
(emsdk의 `emcc`). **테스트.** `tools/test_web_picker.py`(`web/build.sh`를 통해).

### `web/copyfaces.py`

**목적.** `faces.json`이 지명하는 페이스와 라이선스 파일을 `SVF_DIR`에서 `OUT`으로 복사하며, 모든 경로가
루트 아래에 머무는지 검사한다.

**상태.** 범용이다.

**입력.** `SVF_DIR`과 `faces.json`(표준 `json` 모듈로 읽는다).

**출력.** `OUT` 아래에 복사된 페이스와 라이선스 파일(폰트는 바뀌지 않는다).

**사용법.** `python3 web/copyfaces.py SVF_DIR FACES_JSON OUT`(옵션 없음). `F faces, N MB copied`를 출력하며
첫 번째 잘못된 경로에서 종료 코드 2로 끝난다.

**내부 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_web_picker.py`(`web/build.sh`를 통해).

### `web/mkindex.py`

**목적.** `svf/`와 라이선스 및 패밀리 표에서 선택기의 페이스 인덱스인 `faces.json`(형식 `svf-fonts-web-index/1`)을 쓴다.

**상태.** 범용이다.

**입력.** 모든 `svf/**/*.SVF`. `tools/jamoset.py parse_svfn`과 `tools/svfline.py Face`(경로로 로드)로 읽는다.
`LICENCES.tsv`와 `FAMILIES.tsv`(그리고 `svf/jamo-extra/FACES.TSV`).

**출력.** `faces.json`. 페이스당 항목 하나(key, url, group, label, cell, px, bpp, ascent, glyphs, jamo, flags,
bytes, licences, hangul, latin_only, subset, family, style, variant). 폰트는 쓰지 않는다.

**사용법.** `python3 web/mkindex.py SVF_DIR OUT_JSON [--licences TSV] [--families TSV]` 또는
`python3 web/mkindex.py SVF_DIR --check [--licences TSV] [--families TSV]`.

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--check` | 꺼짐 | 모든 검사를 실행하고 아무것도 쓰지 않는다 |
| `--licences TSV` | `LICENCES.tsv` beside this script | 페이스-라이선스 표 |
| `--families TSV` | `FAMILIES.tsv` beside this script | 페이스-패밀리 표 |

**내부 모듈.** `tools/svfline.py`(그리고 그것을 통해 `tools/jamoset.py`). **서드파티.** 없음.
**테스트.** `tools/test_web_picker.py`.

## 7. 파일 안의 폰트를 찾아 잘라 내기

실행 예는 [recipes/programs-and-drivers.ko.md](recipes/programs-and-drivers.ko.md#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기)(DOS TSR, DOS 드라이버),
[recipes/rom-86box.ko.md](recipes/rom-86box.ko.md#한글-vga-폰트-rom-86box)(한글 VGA 폰트 ROM)와 [recipes/os2.ko.md](recipes/os2.ko.md#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기)(OS/2)에 있다. 이 도구들은 바이트만 읽고
파일의 코드를 실행하지 않는다. 내려받은 파일에는 `python3 -I`로 실행하라.

### `tools/binscan.py`

**목적.** 어떤 파일(`.COM`/`.EXE`, TSR, ROM 덤프) 안에서 비트맵 폰트가 어디 있는지 찾고 오프셋에 있는 것을 그려, 사람이나
어시스턴트가 폰트가 어디서 시작하고 어떻게 저장되었는지 볼 수 있게 한다.

**상태.** 범용이다.

**입력.** 아무 파일. 글리프 기하: `--glyph WxH`, `--stride B`(기본은 글리프의 바이트 수), `--order rows`(행 우선, 한 행이 ceil(W/8)
바이트), `strips`(H 바이트짜리 8 픽셀 너비 스트립이 차례로: 한글 VGA 폰트 ROM과 6x2x1 폰트, jamoset의 `g_bytecols`), `cols`(열 우선, MSB가
위: Dokkaebi 프린터 배치), `bytecols`(W 바이트짜리 8행 띠, 바이트 하나가 한 열, 비트 7이 띠의 맨 위 행), `--lsb`(비트 0 = 왼쪽 픽셀,
`cols` / `bytecols`에서는 맨 위), `--invert`(잉크가 0 비트: 삼성 SPC-1500처럼 바탕으로 저장한 ROM). 여러 비트 타일(아케이드
스프라이트와 타일 ROM): `--gfx LAYOUT`, 프리셋 `WxHxN_packed_lsb` / `WxHxN_packed_msb`(픽셀당 N비트, 행 다음 행. `_lsb`는 바이트의 첫
픽셀이 낮은 비트: MAME의 `gfx_16x16x4_packed_lsb`) 또는 드라이버의 MAME `gfx_layout`(참고 문헌 9)을 `planes=..;x=..;y=..;inc=N`으로(타일 시작에서의
비트 오프셋, 비트 0은 첫 바이트의 MSB, `planes`는 펜의 높은 비트부터. MAME의 `STEP2` .. `STEP1024(start,step)`과 그 `_INV` 꼴(같은 오프셋을 거꾸로. MAME에는 `STEP2_INV`와 `STEP4_INV`가 있고, 더 큰 것도 받는다),
`RGN_FRAC(a,b)` = 파일의 a/b(비트), `+ - * /`, 앞에 0이 없는 10진수와 0x 16진. 목록은 중괄호와 C 주석을 빼고 옮긴다. 목록당 오프셋 1,024개,
중첩 32단계, 오프셋 2^36까지). 이때 파일은 ROM 영역이다(`rawcarve.py region`). 펜이 `--bg PEN`(0)이 아니면 잉크이고, `--fg PEN[,PEN...]`이
있으면 그 펜일 때만 잉크다(외곽선이 있는 글리프의 몸통. `--bg`와 `--fg`는 서로 다른 규칙이라 하나만, 그리고 `--gfx`와 함께만 준다). `--invert`는 잉크와 바탕을 바꾼다. `--glyph`의 기본은 타일 크기,
`--stride`의 기본은 `inc`다. `render`는 그리는 바이트만 읽고(`--count` 1..4096, `--cols` 1..64, `--scale` 1..32), `info`는
블록씩 읽는다.

**출력.** stdout의 텍스트. `render --png`는 회색조 PNG를 쓴다(zlib, Pillow 없음).

**사용법.**

    python3 tools/binscan.py info FILE [--block B]
    python3 tools/binscan.py runs FILE (--glyph WxH | --gfx LAYOUT [--bg PEN | --fg PENS]) [--invert] [--min N] [--max-change C] [--start O] [--length N]
    python3 tools/binscan.py sets FILE [--sets NI,NM,NF] [--slots SI,SM,SF] [--glyph WxH] [--invert] [--min-inked F] [--start O] [--length N]
    python3 tools/binscan.py ascii FILE [--height H] [--invert] [--start O] [--length N]
    python3 tools/binscan.py render FILE --offset O (--glyph WxH | --gfx LAYOUT [--bg PEN | --fg PENS]) [--invert] [--count N] [--cols C] [--png OUT --scale S]

기본값: `info --block 4096`, `runs --max-change 2.5`, `sets --sets 8,4,4 --slots 20,22,28`,
`ascii --height 16`. `sets`와 `ascii`의 `--limit N`은 출력 후보 묶음 수를 제한한다(20).
`render`의 기본값은 오프셋 0, 최대 64개 글리프, 너비 12 px 초과이면 8열(그 외 16열), 배율 3이다.

| 명령 | 출력하는 것 |
|---|---|
| `info` | 크기, 종류(적재 이미지와 LZEXE / PKLITE 표시가 있는 DOS MZ, `.COM`, ARJ, ZIP, 옵션 ROM `55 AA`), 파일과 바이트 크기가 맞는 배치, 블록별 엔트로피 지도(바이트당 8비트에 가까우면 압축됨) |
| `runs` | 글리프처럼 보이는 창(잉크 2-60 %, 행끼리 거의 변하지 않음)이 `--min`(32)개 이상 이어지는 구간 |
| `sets` | 원시 자모 조각 폰트의 모든 벌 슬롯 0이 빈 칸이고 다른 슬롯의 `--min-inked`(0.8) 이상에 잉크가 있는 오프셋. 가까이 붙어 통과하는 읽기 묶음 가운데 행이 바이트 이음매(x = 7 / 8)를 가로질러 붙어 있는 것을 고르고, 한 행씩 떨어져 같은 점수를 얻는 읽기들은 순위 없이 함께 나열한다(드라이버 코드나 따로 된 사본으로 정한다) |
| `ascii` | 8xH 영문 폰트의 오프셋: 공백은 빈 칸, `_`는 아래 3분의 1, `-`는 가운데, 0x21-0x7E는 잉크 있음. 묶음 가운데 첫 행이나 마지막 행에 잉크가 있는 글리프가 가장 적은 정렬 |
| `render` | 오프셋부터의 글리프를 번호와 파일 오프셋을 붙인 `#`/`.` 텍스트로, 또는 PNG로 |

`sets`와 `ascii`는 검색 창의 모든 바이트 오프셋을 시도한다. `runs`는 `--step` 간격의 위상을 검사한다. 기본값은 `rows`에서 `ceil(W/8)`, 다른 1 bpp 순서에서 `ceil(H/8)`, `--gfx`에서 타일 스트라이드이다. 모든 바이트 오프셋을 검사하려면 `--step 1`을 준다. `--start O` / `--length N`이 창을 정하고(출력하는 오프셋은 파일
오프셋 그대로), 16 MiB를 넘는 창은 거부한다(큰 파일은 겹치는 창으로 나눠 훑어라). `runs --gfx`는 파일 전체를 읽고(전체 파일도 16 MiB로 제한한다) 창만 훑는다. `runs`와 `render`(기본 `--count`)는 범위 전체가 파일 안에 있는 타일만 쓰며, `sets`는 `--gfx`, `--bg`,
`--fg`를 거부한다(먼저 `rawcarve.py ink`로 잉크 지도를 써라). 한글 VGA 폰트 ROM에는
`--order strips`를 쓴다. 종료 코드 0. argparse 오류(해석되지 않거나 네 키 가운데 하나가 없거나 `inc`가 바이트 단위가 아닌 `--gfx`
배치, 평면 밖의 바탕 펜이나 잉크 펜, 타일과 다른 `--glyph`, `--gfx` 없는 `--fg`, 0이나 음수인 `--block`, `--step`, `--stride`, `--glyph`,
`--count` ...)는 2. **내부 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_extract.py`. `tools/test_tiles.py`(`--invert`,
손으로 만든 타일에 대한 `--gfx` 프리셋과 드라이버의 배치 문자열, `--bg`, `--fg`, 거부).

### `tools/msx1_harvest.py`

**목적.** 한국 MSX1 한글 ROM(모아쓰기 모드)의 음절 배치를 openMSX에서 실행 중인 기계로부터 읽는다: 에뮬레이터가 모든 음절을 찍는 BASIC
프로그램을 치고, 화면마다 이름 표를 덤프한다(recipes/rom-msx.ko.md, 한국 MSX 폰트, MSX1).

**상태.** 특수 목적(대우 / 금성 MSX1 계열). 다른 기종용 틀이 된다.

**입력.** openMSX 기종 이름과 저장소 밖의 출력 접두어. 에뮬레이터는 `--emu DIR`(`DIR/root`에 푼 openMSX, 시스템 ROM은
`DIR/userdata/share/systemroms`) 또는 `--openmsx BIN`. `--first`, `--count`가 음절을 고른다(기본은 11,172자 전부).

**출력.** `PREFIX.tcl`(openMSX 스크립트), `PREFIX.index`(한 줄에 16진 코드 하나), `PREFIX.names`(77자 화면마다 768바이트. 마지막
화면은 그 마지막 음절로 채운다), `PREFIX.patterns`(2,048바이트), `PREFIX.png`(마지막 화면의 날 스크린샷). `msxfont.py msx1-verify`용.

**사용법.** `python3 tools/msx1_harvest.py MACHINE PREFIX (--emu DIR | --openmsx BIN) [--first N] [--count N] [--timeout 600]
[--script-only]`. `timeout T xvfb-run -a openmsx -machine MACHINE -script PREFIX.tcl`을 실행한다. ROM 코드는 에뮬레이터 안에서만
돈다. 저장소 안이거나 공백이나 Tcl 특수 문자가 든 접두어, 에뮬레이터 없음, 덜 된 수집(에뮬레이터의 마지막 줄과 함께)에는 메시지와
함께 종료 코드 1.

**내부 모듈.** 없음. **서드파티.** openMSX와 `xvfb-run`(실행할 때만). **테스트.** `tools/test_msx1_harvest.py`(저장 바이트, 화면과
채움, 치는 프로그램과 Tcl 스크립트, 거부. 에뮬레이터 없이).

### `tools/msxfont.py`

**목적.** 평범한 글리프 표가 아닌 한국 MSX 폰트: 대우 CPC-400 / 400S 완성형 폰트 ROM의 코드-슬롯 대응, 그리고 BIOS의 8x8 셀로
한글 ROM의 배치 규칙대로 만든 한국 MSX1 음절(recipes/rom-msx.ko.md, 한국 MSX 폰트).

**상태.** 특수 목적(한 기종 계열).

**입력.** `kfn-map`: 64 KB `CPC-400S.U44` 이미지(또는 그 마지막 16 KB, "Kanji control ROM"). `msx1`: 한국 MSX1 BIOS(`--offset`의
문자 표, 기본 0x1B49). `msx1-verify`: 에뮬레이터 수집 결과 `PREFIX.index`, `PREFIX.names`, `PREFIX.patterns`(셀 검사에는 `--bios`).

**출력.** `kfn-map`: `rawcarve.py bdf --chars map`이 읽는 `SLOT U+XXXX` 줄(드라이버의 목록 A와 B가 닿는 음절). `msx1`: 11,172 음절
(8x16 또는 16x16, 진행 폭 = 너비)과 ASCII 0x20-0x7E(8x8 셀을 `--ascii-top`행 아래에, 기본 8. `--ascent` 16)의 유니코드 BDF.
`msx1-verify`: 기계가 규칙대로 셀을 그린 음절 수와 BIOS와 같은 패턴 표 셀 수.

**사용법.** `python3 tools/msxfont.py kfn-map U44 -o MAP.txt`, `python3 tools/msxfont.py msx1 BIOS [--offset O] [--ascii-top N]
-o OUT.bdf`, `python3 tools/msxfont.py msx1-verify PREFIX [--bios BIOS]`. 크기가 맞지 않는 파일(읽기 전에 거부), 정렬된 목록이 아닌 시작 오프셋,
0..8 밖의 `--ascii-top`이나 0..16 밖의 `--ascent`, 비었거나 음절이 아닌 코드가 든 수집 색인, 모자란 이름 표, 2,048바이트가 아닌 패턴 표,
다른 음절, (`--bios`가 있으면) 커서 0xFF가 아닌 다른 셀에는 메시지와 함께 종료 코드 1.

**내부 모듈.** `binscan.py`, `rawcarve.py`. **서드파티.** 없음. **테스트.** `tools/test_msxfont.py`(합성 제어 ROM, 셀 표, 수집
결과. 배치의 경우들. `rawcarve.py bdf --chars map`).

### `tools/nkpspec.py`

**목적.** NKP 한글 TSR(1989년 허큘리스 한글 드라이버 NKP.COM V3.00, NKP3.COM)의 `rawcarve.py compose` 명세를 드라이버 자신의 표에서
쓴다: 조각 벌 레코드, 자모 표, 한글 루틴의 초성 벌 표와 중성 선택 표(recipes/programs-and-drivers.ko.md, NKP).

**상태.** 특수 목적(한 드라이버 계열). 다른 드라이버용 "드라이버 표에서 명세로" 스크립트의 모양을 보여 준다.

**입력.** 드라이버의 .COM 이미지. 표 주소는 그것을 쓰는 명령어 바이트로 찾거나(`find`) 메모리 주소로 준다(`--desc`, `--cho`,
`--jung`, `--jong`, `--iset`, `--med`. 파일 오프셋 = 주소 - 0x100).

**출력.** `find`: 표마다 한 줄(메모리 주소, 파일 오프셋. 영문 폰트도). `spec`: JSON 명세(오프셋과 규칙뿐): 플래그 비트 0이 켜진
레코드는 (끝 - 첫) / 2 행의 16 픽셀 조각, 꺼진 레코드는 한 바이트짜리 (끝 - 첫 + 1) / 2 행의 오른쪽(또는 왼쪽) 절반 조각. 초성 벌
표와 중성 표는 레코드를 바이트 오프셋으로 가리킨다(레코드 = 값 / 6). 종성 벌은 레코드 96.

**사용법.** `python3 tools/nkpspec.py find FILE`, `python3 tools/nkpspec.py spec FILE [--desc A ...] -o SPEC.json`. 표가 없거나
파일 밖이거나 NKP 모양이 아니면(자모 표가 유니코드 순서가 아님, 레코드 오프셋이 6의 배수가 아님, 0x100보다 작은 조각 주소, 행이 없는 16 픽셀 레코드) 메시지와 함께 종료 코드 1.

**내부 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(명령어 패턴과 표를 가진 합성 .COM. 명세의
기하와 조합한 음절).

### `tools/rawcarve.py`

**목적.** `binscan.py`로 찾은 폰트를 파일에서 잘라 다른 도구가 읽는 것으로 만든다: 날 바이트, 원시 8x16 영문 폰트, ASCII나 KS X 1001
음절의 유니코드 BDF, 또는 JSON 명세로 적은 규칙대로 조합한 자모 조각 폰트의 음절.

**상태.** 범용이다.

**입력.** 아무 파일. `region`에는 MAME 영역의 ROM 파일들, `compose`에는 명세(아래). 기하 옵션은 `binscan.py`와 같다(`--invert`,
`--gfx`, `--bg`, `--fg` 포함).

**출력.** `cut`: 그 바이트. `eng`: 4,096 바이트(8x16 글리프 256개. 8xH 폰트는 16행으로 채우고 위에 `--top`행), `--width 16`이면 8,192
바이트(16x16 글리프 256개, 한 행 2바이트). `--first C`는 오프셋에 있는 글리프의 코드, `--count N`은 읽을 글리프 수(나머지 코드는 빈 칸), `--invert`는 0 비트를 잉크로 읽는다. `region`: 각
묶음(`A,B[,C,D]`)의 파일을 `--unit` 1, 2, 4바이트씩 번갈아 엮고(MAME의 `ROM_LOAD16_BYTE` / `ROM_LOAD32_BYTE` = 1, `ROM_LOAD32_WORD` /
`ROM_LOAD64_WORD` = 2) 묶음을 차례로 잇는다. `--swap`은 워드마다 두 바이트를 바꾼다(`ROM_LOAD16_WORD_SWAP`). 한 묶음의 파일은 크기가
같고 단위의 배수여야 하며, 최대 64 MiB(읽기 전에 파일 크기로 확인한다. 빈 묶음은 거부한다). `ink`: `--offset`부터의 글리프(`--count`, 기본은 들어가는 만큼
전부. 들어가는 것보다 많으면 거부한다)를 한 글리프에 ceil(W/8) x H
바이트인 평범한 1 bpp 행 우선 글리프로 차례로: 반전되었거나 스트립 순서이거나 여러 비트인 폰트를 `binscan.py sets`, `rawcarve.py cut` /
`eng` / `bdf`, `jamoset.py --layout 844`가 읽는 바이트로 만든다. `bdf`, `compose`:
`CHARSET_REGISTRY "ISO10646"`, `CHARSET_ENCODING "1"`, `PIXEL_SIZE` = 글리프 높이, `FONT_ASCENT` = `--ascent`(기본은 높이의 7/8,
올림)인 BDF. 모든 글리프가 셀 전체이며, 빈 KS 글리프는 뺀다.

**사용법.**

    python3 tools/rawcarve.py cut FILE --offset O --length N -o OUT
    python3 tools/rawcarve.py eng FILE --offset O [--height H] [--top T] [--first C] [--count N] [--width 8|16] [--invert] -o OUT
    python3 tools/rawcarve.py region FILE[,FILE...] [FILE[,FILE...] ...] [--unit 1|2|4] [--swap] -o OUT
    python3 tools/rawcarve.py ink FILE (--glyph WxH [--order O] | --gfx LAYOUT [--bg PEN | --fg PENS]) [--invert] \
        [--offset O] [--count N] -o OUT
    python3 tools/rawcarve.py bdf FILE [--offset O] (--glyph WxH | --gfx LAYOUT) [--invert] \
        --chars ascii|ks-hangul|ks-nonhanja|ks-all [--first C] [--count N] [--dense | --grid L0,T0,PITCH] [--ascent A] -o OUT.bdf
    python3 tools/rawcarve.py bdf FILE [--offset O] --glyph WxH --chars map --map MAP.txt [--ascent A] -o OUT.bdf
    python3 tools/rawcarve.py compose FILE --spec SPEC.json|spc1500 [--invert] [--syllables ks|all] \
        [--eng FILE2 --eng-offset O --eng-height H --eng-top T] [--ascent A] -o OUT.bdf

`bdf --chars ks-*`는 각 KS X 1001 코드를 `--dense`(글리프 i = 그 집합의 i번째 코드: 2,350 음절 덤프) 또는 `--grid L0,T0,PITCH`(글리프 =
(lead - L0) x PITCH + (trail - T0): 전체 표는 `0xA1,0xA1,94`, 한글 VGA ROM은 `0x80,0x80,128`)로 놓는다(lead가 L0보다 작거나 trail이 T0 .. T0 + PITCH - 1 밖인 코드는 거부한다). `--chars map`은 `--map`의 `GLYPH U+XXXX` 줄마다
글리프 GLYPH를 U+XXXX에 놓는다(기계 자신의 순서인 폰트. `msxfont.py kfn-map`이 하나를 쓴다. UTF-8, `#` 주석. 잘못된 줄이나
파일 끝을 넘는 글리프는 파일과 줄을 밝혀 거부한다). 음수 오프셋,
1보다 작은 `--length` / `--stride` / `--count`, 음수 `--first`, 16행을 넘는 `--top` + `--height`는 거부한다. `cut`, `eng`, `bdf`는
쓰는 바이트만 읽고(글리프보다 짧은 `--stride`여도 마지막 글리프의 전체 범위까지), `compose`는 파일 전체(64 MiB까지)를 읽는다. 1..256 밖의 셀, 음수 조각, 없는 벌, 셀을 넘는 `--eng-top` +
`--eng-height`인 compose 명세는 메시지와 함께 거부한다. compose 명세는 조각 벌(`offset`,
`stride`, 저장된 조각이 셀의 어디로 가는지: `x`, `y`, `width`, `height`, `order`, 그리고 선택으로 `lsb`, `invert`, `bg` / `fg`가 있는
`gfx`, 폰트의 번호가 저장된 칸을 건너뛸 때 벌의 조각 번호를 다시 매기는 목록 `slots`. 최상위의 `"invert": true`나 `--invert`는 `"invert": false`라고 적지 않은 모든 벌과 `--eng` 폰트를 반전한다), 종성 없을 때와 있을 때 모음별 초성 벌, 모음별 중성
(벌, 조각)(ㄱ / ㅋ용 다른 표를 둘 수 있다: 8x4x4 규칙), 모음별 종성 벌 또는 벌 하나, 그리고 폰트 자신의 모음 순서를 적는다.
자모 번호는 유니코드의 번호다(형식은 모듈 docstring). `--spec spc1500`(이 이름은 언제나 내장 명세이며, 그 이름의 JSON 파일은 `./spc1500`)은 삼성 SPC-1500 한글 ROM의 내장
명세(`spc1500_spec`, MAME `spc1500.cpp`에서; 참고 문헌 10)이며, `ss150fnt.bin` .. `ss153fnt.bin`을 차례로 이은 32 KB 영역에 쓴다.
`tools/specs/msx2-daewoo.json`은 대우 MSX2 자모 벌 폰트(CPC-300 / 400S ext ROM에서 잘라 낸 9,280바이트 블록, 레시피 참고)의 명세다.
`jamoset.py --layout spec`도 같은 명세를 읽는다. 잘못된 오프셋, 명세, 빈 결과에는 메시지와 함께 종료 코드 1.

`region --group FILE...`은 반복 가능한 묶음 입력이다. `bdf --name`의 기본값은 `carved`,
`compose --name`은 `composed`이다. `bdf`와 `ink`는 `--stride`, `--order`, `--lsb`도 받는다
(기본: 글리프 바이트 수, `rows`, 꺼짐). 쓰기 명령의 `-o`는 `--output`으로도 지정할 수 있다.

**내부 모듈.** `binscan.py`. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(잘라 낸 8x4x4 폰트가 `jamoset.py`로
빌드된다. KS 격자 ROM. 8x4x4 규칙의 compose 명세가 jamoset의 조합과 같다. `tools/specs/msx2-daewoo.json`이 합성 블록에서 따로 적은
대우 규칙과 같다. `slots`). `tools/test_tiles.py`(`eng`, `ink`, `bdf`, `compose`를 거친
반전 폰트. `region`의 엮기, 묶음, 바꾸기. 묶음(packed)과 평면(planar) 타일의 `ink`와 `bdf`. 내장 `spc1500` 명세. `MAME_ROMS`가 있으면
실제 SPC-1500, Date Quiz Go Go, X Se Dae Quiz ROM을 해시로).

### `tools/os2dbcs.py`

**목적.** OS/2 "System DBCS" 폰트(`$korZN16.FNT`, `$korZN24.FNT`. 일본어와 중국어 것도 같은 형식)를 글리프 표로 푼다.

**상태.** 범용이다. 디코딩 형식은 모듈 docstring에 설명되어 있다.

**입력.** System DBCS 파일(헤더 "System DBCS NN"): 0x1A00부터 512 바이트 블록의 레코드. 각 레코드는 허프만 부호의 니블 열이며,
위 두 행의 문맥 표를 거쳐 되돌린다. 레코드는 블록을 넘지 않고 블록의 나머지는 0xFF 채움(글리프 번호 0xFFFF)이다. 헤더는 처음 0x1A00
바이트로 먼저 확인하고 나머지를 읽는다(16 MiB를 넘는 파일은 거부). 메시지와 함께 거부: 표보다 짧은 파일, 1..64 밖의 셀이나
ceil(w / 8) x h가 아닌 글리프당 바이트, 블록이나 파일을 넘는 레코드, 순서가 틀린 글리프 번호, 레코드 페이로드를 넘거나 마지막 바이트
전에 끝나는 부호(데이터와 맞지 않는 레코드 길이), 블록의 채움 표시 뒤의 0xFF 아닌
바이트나 블록 끝에서 잘린 레코드 헤더. 어떤 유효한 부호 열과 우연히 맞는 손상된 길이는 진짜와 가려낼 수 없다.

**출력.** `info`: 헤더(셀, 글리프당 바이트, 리드 바이트, 글리프 번호 범위, 레코드, 있는 음절). `table`: 글리프 번호 256..8997 전부를 차례로
(슬롯 8,742개, 없는 것은 빈 칸), 행 우선: A1A1부터의 KS X 1001 94 x 94 표로, `rawcarve.py bdf --grid 0xA1,0xA1,94`용.

**사용법.** `python3 tools/os2dbcs.py info FILE`, `python3 tools/os2dbcs.py table FILE -o OUT.bin`. 헤더가 없는 파일에는
메시지와 함께 종료 코드 1.

**내부 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(자체 부호표를 가진 합성 폰트: 이스케이프 부호 니블, 항등이 아닌 문맥 표, 여러 블록에 걸친 드문 글리프 번호, 잘못된 파일의 거부.
`JOHAB_FONTS`가 연구 트리를 가리키면 풀어 낸 진짜 `$korZN16.FNT`와 가, 각, 힝의 해시, 그리고 그 노트의 렌더와 가 / 힝 비교).

### `tools/tbmfont.py`

**목적.** 한글 Windows 3.1 / Windows 95의 `.TBM` 비트맵 폰트(`BT16.TBM`, `BT20.TBM`, `GULIM16.TBM`, `GULIM12.TBM`)의 헤더를 읽어
글리프 블록이 시작하는 곳을 `rawcarve.py bdf`용으로 출력하고, 기호와 한자 블록의 KS X 1001 슬롯 맵을 쓴다. 실행 예:
[recipes/windows.ko.md](recipes/windows.ko.md).

**상태.** 특수 목적(한 폰트 형식). 파일 배치는 모듈 docstring에 설명되어 있다.

**입력.** TBM 파일(서명 "TTBITMAP VARIABLE-PITCH HANGEUL", 16 MiB를 넘는 파일은 거부): 셀 크기, 범위 레코드, 7 바이트 글리프 표.
메시지와 함께 거부: 서명이 없는 파일, 두 크기 필드가 다르거나 파일을 넘거나 앞 범위에 이어지지 않는 범위, 온전한 항목으로 나뉘지
않는 글리프 표, 범위에 들어가지 않거나 앞 글리프에 이어지지 않는 글리프.

**출력.** `info`: 크기, 셀, 범위, 글리프, 데이터의 범위와 그 뒤의 바이트, 크기별로 묶은 글리프, 그리고 128 + 8,366 배치이면 ASCII,
기호, 음절, 한자 블록의 오프셋. `map`: 지정한 블록(`--blocks symbols,hangul,hanja`, 기본값)에 대한 `rawcarve.py bdf --chars map`용
"GLYPH U+XXXX" 줄(코드 포인트로 풀리지 않는 슬롯은 뺀다).

**사용법.** `python3 -I tools/tbmfont.py info FILE`, `python3 -I tools/tbmfont.py map [--blocks B,...] -o MAP.txt`. 거부하는
파일에는 메시지와 함께 종료 코드 1.

**내부 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_tbmfont.py`(합성 12, 16, 20 px TBM 파일: 배치, 거부, 슬롯 맵,
페이스까지 가는 레시피의 명령, `doc_figures_windows.py --check`).

### `tools/doc_figures_windows.py`

**목적.** [recipes/windows.ko.md](recipes/windows.ko.md)의 샘플 그림을 그린다. 레시피가 만드는 페이스마다 하나: Windows 3.1 TBM
폰트 BT16과 BT20, Windows 95 TBM 폰트 GULIM16과 GULIM12, Windows 95 `gulim.ttc`의 굴림 16, 12 px 스트라이크, Windows XP 폰트의
굴림 12 px와 바탕 16 px 스트라이크.

**상태.** 특수 목적(문서).

**입력.** 폰트 파일을 인수로 받는다(`--bt16`, `--bt20`, `--gulim16`, `--gulim12`, `--win95-gulim`, `--xp-gulim`, `--xp-batang`).
스크립트에는 폰트 경로가 없고, 준 폰트만 그린다. 페이스마다 임시 폴더에서 레시피의 명령(`tbmfont.py`, `rawcarve.py bdf --invert`,
`bdfface.py`, `mkfont.py`)을 `python3 -I`로 실행해 만든다.

**출력.** `docs/images/recipes/windows/`의 PNG 파일(8비트 회색, 흰 바탕에 검은 글자, 픽셀마다 2배, 메타데이터 없음): 페이스마다
네 줄(한국어 팬그램 두 줄, 영문 한 줄, ASCII 기호와 KS X 1001 기호 16자), 그리고 그림마다 크기와 페이스에 없는 샘플 글자를 알리는
한 줄.

**사용법.**

    python3 -I tools/doc_figures_windows.py [--bt16 F] [--bt20 F] [--gulim16 F] [--gulim12 F] [--win95-gulim F] [--xp-gulim F] [--xp-batang F] [--out DIR] [--check]

`--check`는 메모리에서 그려 `DIR`의 파일과 바이트 단위로 비교한다(다르거나 파일이 없으면 종료 코드 1). TTC 그림은 Pillow와 그
FreeType에 따라 달라진다(출력한다). 저장소의 그림은 Pillow 10.2.0과 FreeType 2.13.2로 만들었다.

**내부 모듈.** `tbmfont.py`, `svfline.py`, `binscan.py`(그리고 실행하는 도구들). **서드파티.** Pillow(`mkfont.py`를 거쳐).
**테스트.** `tools/test_tbmfont.py`(합성 BT16), `--check`.

### `tools/doc_figures_hbios.py`

**목적.** [recipes/dos-fonts.ko.md](recipes/dos-fonts.ko.md#ibm-pc-dos-한글-hbios-v30)의 "IBM PC DOS 한글 (HBIOS V3.0)" 절의 샘플
그림을 그린다: 한국IBM HBIOS V3.0 디스크의 고딕 16 px, 명조 16 px, 명조 24 px 자모 세트와 같은 24 px 파일의 완성형 음절 2,350자.

**상태.** 특수 목적(문서). `tools/doc_figures_windows.py`의 짝으로, 같은 네 줄, 그리기, `--check`(그 `draw`와 `write_or_check`)를 쓴다.

**입력.** `--disk DIR`: 디스크의 폰트 파일이 제 이름으로 든 폴더(`$KGOZN16.FNT`, `$KMYZN16.FNT`, `$KMYZN24.FNT`, `$KSAHN16.FNT`,
`$KROHN16.FNT`, `$KROHN24.FNT`, `$KSPHJ16.FNT`, `$KSPHJ24.FNT`). 스크립트에는 경로가 없고, 파일이 없는 그림은 건너뛴다. 페이스마다
임시 폴더에서 레시피의 명령(`jamoset.py --layout 844` / `844-hbios24 --eng ... --symbols`, `rawcarve.py bdf`, `bdfface.py`, 기호는
`tbmfont.py map` + `rawcarve.py bdf --chars map` + `mkfont.py --only-listed`)을 `python3 -I`로 실행해 만든다. `HBIOS.EXE`와
드라이버는 읽지 않는다.

**출력.** `docs/images/recipes/dos/`의 `hbios-gothic16.png`, `hbios-myeongjo16.png`, `hbios-myeongjo24.png`,
`hbios-myeongjo24-precomposed.png`(8비트 회색, 흰 바탕에 검은 글자, 2배, 메타데이터 없음)와 그림마다 한 줄.

**사용법.**

    python3 -I tools/doc_figures_hbios.py --disk DIR [--out DIR] [--check]

`--check`는 메모리에서 그려 `--out`의 파일과 바이트 단위로 비교한다(다르거나 파일이 없으면 종료 코드 1).

**내부 모듈.** `doc_figures_windows.py`(그리고 그것을 거쳐 `tbmfont.py`, `svfline.py`, `binscan.py`). **서드파티.** Pillow
(`mkfont.py`를 거쳐). **테스트.** `tools/test_tbmfont.py`(합성 HBIOS 디스크), `--check`.

## 8. 레거시 포맷 리더

### `tools/macfbit3.py`

**목적.** HangulTalk 7.1.x의 자모 plane 비트맵 폰트(Seoul12, AppleGothic12, AppleMyungjo12와
24 px의 AppleGothic24 / AppleMyungjo24)를 7.1.2 설치 프로그램의 'splt' "JM" 아카이브 또는 설치된
리소스 포크에서 읽고, 그 KS X 1001 음절을 합성하며, 시트와 `bdfface.py`가 받는 BDF를 쓴다.

**상태.** 연구용 리더. 사용자가 제공한 리소스를 읽는다.

**입력.** JM 아카이브(`<Font>[splt]`의 데이터 포크), 리소스 포크, 또는 원시 'fbit' 리소스. 합성에는
7.1.2 CD의 InputBackSupport 리소스 포크(그 'HTBL' 1. 거기서는 압축되지 않음) 또는 원시 HTBL 1이 쓰인다.
포맷은 모듈 docstring에 있다. JM = 0x1e에서 시작하는 LHA -lh5-(ar002) 스트림과 바이트 합 체크섬. fbit type 3 =
`0x4E + 6 * range_count`부터 시작하는(범위 하나이면 0x54) 482개의 h x h plane(2 bank x 241). HTBL 1 = 코드마다 4바이트 항목 하나 [bank][g1][g2][g3], plane들을 OR한다.
복원할 규칙은 없다. 표 자체가 합성이며, 2,350개 KS 음절과 51개 호환 자모
(A4A1..A4D3)만 존재한다.

**출력.** `unpack`: 풀어낸 리소스 포크. `fbit`: 'fbit' 리소스. `info`: 한 줄(type, 셀, plane
개수, 합성 가능한 코드). `sheets`: 회색조 PNG 넷, `PREFIX_glyphs_x1/_x4.png`(모든 plane, 한 줄에 32개)와
`PREFIX_ks2350_x1/_x4.png`(합성된 2,350개 음절, 한 줄에 94 / 47개). `bdf`: 글리프 2,401개, h x h 셀,
`CHARSET_REGISTRY "ISO10646"`, 유니코드 `ENCODING`, `STARTCHAR KS<code>`.

**사용법.**

    python3 tools/macfbit3.py unpack SPLT.data OUT
    python3 tools/macfbit3.py fbit SRC OUT
    python3 tools/macfbit3.py info FONT [HTBLSRC]
    python3 tools/macfbit3.py sheets FONT HTBLSRC OUTPREFIX
    python3 tools/macfbit3.py bdf FONT HTBLSRC NAME OUT.bdf

**내부 모듈.** 없음. **서드파티.** 없음.
**테스트.** `tools/test_macfbit3.py`(합성 데이터. `MACFBIT3_CD712=<extracted CD tree>`를 주면 CD
파일에 대한 검사가 추가된다).


### `tools/hwpfont.py`

**목적.** DOS용 한글(HWP) 1.x와 3.0의 비트맵 폰트와 헤더 없는 KS X 1001 음절 덤프를 읽는다. 파일이 무엇인지 말하고, HWP 1.x
페이스의 음절을 HWP.EXE의 규칙으로 조합하고, 파일의 글리프를 `mkfont.py`와 `bdfface.py`가 받는 유니코드 BDF(참고 문헌 11)로 쓴다.
`jamoset.py --layout hwp1` / `844-hwp3`와 그 HWP `--eng`가 이 도구를 통해 파일을 읽는다.

**상태.** 연구용 리더. 사용자가 제공한 파일의 바이트를 읽는다(`python3 -I`로 실행한다).
HWP 1.x 조합 규칙은 `L_CLS`, `V_CLS`, `T_CLS`, `SEL`에 정의되어 있다.

**입력.** HWP 1.x `.SFT` / `.PFT`(32 바이트 "HWP Font Editor v1.0" 또는 "FE" 헤더, 크기는 정확히 32 + 글리프 수 x 글리프 바이트.
화면 폰트는 행 우선, 프린터 폰트는 열 우선): `HANGUL.SFT`(16x16, 글리프 1,193개, 조각 31/29/31개짜리 초성/중성/종성 벌이 10/4/4,
7/2/2, 6/2/2인 페이스 셋), `HANGUL1/2/3.PFT`(24x24, 980개; 7/2/3, 7/2/2, 5/2/2), `ASCII.SFT` / `ASCII.PFT`(8x16 / 14x24, 991개:
147개짜리 페이스 여섯), `HANJA.SFT`(4,888개), 기호 파일(`other`). HWP 3.0 `.FNT`(72 바이트 "FNT" 01 헤더: 형식 0 영문, 1 한글,
2 한자. 6과 8에 LE16 폭과 높이. 행 우선 글리프): `HAN*.FNT`는 KS X 1001 음절 2,350자(16 px는 360개 조각으로 이루어진 8x4x4 벌 체계 추가),
`ENG*.FNT`는 0x20부터의 코드, `HAJ16_0.FNT`는 한자. 글리프 수는 본문의 것이며, 헤더와 다르면 `info`가 알린다(HAN24는 2,710이라 적고 2,350을, ENG40은
147이라 적고 96을 담는다). 0x20-0x7E의 95자에 못 미치는 영문 FNT는 거부한다. 글리프 순서는 파일 이름이 아니라 높이를 따른다: 24행인
HWP 1.x 폰트는 열 우선이다. KS 원시: 16, 24, 32, 40, 48 px 정사각형 글리프 정확히 2,350개인 헤더 없는 파일
(75,200 / 169,200 / 300,800 / 470,000 / 676,800 바이트)로, 첫 글리프와 마지막 글리프에 잉크가 있고 서로 달라야 한다. 그 밖의 것과
16 MiB를 넘는 파일은 거부한다. `--ascii`는 `jamoset.py --eng`가 읽는 어떤 영문 폰트든 받는다.

**출력.** `info`: 한 줄(계열 `HWP 1.x font` / `HWP 3.0 FNT` / `KS X 1001 raw dump`, 종류, 글리프 수와 크기, 페이스들의 벌 수,
HWP 3.0 폰트의 이름, 8x4x4 꼬리). `bdf`: BDF 2.1(`CHARSET_REGISTRY "ISO10646"`, `PIXEL_SIZE` = 셀 높이, `ENCODING` = 코드
포인트, `STARTCHAR U+XXXX`): 한글 파일은 음절(KS X 1001 2,350자. HWP 1.x 페이스는 `--syllables all`로 11,172자 전부), 영문 파일은
U+0020..U+007E(advance = 글리프 폭), 한자 파일은 한자 4,888자. `--ascii`를 주면 그 영문 폰트의 ASCII도 넣는다(셀보다 낮으면 높이
가운데에, 자신의 advance로). ascent는 `--ascent`, 없으면 영문 페이스의 기준선(`H` 잉크 아래 행), 그것도 없으면 셀의 7/8이다.
파일에 U+0020이 없으면 빈 U+0020(셀 폭의 절반)을 쓴다. FreeType은 BDF의 첫 글리프를 `.notdef`로 보고 `mkfont.py`는 그것과 같은 글리프를 모두 버리므로, 그러지 않으면 U+AC00이 빠진다.
요약 한 줄(`wrote OUT: 2350 Hangul syllables, 95 ASCII of 14x24 from ASCII.PFT; cell 24x24, ascent 20`).

**사용법.**

    python3 -I tools/hwpfont.py info FILE
    python3 -I tools/hwpfont.py bdf FILE [--face N] [--syllables ks|all] [--ascii ENG [--ascii-face N]] [--ascent A] [--name NAME] -o OUT.bdf

`--face`는 HWP 1.x 한글 파일의 페이스(0..2) 또는 HWP 1.x ASCII 파일의 페이스(0..5)이다. 종료 코드 0, 또는 `hwpfont.py: <이유>`와
함께 1(어느 형식도 아님, 헤더와 맞지 않는 크기, 범위를 벗어난 페이스, 쓸 것이 없는 파일).

라이브러리로: `read(data)`(`Font`: `family`, `kind`, `w`, `h`, `count`, 행 정수로 된 `glyph(i)`, `jamo844`, `table`),
`Hwp1Hangul(font, face)`(`pieces(cp)`, `syllable(cp)`, 그리고 JSET 벌 함수로 쓴 규칙 `lead_class`, `init_set`, `med_set`,
`fin_set`, `init_src`, `med_src`, `fin_src`), `syllables`, `ascii_glyphs`, `hanja_glyphs`, `english(path)`, `ks_hangul()`,
`ks_hanja()`, `ks_raw_px(size)`.

**내부 모듈.** `rawcarve.py`(`bdf_text`), `jamoset.py`(`--ascii`의 `read_eng`). **서드파티.** 없음. **테스트.**
`tools/test_hwpfont.py`(합성 파일. `JOHAB_FONTS=<연구 트리>`이면 실제 HWP 1.20, HWP 3.0, 태백 파일의 해시 검사가 더해진다).

### `tools/macsfnt.py`

**목적.** Mac 형식 TrueType을 다른 도구들이 쓸 수 있게 한다. 리소스 포크(.dfont, suitcase의 포크, AppleDouble `._` 파일, MacBinary)의 'sfnt' 리소스를 나열하고 추출하며, 폰트의 cmap 서브테이블을 보고하고, Mac Korean(platform 1, script 3) 또는 Windows Wansung(3, 5) cmap만 있는
폰트에 유니코드 cmap을 추가한다.

**상태.** 범용이다. 사용자가 제공한 파일을 읽는다.

**입력.** 일반 파일로서의 리소스 포크(또는 AppleDouble / MacBinary로 감싼 것). `cmap`과 `unicode`에는 sfnt 폰트.

**출력.** `list`: 폰트 리소스당 한 줄(`TYPE<TAB>ID<TAB>NAME<TAB>BYTES`, 타입 sfnt, NFNT, FONT, FOND, fbit).
`extract`: .ttf로서의 'sfnt' 리소스. `cmap`: 서브테이블 하나당 `platform=P encoding=E format=F entries=N hangul=H`.
`unicode`: 각 두 바이트 코드를 EUC-KR(KS X 1001)로 디코딩해 만든 (3,1) format 4 서브테이블(코드 포인트가 U+FFFF를 넘으면 (3,10) format 12도)을 가진 폰트의 사본.
폰트에 이미 유니코드 서브테이블이 있으면 거부된다.

**사용법.**

    python3 tools/macsfnt.py list FILE
    python3 tools/macsfnt.py extract FILE OUT.ttf [--id N]
    python3 tools/macsfnt.py cmap FONT
    python3 tools/macsfnt.py unicode FONT OUT.ttf

종료 코드 0, 또는 메시지와 함께 1(리소스 포크가 아님, 'sfnt' 리소스 없음, 한국어 cmap 없음, 유니코드 cmap이 이미 있음).

**내부 모듈.** 없음. **서드파티.** fontTools(`cmap`, `unicode`). **테스트.** `tools/test_macsfnt.py`
(Mac Korean cmap을 가진 합성 폰트와 테스트에서 만든 리소스 포크. fontTools 자체의
리소스 리더와도 대조했다).

## 9. 레시피: 입력 포맷에서 SVF로

입력 포맷별 지원 범위, 실행 예와 Maker 변환 경로는 [레시피](recipes.ko.md)를 참고한다.
TTF/OTF, TTC, 가변 폰트, Mac 폰트, BDF/PCF/HBF, DOS 원시 폰트와 기존 SVF를 다룬다.

<a id="도구에-남은-빈틈"></a>

## 10. 도구의 제약

- `mkfont.py`에는 `--unicode` 또는 `--chars-from`이 필요하며, 항상 메트릭 표를 쓴다.
  같은 전진 폭을 가진 글리프만 있어도 메트릭 표는 생략하지 않는다.
- `jamoset.py`의 옵션은 모드에 따라 적용 여부가 다르다. 위의 모드별 표를 참고한다.
- `jamoset.py --from-ttf --binarize mono`와 마스크 폰트 경로는 freetype-py와 uharfbuzz가 모두 필요하다.
  마스크 없이 `--binarize threshold|ridge` 또는 `--bpp 2`를 쓰는 아웃라인 경로는 fontTools를 사용한다.
- `mkfont.py`가 FreeType으로 여는 비트맵 폰트는 내장 스트라이크 크기를 사용한다.
  더 작은 비트맵이 필요하면 `svfscale.py`를 쓴다. 스트라이크 탐지는 `maker/detect.py`의 `bitmap_strikes`가 담당한다.
- `hwpfont.py`는 HWP `.HFT`를 지원하지 않는다. 지원하는 `.SFT`, `.PFT`, `.FNT`와 원시 덤프의 조건은 위 표를 참고한다.
- `svfscale.py --bpp 2`는 더 큰 1 bpp 비트맵을 축소한다. 같은 크기의 1 bpp 비트맵에서 중간 커버리지를 복원하는 기능은 없다.
  `mkfont.py --bpp 2`는 BDF/PCF도 열지만, 원래 이진 비트맵에 없던 가장자리 정보를 복원하지는 않는다.
  `jamoset.py --bpp 2`는 `--from-ttf`만 받으므로 비트맵에서 2 bpp 자모 세트를 직접 맞추지는 못한다.
- `mkfont.py --probe`는 주어진 크기의 잉크에 맞는 셀을 구하고, `--fit-cell`은 주어진 셀에 맞게 크기를 줄인다.
  대상 디스플레이의 줄 간격과 셀 크기는 호출자가 정해야 한다.
- 공통 라이브러리 API는 없다. `bdfface.build`, `jamoexc.build`, `svf2ttf.build_ttf`처럼 반환값을 주는 개별 함수는 있다.
  Maker는 `maker/toolrun.py`를 통해 도구를 하위 프로세스로 실행한다. 입력 탐지와 커버리지 보고는
  `maker/detect.py` 및 [Maker 데스크톱](maker-desktop.ko.md)을 참고한다.

## 11. 참고 문헌

1. [Unicode Standard: Hangul syllables](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/#G3307)
2. [Unicode: CP949 mapping](https://www.unicode.org/Public/MAPPINGS/VENDORS/MICSFT/WINDOWS/CP949.TXT)
3. [Pillow: ImageFont.truetype](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype)
4. [FreeType: Glyph Retrieval](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html)
5. [OpenType: EBDT](https://learn.microsoft.com/en-us/typography/opentype/spec/ebdt)
6. [OpenType: EBLC](https://learn.microsoft.com/en-us/typography/opentype/spec/eblc)
7. [OpenType: cmap](https://learn.microsoft.com/en-us/typography/opentype/spec/cmap)
8. [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/)
9. [MAME: graphics layout definitions](https://raw.githubusercontent.com/mamedev/mame/master/src/emu/drawgfx.h)
10. [MAME: SPC-1500 driver](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/samsung/spc1500.cpp)
11. [Adobe: Glyph Bitmap Distribution Format (BDF) 2.2](https://adobe-type-tools.github.io/font-tech-notes/pdfs/5005.BDF_Spec.pdf)
12. [iolo: 8x4x4 fonts](https://github.com/iolo/8x4x4-fonts)
