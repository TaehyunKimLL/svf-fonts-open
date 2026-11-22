[English](README.md) | **한국어**

# Raspberry Pi Pico 예제 (pico-sdk): colour, grey, mono 프로필 (기본: mono)

프로필마다 이미지 하나이며, 구성 시점에 `-DSVF_PROFILE=colour|grey|mono`로 고른다(기본 `mono`). `main.c`는
`display_init(); profile_run();`을 실행한 뒤 `svf_port_idle()`(영원히 잠드는, 인라인되지 않은 함수)로 들어간다. stdio도,
세미호스팅도 없으며 예제 자체 코드에는 BKPT도 없다.

| profile | panel | driver | wiring | faces |
|---|---|---|---|---|
| `colour` | 240 x 240 RGB565 ST7789, SPI0 | `disp_st7789.c` | MOSI GP19, SCK GP18, CS GP17, DC GP16, RST GP20 | `svf/dos/PAPLG16.SVF` + `PAPLG18.SVF` |
| `grey` | 128 x 128 SSD1327, I2C0 | `disp_ssd1327.c` | SDA GP4, SCL GP5, address 0x3C | `PAPLG16.SVF` + `PAPLG18.SVF` |
| `mono` | 128 x 64 SSD1306, I2C0 | `disp_ssd1306.c` | SDA GP4, SCL GP5, address 0x3C | `svf/dos/NEODG16G.SVF` |

`c/ports/profiles.txt`가 이들의 바탕이 되는 표이다(종류, `SVF_TARGETS` 비트, 페이스, 드라이버, 버스). `profiles.cmake`가 이를 읽는다.
라이브러리는 `SVF_NO_SCALE`과 프로필의 `SVF_TARGETS` 비트 하나로 빌드한다. grey 프로필은 GRAY8을 그리고
드라이버가 이를 SSD1327의 픽셀당 4비트로 패킹한다. `-DSVF_GREY_KIND=GRAY8`(유일한 값이며 기본값)은 그 종류를 지정하는
캐시 STRING이다.

툴체인(여기서 빌드하고 측정함): pico-sdk **2.3.1**(`~/opt/pico-sdk-2.3.1`), arm-none-eabi-gcc 15.2.1(Arm GNU Toolchain 15.2.Rel1.
`sh c/cross/install-toolchains.sh "$HOME/opt" arm`이 `~/opt/arm-gnu-toolchain-15.2.rel1/bin`에 넣으며 이것이 `PATH`에 있어야 한다), CMake, 페이스 배열용 python3,
`.uf2`용 picotool 2.3.1.

빌드(pico-sdk 설치됨. 페이스 배열용 python3 필요). 프로필마다 빌드 디렉터리 하나를 쓴다.

    cmake -S c/ports/pico -B build-pico-mono   -DSVF_PROFILE=mono   -DPICO_SDK_PATH=/path/to/pico-sdk
    cmake -S c/ports/pico -B build-pico-grey   -DSVF_PROFILE=grey   -DPICO_SDK_PATH=/path/to/pico-sdk
    cmake -S c/ports/pico -B build-pico-colour -DSVF_PROFILE=colour -DPICO_SDK_PATH=/path/to/pico-sdk
    cmake --build build-pico-colour      # build-pico-colour/svf_pico_colour.elf and .uf2

`PICO_SDK_PATH`는 대신 환경 변수로 줄 수도 있다. 아래의 크기는 `-DCMAKE_BUILD_TYPE=Release`일 때의 값이다.

**Pico 2(RP2350, Arm 코어).** 같은 소스가 `-DPICO_BOARD=pico2`(pico-sdk의 보드 이름이며 `rp2350-arm-s` 플랫폼을 고른다)로 빌드된다. 빌드 디렉터리는 각각 새것을 쓴다.

    cmake -S c/ports/pico -B build-pico2-mono -DSVF_PROFILE=mono -DPICO_BOARD=pico2 -DPICO_SDK_PATH=/path/to/pico-sdk

세 프로필 모두 빌드된다(크기는 "확인한 것" 아래). Pico 이미지처럼 보드에서 실행한 적은 없다.
아래의 수동 `.uf2` 변환은 RP2040용이다. Pico 2에서는 SDK의 picotool 단계가 만들게 하거나(`-DPICO_NO_PICOTOOL=1` 없이 구성한다),
`picotool uf2 convert`에 RP2350 패밀리와 플랫폼을 준다. 빌드 디렉터리는 프로필에 묶인다(grey는 `SVF_GREY_KIND`에도 묶인다).
다른 `SVF_PROFILE`(grey는 `SVF_GREY_KIND`)로 다시 구성하면 오류("configured for ...")가 난다. 새
`-B` 디렉터리를 쓰거나 이전 것을 지운다. `CMakeLists.txt`는 빌드 시 `c/bench/mkface.py`로 페이스 배열을 생성한다(커밋되지 않음).
`-DSVF_FACE_ASCII=` / `-DSVF_FACE_HANGUL=`은 colour와 grey에서 다른 페이스를 고르고, `-DSVF_FACE=`는 mono에서 다른 16 px 1 bpp
페이스를 고른다.

`.uf2`: SDK 2.x는 picotool로 만든다. SDK의 CMake는 설치된 picotool CMake 패키지를 찾고
(`find_package(picotool CONFIG)`: picotool 빌드의 `cmake --install` 또는 `-Dpicotool_DIR=<picotoolConfig.cmake가 있는 디렉터리>`.
PATH에 `picotool` 바이너리만 있는 것으로는 찾지 못한다), 없으면 git에서 picotool을 가져와 빌드한다.
검사 빌드는 `-DPICO_NO_PICOTOOL=1`을 주어 picotool을 건너뛰고 `.elf`만 만든다. `.uf2`가 필요하면 그 옵션 없이 구성하거나,
가지고 있는 picotool로 직접 변환한다.

    picotool uf2 convert build-pico-colour/svf_pico_colour.elf build-pico-colour/svf_pico_colour.uf2 --family rp2040 --platform rp2040

가정한 모듈(데이터시트와 흔한 브레이크아웃 보드에 맞춰 작성했으며 패널에서는 시험하지 않았다)과, 흔한 변형을 위해
바꿀 바이트 하나는 다음과 같다.

- ST7789, 240 x 240: init의 `MADCTL`(`0x36`)을 `0x00`(기본 방향, RGB 순서)으로 하고 `INVON`(`0x21`, 일반적인
  IPS 모듈)을 쓴다. BGR 모듈은 `0x36`의 매개변수로 `0x08`이 필요하고, 색이 반전되어 잘못 보이는 모듈은
  `0x21` 대신 `0x20`(`INVOFF`)이 필요하다. 많은 240 x 240 모듈은 `MADCTL`에 MY가 설정되면(`0xC0`, 180도 회전)
  컨트롤러의 240 x 320 RAM 중 80행부터 319행을 보여 준다. 그 경우 `RASET`의 시작과 끝이 80 높아진다. 여기서 쓰는 `0x00`에서는
  윈도가 0행에서 시작하며 아무것도 더하지 않는다.
- SSD1327, 128 x 128: 리맵 `0xA0`에 `0x51`(비트 0 열 주소 리맵 설정, 비트 1 니블 리맵 해제: 한 쌍의 왼쪽
  픽셀이 상위 니블이며 `grey_pack_rows`가 패킹하는 순서이다. 비트 4 COM 리맵, 비트 6 홀수/짝수 분할). 각 픽셀 쌍이
  서로 바뀌어 보이는 모듈은 그 매개변수 하나를 `0x53`으로 해야 한다.
- SSD1306, 128 x 64: 세그먼트 리맵과 COM 스캔 `0xA1`, `0xC8`(흔한 모듈에서 (0, 0)이 왼쪽 위).

XIP 캐시 주의: colour와 grey 이미지는 페이스 74,660바이트를 RP2040의 16 KB XIP 캐시 뒤 플래시에 둔다
(mono 이미지는 빌드된 이미지에서 페이스 10,124바이트, text 35,484바이트). rp2040js도 bench도 이 캐시를 모델링하지 않으므로, 실제 그리기 시간은 에뮬레이션된
시간이거나 그보다 느리며, 그 차이를 여기서 측정한 것은 없다(`c/bench/MEASUREMENTS.md`).

라이선스: 이미지는 폰트 소프트웨어를 내장한다([FACES.md](../FACES.ko.md)가 각 페이스의 출처, 저작권, 라이선스를 적는다). 배포하는 이미지는 `c/ports/FACES.md`와 라이선스 문서
(`svf/dos/OFLPAPLG.TXT`, `svf/dos/OFL.TXT`, `svf/dos/NEODGM.TXT`)를 함께 두어야 한다. 구성하면 이들이
`<build>/licences/`로 복사된다. 저장소의 `LICENSE`(코드의 MIT 라이선스)도 `LICENSE-MIT.txt`로 함께 복사된다.

## 확인한 것

하드웨어는 실행하지 않았다. 프로필별 상태는 다음과 같다.

| | colour (ST7789) | grey (SSD1327) | mono (SSD1306) |
|---|---|---|---|
| 호스트 검사(`sh c/ports/check/host-checks.sh`: 기록용 `display_show`를 거친 실제 `profile_<p>.c`를 `c/ports/check/screen_ref.py`와 비교. 기록용 스텁에 대한 드라이버 명령 스트림) | yes | yes | yes |
| 실제 pico-sdk 2.3.1에 대한 빌드(`-DPICO_NO_PICOTOOL=1`. `PICO_SDK_PATH`가 설정되어 있으면 `sh c/ports/check/test_pico_cmake.sh`가 구성 규칙을 검사한다) | yes | yes | yes |
| 패널 모델 위에서 rp2040js로 실행(`sh c/ports/check/run-screens.sh`): 패널 메모리가 참조와 같고 `svf_port_idle`에서 끝난다 | yes: 15회 show, 에뮬레이션 280.6 ms | yes: 1회 show, 에뮬레이션 13.9 ms | yes: 1회 show, 에뮬레이션 2.6 ms |
| `stub/`에 대해 Cortex-M0+용으로 링크(`c/cross/build-all.sh --ports`), 페이스 제외 text(`c/cross/SIZES.md`) | 9,646 바이트 | 9,486 | 9,554 |
| pico-sdk 2.3.1 이미지, Pico(`arm-none-eabi-size`, Release. 내장 페이스 포함. 2026-11-22에 깨끗한 `git archive`에서 측정) | text 99,828, data 0, bss 12,812 | text 99,256, data 0, bss 17,936 | text 35,484, data 0, bss 2,384 |
| 같은 것을 Pico 2(`-DPICO_BOARD=pico2`)로 | text 98,176, data 0, bss 12,428 | text 97,420, data 0, bss 17,552 | text 33,636, data 0, bss 2,000 |
| 빌드만 하고 실행하지 않음: 타이밍, 전압, 패널 변형, 핀 매핑, `.uf2` 단계 | yes | yes | yes |

세 번째 행의 시간은 SDK 시작과 패널의 init 지연(`sleep_ms`, colour 이미지 280.6 ms 중 242 ms)을 포함한 이미지 전체 실행에 대한
rp2040js의 에뮬레이션 클럭(`nanos`)이며, 그리기 시간도 아니고 Pico의 측정값도 아니다.
명령 사이클 카운터(`cycles`, `c/bench/MEASUREMENTS.md`의 "Screens")는 다른 수치이다. 패널의 PNG는 `run-screens.sh`가
`c/build/screens/pico-<profile>.png`에 쓴다(커밋되지 않음). `c/cross/build-all.sh --ports`는 호스트 검사, `run-screens.sh`,
`test_pico_screen.sh`, `c/ports/check`의 단위 테스트를 실행하고 `OK` 줄 43개를 출력한다: 14 ports + 19 `port-check-*` +
5 `screen-*` + `pico-screen-negative` + `run-screens-gates` + 단위 테스트 3개(`port-check-unit-*`). 스텁 링크의
크기는 `c/cross/SIZES.md`의 "Port examples" 표의 Pico 행이고, pico-sdk 링크의 크기는 같은 문서의 "Pico SDK
images" 표이며 `run-screens.sh`가 이를 측정값과 비교한다.

속도: `c/bench/MEASUREMENTS.md`에 대상 종류별 Pico bench가 있다(에뮬레이션, rp2040js).
