cmake_minimum_required(VERSION 3.22)

set(PROJECT_NAME krkrz_web)
set(PROJECT_VERSION 1.0)

# ----------------------------------------------------
# krkrz ソース参照先
#
# KRKRZ_BASE: krkrz_dev フォルダがあるディレクトリ。
# 環境変数 KRKRZ_BASE、なければこのリポジトリの親ディレクトリを仮定する
# (krkrz_dev と krkrz_web が同じ場所に clone されている構成)。
# ----------------------------------------------------

if(DEFINED ENV{KRKRZ_BASE})
    cmake_path(SET KRKRZ_BASE "$ENV{KRKRZ_BASE}")
else()
    cmake_path(SET KRKRZ_BASE "${CMAKE_CURRENT_SOURCE_DIR}/..")
endif()

set(KRKRZ_DIR ${KRKRZ_BASE}/krkrz_dev/src/core)
set(PLUGINS_DIR ${KRKRZ_BASE}/krkrz_dev/src/plugins)

if(NOT EXISTS "${KRKRZ_DIR}/CMakeLists.txt")
    message(FATAL_ERROR "krkrz core not found: ${KRKRZ_DIR} (set KRKRZ_BASE env)")
endif()

# ----------------------------------------------------
# 組み込みプラグイン定義
#
# wasm に共有ライブラリの動的ロードは無いため、プラグインは全て
# TVP_PLUGINS_STATIC で静的リンクする。
# (pre-project で定義: core 側の vcpkg manifest マージ判定にも使われる)
# ----------------------------------------------------

LIST(APPEND TVP_PLUGIN_FOLDERS
   ${PLUGINS_DIR}
)

set(TPSTUB_DIR ${KRKRZ_DIR}/tp_stub)
set(NCBIND_DIR ${PLUGINS_DIR}/ncbind)
set(SIMPLEBIND_DIR ${PLUGINS_DIR}/simplebinder)

LIST(APPEND TVP_PLUGINS_STATIC
  csvParser
  extNagano
  extrans
  json
  KAGParserEx
  saveStruct
  scriptsEx
)

LIST(APPEND TVP_PLUGINS
  ${TVP_PLUGINS_STATIC}
)

# ----------------------------------------------------
# vcpkg マニフェスト統合 (project() より前で実行する必要あり)
#
# トップの vcpkg.json を BASE に、プラグイン各自の vcpkg.json をマージして
# ${CMAKE_BINARY_DIR}/manifest/vcpkg.json に書き出し、VCPKG_MANIFEST_DIR を
# そこへ向ける (krkrz_nx と同方式)。core 側も同名関数で再マージするが
# 出力先が違うため干渉しない。
# ----------------------------------------------------

include(${KRKRZ_DIR}/cmake/MergeVcpkgManifest.cmake)

set(_KRKRZ_WEB_VCPKG_SUBDIRS "")
foreach(_plugin IN LISTS TVP_PLUGINS)
    foreach(_folder IN LISTS TVP_PLUGIN_FOLDERS)
        if(EXISTS "${_folder}/${_plugin}")
            list(APPEND _KRKRZ_WEB_VCPKG_SUBDIRS "${_folder}/${_plugin}")
            break()
        endif()
    endforeach()
endforeach()

set(_KRKRZ_WEB_MANIFEST_DIR "${CMAKE_BINARY_DIR}/manifest")
file(MAKE_DIRECTORY "${_KRKRZ_WEB_MANIFEST_DIR}")

krkrz_merge_vcpkg_manifest(
    BASE    "${CMAKE_CURRENT_SOURCE_DIR}/vcpkg.json"
    OUTPUT  "${_KRKRZ_WEB_MANIFEST_DIR}/vcpkg.json"
    SUBDIRS ${_KRKRZ_WEB_VCPKG_SUBDIRS}
)
set(VCPKG_MANIFEST_DIR "${_KRKRZ_WEB_MANIFEST_DIR}" CACHE PATH
    "vcpkg manifest directory (merged manifest written by krkrz_merge_vcpkg_manifest)" FORCE)

project(${PROJECT_NAME} VERSION ${PROJECT_VERSION})

if(NOT EMSCRIPTEN)
    message(FATAL_ERROR "this project must be configured with the wasm32-emscripten preset (EMSDK required)")
endif()

# ----------------------------------------------------
# krkrz core オプション (wasm 構成)
# ----------------------------------------------------

# SDL3 は静的リンク (wasm に shared は無い)
set(SDL_SHARED OFF CACHE BOOL "Build SDL shared library")
set(SDL_STATIC ON  CACHE BOOL "Build SDL static library")
# SDL3 は Emscripten では pthread バックエンドがデフォルト OFF (ダミー実装で
# SDL_CreateThread が何もせず、krkrz のスレッド起動待ちが永久ブロックする)。
# krkrz は TimerThread 等でスレッド必須なので明示的に有効化する。
set(SDL_PTHREADS ON CACHE BOOL "Use POSIX threads for multi-threading" FORCE)

# ThorVG が find_package(OpenMP) を auto-detect で行うが、Emscripten では
# FindOpenMP が試しコンパイル時の暗黙リンクライブラリ (sysroot キャッシュの
# debug/noexcept 変種) を絶対パスで焼き込み、-fwasm-exceptions のシステム
# ライブラリと重複シンボルになる。wasm に OpenMP は不要なので検出ごと止める
set(CMAKE_DISABLE_FIND_PACKAGE_OpenMP TRUE)

# Elements は部分対応: 非同期 overlay 系 (Dialog.showJson/showFile) は動く。
# モーダル系 (showModal* / navigator フロー / -userconf) はメインスレッドの
# ネストポンプループが wasm で回せないため、core 側 SDLElementsModalRunner の
# __EMSCRIPTEN__ ガードで実行時に失敗を返す
set(KRKRZ_USE_ELEMENTS ON CACHE BOOL "" FORCE)
# movie-player (libvpx) は wasm 初期スコープ外。VideoOverlay はスタブ化
set(KRKRZ_USE_MOVIE OFF CACHE BOOL "" FORCE)
# 端末前提の機能は無効化
set(KRKRZ_REPL OFF CACHE BOOL "" FORCE)
set(KRKRZ_USE_LOGCORE OFF CACHE BOOL "" FORCE)
set(KRKRZ_BUILD_TESTS OFF CACHE BOOL "" FORCE)
# DAP (VSCode デバッガ) は BSD socket 前提のため wasm では不可
set(KRKRZ_ENABLE_DAP OFF CACHE BOOL "" FORCE)

# krkrz プラットフォーム定義
set(KRKRZ_DEFINES_PLATFORM
# miniaudio のランタイムを動的処理しない
MA_NO_RUNTIME_LINKING
# System.buildVariantName の追加定義
KRKRZ_VARIANT_OPTION=_WEB
)

# ----------------------------------------------------
# wasm ビルド設定
# ----------------------------------------------------

# スレッド (SharedArrayBuffer) + wasm 例外。依存ライブラリ側は
# cmake/toolchains/ のラッパ toolchain が同じフラグでビルドしている。
# -fwasm-exceptions は必須: Emscripten デフォルトは C++ 例外無効 (throw=abort)
# だが、TJS はスクリプトエラーを例外で処理する
add_compile_options(-pthread -fwasm-exceptions)
add_link_options(-pthread -fwasm-exceptions)

# 出力は .html (+ .js/.wasm/.data)。emcc 標準シェルでそのまま起動確認できる
set(CMAKE_EXECUTABLE_SUFFIX ".html")

add_subdirectory(${KRKRZ_DIR} ${CMAKE_BINARY_DIR}/krkrz)

# ----------------------------------------------------
# ゲームデータ
#
# KRKRZ_WEB_DATA_DIR のフォルダを MEMFS の /data に preload する。
# 既定は core 同梱のサンプルデータ。案件では -DKRKRZ_WEB_DATA_DIR=... で
# 差し替える。
# ----------------------------------------------------

set(KRKRZ_WEB_DATA_DIR "${KRKRZ_DIR}/data" CACHE PATH "game data folder preloaded to /data")

# ----------------------------------------------------
# 実行ファイル (core 側 target 名 = krkrz) へのリンクオプション
# ----------------------------------------------------

target_link_options(krkrz PRIVATE
    # ワーカ事前確保: pthread 生成がメインループ復帰を待たずに済むようにする。
    # krkrz はスレッド生成直後にメインスレッドが開始待ちでブロックするため、
    # プールが枯渇すると新規 Worker を作れずデッドロックする (メインが
    # イベントループに戻れないため)。常駐スレッド + DrawThread (最大コア数) +
    # サウンドデコード分を見込んで多めに確保する。
    "-sPTHREAD_POOL_SIZE=navigator.hardwareConcurrency+32"
    -sPTHREAD_POOL_SIZE_STRICT=0
    # メモリ: 初期 512MB、成長許可
    -sINITIAL_MEMORY=536870912
    -sALLOW_MEMORY_GROWTH=1
    -sMAXIMUM_MEMORY=2147483648
    # TJS の再帰に備えてスタックは大きめに
    -sSTACK_SIZE=5242880
    -sDEFAULT_PTHREAD_STACK_SIZE=2097152
    # OGLDrawDevice の glMapBufferRange 等 (WebGL2 に無い GLES3 API) の
    # エミュレーションを有効化
    -sFULL_ES3
    # セーブデータ永続化 (IDBFS)
    -lidbfs.js
    # devtools コンソール REPL (pre.js の tjs() → ccall → krkrz_repl_eval)
    -sEXPORTED_RUNTIME_METHODS=ccall
    # 起動引数・IDBFS マウントは pre.js で設定
    "SHELL:--pre-js ${CMAKE_CURRENT_SOURCE_DIR}/web/pre.js"
    # ゲームデータを /data に preload
    "SHELL:--preload-file ${KRKRZ_WEB_DATA_DIR}@/data"
)

# pre.js / データ更新でリリンクさせる
set_property(TARGET krkrz APPEND PROPERTY LINK_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/web/pre.js
)

# Debug ではアサーション有効
target_link_options(krkrz PRIVATE
    $<$<CONFIG:Debug>:-sASSERTIONS=1>
)

# wasm の関数名を name section に保持 (スタックトレース可読化。サイズ増のみで
# 実行速度への影響は無い。プロファイル/デバッグ支援)
target_link_options(krkrz PRIVATE --profiling-funcs)
