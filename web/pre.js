// krkrz wasm 起動設定 (emcc --pre-js)
//
// - 起動引数: データフォルダ (/data = --preload-file で埋め込んだ MEMFS パス)
//   と DrawDevice 指定。まずは SDL_Renderer 経由の SDLDrawDevice で起動する
//   (既定の SDLOGLDrawDevice は GLES3 API を使うため WebGL2 では要 -sFULL_ES3。
//    GL 機能を使う場合は '-drawdevice=sdl' を外すか '-drawdevice=ogl' に変更)。
// - /save を IDBFS にマウントし、起動前に IndexedDB から復元する。
//   書き込み後の永続化 (FS.syncfs(false)) はエンジン側から呼ぶ (Phase 3)。

// 診断: 早期エラーを document.title に反映する (ヘッドレス検証で DOM から読める)
if (typeof window !== 'undefined') {
    window.addEventListener('error', function (e) {
        document.title = 'KRKRZ-ERR: ' + (e.message || e.error);
    });
    window.addEventListener('unhandledrejection', function (e) {
        document.title = 'KRKRZ-REJ: ' + e.reason;
    });
}

// canvas 表示フィット (アスペクト維持でビューポートに収める)。
// SDL emscripten はマウス座標を canvas の実表示矩形から逆算するので
// CSS 縮小してもゲーム側の座標系 (論理 1920x1080 等) は保たれる。
// URL パラメータで挙動を変更できる:
//   ?fit=0 … フィット無効 (CSS ピクセル等倍 = 従来表示)
if (typeof window !== 'undefined') {
    var krkrzParams = new URLSearchParams(window.location.search);
    if (krkrzParams.get('fit') !== '0') {
        var krkrzStyle = document.createElement('style');
        krkrzStyle.textContent =
            '#canvas { display: block; margin: 0 auto;' +
            ' max-width: 100vw; max-height: 100vh; width: auto; height: auto; }';
        document.head.appendChild(krkrzStyle);
    }
}

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
Module['arguments'] = ['-drawdevice=sdl', '-drawthread=1', '/data'];

Module['preRun'] = Module['preRun'] || [];
Module['preRun'].push(function () {
    // node での検証実行時は IDBFS が無いのでスキップ
    if (typeof window === 'undefined') return;
    FS.mkdir('/save');
    FS.mount(IDBFS, {}, '/save');
    addRunDependency('krkrz-idbfs-load');
    FS.syncfs(true, function (err) {
        if (err) console.warn('krkrz: IDBFS restore failed:', err);
        removeRunDependency('krkrz-idbfs-load');
    });
});
