# screens-lib.sh - the settings and build functions of the emulated screens, sourced by run-screens.sh and
# test_pico_screen.sh (never executed). The caller sets SCR_DIR (c/ports/check) before sourcing; nothing here reads $0.
# Sets: SCR_ROOT, SCR_P (c/ports), OPT, NODE, SDK, ARMTC, RPJS, ROM, NM, RV, XT, QEMU_RV, QEMU_XT, OUT, COMMON.
# Functions: build_pico PROFILE, build_esp BOARD [MAIN]. Uses only b_* variables of its own.
SCR_ROOT=$(cd "$SCR_DIR/../../.." && pwd)
SCR_P=$SCR_ROOT/c/ports
OPT=${OPT:-$HOME/opt}
NODE=${NODE:-$OPT/node-v24.13.0-linux-x64/bin/node}
SDK=$OPT/pico-sdk-2.3.1
ARMTC=$OPT/arm-gnu-toolchain-15.2.rel1
RPJS=$OPT/rp2040js-1.4.0
ROM=$RPJS/bootrom-b1.bin
NM=$ARMTC/bin/arm-none-eabi-nm
RV=$OPT/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf
XT=$OPT/xtensa-esp-elf-esp-16.1.0_20260609/xtensa-esp-elf/bin/xtensa-esp32s3-elf
QEMU_RV=${QEMU_RV:-$OPT/qemu-esp-9.2.2-20260417-riscv32/qemu/bin/qemu-system-riscv32}
QEMU_XT=${QEMU_XT:-$OPT/qemu-esp-9.2.2-20260417-xtensa/qemu/bin/qemu-system-xtensa}
OUT=${OUT:-$SCR_ROOT/c/build/screens}
COMMON="-std=c99 -Wall -Wextra -Werror -ffunction-sections -fdata-sections"

# build_pico PROFILE: the Pico image of PROFILE into $OUT/build-pico-PROFILE (svf_pico_PROFILE.elf); log in <dir>.log
build_pico() {
	b_d=$OUT/build-pico-$1
	mkdir -p "$b_d" || return 1
	{
		cmake -S "$SCR_P/pico" -B "$b_d" -DSVF_PROFILE="$1" -DPICO_SDK_PATH="$SDK" -DPICO_TOOLCHAIN_PATH="$ARMTC" \
			-DPICO_NO_PICOTOOL=1 -DCMAKE_BUILD_TYPE=Release &&
			cmake --build "$b_d"
	} >"$b_d.log" 2>&1 || { tail -n 20 "$b_d.log" >&2; echo "build_pico $1: FAIL (log $b_d.log)" >&2; return 1; }
}

# build_esp BOARD [MAIN]: the bare colour image of BOARD (esp32c3 or esp32s3) into $OUT/esp/screen-BOARD.elf; with MAIN
# only that file and the library are linked, into $OUT/esp/<MAIN's name>-BOARD.elf (the negative fixture)
build_esp() {
	b_d=$OUT/esp
	mkdir -p "$b_d/faces" || return 1
	for b_n in paplg16 paplg18; do
		python3 -I "$SCR_ROOT/c/bench/mkface.py" "$SCR_ROOT/svf/dos/$(echo $b_n | tr a-z A-Z).SVF" "$b_d/faces/$b_n.c" --name $b_n --profile mcu-strict ||
			return 1
	done
	if [ -n "${2:-}" ]; then
		b_elf=$b_d/$(basename "$2" .c)-$1.elf
		set -- "$1" "$2"
	else
		b_elf=$b_d/screen-$1.elf
		set -- "$1" "$SCR_P/esp32/main/main_qemu.c" "$SCR_P/esp32/main/profile_colour.c" "$SCR_P/esp32/main/disp_esp_rgb.c" \
			"$b_d/faces/paplg16.c" "$b_d/faces/paplg18.c"
	fi
	b_board=$1
	b_log=$b_d/build-$(basename "$b_elf" .elf | sed 's/^screen-//').log
	shift
	case $b_board in
	esp32c3)
		# shellcheck disable=SC2086
		"$RV-gcc" $COMMON -march=rv32imc_zicsr_zifencei -mabi=ilp32 -Os -DSVF_NO_SCALE -DSVF_TARGETS=0x08 \
			-I"$SCR_P/esp32/main" -I"$SCR_P" -I"$SCR_ROOT/c/include" "$@" "$SCR_ROOT"/c/src/*.c \
			-specs=esp32c3.qemu.specs -Wl,--gc-sections -o "$b_elf" ;;
	esp32s3)
		# shellcheck disable=SC2086
		"$XT-gcc" $COMMON -mlongcalls -Os -DSVF_ESP32S3=1 -DSVF_NO_SCALE -DSVF_TARGETS=0x08 \
			-I"$SCR_P/esp32/main" -I"$SCR_P" -I"$SCR_ROOT/c/include" "$@" "$SCR_ROOT"/c/src/*.c \
			-specs=sys.qemu.specs -specs=sim.elf.specs -Wl,--defsym=entire_dram_seg=1 -Wl,--gc-sections -o "$b_elf" ;;
	*) echo "build_esp: unknown board '$b_board'" >&2; return 1 ;;
	esac >"$b_log" 2>&1 || { tail -n 20 "$b_log" >&2; echo "build_esp $b_board: FAIL" >&2; return 1; }
}
