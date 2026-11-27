[English](README.md) | **한국어**

# SVF maker

maker는 업로드한 폰트(TTF/OTF/TTC, 가변 폰트, Mac 폰트, BDF/PCF, DOS Johab 원시 폰트, SVF 파일)를 이 저장소의 도구로
SVFN v3 페이스(face)로 바꾸고, 모든 결과를 브라우저에서 미리 보여 주는 페이지를 제공한다. 127.0.0.1에서만
수신하며 작업(job)을 데이터 디렉터리 아래에 보관한다.

## 실행

    SVF_MAKER_REPO=$PWD SVF_MAKER_DATA=$(mktemp -d) SVF_MAKER_BIND=127.0.0.1:8766 python3 -P maker/server.py

`SVF_MAKER_REPO`는 체크아웃(그 `tools/`와 `svf/`를 사용), `SVF_MAKER_DATA`는 작업 저장소, `SVF_MAKER_BIND`는
`host:port`(기본값 127.0.0.1:8766)이다. `http://127.0.0.1:8766/`을 연다.

## 토큰과 루프백

`SVF_MAKER_TOKEN`(소문자 16진수 32자, 실행마다 새로 만듦)은 로컬 모드를 켠다. 설정하면 모든
`/api/` 요청이 그 값을 가진 `X-Maker-Token` 헤더를 정확히 하나 가져야 하고(아니면 403), 모든 요청(페이지와
`/static/*` 포함)이 `Host` 헤더에 이 서버를 지목해야 하며, 서버는 `127.0.0.1` 또는 `::1`에만 바인드한다. 루프백이 아닌
`SVF_MAKER_BIND`는 거부되고 프로세스는 종료 코드 2로 끝난다(잘못된 토큰도 종료 코드 2이며 토큰은 절대
출력하지 않는다). 페이지는 자기 오리진만 허용하는 Content-Security-Policy와 함께 제공된다. 토큰이 없으면
maker는 이전처럼 동작한다.

## 미리보기 모듈

페이지는 WebAssembly로 빌드한 C 렌더러로 페이스를 그린다. 한 번 빌드한다(emsdk 필요, 기본값 `~/opt/emsdk`이며
`EMSDK`로 지정 가능):

    bash maker/build-wasm.sh

`c/ports/web/emcc-flags.sh`의 컴파일 줄(`web/build.sh`와 같음)로 `maker/static/wasm/svf.js`와 `svf.wasm`을
쓴다(git에서 무시됨. `SVF_WASM_OUT`으로 폴더를 바꿀 수 있다). 모듈이 없으면 페이지는 "preview module not
built: run maker/build-wasm.sh"라고 알리고 모든 미리보기 셀이 그 문구를 보여 주며, 그 밖의 것은 깨지지 않는다.

## 로컬 모드 (데스크톱 앱)

토큰을 설정하면(위 참조) maker는 폰트를 **있는 자리에서** 읽고, 사용자가 고른 출력 폴더에만 페이스를 쓴다.
아무것도 업로드하지 않고, 데이터 디렉터리로 복사하지 않으며, zip도 만들지 않는다. 데스크톱 앱이 이를 구동한다:

- `POST /api/jobs {"source": "local", "output_dir": "/abs/folder"}`가 작업을 만든다(토큰이 없으면 403. 폴더는 이미 있어야 하며, 없으면 400
  `{"error": "output folder: no such file or folder"}`이다. 서버의 모든 거부는 `error` 문장이 있는 JSON이다).
  `PUT /api/jobs/<id>/sources {"paths": [...]}`가 읽을 파일이나 폴더를 알려 준다(각각 검사한다: 절대 경로일 것, 링크가
  아닐 것, 데이터 폴더가 아닐 것, 출력 폴더나 다른 입력과 겹치지 않을 것. 선택적인 `SVF_MAKER_ROOTS`
  허용 목록이 더 제한하며 출력 폴더에도 적용된다). 그다음 평소대로 `POST detect`, `PUT settings`, `POST run`. 고른 경로는 제자리에서 읽으며,
  아카이브는 목록만 보이고 풀지 않는다.
- 실행하면 `svf/<dest>/<NAME>.SVF`와 그 노트(라이선스 본문을 골랐다면 그것도), 그리고 `build-<id>/`
  (`BUILD.md`, `LICENCES.tsv.lines`, `FAMILIES.tsv.lines`, `FACES.TSV.lines`)를 출력 폴더에 쓰며, 그 밖에는 쓰지 않는다.
  `BUILD.md`는 실행한 명령을 나열한다. [docs/recipes/desktop-routes.ko.md](../docs/recipes/desktop-routes.ko.md#데스크톱-앱과-maker-경로)는 페이지의 모든 경로 레이블을
  그 명령줄과 레시피에 대응시킨다.
  `options.export`(`{"ttf": true, "bdf": true}`, 일괄 또는 폰트별)가 있으면 모든 페이스를 그 옆에 `<NAME>.ttf` / `<NAME>.bdf`로도
  쓴다. 페이스 단계 뒤의 `export` 단계가 `tools/svf2ttf.py ttf|bdf FACE OUT [--licence FILE]`을 실행하고(작업이 그 폰트에 대해 아는
  라이선스를, 그것이 이름을 든 `.TXT` 중 배치에 있는 것만 소스를 거쳐 찾아 `work/<font id>/licence/`에 UTF-8로 옮겨 둔 것(UTF-8로, 아니면 CP949로, 아니면 바이트를 바꾸어 읽는다). svf2ttf.py는
  이름 든 파일을 따라가므로 루트 밖으로 가는 링크나 고르지 않은 파일은 보지 못한다. 라이선스를 고르지 않은 채 내보내기만 하는 SVF는
  svf2ttf.py의 규칙으로 그 옆의 노트를 배치의 파일 중에서만 찾는다. 다른 파일은 열지 않는다), 그 확인(`quality.export_facts`)은 파일을
  열어(TTF는 fontTools로) 페이스의 코드 포인트를 정확히 담았는지 요구한다. 내보낸 파일은 `.lines` 행이 없고 페이스의 노트에도
  없으며 `BUILD.md`가 나열한다. SVF 소스의 경로 `svf2ttf`(`precomposed_route` / `jamo_route`)는 페이스를 내보내기용으로만 읽고
  SVF, 노트, 라이선스 본문을 쓰지 않으며(그 이름은 필요하지도 검사하지도 않는다), `ttf`나 `bdf`가 필요하고, 내보낸 파일이 하나라도
  쓰였을 때만 작업이 `done`이다. `"composite": true`는 자모 세트의 TTF에 `--composite`를 더한다(조각은 한 번, 모든 음절은 그 합성. 확인은 문자 외에 조각
  글리프를 허용한다). `ttf` 없는 `composite`는 거부한다.
  작업이 직접 쓰지 않은 이름은(내보낸 파일의 이름도) 절대 덮어쓰지 않는다. 작업이 살아 있는 동안 변환에 중간에 필요한 파일은
  출력 폴더 안의 `.svf-maker-<id>/`(모드 0700)에 두며, 작업이 끝나거나, 삭제되거나, 서버가
  멈추면 지운다. 동기화되지 않는 폴더를 고른다.
- 라이선스는 **선택 사항**이다. 고르지 않으면 노트와 `BUILD.md`에 "licence: not checked (user's
  responsibility)"라고 적힌다. 변환할 권리가 없는 폰트를 변환하는 것은 사용자 본인의 책임이며, 결과를 공개한다면
  폰트의 라이선스를 확인한다. 페이지는 세션마다 한 번 이를 확인(acknowledge)하도록 요청한다.
- 일반적인 종류 외에 읽는 것: 클래식 Mac **HangulTalk 7.1 type-3 `fbit`** 폰트(리소스 포크, AppleDouble `._Name`,
  MacBinary `.bin`, JM 아카이브, 원시 `fbit` 리소스)와 그 **HTBL 1** 테이블
  (`InputBackSupport` 또는 `<Name>.htbl1`, 다른 소스로 함께 고름), 그리고 선택적인 라틴 suitcase(FOND + NFNT)를
  `macfbit_svf.py`(직접 또는 파생)나 `macfbit3.py bdf` + `mkfont.py`로 읽는다. 또한 **HangulTalk 1.0** 폰트(`fdef`가 있는
  포크)는 `jamoset.py --layout mac-fbit-45sets`로 읽는다. `fdef`가 없는 원시 1.0 `fbit` 리소스는
  무엇이 빠졌는지와 함께 목록에 나온다. HWP 1.x: `HANGUL.SFT` / `HANGULn.PFT`의 페이스(파일마다 셋)를 `jamoset.py --layout
  hwp1`(HWP 자체의 조합 규칙, 정확)이나 `hwpfont.py bdf` + `mkfont.py`로 읽고, `ASCII.SFT` / `ASCII.PFT`가 영문 짝이다. HWP 3.0:
  `HAN*.FNT` 한글 폰트(음절 2,350자. 16 px 파일은 8x4x4 세트로도, `--layout 844-hwp3`)와 `ENG*.FNT` 짝(`tools/hwpfont.py`,
  docs/recipes/dos-fonts.ko.md "HWP 1.x와 2.x 폰트"). 헤더 없는 KS X 1001 음절 덤프(태백 `GHAN24.PFT`)는 두 모드 모두 크기로 읽는다. 12x24나 14x24 영문
  폰트(태백 `GASCII24.PFT`는 12x24, HWP 1.x `ASCII.PFT`는 14x24)는 24 px 페이스의 동반 파일이며 배치의 어느 폴더에 있어도 된다.
  **알려진 ROM 세트**: `maker/recipes/*.json`의 내장 레시피(`maker/recipe.py`, 글꼴 찾기 설계의 레시피 스키마 버전 1 중 `files`,
  `ks-grid` / `english` 항목, `bdfface` 페이스, `expect`만. 그 밖의 것은 이름을 들어 거부한다)는 파일을 내용이 아니라 크기와
  SHA-256으로 지정한다. 레시피가 이름 붙인 크기의 파일만 해시를 구하며, 완전한 세트는 `recipe` 항목 하나("known: <제목>", 파일들이
  함께 고정됨)가 되고 그 경로는 레시피의 명령(각 항목의 `rawcarve.py bdf`, `bdfface.py`, `jamoset.py --from-svf` fit)을 실행한다.
  현재: 86Box 한글 VGA ROM 쌍 셋(docs/recipes/rom-86box.ko.md "한글 VGA 폰트 ROM (86Box)")과 MAME 세트 넷, SPC-1500(정확한 자모 세트, 경로 `spec`),
  Date Quiz Go Go, X Se Dae Quiz(경로 `dos raw`), Quiz King of Fighters(한국판)(docs/recipes/rom-mame.ko.md "MAME 세트의 한글 폰트 ROM". 영역, 타일
  배치, 펜도 레시피 데이터이며, 스키마 9.4를 넘는 확장 하나: 페이스의 `english`는 여러 항목을 나열할 수 있고 `srcprep.py or-files`로
  OR한다). 파일이 빠진 세트는 "part of <제목>: also needs
  <이름>; pick the folder", 레시피의 이름과 크기이지만 해시가 다른 파일은 "looks like <제목>, another revision"이다. 업로드
  작업은 표시만 한다. 단일 파일로 고른 폰트 옆의 라이선스 파일은
  그것도 함께 골랐을 때(또는 폴더를 골랐을 때)만 사용한다.
- **독점 폰트는 배포하지 않는다**: 독점 폰트, 비트맵, 테이블은 이 저장소와 maker 어디에도 없다.
  테스트는 합성 입력을 만들며, 실제 파일에 대한 검사는 환경 변수가 사용자 본인의 사본을 가리킬 때만 실행된다
  (`SVF_MAKER_REAL_MAC1`, `_MAC3`, `_NAMEDFORK`, `_PFT`, `SVF_MAKER_REAL_86BOX`, `SVF_MAKER_REAL_MAME`, ...). 내장 레시피는 독점 파일의 이름, 크기,
  해시, 오프셋을 담을 뿐 그 바이트는 담지 않는다.
- maker에는 외부로 연결하는 코드가 없고 어디로도 아무것도 보내지 않는다(텔레메트리, 충돌 업로드, 업데이트 확인 없음). 테스트는 maker 자신의 모듈이 네트워크 라이브러리를 임포트하지 않는지, 그리고 프로세스 내 소켓 감시자가 127.0.0.1 외의 어떤 연결도 보지 못하는지를 검사하지만, 그 도구 하위 프로세스는 보지 못한다. 유일한 선택적
  외부 구성 요소는 정체성 검사이다. `SVF_RECOG_DIR`이 사용자 본인의 `recog.py`를 가리키며, 네트워크 없음 테스트는
  그 외부 코드를 다루지 않는다.

## 데스크톱 앱

`desktop/`은 이 서버를 감싼 Electron 셸이다. 패키징된 앱은 동결된(frozen) 사이드카
(`svf-maker-sidecar serve --exit-with-parent=<pid>`, 서버와 모든 도구의 PyInstaller one-dir 번들)를
새 `SVF_MAKER_TOKEN`, `SVF_MAKER_BIND=127.0.0.1:0`, 자체 데이터 루트 `~/.config/svf-maker/maker`와 함께 시작하고,
stdout 줄("svf-maker listening on 127.0.0.1:<port>")에서 포트를 읽어 `http://127.0.0.1:<port>/`를 로드하며, `/api/` 요청에 토큰
헤더를 붙이고, 페이지에 `window.svfMaker`(함수 네 개)를 제공하고, 종료할 때 사이드카를 멈춘다. 번들에서는
모든 도구가 같은 실행 파일이다: `svf-maker-sidecar run-tool <name> ...`(`maker/toolrun.py`가
argv를 만들며, 소스 모드는 여전히 `python3 -P tools/<name>.py`를 실행한다). 앱은 네트워크 연결을 만들지 않는다. 페이지의 CSP는
자기 오리진만 허용하고, 셸은 그 밖의 모든 요청을 취소하며, maker에는 외부로 나가는 코드가 없다(위 참조).

선택적 구성 요소는 번들 밖에 둔다. 정체성 검사는 `SVF_RECOG_PYTHON`(절대 경로이며 시작 시 numpy, torch, PIL, fontTools를 한 번 점검함)으로 지정한
인터프리터에서 `SVF_RECOG_DIR`과 함께 실행되고, mask-fit 라이브러리는 `JAMOSET_PYLIB`에서 가져온다. 패키징된 저장소 트리는
그 인터프리터를 위해 `maker/*.py`와 `tools/*.py`를 소스로 담고 있다.

Linux에서 git 체크아웃으로 빌드한다(설치와 첫 실행: `docs/desktop-app.ko.md`의 빠른 시작, 기록, 버전, 수치:
`docs/maker-desktop.ko.md`). `cd desktop && npm ci && node node_modules/electron/install.js` 다음에 체크아웃 루트에서
`bash desktop/build/build-appimage.sh`를 실행한다(작성자는 `~/.local/bin/heavy` 아래에서 실행하지만 이는 선택 사항이다).
emsdk(`$EMSDK`, 기본값 `~/opt/emsdk`, 스크립트가 WASM 모듈을 직접 빌드함), pip가 있는 Python 3.12, npm이 있는 node 22,
`xvfb-run`(스모크 검사용), 시스템 `python3`용 Pillow와 fontTools(동결 테스트와 개발 실행이 maker를 import한다. apt:
`python3-pil python3-fonttools`)가 필요하다. 동결된 사이드카를 빌드하고 `THIRD-PARTY.txt`와
`desktop/dist/svf-maker-<version>.AppImage`를 생성하며 릴리스 검사를 실행한다. 패키징 없이 체크아웃에서 앱을 실행하려면:
`cd desktop && npm ci && node node_modules/electron/install.js && bash ../maker/build-wasm.sh &&
node_modules/.bin/electron --no-sandbox .`(`--no-sandbox`는 사용자 네임스페이스가 막힌 곳에서만). Windows와 macOS 패키지는
빌드하지도 검증하지도 않았다. 절차는 `docs/maker-desktop.ko.md`에 적혀 있으며 서버는 Windows에 대응하지 않는다.

## 선택적 환경 변수

- `JAMOSET_PYLIB` - freetype-py와 uharfbuzz가 들어 있는 폴더. `mask fit` 경로와 `binarize mono`용이다
  (없으면 둘은 제공되지 않는다).
- `JAMOSET_MASK_FONT` - `mask fit`이 쓰는, OpenType `ljmo`/`vjmo`/`tjmo`가 있는 폰트(`jamoset.py --mask-font`). `JAMOSET_PYLIB`처럼
  도구에 그대로 전달된다.
- `SVF_MAKER_ROOTS` - 콜론으로 구분한 절대 경로 폴더들. 로컬 모드에서는 모든 소스와 출력 폴더가 이 중 하나 안에 있어야 한다
  (예: `$HOME/fonts:$HOME/svf-out`).
- `SVF_RECOG_PYTHON` - maker가 동결되었을 때 정체성 검사를 실행하는 인터프리터(데스크톱 앱 참조).
- `SVF_RECOG_DIR` - 자모 세트의 조각 정체성 검사를 위한 `recog.py`와 그 가중치가 있는 폴더(numpy와 torch 필요).
  채점 전용이다. 인식기나 가중치는 이 저장소에 없으며, 이 폴더가 없으면 페이지는
  검사를 쓸 수 없다고 알린다.

## 노트

- `GET /api/caps`는 페이지가 로드 시 한 번 호출하며, 로컬 모드가 켜져 있는지(`local`: 업로드 패널 대신 소스 패널)만 알아내기 위한 것이다.
  없는 것(모듈, 라이브러리, 인식기)은 여전히 알림과
  폰트 항목의 `mask_ok`로 알아낸다.
- 서버는 구워진 소스(DOS 원시 또는 SVF 항목)에 대해 여전히 PNG를 `work/preview/<font>.png`로 렌더링한다. 페이지는
  더 이상 이를 보여 주지 않지만(WASM으로 구워진 페이스를 그린다), `test_preview.py`와 소스 PNG 경로가 이를
  바이트 오라클의 이미지 형태로 사용하므로 남겨 둔다. 그 밖에는 이것에 의존하는 것이 없다.
- 서버를 멈추면(SIGTERM, SIGINT 또는 종료) 실행 중인 작업을 취소하고 그 도구 프로세스를 죽인다(각각 자기
  세션에서 실행됨). 대기 중인 업로드 작업은 대기 상태로 남아 다음 시작 때 다시 대기열에 들어간다. 대기 중이거나 실행 중인 로컬 작업은
  실패(`interrupted`)로 표시된다. 파일 디렉터리가 프로세스와 함께 사라지기 때문이다.

## 로컬 모드: 셸 쪽, 그리고 실행하지 않은 것

셸(카드 t_f04f1355)은 `SVF_MAKER_TOKEN`과 `SVF_MAKER_BIND=127.0.0.1:0`으로 서버를 시작하고, stdout 줄에서 포트를
읽어 `http://127.0.0.1:<port>/`를 로드하고, 모든 `/api/` 요청에 `X-Maker-Token`을 붙이고, `window.svfMaker`
(`pickFiles`, `pickFolder`, `pickOutputDir`, `openOutputFolder`. 경로는 절대 경로이고, 취소된
대화상자는 `[]`/`null`을 주며, `openOutputFolder`는 인자를 받지 않는다)를 노출하고, SIGTERM으로 서버를 멈춘다. 전체 계약과
카드의 종료 측정에 대한 증거는 `docs/maker-audit.md` 8절에 있다. 여기서 검증하지 않은 것: `unshare -rn`,
실제 Mac/HWP 파일, macOS 이름 있는 포크, Electron과 네이티브 대화상자, FAT/exFAT/SMB 마운트, 디스크 가득 참, 대소문자를 구분하지 않는
파일시스템, 동기화 클라이언트.

## 실행하지 않은 것

- **`mask fit` 경로는 작업을 한 번도 실행한 적이 없다**: freetype-py와 uharfbuzz(`JAMOSET_PYLIB`)가 필요한데, 이를 만든 호스트에
  설치되어 있지 않다. 그 argv, 제공 여부, 거부는 테스트하지만 결과는 테스트하지 않았다.
- **실제 인식기로 정체성 검사를 실행한 적이 없다**. 테스트는 파일에서 음절을 읽는 스텁을 쓴다.
  numpy/torch 경로는 검증되지 않았다.
- **`vector fit`는 폰트당 몇 분이 걸린다**: NanumGothic Regular에 대한 `jamovec.py master`는 OOM 가드 아래에서 172초로 측정되었다(렌더는 1초 미만).
  합성 테스트 폰트에서는 작업 전체가 1.1초 걸린다.

## 테스트

    export TMPDIR=$HOME/work/tmp/maker-tests; mkdir -p $TMPDIR                        # scratch, never /tmp
    flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'   # the maker suite (it starts Chrome)
    ~/.local/bin/heavy python3 -m unittest discover -s tools -p test_web_picker.py   # the module and the picker
    flock $HOME/work/tmp/svf-browser.lock python3 maker/test/smoke_dom.py              # the page in headless Chrome

종단 간(end-to-end) 테스트(t_e073891a)이며, 각각 위 스위트에도 포함된다(`TMPDIR`을 위와 같이 설정):

    python3 -m unittest discover -s maker/test -p test_e2e.py            # about 9 s
    SVF_MAKER_SLOW=1 ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p test_e2e.py -k SlowFit   # about 85 s
    flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p test_ui_smoke.py

- `test_e2e.py`: `UploadEndToEndTest`와 `LocalEndToEndTest`는 섞인 폴더 하나(TTF + BDF + johab PCF + DOS 원시
  844, 그리고 업로드 모드에서는 배포된 SVF 하나)를 실제 HTTP 서버를 통해 업로드 모드(zip)와 로컬 모드(출력
  폴더)로 변환한다. 모든 단계와 역할을 검사하고, 출력이 `facecheck.py`를 통과하며, 소유자가 사이드카 `.lines` 파일을 병합한 결과가
  `web/mkindex.py --check`를 통과하고, 모든 페이스가 U+AC00을 그린다. `PresetAcceptanceTest`는 `dos-u-2bpp` 프리셋을 17 px로
  업로드 작업을 통해 굽는다. 페이스는 `svf/dos/GBATB17.SVF`와 바이트 단위로 같고, 동일하므로 건너뛰며, 그 행이 목록에 오른다.
  `SlowFitTest`(실험적인 2 bpp 피팅, 품질 한계)는 `SVF_MAKER_SLOW=1`일 때만 실행되고 그 외에는 건너뛴다.
  픽스처는 합성이거나 `ttf/`와 `svf/`에서 복사한 것이다(`e2efx.py`).
- `test_ui_smoke.py`: 업로드 페이지를 헤드리스 Chrome에서 한 번 구동한다(`pagedrive.mjs --files '#files=PATH'`가 zip을 파일
  입력에 넣는다). 업로드, 배치 컨트롤, 저장, 실행, 그려진 캔버스, 다운로드 링크까지 거친다.

Chrome(또는 Electron)을 시작하는 모든 실행은 브라우저 락과 heavy 가드를 잡는다:
`flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy ...`(위의 전체 스위트는 브라우저 테스트를 포함하므로 그 명령은 둘 다 쓴다). 스크래치는
프로젝트 영역 아래에 두며 `/tmp`는 쓰지 않는다: `export TMPDIR=$HOME/work/tmp/<name>`(테스트는 이를 따르는 `tempfile`을 쓴다).

페이지 테스트(`test_page_dom.py`, `test_ui_smoke.py`, `smoke_dom.py`)는 google-chrome 또는 chromium-browser, node, 빌드된
모듈이 필요하며 없으면 건너뛴다. `docs/maker-audit.md`는 설계 상태와 공백 목록을 기록한다.
