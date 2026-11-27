[English](maker-desktop.md) | **한국어**

# SVF maker 데스크톱 구현과 패키징

SVF maker는 Electron 셸, Python HTTP 서버(사이드카), 서버가 제공하는 웹 페이지로 구성된다.
Linux x86_64 AppImage를 빌드한다. 설치와 사용법은 [데스크톱 앱](desktop-app.ko.md),
서버 실행과 HTTP API는 [maker 안내](../maker/README.ko.md), 변환 기능은 [기능 점검](maker-audit.ko.md)을 참고한다.
[설계](superpowers/specs/2026-11-05-maker-desktop-design.md)와
[구현 계획](superpowers/plans/2026-11-05-maker-desktop.md)도 있다.

## 1. 실행 구조

| 구성 요소 | 동작 | 구현 |
|---|---|---|
| Electron 셸 | 단일 인스턴스 잠금, 창·메뉴·네이티브 대화상자, 사이드카 시작·종료 | `desktop/main.js`, `desktop/preload.js`, `desktop/lib/` |
| 사이드카 | `serve --exit-with-parent=<pid>`로 실행하는 PyInstaller one-dir 번들 | `maker/sidecar.py`, `maker/sidecar.spec` |
| 도구 실행 | 소스 모드에서는 `python3 -P tools/<name>.py`, 동결 모드에서는 `svf-maker-sidecar run-tool <name>` | `maker/toolrun.py` |
| 미리 보기 | C 렌더러를 WebAssembly로 빌드하여 페이지에서 실행 | `maker/build-wasm.sh`, `maker/static/svfview.js`, `c/ports/web/` |

셸은 실행마다 16바이트 난수를 32자리 16진 토큰으로 만들고, `127.0.0.1:0`으로 서버를 시작한다.
최대 75초 동안 `svf-maker listening on 127.0.0.1:<port>`를 기다린다.
2초 안에 준비되지 않으면 시작 안내 페이지를 표시한다. 포트를 받으면 해당 루프백 HTTP 페이지를 로드하며,
`/api/` 요청에는 셸이 `X-Maker-Token`을 붙인다. 토큰은 페이지에 전달하지 않는다.

페이지의 `window.svfMaker`는 `pickFiles()`, `pickFolder()`, `pickOutputDir()`,
`openOutputFolder()`와 `platform`을 제공한다. 마지막 함수는 인자를 받지 않는다. 셸이 현재 작업의 출력 폴더를
조회하고, 사용자가 대화상자에서 고른 최근 32개 실제 경로 중 하나인지 확인한 뒤 파일 관리자에 표시한다.

데이터는 Electron의 `userData` 아래 `maker/`, 개발 실행에서는 `maker-dev/`에 둔다.
Linux 기본 경로는 `~/.config/svf-maker/`이며, `--user-data-dir`로 바꿀 수 있다.
서버의 `instance.lock`은 같은 데이터 폴더의 동시 사용을 막는다.
각 도구는 별도 세션에서 실행되어 `tools.pids`에 등록된다. 정상 종료 때 중지하며, 비정상 종료 후에는 다음 시작 때
식별 가능한 잔여 프로세스를 정리한다. 셸의 정상 종료 대기는 45초이며 이후 강제 종료 대기는 5초이다.

## 2. Linux 빌드

빠른 시작의 [필수 도구와 설치 명령](desktop-app.ko.md#0-빠른-시작)을 먼저 따른다.
필수 조건은 git 체크아웃, pip가 있는 Python 3.12, 시스템 Python용 Pillow·fontTools,
Node.js 22.12 이상과 npm, emsdk, `xvfb-run`, `flock`이다.
고정 wheel은 Linux x86_64 CPython 3.12용이다. emsdk 기본 경로는 `~/opt/emsdk`이며 `$EMSDK`로 바꾼다.

체크아웃 루트에서 실행한다.

```sh
mkdir -p "$HOME/work/tmp"
cd desktop
npm ci
node node_modules/electron/install.js
cd ..
bash desktop/build/build-appimage.sh
```

Electron 설치 스크립트를 명시적으로 실행하므로 npm이 설치 스크립트를 차단하는 설정에서도 바이너리를 받는다.
버전은 `desktop/package-lock.json`과 `desktop/build/requirements.lock`에서 고정한다.

| 구성 요소 | 고정 버전 |
|---|---|
| Electron | 45.2.3 |
| electron-builder | 26.18.0 |
| PyInstaller | 6.22.3 |
| Pillow | 10.2.0 |
| fontTools | 4.66.1 |
| AppImage 도구 세트 | appimage@1.0.3 |

`maker/build-sidecar.sh`가 WASM 빌드, 해시를 검사하는 `pip --target` 설치, PyInstaller 빌드,
`env -i` 자체 점검과 동결 테스트를 수행한다. `build-appimage.sh`에서는 동결 테스트를 건너뛰지 않는다.
고지 파일을 생성한 뒤 electron-builder가 `desktop/dist/svf-maker-0.1.0.AppImage`를 만든다.
버전은 `desktop/package.json`에서 가져온다.

스크래치는 `$SVF_DESKTOP_TMP`(기본 `$HOME/work/tmp/svf-desktop-build`)에 둔다.
빌드와 릴리스 점검 스크립트는 스모크 검사 때 `$HOME/work/tmp/svf-browser.lock`을 직접 잠근다.
같은 잠금의 `flock`으로 감싸면 교착된다. `desktop/test/run-e2e.sh`는 잠금을 직접 얻지 않으므로,
별도로 실행할 때는 호출자가 잠금을 관리한다. 이 테스트는 짧은 스크래치 경로를 `TMP_DIR`로 받아 `TMPDIR`에 전달한다.

### 2.1. 릴리스 점검

`desktop/build/release-check.sh APPIMAGE [--release]`가 다음을 검사한다.

| 점검 | 조건 |
|---|---|
| `size`, `size-sidecar` | AppImage ≤ 170 MiB, 사이드카는 `du -sm` 결과 ≤ 60 |
| `extract`, `layout` | 추출 성공, 필수 자원 존재, 스테이징한 소스에 테스트·캐시 없음 |
| `apprun`, `desktop-entry` | `unshare` 검사와 `--no-sandbox` 분기 존재, 실행 항목이 `AppRun` 사용 |
| `runtime` | ELF 인터프리터·동적 의존성·`libfuse.so.2` 문자열 없음, HOME·PATH만 남긴 환경에서 버전 출력과 종료 코드 확인 |
| `frozen` | 추출한 사이드카의 동결 테스트 통과, 건너뛴 테스트 없음 |
| `wasm` | 새로 빌드한 WASM과 바이트 단위 일치 |
| `licences`, `notices`, `sources` | 라이선스 매핑·고지 재생성·동봉 Python 소스 검증 |
| `smoke` | Xvfb에서 추출한 `AppRun` 시작, API 응답, 정상 종료와 프로세스 종료 확인 |
| `sources` (`--release`) | LGPL 대응 소스 보관 조건 충족 |
| `contents` | 빌드 식별자·AppImage 해시별 파일 목록 저장 |

`--release`가 없으면 대응 소스 보관 점검은 `CHECK sources skipped`이다.
두 종류의 소스 점검은 같은 `sources` 이름을 쓰므로 줄 이름만으로 구별하지 말고 세부 내용을 읽는다.
실패가 있으면 종료 코드는 1이다. 스모크 검사는 잠금을 얻은 뒤 Electron 실행에 90초를 허용한다.
추출 실행을 검사하므로 FUSE 마운트 성공까지 증명하지는 않는다.

## 3. AppImage 런타임과 샌드박스

`desktop/build/appimage-toolset.json`은 도구 세트 아카이브, 런타임, 제거할 라이브러리의 SHA-256을 고정한다.
선택한 런타임은 type2-runtime 20251108이며 정적으로 링크된 FUSE 3 코드를 포함한다.
호스트의 `libfuse.so.2`는 필요 없지만 `fusermount` 또는 `fusermount3`와 마운트 권한은 필요하다.
마운트할 수 없으면 `--appimage-extract` 후 추출한 `AppRun`을 실행한다.

`AppRun`은 `unshare -Ur true`에 실패하면 `--no-sandbox`를 추가한다.
Ubuntu의 사용자 네임스페이스 제한은 시스템 정책에 따라 달라지므로 배포판 이름만으로 샌드박스 상태를 단정하지 않는다.
셸은 `sandbox: true`, `contextIsolation: true`, `nodeIntegration: false`를 요청하지만,
`--no-sandbox` 실행에서 Chromium 프로세스 샌드박스가 켜지는 것은 아니다.
실제 감지 결과는 셸 로그와 Help > About에 표시한다.

셸은 원격 요청, 새 창, 다운로드와 권한 요청을 차단한다. 페이지와 사이드카는 루프백 HTTP로 통신한다.
이 제어는 선택적 인식기 등 하위 프로세스의 운영체제 수준 네트워크 격리가 아니다.
보안 설정의 의미는 Electron 보안 안내와 Ubuntu 사용자 네임스페이스 설명을 참고한다(7절).

## 4. 라이선스와 대응 소스

`desktop/build/third-party.mjs`가 `THIRD-PARTY.txt`를 생성한다. 공유 라이브러리는
`third-party-map.json`에 매핑되어야 하며, 사이드카 라이브러리는 빌드 출처와 일치해야 한다.
일반 GPL 라이브러리는 거부한다. PyInstaller 부트로더는 GPL과 별도 부트로더 예외로 분류한다.
LGPL 구성 요소는 배포 기록이 필요하며, `svf/`에는 허용 목록의 OFL 페이스만 둔다.

AppImage 도구 세트의 `libindicator`는 GPL-3.0이므로 `prune-appimage-toolset.py`가 이를 제거한다.
이에 의존하는 `libappindicator`도 제거한다. 앱은 트레이 아이콘을 제공하지 않는다.
런타임에 포함된 구성 요소의 라이선스 본문은 `desktop/build/licences/appimage-runtime.txt`에 있다.

공개 릴리스에는 `desktop/build/out/sources/MANIFEST.json`과 대응 소스 아카이브를 준비하고
`bash desktop/build/build-appimage.sh --release`를 실행한다. 각 LGPL 구성 요소의 `component`와
`version`이 매핑과 같은 `source` 항목을 요구하며, AppImage 런타임은 `recipe` 항목도 요구한다.
각 항목에는 `archive`와 `sha256`이 있어야 한다. 예시는 다음과 같다.

```json
[
  {"component": "appimage-runtime", "version": "20251108", "kind": "source", "archive": "runtime-src.tar.gz", "sha256": "<hex>"},
  {"component": "appimage-runtime", "version": "20251108", "kind": "recipe", "archive": "runtime-recipe.txt", "sha256": "<hex>"}
]
```

이 예시는 런타임 항목만 보여 준다. Electron의 ffmpeg 등 매핑의 다른 LGPL 구성 요소도 필요하다.
생성기가 `corresponding sources archived: YES`를 출력해야 릴리스 소스 점검을 통과한다.

## 5. 자동 검증과 기록된 실행

`npm test --prefix desktop`는 Electron 창 없이 셸 유틸리티, 라이선스 생성기, 추출 검증,
런타임 검사기의 Node 테스트를 실행한다. `maker/test/test_frozen.py`는 빌드된 사이드카가 필요하다.
`desktop/test/run-e2e.sh`는 Xvfb와 Electron이 필요하며 대화상자를 스텁으로 바꾸고 GPU를 끈다.
패키지 경로의 두 번째 패스에는 `SVF_MAKER_SIDECAR`와 `SVF_MAKER_STAGED_REPO`가 필요하다.

샘플 변환은 `maker/test/uisample.py`가 입력과 기대 출력을 정의한다.
OFL 폰트 네 개와 합성 Mac·HWP·BDF 입력을 사용하여 페이스 10개와 TTF/BDF 내보내기 3개를 검사한다.
예상 파일 목록, 입력 불변성, 페이스 검사와 실제 그리기, 순수 Python 경로의 개발·패키지 결과 일치를 확인한다.
윤곽선 결과는 호스트와 고정 wheel의 FreeType 차이 때문에 일부 바이트 차이를 허용한다.
TTF 비교는 `head` 타임스탬프를 맞춘다. 자세한 검증은 `maker/test/test_uisample.py`에 있다.

기록된 2026-11-22 실행에서는 Ubuntu 24.04 x86_64에서 만든 커밋 `3d40de8`의 AppImage가
140,426,554바이트였으며, 깨끗한 Ubuntu 24.04.5 호스트에서도 Xvfb 아래 창과 로컬 변환이 동작했다.
이 값은 현재 빌드의 크기나 실행 시간을 보장하지 않는다.

## 6. 지원 범위와 남은 검증

- Linux x86_64 빌드를 제공한다. Windows와 macOS 패키지는 빌드·실행하지 않았다.
- Windows 이식에는 `fcntl`, 프로세스 그룹 종료, 파일 잠금·링크 및 경로 검증을 바꾸거나 확인해야 한다.
  macOS도 별도 wheel·서명·공증과 프로세스 식별 검증이 필요하다. 현재의 Linux wheel 잠금을 그대로 쓸 수 없다.
- 기록된 빌드 호스트의 glibc는 2.39이다. 오래된 glibc와의 호환성은 검증하지 않았으며,
  실제 요구 심벌 버전은 수집한 바이너리에 따라 달라진다.
- 실제 창 관리자·GPU, 네이티브 대화상자, 파일 관리자 연동, 샌드박스된 렌더러는 별도 수동 검증이 필요하다.
- 외부 인식기의 실제 모델은 검증되지 않았다. 선택적 라이브러리는 번들에 포함하지 않는다.
- AppImage의 비트 단위 재현성은 보장하지 않으며 자동 업데이트는 없다.

출력 페이스를 사용하는 방법은 [C 렌더러](c-renderer-guide.ko.md),
[웹 렌더러](web-renderer-guide.ko.md), [렌더러 설계](../spec/renderer-design.ko.md)를 참고한다.

## 7. 참고 문헌 / References

- Electron: 보안 권고 — <https://www.electronjs.org/docs/latest/tutorial/security>
- Electron: 프로세스 샌드박스 — <https://www.electronjs.org/docs/latest/tutorial/sandbox>
- Ubuntu 24.04: 비특권 사용자 네임스페이스 제한 — <https://discourse.ubuntu.com/t/ubuntu-24-04-lts-noble-numbat-release-notes/39890>
- AppImage type2-runtime 20251108 — <https://github.com/AppImage/type2-runtime/releases/tag/20251108>
- AppImage 런타임 라이선스 — <https://github.com/AppImage/type2-runtime/blob/20251108/LICENSE>
- PyInstaller 부트로더 예외 — <https://pyinstaller.org/en/stable/license.html>
- GNU LGPL 2.1 — <https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html>
