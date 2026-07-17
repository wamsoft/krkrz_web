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

set(VCPKG_ENV_PASSTHROUGH_UNTRACKED EMSDK PATH)

if(NOT DEFINED ENV{EMSDK})
   message(FATAL_ERROR "EMSDK environment variable is required")
endif()

set(VCPKG_TARGET_ARCHITECTURE wasm32)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE static)
set(VCPKG_CMAKE_SYSTEM_NAME Emscripten)

# 独自 chainload toolchain 使用時、VCPKG_C_FLAGS はポートビルドへ反映されない
# (vcpkg 標準 toolchain が読む変数のため)。そこで Emscripten.cmake を include
# して *_FLAGS_INIT に -pthread を足すラッパー toolchain を chainload する。
set(VCPKG_CHAINLOAD_TOOLCHAIN_FILE "${CMAKE_CURRENT_LIST_DIR}/../toolchains/wasm32-emscripten-pthread.toolchain.cmake")
