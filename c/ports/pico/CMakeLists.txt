# Raspberry Pi Pico (pico-sdk): one image per profile, chosen with -DSVF_PROFILE=colour|grey|mono (default mono).
# c/ports/pico/README.md has the build lines. c/ports/profiles.txt is the table behind each profile.
cmake_minimum_required(VERSION 3.13)

get_filename_component(SVF_C ${CMAKE_CURRENT_LIST_DIR}/../.. ABSOLUTE)
get_filename_component(SVF_ROOT ${SVF_C}/.. ABSOLUTE)

set(SVF_PROFILE "mono" CACHE STRING "Profile to build: colour, grey or mono")
set(SVF_GREY_KIND "GRAY8" CACHE STRING "Kind the grey profile draws (only GRAY8 until card t_8e7da3c1)")
set(SVF_PORT pico)
include(${SVF_C}/ports/profiles.cmake) # validates SVF_PROFILE (and SVF_GREY_KIND for grey) before anything else

# A build directory keeps its cache: another profile (or, for grey, another kind) in the same -B would silently rebuild
# the old one. The key is stored once the SDK is found and initialised (below), so a failed first configure locks nothing.
if(SVF_PROFILE STREQUAL "grey")
  set(_svf_configured "grey/${SVF_GREY_KIND}")
else()
  set(_svf_configured "${SVF_PROFILE}")
endif()
if(SVF_PROFILE_CONFIGURED AND NOT SVF_PROFILE_CONFIGURED STREQUAL _svf_configured)
  message(FATAL_ERROR "this build directory was configured for ${SVF_PROFILE_CONFIGURED}: use a fresh -B directory")
endif()

# -DPICO_SDK_PATH, else a cached value, else the environment (an empty cached value does not hide the environment)
if(NOT PICO_SDK_PATH AND NOT "$ENV{PICO_SDK_PATH}" STREQUAL "")
  set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}" CACHE PATH "pico-sdk checkout" FORCE)
endif()
if(NOT PICO_SDK_PATH)
  message(FATAL_ERROR "PICO_SDK_PATH: pass -DPICO_SDK_PATH=... or set the environment")
endif()
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(svf_pico_${SVF_PROFILE} C CXX ASM)
pico_sdk_init()
set(SVF_PROFILE_CONFIGURED "${_svf_configured}" CACHE INTERNAL "profile (and for grey the kind) this build directory is for")

set(SVF_TARGET svf_pico_${SVF_PROFILE})
set(SVF_FACE_GEN ${CMAKE_CURRENT_BINARY_DIR}/faces)
file(MAKE_DIRECTORY ${SVF_FACE_GEN})
set(SVF_FACE_SRCS)

# The faces as C arrays, generated at build time (not committed), from the profile's row of profiles.txt (SVF_FACES, under
# svf/). One face is the array svf_face_data (mono); several are named after the file (paplg16, paplg18).
# -DSVF_FACE_ASCII= / -DSVF_FACE_HANGUL= replace the first two faces, -DSVF_FACE= the single one.
set(_svf_face_list)
list(LENGTH SVF_FACES _svf_nfaces)
set(_svf_i 0)
foreach(_svf_f IN LISTS SVF_FACES)
  if(_svf_nfaces EQUAL 1)
    set(SVF_FACE ${SVF_ROOT}/svf/${_svf_f} CACHE FILEPATH "face embedded in flash")
    set(_svf_path "${SVF_FACE}")
    set(_svf_name svf_face_data)
  else()
    get_filename_component(_svf_name ${_svf_f} NAME_WE)
    string(TOLOWER ${_svf_name} _svf_name)
    if(_svf_i EQUAL 0)
      set(SVF_FACE_ASCII ${SVF_ROOT}/svf/${_svf_f} CACHE FILEPATH "ASCII face embedded in flash (colour, grey)")
      set(_svf_path "${SVF_FACE_ASCII}")
    elseif(_svf_i EQUAL 1)
      set(SVF_FACE_HANGUL ${SVF_ROOT}/svf/${_svf_f} CACHE FILEPATH "Hangul face embedded in flash (colour, grey)")
      set(_svf_path "${SVF_FACE_HANGUL}")
    else()
      set(_svf_path ${SVF_ROOT}/svf/${_svf_f})
    endif()
  endif()
  add_custom_command(OUTPUT "${SVF_FACE_GEN}/${_svf_name}.c"
    COMMAND python3 -I "${SVF_C}/bench/mkface.py" "${_svf_path}" "${SVF_FACE_GEN}/${_svf_name}.c" --name ${_svf_name} --profile mcu-strict
    DEPENDS "${_svf_path}" "${SVF_C}/bench/mkface.py" VERBATIM)
  list(APPEND SVF_FACE_SRCS "${SVF_FACE_GEN}/${_svf_name}.c")
  math(EXPR _svf_i "${_svf_i} + 1")
endforeach()

file(GLOB SVF_SRCS ${SVF_C}/src/*.c)
add_executable(${SVF_TARGET} main.c profile_${SVF_PROFILE}.c disp_${SVF_DRIVER}.c ${SVF_SRCS} ${SVF_FACE_SRCS})
target_include_directories(${SVF_TARGET} PRIVATE ${CMAKE_CURRENT_LIST_DIR} ${SVF_C}/ports ${SVF_C}/include)
target_compile_definitions(${SVF_TARGET} PRIVATE SVF_NO_SCALE SVF_TARGETS=${SVF_TARGETS_BIT} ${SVF_GREY_KIND_DEFINE})
target_link_libraries(${SVF_TARGET} pico_stdlib hardware_${SVF_BUS})
if(NOT PICO_NO_PICOTOOL)
  pico_add_extra_outputs(${SVF_TARGET})
endif()

# A distributed image carries the faces' notices and licence texts (c/ports/FACES.md): copied next to the image.
file(COPY ${SVF_C}/ports/FACES.md ${SVF_ROOT}/svf/dos/OFLPAPLG.TXT ${SVF_ROOT}/svf/dos/OFL.TXT
          ${SVF_ROOT}/svf/dos/NEODGM.TXT DESTINATION ${CMAKE_BINARY_DIR}/licences)
