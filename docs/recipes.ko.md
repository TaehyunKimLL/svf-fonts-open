[English](recipes.md) | **한국어**

# 레시피: 폰트에서 SVF 페이스(face)까지

아웃라인 폰트, 비트맵 폰트, 원시 자모 파일, 폰트 ROM에서 완성형 SVF 페이스나 자모 세트를 만드는 방법을 설명한다.
아래의 입력 형식 표에서 시작한다. 자모 세트 설계는 [자모 세트](jamo-sets.ko.md), 안티앨리어싱은 [안티앨리어싱](anti-aliasing.ko.md)를 참고한다. 옵션은 [도구 설명서](tools.ko.md), 바이너리 형식과 용어는
[SVF 형식](../spec/SVF.ko.md)과 [한영 용어집](../spec/SVF.ko.md#glossary)을 참고한다.

명령은 프로젝트 루트에서 실행한다. 먼저 출력 폴더를 정하고, 대문자로 쓴 입력 이름은 직접 마련한 파일로 바꾼다.

    OUT=${TMPDIR:-/tmp}/svf-recipes
    mkdir -p "$OUT"

아웃라인 변환에는 선택한 Python 환경의 Pillow와 fontTools가 필요하다. `python3 -I`는 사용자 site 패키지를 제외한다.
자모 도구는 `--pylib DIR`로 기존 의존성 폴더를 읽을 수 있다.

변환 명령은 표시된 출력 경로에 쓴다. 명령 틀의 대괄호는 선택 인수를 뜻한다. 대괄호나 여러 대안을 그대로 입력하지 않는다.
독점 폰트의 원본 파일은 별도로 마련해야 한다.

`mkfont.py` 다음에는 `svf2to3.py --profile default --check`로 `default` 레코드 배치를 선택하고 픽셀이 같은지 점검한다
([완성형 페이스](#완성형-페이스-mkfontpy)). 다른 대상 프로필은 [렌더러 설계](../spec/renderer-design.ko.md)를 참고한다.

수치 예시는 명시한 입력과 설정으로 측정한 값이다. 파일 크기와 실행 시간은 도구 및 폰트 버전에 따라 달라질 수 있다.
*Synthetic* 예시는 테스트에서 만든 입력을 쓴다. 맞춤의 IoU는 맞춤 보고서에서 얻는다. `--check`는 조합과 표의 일관성을
점검하며, 최소 IoU를 요구하지 않는다.

목차:

- [빠른 시작: 입력 종류별](#빠른-시작-입력-종류별)
- [페이스 점검](#페이스-점검)
- [아웃라인 폰트](#아웃라인-폰트)
- [비트맵 폰트](#비트맵-폰트)
- [DOS 시대 원시 폰트](#dos-시대-원시-폰트)
- [Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기](#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기)
- [한국 MSX 폰트 (MSX2와 MSX1)](#한국-msx-폰트-msx2와-msx1)
- [MAME 세트의 한글 폰트 ROM](#mame-세트의-한글-폰트-rom)
- [OS/2 한글 폰트(완성형)에서 완성형 페이스와 자모 세트 만들기](#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기)
- [고해상도 비트맵 폰트에서 저해상도 페이스 만들기](#고해상도-비트맵-폰트에서-저해상도-페이스-만들기)
- [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트)
- [기존 SVF](#기존-svf)
- [SVF 페이스를 다시 TTF 비트맵 폰트로](#svf-페이스를-다시-ttf-비트맵-폰트로)
- [벌 수 정하기](#벌-수-정하기)
- [데스크톱 앱과 maker 경로](#데스크톱-앱과-maker-경로)
- [svf/의 페이스](#svf의-페이스)
- [참고](#참고)
- [svf/에 페이스 추가하기](#svf에-페이스-추가하기)
- [참고 문헌](#참고-문헌)

<a id="빠른-시작-입력-종류별"></a>

## 1. 빠른 시작: 입력 종류별

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
| Windows `.FNT` / `.FON` | 리더 없음(FreeType이 유니코드 맵을 주지 않는다. 먼저 바깥 도구로 BDF로 변환하라) | 없음 | [Windows FNT와 FON](#windows-fnt와-fon) |
| DOS 원시 자모 조각 폰트(8x4x4 `HANGUL.FNT`, san, 도깨비, Kyra...) | `johab844.py`(16 px 8x4x4) | `jamoset.py --layout L` | [DOS 시대 원시 폰트](#dos-시대-원시-폰트) |
| HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT` | `hwpfont.py bdf --face N` 다음 `mkfont.py` | `jamoset.py --layout hwp1 --face N`(HWP 자체 규칙, 정확) | [HWP 1.x와 2.x 폰트](#hwp-1x와-2x-폰트) |
| HWP 3.0 `HAN*.FNT`(음절 2,350개, 16 px는 8x4x4 벌 체계 추가) | `hwpfont.py bdf` 다음 `mkfont.py` | `jamoset.py --layout 844-hwp3`(16 px), 그 밖에는 `--from-svf` | [HWP 3.0 FNT 폰트](#hwp-30-fnt-폰트) |
| KS X 1001 원시 덤프(코드 순서의 음절 2,350개, 또는 94 x 94 표) | `hwpfont.py bdf`(16-48 px 덤프), 또는 `rawcarve.py bdf --dense` / `--grid`; 다음 `mkfont.py`나 `bdfface.py` | `jamoset.py --from-svf` | [KS X 1001 원시 덤프](#ks-x-1001-원시-덤프) |
| 프로그램이나 ROM 안의 폰트(DOS 드라이버나 TSR, 워드프로세서, 한글 VGA BIOS + 폰트 ROM) | 찾기는 `binscan.py`, 잘라 내기는 `rawcarve.py`(원시, BDF, 또는 드라이버 규칙대로 조합), 다음 `bdfface.py` | 잘라 낸 원시 폰트에 `jamoset.py --layout 844`, 또는 `--from-svf` | [Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기](#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기) |
| 한국 MSX ROM(대우, 금성: MSX2 SUB-ROM, CPC-400S 폰트 ROM, MSX1 BIOS) | `msxfont.py kfn-map` + `rawcarve.py bdf --chars map`(CPC-400S), `msxfont.py msx1` + `mkfont.py`(MSX1), 그다음 `bdfface.py` | `jamoset.py --layout spec --spec tools/specs/msx2-daewoo.json`(MSX2, 정확) | [한국 MSX 폰트](#한국-msx-폰트-msx2와-msx1) |
| MAME 세트에 든 한국 기계나 아케이드 게임의 ROM(반전된 자모 ROM, 여러 비트 스프라이트 타일) | `rawcarve.py region` + `ink --gfx`(또는 `--invert`), `rawcarve.py bdf --dense`, 그다음 `bdfface.py` | `jamoset.py --layout spec`(자체 규칙이 있는 폰트, 정확), 잘라 낸 8x4x4 폰트에 `--layout 844`, 또는 `--from-svf` | [MAME 세트의 한글 폰트 ROM](#mame-세트의-한글-폰트-rom) |
| OS/2 한글 System DBCS 폰트(`$korZN16.FNT`, `$korZN24.FNT`, 완성형) | `os2dbcs.py table`, `rawcarve.py bdf --grid 0xA1,0xA1,94`, `bdfface.py` | `jamoset.py --from-svf` | [OS/2 한글 폰트(완성형)](#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기) |
| 자모 글리프가 있는 TTF(첫가끝 자모, PUA 조각, GSUB `ljmo`) | 다른 TTF와 같이 | 합성 글리프는 `jamovec.py --components`, 변형은 `--mask-font`, 그 밖에는 맞춤 | [이미 자모를 가진 TrueType 폰트](#이미-자모를-가진-truetype-폰트) |
| 16 px나 2 bpp로 쓰고 싶은 24-48 px 비트맵 페이스 | `svfscale.py --size 16 [--bpp 2]` | `jamoset.py --from-svf`(1 bpp 결과) | [고해상도 비트맵 폰트에서 저해상도 페이스 만들기](#고해상도-비트맵-폰트에서-저해상도-페이스-만들기) |
| Mac HangulTalk 1.0 `fbit`(벌 45개 + `fdef`) | 없음 | `jamoset.py --layout mac-fbit-45sets` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| Mac HangulTalk 7.1 type-3 `fbit` + HTBL 1 | `macfbit3.py bdf` + `mkfont.py` | `macfbit_svf.py build` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| SVF 페이스 | `svfdy.py`, `svf2to3.py` | `jamoset.py --from-svf`(1 bpp 원본) | [기존 SVF](#기존-svf) |
| 다시 TTF(또는 BDF) 비트맵 폰트로 만들 SVF 페이스 | `svf2ttf.py ttf`(또는 `bdf`) | 같음: 모든 음절을 합성한 완성형 폰트(`--composite`: 조각을 나눠 쓰고 음절은 합성 글리프) | [SVF 페이스를 다시 TTF 비트맵 폰트로](#svf-페이스를-다시-ttf-비트맵-폰트로) |

자모 세트의 벌 수를 정하려면: [벌 수 정하기](#벌-수-정하기). 안티앨리어싱 페이스:
[2 bpp 안티앨리어싱 페이스](#truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기).

모든 행의 점검은 같다: [페이스 점검](#페이스-점검)(샘플 줄의 measure와 잉크, 자모 세트는 맞춤 IoU). 흑백 원본 픽셀을 같은 크기로 저장해도 중간 피복도는 새로 생기지 않는다. 더 작은 크기로 다시 샘플링하면(`svfscale.py --bpp 2`) 중간 단계가 생길 수 있다. 대상의 메모리가 적으면 자모
세트를 고르고(2,350 음절 16 px 예시는 약 115 KB, 그 자모 세트는 약 20 KB), 모든 음절이 원본과 정확히 같아야 하면 완성형을
고른다.

<a id="페이스-점검"></a>

## 2. 페이스 점검

<a id="새-페이스-점검"></a>

아래의 모든 레시피는 같은 점검으로 끝난다. 샘플 줄은 `안녕하세요 ABC 123`이고, 따로 적지 않으면 페이스는 16x16 셀의 16 px이다.

    python3 tools/svfline.py measure "안녕하세요 ABC 123" FACE.SVF       # width=W ascent=A descent=D
    python3 tools/svfline.py line 200 24 0 16 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray   # a 200x24 GRAY8 buffer
    python3 tools/fontmetrics.py FACE.SVF                                 # glyphs whose ink reaches past the advance
    python3 tools/svf2to3.py FACE.SVF $OUT/x.SVF --check                  # re-layout and compare every glyph
    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf -o $OUT/m.tsv
    python3 tools/facecheck.py verify $OUT/m.tsv

- 파일 크기와 글리프 수(코드 포인트 표의 항목 수)는 도구 자신의 요약 줄에 나온다. `mkfont.py`는 이를 한국어로 출력한다
  (`글리프 2446개 ... 125,520 바이트`).
- 잉크는 `line` 버퍼에서 0이 아닌 바이트의 수이다:
  `python3 -c "import sys;print(sum(1 for b in open(sys.argv[1],'rb').read() if b))" $OUT/out.gray`. 아무것도 그리지 못하는 페이스는
  잉크가 0이다.
  위의 200x24 버퍼와 기준선 16은 16 px 셀에 맞는다. 셀 C가 16이 아닌 페이스(12, 15, 24, 40, 48 px)의 레시피 잉크 수치는
  `line 400 C+8 0 C`로 얻은 것이다(너비 400의 버퍼, 기준선은 셀 높이, C+8행. 버퍼는 잰 너비 이상, 셀 + descent 이상의 높이여야 하며
  아니면 줄이 잘린다): 24 px 페이스라면 `python3 tools/svfline.py line 400 32 0 24 "안녕하세요 ABC 123" FACE.SVF > $OUT/out.gray`.
  측정 너비가 200(큰 셀 명령 틀에서는 400)을 넘으면 더 넓은 버퍼를 쓴다. 해당 예외는 아래에 따로 적었다.
- 자모 세트는 `--check`(`jamoset.py`와 `jamovec.py`)로 판정한다. 조각에서 음절 11,172개를 모두 조합하고 표 오류에서 실패한다. 그
  앞의 맞춤 줄은 조각과 원본 음절의 IoU를 출력한다(`fit: 11172 syllables, IoU 0.817`). `--check`는 맞춤이 나쁘다고 실패하지는 않는다.
  IoU를 읽고 결과를 직접 보라(`svfline.py line`, 또는 `web/` 선택기).
- `svf2to3.py --check`는 `svfline`으로 글리프마다 비교한다. 위 `facecheck.py` 명령은 `HEAD`의 커밋된 파일로
  매니페스트를 만든 뒤 작업 파일을 대조한다. 새 `FACE.SVF`를 검증하는 명령은 아니다.
  `tools/build/build_faces.py`는 `svf/`의 페이스를 다시 빌드한다([svf/의 페이스](#svf의-페이스) 참고).

기준 실행(검증), 아래의 16 px NanumGothic Bold: 1 bpp `125,520` 바이트, 글리프 2,446개, `width=146 ascent=14 descent=2`, 잉크 677.

<a id="아웃라인-폰트"></a>

## 3. 아웃라인 폰트

FreeType은 TrueType과 CFF(OpenType `.otf`)를 똑같이 읽으므로, 유니코드 cmap이 있는 정적 TTF나 OTF는 곧바로 도구에 들어간다.
`jamoset.py --from-ttf`, `jamoaa.py`, `jamovec.py`, `--binarize threshold|ridge`는 윤곽선을 직접 평탄화하며(fontTools pen, 정확 면적
피복도) 둘에서 똑같다. 컬렉션, 가변 폰트, Mac 형식 폰트는 먼저 한 단계가 필요하다(아래).

<a id="완성형-페이스-mkfontpy"></a>

### 3.1. 완성형 페이스 (`mkfont.py`)

원본: `ttf/nanumgothic/NanumGothic-Bold.ttf`. 완성형, 1 bpp, 그다음 정규 레이아웃 단계:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-1bpp.svf \
        --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/ng16-1bpp.svf $OUT/NG16.SVF --profile default --check

검증: `125,520 바이트`(`mkfont.py`의 임시 파일), 글리프 2,446개(한글 음절 2,350개). 렌더는 `width=146 ascent=14 descent=2`,
잉크 677. `svf2to3.py ... --profile default --check`는 다시 125,520 바이트를 쓴다(글리프는 같고 레코드 순서만 다르다. 처음 다른 바이트는 813번). `data_in=86332 data_out=86332`를 보고한다.

`mkfont.py`는 레코드를 자기 순서로 쓴다. `svf2to3.py --profile default`는 이를 `default` 프로필의 정규 순서로 다시 배치한다(배포된
페이스, `tools/build/build_faces.py`, maker 모두 이 단계로 끝난다). `--check`가 픽셀이 같음을 증명한다. 다른 대상(`mcu-strict`,
`dos`, `wasm`, `full`, `simd16`)에 맞게 배치하려면 그 `--profile`을 쓴다.

안티앨리어싱(2 bpp): 같은 명령에 `--bpp 2`(`195,760 바이트`, 글리프 2,446개, `width=146 ascent=14 descent=2`, 잉크 847. 피복도는 4단계로
양자화된다). 정규 단계는 이번에도 크기(195,760 바이트)를 유지하고 픽셀이 같음을 증명한다. `--bpp 8`은 전체 피복도를 유지한다(8 bpp 페이스는 호스트용). 크기, 셀, ascent, 클리핑을 고르는 `mkfont.py` 옵션은
[기준선, 세로 이동, 클리핑](#기준선-세로-이동-클리핑)에, `svf/`의 행 레시피 전체는
[완성형 글리프 레시피](#완성형-글리프-레시피-mkfont-행)에 있다.

**문자 집합이 필요하다**(`--unicode SET` 또는 `--chars-from FILE`). 둘 다 없으면 `mkfont.py`는 종료 코드 2로 끝난다. 이름은
[참고](#참고)에 있다.

<a id="opentype-cff-otf"></a>

### 3.2. OpenType CFF (`.otf`)

Noto Sans CJK KR은 누구나 구할 수 있는 CFF 폰트이다(SIL OFL 1.1. Debian의 `fonts-noto-cjk`가 KR, JP, SC, TC, HK 페이스의 컬렉션인
`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`로 싣는다. [TTC와 OTC](#ttc와-otc) 참고). KR 페이스를 일반 `.otf`로 저장해서
변환한다([폰트 원본과 라이선스](#ref-fonts) 참고).

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

### 3.3. TrueType와 OpenType 폰트에서 만드는 자모 세트

자모 세트(조합형)는 조각과 표를 담는다. 1 bpp에서 조합한 음절은 조각 둘 또는 셋의 OR이고,
2 bpp에서는 픽셀마다 가장 큰 단계를 취한다. [자모 세트](jamo-sets.ko.md)를 참고한다. 윤곽선 폰트에서 조각을 얻는 방법은 폰트가 무엇을
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

### 3.4. 이미 자모를 가진 TrueType 폰트

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

### 3.5. TrueType/OpenType 폰트에서 2 bpp 안티앨리어싱 페이스 만들기

<a id="안티에일리어싱된-2-bpp-페이스"></a>
<a id="안티앨리어싱된-2-bpp-페이스"></a>
<a id="truetypeopentype-폰트에서-2-bpp-안티에일리어싱-페이스-만들기"></a>

2 bpp 페이스는 픽셀마다 네 단계(0, 1, 2, 3)를 저장한다(피복도 = 단계 × 85). 아래의 아웃라인 폰트 경로는 윤곽선을
래스터화해 이 단계를 얻는다. 흑백 비트맵의 원래 크기에서는 피복도가 0과 255뿐이지만, 회색조 비트맵은 이미 중간 피복도를
가질 수 있다. 큰 비트맵을 축소해도 중간 단계가 생길 수 있다
([고해상도 비트맵 폰트에서 저해상도 페이스 만들기](#고해상도-비트맵-폰트에서-저해상도-페이스-만들기)). 아웃라인 폰트의 세 가지 경로:

    python3 tools/mkfont.py ttf/nanumgothic/NanumGothic-Bold.ttf $OUT/ng16-2.svf --size 16 --bpp 2 --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --layout 844 --from-ttf ttf/nanumgothic/NanumGothic-Bold.ttf --size 16 --bpp 2 \
        --check -o $OUT/NG16JA.SVF
    python3 tools/jamovec.py master ttf/neodgm/neodgm.ttf -o $OUT/neodgm.json --components
    python3 tools/jamovec.py render $OUT/neodgm.json --size 16 --bpp 2 --check -o $OUT/NEOVEC16A.SVF

**단계를 정하는 것.** `mkfont.py --bpp 2`는 각 글리프를 Pillow를 통해 FreeType의 안티앨리어싱 렌더러로 그리고(FreeType이 기본으로
적용하는 폰트의 힌팅), 8비트 피복도를 `(coverage x 3 + 127) // 255`로 양자화한다. 2 bpp용 감마, 임계값, 오버샘플링, 힌팅 옵션은 없다
(`--mono-hint`는 `--bpp 1`용이고 그 밖에는 거부된다). 그러니 크기(`--size`, 배치는 `--cell` / `--ascent`)가 유일한 조절이다.
`jamoset.py --bpp 2`(`jamoaa.py`)는 음절을 자신의 정확 면적 피복도(힌팅 없음)로 래스터화하고, 1 bpp 맞춤의 영역으로 각 픽셀을 어느
조각이 소유할지 정하며, 각 조각의 단계를 그것을 공유하는 음절들의 중앙값으로 정한 뒤 단계 오차에 대해 다듬는다: `--aa-refine N`
(2회. 0이면 중앙값만), `--clean` / `--no-clean`(2 bpp에서는 켜짐: 조각을 그 자모의 윤곽이 잉크를 두는 곳으로 한정하고, 옅은 단계는
음절의 절반이 가진 곳에만 둔다), 벌 체계(`--layout 844` 또는 `adaptive[:NI,NM,NF]`, [벌 수 정하기](#벌-수-정하기)).
`jamovec.py render --bpp 2`(기본값)는 벡터 마스터의 조각을 같은 정확 면적 피복도로 그린다.

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
낮추고 단계 2 IoU를 높인다. 위의 16 px Neo둥근모 렌더에는 부분 피복도가 없다. 그 2 bpp 페이스는 단계 3인 1 bpp 페이스일 뿐이고
바이트만 더 든다. 자모 세트의 기준선은 폰트의 ascent가 아니라 맞춤(잉크 상자 가운데)에서 오므로 `mkfont.py` 페이스와 한 행 다를 수
있다(`--baseline`으로 정한다).

**크기 고르기.** 위의 2 bpp 완성형 예시에서 잉크 픽셀의 55-59 %가 단계 3이다. 더 작은 크기는 여기서 재지 않았다. 12-14 px에서는 대상에서 2 bpp 페이스와 힌팅된 폰트의 1 bpp `--mono-hint`
페이스([완성형 글리프 레시피](#완성형-글리프-레시피-mkfont-행))를 비교한 뒤 고르라. 그리는 시점에 축소하지 말고 대상이 그리는
크기로 구워라. 모든 결과를 숫자(잉크, 단계, 자모 세트는 `aa:` 줄의 단계 오차와 단계 2 IoU)와 눈으로 점검하라. `svfline.py line`은
GRAY8을 쓰고, `web/` 피커는 페이스를 그 단계로 보여 준다.

**함정.** 다른 조각 위의 안티앨리어싱된 조각은 합이 아니라 최댓값을 취한다. 교차하는 획은 완성형 글리프보다 옅게 보일 수 있다. 흑백 대상(`SVF_T_MONO_PAGE`, `SVF_T_MONO_ROW`)은 그리는 시점에 2 bpp 페이스를 임계값으로 자른다
(`svf_target.mono_threshold`, 기본값 128). 모노 디스플레이에는 1 bpp
페이스를 주어라. `--bpp 8`(mkfont만)은 호스트용으로 전체 피복도를 유지한다.

배경 설명(피복도, 감마, 서브픽셀 렌더링을 하지 않는 이유), 타깃별 단계-색 변환 규칙, 자모 세트의 최댓값과 OR, bpp 선택표는
[안티앨리어싱](anti-aliasing.ko.md)에 있다. 미리보기는 [웹 렌더러 안내서](web-renderer-guide.ko.md)를 참고한다.

<a id="기준선-세로-이동-클리핑"></a>

### 3.6. 기준선, 세로 이동, 클리핑

페이스의 ascent 필드는 셀 위에서부터 잰 기준선 행이다. 배율 1에서 C 렌더러는 셀 위끝을
`y_baseline - ascent + dy`에 놓는다. 글리프별 `dy`가 양수이면 아래로 이동한다.
[SVF 메트릭](../spec/SVF.ko.md)과 [C 렌더러 안내서](c-renderer-guide.ko.md)를 참고한다.

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

### 3.7. TTC와 OTC

<a id="opentype-cff-컬렉션-가변-폰트"></a>

`mkfont.py`는 컬렉션의 인덱스 0을 연다(synthetic: Galmuri9 + Galmuri7의 TTC는 Galmuri9와 똑같이 변환된다). 다른 페이스는 먼저 일반
폰트로 저장해 둔다(maker의 `ttc-face`와 같은 단계. TrueType든 CFF든 페이스에 똑같이 된다. CFF 페이스는 위 OpenType CFF 레시피처럼 출력을 `.otf`로 이름 붙인다).

    python3 maker/srcprep.py ttc-face F.ttc $OUT/F1.ttf --index 1

위치가 아니라 이름으로 고른다. Noto CJK 컬렉션에서 KR은 인덱스 0이 아니다. 이름을 나열한다.

    python3 -c "from fontTools.ttLib.ttCollection import TTCollection as C; [print(i, f['name'].getDebugName(4)) for i, f in enumerate(C('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').fonts)]"

검증(이 호스트의 Noto Sans CJK Regular 컬렉션): 페이스 열 개, 인덱스 0 Noto Sans CJK JP, 1 KR, 2 SC, 3 TC, 4 HK, 그다음 5-9 Noto Sans Mono CJK JP, KR, SC, TC, HK. 이렇게 얻은 페이스는 일반 정적 폰트처럼 레시피에 들어간다(위의
[OpenType CFF](#opentype-cff-otf)가 바로 이것이다).

<a id="가변-폰트"></a>

### 3.8. 가변 폰트

`mkfont.py`는 기본 인스턴스를 그린다. 다른 인스턴스는 먼저 정적 인스턴스로 잘라 낸다(fontTools, maker의 `instance` 단계)([fontTools 가변 폰트 인스턴스 생성기](#ref-fonttools) 참고).

    python3 -m fontTools.varLib.instancer ttf/caveat/Caveat-VF.ttf wght=700 -o $OUT/Caveat-Bold.ttf
    python3 tools/mkfont.py $OUT/Caveat-Bold.ttf $OUT/CAVB24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/mkfont.py ttf/caveat/Caveat-VF.ttf $OUT/CAV24.SVF --size 24 --bpp 2 --unicode ascii --latin
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAVB24.SVF     # one face per call: several faces are a fallback chain
    python3 tools/svfline.py measure "Hamburgefonstiv" $OUT/CAV24.SVF

검증: 기본 인스턴스(Regular 400)는 6,760 바이트로, 700 인스턴스는 7,192 바이트로 변환된다(각각 글리프 95개, "Hamburgefonstiv"의
폭은 Bold 141 px, Regular 136 px. 요약이 뺀 글자 1개는 요청했지만 폰트에 없는 글자이다). 이름 있는 인스턴스는 `fvar` 표에 있다(`Caveat`: Regular,
Bold; `EB Garamond`: Regular .. ExtraBold).

<a id="mac-형식-truetype"></a>

### 3.9. Mac 형식 TrueType

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

<a id="비트맵-폰트"></a>

## 4. 비트맵 폰트

<a id="x-window-한글-폰트"></a>

비트맵 폰트는 두 종류가 서로 다른 경로로 도구에 닿는다. 유니코드 인코딩(`CHARSET_REGISTRY "ISO10646"`, 또는 내장 스트라이크가 있는
TrueType)은 `mkfont.py`와 FreeType을 거치고, KS C 5601 / KS X 1001 인코딩(`ENCODING` = GL 코드, X Window 한글 폰트)은
`bdfface.py`를 거친다.

<a id="iso-10646-bdf와-pcf"></a>

### 4.1. ISO 10646 BDF와 PCF

`mkfont.py`는 BDF나 PCF를 Pillow의 FreeType으로 읽되, 파일에 내장된 픽셀 크기(스트라이크)에서만 읽는다. 다른 크기는 `OSError:
invalid pixel size`이며, maker의 `detect.bitmap_strikes`가 폰트가 제공하는 크기를 알려 준다. 이제 shim이나 우회는 없다. `mkfont.py`는
fontTools에 코드 포인트가 cmap에 있는지 묻고, sfnt가 아닌 파일(BDF, PCF, FNT)은 오류가 아니라 알 수 없음으로 취급한다(`cmap_has`가
None을 돌려준다). 예시는 다음 폰트를 쓴다:
`/usr/share/dosbox-x/wqy_12pt.bdf`(WenQuanYi Bitmap Song, 16 px, 유니코드)와 `/usr/share/fonts/X11/misc/18x18ko.pcf.gz`(Misc Fixed
Wide, 18 px)([BDF 형식](#ref-bdf) 참고).

    python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf $OUT/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-2bpp.svf --size 18 --bpp 2 --unicode ascii,ksx1001-hangul

Verified, shim 없이: BDF `115,684 바이트`, 글리프 2,446개, `width=156 ascent=12 descent=4`, 잉크 348; PCF 1 bpp `116,552 바이트`, 글리프
2,446개(18x18 셀), `width=234 ascent=15 descent=3`, 잉크 366; PCF 2 bpp `181,108 바이트`. 이 비트맵에는 흑백 피복도만 있으므로 `--bpp 2`의 단계는 0과
3뿐이다. 같은 모노크롬 픽셀을 2 bpp로 담을 뿐 부드러운 페이스가 아니다. 이 페이스의 자모 세트는 완성형 결과에 대한 맞춤이다:
`jamoset.py --layout 844 --from-svf $OUT/bdf16-1bpp.svf --mask-font none --check -o ...`(수치는 다음 소절의 bdfface 페이스에 있다).

<a id="ks-c-5601-bdf와-pcf"></a>

### 4.2. KS C 5601 BDF와 PCF

X Window 한글 폰트(`CHARSET_REGISTRY "KSC5601.1987"` 또는 `"KSX1001"`, `ENCODING` = GL 코드: `-baekmuk-*`, `-daewoo-*`, `hanglm16`)는
BDF만 읽는 `bdfface.py`로 간다. PCF는 maker의 `srcprep.py pcf-bdf`(표준 라이브러리만 사용, gz 허용. 외부 `pcf2bdf`가 필요 없다)로 변환하고,
완성형 페이스를 만든 다음 거기에 자모 세트를 맞춘다.

    python3 -c "import sys; sys.path.insert(0, 'tools'); import mkfont; open(sys.argv[1], 'w', encoding='utf-8').write(''.join(chr(c) for c in mkfont.NAMED_RANGES['ksx1001-hangul']()))" $OUT/ks.txt
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/hanglm16.pcf.gz $OUT/hanglm16.bdf
    python3 tools/bdfface.py --hangul $OUT/hanglm16.bdf --ascii /usr/share/dosbox-x/wqy_12pt.bdf --cell 16x16 \
        --chars-from $OUT/ks.txt -o $OUT/KS16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/KS16.SVF --mask-font none --check -o $OUT/KS16J.SVF

검증: BDF는 `FONTBOUNDINGBOX 16 16 0 -2`, `PIXEL_SIZE 16`, `CHARSET_REGISTRY "KSC5601.1987"`; `bdfface.py`는 `125,096 바이트`,
음절 2,350개(글리프 2,447개: 음절, ASCII 0x20-0x7E, 자체의 U+2026 / U+25A1), 잘린 글리프 7개, `width=156 ascent=14 descent=2`, 잉크 354를
쓴다. 자모 세트는 `18,436 바이트`, 글리프 441개, 조각 344개, 음절 2,350개에 대한 IoU 0.826(p5 0.511)이고 `--check`가 음절 11,172개를
모두 조합하며 잉크 361이다. 유니코드 BDF를 두 절반 모두로 쓴 같은 체인(`--hangul wqy_12pt.bdf --ascii wqy_12pt.bdf`)은 페이스
`115,700 바이트`, 자모 세트 `16,272 바이트`, IoU 1.000이다.

`bdfface.py`는 `--chars-from`이 지정한 한글 음절(임의의 텍스트; `mkfont.py`의 규칙), `--ascii`의 ASCII 0x20-0x7E, 자체의 U+2026 /
U+25A1만 담는다. BDF에서 기호나 자모는 오지 않는다. 셀의 기본값은 BDF의 박스와 상관없이 24x24이므로 `--cell`을 주어라. `--ascent` /
`--hangul-ascent`는 기준선을 정한다. Synthetic(`tools/test_recipes.py`): 음절 10개짜리 KS C 5601 BDF와 ISO 10646 ASCII BDF는 정확히 그
음절만 담은 페이스를 주고 행도 제자리에 있다.

<a id="hanterm"></a>

### 4.3. hanterm

hanterm 폰트(johab-1 인코딩, 글리프 번호는 `ENCODING`, 10x(3|4)x4 벌, 글리프 529개)는 직접 읽는다.

    python3 tools/jamoset.py --layout hanterm-johab johabm16.bdf --check -o $OUT/HTERM16J.SVF

KAIST 명조와 KAIST 고딕, hanterm 3.0.4 폰트 세트의 16 px Johab 폰트(`johabm16.bdf`, `johabg16.bdf`; 각각 글리프 529개,
`CHARSET_REGISTRY "JOHAB-1"`; KAIST; 재배포 조건 명시 없음)로 실행했다.

명조: `13,740 바이트`, 조각 368개, `check: composed 11172 syllables from 368 glyphs, JSET 1303 bytes`, `width=80 ascent=14
descent=2`(샘플 줄의 음절 다섯 개. BDF에 ASCII가 없으니 ASCII는 `--eng`에 원시 8x16 영문 폰트를 준다), 잉크 310. 고딕: `13,180 바이트`,
잉크 214. maker의 `detect.scan`은 둘 다 종류 `bdf-johab`, 레이블 "BDF (johab)", 크기 [16], 경로 `hanterm`을 준다. 같은 세트의 `10-6-6`
폴더(10x6x6 벌)는 다른 레이아웃이라 실행하지 않았다. Synthetic(`tools/test_recipes.py`): 글리프 529개의 hanterm BDF가 음절 11,172개를
10/4/4 벌 체계로 모두 조합한다.

<a id="hbf"></a>

### 4.4. HBF

`bdfface.py --ascii`는 HBF(옆에 `.bin` 또는 `.bin.gz`가 있는 `.hbf`)를 읽지만 페이스의 ASCII 절반으로만 읽는다. 한글 절반은 BDF여야
한다. ibiblio의 HBF 모음에 있는 X11 Sony 폰트 Sony Fixed 12x24(`12x24.hbf`와 `12x24.bin.gz`; Sony, 고지 조건으로 자유 사용)를 ASCII 절반으로,
Baekmuk 2.0 X11 BDF 세트의 Baekmuk 바탕 24(`batang24.bdf`, KS C 5601)를 한글 절반으로 실행했다.

    python3 tools/bdfface.py --hangul batang24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HBF24.SVF

`206,872 바이트`, 음절 2,350자, ascent 22, step 24, 잘린 글리프 없음, `width=216 ascent=22 descent=2`(24 px 음절 다섯 개와 12 px 문자 일곱 개),
잉크 746. `.hbf` 옆에 `.bin`을 풀어 두면 페이스가 바이트 단위로 같다. maker의 `detect.scan`(사본에서 확인, 업로드와 로컬
모드 모두)은 `12x24.bin.gz`와 함께 있는 `12x24.hbf`를 형식 `hbf`, 레이블 "HBF", 24 px, ASCII 피복도 95로 나열하고 자기 경로는 주지 않는다.
HBF는 페이스의 라틴 절반일 뿐이다. 라틴 절반으로 쓸 수 없는 HBF에는 이유를 말하는 레이블이 붙는다: 2 바이트 코드 범위(`uni24.hbf`,
`unihan16.hbf`: "HBF: two-byte code range not supported"), gzip으로 압축된 HBF 자체("HBF: gzipped HBF not supported"), 없는 비트맵 파일
("HBF: bitmap file missing").
Synthetic(`tools/test_bdfface.py`): 합성 HBF를 ASCII 절반으로.

<a id="windows-fnt와-fon"></a>

### 4.5. Windows FNT와 FON

FreeType에는 winfnt 드라이버가 있어서 `mkfont.py`는 Windows `.FNT`(또는 여러 개를 담은 `.FON`)를 BDF나 PCF처럼 폰트 자신의 픽셀 크기로
열지만, 거기서 그리지는 못한다. 드라이버가 이런 폰트에 `FT_ENCODING_NONE` 맵 하나만 주어서 유니코드가 없고, 모든 코드 포인트가 글리프 0으로
떨어진다. Windows 95 한글판의 시스템 폰트(Microsoft, 독점)로 실행했다: VGAFIX.FON "Fixedsys" 16 px, VGASYS.FON "System" 13 px,
SERIFF.FON "MS Serif" 13 px, 8514FIX.FON([FreeType 비트맵 및 Windows FNT 지원](#ref-freetype) 참고).

    python3 tools/mkfont.py VGAFIX.FON $OUT/fon.svf --size 16 --bpp 1 --unicode ascii

는 `--unicode 의 글자가 글꼴에 하나도 없다`로 끝나고, `--unicode ascii,ksx1001-hangul`도 같다. Pillow는 "A", "B", "가"를 똑같은 notdef 글리프
하나로 그린다. maker의 `detect.scan`(업로드와 로컬 모드)은 이들에 이름을 붙이고 경로는 주지 않는다: VGAFIX.FON과
VGASYS.FON은 "Windows FON face 0; no Unicode character map, mkfont cannot read it"(크기 [16]과 [13]), MODERN.FON은 "Windows FON; no openable
face". 맨 Windows `.FNT`도 같은 식으로 붙는다("Windows FNT; no Unicode character map, mkfont cannot read it"). 지원하지 않는 것으로 다루거나
먼저 변환하라. 한글 글리프가 있는
Windows FNT나 FON은 찾지 못했다. Windows 95 한글판 디스크에는 라틴과 OEM 폰트(Fixedsys, System, Terminal, MS Serif, MS Sans Serif, Courier,
Small Fonts; FON 25개)뿐이고, 그 시스템의 한글 글리프는 TrueType이다(`gulim.ttc`, 스트라이크 포함: [내장 비트맵 스트라이크](#내장-비트맵-스트라이크)).
FON은 외부 도구로 먼저 BDF로 변환해야 하며, 그 변환기는 제공하지 않는다.

자모 조각 폰트인 DOS Johab `.FNT` 파일과 혼동하지 말 것: [DOS 시대 원시 폰트](#dos-시대-원시-폰트)를 참고한다.

<a id="내장-비트맵-스트라이크"></a>

### 4.6. 내장 비트맵 스트라이크

내장 비트맵이 있는 아웃라인 폰트(TrueType `bdat`/`bloc`, OpenType `EBDT`/`EBLC`)는 FreeType이 스트라이크 자신의 픽셀 크기에서만 쓴다.
스트라이크의 크기로 `mkfont.py --size N`과 `--bpp 1`을 실행한다. 다른 크기에서는 윤곽선을 쓰고, 비트맵 전용 폰트는 열기가 실패한다
(`OSError: invalid pixel size`). maker의 `detect.bitmap_strikes`가 폰트의 스트라이크를 나열해 크기로 제공한다. 실제 폰트 두 개로 실행했다([OpenType 글리프, 셰이핑, 비트맵 스트라이크](#ref-opentype) 참고).

*Seoul*, Mac OS 7.6.1 한글판 CD의 폰트(`Font Folder/Seoul[FFIL]`, Apple Korea / Elex, 독점; 스트라이크 9, 10, 12, 14, 16, 18, 20, 24 ppem,
[Mac 형식 TrueType](#mac-형식-truetype) 참고): `macsfnt.py extract`와 `unicode` 뒤에 `mkfont.py --size 16 --bpp 1
--unicode ascii,ksx1001-hangul`은 스트라이크의 픽셀을 쓴다(`124,868 바이트`, 잉크 346). `--size 17`에서는 윤곽선을 그린다.
같은 CD에 있는 같은 패밀리의 비트맵 전용 사본(`CD Extras/Bitmap 서체 설치/Seoul/Seoul[FFIL]`, 2,626,404 바이트, `bdat` + `bloc` + `bhed`,
`glyf` 없음, maker 종류 `bitmap`, 크기 [9, 10, 12, 14, 16, 18, 20, 24])는 16 px(`124,868 바이트`), 12 px(`105,972 바이트`), 24 px(`219,116 바이트`)에서
같은 글리프 바이트를 주고, `--size 17`은 `폰트를 17px 로 열 수 없다: invalid pixel size`로 멈춘다. `head`가 없어(대신 Apple의 `bhed`)
Pillow는 모든 advance를 0으로 재지만, `mkfont.py`가 글리프마다 스트라이크 자체의 메트릭에서 advance를 가져오므로 비트맵 전용 사본도 전체 폰트처럼 구워진다:
16 px `width=156 ascent=13 descent=3`, 잉크 346, `fontmetrics.py`는 모든 글리프가 advance 안에 있다고 알린다. 12 px `width=111 ascent=10
descent=2`, 잉크 252.

*굴림*(Gulim), Windows의 폰트(`GULIM.TTC`, Microsoft와 한양정보통신, 독점; `EBLC` 스트라이크 11~25 ppem):

    python3 maker/srcprep.py ttc-face GULIM.TTC $OUT/Gulim.ttf --index 0
    python3 tools/mkfont.py $OUT/Gulim.ttf $OUT/gu16.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul

16 px `125,288 바이트`, 글리프 2,446개, `width=149 ascent=14 descent=2`, 잉크 371. 12 px `106,208 바이트`, `width=114 ascent=10
descent=2`, 잉크 298. `svf2to3.py --profile default --check`는 두 크기 모두 그대로 둔다. 스트라이크가 없는 크기(26)는 윤곽선을 래스터화하고
(`202,144 바이트`), `--bpp 2`는 스트라이크 크기에서도 윤곽선을 쓰므로(16 px: `182,604 바이트`) `--bpp 1`만 스트라이크의 픽셀을 준다. 추출한 폰트에
`detect.scan`을 쓰면 종류 `outline-composite`, 레이블 "TTF; bitmap strikes 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25", 크기 [16], 경로 `mkfont`,
`composite`, `vector fit`을 준다.

<a id="dos-시대-원시-폰트"></a>

## 5. DOS 시대 원시 폰트

DOS 한글 시스템(한글 BIOS, 이야기, 한메, san, 도깨비, 게임)은 음절이 아니라 자모 조각을 저장했다. 음절은 초성, 중성, 선택적인
종성의 OR이었고, 어느 벌을 쓸지는 다른 자모가 정했다. 도구는 이 원시 파일을 **정확한 바이트 크기**로(maker의 `detect.py`도
마찬가지이며, 목록에 없는 크기의 파일은 "unknown"이다) 그리고 레이아웃으로 읽는다. 냄새로 알아볼 헤더는 없다.

<a id="그-밖의-dos-시대-한글-폰트"></a>

### 5.1. 그 밖의 DOS 시대 한글 폰트

| `--layout` | 파일 | 바이트 | 조각 |
|---|---|---|---|
| `844` | 원시 8x4x4 (`HANGUL.FNT`, `*.KOR`, `$K*ZN16`), 16/24/40/48 px | 11,520 (2 바이트 헤더가 있으면 11,522), 25,920, 72,000, 103,680; 15,584 (DKB2, 16 px로 읽음) | 360: 초성 8벌(각 20), 중성 4벌(각 22), 종성 4벌(각 28); 각 벌의 슬롯 0은 빈 칸 |
| `844-ihnm` | SAGA IHNM 8x4x4 (중성 벌이 ㄱ ㅋ에 맞게 바뀜) | 11,520+ | 360 |
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
조합한 결과 = 원시 슬롯 1과 161의 OR, 바이트 단위로 동일), 6x2x1 폰트(초성 클래스 1개 / 종성 클래스 2개, 벌 6/2/1), 완성형
페이스의 재맞춤(NEODG16J에 `--from-svf`, IoU 1.000).

실제 폰트로 실행(2026-11-22. 모든 줄에 `--symbols --check`, 이름이 있는 곳에는 `--eng`. 샘플 줄은 `안녕하세요 ABC 123`, "잉크"는 렌더 점검의 수.
`--eng`를 줄 때만 ASCII가 그려지므로 주지 않은 페이스는 음절 다섯 개를 잰다):

| `--layout` | 원본(폰트, 제품; 따로 적지 않으면 독점) | 결과 |
|---|---|---|
| `844` | GOTHIC16.FNT, 11,520 바이트(태백 3.5.1 고딕 16), 같은 패키지의 `--eng ROMAN16.FNT` | `15,756 바이트`, 조각 344개, 글리프 441개, `johab844.py`의 음절과 동일. `width=144 ascent=14 descent=2`, 잉크 566 |
| `844` | TBG1.FNT, 2 바이트 헤더가 붙은 11,522 바이트(T-Hangul, 초기 태백), `--eng ROMAN16.FNT` | `15,712 바이트`, 같은 조각 344개, 잉크 566 |
| `844` | DKBBM.FNT, 15,584 바이트(한글 도깨비 B 명조), `--eng ROMAN16.FNT` | `15,744 바이트`, 글리프 441개, `johab844.py`와 동일. 잉크 512 |
| `844` | MHANC24.PFT, 25,920 바이트(태백 3.5.1 명조 24 px), `--eng MASCII24.PFT`(12,288 바이트, 12x24 영문 폰트) | `23,088 바이트`, 조각 344개. `width=216 ascent=20 descent=4`, 잉크 916 |
| `844` | GHANC40.PFT, 72,000 바이트(태백 3.5.1 고딕 40 px), `--eng GASCII40.PFT`(30,720 바이트, 20x40 영문 폰트) | `42,716 바이트`, 글리프 441개. `width=360 ascent=34 descent=6`, 잉크 3,078 |
| `844` | GHANC48.PFT, 103,680 바이트(태백 3.5.1 고딕 48 px), `--eng GASCII48.PFT`(49,152 바이트, 24x48) | `51,972 바이트`. `width=432 ascent=40 descent=8`, 잉크 3,921(`line 440 56 0 48`: 줄이 400보다 넓다) |
| `844` | MHANC48.PFT, 103,680 바이트(태백 3.5.1 명조 48 px), `--eng MASCII48.PFT`(49,152 바이트) | `54,112 바이트`. `width=432 ascent=40 descent=8`, 잉크 3,573(`line 440 56 0 48`) |
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
이상의 원본에는 거기에 맞는 영문 폰트나 `--base`가 필요하다. `--eng`는 8x16 폰트와 같은 패키지의 12x24, 20x40(30,720 바이트),
24x48(49,152 바이트) PFT 영문 폰트를 받아 셀에 맞게 정수배로 키운다. 데스크톱 앱은 40, 48 px 페이스에 같은 높이의 영문 폰트를, 같은
계열(G / M)을 먼저 짝짓는다.

<a id="hwp-1x와-2x-폰트"></a>

### 5.2. HWP 1.x와 2.x 폰트

한글과컴퓨터의 DOS 워드프로세서는 자체 비트맵 폰트를 실었다. `tools/hwpfont.py`가 이것을 읽는다. HWP 1.x `.SFT`(화면)와
`.PFT`(프린터), HWP 3.0 `.FNT`([아래](#hwp-30-fnt-폰트))를 읽어 유니코드 BDF로 쓰고, `jamoset.py --layout hwp1`은 HWP 1.x 한글
페이스를 HWP 자체의 조합 규칙 그대로 자모 세트로 만든다. 형식은 johab-fonts 연구 노트에서 왔고(거기서 HWP.EXE를 바이트로만 읽었으며
실행한 적은 없다), 전체는 `hwpfont.py`의 docstring에 있다.

- HWP 1.x(1989-1990): 32 바이트 "HWP Font Editor v1.0" 헤더(`HPFT3.LZH`의 `HANGUL3.PFT`는 대신 "FE"), 0x1C에 글리프 수(빅엔디언 16비트),
  0x1E에 (폭 - 1, 높이 - 1), 그다음 글리프. 파일 크기는 정확히 32 + 글리프 수 x 글리프 바이트이다. 화면 폰트(16행)는 행 우선,
  프린터 폰트(24행, 24핀 헤드)는 열 우선이며 한 열이 3 바이트, MSB가 위다.
- `HANGUL.SFT`(16x16, 글리프 1,193개)와 `HANGUL1/2/3.PFT`(24x24, 980개)는 페이스 셋을 담는다(HWP의 스타일 0, 1, 2: 메뉴 순서로 명조,
  고딕, 샘물. 증명되지는 않았다). 페이스는 초성, 중성, 종성 조각 벌(한 벌에 조각 31, 29, 31개)로 되어 있다. SFT는 10/4/4, 7/2/2,
  6/2/2 벌, PFT는 7/2/3, 7/2/2, 5/2/2 벌.
- `ASCII.SFT`(8x16)와 `ASCII.PFT`(14x24): 글리프 991개. 다른 글리프 109개 다음에 코드 0x20-0xB2의 페이스 여섯(명조, 고딕, 위첨자,
  아래첨자, 이탤릭, 필기체). `HANJA.SFT`: KS X 1001 한자 4,888자. 기호 파일(`SPECIAL1/2`, `JAPAN`, `USER1/2`, `SYSTEM.PFT`)은
  알아보지만(`hwpfont.py info`) 변환하지 않는다.

**맞춤이 아니라 자모 세트.** HWP.EXE는 음절을 조각 셋의 OR로 조합하며, 그 벌을 초성의 부류(ㄱ ㅋ 또는 나머지), 종성 유무,
중성의 모양 부류로 고른다. 이것은 JSET 방식의 벌 규칙이고, 부류 2 x 2와 많아야 10/4/4 벌라서 표준 JSET 한도에 그대로 들어간다.
`--layout hwp1`은 고른 페이스(`--face 0..2`)의 HWP.EXE 표를 그대로 쓰고, 모든 음절이 비트 단위로 똑같이 조합된다. `--check`는 쓴
페이스에서 음절 11,172개를 모두 조합해, HWP의 표를 통해 조각을 직접 읽는 `hwpfont.py` 자체의 조합과 하나씩 비교한다. 그러므로
자모 세트가 이 폰트들의 본래 형태이다(16 px에서 약 120 KB 대신 10-18 KB). 같은 음절의 완성형 페이스는 `hwpfont.py bdf`와
`mkfont.py`로 만든다(maker의 `hwp bdf + mkfont`). HWP가 옛한글용으로 둔 조각(초성 20-31, 중성 22-29, 종성 28-31)은 유니코드의 현대 한글 완성형
음절에 속하지 않아 빠진다.

    python3 -I tools/hwpfont.py info HANGUL.SFT
    python3 -I tools/jamoset.py --layout hwp1 --face 1 HANGUL.SFT --eng ASCII.SFT --check -o $OUT/HWPS1J.SVF
    python3 -I tools/hwpfont.py bdf HANGUL1.PFT --face 1 --ascii ASCII.PFT -o $OUT/hwp24.bdf
    python3 tools/mkfont.py $OUT/hwp24.bdf $OUT/hwp24.tmp --size 24 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/hwp24.tmp $OUT/HWP24.SVF --profile default

`--eng`(jamoset.py)와 `--ascii`(hwpfont.py)는 HWP 영문 파일을 그대로 받는다. `--eng-face N` / `--ascii-face N`이 따로 말하지
않으면 여섯 페이스 중 0번이다. 전에 `--eng`가 읽던 영문 폰트도 모두 받는다. `hwpfont.py bdf --syllables all`은 HWP 1.x 페이스의
KS X 1001 음절 2,350자 대신 11,172자를 모두 쓴다. 완성형 BDF는 영문 페이스의 기준선을 ascent로 삼는다(`ASCII.SFT`는 12,
`ASCII.PFT`는 20. `--ascent`로 바꾼다). `jamoset.py`는 다른 DOS 폰트와 같이 16 px 셀의 8x16 영문 폰트를 7/8(ascent 14)에 놓는다.

DOS용 HWP 1.20(한글과컴퓨터, 1989-1990; archive.org `hwp-120`; 독점)으로 2026-11-23에 실행했다. 영문 폰트는 같은 폴더의 것, 페이스 0:

| 원본 | 명령 | 결과 |
|---|---|---|
| `HANGUL.SFT`(38,208 바이트), 페이스 0 / 1 / 2, `--eng ASCII.SFT` | `jamoset.py --layout hwp1 --face N --check` | `16,996` / `11,188` / `10,468 바이트`, 조각 382 / 229 / 210개(벌 10/4/4, 7/2/2, 6/2/2); `width=144 ascent=14 descent=2`, 잉크 497 / 403 / 363 |
| `HANGUL1.PFT`(70,592 바이트), 페이스 0 / 1 / 2, `--eng ASCII.PFT` | 위와 같음 | `18,224` / `16,712` / `14,252 바이트`, 조각 256 / 229 / 191개; `width=232 ascent=20 descent=4`, 잉크 886 / 886 / 818 |
| `HANGUL.SFT` 페이스 1과 `ASCII.SFT` | `hwpfont.py bdf --face 1`, `mkfont.py --size 16`, `svf2to3.py` | `122,440 바이트`, 음절 2,350자; `width=144 ascent=12 descent=4`, 잉크 403 |
| `HANGUL1.PFT` 페이스 1과 `ASCII.PFT` | 같은 명령, `--size 24` | `218,748 바이트`; `width=232 ascent=20 descent=4`, 잉크 886 |

자모 줄마다 `hwp1: 11172 syllables identical to the HWP 1.x rule (hwpfont.py)`가 찍혔다. `tools/test_hwpfont.py`는 `JOHAB_FONTS`로 선택 원본 파일을 제공하면 기록된 음절 해시도 점검한다.

DOS용 HWP 2.x는 폰트를 `.HFT` 파일로 둔다(아래). HWP 2.x 화면 폰트 가운데 평범한 원시 8x4x4인 것은 한글 2.1 PRO 디스크(13번)의
`HMJ.FNT`(11,520 바이트) 하나이며 다른 `844` 폰트처럼 읽힌다. `python3 tools/jamoset.py --layout 844 HMJ.FNT --eng ROMAN16.FNT --check
-o $OUT/HMJ.SVF`는 `15,700 바이트`를 쓰고 음절 11,172개를 모두 조합하며 `johab844.py`와 동일하다.

**읽지 않는 것:** HWP 2.0("HWP 2.0 font file" 헤더), 2.1, 3.0("Han Unified Font File 1.0"; HWP 3.0 CD의 `HNC/FONT`에 160개)의
`.HFT` 폰트. 헤더를 살펴보았다. 비트맵이 아니라 크기 조절이 되는 윤곽선 또는 획 폰트이며(HWP 2.0 헤더는 1,200 단위 정사각형을
적는다), 여기에는 그것을 해독하는 도구가 없다. HWP 1.x 기호 파일은 목록에만 나오고 변환하지 않는다. `HANJA.SFT`(와 HWP 3.0의
`HAJ16_0.FNT`)는 한자 4,888자를 유니코드 코드 포인트에 둔 BDF가 되지만(`hwpfont.py bdf`), maker는 이를 한글 페이스 경로로 제공하지 않는다. `mkfont.py --unicode ksx1001`로 BDF의 한자를 고를 수 있다.

**maker**(로컬 모드에서만. Mac 폰트와 같이 업로드 작업은 HWP 파일마다 "HWP font: not converted here (local-only mode)"로 보인다)는
HWP 1.x 한글 파일을 페이스마다 하나씩 `hwp1` 항목 셋으로("HWP 1.x Hangul (printer .PFT, 24x24), face 1 of 3 (Gothic by HWP's menu
order)") 경로 `hwp1`(자모, native)과 `hwp bdf + mkfont`(완성형)와 함께 보이고, 영문 파일은 라틴 짝으로("HWP 1.x English (--eng,
14x24; face 0 of 6)") 보인다. 이 짝은 HWP와 KS 페이스에만 주어진다(DOS 원시 폰트의 경로는 원시 영문 폰트를 읽는다). 다른 파일은 `other`이다("HWP 1.x font: 4888 hanja of 16x16, not a Hangul face"). 위 파일의 사본에
`detect.scan(..., local=True)`와 `routes.routes`를 돌리고 모든 경로의 명령을 실행해 확인했다(2026-11-23). `hwp1` 경로는 표의
16,712 바이트 페이스를, `hwp bdf + mkfont`는 218,748 바이트 페이스를 쓴다.

<a id="hwp-30-fnt-폰트"></a>

### 5.3. HWP 3.0 FNT 폰트

DOS용 HWP 3.0(1995; CD의 `HNCAPP/HDR30/FONT`)은 비트맵 폰트를 72 바이트 헤더가 붙은 `.FNT` 파일로 둔다. "FNT" 01, 형식 바이트(0 영문,
1 한글, 2 한자), 01, 6과 8에 폭과 높이(리틀엔디언 16비트), 0x10에 글리프 수(32비트), 0x14에 조합형으로 된 폰트 이름("고딕체 16*16"),
그다음 행 우선 글리프. 한글 FNT는 KS X 1001 음절 2,350자를 코드 순서로, 가부터 완성형으로 담는다. 16 px 파일(`HAN16_*.FNT`,
86,792 바이트)은 그 뒤에 나머지 음절을 위한 360개짜리 8x4x4 자모 조각 벌을 더 두며, `jamoset.py --layout 844-hwp3`가 그것을
읽는다(채움 슬롯을 점검하고, `--check`는 `johab844.py`와 같다). `HAN24_*` / `HAN40_0` / `96MT`는 2,350자만 담는다(HAN24의 헤더는
그래도 2,710이라고 센다). 영문 FNT는 0x20부터의 코드를 담는다(글리프 147개; `ENG40_0`은 96개).

    python3 -I tools/hwpfont.py bdf HAN16_0.FNT --ascii ENG16_3.FNT -o $OUT/han16.bdf
    python3 tools/mkfont.py $OUT/han16.bdf $OUT/han16.tmp --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/han16.tmp $OUT/HAN16.SVF --profile default
    python3 -I tools/jamoset.py --layout 844-hwp3 HAN16_0.FNT --eng ENG16_3.FNT --check -o $OUT/HAN16J.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/HAN24.SVF --mask-font none --check -o $OUT/HAN24J.SVF

DOS용 HWP 3.0 CD(한글과컴퓨터, 1995; archive.org `hwp-30-dos`; 독점)로 2026-11-23에 실행했다. 완성형 페이스는 `hwpfont.py bdf`,
셀 크기의 `mkfont.py`, `svf2to3.py --profile default`로 만들었다:

| 원본 | 명령 | 결과 |
|---|---|---|
| `HAN16_0.FNT`("고딕체 16*16"), `--ascii ENG16_3.FNT`("고딕체 8*16") | 완성형 | `115,112 바이트`, 음절 2,350자; `width=144 ascent=12 descent=4`, 잉크 523 |
| 같은 파일, `--eng ENG16_3.FNT` | `jamoset.py --layout 844-hwp3 --check` | `15,432 바이트`, 조각 344개, `johab844.py`와 동일; `width=144 ascent=14 descent=2`, 잉크 523 |
| 완성형 `HAN16_0` 페이스 | `jamoset.py --layout 844 --from-svf --mask-font none` | `16,308 바이트`, IoU 0.994(2,350자 중 2,166자 정확) |
| `HAN16_1` / `_2` / `_3` / `_4`(명조체, 샘물체, 필기체, 모양체), `--ascii ENG16_0.FNT` | 완성형 | `118,020` / `122,100` / `123,468` / `115,272 바이트`; 잉크 496 / 363 / 521 / 501 |
| `HAN24_0.FNT`("고딕체 24*24", 169,272 바이트), `--ascii ENG24_0.FNT`(12x24) | 완성형 | `218,472 바이트`; `width=216 ascent=22 descent=2`, 잉크 972 |
| `HAN24_1.FNT`("명조체 24*24"), `--ascii ENG24_0.FNT` | 완성형 | `220,044 바이트`, 잉크 984 |
| `HAN40_0.FNT`("명조체 40*40", 470,072 바이트), `--ascii ENG40_0.FNT`(20x40) | 완성형 | `492,420 바이트`; `width=360 ascent=34 descent=6`, 잉크 2,289 |
| `96MT.FNT`("문화부 바탕체 96*96", 2,707,272 바이트), 영문 폰트 없음 | 완성형, `--size 96` | `2,154,232 바이트`, 음절 2,350자 모두; `width=576 ascent=84 descent=12`, 잉크 6,058(`line 576 104 0 96`. BDF의 빈 U+0020이 48씩 나아간다) |
| `HAN24_0` / `HAN40_0` 페이스 | `jamoset.py --layout 844 --from-svf --mask-font none` | `28,928` / `64,904 바이트`, IoU 0.819 / 0.687 |

16 px FNT의 음절 2,350자가 모두 그 자모 세트의 조합인 것은 아니다. 8x4x4 자모 세트가 조합하는 것과 같은 음절은 2,083자(`HAN16_0`),
1,788자(`_1`), 2,221자(`_2`), 375자(`_3`, 필기체), 1,700자(`_4`)이고 나머지는 통째로 그렸다. 그러니 2,350자는 완성형 페이스가
더 낫고, 11,172자 전체는 자모 세트로 간다. maker(로컬 모드)는 한글 FNT를 `ks-raw`("HWP 3.0 FNT Hangul 16x16: 2,350 KS X 1001
syllables + an 8x4x4 jamo set")로 `hwp bdf + mkfont`, `hwp3 844`(16 px 파일만), 실험적인 `hwp bdf + from-svf fit`과 함께 보이고,
영문 FNT는 라틴 짝("HWP 3.0 English (--eng, 12x24)")으로 보인다. `HAJ16_0.FNT`는 `other`이다.

<a id="ks-x-1001-원시-덤프"></a>

### 5.4. KS X 1001 원시 덤프

KS X 1001 완성형 음절 2,350자의 원시 덤프(일부 DOS와 임베디드 시스템이 하듯 코드 순서로 음절마다 비트맵 하나, 행 우선, 헤더
없음)는 `hwpfont.py`가 크기로 읽는다. 2,350 x 16, 24, 32, 40, 48 px 정사각형 글리프의 바이트 수(75,200, 169,200, 300,800,
470,000, 676,800 바이트)이고, 첫 글리프와 마지막 글리프에 잉크가 있으며 서로 달라야 한다. 덤프를 유니코드 BDF로 쓰고, `--eng`가
읽는 어떤 영문 폰트의 ASCII든 함께 넣는다. maker는 그런 파일을 `ks-raw`("KS X 1001 raw dump Hangul 24x24: 2,350 KS X 1001 syllables",
DOS 원시 폰트를 크기로 읽듯 업로드와 로컬 모드 모두)로 `hwp bdf + mkfont`와 실험적인 `hwp bdf + from-svf fit`과 함께 보인다.
`jamoset.py --layout 844`는 여전히 거부한다(`size 169200 is not an 8x4x4 size`). 덤프는 완성형이고, 그 자모 세트는 맞춤이다.

    python3 -I tools/hwpfont.py bdf GHAN24.PFT --ascii GASCII24.PFT -o $OUT/ghan24.bdf
    python3 tools/mkfont.py $OUT/ghan24.bdf $OUT/ghan24.tmp --size 24 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/svf2to3.py $OUT/ghan24.tmp $OUT/GHAN24.SVF --profile default
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/GHAN24.SVF --mask-font none --check -o $OUT/GHAN24J.SVF

태백 3.5.1(`FNT/`, 독점)로 2026-11-23에 실행했다. 각각 같은 계열과 높이의 영문 폰트를 썼다:

| 원본 | 결과 |
|---|---|
| `GHAN24.PFT`(고딕 24 px, 169,200 바이트), `--ascii GASCII24.PFT`(12x24) | `216,192 바이트`, 음절 2,350자; `width=216 ascent=20 descent=4`, 잉크 1,133; 자모 세트 `33,428 바이트`, 조각 344개, IoU 0.710, 잉크 1,096 |
| `MHAN24.PFT`(명조 24 px), `--ascii MASCII24.PFT` | `213,812 바이트`; `width=216 ascent=20 descent=4`, 잉크 907; 자모 세트 `31,664 바이트`, IoU 0.623 |
| `GHAN40.PFT`(470,000 바이트), `--ascii GASCII40.PFT`(20x40) | `487,808 바이트`; `width=360 ascent=34 descent=6`, 잉크 3,112 |
| `GHAN48.PFT`(676,800 바이트), `--ascii GASCII48.PFT`(24x48) | `663,328 바이트`; `width=432 ascent=40 descent=8`, 잉크 3,926(`line 440 56 0 48`) |

맞춤이 나쁜 것(IoU 0.710)은 페이스가 조각의 OR이 아니라 음절 통째의 디자인이라서다. `hwpfont.py`가 생기기 전 `rawcarve.py`로
잘라 낸 BDF에서도 같은 IoU가 나왔다. `rawcarve.py bdf --dense`는 여전히 더 큰 파일 안에 든 덤프를 잘라 내고(`--offset`), 94 x 94 표
전체의 덤프는 그 대신 `--grid 0xA1,0xA1,94`를 쓴다([OS/2 한글 폰트](#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기)):

    python3 -I tools/rawcarve.py bdf GHAN24.PFT --glyph 24x24 --chars ks-hangul --dense --ascent 22 -o $OUT/ghan24.bdf

<a id="claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기"></a>

## 6. Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기

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
`jamoset.py --layout 844`로 간다([그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트)). 두 도구는 바이트만 읽고 파일의 코드를
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

### 6.1. 프롬프트

파일 하나에 대해 Claude(또는 여기서 명령을 실행할 수 있는 어시스턴트)에게 줄 내용이다. 꺾쇠 안은 직접 채운다:

```
Find the Hangul (and English) bitmap font inside <FILE> (<what it is: a 1989 DOS Hangul TSR / a Korean VGA BIOS and
its font ROM / ...>), cut it out and build SVF faces from it with the tools of this repository (docs/recipes.md,
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
   NAMED_RANGES['ksx1001-hangul'] as in docs/recipes.md, KS C 5601 BDF and PCF; WxH = the font's cell) then
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

### 6.2. NKP: 조각을 잘라 저장한 허큘리스 한글 TSR

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

### 6.3. 도깨비: 드라이버 안의 폰트

원본: 한글 도깨비 B 배포본(`dkbb.rar`. 드라이버 소스 DKBB.ASM과 DKBBG.FNT / DKBBM.FNT가 함께 있다, 독점)에 든 한글 도깨비 B 드라이버 DKBB.COM(22,035 바이트)과 DKBII.COM(20,355 바이트).
따로 된 DKBBG.FNT는 [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트)에서 읽는다. 여기서는 드라이버 자체에서 폰트를 꺼낸다.

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

<a id="한글-vga-폰트-rom-86box"></a>

### 6.4. 한글 VGA 폰트 ROM (86Box)

원본: 86Box ROM 묶음(https://github.com/86Box/roms, 2026-11-14의 커밋 1ac40f2). 파일별로 내려받았고 url, 바이트, sha256을 파일
곁에 적었다. 그 트리에는 한글 VGA 카드가 셋 있고, 각각 32 KB VGA BIOS와 512 KB
KS C 5601 폰트 ROM이다: 삼보 트라이젬 한글 VGA(ET4000, `video/et4000/tgkorvga.bin`, `tg_ksc5601.rom`), 가산 ET4000(`et4000_kasan16.bin`,
`kasan_ksc5601.rom`), ATI 28800 한글(`video/ati28800/atikorvga.bin`, `ati_ksc5601.rom`). 그 밖의 한국 항목은 한글 폰트가 없는 기계 BIOS다
(삼성 Deskmaster 286, 현대 Super-16T, LG IBM, 트라이젬 286M / 486G). ROM은 독점 칩의 덤프다([86Box 한글 VGA ROM 메타데이터와 렌더링](#ref-86box) 참고).

    python3 -I tools/binscan.py info tg_ksc5601.rom      # 524288 bytes; size = 16384 x 32 B: 16,384 slots
    python3 -I tools/binscan.py render tg_ksc5601.rom --offset $((0x1821*32)) --glyph 16x16 --order strips --count 4

32 바이트 슬롯 16,384개는 128 x 128 격자다. 에뮬레이터 자신의 소스(`src/video/vid_svga_render.c`)가 `((lead & 0x7F) << 7) | (trail &
0x7F)`로 색인하고, 왼쪽 8 픽셀은 바이트 `scanline`, 오른쪽은 `scanline + 16`으로 그린다. 16행짜리 8 픽셀 스트립 두 개다(`--order
strips`). 가(B0A1)는 슬롯 0x1821이며, 세 ROM 모두 렌더가 가 각 간 갇을 보인다(디자인은 셋이 다 다르다). 영문 폰트는 BIOS의 8x16 VGA
폰트다:

    python3 -I tools/binscan.py ascii tgkorvga.bin                   # offset 0x4a2d, edge 3 (Kasan 0x499a, ATI 0x4d59)
    python3 -I tools/rawcarve.py bdf tg_ksc5601.rom --glyph 16x16 --order strips --chars ks-hangul \
        --grid 0x80,0x80,128 --ascent 12 -o $OUT/tg-hangul.bdf
    python3 -I tools/rawcarve.py bdf tgkorvga.bin --offset 0x4a2d --glyph 8x16 --chars ascii --ascent 12 -o $OUT/tg-ascii.bdf
    python3 tools/bdfface.py --hangul $OUT/tg-hangul.bdf --ascii $OUT/tg-ascii.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/TGVGA16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/TGVGA16.SVF --mask-font none --check -o $OUT/TGVGA16J.SVF

두 BDF에 모두 `--ascent 12`를 주면 ROM의 셀이 그대로 유지된다(VGA 폰트의 대문자는 11행에서 끝난다). 결과(각 페이스 글리프 2,447개,
모든 줄이 `width=144 ascent=12 descent=4`):

| ROM | 완성형 | 잉크 | 8x4x4 자모 세트 | IoU (2,350 중 정확) | 잉크 |
|---|---|---:|---|---|---:|
| 트라이젬 (`tg_ksc5601.rom` + `tgkorvga.bin`) | `122,392 bytes` | 476 | `17,172 bytes` | 0.968 (1,576) | 476 |
| 가산 (`kasan_ksc5601.rom` + `et4000_kasan16.bin`) | `124,968 bytes` | 557 | `18,576 bytes` | 0.872 (290) | 566 |
| ATI (`ati_ksc5601.rom` + `atikorvga.bin`) | `123,188 bytes` | 517 | `17,596 bytes` | 0.919 (644) | 517 |

ROM에는 KS X 1001 표 전체가 있다. `--chars ks-nonhanja`는 기호와 자모를, `ks-all`은 한자까지 더한다(BDF를 그대로 두는 `mkfont.py`용.
`bdfface.py`는 음절과 ASCII만 남긴다). `rawcarve.py eng tgkorvga.bin --offset 0x4a2d`는 같은 영문 폰트를 원시 `--eng` 파일로 준다.

확인한 다른 ROM 묶음: openMSX 시스템 ROM 묶음(file-hunter의 RomDB, 파일 1,241개)에는 한글 폰트가 셋 있다. 대우 MSX2 SUB-ROM의
자모 세트 폰트, CPC-400S의 256 KB 완성형 폰트, 한국 MSX1 BIOS의 8x8 자모 셀이다. 한글 BASIC ROM(`cpc-300_hangul`, `dpc-200_hangul`)에는
드라이버만 있고 글리프는 없다([한국 MSX 폰트](#한국-msx-폰트-msx2와-msx1)). 88emuplayer ROM 묶음(`88emuplayer-roms.zip`)에는 Roland 음원 모듈 ROM(SC-55, SC-88, SC-8850, CM-300)만 있고 폰트는
없다. MAME 롬셋은 [MAME 세트의 한글 폰트 ROM](#mame-세트의-한글-폰트-rom)에 있다.

데스크톱 앱은 세 쌍을 크기와 SHA-256으로 알아본다(내장 레시피 `maker/recipes/86box-tgkorvga.json`, `86box-kasan16.json`,
`86box-atikorvga.json`: 이름, 크기, 해시, 오프셋만 있고 ROM의 바이트는 없다). 두 파일이 든 폴더를 고르면 글꼴 ROM이 한 행이 되어
페이스 `TGVGA16` / `KASAN16` / `ATIVGA16`(경로 `bdfface`)과 자모 세트 `TGVGA16J` / `KASAN16J` / `ATIVG16J`(`bdfface + from-svf fit`,
experimental)를 위의 명령으로 만든다. `SVF_MAKER_REAL_86BOX`가 내려받은 파일을 가리키게 하고 실행하면(`maker/test/test_recipe.py`)
표의 모든 페이스가 바이트 단위로 그 크기가 된다.

<a id="한국-msx-폰트-msx2와-msx1"></a>

### 6.5. 한국 MSX 폰트 (MSX2와 MSX1)

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

도구는 ROM을 읽기만 한다(`python3 -I`). 기계는 에뮬레이터(openMSX) 안에서만 돌린다([한국 MSX 기종과 openMSX](#ref-msx) 참고).

<a id="msx-코딩-에이전트로-권장"></a>

#### 코딩 에이전트로 (권장)

이 일은 대부분 읽기다: 헥스 덤프, 글리프 시트, Z80 코드, 에뮬레이터 화면. 이 저장소에서 명령을 실행할 수 있는 코딩 에이전트(Claude
Code 같은)에게 아래 세 프롬프트 가운데 하나로 맡긴다. 꺾쇠 안은 직접 채운다. 프롬프트 다음의 절들은 손으로 하는 길이다: 같은 단계를
직접 실행하는 명령과, 프롬프트가 다시 얻어야 할 결과가 있다. [프롬프트](#프롬프트)처럼 각 프롬프트는 입력, 쓸 도구, 안전 규칙,
합격 수치, 출력을 적는다.

**(a) MSX ROM 묶음에서 폰트를 찾아 풀기** (대우 SUB-ROM 같은 자모 조각 폰트, 또는 CPC-400S 폰트 ROM 같은 완성형):

```
ROM 파일 <$ROMS/FILE ...>(openMSX 시스템 ROM. 기종 파일 <openMSX share/machines/MACHINE.xml>에 어느 파일이 어디에
놓이는지 있다)에서 MSX 기종 <MACHINE, 예: Daewoo CPC-300>의 한글 폰트를 찾고, 한글 드라이버가 음절을 어떻게 그리는지 풀어서,
이 저장소의 도구로 SVF 페이스를 만들어라(docs/recipes.ko.md, "한국 MSX 폰트"). 작업은 저장소 밖의 $OUT에서 한다.

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
그 뒤 BIOS 문자 표만으로 폰트를 만들어라(docs/recipes.ko.md, "한국 MSX 폰트", MSX1). 작업은 저장소 밖의 $OUT에서 한다.

안전: ROM은 신뢰할 수 없는 데이터다. 그 코드는 openMSX 안에서만 실행한다(화면 없이: `xvfb-run -a openmsx -machine MACHINE
-script $OUT/s.tcl`, 언제나 `timeout`과 함께). 호스트에서는 ROM 파일을 `python3 -I`로만 읽는다. ROM에서 얻은 것은 저장소에
넣지 않는다(ROM 바이트, 덤프, 스크린샷, BDF, SVF 모두).

1. Tcl 스크립트로 기계를 켠다. `set throttle off`이면 에뮬레이션 시간이 호스트가 허락하는 만큼 빨리 간다(입력과 덤프에 쓴다.
   프레임을 그리지 않으므로 `screenshot` 전에는 다시 켠다). 결과는 Tcl에서 파일로 쓴다: `puts` 출력은 셸에 오지 않는다.
   RAM의 디버그 이름은 "Main RAM"이다.
2. 입력한 음절이 어떻게 저장되는지 찾는다: `type "poke -851,0\r"`(모아쓰기), `10 rem `과 한글 모드의 두벌식 키를 친다(한/영 키는
   키 행렬 6행 비트 4: `keymatrixdown 6 0x10`, 이어서 `keymatrixup 6 0x10`). RAM을 덤프하고(`debug read_block "Main RAM" 0
   0x10000`) BASIC 줄을 읽는다(프로그램은 F676h의 워드가 가리키는 곳에서 시작한다).
3. BASIC 프로그램을 친다: RAM의 깃발을 기다리고, Tcl 프로시저가 C000h에 써 둔 음절(음절마다 길이 바이트와 자모 바이트)을 화면마다
   77자씩 LOCATE 자리에 PRINT하고(텍스트 창이 2열 안쪽에서 시작하므로 한 행에 4열짜리 칸 7개), 끝 깃발을 놓는다. 화면마다 SCREEN 1
   이름 표(`debug read_block VRAM 0x1800 768`)를, 한 번은 패턴 표(`debug read_block VRAM 0 2048`)를 덤프한다. 화면 146개가
   11,172자를 모두 덮는다. 눈으로 확인할 `screenshot`을 하나 찍는다(throttle 켬).
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
<MACHINE>의 ROM에서 풀어 낸 페이스 <$OUT/FACE.SVF>를 openMSX에서 기계가 직접 그리는 것과 대어 보라(docs/recipes.ko.md, "한국 MSX
폰트", "정답으로서의 에뮬레이터"). 작업은 저장소 밖의 $OUT에서 한다.

안전: ROM 코드는 `xvfb-run`과 `timeout` 아래의 openMSX 안에서만 실행한다. 호스트에서는 파일을 `python3 -I`로만 읽는다. ROM,
화면, 덤프에서 얻은 것은 저장소에 넣지 않는다.

1. 기계를 켜고(스크린샷에는 throttle 켬. CPC-400S는 약 20초, 다른 기종은 약 12초) 알려진 글을 그리게 한다: 펌웨어가 스스로 보이는
   화면(CPC-300의 MSX-TUTOR), 또는 음절 PRINT를 `type`한다(대우 MSX2: 한글은 SCREEN 9, 문자열은 조합형 코드, `print
   chr$(&H88)+chr$(&H61)`은 가. Tcl에서 `$`는 `\$`, `&`는 `\&`로. MSX1: `poke -851,0` 뒤 모아쓰기). 규칙이 가르는 모든 벌을 쓰는
   음절을 20자 이상 고른다(모음 종류마다 받침 있고 없음, 겹받침, 초성 ㅍ/ㅎ).
2. 그려진 것을 정확히 읽는다: 텍스트 모드는 이름 표와 패턴 표(`debug read_block VRAM ...`), 비트맵 모드(SCREEN 5-8. 대우 SCREEN 9는
   SCREEN 6 위에 만든 것)는 글이 있는 곳의 VRAM 픽셀. `screenshot -raw -size auto FILE.png`는 화면 모드에 따른 크기의 날 MSX
   화면이다(CPC-300의 MSX-TUTOR는 SCREEN 7). 그냥 `screenshot`은 크기가 바뀌고 걸러지므로 보는 데만 쓴다.
3. 같은 글을 페이스로 그리고(`svfline.py line`, 또는 jamoset.parse_svfn의 글리프 행) 기계가 쓴 자리에서 픽셀마다 비교한다.

합격: 음절마다 다른 픽셀 수, 모두 0. 아니면 차이를 보이고(두 비트맵) 페이스가 틀렸는지 비교가 틀렸는지(화면 위치, 확대,
화면 모드가 자르는 셀) 말한다. 출력: $OUT의 Tcl 스크립트, 덤프, 스크린샷, 그리고 음절과 다른 픽셀 수의 표가 든 짧은 보고.
```

#### MSX2: 대우 자모 세트 폰트(정확)

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
종성 코드는 18을 건너뛰므로 종성 벌은 받침 27개에 칸이 29개다. 폰트 블록 전체는 0x59DE .. 0x7E1E, 9,280바이트(조각 290개)다.
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

#### MSX2: CPC-400S 완성형 폰트

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
`--chars-from $OUT/ks.txt`로는 음절 2,217자, `117,976 bytes`(KS 음절 133자, 그 가운데 뷁과 힣은 ROM에 없다). 이 페이스의 8x4x4 맞춤
(`jamoset.py --layout 844 --from-svf`)은 IoU 0.794(`19,900 bytes`, 정확히 맞은 음절 83자)에 그친다. 완성형 디자인이 자모 조각으로
짜여 있지 않기 때문이다. 한자 군은 KS X 1001이 아닌 드라이버 자신의 코드(lead 바이트 D4h 이상)를 쓰며, 여기서는 뺀다.

#### MSX1: BIOS의 자모 셀을 기계처럼 배치하기

한국 MSX1 BIOS는 표준 문자 표(0x1BBF) 대신 0x1B49에 자신의 표를 둔다: 8x8 셀 256개, 0x20-0x7E에 라틴 문자, 0x86-0x98에 초성 19개,
0x99-0xA6에 모음, 0xA7-0xFB에 "ㅗ ㅛ ㅜ ㅠ ㅡ 위의 초성" 셀 85개(마지막 10개는 0x02-0x0B로 이어진다), 0x0C-0x0E에 획 끝 조각.
모아쓰기 모드(`POKE -851,0`)에서 한글 ROM은 음절을 이 셀들의 텍스트 2행으로 찍는다. 너비는 겹받침이 없는 ㅗ ㅛ ㅜ ㅠ ㅡ 음절이면
1열, 그 밖은 2열이다. 어느 셀이 어디에 가는지는 표로 저장되어 있지 않아서, 실행 중인 기계에서 읽었다.

방법(openMSX 19.1, 기종 `Daewoo_DPC-200`, Xvfb에서 화면 없이):

1. Tcl 스크립트로 기계를 켠다: `xvfb-run -a openmsx -machine Daewoo_DPC-200 -script harvest.tcl`. 스크립트 첫 줄에 `set throttle off`를
   두면 에뮬레이션이 호스트가 허락하는 만큼 빨리 돈다(부팅, 입력, 화면 146개에 약 2초). 이때는 프레임을 그리지 않으므로 스크린샷(5단계)은
   throttle을 켜고 찍는다.
2. 음절이 어떤 바이트로 저장되는지 찾는다: BASIC `REM` 줄에 두벌식 키를 친다(한/영은 키 행렬 6행 비트 4: `keymatrixdown 6 0x10`, 이어서
   `keymatrixup 6 0x10`). 그리고 프로그램을 RAM에서 읽는다(`debug read_block "Main RAM" 0 0x10000`, 프로그램은 F676h의 주소부터).
   음절은 자모 바이트로 저장된다: 초성 0x86 + L, 모음 셀(ㅏ 99 ㅐ 9A ㅑ 9B ㅒ 9C ㅓ 9D ㅔ 9E ㅕ 9F ㅖ A0 ㅗ A1 ㅛ A2 ㅜ A3 ㅠ A4 ㅡ A5 ㅣ A6.
   겹모음은 둘: ㅘ = A1 99, ㅢ = A5 A6), 받침은 그 자음의 셀(ㄳ = 86 8F). ROM은 찍을 때 조합한다.
3. RAM에 놓은 음절을 찍는 프로그램을 친다: `type "poke -851,0\r"`(모아쓰기), 그리고 한 줄씩 `10 defint a-z`,
   `20 if peek(&hbffe)=0 then 20`, `30 poke &hbffe,0:poke &hbfff,0:cls:a=&hc000`, `40 for k=0 to 76`,
   `50 locate (k mod 7)*4,(k\7)*2`, `60 n=peek(a):a=a+1`, `70 for j=1 to n:print chr$(peek(a));:a=a+1:next`,
   `80 print " ";`, `90 next`, `100 poke &hbfff,1`, `110 goto 20`, 그리고 `run`. 화면마다 77자(한 행에 7자: 텍스트 창이 2열 안쪽에서
   시작하므로 4열짜리 칸이 한 행에 8개가 아니라 7개 들어간다).
4. 화면마다 스크립트가 77자(음절마다 길이 바이트와 자모 바이트)를 `debug write_block "Main RAM" 0xC000 ...`로 C000h에 쓰고, BFFEh를
   1로 놓고, 프로그램이 BFFFh를 1로 놓을 때까지 기다린 뒤, SCREEN 1 이름 표를 파일에 덧붙인다(`debug read_block VRAM 0x1800 768`).
   패턴 표는 한 번만(`debug read_block VRAM 0 2048`). 화면 146개가 11,172자를 덮는다. 결과는 파일로 쓴다: `puts` 출력은 셸에 오지 않는다.
5. 눈으로 확인: `screenshot FILE.png`(throttle 켬)가 이름 표가 말하는 화면을 보여 준다.
6. 이름 표에서 규칙을 이끌어 내고(음절마다 셀 코드, 모음 종류와 받침별로 모아서) 모든 음절에 대어 본다. `tools/msxfont.py msx1-verify
   PREFIX --bios BIOS`가 `PREFIX.index`(음절, 한 줄에 16진 코드 하나), `PREFIX.names`, `PREFIX.patterns`를 읽는다.

        python3 -I tools/msxfont.py msx1-verify $OUT/dpc200 --bios $ROMS/dpc-200_basic-bios1.rom
        #   layout rule vs the machine: 11172 of 11172 syllables identical
        #   VRAM pattern table vs the BIOS table: 255 of 256 cells identical (differ: 0xff)

   셀 0xFF는 커서다. 금성 FC-80U도 바이트까지 같은 이름 표와 패턴 표를 낸다.

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

#### TrueType 파일

페이스마다 TrueType 비트맵 폰트로 이어 갈 수 있다([SVF 페이스를 다시 TTF 비트맵 폰트로](#svf-페이스를-다시-ttf-비트맵-폰트로)).

    python3 tools/svf2ttf.py ttf $OUT/CPC300J.SVF $OUT/CPC300J.ttf --composite --licence none
    python3 tools/svf2ttf.py ttf $OUT/CPC400S.SVF $OUT/CPC400S.ttf --licence none
    python3 tools/svf2ttf.py ttf $OUT/MSX1.SVF $OUT/MSX1.ttf --licence none

결과: `671,640 bytes`(조각 210, 합성 음절 11,172, 글리프 11,318개), `623,164 bytes`(글리프 2,688개), `374,680 bytes`(글리프 2,445개).
모두 16 px 스트라이크가 있다. 이 폰트들에는 따라갈 라이선스 문서가 없으므로 `--licence none`이다.

#### 정답으로서의 에뮬레이터

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

<a id="mame-세트의-한글-폰트-rom"></a>

## 7. MAME 세트의 한글 폰트 ROM

한국 가정용 컴퓨터와 한국 아케이드 게임은 한글 폰트를 ROM 칩에 두며, MAME의 롬셋에 그 덤프가 있다. 24x24는 없다: 찾은 폰트는
16x16이고, 하나는 자모 조각 세트(삼성 SPC-1500), 나머지는 게임 스프라이트로 된 완성형 세트다. 도구: `rawcarve.py region`은 게임의
ROM 파일들을 MAME 드라이버가 올리는 영역으로 잇는다. `binscan.py` / `rawcarve.py`는 반전된 폰트(`--invert`)와 여러 비트 스프라이트
타일(`--gfx`, 드라이버 자신의 `gfx_layout` 숫자로, 펜 규칙 `--bg PEN` 또는 `--fg PENS`로 1 bpp로 줄인다)을 읽는다. `rawcarve.py ink`는
다른 도구가 읽는 1 bpp 글리프를 쓴다. `jamoset.py --layout spec`은 compose 명세에서 정확한 자모 세트를 만든다. `rawcarve.py eng
--width 16` / `jamoset.py --eng`는 16 너비 영문 셀을 받는다. [Claude와 함께 프로그램이나 데이터 파일 안의 폰트
찾기](#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기)의 드라이버처럼 ROM은 읽기만 한다: 게임은 실행하지 않는다(에뮬레이터는
괜찮다. 아래 그리기 규칙은 MAME 소스와, 역어셈블한 게임의 68000 코드에서 읽었다)([MAME 기종 정보, ROM 로드, 타일 배치](#ref-mame) 참고).

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

### 7.1. 삼성 SPC-1500: 반전된 ROM 네 개의 자모 세트(정확)

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

### 7.2. Date Quiz Go Go: 음절 2,350자의 스프라이트 폰트

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

### 7.3. X Se Dae Quiz: 스프라이트 속의 태백 GOTHIC16(대조용)

원본: 세트 `xsedae`(Dream Island, 1995), `obj-1.u0811`과 `obj-2.u082`(각 2 MB), `ROM_LOAD32_WORD`와 `gfx_16x16x4_packed_lsb`
(`seibu/raiden2.cpp`). 여기서는 바탕이 마지막 펜이다: 잉크 = 펜 != 15. 처음 스프라이트 360개가 원시 8x4x4 폰트이고, 영문 폰트(16
너비: 몇 글리프는 15열까지 간다)가 `!`부터 뒤따른다.

    python3 -I tools/rawcarve.py region --unit 2 $MAME/xsedae/obj-1.u0811,$MAME/xsedae/obj-2.u082 -o $OUT/xsedae-obj.bin
    python3 -I tools/rawcarve.py ink $OUT/xsedae-obj.bin --gfx 16x16x4_packed_lsb --bg 15 --count 600 -o $OUT/xsedae-ink.bin
    python3 -I tools/binscan.py sets $OUT/xsedae-ink.bin              # offsets 0x0, 0x2 tie: the font starts at 0
    python3 -I tools/rawcarve.py cut $OUT/xsedae-ink.bin --offset 0 --length 11520 -o $OUT/xsedae.fnt
    python3 -I tools/rawcarve.py eng $OUT/xsedae-ink.bin --offset $((360*32)) --width 16 --first 0x21 -o $OUT/xsedae-eng16.bin
    python3 tools/jamoset.py --layout 844 $OUT/xsedae.fnt --eng $OUT/xsedae-eng16.bin --check -o $OUT/XSEDAE16J.SVF

`xsedae.fnt`는 태백 3.5.1의 `GOTHIC16.FNT`([그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트)의 원본)와 바이트 단위로 같다. 게임이
더한 디자인은 없고, 타일 경로를 점검하는 데 쓴다. 검증함: `15,780 bytes`, 글리프 439개, `check: ... identical to johab844.py`,
`width=144 ascent=14 descent=2`(16x16 영문 폰트의 이동 폭은 8로 잰다), 잉크 617.

<a id="quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트"></a>

### 7.4. Quiz King of Fighters(한국판): 외곽선 펜이 있는 음절 2,350자 폰트

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

### 7.5. Live Quiz Show: 규칙은 읽었고 조각은 맞지 않는다(만들지 않음)

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

### 7.6. 폰트가 없거나 풀지 못한 세트

- `quizdaisk`(Quiz 사립탐정, 네오지오, 1995): 스프라이트(c1/c2, 위의 네오지오 배치, `--fg 1`)에 스프라이트 4097부터 KS X 1001 순서에
  빈틈이 있는 16x16 한글 세트가 있다(가 각 간 갇 갈 감 ..., 갉 갊 없음. 약 1,467 타일이 글리프이고 나머지는 그림이나 빈 칸): 게임 자신의
  글자 목록이며, 프로그램에서는 찾지 못했다(`123-p1.p1`에 KS 표가 없다). 픽스 레이어 `123-s1.s1`(8x8, `--gfx 'planes=0,1,2,3;x=132,128,196,192,4,0,68,64;y=STEP8(0,8);inc=256'`)에는
  그림으로 그린 낱말만 있다. `quizkofk`의 픽스 레이어에는 한글이 없다.
- `shangha3`(Shanghai III, `27c4000.ic44`): 16x16x4 타일로 그린 한국어 메시지 음절 약 90개. 메시지 통째이지 폰트가 아니다.
- `quizchqk`(Quiz Channel Question, 한국어): Dynax 블리터 데이터가 압축되어 있다. 12-24 px의 원시 1 bpp 폰트는 없다.
- `spc800`(`spc800han.rom`: 한글 BASIC 코드), `spc1000`, `fc100`, `cpc61`, `cpg120`(8x8 / 8x12 문자 ROM, SPC-1000에 한글 그림 셀 몇 개):
  한글 폰트 없음.

<a id="os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기"></a>

## 8. OS/2 한글 폰트(완성형)에서 완성형 페이스와 자모 세트 만들기

<a id="os2-한글-폰트완성형"></a>

OS/2의 한글 "System DBCS" 폰트(`$korZN16.FNT`, `$korZN24.FNT`)는 완성형이다. KS X 1001 표 전체(기호 1,128개, 음절 2,350개, 한자
4,888개)를 코드 순서로 담고, 글리프마다 압축되어 있다(니블의 허프만 부호, 그다음 위 두 행에서 문맥 표로 예측). `tools/os2dbcs.py`가
이를 94 x 94 표로 풀고, 그다음은 어느 KS X 1001 덤프와 같은 길이다: BDF, `bdfface.py`, 그리고 그 페이스에 맞춘 자모 세트.

    python3 -I tools/os2dbcs.py info '$korZN16.FNT'
    python3 -I tools/os2dbcs.py table '$korZN16.FNT' -o $OUT/zn16.bin
    python3 -I tools/rawcarve.py bdf $OUT/zn16.bin --glyph 16x16 --chars ks-hangul --grid 0xA1,0xA1,94 -o $OUT/zn16.bdf
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/8x16.pcf.gz $OUT/8x16.bdf   # Misc Fixed 8x16, Debian xfonts-base
    python3 tools/bdfface.py --hangul $OUT/zn16.bdf --ascii $OUT/8x16.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/OS2ZN16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/OS2ZN16.SVF --mask-font none --check -o $OUT/OS2ZN16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/OS2ZN16.SVF --mask-font none --check -o $OUT/OS2ZN16JA.SVF

OS/2 Warp 4 한국어판(IBM. CD의 FTCOMP 묶음을 johab-fonts 연구에서 푼 것, `D28REQ.004` = `$korZN16.FNT` 220,160 바이트, `D28REQ.002` =
`$korZN24.FNT` 346,624 바이트, 독점)에서 실행했다. `info`: "System DBCS 16", 16x16, 글리프당 32 바이트, 리드 바이트 A1-AC, B0-C8, CA-FD,
글리프 레코드 8,224개, 음절 2,350개 모두 있음. `table`은 슬롯 8,742개(279,744 바이트, 연구 디코더의 덤프와 같은 바이트)를 쓴다. 영문
절반은 이 호스트의 X11 "Misc Fixed" 8x16과 12x24(`xfonts-base`, 퍼블릭 도메인)이다. OS/2의 DBCS 파일에는 ASCII가 없다. 24 px 페이스는
같은 명령에 `--glyph 24x24 --ascent 22`, `12x24.pcf.gz`, `--cell 24x24`:

| 페이스 | 바이트 | 글리프 | 맞춤 | measure | 잉크 |
|---|---|---:|---|---|---:|
| `OS2ZN16.SVF`, 완성형 16 px | `123,328` | 2,447 | | `width=144 ascent=14 descent=2` | 469 |
| 그 8x4x4 자모 세트 | `17,264` | 441 | IoU 0.984 (p5 0.898), 2,350 중 1,753 정확, 0.3 s | 같음 | 470 |
| adaptive 자모 세트 | `42,140` | 858 | 벌 14/12/9, IoU 0.999, 2,299 정확, 3 s | 같음 | 469 |
| `OS2ZN24.SVF`, 완성형 24 px | `220,164` | 2,447 | | `width=216 ascent=22 descent=2`(규칙 `line 400 32 0 24`) | 922 |
| 그 8x4x4 자모 세트 | `30,544` | 441 | IoU 0.720 (p5 0.457), 17 정확, 0.8 s | 같음 | 909 |
| adaptive 자모 세트 | `100,740` | 1,533 | 벌 32/24/12, IoU 0.883, 548 정확, 11 s | 같음 | 921 |

모든 자모 세트에서 `--check`는 11,172 음절을 모두 조합한다. 16 px 디자인은 조각의 OR에 가까워 8x4x4로도 0.984가 맞지만, 24 px는
음절마다 따로 그린 디자인이라 기본 adaptive 예산(벌 32/24/12)으로도 잘 맞지 않는다. 예산이 허락하면 완성형 페이스를 두거나
[벌 수 정하기](#벌-수-정하기)를 보라. `rawcarve.py bdf` 줄에 `--chars ks-nonhanja`를 주면 기호와 호환 자모까지 남는다
(글리프 3,334개). `bdfface.py`는 음절만 남기고, `mkfont.py`는 BDF를 그 자신의 크기로 읽는다: `mkfont.py $OUT/zn16-nh.bdf ... --size 16
--bpp 1 --unicode ksx1001-hangul,jamo`는 `123,880 bytes`, 글리프 2,444개, 샘플 줄의 다섯 음절 `width=80`, 잉크 310을 쓴다.
`--unicode ksx1001-nohanja`는 Pillow의 `raqm_get_glyphs() failed`로 멈춘다. KS X 1001 A1A9는 셰이퍼가 버리는 U+00AD(소프트 하이픈)이니
목록에서 빼라(`--chars-from`). 같은 CD의 `$SYS1Z16/24.FNT` 파일은 음절이 아니다(조각으로 된 IBM 사용자 영역). 읽지 않는다.

<a id="고해상도-비트맵-폰트에서-저해상도-페이스-만들기"></a>

## 9. 고해상도 비트맵 폰트에서 저해상도 페이스 만들기

24, 40, 48 px 비트맵 폰트(DOS나 프린터 폰트, BDF, ROM)를 16 px로, 또는 2 bpp 페이스로 쓰고 싶을 때다. 지금 도구가 하는 일:
`mkfont.py`는 BDF나 PCF를 그 자신의 크기로만 연다(다른 크기에서는 `OSError: invalid pixel size`,
[ISO 10646 BDF와 PCF](#iso-10646-bdf와-pcf)). `jamoset.py --from-svf`는 원본의 셀을 유지한다. C 렌더러와 `svfline.py`는 그리는 시점에
페이스를 축소한다(`scale_num / scale_den`, 8비트 피복도로 가는 박스 필터). `tools/svfscale.py`는 더 작은 페이스를 쓴다. 1 bpp 페이스(자모 세트는 음절을 조합해서)나 BDF에서 선택한 글리프를 그리고, 새 셀로 박스 필터를
걸어(출력 픽셀마다 원본 영역 중 잉크가 차지한 정확한 비율) 완성형 페이스를 쓴다. 1 bpp는 임계값으로, 2 bpp는 네 단계로:

    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 -o $OUT/ZN24TO16.SVF --compare $OUT/OS2ZN16.SVF   # 1 bpp, 비율 >= 0.5
    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 --bpp 2 -o $OUT/ZN24TO16A.SVF                     # 2 bpp
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/ZN24TO16.SVF --mask-font none --check -o $OUT/ZN24TO16J.SVF

다른 두 원본도 같은 길이다: `bdfface.py --hangul dotum24.bdf --ascii $OUT/12x24.bdf --cell 24x24 ...`(비교할 페이스는 `dotum16.bdf`와
`8x16.bdf`), `jamoset.py --layout 844 GHANC40.PFT --eng GASCII40.PFT --symbols --check -o $OUT/GHANC40J.SVF`(비교용은 `GOTHIC16.FNT --eng ROMAN16.FNT`). 각각 그다음
`svfscale.py --size 16`.

2 bpp 결과는 렌더러가 24 px 페이스를 2/3로 축소해 그리고 피복도를 네 단계로 양자화한 것과 정확히 같다(아래 OS/2 페이스의 2,350
음절 모두에서 확인: 전부 같음). 이 비교에서는 저장한 2 bpp 페이스와 그리는 시점의 축소를 양자화한 결과가 같은 픽셀을 내며, 저장한 페이스는 메모리를,
축소해 그리기는 시간을 쓴다. 자모 세트는 1 bpp 결과에만 맞출 수 있다. `jamoset.py --bpp 2`는 아웃라인 폰트만 받으므로(`--bpp 2 works
from an outline font (--from-ttf)`) 비트맵 원본에서 2 bpp 자모 세트를 만드는 길은 없다.

여기서 실행(2026-11-22)한 세 원본, 각각 같은 패밀리나 제작사의 손으로 그린 16 px 페이스와 비교했다. "겹침"은 `--compare`가 출력하는
값으로, 1 bpp 결과의 2,350 음절을 그 페이스와 두 페이스를 한 기준선에 놓고 2 픽셀 안의 가장 좋은 공통 이동에서 비교한 평균 IoU이다(다시 샘플링한 페이스가 그린
페이스에서 얼마나 먼지를 재는 값이지 품질 점수가 아니다):

| 원본 | 1 bpp 결과 | 잉크 | 2 bpp 결과 | 잉크 | 1 bpp 결과의 8x4x4 맞춤 | 그린 16 px 페이스와 겹침 |
|---|---|---:|---|---:|---|---|
| 백묵 돋움 24 (Baekmuk BDF 2.2의 `dotum24.bdf` + Misc Fixed 12x24, `bdfface.py`를 거쳐 `216,196 bytes`) | `122,016 bytes`, 글리프 2,447개, `width=144 ascent=15 descent=1` | 330 | `194,208 bytes` | 612 | `18,292 bytes`, IoU 0.597 | `dotum16.bdf`(`122,804 bytes`, 잉크 411)와 0.520 |
| OS/2 `$korZN24.FNT` ([OS/2 한글 폰트](#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기), `220,164 bytes`) | `125,084 bytes`, 글리프 2,447개, `width=144 ascent=15 descent=1` | 410 | `200,760 bytes` | 691 | `18,596 bytes`, IoU 0.710 | `$korZN16.FNT`와 0.387 |
| 태백 3.5.1 고딕 40 (`GHANC40.PFT`와 `--eng GASCII40.PFT`, [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트)의 8x4x4 페이스, `42,716 bytes`) | `124,940 bytes`, 글리프 2,447개, `width=144 ascent=14 descent=2` | 476 | `197,288 bytes` | 764 | `17,088 bytes`, IoU 0.990 | GOTHIC16.FNT와 0.471 |

40 px 원본은 그 자체가 8x4x4 조각의 OR이라 16 px로 다시 샘플링해도 거의 그대로다(IoU 0.990). 음절마다 그린 두 디자인은 8x4x4에 잘
맞지 않는다. 임계값은 획과 뭉침을 맞바꾼다: OS/2 페이스를 `--threshold 0.25`로 하면 잉크 615(`0.5`는 410), 그린 16 px 페이스와 겹침
0.489이다. `svfscale.py dotum24.bdf --chars face`는 BDF의 모든 글리프를 고른다(이 예시에서는 한자 포함 8,226개).
기본 `--chars ks`는 KS 음절, ASCII, 사용 가능한 비음절 문자를 고른다. ascent는 BDF의 값을 쓴다. ASCII와 원하는
셀이 있는 페이스를 원하면 먼저 `bdfface.py`를 거쳐라.

**함정.** 24 px의 1 픽셀 획은 16 px 픽셀의 3분의 2를 덮으므로, 위치가 맞을 때만 0.5 임계값에서 살아남는다. 40, 48 px의 가는 획은 비율
0.4인 픽셀이 되어 1 bpp에서 사라진다. 다시 샘플링은 다시 그리기가 아니다: 그린 16 px 페이스(위 표의 마지막 열)가 더 선명하고,
아웃라인 폰트에서 만든 2 bpp 페이스([2 bpp 안티앨리어싱 페이스](#truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기))는
비트맵 계단의 피복도가 아니라 진짜 피복도를 가진다.

<a id="클래식-mac-한글-비트맵-폰트"></a>

## 10. 클래식 Mac 한글 비트맵 폰트

원본 파일은 직접 마련한다. maker의 로컬 모드([maker 데스크톱 안내서](maker-desktop.ko.md))는 이
폰트를 디스크의 제자리에서 같은 도구로 읽고, 페이스는 고른 폴더에만 쓴다([Apple 폰트 표와 리소스 포크](#ref-apple) 참고).

**HangulTalk 1.0 'fbit' 폰트** (한글 System 4.1: Gotic12/16, Munjo12/16/24). 입력: 폰트의 리소스 포크를 파일로 한 것(Mac 볼륨에서
복사했거나 아카이브의 포크; `tools/macsfnt.py list`가 그 'fbit' 리소스를 보여 준다). 포크에는 글리프 벌 45개의 'fbit' 리소스와
18개의 조회 표를 가진 'fdef' 드라이버 리소스가 있다. 벌 체계는 폰트 자신의 규칙에서 유도하므로, 모든 음절이 Mac이 그리는 대로
조합된다.

    python3 tools/jamoset.py --layout mac-fbit-45sets Munjo24.rsrc --symbols --check -o $OUT/MUNJO24J.SVF

출력: 음절 11,172개 전체의 1 bpp 자모 세트(이 폰트들은 초성 클래스 8개, 종성 클래스 4개, 초성 벌 20개), 셀 = 폰트의 크기.
`--check`는 모든 것을 조합해 jamoset 자체의 'fdef' 규칙 사본과 비교한다. 직접 만들면 골든 파일(`tools/testdata/mac-fbit-golden.json`,
배포하지 않음: Apple 비트맵이 들어가기 때문)이 독립적인 비교를 더한다. 실제 파일에 대한 테스트는 `JOHAB_FONTS`가
`mac/extracted/kh10_system_disk/System Folder/*.rsrc`와 참조 렌더러를 담은 트리를 가리킬 때 실행되고, 아니면 건너뛴다.

한글 시스템 4.1 / HangulTalk 1.0(1988년 1월, Apple Korea / Elex Computer; 독점)의 시스템 디스크로 실행했다. `System Folder`에 네 폰트가 리소스 포크
파일로 있다. `Munjo24`(24 px 문조. `list`는 `fbit` 17409, 47,714 바이트와 그 `fdef` 3, 2,398 바이트를 보여 준다): `36,660 바이트`, 24x24 조각 653개,
초성 클래스 8개 x 종성 클래스 4개, 벌 20/15/4, `check: composed 11172 syllables from 655 glyphs`, 그리고 jamoset 자체의 `fdef` 규칙 사본에 대한 자기
일관성 줄 `IoU 1.000, exact 11172`(골든 파일 없음), 1.0초. 샘플 줄은 `width=120 ascent=24 descent=0`(이 폰트들에는 라틴이 없어 음절 다섯 개만
그려진다), 잉크 591. `Gotic12`(12 px 고딕): `23,368 바이트`, 같은 벌, `width=60 ascent=12 descent=0`. maker의 로컬 모드(`detect.scan(..., local=True)`, 네
폰트의 사본에서)는 이들을 "HangulTalk 1.0 fbit (45 sets), 24 x 24"(Munjo24. Munjo12, Gotic12는 12 x 12, Munjo16은 16 x 16), 소스 종류
`mac-fbit1`, 피복도 KS 2,350 / 음절 11,172와 호환 자모 51로 읽고, 위 명령을 실행하는 `mac fbit 1.0` 경로를 제공한다. 업로드 모드는
"Mac bitmap font (NFNT/fbit): not converted here (local-only mode)"라고 한다.

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
외삽한 것이다(Mac 출력이 아님). 라틴 문자를 포함한 완성형 페이스를 만들려면 BDF를 `bdfface.py --hangul`로 주고 별도 `--ascii` 폰트와
`--cell 12x12 --chars-from $OUT/ks.txt`를 지정한다. 아래의 `mkfont.py` 경로에는 라틴 짝 파일이 필요 없다. 변형이 많은 페이스를 MCU 예산에 맞게 줄이려면:

    python3 tools/jamomerge.py merge --face $OUT/SEOUL12D.SVF --points 8192 7168 --prefix SM -o $OUT/SMALL

(모든 조각을 그려진 그대로 유지하고, 픽셀 목적 함수로 변형, 벌, 클래스를 병합한다). 테스트: `tools/test_macfbit3.py`와
`tools/test_macfbit_svf.py`는 테스트 안에서 만든 합성 fbit / HTBL / NFNT 데이터로 실행된다. `MACFBIT3_CD712=<CD tree>`와
`SVF_MAC71_INPUTS=<dir of Name.fbit and Name.htbl1>`은 직접 가진 파일에 대한 점검을 더한다. 윤곽선 Mac TrueType 폰트는
[Mac 형식 TrueType](#mac-형식-truetype)을 참고한다. 이 폰트들에 대한 maker의 경로는 [경로 표](#데스크톱-앱과-maker-경로)에 있다.

한글 시스템 7.1.2 / HangulTalk 7.1.2(Apple Korea / Elex Computer; 독점)의 Seoul12로 실행했다. CD의 `More Additions` 폴더에 있는
`Seoul12[splt]`(HangulTalk 7.5.1 설치 디스크의 `Seoul12[fbit]` 포크도 같은 8,760 바이트 `fbit`를 주며 `cmp`로 동일하다)와, 그 CD의
`InputBackSupport` 확장의 HTBL 1이다. HTBL은 위 명령이 보여 주지 않았던 단계로, 이제 위 블록의 첫 줄이다(`srcprep.py mac-htbl`, 9,816 바이트). 확장의 7.5.1 사본은 압축되어 있어 `srcprep.py`가 "not an HTBL 1
table"이라고 답한다. 이 `$OUT/HTBL1.bin`으로 위 명령은 적힌 그대로 돈다. `unpack`은 `JM 1843 -> 9673 bytes`, `fbit`는 8,760 바이트, `bdf`는 글리프 2,401개. `direct`는 `15,016 바이트`,
조각 207개, `verify`는 ks_bad 0, compat_bad 0, non_ks_present 0. `derived`는 `9,716 바이트`, 조각 219개, 8 x 4 클래스, 벌 9/6/3(JSET v2로는 `7,928 바이트`),
KS 음절과 호환 자모 검증. 둘 다 샘플 줄의 음절 다섯 개를 `width=60 ascent=10 descent=2`, 잉크 142로 그린다. BDF 경로(`macfbit3.py bdf`, 그다음 `srcprep.py bdf-pixel-size
seoul12.bdf seoul12-sized.bdf --size 12`, 그다음 `mkfont.py ... --size 12 --bpp 1 --unicode ascii,ksx1001-hangul`과 정규 단계)는 `103,012 바이트`,
글리프 2,350개, 같은 `width=60 ascent=10 descent=2`, 잉크 142를 준다. 라틴 글자를 패밀리 suitcase로 넣으면(`--latin "Seoul[FFIL].rsrc"`: 같은 CD의 `FOND`와
9, 12 pt `NFNT` 스트라이크 둘) `direct`는 `17,924 바이트`(라틴 1,388), `derived`는 `12,624 바이트`이고 둘 다 `width=111 ascent=10 descent=2`, 잉크 253,
`verify` 이상 없음. `jamomerge.py merge --points 8192 7168`(약 2분)은 `SM8K.SVF` `7,964 바이트`와 `SM7K.SVF` `7,032 바이트`(조각 191개, 벌 7/6/3)를
쓰고 검증된다. maker의 로컬 모드가 파일을 읽는다(`detect.scan(..., local=True)`): `Seoul12` 포크, `splt` 파일, 원시 포크는 "HangulTalk 7.1 type-3 fbit, 12 px,
482 planes (needs HTBL 1)"이고 경로 `mac fbit 7.1 direct`, `derived`, `bdf + mkfont`를 얻는다. 확장은 "HangulTalk 7.1 HTBL 1 (InputBackSupport): the
composition table", `Seoul[FFIL]`은 "Mac bitmap suitcase (FOND + NFNT): Latin strikes at 9, 12 pt"이다.

<a id="기존-svf"></a>

## 11. 기존 SVF

원본: `svf/dos/NEODG16.SVF`(완성형 1 bpp 페이스, 16x16, 글리프 2,905개, 메트릭 표 있음).

dy 설정(글리프 픽셀과 나머지 메트릭을 유지하며 파일은 다시 패킹한다):

    python3 tools/svfdy.py svf/dos/NEODG16.SVF $OUT/neodg16-dy.svf --range 0x20-0x7e --dy 3

검증: `133,720 바이트`(변함 없음), 글리프 2,905개, 글리프 95개에 dy 설정, 범위 0..3. 렌더는 `width=144 ascent=12 descent=7`
(descent가 dy만큼 커졌다), 잉크 559.

자모 세트로 다시 변환(1 bpp 페이스의 완성형 음절에 대한 맞춤. 조각과 페이스의 나머지 글리프는 유지된다):

    python3 tools/jamoset.py --layout 844 --from-svf svf/dos/NEODG16.SVF --mask-font none -o $OUT/neodg16-from-svf.svf

검증: `34,332 바이트`, 글리프 892개, 조각 344개. 맞춤: 음절 2,357개, IoU 1.000(Neo Dunggeunmo는 그 자체가 조각의 OR이다). 렌더는
`width=144 ascent=12 descent=4`, 잉크 559. 기존 SVF는 같은 크기의 안티앨리어싱 원본이 아니다. 1 bpp 페이스를 같은 크기의 2 bpp로 바꾸는 도구는 없고(`svfscale.py --bpp 2`는 더 작은 크기로 다시 샘플링한다),
`svfdy.py`는 dy만 바꾼다.

**버전과 프로필.** SVFN v2는 폐기되었다. `svf2to3.py`는 v2를 읽고 v3 페이스를 다시 배치한다. maker의 "copy" 경로는 업로드된 SVF에 이를 쓴다
(`svf2to3.py SRC OUT --jset-version V --check`: v2 페이스를 v3로 담거나, JSET 블록을 다시 쓴 v3 페이스). 자모 세트는 표를 JSET v1(기본)
또는 v2(메모리가 제한된 대상에서 더 작다)로 담는다. `--jset-version auto`는 v1 블록이 1,024 바이트 이상 크면 v2를 고른다. JMAP 블록(JSET
버전 3)은 그대로 복사되며 그 경우 이 플래그는 아무 일도 하지 않는다.

    python3 tools/svf2to3.py $OUT/NG16J.SVF $OUT/NG16J-v2.SVF --jset-version 2 --check
    python3 tools/svf2to3.py svf/dos/NEODG16A.SVF $OUT/NEODG16A-v2.SVF --jset-version 2 --check
    python3 tools/svf2to3.py svf/dos/NEODG16.SVF $OUT/NEODG16-canon.SVF --profile default --check

검증: NanumGothic Bold의 1 bpp 자모 세트는 `--jset-version 2`로 `20,064` -> `19,232 바이트`(JSET 블록 1,101 -> 272 바이트, 글리프 데이터 11,884 변함 없음, 모든 글리프 비교 일치); 배포된 NEODG16A는 `16,408` -> `15,576 바이트`; `--jset-version auto`에서 NEODG16A는 v1로 남는다(`jset=1`. v1 블록이 v2보다 829 바이트만 커서 1,024 기준에 못 미친다). 마지막 명령은 배포된 페이스를 `default` 프로필로 다시 배치하며 바이트가 같다: 입출력 모두 133,720 바이트(`cmp`가 차이를 보고하지 않는다). `--profile`은 대상별 레이아웃을
고른다(`mcu-strict`, `default`, `dos`, `wasm`, `full`, `simd16`). `--check`는 픽셀이 바뀌지 않았음을 증명한다.

<a id="svf-페이스를-다시-ttf-비트맵-폰트로"></a>

## 12. SVF 페이스를 다시 TTF 비트맵 폰트로

반대 방향이다. `tools/svf2ttf.py`는 완성형이든 자모 세트든 SVF 페이스를 OS나 응용 프로그램이 설치할 수 있는 TrueType 폰트로,
그리고 BDF로 되돌린다. 페이스는 C 라이브러리가 읽는 방식(`svfline.Face`)으로 읽는다. 그래서 자모 세트는 그 표가 합성하는 모든
음절(전체 표라면 11,172개 모두, `svfline.py`가 그리는 대로 `jamoset.compose`로 합성)과 표가 매핑하는 호환 자모를 나머지 글리프와
함께 내며, 어느 쪽이든 출력은 완성형 폰트이다. 모든 글리프는 `svfline.py`가 그리는 자리에 선다: 셀의 왼쪽 열이 펜에, 맨 위 행이
기준선 위 `ascent - dy`행에, 결합 부호는 그 원점에 advance 0으로, advance는 페이스 자신의 값이다([OpenType 글리프, 셰이핑, 비트맵 스트라이크](#ref-opentype) 참고).

    python3 tools/svf2ttf.py ttf svf/dos/NEODG16.SVF $OUT/NEODG16.ttf
    python3 tools/svf2ttf.py ttf svf/dos/NEODG16A.SVF $OUT/NEODG16A.ttf --family "My Pixel" --style Regular --version 1.001
    python3 tools/svf2ttf.py bdf svf/dos/NEODG16A.SVF $OUT/NEODG16A.bdf

**TTF에 담기는 것.**

- **아웃라인**(`glyf`): 각 글리프의 픽셀을 가장자리를 따라 윤곽선으로 추적한 것(구멍은 유지, 대각선으로 닿는 픽셀은 떼어 둠, 힌팅 없음.
  바이트코드는 no-op 하나뿐인 `prep`(`PUSHB 0, POP`)만 있다: FreeType은 바이트코드가 전혀 없는 TrueType을 자동 힌터에 넘기는데, 자동
  힌터는 1.5 x에서 NEODG16의 아웃라인을 최대 한 픽셀까지 옮겼고(24 px 샘플 줄에서 591 픽셀), prep이 있으면 정확한 면적 피복도를
  그린다: `svfline.py`의 3/2 배율과 1 단계 이내).
  `unitsPerEm` = ppem x 64이므로 한 픽셀이 64 단위이고, 아웃라인은 ppem과 그 정수배에서 페이스의 픽셀을 정확히 덮는다. 폰트는
  확대·축소할 수 있고 설치할 수 있다. ppem의 기본은 셀 높이이다(다른 값은 `--ppem N`, 예: 24행 셀에 17 px로 구운 페이스는 17).
  줄 높이는 셀이다(ascent + descent = 셀 높이).
- **내장 비트맵 스트라이크**(`EBLC`/`EBDT`, 이미지 형식 1, 인덱스 형식 1): ppem에서 페이스 자신의 비트 깊이로. 1 bpp 페이스는 1비트
  스트라이크, 2 bpp 페이스는 2비트 스트라이크(네 단계를 그대로), 8 bpp는 8비트. 내장 비트맵을 쓰는 렌더러(FreeType, Windows)는
  ppem에서 페이스 자신의 픽셀과 단계를 그리고, 그 밖의 모든 크기에서는 아웃라인을 그린다. `--no-strike`는 아웃라인만 쓰고,
  `--apple`은 같은 스트라이크를 `bloc`/`bdat`으로 더한다.
- **2 bpp 페이스.** 아웃라인에는 단계가 없으므로 2 bpp 페이스의 아웃라인은 피복도 128 이상의 픽셀(단계 2와 3, C 라이브러리의
  mono 대상 규칙. 다른 값은 `--threshold C`)을 취한다. ppem에서는 스트라이크가 단계를 주고, 다른 크기에서는 아웃라인이 그 1비트
  절단이다.
- **메트릭**: `hmtx`의 advance = 페이스의 advance x 64. `hhea`와 OS/2 typo ascender / descender = 페이스의 ascent와 셀 높이 - ascent
  (`USE_TYPO_METRICS`). OS/2 win ascent / descent는 dy가 셀 밖으로 옮긴 잉크까지 덮는다. 스트라이크 자체의 small metrics가 글리프마다
  bearing과 advance를 담는다.
- **cmap**(형식 4, U+FFFF를 넘으면 12), `post` 형식 3(글리프 이름 없음), `head`, `maxp`, `gasp`, OS/2(굵기 400, `--style`에
  "Bold"가 있으면 700과 bold 비트. 코드 페이지 비트는 Latin 1, 한국어 완성형, 그리고 11,172 음절이 다 있으면 조합형), `.notdef` 상자.
- **name**: 패밀리 `--family`(기본 `<페이스 이름> SVF`, 예: `NEODG16 SVF`. 원본 폰트 자신의 이름은 쓰지 않는다: OFL의 Reserved Font
  Name은 수정본에 그 이름을 금할 수 있다), 스타일 `--style`(기본 Regular), 버전 `--version`(기본 1.000), 페이스를 밝히는 설명
  (`Generated by svf2ttf.py from NEODG16.SVF (16x16 cell, 1 bpp, precomposed, 2905 glyphs, 16 px strike)`), 그리고 라이선스. 이 저장소
  `svf/`의 페이스는 `web/LICENCES.tsv`의 해당 행이 지명하는 라이선스 파일을 받는다(노트와 OFL 파일, 예: `NEODG*`는 `NEODGM.TXT`와
  `OFL.TXT`, `PAPER*`는 `PAPMARU.TXT`와 `OFLPAPLG.TXT`, `MARU*`는 `OFLMARU.TXT`, `BHSAN28`과 `NSQR*` 등은 OFL 파일만). `svf/` 아래에서
  어느 행에도 해당하지 않는 페이스는 `--licence`가 없으면 오류이다. 그 밖의 페이스는 옆에서 제목 줄이 그 파일 이름이나 그에 맞는
  패턴을 적은 `*.TXT`와 그 노트가 이름을 든 라이선스 파일(모두: 두 폰트를 다루는 노트는 둘 다, 경고와 함께), 없으면 옆
  `FACES.TSV`의 licence 열을 받는다. 텍스트는 라이선스 설명으로, OFL 파일의 저작권 문단(`SIL OPEN FONT LICENSE` 머리 위에서
  "Copyright"나 "(c)"를 말하는 문단, 없으면 첫 문단: Neo Dunggeunmo Pro의 퍼블릭 도메인 출처 표기처럼)은 저작권으로, OFL URL은 OFL
  텍스트가 들어갈 때만 넣는다. `--licence FILE`로 노트를 지정하고 `--licence none`은 넣지 않는다. 저장소 밖에서 노트가 없는
  페이스(`$OUT`에서 직접 만든 것)에는 원본 폰트의 라이선스가 적용된다는 한 줄과 경고가 붙는다: `--licence`를 주어라.
- **코드 포인트**: 자모 세트의 조각(평면 U+F0000..U+FFFFF)은 내보내지 않는다. 완성형 페이스는 거기와 그 너머의 사용자 정의 영역
  글리프를 지킨다. 서로게이트와 U+FFFF는 글자가 되지 않는다. 내보낼 것이 없는 페이스나 전체 글리프(`.notdef`와 공유 구성 요소 포함)가 65,535개를 넘는 TTF는 오류이다.
- **만들지 않는 것**: 첫가끝 자모(U+1100) 셰이핑, GSUB나 GPOS, 커닝, 힌팅 명령, 세로 메트릭. 타임스탬프는 `$SOURCE_DATE_EPOCH`가 있으면 그 값, 없으면 지금이다.

**BDF**(`bdf`): 코드 포인트마다 글리프 하나(BBX는 잉크 상자, DWIDTH는 advance), `FONT_ASCENT` / `FONT_DESCENT`는 페이스의 값,
`PIXEL_SIZE`는 72 dpi의 ppem(`SIZE ppem 72 72`, `POINT_SIZE`는 ppem x 10, `SWIDTH`는 advance x 1000 / ppem), `AVERAGE_WIDTH`는
평균 advance x 10, 라이선스 노트는 `COMMENT` 줄로, 저작권은 `COPYRIGHT`로, UTF-8로 쓴다(노트의 한글은 그대로 남고 FreeType이 읽는다).
1 bpp 페이스는 BDF 2.1을 쓰고, 2 또는 8 bpp 페이스는
`SIZE`의 네 번째 필드에 비트 깊이를 적은 BDF 2.3을 쓴다(FreeType이 읽는다). `--bpp1`이면 1 bpp로 쓴다(`--threshold` 이상의 픽셀).

**왕복(round trip).** TTF를 스트라이크 크기와 페이스의 비트 깊이로 `mkfont.py`에 다시 굽고 비교한다:

    python3 tools/mkfont.py $OUT/NEODG16A.ttf $OUT/back.svf --size 16 --bpp 1 --probe --width 16 --only-listed \
        --unicode $(python3 tools/svf2ttf.py cps svf/dos/NEODG16A.SVF)
    python3 tools/svf2ttf.py compare svf/dos/NEODG16A.SVF $OUT/back.svf

`cps`는 페이스의 코드 포인트를 `--unicode` 범위로 찍고(NEODG16A는 `20-7e,25a1,3131-3163,ac00-d7a3`), `--only-listed`는 그것만
굽는다. `--probe`는 아무것도 자르지 않는 키 큰 셀을 잡고 기준선 하나를 지키며, `--width`는 페이스의 셀 폭이다. `compare`는 두
페이스의 모든 글리프를 `svfline.py`처럼 놓고, 픽셀(피복도로)이나 advance가 다른 글리프와 한쪽에만 있는 잉크 있는 글리프를 센다.
한쪽에만 있는 빈 글리프는 따로 센다: `mkfont.py`는 공백을 뺀 모든 빈 글리프를 버린다(한쪽에만 있는 U+0020, U+00A0, U+3000은
불일치이다: `mkfont.py`가 이들은 지킨다). 불일치가 0이면 종료 코드 0이고, 읽을 수 없는 페이스는 1이다.

검증(2026-11-23). 모든 페이스를 `ttf`와 `bdf`로 만들고, 각 출력을 위와 같이 `mkfont.py`로 다시 구워(2 bpp 페이스는 `--bpp 2`)
비교했다. Pillow(FreeType)로 ppem과 2 x ppem에서 `가각간한글 ABC 123` 줄을 그려 `svfline.py`와 비교했다(2 x에서는 2 bpp 줄을 128에서
자르고 2 x 2 블록으로). OTS 9.2.0(`ots-sanitize`)은 모든 TTF를 통과시키고, `fc-scan`은 모든 TTF를 읽는다(scalable, outline,
패밀리와 스타일):

| 페이스 | 종류 | 글리프 | SVF | TTF | BDF | TTF / BDF 왕복 | 렌더 1 x / 2 x |
|---|---|---|---|---|---|---|---|
| `svf/dos/NEODG16.SVF` | 완성형 1 bpp 16x16 | 2,905 | `133,720` | `481,800` | `440,766` | 2,905개 중 불일치 0 / 0 | 같음 / 같음 |
| `svf/dos/NEODG16A.SVF` | 자모 세트 1 bpp 16x16 | 11,319 | `16,408` | `2,038,968` | `1,745,233` | 11,318개 중 0 / 0 (빈 글리프 1: U+3161) | 같음 / 같음 |
| `svf/jamo-extra/GOTHA16A.SVF` | 자모 세트 2 bpp 16x16 | 11,319 | `73,752` | `2,418,300` | `2,519,856` | 11,319개 중 0 / 0 | 단계까지 같음 / 같음 |
| `svf/dos/NGOTB16.SVF` | 완성형 2 bpp 16x16 | 2,880 | `219,480` | `563,900` | `621,422` | 2,880개 중 0 / 0 | 단계까지 같음 / 같음 |
| `svf/jamo-extra/GOTHB24.SVF` | 자모 세트 1 bpp 24x24 | 11,319 | `96,180` | `2,796,288` | `2,757,257` | 11,319개 중 0 / 0 | 같음 / 같음 |
| HWP 1.x `HANGUL1.PFT` face 1 + `ASCII.PFT`(`jamoset.py --layout hwp1`, [HWP 1.x](#hwp-1x와-2x-폰트)) | 자모 세트 1 bpp 24x24 | 11,318 | `16,712` | `2,849,128` | `2,726,291` | 11,318개 중 0 / 0 | 같음 / 같음 |

8 bpp 페이스(`ttf/nanumgothic/NanumGothic-Bold.ttf`를 16 px, `ascii,ksx1001-hangul`로 `mkfont.py --bpp 8`한 것, 글리프 2,446개,
`579,152 바이트`)는 8비트 스트라이크를 받는다: TTF `876,820`, BDF `1,307,960 바이트`, 두 왕복(`--bpp 8`) 모두 불일치 0. HWP 1.x 페이스(HWP 1.20, 독점)는 옆에 라이선스 노트가 없으므로 그 TTF에는 원본 폰트의 라이선스가 적용된다는 줄이 들어가며,
페이스와 마찬가지로 `$OUT`에 남는다.

`ttf`는 11,172 음절의 자모 세트에 2.5-4.8초, 글리프 2,905개의 완성형 페이스에 1초 미만이 걸린다. TTF의 대부분은 아웃라인이다
(`glyf`: NEODG16A의 2,038,968 바이트 중 1,561,590. 스트라이크는 348,244 + 45,352). 그래서 TTF는 완성형 페이스의 2.5-3.6배, 자모
세트의 29-170배이다. NEODG16A는 U+3161(ㅡ)을 빈 글리프로 그린다(그 호환 조각이 비어 있다). 그래서 `mkfont.py`가 이를 버리고
`compare`는 이를 빈 글리프 하나로 센다.

**설치.** [fontconfig](#ref-fontconfig)를 참고한다. Linux: `.ttf`를 `~/.local/share/fonts/`에 복사하고 `fc-cache`를 실행한다. 별도의 fontconfig 설정(`$OUT` 아래의 `<dir>`와
`<cachedir>`, 이를 가리키는 `FONTCONFIG_FILE`)으로 점검했다: `fc-list`가 `NEODG16A SVF`와 `GOTHA16A SVF`를 나열하고,
`fc-match "NEODG16A SVF:pixelsize=16"`이 그 파일을 고른다. fontconfig는 한국어 철자 목록의 모든 글자(호환 자모 U+3165-U+318E 포함)를
가진 페이스에만 언어 `ko`를 붙인다(NGOTB16은 붙고, NEODG16과 자모 세트들은 안 붙는다). 이는 언어에 따른 대체 폰트 선택에만
영향을 준다. Windows와 macOS: 여기서 테스트하지 않았다(다른 `.ttf`처럼 설치한다. ppem에서 스트라이크를 그릴지 아웃라인을 그릴지는
렌더러가 정한다. Windows는 `EBLC`/`EBDT` 스트라이크를 읽지만 2 또는 8비트 스트라이크를 단계로 그리는지는 테스트하지 않았다. `--apple`은 같은 표를 Apple의 이름 `bloc`/`bdat`으로 더하지만 Mac에서
테스트하지 않았다).

**한계.** 스트라이크는 페이스의 크기 하나만 담는다. 다른 크기에서는 아웃라인이 네모난 픽셀을 그린다(정수배에서 정확하고, 그 밖에서는
렌더러가 안티앨리어싱한다). 2 bpp 페이스의 단계는 스트라이크에만 있다. 출력은 완성형이다: 자모 세트의 작은 크기는 변환 뒤에 남지
않는다(아래의 `--composite`는 조각을 나눠 써서 보통 TTF의 4분의 1에서 절반 미만이 된다). 스트라이크의 메트릭은 바이트이다: advance는 0..255(SVF의 모든 advance가 들어간다), ascent, descent, 글리프마다의 bearing x와 잉크 위끝,
스트라이크의 극값(최소 왼쪽·오른쪽 side bearing, 가장 높고 낮은 잉크. 글리프 자신의 오른쪽 side bearing은 저장되지 않으므로 넓은 글리프와
좁은 글리프가 함께 있는 200폭 셀도 들어가고, '.' 하나뿐인 200폭 셀처럼 127을 넘는 최소 오른쪽 side bearing은 여전히 하한인 127로 저장된다. 글리프마다의 bearing x와 잉크 위끝이 들어가면 127을 넘을 수 있는 극값은 이것뿐이다)은 부호 있는 -128..127이라, ascent나 잉크가 기준선에서 127행보다 멀리 가는 페이스(셀이 약 127행을 넘는 것)는 그 필드를 밝히는 오류로
멈춘다. `--no-strike`는 이를 아웃라인만으로 변환하며, BDF에는 이 한계가 없다. TTF에는 페이스의
원본 폰트 라이선스가 적용된다. OFL 폰트의 Reserved Font Name은 새 패밀리 이름이 되어서는 안 된다(기본 이름은 이를 피한다).

<a id="합성-글리프--composite"></a>

### 12.1. 합성 글리프(`--composite`)

`ttf --composite`는 자모 세트의 구조를 TTF에 남긴다: 자모 조각마다 글리프 하나로 한 번만 쓰고(아웃라인과 스트라이크 비트맵,
합성된 음절이 놓는 자리에), 합성되는 음절은 모두 그 조각들의 합성(composite) 글리프가 되며, 호환 자모는 cmap이 그 조각 글리프
자체를 가리킨다. 나머지 글리프(ASCII 등)는 보통 글리프로 남는다. 완성형 페이스는 나눌 것이 없으므로 `--composite`는 보통 TTF를
쓰고 안내를 찍는다.

    python3 tools/svf2ttf.py ttf svf/dos/NEODG16A.SVF $OUT/NEODG16A-c.ttf --composite

- **아웃라인**(`glyf`): 음절의 빈 조각이 아닌 조각들을 각각 오프셋 (0, 0)에 둔 합성 글리프(조각은 셀 전체이고 dy가 없다), `hmtx`에는
  음절 자신의 advance. TrueType은 구성요소의 합집합을 그리고, 조각 아웃라인의 합집합은 합성된 음절의 `--threshold` 이상 픽셀의
  아웃라인과 같다(단계의 최댓값을 취한 뒤 문턱으로 자르는 것은 조각마다 잘라서 합치는 것과 같다). 그래서 1, 2, 8 bpp 모두 정확하다.
  첫 구성요소에 `OVERLAP_COMPOUND`를 둔다(그러면 FreeType이 합성 글리프를 오버샘플링해 그려, 정수배 사이 크기에서 두 조각이 함께
  덮는 가장자리 픽셀을 두 번 칠하지 않는다). 모든 TTF가 갖는 no-op `prep`(위)은 여기서 더 중요하다: 그것이 없으면 FreeType의 자동
  힌터가 합성 글리프의 겹친 윤곽선을 최대 반 픽셀 옮긴다(2 x ppem에서도. 32 px에서 NEODG16A의 음절 6,463개). `maxp`의 구성요소
  필드는 다시 계산된다(`maxComponentElements` 3, `maxComponentDepth` 1).
- **스트라이크**(`EBDT`): 음절은 복합(compound) 비트맵, 이미지 형식 8(small metrics, 패딩 바이트, 그리고 조각마다 글리프 id와 복합
  비트맵 왼쪽 위에서의 x / y 오프셋)이며, 형식 1 글리프들 뒤의 별도 인덱스 하위 테이블에 있다. 형식 9(big metrics)는 폰트에 없는
  세로 메트릭 때문에 음절마다 3바이트를 더한다. FreeType은 복합 비트맵을 읽는다(`ttsbit.c`): 각 구성요소의 행을 복합 비트맵에 OR한다.
  1 bpp에서는 그것이 SVF의 규칙이다. 2와 8 bpp에서는 두 가지가 다르다: FreeType은 구성요소를 x 오프셋만큼 픽셀이 아니라 비트 단위로
  밀므로 2 / 8 bpp 페이스의 조각 비트맵은 모두 펜에서 시작하고(그러면 x 오프셋은 0), 두 단계의 OR는 최댓값이 아니다(2 bpp: 1 | 2 = 3,
  페이스는 2를 그린다). 조각들이 한 픽셀에서 a | b != max(a, b)인 단계 a, b로 겹치는 음절은 펼친 형식 1 비트맵을 유지한다(아웃라인은
  합성 그대로). 요약 줄이 그 수를 센다(GOTHA16A는 `strike: 6091 compound, 5081 expanded bitmaps`). 펼친 비트맵 없이 만들면 FreeType에서
  GOTHA16A는 정확히 그 5,081 음절을(픽셀 9,487개가 단계 2 대신 3으로), NSQRB36A는 그 5,831 음절을 잘못 그린다.
  구성요소 오프셋은 부호 있는 바이트라서, 128 px를 넘는 셀에서 조각들이 127픽셀보다 멀리 떨어진 음절도 펼친 비트맵을 유지한다:
  잉크가 x 127보다 오른쪽에서 시작하는 조각은 자기 비트맵을 펜에서 시작한다(bearing x가 바이트에 들어가지 않으므로).
  `--composite`는 보통 스트라이크가 되는 모든 페이스를 변환한다.

확인(2026-11-23): 각 페이스를 `ttf`와 `ttf --composite`로 만들고, 합성 TTF를 위와 같이 `mkfont.py`로 되구워 비교했다. 모든 글리프를
Pillow로 ppem과 2 x ppem에서, freetype-py로 ppem에서(스트라이크, 그리고 `FT_LOAD_NO_BITMAP`의 아웃라인) 그려 보통 TTF의 같은 글리프와
같았다. fontTools가 읽고 모든 테이블을 풀고 다시 컴파일한다. `fc-query` / `fc-scan`이 읽는다(scalable, outline). OTS(`ots-sanitize`
9.2.0)를 통과한다. OTS는 통과시킨 폰트에서 `EBLC`/`EBDT`를 뺀다(보통 TTF도 같다): 웹 폰트를 OTS로 거르는 브라우저는 아웃라인만
그린다. 스트라이크는 위의 FreeType이 확인한다. HWP 1.x 페이스는 라이선스 노트가 없어서 두 TTF 모두 원본 폰트의 라이선스가
적용된다는 줄을 담는다(위 표와 같다):

| 페이스 | 조각 | 보통 TTF | 합성 TTF | 스트라이크: 복합 / 펼침 | 왕복 | 렌더, OTS |
|---|---|---|---|---|---|---|
| `svf/dos/NEODG16A.SVF`(1 bpp 16x16, 8/4/4 벌) | 344 | `2,038,968` | `694,384`(34 %) | 11,172 / 0 | 11,318개 중 불일치 0(빈 글리프 1: U+3161) | 같음, 통과 |
| `svf/jamo-extra/GOTHA16A.SVF`(2 bpp 16x16, 24/16/16) | 1,224 | `2,418,300` | `1,037,104`(43 %) | 6,091 / 5,081 | 11,319개 중 0 | 단계까지 같음, 통과 |
| `svf/jamo-extra/GOTHB24.SVF`(1 bpp 24x24, 24/16/16) | 1,224 | `2,796,288` | `844,780`(30 %) | 11,172 / 0 | 11,319개 중 0 | 같음, 통과 |
| `svf/dos/MARUS24.SVF`(1 bpp 24x24, 24/16/16) | 1,178 | `3,415,744` | `854,684`(25 %) | 11,172 / 0 | 11,335개 중 0 | 같음, 통과 |
| `svf/dos/NSQRB36A.SVF`(2 bpp 36x36, 24/16/16) | 1,070 | `5,901,072` | `2,432,800`(41 %) | 5,341 / 5,831 | 11,319개 중 0 | 단계까지 같음, 통과 |
| HWP 1.x `HANGUL1.PFT` 페이스 1 + `ASCII.PFT`(1 bpp 24x24, 7/2/2) | 229 | `2,849,128` | `684,916`(24 %) | 11,172 / 0 | 11,318개 중 0 | 같음, 통과 |

바닥은 음절마다의 레코드다: 조각 3개의 합성 글리프는 `glyf` 약 30바이트, `loca` 4, `hmtx` 4, `EBDT` 20, `EBLC` 4바이트이다
(NEODG16A: `glyf` 334,881, `EBDT` 227,283바이트). 그래서 11,172 음절의 합성 TTF는 이 예시에서는 조각이 작아도 0.7 MB 근처에 머물고, 펼친
2 bpp 비트맵과 큰 셀이 거기에 더해진다. `--composite`는 16-24 px에서 0.5-1.2초(NSQRB36A는 4.0초. 보통 TTF는 2.4-4.4초와 8.7초)로, 조각마다 한 번만 추적하므로
보통 TTF보다 빠르다.

**`--composite`의 한계.** FreeType(Pillow, fontconfig, freetype-py)만 확인했다. Windows(GDI, DirectWrite)나 Mac(`--apple`: 형식 8 복합
비트맵이 든 `bdat`)이 복합 비트맵을 그리는지는 시험하지 않았고, 이를 무시하는 렌더러는 ppem에서 아웃라인을 그린다. ppem의 정수배
사이에서 FreeType이 `OVERLAP_COMPOUND` 글리프를 오버샘플링해 그린 것은 보통 TTF가 받는 정확한 면적 피복도가 아니다: 20, 24 px에서는
NEODG16A와 GOTHA16A의 표본 음절(7개마다 하나)이 모두 보통 TTF처럼 그려지고, 17 px에서는 1,596개 중 303개(19 %, NEODG16A)와 454개(28 %,
GOTHA16A)가 가장자리 픽셀에서 255 중 최대 32, 42만큼 다르다. 단계가 겹치는 2, 8 bpp 음절은 펼친 비트맵을 유지한다(위). 조각에는 유니코드가 없다
(첫가끝 자모 셰이핑은 전과 같이 없다).

<a id="세트-수벌-수-정하기"></a>

<a id="벌-수-정하기"></a>

## 13. 벌 수 정하기

<a id="세트-수-정하기"></a>

자모 세트는 음절을 초성 조각 하나, 중성 조각 하나, 그리고 있으면 종성 조각 하나로 그린다. *벌*는 각 자모의 변형이고, 벌
체계는 모음, 종성, 초성의 클래스에 따라 음절마다 하나를 고른다. 벌이 많을수록 폰트를 더 가깝게 따르지만 바이트(벌마다 그
벌이 쓰이는 모든 자모의 조각)와 표 크기가 든다.

**벌 체계**(`jamoset.py --layout`. JSET 블록은 초성 32, 중성 24, 종성 16벌과 12 x 12 초성 / 종성 클래스까지, `--jset-big`은
128 / 128 / 64와 19 x 28까지 허용한다):

| 배치 | 벌 (초성 / 중성 / 종성) | 출처 | 맞춤에서(`--from-ttf`, `--from-svf`) |
|---|---|---|---|
| `621` | 6 / 2 / 1 | Apple II 시대 6x2x1 폰트 | 예 (`svf/`의 NEODG16G가 그 예) |
| `844`, `844-ihnm`, `844-hbios24` | 8 / 4 / 4 | DOS 표준(`HANGUL.FNT`). IHNM은 ㄱ ㅋ의 중성 벌을 바꾸고, HBIOS는 그 24x30 파일 | 예 |
| `1044-san` | 10 / 4 / 4 | san 1.0 | 예 |
| `hanterm-johab` | 10 / 4 / 4 (어떤 파일은 3) | hanterm의 johab BDF | 예 |
| `dkb-printer-7x2x2`, `dkb-printer-12x4x4` | 7 / 2 / 2, 12 / 4 / 4 | 도깨비 프린터 폰트 | 예 |
| `kyra-lok` | 10 / 4 / 4 | Kyrandia의 MK15.BIT | 예 |
| `hwp1` | 페이스별: SFT는 10/4/4, 7/2/2, 6/2/2; PFT는 7/2/3, 7/2/2, 5/2/2 | HWP 1.x 한글 파일 | 원본 파일만 |
| `844-hwp3` | 8 / 4 / 4 | HWP 3.0 16 px 한글 FNT에 덧붙인 자모 세트 | 예 |
| `spec` | 조합 규칙에서 유도(SPC-1500: 6 / 2 / 2) | `rawcarve.py compose` 규칙 | 원본 파일만 |
| `mac-fbit-45sets` | 폰트에서 끌어냄 (Munjo24: 20 / 15 / 4, 8 x 4 클래스) | HangulTalk 1.0 `fbit` | 원본 파일만 |
| `adaptive[:NI,NM,NF]` | 8 / 4 / 4에서 NI / NM / NF까지 (기본 32 / 24 / 12. NI 8-32, NM 4-24, NF 4-16), 12 x 12 클래스 | `jamoadapt.py`: 조각을 공유하는 음절들이 서로 다르면 벌을 나눈다 | 예 |

**벌 수를 바꾸는 옵션.** `--layout adaptive:NI,NM,NF`는 벌 수에 상한을 둔다(나누어도 더 얻는 것이 없으면 일찍 멈춘다: 시작
비용의 0.05 % 이상, 양쪽에 음절 4개 이상, `jamoadapt.py`에 고정). `jamoset.py --layout adaptive`의 클래스 한도는 12 x 12이다. `--jset-big`은 원본의 더 큰 표를 쓸 수 있게 하지만,
`adaptive`의 클래스 계산 자체를 바꾸지는 않는다. `jamovec.py master --adaptive NI,NM,NF`와 `--class-limit N`은 벡터 마스터에
같은 일을 한다(표준 한도를 넘으면 `jamovec.py render --jset-big`과 `SVF_JSET_BIG`으로 빌드한 렌더러가 필요하다. BIG 한도를 넘는 표는 시뮬레이션만 가능하다). 맞춘 뒤에는 `jamomerge.py merge --points BYTES ...`가 변형, 벌,
클래스를 바이트 예산까지 합치고([클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트)에 실행 예가 있다), `jamoexc.py`는 벌을
늘리는 대신 자주 쓰는 음절 몇 개를 통째로 저장한다(LIST 예외).

**측정**(2026-11-22): 모든 배치를 `jamoset.py --layout L --from-svf FACE --mask-font none --check`로 16 px 완성형 페이스 둘에 맞췄다.
NanumGothic Bold(`mkfont.py ... --size 16 --bpp 1`, 아웃라인 폰트의 래스터)와 OS/2의 `$korZN16.FNT`([OS/2 한글
폰트](#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기), 손으로 그린 비트맵 페이스). 페이스 전체의 바이트(ASCII 포함),
2,350 음절에 대한 IoU(2,350 중 정확), 샘플 줄의 잉크(완성형 페이스는 677과 469):

| 배치 | 쓰인 벌 | NanumGothic Bold: 바이트 | IoU (정확) | 잉크 | OS/2 ZN16: 바이트 | IoU (정확) | 잉크 |
|---|---|---:|---|---:|---:|---|---:|
| `621` | 6 / 2 / 1 | 12,788 | 0.743 (25) | 673 | 11,544 | 0.889 (206) | 471 |
| `844` | 8 / 4 / 4 | 20,648 | 0.795 (126) | 681 | 17,264 | 0.984 (1,753) | 470 |
| `1044-san` | 10 / 4 / 4 | 22,504 | 0.799 (118) | 681 | 18,788 | 0.991 (1,823) | 470 |
| `hanterm-johab` | 10 / 4 / 4 | 21,992 | 0.798 (110) | 676 | 18,608 | 0.981 (1,501) | 468 |
| `adaptive:8,4,4` | 8 / 4 / 4 | 29,544 | 0.796 (135) | 680 | 25,972 | 0.992 (2,171) | 469 |
| `adaptive:12,8,6` | 12 / 8 / 6 | 39,176 | 0.857 (205) | 678 | 33,924 | 0.999 (2,273) | 469 |
| `adaptive:16,12,8` | 16 / 12 / 8 (ZN16: 14 / 12 / 8) | 48,156 | 0.875 (291) | 672 | 41,008 | 0.999 (2,299) | 469 |
| `adaptive:24,16,12` | 24 / 16 / 12 (ZN16: 14 / 12 / 9) | 65,412 | 0.905 (414) | 677 | 42,140 | 0.999 (2,299) | 469 |
| `adaptive` (32,24,12) | 32 / 24 / 12 (ZN16: 14 / 12 / 9) | 77,560 | 0.918 (576) | 669 | 42,140 | 0.999 (2,299) | 469 |

맞춤은 하나에 0.3-0.5 s(고정 배치) 또는 2-7 s(adaptive)가 걸렸다. 완성형 페이스는 125,520과 123,328 바이트이다.

**읽는 법.** 고정 배치는 조각 수만큼의 값이 들고(621: 두 페이스에서 글리프 279 / 280개, 844: 440 / 441개, 10x4x4 배치들: 464-479개), 서로 간에 얻는 것이 적다.
`adaptive:8,4,4`는 844와 같은 수지만 12 x 12 클래스를 가진다. 표가 8.8 KB 더 들고(JSET 블록 9,921 바이트 대 1,101. JSET v2로는 2,844:
`--jset-version 2`나 `auto`. 위의 모든 adaptive 페이스가 이렇게 6-7 KB 줄어든다) 어느 음절들이 조각을 공유할지를 더 잘 고른다(OS/2:
2,171개 정확 대 1,753개). 손으로 그린 비트맵 페이스는 이미 조각의 OR에 가까워 14 / 12 / 9에서 IoU 0.999로 나누기를 멈춘다. 아웃라인
래스터는 상한까지 계속 나아지고(32 / 24 / 12에서 0.918) 끝내 정확해지지 않는다. 크기를 바꾼 아웃라인은 음절마다 조금씩 다르게
그리기 때문이다.

**권장.** 먼저 `844`로 맞추고 IoU를 읽어라. 약 0.98 이상(조각으로 설계된 비트맵 페이스, DOS 폰트, ROM)이면 `844`를 두어라. 벌을 더해도
얻는 것이 거의 없다. 그 아래 약 0.9까지는 `adaptive:12,8,6`을 시도하라. 844 크기의 약 두 배로 벌을 늘려 얻을 것의 대부분을 얻는다.
844로 0.8인 아웃라인 폰트의 래스터는 전체 `adaptive` 예산을 써야 0.9에 닿고, 그러면 완성형 페이스의 60 %를 넘는다. 그럴 때는 대개
완성형 페이스, 또는 844 자모 세트에 LIST 예외 몇 개(`jamoexc.py`)를 두는 편이 바이트를 더 잘 쓴다. 예산이 정해진 대상에는 넉넉히 맞춘 뒤
`jamomerge.py merge --points`로 깎아라. 어느 경우든 결과를 눈으로 보라(`svfline.py line`, `web/` 피커). IoU는 어느 음절이 틀렸는지
보여 주지 않는다.

<a id="데스크톱-앱과-maker-경로"></a>

## 14. 데스크톱 앱과 maker 경로

UI 작업 순서는 [maker 데스크톱](maker-desktop.ko.md), 렌더 미리보기는 [데스크톱 앱](desktop-app.ko.md)을 참고한다.

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
| 자모, `mask fit` | GSUB 자모와 쓸 수 있는 마스크가 있는 outline 또는 outline-composite(1 bpp) | `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --mask-font SRC --no-clean --check -o OUT [--pylib DIR]` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 2: 결합 자모 셰이핑](#truetype와-opentype-폰트에서-만드는-자모-세트) |
| 자모, `vector fit` | outline, outline-composite | `jamovec.py master SRC -o M.json [--adaptive]`(`--components` 없음) 다음 같은 `render` | [TrueType와 OpenType 폰트에서 만드는 자모 세트, 방법 3: 완성형 음절에 맞추기](#truetype와-opentype-폰트에서-만드는-자모-세트) (`--components` 없는 `jamovec.py master`) |
| 완성형, `johab844` | dos-raw, 정확히 11,520 바이트(16 px 8x4x4) | `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng E]`(maker는 베이스를 `svf/` 아래에서 찾는다) | [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트) |
| 자모, `dos raw` | dos-raw | `jamoset.py SRC --layout L --check -o OUT [--eng E] [--face 0\|1]`(`--face`는 도깨비 프린터 레이아웃용) | [그 밖의 DOS 시대 한글 폰트](#그-밖의-dos-시대-한글-폰트) |
| 자모, `hanterm` | bdf-johab | `jamoset.py SRC --layout hanterm-johab --check -o OUT [--eng E]` | [hanterm](#hanterm) |
| 완성형, `bdfface` | bdf-ksc5601(BDF, 또는 `pcf-bdf` 단계를 거친 PCF) | `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST -o OUT`(`WxH` = BDF의 박스) | [KS C 5601 BDF와 PCF](#ks-c-5601-bdf와-pcf) |
| 자모, `bdfface + from-svf fit` | bdf-ksc5601 | `bdfface.py` 페이스 다음 `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS C 5601 BDF와 PCF](#ks-c-5601-bdf와-pcf) |
| 자모, `mac fbit 1.0` | mac-fbit1 | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| 자모, `hwp1` | hwp1(HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT`의 페이스; 로컬 모드) | `jamoset.py SRC --layout hwp1 --face N --check -o OUT [--eng E]` | [HWP 1.x와 2.x 폰트](#hwp-1x와-2x-폰트) |
| 완성형, `hwp bdf + mkfont` | hwp1, ks-raw(HWP 3.0 한글 FNT는 로컬 모드; 헤더 없는 KS X 1001 덤프) | `hwpfont.py bdf SRC [--face N] [--syllables all] [--ascii E] -o hwp.bdf`, `mkfont.py hwp.bdf mkfont.tmp --size S --bpp 1 --unicode R`, `svf2to3.py mkfont.tmp OUT --profile default`(`E`가 없으면 범위에서 `ascii`를 뺀다) | [HWP 1.x와 2.x 폰트](#hwp-1x와-2x-폰트), [KS X 1001 원시 덤프](#ks-x-1001-원시-덤프) |
| 자모, `hwp3 844` | 8x4x4 벌 체계가 있는 ks-raw(HWP 3.0 `HAN16_*.FNT`) | `jamoset.py SRC --layout 844-hwp3 --check -o OUT [--eng E]` | [HWP 3.0 FNT 폰트](#hwp-30-fnt-폰트) |
| 자모, `hwp bdf + from-svf fit` | ks-raw | `hwp bdf + mkfont` 페이스를 `precomposed.svf`로, 다음 `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS X 1001 원시 덤프](#ks-x-1001-원시-덤프) |
| 자모, `mac fbit 7.1 direct` / `derived` | mac-fbit3 + HTBL 1 | `macfbit_svf.py build FBIT HTBL -o OUT --mode direct\|derived [--latin SUITCASE]` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| 완성형, `mac fbit 7.1 bdf + mkfont` | mac-fbit3 + HTBL 1 | `macfbit3.py bdf FBIT HTBL NAME mac.bdf`, `srcprep.py bdf-pixel-size mac.bdf mac-sized.bdf --size S`, `mkfont.py mac-sized.bdf mkfont.tmp --size S --bpp 1 --unicode ...`, `svf2to3.py ... --profile default` | [클래식 Mac 한글 비트맵 폰트](#클래식-mac-한글-비트맵-폰트) |
| 완성형 또는 자모, `copy` | svf-precomposed, svf-jamo | 업로드된 그대로 쓰면 없음. v2 페이스나 요청한 JSET 변경에는 `svf2to3.py SRC OUT --jset-version V --check` | [기존 SVF](#기존-svf) |
| 완성형 또는 자모, `svf2ttf` | svf-precomposed, svf-jamo | `copy`가 읽는 페이스를 아래의 내보내기로만 쓴다. SVF는 쓰지 않음 | [SVF 페이스를 다시 TTF 비트맵 폰트로](#svf-페이스를-다시-ttf-비트맵-폰트로) |
| 완성형, `bdfface`; 자모, `bdfface + from-svf fit` | recipe(`maker/recipes/`의 알려진 ROM 세트, 로컬 모드) | 레시피의 한글 항목과 영문 항목을 `rawcarve.py bdf`로, `bdfface.py --hangul H --ascii A --cell WxH --chars-from LIST -o OUT`. fit은 그 페이스를 `precomposed.svf`로 만든 뒤 `jamoset.py --layout L --from-svf precomposed.svf --mask-font none [--eng E] --check -o OUT`. 그 앞에 세트 파일들의 `rawcarve.py region --group ...`(경로를 통째로: 폴더 이름의 쉼표도 그대로), 조합 항목은 `rawcarve.py compose`, 타일 속 영문 폰트는 `ink` + `eng` | [한글 VGA 폰트 ROM (86Box)](#한글-vga-폰트-rom-86box), [MAME 폰트 ROM](#mame-세트의-한글-폰트-rom) |
| 자모, `spec` | recipe(SPC-1500) | `rawcarve.py region ...`, `rawcarve.py eng REGION ...`, `jamoset.py --layout spec --spec spc1500 REGION --eng E --check -o OUT` | [삼성 SPC-1500](#삼성-spc-1500-반전된-rom-네-개의-자모-세트정확) |
| 자모, `dos raw` | recipe(ROM 속 raw 세트: X Se Dae Quiz) | `rawcarve.py region`, `ink`, `cut`(raw 폰트), `ink` + `eng`(영문 폰트), `jamoset.py RAW --layout L --eng E --check -o OUT` | [X Se Dae Quiz](#x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용) |
| 자모, `from-svf fit` | svf-precomposed, 1 bpp | `[svf2to3.py ... source-v3.svf]` 다음 `jamoset.py --layout L --from-svf SRC --check -o OUT [--eng E]` | [기존 SVF](#기존-svf) |

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

위 레시피의 독점 원본 사본에 같은 점검을 했다(2026-11-22. 자세한 것은 각 레시피에): 원시 DOS 폰트는 `dos-raw`에 `dos raw`(11,520 바이트짜리는 `johab844`도),
`johabm16.bdf`는 `bdf-johab`에 `hanterm`, `batang24.bdf`는 `bdf-ksc5601`에 `bdfface`와 `bdfface + from-svf fit`, 스트라이크가 있는 굴림과 Mac Seoul은
`outline-composite` / `outline`에 `mkfont`(비트맵 전용 Seoul은 `bitmap`에 `mkfont`만), Windows FON은 경로 없이 레이블만("no Unicode character map, mkfont cannot read it"),
HWP 1.x, HWP 3.0, KS X 1001 덤프 파일은 각 레시피대로(2026-11-23: 한글 파일 하나에 `hwp1` 항목 셋과 `hwp1`, `hwp bdf + mkfont`; `ks-raw`에
`hwp bdf + mkfont`, 16 px HWP 3.0 FNT에는 `hwp3 844`, 그리고 실험적인 `hwp bdf + from-svf fit`; 여기서 읽는 레이아웃이 아닌 `.PFT`, 예컨대 태백의
`HANJA24.PFT`는 `hwp-pft` "other"), 로컬 모드의 Mac 폰트는 위와 같다(1.0 폰트는 `mac-fbit1`에 `mac fbit 1.0`). `mask fit` 행은 `mask_ok`를 설정하면
(서버가 `freetype-py`와 `uharfbuzz`를 import할 수 있을 때 설정한다) neodgm.ttf, Noto Sans CJK KR, 맑은 고딕에 나타난다.

<a id="svf의-페이스"></a>

## 15. svf/의 페이스

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

### 15.1. 완성형 글리프 레시피 (`mkfont` 행)

    python3 tools/mkfont.py SOURCE.ttf OUT.tmp --size S --cell H --width W --bpp B --ascent A --clip-cell \
        [--mono-hint] [--fallback-ttf OTHER.ttf] --only-listed --unicode CODEPOINTS
    python3 tools/svf2to3.py OUT.tmp OUT.SVF --profile default

- `--size S`: 폰트를 그리는 픽셀 크기(Pillow/FreeType `truetype(font, S)`). 페이스 이름에 이 값이 들어간다(`GBATB23` = Gowun
  Batang Bold 23 px).
- `--cell H --width W`: 셀. 크기보다 클 수 있다(게임의 줄 간격. `GBATB17B`는 26x24 셀 안의 17 px).
- `--bpp B`: 1(절반 피복도에서 자르기, 또는 `--mono-hint`를 준 FreeType의 모노크롬 렌더러) 또는 2(피복도 4단계:
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

<a id="완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행"></a>

### 15.2. 완성형 글리프에서 자모 세트를 만드는 레시피 (`jamoset` 행)

    python3 tools/mkfont.py ttf/neodgm/neodgm.ttf $OUT/PRE.svf --size 16 --cell 16 --width 16 --bpp 1 --ascent 12 \
        --clip-cell --unicode ascii,ksx1001-hangul
    python3 tools/jamoset.py --from-svf $OUT/PRE.svf --mask-font none -o $OUT/NEODG16A.SVF --layout 844

`--from-svf`는 1 bpp 페이스의 완성형 음절을 벌 체계(여기서는 8x4x4)의 조각으로 분해하고, 그 밖의 글리프는 그대로 둔다.
Neo Dunggeunmo는 그 자체가 8x4x4 조각의 OR로 그려져 있어서 맞춤이 정확하고(IoU 1.000) 11,172개 음절이 모두 조합된다.
NEODG16D/E/F/32/32A는 셀만 다른 같은 방식이다(22x22, 18x24, 20x24; 36x36 안의 32 px와 46x54). NEODG16G는 6x2x1 벌 체계이다
(`--layout 621 --advance 0 --check`, `--ascent`/`--clip-cell` 없음: mkfont의 ascent 12), 10,684 바이트이며 MCU 예제용 작은
페이스이다(완성형 변환 결과와의 IoU 0.958).

<a id="패밀리"></a>

### 15.3. 패밀리

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

### 15.4. 레시피 없는 페이스

- `svf/iolo/SANS8J.SVF`: iolo 레거시 8x4x4 SANS `.fnt`의 외부 변환본이며 원본 파일은 포함하지 않는다.

이 페이스들은 빌드된 그대로 보관한다. 이유는 `tools/build/faces.tsv`의 행에 적혀 있다. 이는 재현상의 한계이다.
원본별 라이선스는 [LICENCES.tsv](../web/LICENCES.tsv)를 따르고, iolo의 이중 라이선스 해석 문제는
[IOLO.TXT](../svf/iolo/IOLO.TXT)를 참고한다.

- **연구 파이프라인으로 만든 자모 세트** (`svf/dos`의 PAPER*, PAPLB*, PAPLG18, MARU*, GOTHB18A, NSQR*와 `svf/jamo-extra`의 모든
  페이스): 음절 윤곽선을 초성 / 중성 / 종성 벡터 조각으로 분리하고, 래스터화하고, 사용 가중치와 함께 24/16/16 벌 및 최대
  12 x 12 클래스로 병합하는 일을, 이 저장소에 속하지 않는 연구 파이프라인이 했다(`svf/dos/PAPLG.TXT`, `PAPMARU.TXT`,
  `svf/jamo-extra/FACES.TSV`에 실행과 품질이 기록되어 있다). 여기서 가장 가까운 도구는 `jamovec.py`(벡터 분리)와
  `jamoset.py --layout adaptive`(분할 벌)이다. [TrueType와 OpenType 폰트에서 만드는 자모 세트](#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- **외곽선 페이스** NEODG16O, GBATB17O: 16 / 17 px 글리프를 2 px 팽창시킨 것(내레이션 아래에서 검게 그려짐). 게임 전용 장식
  스크립트로 만들었으며 그 스크립트는 이 저장소에 없다.
- **NEODG16B, NEODG16C**: 완성형 원본이 한 게임의 문자만 변환한 것이었던 Neo Dunggeunmo의 8x4x4 세트이다.
  KS X 1001 전체에 `jamoset.py --from-svf`를 적용하면 다른 조각에 맞춰진다(NEODG16B의 글리프 441개 중 71개가 다르다).
- **DIPHY36**: 36 px 1 bpp의 Diphylleia Regular로, 외부 파이프라인이 래스터화했다. Diphylleia의 현재 릴리스에 `mkfont.py`를
  쓰면 다른 픽셀이 그려진다(글리프 2,359개 중 2,358개).
- **PAPLG16**: Paperlogy 1.000에 `mkfont.py Paperlogy-4Regular.ttf --size 16 --cell 18 --width 18 --bpp 2 --clip-cell --ascent 14
  --unicode ascii,2026,2122,3131-318e --only-listed --space-advance 6 --punct-extra 1`. 1.001 릴리스는 글리프 149개 중 81개를
  다르게 그리며, 어느 쪽도 `ttf/`에 없다.

<a id="참고"></a>

## 16. 참고

<a id="ks-x-1001"></a>

### 16.1. KS X 1001

KS X 1001(예전 이름 KS C 5601)에는 완성형 한글 음절 2,350자(행 0xB0-0xC8, 행마다 94자), 호환 자모 51개(행 0xA4:
U+3131..U+3163), 기호, 한자가 있다. 도구:

- `mkfont.py --unicode` 이름: `ksx1001-hangul`(2,350자), `ksx1001-nohanja`(기호, 자모, 2,350자), `ksx1001-symbols`,
  `ksx1001`(한자 포함), `hangul` / `cp949-hangul`(11,172자 전부), `cp949`(CP949가 디코딩하는 모든 것), `jamo`(U+3131..U+318E,
  94개). `--limit`은 `--chars-from` 목록과 이들 중 하나의 교집합을 취하고, `--require`는 폰트에 없는 코드 포인트를 거부한다.
- `jamoset.ks_x_1001_syllables()`(음절 인덱스)와 품질 보고서(`ks2350` 열)는 같은 집합을 쓴다. `tools/test_recipes.py`가 둘이 euc_kr
  코덱의 행과 같음을 점검한다.
- 완전한 JSET 표는 음절 11,172개를 모두 조합한다. 직접 매핑하는 JMAP 페이스는 일부만 지원할 수 있다. 호환 자모는 표가 조각을 지정하면 조각으로, 아니면 글리프 전체로 그린다.
  `jamoset.py --blank-compat`은 글리프 전체가 있는 곳에서 그것을 쓰도록 페이스를 다시 쓴다.
- `facecheck.py`는 페이스를 매니페스트와 대조하고(`verify`) 맵을 만든다(`mapfaces`). 페이스별 피복도는 웹 인덱스에 있다
  (`web/mkindex.py`: `hangul` = 그려진 KS 음절, `subset` = 자모 세트와 라틴 전용 페이스를 제외하고 KS 음절이 2,350자보다 적은 페이스).

<a id="인코딩"></a>

### 16.2. 인코딩

EUC-KR / 완성형 바이트 쌍 = GL 코드 + 0x8080 (`가` = B0A1 = GL 3021). Python: `bytes((0xB0,0xA1)).decode("euc_kr")`. 조합형(Python `johab` 코덱): 16비트 코드 `1 iiiii mmmmm fffff`에 채움 값(초성 2 = ㄱ, 중성 3 = ㅏ, 종성 1 = 없음)이 있고 `가` = 8861;
`bytes((0x88,0x61)).decode("johab")`. 유니코드 음절 = 0xAC00 + (초성 x 21 + 중성) x 28 + 종성 (자모 인덱스는 0부터). [한글 조합과 인코딩](#ref-encoding)을 참고한다. `tools/test_recipes.py`가 이 예시를 점검한다.

<a id="알려진-한계"></a>

### 16.3. 알려진 한계

- `jamoset.py`의 기본 `--binarize mono`에는 `freetype-py`가 필요하다(마스크 폰트에는 `uharfbuzz`도 필요하다). 레시피는 `--binarize threshold`를 쓰고, `--mask-font none`은 1 bpp 맞춤이 `$JAMOSET_MASK_FONT`에
  좌우되지 않게 한다. [자모 세트](#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- 실행 시간(이 호스트, 코어 하나): 16 px 아웃라인 폰트의 1 bpp `threshold` 맞춤은 약 12초, 2 bpp는 약 73초, Gowun Batang adaptive 20 px는
  약 90초이다. 위의 2 bpp 페이스는 같은 1 bpp 페이스의 약 1.5-1.6배, 자모 세트는 약 6분의 1이다.
- `mkfont.py --bpp 2`는 흑백 비트맵을 원래 크기의 2 bpp로 저장할 수 있지만 중간 피복도를 새로 만들지는 않는다. `svfscale.py --bpp 2`는 더 작은 크기의 2 bpp
  페이스를 만들고([고해상도 비트맵 폰트에서 저해상도 페이스 만들기](#고해상도-비트맵-폰트에서-저해상도-페이스-만들기)), 비트맵에서 2 bpp 자모 세트를 만드는 도구는 없다.
- `mkfont.py`는 요약을 한국어로 출력한다. 필드 이름을 찾으려고 그 stdout을 파싱하지 말 것.
- 도구 전반의 알려진 빈틈: [tools.ko.md](tools.ko.md#도구에-남은-빈틈)의 "도구에 남은 빈틈".

<a id="svf에-페이스-추가하기"></a>

## 17. svf/에 페이스 추가하기

위의 레시피로 페이스를 만들고, 점검하고([페이스 점검](#페이스-점검)), 다음을 추가한다.

- `svf/`에 그 옆의 라이선스 텍스트;
- `web/LICENCES.tsv`의 행과 `web/FAMILIES.tsv`의 행;
- `tools/build/faces.tsv`의 행(레시피를 적거나, 방법 `none`과 그 이유를 적음).

그렇지 않으면 `tools/test_build_faces.py`와 `tools/test_web_picker.py`가 실패한다. maker는 이 표들에 넣을 줄을 만들어 준다
(`build-<id>/LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`).

<a id="참고-문헌"></a>

## 18. 참고 문헌

- <a id="ref-opentype"></a>**OpenType 글리프, 셰이핑, 비트맵 스트라이크**: [glyf](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf), [EBDT](https://learn.microsoft.com/en-us/typography/opentype/spec/ebdt), [EBLC](https://learn.microsoft.com/en-us/typography/opentype/spec/eblc), [Hangul shaping](https://learn.microsoft.com/en-us/typography/script-development/hangul).
- <a id="ref-freetype"></a>**FreeType 비트맵 및 Windows FNT 지원**: [Font formats](https://freetype.org/freetype2/docs/reference/ft2-font_formats.html), [Windows FNT driver](https://gitlab.freedesktop.org/freetype/freetype/-/blob/master/src/winfonts/winfnt.c), [TrueType bitmap loader](https://gitlab.freedesktop.org/freetype/freetype/-/blob/master/src/sfnt/ttsbit.c).
- <a id="ref-fonttools"></a>**fontTools 가변 폰트 인스턴스 생성기**: [varLib.instancer](https://fonttools.readthedocs.io/en/latest/varLib/instancer.html).
- <a id="ref-encoding"></a>**한글 조합과 인코딩**: [Unicode Hangul algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/), [Python standard encodings](https://docs.python.org/3/library/codecs.html#standard-encodings), [KS C 5601 mapping](https://www.unicode.org/Public/MAPPINGS/OBSOLETE/EASTASIA/KSC/KSC5601.TXT).
- <a id="ref-bdf"></a>**BDF 형식**: [Adobe BDF 2.2](https://adobe-type-tools.github.io/font-tech-notes/pdfs/5005.BDF_Spec.pdf).
- <a id="ref-apple"></a>**Apple 폰트 표와 리소스 포크**: [TrueType reference manual](https://developer.apple.com/fonts/TrueType-Reference-Manual/), [Resource Manager](https://dev.os9.ca/techpubs/mac/MoreToolbox/MoreToolbox-9.html).
- <a id="ref-86box"></a>**86Box 한글 VGA ROM 메타데이터와 렌더링**: [ROM set](https://github.com/86Box/roms), [SVGA renderer](https://raw.githubusercontent.com/86Box/86Box/master/src/video/vid_svga_render.c).
- <a id="ref-msx"></a>**한국 MSX 기종과 openMSX**: MSX Wiki [Daewoo CPC-300](https://www.msx.org/wiki/Daewoo_CPC-300), [Daewoo CPC-400S](https://www.msx.org/wiki/Daewoo_CPC-400S), [Daewoo DPC-200](https://www.msx.org/wiki/Daewoo_DPC-200), [Goldstar FC-80U](https://www.msx.org/wiki/Goldstar_FC-80U), [Daewoo machines](https://www.msx.org/wiki/Category:Daewoo). [openMSX MSXKanji.cc](https://raw.githubusercontent.com/openMSX/openMSX/master/src/MSXKanji.cc)(`hangul` 폰트 장치), [openMSX console commands](https://openmsx.org/manual/commands.html). msx.org 포럼 [Daewoo CPC-400S hanja display bug](https://www.msx.org/forum/msx-talk/openmsx/daewoo-cpc-400s-hanja-display-bug)(256 KB 폰트 ROM). [file-hunter system ROMs](https://download.file-hunter.com/System%20ROMs/).
- <a id="ref-mame"></a>**MAME 기종 정보, ROM 로드, 타일 배치**: [SPC-1500](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/samsung/spc1500.cpp), [tumbleb](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/dataeast/tumbleb.cpp), [raiden2](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/seibu/raiden2.cpp), [midas](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/snk/midas.cpp), [neogeo](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/snk/neogeo.cpp), [Neo Geo sprites](https://raw.githubusercontent.com/mamedev/mame/master/src/mame/snk/neogeo_spr.cpp).
- <a id="ref-fonts"></a>**폰트 원본과 라이선스**: [Noto CJK](https://github.com/notofonts/noto-cjk), [Google Fonts](https://github.com/google/fonts/tree/main/ofl), [Un fonts (Debian)](https://sources.debian.org/src/fonts-unfonts-core/), [X11 bitmap fonts](https://www.cl.cam.ac.uk/~mgk25/ucs-fonts.html), [HBF](https://www.ibiblio.org/pub/packages/ccic/software/fonts/README), [SIL OFL 1.1](https://openfontlicense.org/open-font-license-official-text/).
- <a id="ref-fontconfig"></a>**fontconfig 설치와 언어 일치**: [User guide](https://fontconfig.pages.freedesktop.org/fontconfig/fontconfig-user.html), [Korean orthography](https://gitlab.freedesktop.org/fontconfig/fontconfig/-/blob/main/fc-lang/ko.orth).
- <a id="ref-7zip"></a>**7-Zip 출력 폴더 스위치**: [7-Zip -o](https://7-zip.opensource.jp/chm/cmdline/switches/output_dir.htm).
- 그 밖의 패밀리 원본: [Gowun Batang](https://github.com/yangheeryu/Gowun-Batang), [Neo Dunggeunmo](https://github.com/neodgm/neodgm), [Black Han Sans](https://github.com/zesstype/Black-Han-Sans), [Coustard](https://github.com/googlefonts/coustardFont), [Diphylleia](https://github.com/JAMO-TYPEFACE/Diphylleia), [Paperlogy](https://github.com/fonts-archive/Paperlogy), [NAVER](https://hangeul.naver.com), [Neo Dunggeunmo Pro](https://github.com/neodgm/neodgm-pro).
- 역사적 입력 자료 설명: [HWP 1.20](https://archive.org/details/hwp-120), [HWP 3.0 DOS](https://archive.org/details/hwp-30-dos), [MAME ROM set metadata](https://archive.org/details/mame-roms-non-merged), [iolo 8x4x4](https://github.com/iolo/8x4x4-fonts).

[프로젝트 개요](../README.ko.md) · [도구 설명서](tools.ko.md)
