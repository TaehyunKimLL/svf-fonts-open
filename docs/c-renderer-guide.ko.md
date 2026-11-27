[English](c-renderer-guide.md) | **한국어**

# SVF C 렌더러: 통합 가이드

이 가이드는 SVF C 렌더러(`c/`)를 자신의 프로그램에 넣는 방법을 설명한다. 소스를 얻는 방법, 페이스(face)를 여는 방법, 페이스를 펌웨어에
내장하는 방법, 장치에 들어가는 페이스를 고르는 방법, 자모 세트로 한글 음절을 조합하여 UTF-8 텍스트를 그리는 방법, 그리기 타깃을 고르는 방법, 메모리
예산을 잡는 방법, 지원 플랫폼용으로 빌드하는 방법, 그리고 그림이 잘못 나올 때 무엇을 확인할지를 다룬다. 이 문서는 튜토리얼이다. 레퍼런스는 [c/README.ko.md](../c/README.ko.md)(API 표, 컴파일 타임 스위치,
포트)이며, 무엇보다 모든 함수의 정확한 계약을 밝혀 두는 [c/include/svf.h](../c/include/svf.h)의 주석이다. 파일 포맷은
[spec/SVF.ko.md](../spec/SVF.ko.md)에, 설계는 [spec/renderer-design.ko.md](../spec/renderer-design.ko.md)에 있다.

3–12절의 이식 가능한 C 프로그램은 각각 파일로 복사하고 `cc -std=c99 -Wall -Wextra -Ic/include EXAMPLE.c c/src/*.c -o EXAMPLE`로 빌드한다.
내장 예제는 생성한 `face.c`도 링크한다. SDL 예제에는 13.6절의 플래그를 쓴다. C++ 예제는 C 소스를 먼저 `cc`로 컴파일한 뒤 `c++`로 링크한다.
파일 기반 예제에는 `svf/dos/NEODG16A.SVF`를 인자로 준다. 앱 소스에 폰트 바이트를 직접 적을 필요는 없다.
브라우저 통합은 [웹 렌더러 사용법](web-renderer-guide.ko.md)으로 이어진다.

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
17. 관련 문서

## 1. 다섯 단어로 보는 모델

**페이스, 체인, 타깃, 스크래치, 줄.**

- **페이스(face)**(`svf_face`)는 열린 `.SVF` 파일 하나이다. 셀 크기, 비트 깊이(픽셀당 1, 2 또는 8비트), 글리프 테이블, 그리고 선택적으로
  한글 음절을 조합할 수 있게 해 주는 자모 세트(11,172자 전부, 또는 그 테이블이 담은 음절)로 이루어진다. 구조체는 호출자가 할당하며, 라이브러리는 할당하지 않는다.
- **체인**(`svf_chain`)은 페이스의 순서 있는 목록이다. 각 코드 포인트는 그것을 가진 첫 번째 페이스가 그리므로,
  `{ ascii_face, hangul_face }`는 두 페이스로 섞인 줄을 그린다.
- **타깃**(`svf_target`)은 픽셀이 가는 곳이다. 아홉 가지 버퍼 포맷 중 하나의 바이트 버퍼이거나, 픽셀마다 `(x, y, coverage)` 하나씩을
  받는 콜백이다.
- **스크래치**는 글리프 복원·조합·스케일링에 쓰는, 호출자가 제공하는 임시 바이트 버퍼이다. 크기는 `svf_chain_scratch_bytes()`가 알려 준다.
- **줄**은 호출 하나, 즉 `svf_draw_utf8()`이다. UTF-8 바이트가 들어가고 픽셀이 나오며, 기준선을 따라 그려진다.

모든 것은 C99이고, `<stdint.h>`, `<stddef.h>`, `<string.h>`만 사용하며, `malloc`을 호출하지 않고, Python 레퍼런스
(`tools/jamoset.py`, `tools/svfline.py`)와 바이트 단위로 동일한 픽셀을 그린다.

아래에서 쓰는 용어: **셀**은 글리프 하나를 복원한 비트맵(`cell_w x cell_h` 픽셀)이다. **피복도**는 한 픽셀에 잉크가 얼마나 있는가를
0..255로 나타낸 값이다(1 bpp 잉크 픽셀은 255, 2 bpp 레벨 `k`는 `k * 85`, 8 bpp 픽셀은 그 바이트 자체). **기준선**은 어센트 아래의
행이며, 셀의 맨 위 행은 `y_baseline - ascent + dy`이다.

## 2. 라이브러리를 빌드에 넣기

라이브러리는 소스 파일 다섯 개, 비공개 헤더 하나, 공개 헤더 하나이다. 의존성은 없다.

    c/include/svf.h
    c/src/svf_face.c  svf_jamo.c  svf_stream.c  svf_draw.c  svf_scale.c   (+ svf_internal.h)

사용 방법은 세 가지이다.

1. **소스를 프로그램에 직접 컴파일한다.** 빌드에 `c/src/*.c`를 추가하고 `-I c/include`를 준다. 여기의 예제들이 이 방법을 쓴다.

       gcc -std=c99 -I c/include my_app.c c/src/*.c -o my_app

2. 제공된 Makefile로 **정적 라이브러리를 빌드한다.** `make -C c`는 `libsvf.a`(와 `svfdump` 도구)를 `c/build`에 쓰며, `O=DIR`로 위치를 옮길 수 있다.
3. **벤더링하거나 서브모듈로 넣는다.** 코드는 MIT 라이선스이다(`svf/` 아래의 페이스는 OFL이다.
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

### 2.1 CMake와 Makefile에서 설정하기

CMake 라이브러리 타깃의 정의를 `PUBLIC`으로 전달하면 헤더를 쓰는 앱과 라이브러리의 구조체 크기가 일치한다.
`SVF_ROOT`에는 SVF 소스가 있는 절대 경로를 준다. 아래 타깃은 라이브러리만 빌드한다.

```cmake
cmake_minimum_required(VERSION 3.16)
project(svf_embed C)
set(SVF_ROOT "" CACHE PATH "SVF source directory")
file(GLOB SVF_SOURCES CONFIGURE_DEPENDS "${SVF_ROOT}/c/src/*.c")
add_library(svf STATIC ${SVF_SOURCES})
target_include_directories(svf PUBLIC "${SVF_ROOT}/c/include")
target_compile_features(svf PUBLIC c_std_99)
target_compile_definitions(svf PUBLIC SVF_JMAP=1 SVF_JMAP_LIST=1)
```

```sh
cmake -S /path/to/project -B /tmp/svf-cmake -DSVF_ROOT="$PWD"
cmake --build /tmp/svf-cmake
make -C c O=/tmp/svf-make lib CFLAGS='-O2 -DSVF_JMAP=1 -DSVF_JMAP_LIST=1'
```

자체 Makefile에서는 같은 `CPPFLAGS`를 앱과 다섯 C 소스에 모두 적용한다. 제공된 `c/Makefile`은 `CFLAGS`로 정의를 받는다. Arduino는 포트의 빌드 스크립트·전역 extra flags에, ESP-IDF는 `${COMPONENT_LIB}`에 정의를 둔다. Pico SDK에서는 SDK 초기화와 별개로 앱 타깃의 `target_compile_definitions`를 사용한다. `CMAKE_C_FLAGS`를 덮어쓰지 않는다. 각 포트의 정확한 명령은 13절을 따른다.

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
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
	if (argc < 2) { fprintf(stderr, "usage: ex1 FACE [TEXT]\n"); return 2; }
	size_t len;
	uint8_t *bytes = slurp(argv[1], &len);
	svf_face face;
	svf_err err = bytes ? svf_open_mapped(&face, bytes, len) : SVF_E_IO;
	if (err != SVF_OK) { fprintf(stderr, "open failed: %d\n", (int)err); return 1; }

	svf_face *faces[1] = { &face };
	svf_chain chain = {0};            /* zeroed: scale 1/1, default marks, no cache */
	chain.faces = faces;
	chain.count = 1;

	const char *text = argc > 2 ? argv[2] : "SVF 안녕";
	svf_extent e;
	if (svf_measure_utf8(&chain, text, strlen(text), &e) != SVF_OK) return 1;
	/* e.width is the pen's travel, not the ink: the last cell can reach past it, so leave a cell's width of room */
	int w = e.width + svf_cell_w(&face) + 2, h = e.ascent + e.descent + 2;
	if (w <= 0 || w > 32767 || h <= 0 || h > 32767) return 1;
	uint8_t *pix = calloc((size_t)w * h, 1);
	size_t need = svf_chain_scratch_bytes(&chain);
	uint8_t *scratch = malloc(need);

	if (!pix || !scratch) { free(scratch); free(pix); free(bytes); return 1; }
	svf_target t;
	if (svf_target_init(&t, SVF_T_GRAY8, pix, (size_t)w * h, (int16_t)w, (int16_t)h, (uint16_t)w) != SVF_OK) return 1;
	err = svf_draw_utf8(&chain, text, strlen(text), 1, (int16_t)(1 + e.ascent), &t, scratch, need);
	/* Check every error; streamed glyphs can also fail record validation. */

	for (int y = 0; y < h; y++) {
		for (int x = 0; x < w; x++) putchar(pix[y * w + x] > 127 ? '#' : pix[y * w + x] ? '+' : '.');
		putchar('\n');
	}
	free(scratch); free(pix); free(bytes);
	return err == SVF_OK ? 0 : 1;
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

- `svf_open_mapped`는 헤더·테이블·레코드 범위를 검증한다. 기본 검증 설정에서는 열린 페이스를 안전하게 그릴 수 있다. 반환값은 파일이 거부된 이유(`SVF_E_MAGIC`,
  `SVF_E_VERSION`, ...)를 알려 준다.
- `svf_measure_utf8`는 글리프를 읽지 않고 줄의 범위(extent)를 준다. `e.width`는 **펜 이동 거리**(advance의 합)이며 잉크의 폭이 아니다. `e.ascent`와
  `e.descent`는 셀이 기준선 위와 아래로 닿는 행 수이다(잉크가 있는 행만이 아니라 셀 전체). 여기서는 64 x (12 + 4)이며 `dy`가 있는 글리프는 그 이동도 반영한다. `e.width`는 최대 32,767로 포화되므로 긴 줄은 나누어 처리한다.
- 그래서 버퍼의 폭은 `e.width + 2`가 아니라 `e.width + svf_cell_w(&face) + 2`이다. 글리프는 advance 너머에 잉크가 있을 수 있어(PAPLG16의 `f`는 3픽셀 넘어까지
  닿는다. 측정값) 마지막 셀이 셀 폭만큼 더 필요할 수 있고, 줄 맨 앞의 결합 부호는 `x`의 왼쪽에서 시작할 수 있다. 라이브러리는 타깃에 맞춰 클립하므로 바깥에는
  아무것도 쓰이지 않는다. 버퍼가 너무 작으면 메모리가 손상되는 것이 아니라 잉크가 잘린다.
- `svf_draw_utf8`에 넘기는 기준선 행은 `1 + e.ascent`이다. 범위의 어센트에 우리가 남겨 둔 1픽셀 여백을 더한 값이다.
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
제공한다. 글리프 행은 그릴 때 읽힌다. DOS 프로그램들이 이렇게 하므로, 1 MiB 페이스에 1 MiB의 RAM이 필요하지 않다.

```c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>
#include "svf.h"

static long rd(void *ctx, uint32_t off, uint8_t *dst, uint32_t len)
{
#if LONG_MAX < UINT32_MAX
    if (off > (uint32_t)LONG_MAX) return -1;
#endif
    return fseek((FILE *)ctx, (long)off, SEEK_SET) == 0
        ? (long)fread(dst, 1, len, (FILE *)ctx) : -1;
}

int main(int argc, char **argv)
{
    FILE *fp;
    long length;
    svf_face face;
    svf_err err;
    uint8_t *tables = NULL, *scratch = NULL;
    uint8_t cache[2 * (1024 + 8)], pixels[128 * 32] = {0};
    svf_face *faces[] = {&face};
    svf_chain chain = {0};
    svf_target target;
    int rc = 1;
    if (argc != 2) { fprintf(stderr, "usage: stream FACE\n"); return 2; }
    fp = fopen(argv[1], "rb");
    if (!fp) return 1;
    if (fseek(fp, 0, SEEK_END) || (length = ftell(fp)) <= 0 ||
        (uint64_t)length > UINT32_MAX) goto done;
    size_t need = svf_stream_tables_size(rd, fp, (uint32_t)length, &err);
    if (err != SVF_OK || !need || !(tables = malloc(need))) goto done;
    err = svf_open_stream(&face, rd, fp, (uint32_t)length, tables, need,
                          cache, sizeof cache, 1024);
    if (err != SVF_OK) goto done;
    chain.faces = faces; chain.count = 1;
    size_t scratch_len = svf_chain_scratch_bytes(&chain);
    scratch = malloc(scratch_len);
    if (!scratch) goto done;
    err = svf_target_init(&target, SVF_T_GRAY8, pixels, sizeof pixels, 128, 32, 128);
    if (err != SVF_OK) goto done;
    err = svf_draw_utf8(&chain, "SVF 한글", strlen("SVF 한글"), 0, 20,
                        &target, scratch, scratch_len);
    size_t ink = 0;
    for (size_t i = 0; i < sizeof pixels; ++i) ink += pixels[i] != 0;
    printf("status=%u tables=%zu scratch=%zu reads=%lu ink=%zu draw=%d\n",
           (unsigned)svf_status(&face), need, scratch_len,
           (unsigned long)svf_stream_reads(&face), ink, (int)err);
    rc = err != SVF_OK;
done:
    free(scratch); free(tables); fclose(fp);
    return rc;
}
```

알아 둘 규칙은 다음과 같다.

- `svf_stream_tables_size`는 `tables`가 얼마나 커야 하는지 알려 준다. 이는 페이스에, 그리고 빌드가 어떤 리더를 컴파일했는지에 달려 있다.
  `NEODG16A.SVF`(자모 페이스)는 8,153바이트이고, 완성형 `NEODG16.SVF`는 46,492바이트이다(측정값).
- 블록 캐시는 선택 사항이다(`cache_len`이 0이면 없음). 캐시가 있으면 라이브러리는 `block_size`바이트 블록(64에서 4096 사이의 2의 거듭제곱)
  전체를 읽고 가장 최근에 쓴 것들을 유지한다. 슬롯 하나는 `block_size + 8`바이트이며 캐시는 최소 두 슬롯을 담아야 한다.
  `cache_len`으로 `sizeof cache`를 넘긴다.
- 페이스는 사용자의 `tables`, `cache`, `rd`, `ctx`에 대한 포인터를 유지하므로 이것들을 살려 두라. 스트리밍 페이스 하나를 두 스레드에서
  동시에 그려서는 안 된다.
- 읽기가 실패하거나 모자라면 그리고 있던 글리프에 대해서만 `SVF_E_IO`가 반환된다. 줄은 계속 그려지고 오류는 끝에서 반환된다.
  잘못된 레코드를 읽으면 `SVF_E_RANGE`가 반환될 수도 있다. `svf_stream_reads(&face)`는 콜백 호출 횟수를 센다(캐시 크기를 조정할 때 유용하다).
- 캐시 **없이** 스트리밍 페이스의 음절을 조합하려면 `2 * svf_cell_bytes`의 스크래치가 필요하다(후반부에는 읽고 있는 조각이 들어간다).
  `svf_chain_scratch_bytes`가 이미 이를 반영한다.
- `-DSVF_NO_STREAM`이면 스트리밍 함수가 선언·정의되지 않는다. 호출 시 엄격한 경고 설정에서 컴파일 오류가 나거나 링크가 실패한다.

외부 SPI 플래시도 같은 스트리밍 인터페이스를 쓴다. `ctx`에 장치 상태를 두고 `rd`가 파일 시작 기준 `off`에서 `len`바이트를 읽게 한다. 성공 시 정확히 `len`, 실패 시 음수나 짧은 길이를 반환한다. 메모리 매핑 가능한 플래시는 5절의 `const` 배열처럼 `svf_open_mapped`로 읽는 편이 간단하다.

### 4.3 페이스가 알려 주는 것

열기에 성공한 뒤에는 접근자들이 헤더를 보고한다. `svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`, `svf_glyph_count`, `svf_flags`.
`svf_has(f, cp)`는 페이스가 코드 포인트를 그릴 수 있는지(저장된 글리프, 또는 조합해 내는 음절이나 호환 자모)를 알려 준다.
`svf_metrics_of(f, cp, &m)`는 글리프의 전진 폭(advance), 베어링, 잉크 너비, 수직 오프셋을 반환한다.

`svf_status(f)`는 놓치기 쉽지만 중요하다. 페이스는 성공적으로 열리고도 무엇이 버려졌는지를 알리는 **상태 비트**를 가질 수 있다. 예를 들어
`SVF_FACE_JSET_BAD`(자모 블록이 검증에 실패했다. 이 페이스는 일반 페이스이며 한글을 조합하지 않는다)나 `SVF_FACE_JSET_UNREAD`(버전 1·2 헤더는 유효하지만 이 빌드에 해당 리더가 없다)가 있다. 음절이 나오지 않을 때 가장 먼저 확인할 것은 상태가 0이 아닌 한글 페이스이다
(16절).

열기 반환값이 `SVF_OK`라도 아래 상태가 함께 있을 수 있다. 저장된 글리프는 계속 그릴 수 있으므로
앱이 필요한 문자에 대해 `svf_has`를 확인하고, 진단 메시지에는 오류 코드와 상태를 함께 기록한다.

| 상태 | 의미 |
|---|---|
| `SVF_FACE_CMAP_LINEAR` | 정렬되지 않았거나 중복 코드 포인트. 선형 조회, 중복은 마지막 항목. |
| `SVF_FACE_DY_IGNORED` | 잘못된 dy 범위를 무시. |
| `SVF_FACE_METRICS_DROPPED` | 메트릭 영역을 버리고 셀 폭을 전진 폭으로 사용. |
| `SVF_FACE_JSET_BAD`, `SVF_FACE_JMAP_BAD` | 잘못된 조합 블록. 세부 폴백 규칙은 [명세](../spec/SVF.ko.md#검증). |
| `SVF_FACE_JSET_UNREAD`, `SVF_FACE_JMAP_UNREAD` | 빌드에서 해당 리더가 꺼져 있음. 지원되는 폴백이 있으면 사용. |

## 5. 페이스 내장하기

마이크로컨트롤러에는 파일 시스템이 없거나, 있어도 의존하고 싶지 않다. 또 페이스 하나만 싣는 프로그램은 페이스를 프로그램 안에 넣는 편이
단순하다. `c/bench/mkface.py`가 페이스를 C 배열로 써 준다.

    python3 -I c/bench/mkface.py svf/dos/NEODG16G.SVF face.c --name neodg16g --profile mcu-strict

Python 3과 `tools/jamoset.py`가 필요하다. import 경로는 스크립트 위치를 기준으로 찾으므로 다른 작업 디렉터리에서도
실행할 수 있다. 아래 파일 경로는 프로젝트 루트를 기준으로 한다. `--name`은 C 식별자여야 한다. 출력의 공개 심벌은 다음과 같다.

`face.c`는 `const uint8_t neodg16g[]`와 `const uint32_t neodg16g_len`을 정의한다.
AVR에서는 배열에 `PROGMEM`이 붙으며 정렬은 선택한 레이아웃을 따른다.

- 배열을 플래시에 두는 링커 설정에서는 RAM 사본 없이 읽는다. AVR에서는 `PROGMEM`이어서 플래시 고유의 주소 공간에 놓이고,
  라이브러리는 `SVF_RD8`을 통해 읽는다(4.1절). `NAME_len`은 페이스의 바이트 크기이다. 둘 다 `svf_open_mapped`에 넘긴다.
- `aligned(A)`의 `A`는 기록된 레이아웃의 `2^max(REC, TAB)`바이트이다(`mcu-strict`는 4이며 1이면 생략된다). 그래서 파일 안의 레코드
  오프셋이 곧 주소 정렬이 된다. 정렬은 **속도에만** 관여한다. `svf_open_mapped`는 *파일 안의* 오프셋 정렬을 레이아웃에 맞춰 검사할 뿐
  배열의 주소는 검사하지 않는다. 페이스는 홀수 주소에서도 똑같이 열리고 그려진다.
- `--profile mcu-strict`는 페이스를 `SVF_LAYOUT_MCU_STRICT` 레이아웃(레코드와 테이블 단위 4바이트, 행 단위 1바이트, 들어맞는 곳은 16비트
  오프셋)으로 다시 쓴다. 픽셀은 같다. 배포된 117개 페이스의 레이아웃 단위는 모두 4/1/4바이트이다. 따라서 `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` 빌드는 배포된 파일을 그대로 열 수 있고, 프로파일은 오프셋만 줄인다. NEODG16G는
  10,684바이트에서 10,124바이트가 된다. `--profile`을 주지 않으면 바이트는 파일 그대로이다. `dos`·`wasm` 프로파일(레이아웃 단위 1/1/1바이트)의 페이스는 그런
  빌드에서 `SVF_E_LAYOUT`으로 거부된다.
- **내장 페이스에는 `mkface.py`를 사용한다.** 기본 `xxd -i` 출력은 `const`가 아닌 `unsigned char name[]`이다.
  이를 그대로 링크하면 RAM 사본이 생길 수 있다. AVR용 `PROGMEM`과 레이아웃에 맞는 정렬도 별도로 지정해야 한다.

### 5.1 배열이 가는 곳, 플랫폼별

| 타깃 | 페이스가 있는 곳 | 비고 |
|---|---|---|
| AVR(Arduino Uno) | `PROGMEM` 플래시 | 라이브러리를 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드한다. `SVF_RD8`이 없으면 라이브러리가 플래시 주소를 RAM으로 읽어 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환한다. `svf_draw_utf8`에 넘기는 텍스트는 일반 로드로 읽힌다. RAM에 두라(`PROGMEM` 문자열은 먼저 `strncpy_P`로 복사한다) |
| 그 밖의 Arduino 코어(ARM, ESP32, RP2040) | 플래시의 `const` 배열 | 플래시가 메모리에 매핑되어 있으므로 `SVF_RD8` 재정의도 `PROGMEM`도 필요 없다(`mkface`는 `__AVR__`에서만 `PROGMEM`을 붙인다) |
| ESP32(ESP-IDF) | `const` 배열(플래시의 `.rodata`), **또는** `esp_partition_mmap`으로 매핑한 데이터 파티션, **또는** 스트리밍하는 SPIFFS 파일 | 파티션은 페이스를 앱 이미지와 그 크기에서 빼 준다. SPIFFS + `svf_open_stream`은 주소 공간에서도 뺀다(13.4절) |
| Raspberry Pi Pico / Pico 2 | 플래시의 `const` 배열, 제자리 실행(XIP) | 페이스는 XIP 캐시를 거쳐 읽힌다. 블록을 처음 건드리면 플래시 읽기이다(13.5절) |
| CH582 | CodeFlash의 `const` 배열 | 링커가 `.rodata`를 플래시에 둔다. RAM 사본이 없다 |
| DOS, SDL, 데스크톱, WASM | 메모리에 읽어 들인 파일(`fread`, `SDL_LoadFile`, 모듈로 복사한 JavaScript `Uint8Array`), 또는 `mmap` | 또는 파일에서 스트리밍(4.2절). 버퍼는 페이스보다 오래 살아야 한다 |

### 5.2 연 뒤에: 페이스를 확인하라

`svf_open_mapped`는 파일이 유효하다는 것만 알려 줄 뿐, 이 빌드가 그 한글을 조합할 수 있다는 것은 알려 주지 않는다. 시작할 때 한 번 둘 다
확인하라(이것이 `text_cb.c`이다. 호스트와 Cortex-M0+에서, 그리고 13.1절의 Uno 플래그에 `-DSVF_TARGETS=0x10`을 주면 AVR에서도 컴파일된다. 이 예제는 콜백 종류로 그리므로 `0x02`이면 `text_init`이 -3을 반환한다).

```c
/* text_cb.c - draw UTF-8 with a face embedded by c/bench/mkface.py through your own pixel routine. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "svf.h"

extern const uint8_t neodg16g[];            /* face.c from mkface.py --name neodg16g */
extern const uint32_t neodg16g_len;

/* Your display driver: one pixel, on/off (or a grey level from cov). */
static unsigned ink;
void lcd_set_pixel(int16_t x, int16_t y, uint8_t on)
{
    (void)x; (void)y;
    ink += on != 0;
}

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	(void)ctx;
	lcd_set_pixel(x, y, cov >= 128);
}

static svf_face face;                       /* must outlive every draw */
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
	return svf_is_jamo(&face) && svf_status(&face) == 0 ? 0 : -4;   /* -4: opened plain: svf_status says why */
}

/* Draws s with its top-left at (x, y_top); returns the width drawn (the pen's travel). */
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

int main(void)
{
    int init = text_init(128, 32);
    if (init) { printf("init=%d\n", init); return 1; }
    int width = text_draw("SVF 한글", 0, 0);
    printf("status=%u width=%d ink=%u\n", (unsigned)svf_status(&face), width, ink);
    return width < 0;
}
```

한글을 조합하는 페이스에서는 `svf_is_jamo`가 1이고, 아무것도 버려지지 않았으면 `svf_status`가 0이다(4.3절). 조합 블록을 사용할 수 없더라도 저장된 글리프는 그릴 수 있다. `JMAP_UNREAD`만으로 일반 페이스라고 단정할 수는 없다. 지원되는 폴백이 있으면 조합된다.
완성형 페이스에는 자모 블록이 없으므로 대신 `svf_has(&face, 0xD55C)`를 확인한다.

`text_cb.c`를 `face.c`와 함께 빌드하고 실행한다. 호스트의 픽셀 함수는 켜진 픽셀 호출 수를 세며, 장치에서는 디스플레이 쓰기로 바꾼다.

```sh
cc -std=c99 -Wall -Wextra -Ic/include text_cb.c face.c c/src/*.c -o text_cb
./text_cb
# status=0 width=64 ink=248
```

### 5.3 C++와 Arduino: `face.c`는 C 파일로 둔다

배열은 `.c` 파일로 생성하여 C 컴파일러가 빌드하게 하라. C++에서 네임스페이스 범위의 `const` 배열은 별도 외부 링크 선언이 없으면 내부 링크를 가지므로 다른
번역 단위에서 참조할 수 없다.[9] Arduino 빌드는 스케치 폴더의 `.c` 파일을 C로 컴파일한다. C++ 쪽에서는 C 링키지로 선언한다(`c/ports/arduino/arduino.ino`가
그렇게 한다).

```cpp
#ifdef __AVR__
#include <avr/pgmspace.h>
#else
#define PROGMEM
#endif
#include "svf.h"                          /* svf.h는 C++에서 스스로 extern "C"로 감싸져 있다 */

extern "C" {
extern const uint8_t neodg16g[] PROGMEM;  /* face.c, mkface.py에서 */
extern const uint32_t neodg16g_len;
}

static svf_face face;
bool face_ok() { return svf_open_mapped(&face, neodg16g, neodg16g_len) == SVF_OK; }
int main() { return face_ok() ? 0 : 1; }
```

### 5.4 배포할 라이선스

페이스가 들어 있는 프로그램이나 이미지는 폰트 소프트웨어를 배포하는 것이다.[10] 다음을 함께 배포하라. 페이스 자체의 라이선스 텍스트(NEODG16G는
`svf/dos/OFL.TXT`와 `svf/dos/NEODGM.TXT`, PAPLG16과 PAPLG18은 `svf/dos/OFLPAPLG.TXT`. `web/LICENCES.tsv`가 `svf/` 아래 모든 페이스를 그
라이선스 파일에 대응시킨다), [NOTICE.ko.md](../NOTICE.ko.md)(무엇이 어떤 라이선스 아래에 있는지), 그리고 [LICENSE](../LICENSE)(라이브러리
코드의 MIT). `c/ports/FACES.md`는 포트가 내장하는 각 페이스의 출처, 저작권, 라이선스를 밝히며, Pico, ESP32, CH582 빌드는 이것과 라이선스
텍스트를 `<build>/licences/`에 복사한다.

## 6. 타깃에 맞는 페이스 고르기

페이스는 파일이다. 어디에 들어가는지는 픽셀 크기가 아니라 파일 크기가 정한다. 쓰려는 페이스를 직접 측정하라.

    python3 -I c/bench/mkface.py svf/dos/NEODG16A.SVF x.c --name x --profile mcu-strict && tail -2 x.c

마지막 줄 `const uint32_t x_len = 15528u;`가 아래 표의 숫자이다. 링크되는 바이트이다. 배열은 `mcu-strict` 출력 기준이며 스트리밍 테이블은 원본 파일과 기본 호스트 빌드 기준이다.

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

- **한글.** 표의 자모 세트 페이스는 조각을 조합한다. 지원 범위는 조합 블록에 달려 있다(10절). 완성형 페이스는 지원하는 음절마다 글리프를 저장한다.
  위 배열 크기에서 NEODG16은 NEODG16A의 약 8.24배이다. 작은 장치에는 필요한 음절을 지원하는 자모 페이스가 유리하다.
- **Uno.** ATmega328P는 SRAM 2 KiB를 제공한다.[3] 표의 적합 여부는 플래시에 내장하는 구성을 전제로 한다.
  최종 코드와 페이스, 전역 데이터, 스택을 함께 확인한다. AVR 플래시 읽기와 빌드 스위치는 13.1절을 따른다.
- **CH582.** 포트의 `link.ld`는 플래시 448 KiB·RAM 32 KiB를 배정한다. 페이스 외에 코드와 플래시에서 복사되는 데이터도 포함한다.
- **Pico.** Pico 보드는 플래시 2 MiB, Pico 2는 4 MiB를 갖는다.[6] 표의 페이스는 이 용량 안에 들어가지만 최종 이미지 전체를 확인한다.
- **ESP32.** 앱에 내장할 수 있는 크기는 선택한 파티션 표에 달려 있다. 표는 1 MiB 앱 파티션을 전제로 하며,
  GBATB47은 페이스만으로 이보다 크다. 더 큰 앱 파티션이나 별도 데이터 파티션을 사용한다(13.4절).[5]
- **스트리밍**(SD, SPIFFS, 디스크의 파일)에는 테이블용 RAM(위 열, 배포된 파일 기준)과 선택적 블록 캐시가 필요하다. Uno는 할 수 없다(`NEODG16G`만으로도
  테이블이 5,129바이트이고, Uno 빌드는 리더를 뺀다).
- 그리기에 쓰는 **RAM**은 적다. 스크래치는 비스케일 매핑 페이스에서 셀 하나(`셀 바이트`, 11절)이고 여기에 프레임 버퍼가 더해진다.

## 7. 텍스트 한 줄: 체인, 메트릭, 측정

### 7.1 폴백 체인

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc < 2 || argc > 3) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    hangul_face = face;
    size_t latin_len;
    uint8_t *latin_bytes = slurp(argc == 3 ? argv[2] : argv[1], &latin_len);
    if (!latin_bytes || svf_open_mapped(&latin_face, latin_bytes, latin_len) != SVF_OK) {
        free(latin_bytes); free(bytes); return 1;
    }
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;

svf_face *faces[2] = { &latin_face, &hangul_face };
svf_chain chain = {0};
chain.faces = faces;
chain.count = 2;
chain.missing_advance = 8;      /* pixels to advance for a code point no face has (nothing is drawn) */
svf_target target;
svf_extent extent;
const char *text = "SVF 한글";
if (svf_target_init(&target, SVF_T_GRAY8, pix, sizeof pix, 64, 24, 64) != SVF_OK ||
    svf_measure_utf8(&chain, text, strlen(text), &extent) != SVF_OK ||
    svf_draw_utf8(&chain, text, strlen(text), 0, 20, &target, scratch, scratch_len) != SVF_OK)
    return 1;
printf("faces=%u width=%d scratch=%zu\n", (unsigned)chain.count, extent.width,
       svf_chain_scratch_bytes(&chain));
    free(latin_bytes); free(bytes);
    return 0;
}
```

각 코드 포인트는 `svf_has`가 참인 첫 번째 페이스가 그린다. 순서가 중요하다. 공유되는 문자(숫자, 구두점)에 원하는 스타일의 페이스를
먼저 두라. `chain.faces`가 `NULL`이거나, `count`가 0이거나, 항목 중 하나가 NULL이면 체인은 "페이스 없음" 상태가 된다. 이 체인을 쓰는
호출은 `SVF_E_ARG`를 반환하고 아무것도 그리지 않는다.

완전한 체인 예제는 `./chain svf/dos/NEODG16A.SVF svf/dos/PAPLG16.SVF`로 실행한다. 두 번째 인자를 생략하면 같은 파일을 두 번 열어 호출 경로만 보여 준다.

### 7.2 결합 부호, 전진 폭, 잘못된 UTF-8

- advance는 페이스의 메트릭 테이블에서 온다(가변 폭). 메트릭 테이블이 없는 페이스는 셀 폭만큼 전진한다. 조합된 음절은 자모 블록의
  음절 advance(또는 셀 폭)만큼 전진한다.
- 지원되는 결합 부호는 전진하지 않는다. 현재 펜 위치에 놓되, 페이스 플래그 비트 2가 켜져 있고 `bearing_x < 0`이면
  `min(-bearing_x, cell_w)`만큼 왼쪽으로 옮긴다. 기본 판정 함수는 U+0300..U+036F이며, 다른 범위에는 `chain.is_mark`를 지정한다.
  페이스에 없는 코드 포인트는 결합 부호라도 `missing_advance`만큼 전진한다.
- 잘못된 UTF-8은 절대 크래시하지 않으며 `len`을 넘어 읽지도 않는다. 잘못된 부분 시퀀스는 각각 어떤 페이스에 U+FFFD가 있으면 그것으로
  그려지고, 없으면 전진 없이 건너뛴다. NUL은 일반 코드 포인트이다(C 문자열이 아니라 `len`바이트가 그려진다).

### 7.3 그리기 전에 측정하기

`svf_measure_utf8(&chain, s, len, &e)`는 그리기와 정확히 같은 레이아웃 규칙을 써서 `e.width`, `e.ascent`, `e.descent`를 주며, 글리프를
읽지 않는다(그래서 비용이 적고 스트리밍 페이스는 측정 중 I/O를 하지 않는다). 가운데 정렬, 오른쪽 정렬, 단어 줄바꿈, 그리고 그려 넣을 버퍼의
크기를 정할 때 쓴다. `e.width`는 펜 이동 거리이지 잉크의 범위가 아니다. 마지막 셀이 그 너머로(셀 폭까지) 닿을 수 있으므로 버퍼 크기를 정할 때
`svf_cell_w(face)`를 더하라(3절). 단어와 줄은 사용자의 몫이다. 라이브러리는 한 번에 한 줄을 그리며 줄바꿈에 대해서는 아무것도 모른다.

## 8. 타깃: 픽셀이 가는 곳

타깃은 그려진 각 픽셀의 피복도를 사용자의 포맷으로 변환한다. 종류는 `svf_target_init`로 고른다.

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
| 픽셀당 피복도 1바이트 | `SVF_T_GRAY8` | 직접 합성하는 마스크 |
| **그 밖의 모든 것** | `SVF_T_COVERAGE_CB` | 콜백이 `(x, y, coverage)`를 받음 |

각 종류가 기존 픽셀을 어떻게 다루는지는 정확하며 `svf.h`의 `svf_target` 위에 문서화되어 있다. 요약은 다음과 같다.

- 컬러 종류(`RGB565`, `RGB555`, `XRGB8888`, `RGB888`)는 **기존 픽셀을 읽지 않는다**. `bg`와 `fg`를 피복도로 섞은 값을 쓰므로, `bg`는
  배경의 실제 색이어야 한다. 단색 배경에 그리거나, 임의의 내용 위에 섞으려면 콜백 종류를 쓰라.
- `GRAY8`, `INDEXED8`, `GRAY`는 기존 값과 새 값 중 최댓값을 유지한다. `INDEXED8`에서는 기존 인덱스가 잉크의 인덱스보다 낮은 곳에만 텍스트가
  보인다는 뜻이다. 배경 인덱스를 램프 `index_base + 1 .. index_base + index_levels`보다 아래에 두라.
- `MONO_*`는 피복도가 `t.mono_threshold`(기본값 128) 이상일 때 비트를 설정하며 비트를 지우지 않는다.
- 클립 사각형(`t.clip_x0..clip_y1`, 반개구간, 기본값은 타깃 전체) 안의 픽셀만 쓰인다. 이웃 픽셀의 바이트나 행 패딩은 건드리지 않는다.

2 bpp 단계가 종류마다 어떤 색이 되는지(정확한 섞기 식과 반올림, 단계별 mono 임계값)와 어떤 화면에 어떤 bpp가 맞는지는 그림과 함께
[안티앨리어싱](anti-aliasing.ko.md#23-단계가-색이-되는-과정)에 있다.

### 8.1 32비트 서피스 위의 컬러 텍스트

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

svf_target t;
if (svf_target_init(&t, SVF_T_XRGB8888, surface_pixels, (size_t)pitch * height,
                    (int16_t)width, (int16_t)height, (uint16_t)pitch) != SVF_OK) return 1;
t.fg888 = 0x00FFC000;      /* amber text */
t.bg888 = 0x00000020;      /* the background colour the caller knows */
for (size_t i = 0; i < sizeof pix; i += 4) {
    pix[i] = 0x20; pix[i + 1] = 0; pix[i + 2] = 0; pix[i + 3] = 0;
}
if (svf_draw_utf8(&chain, "SVF 한글", strlen("SVF 한글"), 0, 20,
                  &t, scratch, scratch_len) != SVF_OK) return 1;
printf("status=%u scratch=%zu\n", (unsigned)svf_status(&face), svf_chain_scratch_bytes(&chain));
    free(bytes);
    return 0;
}
```

`stride`는 바이트 수를 나타내는 `uint16_t`이므로, 32비트 타깃의 폭은 최대 16,383픽셀이다. 픽셀의 **메모리 순서는 모든 호스트에서 B, G, R, X**이다.
네이티브 32비트 값으로 `0x00RRGGBB`가 되는 것은 리틀 엔디언 호스트에서뿐이다. 코어는 호스트 바이트 순서와 관계없이 같은 네 바이트를 쓴다.

### 8.2 콜백 타깃: 만능 어댑터

픽셀 포맷이 위의 것들 중 어느 것도 아니거나, 기존 내용 위에 섞고 싶거나, 목적지가 다른 라이브러리의 서피스일 때는 콜백을 쓴다.
라이브러리는 클립 안에서 피복도가 0보다 큰 각 픽셀마다 셀별로 행 단위로 `plot(ctx, x, y, coverage)`를 한 번씩 호출하며, 버퍼는 관여하지
않는다. 이 예제는 32비트 서피스의 기존 픽셀과 흰 텍스트를 섞는다(메모리 순서 B, G, R, X를 바이트 단위로 읽고 쓴다).

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

typedef struct { uint8_t *pix; int pitch; uint32_t fg; } Surf;      /* your surface */

static void plot(void *ctx, int16_t x, int16_t y, uint8_t cov)
{
	Surf *s = ctx;
	uint8_t *px = s->pix + (size_t)y * s->pitch + 4 * (size_t)x;
	for (int c = 0; c < 3; ++c) {                              /* B, G, R */
		uint32_t b = px[c], f = (s->fg >> (8 * c)) & 255;
		px[c] = (uint8_t)((b * (255 - cov) + f * cov + 127) / 255);
	}
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

Surf s = { pix, 64 * 4, 0x00FFFFFF };
svf_target t;
if (svf_target_init(&t, SVF_T_COVERAGE_CB, NULL, 0, 64, 24, 0) != SVF_OK) return 1;
t.plot = plot;
t.ctx = &s;
if (svf_draw_utf8(&chain, "가A", strlen("가A"), 2, 16, &t, scratch, scratch_len) != SVF_OK) return 1;
printf("status=%u scratch=%zu\n", (unsigned)svf_status(&face), svf_chain_scratch_bytes(&chain));
    free(bytes);
    return 0;
}
```

`plot`은 그리기 전에 설정해야 한다(아니면 `SVF_E_ARG`). 두 셀이 한 픽셀에서 겹치는 곳(마크가 기본 글자 위에 얹힐 때)에서는 콜백이 셀마다
한 번씩 호출되므로, 섞는 콜백은 둘을 모두 합성하며, 이것이 원하는 동작이다.

## 9. 스케일링

`chain.scale_num`과 `chain.scale_den`을 설정한다(각각 1에서 16; 0과 0은 1/1을 뜻한다). 정수배(`2/1`, `3/1`)는 원본 픽셀을 각각 N x N 블록으로
그리므로 비트맵의 가장자리가 선명하게 유지된다. 다른 비율은 영역 평균을 내어 8비트 피복도가 되므로, 1 bpp 페이스의 `3/2`는 가장자리
픽셀이 회색이 된다(이때는 컬러나 회색조 타깃을 쓰라. 모노 타깃에서는 임계값이 결정한다). 길이는 반올림(0.5는 올림, 대칭)으로
스케일되므로, 측정된 범위는 그려진 것과 같다. `x`, `y_baseline`, 클립은 항상 출력 픽셀 단위이다.

스크래치는 스케일링에 따라 커진다. 스케일된 줄에는 체인에서 가장 큰 페이스를 기준으로 **저장된 셀의 두 배에 스케일된 셀을 더한 만큼**이 필요하다.

    scratch = 2 * svf_cell_bytes(face) + ceil(cell_w * num / den) * ceil(cell_h * num / den)

스케일된 셀은 8비트 피복도로 픽셀당 1바이트이다. 식은 매핑된 페이스와 스트리밍 페이스에서, 그리고 스트리밍 페이스에 블록 캐시가 있든 없든 같다(1/1에서는
셀 하나가 필요하고, 캐시 없는 스트리밍 페이스는 둘이다). `svf_chain_scratch_bytes`가 이를 계산한다. 스케일을 바꾼 뒤에는 항상 다시 계산하라. 16x16 1 bpp
`NEODG16A`(셀 32바이트)에서 측정한 값은, 3/2는 2 x 32 + 24 x 24 = 640바이트, 2/1은 2 x 32 + 32 x 32 = 1,088, 1/2는 2 x 32 + 8 x 8 = 128이다.

작은 MCU 빌드에서는 `-DSVF_NO_SCALE`이 스케일링을 완전히 제거한다(그러면 n/n 이외의 비율은 `SVF_E_ARG`이다). 빠른 스케일러의 스택 프레임은
약 610~680바이트이다. 2 KB RAM 칩에서 쓰기 전에 `svf.h`의 "Scaling"을 보라.

## 10. 한글: 자모 페이스와 음절 조합

**완성형** 페이스는 담당하는 음절마다 글리프 하나를 저장한다. **자모 세트(jamo-set)** 페이스(헤더 플래그 비트 1,
`svf_is_jamo(f)`)는 수백 개의 작은 조각과, 어떤 조각들이 각 음절을 이루는지 알려 주는 테이블을 저장한다. `svf_draw_utf8`는 조각들로부터
U+AC00..U+D7A3(그리고 호환 자모 U+3131..U+3163)을 즉석에서 조합한다. 음절의 두세 조각을 픽셀별 피복도 최댓값으로 합친다. 호환 자모는 지정된 한 조각을 사용한다. 특별히 할 일은 없다. 그냥 한글
텍스트를 그리면 된다. 한 가지 단서가 있다. 음절 테이블은 일부만 담을 수 있다. SPARSE(비트맵과 그 항목들) 또는 LIST(예외 최대 255개의 정렬된 목록)인
버전 3 JMAP 블록에 **폴백 블록이 없으면** 그 블록이 나열한 음절만 조합된다. 나머지는 `svf_has`가 0이고 잉크 없이 `missing_advance`만큼 전진한다. 유효하고 빌드에서 지원하는 폴백
블록이 있으면 테이블에 없는 음절은 폴백으로 간다. 조밀한 JMAP과 버전 1, 2 블록은 11,172자 전부를 다룬다.

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

if (svf_is_jamo(&face)) {
	uint16_t pieces[3];
	int n = svf_jamo_pieces(&face, 0xD55C /* 한 */, pieces);   /* 3: initial, medial, final */
	for (int i = 0; i < n; i++)
		printf("piece %u\n", (unsigned)pieces[i]);               /* glyph U+F0000 + number in the face */
}
size_t cell_len = svf_chain_scratch_bytes(&chain);
uint8_t *cell = malloc(cell_len);
if (!cell || svf_glyph(&face, 0xD55C, cell, cell_len) != SVF_OK) {
    free(cell); free(bytes); return 1;
}
free(cell);
printf("status=%u scratch=%zu\n", (unsigned)svf_status(&face), svf_chain_scratch_bytes(&chain));
    free(bytes);
    return 0;
}
```

`svf_glyph`와 `svf_compose`는 타깃 없이 코드 포인트 하나의 셀을 반환한다. 자신의 아틀라스에 글리프를 캐시할 때 유용하다.

### 10.1 사용자의 빌드가 읽는 것

자모 블록은 버전 1, 2, 3(LIST 형식이 있는 JMAP)이 있다. 기본 데스크톱/DOS/WASM/SDL 빌드는 모두 읽는다(`-DSVF_SMALL`에서는 읽지 않는다. 12절). 작은 MCU 빌드는 더 적게 읽는다
([c/README.ko.md](../c/README.ko.md)의 표 "자모 세트: 각 빌드가 읽는 것" 참조). 조합 블록을 읽지 못하면 상태 비트를 설정한다. 지원되는 JSET 폴백이 있으면 그것으로 조합하고, 없으면 **일반**
페이스로 연다. 로드 시점에 `svf_status`, `svf_is_jamo`, 필요한 코드 포인트의 `svf_has`를 함께 확인한다.

### 10.2 조합된 음절 캐시

조합에는 음절마다 몇 번의 테이블 조회와 병합이 든다. 반복되는 텍스트(UI, 프레임마다 다시 그리는 대화 상자)에는 체인에 캐시를 준다.

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "svf.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *fp = fopen(path, "rb");
    long n;
    uint8_t *p;
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 ||
        (unsigned long)n > SIZE_MAX || fseek(fp, 0, SEEK_SET)) {
        fclose(fp); return NULL;
    }
    p = malloc((size_t)n);
    if (p && fread(p, 1, (size_t)n, fp) != (size_t)n) { free(p); p = NULL; }
    fclose(fp);
    *len = (size_t)n;
    return p;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    size_t len;
    uint8_t *bytes = slurp(argv[1], &len);
    svf_face face, latin_face, hangul_face;
    if (!bytes || svf_open_mapped(&face, bytes, len) != SVF_OK) return 1;
    latin_face = face; hangul_face = face;
    (void)latin_face; (void)hangul_face;
    svf_face *base_faces[] = {&face};
    svf_chain base_chain = {0};
    base_chain.faces = base_faces; base_chain.count = 1;
    (void)base_chain;
    uint8_t scratch[4096], pix[64 * 24 * 4] = {0};
    uint8_t *surface_pixels = pix;
    int pitch = 64 * 4, width = 64, height = 24;
    size_t scratch_len = sizeof scratch;
    (void)surface_pixels; (void)pitch; (void)width; (void)height;
    (void)scratch; (void)scratch_len;
    svf_chain chain = base_chain;
    (void)chain;

static uint8_t syl[4096];                       /* slots of (8 + the largest cell bytes of the chain's faces) */
svf_chain_cache(&chain, syl, sizeof syl);
chain.scale_num = 3; chain.scale_den = 2;
size_t need = svf_chain_scratch_bytes(&chain);
if (need > sizeof scratch) return 1;
const svf_target_kind kinds[] = {SVF_T_GRAY8, SVF_T_MONO_ROW, SVF_T_RGB565};
const uint16_t strides[] = {64, 8, 128};
for (unsigned k = 0; k < 3; ++k) {
    svf_target t;
    memset(pix, 0, sizeof pix);
    if (svf_target_init(&t, kinds[k], pix, sizeof pix, 64, 24, strides[k]) != SVF_OK) return 1;
    t.fg565 = 0xffff; t.bg565 = 0;
    t.clip_x0 = 2; t.clip_x1 = 62;
    if (svf_draw_utf8(&chain, "한글", strlen("한글"), 0, 20, &t, scratch, need) != SVF_OK) return 1;
    unsigned nonzero = 0;
    for (size_t j = 0; j < sizeof pix; ++j) nonzero += pix[j] != 0;
    printf("kind=%d scratch=%zu nonzero=%u\n", (int)kinds[k], need, nonzero);
}

    free(bytes);
    return 0;
}
```

캐시가 있든 없든 픽셀은 동일하다. 스트리밍 페이스에서 가장 효과가 크다. 캐시된 음절은 읽기를 전혀 일으키지 않는다. 라틴 글리프처럼 조합하지 않는 셀은
이 캐시의 대상이 아니므로 같은 줄을 다시 그려도 읽기가 생길 수 있다. 캐시는 선형 조회를 쓰는
라운드 로빈 방식이다. 작은 타깃에는 수십 개의 슬롯이 알맞고, 수천 개는 맞지 않는다. `chain.faces`를 바꾸거나 페이스를 다시 연 뒤에는
`svf_chain_cache`를 다시 호출하라.

## 11. 메모리 예산

모든 메모리는 사용자의 것이다. 합산하라.

| 항목 | 크기 |
|---|---|
| `svf_face` | `sizeof(svf_face)`: `SVF_JMAP`이 있는 64비트 호스트에서 96바이트(없으면 80, MCU에서는 더 작음. 실제 크기는 ABI에 따라 `sizeof`로 확인) |
| `svf_chain`, `svf_target` | 각각 수십 바이트 |
| 스크래치 | `svf_chain_scratch_bytes(&chain)`: 셀 하나(`svf_cell_bytes`), 블록 캐시 없는 스트리밍 페이스는 그 두 배. 스케일링 시에는 **셀의 두 배에 스케일된 셀을 더한 만큼**(9절) |
| 스트리밍 페이스 | 테이블용 `svf_stream_tables_size(...)`, 선택적 캐시용 `slots * (block_size + 8)` |
| 음절 캐시 | `slots * (8 + 가장 큰 셀 바이트 수)` |
| 타깃 버퍼 | `rows * stride`(콜백 종류는 없음) |
| 매핑된 페이스 | 파일 자체, RAM 또는 플래시에(플래시에 배치한 `const` 배열이나 PROGMEM 페이스는 RAM 사본이 없음, 5절) |
| 스택 | 스케일러 자신의 프레임: 기본 빠른 스케일러에서 AVR은 약 610바이트, Cortex-M0+는 680바이트 |

16x16 1 bpp 셀은 32바이트이고, 24x24 2 bpp 셀은 144바이트이다.

## 12. 컴파일 타임 스위치: 세 가지 레시피

스위치는 **모든** 소스에 주는 `-D` 플래그이다(2절). 데스크톱에서는 거의 필요하지 않다. 레시피를 고를 때 중요한 것들은 다음과 같다.

- **데스크톱, DOS, WASM, SDL, ScummVM급 애플리케이션: 스위치 없음.** 모든 것이 켜져 있다.
- **디스플레이 하나인 작은 MCU:** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_TARGETS=<one kind's bit> -DSVF_JSET_V2=0
  -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`를 쓰고, 맞는 프로파일로 페이스를 쓴다(`tools/jamoset.py` `mcu-strict`. 배포되는 페이스는 이미 그 레이아웃이며 `c/bench/mkface.py --profile mcu-strict`는 오프셋을 줄인다. 5절). Arduino Uno 빌드가 정확히
  이것을 쓴다. [c/ports/arduino/README.ko.md](../c/ports/arduino/README.ko.md)를 보라.
- **어느 CPU에서든 가장 작은 코드:** `-DSVF_SMALL`은 속도 중심의 빠른 경로(워드 병합, GRAY8 테이블, 빠른 스케일러, 니블 popcount 테이블)를 끈다. 픽셀은 동일하며
  속도만 잃는다. **그리고 빌드가 읽는 것도 바꾼다.** `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG`의 *기본값*을 0으로 뒤집는다(기본 데스크톱·DOS·WASM 빌드에서는 1이다). 따라서 데스크톱, DOS, WASM의 `SVF_SMALL` 빌드는 버전 3(JMAP, LIST) 자모 블록이나 BIG 한계를 더는 읽지
  않는다. 그것을 필요로 하는 페이스는 `SVF_FACE_JSET_BAD`가 설정된(`SVF_FACE_JMAP_UNREAD`는 `-DSVF_JMAP_RECOG=1`일 때만) **일반 페이스**로 열리고 한글을 그리지 않는다. 필요하면
  `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`을 더하라(`SVF_JMAP_LIST`는 `SVF_JMAP`을 따른다).

툴체인별 기본값이 있는 전체 스위치 표는 [c/README.ko.md](../c/README.ko.md)의 "컴파일 시점 스위치"에 있고, 각 구성이 만드는 크기는
`c/cross/SIZES.md`에 있다.

| 매크로 | 기본값과 효과 |
|---|---|
| `SVF_SMALL` | 기본 미정의. 정의하면 빠른 경로를 줄이고 JMAP·BIG 기본값을 끈다. `=0`도 정의한 것으로 처리한다. |
| `SVF_JMAP` | 데스크톱·DOS·WASM에서 1, AVR·MCU·SMALL에서 0. 버전 3 매핑 리더와 `svf_face` 크기에 영향. |
| `SVF_JMAP_LIST` | `SVF_JMAP`을 따름. LIST 리더. JMAP 없이 1이면 컴파일 오류. |
| `SVF_JMAP_RECOG` | 데스크톱·DOS·WASM에서 1, MCU·SMALL에서 0. JMAP을 읽지 않아도 인식하고 폴백 사용. |
| `SVF_JSET_BIG` | 데스크톱·DOS·WASM에서 1, MCU·SMALL에서 0. 클래스·세트 한도 확장. |
| `SVF_JSET_V1`, `SVF_JSET_V2` | V1은 1, V2는 AVR에서 0이고 그 외 1. V1·V2·JMAP 중 하나 이상 켜야 한다. CH582 포트는 V2를 명시적으로 끈다. |
| `SVF_JSET_TRUSTED` | 0. 1은 내장한 검증된 페이스에만 사용. 표 내용 검증을 생략한다. |
| `SVF_JSET_POP4` | 보통 1, AVR·SMALL에서 0. V2 popcount 구현 선택. |
| `SVF_NO_STREAM`, `SVF_NO_SCALE` | 기본 미정의. 정의하면 해당 기능 제거. |
| `SVF_LAYOUTS` | 기본은 모든 유효 레이아웃. 예: `SVF_LAYOUT_MCU_STRICT`. |
| `SVF_TARGETS` | `0x3ff`. 타깃 비트 OR: GRAY8 `0x001`, MONO_PAGE `0x002`, MONO_ROW `0x004`, RGB565 `0x008`, CB `0x010`, INDEXED8 `0x020`, RGB555 `0x040`, XRGB8888 `0x080`, RGB888 `0x100`, GRAY `0x200`. |
| `SVF_RD8(p)` | 기본 일반 메모리 읽기. AVR PROGMEM에서는 `pgm_read_byte(p)`로 재정의. |
| `SVF_MERGE_WORDS`, `SVF_GRAY8_LUT1`, `SVF_SCALE_FAST`, `SVF_WORD_STORE` | CPU·SMALL에 따른 최적화. 정확한 기본 조건은 [svf.h](../c/include/svf.h). 픽셀 의미는 같다. |

## 13. 플랫폼

각 포트의 빌드 설정과 디스플레이 드라이버를 시작점으로 삼는다. 아래 명령은 저장소 루트에서 시작한다.
빌드 성공과 실제 패널 동작은 별도로 확인해야 한다. 메모리 사용량은 툴체인·SDK·페이스·플래그에 따라 달라지므로
최종 이미지에서 `size`와 링크 맵을 확인한다. 구성별 크기는 [빌드 크기 표](../c/cross/SIZES.md)에 있다.

### 13.1 Arduino Uno와 그 밖의 Arduino 코어

Arduino 빌드는 스케치 폴더의 `.c`를 C로 컴파일한다.[1] 다음은 Uno용 `MONO_PAGE` 설정이다.
`arduino-cli`와 `arduino:avr` 코어를 먼저 설치한다.

```sh
mkdir -p ~/Arduino/libraries/svf
cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
python3 -I c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
arduino-cli compile -b arduino:avr:uno c/ports/arduino \
    --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"
```

생성한 `face.c`는 `.ino` 옆에 두고 C++에서는 5.3절처럼 C 링키지로 선언한다.
`compiler.c.extra_flags`와 `compiler.cpp.extra_flags`에 같은 플래그를 준다. `build.extra_flags`는 어셈블러에도 전달되므로
`-include avr/pgmspace.h`를 넣는 용도로 쓰지 않는다. AVR의 `PROGMEM` 읽기에는 `SVF_RD8` 재정의가 필요하다.[2]
텍스트는 RAM에 두거나 `strncpy_P` 등으로 복사한 뒤 넘긴다.

[arduino.ino](../c/ports/arduino/arduino.ino)는 128 x 64, 1,024바이트 페이지 버퍼에 그리고 `Wire`로 16바이트씩 보낸다.
Uno의 SRAM은 2 KiB이므로[3] 프레임버퍼 외에 Wire 버퍼·전역 데이터·스택을 함께 계산한다. 스케일링과 스트리밍은 위 설정에서 제외된다.
Mega에서도 `pgm_read_byte`의 주소 범위 밖에 있는 페이스는 이 포트로 읽을 수 없다. 메모리 매핑된 플래시를 쓰는 다른 코어에는
AVR용 `SVF_RD8` 플래그를 적용하지 않는다. 자세한 설정은 [Arduino 포트](../c/ports/arduino/README.ko.md)를 따른다.

### 13.2 WCH CH582(RISC-V, 베어메탈)

[CH582 포트](../c/ports/ch582/README.ko.md)는 WCH CH583 EVT의 스타트업·주변장치 코드와
`riscv32-esp-elf-gcc`를 사용한다. SDK와 컴파일러 경로는 [Makefile](../c/ports/ch582/Makefile)의
`CH583_SDK`, `CROSS`로 바꾼다.

```sh
sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
make -C c/ports/ch582
# BOOT held while connecting USB / USB 연결 시 BOOT 버튼 누름
make -C c/ports/ch582 flash
```

라이브러리는 `-std=c99`, 포트는 `-std=gnu99`로 빌드한다. 라이브러리 스위치는 Uno와 같은
`SVF_NO_SCALE`, `SVF_NO_STREAM`, `SVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, `SVF_TARGETS=0x02`, `SVF_JSET_V2=0`이다.
페이스는 플래시의 `const` 배열이다. [link.ld](../c/ports/ch582/link.ld)는 플래시 448 KiB, RAM 32 KiB,
스택 2,048바이트를 배정한다. `.highcode`는 RAM에 배치하므로 플래시와 RAM 예산에 모두 반영한다.

128 x 64 SH1106은 PB20(SDA)·PB21(SCL)의 I2C, 주소 0x3C를 쓴다. `MONO_PAGE` 버퍼는 1,024바이트이다.
`display_show(buf, y, rows)`는 타임아웃이 있는 `ch582_i2c_write`를 통해 전송한다.
`FREQ_SYS=24000000`은 `main.c`의 `SetSysClock(CLK_SOURCE_PLL_24MHz)`와 일치해야 한다.

### 13.3 DOS(DJGPP)

DJGPP로 32비트 보호 모드 실행 파일을 만든다. 실제 DOS에는 DPMI 호스트가 필요하며,
`CWSDPMI.EXE`를 실행 파일 옆이나 `PATH`에 둘 수 있다.[4]

```sh
DJ="$HOME/opt/djgpp/bin/i586-pc-msdosdjgpp"
"$DJ-gcc" -std=gnu99 -O2 -Ic/include c/ports/dos/svfdemo.c c/src/*.c -o SVFDEMO.EXE
"$DJ-gcc" -std=gnu99 -O2 -Ic/include -Ic/ports/dos c/ports/dos/svfvesa.c c/ports/dos/vbe_select.c \
    c/ports/dos/vesa_lines.c c/src/*.c -o SVFVESA.EXE
```

라이브러리는 `__DJGPP__`의 전체 기본 기능을 쓴다. 포트의 POSIX 함수를 선언하는 헤더를 위해 `-std=gnu99`를 사용한다.
긴 파일 이름을 지원하지 않는 환경에서는 `NEODG16A.SVF`, `VESALINE.TXT` 같은 8.3 이름을 사용한다.
stdio는 `fopen(path, "rb")`, 저수준 파일 API는 `O_RDONLY | O_BINARY`로 연다.[4]

`svfdemo.c`는 PAPLG16·PAPLG18을 스트리밍하고 1 KiB 블록 캐시를 각각 16·64슬롯 사용한다.
320 x 200 GRAY8 화면은 64,000바이트이며 회색 팔레트와 함께 VGA 모드 13h로 복사한다.
`svfvesa.c`는 8·15·16·24·32 bpp VBE 타깃을 다룬다. 큰 페이스는 4.2절의 스트리밍으로 연결한다.
자세한 실행 방법은 [DOS 포트](../c/ports/dos/README.ko.md)를 따른다.

### 13.4 ESP32(ESP-IDF)

[ESP32 포트](../c/ports/esp32/README.ko.md)는 ESP32-C3·ESP32-S3용이다. ESP-IDF 환경을 먼저 활성화한다.
프로파일과 칩별로 빌드 디렉터리를 나누고, 칩을 바꿀 때 공유 `sdkconfig`도 확인한다.

```sh
cd c/ports/esp32
idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3
idf.py -B build-colour build flash monitor
```

`main/CMakeLists.txt`는 페이스를 `mkface.py --profile mcu-strict`로 생성한다.
자체 컴포넌트는 `svf.h`, `svf_internal.h`, `svf_*.c`, 생성한 `face.c`를 포함하고 동일한 정의로 빌드한다.
다른 컴포넌트에서도 `svf.h`를 include한다면 정의와 include 경로를 `PUBLIC`으로 전달한다.[5]

```cmake
# main/CMakeLists.txt; svf/ contains headers and sources / 헤더와 소스는 svf/에 둔다
file(GLOB SVF_SRCS svf/*.c)
idf_component_register(SRCS main.c face.c ${SVF_SRCS} INCLUDE_DIRS svf)
target_compile_definitions(${COMPONENT_LIB} PUBLIC SVF_NO_SCALE SVF_TARGETS=0x08)
```

플래시 `const` 배열은 `svf_open_mapped`로 연다. 데이터 파티션은 `esp_partition_find_first`로 찾고
`esp_partition_mmap(..., ESP_PARTITION_MMAP_DATA, &ptr, &handle)`으로 매핑한 뒤 실제 파일 길이로 연다.
페이스 사용이 끝나면 `esp_partition_munmap(handle)`을 호출한다. SPIFFS는 `esp_vfs_spiffs_register`로 마운트하고
4.2절의 stdio 콜백으로 스트리밍한다. 자체 컴포넌트가 이 API를 사용하면 필요한 `esp_partition`·`spiffs` 의존성도 선언한다.[5]

컬러 프로파일은 320 x 24 RGB565 밴드(15,360바이트)를 `spi_device_polling_transmit`로 ILI9341에 보낸다.
드라이버에 맞춰 `SVF_TF_RGB16_BIGENDIAN`을 설정한다. QEMU `esp_rgb` 드라이버는 플래그 0을 쓴다.
앱 파티션에 페이스가 들어가는지는 최종 이미지와 선택한 파티션 표로 확인한다.

### 13.5 Raspberry Pi Pico와 Pico 2(pico-sdk)

pico-sdk 경로를 지정하고, Pico 2의 Arm 코어에는 `-DPICO_BOARD=pico2`를 추가한다.
`PICO_NO_PICOTOOL=1`이면 아래 프로젝트는 `pico_add_extra_outputs`를 생략하므로 `.uf2`를 만들지 않는다.[6]

```sh
cmake -S c/ports/pico -B build-pico-mono -DSVF_PROFILE=mono -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico-mono
cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico2-mono
```

자체 타깃에는 `c/src/*.c`와 생성한 `face.c`를 더하고 `c/include`를 include 경로로 설정한다.
`target_compile_definitions`로 앱과 라이브러리에 같은 스위치를 주고 `pico_stdlib` 및 사용하는 버스 라이브러리를 링크한다.
[포트의 CMakeLists.txt](../c/ports/pico/CMakeLists.txt)가 전체 구성 예이다.

SSD1306은 GP4·GP5의 I2C(`i2c_write_blocking`), ST7789는 GP16..GP20의 SPI(`spi_write_blocking`)로 연결한다.
컬러 프로파일은 240 x 24 RGB565 밴드(11,520바이트)를 쓰며 `SVF_TF_RGB16_BIGENDIAN`을 설정한다.
페이스는 XIP 플래시에서 읽는다.[6] 에뮬레이터 실행 시간만으로 실제 보드의 플래시·캐시·버스 시간을 단정할 수 없다.
배선과 플래시 방법은 [Pico 포트](../c/ports/pico/README.ko.md)를 따른다.

### 13.6 SDL2와 SDL3

[SDL 포트](../c/ports/sdl/README.ko.md)는 `sdl_compat.h`로 SDL2·SDL3를 지원한다.
다음 SDL3 예제는 페이스를 읽어 2/1 배율로 그리고 `out.bmp`에 저장한다.
`SDL_PIXELFORMAT_BGRX32`는 호스트 바이트 순서와 관계없이 메모리 순서 B, G, R, X를 나타낸다.[7]

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
      SDL_Surface *surf = SDL_CreateSurface(320, 48, SDL_PIXELFORMAT_BGRX32); /* memory bytes B G R X */
      if (!surf || !SDL_FillSurfaceRect(surf, NULL, SDL_MapSurfaceRGB(surf, 0, 0, 0x20)) || !SDL_LockSurface(surf))
          return 1;
      if (svf_target_init(&t, SVF_T_XRGB8888, surf->pixels, (size_t)surf->pitch * surf->h, (int16_t)surf->w,
                          (int16_t)surf->h, (uint16_t)surf->pitch) != SVF_OK)
          return 1;
      t.fg888 = 0x00FFC000;
      t.bg888 = 0x00000020;                                  /* 서피스를 채운 색 */
      svf_err e = svf_draw_utf8(&chain, s, strlen(s), 4, (int16_t)(4 + 2 * svf_ascent(&face)), &t, scratch, sizeof scratch);
      SDL_UnlockSurface(surf);
      bool saved = SDL_SaveBMP(surf, "out.bmp");
      SDL_DestroySurface(surf);
      SDL_free(bytes);
      return e == SVF_OK && saved ? 0 : 1;
  }
  ```
```sh
export PKG_CONFIG_PATH="$HOME/opt/sdl3/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
cc -std=c99 -Wall -Wextra -Ic/include sdl_min.c c/src/*.c $(pkg-config --cflags --libs sdl3) \
    -Wl,-rpath,$(pkg-config --variable=libdir sdl3) -o sdl_min
SDL_VIDEODRIVER=dummy ./sdl_min svf/dos/NEODG16A.SVF
```

`stride`에는 `surf->pitch`를 넘긴다. 그리기 중에는 서피스를 잠그고, 색상 타깃의 `bg888`과 같은 색으로 먼저 채운다.
16비트 SDL 서피스는 호스트 순서를 따르므로 빅 엔디언에서는 `SVF_TF_RGB16_BIGENDIAN`을 설정한다.
`make -C c/ports/sdl SDL=2`·`SDL=3`은 전체 예제를 빌드하며,
`sh c/ports/sdl/check.sh`는 지원 포맷의 서피스 바이트를 Python 출력과 비교한다.

### 13.7 웹(WebAssembly, Emscripten)

[웹 렌더러 사용법](web-renderer-guide.ko.md)에 HTML·Node 예제와 메모리 해제 순서가 있다.
공통 빌드 함수를 쓰면 `EMSCRIPTEN_KEEPALIVE` API와 `_malloc`·`_free`, 힙 뷰, 메모리 증가 설정을 함께 적용한다.[8]

```sh
mkdir -p /tmp/svf-module
. c/ports/web/emcc-flags.sh
svf_web_compile "$PWD" /tmp/svf-module
```

래퍼가 노출하는 타깃은 GRAY8·MONO_PAGE·MONO_ROW·RGB565이다. 슬롯에는 페이스를 최대 4개 열 수 있다.
`svfw_draw`의 첫 스크래치는 정적 65,536바이트이고, 더 필요할 때 동적 할당한다. GBATB47의 16/1 배율에는
`2*648 + (46*16)*(54*16) = 637200`바이트가 필요하다. C 코어는 동적 할당을 하지 않는다.
페이스 메모리를 해제하기 전에 `svfw_reset`을 호출하고, WASM 메모리가 증가할 수 있는 호출 뒤에는 힙 뷰를 다시 얻는다.[8]

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
2. **상단이 아니라 기준선.** `y_baseline`은 글리프의 어센트 아래의 행이다. 줄의 상단이 `top`에 오도록 그리려면 `top + e.ascent`
   (`e`는 `svf_measure_utf8`의 결과) 또는 `top + svf_ascent(&face)`를 넘긴다.
3. **줄 높이.** 범위의 `ascent + descent`는 측정된 텍스트의 셀이 기준선 위아래로 닿는 행 수이다(셀의 어센트와 `cell_h - ascent`를 `dy`만큼 옮긴 값).
   잉크가 있는 행이 아니다. 균일한 줄 간격에는 페이스들의 `cell_h`를 쓴다.
4. **여러 크기.** 페이스 하나는 셀 크기 하나이다. 크기마다 페이스 하나를 쓰거나(`svf/dos`에 많이 있다), 한 크기를 정수 비율로 스케일해서
   그리면 픽셀이 선명하게 유지된다.
5. **페이스의 수명.** 페이스 구조체, 데이터 버퍼(매핑) 또는 tables/cache/`ctx`(스트리밍)는 모든 그리기보다 오래 살아야 한다.
   `svf_face`를 이동시킬 메모리에 두지 말라.
6. **스레드.** 독립된 페이스/체인은 병렬로 쓸 수 있다. 스트리밍 페이스·음절 캐시처럼 변경되는 상태는 동시에 공유하지 않는다. 각 호출에는 독립된 스크래치와 타깃을 사용한다.
7. **클리핑.** 타깃의 클립 사각형(`clip_x0..clip_y1`)을 대화 상자에 맞추라. 라이브러리는 그 바깥에 쓰지 않으며 완전히 바깥에 있는 셀의
   글리프는 읽지 않는다.
8. **사용자가 제공한 페이스를 검증하라.** `svf_open_*`는 악의적인 파일을 거부하도록 만들어졌지만(퍼즈 테스트되었다), 자신의 빌드에서 나오지
   않은 페이스에는 `-DSVF_JSET_TRUSTED=1`로 빌드하지 말라.
9. **어디서나 같은 스위치**(2절).

래퍼는 페이스, 체인, 스크래치, 음절 캐시를 담은 객체와, 각각 `svf_measure_utf8`와 `svf_draw_utf8`를 호출하는
`width(str)` 및 `draw(str, x, y_top)` 메서드로 이루어진다.


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
  가리키는 페이스를 검사한다. 출력 제작은 [메이커 앱](maker-desktop.ko.md), 페이스 조회와 미리보기는 [데스크톱 앱](desktop-app.ko.md)을 참고한다.

## 16. 문제 해결

| 증상 | 있을 법한 원인 | 할 일 |
|---|---|---|
| `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | SVFN 파일이 아니거나, 파일이 텍스트 모드로 읽혔거나 잘렸음 | 바이너리 모드로 열고 길이를 비교 |
| `SVF_E_VERSION` | 버전 2 파일 | `tools/svf2to3.py`로 변환 |
| `SVF_E_LAYOUT` | 빌드가 `-DSVF_LAYOUTS=...`로 컴파일되었고 페이스가 다른 레이아웃을 씀 | 빌드가 읽는 프로파일로 페이스를 쓰거나, `SVF_LAYOUTS`를 넓힘 |
| 한글은 아무것도 그려지지 않는데 라틴은 됨 | 페이스가 일반 페이스임: `svf_status`에서 `SVF_FACE_JSET_BAD`, `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD`를 확인 | 페이스가 필요로 하는 리더로 빌드(10.1절)하거나 페이스를 다시 작성 |
| 한글이 누락 글리프 간격으로 그려짐 | 체인의 어느 페이스에도 그 코드 포인트가 없음 | `svf_has(face, cp)`. 페이스를 추가하고 `missing_advance`를 설정 |
| `svf_draw_utf8`가 `SVF_E_NOMEM`을 반환 | 스크래치가 `svf_chain_scratch_bytes`보다 작음(스케일이나 페이스를 바꾼 뒤 다시 계산) | 스크래치를 키움 |
| `svf_target_init`에서 `SVF_E_ARG` | 종류가 `SVF_TARGETS`에 없음, `buf_len < rows * stride`, stride가 너무 작음, 또는 w/h가 0 | 각각 확인. GRAY는 초기화 뒤에 `gray_bits`를 설정 |
| `svf_draw_utf8`에서 `SVF_E_ARG` | 페이스 없는 체인, 1..16을 벗어난 스케일 비율 또는 `SVF_NO_SCALE`, 잘못된 램프의 `INDEXED8`, `plot` 없는 `COVERAGE_CB` | 이것들을 확인 |
| `INDEXED8` 타깃에서 텍스트가 안 보임 | 배경 인덱스가 잉크 램프보다 낮지 않음(최댓값 규칙) | 팔레트 번호를 다시 매김 |
| 컬러 텍스트에 후광이 생김 | `bg565`/`bg888`이 실제 배경이 아님 | 실제 배경을 설정하거나 콜백 타깃을 사용 |
| 글리프가 한 행 높거나 낮음 | 기준선 대신 상단 행을 넘김 | `y_baseline = top + ascent` |
| `PROGMEM` 배열 페이스인 AVR 빌드에서 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | 라이브러리를 `-DSVF_RD8(p)=pgm_read_byte(p)` 없이 빌드하여 플래시 주소를 RAM으로 읽음 | 모든 라이브러리 소스를 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드(5.1절) |
| 페이스 배열이 RAM을 먹거나 링크가 RAM 초과로 실패 | 배열을 `xxd -i`로 만들었음(`const`가 아니라 `.data`) | `c/bench/mkface.py`로 생성(5절). `size`에서 페이스가 data가 아니라 text에 잡히는지 확인 |
| `-DSVF_SMALL`을 넣은 뒤 한글이 그려지지 않음 | `SVF_SMALL`이 `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG`의 기본값을 꺼서 버전 3 또는 BIG 페이스가 일반 페이스로 열림(`JSET_BAD`. `JMAP_UNREAD`는 `-DSVF_JMAP_RECOG=1`일 때만) | `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`을 더하거나, 빌드가 읽는 형식으로 페이스를 작성(10.1절, 12절) |
| 일부 한글 음절만 그려지고 나머지는 누락됨 | 페이스의 JMAP이 SPARSE 또는 LIST이고 폴백 블록이 없어서 나열된 음절만 조합됨 | 음절마다 `svf_has(face, cp)` 확인. 폴백이나 조밀한 테이블로 페이스를 다시 만듦(10절) |
| 텍스트의 오른쪽 끝이 버퍼에서 잘림 | 버퍼 크기를 펜 이동 거리인 `e.width`로 정했는데 마지막 글리프의 잉크가 그 너머까지 닿음 | `e.width + svf_cell_w(face)`(3절) |
| 업그레이드 뒤 크래시나 잘못된 값 | 번역 단위들이 서로 다른 `-D` 스위치로 빌드됨(`SVF_JMAP`은 `svf_face`를 바꿈) | 하나의 플래그 집합으로 전부 다시 빌드 |
| 스트리밍 페이스에서 `SVF_E_IO` | 읽기 콜백이 모자라거나 음수인 개수를 반환함 | 정확히 `len`바이트 또는 음수 값을 반환. 파일 위치 로직을 확인 |

## 17. 관련 문서

[프로젝트 안내](../README.ko.md)에서 시작해 [SVF 용어집](../spec/SVF.ko.md#glossary),
[렌더러 설계](../spec/renderer-design.ko.md), [자모 세트](jamo-sets.ko.md)를 읽으면 데이터와 조합 규칙을 확인할 수 있다.
[레시피](recipes.ko.md)와 [도구 사용법](tools.ko.md)은 페이스 제작·변환에,
[안티앨리어싱](anti-aliasing.ko.md)은 피복도·색상·출력 비트 깊이 선택에 사용한다.
[웹 가이드](web-renderer-guide.ko.md), [데스크톱 앱](desktop-app.ko.md), [메이커 앱](maker-desktop.ko.md)은 앱별 흐름을 설명한다.

## 참고 문헌 / References

1. Arduino, Sketch build process: https://docs.arduino.cc/arduino-cli/sketch-build-process/
2. AVR-LibC, Program Space Utilities: https://avrdudes.github.io/avr-libc/avr-libc-user-manual/group__avr__pgmspace.html
3. Arduino UNO R3 datasheet (ATmega328P SRAM): https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf
4. DJGPP FAQ mirror (DPMI, binary files): https://djgpp.mirror.garr.it/v2faq/faq6_2.html ; https://djgpp.mirror.garr.it/v2faq/faq9_4.html
5. ESP-IDF v5.5, build system, partitions and SPIFFS; CMake compile definitions: https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-guides/build-system.html ; https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/storage/partition.html ; https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-guides/partition-tables.html ; https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/storage/spiffs.html ; https://cmake.org/cmake/help/latest/command/target_compile_definitions.html
6. Raspberry Pi, Pico C/C++ SDK and Pico/Pico 2 datasheets: https://datasheets.raspberrypi.com/pico/raspberry-pi-pico-c-sdk.pdf ; https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf ; https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf
7. SDL3, pixel formats and surfaces: https://wiki.libsdl.org/SDL3/SDL_PixelFormat ; https://wiki.libsdl.org/SDL3/SDL_LockSurface ; https://wiki.libsdl.org/SDL3/SDL_SaveBMP
8. Emscripten, module options and memory access: https://emscripten.org/docs/api_reference/module.html ; https://emscripten.org/docs/porting/connecting_cpp_and_javascript/Interacting-with-code.html
9. C++ linkage: https://en.cppreference.com/cpp/language/storage_duration#Internal_linkage
10. SIL Open Font License 1.1: https://openfontlicense.org/open-font-license-official-text/
