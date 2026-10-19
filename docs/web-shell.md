# カスタムシェル (web/shell.html)

`web/shell.html` は、生成される `krkrz.html` のひな形です。emscripten の既定のシェルは使わず、
「黒背景 + canvas を中央にフィット + ローディング表示」だけのミニマルな構成にしてあります。
タイトルごとの見た目を変えるときは、このファイルを編集します (`LINK_DEPENDS` に登録済みなので、編集すれば
`make build` でリンクし直されます)。

## 改変するときに守ること

- **`{{{ SCRIPT }}}`** — emcc がスクリプトタグに置き換えるプレースホルダです。body の末尾に必ず残して
  ください (無いと JS がロードされません)
- **`<canvas id="canvas">` と `Module.canvas`** — SDL の描画先です。id とプロパティの設定をセットで
  維持してください
- **`Module.setStatus(text)`** — データのダウンロードの進み具合などが text で流れてきます。ローディング UI の
  更新に使います。空文字が来たら非表示にします。`onRuntimeInitialized` でも畳んでいます (実行開始 =
  ロード完了)

## カスタムの起点

- **タイトル / 背景**: `<title>` と CSS (`html, body { background: ... }`)
- **ローディングの演出**: `#loading` ブロック (スピナー + `#status` テキスト)。画像や進捗バーへの差し替えは
  `Module.setStatus` の実装を変えます。背景画像や文字は `resource/loading.json` でも差し替えられます
  ([web-loading.md](web-loading.md))
- **フィット表示**: canvas の CSS (`max-width/max-height + auto`) でアスペクト比を保ったフィットにしています。
  URL に `?fit=0` を付けると等倍 (CSS ピクセル) + スクロール表示 (`body.nofit`) になります。CSS で縮小しても
  マウス座標は SDL 側で補正されるので、ゲームの座標系は変わりません
- **右クリック**: canvas の `oncontextmenu` で既定のメニューを抑止しています

`web/pre.js` は生成 JS の先頭に埋め込まれるフックの側で、役割は起動引数 / devtools の REPL `tjs()` / 早期の
エラーの title へのミラーです。シェル (ページ側) と pre.js (Module 側) で役割を分けています。
