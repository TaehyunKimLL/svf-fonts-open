[English](outline-fonts.md) | **한국어**

# 레시피: 아웃라인 폰트

TrueType와 OpenType 폰트(TTF, CFF 윤곽의 OTF, TTC/OTC, 가변 폰트, Mac 형식 TrueType)에서 완성형 페이스와 자모 세트를 만든다: 폰트에 맞춘 자모 세트나 폰트가 가진 자모 글리프에서 읽은 자모 세트, 2 bpp 안티앨리어싱 페이스, 그리고 모든 아웃라인 경로에 공통인 기준선, 세로 이동, 클리핑.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. 선택한 Python 환경의 Pillow와 fontTools가 필요하다(자모 도구는 `--pylib DIR`도 받는다).

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [벌 수 정하기](sets.ko.md), [기존 SVF, 그리고 SVF에서 다시 TTF로](svf-and-ttf.ko.md), [자모 세트](../jamo-sets.ko.md), [자모 분리](../jamo-split.ko.md), [안티앨리어싱](../anti-aliasing.ko.md).

<a id="아웃라인-폰트"></a>

## 아웃라인 폰트

FreeType은 TrueType과 CFF(OpenType `.otf`)를 똑같이 읽으므로, 유니코드 cmap이 있는 정적 TTF나 OTF는 곧바로 도구에 들어간다.
`jamoset.py --from-ttf`, `jamoaa.py`, `jamovec.py`, `--binarize threshold|ridge`는 윤곽선을 직접 평탄화하며(fontTools pen, 정확 면적
커버리지) 둘에서 똑같다. 컬렉션, 가변 폰트, Mac 형식 폰트는 먼저 한 단계가 필요하다(아래).

<a id="완성형-페이스-mkfontpy"></a>

### 완성형 페이스 (`mkfont.py`)

원본: `ttf/nanumgothic/NanumGothic-Bold.ttf`. 완성형, 1 bpp, 그다음 정규 레이아웃 단계:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-1bpp.svf \
        --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/ng16-1bpp.svf $OUT/NG16.SVF --profile default --check

검증: `125,520 바이트`(`mkfont.py`의 임시 파일), 글리프 2,446개(한글 음절 2,350개). 렌더는 `width=146 ascent=14 descent=2`,
잉크 677. `svf2to3.py ... --profile default --check`는 다시 125,520 바이트를 쓴다(글리프는 같고 레코드 순서만 다르다. 처음 다른 바이트는 813번). `data_in=86332 data_out=86332`를 보고한다.

`mkfont.py`는 레코드를 자기 순서로 쓴다. `svf2to3.py --profile default`는 이를 `default` 프로필의 정규 순서로 다시 배치한다(배포된
페이스, `tools/build/build_faces.py`, maker 모두 이 단계로 끝난다). `--check`가 픽셀이 같음을 증명한다. 다른 대상(`mcu-strict`,
`dos`, `wasm`, `full`, `simd16`)에 맞게 배치하려면 그 `--profile`을 쓴다.

안티앨리어싱(2 bpp): 같은 명령에 `--bpp 2`(`195,760 바이트`, 글리프 2,446개, `width=146 ascent=14 descent=2`, 잉크 847. 커버리지는 4단계로
양자화된다). 정규 단계는 이번에도 크기(195,760 바이트)를 유지하고 픽셀이 같음을 증명한다. `--bpp 8`은 전체 커버리지를 유지한다(8 bpp 페이스는 호스트용). 크기, 셀, ascent, 클리핑을 고르는 `mkfont.py` 옵션은
[기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑)에, `svf/`의 행 레시피 전체는
[완성형 글리프 레시피](svf-faces.ko.md#완성형-글리프-레시피-mkfont-행)에 있다.

**문자 집합이 필요하다**(`--unicode SET` 또는 `--chars-from FILE`). 둘 다 없으면 `mkfont.py`는 종료 코드 2로 끝난다. 이름은
[참고](../recipes.ko.md#참고)에 있다.

<a id="opentype-cff-otf"></a>

### OpenType CFF (`.otf`)

Noto Sans CJK KR은 누구나 구할 수 있는 CFF 폰트이다(SIL OFL 1.1. Debian의 `fonts-noto-cjk`가 KR, JP, SC, TC, HK 페이스의 컬렉션인
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`로 싣는다. [TTC와 OTC](#ttc와-otc) 참고). KR 페이스를 일반 `.otf`로 저장해서
변환한다([폰트 원본과 라이선스](../recipes.ko.md#ref-fonts) 참고).

    python3 maker/srcprep.py ttc-face /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc $OUT/NotoSansCJKkr.otf --index 1
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-2bpp.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --binarize threshold \
        --mask-font none --check -o $OUT/noto16-jamo-1bpp.svf
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --bpp 2 --check -o $OUT/noto16-jamo-2bpp.svf

검증(부분 집합이 아닌 전체 폰트): 페이스 이름은 "Noto Sans CJK KR"; 1 bpp `125,196 바이트`, 글리프 2,446개, `width=141 ascent=11
descent=5`, 잉크 472; 2 bpp `197,992 바이트`, 잉크 700; 자모 세트 `19,040 바이트`, 글리프 439개, 조각 344개, 음절 11,172개에 대한 IoU
0.786(6.9 초), `width=146 ascent=14 descent=2`, 잉크 477; 2 bpp 자모 세트 `23,268 바이트`, 글리프 439개, 단계 오차 0.208, 단계 2의 IoU 0.781, 62 초, `width=141 ascent=14 descent=2`, 잉크 722(이 Noto 맞춤은 0.786과 0.781이고 NanumGothic은 0.817과 0.822이다. 이 비교만으로 아웃라인 형식에 따른 차이를 단정할 수는 없다). `mkfont.py` 페이스는 폰트 메트릭으로 ascent를 고르므로 폰트마다 기준선이 다르다.
[기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑)을 참고한다.

<a id="truetype와-opentype-폰트에서-만드는-자모-세트"></a>

### TrueType와 OpenType 폰트에서 만드는 자모 세트

자모 세트(조합형)는 조각과 표를 담는다. 1 bpp에서 조합한 음절은 조각 둘 또는 셋의 OR이고,
2 bpp에서는 픽셀마다 가장 큰 단계를 취한다. [자모 세트](../jamo-sets.ko.md)를 참고한다. 윤곽선 폰트에서 조각을 얻는 방법은 폰트가 무엇을
담고 있느냐에 따라 세 가지이다.

**1. 합성 글리프(TrueType `glyf`).** 어떤 폰트는 음절을 그 자모 글리프의 합성으로 저장한다. 그러면 구성 요소가 곧 조각이다.

    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 1 --check -o $OUT/NEOVEC16.SVF
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

검증: neodgm.ttf에는 합성 음절 11,172개가 있다. `master`는 25 초 걸렸고(조각 344개, 잘못된 모양 0), 1 bpp 렌더는 15,724
바이트, 2 bpp 렌더는 19,452 바이트이며 둘 다 음절 11,172개가 조합되었다. 벡터 렌더는 래스터 맞춤 NEODG16A와 음절 11,172개 중
2,633개에서 다르다(2026-11-03 측정값. 픽셀 폰트에 대한 FreeType의 픽셀 스냅과 `jamovec`의 정확 면적 래스터라이저의 차이). 먼저 폰트를 점검한다.

    python3 -c "from fontTools.ttLib import TTFont; f=TTFont('FONT.ttf'); c=f.getBestCmap(); g=f['glyf']; print(sum(g[c[x]].isComposite() for x in c if 0xAC00<=x<=0xD7A3))"

`ttf/`에서: neodgm은 합성 음절 11,172개; NanumGothic Regular/Bold와 NanumMyeongjo Bold는 8,822개(KS X 1001 밖의 음절은 합성이고
2,350자는 그렇지 않다); NanumPenScript는 8,693개; 나머지는 없음. 일부만 합성인 폰트에 `--components`를 주면 합성 글리프만 쓴다
(Python API의 `components="auto"`는 대부분의 음절이 합성이면 구성 요소를 고른다. CLI에는 `--components`가 필요하다). **CFF / CFF2에는 이 경로가 읽는 TrueType `glyf` 합성 구조가 없다.** 도구는 음절을 윤곽선으로 다루므로, 조각은 다음 두 방법에서 나와야 한다.

**2. 결합 자모 셰이핑(GSUB `ljmo` / `vjmo` / `tjmo`).** 이 기능이 있는 폰트는 결합 자모 U+1100..을 위치별 변형으로 그린다.
`jamoset.py --from-ttf ... --mask-font FONT`는 HarfBuzz로 각 음절을 결합 자모로 셰이핑하고, 그 변형을 맞춰진 조각을 제한하는
마스크로 쓴다(`freetype-py`와 `uharfbuzz`가 필요하며, `--pylib DIR`이 그 위치를 가리킨다). 두 모듈을 스크래치 폴더에 설치해 여기서 실행했다
(`pip install --target $OUT/pylib freetype-py uharfbuzz`, 그다음 `--pylib`에 그 폴더. 시스템이나 사용자 site에는 아무것도 설치하지 않는다):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/neodgm/neodgm.ttf --size 16 --binarize threshold \
        --mask-font ttf/neodgm/neodgm.ttf --no-clean --check --pylib $OUT/pylib -o $OUT/NEO16M.SVF

`ttf/`의 neodgm.ttf에는 세 기능이 있어서 스스로 마스크 폰트가 된다. `15,740 바이트`, 글리프 439개, 조각 344개, 음절 11,172개에 대한 IoU
1.000(3.6초), 그중 11,008개가 정확, `width=144 ascent=12 descent=4`, 잉크 559. 같은 폰트의 자유 맞춤(`--mask-font none`)은
`16,376 바이트`, 11,172개 모두 정확, 역시 3.6초이다. 마스크는 바이트를 덜 쓰지만(조각이 자기 변형에 갇힌다) 그 대가로 정확한 음절 일부를
내준다. 폰트의 결합 조각이 완성형 음절과 다른 경우 마스크는 도움보다 손해가 크다. Noto Sans CJK KR([OpenType CFF](#opentype-cff-otf) 레시피의
OFL 폰트) `16,396 바이트`, IoU 0.752(자유 맞춤 0.786), 6.5초, 잉크 450. 맑은 고딕(Microsoft, Windows; 독점)
`16,212 바이트`, IoU 0.753(자유 맞춤 0.766, `18,368 바이트`), 5.7초, 잉크 413. 모듈이 있으면 기본 `--binarize mono`도 돈다(neodgm: IoU 1.000,
0.8초, `16,376 바이트`). maker는 서버가 두 모듈을 찾을 때만(`/api/caps`의 `mask_libs`) `mask fit` 경로를 제공한다. 모듈이 있으면 neodgm.ttf,
Noto Sans CJK KR, 맑은 고딕의 경로에 그것이 들어간다(`mask_ok`를 설정한 `detect.scan` 항목에 `routes.routes`를 실행해 확인).
`jamoset.py --from-ttf`와 `--from-svf`는 `$JAMOSET_MASK_FONT`가
폰트를 가리키고(또는 ScummVM 트리 옆에 NotoSansKR이 있고) 두 모듈이 있으면 스스로 마스크 폰트도 쓴다. 자유 맞춤이 먼저이고, 그 평균 IoU가
0.995 미만일 때만 마스크를 쓴다(`AUTO_EXACT`. 이미 조각의 OR인 페이스는 자유 맞춤을 유지한다). 모듈이 없으면 stderr에 알림을 내고
자유롭게 맞춘다. 자유 맞춤을 강제하려면 `--mask-font none`을 준다. 이 장의 1 bpp 명령이 그렇게 한다. maker는 `experimental fit` 경로에만
이를 주고, `from-svf fit`과 `bdfface + from-svf fit` 경로는 자동으로 둔다.

**3. 완성형 음절에 맞추기** (TrueType든 CFF든 모든 폰트):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 \
        --binarize threshold --mask-font none --check -o $OUT/NG16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-ttf ttf/gowunbatang/GowunBatang-Bold.ttf --size 20 \
        --binarize threshold --mask-font none --check -o $OUT/GB20J.SVF

검증(2026-11-22): NanumGothic Bold 16 px를 8x4x4로 만드는 데 12 초, 20,064 바이트, 조각 344개, 음절 11,172개에 대한 IoU 0.817이었다.
Gowun Batang Bold 20 px adaptive는 89 초, 73,220 바이트, 벌 32/24/12와 12 x 12 클래스, IoU 0.934였다. `jamofit.py`는 조각을
맞추고(1 bpp 음절에 대한 좌표 하강), `jamoadapt.py`는 조각을 공유하는 음절들이 서로 어긋나는 곳에서 벌을 쪼개고(`--layout
adaptive[:NI,NM,NF]`), `jamoseg.py`는 음절의 윤곽선을 자모별 윤곽선으로 분리하며(`jamoaa.py`와 `jamovec.py`가 쓴다),
`--components` 없이 쓰는 `jamovec.py master`는 결정 크기에서 한 번 분리하고 모든 크기를 같은 조각에서 렌더한다. `--binarize
mono`(기본값)에는 freetype-py가 필요하다. `threshold`와 `ridge`는 정확 면적 래스터라이저를 쓴다(fontTools pen이므로
TrueType과 CFF 모두 된다). 맞춤은 근사이다. IoU를 읽고 결과를 직접 보라(`web/` 선택기, 또는 `svfline.py line`).

**함정.** 음절을 적게 그리는 폰트(Black Han Sans: 2,581자)는 그 음절만 맞춘다(`--present-only`, 기본값). 나머지는 가장 가까운
조각으로 조합된다. `--check`는 음절 11,172개를 모두 조합하고 표 오류에서 실패하며, 맞춤이 나쁘다고 실패하지는 않는다.

<a id="이미-자모를-가진-truetype-폰트"></a>

### 이미 자모를 가진 TrueType 폰트

어떤 한글 폰트는 음절 말고도 자모 글리프를 가진다. 도구가 그것을 쓸 수 있는지는 폰트가 그것을 음절과 어떻게 잇는지에 달렸다.
먼저 폴더를 훑어라(`fontTools`: U+1100-11FF와 사용 영역 U+E000-F8FF의 cmap 항목, 합성 음절, GSUB 기능 `ljmo` / `vjmo` / `tjmo`).
다음 경우는 서로 다른 경로가 필요하다:

| 폰트가 가진 것 | 예(여기) | 길 | 절 |
|---|---|---|---|
| GSUB `ljmo`/`vjmo`/`tjmo`: U+1100..의 위치별 변형 | 나눔명조 / 나눔바른고딕 옛한글(변형 250개에 닿음), 은바탕(164) | 변형을 마스크로(`--mask-font FONT`) | [방법 2](#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 구성 요소가 PUA 조각 글리프인 합성 음절 | 은 글꼴(은돋움, 은바탕, 은그래픽, 은디나루, 은궁서, 은필기: 각각 합성 음절 11,172개) | `jamovec.py master --components` | [방법 1](#truetype와-opentype-폰트에서-만드는-자모-세트), 아래 |
| 겹쳐 그리도록 그린 첫가끝 자모 U+1100..(중성과 종성은 폭 0, 펜 왼쪽에 놓임), 변형 없음 | 은돋움(U+1100 전진 폭 1000, U+1161과 U+11A8은 전진 폭 0에 x가 음수) | 자모마다 모양 하나인 방법 2, 또는 방법 3 | 아래 |
| PUA의 위치별 자모 변형, 합성 음절 없음, GSUB 없음 | MiraeroNormal(U+E000-E9EF의 PUA 글리프 2,544개: 옛 자모와 현대 자모가 각각 여러 위치로) | 없음: 규칙이 폰트에 없다 | 아래 |

**(a) 조합용으로 그린 첫가끝 자모.** 은돋움(은 글꼴 1.0.2, Debian의 `fonts-unfonts-core`, GPL 2)에는 현대 첫가끝 자모 67개(옛 자모까지
146개)가 있고 GSUB가 없다. HarfBuzz는 가를 U+1100 + U+1161로, 자모마다 글리프 하나로 셰이핑하며, 모음은 전진 폭이 0이라 자음 위에
그려진다. 방법 2는 이것을 마스크로 쓰고(자모마다 마스크 하나라, 한 역할의 모든 벌이 같은 마스크를 받는다), 방법 3은 자유롭게 맞춘다:

    python3 tools/jamoset.py --layout 844 --from-ttf UnDotum.ttf --size 16 --binarize threshold \
        --mask-font UnDotum.ttf --no-clean --check --pylib $OUT/pylib -o $OUT/UND16M.SVF
    python3 tools/jamoset.py --layout 844 --from-ttf UnDotum.ttf --size 16 --binarize threshold \
        --mask-font none --no-clean --check -o $OUT/UND16F.SVF

마스크 맞춤 `15,620 bytes`, IoU 0.761 (p5 0.518), 0개 정확, 7.5 s, `width=149 ascent=13 descent=3`, 잉크 371. 자유 맞춤 `17,908 bytes`,
IoU 0.840, 776개 정확, 7.8 s, 잉크 493(완성형 `mkfont.py` 페이스: `124,480 bytes`, 잉크 472). 자모마다 마스크 하나면 초성 벌 여덟 개의
조각이 모두 같은 모양으로 묶이는데, 음절들은 그렇지 않다. 이런 폰트에는 자유 맞춤이 더 나은 자모 세트이고, 아래에서 `--adaptive`로 읽은 합성 글리프가
그보다 낫다.

**(b) PUA 조각 글리프.** 은 글꼴은 모든 음절을 `jamo0000` .. 라는 이름의 PUA 글리프 둘이나 셋의 합성으로 저장한다(은돋움: U+EA60-F25F의
PUA 글리프 2,048개, 그중 1,991개를 합성 음절 11,172개가 쓴다. 가 = `jamo0000` + `jamo0019`, 과 = `jamo0220` + `jamo0239`). PUA 글리프가
폰트 자신의 조각 묶음이고 합성이 규칙이다. 방법 1이 이것을 읽는다:

    python3 tools/jamovec.py master UnDotum.ttf -o $OUT/undotum.json --components
    python3 tools/jamovec.py render $OUT/undotum.json --size 16 --bpp 1 --check -o $OUT/UNDVEC16.SVF
    python3 tools/jamovec.py render $OUT/undotum.json --size 16 --bpp 2 --check -o $OUT/UNDVEC16A.SVF

`master`는 36 s가 걸렸다. 구성 요소 1,991개가 8x4x4 슬롯으로 나뉘었다(조각 344개, 각 슬롯 구성 요소의 메도이드. 폰트의 변형이
8x4x4의 벌보다 많아 기증 모양 5,576개가 슬롯의 이상값이었다). 1 bpp 렌더는 `16,356 bytes`, `--check`는 11,172 음절을 모두 조합하고,
`width=149 ascent=13 descent=3`, 잉크 472. 2 bpp 렌더는 `21,348 bytes`, 잉크 716. `master --components --adaptive`(124 s)로 하면 조각이
폰트 자신의 변형을 더 많이 지킨다: 기본 adaptive 예산 안의 조각 1,436개, 1 bpp `62,976 bytes`, 잉크 476, 2 bpp `79,088 bytes`, 잉크 728.
같은 폰트의 완성형 `mkfont.py` 페이스와 비교하면(`svfscale.overlap`, 2,350 음절의 평균 IoU. 두 래스터라이저가 달라 완전한 일치를 보장하지는 않는다): 마스크 맞춤 0.648, 8x4x4 구성 요소 0.734, 자유 맞춤 0.755, adaptive 구성 요소 0.840.

PUA에 위치별 자모가 있지만 음절은 그냥 윤곽선이고 PUA에 닿는 GSUB도 없는 폰트(MiraeroNormal: 합성 음절 없음, GSUB 없음)는 어느
도구에도 음절에 맞는 변형을 고르는 규칙을 주지 않는다. PUA 코드 배정(어느 코드가 어느 위치의 어느 자모인지)과 모음과 종성에 따른 선택은
폰트 제작자의 방식이고 파일 어디에도 적혀 있지 않다. 이런 폰트는 다른 폰트처럼 방법 3으로 간다. 그 PUA 조각을 쓰려면 그 방식을 표로
적어야 한다(`rawcarve.py compose` 명세의 꼴이지만 코드 포인트로 아웃라인 글리프를 그려야 하며, 그렇게 하는 도구는 없다).

**(c) GSUB `ljmo` / `vjmo` / `tjmo`.** [방법 2](#truetype와-opentype-폰트에서-만드는-자모-세트)의 마스크 맞춤(neodgm, Noto Sans CJK KR,
맑은 고딕을 거기서 쟀다).

<a id="truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기"></a>

### TrueType/OpenType 폰트에서 2 bpp 안티앨리어싱 페이스 만들기

<a id="안티에일리어싱된-2-bpp-페이스"></a>
<a id="안티앨리어싱된-2-bpp-페이스"></a>
<a id="truetypeopentype-폰트에서-2-bpp-안티에일리어싱-페이스-만들기"></a>

2 bpp 페이스는 픽셀마다 네 단계(0, 1, 2, 3)를 저장한다(커버리지 = 단계 × 85). 아래의 아웃라인 폰트 경로는 윤곽선을
래스터화해 이 단계를 얻는다. 흑백 비트맵의 원래 크기에서는 커버리지가 0과 255뿐이지만, 회색조 비트맵은 이미 중간 커버리지를
가질 수 있다. 큰 비트맵을 축소해도 중간 단계가 생길 수 있다
([고해상도 비트맵 폰트에서 저해상도 페이스 만들기](bitmap-fonts.ko.md#고해상도-비트맵-폰트에서-저해상도-페이스-만들기)). 아웃라인 폰트의 세 가지 경로:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-2.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 --bpp 2 \
        --check -o $OUT/NG16JA.SVF
    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

**단계를 정하는 것.** `mkfont.py --bpp 2`는 각 글리프를 Pillow를 통해 FreeType의 안티앨리어싱 렌더러로 그리고(FreeType이 기본으로
적용하는 폰트의 힌팅), 8비트 커버리지를 `(coverage x 3 + 127) // 255`로 양자화한다. 2 bpp용 감마, 임계값, 오버샘플링, 힌팅 옵션은 없다
(`--mono-hint`는 `--bpp 1`용이고 그 밖에는 거부된다). 그러니 크기(`--size`, 배치는 `--cell` / `--ascent`)가 유일한 조절이다.
`jamoset.py --bpp 2`(`jamoaa.py`)는 음절을 자신의 정확 면적 커버리지(힌팅 없음)로 래스터화하고, 1 bpp 맞춤의 영역으로 각 픽셀을 어느
조각이 소유할지 정하며, 각 조각의 단계를 그것을 공유하는 음절들의 중앙값으로 정한 뒤 단계 오차에 대해 다듬는다: `--aa-refine N`
(2회. 0이면 중앙값만), `--clean` / `--no-clean`(2 bpp에서는 켜짐: 조각을 그 자모의 윤곽이 잉크를 두는 곳으로 한정하고, 옅은 단계는
음절의 절반이 가진 곳에만 둔다), 벌 체계(`--layout 844` 또는 `adaptive[:NI,NM,NF]`, [벌 수 정하기](sets.ko.md#벌-수-정하기)).
`jamovec.py render --bpp 2`(기본값)는 벡터 마스터의 조각을 같은 정확 면적 커버리지로 그린다.

**측정**(2026-11-22. 잉크는 이 장의 규칙대로, "단계"는 2,350 음절을 `svfline.py`로 그렸을 때 잉크 픽셀 중 단계 1 / 2 / 3의 비율):

| 폰트, 크기 | 페이스 | 바이트 | 맞춤 | 단계 1/2/3 | measure | 잉크 |
|---|---|---|---|---|---|---:|
| NanumGothic Bold 16 | `mkfont.py --bpp 1` | `125,520` | | (1 bpp) | `width=146 ascent=14 descent=2` | 677 |
| | `mkfont.py --bpp 2` | `195,760` | | 23 / 18 / 59 % | 같음 | 847 |
| | `jamoset.py --bpp 1` (threshold) | `20,064` | IoU 0.817, 12 s | (1 bpp) | `width=151 ascent=13 descent=3` | 672 |
| | `jamoset.py --bpp 2 --aa-refine 0` | `23,692` | 단계 오차 0.269, 단계 2 IoU 0.783, 69 s | 30 / 31 / 39 % | `width=146 ascent=13 descent=3` | 869 |
| | `jamoset.py --bpp 2` (refine 2) | `24,960` | 단계 오차 0.233, 단계 2 IoU 0.822, 72 s | 27 / 32 / 41 % | 같음 | 879 |
| Gowun Batang Bold 20 (규칙 `line 400 28 0 20`) | `mkfont.py --bpp 1` | `170,924` | | (1 bpp) | `width=175 ascent=18 descent=2` | 727 |
| | `mkfont.py --bpp 2` | `264,376` | | 25 / 20 / 55 % | 같음 | 955 |
| | `jamoset.py --bpp 1` (threshold) | `23,316` | IoU 0.807, 21 s | (1 bpp) | `width=184 ascent=17 descent=3` | 776 |
| | `jamoset.py --bpp 2` | `28,940` | 단계 오차 0.193, 단계 2 IoU 0.805, 94 s | 27 / 30 / 43 % | `width=174 ascent=17 descent=3` | 1,020 |
| Neo둥근모 16 | `jamovec.py render --bpp 2` | `19,452` | 11,172 조합, 마스터 24 s | 0 / 0 / 100 % | `width=144 ascent=12 descent=4` | 559 |

위 측정에서 2 bpp 완성형 페이스는 1 bpp 페이스의 1.5-1.6배, 2 bpp 자모 세트는 1 bpp 세트의 약 1.2배이다. 자모 세트는 완성형 글리프보다 중간
단계가 많다(조각의 단계는 많은 음절의 중앙값이고, 조각을 조합할 때는 최댓값을 취한다). `--aa-refine 2`는 여기서 1 KB를 더 써서 단계 오차를
낮추고 단계 2 IoU를 높인다. 위의 16 px Neo둥근모 렌더에는 부분 커버리지가 없다. 그 2 bpp 페이스는 단계 3인 1 bpp 페이스일 뿐이고
바이트만 더 든다. 자모 세트의 기준선은 폰트의 ascent가 아니라 맞춤(잉크 상자 가운데)에서 오므로 `mkfont.py` 페이스와 한 행 다를 수
있다(`--baseline`으로 정한다).

**크기 고르기.** 위의 2 bpp 완성형 예시에서 잉크 픽셀의 55-59 %가 단계 3이다. 더 작은 크기는 여기서 재지 않았다. 12-14 px에서는 대상에서 2 bpp 페이스와 힌팅된 폰트의 1 bpp `--mono-hint`
페이스([완성형 글리프 레시피](svf-faces.ko.md#완성형-글리프-레시피-mkfont-행))를 비교한 뒤 고르라. 그리는 시점에 축소하지 말고 대상이 그리는
크기로 구워라. 모든 결과를 숫자(잉크, 단계, 자모 세트는 `aa:` 줄의 단계 오차와 단계 2 IoU)와 눈으로 점검하라. `svfline.py line`은
GRAY8을 쓰고, `web/` 피커는 페이스를 그 단계로 보여 준다.

**함정.** 다른 조각 위의 안티앨리어싱된 조각은 합이 아니라 최댓값을 취한다. 교차하는 획은 완성형 글리프보다 옅게 보일 수 있다. 흑백 대상(`SVF_T_MONO_PAGE`, `SVF_T_MONO_ROW`)은 그리는 시점에 2 bpp 페이스를 임계값으로 자른다
(`svf_target.mono_threshold`, 기본값 128). 모노 디스플레이에는 1 bpp
페이스를 주어라. `--bpp 8`(mkfont만)은 호스트용으로 전체 커버리지를 유지한다.

배경 설명(커버리지, 감마, 서브픽셀 렌더링을 하지 않는 이유), 타깃별 단계-색 변환 규칙, 자모 세트의 최댓값과 OR, bpp 선택표는
[안티앨리어싱](../anti-aliasing.ko.md)에 있다. 미리보기는 [웹 렌더러 안내서](../web-renderer-guide.ko.md)를 참고한다.

<a id="기준선-세로-이동-클리핑"></a>

### 기준선, 세로 이동, 클리핑

페이스의 ascent 필드는 셀 위에서부터 잰 기준선 행이다. 배율 1에서 C 렌더러는 셀 위끝을
`y_baseline - ascent + dy`에 놓는다. 글리프별 `dy`가 양수이면 아래로 이동한다.
[SVF 메트릭](../../spec/SVF.ko.md)과 [C 렌더러 안내서](../c-renderer-guide.ko.md)를 참고한다.

`mkfont.py`가 이를 고르는 방법: `--ascent N`이 값을 정한다. 주지 않으면, 폰트의 ascent + descent가 셀에 들어갈 때는 폰트의 ascent
이고, 들어가지 않을 때는 탐침("한글AQg", `--latin`이면 "AQgjy")의 잉크를 셀 가운데에 놓는다. `--latin`이면 대문자 높이가 맨 위로
간다. 그다음 글리프마다:

- 기본: 왼쪽 베어링이 음수이면 오른쪽으로, 잉크가 셀 위로 넘치면 아래로 옮긴다(그 글리프는 기준선에서 벗어난다).
  오른쪽이나 아래쪽 경계를 넘는 잉크는 잘린다.
- `--clip-cell`: 모든 글리프가 하나의 수직 기준선을 따른다. 위아래로 넘치는 잉크를 자르고 표준 출력으로 개수를 알린다.
  음수인 왼쪽 베어링은 여전히 오른쪽으로 옮기고, 오른쪽으로 넘치는 잉크는 자른다.
- `--fit-cell`: 측정한 글리프 상자가 한 기준선 위에서 셀에 들어갈 때까지 크기를 1 px씩, 최소 8 px까지 낮춘다.
  맞는 크기가 없으면 실패한다.

실제 예(검증), NanumGothic Bold를 18 px로 16x16 셀에 그린다(ASCII와 음절 2,350자):

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/c.svf --size 18 --cell 16 --bpp 1 \
        --unicode ascii,ksx1001-hangul [--clip-cell | --fit-cell | --ascent 14 --clip-cell]

| 옵션 | Ascent | 결과 |
|---|---|---|
| 없음 | 13 (잉크 가운데 정렬) | 글리프를 하나씩 셀 안으로 옮김, 126,048 바이트 |
| `--clip-cell` | 15 (잘린 글리프가 가장 적음) | 글리프 2,445개 중 2,300개가 잘림 (위 368, 아래 2,299) |
| `--ascent 14 --clip-cell` | 14 | 2,327개 잘림 (위 2,321, 아래 36) |
| `--fit-cell` | 13, 15 px에서 | 잘림 0, 118,116 바이트 |

`--probe`: 셀을 직접 고르는 대신 아무것도 자르지 않는 키 큰 셀로 변환한다. 셀 높이와 ascent는 요청한 글리프의 잉크 상자에서 나오고, `--report FILE.json`이 그 상자를 쓴다(`--probe-cell H`는 높이 H의 셀이 얻을 `auto_ascent`를 잰다. `--probe`는 `--cell`, `--ascent`, `--clip-cell`, `--fit-cell`과 함께 쓸 수 없다).

검증: `mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/p.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul --probe --report $OUT/probe.json`은 18x18 셀, ascent 15, `123,116 바이트`, 잘린 것 없음(모드 `clip`), `width=146 ascent=15 descent=3`, 잉크 678을 준다. 셀이 폰트의 잉크만큼 크므로 이것은 설계 선택이 아니라 측정이다. 셀은 여전히 게임의 줄 간격이 정한다.

`tools/fontmetrics.py $OUT/c.svf`는 잉크가 advance 밖으로 나가는 글리프를 나열한다(여기서는 하나, `\`). 사후에 디센더를 낮추려면(또는
글리프를 올리려면) 글리프별 dy를 정한다.

    python3 tools/svfdy.py $OUT/c.svf $OUT/c-dy.svf --range 0x67,0x6a,0x70,0x71,0x79 --dy 1    # g j p q y one row lower
    python3 tools/svfdy.py $OUT/c-dy.svf --show

`--dy`는 그리는 시점에 글리프를 옮긴다. 페이스의 dy 범위(헤더 바이트 17/18)는 다시 계산한다. 줄의 범위는 그 줄에 쓰인 글리프의 dy 값에 따라 달라진다. dy를 지원하지
않는 엔진은 그 글리프를 셀 위치에 그린다.

**함정.** 폰트의 줄 간격보다 작은 셀은 잉크를 자를 수 있다. `--fit-cell`을 쓰거나, advance를 고정한 더 큰 셀을 써라. 페이스의
ascent를 바꾸면 모든 줄의 잉크가 놓이는 곳이 바뀐다(MCU 예제는 줄의 기준선을 그 줄의 맨 윗 행 + 페이스의 ascent에 놓는다).

<a id="ttc와-otc"></a>

### TTC와 OTC

<a id="opentype-cff-컬렉션-가변-폰트"></a>

`mkfont.py`는 컬렉션의 인덱스 0을 연다(synthetic: Galmuri9 + Galmuri7의 TTC는 Galmuri9와 똑같이 변환된다). 다른 페이스는 먼저 일반
폰트로 저장해 둔다(maker의 `ttc-face`와 같은 단계. TrueType든 CFF든 페이스에 똑같이 된다. CFF 페이스는 위 OpenType CFF 레시피처럼 출력을 `.otf`로 이름 붙인다).

    python3 maker/srcprep.py ttc-face F.ttc $OUT/F1.ttf --index 1

위치가 아니라 이름으로 고른다. Noto CJK 컬렉션에서 KR은 인덱스 0이 아니다. 이름을 나열한다.

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; [print(i, f['name'].getDebugName(4)) for i, f in enumerate(C('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').fonts)]"

검증(이 호스트의 Noto Sans CJK Regular 컬렉션): 페이스 열 개, 인덱스 0 Noto Sans CJK JP, 1 KR, 2 SC, 3 TC, 4 HK, 그다음 5-9 Noto Sans Mono CJK JP, KR, SC, TC, HK. 이렇게 얻은 페이스는 일반 정적 폰트처럼 레시피에 들어간다(위의
[OpenType CFF](#opentype-cff-otf)가 바로 이것이다).

<a id="가변-폰트"></a>

### 가변 폰트

`mkfont.py`는 기본 인스턴스를 그린다. 다른 인스턴스는 먼저 정적 인스턴스로 잘라 낸다(fontTools, maker의 `instance` 단계)([fontTools 가변 폰트 인스턴스 생성기](../recipes.ko.md#ref-fonttools) 참고).

    python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o $OUT/Caveat-Bold.ttf
    python3 tools/mkfont.py $OUT/Caveat-Bold.ttf $OUT/CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/mkfont.py ttf/caveat/Caveat-VF.ttf $OUT/CAV24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAVB24.SVF     # one face per call: several faces are a fallback chain
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAV24.SVF

검증: 기본 인스턴스(Regular 400)는 6,760 바이트로, 700 인스턴스는 7,192 바이트로 변환된다(각각 글리프 95개, "Hamburgefonstiv"의
폭은 Bold 141 px, Regular 136 px. 요약이 뺀 글자 1개는 요청했지만 폰트에 없는 글자이다). 이름 있는 인스턴스는 `fvar` 표에 있다(`Caveat`: Regular,
Bold; `EB Garamond`: Regular .. ExtraBold).

<a id="mac-형식-truetype"></a>

### Mac 형식 TrueType

**리소스 포크 폰트** (.dfont, suitcase, HFS에서 복사한 포크): TrueType 데이터는 'sfnt' 리소스이다.

    python3 tools/macsfnt.py list Font.dfont                 # type, id, name, bytes of sfnt / NFNT / FOND / fbit
    python3 tools/macsfnt.py extract Font.dfont $OUT/Font.ttf [--id N]

`macsfnt.py`는 AppleDouble(`._Font`)과 MacBinary 파일도 푼다. FreeType도 .dfont를 직접 열 수 있어서, 유니코드에 매핑된 폰트의 첫
페이스는 `mkfont.py Font.dfont ...`로 된다(합성 .dfont). 실행하지 않음: `.dfont`를 찾지 못했다. 가진 한글 Mac 폰트는 클래식 리소스 포크 파일
(`Seoul[FFIL]`)이며, 아래의 `list` / `extract` 실행이 그것을 읽는다.

**Mac 한글 cmap.** 한글 Mac용 폰트(와 일부 Windows 폰트)에는 플랫폼 1 / 스크립트 3(Mac Korean) 또는 플랫폼 3 / 인코딩 5(Wansung)
cmap, 즉 두 바이트 KS X 1001 코드만 있다. FreeType과 SVF 도구는 유니코드 cmap을 고르므로, 이런 폰트는 유니코드 cmap이 생기기 전까지
아무것도 그리지 못한다.

    python3 tools/macsfnt.py cmap $OUT/Font.ttf                   # platform=1 encoding=3 format=2 entries=... hangul=...
    python3 tools/macsfnt.py unicode $OUT/Font.ttf $OUT/FontU.ttf      # adds (3,1) format 4 [+ (3,10) format 12]

각 코드는 EUC-KR(KS X 1001)로 디코딩된다. Mac Korean에 대한 Apple 자체의 추가분은 KS X 1001에서 의미가 없으므로 매핑되지 않은 것으로
센다. Synthetic(`tools/test_macsfnt.py`): (1,3) format 2 cmap만 가진 폰트가 나열되고, 리소스 포크, AppleDouble, MacBinary에서 추출되고,
유니코드 서브테이블을 얻고, 그다음 `mkfont.py`가 그 음절을 그린다.

실제 폰트로 실행: Mac OS 7.6.1 한글판 CD의 Seoul(`Font Folder/Seoul[FFIL]`, Apple Korea / Elex Computer 1994-1995, 독점).
`list`는 `NFNT` 여덟 개, `FOND` 17408 "Seoul", `sfnt` 17408(6,159,836 바이트)을 보여 주고, `extract`는 그 6,159,836 바이트를 `Seoul.ttf`로
쓰며, `cmap`은 `platform=1 encoding=0 format=0 entries=232 hangul=0`과 `platform=1 encoding=3 format=2 entries=9799 hangul=2350`을 찍는다.
추출한 그대로의 `Seoul.ttf`에 `mkfont.py`를 쓰면 아무것도 그리지 못한다(글리프 1개, 72 바이트: 집합의 어떤 코드 포인트도 폰트에 없다).
`unicode`는 `8329 code points in the Unicode subtable, 1470 codes not in KS X 1001`을 보고하고, 그다음

    python3 tools/mkfont.py $OUT/SeoulU.ttf $OUT/seoul16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/seoul16.svf $OUT/SEOUL16.SVF --profile default --check

은 `124,868 바이트`, 글리프 2,446개, `width=156 ascent=13 descent=3`, 잉크 346을 준다. Seoul에는 손으로 만든 `bdat` 스트라이크(9~24 ppem)가
있어서 16 px에서는 FreeType이 윤곽선이 아니라 스트라이크를 그린다([내장 비트맵 스트라이크](bitmap-fonts.ko.md#내장-비트맵-스트라이크)). 스트라이크가 없는 17 px에서는
윤곽선을 래스터화한다(`125,164 바이트`, 글리프 2,444개: 윤곽선에 없는 코드 포인트 둘은 뺀다, `width=164 ascent=14 descent=3`). maker는 리소스 포크를 곧바로
읽는다. `Seoul[FFIL]`에 `detect.scan`을 쓰면 종류 `outline`, 레이블 "resource fork: sfnt 17408; bitmap strikes 9, 10, 12, 14, 16, 18, 20, 24; Mac Korean cmap",
경로 `mkfont`, `experimental fit`, `vector fit`을 준다. 한글 Mac의 클래식 비트맵 폰트는
[클래식 Mac 한글 비트맵 폰트](classic-mac.ko.md#클래식-mac-한글-비트맵-폰트)에 있다.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
