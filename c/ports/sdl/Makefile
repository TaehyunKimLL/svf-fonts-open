# SDL2 / SDL3 example of the C renderer: svfsdl2 and svfsdl3 from one source.
#   make [SDL=2|3] [O=dir] [ASAN=1]      SDL empty builds both; outputs $(O)/svfsdl2, $(O)/svfsdl3
#   make check                           check.sh (headless matrix, needs both SDLs)
#   make shots                           shots.sh (screenshots)
#   make clean
# SDL3 is found with pkg-config in $(SDL3_PREFIX)/lib/pkgconfig (default $(HOME)/opt/sdl3, the user's fork build) and
# linked with an rpath, so it runs without LD_LIBRARY_PATH.
SDL ?=
SDL3_PREFIX ?= $(HOME)/opt/sdl3
O ?= ../../build/ports/sdl
ASAN ?=
# An ASAN=1 build goes to $(O)/asan, so a sanitizer binary and a plain one never share a path (check.sh passes O=$OUT).
ifneq ($(ASAN),)
override O := $(O)/asan
endif
CC ?= cc

CFLAGS_ALL = -std=c99 -Wall -Wextra -Werror -O2 -I../../include -I../dos
ifneq ($(ASAN),)
CFLAGS_ALL += -g -fsanitize=address,undefined -fno-omit-frame-pointer
endif
SRCS = svfsdl.c ../dos/vesa_lines.c ../dos/vbe_select.c $(wildcard ../../src/*.c)
HDRS = sdl_compat.h ../dos/vesa_lines.h ../dos/vbe_select.h $(wildcard ../../include/*.h ../../src/*.h)

PCPATH2 = $(PKG_CONFIG_PATH)
PCPATH3 = $(SDL3_PREFIX)/lib/pkgconfig$(if $(PKG_CONFIG_PATH),:$(PKG_CONFIG_PATH))

TARGETS = $(if $(SDL),$(O)/svfsdl$(SDL),$(O)/svfsdl2 $(O)/svfsdl3)

all: $(TARGETS)

$(O)/svfsdl2: $(SRCS) $(HDRS)
	@mkdir -p $(O)
	PKG_CONFIG_PATH='$(PCPATH2)' ; export PKG_CONFIG_PATH ; \
	$(CC) $(CFLAGS_ALL) -DSVFSDL=2 $$(pkg-config --cflags sdl2) -o $@ $(SRCS) $$(pkg-config --libs sdl2)

$(O)/svfsdl3: $(SRCS) $(HDRS)
	@mkdir -p $(O)
	PKG_CONFIG_PATH='$(PCPATH3)' ; export PKG_CONFIG_PATH ; \
	$(CC) $(CFLAGS_ALL) -DSVFSDL=3 $$(pkg-config --cflags sdl3) -o $@ $(SRCS) $$(pkg-config --libs sdl3) \
		-Wl,-rpath,$$(pkg-config --variable=libdir sdl3)

check:
	sh check.sh

shots:
	sh shots.sh

clean:
	rm -rf $(O)

.PHONY: all check shots clean
