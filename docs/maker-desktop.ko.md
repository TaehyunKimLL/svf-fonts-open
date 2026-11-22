[English](maker-desktop.md) | **한국어**

# SVF maker 데스크톱 앱

maker 서버를 감싼 Electron 셸(`desktop/`)과, 이를 동결된 Python 사이드카와 함께 Linux AppImage로 패키징하는 빌드이다. 카드
t_f04f1355(셸)와 t_e64a56a7(패키징). 설계: `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`; 계획:
`docs/superpowers/plans/2026-11-05-maker-desktop.md`. 패키지는 소유자가 저장소를 공개로 돌릴 때까지 비공개이다.

## 이것이 무엇인가

- `desktop/main.js`는 실행할 때마다 새 토큰과 `127.0.0.1:0`으로 `svf-maker-sidecar serve --exit-with-parent=<pid>`(서버와 모든
  도구의 PyInstaller one-dir 번들)를 띄우고, 포트 줄을 읽고, `http://127.0.0.1:<port>/`를 불러오고, `/api/` 요청에 `X-Maker-Token`을
  직접 붙이고, 페이지에 `window.svfMaker`를 주고, 종료할 때 사이드카를 멈춘다. 사이드카 자신의 origin이 아닌 요청은 모두 취소되고,
  탐색과 새 창은 거부되고, 다운로드는 저장되지 않고, 권한은 부여되지 않는다. 네트워크 연결은 하지 않는다. 자동 업데이트도 없다.
- 사이드카는 각 도구를 `svf-maker-sidecar run-tool <name> ...`로 자기 세션에서 실행하고, `<data root>/tools.pids`에 등록하며, 시작할
  때 죽은 실행이 남긴 것을 정리한다(`maker/toolreg.py`). 데이터 루트당 서버는 하나이다(`instance.lock`). 데이터 루트는
  `~/.config/svf-maker/maker`(`<userData>/maker`)이고, 개발 실행은 `<userData>/maker-dev`를 쓴다.
- 선택적 부품은 밖에 둔다. 신원 점검은 `SVF_RECOG_DIR`와 함께 `SVF_RECOG_PYTHON` 아래에서 실행되고, 마스크 맞춤 라이브러리는
  `JAMOSET_PYLIB`에서 온다. 패키지는 그 인터프리터를 위해 `maker/*.py`와 `tools/*.py`를 소스로 싣는다.

## 빌드 (Linux)

사용자용 안내(무엇을 설치하는지, AppImage가 어디에 생기는지, 첫 실행)는 [desktop-app.ko.md](desktop-app.ko.md)의 빠른 시작이고,
이 절은 그 기록이다.

빌드 호스트의 선결 조건: git 체크아웃(스크립트가 `git log`와 `git describe`를 읽는다), emsdk(`$EMSDK`, 기본값 `~/opt/emsdk`.
`maker/build-wasm.sh`가 미리 보기 모듈을 직접 컴파일한다. 마지막으로 쓴 것은 emcc 6.0.13이며 설치는
`sh c/cross/install-toolchains.sh "$HOME/opt" emsdk`), pip이 있는 Python 3.12.3(wheel은 cp312이다. Ubuntu에서는
`python3-venv` 없이 `python3 -m venv`가 동작하지 않는다. 빌드는 `pip install --target`과 `python3 -S`를 쓴다), 시스템 `python3`용(동결 테스트와 개발 실행이 쓴다) Pillow와 fontTools(apt의 `python3-pil`, `python3-fonttools`. apt의
fontTools 4.46.0은 고정된 4.66.1보다 오래되었다. desktop-app.ko.md 참조), node 22.12 이상(apt에는 18이 있다. NodeSource나 nvm)과 npm 12
(마지막으로 22.23.4와 12.0.2), 릴리스 점검의 smoke 실행을 위한 `xvfb-run`과 `flock`(`xvfb-run`이 없으면 `smoke` 점검이 실패하고 스크립트는
종료 코드 1로 끝나지만 AppImage는 이미 `desktop/dist/`에 있다), `~/work/tmp`(브라우저 락 파일이 거기에 있다), 고정된 wheel,
Electron, AppImage 도구 세트를 위해 한 번의 네트워크 접근.

    # in the checkout root
    cd desktop && npm ci && node node_modules/electron/install.js && cd ..   # npm 12 blocks install scripts (Electron's download)
    bash desktop/build/build-appimage.sh [--release]                         # any directory; it changes to the root itself

`npm ci`는 차단된 설치 스크립트(`electron-winstaller`의 `select-7z-arch.js`)에 대한 경고를 출력한다. Linux 빌드에는 무해하다.
`~/.local/bin/heavy`는 작성자의 자원 보호 장치일 뿐 필수가 아니다. 빌드는 이것 없이도 돈다(작성자는
`~/.local/bin/heavy bash desktop/build/build-appimage.sh`로 실행한다). AppImage는
`desktop/dist/svf-maker-<version>.AppImage`이다.

마지막으로 쓴 버전(모두 고정: 해시가 있는 `desktop/build/requirements.lock`, `desktop/package-lock.json`): PyInstaller 6.22.3,
Pillow 10.2.0, fontTools 4.66.1, Electron 45.2.3, electron-builder 26.18.0.

스크래치: 스크립트는 `SVF_DESKTOP_TMP`를 받는다(기본값 `$HOME/work/tmp/svf-desktop-build`: pip 다운로드, PyInstaller 작업 디렉터리,
가지친 도구 세트, 추출물). 테스트는 `TMP_DIR`을 받는다(짧게 유지하라: `$HOME` 뒤로 약 40자 이내. Chrome의 소켓 경로는 107 바이트로
제한된다). `/tmp`는 절대 쓰지 않는다. Chrome이나 Electron을 시작하는 모든 실행은 `flock $HOME/work/tmp/svf-browser.lock`을 잡고
`~/.local/bin/heavy` 아래에서 실행한다.

`build-appimage.sh`는 `maker/build-sidecar.sh`(동결 테스트 포함, 건너뛰기 불가)를 실행하고, `THIRD-PARTY.txt`를 쓰고(출처가 밝혀지지
않은 라이브러리나 GPL 라이브러리가 있으면 실패), AppImage를 빌드하고, `desktop/build/release-check.sh`를 실행한다. 이 스크립트는
`CHECK <name> ok|FAIL` 줄을 하나씩 출력한다: size, extract, size-sidecar, layout, apprun, runtime(AppImage의 runtime은 정적이다:
로더 없음, 필요한 라이브러리 없음, `libfuse.so.2` 문자열 없음; `desktop/build/check-runtime.mjs`, `desktop/test/check-runtime.test.js`로
테스트; 그리고 `--appimage-version`이 `env -i`에서 버전 줄과 함께 0으로 종료), desktop-entry, frozen(추출된 사이드카에 대한
`test_frozen.py`, 건너뜀 0), wasm(새 빌드와 `cmp`), licences(추출물에 대한 생성기), notices와 sources(번들된 `THIRD-PARTY.txt`가 다시
생성한 것과 같음; `resources/repo/{maker,tools}/*.py`와 `resources/repo/web/mkindex.py`가 checkout과 sha256으로 같음:
`desktop/build/verify-extraction.sh`, `verify-report.sh`/`run-verify.sh`로 실행되며, 0이 아닌 종료, 없거나 중복된 결과 줄, stderr를
포함한 그 밖의 모든 출력에서 fail closed), smoke(xvfb 아래의 추출된 `AppRun`), sources(`--release`만), contents(파일 목록 기록,
`desktop/build/out/release-<build id>-<AppImage sha256 prefix>.txt`, AppImage마다 하나).

`build-appimage.sh`와 `release-check.sh`는 smoke 실행을 위해 브라우저 락을 스스로 잡는다(필요한 만큼 기다리고, 그다음 Electron 실행에
90 초를 허용한다). `~/.local/bin/heavy` 아래에서 시작하고, **`flock` 아래에서는 절대 시작하지 않는다**. 교착 상태가 된다.

### 측정값 (이 호스트, Ubuntu 24.04 x86_64, glibc 2.39)

| 항목 | 값 |
|---|---|
| 사이드카 one-dir | 47 MB; 빌드 8-9 초(동결 테스트 포함 약 30 초); 시작 후 포트 줄까지 2 초 훨씬 미만 |
| AppImage | 140 MB (133.9 MiB, 커밋 3d40de8, 2026-11-22. 정적 runtime과 zstd 이전에는 149.7 MB); `linux-unpacked` 335 MB; electron-builder 약 50 초; 캐시가 따뜻할 때 스크립트 전체 1분 26초 |
| 동결 테스트 | 테스트 26개, 건너뜀 0: `env -i`에서 고정된 wheel과 바이트 단위로 같음, 동결된 작업과 노트가 소스 모드와 같음 |
| Electron 태스크 수 (xvfb 아래 `--no-sandbox --disable-gpu`) | 인스턴스 하나 87, 두 번째 인스턴스 경우 114 (계획 단계 측정, GPU 포함 143과 170); 수명 주기 테스트의 최대값은 79-80 |
| Debian Pillow 비교 | 같음 |
| `sample set` e2e 단계 | dev 10.4 초, 패키지 15.0 초 (14단계, 페이스 10개; 락 대기가 없을 때 전체 e2e 48 초) |

### Sample set (e2e, t_30b843b8)

`desktop/test/e2e.js`에는 단계가 하나 있다. 패스마다 `sample set`이라는 단계로, 고정된 샘플을 로컬 모드에서 **페이지를 통해**
변환한다(입력은 제자리에서 읽고 페이스는 고른 출력 폴더에 씀). dev 패스와 패키지 패스에서 모두 한다. 샘플은
`maker/test/uisample.py`가 정의한다(테스트 시점에 합성 입력을 만들고, 폰트별 설정 표, 기대하는 33개 파일 트리, 점검을 소유한다).
`ttf/`의 OFL 폰트 넷을 제자리에서 읽고(neodgm, NanumGothic-Bold, `dos-u-2bpp` preset을 쓰는 GowunBatang-Bold, Bold 인스턴스의
Caveat-VF), 저장소의 fixture 빌더가 만든 합성 파일을 쓴다: HTBL 표와 suitcase가 있는 Mac 7.1 fbit, HangulTalk 1.0 폰트, Mac
dfont, `ASCII.PFT`가 있는 HWP DOS 844 폰트(`HANGUL24.PFT`는 읽지 않음으로 표시), KSC / johab BDF. 이 단계는 스텁 대화상자로 루트 9개와
출력 폴더를 고르고, 활성화된 컨트롤만 바꾸고(경로가 없는 행은 비활성에 체크 해제로 남으며 이를 assert한다), 저장하고, 저장된 설정을
다시 읽고, 실행한 다음 `uisample.py check`가 검증한다: 기대한 파일만 정확히 있고 다른 것은 없음(남은 `.svf-maker-*` 없음), 쓰인
트리에 대한 `facecheck.py`와 `web/mkindex.py --check`, 모든 페이스가 잉크를 그림, `GOWUN17A.SVF`가 `svf/dos/GBATB17.SVF`와 바이트
단위로 같음, 입력이 바뀌지 않음. 그런 다음에야 결과 캔버스 10개를 센다(`data-drawn="1"`, `Number(dataset.ink) > 0`). 패키지
패스에서는 `--same-as`가 페이스를 dev 패스와 비교한다. 순수 Python 페이스(SEOU12J, HAN224J, JOHA16J, KSC16, MUNJ16J)는 바이트
동일이 필요하다. 윤곽선 페이스(NEODU16, NANUM17A, GOWUN17A, CAVEA16, SYNTH16)의 차이는 실패가 아니라 `E2E NOTE`로 출력된다(dev
패스는 호스트의 Pillow/FreeType으로, 패키지 패스는 고정된 wheel로 렌더하기 때문). `maker/test/test_uisample.py`는 같은 표를 HTTP
API로 실행하고 각 점검이 변이에서 실패함을 증명한다.

## 샌드박스

AppImage는 Chromium의 SUID 샌드박스 도우미를 실을 수 없다(FUSE 마운트는 `nosuid`이다). 따라서 가질 수 있는 샌드박스는 사용자
네임스페이스 샌드박스뿐인데, Ubuntu 24.04는 권한 없는 사용자 네임스페이스를 거부한다. electron-builder의 `AppRun`은 `unshare -Ur
true`를 테스트하고 실패하면 `--no-sandbox`를 붙인다. AppImage의 `.desktop` 항목은 `Exec=AppRun %U`이다(사용자 네임스페이스가 있든 없든 항목은 같고, 플래그는 `AppRun`이 스스로 붙인다. 아래 참조). 따라서 이
호스트와 Ubuntu 24.04급의 모든 시스템에서 렌더러는 샌드박스 **없이** 실행된다(셸이 로그를 남기고 About에 "renderer sandbox: off
(--no-sandbox; user namespaces unavailable)"이 표시된다). 사용자 네임스페이스가 있는 시스템에서는 샌드박스 안에서 실행될 것이다
(검증하지 않음). 렌더러는 엄격한 CSP를 가진 루프백 서버의 앱 자체 페이지와 사용자가 고른 파일만 불러오며, 원격 콘텐츠는 불러오지
않는다(D7, 명세 17절). AppArmor 프로필이 있는 `.deb`는 Ubuntu 24.04에서 샌드박스를 되돌릴 것이다. 이는 나중 카드(D13)이고 여기서는
하지 않았다.

## AppImage 도구 세트, runtime, 트레이 아이콘

**Runtime (t_ea7dcc8e).** electron-builder의 기본(레거시 `appimage-12.0.1`) 도구 세트로 만든 AppImage는 `libfuse.so.2`를
`dlopen()`하는 옛 type-2 runtime을 싣는다. `libfuse2t64`가 없는 깨끗한 Ubuntu 24.04.5에서는 "dlopen(): error loading
libfuse.so.2 ... AppImages require FUSE to run"으로 멈췄다. 그래서 `desktop/package.json`은 `"toolsets": {"appimage": "1.0.3"}`
(electron-builder 26.18.0 자체의 스위치)을 설정한다. 그러면 runtime은 AppImage/type2-runtime **release 20251108**의 static-pie
type2 runtime(`runtimes/runtime-x64`, sha256 `2fca8b44...260d`, electron-builder-binaries release `appimage@1.0.3`에서 가져옴,
아카이브 `appimage-tools-runtime-20251108.tar.gz` sha256 `84021a78...7665`, 둘 다 `desktop/build/appimage-toolset.json`과
electron-builder에 고정됨)이 된다. 이는 정적으로 링크된 자체 libfuse3로 마운트하며 머신에 `fusermount`/`fusermount3`만 있으면 된다
(Ubuntu 24.04에는 있음). 더 새로운 도구 경로의 다른 차이: squashfs 압축은 zstd이고(레거시 경로는 gzip), 생성되는 `.desktop` 항목은
`Exec=AppRun %U`이다(`--no-sandbox` 플래그는 `unshare -Ur true`가 실패할 때 전과 같이 `AppRun`이 스스로 붙인다). 릴리스 점검
`runtime`이 이것이 퇴행하지 않게 한다. runtime의 소스(libfuse3과 squashfuse가 딸린 type2-runtime 20251108)는 D8 구성 요소
`appimage-runtime` 버전 `20251108`이다(보관할 LGPL 구성 요소: libfuse 3.15.0; 레시피: type2-runtime release). THIRD-PARTY.txt는
내장된 구성 요소 여섯 개 모두의 텍스트를 싣고(`desktop/build/licences/appimage-runtime.txt`, 각각 해당 버전의 업스트림 소스에서
가져왔고 소스 URL을 기록함), runtime의 sha256을 도구 세트 기록 옆에 출력한다.

**트레이 아이콘.** electron-builder는 오래된 라이브러리 여섯 개(appindicator3, gconf, indicator3, notify, Xss, Xtst)를
AppImage의 `usr/lib`에 복사한다. `libindicator`는 **GPL-3.0**이고 패키징 규칙은 패키지에 GPL을 금지한다. 레거시 도구 세트와 1.0.x
도구 세트 모두 이를 싣는다. 그래서 빌드는 electron-builder(`APPIMAGE_TOOLS_PATH`)가 `libindicator`와 `libappindicator`를 제거한
도구 세트 사본을 가리키게 한다(`desktop/build/prune-appimage-toolset.py`, `desktop/build/appimage-toolset.json`이 구동: 내려받은
아카이브의 sha256, runtime의 sha256, 제거한 각 파일의 sha256을 검사하고 THIRD-PARTY.txt에 출력하며, 바이너리는 저장소에 저장하지
않는다). **트레이 아이콘 지원(libappindicator)은 싣지 않는다.** `libindicator` 없이는 불러올 수 없고 앱에는 트레이 아이콘이 없으므로
잃는 것이 없다. 릴리스 점검은 가지친 AppImage가 여전히 시작하는지(추출된 `AppRun` smoke)와 GPL 라이브러리가 남지 않았는지를
증명한다.

## 라이선스와 릴리스 게이트

`THIRD-PARTY.txt`는 번들에서 생성된다. 규칙: 사이드카, Electron의 디렉터리, `usr/lib`의 모든 공유 객체는
`desktop/build/third-party-map.json`의 항목과 일치해야 한다(fail closed). Electron과 `usr/lib`의 모든 라이브러리의 sha256이 그 옆에
출력된다. 사이드카 라이브러리는 빌드 시점의 출처와 일치해야 한다(`sidecar-provenance.py`, PyInstaller의 목차에서). 클래스 `gpl`은
금지된다. 클래스 `lgpl`은 배포 기록이 필요하다. `svf/`에는 OFL로 나열된 페이스만 둘 수 있다. 현재의 카피레프트 구성 요소: ffmpeg
(Electron의 `libffmpeg.so`, LGPL-2.1), AppImage runtime(libfuse가 정적으로 링크됨, LGPL-2.1), PyInstaller 부트로더(부트로더 예외가
있는 GPL).

**D8, 릴리스 게이트(비공개 빌드의 게이트가 아님):** 첫 공개 릴리스 전에 해당 소스 아카이브를 `MANIFEST.json`과 함께
`desktop/build/out/sources/`에 둔다.

    [{"component": "ffmpeg (Chromium build, in Electron)", "version": "Electron 45.2.3", "kind": "source",
      "archive": "ffmpeg-....tar.xz", "sha256": "<hex>"},
     {"component": "appimage-runtime", "version": "20251108", "kind": "source", "archive": "runtime-src.tar.gz", "sha256": "<hex>"},
     {"component": "appimage-runtime", "version": "20251108", "kind": "recipe", "archive": "runtime-recipe.txt", "sha256": "<hex>"}]

(구성 요소와 버전이 맵의 것과 같은 LGPL 구성 요소마다 `source` 항목 하나, 그리고 AppImage runtime에는 `recipe` 하나.) 그러면
`build-appimage.sh --release`는 생성기가 "corresponding sources archived: YES"를 출력하지 않는 한 실패한다.

## glibc 하한

사이드카는 PyInstaller가 찾는 시스템 라이브러리를 glibc만 빼고 번들한다. 따라서 패키지에는 적어도 빌드 호스트의 glibc(2.39,
Ubuntu 24.04)가 필요하다. Ubuntu 22.04(glibc 2.35)의 컨테이너 빌드라면 이를 넓힐 것이다(D9; 하지 않음).

## 수동 점검 (실제 데스크톱이 있는 사람)

네이티브 파일 및 폴더 대화상자(테스트는 이를 스텁으로 대체한다), 데스크톱 파일 관리자에서 "폴더 열기", 창 관리자가 있는 실제 데스크톱에서
AppImage 시작(`./svf-maker-0.1.0.AppImage`; 마운트와 Xvfb 아래의 창은 깨끗한 호스트에서 보였으며 아래 참고), GPU 경로(테스트는 `--disable-gpu`를 쓴다), 사용자 네임스페이스가 있는 호스트에서
샌드박스된 렌더러.

## 깨끗한 머신에서의 시작 (t_ea7dcc8e, 2026-11-20)

호스트 `pc`: Ubuntu 24.04.5, `libfuse2t64` 없음(`libfuse.so.2` 없음), `fusermount`/`fusermount3` 있음, 디스플레이 없음, 테스트를 위해
설치한 것 없음. 이 브랜치에서 빌드한 AppImage(133 MB, zstd squashfs)를 `~/work/tmp/svf-clean`에 복사해 `env -i HOME=$HOME
PATH=/usr/bin:/bin`으로 실행했다.

    $ ./svf-maker-0.1.0.AppImage --appimage-version
    AppImage runtime version: https://github.com/AppImage/type2-runtime/commit/dd6cebe          (exit 0)
    $ ./svf-maker-0.1.0.AppImage
    ERROR:ui/ozone/platform/x11/ozone_platform_x11.cc:257] Missing X server or $DISPLAY          (exit 1)
    $ ./svf-maker-0.1.0.AppImage --appimage-mount     # the squashfs is mounted: AppRun, chrome_100_percent.pak, ... listed

libfuse 오류는 사라졌다. 이제는 FUSE 마운트 뒤에(마운트된 이미지에서 Electron이 시작됨) 디스플레이가 없다는 이유로만 실패한다.

### Xvfb 아래의 창 (t_9b9e0bd8 기록, 2026-11-22)

같은 호스트 `pc`(Ubuntu 24.04.5, `libfuse2t64` 없음)에서 커밋 3d40de8로 빌드한 AppImage가 Xvfb 아래에서 시작되었다. 창이 그려졌고
로컬 모드 변환이 패키지된 사이드카를 통해 실행되었다. 검증하지 않음: 창 관리자와 GPU가 있는 실제 데스크톱, Windows와 macOS. 이 문서화
작업에서는 같은 커밋을 빠른 시작대로 깨끗한 체크아웃에서 빌드했고(캐시가 따뜻할 때 1분 26초, 모든 `CHECK` 줄 ok, AppImage
140,426,554 바이트), 추출한 `AppRun`과 AppImage 자체가 Xvfb 아래에서 smoke 줄 `svf-maker smoke ok SVF maker`를 출력했으며, 개발 실행(`desktop/`에서
`node_modules/.bin/electron --no-sandbox .`, Xvfb 아래)은 `sidecar start mode=dev`와 사이드카의 포트 줄을 기록했다.

## Windows와 macOS (UNVERIFIED)

아래의 어느 것도 실행하지 않았다. 이 호스트들의 빌더가 따를 계획과 그것을 막는 것이다. 빌드도 검증도 하지 않았다.

- **macOS.** PyInstaller one-dir은 macOS에서 같은 spec을 빌드한다(arm64와 x86_64는 별개의 빌드이고, universal2 빌드에는 Pillow와
  fontTools의 universal wheel이 필요하다. `desktop/build/requirements.lock`은 Linux cp312 wheel만 고정한다). 서버는 이미 macOS
  (POSIX)에서 동작하지만, 레지스트리의 macOS 시작 시각(`ps -o lstart=`)은 테스트하지 않았다. electron-builder 대상은 `dmg` + `zip`이고,
  `extraResources`는 같으며, AppImage의 `--no-sandbox` 문제는 없다. 서명: Developer ID Application 인증서, `mac.hardenedRuntime:
  true`, `com.apple.security.cs.allow-unsigned-executable-memory`(Chromium) 외에는 아무것도 허용하지 않는 entitlements 파일 - 그리고
  `resources/sidecar/` 아래의 모든 바이너리도 서명해야 한다(`codesign --deep`은 `_internal/*.so`에 확실히 닿지 않는다. 각각
  `--options runtime`으로 개별 서명한다). 그다음 `notarytool submit`과 `stapler`. 서명하지 않으면 Gatekeeper가 첫 실행에서 앱을
  막는다(오른쪽 클릭으로 열기는 된다).
- **Windows.** **서버는 Windows용이 아니다**(`os.killpg`, `start_new_session`, 그룹에 대한 `signal.SIGTERM`, `os.umask(0o077)`의
  의미, 덮어쓰기 없는 쓰기를 위한 `os.link`, 레지스트리와 데이터 루트 락의 `fcntl` 락). 포팅에는 그룹 kill을 위한 Job Objects(또는
  `CREATE_NEW_PROCESS_GROUP` + `GenerateConsoleCtrlEvent`), `run_command`/`run_bounded`의 `CreateProcess` 플래그, NTFS에서 로컬 모드
  설계의 모든 `realpath`/inode 규칙에 대한 검토가 필요하다. 이는 별도의 카드이며, 이것이 끝나기 전에는 Windows 빌드를 시도하지
  않는다. 그다음: 같은 PyInstaller spec(`console=True`와 셸의 `windowsHide`를 유지), electron-builder 대상 `nsis` 또는 `portable`,
  Job Object를 쓰는 Electron spawn, 코드 서명 인증서로 서명.

## 여기서 검증하지 않은 것

Windows와 macOS 전체; 실제 데스크톱(창 관리자, GPU)에서의 AppImage 시작(위의 Xvfb 창 실행은 했음); 샌드박스된 렌더러; 2.39보다 오래된 glibc; 동결된 프로세스에서 3.12
wheel을 쓰는 `JAMOSET_PYLIB`과 실제 인식기(테스트는 스텁 인터프리터를 쓴다); 디스플레이가 있는 네이티브 대화상자; AppImage runtime의
바이너리가 밝히는 것 이상의 구성(내장된 라이선스 목록과 버전 문자열: type2-runtime, musl libc, libfuse 3.15.0, squashfuse 0.5.2,
libzstd 1.5.6, zlib 1.3.1; musl 자체의 버전은 내장되어 있지 않으므로 그 COPYRIGHT는 v1.2.5의 것을 가져왔다); AppImage의
`SOURCE_DATE_EPOCH` 결정성(사이드카는 비트 단위로 재현되지 않는다: `base_library.zip` 멤버 순서가 빌드마다 바뀐다); 향후 Pillow
wheel의 2.13.2가 아닌 FreeType; 기록된 소스의 정확한 URL(기록만 했고 가져오지 않았다).
