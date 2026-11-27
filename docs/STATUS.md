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
| 포트 예제 | Pico, ESP32-C3/S3, Arduino Uno/Mega, CH582M, DOS, WASM, SDL2/SDL3 | [포트와 페이스](../c/ports/FACES.ko.md) |
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

- Windows NSIS·portable 빌드는 `windows-build` 브랜치에서 Actions를 통과했으나 main에는 아직 병합되지 않았다. macOS는 빌드하지 않았다. [플랫폼 상태](maker-desktop.ko.md#65-windows와-macos-2026-11-27-상태)를 참고한다. Linux glibc 2.39보다 오래된 환경은 미검증이다.
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

## 7. 기록 / Records

### 7.0. 상태 기록 (2026-11-22 기준, 11-23·11-27 추가 포함)

다음은 당시 구성 요소·연표·열린 일·결정·측정·한계의 기록이다. 제목의 기준일 이후에 추가된 HWP와
2026-11-27 라이선스 해석도 날짜 그대로 보존했다. 카드 ID는 기록 식별자이며 현재 지원 여부를 뜻하지 않는다.
당시의 “진행 중”, “미검증”, “비공개” 등은 현재 상태로 읽지 않는다. 현재 기능과 한계는 위의 1~5절을 따른다.
Windows의 별도 브랜치 빌드는 [패키징 안내의 2026-11-27 상태](maker-desktop.ko.md#65-windows와-macos-2026-11-27-상태)를 따른다.


이 문서는 2026-11-22 기준 저장소 전체의 상태 요약이다. 2026-11-01 판 이후의 일(11-03..11-22: 공개판, maker 입력 종류·컨트롤·로컬 모드, 데스크톱 앱, 문서)은 연표와 4, 6장에 더했다. 숫자는 모두 이름을 밝힌 파일에서 옮겼다: 크기는
`c/cross/SIZES.md`, 속도는 `c/bench/MEASUREMENTS.md`, 결정과 후속 과제는 `docs/superpowers/specs/*.md`의 "Implemented"
노트와 별도 연구 저장소(비공개)의 `docs/experiments/*.md`. 2026-11-01 부분의 기준 commit은 `main` 124baec (JMAP-LIST 병합 ca86268 + 실험 문서), 2026-11-22 부분의 기준은 `main` e1ef269 (C 렌더러 안내서 병합)이다. 열린 일은 2026-11-01의 작업 목록에서 옮기고 이후 끝난 것을 뺐다. C 라이브러리의 사용법은 [c/README.md](../c/README.ko.md).

공개판 주 (2026-11-03): 이 공개 저장소는 원본 저장소에서 SIL OFL 1.1 face (117개)와 도구를 골라 담았다. OFL이 아닌 face
(라이선스 미기재, MIT, san 1.0)은 제외하고, iolo SANS8J는 2026-11-27 소유자 승인으로 묶음 라이선스 선언을 해석해 OFL-1.1 폰트 예외로 포함했다, 게임 전용 bake 스크립트, Uno Seoul preset은 빠졌다
([NOTICE.md](../NOTICE.ko.md)). MCU 예제의 mono face는 HGKEY6J 대신 `svf/dos/NEODG16G.SVF` (Neo Dunggeunmo 6x2x1)다.
face마다 만드는 법은 [recipes/svf-faces.ko.md](recipes/svf-faces.ko.md)와 `tools/build/faces.tsv`. 공개 전(11-03 ec5c6b3 이전)의 commit 번호는 원본 저장소의 것이다. ec5c6b3 이후의 번호는 이 저장소의 것이다.

### 7.1. 구성 요소 한눈에

| 구성 요소 | 상태 | 위치 | 마지막 관련 commit / 문서 |
|---|---|---|---|
| SVF 포맷 v3 | done (포맷 기능 동결, 10-28) | `spec/SVF.md` | v3 전환 5f264c7 (10-22); JSET v1 표준·v2 예외 e2dfd59 (10-25) |
| JSET 계열: v1, v2, BIG, JMAP (dense/SPARSE), LIST | done | `spec/SVF.md` "Jamo-set fonts", "Version 3" | JMAP·BIG f880976 (10-27); LIST ca86268 (10-28) |
| C 렌더러 | done (유지보수) | `c/src`, `c/include/svf.h` | ca86268; plan `2026-10-27-jmap-list.md` |
| 포트 예제 | done; CH582 실기 첫 실행 보류 | `c/ports/{pico,esp32,arduino,ch582,dos,web,sdl}` | f880976 (Mega·ESP32 원본 size row 포함) |
| Python 도구 | done (유지보수) | `tools/`, [docs/tools.md](tools.ko.md) | `jamoexc.py` 47cc044, LIST 소비자 ee5db51 (10-28) |
| SVF maker | done (끝난 일은 아래 연표 11-03..11-22: 입력 종류 t_f3ef3189, 컨트롤과 WASM 미리보기 t_9acea7ab, 로컬 모드 t_cbd14d61, 로컬 모드의 제한된 수명 주기, busy 409, e2e T16, 샘플 세트 e2e). 서버 배포용 systemd unit은 없다(t_bbceabe9) | `maker/` | 병합 837f525 (10-23); LIST 대응 0d73568 (10-28); 97f7ce3 (11-17) |
| SVF maker 데스크톱 앱 | done (데스크톱 목표 종결 11-22): Electron 셸 + 동결 사이드카 + 정적 type2 AppImage 런타임(libfuse2 불필요), 릴리스 점검(`runtime` 포함)과 e2e(OFL 샘플 세트 포함). 깨끗한 Ubuntu 24.04.5 호스트에서 Xvfb 아래 시작 확인(11-22). Windows·macOS 미검증, 창 관리자가 있는 실제 데스크톱 미검증, LGPL 소스 보관은 릴리스 게이트 | `desktop/`, `maker/sidecar.py`, `docs/maker-desktop.md`, `docs/desktop-app.md` | t_f04f1355, t_e64a56a7; t_ea7dcc8e (4eb8e46), t_30b843b8 (4569676), t_afb4689b |
| WASM picker | done, parked minors 보류 | `web/`, `c/ports/web` | 병합 ed0e2d9 (10-21); JMAP 대응 c5f4efa (10-27) |
| 연구 도구·실험 | running / paused (아래 4장) | 별도 연구 저장소 (분리 11-01, 비공개) | 124baec (Malgun·Noto 실험, 11-01) |
| 한국어 문서와 안내서 | done (11-22): 공개 문서의 `*.ko.md` 쌍, 데스크톱 앱 설치·사용 문서, C 렌더러 안내서 플랫폼·임베딩 | `*.ko.md`, `docs/desktop-app.md`, `docs/c-renderer-guide.md` | 3d40de8, e5a6c39, e1ef269 |
| ScummVM 연동 | todo | ScummVM `graphics/hires_text` | spec `2026-10-26-jset-limits-design.md` follow-up (a) |

### 7.2. 연표 (git log와 plan 파일 이름 기준)

| 날짜 | 무엇 | 근거 |
|---|---|---|
| 10-19 | 저장소 시작: ScummVM jamo 도구와 face 이전, SVF spec, facecheck baseline; 분할 연구 구출 | abe401b, c6debee, 8b1d3b8 |
| 10-19 | 이식 가능한 C 렌더러 설계와 계획 | c2fb1c6, 17692bd, `plans/2026-10-19-c-svf-renderer.md` |
| 10-20 | C 렌더러 병합; blit fast path와 `SVF_TARGETS` 병합 | c3f04f5, eb41629, `plans/2026-10-20-blit-fast-paths.md` |
| 10-20 | face 선택, MCU 포트, VESA packed kind, WASM picker 계획 | `plans/2026-10-20-{face-selection,mcu-ports,vesa-packed-kinds,wasm-picker}.md` |
| 10-21 | WASM picker 병합, `docs/tools.md` 병합, MCU 포트·VESA 브랜치에 main 병합 | ed0e2d9, c88f72a, 1b92237, ec52b14 |
| 10-21 | SVF v3, C speedups, SVF maker 계획 | `plans/2026-10-21-{svf-v3,c-speedups,svf-maker}.md` |
| 10-22 | v3 only: face 153개 v3 변환, v2 제거 | 5f264c7, a9829ae |
| 10-23 | SVF maker 병합; C speedups 6-11 병합; compact JSET 설계·계획 | 837f525, c592140, 474ce30, 56176c3 |
| 10-24 | CH582M 포트 병합; SDL 대상 설계 | e5232ca, 9977621 |
| 10-25 | JSET v1 표준, v2는 요청 시만 (Amendment 3); SDL 계획 | e2dfd59, cc3e94d |
| 10-26 | SDL2/SDL3 대상과 GRAY kind 완료; Mac fbit 변환 도구; JMAP/BIG 설계와 계획 | 2fb312d, 33deba5, 2ff39ad, ecda358 |
| 10-27 | JSET v3 (JMAP) 리더, BIG 한도, `SVF_JMAP_RECOG`, Uno preset, Mega·ESP32 원본 size row | 51a4020, 51c02a0, 6e4317d, 84ae0cf, 67a8ae0; main f880976 |
| 10-27 | JMAP-LIST 설계와 계획 | `specs/2026-10-27-jmap-list-design.md`, `plans/2026-10-27-jmap-list.md` |
| 10-28 | JMAP-LIST 병합; 조합형 문헌 노트와 연구 백로그 | ca86268, 4d76741, 0a085e7 |
| 11-01 | 맑은 고딕·Noto 조합 조각 12 px 실험 문서 | 124baec |
| 11-03 | 공개판: SIL OFL 1.1 face와 도구만 담은 선별 공개 저장소의 첫 commit | ec5c6b3 |
| 11-03 | maker 새 입력 종류(TTC·가변 폰트·Mac 컨테이너·PCF·DOS 원시 폰트, 12x24 영문 동반 파일)와 소스 단계 | t_f3ef3189 (01a943f) |
| 11-04 | maker 컨트롤과 WASM 미리보기: 클리핑 probe, 분해 가능한 폰트의 자모 경로(mask fit, vector fit), 선택적 정체성 검사 | t_9acea7ab (ce976f8) |
| 11-05 | maker 로컬 모드(독점 입력을 로컬에서만 변환): Sources 해석기, 파일 디렉터리, Mac fbit·HWP 입력, 셸 계약 | t_cbd14d61 (94011ff) |
| 11-09 | 데스크톱 앱 병합(Electron 셸 + 동결 사이드카 + Linux AppImage); T15 재조정(서버 unit 없음) | 4278d28 (t_f04f1355, t_e64a56a7); 004a449 |
| 11-15 | 데스크톱 후속(5a3c7b2 병합 전 검토에서 나온 것): 릴리스 점검이 모든 분기에서 닫힌 채 실패(fail closed), `verify-report.sh`는 정확한 결과 줄만 받음, `third-party.mjs`, 도구 세트 가지치기 | 587dfb5 (t_951f7c7b) |
| 11-15 | F1: mkfont 경로가 `build_faces.py`처럼 출력을 정규화함 | 05a450c (t_df773bf5) |
| 11-17 | maker 로컬 모드의 제한된 수명 주기(시작, 중지, 활성화): 호출자의 마감 시한 안의 rename, 대기 기록, 고아 정리, 펜스, 시작 시 묘비 정리 | 97f7ce3 (t_d1aba4b8) |
| 11-17 | SVF maker T16 end-to-end: 업로드·로컬 혼합 폴더, 프리셋 인수, 느린 fit(`SVF_MAKER_SLOW=1`), Chrome으로 구동한 UI smoke | 084ca27 (t_e073891a) |
| 11-18 | maker 페이지가 busy / 준비 중 409에 재시도하거나 설명함 (busy 종류, `Try again`, stale) | 4a83d55 (t_39c9fb52) |
| 11-18 | 실행 충돌(409) 때 입력한 폼 수정과 더 새로운 저장을 지킴 | eab664a (t_6daa1bc7) |
| 11-20 | probe 대 delete 경쟁 테스트가 부하에 독립적임 (잠금 밖에서 멈추고 추적을 검증) | 8b451d5 (t_4316ea37) |
| 11-20 | 정적 type2 AppImage 런타임(appimage@1.0.3 도구 세트), libfuse2 불필요, 릴리스 점검 `runtime` | 4eb8e46 (t_ea7dcc8e) |
| 11-20 | 데스크톱 앱이 OFL 샘플 세트와 합성 Mac/HWP/BDF 샘플을 UI로 변환하는 e2e (두 패스) | 4569676 (t_30b843b8) |
| 11-22 | 공개 문서의 한국어 쌍(`*.ko.md`)과 데스크톱 앱·C 렌더러 안내서 | 3d40de8 |
| 11-22 | 데스크톱 앱 설치·사용 문서(Quick start, 체크아웃에서 빌드, 메시지, 복구) | e5a6c39 (t_9b9e0bd8) |
| 11-22 | C 렌더러 안내서 플랫폼·임베딩·페이스 고르기와 포트 README 갱신 | e1ef269 (t_847e4d29) |
| 11-23 | HWP 폰트 리더 `tools/hwpfont.py`: HWP 1.x `.SFT`/`.PFT`(`jamoset.py --layout hwp1`, HWP.EXE 규칙 그대로의 자모 세트), HWP 3.0 `.FNT`(`--layout 844-hwp3`), 헤더 없는 KS X 1001 덤프; maker 종류 `hwp1`, `ks-raw`와 경로 넷 | t_d4cf7f46 |
| 11-22 | 데스크톱 목표 종결: 커밋 3d40de8에서 빌드한 AppImage를 깨끗한 Ubuntu 24.04.5 호스트(libfuse2 없음)에서 Xvfb 아래 시작, 창이 그려지고 로컬 모드 변환이 패키지된 사이드카로 실행됨 | t_afb4689b; `docs/desktop-app.md` 13절 |

### 7.3. 현재 기능 표 (무엇을 읽는가, 얼마나 큰가)

기본 빌드가 읽는 JSET 형태 (`svf.h`의 기본값을 각 toolchain의 `-dM -E`로 2026-11-01 확인; 자세한 표는
[c/README.md](../c/README.ko.md) "Jamo sets: what each build reads"):

| 대상 | v1 | v2 | BIG | JMAP dense/SPARSE | LIST | 스트리밍 | 스케일 |
|---|---|---|---|---|---|---|---|
| host, DOS, WASM, SDL | 예 | 예 | 예 | 예 | 예 | 예 | 예 |
| Arduino Uno (AVR, 포트 flag) | 예 | 아니오 (`JSET_UNREAD`) | 아니오 | 아니오 (`JSET_BAD`) | 아니오 | 아니오 | 아니오 |
| Cortex-M0+/M33, ESP32, CH582 (기본값) | 예 | 예 (CH582 포트는 v1만) | 아니오 | 아니오 | 아니오 | 예 (Uno·CH582·M0+ P1/P2 프로필은 끔) | 포트는 끔 |

크기 (모두 `c/cross/SIZES.md`, text bytes; P1 probe = mapped jamo face 하나, MONO_PAGE):

| 행 | AVR | Cortex-M0+ | 성격 |
|---|---:|---:|---|
| `minimal` (Uno flag, v1 리더만) | 12,930 | 6,162 | gate (정확히 일치) |
| `default` | - | 7,381 | gate |
| `minimal+RECOG` | 13,238 | 6,358 | budget 13,250 / 6,366 |
| `minimal+JMAP` (LIST 포함) | 15,370 | 7,646 | budget 15,532 / 7,688 |
| `minimal+JMAP+nolist` | 15,002 | 7,398 | budget 15,032 / 7,398 (여유 0) |
| `ksonly` | 13,460 | 6,822 | budget 13,648 / 6,900 |
| `minimal+BIG` / `minimal+BIG+V2` | 12,956 / 15,314 | 6,158 / 7,369 | info |

프로그램 전체 ("Port examples", "Pico SDK images", "CH582 SDK image"):

| 이미지 | text | data | bss | 비고 |
|---|---:|---:|---:|---|
| Arduino Uno, NEODG16G | 23,676 | 18 | 1,085 | face 10,124 B (`mcu-strict`) |
| Arduino Mega (Uno flag / 전부 켬) | 23,802 / 40,490 | 18 | 1,085 / 1,094 | 64 KB 아래 PROGMEM만 |
| ESP32-C3 / ESP32-S3 mono | 22,174 / 20,576 | 0 | 1,088 / 1,092 | stub link |
| ESP32 원본 (Xtensa LX6) P1 probe | 7,794 | 0 | 848 | size row만, 포트 이미지 없음 |
| Pico mono (pico-sdk 2.3.1 실제 이미지) | 35,484 | 0 | 2,384 | |
| CH582 mono (SDK 실제 이미지) | 22,456 | 20 | 1,232 | RAM used 5,876 B |
| DOS `SVFDEMO.EXE` / WASM `svf.wasm` | 266,265 / 39,234 bytes | | | 파일 크기 |

속도 (`c/bench/MEASUREMENTS.md` "Results"; Set A는 공개판에 없는 HGKEY6J로 잰 값이고 NEODG16G로 다시 재지 않았다): Pico `-Os` MONO_PAGE `syl_ga` 48.39 µs (예산 50 µs 충족), `syl_bwelk`
58.23 µs (**미달**, `-O2` 47.18 µs는 충족), `screen32` 1,498.39 µs (예산 2 ms); DOS 486DX2-66 `line40_mapped` 11,876.45 µs
(예산 16 ms 충족; cold 스트리밍과 DX-33 행은 미달); WASM `line40_mapped` 13.74 µs (예산 1 ms).

### 7.4. 열린 일 (2026-11-22)

주제별로 묶었다. "보류"는 계획만 있고 진행하지 않는 일이다. 2026-11-01 판의 열린 일 중 "SVF maker web UI v1; systemd unit, README, docs (T15); end-to-end 시험 (T16)"은 끝났다 (web UI v1 목표 t_a1cf496b는 11-09에 로컬 실행으로 재조정, T15 재조정 004a449·t_bbceabe9, T16 t_e073891a 11-17, 데스크톱 앱 목표 11-22). 아직 남은 빈틈은 6장에 있다.

**페이스 품질 연구 (학습 없음; 11-01 정리)**

- done: 상위 목표 (124baec), approach P, gothic 12 px 생성·refinement, 맑은 고딕·Noto 조각 실험.
- cancelled (사용자 결정 11-01; 발견은 연구 저장소의 `experiments/research-backlog.md`에 보존): R1 평가 함수 기반
  직접 탐색, R6 레이아웃 보정, R5 평가 함수 신뢰도, Galmuri 조합화 (10-26 폐기), SAM8J Uno face.

**작은 MCU와 Uno**

- Uno true-minimal 빌드 (나머지 ifdef). 하드코딩 JSET은 폐기, 표 기반 유지. (Uno Seoul preset은 Apple 파생 데이터라 이 공개판에 없다.)
- CH582M 실기 첫 실행 (패널 offset/variant/LED 극성) + 남은 review 항목.

**C 렌더러 확장 (모두 보류)**

- GRAY4 kind와 grey OLED 프로필; SIMD 경로 (MMX/SSE/NEON/DSP/simd128, byte-identical).
- Pico `syl_bwelk` 50 µs 미만과 PIO-DMA; DOS cold·uncached·DX-33 16 ms 미만.
- Pico `-Os` 단일 kind 빌드가 전체 kind 빌드보다 느림 (6335 대 6070 cycles).
- u8g2 연동; LVGL v9 font driver.

**도구와 페이스 묶음**

- ScummVM `hires_text`가 이 C 렌더러를 쓰게 하고 SVF pack 17개를 v3로 다시 빌드.
- Dig·Full Throttle pack의 v1 hi-res face를 v3로 (사용자 판정으로 v3 재빌드에서 제외됐던 것).
- NKP (1989 Hercules 한글 TSR) jamo face, layout `nkp-821`.
- WASM picker parked minors.

연구 백로그 전체 (R1-R11)와 실험 목록·결정 기록·용어집은 별도 연구 저장소(비공개)의 `experiments/research-backlog.md`,
`experiments/README.md`에 있다.

### 7.5. 유효한 결정

| 날짜 | 결정 | 출처 |
|---|---|---|
| 10-21 | SVF v3 승인, v2 폐기 (v2 파일은 `tools/svf2to3.py`로 변환) | experiments/README.md 결정 기록; 5f264c7 |
| 10-24 | JSET v1이 표준, v2는 요청 시만 (Amendment 3) | experiments/README.md; e2dfd59 |
| 10-26 | 학습 보류: GPU는 점수 계산에만 ("점수계산만 쓰고 학습은 일단 보류") | experiments/README.md, process-lessons.md |
| 10-26 | Galmuri 12 px 조합화 폐기; Galmuri piece로 SAM 구조 face를 만들지 않음; face-pure SAM/SANS 경로도 중단, Uno는 Seoul12 기반 | galmuri-jamo-split.md, uno-12px.md, 사용자 결정 |
| 10-26 | Mac face는 원본 구조가 canonical (JMAP), 축소 face는 derivative | experiments/README.md |
| 10-27 | 하드코딩한 Seoul 전용 JSET 조합은 폐기, 표 기반 JSET 유지 (ifdef 최소화만) | 작업 기록; jset-limits spec follow-up (j) |
| 10-27 | JMAP-LIST: N ≤ 255 (u8), plane 15만, LIST=0 빌드와 RECOG는 header 규칙만, `SVF_JMAP` 없는 LIST 리더 없음 (9.11) | `specs/2026-10-27-jmap-list-design.md` Implemented |
| 10-28 | 포맷 표현력은 충분 (JSET v1/v2, BIG, JMAP, LIST); 새 포맷 기능 없음; 노력은 페이스 품질 연구로 | 작업 기록 |
| 상시 | Apple·Windows·Galmuri 파생 데이터와 bitmap은 로컬 전용, git에는 수치·경로·hash만 | experiments/README.md "데이터 취급"; malgun-noto-jamo-studies.md |
| 상시 | 렌더러는 기본 byte-identical (svfline.py 기준), fast mode만 허용 오차 | experiments/README.md 규칙 |
| 상시 | 라이선스는 face 선택 기준이 아님 (pack은 배포하지 않음); 단 이 공개 저장소에는 SIL OFL 1.1 face만 담으며, iolo SANS8J는 위의 승인된 예외이다 | experiments/README.md 규칙; 공개판 |
| 미정 | 연구 부분의 저장소 분리: 현재 연구가 끝날 때까지 보류였고 그 연구(맑은 고딕·Noto)는 끝났으므로 **논의 예정** | 사용자 지시; research-backlog.md 머리말은 분리를 백로그 밖 정리 작업으로만 언급 |

### 7.6. 알려진 빈틈과 위험

- **M0+ `minimal+JMAP+nolist` budget 여유 0** (7,398 / 7,398): LIST=0 arm이나 JMAP 리더에 1 byte만 늘어도 gate가 깨진다.
  올리는 것은 판정 사항이다 (`c/cross/SIZES.md` "JMAP-LIST identity, budgets and follow-ups", jmap-list spec follow-up (h)).
- **`check_absent ... jlist` 규칙은 공허하다**: `-Os`에서 `jlist_` symbol이 남지 않아 실패할 수 없다. 실제 누수 방어는
  `+nolist` size row와 `test_jmap_nolist_identical` (jmap-list spec follow-up (k)).
- **Arduino Mega 64 KB 넘는 far read 미지원** (`pgm_read_byte_far` 필요; SIZES.md "Port examples", jset-limits spec (h)).
- **ESP32 원본 (Odroid-Go) 포트 이미지 없음**: size row만 있고 이미지에는 새 driver와 board 코드가 필요
  (SIZES.md "Port examples"). 사용자가 실기 16 bpp를 따로 확인 (jset-limits spec (k), (l)).
- **ScummVM `jamo_set.h`는 v3 JSET block을 거부** (plain face): ScummVM 연동 전까지. 그 전에 v1 한도를 읽으려면
  `kJamoMaxInitSets`/`kJamoMaxMedSets` 32/24, `kJamoSetMaxSize` 12,321 수정 필요 (jset-limits spec (a); jmap-list spec (b)).
- **DOS DX2-66 행 약 +105 µs (+0.9 %) 설명 안 됨**: 51a4020 probe에서 모든 행이 균일하게 이동, 원인 미규명, DOS 표 재측정
  안 함 (MEASUREMENTS.md "Results").
- **Pico `syl_bwelk` 50 µs 미달**: `-Os` 58.23 µs (MEASUREMENTS.md).
- **`arduino-cli`는 실행하지 않았다**: Arduino 코어가 설치되어 있지 않아 스케치를 `arduino-cli`로 빌드하거나 실행한 적이 없다 (`c/ports/arduino/README.md`).
- Mega 행에 JMAP 열 없음, AVR BIG 포트 (BIG + `SVF_NO_STREAM`/`mcu-strict`)는 fuzz 대상 없음 (jset-limits spec (g), (m)).

**HWP와 KS 원시 폰트 (2026-11-23, t_d4cf7f46)**

- **HWP 2.x / 3.0 `.HFT`는 읽지 못한다**: "HWP 2.0 font file", "Han Unified Font File 1.0" 헤더의 윤곽선 또는 획 폰트(HWP 3.0 CD에
  160개)로, 헤더만 살폈고 해독기는 없다 (recipes/dos-fonts.ko.md "HWP 1.x와 2.x 폰트").
- **HWP 1.x 페이스 이름은 메뉴 순서로 추정했다**: 페이스 0/1/2 = 명조/고딕/샘물은 HWP.EXE 메뉴 순서일 뿐 증명되지 않았다
  (johab-fonts notes/hwp1.md). 옛한글 조각(초성 20-31, 중성 22-29, 종성 28-31)은 유니코드 음절이 없어 버린다.
- **기호·한자 파일은 페이스가 되지 않는다**: HWP 1.x `SPECIAL*`, `JAPAN`, `USER*`, `SYSTEM.PFT`는 목록에만, `HANJA.SFT`와 HWP 3.0
  `HAJ16_0.FNT`는 `hwpfont.py bdf`로 BDF까지만 간다. 태백의 `HANJA*.PFT`, `SPC*.PFT`, `USER*.PFT`(크기로만 아는 한자·기호 덤프)는
  여전히 `hwp-pft` "other"이다.
- **HWP 3.0 16 px FNT의 2,350자와 8x4x4 세트는 한 페이스로 합쳐지지 않는다**: 완성형 2,350자 중 1,700-2,221자(필기체는 375자)만 그
  세트의 조합과 같다. 2,350자는 완성형 페이스, 11,172자는 `844-hwp3` 자모 세트로 따로 만든다 (JMAP LIST로 합치는 것은 하지 않았다).
- **KS 원시 덤프와 24 px 이상 HWP 3.0 FNT의 자모 세트는 맞춤이다**: 음절 통째의 디자인이라 IoU 0.62-0.82(태백 GHAN24 0.710, HWP 3.0
  HAN24 0.819, HAN40 0.687). adaptive 레이아웃은 시험하지 않았다.
- maker는 HWP 1.x / 3.0 파일을 로컬 모드에서만 변환한다(업로드는 "HWP font: not converted here (local-only mode)"); 헤더 없는 KS 덤프는
  DOS 원시 폰트처럼 크기로 두 모드 모두 읽는다. HWP 1.x 한 파일의 페이스 셋은 같은 이름(예: `HANG16J.SVF`)을 제안하므로 함께
  고르면 이름을 바꿔야 한다(Dokkaebi 프린터 페이스와 같다).

**데스크톱 앱과 문서 (2026-11-22)**

- **Windows·macOS 패키지는 만들지도 실행하지도 않았다**: 서버가 Windows 준비가 안 되어 있고(프로세스 그룹, 잠금, 파일 링크 호출이
  POSIX), macOS는 서명·공증 계획만 있다 (`docs/desktop-app.md` 13절, `docs/maker-desktop.md`).
- **창 관리자와 GPU가 있는 실제 데스크톱에서는 검증하지 않았다**: 증거는 Xvfb 아래의 창 실행(작성자 호스트와 깨끗한 Ubuntu
  24.04.5)과 FUSE 마운트 시작(`docs/maker-desktop.md`)까지다. 디스플레이가 있는 네이티브 대화상자, 파일 관리자 연동, 창 관리자와
  함께 하는 실제 FUSE 마운트 시작, GPU 경로, 샌드박스된 렌더러는 **아직 하지 않은 수동 점검**이다. 자동 테스트는 대화상자를
  스텁으로 바꾸고 GPU를 끈다.
- **`mask fit`**: 2026-11-22에 freetype-py와 uharfbuzz를 스크래치 폴더에 설치해 `jamoset.py`의 마스크 맞춤을 neodgm, Noto Sans CJK KR, 맑은 고딕으로
  실행했다(recipes/outline-fonts.ko.md). 작성자 호스트의 시스템에는 라이브러리가 여전히 없어서 maker의 정체성 검사는 스텁으로만 테스트했다. 실제 Mac, HWP,
  Johab 파일은 환경 변수가 사용자 자신의 사본을 가리킬 때만 테스트되고, 저장소의 테스트는 합성 입력을 쓴다. 레시피는 2026-11-22에 실제 원본
  (Mac fbit 1.0 / 7.1, HWP 1.20 / 2.1, DOS 원시 폰트, 스트라이크, hanterm, HBF)으로 실행했고(recipes.ko.md), 그 실행에서 나온 빈틈은 `docs/tools.ko.md`
  "도구의 남은 한계"에 있다: Windows FNT/FON은 아무것도 그리지 못한다(maker는 경로 없이 "no Unicode character map"으로 표시한다). 그 실행의
  다른 빈틈은 고쳐 병합됐다: maker는 HangulTalk 1.0 `fbit`를 서술자 표로 감지해 `mac fbit 1.0` 경로를 주고, `.bin.gz`뿐인 HBF를 라틴 절반으로
  받는다(faf981e). 비트맵 전용 Mac TrueType은 스트라이크의 advance로 구워진다(t_cf52974e), `--eng`는 40 / 48 px 영문 폰트도 받는다(t_262e222d;
  둘 다 main 2e80647). `.dfont`와 SAGA IHNM(`844-ihnm`)은 원본을 찾지 못해 실행하지 않았다.
- **AppImage는 비트 단위로 재현되지 않고** 자동 갱신도 없다. LGPL 소스 보관은 릴리스 게이트다.
- 이 저장소는 공개 전까지 비공개이다 (`docs/maker-desktop.md`).
