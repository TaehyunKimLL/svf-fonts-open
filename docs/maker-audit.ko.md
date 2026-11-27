[English](maker-audit.md) | **한국어**

# SVF maker 기능 점검

SVF maker의 입력, 변환 경로, 설정, 미리 보기와 실행 경계를 설명한다.
사용법은 [데스크톱 앱](desktop-app.ko.md), 패키징은 [데스크톱 구현](maker-desktop.ko.md),
명령줄 대응은 [레시피](recipes.ko.md#데스크톱-앱과-maker-경로), HTTP API는
[maker 안내](../maker/README.ko.md)를 참고한다.

## 1. 입력과 변환 경로

경로는 `maker/routes.py`의 `routes()`가 제시한다. **native**는 그 입력 종류에 대한 기본 경로라는
분류이며, 원본 전체를 무손실로 보존한다는 뜻은 아니다. 비기본 경로는 폰트별 `experimental` 허용이 필요하다.

| 입력 | 완성형 경로 | 자모 세트 경로와 조건 |
|---|---|---|
| 아웃라인 TTF/OTF | `mkfont` | 합성 글리프 폰트의 `composite`; 그 밖의 `experimental fit`; GSUB 자모 치환이 있는 폰트의 `mask fit`; `vector fit` |
| TTC, 가변 폰트, Mac cmap·컨테이너 | 선택한 페이스·인스턴스·문자 매핑을 준비한 뒤 해당 경로 사용 | 준비된 폰트의 종류에 따라 위 경로 사용 |
| 비트맵 전용 sfnt, ISO 10646 BDF/PCF | `mkfont`, 원본에 있는 크기, 1 bpp | 직접 경로 없음 |
| KS C 5601 BDF/PCF | `bdfface`, 라틴 동반 폰트 필요 | `bdfface + from-svf fit`(experimental) |
| Hanterm Johab BDF/PCF | 직접 경로 없음 | `hanterm`, `hanterm-johab` 레이아웃 |
| ISO 8859 BDF, HBF | 독립 경로 없음 | KS C 5601의 라틴 동반 폰트로만 사용 |
| DOS 원시 조합형 폰트 | 지원하는 16 px 8x4x4 입력의 `johab844` | `dos raw`; 파일 크기로 나온 후보 중 레이아웃 확인 필요 |
| HWP 1.x `.SFT`/`.PFT` | `hwp bdf + mkfont` | `hwp1`; 로컬 모드 전용 |
| HWP 3.0 `.FNT`, 헤더 없는 KS X 1001 덤프 | `hwp bdf + mkfont` | 16 px HWP 3.0의 `hwp3 844`; `hwp bdf + from-svf fit`(experimental) |
| Mac HangulTalk 1.0 | 직접 경로 없음 | `mac fbit 1.0`; `fdef`가 있는 리소스 포크 필요, 로컬 전용 |
| Mac HangulTalk 7.1 type-3 `fbit` | `mac fbit 7.1 bdf + mkfont` | `mac fbit 7.1 direct`, `mac fbit 7.1 derived`(experimental); HTBL 필요, 로컬 전용 |
| 기존 SVF v2/v3(1·2 bpp) | `copy`, 또는 TTF/BDF만 쓰는 `svf2ttf` | 자모 페이스의 `copy`/`svf2ttf`; 1 bpp 완성형의 `from-svf fit`(experimental) |
| 알려진 ROM 세트 | 레시피가 지정한 `bdfface` 등 | 레시피별 `spec`, `dos raw`, fit 등; 로컬 전용, 파일 크기·SHA-256과 동반 파일 확인 |

HWP 1.x와 헤더로 식별한 HWP 3.0은 로컬 모드에서만 변환한다. 헤더 없는 KS 덤프는 업로드 모드에서도 읽는다.
SVF v2는 `copy` 경로에서 v3로 변환하며, SVF v1과 8 bpp SVF는 maker 경로를 제공하지 않는다.
HWP `.HFT`와 해독하지 못하는 `.PFT`는 변환 경로가 없다. 폰트로 인식되지 않거나 동반 파일이 빠진 입력은
이유를 표시하며, 경로가 없는 행은 선택할 수 없다. ROM 레시피는 `maker/recipes/`에 있다.

감지는 `maker/detect.py`, 폰트 준비는 `maker/srcprep.py`, 경로 검증은 `maker/settings.py`가 담당한다.
합성 입력 검증은 `test_detect_inputs.py`, `test_plan_inputs.py`, `test_hwp_inputs.py`,
`test_recipe.py` 등 `maker/test/`의 테스트에 있다. 실제 파일 검사는 해당 `SVF_MAKER_REAL_*` 변수가 있어야 실행된다.

## 2. 설정과 도구 대응

| 설정 | 현재 동작 | 구현 |
|---|---|---|
| 기본 일괄 설정 | `dest=dos`, 완성형, `layout=844`, 크기 16, bpp 1·2, 범위 `2350`, 프리셋 `plain` | `settings.BATCH_DEFAULTS` |
| 범위 | `2350`, `11172`, `ksx1001-nohanja`, `ksx1001-symbols`, `ksx1001`, `jamo`, `cp949` 또는 배치의 목록 파일; 생성 범위에 ASCII 추가 | `settings.RANGE_FILES`, `routes.py` |
| 셀·ascent·advance | `mkfont`의 셀·ascent·폭·공백 advance, `jamoset`의 헤더 ascent·fit 기준선, `bdfface`의 라틴·한글 ascent | `presets.panel_argv()` |
| 클리핑 | `clip_cell`, `fit_cell`, 사전 probe와 행별 클리핑 표시; 완성 후 mkfont 보고서의 잘림·이동·축소 결과 | `settings.py`, `maker/static/clip.js`, `tools/mkfont.py` |
| 자모 맞춤 | `aa_refine`, 2 bpp의 `clean`, 1 bpp의 `binarize`(threshold/ridge/mono); 경로가 지원하는 값만 허용 | `presets.py`, `settings.py` |
| 글리프별 수직 이동 | 완성형의 dy 표를 `svfdy.py` 단계로 적용; 미리 보기에서 시험 가능 | `settings.py`, `maker/static/svfview.js` |
| 내보내기 | TTF/BDF, 자모 TTF의 `--composite`; 기본은 모두 꺼짐, 폰트별 덮어쓰기 가능 | `settings.DEFAULT_OPTIONS`, `jobs.py`, `tools/svf2ttf.py` |
| 조각 정체성 | 선택적 외부 인식기의 점수; 내장 모델 없음 | `caps.py`, `recog_score.py` |

표의 기본값을 모든 폰트가 그대로 사용할 수 있는 것은 아니다. 비트맵 경로 등은 크기와 bpp를 제한하므로
저장·실행 전에 유효성을 검사한다. 고급 옵션은 프리셋을 덮어쓰며 폰트별 값은 일괄 설정을 덮어쓴다.
`--punct-extra`, `--ink-advance`, `--fallback-ttf` 등 모든 명령줄 옵션을 UI에서 제공하지는 않는다.
도구의 전체 옵션은 [도구 안내](tools.ko.md)를 참고한다.

`mask fit`과 `binarize mono`에는 freetype-py와 uharfbuzz가 필요하며 `JAMOSET_PYLIB`로 경로를 지정할 수 있다.
마스크 폰트는 `JAMOSET_MASK_FONT`로 지정한다. 인식기는 `SVF_RECOG_DIR`의 `recog.py`와 선택적
`SVF_RECOG_PYTHON`을 사용한다. 외부 인터프리터는 numpy·torch·PIL·fontTools import 검사를 통과해야 한다.

## 3. 미리 보기와 품질 검사

생성된 페이스는 C 렌더러의 WASM 빌드로 페이지에서 그린다. `maker/build-wasm.sh`와 `web/build.sh`는
`c/ports/web/emcc-flags.sh`를 공유한다. 폰트 구조와 메트릭은 [SVF 명세](../spec/SVF.ko.md),
합성은 [자모 세트](jamo-sets.ko.md), coverage와 타깃별 색 변환은 [안티앨리어싱](anti-aliasing.ko.md)을 참고한다.

`maker/static/svfview.js`는 텍스트, 스케일, GRAY8·MONO·RGB565 타깃, 임계값, 가이드, 글리프 격자를 제공한다.
ascent와 dy 시험은 페이지의 글리프 합성기가 수행한다. FreeType이 읽는 원본 폰트의 PNG는 서버의
`preview.source_png()`가 만들며, 결과 SVF의 페이지 표시는 서버 PNG에 의존하지 않는다.

`/api/jobs/<id>/` 아래의 `face/<step>.svf`, `source/<font>.svf`, `report/<step>.json`,
`probe/<font>/<size>/<bpp>.svf`·`.json`, `identity/<step>.json` 등이 결과와 probe를 제공한다.
`/api/caps`의 공개 키는 `wasm`, `mask_libs`, `recog`, `local` 네 개이다.
C/WASM 내보내기 함수는 `c/ports/web/svf_web.c`에 있으며 사용법은 [웹 렌더러](web-renderer-guide.ko.md)에 있다.

`--check`로 모든 현대 한글 음절 11,172자의 조합 가능성을 검사하는 것과 조각이 올바른 자모인지 판정하는 것은 다르다.
IoU도 기준 비트맵과의 겹침 정도이며 가독성을 보장하지 않는다.
TTF/BDF 내보내기는 다시 읽어 문자 집합을 확인하지만 TTF를 다시 래스터화하는 왕복 검사는 매 실행에 포함하지 않는다.

## 4. 로컬 모드와 데스크톱 경계

토큰을 설정한 로컬 모드는 루프백 바인딩만 허용한다. 선택한 소스를 제자리에서 읽고 결과와 임시 파일을
출력 폴더에 쓰며, 소스를 데이터 폴더로 복사하지 않는다. 작업 메타데이터는 데이터 폴더에 따로 둔다.
경로는 절대 경로·심벌릭 링크·입출력 겹침·데이터 폴더·`SVF_MAKER_ROOTS` 허용 목록을 검사한다.
임시 `.svf-maker-<id>/`는 정리 대상이며, 정리에 실패하면 다음 시작 때 재시도할 기록을 남긴다.

토큰 없는 서버는 업로드 모드이다. 요청 본문 한도는 64 MiB, 작업은 256 MiB·2,000파일이며,
gzip 해제 한도는 128 MiB이다. 로컬 모드는 업로드 복사 한도를 적용하지 않지만 형식별 읽기 한도는 적용한다.
서버는 작업 수 20개·생성 후 7일 기준으로 오래된 완료 작업을 정리한다. 로컬의 감지된 작업이 30분 동안
변경되지 않으면 작업 파일 디렉터리를 회수할 수 있다(`server.LOCAL_IDLE_SWEEP_S`).

Electron은 실행마다 토큰을 생성하고 `userData` 아래 데이터 폴더를 지정하며 사이드카 수명을 관리한다.
상세 보안·실패 처리·파일 위치는 [데스크톱 앱](desktop-app.ko.md)에 있다.
`SOURCE_DATE_EPOCH`는 직접 실행한 서버가 도구에 전달하지만 데스크톱 셸의 환경 허용 목록에는 없다.

## 5. 검증 경계

- 자동 입력 테스트는 합성 파일을 사용한다. 실제 Mac·HWP·ROM 원본은 사용자가 별도로 제공해야 한다.
- 마스크 맞춤 명령줄 실행 기록은 [레시피](recipes.ko.md)에 있다. 그것이 maker의 전체 `mask fit` 실행을 검증하지는 않는다.
- 조각 인식기의 실제 모델은 검증되지 않았으며 통합 테스트는 스텁을 사용한다.
- 데스크톱 자동 테스트는 대화상자를 스텁으로 바꾸고 GPU를 끈다. 실제 대화상자·파일 관리자·창 관리자·GPU·샌드박스 검증은 별도이다.
- Windows·macOS 패키지와 오래된 glibc 호환성은 검증하지 않았다. 서버 배포용 systemd unit은 제공하지 않는다.

사용 가능한 테스트와 패키지 검증은 [패키징 안내](maker-desktop.ko.md#5-자동-검증과-기록된-실행)에 있다.
렌더러 통합은 [C 가이드](c-renderer-guide.ko.md), 구조는 [렌더러 설계](../spec/renderer-design.ko.md),
문서의 시작점은 [README](../README.ko.md)를 참고한다.

## 6. 참고 문헌 / References

- Unicode Hangul composition — <https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/>
- OpenType Hangul shaping — <https://learn.microsoft.com/en-us/typography/script-development/hangul>
