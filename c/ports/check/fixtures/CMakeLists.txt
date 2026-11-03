# Negative-test images of pico-screen.mjs (c/ports/check/test_pico_screen.sh builds them; they are not a port).
# Each ends in the failure the runner must name: fix_bkpt (BKPT), fix_wfi (sleep with no alarm), fix_noshow (the SSD1306
# started, no show), fix_sleep (20 s of sleep: the emulated-time cap), fix_loop (a busy loop: the iteration bound). Every one defines the non-inlined svf_port_idle the runner looks up, reached from main after the
# faulting or waiting statement, so a runner that stopped at the idle symbol too early would be caught as well.
cmake_minimum_required(VERSION 3.13)
get_filename_component(SVF_PICO ${CMAKE_CURRENT_LIST_DIR}/../../pico ABSOLUTE)
get_filename_component(SVF_PORTS ${CMAKE_CURRENT_LIST_DIR}/../.. ABSOLUTE)
if(NOT PICO_SDK_PATH AND NOT "$ENV{PICO_SDK_PATH}" STREQUAL "")
  set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}" CACHE PATH "pico-sdk checkout" FORCE)
endif()
if(NOT PICO_SDK_PATH)
  message(FATAL_ERROR "PICO_SDK_PATH: pass -DPICO_SDK_PATH=... or set the environment")
endif()
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(svf_pico_fixtures C CXX ASM)
pico_sdk_init()

add_executable(fix_bkpt fix_bkpt.c)
target_link_libraries(fix_bkpt pico_stdlib)
add_executable(fix_wfi fix_wfi.c)
target_link_libraries(fix_wfi pico_stdlib)
add_executable(fix_noshow fix_noshow.c ${SVF_PICO}/disp_ssd1306.c)
target_include_directories(fix_noshow PRIVATE ${SVF_PICO})
target_link_libraries(fix_noshow pico_stdlib hardware_i2c)
add_executable(fix_sleep fix_sleep.c)
target_link_libraries(fix_sleep pico_stdlib)
add_executable(fix_loop fix_loop.c)
target_link_libraries(fix_loop pico_stdlib)
