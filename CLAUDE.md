# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

吉里吉里Z (Kirikiri Z) の **Emscripten (wasm32, ブラウザ) 版**プロジェクトテンプレート。
このリポジトリは「ガワ」のみで、エンジン本体・プラグインのソースは **外部の
`krkrz_dev` から参照**する (`krkrz_android` と同方式)。リポジトリ内だけを
grep してもエンジン実装は見えない。

- `KRKRZ_BASE` 環境変数 (既定: このリポジトリの親) の `krkrz_dev/src/core` を
  `add_subdirectory` で取り込む。エンジン内部の話は `krkrz_dev/src/core/CLAUDE.md` を読む。
- core 側の wasm 対応 (sources.cmake の `EMSCRIPTEN` 分岐、`cmake/Bin2C.cmake`
  リソース埋め込み、`KRKRZ_USE_MOVIE` オプション等) は krkrz_dev 側のコミット。

## ビルド

必須環境変数: `VCPKG_ROOT`、`EMSDK` (既定 D:/work/emsdk)。

```bash
make prebuild   # cmake --preset wasm32-emscripten (vcpkg install)
make build      # 出力: build/wasm32-emscripten/$BUILD_TYPE/krkrz/krkrz.{html,js,wasm,data}
make run        # build + web/serve.py (COOP/COEP ヘッダ付き) で http://localhost:8080/krkrz.html
```

- vcpkg triplet は overlay の `cmake/triplets/wasm32-emscripten-pthread.cmake`
  (community triplet + `-pthread`)。アプリ本体も `-pthread` でビルドされるため、
  **依存ライブラリと ABI (atomics/bulk-memory) を揃える必要がある** — triplet を
  変えるときは両方を意識すること。
- ゲームデータ: `-DKRKRZ_WEB_DATA_DIR=<dir>` → `--preload-file` で MEMFS `/data` へ。
  既定は `krkrz_dev/src/core/data` (サンプル)。データだけ変えた場合もリリンクが必要。
- 起動引数は `web/pre.js` の `Module['arguments']`。既定 `['-drawdevice=sdl', '/data']`。

## wasm 構成の要点 (なぜこうなっているか)

- **pthread 必須**: core は TimerThread / SoundDecodeThread / AsyncImageLoader /
  StorageCacheThread / WatchThread が常時起動し、Timer とサウンドは無効化=機能喪失。
  よって SharedArrayBuffer (COOP/COEP ヘッダ) が前提。`-sPTHREAD_POOL_SIZE=16` は
  「スレッド生成をメインスレッドが待つ」箇所 (tTVPThread::StartThread) が
  デッドロックしないためのワーカ事前確保で、**削ると起動時にハングする**。
- **プラグインは全静的リンク** (`TVP_PLUGINS_STATIC`)。wasm に SDL_LoadObject は無い。
- **KRKRZ_USE_ELEMENTS=OFF**: Elements モーダルは SDL_Delay 入りネストポンプループ
  (SDLElementsModalRunner.cpp) でメインスレッドをブロックするため wasm では動かない。
- **KRKRZ_USE_MOVIE=OFF**: movie-player (libvpx) は初期スコープ外。
  TVPCreateMoviePlayer は core 側 movie_null.cpp のスタブ (常に nullptr)。
- **描画**: 既定 `-drawdevice=sdl` (SDL_Renderer → WebGL)。OGLDrawDevice 系
  (Canvas/Texture/Shader) は GLES3 の glMapBufferRange 等を使うため
  `-sFULL_ES3` をリンクに含めてある。テクスチャ swizzle は WebGL2 非対応
  (core 側 `_support_swizzle` ガードあり)。
- **リソース (`resource://`)**: core の EMSCRIPTEN 分岐が Bin2C.cmake で C 配列化して
  埋め込む。objcopy 不使用。消費側は Linux と同じ objres.cpp。
- **セーブ**: `/save` を IDBFS にマウント (pre.js)。**書き込み後の
  FS.syncfs(false) フラッシュは未実装 (Phase 3 TODO)** — 現状リロードで消える。
  注入点は Application::CommitSavedata。

## 案件テンプレートとしての使い方

案件では `KRKRZ_WEB_DATA_DIR` を案件データに向け、`TVP_PLUGINS_STATIC` に
必要プラグインを足す。プラグイン追加時は krkrz_dev と同じ名前解決
(`TVP_PLUGIN_FOLDERS` 検索) で、プラグイン側 vcpkg.json も自動マージされる。

## 編集時の注意

- エンジン・プラグインの実装に手を入れる場合、対象は `KRKRZ_BASE/krkrz_dev/` 配下
  (それぞれ独立 submodule) であってこのリポジトリではない。
- ソースは UTF-8、コメント・コミットメッセージは日本語基調。
