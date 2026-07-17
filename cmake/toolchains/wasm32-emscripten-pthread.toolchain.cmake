# Emscripten toolchain + -pthread
#
# vcpkg は独自の VCPKG_CHAINLOAD_TOOLCHAIN_FILE を指定した場合、triplet の
# VCPKG_C_FLAGS / VCPKG_CXX_FLAGS をポートビルドに反映しない (あれらは vcpkg
# 標準 toolchain (scripts/toolchains/*.cmake) が読む変数のため)。
# そこで Emscripten.cmake を include した上で *_FLAGS_INIT に -pthread を
# 追加するラッパーを chainload する。ポートビルドと本体ビルドの両方で使う。

if(NOT DEFINED ENV{EMSDK})
    message(FATAL_ERROR "EMSDK environment variable is required")
endif()

include("$ENV{EMSDK}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake")

string(APPEND CMAKE_C_FLAGS_INIT " -pthread")
string(APPEND CMAKE_CXX_FLAGS_INIT " -pthread")
string(APPEND CMAKE_EXE_LINKER_FLAGS_INIT " -pthread")
