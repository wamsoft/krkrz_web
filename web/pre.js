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
