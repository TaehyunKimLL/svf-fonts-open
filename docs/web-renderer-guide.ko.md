[English](web-renderer-guide.md) | **한국어**

# SVF 웹 렌더러 사용법

WebAssembly 렌더러는 C 렌더러를 브라우저와 Node에서 호출한다. 페이스를 `fetch`로 받아 WASM 메모리에 복사하고,
슬롯을 연 뒤 UTF-8 텍스트를 픽셀 버퍼에 그린다. `<canvas>`에는 그 결과를 `ImageData`로 변환해서 올린다.
C 앱의 직접 메모리 접근과 스트리밍은 [C 가이드](c-renderer-guide.ko.md), 파일 구조는 [SVF 명세](../spec/SVF.ko.md),
조합 원리는 [자모 세트](jamo-sets.ko.md)를 참고한다.

## 1. 빌드와 파일 배치

emsdk를 설치하고 활성화한다. `EMSDK`는 `upstream/emscripten/emcc`와 `.emscripten`이 들어 있는 SDK 루트다.
아래 명령은 기본 설치 경로를 사용한다. 이미 설치했다면 설치 명령은 생략한다.

```sh
sh c/cross/install-toolchains.sh "$HOME/opt" emsdk
. "$HOME/opt/emsdk/emsdk_env.sh"
EMSDK="$HOME/opt/emsdk" bash web/build.sh /tmp/svf-picker
python3 -I -m http.server 8000 --directory /tmp/svf-picker
```

`http://localhost:8000/`에서 전체 picker를 연다. [web/build.sh](../web/build.sh)는 `svf.js`, `svf.wasm`,
페이지와 페이스 인덱스를 출력한다. 별도 앱에서는 JS·WASM과 자신이 쓸 페이스 및 라이선스 파일만 배치하면 된다.
JS와 WASM은 같은 디렉터리에 두거나 모듈 팩토리의 `locateFile` 옵션으로 WASM URL을 지정한다.[1]

모듈만 빌드하려면 공통 [emcc-flags.sh](../c/ports/web/emcc-flags.sh)를 사용한다. 출력 디렉터리를 먼저 만든다.

```sh
mkdir -p /tmp/svf-module
. c/ports/web/emcc-flags.sh
svf_web_compile "$PWD" /tmp/svf-module
```

플래그는 ES 모듈 팩토리 `SvfModule`, `web,node` 환경, `_malloc`·`_free`, `HEAPU8`·`HEAP16`·`HEAP32`,
메모리 증가를 활성화한다. `await SvfModule()` 뒤에 API를 호출한다. `svf.js`만 복사하면 WASM을 찾지 못한다.
HTTP(S)로 서빙하고 `.wasm` MIME은 `application/wasm`으로 설정한다.[3] `file://`로 페이지를 열지 않는다.

## 2. 최소 완전한 HTML 페이지

다음 파일을 `example.html`로 저장하고 같은 디렉터리에 `svf.js`, `svf.wasm`, `NEODG16A.SVF`를 둔다.
서버에서 `/example.html`을 열면 호박색 텍스트와 측정값이 나온다. 슬롯이 페이스 핸들 역할을 한다.
`_svfw_open`의 두 번째 인자는 JS 배열이 아니라 WASM 주소다.

```html
<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<title>SVF canvas</title>
<canvas id="text"></canvas>
<pre id="status"></pre>
<script type="module">
import SvfModule from './svf.js';
const status = document.querySelector('#status');
try {
  const M = await SvfModule();
  const owned = [];
  function alloc(n) {
    const p = M._malloc(Math.max(n, 1));
    if (!p) throw new Error('Out of WASM memory');
    owned.push(p);
    return p;
  }
  function put(bytes) {
    const p = alloc(bytes.length);
    M.HEAPU8.set(bytes, p);
    return p;
  }
  function check(name, result) {
    if (result !== 0) throw new Error(`${name}: svf_err ${result}`);
  }
  try {
    const response = await fetch('./NEODG16A.SVF');
    if (!response.ok) throw new Error(`Font HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    const face = put(bytes);
    check('open', M._svfw_open(0, face, bytes.length));
    const info = alloc(32);
    check('info', M._svfw_info(0, info));
    const cellWidth = M.HEAP32[(info >> 2) + 1];
    const faceStatus = M.HEAP32[(info >> 2) + 5];
    const utf8 = new TextEncoder().encode('SVF 한글');
    const text = put(utf8), extent = alloc(6);
    check('scale', M._svfw_scale(2, 1));
    check('measure', M._svfw_measure(text, utf8.length, extent));
    const width = M.HEAP16[extent >> 1];
    const ascent = M.HEAP16[(extent >> 1) + 1];
    const descent = M.HEAP16[(extent >> 1) + 2];
    // Width is pen travel. Leave room for cell overhang at scale 2/1.
    const w = width + 2 * cellWidth + 4, h = ascent + descent + 4;
    const pixels = alloc(w * h);
    M.HEAPU8.fill(0, pixels, pixels + w * h);
    check('target', M._svfw_target(pixels, w, h));
    check('draw', M._svfw_draw(text, utf8.length, 2, ascent + 2));
    const image = new ImageData(w, h);
    const fg = [255, 192, 0], bg = [16, 24, 32];
    // Reacquire HEAPU8 after any call that can allocate or grow memory.
    const coverage = M.HEAPU8.subarray(pixels, pixels + w * h);
    let ink = 0;
    for (let i = 0; i < coverage.length; ++i) {
      const a = coverage[i];
      if (a) ++ink;
      for (let c = 0; c < 3; ++c)
        image.data[4 * i + c] = Math.round((bg[c] * (255 - a) + fg[c] * a) / 255);
      image.data[4 * i + 3] = 255;
    }
    const canvas = document.querySelector('canvas');
    canvas.width = w; canvas.height = h;
    canvas.getContext('2d').putImageData(image, 0, 0);
    status.textContent = `status=${faceStatus} width=${width} ascent=${ascent} descent=${descent} ink=${ink}`;
  } finally {
    check('reset', M._svfw_reset()); // Stop referring to face bytes before freeing them.
    for (const p of owned.reverse()) M._free(p);
  }
} catch (err) { status.textContent = String(err); console.error(err); }
</script>
</html>
```

`svfw_measure`는 `int16` 세 개(전진 폭·ascent·descent)를 쓰므로 6바이트를 할당하고 `HEAP16`으로 읽는다.
폭은 잉크 경계가 아니다. 마지막 셀의 돌출과 왼쪽 결합 부호에 여백을 더하고, 큰 줄은 나누어 그린다.
`x`와 기준선은 출력 픽셀 단위다. `_svfw_draw`는 이를 `int16_t`로 변환하므로 -32,768..32,767 범위의 정수로 넘긴다.
측정 폭은 32,767로 포화된다. 한 호출은 한 줄이다. 줄바꿈·줄 배치는 앱에서 처리한다.
GRAY8은 기존 값과 피복도의 최댓값을 취하므로 매 프레임 마스크를 0으로 지운다.
투명 텍스트라면 RGB를 전경색으로, 알파를 피복도로 채우고 캔버스에서 합성할 수도 있다.[4]

## 3. 색상과 RGB565 출력

위 예제의 GRAY8은 색 자체가 아닌 피복도다. 따라서 JS에서 원하는 전경·배경색을 선택할 수 있다.
직접 RGB565를 그리려면 `2*w*h`바이트를 할당하고, 배경색의 하위·상위 바이트로 전체 버퍼를 채운 다음
`_svfw_target2(3, ptr, 2*w*h, w, h, 2*w, fg565, bg565, 128, 0)`을 호출한다.
색상 타깃은 알려진 배경색과 혼합하며 대상 픽셀을 읽지 않는다. 안 그린 픽셀은 초기화한 배경으로 남는다.
`flags=0`일 때 하위 바이트가 먼저다. `flags=1`이면 상위 바이트가 먼저이므로 아래 변환의 바이트 순서를 바꾼다.
그린 뒤 다음 함수의 반환값을 `putImageData`에 넘긴다.

```js
function rgb565Image(M, ptr, w, h, stride) {
  const image = new ImageData(w, h);
  const bytes = M.HEAPU8; // target flags=0: low byte first
  for (let y = 0; y < h; ++y) for (let x = 0; x < w; ++x) {
    const p = ptr + y * stride + 2 * x, v = bytes[p] | (bytes[p + 1] << 8);
    const o = 4 * (y * w + x);
    image.data[o] = Math.round(((v >> 11) & 31) * 255 / 31);
    image.data[o + 1] = Math.round(((v >> 5) & 63) * 255 / 63);
    image.data[o + 2] = Math.round((v & 31) * 255 / 31);
    image.data[o + 3] = 255;
  }
  return image;
}
```

RGB565의 빨강·파랑은 5비트, 초록은 6비트이므로 색 정밀도가 줄어든다. 이 래퍼는 C 코어의 XRGB8888·RGB888을
노출하지 않는다. 24/32비트 캔버스 색상에는 GRAY8을 변환한다. MONO_PAGE는 종류 1, stride `w`, 길이
`w*ceil(h/8)`이며 MONO_ROW는 종류 2, stride `ceil(w/8)`, 길이 `stride*h`다. 단색은 threshold로 판정한다.

## 4. Node에서 그리기

다음을 `example.mjs`로 저장한다. 브라우저와 같은 모듈을 사용하며 `fetch` 대신 파일 바이트를 복사한다.

```js
// node example.mjs /absolute/path/to/module /path/to/FACE.SVF
import { readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
const [dir, path] = process.argv.slice(2);
if (!dir || !path) throw new Error('usage: example.mjs MODULE_DIR FACE');
const M = await (await import(pathToFileURL(join(resolve(dir), 'svf.js')).href)).default();
const owned = [];
function alloc(n) {
  const p = M._malloc(Math.max(1, n));
  if (!p) throw new Error('Out of WASM memory');
  owned.push(p); return p;
}
function put(bytes) { const p = alloc(bytes.length); M.HEAPU8.set(bytes, p); return p; }
function check(name, e) { if (e !== 0) throw new Error(`${name}: svf_err ${e}`); }
try {
  const bytes = readFileSync(path);
  check('open', M._svfw_open(0, put(bytes), bytes.length));
  const utf8 = new TextEncoder().encode('SVF 한글');
  const text = put(utf8), extent = alloc(6);
  check('scale', M._svfw_scale(1, 1));
  check('measure', M._svfw_measure(text, utf8.length, extent));
  const [width, ascent, descent] = M.HEAP16.slice(extent >> 1, (extent >> 1) + 3);
  const w = 128, h = 32, pixels = alloc(w * h);
  M.HEAPU8.fill(0, pixels, pixels + w * h);
  check('target', M._svfw_target2(0, pixels, w * h, w, h, w, 0xffff, 0, 128, 0));
  check('draw', M._svfw_draw(text, utf8.length, 0, 20));
  const output = M.HEAPU8.slice(pixels, pixels + w * h);
  console.log(`width=${width} ascent=${ascent} descent=${descent} ink=${output.filter(v => v !== 0).length}`);
} finally {
  check('reset', M._svfw_reset());
  for (const p of owned.reverse()) M._free(p);
}
```

```sh
node example.mjs /tmp/svf-module svf/dos/NEODG16A.SVF
node web/test/render.mjs /tmp/svf-module '{"faces":["svf/dos/NEODG16A.SVF"],"text":"SVF 한글","kind":"gray8","w":128,"h":32,"x":0,"baseline":20}' > /tmp/svf-gray8.raw
```

첫 명령은 측정값과 잉크 픽셀 수를 출력한다. 두 번째는 [render.mjs](../web/test/render.mjs)의 완전한 실행 예로,
4096바이트의 원시 피복도를 파일에 쓴다. JSON 파일 경로도 받을 수 있고, spec 배열을 주면 같은 모듈로 연속 처리한다.
알 수 없는 타깃 종류·존재하지 않는 페이스·필수 인자 누락은 종료 2, API 오류는 종료 3이다.
JSON 파싱·파일 읽기 예외는 Node의 처리되지 않은 예외로 종료하므로 모든 인자 오류가 종료 2인 것은 아니다.

## 5. API와 수명

실제 계약은 [svf_web.c](../c/ports/web/svf_web.c), 전체 목록은 [Web 포트](../c/ports/web/README.ko.md)에 있다.
함수 앞의 `_`는 Emscripten이 JS에 내보내는 이름이다. 대부분 0 성공, 그 외 `svf_err`이며 아래 예외를 구별한다.

| 호출 | 용도와 주의점 |
|---|---|
| `_svfw_open(slot, ptr, len)` | 슬롯 0부터 순서대로 최대 4개. 다시 열면 이후 슬롯을 닫으며 실패하면 열린 체인이 거기서 끝난다. |
| `_svfw_reset()` | 모든 슬롯을 닫는다. 페이스 메모리를 해제하기 전에 호출한다. |
| `_svfw_info(slot, out)` | 32바이트, `HEAP32`: bpp, cell_w, cell_h, ascent, flags, status, glyph count, is_jamo. 열기 성공 뒤에도 status를 확인한다. |
| `_svfw_has(slot, cp)` | 지원 여부 1/0. 슬롯 오류도 0. |
| `_svfw_order(first)` | 기존 슬롯의 우선순위만 변경. open/reset은 원래 순서로 복구. |
| `_svfw_scale(num, den)` | 각각 정수 1..16. 측정 전에 설정. 정수 확대는 픽셀 블록, 분수 배율은 면적 평균. |
| `_svfw_measure(text, len, out)` | UTF-8 바이트 수와 6바이트 출력. |
| `_svfw_draw(text, len, x, baseline)` | 마지막으로 설정한 타깃으로 한 줄 그리기. 타깃 범위로 클리핑. |
| `_svfw_metrics(slot, cp, out)` | 16바이트 `HEAP32`: advance, bearing_x, ink_w, dy. 반환 1 메트릭 있음, 0 기본값, -1 없음/잘못된 인자. |
| `_svfw_line_box(text, len, x, baseline, out)` | 16바이트 `HEAP32`: x, baseline-ascent, width, baseline+descent. 마지막 값은 높이가 아닌 아래 좌표다. |
| `_svfw_cell_bytes`, `_svfw_glyph`, `_svfw_pieces`, `_svfw_cmap_cp` | 셀 추출·조각·코드 포인트 조사. 정확한 출력 타입과 반환 센티널은 포트 레퍼런스 참고. |

한글+라틴은 바이트를 각각 보관하고 슬롯 0과 1에 연다. 기본은 해당 문자를 가진 첫 슬롯이 그린다.
동일 문자가 두 페이스에 있으면 `_svfw_order`로 우선순위를 바꿀 수 있다. picker는 한글·라틴 런별로 순서를 바꾸며
측정과 그리기에 같은 순서를 사용한다. 이는 자동 폰트 셰이핑이 아니다.

## 6. 전체 picker와 window.picker

[폰트 선택 페이지](../web/README.ko.md)는 지연 로딩, 페이스 조합, 줄별 캔버스, 색상과 배율, 선택 내보내기를
보여 주는 완전한 앱이다. 페이지의 개발자 콘솔에서는 `await window.picker.ready` 뒤에 다음 API를 쓴다.

| API | 용도 |
|---|---|
| `faces()`, `listed()`, `sizes()`, `families(px)` | 인덱스와 선택 가능한 크기·패밀리 조회. `listed()`는 Latin-only도 포함. |
| `pick(key)`, `select({latin, hangul})`, `setSize(px)` | 비동기 선택. `pick`은 목록의 한글 페이스만 받음. `setSize`는 크기 목록과 프리페치를 갱신. |
| `setText(s)`, `setScale(n,d)`, `setTarget(opts)`, `render()` | 텍스트·배율·타깃을 정하고 렌더링. |
| `chain()`, `view()`, `covers(text)`, `lacking(text)` | 선택 상태와 문자 지원 확인. |
| `addChoice({game,id,lineh})`, `choices()`, `removeChoice(i)`, `exportJSON()` | 현재 조합을 기록·조회·삭제·JSON 내보내기. |
| `prefetch(key, keep)`, `faceMemory()` | 페이스 선로딩과 메모리 사용량 확인. |

```js
await window.picker.ready;
const p = window.picker;
const face = p.listed().find(f => !f.latin_only);
await p.pick(face.key);
p.setText('SVF 한글');
p.setScale(2, 1);
p.setTarget({kind: 'gray8'});
const result = p.render();
console.log(result, p.faceMemory());
```

이 API는 picker 페이지가 제공하며 WASM 모듈 자체에는 없다. 키는 `faces.json`의 값이며 파일 URL과 구별한다.
전체 옵션과 테스트 훅은 [picker.js](../web/picker.js)와 [check.mjs](../web/test/check.mjs)를 참고한다.

## 7. 성능·메모리·브라우저

| 항목 | 예산과 사용 방식 |
|---|---|
| 페이스 | 파일 전체를 WASM 힙에 복사. 슬롯이 열려 있는 동안 포인터 유지. JS 바이트 배열은 복사 뒤 버릴 수 있음. |
| 텍스트 | JS 문자열 길이가 아니라 `TextEncoder`의 UTF-8 바이트 수. 재사용하면 복사·할당 감소. |
| 타깃 | GRAY8 `w*h`, RGB565 `2*w*h`. `ImageData`는 별도로 JS에 `4*w*h`바이트. |
| scratch | 처음 정적 64 KiB. 더 필요하면 glue가 동적 확장. 스케일이 커질수록 증가. |
| 캐시 | glue는 코어의 음절 캐시를 연결하지 않음. picker는 로드한 페이스를 보관하며 예산으로 관리. |

`_malloc`이나 draw의 내부 할당으로 WASM 메모리가 증가하면 이전 typed-array view는 무효화될 수 있다.
할당·그리기 후에는 `M.HEAPU8` 등을 다시 얻는다.[2] `slice`는 복사본, `subarray`는 살아 있는 뷰다.
여러 프레임에서는 모듈·페이스·텍스트·타깃을 재사용하고 필요한 때만 지우고 다시 그린다. 한 모듈의 체인과 타깃은
전역 상태이므로 비동기 작업은 직렬화하거나 독립 모듈 인스턴스를 쓴다. reset은 슬롯만 닫으며 scale·target과 scratch를
초기화하지 않는다. free 뒤에는 새 타깃을 설정하고 그린다. 동적 scratch는 모듈 수명 동안 유지된다.

브라우저 예제에는 WebAssembly, ES 모듈, async/await, fetch, TextEncoder, Canvas 2D가 필요하다.[3][4]
다른 출처의 페이스·WASM 요청에는 CORS 허용이 필요하다.[5] 구형 브라우저용 JS 폴백은 제공하지 않는다.
Node에서는 ES 모듈과 WebAssembly를 지원하는 버전을 사용한다.[6]

## 8. 관련 문서

[렌더러 설계](../spec/renderer-design.ko.md)와 [안티앨리어싱](anti-aliasing.ko.md)은 스케일·피복도·색상 변환을 설명한다.
페이스 제작·변환은 [레시피](recipes.ko.md), [도구](tools.ko.md), [메이커 앱](maker-desktop.ko.md),
로컬 조회는 [데스크톱 앱](desktop-app.ko.md)을 참고한다. 전체 구성은 [프로젝트 안내](../README.ko.md)에 있다.

## 참고 문헌 / References

1. Emscripten, modular output and module options: https://emscripten.org/docs/compiling/Modularized-Output.html ; https://emscripten.org/docs/api_reference/module.html
2. Emscripten, JavaScript memory access and growth: https://emscripten.org/docs/porting/connecting_cpp_and_javascript/Interacting-with-code.html
3. MDN, WebAssembly loading and MIME type: https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/JavaScript_interface/instantiateStreaming_static
4. MDN, ImageData and Canvas 2D: https://developer.mozilla.org/en-US/docs/Web/API/ImageData ; https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/putImageData
5. MDN, CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
6. Node.js, ES modules: https://nodejs.org/api/esm.html
