[English](tools.md) | **한국어**

# 도구

이 문서는 이 저장소에서 폰트를 읽고, SVF(SVFN) 페이스(face)를 쓰고, 그것을 검사하는 프로그램들의 참조 문서이다.
SVF maker의 설계가 이 문서를 바탕으로 계획되므로, 아래의 모든 옵션과 동작은 도구의 코드에서 나왔거나 직접 실행해서
얻은 것이며, 이름만 보고 추정한 것은 없다. 포맷 자체는 `spec/SVF.md`에, C 렌더러는
`spec/renderer-design.md`와 `c/include/svf.h`에 있다.

`svf/`의 각 페이스를 만드는 방법과, 모든 종류의 한글 폰트 원본에서 SVF로 가는 레시피(입력 종류별)는 [recipes.ko.md](recipes.ko.md)에 있다.

도구는 명령줄용으로 작성되었다. 한 도구가 다른 도구의 라이브러리가 될 수 있다. `jamoset.py`는 `bdfface.py`,
`jamoaa.py`, `jamoadapt.py`, `svfdy.py`, `svfline.py`, `svf_synth.py`, `jamovec.py`, `web/mkindex.py`가 import하며,
맞춤(fitting) 모듈(`jamofit.py`, `jamoaa.py`, `jamoadapt.py`, `jamoseg.py`)에는 자체 명령줄이 없다.

## 도구가 만드는 SVFN 종류

**SVFN** 파일(매직 `SVFN`, 리틀 엔디언)은 헤더, 코드 포인트 표, 선택적인 글리프별 메트릭, 글리프 레코드로 이루어진
비트맵 폰트이다. 여기의 모든 작성기는 `jamoset.pack_svfn`을 통해 **버전 3**을 쓴다(명세:
`docs/superpowers/specs/2026-10-21-svf-v3-design.md`, `spec/SVF.md`). 버전 2(고정 셀)는 `svf2to3.py`가 변환하며
(`jamoset.parse_svfn`은 v2 페이스를 변환 안내 메시지와 함께 거부한다), 버전 1(코드 페이지 순서)은 없어졌다. **모든 작성기는
`--profile NAME`(기본 `default`. `svf2to3.py` 아래 표의 프로파일 이름 또는 `REC,ROW,TAB,OFF` 단위)과 `--box x|y|full`
(글리프 레코드의 잉크 박스 정책. 기본: 프로파일의 값)을 받는다.** 헤더 바이트 17과 18은 폰트 전체의 **dy** 범위를 담고,
메트릭 바이트 3은 각 글리프의 dy를 담는다(글리프는 셀 위치보다 dy행 아래에 그려진다). 메트릭 표가 있는 폰트만 dy를 가질 수 있다.

도구는 두 종류를 쓴다.

- **완성형 페이스**는 코드 포인트마다 글리프 하나를 저장한다(한글 음절, ASCII 문자, 기호). **1, 2, 8 bpp**로
  쓴다(1 bpp는 스텐실, 2 bpp는 4단계 커버리지, 8 bpp는 256단계). 4 bpp는 없다. 페이스는 글리프별 advance, 왼쪽 베어링,
  잉크 폭을 가진 메트릭 표(헤더 플래그 비트 0)를 가질 수 있으며, 이 경우 가변 폭이 된다.
  코드 포인트 목록에서 `mkfont.py`가 쓴 페이스는 플래그 비트 2도 설정한다(결합 표시는 펜을
  `max(0, -bearingX)`에 둔 채 저장된다).
- **자모 세트(jamo set)**(헤더 플래그 비트 1)는 음절을 담지 않고, 위치별 자모 **조각(piece)**을
  `U+F0000 + 조각 번호`의 글리프로 담으며, 음절마다 어떤 조각을 합성할지(둘 또는 셋의 OR, 즉 픽셀별 최댓값)를 알려 주는
  **JSET** 블록(코드 포인트 표 바로 뒤)을 담는다. 11,172개의 한글 음절 전부를 약 11 KB(16 px, 1 bpp, 조각만)부터
  담을 수 있다. `svf/`의 66개 자모 세트는 10,684바이트(`svf/dos/NEODG16G.SVF`)에서
  162,124바이트(`svf/dos/NSQRB36A.SVF`)까지이며, 2 bpp, 더 큰 셀, 유지한 글리프가 있으면 더 크다. 조각은 1 bpp 또는
  2 bpp로 쓰며, 세트는 메트릭 표(플래그 비트 0)를 가진다. 호환 자모 U+3131..U+3163은 블록이 조각을 지정하면 그
  조각으로 그려진다. 자모 세트는 구형 리더에게도 여전히 유효한 일반 페이스이다.

두 종류 모두 **dy** 범위를 가질 수 있다. 자모 세트는 음절을 dy 0에서 합성한다(조각은 dy를 가질 수 없다).

**레이아웃(layout)**은 자모 세트의 세트 체계이다. 초성/종성 클래스, 초성/중성/종성 세트 표, 조각 표로 이루어진다. 이름이
있는 레이아웃은 `844`(DOS 8x4x4 표준), `844-ihnm`, `844-hbios24`, `1044-san`, `621`, `hanterm-johab`,
`dkb-printer-7x2x2`, `dkb-printer-12x4x4`, `kyra-lok`, `mac-fbit-45sets`, `adaptive[:NI,NM,NF]`이다.

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
- `tools/build/build_faces.py`는 `svf/`의 페이스를 업스트림 폰트에서 다시 빌드한다(`tools/build/faces.tsv`, [recipes.ko.md](recipes.ko.md)).
- `web/` 도구는 WASM 선택기가 서비스하는 페이스를 인덱싱하고 복사한다.

## 핵심 빌더

### `tools/jamoset.py`

**목적.** DOS 시대 원본 폰트에서 자모 세트 SVF(플래그 비트 1과 JSET 블록)를 만들거나, 조각을 아웃라인 폰트나 기존의
완성형 페이스에 맞춘다. SVFN v3도 쓰고(`write_svfn`, `pack_svfn`, `--profile`, `--box`) 읽으며(v2 페이스는 변환 안내
메시지와 함께 거부된다, `tools/svf2to3.py`), JSET 블록을 묶고 풀며, 검사를 위해 음절을 합성한다.

**상태.** 범용이다. 게임 전용 세트 체계(SAGA IHNM, hanterm, Dokkaebi 프린터, Kyra LoK, Mac
HangulTalk, HWP 1.x)의 이름을 갖지만 특정 게임에 묶여 있지 않다.

**입력.** 모드에 따라 다르다.
- 자체 파서로 읽는 DOS Johab 원시 폰트: 원시 8x4x4(`844`, 16/24/40/48 px, 11520/11522/25920/72000/103680/15584
  바이트), 10x4x4(`1044-san`, 12800바이트), 6x2x1(`621`, 6144바이트, 바이트 열 순서), HBIOS/Taebaek 24x30
  (`844-hbios24`, 243900바이트), SAGA IHNM(`844-ihnm`), Kyra `MK15.BIT`(11550바이트), Dokkaebi 프린터
  `HANGUL16/24.FNT`(15360/34560, 열 우선)와 `HANGUL40/48.FNT`(176000/253440);
- `ENCODING`이 johab-1 글리프 번호인 hanterm BDF(`hanterm-johab`). 정규식 리더로 파싱한다;
- Mac HangulTalk 1.0 `fbit` 리소스 포크(`mac-fbit-45sets`). 원시 리소스 맵에서 파싱한다;
- HWP 1.x `HANGUL.SFT` / `HANGUL1/2/3.PFT`(`hwp1`, `--face 0..2`): JSET 표는 그 페이스에 대한 HWP.EXE 자체의 규칙이며 `hwpfont.py`를
  통해 읽는다. HWP 3.0 `HAN16_*.FNT`(`844-hwp3`: 음절 2,350자 뒤의 360개짜리 8x4x4 세트);
- `--eng` 원시 8x16 DOS 영문 폰트(2048 또는 4096바이트), 또는 HBIOS 12x24(15360) / PFT 12x24(12288) / Taebaek PFT 20x40(30720, GASCII40) / 24x48(49152, GASCII48), 또는 HWP 영문 폰트: HWP 1.x `ASCII.SFT`(8x16) / `ASCII.PFT`(14x24, 이동 폭 14. 여섯 페이스 중 `--eng-face`) 또는 HWP 3.0 `ENG*.FNT`(8x16, 12x24, 20x40). 헤더로 알아본다;
- `--base` SVFN v3 페이스(음절이 아닌 글리프를 유지한다. v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`));
- `--from-ttf` 아웃라인 TTF/OTF. 1 bpp `mono` 대상은 freetype-py로, 2 bpp와 `--binarize threshold|ridge`는
  fontTools(`jamoaa.py`를 통해)로 읽는다;
- `--from-svf` 완성형 1 bpp SVFN v3 페이스(v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`)).

**출력.** SVFN v3 자모 세트 페이스(플래그 비트 1, 메트릭이 있으면 비트 0도). 기본은 1 bpp이고 `--bpp 2`이면 2 bpp이다.
조각은 `U+F0000 + n`에 있으며, `--from-ttf`/`--from-svf`는 ASCII 글리프도 담는다. `--blank-compat`는 대신 기존 자모 세트를
다시 쓴다.

**개요(Synopsis).**

    python3 tools/jamoset.py SOURCE --layout LAYOUT -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --from-ttf FONT --size N -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --from-svf FACE.SVF -o OUT.SVF [options]
    python3 tools/jamoset.py --layout LAYOUT --blank-compat FACE.SVF -o OUT.SVF

옵션(기본값은 괄호 안). **Modes** 열은 옵션이 어느 모드에 속하는지 나타낸다. `source`(위치 인자로 주는 DOS Johab,
hanterm BDF, Kyra `.BIT`, Dokkaebi FNT, HWP 3.0 HAN16 FNT 파일), `mac-fbit-45sets`(위치 인자로 주는 Mac HangulTalk `fbit`
리소스 포크. 독자적인 모드로, `--from-*`, `--eng`, `--base`를 받지 않는다), `hwp1`(위치 인자로 주는 HWP 1.x 한글 파일. 독자적인
모드로 `--from-*`는 받지 않고, `--eng`와 `--base`는 `source`처럼 받는다), `--from-ttf`, `--from-svf`, `--bpp 2`
(`--from-ttf`와 함께일 때만), `--blank-compat`. 모드에 나열되지 않은 옵션은 그 모드에서 무시된다(거부되지 않는다).
단, 표에 "refused"라고 적힌 경우는 예외이다.

| Option (default) | Modes | Meaning |
|---|---|---|
| `--layout` (required) | all | 세트 체계: `1044-san`, `621`, `844`, `844-hbios24`, `844-hwp3`, `844-ihnm`, `dkb-printer-12x4x4`, `dkb-printer-7x2x2`, `hanterm-johab`, `hwp1`, `kyra-lok`, `mac-fbit-45sets`, `adaptive[:NI,NM,NF]`. `adaptive`는 `--from-ttf` 또는 `--from-svf`가 필요하다. `mac-fbit-45sets`와 `hwp1`은 독자적인 모드이다(위치 인자 파일이 `fbit` 리소스 포크, HWP 1.x 한글 파일) |
| `--face N` (0) | `source`, `hwp1` | Dokkaebi 프린터 폰트의 서체(0 또는 1), HWP 1.x 한글 파일의 페이스(0, 1, 2) |
| `--eng FILE` (none) | `source`, `hwp1`, `--from-ttf`, `--from-svf` | ASCII용 원시 8x16 영문 폰트(2048 또는 4096바이트; 12x24, 20x40, 24x48 페이스와 위의 HWP 영문 폰트도 읽는다). `--bpp 2` 및 `mac-fbit-45sets`와 함께면 거부된다 |
| `--eng-face N` (0) | `--eng`가 있는 곳 | `--eng`로 준 HWP 1.x `ASCII.SFT` / `ASCII.PFT`의 페이스(0..5: HWP 메뉴의 명조, 고딕, 위첨자, 아래첨자, 이탤릭, 필기체) |
| `--base FILE` (none) | `source`, `hwp1`, `--from-ttf` | 음절이 아닌 글리프를 유지하는 SVFN v3(같은 셀, 1 bpp). `--from-svf`는 무시한다(입력 페이스가 base이다). `--bpp 2` 및 `mac-fbit-45sets`와 함께면 거부된다 |
| `-o`, `--output` (required) | all | 출력 경로 |
| `--profile NAME` (`default`), `--box x\|y\|full` (the profile's) | all | 출력의 SVFN v3 레이아웃 프로파일과 잉크 박스 정책(`svf2to3.py` 참고) |
| `--jset-version 1\|2\|auto` (1; `--blank-compat`: the input's) | all | 쓰는 JSET 블록의 버전(아래 "JSET 버전" 참고) |
| `--jset-big` (off) | all | 표준 한계(19 x 28 클래스, 128/128/64 세트)를 넘는 JSET을 허용한다(리더에 `SVF_JSET_BIG`가 필요하다). 표준 한계 안의 출력은 이 옵션이 있든 없든 같다("JSET 버전" 참고) |
| `--advance N` (none) | `source`, `mac-fbit-45sets`, `hwp1`, `--from-ttf`, `--from-svf`, `--bpp 2` | 합성된 음절의 이동 폭(JSET advance 바이트. 레이아웃의 값, 0 = 셀 폭) |
| `--ascent N` (none) | `source`, `mac-fbit-45sets`, `hwp1` | SVF의 베이스라인 행(12x24, 20x40, 24x48 페이스는 `--eng` 페이스의 베이스라인, 그 외에는 셀의 7/8). 맞춤 모드는 맞춘 페이스에서 가져오므로 무시한다 |
| `--embolden` (off) | `source`, `mac-fbit-45sets`, `hwp1` | 모든 조각과 ASCII 글리프를 오른쪽으로 1 px 민 자기 자신과 OR한다. 맞춤 모드는 무시하고, `--bpp 2`와 함께면 거부된다 |
| `--symbols` (off) | `source`, `mac-fbit-45sets`, `hwp1`, `--bpp 2` | U+2026과 U+25A1을 추가한다. 1 bpp `--from-ttf`/`--from-svf`는 무시한다 |
| `--check` (off) | `source`, `mac-fbit-45sets`, `hwp1`, `--from-ttf`, `--from-svf`, `--bpp 2` | 출력에서 11,172개 음절 전부를 합성해 검증한다(16 px의 `844`와 `844-hwp3`는 `johab844.py`와도, `hwp1`은 `hwpfont.py`의 HWP 규칙과도 비교해 `hwp1: 11172 syllables identical to the HWP 1.x rule (hwpfont.py)`를 출력한다) |
| `--from-ttf FONT` (none) | mode | 조각을 `--size`에서의 아웃라인 폰트 음절에 맞춘다 |
| `--from-svf FACE.SVF` (none) | mode | 1 bpp 완성형 SVFN 페이스를 분해한다(다른 bpp는 거부된다) |
| `--size N` (none) | `--from-ttf` | 픽셀 크기 |
| `--cell WxH` (none) | `--from-ttf` | 셀(기본 `SIZExSIZE`) |
| `--baseline N` (none) | `--from-ttf` | 베이스라인 행(기본: 잉크 박스 중앙) |
| `--present-only` / `--no-present-only` (on) | `--from-ttf` 1 bpp `mono` | 폰트가 그리는 음절만 맞출지, `.notdef`도 맞출지. `--binarize threshold\|ridge`는 그려진 음절만 맞추며 `--no-present-only`를 거부한다. `--bpp 2`와 함께면 거부된다 |
| `--blank-compat FACE.SVF` (none) | mode | 온전한 글리프가 있는 호환 자모는 그 글리프에 맡기도록 자모 세트를 다시 쓴다 |
| `--mask-font FONT\|none` (별칭 `--mask`) | `--from-ttf`, `--from-svf` 1 bpp | OpenType `ljmo`/`vjmo`/`tjmo`가 있는 마스크 폰트. 기본은 `$JAMOSET_MASK_FONT` 또는 freetype/uharfbuzz를 import할 수 있을 때 동봉된 NotoSansKR, 그렇지 않으면 자유 조각 |
| `--mask-radius N` (none) | `--from-ttf`, `--from-svf` 1 bpp | 마스크 팽창(1은 16 px까지, 2는 24까지, 그 이상은 3) |
| `--passes N` (12) | `--from-ttf`, `--from-svf`, `--bpp 2` | 좌표 하강(coordinate-descent)의 최대 패스 수 |
| `--pylib DIR` (none) | `--from-ttf`, `--from-svf`, `--bpp 2` | freetype과 uharfbuzz가 있는 디렉터리(`$JAMOSET_PYLIB`도 가능) |
| `--report FILE.json` (none) | `mac-fbit-45sets`, `--from-ttf`, `--from-svf`, `--bpp 2` | 품질 보고서를 쓴다 |
| `--bpp {1,2}` (1) | `--from-ttf` | 2 = 안티앨리어싱된 조각(fontTools 필요) |
| `--aa-refine N` (2) | `--from-ttf --bpp 2` | 레벨 오차 개선 패스(0 = 중앙값만) |
| `--binarize {mono,threshold,ridge}` (mono) | `--from-ttf` 1 bpp | FreeType 모노크롬, 정확한 면적 커버리지, 또는 그것에 희미한 능선을 더한 것(fontTools) |
| `--threshold F` (0.5) | `--from-ttf --binarize threshold\|ridge` | 커버리지 컷 |
| `--clean` / `--no-clean` (off) | `--from-ttf`, `--from-svf`, `--bpp 2` | 노이즈 정리(`--bpp 2`와 `--layout adaptive`에서는 켜짐, 그 외에는 꺼짐) |

**JSET 버전.** 버전 1이 표준이며 모든 작성기의 기본값이다. 버전 2(compact)는 메모리가 제한된 대상을 겨냥한 빌드와
팩용이다(`spec/SVF.ko.md`, "버전 2를 쓸 때"). `--jset-version`은 `1`, `2`, `auto`를 받는다. `auto`는 페이스의 버전 1
블록이 버전 2 블록보다 `JSET_V2_MIN_SAVING`(1,024)바이트 이상 크면 버전 2를 쓰고, 아니면 버전 1을 쓴다. 같은 플래그가
`jamovec.py render`와 `svf2to3.py`에도 있다. `jamoaa.py`(라이브러리)는 빌더의 `jset_version` 인자로 받으며, `jamoset.py --bpp 2`가 이를
넘긴다. `jamovec.py`는 `pack_jset`을 직접 호출한다.
라이브러리로서 `jamoset.py`에는 다음이 있다. `pack(tables, big=False)`(버전 2 블록. `Packed(block, piece_map)`로 반환되며, 맵은
조각 번호를 다시 매긴다: 처음 보면 새 번호, 나중에 보면 별칭), `pack_v1(tables, big=False)`(버전 1 블록), `pack_jset(tables,
version, big=False)`(1, 2 또는 `"auto"`. 같은 `Packed`이며 버전 1은 항등 맵), `choose_jset_version(tables, big=False)`(`auto`가 고르는 것),
`renumber_glyphs(glyphs, piece_map)`(글리프 딕셔너리나 리스트의 plane-15 코드 포인트에 맵을 적용하므로 블록과 글리프가
어긋날 수 없다), `jset_size(...)`(버전 2 크기), `jset_line(face_bytes)`(버전과 두 크기), 그리고
`unpack(block)`. `unpack`은 **두** 버전을 모두 읽고(BIG 개수도 항상) 어느 쪽이든 같은 `Tables`(슬롯별로 풀어낸 조각 목록.
빈 슬롯은 `BLANK`, 호환은 51개 조각 번호)를 돌려준다. SVF maker는 실행하는 경로에 추가 플래그로 `--jset-version 1|2`를 넘기며,
넘기지 않으면 업로드된 자모 세트 페이스는 블록의 버전을 그대로 유지한다.

**BIG (`--jset-big`).** JSET 한계는 `jamoset.JSET_LIMITS`이다. 표준은 12 x 12 클래스, 32 / 24 / 16 세트이고, BIG은 19 x 28 클래스,
128 / 128 / 64 세트이다(가장 큰 블록: 버전 1은 47,373바이트, 버전 2는 NA = 0일 때 29,708, 모든 슬롯이 별칭이면 45,068).
`unpack`은 항상 두 행을 모두 읽는다. 작성기(`pack`, `pack_v1`, `pack_jset`, `pack_fallback`, 그리고 `--jset-version`이 있는 모든 CLI인 `jamoset.py`,
`jamovec.py render`, `svf2to3.py`. `jamoaa.py`는 `jset_big`)는 표준 행을 넘는 표를 `--jset-big` / `big=True` 없이는
`JSET {name} {v} is not 1..{hi} (--jset-big allows 19 x 28 classes, 128/128/64 sets)`라는 메시지로 거부한다. `svf2to3.py`는 이 규칙을 재인코딩뿐 아니라 v2 블록(또는 JMAP 영역의 폴백)의 그대로 복사에도 적용한다. `jamoset.py --layout adaptive`와 `jamovec.py`의 `--jset-big`는 BIG 표를 쓰는 것만 허용할 뿐이며, 적응형(adaptive) 탐색 한계는 이로 인해 넓어지지 않는다(`--adaptive` / `--class-limit`를 따른다). `jamomerge.py`와 `jamofill.py`에는 그런 옵션이 없으며 BIG 표를 거부한다. `jamofill.py`(골격 읽기), `jamomerge.py`(`read_face`), `jamovec.py`(`tables_json`)는 JMAP 또는 LIST 페이스(JSET 버전 3)를 ValueError로 거부한다. 세트 표가 없기 때문이다. 표준 한계 안의 출력은 플래그가 있든 없든
바이트 단위로 같다. `needs_big(tables)`는 표에 BIG이 필요한지 알려 주고, `class_limits(big)`는
(초성, 종성) 클래스 한계를 주며, `jset_line`은 그런 페이스에 ` big=1`을 덧붙인다. `jamoadapt.FORMAT_LIMITS` / `CLASS_LIMITS`는 두 행을 모두 담고
`adapt(..., class_limit=)`는 정수 또는 (초성, 종성) 쌍을 받는다.

**JMAP (JSET 버전 3).** 라이브러리로서 `jamoset.py`는 `spec/SVF.ko.md`("버전 3: 매핑 테이블 (JMAP)")의 매핑 표 블록도 읽고 쓴다.
`Jmap`(advance, plane 개수 `pi`/`pm`/`pf`, `entries` 음절 인덱스 -> plane 인덱스, `block_compat`, 유효한 `compat`, `fallback` Tables, `pieces(cp)`), `jmap_size(ns, four, sparse,
fallback_len)`, `pack_jmap(jmap, fallback_block)`(개수가 255를 넘으면 4B, 항목이 11,172개보다 적으면 SPARSE. 한계를 넘거나 65,534바이트를 넘는 것은 거부한다), `unpack_jmap(block)`(규칙 R1-R7을 명세의 순서대로. ValueError 메시지는
`JMAP Rn ...`), `jmap_from_tables(tables, syllables, glyphs, pad)`(JSET 페이스에서 plane별로 연속된 조각과, U+F0000 + 번호를 키로 하는 새 조각 글리프. 입력 글리프는 조각 번호 또는 코드 포인트를 키로 쓸 수 있다. 페이스의 글리프 딕셔너리 전체가 통하며 낮은 키는 무시된다), 그리고
`shift_pieces(tables, delta)`(모든 조각 번호를 올린 사본. JMAP 폴백은 PI+PM+PF 이상의 조각을 지정해야 하며,
`pack_jmap`은 겹침을 거부한다). `pack_fallback(tables, version, base=0, big=False)`는 JMAP 폴백으로 쓰도록 주어진 조각 번호(에 `base`를 더한 것)를 유지하는 버전 1 또는 2 블록을 쓴다. 버전 2는 각 행을 첫 조각에서 시작해 탐욕적으로 걸으며, 하나씩 증가하는 슬롯은 새 조각으로 저장하고 그 밖의 그려진 슬롯은 모두 별칭으로 저장하므로(가장 긴 연속 탐색이 아니다) `pack`의 것보다 크다. `renumber`, `pack_v1`, `pack`, `pack_jset`, `choose_jset_version`은 `Jmap`을 거부한다
("a JMAP block has no set tables"). `blank_compat`와 `blank_whole_compat`는 JMAP 자체의 호환 항목과 폴백의 호환 항목을 비운다(`blank_compat`는 그 결과 폴백이 바뀌었으면 `fallback_block`을 같은 버전과 번호 체계로 `pack_fallback`으로 다시 인코딩한다(BIG 폴백은 `--jset-big` 여부와 관계없이 자신의 크기로 다시 인코딩되므로 `jamoset.py --blank-compat`는 이를 보존한다). `blank_whole_compat`는 JMAP의 모든 조각을 유지하고 세트 표의 쓰이지 않는 조각만 버린다). LIST 모드(플래그 0x08): `Jmap(..., list_mode=True)`는 `entries`를 음절 인덱스 -> 하나의 공유 풀에 있는 조각 번호 셋(BLANK = 없음. `pi`/`pm`/`pf`는 0)으로 유지한다. 상수 `JMAP_FLAG_LIST`, `JMAP_LIST_MAX`(255), `JMAP_LIST_ENTRIES`(118), `JMAP_LIST_ENTRY`(8). `jmap_size(ns, four, sparse, fallback_len, list_mode)`. `pack_jmap`은 list-mode `Jmap`에 대해 LIST를 쓰고(겹침 거부 없음, 255개 항목 초과는 SPARSE 힌트와 함께 거부), `unpack_jmap`은 그것을 읽으며(규칙 R1', L2, L3, R4, L6. L5/L7은 `parse_svfn`의 사용 가능 규칙이다) `jset_line`은 `list=1`을 출력한다. `unpack`은 버전 3 블록에 `Jmap`을 돌려주며, `pieces_of`, `used_pieces`, `compose`, `jset_line`(`jset=v3 jmap=BYTES ns=NS fallback=v1|v2|none`, 폴백에 BIG이 필요하면 이어서 ` big=1`)이 이를 받는다. `jmap_list(f, exceptions, compat=None, jset_version=None, fallback=True, advance=0)`는 파싱된 자모 페이스 `f` 위에 LIST를 만든다. `exceptions`는 음절 인덱스(0..11171)를 1-3개의 조각 번호(BLANK로 채움) 또는 온전한 셀(바이트, 묶인 행)에 대응시키고, `compat`는 호환 인덱스(0..50)를 조각 번호 하나 또는 온전한 셀에 대응시킨다(나머지 k는 BLANK로 남아 폴백으로 간다). 온전한 셀은 페이스의 가장 높은 U+F0000 + n 코드 포인트보다 위의 번호를 가진 새 조각이 된다(음절은 s 오름차순, 그다음 호환은 k 오름차순). 0xFFFF에 이르게 되는 번호는 거부된다. `fallback`이 켜져 있으면 페이스의 JSET(버전 1 또는 2)이 그대로 폴백으로 유지되고(`jset_version`이 다르면 번호를 유지한 채 `pack_fallback`으로 다시 인코딩된다) LIST advance는 그 advance 바이트이며 `advance`는 무시된다. `fallback=False`는 폴백 없이 `advance`로 LIST를 만든다. 필드는 BLANK(0xFFFF)일 수 있다(BLANK 번호로 준 호환은 주지 않은 것을 뜻한다). 페이스에 글리프가 없는 조각 번호는 거부된다. 255개 초과 항목, 버전 3 원본(`fallback=False`여도), `fallback=False`와 함께 준 `jset_version`, 쓸 수 있는 JSET이 없는 페이스(`fallback=False`가 아니면), 범위를 벗어난 s 또는 k, 셀도 아니고 1-3개 조각의 목록도 아닌 값, 크기가 잘못된 셀을 거부한다. `(Jmap, {cp: cell})`을 돌려주며, 호출자가 `pack_jmap(jm, jm.fallback_block)`을 쓴다. `jamoset.py`에는 JMAP을 쓰는 옵션이 없고, `jamoexc.py build`가 LIST를 쓴다.

**import하는 저장소 모듈.** `johab844.py`(844 동일성 검사용), `hwpfont.py`(`hwp1`, `844-hwp3`, HWP 영문 폰트), `jamoaa.py`, `jamofit.py`,
`jamoadapt.py`. **서드파티.** fontTools(`--bpp 2`, `--binarize threshold|ridge`, `--clean` 윤곽 도너용), freetype-py와
uharfbuzz(마스크 폰트와 1 bpp `mono`의 `--from-ttf`용). 둘 다 선택 사항이다.
없으면 `--binarize threshold|ridge`나 `--bpp 2`를 주지 않은 `--from-ttf`는 실패하고, 마스크 폰트는
메시지와 함께 건너뛴다.

**테스트.** `tools/test_jamoset.py`. `tools/test_hwpfont.py`(`hwp1`, `844-hwp3`, HWP `--eng`).

### `tools/mkfont.py`

**목적.** TTF 또는 OTF를 명시적인 코드 포인트 목록(`--unicode` 또는 `--chars-from`. 없으면 `mkfont: version 1 (code page order) is gone:
pass --unicode SET`과 함께 종료 코드 2로 끝난다)에서 Pillow의 FreeType 래스터라이저로 완성형 SVFN v3 페이스로 굽는다. 비트맵 BDF나 PCF도
FreeType을 통해 열리지만, 파일에 내장된 픽셀 크기에서만 열린다.

**상태.** 범용이다.

**입력.** Pillow의 FreeType(`PIL.ImageFont.truetype`)으로 읽는 TTF, OTF, BDF, PCF. 비트맵 BDF나 PCF는
파일에 내장된 픽셀 크기(스트라이크)에서만 열리며, 다른 크기는 `OSError: invalid pixel size`이다. `fontTools`는
폰트의 cmap에 코드 포인트가 있는지 묻는 데(`cmap_has`), `--fallback-ttf`에, 그리고 어떤
`--unicode` 코드 포인트를 버릴지 정하는 데에만 쓰인다. `cmap_has`는 sfnt가 아닌 파일(BDF, PCF, FNT)에는 None(알 수 없음)을 돌려주므로 그런 파일도
오류 없이 열린다. `--chars-from`은 게임이 쓴 파일을 읽는다(아래 참고).

**출력.** 완성형 SVFN v3 페이스. 1, 2, 8 bpp이고 가변 폭(메트릭 표), 플래그 비트 2 설정, `--profile` 레이아웃이다.
v1 옵션 `--codepage`, `--count`, `--shadow`, `--center`, `--fixed`, `--fullwidth`, `--variable`은 없어졌다(argparse가 거부한다).

**개요(Synopsis).** `python3 tools/mkfont.py INPUT OUTPUT --size N [options]`

| Option | Default | Meaning |
|---|---|---|
| `--size N` (required) | - | 렌더링할 픽셀 크기 |
| `--cell N` | 0 (= `--size`) | 셀 높이 |
| `--width N` | 0 (= cell height) | 셀 폭 |
| `--bpp {1,2,8}` | 8 | 1 스텐실, 2 네 단계, 8 커버리지 |
| `--mono-hint` | off | 1 bpp: FreeType 모노크롬 렌더러와 폰트의 힌팅 |
| `--latin` | off | Latin 베이스라인 규칙(ascent)을 고른다. `--fit-cell`/`--clip-cell`에서도 적용된다 |
| `--ink-advance` | off | 가변 폭을 폰트 메트릭이 아니라 잉크에서 가져온다 |
| `--space-advance N` | none | 가변 폭: U+0020/U+00A0의 advance를 고정한다 |
| `--punct-extra N` | 0 | 가변 폭: `. , : ; ! ? ' …`에 N px를 더한다 |
| `--ascent N` | 0 (= chosen) | 셀 위에서부터의 베이스라인 행 |
| `--fit-cell` | off | 모든 잉크가 셀에 들어올 때까지 크기를 줄인다 |
| `--clip-cell` | off | 베이스라인 하나를 유지하고 셀 밖의 잉크를 잘라낸다 |
| `--report FILE.json` | none | 페이스 옆에 JSON 보고서를 쓴다: 글리프별 잉크 박스, 셀이 자르거나(`--clip-cell`) 밀어내는 행, 개수, 선택된 크기/ascent(어느 모드든). 셀이 통째로 잘라내는 글리프는 `gone`으로 표시된다(빌드가 버린다) |
| `--probe` | off | 아무것도 자르지 않는 키 큰 셀로 굽고 `--report`를 쓴다(셀 높이와 ascent는 잉크 박스에서 나온다). 255행을 넘으면 보고서만 쓴다. `--cell`, `--ascent`, `--clip-cell`, `--fit-cell`을 거부한다(종료 코드 2) |
| `--probe-cell H` | none | `--probe`와 함께: 호출자의 셀 높이(1..255). 보고서의 `auto_ascent`가 `--clip-cell`이 그 셀에 대해 고를 베이스라인이 된다 |
| `--unicode SPEC` | "" | 코드 포인트 목록(이것 또는 `--chars-from`이 필요하다): 16진 범위, 이름 있는 세트(`ascii`, `latin1`, `hangul`, `jamo`, `cjk-punct`, `kana`, `thai`, `ksx1001`, `ksx1001-nohanja`, `ksx1001-hangul`, `ksx1001-symbols`, `cp949`, `cp949-hangul`), 또는 `file:PATH` |
| `--chars-from FILE...` | none | 그 파일들이 쓰는 코드 포인트의 합집합 |
| `--limit SPEC` | "" | 결과를 이 코드 포인트 집합과 교집합한다 |
| `--only-listed` | off | ASCII와 U+25A1을 항상 유지하지 않는다 |
| `--fallback-ttf FILE` | "" | 주 폰트에 없는 코드 포인트를 이 TTF에서 그린다 |
| `--fail-on-drop` | off | `--limit`이 `--chars-from`의 문자를 버렸으면 실패한다 |
| `--require` | off | 요청한 코드 포인트가 폰트에 없으면 실패한다 |
| `--profile NAME` | `default` | SVFN v3 레이아웃 프로파일(이름 또는 `REC,ROW,TAB,OFF` 단위) |
| `--box x\|y\|full` | the profile's | 글리프 레코드의 잉크 박스 정책 |

`--chars-from`은 파일 이름으로 네 종류를 읽는다. `TEXT.nnn`/`text.nnn`(SCI TEXT 패치: 2바이트 헤더 뒤에 NUL로 구분된
UTF-8 문자열), `*.str`/`sci-ko.str`(`script<TAB>id[<TAB>room]<TAB>text`, UTF-8), `*.map`(hires_text INI의 `missing=`
과 `[glyphs]` 절대 코드), `*.trs`(SCUMM `SCVMTRS` 번들: 본문이 BOM으로 시작하면 UTF-8, 아니면 CP949),
그리고 그 외에는 평문 UTF-8 텍스트이다.

**import하는 저장소 모듈.** 없음(독립 실행). `bdfface.py`가 이것을 import한다. **서드파티.** Pillow(필수),
fontTools(선택).

**테스트.** `tools/test_mkfont.py`.

### `tools/bdfface.py`

**목적.** 완성형 한글 비트맵 폰트(BDF)와 ASCII 비트맵 폰트(BDF 또는 HBF)에서 완성형 1 bpp SVF를 굽는다.
MI1/MI2 "L" 페이스용으로 작성되었으나 게임 전용은 아니다.

**상태.** 범용이다.

**입력.** 자체 정규식 BDF 리더(KS X 1001 `ENCODING` 또는 유니코드)와 HBF 리더(비트맵 파일이 옆에 있는 단일 바이트 코드
범위. gzip 가능). 한글 BDF와 ASCII BDF/HBF. `--chars-from`이 지정한 한글 음절(그래서 그것을 나열한 텍스트
파일이 필요하다), `--ascii`의 ASCII 0x20-0x7E, 그리고 자체 U+2026/U+25A1만 유지하며, 어느 비트맵 페이스에서도 기호나 자모를 가져오지 않는다. 셀은
BDF 자체의 박스와 관계없이 기본 24x24이다.

**출력.** 완성형 SVFN v3 페이스. 1 bpp, 가변 폭, 플래그 5(가변 폭 + 원점의 표시). U+2026(점 셋)과 U+25A1(글리프 누락 박스)을
스스로 쓴다. `--fill-absent`가 있으면 페이스에 없는, 요청된 음절을 페이스에 맞춘 자모 조각으로 합성한다(`jamoset.fit_font`를 통해).

**개요(Synopsis).**

    python3 tools/bdfface.py --hangul HANGUL.bdf --ascii ASCII.bdf|.hbf --chars-from FILE... -o OUT.SVF [options]

| Option | Default | Meaning |
|---|---|---|
| `--hangul FILE` (required) | - | 한글 BDF |
| `--ascii FILE` (required) | - | ASCII BDF 또는 HBF |
| `--cell WxH` | `24x24` | 셀 |
| `--ascent N` | ASCII face's FONT_ASCENT | ASCII 베이스라인의 셀 행 |
| `--hangul-ascent N` | Hangul face's FONT_ASCENT | 한글 베이스라인의 셀 행 |
| `--chars-from FILE...` (required) | - | 문자를 지정하는 파일(`mkfont.py` 규칙) |
| `--hangul-advance N` | the BDF's DWIDTH | 음절 advance |
| `--fill-absent` | off | 페이스에 없는, 요청된 음절을 합성한다 |
| `--mask-font FILE` | `$JAMOSET_MASK_FONT` / shipped NotoSansKR | `--fill-absent` 마스크 폰트(`none` = 자유 조각) |
| `--pylib DIR` | `$JAMOSET_PYLIB` | freetype과 uharfbuzz가 있는 디렉터리 |
| `--profile NAME`, `--box x\|y\|full` | `default`, the profile's | SVFN v3 레이아웃 프로파일과 잉크 박스 정책 |
| `-o`, `--output` (required) | - | 출력 경로 |

**import하는 저장소 모듈.** `jamoset.py`(그리고 `collect_chars_from_files`를 위한 `mkfont.py`). **서드파티.** 없음
(BDF/HBF 리더는 자체 것이다. 마스크 폰트를 쓰는 `--fill-absent`는 `jamoset.py`를 통해 freetype/uharfbuzz를 쓴다).

**테스트.** `tools/test_bdfface.py`.

### `tools/johab844.py`

**목적.** 원시 8x4x4 Johab 비트맵 폰트의 한글을 기존 16x16 1 bpp SVFN base에 넣어, 모든
음절을 조각의 OR로 다시 그리고 base의 다른 글리프는 유지한다.

**상태.** 범용이다.

**입력.** 원시 8x4x4 Johab 폰트(11520바이트, 조각 360개. 자체 리더로 읽는다)와 SVFN v3 16x16 1 bpp base(`jamoset.parse_svfn`. v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`)).
`--eng`는 원시 8x16 DOS 영문 폰트(2048 또는 4096바이트)를 읽는다.

**출력.** 한글 음절이 다시 그려진 SVFN v3 형태의 base(`jamoset.pack_svfn`. 여전히 완성형 1 bpp 페이스이다). 글리프는 코드 포인트 순서로 저장된다.

**개요(Synopsis).** `python3 tools/johab844.py JOHAB.KOR BASE.SVF OUTPUT [--eng ENG] [--profile NAME] [--box x|y|full]`

| Option | Default | Meaning |
|---|---|---|
| `--eng FILE` | none | ASCII 0x21-0x7E용 원시 8x16 영문 폰트 |
| `--profile NAME`, `--box x\|y\|full` | the base's layout, the profile's box | SVFN v3 레이아웃 프로파일과 잉크 박스 정책(`--profile`이 없으면 base 자체의 레이아웃을 유지한다) |

**import하는 저장소 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_jamoset.py`.

### `tools/macfbit_svf.py`

**목적.** Mac HangulTalk 7.1.x type-3 'fbit' 자모 plane 폰트(Seoul12, AppleGothic12/24, AppleMyungjo12/24)를
SVF v3 자모 세트 페이스로 변환한다. 모든 KS X 1001 음절이 Mac이 그리는 그대로 나온다.

**상태.** 특수 목적(폰트 패밀리 하나). Apple 폰트는 독점이다. 이 도구는 사용자가 직접 디코딩한
사본을 읽으며, 이 저장소에는 Apple의 바이트가 하나도 없다.

**입력.** 'fbit' 리소스(글리프 슬롯 482개, 241개씩 2 bank)와 InputBackSupport 'HTBL' 1(KS 코드당 4바이트:
bank와 글리프 바이트 셋. 포맷은 `tools/macfbit3.py`와 [recipes.ko.md](recipes.ko.md#클래식-mac-한글-비트맵-폰트)에 설명되어 있다). `--latin`은
패밀리 suitcase의 리소스 포크('FOND' + 'NFNT')에서 셀의 포인트 크기로 ASCII 0x20-0x7E를 읽는다.

**방법.** Mac은 모든 Mac 슬롯이 조각 하나일 때(`slot_conflicts`) 중성(그리고 ㄱ ㄹ ㅇ 종성)을 초성에 따라 12개 초성 클래스가 허용하는 것보다 더 세밀하게
고르므로, 조각은 Mac plane의 셀 상한(cap)이다. 중성 = 셀의 Mac 중성들의 AND, 종성 = 셀의 Mac 종성들의 AND, 초성 = 각 음절의 나머지(Mac 초성에
공유 중성이 빠뜨리는 초성 고유의 획을 더한 것. 잔여 픽셀로 보고된다)이다. `search_classes`는 어떤 KS 음절도 정확하지 않게 되지 않고 잔여 픽셀이 더해지지 않는 동안(또는 개수가 12를 넘을 때까지) 초성과 종성
클래스를 병합한다.
`fit_limits`는 표에 32 / 24 / 16개보다 많은 세트가 필요할 때 개별 자모를 클래스 사이에서 옮긴다. 세트: 영역(초성
클래스 / 모음 / 종성 클래스)별로 셀의 부분 행들이 일치하는 곳에서 병합된다(`cluster`). KS 밖의 8,822개 음절은
외삽한다. 음절의 각 셀이 KS 음절을 담고 세트가 KS 데이터에서 그 자모를 확정하면 "regular", 아니면 "guess"이다(어떤 KS 음절도 닿지 않는 셀은
가장 가까운 관측 셀의 세트를 취하고, 세트에 없는 자모는 가장 가까운 문맥의 평범한 Mac 글리프로 채운다). 외삽된 음절은 Mac의 출력이 아니다.

**direct 모드(기본, `--mode direct`).** 외삽 없이 Mac의 구조 자체를 쓴다. 조각이 Mac 슬롯인 JMAP 블록(JSET 버전 3,
명세 `spec/SVF.ko.md`의 "자모 세트 폰트 (플래그 비트 1)")이다(`direct_jmap`). plane별로 슬롯 순서대로(초성, 중성, 종성.
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

**실제 페이스 golden.** `tools/test_macfbit_svf.py`의 `RealFaces` 클래스는 `SVF_MAC71_INPUTS`가 `Seoul12`, `AppleGothic12`, `AppleGothic24`, `AppleMyungjo12`, `AppleMyungjo24`를 `<Name>.fbit`(디코딩된
'fbit' 리소스)와 `<Name>.htbl1`(InputBackSupport 'HTBL' 1. 모든 페이스에 같은 파일)로 담은 디렉터리를 가리킬 때 다섯 페이스를 실행한다. 직접 디코딩한 리소스로 채운다(git 밖에서. 이 저장소에는 Apple 데이터가 없다). 각
폰트의 리소스 포크에서 'fbit' 리소스(`python3 tools/macfbit3.py fbit FORK OUT`)와 InputBackSupport의 'HTBL' 1 리소스를 쓴다.

```sh
DST=/path/to/mac71-inputs; mkdir -p "$DST"
for n in Seoul12 AppleGothic12 AppleGothic24 AppleMyungjo12 AppleMyungjo24; do
  python3 tools/macfbit3.py fbit "/path/to/forks/$n.rsrc" "$DST/$n.fbit"; cp /path/to/HTBL1.bin "$DST/$n.htbl1"; done
SVF_MAC71_INPUTS=$DST python3 -m unittest tools.test_macfbit_svf.RealFaces
```

**출력.** SVFN v3, 1 bpp, 셀 h x h(12 또는 24), ascent h - h/6, JSET 플래그. 조각은 U+F0000 + n에 있다. 호환
자모는 Mac 글리프가 자기 자연 표의 조각이면 호환 조각으로, 아니면 통째로 저장된다. Latin은
글리프별 dy를 가진다(셀보다 넓은 글리프는 셀 안으로 밀어 넣으며, 기록된다). `--report`는 JSON(클래스, 세트, JSET v1과 v2의 크기,
외삽 개수, 검증)을 쓴다. `--sheets`는 PNG 시트(Mac 대 페이스 대 XOR, KS 1x/3x,
외삽 샘플, 조각. PIL 필요)를 쓴다.

**개요(Synopsis).**
`python3 tools/macfbit_svf.py analyse FBIT HTBL1 [-o OUT.json]`
`python3 tools/macfbit_svf.py build FBIT HTBL1 -o FACE.SVF [--mode direct|derived] [--no-dedup] [--with-jset] [--classes OUT.json] [--latin SUITCASE.rsrc] [--latin-size N] [--report R.json] [--sheets DIR] [--name P] [--jset-version 1|2|auto] [--jset-big]`
`python3 tools/macfbit_svf.py verify FACE.SVF FBIT HTBL1 [--classes OUT.json] [--svfdump PATH ...]`

| Option | Default | Meaning |
|---|---|---|
| `--mode direct\|derived` | direct | Mac 구조의 JMAP 페이스(KS만), 또는 외삽된 JSET 페이스 |
| `--no-dedup` | dedup on | direct: plane의 서로 다른 비트맵마다 하나가 아니라 Mac 슬롯마다 조각 하나 |
| `--with-jset` | off | direct: 도출된 JSET이 JMAP 폴백이 된다(11,172개 음절 전부 합성된다) |
| `--classes FILE` | search | `analyse` JSON의 `lc` / `tc`를 쓴다(derived, `--with-jset`, derived 페이스의 verify) |
| `--latin FILE`, `--latin-size N` | none, the cell size | 패밀리의 'NFNT' 스트라이크에서 가져오는 ASCII |
| `--jset-version 1\|2\|auto` | 1 | JSET 블록 버전(`jamoset.pack_jset`. direct: `--with-jset` 폴백의 것. auto = `jamoset.choose_jset_version`) |
| `--jset-big` | off | derived와 `--with-jset`: 19 x 28 클래스까지 탐색하고 128 / 128 / 64 세트에 맞춘다. JSET은 `big=True`로 쓰인다 |
| `--svfdump PATH` | none | C 렌더러의 음절도 함께 비교한다(`c/tests/svfdump.c`). 반복 가능 |

**import하는 저장소 모듈.** `jamoset`, `macfbit3`. **서드파티.** `--sheets`에만 PIL. **테스트.** `tools/test_macfbit_svf.py`(합성 fbit / HTBL / NFNT 픽스처).


### `tools/jamovec.py`

**목적.** 폰트의 자모를 아웃라인으로 한 번 분리해 마스터 JSON에 담고, 이후 어떤 크기든 다시 맞추지 않고 그것에서
렌더링한다.

**상태.** 범용이다.

**입력.** `master`는 fontTools(`jamoaa.OutlineFace`를 통해)로 TTF/OTF를 읽는다(`--components`는 `glyf`
합성 컴포넌트를 읽는다). `render`는 마스터 JSON을 읽는다.

**출력.** `master`는 JSON 마스터를 쓰고, `render`는 1 또는 2 bpp의 SVFN v3 자모 세트 페이스를 쓴다.

**개요(Synopsis).**

    python3 tools/jamovec.py master FONT -o MASTER.json [options]
    python3 tools/jamovec.py render MASTER.json --size N -o OUT.SVF [options]

`master` 옵션: `-o`/`--output`(필수), `--adaptive [NI,NM,NF]`(없음. 상수 `32,24,12`),
`--decision-px N`(48), `--class-limit N`(12, 엔진의 한계), `--components`(off), `--pylib DIR`(없음).
`render` 옵션: `--size N`(필수), `--bpp {1,2}`(2), `--binarize {threshold,ridge}`(threshold),
`--cell WxH`(없음), `--baseline N`(없음), `--symbols`(off), `--check`(off), `--profile NAME`(`default`),
`--box x|y|full`(프로파일의 값), `--jset-version 1|2|auto`(1), `--jset-big`(off), `-o`/`--output`(필수).

**import하는 저장소 모듈.** `jamoaa.py`, `jamoset.py`, `jamoadapt.py`, `jamofit.py`. **서드파티.** fontTools
(`master`에 필수. 래스터라이저는 자체 것이다).

**테스트.** `tools/test_jamoaa.py`.

### `tools/svfdy.py`

**목적.** 기존 SVFN 페이스의 글리프별 dy를 설정하거나 지운다. `jamoset.parse_svfn`으로 읽고 `jamoset.pack_svfn`으로 v3로 다시 쓰므로, 모든 글리프, 메트릭, JSET 블록, 플래그는 유지되고 dy 필드만 바뀐다(글리프는 `--profile` 레이아웃에서 코드 포인트 순서로 끝난다).

**상태.** 범용이다.

**입력.** 메트릭 표가 있는 SVFN v3 페이스. `jamoset.py`로 읽는다(v2 페이스는 변환 안내 메시지와 함께 거부된다(`tools/svf2to3.py`)). `--json`은 코드 포인트를
dy에 대응시킨 JSON 객체를 읽는다.

**출력.** dy 바이트와 헤더 범위가 바뀐 v3 페이스(입력과 같은 종류, bpp, 픽셀).

**개요(Synopsis).**

    python3 tools/svfdy.py INPUT [OUTPUT] [--range CPS --dy N] [--set CPS=N]... [--json FILE] [--clear] [--show] [--profile NAME] [--box x|y|full]

| Option | Default | Meaning |
|---|---|---|
| `--range CPS` | none | `--dy`를 줄 코드 포인트(예: `0x20-0x7e,0x2026`) |
| `--dy N` | none | `--range`의 dy |
| `--set CPS=DY` | none (repeatable) | 코드 포인트와 그 dy |
| `--json FILE` | none | JSON 객체 `{code point: dy}` |
| `--clear` | off | 먼저 모든 글리프의 dy를 0으로 한다 |
| `--show` | off | 범위와 dy가 있는 글리프를 출력한다(출력 파일은 필요 없다) |
| `--profile NAME`, `--box x\|y\|full` | the input's layout, the profile's box | 출력의 SVFN v3 레이아웃 프로파일과 잉크 박스 정책(`--profile`이 없으면 입력 자체의 레이아웃을 유지한다) |

자모 조각(`U+F0000..`)에 dy를 주는 것은 거부된다. 폰트에 없는 코드 포인트는 세어서 건너뛴다.

**import하는 저장소 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_jamoset.py`.

### `tools/svfscale.py`

**목적.** 비트맵 페이스를 더 작은 픽셀 크기로 그린다(40 / 48 px DOS나 프린터 페이스, 24 px BDF를 16 px로). 1 bpp는 임계값으로, 2 bpp는
덮인 비율로: 비트맵 원본에서 2 bpp 페이스로 가는 유일한 길이다.

**상태.** 범용이다.

**입력.** 1 bpp SVFN v3 페이스(완성형 또는 자모 세트: 모든 글리프를 `svfline.py`로 그리므로 자모 세트의 음절은 먼저 조합된다) 또는
BDF(`bdfface.read_bdf`: KS X 1001 또는 유니코드 인코딩).

**출력.** 셀이 `round(W x h / H)` x `h`인 완성형 SVFN v3 페이스(가변 폭. 플래그 비트 2, 원점의 표시는 원본 SVF에 있을 때만: 없으면 음수 bearing_x는 표시의 원점이
아니다). 높이(ascent, 글리프별 dy)는 h / H, 너비(진행 폭, 결합 부호의 음수
bearing_x)는 w / W로 비례해 반올림한다(w = `round(W x h / H)`). 글리프마다 자기 비트맵(`svfline.Face.coverage`: dy 이동도 부호 원점도
없고 잘리지도 않는다)에서 다시 샘플링한다. 출력 픽셀은 원본 영역 중 잉크가 차지한 정확한 비율이다. 1 bpp는 비율 >= `--threshold`
(0 < threshold <= 1)를 남기고, 2 bpp는 비율을 0..255의 커버리지 c로 반올림한 뒤 `(c x 3 + 127) // 255`를 저장한다(mkfont의 규칙).
64 MiB를 넘는 원본은 거부한다. `--compare`는 두 페이스를 한 기준선에, 모든 글리프의 dy까지 담는 화면에 그린다.

**개요(Synopsis).** `python3 tools/svfscale.py SRC --size H [--bpp 1|2] [--threshold 0.5] [--chars ks|face|all|FILE] [--compare FACE.SVF] [--profile NAME] -o OUT.SVF`

| Option | Default | Meaning |
|---|---|---|
| `--size H` | 필수 | 새 셀 높이(원본보다 작게) |
| `--bpp 1\|2` | 1 | 임계값 또는 네 단계 |
| `--threshold F` | 0.5 | 1 bpp: 픽셀을 남기는 잉크 비율 |
| `--chars` | `ks` | `ks`: ASCII 0x20-0x7E, KS X 1001 음절 2,350개, 원본의 다른 코드 포인트(평면 15에 있는 자모 세트의 조각은 빼고). `face`: 원본이 나열하는 것. `all`: 11,172 음절 전부와 함께. 또는 문자 파일 |
| `--compare FACE.SVF` | 없음 | 1 bpp 결과를 쓴 뒤, 다른 1 bpp 페이스와의 겹침(둘 다 그리는 KS 음절의 평균 IoU, 두 페이스를 한 기준선에, 2 px 안의 가장 좋은 이동)을 출력 |
| `--profile NAME`, `--box` | `default` | v3 레이아웃 프로파일 |

메시지와 함께 종료 코드 1(1 bpp가 아님, `--size`가 1보다 작거나 원본보다 작지 않음, (0, 1] 밖의 임계값, `--bpp 2`와 `--compare`,
`bdfface.py`가 읽지 못하는 BDF). **import하는 저장소 모듈.** `jamoset.py`, `svfline.py`,
`bdfface.py`. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(합성 32 px BDF를 16 px로 줄인 박스 필터 단계, 48에서 16 px로의 2 bpp 단계 규칙, 반올림한 ascent와 비례한 진행 폭과 dy가 있는
24에서 16 px, 너비 29 셀에서 w / W로 줄인 진행 폭과 부호의 bearing_x, ascent가 다른 페이스와 dy가 셀 아래로 미는 잉크의 겹침).

### `tools/svf2to3.py`

**목적.** SVFN v2 페이스를 v3로 변환하고, v3 페이스를 다른 프로파일로 다시 레이아웃하며, 픽셀, 메트릭,
합성된 음절이 하나도 바뀌지 않았다는 증명을 함께 낸다.

**상태.** 범용이다. 다른 모든 작성기는 v3만 쓰고, `jamoset.parse_svfn`은 v3만 읽는다(v2 페이스는 이 도구를 지목하는 변환 안내 메시지와 함께 거부된다). v2 파서는 `svf2to3.py`에만 있다.

**입력.** SVFN v2 또는 v3 페이스. 또는 `--tree`로 `*.SVF`(대소문자 무관)를 재귀적으로 찾는 폴더.

**출력.** `jamoset.pack_svfn`이 쓴 v3 페이스. `--tree`이면 DST 아래의 같은 상대 경로(SRC가 DST와 같을 수
있다. 다른 파일은 복사하지 않는다). 각 페이스는 대상 옆의 임시 파일에 쓰이고, `--check`가 주어지면 거기서 검사한 뒤
검사를 통과했을 때만 대상 위로 이름을 바꾼다.

**JSET 버전.** `--jset-version`의 기본은 1이다(v2는 메모리가 제한된 대상 전용). v1 블록은 v1으로 남고 v2 블록은 v1으로 쓰인다. `2`는 v2를 쓰고, `auto`는 1024 B 이상 작을 때 v2를 쓴다. `--jset-big`은 다시 인코딩되거나 그대로 복사되는 블록(v2 블록, 또는 JMAP 영역의 폴백)이 표준 한계를 넘는 것을 허용한다. `--check`는 파서가 자모 세트를 거부한 페이스를 `composed=unchecked`로 보고한다. JMAP 영역(JSET 버전 3)은 그대로 복사된다(출력의 영역 바이트가 입력과, 조각 번호까지 모두 같다). `--jset-version`은 거기에 아무것도 적용되지 않으며 stderr의 메모가 그렇게 알린다. `--check`는 `svfline.py`를 통해 두 페이스를 모두 합성하며(JMAP에만 있는 누락은 합성되지 않는다: 일반 페이스처럼 cmap 글리프이거나 없음) 출력 줄은 `jset=3 jmap=BYTES`로 읽힌다(LIST 영역, 플래그 0x08은 같은 방식으로 복사되고 다시 인코딩되지 않으며 ` list=1`이 더 붙는다). 같은 해석이 `svfline.py`, `maker/detect.py`(종류 `svf-jamo`, `jset_version` 3, `jmap_mode` `dense` / `sparse` / `list`. plane 조각, 폴백 조각, 호환이 모두 글리프를 가질 때만 사용 가능. `maker/quality.py`의 `face_facts`는 LIST에 대해 `pool`을 보고한다: LIST 블록 자체가 지명하는 서로 다른 조각의 수로, 그 항목과 자체 호환 항목을 센 것이며 폴백의 것은 아니다), `web/mkindex.py`(그런 페이스에 `jamo`가 true)에도 적용된다.

**개요(Synopsis).**

    python3 -I tools/svf2to3.py IN OUT [--profile P | --units R,W,T,O] [--box x|y|full] [--jset-version 1|2|auto] [--jset-big] [--check]
    python3 -I tools/svf2to3.py --tree SRC DST [same options]

| Option | Default | Meaning |
|---|---|---|
| `--profile P` | `default` | 아래 표의 작성기 프리셋 |
| `--units R,W,T,O` | none | 레코드, 행, 표 단위의 log2와 오프셋 폭 16 또는 32(박스 `x`) |
| `--box B` | the profile's | 박스 정책: `x`(x-boxed), `y`, `full`(전체 셀) |
| `--check` | off | 출력을 입력과 `svfline.Face`로 비교한다: 모든 코드 포인트의 has, 메트릭, 셀과 합성된 모든 음절(U+AC00..U+D7A3, U+3131..U+3163) |
| `--tree` | off | 폴더를 변환한다. 페이스마다 `REL in= out= data_in= data_out=`를 출력하고 마지막에 `total faces= ... data_out= v3_faces= v3_jset= v1_faces= ... failed=` 줄을 출력한다(`v3_*`: JMAP 페이스와 그 영역 바이트. LIST 영역은 다른 버전 3 블록처럼 그대로 복사되며 그 줄에 ` list=1`을 더한다: ` jset=3 jmap=BYTES list=1`) |

| Profile | REC / ROW / TAB (log2) | Box | Offsets |
|---|---|---|---|
| `mcu-strict` | 4 / 1 / 4 bytes (2 / 0 / 2) | x | u16, u32 when the data passes `65535 << REC` |
| `default` | 4 / 1 / 4 bytes | x | u32 |
| `dos` | 1 / 1 / 1 bytes | x | u16, u32 past 64 KB |
| `wasm` | 1 / 1 / 1 bytes | x | u16, u32 past 64 KB |
| `full` | 4 / 1 / 4 bytes | full cells | u32 |
| `simd16` | 16 / 1 / 16 bytes | x | u32 |

종료 상태: 0은 모든 페이스 통과, 1은 검사 차이(처음 다른 코드 포인트나 marks-at-origin 플래그를 지목한다), 2는 읽을 수 없거나 잘못된 입력, 디렉터리가 아닌 SRC, 읽을 수 없는 하위 디렉터리이다. 실패한
페이스는 대상을 건드리지 않고 두며 실행은 계속된다. 마지막 줄의 `faces=`, `in=`, `out=`, `data_in=`, `data_out=`는
변환된 페이스만 센다. `failed=`는 나머지를 센다. SIGTERM은 종료 전에 임시 파일을 제거한다.

**import하는 저장소 모듈.** `jamoset.py`, `svfline.py`. **서드파티.** 없음. **테스트.** `tools/test_svf2to3.py`
(픽스처는 `tools/testdata/v2/`).

### `tools/svf_synth.py`

**목적.** `jamoset.write_svfn`으로 만든, C 렌더러 테스트용 합성 SVFN 페이스를 쓴다.

**상태.** 테스트/지원 전용.

**입력.** `--marks`를 뺀 모든 종류에서 `--from`은 유효한 자모 세트 페이스이다.

**출력.** 합성 SVFN 페이스: 깨진 JSET 블록(잘못된 종류 하나)을 가진 자모 세트, JMAP(JSET
버전 3) 블록을 가진 유효한 페이스 또는 깨진 것, 8 bpp 페이스, 또는 16 px 1 bpp 플래그 비트 2 marks 페이스.

**개요(Synopsis).** `python3 tools/svf_synth.py (--jset-bad KIND | --reencode | --jset-variant V | --jmap-variant V | --jmap-bad KIND |
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
리더용으로 `limits_big`(19 x 28 클래스, 128/128/64 세트, 별칭 없음: 버전 2에서 29,708 B, `--jset-version 1`이면 47,373 B)과 `limits_big_alias`(같되 모든 슬롯이 별칭. 45,068 B. 버전 2만)를 쓰며, 각각 모든 조각에
글리프가 있다.
`--jmap-variant V`는 `jamoset.jmap_from_tables`로 FACE의 표에서 만든 유효한 JSET 버전 3(JMAP) 블록을 쓴다
(`sparse3`, `sparse4`, `dense3`, `dense4`, `hybrid1`, `hybrid2`(버전 1 또는 2 폴백 위에 16개 예외 음절), `dhybrid1` / `dhybrid2`(dense, 3 / 4바이트 항목, 버전 1 / 2 폴백 위: 34 / 45 KB 영역), `adv0`, `adv0fb`(JMAP과 그 버전 1 폴백의 advance가 0), `sparse_full`(11,172개 항목 전부를 가진 SPARSE 플래그. `pack_jmap`은 그 개수를 dense로 쓰므로 손으로 조립했다), `blanks`, `pi2047`). `--jmap-bad KIND`는 JMAP 규칙 하나를 깨뜨린다(23개의 `JMAP_BAD_KINDS`. 각각의 규칙은 모듈
docstring이 알려 준다. `jmap_missing_piece`와 `jmap_region_max`는 블록은 유효하되 리더에서 조각 글리프
규칙과 65,534바이트 영역 상한에 실패한다. `v2_as_v3`는 그 필드가 처음 깨뜨리는 규칙이며 NEODG16G에서는 R3이다).
LIST 변형과 종류는 별도의 목록이다(`LIST_VARIANTS`, `LIST_BAD_KINDS`. `JMAP_VARIANTS`와 `JMAP_BAD_KINDS`는 15개와 23개 이름을 유지하며 `--jmap-variant` / `--jmap-bad`는 둘 다 받는다). `--jmap-variant list1`(38개 항목, s = 0, 300, ..., 11,100: 폴백 자체와 다른 온전한 셀과 재조합. 원본 자신의 폴백 버전을 advance 16으로 다시 인코딩한 것 위), `list2`(버전 2 폴백, 조각 번호 5, 3, 9, ... 재부여), `list_nofb`(항목 하나, 폴백 없음), `list_blank`, `list_zero`, `list_compat`, `list_max`(255개 항목, 키 0과 11,171, 폴백 없음, 2,158바이트), `list_big`(`limits_big` 표 위). `--jmap-bad`는 22개의 `jlist_*` 종류를 받는다. `list1`의 바이트 편집(`jlist_short_nofb`, `list_nofb`의 `jlist_length`)이며 각각 `unpack_jmap`의 규칙 하나(R1, L2, L3, R4, L6. 모듈 docstring이 이름을 알려 준다)를 깨뜨린다. 단 `jlist_field_noglyph`, `jlist_field_fffe`, `jlist_compat_noglyph`(`parse_svfn`이 페이스를 나쁜 것으로 표시한다)와 `jlist_region_max`(헤더 JSET 크기 0x10000)는 예외이다.
둘 다 `--jset-version`을 무시하고, JSET 표가 있는 FACE(그 자체로 JMAP 페이스는 아님)가 필요하며, 조각 글리프의 dy를 버린다(plane은
dy 없이 쓰인다). 3바이트 종류는 4바이트 블록을 주는 FACE를, 4바이트 종류는 3바이트 블록을 주는 FACE를 거부한다(명확한 오류).
`sparse4`/`dense4`는 세 plane 모두를 255 너머까지 패딩하고 패딩된 조각을 인덱스 256부터 지명한다.
`pi2047`은 손으로 만든다. `hybrid1`은 JMAP 호환 항목 하나를 비워 폴백이 답하게 한다. `--from FACE`는 `--marks`를 뺀 모든 종류에 필요하다. `--profile P` / `--units R,W,T,O`와 `--box`는
v3 레이아웃을 고른다(기본: `default` 프로파일. `--layout-bad`와는 함께 쓸 수 없다). 기본 출력 경로는 없다.

**import하는 저장소 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_c_renderer.py`.

### `tools/jamofill.py`

**목적.** 비트맵 레퍼런스 자신의 크기로 작은 자모 세트 페이스를 만든다. 세트 골격(클래스, 세트 표,
선택적으로 어느 슬롯이 조각을 공유하는지)을 유지하고 모든 조각을 레퍼런스의 음절에서 가져온다. 바이트
예산 안에서 Arduino Uno 12 px 페이스를 위해 작성되었다(카드 t_304228de: SAM8J의 8x4x4 골격, MR1286J의 6x2x1, 레퍼런스는 Galmuri9).

**상태.** 연구용 빌더. 출력은 로컬에 있다(레퍼런스 스트라이크는 저장소에 없다).

**입력.** `--strike` 비트맵 조사 스트라이크(`NAME-PX.npz`: `cp`, `glyphs`, `meta`, 선택적인 `adv`. numpy 없이 읽는다). `--skeleton`은 `FACE.SVF`(그 클래스와 세트 표. 모든 슬롯이 각자의 조각), `FACE.SVF:tied`(그 공유도 함께: 조각이 하나의 비트맵인 슬롯은 하나의 조각으로 남는다), 또는 이름 있는 구조이다. `111`, `224`(초성과 중성은 종성 유무에 따라, 종성은 8x4x4 모음 그룹에 따라), `621`, `844`(jamoset.py의 레이아웃), `fine`(2 x 3 클래스, `sweep`의 63 / 6 / 42
세트 시작점. 병합되기 전까지는 포맷 한계를 넘는다). `--pieces`는 선택적인 추가 자모 라이브러리
(`galmuri_jamo.py analyse`의 `pieces-NAME.json`)이다.

**방법.** 스트라이크의 음절을 초성, 중성, 종성으로 나누고(`decompose_strike`: 문맥별 코어, 가로형 또는 혼합형 모음의 막대에 있는 긴 수평 구간은 모음의 것으로, 나머지는 잉크가 있는 이웃을 따라 geodesic 성장으로), 세 번 이상 쓰인 변형을 유지하며, 스트라이크 자체의 호환 자모보다 수평 또는 수직 획이 더 많은 변형은 버린다(`stroke_filter`: 이웃의 획을 가져온 것). 그런 다음 각 조각
(unit)은 좌표 하강으로, 그 unit들의 음절을 스트라이크 자체의 것과 비교해 가장 잘 합성하는 변형을 취한다. 빠진 레퍼런스 픽셀은 `MISS`(2), 남는 픽셀은 1, 두 조각 모두 잉크인 픽셀은 `OVERLAP`(3), 다른 조각에 닿는 픽셀은 `TOUCH`(0.25)의 비용이다. 가중치는 2,350개 KS X 1001 음절에 1.0, 나머지에 0.2이다. 두 개의 하드 게이트: 평행한 획의 폭이 다른 후보 조각(`width_violation`: 1 px와 2 px 줄기를 가진 ㅍ, 뭉개진 ㅃ), 또는 틱이 없거나 막대의 잘못된 쪽에 있는 중성(`tick_ok`: ㅗ ㅛ ㅘ ㅙ ㅚ는 위, ㅜ ㅠ ㅝ ㅞ
ㅟ는 아래, ㅡ는 없음), 또는 캡, 막대, 몸통을 잃은 ㅊ / ㅎ(`cap_ok`)은 거부된다(`shape_filter`,
`stroke_filter`, 그리고 픽셀 최선 조각에 대해). 그리고 중성 구별성(`Fill.medial_violations`)은 위반마다 `MEDIAL_PENALTY`(30, 가중 없음)의 비용이 든다. 같은 초성과 종성 아래에서 같은 그룹(ㅗㅛㅜㅠㅡ, ㅏㅑㅓㅕㅣ, ㅐㅒㅔㅖ,
ㅘㅙㅚㅝㅞㅟㅢ)의 다른 모음을 가진 음절과 min(2, 레퍼런스 자신의 거리) 픽셀보다 가까운 음절, 또는 틱이 다른 자모에 덮인 음절(다른 자모에 닿기만 하는 틱은 5분의 1의 비용)이다. 획 완전성(`complete_ok`, 표 `COMPLETE`): 단자음은 2픽셀 이상의 수평과
수직 획을 유지하고, ㄲ ㄸ ㅃ는 위 / 아래 잉크 행에 분리된 두 막대를 유지한다. 막대가
붙어 버린 ㄲ ㄸ ㅃ(Galmuri9는 12 px ㄲ를 그렇게 그린다)는 막대 사이를 한 픽셀 잘라 복구한 것이 제공된다(`split_double`).
누출(`leak_masks`, `Fill.leak_mask`): 문맥(모음 모양, 종성 그룹)에서 레퍼런스의 음절 5 % 미만에서만 자모가 잉크로 채우는 픽셀을, 거기서 다른 자모가 30 % 이상 채운다면 누출이며, 사용자당 픽셀마다 `LEAK_PENALTY`(40)이다. 호출자는 unit별로 비트맵을 금지할 수 있다(`Fill.banned`, {unit: set}). 금지된 후보는 절대 이기지 않는다(Uno 작업의 인식기 게이트가 이렇게 돈다: 잘못 읽힌 조각을 금지하고 fill을 다시 실행). `--pixel`이면
각 unit은 픽셀 단위 최선의 비트맵(분할이 그 자모에 준 픽셀만)도 취할 수 있으며, 풀에 추가된다. 세트
표는 쓸 때 압축된다(조각이 일치하는 세트가 병합되고, 그다음 세트 열이 일치하는 초성과 종성 클래스가 병합된다.
`build_face(fill, compact=False)` / `plain_tables`는 세트와 클래스를 그대로 둔다).
`--budget N`은 파일이 들어맞을 때까지 한 자모의 unit들을 묶는다(절약된 바이트당 손실이 가장 적은 것부터).

**출력.** `fill`: 페이스 하나(`-o`), SVFN v3 `mcu-strict`, JSET 버전 1, 스트라이크의 인쇄 가능한 ASCII(비례 폭,
`adv`에서)와 서로 다른 조각. 다시 읽어 모든 음절을 fill과 대조한다. `--report` JSON:
`bytes`, `pieces`, `jset_bytes`, 클래스와 세트 개수, `exact` / `exact_ks`, `mean_dist_ks`, `confuse_ks`(자모 하나 떨어진 음절과 2픽셀 이내인데 레퍼런스의 두 음절은 더 많이 다른 음절, 범주별: `oug` ㅗ ㅛ ㅜ ㅠ ㅡ,
`hieuh` 초성 ㅎ, `final`, `initial`, `vowel`), `overlap_ks`(모음 조각과 픽셀을 공유하는 종성 조각),
`missing3_ks`, `extra4_ks`, `medial_violations(_ks)`, `medial_pairs`(모음 쌍별: 문맥, 위반, 최소
거리, 최악의 문맥), `tick_merged_ks`(없거나 덮임), `tick_touch_ks`, `width_violation_count`,
`width_violations`(자모), `stem_widths`(자모별 수직 획 폭), `incomplete_pieces`(ㄲ 먼저),
`leak_units`와 `leak_pairs`(조각>이웃: 픽셀)이며 KS 예시가 붙는다. `sweep`: 골격에서 시작하는 탐욕적 세트 병합(손실이
가장 적은 병합), 각 `--points NI,NM,NF` 이하에 처음 이르는 상태의 페이스와 보고서, 그리고 `PREFIX-curve.json`. `sheet`:
`PREFIX-ks-{1,4}x.png`(2,350개 KS 음절, 한 줄에 50개), `PREFIX-text-{1,4}x.png`(샘플 텍스트), 그리고 `--strike`가 있으면
`PREFIX-vs-ref-4x.png`(레퍼런스 위에 올린 흔한 음절 20개).

**개요(Synopsis).** `python3 tools/jamofill.py fill --strike S.npz --skeleton SK [--pixel] [--budget N] [--pieces J ...]
-o FACE.SVF [--report R.json]`; `python3 tools/jamofill.py sweep --strike S.npz --skeleton SK [--pixel] [--budget N]
--points NI,NM,NF ... [--prefix P] -o DIR`; `python3 tools/jamofill.py sheet FACE.SVF [--strike S.npz] -o PREFIX`.
실험을 위해 가중치는 `JAMOFILL_MISS`, `JAMOFILL_OVERLAP`, `JAMOFILL_TOUCH`,
`JAMOFILL_OWN`(0: `--pixel`이 어떤 픽셀이든 취할 수 있다), `JAMOFILL_MEDIAL_PENALTY`, `JAMOFILL_LEAK_PENALTY`로 바꿀 수 있다.

**import하는 저장소 모듈.** `jamoset.py`. **서드파티.** Pillow(`sheet`만). **테스트.**
`tools/test_jamofill.py`(문맥에 무관한 자모의 합성 스트라이크: 분할, 정확한 1/1/1과 8x4x4 fill, 압축,
세트 병합, 예산 묶기, 획 폭, 틱, ㅊ/ㅎ 캡, 획 완전성과 ㄲ 복구, 누출 마스크,
중성 게이트, 명령줄).

### `tools/jamomerge.py`

**목적.** 변형이 많은 자모 세트 페이스의 변형을 병합해 더 작게 만들되, 모든 조각은 그린 그대로 유지한다. 변형이
많은 페이스(예: 모음 클래스와 종성에 따른 13개 초성 세트, 많은 중성 구간)를 Arduino Uno 예산(8,192 B, JSET 버전 1, ASCII 포함)에
맞춰야 해서 작성되었다.

**상태.** 연구용 빌더. 자체 페이스는 동봉하지 않는다.

**입력.** `--face` 자모 세트 SVF(`jamoset.py`가 읽는 어떤 JSET 버전이든). `--ref` 레퍼런스 페이스(기본: 페이스
자신. 병합된 것에서 이어 가려면 병합되지 않은 페이스를 준다). `--planes` 선택적인 레퍼런스 자모 plane JSON(
`planes` 하위 명령이 Mac type-3 `fbit`와 그 `HTBL` 1에서 쓴다. KS 레퍼런스 음절은 그때 그것에서 온다).

**방법.** 페이스는 병합 상태이다. 초성과 종성 클래스, 세 세트 표, 쓰이는 슬롯마다의 비트맵으로 이루어진다. 이동(move):
`tie`(한 자모의 모든 슬롯에서 비트맵 x를 그리던 것이 그 자모의 다른 변형 y를 그린다), `set`(한 종류의 두 세트가
하나가 된다. 자모마다 그 자모의 존재하는 모든 변형 중에서 두 세트 사용자 전체에 대한 목적 함수가 가장 작은 변형을 취한다), 그리고 초성 / 종성 `class` 병합(
(모음, 다른 클래스) 셀과 종류별로 어느 한쪽의 세트. 초성 병합에서의 초성과 종성 병합에서의 종성은 양쪽 자모가 서로소이므로 양쪽 조각을 모두 담은 합집합 세트도 만든다. 빈 슬롯은 그 음절의 존재하는 비트맵으로 채운다). 각 이동 뒤에 쓰이지 않는 슬롯과 세트는
버려지고, 일치하는 세트가, 그다음 행이 일치하는 초성과 종성 클래스가 공짜로 병합된다. 탐욕적이다. 모든 이동은
절약된 바이트당 레퍼런스에 대한 픽셀 목적 함수(잃은 레퍼런스 픽셀 `MISS` 2, 남는 픽셀 1, 두 조각이 공유하는 픽셀 `OVERLAP` 1. KS X 1001 음절의 가중치는 1.0, 나머지는 `JAMOMERGE_OTHER`, 기본 0.1)로
점수가 매겨진다. `--recog`이면 상위 `JAMOMERGE_RECOG_TOP`(16)개를 recog-11-12(바뀐 음절에 대한 가중 top-1 오류 + 0.2 x
log-loss. 연구 저장소의 `recog.py`, `SVF_RECOG_DIR`로 찾으며 추론만 한다)로 다시 채점하고 바이트당 최선을 적용한다. 하드
게이트는 음절별로, 그리고 이동이 더 나쁘게 만드는 것에 대해서만 적용된다. `tick`(ㅗ/ㅛ/ㅜ/ㅠ/ㅡ 유형 중성의 틱이 없거나
다른 조각에 덮임. 모든 음절), `medial`(같은 중성 그룹의 두 KS 음절이 같은 초성과
종성을 가지면서 min(2, 레퍼런스 거리) 픽셀보다 가까움), `stroke`(KS 음절의 레퍼런스에 있는 2픽셀 이상의 구간이 그 줄이나 이웃 줄에 대응물이 없거나, 한 픽셀을 뺀 전부를 덮는 대응물만 있음), `leak`(KS 음절의 한 컴포넌트가
레퍼런스의 두 컴포넌트를 잇는 것: 틈을 가로지르는 잉크), 그리고 `--recog`이면 `recog`(바뀐 슬롯의 가장
중립적인 음절이 전에는 그 자모로 올바르게 읽혔는데 후에는 잘못 읽힘). `--soft`이면 게이트가 걸리는 이동이 남지 않았을 때(
게이트 바닥. `PREFIX-floor.SVF`로 쓴다) `stroke`와 `leak`이 비용이 된다(`JAMOMERGE_SOFT`, KS 음절당 40).
`tick`과 `medial`은 계속 하드이다. KS가 아닌 음절은 KS 음절처럼 병합된 표에서 합성되며, 이들의 stroke
와 leak 플래그는 비용만 든다(20 x 가중치).

**출력.** `-o DIR`에: `--points` 예산마다 페이스 `PREFIXnK.SVF`(SVFN v3 `mcu-strict`, JSET 버전 1,
메트릭과 dy가 있는 페이스의 ASCII. 다시 읽어 모든 음절을 검사한다)와 `PREFIXnK.json`(바이트, 부분, 세트,
클래스, 조각, 게이트 개수, 그려진 자모별 줄기 폭, `--recog`이면 인식기 top-1, `soft_gates`).
`PREFIX-steps.json`(적용된 모든 이동: 종류, 절약된 바이트, 픽셀과 인식기 델타, 바뀐 음절, 게이트별
거부). 이동이 남지 않은 곳의 `PREFIX-stop.SVF/.json`. `baseline`은 페이스의 크기 부분을
`mcu-strict` / JSET v1로, 고정 부분(헤더, ASCII, 가장 작은 JSET), 게이트 개수, 줄기 폭을 출력한다(또는 `-o`).

**개요(Synopsis).** `python3 tools/jamomerge.py baseline --face F.SVF [--planes P.json] [-o R.json]`;
`python3 tools/jamomerge.py merge --face F.SVF [--ref UNMERGED.SVF] [--planes P.json] --points 8192 7168 ... [--recog
[--threads N]] [--soft | --start-soft] [--batch] [--prefix P] -o DIR`(`--batch`: 다음 지점을 훨씬 넘을 때, 단계마다 음절이 서로소인 서로 다른 자모의 여러
tie를 묶어서 처리하며 픽셀 목적 함수만 쓴다. 함께 적용했을 때 게이트를 깨면 배치는 가장 좋은 이동까지 되돌려진다). `python3 tools/jamomerge.py planes FBIT.bin HTBL1.bin -o
P.json`.

**import하는 저장소 모듈.** `jamoset.py`, `jamofill.py`. **서드파티.** 없음(`--recog`이면 numpy와 torch).
**테스트.** `tools/test_jamomerge.py`(합성 페이스: 빌드 / 읽기 왕복과 크기, 정규화, 모든 이동이
약속대로 합성되는지, 탐욕 단계 하나, leak, stroke, tick 게이트).

### `tools/jamoexc.py`

**목적.** LIST 예외 페이스를 쓴다. 자모 세트 페이스에 선택한 음절과 호환 자모를 위한 온전한 글리프와 조각 재조합을 더한 것이며, list 모드의 JMAP 블록(spec/SVF.md, JMAP LIST)이다. 페이스 자신의 JSET 바이트는
폴백으로 남으므로 목록에 없는 모든 음절은 전과 같이 그려진다.

**개요(Synopsis).** `python3 tools/jamoexc.py build FACE.SVF EXC.json OUT.SVF [--jset-version 1|2] [--profile P] [--box B]`.

**EXC 형식.** 음절 또는 호환 자모를 키로 하는 JSON 객체. 키는 문자(`"가"`, `"ㄱ"`) 또는 `"U+AC00"`이며, 두 번 쓴
키는 거부된다. 값은 `{"whole": "HEX"}`(`ceil(cell_w * bpp / 8)`바이트의 행 `cell_h`개를 16진수로. 16진 행만
받으며 PNG 입력은 없다) 또는 `{"pieces": [n, n, n]}`(페이스의 조각 번호: 음절은 1개에서 3개, 호환 키는 정확히 1개)이다. `whole` 셀은
페이스의 가장 높은 U+F0000 + n 코드 포인트보다 위의 번호를 가진 새 조각 글리프가 된다
(음절 오름차순, 그다음 호환 자모 오름차순). 번호 0xFFFF(BLANK)는 절대 부여되지 않는다. 값의 다른 키
(`dy`, `advance`, ...)는 거부된다. 조각은 dy나 메트릭을 가지지 않는다.

**출력.** 한 줄, `jmap=BYTES ns=N whole=W recomb=R total=BYTES`. `jmap`은 JMAP 블록의 바이트 크기(LIST
헤더, 항목, 호환, 그대로 복사한 폴백), `ns`는 LIST의 음절 항목 수, `whole`은 쓴 새 온전한
글리프(`"whole"` 값마다 하나. 음절과 호환 자모), `recomb`는 `"pieces"`로 준 항목(
음절과 호환 자모. `"whole"`은 거기에 세지 않는다), `total`은 출력 파일의 바이트 크기이다. N >= 200이면
줄 끝에 ` sparse=BYTES`가 붙는다(1604 + 3 N: 항목 N개의 SPARSE 블록 크기이며 LIST와 견주기 위한 것).
`svf/dos/NEODG16G.SVF`에 `{"가": {"pieces": [1, 2]}, "ㄱ": {"pieces": [3]}}`를 준 예:
`jmap=779 ns=1 whole=0 recomb=2 total=10808`.

**충실도.** 출력은 원본의 레이아웃(rec/row/tab/off 단위 유지. `--box`가 없으면 박스 정책은 x, 픽셀은
동일. `--profile`은 요청 시 레이아웃을 바꾼다), JSET 버전과 바이트(`--jset-version 1|2`는 버전이 바뀔 때만 폴백을 `pack_fallback`으로 다시 인코딩하며 조각 번호는 유지한다. 그 밖에는 절대 다시 인코딩하지 않는다), 그리고 모든 원본 글리프의 셀, advance, 베어링, 잉크 폭, dy를 유지한다. 새
조각은 페이스의 첫 조각 글리프의 메트릭과 dy 0을 받는다. 보드나
저장소에서 읽거나 쓰는 것은 없다. 쓰는 파일은 출력 경로뿐이며 성공했을 때만, 임시 파일에 쓰고 이름을 바꾸는 방식으로 쓴다.

**거부(종료 코드 1, 텍스트는 stderr. 사용법 오류는 종료 코드 2).** 255개 초과 항목: `jmap_list: N LIST entries is over
255: use SPARSE (1604 + 3N B plus plane copies for recombinations)`. 버전 3 원본(`the face already has a JSET
version 3 block; start from the plain face`). 쓸 수 있는 JSET이 없는 페이스(`the face has no usable JSET block; start
from a jamo face whose JSET parses`). 길이가 잘못되었거나(기대하는 바이트 수를 알려 준다) 16진수가 아닌 `whole`, 조각이 하나가 아니거나 65535(BLANK. 폴백의 것을 유지하려면 키를 생략한다)인 호환
키, 두 번 쓴 키(JSON에 문자 그대로 두 번 쓴 경우도), 한 문자 또는 `U+` 뒤에 16진수 4에서 6자리가 아닌 키, 음절 항목이 없는 EXC
(`a LIST needs at least one syllable entry (L3); compat jamo alone cannot be listed`), u16
오프셋을 넘는 글리프 데이터(메시지가 해결책을 알려 준다: 온전한 셀을 줄이거나, u32 또는 auto 오프셋의 `--profile`), 조각이 0개이거나 3개를 넘는 음절, 글리프가 없는 조각 번호, 
U+AC00..U+D7A3과 U+3131..U+3163 밖의 키, 값 안의 알 수 없는 키.

**import하는 저장소 모듈.** `jamoset.py`. **서드파티.** 없음.
**테스트.** `tools/test_jamoexc.py`(`svf/dos/NEODG16G.SVF` 위의 합성 셀: Python `compose`가 LIST 리더 빌드(매핑 및 스트리밍)의 `svfdump
syllables`와 같음. `default`와 `dos` 원본에 대한 레이아웃, 메트릭, dy 충실도. 200에서의 sparse 메모. 거부.
버전 재인코딩).

## 맞춤 및 분리 모듈(명령줄 없음)

`jamofit.py`, `jamoaa.py`, `jamoadapt.py`는 `jamoset.py`와 `jamovec.py`가 import한다. `jamoseg.py`는
어떤 도구도 import하지 않고 `tools/test_jamoaa.py`만 import한다. 이들 중 `main`을 가진 것은 없다.

### `tools/jamoaa.py`

**목적.** 아웃라인 폰트에서 안티앨리어싱된(2 bpp) 자모 세트를 만든다. 그리고 `jamoset.py --from-ttf --bpp 2`와 `jamovec.py`가 쓰는 공유 아웃라인 래스터라이저/윤곽 로직이다.

**상태.** 범용이다.

**입력.** fontTools로 읽는 아웃라인 폰트(glyf 또는 CFF, 컴포짓 분해). fontTools pen을 통한다.

**출력.** 직접 쓰는 것은 없다. 호출자가 쓰는 커버리지 래스터, 묶인 레벨, 맞춘 조각, 표를 돌려준다.

**CLI.** 없음. 함수는 `jamoset.main_aa`와 `jamovec.py`가 호출한다.

**import하는 저장소 모듈.** `jamofit.py`, `jamoset.py`, `jamoadapt.py`(지연 import). **서드파티.** fontTools
(아웃라인 경로에 필수. `--pylib` 또는 `$JAMOSET_PYLIB`로 찾는다).

**테스트.** `tools/test_jamoaa.py`.

### `tools/jamoadapt.py`

**목적.** 맞춘 자모 세트를 위한 적응형(adaptive) 세트 체계. 844에서 시작해 조각을 공유하는 음절들이 서로 어긋나는 곳에서 세트를 쪼개며, 엔진의 JSET 한계(초성 12개와 종성 12개 클래스, 32/24/16 세트)까지 간다.

**상태.** 범용이다.

**입력.** "도너(donor)": `jamoaa.contour_donors`(아웃라인) 또는
`jamoaa.pixel_donors`(비트맵)에서 가져온, 슬롯별로 존재하는 각 음절 자신의 래스터.

**출력.** 표가 매핑을 인코딩하는 `adaptive`라는 이름의 `jamoset.Layout`(파일 없음).

**CLI.** 없음. `jamoset.py --layout adaptive`와 `jamovec.py --adaptive`를 통해 쓰인다.

**import하는 저장소 모듈.** `jamoset.py`. **서드파티.** 없음.

**테스트.** `tools/test_jamoaa.py`가 테스트한다(`--layout adaptive` 경우들).

### `tools/jamofit.py`

**목적.** 마스크가 있는 좌표 하강으로 자모 세트 조각을 완성형 1 bpp 음절에 맞추고, 그 맞춤에 점수를 매긴다
(IoU, 1 px 허용 F1, blob과 stray-ink 메트릭).

**상태.** 범용이다.

**입력.** Python 정수("gints")로 된 글리프 래스터. 선택적인 아웃라인 마스크 폰트(OpenType 자모
변형이 있는 NotoSansKR)는 freetype-py로 읽고 uharfbuzz로 셰이핑한다.

**출력.** 맞춘 조각과 품질 수치(파일 없음).

**CLI.** 없음. `jamoset.py --from-ttf`/`--from-svf`와 `bdfface.py --fill-absent`가 쓴다.

**import하는 저장소 모듈.** 없음. **서드파티.** freetype-py와 uharfbuzz(선택: 마스크 폰트와
아웃라인 `mono` 대상만 필요로 한다).

**테스트.** `tools/test_jamoset.py`(직접 import한다)와 `tools/test_jamoaa.py`.

### `tools/jamoseg.py`

**목적.** 벡터 자모 분할: 윤곽 그룹화, peer, 영역 클리핑으로 음절의 아웃라인을 초성, 중성, 종성의 아웃라인으로
폰트 단위에서 나눈다.

**상태.** 범용이다.

**입력.** 폰트 단위의 음절 아웃라인(fontTools pen에서).

**출력.** 음절별로 슬롯마다의 닫힌 폴리라인 목록과 각 그룹이 어떻게 결정되었는지(파일 없음).

**CLI.** 없음. **import하는 저장소 모듈.** 없음. **서드파티.** 병합된 아웃라인을 클리핑하는 skia-pathops(`pathops`, 선택: 없으면
`load_pathops`가 None을 돌려준다).

**테스트.** `tools/test_jamoaa.py`.

## 검사와 확인

### `tools/facecheck.py`

**목적.** 페이스 매니페스트와 맵 페이스 검사: 커밋된 모든 페이스의 sha256을 기록하고, 이동 후 매니페스트를 검증하며,
맵이 지명하는 모든 페이스를 찾을 수 있는지 검사한다.

**상태.** 범용이다.

**입력.** git blob(`manifest`), 매니페스트 TSV(`verify`), 맵 파일, 그리고 선택적으로 builtin zip(`mapfaces`).

**출력.** 매니페스트 TSV, 또는 `MISSING`/`CHANGED` 줄과 종료 코드. 폰트는 쓰지 않는다.

**개요(Synopsis).**

    python3 tools/facecheck.py manifest --git REPO --rev REV --path DIR [--path DIR ...] [--exclude GLOB] [--exclude GLOB ...] -o OUT.tsv
    python3 tools/facecheck.py verify MANIFEST.tsv [--map OLD_PREFIX=NEW_DIR] [--map OLD_PREFIX=NEW_DIR ...]
    python3 tools/facecheck.py mapfaces --maps DIR [--maps DIR ...] --root PREFIX=DIR [--root PREFIX=DIR ...] [--builtin-zip FILE] [--builtin-zip FILE ...]

모든 목록 옵션은 `action="append"`이다. 플래그마다 값 하나를 주고 플래그를 반복한다. `manifest`: `--git`, `--rev`,
`--path`(필수), `--exclude`, `-o`(필수). `verify`: `MANIFEST.tsv`, `--map`. `mapfaces`: `--maps`(필수),
`--root`(필수), `--builtin-zip`.

**import하는 저장소 모듈.** 없음. **서드파티.** 없음(git, zipfile). **테스트.** `tools/test_facecheck.py`.

### `tools/fontmetrics.py`

**목적.** 페이스의 advance가 글리프를 감당하는지 보고한다. 헤더, 관찰된 advance와 잉크 폭을 출력하고,
`bearingX + inkWidth`가 advance를 넘는 글리프를 나열한다.

**상태.** 범용이다.

**입력.** SVFN 페이스. 자체 `struct` 헤더 리더로 읽는다.

**출력.** 텍스트 보고서(파일 없음).

**개요(Synopsis).** `python3 tools/fontmetrics.py FACE [FACE ...]`(옵션 없음).

**import하는 저장소 모듈.** 없음. **서드파티.** 없음. **테스트.** 없음.

### `tools/svfline.py`

**목적.** C 렌더러의 줄 그리기를 위한 Python 레퍼런스: UTF-8을 디코딩하고, 체인에서 각 코드 포인트의 페이스를 고르며,
advance, dy, 결합 표시와 함께 한 베이스라인에 셀을 그리고, 한 줄을 측정한다.

**상태.** 범용이다.

**입력.** SVFN 페이스. `jamoset.parse_svfn`과 엔진의 로드 규칙으로 읽는다(dy 범위는 유효할 때만, 메트릭 표는
맞을 때만, JSET 블록은 풀리고 모든 조각에 글리프가 있을 때만).

**출력.** stdout의 GRAY8 버퍼(`line`) 또는 한 줄 측정값(`measure`). 라이브러리로도 쓰인다. `layout`, `measure`,
`placements`, 그리고 `Target` 변환.

**개요(Synopsis).**

    python3 tools/svfline.py line W H X Y TEXT FACE...
    python3 tools/svfline.py measure TEXT FACE...

옵션 없음. `TEXT`는 인자의 바이트이며 UTF-8로 디코딩된다(잘못된 부분은 U+FFFD가 되거나, 어떤
페이스에도 없으면 건너뛴다). 라이브러리는 렌더러의 스케일링을 위해 `scale=(num, den)`을 받는다.

**import하는 저장소 모듈.** `jamoset.py`. **서드파티.** 없음. **테스트.** `tools/test_c_renderer.py`와
`tools/test_web_picker.py`.

### `tools/vesa_lines.py`

**목적.** `c/ports/dos/vesa-lines.txt`(DOS VESA 예제의 색과 줄 표)의 Python 리더이며
그 예제의 오라클이다. 파일의 줄을 그린 뒤 `c/ports/dos/svfvesa.c`의 백 버퍼가 담아야 할 내용이다. 이 파서는 `c/ports/dos/vesa_lines.c`와 일치한다(같은 표, 팔레트, 같은 줄에서의 거부 메시지). 둘을
함께 바꾼다.

**상태.** 특수 목적(DOS VESA 예제).

**입력.** `vesa-lines.txt` 파일(형식은 `c/ports/dos/vesa_lines.h`와 `c/ports/dos/README.md`에 있다)과, `--expect`에서는 그것이 지명하는 페이스의 디렉터리(8.3 대문자 `.SVF` 이름).

**출력.** `--print-table`: `c/tests/vesa-lines-dump`가 출력하는 형태의 파싱된 표와 팔레트. `--expect`:
`sum=<예상 백 버퍼의 FNV-1a, 16진수 8자리>`. 거부는 `line N: message`를 출력하고 0이 아닌 값으로 종료한다.

**개요(Synopsis).**

    python3 tools/vesa_lines.py --print-table FILE [--dac 6|8]
    python3 tools/vesa_lines.py --expect FILE --faces DIR W H BPP

`BPP`는 8, 15, 16, 24, 32이다(INDEXED8, RGB555, RGB565, RGB888, XRGB8888).

**import하는 저장소 모듈.** `svfline.py`(그리고 그것을 통해 `jamoset.py`). **서드파티.** 없음. **테스트.**
`tools/test_c_renderer.py`(`TestVesaLines`). `c/ports/dos/vesa-shots.sh`가 쓴다.

## 빌드 스크립트

### `tools/build/build_faces.py`

**목적.** 저장소 자체의 도구로 `svf/`의 페이스를 업스트림 폰트에서 다시 빌드하되, 레시피 표
`tools/build/faces.tsv`가 정한 대로 하고, 각 결과를 `svf/`의 페이스와 비교한다.

**상태.** 범용(동봉된 페이스의 출처 검사. [recipes.ko.md](recipes.ko.md)가 모든 레시피를 설명한다).

**입력.** `tools/build/faces.tsv`(face, method, source, args, codepoints, expect, note. `svf/`의 모든 페이스마다 한 행), `tools/build/cps/` 아래의 코드 포인트 목록, `ttf/`의 원본 폰트. source가
`ext:NAME`인 행은 이 저장소에 없는 폰트를 지명한다. `--ext NAME=PATH`가 그것을 공급하며, 없으면 그 행은
`skipped`로 보고된다.

**출력.** 빌드하는 모든 행에 대한 `OUT/<face>`와, stdout에 페이스당 한 줄: `identical`(`svf/`와 같은 바이트),
`pixels`(같은 글리프, 메트릭, 헤더 값이 다른 바이트 레이아웃으로) 또는 `differs: ...`(무엇이 다른지).
그다음 `build_faces:` 합계 줄. `OUT` 밖에는 아무것도 쓰지 않는다.

**개요(Synopsis).** `python3 tools/build/build_faces.py --out DIR [FACE ...] [--ext NAME=PATH ...] [--list]`. FACE는 행의
face(`dos/NGOTB15.SVF`) 또는 그 파일 이름이다. 없으면 레시피가 있는 모든 행을 뜻한다. 빌드된 모든 페이스가 행의 `expect`와 일치하면 종료 코드 0(`identical` 행은 동일해야 한다), 아니면 1, 사용법 오류는 2이다. `mkfont` 행은
`tools/mkfont.py SOURCE OUT ARGS --unicode CODEPOINTS`를 실행한 다음 `tools/svf2to3.py --profile default`(
`svf/`의 표준 레코드 순서)를 실행한다. `jamoset` 행은 `|` 앞의 인자로 `mkfont.py`를, 뒤의 인자로 `tools/jamoset.py --from-svf`를
실행한다.

**import하는 저장소 모듈.** `tools/jamoset.py`(그리고 `mkfont.py`, `svf2to3.py`, `jamoset.py`를 실행한다).
**서드파티.** `mkfont.py`의 것(Pillow, fontTools). **테스트.** `tools/test_build_faces.py`.

### `tools/build/faces.tsv`

**목적.** `tools/build/build_faces.py`의 레시피 표. `svf/`의 모든 페이스마다 한 행(face, method, source,
args, codepoints, expect, note). `method`는 `mkfont`, `jamoset`, `none`(이 저장소의 도구로는 레시피 없음.
note가 이유를 말한다)이다. `codepoints`는 `mkfont.py --unicode` 세트 또는 `tools/build/cps/` 아래 파일(한 줄에 16진 코드 포인트
하나 또는 범위. 페이스 자체의 코드 포인트 목록)을 지명한다. [recipes.ko.md](recipes.ko.md)가 모든 행을 설명하며, `tools/test_build_faces.py`가
표를 완전하게 유지한다.

## 웹(WASM 선택기)

### `web/build.sh`

**목적.** WASM 폰트 선택기를 빌드한다: `svf.js` + `svf.wasm`으로서의 C 렌더러, 페이스 인덱스, 페이스와
라이선스 파일.

**상태.** 범용이다.

**입력.** `c/` 아래의 C 소스, `svf/`, 페이지 소스. emsdk의 emcc가 필요하다.

**출력.** `OUT`(기본 `web/dist`) 아래에: `svf.js`, `svf.wasm`, `faces.json`, `faces/<group>/<FILE>.SVF`,
`licences/<group>/<FILE>`, 그리고 `index.html`, `picker.js`, `style.css`의 사본.

**개요(Synopsis).** `bash web/build.sh [OUT]`. 환경 변수: `EMSDK`(기본 `~/opt/emsdk`). `web/mkindex.py`와
`web/copyfaces.py`를 호출한다.

**import하는 저장소 모듈.** 없음(`web/mkindex.py`와 `web/copyfaces.py`를 실행한다). **서드파티.** emscripten
(emsdk의 `emcc`). **테스트.** `tools/test_web_picker.py`(`web/build.sh`를 통해).

### `web/copyfaces.py`

**목적.** `faces.json`이 지명하는 페이스와 라이선스 파일을 `SVF_DIR`에서 `OUT`으로 복사하며, 모든 경로가
루트 아래에 머무는지 검사한다.

**상태.** 범용이다.

**입력.** `SVF_DIR`과 `faces.json`(표준 `json` 모듈로 읽는다).

**출력.** `OUT` 아래에 복사된 페이스와 라이선스 파일(폰트는 바뀌지 않는다).

**개요(Synopsis).** `python3 web/copyfaces.py SVF_DIR FACES_JSON OUT`(옵션 없음). `F faces, N MB copied`를 출력하며
첫 번째 잘못된 경로에서 종료 코드 2로 끝난다.

**import하는 저장소 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_web_picker.py`(`web/build.sh`를 통해).

### `web/mkindex.py`

**목적.** `svf/`와 라이선스 및 패밀리 표에서 선택기의 페이스 인덱스인 `faces.json`(형식 `svf-fonts-web-index/1`)을 쓴다.

**상태.** 범용이다.

**입력.** 모든 `svf/**/*.SVF`. `tools/jamoset.py parse_svfn`과 `tools/svfline.py Face`(경로로 로드)로 읽는다.
`LICENCES.tsv`와 `FAMILIES.tsv`(그리고 `svf/jamo-extra/FACES.TSV`).

**출력.** `faces.json`. 페이스당 항목 하나(key, url, group, label, cell, px, bpp, ascent, glyphs, jamo, flags,
bytes, licences, hangul, latin_only, subset, family, style, variant). 폰트는 쓰지 않는다.

**개요(Synopsis).** `python3 web/mkindex.py SVF_DIR OUT_JSON [--licences TSV] [--families TSV]` 또는
`python3 web/mkindex.py SVF_DIR --check [--licences TSV] [--families TSV]`.

| Option | Default | Meaning |
|---|---|---|
| `--check` | off | 모든 검사를 실행하고 아무것도 쓰지 않는다 |
| `--licences TSV` | `LICENCES.tsv` beside this script | 페이스-라이선스 표 |
| `--families TSV` | `FAMILIES.tsv` beside this script | 페이스-패밀리 표 |

**import하는 저장소 모듈.** `tools/svfline.py`(그리고 그것을 통해 `tools/jamoset.py`). **서드파티.** 없음.
**테스트.** `tools/test_web_picker.py`.

## 파일 안의 폰트를 찾아 잘라 내기

실행 예는 [recipes.ko.md](recipes.ko.md#claude와-함께-프로그램이나-데이터-파일-안의-폰트-찾기)(DOS TSR, DOS 드라이버, 한글 VGA 폰트
ROM)와 [recipes.ko.md](recipes.ko.md#os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기)(OS/2)에 있다. 이 도구들은 바이트만 읽고
파일의 코드를 실행하지 않는다. 내려받은 파일에는 `python3 -I`로 실행하라.

### `tools/binscan.py`

**목적.** 어떤 파일(`.COM`/`.EXE`, TSR, ROM 덤프) 안에서 비트맵 폰트가 어디 있는지 찾고 오프셋에 있는 것을 그려, 사람이나
어시스턴트가 폰트가 어디서 시작하고 어떻게 저장되었는지 볼 수 있게 한다.

**상태.** 범용이다.

**입력.** 아무 파일. 글리프 기하: `--glyph WxH`, `--stride B`(기본은 글리프의 바이트 수), `--order rows`(행 우선, 한 행이 ceil(W/8)
바이트), `strips`(H 바이트짜리 8 픽셀 너비 스트립이 차례로: 한글 VGA 폰트 ROM과 6x2x1 폰트, jamoset의 `g_bytecols`), `cols`(열 우선, MSB가
위: 도깨비 프린터 배치), `bytecols`(W 바이트짜리 8행 띠, 바이트 하나가 한 열, 비트 7이 띠의 맨 위 행), `--lsb`(비트 0 = 왼쪽 픽셀,
`cols` / `bytecols`에서는 맨 위). `render`는 그리는 바이트만 읽고(`--count` 1..4096, `--cols` 1..64, `--scale` 1..32), `info`는
블록씩 읽는다.

**출력.** stdout의 텍스트. `render --png`는 회색조 PNG를 쓴다(zlib, Pillow 없음).

**개요(Synopsis).**

    python3 tools/binscan.py info FILE [--block B]
    python3 tools/binscan.py runs FILE --glyph WxH [--min N] [--max-change C] [--start O] [--length N]
    python3 tools/binscan.py sets FILE [--sets NI,NM,NF] [--slots SI,SM,SF] [--glyph WxH] [--min-inked F] [--start O] [--length N]
    python3 tools/binscan.py ascii FILE [--height H] [--start O] [--length N]
    python3 tools/binscan.py render FILE --offset O --glyph WxH [--count N] [--cols C] [--png OUT --scale S]

| 명령 | 출력하는 것 |
|---|---|
| `info` | 크기, 종류(적재 이미지와 LZEXE / PKLITE 표시가 있는 DOS MZ, `.COM`, ARJ, ZIP, 옵션 ROM `55 AA`), 파일과 바이트 크기가 맞는 배치, 블록별 엔트로피 지도(바이트당 8비트에 가까우면 압축됨) |
| `runs` | 글리프처럼 보이는 창(잉크 2-60 %, 행끼리 거의 변하지 않음)이 `--min`(32)개 이상 이어지는 구간 |
| `sets` | 원시 자모 조각 폰트의 모든 세트 슬롯 0이 빈 칸이고 다른 슬롯의 `--min-inked`(0.8) 이상에 잉크가 있는 오프셋. 가까이 붙어 통과하는 읽기 묶음 가운데 행이 바이트 이음매(x = 7 / 8)를 가로질러 붙어 있는 것을 고르고, 한 행씩 떨어져 같은 점수를 얻는 읽기들은 순위 없이 함께 나열한다(드라이버 코드나 따로 된 사본으로 정한다) |
| `ascii` | 8xH 영문 폰트의 오프셋: 공백은 빈 칸, `_`는 아래 3분의 1, `-`는 가운데, 0x21-0x7E는 잉크 있음. 묶음 가운데 첫 행이나 마지막 행에 잉크가 있는 글리프가 가장 적은 정렬 |
| `render` | 오프셋부터의 글리프를 번호와 파일 오프셋을 붙인 `#`/`.` 텍스트로, 또는 PNG로 |

`runs`, `sets`, `ascii`는 훑는 창의 모든 오프셋을 시도한다. `--start O` / `--length N`이 창을 정하고(출력하는 오프셋은 파일
오프셋 그대로), 16 MiB를 넘는 창은 거부한다(큰 파일은 겹치는 창으로 나눠 훑어라). 한글 VGA 폰트 ROM에는 `--order strips`를 쓴다.
종료 코드 0. argparse 오류(0이나 음수인 `--block`, `--step`, `--stride`, `--glyph`, `--count` ...)는 2. **import하는 저장소 모듈.**
없음. **서드파티.** 없음. **테스트.** `tools/test_extract.py`.

### `tools/nkpspec.py`

**목적.** NKP 한글 TSR(1989년 허큘리스 한글 드라이버 NKP.COM V3.00, NKP3.COM)의 `rawcarve.py compose` 명세를 드라이버 자신의 표에서
쓴다: 조각 세트 레코드, 자모 표, 한글 루틴의 초성 세트 표와 중성 선택 표(recipes.ko.md, NKP).

**상태.** 특수 목적(한 드라이버 계열). 다른 드라이버용 "드라이버 표에서 명세로" 스크립트의 모양을 보여 준다.

**입력.** 드라이버의 .COM 이미지. 표 주소는 그것을 쓰는 명령어 바이트로 찾거나(`find`) 메모리 주소로 준다(`--desc`, `--cho`,
`--jung`, `--jong`, `--iset`, `--med`. 파일 오프셋 = 주소 - 0x100).

**출력.** `find`: 표마다 한 줄(메모리 주소, 파일 오프셋. 영문 폰트도). `spec`: JSON 명세(오프셋과 규칙뿐): 플래그 비트 0이 켜진
레코드는 (끝 - 첫) / 2 행의 16 픽셀 조각, 꺼진 레코드는 한 바이트짜리 (끝 - 첫 + 1) / 2 행의 오른쪽(또는 왼쪽) 절반 조각. 초성 세트
표와 중성 표는 레코드를 바이트 오프셋으로 가리킨다(레코드 = 값 / 6). 종성 세트는 레코드 96.

**개요(Synopsis).** `python3 tools/nkpspec.py find FILE`, `python3 tools/nkpspec.py spec FILE [--desc A ...] -o SPEC.json`. 표가 없거나
파일 밖이거나 NKP 모양이 아니면(자모 표가 유니코드 순서가 아님, 레코드 오프셋이 6의 배수가 아님, 0x100보다 작은 조각 주소, 행이 없는 16 픽셀 레코드) 메시지와 함께 종료 코드 1.

**import하는 저장소 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(명령어 패턴과 표를 가진 합성 .COM. 명세의
기하와 조합한 음절).

### `tools/rawcarve.py`

**목적.** `binscan.py`로 찾은 폰트를 파일에서 잘라 다른 도구가 읽는 것으로 만든다: 날 바이트, 원시 8x16 영문 폰트, ASCII나 KS X 1001
음절의 유니코드 BDF, 또는 JSON 명세로 적은 규칙대로 조합한 자모 조각 폰트의 음절.

**상태.** 범용이다.

**입력.** 아무 파일. `compose`에는 명세(아래). 기하 옵션은 `binscan.py`와 같다.

**출력.** `cut`: 그 바이트. `eng`: 4,096 바이트(8x16 글리프 256개. 8xH 폰트는 16행으로 채우고 위에 `--top`행). `bdf`, `compose`:
`CHARSET_REGISTRY "ISO10646"`, `CHARSET_ENCODING "1"`, `PIXEL_SIZE` = 글리프 높이, `FONT_ASCENT` = `--ascent`(기본은 높이의 7/8,
올림)인 BDF. 모든 글리프가 셀 전체이며, 빈 KS 글리프는 뺀다.

**개요(Synopsis).**

    python3 tools/rawcarve.py cut FILE --offset O --length N -o OUT
    python3 tools/rawcarve.py eng FILE --offset O [--height H] [--top T] -o OUT
    python3 tools/rawcarve.py bdf FILE [--offset O] --glyph WxH --chars ascii|ks-hangul|ks-nonhanja|ks-all \
        [--first C] [--count N] [--dense | --grid L0,T0,PITCH] [--ascent A] -o OUT.bdf
    python3 tools/rawcarve.py compose FILE --spec SPEC.json [--syllables ks|all] \
        [--eng FILE2 --eng-offset O --eng-height H --eng-top T] [--ascent A] -o OUT.bdf

`bdf --chars ks-*`는 각 KS X 1001 코드를 `--dense`(글리프 i = 그 집합의 i번째 코드: 2,350 음절 덤프) 또는 `--grid L0,T0,PITCH`(글리프 =
(lead - L0) x PITCH + (trail - T0): 전체 표는 `0xA1,0xA1,94`, 한글 VGA ROM은 `0x80,0x80,128`)로 놓는다(lead가 L0보다 작거나 trail이 T0 .. T0 + PITCH - 1 밖인 코드는 거부한다). 음수 오프셋,
1보다 작은 `--length` / `--stride` / `--count`, 음수 `--first`, 16행을 넘는 `--top` + `--height`는 거부한다. `cut`, `eng`, `bdf`는
쓰는 바이트만 읽고(글리프보다 짧은 `--stride`여도 마지막 글리프의 전체 범위까지), `compose`는 파일 전체(64 MiB까지)를 읽는다. 1..256 밖의 셀, 음수 조각, 없는 세트, 셀을 넘는 `--eng-top` +
`--eng-height`인 compose 명세는 메시지와 함께 거부한다. compose 명세는 조각 세트(`offset`,
`stride`, 저장된 조각이 셀의 어디로 가는지: `x`, `y`, `width`, `height`, `order`), 종성 없을 때와 있을 때 모음별 초성 세트, 모음별 중성
(세트, 조각)(ㄱ / ㅋ용 다른 표를 둘 수 있다: 8x4x4 규칙), 모음별 종성 세트 또는 세트 하나, 그리고 폰트 자신의 모음 순서를 적는다.
자모 번호는 유니코드의 번호다(형식은 모듈 docstring). 잘못된 오프셋, 명세, 빈 결과에는 메시지와 함께 종료 코드 1.

**import하는 저장소 모듈.** `binscan.py`. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(잘라 낸 8x4x4 폰트가 `jamoset.py`로
빌드된다. KS 격자 ROM. 8x4x4 규칙의 compose 명세가 jamoset의 조합과 같다).

### `tools/os2dbcs.py`

**목적.** OS/2 "System DBCS" 폰트(`$korZN16.FNT`, `$korZN24.FNT`. 일본어와 중국어 것도 같은 형식)를 글리프 표로 푼다.

**상태.** 범용이다. 형식은 바이트와 OS/2의 16비트 FNTCALLS.DLL에서 읽었다. 노트는 johab-fonts 연구에 있다.

**입력.** System DBCS 파일(헤더 "System DBCS NN"): 0x1A00부터 512 바이트 블록의 레코드. 각 레코드는 허프만 부호의 니블 열이며,
위 두 행의 문맥 표를 거쳐 되돌린다. 레코드는 블록을 넘지 않고 블록의 나머지는 0xFF 채움(글리프 번호 0xFFFF)이다. 헤더는 처음 0x1A00
바이트로 먼저 확인하고 나머지를 읽는다(16 MiB를 넘는 파일은 거부). 메시지와 함께 거부: 표보다 짧은 파일, 1..64 밖의 셀이나
ceil(w / 8) x h가 아닌 글리프당 바이트, 블록이나 파일을 넘는 레코드, 순서가 틀린 글리프 번호, 레코드 페이로드를 넘거나 마지막 바이트
전에 끝나는 부호(데이터와 맞지 않는 레코드 길이: OS/2 Warp 4 두 폰트의 모든 레코드 길이는 맞는다), 블록의 채움 표시 뒤의 0xFF 아닌
바이트나 블록 끝에서 잘린 레코드 헤더. 어떤 유효한 부호 열과 우연히 맞는 손상된 길이는 진짜와 가려낼 수 없다.

**출력.** `info`: 헤더(셀, 글리프당 바이트, 리드 바이트, 글리프 번호 범위, 레코드, 있는 음절). `table`: 글리프 번호 256..8997 전부를 차례로
(슬롯 8,742개, 없는 것은 빈 칸), 행 우선: A1A1부터의 KS X 1001 94 x 94 표로, `rawcarve.py bdf --grid 0xA1,0xA1,94`용.

**개요(Synopsis).** `python3 tools/os2dbcs.py info FILE`, `python3 tools/os2dbcs.py table FILE -o OUT.bin`. 헤더가 없는 파일에는
메시지와 함께 종료 코드 1.

**import하는 저장소 모듈.** 없음. **서드파티.** 없음. **테스트.** `tools/test_extract.py`(자체 부호표를 가진 합성 폰트: 이스케이프 부호 니블, 항등이 아닌 문맥 표, 여러 블록에 걸친 드문 글리프 번호, 잘못된 파일의 거부.
`JOHAB_FONTS`가 연구 트리를 가리키면 풀어 낸 진짜 `$korZN16.FNT`와 가, 각, 힝의 해시, 그리고 그 노트의 렌더와 가 / 힝 비교).

## 레거시 포맷 리더

### `tools/macfbit3.py`

**목적.** HangulTalk 7.1.x(1992)의 자모 plane 비트맵 폰트(Seoul12, AppleGothic12, AppleMyungjo12와
24 px의 AppleGothic24 / AppleMyungjo24)를 7.1.2 설치 프로그램의 'splt' "JM" 아카이브 또는 설치된
리소스 포크에서 읽고, 그 KS X 1001 음절을 합성하며, 시트와 `bdfface.py`가 받는 BDF를 쓴다.

**상태.** 연구용 리더. 폰트는 Apple/Elex의 독점이다. 이 도구는 사용자 자신의 사본을 읽으며 그것에서 나온 페이스나
비트맵은 이 저장소에 없다.

**입력.** JM 아카이브(`<Font>[splt]`의 데이터 포크), 리소스 포크, 또는 원시 'fbit' 리소스. 합성에는
7.1.2 CD의 InputBackSupport 리소스 포크(그 'HTBL' 1. 거기서는 압축되지 않음) 또는 원시 HTBL 1이 쓰인다.
포맷은 모듈 docstring에 있다. JM = 0x1e에서 시작하는 LHA -lh5-(ar002) 스트림과 바이트 합 체크섬. fbit type 3 =
0x54부터 시작하는 482개의 h x h plane(2 bank x 241). HTBL 1 = 코드마다 4바이트 항목 하나 [bank][g1][g2][g3], plane들을 OR한다.
복원할 규칙은 없다. 표 자체가 합성이며, 2,350개 KS 음절과 51개 호환 자모
(A4A1..A4D3)만 존재한다.

**출력.** `unpack`: 풀어낸 리소스 포크. `fbit`: 'fbit' 리소스. `info`: 한 줄(type, 셀, plane
개수, 합성 가능한 코드). `sheets`: 회색조 PNG 넷, `PREFIX_glyphs_x1/_x4.png`(모든 plane, 한 줄에 32개)와
`PREFIX_ks2350_x1/_x4.png`(합성된 2,350개 음절, 한 줄에 94 / 47개). `bdf`: 글리프 2,401개, h x h 셀,
`CHARSET_REGISTRY "ISO10646"`, 유니코드 `ENCODING`, `STARTCHAR KS<code>`.

**개요(Synopsis).**

    python3 tools/macfbit3.py unpack SPLT.data OUT
    python3 tools/macfbit3.py fbit SRC OUT
    python3 tools/macfbit3.py info FONT [HTBLSRC]
    python3 tools/macfbit3.py sheets FONT HTBLSRC OUTPREFIX
    python3 tools/macfbit3.py bdf FONT HTBLSRC NAME OUT.bdf

사용자의 7.1.2 CD에서 실행했다(2026-10-26). Seoul12(1,843 B), AppleGothic12(2,707 B), AppleMyungjo12(3,194 B)는 풀면 9,673
/ 9,673 / 9,617 B의 포크가 되고 각각 8,760 B의 fbit(plane 482개, 12 px)을 가진다. Seoul12의 것은 CD의 압축되지 않은
`Seoul12[fbit]`와 바이트 단위로 같다. BDF는 `bdfface.py --cell 12x12 --chars-from <2,350 KS
syllables>`를 거쳐 음절 2,350개, 누락 0, 잘림 0이 된다.

**import하는 저장소 모듈.** 없음. **서드파티.** 없음.
**테스트.** `tools/test_macfbit3.py`(합성 데이터. `MACFBIT3_CD712=<extracted CD tree>`를 주면 CD
파일에 대한 검사가 추가된다).


### `tools/hwpfont.py`

**목적.** DOS용 한글(HWP) 1.x와 3.0의 비트맵 폰트와 헤더 없는 KS X 1001 음절 덤프를 읽는다. 파일이 무엇인지 말하고, HWP 1.x
페이스의 음절을 HWP.EXE의 규칙으로 조합하고, 파일의 글리프를 `mkfont.py`와 `bdfface.py`가 받는 유니코드 BDF로 쓴다.
`jamoset.py --layout hwp1` / `844-hwp3`와 그 HWP `--eng`가 이 도구를 통해 파일을 읽는다.

**상태.** 저장소 도구가 된 연구용 리더. 폰트는 한글과컴퓨터의 것이다(독점). 도구는 사용자 자신의 사본을 읽으며, 실제 파일의
폰트, 글리프, 표는 이 저장소에 없다(규칙인 HWP.EXE의 선택 표는 johab-fonts 연구 노트에서 가져온 데이터로 담는다). 바이트만 읽는다
(`python3 -I`로 실행하라).

**입력.** HWP 1.x `.SFT` / `.PFT`(32 바이트 "HWP Font Editor v1.0" 또는 "FE" 헤더, 크기는 정확히 32 + 글리프 수 x 글리프 바이트.
화면 폰트는 행 우선, 프린터 폰트는 열 우선): `HANGUL.SFT`(16x16, 글리프 1,193개, 조각 31/29/31개짜리 초성/중성/종성 세트가 10/4/4,
7/2/2, 6/2/2인 페이스 셋), `HANGUL1/2/3.PFT`(24x24, 980개; 7/2/3, 7/2/2, 5/2/2), `ASCII.SFT` / `ASCII.PFT`(8x16 / 14x24, 991개:
147개짜리 페이스 여섯), `HANJA.SFT`(4,888개), 기호 파일(`other`). HWP 3.0 `.FNT`(72 바이트 "FNT" 01 헤더: 형식 0 영문, 1 한글,
2 한자. 6과 8에 LE16 폭과 높이. 행 우선 글리프): `HAN*.FNT`는 KS X 1001 음절 2,350자(16 px는 360개짜리 8x4x4 세트 추가),
`ENG*.FNT`는 0x20부터의 코드, `HAJ16_0.FNT`는 한자. 글리프 수는 본문의 것이며, 헤더와 다르면 `info`가 알린다(HAN24는 2,710이라 적고 2,350을, ENG40은
147이라 적고 96을 담는다). 0x20-0x7E의 95자에 못 미치는 영문 FNT는 거부한다. 글리프 순서는 파일 이름이 아니라 높이를 따른다: 24행인
HWP 1.x 폰트는 열 우선이다. KS 원시: 16, 24, 32, 40, 48 px 정사각형 글리프 정확히 2,350개인 헤더 없는 파일
(75,200 / 169,200 / 300,800 / 470,000 / 676,800 바이트)로, 첫 글리프와 마지막 글리프에 잉크가 있고 서로 달라야 한다. 그 밖의 것과
16 MB를 넘는 파일은 거부한다. `--ascii`는 `jamoset.py --eng`가 읽는 어떤 영문 폰트든 받는다.

**출력.** `info`: 한 줄(계열 `HWP 1.x font` / `HWP 3.0 FNT` / `KS X 1001 raw dump`, 종류, 글리프 수와 크기, 페이스들의 세트 수,
HWP 3.0 폰트의 이름, 8x4x4 꼬리). `bdf`: BDF 2.1(`CHARSET_REGISTRY "ISO10646"`, `PIXEL_SIZE` = 셀 높이, `ENCODING` = 코드
포인트, `STARTCHAR U+XXXX`): 한글 파일은 음절(KS X 1001 2,350자. HWP 1.x 페이스는 `--syllables all`로 11,172자 전부), 영문 파일은
U+0020..U+007E(advance = 글리프 폭), 한자 파일은 한자 4,888자. `--ascii`를 주면 그 영문 폰트의 ASCII도 넣는다(셀보다 낮으면 높이
가운데에, 자신의 advance로). ascent는 `--ascent`, 없으면 영문 페이스의 베이스라인(`H` 잉크 아래 행), 그것도 없으면 셀의 7/8이다.
파일에 U+0020이 없으면 빈 U+0020(셀 폭의 절반)을 쓴다. FreeType은 BDF의 첫 글리프를 `.notdef`로 보고 `mkfont.py`는 그것과 같은 글리프를 모두 버리므로, 그러지 않으면 U+AC00이 빠진다.
요약 한 줄(`wrote OUT: 2350 Hangul syllables, 95 ASCII of 14x24 from ASCII.PFT; cell 24x24, ascent 20`).

**개요(Synopsis).**

    python3 -I tools/hwpfont.py info FILE
    python3 -I tools/hwpfont.py bdf FILE [--face N] [--syllables ks|all] [--ascii ENG [--ascii-face N]] [--ascent A] [--name NAME] -o OUT.bdf

`--face`는 HWP 1.x 한글 파일의 페이스(0..2) 또는 HWP 1.x ASCII 파일의 페이스(0..5)이다. 종료 코드 0, 또는 `hwpfont.py: <이유>`와
함께 1(어느 형식도 아님, 헤더와 맞지 않는 크기, 범위를 벗어난 페이스, 쓸 것이 없는 파일).

라이브러리로: `read(data)`(`Font`: `family`, `kind`, `w`, `h`, `count`, 행 정수로 된 `glyph(i)`, `jamo844`, `table`),
`Hwp1Hangul(font, face)`(`pieces(cp)`, `syllable(cp)`, 그리고 JSET 세트 함수로 쓴 규칙 `lead_class`, `init_set`, `med_set`,
`fin_set`, `init_src`, `med_src`, `fin_src`), `syllables`, `ascii_glyphs`, `hanja_glyphs`, `english(path)`, `ks_hangul()`,
`ks_hanja()`, `ks_raw_px(size)`.

사용자의 HWP 1.20, HWP 3.0, 태백 3.5.1 파일로 실행했다(2026-11-23. 수치는 recipes.ko.md의 "HWP 1.x와 2.x 폰트", "HWP 3.0 FNT 폰트",
"KS X 1001 원시 덤프"): 손에 있는 HWP 1.x 한글 파일 일곱 개의 음절 11,172자는 각 페이스 셋 모두 연구 렌더러(johab-fonts 노트의
`hwp1_fnt.py`)의 것과 같다.

**import하는 저장소 모듈.** `rawcarve.py`(`bdf_text`), `jamoset.py`(`--ascii`의 `read_eng`). **서드파티.** 없음. **테스트.**
`tools/test_hwpfont.py`(합성 파일. `JOHAB_FONTS=<연구 트리>`이면 실제 HWP 1.20, HWP 3.0, 태백 파일의 해시 검사가 더해진다).

### `tools/macsfnt.py`

**목적.** Mac 형식 TrueType을 다른 도구들이 쓸 수 있게 한다. 리소스 포크(.dfont, suitcase의 포크, AppleDouble `._` 파일, MacBinary)의 'sfnt' 리소스를 나열하고 추출하며, 폰트의 cmap 서브테이블을 보고하고, Mac Korean(platform 1, script 3) 또는 Windows Wansung(3, 5) cmap만 있는
폰트에 유니코드 cmap을 추가한다.

**상태.** 범용이다. 사용자 자신의 파일을 읽으며, 이 저장소에는 Mac 폰트가 없다.

**입력.** 일반 파일로서의 리소스 포크(또는 AppleDouble / MacBinary로 감싼 것). `cmap`과 `unicode`에는 sfnt 폰트.

**출력.** `list`: 폰트 리소스당 한 줄(`TYPE<TAB>ID<TAB>NAME<TAB>BYTES`, 타입 sfnt, NFNT, FONT, FOND, fbit).
`extract`: .ttf로서의 'sfnt' 리소스. `cmap`: 서브테이블 하나당 `platform=P encoding=E format=F entries=N hangul=H`.
`unicode`: 각 두 바이트 코드를 EUC-KR(KS X 1001)로 디코딩해 만든 (3,1) format 4 서브테이블(코드 포인트가 U+FFFF를 넘으면 (3,10) format 12도)을 가진 폰트의 사본.
폰트에 이미 유니코드 서브테이블이 있으면 거부된다.

**개요(Synopsis).**

    python3 tools/macsfnt.py list FILE
    python3 tools/macsfnt.py extract FILE OUT.ttf [--id N]
    python3 tools/macsfnt.py cmap FONT
    python3 tools/macsfnt.py unicode FONT OUT.ttf

종료 코드 0, 또는 메시지와 함께 1(리소스 포크가 아님, 'sfnt' 리소스 없음, 한국어 cmap 없음, 유니코드 cmap이 이미 있음).

**import하는 저장소 모듈.** 없음. **서드파티.** fontTools(`cmap`, `unicode`). **테스트.** `tools/test_macsfnt.py`
(Mac Korean cmap을 가진 합성 폰트와 테스트에서 만든 리소스 포크. fontTools 자체의
리소스 리더와도 대조했다).

## 레시피: 입력 포맷에서 SVF로

모든 입력 포맷(TTF, OTF, TTC, 가변 폰트, Mac 폰트, BDF, PCF, FNT, HBF, DOS 원시 폰트, 클래식 Mac 폰트, 기존 SVF)에서 SVF로 가는 레시피와,
그것을 다시 실행해 얻은 수치와, maker의 경로 표는 이제 한 장에 있다: [recipes.ko.md](recipes.ko.md). 입력 종류별 빠른 시작 표로
시작한다. 이 절은 포인터로 남겨 둔다.

## 도구에 남은 빈틈

도구 자체가 아직 하지 못하는 것. maker(`maker/`, `maker/README.md`)는 이 중 일부를 우회한다(`detect.py`가 파일의 포맷, 패밀리, 스타일, 크기,
커버리지를 알려 주고, 경로는 [recipes.ko.md](recipes.ko.md#데스크톱-앱과-maker-경로)에 표로 있다). 나머지는 누가 호출하든 도구에 대해 참이다.

- **문자 집합이 필요하다.** `mkfont.py`에는 더 이상 코드 페이지(버전 1) 순서가 없다. `--unicode`나
  `--chars-from` 없이는 종료 코드 2로 끝난다(`mkfont: version 1 (code page order) is gone: pass --unicode SET`).
- **고정 폭 페이스가 없다.** `mkfont.py`는 항상 메트릭 표를 쓴다. `--fixed`, `--center`, `--variable`은 없어졌다.
- **모드에 따라 달라지는 jamoset 옵션.** `--embolden`, `--symbols`, `--ascent`, `--eng`, `--base`는 일부
  `jamoset.py` 모드에서 무시된다(Modes 열 참고). 잘못된 모드에 연결된 토글은 조용히 아무 일도 하지 않는다.
- **실행 시간.** 16 px 아웃라인 페이스에서 2 bpp 자모 세트는 이 호스트에서 약 73초, 1 bpp `threshold` 맞춤은 약 12초가 걸렸으며
  (2026-11-22), 웹 요청은 이를 감안해야 한다.
- **한국어 stdout.** `mkfont.py`는 요약을 한국어로 출력하므로 래퍼는 필드 이름을 찾으려고 그 stdout을 파싱해서는 안 된다.
- **기본 `--binarize mono`는 freetype-py가 필요하다(`--mask-font`는 uharfbuzz도).** 이 호스트에는 둘 다 없으며
  (`cannot import freetype`), 그래서 레시피가 `--binarize threshold`를 쓴다. 호출자는 이를 동봉하거나 threshold 경로를 택해야 한다.
  둘 다 스크래치 폴더에 설치해 실행할 수 있다(`pip install --target $OUT/pylib freetype-py uharfbuzz`(`$OUT`은 recipes.ko.md의 것), 그다음 `--pylib $OUT/pylib`). 마스크 맞춤과 `mono` 맞춤을
  2026-11-22에 그렇게 실행했다(recipes.ko.md, 2번 방법).
- **비트맵 폰트는 스트라이크 크기에서만 열린다.** PCF나 BDF는 파일에 내장된 픽셀 크기에서만 열리고 다른 크기에서는 열리지 않는다
  (`OSError: invalid pixel size`). 도구는 스트라이크를 나열하지 않는다(maker의 `detect.bitmap_strikes`는 나열한다).
- **Windows `.FNT` / `.FON`은 아무것도 그리지 못한다.** FreeType은 이를 열지만 `FT_ENCODING_NONE` 맵만 주므로, Windows 95 한글판 FON에서
  `mkfont.py`는 "`--unicode`의 글자가 글꼴에 하나도 없다"로 끝나고, maker는 이들에 경로를 주지 않는다("no Unicode character map, mkfont
  cannot read it"). 한글 글리프가 있는 FNT나 FON도 찾지 못했다(recipes.ko.md, Windows FNT와 FON).
- **HWP 2.x / 3.0 `.HFT` 폰트의 리더가 없다**(비트맵이 아니라 크기 조절이 되는 윤곽선 또는 획 폰트). HWP 1.x `.SFT` / `.PFT`,
  HWP 3.0 `.FNT`, 16-48 px의 헤더 없는 KS X 1001 음절 덤프는 `hwpfont.py`가 읽는다(`jamoset.py --layout hwp1` / `844-hwp3`). KS 코드
  격자, 다른 크기이거나 더 큰 파일 안에 든 덤프, 프로그램과 ROM 안의 폰트는 `rawcarve.py`가 BDF로 잘라 낸다(이를 바로 읽는 빌더는
  없다). `jamoset.py`의 어느 배치도 아닌 자모 조각 폰트는 그 규칙을 `rawcarve.py compose` 명세로 적어야 한다. `--eng`는 8x16,
  12x24, 20x40, 24x48 영문 폰트와 HWP 영문 폰트를 받는다. HWP 1.x 기호 파일과 한자 파일은 페이스로 가는 경로가 없다(`hwpfont.py
  bdf`가 한자를 BDF로 쓴다).
- **같은 크기에서 1 bpp를 안티에일리어싱으로 바꾸는 변환이 없다.** 1 bpp 페이스에서 같은 크기의 2 bpp 페이스를 만드는 도구가 없다.
  `svfscale.py --bpp 2`는 더 큰 비트맵 페이스에서 만들고(박스 필터), 다른 2 bpp 페이스는 아웃라인 폰트에서 나온다(`mkfont.py --bpp 2`,
  `jamoset.py --bpp 2`, `jamovec.py render --bpp 2`). 비트맵 원본에서 2 bpp 자모 세트로 가는 길은 없다: `jamoset.py --bpp 2`는
  `--from-svf`를 거부한다(`--bpp 2 works from an outline font (--from-ttf)`).
- **규칙 없는 PUA 자모 조각.** 사용 영역(PUA)에 자모 조각을 두되 합성 음절도 GSUB 룩업도 그것에 닿지 않는 폰트(MiraeroNormal의 PUA
  글리프 2,544개)는 리더가 없다. 음절마다 조각 세트를 고르는 규칙이 폰트에 없다(recipes.ko.md, 이미 자모를 가진 TrueType 폰트).
- **임의의 폰트에 대한 메타데이터와 커버리지 보고가 없다.** 입력 폰트의 패밀리나 스타일, 사용 가능한 크기, 11,172개 음절(또는 2,350개
  KS X 1001 음절) 중 몇 개를 덮는지 출력하는 도구가 없다. `mkfont.py`는 버린 코드 포인트를 세고, `web/mkindex.py`는 구워진 페이스의
  커버리지를 보고한다.
- **설계 품질의 셀 크기가 없다.** `mkfont.py --probe`는 한 크기에서 아무것도 자르지 않는 키 큰 셀로 bake하고(셀과 ascent는 잉크 상자에서
  나온다), `--fit-cell`은 호출자가 준 셀에 맞도록 크기를 줄인다. 대상(게임의 줄 간격, 디스플레이)이 원하는 셀을 고르는 것은 없다.
- **라이브러리 API가 없다.** 굽기는 경로에 쓰는 명령줄 프로그램이며, 반환값이 있는 호출로 노출하는 것은 없다(maker는 이를 하위
  프로세스로 실행한다. `maker/toolrun.py`).
