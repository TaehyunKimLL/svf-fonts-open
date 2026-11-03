# Makefile - the CH582 (YD-CH582M, SH1106 OLED) image: a stock GCC and the WCH EVT sources, no vendor IDE.
#   make [all]  build $(BUILD)/svf_ch582_mono.{elf,bin,hex,map}, the face, the licences, then print the sizes
#   make size   the sizes of an existing image (size -A figures and the RAM total)
#   make flash  wchisp flash (needs the board in its boot loader; this Makefile's tests never run it)
#   make clean  remove $(BUILD)
# Toolchain and SDK are the ones c/cross/install-toolchains.sh installs under $(OPT); the esp toolchain is not on PATH
# (CROSS=riscv-none-elf- for the xPack one). STACK_INFO=1 adds -fstack-usage -fcallgraph-info=su (c/cross/stack-usage.py
# reads obj/*.ci); EXTRA_CFLAGS goes to the port files only (the driver variants, e.g. -DSH1106_COL_OFFSET=0). The size
# line is the last line of `make --no-print-directory -C DIR` (build-all.sh parses it).
MAKEFLAGS += --no-print-directory

OPT ?= $(HOME)/opt
CROSS ?= $(OPT)/riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-
CH583_SDK ?= $(OPT)/ch583-evt
WCHISP ?= $(OPT)/wchisp-0.3.0/wchisp
BUILD ?= build
STACK_INFO ?=
EXTRA_CFLAGS ?=

SDKSRC = $(CH583_SDK)/EVT/EXAM/SRC
ifneq ($(MAKECMDGOALS),clean)
ifeq ($(wildcard $(SDKSRC)/Ld/Link.ld),)
$(error CH583 SDK not found at $(CH583_SDK): run c/cross/install-toolchains.sh ch583)
endif
ifeq ($(wildcard $(CH583_SDK)/LICENSE),)
$(error CH583 SDK at $(CH583_SDK) has no LICENSE: run c/cross/install-toolchains.sh ch583)
endif
endif

NAME = svf_ch582_mono
ELF = $(BUILD)/$(NAME).elf
BIN = $(BUILD)/$(NAME).bin
HEX = $(BUILD)/$(NAME).hex
MAP = $(BUILD)/$(NAME).map
OBJ = $(BUILD)/obj
FACE_C = $(BUILD)/faces/svf_face_data.c
LICENCES = $(BUILD)/licences
NOTICE_SRC = StdPeriphDriver/CH58x_i2c.c

CC = $(CROSS)gcc
ARCH = -march=rv32imac_zicsr_zifencei -mabi=ilp32 -mcmodel=medany -msmall-data-limit=8 -mstrict-align -Os \
	-ffunction-sections -fdata-sections -g
# -DSVF_JSET_V2=0: the port draws the version 1 face NEODG16G only, so it pins the version 1 reader (as the Arduino port does);
# SVFDEFS reaches the library objects too (LIB_FLAGS). Drop it to open version 2 faces (about +1.5 KB).
SVFDEFS = -DSVF_NO_SCALE -DSVF_NO_STREAM -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_TARGETS=0x02 -DSVF_JSET_V2=0
# FREQ_SYS must match main.c's SetSysClock(CLK_SOURCE_PLL_24MHz): 24 MHz keeps the I2C module clock in 2..36 MHz and,
# with I2C_DutyCycle_2, gives the SDK's divider an exact 400 kHz SCL (32 MHz gives about 427 kHz with duty 16/9 and
# about 410 kHz with duty 2, over the SH1106's limit)
SDKDEFS = -DINT_SOFT -DFREQ_SYS=24000000
SDKINC = -I$(SDKSRC)/StdPeriphDriver/inc -I$(SDKSRC)/RVMSIS
SU = $(if $(STACK_INFO),-fstack-usage -fcallgraph-info=su)
PORT_FLAGS = $(ARCH) $(SU) -std=gnu99 -Wall -Wextra -Werror $(SVFDEFS) $(SDKDEFS) -I. -I.. -I../../include $(SDKINC) \
	$(EXTRA_CFLAGS)
LIB_FLAGS = $(ARCH) $(SU) -std=c99 -Wall -Wextra -Werror $(SVFDEFS) -I../../include
SDK_FLAGS = $(ARCH) $(SU) $(SDKDEFS) -w $(SDKINC)
LDFLAGS = $(ARCH) -T link.ld -nostartfiles --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections -Wl,-Map=$(MAP) \
	-Wl,--print-memory-usage

PORT_SRC = main profile_mono disp_sh1106 i2c
LIB_SRC = $(basename $(notdir $(wildcard ../../src/*.c)))
SDK_SRC = CH58x_gpio CH58x_i2c CH58x_sys
# every object (and the link) depends on the flag string: changing EXTRA_CFLAGS, STACK_INFO, FREQ_SYS or the compiler
# against an existing BUILD rebuilds (the stamp is rewritten only when the string changes)
STAMP = $(OBJ)/flags.stamp
FLAGS_ALL = $(CC)|$(PORT_FLAGS)|$(LIB_FLAGS)|$(SDK_FLAGS)|$(LDFLAGS)
OBJS = $(addprefix $(OBJ)/,$(addsuffix .o,$(PORT_SRC) $(LIB_SRC) $(SDK_SRC) startup_CH583 svf_face_data))

all: $(ELF) $(BIN) $(HEX) licences
	@$(MAKE) size

$(STAMP): FORCE | $(OBJ)
	@$(if $(subst X$(FLAGS_ALL),,X$(file <$@)),$(file >$@,$(FLAGS_ALL)))

$(OBJ)/%.o: %.c $(STAMP) | $(OBJ)
	$(CC) $(PORT_FLAGS) -MMD -MP -c $< -o $@
$(OBJ)/svf_%.o: ../../src/svf_%.c $(STAMP) | $(OBJ)
	$(CC) $(LIB_FLAGS) -MMD -MP -c $< -o $@
$(OBJ)/svf_face_data.o: $(FACE_C) $(STAMP) | $(OBJ)
	$(CC) $(LIB_FLAGS) -MMD -MP -c $< -o $@
$(OBJ)/CH58x_%.o: $(SDKSRC)/StdPeriphDriver/CH58x_%.c $(STAMP) | $(OBJ)
	$(CC) $(SDK_FLAGS) -MMD -MP -c $< -o $@
$(OBJ)/startup_CH583.o: $(SDKSRC)/Startup/startup_CH583.S $(STAMP) | $(OBJ)
	$(CC) $(SDK_FLAGS) -MMD -MP -c $< -o $@

$(FACE_C): ../../bench/mkface.py ../../../svf/dos/NEODG16G.SVF
	mkdir -p $(dir $@)
	python3 -I ../../bench/mkface.py ../../../svf/dos/NEODG16G.SVF $@ --name svf_face_data --profile mcu-strict

$(ELF): $(OBJS) link.ld $(STAMP)
	$(CC) $(LDFLAGS) $(OBJS) -L$(SDKSRC)/StdPeriphDriver -lISP583 -o $@

$(BIN): $(ELF)
	$(CROSS)objcopy -O binary $< $@
$(HEX): $(ELF)
	$(CROSS)objcopy -O ihex $< $@

$(OBJ):
	mkdir -p $@

licences: | $(ELF)
	mkdir -p $(LICENCES)
	cp ../FACES.md ../../../svf/dos/OFL.TXT ../../../svf/dos/NEODGM.TXT $(LICENCES)/
	cp $(CH583_SDK)/LICENSE $(LICENCES)/LICENSE-ch583-evt.txt
	{ echo "WCH's notice from the header of $(NOTICE_SRC) (EVT/EXAM/SRC/ of github.com/openwch/ch583), verbatim:"; \
	  grep -a -A1 'Attention:' $(SDKSRC)/$(NOTICE_SRC); } >$(LICENCES)/NOTICE-ch583-evt.txt

size:
	$(CROSS)size $(ELF)
	python3 -I image_sizes.py --size $(CROSS)size --readelf $(CROSS)readelf $(ELF) $(MAP)

# the image is rebuilt (and its placement checked by image_sizes.py) before wchisp programs it
flash: $(ELF)
	python3 -I image_sizes.py --size $(CROSS)size --readelf $(CROSS)readelf $(ELF) $(MAP) >/dev/null
	$(WCHISP) flash $(ELF)

clean:
	rm -rf $(BUILD)

.PHONY: all licences size flash clean FORCE
FORCE:

-include $(OBJS:.o=.d)
