# c/Makefile - the portable SVF renderer: library, host tools and the gate.
#
#   make -C c [O=dir] lib | lib-noscale | svfdump | svfdump-asan | svfdump-page | svfdump-vesa | svfdump-gray | svfdump-bytes | svfdump-rd8
#                     | svfdump-noscale | test-open | test-open-size16 | test-layouts | test-args | test-args-page | test-args-vesa | test-args-gray | test-args-jmap | test-blend16 | test-kernels | test-vbe | vesa-lines-dump | check
#
# lib-noscale (objects in $(O)/noscale) and svfdump-noscale build the library with -DSVF_NO_SCALE: no scaling code.
#
# svfdump-bytes is the sanitizer build with -DSVF_WORD_STORE=0 (the byte loops), the oracle the word stores are
# compared with (tools/test_c_renderer.py).
#
# svfdump-rd8 builds the library with SVF_RD8 overridden by a host stand-in for a separate address space
# (tests/test_rd8.h), so mapped face bytes are read only through SVF_RD8 and streamed bytes never are.
#
# test-open-size16: test-open with the library built -DSVF__SIZE_MAX=0xFFFF, a 16-bit size_t (AVR): a streamed open whose
# tables pass 65535 bytes is refused SVF_E_NOMEM. test-layouts: tests/test_layouts.c built four ways, all sanitizer
# builds: test-layouts (every layout), test-layouts-strict (-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT), test-layouts-tight
# (SVF_LAYOUT_TIGHT) and test-layouts-pair (both). They take the six layout files tools/test_c_renderer.py
# TestLayoutsBuild writes ("test-layouts DIR BUILD"); `make check` does not run them (it has no input files), the
# Python runs of check.sh do.
#
# test-args (sanitizer build): every public entry point with each NULL pointer and bad argument (tests/test_args.c).
#
# test-blend16: the level, blend and palette formulas under a 16-bit int model (tests/test_blend16.c, no library).
#
# test-pad (sanitizer builds, -DSVF_TEST_HOOKS, with SVF_WORD_STORE=1 and =0): the blitters on cells whose padding bits are
# inked (tests/test_pad.c); both builds print the same line.
#
# test-kernels (sanitizer builds, -DSVF_TEST_HOOKS; defaults, -DSVF_WORD_STORE=0 -DSVF__MERGE_UNALIGNED=0 (the strict-align
# merge words), and -DSVF_MERGE_WORDS=0 -DSVF_GRAY8_LUT1=0, -DSVF_SCALE_FAST=0, -DSVF_SMALL):
# the exhaustive net for svf__merge, the 1 bpp GRAY8 blit and svf__scale_cell against reference loops kept in the test
# (tests/test_kernels.c); the five builds print the same line.
#
# test-vbe: ports/dos/vbe_select.c on hostile VBE blocks and mode lists, sanitizer build (tests/test_vbe.c, no library).
#
# vesa-lines-dump: ports/dos/vesa_lines.c plus a main (tests/vesa_lines_dump.c): the parsed vesa-lines.txt and its palette
# as text (--print-table FILE [--dac N]), sanitizer build; tools/test_c_renderer.py TestVesaLines compares it with
# tools/vesa_lines.py.
#
# check: test-blend16, test-vbe, test-pad, test-kernels, no allocator symbol in the objects of both builds (default and SVF_NO_SCALE), then
# tools/test_c_renderer.py against the sanitizer build (check.sh).
#
# The three fuzz builds define SVF_FUZZ_POISON: svf_draw_utf8 then poisons (ASan manual poisoning) the idle second cell of its scratch while
# svf__scale_cell runs, so a scaler that reads beyond its source cell is a use-after-poison report instead of a read of its own scratch.
# fuzz: $(O)/fuzz-open, a libFuzzer build (tests/fuzz_open.c, $(CLANG) -fsanitize=fuzzer,address,undefined) of the record parser:
# open mapped and streamed (no cache, 4 KB cache of 64-byte blocks), then every glyph. Not part of check.
#
# fuzz-strict: $(O)/fuzz-open-strict, the same harness built -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_NO_STREAM (mapped only, one
# layout). fuzz-rd: $(O)/fuzz-open-rd, the harness with SVF_RD8 overridden (tests/test_rd8.h: the mapped copy is an alias of 0x5A
# bytes, read only through svf_test_rd8; a streamed face's bytes are never read that way). fuzz-smoke: 60 s of each of the
# six (fuzz-open-nolist: -DSVF_JMAP=1 -DSVF_JMAP_LIST=0; fuzz-open-mcu: the MCU build, -DSVF_JMAP=0 -DSVF_JMAP_RECOG=0 -DSVF_JSET_BIG=0, on corpus-strict; fuzz-open-nojmap: -DSVF_JMAP=0, the recognition path; fuzz-open, -rd and -nojmap are built -DSVF_JSET_BIG=1; fuzz-open-strict
# -DSVF_JSET_BIG=0, the MCU default: the narrow reader on the same seeds, its BIG faces refused) on the seed corpora (4 minutes; not part of check). fuzz-corpus: the seeds of both under $(O)/fuzz/corpus and corpus-strict (tests/fuzz_corpus.sh).
#
# O is the build directory (default c/build). CC, CFLAGS and AR may be overridden (cross builds).

O ?= build
CC ?= cc
AR ?= ar
CFLAGS ?= -O2
CLANG ?= $(firstword $(wildcard $(HOME)/opt/llvm-*/bin/clang) clang)
WARN = -std=c99 -Wall -Wextra -Werror
ASAN = -O1 -g -fsanitize=address,undefined,pointer-overflow -fno-sanitize-recover=all -fno-omit-frame-pointer

SRCS = $(wildcard src/*.c)
OBJS = $(SRCS:src/%.c=$(O)/obj/%.o)
NOSCALE_OBJS = $(SRCS:src/%.c=$(O)/noscale/%.o)
HDRS = include/svf.h src/svf_internal.h

.PHONY: all lib lib-noscale svfdump svfdump-asan svfdump-page svfdump-vesa svfdump-gray svfdump-bytes svfdump-rd8 svfdump-noscale
.PHONY: test-open test-open-size16 test-layouts test-args fuzz
.PHONY: fuzz-rd fuzz-nojmap fuzz-nolist fuzz-mcu fuzz-smoke test-args-page test-args-vesa test-args-gray test-args-jmap test-blend16 test-vbe vesa-lines-dump test-pad test-kernels check clean fuzz-strict fuzz-corpus
all: lib svfdump

lib: $(O)/libsvf.a
svfdump: $(O)/svfdump
svfdump-asan: $(O)/svfdump-asan
svfdump-page: $(O)/svfdump-page
svfdump-vesa: $(O)/svfdump-vesa
svfdump-gray: $(O)/svfdump-gray
svfdump-bytes: $(O)/svfdump-bytes
svfdump-rd8: $(O)/svfdump-rd8
lib-noscale: $(O)/noscale/libsvf.a
svfdump-noscale: $(O)/svfdump-noscale
test-open: $(O)/test-open
test-open-size16: $(O)/test-open-size16
test-layouts: $(O)/test-layouts $(O)/test-layouts-strict $(O)/test-layouts-tight $(O)/test-layouts-pair
test-args: $(O)/test-args
test-args-page: $(O)/test-args-page
test-args-vesa: $(O)/test-args-vesa
test-args-gray: $(O)/test-args-gray
test-args-jmap: $(O)/test-args-jmap
test-blend16: $(O)/test-blend16
test-vbe: $(O)/test-vbe
vesa-lines-dump: $(O)/vesa-lines-dump
test-pad: $(O)/test-pad $(O)/test-pad-bytes
test-kernels: $(O)/test-kernels $(O)/test-kernels-bytes $(O)/test-kernels-plain $(O)/test-kernels-slowscale $(O)/test-kernels-small

$(O)/obj/%.o: src/%.c $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(CFLAGS) -Iinclude -c $< -o $@

$(O)/libsvf.a: $(OBJS)
	@rm -f $@
	$(AR) rcs $@ $(OBJS)

$(O)/noscale/%.o: src/%.c $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(CFLAGS) -DSVF_NO_SCALE -Iinclude -c $< -o $@

$(O)/noscale/libsvf.a: $(NOSCALE_OBJS)
	@rm -f $@
	$(AR) rcs $@ $(NOSCALE_OBJS)

$(O)/svfdump-noscale: tests/svfdump.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_NO_SCALE -Iinclude tests/svfdump.c $(SRCS) -o $@

$(O)/svfdump: tests/svfdump.c $(O)/libsvf.a $(HDRS)
	$(CC) $(WARN) $(CFLAGS) -Iinclude tests/svfdump.c $(O)/libsvf.a -o $@

$(O)/svfdump-asan: tests/svfdump.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -Iinclude tests/svfdump.c $(SRCS) -o $@

$(O)/svfdump-page: tests/svfdump.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TARGETS=0x02 -Iinclude tests/svfdump.c $(SRCS) -o $@

$(O)/svfdump-vesa: tests/svfdump.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TARGETS=0x1E8 -Iinclude tests/svfdump.c $(SRCS) -o $@

$(O)/svfdump-gray: tests/svfdump.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TARGETS=0x200 -Iinclude tests/svfdump.c $(SRCS) -o $@

$(O)/svfdump-bytes: tests/svfdump.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_WORD_STORE=0 -Iinclude tests/svfdump.c $(SRCS) -o $@

$(O)/svfdump-rd8: tests/svfdump.c tests/test_rd8.c tests/test_rd8.h $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_RD8 -include tests/test_rd8.h '-DSVF_RD8(p)=svf_test_rd8(p)' -Iinclude \
		tests/svfdump.c tests/test_rd8.c $(SRCS) -o $@

$(O)/test-open: tests/test_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -Iinclude tests/test_open.c $(SRCS) -o $@

$(O)/test-open-size16: tests/test_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF__SIZE_MAX=0xFFFF -Iinclude tests/test_open.c $(SRCS) -o $@

$(O)/test-layouts: tests/test_layouts.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -Iinclude tests/test_layouts.c $(SRCS) -o $@

$(O)/test-layouts-strict: tests/test_layouts.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -Iinclude tests/test_layouts.c $(SRCS) -o $@

$(O)/test-layouts-tight: tests/test_layouts.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_LAYOUTS=SVF_LAYOUT_TIGHT -Iinclude tests/test_layouts.c $(SRCS) -o $@

$(O)/test-layouts-pair: tests/test_layouts.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) '-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT,SVF_LAYOUT_TIGHT' -Iinclude tests/test_layouts.c $(SRCS) -o $@

$(O)/test-args: tests/test_args.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -Iinclude tests/test_args.c $(SRCS) -o $@

$(O)/test-args-page: tests/test_args.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TARGETS=0x02 -Iinclude tests/test_args.c $(SRCS) -o $@

$(O)/test-args-vesa: tests/test_args.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TARGETS=0x1E8 -Iinclude tests/test_args.c $(SRCS) -o $@

$(O)/test-args-gray: tests/test_args.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TARGETS=0x200 -Iinclude tests/test_args.c $(SRCS) -o $@

# the same entry points on a face with a JMAP (version 3) block: SVF_JMAP=1 (tests/test_args.c needs a jamo face)
$(O)/test-args-jmap: tests/test_args.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_JMAP=1 -Iinclude tests/test_args.c $(SRCS) -o $@

$(O)/test-blend16: tests/test_blend16.c
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) tests/test_blend16.c -o $@

$(O)/test-vbe: tests/test_vbe.c ports/dos/vbe_select.c ports/dos/vbe_select.h
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -Iports/dos tests/test_vbe.c ports/dos/vbe_select.c -o $@

$(O)/vesa-lines-dump: tests/vesa_lines_dump.c ports/dos/vesa_lines.c ports/dos/vesa_lines.h ports/dos/vbe_select.c ports/dos/vbe_select.h $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -Iinclude -Iports/dos tests/vesa_lines_dump.c ports/dos/vesa_lines.c ports/dos/vbe_select.c $(SRCS) -o $@

$(O)/test-pad: tests/test_pad.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -DSVF_WORD_STORE=1 -Iinclude tests/test_pad.c $(SRCS) -o $@

$(O)/test-pad-bytes: tests/test_pad.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -DSVF_WORD_STORE=0 -Iinclude tests/test_pad.c $(SRCS) -o $@

$(O)/test-kernels: tests/test_kernels.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -Iinclude -Isrc tests/test_kernels.c $(SRCS) -o $@

$(O)/test-kernels-bytes: tests/test_kernels.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -DSVF_WORD_STORE=0 -DSVF__MERGE_UNALIGNED=0 -Iinclude -Isrc tests/test_kernels.c $(SRCS) -o $@

$(O)/test-kernels-plain: tests/test_kernels.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -DSVF_MERGE_WORDS=0 -DSVF_GRAY8_LUT1=0 -Iinclude -Isrc tests/test_kernels.c $(SRCS) -o $@

$(O)/test-kernels-slowscale: tests/test_kernels.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -DSVF_SCALE_FAST=0 -Iinclude -Isrc tests/test_kernels.c $(SRCS) -o $@

$(O)/test-kernels-small: tests/test_kernels.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CC) $(WARN) $(ASAN) -DSVF_TEST_HOOKS -DSVF_SMALL -Iinclude -Isrc tests/test_kernels.c $(SRCS) -o $@

check: lib lib-noscale test-blend16 test-vbe vesa-lines-dump test-pad test-kernels
	$(O)/test-blend16
	@$(O)/test-vbe >$(O)/test-vbe.out || { grep -v ': ok$$' $(O)/test-vbe.out; exit 1; }; tail -n 1 $(O)/test-vbe.out
	@a=`$(O)/test-pad` && b=`$(O)/test-pad-bytes` && echo "$$a" && echo "$$b" && [ "$$a" = "$$b" ]
	@a=`$(O)/test-kernels` && b=`$(O)/test-kernels-bytes` && c=`$(O)/test-kernels-plain` && d=`$(O)/test-kernels-slowscale` && e=`$(O)/test-kernels-small` && echo "$$a" && echo "$$b" && echo "$$c" && echo "$$d" && echo "$$e" && [ "$$a" = "$$b" ] && [ "$$a" = "$$c" ] && [ "$$a" = "$$d" ] && [ "$$a" = "$$e" ]
	SVF_HOTPATH_REQUIRE=1 sh check.sh --asan $(OBJS) $(NOSCALE_OBJS)

fuzz: $(O)/fuzz-open
fuzz-strict: $(O)/fuzz-open-strict
fuzz-rd: $(O)/fuzz-open-rd
fuzz-nojmap: $(O)/fuzz-open-nojmap
fuzz-nolist: $(O)/fuzz-open-nolist
fuzz-mcu: $(O)/fuzz-open-mcu

FUZZ_SMOKE_S ?= 60
fuzz-smoke: fuzz fuzz-strict fuzz-rd fuzz-nojmap fuzz-nolist fuzz-mcu fuzz-corpus
	@for t in "fuzz-open corpus" "fuzz-open-strict corpus-strict" "fuzz-open-rd corpus" "fuzz-open-nojmap corpus" "fuzz-open-nolist corpus" "fuzz-open-mcu corpus-strict"; do set -- $$t; \
		mkdir -p $(O)/fuzz/smoke-$$1; cp -n $(O)/fuzz/$$2/* $(O)/fuzz/smoke-$$1/ 2>/dev/null; \
		echo "$$1: $(FUZZ_SMOKE_S) s"; \
		$(O)/$$1 -max_total_time=$(FUZZ_SMOKE_S) -max_len=2000000 -artifact_prefix=$(O)/fuzz/smoke-$$1- $(O)/fuzz/smoke-$$1 >$(O)/fuzz/smoke-$$1.log 2>&1 \
			|| { tail -n 20 $(O)/fuzz/smoke-$$1.log; exit 1; }; \
		tail -n 1 $(O)/fuzz/smoke-$$1.log; done

fuzz-corpus:
	sh tests/fuzz_corpus.sh $(O)/fuzz

FUZZ = -O1 -g -fsanitize=fuzzer,address,undefined,pointer-overflow -fno-sanitize-recover=all -fno-omit-frame-pointer

$(O)/fuzz-open: tests/fuzz_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CLANG) $(WARN) $(FUZZ) -DSVF_JMAP=1 -DSVF_JSET_BIG=1 -DSVF_FUZZ_POISON -Iinclude tests/fuzz_open.c $(SRCS) -o $@

$(O)/fuzz-open-strict: tests/fuzz_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CLANG) $(WARN) $(FUZZ) -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_NO_STREAM -DSVF_JMAP=1 -DSVF_JSET_BIG=0 -DSVF_FUZZ_POISON -Iinclude tests/fuzz_open.c $(SRCS) -o $@

$(O)/fuzz-open-rd: tests/fuzz_open.c tests/test_rd8.c tests/test_rd8.h $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CLANG) $(WARN) $(FUZZ) -DSVF_JMAP=1 -DSVF_JSET_BIG=1 -DSVF_FUZZ_POISON -DSVF_TEST_RD8 -include tests/test_rd8.h '-DSVF_RD8(p)=svf_test_rd8(p)' -Iinclude -Itests tests/fuzz_open.c tests/test_rd8.c $(SRCS) -o $@

# fuzz-nojmap: $(O)/fuzz-open-nojmap, the fuzz-open harness with -DSVF_JMAP=0: the recognition path (PR-6) of a build without the
# JMAP reader, on the same corpus (JMAP faces open as plain faces or through their fallback).
$(O)/fuzz-open-nojmap: tests/fuzz_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CLANG) $(WARN) $(FUZZ) -DSVF_JMAP=0 -DSVF_JSET_BIG=1 -DSVF_FUZZ_POISON -Iinclude tests/fuzz_open.c $(SRCS) -o $@

# fuzz-nolist: $(O)/fuzz-open-nolist, the fuzz-open harness with -DSVF_JMAP=1 -DSVF_JMAP_LIST=0: a JMAP build without the LIST form (a LIST
# block is JMAP_UNREAD with its fallback read in its place, or plain), on the same corpus.
$(O)/fuzz-open-nolist: tests/fuzz_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CLANG) $(WARN) $(FUZZ) -DSVF_JMAP=1 -DSVF_JMAP_LIST=0 -DSVF_JSET_BIG=1 -DSVF_FUZZ_POISON -Iinclude tests/fuzz_open.c $(SRCS) -o $@

# fuzz-mcu: $(O)/fuzz-open-mcu, what the MCU images compile: no JMAP reader, no recognition, the narrow JSET row, the strict layout, mapped only.
$(O)/fuzz-open-mcu: tests/fuzz_open.c $(SRCS) $(HDRS)
	@mkdir -p $(@D)
	$(CLANG) $(WARN) $(FUZZ) -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT -DSVF_NO_STREAM -DSVF_JMAP=0 -DSVF_JMAP_RECOG=0 -DSVF_JSET_BIG=0 -DSVF_FUZZ_POISON -Iinclude tests/fuzz_open.c $(SRCS) -o $@

clean:
	rm -rf $(O)
