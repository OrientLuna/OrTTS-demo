cmake_minimum_required(VERSION 3.22)
project(OrTTSDemo VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(ORTTS_ENGINE_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/third_party/ortts-engine" CACHE PATH "Standalone ortts-engine source tree")
set(ORTTS_ENGINE_PREFIX "" CACHE PATH "Optional prebuilt ortts-engine build or install prefix to inherit directly")
option(ORTTS_ENABLE_LIQUIDCODEC "LiquidCodec support (built into ortts-engine)" ON)
option(ORTTS_ANDROID_CPU_AUTO "Android arm64 CPU module dispatch" OFF)
option(ORTTS_CPU_DISPATCH_QA "Enable test-only CPU module override" OFF)
option(ORTTS_BUILD_ENGINE_PLUGIN "Install/build embeddable libortts runtime" OFF)
option(ORTTS_BUILD_ANDROID_JNI "Build Android app JNI and device support libraries" OFF)

set(ORTTS_CPU_PROFILE "legacy" CACHE STRING "legacy, x86_64-baseline, x86_64-avx2, arm64-baseline, arm64-dotprod, arm64-i8mm, arm64-auto")

if(ORTTS_ANDROID_CPU_AUTO)
  if(NOT ANDROID OR NOT ANDROID_ABI STREQUAL "arm64-v8a")
    message(FATAL_ERROR "CPU auto requires Android arm64-v8a")
  endif()
  set(ORTTS_CPU_PROFILE "arm64-auto" CACHE STRING "CPU profile" FORCE)
  add_compile_definitions(ORTTS_ANDROID_CPU_AUTO=1 ORTTS_CPU_DISPATCH_QA=$<BOOL:${ORTTS_CPU_DISPATCH_QA}>)
endif()

add_compile_definitions(
  ORTTS_WITH_LIQUIDCODEC=1
  ORTTS_WITH_COOPERATIVE_CANCEL=1
  ORTTS_WITH_P3_FOUR_ROUND=1
  ORTTS_WITH_SPEECH=0
)

if(ANDROID)
  add_compile_options($<$<CONFIG:Release>:-ffunction-sections> $<$<CONFIG:Release>:-fdata-sections>)
endif()

set(_ortts_cpu_auto_modules
  ggml
  ggml-base
  ggml-cpu-android_armv8.0_1
  ggml-cpu-android_armv8.2_2
  ggml-cpu-android_armv8.6_1
)

if(ORTTS_ENGINE_PREFIX)
  get_filename_component(_ortts_prefix "${ORTTS_ENGINE_PREFIX}" ABSOLUTE)
  if(APPLE)
    set(_ortts_lib_names libortts.dylib ortts)
  else()
    set(_ortts_lib_names libortts.so ortts)
  endif()
  find_library(ORTTS_PREBUILT_LIBRARY
    NAMES ${_ortts_lib_names}
    PATHS "${_ortts_prefix}/lib" "${_ortts_prefix}"
    NO_DEFAULT_PATH
    NO_CMAKE_FIND_ROOT_PATH
  )
  if(NOT ORTTS_PREBUILT_LIBRARY)
    message(FATAL_ERROR "Prebuilt libortts not found under ORTTS_ENGINE_PREFIX=${_ortts_prefix}")
  endif()

  if(EXISTS "${_ortts_prefix}/include/ortts_engine.h" AND EXISTS "${_ortts_prefix}/include/audiocpp.h")
    set(_ortts_include_dir "${_ortts_prefix}/include")
  elseif(EXISTS "${ORTTS_ENGINE_SOURCE}/include/ortts_engine.h")
    set(_ortts_include_dir "${ORTTS_ENGINE_SOURCE}/include")
  else()
    message(FATAL_ERROR "ortts-engine headers not found under ${_ortts_prefix}/include or ${ORTTS_ENGINE_SOURCE}/include")
  endif()

  add_library(ortts_runtime SHARED IMPORTED GLOBAL)
  set_target_properties(ortts_runtime PROPERTIES
    IMPORTED_LOCATION "${ORTTS_PREBUILT_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${_ortts_include_dir}"
  )

  set(_ortts_prebuilt_extra_libs "")
  if(ORTTS_ANDROID_CPU_AUTO)
    foreach(_mod IN LISTS _ortts_cpu_auto_modules)
      set(_mod_var "ORTTS_PREBUILT_${_mod}")
      find_library(${_mod_var}
        NAMES "lib${_mod}.so"
        PATHS "${_ortts_prefix}/lib" "${_ortts_prefix}"
        NO_DEFAULT_PATH
        NO_CMAKE_FIND_ROOT_PATH
      )
      if(NOT ${_mod_var})
        message(FATAL_ERROR "Prebuilt --cpu-auto library lib${_mod}.so not found under ${_ortts_prefix}")
      endif()
      list(APPEND _ortts_prebuilt_extra_libs "${${_mod_var}}")
    endforeach()
  endif()
else()
  if(NOT EXISTS "${ORTTS_ENGINE_SOURCE}/CMakeLists.txt")
    message(FATAL_ERROR "Missing ortts-engine source at ${ORTTS_ENGINE_SOURCE}; run git submodule update --init third_party/ortts-engine or pass -DORTTS_ENGINE_PREFIX=...")
  endif()
  add_subdirectory("${ORTTS_ENGINE_SOURCE}" ortts_engine EXCLUDE_FROM_ALL)
  add_library(ortts_runtime ALIAS ortts)
endif()

# Native CLI entry point
add_executable(ortts-tts src/tts_main.cpp)
target_compile_definitions(ortts-tts PRIVATE AUDIOCPP_ORTTS_JOINT=1 AUDIOCPP_VERSION_STRING="ortts-demo-local-0.1.0")
target_link_libraries(ortts-tts PRIVATE ortts_runtime)
if(APPLE)
  set_target_properties(ortts-tts PROPERTIES BUILD_RPATH "@loader_path" INSTALL_RPATH "@loader_path")
elseif(UNIX)
  set_target_properties(ortts-tts PROPERTIES BUILD_RPATH "$ORIGIN" INSTALL_RPATH "$ORIGIN")
endif()
if(ANDROID)
  target_link_libraries(ortts-tts PRIVATE log)
  target_link_options(ortts-tts PRIVATE "-Wl,-z,max-page-size=16384")
endif()
install(TARGETS ortts-tts RUNTIME DESTINATION bin BUNDLE DESTINATION bin)

if(ORTTS_BUILD_ENGINE_PLUGIN)
  if(ORTTS_CPU_PROFILE STREQUAL "legacy")
    message(FATAL_ERROR "Plugin builds require an explicit ORTTS_CPU_PROFILE; use tools/build_engine.py")
  endif()
  if(ORTTS_ENGINE_PREFIX)
    add_custom_target(ortts_engine)
    install(PROGRAMS "${ORTTS_PREBUILT_LIBRARY}" DESTINATION lib COMPONENT Engine)
    if(ORTTS_ANDROID_CPU_AUTO)
      install(PROGRAMS ${_ortts_prebuilt_extra_libs} DESTINATION lib COMPONENT Engine)
    endif()
    install(FILES "${_ortts_include_dir}/ortts_engine.h" "${_ortts_include_dir}/ortts_capi.h"
      DESTINATION include COMPONENT Engine)
  else()
    add_custom_target(ortts_engine DEPENDS ortts)
    if(ORTTS_ANDROID_CPU_AUTO)
      add_dependencies(ortts_engine ${_ortts_cpu_auto_modules})
      foreach(_mod IN LISTS _ortts_cpu_auto_modules)
        install(PROGRAMS "$<TARGET_FILE:${_mod}>" DESTINATION lib COMPONENT Engine)
      endforeach()
    endif()
    install(PROGRAMS "$<TARGET_FILE:ortts>" DESTINATION lib COMPONENT Engine)
    install(FILES "${ORTTS_ENGINE_SOURCE}/include/ortts_engine.h" "${ORTTS_ENGINE_SOURCE}/include/ortts_capi.h"
      DESTINATION include COMPONENT Engine)
  endif()
endif()

if(ORTTS_BUILD_ANDROID_JNI)
  if(NOT ANDROID)
    message(FATAL_ERROR "Android JNI requires an Android toolchain")
  endif()
  add_library(ortts_jni SHARED android/app/src/main/cpp/ortts_jni.cpp)
  set_target_properties(ortts_jni PROPERTIES C_VISIBILITY_PRESET hidden CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN YES)
  target_include_directories(ortts_jni PRIVATE runtime/include runtime/src)
  target_compile_definitions(ortts_jni PRIVATE ORTTS_WITH_SPEECH=0 ORTTS_WITH_P3_FOUR_ROUND=1)
  target_link_libraries(ortts_jni PRIVATE ortts_runtime log)
  target_link_options(ortts_jni PRIVATE "-Wl,-z,max-page-size=16384" "-Wl,--gc-sections" "-Wl,--exclude-libs,ALL")

  add_library(ortts_device SHARED android/app/src/main/cpp/device_support.c)
  set_target_properties(ortts_device PROPERTIES C_VISIBILITY_PRESET hidden)
  target_compile_options(ortts_device PRIVATE -march=armv8-a)
  if(ORTTS_CPU_PROFILE STREQUAL "arm64-dotprod")
    target_compile_definitions(ortts_device PRIVATE ORTTS_DEVICE_DOTPROD_ONLY=1)
  endif()
  target_link_options(ortts_device PRIVATE "-Wl,-z,max-page-size=16384" "-Wl,--gc-sections" "-Wl,--exclude-libs,ALL")
endif()
