# The RP2350 benchmark images of c/bench/run-rp2350.sh: c/bench/bench.c (-DBENCH_RP2350) and the library as pico-sdk
# 2.3.1 `pico2` executables (-DPICO_BOARD=pico2, -DPICO_PLATFORM=rp2350-riscv for Hazard3 or rp2350-arm-s for the
# Cortex-M33), the same kind of image as the c/ports/pico builds for pico2: the SDK's crt0, runtime init, linker script
# and IMAGE_DEF block, so the A2 boot ROM of rp2350js boots them. Eight executables per configure, bench-<opt>-<NAME>
# for opt Os / O2 and NAME MONO_PAGE (SVF_TARGETS 0x02), GRAY8 (0x01), RGB565 (0x08) and LINE (the default SVF_TARGETS,
# scaling in, faces 16 and 18 only). The MCU ones are built with -DBENCH_MCU -DSVF_NO_SCALE as run-m33.sh builds them.
# Required: -DPICO_SDK_PATH=<pico-sdk 2.3.1>, -DBENCH_GEN=<directory with face.c, face16.c, face18.c from mkface.py>.
# No pico_add_extra_outputs: the run passes -DPICO_NO_PICOTOOL=1 and rp2350js loads the ELF.
cmake_minimum_required(VERSION 3.13)

if(NOT BENCH_GEN)
  message(FATAL_ERROR "BENCH_GEN: pass -DBENCH_GEN=<directory with face.c, face16.c and face18.c from c/bench/mkface.py>")
endif()
get_filename_component(SVF_C ${CMAKE_CURRENT_LIST_DIR}/../.. ABSOLUTE)
if(NOT PICO_SDK_PATH)
  message(FATAL_ERROR "PICO_SDK_PATH: pass -DPICO_SDK_PATH=...")
endif()
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(svf_bench_rp2350 C CXX ASM)
pico_sdk_init()

file(GLOB SVF_SRCS ${SVF_C}/src/*.c)
set(BENCH_C ${SVF_C}/bench/bench.c)

foreach(opt Os O2)
  foreach(spec "MONO_PAGE;0x02" "GRAY8;0x01" "RGB565;0x08" "LINE;")
    list(GET spec 0 name)
    list(GET spec 1 bit)
    set(tgt bench-${opt}-${name})
    if(name STREQUAL "LINE")
      add_executable(${tgt} ${BENCH_C} ${SVF_SRCS} ${BENCH_GEN}/face16.c ${BENCH_GEN}/face18.c)
      target_compile_definitions(${tgt} PRIVATE BENCH_RP2350)
    else()
      add_executable(${tgt} ${BENCH_C} ${SVF_SRCS} ${BENCH_GEN}/face.c ${BENCH_GEN}/face16.c ${BENCH_GEN}/face18.c)
      target_compile_definitions(${tgt} PRIVATE BENCH_RP2350 BENCH_MCU SVF_NO_SCALE SVF_TARGETS=${bit}
                                 BENCH_KIND=SVF_T_${name})
    endif()
    # Whole image, SDK sources included; it follows the Release -O3 on the command line, so it wins.
    target_compile_options(${tgt} PRIVATE -${opt})
    target_include_directories(${tgt} PRIVATE ${SVF_C}/include)
    target_link_libraries(${tgt} pico_stdlib)
  endforeach()
endforeach()
# Not on the SDK's own sources: its headers need C11 static_assert.
set_source_files_properties(${BENCH_C} ${SVF_SRCS} PROPERTIES COMPILE_OPTIONS "-std=c99;-Wall;-Wextra;-Werror")
