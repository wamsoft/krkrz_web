# ツール (tools/)

`tools/` にある Python のスクリプトを説明します。

## tools/stage_web.py — プロジェクトフォルダのステージング

[プロジェクトフォルダのステージング](web-config.md#ステージング-project_dir) の実体です。
`make PROJECT_DIR=X web` から呼ばれます。

```bash
python tools/stage_web.py <PROJECT_DIR> [--data DIR] [--build-type Release] [--port N] [--lowercase]
```

タイトルの `web-config.json` (無ければ慣例) を読み、**共有バイナリ (`make build` 済み) をコピーし、タイトルの
差分をサイドカーとして置いて** (cmake は呼ばないので、リンクし直しはありません)、
`${PROJECT_DIR}/build/web/site/` にサイト一式 + `serve.py` + `README.md` + マニフェストを出力します。
配置はハードリンクを自動で判定します (別のドライブでは自動でコピーに切り替わります)。
`--data DIR` で `assetPack` を無視して、1 つのフォルダの配信に上書きできます (簡易テスト用)。
`--lowercase` は web-config.json の `"lowercase": true` と同じです ([web-hosting.md](web-hosting.md))。

## tools/gen_manifest.py — web:// autopath マニフェストの生成

```bash
python tools/gen_manifest.py <srcdir> <outfile> [--exclude .bak .psd]
```

サーバ上のばらのファイルはディレクトリを列挙できないので、`web://` メディアの `GetListAt` /
`CheckExistentStorage` はこのマニフェスト (小文字・'/' 区切りのパスの配列の JSON) を参照します。
`stage_web.py` が内部で呼びます。

## tools/xp3pack.py — 簡易 XP3 アーカイバ

```bash
python tools/xp3pack.py pack <srcdir> <out.xp3>   # フォルダをパック
python tools/xp3pack.py list <archive.xp3>        # 内容の一覧
python tools/xp3pack.py extract <arc.xp3> <dir>   # 展開 + adler32 の検証
```

krkrz core の読み込みの実装に準拠しています (zlib 圧縮のインデックス / セグメントに対応、画像・音声などの
圧縮済みの形式は自動で無圧縮で格納)。暗号化には対応しません (暗号化込みのパッカーは別のツールを使って
ください)。wasm の実機で raw / zlib のセグメント・サブディレクトリ・autopath の読み込みを確認済みです。

## tools/stage_docs.py — 静的ホストへの埋め込み用の配置

```bash
python tools/stage_docs.py <output_dir> [--build-type Release] [--coi-href HREF] [--no-coi] [--clean]
```

`make build` 済みの共有バイナリとサイドカーを、**coi-serviceworker を同梱した自己完結のディレクトリ**として
任意の出力先へ置きます。COOP/COEP ヘッダを設定できない静的ホスト (GitHub Pages など) やドキュメント
(mkdocs など) への埋め込み向けで、COOP/COEP は coi-serviceworker (`tools/coi-serviceworker.js`) でクライアント
側に注入します。データは preload (`krkrz.data` 同梱) をそのまま使います (web:// は使いません)。

| オプション | 意味 |
|---|---|
| `--build-type T` | 参照する共有バイナリ (Release (既定) / Debug) |
| `--coi-href HREF` | `index.html` に注入する coi-serviceworker の src を上書きします (既定は同じディレクトリの `coi-serviceworker.js` を同梱して参照) |
| `--no-coi` | coi-serviceworker を同梱も注入もしません (埋め込む側で隔離を用意する場合) |
| `--clean` | 出力先の既存の `krkrz.*` / `resource/` を消してから置きます |

iframe で埋め込むときは、**親のページも crossOriginIsolated** である必要があります (子の iframe の隔離は
親の隔離が前提です)。mkdocs なら `extra_javascript` にサイト直下の coi-serviceworker.js を足して、全ページに
適用します。
