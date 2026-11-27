[English](maker-audit.ko.md) | **한국어**

# SVF maker 기능 점검

SVF maker의 입력, 변환 경로, 설정, 미리 보기와 실행 경계를 설명한다.
사용법은 [데스크톱 앱](desktop-app.ko.md), 패키징은 [데스크톱 구현](maker-desktop.ko.md),
명령줄 대응은 [레시피](recipes/desktop-routes.ko.md#데스크톱-앱과-maker-경로), HTTP API는
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
- 마스크 맞춤 명령줄 실행 기록은 [recipes/outline-fonts.ko.md](recipes/outline-fonts.ko.md#truetype와-opentype-폰트에서-만드는-자모-세트)(방법 2)와 [recipes/desktop-routes.ko.md](recipes/desktop-routes.ko.md#데스크톱-앱과-maker-경로)에 있다. 그것이 maker의 전체 `mask fit` 실행을 검증하지는 않는다.
- 조각 인식기의 실제 모델은 검증되지 않았으며 통합 테스트는 스텁을 사용한다.
- 데스크톱 자동 테스트는 대화상자를 스텁으로 바꾸고 GPU를 끈다. 실제 대화상자·파일 관리자·창 관리자·GPU·샌드박스 검증은 별도이다.
- Windows NSIS·portable 빌드는 `windows-build` 브랜치에서 Actions를 통과했으나 main에 병합되지 않았다. macOS와 오래된 glibc는 미검증이다. [플랫폼 상태](maker-desktop.ko.md#65-windows와-macos-2026-11-27-상태)를 참고한다. 서버 배포용 systemd unit은 제공하지 않는다.

사용 가능한 테스트와 패키지 검증은 [패키징 안내](maker-desktop.ko.md#5-자동-검증과-기록된-실행)에 있다.
렌더러 통합은 [C 가이드](c-renderer-guide.ko.md), 구조는 [렌더러 설계](../spec/renderer-design.ko.md),
문서의 시작점은 [README](../README.ko.md)를 참고한다.

## 6. 참고 문헌 / References

- Unicode Hangul composition — <https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/>
- OpenType Hangul shaping — <https://learn.microsoft.com/en-us/typography/script-development/hangul>

## 7. 기록 / Records

2026-11-03의 입력·제어 감사와 이후 11-04~22의 구현·종결 기록을 보존한다.
본문의 날짜, 커밋, 카드 ID, 당시 테스트 개수와 미검증 항목은 그 시점의 기록이다.
원문이 개별 실행일을 적지 않은 부분은 날짜를 새로 추정하지 않았다.
“현재”, “없음”, “해야 한다” 등은 당시 상태를 뜻한다. 현재 동작은 1~5절을 따른다.
HWP는 이후 확장이 원문에 덧붙어 있으며, Windows는 [2026-11-27 상태](maker-desktop.ko.md#65-windows와-macos-2026-11-27-상태)를 따른다.
실행 기록의 명령은 보존했으며 이번에 다시 실행했다는 뜻은 아니다.


카드 t_c3d8c80b. `maker/`(detect.py, jobs.py, routes.py, presets.py, settings.py, naming.py,
preview.py, server.py, static/*)를 레시피(당시 한 파일, 지금은 [색인](recipes.ko.md)과 [그 문서들](recipes.ko.md#레시피-문서))와 대조한 읽기 전용 감사이며, 2026-11-03에 `ec5c6b3`(선별된 OFL 전용
저장소)에서 수행했다. 근거는 해당 커밋의 `file:line`이다(이 브랜치를 위해 다시 쓴 행은 줄 번호가 변하므로 심볼 이름을 인용한다). "Not verified"는 읽기만 하고 실행하지 않은 부분을 뜻한다.

maker의 동작을 한 단락으로 설명하면 다음과 같다. `detect.sniff`(maker/detect.py:84)가 매직 바이트와 크기로 파일에 태그를 붙이고,
`_detect_file`(detect.py:331)이 이를 `source_kind`를 가진 폰트 항목으로 바꾸며, `routes.routes`(maker/routes.py:253)가
`source_kind`를 도구 argv에 대응시키고, `settings.plan_steps`(maker/settings.py:1036)가 단계를 만들고, `jobs.run_command`
(maker/jobs.py:160)가 각 도구를 서브프로세스로 실행하며, `zipout`이 `svf/` 레이아웃의 zip을 쓴다. maker-controls 브랜치 이후
페이지는 생성된 모든 페이스(face)와 구워 낸 모든 원본 페이스를 WebAssembly로 빌드한 C 렌더러로 직접 그린다(3절). 서버는
FreeType으로 읽을 수 있는 원본의 원본 PNG만 Pillow(`preview.source_png`)로 그린다. 아래 1절과 2절은 `ec5c6b3`에서 감사한 내용이며 당시의 행을
그대로 두되, 브랜치에서 바뀐 곳에는 갱신을 덧붙였다("Now:"가 현재 상태를 나타낸다). 3절과 7절은 현재 상태이다.

### 7.1. 레시피 입력 종류

열: **Detect** = 경로(route)가 있는 `source_kind`; **Convert** = 경로가 실행하는 명령; **Preview** = 원본 미리보기(감사 당시 기준. 생성된 모든 페이스의 결과 미리보기는 이제 페이지에서 WASM으로 그린다, 3절).

| 레시피 입력 (recipes.md) | Detect | Convert (도구/명령) | Preview | 근거 |
|---|---|---|---|---|
| TTF (static) | 예: `ttf` -> `outline`; 합성 음절 -> `outline-composite` | 완성형: `mkfont.py SRC TMP --size S --bpp B --unicode ascii,ksx1001-hangul`(또는 `ascii,hangul`, 또는 목록 파일), 이어서 `tools/build/build_faces.py`처럼 `svf2to3.py TMP OUT --profile default`(배포된 페이스와 같은 페이스는 바이트 단위로 동일하다). 자모: 합성 -> `jamovec.py master --components [--adaptive]` 다음 `jamovec.py render --binarize threshold --check`; 비합성 -> "experimental fit" `jamoset.py --layout 844\|adaptive --from-ttf --binarize threshold\|--bpp 2 --check` | 예, 첫 크기에서 Pillow `source_png` | detect.py:91, 346-350, 851, 1108; routes.py:113-117, 119-130, 132-141, 263-272; preview.py:118 |
| OTF (CFF) | 예: `otf` -> `outline`(합성은 없음: CFF에는 없다) | TTF와 같음: mkfont; 자모는 experimental fit으로만 | 예 (Pillow/FreeType) | detect.py:93, 346; routes.py:263-272 |
| TTC / OTC | 예: 모든 페이스(최대 64개)를 나열한다; 첫 번째가 아닌 페이스, 또는 Mac 전용 cmap을 가진 페이스는 `prep` 목록(`ttc-face`)을 가진다 | 먼저 `source` 단계: `maker/srcprep.py ttc-face SRC OUT --index N`이 페이스를 일반 sfnt(CFF는 `.otf`)로 저장하고, 이후 TTF/OTF 경로가 그것을 읽는다 | 모든 페이스에 대해 예(`preview.source_png`가 페이스 인덱스를 받는다); Now: 미리보기와 클리핑 프로브는 준비된 페이스를 읽는다(`settings.source_ops`) | maker/detect.py `_ttc_entries`; maker/srcprep.py; routes.py `source_commands`; branch maker-inputs, A3/B1 |
| Variable font | 예: `fvar` 축과 이름 있는 인스턴스를 읽는다(항목의 `variable`, 레이블 `; variable (wght 100..900)`) | 작업당 폰트마다 인스턴스 하나: 설정 `instance`가 모든 축을 고정하는(기본값 위에 선택이 덧씌워짐) `fontTools.varLib.instancer` 원본 연산을 추가한다; 페이지에 인스턴스 선택이 있다 | Now 예: 미리보기와 프로브가 인스턴스화된 사본(`work/preview/<font>/source.ttf`)을 읽는다; 감사 당시: 기본 인스턴스 | settings.py `instance`, `instance_coords`; routes.py `source_commands`; maker.js `perFontInstance`; B2/C1 |
| GSUB로 분해 가능한 윤곽(`ljmo`/`vjmo`/`tjmo`) | Now 예: GSUB FeatureList를 읽는다(`gsub_jamo`, 레이블 "; conjoining jamo (GSUB)") | Now `mask fit` 경로(`jamoset.py --from-ttf --mask-font SRC --no-clean`, `--pylib DIR`)는 폰트에 자모 feature가 있고 라이브러리가 로드될 때 제공되며, `vector fit` 경로(`--components` 없는 `jamovec.py master`)도 있다. 자유 fit은 `--mask-font none`을 넘기므로 워커의 환경이 mask를 켤 수 없다. **mask-fit 작업은 한 번도 실행된 적이 없다: 이것을 빌드한 호스트에 freetype-py와 uharfbuzz가 설치되어 있지 않아서 argv, 제공 여부, 거부만 테스트했다.** vector fit은 합성 폰트에서 실행되었고(1.1 s) 그 master는 maker 밖에서 NanumGothic Regular로 한 번 시간을 쟀다: 높은 부하에서 172 s | TTF와 같음 | routes.py:132-141; jobs.py:66; tools/jamoset.py:2297-2302, 2855 |
| BDF ISO 10646 (Unicode) | 예: `bdf-iso10646`, 크기 = FreeType이 여는 스트라이크 | 완성형: 스트라이크에서 mkfont, 1 bpp만 | 예 (Pillow) | detect.py:355-373, 516; routes.py:273-276 |
| BDF ISO 8859 | 예: `bdf-iso8859`, 라틴 동반 폰트로만 사용 | 자체 경로 없음 | 아니오 | detect.py:516; routes.py (분기 없음); 동반 폰트 설정 detect.py:1120-1130 |
| hanterm (johab BDF) | 예: `bdf-johab`(레지스트리에 `johab`/`hanterm` 포함) | `jamoset.py SRC --layout hanterm-johab --check [--eng]` | 아니오: FreeType이 Unicode charmap을 주지 않아 `_draws_sample`이 거부한다 | detect.py:516-525; routes.py:153-158, 280-281; preview.py:236 |
| KS X 1001 BDF (KSC5601.1987 / KSX1001) | 예: `bdf-ksc5601` | 완성형: `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST`; 라틴 동반 폰트가 필요하다. 실험적 자모 경로 "bdfface + from-svf fit": `bdfface.py -o precomposed.svf` 다음 `jamoset.py --layout 844\|adaptive --from-svf precomposed.svf --check` | 아니오 (같은 이유) | routes.py `_bdfface_fit_commands`; B4 |
| PCF | 예. KSC5601/KSX1001 또는 johab PCF는 `srcprep.pcf_properties`가 읽어 `pcf-bdf` prep 연산이 붙은 `bdf-ksc5601` / `bdf-johab`이 된다; 그 밖의 PCF는 일반 `bitmap`으로 남는다(`.pcf.gz`는 FreeType이 읽는다) | `source` 단계 `srcprep.py pcf-bdf IN OUT`(maker 자체 리더, `pcf2bdf` 없음), 이어서 BDF 경로; 그 밖의 PCF: 스트라이크에서 mkfont | KSC/johab: 아니오; 그 밖: 예 | detect.py `_ksc_pcf_entry`; srcprep.py `pcf_to_bdf`; B3 |
| HBF | 예: `hbf`, 라틴 동반 폰트로만 | 경로 없음 | 아니오 | detect.py:101, 375-383; routes.py (분기 없음) |
| DOS johab raw (`.FNT`, `*.KOR`, HBIOS, san, 621, Dokkaebi, Kyra) | 예: 정확한 크기(`DOS_SIZES`)로 판별하고, 후보를 레이아웃 opener로 거른다; 소유자가 레이아웃을 확인한다 | `jamoset.py SRC --layout L --check [--eng ENG] [--face 0\|1]`; `--eng` = 옆에 있는 2048/4096바이트 파일 | 예: 첫 크기에서 같은 명령으로 구운 뒤 `svfline` | detect.py:29-33, 241-253, 417-436; routes.py:144-150, 277-279; preview.py:146-197; server.py:906-913 |
| DOS `johab844.py` (raw 조각에서 만든 완성형) | 예: 후보 `844`를 가진 11,520바이트 raw 폰트(`dos_bytes`) | 완성형 경로 `johab844`: `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng ENG]`; 레이아웃 844와 8x16 영문 폰트만; 선택한 범위는 무시되고 노트가 기준 페이스를 명시한다 | 해당 없음 | routes.py `_johab844_commands`; settings.py `_route_errors`; B5 |
| 12x24 영문 `.PFT` (12,288바이트: 태백 `GASCII24.PFT`. HWP 1.x 자신의 `ASCII.PFT`는 14x24, 41,654바이트이며 t_d4cf7f46부터 헤더로 읽는다) / HBIOS 12x24 영문 (15,360) | 예: 둘 다 `eng` 항목이다(`eng` = 바이트와 셀); 15,360바이트 파일은 `hbios_eng_like`(빈 여백 행, 12 px 셀, `A`에 잉크)일 때만 HBIOS 영문이고, 아니면 Dokkaebi 페이스이다; UI 재정의 없음 | DOS 자모 경로의 `jamoset.py --eng FILE`; 24 px 미만 페이스에서는 거부 | 아니오 | detect.py `hbios_eng_like`; settings.py `_route_errors`; A5/B6 |
| HWP 한글 `.PFT` | 로컬 모드 전용(Task 14): 크기가 `eng` 크기가 아닐 때 `.pft` 확장자(바이트 규칙 없음)로 이름 붙은 `other` 항목, 형식 `hwp-pft`, 다른 곳에서 변환해 그 파일을 추가하라는 레이블을 가진다; 업로드는 `unknown (...)`을 유지한다. 12,288바이트 12x24 영문 `.PFT`(태백 `GASCII24.PFT`. 테스트의 `ASCII.PFT` 픽스처)는 배치의 어느 폴더에 있든 24 px DOS raw 페이스와 짝지어진다(`detect.detect_file`, `HWP_PFT_LABEL`, `scan`). t_d4cf7f46부터 HWP 1.x `.SFT`/`.PFT`(자신의 `ASCII.PFT`는 14x24, 41,654바이트), HWP 3.0 `.FNT`, KS X 1001 덤프는 `tools/hwpfont.py`가 읽는다(종류 `hwp1`, `ks-raw`). `hwp-pft`는 여기서 읽는 레이아웃이 아닌 `.PFT`만 가리킨다 | 당시에는 없음(recipes: BDF 또는 완성형 SVF를 넣을 것). 지금은 `hwp1` / `hwp bdf + mkfont` / `hwp3 844` / `hwp bdf + from-svf fit` 경로 | 아니오 | `test_hwp_pft_label`, `test_ascii_pft_from_another_folder`, `test_8x16_eng_keeps_the_folder_rule` (test_detect_inputs.py), `test_hwp_inputs.py`; 실제 HWP 파일은 손으로, 그리고 `JOHAB_FONTS`와 함께 `tools/test_hwpfont.py`로 실행했다(recipes/dos-fonts.ko.md) |
| Windows `.FNT` / `.FON` | 예: `fnt`/`fon` -> `bitmap`; FON은 페이스 0만 | 스트라이크에서 mkfont, 1 bpp | 예 | detect.py:109-112, 391-415; routes.py:273-276 |
| Unicode cmap을 가진 Mac TrueType (`true` 매직) | 예: `ttf` | TTF와 같음 | 예 | detect.py:90-91 |
| Mac Korean (1,3) 또는 Wansung (3,5) cmap만 가진 Mac TrueType | 예: `mac_cmap_only`가 항목에 `mac-cmap` prep 연산을 주고 커버리지를 그것을 통해 읽는다(Unicode 서브테이블도 있는 폰트에는 주지 않는다) | `source` 단계: `macsfnt.py unicode IN OUT`, 이어서 TTF 경로 | Now 예(준비된 사본을 그린다) | detect.py `_sfnt_entry`; srcprep.py `mac_cmap_only`; B1 |
| `.dfont`, suitcase, resource fork, AppleDouble, MacBinary | 예: `mac-rsrc`; `sfnt` 리소스마다 항목 하나(`rsrc-sfnt` 연산, 필요하면 `mac-cmap`도); `NFNT`/`fbit` 리소스만 있으면 `other` 항목 하나; 손상된 맵은 `unknown` 항목 하나 | `source` 단계: `macsfnt.py extract IN OUT --id N`(그다음 `unicode`) | Now 예(준비된 사본을 그린다) | detect.py `_mac_head`, `_mac_entries`; B1 |
| Mac HangulTalk 1.0 `fbit` (`--layout mac-fbit-45sets`) | 로컬 모드 전용(Task 12): `mac-fbit1`, 45세트의 `fbit`와 `fdef` 3을 가진 fork(raw fork, AppleDouble, MacBinary); `fbit` 리소스만 있는 경우는 없는 `fdef`를 이름으로 알려 주는 `other` 항목이다(`detect._mac_fbit1_entry`) | 경로 `mac fbit 1.0`: `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT`(`routes._mac10_commands`); 감싸진 원본은 jamoset의 golden 조회를 위해 `<stem>.rsrc`로 끝난다 | 예: 구운 원본 페이스 | `MacEndToEndTest.test_mac10_end_to_end_and_prepared_name`; Task 12 Step 1 결과 (a)가 유지되었다: 합성 픽스처(`macfx.fbit1_fork`, 모두 0인 `fdef`)가 `--check`를 통과한다. 실제 1.0 폰트와 그 golden은 실행하지 않았다(`SVF_MAKER_REAL_MAC1`, `RealMac1Test`) |
| Mac HangulTalk 7.1 type-3 `fbit` (+ HTBL) | 로컬 모드 전용(Task 11): `mac-fbit3`(resource fork, AppleDouble, MacBinary, JM 아카이브, raw `fbit`), `mac-htbl`(HTBL 1 테이블, raw 9,612 또는 9,816바이트), `mac-suitcase`(FOND + 스트라이크를 가진 NFNT); HTBL과 선택적 suitcase는 동반 파일이며, 각각 한 번씩 자체 원본 단계로 계획되고 페이스 단계에 `needs`가 걸린다 | 경로 `mac fbit 7.1 direct` / `derived`: `macfbit_svf.py build SRC HTBL -o OUT --mode ... [--latin]`; `mac fbit 7.1 bdf + mkfont`: `macfbit3.py bdf`, `srcprep.py bdf-pixel-size`(도구의 BDF에는 `PIXEL_SIZE`가 없다), `mkfont.py`, `svf2to3.py --profile default` | 예: 구운 원본 페이스(HTBL 필요; 선택한 suitcase는 구워 넣는다) | `MacEndToEndTest`(direct는 `macfbit_svf.py verify`와 facecheck로 검증, wrapped와 JM, derived와 bdf + mkfont, gz fork, 동반 파일 연쇄, 원본 페이스), `LocalKindsTest`, `MacRoutesTest`, `LocalSettingsTest`. 실제 7.1.2 폰트와 HTBL은 실행하지 않았다(`SVF_MAKER_REAL_MAC3`, `RealMac3Test`) |
| 내장 비트맵 스트라이크 (`EBDT`/`bdat`) | 예: `EBLC`/`bloc` 스트라이크 크기를 나열한다(`strikes`); 스트라이크가 있고 윤곽이 없는 sfnt는 그 크기의 `bitmap` 원본이다(`sizes_fixed`) | 스트라이크에서 mkfont(계획 및 테스트됨; 실제 비트맵 전용 폰트는 `SVF_MAKER_REAL_EBDT`로만 실행된다) | 윤곽 폰트에 대해 예 | detect.py `_sfnt_entry`; srcprep.py `embedded_strikes`; A3/B1 |
| WOFF / WOFF2 | 아니오: `unknown`(레시피 입력도 아니다) | 없음 | 아니오 | detect.py:84-117 |
| SVF v3 (완성형 / 자모) | 예: `svf-precomposed` / `svf-jamo`, JSET 버전과 JMAP 모드 포함 | 복사, 또는 `svf2to3.py --jset-version V --check`; 완성형 1 bpp는 "from-svf fit" `jamoset.py --layout 844\|adaptive --from-svf --check`도 가능 | 예: 복사한 뒤 `svfline` | detect.py:438-451; routes.py:224-250, 286-296; preview.py:173-179 |
| SVF v2 | 예: v3로 변환된다 | `svf2to3.py --jset-version 1 --check` | 예 | detect.py:103-105, 438-451; routes.py:200-221 |
| SVF v1 | 거부됨("convert from the original font") | 없음 | 아니오 | detect.py:440-441 |
| 아카이브 (zip/tar/gz/xz) | 업로드 시 보호 장치와 함께 풀린다; 단일 파일 `.gz`는 압축 해제된다(128 MiB 상한) | 해당 없음 | 해당 없음 | detect.py:106-107, 120-134; maker/archive.py |

요약(maker-inputs 브랜치, 카드 t_f3ef3189 이후): maker는 정적 및 variable TTF/OTF(작업당 폰트마다 인스턴스 하나), 모든 TTC/OTC 페이스, Mac-cmap TTF,
dfont/suitcase/AppleDouble/MacBinary, Unicode BDF/PCF/FNT/FON, KSC/johab PCF,
hanterm, KS X 1001 BDF(완성형, 그리고 실험적 `--from-svf` 자모 경로), `jamoset.py`의 모든 DOS raw 레이아웃,
`johab844.py`, 12x24 영문 동반 폰트, SVF v2/v3를 다룬다. 아직 Mac `fbit`(두 세대 모두)와 HWP
한글 `.PFT`에 대해서는 아무것도 없다. Now(maker-controls 브랜치): GSUB로 분해 가능한 폰트는 `mask fit`과 `vector fit` 경로를 얻고
(mask fit은 여기서 실행된 적이 없다), 원본 미리보기와 프로브는 선택한 variable 인스턴스, TTC 페이스, Mac 폰트를 보여 준다.

### 7.2. 레시피에 비해 빠진 제어

**`ec5c6b3`에서 감사한 대로**(아래 표는 발견된 격차를 그대로 두며, "Now" 열은 브랜치가 추가한 것을, 7절의 격차 목록은 각각을 닫은 작업을 알려 준다): 당시 페이지가 제공하던 것(maker/static/index.html;
maker/static/maker.js:62-83; maker/settings.py:32-37; maker/presets.py:16-60, 63-90)은 배치 종류(완성형 / 자모), 레이아웃(844 / adaptive), 크기(목록), bpp(1, 2),
범위(2350 / 11172 / 업로드한 목록), 프리셋, 그리고 `cell`, `ascent`, `space_advance`,
`mono_hint`, `clip_cell`(mkfont)과 `embolden`, `symbols`, `jset_version`(jamoset)이 있는 고급 패널이다.

| 레시피 제어 | maker에 있는가? | 격차 (감사 당시) | Now |
|---|---|---|---|
| AA 2 bpp, 완성형 | 예: 윤곽 원본에 bpp 2(mkfont `--bpp 2`) | 비트맵/BDF/DOS 원본은 1 bpp뿐이며(routes.py:273-284) 이는 올바르다. `--bpp 8`(호스트 페이스)은 제공되지 않는다 | 변경 없음 |
| AA 2 bpp, 자모 세트 | 윤곽에 대해 예: 합성 경로 `jamovec.py render --bpp 2`, fit 경로 `jamoset.py --bpp 2`(routes.py:126-141) | `--aa-refine N`, `--clean/--no-clean`이 노출되지 않음; `quality.py`의 IoU(maker/quality.py) 외에는 레벨 오차 수치가 표시되지 않음 | `--aa-refine`와 `clean`이 옵션이다(`clean`은 2 bpp에서만); `binarize` threshold/ridge/mono |
| 베이스라인 / ascent | mkfont에만 `--ascent`(presets.py:69-70) | jamoset 경로(DOS raw, hanterm, fit, from-svf; tools/jamoset.py:2839)에도 bdfface(`--ascent` / `--hangul-ascent`)에도 `--ascent`가 없음; `--latin`(대문자 높이를 맨 위로)이 노출되지 않음 | 도구별 ascent 키(`ascent`, `jamo_ascent`, `fit_baseline`, `latin_ascent`, `hangul_ascent`), `latin`, 미리보기에서 테스트해 볼 ascent |
| 글리프별 수직 이동 (`svfdy.py --range --dy`) | 아니오 | 단계도 제어도 없음; `svfdy.py`는 maker/ 어디에도 언급되지 않음 | 폰트별 dy 표와 완성형 페이스에 대한 `svfdy.py` 단계, 미리보기에서 테스트해 볼 dy |
| 위/아래 클리핑 | `--clip-cell`만 | `--fit-cell`(잉크가 잘리지 않을 때까지 크기를 낮춤)이 노출되지 않음; mkfont가 stdout에 찍는 잘림 횟수는 빌드 로그에만 있고 단계별로 표시되지 않음; 빌드 전에 "잘린 행"을 보는 화면이 없음 | `fit_cell`; mkfont `--report`에서 얻은 단계별 잘림 횟수; 클리핑 패널이 빌드 전에 어떤 ascent에서든 잘리는 행을 보여 준다 |
| 셀 너비 / 고정 advance | 프리셋을 통해서만(`latin-18cell-2bpp`의 `--width`) | `--width` 필드 없음; `--punct-extra`, `--ink-advance`, `--only-listed`, `--fallback-ttf`, `--limit`, `--require`가 패널에 없음; jamoset `--advance`, `--cell`(from-ttf)이 노출되지 않음 | `width`가 옵션이다; 나머지 플래그는 여전히 노출되지 않는다 |
| 크기 / bpp / 문자 집합 | 크기, bpp 1/2, 범위 2350 / 11172 / 목록 파일 | 이 둘 너머의 이름 있는 범위(`ksx1001-nohanja`, `ksx1001-symbols`, `jamo`, `cp949`, `ksx1001`)는 프리셋을 통해서만; ASCII는 항상 추가된다(`ascii,` 접두, routes.py:98-110) | 이름 있는 범위 다섯 개를 선택할 수 있다(모두 일곱 개) |
| 분해 가능한 폰트에서 만드는 자모 세트 | 합성 TTF 경로(`jamovec.py --components`)와 비네이티브 "experimental fit" | GSUB-mask 경로(`--mask-font`, `--mask-radius`, `--pylib`) 없음, `--components` 없는 `jamovec.py master`(결정 크기에서의 벡터 분리) 없음, `--binarize mono\|ridge` 선택 없음(항상 `threshold`, routes.py:128, 135) | `mask fit`(여기서 실행된 적 없음), `vector fit`(master에 수 분이 걸림: NanumGothic 172 s), `binarize` 선택, `jamo_route` 선택 |
| 조각 정체성 검사 | 아니오 | 경로는 `--check`를 실행하는데, 이는 표가 11,172개 음절을 모두 조합함을 증명할 뿐 각 조각이 해당 자모임을 증명하지 않는다. `quality.py`는 기준에 대한 IoU만 점수 낸다. 이 저장소에는 자모 인식기가 없다(tools/에서 "recogni"를 grep하면 JMAP_RECOG 플래그 처리만 나온다); 카드 t_9acea7ab 요건은 인식기를 가져오거나 작성해야 한다 | `SVF_RECOG_DIR`가 인식기를 가리킬 때 자모 단계마다 `maker/recog_score.py`; **실제 인식기는 실행되지 않았다: 스텁만 있다**(이 저장소에는 없다) |
| Mac/HWP 옵션 (fbit용 `--symbols`, `--mode derived`, `jamomerge.py`, `jamoexc.py`) | 아니오 | 이 도구 중 어느 것도 호출되지 않는다 | 변경 없음 |

### 7.3. 미리보기: 브라우저가 WASM 렌더러로 그린다

**상태(카드 t_9acea7ab).** 생성된 모든 페이스와 구워 낸 모든 원본 페이스는 WebAssembly로 빌드된 C 렌더러가 페이지에서 그린다
(`maker/build-wasm.sh`가 `maker/static/wasm/`로 빌드하며, 컴파일 줄은 `c/ports/web/emcc-flags.sh`를 통해 `web/build.sh`와 공유한다).
`svfline.py`는 바이트 단위 오라클로 남는다(`tools/test_web_picker.py`
`TestModule`이 페이지의 글리프별 컴포지터와 대상 디코더도 고정한다). 워커는 더 이상 결과 PNG를 쓰지 않는다.

- **바이트를 제공하는 엔드포인트**(`maker/server.py`, 모두 GET, `no-cache`, 호스트 검사; 바이트 파일은 ETag를 갖고 `If-None-Match`에 304로 답하며, 생성되는 프로브 JSON은 그렇지 않다): `face/<step>.svf`
  (완료된 페이스 단계만), `source/<font>.svf`(DOS raw 또는 SVF 항목의 구운 원본), `repo/face/<group>/<FILE>`
  (라틴 동반 폰트 `dos/NEODG16.SVF`), `report/<step>.json`, `probe/<font>/<size>/<bpp>.(svf|json)`,
  `identity/<step>.json`; `/api/caps`가 어떤 선택적 부분이 있는지 알려 준다.
- 그리기 경로 외에 `c/ports/web/svf_web.c`의 **export**: `svfw_metrics`, `svfw_cell_bytes`, `svfw_glyph`,
  `svfw_pieces`, `svfw_cmap_cp`, `svfw_line_box`(`svf.h`로의 얇은 호출; `c/src`는 바뀌지 않았다).
- **페이지**(`maker/static/svfview.js`, `maker.js`): 완료된 단계마다 샘플 텍스트, 배율, 대상(GRAY8, MONO, RGB565), 임계값, 가이드, 글리프 격자,
  그리고 재빌드 없이 글리프별 컴포지터(`walk_next`를 따르는 `drawGlyphsInto`)가 그리는 테스트용 ascent(`dos raw`/`hanterm`) 또는 테스트용 dy(완성형)를 가진 결과 셀;
  하나를 적용하면 끝난 작업을 다시 열어 저장한다. 단계 행은 mkfont 보고서(`cut N`, `nudged N`, `fit at
  S px`)를 보여 준다; 자모 단계는 정체성 판정을 보여 주고, 열면 그 조각들을 보여 준다.
- **빌드 전 클리핑**(`mkfont --probe` / `--report`, `clip.js`): 프로브는 그 단계 자신의 argv(`settings.face_argv` / `probe_argv`)로, 아무것도 자르지 않는 셀에서 구워진다;
  "clipping" 패널은 `fit_counts`의 규칙으로 어떤 ascent가 자르게 될 행을 계산해 프로브 페이스 위에 그린다.
- **서버가 계속 그리는 것:** FreeType으로 읽을 수 있는 원본의 원본 PNG(Pillow, `preview.source_png`); 구운 원본의
  PNG는 여전히 서버가 쓰지만(그리고 테스트되지만) 페이지는 그것들을 WASM으로 그린다.
- **Caps:** `wasm`(모듈이 빌드됨), `mask_libs`(`mask fit`과 `binarize mono`를 위한 freetype-py와 uharfbuzz),
  `recog`(정체성 검사를 위해 numpy와 torch가 있는 `SVF_RECOG_DIR`).

### 7.4. 127.0.0.1의 Python 사이드카를 가진 Electron 셸

현재 있는 것과 바뀔 것:

| 영역 | 현재 | Electron + 사이드카를 위한 변경 |
|---|---|---|
| Bind | `SVF_MAKER_BIND`, 기본값 `127.0.0.1:8766`; 호스트가 없으면 127.0.0.1(server.py:118-125, 993-997) | `127.0.0.1:0`에 bind하고 실제 포트를 출력(서버는 이미 "listening on host:port"를 출력한다, server.py:999); Electron이 stdout에서 읽는다 |
| Tailnet | 명세만 tailnet을 말한다(`docs/superpowers/specs/2026-10-21-svf-maker-design.md:80-81, 504-523`, 100.78.108.85); tailnet을 가정하는 코드는 없다 | 코드에는 없음; T15의 unit/README만이 유일한 위치가 된다 |
| Auth | 없음; 상태를 바꾸는 요청은 `Host`가 {127.0.0.1, localhost, ::1, bound host}에 속하는지와 `Origin`이 같은 호스트+포트인지를 검사한다(server.py:380-403) | 어떤 로컬 프로세스든 127.0.0.1에 닿을 수 있으므로 실행마다 토큰을 추가한다(Electron이 env로 주고 모든 요청에 헤더로 붙임); `file://` 페이지는 `Origin: null`을 보내 거부되므로 창은 `http://127.0.0.1:PORT/`를 로드해야 한다(검증됨: 외부 Origin은 403을 받는다) |
| Repo dir | `SVF_MAKER_REPO`, 기본값은 `maker/` 위의 체크아웃(server.py:994); 서버에는 `tools/`(모든 도구), `svf/`(이름 충돌, 라이선스 텍스트, NEODG16 라틴 대체), `web/mkindex.py`와 `web/LICENCES.tsv`/`FAMILIES.tsv` 리더(maker/zipout.py:273-292, 409-420; maker/naming.py:129-142; preview.py:202-216), 그리고 `git rev-parse HEAD`(zipout.py:78-88, git이 없으면 "unknown")가 필요하다 | `tools/`, `svf/`(또는 부분집합), `web/mkindex.py`를 데이터로 싣는다; "repo head"를 빌드 id로 만든다 |
| Tool launch | 모든 도구는 `[sys.executable, "-P", tools/X.py]`(routes.py:20) | PyInstaller에서는 `sys.executable`이 python이 아니라 동결된 사이드카이다: 실제 python을 싣거나, 사이드카에 `run-tool NAME ARGS` 진입점을 주고 거기서 argv를 만든다(카드 t_e64a56a7) |
| Data / temp dirs | `SVF_MAKER_DATA`, 기본값 `~/.local/share/svf-maker`; 작업마다 `upload/ work/ out/`; 최대 20개 작업, 7일(server.py:995; jobs.py:42-48) | Electron의 `app.getPath('userData')`를 쓴다; 보존 정책은 유지한다 |
| Upload limits | 본문 64 MiB, 작업 256 MiB, 파일 2,000개(server.py:41-43); `.gz`는 압축 해제 후 128 MiB(detect.py:44) | 업로드에는 유지한다; 경로 모드는 복사 한도가 필요 없지만 압축 해제 상한은 유지한다 |
| Subprocess env | PATH/HOME/LANG만 있는 명시적 `ENV`(jobs.py:66; preview.py:48) | GSUB 경로를 추가하면 `JAMOSET_PYLIB`/`JAMOSET_MASK_FONT` 통과를 추가한다 |
| systemd | 저장소에 unit 없음(계획 Task 15 미완) | Electron에는 필요 없음(Electron이 사이드카의 수명을 관리한다); 서버 용도로는 unit을 유지한다 |
| Page | 사이드카가 제공하는 `static/`, `<input type=file webkitdirectory>` 업로드(static/index.html:38) | Electron 안에서 그대로 동작한다; 네이티브 대화상자와 드래그 앤 드롭은 경로를 넘긴다(아래) |
| Output | `GET /api/jobs/<id>/zip`의 zip 다운로드(server.py:974-983) | Electron이 저장하거나, 사이드카가 선택한 폴더에 쓴다(경로 모드) |

**독점 입력을 위한 Local 전용 모드**(Mac fbit, HWP, 그 밖의 비 OFL 폰트): 현재는 모든 입력이 `PUT /api/jobs/<id>/files?path=`
(server.py:567-632)를 통해 작업의 `upload/`로 복사되고, 미리보기와 zip은 작업 디렉터리 아래에 써진다. 로컬 모드는 다음과 같이 한다. Electron의 대화상자에서 온 절대 경로 목록을
토큰 보유자만 호출할 수 있는 새 엔드포인트로 받는다; 그 경로에서 제자리로 감지하고 변환한다(detect는 이미 경로에서 동작한다;
`plan_steps`는 `upload_dir`을 받으며, settings.py:1016-1027, 이는 폰트별 원본 루트가 된다); 출력은 선택한 출력 폴더에만 쓰고,
작업 파일은 작업 후 지워지는 임시 디렉터리에 둔다; 원본을 데이터 디렉터리에 복사하지 않으며 zip에 쓰지도 않는다(지금 zip에는 생성된 페이스와 라이선스 텍스트만 들어 있다, zipout.py). 이를 위한 테스트는
listen 소켓이 127.0.0.1 전용이고 출력 폴더와 임시 디렉터리 밖에는 아무것도 쓰이지 않음을 보여야 한다.

### 7.5. 웹 UI v1 계획과 열린 카드

계획 `docs/superpowers/plans/2026-10-21-svf-maker.md`(16개 작업). 체크박스는 모두 비어 있고(`- [ ]` 82개, `- [x]` 0개)
"Implemented" 노트도 없다; 아래 상태는 파일과 `docs/STATUS.md:29, 120`에서 얻었다
("대부분 done, systemd unit·문서·end-to-end 시험과 web UI v1 남음"; 10-23에 837f525로 병합, LIST 지원은 10-28에 0d73568; 두 커밋 모두 이 선별된 이력에는 없다).

| 계획 작업 | 이 트리에서의 상태 |
|---|---|
| 1-13 (cmap_has, 픽스처, detect, scan, presets/routes, naming, settings, quality, zip, previews, archive, jobs, server) | 완료: 모듈과 테스트가 있다; 테스트 통과(아래) |
| 14 페이지 | 완료: `maker/static/index.html`, `maker.js`(1,327줄), `style.css`; 계획이 나열한 id가 모두 있다(`files`, `folder`, `upload`, `state`, `notice`, `fonts`, `settings`, `advanced`, `save`, `run`, `cancel`, `download`, `steps`, `jobs`, `position`) |
| 15 systemd unit, README, `.gitignore`, docs 줄 | **재조정됨(t_bbceabe9, 2026-11-09)**: 서버 배포가 없으므로 `maker/svf-maker.service`는 없다; `maker/README.md`가 있다(실행, 토큰, 로컬 모드, 데스크톱 앱, 테스트); `docs/tools.md` 포인터가 반영되었다 |
| 16 end-to-end, 프리셋 인수, 느린 fit, UI smoke | **완료(t_e073891a)**: `maker/test/test_e2e.py`(upload와 로컬 모드의 혼합 폴더, facecheck, 병합된 `mkindex --check`, 그리기; `dos-u-2bpp`가 GBATB17과 바이트 동일; 느린 fit은 `SVF_MAKER_SLOW=1` 뒤에), `maker/test/test_ui_smoke.py`; `smoke.mjs`/playwright는 `pagedrive.mjs --files`로 대체되었다 |

카드: t_a1cf496b(web UI v1 목표)는 2026-11-09에 재조정되었다: tailnet 서비스 없음; maker를 로컬(데스크톱 앱, 또는 loopback의 `maker/server.py`)에서 실행해
TTF+BDF+PCF+DOS Johab 테스트 폴더를 `facecheck.py`를 통과하는 페이스로 변환하고, T16이 통과하며, 리뷰를 마치면 닫힌다. T15(t_bbceabe9)는 재조정되어 닫혔다; T16(t_e073891a)은 위 16행이다.

### 7.6. 실행 상태 (2026-11-03, 이 worktree)

- `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`: **Ran 431 tests in 77.3 s, OK**
  (tools/jamoset.py:1808에서 ResourceWarning 하나, 테스트에서 닫히지 않은 파일).
- `tools/test_web_picker.py`(WASM 대 svfline 오라클): 44개 테스트 OK, 1개 건너뜀(TestPage, playwright-core 없음).
- 서버: `SVF_MAKER_REPO=<worktree> SVF_MAKER_DATA=<tmp> SVF_MAKER_BIND=127.0.0.1:18766 python3 -P maker/server.py`가
  "svf-maker listening on 127.0.0.1:18766"을 출력했다; `GET /` 200, 4,910바이트, 제목 "SVF maker"; `GET /api/repo`
  200(폴더 `dos`, `jamo-extra`); `POST /api/jobs` 200 `{"id": ...}`; `Origin:
  http://evil.example`를 붙인 같은 POST는 403 "cross-origin request". 서버를 통한 업로드나 변환은 실행하지 않았다.

**마감 실행 상태(Task 15, maker-controls 브랜치).** heavy를 통한 maker 스위트: 666개 테스트 OK(10개 건너뜀: playwright, freetype-py/uharfbuzz, numpy, `SVF_MAKER_REAL_*` 없음); heavy를 통한 `tools/test_*.py`: 967개 테스트 OK(17개 건너뜀), `test_web_picker` 포함;
heavy를 통한 `make -C c check`: exit 0; `sh c/cross/test-check-features.sh`: OK; google-chrome에서 `maker/test/smoke_dom.py`: exit 0;
`git diff 01a943f -- c/src c/include`: 비어 있음.

### 7.7. 격차 목록(우선순위 순)과 각각이 속한 카드

1. **t_9acea7ab** - 완료(Tasks 6-8): 페이지가 생성된 페이스를 WASM 렌더러로 그린다; `GET .../face/<step>.svf`;
   `svfline` PNG는 테스트 오라클일 뿐이다.
2. **t_9acea7ab** - 완료(Tasks 1, 7): export `svfw_metrics`, `svfw_glyph`, `svfw_pieces`, `svfw_cmap_cp`,
   `svfw_line_box`; ascent와 dy 재정의는 페이지의 컴포지터가 처리한다(`c/src`에 훅 없음).
3. **t_9acea7ab** - 완료(Tasks 4, 5, 9, 10, 11): 도구별 ascent 키, `--fit-cell`, `--width`, `--latin`,
   dy 표를 가진 `svfdy.py` 단계, mkfont `--report`와 단계별 잘림 횟수, 클리핑 프로브와 패널,
   `--aa-refine`, `--binarize`, `clean`, 일곱 개의 이름 있는 범위.
4. **t_9acea7ab** - 완료(Tasks 3, 12, 14): `mask fit` 경로(`--mask-font`, `--pylib`)와 `vector fit` 경로
   (`--components` 없는 `jamovec.py master`); 정체성 검사는 `SVF_RECOG_DIR`가 인식기를 가리킬 때
   `maker/recog_score.py`를 실행한다(이 저장소에는 없다; 스텁만 실행되었다). **Not verified:** mask-fit 작업은 실행된 적이 없다(이 호스트에 freetype-py/uharfbuzz 없음); vector fit은 합성 픽스처에서 실행되었고(1.1 s) NanumGothic의 master는 heavy에서 172 s가 걸렸다. 원본 미리보기와 프로브는
   준비된 폰트를 읽는다(Task 13).
5. **t_f3ef3189** - 입력 종류: maker-inputs 브랜치에서 완료(1절 참조: VF 인스턴스, TTC 페이스, Mac TTF와 컨테이너,
   KSC/johab PCF, `johab844.py`, 12x24 `--eng`, `bdfface` 뒤의 `--from-svf`, 스트라이크 크기). 남은 것: 원본 및
   인스턴스 미리보기(t_9acea7ab), local 전용 모드와 Mac `fbit`(t_cbd14d61), Electron, 패키징, 자모 인식기.
6. **t_cbd14d61** - 완료(Tasks 1-15, maker-local 브랜치): 경로 기반 원본을 쓰는 local 전용 모드, Mac `fbit`(두 세대 모두)와 HWP 줄은 그곳에만;
   출력은 선택한 폴더에만; 127.0.0.1은 테스트로 증명됨. 마감 근거와 열린 항목은 8절에 있다.
7. **t_f04f1355** - Electron: 포트 0 + stdout 핸드셰이크, 실행마다 토큰, http로 로드(file:// 아님), userData를
   데이터 루트로, 경로를 로컬 모드에 넘기는 네이티브 대화상자, 창과 함께 멈추는 사이드카.
8. **t_e64a56a7** - 패키징: `[sys.executable, "-P", tool]`(routes.py:20)을 사이드카 도구 진입점으로 대체;
   `tools/`, `svf/` 부분집합, `web/mkindex.py`를 싣는다; repo head를 빌드 id로; Pillow/FreeType/fontTools를
   번들에 포함.
9. **t_bbceabe9 / t_e073891a / t_a1cf496b** - T16 반영됨(t_e073891a, t_df773bf5 이후: maker의 mkfont
   페이스를 그것이 재현하는 배포 페이스와 바이트 단위로 동일하게 만들었다: 경로가 `svf2to3.py --profile default`로 끝나며
   `PresetAcceptanceTest`가 바이트 단위로 고정한다); T15의 unit/README와 t_a1cf496b의 tailnet 조항은 데스크톱 방향으로 재조정해야 한다.

### 7.8. 로컬 모드: 마감 근거, 셸 계약, 검증하지 못한 것(카드 t_cbd14d61)

**카드의 마감 측정과 테스트의 대응**(모두 합성; 저장소에 독점 바이트는 없다):

| 마감 측정 | 근거 |
|---|---|
| 합성 Mac/HWP 유사 파일이 로컬 모드로 변환된다 | `MacEndToEndTest`(test_plan_inputs.py: 7.1 direct, derived, bdf + mkfont, wrapped, JM, gz, 동반 파일 실패 연쇄, 1.0 end to end); `test_ascii_pft_from_another_folder`(감지)와 `LocalRunTest`의 DOS raw 작업 |
| 네트워크 꺼짐, 127.0.0.1만 | `LocalBindTest`(토큰, loopback 전용 bind, `main()` 거부); `NoNetworkTest.test_static_no_network_imports`, `test_network_off_in_process`, `test_network_off_namespace`(`unshare -rn`이 거부되는 곳에서는 건너뜀) |
| README가 독점 폰트를 배포하지 않음을 밝힌다 | `test_readme_and_notice_wording` (test_server.py) |
| 선택한 출력 폴더 밖에는 아무것도 쓰이지 않는다 | `LocalSweepTest.test_no_write_outside_output`, `WriteTreeTest`(디스크립터 상대 쓰기, 링크되거나 바뀐 폴더, 교체되거나 제거된 출력 폴더) |
| 입력이 데이터 디렉터리로 복사되지 않는다 | `LocalJobTest.test_no_upload_copy`, `LocalSweepTest.test_final_no_upload_copy`, `LocalPrivacyTest`(어떤 영속 산출물에도 입력 바이트나 예외 메시지가 없다) |

**Electron 셸(카드 t_f04f1355)이 이 서버에 대해 해야 할 일**
- `SVF_MAKER_TOKEN`(소문자 16진수 32자, 실행마다 새로 만듦), `SVF_MAKER_BIND=127.0.0.1:0`(loopback이 아닌 bind는 거부되며 exit 2), `userData` 아래의 `SVF_MAKER_DATA`, 선택적으로
  `SVF_MAKER_ROOTS`(원본과 출력 폴더를 위한 콜론으로 구분된 허용 목록)를 주고 `python3 -P maker/server.py`를 시작한다. 포트는 stdout
  줄 `svf-maker listening on 127.0.0.1:<port>`에서 읽는다.
- 페이지는 `http://127.0.0.1:<port>/`에서 로드하고(`file://`은 절대 안 됨: `Host`/`Origin` 검사가 거부한다) `/api/`로 가는 모든 요청에
  `X-Maker-Token: <token>`을 추가한다(헤더는 정확히 하나; `/`와 `/static/*`에는 필요 없지만 서버를 가리키는
  `Host`를 실어야 한다). 페이지와 토큰은 만나지 않는다: 헤더는 셸이 붙이고 페이지는 보내지 않는다.
- `window.svfMaker`를 노출한다(preload, `contextIsolation`에 안전하게): `pickFiles()`와 `pickFolder()`(각각 절대 경로 배열로 resolve되며, 취소된 대화상자는 `[]`/`null`),
  `pickOutputDir()`(경로 문자열 또는 `null`), `openOutputFolder()`(인자 없이 호출; 셸이 작업의 출력 폴더를 직접 연다). 브리지가 있으면 페이지는
  경로 직접 입력 필드를 숨기고, 없으면 직접 입력한 경로를 받는다.
- 서버는 SIGTERM(또는 SIGINT)으로 멈춘다: 실행 중인 작업은 취소되고, 도구 프로세스는 종료되며, 모든 files
  디렉터리가 정리된다. 가능하면 SIGKILL을 쓰지 않는다: 강제 종료된 실행은 다음 시작 때까지 `.svf-maker-<id>/`를 남긴다
  (시작 시 정리가 이를 제거하며, 보류 정리 기록이 실패한 제거를 보존한다).
- 페이지는 세션마다 한 번, 폰트 변환은 사용자의 책임이라는 확인을 요청한다; 셸은 그럴 필요가 없다.

**Not verified**(이것을 빌드한 호스트에서는 실행할 수 없었다; 각각 코드와 테스트의 해당 위치에 명시되어 있다):
`unshare -rn` 실행(호스트에서 거부됨; 정적 import 검사와 프로세스 내 소켓 가드가 관문이며,
가드는 도구 서브프로세스도, `SVF_RECOG_DIR`가 가리키는 사용자 자신의 `recog.py`도 볼 수 없다); 실제 Apple HangulTalk
7.1.2 및 1.0 파일, 실제 HWP `.PFT` 파일, 실제 7.1.2 HTBL(`SVF_MAKER_REAL_*` 테스트는 건너뜀); Mac의 macOS 이름 있는
resource fork; Electron, 그 preload, `contextIsolation`, 네이티브 대화상자, `shell.showItemInFolder`(가짜
`window.svfMaker`가 대신한다); FAT, exFAT, SMB/NAS 마운트(하드 링크 없음 대체와 거부된 `chmod`는
목으로 테스트한다); 실제 디스크 가득 참 상황(목); 대소문자를 구분하지 않는 파일 시스템; 심볼릭 링크된 부모 외의 방식으로 표기된
inode 겹침; `.svf-maker-<id>/`를 읽는 동기화 클라이언트; 실제
Electron 재실행에 걸친 `sessionStorage` 유지.

**제한된 수명 주기(t_d1aba4b8).** 이는 앞선 "accepted trade-off (lifecycle lock)"와 "known limits of
the cleanup"을 대체한다. 이제 무엇이 제한되고 무엇이 제한되지 않는지를 적는다.

- **구간별.** 요청 또는 유휴 스위퍼의 모든 lifecycle-lock 구간(`ensure_files_dir`의 호출들,
  `_rename_away`의 stat과 rename, local `delete`가 쓰는 보류 기록, 실행의 commit 검사)은 모든 호출을 합쳐
  `LOCKED_IO_S`(5 s)의 `Deadline` 하나를 가진다(호출마다가 아니다). lifecycle lock 아래에서 취한 작업 락 대기와 그 뒤의 I/O는 각각 `LOCKED_IO_S`를 받는다; 미리보기 락은
  try-lock만 한다(`PREVIEW_TRY_S`). 같은 멈춘 경로에 대한 두 번째 요청은 이미 진행 중인 호출을 공유하며, 자기 구간의 한도 안에서 그렇게 한다.
- **예외.** 시작 시 정리는 `STARTUP_CLEANUP_S`(30 s)를, 정지는 `STOP_SWEEP_TOTAL_S`(8 s)를 모든 대기(lifecycle lock, 미리보기 락, stat, rename, 제거, 보류 기록)의 하나뿐인 데드라인으로 쓴다; 이들은 `LOCKED_IO_S`로 제한되지 않는다. 한 번의 패스는 데드라인을 기껏 보류 하한 몇 개
  (약 2 s: 한 패스의 기록들, 그다음 flush)만큼 넘기며, 이는 `desktop/lib/budget.js`의 여유 안에 있다. 데이터 루트(`job.json`, `Store.list`, `log.md`)는
  로컬 디스크로 가정하며 제한되지 않는다.
- **실패한 ensure.** 디렉터리를 만들기 시작한 뒤 실패한 `ensure_files_dir`은 `job.json`의 `files_id`를 지우고 경로를
  보류(`making`)로 기록하며, 이는 자신의 `LOCKED_IO_S` 안에서 이루어진다. 따라서 실패하는 호출은 lifecycle lock을 약 2 x `LOCKED_IO_S`(I/O 예산, 그다음 그 기록)에
  작업 락 대기를 더한 시간 동안 쥘 수 있다.
- **미리보기 락의 허용된 한계.** 삭제된 작업의 미리보기 락 중 그 순간 잡혀 있는 것은
  `_PREVIEW_LOCKS`에 남는다(작은 객체 몇 개이며, 사용에 따라 늘지 않고, 풀린 뒤 이후 호출이 버린다). 따라서 삭제 뒤에 오는 스윕도
  여전히 잡힌 상태로 찾는다. `_drop_preview_locks`는 `locked()`를 확인하고 하나의 가드 아래에서 제거하지만, 보유자가 그 직후 락을 잡을 수 있다;
  모든 보유자는 디렉터리를 쓰기 전에 lifecycle lock 아래에서 작업이 아직 존재하는지 다시 확인한다.
- **펜스.** 포기된(시간 초과된) rename은 진행 중으로 등록된 채 남아 그 경로를 펜스로 막는다:
  `ensure_files_dir`은 그 이름의 새 세대를 만들기를 거부하고, 스윕은 그것을 보류로 기록하므로, 늦은
  rename은 자신이 발행된 세대만 옮길 수 있다. 읽기 전용 호출(stat, listdir)은 진행 중인 하나를 공유한다.
  **허용된 한계:** 돌아오지 않는 rename 또는 mkdir(죽은 hard mount)은 프로세스가 재시작할 때까지 그 작업 하나의 files 디렉터리를
  펜스로 막아 둔다: 그 미리보기는 "the files directory is still being moved or made on
  a slow or hung volume"와 함께 404로 답한다. 다른 것은 막히지 않는다.
- **보류 기록.** `pending-sweeps.json`의 모든 읽기와 쓰기는 하나의 쓰기 스레드를 거친다; 호출자는
  데드라인까지 기다리되, 쓰기 스레드가 유휴일 때는 최소 `PENDING_FLOOR_S`(0.5 s)를 기다리고, 앞선
  작업이 끝나지 않았으면 하한이 없다. 기다리지 않은 작업도 나중에 순서대로 실행된다. 정지와 시작 시 정리는 돌아가기 전에 쓰기 스레드를
  flush한다. local 작업의 `delete`는 메타데이터를 제거하기 전에 정리 기록을 저장한다; 기록을
  저장할 수 없으면 작업은 남고 DELETE는 409 busy로 답한다.
- **local `POST run`은 세 구간이다.** 준비(짧음, lifecycle lock 아래: 검사, files 디렉터리, 미리보기 try-lock, `preparing` 표시), 읽기와 계획(저장소 락 없음: 입력 stat, 라이선스 해싱, 계획,
  범위 복사), commit(lifecycle lock 아래: files 디렉터리가 여전히 현재인지 확인한 뒤, 상태와 작업의 지문을
  작업 락 안에서 다시 확인). 따라서 멈춘 입력 볼륨이 더 이상 다른 작업의 생성, 활성화, 스윕을 지연시키지 않는다.
- **락 순서 복원.** lifecycle lock -> job lock -> preview locks -> pending lock, 어디서나. `PUT settings`는
  작업 락 아래에서 저장하고 바뀐 폰트의 미리보기를 그 바깥에서 나중에 지운다; `_preview_dir`은
  미리보기 락을 잡기 전에 디렉터리를 만든다.
- **클라이언트에 보이는 변경(허용됨).** 작업 락 또는 정리 기록을 제때 얻지 못하면(DELETE, create takeover, run activation, ensure) 409 `"job X is busy; try again"`; 409 `"a run of job X is being prepared"`(미리보기는
  "; try again"을 덧붙인다); 409 `"the job changed while the run was being prepared: run again"`; bake가 `LOCKED_IO_S`보다 오래 미리보기 락을 쥐고 있을 때 `POST run`에서 409 `"job X is busy: a
  preview is being made; try again"`;
  정리 기록을 저장할 수 없으면 DELETE는 409 busy로 답할 수 있다(작업은 남고, 쓰기 스레드가 회복되면 재시도가 통한다); 바쁜 보유자 때문에 실패한 create takeover는
  409 busy로 답하고 보유자를 남긴다(유휴가 되면 스윕된다); 설정 저장과 미리보기 지우기 사이에 도착한 bake는 버려지고 다시 그려진다(W2 창, 좁아짐).
  서버는 재시도 가능한 409마다 `"busy": "lock" | "preparing" | "preview"`(도우미 하나, `_busy`)를, 바뀐
  실행에는 `"stale": true`를 붙인다; 문구는 바뀌지 않았다. 페이지는 그 필드만으로 결정한다: busy 답을 받은 그 요청 하나를
  0.5, 1, 2 s 뒤에, 첫 전송 이후 15 s를 넘기지 않는 범위에서 반복하고, 그다음 메시지를
  동일한 요청을 한 번 더 보내는 "Try again" 버튼과 함께 남긴다. "The previous run is finishing"도 태그되어
  다른 것들처럼 재시도된다. 절대 반복하지 않는 것: 네트워크 오류(응답 없음, 결과 불명), 태그 없는 409, 그리고 "being prepared"로 답한 `POST
  run`(다른 실행이 만들어지는 중이다: 페이지는 버튼을 보여 주고 대신 그 다른 실행을 따라가며, 작업이 `detected`를 벗어날 때까지 초당 한 번 작업을 읽되 최대 15 s). `OutputGone` 409("the
  files directory is still being moved or made ...; try again later")는 의도적으로 태그가 없다: 멈춘 rename 또는 mkdir은
  프로세스가 재시작할 때까지 디렉터리를 펜스로 막으므로 제한된 재시도는 도움이 되지 않는다. JSON 호출의 경우 반복은
  사용자의 다음 동작보다 오래 살지 않는다(알림 epoch가 잠든 재시도, 늦은 응답, 그리고 대체된 호출의 늦은 종결 오류를 취소하며, 마지막은 알림 없이 버려진다); 조용한 미리보기 GET은 어떤 동작에도 속하지 않으며
  자신의 한도까지 실행된다. "stale" 응답은
  작업을 다시 불러와 바뀐 설정이 보이게 한다. 미리보기 GET(`fetchBusy`, 원본 `<img>` 대체)도
  같은 방식으로 조용히 재시도하며, 한도를 다 쓰면 오늘의 실패를 보여 준다. create 경로 자체의 busy 답(`_job_create`: 작업이 만들어진 뒤의 ensure 또는 cleanup busy)은
  태그가 없고 재시도되지 않는다.
  busy 답이 남기는 것: 어떤 것도 두 번 제출되지 않지만, 일부 busy 답은 요청이 상태를 바꾼 뒤에 오며 반복은 그 상태를 본다: `DELETE`는 정리 기록이 실패하기 전에 files 디렉터리를 치워 두었다(작업은 남고, 반복이 삭제를 끝낸다);
  `POST detect`는 감지 오류 노트를 `log.md`에 덧붙였다(반복하면 다시 덧붙인다: 중복된 로그 줄, 그 외에는 없음);
  `PUT sources` / `POST detect` / create takeover는 유휴 상태의 경쟁 작업을 삭제했을 수 있다(어쨌든 허용됨; 반복하면 폴더가 비어 있다). ensure / cleanup이
  busy였던 create는 만들어 둔 작업을 남긴다(고아, 허용됨).
- **제한되지 않는 것.** 데이터 루트; 돌아오지 않는 rename 또는 mkdir(위); 볼륨 자체의 회복(멈춘 호출은
  돌아올 때까지 데몬 스레드를 유지한다).

근거(별도 언급이 없으면 `maker/test/test_local_bounds.py`의 테스트):

| 한도 | 테스트 |
|---|---|
| 펜스, 공유 읽기, 보류 쓰기 스레드 | `test_rename_bounded_abandons_a_hung_rename_and_fences_the_path`, `test_a_read_only_call_waits_for_the_one_in_flight`, `test_pending_op_returns_by_the_deadline_while_the_pending_lock_is_held`, `test_pending_op_returns_by_the_deadline_while_fsync_hangs`, `test_pending_op_with_an_expired_deadline_still_lands_on_a_healthy_disk`, `test_records_after_a_stalled_one_do_not_wait_the_floor`, `test_the_pending_writer_exits_when_idle_and_restarts` |
| 정지와 스윕 | `test_stop_returns_by_the_deadline_although_a_rename_hangs`, `test_an_abandoned_rename_never_moves_a_later_generation`, `test_stop_returns_by_the_deadline_while_fsync_hangs`, `test_stop_lands_its_pending_records_before_returning`, `test_an_idle_sweep_does_not_wait_beyond_its_deadline_for_the_lifecycle_lock`, `test_a_retry_starts_no_filesystem_call_after_its_deadline` |
| 잊기 전에 기록하는 delete | `test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job`, `test_the_only_job_of_a_folder_leaves_a_findable_tombstone_when_deleted`, `test_a_failed_takeover_that_cannot_record_answers_409_busy_and_keeps_the_job` |
| 시작 | `test_startup_returns_by_the_deadline_although_a_rename_hangs`, `test_startup_with_several_hung_tombstones_returns_by_the_single_deadline`, `test_startup_returns_by_the_deadline_although_listdir_hangs`, `test_startup_with_hung_tombstones_and_a_stalled_writer_returns_by_the_deadline`, `test_an_orphan_tombstone_is_swept_at_start_up` |
| 락 걸린 I/O, 락 순서 | `test_a_create_is_not_held_by_a_hung_output_stat_in_ensure`, `test_a_create_is_not_held_by_a_hung_mkdir`, `test_a_lifecycle_holder_does_not_wait_for_a_held_job_lock`, `test_a_preview_and_a_settings_change_of_one_font_do_not_deadlock`, `test_a_settings_put_never_waits_for_a_preview_lock_under_the_job_lock`, `test_after_a_settings_put_returns_the_old_preview_is_never_served` |
| 실행 준비와 commit | `test_a_create_is_not_held_by_a_run_reading_a_hung_input`, `test_a_create_is_not_held_by_a_run_hashing_a_hung_licence`, `test_a_create_is_not_held_by_a_run_planning_on_a_hung_volume`, `test_run_preparation_holds_no_lifecycle_lock`, `test_a_run_whose_job_changed_while_preparing_is_refused`, `test_a_second_run_during_preparation_is_refused`, `test_a_run_waits_a_bounded_time_for_a_preview_lock` |

### 7.9. 데스크톱 앱: 마감 근거(카드 t_f04f1355 셸, t_e64a56a7 패키징)

| 마감 측정 | 근거 |
|---|---|
| 셸이 Linux에서 앱을 열고, 브리지를 통해 파일과 폴더를 고르고, 샘플을 출력 폴더로 변환하고, 고아 프로세스 없이 깔끔하게 종료한다 | `desktop/test/e2e.js`(`bridge`, `flow`, `open-folder`, 가드, 재시작, privacy; dev와 패키지 패스, 30개 검사)와 `desktop/test/lifecycle.test.js`(close, SIGTERM, 셸의 SIGKILL, 두 번째 인스턴스); 릴리스 검사의 `smoke` |
| 동결된 사이드카가 python이 PATH에 없는 깨끗한 환경에서 OFL 샘플 세트를 source 모드와 바이트 단위로 동일하게 변환한다 | `maker/test/test_frozen.py`(26개 테스트, `FrozenByteEqualTest`, 빈 PATH와 `env -i` 아래의 `test_frozen_jobs_match_source`, `test_frozen_notes_equal_source`), 추출된 AppImage에서 건너뜀 없이 다시(`release-check.sh` `frozen`) |
| AppImage가 로컬 스크립트로 빌드되고 실행된다 | `desktop/build/build-appimage.sh`; 추출된 `AppRun` smoke(호스트에 FUSE 없음) |
| THIRD-PARTY 생성 | `desktop/test/third-party.test.js`(12개 테스트)와 추출본에 대한 `licences` 검사 |
| Windows와 macOS 단계는 UNVERIFIED로 문서화됨 | `docs/maker-desktop.md` |

고아 프로세스와 수명 주기 규칙(`maker/toolreg.py`, `--exit-with-parent`, `instance.lock`)은 `test_toolreg.py`,
`test_server_signals.py`, `test_frozen.py`에서 테스트한다. Not verified: `docs/maker-desktop.md`를 참조한다.
