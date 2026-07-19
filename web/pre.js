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

// リソースを preRun で MEMFS /resource へ fetch する (配信サイドカー方式)。
// resource/ (config.cf/messages/フォント/SysInitScript) は wasm に焼かず配信ファイルに
// してあるので、main 実行前にここで取り込む。addRunDependency で main を待たせるため、
// 最初期の config.cf 読み (charset 決定) も安全。エンジンは file://./resource/ で同期読み。
// KRKRZ_WEB_RESOURCE_BASE は webconfig.js (shell が先に読む配信ファイル) が定義する。
Module = (typeof Module !== 'undefined') ? Module : {};
Module.preRun = Module.preRun || [];
Module.preRun.push(function () {
    var base = (typeof KRKRZ_WEB_RESOURCE_BASE !== 'undefined' && KRKRZ_WEB_RESOURCE_BASE)
        ? KRKRZ_WEB_RESOURCE_BASE : 'resource/';
    addRunDependency('krkrz-resource');
    (async function () {
        try {
            // resource.list は resource バンドルの「目次」で、バンドルのメンバーでは
            // なく site 直下 (resource/ の兄弟) に置かれる。個々のリソースファイルだけ
            // base (resource/) 配下から取得する。
            var list = await (await fetch('resource.list')).json();
            try { FS.mkdir('/resource'); } catch (e) { /* 既存 */ }
            for (var i = 0; i < list.length; i++) {
                var resp = await fetch(base + list[i]);
                if (!resp.ok) { console.error('krkrz resource 404:', base + list[i]); continue; }
                var buf = new Uint8Array(await resp.arrayBuffer());
                FS.writeFile('/resource/' + list[i], buf);
            }
        } catch (e) {
            console.error('krkrz resource load failed:', e);
        }
        removeRunDependency('krkrz-resource');
    })();
});

// web:// OPFS キャッシュのキー規約 (エンジン core HttpStorageMedia の
// krkrz_web_fetch と同一であること): SHA-256(url) 先頭 40hex + '_' +
// サニタイズ済み末尾 32 文字。単純サニタイズだけの旧方式 (v1) は日本語
// ファイル名同士が同一キーに潰れて衝突していた。
async function krkrzOpfsKey(url) {
    var d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(url));
    var h = Array.from(new Uint8Array(d)).map(function (b) {
        return b.toString(16).padStart(2, '0');
    }).join('');
    return h.slice(0, 40) + '_' + url.replace(/[^A-Za-z0-9._-]/g, '_').slice(-32);
}

// OPFS キャッシュの版数移行: キー規約を変えたとき、旧形式のエントリは二度と
// ヒットしないゴミになる (旧衝突キーは実害もある) ので、版数マーカーが無ければ
// 一度だけ全クリアして張り直す。main 開始前に完了させる (エンジンの最初の
// web:// アクセスより先)。
Module.preRun.push(function () {
    addRunDependency('krkrz-opfs-ver');
    (async function () {
        var MARKER = '.krkrz-cache-v2';
        try {
            var root = await navigator.storage.getDirectory();
            var need = true;
            try { await root.getFileHandle(MARKER); need = false; } catch (e) { /* 未移行 */ }
            if (need) {
                var names = [];
                for await (var name of root.keys()) names.push(name);
                for (var i = 0; i < names.length; i++) {
                    try { await root.removeEntry(names[i], { recursive: true }); } catch (e) {}
                }
                var wh = await root.getFileHandle(MARKER, { create: true });
                await (await wh.createWritable()).close();
                if (names.length) {
                    console.log('krkrz: OPFS cache cleared for key-format v2 ('
                        + names.length + ' old entries)');
                }
            }
        } catch (e) { console.warn('krkrz: OPFS cache version check failed', e); }
        removeRunDependency('krkrz-opfs-ver');
    })();
});

// 起動後バックグラウンド先読み (Phase E: fast-follow)。
// 案件サイトに krkrz_prefetch.json (stage_web.py が delivery:"prefetch" ソースから
// 生成。gamedata 相対の小文字パス配列) があれば、起動が落ち着いた頃に
// バックグラウンドで fetch → OPFS 保存する。以後のエンジンの web:// オンデマンド
// アクセスは初回プレイでも OPFS ヒットになる。
// OPFS キーはエンジン (core HttpStorageMedia の krkrz_web_fetch) と同じ規約:
//   key = (webbase + path) の [^A-Za-z0-9._-] を '_' に置換
// OPFS キーは krkrzOpfsKey (エンジンと同一規約)。
// ?prefetch=0 で無効化。進捗は Module.krkrzPrefetch = {total,done,skipped,failed}。
if (typeof window !== 'undefined') {
    (function () {
        var params = new URLSearchParams(window.location.search);
        if (params.get('prefetch') === '0') return;
        var defbase = (typeof KRKRZ_WEB_DEFAULT_WEBBASE !== 'undefined') ? KRKRZ_WEB_DEFAULT_WEBBASE : '';
        var webbase = params.get('webbase') || defbase;
        // wasm/データのダウンロードと帯域を取り合わないよう、エンジン開始
        // (runtime 初期化 = shell が Module.krkrzRuntimeReady を立てる) を
        // 待ってから開始する。進捗はローディング表示のカウンタ interval が
        // Module.krkrzPrefetch を参照して表示する
        var waitReady = setInterval(function () {
            if (typeof Module === 'undefined' || !Module.krkrzRuntimeReady) return;
            clearInterval(waitReady);
            setTimeout(runPrefetch, 1000);
        }, 250);
        async function runPrefetch() {
            try {
                var resp = await fetch('krkrz_prefetch.json');
                if (!resp.ok) return;   // リスト無し = 先読みしない案件/サンプル
                var list = await resp.json();
                if (!Array.isArray(list) || !list.length) return;
                var root = await navigator.storage.getDirectory();
                // 既存キーを一括列挙して重複 fetch を避ける
                var have = new Set();
                for await (var k of root.keys()) have.add(k);
                var stat = { total: list.length, done: 0, skipped: 0, failed: 0 };
                Module.krkrzPrefetch = stat;
                var idx = 0;
                async function worker() {
                    while (idx < list.length) {
                        var url = webbase + list[idx++];
                        var key = await krkrzOpfsKey(url);
                        try {
                            if (have.has(key)) { stat.skipped++; stat.done++; continue; }
                            var r = await fetch(url);
                            if (!r.ok) { stat.failed++; stat.done++; continue; }
                            var ab = await r.arrayBuffer();
                            var wh = await root.getFileHandle(key, { create: true });
                            var w = await wh.createWritable();
                            await w.write(ab);
                            await w.close();
                        } catch (e) { stat.failed++; }
                        stat.done++;
                    }
                }
                // 同時 2 本: 起動直後のオンデマンド fetch と帯域を取り合わないよう控えめに
                await Promise.all([worker(), worker()]);
                console.log('krkrz prefetch: ' + stat.total + ' file(s), skipped='
                    + stat.skipped + ', failed=' + stat.failed);
            } catch (e) { console.warn('krkrz prefetch failed:', e); }
        }
    })();
}

// オーディオゲート: autoplay ポリシーで音声がブロックされる環境では、
// AudioContext がユーザー操作まで suspended で、その間に鳴らした音は全て
// 捨てられる (起動直後のロゴ音・タイトルコール等が欠落する)。
// 対策として、**起動スクリプト完了直後 (= ローディング画面が消える直前、
// シナリオの最初の発音より前)** にクリック待ちを差し込む。core の
// OnStartupScriptDone (wasm) が krkrzWaitBeforeStart() を JSPI で await して
// からローディング終了フックを呼ぶので、この関数が Promise を返せばその間
// エンジンは停止したまま。クリック → 即ゲーム開始 (待ちゼロ)。
// - それまでのダウンロード/起動処理は全て通常どおり進む
// - ページ内で既に操作済み (sticky activation で音声許可済み) なら待たない
// - autoplay 許可環境 (エンゲージメント/kiosk/--autoplay-policy) も待たない
// - ?audiogate=0 で無効化
if (typeof window !== 'undefined') {
    (function () {
        var disabled =
            new URLSearchParams(window.location.search).get('audiogate') === '0';
        // ページ内操作の記録 (一度でも操作があれば音声は許可される)
        var interacted = false;
        var markOnce = function () {
            interacted = true;
            window.removeEventListener('pointerdown', markOnce);
            window.removeEventListener('keydown', markOnce);
        };
        window.addEventListener('pointerdown', markOnce);
        window.addEventListener('keydown', markOnce);
        // autoplay 可否の probe (許可済みならゲート不要)
        var allowed = false;
        try {
            var AC = window.AudioContext || window.webkitAudioContext;
            if (AC) {
                var probe = new AC();
                allowed = (probe.state !== 'suspended');
                probe.close();
            } else {
                allowed = true; // WebAudio 無し = ゲートの意味なし
            }
        } catch (e) { allowed = true; }

        globalThis.krkrzWaitBeforeStart = function () {
            if (disabled || allowed || interacted) return Promise.resolve();
            return new Promise(function (resolve) {
                var el = document.getElementById('loading-gate');
                var st = document.getElementById('status');
                var bar = document.getElementById('loading-bar');
                var spin = document.getElementById('spinner');
                var loading = document.getElementById('loading');
                // ?loading=0 等でオーバーレイが畳まれていても、ゲート表示は
                // 見える必要があるので強制的に出す
                if (loading) {
                    loading.classList.remove('hide');
                    loading.style.display = '';
                }
                if (bar) bar.style.display = 'none';
                if (spin) spin.style.display = 'none';
                if (st) st.textContent = '準備完了';
                if (el) el.style.display = 'block';
                var fire = function () {
                    window.removeEventListener('pointerdown', fire);
                    window.removeEventListener('keydown', fire);
                    if (el) el.style.display = 'none';
                    resolve();
                };
                window.addEventListener('pointerdown', fire);
                window.addEventListener('keydown', fire);
            });
        };
    })();
}

// krkrz.wasm のダウンロード進捗表示。
// emscripten の setStatus 進捗はデータバンドル (krkrz.data) のみで、最も大きい
// wasm 本体 (~10MB) は無進捗のまま落ちてくる。instantiateWasm を自前 fetch に
// 差し替え、ReadableStream で読みながら setStatus に "(loaded/total)" を流す
// (shell 側がプログレスバー + MB 表記に変換する)。
// pthread ビルドでは receiveInstance に module も渡す必要がある (worker が
// コンパイル済み module を共有で受け取るため)。
if (typeof window !== 'undefined') {
    Module.instantiateWasm = function (info, receiveInstance) {
        (async function () {
            try {
                var resp = await fetch('krkrz.wasm');
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                var total = parseInt(resp.headers.get('Content-Length') || '0', 10);
                var reader = resp.body.getReader();
                var chunks = [];
                var loaded = 0;
                for (;;) {
                    var r = await reader.read();
                    if (r.done) break;
                    chunks.push(r.value);
                    loaded += r.value.length;
                    if (Module.setStatus) {
                        // total 不明 (Content-Length 無し) ならサイズのみ表示 (バー無し)
                        Module.setStatus(total > 0
                            ? 'エンジンダウンロード中 (' + loaded + '/' + total + ')'
                            : 'エンジンダウンロード中 ' + (loaded / 1048576).toFixed(1) + 'MB');
                    }
                }
                var buf = new Uint8Array(loaded);
                var off = 0;
                for (var i = 0; i < chunks.length; i++) {
                    buf.set(chunks[i], off);
                    off += chunks[i].length;
                }
                var res = await WebAssembly.instantiate(buf.buffer, info);
                receiveInstance(res.instance, res.module);
                globalThis.__krkrzWasmDone = true; // ワーカー起動進捗表示の開始条件
            } catch (e) {
                console.error('krkrz: wasm instantiate failed:', e);
                if (Module.setStatus) Module.setStatus('エンジンの読み込みに失敗しました');
            }
        })();
        return {}; // 非同期 instantiate
    };
}

// pthread ワーカープール起動の進捗表示。
// DL バーが max になった後、PTHREAD_POOL_SIZE 個のワーカーがそれぞれ
// krkrz.js を importScripts でロードする区間 (サーバに GET /krkrz.js が
// 続く時間帯) が無表示だったので、「エンジン初期化中 (k / N)」として出す。
// ワーカーのロード完了は emscripten が worker.loaded を立てるので数えられる。
// DL 表示 (setStatus) との取り合いを避けるため、全 DL ストリーム完了
// (Module.krkrzDlComplete) + wasm instantiate 完了後のみ表示する。
if (typeof window !== 'undefined') {
    (function () {
        var workerTimer = setInterval(function () {
            if (typeof Module !== 'undefined' && Module.krkrzRuntimeReady) {
                clearInterval(workerTimer);
                return;
            }
            if (!globalThis.__krkrzWasmDone) return;
            if (typeof Module === 'undefined' || !Module.krkrzDlComplete) return;
            if (typeof PThread === 'undefined' || !PThread.unusedWorkers) return;
            var ws = PThread.unusedWorkers.concat(PThread.runningWorkers || []);
            if (!ws.length) return;
            var loaded = 0;
            for (var i = 0; i < ws.length; i++) if (ws[i].loaded) loaded++;
            var st = document.getElementById('status');
            var bar = document.getElementById('loading-bar');
            var fill = document.getElementById('loading-bar-fill');
            if (st) st.textContent = 'エンジン初期化中 (' + loaded + ' / ' + ws.length + ')';
            if (bar && fill) {
                fill.style.width = (loaded / ws.length) * 100 + '%';
                bar.style.display = 'block';
            }
        }, 200);
    })();
}

// 起動ローディング表示 (shell の #loading) の制御。
// wasm ロード〜resource 取込〜エンジン初期化〜起動スクリプト実行完了までを
// カバーする。完了は core (SDL3Application::OnStartupScriptDone) が EM_ASM で
// krkrzOnStartupScriptDone() を呼んで通知する (デスクトップの splash 破棄と
// 同じタイミング = 初回スクリプトロード完了 ≒ メイン描画開始)。
// - resource/loading.json があれば見た目を差し替える:
//     { "image": "loading.png",   // resource/ 内の背景画像 (contain 中央、任意)
//       "background": "#000000",  // 背景色 (任意)
//       "text": "Now Loading...", // 起動中テキスト (任意)
//       "textColor": "#cccccc" }  // 文字色 (任意)
// - 進捗: エンジンの web:// 取得数 (krkrz_web_fetch が globalThis.
//   __krkrzWebFetchCount を加算) を「取得ファイル: N」として表示
// - ?loading=0 で旧挙動 (wasm ロード完了で畳む。shell 側で判定)
if (typeof window !== 'undefined') {
    (function () {
        if (new URLSearchParams(window.location.search).get('loading') === '0') {
            // 旧挙動でもオーディオゲートがオーバーレイを強制表示することが
            // あるため、完了時には必ず畳む
            globalThis.krkrzOnStartupScriptDone = function () {
                var l = document.getElementById('loading');
                if (l) l.style.display = 'none';
            };
            return;
        }
        var counterTimer = setInterval(function () {
            if (typeof Module !== 'undefined' && Module.krkrzLoadingDone) {
                clearInterval(counterTimer);
                return;
            }
            var el = document.getElementById('loading-count');
            if (!el) return;
            var n = globalThis.__krkrzWebFetchCount || 0;
            var b = globalThis.__krkrzWebFetchBytes || 0;
            var txt = n > 0
                ? '取得ファイル: ' + n + ' (' + (b / 1048576).toFixed(1) + 'MB)'
                : '';
            // prefetch (バックグラウンド先読み) の進捗。総数が既知なので
            // プログレスバーも駆動する (DL フェーズ終了後 = エンジン開始後に
            // しか prefetch は走らないためバーの取り合いは起きない)
            var ps = (typeof Module !== 'undefined') ? Module.krkrzPrefetch : null;
            var gateEl = document.getElementById('loading-gate');
            var gateShown = gateEl && gateEl.style.display === 'block';
            if (ps && ps.total > 0 && !gateShown) {
                var bar = document.getElementById('loading-bar');
                var fill = document.getElementById('loading-bar-fill');
                if (ps.done < ps.total) {
                    txt += (txt ? '　' : '') + '先読み: ' + ps.done + ' / ' + ps.total;
                    if (bar && fill) {
                        fill.style.width = (ps.done / ps.total) * 100 + '%';
                        bar.style.display = 'block';
                    }
                } else if (bar) {
                    bar.style.display = 'none';
                }
            }
            el.textContent = txt;
        }, 300);
        globalThis.krkrzOnStartupScriptDone = function () {
            clearInterval(counterTimer);
            if (typeof Module !== 'undefined'
                && typeof Module.krkrzHideLoading === 'function') {
                Module.krkrzHideLoading();
            }
        };
        // resource/loading.json による見た目カスタマイズ (無ければ既定のまま)
        (async function () {
            try {
                var base = (typeof KRKRZ_WEB_RESOURCE_BASE !== 'undefined' && KRKRZ_WEB_RESOURCE_BASE)
                    ? KRKRZ_WEB_RESOURCE_BASE : 'resource/';
                var resp = await fetch(base + 'loading.json');
                if (!resp.ok) return;
                var conf = await resp.json();
                var loading = document.getElementById('loading');
                var bg = document.getElementById('loading-bg');
                if (!loading) return;
                if (conf.background) loading.style.background = conf.background;
                if (conf.textColor) loading.style.color = conf.textColor;
                if (conf.image && bg) {
                    bg.style.backgroundImage = "url('" + encodeURI(base + conf.image) + "')";
                }
                if (conf.text && typeof Module !== 'undefined') {
                    Module.krkrzBootText = conf.text;
                }
            } catch (e) { /* loading.json 無し = 既定表示 */ }
        })();
    })();
}

// 開発用: ?opfsclear で OPFS (web:// メディアの永続キャッシュ) を全消しする。
// アセット更新時にキャッシュが古いままになるのを手動リセットするため。
// 本番では cache busting (ファイル名/URL 変更) で更新する運用。
if (typeof window !== 'undefined'
    && new URLSearchParams(window.location.search).get('opfsclear') === '1') {
    (async function () {
        try {
            var root = await navigator.storage.getDirectory();
            for await (var name of root.keys()) {
                await root.removeEntry(name, { recursive: true });
            }
            console.log('krkrz: OPFS cleared');
        } catch (e) { console.warn('krkrz: OPFS clear failed', e); }
    })();
}

// 未処理スクリプト例外ハンドラ (engine の SDL3Application::OnUnhandledScriptException
// から MAIN_THREAD_EM_ASM 経由で呼ばれる)。
// - 音を止める (SDL の AudioContext を suspend)
// - shell の #error オーバーレイに本文と trace を出し、リロードを促す
// - ?onerror=reload なら自動リロード (起動直後の連続エラーはガードで抑止)
if (typeof window !== 'undefined') {
    globalThis.krkrzOnScriptError = function (message, trace) {
        // オーディオ停止 (ぶつぶつ回避)
        try {
            if (typeof SDL3 !== 'undefined' && SDL3.audioContext) {
                SDL3.audioContext.suspend();
            }
        } catch (e) {}

        console.error('krkrz script exception:\n' + message + (trace ? '\n' + trace : ''));

        // 起動中のエラーならローディング表示を畳む (エラーオーバーレイを見せる)
        try {
            if (typeof Module !== 'undefined'
                && typeof Module.krkrzHideLoading === 'function') {
                Module.krkrzHideLoading();
            }
        } catch (e2) {}

        var params = new URLSearchParams(window.location.search);
        if (params.get('onerror') === 'reload') {
            // 無限リロード抑止: 直近の自動リロードから一定時間内は手動表示に切替
            var now = Date.now();
            var last = 0;
            try { last = parseInt(sessionStorage.getItem('krkrz-autoreload-at') || '0', 10); } catch (e) {}
            if (now - last > 4000) {
                try { sessionStorage.setItem('krkrz-autoreload-at', String(now)); } catch (e) {}
                window.location.reload();
                return;
            }
            // 連続エラー: 自動リロードをやめて画面表示に落とす
        }

        if (typeof Module !== 'undefined' && typeof Module.showError === 'function') {
            Module.showError(message, trace);
        }
    };
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
    // ?drawdevice=sdl|ogl|sdlogl で描画デバイスを切替可能 (検証用)。既定 sdl
    var dd = 'sdl';
    if (typeof window !== 'undefined') {
        var d = new URLSearchParams(window.location.search).get('drawdevice');
        if (d && /^[a-z]+$/.test(d)) dd = d;
    }
    var args = ['-drawdevice=' + dd, '-drawthread=1'];
    var xp3 = (typeof KRKRZ_WEB_DATA_XP3 !== 'undefined') && KRKRZ_WEB_DATA_XP3;
    var params = (typeof window !== 'undefined')
        ? new URLSearchParams(window.location.search) : new URLSearchParams();

    // ?webbase=<url> : web:// メディアの fetch ベース URL (案件データの配信元)。
    // ?webproject=1  : プロジェクトパスを web://./ にし、サーバ上のバラファイルを
    //                  そのままプロジェクトとして起動する (オンデマンド配信テスト)。
    // ?readencoding=<enc> : スクリプト読み込みエンコーディング (Shift-JIS 案件は
    //                  Shift_JIS)。UTF-8 案件は不要。
    // webbase: URL 指定が最優先。無ければ案件サイトの既定 (webconfig.js の
    // KRKRZ_WEB_DEFAULT_WEBBASE。stage_web.py が案件配信元 "gamedata/" を焼く)。
    var defbase = (typeof KRKRZ_WEB_DEFAULT_WEBBASE !== 'undefined') ? KRKRZ_WEB_DEFAULT_WEBBASE : '';
    var webbase = params.get('webbase') || defbase;
    if (webbase) args.push('-webbase=' + webbase);
    var readenc = params.get('readencoding');
    if (readenc && /^[A-Za-z0-9_\-]+$/.test(readenc)) args.push('-readencoding=' + readenc);

    var sample = params.get('sample');
    if (sample && !/^[A-Za-z0-9_\-]+$/.test(sample)) sample = null;

    // ?webproject=1、または案件サイト (既定 webbase 有り & sample 指定無し) は
    // web:// プロジェクト起動。これで案件サイトは引数なし URL で直接起動する。
    // 案件サイトの既定追加引数 (webconfig.js の KRKRZ_WEB_DEFAULT_ARGS)。
    // config.cf より優先されるので、wasm32 の 2GB に収めるプールサイズ上書き等に使う。
    if (typeof KRKRZ_WEB_DEFAULT_ARGS !== 'undefined' && KRKRZ_WEB_DEFAULT_ARGS) {
        KRKRZ_WEB_DEFAULT_ARGS.split(/\s+/).forEach(function (a) { if (a) args.push(a); });
    }

    if (params.get('webproject') === '1' || (defbase && !sample)) {
        args.push('web://./');
    } else if (sample) {
        // 相対パス指定はエンジン側で appPath (=/) 前置で解決される
        args.push(xp3 ? ('data.xp3>' + sample + '/') : ('data/' + sample + '/'));
    } else if (!xp3) {
        args.push('/data');
    }
    Module['arguments'] = args;
})();

