[English](README.md) | **한국어**

# SVF C 렌더러 (`c/`)

SVFN v3 비트맵 페이스(face)([spec/SVF.ko.md](../spec/SVF.ko.md))를 읽어 UTF-8 한 줄을 그리는 이식 가능한 C99 라이브러리이다.
자모 세트 페이스에서 조합되는 한글 음절도 그린다. 설계: [spec/renderer-design.ko.md](../spec/renderer-design.ko.md).
기준은 Python 도구이다. glyph와 음절은 `tools/jamoset.py`(`parse_svfn`, `pieces_of`, `compose`), 줄·타깃·스케일링은
`tools/svfline.py`가 기준이다. 이 라이브러리는 이들과 바이트 단위로 같은 픽셀을 그린다.

- **할당 없음.** 호출자가 모든 바이트를 소유한다: 페이스 구조체, 스트리밍 페이스의 테이블 버퍼와 캐시,
  스크래치 셀, 타깃 버퍼. 오브젝트가 `malloc`, `calloc`, `realloc`, `free`를 참조하면 `make -C c check`가 실패한다.
- **작은 의존성.** `<stdint.h>`, `<stddef.h>`, `<string.h>`만 쓴다.
- **모든 타깃에 하나의 소스.** 아래의 스위치로 컴파일 시점에 줄여 낸다.

사용처(2026-11-01):

| 사용처 | 위치 | 빌드 결과 |
|---|---|---|
| MCU 예제 | `c/ports/{pico,esp32,arduino,ch582}` | 플래시에 매핑된 페이스, 각각 타깃 종류 하나 |
| DOS 프로그램 | `c/ports/dos` | `SVFDEMO.EXE`(모드 13h)와 `SVFVESA.EXE`(VBE 2.0), 스트리밍 페이스 |
| WASM 피커 | `c/ports/web` -> `web/` | `svf.wasm`, 폰트 피커 페이지([web/README.ko.md](../web/README.ko.md)) |
| SDL2 / SDL3 | `c/ports/sdl` | `svfsdl2`, `svfsdl3`: 타깃 종류가 다루는 모든 픽셀 포맷의 SDL 서피스 |
| ScummVM | `graphics/hires_text` (이 저장소의 서브모듈 사용처) | **아직 아님**: ScummVM은 아직 자체 SVF 리더(`jamo_set.h`)를 쓰며, 이것은 버전 3 JSET 블록을 거부한다. 카드 t_5a7bcd78이 이를 이 라이브러리로 교체한다 |

## 파일

| 경로 | 내용 |
|---|---|
| `include/svf.h` | 공개 API 전체와 모든 컴파일 시점 스위치, 계약은 주석에 있음 |
| `src/svf_face.c` | 헤더, 레이아웃과 테이블 검증, `svf_open_mapped`, 접근자, 코드 포인트 조회 |
| `src/svf_jamo.c` | JSET v1/v2 리더, JMAP(dense, SPARSE, LIST), `svf_jamo_pieces`, `svf_compose` |
| `src/svf_stream.c` | 스트리밍 페이스: `svf_open_stream`, 블록 캐시(`SVF_NO_STREAM`에서는 비어 있음) |
| `src/svf_draw.c` | 타깃, 체인, `svf_measure_utf8`, `svf_draw_utf8`, 조합된 음절 캐시 |
| `src/svf_scale.c` | 스케일된 셀(`SVF_NO_SCALE`에서는 비어 있음) |
| `tests/` | `svfdump`(Python 테스트의 C 쪽), 단위 프로그램, 퍼즈 하니스와 코퍼스 스크립트 |
| `cross/` | 크로스 빌드, 크기 표, 크기/심볼 게이트(`SIZES.md`) |
| `bench/` | 에뮬레이션 속도 벤치와 동일성 검사(`MEASUREMENTS.md`, `JSET2-IDENTITY.md`) |
| `ports/` | 위의 예제들, 호스트 검사(`ports/check`), 내장 페이스의 고지문(`ports/FACES.md`) |

호스트 라이브러리와 `svfdump` 빌드: `make -C c` (출력은 `c/build`, 옮기려면 `O=DIR`).

## 페이스: 통째로 보유하거나 스트리밍

페이스는 두 방식 중 하나로 열며, 그 뒤로는 모든 호출이 같다.

- **Mapped**(`svf_open_mapped`): 파일 전체가 주소 지정 가능한 메모리(RAM, 플래시, PROGMEM)에 있다. 모든 테이블과 모든
  glyph 레코드를 열 때 검증하며, 페이스를 쓰는 동안 바이트가 바뀌어서는 안 된다. AVR에서는 라이브러리를
  `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드하여 모든 페이스 읽기가 `pgm_read_byte`를 거친다.
- **Streamed**(`svf_open_stream`): 파일은 디스크, SD 카드 또는 네트워크에 남는다. 헤더와 테이블은 호출자 버퍼에
  한 번 읽는다(`svf_stream_tables_size`가 필요한 크기를 알려 준다). glyph 행은 `svf_read_fn` 콜백으로 필요할 때
  읽으며, 선택적으로 블록 캐시를 거친다(`block_size`는 64..4096 범위의 2의 거듭제곱, 슬롯은 `block_size + 8` 바이트,
  최소 2개). glyph 레코드는 읽을 때 검사한다. `-DSVF_NO_STREAM`에서는 컴파일되지 않는다(스트림 함수 세 개는
  선언조차 되지 않는다).

```c
/* mapped: a face linked into flash */
svf_face face;
if (svf_open_mapped(&face, face_bytes, face_len) != SVF_OK) { /* refused: see svf_err */ }

/* streamed: a file read through a callback, 8 cache slots of 1 KB */
static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
{
	FILE *fp = ctx;
	return fseek(fp, (long)off, SEEK_SET) == 0 ? (long)fread(dst, 1, len, fp) : -1;
}
static uint8_t tables[64 * 1024], cache[8 * (1024 + 8)];
svf_err err;
size_t need = svf_stream_tables_size(rd, fp, file_len, &err);  /* 0 and err set when the header is refused */
if (need && need <= sizeof tables)
	err = svf_open_stream(&face, rd, fp, file_len, tables, sizeof tables, cache, sizeof cache, 1024);
```

## 공개 API

모든 함수는 NULL 포인터에 안전하다. `svf_err`를 반환하는 함수는 `SVF_E_ARG`를 반환하고, 나머지는 주석에 명시된
센티널 값을 반환한다(NULL 페이스는 0으로 채운 페이스로 읽힌다). `c/tests/test_args.c`가 각 함수를 각 경우로 호출한다.

### 오류(`svf_err`)

| 값 | 의미 |
|---|---|
| `SVF_OK` | 성공 |
| `SVF_E_MAGIC` | SVFN 파일이 아님 |
| `SVF_E_VERSION` | 버전 3이 아님(v2 파일은 `tools/svf2to3.py`로 변환) |
| `SVF_E_BPP` | 픽셀당 비트 수가 1, 2, 8이 아님 |
| `SVF_E_RANGE` | 파일 밖의 크기나 오프셋, 빈 glyph 박스, 없는 코드 포인트나 glyph |
| `SVF_E_NOMEM` | 호출자 버퍼가 너무 작음 |
| `SVF_E_IO` | 읽기 콜백 실패(스트리밍 페이스) |
| `SVF_E_ARG` | NULL 포인터 또는 잘못된 인자(이 빌드가 컴파일하지 않은 타깃 종류나 스케일 포함) |
| `SVF_E_LAYOUT` | 레이아웃 바이트, 플래그, 정렬 또는 오프셋 테이블이 잘못됨, 또는 빌드의 `SVF_LAYOUTS` 밖의 레이아웃 |

### 페이스 상태 비트(`svf_status`)

열리는 페이스도 상태 비트를 가질 수 있다. 이는 무엇이 버려졌는지를 알려 주며, 열기 실패를 뜻하지 않는다.

| 비트 | 이름 | 의미 |
|---|---|---|
| 0x0001 | `SVF_FACE_CMAP_LINEAR` | 코드 포인트 테이블이 엄격히 증가하지 않음: 선형 탐색, 마지막 항목이 우선 |
| 0x0002 | `SVF_FACE_DY_IGNORED` | 헤더의 dy 범위가 잘못됨: 모든 glyph를 dy 0에 둠 |
| 0x0004 | `SVF_FACE_METRICS_DROPPED` | 메트릭 테이블이 파일 밖에 있음: 버림, 셀은 자기 폭만큼 전진 |
| 0x0008 | `SVF_FACE_JSET_BAD` | JSET 부분이 검증에 실패하거나 이 빌드가 모르는 버전임: 일반 페이스 |
| 0x0010 | `SVF_FACE_JSET_UNREAD` | 형식이 올바른 v1 또는 v2 블록이지만 리더가 컴파일되지 않음: 일반 페이스 |
| 0x0020 | `SVF_FACE_JMAP_BAD` | 버전 3 블록(JMAP)이 JMAP 규칙을 어김, 폴백 포함 |
| 0x0040 | `SVF_FACE_JMAP_UNREAD` | 빌드가 인식하지만 읽지 않는 버전 3 블록: 있으면 그 폴백 JSET을 대신 읽음 |

### 함수

| 함수 | 계약(한 줄; 전문은 `svf.h`의 주석) |
|---|---|
| `svf_open_mapped(f, data, len)` | 통째로 보유한 페이스를 연다. 헤더, 레이아웃, 테이블, 모든 glyph 레코드와 JSET 부분을 검증한다 |
| `svf_open_stream(f, rd, ctx, file_len, tables, tables_len, cache, cache_len, block_size)` | `rd`로 읽는 페이스를 연다. 오류 시 페이스는 전부 0이다(`SVF_NO_STREAM`에서는 없음) |
| `svf_stream_tables_size(rd, ctx, file_len, err)` | 이 빌드의 리더로 그 파일이 필요로 하는 `tables`의 바이트 수. 헤더가 거부되면 0이며 `err`가 설정된다 |
| `svf_stream_reads(f)` | 열린 뒤 읽기 콜백이 호출된 횟수(mapped 페이스는 0) |
| `svf_layouts(&set)` | 이 빌드가 읽는 레이아웃 코드. 유효한 모든 레이아웃을 읽으면 0과 NULL |
| `svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`, `svf_flags`, `svf_status`, `svf_glyph_count` | 헤더 값. NULL 페이스는 0 |
| `svf_cmap_cp(f, i)` | 코드 포인트 테이블 항목 `i`의 코드 포인트, 또는 0xFFFFFFFF |
| `svf_has(f, cp)` | 페이스가 `cp`를 그리면(저장된 glyph, 또는 조합되는 음절/호환 자모) 0이 아님 |
| `svf_metrics_of(f, cp, &m)` | 메트릭 테이블에서 얻으면 1, 테이블이 없으면 0(셀 메트릭), 페이스에 glyph가 없으면 -1 |
| `svf_cell_bytes(f)` | 저장된 셀 하나의 바이트 수: `((cell_w * bpp + 7) / 8) * cell_h` |
| `svf_glyph(f, cp, cell, cell_len)` | `cp`의 저장된 또는 조합된 행을 `cell`에 복사한다(MSB 우선, 행은 바이트로 패딩) |
| `svf_is_jamo(f)` | 페이스가 음절을 조합하면(쓸 수 있는 JSET 또는 JMAP) 0이 아님 |
| `svf_jamo_pieces(f, cp, out)` | 그리는 순서대로의 `cp`의 조각 번호. 음절이면 2 또는 3, 호환 자모면 1, 그 외 0을 반환 |
| `svf_compose(f, cp, cell, cell_len)` | 조각들의 최대 커버리지로 `cp`를 조합한다 |
| `svf_is_mark_default(cp)` | 기본 마크 판별: U+0300..U+036F |
| `svf_chain_cache(c, buf, len)` | 체인에 조합된 음절 캐시를 준다(라운드 로빈, 있든 없든 같은 픽셀) |
| `svf_target_init(t, kind, buf, buf_len, w, h, stride)` | 타깃을 채운다(타깃 전체 클립, 종류별 기본값). 컴파일되지 않은 종류는 `SVF_E_ARG` |
| `svf_chain_scratch_bytes(c)` | 이 체인을 그 스케일로 `svf_draw_utf8`이 필요로 하는 스크래치 |
| `svf_measure_utf8(c, s, len, &e)` | glyph를 읽지 않고 구한 줄의 폭, ascent, descent |
| `svf_draw_utf8(c, s, len, x, y_baseline, t, scratch, scratch_len)` | UTF-8 한 줄을 그린다. 스트리밍 읽기가 실패하면 그 glyph를 건너뛰고 끝에서 `SVF_E_IO`를 반환한다 |

조합에는 공간이 필요하다: 캐시가 **없는** 스트리밍 페이스는 `2 * svf_cell_bytes`에 조합한다(뒤쪽 절반은 읽고 있는
조각을 담는다). `svf_chain_scratch_bytes`는 이것과 스케일링을 이미 반영한다.

### 체인, 타깃, 스케일

`svf_chain`은 페이스의 목록이다. 각 코드 포인트는 그것을 가진(`svf_has`) 첫 페이스가 그린다. 어느 페이스에도 없는
코드 포인트는 `missing_advance` 픽셀만큼 전진한다. 마크(`is_mark`, 기본 U+0300..U+036F)는 0만큼 전진하며 앞 glyph
위에 그려진다. `scale_num / scale_den`(각각 1..16, 0/0은 1/1을 뜻함)은 줄을 스케일한다: 정수배는 픽셀을
반복하고, 그 외 비율은 면적 평균을 낸다(기준은 `tools/svfline.py`의 "Scaling").

| 종류 | `SVF_TARGETS` 비트 | 픽셀 |
|---|---|---|
| `SVF_T_GRAY8` | 0x001 | 1바이트, max(기존 값, 커버리지) |
| `SVF_T_MONO_PAGE` | 0x002 | SSD1306 페이지: `buf[(y >> 3) * stride + x]`의 비트 `y & 7`, `mono_threshold`에서 설정 |
| `SVF_T_MONO_ROW` | 0x004 | 1 bpp 행, MSB 우선, 같은 임계값 규칙 |
| `SVF_T_RGB565` | 0x008 | `bg565`/`fg565`를 채널별로 블렌드(`SVF_TF_RGB16_BIGENDIAN`이면 상위 바이트 우선) |
| `SVF_T_COVERAGE_CB` | 0x010 | `plot(ctx, x, y, coverage)` 콜백, 버퍼 없음 |
| `SVF_T_INDEXED8` | 0x020 | 팔레트 인덱스 `index_base + level`, max 규칙(VGA/VBE 8 bpp, SDL CLUT8) |
| `SVF_T_RGB555` | 0x040 | 5/5/5 블렌드, 비트 15는 `fg565`에서 |
| `SVF_T_XRGB8888` | 0x080 | B, G, R, X 바이트(VBE 32 bpp) |
| `SVF_T_RGB888` | 0x100 | B, G, R 바이트 |
| `SVF_T_GRAY` | 0x200 | 픽셀당 `gray_bits` 1, 2, 4 또는 8, MSB 또는 LSB 우선(`SVF_TF_GRAY_LSB_FIRST`) |

모든 종류는 클립 사각형 안의 픽셀만 쓰며 패딩 바이트는 절대 쓰지 않는다. 정확한 공식은 `svf.h`의 `svf_target`
위에 있다.

```c
svf_face *faces[2] = {&ascii_face, &hangul_face};
svf_chain chain = {0};                 /* zeroed: scale 1/1, default marks, no cache */
chain.faces = faces;
chain.count = 2;

static uint8_t page[128 * 64 / 8], scratch[512];
svf_target t;
if (svf_target_init(&t, SVF_T_MONO_PAGE, page, sizeof page, 128, 64, 128) != SVF_OK) { /* kind not compiled */ }
if (svf_chain_scratch_bytes(&chain) > sizeof scratch) { /* scratch too small */ }

const char *s = "안녕 SVF";
svf_extent e;
svf_measure_utf8(&chain, s, strlen(s), &e);           /* e.width, e.ascent, e.descent */
svf_draw_utf8(&chain, s, strlen(s), 0, (int16_t)svf_ascent(&hangul_face), &t, scratch, sizeof scratch);
```

`c/ports/arduino/arduino.ino`는 이와 같은 방식의 완전한 작은 프로그램이다(PROGMEM의 mapped 페이스, MONO_PAGE).

## 컴파일 시점 스위치

모든 스위치는 라이브러리의 **모든** 소스와 `svf.h`를 포함하는 모든 파일에 주는 `-D`이다(`SVF_JMAP`은 `svf_face`의
크기를 바꾼다). 빼 둔 기능은 오브젝트 코드에 전혀 들어가지 않는다. 아래 기본값은 각 툴체인에서 `svf.h`를
`-dM -E`로 읽어 2026-11-01에 얻은 것이다(호스트 gcc 13.3 x86-64, DJGPP i586 gcc 12.2, emcc 6.0.13,
avr-gcc 16.1.0 `-mmcu=atmega328p`, arm-none-eabi-gcc 15.2.1 Cortex-M0+, riscv32-esp-elf-gcc 16.1.0,
xtensa-esp32s3/esp32-elf-gcc 16.1.0):

| 스위치 | 호스트, DOS, WASM, SDL | AVR | Cortex-M, RISC-V, Xtensa | `-DSVF_SMALL`(호스트) | 하는 일 |
|---|---|---|---|---|---|
| `SVF_TARGETS` | 0x3FF | 0x3FF | 0x3FF | 0x3FF | 컴파일되는 종류의 OR. 나머지는 `SVF_E_ARG`로 거부 |
| `SVF_NO_STREAM` | 미설정 | 미설정 | 미설정 | 미설정 | 정의 시: 스트리밍 페이스 없음(`svf_stream.c`가 비어 있음) |
| `SVF_NO_SCALE` | 미설정 | 미설정 | 미설정 | 미설정 | 정의 시: 스케일링 없음(`svf_scale.c`가 비어 있음. n/n 외의 비율은 `SVF_E_ARG`) |
| `SVF_LAYOUTS` | 미설정(전부) | 미설정 | 미설정 | 미설정 | 읽는 `SVF_LAYOUT` 코드의 쉼표 목록(예: `SVF_LAYOUT_MCU_STRICT`). 나머지는 `SVF_E_LAYOUT` |
| `SVF_RD8(p)` | 일반 로드 | 일반 로드 | 일반 로드 | 일반 로드 | mapped 페이스의 바이트 읽기. AVR 포트는 `pgm_read_byte(p)`로 설정 |
| `SVF_WORD_STORE` | 1 (x86, wasm) | 0 | 0 | 1 | 임의 정렬에서의 4바이트 저장. 같은 픽셀 |
| `SVF_SMALL` | 미설정 | 미설정 | 미설정 | 설정 | 포괄 스위치: 아래 네 속도 스위치의 기본값이 0이 된다 |
| `SVF_MERGE_WORDS` | 1 | 0 | 1 | 0 | 자모 조각 행의 워드 단위 병합 |
| `SVF_GRAY8_LUT1` | 1 | 0 | 1 (Xtensa 0) | 0 | GRAY8 1 bpp blit용 64 B 니블 테이블 |
| `SVF_SCALE_FAST` | 1 | 1 | 1 | 0 | 2차원 루프 대신 분리형 면적 평균(스택 프레임 AVR 610 B, M0+ 680 B) |
| `SVF_JSET_V1` | 1 | 1 | 1 | 1 | JSET 버전 1 리더 |
| `SVF_JSET_V2` | 1 | 0 | 1 | 1 | JSET 버전 2(컴팩트) 리더 |
| `SVF_JSET_POP4` | 1 | 0 | 1 | 0 | v2 리더의 니블 popcount 테이블 |
| `SVF_JSET_TRUSTED` | 0 | 0 | 0 | 0 | 1이면 JSET 내용 검증을 건너뜀: 플래시에 내장된 페이스에만 쓰고 파일에는 쓰지 말 것 |
| `SVF_JSET_BIG` | 1 | 0 | 0 | 0 | v1/v2 한계 19 x 28 클래스, 128 / 128 / 64 세트(좁은 한계: 12 x 12, 32 / 24 / 16) |
| `SVF_JMAP` | 1 | 0 | 0 | 0 | 버전 3 블록(JMAP) 리더. `svf_face`가 커진다 |
| `SVF_JMAP_LIST` | 1 | 0 | 0 | 0 | LIST 형식(플래그 0x08). `SVF_JMAP`을 따르며, 그것 없이 1이면 `#error` |
| `SVF_JMAP_RECOG` | 1 (컴파일에서 빠짐: `SVF_JMAP`이 1) | 0 | 0 | 0 | `SVF_JMAP` 없이: v3 블록을 인식하고 그 폴백 JSET을 읽음 |

기본값이 정해지는 방식(`svf.h`): `SVF_JMAP`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG`은 컴파일러가 AVR이 아니고,
`SVF_SMALL`이 설정되지 않았으며, `__unix__`, `_WIN32`, `__APPLE__`, `__DJGPP__`, `__EMSCRIPTEN__` 중 하나가
정의된 경우에만 1이다. 이들이 없는 베어메탈 x86 빌드는 MCU 기본값을 받는다. `SVF_JMAP_RECOG`은 `SVF_JMAP`이 0인
곳에서만 작동하므로 호스트에서는 명시적인 `-DSVF_JMAP=0`이 필요하다. 명시적인 `-DSVF_X=0/1`이 항상 우선한다.
`SVF_JSET_V1`, `SVF_JSET_V2`, `SVF_JMAP`이 모두 0일 수는 없다.

포트가 실제로 빌드하는 설정:

| 빌드 | 기본값에 더하는 플래그 |
|---|---|
| Arduino Uno(`c/ports/arduino`, `check-features.sh`의 `minimal` 설정) | `-DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0`, PROGMEM 읽기 |
| CH582 | Uno 스위치(버전 1 리더만) |
| Pico, ESP32-C3/S3 | `-DSVF_NO_SCALE`과 프로파일의 `SVF_TARGETS` 비트 하나(`c/ports/profiles.txt`) |
| DOS, WASM, SDL | 기본값(모든 종류, 스트리밍, 스케일링, JMAP, LIST, BIG) |

## 자모 세트: 각 빌드가 읽는 것

자모 세트 페이스(헤더 플래그 비트 1)는 JSET 블록을 가지며, 음절 U+AC00..U+D7A3은 조각 둘 또는 셋의 최대
커버리지이다(조각 번호를 U+F0000에 더한 위치의 glyph). 블록의 형식은 모두 [spec/SVF.ko.md](../spec/SVF.ko.md)에 명세되어 있다.

- **JSET 버전 1**("Jamo-set fonts"): 클래스 테이블과 세트 테이블. 표준 형식이며 기본으로 기록된다.
- **JSET 버전 2**("JSET block version 2 (compact; exception-only)"): 비트 팩 테이블. 요청할 때만 기록된다
  (`--jset-version 2`, "When to use version 2" 참조).
- 버전 1과 2의 **BIG 한계**: 초성 19 x 종성 28 클래스까지, 초성/중성/종성 세트 128 / 128 / 64까지.
  좁은 한계는 12 x 12와 32 / 24 / 16이다.
- **버전 3, JMAP**("Version 3: mapping table (JMAP)"): 음절에서 조각으로의 직접 매핑. dense(전체
  11,172개) 또는 SPARSE(비트맵과 NS개 항목)이며, 나열하지 않은 음절을 위한 선택적 FALLBACK v1/v2 블록이 있다.
- **JMAP LIST**(플래그 0x08, 같은 절): 최대 255개 예외의 정렬된 목록(음절 -> 폴백과 공유하는 풀 위의 조각 번호 셋).
  없으면 폴백으로 가고, 폴백도 없으면 그 음절은 조합되지 않는다.

| 페이스가 가진 것 | 기본 호스트 / DOS / WASM / SDL | AVR 기본 | 그 외 MCU 기본 |
|---|---|---|---|
| v1, 좁은 한계 | 조합됨 | 조합됨 | 조합됨 |
| v2, 좁은 한계 | 조합됨 | 일반, `JSET_UNREAD` | 조합됨 |
| 좁은 한계를 넘는 v1 또는 v2 | 조합됨(BIG) | 일반, `JSET_BAD` | 일반, `JSET_BAD` |
| v3 JMAP, dense 또는 SPARSE | 조합됨 | 일반, `JSET_BAD`(알 수 없는 버전) | 일반, `JSET_BAD` |
| v3 JMAP LIST | 조합됨 | 일반, `JSET_BAD` | 일반, `JSET_BAD` |

그 외의 조합: MCU에서 `-DSVF_JMAP_RECOG=1`은 v3 블록을 `JMAP_UNREAD`로 만들고, 그 리더가 컴파일되어 있으면 그
폴백 JSET을 읽는다(아니면 `JSET_UNREAD` / `JSET_BAD`가 이유를 말해 준다). `-DSVF_JMAP=1 -DSVF_JMAP_LIST=0`은
LIST 헤더 규칙(R1', L2, L3, R4)만 적용한다: 통과하는 블록은 폴백을 읽은 채 `JMAP_UNREAD`가 되고, 실패하는 블록은
`JMAP_BAD`가 된다. KS 전용 빌드 `-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0`은 JMAP만 읽는다(이때 폴백은
`JSET_UNREAD`). 잘못된 JSET 부분이 열기를 실패시키는 일은 없다: 페이스는 일반으로 로드되고 상태가 이유를 말한다.
이 행렬은 `tools/test_c_renderer.py`의 `test_status_unread_bits`와 `test_jmap_list_status_matrix`가 테스트한다.

## 포트

| 포트 | 한 줄 설명 | README |
|---|---|---|
| `pico` | Raspberry Pi Pico와 `-DPICO_BOARD=pico2`로 Pico 2(pico-sdk 2.3.1, arm-none-eabi-gcc 15.2.1): 컬러 ST7789 RGB565, 그레이 SSD1327 GRAY8, 모노 SSD1306 MONO_PAGE | [ports/pico/README.ko.md](ports/pico/README.ko.md) |
| `esp32` | ESP-IDF v5.5.6, ESP32-C3와 ESP32-S3: 컬러 ILI9341(또는 `esp_rgb`), 그레이 SSD1327, 모노 SSD1306 | [ports/esp32/README.ko.md](ports/esp32/README.ko.md) |
| `arduino` | Arduino Uno(와 Mega 크기 행): I2C 위의 SSD1306, PROGMEM의 페이스 | [ports/arduino/README.ko.md](ports/arduino/README.ko.md) |
| `ch582` | WCH CH582M(YD-CH582M), 하드웨어 I2C의 SH1106 OLED, 베어메탈, 24 MHz | [ports/ch582/README.ko.md](ports/ch582/README.ko.md) |
| `dos` | DJGPP(gcc 12.2.0, CWSDPMI): 모드 13h의 `SVFDEMO.EXE`와 VBE 2.0 LFB 모드의 `SVFVESA.EXE`, 파일에서 스트리밍하는 페이스 | [ports/dos/README.ko.md](ports/dos/README.ko.md) |
| `web` | `web/`의 WASM 피커용 emscripten(emsdk 6.0.13) 글루 `svf_web.c` | [ports/web/README.ko.md](ports/web/README.ko.md) |
| `sdl` | `svfsdl.c`, SDL2와 SDL3를 위한 하나의 소스, 타깃 종류가 다루는 모든 SDL 픽셀 포맷, 헤드리스 바이트 검사 | [ports/sdl/README.ko.md](ports/sdl/README.ko.md) |

포트의 파일과 플래그를 자신의 프로젝트로 가져가는 방법, 페이스를 내장하는 방법(`bench/mkface.py`), 어떤 페이스가 어떤 타깃에 맞는지는
[docs/c-renderer-guide.ko.md](../docs/c-renderer-guide.ko.md)의 5, 6, 13절에 있다.

원래의 ESP32(Xtensa LX6, Odroid-Go)에는 크기 행(`esp32-xtensa`)이 있지만 포트 이미지는 없다: 자체 드라이버와
보드 코드가 필요하다. Arduino Mega는 64 KB 아래의 PROGMEM만 읽는다(near `pgm_read_byte`). far 읽기는 지원하지 않는다.

## 테스트와 게이트

| 명령 | 증명하는 것 | 시간 |
|---|---|---|
| `make -C c check` | ASan/UBSan 아래의 `tools/test_c_renderer.py`, 이어서 clang으로 다시(2026-11-01 기준 350개 테스트). no-malloc. 모든 `SVF_TARGETS` 마스크 0x000..0x3FF가 경고 없이 컴파일됨(컴파일러당 2066개 작업). 커널 그물(`test-kernels`, `test-pad`, `test-blend16`, `test-vbe`). 좁은 hot-path와 LIST=0 오브젝트 코드 동일성 테스트(Arm 툴체인 필요) | 한 호스트에서 30분 이상: ASan 패스만 966 s(2026-11-01) |
| `python3 -m unittest discover -s tools -p 'test_*.py'` | Python 도구. 위의 C 테스트를 새니타이저 패스 없이 포함 | - |
| `sh c/cross/check-features.sh [OUT]` | AVR과 Cortex-M0+에서 모든 스위치 설정에 대해 P1 프로브를 빌드한다: 게이트된 행이 `SIZES.md`의 "Minimal config"와 정확히 같고, 예산이 지켜지며, 제외된 기능의 심볼이 없고, `JMAP`/`jmap`/`BIG` 문자열이 없다. `features: OK`를 출력 | 한 호스트에서 22 s(2026-11-01) |
| `sh c/cross/test-check-features.sh` | 가짜 행에 대한 `check-features.sh`의 게이트(툴체인 불필요): `check-features-gates: OK` | 약 1 s |
| `sh c/cross/build-all.sh [OUT]` | 프로브 프로파일 P0-P5와 스위치 변형에 대해 모든 툴체인으로 `c/src`를 빌드하고 크기 표를 출력한다(`SIZES.md`에는 손으로 복사). 툴체인이 없거나 Cortex-M0+ P1/P2가 8,192 B를 넘으면 실패 | 한 호스트에서 146 s(2026-11-01) |
| `sh c/cross/build-all.sh --ports [OUT]` | 모든 포트 이미지, `c/ports/check`의 호스트 검사, 에뮬레이션 화면. "Port examples" 표와 비교한다(JMAP-LIST 병합 시점에 43개 OK 줄) | 여기서는 시간을 재지 않음 |
| `sh c/cross/build-all.sh --port NAME [OUT]` | 포트 하나: `dos`, `web`, `sdl`, `arduino`, `ch582`, `pico`, `esp32` | - |
| `sh c/cross/test-build-all.sh` | 픽스처에 대한 화면 게이트와 `SIZES.md` 비교: `build-all-gates: OK` | 약 13 s |
| `sh c/cross/test-manifest.sh`, `sh c/cross/test-installers.sh` | 툴체인 설치 프로그램의 매니페스트. 설치 프로그램 자체(수동, 약 30 s) | 1 s 미만 / 30 s |
| `sh c/ports/check/host-checks.sh`, `sh c/ports/check/run-screens.sh` | 기록용 스텁에 대한 디스플레이 드라이버. 에뮬레이션 화면 다섯 개를 바이트 단위로 | - |
| `sh c/bench/run-{pico,avr,dos,wasm,host,esp32,m33,rp2350}.sh [OUT]` | `MEASUREMENTS.md`용 에뮬레이션 속도 행과 픽셀 체크섬. `run-esp32-hw.sh`는 실제 ESP32-S3 보드가 필요 | 각각 몇 분(여기서는 시간을 재지 않음) |
| `python3 c/bench/jset2-identity.py OLD_DUMP NEW_DUMP OLD_DIR NEW_DIR OUT.md` | 두 `svfdump` 빌드 사이의 모든 페이스의 픽셀 동일성(결과는 `c/bench/JSET2-IDENTITY.md`). `v2v3-identity.py`는 v2 -> v3에 대해 같은 일을 했다 | - |
| `make -C c fuzz-smoke` | 생성된 코퍼스에 대해 각각 `FUZZ_SMOKE_S`(60) 초씩 도는 libFuzzer 타깃 여섯 개(`fuzz`, `-strict`, `-rd`, `-nojmap`, `-nolist`, `-mcu`). clang 필요 | 약 6분과 빌드 시간 |

툴체인과 에뮬레이터는 `c/cross/install-toolchains.sh`와 `c/bench/install-emulators.sh`가 `~/opt`에 설치한다.

## 크기와 속도

크기는 [cross/SIZES.md](cross/SIZES.md)에 있고(그 표는 `build-all.sh --ports`, `check-features.sh`가 비교한다), 속도는
[bench/MEASUREMENTS.md](bench/MEASUREMENTS.md)에 있다. 아래의 대표 수치는 ca86268 시점의 `c/cross/SIZES.md`에서
복사한 것이다. 인용하기 전에 그 파일을 다시 읽을 것.

라이브러리만, P1 프로브(mapped 자모 페이스 하나, MONO_PAGE), 텍스트 바이트("Minimal config"):

| 툴체인 | 설정 | 텍스트 | 게이트 |
|---|---|---:|---|
| AVR (avr-gcc 16.1.0) | `minimal` (Uno 플래그) | 12,930 | 정확 |
| Cortex-M0+ (gcc 15.2.1) | `minimal` (v1 리더만) | 6,162 | 정확 |
| Cortex-M0+ | `default` (두 리더) | 7,381 | 정확 |
| AVR / M0+ | `minimal+RECOG` | 13,238 / 6,358 | 예산 13,250 / 6,366 |
| AVR / M0+ | `minimal+JMAP` (LIST 켬) | 15,370 / 7,646 | 예산 15,532 / 7,688 |
| AVR / M0+ | `minimal+JMAP+nolist` | 15,002 / 7,398 | 예산 15,032 / 7,398 |
| AVR / M0+ | `ksonly` | 13,460 / 6,822 | 예산 13,648 / 6,900 |
| AVR / M0+ | `minimal+BIG` | 12,956 / 6,158 | 참고 |
| AVR / M0+ | `minimal+BIG+V2` | 15,314 / 7,369 | 참고 |

프로그램 전체("Port examples"):

| 이미지 | 텍스트 | data | bss | 비고 |
|---|---:|---:|---:|---|
| Arduino Uno, NEODG16G (`arduino` 행, 10,124 B 페이스) | 23,676 | 18 | 1,085 | 스텁 링크, Uno 플래그 |
| Arduino Mega, Uno 플래그 (`arduino-mega`) | 23,802 | 18 | 1,085 | |
| Arduino Mega, 모든 종류와 리더 (`arduino-mega-rich`) | 40,490 | 18 | 1,094 | |
| ESP32-C3 / ESP32-S3 모노 (스텁 링크) | 22,174 / 20,576 | 0 | 1,088 / 1,092 | 페이스 없이 12,050 / 10,452 |
| 원래의 ESP32 (Xtensa LX6), P1 프로브 | 7,794 | 0 | 848 | 크기 행만, 포트 이미지 없음 |
| Pico 모노, 실제 pico-sdk 2.3.1 이미지 | 35,484 | 0 | 2,384 | "Pico SDK images" |
| CH582 모노, 실제 SDK 이미지 | 22,456 | 20 | 1,232 | 사용 RAM 5,876 B ("CH582 SDK image") |

속도 예산(`MEASUREMENTS.md`에서): Pico `-Os` MONO_PAGE `syl_ga` 48.39 µs(예산 50, 충족), `syl_bwelk` 58.23 µs
(**미달**, `-O2`에서는 충족, 47.18 µs), `screen32` 1,498.39 µs(예산 2 ms). DOS 486DX2-66 `line40_mapped` 11,876.45 µs
(예산 16 ms, 충족, cold streamed와 DX-33 행은 미달). WASM `line40_mapped` 13.74 µs(예산 1 ms).

## 스위치 추가하기

1. **모든 MCU에서 기본은 꺼짐.** 기본값을 `svf.h`의 다른 기본값 옆에 두고 "Size switches" 주석 블록에 문서화한다.
   데스크톱용 기능은 `SVF_JMAP`의 양성 목록(`__unix__ _WIN32 __APPLE__ __DJGPP__
   __EMSCRIPTEN__`, `__AVR__` 아님, `SVF_SMALL` 아님)을 따른다. 명시적인 `-D`가 우선해야 한다.
2. **크기 게이트.** `c/cross/check-features.sh`에 `CONFIGS` 항목을, `SIZES.md`의 "Minimal config"에 그 행을 추가하고,
   그 행에 상한을 걸면 `BUDGETS` 줄을 추가한다. 게이트된 행(`avr minimal`, `m0plus minimal`, `m0plus default`)은
   움직여서는 안 된다. 예산을 올리는 것은 판정이지 편집이 아니다.
3. **심볼 규칙.** 기능의 static에 고유한 접두사를 붙이고, 그것을 빼는 모든 설정에 `check_absent CONFIG PREFIX`를
   추가한다(심볼이 `-Os`에서 살아남는지 확인할 것. 아니면 규칙이 공허해진다. 아래 `jlist` 참조). 라이브러리에는
   문자열이 없다.
4. **상태 행렬 테스트.** 기능이 읽거나 거부하는 모든 페이스 종류는 그 기능이 있는 빌드와 없는 빌드, mapped와
   streamed에 대해 `tools/test_c_renderer.py`에 행을 가진다(`test_jmap_list_status_matrix`처럼). 추가로 퍼즈 시드가
   필요하고, 하니스가 새 경로에 닿을 수 있다면 퍼즈 타깃도 필요하다.
5. **hot-path 동일성.** 스위치가 조회 또는 검증 코드를 건드리면, 스위치를 껐을 때 옛 경로의 오브젝트 코드가
   바뀌지 않았음을 증명하고(`test_narrow_hot_path_identical`, `test_jmap_nolist_identical`),
   `svf/`에 대해 `c/bench/jset2-identity.py`의 동일성 검사를 돌린다.

## 알려진 공백

- Cortex-M0+ `minimal+JMAP+nolist` 예산은 **여유가 0**이다(7,398 중 7,398): LIST=0 쪽이나 JMAP 리더에 한 바이트라도
  더해지면 다시 측정하고 예산을 판정해야 한다.
- `check_absent ... jlist`는 실제 빌드에서 실패할 수 없다(`-Os`에서 `jlist_` 심볼이 남지 않는다). 실제 누출 방지는
  `+nolist` 크기 행과 `test_jmap_nolist_identical`이다.
- `SVF_JMAP` 없는 LIST 리더는 없다(MCU 예외 페이스에는 필요할 것이다). `SVF_NO_STREAM`/`mcu-strict`를 쓰는 BIG
  (AVR BIG 포트)은 퍼즈하지 않는다.
- Arduino Mega: 플래시 64 KB를 넘는 페이스는 far 읽기가 필요하지만 지원하지 않는다.
- DOS: 51a4020의 프로브에서 행이 약 +105 µs(+0.9 %) 읽혔고, 원인은 설명되지 않았으며, 표는 다시 뜨지 않았다.

출처: `c/cross/SIZES.md`의 "JMAP-LIST identity, budgets and follow-ups",
`docs/superpowers/specs/2026-10-26-jset-limits-design.md`와 `2026-10-27-jmap-list-design.md`의 "Implemented" 노트,
`c/bench/MEASUREMENTS.md`의 "Results". 저장소 전체의 개발 상태는 [docs/STATUS.md](../docs/STATUS.md)에 있다.
