# ESP-IDF project: one image per profile, chosen with -DSVF_PROFILE=colour|grey|mono (default colour); the colour profile's
# display with -DSVF_DISPLAY=ili9341|esp_rgb (default ili9341). c/ports/esp32/README.md has the build lines.
# c/ports/profiles.txt is the table behind each profile. Everything is validated before the IDF is included, so a typo
# is reported at once (and without an IDF installed).
cmake_minimum_required(VERSION 3.16)

get_filename_component(SVF_C ${CMAKE_CURRENT_LIST_DIR}/../.. ABSOLUTE)

set(SVF_PROFILE "colour" CACHE STRING "Profile to build: colour, grey or mono")
set(SVF_DISPLAY "ili9341" CACHE STRING "Colour display: ili9341 (SPI) or esp_rgb (QEMU's RGB panel)")
set(SVF_GREY_KIND "GRAY8" CACHE STRING "Kind the grey profile draws (only GRAY8 until card t_8e7da3c1)")
set(SVF_PORT esp32)
include(${SVF_C}/ports/profiles.cmake) # validates SVF_PROFILE (and SVF_GREY_KIND for grey) before anything else

if(NOT SVF_DISPLAY MATCHES "^(ili9341|esp_rgb)$")
  message(FATAL_ERROR "SVF_DISPLAY ${SVF_DISPLAY}: ili9341 or esp_rgb")
endif()
if(SVF_DISPLAY STREQUAL "esp_rgb" AND NOT SVF_PROFILE STREQUAL "colour")
  message(FATAL_ERROR "SVF_DISPLAY esp_rgb needs SVF_PROFILE colour")
endif()

# A build directory keeps its cache: another profile (or, for grey, another kind) in the same -B would silently rebuild
# the old one. The key is stored once the IDF project is set up (below), so a failed first configure locks nothing.
if(SVF_PROFILE STREQUAL "grey")
  set(_svf_configured "grey/${SVF_GREY_KIND}")
else()
  set(_svf_configured "${SVF_PROFILE}")
endif()
if(SVF_PROFILE_CONFIGURED AND NOT SVF_PROFILE_CONFIGURED STREQUAL _svf_configured)
  message(FATAL_ERROR "this build directory was configured for ${SVF_PROFILE_CONFIGURED}: use a fresh -B directory")
endif()

# The ESP-IDF: -DIDF_PATH=<dir> (as PICO_SDK_PATH is given) or the exported environment. The IDF's own scripts read the
# environment variable, so a -D value is passed on through it.
if(NOT IDF_PATH)
  set(IDF_PATH "$ENV{IDF_PATH}")
endif()
if(NOT IDF_PATH OR NOT EXISTS "${IDF_PATH}/tools/cmake/project.cmake")
  message(FATAL_ERROR "IDF_PATH: export the ESP-IDF environment (. $IDF_PATH/export.sh) or pass -DIDF_PATH=<esp-idf directory>")
endif()
set(ENV{IDF_PATH} "${IDF_PATH}")
include(${IDF_PATH}/tools/cmake/project.cmake)
project(svf_esp32_${SVF_PROFILE})
set(SVF_PROFILE_CONFIGURED "${_svf_configured}" CACHE INTERNAL "profile (and for grey the kind) this build directory is for")
