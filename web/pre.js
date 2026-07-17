// krkrz wasm 起動設定 (emcc --pre-js)
//
// - 起動引数: データフォルダ (/data = --preload-file で埋め込んだ MEMFS パス)
//   と DrawDevice 指定。まずは SDL_Renderer 経由の SDLDrawDevice で起動する
//   (既定の SDLOGLDrawDevice は GLES3 API を使うため WebGL2 では要 -sFULL_ES3。
//    GL 機能を使う場合は '-drawdevice=sdl' を外すか '-drawdevice=ogl' に変更)。
// - /save を IDBFS にマウントし、起動前に IndexedDB から復元する。
//   書き込み後の永続化 (FS.syncfs(false)) はエンジン側から呼ぶ (Phase 3)。

Module['arguments'] = ['-drawdevice=sdl', '/data'];

Module['preRun'] = Module['preRun'] || [];
Module['preRun'].push(function () {
    FS.mkdir('/save');
    FS.mount(IDBFS, {}, '/save');
    addRunDependency('krkrz-idbfs-load');
    FS.syncfs(true, function (err) {
        if (err) console.warn('krkrz: IDBFS restore failed:', err);
        removeRunDependency('krkrz-idbfs-load');
    });
});
