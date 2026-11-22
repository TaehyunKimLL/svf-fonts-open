[English](recipes.md) | **한국어**

# 레시피: 폰트에서 SVF 페이스(face)까지

`svf/`의 페이스를 업스트림 폰트에서 만든 방법과, 이 저장소의 도구로 다른 종류의 한글 폰트에서 페이스를 만드는 방법을 설명한다.
모든 도구는 [tools.md](tools.ko.md)에 설명되어 있고, 포맷은 `spec/SVF.md`이다.

`ttf/`의 OFL 폰트와 `svf/`의 페이스 외에는 어떤 폰트 데이터도 이 저장소에 없다. 독점 폰트(클래식 Mac, HWP, 그 밖의 DOS 시대
폰트)의 사용법은 방법과 명령만 설명하며, 파일은 직접 마련해야 한다. **verified**로 표시한 사용법은 적힌 그대로 실행했고, 그 시험은
`tools/test_recipes.py`, `tools/test_build_faces.py`, `tools/test_macsfnt.py`이다(시험 안에서 만든 합성 폰트와 `ttf/`의 OFL 폰트를
쓴다). 아래에 인용한 수치는 2026-11-03의 실제 실행에서 나온 것이다(출력은 `/tmp`에 있다). 실행하지 않은 것은 그렇다고 적었다.

목차:

- [svf/ 페이스 다시 빌드하기](#svf-페이스-다시-빌드하기)
- [TrueType와 OpenType 폰트에서 만드는 자모 세트](#truetype와-opentype-폰트에서-만드는-자모-세트)
- [안티에일리어싱된 (2 bpp) 페이스](#안티에일리어싱된-2-bpp-페이스)
- [기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑)
- [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트)
- [HWP 1.x와 2.x 폰트](#hwp-1x와-2x-폰트)
- [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트)
- [X Window 한글 폰트](#x-window-한글-폰트)
- [KS X 1001](#ks-x-1001)
- [Mac 형식 TrueType](#mac-형식-truetype)
- [OpenType CFF, 컬렉션, 가변 폰트](#opentype-cff-컬렉션-가변-폰트)
- [새 페이스 점검](#새-페이스-점검)

## svf/ 페이스 다시 빌드하기

`tools/build/faces.tsv`에는 `svf/`의 페이스마다 한 행씩(116행) 있고, `tools/build/build_faces.py`가 이를 실행해 각 결과를 배포된
페이스와 비교한다.

    python3 tools/build/build_faces.py --out /tmp/rebuild                      # every row with a recipe
    python3 tools/build/build_faces.py --out /tmp/rebuild NGOTB15 GBATB23      # some faces
    python3 tools/build/build_faces.py --out /tmp/rebuild --ext nanumgothic-nhn=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf

출력의 각 줄은 `FACE identical`, `FACE pixels`(글리프(glyph)와 헤더 값은 같고 바이트 순서만 다름), `FACE differs: ...` 중 하나이다.
`identical`로 표시된 행이 그렇지 않으면 실행은 종료 코드 1로 끝난다.

**범위(verified, 2026-11-03).** 페이스 116개:

| 상태 | 페이스 | 개수 |
|---|---|---:|
| `ttf/`의 폰트에서 바이트 단위로 동일하게 다시 빌드됨 | 아래의 mkfont와 jamoset 행 중 바로 다음에 나오는 것을 제외한 전부 | 45 |
| 외부 OFL 폰트로 바이트 단위로 동일하게 다시 빌드됨 (`--ext nanumgothic-nhn=`, NAVER 원본 배포의 힌팅된 NanumGothicBold.ttf 3.021, Debian의 `fonts-nanum`이 싣는 것) | NGOTB17, NGO17X1, NGO17X2 (`--mono-hint`), NGO15X2, NGO16BX2, NGO21AX2 (글리프 둘은 `--fallback-ttf`로) | 6 |
| 다시 빌드됨, 글리프 하나가 다름 | NEODG16 (배포된 페이스에는 neodgm.ttf에 없는 U+212B도 있다), NGOTB16 (이 NanumGothic-Bold.ttf에 없는 U+3000도 있다); 나머지 글리프는 모두 동일 | 2 |
| 문서화만 됨 (이 저장소의 도구로는 레시피 없음) | [레시피 없는 페이스](#레시피-없는-페이스) 참고 | 63 |

### 미리 조합된 글리프 레시피 (`mkfont` 행)

    python3 tools/mkfont.py SOURCE.ttf OUT.tmp --size S --cell H --width W --bpp B --ascent A --clip-cell \
        [--mono-hint] [--fallback-ttf OTHER.ttf] --only-listed --unicode CODEPOINTS
    python3 tools/svf2to3.py OUT.tmp OUT.SVF --profile default

- `--size S`: 폰트를 그리는 픽셀 크기(Pillow/FreeType `truetype(font, S)`). 페이스 이름에 이 값이 들어간다(`GBATB23` = Gowun
  Batang Bold 23 px).
- `--cell H --width W`: 셀. 크기보다 클 수 있다(게임의 줄 간격. `GBATB17B`는 26x24 셀 안의 17 px).
- `--bpp B`: 1(절반 커버리지에서 자르기, 또는 `--mono-hint`를 준 FreeType의 모노크롬 렌더러) 또는 2(커버리지 4단계:
  `level = (coverage * 3 + 127) // 255`).
- `--ascent A`: 셀 위쪽에서 기준선까지의 행. `--clip-cell`: 모든 글리프가 그 기준선 위에 서고 셀 밖으로 나간 잉크는 잘린다(표준
  출력에 개수가 나온다). 이 옵션이 없으면 위로 넘치는 글리프는 대신 아래로 옮겨진다([기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑) 참고).
- `--mono-hint`: 폰트의 TrueType 힌팅을 쓰는 1 bpp(Pillow의 `fontmode "1"`을 거친 FreeType `FT_LOAD_TARGET_MONO`). 줄기가 정수
  픽셀에 맞춰진다. 힌팅된 폰트가 필요하며, NHN 원본 NanumGothicBold.ttf는 힌팅되어 있고 Google Fonts 빌드는 그렇지 않다.
- `--fallback-ttf`: 폰트에 없는 코드 포인트를 두 번째 폰트에서 그린다(여기서는 NGO*X2 보충 페이스의 â와 é).
- `--only-listed --unicode CODEPOINTS`: 나열한 코드 포인트만 정확히 담는다(행의 `tools/build/cps/FACE.txt`, 그 페이스 자신의
  목록. 부분 집합 페이스의 목록은 게임의 텍스트에서 나왔으며 그 텍스트는 이 저장소에 없다).
- `svf2to3.py --profile default`: mkfont는 레코드를 자기 순서로 쓴다. 배포된 페이스는 v2 -> v3 변환을 거쳤고, 이 변환은 레코드를
  `default` 프로필의 정규 순서로 쓴다. 새로 구운 것을 다시 배치해도 같은 바이트가 나온다.

### 미리 조합된 글리프에서 자모 세트를 만드는 레시피 (`jamoset` 행)

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf PRE.svf -o NEODG16A.SVF --layout 844

`--from-svf`는 1 bpp 페이스의 미리 조합된 음절을 세트 체계(여기서는 8x4x4)의 조각으로 분해하고, 그 밖의 글리프는 그대로 둔다.
Neo Dunggeunmo는 그 자체가 8x4x4 조각의 OR로 그려져 있어서 맞춤이 정확하고(IoU 1.000) 11,172개 음절이 모두 조합된다.
NEODG16D/E/F/32/32A는 셀만 다른 같은 방식이다(22x22, 18x24, 20x24; 36x36 안의 32 px와 46x54). NEODG16G는 6x2x1 세트 체계이다
(`--layout 621 --advance 0 --check`, `--ascent`/`--clip-cell` 없음: mkfont의 ascent 12), 10,684 바이트이며 MCU 예제용 작은
페이스이다(미리 조합된 bake와의 IoU 0.958).

### 패밀리

| 패밀리 | 페이스 | 업스트림, 버전 | 라이선스 | 레시피 상태 |
|---|---|---|---|---|
| NanumGothic Bold | NGOTB*, NGO*X? | Google Fonts `ofl/nanumgothic` (3.020), `ttf/nanumgothic`에 있음; 1 bpp 힌팅 페이스는 NHN 원본 3.021 | OFL 1.1, RFN "Nanum", "NanumGothic" ... | verified (16 + 외부 6), NGOTB16은 글리프 하나 다름 |
| Gowun Batang Bold | GBATB*, GBA*X? | https://github.com/yangheeryu/Gowun-Batang (Google Fonts `ofl/gowunbatang`, 2.000), `ttf/gowunbatang`에 있음 | OFL 1.1 | verified (16); GBATB17O는 문서화만 됨 |
| Neo Dunggeunmo | NEODG*, NEO16BX2 | https://github.com/neodgm/neodgm v1.601, `ttf/neodgm`에 있음 | OFL 1.1, RFN "Neo둥근모", "NeoDunggeunmo" ... | verified (미리 조합 5, 자모 세트 7), NEODG16은 글리프 하나 다름; NEODG16B/C/O는 문서화만 됨 |
| Black Han Sans | BHSAN28 | https://github.com/zesstype/Black-Han-Sans (1.001), `ttf/blackhansans`에 있음 | OFL 1.1 | verified |
| Coustard | COUSB24 | https://github.com/googlefonts/coustardFont (1.100), `ttf/coustard`에 있음 | OFL 1.1 | verified |
| Diphylleia | DIPHY36 | https://github.com/JAMO-TYPEFACE/Diphylleia | OFL 1.1 | 문서화만 됨 |
| Paperlogy | PAPLG16, PAPLG18, PAPER*, PAPLB* | https://freesentation.blog/paperlogy (designptn.com), 1.000 | OFL 1.1 | 문서화만 됨 |
| MaruBuri | MARU* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 | 문서화만 됨 |
| NanumSquareRound | NSQR* | NAVER, https://hangeul.naver.com (1.000) | OFL 1.1 (NAVER의 Nanum 라이선스) | 문서화만 됨 |
| Gothic A1 | GOTHB18A, GOTHA*, GOTHB* | HanYang I&C (Google Fonts `ofl/gothica1`, 2.50) | OFL 1.1 | 문서화만 됨 |
| Single Day | SGDAY* | DXKorea (Google Fonts `ofl/singleday`, 1.00) | OFL 1.1 | 문서화만 됨 |
| Neo Dunggeunmo Pro | NDGPR* | https://github.com/neodgm/neodgm-pro 1.020 | OFL 1.1 | 문서화만 됨 |

모든 페이스는 라이선스 텍스트를 `svf/` 안의 옆자리에 둔다(`web/LICENCES.tsv`가 그 이름을 적는다). 노트 `svf/dos/*.TXT`와
`svf/jamo-extra/FACES.TSV`가 각 페이스를 설명한다.

### 레시피 없는 페이스

이 페이스들은 빌드된 그대로 보관한다. 이유는 `tools/build/faces.tsv`의 행에 적혀 있다. 이유 중 라이선스 문제는 없다. 원본 폰트는
OFL이고, 만드는 단계만 이 저장소에 없거나 여기서 재현할 수 없다.

- **연구 파이프라인으로 만든 자모 세트** (`svf/dos`의 PAPER*, PAPLB*, PAPLG18, MARU*, GOTHB18A, NSQR*와 `svf/jamo-extra`의 모든
  페이스): 음절 윤곽선을 초성 / 중성 / 종성 벡터 조각으로 분리하고, 래스터화하고, 사용 가중치와 함께 24/16/16 세트 및 최대
  12 x 12 클래스로 병합하는 일을, 이 저장소에 속하지 않는 연구 파이프라인이 했다(`svf/dos/PAPLG.TXT`, `PAPMARU.TXT`,
  `svf/jamo-extra/FACES.TSV`에 실행과 품질이 기록되어 있다). 여기서 가장 가까운 도구는 `jamovec.py`(벡터 분리)와
  `jamoset.py --layout adaptive`(분할 세트)이다. [TrueType와 OpenType 폰트에서 만드는 자모 세트](#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- **외곽선 페이스** NEODG16O, GBATB17O: 16 / 17 px 글리프를 2 px 팽창시킨 것(내레이션 아래에서 검게 그려짐). 게임 전용 장식
  스크립트로 만들었으며 그 스크립트는 이 저장소에 없다.
- **NEODG16B, NEODG16C**: 미리 조합된 원본이 한 게임의 문자만 bake한 것이었던 Neo Dunggeunmo의 8x4x4 세트이다.
  KS X 1001 전체에 `jamoset.py --from-svf`를 적용하면 다른 조각에 맞춰진다(NEODG16B의 글리프 441개 중 71개가 다르다).
- **DIPHY36**: 36 px 1 bpp의 Diphylleia Regular로, 외부 파이프라인이 래스터화했다. Diphylleia의 현재 릴리스에 `mkfont.py`를
  쓰면 다른 픽셀이 그려진다(글리프 2,359개 중 2,358개).
- **PAPLG16**: Paperlogy 1.000에 `mkfont.py Paperlogy-4Regular.ttf --size 16 --cell 18 --width 18 --bpp 2 --clip-cell --ascent 14
  --unicode ascii,2026,2122,3131-318e --only-listed --space-advance 6 --punct-extra 1`. 1.001 릴리스는 글리프 149개 중 81개를
  다르게 그리며, 어느 쪽도 `ttf/`에 없다.

## TrueType와 OpenType 폰트에서 만드는 자모 세트

자모 세트(조합형)는 조각과 표를 담는다. 모든 음절은 조각 둘 또는 셋의 OR이다. 윤곽선 폰트에서 조각을 얻는 방법은 폰트가 무엇을
담고 있느냐에 따라 세 가지이다.

**1. 합성 글리프(TrueType `glyf`).** 어떤 폰트는 음절을 그 자모 글리프의 합성으로 저장한다. 그러면 구성 요소가 곧 조각이다.

    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o neodgm.json --components
    python3 tools/jamovec.py render neodgm.json --size 16 --bpp 1 --check -o NEOVEC16.SVF
    python3 tools/jamovec.py render neodgm.json --size 16 --bpp 2 --check -o NEOVEC16A.SVF

Verified: neodgm.ttf에는 합성 음절 11,172개가 있다. `master`는 25 초 걸렸고(조각 344개, 잘못된 모양 0), 1 bpp 렌더는 15,724
바이트, 2 bpp 렌더는 19,452 바이트이며 둘 다 음절 11,172개가 조합되었다. 벡터 렌더는 래스터 맞춤 NEODG16A와 음절 11,172개 중
2,633개에서 다르다(픽셀 폰트에 대한 FreeType의 픽셀 스냅과 `jamovec`의 정확 면적 래스터라이저의 차이). 먼저 폰트를 점검한다.

    python3 -c "from fontTools.ttLib import TTFont; f=TTFont('FONT.ttf'); c=f.getBestCmap(); g=f['glyf']; print(sum(g[c[x]].isComposite() for x in c if 0xAC00<=x<=0xD7A3))"

`ttf/`에서: neodgm은 합성 음절 11,172개; NanumGothic Regular/Bold와 NanumMyeongjo Bold는 8,822개(KS X 1001 밖의 음절은 합성이고
2,350자는 그렇지 않다); NanumPenScript는 8,693개; 나머지는 없음. 일부만 합성인 폰트에 `--components`를 주면 합성 글리프만 쓴다
("auto"는 대부분의 음절이 합성이면 구성 요소를 고른다). **CFF / CFF2(OpenType `.otf`)에는 합성 글리프가 없다.** 모든 음절이
평면 윤곽선이므로, 조각은 다음 두 방법에서 나와야 한다.

**2. 결합 자모 shaping(GSUB `ljmo` / `vjmo` / `tjmo`).** 이 feature가 있는 폰트는 결합 자모 U+1100..을 위치별 변형으로 그린다.
`jamoset.py --from-ttf ... --mask-font FONT`는 HarfBuzz로 각 음절을 결합 자모로 shaping하고, 그 변형을 맞춰진 조각을 제한하는
마스크로 쓴다(`freetype-py`와 `uharfbuzz`가 필요하며, `--pylib DIR`이 그 위치를 가리킨다). 여기서는 실행하지 않았다(이 호스트에는 두
모듈 모두 설치되어 있지 않다). `ttf/`의 neodgm.ttf에는 세 feature가 있어서 마스크 폰트로 쓸 수 있다. 별도의 연구 저장소가 이
feature가 돌려주는 조각을 12 px, 힌팅 켬으로 측정했다. 맑은 고딕은 5/2/1 세트(조각 164개), Noto Sans CJK KR은 6/2/4(조각 264개;
Noto TTC에서 KR은 인덱스 1)를 준다. 이것으로 곧바로 만든 페이스는 잘 읽히지만 미리 조합된 글리프와 한두 픽셀씩 다르다(평균 IoU
약 0.58). 폰트의 결합 조각이 미리 조합된 음절과 다르게 배치되어 있기 때문이다. 그 작업은 같은 바이트 예산에서 LIST 예외로 저장한
자주 쓰는 음절 수십 개(`jamoexc.py`)가 세트를 늘리는 것보다 더 많이 개선한다는 것도 알아냈다. 이 폰트들의 데이터는 이 저장소에 없다.

**3. 미리 조합된 음절에 맞추기** (TrueType든 CFF든 모든 폰트):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 \
        --binarize threshold --check -o NG16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-ttf ttf/gowunbatang/GowunBatang-Bold.ttf --size 20 \
        --binarize threshold --check -o GB20J.SVF

Verified: NanumGothic Bold 16 px를 8x4x4로 만드는 데 12 초, 20,064 바이트, 조각 344개, 음절 11,172개에 대한 IoU 0.817이었다.
Gowun Batang Bold 20 px adaptive는 92 초, 73,220 바이트, 세트 32/24/12와 12 x 12 클래스, IoU 0.934였다. `jamofit.py`는 조각을
맞추고(1 bpp 음절에 대한 좌표 하강), `jamoadapt.py`는 조각을 공유하는 음절들이 서로 어긋나는 곳에서 세트를 쪼개고(`--layout
adaptive[:NI,NM,NF]`), `jamoseg.py`는 음절의 윤곽선을 자모별 윤곽선으로 분리하며(`jamoaa.py`와 `jamovec.py`가 쓴다),
`--components` 없이 쓰는 `jamovec.py master`는 결정 크기에서 한 번 분리하고 모든 크기를 같은 조각에서 렌더한다. `--binarize
mono`(기본값)에는 freetype-py가 필요하다. `threshold`와 `ridge`는 저장소 자체의 정확 면적 래스터라이저를 쓴다(fontTools pen이므로
TrueType과 CFF 모두 된다). 맞춤은 근사이다. IoU를 읽고 결과를 직접 보라(`web/` 선택기, 또는 `svfline.py line`).

**함정.** 음절을 적게 그리는 폰트(Black Han Sans: 2,581자)는 그 음절만 맞춘다(`--present-only`, 기본값). 나머지는 가장 가까운
조각으로 조합된다. `--check`는 음절 11,172개를 모두 조합하고 표 오류에서 실패하며, 맞춤이 나쁘다고 실패하지는 않는다.

## 안티에일리어싱된 (2 bpp) 페이스

미리 조합됨 (verified, `tools.md` "Recipes"): `mkfont.py FONT OUT --size 16 --bpp 2 --unicode ascii,ksx1001-hangul` (NanumGothic
Bold: 185,932 바이트, 글리프 2,446개). 커버리지는 4단계로 양자화되고, 리더는 level x 85로 되살린다. 2 bpp 페이스는 같은 1 bpp
페이스의 약 1.7배이다. `--bpp 8`은 전체 커버리지를 유지한다(8 bpp 페이스는 호스트용).

자모 세트:

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 --bpp 2 \
        --check -o NG16JA.SVF                     # verified: 73 s, 24,960 bytes, level error 0.233, IoU at level 2 0.822
    python3 tools/jamovec.py render MASTER.json --size 16 --bpp 2 -o OUT.SVF      # from a vector master

`--bpp 2`는 `jamoaa.py`를 실행한다. 음절을 정확 면적 커버리지로 래스터화하고, 1 bpp 맞춤의 영역이 각 픽셀을 어느 조각이 소유하는지
정하며, 각 조각의 level은 그 조각을 공유하는 음절들의 중앙값으로 정한 뒤 level 오차에 대해 다듬는다(`--aa-refine N`, 2회). `--clean`
(2 bpp에서는 켜짐)은 고립된 잡음을 지운다. 조각은 픽셀별 최댓값으로 OR된다. 2 bpp에는 fontTools만 필요하다.

**함정.** 다른 조각 위의 안티에일리어싱된 조각은 합이 아니라 최댓값을 취한다. 가늘게 교차하는 획은 미리 조합된 글리프보다 옅게
보인다. 1 bpp 대상(MONO_PAGE)은 그리는 시점에 2 bpp 페이스를 임계값으로 자른다(대상의 `threshold`). 모노 디스플레이에는 1 bpp
페이스를 주어라.

## 기준선, 세로 이동, 클리핑

페이스의 ascent 필드는 셀 위쪽에서 기준선까지의 행이다. 렌더러는 줄의 기준선을 펜 y에 놓고 각 글리프를 `dy` 행만큼 아래에 그린다
(글리프별 dy, `spec/SVF.md`).

`mkfont.py`가 이를 고르는 방법: `--ascent N`이 값을 정한다. 주지 않으면, 폰트의 ascent + descent가 셀에 들어갈 때는 폰트의 ascent
이고, 들어가지 않을 때는 탐침("한글AQg", `--latin`이면 "AQgjy")의 잉크를 셀 가운데에 놓는다. `--latin`이면 대문자 높이가 맨 위로
간다. 그다음 글리프마다:

- 기본: 잉크가 셀의 위나 옆으로 나가는 글리프는 셀 안으로 옮겨진다(글리프별 이동. 그 글리프는 기준선에서 벗어난다). 셀 아래로 나간
  잉크는 잘린다.
- `--clip-cell`: 모든 글리프가 하나의 기준선 위에 있고 셀 밖의 잉크는 잘린다. 표준 출력이 위와 아래에서 잘린 글리프 수를 센다.
- `--fit-cell`: 모든 글리프의 잉크가 한 기준선 위에서 셀에 들어갈 때까지 크기를 1 px씩 낮춘다.

실제 예(verified), NanumGothic Bold를 18 px로 16x16 셀에 그린다(ASCII와 음절 2,350자):

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf c.svf --size 18 --cell 16 --bpp 1 \
        --unicode ascii,ksx1001-hangul [--clip-cell | --fit-cell | --ascent 14 --clip-cell]

| 옵션 | Ascent | 결과 |
|---|---|---|
| 없음 | 13 (잉크 가운데 정렬) | 글리프를 하나씩 셀 안으로 옮김, 126,048 바이트 |
| `--clip-cell` | 15 (잘린 글리프가 가장 적음) | 글리프 2,445개 중 2,300개가 잘림 (위 368, 아래 2,299) |
| `--ascent 14 --clip-cell` | 14 | 2,327개 잘림 (위 2,321, 아래 36) |
| `--fit-cell` | 13, 15 px에서 | 잘림 0, 118,116 바이트 |

`tools/fontmetrics.py FACE.SVF`는 잉크가 advance 밖으로 나가는 글리프를 나열한다(여기서는 하나, `\`). 사후에 디센더를 낮추려면(또는
글리프를 올리려면) 글리프별 dy를 정한다.

    python3 tools/svfdy.py IN.SVF OUT.SVF --range 0x67,0x6a,0x70,0x71,0x79 --dy 1    # g j p q y one row lower
    python3 tools/svfdy.py OUT.SVF --show

`--dy`는 그리는 시점에 글리프를 옮긴다. 페이스의 dy 범위(헤더 바이트 17/18)가 넓어지고, 줄의 descent는 그만큼 커진다. dy를 지원하지
않는 엔진은 그 글리프를 셀 위치에 그린다.

**함정.** 폰트의 줄 간격보다 작은 셀은 언제나 무언가를 자른다. `--fit-cell`을 쓰거나, advance를 고정한 더 큰 셀을 써라. 페이스의
ascent를 바꾸면 모든 줄의 잉크가 놓이는 곳이 바뀐다(MCU 예제는 줄의 기준선을 그 줄의 맨 윗 행 + 페이스의 ascent에 놓는다).

## 클래식 Mac 한글 비트맵 폰트

Apple의 데이터는 이 저장소에 없다. 도구는 직접 마련한 파일을 읽는다. maker의 로컬 모드(`maker/README.md`, "Local mode")는 이
폰트를 디스크의 제자리에서 같은 도구로 읽고, 페이스는 고른 폴더에만 쓴다.

**HangulTalk 1.0 'fbit' 폰트** (한글 System 4.1: Gotic12/16, Munjo12/16/24). 입력: 폰트의 리소스 포크를 파일로 한 것(Mac 볼륨에서
복사했거나 아카이브의 포크; `tools/macsfnt.py list`가 그 'fbit' 리소스를 보여 준다). 포크에는 글리프 세트 45개의 'fbit' 리소스와
18개의 조회 표를 가진 'fdef' 드라이버 리소스가 있다. 세트 체계는 폰트 자신의 규칙에서 유도하므로, 모든 음절이 Mac이 그리는 대로
조합된다.

    python3 tools/jamoset.py --layout mac-fbit-45sets Munjo24.rsrc --symbols --check -o MUNJO24J.SVF

출력: 음절 11,172개 전체의 1 bpp 자모 세트(이 폰트들은 초성 클래스 8개, 종성 클래스 4개, 초성 세트 20개), 셀 = 폰트의 크기.
`--check`는 모든 것을 조합해 jamoset 자체의 'fdef' 규칙 사본과 비교한다. 직접 만들면 골든 파일(`tools/testdata/mac-fbit-golden.json`,
배포하지 않음: Apple 비트맵이 들어가기 때문)이 독립적인 비교를 더한다. 실제 파일에 대한 시험은 `JOHAB_FONTS`가
`mac/extracted/kh10_system_disk/System Folder/*.rsrc`와 참조 렌더러를 담은 트리를 가리킬 때 실행되고, 아니면 건너뛴다.

**HangulTalk 7.1.x type-3 'fbit' 폰트** (Seoul12, AppleGothic12/24, AppleMyungjo12/24): 평면은 표, InputBackSupport 'HTBL' 1로
조합되며, KS X 1001 음절 2,350자와 호환 자모 51개만 있다.

    python3 tools/macfbit3.py unpack Seoul12.splt.data Seoul12.rsrc     # the 7.1.2 Installer's 'splt' "JM" archive
    python3 tools/macfbit3.py fbit Seoul12.rsrc Seoul12.fbit
    python3 tools/macfbit3.py bdf Seoul12.fbit HTBL1.bin Seoul12 seoul12.bdf          # 2,401 glyphs, Unicode BDF
    python3 tools/macfbit_svf.py build Seoul12.fbit HTBL1.bin -o SEOUL12J.SVF         # direct: the Mac structure (JMAP)
    python3 tools/macfbit_svf.py build Seoul12.fbit HTBL1.bin --mode derived -o SEOUL12D.SVF   # a JSET face, all 11,172
    python3 tools/macfbit_svf.py verify SEOUL12J.SVF Seoul12.fbit HTBL1.bin

`direct`는 Mac 평면을 조각으로 유지하고 KS 음절만 정확히 조합한다. `derived`는 JSET을 맞추는데, 그 JSET의 추가 음절 8,822개는
외삽한 것이다(Mac 출력이 아님). BDF 경로는 `bdfface.py --cell 12x12 --chars-from <the 2,350 syllables>`로 이어져 미리 조합된
페이스가 된다. 변형이 많은 페이스를 MCU 예산에 맞게 줄이려면:

    python3 tools/jamomerge.py merge --face SEOUL12D.SVF --points 8192 7168 --prefix SM -o OUTDIR

(모든 조각을 그려진 그대로 유지하고, 픽셀 목적 함수로 변형, 세트, 클래스를 병합한다). 시험: `tools/test_macfbit3.py`와
`tools/test_macfbit_svf.py`는 시험 안에서 만든 합성 fbit / HTBL / NFNT 데이터로 실행된다. `MACFBIT3_CD712=<CD tree>`와
`SVF_MAC71_INPUTS=<dir of Name.fbit and Name.htbl1>`은 직접 가진 파일에 대한 점검을 더한다. 윤곽선 Mac TrueType 폰트는
[Mac 형식 TrueType](#mac-형식-truetype)을 참고한다.

## HWP 1.x와 2.x 폰트

한글과컴퓨터의 DOS 워드프로세서는 프린터 폰트와 화면 폰트(`HANGUL*.PFT`, `ASCII.PFT`, `*.FNT`)를 실었다. 이 저장소가 직접 읽는
것은 다음과 같다.

- 12x24 영문 폰트: `jamoset.py ... --eng ASCII.PFT` (12,288 바이트, 48 바이트짜리 글리프 256개)와 HBIOS 12x24 (15,360 바이트);
- 직접 만든, 한글을 미리 조합한 1 bpp 페이스를 조각으로 다시 맞추기: `jamoset.py --layout 844 --from-svf FACE.SVF --check` (HWP 1.20
  24 px 페이스에서는 이 맞춤이 정확했다);
- 조합된 음절의 BDF: `bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf --cell 24x24 --chars-from LIST`.

읽지 **않는** 것: HWP의 `.PFT` 한글 파일 자체. 그 글리프는 HWP 자체의 규칙으로 조합되며, 별도의 연구 도구(johab-fonts 연구 노트의
`kfont.py`)가 이를 해독한다. 그 리더는 이 저장소에 속하지 않으며, 그 출력(BDF 또는 미리 조합된 페이스)이 위 두 경로의 입력이다.
HWP 폰트는 이 저장소에 없다.

## 그 밖의 DOS 시대 한글 폰트

DOS 한글 시스템(한글 BIOS, 이야기, 한메, san, 도깨비, 게임)은 음절이 아니라 자모 조각을 저장했다. 음절은 초성, 중성, 선택적인
종성의 OR이었고, 어느 세트를 쓸지는 다른 자모가 정했다. `jamoset.py`는 이 원시 파일을 크기와 레이아웃으로 읽어, 원래의 선택 규칙을
재현하는 표를 가진 자모 세트를 쓴다.

| `--layout` | 파일 | 바이트 | 조각 |
|---|---|---|---|
| `844` | 원시 8x4x4 (`HANGUL.FNT`, `*.KOR`, `$K*ZN16`), 16/24/40/48 px | 11,520 (2 바이트 헤더가 있으면 11,522), 25,920, 72,000, 103,680 | 360: 초성 세트 8개(각 20), 중성 4개(각 22), 종성 4개(각 28); 각 세트의 슬롯 0은 빈 칸 |
| `844-ihnm` | SAGA IHNM 8x4x4 (중성 세트가 ㄱ ㅋ에 맞게 바뀜) | 11,520+ | 360 |
| `844-hbios24` | HBIOS / 태백 3.5 24x30 (`GOTHIC24.FNT`, `MY24.FNT`) | 243,900 | 처음 360개 |
| `1044-san` | san 1.0 10x4x4 | 12,800 | 400 |
| `621` | 6x2x1 (Apple II 시대), 바이트 열 글리프 | 6,144 | 192 |
| `dkb-printer-7x2x2` / `dkb-printer-12x4x4` | 도깨비 프린터 `HANGUL16/24.FNT` / `HANGUL40/48.FNT` (`--face 0|1`) | 15,360 / 34,560; 176,000 / 253,440 | 페이스당 240 / 440 |
| `kyra-lok` | Kyra LoK `MK15.BIT`, 15x15 | 11,550 | 385 |

    python3 tools/jamoset.py --layout 844 HANGUL.FNT --eng ENGLISH.FNT --symbols --check -o MYFONT16J.SVF
    python3 tools/johab844.py HANGUL.FNT svf/dos/NEODG16.SVF MYFONT16.SVF --eng ENGLISH.FNT     # precomposed instead

`--eng`는 ASCII용 원시 8x16 영문 폰트(2,048 또는 4,096 바이트; 셀에 맞게 정수배로 확대)를 받는다. `--base FACE.SVF`는 다른
페이스의 음절 아닌 글리프를 유지한다. ascent의 기본값은 셀의 7/8이다(`--ascent N`). 8x16 DOS 폰트는 기준선을 13행 또는 14행에
둔다. `--check`는 음절 11,172개를 모두 조합한다. `johab844.py`는 16x16 1 bpp 베이스의 음절을 원시 조각으로 다시 그리고 베이스의
나머지 글리프는 유지한다. `tools/test_recipes.py`에서 만든 합성 파일로 verified: 8x16 영문 폰트가 딸린 원시 8x4x4 폰트(가를
조합한 결과 = 원시 슬롯 1과 161의 OR, 바이트 단위로 동일), 6x2x1 폰트(초성 클래스 1개 / 종성 클래스 2개, 세트 6/2/1), 미리 조합된
페이스의 재맞춤(NEODG16J에 `--from-svf`, IoU 1.000).

**함정.** 크기가 맞는 파일이 다른 레이아웃이어도 크기 점검은 통과한다. 슬롯 0의 채움 조각이 비어 있지 않으면 `jamoset.py`가
거부하지만, 결과를 직접 보라(`svfline.py line ... "가나다"`). 2 바이트 헤더가 있는 폰트(T-Hangul)는 오프셋 2에서 읽는다. 24 px
이상의 원본에는 거기에 맞는 영문 폰트나 `--base`가 필요하다.

## X Window 한글 폰트

**hanterm** (johab-1 인코딩, 글리프 번호는 `ENCODING`, 10x(3|4)x4 세트, 글리프 529개):

    python3 tools/jamoset.py --layout hanterm-johab johabm16.bdf --check -o HTERM16J.SVF

**KS X 1001(완성형) BDF/PCF** (`CHARSET_REGISTRY "KSC5601.1987"` 또는 `"KSX1001"`, `ENCODING` = GL 코드, 예: `-baekmuk-*`,
`-daewoo-*`, `hanglm16.bdf`) 또는 유니코드 BDF (`ISO10646`): `bdfface.py`로 미리 조합된 페이스를 만든 다음 `--from-svf`로 자모
세트를 만든다.

    python3 tools/bdfface.py --hangul hanglm16.bdf --ascii 8x16.bdf --cell 16x16 --chars-from CHARS.txt -o KS16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf KS16.SVF --check -o KS16J.SVF

`--chars-from`은 가져올 음절을 지정하고(임의의 텍스트; `mkfont.py`의 규칙), `--ascent` / `--hangul-ascent`는 기준선을 정한다.
합성 BDF로 verified(`tools/test_recipes.py`): 음절 10개짜리 KS C 5601 BDF와 ISO 10646 ASCII BDF는 정확히 그 음절만 담은 페이스를
주고 행도 제자리에 있다. 글리프 529개의 합성 hanterm BDF는 음절 11,172개를 10/4/4 세트로 모두 조합한다.

**PCF.** `bdfface.py`와 hanterm 리더는 BDF만 읽는다. 외부 도구로 변환한다. 예를 들어 `pcf2bdf`(Debian 패키지 `pcf2bdf`):
`pcf2bdf -o font.bdf font.pcf.gz` (여기서는 실행하지 않음: 이 호스트에 설치되어 있지 않다). `mkfont.py`는 PCF나 BDF를 FreeType을
통해 직접 읽되, 내장된 픽셀 크기에서만 읽는다(tools.md "Recipes", PCF).

**인코딩.** EUC-KR / 완성형 바이트 쌍 = GL 코드 + 0x8080 (`가` = B0A1 = GL 3021). Python: `bytes((0xB0,0xA1)).decode
("euc_kr")`. 조합형(KS X 1001 부속서 3, `johab` 코덱): 16비트 코드 `1 iiiii mmmmm fffff`에 채움 값(초성 2 = ㄱ, 중성 3 = ㅏ, 종성
1 = 없음)이 있고 `가` = 8861; `bytes((0x88,0x61)).decode("johab")`. 유니코드 음절 = 0xAC00 + (초성 x 21 + 중성) x 28 + 종성 (자모
인덱스는 0부터). `tools/test_recipes.py`에서 verified.

## KS X 1001

KS X 1001(예전 이름 KS C 5601)에는 미리 조합된 한글 음절 2,350자(행 0xB0-0xC8, 행마다 94자), 호환 자모 51개(행 0xA4:
U+3131..U+3163), 기호, 한자가 있다. 도구:

- `mkfont.py --unicode` 이름: `ksx1001-hangul`(2,350자), `ksx1001-nohanja`(기호, 자모, 2,350자), `ksx1001-symbols`,
  `ksx1001`(한자 포함), `hangul` / `cp949-hangul`(11,172자 전부), `cp949`(CP949가 디코딩하는 모든 것), `jamo`(U+3131..U+318E,
  94개). `--limit`은 `--chars-from` 목록과 이들 중 하나의 교집합을 취하고, `--require`는 폰트에 없는 코드 포인트를 거부한다.
- `jamoset.ks_x_1001_syllables()`(음절 인덱스)와 품질 보고서(`ks2350` 열)는 같은 집합을 쓴다. `tools/test_recipes.py`가 둘이 euc_kr
  코덱의 행과 같음을 점검한다.
- 자모 세트는 음절 11,172개를 모두 조합한다. 호환 자모는 표가 조각을 지정하면 조각으로, 아니면 글리프 전체로 그린다.
  `jamoset.py --blank-compat`은 글리프 전체가 있는 곳에서 그것을 쓰도록 페이스를 다시 쓴다.
- `facecheck.py`는 페이스를 매니페스트와 대조하고(`verify`) 맵을 만든다(`mapfaces`). 페이스별 커버리지는 웹 인덱스에 있다
  (`web/mkindex.py`: `hangul` = 그려진 KS 음절, `subset` = 2,350자보다 적음).

## Mac 형식 TrueType

**리소스 포크 폰트** (.dfont, suitcase, HFS에서 복사한 포크): TrueType 데이터는 'sfnt' 리소스이다.

    python3 tools/macsfnt.py list Font.dfont                 # type, id, name, bytes of sfnt / NFNT / FOND / fbit
    python3 tools/macsfnt.py extract Font.dfont Font.ttf [--id N]

`macsfnt.py`는 AppleDouble(`._Font`)과 MacBinary 파일도 푼다. FreeType도 .dfont를 직접 열 수 있어서, 유니코드에 매핑된 폰트의 첫
페이스는 `mkfont.py Font.dfont ...`로 된다(합성 .dfont로 verified).

**Mac 한글 cmap.** 한글 Mac용 폰트(와 일부 Windows 폰트)에는 플랫폼 1 / 스크립트 3(Mac Korean) 또는 플랫폼 3 / 인코딩 5(Wansung)
cmap, 즉 두 바이트 KS X 1001 코드만 있다. FreeType과 SVF 도구는 유니코드 cmap을 고르므로, 이런 폰트는 유니코드 cmap이 생기기 전까지
아무것도 그리지 못한다.

    python3 tools/macsfnt.py cmap Font.ttf                   # platform=1 encoding=3 format=2 entries=... hangul=...
    python3 tools/macsfnt.py unicode Font.ttf FontU.ttf      # adds (3,1) format 4 [+ (3,10) format 12]

각 코드는 EUC-KR(KS X 1001)로 디코딩된다. Mac Korean에 대한 Apple 자체의 추가분은 KS X 1001에서 의미가 없으므로 매핑되지 않은 것으로
센다. Verified (`tools/test_macsfnt.py`): (1,3) format 2 cmap만 가진 합성 폰트가 나열되고, 리소스 포크, AppleDouble, MacBinary에서
추출되고, 유니코드 서브테이블을 얻고, 그다음 `mkfont.py`가 그 음절을 그린다.

**TTC.** `mkfont.py`는 컬렉션의 인덱스 0을 연다(verified: Galmuri9 + Galmuri7의 TTC는 Galmuri9와 똑같이 bake된다). 다른 페이스는
먼저 저장해 둔다.

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; C('F.ttc').fonts[1].save('F1.ttf')"

위치가 아니라 이름으로 고른다(`fonts[i]['name'].getDebugName(4)`). Noto CJK 컬렉션에서 KR은 인덱스 0이 아니다.

**내장 비트맵 (`bdat`/`bloc`, `EBDT`/`EBLC`).** FreeType은 스트라이크를 그 자체의 픽셀 크기에서만 쓴다. 스트라이크의 크기로
`mkfont.py --size N`과 `--bpp 1`을 실행한다. 다른 크기에서는 윤곽선을 쓰고, 비트맵 전용 폰트는 열기가 실패한다(`OSError: invalid
pixel size`). 여기서는 실행하지 않았다(`ttf/`에 그런 폰트가 없다).

## OpenType CFF, 컬렉션, 가변 폰트

- **래스터화.** `mkfont.py`는 Pillow의 FreeType 바인딩으로 그린다. 안티에일리어싱된 커버리지(1 bpp는 128에서 자르고, 2 bpp는
  양자화), 또는 `--mono-hint`를 주면 폰트의 힌팅을 쓰는 FreeType의 모노크롬 렌더러(`FT_LOAD_TARGET_MONO`)이다. FreeType은
  TrueType과 CFF/CFF2를 똑같이 읽는다(OTF는 변환이 필요 없다). `jamoaa.py` / `jamovec.py` / `--binarize threshold|ridge`는 윤곽선을
  직접 평탄화하고(fontTools pen, 곡선 평탄화, 정확 면적 커버리지) TrueType과 CFF에서 똑같다.
- **CFF에는 합성 글리프가 없다.** 따라서 OTF의 자모 세트는 GSUB shaping(마스크 폰트)이나 맞춤에서 나온다.
  [TrueType와 OpenType 폰트에서 만드는 자모 세트](#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- **OTC** 컬렉션: 위의 TTC와 같다.
- **가변 폰트.** `mkfont.py`는 기본 인스턴스를 그린다. 다른 인스턴스는 먼저 정적 인스턴스로 잘라 낸다(fontTools, 외부 단계):

      python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o Caveat-Bold.ttf
      python3 tools/mkfont.py Caveat-Bold.ttf CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin

  Verified: 기본 인스턴스(Regular 400)는 6,760 바이트로, 700 인스턴스는 7,192 바이트로 bake된다(각각 글리프 95개,
  "Hamburgefonstiv"의 폭은 136 대 141 px). 이름 있는 인스턴스는 `fvar` 표에 있다(`Caveat`: Regular, Bold; `EB Garamond`:
  Regular .. ExtraBold).
- **레시피에 넣기.** 이 중 무엇이든 유니코드 cmap이 있는 정적 TrueType 또는 CFF 폰트가 되고 나면 `mkfont.py`(미리 조합),
  `jamoset.py --from-ttf` / `jamovec.py`(자모 세트), 또는 `mkfont.py` 다음 `jamoset.py --from-svf`로 들어간다.

## 새 페이스 점검

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF       # width, ascent, descent
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > out.gray
    python3 tools/fontmetrics.py FACE.SVF                                 # ink past the advance
    python3 tools/svf2to3.py FACE.SVF /tmp/x.SVF --check                  # re-layout and compare every glyph
    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf -o /tmp/m.tsv

`svf/`에 추가하는 페이스에는 그 옆의 라이선스 텍스트, `web/LICENCES.tsv`와 `web/FAMILIES.tsv`의 행, `tools/build/faces.tsv`의 행
(레시피를 적거나, `none`과 그 이유를 적음)이 필요하다. 그렇지 않으면 `tools/test_build_faces.py`와 `tools/test_web_picker.py`가
실패한다.
