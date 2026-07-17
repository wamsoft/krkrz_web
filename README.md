# krkrz_web

吉里吉里Z (Kirikiri Z) を **Emscripten (wasm32) でブラウザ上で動かす**ための
プロジェクトテンプレート。

このリポジトリは「ガワ」のみで、エンジン本体・プラグインのソースは
`krkrz_dev` (umbrella リポジトリ) から参照する。`krkrz_nx` (コンソール版) /
`krkrz_android` (Android 版) と同じ外枠方式。

## 必要なもの

- **emsdk** — `git clone https://github.com/emscripten-core/emsdk && ./emsdk install latest && ./emsdk activate latest`
- **vcpkg** — `VCPKG_ROOT` 環境変数
- **krkrz_dev** — このリポジトリと同じ場所に clone してあること
  (別の場所なら `KRKRZ_BASE` 環境変数に krkrz_dev の親フォルダを設定)
- CMake 3.22+ / Ninja / Python 3 (開発サーバ用)

## ビルドと実行

```bash
export EMSDK=/path/to/emsdk      # 既定: D:/work/emsdk

make prebuild    # cmake configure (vcpkg install が走る)
make build       # ビルド → build/wasm32-emscripten/Release/krkrz/krkrz.html
make run         # ビルド + http://localhost:8080/krkrz.html で配信
```

ゲームデータは `-DKRKRZ_WEB_DATA_DIR=<folder>` で指定したフォルダが
MEMFS の `/data` に preload される (既定は core 同梱のサンプルデータ)。

```bash
CMAKEOPT='-DKRKRZ_WEB_DATA_DIR=/path/to/game/data' make prebuild build
```

## 配信時の注意 (COOP/COEP)

pthread (SharedArrayBuffer) を使うため、配信サーバは以下のヘッダが**必須**:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

`web/serve.py` はこれを付けて配信する開発用サーバ。itch.io は
「SharedArrayBuffer support」を有効にすれば配信できる。

## 構成のポイント

- プラグインは全て静的リンク (`TVP_PLUGINS_STATIC`)。wasm に DLL は無い
- Elements ダイアログ / movie-player (動画) / REPL は初期スコープ外 (OFF)
- 描画は既定で SDL_Renderer (`-drawdevice=sdl`、`web/pre.js` で指定)。
  OpenGL 系機能 (Canvas/Shader) を使う場合は pre.js の引数を変更
  (リンクには `-sFULL_ES3` を含めてある)
- セーブデータは `/save` を IDBFS にマウント (`web/pre.js`)。
  書き込み後の永続化フラッシュはエンジン側対応が進行中 (Phase 3)

## ライセンス

吉里吉里Z 本体に準ずる。
