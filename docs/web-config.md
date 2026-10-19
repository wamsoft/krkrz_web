# web-config.json とプロジェクトフォルダのステージング

プロジェクトフォルダの `web-config.json` で、表示名・リソース・起動引数と、配信する資材 (`assetPack`) を
指定します。`tools/stage_web.py` がこのファイルを読んでサイトを組みます。

`assetPack` とパス文字列の `${...}` 展開は、krkrz_android / krkrz_ios / krkrz_linux / krkrz_gdk と共通の
書式です。共通部分の説明は公開サイトの
[外枠リポジトリの共通設定 (cmake / assetPack)](https://wamsoft.github.io/krkrz_dev/topics/core/platform_config/)
にあります。このページはブラウザ版だけの項目と、ブラウザ版での動き方を説明します。ブラウザ版は共有バイナリを
使い、プラグインは全て静的リンクするので、`cmake` の節はありません。

## ステージング (PROJECT_DIR)

krkrz_android の `PROJECT_DIR` 方式のブラウザ版です。**共有バイナリ (リンクし直し不要)** を前提に、
プロジェクトフォルダを指定すると、共有バイナリをコピーしてタイトルの差分をサイドカーとして置き、
**プロジェクトフォルダの下に自己完結の実行用サイト**を出力します。

前提として、先に一度だけ共有バイナリをビルドしておきます (`make prebuild build`。タイトルに依存しません)。

```bash
make PROJECT_DIR=/path/to/game web
#   = python tools/stage_web.py /path/to/game
```

やること (cmake は呼ばないので、リンクし直しは一切ありません):

1. タイトルの `web-config.json` (無ければ慣例で補います) を読みます
2. 共有バイナリ (`krkrz.js` / `krkrz.wasm` / `krkrz.data`、`krkrz.html` → `index.html`) を
   `${PROJECT_DIR}/build/web/site/` へ置きます
3. タイトルの差分を**サイドカー**として置きます
   - `resource/` + `resource.list` … タイトルの config.cf (charset) / messages / フォント
   - `webconfig.js` … 起動時の構成 (`webbase=gamedata/` / プールサイズなどの起動引数)
4. **data は preload せず、web:// でオンデマンド配信します** (`serve.py` が `/gamedata/` でタイトルのデータを
   配信し、autopath 用のマニフェスト `krkrz_files.json` を注入します)

配置は**ハードリンクを自動で判定**します。サイトと元のファイルが同じドライブならハードリンク (実体を複製せず
即時)、別のドライブなどでハードリンクできないときは、ファイル単位で自動的にコピーに切り替わります
(binary / resource / data のすべてが対象です。手動のフラグは要りません。2 回目以降はサイズと更新時刻が同じ
ファイルを飛ばす増分ステージングです)。出力したサイトは自己完結 (絶対パスを参照しない) なので、フォルダごと
コピーしても、別のホストへアップロードしても動きます。

**ビルド + ステージング + 起動まで一括**で行うなら `run` を使います。

```bash
make PROJECT_DIR=/path/to/game run    # build → stage → 生成した serve.py で起動 (引数なしの URL)
#   → http://localhost:8100/   (web-config.json の port)
```

ステージングだけ (サイトを作り直すだけ) なら `make PROJECT_DIR=... web` です。
生成された `serve.py` を直接実行してもかまいません。

```bash
python "${PROJECT_DIR}/build/web/site/serve.py"   # → http://localhost:8100/
```

`stage_web.py` のオプションは [web-tools.md](web-tools.md) にあります。

## web-config.json (全て任意。Android の app-config.json とは別のファイル)

`assetPack.sources` は **krkrz_android の app-config.json と同じ書式**で、複数のソースを**マージ**して
`gamedata/` (web:// で配信するもの) を組みます。

```jsonc
{
  "name":     "mygame",            // 表示名 (既定: フォルダ名)
  "resource": "setup/nxresource",  // config.cf/messages/フォント (既定: setup/nxresource)
  "port":     8100,                // 生成する serve.py の既定ポート
  "args": [                        // config.cf より優先する起動引数 (下のプール上限など)
    "-bitmappoolsize=640", "-filepoolsize=320",
    "-soundpoolsize=96",   "-krkrzpoolsize=128"
  ],
  "lowercase": false,              // true で gamedata の配置先を ASCII 小文字にする
                                   // (serve.py を使わない case-sensitive な静的配信向け。web-hosting.md)
  "assetPack": {
    "baseFolder": "${PROJECT_DIR}",  // 相対 from の基準 (既定: PROJECT_DIR)。
                                     // ${PROJECT_DIR}/${KRKRZ_BASE}/${BUILD_SYSTEM_DIR}/環境変数 を展開
    "sources": [
      // 起動系のフォルダは prefetch で先読み (起動後にバックグラウンドで OPFS へ)
      { "type": "mirror", "from": "data/main",   "to": "main",   "delivery": "prefetch" },
      { "type": "mirror", "from": "data/system", "to": "system", "delivery": "prefetch" },
      { "type": "mirror", "from": "data", "to": "",     // type: mirror(サブツリー保持)/flatten(階層を潰す)
        "include": ["**/*"], "exclude": ["**/*.bak", "**/*.psd"] },
      // 例: 追加のソースをマージ (別フォルダ / 共通アセット / xp3 を平坦化 など)
      { "type": "flatten", "from": "archive", "include": ["*.xp3"] }
    ]
  }
}
```

| キー | 内容 |
|---|---|
| `name` | 表示名 (既定: フォルダ名) |
| `resource` | config.cf / messages / フォントのフォルダ (既定: `setup/nxresource`) |
| `port` | 生成する `serve.py` の既定ポート (既定: 8100) |
| `args` | config.cf より優先する起動引数。`webconfig.js` の `KRKRZ_WEB_DEFAULT_ARGS` に書き込まれます |
| `lowercase` | `true` で `gamedata/` の配置先を ASCII 小文字にします ([web-hosting.md](web-hosting.md#ファイル名の大文字小文字-case-sensitive-なサーバへの配信)) |
| `assetPack` | 資材の取り込み (外枠共通の書式) |

`assetPack` についての補足:

- `to` を省略したときの既定は app-config と同じです: mirror + 相対 → `from` と同じ / mirror + 絶対 →
  `from` の末尾のフォルダ名 / flatten → ルート。**gamedata のルートに置きたいときは `"to": ""`** を明示します
- `include` / `exclude` は Ant 風のグロブ (`**/*`, `*.xp3`, `**/*.bak`) です。配置先が重なったときは先に
  書いたものが勝ちます
- `delivery` (ブラウザ版だけの項目): `"on-demand"` (既定) / `"prefetch"`。prefetch のソースのファイルは
  `krkrz_prefetch.json` に列挙され、**起動後に pre.js がバックグラウンドで fetch して OPFS に保存**します
  (同時に 2 本。`?prefetch=0` で無効。進捗は `Module.krkrzPrefetch`)。以後の web:// オンデマンドアクセスは、
  初回のプレイでもローカルにヒットします。同じファイルが複数のソースに載る場合は delivery も先勝ちなので、
  **prefetch のソースは全体の mirror より先に**書きます。動画は `<video>` の URL 直接ストリーミングで OPFS を
  通らないので、prefetch の対象にしません
- 旧書式 (`"data": "data"`, `"exclude": [".bak", ".psd"]`) も後方互換で受け付けます (単一の mirror `to=""`
  に展開します。拡張子の指定は `**/*<ext>` に変換します)
- `manifest` (`gamedata.krkrz_files.json`) は**組み上がった `gamedata/` から**生成されるので、マージ / 除外の
  結果がそのまま autopath に反映されます

## wasm32 の 2GB 上限とメモリプール

Bitmap / File / Krkrz / Sound の各プールの合計が wasm32 の 2GB を超えると、起動時に `Aborted(OOM)` に
なります。既定のプールは bitmap 1024 + file 512 + krkrz 256 + sound 128 = 1920MB で、すでに限界に近く、
タイトルの config.cf が大きめ (たとえば bitmap 1280 + file 384 = 合計 2048MB) だと超えてしまいます。
タイトルの `web-config.json` の `"args"` でプールサイズを縮めて指定してください (コマンドラインは config.cf
より優先されます)。上の例 (合計 1184MB) は 2GB に余裕を残す構成です。
