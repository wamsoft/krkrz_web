# 配信 — COOP/COEP・大文字小文字・web:// キャッシュ

ブラウザ版をサーバに置いて配信するときに必要なことと、web:// のキャッシュの扱いを説明します。

## 配信時の注意 (COOP/COEP)

pthread (SharedArrayBuffer) を使うので、配信サーバは次のヘッダを**必ず**返す必要があります。

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

`web/serve.py` はこれを付けて配信する開発用サーバです。itch.io は「SharedArrayBuffer support」を有効に
すれば配信できます。ヘッダを設定できない静的ホスト (GitHub Pages など) に置く場合は、coi-serviceworker で
クライアント側からヘッダを注入する `tools/stage_docs.py` を使います ([web-tools.md](web-tools.md))。

## ファイル名の大文字小文字 (case-sensitive なサーバへの配信)

web:// のリクエスト URL は **ASCII 小文字に正規化**されます (autopath のマニフェストが小文字であることに
加えて、エンジンの URL 生成でも小文字にして OPFS のキーを統一しています)。ファイル名自体はそのままでかまい
ませんが、**配信サーバは小文字のリクエストを実際のファイルへ解決できる必要があります**。

- 同梱の `serve.py` (web/ と、ステージングで生成するサイトのもの) は、実際のファイルの一覧と照らし合わせて
  解決します (Linux などの case-sensitive な FS でもそのまま動きます)
- Windows 系のサーバや itch.io などの case-insensitive な配信は、そのままで問題ありません
- 素の nginx / S3 など case-sensitive な静的配信に置く場合は、**ステージング時の小文字化オプション**を
  使います: web-config.json に `"lowercase": true` (または `stage_web.py --lowercase`)。gamedata の配置先の
  パスが ASCII 小文字になり、実際のファイル名 = リクエスト URL になるので、サーバ側での解決が要らなく
  なります (元のデータのファイル名は変えません。サイト側の名前だけが変わります)

## web:// キャッシュ (OPFS) のクリア

web:// で取得したファイルは **OPFS** (Origin Private File System) に永続的にキャッシュされます (キーは
SHA-256(URL) ベース)。ETag の検証はしないので、アセットを更新しても古いキャッシュが使われ続けます (本番では
cache busting = ファイル名 / URL を変えて運用します)。開発中や不整合が起きたときは、次の方法でクリアします。

| 方法 | 効果 |
|---|---|
| URL に `?opfsclear=1` を付けて開く | OPFS (web:// のキャッシュ) を全て消して起動します。**推奨** |
| キー形式の版数の更新 (`.krkrz-cache-v2` マーカー) | 形式が変わった初回の起動で一度だけ自動で全クリアします (操作不要) |
| DevTools → Application → Storage → Clear site data | OPFS も消えますが、**IndexedDB (セーブデータ) も消える**ので注意してください |

セーブデータ (`user://` = IndexedDB) は OPFS とは別の領域で、`?opfsclear=1` では消えません
([web-save-data.md](web-save-data.md))。
