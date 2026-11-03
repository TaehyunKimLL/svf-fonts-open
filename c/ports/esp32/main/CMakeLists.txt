# The example and the SVF library as one component: main.c, the profile, the display driver, the library and the
# profile's faces (generated as C arrays at build time by c/bench/mkface.py, not committed: PAPLG18 alone is a 124 KB
# face, about 450 KB of C). SVF_PROFILE, SVF_DISPLAY and SVF_GREY_KIND are cache variables set by ../CMakeLists.txt.
# ESP-IDF reads every component's CMakeLists.txt twice: first in a separate script-mode cmake (CMAKE_BUILD_EARLY_EXPANSION=1,
# to collect requirements; SVF_PROFILE and the other cache values do not exist there), then in the build proper. A component
# that does not call idf_component_register in the first pass is dropped from the build, so the early pass registers the
# component (no REQUIRES: the project does not set COMPONENTS, so the empty early registration links every build
# component; a trimmed build, with COMPONENTS set, needs PRIV_REQUIRES esp_driver_spi esp_driver_gpio here and in the real pass) and stops;
# the sources and definitions below belong to the second.
if(CMAKE_BUILD_EARLY_EXPANSION)
  idf_component_register()
  return()
endif()
get_filename_component(SVF_C ${CMAKE_CURRENT_LIST_DIR}/../../.. ABSOLUTE)
get_filename_component(SVF_ROOT ${SVF_C}/.. ABSOLUTE)
set(SVF_PORT esp32)
include(${SVF_C}/ports/profiles.cmake) # SVF_KIND SVF_TARGETS_BIT SVF_FACES SVF_DRIVER SVF_BUS SVF_GREY_KIND_DEFINE
if(SVF_PROFILE STREQUAL "colour")
  set(SVF_DRIVER ${SVF_DISPLAY}) # ili9341 (the table's) or esp_rgb
endif()

set(SVF_FACE_GEN ${CMAKE_CURRENT_BINARY_DIR}/faces)
file(MAKE_DIRECTORY ${SVF_FACE_GEN})
set(SVF_FACE_SRCS)
# The faces from the profile's row of profiles.txt (SVF_FACES, under svf/). One face is the array svf_face_data (mono);
# several are named after the file (paplg16, paplg18). -DSVF_FACE_ASCII= / -DSVF_FACE_HANGUL= replace the first two
# faces, -DSVF_FACE= the single one.
set(_svf_nfaces 0)
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
set_source_files_properties(${SVF_FACE_SRCS} PROPERTIES GENERATED TRUE)

file(GLOB SVF_SRCS ${SVF_C}/src/*.c)
idf_component_register(SRCS main.c profile_${SVF_PROFILE}.c disp_${SVF_DRIVER}.c ${SVF_SRCS} ${SVF_FACE_SRCS}
                       INCLUDE_DIRS ${SVF_C}/include PRIV_INCLUDE_DIRS . ${SVF_C}/ports)
add_custom_target(svf_faces DEPENDS ${SVF_FACE_SRCS})
add_dependencies(${COMPONENT_LIB} svf_faces)
target_compile_definitions(${COMPONENT_LIB} PRIVATE SVF_NO_SCALE SVF_TARGETS=${SVF_TARGETS_BIT} ${SVF_GREY_KIND_DEFINE})
if(IDF_TARGET STREQUAL "esp32s3")
  target_compile_definitions(${COMPONENT_LIB} PRIVATE SVF_ESP32S3=1)
endif()

# A distributed image carries the faces' notices and licence texts (c/ports/FACES.md): copied next to the image.
file(COPY ${SVF_C}/ports/FACES.md ${SVF_ROOT}/svf/dos/OFLPAPLG.TXT ${SVF_ROOT}/svf/dos/OFL.TXT
          ${SVF_ROOT}/svf/dos/NEODGM.TXT DESTINATION ${CMAKE_BINARY_DIR}/licences)
