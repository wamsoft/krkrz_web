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
# そこへ向ける。core 側も同名関数で再マージするが
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
# セーブデータ永続化: SDL_RunApp が main 実行前にこのパスへ IDBFS を
# autoPersist 付きでマウントし、IndexedDB からの復元完了を待ってから
# SDL_AppInit を開始する。SDL_GetPrefPath がこの配下を返すため、
# user:// (SDL_OpenUserStorage → generic storage backend) の書き込みは
# 自動的に IndexedDB へ永続化される (明示的な FS.syncfs 呼び出しは不要)。
# -lidbfs.js のリンクが前提
set(SDL_EMSCRIPTEN_PERSISTENT_PATH "/persist" CACHE STRING "Path to mount Emscripten IDBFS at startup" FORCE)

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

# 空 (既定) の場合は「サンプルランチャ一式」をステージングして使う:
#   ${KRKRZ_BASE}/krkrz_dev/data (ランチャ + 拡張サンプル群)
# + ${KRKRZ_DIR}/data を core/ サブフォルダとして合成 (コア機能テスト)
# 案件データを使う場合は -DKRKRZ_WEB_DATA_DIR=<folder> で差し替える
set(KRKRZ_WEB_DATA_DIR "" CACHE PATH "game data folder (empty = bundled sample launcher)")

if(KRKRZ_WEB_DATA_DIR STREQUAL "")
    set(_krkrz_web_samples_root ${KRKRZ_BASE}/krkrz_dev/data)
    set(_krkrz_web_data_src ${CMAKE_BINARY_DIR}/sampledata)
    set(_krkrz_web_stage_stamp ${CMAKE_BINARY_DIR}/sampledata.stamp)
    file(GLOB_RECURSE _krkrz_web_stage_deps CONFIGURE_DEPENDS
        "${_krkrz_web_samples_root}/*"
        "${KRKRZ_DIR}/data/*")
    add_custom_command(
        OUTPUT ${_krkrz_web_stage_stamp}
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${_krkrz_web_samples_root} ${_krkrz_web_data_src}
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${KRKRZ_DIR}/data ${_krkrz_web_data_src}/core
        COMMAND ${CMAKE_COMMAND} -E touch ${_krkrz_web_stage_stamp}
        DEPENDS ${_krkrz_web_stage_deps}
        COMMENT "Staging sample data (krkrz_dev/data + core data as core/)"
    )
else()
    set(_krkrz_web_data_src ${KRKRZ_WEB_DATA_DIR})
    set(_krkrz_web_stage_stamp "")
endif()

# ON: データフォルダを tools/xp3pack.py で 1 つの xp3 にパックして /data.xp3 に
#     preload する (リリース形態)。エンジンは起動時に appPath 直下の data.xp3 を
#     自動発見してプロジェクトにする (sdl3/environ/stdapp.cpp)
# OFF: フォルダをそのまま /data に preload する (開発向け。ファイル構成が
#     ブラウザの devtools からそのまま見える)
option(KRKRZ_WEB_DATA_XP3 "pack game data into a single xp3 (release-like layout)" ON)

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
    # devtools コンソール REPL (pre.js の tjs() → ccall → krkrz_repl_eval)。
    # FS はデバッグ/検証時に外部からファイル注入するため export (Module.FS)
    -sEXPORTED_RUNTIME_METHODS=ccall,FS
    # カスタム HTML シェル (黒背景 + canvas フィット + ローディング表示のみ。
    # emscripten 既定シェルのロゴ/チェックボックス/出力 textarea を排除)
    "SHELL:--shell-file ${CMAKE_CURRENT_SOURCE_DIR}/web/shell.html"
)
# 注: pre.js はビルド構成フラグ (webconfig.js) の後に読み込む必要があるため、
# データ構成確定後 (下方) で --pre-js を指定する

if(KRKRZ_WEB_DATA_XP3)
    # データを build 時に xp3 へパックして単体 preload
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(KRKRZ_WEB_DATA_XP3_FILE ${CMAKE_BINARY_DIR}/gamedata.xp3)
    if(_krkrz_web_stage_stamp STREQUAL "")
        file(GLOB_RECURSE _krkrz_web_data_files CONFIGURE_DEPENDS "${_krkrz_web_data_src}/*")
        set(_krkrz_web_pack_deps ${_krkrz_web_data_files})
    else()
        set(_krkrz_web_pack_deps ${_krkrz_web_stage_stamp})
    endif()
    add_custom_command(
        OUTPUT ${KRKRZ_WEB_DATA_XP3_FILE}
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/xp3pack.py
            pack "${_krkrz_web_data_src}" "${KRKRZ_WEB_DATA_XP3_FILE}"
        DEPENDS ${_krkrz_web_pack_deps} ${CMAKE_CURRENT_SOURCE_DIR}/tools/xp3pack.py
        COMMENT "Packing game data to gamedata.xp3"
    )
    add_custom_target(krkrz_web_data_xp3 DEPENDS ${KRKRZ_WEB_DATA_XP3_FILE})
    add_dependencies(krkrz krkrz_web_data_xp3)
    target_link_options(krkrz PRIVATE
        "SHELL:--preload-file ${KRKRZ_WEB_DATA_XP3_FILE}@/data.xp3"
    )
    set_property(TARGET krkrz APPEND PROPERTY LINK_DEPENDS ${KRKRZ_WEB_DATA_XP3_FILE})
else()
    # フォルダをそのまま /data に preload
    if(NOT _krkrz_web_stage_stamp STREQUAL "")
        add_custom_target(krkrz_web_data_stage DEPENDS ${_krkrz_web_stage_stamp})
        add_dependencies(krkrz krkrz_web_data_stage)
        set_property(TARGET krkrz APPEND PROPERTY LINK_DEPENDS ${_krkrz_web_stage_stamp})
    endif()
    target_link_options(krkrz PRIVATE
        "SHELL:--preload-file ${_krkrz_web_data_src}@/data"
    )
endif()

# ビルド構成フラグ (webconfig.js)。Module.arguments は生成 JS のロード時に
# 読み取られるため、pre.js がトップレベルで同期的に引数を組み立てられるよう
# 構成情報を pre.js より先の --pre-js として注入する
set(_krkrz_web_config_js ${CMAKE_BINARY_DIR}/webconfig.js)
if(KRKRZ_WEB_DATA_XP3)
    set(_krkrz_web_xp3_flag "true")
else()
    set(_krkrz_web_xp3_flag "false")
endif()
file(WRITE ${_krkrz_web_config_js}
"// 生成物 (CMakeLists.txt): ビルド構成フラグ。pre.js より先に読み込まれる
var KRKRZ_WEB_DATA_XP3 = ${_krkrz_web_xp3_flag};
")
target_link_options(krkrz PRIVATE
    "SHELL:--pre-js ${_krkrz_web_config_js}"
    "SHELL:--pre-js ${CMAKE_CURRENT_SOURCE_DIR}/web/pre.js"
)

# pre.js / shell.html / webconfig.js 更新でリリンクさせる
set_property(TARGET krkrz APPEND PROPERTY LINK_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/web/pre.js
    ${CMAKE_CURRENT_SOURCE_DIR}/web/shell.html
    ${_krkrz_web_config_js}
)

# Debug ではアサーション有効
target_link_options(krkrz PRIVATE
    $<$<CONFIG:Debug>:-sASSERTIONS=1>
)

# wasm の関数名を name section に保持 (スタックトレース可読化。サイズ増のみで
# 実行速度への影響は無い。プロファイル/デバッグ支援)
target_link_options(krkrz PRIVATE --profiling-funcs)
