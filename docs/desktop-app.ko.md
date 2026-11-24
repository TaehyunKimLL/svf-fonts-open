[English](desktop-app.md) | **한국어**

# SVF maker 데스크톱 앱

SVF maker 데스크톱 앱은 사용자가 가진 폰트를 자신의 컴퓨터에서 SVF 페이스(face)로 변환한다. 폰트(아웃라인 폰트, 비트맵
폰트, 클래식 Mac 한글 폰트, DOS Johab 폰트, 기존 SVF 파일)와 출력 폴더를 고르면, 앱은 각 파일이 어떤 종류인지 감지하고
적합한 변환 경로를 제시하며, 저장소의 폰트 도구를 실행하고, 게임이 쓰는 것과 같은 C 렌더러로 그린 모든 결과를 보여 주고,
페이스를 출력 폴더에 쓴다. 아무것도 업로드되지 않으며 어디로도 전송되지 않는다.

이 문서는 앱이 무엇이고 어떻게 쓰는지를 설명한다. 앱의 빌드와 패키징(AppImage, 라이선스, 릴리스 점검)은
[maker-desktop.ko.md](maker-desktop.ko.md)에, 서버와 HTTP API는 [../maker/README.ko.md](../maker/README.ko.md)에,
설계는 `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`에 있다.

상태: Linux AppImage는 작성자의 호스트(Ubuntu 24.04, x86_64)에서 빌드하고 테스트했으며, 두 번째의 깨끗한 Ubuntu 24.04.5
호스트에서도 시작했다(13절). Windows x64 설치 프로그램과 포터블 `.exe`는 GitHub Actions(`windows-latest`)에서 빌드하고
테스트했다. 아직 누구도 Windows 데스크톱에서 써 보지 않았다(13절). macOS는 **빌드되지 않았고 검증되지 않았다**. 어떤 패키지도
서명되지 않았고 자동 업데이트가 없다.

## 빠른 시작

Linux(x86_64)에서는 내려받을 파일이 없다. 앱은 아래처럼 이 저장소의 git 체크아웃에서 빌드한다. Windows(x64)에서는 빌드
워크플로가 만드는 두 `.exe` 파일을 쓴다(아래 [Windows (x64)](#windows-x64)). macOS는 아직 지원하지 않는다(13절).

**필요한 것**

| 항목 | 비고 |
|---|---|
| git 체크아웃 | 빌드가 `git log`와 `git describe`를 읽는다. 단순한 소스 아카이브로는 동작하지 않는다. |
| pip가 있는 Python 3.12 | `python3 --version`이 3.12여야 하고 `python3 -m pip`가 동작해야 한다. 사이드카의 고정 wheel이 cp312이다(마지막으로 3.12.3). `python3-venv`는 필요 없다. |
| 시스템 `python3`용 Pillow와 fontTools | 갓 설치한 Ubuntu 24.04에는 둘 다 없다. 빌드의 동결 테스트와 개발 실행(아래)은 시스템 `python3`로 maker 자신의 Python 코드를 import하며, 그 코드가 `PIL`과 `fontTools`를 import한다(`maker/detect.py`). 패키지된 앱에는 필요 없다(고정된 wheel Pillow 10.2.0, fontTools 4.66.1을 싣는다). apt로 설치한다(아래). 시작할 때 그 밖의 것은 import하지 않는다. numpy, torch, freetype-py, uharfbuzz, pathops는 선택 사항이며 그것을 밝힌 경로에서만 쓰인다. |
| node 22와 npm | node 22.12 이상(`desktop/package-lock.json`이 요구한다). Ubuntu 24.04의 apt에는 node 18이 있어 너무 오래되었다. NodeSource나 nvm을 쓴다. node 22.23.4와 npm 12를 썼다(node 22가 번들하는 npm 10은 시도하지 않았다). |
| emsdk | 빌드가 미리 보기 모듈(WebAssembly)을 직접 컴파일한다. `$EMSDK/upstream/emscripten/emcc`에서 `emcc`를 찾으며 `$EMSDK`의 기본값은 `~/opt/emsdk`이다. 없으면 `sh c/cross/install-toolchains.sh "$HOME/opt" emsdk`(마지막으로 emcc 6.0.13). |
| `xvfb-run`과 `flock` | 마지막 빌드 단계가 새 AppImage를 가상 디스플레이에서 한 번 시작한다(스모크 검사). `xvfb-run`이 없으면 그 검사가 실패하고 스크립트는 종료 코드 1로 끝나지만 AppImage는 이미 존재한다(아래 참조). 검사만 안 된 것이다. `flock`은 util-linux에 있다. |
| 네트워크, 첫 빌드에만 | pip가 고정된 wheel(해시 확인)을, npm과 Electron이 패키지를, electron-builder가 AppImage 도구 세트를 내려받는다. 이후 빌드는 캐시를 재사용한다. |
| 디스크 | 수 GB: `desktop/node_modules`, 스크래치 디렉터리, `desktop/dist`(풀어 놓은 트리가 약 335 MB). |

갓 설치한 Ubuntu 24.04에서 필요한 패키지는 다음과 같다(`flock`은 util-linux에 있어 항상 있다. `libpython3.12-dev`는 `python3`이 끌어오는
`libpython3.12t64`가 있는 호스트에서는 필요 없다. 그것이 없는 호스트는 시도하지 않았다).

    sudo apt install git curl xz-utils python3-pip python3-pil python3-fonttools xvfb

`python3-pil`은 고정된 버전인 Pillow 10.2.0이다. `python3-fonttools`는 4.46.0으로 고정된 4.66.1보다 오래되었다. maker의 detect, route,
로컬 모드, 종단 간 테스트 파일(`maker/test/test_detect.py`, `test_routes.py`, `test_local.py`, `test_e2e.py`)은 이것으로 통과한다.
동결 테스트 자체는 이것으로 실행하지 않았다(작성자의 호스트에는 pip로 설치한 fontTools 4.66.1이 있다). 고정된 것을 원하면
`python3 -m pip install --user --break-system-packages fonttools==4.66.1`. `curl`, `xz-utils`, `git`은 `install-toolchains.sh`가 emsdk를
가져오는 데 필요하다. node 22는 따로 설치한다(node 행 참조).

**빌드**(각 명령 앞에 작업 디렉터리를 적었다. 명령은 이 순서대로 한 번 실행한다)

    # in the checkout root
    mkdir -p ~/work/tmp                          # the release check keeps its lock file there
    cd desktop && npm ci && node node_modules/electron/install.js && cd ..
    bash desktop/build/build-appimage.sh

- `npm ci`는 npm 12가 설치 스크립트를 차단했다는 경고(예: `electron-winstaller ... select-7z-arch.js`)를 출력한다. 앱을 Linux용으로만
  패키징하므로 여기서는 무해하다. 같은 차단 때문에 Electron 자체의 바이너리는 `node node_modules/electron/install.js`로 받는다.
- `build-appimage.sh`는 스스로 체크아웃 루트로 이동하므로 어디서든 시작할 수 있지만, 여기의 다른 명령은 모두 체크아웃 루트에서
  시작한다. WebAssembly 모듈, 동결된 사이드카(테스트 포함), 고지 파일, AppImage를 빌드한 다음 릴리스 점검마다 `CHECK <name> ok` 줄을
  하나씩 출력한다. 점검이 하나라도 실패하면 스크립트는 종료 코드 1로 끝난다.
- 빌드는 스크래치(pip 다운로드, PyInstaller 작업 디렉터리, 추출물)를 `$SVF_DESKTOP_TMP`에 둔다. 기본값은
  `~/work/tmp/svf-desktop-build`이며, 원하면 다른 폴더로 지정한다. 빌드가 돌고 있지 않을 때 지운다.
- `~/.local/bin/heavy`는 작성자의 자원 보호 장치이다(공유 호스트에서 메모리와 태스크를 제한한다). 필요하지 않다. 위에 적은 대로
  빌드를 시작한다. 캐시가 따뜻할 때 여기서는 1분 반이 걸렸고, 첫 빌드는(다운로드 때문에) 더 걸린다.

**AppImage가 생기는 곳**: `desktop/dist/svf-maker-0.1.0.AppImage`(버전은 `desktop/package.json`의 것)이며 약 133~134 MiB(140 MB)이다.
직접 빌드한 것의 크기를 재 보라. 수치는 도구 체인에 따라 다르다. 어디로든 복사해도 된다. 자체 완결된 파일 하나이다.

**시작**(그래픽 세션이 필요하다. 아래의 첫 변환은 앱에서 한다). 빌드 직후 체크아웃 루트에서:

    chmod +x desktop/dist/svf-maker-0.1.0.AppImage
    desktop/dist/svf-maker-0.1.0.AppImage

또는 먼저 복사한다.

    mkdir -p "$HOME/Apps"
    cp desktop/dist/svf-maker-0.1.0.AppImage "$HOME/Apps/"
    cd "$HOME/Apps" && ./svf-maker-0.1.0.AppImage

이후 절에서는 현재 디렉터리의 파일을 `./svf-maker-0.1.0.AppImage`로 적는다.

**첫 변환**

1. "SVF maker" 창이 열린다. 소스 패널에서 **choose files**(또는 **choose folder**)를 눌러 폰트(예: `.ttf`)를 고른다.
2. **choose output folder**를 눌러 비어 있고 클라우드 클라이언트가 동기화하지 않는 폴더를 고른다.
3. **detect**를 누르고 "before you convert" 안내를 읽은 뒤 OK를 누른다. 폰트 표가 채워진다.
4. 원하는 행의 **use** 상자를 체크한다(행은 그 폰트와 함께 라이선스 파일이 발견된 경우에만 미리 체크되며, DOS raw 폰트는 절대
   미리 체크되지 않는다). 일괄 설정을 살펴보고(처음에는 프리셋 `plain`이면 충분하다) **run**을 누른다. 단계 표는 각 단계의 상태, 시간(seconds), stderr를 보여 준다(명령 자체는 출력 폴더의 `build-<id>/BUILD.md`에 기록되며, [recipes.ko.md](recipes.ko.md#데스크톱-앱과-maker-경로)가 각 경로를 그 명령줄에 대응시킨다).
5. 작업이 끝나면 **open folder**를 누른다. 페이스는 `<output>/svf/<dest>/`에 있다(6절).

**패키징 없이 체크아웃에서 실행**(개발용. AppImage도 PyInstaller도 없다. 위와 같은 Python, node, emsdk, 네트워크가 필요하지만 한 번만, 그리고 위의 apt 패키지도 필요하다. 셸이 시스템 `python3`로 maker를 시작하므로 그 `python3`이
Pillow와 fontTools를 import할 수 있어야 한다):

    # in the checkout root
    cd desktop && npm ci && node node_modules/electron/install.js
    bash ../maker/build-wasm.sh                  # still in desktop/: builds maker/static/wasm/svf.wasm
    node_modules/.bin/electron --no-sandbox .    # still in desktop/

셸은 패키지된 사이드카를 찾지 못하므로 체크아웃의 `python3 -P maker/server.py`를 시작한다(데이터 폴더
`~/.config/svf-maker/maker-dev`). `--no-sandbox`는 사용자 네임스페이스를 막는 호스트(Ubuntu 24.04)용이며, 그 밖에서는 빼도 된다.
로그는 `~/.config/svf-maker/logs/shell.log`에 쌓인다(`SVF_MAKER_SHELL_LOG=stderr`이면 화면에도 출력된다).

**제거**: AppImage와 `~/.config/svf-maker/`를 삭제한다(12절).

### Windows (x64)

**받기.** 저장소의 워크플로 `windows`(`.github/workflows/windows.yml`, GitHub Actions)가 그 브랜치에 push할 때마다, 그리고 요청할
때 두 Windows 패키지를 빌드한다. 녹색(성공) 실행을 열고 아티팩트 `svf-maker-windows`(zip, 14일 보관)를 내려받는다. 안에는:

| 파일 | 무엇인가 |
|---|---|
| `svf-maker-0.1.0-setup.exe` | 설치 프로그램: 한 번 클릭, 내 사용자에게만(관리자 권한 없음), `%LOCALAPPDATA%\Programs\svf-maker`에 설치하고 시작 메뉴에 "SVF maker"를 추가한다. 제거는 설정 > 앱(또는 "프로그램 추가/제거")에서 한다. |
| `svf-maker-0.1.0-portable.exe` | 설치 없이 실행되는 파일 하나: 시작할 때마다 먼저 앱을 임시 폴더에 풀고(몇 초) 끝날 때 지운다. |
| `THIRD-PARTY.txt` | 묶인 모든 것의 고지(설치된 앱에도 같은 파일이 있다). |

Windows에서 직접 빌드하려면 [maker-desktop.ko.md](maker-desktop.ko.md#windows-t_9b8f56f0)를 본다.

**서명 없음: SmartScreen.** 두 파일 모두 코드 서명이 없다. 인터넷에서 온 파일(내려받은 zip은 그 안의 파일에 표시를 남긴다)을 시작하면
Windows SmartScreen이 "Windows의 PC 보호"를 보여 준다. **추가 정보**를 누르고, 실행에서 내려받은 바로 그 파일인지 확인한 뒤
**실행**을 누른다. 브라우저도 다운로드 자체에 경고할 수 있다("일반적으로 다운로드되지 않는 파일"). 백신이 포터블 파일을 처음
검사하는 데 시간이 걸릴 수 있다. 그 밖에 권한을 묻는 것은 없다: 설치 프로그램은 권한을 올리지 않고, 앱은 네트워크 연결을 만들지
않는다(Windows 방화벽이 묻는 일이 없다).

**쓰기.** 시작 메뉴의 "SVF maker"(또는 포터블 파일)로 시작한다. 창과 단계는 Linux와 같다(위의 첫 변환, 3~7절). 경로는 Windows
경로다(`C:\Users\you\Fonts`, `\\server\share\fonts`). 드라이브 전체(`C:\`)는 출력 폴더가 될 수 없다.

**어디에 있나.** 앱의 데이터는 `%APPDATA%\svf-maker\`에 있다(`maker\`에 작업, `logs\shell.log`에 로그. 9절). **제거**: 제거(설치
프로그램)하거나 포터블 파일을 지운 다음 `%APPDATA%\svf-maker\`를 지운다(12절).

## 목차

빠른 시작(위)

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
11. 볼 수 있는 메시지
12. 복구, 데스크톱 통합, 제거
13. 한계와 검증되지 않은 것

## 1. 앱의 구성

앱은 하나의 패키지 안에 세 계층으로 이루어져 있다.

| 계층 | 정체 | 위치 |
|---|---|---|
| 셸 | Electron 프로그램: 창 하나, 네이티브 메뉴, 네이티브 대화상자 넷. 나머지 두 계층을 시작하고 중지하며 페이지에 아주 작은 브리지를 건네 준다. | `desktop/main.js`, `desktop/preload.js`, `desktop/lib/*.js` |
| Maker 서버("사이드카") | `127.0.0.1`의 임의 포트에 바인딩되는 Python HTTP 서버. 폰트를 감지하고, 경로를 계획하고, 도구를 작업(job)으로 실행하며, 페이지를 제공한다. 패키지에서는 PyInstaller one-directory 번들 `svf-maker-sidecar`이며, 모든 도구는 같은 실행 파일을 `svf-maker-sidecar run-tool <name>`으로 호출한 것이다. | `maker/*.py`, `tools/*.py` |
| 페이지 | 사용자 인터페이스. 사이드카가 제공하는 순수 HTML과 ES 모듈이다. WebAssembly로 컴파일한 C 렌더러(`maker/static/wasm/svf.wasm`)를 페이지 안에서 직접 실행하여 페이스를 미리 본다. | `maker/static/` |

창 제목은 "SVF maker"이다. 셸은 정확히 한 페이지 `http://127.0.0.1:<port>/`만 로드한다. 사이드카가 아직 시작되는 중이면
(2초 넘게) 창에는 작은 "starting the maker..." 페이지가 표시된다.

## 2. 앱 시작

Linux에서 패키지는 파일 하나 `svf-maker-<version>.AppImage`(약 133~134 MiB이며 빠른 시작대로 빌드한다)이다.

    chmod +x svf-maker-0.1.0.AppImage
    ./svf-maker-0.1.0.AppImage

- AppImage는 정적으로 링크된 자체 FUSE 3 코드로 스스로를 마운트한다. 머신에는 `fusermount` 또는 `fusermount3`만 있으면
  되며(Ubuntu 24.04에 있다) `libfuse.so.2`는 필요 없다.
- glibc 2.39 이상이 필요하다(빌드 호스트의 버전이며, 그보다 오래된 것은 테스트하지 않았다).
- `/tmp`에서 실행이 가능해야 한다. 이미지는 `/tmp/.mount_*` 아래에 마운트된다(12절).
- 그래픽 세션이 필요하다. `$DISPLAY`가 없으면 앱은 Electron의 "Missing X server" 메시지와 함께 멈춘다.
- 사용자당 앱은 한 번에 하나만 실행된다. 다시 시작하면 기존 창에 포커스가 가고(두 번째 프로세스는 아무것도 띄우기 전에
  종료한다), 두 서버가 하나의 데이터 폴더를 공유할 수는 없다(`instance.lock`).
- 권한 없는 사용자 네임스페이스를 금지하는 시스템(Ubuntu 24.04가 그렇다)에서는 런처가 `--no-sandbox`를 추가하며,
  렌더러는 Chromium의 샌드박스 없이 실행된다(자동이며 아무것도 넘길 필요가 없다). Help > About에 이 사실이 표시된다. 8절을 참조한다.
- AppImage는 아무것도 설치하지 않는다. 메뉴 항목도, 아이콘 테마 항목도 없다. 추가하는 방법은 12절에 있다.

Windows에서 패키지는 설치 프로그램이나 포터블 `.exe`다(빠른 시작, [Windows (x64)](#windows-x64)). 같은 규칙이 적용된다: 사용자당
한 번에 앱 하나, 데이터 폴더당 서버 하나. 그곳에서는 Chromium의 렌더러 샌드박스가 켜져 있다(Help > About이 "renderer sandbox: on"이라고
한다). 사이드카는 콘솔 창 없이 실행되고, 그 도구들도 그렇다.

시작 순서(궁금한 사람을 위해): 셸이 단일 인스턴스 잠금을 얻고, 로그를 열고, 새 임의 토큰과 `127.0.0.1:0`으로 사이드카를
시작하고, `svf-maker listening on 127.0.0.1:<port>` 줄을 기다린 뒤(최대 75초이며, 정상적인 시작은 2초 안에 이 줄을
출력한다) 창을 열고 페이지를 로드한다. 페이지는 `/api/caps`를 한 번 요청하여 로컬 모드로 실행 중인지, 어떤 선택적
부분이 있는지를 알아낸다.

## 3. 창, 단계별 설명

창은 1200 x 800으로 열린다(마지막으로 둔 크기와 위치가 기억된다). 페이지에는 상단 바가 있고 그 아래에: 소스 패널과 작업 목록이
있는 좁은 왼쪽 열, 그 옆(왼쪽 열의 오른쪽)의 일괄 설정, 그 둘 아래 전체 너비의 폰트 표, 맨 아래의 단계 표가 있다. 1000 px보다 좁은
창에서는 영역이 한 열로 쌓인다.

### 3.1 첫 실행: 확인 동의

세션마다 처음 **detect**를 누를 때(무엇이 만들어지기 전에) 페이지에 "before you convert"가 표시된다. 선택한 폰트를 변환할 권리가 있음을 확인할
책임은 사용자에게 있고, 페이스는 선택한 출력 폴더에만 쓰이며, 공개하려면 각 폰트의 라이선스를 확인해야 한다는
내용이다. OK를 눌러 계속한다. 도구는 라이선스를 대신 확인해 주지 않는다. 라이선스를 선택하지 않으면 모든 note와
`BUILD.md`에 "licence: not checked (user's responsibility)"라고 적힌다.

### 3.2 소스 패널(왼쪽)

1. **choose files**는 네이티브 파일 대화상자(다중 선택)를 연다. **choose folder**는 네이티브 폴더 대화상자를 연다. 선택한
   항목은 각각 버튼 아래에 표시되는 소스 루트 목록에 추가되며, 여러 번 선택할 수 있다. 폰트는 **있는 그대로의 위치에서** 읽힌다.
   복사하거나 업로드하지 않으며, 아카이브는 목록에만 표시될 뿐 풀지 않는다.
2. **choose output folder**는 폴더 대화상자("create folder" 포함)를 연다. 마지막으로 쓴 폴더에서 시작한다. 고른 경로는
   버튼 옆에 표시된다.
3. **detect**는 소스를 읽어 폰트 표를 채운다.

앱에서는 페이지에 "paths, one absolute path per line" 상자도 "output folder" 텍스트 상자도 없다. 셸의 대화상자가 있으면
페이지가 이를 숨기기 때문이다. 셸 없이 페이지를 열었을 때(예: 브라우저에서 연 서버, [../maker/README.ko.md](../maker/README.ko.md)
참조)에만 나타나며, 그때는 절대 경로를 직접 입력한다.

모든 경로는 검사된다. 절대 경로여야 하고, 심볼릭 링크가 아니어야 하며, 앱 자신의 데이터 폴더가 아니어야 하고, 출력
폴더나 다른 소스와 겹치지 않아야 하며, `SVF_MAKER_ROOTS`가 설정되어 있으면 그 폴더들 중 하나 안에 있어야 한다
(출력 폴더도 마찬가지다. `SVF_MAKER_ROOTS=$HOME/fonts:$HOME/svf-out`이면 `~/fonts` 아래의 소스와 `~/svf-out` 아래의 출력 폴더를
허용한다. 어떤 루트에도 속하지 않는 출력 폴더는 `output folder: outside SVF_MAKER_ROOTS`로 거부된다). 거부된 경로는 이유와 함께
나열된다(11절).

작업이 살아 있는 동안 앱은 중간 파일을 출력 폴더 안의 `.svf-maker-<id>/`(권한 0700)에 두고, 작업이 끝나거나 삭제되거나
앱이 종료될 때 지운다. 클라우드 클라이언트가 **동기화하지 않는** 출력 폴더를 고른다.

패널 아래의 **jobs**는 이 세션의 작업을 나열하므로 작업 사이를 전환할 수 있다.

### 3.3 폰트 표(설정 아래, 전체 너비)

감지 후에는 모든 폰트(또는 컬렉션의 모든 페이스)가 한 행이 된다: 그 파일, 패밀리와 스타일, 종류(4절 참조), 폰트가
비트맵이면 제공하는 픽셀 크기, 행별 포함 체크 상자, 그리고 WASM 렌더러가 그린 한글 음절 미리보기이다. 경로가 없는
행은 비활성화되고 체크 해제된 채로 남으며 이유가 표시된다(예: 짝이 되는 표가 없는 한글 폰트). 페이지는 거부된 파일
(폰트가 아님, 읽을 수 없음, 규칙 밖)도 숨기지 않고 "refused" 목록에 나열한다.

열은 id, use, preview, label, family/style, sizes, coverage, jamo, licence, layout, override이다.

- **use**는 그 행을 실행에 포함한다. 행은 그 폰트와 함께 라이선스 파일이 발견된 경우에만 미리 체크된다. DOS raw 폰트는 배치를 먼저
  확인해야 하므로 절대 미리 체크되지 않는다.
- **layout**은 DOS raw 폰트 전용 컨트롤이다. 감지기가 그 파일 크기에 대해 찾은 후보 배치(`844` 같은 배치 이름) 중 하나를 고를 때까지
  "confirm"으로 표시된다. 하나를 고르기 전에는 "confirm the DOS Johab layout"으로 실행이 거부되고, 원본 페이스도 그려지지 않는다. 다른
  종류의 폰트에서는 이 칸에 줄표가 표시된다.
- **override**는 행 아래에 폰트별 패널을 연다. 이 폰트 하나에 대해 일괄 컨트롤(dest, kinds, layout, sizes, bpp, range, preset. 빈 값은
  "(batch)"를 뜻한다)을 반복하고 다음을 더한다: **jamo route**(5절의 경로 중 이 폰트의 jamo 페이스를 만드는 것. "(default)"는 첫
  번째 기본(native) 경로이며 `vector fit`에는 "minutes per font"라고 표시된다); **precomposed route**(SVF 소스에만:
  `copy` 또는 SVF의 TTF / BDF만 쓰는 `svf2ttf`); **also write**(이 폰트만의 TTF / BDF 선택: "(batch)" 또는 on / off); **experimental**(experimental로 표시된 경로를
  허용한다. 꺼 두면 그것이 필요한 경로는 나열되지만 "needs experimental"이라는 이유로 거부된다); **latin companion**(Latin 글자를
  더해 줄 일괄 안의 BDF 또는 HBF. Mac 7.1 `fbit`에는 그 크기의 strike가 있는 suitcase); **HTBL table**(Mac 7.1 `fbit`의 조합
  표); **instance**(가변 폰트의 이름 붙은 인스턴스); **licence name**과 **note name**; **advanced options**(3.4절의 고급 패널,
  이 폰트에만); 글리프별 수직 이동 편집기와 출력 이름.

### 3.4 일괄 설정(왼쪽 열의 오른쪽)

하나의 설정 묶음이 일괄 전체에 적용되며, 행은 제외를 선택할 수 있다.

| 컨트롤 | 의미 |
|---|---|
| dest | 페이스가 들어갈, 출력의 `svf/` 트리 아래 하위 폴더. 다음 형식만 받아들인다: `dos`, `jamo-extra`, `games/<name>`, `new/<name>`. `<name>`은 소문자, 숫자, `-`이다(예: `new/my-set`). 목록에서 고르거나 "new..."를 골라 `new/<name>`을 입력한다. `my/set` 같은 이름은 거부된다. |
| kinds | **precomposed**: 음절마다 가변 폭 글리프 하나(SVF v3). **jamo**: 자모 조각을 담고 그릴 때 음절을 조합하는 페이스(JSET 블록). 하나 또는 둘 다 체크한다. |
| layout | jamo용: 조각 배치(예: `844`, `adaptive`, `621`, 또는 소스가 필요로 할 때 Mac 또는 Hanterm 배치). |
| sizes | 생성할 픽셀 크기, 예: `16, 20`. 비트맵 폰트는 자신이 담고 있는 크기만 제공한다. |
| bpp | 픽셀당 1비트 또는 2비트. 하나 또는 둘 다 체크한다. |
| range | 포함할 문자 집합. |
| preset | 이름 붙은 레시피(5절). "plain"은 도구의 기본값을 쓴다. |
| also write TTF / BDF | 실행이 만드는 모든 페이스를 SVF 옆에 `<NAME>.ttf`(페이스의 픽셀을 아웃라인으로, 비트맵 strike를 내장한 TrueType 폰트)와/또는 `<NAME>.bdf`로도 쓴다. `tools/svf2ttf.py`가 만든다([recipes.ko.md](recipes.ko.md)의 "SVF 페이스를 TTF 비트맵 폰트로"). 기본은 꺼짐이며, 폰트의 override에서 그 폰트만 켜거나 끌 수 있다. **TTF as composites**(기본 꺼짐)는 자모 세트의 TTF를 `--composite`로 쓴다: 조각을 한 번씩 글리프로 두고 모든 음절을 그 조각의 합성 글리프로 만든다(레시피가 설명하듯 더 작다). 완성형 페이스의 TTF는 그대로이다. |
| advanced panel | 세부 컨트롤: cell, ascent, width, space advance, mono hint, clip cell, fit cell, Latin top, embolden, symbols, JSET version, header ascent, fit baseline, AA refine, clean noise, binarize(threshold, ridge, mono), Latin ascent, Hangul ascent. 여기의 값이 프리셋의 값보다 우선한다. 경로가 쓸 수 없는 컨트롤은 숨겨지거나 비활성화된다. |

### 3.5 상단 바의 버튼

| 버튼 | 동작 |
|---|---|
| save settings | 현재 설정을 작업에 저장한다(확인을 위해 다시 읽어 오기도 한다). |
| run | (설정을 바꿨다면) 먼저 현재 설정을 저장한 다음 작업을 대기열에 넣는다. 상태 줄에 작업의 상태가 표시되며, 서버가 바쁘면 순번도 표시된다. |
| cancel | 실행 중인 작업을 중지하고 그 도구 프로세스를 종료한다. |
| edit and re-run | 실행 후 같은 소스로 설정 화면으로 돌아간다. |
| open folder | 출력 폴더를 시스템 파일 관리자에 표시한다(이 앱에서 직접 고른 폴더에 한함). |
| download zip | 일반 웹 페이지의 업로드 모드에서 쓰인다. 데스크톱 앱은 대신 출력 폴더에 쓰며 zip이 없다. |
| delete job | 작업을 잊고 그 출력 폴더를 해제한다. 이미 쓰인 페이스는 남는다. |

### 3.6 단계 표(아래)

각 작업은 단계(detect, convert, check, preview...)의 목록이다. 열은 id, font, kind, size, bpp, name, state, seconds,
quality, stderr, result이므로 어떤 폰트에 어떤 단계가 실행되었고 무엇을 출력했는지 볼 수 있다. 페이스의 TTF / BDF는 페이스 바로
뒤의 별도 단계(kind `export`)이다. 그 result 칸은 파일이 담은 글리프 수(다시 읽어 페이스의 문자와 대조한 것)와 쓰인 위치를 보여 주며,
페이스 단계가 실패하면 그 export는 "face step failed"로 실패한다. 명령 자체는 이 표에 없다. 출력 폴더의
`build-<id>/BUILD.md`가 무엇을 어떤 명령으로 실행했는지 나열한다([경로 표](recipes.ko.md#데스크톱-앱과-maker-경로)). 모든 결과 페이스는 렌더러가 캔버스에 그리므로 무엇이 만들어졌는지
볼 수 있다. (캔버스에 잉크가 있다는 것은 저장소의 테스트가 단언하는 것이지 앱이 검사하는 것이 아니다.)

## 4. 앱이 이해하는 입력

| 입력 | 비고 |
|---|---|
| TrueType, OpenType, 컬렉션(`.ttf`, `.otf`, `.ttc`), 가변 폰트 | 아웃라인 폰트. 가변 폰트는 사용자가 고른 인스턴스로 변환된다. |
| BDF, PCF 비트맵 폰트 | ISO 10646(비트맵 페이스, `mkfont`로 변환), KS C 5601과 Johab BDF(한글 페이스). |
| HBF 폰트와 ISO 8859 BDF | 그 자체로는 변환되지 않는다. 자신만의 경로가 없다. KS C 5601 BDF 한글 폰트(`bdfface` 경로)의 **Latin 짝(companion)**으로만 제시된다. |
| DOS raw 한글 폰트 | Johab 8x4x4 / 6x2x1 방식의 raw 폰트(및 24 px HBIOS), 그리고 헤더 없는 KS X 1001 음절 덤프(태백 `GHAN24.PFT`). 12x24 영문 폰트(`GASCII24.PFT`)는 24 px 페이스의 짝(companion)으로 쓰인다. |
| HWP 폰트(로컬 모드) | HWP 1.x `HANGUL.SFT` / `HANGULn.PFT`(파일마다 페이스 셋, HWP 자체 규칙의 자모 세트 또는 완성형 페이스)와 `ASCII.SFT` / `ASCII.PFT`; HWP 3.0 `HAN*.FNT`와 `ENG*.FNT`. `.HFT` 윤곽선 폰트는 읽지 않는다. |
| 클래식 Mac HangulTalk 7.1 type-3 `fbit` | 리소스 포크, AppleDouble `._Name`, MacBinary `.bin`, JM 아카이브, 또는 raw `fbit` 리소스에서 읽는다. HTBL 1 표(`InputBackSupport` 또는 `<Name>.htbl1`, 다른 소스로 함께 선택)가 필요하며 Latin suitcase(FOND + NFNT)를 쓸 수도 있다. |
| 클래식 Mac HangulTalk 1.0 폰트 | `fdef`가 있는 포크. `fdef` 없는 raw 1.0 `fbit`는 무엇이 빠졌는지와 함께 목록에 표시된다. |
| Hanterm Johab 폰트 | 배치 `hanterm-johab`(Johab BDF). |
| SVF 파일(`.svf`) | 복사되거나(경로가 허용할 때) jamo fit의 소스로 쓰인다. 업로드한 SVF는 자신의 JSET 블록을 유지한다. `svf2ttf` 경로는 SVF를 TTF와/또는 BDF로만 바꾼다("also write TTF" 또는 "BDF"를 체크한다). |
| 알려진 ROM 세트(로컬 모드) | `maker/recipes/`의 내장 레시피에서 크기와 SHA-256으로 알아보는 글꼴 ROM: 86Box의 한글 VGA 카드 셋, 각각 512 KB KS C 5601 글꼴 ROM과 32 KB VGA BIOS(Trigem `tg_ksc5601.rom` + `tgkorvga.bin`, Kasan `kasan_ksc5601.rom` + `et4000_kasan16.bin`, ATI `ati_ksc5601.rom` + `atikorvga.bin`). 두 파일이 든 폴더를 고른다. 글꼴 ROM이 "known: <카드>" 한 행이 되고 BIOS는 그것과 함께 읽힌다고 표시된다. 한 파일만 있으면 행은 "part of <카드>: also needs <파일>; pick the folder"라고 하며 아무것도 제시하지 않는다. 이름과 크기는 맞지만 해시가 다른 파일은 "looks like <카드>, another revision"이며 변환하지 않는다. 페이스는 16 px 완성형 페이스(한글은 ROM에서, 영문은 BIOS의 8x16 글꼴에서)와 experimental인 8x4x4 자모 fit이다([recipes.ko.md](recipes.ko.md)의 "한글 VGA 글꼴 ROM (86Box)"). MAME 세트 넷도 같은 방식이다(풀어 둔 세트의 폴더를 고른다. zip은 읽지 않는다): 삼성 SPC-1500(`ss150fnt.bin` .. `ss153fnt.bin`: 완성형 페이스와 정확한 자모 세트, 경로 `spec`), Date Quiz Go Go(`uor1` .. `uor4`), X Se Dae Quiz(`obj-1.u0811`, `obj-2.u082`: 자모 세트, 경로 `dos raw`), Quiz King of Fighters(한국판)(`vic-080-c1.c1` .. `c4.c4`)([recipes.ko.md](recipes.ko.md)의 "MAME 세트의 한글 폰트 ROM"). 업로드 작업은 표시만 한다. |

독점 폰트, 비트맵, 표는 앱과 함께 배포되지 않는다. 테스트는 합성 입력을 쓴다.

폰트 옆의 라이선스 파일은 그것도 함께 선택된 경우(또는 폴더 전체가 선택된 경우)에만 쓰인다. 앱은 사용자가 선택한
라이선스를 페이스의 note에 기록할 수 있지만, 어떤 폰트를 변환해도 자유롭다고 스스로 판단하는 일은 없다.

## 5. 경로와 프리셋

각 폰트에 대해 maker는 그 종류에 맞는 경로를 제시한다. 경로는 저장소 도구의 고정된 순서열이다. (experimental)로 표시된 경로는 폰트의
**experimental** 상자를 체크했을 때만 쓸 수 있고, 나머지는 기본(native) 경로이다.

| 종류 | 경로 |
|---|---|
| precomposed | `mkfont`(아웃라인 또는 ISO 10646 비트맵에서 SVF로); `johab844`(DOS raw, 16 px); `bdfface`(KS C 5601 BDF와 Latin 짝, 또는 알려진 ROM 세트에서 잘라 낸 한글과 영문); `mac fbit 7.1 bdf + mkfont`; `copy`(SVF를 그대로); `svf2ttf`(SVF를 TTF / BDF로만) |
| jamo | `spec`(알려진 세트의 정확한 자모 세트: SPC-1500); `composite`(합성 글리프 아웃라인 폰트); `experimental fit`(아웃라인 폰트, 1 또는 2 bpp, 느림, 품질 제약, experimental); `mask fit`(1 bpp, experimental, `freetype-py`, `uharfbuzz`, OpenType 자모 치환이 있는 마스크 폰트 필요, 9절 참조); `vector fit`(experimental, 폰트당 수 분 소요); `dos raw`; `hanterm`; `mac fbit 1.0`; `mac fbit 7.1 direct`(native)와 `derived`(experimental); `bdfface + from-svf fit`과 `from-svf fit`(experimental); `copy`(이미 자모 조각이 있는 SVF); `svf2ttf`(자모 SVF를 TTF / BDF로만) |

프리셋은 이름 붙은 출발점이다. 고급 패널이 프리셋을 덮어쓴다.

| 프리셋 | 레시피 | 재현 대상 |
|---|---|---|
| `plain` | 도구의 기본값 | |
| `dos-l-1bpp` | cell 16, 1 bpp, ASCII + 한자 제외 KS X 1001 + 추가 8자 | `svf/dos/NEODG16.SVF`(배포 파일보다 글리프 하나 적음) |
| `dos-u-2bpp` | cell 16, 2 bpp, clip cell, ascent size-2 | `svf/dos/GBATB17.SVF`(크기 17에서 바이트 단위로 동일), `NGOTB16.SVF`(글리프 하나 적음) |
| `latin-18cell-2bpp` | cell 18, width 18, 2 bpp, 나열한 문자만 | `svf/dos/PAPLG16.SVF` |
| `jamo-844`, `jamo-844-symbols`, `jamo-844-hbios24`, `jamo-621` | DOS raw 폰트에서 나온 jamo 배치 | `maker/presets.py`에 이름이 붙은 배치 |

## 6. 실행이 쓰는 것

출력 폴더 안에만 쓰며, 그 밖에는 아무것도 쓰지 않는다.

    <output>/
      svf/<dest>/<NAME>.SVF          the face
      svf/<dest>/<NAME>.ttf, .bdf    its TTF / BDF, when "also write" asks for them (the svf2ttf route: these only)
      svf/<dest>/<NAME>.TXT          its note (how it was made, the licence you chose or "not checked")
      svf/<dest>/<licence file>      when a licence text was chosen
      build-<id>/
        BUILD.md                     what was converted, with which commands
        LICENCES.tsv.lines           lines for the repository's web/LICENCES.tsv
        FAMILIES.tsv.lines           lines for its families table
        FACES.TSV.lines              lines for its faces table

- 작업이 직접 쓰지 않은 이름은 절대 대체되지 않는다. 파일이 이미 있으면 실행은 건너뛰거나 거부하며, 사용자의 파일을
  덮어쓰지 않는다. `.ttf` / `.bdf`에도 같은 규칙이 적용된다.
- TTF / BDF는 작업이 그 폰트에 대해 아는 라이선스(사용자가 고른 라이선스 파일과, 그 파일이 이름을 든 `.TXT` 중 사용자가 함께
  고른 것. CP949 라이선스는 CP949로 읽고, 그 밖의 UTF-8이 아닌 라이선스는 읽을 수 없는 바이트를 바꾸어 담는다. 고르지 않은 파일이나 고른 폴더 밖으로 가는 링크는 읽지 않는다. `svf2ttf`로 바꾸는 SVF에 라이선스를 고르지 않았으면 고른 파일 중
  그 옆의 노트를 쓴다. 고른 파일만 보므로 저장소의 `svf/` 트리에서 고른 페이스라도 `svf2ttf.py`를 직접 실행할 때처럼 `web/LICENCES.tsv`가
  지정하는 파일을 받지 않는다. 그 행에서 라이선스 파일을 고른다)를 이름 표나 `COMMENT` 줄에 담는다. 라이선스가
  없으면 원본 폰트의 라이선스가 적용된다고 적는다. `BUILD.md`에는 나열되지만(`svf2ttf.py` 명령과 "written" 줄) `.lines` 파일의
  행은 없고 페이스의 노트에도 이름이 오르지 않는다. 그것들은 SVF 페이스를 설명한다. 타임스탬프는 현재 시각이며, 앱을
  `SOURCE_DATE_EPOCH`를 설정한 채 시작했으면 그 값이다.
- `.lines` 파일은 사용자가 저장소의 표에 손으로 병합하는 조각이다(저장소의 `web/mkindex.py --check`가 병합된 결과를
  받아들인다).
- 페이지는 쓰인 모든 페이스를 렌더러로 그려 보여 준다. 저장소 자체의 페이스 검사(`facecheck.py`는 매니페스트와 맵 검사기이다. `web/mkindex.py --check`)는 별개이다. 저장소에
  추가하는 페이스에는 직접 실행하라(앱의 일부가 아니다).

## 7. 메뉴, 확대/축소, 창 상태

- **File**: Open output folder; Quit.
- **View**: Reload; Actual size; Zoom in과 Zoom out(Ctrl과 `+` 또는 `-`, 50%에서 300%까지).
- **Help**: About은 앱 버전, 빌드 id, Electron, Chromium, Node 버전, 사이드카의 버전과 Python, 렌더러 샌드박스 상태,
  그리고 서드파티 라이선스(`THIRD-PARTY.txt`) 버튼을 보여 준다.

셸은 `shell-state.json`에 네 가지를 기억한다: 창의 위치와 크기, 확대 배율, 마지막 출력 폴더, 그리고 내준 출력
폴더들(마지막 32개, 실제 경로로 저장하며 이것들만 "Open output folder"로 열 수 있다). 토큰과 입력 경로는 저장하지
않는다.

## 8. 프라이버시와 보안

- **네트워크 없음.** 페이지의 Content-Security-Policy는 자기 origin만 허용한다. 셸은 사이드카로 가지 않는 모든 요청을
  취소한다(새 창, 탐색, 다운로드, 장치 및 권한 요청은 모두 거부된다). maker 자체 코드는 네트워크 라이브러리를 import하지
  않는다. 텔레메트리, 충돌 업로드, 업데이트 확인은 없다.
- **토큰.** 사이드카는 실행할 때마다 새 임의 토큰으로 시작한다. 셸이 이를 페이지의 `/api/` 요청에 `X-Maker-Token`으로
  덧붙이며, 페이지 자신은 토큰을 보지 못한다. 모든 요청은 이 서버의 `Host`도 실어야 한다. 서버는 loopback에만
  바인딩되며 그 밖의 것은 거부한다.
- **브리지.** 페이지는 네 함수가 있는 `window.svfMaker`를 받는다: `pickFiles()`, `pickFolder()`, `pickOutputDir()`,
  `openOutputFolder()`(그리고 읽기 전용 `platform`). 셸은 maker 자신의 origin의 프레임에만 응답한다. 경로는
  절대 경로이며, 취소된 대화상자는 빈 목록 또는 `null`을 반환한다.
- **파일.** 폰트는 제자리에서 읽히며 수정되지 않는다. 출력은 사용자가 고른 폴더 아래에만 쓰인다.
- **샌드박스.** 페이지는 context isolation, Node 통합 없음, 샌드박스된 preload로 실행된다. 시스템이 사용자
  네임스페이스를 거부하는 곳에서는 Chromium 자체의 프로세스 샌드박스가 **꺼진다**(AppImage는 SUID 헬퍼를 담을 수
  없다). 그 경우 렌더러는 loopback의 앱 자신의 페이지만 로드한다.
- **프로세스.** 각 도구는 자신의 세션에서 실행되고 `tools.pids`에 기록된다. 앱을 종료하거나 충돌이 나도 실행 중인 도구가
  남지 않는다(다음 시작 때 남은 것을 정리한다). Windows에서는 각 도구가 자기 Job Object 안에서 실행된다: 사이드카가 어떻게
  끝나든 Windows가 그 도구들도 함께 끝낸다.
- **Windows.** 위의 규칙은 그곳에서도 Windows의 형태로 적용된다(maker-desktop.ko.md, "Windows에서 다른 것"): 정션이나 마운트 지점은
  링크로 보고 심볼릭 링크처럼 거부한다. Windows가 예약한 출력 이름(`CON`, `NUL.TXT`, `COM1`, ...)은 거부한다. 페이스를 쓰는 동안
  출력 폴더와 쓰기가 지나가는 모든 폴더를 연 채로 두어 그 사이에 누구도 이름을 바꾸거나 지울 수 없다. 데이터 폴더의 비공개는
  사용자 프로필에서 물려받은 폴더 권한(ACL)이다: Windows에는 `chmod 700`이 없다.
- **서드파티 코드.** `THIRD-PARTY.txt`는 번들된 모든 라이브러리를 그 라이선스와 함께 나열한다. 출처 표기가 없거나 GPL인
  라이브러리가 있으면 빌드가 실패한다.

## 9. 파일 위치, 로그, 환경 변수

| 항목 | 위치 |
|---|---|
| 앱 데이터(작업, 작업 파일, `instance.lock`, `tools.pids`) | `~/.config/svf-maker/maker`(앱의 user-data 폴더에 `maker`를 더한 것) |
| 창 상태 | `~/.config/svf-maker/shell-state.json` |
| 셸 로그 | `~/.config/svf-maker/logs/shell.log`(그리고 순환된 `shell.log.1`. redaction 규칙이 허용하는 것 이상의 폰트 이름이나 경로는 없으며, 토큰은 절대 없다) |
| 개발 실행 데이터 | `~/.config/svf-maker/maker-dev` |
| Windows | 같은 이름으로 `%APPDATA%\svf-maker\` 아래(`maker\`, `shell-state.json`, `logs\shell.log`, `maker-dev\`). 설치된 프로그램은 `%LOCALAPPDATA%\Programs\svf-maker\`에 있다 |

선택적 환경 변수(앱을 시작하기 전에 설정한다):

| 변수 | 효과 |
|---|---|
| `JAMOSET_PYLIB` | `freetype-py`와 `uharfbuzz`가 있는 폴더. `mask fit` 경로와 `binarize mono`를 활성화한다. |
| `JAMOSET_MASK_FONT` | `mask fit`이 조각을 한정하는 데 쓰는, OpenType 자모 치환(`ljmo`, `vjmo`, `tjmo`)이 있는 폰트 파일. 없으면 도구는 ScummVM 트리 옆의 NotoSansKR을 찾는데 패키지된 앱에는 그것이 없으므로, `mask fit`을 쓸 때는 지정한다. |
| `SVF_MAKER_ROOTS` | 콜론으로 구분한 절대 경로 폴더들(Windows에서는 세미콜론으로 구분: `C:\fonts;D:\out`). 모든 소스와 **출력 폴더**가 이 중 하나 안에 있어야 한다(밖의 경로는 "outside SVF_MAKER_ROOTS"로 거부된다). 루트를 나눈 예: `SVF_MAKER_ROOTS=$HOME/fonts:$HOME/svf-out ./svf-maker-0.1.0.AppImage`. 설정하지 않으면 3.2절의 규칙 외에 제한이 없다. |
| `SVF_RECOG_PYTHON` + `SVF_RECOG_DIR` | 인터프리터(절대 경로, numpy, torch, PIL, fontTools 포함)와, 조각 정체성 검사를 위한 사용자 자신의 `recog.py`가 있는 폴더. 점수 계산 전용이며 아무것도 함께 배포되지 않는다. 이것이 없으면 페이지는 검사를 쓸 수 없다고 표시한다. |
| `SVF_MAKER_DEV=1` | 개발 모드: frozen 사이드카 대신 체크아웃에서 `python3 maker/server.py`를 실행한다. `SVF_MAKER_DEV_REPO`가 체크아웃을 지정한다. |
| `SVF_MAKER_DEVTOOLS=1` | 개발자 도구와 View > Toggle DevTools 항목을 활성화한다. |
| `SVF_MAKER_SHELL_LOG=stderr` | 셸 로그가 표준 오류에도 출력된다. |
| `SVF_MAKER_SMOKE=1` | 시작하고, `/api/caps`를 확인하고, 한 줄을 출력한 뒤 종료한다(릴리스 점검에서 사용). |

## 10. 실패 처리

- **서버가 시작하지 못함**(오류 대화상자 후 앱 종료): 대화상자에 서버 출력의 마지막 줄들이 표시된다. 다른 maker가 아직
  종료 중이면 잠시 기다렸다가 다시 시작한다.
- **앱이 실행 중일 때 서버가 멈춤**: 대화상자가 Restart 또는 Quit를 제안한다. 재시작에는 횟수 제한이 있으며, 짧은 시간에
  너무 많이 재시작하면 앱이 종료된다.
- **창이 충돌함**: 앱은 같은 페이지를 한 번 다시 로드하며, 두 번째 충돌이 나면 메시지를 보여 주고 종료한다.
- **종료**: 셸은 사이드카에 중지를 요청하고(최대 45초) 실행 중인 작업을 취소하며 그 도구 프로세스를 종료한다. 그 시점에
  대기 중이거나 실행 중이던 작업은 작업 파일이 프로세스와 함께 사라지므로 실패(`interrupted`)로 표시된다. 출력 폴더에
  이미 쓰인 페이스는 남는다.
- **디스크 가득 참, 특이한 파일 시스템, 대소문자를 구분하지 않는 디스크, 동기화 클라이언트**: 테스트하지 않았다(아래
  참조).

## 11. 볼 수 있는 메시지

페이지는 서버가 거부하는 모든 것에 대해 상단 바 아래에 메시지 줄을 보여 준다. 줄의 형식은
`METHOD /api/...: HTTP <status>: <text>`이다. 아래 문장은 서버 자신의 문장이다.

**서버가 바쁨(바쁨 종류가 붙은 HTTP 409).** 여러 동작이, 다른 요청(같은 작업의 두 번째 창, 만들어지는 중인 미리 보기, 준비되는 중인
실행)이 바꾸고 있는 작업과 마주칠 수 있다. 이 응답은 설정 오류가 아니다.

- 페이지는 같은 요청을 0.5초, 1초, 2초 뒤에 스스로 반복한다(최대 세 번, 전체로 15초를 넘기지 않음). 이때 줄 끝에 ` (retrying 1/3)`이
  붙는다. 그래도 실패하면 메시지가 남고 **Try again** 버튼이 나타나며, 이 버튼은 같은 요청을 한 번 더 보낸다. 다른 것을 시작하면
  메시지와 재시도가 지워진다.
- `job <id> is busy; try again`, `job <id>: the previous run is finishing; try again in a moment`,
  `job <id> is busy: a preview is being made; try again`: 잠금이 잠깐 잡혀 있다. 자동 재시도가 보통 해소한다. 예외
  하나: 작업을 만드는 동안 **detect**가 답할 수 있는 `job <id> is busy; try again`은 재시도 가능으로 태그되지 않으므로 페이지가 재시도하지 않고
  **Try again** 버튼도 없다. **detect**를 다시 누른다.
- `a run of job <id> is being prepared`: 이 작업의 다른 창이 방금 run을 눌렀을 때 **run**이 받는 답이다. 페이지는 실행을 반복하지 않고(첫
  번째와 경합하게 되므로) **Try again**을 보여 주면서 다른 실행을 **따라간다**. 15초까지 1초마다 작업을 읽어서, 작업이 "detected" 상태를
  벗어나면 그 작업의 진행 상황을 보여 주고 메시지를 지운다. (준비 중에 요청한 미리 보기는 같은 문장에 `; try again`이 붙은 답을 받고
  자동으로 재시도된다.)
- `the job changed while the run was being prepared: run again`: 저장과 실행 시작 사이에 설정이 바뀌었다(예: 다른 창에서). 페이지는
  작업을 다시 읽어 저장된 상태를 보여 준다. 설정을 확인하고 **run**을 다시 누른다.
- `job <id> is queued`(또는 running): 다른 곳에서 실행이 시작되어 작업을 더는 편집할 수 없다. 페이지는 그 작업의 상태를 보여 준다.
  **편집한 내용은 입력한 그대로 폼에 남는다**(페이지는 초안을 버리지 않는다). 다만 편집하고 다시 실행하기 전까지는 저장되지 않는다.

**폴더와 경로.**

- `output folder is in use by job <id> (delete it, or wait until it has been idle for 30 minutes)`(실행 시에는 더 짧은
  `output folder is in use by job <id>`): 출력 폴더는 한 번에 한 작업만
  쥘 수 있다. 작업 목록에서 다른 작업을 삭제하거나(이미 쓰인 페이스는 남는다) 다른 폴더를 고른다. 감지만 되고 30분 동안 손대지 않은
  작업은 스스로 폴더를 내놓는다.
- `the files directory is still being moved or made on a slow or hung volume; try again later`: 작업의 `.svf-maker-<id>/` 폴더를
  지우거나 만드는 일이 아직 진행 중이다(느린 디스크, 네트워크 마운트, 동기화 클라이언트). 기다렸다가 다시 시도하거나, 로컬의
  동기화하지 않는 폴더를 쓴다.
- `cleanup pending: the earlier files of job <id> are still being removed; try again later`: 이전 세션의 작업이 재시작 후에도 아직 정리되는
  중이다.
- `output folder is gone or changed`: 작업이 쓰는 동안 출력 폴더가 옮겨지거나, 교체되거나, 마운트 해제되었다. 다시 고른다.
- "refused" 목록(또는 안내)의 경로에는 다음 이유 중 하나가 붙는다: `not an absolute path`, `path too long`, `NUL in path`,
  `no such file or folder`, `the path is a symlink`, `/ cannot be chosen`, `not a regular file or folder`(소스), `not a folder`(출력),
  `the data folder cannot be chosen`, `outside SVF_MAKER_ROOTS`, `the output folder must not overlap an input`,
  `overlaps another input`. 링크 대신 실제 경로를 고르고, 출력 폴더를 소스와 떨어뜨려 둔다.
- `confirm the DOS Johab layout`: 행에서 DOS raw 폰트의 배치를 고른다(3.3절).

## 12. 복구, 데스크톱 통합, 제거

**AppImage가 시작되지 않는다.**

- *FUSE 없음.* AppImage 자신의 runtime이 FUSE 코드를 담고 있으며 `fusermount` 또는 `fusermount3`(패키지 `fuse3`, Ubuntu 24.04에는
  있음)만 필요하다. 둘 다 없거나 마운트가 허용되지 않으면(컨테이너, 잠긴 시스템) `fuse3`를 설치하거나, 이미지를 마운트하지 않고 실행한다.

      ./svf-maker-0.1.0.AppImage --appimage-extract       # writes ./squashfs-root/
      ./squashfs-root/AppRun

  `squashfs-root/AppRun`은 같은 런처이며, AppImage 대신 그 폴더를 보관해도 된다.
- *디스플레이 없음, 또는 X 권한(authority) 없음.* 메시지 `Missing X server or $DISPLAY`(또는 Electron이 디스플레이를 열지 못함)는 이 셸에
  그래픽 세션이 없다는 뜻이다. 데스크톱 세션에서 앱을 실행한다. `ssh`로는 X 포워딩을 쓰거나, `$DISPLAY`가 설정되어 있고 `$XAUTHORITY`가
  세션의 권한 파일을 가리키는지 확인한다(`xauth list`). 화면 없는 머신에서는 `xvfb-run -a ./svf-maker-0.1.0.AppImage`로 가상
  디스플레이에서 실행할 수 있지만 그러면 쓸 수 없다.
- */tmp에서 실행이 가능해야 한다.* AppImage는 `/tmp/.mount_*` 아래에 스스로를 마운트하고 거기서 프로그램을 실행한다. `/tmp`가 `noexec`로
  마운트되어 있으면 시작이 실패한다(보통 "permission denied" 메시지. 여기서 재현하지는 않았다). `/tmp`를 `noexec` 없이 다시
  마운트하거나, `--appimage-extract`를 쓰고 실행이 허용되는 곳에서 `squashfs-root/AppRun`을 실행한다.
- *샌드박스 없음.* 권한 없는 사용자 네임스페이스를 쓸 수 없으면 런처가 이를 알아차리고(`unshare -Ur true`를 테스트한다) 스스로 `--no-sandbox`를
  붙인다. 사용자가 할 일은 없다. 그러면 Help > About에 "renderer sandbox: off"가 표시된다.
- *그 밖의 경우.* 터미널에서 `SVF_MAKER_SHELL_LOG=stderr ./svf-maker-0.1.0.AppImage`로 시작해 메시지를 읽고,
  `~/.config/svf-maker/logs/shell.log`도 본다.

**데스크톱 통합.** AppImage는 메뉴나 아이콘 폴더에 아무것도 넣지 않으며 어디에도 설치되지 않는다. 런처를 만들려면
`~/.local/share/applications/svf-maker.desktop` 파일을 직접 쓴다.

    [Desktop Entry]
    Type=Application
    Name=SVF maker
    Exec=/home/you/Apps/svf-maker-0.1.0.AppImage %U
    Terminal=false
    Categories=Utility;

(AppImage의 실제 절대 경로를 쓴다. 아이콘을 원하면 체크아웃의 `desktop/build/icon.png`에 대한 절대 경로로 `Icon=`을 추가한다.) 또는
이미지 안의 항목을 읽는 AppImageLauncher 같은 AppImage 관리자를 쓴다. 이미지 안에서는 `Exec=AppRun %U`가 항목이며 `AppRun`이 필요할 때
스스로 `--no-sandbox`를 붙인다.

**Windows.** 앱이 시작하지 않으면 `%APPDATA%\svf-maker\logs\shell.log`를 읽는다. 메시지를 바로 보려면 PowerShell 창에서
먼저 `$env:SVF_MAKER_SHELL_LOG='stderr'`를 설정하고 시작한다. SmartScreen의 "Windows의 PC 보호"는 서명 없는 패키지 때문이다(빠른
시작). 제거: 설정 > 앱 > SVF maker(또는 "프로그램 추가/제거"), 또는 포터블 파일을 지운다. 그다음 `%APPDATA%\svf-maker\`를 지우면
데이터, 로그, Chromium 프로필이 지워진다. 출력 폴더의 페이스는 남는다.

**제거.** AppImage 파일을 삭제한다. 앱의 데이터는 `~/.config/svf-maker/` 아래에 있다: 작업과 작업 파일(`maker/`, `maker-dev/`),
`shell-state.json`, `logs/shell.log`, 그리고 Electron 셸이 같은 폴더에 두는 Chromium 자신의 프로필 데이터(캐시, 로컬 저장소 등). 흔적을 모두
없애려면 `~/.config/svf-maker/`도 삭제한다. 출력 폴더에 이미 쓰인 페이스는 사용자의 것이며 그대로 남는다.

## 13. 한계와 검증되지 않은 것

- 2026-11-22에 검증함: 커밋 3d40de8로 빌드한 AppImage가 깨끗한 호스트(Ubuntu 24.04.5, `libfuse2` 없음)에서 Xvfb 아래에서 시작되었고,
  창이 그려졌으며 로컬 모드 변환이 패키지된 사이드카를 통해 실행되었다. 아직 검증하지 않음: 창 관리자와 GPU가 있는 실제 데스크톱,
  Windows와 macOS.
- Windows x64(t_9b8f56f0): GitHub Actions `windows-latest`(Windows Server, 데스크톱 앞의 사용자 없음)에서 빌드하고 테스트했다.
  그곳에서 검증한 것: Windows에서의 maker와 tools 테스트 스위트(1,277개와 980개, 실패 0. 건너뛴 것은 maker-desktop.ko.md에 있다), frozen 사이드카의 테스트, 데스크톱 단위 테스트,
  개발 서버와 패키지된 사이드카에 대한 데스크톱 end-to-end 테스트(대화상자는 스텁), 사용자별 무인 설치와 제거, 그리고 풀어 둔 앱,
  설치된 앱, 포터블 앱이 패키지된 사이드카로 페이지를 로드하고 깨끗하게 멈추는 시작. **검증하지 않은 것**: 실제 Windows 10/11
  데스크톱(창을 쓰는 사람, 네이티브 대화상자, GPU 경로, 고DPI 배율), SmartScreen과 브라우저 다운로드 경고(파일에 서명이 없다),
  백신과의 상호작용, OneDrive가 동기화하는 폴더나 네트워크 공유, FAT/exFAT 출력 드라이브, 긴 경로(260자 초과), Arm용 Windows.
  서버의 검사는 Windows에서 그 Windows 형태로 지켜진다(maker-desktop.ko.md, "Windows에서 다른 것"). 그곳에서 도구 정지는 즉시다(5초
  유예 없음). Windows에서 만든 페이스는 Linux에서 만든 같은 페이스와 글리프 몇 개가 다를 수 있다(측정: GowunBatang-Bold 17 px 2 bpp의
  U+2116). 그래서 그곳에서는 그런 페이스가 수록된 페이스로 인식되지 않고 새 페이스로 쓰인다.
- macOS: 빌드하지도 실행하지도 않았다. 계획(서명, notarisation)은 [maker-desktop.ko.md](maker-desktop.ko.md)에 적혀 있다.
- TTF / BDF 내보내기: 각 파일을 다시 읽어(TTF는 fontTools로) 페이스의 문자를 정확히 담았는지 확인한다. 왕복 검사(TTF를
  `mkfont.py`로 다시 구워 비교하는 것, recipes.md)는 실행에 포함되지 않는다. 자모 세트에서는 수 분이 걸린다. 프로그램이 TTF의 2 bpp
  strike를 단계로 그리는지는 그 렌더러에 달렸다(Windows와 macOS는 테스트하지 않음).
- 알려진 ROM 세트: 실제 파일과의 대조는 `SVF_MAKER_REAL_86BOX` / `SVF_MAKER_REAL_MAME`이 사용자 자신의 사본을 가리킬 때만 한다(모든 페이스가
  recipes.md에 기록된 크기). 테스트는 OFL 페이스로 그린 합성 ROM을 쓴다.
- `mask fit` 경로는 작성자의 호스트에서 작업을 한 번도 실행한 적이 없다(그곳에는 라이브러리가 설치되어 있지 않다).
  정체성 검사는 스텁으로만 테스트했다. `vector fit`은 폰트당 수 분이 걸린다.
- 검증하지 않았으며 실제 데스크톱에서 수동으로 점검해야 한다: 디스플레이가 있는 네이티브 대화상자, 파일 관리자 연동,
  창 관리자와 함께 하는 실제 FUSE 마운트 시작, GPU 경로, 샌드박스된 렌더러. 실행한 것은 위의 Xvfb 시작이며, 자동화된
  테스트는 대화상자를 스텁으로 대체하고 GPU를 끈 채 실행한다.
- 실제 Mac, HWP, Johab 파일은 환경 변수가 사용자 자신의 사본을 가리키는 곳에서만 테스트한다. 저장소의 테스트는 합성
  입력을 쓴다.
- AppImage는 비트 단위로 재현되지 않으며 자동 업데이트도 없다. 새 버전은 새 파일이다.
