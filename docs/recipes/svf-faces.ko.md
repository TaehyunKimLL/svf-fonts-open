[English](svf-faces.md) | **한국어**

# 레시피: svf/의 페이스

`svf/`에 든 페이스마다 만드는 법과 다시 빌드하는 법(`tools/build/faces.tsv`, `tools/build/build_faces.py`): 완성형 레시피와 완성형에서 자모 세트를 만드는 레시피, 패밀리, 레시피 없는 페이스, 그리고 새 페이스와 함께 추가할 것.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. 상류 폰트는 `ttf/`에 있다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [아웃라인 폰트](outline-fonts.ko.md), [기존 SVF, 그리고 SVF에서 다시 TTF로](svf-and-ttf.ko.md), [NOTICE](../../NOTICE.ko.md).

<a id="svf의-페이스"></a>

## svf/의 페이스

<a id="svf-페이스-다시-빌드하기"></a>

`tools/build/faces.tsv`에는 `svf/`의 페이스마다 한 행씩(117행) 있고, `tools/build/build_faces.py`가 이를 실행해 각 결과를 배포된
페이스와 비교한다.

    python3 tools/build/build_faces.py --out $OUT/rebuild                      # every row with a recipe
    python3 tools/build/build_faces.py --out $OUT/rebuild NGOTB15 GBATB23      # some faces
    python3 tools/build/build_faces.py --out $OUT/rebuild --ext nanumgothic-nhn=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf

출력의 각 줄은 `FACE identical`, `FACE pixels`(글리프와 헤더 값은 같고 바이트 순서만 다름), `FACE differs: ...` 중 하나이다.
`identical`로 표시된 행이 그렇지 않으면 실행은 종료 코드 1로 끝난다.

**범위(verified, 2026-11-22).** 페이스 117개:

| 상태 | 페이스 | 개수 |
|---|---|---:|
| `ttf/`의 폰트에서 바이트 단위로 동일하게 다시 빌드됨 | 아래의 mkfont와 jamoset 행 중 바로 다음에 나오는 것을 제외한 전부 | 45 |
| 외부 OFL 폰트로 바이트 단위로 동일하게 다시 빌드됨 (`--ext nanumgothic-nhn=`, NAVER 원본 배포의 힌팅된 NanumGothicBold.ttf 3.021, Debian의 `fonts-nanum`이 싣는 것) | NGOTB17, NGO17X1, NGO17X2 (`--mono-hint`), NGO15X2, NGO16BX2, NGO21AX2 (글리프 둘은 `--fallback-ttf`로) | 6 |
| 다시 빌드됨, 글리프 하나가 다름 | NEODG16 (배포된 페이스에는 neodgm.ttf에 없는 U+212B도 있다), NGOTB16 (이 NanumGothic-Bold.ttf에 없는 U+3000도 있다); 나머지 글리프는 모두 동일 | 2 |
| 문서화만 됨 (이 저장소의 도구로는 레시피 없음) | [레시피 없는 페이스](#레시피-없는-페이스) 참고 | 64 |

<a id="완성형-글리프-레시피-mkfont-행"></a>

### 완성형 글리프 레시피 (`mkfont` 행)

    python3 tools/mkfont.py SOURCE.ttf OUT.tmp --size S --cell H --width W --bpp B --ascent A --clip-cell \
        [--mono-hint] [--fallback-ttf OTHER.ttf] --only-listed --unicode CODEPOINTS
    python3 tools/svf2to3.py OUT.tmp OUT.SVF --profile default

- `--size S`: 폰트를 그리는 픽셀 크기(Pillow/FreeType `truetype(font, S)`). 페이스 이름에 이 값이 들어간다(`GBATB23` = Gowun
  Batang Bold 23 px).
- `--cell H --width W`: 셀. 크기보다 클 수 있다(게임의 줄 간격. `GBATB17B`는 26x24 셀 안의 17 px).
- `--bpp B`: 1(절반 커버리지에서 자르기, 또는 `--mono-hint`를 준 FreeType의 모노크롬 렌더러) 또는 2(커버리지 4단계:
  `level = (coverage * 3 + 127) // 255`).
- `--ascent A`: 셀 위쪽에서 기준선까지의 행. `--clip-cell`: 모든 글리프가 그 기준선 위에 서고 셀 밖으로 나간 잉크는 잘린다(표준
  출력에 개수가 나온다). 이 옵션이 없으면 위로 넘치는 글리프는 대신 아래로 옮겨진다([기준선, 세로 이동, 클리핑](outline-fonts.ko.md#기준선-세로-이동-클리핑) 참고).
- `--mono-hint`: 폰트의 TrueType 힌팅을 쓰는 1 bpp(Pillow의 `fontmode "1"`을 거친 FreeType `FT_LOAD_TARGET_MONO`). 줄기가 정수
  픽셀에 맞춰진다. 힌팅된 폰트가 필요하며, NHN 원본 NanumGothicBold.ttf는 힌팅되어 있고 Google Fonts 빌드는 그렇지 않다.
- `--fallback-ttf`: 폰트에 없는 코드 포인트를 두 번째 폰트에서 그린다(여기서는 NGO*X2 보충 페이스의 â와 é).
- `--only-listed --unicode CODEPOINTS`: 나열한 코드 포인트만 정확히 담는다(행의 `tools/build/cps/FACE.txt`, 그 페이스 자신의
  목록. 부분 집합 페이스의 목록은 게임의 텍스트에서 나왔으며 그 텍스트는 이 저장소에 없다).
- `svf2to3.py --profile default`: mkfont는 레코드를 자기 순서로 쓴다. 배포된 페이스는 v2 -> v3 변환을 거쳤고, 이 변환은 레코드를
  `default` 프로필의 정규 순서로 쓴다. 새로 구운 것을 다시 배치해도 같은 바이트가 나온다.

<a id="완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행"></a>

### 완성형 글리프에서 자모 세트를 만드는 레시피 (`jamoset` 행)

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf $OUT/PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf $OUT/PRE.svf --mask-font none -o $OUT/NEODG16A.SVF --layout 844

`--from-svf`는 1 bpp 페이스의 완성형 음절을 벌 체계(여기서는 8x4x4)의 조각으로 분해하고, 그 밖의 글리프는 그대로 둔다.
Neo Dunggeunmo는 그 자체가 8x4x4 조각의 OR로 그려져 있어서 맞춤이 정확하고(IoU 1.000) 11,172개 음절이 모두 조합된다.
NEODG16D/E/F/32/32A는 셀만 다른 같은 방식이다(22x22, 18x24, 20x24; 36x36 안의 32 px와 46x54). NEODG16G는 6x2x1 벌 체계이다
(`--layout 621 --advance 0 --check`, `--ascent`/`--clip-cell` 없음: mkfont의 ascent 12), 10,684 바이트이며 MCU 예제용 작은
페이스이다(완성형 변환 결과와의 IoU 0.958).

<a id="패밀리"></a>

### 패밀리

| 패밀리 | 페이스 | 업스트림, 버전 | 라이선스 | 레시피 상태 |
|---|---|---|---|---|
| NanumGothic Bold | NGOTB*, NGO*X? | Google Fonts `ofl/nanumgothic` (3.020), `ttf/nanumgothic`에 있음; 1 bpp 힌팅 페이스는 NHN 원본 3.021 | OFL 1.1, RFN "Nanum", "NanumGothic" ... | verified (16 + 외부 6), NGOTB16은 글리프 하나 다름 |
| Gowun Batang Bold | GBATB*, GBA*X? | https://github.com/yangheeryu/Gowun-Batang (Google Fonts `ofl/gowunbatang`, 2.000), `ttf/gowunbatang`에 있음 | OFL 1.1 | verified (16); GBATB17O는 문서화만 됨 |
| Neo Dunggeunmo | NEODG*, NEO16BX2 | https://github.com/neodgm/neodgm v1.601, `ttf/neodgm`에 있음 | OFL 1.1, RFN "Neo둥근모", "NeoDunggeunmo" ... | verified (완성형 5, 자모 세트 7), NEODG16은 글리프 하나 다름; NEODG16B/C/O는 문서화만 됨 |
| Black Han Sans | BHSAN28 | https://github.com/zesstype/Black-Han-Sans (1.001), `ttf/blackhansans`에 있음 | OFL 1.1 | verified |
| Coustard | COUSB24 | https://github.com/googlefonts/coustardFont (1.100), `ttf/coustard`에 있음 | OFL 1.1 | verified |
| Diphylleia | DIPHY36 | https://github.com/JAMO-TYPEFACE/Diphylleia | OFL 1.1 | 문서화만 됨 |
| Paperlogy | PAPLG16, PAPLG18, PAPER*, PAPLB* | https://github.com/fonts-archive/Paperlogy (designptn.com), 1.000 | OFL 1.1 | 문서화만 됨 |
| MaruBuri | MARU* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 | 문서화만 됨 |
| NanumSquareRound | NSQR* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 (NAVER의 Nanum 라이선스) | 문서화만 됨 |
| Gothic A1 | GOTHB18A, GOTHA*, GOTHB* | HanYang I&C (Google Fonts `ofl/gothica1`, 2.50) | OFL 1.1 | 문서화만 됨 |
| Single Day | SGDAY* | DXKorea (Google Fonts `ofl/singleday`, 1.00) | OFL 1.1 | 문서화만 됨 |
| Neo Dunggeunmo Pro | NDGPR* | https://github.com/neodgm/neodgm-pro 1.020 | OFL 1.1 | 문서화만 됨 |

모든 페이스는 라이선스 텍스트를 `svf/` 안의 옆자리에 둔다(`web/LICENCES.tsv`가 그 이름을 적는다). 노트 `svf/dos/*.TXT`와
`svf/jamo-extra/FACES.TSV`가 각 페이스를 설명한다.

<a id="레시피-없는-페이스"></a>

### 레시피 없는 페이스

- `svf/iolo/SANS8J.SVF`: iolo 레거시 8x4x4 SANS `.fnt`의 외부 변환본이며 원본 파일은 포함하지 않는다.

이 페이스들은 빌드된 그대로 보관한다. 이유는 `tools/build/faces.tsv`의 행에 적혀 있다. 이는 재현상의 한계이다.
원본별 라이선스는 [LICENCES.tsv](../../web/LICENCES.tsv)를 따르고, iolo의 이중 라이선스 해석 문제는
[IOLO.TXT](../../svf/iolo/IOLO.TXT)를 참고한다.

- **연구 파이프라인으로 만든 자모 세트** (`svf/dos`의 PAPER*, PAPLB*, PAPLG18, MARU*, GOTHB18A, NSQR*와 `svf/jamo-extra`의 모든
  페이스): 음절 윤곽선을 초성 / 중성 / 종성 벡터 조각으로 분리하고, 래스터화하고, 사용 가중치와 함께 24/16/16 벌 및 최대
  12 x 12 클래스로 병합하는 일을, 이 저장소에 속하지 않는 연구 파이프라인이 했다(`svf/dos/PAPLG.TXT`, `PAPMARU.TXT`,
  `svf/jamo-extra/FACES.TSV`에 실행과 품질이 기록되어 있다). 여기서 가장 가까운 도구는 `jamovec.py`(벡터 분리)와
  `jamoset.py --layout adaptive`(분할 벌)이다. [TrueType와 OpenType 폰트에서 만드는 자모 세트](outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- **외곽선 페이스** NEODG16O, GBATB17O: 16 / 17 px 글리프를 2 px 팽창시킨 것(내레이션 아래에서 검게 그려짐). 게임 전용 장식
  스크립트로 만들었으며 그 스크립트는 이 저장소에 없다.
- **NEODG16B, NEODG16C**: 완성형 원본이 한 게임의 문자만 변환한 것이었던 Neo Dunggeunmo의 8x4x4 세트이다.
  KS X 1001 전체에 `jamoset.py --from-svf`를 적용하면 다른 조각에 맞춰진다(NEODG16B의 글리프 441개 중 71개가 다르다).
- **DIPHY36**: 36 px 1 bpp의 Diphylleia Regular로, 외부 파이프라인이 래스터화했다. Diphylleia의 현재 릴리스에 `mkfont.py`를
  쓰면 다른 픽셀이 그려진다(글리프 2,359개 중 2,358개).
- **PAPLG16**: Paperlogy 1.000에 `mkfont.py Paperlogy-4Regular.ttf --size 16 --cell 18 --width 18 --bpp 2 --clip-cell --ascent 14
  --unicode ascii,2026,2122,3131-318e --only-listed --space-advance 6 --punct-extra 1`. 1.001 릴리스는 글리프 149개 중 81개를
  다르게 그리며, 어느 쪽도 `ttf/`에 없다.


<a id="svf에-페이스-추가하기"></a>

## svf/에 페이스 추가하기

레시피([레시피 문서](../recipes.ko.md#레시피-문서))로 페이스를 만들고, 점검하고([페이스 점검](../recipes.ko.md#페이스-점검)), 다음을 추가한다.

- `svf/`에 그 옆의 라이선스 텍스트;
- `web/LICENCES.tsv`의 행과 `web/FAMILIES.tsv`의 행;
- `tools/build/faces.tsv`의 행(레시피를 적거나, 방법 `none`과 그 이유를 적음).

그렇지 않으면 `tools/test_build_faces.py`와 `tools/test_web_picker.py`가 실패한다. maker는 이 표들에 넣을 줄을 만들어 준다
(`build-<id>/LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`).

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
