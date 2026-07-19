# krkrz_web

吉里吉里Z (Kirikiri Z) を **Emscripten (wasm32) でブラウザ上で動かす**ための
プロジェクトテンプレート。

このリポジトリは「ガワ」のみで、エンジン本体・プラグインのソースは
`krkrz_dev` (umbrella リポジトリ) から参照する。`krkrz_android` (Android 版)
と同じ外枠方式。

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

> **リソースは wasm に埋め込まない (共有バイナリ + 配信サイドカー)**
> config.cf / messages.json / フォント / SysInitScript.tjs 等のエンジンリソースは
> wasm 本体に埋め込まず、**配信ファイル (サイドカー)** として出力隣に置く:
> `resource/` (実体) + `resource.list` (`resource/` のファイル名一覧 JSON。`resource/`
> の兄弟として site 直下に置く)。`web/pre.js` が起動前 (`preRun`) にこれらを fetch して
> MEMFS `/resource` に載せ、エンジンは `ResourcePath` = `file://./resource/` から同期読み
> する (NX の `file://basepath/resource` と同型)。これにより **wasm 本体はリソース非依存
> = 案件間で完全に共有**でき、案件差し替えは**サイドカーの差し替えだけ (relink 不要)**。
> 文字コード (`readencoding`) も `/resource/config.cf` から起動時に読むため、案件別
> charset は起動引数不要で切り替わる。埋め込みに戻すには
> `-DKRKRZ_EMSCRIPTEN_EMBED_RESOURCE=ON` (core 側オプション)。

ゲームデータは `-DKRKRZ_WEB_DATA_DIR=<folder>` で指定したフォルダが
ビルド時に `tools/xp3pack.py` で **1 つの xp3 にパック**され、`/data.xp3`
として preload される (既定は core 同梱のサンプルデータ)。エンジンは起動時に
`data.xp3` を自動発見してプロジェクトとして開く (リリース形態)。
**データだけ変更した場合もリリンクが必要** (`make build` で再パックされる)。

```bash
CMAKEOPT='-DKRKRZ_WEB_DATA_DIR=/path/to/game/data' make prebuild build
```

開発時にファイル構成を devtools からそのまま見たい場合は
`-DKRKRZ_WEB_DATA_XP3=OFF` でフォルダ直接 preload (`/data`) に切り替わる。
どちらの構成かは pre.js が起動時に自動判別する。

> この節はサンプル / データ埋め込み構成 (`make run` のサンプルランチャ) の説明。
> **実案件の配信は下記「案件ごとのステージング (PROJECT_DIR)」の web:// オンデマンド方式を推奨**する
> (共有バイナリを relink せず、データ変更もサイドカー再配置だけで済む)。

起動引数は `web/pre.js` が URL パラメータ + ビルド構成 (`webconfig.js`) から組み立て、
`Module['arguments']` に設定する。既定は `['-drawdevice=sdl', '-drawthread=1']`。
URL の `?webbase=` / `?webproject=1` / `?readencoding=` / `?sample=` / `?drawdevice=` を解釈し、
案件サイト (下記 PROJECT_DIR ステージング) では `KRKRZ_WEB_DEFAULT_WEBBASE` /
`KRKRZ_WEB_DEFAULT_ARGS` を焼き込むことで**引数なし URL で案件を直接起動**する。

## 案件ごとのステージング (PROJECT_DIR)

`krkrz_android` の `PROJECT_DIR` 方式の web 版。**共有バイナリ (relink 不要)** を前提に、
案件フォルダを指定すると共有バイナリをコピー + 案件差分をサイドカー配置し、
**案件フォルダ配下に自己完結の実行用サイトを出力**する。

前提: 先に一度だけ共有バイナリをビルドしておく (`make prebuild build`。案件非依存)。

```bash
make PROJECT_DIR=/path/to/game web
#   = python tools/stage_web.py /path/to/game
```

やること (cmake は呼ばない = relink 一切なし):

1. 案件の `web-config.json` (無ければ慣例で補完) を読む
2. 共有バイナリ (`krkrz.js` / `krkrz.wasm` / `krkrz.data`、`krkrz.html`→`index.html`) を
   `${PROJECT_DIR}/build/web/site/` へ配置
3. 案件差分を**サイドカー**として配置:
   - `resource/` + `resource.list` … 案件の config.cf(charset) / messages / フォント
   - `webconfig.js` … 起動時構成 (`webbase=gamedata/` / プールサイズ等の起動引数)
4. **data は preload せず web:// でオンデマンド配信** (`serve.py` が `/gamedata/` で
   案件データを配信し、autopath 用マニフェスト `krkrz_files.json` を注入する)

配置は **ハードリンク自動判定**: site と元ファイルが同一ドライブならハードリンク
(実体複製なし・即時)、別ドライブ等でハードリンク不可ならファイル単位で自動的に
実コピーにフォールバックする (binary / resource / data すべて対象。手動フラグ不要。
2 回目以降はサイズ+mtime 一致分をスキップする増分ステージング)。出力 site は
自己完結 (絶対パス参照なし) なのでフォルダごとコピー / 別ホストへアップロードしても動く。

**ビルド + ステージング + 起動まで一括**するなら `run`:

```bash
make PROJECT_DIR=/path/to/game run    # build → stage → 生成 serve.py で起動 (引数なし URL)
#   → http://localhost:8100/   (web-config.json の port)
```

ステージングのみ (site を再生成するだけ) なら `make PROJECT_DIR=... web`。
生成された `serve.py` を直接実行してもよい:

```bash
python "${PROJECT_DIR}/build/web/site/serve.py"   # → http://localhost:8100/
```

### web-config.json (すべて任意 / Android の app-config.json とは別ファイル)

`assetPack.sources` は **krkrz_android の app-config.json と同じ書式**で、複数ソースを
**マージ**して `gamedata/` (web:// 配信) を組む。

```jsonc
{
  "name":     "mygame",            // 表示名 (既定: フォルダ名)
  "resource": "setup/nxresource",  // config.cf/messages/フォント (既定: setup/nxresource)
  "port":     8100,                // 生成 serve.py の既定ポート
  "args": [                        // config.cf より優先の起動引数 (下記プール上限等)
    "-bitmappoolsize=640", "-filepoolsize=320",
    "-soundpoolsize=96",   "-krkrzpoolsize=128"
  ],
  "assetPack": {
    "baseFolder": "${PROJECT_DIR}",  // 相対 from の基準 (既定: PROJECT_DIR)。
                                     // ${PROJECT_DIR}/${KRKRZ_BASE}/${BUILD_SYSTEM_DIR}/環境変数 を展開
    "sources": [
      // 起動系フォルダは fast-follow 先読み (起動後にバックグラウンドで OPFS へ)
      { "type": "mirror", "from": "data/main",   "to": "main",   "delivery": "prefetch" },
      { "type": "mirror", "from": "data/system", "to": "system", "delivery": "prefetch" },
      { "type": "mirror", "from": "data", "to": "",     // type: mirror(サブツリー保持)/flatten(階層を潰す)
        "include": ["**/*"], "exclude": ["**/*.bak", "**/*.psd"] },
      // 例: 追加ソースをマージ (別フォルダ / 共通アセット / xp3 を平坦化 など)
      { "type": "flatten", "from": "archive", "include": ["*.xp3"] }
    ]
  }
}
```

- `to` 省略時の既定は app-config と同じ: mirror+相対 → `from` と同じ / mirror+絶対 →
  `from` の末尾フォルダ名 / flatten → ルート。**gamedata ルートに置きたいときは `"to": ""`** を明示。
- `include`/`exclude` は Ant 風グロブ (`**/*`, `*.xp3`, `**/*.bak`)。重複配置先は先勝ち。
- `delivery`: `"on-demand"` (既定) / `"prefetch"`。prefetch のソースのファイルは
  `krkrz_prefetch.json` に列挙され、**起動後に pre.js がバックグラウンドで fetch → OPFS
  保存**する (同時 2 本、`?prefetch=0` で無効、進捗は `Module.krkrzPrefetch`)。以後の
  web:// オンデマンドアクセスは初回プレイでもローカルヒットになる。同一ファイルが複数
  ソースに載る場合は delivery も先勝ちなので、**prefetch ソースは全体 mirror より先に**書く。
  動画は `<video>` の URL 直接ストリーミングで OPFS を通らないため prefetch 対象にしない。
- 旧書式 (`"data": "data"`, `"exclude": [".bak", ".psd"]`) も後方互換で受ける
  (単一 mirror `to=""` に展開。拡張子指定は `**/*<ext>` に変換)。
- `manifest` (`gamedata.krkrz_files.json`) は**組み上がった `gamedata/` から**生成されるので、
  マージ / 除外の結果がそのまま autopath に反映される。

> **⚠ wasm32 の 2GB 上限とメモリプール**
> Bitmap/File/Krkrz/Sound の各プール合計が wasm32 の 2GB を超えると起動時に
> `Aborted(OOM)` になる。既定プールは bitmap 1024 + file 512 + krkrz 256 +
> sound 128 = 1920MB で既に限界に近く、案件 config.cf が大きめ (例えば
> bitmap 1280 + file 384 = 合計 2048MB) だと超過する。案件の `web-config.json`
> の `"args"` でプールサイズを縮小指定すること (コマンドラインは config.cf より
> 優先される)。上の例 (合計 1184MB) は 2GB に余裕を残す構成。

## 配信時の注意 (COOP/COEP)

pthread (SharedArrayBuffer) を使うため、配信サーバは以下のヘッダが**必須**:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

`web/serve.py` はこれを付けて配信する開発用サーバ。itch.io は
「SharedArrayBuffer support」を有効にすれば配信できる。

### ファイル名の大文字小文字 (case-sensitive サーバへの配信)

web:// のリクエスト URL は **ASCII 小文字に正規化**される (autopath マニフェスト
が小文字であることに加え、エンジンの URL 生成でも小文字化して OPFS キーを統一
している)。ファイル名自体はそのままでよいが、**配信サーバは小文字リクエストを
実ファイルへ解決できる必要がある**:

- 同梱 `serve.py` (web/ + 案件 site 生成分) は実ファイル一覧との照合で解決する
  (Linux 等の case-sensitive FS でもそのまま動く)
- Windows 系サーバ / itch.io 等の case-insensitive な配信はそのままで OK
- 素の nginx / S3 等 case-sensitive な静的配信に置く場合は、ファイル名を
  小文字に揃えてアップロードするか、小文字→実名の rewrite を用意すること

## web:// キャッシュ (OPFS) のクリア

web:// で取得したファイルは **OPFS** (Origin Private File System) に永続
キャッシュされる (キーは SHA-256(URL) ベース)。ETag 検証はしないので、
アセットを更新しても古いキャッシュが使われ続ける (本番は cache busting =
ファイル名/URL 変更で運用する)。開発中や不整合時のクリア手段:

| 方法 | 効果 |
|---|---|
| URL に `?opfsclear=1` を付けて開く | OPFS (web:// キャッシュ) を全消しして起動。**推奨** |
| キー形式の版数更新 (`.krkrz-cache-v2` マーカー) | 形式が変わった初回起動に一度だけ自動全クリア (操作不要) |
| DevTools → Application → Storage → Clear site data | OPFS も消えるが **IndexedDB (セーブデータ) も消える**ので注意 |

セーブデータ (`user://` = IndexedDB) は OPFS とは別領域で、`?opfsclear=1` では消えない。

## セーブデータの永続化と識別名 (リリース時の必須確認)

### 仕組み

`user://` への書き込みはブラウザの **IndexedDB** に自動永続化される。
チェーンは以下のとおりで、エンジン側・ページ側に追加コードは無い:

- CMakeLists.txt で `SDL_EMSCRIPTEN_PERSISTENT_PATH=/persist` を設定
  → SDL が起動前に `/persist` へ IDBFS を `autoPersist` 付きでマウントし、
  IndexedDB からの復元完了を**待ってから**エンジンを開始する
- `user://` (SDL_OpenUserStorage 経由) の実体は
  `/persist/<orgname>/<appname>/` 配下
- ファイルクローズ時の一括書き込み (`SDL_WriteStorageFile`) を IDBFS の
  autoPersist が検知し、自動で IndexedDB へ書き戻す

### orgname / appname の設定 (タイトル毎に必ず設定する)

保存場所の識別名は起動引数で決まる。`web/pre.js` の `Module['arguments']` に追加:

```js
Module['arguments'] = ['-drawdevice=sdl', '-drawthread=1',
                       '-orgname=yourbrand', '-appname=yourtitle', '/data'];
```

**未設定時の既定は `wamsoft` / `krkrz`**。IndexedDB は「オリジン
(ドメイン) 単位」なので、**同じドメインで複数タイトルを配信する場合、
識別名が同じだとセーブデータ領域が共有・衝突する**。リリース時は
タイトル毎に一意な組み合わせを必ず設定すること。

### リリース時に把握しておくべき挙動

- **保存はオリジン単位**: 配信ドメインを変える (移転する) と、識別名が
  同じでもセーブは引き継がれない
- **ユーザ操作で消える**: ブラウザの「サイトデータの削除」でセーブも消える。
  長期保持が重要なタイトルはセーブのエクスポート/インポート手段の提供を検討
- **プライベートブラウジング**: 保存できない・タブを閉じると消える場合がある
- 容量はブラウザのクォータ管理に従う (通常のセーブデータ量では問題にならない)

### 動作確認の手順 (devtools コンソール)

```js
// 書き込み (ストリームクローズ時に IndexedDB へ自動反映)
tjs('(Dictionary.saveStruct incontextof (%[v:42]))("user://./ptest.tjs")')
// → ページをリロード後:
tjs('Scripts.evalStorage("user://./ptest.tjs").v')   // → 42 が返れば OK
```

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
起動引数 / devtools REPL `tjs()` / 早期エラーの title ミラー。
シェル (ページ側) と pre.js (Module 側) で役割分担している。

## ツール

### tools/stage_web.py — PROJECT_DIR ステージング

上記「案件ごとのステージング」の実体。`make PROJECT_DIR=X web` から呼ばれる。

```bash
python tools/stage_web.py <PROJECT_DIR> [--data DIR] [--build-type Release] [--port N]
```

案件の `web-config.json` (無ければ慣例) を読み、**共有バイナリ (`make build` 済) をコピー +
案件差分をサイドカー配置** (cmake は呼ばない = relink なし) して
`${PROJECT_DIR}/build/web/site/` に site 一式 + `serve.py` + `README.md` + マニフェストを
出力する。配置はハードリンク自動判定 (別ドライブは copy に自動フォールバック)。
`--data DIR` で `assetPack` を無視して単一フォルダ配信に上書きできる (簡易テスト用)。

### tools/gen_manifest.py — web:// autopath マニフェスト生成

```bash
python tools/gen_manifest.py <srcdir> <outfile> [--exclude .bak .psd]
```

サーバ上のバラファイルはディレクトリ列挙ができないため、`web://` メディアの
`GetListAt` / `CheckExistentStorage` はこのマニフェスト (小文字・'/' 区切りの
パス配列 JSON) を参照する。`stage_web.py` が内部で呼ぶ。

### tools/xp3pack.py — 簡易 XP3 アーカイバ

```bash
python tools/xp3pack.py pack <srcdir> <out.xp3>   # フォルダをパック
python tools/xp3pack.py list <archive.xp3>        # 内容一覧
python tools/xp3pack.py extract <arc.xp3> <dir>   # 展開 + adler32 検証
```

krkrz core の読み込み実装準拠 (zlib 圧縮インデックス/セグメント対応、
画像・音声等の圧縮済み形式は自動で無圧縮格納)。暗号化には対応しない
(暗号化込みのパッカーは krkrtemplate/makeworld 側のツールを使用)。
wasm 実機で raw/zlib セグメント・サブディレクトリ・autopath 読み込みを検証済み。

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
| 静的プラグイン | ○ csvParser / getSample / json / KAGParserEx / layerExBTOA / layerExImage / layerExRaster / saveStruct / scriptsEx / shrinkCopy / getLangName / textrender / tjsDataPack / tlgSliceLoader / psbfile / extrans / extNagano |
| Elements ダイアログ | ○ overlay 系 + **モーダル系 (showModal*) も JSPI で動作**。要 JSPI 対応ブラウザ (Chrome 137+) |
| セーブデータ (`user://`) | ○ IndexedDB へ自動永続化 (SDL_EMSCRIPTEN_PERSISTENT_PATH + IDBFS autoPersist)。リロード/再起動をまたいで残存することを検証済み |
| 動画 (VideoOverlay) | ○ ブラウザネイティブ `<video>` 実装 (下記「動画再生」) |
| コンソール REPL / DAP | × (devtools REPL で代替) |

### 動画再生 (VideoOverlay)

wasm ではデコーダ (libvpx 等) を移植せず、**ブラウザの `<video>` 要素**に
デコード・音声出力・同期を任せる (core 側 `sdl3/base/WebMoviePlayer.cpp`)。
ブラウザが再生できる形式 (webm/VP8/VP9/AV1、環境により mp4/H.264) が対象。

- **mixer / overlay モード**: `<video>` を DOM オーバレイとして canvas に
  重ねて表示 (ウィンドウ内接フィット・中央寄せ = デスクトップ SDL 実装と
  同じ見た目)。`pointer-events: none` なので入力はエンジンに素通しされ、
  ムービー中のクリックスキップ等がそのまま機能する。
- **layer モード**: 非表示 `<video>` + requestVideoFrameCallback で
  フレームを RGBA 取得し、通常のレイヤ描画に合成する (デスクトップと同じ
  `layer1`/`layer2` API)。
- **ソース**: `web://` / `webnc://` は URL を直接 `<video>` に渡す
  (**ストリーミング再生**。fetch/OPFS を通らずメモリに全展開しない。
  シークは HTTP Range — serve.py は対応済。本番サーバも Range 対応推奨)。
  MEMFS / xp3 アーカイブ内のファイルは全読みして Blob URL で再生する
  (大きい動画は xp3 に入れず web:// 側に置くこと)。
- 状態遷移は `onStatusChanged("play"/"stop")` で通知される (再生終了で
  stop)。音量は `audioVolume` が `<video>` の volume にマップされる。
- 注意: ブラウザの autoplay ポリシーでユーザ操作前の音声付き再生は
  拒否されることがある (その場合は次のクリック/キー入力で自動再試行)。

プラグインの増減は `CMakeLists.txt` の `TVP_PLUGINS_STATIC` を編集する
(wasm に DLL は無いので全て静的リンク)。旧 V2Link 系プラグインを追加する
場合、Main.cpp のフックが `ONV2LINK()`/`ONV2UNLINK()` マクロ定義
(simplebinder.hpp) になっている必要がある — 素の `onV2Link()` のままだと
複数プラグイン同居時にシンボル衝突する。

## ライセンス

吉里吉里Z 本体に準ずる。
