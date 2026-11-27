**English** | [한국어](web-renderer-guide.ko.md)

# SVF web renderer guide

The WebAssembly renderer exposes the C renderer to browsers and Node. Fetch a face, copy its bytes into WASM memory,
open a slot, then draw UTF-8 text into a pixel buffer. Convert that buffer into `ImageData` for a `<canvas>`.
See the [C guide](c-renderer-guide.md) for direct-memory and streaming C applications, the [SVF specification](../spec/SVF.md)
for file structure, and [jamo sets](jamo-sets.md) for composition.

## Build and arrange the files

Install and activate emsdk. `EMSDK` is the SDK root containing `upstream/emscripten/emcc` and `.emscripten`.
These commands use the default installation path; skip installation if it is already present.

```sh
sh c/cross/install-toolchains.sh "$HOME/opt" emsdk
. "$HOME/opt/emsdk/emsdk_env.sh"
EMSDK="$HOME/opt/emsdk" bash web/build.sh /tmp/svf-picker
python3 -m http.server 8000 --directory /tmp/svf-picker
```

Open `http://localhost:8000/` for the complete picker. [web/build.sh](../web/build.sh) outputs `svf.js`, `svf.wasm`,
the page and a face index. A separate application needs the JS/WASM pair and its chosen faces and licence files.
Keep JS and WASM together, or supply a WASM URL through the module factory’s `locateFile` option.

To build only the module, use the shared [emcc-flags.sh](../c/ports/web/emcc-flags.sh). Create the output directory first.

```sh
mkdir -p /tmp/svf-module
. c/ports/web/emcc-flags.sh
svf_web_compile "$PWD" /tmp/svf-module
```

The flags enable the ES module factory `SvfModule`, the `web,node` environments, `_malloc`/`_free`,
`HEAPU8`/`HEAP16`/`HEAP32`, and memory growth. Call the API after `await SvfModule()`.
Copying only `svf.js` leaves the WASM unavailable. Serve over HTTP(S), with `.wasm` as `application/wasm`;
open the page through the server rather than `file://`.

## Minimal complete HTML page

Save this as `example.html` alongside `svf.js`, `svf.wasm` and `NEODG16A.SVF`.
Open `/example.html` through the server to see amber text and its measurements. A slot acts as the face handle.
The second argument of `_svfw_open` is a WASM address, rather than a JavaScript array.

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

`svfw_measure` writes three `int16` values (advance width, ascent, descent): allocate 6 bytes and read `HEAP16`.
Width is not the ink bounds. Allow for the last cell’s overhang and leading combining marks, and split very long lines.
The x coordinate and baseline are in output pixels; each call draws one line. The application handles newlines and line placement.
GRAY8 keeps the maximum of existing coverage and new coverage, so clear the mask to 0 for each frame.
For transparent text, another option is to set RGB to the foreground and alpha to coverage, then composite in canvas.

## Colours and RGB565 output

The GRAY8 example produces coverage rather than colour, allowing JavaScript to choose foreground and background.
To draw RGB565 directly, allocate `2*w*h` bytes, fill the entire buffer with the background’s low/high bytes, then call
`_svfw_target2(3, ptr, 2*w*h, w, h, 2*w, fg565, bg565, 128, 0)`.
Colour targets blend against a known background and never read the destination pixel. Undrawn pixels retain the initialized background.
With `flags=0` the low byte comes first; `flags=1` means high byte first, requiring a byte-order change in the conversion below.
After drawing, pass this function’s result to `putImageData`.

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

RGB565 reduces colour precision to 5 red, 6 green and 5 blue bits. This wrapper does not expose the C core’s
XRGB8888/RGB888 targets; convert GRAY8 for 24/32-bit canvas colour. MONO_PAGE is kind 1, stride `w`, length
`w*ceil(h/8)`; MONO_ROW is kind 2, stride `ceil(w/8)`, length `stride*h`. Monochrome output uses the threshold.

## Render under Node

Save this as `example.mjs`. It uses the same module as the browser, copying file bytes in place of `fetch`.

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

The first command prints measurements and the number of ink pixels. The second is a complete invocation of
[render.mjs](../web/test/render.mjs), writing 4096 raw coverage bytes. It also accepts a JSON file path or an array
of specs processed in one module instance. Errors go to stderr: argument errors exit 2 and API errors exit 3.

## API and lifetimes

The contracts are in [svf_web.c](../c/ports/web/svf_web.c); see the [Web port reference](../c/ports/web/README.md)
for the complete list. The leading `_` is Emscripten’s JavaScript export name. Most functions return 0 for success
and otherwise an `svf_err`; distinguish the exceptions below.

| Call | Purpose and caveats |
|---|---|
| `_svfw_open(slot, ptr, len)` | Open in order from slot 0, up to 4 faces. Reopening closes later slots; failure ends the open chain there. |
| `_svfw_reset()` | Close all slots before freeing face memory. |
| `_svfw_info(slot, out)` | 32 bytes, `HEAP32`: bpp, cell_w, cell_h, ascent, flags, status, glyph count, is_jamo. Check status even after open succeeds. |
| `_svfw_has(slot, cp)` | Support as 1/0; an invalid slot also gives 0. |
| `_svfw_order(first)` | Change priority of existing slots; open/reset restore slot order. |
| `_svfw_scale(num, den)` | Integers 1..16 each; set before measuring. Integer enlargement uses pixel blocks; fractional scaling uses area averaging. |
| `_svfw_measure(text, len, out)` | UTF-8 byte length and 6-byte output. |
| `_svfw_draw(text, len, x, baseline)` | Draw one line to the last configured target, clipped to its bounds. |
| `_svfw_metrics(slot, cp, out)` | 16 bytes, `HEAP32`: advance, bearing_x, ink_w, dy. Returns 1 with metrics, 0 for defaults, -1 for missing glyph/bad arguments. |
| `_svfw_line_box(text, len, x, baseline, out)` | 16 bytes, `HEAP32`: x, baseline-ascent, width, baseline+descent. The last value is a bottom coordinate, not a height. |
| `_svfw_cell_bytes`, `_svfw_glyph`, `_svfw_pieces`, `_svfw_cmap_cp` | Extract cells and inspect pieces/code points; see the port reference for exact output types and return sentinels. |

For Hangul plus Latin, retain each face’s bytes and open slots 0 and 1. The first slot supporting a character draws it.
Use `_svfw_order` to change priority for shared characters. The picker switches order per Hangul/Latin run, using
the same order for measuring and drawing. This is not automatic font shaping.

## The complete picker and window.picker

The [font picker](../web/README.md) is a complete application showing lazy loading, face pairing, multiline canvas,
colours, scaling and selection export. In its developer console, wait for `window.picker.ready` before using these APIs.

| API | Purpose |
|---|---|
| `faces()`, `listed()`, `sizes()`, `families(px)` | Query the index and available sizes/families. `listed()` includes Latin-only faces. |
| `pick(key)`, `select({latin, hangul})`, `setSize(px)` | Asynchronous selection. `pick` requires a listed Hangul face; `setSize` changes the size list and prefetches it. |
| `setText(s)`, `setScale(n,d)`, `setTarget(opts)`, `render()` | Set text, scale and target, then render. |
| `chain()`, `view()`, `covers(text)`, `lacking(text)` | Inspect selection and character support. |
| `addChoice({game,id,lineh})`, `choices()`, `removeChoice(i)`, `exportJSON()` | Record, inspect, remove and export the current pairing. |
| `prefetch(key, keep)`, `faceMemory()` | Preload faces and inspect face memory. |

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

This API belongs to the picker page, not the WASM module. Keys come from `faces.json` and are distinct from file URLs.
See [picker.js](../web/picker.js) and [check.mjs](../web/test/check.mjs) for complete options and test hooks.

## Performance, memory and browsers

| Item | Budget and usage |
|---|---|
| Face | Entire file copied into the WASM heap; retain its pointer while its slot is open. The JS byte array can be discarded after copying. |
| Text | Use `TextEncoder`’s UTF-8 byte count, not JS string length. Reuse to reduce copies and allocations. |
| Target | GRAY8 `w*h`, RGB565 `2*w*h`; `ImageData` separately uses `4*w*h` JS bytes. |
| Scratch | Initially 64 KiB static; the glue allocates more if needed. Larger scales increase it. |
| Cache | The glue does not attach the core’s syllable cache. The picker retains loaded faces under a memory budget. |

WASM memory growth from `_malloc` or a draw’s internal allocation can invalidate old typed-array views.
Reacquire `M.HEAPU8` and other views after allocation/drawing. `slice` copies; `subarray` is a live view.
Reuse the module, faces, text and targets across frames, clearing and redrawing when needed. Each module has global
chain/target state: serialize asynchronous work or use independent module instances. Reset closes slots but does not
reset scale, target or scratch. After freeing a target, configure a new one before drawing. Dynamic scratch is retained
for the module’s lifetime.

Modern Chrome, Edge, Firefox and Safari need WebAssembly, ES modules, async/await, fetch, TextEncoder and Canvas 2D.
This build uses no threads or SharedArrayBuffer, so it does not require COOP/COEP isolation. Cross-origin faces and WASM
need CORS permission. There is no separate JavaScript fallback for old browsers. Minimum versions have not been exhaustively
tested; check the devices you intend to support. Use a Node version supporting ES modules and WebAssembly.
