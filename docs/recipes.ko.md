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
([완성형 페이스](recipes/outline-fonts.ko.md#완성형-페이스-mkfontpy)). 다른 대상 프로필은 [렌더러 설계](../spec/renderer-design.ko.md)를 참고한다.

수치 예시는 명시한 입력과 설정으로 측정한 값이다. 파일 크기와 실행 시간은 도구 및 폰트 버전에 따라 달라질 수 있다.
*Synthetic* 예시는 테스트에서 만든 입력을 쓴다. 맞춤의 IoU는 맞춤 보고서에서 얻는다. `--check`는 조합과 표의 일관성을
점검하며, 최소 IoU를 요구하지 않는다.

목차:

- [레시피 문서](#레시피-문서)
- [빠른 시작: 입력 종류별](#빠른-시작-입력-종류별)
- [페이스 점검](#페이스-점검)
- [참고](#참고)
- [참고 문헌](#참고-문헌)
- [옮긴 절](#옮긴-절)

<a id="레시피-문서"></a>

## 레시피 문서

레시피 문서마다 입력 한 종류를 명령과 측정 결과와 함께 다룬다. 아래의 빠른 시작이 입력 종류마다 문서와 절을 알려 준다. 점검, KS X 1001과 인코딩 참고, 참고 문헌은 이 문서에 있다.

| 문서 | 다루는 내용 |
|---|---|
| [아웃라인 폰트](recipes/outline-fonts.ko.md) | TTF, OTF, TTC/OTC, 가변 폰트, Mac TrueType; 아웃라인 폰트와 자모를 가진 폰트에서 만드는 자모 세트; 2 bpp 안티앨리어싱; 기준선과 클리핑 |
| [비트맵 폰트](recipes/bitmap-fonts.ko.md) | BDF/PCF(ISO 10646, KS C 5601), HBF, Windows FNT/FON, 내장 스트라이크; 고해상도 비트맵 폰트에서 만드는 저해상도 페이스 |
| [X 윈도와 유닉스의 한글 폰트](recipes/x-window.ko.md) | X와 유닉스 한글 폰트를 계열별로: 대우, 백묵, 한양, KAIST, 미지, jfbterm, zhcon(KS C 5601 BDF/PCF), hanterm의 johab844-1과 johab-1 자모 세트 폰트; 라이선스와 샘플 |
| [DOS 시대 원시 폰트](recipes/dos-fonts.ko.md) | 원시 자모 조각 폰트(8x4x4, san, 도깨비, Kyrandia), HWP 1.x/2.x와 3.0 폰트, KS X 1001 원시 덤프 |
| [프로그램과 드라이버 안의 폰트](recipes/programs-and-drivers.ko.md) | Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기: 도구, 프롬프트, NKP, 도깨비 |
| [한글 VGA 폰트 ROM (86Box)](recipes/rom-86box.ko.md) | 86Box ROM 세트의 한글 VGA 폰트 ROM(Trigem, 가산, ATI) |
| [한국 MSX 폰트 (MSX2와 MSX1)](recipes/rom-msx.ko.md) | MSX2 대우 자모 세트, CPC-400S 완성형 폰트, MSX1 BIOS 셀과 openMSX 수집 |
| [MAME 세트의 한글 폰트 ROM](recipes/rom-mame.ko.md) | MAME 세트: SPC-1500 자모 세트, 퀴즈 게임의 스프라이트 폰트, 풀지 못한 세트 |
| [OS/2 한글 폰트(완성형)](recipes/os2.ko.md) | OS/2 System DBCS 폰트(완성형)에서 완성형 페이스와 자모 세트 |
| [Windows 한글 비트맵 폰트 (3.1, 95, XP)](recipes/windows.ko.md) | Windows 3.1 / 95 TBM 폰트(BT16, BT20, GULIM16, GULIM12), Windows 95 `HFONT.SYS`, Windows 95와 XP `gulim.ttc` / `batang.ttc`의 내장 스트라이크; 샘플 그림 |
| [클래식 Mac 한글 비트맵 폰트](recipes/classic-mac.ko.md) | HangulTalk 1.0과 7.1 `fbit` 비트맵 폰트 |
| [기존 SVF, 그리고 SVF에서 다시 TTF로](recipes/svf-and-ttf.ko.md) | 기존 SVF(dy, 자모 세트로 다시 굽기); SVF 페이스를 다시 TTF나 BDF 폰트로, 합성 글리프 |
| [벌 수 정하기](recipes/sets.ko.md) | 자모 세트의 벌을 몇 개로 할지, 그 비용 |
| [자모 분리](jamo-split.ko.md) | 모든 자모 세트 맞춤의 배경: 완성형 글꼴에 자모 세트를 맞추는 방식, 경우별 처리, 잘 맞지 않는 것 |
| [데스크톱 앱과 maker 경로](recipes/desktop-routes.ko.md) | maker의 경로 표: 경로마다 그 명령줄 |
| [svf/의 페이스](recipes/svf-faces.ko.md) | svf/의 페이스를 만들고 다시 빌드하는 법; svf/에 페이스 추가하기 |

<a id="빠른-시작-입력-종류별"></a>

<a id="1-빠른-시작-입력-종류별"></a>

## 빠른 시작: 입력 종류별

가진 것을 찾아라. 행이 방법과 명령이 있는 절을 알려 준다. "완성형"은 완성형 페이스(음절마다 글리프, 1 또는 2 bpp), "자모"는 자모
세트(조각과 표, 1 bpp 또는 2 bpp, 크기는 약 6분의 1)이다.

| 가진 것 | 완성형 | 자모 | 절 |
|---|---|---|---|
| TTF, 또는 유니코드 cmap이 있는 OTF(CFF) | `mkfont.py`(1, 2 bpp) 다음 `svf2to3.py --profile default` | `jamoset.py --from-ttf`(1 bpp: `--binarize threshold --mask-font none`, 2 bpp: `--bpp 2`); 합성 음절 폰트에는 `jamovec.py` | [아웃라인 폰트](recipes/outline-fonts.ko.md#아웃라인-폰트) |
| TTC / OTC (Noto CJK) | `srcprep.py ttc-face`로 일반 폰트를 만든 뒤 위와 같이 | 위와 같이 | [TTC와 OTC](recipes/outline-fonts.ko.md#ttc와-otc) |
| 가변 폰트 | `fontTools.varLib.instancer` 다음 위와 같이 | 위와 같이 | [가변 폰트](recipes/outline-fonts.ko.md#가변-폰트) |
| Mac TrueType(`.dfont`, suitcase, 한글 전용 cmap) | `macsfnt.py extract` / `unicode` 다음 위와 같이 | 위와 같이 | [Mac 형식 TrueType](recipes/outline-fonts.ko.md#mac-형식-truetype) |
| 내장 스트라이크(`EBDT`, `bdat`)가 있는 아웃라인 폰트 | 스트라이크의 크기로 `mkfont.py --size`, 1 bpp | 없음 | [내장 비트맵 스트라이크](recipes/bitmap-fonts.ko.md#내장-비트맵-스트라이크) |
| 유니코드(`ISO10646`) BDF 또는 PCF | 파일 자신의 픽셀 크기로 `mkfont.py`, 1 bpp | `jamoset.py --from-svf`로 맞춤 | [ISO 10646 BDF와 PCF](recipes/bitmap-fonts.ko.md#iso-10646-bdf와-pcf) |
| KS C 5601 / KS X 1001(X Window) BDF 또는 PCF | `srcprep.py pcf-bdf`(PCF만) 다음 `bdfface.py`(기호는 `--symbols`) | `jamoset.py --from-svf` | [KS C 5601 BDF와 PCF](recipes/bitmap-fonts.ko.md#ks-c-5601-bdf와-pcf). 폰트 계열별: [X 윈도와 유닉스의 한글 폰트](recipes/x-window.ko.md#x-윈도와-유닉스의-한글-폰트) |
| hanterm johab-1 BDF(`10-6-6`, 글리프 529개) | 없음 | `jamoset.py --layout hanterm-johab` | [hanterm 조합형 폰트](recipes/x-window.ko.md#hanterm) |
| hanterm johab844-1 BDF(`8-4-4`, 글리프 360개) | 없음 | `jamoset.py --layout hanterm-844`(정확) | [hanterm 조합형 폰트](recipes/x-window.ko.md#hanterm) |
| HBF | `bdfface.py`의 ASCII 절반으로만 | 없음 | [HBF](recipes/bitmap-fonts.ko.md#hbf) |
| Windows `.FNT` / `.FON` | 리더 없음(FreeType이 유니코드 맵을 주지 않는다. 먼저 바깥 도구로 BDF로 변환하라) | 없음 | [Windows FNT와 FON](recipes/bitmap-fonts.ko.md#windows-fnt와-fon) |
| DOS 원시 자모 조각 폰트(8x4x4 `HANGUL.FNT`, san, 도깨비, Kyra...) | `johab844.py`(16 px 8x4x4) | `jamoset.py --layout L` | [DOS 시대 원시 폰트](recipes/dos-fonts.ko.md#dos-시대-원시-폰트) |
| IBM PC DOS 한글 HBIOS V3.0 폰트(`$KGOZN16.FNT`, `$KMYZN16.FNT`, `$KMYZN24.FNT`, 영문 `$K*HN*.FNT`, 기호와 한자 `$KSPHJ*.FNT`) | `$KMYZN24.FNT`의 음절 2,350자: `rawcarve.py bdf --offset 32409 --stride 90 --dense` + `bdfface.py` | `jamoset.py --layout 844`(16 px) / `844-hbios24`(24 px), `--eng`는 같은 디스크의 SBCS 파일 | [IBM PC DOS 한글 (HBIOS V3.0)](recipes/dos-fonts.ko.md#ibm-pc-dos-한글-hbios-v30) |
| HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT` | `hwpfont.py bdf --face N` 다음 `mkfont.py` | `jamoset.py --layout hwp1 --face N`(HWP 자체 규칙, 정확) | [HWP 1.x와 2.x 폰트](recipes/dos-fonts.ko.md#hwp-1x와-2x-폰트) |
| HWP 3.0 `HAN*.FNT`(음절 2,350개, 16 px는 8x4x4 벌 체계 추가) | `hwpfont.py bdf` 다음 `mkfont.py` | `jamoset.py --layout 844-hwp3`(16 px), 그 밖에는 `--from-svf` | [HWP 3.0 FNT 폰트](recipes/dos-fonts.ko.md#hwp-30-fnt-폰트) |
| KS X 1001 원시 덤프(코드 순서의 음절 2,350개, 또는 94 x 94 표) | `hwpfont.py bdf`(16-48 px 덤프), 또는 `rawcarve.py bdf --dense` / `--grid`; 다음 `mkfont.py`나 `bdfface.py` | `jamoset.py --from-svf` | [KS X 1001 원시 덤프](recipes/dos-fonts.ko.md#ks-x-1001-원시-덤프) |
| 프로그램이나 ROM 안의 폰트(DOS 드라이버나 TSR, 워드프로세서, 한글 VGA BIOS + 폰트 ROM) | 찾기는 `binscan.py`, 잘라 내기는 `rawcarve.py`(원시, BDF, 또는 드라이버 규칙대로 조합), 다음 `bdfface.py` | 잘라 낸 원시 폰트에 `jamoset.py --layout 844`, 또는 `--from-svf` | [Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기](recipes/programs-and-drivers.ko.md#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기) |
| 한국 MSX ROM(대우, 금성: MSX2 SUB-ROM, CPC-400S 폰트 ROM, MSX1 BIOS) | `rawcarve.py compose` + `bdfface.py`(MSX2), `msxfont.py kfn-map` + `rawcarve.py bdf --chars map` + `bdfface.py`(CPC-400S), `msxfont.py msx1` + `mkfont.py`(MSX1) | `jamoset.py --layout spec --spec tools/specs/msx2-daewoo.json`(MSX2, 정확) | [한국 MSX 폰트](recipes/rom-msx.ko.md#한국-msx-폰트-msx2와-msx1) |
| MAME 세트에 든 한국 기계나 아케이드 게임의 ROM(반전된 자모 ROM, 여러 비트 스프라이트 타일) | `rawcarve.py region` + `ink --gfx`(또는 `--invert`), `rawcarve.py bdf --dense`, 그다음 `bdfface.py` | `jamoset.py --layout spec`(자체 규칙이 있는 폰트, 정확), 잘라 낸 8x4x4 폰트에 `--layout 844`, 또는 `--from-svf` | [MAME 세트의 한글 폰트 ROM](recipes/rom-mame.ko.md#mame-세트의-한글-폰트-rom) |
| OS/2 한글 System DBCS 폰트(`$korZN16.FNT`, `$korZN24.FNT`, 완성형) | `os2dbcs.py table`, `rawcarve.py bdf --grid 0xA1,0xA1,94`, `bdfface.py` | `jamoset.py --from-svf` | [OS/2 한글 폰트(완성형)](recipes/os2.ko.md#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기) |
| 한글 Windows 3.1 / 95 `.TBM` 비트맵 폰트(`BT16.TBM`, `BT20.TBM`, `GULIM16.TBM`, `GULIM12.TBM`) | `tbmfont.py info`, `rawcarve.py bdf --invert`(`--chars ks-hangul --dense`, `ascii`), `bdfface.py` | `jamoset.py --from-svf` | [TBM 폰트](recipes/windows.ko.md#windows-tbm-폰트-31과-95) |
| Windows 95 / XP `gulim.ttc`, `batang.ttc`(내장 스트라이크) | 스트라이크의 크기로 `mkfont.py --size N --bpp 1`(Windows 95: 12-21, 24, 25; XP: 11-21, 24, 25) | 없음 | [TrueType 내장 스트라이크](recipes/windows.ko.md#windows-truetype-내장-스트라이크-95와-xp) |
| 자모 글리프가 있는 TTF(첫가끝 자모, PUA 조각, GSUB `ljmo`) | 다른 TTF와 같이 | 합성 글리프는 `jamovec.py --components`, 변형은 `--mask-font`, 그 밖에는 맞춤 | [이미 자모를 가진 TrueType 폰트](recipes/outline-fonts.ko.md#이미-자모를-가진-truetype-폰트) |
| 16 px나 2 bpp로 쓰고 싶은 24-48 px 비트맵 페이스 | `svfscale.py --size 16 [--bpp 2]` | `jamoset.py --from-svf`(1 bpp 결과) | [고해상도 비트맵 폰트에서 저해상도 페이스 만들기](recipes/bitmap-fonts.ko.md#고해상도-비트맵-폰트에서-저해상도-페이스-만들기) |
| Mac HangulTalk 1.0 `fbit`(벌 45개 + `fdef`) | 없음 | `jamoset.py --layout mac-fbit-45sets` | [클래식 Mac 한글 비트맵 폰트](recipes/classic-mac.ko.md#클래식-mac-한글-비트맵-폰트) |
| Mac HangulTalk 7.1 type-3 `fbit` + HTBL 1 | `macfbit3.py bdf` + `mkfont.py` | `macfbit_svf.py build` | [HangulTalk 7.1.x type-3 `fbit` 폰트](recipes/classic-mac.ko.md#클래식-mac-hangultalk-71) |
| SVF 페이스 | `svfdy.py`, `svf2to3.py` | `jamoset.py --from-svf`(1 bpp 원본) | [기존 SVF](recipes/svf-and-ttf.ko.md#기존-svf) |
| 다시 TTF(또는 BDF) 비트맵 폰트로 만들 SVF 페이스 | `svf2ttf.py ttf`(또는 `bdf`) | 같음: 모든 음절을 합성한 완성형 폰트(`--composite`: 조각을 나눠 쓰고 음절은 합성 글리프) | [SVF 페이스를 다시 TTF 비트맵 폰트로](recipes/svf-and-ttf.ko.md#svf-페이스를-다시-ttf-비트맵-폰트로) |

자모 세트의 벌 수를 정하려면: [벌 수 정하기](recipes/sets.ko.md#벌-수-정하기). 안티앨리어싱 페이스:
[2 bpp 안티앨리어싱 페이스](recipes/outline-fonts.ko.md#truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기).

모든 행의 점검은 같다: [페이스 점검](#페이스-점검)(샘플 줄의 measure와 잉크, 자모 세트는 맞춤 IoU). 흑백 원본 픽셀을 같은 크기로 저장해도 중간 커버리지는 새로 생기지 않는다. 더 작은 크기로 다시 샘플링하면(`svfscale.py --bpp 2`) 중간 단계가 생길 수 있다. 대상의 메모리가 적으면 자모
세트를 고르고(2,350 음절 16 px 예시는 약 115 KB, 그 자모 세트는 약 20 KB), 모든 음절이 원본과 정확히 같아야 하면 완성형을
고른다.

<a id="페이스-점검"></a>

<a id="2-페이스-점검"></a>

## 페이스 점검

<a id="새-페이스-점검"></a>

모든 레시피 문서는 같은 점검으로 끝난다. 샘플 줄은 `안녕하세요 ABC 123`이고, 따로 적지 않으면 페이스는 16x16 셀의 16 px이다.

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
  측정 너비가 200(큰 셀 명령 틀에서는 400)을 넘으면 더 넓은 버퍼를 쓴다. 해당 예외는 각 레시피에 따로 적었다.
- 자모 세트는 `--check`(`jamoset.py`와 `jamovec.py`)로 판정한다. 조각에서 음절 11,172개를 모두 조합하고 표 오류에서 실패한다. 그
  앞의 맞춤 줄은 조각과 원본 음절의 IoU를 출력한다(`fit: 11172 syllables, IoU 0.817`). `--check`는 맞춤이 나쁘다고 실패하지는 않는다.
  IoU를 읽고 결과를 직접 보라(`svfline.py line`, 또는 `web/` 선택기).
- `svf2to3.py --check`는 `svfline`으로 글리프마다 비교한다. 위 `facecheck.py` 명령은 `HEAD`의 커밋된 파일로
  매니페스트를 만든 뒤 작업 파일을 대조한다. 새 `FACE.SVF`를 검증하는 명령은 아니다.
  `tools/build/build_faces.py`는 `svf/`의 페이스를 다시 빌드한다([svf/의 페이스](recipes/svf-faces.ko.md#svf의-페이스) 참고).

기준 실행(검증), 16 px NanumGothic Bold([완성형 페이스](recipes/outline-fonts.ko.md#완성형-페이스-mkfontpy)): 1 bpp `125,520` 바이트, 글리프 2,446개, `width=146 ascent=14 descent=2`, 잉크 677.

<a id="참고"></a>

<a id="16-참고"></a>

## 참고

<a id="ks-x-1001"></a>

<a id="161-ks-x-1001"></a>

### KS X 1001

KS X 1001(예전 이름 KS C 5601)에는 완성형 한글 음절 2,350자(행 0xB0-0xC8, 행마다 94자), 호환 자모 51개(행 0xA4:
U+3131..U+3163), 기호, 한자가 있다. 도구:

- `mkfont.py --unicode` 이름: `ksx1001-hangul`(2,350자), `ksx1001-nohanja`(기호, 자모, 2,350자), `ksx1001-symbols`,
  `ksx1001`(한자 포함), `hangul` / `cp949-hangul`(11,172자 전부), `cp949`(CP949가 디코딩하는 모든 것), `jamo`(U+3131..U+318E,
  94개). `--limit`은 `--chars-from` 목록과 이들 중 하나의 교집합을 취하고, `--require`는 폰트에 없는 코드 포인트를 거부한다.
- `jamoset.ks_x_1001_syllables()`(음절 인덱스)와 품질 보고서(`ks2350` 열)는 같은 집합을 쓴다. `tools/test_recipes.py`가 둘이 euc_kr
  코덱의 행과 같음을 점검한다.
- 완전한 JSET 표는 음절 11,172개를 모두 조합한다. 직접 매핑하는 JMAP 페이스는 일부만 지원할 수 있다. 호환 자모는 표가 조각을 지정하면 조각으로, 아니면 글리프 전체로 그린다.
  `jamoset.py --blank-compat`은 글리프 전체가 있는 곳에서 그것을 쓰도록 페이스를 다시 쓴다.
- `facecheck.py`는 페이스를 매니페스트와 대조하고(`verify`) 맵을 만든다(`mapfaces`). 페이스별 커버리지는 웹 인덱스에 있다
  (`web/mkindex.py`: `hangul` = 그려진 KS 음절, `subset` = 자모 세트와 라틴 전용 페이스를 제외하고 KS 음절이 2,350자보다 적은 페이스).

<a id="인코딩"></a>

<a id="162-인코딩"></a>

### 인코딩

EUC-KR / 완성형 바이트 쌍 = GL 코드 + 0x8080 (`가` = B0A1 = GL 3021). Python: `bytes((0xB0,0xA1)).decode("euc_kr")`. 조합형(Python `johab` 코덱): 16비트 코드 `1 iiiii mmmmm fffff`에 채움 값(초성 2 = ㄱ, 중성 3 = ㅏ, 종성 1 = 없음)이 있고 `가` = 8861;
`bytes((0x88,0x61)).decode("johab")`. 유니코드 음절 = 0xAC00 + (초성 x 21 + 중성) x 28 + 종성 (자모 인덱스는 0부터). [한글 조합과 인코딩](#ref-encoding)을 참고한다. `tools/test_recipes.py`가 이 예시를 점검한다.

<a id="알려진-한계"></a>

<a id="163-알려진-한계"></a>

### 알려진 한계

- `jamoset.py`의 기본 `--binarize mono`에는 `freetype-py`가 필요하다(마스크 폰트에는 `uharfbuzz`도 필요하다). 레시피는 `--binarize threshold`를 쓰고, `--mask-font none`은 1 bpp 맞춤이 `$JAMOSET_MASK_FONT`에
  좌우되지 않게 한다. [자모 세트](recipes/outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트)를 참고한다.
- 실행 시간(이 호스트, 코어 하나): 16 px 아웃라인 폰트의 1 bpp `threshold` 맞춤은 약 12초, 2 bpp는 약 73초, Gowun Batang adaptive 20 px는
  약 90초이다. 2 bpp 페이스는 같은 1 bpp 페이스의 약 1.5-1.6배, 자모 세트는 약 6분의 1이다.
- `mkfont.py --bpp 2`는 흑백 비트맵을 원래 크기의 2 bpp로 저장할 수 있지만 중간 커버리지를 새로 만들지는 않는다. `svfscale.py --bpp 2`는 더 작은 크기의 2 bpp
  페이스를 만들고([고해상도 비트맵 폰트에서 저해상도 페이스 만들기](recipes/bitmap-fonts.ko.md#고해상도-비트맵-폰트에서-저해상도-페이스-만들기)), 비트맵에서 2 bpp 자모 세트를 만드는 도구는 없다.
- `mkfont.py`는 요약을 한국어로 출력한다. 필드 이름을 찾으려고 그 stdout을 파싱하지 말 것.
- 도구 전반의 알려진 빈틈: [tools.ko.md](tools.ko.md#도구에-남은-빈틈)의 "도구에 남은 빈틈".

<a id="참고-문헌"></a>

<a id="18-참고-문헌"></a>

## 참고 문헌

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

<a id="옮긴-절"></a>

## 옮긴 절

레시피는 2026-11-27까지 문서 하나였다. 옮긴 절의 앵커로 가는 링크는 여기, 그 절의 행에 닿고, 그 행이 새 위치로 이어 준다.

| docs/recipes.ko.md의 예전 앵커 | 지금 위치 |
|---|---|
| <a id="아웃라인-폰트"></a><a id="3-아웃라인-폰트"></a>`#아웃라인-폰트`, `#3-아웃라인-폰트` | [아웃라인 폰트](recipes/outline-fonts.ko.md#아웃라인-폰트) |
| <a id="완성형-페이스-mkfontpy"></a><a id="31-완성형-페이스-mkfontpy"></a>`#완성형-페이스-mkfontpy`, `#31-완성형-페이스-mkfontpy` | [완성형 페이스 (`mkfont.py`)](recipes/outline-fonts.ko.md#완성형-페이스-mkfontpy) |
| <a id="opentype-cff-otf"></a><a id="32-opentype-cff-otf"></a>`#opentype-cff-otf`, `#32-opentype-cff-otf` | [OpenType CFF (`.otf`)](recipes/outline-fonts.ko.md#opentype-cff-otf) |
| <a id="truetype와-opentype-폰트에서-만드는-자모-세트"></a><a id="33-truetype와-opentype-폰트에서-만드는-자모-세트"></a>`#truetype와-opentype-폰트에서-만드는-자모-세트`, `#33-truetype와-opentype-폰트에서-만드는-자모-세트` | [TrueType와 OpenType 폰트에서 만드는 자모 세트](recipes/outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트) |
| <a id="이미-자모를-가진-truetype-폰트"></a><a id="34-이미-자모를-가진-truetype-폰트"></a>`#이미-자모를-가진-truetype-폰트`, `#34-이미-자모를-가진-truetype-폰트` | [이미 자모를 가진 TrueType 폰트](recipes/outline-fonts.ko.md#이미-자모를-가진-truetype-폰트) |
| <a id="truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기"></a><a id="안티에일리어싱된-2-bpp-페이스"></a><a id="안티앨리어싱된-2-bpp-페이스"></a><a id="truetypeopentype-폰트에서-2-bpp-안티에일리어싱-페이스-만들기"></a><a id="35-truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기"></a>`#truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기`, `#안티에일리어싱된-2-bpp-페이스`, `#안티앨리어싱된-2-bpp-페이스`, `#truetypeopentype-폰트에서-2-bpp-안티에일리어싱-페이스-만들기`, `#35-truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기` | [TrueType/OpenType 폰트에서 2 bpp 안티앨리어싱 페이스 만들기](recipes/outline-fonts.ko.md#truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기) |
| <a id="기준선-세로-이동-클리핑"></a><a id="36-기준선-세로-이동-클리핑"></a>`#기준선-세로-이동-클리핑`, `#36-기준선-세로-이동-클리핑` | [기준선, 세로 이동, 클리핑](recipes/outline-fonts.ko.md#기준선-세로-이동-클리핑) |
| <a id="ttc와-otc"></a><a id="opentype-cff-컬렉션-가변-폰트"></a><a id="37-ttc와-otc"></a>`#ttc와-otc`, `#opentype-cff-컬렉션-가변-폰트`, `#37-ttc와-otc` | [TTC와 OTC](recipes/outline-fonts.ko.md#ttc와-otc) |
| <a id="가변-폰트"></a><a id="38-가변-폰트"></a>`#가변-폰트`, `#38-가변-폰트` | [가변 폰트](recipes/outline-fonts.ko.md#가변-폰트) |
| <a id="mac-형식-truetype"></a><a id="39-mac-형식-truetype"></a>`#mac-형식-truetype`, `#39-mac-형식-truetype` | [Mac 형식 TrueType](recipes/outline-fonts.ko.md#mac-형식-truetype) |
| <a id="비트맵-폰트"></a><a id="4-비트맵-폰트"></a>`#비트맵-폰트`, `#4-비트맵-폰트` | [비트맵 폰트](recipes/bitmap-fonts.ko.md#비트맵-폰트) |
| <a id="x-window-한글-폰트"></a>`#x-window-한글-폰트` | [X 윈도와 유닉스의 한글 폰트](recipes/x-window.ko.md#x-window-한글-폰트) |
| <a id="iso-10646-bdf와-pcf"></a><a id="41-iso-10646-bdf와-pcf"></a>`#iso-10646-bdf와-pcf`, `#41-iso-10646-bdf와-pcf` | [ISO 10646 BDF와 PCF](recipes/bitmap-fonts.ko.md#iso-10646-bdf와-pcf) |
| <a id="ks-c-5601-bdf와-pcf"></a><a id="42-ks-c-5601-bdf와-pcf"></a>`#ks-c-5601-bdf와-pcf`, `#42-ks-c-5601-bdf와-pcf` | [KS C 5601 BDF와 PCF](recipes/bitmap-fonts.ko.md#ks-c-5601-bdf와-pcf) |
| <a id="hanterm"></a><a id="43-hanterm"></a>`#hanterm`, `#43-hanterm` | [hanterm 조합형 폰트](recipes/x-window.ko.md#hanterm) |
| <a id="hbf"></a><a id="44-hbf"></a>`#hbf`, `#44-hbf` | [HBF](recipes/bitmap-fonts.ko.md#hbf) |
| <a id="windows-fnt와-fon"></a><a id="45-windows-fnt와-fon"></a>`#windows-fnt와-fon`, `#45-windows-fnt와-fon` | [Windows FNT와 FON](recipes/bitmap-fonts.ko.md#windows-fnt와-fon) |
| <a id="내장-비트맵-스트라이크"></a><a id="46-내장-비트맵-스트라이크"></a>`#내장-비트맵-스트라이크`, `#46-내장-비트맵-스트라이크` | [내장 비트맵 스트라이크](recipes/bitmap-fonts.ko.md#내장-비트맵-스트라이크) |
| <a id="고해상도-비트맵-폰트에서-저해상도-페이스-만들기"></a><a id="9-고해상도-비트맵-폰트에서-저해상도-페이스-만들기"></a>`#고해상도-비트맵-폰트에서-저해상도-페이스-만들기`, `#9-고해상도-비트맵-폰트에서-저해상도-페이스-만들기` | [고해상도 비트맵 폰트에서 저해상도 페이스 만들기](recipes/bitmap-fonts.ko.md#고해상도-비트맵-폰트에서-저해상도-페이스-만들기) |
| <a id="dos-시대-원시-폰트"></a><a id="5-dos-시대-원시-폰트"></a>`#dos-시대-원시-폰트`, `#5-dos-시대-원시-폰트` | [DOS 시대 원시 폰트](recipes/dos-fonts.ko.md#dos-시대-원시-폰트) |
| <a id="그-밖의-dos-시대-한글-폰트"></a><a id="51-그-밖의-dos-시대-한글-폰트"></a>`#그-밖의-dos-시대-한글-폰트`, `#51-그-밖의-dos-시대-한글-폰트` | [그 밖의 DOS 시대 한글 폰트](recipes/dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트) |
| <a id="hwp-1x와-2x-폰트"></a><a id="52-hwp-1x와-2x-폰트"></a>`#hwp-1x와-2x-폰트`, `#52-hwp-1x와-2x-폰트` | [HWP 1.x와 2.x 폰트](recipes/dos-fonts.ko.md#hwp-1x와-2x-폰트) |
| <a id="hwp-30-fnt-폰트"></a><a id="53-hwp-30-fnt-폰트"></a>`#hwp-30-fnt-폰트`, `#53-hwp-30-fnt-폰트` | [HWP 3.0 FNT 폰트](recipes/dos-fonts.ko.md#hwp-30-fnt-폰트) |
| <a id="ks-x-1001-원시-덤프"></a><a id="54-ks-x-1001-원시-덤프"></a>`#ks-x-1001-원시-덤프`, `#54-ks-x-1001-원시-덤프` | [KS X 1001 원시 덤프](recipes/dos-fonts.ko.md#ks-x-1001-원시-덤프) |
| <a id="claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기"></a><a id="6-claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기"></a>`#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기`, `#6-claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기` | [Claude와 함께 프로그램이나 데이터 파일 안의 폰트 찾기](recipes/programs-and-drivers.ko.md#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기) |
| <a id="프롬프트"></a><a id="61-프롬프트"></a>`#프롬프트`, `#61-프롬프트` | [프롬프트](recipes/programs-and-drivers.ko.md#프롬프트) |
| <a id="nkp-조각을-잘라-저장한-허큘리스-한글-tsr"></a><a id="62-nkp-조각을-잘라-저장한-허큘리스-한글-tsr"></a>`#nkp-조각을-잘라-저장한-허큘리스-한글-tsr`, `#62-nkp-조각을-잘라-저장한-허큘리스-한글-tsr` | [NKP: 조각을 잘라 저장한 허큘리스 한글 TSR](recipes/programs-and-drivers.ko.md#nkp-조각을-잘라-저장한-허큘리스-한글-tsr) |
| <a id="도깨비-드라이버-안의-폰트"></a><a id="63-도깨비-드라이버-안의-폰트"></a>`#도깨비-드라이버-안의-폰트`, `#63-도깨비-드라이버-안의-폰트` | [도깨비: 드라이버 안의 폰트](recipes/programs-and-drivers.ko.md#도깨비-드라이버-안의-폰트) |
| <a id="한글-vga-폰트-rom-86box"></a><a id="64-한글-vga-폰트-rom-86box"></a>`#한글-vga-폰트-rom-86box`, `#64-한글-vga-폰트-rom-86box` | [한글 VGA 폰트 ROM (86Box)](recipes/rom-86box.ko.md#한글-vga-폰트-rom-86box) |
| <a id="한국-msx-폰트-msx2와-msx1"></a><a id="65-한국-msx-폰트-msx2와-msx1"></a>`#한국-msx-폰트-msx2와-msx1`, `#65-한국-msx-폰트-msx2와-msx1` | [한국 MSX 폰트 (MSX2와 MSX1)](recipes/rom-msx.ko.md#한국-msx-폰트-msx2와-msx1) |
| <a id="msx-코딩-에이전트로-권장"></a><a id="코딩-에이전트로-권장"></a>`#msx-코딩-에이전트로-권장`, `#코딩-에이전트로-권장` | [코딩 에이전트로 (권장)](recipes/rom-msx.ko.md#msx-코딩-에이전트로-권장) |
| <a id="msx2-대우-자모-세트-폰트정확"></a>`#msx2-대우-자모-세트-폰트정확` | [MSX2: 대우 자모 세트 폰트(정확)](recipes/rom-msx.ko.md#msx2-대우-자모-세트-폰트정확) |
| <a id="msx2-cpc-400s-완성형-폰트"></a>`#msx2-cpc-400s-완성형-폰트` | [MSX2: CPC-400S 완성형 폰트](recipes/rom-msx.ko.md#msx2-cpc-400s-완성형-폰트) |
| <a id="msx1-bios의-자모-셀을-기계처럼-배치하기"></a>`#msx1-bios의-자모-셀을-기계처럼-배치하기` | [MSX1: BIOS의 자모 셀을 기계처럼 배치하기](recipes/rom-msx.ko.md#msx1-bios의-자모-셀을-기계처럼-배치하기) |
| <a id="truetype-파일"></a>`#truetype-파일` | [TrueType 파일](recipes/rom-msx.ko.md#truetype-파일) |
| <a id="정답으로서의-에뮬레이터"></a>`#정답으로서의-에뮬레이터` | [정답으로서의 에뮬레이터](recipes/rom-msx.ko.md#정답으로서의-에뮬레이터) |
| <a id="mame-세트의-한글-폰트-rom"></a><a id="7-mame-세트의-한글-폰트-rom"></a>`#mame-세트의-한글-폰트-rom`, `#7-mame-세트의-한글-폰트-rom` | [MAME 세트의 한글 폰트 ROM](recipes/rom-mame.ko.md#mame-세트의-한글-폰트-rom) |
| <a id="삼성-spc-1500-반전된-rom-네-개의-자모-세트정확"></a><a id="71-삼성-spc-1500-반전된-rom-네-개의-자모-세트정확"></a>`#삼성-spc-1500-반전된-rom-네-개의-자모-세트정확`, `#71-삼성-spc-1500-반전된-rom-네-개의-자모-세트정확` | [삼성 SPC-1500: 반전된 ROM 네 개의 자모 세트(정확)](recipes/rom-mame.ko.md#삼성-spc-1500-반전된-rom-네-개의-자모-세트정확) |
| <a id="date-quiz-go-go-음절-2350자의-스프라이트-폰트"></a><a id="72-date-quiz-go-go-음절-2350자의-스프라이트-폰트"></a>`#date-quiz-go-go-음절-2350자의-스프라이트-폰트`, `#72-date-quiz-go-go-음절-2350자의-스프라이트-폰트` | [Date Quiz Go Go: 음절 2,350자의 스프라이트 폰트](recipes/rom-mame.ko.md#date-quiz-go-go-음절-2350자의-스프라이트-폰트) |
| <a id="x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용"></a><a id="73-x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용"></a>`#x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용`, `#73-x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용` | [X Se Dae Quiz: 스프라이트 속의 태백 GOTHIC16(대조용)](recipes/rom-mame.ko.md#x-se-dae-quiz-스프라이트-속의-태백-gothic16대조용) |
| <a id="quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트"></a><a id="74-quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트"></a>`#quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트`, `#74-quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트` | [Quiz King of Fighters(한국판): 외곽선 펜이 있는 음절 2,350자 폰트](recipes/rom-mame.ko.md#quiz-king-of-fighters한국판-외곽선-펜이-있는-음절-2350자-폰트) |
| <a id="live-quiz-show-규칙은-읽었고-조각은-맞지-않는다만들지-않음"></a><a id="75-live-quiz-show-규칙은-읽었고-조각은-맞지-않는다만들지-않음"></a>`#live-quiz-show-규칙은-읽었고-조각은-맞지-않는다만들지-않음`, `#75-live-quiz-show-규칙은-읽었고-조각은-맞지-않는다만들지-않음` | [Live Quiz Show: 규칙은 읽었고 조각은 맞지 않는다(만들지 않음)](recipes/rom-mame.ko.md#live-quiz-show-규칙은-읽었고-조각은-맞지-않는다만들지-않음) |
| <a id="폰트가-없거나-풀지-못한-세트"></a><a id="76-폰트가-없거나-풀지-못한-세트"></a>`#폰트가-없거나-풀지-못한-세트`, `#76-폰트가-없거나-풀지-못한-세트` | [폰트가 없거나 풀지 못한 세트](recipes/rom-mame.ko.md#폰트가-없거나-풀지-못한-세트) |
| <a id="os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기"></a><a id="os2-한글-폰트완성형"></a><a id="8-os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기"></a>`#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기`, `#os2-한글-폰트완성형`, `#8-os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기` | [OS/2 한글 폰트(완성형)에서 완성형 페이스와 자모 세트 만들기](recipes/os2.ko.md#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기) |
| <a id="클래식-mac-한글-비트맵-폰트"></a><a id="10-클래식-mac-한글-비트맵-폰트"></a>`#클래식-mac-한글-비트맵-폰트`, `#10-클래식-mac-한글-비트맵-폰트` | [클래식 Mac 한글 비트맵 폰트](recipes/classic-mac.ko.md#클래식-mac-한글-비트맵-폰트) |
| <a id="기존-svf"></a><a id="11-기존-svf"></a>`#기존-svf`, `#11-기존-svf` | [기존 SVF](recipes/svf-and-ttf.ko.md#기존-svf) |
| <a id="svf-페이스를-다시-ttf-비트맵-폰트로"></a><a id="12-svf-페이스를-다시-ttf-비트맵-폰트로"></a>`#svf-페이스를-다시-ttf-비트맵-폰트로`, `#12-svf-페이스를-다시-ttf-비트맵-폰트로` | [SVF 페이스를 다시 TTF 비트맵 폰트로](recipes/svf-and-ttf.ko.md#svf-페이스를-다시-ttf-비트맵-폰트로) |
| <a id="합성-글리프--composite"></a><a id="121-합성-글리프--composite"></a>`#합성-글리프--composite`, `#121-합성-글리프--composite` | [합성 글리프(`--composite`)](recipes/svf-and-ttf.ko.md#합성-글리프--composite) |
| <a id="세트-수벌-수-정하기"></a><a id="벌-수-정하기"></a><a id="세트-수-정하기"></a><a id="13-벌-수-정하기"></a>`#세트-수벌-수-정하기`, `#벌-수-정하기`, `#세트-수-정하기`, `#13-벌-수-정하기` | [벌 수 정하기](recipes/sets.ko.md#세트-수벌-수-정하기) |
| <a id="데스크톱-앱과-maker-경로"></a><a id="14-데스크톱-앱과-maker-경로"></a>`#데스크톱-앱과-maker-경로`, `#14-데스크톱-앱과-maker-경로` | [데스크톱 앱과 maker 경로](recipes/desktop-routes.ko.md#데스크톱-앱과-maker-경로) |
| <a id="svf의-페이스"></a><a id="svf-페이스-다시-빌드하기"></a><a id="15-svf의-페이스"></a>`#svf의-페이스`, `#svf-페이스-다시-빌드하기`, `#15-svf의-페이스` | [svf/의 페이스](recipes/svf-faces.ko.md#svf의-페이스) |
| <a id="완성형-글리프-레시피-mkfont-행"></a><a id="151-완성형-글리프-레시피-mkfont-행"></a>`#완성형-글리프-레시피-mkfont-행`, `#151-완성형-글리프-레시피-mkfont-행` | [완성형 글리프 레시피 (`mkfont` 행)](recipes/svf-faces.ko.md#완성형-글리프-레시피-mkfont-행) |
| <a id="완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행"></a><a id="152-완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행"></a>`#완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행`, `#152-완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행` | [완성형 글리프에서 자모 세트를 만드는 레시피 (`jamoset` 행)](recipes/svf-faces.ko.md#완성형-글리프에서-자모-세트를-만드는-레시피-jamoset-행) |
| <a id="패밀리"></a><a id="153-패밀리"></a>`#패밀리`, `#153-패밀리` | [패밀리](recipes/svf-faces.ko.md#패밀리) |
| <a id="레시피-없는-페이스"></a><a id="154-레시피-없는-페이스"></a>`#레시피-없는-페이스`, `#154-레시피-없는-페이스` | [레시피 없는 페이스](recipes/svf-faces.ko.md#레시피-없는-페이스) |
| <a id="svf에-페이스-추가하기"></a><a id="17-svf에-페이스-추가하기"></a>`#svf에-페이스-추가하기`, `#17-svf에-페이스-추가하기` | [svf/에 페이스 추가하기](recipes/svf-faces.ko.md#svf에-페이스-추가하기) |

[프로젝트 개요](../README.ko.md) · [도구 설명서](tools.ko.md)
