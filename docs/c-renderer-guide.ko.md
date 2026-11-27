[English](c-renderer-guide.md) | **한국어**

# SVF C 렌더러: 통합 가이드

이 가이드는 SVF C 렌더러(`c/`)를 자신의 프로그램에 넣는 방법을 설명한다. 소스를 얻는 방법, 페이스(face)를 여는 방법, 페이스를 펌웨어에
내장하는 방법, 타깃에 들어가는 페이스를 고르는 방법, 자모 세트로 한글 음절을 조합하여 UTF-8 텍스트를 그리는 방법, 그리기 타깃을 고르는 방법, 메모리
예산을 잡는 방법, 저장소에 예제가 있는 각 플랫폼용으로 빌드하는 방법, 그리고 그림이 잘못 나올 때 무엇을 확인할지를 다룬다. 이 문서는 튜토리얼이다. 레퍼런스는 [c/README.ko.md](../c/README.ko.md)(API 표, 컴파일 타임 스위치,
포트)이며, 무엇보다 모든 함수의 정확한 계약을 밝혀 두는 [c/include/svf.h](../c/include/svf.h)의 주석이다. 파일 포맷은
[spec/SVF.ko.md](../spec/SVF.ko.md)에, 설계는 [spec/renderer-design.ko.md](../spec/renderer-design.ko.md)에 있다.

아래의 모든 C 예제는 이 저장소를 대상으로 `gcc -std=c99 -Wall -Wextra`로 컴파일했다(페이스 내장 샘플은 arm-none-eabi-gcc로 Cortex-M0+용으로, avr-gcc로
ATmega328P용으로도, 플랫폼 샘플은 해당 플랫폼의 툴체인으로 컴파일했다). 실행할 수 있는 곳에서는 배포되는 페이스로 실행했으며, 표시된 출력은 실제 출력이다.

## 목차

1. 다섯 단어로 보는 모델
2. 라이브러리를 빌드에 넣기
3. 완전한 첫 번째 프로그램
4. 페이스: 매핑 방식과 스트리밍 방식
5. 페이스 내장하기
6. 타깃에 맞는 페이스 고르기
7. 텍스트 한 줄: 체인, 메트릭, 측정
8. 타깃: 픽셀이 가는 곳
9. 스케일링
10. 한글: 자모 페이스와 음절 조합
11. 메모리 예산
12. 컴파일 타임 스위치: 세 가지 레시피
13. 플랫폼: Arduino, CH582, DOS, ESP32, Pico, SDL, 웹
14. 자체 텍스트 경로가 있는 애플리케이션에 통합하기
15. 통합 테스트
16. 문제 해결

## 1. 다섯 단어로 보는 모델

**페이스, 체인, 타깃, 스크래치, 줄.**

- **페이스(face)**(`svf_face`)는 열린 `.SVF` 파일 하나이다. 셀 크기, 비트 깊이(픽셀당 1, 2 또는 8비트), 글리프 테이블, 그리고 선택적으로
  한글 음절을 조합할 수 있게 해 주는 자모 세트(11,172자 전부, 또는 그 테이블이 담은 음절)로 이루어진다. 구조체는 호출자가 할당하며, 라이브러리는 할당하지 않는다.
- **체인**(`svf_chain`)은 페이스의 순서 있는 목록이다. 각 코드 포인트는 그것을 가진 첫 번째 페이스가 그리므로,
  `{ ascii_face, hangul_face }`는 두 페이스로 섞인 줄을 그린다.
- **타깃**(`svf_target`)은 픽셀이 가는 곳이다. 열 가지 픽셀 포맷 중 하나의 바이트 버퍼이거나, 픽셀마다 `(x, y, coverage)` 하나씩을
  받는 콜백이다.
- **스크래치**는 셀 하나를 담기에 충분한, 호출자가 제공하는 바이트 버퍼이다. 크기는 `svf_chain_scratch_bytes()`가 알려 준다.
- **줄**은 호출 하나, 즉 `svf_draw_utf8()`이다. UTF-8 바이트가 들어가고 픽셀이 나오며, 베이스라인을 따라 그려진다.

모든 것은 C99이고, `<stdint.h>`, `<stddef.h>`, `<string.h>`만 사용하며, `malloc`을 호출하지 않고, Python 레퍼런스
(`tools/jamoset.py`, `tools/svfline.py`)와 바이트 단위로 동일한 픽셀을 그린다.

아래에서 쓰는 용어: **셀**은 글리프 하나의 저장된 비트맵(`cell_w x cell_h` 픽셀)이다. **커버리지**는 한 픽셀에 잉크가 얼마나 있는가를
0..255로 나타낸 값이다(1 bpp 잉크 픽셀은 255, 2 bpp 레벨 `k`는 `k * 85`, 8 bpp 픽셀은 그 바이트 자체). **베이스라인**은 어센트 아래의
행이며, 셀의 맨 위 행은 `y_baseline - ascent + dy`이다.

## 2. 라이브러리를 빌드에 넣기

라이브러리는 소스 파일 다섯 개, 비공개 헤더 하나, 공개 헤더 하나이다. 의존성은 없다.

    c/include/svf.h
    c/src/svf_face.c  svf_jamo.c  svf_stream.c  svf_draw.c  svf_scale.c   (+ svf_internal.h)

사용 방법은 세 가지이다.

1. **소스를 프로그램에 직접 컴파일한다.** 빌드에 `c/src/*.c`를 추가하고 `-I c/include`를 준다. 여기의 예제들이 이 방법을 쓴다.

       gcc -std=c99 -I c/include my_app.c c/src/*.c -o my_app

2. 저장소의 Makefile로 **정적 라이브러리를 빌드한다.** `make -C c`는 `libsvf.a`(와 `svfdump` 도구)를 `c/build`에 쓰며, `O=DIR`로 위치를 옮길 수 있다.
3. **벤더링하거나 서브모듈로 넣는다.** 저장소는 공개이며 코드는 MIT 라이선스이다(`svf/` 아래의 페이스는 OFL이다.
   [NOTICE.ko.md](../NOTICE.ko.md) 참조). ScummVM 같은 프로젝트는 저장소를 git 서브모듈로 추가하고 소스들을 자체 빌드 시스템으로
   컴파일할 수 있다.

**무엇보다 중요한 규칙이 하나 있다. `svf.h`를 include하는 모든 소스 파일과 모든 라이브러리 소스는 같은 `-D` 스위치로 컴파일해야 한다.**
`SVF_JMAP`은 `svf_face`의 크기를 바꾸므로, 빌드를 섞으면 메모리가 손상된다. 스위치는 한곳에 두라(프로젝트 전체의 플래그 변수, 또는
강제로 include하는 작은 헤더).

데스크톱(`__unix__`, `_WIN32`, `__APPLE__`을 정의하는 컴파일러), DOS 빌드(`__DJGPP__`), WASM 빌드(`__EMSCRIPTEN__`)에서는 스위치가 필요 없다. 기본값이
전체 기능 집합이다(모든 타깃 종류, 스트리밍, 스케일링, 모든 자모 블록 버전). 거기서는 무언가를 *제거*할 때에만 스위치를 설정한다. **그 밖의 타깃은
작은 장치용 기본값을 받는다.** MCU, 베어메탈, 또는 위 매크로를 하나도 정의하지 않는 컴파일러는 버전 3(JMAP, LIST) 자모 블록과 BIG 한계를 읽지 않으므로
그것을 필요로 하는 페이스는 일반 페이스로 열린다. 필요한 것은 명시적으로 설정하라(12절의 `-DSVF_JMAP=1` 등). `-DSVF_SMALL`은 데스크톱에서도 같은
효과를 낸다(12절).

## 3. 완전한 첫 번째 프로그램

이 프로그램은 페이스 파일을 열고, 한글/라틴 혼합 줄을 8비트 버퍼에 그린 뒤, 텍스트로 출력한다. `ex1.c`로 저장한다.

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
	FILE *fp = fopen(path, "rb");
	if (!fp) return NULL;
	fseek(fp, 0, SEEK_END);
	long n = ftell(fp);
	fseek(fp, 0, SEEK_SET);
	uint8_t *p = malloc((size_t)n);
	if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
	fclose(fp);
	*len = (size_t)n;
	return p;
}

int main(int argc, char **argv)
{
	size_t len;
	uint8_t *bytes = slurp(argv[1], &len);
	svf_face face;
	svf_err err = bytes ? svf_open_mapped(&face, bytes, len) : SVF_E_IO;
	if (err != SVF_OK) { fprintf(stderr, "open failed: %d\n", (int)err); return 1; }

	svf_face *faces[1] = { &face };
	svf_chain chain = {0};            /* 0으로 초기화: 스케일 1/1, 기본 마크, 캐시 없음 */
	chain.faces = faces;
	chain.count = 1;

	const char *text = argc > 2 ? argv[2] : "SVF 안녕";
	svf_extent e;
	svf_measure_utf8(&chain, text, strlen(text), &e);
	/* e.width는 잉크가 아니라 펜 이동 거리이다. 마지막 셀이 그 너머까지 닿을 수 있으므로 셀 폭만큼 여유를 둔다 */
	int w = e.width + svf_cell_w(&face) + 2, h = e.ascent + e.descent + 2;
	uint8_t *pix = calloc((size_t)w * h, 1);
	size_t need = svf_chain_scratch_bytes(&chain);
	uint8_t *scratch = malloc(need);

	svf_target t;
	if (svf_target_init(&t, SVF_T_GRAY8, pix, (size_t)w * h, (int16_t)w, (int16_t)h, (uint16_t)w) != SVF_OK) return 1;
	err = svf_draw_utf8(&chain, text, strlen(text), 1, (int16_t)(1 + e.ascent), &t, scratch, need);
	/* err는 SVF_OK이거나, 스트리밍 읽기가 도중에 실패했다면 SVF_E_IO이다 */

	for (int y = 0; y < h; y++) {
		for (int x = 0; x < w; x++) putchar(pix[y * w + x] > 127 ? '#' : pix[y * w + x] ? '+' : '.');
		putchar('\n');
	}
	return 0;
}
```

배포되는 페이스로 빌드하고 실행한다.

    gcc -std=c99 -Wall -Wextra -I c/include ex1.c c/src/*.c -o ex1
    ./ex1 svf/dos/NEODG16A.SVF

출력(16x16 자모 세트 페이스이며, 한글은 그릴 때 조각들로 조합된다).

    ..................................................................................
    ..................................................................................
    ....................................####....##....##.........##...................
    ..#####..##...##..######...........##..##...##....##.........##...................
    .##...##.##...##.##...............##....##..##....##......#####...................
    .##......##...##.##...............##....##..#####.##.........##...................
    .##......##...##.##...............##....##..##....##......#####...................
    ..#####..##...##.######............##..##...##....##.........##...................
    ......##.##...##.##.................####....##.....#######...##...................
    ......##.##...##.##...............................................................
    ......##.##...##.##................##................########.....................
    .##...##..##.##..##................##..............###......###...................
    ..#####....###...##................##..............##........##...................
    ...................................##..............###......###...................
    ....................................##########.......########.....................
    ..................................................................................
    ..................................................................................
    ..................................................................................

단계별로 살펴보면 다음과 같다.

- `svf_open_mapped`는 파일 전체를 검증한다. 열린 페이스는 그려도 안전하다. 반환값은 파일이 거부된 이유(`SVF_E_MAGIC`,
  `SVF_E_VERSION`, ...)를 알려 준다.
- `svf_measure_utf8`는 글리프를 읽지 않고 줄의 범위(extent)를 준다. `e.width`는 **펜 이동 거리**(advance의 합)이며 잉크의 폭이 아니다. `e.ascent`와
  `e.descent`는 셀이 베이스라인 위와 아래로 닿는 행 수이다(잉크가 있는 행만이 아니라 셀 전체). 여기서는 64 x (12 + 4)이다.
- 그래서 버퍼의 폭은 `e.width + 2`가 아니라 `e.width + svf_cell_w(&face) + 2`이다. 글리프는 advance 너머에 잉크가 있을 수 있어(PAPLG16의 `f`는 3픽셀 넘어까지
  닿는다. 측정값) 마지막 셀이 셀 폭만큼 더 필요할 수 있고, 줄 맨 앞의 결합 마크는 `x`의 왼쪽에서 시작할 수 있다. 라이브러리는 타깃에 맞춰 클립하므로 바깥에는
  아무것도 쓰이지 않는다. 버퍼가 너무 작으면 메모리가 손상되는 것이 아니라 잉크가 잘린다.
- `svf_draw_utf8`에 넘기는 베이스라인 행은 `1 + e.ascent`이다. 범위의 어센트에 우리가 남겨 둔 1픽셀 여백을 더한 값이다.
- 타깃에는 `rows * stride` 이상의 `buf_len`이 필요하다. `svf_target_init`는 이를 검사하여, 모자라거나, 해당 종류가 이 빌드에 컴파일되어
  있지 않거나, stride가 너무 작으면 거부한다(`SVF_E_ARG`).

## 4. 페이스: 매핑 방식과 스트리밍 방식

페이스를 여는 방법은 두 가지이다. 그 뒤에는 모든 호출이 같다.

### 4.1 매핑 방식: 파일 전체가 주소 지정 가능하다

    svf_err svf_open_mapped(svf_face *f, const uint8_t *data, size_t len);

페이스가 RAM, 플래시(`const` 배열) 또는 PROGMEM에 있을 때 쓴다. 라이브러리는 `data`를 **제자리에서** 읽는다. 페이스를 쓰는 동안 그
바이트는 유효하고 변하지 않아야 한다(글리프 레코드는 다시 검사하지 않고 그린다). AVR에서는 모든 페이스 읽기가 `pgm_read_byte`를
거치도록 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 라이브러리를 빌드한다.

데스크톱에서는 파일을 힙 버퍼로 `fread`하거나(3절) `mmap`할 수 있다. 버퍼를 계속 살려 두라.

### 4.2 스트리밍 방식: 파일이 디스크, SD 카드 또는 네트워크에 남는다

    size_t svf_stream_tables_size(svf_read_fn rd, void *ctx, uint32_t file_len, svf_err *err);
    svf_err svf_open_stream(svf_face *f, svf_read_fn rd, void *ctx, uint32_t file_len,
                            uint8_t *tables, size_t tables_len,
                            uint8_t *cache, size_t cache_len, uint16_t block_size);

읽기 콜백, 파일의 테이블(헤더, 코드 포인트 테이블, 메트릭, 자모 블록, 글리프 오프셋 테이블)을 담을 버퍼, 그리고 선택적으로 블록 캐시를
제공한다. 글리프 행은 그릴 때 읽힌다. DOS 프로그램들이 이렇게 하므로, 1 MB 페이스에 1 MB의 RAM이 필요하지 않다.

```c
static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
{
	FILE *fp = ctx;
	return fseek(fp, (long)off, SEEK_SET) == 0 ? (long)fread(dst, 1, len, fp) : -1;
}

static uint8_t tables[256 * 1024], cache[8 * (1024 + 8)];
svf_err err;
size_t need = svf_stream_tables_size(rd, fp, file_len, &err);   /* 헤더가 거부되면 0을 반환하고 err가 설정된다 */
if (need && need <= sizeof tables)
	err = svf_open_stream(&face, rd, fp, file_len, tables, sizeof tables, cache, sizeof cache, 1024);
```

알아 둘 규칙은 다음과 같다.

- `svf_stream_tables_size`는 `tables`가 얼마나 커야 하는지 알려 준다. 이는 페이스에, 그리고 빌드가 어떤 리더를 컴파일했는지에 달려 있다.
  `NEODG16A.SVF`(자모 페이스)는 8,153바이트이고, 완성형 `NEODG16.SVF`는 46,492바이트이다(측정값).
- 블록 캐시는 선택 사항이다(`cache_len`이 0이면 없음). 캐시가 있으면 라이브러리는 `block_size`바이트 블록(64에서 4096 사이의 2의 거듭제곱)
  전체를 읽고 가장 최근에 쓴 것들을 유지한다. 슬롯 하나는 `block_size + 8`바이트이며 캐시는 최소 두 슬롯을 담아야 한다.
  `cache_len`으로 `sizeof cache`를 넘긴다.
- 페이스는 사용자의 `tables`, `cache`, `rd`, `ctx`에 대한 포인터를 유지하므로 이것들을 살려 두라. 하나의 페이스(캐시 포함)를 두 스레드에서
  동시에 그려서는 안 된다.
- 읽기가 실패하거나 모자라면 그리고 있던 글리프에 대해서만 `SVF_E_IO`가 반환된다. 줄은 계속 그려지고 오류는 끝에서 반환된다.
  `svf_stream_reads(&face)`는 콜백 호출 횟수를 센다(캐시 크기를 조정할 때 유용하다).
- 캐시 **없이** 스트리밍 페이스의 음절을 조합하려면 `2 * svf_cell_bytes`의 스크래치가 필요하다(후반부에는 읽고 있는 조각이 들어간다).
  `svf_chain_scratch_bytes`가 이미 이를 반영한다.
- `-DSVF_NO_STREAM`으로 빌드하면 이 함수들은 선언조차 되지 않는다. 호출하면 런타임 실패가 아니라 컴파일 오류가 된다.

### 4.3 페이스가 알려 주는 것

열기에 성공한 뒤에는 접근자들이 헤더를 보고한다. `svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`, `svf_glyph_count`, `svf_flags`.
`svf_has(f, cp)`는 페이스가 코드 포인트를 그릴 수 있는지(저장된 글리프, 또는 조합해 내는 음절이나 호환 자모)를 알려 준다.
`svf_metrics_of(f, cp, &m)`는 글리프의 advance, bearing, 잉크 폭, 수직 오프셋을 반환한다.

`svf_status(f)`는 놓치기 쉽지만 중요하다. 페이스는 성공적으로 열리고도 무엇이 버려졌는지를 알리는 **상태 비트**를 가질 수 있다. 예를 들어
`SVF_FACE_JSET_BAD`(자모 블록이 검증에 실패했다. 이 페이스는 일반 페이스이며 한글을 조합하지 않는다)나 `SVF_FACE_JSET_UNREAD`(자모
블록은 멀쩡하지만 이 빌드가 그 버전을 읽지 않는다)가 있다. 음절이 나오지 않을 때 가장 먼저 확인할 것은 상태가 0이 아닌 한글 페이스이다
(16절).

## 5. 페이스 내장하기

마이크로컨트롤러에는 파일 시스템이 없거나, 있어도 의존하고 싶지 않다. 또 페이스 하나만 싣는 프로그램은 페이스를 프로그램 안에 넣는 편이
단순하다. `c/bench/mkface.py`가 페이스를 C 배열로 써 준다.

    python3 c/bench/mkface.py svf/dos/NEODG16G.SVF face.c --name neodg16g --profile mcu-strict

Python 3과 저장소의 `tools/`가 필요하며(`tools/jamoset.py`를 자신의 위치 기준 상대 경로로 import하므로 체크아웃에서 실행해야 한다),
출력 파일 말고는 아무것도 쓰지 않는다. `--name`은 C 식별자여야 한다. 출력은 다음과 같다(일부 생략).

```c
/* Generated by c/bench/mkface.py from svf/dos/NEODG16G.SVF (10124 bytes, profile mcu-strict). */
#include <stdint.h>
#ifdef __AVR__
#include <avr/pgmspace.h>
#define BENCH_FACE_ATTR PROGMEM
#else
#define BENCH_FACE_ATTR
#endif
const uint8_t neodg16g[] BENCH_FACE_ATTR __attribute__((aligned(4))) = {
	83,86,70,78,3,0,7,0,1,2,2,0,23,1,16,16,12,0,0,0,120,11,0,0,
	...
};
const uint32_t neodg16g_len = 10124u;
```

- 배열은 `const`이므로 플래시(읽기 전용 데이터)에 머물며 RAM을 쓰지 않는다. AVR에서는 `PROGMEM`이어서 플래시 고유의 주소 공간에 놓이고,
  라이브러리는 `SVF_RD8`을 통해 읽는다(4.1절). `NAME_len`은 페이스의 바이트 크기이다. 둘 다 `svf_open_mapped`에 넘긴다.
- `aligned(A)`의 `A`는 기록된 레이아웃의 `2^max(REC, TAB)`바이트이다(`mcu-strict`는 4이며 1이면 생략된다). 그래서 파일 안의 레코드
  오프셋이 곧 주소 정렬이 된다. 정렬은 **속도에만** 관여한다. `svf_open_mapped`는 *파일 안의* 오프셋 정렬을 레이아웃에 맞춰 검사할 뿐
  배열의 주소는 검사하지 않는다. 페이스는 홀수 주소에서도 똑같이 열리고 그려진다(테스트함).
- `--profile mcu-strict`는 페이스를 `SVF_LAYOUT_MCU_STRICT` 레이아웃(레코드와 테이블 단위 4바이트, 행 단위 1바이트, 들어맞는 곳은 16비트
  오프셋)으로 다시 쓴다. 픽셀은 같다. **`svf/` 아래의 모든 페이스는 이미 그 레이아웃이다**(단위 기준. 117개 파일 전체를 `svfdump FACE info`로
  확인했다). 따라서 `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` 빌드는 배포된 파일을 그대로 열 수 있고, 프로필은 오프셋만 줄인다. NEODG16G는
  10,684바이트에서 10,124바이트가 된다. `--profile`을 주지 않으면 바이트는 파일 그대로이다. `tight` 프로필(1/1/1)의 페이스는 그런
  빌드에서 `SVF_E_LAYOUT`으로 거부된다.
- **`xxd -i`를 쓰지 말라.** 이것은 `const`가 아닌 `unsigned char name[]`를 쓰므로 배열이 `.data`, 곧 RAM 사본에 놓인다(arm-none-eabi-gcc
  15.2.1로 측정: NEODG16G는 `.data` 10,688바이트이며, Uno의 전체 RAM의 다섯 배이다). AVR에서는 `PROGMEM`도 없고, 정렬도 없으며,
  `unsigned int name_len`은 16비트이다. RAM 사본이 목적인 데스크톱에서는 괜찮다.

### 5.1 배열이 가는 곳, 플랫폼별

| 타깃 | 페이스가 있는 곳 | 비고 |
|---|---|---|
| AVR(Arduino Uno) | `PROGMEM` 플래시 | 라이브러리를 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드한다. `SVF_RD8`이 없으면 라이브러리가 플래시 주소를 RAM으로 읽어 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환한다(simavr에서 실행: 재정의가 있으면 0, 없으면 1). `svf_draw_utf8`에 넘기는 텍스트는 일반 로드로 읽힌다. RAM에 두라(`PROGMEM` 문자열은 먼저 `strncpy_P`로 복사한다) |
| 그 밖의 Arduino 코어(ARM, ESP32, RP2040) | 플래시의 `const` 배열 | 플래시가 메모리에 매핑되어 있으므로 `SVF_RD8` 재정의도 `PROGMEM`도 필요 없다(`mkface`는 `__AVR__`에서만 `PROGMEM`을 붙인다) |
| ESP32(ESP-IDF) | `const` 배열(플래시의 `.rodata`), **또는** `esp_partition_mmap`으로 매핑한 데이터 파티션, **또는** 스트리밍하는 SPIFFS 파일 | 파티션은 페이스를 앱 이미지와 그 크기에서 빼 준다. SPIFFS + `svf_open_stream`은 주소 공간에서도 뺀다(13.4절) |
| Raspberry Pi Pico / Pico 2 | 플래시의 `const` 배열, 제자리 실행(XIP) | 페이스는 XIP 캐시를 거쳐 읽힌다. 블록을 처음 건드리면 플래시 읽기이다(13.5절) |
| CH582 | CodeFlash의 `const` 배열 | 링커가 `.rodata`를 플래시에 둔다. RAM 사본이 없다 |
| DOS, SDL, 데스크톱, WASM | 메모리에 읽어 들인 파일(`fread`, `SDL_LoadFile`, 모듈로 복사한 JavaScript `Uint8Array`), 또는 `mmap` | 또는 파일에서 스트리밍(4.2절). 버퍼는 페이스보다 오래 살아야 한다 |

### 5.2 연 뒤에: 페이스를 확인하라

`svf_open_mapped`는 파일이 유효하다는 것만 알려 줄 뿐, 이 빌드가 그 한글을 조합할 수 있다는 것은 알려 주지 않는다. 시작할 때 한 번 둘 다
확인하라(이것이 `text_cb.c`이다. 호스트와 Cortex-M0+에서, 그리고 13.1절의 Uno 플래그에 `-DSVF_TARGETS=0x10`을 주면 AVR에서도 컴파일된다. 이 예제는 콜백 종류로 그리므로 `0x02`이면 `text_init`이 -3을 반환한다).

```c
/* text_cb.c - mkface.py로 내장한 페이스로, 자신의 픽셀 루틴을 통해 UTF-8을 그린다. */
#include <stdint.h>
#include <string.h>
#include "svf.h"

extern const uint8_t neodg16g[];            /* mkface.py --name neodg16g 로 만든 face.c */
extern const uint32_t neodg16g_len;

/* 디스플레이 드라이버: 픽셀 하나, 켜짐/꺼짐(또는 cov에서 얻은 회색 레벨). */
void lcd_set_pixel(int16_t x, int16_t y, uint8_t on);

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	(void)ctx;
	lcd_set_pixel(x, y, cov >= 128);
}

static svf_face face;                       /* 모든 그리기보다 오래 살아야 한다 */
static svf_face *faces[1] = {&face};
static svf_chain chain;
static svf_target target;
static uint8_t scratch[32];                 /* >= svf_chain_scratch_bytes(&chain): 16 x 16 x 1 bpp */

int text_init(int16_t lcd_w, int16_t lcd_h)
{
	if (svf_open_mapped(&face, neodg16g, neodg16g_len) != SVF_OK)
		return -1;
	memset(&chain, 0, sizeof chain);
	chain.faces = faces;
	chain.count = 1;
	chain.missing_advance = 8;
	if (svf_chain_scratch_bytes(&chain) > sizeof scratch)
		return -2;
	if (svf_target_init(&target, SVF_T_COVERAGE_CB, NULL, 0, lcd_w, lcd_h, 0) != SVF_OK)
		return -3;
	target.plot = plot;
	return svf_is_jamo(&face) && svf_status(&face) == 0 ? 0 : -4;   /* -4: 일반 페이스로 열림: 이유는 svf_status */
}

/* s를 왼쪽 위가 (x, y_top)이 되도록 그린다. 그려진 폭(펜 이동 거리)을 반환한다. */
int text_draw(const char *s, int16_t x, int16_t y_top)
{
	svf_extent e;
	if (svf_measure_utf8(&chain, s, strlen(s), &e) != SVF_OK)
		return -1;
	if (svf_draw_utf8(&chain, s, strlen(s), x, (int16_t)(y_top + svf_ascent(&face)), &target, scratch,
	                  sizeof scratch) != SVF_OK)
		return -1;
	return e.width;
}
```

한글을 조합하는 페이스에서는 `svf_is_jamo`가 1이고, 아무것도 버려지지 않았으면 `svf_status`가 0이다(4.3절). 열렸지만 일반 페이스인 것(`JSET_BAD`,
`JSET_UNREAD`, `JMAP_UNREAD`)은 라틴만 그리고 한글은 말없이 그리지 않는다. 현장이 아니라 작업대에서 이것을 알아내는 방법이 이 검사이다.
완성형 페이스에는 자모 블록이 없으므로 대신 `svf_has(&face, 0xD55C)`를 확인한다.

### 5.3 C++와 Arduino: `face.c`는 C 파일로 둔다

배열은 `.c` 파일로 생성하여 C 컴파일러가 빌드하게 하라. C++에서 네임스페이스 범위의 `const` 배열은 내부 링크이고 C++ 이름을 가지므로 다른
파일의 링커가 찾지 못한다. Arduino 빌드는 스케치 폴더의 `.c` 파일을 C로 컴파일한다. C++ 쪽에서는 C 링키지로 선언한다(`c/ports/arduino/arduino.ino`가
그렇게 한다).

```cpp
#include <avr/pgmspace.h>
#include "svf.h"                          /* svf.h는 C++에서 스스로 extern "C"로 감싸져 있다 */

extern "C" {
extern const uint8_t neodg16g[] PROGMEM;  /* face.c, mkface.py에서 */
extern const uint32_t neodg16g_len;
}

static svf_face face;
bool face_ok() { return svf_open_mapped(&face, neodg16g, neodg16g_len) == SVF_OK; }
```

### 5.4 배포할 라이선스

페이스가 들어 있는 프로그램이나 이미지는 폰트 소프트웨어를 배포하는 것이다. 다음을 함께 배포하라. 페이스 자체의 라이선스 텍스트(NEODG16G는
`svf/dos/OFL.TXT`와 `svf/dos/NEODGM.TXT`, PAPLG16과 PAPLG18은 `svf/dos/OFLPAPLG.TXT`. `web/LICENCES.tsv`가 `svf/` 아래 모든 페이스를 그
라이선스 파일에 대응시킨다), [NOTICE.ko.md](../NOTICE.ko.md)(무엇이 어떤 라이선스 아래에 있는지), 그리고 [LICENSE](../LICENSE)(라이브러리
코드의 MIT). `c/ports/FACES.md`는 포트가 내장하는 각 페이스의 출처, 저작권, 라이선스를 밝히며, Pico, ESP32, CH582 빌드는 이것과 라이선스
텍스트를 `<build>/licences/`에 복사한다.

## 6. 타깃에 맞는 페이스 고르기

페이스는 파일이다. 어디에 들어가는지는 픽셀 크기가 아니라 파일 크기가 정한다. 쓰려는 페이스를 직접 측정하라.

    python3 c/bench/mkface.py svf/dos/NEODG16A.SVF x.c --name x --profile mcu-strict && tail -2 x.c

마지막 줄 `const uint32_t x_len = 15528u;`가 아래 표의 숫자이다. 링크되는 바이트이다. 이 저장소의 페이스를 `mcu-strict`로 측정한 값이다.

| 페이스 | 셀, 비트 | 한글 | 배열 바이트 | 셀 바이트 | 스트리밍 테이블 | Uno | CH582 | Pico | ESP32 |
|---|---|---|---:|---:|---:|---|---|---|---|
| `PAPLG16` | 18x18, 2 | 없음(ASCII, 글리프 149개) | 7,460 | 90 | 2,396 | 예 | 예 | 예 | 예 |
| `NEODG16G` | 16x16, 1 | 자모(11,172자 전부 조합) | 10,124 | 32 | 5,129 | 예 | 예 | 예 | 예 |
| `NEODG16A` | 16x16, 1 | 자모 | 15,528 | 32 | 8,153 | 예 | 예 | 예 | 예 |
| `NEODG16C` | 16x16, 1 | 자모 | 19,088 | 32 | 9,721 | 아니오 | 예 | 예 | 예 |
| `NDGPR16`(`svf/jamo-extra`) | 16x16, 1 | 자모 | 25,532 | 32 | 15,519 | 아니오 | 예 | 예 | 예 |
| `NEODG32` | 36x36, 1 | 자모 | 30,616 | 180 | 8,153 | 아니오 | 예 | 예 | 예 |
| `SGDAY16`(`svf/jamo-extra`) | 16x16, 1 | 자모 | 38,204 | 32 | 23,117 | 아니오 | 예 | 예 | 예 |
| `NSQRR16`(`svf/jamo-extra`) | 16x16, 1 | 자모 | 53,204 | 32 | 30,365 | 아니오 | 예 | 예 | 예 |
| `PAPLG18` | 18x18, 2 | 자모 | 67,200 | 90 | 29,341 | 아니오 | 예 | 예 | 예 |
| `NEODG16` | 16x16, 1 | 완성형(글리프 2,905개) | 127,908 | 32 | 46,492 | 아니오 | 예 | 예 | 예 |
| `NGOTB15` | 16x16, 2 | 완성형(글리프 2,446개) | 178,352 | 64 | 39,148 | 아니오 | 예 | 예 | 예 |
| `GBATB47` | 46x54, 2 | 완성형(글리프 2,446개) | 1,162,764 | 648 | 39,148 | 아니오 | 아니오 | 예 | 더 큰 파티션 필요 |

- **한글.** 자모 세트 페이스는 수백 개의 조각을 저장하고 모든 음절을 조합한다. 완성형 페이스는 담당하는 음절마다 글리프 하나를 저장하므로(KS X
  1001의 흔한 2,350자와 몇 자 더) 같은 픽셀 크기에서 몇 배 더 크고(NEODG16 대 NEODG16A: 8배) 나머지는 그리지 못한다. 작은 장치에는 자모
  페이스를 고르라.
- **Uno**(ATmega328P. Optiboot과 함께 플래시 32,256바이트, RAM 2 KB): NEODG16G 스케치는 10,124바이트 페이스와 함께 플래시 23,694바이트이므로
  13,570바이트가 코드이다. 페이스는 18,686바이트 이하여야 한다(13,570 + 15,528 = 29,098은 들어가고, 13,570 + 19,088 = 32,658은 들어가지
  않는다). 자모 페이스는 Uno 스위치(`SVF_JSET_V2=0`, `JMAP` 없음, `BIG` 없음)로 열리고 조합된다(호스트에서 그 스위치로 확인했다).
- **CH582**: CodeFlash 448 KB이다. 페이스를 제외한 이미지는 코드 약 12 KB이므로 약 400 KB까지의 페이스가 들어간다. 매핑된 페이스에서는 RAM
  (32 KB)이 한계가 아니다.
- **Pico**: Pico 보드는 플래시 2 MB(Pico 2는 4 MB)이며 제자리 실행한다. mono 이미지 전체가 10,124바이트 페이스를 포함해 35,484바이트이다(13.5절).
  위의 모든 페이스가 들어간다. 페이스가 클수록 XIP 캐시(RP2040은 16 KB)가 더 자주 빗나간다.
- **ESP32-C3 / S3**: 모듈의 플래시는 보통 4 MB이고 기본 파티션 테이블은 애플리케이션 파티션이 1 MB이다. mono 이미지는 페이스를 포함해
  229,648바이트(페이스 제외 약 220 KB)이므로 GBATB47만 빼고 모두 들어간다. GBATB47은 자신의 데이터 파티션에 둔다(13.4절).
- **스트리밍**(SD, SPIFFS, 디스크의 파일)에는 테이블용 RAM(위 열, 배포된 파일 기준)에 블록 캐시가 더 필요하다. Uno는 할 수 없다(`NEODG16G`만으로도
  테이블이 5,129바이트이고, Uno 빌드는 리더를 뺀다).
- 그리기에 쓰는 **RAM**은 적다. 스크래치는 셀 하나(`셀 바이트`, 11절)이고 여기에 프레임 버퍼가 더해진다.

## 7. 텍스트 한 줄: 체인, 메트릭, 측정

### 7.1 폴백 체인

```c
svf_face *faces[2] = { &latin_face, &hangul_face };
svf_chain chain = {0};
chain.faces = faces;
chain.count = 2;
chain.missing_advance = 8;      /* 어느 페이스에도 없는 코드 포인트에 대해 전진할 픽셀 수(아무것도 그려지지 않음) */
```

각 코드 포인트는 `svf_has`가 참인 첫 번째 페이스가 그린다. 순서가 중요하다. 공유되는 문자(숫자, 구두점)에 원하는 스타일의 페이스를
먼저 두라. `chain.faces`가 `NULL`이거나, `count`가 0이거나, 항목 중 하나가 NULL이면 체인은 "페이스 없음" 상태가 된다. 이 체인을 쓰는
호출은 `SVF_E_ARG`를 반환하고 아무것도 그리지 않는다.

### 7.2 마크, advance, 잘못된 UTF-8

- advance는 페이스의 메트릭 테이블에서 온다(가변 폭). 메트릭 테이블이 없는 페이스는 셀 폭만큼 전진한다. 조합된 음절은 자모 블록의
  음절 advance(또는 셀 폭)만큼 전진한다.
- 결합 마크는 0만큼 전진하며 앞선 글리프 위에 그려진다. 기본 술어는 U+0300..U+036F이다. 코어는 유니코드 테이블을 갖고 있지 않으므로
  더 많은 범위가 필요하면 자신의 `chain.is_mark`를 넘긴다.
- 잘못된 UTF-8은 절대 크래시하지 않으며 `len`을 넘어 읽지도 않는다. 잘못된 부분 시퀀스는 각각 어떤 페이스에 U+FFFD가 있으면 그것으로
  그려지고, 없으면 전진 없이 건너뛴다. NUL은 일반 코드 포인트이다(C 문자열이 아니라 `len`바이트가 그려진다).

### 7.3 그리기 전에 측정하기

`svf_measure_utf8(&chain, s, len, &e)`는 그리기와 정확히 같은 레이아웃 규칙을 써서 `e.width`, `e.ascent`, `e.descent`를 주며, 글리프를
읽지 않는다(그래서 비용이 적고 스트리밍 페이스는 I/O를 하지 않는다). 가운데 정렬, 오른쪽 정렬, 단어 줄바꿈, 그리고 그려 넣을 버퍼의
크기를 정할 때 쓴다. `e.width`는 펜 이동 거리이지 잉크의 범위가 아니다. 마지막 셀이 그 너머로(셀 폭까지) 닿을 수 있으므로 버퍼 크기를 정할 때
`svf_cell_w(face)`를 더하라(3절). 단어와 줄은 사용자의 몫이다. 라이브러리는 한 번에 한 줄을 그리며 줄바꿈에 대해서는 아무것도 모른다.

## 8. 타깃: 픽셀이 가는 곳

타깃은 그려진 각 픽셀의 커버리지를 사용자의 포맷으로 변환한다. 종류는 `svf_target_init`로 고른다.

    svf_err svf_target_init(svf_target *t, svf_target_kind kind, uint8_t *buf, size_t buf_len,
                            int16_t w, int16_t h, uint16_t stride);

| 그리는 대상 | 사용 | 비고 |
|---|---|---|
| 32비트 프레임버퍼 또는 SDL 서피스(메모리상 B, G, R, X. 리틀 엔디언에서는 dword `0x00RRGGBB`) | `SVF_T_XRGB8888` | `t.fg888`, `t.bg888`을 `0x00RRGGBB`로 설정 |
| 24비트 | `SVF_T_RGB888` | 같은 필드 |
| 16비트 컬러 LCD | `SVF_T_RGB565` / `SVF_T_RGB555` | `t.fg565`, `t.bg565`. 상위 바이트가 먼저이면 `t.flags`에 `SVF_TF_RGB16_BIGENDIAN`(옛 이름 `SVF_TF_565_BIGENDIAN`은 같은 비트이다) |
| 팔레트 모드(VGA 모드 13h, VBE 8 bpp, SDL CLUT8) | `SVF_T_INDEXED8` | `t.index_base`, `t.index_levels`가 팔레트 항목의 램프를 선택 |
| SSD1306 페이지 | `SVF_T_MONO_PAGE` | `buf[(y >> 3) * stride + x]`의 비트 `y & 7` |
| 1 bpp 비트맵 행 | `SVF_T_MONO_ROW` | MSB 우선 |
| 1/2/4/8비트 회색조 | `SVF_T_GRAY` | `t.gray_bits`. MSB 우선, 또는 `SVF_TF_GRAY_LSB_FIRST` |
| 픽셀당 커버리지 1바이트 | `SVF_T_GRAY8` | 직접 합성하는 마스크 |
| **그 밖의 모든 것** | `SVF_T_COVERAGE_CB` | 콜백이 `(x, y, coverage)`를 받음 |

각 종류가 기존 픽셀을 어떻게 다루는지는 정확하며 `svf.h`의 `svf_target` 위에 문서화되어 있다. 요약은 다음과 같다.

- 컬러 종류(`RGB565`, `RGB555`, `XRGB8888`, `RGB888`)는 **기존 픽셀을 읽지 않는다**. `bg`와 `fg`를 커버리지로 섞은 값을 쓰므로, `bg`는
  배경의 실제 색이어야 한다. 단색 배경에 그리거나, 임의의 내용 위에 섞으려면 콜백 종류를 쓰라.
- `GRAY8`, `INDEXED8`, `GRAY`는 기존 값과 새 값 중 최댓값을 유지한다. `INDEXED8`에서는 기존 인덱스가 잉크의 인덱스보다 낮은 곳에만 텍스트가
  보인다는 뜻이다. 배경 인덱스를 램프 `index_base + 1 .. index_base + index_levels`보다 아래에 두라.
- `MONO_*`는 커버리지가 `t.mono_threshold`(기본값 128) 이상일 때 비트를 설정하며 비트를 지우지 않는다.
- 클립 사각형(`t.clip_x0..clip_y1`, 반개구간, 기본값은 타깃 전체) 안의 픽셀만 쓰인다. 이웃 픽셀의 바이트나 행 패딩은 건드리지 않는다.

### 8.1 32비트 서피스 위의 컬러 텍스트

```c
svf_target t;
svf_target_init(&t, SVF_T_XRGB8888, surface_pixels, (size_t)pitch * height, width, height, (uint16_t)pitch);
t.fg888 = 0x00FFC000;      /* 호박색 텍스트 */
t.bg888 = 0x00000020;      /* 호출자가 아는 배경색 */
```

`stride`는 바이트 수를 나타내는 `uint16_t`이므로, 32비트 타깃의 폭은 최대 16,383픽셀이다. 픽셀의 **메모리 순서는 모든 호스트에서 B, G, R, X**이다.
네이티브 32비트 값 하나로 보았을 때 `0x00RRGGBB`인 것은 리틀 엔디언 기계(x86, ARM, RISC-V, WebAssembly)에서만이다. 빅 엔디언 호스트에서는 네 바이트를 직접
쓴다.

### 8.2 콜백 타깃: 만능 어댑터

픽셀 포맷이 위의 것들 중 어느 것도 아니거나, 기존 내용 위에 섞고 싶거나, 목적지가 다른 라이브러리의 서피스일 때는 콜백을 쓴다.
라이브러리는 클립 안에서 커버리지가 0보다 큰 각 픽셀마다 행 단위로 `plot(ctx, x, y, coverage)`를 한 번씩 호출하며, 버퍼는 관여하지
않는다. 이 예제는 이미 그림이 들어 있는 32비트 서피스 위에 흰 텍스트를 섞는다(`NEODG16A.SVF`에 대해 컴파일하고 실행했다. 픽셀을 리틀 엔디언 `uint32_t` 하나로 읽고 쓰며 B가 낮은 바이트이다. 메모리 순서 B, G, R, X와 일치한다).

```c
typedef struct { uint8_t *pix; int pitch; uint32_t fg; } Surf;      /* 사용자의 서피스 */

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	Surf *s = ctx;
	uint32_t *px = (uint32_t *)(s->pix + y * s->pitch) + x;
	uint32_t bg = *px, out = 0;
	for (int sh = 0; sh <= 16; sh += 8) {                       /* B, G, R */
		uint32_t b = (bg >> sh) & 255, f = (s->fg >> sh) & 255;
		out |= ((b * (255 - cov) + f * cov + 127) / 255) << sh;
	}
	*px = out;
}

Surf s = { pix, 64 * 4, 0x00FFFFFF };
svf_target t;
svf_target_init(&t, SVF_T_COVERAGE_CB, NULL, 0, 64, 24, 0);    /* w, h는 여전히 경계와 클립을 정의한다 */
t.plot = plot;
t.ctx = &s;
svf_draw_utf8(&chain, "가A", 4, 2, 16, &t, scratch, scratch_len);
```

`plot`은 그리기 전에 설정해야 한다(아니면 `SVF_E_ARG`). 두 셀이 한 픽셀에서 겹치는 곳(마크가 기본 글자 위에 얹힐 때)에서는 콜백이 셀마다
한 번씩 호출되므로, 섞는 콜백은 둘을 모두 합성하며, 이것이 원하는 동작이다.

## 9. 스케일링

`chain.scale_num`과 `chain.scale_den`을 설정한다(각각 1에서 16; 0과 0은 1/1을 뜻한다). 정수배(`2/1`, `3/1`)는 원본 픽셀을 각각 N x N 블록으로
그리므로 비트맵의 가장자리가 선명하게 유지된다. 다른 비율은 영역 평균을 내어 8비트 커버리지가 되므로, 1 bpp 페이스의 `3/2`는 가장자리
픽셀이 회색이 된다(이때는 컬러나 회색조 타깃을 쓰라. 모노 타깃에서는 임계값이 결정한다). 길이는 반올림(0.5는 올림, 대칭)으로
스케일되므로, 측정된 범위는 그려진 것과 같다. `x`, `y_baseline`, 클립은 항상 출력 픽셀 단위이다.

스크래치는 스케일링에 따라 커진다. 스케일된 줄에는 체인에서 가장 큰 페이스를 기준으로 **저장된 셀의 두 배에 스케일된 셀을 더한 만큼**이 필요하다.

    scratch = 2 * svf_cell_bytes(face) + ceil(cell_w * num / den) * ceil(cell_h * num / den)

스케일된 셀은 8비트 커버리지로 픽셀당 1바이트이다. 식은 매핑된 페이스와 스트리밍 페이스에서, 그리고 스트리밍 페이스에 블록 캐시가 있든 없든 같다(1/1에서는
셀 하나가 필요하고, 캐시 없는 스트리밍 페이스는 둘이다). `svf_chain_scratch_bytes`가 이를 계산한다. 스케일을 바꾼 뒤에는 항상 다시 계산하라. 16x16 1 bpp
`NEODG16A`(셀 32바이트)에서 측정한 값은, 3/2는 2 x 32 + 24 x 24 = 640바이트, 2/1은 2 x 32 + 32 x 32 = 1,088, 1/2는 2 x 32 + 8 x 8 = 128이다.

작은 MCU 빌드에서는 `-DSVF_NO_SCALE`이 스케일링을 완전히 제거한다(그러면 n/n 이외의 비율은 `SVF_E_ARG`이다). 빠른 스케일러의 스택 프레임은
약 610~680바이트이다. 2 KB RAM 칩에서 쓰기 전에 `svf.h`의 "Scaling"을 보라.

## 10. 한글: 자모 페이스와 음절 조합

**완성형** 페이스는 담당하는 음절마다 글리프 하나를 저장한다. **자모 세트(jamo-set)** 페이스(헤더 플래그 비트 1,
`svf_is_jamo(f)`)는 수백 개의 작은 조각과, 어떤 조각들이 각 음절을 이루는지 알려 주는 테이블을 저장한다. `svf_draw_utf8`는 조각들로부터
U+AC00..U+D7A3(그리고 호환 자모 U+3131..U+3163)을 즉석에서 조합한다. 두세 조각의 최대 커버리지이다. 특별히 할 일은 없다. 그냥 한글
텍스트를 그리면 된다. 한 가지 단서가 있다. 음절 테이블은 일부만 담을 수 있다. SPARSE(비트맵과 그 항목들) 또는 LIST(예외 최대 255개의 정렬된 목록)인
버전 3 JMAP 블록에 **폴백 블록이 없으면** 그 블록이 나열한 음절만 조합된다. 나머지는 `svf_has`가 0이고 누락 글리프(`missing_advance`)로 그려진다. 폴백
블록이 있으면 테이블에 없는 음절은 폴백으로 간다. 조밀한 JMAP과 버전 1, 2 블록은 11,172자 전부를 다룬다.

```c
if (svf_is_jamo(&face)) {
	uint16_t pieces[3];
	int n = svf_jamo_pieces(&face, 0xD55C /* 한 */, pieces);   /* 3: 초성, 중성, 종성 */
	for (int i = 0; i < n; i++)
		printf("piece %u\n", (unsigned)pieces[i]);               /* 글리프 U+F0000 + 번호 (페이스 안) */
}
uint8_t cell[64];                                      /* >= svf_cell_bytes(&face) */
svf_glyph(&face, 0xD55C, cell, sizeof cell);           /* 조합된 셀, MSB 우선, 행은 바이트 단위로 패딩 */
```

`svf_glyph`와 `svf_compose`는 타깃 없이 코드 포인트 하나의 셀을 반환한다. 자신의 아틀라스에 글리프를 캐시할 때 유용하다.

### 10.1 사용자의 빌드가 읽는 것

자모 블록은 버전 1, 2, 3(LIST 형식이 있는 JMAP)이 있다. 기본 데스크톱/DOS/WASM/SDL 빌드는 모두 읽는다(`-DSVF_SMALL`에서는 읽지 않는다. 12절). 작은 MCU 빌드는 더 적게 읽는다
([c/README.ko.md](../c/README.ko.md)의 표 "자모 세트: 각 빌드가 읽는 것" 참조). 빌드가 읽지 못하는 페이스도 상태 비트와 함께 **일반**
페이스로 열리며, 다만 한글을 조합하지 않는다. 자신의 애플리케이션용 페이스는 저장소의 도구와 같은 방식으로 빌드하고, 로드 시점에
`svf_status`를 확인하라.

### 10.2 조합된 음절 캐시

조합에는 음절마다 몇 번의 테이블 조회와 병합이 든다. 반복되는 텍스트(UI, 프레임마다 다시 그리는 대화 상자)에는 체인에 캐시를 준다.

```c
static uint8_t syl[4096];                       /* 슬롯은 (8 + 체인 페이스들 중 가장 큰 셀 바이트 수) 크기 */
svf_chain_cache(&chain, syl, sizeof syl);
```

캐시가 있든 없든 픽셀은 동일하다. 스트리밍 페이스에서 가장 효과가 크다. 캐시된 음절은 읽기를 전혀 일으키지 않는다. 스트리밍 16x16
페이스에서 "한글 ab"를 3/2로 처음 그릴 때 읽기 호출은 10번이었고, 캐시된 두 번째 그리기에서는 더 늘지 않았다(측정값). 캐시는 선형 조회를 쓰는
라운드 로빈 방식이다. 작은 타깃에는 수십 개의 슬롯이 알맞고, 수천 개는 맞지 않는다. `chain.faces`를 바꾸거나 페이스를 다시 연 뒤에는
`svf_chain_cache`를 다시 호출하라.

## 11. 메모리 예산

모든 메모리는 사용자의 것이다. 합산하라.

| 항목 | 크기 |
|---|---|
| `svf_face` | `sizeof(svf_face)`: `SVF_JMAP`이 있는 64비트 호스트에서 96바이트(없으면 80, MCU에서는 더 작음. 96이 상한) |
| `svf_chain`, `svf_target` | 각각 수십 바이트 |
| 스크래치 | `svf_chain_scratch_bytes(&chain)`: 셀 하나(`svf_cell_bytes`), 블록 캐시 없는 스트리밍 페이스는 그 두 배. 스케일링 시에는 **셀의 두 배에 스케일된 셀을 더한 만큼**(9절) |
| 스트리밍 페이스 | 테이블용 `svf_stream_tables_size(...)`, 선택적 캐시용 `slots * (block_size + 8)` |
| 음절 캐시 | `slots * (8 + 가장 큰 셀 바이트 수)` |
| 타깃 버퍼 | `rows * stride`(콜백 종류는 없음) |
| 매핑된 페이스 | 파일 자체, RAM 또는 플래시에(`const` 배열이나 PROGMEM 페이스는 RAM을 쓰지 않음, 5절) |
| 스택 | 스케일러 자신의 프레임: 기본 빠른 스케일러에서 AVR은 약 610바이트, Cortex-M0+는 680바이트 |

16x16 1 bpp 셀은 32바이트이고, 24x24 2 bpp 셀은 144바이트이다.

## 12. 컴파일 타임 스위치: 세 가지 레시피

스위치는 **모든** 소스에 주는 `-D` 플래그이다(2절). 데스크톱에서는 거의 필요하지 않다. 레시피를 고를 때 중요한 것들은 다음과 같다.

- **데스크톱, DOS, WASM, SDL, ScummVM급 애플리케이션: 스위치 없음.** 모든 것이 켜져 있다.
- **디스플레이 하나인 작은 MCU:** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_TARGETS=<one kind's bit> -DSVF_JSET_V2=0
  -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`를 쓰고, 맞는 프로필로 페이스를 쓴다(`tools/jamoset.py` `mcu-strict`. 배포되는 페이스는 이미 그 레이아웃이며 `c/bench/mkface.py --profile mcu-strict`는 오프셋을 줄인다. 5절). Arduino Uno 빌드가 정확히
  이것을 쓴다. [c/ports/arduino/README.ko.md](../c/ports/arduino/README.ko.md)를 보라.
- **어느 CPU에서든 가장 작은 코드:** `-DSVF_SMALL`은 속도 중심의 빠른 경로(워드 병합, GRAY8 테이블, 빠른 스케일러, 니블 popcount 테이블)를 끈다. 픽셀은 동일하며
  속도만 잃는다. **그리고 빌드가 읽는 것도 바꾼다.** `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG`의 *기본값*을 0으로 뒤집는다(`SVF_SMALL`이 없을
  때에만 기본값이 1이다. `gcc -dM -E`로 측정). 따라서 데스크톱, DOS, WASM의 `SVF_SMALL` 빌드는 버전 3(JMAP, LIST) 자모 블록이나 BIG 한계를 더는 읽지
  않는다. 그것을 필요로 하는 페이스는 `SVF_FACE_JSET_BAD`가 설정된(`SVF_FACE_JMAP_UNREAD`는 `-DSVF_JMAP_RECOG=1`일 때만) **일반 페이스**로 열리고 한글을 그리지 않는다. 필요하면
  `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`을 더하라(`SVF_JMAP_LIST`는 `SVF_JMAP`을 따른다).

툴체인별 기본값이 있는 전체 스위치 표는 [c/README.ko.md](../c/README.ko.md)의 "컴파일 시점 스위치"에 있고, 각 구성이 만드는 크기는
`c/cross/SIZES.md`에 있다.

## 13. 플랫폼

플랫폼마다 한 소절이다. 여기서 예제를 빌드한 툴체인과 버전, 빌드 방법, 자신의 프로젝트로 가져갈 것(파일과 플래그), `svf_target`과 플랫폼 픽셀 사이의
접착 코드, 측정한 메모리, 한계를 다룬다. 나머지는 `c/ports/<port>/` 아래 포트 README에 있다. 포트들은 여기서 빌드했고, Pico와 ESP32(컬러)는
에뮬레이터에서 실행했다. 실제 보드에서 실행한 것은 하나도 없다(각 README가 무엇을 확인했는지 적고 있다). Arduino 지침은 `arduino-cli`로 실행해 본 적이
없다. "측정"이라고 표시한 수치는 이 가이드를 위해 저장소의 깨끗한 `git archive`에서 빌드하여 출력한 값이다.

### 13.1 Arduino Uno와 그 밖의 Arduino 코어

- **툴체인.** avr-gcc 16.1.0과 AVR-LibC 2.3.2(`sh c/cross/install-toolchains.sh "$HOME/opt" avr`이 `~/opt` 아래에 설치하는 Zak Kemble 빌드), `-Os`.
  arduino-cli는 여기에 설치되어 있지 않으므로 아래 명령은 표준 AVR 코어에 대해 실행해 보지 않았다. 같은 소스에 대해
  `c/cross/build-all.sh --ports`가 쓰는 설정이며, 이것은 `c/ports/arduino/stub/`에 대해 컴파일하고 링크한다. 사용하는 코어의 avr-gcc 버전을
  기록해 두라. 라이브러리는 C99이며 그 이상을 요구하지 않는다.
- **빌드**(저장소 루트에서. 라이브러리는 Arduino 라이브러리로 들어가고, 생성된 `face.c`는 스케치 폴더에 들어가며 커밋하지 않는다).

      mkdir -p ~/Arduino/libraries/svf && cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
      python3 c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
      F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
      arduino-cli compile -b arduino:avr:uno c/ports/arduino \
          --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"

- **자신의 스케치에서.** `svf.h`, `svf_internal.h`, `svf_*.c`를 라이브러리 폴더로 복사하고, 생성한 `face.c`를 `.ino` 옆에 두며, 5.3절처럼
  `extern "C"`로 선언하고, C와 C++ 컴파일에 위의 플래그를 준다. 플래그는 `compiler.c.extra_flags`와 `compiler.cpp.extra_flags`에 넣고,
  `build.extra_flags`에는 **넣지 않는다**. AVR 코어는 `build.extra_flags`를 어셈블러 소스에도 넘기는데, `-include avr/pgmspace.h`는 거기서
  실패한다. `-DSVF_JSET_V2=0`은 버전 1 리더만 빌드한다(NEODG16G는 버전 1 페이스이며 버전 2 리더는 약 2.4 KB가 든다). `-DSVF_TARGETS=0x02`는
  `MONO_PAGE`만 컴파일하고, `-DSVF_NO_STREAM`은 스트림 리더를 뺀다. `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`는 레이아웃 단위를 상수로 만든다.
- **픽셀 접착 코드.** 128 x 64 SSD1306 페이지 버퍼는 1,024바이트이다. 타깃은 컨트롤러의 레이아웃에 그대로 쓰며, `Wire`가 16바이트씩 보낸다(버퍼가
  32바이트이다).

  ```cpp
  static uint8_t page[128 * 64 / 8];
  svf_target_init(&t, SVF_T_MONO_PAGE, page, sizeof page, 128, 64, 128);      /* stride: 페이지당 바이트 */
  /* ... svf_draw_utf8(...) ..., 그다음 16바이트마다: */
  Wire.beginTransmission(0x3C); Wire.write(0x40); Wire.write(page + i, 16); Wire.endTransmission();
  ```

  `PROGMEM`에 둔 텍스트는 그리기 전에 RAM으로 복사한다(`strncpy_P(text, lines[i], sizeof text - 1)`). 라이브러리는 문자열을 일반 로드로 읽는다.
- **메모리(측정, ATmega328P).** `c/cross/build-all.sh --ports`: 32,256바이트 중 플래시 23,694바이트(text 23,676 + data 18), 페이스는 10,124바이트이다.
  스택 이전 RAM은 1,103바이트이며 그중 페이지 버퍼가 1,024바이트이다. 실제 `Wire`는 버퍼로 약 200바이트를, 코어는 수십 바이트를 더하므로 스택에는 약
  700바이트가 남는다.
- **한계.** 스케일링은 꺼져 있다(`-DSVF_NO_SCALE`). 스케일된 그리기는 1 KB 페이지 버퍼 옆에서 스택이 약 864바이트 필요하므로, 꼭 해야 한다면
  `-DSVF_SCALE_FAST=0`으로 빌드한다(451바이트, 정적으로 측정). 버전 2 리더가 없으면 버전 2 페이스는 일반 페이스로 열린다. 버전 3 페이스는 **일반 페이스**로
  열린다(`SVF_FACE_JSET_BAD`. AVR에서는 `SVF_JMAP`과 `SVF_JMAP_RECOG`가 0이다). 블록을 인식하여(`JMAP_UNREAD`) 그것이 담은 버전 1 폴백 JSET을 읽게 하려면
  `-DSVF_JMAP_RECOG=1`을 더한다(`svf.h`와 `c/README.md`에서. 여기서 빌드하지는 않았다). 스트리밍은 들어가지 않는다. 테이블만 5,129바이트이다. **Arduino Mega 2560**: 같은 스케치가 ATmega2560용으로도
  링크된다(플래시 23,820바이트). 그러나 플래시 64 KB 위의 페이스와 데이터는 far 읽기(`pgm_read_byte_far`)가 필요한데 라이브러리는 이를 하지
  않는다. 지원하지 않으며 테스트하지 않았다(Mega 이미지의 플래시 끝이 65,536에 닿으면 빌드가 `FLAG` 줄을 출력한다). **그 밖의 코어**(Arduino
  IDE의 SAMD, RP2040, ESP32): 플래시가 메모리에 매핑되어 있으므로 라이브러리를 `SVF_RD8` 재정의와 `PROGMEM` 없이 평범한 C로 빌드한다.
  `mkface.py`는 거기서 이미 일반 `const` 배열을 낸다. 여기서는 시도하지 않았다. 세부 내용은
  [c/ports/arduino/README.ko.md](../c/ports/arduino/README.ko.md)에 있다.

### 13.2 WCH CH582(RISC-V, 베어메탈)

- **툴체인.** `riscv32-esp-elf-gcc` 16.1.0(crosstool-NG esp-16.1.0_20260609, `sh c/cross/install-toolchains.sh "$HOME/opt" esp`), 이 포트가 CH582M에
  쓰는 WCH CH583 EVT 소스(github.com/openwch/ch583의 커밋 `bd508ad`), 플래시용 `wchisp` 0.3.0이다. xPack `riscv-none-elf-gcc` 15.2.0-1은 대안으로
  문서화되어 있으나(`CROSS=riscv-none-elf-`) 여기에 설치되어 있지 않다.
- **빌드와 플래시**(24 MHz. Type-C 케이블을 꽂는 동안 보드의 BOOT 버튼을 누른다).

      sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
      make -C c/ports/ch582            # build/svf_ch582_mono.{elf,bin,hex,map}, build/licences/
      make -C c/ports/ch582 flash

- **자신의 프로젝트에서.** `c/src/*.c`와 생성한 `face.c`를
  `-march=rv32imac_zicsr_zifencei -mabi=ilp32 -mcmodel=medany -msmall-data-limit=8 -mstrict-align -Os -std=c99` 및
  `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0`으로 컴파일한다(Uno와 같은 스위치이다. 매핑된
  페이스, 레이아웃 하나, `MONO_PAGE`, 버전 1 리더). WCH 스타트업 코드, SDK 소스(`CH58x_gpio.c`, `CH58x_i2c.c`, `CH58x_sys.c`), `link.ld`는 EVT
  트리에서 온다. 그 플래그(`-DINT_SOFT -w`, 포트 자체 파일의 `-std=gnu99`)는 포트의 Makefile을 보라. 페이스는 CodeFlash의 `const` 배열이다.
- **픽셀 접착 코드.** 패널은 하드웨어 I2C(PB20 SDA, PB21 SCL, 주소 0x3C)에 연결된 128 x 64 SH1106이며, 포트의
  `display_show(const uint8_t *buf, int16_t y, int16_t rows)`가 `int ch582_i2c_write(uint8_t addr, const uint8_t *buf, size_t n)`(성공이면 0,
  타임아웃이나 NACK이면 -1이며 `CH582_I2C_SPIN`으로 한정)를 통해 구동한다. 프레임은 13.1절과 같은 1,024바이트 `MONO_PAGE` 버퍼이다.
  `svf_target_init(&t, SVF_T_MONO_PAGE, frame, sizeof frame, 128, 64, 128)`.
- **메모리(측정).** `.bin` 21,068바이트. text 22,456(페이스 10,124), data 20, bss 1,232, `.highcode` 2,576(RAM에 산다). 사용 RAM은 32,768 중
  5,876이며 스택은 2,048바이트이고, `main`의 스택 최고치는 640이다.
- **한계.** 이미지는 24 MHz로 돈다(I2C 모듈 클럭은 2..36 MHz여야 한다). Makefile의 `FREQ_SYS`는 `SetSysClock`과 일치해야 한다. **패널에서
  아직 테스트하지 않았다.** 핀 매핑, 패널 변종(SH1106 또는 진짜 SSD1306, 열 오프셋), LED 결과 코드는 README에 있다. 세부 내용은
  [c/ports/ch582/README.ko.md](../c/ports/ch582/README.ko.md)에 있다.

### 13.3 DOS(DJGPP)

- **툴체인.** `~/opt/djgpp`의 DJGPP `i586-pc-msdosdjgpp-gcc` 12.2.0과 binutils 2.30(build-djgpp v3.4). 실행에는 DOSBox-X 2026.08.31을 쓴다. 프로그램은
  32비트 보호 모드 `.EXE`이며 DPMI 호스트가 필요하다. 실제 DOS에서는 **`CWSDPMI.EXE`**가 프로그램의 디렉터리나 `PATH`에 있어야 한다(DOSBox-X에는 내장되어
  있다).
- **빌드**(측정: `SVFDEMO.EXE` 266,265바이트, `SVFVESA.EXE` 294,345바이트).

      DJ=~/opt/djgpp/bin/i586-pc-msdosdjgpp
      $DJ-gcc -std=gnu99 -O2 -Ic/include c/ports/dos/svfdemo.c c/src/*.c -o SVFDEMO.EXE
      $DJ-gcc -std=gnu99 -O2 -Ic/include -Ic/ports/dos c/ports/dos/svfvesa.c c/ports/dos/vbe_select.c \
          c/ports/dos/vesa_lines.c c/src/*.c -o SVFVESA.EXE

- **자신의 프로젝트에서.** `c/src/*.c`와 `-I c/include`, 스위치는 없다. `__DJGPP__`가 전체 기본값(모든 타깃 종류, 스트리밍, 스케일링, JMAP, BIG)을
  고른다. `-std=c99`가 아니라 `-std=gnu99`를 쓴다. 엄격한 `-std=c99`에서는 DJGPP 헤더가 `lseek` 같은 POSIX 이름을 숨긴다(측정: 암시적 선언 경고).
  **8.3 이름:** 긴 파일 이름이 없는 DOS에서는 페이스 파일이 대문자 8.3 이름이어야 하며(`NEODG16A.SVF`. `svf/dos`의 모든 페이스가 이미 그렇다),
  `vesa-lines.txt` 같은 데이터 파일은 `VESALINE.TXT`로 복사해야 한다. 파일은 **`O_BINARY`**로 연다(DJGPP의 기본은 텍스트 모드이다).
- **스트리밍인가 매핑인가.** `svfdemo.c`는 두 페이스를 스트리밍한다(`svf_open_stream`, `lseek` + `read`를 쓰는 `read_file` 콜백, 블록 캐시의 1 KB 블록.
  PAPLG16은 16슬롯, PAPLG18은 64슬롯). 그래서 1 MB 페이스가 1 MB의 RAM을 요구하지 않는다. 매핑하려면 파일을 통째로 읽어 제자리에서 연다(DJGPP 12.2.0으로
  컴파일함).

  ```c
  /* dos_mapped.c - DJGPP: 파일을 통째로 메모리에 읽어 매핑 방식으로 연 페이스. */
  #include <fcntl.h>
  #include <stdlib.h>
  #include <unistd.h>
  #include "svf.h"

  svf_err load_face(svf_face *f, const char *path)       /* path: NEODG16A.SVF 같은 8.3 이름 */
  {
  	int fd = open(path, O_RDONLY | O_BINARY);           /* O_BINARY: DJGPP는 기본이 텍스트 모드 */
  	off_t len;
  	uint8_t *bytes;

  	if (fd < 0)
  		return SVF_E_IO;
  	len = lseek(fd, 0, SEEK_END);
  	lseek(fd, 0, SEEK_SET);
  	bytes = len > 0 ? malloc((size_t)len) : NULL;       /* 보관하라: 그리는 동안 페이스가 제자리에서 읽는다 */
  	if (!bytes || read(fd, bytes, (size_t)len) != len) {
  		free(bytes);
  		close(fd);
  		return SVF_E_IO;
  	}
  	close(fd);
  	return svf_open_mapped(f, bytes, (size_t)len);
  }
  ```

- **픽셀 접착 코드.** 모드 13h: 320 x 200 `GRAY8` 버퍼에 그리고, 팔레트를 회색 램프로 설정하여 커버리지 바이트가 곧 자신의 색 인덱스가 되게 하며
  (`outportb(0x3C8, 0)` 다음에 항목마다 `outportb(0x3C9, i >> 2)` 세 번), `__dpmi_int(0x10, &regs)`로 모드를 설정하고(`regs.x.ax = 0x13`.
  `0x03`이면 텍스트 모드로 복귀), `dosmemput(screen, sizeof screen, 0xA0000)`으로 버퍼를 복사한다. VBE 2.0 선형 프레임버퍼 모드(8, 15, 16, 24, 32비트)에는
  `svfvesa.c`를 쓴다. 패킹된 타깃 종류를 쓰고, 모드는 번호가 아니라 기하와 채널 배치로 고르며, 행은 `movedata`로 복사한다.
- **메모리.** `svfdemo.c`: 테이블 4,096 + 32,768바이트, 캐시 16 x 1,032 + 64 x 1,032바이트, 스크래치 180, 64,000바이트 화면 버퍼. 캐시 슬롯은 한 줄이
  건드리는 블록들을 모두 담아야 한다. 그렇지 않으면 같은 블록을 계속 다시 읽는다.
- **한계.** 매핑된 페이스는 DJGPP의 보호 모드 힙에 `malloc`한 것이며 기계의 확장 메모리로 제한된다. 큰 페이스는 스트리밍하라. 헤드리스 실행과 정확한 픽셀
  검사는 [c/ports/dos/README.ko.md](../c/ports/dos/README.ko.md)에 있다.

### 13.4 ESP32(ESP-IDF)

- **툴체인.** ESP-IDF **v5.5.6**(여기서 빌드한 버전이며 `~/opt/esp-idf-v5.5.6`에 있다. `. $IDF_PATH/export.sh`로 환경을 내보내거나 `-DIDF_PATH=`를 준다)과 그것이
  설치하는 툴체인이다. 포트는 **ESP32-C3**(RISC-V)와 **ESP32-S3**(Xtensa)를 다룬다. 원래의 ESP32는 크기 행(`xtensa-esp32-elf-gcc` 16.1.0)은 있지만 포트
  이미지는 없다(플래시 핀과 흔한 보드의 배선이 포트의 핀 표와 다르다).
- **빌드**(프로필과 칩마다 빌드 디렉터리 하나. `main/CMakeLists.txt`가 `mkface.py`로 페이스 배열을 생성한다).

      cd c/ports/esp32
      idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3 && idf.py -B build-colour build flash monitor
      idf.py -B build-grey   -DSVF_PROFILE=grey   set-target esp32s3 && idf.py -B build-grey build
      idf.py -B build-mono   -DSVF_PROFILE=mono   set-target esp32c3 && idf.py -B build-mono build

  `idf.py`는 `sdkconfig`와 `sdkconfig.old`를 프로젝트 디렉터리에 쓴다(`c/ports/esp32/.gitignore`에 올라 있다).
- **자신의 프로젝트에서.** 라이브러리를 컴포넌트로 만든다. `svf.h`, `svf_internal.h`, `svf_*.c`를 `main/svf/`로 복사하고 `face.c`를 생성한다.

  ```cmake
  # main/CMakeLists.txt
  file(GLOB SVF_SRCS svf/*.c)
  idf_component_register(SRCS main.c esp_faces.c face.c ${SVF_SRCS} INCLUDE_DIRS svf REQUIRES esp_partition spiffs)
  target_compile_definitions(${COMPONENT_LIB} PRIVATE SVF_NO_SCALE SVF_TARGETS=0x08)   # 종류 하나: 여기서는 RGB565
  ```

  `svf.h`를 include하는 모든 소스는 같은 `-D` 스위치를 보아야 한다(2절). 컴포넌트에 `target_compile_definitions`를 주면 그렇게 된다. 이 컴포넌트
  형태는 여기서 ESP-IDF v5.5.6으로 ESP32-S3용으로 빌드했다.
- **페이스.** 플래시의 `const` 배열은 다른 것이 필요 없다. 자신의 데이터 파티션에 둔 페이스는 RAM 사본 없이 메모리 매핑된다. SPIFFS의 페이스는 stdio를
  통해 스트리밍된다(테이블과 블록 캐시가 RAM에 있다). 둘 다 ESP-IDF v5.5.6으로 컴파일된다(`esp_faces.c`. 여기서 ESP32-S3용 컴포넌트로 빌드했다).

  ```c
  /* esp_faces.c - ESP-IDF: (a) 자신의 플래시 파티션에 둔 페이스, 메모리 매핑(RAM 사본 없음);
   * (b) SPIFFS의 페이스 파일, stdio로 스트리밍(테이블 + 블록 캐시는 RAM). */
  #include <stdio.h>
  #include "esp_partition.h"
  #include "esp_spiffs.h"
  #include "svf.h"

  /* (a) partitions.csv:  font, data, 0x40, , 256K   그다음: parttool.py write_partition --partition-name font --input FACE.SVF */
  static esp_partition_mmap_handle_t font_map;

  /* face_len: 페이스의 바이트 크기(예: 기록할 때 저장해 둔 값). p->size를 넘겨도 된다. 0xFF로 채워진 뒤쪽 영역도 status 0으로 열린다 */
  svf_err face_from_partition(svf_face *f, uint32_t face_len)
  {
  	const esp_partition_t *p = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x40, "font");
  	const void *ptr;
  	if (!p || face_len > p->size)
  		return SVF_E_IO;
  	if (esp_partition_mmap(p, 0, p->size, ESP_PARTITION_MMAP_DATA, &ptr, &font_map) != ESP_OK)
  		return SVF_E_IO;
  	return svf_open_mapped(f, (const uint8_t *)ptr, face_len);   /* 페이스의 수명 동안 매핑을 유지하라 */
  }

  /* (b) SPIFFS에서 스트리밍: 시작할 때 한 번 마운트하고, 그다음 페이스를 연다 */
  static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
  {
  	FILE *fp = ctx;
  	return fseek(fp, (long)off, SEEK_SET) == 0 ? (long)fread(dst, 1, len, fp) : -1;
  }
  static uint8_t tables[16 * 1024], cache[8 * (512 + 8)];   /* 한 번에 페이스 하나 */

  esp_err_t spiffs_mount(void)                                /* 한 번만 호출한다 */
  {
  	esp_vfs_spiffs_conf_t conf = {.base_path = "/spiffs", .partition_label = NULL, .max_files = 2,
  	                              .format_if_mount_failed = false};
  	return esp_vfs_spiffs_register(&conf);
  }

  svf_err face_from_spiffs(svf_face *f, const char *path)
  {
  	FILE *fp = fopen(path, "rb");
  	long len;
  	size_t need;
  	svf_err e;

  	if (!fp)
  		return SVF_E_IO;
  	if (fseek(fp, 0, SEEK_END) != 0 || (len = ftell(fp)) <= 0) {
  		fclose(fp);
  		return SVF_E_IO;
  	}
  	need = svf_stream_tables_size(rd, fp, (uint32_t)len, &e);
  	if (!need) {
  		fclose(fp);
  		return e;
  	}
  	if (need > sizeof tables) {
  		fclose(fp);
  		return SVF_E_NOMEM;
  	}
  	e = svf_open_stream(f, rd, fp, (uint32_t)len, tables, sizeof tables, cache, sizeof cache, 512);
  	if (e != SVF_OK)
  		fclose(fp);                                          /* 성공하면 fp를 열어 둔다: 그리는 동안 페이스가 읽는다 */
  	return e;
  }
  ```

  페이스를 그리는 동안은 매핑을 유지하라. `esp_partition_munmap(font_map)`이 이를 해제한다.
- **픽셀 접착 코드.** 포트는 컬러 밴드(320 x 24 `RGB565`, 15,360바이트)를 그리고
  `spi_device_polling_transmit(spi_device_handle_t, spi_transaction_t *)`로 보낸다(SPI2의 ILI9341). ILI9341은 상위 바이트가 먼저이므로
  `t.flags = SVF_TF_RGB16_BIGENDIAN`을 설정한다(옛 이름 `SVF_TF_565_BIGENDIAN`도 같은 비트이다). QEMU RGB 패널은 네이티브 워드를 받는다(플래그 0).
  프로필이 그려 넣는 경계는 포트의 `display_show(const uint8_t *buf, int16_t y, int16_t rows)`이다.
- **메모리(측정, ESP-IDF v5.5.6, Release).** ESP32-C3 컬러 프로필의 `.bin`은 294,960바이트(페이스 74,660), ESP32-S3 grey는 317,856, ESP32-C3 mono는
  229,648(페이스 10,124)이며, 모두 기본 1 MB 애플리케이션 파티션에 들어간다(여유 72 %, 70 %, 78 %). `idf.py size`, C3 컬러: 플래시 코드 109,930, `.rodata`
  117,180, DRAM `.bss` 19,320과 `.data` 6,920. mono: `.bss` 4,920.
- **한계.** 여기서는 ESP32 보드에서 실행한 것이 없다(`esp_rgb` 패널은 QEMU 9.2.2에서 실행했다). 배선, `MADCTL`, 패널 변종은 README에 있다. 세부 내용은
  [c/ports/esp32/README.ko.md](../c/ports/esp32/README.ko.md)에 있다.

### 13.5 Raspberry Pi Pico와 Pico 2(pico-sdk)

- **툴체인.** pico-sdk **2.3.1**, arm-none-eabi-gcc 15.2.1(Arm GNU Toolchain 15.2.Rel1), CMake, 페이스 배열용 Python 3이며, `.uf2`를 만드는 데에는 picotool 2.3.1을
  쓴다(포트 README 참조).
- **빌드.** 프로필마다 디렉터리 하나이다. `-DPICO_NO_PICOTOOL=1`은 `.elf`만 만든다. **Pico 2**(RP2350, Arm 코어)에는 `-DPICO_BOARD=pico2`를 더한다.

      cmake -S c/ports/pico -B build-pico-mono  -DSVF_PROFILE=mono -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
      cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
      cmake --build build-pico-mono

- **자신의 프로젝트에서.** 포트의 `CMakeLists.txt`가 템플릿이다. `mkface.py`를 실행하는 `add_custom_command`로 페이스를 생성하고, `c/src/*.c`를 더하고,
  `pico_stdlib`와 버스 라이브러리를 링크하며, 타깃에 스위치를 정의한다(이 형태는 여기서 Pico용으로, 그리고 `-DPICO_BOARD=pico2`로 Pico 2용으로 빌드했다.
  RGB565 밴드에 그리는 `main.c`로 text가 각각 33,988과 32,340바이트였다).

  ```cmake
  file(GLOB SVF_SRCS svf/c/src/*.c)
  add_executable(app main.c face.c ${SVF_SRCS})
  target_include_directories(app PRIVATE svf/c/include)
  target_compile_definitions(app PRIVATE SVF_NO_SCALE SVF_TARGETS=0x08)      # RGB565만
  target_link_libraries(app pico_stdlib hardware_spi)
  ```

- **픽셀 접착 코드.** I2C 패널: `i2c_write_blocking(i2c0, addr, buf, len, false)`(GP4/GP5의 SSD1306 mono, 주소 0x3C). SPI 컬러:
  `spi_write_blocking(spi0, buf, len)`(GP16..GP20의 ST7789). ST7789는 RGB565를 상위 바이트 먼저 받으므로 `t.flags = SVF_TF_RGB16_BIGENDIAN`이다.
  포트는 컬러 프로필을 24행 밴드(240 x 24 x 2 = 11,520바이트)로 그리고 `display_show(band, y, 24)`를 호출한다.
- **메모리(측정, `arm-none-eabi-size`, Release, 페이스 포함).**

  | 이미지 | Pico(RP2040) text / bss | Pico 2(RP2350) text / bss |
  |---|---|---|
  | mono(NEODG16G, 10,124) | 35,484 / 2,384 | 33,636 / 2,000 |
  | grey(PAPLG16 + PAPLG18, 74,660) | 99,256 / 17,936 | 97,420 / 17,552 |
  | colour(PAPLG16 + PAPLG18) | 99,828 / 12,812 | 98,176 / 12,428 |

  Pico 열은 `c/cross/SIZES.md`의 "Pico SDK images" 표와 같다.
- **한계.** 페이스는 플래시에서 **XIP 캐시**(RP2040은 16 KB)를 거쳐 읽힌다. 여기서 쓴 에뮬레이터(rp2040js, 벤치)는 이를 모델링하지 않으므로, 실제 그리기 시간은
  에뮬레이션 값이거나 그보다 느리며 그 차이는 여기서 측정한 것이 없다. 하드웨어에서는 실행한 적이 없다. Pico 2는 빌드만 했고 실행하지 않았다. 세부 내용은
  [c/ports/pico/README.ko.md](../c/ports/pico/README.ko.md)에 있다.

### 13.6 SDL2와 SDL3

- **툴체인.** 호스트 gcc 13.3.0. SDL 2.30.0 이상(`libsdl2-dev`) 또는 SDL3(사용자의 포크에서 가져온 3.5.0-dev, `~/opt/sdl3`. `pkg-config sdl3`가 찾는 SDL3이면 어느 것이든
  예제를 빌드한다). `c/ports/sdl/svfsdl.c`는 둘 모두를 위한 한 소스이며(`sdl_compat.h`) 타깃 종류가 맞는 모든 SDL 픽셀 포맷을 다룬다.
- **최소 샘플**(SDL3. 디스크에서 매핑한 페이스, `XRGB8888` 서피스에 2/1 스케일로 그린 한 줄, BMP로 저장). SDL 3.5.0-dev로 `SDL_VIDEODRIVER=dummy`에서 빌드하고 실행했다.

  ```c
  /* sdl_min.c - SDL3: 디스크에서 매핑한 페이스 파일, XRGB8888 서피스에 그린 한 줄, BMP로 저장. */
  #include <SDL3/SDL.h>
  #include <string.h>
  #include "svf.h"

  int main(int argc, char **argv)
  {
  	size_t len;
  	void *bytes = SDL_LoadFile(argc > 1 ? argv[1] : "NEODG16A.SVF", &len);   /* 페이스를 쓰는 동안 보관하라 */
  	static svf_face face;
  	svf_face *faces[1] = {&face};
  	svf_chain chain = {0};
  	svf_target t;
  	uint8_t scratch[2048];                               /* 16x16의 2/1: 2*32 + 32*32 = 1,088 */
  	const char *s = "SDL 한글 렌더링";

  	if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK)
  		return 1;
  	chain.faces = faces;
  	chain.count = 1;
  	chain.scale_num = 2;                                   /* 2/1: 선명한 두 배 크기 */
  	chain.scale_den = 1;
  	if (svf_chain_scratch_bytes(&chain) > sizeof scratch)
  		return 1;
  	SDL_Surface *surf = SDL_CreateSurface(320, 48, SDL_PIXELFORMAT_XRGB8888); /* 리틀 엔디언에서 메모리 순서 B G R X */
  	if (!surf || !SDL_FillSurfaceRect(surf, NULL, SDL_MapSurfaceRGB(surf, 0, 0, 0x20)) || !SDL_LockSurface(surf))
  		return 1;
  	if (svf_target_init(&t, SVF_T_XRGB8888, surf->pixels, (size_t)surf->pitch * surf->h, (int16_t)surf->w,
  	                    (int16_t)surf->h, (uint16_t)surf->pitch) != SVF_OK)
  		return 1;
  	t.fg888 = 0x00FFC000;
  	t.bg888 = 0x00000020;                                  /* 서피스를 채운 색 */
  	svf_err e = svf_draw_utf8(&chain, s, strlen(s), 4, (int16_t)(4 + 2 * svf_ascent(&face)), &t, scratch, sizeof scratch);
  	SDL_UnlockSurface(surf);
  	SDL_SaveBMP(surf, "out.bmp");
  	SDL_DestroySurface(surf);
  	SDL_free(bytes);
  	return e == SVF_OK ? 0 : 1;
  }
  ```

      export PKG_CONFIG_PATH=~/opt/sdl3/lib/pkgconfig
      cc -std=c99 -Wall -Wextra -I c/include sdl_min.c c/src/*.c $(pkg-config --cflags --libs sdl3) \
          -Wl,-rpath,$(pkg-config --variable=libdir sdl3) -o sdl_min
      SDL_VIDEODRIVER=dummy ./sdl_min svf/dos/NEODG16A.SVF

- **전체 예제.** `make -C c/ports/sdl SDL=2` 또는 `SDL=3`이 `svfsdl2` / `svfsdl3`(`c/build/ports/sdl/`)을 빌드한다. `sh c/ports/sdl/check.sh`는 두 SDL에서 모든
  포맷에 대해 서피스 바이트를 `tools/svfline.py`와 대조하여 증명한다(증거는 스크린샷이 아니라 덤프이다).
- **픽셀 접착 코드.** `stride`는 서피스의 `pitch`이며(SDL은 행을 4바이트로 올림한다) 그리는 동안 서피스는 잠겨 있어야 한다(`SDL_LockSurface`). 먼저 지워 두라(라이브러리는
  패딩을 절대 쓰지 않으며, 회색조와 인덱스 종류는 기존 값과 새 값 중 최댓값을 유지한다). 포맷은 **메모리 순서**로 이름 짓는다. `SDL_PIXELFORMAT_BGRX32`가
  `SVF_T_XRGB8888`이다(모든 호스트에서 메모리상 B, G, R, X. 네이티브 `uint32_t` 하나로 보면 `0x00RRGGBB`인 것은 리틀 엔디언에서만이다). `SDL_PIXELFORMAT_RGB24`에는 맞는 종류가
  없다. 16비트 종류는 호스트를 따른다. `SDL_BYTEORDER`가 빅 엔디언이면 `SVF_TF_RGB16_BIGENDIAN`을 더한다.
- **한계.** 32비트 타깃의 폭은 최대 16,383픽셀이다(`uint16_t` stride). 리틀 엔디언에서만 실행했다. SDL2와 SDL3는 화면 표시를 위해 RGB565를 넓히는 방식이 다를 뿐, 라이브러리가 쓰는
  바이트는 다르지 않다. 세부 내용은 [c/ports/sdl/README.ko.md](../c/ports/sdl/README.ko.md)에 있다.

### 13.7 웹(WebAssembly, emscripten)

- **툴체인.** emsdk 태그 **6.0.13**(emcc 6.0.13, `sh c/cross/install-toolchains.sh "$HOME/opt" emsdk`가 node 24.19.0과 함께 설치), `-O2`, `-std=c99 -Wall -Wextra -Werror`.
- **빌드**(`web/build.sh`가 실행하는 줄이며 `c/ports/web/emcc-flags.sh`에 있다. 측정: `svf.wasm` 39,808바이트, `svf.js` 6,937).

      EM_CONFIG=~/opt/emsdk/.emscripten ~/opt/emsdk/upstream/emscripten/emcc -std=c99 -Wall -Wextra -Werror -O2 \
          -Ic/include c/ports/web/svf_web.c c/src/*.c -o svf.js -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule \
          -sENVIRONMENT=web,node -sEXPORTED_FUNCTIONS=_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP16,HEAP32 \
          -sALLOW_MEMORY_GROWTH

  `web/build.sh [OUT]`는 이를 실행하고 피커 페이지용으로 `faces.json`을 쓰고 페이스와 라이선스를 복사한다.
- **자신의 프로젝트에서.** `c/ports/web/svf_web.c`를 `c/src/*.c`와 함께 컴파일하고 그 export들(`svfw_open(slot, data, len)`,
  `svfw_target2(kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags)`, `svfw_scale`, `svfw_measure(text, len, out)`,
  `svfw_draw(text, len, x, baseline)`, `svfw_reset`, ... 목록은 [c/ports/web/README.ko.md](../c/ports/web/README.ko.md)에 있다)을 유지하거나, C API 위에 자신의
  `EMSCRIPTEN_KEEPALIVE` 접착 코드를 쓴다. 스위치는 없다. `__EMSCRIPTEN__`이 전체 기본값을 고른다.
- **픽셀 접착 코드.** 타깃 버퍼(모듈 메모리의 뷰)와 페이스 바이트는 JavaScript가 소유하고, C 쪽이 거기에 그린다. 접착 코드가 노출하는 종류는 `GRAY8`,
  `MONO_PAGE`, `MONO_ROW`, `RGB565`(플래그 0 또는 `SVF_TF_RGB16_BIGENDIAN`. 옛 이름은 `SVF_TF_565_BIGENDIAN`)이다. 버퍼를 `<canvas>`의 `ImageData`로 복사하는 일은
  직접 한다.
- **메모리.** `svfw_draw`에는 `svf_chain_scratch_bytes`가 필요하다. 처음에는 정적 64 KB이고, 그다음에는 필요한 만큼만 `malloc`한다(큰 스케일된 셀, 예컨대 16/1의
  GBATB47은 637 KB가 필요하다). 할당하는 코드는 이 포트뿐이며 `c/src`는 절대 할당하지 않는다.
- **한계.** 페이스 바이트는 슬롯이 쓰는 동안 모듈의 메모리에 있어야 한다. 해제하기 전에 `svfw_reset`을 호출하라. 체인에는 페이스가 최대 네 개이다.
  `-sALLOW_MEMORY_GROWTH`는 힙을 옮긴다. 커질 수 있는 호출 뒤에는 `HEAPU8` 뷰를 다시 가져오라.

## 14. 자체 텍스트 경로가 있는 애플리케이션에 통합하기

대부분의 애플리케이션에는 이미 "이 문자열을 x, y에 이 색으로 그려라"라는 루틴과 "이 문자열의 폭은 얼마인가"라는 루틴이 있다. 렌더러는 둘 다에
대응된다.

| 애플리케이션이 필요로 하는 것 | 라이브러리 호출 |
|---|---|
| 시작할 때 폰트 열기 | `svf_open_mapped`(메모리에 로드된 페이스) 또는 `svf_open_stream`(큰 페이스, 적은 RAM) |
| 문자열의 폭과 높이 | `svf_measure_utf8`(`width`는 잉크가 아니라 펜 이동 거리. 높이 = `ascent + descent`, 또는 페이스의 `cell_h`) |
| 문자열 그리기 | 타깃으로 `svf_draw_utf8` |
| 애플리케이션 자체 서피스에 그리기 | `ctx`에 서피스를 넣은 `SVF_T_COVERAGE_CB`(8.2절), 또는 그 픽셀 포맷에 맞는 타깃 종류 |
| 같은 문자열을 매 프레임 그리기 | 음절 캐시(10.2절), 그리고 렌더링된 문자열 비트맵을 직접 캐시 |
| 자체 레이아웃을 위한 글리프별 advance | `svf_metrics_of`, 또는 문자 하나에 대한 `svf_measure_utf8` |

번번이 문제를 일으키는 점들은 다음과 같다.

1. **텍스트 인코딩.** 라이브러리는 UTF-8을 받는다. 텍스트를 CP949/EUC-KR, UHC 또는 게임 고유의 코드 페이지로 저장하는 애플리케이션은
   호출 전에 UTF-8(또는 코드 포인트)로 변환해야 한다. 라이브러리에는 바이트 쌍을 추측하는 기능이 없다.
2. **상단이 아니라 베이스라인.** `y_baseline`은 글리프의 어센트 아래의 행이다. 줄의 상단이 `top`에 오도록 그리려면 `top + e.ascent`
   (`e`는 `svf_measure_utf8`의 결과) 또는 `top + svf_ascent(&face)`를 넘긴다.
3. **줄 높이.** 범위의 `ascent + descent`는 측정된 텍스트의 셀이 베이스라인 위아래로 닿는 행 수이다(셀의 어센트와 `cell_h - ascent`를 `dy`만큼 옮긴 값).
   잉크가 있는 행이 아니다. 균일한 줄 간격에는 페이스들의 `cell_h`를 쓴다.
4. **여러 크기.** 페이스 하나는 셀 크기 하나이다. 크기마다 페이스 하나를 쓰거나(`svf/dos`에 많이 있다), 한 크기를 정수 비율로 스케일해서
   그리면 픽셀이 선명하게 유지된다.
5. **페이스의 수명.** 페이스 구조체, 데이터 버퍼(매핑) 또는 tables/cache/`ctx`(스트리밍)는 모든 그리기보다 오래 살아야 한다.
   `svf_face`를 이동시킬 메모리에 두지 말라.
6. **스레드.** 독립된 페이스/체인은 병렬로 쓸 수 있다. 하나의 페이스(캐시 포함)와 하나의 체인(음절 캐시 포함)을 두 스레드에서 쓰지 않는다.
7. **클리핑.** 타깃의 클립 사각형(`clip_x0..clip_y1`)을 대화 상자에 맞추라. 라이브러리는 그 바깥에 쓰지 않으며 완전히 바깥에 있는 셀의
   글리프는 읽지 않는다.
8. **사용자가 제공한 페이스를 검증하라.** `svf_open_*`는 악의적인 파일을 거부하도록 만들어졌지만(퍼즈 테스트되었다), 자신의 빌드에서 나오지
   않은 페이스에는 `-DSVF_JSET_TRUSTED=1`로 빌드하지 말라.
9. **어디서나 같은 스위치**(2절).

전형적인 래퍼는 서른 줄 정도이다. 페이스, 체인, 스크래치, 음절 캐시를 담은 객체 하나와, 각각 `svf_measure_utf8`와 `svf_draw_utf8`를 호출하는
`width(str)` 및 `draw(str, x, y_top)` 메서드로 이루어진다.

ScummVM에 대한 참고: 저장소의 ScummVM 작업은 현재 자체 SVF 리더(`jamo_set.h`)를 쓰며, 이는 버전 3 자모 블록을 읽지 못한다. 이를 이
라이브러리로 교체하는 일은 따로 추적된다([c/README.ko.md](../c/README.ko.md)의 "사용처" 참조). 이 절의 모든 내용은 그 통합에
적용된다.

## 15. 통합 테스트

- **레퍼런스.** `tools/svfline.py`는 같은 줄을 Python으로 그린다. 그 출력은 C 출력과 바이트 단위로 같아야 한다.
  `tools/test_c_renderer.py`는 저장소 자체의 비교이며, 양쪽을 어떻게 구동하는지는 이를 읽으라.
- **게이트.** `make -C c check`는 새니타이저 아래에서 단위 프로그램을 실행하고, 어떤 오브젝트도 `malloc`, `calloc`, `realloc`, `free`를
  참조하지 않는지 검증하며, Python 비교를 실행한다.
- **자신의 검사.** 알려진 문자열을 `SVF_T_GRAY8` 버퍼에 그려 출력하는 작은 프로그램(3절)이 레이아웃 문제를 가장 빨리 확인하는 방법이다.
  테스트는 `-fsanitize=address,undefined`로 컴파일하라.
- **페이스.** 페이스 파일에 무엇이 들어 있는지 보려면 `c/build/svfdump FACE info`(헤더 값, 레이아웃 단위, 상태 비트 `jset_bad`, `jset_unread`, `jmap_bad`,
  `jmap_unread`)를 실행한다. `svfdump FACE has U+AC00 U+D55C`는 각 코드 포인트가 그려지는지 알려 주고, `svfdump FACE syllables`는 조합된 음절 셀을 전부 덤프한다
  (Python 동일성 테스트의 C 쪽이다). Python에서는 `jamoset.parse_svfn`을 쓴다. `tools/facecheck.py`는 페이스 검사기가 **아니다**. 매니페스트와 폰트 맵이
  가리키는 페이스를 검사한다. 메이커 앱은 자신이 쓰는 모든 페이스를 검사하고, 완료로 치기 전에 그려 본다.

## 16. 문제 해결

| 증상 | 있을 법한 원인 | 할 일 |
|---|---|---|
| `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | SVFN 파일이 아니거나, 파일이 텍스트 모드로 읽혔거나 잘렸음 | 바이너리 모드로 열고 길이를 비교 |
| `SVF_E_VERSION` | 버전 2 파일 | `tools/svf2to3.py`로 변환 |
| `SVF_E_LAYOUT` | 빌드가 `-DSVF_LAYOUTS=...`로 컴파일되었고 페이스가 다른 레이아웃을 씀 | 빌드가 읽는 프로필로 페이스를 쓰거나, `SVF_LAYOUTS`를 넓힘 |
| 한글은 아무것도 그려지지 않는데 라틴은 됨 | 페이스가 일반 페이스임: `svf_status`에서 `SVF_FACE_JSET_BAD`, `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD`를 확인 | 페이스가 필요로 하는 리더로 빌드(10.1절)하거나 페이스를 다시 작성 |
| 한글이 누락 글리프 간격으로 그려짐 | 체인의 어느 페이스에도 그 코드 포인트가 없음 | `svf_has(face, cp)`. 페이스를 추가하고 `missing_advance`를 설정 |
| `svf_draw_utf8`가 `SVF_E_NOMEM`을 반환 | 스크래치가 `svf_chain_scratch_bytes`보다 작음(스케일이나 페이스를 바꾼 뒤 다시 계산) | 스크래치를 키움 |
| `svf_target_init`에서 `SVF_E_ARG` | 종류가 `SVF_TARGETS`에 없음, `buf_len < rows * stride`, stride가 너무 작음, 또는 w/h가 0 | 각각 확인. GRAY는 초기화 뒤에 `gray_bits`를 설정 |
| `svf_draw_utf8`에서 `SVF_E_ARG` | 페이스 없는 체인, 1..16을 벗어난 스케일 비율 또는 `SVF_NO_SCALE`, 잘못된 램프의 `INDEXED8`, `plot` 없는 `COVERAGE_CB` | 이것들을 확인 |
| `INDEXED8` 타깃에서 텍스트가 안 보임 | 배경 인덱스가 잉크 램프보다 낮지 않음(최댓값 규칙) | 팔레트 번호를 다시 매김 |
| 컬러 텍스트에 후광이 생김 | `bg565`/`bg888`이 실제 배경이 아님 | 실제 배경을 설정하거나 콜백 타깃을 사용 |
| 글리프가 한 행 높거나 낮음 | 베이스라인 대신 상단 행을 넘김 | `y_baseline = top + ascent` |
| `PROGMEM` 배열 페이스인 AVR 빌드에서 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | 라이브러리를 `-DSVF_RD8(p)=pgm_read_byte(p)` 없이 빌드하여 플래시 주소를 RAM으로 읽음 | 모든 라이브러리 소스를 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드(5.1절. simavr: 없으면 1, 있으면 0) |
| 페이스 배열이 RAM을 먹거나 링크가 RAM 초과로 실패 | 배열을 `xxd -i`로 만들었음(`const`가 아니라 `.data`) | `c/bench/mkface.py`로 생성(5절). `size`에서 페이스가 data가 아니라 text에 잡히는지 확인 |
| `-DSVF_SMALL`을 넣은 뒤 한글이 그려지지 않음 | `SVF_SMALL`이 `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG`의 기본값을 꺼서 버전 3 또는 BIG 페이스가 일반 페이스로 열림(`JSET_BAD`. `JMAP_UNREAD`는 `-DSVF_JMAP_RECOG=1`일 때만) | `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`을 더하거나, 빌드가 읽는 형식으로 페이스를 작성(10.1절, 12절) |
| 일부 한글 음절만 그려지고 나머지는 누락됨 | 페이스의 JMAP이 SPARSE 또는 LIST이고 폴백 블록이 없어서 나열된 음절만 조합됨 | 음절마다 `svf_has(face, cp)` 확인. 폴백이나 조밀한 테이블로 페이스를 다시 만듦(10절) |
| 텍스트의 오른쪽 끝이 버퍼에서 잘림 | 버퍼 크기를 펜 이동 거리인 `e.width`로 정했는데 마지막 글리프의 잉크가 그 너머까지 닿음 | `e.width + svf_cell_w(face)`(3절) |
| 업그레이드 뒤 크래시나 쓰레기 값 | 번역 단위들이 서로 다른 `-D` 스위치로 빌드됨(`SVF_JMAP`은 `svf_face`를 바꿈) | 하나의 플래그 집합으로 전부 다시 빌드 |
| 스트리밍 페이스에서 `SVF_E_IO` | 읽기 콜백이 모자라거나 음수인 개수를 반환함 | 정확히 `len`바이트 또는 음수 값을 반환. 파일 위치 로직을 확인 |
