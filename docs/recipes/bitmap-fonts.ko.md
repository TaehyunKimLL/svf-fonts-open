[English](bitmap-fonts.md) | **한국어**

# 레시피: 비트맵 폰트

비트맵 폰트 파일에서 SVF 페이스를 만든다: ISO 10646이나 KS C 5601의 BDF와 PCF(X 윈도 한글 폰트 자체는 hanterm 조합형 폰트를 포함해 [별도 문서](x-window.ko.md)에 있다), HBF, Windows FNT와 FON, 아웃라인 폰트에 내장된 비트맵 스트라이크, 그리고 고해상도 비트맵 폰트를 줄여 만드는 저해상도(또는 2 bpp) 페이스.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. KS C 5601 레시피가 모든 문서의 `bdfface.py` 줄이 읽는 `$OUT/ks.txt`(KS X 1001 음절 2,350자)를 쓴다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [X 윈도와 유닉스의 한글 폰트](x-window.ko.md), [아웃라인 폰트](outline-fonts.ko.md), [DOS 시대 원시 폰트](dos-fonts.ko.md), [안티앨리어싱](../anti-aliasing.ko.md).

<a id="비트맵-폰트"></a>

## 비트맵 폰트

<a id="x-window-한글-폰트"></a>

비트맵 폰트는 두 종류가 서로 다른 경로로 도구에 닿는다. 유니코드 인코딩(`CHARSET_REGISTRY "ISO10646"`, 또는 내장 스트라이크가 있는
TrueType)은 `mkfont.py`와 FreeType을 거치고, KS C 5601 / KS X 1001 인코딩(`ENCODING` = GL 코드, X Window 한글 폰트)은
`bdfface.py`를 거친다. X 윈도와 유닉스의 한글 폰트를 계열별로(대우, 백묵, 한양, KAIST, 미지, hanterm) 명령, 측정값, 라이선스,
샘플과 함께 다룬 것은 [X 윈도와 유닉스의 한글 폰트](x-window.ko.md)에 있다.

<a id="iso-10646-bdf와-pcf"></a>

### ISO 10646 BDF와 PCF

`mkfont.py`는 BDF나 PCF를 Pillow의 FreeType으로 읽되, 파일에 내장된 픽셀 크기(스트라이크)에서만 읽는다. 다른 크기는 `OSError:
invalid pixel size`이며, maker의 `detect.bitmap_strikes`가 폰트가 제공하는 크기를 알려 준다. 이제 shim이나 우회는 없다. `mkfont.py`는
fontTools에 코드 포인트가 cmap에 있는지 묻고, sfnt가 아닌 파일(BDF, PCF, FNT)은 오류가 아니라 알 수 없음으로 취급한다(`cmap_has`가
None을 돌려준다). 예시는 다음 폰트를 쓴다:
`/usr/share/dosbox-x/wqy_12pt.bdf`(WenQuanYi Bitmap Song, 16 px, 유니코드)와 `/usr/share/fonts/X11/misc/18x18ko.pcf.gz`(Misc Fixed
Wide, 18 px)([BDF 형식](../recipes.ko.md#ref-bdf) 참고).

    python3 tools/mkfont.py /usr/share/dosbox-x/wqy_12pt.bdf $OUT/bdf16-1bpp.svf --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-1bpp.svf --size 18 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 tools/mkfont.py /usr/share/fonts/X11/misc/18x18ko.pcf.gz $OUT/pcf18-2bpp.svf --size 18 --bpp 2 --unicode ascii,ksx1001-hangul

Verified, shim 없이: BDF `115,684 바이트`, 글리프 2,446개, `width=156 ascent=12 descent=4`, 잉크 348; PCF 1 bpp `116,552 바이트`, 글리프
2,446개(18x18 셀), `width=234 ascent=15 descent=3`, 잉크 366; PCF 2 bpp `181,108 바이트`. 이 비트맵에는 흑백 커버리지만 있으므로 `--bpp 2`의 단계는 0과
3뿐이다. 같은 모노크롬 픽셀을 2 bpp로 담을 뿐 부드러운 페이스가 아니다. 이 페이스의 자모 세트는 완성형 결과에 대한 맞춤이다:
`jamoset.py --layout 844 --from-svf $OUT/bdf16-1bpp.svf --mask-font none --check -o ...`(수치는 다음 소절의 bdfface 페이스에 있다).

<a id="ks-c-5601-bdf와-pcf"></a>

### KS C 5601 BDF와 PCF

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
U+25A1만 담는다. `--symbols`를 주지 않으면 BDF에서 기호나 자모는 오지 않는다. `--symbols`를 주면 `--chars-from`이 지정한 다른
문자(KS X 1001 기호, 자모, 한자)도 한글 BDF에서 가져온다([X 윈도 레시피](x-window.ko.md#준비-음절-목록-ascii-절반-pcf)가 쓴다). 셀의 기본값은 BDF의 박스와 상관없이 24x24이므로 `--cell`을 주어라. `--ascent` /
`--hangul-ascent`는 기준선을 정한다. Synthetic(`tools/test_recipes.py`): 음절 10개짜리 KS C 5601 BDF와 ISO 10646 ASCII BDF는 정확히 그
음절만 담은 페이스를 주고 행도 제자리에 있다.

<a id="hanterm"></a>

**hanterm**(옮김). hanterm 조합형 BDF(hanterm 3.0.4의 johab-1 폰트와 hanterm-font 3.1의 johab844-1 폰트,
`jamoset.py --layout hanterm-johab`과 `--layout hanterm-844`)는 이제 [X 윈도와 유닉스의 한글 폰트](x-window.ko.md)의
[hanterm 조합형 폰트](x-window.ko.md#hanterm)에 있다.

<a id="hbf"></a>

### HBF

`bdfface.py --ascii`는 HBF(옆에 `.bin` 또는 `.bin.gz`가 있는 `.hbf`)를 읽지만 페이스의 ASCII 절반으로만 읽는다. 한글 절반은 BDF여야
한다. ibiblio의 HBF 모음에 있는 X11 Sony 폰트 Sony Fixed 12x24(`12x24.hbf`와 `12x24.bin.gz`; Sony, 고지 조건으로 자유 사용)를 ASCII 절반으로,
Baekmuk 2.0 X11 BDF 세트의 Baekmuk 바탕 24(`batang24.bdf`, KS C 5601)를 한글 절반으로 실행했다.

    python3 tools/bdfface.py --hangul batang24.bdf --ascii 12x24.hbf --cell 24x24 --chars-from $OUT/ks.txt -o $OUT/HBF24.SVF

`206,872 바이트`, 음절 2,350자, ascent 22, step 24, 잘린 글리프 없음, `width=216 ascent=22 descent=2`(24 px 음절 다섯 개와 12 px 문자 일곱 개),
잉크 746. `.hbf` 옆에 `.bin`을 풀어 두면 페이스가 바이트 단위로 같다. maker의 `detect.scan`(사본에서 확인, 업로드와 로컬
모드 모두)은 `12x24.bin.gz`와 함께 있는 `12x24.hbf`를 형식 `hbf`, 레이블 "HBF", 24 px, ASCII 커버리지 95로 나열하고 자기 경로는 주지 않는다.
HBF는 페이스의 라틴 절반일 뿐이다. 라틴 절반으로 쓸 수 없는 HBF에는 이유를 말하는 레이블이 붙는다: 2 바이트 코드 범위(`uni24.hbf`,
`unihan16.hbf`: "HBF: two-byte code range not supported"), gzip으로 압축된 HBF 자체("HBF: gzipped HBF not supported"), 없는 비트맵 파일
("HBF: bitmap file missing").
Synthetic(`tools/test_bdfface.py`): 합성 HBF를 ASCII 절반으로.

<a id="windows-fnt와-fon"></a>

### Windows FNT와 FON

FreeType에는 winfnt 드라이버가 있어서 `mkfont.py`는 Windows `.FNT`(또는 여러 개를 담은 `.FON`)를 BDF나 PCF처럼 폰트 자신의 픽셀 크기로
열지만, 거기서 그리지는 못한다. 드라이버가 이런 폰트에 `FT_ENCODING_NONE` 맵 하나만 주어서 유니코드가 없고, 모든 코드 포인트가 글리프 0으로
떨어진다. Windows 95 한글판의 시스템 폰트(Microsoft, 독점)로 실행했다: VGAFIX.FON "Fixedsys" 16 px, VGASYS.FON "System" 13 px,
SERIFF.FON "MS Serif" 13 px, 8514FIX.FON([FreeType 비트맵 및 Windows FNT 지원](../recipes.ko.md#ref-freetype) 참고).

    python3 tools/mkfont.py VGAFIX.FON $OUT/fon.svf --size 16 --bpp 1 --unicode ascii

는 `--unicode 의 글자가 글꼴에 하나도 없다`로 끝나고, `--unicode ascii,ksx1001-hangul`도 같다. Pillow는 "A", "B", "가"를 똑같은 notdef 글리프
하나로 그린다. maker의 `detect.scan`(업로드와 로컬 모드)은 이들에 이름을 붙이고 경로는 주지 않는다: VGAFIX.FON과
VGASYS.FON은 "Windows FON face 0; no Unicode character map, mkfont cannot read it"(크기 [16]과 [13]), MODERN.FON은 "Windows FON; no openable
face". 맨 Windows `.FNT`도 같은 식으로 붙는다("Windows FNT; no Unicode character map, mkfont cannot read it"). 지원하지 않는 것으로 다루거나
먼저 변환하라. 한글 글리프가 있는
Windows FNT나 FON은 찾지 못했다. Windows 95 한글판 디스크에는 라틴과 OEM 폰트(Fixedsys, System, Terminal, MS Serif, MS Sans Serif, Courier,
Small Fonts; FON 25개)뿐이고, 그 시스템의 한글 글리프는 TrueType이다(`gulim.ttc`, 스트라이크 포함: [내장 비트맵 스트라이크](#내장-비트맵-스트라이크)).
FON은 외부 도구로 먼저 BDF로 변환해야 하며, 그 변환기는 제공하지 않는다.

자모 조각 폰트인 DOS Johab `.FNT` 파일과 혼동하지 말 것: [DOS 시대 원시 폰트](dos-fonts.ko.md#dos-시대-원시-폰트)를 참고한다.

<a id="내장-비트맵-스트라이크"></a>

### 내장 비트맵 스트라이크

내장 비트맵이 있는 아웃라인 폰트(TrueType `bdat`/`bloc`, OpenType `EBDT`/`EBLC`)는 FreeType이 스트라이크 자신의 픽셀 크기에서만 쓴다.
스트라이크의 크기로 `mkfont.py --size N`과 `--bpp 1`을 실행한다. 다른 크기에서는 윤곽선을 쓰고, 비트맵 전용 폰트는 열기가 실패한다
(`OSError: invalid pixel size`). maker의 `detect.bitmap_strikes`가 폰트의 스트라이크를 나열해 크기로 제공한다. 실제 폰트 두 개로 실행했다([OpenType 글리프, 셰이핑, 비트맵 스트라이크](../recipes.ko.md#ref-opentype) 참고).

*Seoul*, Mac OS 7.6.1 한글판 CD의 폰트(`Font Folder/Seoul[FFIL]`, Apple Korea / Elex, 독점; 스트라이크 9, 10, 12, 14, 16, 18, 20, 24 ppem,
[Mac 형식 TrueType](outline-fonts.ko.md#mac-형식-truetype) 참고): `macsfnt.py extract`와 `unicode` 뒤에 `mkfont.py --size 16 --bpp 1
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


<a id="고해상도-비트맵-폰트에서-저해상도-페이스-만들기"></a>

## 고해상도 비트맵 폰트에서 저해상도 페이스 만들기

24, 40, 48 px 비트맵 폰트(DOS나 프린터 폰트, BDF, ROM)를 16 px로, 또는 2 bpp 페이스로 쓰고 싶을 때다. 지금 도구가 하는 일:
`mkfont.py`는 BDF나 PCF를 그 자신의 크기로만 연다(다른 크기에서는 `OSError: invalid pixel size`,
[ISO 10646 BDF와 PCF](#iso-10646-bdf와-pcf)). `jamoset.py --from-svf`는 원본의 셀을 유지한다. C 렌더러와 `svfline.py`는 그리는 시점에
페이스를 축소한다(`scale_num / scale_den`, 8비트 커버리지로 가는 박스 필터). `tools/svfscale.py`는 더 작은 페이스를 쓴다. 1 bpp 페이스(자모 세트는 음절을 조합해서)나 BDF에서 선택한 글리프를 그리고, 새 셀로 박스 필터를
걸어(출력 픽셀마다 원본 영역 중 잉크가 차지한 정확한 비율) 완성형 페이스를 쓴다. 1 bpp는 임계값으로, 2 bpp는 네 단계로:

    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 -o $OUT/ZN24TO16.SVF --compare $OUT/OS2ZN16.SVF   # 1 bpp, 비율 >= 0.5
    python3 tools/svfscale.py $OUT/OS2ZN24.SVF --size 16 --bpp 2 -o $OUT/ZN24TO16A.SVF                     # 2 bpp
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/ZN24TO16.SVF --mask-font none --check -o $OUT/ZN24TO16J.SVF

다른 두 원본도 같은 길이다: `bdfface.py --hangul dotum24.bdf --ascii $OUT/12x24.bdf --cell 24x24 ...`(비교할 페이스는 `dotum16.bdf`와
`8x16.bdf`), `jamoset.py --layout 844 GHANC40.PFT --eng GASCII40.PFT --symbols --check -o $OUT/GHANC40J.SVF`(비교용은 `GOTHIC16.FNT --eng ROMAN16.FNT`). 각각 그다음
`svfscale.py --size 16`.

2 bpp 결과는 렌더러가 24 px 페이스를 2/3로 축소해 그리고 커버리지를 네 단계로 양자화한 것과 정확히 같다([OS/2 페이스](os2.ko.md)의 2,350
음절 모두에서 확인: 전부 같음). 이 비교에서는 저장한 2 bpp 페이스와 그리는 시점의 축소를 양자화한 결과가 같은 픽셀을 내며, 저장한 페이스는 메모리를,
축소해 그리기는 시간을 쓴다. 자모 세트는 1 bpp 결과에만 맞출 수 있다. `jamoset.py --bpp 2`는 아웃라인 폰트만 받으므로(`--bpp 2 works
from an outline font (--from-ttf)`) 비트맵 원본에서 2 bpp 자모 세트를 만드는 길은 없다.

여기서 실행(2026-11-22)한 세 원본, 각각 같은 패밀리나 제작사의 손으로 그린 16 px 페이스와 비교했다. "겹침"은 `--compare`가 출력하는
값으로, 1 bpp 결과의 2,350 음절을 그 페이스와 두 페이스를 한 기준선에 놓고 2 픽셀 안의 가장 좋은 공통 이동에서 비교한 평균 IoU이다(다시 샘플링한 페이스가 그린
페이스에서 얼마나 먼지를 재는 값이지 품질 점수가 아니다):

| 원본 | 1 bpp 결과 | 잉크 | 2 bpp 결과 | 잉크 | 1 bpp 결과의 8x4x4 맞춤 | 그린 16 px 페이스와 겹침 |
|---|---|---:|---|---:|---|---|
| 백묵 돋움 24 (Baekmuk BDF 2.2의 `dotum24.bdf` + Misc Fixed 12x24, `bdfface.py`를 거쳐 `216,196 bytes`) | `122,016 bytes`, 글리프 2,447개, `width=144 ascent=15 descent=1` | 330 | `194,208 bytes` | 612 | `18,292 bytes`, IoU 0.597 | `dotum16.bdf`(`122,804 bytes`, 잉크 411)와 0.520 |
| OS/2 `$korZN24.FNT` ([OS/2 한글 폰트](os2.ko.md#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기), `220,164 bytes`) | `125,084 bytes`, 글리프 2,447개, `width=144 ascent=15 descent=1` | 410 | `200,760 bytes` | 691 | `18,596 bytes`, IoU 0.710 | `$korZN16.FNT`와 0.387 |
| 태백 3.5.1 고딕 40 (`GHANC40.PFT`와 `--eng GASCII40.PFT`, [그 밖의 DOS 시대 한글 폰트](dos-fonts.ko.md#그-밖의-dos-시대-한글-폰트)의 8x4x4 페이스, `42,716 bytes`) | `124,940 bytes`, 글리프 2,447개, `width=144 ascent=14 descent=2` | 476 | `197,288 bytes` | 764 | `17,088 bytes`, IoU 0.990 | GOTHIC16.FNT와 0.471 |

40 px 원본은 그 자체가 8x4x4 조각의 OR이라 16 px로 다시 샘플링해도 거의 그대로다(IoU 0.990). 음절마다 그린 두 디자인은 8x4x4에 잘
맞지 않는다. 임계값은 획과 뭉침을 맞바꾼다: OS/2 페이스를 `--threshold 0.25`로 하면 잉크 615(`0.5`는 410), 그린 16 px 페이스와 겹침
0.489이다. `svfscale.py dotum24.bdf --chars face`는 BDF의 모든 글리프를 고른다(이 예시에서는 한자 포함 8,226개).
기본 `--chars ks`는 KS 음절, ASCII, 사용 가능한 비음절 문자를 고른다. ascent는 BDF의 값을 쓴다. ASCII와 원하는
셀이 있는 페이스를 원하면 먼저 `bdfface.py`를 거쳐라.

**함정.** 24 px의 1 픽셀 획은 16 px 픽셀의 3분의 2를 덮으므로, 위치가 맞을 때만 0.5 임계값에서 살아남는다. 40, 48 px의 가는 획은 비율
0.4인 픽셀이 되어 1 bpp에서 사라진다. 다시 샘플링은 다시 그리기가 아니다: 그린 16 px 페이스(위 표의 마지막 열)가 더 선명하고,
아웃라인 폰트에서 만든 2 bpp 페이스([2 bpp 안티앨리어싱 페이스](outline-fonts.ko.md#truetypeopentype-폰트에서-2-bpp-안티앨리어싱-페이스-만들기))는
비트맵 계단의 커버리지가 아니라 진짜 커버리지를 가진다.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
