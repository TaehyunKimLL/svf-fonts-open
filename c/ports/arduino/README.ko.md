[English](README.md) | **한국어**

# Arduino Uno 예제 (I2C로 연결한 SSD1306, 페이스는 PROGMEM)

`arduino.ino`는 128 x 64 SSD1306 OLED에 한글과 ASCII 네 줄을 그린다. 페이스(face)인 `svf/dos/NEODG16G.SVF`(16 px 1 bpp
자모, `mcu-strict` 레이아웃에서 10.1 KB)는 플래시(PROGMEM)에 그대로 둔다. 라이브러리는 다음 스위치로 빌드한다.

- `-DSVF_TARGETS=0x02`: `MONO_PAGE`만 컴파일된다.
- `-DSVF_NO_STREAM`: 스트림 리더 없음. 스케치는 페이스를 매핑해서 연다. 그러면 `svf_open_stream`, `svf_stream_tables_size`, `svf_stream_reads`는 선언되지 않으므로
  이들을 호출하는 스케치는 컴파일되지 않는다(페이스를 스트리밍하려면 이 스위치를 뺀다).
- `-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT`: 라이브러리는 `mkface.py --profile mcu-strict`가 쓰는 페이스 레이아웃만 읽는다(배포되는 페이스는 이미 그 레이아웃이며 프로필은 오프셋을
  줄인다). 이 페이스를 쓴 text는 23,676바이트이며 `c/cross/SIZES.md`의 `arduino` 행이다.
- `-DSVF_RD8(p)=pgm_read_byte(p)`: 페이스의 모든 읽기가 `pgm_read_byte`를 거친다. 이것이 없으면 PROGMEM 페이스에서 `svf_open_mapped`가 `SVF_E_MAGIC`을 반환한다
  (simavr에서 실행: 재정의가 있으면 0, 없으면 1).

텍스트 줄도 PROGMEM에 있으며 그리기 전에 RAM 버퍼로 복사된다(라이브러리는 텍스트를 일반 로드로 읽는다). MONO_PAGE 타깃은 SSD1306의 레이아웃인 128 x 64 페이지 버퍼에 그린다:
**1 KB이며, Uno의 RAM 2 KB의 절반이다.** Wire는 한 번 전송에 32 바이트를 보내므로 프레임은 16 바이트씩 나간다. 배선: SDA A4, SCL A5, 디스플레이 주소 0x3C.

아래 수치에 쓴 툴체인: avr-gcc 16.1.0과 AVR-LibC 2.3.2(`sh c/cross/install-toolchains.sh "$HOME/opt" avr`이 `~/opt` 아래에 설치하는 Zak Kemble 빌드). 여기에는 Arduino 코어가 설치되어 있지 않으므로
코어 버전은 기록하지 않았다. Uno의 쓸 수 있는 플래시 32,256바이트는 32 KB에서 Optiboot의 512바이트를 뺀 값이다. `face.c`는 스케치 폴더에 **C** 파일로 생성되며(`.gitignore`에 올라 있다)
스케치는 `arduino.ino`처럼 이를 `extern "C"`로 선언한다.

arduino-cli로 빌드한다(저장소 루트에서. 라이브러리는 Arduino 라이브러리로 넣고, 페이스 배열은 스케치 폴더의 `face.c`로
생성하며 커밋되지 않는다).

    mkdir -p ~/Arduino/libraries/svf && cp c/include/svf.h c/src/*.c c/src/*.h ~/Arduino/libraries/svf/
    python3 c/bench/mkface.py svf/dos/NEODG16G.SVF c/ports/arduino/face.c --name svf_face_data --profile mcu-strict
    F='-include avr/pgmspace.h "-DSVF_RD8(p)=pgm_read_byte(p)" -DSVF_NO_SCALE -DSVF_TARGETS=0x02 -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_JSET_V2=0'
    arduino-cli compile -b arduino:avr:uno c/ports/arduino \
        --build-property "compiler.c.extra_flags=$F" --build-property "compiler.cpp.extra_flags=$F"

`-DSVF_JSET_V2=0`(svf.h의 AVR 기본값이기도 하며 여기에 명시했다)은 JSET 버전 1 리더만 빌드한다. NEODG16G의 작은
자모 세트는 버전 1 블록이며, 버전 2 리더를 더하면 이 스케치에 필요 없는 플래시가 약 2.4 KB 늘어난다(`c/cross/SIZES.md`
"Size switches"의 P1)(그러면 버전 2 페이스는 음절 없는 일반 페이스로 열린다). `SVF_JMAP`(버전 3 리더)은 AVR에서 기본적으로 0이며 여기서도
꺼 둔다. 버전 3 페이스는 일반 페이스로 열린다(`SVF_FACE_JSET_BAD`. `-DSVF_JMAP_RECOG=1`이면 블록을 인식하여 그것이 담은 버전 1 폴백 JSET을 읽는다).

플래그는 C와 C++ 컴파일에만 준다(`compiler.c.extra_flags`, `compiler.cpp.extra_flags`). `build.extra_flags`에는 주지 않는다.
AVR 코어의 레시피는 `build.extra_flags`를 어셈블러 소스(`.S`)에도 넘기는데, 거기서 `-include avr/pgmspace.h`는 C 선언을 어셈블러에 먹여서
실패하기 때문이다. 셸의 작은따옴표는 값을 하나로 유지하고, 안쪽의 큰따옴표는 arduino-cli를 위한 것이다. arduino-cli는 레시피를 스스로(셸 없이) 인수로 나누므로,
괄호가 든 매크로가 하나의 인수 `-DSVF_RD8(p)=pgm_read_byte(p)`로 남는다.

(Arduino IDE에서는 같은 플래그를, 큰따옴표를 포함해, AVR 코어의 `platform.txt` 옆 `platform.local.txt`의 `compiler.c.extra_flags`와
`compiler.cpp.extra_flags`에 넣는다.)

확인한 것: 여기에는 Arduino 코어도 arduino-cli도 설치되어 있지 않으므로 위의 두 명령은 실제
arduino-cli 빌드로 실행한 적이 없고, 스케치는 arduino-cli로 빌드하거나 실행하지 않았다.
`c/cross/build-all.sh --ports`는 avr-gcc 16.1.0(`-mmcu=atmega328p
-Os`, 위의 플래그)으로 라이브러리와 생성된 페이스를 컴파일하고, `stub/`(`Wire`와 코어의
`main`의 no-op 대용품)에 대해 `arduino.ino`를 C++로 컴파일하여 링크한다. SVF 쪽(PROGMEM 페이스, `svf_open_mapped`, 체인, `svf_target_init`, 페이지
버퍼로의 `svf_draw_utf8`)은 ATmega328P용으로 컴파일되고 링크된다. Wire와 SSD1306 코드는 Arduino API에 맞춰 작성되었으며
검증되지 않았다. 그 링크 결과: 플래시 23,694 바이트(text 23,676 + data 18. `stub/`에 대한 크로스 빌드이며 arduino-cli 빌드가 아니다)(32 KB 중. 페이스 10,124), 스택 전 RAM 1,103 바이트(페이지
버퍼 1,024). 실제 Wire 라이브러리는 자체 버퍼(약 200 바이트)를, 코어는 수십 바이트를 더하므로 스택에는 약 700 바이트가
남는다.
이 스케치는 `-DSVF_NO_SCALE`로 빌드한다. 스케일하는 스케치(`scale_num`/`scale_den`이 1/1이 아님)는 스케일러의 스택도 예산에 넣어야 한다. `svf__scale_cell`은 610 B 프레임을 가지며 스케일된 `svf_draw_utf8`은 ATmega328P에서 스택이 약 864 B까지 오르고(스케일 없는 경로보다 +413 B), 이는 2 KB에서 페이지 버퍼와 함께 들어가지 않는다. 직접 스케일러를 쓰려면 `-DSVF_SCALE_FAST=0`(또는 `-DSVF_SMALL`)로 빌드한다. 그 최대치는 451 B이다(`c/cross/stack-usage.py`로 정적으로 측정. `c/cross/SIZES.md` "Size switches" 참조).

## Mega 2560

같은 스케치와 페이스는 ATmega2560(Arduino Mega, 플래시 256 KB)용으로도 링크된다. `c/cross/build-all.sh --ports`는 `-mmcu=atmega2560`과 Uno 플래그로(플래시 23,820 B) 빌드하고, 두 번째 행으로 모든 타깃과 리더를 켜서(`-DSVF_TARGETS=0x1FF -DSVF_JSET_V2=1 -DSVF_JMAP=1 -DSVF_JSET_BIG=1`, 플래시 40,508 B) 빌드한다. `c/cross/SIZES.md` "Port examples"에 `arduino-mega`와 `arduino-mega-rich` 행이 있다. 이것은 빌드일 뿐이며 Mega 보드나 에뮬레이터 실행은 없고 arduino-cli도 쓰지 않는다(같은 플래그로 `-b arduino:avr:mega`를 쓰는 것은 테스트하지 않았다). 페이스 데이터는 64 KB 아래의 PROGMEM에 두고 near `pgm_read_byte`로 읽는다. 64 KB 위의 페이스나 데이터는 far 읽기가 필요하며 범위 밖이다(지원하지 않고 테스트하지 않았다). Mega 이미지의 플래시 끝이 65,536 B에 닿으면 빌드는 `FLAG` 줄을 출력한다.
