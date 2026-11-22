[English](README.md) | **한국어**

# ESP32 예제 (ESP-IDF): colour, grey, mono 프로필 (기본: colour)

프로필마다 이미지 하나이며, 구성 시점에 `-DSVF_PROFILE=colour|grey|mono`로 고른다(기본 `colour`). `main/main.c`는
`display_init(); profile_run();`을 실행한 뒤 `svf_port_idle()`(`vTaskDelay` 안에서 영원히 잠드는,
인라인되지 않은 함수)로 들어간다. 그리기는 `main/profile_<p>.c`에, 패널은 `main/disp_<driver>.c`에 있다.

| profile | panel | driver | wiring (ESP32-C3 / ESP32-S3) | faces |
|---|---|---|---|---|
| `colour` | 320 x 240 RGB565 ILI9341, SPI2 | `disp_ili9341.c` | MOSI 7 / 11, SCLK 6 / 12, CS 10, DC 2 / 4, RST 3 / 5 | `svf/dos/PAPLG16.SVF` + `PAPLG18.SVF` |
| `colour`, `-DSVF_DISPLAY=esp_rgb` 사용 | QEMU의 320 x 240 RGB 패널, 일반 MMIO | `disp_esp_rgb.c` | 없음 | 같음 |
| `grey` | 128 x 128 SSD1327, SPI2 | `disp_ssd1327.c` | MOSI 7 / 11, SCLK 6 / 12, CS 10, DC 2 / 4, RST 3 / 5 | 같음 |
| `mono` | 128 x 64 SSD1306, SPI2 | `disp_ssd1306.c` | MOSI 7 / 11, SCLK 6 / 12, CS 10, DC 2 / 4, RST 3 / 5 | `svf/dos/NEODG16G.SVF` |

`SVF_DISPLAY`(`ili9341`이 기본, 또는 `esp_rgb`)는 `colour`에만 의미가 있다. 다른 프로필에 `esp_rgb`를 주면
오류이다. `c/ports/profiles.txt`가 프로필의 바탕이 되는 표이다(종류, `SVF_TARGETS` 비트, 페이스, 드라이버, 버스).
`c/ports/profiles.cmake`가 이를 읽는다. 라이브러리는 `SVF_NO_SCALE`과 프로필의 `SVF_TARGETS` 비트 하나로 빌드한다
(IDF 타깃이 esp32s3이면 `SVF_ESP32S3=1`도 준다). grey 프로필은 GRAY8을 그리고 드라이버가 이를
SSD1327의 픽셀당 4비트로 패킹한다. `-DSVF_GREY_KIND=GRAY8`(유일한 값이며 기본값)은 그 종류를 지정하는
캐시 STRING이다.

툴체인(여기서 빌드하고 측정함): ESP-IDF **v5.5.6**(`~/opt/esp-idf-v5.5.6`. esp32s3와 esp32c3 타깃용으로 설치했으며 자체 Python 3.12 환경을 쓴다.
`~/opt/esp-idf-NOTES.txt` 참조). 설치 프로그램이 컴파일러(ESP32-C3용 `riscv32-esp-elf`, ESP32-S3용 `xtensa-esp32s3-elf`), CMake, Ninja를 가져온다.

빌드(ESP-IDF가 설치되고 `. $IDF_PATH/export.sh`로 export되어 있거나 `-DIDF_PATH=<esp-idf 디렉터리>`. 페이스 배열용 python3 필요). 프로필과 칩마다
빌드 디렉터리 하나를 쓴다.

    cd c/ports/esp32
    idf.py -B build-colour -DSVF_PROFILE=colour set-target esp32c3 && idf.py -B build-colour build flash monitor
    idf.py -B build-grey   -DSVF_PROFILE=grey   set-target esp32s3 && idf.py -B build-grey build
    idf.py -B build-mono   -DSVF_PROFILE=mono   set-target esp32c3 && idf.py -B build-mono build
    idf.py -B build-qemu   -DSVF_PROFILE=colour -DSVF_DISPLAY=esp_rgb set-target esp32s3 && idf.py -B build-qemu build

`idf.py`는 `sdkconfig`와 `sdkconfig.old`도 `c/ports/esp32`(빌드 디렉터리가 아니라 프로젝트 디렉터리)에 쓴다. `c/ports/esp32/.gitignore`가 이들과
`build-*` 디렉터리를 나열한다. `set-target`은 빌드 디렉터리를 비운다. 이미 있는 디렉터리에서 프로필이나 칩을 바꾸려면 `idf.py -B <dir>
fullclean`을 실행하고 다시 구성하거나 새 `-B`를 쓴다. 오래된 캐시는 이전 `SVF_PROFILE` / `SVF_DISPLAY`를 유지한다
(`idf.py`의 `-D` 옵션은 CMake가 구성될 때에만 캐시에 전달된다). 빌드 디렉터리는 프로필에 묶인다(grey는
`SVF_GREY_KIND`에도 묶인다). 다른 `SVF_PROFILE`(grey는 다른 `SVF_GREY_KIND`)로 다시 구성하면
오류("configured for ...")가 난다. 새 `-B` 디렉터리를 쓰거나 이전 것을 지운다.

`main/CMakeLists.txt`는 빌드 시 `c/bench/mkface.py`로 프로필의 페이스 배열을 생성하고(커밋되지 않음: PAPLG18은
`mcu-strict` 레이아웃에서 67,200바이트 페이스이며 C로 약 186 KB이다) 라이브러리 소스를 `main` 컴포넌트에 빌드한다.
`-DSVF_FACE_ASCII=` / `-DSVF_FACE_HANGUL=`은 colour와 grey에서 다른 페이스를 고르고, `-DSVF_FACE=`는 mono에서 다른 16 px 1 bpp 페이스를
고른다.

라이선스: 이미지는 폰트 소프트웨어를 내장한다([FACES.md](../FACES.ko.md)가 각 페이스의 출처, 저작권, 라이선스를 적는다).
배포하는 이미지는 `c/ports/FACES.md`와 라이선스 문서(`svf/dos/OFLPAPLG.TXT`,
`svf/dos/OFL.TXT`, `svf/dos/NEODGM.TXT`)와 저장소의 `LICENSE`(코드의 MIT 라이선스)를 함께 두어야 한다. 구성하면 이들이 `<build>/licences/`로 복사된다
(`LICENSE`는 `LICENSE-MIT.txt`로).

`main/main_qemu.c`는 QEMU 화면 실행용 베어메탈 main이다. `display_init(); profile_run();`을 실행한 뒤 newlib 세미호스팅 콘솔에
`screen=ready`(프로필 호출이 실패했으면 `screen=failed`)를 출력하고 제자리에서 돈다. IDF 헤더는 필요 없다.

가정한 모듈(데이터시트와 흔한 브레이크아웃 보드에 맞춰 작성했으며 패널에서는 시험하지 않았다)과, 흔한 변형을 위해
바꿀 바이트 하나는 다음과 같다.

- ILI9341, 320 x 240: `MADCTL`(`0x36`)을 `0x28`로 한다(가로 방향을 위한 행/열 교환, BGR 패널. RGB
  모듈은 `0x20`). `COLMOD`는 `0x55`, `INVON` 없음.
- SSD1327, 128 x 128: 리맵 `0xA0`에 `0x51`(비트 1, 니블 리맵이 해제됨: 한 쌍의 왼쪽 픽셀이 상위
  니블이며 `grey_pack_rows`가 패킹하는 순서이다). 각 쌍이 서로 바뀌어 보이는 모듈은 `0x53`이 필요하다.
- SSD1306, 128 x 64: 세그먼트 리맵과 COM 스캔 `0xA1`, `0xC8`.

`esp_rgb`(QEMU의 RGB 패널, `-DSVF_DISPLAY=esp_rgb`): `disp_esp_rgb.c`는 프레임을 패널의 VRAM과 갱신 레지스터에 쓰며
`RGB_UPDATE_STATUS`를 **폴링하지 않는다**. 장치는 다음 갱신 때(`-display none`에서는 `screendump`, 실제 디스플레이에서는 다음 리프레시) 복사하고
그때까지 상태는 1로 남는다. 따라서 `esp_lcd_qemu_rgb`처럼 이를 기다리는 드라이버는 `-display none`에서 멈추게 된다.
그러므로 이미지는 호스트가 복사를 요청할 때까지 아무것도 보여 주지 않는다.

## 확인한 것

ESP-IDF v5.5.6이 여기에 설치되어 있고 `idf.py`가 프로필들을 빌드한다. ESP32-C3용 colour, ESP32-S3용 grey, ESP32-C3용 mono이다
(2026-11-22에 깨끗한 `git archive`에서 Release로 측정. 이미지는 기본 1 MB 애플리케이션 파티션에 들어간다. `svf_esp32_colour.bin` 294,960바이트(여유 72 %),
`svf_esp32_grey.bin` 317,856(70 %), `svf_esp32_mono.bin` 229,648(78 %). `idf.py size`: colour 이미지는 플래시 코드 109,930바이트, `.rodata` 117,180(페이스 74,660),
`.bss` 19,320이고, mono 이미지는 `.bss` 4,920이다). 두 `CMakeLists.txt`는 `test_esp32_cmake.sh`와 `test_esp32_component.sh`(대용 `IDF_PATH`, 모의 IDF 명령)로도
실행한다. 하드웨어에서 실행된 것은 없다. 프로필별 상태는 다음과 같다.

| | colour (ILI9341, 또는 `esp_rgb`) | grey (SSD1327) | mono (SSD1306) |
|---|---|---|---|
| 호스트 검사(`sh c/ports/check/host-checks.sh`: 기록용 `display_show`를 거친 실제 `profile_<p>.c`를 `c/ports/check/screen_ref.py`와 비교. colour는 두 픽셀 순서와 ESP32-S3 제목 모두. 기록용 스텁에 대한 드라이버 명령 스트림. `esp_rgb` 레지스터 쓰기 횟수) | yes | yes | yes |
| 구성 규칙과 컴포넌트 소스(`test_esp32_cmake.sh`, `test_esp32_component.sh`) | yes | yes | yes |
| `stub/`에 대해 riscv32(ESP32-C3)와 xtensa(ESP32-S3)용으로 링크(`c/cross/build-all.sh --ports`), 페이스 제외 text(`c/cross/SIZES.md`) | C3 12,022 바이트, S3 10,392 | C3 11,770, S3 9,988 | C3 12,050, S3 10,452 |
| ESP-IDF v5.5.6으로 `idf.py build`(위의 이미지들) | yes (C3) | yes (S3) | yes (C3) |
| `profile_colour.c` + `disp_esp_rgb.c`의 베어 이미지를 QEMU 9.2.2 `-M esp32c3`와 `-M esp32s3`에서 실행(`sh c/ports/check/run-screens.sh`): VRAM과 `screendump` PPM이 양쪽 모두 참조와 같다 | yes (`esp_rgb` 빌드만) | no | no |
| 빌드만 했거나 읽기만 함: SPI 타이밍, 패널 변형, 핀 매핑, 실제 패널에서의 ILI9341 / SSD13xx SPI 경로 | yes | yes | yes |

C3와 S3 화면의 PNG는 `run-screens.sh`가 `c/build/screens/esp32c3-colour.png`와 `esp32s3-colour.png`에 쓴다
(커밋되지 않음). `main_qemu.c`는 기록용 스텁으로 호스트에서도 실행된다. `c/cross/build-all.sh
--ports`는 이 모두를 실행하고 `OK` 줄 43개를 출력한다(`c/ports/pico/README.md` 참조). 속도: `c/bench/MEASUREMENTS.md`에
ESP32-C3와 ESP32-S3 bench가 있으며, QEMU에서의 명령 수이고 사이클도 마이크로초도 아니다.
