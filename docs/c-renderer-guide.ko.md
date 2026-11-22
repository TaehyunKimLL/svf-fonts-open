[English](c-renderer-guide.md) | **한국어**

# SVF C 렌더러: 통합 가이드

이 가이드는 SVF C 렌더러(`c/`)를 자신의 프로그램에 넣는 방법을 설명한다. 소스를 얻는 방법, 페이스(face)를 여는 방법, 자모 세트로
한글 음절을 조합하여 UTF-8 텍스트를 그리는 방법, 그리기 타깃을 고르는 방법, 메모리 예산을 잡는 방법, 그리고 그림이 잘못 나올 때
무엇을 확인할지를 다룬다. 이 문서는 튜토리얼이다. 레퍼런스는 [c/README.ko.md](../c/README.ko.md)(API 표, 컴파일 타임 스위치,
포트)이며, 무엇보다 모든 함수의 정확한 계약을 밝혀 두는 [c/include/svf.h](../c/include/svf.h)의 주석이다. 파일 포맷은
[spec/SVF.ko.md](../spec/SVF.ko.md)에, 설계는 [spec/renderer-design.ko.md](../spec/renderer-design.ko.md)에 있다.

아래의 모든 예제는 이 저장소를 대상으로 `gcc -std=c99 -Wall -Wextra`로 컴파일하고 배포되는 페이스로 실행한 것이며, 표시된 출력은
실제 출력이다.

## 목차

1. 다섯 단어로 보는 모델
2. 라이브러리를 빌드에 넣기
3. 완전한 첫 번째 프로그램
4. 페이스: 매핑 방식과 스트리밍 방식
5. 텍스트 한 줄: 체인, 메트릭, 측정
6. 타깃: 픽셀이 가는 곳
7. 스케일링
8. 한글: 자모 페이스와 음절 조합
9. 메모리 예산
10. 컴파일 타임 스위치: 세 가지 레시피
11. 자체 텍스트 경로가 있는 애플리케이션에 통합하기
12. 통합 테스트
13. 문제 해결

## 1. 다섯 단어로 보는 모델

**페이스, 체인, 타깃, 스크래치, 줄.**

- **페이스(face)**(`svf_face`)는 열린 `.SVF` 파일 하나이다. 셀 크기, 비트 깊이(픽셀당 1, 2 또는 8비트), 글리프 테이블, 그리고 선택적으로
  모든 한글 음절을 그릴 수 있게 해 주는 자모 세트로 이루어진다. 구조체는 호출자가 할당하며, 라이브러리는 할당하지 않는다.
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

라이브러리는 소스 파일 여섯 개와 헤더 하나이다. 설정할 것도, 의존성도 없다.

    c/include/svf.h
    c/src/svf_face.c  svf_jamo.c  svf_stream.c  svf_draw.c  svf_scale.c   (+ svf_internal.h)

사용 방법은 세 가지이다.

1. **소스를 프로그램에 직접 컴파일한다.** 빌드에 `c/src/*.c`를 추가하고 `-I c/include`를 준다. 여기의 예제들이 이 방법을 쓴다.

       gcc -std=c99 -I c/include my_app.c c/src/*.c -o my_app

2. 저장소의 Makefile로 **정적 라이브러리를 빌드한다.** `make -C c`는 `libsvf.a`(와 `svfdump` 도구)를 `c/build`에 쓰며, `O=DIR`로 위치를 옮길 수 있다.
3. **벤더링하거나 서브모듈로 넣는다.** 저장소는 공개이며 코드는 MIT 라이선스이다(`svf/` 아래의 페이스는 OFL이다.
   [NOTICE.ko.md](../NOTICE.ko.md) 참조). ScummVM 같은 프로젝트는 저장소를 git 서브모듈로 추가하고 여섯 파일을 자체 빌드 시스템으로
   컴파일할 수 있다.

**무엇보다 중요한 규칙이 하나 있다. `svf.h`를 include하는 모든 소스 파일과 모든 라이브러리 소스는 같은 `-D` 스위치로 컴파일해야 한다.**
`SVF_JMAP`은 `svf_face`의 크기를 바꾸므로, 빌드를 섞으면 메모리가 손상된다. 스위치는 한곳에 두라(프로젝트 전체의 플래그 변수, 또는
강제로 include하는 작은 헤더).

데스크톱, DOS, WASM 빌드의 기본값은 전체 기능 집합이다. 모든 타깃 종류, 스트리밍, 스케일링, 모든 자모 블록 버전이 켜져 있다.
스위치는 작은 장치에서 무언가를 *제거*할 때에만 설정한다(10절).

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
	int w = e.width + 2, h = e.ascent + e.descent + 2;
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

    ..................................................................
    ..................................................................
    ....................................####....##....##.........##...
    ..#####..##...##..######...........##..##...##....##.........##...
    .##...##.##...##.##...............##....##..##....##......#####...
    .##......##...##.##...............##....##..#####.##.........##...
    .##......##...##.##...............##....##..##....##......#####...
    ..#####..##...##.######............##..##...##....##.........##...
    ......##.##...##.##.................####....##.....#######...##...
    ......##.##...##.##...............................................
    ......##.##...##.##................##................########.....
    .##...##..##.##..##................##..............###......###...
    ..#####....###...##................##..............##........##...
    ...................................##..............###......###...
    ....................................##########.......########.....
    ..................................................................
    ..................................................................
    ..................................................................

단계별로 살펴보면 다음과 같다.

- `svf_open_mapped`는 파일 전체를 검증한다. 열린 페이스는 그려도 안전하다. 반환값은 파일이 거부된 이유(`SVF_E_MAGIC`,
  `SVF_E_VERSION`, ...)를 알려 준다.
- `svf_measure_utf8`는 글리프를 읽지 않고 줄의 범위(extent)를 준다. `e.width`(펜 이동 거리), `e.ascent`와 `e.descent`(베이스라인 위와
  아래의 행 수)이다. 여기서는 64 x (12 + 4)이다.
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
  `NEODG16A.SVF`(자모 페이스)는 8,153바이트이고, 미리 조합된 `NEODG16.SVF`는 46,492바이트이다(측정값).
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
(13절).

## 5. 텍스트 한 줄: 체인, 메트릭, 측정

### 5.1 폴백 체인

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

### 5.2 마크, advance, 잘못된 UTF-8

- advance는 페이스의 메트릭 테이블에서 온다(가변 폭). 메트릭 테이블이 없는 페이스는 셀 폭만큼 전진한다. 조합된 음절은 자모 블록의
  음절 advance(또는 셀 폭)만큼 전진한다.
- 결합 마크는 0만큼 전진하며 앞선 글리프 위에 그려진다. 기본 술어는 U+0300..U+036F이다. 코어는 유니코드 테이블을 갖고 있지 않으므로
  더 많은 범위가 필요하면 자신의 `chain.is_mark`를 넘긴다.
- 잘못된 UTF-8은 절대 크래시하지 않으며 `len`을 넘어 읽지도 않는다. 잘못된 부분 시퀀스는 각각 어떤 페이스에 U+FFFD가 있으면 그것으로
  그려지고, 없으면 전진 없이 건너뛴다. NUL은 일반 코드 포인트이다(C 문자열이 아니라 `len`바이트가 그려진다).

### 5.3 그리기 전에 측정하기

`svf_measure_utf8(&chain, s, len, &e)`는 그리기와 정확히 같은 레이아웃 규칙을 써서 `e.width`, `e.ascent`, `e.descent`를 주며, 글리프를
읽지 않는다(그래서 비용이 적고 스트리밍 페이스는 I/O를 하지 않는다). 가운데 정렬, 오른쪽 정렬, 단어 줄바꿈, 그리고 그려 넣을 버퍼의
크기를 정할 때 쓴다. 단어와 줄은 사용자의 몫이다. 라이브러리는 한 번에 한 줄을 그리며 줄바꿈에 대해서는 아무것도 모른다.

## 6. 타깃: 픽셀이 가는 곳

타깃은 그려진 각 픽셀의 커버리지를 사용자의 포맷으로 변환한다. 종류는 `svf_target_init`로 고른다.

    svf_err svf_target_init(svf_target *t, svf_target_kind kind, uint8_t *buf, size_t buf_len,
                            int16_t w, int16_t h, uint16_t stride);

| 그리는 대상 | 사용 | 비고 |
|---|---|---|
| 32비트 프레임버퍼 또는 SDL 서피스(메모리상 B, G, R, X) | `SVF_T_XRGB8888` | `t.fg888`, `t.bg888`을 `0x00RRGGBB`로 설정 |
| 24비트 | `SVF_T_RGB888` | 같은 필드 |
| 16비트 컬러 LCD | `SVF_T_RGB565` / `SVF_T_RGB555` | `t.fg565`, `t.bg565`. 상위 바이트가 먼저이면 `t.flags`에 `SVF_TF_RGB16_BIGENDIAN` |
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

### 6.1 32비트 서피스 위의 컬러 텍스트

```c
svf_target t;
svf_target_init(&t, SVF_T_XRGB8888, surface_pixels, (size_t)pitch * height, width, height, (uint16_t)pitch);
t.fg888 = 0x00FFC000;      /* 호박색 텍스트 */
t.bg888 = 0x00000020;      /* 호출자가 아는 배경색 */
```

`stride`는 바이트 수를 나타내는 `uint16_t`이므로, 32비트 타깃의 폭은 최대 16,383픽셀이다.

### 6.2 콜백 타깃: 만능 어댑터

픽셀 포맷이 위의 것들 중 어느 것도 아니거나, 기존 내용 위에 섞고 싶거나, 목적지가 다른 라이브러리의 서피스일 때는 콜백을 쓴다.
라이브러리는 클립 안에서 커버리지가 0보다 큰 각 픽셀마다 행 단위로 `plot(ctx, x, y, coverage)`를 한 번씩 호출하며, 버퍼는 관여하지
않는다. 이 예제는 이미 그림이 들어 있는 32비트 서피스 위에 흰 텍스트를 섞는다(`NEODG16A.SVF`에 대해 컴파일하고 실행했다).

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

## 7. 스케일링

`chain.scale_num`과 `chain.scale_den`을 설정한다(각각 1에서 16; 0과 0은 1/1을 뜻한다). 정수배(`2/1`, `3/1`)는 원본 픽셀을 각각 N x N 블록으로
그리므로 비트맵의 가장자리가 선명하게 유지된다. 다른 비율은 영역 평균을 내어 8비트 커버리지가 되므로, 1 bpp 페이스의 `3/2`는 가장자리
픽셀이 회색이 된다(이때는 컬러나 회색조 타깃을 쓰라. 모노 타깃에서는 임계값이 결정한다). 길이는 반올림(0.5는 올림, 대칭)으로
스케일되므로, 측정된 범위는 그려진 것과 같다. `x`, `y_baseline`, 클립은 항상 출력 픽셀 단위이다.

스크래치는 스케일링에 따라 커진다. `svf_chain_scratch_bytes(&chain)`에는 스케일된 셀(대략 `ceil(cell_w*num/den) * ceil(cell_h*num/den)`바이트
추가)이 포함된다. 스케일을 바꾼 뒤에는 항상 다시 계산하라. 16x16 페이스를 3/2로 쓴 측정 실행에서는 640바이트였다.

작은 MCU 빌드에서는 `-DSVF_NO_SCALE`이 스케일링을 완전히 제거한다(그러면 n/n 이외의 비율은 `SVF_E_ARG`이다). 빠른 스케일러의 스택 프레임은
약 610~680바이트이다. 2 KB RAM 칩에서 쓰기 전에 `svf.h`의 "Scaling"을 보라.

## 8. 한글: 자모 페이스와 음절 조합

**미리 조합된(precomposed)** 페이스는 담당하는 음절마다 글리프 하나를 저장한다. **자모 세트(jamo-set)** 페이스(헤더 플래그 비트 1,
`svf_is_jamo(f)`)는 수백 개의 작은 조각과, 어떤 조각들이 각 음절을 이루는지 알려 주는 테이블을 저장한다. `svf_draw_utf8`는 조각들로부터
U+AC00..U+D7A3(그리고 호환 자모 U+3131..U+3163)을 즉석에서 조합한다. 두세 조각의 최대 커버리지이다. 특별히 할 일은 없다. 그냥 한글
텍스트를 그리면 된다.

```c
if (svf_is_jamo(&face)) {
	uint16_t pieces[3];
	int n = svf_jamo_pieces(&face, 0xD55C /* 한 */, pieces);   /* 3: 초성, 중성, 종성 */
}
uint8_t cell[64];                                      /* >= svf_cell_bytes(&face) */
svf_glyph(&face, 0xD55C, cell, sizeof cell);           /* 조합된 셀, MSB 우선, 행은 바이트 단위로 패딩 */
```

`svf_glyph`와 `svf_compose`는 타깃 없이 코드 포인트 하나의 셀을 반환한다. 자신의 아틀라스에 글리프를 캐시할 때 유용하다.

### 8.1 사용자의 빌드가 읽는 것

자모 블록은 버전 1, 2, 3(LIST 형식이 있는 JMAP)이 있다. 기본 데스크톱/DOS/WASM/SDL 빌드는 모두 읽는다. 작은 MCU 빌드는 더 적게 읽는다
([c/README.ko.md](../c/README.ko.md)의 표 "Jamo sets: what each build reads" 참조). 빌드가 읽지 못하는 페이스도 상태 비트와 함께 **일반**
페이스로 열리며, 다만 한글을 조합하지 않는다. 자신의 애플리케이션용 페이스는 저장소의 도구와 같은 방식으로 빌드하고, 로드 시점에
`svf_status`를 확인하라.

### 8.2 조합된 음절 캐시

조합에는 음절마다 몇 번의 테이블 조회와 병합이 든다. 반복되는 텍스트(UI, 프레임마다 다시 그리는 대화 상자)에는 체인에 캐시를 준다.

```c
static uint8_t syl[4096];                       /* 슬롯은 (8 + 체인 페이스들 중 가장 큰 셀 바이트 수) 크기 */
svf_chain_cache(&chain, syl, sizeof syl);
```

캐시가 있든 없든 픽셀은 동일하다. 스트리밍 페이스에서 가장 효과가 크다. 캐시된 음절은 읽기를 전혀 일으키지 않는다. 스트리밍 16x16
페이스에서 "한글 ab"를 3/2로 처음 그릴 때 읽기 호출은 10번이었고, 캐시된 두 번째 그리기에서는 더 늘지 않았다(측정값). 캐시는 선형 조회를 쓰는
라운드 로빈 방식이다. 작은 타깃에는 수십 개의 슬롯이 알맞고, 수천 개는 맞지 않는다. `chain.faces`를 바꾸거나 페이스를 다시 연 뒤에는
`svf_chain_cache`를 다시 호출하라.

## 9. 메모리 예산

모든 메모리는 사용자의 것이다. 합산하라.

| 항목 | 크기 |
|---|---|
| `svf_face` | `sizeof(svf_face)`: `SVF_JMAP`이 있는 64비트 호스트에서 96바이트(없으면 80, MCU에서는 더 작음. 96이 상한) |
| `svf_chain`, `svf_target` | 각각 수십 바이트 |
| 스크래치 | `svf_chain_scratch_bytes(&chain)`: 셀 하나(`svf_cell_bytes`), 블록 캐시 없는 스트리밍 페이스는 그 두 배, 스케일링 시 스케일된 셀 추가 |
| 스트리밍 페이스 | 테이블용 `svf_stream_tables_size(...)`, 선택적 캐시용 `slots * (block_size + 8)` |
| 음절 캐시 | `slots * (8 + 가장 큰 셀 바이트 수)` |
| 타깃 버퍼 | `rows * stride`(콜백 종류는 없음) |
| 매핑된 페이스 | 파일 자체, RAM 또는 플래시에(플래시 페이스는 RAM을 쓰지 않음) |
| 스택 | 스케일러 자신의 프레임: 기본 빠른 스케일러에서 AVR은 약 610바이트, Cortex-M0+는 680바이트 |

16x16 1 bpp 셀은 32바이트이고, 24x24 2 bpp 셀은 144바이트이다.

## 10. 컴파일 타임 스위치: 세 가지 레시피

스위치는 **모든** 소스에 주는 `-D` 플래그이다(2절). 데스크톱에서는 거의 필요하지 않다. 레시피를 고를 때 중요한 것들은 다음과 같다.

- **데스크톱, DOS, WASM, SDL, ScummVM급 애플리케이션: 스위치 없음.** 모든 것이 켜져 있다.
- **디스플레이 하나인 작은 MCU:** `-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_TARGETS=<one kind's bit> -DSVF_JSET_V2=0
  -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`를 쓰고, 맞는 프로필로 페이스를 쓴다(`tools/jamoset.py` `mcu-strict`). Arduino Uno 빌드가 정확히
  이것을 쓴다. [c/ports/arduino/README.ko.md](../c/ports/arduino/README.ko.md)를 보라.
- **어느 CPU에서든 가장 작은 코드:** `-DSVF_SMALL`은 속도 중심의 빠른 경로를 끈다. 픽셀은 동일하며 속도만 잃는다.

툴체인별 기본값이 있는 전체 스위치 표는 [c/README.ko.md](../c/README.ko.md)의 "Compile-time switches"에 있고, 각 구성이 만드는 크기는
`c/cross/SIZES.md`에 있다.

## 11. 자체 텍스트 경로가 있는 애플리케이션에 통합하기

대부분의 애플리케이션에는 이미 "이 문자열을 x, y에 이 색으로 그려라"라는 루틴과 "이 문자열의 폭은 얼마인가"라는 루틴이 있다. 렌더러는 둘 다에
대응된다.

| 애플리케이션이 필요로 하는 것 | 라이브러리 호출 |
|---|---|
| 시작할 때 폰트 열기 | `svf_open_mapped`(메모리에 로드된 페이스) 또는 `svf_open_stream`(큰 페이스, 적은 RAM) |
| 문자열의 폭과 높이 | `svf_measure_utf8`(`width`. 높이 = `ascent + descent`, 또는 페이스의 `cell_h`) |
| 문자열 그리기 | 타깃으로 `svf_draw_utf8` |
| 애플리케이션 자체 서피스에 그리기 | `ctx`에 서피스를 넣은 `SVF_T_COVERAGE_CB`(6.2절), 또는 그 픽셀 포맷에 맞는 타깃 종류 |
| 같은 문자열을 매 프레임 그리기 | 음절 캐시(8.2절), 그리고 렌더링된 문자열 비트맵을 직접 캐시 |
| 자체 레이아웃을 위한 글리프별 advance | `svf_metrics_of`, 또는 문자 하나에 대한 `svf_measure_utf8` |

번번이 문제를 일으키는 점들은 다음과 같다.

1. **텍스트 인코딩.** 라이브러리는 UTF-8을 받는다. 텍스트를 CP949/EUC-KR, UHC 또는 게임 고유의 코드 페이지로 저장하는 애플리케이션은
   호출 전에 UTF-8(또는 코드 포인트)로 변환해야 한다. 라이브러리에는 바이트 쌍을 추측하는 기능이 없다.
2. **상단이 아니라 베이스라인.** `y_baseline`은 글리프의 어센트 아래의 행이다. 줄의 상단이 `top`에 오도록 그리려면 `top + e.ascent`
   (`e`는 `svf_measure_utf8`의 결과) 또는 `top + svf_ascent(&face)`를 넘긴다.
3. **줄 높이.** 범위의 `ascent + descent`는 측정된 대상의 잉크 범위이다. 균일한 줄 간격에는 페이스들의 `cell_h`를 쓴다.
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
라이브러리로 교체하는 일은 따로 추적된다([c/README.ko.md](../c/README.ko.md)의 "Who uses it" 참조). 이 절의 모든 내용은 그 통합에
적용된다.

## 12. 통합 테스트

- **레퍼런스.** `tools/svfline.py`는 같은 줄을 Python으로 그린다. 그 출력은 C 출력과 바이트 단위로 같아야 한다.
  `tools/test_c_renderer.py`는 저장소 자체의 비교이며, 양쪽을 어떻게 구동하는지는 이를 읽으라.
- **게이트.** `make -C c check`는 새니타이저 아래에서 단위 프로그램을 실행하고, 어떤 오브젝트도 `malloc`, `calloc`, `realloc`, `free`를
  참조하지 않는지 검증하며, Python 비교를 실행한다.
- **자신의 검사.** 알려진 문자열을 `SVF_T_GRAY8` 버퍼에 그려 출력하는 작은 프로그램(3절)이 레이아웃 문제를 가장 빨리 확인하는 방법이다.
  테스트는 `-fsanitize=address,undefined`로 컴파일하라.
- **페이스.** `tools/facecheck.py`는 작성자 쪽에서 페이스 파일을 검증한다. 메이커 앱은 자신이 쓰는 모든 페이스를 검사하고, 완료로 치기 전에
  그려 본다.

## 13. 문제 해결

| 증상 | 있을 법한 원인 | 할 일 |
|---|---|---|
| `svf_open_mapped`가 `SVF_E_MAGIC`을 반환 | SVFN 파일이 아니거나, 파일이 텍스트 모드로 읽혔거나 잘렸음 | 바이너리 모드로 열고 길이를 비교 |
| `SVF_E_VERSION` | 버전 2 파일 | `tools/svf2to3.py`로 변환 |
| `SVF_E_LAYOUT` | 빌드가 `-DSVF_LAYOUTS=...`로 컴파일되었고 페이스가 다른 레이아웃을 씀 | 빌드가 읽는 프로필로 페이스를 쓰거나, `SVF_LAYOUTS`를 넓힘 |
| 한글은 아무것도 그려지지 않는데 라틴은 됨 | 페이스가 일반 페이스임: `svf_status`에서 `SVF_FACE_JSET_BAD`, `JSET_UNREAD`, `JMAP_BAD`, `JMAP_UNREAD`를 확인 | 페이스가 필요로 하는 리더로 빌드(8.1절)하거나 페이스를 다시 작성 |
| 한글이 누락 글리프 간격으로 그려짐 | 체인의 어느 페이스에도 그 코드 포인트가 없음 | `svf_has(face, cp)`. 페이스를 추가하고 `missing_advance`를 설정 |
| `svf_draw_utf8`가 `SVF_E_NOMEM`을 반환 | 스크래치가 `svf_chain_scratch_bytes`보다 작음(스케일이나 페이스를 바꾼 뒤 다시 계산) | 스크래치를 키움 |
| `svf_target_init`에서 `SVF_E_ARG` | 종류가 `SVF_TARGETS`에 없음, `buf_len < rows * stride`, stride가 너무 작음, 또는 w/h가 0 | 각각 확인. GRAY는 초기화 뒤에 `gray_bits`를 설정 |
| `svf_draw_utf8`에서 `SVF_E_ARG` | 페이스 없는 체인, 1..16을 벗어난 스케일 비율 또는 `SVF_NO_SCALE`, 잘못된 램프의 `INDEXED8`, `plot` 없는 `COVERAGE_CB` | 이것들을 확인 |
| `INDEXED8` 타깃에서 텍스트가 안 보임 | 배경 인덱스가 잉크 램프보다 낮지 않음(최댓값 규칙) | 팔레트 번호를 다시 매김 |
| 컬러 텍스트에 후광이 생김 | `bg565`/`bg888`이 실제 배경이 아님 | 실제 배경을 설정하거나 콜백 타깃을 사용 |
| 글리프가 한 행 높거나 낮음 | 베이스라인 대신 상단 행을 넘김 | `y_baseline = top + ascent` |
| 업그레이드 뒤 크래시나 쓰레기 값 | 번역 단위들이 서로 다른 `-D` 스위치로 빌드됨(`SVF_JMAP`은 `svf_face`를 바꿈) | 하나의 플래그 집합으로 전부 다시 빌드 |
| 스트리밍 페이스에서 `SVF_E_IO` | 읽기 콜백이 모자라거나 음수인 개수를 반환함 | 정확히 `len`바이트 또는 음수 값을 반환. 파일 위치 로직을 확인 |
