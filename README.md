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
make build       # ビルド
make run         # ビルド + http://localhost:8080/krkrz.html で配信 (PORT= で変更)
make serve       # サーバのみ起動
```

出力は `build/wasm32-emscripten/$BUILD_TYPE/krkrz/` 配下の
`krkrz.html` / `krkrz.js` / `krkrz.wasm` / `krkrz.data` の 4 ファイル。
この 4 つを COOP/COEP ヘッダ付きで配信すればそのまま動く。

ゲームデータは `-DKRKRZ_WEB_DATA_DIR=<folder>` で指定したフォルダが
`krkrz.data` にパックされ、MEMFS の `/data` に preload される
(既定は core 同梱のサンプルデータ)。**データだけ変更した場合もリリンクが必要**。

```bash
CMAKEOPT='-DKRKRZ_WEB_DATA_DIR=/path/to/game/data' make prebuild build
```

起動引数は `web/pre.js` の `Module['arguments']` で指定する。
既定は `['-drawdevice=sdl', '-drawthread=1', '/data']`。

## 配信時の注意 (COOP/COEP)

pthread (SharedArrayBuffer) を使うため、配信サーバは以下のヘッダが**必須**:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

`web/serve.py` はこれを付けて配信する開発用サーバ。itch.io は
「SharedArrayBuffer support」を有効にすれば配信できる。

## カスタムシェル (web/shell.html)

生成される `krkrz.html` の雛形。emscripten 既定シェルは使わず、
「黒背景 + canvas 中央フィット + ローディング表示」だけのミニマル構成に
してある。案件ごとの見た目のカスタムはこのファイルを編集する
(`LINK_DEPENDS` 登録済みなので、編集すれば `make build` でリリンクされる)。

### 改変時に守ること

- **`{{{ SCRIPT }}}`** — emcc がスクリプトタグに置換するプレースホルダ。
  body 末尾に必ず残すこと (無いと JS がロードされない)
- **`<canvas id="canvas">` と `Module.canvas`** — SDL の描画先。
  id とプロパティ設定をセットで維持すること
- **`Module.setStatus(text)`** — データダウンロード進捗などが text で
  流れてくる。ローディング UI の更新に使う。空文字が来たら非表示にする。
  `onRuntimeInitialized` でも畳んでいる (実行開始 = ロード完了)

### カスタムの起点

- **タイトル/背景**: `<title>` と CSS (`html, body { background: ... }`)
- **ローディング演出**: `#loading` ブロック (スピナー + `#status` テキスト)。
  画像や進捗バーへの差し替えは `Module.setStatus` の実装を変える
- **フィット表示**: canvas の CSS (`max-width/max-height + auto`) が
  アスペクト維持フィットを実現。`?fit=0` を URL に付けると等倍
  (CSS ピクセル) + スクロール表示 (`body.nofit`)。
  CSS 縮小してもマウス座標は SDL 側で補正されるためゲーム座標系は不変
- **右クリック**: canvas の `oncontextmenu` で既定メニューを抑止している

`web/pre.js` は生成 JS の先頭に埋め込まれるフック側で、役割は
起動引数 / IDBFS (`/save`) マウント / devtools REPL `tjs()` /
早期エラーの title ミラー。シェル (ページ側) と pre.js (Module 側) で
役割分担している。

## devtools コンソール = TJS REPL

F12 → Console で任意の TJS 式を評価できる (MASTER ビルドには入らない):

```js
tjs('System.versionString')
tjs('Debug.message("hello")')
```

## 機能の対応状況

| 機能 | 状態 |
|---|---|
| 描画 (SDLDrawDevice → WebGL) | ○ 既定。`-sFULL_ES3` リンク済で OGL 系も試験可 |
| スレッド (Timer/サウンド/画像ロード) | ○ pthread + SharedArrayBuffer |
| TJS 例外 | ○ `-fwasm-exceptions` (必須。外すと TJS エラーで即 abort) |
| 静的プラグイン | ○ csvParser / extNagano / extrans / json / KAGParserEx / saveStruct / scriptsEx |
| Elements ダイアログ | △ overlay 系 (showJson/showFile) のみ。モーダル系は実行時エラー |
| セーブデータ | △ `/save` を IDBFS マウント済。**書込後の永続化フラッシュは未実装** (リロードで消える) |
| 動画 (VideoOverlay) | × KRKRZ_USE_MOVIE=OFF (スタブ) |
| コンソール REPL / DAP | × (devtools REPL で代替) |

プラグインの増減は `CMakeLists.txt` の `TVP_PLUGINS_STATIC` を編集する
(wasm に DLL は無いので全て静的リンク)。旧 V2Link 系プラグインを追加する
場合、Main.cpp のフックが `ONV2LINK()`/`ONV2UNLINK()` マクロ定義
(simplebinder.hpp) になっている必要がある — 素の `onV2Link()` のままだと
複数プラグイン同居時にシンボル衝突する。

## ライセンス

吉里吉里Z 本体に準ずる。
