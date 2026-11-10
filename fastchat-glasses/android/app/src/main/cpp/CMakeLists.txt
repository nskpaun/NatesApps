cmake_minimum_required(VERSION 3.22)
project(fastchat_llm LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# llama.cpp, pinned. Upstream runs Bonsai's Q2_0 file from b11556 on; v0.9.0 is the first stable
# release after that. To use Bonsai's PQ2_0 / MTP files instead, point these at the PrismML fork
# (https://github.com/PrismML-Eng/llama.cpp, tag prism-b12128-d7b2896): its llama.h matches.
set(LLAMA_REPO "https://github.com/ggml-org/llama.cpp.git" CACHE STRING "llama.cpp repository")
set(LLAMA_TAG "v0.9.0" CACHE STRING "llama.cpp tag")
set(LLAMA_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../third_party/llama.cpp" CACHE PATH "llama.cpp checkout")

# The checkout is shared by every build (debug, release, desktop) and fetched once.
if(NOT EXISTS "${LLAMA_DIR}/CMakeLists.txt")
    message(STATUS "Fetching llama.cpp ${LLAMA_TAG} into ${LLAMA_DIR}")
    execute_process(
        COMMAND git clone --depth 1 --branch ${LLAMA_TAG} ${LLAMA_REPO} ${LLAMA_DIR}
        RESULT_VARIABLE clone_result)
    if(NOT clone_result EQUAL 0)
        message(FATAL_ERROR "Could not clone llama.cpp ${LLAMA_TAG} from ${LLAMA_REPO}")
    endif()
endif()

set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_COMMON OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_APP OFF CACHE BOOL "" FORCE)
set(LLAMA_OPENSSL OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_CCACHE OFF CACHE BOOL "" FORCE)
# CPU only, on purpose: Bonsai's ternary kernels are CPU (NEON) kernels.
set(GGML_METAL OFF CACHE BOOL "" FORCE)
if(ANDROID)
    set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
    set(GGML_LLAMAFILE OFF CACHE BOOL "" FORCE)
    # Baseline: ARMv8.2 with dot-product and half-float, which every flagship phone since 2019
    # has. The Q2_0 kernel uses the dot-product instructions directly.
    set(GGML_CPU_ARM_ARCH "armv8.2-a+dotprod+fp16" CACHE STRING "" FORCE)
endif()

add_subdirectory(${LLAMA_DIR} llama-build EXCLUDE_FROM_ALL)

add_library(llm_engine STATIC llm_engine.cpp)
target_include_directories(llm_engine PUBLIC ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(llm_engine PUBLIC llama)

if(ANDROID)
    add_library(fastchat_llm SHARED jni.cpp)
    target_link_libraries(fastchat_llm PRIVATE llm_engine log)
endif()

# Command-line tool for trying the engine against the real model, on a desktop or (built with the
# NDK and pushed with adb) on the phone itself: see the README. Not part of the app build.
add_executable(llm_cli EXCLUDE_FROM_ALL llm_cli.cpp)
target_link_libraries(llm_cli PRIVATE llm_engine)
