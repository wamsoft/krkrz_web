# セーブデータの永続化と識別名 (リリース時に必ず確認)

`user://` に書いたセーブデータがブラウザのどこに保存されるかと、タイトルごとに設定する識別名を説明します。

## 仕組み

`user://` への書き込みは、ブラウザの **IndexedDB** に自動で永続化されます。流れは次のとおりです。

- core の自前の `main()` (sdl3/environ/main.cpp) が、起動時に `/persist` へ IDBFS を `autoPersist` 付きで
  マウントし、IndexedDB からの復元が終わるのを**待ってから**エンジンを開始します (パスは CMakeLists の
  `KRKRZ_EMSCRIPTEN_PERSISTENT_PATH`)。
  ※ SDL の `SDL_EMSCRIPTEN_PERSISTENT_PATH` の仕組みは `SDL_RunApp` の中にありますが、wasm は非同期 suspend
  のため自前の main() で `SDL_RunApp` を通りません。SDL 側のオプションは、`SDL_GetPrefPath` がこのパスの
  下を返すように、引き続き設定しています
- `user://` (SDL_OpenUserStorage 経由) の実体は `/persist/<orgname>/<appname>/` の下です
- ファイルを閉じるときの一括書き込み (`SDL_WriteStorageFile`) を IDBFS の autoPersist が検知し、自動で
  IndexedDB へ書き戻します

## orgname / appname の設定 (タイトルごとに必ず設定します)

保存場所の識別名は起動引数 `-orgname=` / `-appname=` で決まります。

- プロジェクトフォルダのステージングでは、`web-config.json` の `args` に足します
  (`webconfig.js` の `KRKRZ_WEB_DEFAULT_ARGS` に入り、`web/pre.js` が `Module['arguments']` に加えます)

  ```jsonc
  "args": ["-orgname=yourbrand", "-appname=yourtitle"]
  ```

- サンプル (データ埋め込み構成) のビルドでは、CMake のキャッシュ変数 `KRKRZ_WEB_DEFAULT_ARGS` に
  指定します (`-DKRKRZ_WEB_DEFAULT_ARGS="-orgname=yourbrand -appname=yourtitle"`)

**設定しないときの既定は `wamsoft` / `krkrz` です**。IndexedDB は「オリジン (ドメイン) 単位」なので、
**同じドメインで複数のタイトルを配信する場合、識別名が同じだとセーブデータの領域が共有され、衝突します**。
リリース時には、タイトルごとに一意な組み合わせを必ず設定してください。

## リリース時に把握しておく挙動

- **保存はオリジン単位です**: 配信ドメインを変える (移転する) と、識別名が同じでもセーブは引き継がれません
- **ユーザの操作で消えます**: ブラウザの「サイトデータの削除」でセーブも消えます。長く保持することが重要な
  タイトルは、セーブのエクスポート / インポートの手段の提供を検討してください
- **プライベートブラウジング**: 保存できない、またはタブを閉じると消える場合があります
- 容量はブラウザのクォータ管理に従います (通常のセーブデータの量では問題になりません)

## 動作確認の手順 (devtools のコンソール)

```js
// 書き込み (ストリームを閉じたときに IndexedDB へ自動で反映)
tjs('(Dictionary.saveStruct incontextof (%[v:42]))("user://./ptest.tjs")')
// → ページをリロードしたあと:
tjs('Scripts.evalStorage("user://./ptest.tjs").v')   // → 42 が返れば OK
```
