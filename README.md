# krkrz_web — 吉里吉里Z ブラウザ版

日本語 | [English](README_en.md)

吉里吉里Z (krkrz) を Emscripten (wasm32) でビルドし、ブラウザで動かすための外枠リポジトリです。
システムまわりは SDL3 を使い、描画は WebGL、スレッドは pthread (SharedArrayBuffer) で動きます。

- エンジン本体とプラグインのソースは [krkrz_dev](https://github.com/wamsoft/krkrz_dev) を `KRKRZ_BASE`
  経由で参照します。このリポジトリにはブラウザ版固有のビルド定義と配信用のファイル (シェル・起動スクリプト・
  ツール) だけを置きます
- wasm 本体はタイトルに依存しない**共有バイナリ**です。エンジンのリソース (config.cf / messages / フォントなど)
  は wasm に埋め込まず、配信ファイル (サイドカー) として隣に置きます。タイトルを替えるときはサイドカーを
  差し替えるだけで、リンクし直す必要はありません
- タイトルごとの設定 (`web-config.json`) と資材は別のフォルダ (プロジェクトフォルダ) に置けます。
  ゲームデータは `web://` でファイル単位にオンデマンド配信します
- `assetPack` (資材の取り込み) は krkrz_android / krkrz_ios / krkrz_linux / krkrz_gdk と共通の書式です。
  プラグインは全て静的リンクするので、`cmake` の節はありません

## 必要なもの

- [emsdk](https://github.com/emscripten-core/emsdk) — `git clone https://github.com/emscripten-core/emsdk && ./emsdk install latest && ./emsdk activate latest`。
  環境変数 `EMSDK` に導入先を指定します (未設定のときの既定は `C:/work/emsdk`。`make EMSDK=<パス>` でも指定できます)
- [vcpkg](https://github.com/microsoft/vcpkg) — 環境変数 `VCPKG_ROOT` に導入先を指定
- [krkrz_dev](https://github.com/wamsoft/krkrz_dev) — このリポジトリと同じ場所に clone します
  (別の場所に置くときは、環境変数 `KRKRZ_BASE` にその親フォルダを指定)
- CMake 3.22 以降 / Ninja / Python 3 (ステージングのツールと開発用サーバに使います)
- GNU Make が使えるシェル (Git Bash / MSYS2 など。Makefile を使う場合)

## セットアップ

1. krkrz_dev とこのリポジトリを同じフォルダに clone します

   ```
   <KRKRZ_BASE>/
   ├── krkrz_dev/        ← git clone --recursive https://github.com/wamsoft/krkrz_dev.git
   └── krkrz_web/        ← このリポジトリ
   ```

2. 環境変数 `EMSDK` と `VCPKG_ROOT` を設定します (`KRKRZ_BASE` の既定はこのリポジトリの親フォルダです)

エンジン本体は `${KRKRZ_BASE}/krkrz_dev/src/core` を `add_subdirectory` で取り込みます (`CMakeLists.txt`)。

## ビルドと実行

```bash
export EMSDK=/path/to/emsdk      # 環境変数が優先。未設定時の既定: C:/work/emsdk

make prebuild    # cmake configure (vcpkg install が走ります)
make build       # 共有バイナリをビルド
make run         # ビルド + http://localhost:8080/krkrz.html で配信 (同梱のサンプル。PORT= で変更)
make serve       # サーバだけ起動

make PROJECT_DIR=/path/to/mygame run   # 自分のプロジェクトフォルダをステージングして起動
```

出力は `build/wasm32-emscripten/$BUILD_TYPE/krkrz/` の `krkrz.html` / `krkrz.js` / `krkrz.wasm` /
`krkrz.data` と、サイドカー (`resource/` / `resource.list` / `webconfig.js`) です。
COOP/COEP ヘッダを付けて配信すれば、そのまま動きます ([配信](#配信)を参照)。

| やること | コマンド |
|---|---|
| 共有バイナリのビルド | `make prebuild` → `make build` |
| サンプルを配信 | `make run` / `make serve` |
| プロジェクトフォルダをステージング (サイトを作るだけ) | `make PROJECT_DIR=/path/to/mygame web` |
| ビルド + ステージング + 起動 | `make PROJECT_DIR=/path/to/mygame run` |
| ビルドの生成物を消す | `make clean` |

サンプル (データ埋め込み構成) のビルドオプション、起動引数と URL パラメータは
[docs/web-build.md](docs/web-build.md) にあります。

## プロジェクトフォルダ (PROJECT_DIR)

krkrz_android の `PROJECT_DIR` 方式のブラウザ版です。先に一度だけ共有バイナリをビルドしておけば
(`make prebuild build`。タイトルに依存しません)、プロジェクトフォルダを指定するだけで、
**プロジェクトフォルダの下に自己完結の実行用サイト**を出力します。cmake は呼ばないので、リンクし直しは
ありません。

```bash
make PROJECT_DIR=/path/to/mygame web    # = python tools/stage_web.py /path/to/mygame
make PROJECT_DIR=/path/to/mygame run    # build → stage → 生成された serve.py で起動
#   → http://localhost:8100/   (web-config.json の port)
```

`${PROJECT_DIR}/build/web/site/` に共有バイナリ (`krkrz.html` は `index.html` に改名)、タイトルの
サイドカー (`resource/` / `resource.list` / `webconfig.js`)、`gamedata/` (web:// で配信するゲームデータ)、
`serve.py` を置きます。生成された `serve.py` を直接実行してもかまいません。

- 配置はハードリンクを自動で選びます (同じドライブなら実体を複製しません。別のドライブなどではファイル単位で
  コピーに切り替わります)。2 回目以降はサイズと更新時刻が同じファイルを飛ばします
- 出力したサイトは絶対パスを参照しないので、フォルダごとコピーしても、別のホストへアップロードしても動きます
- URL に引数を付けなくても、そのタイトルが直接起動します

手順の詳細は [docs/web-config.md](docs/web-config.md) にあります。

## web-config.json

プロジェクトフォルダの `web-config.json` で、表示名・リソース・起動引数・資材を指定します。全て任意で、
無いときは慣例の値で補います (Android の `app-config.json` とは別のファイルです)。
各項目の説明は [docs/web-config.md](docs/web-config.md) にあります。

| キー | 内容 |
|---|---|
| `name` | 表示名 (既定: フォルダ名) |
| `resource` | config.cf / messages / フォントのフォルダ (既定: `setup/nxresource`) |
| `port` | 生成する `serve.py` の既定ポート (既定: 8100) |
| `args` | config.cf より優先する起動引数 (メモリプールの上限など) |
| `lowercase` | `true` で `gamedata/` の配置先を ASCII 小文字にする (大文字小文字を区別する静的配信向け) |
| `assetPack` | 資材の取り込み (外枠共通の書式)。ソースごとの `delivery` (`on-demand` / `prefetch`) はブラウザ版だけの項目 |

`assetPack` とパスの `${...}` 展開の書式は、公開サイトの
[外枠リポジトリの共通設定](https://wamsoft.github.io/krkrz_dev/topics/core/platform_config/) を参照してください。

> **wasm32 の 2GB 上限に注意してください。** Bitmap / File / Krkrz / Sound の各メモリプールの合計が 2GB を
> 超えると、起動時に `Aborted(OOM)` になります。config.cf のプールが大きいタイトルは、`args` でプールサイズを
> 縮めてください ([docs/web-config.md](docs/web-config.md#wasm32-の-2gb-上限とメモリプール))。

## 配信

pthread (SharedArrayBuffer) を使うので、配信サーバは次のヘッダを**必ず**返す必要があります。

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

`web/serve.py` と、ステージングで生成する `serve.py` はこのヘッダを付けて配信する開発用サーバです。
itch.io は「SharedArrayBuffer support」を有効にすれば配信できます。

| やること | 説明 |
|---|---|
| COOP/COEP、大文字小文字を区別するサーバへの配信、web:// キャッシュ (OPFS) のクリア | [docs/web-hosting.md](docs/web-hosting.md) |
| セーブデータの保存先と識別名 (`-orgname` / `-appname`) — **リリース前に必ず確認** | [docs/web-save-data.md](docs/web-save-data.md) |
| 起動中のローディング表示と「クリックでスタート」(オーディオゲート) | [docs/web-loading.md](docs/web-loading.md) |
| ページの見た目を変える (カスタムシェル `web/shell.html`) | [docs/web-shell.md](docs/web-shell.md) |

## 機能の対応状況

| 機能 | 状態 |
|---|---|
| 描画 (WebGL) | ○ 既定は OGLDrawDevice (`?drawdevice=sdl` で SDLDrawDevice)。`-sFULL_ES3` でリンクしています |
| スレッド (Timer / サウンド / 画像ロード) | ○ pthread + SharedArrayBuffer |
| TJS 例外 | ○ `-fwasm-exceptions` (必須。外すと TJS のエラーで即 abort します) |
| 静的プラグイン | ○ csvParser / getSample / json / KAGParserEx / layerExBTOA / layerExImage / layerExRaster / layerExVector / saveStruct / scriptsEx / shrinkCopy / getLangName / textrender / tjsDataPack / tlgSliceLoader / psbfile / extrans / extNagano |
| Elements ダイアログ | ○ overlay 系に加えて**モーダル系 (showModal\*) も動きます**。既定の Asyncify は全ブラウザで動作 (`-DKRKRZ_WEB_ASYNC_BACKEND=JSPI` で JSPI 版。Chrome/Edge 137 以降に限ります) |
| セーブデータ (`user://`) | ○ IndexedDB へ自動で永続化します。リロード・再起動をまたいで残ることを確認済み ([docs/web-save-data.md](docs/web-save-data.md)) |
| 動画 (VideoOverlay) | ○ ブラウザの `<video>` で再生します ([docs/web-video.md](docs/web-video.md)) |
| コンソール REPL / DAP | × (devtools の REPL で代わりにします) |

プラグインの増減は `CMakeLists.txt` の `TVP_PLUGINS_STATIC` を編集します (wasm に DLL は無いので、全て
静的リンクです)。旧 V2Link 系のプラグインを足すときは、Main.cpp のフックが `ONV2LINK()` / `ONV2UNLINK()`
マクロの定義 (simplebinder.hpp) になっている必要があります。素の `onV2Link()` のままだと、複数のプラグインを
一緒に入れたときにシンボルが衝突します。

## 開発用の機能

- **devtools コンソール = TJS REPL** — F12 → Console で任意の TJS 式を評価できます (MASTER ビルドには入りません)

  ```js
  tjs('System.versionString')
  tjs('Debug.message("hello")')
  ```

- **ツール** — ステージング (`stage_web.py`)、web:// のマニフェスト生成 (`gen_manifest.py`)、
  簡易 XP3 アーカイバ (`xp3pack.py`)、静的ホストへの埋め込み用の配置 (`stage_docs.py`)。
  [docs/web-tools.md](docs/web-tools.md)

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/web-build.md](docs/web-build.md) | リソースのサイドカー化、サンプル (データ埋め込み構成) のビルド、起動引数と URL パラメータ |
| [docs/web-config.md](docs/web-config.md) | プロジェクトフォルダのステージング、`web-config.json` の各項目、メモリプールの上限 |
| [docs/web-hosting.md](docs/web-hosting.md) | COOP/COEP、ファイル名の大文字小文字、web:// キャッシュ (OPFS) のクリア |
| [docs/web-save-data.md](docs/web-save-data.md) | セーブデータの永続化の仕組み、識別名、リリース時に把握しておく挙動 |
| [docs/web-loading.md](docs/web-loading.md) | 起動ローディング表示 (`loading.json`)、オーディオゲート |
| [docs/web-shell.md](docs/web-shell.md) | カスタムシェル `web/shell.html` の改変のしかた |
| [docs/web-video.md](docs/web-video.md) | 動画再生 (VideoOverlay) の実装と注意 |
| [docs/web-tools.md](docs/web-tools.md) | `tools/` のスクリプト |

吉里吉里Z 本体のドキュメントは [公開サイト](https://wamsoft.github.io/krkrz_dev/) にあります。

## ライセンス

このリポジトリのライセンスは吉里吉里Z 本体に準じます。

ビルド時に参照・取得するもの (吉里吉里Z 本体とプラグイン、SDL3、Emscripten、vcpkg で取得する依存ライブラリ
など) は、それぞれのライセンスに従います。配布物に必要なライセンスの表記は、使ったエンジン・プラグイン・
ライブラリに合わせてタイトル側で同梱してください。
