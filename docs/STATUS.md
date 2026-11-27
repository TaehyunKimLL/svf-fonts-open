---
title: "svf-fonts 개발 현황 (development status) 2026-11-27"
type: status
status: running
date: 2026-11-27
keywords: [status, 개발 현황, SVF v3, JSET, JMAP, LIST, BIG, C renderer, ports, maker, desktop app, AppImage]
---

# svf-fonts 개발 현황 (2026-11-27)

SVF v3 리더와 변환 도구, C 렌더러, 웹 미리 보기, Linux 데스크톱 변환 앱을 제공한다.
시작점은 [README](../README.ko.md), 형식과 용어는 [SVF 명세](../spec/SVF.ko.md),
구조는 [렌더러 설계](../spec/renderer-design.ko.md)를 참고한다.

## 1. 구성 요소

| 구성 요소 | 제공 기능 | 안내 |
|---|---|---|
| SVF v3 | 완성형과 자모 세트, JSET v1/v2, BIG, JMAP dense/SPARSE와 LIST, 글리프별 dy | [명세](../spec/SVF.ko.md), [자모 세트](jamo-sets.ko.md) |
| C 렌더러 | 메모리·스트리밍 읽기, UTF-8 줄 그리기, 스케일, 타깃별 출력; 빌드 옵션으로 기능 제한 | [C 가이드](c-renderer-guide.ko.md), [C API](../c/README.ko.md) |
| 포트 예제 | Pico, ESP32-C3/S3, Arduino Uno/Mega, CH582M, DOS, WASM, SDL2/SDL3 | [포트와 페이스](../c/ports/FACES.md) |
| Python 도구 | 폰트 변환, 프로파일, 부분집합, 자모 맞춤, 내보내기와 검사 | [도구](tools.ko.md), [레시피](recipes.ko.md) |
| SVF maker | 입력 감지, 경로 선택, 설정, 작업 실행, WASM 미리 보기, TTF/BDF 내보내기; 업로드·로컬 모드 | [서버](../maker/README.ko.md), [기능 점검](maker-audit.ko.md) |
| 데스크톱 앱 | Electron 셸, 동결 사이드카, Linux x86_64 AppImage, 패키지 점검 | [앱 사용법](desktop-app.ko.md), [패키징](maker-desktop.ko.md) |
| 웹 렌더러·선택기 | C/WASM 렌더링, Canvas 표시, 페이스 색인과 선택 | [웹 가이드](web-renderer-guide.ko.md), [선택기](../web/README.ko.md) |
| 폰트 배포 | 페이스별 라이선스와 생성 경로 | [NOTICE](../NOTICE.ko.md), [레시피](recipes.ko.md) |

배포 페이스는 SIL OFL 1.1 대상으로 관리한다. 라이선스 해석과 예외는 NOTICE가 설명한다.
MCU 단색 예제는 `svf/dos/NEODG16G.SVF`를 사용한다. Apple·Windows 등 사용자가 제공한 폰트는
변환 도구의 입력일 수 있지만 해당 원본을 앱과 함께 배포하지 않는다.

## 2. 주요 구현 이력

| 날짜 | 기능 | 구현·사용법 |
|---|---|---|
| 2026-10-20 | 이식 가능한 C 렌더러 | `c/src/`, `c/include/svf.h` |
| 2026-10-21 | WASM 선택기 | `web/`, `c/ports/web/` |
| 2026-10-22 | SVF v3 전환; v2 변환 도구 | `tools/svf2to3.py` |
| 2026-10-26 | SDL2/SDL3와 매개변수형 GRAY 타깃 | `c/ports/sdl/`, `c/src/svf_draw.c` |
| 2026-10-27~28 | JMAP·BIG·LIST | `c/src/svf_jamo.c`, `spec/SVF.ko.md` |
| 2026-11-03~05 | maker 입력 확장, 컨트롤·WASM 미리 보기, 로컬 모드 | `maker/detect.py`, `routes.py`, `settings.py`, `server.py` |
| 2026-11-09 | Electron 데스크톱 앱과 AppImage 빌드 | `desktop/`, `maker/sidecar.py` |
| 2026-11-17~18 | 로컬 정리 수명 주기, e2e, busy·409 처리 | `maker/jobs.py`, `server.py`, `static/maker.js` |
| 2026-11-20~22 | 정적 AppImage 런타임, 샘플 변환 e2e, 깨끗한 Ubuntu에서 Xvfb 실행 | `desktop/build/`, `desktop/test/`, `maker/test/uisample.py` |
| 2026-11-23 | HWP 1.x/3.0과 KS 원시 덤프 리더 | `tools/hwpfont.py`, `maker/test/test_hwp_inputs.py` |
| 2026-11-24 | maker TTF/BDF 내보내기를 포함한 샘플 e2e | `tools/svf2ttf.py`, `maker/test/uisample.py` |

## 3. C 빌드 기능과 기록된 수치

### 3.1. 자모 블록 지원

다음은 `c/include/svf.h`의 기본값과 포트의 빌드 옵션을 구별한 표이다.
옵션 이름과 오류 코드는 [C API 안내](../c/README.ko.md)에 있다.

| 대상·설정 | JSET v1 | JSET v2 | BIG | JMAP·LIST | 스트리밍 | 스케일 |
|---|---|---|---|---|---|---|
| host, DOS, WASM, SDL 기본값 | 예 | 예 | 예 | 예 | 예 | 예 |
| Arduino Uno 포트 | 예 | 아니오 | 아니오 | 아니오 | 아니오 | 아니오 |
| 일반 MCU 헤더 기본값(AVR 제외) | 예 | 예 | 아니오 | 아니오 | 예 | 예 |
| Pico·ESP32 포트 프로파일 | 예 | 예 | 아니오 | 아니오 | 프로파일에 따라 끔 | 끔 |
| CH582 포트 | 예 | 아니오 | 아니오 | 아니오 | 끔 | 끔 |

MCU에서도 명시적 옵션으로 기능을 켤 수 있다. Arduino Mega의 rich 빌드는 JMAP 등을 켠 별도 설정이며
Uno 설정과 같지 않다. 메모리·플래시 한도는 별도로 확인해야 한다.

### 3.2. 크기

아래 값은 [SIZES.md](../c/cross/SIZES.md)의 기록이다. 라이브러리 행은 빈 프로그램을 뺀
text 바이트 수이며, P1 probe는 메모리 매핑한 자모 페이스와 MONO_PAGE를 사용한다.

| 빌드 | AVR text | Cortex-M0+ text | 판정 |
|---|---:|---:|---|
| `minimal` | 12,930 | 6,162 | 정확히 일치하는 게이트 |
| `default` | — | 7,381 | 정확히 일치하는 게이트 |
| `minimal+RECOG` | 13,238 | 6,358 | 예산 13,250 / 6,366 |
| `minimal+JMAP` | 15,370 | 7,646 | 예산 15,532 / 7,688 |
| `minimal+JMAP+nolist` | 15,002 | 7,398 | 예산 15,032 / 7,398 |
| `ksonly` | 13,460 | 6,822 | 예산 13,648 / 6,900 |
| `minimal+BIG` / `minimal+BIG+V2` | 12,956 / 15,314 | 6,158 / 7,369 | 정보용 |

| 전체 프로그램·이미지 | text | data | bss | 비고 |
|---|---:|---:|---:|---|
| Arduino Uno | 23,676 | 18 | 1,085 | 페이스 10,124 B, `mcu-strict` |
| Arduino Mega, Uno 설정 / rich | 23,802 / 40,490 | 18 | 1,085 / 1,094 | 64 KiB 아래 PROGMEM만 읽음 |
| ESP32-C3 / S3 단색 | 22,174 / 20,576 | 0 | 1,088 / 1,092 | SDK 스텁 링크 |
| 원래 ESP32 (Xtensa LX6), P1 probe | 7,794 | 0 | 848 | 포트 이미지가 아닌 크기 측정 |
| Pico 단색, pico-sdk 2.3.1 | 35,484 | 0 | 2,384 | SDK 이미지 |
| CH582 단색 | 22,456 | 20 | 1,232 | SDK 이미지, RAM 사용 5,876 B |
| DOS `SVFDEMO.EXE` / WASM `svf.wasm` | — | — | — | 파일 크기 266,265 / 39,234 B |

### 3.3. 속도

[MEASUREMENTS.md](../c/bench/MEASUREMENTS.md)의 측정 환경과 Set A/B를 구별해야 한다.
아래 Set A 수치는 HGKEY6J로 잰 값이며 현재 단색 예제의 NEODG16G 수치가 아니다.

| 환경·작업 | 기록된 시간 | 예산 |
|---|---:|---|
| Pico 에뮬레이션 `-Os`, `syl_ga` | 48.39 µs | 50 µs 충족 |
| Pico 에뮬레이션 `-Os`, `syl_bwelk` | 58.23 µs | 50 µs 초과 (`-O2` 47.18 µs는 충족) |
| Pico 에뮬레이션 `screen32` | 1,498.39 µs | 2 ms 충족 |
| DOS 486DX2-66 `line40_mapped` | 11,876.45 µs | 16 ms 충족 |
| WASM `line40_mapped` | 13.74 µs | 1 ms 충족 |

측정은 대상 CPU 실기 전체의 성능 보장이 아니다. 에뮬레이터, 호스트, 컴파일러와 페이스의 영향을 받는다.
coverage·bpp별 출력과 비용은 [안티앨리어싱](anti-aliasing.ko.md)을 참고한다.

## 4. 알려진 한계

### 4.1. 렌더러와 포트

- Cortex-M0+ `minimal+JMAP+nolist`는 기록된 예산 7,398 B에 여유가 없다.
  인라인된 `jlist_` 심벌의 부재만으로 LIST 코드 누출을 검사할 수 없으므로 크기 게이트도 필요하다.
- Arduino Mega의 64 KiB 이상 PROGMEM far read는 지원하지 않는다.
- 원래 ESP32의 포트 이미지는 없으며 크기 측정만 있다. CH582M의 패널 오프셋·변형·LED 극성은 실기 확인이 필요하다.
- Arduino 예제의 스텁 빌드는 `arduino-cli`와 설치한 코어의 빌드를 대신하지 않는다.
- ScummVM 통합은 별도이다. 이 C 리더의 JSET 지원을 ScummVM의 기존 `jamo_set.h` 지원과 같다고 해석하면 안 된다.
- Pico의 위 `syl_bwelk` 예산, DOS cold 스트리밍·DX-33의 16 ms 목표는 아직 충족되지 않은 측정 행이 있다.

### 4.2. 입력과 맞춤

- HWP `.HFT`는 해독하지 않는다. 일부 한자·기호 파일은 BDF까지만 내보내거나 변환 경로가 없다.
- HWP 1.x의 세 페이스 이름은 추정이며 원본의 이름으로 확정하지 않는다. 현대 한글 조합에 사용하지 않는 옛한글 조각은 보존하지 않는다.
- HWP 3.0 16 px의 완성형 2,350자와 8x4x4 조합 결과는 항상 같지 않다. 완성형과 자모 페이스를 별도로 만든다.
- KS 원시 덤프와 큰 HWP 3.0 입력의 자모 세트는 맞춤 결과이며 원본의 정확한 분해가 아니다.
- HWP 1.x의 여러 페이스나 Dokkaebi 프린터 페이스를 함께 고르면 제안 이름이 충돌할 수 있으므로 이름을 바꾼다.
- Windows FNT/FON처럼 Unicode 문자 맵이 없는 입력은 maker가 경로 없이 표시할 수 있다.
- 마스크 맞춤의 명령줄 실행과 maker 전체 실행을 구별한다. 실제 조각 인식 모델은 검증되지 않았다.

형식별 세부 한계와 실행 조건은 [도구](tools.ko.md), [레시피](recipes.ko.md), [maker 기능 점검](maker-audit.ko.md)에 있다.

### 4.3. 데스크톱 앱

- Windows·macOS 패키지는 빌드하거나 실행하지 않았다. Linux glibc 2.39보다 오래된 환경의 호환성은 검증하지 않았다.
- Ubuntu 24.04.5에서 FUSE 마운트와 Xvfb 창 실행 기록은 있다. 실제 창 관리자·GPU·네이티브 대화상자·파일 관리자·샌드박스는 별도 검증이 필요하다.
- 자동 테스트는 대화상자를 스텁으로 바꾸고 GPU를 끈다. 실제 입력 파일 테스트는 사용자 사본을 가리키는 환경 변수가 필요하다.
- AppImage는 비트 단위 재현성을 보장하지 않고 자동 업데이트도 없다. LGPL 대응 소스 보관은 공개 릴리스 점검 조건이다.

## 5. 확장 후보와 검증 방법

GRAY4·회색 OLED 프로파일, SIMD, Pico PIO-DMA, u8g2·LVGL 연동은 현재 제공 기능과 구별한다.
ScummVM의 v3 페이스 통합과 게임별 묶음 재생성도 별도의 통합 작업이다.

주요 검사 진입점은 다음과 같다. 필요한 도구 체인과 선택적 의존성은 각 안내를 따른다.

| 대상 | 명령 |
|---|---|
| C 렌더러 | `make -C c check` |
| Python 도구 | `python3 -B -m unittest discover -s tools -p 'test_*.py'` |
| maker | `python3 -B -m unittest discover -s maker/test -p 'test_*.py'` |
| 데스크톱 단위 검사 | `npm test --prefix desktop` |
| 포트와 화면 | `sh c/cross/build-all.sh --ports` (필수 에뮬레이터가 없으면 화면 검사를 건너뛸 수 있음) |
| AppImage | `bash desktop/build/release-check.sh <AppImage> --release` |

## 6. 참고 문헌 / References

- SIL Open Font License 1.1 — <https://openfontlicense.org/open-font-license-official-text/>
- Electron 보안 권고 — <https://www.electronjs.org/docs/latest/tutorial/security>
- AppImage type2-runtime 20251108 — <https://github.com/AppImage/type2-runtime/releases/tag/20251108>
