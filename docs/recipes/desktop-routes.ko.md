[English](desktop-routes.md) | **한국어**

# 레시피: 데스크톱 앱과 maker 경로

maker의 경로(데스크톱 앱과 서버): maker가 어떤 종류의 파일에 어떤 경로를 주는지, 그리고 각 경로가 실행하는 명령줄. 결과를 손으로 다시 만들 수 있다.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [maker 데스크톱](../maker-desktop.ko.md), [데스크톱 앱](../desktop-app.ko.md), [maker 서버](../../maker/README.ko.md).

<a id="데스크톱-앱과-maker-경로"></a>

## 데스크톱 앱과 maker 경로

UI 작업 순서는 [maker 데스크톱](../maker-desktop.ko.md), 렌더 미리보기는 [데스크톱 앱](../desktop-app.ko.md)을 참고한다.

maker(`maker/`, [desktop-app.md](../desktop-app.ko.md)의 데스크톱 앱, [maker/README.md](../../maker/README.ko.md)의 서버)는 각 파일의 종류를
감지하고(`maker/detect.py`) 그 종류에 `maker/routes.py`의 경로를 제공한다. 모든 경로는 레시피 문서의 도구들로 이루어진 명령줄이다. 실행하면 출력
폴더에 `svf/<dest>/<NAME>.SVF`와 `build-<id>/BUILD.md`가 쓰인다. BUILD.md는 페이스마다 원본 단계와 실행한 명령을 실제 경로와 함께
나열하므로, 어떤 결과든 이 장으로 손수 재현할 수 있다. 페이지에 보이는 레이블별 경로는 다음과 같다(`native` = 원본이 경로가 만드는
것과 정확히 같음. 나머지는 맞춤이며 experimental로 표시된다):

| 경로 (종류, 레이블) | 원본 종류 | 명령 (`routes.py`의 argv) | 레시피 |
|---|---|---|---|
| 완성형, `mkfont` | outline, outline-composite, bitmap, bdf-iso10646 | `mkfont.py SRC mkfont.tmp --size S --bpp B --unicode R` 다음 `svf2to3.py mkfont.tmp OUT --profile default`(비트맵: 스트라이크 크기에서 1 bpp) | [완성형 페이스](outline-fonts.ko.md#완성형-페이스-mkfontpy), [ISO 10646 BDF와 PCF](bitmap-fonts.ko.md#iso-10646-bdf와-pcf) |
| 자모, `composite` | outline-composite(음절이 합성인 TrueType) | `jamovec.py master SRC -o M.json --components [--adaptive]` 다음 `jamovec.py render M.json --size S --bpp B --binarize threshold --check -o OUT` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 1: 합성 글리프](outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `experimental fit` | outline(합성 아님) | 1 bpp: `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --check -o OUT [--eng E] --mask-font none`; 2 bpp: `jamoset.py ... --bpp 2 --check -o OUT` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 3: 완성형 음절에 맞추기](outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `mask fit` | GSUB 자모와 쓸 수 있는 마스크가 있는 outline 또는 outline-composite(1 bpp) | `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --mask-font SRC --no-clean --check -o OUT [--pylib DIR]` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 2: 결합 자모 셰이핑](outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `vector fit` | outline, outline-composite | `jamovec.py master SRC -o M.json [--adaptive]`(`--components` 없음) 다음 같은 `render` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 3: 완성형 음절에 맞추기](outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트) (`--components` 없는 `jamovec.py master`) |
| 완성형, `johab844` | dos-raw, 정확히 11,520 바이트(16 px 8x4x4) | `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng E]`(maker는 베이스를 `svf/` 아래에서 찾는다) | [그 밖의 DOS 시대 한글 폰트](dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트) |
| 자모, `dos raw` | dos-raw | `jamoset.py SRC --layout L --check -o OUT [--eng E] [--face 0\|1]`(`--face`는 도깨비 프린터 레이아웃용) | [그 밖의 DOS 시대 한글 폰트](dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트) |
| 자모, `hanterm` | bdf-johab | `jamoset.py SRC --layout hanterm-johab --check -o OUT [--eng E]` | [hanterm](x-window.ko.md#hanterm) |
| 완성형, `bdfface` | bdf-ksc5601(BDF, 또는 `pcf-bdf` 단계를 거친 PCF) | `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST -o OUT`(`WxH` = BDF의 박스) | [KS C 5601 BDF와 PCF](bitmap-fonts.ko.md#ks-c-5601-bdf와-pcf) |
| 자모, `bdfface + from-svf fit` | bdf-ksc5601 | `bdfface.py` 페이스 다음 `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS C 5601 BDF와 PCF](bitmap-fonts.ko.md#ks-c-5601-bdf와-pcf) |
| 자모, `mac fbit 1.0` | mac-fbit1 | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | [클래식 Mac 한글 비트맵 폰트](classic-mac.ko.md#클래식-mac-한글-비트맵-폰트) |
| 자모, `hwp1` | hwp1(HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT`의 페이스; 로컬 모드) | `jamoset.py SRC --layout hwp1 --face N --check -o OUT [--eng E]` | [HWP 1.x와 2.x 폰트](dos-fonts.ko.md#hwp-1x와-2x-폰트) |
| 완성형, `hwp bdf + mkfont` | hwp1, ks-raw(HWP 3.0 한글 FNT는 로컬 모드; 헤더 없는 KS X 1001 덤프) | `hwpfont.py bdf SRC [--face N] [--syllables all] [--ascii E] -o hwp.bdf`, `mkfont.py hwp.bdf mkfont.tmp --size S --bpp 1 --unicode R`, `svf2to3.py mkfont.tmp OUT --profile default`(`E`가 없으면 범위에서 `ascii`를 뺀다) | [HWP 1.x와 2.x 폰트](dos-fonts.ko.md#hwp-1x와-2x-폰트), [KS X 1001 원시 덤프](dos-fonts.ko.md#ks-x-1001-원시-덤프) |
| 자모, `hwp3 844` | 8x4x4 벌 체계가 있는 ks-raw(HWP 3.0 `HAN16_*.FNT`) | `jamoset.py SRC --layout 844-hwp3 --check -o OUT [--eng E]` | [HWP 3.0 FNT 폰트](dos-fonts.ko.md#hwp-30-fnt-폰트) |
| 자모, `hwp bdf + from-svf fit` | ks-raw | `hwp bdf + mkfont` 페이스를 `precomposed.svf`로, 다음 `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS X 1001 원시 덤프](dos-fonts.ko.md#ks-x-1001-원시-덤프) |
| 자모, `mac fbit 7.1 direct` / `derived` | mac-fbit3 + HTBL 1 | `macfbit_svf.py build FBIT HTBL -o OUT --mode direct\|derived [--latin SUITCASE]` | [HangulTalk 7.1.x type-3 `fbit` 폰트](classic-mac.ko.md#클래식-mac-hangultalk-71) |
| 완성형, `mac fbit 7.1 bdf + mkfont` | mac-fbit3 + HTBL 1 | `macfbit3.py bdf FBIT HTBL NAME mac.bdf`, `srcprep.py bdf-pixel-size mac.bdf mac-sized.bdf --size S`, `mkfont.py mac-sized.bdf mkfont.tmp --size S --bpp 1 --unicode ...`, `svf2to3.py ... --profile default` | [HangulTalk 7.1.x type-3 `fbit` 폰트](classic-mac.ko.md#클래식-mac-hangultalk-71) |
| 완성형 또는 자모, `copy` | svf-precomposed, svf-jamo | 업로드된 그대로 쓰면 없음. v2 페이스나 요청한 JSET 변경에는 `svf2to3.py SRC OUT --jset-version V --check` | [기존 SVF](svf-and-ttf.ko.md#기존-svf) |
| 완성형 또는 자모, `svf2ttf` | svf-precomposed, svf-jamo | `copy`가 읽는 페이스를 아래의 내보내기로만 쓴다. SVF는 쓰지 않음 | [SVF 페이스를 다시 TTF 비트맵 폰트로](svf-and-ttf.ko.md#svf-페이스를-다시-ttf-비트맵-폰트로) |
| 완성형, `bdfface`; 자모, `bdfface + from-svf fit` | recipe(`maker/recipes/`의 알려진 ROM 세트, 로컬 모드) | 레시피의 한글 항목과 영문 항목을 `rawcarve.py bdf`로, `bdfface.py --hangul H --ascii A --cell WxH --chars-from LIST -o OUT`. fit은 그 페이스를 `precomposed.svf`로 만든 뒤 `jamoset.py --layout L --from-svf precomposed.svf --mask-font none [--eng E] --check -o OUT`. 그 앞에 세트 파일들의 `rawcarve.py region --group ...`(경로를 통째로: 폴더 이름의 쉼표도 그대로), 조합 항목은 `rawcarve.py compose`, 타일 속 영문 폰트는 `ink` + `eng` | [한글 VGA 폰트 ROM (86Box)](rom-86box.ko.md#한글-vga-폰트-rom-86box), [MAME 폰트 ROM](rom-mame.ko.md#mame-세트의-한글-폰트-rom) |
| 자모, `spec` | recipe(SPC-1500) | `rawcarve.py region ...`, `rawcarve.py eng REGION ...`, `jamoset.py --layout spec --spec spc1500 REGION --eng E --check -o OUT` | [삼성 SPC-1500](rom-mame.ko.md#삼성-spc-1500-반전된-rom-네-개의-자모-세트정확) |
| 자모, `dos raw` | recipe(ROM 속 raw 세트: X Se Dae Quiz) | `rawcarve.py region`, `ink`, `cut`(raw 폰트), `ink` + `eng`(영문 폰트), `jamoset.py RAW --layout L --eng E --check -o OUT` | [X Se Dae Quiz](rom-mame.ko.md#x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용) |
| 자모, `from-svf fit` | svf-precomposed, 1 bpp | `[svf2to3.py ... source-v3.svf]` 다음 `jamoset.py --layout L --from-svf SRC --check -o OUT [--eng E]` | [기존 SVF](svf-and-ttf.ko.md#기존-svf) |

`L`은 맞춤에서는 `844` 또는 `adaptive`이고, 그 밖에는 원본 종류가 지명하는 레이아웃이다. `[--eng E]`는 페이지가 폰트와 짝지은 영문
동반 폰트이다.

"also write TTF / BDF"(`options.export`)가 켜져 있으면 모든 페이스 단계 뒤에 형식마다 `export` 단계가 하나 따른다:
`svf2ttf.py ttf|bdf FACE OUT [--licence FILE]`. `OUT`은 페이스 이름에 `.ttf` / `.bdf`를 붙인 것으로 페이스 옆에 쓰며, `FILE`은
작업이 그 폰트에 대해 아는 라이선스이다(없으면 svf2ttf.py가 원본 폰트의 라이선스가 적용된다고 적는다). "TTF as composites"는
자모 세트의 TTF에 `--composite`를 더한다.

일부 원본은 먼저 변환이 필요하다. BUILD.md는 이 단계를 경로의 명령 앞에 나열한다(각 단계는 앞 단계가 쓴 파일을 읽는다).

| 단계 | 명령 |
|---|---|
| `rsrc-sfnt` | `macsfnt.py extract SRC OUT --id N` |
| `mac-cmap` | `macsfnt.py unicode SRC OUT` |
| `ttc-face` | `srcprep.py ttc-face SRC OUT --index N` |
| `instance` | `python3 -m fontTools.varLib.instancer SRC AXIS=VALUE ... -o OUT` |
| `pcf-bdf` | `srcprep.py pcf-bdf SRC OUT` |
| `mac-fork`, `mac-fork-named`(macOS 전용), `mac-htbl` | `srcprep.py mac-fork SRC OUT` 등: AppleDouble / MacBinary 파일의 리소스 포크, 네이티브 포크, HTBL 1 표 |
| `mac-fbit3` | `macfbit3.py fbit SRC OUT` |

검증: 이 표의 경로 레이블과 종류는 `routes.py`에서 읽고, 이 호스트 폰트의 사본이 든 폴더에 `detect.scan`과 `routes.routes`를 실행해
확인했다: NanumGothic Bold, Caveat-VF, Noto Sans CJK Regular 컬렉션의 페이스 열 개(인덱스 0-9)는 `outline`이고 `mkfont` 경로를 얻는다(Caveat, NanumGothic, Noto CJK의 각 페이스는 `experimental fit`과 `vector fit`도). neodgm.ttf는 `outline-composite`로 `mkfont`, `composite`(native), `vector fit`을 얻는다. `wqy_12pt.bdf`(종류 `bdf-iso10646`)와 `18x18ko.pcf.gz`(`bitmap`, 크기 [18])는 `mkfont`만, `hanglm16.pcf.gz`는 `bdf-ksc5601`로 `bdfface`와 `bdfface + from-svf fit`, NEODG16.SVF(`svf-precomposed`)는 `copy`와 `from-svf fit`, NEODG16A.SVF(`svf-jamo`)는 `copy`를 얻는다.

레시피 문서의 독점 원본 사본에 같은 점검을 했다(2026-11-22. 자세한 것은 각 레시피에): 원시 DOS 폰트는 `dos-raw`에 `dos raw`(11,520 바이트짜리는 `johab844`도),
`johabm16.bdf`는 `bdf-johab`에 `hanterm`, `batang24.bdf`는 `bdf-ksc5601`에 `bdfface`와 `bdfface + from-svf fit`, 스트라이크가 있는 굴림과 Mac Seoul은
`outline-composite` / `outline`에 `mkfont`(비트맵 전용 Seoul은 `bitmap`에 `mkfont`만), Windows FON은 경로 없이 레이블만("no Unicode character map, mkfont cannot read it"),
HWP 1.x, HWP 3.0, KS X 1001 덤프 파일은 각 레시피대로(2026-11-23: 한글 파일 하나에 `hwp1` 항목 셋과 `hwp1`, `hwp bdf + mkfont`; `ks-raw`에
`hwp bdf + mkfont`, 16 px HWP 3.0 FNT에는 `hwp3 844`, 그리고 실험적인 `hwp bdf + from-svf fit`; 여기서 읽는 레이아웃이 아닌 `.PFT`, 예컨대 태백의
`HANJA24.PFT`는 `hwp-pft` "other"), 로컬 모드의 Mac 폰트는 위와 같다(1.0 폰트는 `mac-fbit1`에 `mac fbit 1.0`). `mask fit` 행은 `mask_ok`를 설정하면
(서버가 `freetype-py`와 `uharfbuzz`를 import할 수 있을 때 설정한다) neodgm.ttf, Noto Sans CJK KR, 맑은 고딕에 나타난다.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
