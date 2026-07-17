# wasm32-emscripten の pthread 有効版 overlay triplet
#
# krkrz 本体は TimerThread / SoundDecodeThread 等でスレッド必須のため
# アプリを -pthread でビルドする。wasm では -pthread が atomics/bulk-memory
# を使う別 ABI になるので、vcpkg でビルドする依存ライブラリ側も同じフラグで
# コンパイルされている必要がある。community triplet (wasm32-emscripten) に
# -pthread を足しただけのもの。
#
# 注意: SharedArrayBuffer を使うため、配信側 (ホスティング/開発サーバ) は
# COOP/COEP ヘッダが必須 (web/serve.py 参照)。

set(VCPKG_ENV_PASSTHROUGH_UNTRACKED EMSCRIPTEN_ROOT EMSDK PATH)

if(NOT DEFINED ENV{EMSCRIPTEN_ROOT})
   find_path(EMSCRIPTEN_ROOT "emcc")
else()
   set(EMSCRIPTEN_ROOT "$ENV{EMSCRIPTEN_ROOT}")
endif()

if(NOT EMSCRIPTEN_ROOT)
   if(NOT DEFINED ENV{EMSDK})
      message(FATAL_ERROR "The emcc compiler not found in PATH")
   endif()
   set(EMSCRIPTEN_ROOT "$ENV{EMSDK}/upstream/emscripten")
endif()

if(NOT EXISTS "${EMSCRIPTEN_ROOT}/cmake/Modules/Platform/Emscripten.cmake")
   message(FATAL_ERROR "Emscripten.cmake toolchain file not found")
endif()

set(VCPKG_TARGET_ARCHITECTURE wasm32)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE static)
set(VCPKG_CMAKE_SYSTEM_NAME Emscripten)
set(VCPKG_CHAINLOAD_TOOLCHAIN_FILE "${EMSCRIPTEN_ROOT}/cmake/Modules/Platform/Emscripten.cmake")

set(VCPKG_C_FLAGS "-pthread")
set(VCPKG_CXX_FLAGS "-pthread")
