// krkrz wasm 起動設定 (emcc --pre-js)
//
// - 起動引数: データフォルダ (/data = --preload-file で埋め込んだ MEMFS パス)
//   と DrawDevice 指定。まずは SDL_Renderer 経由の SDLDrawDevice で起動する
//   (既定の SDLOGLDrawDevice は GLES3 API を使うため WebGL2 では要 -sFULL_ES3。
//    GL 機能を使う場合は '-drawdevice=sdl' を外すか '-drawdevice=ogl' に変更)。
// - セーブデータ永続化は SDL の SDL_EMSCRIPTEN_PERSISTENT_PATH 機構に委譲
//   (SDL_RunApp が /persist へ IDBFS を autoPersist 付きでマウントし復元を
//    待ってから起動する。CMakeLists.txt 参照)。pre.js での FS 操作は不要。

// 診断: 早期エラーを document.title に反映する (ヘッドレス検証で DOM から読める)
if (typeof window !== 'undefined') {
    window.addEventListener('error', function (e) {
        document.title = 'KRKRZ-ERR: ' + (e.message || e.error);
    });
    window.addEventListener('unhandledrejection', function (e) {
        document.title = 'KRKRZ-REJ: ' + e.reason;
    });
}

// サンプルランチャ連携:
// TJS 側 (data/startup.tjs のランチャ) が Debug.message で
// "@krkrz-web:launch-sample=<name>" を出力したら、?sample=<name> を付けて
// ページをリロードし、そのサンプルフォルダをプロジェクトとして起動し直す。
// エンジンのログ出力 (stdout/stderr) をフックして検知する。
if (typeof window !== 'undefined') {
    var krkrzHandleToken = function (text) {
        var m = /@krkrz-web:launch-sample=([A-Za-z0-9_\-]+)/.exec(text);
        if (m) {
            var q = new URLSearchParams(window.location.search);
            q.set('sample', m[1]);
            window.location.search = q.toString();
            return true;
        }
        return false;
    };
    Module['print'] = function (text) {
        if (!krkrzHandleToken(String(text))) console.log(text);
    };
    Module['printErr'] = function (text) {
        if (!krkrzHandleToken(String(text))) console.error(text);
    };
}

// canvas のフィット表示 (アスペクト維持 / ?fit=0 で等倍) は web/shell.html の
// CSS が担当する。SDL emscripten はマウス座標を canvas の実表示矩形から
// 逆算するので、CSS 縮小してもゲーム側の座標系は保たれる。

// devtools コンソール用 TJS REPL。コンソールから
//   tjs('System.versionString')
//   tjs('Debug.message("hello")')
// のように任意の TJS 式を評価できる (engine 側 krkrz_repl_eval ブリッジ、
// MASTER ビルドでは含まれない)。戻り値は pretty-print 済み文字列。
if (typeof window !== 'undefined') {
    window.tjs = function (line) {
        if (!Module['ccall']) {
            console.error('krkrz: runtime not ready');
            return;
        }
        var json = Module['ccall']('krkrz_repl_eval', 'string', ['string'], [String(line)]);
        var r = JSON.parse(json);
        if (r.ok) {
            console.log(r.result);
            return r.result;
        }
        console.error(r.error);
    };
}

// -drawthread=1: wasm では描画スレッドプールを増やしても pthread プールを
// 圧迫するだけで益が薄いので 1 に固定 (最後のタスクはメインスレッド実行)
//
// プロジェクトパスは preload 構成と URL パラメータに応じて自動選択:
//   ?sample=<name> … データ内サブフォルダ <name>/ をプロジェクトとして起動
//                    (サンプルランチャからのリロード起動)
//   xp3 構成 (KRKRZ_WEB_DATA_XP3=true、webconfig.js が定義) なら data.xp3>、
//   フォルダ構成なら /data
// 注意: Module.arguments は生成 JS のロード時に取り込まれるため、preRun 等の
// 遅延コールバックではなくトップレベルで同期的に確定させること。
(function () {
    var args = ['-drawdevice=sdl', '-drawthread=1'];
    var xp3 = (typeof KRKRZ_WEB_DATA_XP3 !== 'undefined') && KRKRZ_WEB_DATA_XP3;
    var sample = null;
    if (typeof window !== 'undefined') {
        var s = new URLSearchParams(window.location.search).get('sample');
        if (s && /^[A-Za-z0-9_\-]+$/.test(s)) sample = s;
    }
    if (sample) {
        // 相対パス指定はエンジン側で appPath (=/) 前置で解決される
        args.push(xp3 ? ('data.xp3>' + sample + '/') : ('data/' + sample + '/'));
    } else if (!xp3) {
        args.push('/data');
    }
    Module['arguments'] = args;
})();

