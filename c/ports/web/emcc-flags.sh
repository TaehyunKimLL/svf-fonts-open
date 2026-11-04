# emcc-flags.sh - sourced by web/build.sh and maker/build-wasm.sh: the one compile line of the WASM module.
#   svf_web_compile ROOT OUT_DIR   builds ROOT/c/ports/web/svf_web.c and ROOT/c/src/*.c into OUT_DIR/svf.js and
#                                  OUT_DIR/svf.wasm with emcc from EMSDK (default ~/opt/emsdk); OUT_DIR must exist.
#                                  Returns 1 with a message when emcc is missing. Writes no other file.
EMSDK=${EMSDK:-$HOME/opt/emsdk}

svf_web_compile() {
	local root=$1 out=$2
	local emcc=$EMSDK/upstream/emscripten/emcc
	local c=$root/c

	[ -x "$emcc" ] || { echo "build.sh: no emcc at $emcc (c/cross/install-toolchains.sh, or set EMSDK)" >&2; return 1; }
	EM_CONFIG="$EMSDK/.emscripten" "$emcc" -std=c99 -Wall -Wextra -Werror -O2 -I"$c/include" \
		"$c/ports/web/svf_web.c" "$c"/src/*.c -o "$out/svf.js" -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
		-sENVIRONMENT=web,node -sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16,HEAP32 \
		-sALLOW_MEMORY_GROWTH
}
