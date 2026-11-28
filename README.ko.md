[English](README.md) | **한국어**

# svf-fonts

비트맵 폰트 환경이다. SVF(SVFN) 형식, 그 형식으로 만든 폰트, 그리고 폰트를 만들고 검사하는 도구로 이루어진다.
ScummVM 한글 고해상도 텍스트 작업의 폰트 쪽에서 출발했으며, ScummVM은 이것의 사용자 중 하나(git 서브모듈로 사용)이다.
임베디드 대상(ESP32, Raspberry Pi Pico, Arduino)처럼 다른 사용자도 염두에 두고 있다. 이런 대상에서는 자모 세트(jamo-set) 페이스(face)가
작은 조각 묶음으로 한글 음절 11,172자를 모두 그린다(Arduino Uno 예제의 페이스인 `svf/dos/NEODG16G.SVF`는 `mcu-strict` 레이아웃에서 10,124 B이다. `c/cross/SIZES.md` 참조).
개발 상태: [docs/STATUS.md](docs/STATUS.md).

## 1. 라이선스

코드, 명세, 문서는 MIT이다([LICENSE](LICENSE)). 폰트와 그로부터 만든 페이스는
모두 SIL Open Font License 1.1을 따르며, 각각 라이선스 본문이 곁에 있다. [NOTICE.ko.md](NOTICE.ko.md)가 이들의 목록과
이 저장소가 Reserved Font Name을 어떻게 해석하는지를 설명한다. 레시피 색인 [docs/recipes.ko.md](docs/recipes.ko.md)와 [docs/recipes/](docs/recipes.ko.md#레시피-문서)의 주제별 문서는 모든 페이스를 상류(upstream)
폰트로부터 어떻게 만드는지, 그리고 다른 종류의 한글 폰트(TrueType/OpenType 아웃라인, X11 BDF/PCF, DOS johab, 클래식
Mac)를 SVF로 변환하는 방법을 입력 종류별 레시피 장으로 설명한다.

## 2. 문서

### 2.1. 먼저 읽기

- [상태](docs/STATUS.md) — 개발 상태, 연표와 알려진 공백.
- [명세](spec/SVF.ko.md) — SVFN v3 파일 형식과 리더 계약.

### 2.2. 폰트와 형식

- [조합형과 자모 세트](docs/jamo-sets.ko.md) — 한글 인코딩, 세트 선택 규칙과 SVF JSET 예.
- [자모 분리](docs/jamo-split.ko.md) — 완성형 글꼴에서 자모 세트 만들기: 맞춤, 경우별 처리, 잘 맞지 않는 것, 앞선 시도에서 배운 점.
- [자모 분리 실습 가이드](docs/jamo-split-guide.ko.md) — OFL 폰트 3종으로 따라 하는 자모 분리 명령, 측정 결과와 조각 비교.
- [안티앨리어싱](docs/anti-aliasing.ko.md) — 커버리지와 회색 단계, 1/2/8 bpp, 타깃별 단계-색 변환, AA 페이스 만들기, bpp 고르기.

### 2.3. 도구와 레시피

- [도구](docs/tools.ko.md) — 폰트 변환·검사 명령어.
- [레시피](docs/recipes.ko.md) — 아웃라인, 비트맵, DOS, ROM/MAME, OS/2, HWP, TTF 자모와 기존 SVF 변환 절차.

### 2.4. C 렌더러와 응용 프로그램

- [C 렌더러 가이드](docs/c-renderer-guide.ko.md) — 통합, 타깃, 메모리와 한글 렌더링.
- [데스크톱 앱](docs/desktop-app.ko.md) — SVF maker 데스크톱 앱의 빌드와 사용법.
- [Maker 데스크톱](docs/maker-desktop.ko.md) — 데스크톱 maker 구현과 패키징.
- [렌더러 설계](spec/renderer-design.ko.md) — 구조와 그리기 계약.
- [웹 렌더러 가이드](docs/web-renderer-guide.ko.md) — WASM·Canvas 통합.
- [Maker 기능 점검](docs/maker-audit.ko.md) — 입력·경로·설정과 검증 경계.

## 3. 페이스 관리

- 배포 페이스를 변경할 때는 생성 레시피와 검사 기준선도 함께 갱신한다.
- 변환 도구의 출력 경로를 명시하고, 생성한 페이스와 라이선스를 함께 보관한다.
- 모든 페이스는 자신의 라이선스 본문과 함께 배포된다.

## 4. 구성

| 경로 | 내용 |
| --- | --- |
| [spec/SVF.ko.md](spec/SVF.ko.md) | SVFN v3 형식(헤더, 레이아웃 바이트, 테이블, 글리프 레코드, 프로파일, 자모 세트 JSET v1/v2, BIG, JMAP과 LIST, 글리프별 dy. v1과 v2는 폐기) |
| `docs/STATUS.md` | 개발 상태: 구성 요소, 구현 이력, 기능·크기·속도, 한계와 검사 |
| `docs/tools.ko.md` | 모든 도구: 목적, 입력, 출력, 옵션, 그리고 남은 빈틈. 레시피는 `docs/recipes.ko.md`와 `docs/recipes/`에 있다 |
| [docs/desktop-app.ko.md](docs/desktop-app.ko.md) | SVF maker 데스크톱 앱: 빠른 시작(체크아웃에서 빌드, 첫 변환), 사용법, 메시지, 복구와 제거, 프라이버시와 보안, 한계 |
| [docs/c-renderer-guide.ko.md](docs/c-renderer-guide.ko.md) | C 렌더러 통합 가이드: 빌드, 페이스 열기, 줄 그리기, 타깃, 스케일, 한글, 메모리, 문제 해결 |
| [docs/web-renderer-guide.ko.md](docs/web-renderer-guide.ko.md) | 웹 렌더러 사용법: emsdk 빌드, WASM 로딩, 캔버스·Node 예제, 색상, 측정, 메모리, picker API |
| `docs/jamo-sets.ko.md` | 조합형 해설: 문자 집합, 글꼴 기법과 벌 체계(8x4x4 등), SVF의 JSET v1/v2/BIG/JMAP/LIST와 실제 페이스로 따라가는 예, MCU에서의 제약 |
| `docs/jamo-split.ko.md` | 자모 분리: 완성형 글꼴에 자모 세트 맞추기(레이아웃, 1 bpp와 2 bpp 맞춤, 벡터 맞춤, 맥의 나머지 이전, LIST), 원본 종류별 결과, 수치로 적은 약점, 시도의 역사, 결정 흐름(그림은 `tools/doc_figures_split.py`) |
| `docs/jamo-split-guide.ko.md` | 자모 분리 실습 가이드: OFL 폰트 3종(Neo둥근모 16, 나눔고딕 12/16 px, Galmuri11 12 px)으로 따라 하는 명령, 측정 표, 샘플 그림과 조각 분해(그림은 `tools/doc_figures_jamoguide.py`) |
| `docs/anti-aliasing.ko.md` | 안티앨리어싱: 커버리지, 감마, 서브픽셀 렌더링을 하지 않는 이유, 1/2/8 bpp와 2 bpp 단계, 타깃별 단계-색 변환 규칙, 2 bpp 자모 세트의 최댓값(OR가 아님), 윤곽과 축소로 AA 페이스 만들기, 메모리·속도·bpp 선택(그림은 `tools/doc_figures_aa.py`) |
| `docs/recipes.ko.md` | 레시피 색인: 입력 종류별 빠른 시작(아웃라인, 비트맵, DOS 원시, ROM, 클래식 Mac, 기존 SVF), 페이스 점검, KS X 1001과 인코딩 참고, 레시피 문서 목록 |
| `docs/recipes/` | 입력 종류마다 레시피 문서 하나(아웃라인 폰트, 비트맵 폰트, DOS 시대 폰트, 프로그램 안의 폰트, 86Box / MSX / MAME ROM, OS/2, 클래식 Mac, 기존 SVF와 SVF에서 TTF로), 다시 실행한 수치가 든 각 레시피, 벌 수 정하기, maker의 경로 표(경로 대 명령줄), `svf/`의 각 페이스를 만드는 방법 |
| `docs/superpowers/specs/`, `docs/superpowers/plans/` | 기능별 설계 문서와 구현 계획 |
| `svf/dos/` | 완성형 및 자모 세트 페이스(처음에는 ScummVM 한글 맵용으로 만듦)와 그 라이선스 `.TXT` 파일 |
| `svf/jamo-extra/` | 합성 글리프 폰트에서 만든 추가 자모 세트 페이스(`FACES.TSV`) |
| `ttf/<family>/` | 맵이 사용하는 TrueType 페이스(`FONTS.md`) |
| `c/` | 이식 가능한 C 렌더러([c/README.ko.md](c/README.ko.md): API, 스위치, 게이트), 그 테스트(`make -C c check`), 포트 예제 `c/ports/{pico,esp32,arduino,ch582,dos,web,sdl}`와 그 호스트 검사 `c/ports/check`, 에뮬레이션 벤치 `c/bench` |
| `maker/` | SVF maker: 도구를 실행해 업로드하거나 로컬에서 선택한 폰트를 페이스로 변환하는 HTTP 서버(`maker/server.py`) |
| `desktop/` | SVF maker 데스크톱 앱: maker를 감싼 Electron 셸과 그 Linux AppImage 빌드(`docs/desktop-app.ko.md`, `docs/maker-desktop.ko.md`) |
| `web/` | WASM 폰트 선택기 페이지, 그 페이스 색인과 테스트([web/README.ko.md](web/README.ko.md)) |
| `tools/` | 폰트 도구와 그 테스트(`python3 -m unittest discover -s tools -p 'test_*.py'`). SVF maker의 테스트: `python3 -m unittest discover -s maker/test -p 'test_*.py'`. `facecheck.py`는 페이스를 매니페스트와 맵에 대조해 검사한다. `macfbit3.py`, `macfbit_svf.py`, `macsfnt.py`는 사용자가 제공하는 클래식 Mac 폰트를 변환한다(그런 폰트는 배포하지 않는다) |
| `tools/build/` | `build_faces.py`와 그 레시피 표 `faces.tsv`: `ttf/`의 폰트로부터 `svf/`의 페이스를 다시 빌드하고 비교한다 |
| `manifest/` | 모든 페이스의 sha256 기준선(`facecheck.py verify`) |

게임의 번역 번들을 읽는 게임 쪽 검사(`facecoverage.py`, `bake-supplements.py`, `charsetchars.py`)는
게임 쪽(ScummVM `tools/korean`)에 두며, 서브모듈에서 이 도구들을 가져다 쓴다.

C 렌더러의 예제(Pico, 컬러·그레이·모노 프로파일의 ESP32-C3와 ESP32-S3, Arduino Uno와 Mega,
SH1106 OLED를 단 WCH CH582M, DOS, WASM, SDL2/SDL3)는 `sh c/cross/build-all.sh --ports`로 빌드하며, 이 명령은
호스트 검사를 실행하고 필요한 에뮬레이터가 있으면 화면 검사도 실행한다. 원래의 ESP32는 크기 행만 있다. 크기는 `c/cross/SIZES.md`에, 속도는
`c/bench/MEASUREMENTS.md`에 있다.

## 5. 참고 문헌 / References

- SIL Open Font License 1.1 — <https://openfontlicense.org/open-font-license-official-text/>
- Unicode Hangul syllable composition — <https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/>
