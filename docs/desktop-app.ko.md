[English](desktop-app.md) | **한국어**

# SVF maker 데스크톱 앱

SVF maker 데스크톱 앱은 사용자가 가진 폰트를 자신의 컴퓨터에서 SVF 페이스(face)로 변환한다. 폰트(아웃라인 폰트, 비트맵
폰트, 클래식 Mac 한글 폰트, DOS Johab 폰트, 기존 SVF 파일)와 출력 폴더를 고르면, 앱은 각 파일이 어떤 종류인지 감지하고
적합한 변환 경로를 제시하며, 저장소의 폰트 도구를 실행하고, 게임이 쓰는 것과 같은 C 렌더러로 그린 모든 결과를 보여 주고,
페이스를 출력 폴더에 쓴다. 아무것도 업로드되지 않으며 어디로도 전송되지 않는다.

이 문서는 앱이 무엇이고 어떻게 쓰는지를 설명한다. 앱의 빌드와 패키징(AppImage, 라이선스, 릴리스 점검)은
[maker-desktop.ko.md](maker-desktop.ko.md)에, 서버와 HTTP API는 [../maker/README.ko.md](../maker/README.ko.md)에,
설계는 `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`에 있다.

상태: Linux AppImage는 작성자의 호스트(Ubuntu 24.04, x86_64)에서 빌드하고 테스트했다. Windows와 macOS 패키지는
**빌드되지 않았고 검증되지 않았다**(마지막 절 참조). 패키지는 서명되지 않았고 자동 업데이트가 없다.

## 목차

1. 앱의 구성
2. 앱 시작
3. 창, 단계별 설명
4. 앱이 이해하는 입력
5. 경로와 프리셋
6. 실행이 쓰는 것
7. 메뉴, 확대/축소, 창 상태
8. 프라이버시와 보안
9. 파일 위치, 로그, 환경 변수
10. 실패 처리
11. 한계와 검증되지 않은 것

## 1. 앱의 구성

앱은 하나의 패키지 안에 세 계층으로 이루어져 있다.

| 계층 | 정체 | 위치 |
|---|---|---|
| Shell | Electron 프로그램: 창 하나, 네이티브 메뉴, 네이티브 대화상자 넷. 나머지 두 계층을 시작하고 중지하며 페이지에 아주 작은 브리지를 건네 준다. | `desktop/main.js`, `desktop/preload.js`, `desktop/lib/*.js` |
| Maker 서버("sidecar") | `127.0.0.1`의 임의 포트에 바인딩되는 Python HTTP 서버. 폰트를 감지하고, 경로를 계획하고, 도구를 작업(job)으로 실행하며, 페이지를 제공한다. 패키지에서는 PyInstaller one-directory 번들 `svf-maker-sidecar`이며, 모든 도구는 같은 실행 파일을 `svf-maker-sidecar run-tool <name>`으로 호출한 것이다. | `maker/*.py`, `tools/*.py` |
| 페이지 | 사용자 인터페이스. sidecar가 제공하는 순수 HTML과 ES 모듈이다. WebAssembly로 컴파일한 C 렌더러(`maker/static/wasm/svf.wasm`)를 페이지 안에서 직접 실행하여 페이스를 미리 본다. | `maker/static/` |

창 제목은 "SVF maker"이다. shell은 정확히 한 페이지 `http://127.0.0.1:<port>/`만 로드한다. sidecar가 아직 시작되는 중이면
(2초 넘게) 창에는 작은 "starting the maker..." 페이지가 표시된다.

## 2. 앱 시작

Linux에서 패키지는 파일 하나 `svf-maker-<version>.AppImage`(약 150 MB)이다.

    chmod +x svf-maker-0.1.0.AppImage
    ./svf-maker-0.1.0.AppImage

- AppImage는 정적으로 링크된 자체 FUSE 3 코드로 스스로를 마운트한다. 머신에는 `fusermount` 또는 `fusermount3`만 있으면
  되며(Ubuntu 24.04에 있다) `libfuse.so.2`는 필요 없다.
- glibc 2.39 이상이 필요하다(빌드 호스트의 버전이며, 그보다 오래된 것은 테스트하지 않았다).
- 그래픽 세션이 필요하다. `$DISPLAY`가 없으면 앱은 Electron의 "Missing X server" 메시지와 함께 멈춘다.
- 사용자당 앱은 한 번에 하나만 실행된다. 다시 시작하면 기존 창에 포커스가 가고(두 번째 프로세스는 아무것도 띄우기 전에
  종료한다), 두 서버가 하나의 데이터 폴더를 공유할 수는 없다(`instance.lock`).
- 권한 없는 사용자 네임스페이스를 금지하는 시스템(Ubuntu 24.04가 그렇다)에서는 런처가 `--no-sandbox`를 추가하며,
  렌더러는 Chromium의 샌드박스 없이 실행된다. Help > About에 이 사실이 표시된다. 8절을 참조한다.

시작 순서(궁금한 사람을 위해): shell이 단일 인스턴스 잠금을 얻고, 로그를 열고, 새 임의 토큰과 `127.0.0.1:0`으로 sidecar를
시작하고, `svf-maker listening on 127.0.0.1:<port>` 줄을 기다린 뒤(최대 75초이며, 정상적인 시작은 2초 안에 이 줄을
출력한다) 창을 열고 페이지를 로드한다. 페이지는 `/api/caps`를 한 번 요청하여 로컬 모드로 실행 중인지, 어떤 선택적
부분이 있는지를 알아낸다.

## 3. 창, 단계별 설명

창은 1200 x 800으로 열린다(마지막으로 둔 크기와 위치가 기억된다). 페이지에는 상단 바와 네 영역이 있다: 소스(왼쪽), 일괄
설정(가운데), 폰트(오른쪽), 단계(아래).

### 3.1 첫 실행: 확인 동의

세션마다 처음 변환을 시작할 때 페이지에 "before you convert"가 표시된다. 선택한 폰트를 변환할 권리가 있음을 확인할
책임은 사용자에게 있고, 페이스는 선택한 출력 폴더에만 쓰이며, 공개하려면 각 폰트의 라이선스를 확인해야 한다는
내용이다. OK를 눌러 계속한다. 도구는 라이선스를 대신 확인해 주지 않는다. 라이선스를 선택하지 않으면 모든 note와
`BUILD.md`에 "licence: not checked (user's responsibility)"라고 적힌다.

### 3.2 소스 패널(왼쪽)

1. **choose files**는 네이티브 파일 대화상자(다중 선택)를 연다. **choose folder**는 네이티브 폴더 대화상자를 연다. 선택한
   항목은 각각 소스 루트 목록에 추가되며, 여러 번 선택할 수 있다. 폰트는 **있는 그대로의 위치에서** 읽힌다. 복사하거나
   업로드하지 않으며, 아카이브는 목록에만 표시될 뿐 풀지 않는다.
2. 텍스트 상자 "paths, one absolute path per line"은 같은 목록을 텍스트로 나타낸 것이다. 대화상자 대신 경로를 붙여넣을
   수 있다.
3. **choose output folder**는 폴더 대화상자("create folder" 포함)를 연다. 마지막으로 쓴 폴더에서 시작한다.
   "output folder" 텍스트 상자는 경로를 보여 주거나 직접 입력받는다.
4. **detect**는 소스를 읽어 폰트 표를 채운다.

모든 경로는 검사된다. 절대 경로여야 하고, 심볼릭 링크가 아니어야 하며, 앱 자신의 데이터 폴더가 아니어야 하고, 출력
폴더나 다른 소스와 겹치지 않아야 한다.

작업이 살아 있는 동안 앱은 중간 파일을 출력 폴더 안의 `.svf-maker-<id>/`(권한 0700)에 두고, 작업이 끝나거나 삭제되거나
앱이 종료될 때 지운다. 클라우드 클라이언트가 **동기화하지 않는** 출력 폴더를 고른다.

패널 아래의 **jobs**는 이 세션의 작업을 나열하므로 작업 사이를 전환할 수 있다.

### 3.3 폰트 표(오른쪽)

감지 후에는 모든 폰트(또는 컬렉션의 모든 페이스)가 한 행이 된다: 그 파일, 패밀리와 스타일, 종류(4절 참조), 폰트가
비트맵이면 제공하는 픽셀 크기, 행별 포함 체크 상자, 그리고 WASM 렌더러가 그린 한글 음절 미리보기이다. 경로가 없는
행은 비활성화되고 체크 해제된 채로 남으며 이유가 표시된다(예: 짝이 되는 표가 없는 한글 폰트). 페이지는 거부된 파일
(폰트가 아님, 읽을 수 없음, 규칙 밖)도 숨기지 않고 "refused" 목록에 나열한다.

### 3.4 일괄 설정(가운데)

하나의 설정 묶음이 일괄 전체에 적용되며, 행은 제외를 선택할 수 있다.

| 컨트롤 | 의미 |
|---|---|
| dest | 페이스가 들어갈, 출력의 `svf/` 트리 아래 하위 폴더(목록에 있는 기존 이름, 또는 `my/set` 같은 이름을 쓰는 "new"). |
| kinds | **precomposed**: 음절마다 가변 폭 글리프 하나(SVF v3). **jamo**: 자모 조각을 담고 그릴 때 음절을 조합하는 페이스(JSET 블록). 하나 또는 둘 다 체크한다. |
| layout | jamo용: 조각 배치(예: `844`, `adaptive`, `621`, 또는 소스가 필요로 할 때 Mac 또는 Hanterm 배치). |
| sizes | 생성할 픽셀 크기, 예: `16, 20`. 비트맵 폰트는 자신이 담고 있는 크기만 제공한다. |
| bpp | 픽셀당 1비트 또는 2비트. 하나 또는 둘 다 체크한다. |
| range | 포함할 문자 집합. |
| preset | 이름 붙은 레시피(5절). "plain"은 도구의 기본값을 쓴다. |
| advanced panel | 세부 컨트롤: cell, ascent, width, space advance, mono hint, clip cell, fit cell, Latin top, embolden, symbols, JSET version, header ascent, fit baseline, AA refine, clean noise, binarize(threshold, ridge, mono), Latin ascent, Hangul ascent. 여기의 값이 프리셋의 값보다 우선한다. 경로가 쓸 수 없는 컨트롤은 숨겨지거나 비활성화된다. |

### 3.5 상단 바의 버튼

| 버튼 | 동작 |
|---|---|
| save settings | 현재 설정을 작업에 저장한다(확인을 위해 다시 읽어 오기도 한다). |
| run | 작업을 대기열에 넣는다. 상태 줄에 작업의 상태가 표시되며, 서버가 바쁘면 순번도 표시된다. |
| cancel | 실행 중인 작업을 중지하고 그 도구 프로세스를 종료한다. |
| edit and re-run | 실행 후 같은 소스로 설정 화면으로 돌아간다. |
| open folder | 출력 폴더를 시스템 파일 관리자에 표시한다(이 앱에서 직접 고른 폴더에 한함). |
| download zip | 일반 웹 페이지의 업로드 모드에서 쓰인다. 데스크톱 앱은 대신 출력 폴더에 쓰며 zip이 없다. |
| delete job | 작업을 잊고 그 출력 폴더를 비운다. 이미 쓰인 페이스는 남는다. |

### 3.6 단계 표(아래)

각 작업은 단계(detect, convert, check, preview...)의 목록이다. 표에는 각 단계의 도구, 인자 목록, 상태, 로그의 끝부분이
표시되므로 어떤 폰트에 어떤 명령이 실행되었는지 정확히 볼 수 있다. 모든 결과 페이스는 캔버스에 그려지며, 페이지는
캔버스에 잉크가 있을 때만 그 페이스를 정상으로 센다.

## 4. 앱이 이해하는 입력

| 입력 | 비고 |
|---|---|
| TrueType, OpenType, 컬렉션(`.ttf`, `.otf`, `.ttc`), 가변 폰트 | 아웃라인 폰트. 가변 폰트는 사용자가 고른 인스턴스로 변환된다. |
| BDF, PCF, HBF 비트맵 폰트 | ISO 10646, ISO 8859, KS C 5601 인코딩. Johab BDF. |
| DOS raw 한글 폰트 | Johab 8x4x4 / 6x2x1 방식의 raw 폰트(및 24 px HBIOS). HWP `ASCII.PFT`(12x24 영문)는 24 px 페이스의 짝(companion)으로 쓰인다. `HANGUL*.PFT`는 읽지 않으며 읽지 않음으로 표시된다. |
| 클래식 Mac HangulTalk 7.1 type-3 `fbit` | 리소스 포크, AppleDouble `._Name`, MacBinary `.bin`, JM 아카이브, 또는 raw `fbit` 리소스에서 읽는다. HTBL 1 표(`InputBackSupport` 또는 `<Name>.htbl1`, 다른 소스로 함께 선택)가 필요하며 Latin suitcase(FOND + NFNT)를 쓸 수도 있다. |
| 클래식 Mac HangulTalk 1.0 폰트 | `fdef`가 있는 포크. `fdef` 없는 raw 1.0 `fbit`는 무엇이 빠졌는지와 함께 목록에 표시된다. |
| Hanterm Johab 폰트 | 배치 `hanterm-johab`. |
| SVF 파일(`.svf`) | 복사되거나(경로가 허용할 때) jamo fit의 소스로 쓰인다. 업로드한 SVF는 자신의 JSET 블록을 유지한다. |

독점 폰트, 비트맵, 표는 앱과 함께 배포되지 않는다. 테스트는 합성 입력을 쓴다.

폰트 옆의 라이선스 파일은 그것도 함께 선택된 경우(또는 폴더 전체가 선택된 경우)에만 쓰인다. 앱은 사용자가 선택한
라이선스를 페이스의 note에 기록할 수 있지만, 어떤 폰트를 변환해도 자유롭다고 스스로 판단하는 일은 없다.

## 5. 경로와 프리셋

각 폰트에 대해 maker는 그 종류에 맞는 경로를 제시한다. 경로는 저장소 도구의 고정된 순서열이다.

| 종류 | 경로 |
|---|---|
| precomposed | `mkfont`(아웃라인에서 SVF로); `johab844`(DOS raw, 16 px); `bdfface`; `mac fbit 7.1 bdf + mkfont`; `copy`(SVF를 그대로) |
| jamo | `composite`; `experimental fit`(2 bpp, 느림, 품질 제약); `mask fit`(`freetype-py`와 `uharfbuzz` 필요, 9절 참조); `vector fit`(폰트당 수 분 소요); `dos raw`; `hanterm`; `mac fbit 1.0`; `mac fbit 7.1 direct`와 `derived`; `bdfface + from-svf fit`; `from-svf fit`; `copy` |

프리셋은 이름 붙은 출발점이다. 고급 패널이 프리셋을 덮어쓴다.

| 프리셋 | 레시피 | 재현 대상 |
|---|---|---|
| `plain` | 도구의 기본값 | |
| `dos-l-1bpp` | cell 16, 1 bpp, ASCII + 한자 제외 KS X 1001 + 추가 8자 | `svf/dos/NEODG16.SVF`(글리프 하나 적음) |
| `dos-u-2bpp` | cell 16, 2 bpp, clip cell, ascent size-2 | `svf/dos/GBATB17.SVF`(크기 17에서 바이트 단위로 동일), `NGOTB16.SVF` |
| `latin-18cell-2bpp` | cell 18, width 18, 2 bpp, 나열한 문자만 | `svf/dos/PAPLG16.SVF` |
| `jamo-844`, `jamo-844-symbols`, `jamo-844-hbios24`, `jamo-621` | DOS raw 폰트에서 나온 jamo 배치 | `maker/presets.py`에 이름이 붙은 배치 |

## 6. 실행이 쓰는 것

출력 폴더 안에만 쓰며, 그 밖에는 아무것도 쓰지 않는다.

    <output>/
      svf/<dest>/<NAME>.SVF          the face
      svf/<dest>/<NAME>.TXT          its note (how it was made, the licence you chose or "not checked")
      svf/<dest>/<licence file>      when a licence text was chosen
      build-<id>/
        BUILD.md                     what was converted, with which commands
        LICENCES.tsv.lines           lines for the repository's web/LICENCES.tsv
        FAMILIES.tsv.lines           lines for its families table
        FACES.TSV.lines              lines for its faces table

- 작업이 직접 쓰지 않은 이름은 절대 대체되지 않는다. 파일이 이미 있으면 실행은 건너뛰거나 거부하며, 사용자의 파일을
  덮어쓰지 않는다.
- `.lines` 파일은 사용자가 저장소의 표에 손으로 병합하는 조각이다(저장소의 `web/mkindex.py --check`가 병합된 결과를
  받아들인다).
- 쓰인 모든 페이스는 저장소의 `facecheck.py`를 통과하며, 페이지가 렌더러로 그려 본 뒤에야 완료로 센다.

## 7. 메뉴, 확대/축소, 창 상태

- **File**: Open output folder; Quit.
- **View**: Reload; Actual size; Zoom in과 Zoom out(Ctrl과 `+` 또는 `-`, 50%에서 300%까지).
- **Help**: About은 앱 버전, 빌드 id, Electron, Chromium, Node 버전, sidecar의 버전과 Python, 렌더러 샌드박스 상태,
  그리고 서드파티 라이선스(`THIRD-PARTY.txt`) 버튼을 보여 준다.

shell은 `shell-state.json`에 네 가지를 기억한다: 창의 위치와 크기, 확대 배율, 마지막 출력 폴더, 그리고 내준 출력
폴더들(마지막 32개, 실제 경로로 저장하며 이것들만 "Open output folder"로 열 수 있다). 토큰과 입력 경로는 저장하지
않는다.

## 8. 프라이버시와 보안

- **네트워크 없음.** 페이지의 Content-Security-Policy는 자기 origin만 허용한다. shell은 sidecar로 가지 않는 모든 요청을
  취소한다(새 창, 탐색, 다운로드, 장치 및 권한 요청은 모두 거부된다). maker 자체 코드는 네트워크 라이브러리를 import하지
  않는다. 텔레메트리, 충돌 업로드, 업데이트 확인은 없다.
- **토큰.** sidecar는 실행할 때마다 새 임의 토큰으로 시작한다. shell이 이를 페이지의 `/api/` 요청에 `X-Maker-Token`으로
  덧붙이며, 페이지 자신은 토큰을 보지 못한다. 모든 요청은 이 서버의 `Host`도 실어야 한다. 서버는 loopback에만
  바인딩되며 그 밖의 것은 거부한다.
- **브리지.** 페이지는 네 함수가 있는 `window.svfMaker`를 받는다: `pickFiles()`, `pickFolder()`, `pickOutputDir()`,
  `openOutputFolder()`(그리고 읽기 전용 `platform`). shell은 maker 자신의 origin의 프레임에만 응답한다. 경로는
  절대 경로이며, 취소된 대화상자는 빈 목록 또는 `null`을 반환한다.
- **파일.** 폰트는 제자리에서 읽히며 수정되지 않는다. 출력은 사용자가 고른 폴더 아래에만 쓰인다.
- **샌드박스.** 페이지는 context isolation, Node 통합 없음, 샌드박스된 preload로 실행된다. 시스템이 사용자
  네임스페이스를 거부하는 곳에서는 Chromium 자체의 프로세스 샌드박스가 **꺼진다**(AppImage는 SUID 헬퍼를 담을 수
  없다). 그 경우 렌더러는 loopback의 앱 자신의 페이지만 로드한다.
- **프로세스.** 각 도구는 자신의 세션에서 실행되고 `tools.pids`에 기록된다. 앱을 종료하거나 충돌이 나도 실행 중인 도구가
  남지 않는다(다음 시작 때 남은 것을 정리한다).
- **서드파티 코드.** `THIRD-PARTY.txt`는 번들된 모든 라이브러리를 그 라이선스와 함께 나열한다. 출처 표기가 없거나 GPL인
  라이브러리가 있으면 빌드가 실패한다.

## 9. 파일 위치, 로그, 환경 변수

| 항목 | 위치 |
|---|---|
| 앱 데이터(작업, 작업 파일, `instance.lock`, `tools.pids`) | `~/.config/svf-maker/maker`(앱의 user-data 폴더에 `maker`를 더한 것) |
| 창 상태 | `~/.config/svf-maker/shell-state.json` |
| shell 로그 | `~/.config/svf-maker/logs/`(redaction 규칙이 허용하는 것 이상의 폰트 이름이나 경로는 없으며, 토큰은 절대 없다) |
| 개발 실행 데이터 | `~/.config/svf-maker/maker-dev` |

선택적 환경 변수(앱을 시작하기 전에 설정한다):

| 변수 | 효과 |
|---|---|
| `JAMOSET_PYLIB` | `freetype-py`와 `uharfbuzz`가 있는 폴더. `mask fit` 경로와 `binarize mono`를 활성화한다. |
| `SVF_RECOG_PYTHON` + `SVF_RECOG_DIR` | 인터프리터(절대 경로, numpy, torch, PIL, fontTools 포함)와, 조각 정체 검사를 위한 사용자 자신의 `recog.py`가 있는 폴더. 점수 계산 전용이며 아무것도 함께 배포되지 않는다. 이것이 없으면 페이지는 검사를 쓸 수 없다고 표시한다. |
| `SVF_MAKER_DEV=1` | 개발 모드: frozen sidecar 대신 체크아웃에서 `python3 maker/server.py`를 실행한다. `SVF_MAKER_DEV_REPO`가 체크아웃을 지정한다. |
| `SVF_MAKER_DEVTOOLS=1` | 개발자 도구와 View > Toggle DevTools 항목을 활성화한다. |
| `SVF_MAKER_SHELL_LOG=stderr` | shell 로그가 표준 오류에도 출력된다. |
| `SVF_MAKER_SMOKE=1` | 시작하고, `/api/caps`를 확인하고, 한 줄을 출력한 뒤 종료한다(릴리스 점검에서 사용). |

## 10. 실패 처리

- **서버가 시작하지 못함**(오류 대화상자 후 앱 종료): 대화상자에 서버 출력의 마지막 줄들이 표시된다. 다른 maker가 아직
  종료 중이면 잠시 기다렸다가 다시 시작한다.
- **앱이 실행 중일 때 서버가 멈춤**: 대화상자가 Restart 또는 Quit를 제안한다. 재시작에는 횟수 제한이 있으며, 짧은 시간에
  너무 많이 재시작하면 앱이 종료된다.
- **창이 충돌함**: 앱은 같은 페이지를 한 번 다시 로드하며, 두 번째 충돌이 나면 메시지를 보여 주고 종료한다.
- **종료**: shell은 sidecar에 중지를 요청하고(최대 45초) 실행 중인 작업을 취소하며 그 도구 프로세스를 종료한다. 그 시점에
  대기 중이거나 실행 중이던 작업은 작업 파일이 프로세스와 함께 사라지므로 실패(`interrupted`)로 표시된다. 출력 폴더에
  이미 쓰인 페이스는 남는다.
- **디스크 가득 참, 특이한 파일 시스템, 대소문자를 구분하지 않는 디스크, 동기화 클라이언트**: 테스트하지 않았다(아래
  참조).

## 11. 한계와 검증되지 않은 것

- Windows와 macOS: 빌드하지도 실행하지도 않았다. 서버는 Windows에 대응하지 않는다(프로세스 그룹, 잠금, 파일 링크 호출이
  POSIX이다). macOS 계획(서명, notarisation)은 [maker-desktop.ko.md](maker-desktop.ko.md)에 적혀 있다.
- `mask fit` 경로는 작성자의 호스트에서 작업을 한 번도 실행한 적이 없다(그곳에는 라이브러리가 설치되어 있지 않다).
  정체 검사는 스텁으로만 테스트했다. `vector fit`은 폰트당 수 분이 걸린다.
- 네이티브 대화상자, 파일 관리자 연동, 실제 FUSE 마운트를 통한 창 시작, GPU 경로, 샌드박스된 렌더러는 손으로만
  확인했다. 자동화된 테스트는 대화상자를 스텁으로 대체하고 GPU를 끈 채 실행한다.
- 실제 Mac, HWP, Johab 파일은 환경 변수가 사용자 자신의 사본을 가리키는 곳에서만 테스트한다. 저장소의 테스트는 합성
  입력을 쓴다.
- AppImage는 비트 단위로 재현되지 않으며 자동 업데이트도 없다. 새 버전은 새 파일이다.
