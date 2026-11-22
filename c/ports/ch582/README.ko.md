[English](README.md) | **한국어**

# CH582M 예제 (YD-CH582M 보드, 하드웨어 I2C로 연결한 SH1106 128 x 64 OLED): mono 프로필, 베어메탈

이미지는 `svf_ch582_mono` 하나이다. YD-CH582M 보드의 WCH CH582M(RISC-V RV32IMAC, SRAM 32 KB, CodeFlash 448 KB)이
`svf/dos/NEODG16G.SVF`(1 bpp 자모 세트, `MONO_PAGE`)의 네 줄을 1.3" SH1106 OLED에 그리고 멈춘다. `main.c`는
`SetSysClock(CLK_SOURCE_PLL_24MHz); led_init(); display_init(); profile_run();`을 실행한 뒤 `svf_port_idle()`(상태
LED)로 들어간다. 베어메탈이며 폴링 방식이다. stdio, `PRINT`, 인터럽트, BLE 스택, 슬립 모드, 벤더 IDE가 없다
(Makefile과 stock GCC, WCH EVT 소스만 쓴다). **패널에서는 아직 시험하지 않았다**: 여기 있는 어떤 것도 보드에서 실행된 적이 없다
("확인한 것" 참조).

**이미지는 24 MHz로 동작한다.** EVT 예제의 60 MHz가 아니다. CH582의 I2C 모듈 클럭은 2..36 MHz여야 하며
(`I2C_Init`은 시스템 클럭을 MHz 단위로 FREQ 필드에 쓴다), 32 MHz에서는 SDK의 분주기가 16/9 듀티로 약 427 kHz
SCL을 만들고(듀티 2에서는 약 410 kHz), 어느 쪽이든 SH1106의 400 kHz 한계를 넘는다. 24 MHz에서 `I2C_DutyCycle_2`를 쓰면 분주값이 정확히 24e6 / (400e3 x 3) = 20이므로
SCL은 400 kHz가 된다. Makefile의 `FREQ_SYS=24000000`은 `main.c`의 `SetSysClock`과 일치해야 한다.

## 보드

레이블은 보드 사진에서 읽은 것이다. status 열은 무엇이 알려져 있고 무엇이 가정인지 적는다.

| part | pin | status |
|---|---|---|
| Type-C = USB1 (ISP 부트로더) | PB10 UD-, PB11 UD+ | 핀: 데이터시트(모든 CH58x의 ISP 포트). Type-C 커넥터가 이 핀에 연결되어 있다는 것은 USB-A 행과 마찬가지로 **보드에 대한 가정**이다 |
| USB-A 호스트 포트 = USB2 | PB12 U2D-, PB13 U2D+ | 보드에서 온 **가정**(남은 유일한 USB 핀). 검증하지 않았다 |
| BOOT 버튼 | PB22: USB 부트로더를 쓰려면 리셋 또는 전원 인가 중에 누르고 있는다 | wchisp의 CH58x 장치 표(`DOWNLOAD_CFG` 1 = PB22, 기본값) |
| RST 버튼 | PB23 (RST#, 내부 풀업) | 데이터시트 |
| LED | PB4 (실크스크린 "PB4"). 극성 불명 | **가정**: active low(WeAct 보드처럼 LED가 3V3와 핀 사이에 있다). 펌웨어가 깜박이므로 어느 극성이든 패턴이 보인다 |
| PWR LED | (전원) | -- |
| 2 x 4 헤더 (사진에서 구멍 8개) | PB14 TIO, PB15 TCK + 3V3/GND | **추측**: 2선 디버그 헤더 |

이 보드에서는 PB12/PB13을 USB2의 D-/D+로 본다(표의 가정이며, 핀 열에도 B12/B13으로 나온다). 따라서 OLED는 I2C 핀 리맵(`GPIOPinRemap(ENABLE, RB_PIN_I2C)`)을 쓴다:
**SCL은 PB21, SDA는 PB20**. 하드웨어 I2C 마스터, 7비트 주소 0x3C, 400 kHz, 핀은 `GPIO_ModeIN_PU`(내부
풀업 켬. 모듈 자체의 풀업도 도움이 된다).

배선. 두 핀 모두 보드 아래쪽 가장자리를 따라 있는 2열 헤더에 있으며 서로 다른 열이다. **B21은 안쪽 열**
(B23과 B19 사이. 이 열은 3.3V로 시작한다)이고 **B20은 가장자리 열**(B22와 B18 사이. 이 열은 GND로 시작한다)이다.
B20 옆의 B22는 BOOT 핀이므로 연결하지 않는다.

| OLED | board |
|---|---|
| VCC | 3.3V |
| GND | GND |
| SCL | **B21** |
| SDA | **B20** |

## 빌드

`make`, `python3`(페이스 배열은 커밋되지 않고 빌드 시 `c/bench/mkface.py`에서 만들어진다)가 필요하며, 저장소의 설치 스크립트가
`$HOME/opt` 아래에 다음 도구를 설치한다.

    sh c/cross/install-toolchains.sh "$HOME/opt" esp ch583 wchisp
    make -C c/ports/ch582

그러면 `build/svf_ch582_mono.{elf,bin,hex,map}`과 `build/licences/`가 만들어지고 크기가 출력된다. `make size`는 크기를 다시 출력하고,
`make flash`는 아래에 설명하며, `make clean`은 `build/`를 지운다. 변수(모두 명령줄에서 덮어쓸 수 있다):

| variable | default | meaning |
|---|---|---|
| `OPT` | `$(HOME)/opt` | 설치 스크립트가 도구를 놓은 위치 |
| `CROSS` | `$(OPT)/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-` | 컴파일러 접두사(`riscv32-esp-elf-gcc` 16.1.0, `esp` 툴체인. `PATH`에 없다) |
| `CH583_SDK` | `$(OPT)/ch583-evt` | WCH CH583 EVT 클론(`EVT/EXAM/SRC/`와 루트의 `LICENSE`만 쓴다). `Ld/Link.ld` 또는 `LICENSE`가 없으면 Makefile이 메시지와 함께 멈춘다 |
| `WCHISP` | `$(OPT)/wchisp-0.3.0/wchisp` | 플래시 도구 |
| `BUILD` | `build` | 출력 디렉터리 |
| `EXTRA_CFLAGS` | 비어 있음 | 포트 자체 파일을 위한 추가 플래그(아래의 드라이버 변형) |
| `STACK_INFO` | 비어 있음 | `1`이면 `-fstack-usage -fcallgraph-info=su`를 추가한다(`c/cross/stack-usage.py`가 읽는다) |

`EXTRA_CFLAGS`, `STACK_INFO` 또는 다른 플래그가 바뀌면 오브젝트를 다시 빌드한다(플래그 스탬프 `build/obj/flags.stamp`).

대체 컴파일러는 xPack riscv-none-elf-gcc 15.2.0-1이다(문서화만 되어 있고 여기에는 설치하지 않았다. 플래그는 같다).
`https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v15.2.0-1/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz`
(433,494,794 바이트, sha256 `aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758`). 이것은
`make -C c/ports/ch582 CROSS=riscv-none-elf-`로 쓴다(`bin/`을 `PATH`에 넣는다).

플래그의 이유. SDK 소스(`CH58x_gpio.c`, `CH58x_i2c.c`, `CH58x_sys.c`, `startup_CH583.S`)는
WCH GCC 8용으로 작성되어 있어 `-DINT_SOFT -w`를 받는다. `INT_SOFT`는 `__INTERRUPT`를 일반 `interrupt()` 속성으로 만든다
(stock GCC는 WCH의 `"WCH-Interrupt-fast"`를 거부하는데, `-Werror`가 이를 오류로 만들 것이다). `-w`는 벤더 경고가 `-Werror` 빌드에 나타나지 않게 한다.
포트의 파일은 `-std=gnu99`를 받는다. WCH 헤더(`core_riscv.h`)가 static inline 안에서 `asm volatile`을 쓰는데
`-std=c99`는 이를 거부하기 때문이다. 라이브러리와 호스트 및 스텁 빌드는 `-std=c99`를 유지한다. `-mstrict-align`은 켜져 있다.
코어가 정렬되지 않은 로드를 어떻게 처리하는지 문서화되어 있지 않기 때문이다(라이브러리는 그런 로드가 필요 없다). 라이브러리는
`-DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0`으로 빌드한다(매핑된 페이스, 레이아웃 하나,
`MONO_PAGE`만, JSET 버전 1 리더만. 포트는 Arduino 포트와 마찬가지로 버전 1 페이스 NEODG16G를 그린다. 버전 2 페이스를 열려면
라이브러리 오브젝트에도 적용되는 Makefile의 `SVFDEFS`에서 `-DSVF_JSET_V2=0`을 빼면 되며, 플래시가 약 1.5 KB 늘어난다). `link.ld`는 WCH의 `EVT/EXAM/SRC/Ld/Link.ld`와 바이트 단위로 같고, 기능상 변경 하나인 `__stack_size = 2048`(WCH는 512)과 출처 헤더 주석만 다르다. `libISP583.a`(WCH의 바이너리이며 Apache-2.0 EVT 저장소에 있다)는
`HardFault_Handler`가 그 안으로 호출하므로 링크된다.

## 플래시

Type-C 포트를 통해 [wchisp](https://github.com/ch32-rs/wchisp) v0.3.0(GPL-2.0. 플래시할 때만 실행하는 별도 도구이며 이미지에 링크되지 않는다)으로 한다.

1. 처음 한 번, root 없이 부트로더에 접근할 수 있도록 udev 규칙을 둔다.
   `SUBSYSTEM=="usb", ATTRS{idVendor}=="4348", ATTRS{idProduct}=="55e0", MODE="0666"`을
   `/etc/udev/rules.d/50-wchisp.rules`에 넣고 `sudo udevadm control --reload-rules && sudo udevadm trigger`를 실행한다.
2. Type-C 케이블을 꽂는 동안 BOOT 버튼(PB22)을 누르고 있다가 놓는다. `lsusb`에 아무것도 나오지 않으면 뽑고,
   BOOT를 누른 채 다시 꽂는다. (케이블을 꽂은 채 BOOT를 누르고 RST를 건드리는 방식은 칩 구성에서 RST 핀 기능이 켜져 있을 때만 동작한다.
   데이터시트의 기본값은 꺼짐이며 이 보드의 설정은 알 수 없다.)
   `lsusb`에 `4348:55e0`(WCH ISP 부트로더)이 보인다. 일부 WCH 부트로더는 대신 `1a86:55e0`으로 열거된다. `lsusb`에
   그렇게 나오면 `ATTRS{idVendor}=="1a86"`인 두 번째 규칙 줄을 추가한다(wchisp는 둘 다 처리한다).
3. `make -C c/ports/ch582 flash`(오래된 이미지는 먼저 다시 빌드하고, 플래시 배치를 확인한 뒤
   `wchisp flash build/svf_ch582_mono.elf`를 실행한다). 의심스러우면 `~/opt/wchisp-0.3.0/wchisp info`가 칩을 보여 준다.
4. 보드가 리셋되어 프로그램으로 들어간다. PB4의 LED가 결과를 알려 준다. **계속 켜짐** = 프레임이 전송되었고 모든
   바이트가 ACK되었다. **2 Hz** = I2C 쓰기가 타임아웃되었거나 ACK되지 않았다(패널 없음, 잘못된 주소, 잘못된 핀). **8 Hz** =
   `svf_*` 그리기 호출이 실패했다. LED 극성은 가정(active low)이다. 반대라면
   계속 켜짐이 꺼짐으로 보이지만 깜박임 패턴은 여전히 구별된다. RST를 누른 뒤(전원 인가 뒤가 아니라) LED가 2 Hz로 깜박이면
   보드의 전원을 껐다 켠다. 패널이 SDA를 low로 붙잡고 있을 수 있다.

## 모듈 변형

드라이버는 일반적인 132열 SH1106 모듈을 가정한다. 보이는 128열이 RAM 열 2..129에 있고
(0, 0)이 왼쪽 위에 오도록 장착된 모듈이다. 세 가지 스위치로 이를 바꾼다(`EXTRA_CFLAGS`이며 `flash`와 `make`/`size`에 똑같이 준다. 플래그
변경은 오브젝트를 다시 빌드하므로, 이후에 그냥 `make flash`를 하면 기본 이미지를 다시 빌드해 그것을 플래시하고
변형은 버려진다).

- `OLED_SSD1306`(기본 0): 1이면 진짜 SSD1306이다. "SH1106"으로 팔리는 모듈이 가끔 이쪽이다. 이 경우 init은
  SH1106의 DC-DC(`AD 8B`)와 펌프 전압(`32`) 대신 SSD1306의 차지 펌프(`8D 14`)와 페이지 주소 지정(`20 02`)을 보내고,
  대비, 프리차지, VCOMH는 Pico SSD1306 드라이버의 값을 쓰며, 열 오프셋 기본값은 0이 된다.
  SH1106 init을 쓰면 이런 패널은 LED가 성공을 알려도 화면이 비어 있다.
- `SH1106_COL_OFFSET`(기본 2): 첫 보이는 열의 RAM 열. RAM이 0열에서 시작하는 SH1106이면 0이다
  (그렇지 않으면 그림이 두 열 밀려 보인다).
- `SH1106_REMAP`(기본 1: 세그먼트 리맵 `0xA1`과 COM 스캔 반전 `0xC8`): 그림이 180도 회전해 보이면 0이다.

(a) RAM이 0열에서 시작하는 SH1106:

      make -C c/ports/ch582 EXTRA_CFLAGS=-DSH1106_COL_OFFSET=0 flash

(b) 진짜 SSD1306:

      make -C c/ports/ch582 EXTRA_CFLAGS=-DOLED_SSD1306=1 flash

(c) 거꾸로 장착된 모듈(컨트롤러 무관. 필요하면 (a)나 (b)에 이 플래그를 더한다. 예: `'-DOLED_SSD1306=1 -DSH1106_REMAP=0'`):

      make -C c/ports/ch582 EXTRA_CFLAGS=-DSH1106_REMAP=0 flash

init은 전원 인가 후 첫 명령 전에 20 ms(`SH1106_RESET_MS`)를 기다리고, 전체 디스플레이 RAM(8페이지 전부,
132열. 전원 인가 시에는 노이즈가 들어 있다)을 지운 다음에야 디스플레이를 켠다.

그림이 흐리거나 깜박이면 먼저 조정할 init 값은 클럭 `0xD5, 0x80`, 프리차지 `0xD9, 0x22`,
대비 `0x81, 0x80`, VCOM deselect `0xDB, 0x35`, 펌프 전압 `0x32`(`disp_sh1106.c`, init 표)이다. 이 값은 흔한 SH1106
라이브러리가 쓰는 값이며 측정에서 나온 값이 아니다(SSD1306 값은 Pico 드라이버의 값이다).

## 디버그 (여기서는 필요 없음)

wlink v0.1.3(`https://github.com/ch32-rs/wlink/releases/download/v0.1.3/wlink-v0.1.3-linux-x64.tar.gz`, 826,918 바이트,
sha256 `b0d55a32adf55214e7b6bf29b5eb45c61a13252622e2be3bf5dba7573e4359d8`)와 PB14/PB15에 연결한 WCH-Link가 이 칩을
디버그하는 방법이다. 여기서는 아무것도 이를 쓰지 않으며 내려받지도 않는다.

## 메모리

빌드와 `make -C c/ports/ch582 size`에서 얻은 값이다(24 MHz 빌드, 페이스 포함. `.bin` 크기는 파일 크기이고, 스택 최대치는 `STACK_INFO=1` 빌드를 `c/cross/stack-usage.py`로 읽은 것이다):

| | bytes |
|---|---:|
| 플래시 이미지(`.bin`) | 21,068 |
| text(코드, 상수, 페이스 10,124. `.highcode` 포함) | 22,456 |
| `.highcode`(벡터 테이블, `CH58x_sys.c`의 단일 섹션, `libISP583`. RAM에 있으며 리셋 시 플래시에서 복사된다) | 2,576 |
| 그중 `--gc-sections` 후 남은 `libISP583.a` | 1,062 |
| data | 20 |
| bss | 1,232 |
| 스택(`__stack_size`) | 2,048 |
| 사용 RAM(`.highcode` + data + bss + 스택) | 5,876 / 32,768 |
| `main`의 스택 최대치(`STACK_INFO=1`, `c/cross/stack-usage.py`: `main` > `profile_run` > `svf_draw_utf8` > ... > `svf__merge`) | 640 |

링커 자체의 `--print-memory-usage`는 `.stack`이 32 KB의 맨 위에 놓이므로 RAM을 100%로 보고한다. 위의 RAM
합계는 `image_sizes.py`의 합이다. `image_sizes.py`는 RAM 합계가 8,192를 넘거나 로드 가능 세그먼트가
`0x70000`을 넘어서 끝나는 이미지도 거부한다(wchisp는 세그먼트를 로드 주소에 프로그래밍하므로 `.highcode`와 `.data`는 플래시에 로드되어야 한다). `c/ports/ch582/stub/`의 no-op 스텁(SDK 없음)에 같은 소스를 링크한 결과인
text와 페이스는 "ch582 mono" 행을 본다
(`c/cross/SIZES.md`, "Port examples").

## 라이선스

`build/licences/`에는 `FACES.md`(각 페이스의 출처, 저작권, 라이선스), `LICENSE-OFL.txt`, `LICENSE-MIT.txt`, 그리고
EVT의 Apache-2.0 `LICENSE-ch583-evt.txt`와 WCH의 "Attention" 고지 `NOTICE-ch583-evt.txt`가 들어 있다. 배포하는 이미지에는 이들이 함께 있어야 한다. `link.ld`는 WCH의 것(Apache-2.0)이며 위의 기능상 변경 하나와 맨 위의 출처 주석이 더해져 있다.

## 확인한 것

**패널에서는 아직 시험하지 않았다.** 보드를 연결하지 않았으며 아무것도 플래시하거나 실행하지 않았다.

| check | status |
|---|---|
| 호스트 검사(`sh c/ports/check/host-checks.sh`): 드라이버의 명령 스트림(SH1106 및 SSD1306 빌드), 스크립트된 주변장치에 대한 I2C 계층(타임아웃, NACK, STOP), 실제 `profile_mono.c`, 부정 사례를 포함한 패널 모델 | yes |
| 스텁 링크(`c/cross/build-all.sh --ports`, `stub/`에 대한 `riscv32-esp-elf-gcc`) | yes: text 18,390, 페이스 10,124 (페이스 제외 text 8,266) |
| SDK 이미지(실제 EVT 시작 코드와 드라이버, `make -C c/ports/ch582`) | yes: text 22,456, data 20, bss 1,232; `.highcode` 2,576; `libISP583` 1,062 바이트 유지 |
| 스텁의 SDK 이름과 값을 실제 헤더와 대조(`c/ports/check/ch582_sdk_values.c`) | yes |
| 보드에서 실행 | **no** |
| 빌드만 하고 실행하지 않음: 보드의 핀 매핑(PB20/PB21 리맵, USB 핀, BOOT 버튼), 패널 변형(열 오프셋, 리맵, init 값), I2C 타이밍(24 MHz에서 400 kHz), ISP 절차(udev 규칙, BOOT, `wchisp`), LED 극성 | 나열만 함, 실행하지 않음 |
