[English](c-renderer-guide.md) | **한국어**

# SVF C 렌더러: 통합 가이드

이 가이드는 SVF C 렌더러(`c/`)를 프로그램에 통합하는 방법을 설명한다. 소스 추가, 페이스 열기, 펌웨어 내장, 장치 용량에 맞는 페이스 선택, 자모 세트를 이용한 한글 음절 조합과 UTF-8 텍스트 렌더링, 타깃 선택, 메모리 예산 계산, 플랫폼별 빌드, 문제 해결까지 순서대로 다룬다.

이 문서는 통합 튜토리얼이다. 레퍼런스는 [c/README.ko.md](../c/README.ko.md)(API 표·컴파일 타임 스위치·포트 목록)이며, 무엇보다 각 함수의 정확한 규약은 [c/include/svf.h](../c/include/svf.h) 주석이 기준이다. 파일 포맷은 [spec/SVF.ko.md](../spec/SVF.ko.md)에, 내부 설계는 [spec/renderer-design.ko.md](../spec/renderer-design.ko.md)에 정리되어 있다.

3–12절의 이식 가능한 C 예제는 각각 별도 파일로 저장한 뒤 `cc -std=c99 -Wall -Wextra -Ic/include EXAMPLE.c c/src/*.c -o EXAMPLE`로 빌드한다.
내장 예제는 생성한 `face.c`를 함께 링크한다. SDL 예제는 13.6절의 플래그를 사용하고, C++ 예제는 C 소스를 먼저 `cc`로 컴파일한 뒤 `c++`로 링크한다.
파일을 여는 예제에는 `svf/dos/NEODG16A.SVF`를 인자로 넘긴다. 폰트 바이트를 앱 소스에 직접 적을 필요는 없다.
브라우저 통합은 [웹 렌더러 사용법](web-renderer-guide.ko.md)을 참고한다.

## 목차

1. 다섯 단어로 보는 모델
2. 라이브러리를 빌드에 넣기
3. 완전한 첫 번째 프로그램
4. 페이스: 매핑 방식과 스트리밍 방식
5. 페이스 내장하기
6. 타깃에 맞는 페이스 고르기
7. 텍스트 한 줄: 체인, 메트릭, 측정
8. 타깃: 픽셀 출력 버퍼와 콜백
9. 스케일링
10. 한글: 자모 페이스와 음절 조합
11. 메모리 예산
12. 컴파일 타임 스위치: 세 가지 레시피
13. 플랫폼: Arduino, CH582, DOS, ESP32, Pico, SDL, 웹
14. 기존 텍스트 렌더링 경로에 통합하기
15. 통합 테스트
16. 문제 해결
17. 관련 문서

## 1. 다섯 단어로 보는 모델

**페이스, 체인, 타깃, 스크래치, 줄.**

- **페이스(폰트)**(`svf_face`): 열린 `.SVF` 파일 하나를 뜻한다. 셀 크기, 비트 깊이(1·2·8 bpp), 글리프 테이블, 그리고 선택적으로 한글 음절(11,172자 전체 또는 테이블에 등록된 음절)을 조합하는 자모 세트를 담는다. 구조체는 호출자가 직접 할당하며, 라이브러리는 메모리를 할당하지 않는다.
- **체인**(`svf_chain`): 페이스를 우선순위 순으로 묶은 목록이다. 각 코드 포인트는 해당 문자를 지원하는 첫 번째 페이스가 그린다. 예를 들어 `{ ascii_face, hangul_face }`처럼 구성하면 두 페이스로 영문과 한글이 섞인 줄을 그릴 수 있다.
- **타깃(출력 버퍼)**(`svf_target`): 렌더링한 픽셀이 기록되는 목적지다. 아홉 가지 메모리 버퍼 포맷 중 하나를 쓰거나, 픽셀마다 `(x, y, coverage)`를 받는 콜백을 지정한다.
- **스크래치**: 글리프 디코딩·조합·스케일링에 쓰는 임시 바이트 버퍼로, 호출자가 제공한다. 필요한 크기는 `svf_chain_scratch_bytes()`로 구한다.
- **줄**: `svf_draw_utf8()` 한 번의 호출이다. UTF-8 바이트열을 받아 기준선을 따라 픽셀을 그린다.

라이브러리 전체는 C99로 작성했으며 `<stdint.h>`, `<stddef.h>`, `<string.h>`만 사용한다. `malloc`을 호출하지 않으며 Python 레퍼런스(`tools/jamoset.py`, `tools/svfline.py`)와 바이트 단위로 동일한 픽셀을 출력한다.

### 이 문서의 용어

이 문서에서 추가로 쓰는 용어는 다음과 같다(전체 정의는 [SVF 한영 용어집](../spec/SVF.ko.md#glossary) 참고).

| 용어 | 뜻 |
|---|---|
| **셀** (cell) | 글리프 하나를 복원한 비트맵 상자(`cell_w x cell_h` 픽셀). |
| **커버리지** (coverage) | 픽셀이 잉크로 덮인 정도(0..255). 1 bpp 잉크 픽셀은 255, 2 bpp 레벨 `k`는 `k * 85`, 8 bpp 픽셀은 해당 바이트 값 그대로다. |
| **기준선 / 어센트** (baseline / ascent) | 여러 페이스를 수직으로 정렬하는 기준 행. 어센트는 셀 상단에서 기준선까지의 행 수이며, 셀의 맨 위 행은 `y_baseline - ascent + dy`다. |
| **전진 폭** (advance) | 글리프를 그린 뒤 다음 글리프를 위해 펜(커서)이 이동하는 거리. 실제 잉크 폭과 다를 수 있다. |

## 2. 라이브러리를 빌드에 넣기

라이브러리는 소스 파일 다섯 개, 비공개 헤더 하나, 공개 헤더 하나로 구성되며 외부 의존성이 없다.

    c/include/svf.h
    c/src/svf_face.c  svf_jamo.c  svf_stream.c  svf_draw.c  svf_scale.c   (+ svf_internal.h)

빌드에 넣는 방법은 세 가지다.

1. **소스를 프로그램에 직접 컴파일한다.** 빌드에 `c/src/*.c`를 추가하고 `-I c/include`를 지정한다. 이 문서의 예제도 이 방식을 따른다.

       gcc -std=c99 -I c/include my_app.c c/src/*.c -o my_app

2. **제공된 Makefile로 정적 라이브러리를 빌드한다.** `make -C c`를 실행하면 `c/build`에 `libsvf.a`와 `svfdump` 도구가 생성된다. 출력 경로는 `O=DIR`로 바꿀 수 있다.
3. **벤더링하거나 서브모듈로 추가한다.** 라이브러리 코드는 MIT 라이선스이며, `svf/` 아래의 페이스는 OFL이다([NOTICE.ko.md](../NOTICE.ko.md) 참고). ScummVM 같은 프로젝트는 저장소를 git 서브모듈로 추가한 뒤 자체 빌드 시스템으로 소스를 컴파일할 수 있다.

**가장 중요한 규칙이 하나 있다. `svf.h`를 include하는 모든 소스 파일과 라이브러리 소스는 반드시 같은 `-D` 스위치로 컴파일해야 한다.**
`SVF_JMAP`은 `svf_face` 구조체 크기를 바꾸므로, 스위치가 다른 오브젝트를 섞어 링크하면 메모리가 손상된다. 스위치는 프로젝트 공통 플래그 변수나 강제 include 헤더 한곳에 모아 관리한다.

데스크톱(`__unix__`, `_WIN32`, `__APPLE__`을 정의하는 컴파일러), DOS(`__DJGPP__`), WASM(`__EMSCRIPTEN__`) 빌드에서는 스위치를 따로 줄 필요가 없다. 기본적으로 모든 타깃 유형, 스트리밍, 스케일링, 모든 자모 블록 버전이 켜져 있으므로, 특정 기능을 *뺄* 때만 스위치를 지정한다. **그 밖의 타깃에는 소형 장치용 기본값이 적용된다.** MCU, 베어메탈, 또는 위 매크로를 하나도 정의하지 않는 컴파일러에서는 버전 3(JMAP, LIST) 자모 블록과 BIG 확장 한도가 꺼진다. 따라서 이 기능이 필요한 페이스는 조합 기능 없는 일반 페이스로 열린다. 필요한 기능은 `-DSVF_JMAP=1`처럼 명시적으로 켜야 하며(12절), 데스크톱에서도 `-DSVF_SMALL`을 주면 같은 효과가 적용된다(12절).

### 2.1 CMake와 Makefile에서 설정하기

CMake에서는 라이브러리 타깃의 컴파일 정의를 `PUBLIC`으로 전파해야 앱과 라이브러리의 구조체 크기가 일치한다.
`SVF_ROOT`에는 SVF 소스 디렉터리의 절대 경로를 지정한다. 아래 예제는 라이브러리만 단독으로 빌드한다.

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

자체 Makefile에서는 앱과 다섯 개 C 소스에 동일한 `CPPFLAGS`를 적용한다. 제공된 `c/Makefile`은 `CFLAGS`로 정의를 받는다. Arduino는 포트 빌드 스크립트나 전역 extra flags에, ESP-IDF는 `${COMPONENT_LIB}`에 정의를 둔다. Pico SDK에서는 SDK 초기화와 별개로 앱 타깃의 `target_compile_definitions`를 사용하며 `CMAKE_C_FLAGS`는 덮어쓰지 않는다. 각 포트의 정확한 명령은 13절을 따른다.

## 3. 완전한 첫 번째 프로그램

아래 프로그램은 페이스 파일을 열어 한글과 라틴 문자가 섞인 한 줄을 8비트 버퍼에 그린 뒤 텍스트로 출력한다. `ex1.c`로 저장한다.

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

저장소에 포함된 페이스로 빌드하고 실행한다.

    gcc -std=c99 -Wall -Wextra -I c/include ex1.c c/src/*.c -o ex1
    ./ex1 svf/dos/NEODG16A.SVF

실행 결과다. 16x16 자모 세트 페이스이므로 한글은 그릴 때 자모 조각을 조합해 만든다.

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

코드의 핵심 동작을 단계별로 살펴본다.

- `svf_open_mapped`는 헤더·테이블·레코드 범위를 모두 검증한다. 기본 검증 설정으로 열린 페이스는 안전하게 그릴 수 있으며, 파일이 거부되면 반환값으로 이유(`SVF_E_MAGIC`, `SVF_E_VERSION` 등)를 알려 준다.
- `svf_measure_utf8`는 글리프를 읽지 않고 줄의 치수(`svf_extent`)를 계산한다. `e.width`는 실제 잉크 폭이 아니라 **펜이 이동한 총 거리**(각 글리프의 전진 폭 합)다. `e.ascent`와 `e.descent`는 잉크가 있는 행만이 아니라 셀 전체가 기준선 위아래로 차지하는 행 수다. 이 예제에서는 64 x (12 + 4)이며, `dy`가 있는 글리프는 수직 이동량도 반영한다. `e.width`는 최대 32,767에서 포화되므로 긴 줄은 나누어 처리한다.
- 버퍼 폭을 `e.width + 2`가 아니라 `e.width + svf_cell_w(&face) + 2`로 잡은 이유도 여기에 있다. 글리프 잉크가 전진 폭 너머로 나갈 수 있어(측정 기준 PAPLG16의 `f`는 3픽셀 더 나간다) 마지막 셀에 최대 셀 폭만큼 더 필요하고, 줄 맨 앞의 결합 부호는 `x`보다 왼쪽에서 시작할 수 있다. 라이브러리가 타깃 영역에 맞춰 클리핑하므로 버퍼가 작아도 메모리는 손상되지 않고 바깥쪽 잉크만 잘린다.
- `svf_draw_utf8`에 넘기는 기준선 행은 `1 + e.ascent`다. 측정된 어센트에 위쪽 여백 1픽셀을 더한 값이다.
- 타깃 버퍼에는 `rows * stride` 이상의 `buf_len`이 필요하다. `svf_target_init`는 버퍼가 부족하거나, 요청한 타깃 유형이 빌드에 빠져 있거나, stride가 너무 작으면 `SVF_E_ARG`를 반환한다.

## 4. 페이스: 매핑 방식과 스트리밍 방식

페이스를 여는 방식은 두 가지다. 일단 페이스를 열고 나면 이후의 모든 API 호출은 동일하다.

<a id="41-매핑-방식-파일-전체가-주소-지정-가능하다"></a>
### 4.1 매핑 방식: 파일 전체를 메모리에 올려 두고 읽기

    svf_err svf_open_mapped(svf_face *f, const uint8_t *data, size_t len);

페이스가 RAM, 플래시(`const` 배열), PROGMEM에 있을 때 사용한다. 라이브러리는 `data`를 복사하지 않고 **직접** 읽는다. 페이스를 사용하는 동안 그 바이트가 유효하고 변하지 않도록 유지해야 한다(그릴 때는 글리프 레코드를 다시 검증하지 않는다). AVR에서는 모든 페이스 읽기가 `pgm_read_byte`를 거치도록 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`를 주고 빌드한다.

데스크톱에서는 3절처럼 파일을 힙 버퍼로 `fread`하거나 `mmap`으로 매핑해 쓴다. 페이스를 쓰는 동안 버퍼를 해제하지 않는다.

<a id="42-스트리밍-방식-파일이-디스크-sd-카드-또는-네트워크에-남는다"></a>
### 4.2 스트리밍 방식: 파일을 디스크·SD 카드·네트워크에 둔 채 읽기

    size_t svf_stream_tables_size(svf_read_fn rd, void *ctx, uint32_t file_len, svf_err *err);
    svf_err svf_open_stream(svf_face *f, svf_read_fn rd, void *ctx, uint32_t file_len,
                            uint8_t *tables, size_t tables_len,
                            uint8_t *cache, size_t cache_len, uint16_t block_size);

읽기 콜백, 파일의 테이블(헤더·코드 포인트 테이블·메트릭·자모 블록·글리프 오프셋 테이블)을 담을 버퍼, 그리고 선택적으로 블록 캐시를 넘긴다. 글리프 픽셀 행은 실제로 그릴 때 읽는다. DOS 포트가 이 방식을 사용하므로 1 MiB 페이스라도 1 MiB의 RAM이 필요하지 않다.

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

스트리밍 사용 시 알아 둘 규칙은 다음과 같다.

- `svf_stream_tables_size`는 `tables` 버퍼에 필요한 바이트 수를 반환한다. 이 크기는 페이스 구성과 빌드에 포함된 리더에 따라 달라진다. 측정값 기준으로 자모 페이스 `NEODG16A.SVF`는 8,153바이트, 완성형 `NEODG16.SVF`는 46,492바이트다.
- 블록 캐시는 선택 사항이며 `cache_len`에 0을 넘기면 사용하지 않는다. 캐시를 주면 라이브러리는 `block_size`바이트(64~4096 사이의 2의 거듭제곱) 단위로 읽고 최근 사용한 블록을 유지한다. 슬롯 하나는 `block_size + 8`바이트이며 최소 두 슬롯이 필요하다. `cache_len`에는 `sizeof cache`를 넘긴다.
- 페이스는 호출자의 `tables`, `cache`, `rd`, `ctx` 포인터를 참조하므로 사용이 끝날 때까지 해제하지 않는다. 또한 같은 스트리밍 페이스를 여러 스레드에서 동시에 그려서는 안 된다.
- 읽기에 실패하거나 요청 길이보다 적게 읽히면 실패는 그리던 글리프에만 영향을 주며, 줄을 끝까지 그린 뒤 `SVF_E_IO`가 반환된다. 잘못된 레코드를 읽으면 `SVF_E_RANGE`가 반환될 수도 있다. `svf_stream_reads(&face)`는 콜백 호출 횟수를 세므로 캐시 크기를 조정할 때 유용하다.
- 블록 캐시 **없이** 스트리밍 페이스의 음절을 조합하려면 `2 * svf_cell_bytes`의 스크래치가 필요하다(뒤쪽 절반에 읽고 있는 조각을 담는다). `svf_chain_scratch_bytes`가 이를 자동으로 반영한다.
- `-DSVF_NO_STREAM`으로 빌드하면 스트리밍 함수의 선언과 정의가 모두 빠진다. 이 상태에서 호출하면 엄격한 경고 설정에서 컴파일 오류가 나거나 링크에 실패한다.

외부 SPI 플래시도 같은 스트리밍 인터페이스로 연결한다. `ctx`에 장치 상태를 두고 `rd` 콜백이 파일 시작 기준 `off`에서 `len`바이트를 읽도록 구현한다. 성공하면 정확히 `len`을, 실패하면 음수나 `len`보다 작은 값을 반환한다. 메모리 매핑을 지원하는 플래시라면 5절의 `const` 배열처럼 `svf_open_mapped`로 읽는 편이 간단하다.

<a id="43-페이스가-알려-주는-것"></a>
### 4.3 페이스 정보와 상태 확인하기

페이스를 연 뒤에는 조회 함수로 헤더 정보를 확인할 수 있다(`svf_bpp`, `svf_cell_w`, `svf_cell_h`, `svf_ascent`, `svf_glyph_count`, `svf_flags`).
`svf_has(f, cp)`는 페이스가 해당 코드 포인트를 그릴 수 있는지(저장된 글리프, 조합 가능한 음절, 호환 자모)를 알려 준다.
`svf_metrics_of(f, cp, &m)`는 글리프의 전진 폭(advance), 베어링, 잉크 너비, 수직 오프셋을 반환한다.

놓치기 쉽지만 중요한 함수가 `svf_status(f)`다. 열기 자체가 성공하더라도 무엇이 무시되거나 바뀌었는지 알리는 **상태 비트**가 설정될 수 있다. 예를 들어 `SVF_FACE_JSET_BAD`는 자모 블록이 검증에 실패했다는 뜻이며, 이때 페이스는 조합 기능 없는 일반 페이스로 열린다. `SVF_FACE_JSET_UNREAD`는 버전 1·2 헤더는 유효하지만 이 빌드에 해당 리더가 없음을 뜻한다. 한글 음절이 나오지 않을 때 가장 먼저 확인할 값은 `svf_status(f)`가 0인지 여부다(16절).

열기 반환값이 `SVF_OK`라도 아래 상태 비트가 함께 켜질 수 있다. 저장된 글리프는 그대로 그릴 수 있으므로 앱에 필요한 문자는 `svf_has`로 확인하고, 진단 로그에는 오류 코드와 상태를 함께 남긴다.

| 상태 | 의미 |
|---|---|
| `SVF_FACE_CMAP_LINEAR` | 정렬되지 않았거나 중복된 코드 포인트가 있음. 선형 조회를 사용하며 중복 시 마지막 항목을 선택. |
| `SVF_FACE_DY_IGNORED` | 잘못된 dy 범위를 무시. |
| `SVF_FACE_METRICS_DROPPED` | 메트릭 영역을 무시하고 셀 폭을 전진 폭으로 사용. |
| `SVF_FACE_JSET_BAD`, `SVF_FACE_JMAP_BAD` | 잘못된 조합 블록. 세부 폴백 규칙은 [명세](../spec/SVF.ko.md#검증) 참고. |
| `SVF_FACE_JSET_UNREAD`, `SVF_FACE_JMAP_UNREAD` | 빌드에서 해당 리더가 꺼져 있음. 지원되는 폴백이 있으면 사용. |

## 5. 페이스 내장하기

마이크로컨트롤러에는 파일 시스템이 없거나, 파일 시스템 의존성을 피하고 싶은 경우가 많다. 페이스 하나만 쓰는 프로그램도 바이너리에 직접 내장하는 편이 간단하다. `c/bench/mkface.py`를 쓰면 페이스를 C 배열로 변환할 수 있다.

    python3 -I c/bench/mkface.py svf/dos/NEODG16G.SVF face.c --name neodg16g --profile mcu-strict

실행에는 Python 3과 `tools/jamoset.py`가 필요하다. 스크립트 위치를 기준으로 모듈 경로를 찾으므로 다른 작업 디렉터리에서도 실행할 수 있다(아래 파일 경로는 프로젝트 루트 기준). `--name`에는 유효한 C 식별자를 지정한다.

생성된 `face.c`는 `const uint8_t neodg16g[]`와 `const uint32_t neodg16g_len` 두 심벌을 공개한다. AVR에서는 배열에 `PROGMEM`이 붙으며, 메모리 정렬은 선택한 레이아웃을 따른다.

- 배열을 플래시에 배치하는 링커 설정에서는 RAM 사본 없이 직접 읽는다. AVR에서는 `PROGMEM`으로 플래시 전용 주소 공간에 배치하고, 라이브러리가 `SVF_RD8`을 통해 읽는다(4.1절). `NAME_len`은 페이스의 바이트 크기이며 두 심벌을 함께 `svf_open_mapped`에 넘긴다.
- `aligned(A)`의 `A`는 기록된 레이아웃의 `2^max(REC, TAB)`바이트다(`mcu-strict`는 4, 1이면 생략). 덕분에 파일 안의 레코드 오프셋이 곧 주소 정렬과 일치한다. 단, 정렬은 **속도에만** 영향을 준다. `svf_open_mapped`는 *파일 내부* 오프셋 정렬만 검사할 뿐 배열 시작 주소는 따지지 않으므로, 홀수 주소에 놓여도 정상적으로 열리고 그려진다.
- `--profile mcu-strict`는 페이스를 `SVF_LAYOUT_MCU_STRICT` 레이아웃(레코드·테이블 단위 4바이트, 행 단위 1바이트, 16비트로 표현 가능한 오프셋은 16비트로 축소)으로 다시 기록한다. 픽셀 출력은 원본과 같다. 배포된 117개 페이스는 모두 4/1/4바이트 레이아웃을 쓰므로 `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT` 빌드에서도 원본을 그대로 열 수 있다. 이 프로파일은 오프셋만 줄여 주며, NEODG16G의 경우 10,684바이트에서 10,124바이트로 작아진다. `--profile`을 생략하면 원본 파일의 바이트가 그대로 담긴다. 반면 `dos`·`wasm` 프로파일(1/1/1바이트 레이아웃) 페이스는 `MCU_STRICT` 전용 빌드에서 `SVF_E_LAYOUT`으로 거부된다.
- **내장 페이스 생성에는 반드시 `mkface.py`를 사용한다.** 기본 `xxd -i` 출력은 `const`가 없는 `unsigned char name[]`을 만들어 링크 시 RAM 사본이 생길 수 있다. AVR용 `PROGMEM`과 레이아웃 정렬도 따로 지정해야 한다.

<a id="51-배열이-가는-곳-플랫폼별"></a>
### 5.1 플랫폼별 배열 배치 위치

| 타깃 | 페이스가 있는 곳 | 비고 |
|---|---|---|
| AVR(Arduino Uno) | `PROGMEM` 플래시 | 라이브러리를 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드한다. `SVF_RD8`이 없으면 플래시 주소를 RAM으로 읽어 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환한다. `svf_draw_utf8`에 넘기는 텍스트는 일반 메모리 읽기로 처리하므로 RAM에 둔다(`PROGMEM` 문자열은 `strncpy_P`로 먼저 복사). |
| 그 밖의 Arduino 코어(ARM, ESP32, RP2040) | 플래시의 `const` 배열 | 플래시가 메모리에 매핑되어 있어 `SVF_RD8` 재정의와 `PROGMEM`이 모두 필요 없다(`mkface`는 `__AVR__`에서만 `PROGMEM`을 붙인다). |
| ESP32(ESP-IDF) | 플래시 `.rodata`의 `const` 배열, **또는** `esp_partition_mmap`으로 매핑한 데이터 파티션, **또는** 스트리밍하는 SPIFFS 파일 | 데이터 파티션을 쓰면 페이스가 앱 이미지와 그 크기에서 빠진다. SPIFFS + `svf_open_stream`은 메모리 매핑 주소 공간도 차지하지 않는다(13.4절). |
| Raspberry Pi Pico / Pico 2 | 플래시의 `const` 배열(XIP) | XIP 캐시를 통해 읽는다. 블록에 처음 접근할 때 플래시 읽기가 발생한다(13.5절). |
| CH582 | CodeFlash의 `const` 배열 | 링커가 `.rodata`를 플래시에 배치하므로 RAM 사본이 생기지 않는다. |
| DOS, SDL, 데스크톱, WASM | 메모리에 읽어 들인 파일(`fread`, `SDL_LoadFile`, 모듈로 복사한 JavaScript `Uint8Array`), 또는 `mmap` | 4.2절처럼 파일에서 스트리밍할 수도 있다. 버퍼는 페이스를 사용하는 동안 유지해야 한다. |

<a id="52-연-뒤에-페이스를-확인하라"></a>
### 5.2 페이스를 연 뒤 상태 확인하기

`svf_open_mapped`가 성공해도 파일 구조가 유효할 뿐, 현재 빌드가 해당 페이스의 한글을 조합할 수 있다는 보장은 없다. 초기화할 때 한 번 두 가지를 모두 확인한다. 아래 `text_cb.c` 예제는 호스트와 Cortex-M0+에서 바로 컴파일되며, 13.1절의 Uno 플래그에서 `-DSVF_TARGETS=0x10`으로 바꾸면 AVR에서도 빌드된다(콜백 타깃을 쓰므로 `0x02`로 빌드하면 `text_init`이 -3을 반환한다).

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

한글을 조합하는 페이스라면 `svf_is_jamo`가 1을 반환하고, 무시된 블록이 없을 때 `svf_status`가 0이다(4.3절). 조합 블록을 쓰지 못하더라도 저장된 글리프는 그릴 수 있다. `JMAP_UNREAD`가 켜져 있어도 지원되는 폴백 블록이 있으면 조합이 동작하므로, 이 비트만으로 일반 페이스라고 단정할 수는 없다. 완성형 페이스에는 자모 블록이 없으므로 대신 `svf_has(&face, 0xD55C)`로 한글 지원 여부를 확인한다.

`text_cb.c`를 `face.c`와 함께 빌드해 실행한다. 호스트 예제에서는 켜진 픽셀 수를 세는 것으로 대체했지만, 실제 장치에서는 디스플레이 출력 루틴으로 바꾸면 된다.

```sh
cc -std=c99 -Wall -Wextra -Ic/include text_cb.c face.c c/src/*.c -o text_cb
./text_cb
# status=0 width=64 ink=248
```

### 5.3 C++와 Arduino: `face.c`는 C 파일로 둔다

배열은 `.c` 파일로 생성해 C 컴파일러로 빌드한다. C++에서는 네임스페이스 범위의 `const` 배열에 외부 링키지를 명시하지 않으면 내부 링키지를 가지므로 다른 소스 파일(컴파일 단위)에서 참조할 수 없다.[9] Arduino 빌드는 스케치 폴더의 `.c` 파일을 C로 컴파일한다. C++ 코드에서는 `c/ports/arduino/arduino.ino`처럼 `extern "C"`(C 링키지)로 선언한다.

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

페이스를 포함한 프로그램이나 펌웨어 이미지는 폰트 소프트웨어를 배포하는 셈이다.[10] 따라서 다음 파일을 함께 배포해야 한다.
- 페이스 자체의 라이선스 문서(NEODG16G는 `svf/dos/OFL.TXT`와 `svf/dos/NEODGM.TXT`, PAPLG16·PAPLG18은 `svf/dos/OFLPAPLG.TXT`. `svf/` 아래 전체 페이스의 라이선스 매핑은 `web/LICENCES.tsv` 참고)
- [NOTICE.ko.md](../NOTICE.ko.md)(구성 요소별 라이선스 안내)
- [LICENSE](../LICENSE)(라이브러리 코드의 MIT 라이선스)

포트가 내장하는 각 페이스의 출처·저작권·라이선스는 `c/ports/FACES.md`에 정리되어 있으며, Pico·ESP32·CH582 빌드는 이 파일과 라이선스 문서를 `<build>/licences/`에 자동으로 복사한다.

## 6. 타깃에 맞는 페이스 고르기

페이스가 장치에 들어갈지는 픽셀 크기가 아니라 파일 크기가 결정한다. 사용할 페이스의 크기를 직접 확인한다.

    python3 -I c/bench/mkface.py svf/dos/NEODG16A.SVF x.c --name x --profile mcu-strict && tail -2 x.c

마지막 줄의 `const uint32_t x_len = 15528u;`가 아래 표의 숫자, 즉 실제 링크되는 바이트 크기다. 아래 표의 배열 바이트는 `mcu-strict` 출력 기준이며, 스트리밍 테이블은 원본 파일과 기본 호스트 빌드 기준 측정값이다.

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

- **한글.** 표의 자모 세트 페이스는 조각을 조합해 글자를 만들며, 지원 음절 범위는 조합 블록 구성에 따라 달라진다(10절). 반면 완성형 페이스는 지원하는 음절마다 글리프를 따로 저장한다. 배열 크기 기준으로 `NEODG16`은 `NEODG16A`의 약 8.24배다. 소형 장치에는 필요한 음절을 지원하는 자모 페이스가 유리하다.
- **Uno.** ATmega328P의 SRAM은 2 KiB다.[3] 표의 가능 여부는 플래시에 내장하는 구성을 전제로 한다. 최종 코드, 페이스, 전역 데이터, 스택 크기를 함께 확인하며, AVR 플래시 읽기와 빌드 스위치는 13.1절을 따른다.
- **CH582.** 포트의 `link.ld`는 플래시 448 KiB와 RAM 32 KiB를 배정한다. 페이스뿐 아니라 코드와 플래시에서 RAM으로 복사되는 데이터도 함께 계산해야 한다.
- **Pico.** Pico 보드는 플래시 2 MiB, Pico 2는 4 MiB를 제공한다.[6] 표의 페이스는 모두 용량 안에 들어가지만 최종 바이너리 전체 크기를 확인해야 한다.
- **ESP32.** 앱에 내장할 수 있는 크기는 선택한 파티션 표에 달려 있다. 위 표는 1 MiB 앱 파티션 기준이며 `GBATB47`은 페이스만으로 이를 넘는다. 더 큰 앱 파티션이나 별도 데이터 파티션을 사용한다(13.4절).[5]
- **스트리밍**(SD, SPIFFS, 디스크 파일)에는 테이블용 RAM(위 표의 원본 파일 기준)과 선택적 블록 캐시가 필요하다. Uno에서는 스트리밍을 쓸 수 없다(`NEODG16G`만 해도 테이블이 5,129바이트이고, Uno 빌드에는 리더가 빠진다).
- 그리기에 필요한 **RAM**은 적다. 스케일링하지 않는 매핑 페이스는 셀 하나 크기(`셀 바이트`, 11절)의 스크래치와 프레임버퍼만 있으면 된다. 스케일링하거나 블록 캐시 없이 스트리밍하면 스크래치가 더 필요하다(9절, 11절).

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

각 코드 포인트는 `svf_has`가 참인 첫 번째 페이스가 그린다. 따라서 체인 순서가 중요하다. 숫자나 구두점처럼 여러 페이스에 공통으로 들어 있는 문자에 원하는 스타일을 쓰려면 그 페이스를 앞쪽에 배치한다. `chain.faces`가 `NULL`이거나 `count`가 0이거나 항목 중 하나라도 `NULL`이면 체인은 "페이스 없음" 상태가 된다. 이 체인으로 호출하면 아무것도 그리지 않고 `SVF_E_ARG`를 반환한다.

완전한 체인 예제는 `./chain svf/dos/NEODG16A.SVF svf/dos/PAPLG16.SVF`로 실행한다. 두 번째 인자를 생략하면 같은 파일을 두 번 열어 호출 흐름만 확인한다.

### 7.2 결합 부호, 전진 폭, 잘못된 UTF-8

- 전진 폭(advance)은 페이스의 메트릭 테이블에서 가져온다(가변 폭). 메트릭 테이블이 없는 페이스는 셀 폭만큼 전진한다. 조합된 한글 음절은 자모 블록의 음절 전진 폭(없으면 셀 폭)만큼 전진한다.
- 지원하는 결합 부호는 펜을 전진시키지 않는다. 현재 펜 위치에 그리되, 페이스 플래그 비트 2가 켜져 있고 `bearing_x < 0`이면 `min(-bearing_x, cell_w)`만큼 왼쪽으로 옮긴다. 기본 결합 부호 범위는 U+0300..U+036F이며, 다른 범위를 쓰려면 `chain.is_mark` 콜백을 지정한다. 어떤 페이스에도 없는 코드 포인트는 결합 부호라도 `missing_advance`만큼 전진한다.
- 잘못된 UTF-8 입력이 들어와도 크래시하지 않으며 `len` 바깥을 읽지 않는다. 잘못된 바이트 구간마다 체인의 어떤 페이스에 U+FFFD가 있으면 그 글리프를 그리고, 없으면 전진 없이 건너뛴다. NUL 문자도 일반 코드 포인트로 취급한다(C 문자열 끝으로 보지 않고 정확히 `len`바이트를 처리한다).

### 7.3 그리기 전에 측정하기

`svf_measure_utf8(&chain, s, len, &e)`는 실제 그리기와 똑같은 레이아웃 규칙으로 `e.width`, `e.ascent`, `e.descent`를 계산한다. 글리프 픽셀을 읽지 않으므로 비용이 적고 스트리밍 페이스에서도 I/O가 발생하지 않는다. 가운데·오른쪽 정렬, 단어 줄바꿈, 출력 버퍼 크기 산정에 활용한다.

주의할 점은 `e.width`가 잉크의 끝이 아니라 **펜이 이동한 총 거리**라는 것이다. 마지막 셀이 그 너머로 최대 셀 폭만큼 더 뻗을 수 있으므로 버퍼 크기를 잡을 때는 `svf_cell_w(face)`를 더한다(3절). 단어 분리와 줄바꿈은 호출자의 몫이다. 라이브러리는 한 번에 한 줄만 그리며 줄바꿈을 처리하지 않는다.

<a id="8-타깃-픽셀이-가는-곳"></a>
## 8. 타깃: 픽셀 출력 버퍼와 콜백

타깃은 각 픽셀의 커버리지를 원하는 출력 포맷으로 변환해 기록한다. 타깃 유형은 `svf_target_init`로 지정한다.

    svf_err svf_target_init(svf_target *t, svf_target_kind kind, uint8_t *buf, size_t buf_len,
                            int16_t w, int16_t h, uint16_t stride);

| 출력 대상 | 타깃 유형 | 비고 |
|---|---|---|
| 32비트 프레임버퍼 또는 SDL 서피스(메모리 순서 B, G, R, X. 리틀 엔디언에서는 32비트 값 `0x00RRGGBB`) | `SVF_T_XRGB8888` | `t.fg888`, `t.bg888`을 `0x00RRGGBB`로 설정 |
| 24비트 | `SVF_T_RGB888` | 같은 필드 사용 |
| 16비트 컬러 LCD | `SVF_T_RGB565` / `SVF_T_RGB555` | `t.fg565`, `t.bg565`. 상위 바이트 우선이면 `t.flags`에 `SVF_TF_RGB16_BIGENDIAN` 설정(옛 이름 `SVF_TF_565_BIGENDIAN`과 같은 비트) |
| 팔레트 모드(VGA 모드 13h, VBE 8 bpp, SDL CLUT8) | `SVF_T_INDEXED8` | `t.index_base`, `t.index_levels`로 사용할 팔레트 구간 지정 |
| SSD1306 페이지 | `SVF_T_MONO_PAGE` | `buf[(y >> 3) * stride + x]`의 비트 `y & 7` |
| 1 bpp 비트맵 행 | `SVF_T_MONO_ROW` | MSB 우선 |
| 1/2/4/8비트 그레이스케일 | `SVF_T_GRAY` | `t.gray_bits`. MSB 우선, 또는 `SVF_TF_GRAY_LSB_FIRST` |
| 픽셀당 커버리지 1바이트 | `SVF_T_GRAY8` | 직접 합성할 때 쓰는 마스크 |
| **그 밖의 모든 포맷** | `SVF_T_COVERAGE_CB` | 콜백이 `(x, y, coverage)`를 받음 |

타깃 유형별 기존 픽셀 처리 규칙은 `svf.h`의 `svf_target` 주석에 정확히 정의되어 있다. 핵심을 요약하면 다음과 같다.

- 컬러 타깃(`RGB565`, `RGB555`, `XRGB8888`, `RGB888`)은 **기존 픽셀을 읽지 않는다.** `bg`와 `fg`를 커버리지 비율로 섞어 덮어쓰므로 `bg`에는 실제 배경색을 넣어야 한다. 단색 배경 위에서만 컬러 타깃을 쓰고, 기존 화면 내용 위에 블렌딩해야 하면 콜백 타깃을 사용한다.
- `GRAY8`, `INDEXED8`, `GRAY`는 기존 값과 새 값 중 최댓값을 유지한다. `INDEXED8`에서는 기존 인덱스가 잉크 인덱스보다 낮아야 글자가 보이므로, 배경 인덱스를 잉크용 팔레트 구간(`index_base + 1 .. index_base + index_levels`)보다 작은 값으로 둔다.
- `MONO_*`는 커버리지가 `t.mono_threshold`(기본값 128) 이상일 때 비트를 1로 켜며, 기존 비트를 0으로 지우지 않는다.
- 클리핑 영역(`t.clip_x0..clip_y1`, 끝점 미포함 `[x0, x1)`, 기본값은 타깃 전체) 안쪽 픽셀만 기록한다. 이웃 픽셀의 바이트(같은 바이트를 공유하는 픽셀의 비트 포함)나 행 패딩은 건드리지 않는다.

2 bpp 단계가 타깃 유형마다 어떤 색으로 변환되는지(블렌딩 식, 반올림, 단계별 단색 임계값)와 디스플레이별 bpp 선택 기준은 그림과 함께 [안티앨리어싱](anti-aliasing.ko.md#23-단계가-색이-되는-과정)에 정리되어 있다.

<a id="81-32비트-서피스-위의-컬러-텍스트"></a>
### 8.1 32비트 서피스에 컬러 텍스트 그리기

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

`stride`는 바이트 단위 `uint16_t`이므로 32비트 타깃의 최대 폭은 16,383픽셀이다. 픽셀의 **메모리 바이트 순서는 모든 호스트에서 B, G, R, X**다.
네이티브 32비트 정수로 읽었을 때 `0x00RRGGBB`가 되는 것은 리틀 엔디언 호스트에서뿐이며, 코어는 빅 엔디언 호스트에서도 동일한 네 바이트 순서로 기록한다.

### 8.2 콜백 타깃: 만능 어댑터

픽셀 포맷이 기본 지원 목록에 없거나, 기존 화면 내용 위에 알파 블렌딩하고 싶거나, 다른 라이브러리의 서피스에 직접 그려야 할 때 콜백 타깃을 사용한다.
라이브러리는 별도 버퍼 없이, 클리핑 영역 안에서 커버리지가 0보다 큰 픽셀마다 셀별·행 단위로 `plot(ctx, x, y, coverage)`를 한 번씩 호출한다. 아래 예제는 32비트 서피스의 기존 픽셀 위에 흰색 텍스트를 블렌딩한다(B, G, R, X 메모리 순서로 바이트 단위로 읽고 쓴다).

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

`plot`은 그리기 전에 반드시 설정해야 하며, 비어 있으면 `SVF_E_ARG`를 반환한다. 결합 부호가 기본 글자 위에 얹혀 두 셀이 같은 픽셀에서 겹치면 콜백이 셀마다 한 번씩 호출되므로 블렌딩 콜백은 둘을 모두 합성하며, 이것이 의도된 동작이다.

## 9. 스케일링

배율은 `chain.scale_num`과 `chain.scale_den`으로 지정한다(각각 1..16, 둘 다 0이면 1/1). 정수 배율(`2/1`, `3/1`)은 원본 픽셀 하나를 N x N 블록으로 확대하므로 비트맵 가장자리가 선명하게 유지된다. 그 밖의 비율은 영역 평균으로 8비트 커버리지를 계산하므로, 1 bpp 페이스를 `3/2`로 확대하면 가장자리에 회색 픽셀이 생긴다(이때는 컬러나 그레이스케일 타깃을 쓴다. 단색 타깃에서는 임계값이 결정한다). 길이는 대칭 반올림(0.5 올림)으로 스케일되므로 `svf_measure_utf8`의 측정 결과와 실제 그려진 크기가 일치한다. `x`, `y_baseline`, 클리핑 영역은 항상 출력 픽셀 단위다.

스케일링을 켜면 스크래치 크기가 커진다. 체인에서 가장 큰 페이스를 기준으로 **저장된 셀 크기의 두 배에 스케일된 셀 크기를 더한 만큼**이 필요하다.

    scratch = 2 * svf_cell_bytes(face) + ceil(cell_w * num / den) * ceil(cell_h * num / den)

스케일된 셀은 8비트 커버리지(픽셀당 1바이트)로 저장한다. 이 공식은 매핑 페이스와 스트리밍 페이스, 그리고 블록 캐시 유무와 관계없이 동일하다(1/1에서는 셀 하나, 캐시 없는 스트리밍 페이스는 셀 둘). `svf_chain_scratch_bytes`가 이 값을 계산하므로 배율을 바꾼 뒤에는 반드시 다시 호출한다. 16x16 1 bpp `NEODG16A`(셀 32바이트)의 측정값은 `3/2`가 `2 x 32 + 24 x 24 = 640`바이트, `2/1`이 `2 x 32 + 32 x 32 = 1,088`바이트, `1/2`이 `2 x 32 + 8 x 8 = 128`바이트다.

소형 MCU 빌드에서는 `-DSVF_NO_SCALE`로 스케일링 코드를 완전히 제거할 수 있다(이때 `n/n` 이외의 비율은 `SVF_E_ARG`를 반환한다). 기본 빠른 스케일러의 스택 프레임은 약 610~680바이트이므로 2 KB RAM 칩에서 쓰기 전에 `svf.h`의 "Scaling" 주석을 확인한다.

## 10. 한글: 자모 페이스와 음절 조합

**완성형** 페이스는 지원하는 음절마다 글리프를 하나씩 저장한다. 반면 **자모 세트(jamo-set)** 페이스(헤더 플래그 비트 1, `svf_is_jamo(f)`)는 수백 개의 작은 자모 조각과, 각 음절에 어떤 조각을 조합할지 기록한 테이블을 저장한다. `svf_draw_utf8`는 이 조각들로 완성형 음절 `U+AC00..U+D7A3`과 호환 자모 `U+3131..U+3163`을 즉석에서 조합한다. 음절은 두세 조각의 픽셀별 커버리지 최댓값을 취해 합치고, 호환 자모는 지정된 한 조각을 그대로 쓴다. 호출자가 따로 처리할 일은 없으며, 일반 UTF-8 문자열처럼 한글을 넘겨 그리면 된다.

단, 음절 테이블이 전체 11,172자가 아니라 일부만 담을 수 있다는 점에 유의한다. SPARSE(비트맵 + 항목 목록) 또는 LIST(최대 255개 예외의 정렬 목록) 형식의 버전 3 JMAP 블록에 **폴백 블록이 없으면** 목록에 들어 있는 음절만 조합한다. 목록에 없는 음절은 `svf_has`가 0을 반환하며 잉크 없이 `missing_advance`만큼만 전진한다. 유효하고 빌드에서 지원하는 폴백 블록이 함께 있으면 목록에 없는 음절은 폴백으로 처리한다. 조밀한(dense) JMAP과 버전 1·2 블록은 한글 11,172자 전체를 지원한다.

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

`svf_glyph`와 `svf_compose`는 타깃 없이 코드 포인트 하나의 셀 비트맵만 반환한다. 애플리케이션 자체의 글리프 아틀라스에 캐시할 때 유용하다.

<a id="101-사용자의-빌드가-읽는-것"></a>
### 10.1 빌드 설정에 따른 자모 블록 지원 범위

자모 블록에는 버전 1, 2, 3(LIST 형식 포함 JMAP)이 있다. 기본 데스크톱·DOS·WASM·SDL 빌드는 세 버전을 모두 읽는다(단, `-DSVF_SMALL`에서는 제외, 12절). 소형 MCU 빌드는 지원 범위가 더 좁다([c/README.ko.md](../c/README.ko.md)의 "자모 세트: 각 빌드가 읽는 것" 표 참고). 조합 블록을 읽지 못하면 해당 상태 비트가 켜지며, 지원하는 JSET 폴백이 있으면 폴백으로 조합하고 없으면 **일반** 페이스로 열린다. 페이스를 연 직후 `svf_status`, `svf_is_jamo`, 그리고 필요한 코드 포인트에 대한 `svf_has`를 함께 확인한다.

### 10.2 조합된 음절 캐시

한글 음절을 조합할 때마다 테이블 조회와 조각 병합이 일어난다. UI나 매 프레임 다시 그리는 대화 상자처럼 같은 텍스트가 반복된다면 체인에 음절 캐시를 붙여 비용을 줄인다.

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

캐시를 쓰든 안 쓰든 출력 픽셀은 완전히 같다. 특히 스트리밍 페이스에서 효과가 크다. 캐시된 음절을 다시 그릴 때는 파일 읽기가 전혀 일어나지 않기 때문이다. 다만 라틴 글리프처럼 조합하지 않는 셀은 이 캐시에 들어가지 않으므로 같은 줄을 다시 그려도 읽기가 발생할 수 있다. 음절 캐시는 선형 조회를 쓰는 라운드 로빈 방식이므로, 소형 타깃에는 수십 개 슬롯이 적당하고 수천 개로 늘리는 것은 적합하지 않다. `chain.faces`를 바꾸거나 페이스를 다시 열었다면 `svf_chain_cache`를 다시 호출해야 한다.

## 11. 메모리 예산

모든 메모리는 호출자가 직접 관리한다. 필요한 총량은 아래 항목을 모두 합산해 계산한다.

| 항목 | 크기 |
|---|---|
| `svf_face` | `sizeof(svf_face)`: `SVF_JMAP`이 켜진 64비트 호스트에서 96바이트(끄면 80바이트, MCU에서는 더 작음. 실제 크기는 ABI별로 `sizeof`로 확인) |
| `svf_chain`, `svf_target` | 각각 수십 바이트 |
| 스크래치 | `svf_chain_scratch_bytes(&chain)`: 셀 하나(`svf_cell_bytes`), 블록 캐시 없는 스트리밍 페이스는 두 배. 스케일링 시에는 **셀의 두 배 + 스케일된 셀**(9절) |
| 스트리밍 페이스 | 테이블용 `svf_stream_tables_size(...)`, 선택적 블록 캐시용 `slots * (block_size + 8)` |
| 음절 캐시 | `slots * (8 + 가장 큰 셀 바이트 수)` |
| 타깃 버퍼 | `rows * stride`(콜백 타깃은 0) |
| 매핑된 페이스 | 파일 자체, RAM 또는 플래시(플래시에 배치한 `const` 배열이나 PROGMEM 페이스는 RAM 사본 없음, 5절) |
| 스택 | 스케일러 자체 프레임: 기본 빠른 스케일러 기준 AVR 약 610바이트, Cortex-M0+ 약 680바이트 |

참고로 16x16 1 bpp 셀은 32바이트, 24x24 2 bpp 셀은 144바이트다.

## 12. 컴파일 타임 스위치: 세 가지 레시피

스위치는 **모든** 소스 파일에 동일하게 주는 `-D` 플래그다(2절). 데스크톱 환경에서는 거의 지정할 일이 없다. 대표적인 구성 레시피 세 가지는 다음과 같다.

- **데스크톱, DOS, WASM, SDL, ScummVM급 애플리케이션: 스위치 없음.** 모든 기능이 기본으로 켜져 있다.
- **디스플레이 하나인 소형 MCU:** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_TARGETS=<타깃 비트 하나> -DSVF_JSET_V2=0 -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`를 지정하고, 이에 맞는 프로파일로 페이스를 준비한다(`tools/jamoset.py`의 `mcu-strict`. 배포된 페이스는 이미 이 레이아웃을 쓰며 `c/bench/mkface.py --profile mcu-strict`로 오프셋을 줄일 수 있다, 5절). Arduino Uno 포트가 바로 이 구성을 사용한다([c/ports/arduino/README.ko.md](../c/ports/arduino/README.ko.md) 참고).
- **모든 CPU에서 최소 코드 크기:** `-DSVF_SMALL`을 정의하면 속도 최적화 경로(워드 병합, GRAY8 룩업 테이블, 빠른 스케일러, 니블 popcount 테이블)가 꺼진다. 픽셀 출력은 같고 실행 속도만 느려진다. **단, 지원하는 자모 블록 범위도 함께 바뀐다.** `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG`의 *기본값*이 0으로 바뀌기 때문이다(기본 데스크톱·DOS·WASM 빌드에서는 1). 따라서 데스크톱·DOS·WASM에서도 `SVF_SMALL`로 빌드하면 버전 3(JMAP, LIST) 자모 블록과 BIG 확장 한도를 읽지 못한다. 이 기능이 필요한 페이스는 `SVF_FACE_JSET_BAD`가 켜진(`SVF_FACE_JMAP_UNREAD`는 `-DSVF_JMAP_RECOG=1`일 때만) **일반 페이스**로 열려 한글을 그리지 않는다. 필요하다면 `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`을 함께 지정한다(`SVF_JMAP_LIST`는 `SVF_JMAP`을 따른다).

툴체인별 기본값이 정리된 전체 스위치 표는 [c/README.ko.md](../c/README.ko.md)의 "컴파일 시점 스위치"에, 구성별 바이너리 크기는 `c/cross/SIZES.md`에 있다.

| 매크로 | 기본값과 효과 |
|---|---|
| `SVF_SMALL` | 기본 미정의. 정의하면 빠른 경로를 줄이고 JMAP·BIG 기본값을 비활성화한다. `=0`도 정의된 것으로 처리한다. |
| `SVF_JMAP` | 데스크톱·DOS·WASM에서 1, AVR·MCU·SMALL에서 0. 버전 3 매핑 리더 활성화 여부이며 `svf_face` 크기에 영향을 준다. |
| `SVF_JMAP_LIST` | `SVF_JMAP`을 따름. LIST 리더. `SVF_JMAP` 없이 1로 지정하면 컴파일 오류가 난다. |
| `SVF_JMAP_RECOG` | 데스크톱·DOS·WASM에서 1, MCU·SMALL에서 0. JMAP 리더가 없어도 JMAP을 인식하고 폴백 블록을 사용한다. |
| `SVF_JSET_BIG` | 데스크톱·DOS·WASM에서 1, MCU·SMALL에서 0. 클래스·벌(세트) 한도를 확장한다. |
| `SVF_JSET_V1`, `SVF_JSET_V2` | V1은 1, V2는 AVR에서 0이고 그 외 1. V1·V2·JMAP 중 하나 이상은 켜야 한다. CH582 포트는 V2를 명시적으로 끈다. |
| `SVF_JSET_TRUSTED` | 0. 1은 직접 검증해 내장한 페이스에만 사용하며, 테이블 내용 검증을 생략한다. |
| `SVF_JSET_POP4` | 보통 1, AVR·SMALL에서 0. V2 popcount 구현 방식을 선택한다. |
| `SVF_NO_STREAM`, `SVF_NO_SCALE` | 기본 미정의. 정의하면 해당 기능을 완전히 제거한다. |
| `SVF_LAYOUTS` | 기본은 모든 유효 레이아웃 허용. 예: `SVF_LAYOUT_MCU_STRICT`로 제한. |
| `SVF_TARGETS` | `0x3ff`. 타깃 비트의 OR 조합: GRAY8 `0x001`, MONO_PAGE `0x002`, MONO_ROW `0x004`, RGB565 `0x008`, CB `0x010`, INDEXED8 `0x020`, RGB555 `0x040`, XRGB8888 `0x080`, RGB888 `0x100`, GRAY `0x200`. |
| `SVF_RD8(p)` | 기본 일반 메모리 읽기. AVR PROGMEM에서는 `pgm_read_byte(p)`로 재정의한다. |
| `SVF_MERGE_WORDS`, `SVF_GRAY8_LUT1`, `SVF_SCALE_FAST`, `SVF_WORD_STORE` | CPU·SMALL 설정에 따른 최적화 스위치. 정확한 기본 조건은 [svf.h](../c/include/svf.h) 참고. 픽셀 출력 의미는 동일하다. |

## 13. 플랫폼

각 포트의 빌드 설정과 디스플레이 드라이버를 출발점으로 삼는다. 아래 명령은 모두 저장소 루트에서 실행한다.
빌드가 성공하더라도 실제 패널에서의 출력은 따로 검증해야 한다. 메모리 사용량은 툴체인·SDK·페이스·플래그에 따라 달라지므로 최종 이미지에서 `size`와 링크 맵을 확인한다. 구성별 크기는 [빌드 크기 표](../c/cross/SIZES.md)에 정리되어 있다.

### 13.1 Arduino Uno와 그 밖의 Arduino 코어

Arduino 빌드는 스케치 폴더 안의 `.c` 파일을 C로 컴파일한다.[1] 아래는 Uno용 `MONO_PAGE` 구성이며, `arduino-cli`와 `arduino:avr` 코어가 먼저 설치되어 있어야 한다.

```sh
mkdir -p ~/Arduino/libraries/svf
cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
python3 -I c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
arduino-cli compile -b arduino:avr:uno c/ports/arduino \
    --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"
```

생성한 `face.c`는 `.ino` 옆에 두고, C++ 쪽에서는 5.3절처럼 `extern "C"`(C 링키지)로 선언한다.
`compiler.c.extra_flags`와 `compiler.cpp.extra_flags`에는 같은 플래그를 넘긴다. `build.extra_flags`는 어셈블러에도 전달되므로 `-include avr/pgmspace.h`를 넣는 용도로 쓰지 않는다. AVR에서 `PROGMEM`을 읽으려면 `SVF_RD8` 재정의가 필수다.[2] 그릴 텍스트는 RAM에 두거나 `strncpy_P` 등으로 복사한 뒤 넘긴다.

[arduino.ino](../c/ports/arduino/arduino.ino)는 128 x 64(1,024바이트) 페이지 버퍼에 그린 뒤 `Wire`로 16바이트씩 전송한다.
Uno의 SRAM은 2 KiB뿐이므로[3] 프레임버퍼와 함께 Wire 버퍼, 전역 데이터, 스택 크기를 모두 합산해 확인한다. 위 설정에서는 스케일링과 스트리밍을 제외했다.
Mega에서도 `pgm_read_byte` 주소 범위 바깥에 놓인 페이스는 이 포트로 읽을 수 없다. 플래시가 메모리에 매핑되는 다른 Arduino 코어에는 AVR용 `SVF_RD8` 플래그를 주지 않는다. 세부 사항은 [Arduino 포트](../c/ports/arduino/README.ko.md)를 참고한다.

### 13.2 WCH CH582(RISC-V, 베어메탈)

[CH582 포트](../c/ports/ch582/README.ko.md)는 WCH CH583 EVT의 스타트업·주변장치 코드와 `riscv32-esp-elf-gcc`를 사용한다. SDK와 컴파일러 경로는 [Makefile](../c/ports/ch582/Makefile)의 `CH583_SDK`, `CROSS` 변수로 바꿀 수 있다.

```sh
sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
make -C c/ports/ch582
# BOOT held while connecting USB / USB 연결 시 BOOT 버튼 누름
make -C c/ports/ch582 flash
```

라이브러리는 `-std=c99`, 포트는 `-std=gnu99`로 빌드한다. 라이브러리 스위치는 Uno와 동일한 `SVF_NO_SCALE`, `SVF_NO_STREAM`, `SVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`, `SVF_TARGETS=0x02`, `SVF_JSET_V2=0`을 사용한다.
페이스는 플래시의 `const` 배열로 내장한다. [link.ld](../c/ports/ch582/link.ld)는 플래시 448 KiB, RAM 32 KiB, 스택 2,048바이트를 배정한다. `.highcode` 섹션은 RAM에 복사되어 실행되므로 플래시와 RAM 예산에 모두 포함해야 한다.

128 x 64 SH1106 디스플레이는 PB20(SDA)·PB21(SCL) I2C(주소 0x3C)로 연결하며 1,024바이트 `MONO_PAGE` 버퍼를 쓴다.
`display_show(buf, y, rows)`가 타임아웃을 갖춘 `ch582_i2c_write`로 버퍼를 전송한다.
`FREQ_SYS=24000000`은 `main.c`의 `SetSysClock(CLK_SOURCE_PLL_24MHz)` 설정과 일치해야 한다.

### 13.3 DOS(DJGPP)

DJGPP는 32비트 보호 모드 실행 파일을 생성한다. 실제 DOS 환경에서 실행하려면 DPMI 호스트가 필요하며, `CWSDPMI.EXE`를 실행 파일 옆이나 `PATH` 경로에 두면 된다.[4]

```sh
DJ="$HOME/opt/djgpp/bin/i586-pc-msdosdjgpp"
"$DJ-gcc" -std=gnu99 -O2 -Ic/include c/ports/dos/svfdemo.c c/src/*.c -o SVFDEMO.EXE
"$DJ-gcc" -std=gnu99 -O2 -Ic/include -Ic/ports/dos c/ports/dos/svfvesa.c c/ports/dos/vbe_select.c \
    c/ports/dos/vesa_lines.c c/src/*.c -o SVFVESA.EXE
```

라이브러리는 `__DJGPP__` 환경의 전체 기본 기능을 그대로 사용한다. 포트 코드가 쓰는 POSIX 함수 선언을 헤더에서 열기 위해 `-std=gnu99`를 지정한다.
긴 파일 이름을 지원하지 않는 환경에서는 `NEODG16A.SVF`, `VESALINE.TXT`처럼 8.3 형식 파일 이름을 사용한다.
파일을 열 때는 stdio의 `fopen(path, "rb")` 또는 저수준 파일 API의 `O_RDONLY | O_BINARY`로 바이너리 모드를 지정한다.[4]

`svfdemo.c`는 `PAPLG16`과 `PAPLG18`을 스트리밍으로 열며, 1 KiB 블록 캐시를 각각 16슬롯·64슬롯 사용한다.
320 x 200 GRAY8 화면(64,000바이트)을 렌더링한 뒤 그레이스케일 팔레트와 함께 VGA 모드 13h로 복사한다.
`svfvesa.c`는 8·15·16·24·32 bpp VBE 타깃을 지원하며, 큰 페이스는 4.2절의 스트리밍으로 연결한다.
자세한 실행 방법은 [DOS 포트](../c/ports/dos/README.ko.md)를 참고한다.

### 13.4 ESP32(ESP-IDF)

[ESP32 포트](../c/ports/esp32/README.ko.md)는 ESP32-C3와 ESP32-S3를 지원한다. 먼저 ESP-IDF 환경을 활성화한다.
프로파일과 칩마다 빌드 디렉터리를 따로 두고, 대상 칩을 바꿀 때는 공유 `sdkconfig`도 함께 확인한다.

```sh
cd c/ports/esp32
idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3
idf.py -B build-colour build flash monitor
```

`main/CMakeLists.txt`는 `mkface.py --profile mcu-strict`로 페이스 배열을 생성한다.
자체 컴포넌트를 만들 때는 `svf.h`, `svf_internal.h`, `svf_*.c`, 생성한 `face.c`를 넣고 모두 같은 정의로 빌드한다.
다른 컴포넌트에서도 `svf.h`를 include한다면 컴파일 정의와 include 경로를 `PUBLIC`으로 전파한다.[5]

```cmake
# main/CMakeLists.txt; svf/ contains headers and sources / 헤더와 소스는 svf/에 둔다
file(GLOB SVF_SRCS svf/*.c)
idf_component_register(SRCS main.c face.c ${SVF_SRCS} INCLUDE_DIRS svf)
target_compile_definitions(${COMPONENT_LIB} PUBLIC SVF_NO_SCALE SVF_TARGETS=0x08)
```

플래시 `const` 배열은 `svf_open_mapped`로 바로 연다. 별도 데이터 파티션을 쓸 때는 `esp_partition_find_first`로 파티션을 찾은 뒤 `esp_partition_mmap(..., ESP_PARTITION_MMAP_DATA, &ptr, &handle)`으로 매핑하고 실제 파일 길이로 연다.
페이스 사용이 끝나면 `esp_partition_munmap(handle)`로 매핑을 해제한다. SPIFFS를 쓸 때는 `esp_vfs_spiffs_register`로 마운트한 뒤 4.2절의 stdio 콜백으로 스트리밍한다. 자체 컴포넌트에서 이 API를 호출한다면 `esp_partition`·`spiffs` 의존성도 함께 선언한다.[5]

컬러 프로파일은 320 x 24 RGB565 밴드(15,360바이트)를 `spi_device_polling_transmit`로 ILI9341에 전송한다.
`SVF_TF_RGB16_BIGENDIAN`은 드라이버에 맞춰 설정한다(QEMU `esp_rgb` 드라이버는 플래그 0).
앱 파티션에 페이스가 들어가는지는 최종 이미지 크기와 선택한 파티션 표를 대조해 확인한다.

### 13.5 Raspberry Pi Pico와 Pico 2(pico-sdk)

`PICO_SDK_PATH`로 pico-sdk 경로를 지정하고, Pico 2의 Arm 코어를 빌드할 때는 `-DPICO_BOARD=pico2`를 추가한다.
`PICO_NO_PICOTOOL=1`을 주면 아래 프로젝트는 `pico_add_extra_outputs`를 생략하므로 `.uf2` 파일을 생성하지 않는다.[6]

```sh
cmake -S c/ports/pico -B build-pico-mono -DSVF_PROFILE=mono -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico-mono
cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH="$HOME/opt/pico-sdk-2.3.1" -DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico2-mono
```

자체 타깃에는 `c/src/*.c`와 생성한 `face.c`를 추가하고 `c/include`를 include 경로로 넣는다.
`target_compile_definitions`로 앱과 라이브러리에 동일한 스위치를 주고, `pico_stdlib`과 사용하는 버스 라이브러리를 링크한다. 전체 구성 예는 [포트의 CMakeLists.txt](../c/ports/pico/CMakeLists.txt)를 참고한다.

SSD1306은 GP4·GP5의 I2C(`i2c_write_blocking`), ST7789는 GP16..GP20의 SPI(`spi_write_blocking`)로 연결한다.
컬러 프로파일은 240 x 24 RGB565 밴드(11,520바이트)를 사용하며 `SVF_TF_RGB16_BIGENDIAN`을 켠다.
페이스는 XIP 플래시에서 직접 읽는다.[6] 에뮬레이터 실행 시간만으로는 실제 보드의 플래시·캐시·버스 시간을 단정할 수 없다.
배선과 플래시 방법은 [Pico 포트](../c/ports/pico/README.ko.md)를 참고한다.

### 13.6 SDL2와 SDL3

[SDL 포트](../c/ports/sdl/README.ko.md)는 `sdl_compat.h`를 통해 SDL2와 SDL3를 모두 지원한다.
아래 SDL3 예제는 페이스를 불러와 2/1 배율로 그린 뒤 `out.bmp`로 저장한다.
`SDL_PIXELFORMAT_BGRX32`는 호스트 바이트 순서와 무관하게 메모리 순서 B, G, R, X를 의미한다.[7]

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

`stride`에는 `surf->pitch`를 넘긴다. 그리는 동안 서피스를 잠그고, 컬러 타깃의 `bg888`과 같은 색으로 미리 채워 둔다.
16비트 SDL 서피스는 호스트 바이트 순서를 따르므로 빅 엔디언 호스트에서는 `SVF_TF_RGB16_BIGENDIAN`을 켠다.
`make -C c/ports/sdl SDL=2` 또는 `SDL=3`으로 전체 예제를 빌드할 수 있으며, `sh c/ports/sdl/check.sh`는 지원하는 포맷의 서피스 바이트를 Python 출력과 비교한다.

### 13.7 웹(WebAssembly, Emscripten)

HTML·Node 예제와 메모리 해제 순서는 [웹 렌더러 사용법](web-renderer-guide.ko.md)에 정리되어 있다.
공통 빌드 함수를 쓰면 `EMSCRIPTEN_KEEPALIVE` API, `_malloc`·`_free`, 힙 뷰, 메모리 증가 설정이 한 번에 적용된다.[8]

```sh
mkdir -p /tmp/svf-module
. c/ports/web/emcc-flags.sh
svf_web_compile "$PWD" /tmp/svf-module
```

웹 래퍼는 `GRAY8`, `MONO_PAGE`, `MONO_ROW`, `RGB565` 타깃을 노출하며 슬롯에 페이스를 최대 4개까지 열 수 있다.
`svfw_draw`는 기본적으로 65,536바이트 정적 스크래치를 사용하고, 부족할 때만 동적 할당한다. 예를 들어 `GBATB47`의 16/1 배율에는 `2*648 + (46*16)*(54*16) = 637200`바이트가 필요하다. C 코어 자체는 동적 할당을 하지 않는다.
페이스 메모리를 해제하기 전에는 반드시 `svfw_reset`을 호출하고, WASM 메모리가 늘어날 수 있는 호출 뒤에는 힙 뷰를 다시 가져온다.[8]

<a id="14-자체-텍스트-경로가-있는-애플리케이션에-통합하기"></a>
## 14. 기존 텍스트 렌더링 경로에 통합하기

대부분의 애플리케이션에는 이미 "이 문자열을 `(x, y)`에 이 색으로 그리기" 함수와 "이 문자열의 폭 구하기" 함수가 있다. SVF 렌더러는 두 기능에 그대로 대응된다.

| 애플리케이션 요구 사항 | 라이브러리 호출 |
|---|---|
| 시작할 때 폰트 열기 | `svf_open_mapped`(메모리에 올린 페이스) 또는 `svf_open_stream`(큰 페이스, 적은 RAM) |
| 문자열의 폭과 높이 구하기 | `svf_measure_utf8`(`width`는 잉크 폭이 아니라 펜 이동 총 거리. 높이는 `ascent + descent` 또는 페이스의 `cell_h`) |
| 문자열 그리기 | 타깃에 `svf_draw_utf8` 호출 |
| 애플리케이션 자체 서피스에 그리기 | `ctx`에 서피스를 넘긴 `SVF_T_COVERAGE_CB`(8.2절), 또는 픽셀 포맷이 일치하는 타깃 유형 |
| 같은 문자열을 매 프레임 그리기 | 음절 캐시(10.2절) 활용 + 렌더링된 문자열 비트맵 자체 캐시 |
| 자체 레이아웃용 글리프별 전진 폭 | `svf_metrics_of`, 또는 한 글자에 대한 `svf_measure_utf8` |

통합할 때 자주 부딪히는 주의 사항은 다음과 같다.

1. **텍스트 인코딩.** 라이브러리는 UTF-8만 받는다. CP949/EUC-KR, UHC, 게임 고유 코드 페이지를 쓰는 앱은 호출 전에 UTF-8(또는 코드 포인트)로 변환해야 한다. 라이브러리에는 인코딩을 자동 판별하는 기능이 없다.
2. **상단이 아니라 기준선.** `y_baseline`은 셀 상단에서 어센트만큼 내려온 기준 행이다. 줄의 맨 위가 `top`에 오도록 그리려면 `top + e.ascent`(`e`는 `svf_measure_utf8` 결과)나 `top + svf_ascent(&face)`를 넘긴다.
3. **줄 높이.** `svf_measure_utf8` 결과의 `ascent + descent`는 잉크가 있는 행이 아니라, 측정된 텍스트의 셀들이 기준선 위아래로 차지하는 행 수다(셀의 어센트와 `cell_h - ascent`에 `dy`를 반영한 값). 일정한 줄 간격이 필요하면 페이스의 `cell_h`를 사용한다.
4. **여러 글자 크기.** 페이스 하나는 셀 크기 하나에 대응한다. 크기별로 페이스를 따로 두거나(`svf/dos`에 여러 크기가 있다), 한 페이스를 정수 배율로 스케일하면 픽셀이 선명하게 유지된다.
5. **페이스와 버퍼의 수명.** `svf_face` 구조체와 데이터 버퍼(매핑) 또는 `tables`/`cache`/`ctx`(스트리밍)는 모든 그리기 작업이 끝날 때까지 유효하게 유지해야 한다. 또한 `svf_face`는 메모리 주소가 이동할 수 있는 공간에 두지 않는다.
6. **멀티스레드.** 서로 독립된 페이스와 체인은 병렬로 사용할 수 있다. 반면 스트리밍 페이스나 음절 캐시처럼 내부 상태가 바뀌는 객체는 동시에 공유하지 않는다. 각 호출에는 독립된 스크래치와 타깃을 넘긴다.
7. **클리핑.** 타깃의 클리핑 영역(`clip_x0..clip_y1`)을 대화 상자 영역에 맞춘다. 라이브러리는 영역 바깥에 쓰지 않으며 완전히 바깥에 있는 셀의 글리프는 아예 읽지 않는다.
8. **외부 페이스 검증.** `svf_open_*`는 악의적인 입력 파일을 거부하도록 설계되었고 퍼즈 테스트도 거쳤다. 다만 직접 빌드해 검증한 페이스가 아니라면 절대 `-DSVF_JSET_TRUSTED=1`로 빌드하지 않는다.
9. **어디서나 같은 스위치 사용**(2절).

실제 래퍼는 페이스·체인·스크래치·음절 캐시를 한 구조체나 객체로 묶고, 내부에서 `svf_measure_utf8`과 `svf_draw_utf8`을 호출하는 `width(str)`·`draw(str, x, y_top)` 메서드를 제공하는 형태로 만들면 깔끔하다.

## 15. 통합 테스트

- **레퍼런스 비교.** `tools/svfline.py`는 같은 줄을 Python으로 렌더링하며, C 출력과 바이트 단위로 일치해야 한다. `tools/test_c_renderer.py`는 저장소 자체의 비교 테스트이므로 양쪽 구동 방법은 이를 참고한다.
- **자동 검증(게이트).** `make -C c check`는 새니타이저를 켠 상태로 단위 테스트를 실행하고, 어느 오브젝트 파일도 `malloc`, `calloc`, `realloc`, `free`를 참조하지 않는지 검사하며, Python 출력 비교까지 수행한다.
- **직접 확인하기.** 레이아웃 문제를 가장 빨리 잡는 방법은 알려진 문자열을 `SVF_T_GRAY8` 버퍼에 그려 터미널에 출력하는 작은 테스트 프로그램이다(3절). 테스트 바이너리는 `-fsanitize=address,undefined`로 컴파일한다.
- **페이스 파일 검사.** 페이스 파일 내부를 보려면 `c/build/svfdump FACE info`(헤더 값, 레이아웃 단위, `jset_bad`·`jset_unread`·`jmap_bad`·`jmap_unread` 상태 비트)를 실행한다. `svfdump FACE has U+AC00 U+D55C`로 각 코드 포인트 지원 여부를 확인하고, `svfdump FACE syllables`로 조합된 음절 셀을 전부 덤프할 수 있다(Python 동일성 테스트의 C 쪽 도구). Python에서는 `jamoset.parse_svfn`을 쓴다. 참고로 `tools/facecheck.py`는 개별 페이스 검사기가 **아니라** 매니페스트와 폰트 맵이 가리키는 페이스를 검사하는 도구다. 페이스 제작은 [메이커 앱](maker-desktop.ko.md), 조회와 미리보기는 [데스크톱 앱](desktop-app.ko.md)을 참고한다.

## 16. 문제 해결

| 증상 | 주요 원인 | 해결 방법 |
|---|---|---|
| `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | SVFN 파일이 아니거나, 텍스트 모드로 읽었거나, 파일이 잘림 | 바이너리 모드로 열고 파일 길이를 비교 |
| `SVF_E_VERSION` | 버전 2 파일 | `tools/svf2to3.py`로 버전 3 변환 |
| `SVF_E_LAYOUT` | `-DSVF_LAYOUTS=...`로 제한 빌드했는데 페이스가 다른 레이아웃 사용 | 빌드가 지원하는 프로파일로 페이스를 다시 만들거나 `SVF_LAYOUTS` 범위 확장 |
| 라틴은 나오는데 한글이 전혀 안 그려짐 | 조합 기능 없는 일반 페이스로 열림(`svf_status`의 `SVF_FACE_JSET_BAD`, `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD` 확인) | 페이스가 요구하는 리더를 켜고 다시 빌드(10.1절)하거나 호환 형식으로 페이스 재생성 |
| 한글 자리에 빈 간격만 생김 | 체인의 어느 페이스에도 해당 코드 포인트가 없음 | `svf_has(face, cp)`로 확인하고 페이스를 추가하거나 `missing_advance` 조정 |
| `svf_draw_utf8`가 `SVF_E_NOMEM`을 반환 | 스크래치가 `svf_chain_scratch_bytes`보다 작음(배율이나 페이스 변경 후 미갱신) | `svf_chain_scratch_bytes`를 다시 계산해 스크래치 확대 |
| `svf_target_init`에서 `SVF_E_ARG` | 타깃 유형이 `SVF_TARGETS`에 없음, `buf_len < rows * stride`, stride 부족, 또는 `w`/`h`가 0 | 항목별로 확인. `GRAY`는 초기화 후 `gray_bits` 설정 |
| `svf_draw_utf8`에서 `SVF_E_ARG` | 페이스 없는 체인, 1..16 범위를 벗어난 배율 또는 `SVF_NO_SCALE`, 팔레트 구간 설정이 잘못된 `INDEXED8`, `plot`이 없는 `COVERAGE_CB` | 해당 설정을 하나씩 확인 |
| `INDEXED8` 타깃에서 글자가 안 보임 | 배경 인덱스가 잉크 팔레트 구간보다 낮지 않음(최댓값 유지 규칙) | 배경 인덱스가 잉크 구간 아래에 오도록 팔레트 재정렬 |
| 컬러 텍스트 가장자리에 테두리(halo)가 생김 | `bg565`/`bg888`이 실제 배경색과 다름 | 실제 배경색을 지정하거나 콜백 타깃으로 블렌딩 |
| 글리프가 한 행 위나 아래로 어긋남 | 기준선 대신 상단 행을 넘김 | `y_baseline = top + ascent`로 전달 |
| AVR `PROGMEM` 배열 페이스에서 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | `-DSVF_RD8(p)=pgm_read_byte(p)` 없이 빌드해 플래시 주소를 RAM으로 읽음 | 모든 라이브러리 소스를 `-include avr/pgmspace.h '-DSVF_RD8(p)=pgm_read_byte(p)'`로 빌드(5.1절) |
| 페이스 배열이 RAM을 차지하거나 링크 시 RAM 초과 오류 발생 | `xxd -i`로 배열을 생성함(`const`가 없어 `.data`에 배치) | `c/bench/mkface.py`로 생성(5절)하고 `size`에서 data가 아닌 text에 잡히는지 확인 |
| `-DSVF_SMALL`을 넣은 뒤 한글이 안 그려짐 | `SVF_SMALL`이 `SVF_JMAP`, `SVF_JMAP_LIST`, `SVF_JMAP_RECOG`, `SVF_JSET_BIG` 기본값을 꺼서 버전 3·BIG 페이스가 일반 페이스로 열림(`JSET_BAD`. `JMAP_UNREAD`는 `-DSVF_JMAP_RECOG=1`일 때만) | `-DSVF_JMAP=1 -DSVF_JSET_BIG=1`을 추가하거나 빌드가 읽는 형식으로 페이스 재생성(10.1절, 12절) |
| 일부 한글 음절만 그려지고 나머지가 누락됨 | 페이스의 JMAP이 SPARSE 또는 LIST이며 폴백 블록이 없어 등록된 음절만 조합함 | 음절별로 `svf_has(face, cp)` 확인. 폴백 블록이나 조밀한 테이블을 포함해 페이스 재생성(10절) |
| 텍스트 오른쪽 끝이 버퍼에서 잘림 | 버퍼 폭을 펜 이동 거리(`e.width`)만으로 잡았는데 마지막 글리프 잉크가 그 너머로 뻗음 | `e.width + svf_cell_w(face)`로 여유 확보(3절) |
| 업그레이드 후 크래시나 이상한 값 출력 | 소스 파일(컴파일 단위)마다 서로 다른 `-D` 스위치로 빌드됨(`SVF_JMAP`이 `svf_face` 크기 변경) | 동일한 플래그 집합으로 전체 다시 빌드 |
| 스트리밍 페이스에서 `SVF_E_IO` | 읽기 콜백이 요청 길이보다 적게 읽거나 음수를 반환함 | 성공 시 정확히 `len`바이트, 실패 시 음수를 반환하도록 수정하고 파일 위치 이동 로직 확인 |

## 17. 관련 문서

[프로젝트 안내](../README.ko.md)에서 시작해 [SVF 용어집](../spec/SVF.ko.md#glossary),
[렌더러 설계](../spec/renderer-design.ko.md), [자모 세트](jamo-sets.ko.md)로 이어 읽으면 데이터 구조와 조합 규칙을 파악할 수 있다.
페이스 제작·변환은 [레시피](recipes.ko.md)와 [도구 사용법](tools.ko.md)을,
커버리지·색상·출력 비트 깊이 선택은 [안티앨리어싱](anti-aliasing.ko.md)을 참고한다.
앱별 통합 흐름은 [웹 가이드](web-renderer-guide.ko.md), [데스크톱 앱](desktop-app.ko.md), [메이커 앱](maker-desktop.ko.md)에서 다룬다.

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
