**English** | [한국어](README.ko.md)

# Web glue (emscripten)

`svf_web.c` exports the renderer to JavaScript: open faces (mapped from bytes JavaScript puts in the module's memory)
into a chain of up to 4, set a target (GRAY8, MONO_PAGE, MONO_ROW or RGB565) over a buffer JavaScript owns, set a scale, measure and draw UTF-8 lines.
The functions and their arguments are listed at the top of the file; each returns an `svf_err` (0 is SVF_OK) unless
said. The page that uses it is `web/` (card t_fe9f6c30), built by `web/build.sh` ([web/README.md](../../../web/README.md)).

Exports:

| function | does |
| --- | --- |
| `svfw_open(slot, data, len)` | opens the face at data in slot 0..3, in order (a slot past the last open one is SVF_E_ARG) and closes the slots after it; the chain is the run of open slots from slot 0, so a failed open ends it there |
| `svfw_target(buf, w, h)` | GRAY8 target over w * h bytes (kept for existing callers; the page uses `svfw_target2`) |
| `svfw_target2(kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags)` | any buffer target: kind 0 GRAY8, 1 MONO_PAGE, 2 MONO_ROW, 3 RGB565 (4, the callback, is SVF_E_ARG); flags 0 or 1 (`SVF_TF_565_BIGENDIAN`, the older name of `SVF_TF_RGB16_BIGENDIAN`: the same bit) |
| `svfw_scale(num, den)` | the line scale, 1..16 each |
| `svfw_measure(text, len, out)` | int16 out[0..2] = width, ascent, descent |
| `svfw_draw(text, len, x, baseline)` | draws the line on the target |
| `svfw_reset()` | closes every slot (chain count 0), so a chain can be rebuilt in another order; SVF_OK |
| `svfw_info(slot, out)` | int32 out[0..7] = bpp, cell_w, cell_h, ascent, flags, status, glyph count, is_jamo; SVF_E_ARG for a slot not open |
| `svfw_has(slot, cp)` | `svf_has` of the slot's face: 1 or 0 (0 for a slot not open) |
| `svfw_order(first)` | the chain tries slot first first, the others after it in slot order (`svfw_order(0)`: slot order); no reopen; SVF_E_ARG for a slot not open; `svfw_open`/`svfw_reset` restore slot order |
| `svfw_metrics(slot, cp, out)` | `svf_metrics_of`: 1 (metrics table), 0 (none), -1 (no glyph, slot not open or out NULL); int32 out[0..3] = advance, bearing_x, ink_w, dy |
| `svfw_cell_bytes(slot)` | `svf_cell_bytes` of the slot's face; 0 for a slot not open |
| `svfw_glyph(slot, cp, cell, len)` | `svf_glyph` (a syllable of a JSET face is composed); its `svf_err`, SVF_E_ARG for a slot not open or cell NULL |
| `svfw_pieces(slot, cp, out)` | `svf_jamo_pieces`: the count 0..3, uint16 out[0..2] = piece numbers (0xFFFF blank); 0 for a slot not open or out NULL |
| `svfw_cmap_cp(slot, i)` | the code point of entry i of the code point table (file order); -1 past the table, below 0 or for a slot not open |
| `svfw_line_box(text, len, x, baseline, out)` | `svf_measure_utf8` on the chain: int32 out = x, baseline - ascent, width, baseline + descent; its `svf_err` |

Face bytes must stay in the module's memory while a slot uses them: call `svfw_reset` before freeing them.

Scratch: `svfw_draw` needs `svf_chain_scratch_bytes` of the chain. The first buffer is a static 64 KB (an 18 px face up
to 14x); a draw that needs more mallocs a buffer of exactly the need before drawing (GBATB47 at 16/1 needs 637 KB) and
frees the previous one if it was malloced. A failed malloc returns SVF_E_NOMEM, draws nothing and keeps the previous
buffer. Only this port allocates: `c/src` never does (`make -C c check`, no-malloc).

Build (emsdk **6.0.13**, emcc 6.0.13, as `sh c/cross/install-toolchains.sh "$HOME/opt" emsdk` installs it under `~/opt/emsdk`; measured
`svf.wasm` 39,808 bytes and `svf.js` 6,937 with this line; this is the line `web/build.sh` and `maker/build-wasm.sh` run, kept in `emcc-flags.sh`):

    EM_CONFIG=~/opt/emsdk/.emscripten ~/opt/emsdk/upstream/emscripten/emcc -std=c99 -Wall -Wextra -Werror -O2 \
        -Ic/include c/ports/web/svf_web.c c/src/*.c -o svf.js -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
        -sENVIRONMENT=web,node -sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16,HEAP32 \
        -sALLOW_MEMORY_GROWTH

`-sENVIRONMENT=web,node` lets `web/test/render.mjs` load the module under node; `HEAP32` is for `svfw_info`.
`web/build.sh [OUT]` also writes faces.json and copies the faces and licences (`web/copyfaces.py`) and prints the svf.wasm
and svf.js sizes. `c/cross/build-all.sh --ports` (every port) and `--port web` (this one alone, emcc only) build it with
the same sources and flags apart from `-sENVIRONMENT` and `HEAP32`.

Use:

    import SvfModule from './svf.js';
    const M = await SvfModule();
    const put = bytes => { const p = M._malloc(bytes.length); M.HEAPU8.set(bytes, p); return p; };
    const face = new Uint8Array(await (await fetch('PAPLG18.SVF')).arrayBuffer());
    M._svfw_open(0, put(face), face.length);              // slot 0 is tried first; open more in 1, 2, 3
    const W = 320, H = 24, buf = M._malloc(W * H);
    M.HEAPU8.fill(0, buf, buf + W * H);
    M._svfw_target(buf, W, H);
    const text = new TextEncoder().encode('다람쥐 헌 쳇바퀴에 타고파');
    M._svfw_draw(put(text), text.length, 0, 19);           // pen x 0, baseline row 19
    const coverage = M.HEAPU8.subarray(buf, buf + W * H);  // one byte a pixel; read HEAPU8 again after a _malloc

`c/cross/build-all.sh --ports` builds it (whole module, nothing stubbed). It was run under node 24 with PAPLG16 +
PAPLG18: `svfw_measure` of "Web: 다람쥐 헌 쳇바퀴에 타고파!" gave width 272, ascent 17, descent 4, and the drawn line
read correctly.
