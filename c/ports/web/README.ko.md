[English](README.md) | **한국어**

# 웹 glue (emscripten)

`svf_web.c`는 렌더러를 JavaScript로 내보낸다. 페이스(face)를 최대 4개의 체인에 열고(JavaScript가 모듈 메모리에 넣은 바이트에서 매핑),
JavaScript가 소유한 버퍼 위에 타깃(GRAY8, MONO_PAGE, MONO_ROW 또는 RGB565)을 설정하고, 스케일을 설정하고, UTF-8 줄을 측정하고 그린다.
함수와 인수는 파일 맨 위에 나열되어 있다. 달리 말하지 않는 한 각 함수는 `svf_err`를 반환한다(0은 SVF_OK). 이를
사용하는 페이지는 `web/`(카드 t_fe9f6c30)이며 `web/build.sh`로 빌드한다([web/README.md](../../../web/README.ko.md)).

내보내는 함수:

| function | does |
| --- | --- |
| `svfw_open(slot, data, len)` | data의 페이스를 슬롯 0..3에 순서대로 연다(마지막으로 열린 슬롯보다 뒤의 슬롯은 SVF_E_ARG). 그 뒤의 슬롯은 닫는다. 체인은 슬롯 0부터 이어지는 열린 슬롯의 연속이므로, 열기에 실패하면 체인이 거기서 끝난다 |
| `svfw_target(buf, w, h)` | w * h 바이트 위의 GRAY8 타깃(기존 호출자를 위해 유지. 페이지는 `svfw_target2`를 쓴다) |
| `svfw_target2(kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags)` | 모든 버퍼 타깃: kind 0 GRAY8, 1 MONO_PAGE, 2 MONO_ROW, 3 RGB565(4, 콜백은 SVF_E_ARG). flags 0 또는 1(`SVF_TF_565_BIGENDIAN`. `SVF_TF_RGB16_BIGENDIAN`의 옛 이름이며 같은 비트이다) |
| `svfw_scale(num, den)` | 줄 스케일, 각각 1..16 |
| `svfw_measure(text, len, out)` | int16 out[0..2] = 너비, ascent, descent |
| `svfw_draw(text, len, x, baseline)` | 타깃에 줄을 그린다 |
| `svfw_reset()` | 모든 슬롯을 닫아(체인 개수 0) 체인을 다른 순서로 다시 만들 수 있게 한다. SVF_OK |
| `svfw_info(slot, out)` | int32 out[0..7] = bpp, cell_w, cell_h, ascent, flags, status, glyph 수, is_jamo. 열려 있지 않은 슬롯은 SVF_E_ARG |
| `svfw_has(slot, cp)` | 슬롯 페이스의 `svf_has`: 1 또는 0(열려 있지 않은 슬롯은 0) |
| `svfw_order(first)` | 체인이 슬롯 first를 먼저 시도하고 나머지는 슬롯 순서로 그 뒤에 시도한다(`svfw_order(0)`: 슬롯 순서). 다시 열지 않는다. 열려 있지 않은 슬롯은 SVF_E_ARG. `svfw_open`/`svfw_reset`은 슬롯 순서를 복원한다 |
| `svfw_metrics(slot, cp, out)` | `svf_metrics_of`: 1(메트릭 표 있음), 0(없음), -1(glyph 없음, 슬롯이 열려 있지 않음 또는 out이 NULL). int32 out[0..3] = advance, bearing_x, ink_w, dy |
| `svfw_cell_bytes(slot)` | 슬롯 페이스의 `svf_cell_bytes`. 열려 있지 않은 슬롯은 0 |
| `svfw_glyph(slot, cp, cell, len)` | `svf_glyph`(JSET 페이스의 음절은 조합된다). 그 `svf_err`. 열려 있지 않은 슬롯이나 cell이 NULL이면 SVF_E_ARG |
| `svfw_pieces(slot, cp, out)` | `svf_jamo_pieces`: 개수 0..3, uint16 out[0..2] = 조각 번호(0xFFFF는 빈 조각). 열려 있지 않은 슬롯이나 out이 NULL이면 0 |
| `svfw_cmap_cp(slot, i)` | 코드 포인트 표의 항목 i의 코드 포인트(파일 순서). 표를 넘거나, 0보다 작거나, 열려 있지 않은 슬롯이면 -1 |
| `svfw_line_box(text, len, x, baseline, out)` | 체인에 대한 `svf_measure_utf8`: int32 out = x, baseline - ascent, 너비, baseline + descent. 그 `svf_err` |

슬롯이 사용하는 동안 페이스 바이트는 모듈 메모리에 남아 있어야 한다. 해제하기 전에 `svfw_reset`을 호출한다.

스크래치: `svfw_draw`는 체인의 `svf_chain_scratch_bytes`가 필요하다. 첫 버퍼는 정적 64 KB이다(18 px 페이스 최대
14배). 더 필요한 그리기는 그리기 전에 필요한 만큼 정확히 malloc하고(16/1의 GBATB47은 637 KB가 필요하다) 이전 버퍼가
malloc된 것이었다면 해제한다. malloc이 실패하면 SVF_E_NOMEM을 반환하고 아무것도 그리지 않으며 이전
버퍼를 유지한다. 할당하는 것은 이 포트뿐이다. `c/src`는 절대 할당하지 않는다(`make -C c check`, no-malloc).

빌드(emsdk **6.0.13**, emcc 6.0.13. `sh c/cross/install-toolchains.sh "$HOME/opt" emsdk`가 `~/opt/emsdk` 아래에 설치한다. 이 줄로 측정: `svf.wasm` 39,808바이트, `svf.js` 6,937. 이것이 `web/build.sh`와 `maker/build-wasm.sh`가 실행하는 줄이며 `emcc-flags.sh`에 있다):

    EM_CONFIG=~/opt/emsdk/.emscripten ~/opt/emsdk/upstream/emscripten/emcc -std=c99 -Wall -Wextra -Werror -O2 \
        -Ic/include c/ports/web/svf_web.c c/src/*.c -o svf.js -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
        -sENVIRONMENT=web,node -sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16,HEAP32 \
        -sALLOW_MEMORY_GROWTH

`-sENVIRONMENT=web,node`는 `web/test/render.mjs`가 node에서 모듈을 불러오게 한다. `HEAP32`는 `svfw_info`를 위한 것이다.
`web/build.sh [OUT]`은 faces.json도 쓰고 페이스와 라이선스를 복사하며(`web/copyfaces.py`) svf.wasm과
svf.js의 크기를 출력한다. `c/cross/build-all.sh --ports`(모든 포트)와 `--port web`(이 포트만, emcc만)은 `-sENVIRONMENT`와 `HEAP32`를 제외하면
같은 소스와 플래그로 이를 빌드한다.

사용:

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

`c/cross/build-all.sh --ports`가 이를 빌드한다(전체 모듈, 스텁 없음). node 24에서 PAPLG16 +
PAPLG18로 실행했다. "Web: 다람쥐 헌 쳇바퀴에 타고파!"의 `svfw_measure`는 너비 272, ascent 17, descent 4를 주었고 그려진 줄은
올바르게 읽혔다.
