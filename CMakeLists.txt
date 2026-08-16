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

# プラグイン参照先 (krkrz_nx / krkrz_android と同じ 3 フォルダ構成)
LIST(APPEND TVP_PLUGIN_FOLDERS
   ${PLUGINS_DIR}
   ${KRKRZ_BASE}/wamsoft_work
   ${KRKRZ_BASE}/krkrtemplate/plugins_utf8
)

set(TPSTUB_DIR ${KRKRZ_DIR}/tp_stub)
set(NCBIND_DIR ${PLUGINS_DIR}/ncbind)
set(SIMPLEBIND_DIR ${PLUGINS_DIR}/simplebinder)

# krkrz_nx と同じ組み込みプラグイン一式 (Android/コンソール専用の
# virtualpad / androidconfig / license / ps5* を除く)。案件 (KAG3 ADV) が
# 依存するプラグインを揃える。+ web で追加した extrans / extNagano。
LIST(APPEND TVP_PLUGINS_STATIC
# krkrz_dev/src/plugins
  csvParser
  getSample
  json
  KAGParserEx
  layerExBTOA
  layerExImage
  layerExRaster
  layerExVector
  saveStruct
  scriptsEx
  shrinkCopy
# krkrtemplate/plugins_utf8
  getLangName
  textrender
  tjsDataPack
  tlgSliceLoader
# wamsoft_work
  psbfile
# web 追加 (トランジション)
  extrans
  extNagano
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

# NOTE: core 配下の外部ライブラリ (glyphware) が要求する harfbuzz は vcpkg では
# 入れない。vcpkg の harfbuzz port は meson + -Werror でビルドされ、
# Emscripten の clang が出す -Wunused-template で失敗するため。
# umbrella (krkrz_dev) と同じく cmake/CommonExternals.cmake の FetchContent で
# 供給する (後述の include)。
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
# セーブデータ永続化: このパスへ IDBFS を autoPersist 付きでマウントし、
# IndexedDB からの復元完了を待ってからエンジンを開始する。SDL_GetPrefPath が
# この配下を返すため、user:// (SDL_OpenUserStorage → generic storage backend)
# の書き込みは自動的に IndexedDB へ永続化される (明示的な FS.syncfs 不要)。
# -lidbfs.js のリンクが前提。
# 注意: SDL 側の同機構は SDL_RunApp 内にあるが、wasm は非同期 suspend (Asyncify)
# のため自前 main() で SDL_AppInit を直接呼び SDL_RunApp を通らない。実際のマウント + 復元は
# core sdl3/environ/main.cpp が KRKRZ_EMSCRIPTEN_PERSISTENT_PATH (下記) で行う。
# SDL 側オプションは SDL_GetPrefPath の経路のために引き続き設定しておく。
set(SDL_EMSCRIPTEN_PERSISTENT_PATH "/persist" CACHE STRING "Path to mount Emscripten IDBFS at startup" FORCE)
add_compile_definitions("KRKRZ_EMSCRIPTEN_PERSISTENT_PATH=\"/persist\"")

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
# テキスト読み込みエンコーディングは UTF-8 固定バイナリにしておき、Shift-JIS
# 案件は起動オプション -readencoding=Shift_JIS で実行時に切り替える
# (DefaultReadEncoding は実行時変数。TVPInitScriptEngine で -readencoding を
#  パースし startup.tjs 実行前に反映される)。案件ごとの再ビルドが不要になる。
set(KRKRZ_USE_SJIS OFF CACHE BOOL "" FORCE)
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

# 埋め込みリソースフォルダの差し替え (NX の setup/nxresource / Android の asset 相当)。
# 案件の config.cf / messages.json / SysInitScript.tjs / フォント一式を wasm に
# 埋め込みたい場合に指定する。空なら core 同梱の既定リソースを使う。
#   -DKRKRZ_WEB_RESOURCE_DIR=<案件のリソースフォルダ>
# 例: -DKRKRZ_WEB_RESOURCE_DIR=/path/to/game/setup/nxresource
# core の KRKRZ_RESOURCE_DIR に橋渡しする (add_subdirectory の前に確定させる)。
set(KRKRZ_WEB_RESOURCE_DIR "" CACHE PATH "埋め込みリソースフォルダ (空=core 同梱の既定)")
if(NOT KRKRZ_WEB_RESOURCE_DIR STREQUAL "")
    set(KRKRZ_RESOURCE_DIR "${KRKRZ_WEB_RESOURCE_DIR}" CACHE PATH "" FORCE)
    message(STATUS "krkrz_web: embedding resource dir: ${KRKRZ_WEB_RESOURCE_DIR}")
endif()

# ----------------------------------------------------
# 共通外部依存 (HarfBuzz / ThorVG 設定)
#
# umbrella (krkrz_dev) が全サブモジュールへ 1 つの HarfBuzz を配るのと同じ仕組みを
# web 外枠でも使う。include するだけで krkrz_setup_harfbuzz() が走り、
# `harfbuzz` ターゲットが用意される (glyphware / elements / ThorVG が
# if(NOT TARGET harfbuzz) ガード越しに再利用する)。
#
# vcpkg の harfbuzz port を使わない理由: meson + -Werror でビルドされるため
# Emscripten の clang が出す -Wunused-template で失敗する。
# ----------------------------------------------------
if(EXISTS "${KRKRZ_BASE}/krkrz_dev/cmake/CommonExternals.cmake")
    include(${KRKRZ_BASE}/krkrz_dev/cmake/CommonExternals.cmake)
endif()

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

# データを MEMFS に preload するか。案件で巨大データを web:// でオンデマンド配信する
# 場合は OFF にして /data(.xp3) を焼かない (stage_web.py が web:// 配信を用意する)。
option(KRKRZ_WEB_DATA_PRELOAD "preload game data into MEMFS (OFF = serve via web://)" ON)

if(KRKRZ_WEB_DATA_PRELOAD)
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
# 非同期 suspend バックエンドの選択 (Asyncify / JSPI)
# ----------------------------------------------------
# Elements モーダルダイアログの同期待機ループ (PumpModalLoop) や毎フレームの yield
# (EM_ASYNC_JS krkrz_jspi_wait_frame) が、メインスレッドをブロックせず次フレームまで
# suspend できるようにする機構。wasm メインループは SDL_MAIN_USE_CALLBACKS ではなく
# 自前 main() の while で SDL_AppInit/AppIterate を駆動する
# (sdl3/environ/main.cpp の __EMSCRIPTEN__)。EM_ASYNC_JS はバックエンド非依存なので
# どちらを選んでも core 側 C++ は無改修。
#
#   ASYNCIFY (既定) … wasm を計装して suspend。全ブラウザで動作。代償は wasm 肥大化と
#                     やや低速化 (Chrome も Asyncify 経路)。将来 -sASYNCIFY_ONLY で削減可。
#   JSPI            … ブラウザのネイティブスタック切替で suspend。軽量・高速だが
#                     Chrome/Edge 137+ でのみ既定有効。Firefox は about:config フラグ裏
#                     (javascript.options.wasm_js_promise_integration)、Safari は未実装。
#
# 切替: cmake ... -DKRKRZ_WEB_ASYNC_BACKEND=JSPI
set(KRKRZ_WEB_ASYNC_BACKEND "ASYNCIFY" CACHE STRING
    "async suspend backend: ASYNCIFY (all browsers) or JSPI (Chrome/Edge 137+ only, smaller/faster)")
set_property(CACHE KRKRZ_WEB_ASYNC_BACKEND PROPERTY STRINGS ASYNCIFY JSPI)

if(KRKRZ_WEB_ASYNC_BACKEND STREQUAL "JSPI")
    set(_krkrz_web_async_link_options -sJSPI)
    message(STATUS "krkrz_web: async backend = JSPI (Chrome/Edge 137+ only)")
elseif(KRKRZ_WEB_ASYNC_BACKEND STREQUAL "ASYNCIFY")
    # 深い TJS 再帰 + モーダルのネスト待機に備え Asyncify の unwind バッファを拡大
    # (既定 4KB では溢れる: RuntimeError unreachable / stack overflow)。不足なら増やす。
    set(_krkrz_web_async_link_options -sASYNCIFY -sASYNCIFY_STACK_SIZE=1048576)
    message(STATUS "krkrz_web: async backend = Asyncify (all browsers)")
else()
    message(FATAL_ERROR
        "KRKRZ_WEB_ASYNC_BACKEND must be ASYNCIFY or JSPI (got: ${KRKRZ_WEB_ASYNC_BACKEND})")
endif()

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
    # 非同期 suspend バックエンド (Asyncify 既定 / JSPI)。
    # 上の KRKRZ_WEB_ASYNC_BACKEND オプションで切替 (-DKRKRZ_WEB_ASYNC_BACKEND=JSPI)
    ${_krkrz_web_async_link_options}
    # セーブデータ永続化 (IDBFS)
    -lidbfs.js
    # devtools コンソール REPL (pre.js の tjs() → ccall → krkrz_repl_eval)。
    # FS はデバッグ/検証時に外部からファイル注入するため export (Module.FS)
    -sEXPORTED_RUNTIME_METHODS=ccall,FS,addRunDependency,removeRunDependency
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
endif() # KRKRZ_WEB_DATA_PRELOAD

# ----------------------------------------------------
# リソース と webconfig は「配信サイドカー」にする (バイナリに焼かない)。
#
# これにより wasm/krkrz.data は完全に案件非依存の**共有バイナリ**になり、案件切替に
# relink が不要。案件差分は下記の配信ファイルの差し替えだけになる:
#   - resource/     … エンジンリソース一式 (config.cf/messages/フォント/SysInitScript)。
#                     pre.js が preRun で MEMFS /resource へ fetch (main 前に確定)。
#                     エンジンは ResourcePath=file://./resource/ から同期読み。
#   - resource.list … resource/ のファイル名一覧 (JSON)。pre.js が参照。
#   - webconfig.js  … 起動時構成 (webbase/args/resource base)。shell が krkrz.js より先に読む。
# stage_web.py はこれらを案件版に差し替えて site を組む (cmake を一切呼ばない)。
# make run / 既定ビルドでは engine 既定 resource + 空 webconfig を出力隣に配置する。
# ----------------------------------------------------

# 案件サイト用の既定値 (make run 用。stage_web.py は自前で webconfig.js を書く)
set(KRKRZ_WEB_DEFAULT_WEBBASE "" CACHE STRING "default webbase (empty = sample launcher)")
set(KRKRZ_WEB_DEFAULT_ARGS "" CACHE STRING "default extra launch args (space-separated)")

# resource.list (resource/ の中身一覧、JSON 配列。フラット構成前提)
file(GLOB _krkrz_web_res_files RELATIVE "${KRKRZ_RESOURCE_DIR}" "${KRKRZ_RESOURCE_DIR}/*")
set(_krkrz_web_res_json "")
foreach(_f ${_krkrz_web_res_files})
    set(_krkrz_web_res_json "${_krkrz_web_res_json}\"${_f}\",")
endforeach()
string(REGEX REPLACE ",$" "" _krkrz_web_res_json "${_krkrz_web_res_json}")
file(WRITE ${CMAKE_BINARY_DIR}/resource.list "[${_krkrz_web_res_json}]")

# webconfig.js (configure 時生成 → POST_BUILD で出力隣へ)
if(KRKRZ_WEB_DATA_XP3)
    set(_krkrz_web_xp3_flag "true")
else()
    set(_krkrz_web_xp3_flag "false")
endif()
if(KRKRZ_WEB_DATA_PRELOAD)
    set(_krkrz_web_preload_flag "true")
else()
    set(_krkrz_web_preload_flag "false")
endif()
set(_krkrz_web_config_js ${CMAKE_BINARY_DIR}/webconfig.js)
file(WRITE ${_krkrz_web_config_js}
"// 生成物 (CMakeLists.txt): 起動時構成。shell が krkrz.js より先に読む (配信ファイル)
var KRKRZ_WEB_DATA_XP3 = ${_krkrz_web_xp3_flag};
var KRKRZ_WEB_DATA_PRELOAD = ${_krkrz_web_preload_flag};
var KRKRZ_WEB_RESOURCE_BASE = \"resource/\";
var KRKRZ_WEB_DEFAULT_WEBBASE = \"${KRKRZ_WEB_DEFAULT_WEBBASE}\";
var KRKRZ_WEB_DEFAULT_ARGS = \"${KRKRZ_WEB_DEFAULT_ARGS}\";
")

# pre.js は焼く (汎用ロジック)。webconfig.js は焼かない (配信ファイル)。
target_link_options(krkrz PRIVATE
    "SHELL:--pre-js ${CMAKE_CURRENT_SOURCE_DIR}/web/pre.js"
)
set_property(TARGET krkrz APPEND PROPERTY LINK_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/web/pre.js
    ${CMAKE_CURRENT_SOURCE_DIR}/web/shell.html
)

# ビルド後、出力隣に resource/ ・ resource.list ・ webconfig.js を配置 (make run 用)。
# krkrz ターゲットは core の add_subdirectory 内で作られるため add_custom_command(TARGET)
# は使えない。ALL な custom target を krkrz に依存させて POST_BUILD 相当にする。
add_custom_target(krkrz_web_sidecars ALL
    COMMAND ${CMAKE_COMMAND} -E rm -rf $<TARGET_FILE_DIR:krkrz>/resource
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${KRKRZ_RESOURCE_DIR} $<TARGET_FILE_DIR:krkrz>/resource
    COMMAND ${CMAKE_COMMAND} -E copy
        ${CMAKE_BINARY_DIR}/resource.list $<TARGET_FILE_DIR:krkrz>/resource.list
    COMMAND ${CMAKE_COMMAND} -E copy
        ${_krkrz_web_config_js} $<TARGET_FILE_DIR:krkrz>/webconfig.js
    COMMENT "Staging web sidecars (resource/, resource.list, webconfig.js)"
)
add_dependencies(krkrz_web_sidecars krkrz)

# Debug ではアサーション有効
target_link_options(krkrz PRIVATE
    $<$<CONFIG:Debug>:-sASSERTIONS=1>
)

# wasm の関数名を name section に保持 (スタックトレース可読化。サイズ増のみで
# 実行速度への影響は無い。プロファイル/デバッグ支援)
target_link_options(krkrz PRIVATE --profiling-funcs)
