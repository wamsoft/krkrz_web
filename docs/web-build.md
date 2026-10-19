# ビルドの詳細 — リソース・サンプルのデータ・起動引数

共有バイナリのビルドと、サンプル (データ埋め込み構成) のビルドオプション、起動引数の組み立て方を説明します。
基本の手順は [README](../README.md#ビルドと実行) を参照してください。

## 出力

`make build` の出力は `build/wasm32-emscripten/$BUILD_TYPE/krkrz/` の
`krkrz.html` / `krkrz.js` / `krkrz.wasm` / `krkrz.data` の 4 ファイルと、下のサイドカーです。
これらを COOP/COEP ヘッダ付きで配信すれば、そのまま動きます ([web-hosting.md](web-hosting.md))。

## リソースは wasm に埋め込みません (共有バイナリ + 配信サイドカー)

config.cf / messages.json / フォント / SysInitScript.tjs などのエンジンのリソースは wasm 本体に埋め込まず、
**配信ファイル (サイドカー)** として出力の隣に置きます。

- `resource/` (実体) と `resource.list` (`resource/` のファイル名一覧の JSON。`resource/` の兄弟として
  サイトの直下に置きます)
- `web/pre.js` が起動前 (`preRun`) にこれらを fetch して MEMFS の `/resource` に載せ、エンジンは
  `ResourcePath` = `file://./resource/` から同期で読みます

これにより **wasm 本体はリソースに依存せず、タイトル間で完全に共有**できます。タイトルの差し替えは
**サイドカーの差し替えだけ (リンクし直し不要)** で済みます。文字コード (`readencoding`) も
`/resource/config.cf` から起動時に読むので、タイトル別の charset は起動引数なしで切り替わります。

埋め込みに戻すには `-DKRKRZ_EMSCRIPTEN_EMBED_RESOURCE=ON` (core 側のオプション) を指定します。

## サンプル (データ埋め込み構成)

> この節はサンプル / データ埋め込み構成 (`make run` のサンプルランチャ) の説明です。
> **タイトルの配信は [プロジェクトフォルダのステージング](web-config.md) の web:// オンデマンド方式を
> 勧めます** (共有バイナリをリンクし直さず、データを変えてもサイドカーを置き直すだけで済みます)。

ゲームデータは `-DKRKRZ_WEB_DATA_DIR=<folder>` で指定したフォルダが、ビルド時に `tools/xp3pack.py` で
**1 つの xp3 にパック**され、`/data.xp3` として preload されます (既定は core 同梱のサンプルデータ)。
エンジンは起動時に `data.xp3` を自動で見つけて、プロジェクトとして開きます (リリースの形態)。
**データだけを変えた場合もリンクし直しが必要**です (`make build` で再パックされます)。

```bash
CMAKEOPT='-DKRKRZ_WEB_DATA_DIR=/path/to/game/data' make prebuild build
```

開発中にファイルの構成を devtools からそのまま見たいときは、`-DKRKRZ_WEB_DATA_XP3=OFF` でフォルダを
直接 preload (`/data`) する構成に切り替わります。どちらの構成かは pre.js が起動時に自動で判別します。

## 起動引数と URL パラメータ

起動引数は `web/pre.js` が URL パラメータとビルド構成 (`webconfig.js`) から組み立て、`Module['arguments']`
に設定します。既定は `['-drawdevice=ogl', '-drawthread=1']` です。

描画デバイスの既定が OGLDrawDevice なのは、SDLDrawDevice (SDL_Renderer) を既定にすると、GL を使う画面
(Canvas / Texture の OGLDrawDevice) との間で切り替えるたびに、同じ canvas 上のただ 1 つの WebGL
コンテキストを取り合うためです。OGLDrawDevice にそろえると、GL コンテキストを破棄せずに使い回すだけになり、
この問題が起きません (2D 描画も OGLDrawDevice で正常に動きます)。

URL の次のパラメータを解釈します。

| パラメータ | 意味 |
|---|---|
| `?webbase=` | web:// の配信元 |
| `?webproject=1` | web:// のプロジェクトとして起動 |
| `?readencoding=` | 読み込みの文字コード (`-readencoding=`) |
| `?language=` | 表示言語 (`?language=en` → `-language=en`。無ければブラウザの言語) |
| `?sample=` | サンプルデータの中のフォルダを指定して起動 |
| `?drawdevice=` | 描画デバイス (`sdl` / `ogl` / `sdlogl`。既定 `ogl`。`sdl` で従来の SDLDrawDevice) |

ほかに、診断用のパラメータ (`?opfsclear=1` / `?prefetch=0` / `?loading=0` / `?audiogate=0` / `?fit=0`) が
あります。それぞれ [web-hosting.md](web-hosting.md)、[web-config.md](web-config.md)、
[web-loading.md](web-loading.md)、[web-shell.md](web-shell.md) で説明しています。

タイトルのサイト ([プロジェクトフォルダのステージング](web-config.md)) では、`webconfig.js` に
`KRKRZ_WEB_DEFAULT_WEBBASE` / `KRKRZ_WEB_DEFAULT_ARGS` を書き込むことで、**引数なしの URL でタイトルを
直接起動**します。
