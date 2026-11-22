[English](NOTICE.md) | **한국어**

# 고지: 이 저장소의 라이선스

이 저장소를 위해 작성한 코드, 형식 명세, 문서(`c/`, `tools/`, `maker/`, `web/`,
`spec/`, `docs/`, 페이스 곁의 노트)는 [LICENSE](LICENSE)의 MIT 라이선스를 따르며, 저작권자는 Taehyun Kim이다.

폰트와 그로부터 만든 페이스(face)는 해당 라이선스의 적용 대상이 **아니다**. 이 저장소의 모든 폰트와 페이스는
**SIL Open Font License 1.1**을 따르며, 그 라이선스 본문이 곁에 있다. `svf/`의 페이스는 원본 폰트의 수정 버전(Modified Version)이다
(래스터화, 서브셋, 또는 자모 조각으로 분할). `web/LICENCES.tsv`는 모든 페이스를 그 라이선스 파일에 연결하며
(페이스에 라이선스가 없으면 `tools/test_web_picker.py`가 실패한다), `tools/build/faces.tsv`와 [docs/recipes.ko.md](docs/recipes.ko.md)는
각 페이스를 상류(upstream) 폰트로부터 어떻게 만드는지 설명한다.

## 페이스 (`svf/`)

| 페이스 | 원본 폰트 | 저작권 | 라이선스 파일 |
|---|---|---|---|
| `svf/dos/BHSAN28` | Black Han Sans | 2015 The Black Han Sans Project Authors | `svf/dos/OFLBHS.TXT` |
| `svf/dos/COUSB24` | Coustard | 2011 The Coustard Project Authors | `svf/dos/OFLCOUS.TXT` |
| `svf/dos/DIPHY36` | Diphylleia | 2022 The Diphylleia Project Authors | `svf/dos/OFLDIPHY.TXT`, `DIPHY.TXT` |
| `svf/dos/GBATB*`, `GBA*X?` | Gowun Batang Bold | 2021 The Gowun Batang Project Authors | `svf/dos/OFLGOWUN.TXT`, `GOWUNBAT.TXT` |
| `svf/dos/GOTHB18A`, `svf/jamo-extra/GOTHA*`, `GOTHB*` | Gothic A1 | HanYang I&C Co., Ltd. | `OFLGOTHA.TXT` (두 폴더 모두) |
| `svf/dos/MARU*` | MaruBuri | NAVER Corp., NAVER Cultural Foundation | `svf/dos/OFLMARU.TXT`, `PAPMARU.TXT` |
| `svf/dos/NEODG*`, `NEO*X?` | Neo Dunggeunmo 1.601 | 2017-2021 Eunbin Jeong (Dalgona.) | `svf/dos/OFL.TXT`, `NEODGM.TXT` |
| `svf/jamo-extra/NDGPR*` | Neo Dunggeunmo Pro 1.020 | Dalgona (original Dunggeunmo by Jungtae Kim, public domain) | `svf/jamo-extra/OFLNDGPR.TXT` |
| `svf/dos/NGOT*`, `NGO*X?` | NanumGothic Bold | 2010 NHN Corporation | `svf/dos/OFLNANUM.TXT`, `NANUMGOT.TXT` |
| `svf/dos/NSQR*`, `svf/jamo-extra/NSQR*` | NanumSquareRound | 2017 NAVER Corporation | `OFLNSQR.TXT` (두 폴더 모두) |
| `svf/dos/PAPLG*`, `PAPER*`, `PAPLB*` | Paperlogy | 2024 PT& (designptn.com) | `svf/dos/OFLPAPLG.TXT`, `PAPLG.TXT`, `PAPMARU.TXT` |
| `svf/jamo-extra/SGDAY*` | Single Day | 2015 DXKorea Inc. | `svf/jamo-extra/OFLSGDAY.TXT` |

## TrueType 원본 (`ttf/`)

수정하지 않은 상류 파일(가변 폰트 두 개는 이름을 바꿨으며 `ttf/FONTS.md` 참조)이며, 각각 라이선스 본문이 곁에 있다.

| 폴더 | 폰트 | 저작권 | 라이선스 |
|---|---|---|---|
| `ttf/blackhansans` | Black Han Sans | 2015 The Black Han Sans Project Authors | SIL OFL 1.1 |
| `ttf/caveat` | Caveat | 2014 The Caveat Project Authors | SIL OFL 1.1 |
| `ttf/coustard` | Coustard | 2011 The Coustard Project Authors | SIL OFL 1.1 |
| `ttf/ebgaramond` | EB Garamond | 2017 The EB Garamond Project Authors | SIL OFL 1.1 |
| `ttf/galmuri` | Galmuri | 2019-2025 Lee Minseo | SIL OFL 1.1 |
| `ttf/gowunbatang` | Gowun Batang | 2021 The Gowun Batang Project Authors | SIL OFL 1.1 |
| `ttf/nanumgothic`, `ttf/nanummyeongjo`, `ttf/nanumpenscript` | NanumGothic, NanumMyeongjo, Nanum Pen Script | 2010 NHN Corporation | SIL OFL 1.1 |
| `ttf/neodgm` | Neo Dunggeunmo | 2017-2021 Eunbin Jeong (Dalgona.) | SIL OFL 1.1 |

## Reserved Font Names: 이 저장소가 OFL을 읽는 방식

원본 폰트 두 계열이 Reserved Font Name을 선언한다. NanumGothic / NanumMyeongjo / Nanum Pen Script("Nanum", "Naver Nanum",
"NanumGothic", "NanumMyeongjo", ...)와 Neo Dunggeunmo("Neo둥근모", "Neo둥근모 Code", "NeoDunggeunmo",
"NeoDunggeunmo Code")이다. OFL 조건 3은 어떤 수정 버전도 Reserved Font Name을 사용해서는 안 된다고 말한다. OFL은
Font Name을 폰트 소프트웨어에 대해 선언된 이름, 즉 폰트가 스스로의 것으로 내세우는 이름(name 테이블,
설치되거나 선택되는 이름)으로 정의한다. 이를 다음과 같이 읽는다:

- `svf/`의 페이스는 수정 버전이다. 안에 폰트 이름을 담고 있지 않으며(SVFN 형식에는 이름 필드가 없다),
  파일 이름(`NGOTB16.SVF`, `NEODG16G.SVF`)은 약어이지 예약된 이름이 아니다. 곁에 있는 라이선스 노트도
  이를 밝힌다.
- `web/FAMILIES.tsv`는 각 페이스에 **원본** 폰트의 패밀리를 부여하고, WASM 선택기는 이를 라이선스 노트와 함께
  행 레이블로 보여 준다. 페이스의 출처에 대한 표시(attribution)이다(OFL 조건 2는 저작권 고지가 폰트와 함께 따라가도록 하고,
  조건 4는 저작자의 이름으로 그 기여를 밝히는 것을 허용한다). 페이스를 원래의
  폰트인 것처럼 내세우지 않는다. 이렇게 읽으면 레이블은 그대로 둘 수 있다.

공개하기 전에 소유자가 확인할 사항이다. 레이블이 예약된 이름을 전혀 보여 주지 않아야 한다면,
`NGOT*`, `NGO*X?`, `NEODG*`, `NEO*X?` 페이스에 대한 `web/FAMILIES.tsv`의 `family` 열이 바꿀 유일한 곳이다
(예: "Nanum-derived Gothic", "Dunggeunmo-derived pixel"). 선택기 테스트는 고정된 이름이 아니라 표를 읽으며,
기본 행으로 "NanumGothic Bold"를 지목하는 몇 개만 예외이다.

## 확인한 상류 라이선스 기록

`ttf/`의 모든 TrueType 파일은 name 테이블(ID 13)에 SIL OFL 1.1을 선언하지만, NanumGothic과
NanumMyeongjo 파일은 name 테이블에 "NHN Corporation"만 적혀 있다. 이들의 `OFL.txt`는 배포처
(Google Fonts)에서 온 것이며 NAVER는 Nanum 폰트를 SIL OFL 1.1로 배포한다. NanumSquareRound 페이스는 같은
NAVER 배포에 근거한다(폰트 파일에는 저작권 줄만 있으며 `OFLNSQR.TXT`가 그렇게 밝힌다). Neo Dunggeunmo Pro와
Paperlogy는 폰트 파일에 OFL을 명시한다. 페이스 여섯 개(`NGOTB17`, `NGO17X1`, `NGO17X2`, 그리고
`NGO15X2`, `NGO16BX2`, `NGO21AX2`의 대체 glyph)는 NHN의 힌팅된 NanumGothicBold.ttf(Debian `fonts-nanum`, SIL OFL
1.1)로 그렸으며, 이 파일은 이 저장소에 없다.

## 데스크톱 패키지

데스크톱 패키지는 Electron/Chromium, CPython, Pillow, fontTools와 이들이 필요로 하는 공유 라이브러리를 번들한다. 그 라이선스는
패키지의 THIRD-PARTY.txt에 나열된다(`desktop/build/third-party.mjs`가 번들로부터 생성하며,
출처 표시가 없는 라이브러리와 GPL 라이브러리가 있으면 실패한다). `svf/`에 없는 폰트는 포함하지 않는다.

## 독점 형식 변환기

일부 도구는 상용 시스템의 폰트 형식을 읽는다. `tools/macfbit3.py`와 `tools/macfbit_svf.py`(클래식 Mac
HangulTalk 'fbit' 폰트), `jamoset.py --layout mac-fbit-45sets`(HangulTalk 1.0), `tools/macsfnt.py`(Mac
리소스 포크와 .dfont 파일 안의 TrueType, Mac 한글 cmap), 그리고 `jamoset.py`와 `johab844.py`의 DOS / X11 원시
레이아웃이다. 이들은 자체 작성한 코드이며 **사용자가 제공한** 폰트 파일만 읽는다. 그런 폰트, 그런 폰트에서 가져온
비트맵, 그런 폰트에서 파생한 골든 데이터는 여기에 배포하지 않는다. 테스트는 테스트 안에서 만든 합성 픽스처를 사용하며,
실제 파일에 대한 검사는 환경 변수가 사용자 본인의 사본을 가리킬 때만 실행된다.

maker(`maker/`)에는 이런 폰트를 위한 로컬 모드가 있다. 데스크톱 앱이 사용자가 고른 파일이나 폴더의 경로와 출력 폴더를 이 모드에 넘기고,
폰트는 제자리에서 읽어 변환하며, 페이스는 그 폴더에만 쓴다. 이 모드에서는 아무것도 업로드하지 않고, maker의 데이터 디렉터리로
아무것도 복사하지 않으며, zip도 만들지 않고, 변환 도중 필요한 파일은 출력 폴더 안에 두었다가 작업이 끝나면 지운다.
maker에는 자신의 로컬 페이지(127.0.0.1) 외에는 어디에도 연결하는 코드가 없다(테스트는 그 임포트와 자체 소켓을 검사한다. docs/maker-audit.md 8절은 테스트가 다루지 않는 것을 설명한다). 독점 폰트, 비트맵, 테이블은 이
저장소에 없다. 로컬 모드 테스트는 테스트 안에서 합성 입력을 만들며, 실제 파일에 대한 검사는 환경
변수가 사용자 본인의 사본을 가리키는 곳에서만 실행된다. 폰트를 변환할 권리가 있는지는 사용자 본인의 책임이다
(로컬 모드의 maker는 라이선스를 검사하지 않고 확인(acknowledgement)을 요청한다). 결과를 공개하는 사람은
폰트의 라이선스를 확인해야 한다.

## 이 저장소에서 제외한 것

이 저장소는 비공개 작업 저장소를 선별해 복사한 것이다. 의도적으로 제외한 것: 원본 라이선스가
명시되지 않았거나 SIL OFL 1.1이 아닌 페이스(DOS, Mac, HWP, 프린터 비트맵 폰트, iolo 컬렉션, san 1.0 페이스,
한 게임 자체의 페이스)와 그런 페이스의 보충분. 또한 TrueType 후보(하나는 다른 라이선스의 폰트를 번들하고,
나머지는 라이선스 기록이 없다), Apple 데이터에서 파생한 Arduino Uno 프리셋, ScummVM `fonts-cjk.dat` 빌더와
파일, 게임별 bake 스크립트, 계획, 맵 작성기이다.
