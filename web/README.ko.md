[English](README.md) | **한국어**

# WASM 폰트 선택기 (카드 t_fe9f6c30)

WebAssembly로 컴파일한 C 렌더러(`c/ports/web/svf_web.c`,
`c/ports/web/README.md` 참조)를 통해 SVF 페이스(face)로 텍스트를 그리는 정적 페이지이다. 크기, 패밀리, 변형(variant)을 고르고,
라틴 페이스와 한글 페이스, 배율, 렌더 대상을 정한 다음, 게임 폰트에 대한 선택을 기록해 `selection.json`(폰트 짝짓기 선택)으로 내보낸다. 이것을
게임 맵으로 바꾸는 도구는 게임 쪽에 속했으며 이 저장소에는 없다.

## 빌드와 서빙

    bash web/build.sh [OUT]                    # 기본값 web/dist; emsdk 필요 ($EMSDK, 기본값 ~/opt/emsdk)
    python3 -m http.server -d web/dist         # 그 뒤 http://localhost:8000/ 을 연다

`build.sh`는 svf.wasm과 svf.js, `faces.json`(`web/mkindex.py`), `faces/<group>/<FILE>.SVF`와
`licences/<group>/<FILE>`(`web/copyfaces.py`)을 쓰고 index.html, picker.js, style.css를 복사한다. OUT 아래에만 쓰며
`svf.wasm N bytes, svf.js N bytes, F faces, N MB copied`를 출력한다.

**`web/dist`는 로컬 용도이다.** 라이선스가 명시되지 않았거나 출처가 독점인 페이스(`LICENCES.tsv`의 노트 참조)와,
Reserved Font Name을 가진 채 변환된 OFL 페이스를 번들한다. 그대로 공개하지 않는다.

커밋하는 것: `index.html`, `picker.js`, `style.css`, `build.sh`, `mkindex.py`, `copyfaces.py`, `LICENCES.tsv`, `FAMILIES.tsv`,
`test/`(`node_modules`와 `out` 제외). 생성되며 커밋하지 않는 것: `web/dist/`, `web/test/out/`,
`web/test/node_modules/`.

## 페이스 색인 (`mkindex.py`)

    python3 web/mkindex.py svf OUT_JSON [--licences TSV] [--families TSV]
    python3 web/mkindex.py svf --check                  # 모든 검사 실행, 아무것도 쓰지 않음

`svf/**/*.SVF`마다 항목 하나가 있다. 헤더 값 외에 `hangul`(페이스가 그리는 KS X 1001 음절 2,350자 중 몇 자인지),
`latin_only`, `subset`, 그리고 `family`, `style`, `variant`를 담는다.

- **서브셋 규칙:** 자모 세트가 아니고, 라틴 전용도 아니며, 음절을 2,350자보다 적게 그리는 페이스는 `subset`이다. 서브셋
  페이스(게임별 보충)는 색인에는 있지만 숨겨진다. 칩, 행, 선택 항목이 없으며, 이를 가리키는 URL은 거부된다.
- **라틴 전용 규칙:** 자모 세트가 아니고, `hangul == 0`이며, 출력 가능한 ASCII 문자 U+0021..U+007E가 모두 cmap에 있는 경우(공백 제외). 이런 페이스는
  라틴 선택에만 제공되며, 한글 페이스나 패밀리 목록에는 나오지 않는다.
- **개수 줄**, `mkindex.py`가 마지막에 출력하는 줄: `153 faces, 120 listed (2 latin-only), 33 subset, 0 unmapped`. listed =
  서브셋이 아닌 것(라틴 전용 포함).

### FAMILIES.tsv

탭으로 구분하며 `#`로 시작하는 줄과 빈 줄은 건너뛴다. 헤더 행이 열 이름을 정하며, `file`과 `family`는 필수이고 `style`과
`variant`는 선택이며, 다른 열은 무시한다. 목록에 오르는 페이스마다 한 행이며, `file`은 색인 키 `svf/<rel>`이다. style이나
variant가 비어 있어도 된다. 헤더보다 짧은 행은 빈 셀로 채운다. 서브셋 페이스는 행이 필요 없다.

`mkindex.py`는 다음 경우에 종료 코드 2로 끝나고, `FAMILIES.tsv:<line>` 또는 페이스를 지목하며, 아무것도 쓰지 않는다.

- 헤더에 `file` 또는 `family`가 없거나, 열 이름이 반복되거나, 헤더가 없는 경우;
- 행에 헤더보다 많은 셀이 있거나, `file`이 비어 있거나, `file`이 `svf/`로 시작하지 않거나, 앞선 줄에 이미 나온 파일인 경우;
- family, style, variant가 256자를 넘는 경우;
- 목록에 오르는 페이스에 행이 없거나, 그 행의 family가 비어 있는 경우;
- 행이 페이스가 아닌 파일을 지목하는 경우(오래된 행);
- 목록에 오르는 두 페이스가 family, style, px, bpp, 구성(자모), 셀 크기, variant를 모두 공유하는 경우(충돌: 하나에 `variant`를 준다).

라이선스 검사가 먼저 실행되므로, 매핑되지 않은 페이스와 빠진 family 행이 모두 있는 트리는 라이선스 오류를 보고한다.
`--families`는 다른 표를 지정한다(테스트는 픽스처를 사용한다).

**페이스 추가하기:** `.SVF`를 `svf/` 아래에 두고, `web/LICENCES.tsv`에 행 하나(라이선스 파일에 대한 glob)를, `web/FAMILIES.tsv`에
행 하나(file, family, style, variant)를 추가한 뒤 `python3 web/mkindex.py svf --check`를 실행한다.

## 알아 둘 페이지 동작

URL 매개변수(로드 시 읽으며, 모든 오류는 알림과 기본값으로 처리하고 예외를 내지 않는다):

| 매개변수 | 값 | 대체 동작 |
| --- | --- | --- |
| `hangul` | 목록에 오른(왼쪽 목록) 페이스의 키 | 없음: 기본 NGOTB16이 열리고 알림 없음. 비어 있음, 알 수 없음, 숨겨진 서브셋, 라틴 전용: 기본값이 열리고 알림이 뜬다 |
| `latin` | 서브셋이 아닌 페이스의 키, 또는 없음을 뜻하는 빈 값 | 없음: 한글 페이스 자체의 것. 알 수 없음 또는 서브셋: 없음, 알림이 뜬다. 빈 값: 없음 |
| `scale` | `n/d`, 각각 1..16 | 1/1, 알림이 뜬다 |
| `manual` | 존재 | 아무것도 열지 않는다(기본값 없음, 프리페치 없음). `scale`은 여전히 읽으며, 잘못된 페이스는 여전히 알림이 된다 |

2,048자를 넘는 쿼리, 또는 256자를 넘는 키나 값은 무시된다("URL ignored: too long"). 선택(pick), select,
`setScale`은 URL을 다시 쓰고(이력 항목 없음) 다른 매개변수는 유지하며, 새로고침하면 체인이 복원된다.

**알림 요소**(`#notice`, `role="status"`, 비어 있으면 숨김)는 URL 오류, 읽을 수 없는 저장된 선택값
("stored choices unreadable: starting empty" 또는 "N stored choices skipped: not valid"), 저장 실패, 그리고
크기 프리페치의 요약을 보여 준다. URL 알림은 유지되고 프리페치 요약이 그 뒤에 덧붙으며("; "), 이후 동작이 알림을 지운다.

게임과 id는 하나의 선택이다. `addChoice`는 (공백을 제거한 뒤) 중복을 거부하며, 로더는 중복 중 첫 번째를 유지하고 알림에서 그 사실을 알린다. `korean.scale`은 입력한 그대로의 비율이다. 키가 더 이상 색인에 없는 저장된 선택은 유지되고, 표시되며, 내보내진다.

저장된 선택은 `localStorage`(`svfpicker.choices`)에 있으며 최대 256개이고, 각각 `addChoice`의 규칙을 따른다(이름에는 제어
문자(C1 포함)가 없고 게임과 id에 `|`가 없다. `lineh`는 없거나 1..65535. 게임과 id는 앞뒤 공백 제거).

## 내보내기

`window.picker.exportJSON()`(Download 버튼, `selection.json`)은 `scummvm-ko-font-pairing/1`을 쓴다: `format`, `created`,
`order`(`"per-run"`), `source`, `games[{game, fonts[...]}]`. 폰트 항목은 `id`, `picked`, 선택적인 `lineh`, `korean` 블록을 가진다. 각 `korean` 블록은 `key`, `file`, `label`(색인의
label), `family`, `style`, `variant`, `latin`, `scale`, `w`, `h`, `bpp`, `ascent`를 가진다. 게임과 id에는 제어
문자와 `|`가 없으므로(선택기가 `addChoice`와 저장된 선택 모두에서 둘 다 거부한다), 소비하는 쪽은 이를 줄 단위
맵과 Markdown 표에 그대로 쓸 수 있다.

## window.picker

페이스 선택: `listed()`(`subset`이 false인 페이스, 라틴 전용 포함), `sizes()`(칩의 px 목록), `families(px)` ->
`[{family, style, name, faces, default}]`(라틴 전용 제외), `defaultVariant(family, style, px)` -> 키 또는 `null`,
`pick(key)`(= `select({latin: key, hangul: key})`, 프리페치 없음. 왼쪽 목록 페이스가 아닌 키는 거부),
`setSize(px)`(칩을 보여 주고, 해당 크기를 프리페치하며, `{px, fetched, held, skipped, failed, stopped}`로 resolve한다. 페이스가 없는 px에는 reject),
`view()` -> `{px, family, style, variant, hangul, latin, same, listed}`, `notice()`(`#notice`의 텍스트).

이전 호출: `presets`, `faces()`, `select({latin, hangul})`, `prefetch(key, keep)`, `lacking(text)`, `faceMemory()`, `setFaceBudget(n)`,
`setText`, `setScale`, `setTarget`, `render`, `chain()`, `addChoice({game, id, lineh})`, `choices()`, `removeChoice(i)`,
`exportJSON()`. `ready`는 모듈, 색인, 기본 짝이 로드되면 resolve된다. 테스트 훅: `setNotice`,
`holdHeap`, `pendingKeys`, `prefetching`, `idle`, `module`, `spyAfterPick`, `licence`, `runs`, `pixels`, `settings`, `covers`.

## 테스트

    python3 -m unittest discover -s tools -p 'test_*.py'

- **TestIndex**(브라우저 없음): `svf/`와 픽스처 트리에 대한 `mkindex.py`. Python만 필요하다.
- **TestCopyFaces**(브라우저 없음): `web/copyfaces.py`가 `faces.json`이 지목하는 모든 경로를 `svf/`와 OUT 아래에 유지한다. Python만 필요하다.
- **TestModule**: `build.sh`로 임시 디렉터리에 모듈을 빌드하고 node에서 `web/test/render.mjs`로 그린다. 모든
  버퍼가 `tools/svfline.py`와 같아야 한다. emcc(`$EMSDK`, 기본값 `~/opt/emsdk`)나 node(`$NODE`,
  `~/opt/node-v24.13.0-linux-x64/bin/node`, 그다음 PATH)가 없으면 건너뛴다.
- **TestPage**와 **TestExportShape**: `web/test/check.mjs DIST OUT`을 한 번 실행하고(playwright-core, Chrome, 빌드된 dist),
  그 출력(`faces-report.tsv`, PNG, `cases.txt`, `selection.json`)을 `web/test/out/`에서 검사한다. `web/test/node_modules`가
  없거나(`cd web/test && npm ci`), 실행되는 Chrome이 없거나(`PICKER_BROWSER=/path/to/chrome`으로 지정), emcc/node가 없으면 건너뛴다.

직접 실행: `node web/test/check.mjs web/dist web/test/out`(종료 코드 0은 정상, 1은 케이스 실패, 2는 실행 불가).
C 렌더러 자체의 테스트: `make -C c check`.
