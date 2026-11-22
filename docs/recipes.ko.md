[English](recipes.md) | **한국어**

# 레시피: 폰트에서 SVF 페이스(face)까지

`svf/`의 페이스를 업스트림 폰트에서 만든 방법과, 이 저장소의 도구가 읽을 수 있는 모든 종류의 한글 폰트 원본에서 페이스를 만드는
방법을 설명한다. 모든 도구는 [tools.ko.md](tools.ko.md)에 설명되어 있고, 포맷은 `spec/SVF.md`이다.

`ttf/`의 OFL 폰트와 `svf/`의 페이스 외에는 어떤 폰트 데이터도 이 저장소에 없다. 독점 폰트(클래식 Mac, HWP, 그 밖의 DOS 시대
폰트)의 사용법은 방법과 명령만 설명하며, 파일은 직접 마련해야 한다.

**규약.** 명령은 저장소 루트에서 실행한다. `$OUT`은 직접 정한 스크래치 폴더이다
(`OUT=$HOME/work/tmp/recipes; mkdir -p $OUT`). 여기의 어떤 명령도 다른 곳에는 쓰지 않는다. 대문자 이름(`NG16J.SVF`,
`FACE.SVF`)은 직접 이름 붙이는 출력이다.

**정규 단계.** 아래의 모든 `mkfont.py` 명령은 `svf2to3.py --profile default`가 다시 배치하는 페이스를 쓴다([완성형 페이스](#완성형-페이스-mkfontpy)에
한 번만 보였다). 다른 명령은 간결함을 위해 이를 생략했다. 보관할 페이스에는 이 단계를 더한다. 여기서 실행: Noto 1 bpp 페이스(125,196 바이트)와 BDF 1
bpp 페이스(115,684 바이트)의 크기가 그대로이다.

**"verified"의 뜻.** 모든 명령 블록은 셋 중 하나를 말한다. *Verified*(또는 *여기서 실행*): 2026-11-22에 저장소 자체의 폰트나 이
호스트의 폰트(Debian의 `fonts-noto-cjk`, `xfonts-*`, DOSBox-X), 또는 관리자가 가진 독점 폰트(쓰인 곳마다 이름과 출처 제품을 적었다.
어느 것도, 그 바이트도 이 저장소에 없다)로 적힌 그대로 실행했고, 인용한 수치는 그 실행에서 나온 것이다.
페이스의 바이트 크기, 글리프 수, [페이스 점검](#페이스-점검)의 렌더 점검(`svfline.py measure`의 width / ascent / descent와 샘플
줄의 잉크 픽셀 수), 자모 세트라면 `--check`의 IoU이다. *Synthetic*: 테스트(`tools/test_recipes.py`, `tools/test_build_faces.py`,
`tools/test_macsfnt.py`, maker의 테스트)에서만, 테스트 안에서 만든 폰트로 실행한 것. *실행하지 않음: 이유*: 그런 종류의 원본을 찾지
못했다. 크기는 도구의 버전에 따라 달라진다. "약"으로 읽고 실행 결과를 믿어라.

목차:

- [빠른 시작: 입력 종류별](#빠른-시작-입력-종류별)
- [페이스 점검](#페이스-점검)
- [아웃라인 폰트](#아웃라인-폰트)
- [비트맵 폰트](#비트맵-폰트)
- [DOS 시대 원시 폰트](#dos-시대-원시-폰트)
- [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트)
- [기존 SVF](#기존-svf)
- [데스크톱 앱과 maker 경로](#데스크톱-앱과-maker-경로)
- [svf/의 페이스](#svf의-페이스)
- [참고](#참고)
- [svf/에 페이스 추가하기](#svf에-페이스-추가하기)

## 빠른 시작: 입력 종류별

가진 것을 찾아라. 행이 방법과 명령이 있는 절을 알려 준다. "완성형"은 완성형 페이스(음절마다 글리프, 1 또는 2 bpp), "자모"는 자모
세트(조각과 표, 1 bpp 또는 2 bpp, 크기는 약 6분의 1)이다.

| 가진 것 | 완성형 | 자모 | 절 |
|---|---|---|---|
| TTF, 또는 유니코드 cmap이 있는 OTF(CFF) | `mkfont.py`(1, 2 bpp) 다음 `svf2to3.py --profile default` | `jamoset.py --from-ttf`(1 bpp: `--binarize threshold --mask-font none`, 2 bpp: `--bpp 2`); 합성 음절 폰트에는 `jamovec.py` | [아웃라인 폰트](#아웃라인-폰트) |
| TTC / OTC (Noto CJK) | `srcprep.py ttc-face`로 일반 폰트를 만든 뒤 위와 같이 | 위와 같이 | [TTC와 OTC](#ttc와-otc) |
| 가변 폰트 | `fontTools.varLib.instancer` 다음 위와 같이 | 위와 같이 | [가변 폰트](#가변-폰트) |
| Mac TrueType(`.dfont`, suitcase, 한글 전용 cmap) | `macsfnt.py extract` / `unicode` 다음 위와 같이 | 위와 같이 | [Mac 형식 TrueType](#mac-형식-truetype) |
| 내장 스트라이크(`EBDT`, `bdat`)가 있는 아웃라인 폰트 | 스트라이크의 크기로 `mkfont.py --size`, 1 bpp | 없음 | [내장 비트맵 스트라이크](#내장-비트맵-스트라이크) |
| 유니코드(`ISO10646`) BDF 또는 PCF | 파일 자신의 픽셀 크기로 `mkfont.py`, 1 bpp | `jamoset.py --from-svf`로 맞춤 | [ISO 10646 BDF와 PCF](#iso-10646-bdf와-pcf) |
| KS C 5601 / KS X 1001(X Window) BDF 또는 PCF | `srcprep.py pcf-bdf`(PCF만) 다음 `bdfface.py` | `jamoset.py --from-svf` | [KS C 5601 BDF와 PCF](#ks-c-5601-bdf와-pcf) |
| hanterm johab BDF | 없음 | `jamoset.py --layout hanterm-johab` | [hanterm](#hanterm) |
| HBF | `bdfface.py`의 ASCII 절반으로만 | 없음 | [HBF](#hbf) |
| Windows `.FNT` / `.FON` | 그 픽셀 크기로 `mkfont.py`(열리지만 FreeType이 유니코드 맵을 주지 않아 아무것도 그리지 못함) | 없음 | [Windows FNT와 FON](#windows-fnt와-fon) |
| DOS 원시 자모 조각 폰트(8x4x4 `HANGUL.FNT`, san, 도깨비, Kyra...) | `johab844.py`(16 px 8x4x4) | `jamoset.py --layout L` | [DOS 시대 원시 폰트](#dos-시대-원시-폰트) |
| HWP `.PFT` 한글, KS X 1001 원시 덤프 | 리더 없음 | 리더 없음 | [HWP 1.x와 2.x 폰트](#hwp-1x와-2x-폰트), [KS X 1001 원시 덤프](#ks-x-1001-원시-덤프) |
| Mac HangulTalk 1.0 `fbit`(세트 45개 + `fdef`) | 없음 | `jamoset.py --layout mac-fbit-45sets` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| Mac HangulTalk 7.1 type-3 `fbit` + HTBL 1 | `macfbit3.py bdf` + `mkfont.py` | `macfbit_svf.py build` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| SVF 페이스 | `svfdy.py`, `svf2to3.py` | `jamoset.py --from-svf`(1 bpp 원본) | [기존 SVF](#기존-svf) |

모든 행의 점검은 같다: [페이스 점검](#페이스-점검)(샘플 줄의 measure와 잉크, 자모 세트는 `--check`의 IoU). 비트맵 원본에서 만든 1 bpp 페이스는 1 bpp로 남는다. 비트맵에서 안티에일리어싱을 만드는 도구는 없다. 대상의 메모리가 적으면 자모
세트를 고르고(2,350 음절 16 px 페이스는 약 115 KB, 그 자모 세트는 약 20 KB), 모든 음절이 원본과 정확히 같아야 하면 완성형을
고른다.

## 페이스 점검

<a id="새-페이스-점검"></a>

아래의 모든 레시피는 같은 점검으로 끝난다. 샘플 줄은 `안녕하세요 ABC 123`이고, 따로 적지 않으면 페이스는 16x16 셀의 16 px이다.

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF       # width=W ascent=A descent=D
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray   # a 200x24 GRAY8 buffer
    python3 tools/fontmetrics.py FACE.SVF                                 # glyphs whose ink reaches past the advance
    python3 tools/svf2to3.py FACE.SVF $OUT/x.SVF --check                  # re-layout and compare every glyph
    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf -o $OUT/m.tsv

- 파일 크기와 글리프 수(코드 포인트 표의 항목 수)는 도구 자신의 요약 줄에 나온다. `mkfont.py`는 이를 한국어로 출력한다
  (`글리프 2446개 ... 125,520 바이트`).
- 잉크는 `line` 버퍼에서 0이 아닌 바이트의 수이다:
  `python3 -c "import sys;print(sum(1 for b in open(sys.argv[1],'rb').read() if b))" $OUT/out.gray`. 아무것도 그리지 못하는 페이스는
  잉크가 0이다.
  위의 200x24 버퍼와 기준선 16은 16 px 셀에 맞는다. 셀 C가 16이 아닌 페이스(12, 15, 24, 40, 48 px)의 레시피 잉크 수치는
  `line 400 C+8 0 C`로 얻은 것이다(너비 400의 버퍼, 기준선은 셀 높이, C+8행. 버퍼는 잰 너비 이상, 셀 + descent 이상의 높이여야 하며
  아니면 줄이 잘린다): 24 px 페이스라면 `python3 tools/svfline.py line 400 32 0 24 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray`.
  16 px 수치는 모두 200x24 명령으로, 다른 셀은 모두 이 규칙으로 재현된다.
- 자모 세트는 `--check`(`jamoset.py`와 `jamovec.py`)로 판정한다. 조각에서 음절 11,172개를 모두 조합하고 표 오류에서 실패한다. 그
  앞의 맞춤 줄은 조각과 원본 음절의 IoU를 출력한다(`fit: 11172 syllables, IoU 0.817`). `--check`는 맞춤이 나쁘다고 실패하지는 않는다.
  IoU를 읽고 결과를 직접 보라(`svfline.py line`, 또는 `web/` 선택기).
- `svf2to3.py --check`는 `svfline`으로 글리프마다 비교하고, `facecheck.py`는 페이스를 매니페스트와 대조한다.
  `tools/build/build_faces.py`는 `svf/`의 페이스를 다시 빌드한다([svf/의 페이스](#svf의-페이스) 참고).

기준 실행(verified), 아래의 16 px NanumGothic Bold: 1 bpp `125,520` 바이트, 글리프 2,446개, `width=146 ascent=14 descent=2`, 잉크 677.

## 아웃라인 폰트

FreeType은 TrueType과 CFF(OpenType `.otf`)를 똑같이 읽으므로, 유니코드 cmap이 있는 정적 TTF나 OTF는 곧바로 도구에 들어간다.
`jamoset.py --from-ttf`, `jamoaa.py`, `jamovec.py`, `--binarize threshold|ridge`는 윤곽선을 직접 평탄화하며(fontTools pen, 정확 면적
커버리지) 둘에서 똑같다. 컬렉션, 가변 폰트, Mac 형식 폰트는 먼저 한 단계가 필요하다(아래).

### 완성형 페이스 (`mkfont.py`)

원본: `ttf/nanumgothic/NanumGothic-Bold.ttf`. 완성형, 1 bpp, 그다음 정규 레이아웃 단계:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-1bpp.svf \
        --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/ng16-1bpp.svf $OUT/NG16.SVF --profile default --check

Verified: `125,520 바이트`(`mkfont.py`의 임시 파일), 글리프 2,446개(한글 음절 2,350개). 렌더는 `width=146 ascent=14 descent=2`,
잉크 677. `svf2to3.py ... --profile default --check`는 다시 125,520 바이트를 쓴다(글리프는 같고 레코드 순서만 다르다. 처음 다른 바이트는 813번). `data_in=86332 data_out=86332`를 보고한다.

`mkfont.py`는 레코드를 자기 순서로 쓴다. `svf2to3.py --profile default`는 이를 `default` 프로필의 정규 순서로 다시 배치한다(배포된
페이스, `tools/build/build_faces.py`, maker 모두 이 단계로 끝난다). `--check`가 픽셀이 같음을 증명한다. 다른 대상(`mcu-strict`,
`dos`, `wasm`, `full`, `simd16`)에 맞게 배치하려면 그 `--profile`을 쓴다.

안티에일리어싱(2 bpp): 같은 명령에 `--bpp 2`(`195,760 바이트`, 글리프 2,446개, `width=146 ascent=14 descent=2`, 잉크 847. 커버리지는 4단계로
양자화된다). 정규 단계는 이번에도 크기(195,760 바이트)를 유지하고 픽셀이 같음을 증명한다. `--bpp 8`은 전체 커버리지를 유지한다(8 bpp 페이스는 호스트용). 크기, 셀, ascent, 클리핑을 고르는 `mkfont.py` 옵션은
[기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑)에, `svf/`의 행 레시피 전체는
[완성형 글리프 레시피](#완성형-글리프-레시피-mkfont-행)에 있다.

**문자 집합이 필요하다**(`--unicode SET` 또는 `--chars-from FILE`). 둘 다 없으면 `mkfont.py`는 종료 코드 2로 끝난다. 이름은
[참고](#참고)에 있다.

### OpenType CFF (`.otf`)

Noto Sans CJK KR은 누구나 구할 수 있는 CFF 폰트이다(SIL OFL 1.1. Debian의 `fonts-noto-cjk`가 KR, JP, SC, TC, HK 페이스의 컬렉션인
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`로 싣는다. [TTC와 OTC](#ttc와-otc) 참고). KR 페이스를 일반 `.otf`로 저장해서
bake한다.

    python3 maker/srcprep.py ttc-face /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc $OUT/NotoSansCJKkr.otf --index 1
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py $OUT/NotoSansCJKkr.otf $OUT/noto16-2bpp.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --binarize threshold \
        --mask-font none --check -o $OUT/noto16-jamo-1bpp.svf
    python3 tools/jamoset.py --layout 844 --from-ttf $OUT/NotoSansCJKkr.otf --size 16 --bpp 2 --check -o $OUT/noto16-jamo-2bpp.svf

Verified(부분 집합이 아닌 전체 폰트): 페이스 이름은 "Noto Sans CJK KR"; 1 bpp `125,196 바이트`, 글리프 2,446개, `width=141 ascent=11
descent=5`, 잉크 472; 2 bpp `197,992 바이트`, 잉크 700; 자모 세트 `19,040 바이트`, 글리프 439개, 조각 344개, 음절 11,172개에 대한 IoU
0.786(6.9 초), `width=146 ascent=14 descent=2`, 잉크 477; 2 bpp 자모 세트 `23,268 바이트`, 글리프 439개, level 오차 0.208, level 2의 IoU 0.781, 62 초, `width=141 ascent=14 descent=2`, 잉크 722(CFF 폰트의 자모 세트는 TrueType 폰트보다 맞춤이 나쁘다. NanumGothic의 0.817과 0.822에 비해 0.786과 0.781). ascent는 폰트 자신의 것이므로 폰트마다 기준선이 다르다.
[기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑)을 참고한다.

### TrueType와 OpenType 폰트에서 만드는 자모 세트

자모 세트(조합형)는 조각과 표를 담는다. 모든 음절은 조각 둘 또는 셋의 OR이다. 윤곽선 폰트에서 조각을 얻는 방법은 폰트가 무엇을
담고 있느냐에 따라 세 가지이다.

**1. 합성 글리프(TrueType `glyf`).** 어떤 폰트는 음절을 그 자모 글리프의 합성으로 저장한다. 그러면 구성 요소가 곧 조각이다.

    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 1 --check -o $OUT/NEOVEC16.SVF
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

Verified: neodgm.ttf에는 합성 음절 11,172개가 있다. `master`는 25 초 걸렸고(조각 344개, 잘못된 모양 0), 1 bpp 렌더는 15,724
바이트, 2 bpp 렌더는 19,452 바이트이며 둘 다 음절 11,172개가 조합되었다. 벡터 렌더는 래스터 맞춤 NEODG16A와 음절 11,172개 중
2,633개에서 다르다(2026-11-03에 센 값이며 다시 세지 않았다. 픽셀 폰트에 대한 FreeType의 픽셀 스냅과 `jamovec`의 정확 면적 래스터라이저의 차이). 먼저 폰트를 점검한다.

    python3 -c "from fontTools.ttLib import TTFont; f=TTFont('FONT.ttf'); c=f.getBestCmap(); g=f['glyf']; print(sum(g[c[x]].isComposite() for x in c if 0xAC00<=x<=0xD7A3))"

`ttf/`에서: neodgm은 합성 음절 11,172개; NanumGothic Regular/Bold와 NanumMyeongjo Bold는 8,822개(KS X 1001 밖의 음절은 합성이고
2,350자는 그렇지 않다); NanumPenScript는 8,693개; 나머지는 없음. 일부만 합성인 폰트에 `--components`를 주면 합성 글리프만 쓴다
("auto"는 대부분의 음절이 합성이면 구성 요소를 고른다). **CFF / CFF2(OpenType `.otf`)에는 합성 글리프가 없다.** 모든 음절이
평면 윤곽선이므로, 조각은 다음 두 방법에서 나와야 한다.

**2. 결합 자모 shaping(GSUB `ljmo` / `vjmo` / `tjmo`).** 이 feature가 있는 폰트는 결합 자모 U+1100..을 위치별 변형으로 그린다.
`jamoset.py --from-ttf ... --mask-font FONT`는 HarfBuzz로 각 음절을 결합 자모로 shaping하고, 그 변형을 맞춰진 조각을 제한하는
마스크로 쓴다(`freetype-py`와 `uharfbuzz`가 필요하며, `--pylib DIR`이 그 위치를 가리킨다). 두 모듈을 스크래치 폴더에 설치해 여기서 실행했다
(`pip install --target $OUT/pylib freetype-py uharfbuzz`, 그다음 `--pylib`에 그 폴더. 시스템이나 사용자 site에는 아무것도 설치하지 않는다):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/neodgm/neodgm.ttf --size 16 --binarize threshold \
        --mask-font ttf/neodgm/neodgm.ttf --no-clean --check --pylib $OUT/pylib -o $OUT/NEO16M.SVF

`ttf/`의 neodgm.ttf에는 세 feature가 있어서 스스로 마스크 폰트가 된다. `15,740 바이트`, 글리프 439개, 조각 344개, 음절 11,172개에 대한 IoU
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
이를 주고, `from-svf fit`과 `bdfface + from-svf fit` 경로는 자동으로 둔다. 별도의 연구 저장소가 이
feature가 돌려주는 조각을 12 px, 힌팅 켬으로 측정했다. 맑은 고딕은 5/2/1 세트(조각 164개), Noto Sans CJK KR은 6/2/4(조각 264개;
Noto TTC에서 KR은 인덱스 1)를 준다. 이것으로 곧바로 만든 페이스는 잘 읽히지만 완성형 글리프와 한두 픽셀씩 다르다(평균 IoU
약 0.58). 폰트의 결합 조각이 완성형 음절과 다르게 배치되어 있기 때문이다. 그 작업은 같은 바이트 예산에서 LIST 예외로 저장한
자주 쓰는 음절 수십 개(`jamoexc.py`)가 세트를 늘리는 것보다 더 많이 개선한다는 것도 알아냈다. 이 폰트들의 데이터는 이 저장소에 없다.

**3. 완성형 음절에 맞추기** (TrueType든 CFF든 모든 폰트):

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 \
        --binarize threshold --mask-font none --check -o $OUT/NG16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-ttf ttf/gowunbatang/GowunBatang-Bold.ttf --size 20 \
        --binarize threshold --mask-font none --check -o $OUT/GB20J.SVF

Verified(2026-11-22): NanumGothic Bold 16 px를 8x4x4로 만드는 데 12 초, 20,064 바이트, 조각 344개, 음절 11,172개에 대한 IoU 0.817이었다.
Gowun Batang Bold 20 px adaptive는 89 초, 73,220 바이트, 세트 32/24/12와 12 x 12 클래스, IoU 0.934였다. `jamofit.py`는 조각을
맞추고(1 bpp 음절에 대한 좌표 하강), `jamoadapt.py`는 조각을 공유하는 음절들이 서로 어긋나는 곳에서 세트를 쪼개고(`--layout
adaptive[:NI,NM,NF]`), `jamoseg.py`는 음절의 윤곽선을 자모별 윤곽선으로 분리하며(`jamoaa.py`와 `jamovec.py`가 쓴다),
`--components` 없이 쓰는 `jamovec.py master`는 결정 크기에서 한 번 분리하고 모든 크기를 같은 조각에서 렌더한다. `--binarize
mono`(기본값)에는 freetype-py가 필요하다. `threshold`와 `ridge`는 저장소 자체의 정확 면적 래스터라이저를 쓴다(fontTools pen이므로
TrueType과 CFF 모두 된다). 맞춤은 근사이다. IoU를 읽고 결과를 직접 보라(`web/` 선택기, 또는 `svfline.py line`).

**함정.** 음절을 적게 그리는 폰트(Black Han Sans: 2,581자)는 그 음절만 맞춘다(`--present-only`, 기본값). 나머지는 가장 가까운
조각으로 조합된다. `--check`는 음절 11,172개를 모두 조합하고 표 오류에서 실패하며, 맞춤이 나쁘다고 실패하지는 않는다.

### 안티에일리어싱된 (2 bpp) 페이스

완성형 (verified, [완성형 페이스](#완성형-페이스-mkfontpy)): `mkfont.py FONT OUT --size 16 --bpp 2 --unicode ascii,ksx1001-hangul` (NanumGothic
Bold: 195,760 바이트, 글리프 2,446개). 커버리지는 4단계로 양자화되고, 리더는 level x 85로 되살린다. 2 bpp 페이스는 같은 1 bpp
페이스의 약 1.5-1.6배이다. `--bpp 8`은 전체 커버리지를 유지한다(8 bpp 페이스는 호스트용).

자모 세트:

    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 --bpp 2 \
        --check -o $OUT/NG16JA.SVF                     # verified: 73 s, 24,960 bytes, level error 0.233, IoU at level 2 0.822
    python3 tools/jamovec.py render $OUT/MASTER.json --size 16 --bpp 2 -o $OUT/OUT.SVF      # from a vector master

`--bpp 2`는 `jamoaa.py`를 실행한다. 음절을 정확 면적 커버리지로 래스터화하고, 1 bpp 맞춤의 영역이 각 픽셀을 어느 조각이 소유하는지
정하며, 각 조각의 level은 그 조각을 공유하는 음절들의 중앙값으로 정한 뒤 level 오차에 대해 다듬는다(`--aa-refine N`, 2회). `--clean`
(2 bpp에서는 켜짐)은 고립된 잡음을 지운다. 조각은 픽셀별 최댓값으로 OR된다. 2 bpp에는 fontTools만 필요하다.

**함정.** 다른 조각 위의 안티에일리어싱된 조각은 합이 아니라 최댓값을 취한다. 가늘게 교차하는 획은 완성형 글리프보다 옅게
보인다. 1 bpp 대상(MONO_PAGE)은 그리는 시점에 2 bpp 페이스를 임계값으로 자른다(대상의 `threshold`). 모노 디스플레이에는 1 bpp
페이스를 주어라.

### 기준선, 세로 이동, 클리핑

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

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/c.svf --size 18 --cell 16 --bpp 1 \
        --unicode ascii,ksx1001-hangul [--clip-cell | --fit-cell | --ascent 14 --clip-cell]

| 옵션 | Ascent | 결과 |
|---|---|---|
| 없음 | 13 (잉크 가운데 정렬) | 글리프를 하나씩 셀 안으로 옮김, 126,048 바이트 |
| `--clip-cell` | 15 (잘린 글리프가 가장 적음) | 글리프 2,445개 중 2,300개가 잘림 (위 368, 아래 2,299) |
| `--ascent 14 --clip-cell` | 14 | 2,327개 잘림 (위 2,321, 아래 36) |
| `--fit-cell` | 13, 15 px에서 | 잘림 0, 118,116 바이트 |

`--probe`: 셀을 직접 고르는 대신 아무것도 자르지 않는 키 큰 셀로 bake한다. 셀 높이와 ascent는 요청한 글리프의 잉크 상자에서 나오고, `--report FILE.json`이 그 상자를 쓴다(`--probe-cell H`는 높이 H의 셀이 얻을 `auto_ascent`를 잰다. `--probe`는 `--cell`, `--ascent`, `--clip-cell`, `--fit-cell`과 함께 쓸 수 없다).

Verified: `mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/p.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul --probe --report $OUT/probe.json`은 18x18 셀, ascent 15, `123,116 바이트`, 잘린 것 없음(모드 `clip`), `width=146 ascent=15 descent=3`, 잉크 678을 준다. 셀이 폰트의 잉크만큼 크므로 이것은 설계 선택이 아니라 측정이다. 셀은 여전히 게임의 줄 간격이 정한다.

`tools/fontmetrics.py $OUT/c.svf`는 잉크가 advance 밖으로 나가는 글리프를 나열한다(여기서는 하나, `\`). 사후에 디센더를 낮추려면(또는
글리프를 올리려면) 글리프별 dy를 정한다.

    python3 tools/svfdy.py $OUT/c.svf $OUT/c-dy.svf --range 0x67,0x6a,0x70,0x71,0x79 --dy 1    # g j p q y one row lower
    python3 tools/svfdy.py $OUT/c-dy.svf --show

`--dy`는 그리는 시점에 글리프를 옮긴다. 페이스의 dy 범위(헤더 바이트 17/18)가 넓어지고, 줄의 descent는 그만큼 커진다. dy를 지원하지
않는 엔진은 그 글리프를 셀 위치에 그린다.

**함정.** 폰트의 줄 간격보다 작은 셀은 언제나 무언가를 자른다. `--fit-cell`을 쓰거나, advance를 고정한 더 큰 셀을 써라. 페이스의
ascent를 바꾸면 모든 줄의 잉크가 놓이는 곳이 바뀐다(MCU 예제는 줄의 기준선을 그 줄의 맨 윗 행 + 페이스의 ascent에 놓는다).

### TTC와 OTC

<a id="opentype-cff-컬렉션-가변-폰트"></a>

`mkfont.py`는 컬렉션의 인덱스 0을 연다(synthetic: Galmuri9 + Galmuri7의 TTC는 Galmuri9와 똑같이 bake된다). 다른 페이스는 먼저 일반
폰트로 저장해 둔다(maker의 `ttc-face`와 같은 단계. TrueType든 CFF든 페이스에 똑같이 된다. CFF 페이스는 위 OpenType CFF 레시피처럼 출력을 `.otf`로 이름 붙인다).

    python3 maker/srcprep.py ttc-face F.ttc $OUT/F1.ttf --index 1

위치가 아니라 이름으로 고른다. Noto CJK 컬렉션에서 KR은 인덱스 0이 아니다. 이름을 나열한다.

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; [print(i, f['name'].getDebugName(4)) for i, f in enumerate(C('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').fonts)]"

Verified(이 호스트의 Noto Sans CJK Regular 컬렉션): 페이스 열 개, 인덱스 0 Noto Sans CJK JP, 1 KR, 2 SC, 3 TC, 4 HK, 그다음 5-9 Noto Sans Mono CJK JP, KR, SC, TC, HK. 이렇게 얻은 페이스는 일반 정적 폰트처럼 레시피에 들어간다(위의
[OpenType CFF](#opentype-cff-otf)가 바로 이것이다).

### 가변 폰트

`mkfont.py`는 기본 인스턴스를 그린다. 다른 인스턴스는 먼저 정적 인스턴스로 잘라 낸다(fontTools, maker의 `instance` 단계).

    python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o $OUT/Caveat-Bold.ttf
    python3 tools/mkfont.py $OUT/Caveat-Bold.ttf $OUT/CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/mkfont.py ttf/caveat/Caveat-VF.ttf $OUT/CAV24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAVB24.SVF     # one face per call: several faces are a fallback chain
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAV24.SVF

Verified: 기본 인스턴스(Regular 400)는 6,760 바이트로, 700 인스턴스는 7,192 바이트로 bake된다(각각 글리프 95개, "Hamburgefonstiv"의
폭은 Bold 141 px, Regular 136 px. 요약이 뺀 글자 1개는 요청했지만 폰트에 없는 글자이다). 이름 있는 인스턴스는 `fvar` 표에 있다(`Caveat`: Regular,
Bold; `EB Garamond`: Regular .. ExtraBold).

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
있어서 16 px에서는 FreeType이 윤곽선이 아니라 스트라이크를 그린다([내장 비트맵 스트라이크](#내장-비트맵-스트라이크)). 스트라이크가 없는 17 px에서는
윤곽선을 래스터화한다(`125,164 바이트`, 글리프 2,444개: 윤곽선에 없는 코드 포인트 둘은 뺀다, `width=164 ascent=14 descent=3`). maker는 리소스 포크를 곧바로
읽는다. `Seoul[FFIL]`에 `detect.scan`을 쓰면 종류 `outline`, 레이블 "resource fork: sfnt 17408; bitmap strikes 9, 10, 12, 14, 16, 18, 20, 24; Mac Korean cmap",
경로 `mkfont`, `experimental fit`, `vector fit`을 준다. 한글 Mac의 클래식 비트맵 폰트는
[클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트)에 있다.

## 비트맵 폰트

<a id="x-window-한글-폰트"></a>

비트맵 폰트는 두 종류가 서로 다른 경로로 도구에 닿는다. 유니코드 인코딩(`CHARSET_REGISTRY "ISO10646"`, 또는 내장 스트라이크가 있는
TrueType)은 `mkfont.py`와 FreeType을 거치고, KS C 5601 / KS X 1001 인코딩(`ENCODING` = GL 코드, X Window 한글 폰트)은
`bdfface.py`를 거친다.

### ISO 10646 BDF와 PCF

`mkfont.py`는 BDF나 PCF를 Pillow의 FreeType으로 읽되, 파일에 내장된 픽셀 크기(스트라이크)에서만 읽는다. 다른 크기는 `OSError:
invalid pixel size`이며, maker의 `detect.bitmap_strikes`가 폰트가 제공하는 크기를 알려 준다. 이제 shim이나 우회는 없다. `mkfont.py`는
fontTools에 코드 포인트가 cmap에 있는지 묻고, sfnt가 아닌 파일(BDF, PCF, FNT)은 오류가 아니라 알 수 없음으로 취급한다(`cmap_has`가
None을 돌려준다. ec5c6b3부터). 이 저장소에는 BDF나 PCF가 없다. 아래 실행은 이 호스트의 폰트(저장소에 없음)를 쓴다:
`/usr/share/dosbox-x/wqy_12pt.bdf`(WenQuanYi Bitmap Song, 16 px, 유니코드)와 `/usr/share/fonts/X11/misc/18x18ko.pcf.gz`(Misc Fixed
Wide, 18 px).

    python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf $OUT/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-2bpp.svf --size 18 --bpp 2 --unicode ascii,ksx1001-hangul

Verified, shim 없이: BDF `115,684 바이트`, 글리프 2,446개, `width=156 ascent=12 descent=4`, 잉크 348; PCF 1 bpp `116,552 바이트`, 글리프
2,446개(18x18 셀), `width=234 ascent=15 descent=3`, 잉크 366; PCF 2 bpp `181,108 바이트`. 비트맵에는 커버리지가 없으므로 `--bpp 2`의 level은 0과
3뿐이다. 같은 모노크롬 픽셀을 2 bpp로 담을 뿐 부드러운 페이스가 아니다. 이 페이스의 자모 세트는 완성형 결과에 대한 맞춤이다:
`jamoset.py --layout 844 --from-svf $OUT/bdf16-1bpp.svf --mask-font none --check -o ...`(수치는 다음 소절의 bdfface 페이스에 있다).

### KS C 5601 BDF와 PCF

X Window 한글 폰트(`CHARSET_REGISTRY "KSC5601.1987"` 또는 `"KSX1001"`, `ENCODING` = GL 코드: `-baekmuk-*`, `-daewoo-*`, `hanglm16`)는
BDF만 읽는 `bdfface.py`로 간다. PCF는 maker의 `srcprep.py pcf-bdf`(표준 라이브러리만 사용, gz 허용. 외부 `pcf2bdf`가 필요 없다)로 변환하고,
완성형 페이스를 만든 다음 거기에 자모 세트를 맞춘다.

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))" $OUT/ks.txt
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/hanglm16.pcf.gz $OUT/hanglm16.bdf
    python3 tools/bdfface.py --hangul $OUT/hanglm16.bdf --ascii /usr/share/dosbox-x/wqy_12pt.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/KS16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/KS16.SVF --mask-font none --check -o $OUT/KS16J.SVF

Verified: BDF는 `FONTBOUNDINGBOX 16 16 0 -2`, `PIXEL_SIZE 16`, `CHARSET_REGISTRY "KSC5601.1987"`; `bdfface.py`는 `125,096 바이트`,
음절 2,350개(글리프 2,447개: 음절, ASCII 0x20-0x7E, 자체의 U+2026 / U+25A1), 잘린 글리프 7개, `width=156 ascent=14 descent=2`, 잉크 354를
쓴다. 자모 세트는 `18,436 바이트`, 글리프 441개, 조각 344개, 음절 2,350개에 대한 IoU 0.826(p5 0.511)이고 `--check`가 음절 11,172개를
모두 조합하며 잉크 361이다. 유니코드 BDF를 두 절반 모두로 쓴 같은 체인(`--hangul wqy_12pt.bdf --ascii wqy_12pt.bdf`)은 페이스
`115,700 바이트`, 자모 세트 `16,272 바이트`, IoU 1.000이다.

`bdfface.py`는 `--chars-from`이 지정한 한글 음절(임의의 텍스트; `mkfont.py`의 규칙), `--ascii`의 ASCII 0x20-0x7E, 자체의 U+2026 /
U+25A1만 담는다. BDF에서 기호나 자모는 오지 않는다. 셀의 기본값은 BDF의 박스와 상관없이 24x24이므로 `--cell`을 주어라. `--ascent` /
`--hangul-ascent`는 기준선을 정한다. Synthetic(`tools/test_recipes.py`): 음절 10개짜리 KS C 5601 BDF와 ISO 10646 ASCII BDF는 정확히 그
음절만 담은 페이스를 주고 행도 제자리에 있다.

### hanterm

hanterm 폰트(johab-1 인코딩, 글리프 번호는 `ENCODING`, 10x(3|4)x4 세트, 글리프 529개)는 직접 읽는다.

    python3 tools/jamoset.py --layout hanterm-johab johabm16.bdf --check -o $OUT/HTERM16J.SVF

KAIST 명조와 KAIST 고딕, hanterm 3.0.4 폰트 세트의 16 px Johab 폰트(`johabm16.bdf`, `johabg16.bdf`; 각각 글리프 529개,
`CHARSET_REGISTRY "JOHAB-1"`; KAIST; 재배포 조건 명시 없음)로 실행했다.

명조: `13,740 바이트`, 조각 368개, `check: composed 11172 syllables from 368 glyphs, JSET 1303 bytes`, `width=80 ascent=14
descent=2`(샘플 줄의 음절 다섯 개. BDF에 ASCII가 없으니 ASCII는 `--eng`에 원시 8x16 영문 폰트를 준다), 잉크 310. 고딕: `13,180 바이트`,
잉크 214. maker의 `detect.scan`은 둘 다 종류 `bdf-johab`, 레이블 "BDF (johab)", 크기 [16], 경로 `hanterm`을 준다. 같은 세트의 `10-6-6`
폴더(10x6x6 세트)는 다른 레이아웃이라 실행하지 않았다. Synthetic(`tools/test_recipes.py`): 글리프 529개의 hanterm BDF가 음절 11,172개를
10/4/4 세트로 모두 조합한다.

### HBF

`bdfface.py --ascii`는 HBF(옆에 `.bin` 또는 `.bin.gz`가 있는 `.hbf`)를 읽지만 페이스의 ASCII 절반으로만 읽는다. 한글 절반은 BDF여야
한다. ibiblio의 HBF 모음에 있는 X11 Sony 폰트 Sony Fixed 12x24(`12x24.hbf`와 `12x24.bin.gz`; Sony, 고지 조건으로 자유 사용)를 ASCII 절반으로,
Baekmuk 2.0 X11 BDF 세트의 Baekmuk 바탕 24(`batang24.bdf`, KS C 5601)를 한글 절반으로 실행했다.

    python3 tools/bdfface.py --hangul batang24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HBF24.SVF

`206,872 바이트`, 음절 2,350자, ascent 22, step 24, 잘린 글리프 없음, `width=216 ascent=22 descent=2`(24 px 음절 다섯 개와 12 px 문자 일곱 개),
잉크 746. `.hbf` 옆에 `.bin`을 풀어 두면 페이스가 바이트 단위로 같다. maker는 맨 `12x24.hbf`를 경로 없는 종류 `hbf`로 나열하고(HBF는 동반
파일일 뿐이다), 비트맵이 디스크에 `.bin.gz`로만 있는 것은 거부한다(레이블 "HBF: unsafe bitmap reference"). 먼저 `.bin`을 풀어라.
Synthetic(`tools/test_bdfface.py`): 합성 HBF를 ASCII 절반으로.

### Windows FNT와 FON

FreeType에는 winfnt 드라이버가 있어서 `mkfont.py`는 Windows `.FNT`(또는 여러 개를 담은 `.FON`)를 BDF나 PCF처럼 폰트 자신의 픽셀 크기로
열지만, 거기서 그리지는 못한다. 드라이버가 이런 폰트에 `FT_ENCODING_NONE` 맵 하나만 주어서 유니코드가 없고, 모든 코드 포인트가 글리프 0으로
떨어진다. Windows 95 한글판의 시스템 폰트(Microsoft, 독점)로 실행했다: VGAFIX.FON "Fixedsys" 16 px, VGASYS.FON "System" 13 px,
SERIFF.FON "MS Serif" 13 px, 8514FIX.FON.

    python3 tools/mkfont.py VGAFIX.FON $OUT/fon.svf --size 16 --bpp 1 --unicode ascii

는 `--unicode 의 글자가 글꼴에 하나도 없다`로 끝나고, `--unicode ascii,ksx1001-hangul`도 같다. Pillow는 "A", "B", "가"를 똑같은 notdef 글리프
하나로 그린다. maker는 이들을 감지하므로(`detect.scan`: 종류 `bitmap`, 레이블 "Windows FON face 0", 크기 [16] 또는 [13], 경로 `mkfont`. 뒤쪽 페이스는
`other`, "face index 1: not convertible in v1". MODERN.FON은 "no openable face") 제공하는 경로가 이 파일들에서는 실패한다. 한글 글리프가 있는
Windows FNT나 FON은 찾지 못했다. Windows 95 한글판 디스크에는 라틴과 OEM 폰트(Fixedsys, System, Terminal, MS Serif, MS Sans Serif, Courier,
Small Fonts; FON 25개)뿐이고, 그 시스템의 한글 글리프는 TrueType이다(`gulim.ttc`, 스트라이크 포함: [내장 비트맵 스트라이크](#내장-비트맵-스트라이크)).
FON은 외부 도구로 먼저 BDF로 변환해야 하며, 이 저장소에는 그런 도구가 없다.

자모 조각 폰트인 DOS Johab `.FNT` 파일과 혼동하지 말 것: [DOS 시대 원시 폰트](#dos-시대-원시-폰트)를 참고한다.

### 내장 비트맵 스트라이크

내장 비트맵이 있는 아웃라인 폰트(TrueType `bdat`/`bloc`, OpenType `EBDT`/`EBLC`)는 FreeType이 스트라이크 자신의 픽셀 크기에서만 쓴다.
스트라이크의 크기로 `mkfont.py --size N`과 `--bpp 1`을 실행한다. 다른 크기에서는 윤곽선을 쓰고, 비트맵 전용 폰트는 열기가 실패한다
(`OSError: invalid pixel size`). maker의 `detect.bitmap_strikes`가 폰트의 스트라이크를 나열해 크기로 제공한다. 실제 폰트 두 개로 실행했다.

*Seoul*, Mac OS 7.6.1 한글판 CD의 폰트(`Font Folder/Seoul[FFIL]`, Apple Korea / Elex, 독점; 스트라이크 9, 10, 12, 14, 16, 18, 20, 24 ppem,
[Mac 형식 TrueType](#mac-형식-truetype) 참고): `macsfnt.py extract`와 `unicode` 뒤에 `mkfont.py --size 16 --bpp 1
--unicode ascii,ksx1001-hangul`은 스트라이크의 픽셀을 쓴다(`124,868 바이트`, 잉크 346). `--size 17`에서는 윤곽선을 그린다.
같은 CD에 있는 같은 패밀리의 비트맵 전용 사본(`CD Extras/Bitmap 서체 설치/Seoul/Seoul[FFIL]`, 2,626,404 바이트, `bdat` + `bloc` + `bhed`,
`glyf` 없음, maker 종류 `bitmap`, 크기 [9, 10, 12, 14, 16, 18, 20, 24])는 16 px, 12 px(`105,972 바이트`), 24 px(`219,116 바이트`)에서 같은 글리프 바이트를
주고, `--size 17`은 `폰트를 17px 로 열 수 없다: invalid pixel size`로 멈춘다. 그러나 메트릭은 잃는다. `head`가 없어(대신 Apple의 `bhed`)
`mkfont.py`가 모든 글리프의 advance를 0으로 쓰고, `svfline.py measure`는 `width=0`을, `fontmetrics.py`는 2,446개 중 2,445개가 advance를 넘어선다고
알린다. 스트라이크는 비트맵 전용 사본이 아니라 전체 폰트에서 구워라.

*굴림*(Gulim), Windows의 폰트(`GULIM.TTC`, Microsoft와 한양정보통신, 독점; `EBLC` 스트라이크 11~25 ppem):

    python3 maker/srcprep.py ttc-face GULIM.TTC $OUT/Gulim.ttf --index 0
    python3 tools/mkfont.py $OUT/Gulim.ttf $OUT/gu16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

16 px `125,288 바이트`, 글리프 2,446개, `width=149 ascent=14 descent=2`, 잉크 371. 12 px `106,208 바이트`, `width=114 ascent=10
descent=2`, 잉크 298. `svf2to3.py --profile default --check`는 두 크기 모두 그대로 둔다. 스트라이크가 없는 크기(26)는 윤곽선을 래스터화하고
(`202,144 바이트`), `--bpp 2`는 스트라이크 크기에서도 윤곽선을 쓰므로(16 px: `182,604 바이트`) `--bpp 1`만 스트라이크의 픽셀을 준다. 추출한 폰트에
`detect.scan`을 쓰면 종류 `outline-composite`, 레이블 "TTF; bitmap strikes 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25", 크기 [16], 경로 `mkfont`,
`composite`, `vector fit`을 준다.

## DOS 시대 원시 폰트

DOS 한글 시스템(한글 BIOS, 이야기, 한메, san, 도깨비, 게임)은 음절이 아니라 자모 조각을 저장했다. 음절은 초성, 중성, 선택적인
종성의 OR이었고, 어느 세트를 쓸지는 다른 자모가 정했다. 도구는 이 원시 파일을 **정확한 바이트 크기**로(maker의 `detect.py`도
마찬가지이며, 목록에 없는 크기의 파일은 "unknown"이다) 그리고 레이아웃으로 읽는다. 냄새로 알아볼 헤더는 없다.

### 그 밖의 DOS 시대 한글 폰트

| `--layout` | 파일 | 바이트 | 조각 |
|---|---|---|---|
| `844` | 원시 8x4x4 (`HANGUL.FNT`, `*.KOR`, `$K*ZN16`), 16/24/40/48 px | 11,520 (2 바이트 헤더가 있으면 11,522), 25,920, 72,000, 103,680; 15,584 (DKB2, 16 px로 읽음) | 360: 초성 세트 8개(각 20), 중성 4개(각 22), 종성 4개(각 28); 각 세트의 슬롯 0은 빈 칸 |
| `844-ihnm` | SAGA IHNM 8x4x4 (중성 세트가 ㄱ ㅋ에 맞게 바뀜) | 11,520+ | 360 |
| `844-hbios24` | HBIOS / 태백 3.5 24x30 (`GOTHIC24.FNT`, `MY24.FNT`) | 243,900 | 처음 360개 |
| `1044-san` | san 1.0 10x4x4 | 12,800 | 400 |
| `621` | 6x2x1 (Apple II 시대), 바이트 열 글리프 | 6,144 | 192 |
| `dkb-printer-7x2x2` / `dkb-printer-12x4x4` | 도깨비 프린터 `HANGUL16/24.FNT` / `HANGUL40/48.FNT` (`--face 0|1`) | 15,360 / 34,560; 176,000 / 253,440 | 페이스당 240 / 440 |
| `kyra-lok` | Kyra LoK `MK15.BIT`, 15x15 | 11,550 | 385 |

    python3 tools/jamoset.py --layout 844 HANGUL.FNT --eng ENGLISH.FNT --symbols --check -o $OUT/MYFONT16J.SVF
    python3 tools/johab844.py HANGUL.FNT svf/dos/NEODG16.SVF $OUT/MYFONT16.SVF --eng ENGLISH.FNT     # precomposed instead

`--eng`는 ASCII용 원시 8x16 영문 폰트(2,048 또는 4,096 바이트; 셀에 맞게 정수배로 확대)를 받는다. `--base FACE.SVF`는 다른
페이스의 음절 아닌 글리프를 유지한다. ascent의 기본값은 셀의 7/8이다(`--ascent N`). 8x16 DOS 폰트는 기준선을 13행 또는 14행에
둔다. `--check`는 음절 11,172개를 모두 조합한다. `johab844.py`는 16x16 1 bpp 베이스의 음절을 원시 조각으로 다시 그리고 베이스의
나머지 글리프는 유지한다. Synthetic(`tools/test_recipes.py`에서 만든 합성 파일): 8x16 영문 폰트가 딸린 원시 8x4x4 폰트(가를
조합한 결과 = 원시 슬롯 1과 161의 OR, 바이트 단위로 동일), 6x2x1 폰트(초성 클래스 1개 / 종성 클래스 2개, 세트 6/2/1), 완성형
페이스의 재맞춤(NEODG16J에 `--from-svf`, IoU 1.000).

실제 폰트로 실행(2026-11-22. 모든 줄에 `--symbols --check`, 이름이 있는 곳에는 `--eng`. 샘플 줄은 `안녕하세요 ABC 123`, "잉크"는 렌더 점검의 수.
`--eng`를 줄 때만 ASCII가 그려지므로 주지 않은 페이스는 음절 다섯 개를 잰다):

| `--layout` | 원본(폰트, 제품; 따로 적지 않으면 독점) | 결과 |
|---|---|---|
| `844` | GOTHIC16.FNT, 11,520 바이트(태백 3.5.1 고딕 16), 같은 패키지의 `--eng ROMAN16.FNT` | `15,756 바이트`, 조각 344개, 글리프 441개, `johab844.py`의 음절과 동일. `width=144 ascent=14 descent=2`, 잉크 566 |
| `844` | TBG1.FNT, 2 바이트 헤더가 붙은 11,522 바이트(T-Hangul, 초기 태백), `--eng ROMAN16.FNT` | `15,712 바이트`, 같은 조각 344개, 잉크 566 |
| `844` | DKBBM.FNT, 15,584 바이트(한글 도깨비 B 명조), `--eng ROMAN16.FNT` | `15,744 바이트`, 글리프 441개, `johab844.py`와 동일. 잉크 512 |
| `844` | MHANC24.PFT, 25,920 바이트(태백 3.5.1 명조 24 px), `--eng MASCII24.PFT`(12,288 바이트, 12x24 영문 폰트) | `23,088 바이트`, 조각 344개. `width=216 ascent=20 descent=4`, 잉크 916 |
| `844` | GHANC40.PFT, 72,000 바이트(태백 3.5.1 고딕 40 px), `--eng` 없음 | `34,040 바이트`, 글리프 346개. `width=200 ascent=35 descent=5`, 잉크 1,751 |
| `844` | MHANC48.PFT, 103,680 바이트(태백 3.5.1 명조 48 px), `--eng` 없음 | `42,020 바이트`. `width=240 ascent=42 descent=6`, 잉크 1,865 |
| `844-hbios24` | GOTHIC24.FNT, 243,900 바이트(태백 3.5.1, HBIOS 24x30 레이아웃) | `17,776 바이트`, 글리프 346개. `width=120 ascent=21 descent=3`, 잉크 551 |
| `844-hbios24` | MY24.FNT, 243,900 바이트(태백 3.5.1 명조 24), `--eng GASCII24.PFT` | `23,136 바이트`. `width=216 ascent=20 descent=4`, 잉크 964 |
| `1044-san` | HANPL.KOR, 12,800 바이트(san 1.0의 `font-kor/`. GitHub의 san 프로젝트) | `13,988 바이트`, 조각 382개, 글리프 384개. `width=80 ascent=14 descent=2`, 잉크 328 |
| `621` | han_woori.fnt, 6,144 바이트("우리", GitHub의 iolo 6x2x1-fonts, Apple II 시대) | `6,584 바이트`, 조각 183개, 글리프 185개. 잉크 204 |
| `dkb-printer-7x2x2` | HANGUL16.FNT 15,360 바이트와 HANGUL24.FNT 34,560 바이트(한글 도깨비 5.1 프린터 폰트), `--face 0` / `--face 1` | 16 px `8,928` / `8,868 바이트`, 조각 229개, 잉크 367 / 363. 24 px `12,068` / `11,872 바이트`, 잉크 542 / 537 |
| `dkb-printer-12x4x4` | HANGUL40.FNT 176,000 바이트와 HANGUL48.FNT 253,440 바이트(같은 제품), `--face 0` / `--face 1` | 40 px `38,704` / `38,624 바이트`, 조각 420개(글리프 422개), 잉크 1,595 / 1,766. 48 px `52,932` / `48,908 바이트`, 잉크 2,472 / 2,538 |
| `kyra-lok` | MK15.BIT, 11,550 바이트(The Legend of Kyrandia 한글판) | `14,036 바이트`, 조각 382개, 15x15. `width=80 ascent=13 descent=2`, 잉크 344 |
| `844-ihnm` | 없음: SAGA IHNM 데이터를 찾지 못했다 | 실행하지 않음 |

모든 페이스가 음절 11,172개를 조합한다(`--check`). 조각 수는 쓰인 조각의 수로, 안 쓰는 슬롯을 버리므로 표의 조각 수보다 적다. 같은
GOTHIC16.FNT에 `johab844.py`(`--eng ROMAN16.FNT`, 베이스 `svf/dos/NEODG16.SVF`)를 쓰면 `133,688 바이트`, 원시 폰트의 음절 2,357자,
ROMAN16.FNT의 ASCII 글리프 94개, 베이스의 다른 글리프 454개, `width=144 ascent=12 descent=4`, 잉크 566이고 `svf2to3.py --check`는 크기를
유지한다. 이 파일들의 사본에 maker의 `detect.scan`을 쓰면 모두 종류 `dos-raw`, 크기 16 / 24 / 40 / 48 / 15, 경로 `dos raw`를 얻는다.
GOTHIC16.FNT(레이블 "844, 844-ihnm". 두 레이아웃의 크기가 같다)는 `johab844`도 얻고, 11,522 바이트의 TBG1.FNT와 15,584 바이트의 DKBBM.FNT는 `dos raw`만
얻는다. 도깨비 프린터 파일은 페이스마다 항목 하나를 주고, GASCII24.PFT / MASCII24.PFT와 ROMAN16.FNT는 "Latin companion"으로 나열된다.

**함정.** 크기가 맞는 파일이 다른 레이아웃이어도 크기 점검은 통과한다. 슬롯 0의 채움 조각이 비어 있지 않으면 `jamoset.py`가
거부하지만, 결과를 직접 보라(`svfline.py line ... "가나다"`). 2 바이트 헤더가 있는 폰트(T-Hangul)는 오프셋 2에서 읽는다. 24 px
이상의 원본에는 거기에 맞는 영문 폰트나 `--base`가 필요하다. 위의 40, 48 px 줄에 ASCII가 없는 이유는 `--eng`가 8x16과 12x24 폰트만 받고 같은 패키지의
40 / 48 px 영문 폰트(GASCII40.PFT, 30,720 바이트)는 받지 않기 때문이다.

### HWP 1.x와 2.x 폰트

한글과컴퓨터의 DOS 워드프로세서는 프린터 폰트와 화면 폰트(`HANGUL*.PFT`, `ASCII.PFT`, `*.FNT`)를 실었다. 이 저장소가 직접 읽는
것은 다음과 같다.

- 12x24 영문 폰트: `jamoset.py ... --eng GASCII24.PFT` 또는 `MASCII24.PFT`(태백 3.5.1. 12,288 바이트, 48 바이트짜리 글리프 256개. 위 표에서
  썼다)와 HBIOS 12x24(15,360 바이트). HWP 1.20 자신의 `ASCII.PFT`는 다른 파일이며(41,654 바이트: 32 바이트 "HWP Font Editor v1.0" 헤더와 14x24
  글리프 991개, 각 42 바이트, 열 우선) 거부된다: `an English font has 2048 or 4096 bytes (8x16), 15360 (HBIOS 12x24) or 12288 (PFT 12x24), not 41654`;
- 평범한 원시 8x4x4인 HWP 2.x 화면 폰트: 한글 2.1 PRO 디스크(13번)의 `HMJ.FNT`(11,520 바이트)는 다른 `844` 폰트처럼 읽힌다.
  `python3 tools/jamoset.py --layout 844 HMJ.FNT --eng ROMAN16.FNT --check -o $OUT/HMJ.SVF`는 `15,700 바이트`를 쓰고 음절 11,172개를 모두 조합하며
  `johab844.py`와 동일하다;
- 직접 만든, 한글을 완성형으로 만든 1 bpp 페이스를 조각으로 다시 맞추기: `jamoset.py --layout 844 --from-svf FACE.SVF --mask-font none --check`;
- 조합된 음절의 BDF: `bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf --cell 24x24 --chars-from LIST`.

DOS용 HWP 1.20(한글과컴퓨터, 1989-1990; `HANGUL1.PFT`, 70,592 바이트, 24x24 페이스 셋(세트는 7/2/3, 7/2/2, 5/2/2), 글리프당 72 바이트, 열 우선;
독점)의 페이스 1(메뉴 순서로 고딕)로 실행했다. johab-fonts 노트의 연구 도구 `hwp1_fnt.py`가 음절을 조합하고, 30줄짜리 스크립트가 그 KS X 1001
음절 2,350자와 `ASCII.PFT`를 BDF 둘로 썼다(`ENCODING` = GL 코드; 24x24와 14x24). 그다음

    python3 tools/bdfface.py --hangul hwp-gothic.bdf --ascii hwp-ascii.bdf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HWP24.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/HWP24.SVF --mask-font none --check -o $OUT/HWP24J.SVF

`218,848 바이트`, 음절 2,350자, `width=232 ascent=21 descent=3`, 잉크 886. 자모 세트는 `24,264 바이트`, 조각 344개, 음절 2,350자에 대한 IoU 1.000
(모두 정확), 잉크 886: HWP 규칙이 모든 음절을 조각 셋으로 조합하므로 이 24 px 페이스들에서는 맞춤이 정확하다.

읽지 **않는** 것: HWP의 `.PFT` 한글 파일 자체. `python3 tools/jamoset.py --layout 844 HANGUL1.PFT -o $OUT/rejected.SVF`는 `size 70592 is not an 8x4x4 size`로 멈춘다(종료 코드 1). 그 글리프는
HWP 자체의 규칙으로 조합되며, 별도의 연구 도구(johab-fonts 연구 노트의 `hwp1_fnt.py`와 `kfont.py`)가 이를 해독한다. 그 리더는 이 저장소에
속하지 않으며, 그 출력(BDF 또는 완성형 페이스)이 위 경로들의 입력이다. maker의 `detect.scan`은 이 파일을 종류 `other`, 레이블 "unknown"으로 준다.

### KS X 1001 원시 덤프

KS X 1001 완성형 음절 2,350자의 원시 덤프(코드 순서로 음절마다 비트맵 하나. 일부 DOS와 임베디드 시스템이 이렇게 보관한다)는 이 저장소에
리더가 없다. `jamoset.py`, `bdfface.py`, maker 어디에도 이를 위한 레이아웃이 없고, 그런 크기의 파일은 알아보지 못한다. 태백 3.5.1의
`GHAN24.PFT`(고딕 24 px; 169,200 바이트 = 2,350 x 72, 헤더 없음, 한 줄이 3 바이트인 24x24 행 우선, KS 순서로 가부터)로 실행: `python3 tools/jamoset.py --layout 844
GHAN24.PFT -o $OUT/rejected.SVF`는 `size 169200 is not an 8x4x4 size`로 멈추고(종료 코드 1), maker의 `detect.scan`은 `other`, "unknown"이라 부른다. 다른 곳에서 BDF(KS C 5601
인코딩, `ENCODING` = GL 코드)로 변환한 뒤 [KS C 5601 BDF와 PCF](#ks-c-5601-bdf와-pcf)를 쓴다. 여기서는 15줄짜리 스크립트(행 `0x30 + i // 94`,
열 `0x21 + i % 94`, 글리프의 각 줄을 16진수로)로 변환하고 ASCII는 Sony Fixed 12x24로 했다.

    python3 tools/bdfface.py --hangul ghan24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/GHAN24.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/GHAN24.SVF --mask-font none --check -o $OUT/GHAN24J.SVF

페이스는 `216,448 바이트`, 음절 2,350자, `width=216 ascent=22 descent=2`, 잉크 1,074. 자모 세트는 `33,684 바이트`, 조각 344개, 음절 2,350자에 대한 IoU
0.710(페이스가 조각의 OR이 아니라 음절 통째의 디자인이라 맞춤이 나쁘다)이다.

## 클래식 Mac 한글 비트맵 폰트

Apple의 데이터는 이 저장소에 없다. 도구는 직접 마련한 파일을 읽는다. maker의 로컬 모드(`maker/README.ko.md`, "로컬 모드 (데스크톱 앱)")는 이
폰트를 디스크의 제자리에서 같은 도구로 읽고, 페이스는 고른 폴더에만 쓴다.

**HangulTalk 1.0 'fbit' 폰트** (한글 System 4.1: Gotic12/16, Munjo12/16/24). 입력: 폰트의 리소스 포크를 파일로 한 것(Mac 볼륨에서
복사했거나 아카이브의 포크; `tools/macsfnt.py list`가 그 'fbit' 리소스를 보여 준다). 포크에는 글리프 세트 45개의 'fbit' 리소스와
18개의 조회 표를 가진 'fdef' 드라이버 리소스가 있다. 세트 체계는 폰트 자신의 규칙에서 유도하므로, 모든 음절이 Mac이 그리는 대로
조합된다.

    python3 tools/jamoset.py --layout mac-fbit-45sets Munjo24.rsrc --symbols --check -o $OUT/MUNJO24J.SVF

출력: 음절 11,172개 전체의 1 bpp 자모 세트(이 폰트들은 초성 클래스 8개, 종성 클래스 4개, 초성 세트 20개), 셀 = 폰트의 크기.
`--check`는 모든 것을 조합해 jamoset 자체의 'fdef' 규칙 사본과 비교한다. 직접 만들면 골든 파일(`tools/testdata/mac-fbit-golden.json`,
배포하지 않음: Apple 비트맵이 들어가기 때문)이 독립적인 비교를 더한다. 실제 파일에 대한 테스트는 `JOHAB_FONTS`가
`mac/extracted/kh10_system_disk/System Folder/*.rsrc`와 참조 렌더러를 담은 트리를 가리킬 때 실행되고, 아니면 건너뛴다.

한글 시스템 4.1 / HangulTalk 1.0(1988년 1월, Apple Korea / Elex Computer; 독점)의 시스템 디스크로 실행했다. `System Folder`에 네 폰트가 리소스 포크
파일로 있다. `Munjo24`(24 px 문조. `list`는 `fbit` 17409, 47,714 바이트와 그 `fdef` 3, 2,398 바이트를 보여 준다): `36,660 바이트`, 24x24 조각 653개,
초성 클래스 8개 x 종성 클래스 4개, 세트 20/15/4, `check: composed 11172 syllables from 655 glyphs`, 그리고 jamoset 자체의 `fdef` 규칙 사본에 대한 자기
일관성 줄 `IoU 1.000, exact 11172`(골든 파일 없음), 1.0초. 샘플 줄은 `width=120 ascent=24 descent=0`(이 폰트들에는 라틴이 없어 음절 다섯 개만
그려진다), 잉크 591. `Gotic12`(12 px 고딕): `23,368 바이트`, 같은 세트, `width=60 ascent=12 descent=0`. maker는 이 폰트들을 1.0이 아니라
"HangulTalk 7.1 type-3 fbit, 24 px, 661 planes (needs HTBL 1)"로 읽는다. 실제 1.0 `fbit` 헤더가 7.1 폰트처럼 세대 3을 담고 있는데 `detect.py`가
45 세트보다 세대를 먼저 검사하기 때문이다(그 테스트는 세대 0으로 1.0 폰트를 만든다). 위 명령은 이 폰트들에 맞지만 실제 폰트에는 `mac fbit 1.0`
경로가 제공되지 않는다.

**HangulTalk 7.1.x type-3 'fbit' 폰트** (Seoul12, AppleGothic12/24, AppleMyungjo12/24): 평면은 표, InputBackSupport 'HTBL' 1로
조합되며, KS X 1001 음절 2,350자와 호환 자모 51개만 있다.

    python3 maker/srcprep.py mac-htbl "InputBackSupport[INIT].rsrc" $OUT/HTBL1.bin     # the HTBL 1 of the extension (7.1.2 CD), 9,816 bytes
    python3 tools/macfbit3.py unpack Seoul12.splt.data $OUT/Seoul12.rsrc     # the 7.1.2 Installer's 'splt' "JM" archive
    python3 tools/macfbit3.py fbit $OUT/Seoul12.rsrc $OUT/Seoul12.fbit
    python3 tools/macfbit3.py bdf $OUT/Seoul12.fbit $OUT/HTBL1.bin Seoul12 $OUT/seoul12.bdf          # 2,401 glyphs, Unicode BDF
    python3 tools/macfbit_svf.py build $OUT/Seoul12.fbit $OUT/HTBL1.bin -o $OUT/SEOUL12J.SVF         # direct: the Mac structure (JMAP)
    python3 tools/macfbit_svf.py build $OUT/Seoul12.fbit $OUT/HTBL1.bin --mode derived -o $OUT/SEOUL12D.SVF   # a JSET face, all 11,172
    python3 tools/macfbit_svf.py verify $OUT/SEOUL12J.SVF $OUT/Seoul12.fbit $OUT/HTBL1.bin

`direct`는 Mac 평면을 조각으로 유지하고 KS 음절만 정확히 조합한다. `derived`는 JSET을 맞추는데, 그 JSET의 추가 음절 8,822개는
외삽한 것이다(Mac 출력이 아님). BDF 경로는 `bdfface.py --cell 12x12 --chars-from <the 2,350 syllables>`로 이어져 완성형
페이스가 된다. 변형이 많은 페이스를 MCU 예산에 맞게 줄이려면:

    python3 tools/jamomerge.py merge --face $OUT/SEOUL12D.SVF --points 8192 7168 --prefix SM -o $OUT/SMALL

(모든 조각을 그려진 그대로 유지하고, 픽셀 목적 함수로 변형, 세트, 클래스를 병합한다). 테스트: `tools/test_macfbit3.py`와
`tools/test_macfbit_svf.py`는 테스트 안에서 만든 합성 fbit / HTBL / NFNT 데이터로 실행된다. `MACFBIT3_CD712=<CD tree>`와
`SVF_MAC71_INPUTS=<dir of Name.fbit and Name.htbl1>`은 직접 가진 파일에 대한 점검을 더한다. 윤곽선 Mac TrueType 폰트는
[Mac 형식 TrueType](#mac-형식-truetype)을 참고한다. 이 폰트들에 대한 maker의 경로는 [경로 표](#데스크톱-앱과-maker-경로)에 있다.

한글 시스템 7.1.2 / HangulTalk 7.1.2(Apple Korea / Elex Computer; 독점)의 Seoul12로 실행했다. CD의 `More Additions` 폴더에 있는
`Seoul12[splt]`(HangulTalk 7.5.1 설치 디스크의 `Seoul12[fbit]` 포크도 같은 8,760 바이트 `fbit`를 주며 `cmp`로 동일하다)와, 그 CD의
`InputBackSupport` 확장의 HTBL 1이다. HTBL은 위 명령이 보여 주지 않았던 단계로, 이제 위 블록의 첫 줄이다(`srcprep.py mac-htbl`, 9,816 바이트). 확장의 7.5.1 사본은 압축되어 있어 `srcprep.py`가 "not an HTBL 1
table"이라고 답한다. 이 `$OUT/HTBL1.bin`으로 위 명령은 적힌 그대로 돈다. `unpack`은 `JM 1843 -> 9673 bytes`, `fbit`는 8,760 바이트, `bdf`는 글리프 2,401개. `direct`는 `15,016 바이트`,
조각 207개, `verify`는 ks_bad 0, compat_bad 0, non_ks_present 0. `derived`는 `9,716 바이트`, 조각 219개, 8 x 4 클래스, 세트 9/6/3(JSET v2로는 `7,928 바이트`),
모든 음절 검증. 둘 다 샘플 줄의 음절 다섯 개를 `width=60 ascent=10 descent=2`, 잉크 142로 그린다. BDF 경로(`macfbit3.py bdf`, 그다음 `srcprep.py bdf-pixel-size
seoul12.bdf seoul12-sized.bdf --size 12`, 그다음 `mkfont.py ... --size 12 --bpp 1 --unicode ascii,ksx1001-hangul`과 정규 단계)는 `103,012 바이트`,
글리프 2,350개, 같은 `width=60 ascent=10 descent=2`, 잉크 142를 준다. 라틴 글자를 패밀리 suitcase로 넣으면(`--latin "Seoul[FFIL].rsrc"`: 같은 CD의 `FOND`와
9, 12 pt `NFNT` 스트라이크 둘) `direct`는 `17,924 바이트`(라틴 1,388), `derived`는 `12,624 바이트`이고 둘 다 `width=111 ascent=10 descent=2`, 잉크 253,
`verify` 이상 없음. `jamomerge.py merge --points 8192 7168`(약 2분)은 `SM8K.SVF` `7,964 바이트`와 `SM7K.SVF` `7,032 바이트`(조각 191개, 세트 7/6/3)를
쓰고 검증된다. maker의 로컬 모드가 파일을 읽는다(`detect.scan(..., local=True)`): `Seoul12` 포크, `splt` 파일, 원시 포크는 "HangulTalk 7.1 type-3 fbit, 12 px,
482 planes (needs HTBL 1)"이고 경로 `mac fbit 7.1 direct`, `derived`, `bdf + mkfont`를 얻는다. 확장은 "HangulTalk 7.1 HTBL 1 (InputBackSupport): the
composition table", `Seoul[FFIL]`은 "Mac bitmap suitcase (FOND + NFNT): Latin strikes at 9, 12 pt"이다.

## 기존 SVF

원본: `svf/dos/NEODG16.SVF`(완성형 1 bpp 페이스, 16x16, 글리프 2,905개, 메트릭 표 있음).

dy 설정(다른 바이트는 바뀌지 않음):

    python3 tools/svfdy.py svf/dos/NEODG16.SVF $OUT/neodg16-dy.svf --range 0x20-0x7e --dy 3

Verified: `133,720 바이트`(변함 없음), 글리프 2,905개, 글리프 95개에 dy 설정, 범위 0..3. 렌더는 `width=144 ascent=12 descent=7`
(descent가 dy만큼 커졌다), 잉크 559.

자모 세트로 다시 bake(1 bpp 페이스의 완성형 음절에 대한 맞춤. 조각과 페이스의 나머지 글리프는 유지된다):

    python3 tools/jamoset.py --layout 844 --from-svf svf/dos/NEODG16.SVF --mask-font none -o $OUT/neodg16-from-svf.svf

Verified: `34,332 바이트`, 글리프 892개, 조각 344개. 맞춤: 음절 2,357개, IoU 1.000(Neo Dunggeunmo는 그 자체가 조각의 OR이다). 렌더는
`width=144 ascent=12 descent=4`, 잉크 559. 기존 SVF는 안티에일리어싱 원본이 아니다. 1 bpp 페이스를 2 bpp로 바꾸는 도구는 없고,
`svfdy.py`는 dy만 바꾼다.

**버전과 프로필.** SVFN v2는 폐기되었다. `svf2to3.py`는 v2를 읽고 v3 페이스를 다시 배치한다. maker의 "copy" 경로는 업로드된 SVF에 이를 쓴다
(`svf2to3.py SRC OUT --jset-version V --check`: v2 페이스를 v3로 담거나, JSET 블록을 다시 쓴 v3 페이스). 자모 세트는 표를 JSET v1(기본)
또는 v2(메모리가 제한된 대상에서 더 작다)로 담는다. `--jset-version auto`는 v1 블록이 1,024 바이트 이상 크면 v2를 고른다. JMAP 블록(JSET
버전 3)은 그대로 복사되며 그 경우 이 플래그는 아무 일도 하지 않는다.

    python3 tools/svf2to3.py $OUT/NG16J.SVF $OUT/NG16J-v2.SVF --jset-version 2 --check
    python3 tools/svf2to3.py svf/dos/NEODG16A.SVF $OUT/NEODG16A-v2.SVF --jset-version 2 --check
    python3 tools/svf2to3.py svf/dos/NEODG16.SVF $OUT/NEODG16-canon.SVF --profile default --check

Verified: NanumGothic Bold의 1 bpp 자모 세트는 `--jset-version 2`로 `20,064` -> `19,232 바이트`(JSET 블록 1,101 -> 272 바이트, 글리프 데이터 11,884 변함 없음, 모든 글리프 비교 일치); 배포된 NEODG16A는 `16,408` -> `15,576 바이트`; `--jset-version auto`에서 NEODG16A는 v1로 남는다(`jset=1`. v1 블록이 v2보다 829 바이트만 커서 1,024 기준에 못 미친다). 마지막 명령은 배포된 페이스를 `default` 프로필로 다시 배치하며 바이트가 같다: 입출력 모두 133,720 바이트(`cmp`가 차이를 보고하지 않는다). `--profile`은 대상별 레이아웃을
고른다(`mcu-strict`, `default`, `dos`, `wasm`, `full`, `simd16`). `--check`는 픽셀이 바뀌지 않았음을 증명한다.

## 데스크톱 앱과 maker 경로

maker(`maker/`, [desktop-app.md](desktop-app.ko.md)의 데스크톱 앱, [maker/README.md](../maker/README.ko.md)의 서버)는 각 파일의 종류를
감지하고(`maker/detect.py`) 그 종류에 `maker/routes.py`의 경로를 제공한다. 모든 경로는 위 도구들로 이루어진 명령줄이다. 실행하면 출력
폴더에 `svf/<dest>/<NAME>.SVF`와 `build-<id>/BUILD.md`가 쓰인다. BUILD.md는 페이스마다 원본 단계와 실행한 명령을 실제 경로와 함께
나열하므로, 어떤 결과든 이 장으로 손수 재현할 수 있다. 페이지에 보이는 레이블별 경로는 다음과 같다(`native` = 원본이 경로가 만드는
것과 정확히 같음. 나머지는 맞춤이며 experimental로 표시된다):

| 경로 (종류, 레이블) | 원본 종류 | 명령 (`routes.py`의 argv) | 레시피 |
|---|---|---|---|
| 완성형, `mkfont` | outline, outline-composite, bitmap, bdf-iso10646 | `mkfont.py SRC mkfont.tmp --size S --bpp B --unicode R` 다음 `svf2to3.py mkfont.tmp OUT --profile default`(비트맵: 스트라이크 크기에서 1 bpp) | [완성형 페이스](#완성형-페이스-mkfontpy), [ISO 10646 BDF와 PCF](#iso-10646-bdf와-pcf) |
| 자모, `composite` | outline-composite(음절이 합성인 TrueType) | `jamovec.py master SRC -o M.json --components [--adaptive]` 다음 `jamovec.py render M.json --size S --bpp B --binarize threshold --check -o OUT` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 1: 합성 글리프](#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `experimental fit` | outline(합성 아님) | 1 bpp: `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --check -o OUT [--eng E] --mask-font none`; 2 bpp: `jamoset.py ... --bpp 2 --check -o OUT` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 3: 완성형 음절에 맞추기](#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `mask fit` | GSUB 자모와 쓸 수 있는 마스크가 있는 outline 또는 outline-composite(1 bpp) | `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --mask-font SRC --no-clean --check -o OUT [--pylib DIR]` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 2: 결합 자모 shaping](#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `vector fit` | outline, outline-composite | `jamovec.py master SRC -o M.json [--adaptive]`(`--components` 없음) 다음 같은 `render` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 3: 완성형 음절에 맞추기](#truetype와-opentype-폰트에서-만드는-자모-세트) (`--components` 없는 `jamovec.py master`) |
| 완성형, `johab844` | dos-raw, 정확히 11,520 바이트(16 px 8x4x4) | `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng E]`(maker는 베이스를 `svf/` 아래에서 찾는다) | [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트) |
| 자모, `dos raw` | dos-raw | `jamoset.py SRC --layout L --check -o OUT [--eng E] [--face 0\|1]`(`--face`는 도깨비 프린터 레이아웃용) | [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트) |
| 자모, `hanterm` | bdf-johab | `jamoset.py SRC --layout hanterm-johab --check -o OUT [--eng E]` | [hanterm](#hanterm) |
| 완성형, `bdfface` | bdf-ksc5601(BDF, 또는 `pcf-bdf` 단계를 거친 PCF) | `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST -o OUT`(`WxH` = BDF의 박스) | [KS C 5601 BDF와 PCF](#ks-c-5601-bdf와-pcf) |
| 자모, `bdfface + from-svf fit` | bdf-ksc5601 | `bdfface.py` 페이스 다음 `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS C 5601 BDF와 PCF](#ks-c-5601-bdf와-pcf) |
| 자모, `mac fbit 1.0` | mac-fbit1 | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| 자모, `mac fbit 7.1 direct` / `derived` | mac-fbit3 + HTBL 1 | `macfbit_svf.py build FBIT HTBL -o OUT --mode direct\|derived [--latin SUITCASE]` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| 완성형, `mac fbit 7.1 bdf + mkfont` | mac-fbit3 + HTBL 1 | `macfbit3.py bdf FBIT HTBL NAME mac.bdf`, `srcprep.py bdf-pixel-size mac.bdf mac-sized.bdf --size S`, `mkfont.py mac-sized.bdf mkfont.tmp --size S --bpp 1 --unicode ...`, `svf2to3.py ... --profile default` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| 완성형 또는 자모, `copy` | svf-precomposed, svf-jamo | 업로드된 그대로 쓰면 없음. v2 페이스나 요청한 JSET 변경에는 `svf2to3.py SRC OUT --jset-version V --check` | [기존 SVF](#기존-svf) |
| 자모, `from-svf fit` | svf-precomposed, 1 bpp | `[svf2to3.py ... source-v3.svf]` 다음 `jamoset.py --layout L --from-svf SRC --check -o OUT [--eng E]` | [기존 SVF](#기존-svf) |

`L`은 맞춤에서는 `844` 또는 `adaptive`이고, 그 밖에는 원본 종류가 지명하는 레이아웃이다. `[--eng E]`는 페이지가 폰트와 짝지은 영문
동반 폰트이다.

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

Verified: 이 표의 경로 레이블과 종류는 `routes.py`에서 읽고, 이 호스트 폰트의 사본이 든 폴더에 `detect.scan`과 `routes.routes`를 실행해
확인했다: NanumGothic Bold, Caveat-VF, Noto Sans CJK Regular 컬렉션의 페이스 열 개(인덱스 0-9)는 `outline`이고 `mkfont` 경로를 얻는다(Caveat, NanumGothic, Noto CJK의 각 페이스는 `experimental fit`과 `vector fit`도). neodgm.ttf는 `outline-composite`로 `mkfont`, `composite`(native), `vector fit`을 얻는다. `wqy_12pt.bdf`(종류 `bdf-iso10646`)와 `18x18ko.pcf.gz`(`bitmap`, 크기 [18])는 `mkfont`만, `hanglm16.pcf.gz`는 `bdf-ksc5601`로 `bdfface`와 `bdfface + from-svf fit`, NEODG16.SVF(`svf-precomposed`)는 `copy`와 `from-svf fit`, NEODG16A.SVF(`svf-jamo`)는 `copy`를 얻는다.

위 레시피의 독점 원본 사본에 같은 점검을 했다(2026-11-22. 자세한 것은 각 레시피에): 원시 DOS 폰트는 `dos-raw`에 `dos raw`(11,520 바이트짜리는 `johab844`도),
`johabm16.bdf`는 `bdf-johab`에 `hanterm`, `batang24.bdf`는 `bdf-ksc5601`에 `bdfface`와 `bdfface + from-svf fit`, 스트라이크가 있는 굴림과 Mac Seoul은
`outline-composite` / `outline`에 `mkfont`(비트맵 전용 Seoul은 `bitmap`에 `mkfont`만), Windows FON은 `bitmap`에 `mkfont`(이 파일들에서 실패한다),
`GHAN24.PFT`와 HWP `.PFT` 파일은 `other`, "unknown", 로컬 모드의 Mac 폰트는 위와 같고 1.0 폰트는 type 3으로 보인다. `mask fit` 행은 `mask_ok`를 설정하면
(서버가 `freetype-py`와 `uharfbuzz`를 import할 수 있을 때 설정한다) neodgm.ttf, Noto Sans CJK KR, 맑은 고딕에 나타난다.

## svf/의 페이스

<a id="svf-페이스-다시-빌드하기"></a>

`tools/build/faces.tsv`에는 `svf/`의 페이스마다 한 행씩(116행) 있고, `tools/build/build_faces.py`가 이를 실행해 각 결과를 배포된
페이스와 비교한다.

    python3 tools/build/build_faces.py --out $OUT/rebuild                      # every row with a recipe
    python3 tools/build/build_faces.py --out $OUT/rebuild NGOTB15 GBATB23      # some faces
    python3 tools/build/build_faces.py --out $OUT/rebuild --ext nanumgothic-nhn=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf

출력의 각 줄은 `FACE identical`, `FACE pixels`(글리프와 헤더 값은 같고 바이트 순서만 다름), `FACE differs: ...` 중 하나이다.
`identical`로 표시된 행이 그렇지 않으면 실행은 종료 코드 1로 끝난다.

**범위(verified, 2026-11-22).** 페이스 116개:

| 상태 | 페이스 | 개수 |
|---|---|---:|
| `ttf/`의 폰트에서 바이트 단위로 동일하게 다시 빌드됨 | 아래의 mkfont와 jamoset 행 중 바로 다음에 나오는 것을 제외한 전부 | 45 |
| 외부 OFL 폰트로 바이트 단위로 동일하게 다시 빌드됨 (`--ext nanumgothic-nhn=`, NAVER 원본 배포의 힌팅된 NanumGothicBold.ttf 3.021, Debian의 `fonts-nanum`이 싣는 것) | NGOTB17, NGO17X1, NGO17X2 (`--mono-hint`), NGO15X2, NGO16BX2, NGO21AX2 (글리프 둘은 `--fallback-ttf`로) | 6 |
| 다시 빌드됨, 글리프 하나가 다름 | NEODG16 (배포된 페이스에는 neodgm.ttf에 없는 U+212B도 있다), NGOTB16 (이 NanumGothic-Bold.ttf에 없는 U+3000도 있다); 나머지 글리프는 모두 동일 | 2 |
| 문서화만 됨 (이 저장소의 도구로는 레시피 없음) | [레시피 없는 페이스](#레시피-없는-페이스) 참고 | 63 |

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
  출력에 개수가 나온다). 이 옵션이 없으면 위로 넘치는 글리프는 대신 아래로 옮겨진다([기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑) 참고).
- `--mono-hint`: 폰트의 TrueType 힌팅을 쓰는 1 bpp(Pillow의 `fontmode "1"`을 거친 FreeType `FT_LOAD_TARGET_MONO`). 줄기가 정수
  픽셀에 맞춰진다. 힌팅된 폰트가 필요하며, NHN 원본 NanumGothicBold.ttf는 힌팅되어 있고 Google Fonts 빌드는 그렇지 않다.
- `--fallback-ttf`: 폰트에 없는 코드 포인트를 두 번째 폰트에서 그린다(여기서는 NGO*X2 보충 페이스의 â와 é).
- `--only-listed --unicode CODEPOINTS`: 나열한 코드 포인트만 정확히 담는다(행의 `tools/build/cps/FACE.txt`, 그 페이스 자신의
  목록. 부분 집합 페이스의 목록은 게임의 텍스트에서 나왔으며 그 텍스트는 이 저장소에 없다).
- `svf2to3.py --profile default`: mkfont는 레코드를 자기 순서로 쓴다. 배포된 페이스는 v2 -> v3 변환을 거쳤고, 이 변환은 레코드를
  `default` 프로필의 정규 순서로 쓴다. 새로 구운 것을 다시 배치해도 같은 바이트가 나온다.

### 완성형 글리프에서 자모 세트를 만드는 레시피 (`jamoset` 행)

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf $OUT/PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf $OUT/PRE.svf --mask-font none -o $OUT/NEODG16A.SVF --layout 844

`--from-svf`는 1 bpp 페이스의 완성형 음절을 세트 체계(여기서는 8x4x4)의 조각으로 분해하고, 그 밖의 글리프는 그대로 둔다.
Neo Dunggeunmo는 그 자체가 8x4x4 조각의 OR로 그려져 있어서 맞춤이 정확하고(IoU 1.000) 11,172개 음절이 모두 조합된다.
NEODG16D/E/F/32/32A는 셀만 다른 같은 방식이다(22x22, 18x24, 20x24; 36x36 안의 32 px와 46x54). NEODG16G는 6x2x1 세트 체계이다
(`--layout 621 --advance 0 --check`, `--ascent`/`--clip-cell` 없음: mkfont의 ascent 12), 10,684 바이트이며 MCU 예제용 작은
페이스이다(완성형 bake와의 IoU 0.958).

### 패밀리

| 패밀리 | 페이스 | 업스트림, 버전 | 라이선스 | 레시피 상태 |
|---|---|---|---|---|
| NanumGothic Bold | NGOTB*, NGO*X? | Google Fonts `ofl/nanumgothic` (3.020), `ttf/nanumgothic`에 있음; 1 bpp 힌팅 페이스는 NHN 원본 3.021 | OFL 1.1, RFN "Nanum", "NanumGothic" ... | verified (16 + 외부 6), NGOTB16은 글리프 하나 다름 |
| Gowun Batang Bold | GBATB*, GBA*X? | https://github.com/yangheeryu/Gowun-Batang (Google Fonts `ofl/gowunbatang`, 2.000), `ttf/gowunbatang`에 있음 | OFL 1.1 | verified (16); GBATB17O는 문서화만 됨 |
| Neo Dunggeunmo | NEODG*, NEO16BX2 | https://github.com/neodgm/neodgm v1.601, `ttf/neodgm`에 있음 | OFL 1.1, RFN "Neo둥근모", "NeoDunggeunmo" ... | verified (완성형 5, 자모 세트 7), NEODG16은 글리프 하나 다름; NEODG16B/C/O는 문서화만 됨 |
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
- **NEODG16B, NEODG16C**: 완성형 원본이 한 게임의 문자만 bake한 것이었던 Neo Dunggeunmo의 8x4x4 세트이다.
  KS X 1001 전체에 `jamoset.py --from-svf`를 적용하면 다른 조각에 맞춰진다(NEODG16B의 글리프 441개 중 71개가 다르다).
- **DIPHY36**: 36 px 1 bpp의 Diphylleia Regular로, 외부 파이프라인이 래스터화했다. Diphylleia의 현재 릴리스에 `mkfont.py`를
  쓰면 다른 픽셀이 그려진다(글리프 2,359개 중 2,358개).
- **PAPLG16**: Paperlogy 1.000에 `mkfont.py Paperlogy-4Regular.ttf --size 16 --cell 18 --width 18 --bpp 2 --clip-cell --ascent 14
  --unicode ascii,2026,2122,3131-318e --only-listed --space-advance 6 --punct-extra 1`. 1.001 릴리스는 글리프 149개 중 81개를
  다르게 그리며, 어느 쪽도 `ttf/`에 없다.

## 참고

### KS X 1001

KS X 1001(예전 이름 KS C 5601)에는 완성형 한글 음절 2,350자(행 0xB0-0xC8, 행마다 94자), 호환 자모 51개(행 0xA4:
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

### 인코딩

EUC-KR / 완성형 바이트 쌍 = GL 코드 + 0x8080 (`가` = B0A1 = GL 3021). Python: `bytes((0xB0,0xA1)).decode("euc_kr")`. 조합형(KS X 1001
부속서 3, `johab` 코덱): 16비트 코드 `1 iiiii mmmmm fffff`에 채움 값(초성 2 = ㄱ, 중성 3 = ㅏ, 종성 1 = 없음)이 있고 `가` = 8861;
`bytes((0x88,0x61)).decode("johab")`. 유니코드 음절 = 0xAC00 + (초성 x 21 + 중성) x 28 + 종성 (자모 인덱스는 0부터). Synthetic
(`tools/test_recipes.py`).

### 알려진 한계

- `jamoset.py`의 기본 `--binarize mono`에는 `freetype-py`가 필요하다(`--mask-font`에는 `uharfbuzz`도). 이 호스트에는 둘 다 설치되어 있지
  않아서(`cannot import freetype`) 레시피는 `--binarize threshold`를 쓰고, `--mask-font none`은 1 bpp 맞춤이 `$JAMOSET_MASK_FONT`에
  좌우되지 않게 한다. [자모 세트](#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- 실행 시간(이 호스트, 코어 하나): 16 px 아웃라인 폰트의 1 bpp `threshold` 맞춤은 약 12초, 2 bpp는 약 73초, Gowun Batang adaptive 20 px는
  약 90초이다. 2 bpp 페이스는 같은 1 bpp 페이스의 약 1.5-1.6배, 자모 세트는 약 6분의 1이다.
- 비트맵이나 1 bpp 페이스에서 2 bpp 페이스를 만드는 도구는 없다.
- `mkfont.py`는 요약을 한국어로 출력한다. 필드 이름을 찾으려고 그 stdout을 파싱하지 말 것.
- 도구 전반의 알려진 빈틈: [tools.ko.md](tools.ko.md#도구에-남은-빈틈)의 "도구에 남은 빈틈".

## svf/에 페이스 추가하기

위의 레시피로 페이스를 만들고, 점검하고([페이스 점검](#페이스-점검)), 다음을 추가한다.

- `svf/`에 그 옆의 라이선스 텍스트;
- `web/LICENCES.tsv`의 행과 `web/FAMILIES.tsv`의 행;
- `tools/build/faces.tsv`의 행(레시피를 적거나, 방법 `none`과 그 이유를 적음).

그렇지 않으면 `tools/test_build_faces.py`와 `tools/test_web_picker.py`가 실패한다. maker는 이 표들에 넣을 줄을 만들어 준다
(`build-<id>/LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`).
