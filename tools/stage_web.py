#!/usr/bin/env python3
"""PROJECT_DIR ベースの web 版ステージング (krkrz_android の PROJECT_DIR 方式の web 版)。

**共有バイナリ + 配信サイドカー方式**。エンジン (krkrz.html/js/wasm/data) は案件非依存の
共有バイナリで、`make build` で一度ビルドしておけばよい。本ツールは cmake を一切呼ばず
(relink しない)、その共有バイナリをコピーし、案件差分だけをサイドカーとして配置する:

  site/
    index.html krkrz.js krkrz.wasm krkrz.data  … 共有バイナリ
    webconfig.js                                … 案件の起動時構成 (webbase/args)
    resource/ resource.list                     … 案件の config.cf/messages/フォント
    gamedata/                                    … 案件データ (web:// 配信。sources をマージ)
    gamedata.krkrz_files.json                    … web:// autopath マニフェスト
    serve.py README.md                           … 実行用サーバ + 起動手順

配置は **ハードリンクを自動判定**する: site と元ファイルが同一ボリュームならハードリンク
(実体複製なし・即時)、別ボリューム等でハードリンク不可なら自動で実コピーにフォールバック
する (ファイル単位)。手動フラグは不要。binary / resource / data すべて対象。

案件フォルダの web-config.json (すべて任意。無指定は慣例で補完):
  {
    "name":     "mygame",           // 表示名 (既定: フォルダ名)
    "resource": "setup/nxresource", // config.cf/messages/フォント (既定: setup/nxresource)
    "port":     8100,               // 生成 serve.py の既定ポート
    "args": ["-bitmappoolsize=640"],// config.cf 優先の起動引数

    // ゲームデータ (web:// 配信) の構成。krkrz_android の app-config.json の
    // assetPack と同じ書式で、複数ソースを **マージ** して gamedata/ を組む。
    "assetPack": {
      "baseFolder": "${PROJECT_DIR}",     // 相対 from の基準 (既定: PROJECT_DIR)
      "sources": [
        // type: "mirror" (サブツリー保持) / "flatten" (階層を潰す)
        // from: baseFolder 相対、または絶対 (${PROJECT_DIR}/${KRKRZ_BASE}/${BUILD_SYSTEM_DIR}/環境変数 展開可)
        // to:   配置先サブパス。省略時の既定は krkrz_android と同じ
        //       (mirror+相対→from と同じ / mirror+絶対→from の末尾フォルダ名 / flatten→ルート)。
        //       gamedata ルートに置きたいときは "to": "" を明示する。
        // include/exclude: Ant 風グロブ (**/*, *.xp3, **/*.bak)。既定 include=["**/*"]
        // delivery: "on-demand" (既定) / "prefetch"
        //       prefetch のソースのファイルは krkrz_prefetch.json に列挙され、
        //       起動後に pre.js がバックグラウンドで fetch→OPFS 保存する
        //       (初回プレイでもオンデマンド fetch がローカルヒットになる)。
        //       同一ファイルが複数ソースに載る場合は先勝ち (delivery も先勝ち)。
        //       動画 (VideoOverlay) は <video> の URL 直接ストリーミングで OPFS を
        //       通らないため prefetch 対象にしないこと。
        { "type": "mirror", "from": "data", "to": "",
          "include": ["**/*"], "exclude": ["**/*.bak", "**/*.psd"] }
      ]
    }
  }
※ Android の app-config.json とは別ファイル (名前衝突を避けるため web-config.json)。
※ 旧書式 ("data": "data", "exclude": [".bak", ".psd"]) も後方互換で受ける
  (単一 mirror ソース to="" として展開。exclude は拡張子指定を **/*<ext> に変換)。

  usage: python stage_web.py <PROJECT_DIR> [options]
    --data DIR      web:// 配信データを単一フォルダで上書き (assetPack より優先)
    --build-type T  Release (既定) / Debug — 共有バイナリの参照先
    --port N        生成 serve.py の既定ポート

出力: ${PROJECT_DIR}/build/web/site/  (この中の serve.py を実行すれば起動)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent   # krkrz_web/


# ---------------------------------------------------------------------------
# 変数展開 (${PROJECT_DIR} / ${KRKRZ_BASE} / ${BUILD_SYSTEM_DIR} / ${ENVVAR}) と
# Ant 風グロブ (krkrz_android app-config と同じ書式)
# ---------------------------------------------------------------------------

def make_ctx(project_dir: Path) -> dict:
    """変数展開のコンテキスト。krkrz_android の resolvePath と同じ 3 変数 + 環境変数。"""
    kb = os.environ.get("KRKRZ_BASE")
    krkrz_base = Path(kb).resolve() if kb else WEB_ROOT.parent
    return {
        "PROJECT_DIR": str(project_dir),
        "KRKRZ_BASE": str(krkrz_base),
        "BUILD_SYSTEM_DIR": str(WEB_ROOT),
    }


_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_vars(s: str, ctx: dict) -> str:
    def repl(m):
        k = m.group(1)
        if k in ctx:
            return ctx[k]
        return os.environ.get(k, m.group(0))
    return _VAR_RE.sub(repl, s)


def glob_to_regex(glob: str) -> re.Pattern:
    """Ant 風グロブ ('/' 区切りパス) を正規表現に変換する。
    ** = 階層跨ぎ / * = '/' 以外の 0+ / ? = '/' 以外の 1 文字。"""
    glob = glob.replace("\\", "/")
    out, i, n = [], 0, len(glob)
    while i < n:
        if glob.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif glob.startswith("**", i):
            out.append(".*"); i += 2
        elif glob[i] == "*":
            out.append("[^/]*"); i += 1
        elif glob[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(glob[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_globs(patterns) -> list:
    return [glob_to_regex(p) for p in patterns]


def matches_any(rel: str, regexes: list) -> bool:
    return any(r.match(rel) for r in regexes)


# ---------------------------------------------------------------------------
# 転送 (ハードリンク自動判定 + copy フォールバック)
# ---------------------------------------------------------------------------

def link_or_copy(src: Path, dest: Path, stats: dict) -> None:
    """src を dest へ配置する。同一ボリュームなら os.link (ハードリンク=実体複製なし・
    即時) を自動採用し、クロスボリューム等で失敗したら実コピーにフォールバックする
    (ファイル単位で自動判定)。krkrz_android app/build.gradle の runCopyRules と同方針。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    try:
        os.link(src, dest)
        stats["linked"] += 1
    except OSError:
        shutil.copy2(src, dest)
        stats["copied"] += 1


def remove_dest(dest: Path) -> None:
    """配置先の既存物を安全に除去する。junction/symlink はリンクだけ消し (target 安全)、
    実体ディレクトリ (旧コピー/ハードリンク木) は中身ごと除去する。ハードリンクの削除は
    別ディレクトリエントリを消すだけで source の実体は残るので rmtree で安全。"""
    if not (dest.exists() or dest.is_symlink()):
        return
    try:
        # junction / symlink / 空ディレクトリはリンクだけ消える (target 非破壊)。
        os.rmdir(dest)
    except OSError:
        shutil.rmtree(dest, ignore_errors=True)


def build_expected(sources: list, base_folder, ctx: dict, label: str) -> tuple:
    """sources を評価し、({配置先相対パス: 元ファイル}, {prefetch 対象の配置先相対パス})
    を返す (krkrz_android runCopyRules の 1. と同じ。重複は先勝ち。delivery も先勝ち)。"""
    expected: dict = {}
    prefetch: set = set()
    dups: list = []
    for src in sources:
        typ = str(src.get("type", ""))
        if typ not in ("mirror", "flatten"):
            raise SystemExit(f"[{label}] unknown type '{typ}' (mirror/flatten)")
        delivery = str(src.get("delivery", "on-demand"))
        if delivery not in ("on-demand", "prefetch"):
            raise SystemExit(f"[{label}] unknown delivery '{delivery}' (on-demand/prefetch)")
        raw_from = src.get("from")
        if not raw_from:
            raise SystemExit(f"[{label}] 'from' is required")
        expanded_from = expand_vars(str(raw_from), ctx)
        from_is_abs = Path(expanded_from).is_absolute()
        if from_is_abs:
            from_dir = Path(expanded_from)
        elif base_folder is not None:
            from_dir = Path(base_folder) / expanded_from
        else:
            raise SystemExit(f"[{label}] 'from' が相対 ('{raw_from}') だが baseFolder 未設定")
        from_dir = from_dir.resolve()

        # 既定の to (krkrz_android と同じ): mirror+相対→from / mirror+絶対→末尾名 / flatten→ルート
        if "to" in src:
            to_path = src["to"] or ""
        elif typ == "mirror":
            to_path = from_dir.name if from_is_abs else expanded_from
        else:
            to_path = ""
        to_path = expand_vars(str(to_path), ctx).replace("\\", "/").strip("/")

        inc = compile_globs(src.get("include", ["**/*"]))
        exc = compile_globs(src.get("exclude", []))

        if not from_dir.is_dir():
            print(f"[{label}] source folder not found, skipped: {from_dir}", file=sys.stderr)
            continue

        for root, _dirs, files in os.walk(from_dir):
            for name in files:
                fp = Path(root) / name
                rel = fp.relative_to(from_dir).as_posix()
                if not matches_any(rel, inc):
                    continue
                if exc and matches_any(rel, exc):
                    continue
                if typ == "mirror":
                    dest_rel = f"{to_path}/{rel}" if to_path else rel
                else:
                    dest_rel = f"{to_path}/{name}" if to_path else name
                dest_rel = dest_rel.lstrip("/")
                if dest_rel in expected:
                    # 重なりは仕様 (先勝ちオーバーレイ。prefetch ソース + 全体 mirror 等)。
                    # 大量に出るためまとめて報告する
                    dups.append(dest_rel)
                    continue
                expected[dest_rel] = fp
                if delivery == "prefetch":
                    prefetch.add(dest_rel)
    if dups:
        head = ", ".join(dups[:3])
        more = f" ほか {len(dups) - 3} 件" if len(dups) > 3 else ""
        print(f"[{label}] {len(dups)} duplicate(s) skipped (first wins): {head}{more}",
              file=sys.stderr)
    return expected, prefetch


def run_copy_rules(sources: list, out_dir: Path, base_folder, ctx: dict,
                   label: str, stats: dict) -> tuple:
    """sources を out_dir にマージ配置する (古いファイルは剪定)。
    krkrz_android runCopyRules の Python 版。転送はハードリンク自動判定。
    (expected, prefetch 対象相対パス集合) を返す。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    expected, prefetch = build_expected(sources, base_folder, ctx, label)

    # 期待に無い古いファイルを除去
    for root, _dirs, files in os.walk(out_dir):
        for name in files:
            fp = Path(root) / name
            rel = fp.relative_to(out_dir).as_posix()
            if rel not in expected:
                fp.unlink()
                stats["removed"] += 1
    # 空になったディレクトリを下から除去
    for root, dirs, _files in os.walk(out_dir, topdown=False):
        for d in dirs:
            try:
                (Path(root) / d).rmdir()
            except OSError:
                pass

    # 変更 (サイズ / mtime) のあるファイルだけ転送
    for dest_rel, src in expected.items():
        dest = out_dir / dest_rel
        if dest.exists():
            ss, ds = src.stat(), dest.stat()
            if ds.st_size == ss.st_size and int(ds.st_mtime) == int(ss.st_mtime):
                stats["unchanged"] += 1
                continue
        link_or_copy(src, dest, stats)
    return expected, prefetch


# ---------------------------------------------------------------------------
# 設定ロード
# ---------------------------------------------------------------------------

def load_config(project_dir: Path) -> dict:
    cfg = project_dir / "web-config.json"
    if not cfg.exists():
        print(f"[stage_web] web-config.json が無いので慣例で続行: {cfg}")
        return {}
    return json.loads(cfg.read_text(encoding="utf-8"))


def resolve_resource_dir(project_dir: Path, cfg: dict, ctx: dict) -> Path | None:
    """resource フォルダ (config.cf/messages.json/フォント等) を解決。
    web-config.json の "resource" 指定 → 慣例 (setup/nxresource) の順。
    charset はここの config.cf (readencoding=...) で決まる。"""
    if cfg.get("resource"):
        raw = expand_vars(str(cfg["resource"]), ctx)
        p = Path(raw)
        if not p.is_absolute():
            p = project_dir / raw
        if (p / "config.cf").exists():
            return p.resolve()
        print(f"[stage_web] 警告: 指定 resource に config.cf が無い: {p}", file=sys.stderr)
    for cand in ("setup/nxresource", "setup/andspec/res"):
        p = project_dir / cand
        if (p / "config.cf").exists():
            return p.resolve()
    return None


def resolve_assetpack(cfg: dict, project_dir: Path, ctx: dict, data_override):
    """gamedata (web:// 配信) を組む (base_folder, sources) を返す。
    優先: --data 上書き > assetPack.sources > 旧 data/exclude 書式 > 慣例 data/。"""
    if data_override:
        d = Path(data_override).resolve()
        return None, [{"type": "mirror", "from": str(d), "to": "", "include": ["**/*"]}]
    ap = cfg.get("assetPack")
    if ap and ap.get("sources"):
        base = ap.get("baseFolder")
        base = Path(expand_vars(str(base), ctx)).resolve() if base else project_dir
        return base, ap["sources"]
    # 後方互換: data + exclude(拡張子指定) を単一 mirror(to="") に展開
    data = cfg.get("data", "data")
    ex = cfg.get("exclude", [".bak", ".psd"])
    globs = [e if ("*" in e or "/" in e) else f"**/*{e}" for e in ex]
    return project_dir, [{"type": "mirror", "from": data, "to": "",
                          "include": ["**/*"], "exclude": globs}]


def run(cmd, **kw):
    print("[stage_web] $", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, **kw)


# ---------------------------------------------------------------------------
# 生成テンプレート
# ---------------------------------------------------------------------------

SERVE_TEMPLATE = '''\
#!/usr/bin/env python3
# 生成物 (stage_web.py): 案件 web サイトの実行用サーバ。
# site/ 一式 (index.html / krkrz.* / webconfig.js / resource/ / gamedata/) を
# COOP/COEP 付きで配信する。gamedata/krkrz_files.json は生成マニフェストを返す。
# <video> ストリーミング (VideoOverlay) 用に HTTP Range (単一レンジ) と
# マルチスレッド配信に対応。
# サイトは自己完結 (絶対パス参照なし) — このフォルダごとコピーすれば動く。
import os, re, sys, posixpath
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(SITE_DIR, "gamedata.krkrz_files.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else {port}

def ci_resolve(path):
    """path が存在しなければ、各パス成分を大文字小文字無視で実在名に置換して返す。
    web:// の URL はマニフェスト由来で小文字なので、case-sensitive な FS (Linux 等)
    でも実ファイル名を変えずに解決できるようにする (見つからなければ通常の 404)。"""
    if os.path.exists(path):
        return path
    drive, rest = os.path.splitdrive(path)
    parts = [p for p in rest.replace('\\\\', '/').split('/') if p]
    cur = (drive + os.sep) if drive else os.sep
    if not os.path.isabs(path):
        cur = '.'
    for comp in parts:
        nxt = os.path.join(cur, comp)
        if not os.path.exists(nxt):
            low = comp.lower()
            try:
                match = next((e for e in os.listdir(cur) if e.lower() == low), None)
            except OSError:
                return path
            if match is None:
                return path
            nxt = os.path.join(cur, match)
        cur = nxt
    return cur

class H(SimpleHTTPRequestHandler):
    extensions_map = {{**SimpleHTTPRequestHandler.extensions_map,
                       '.wasm': 'application/wasm', '.mjs': 'text/javascript',
                       '.js': 'text/javascript'}}
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SITE_DIR, **k)
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()
    def translate_path(self, path):
        p = posixpath.normpath(unquote(path.split('?', 1)[0].split('#', 1)[0]))
        if p == '/gamedata/krkrz_files.json':
            return MANIFEST   # マニフェストは配信データを汚さず site 直下から返す
        return ci_resolve(super().translate_path(path))
    def do_GET(self):
        rh = self.headers.get('Range')
        path = self.translate_path(self.path)
        if rh and os.path.isfile(path):
            self.send_range(path, rh)
        else:
            super().do_GET()
    def send_range(self, path, rh):
        size = os.path.getsize(path)
        m = re.match(r'bytes=(\\d*)-(\\d*)$', rh.strip())
        if not m or (not m.group(1) and not m.group(2)):
            self.send_error(416)
            return
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:  # suffix 形式 bytes=-N (末尾 N バイト)
            start = max(0, size - int(m.group(2)))
            end = size - 1
        end = min(end, size - 1)
        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{{size}}')
            self.end_headers()
            return
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {{start}}-{{end}}/{{size}}')
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        try:
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # ブラウザ側の中断 (シーク等) は正常系

print(f"serving {{SITE_DIR}}\\n  http://localhost:{{PORT}}/")
ThreadingHTTPServer(('localhost', PORT), H).serve_forever()
'''

README_TEMPLATE = '''\
# {name} — web 版 起動手順

このフォルダ (`site/`) は自己完結です。フォルダごとコピー / 別ホストへアップロードしても動きます。

## 起動 (ローカル確認)

```
python serve.py            # → http://localhost:{port}/
```

ブラウザ (**Chrome / Edge**、JSPI を標準搭載する新しめの版) で
**http://localhost:{port}/** を開くと、引数なしで案件が起動します。
別ポートで開くなら `python serve.py 8200` のように引数指定。

> Windows では一部のポート (例 8123) が予約されていて `WinError 10013` になることがあります。
> その場合は 8080 / 8100 / 8200 など別のポートを使ってください。

## 構成

| ファイル | 役割 |
|---|---|
| index.html / krkrz.js / krkrz.wasm / krkrz.data | 共有エンジンバイナリ (案件非依存) |
| webconfig.js | 起動時構成 (webbase / 起動引数) |
| resource/ + resource.list | config.cf(文字コード) / messages / フォント |
| gamedata/ | 案件データ (web:// でオンデマンド取得) |
| gamedata.krkrz_files.json | autopath 用ファイル一覧マニフェスト |
| krkrz_prefetch.json | 起動後バックグラウンド先読みリスト (delivery:"prefetch" 指定時のみ) |

## 配信 (COOP/COEP 必須)

SharedArrayBuffer/pthread のため、配信サーバは以下ヘッダが必須:
`Cross-Origin-Opener-Policy: same-origin` / `Cross-Origin-Embedder-Policy: require-corp`
(同梱 `serve.py` は付与済み)。itch.io は「SharedArrayBuffer support」を有効にすれば配信可。

リクエスト URL は小文字に正規化されるため、case-sensitive なサーバに置く場合は
小文字→実ファイル名の解決が必要 (同梱 `serve.py` は対応済)。

## トラブル時: キャッシュのクリア

アセット更新後に古いデータが出る等の場合、URL に `?opfsclear=1` を付けて一度開くと
web:// の永続キャッシュ (OPFS) を全消しして起動する (セーブデータは消えない)。

## 再生成 (krkrz_web 側)

このサイトは krkrz_web の共有バイナリ + この案件の `web-config.json` から生成されています。
案件データや設定を更新したら、krkrz_web フォルダで再ステージング:

```
make PROJECT_DIR={project} run     # ステージング + ローカル起動
make PROJECT_DIR={project} web     # ステージングのみ (site を再生成)
```
'''


def js_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--data", default=None)
    ap.add_argument("--build-type", default="Release")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"[stage_web] PROJECT_DIR が無い: {project_dir}", file=sys.stderr)
        return 2

    ctx = make_ctx(project_dir)
    cfg = load_config(project_dir)
    res_dir = resolve_resource_dir(project_dir, cfg, ctx)
    ap_base, ap_sources = resolve_assetpack(cfg, project_dir, ctx, args.data)
    name = cfg.get("name", project_dir.name)
    default_args = " ".join(cfg.get("args", []))
    if args.port == 8100 and cfg.get("port"):
        args.port = int(cfg["port"])

    # 共有バイナリ (make build 済みが前提。cmake は呼ばない)
    krkrz_out = WEB_ROOT / "build" / "wasm32-emscripten" / args.build_type / "krkrz"
    if not (krkrz_out / "krkrz.wasm").exists():
        print(f"[stage_web] 共有バイナリが無い: {krkrz_out}\n"
              f"  先に krkrz_web で `make prebuild build` してください。",
              file=sys.stderr)
        return 2

    print(f"[stage_web] PROJECT_DIR = {project_dir}")
    print(f"[stage_web] name        = {name}")
    print(f"[stage_web] 共有バイナリ = {krkrz_out}")
    print(f"[stage_web] resource    = {res_dir}")
    print(f"[stage_web] assetPack   = {len(ap_sources)} source(s), base={ap_base}")
    print(f"[stage_web] extra args  = {default_args or '(なし=config.cf準拠)'}")
    if res_dir is None:
        print("[stage_web] 警告: resource が見つかりません (config.cf 無し)。"
              "engine 既定を使います。", file=sys.stderr)

    site = project_dir / "build" / "web" / "site"
    site.mkdir(parents=True, exist_ok=True)

    # 配置は全てハードリンク自動判定 (別ボリュームは copy に自動フォールバック)
    xfer = {"linked": 0, "copied": 0, "unchanged": 0, "removed": 0}

    # 1) 共有バイナリを配置 (krkrz.html → index.html)
    for f in ("krkrz.js", "krkrz.wasm", "krkrz.data"):
        link_or_copy(krkrz_out / f, site / f, xfer)
    link_or_copy(krkrz_out / "krkrz.html", site / "index.html", xfer)

    # 2) resource サイドカー (案件 resource → site/resource/ + resource.list)
    site_res = site / "resource"
    if site_res.exists():
        shutil.rmtree(site_res, ignore_errors=True)
    src_res = res_dir if res_dir is not None else (WEB_ROOT / ".." / "krkrz_dev" / "src" / "core" / "resource")
    src_res = Path(src_res).resolve()
    for root, _dirs, files in os.walk(src_res):
        rel = Path(root).relative_to(src_res)
        for nm in files:
            link_or_copy(Path(root) / nm, site_res / rel / nm, xfer)
    res_list = sorted(p.name for p in site_res.iterdir() if p.is_file())
    # resource.list は resource バンドルの「目次」= resource/ の兄弟として site 直下に置く
    # (pre.js は base 無しで fetch('resource.list') する)
    (site / "resource.list").write_text(json.dumps(res_list, ensure_ascii=False),
                                        encoding="utf-8")

    # 3) webconfig.js サイドカー (案件の webbase/args)
    webconfig = (
        "// 生成物 (stage_web.py): 案件の起動時構成。shell が krkrz.js より先に読む\n"
        "var KRKRZ_WEB_DATA_XP3 = false;\n"
        "var KRKRZ_WEB_DATA_PRELOAD = false;\n"
        "var KRKRZ_WEB_RESOURCE_BASE = \"resource/\";\n"
        f"var KRKRZ_WEB_DEFAULT_WEBBASE = {js_str('gamedata/')};\n"
        f"var KRKRZ_WEB_DEFAULT_ARGS = {js_str(default_args)};\n"
    )
    (site / "webconfig.js").write_text(webconfig, encoding="utf-8")

    # 4) gamedata (web:// 配信元) を sources マージで組む (ハードリンク自動判定)
    gamedata = site / "gamedata"
    # 旧構成が junction ならまず安全に外す (rmtree で target を消さないため)
    if gamedata.is_symlink():
        remove_dest(gamedata)
    print(f"[stage_web] gamedata を構成中 (sources マージ, ハードリンク自動判定)…")
    _expected, prefetch_rels = run_copy_rules(ap_sources, gamedata, ap_base, ctx,
                                              "gamedata", xfer)

    # 5) web:// autopath マニフェスト (組み上がった gamedata から生成)
    manifest = site / "gamedata.krkrz_files.json"
    if gamedata.is_dir():
        run([sys.executable, str(WEB_ROOT / "tools" / "gen_manifest.py"),
             str(gamedata), str(manifest)])
    else:
        manifest.write_text("[]", encoding="utf-8")

    # 5b) 先読みリスト (delivery:"prefetch" ソースのファイル一覧)。
    # パスはマニフェストと同じ正規化 (小文字・'/' 区切り) にする — エンジンの
    # web:// アクセス (autopath 経由 = マニフェスト由来の小文字パス) と
    # OPFS キーを一致させるため。pre.js が起動後に fetch→OPFS 保存する。
    prefetch_file = site / "krkrz_prefetch.json"
    if prefetch_rels:
        # 小文字化は ASCII のみ (gen_manifest / エンジン NormKey と同一規約)
        import string as _string
        _ascii_lower = str.maketrans(_string.ascii_uppercase, _string.ascii_lowercase)
        plist = sorted(r.translate(_ascii_lower) for r in prefetch_rels)
        prefetch_file.write_text(
            json.dumps(plist, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        print(f"[stage_web] prefetch     = {len(plist)} file(s) -> krkrz_prefetch.json")
    elif prefetch_file.exists():
        prefetch_file.unlink()

    # 6) serve.py + README.md
    (site / "serve.py").write_text(SERVE_TEMPLATE.format(port=args.port), encoding="utf-8")
    (site / "README.md").write_text(
        README_TEMPLATE.format(name=name, port=args.port, project=str(project_dir)),
        encoding="utf-8")

    print(f"\n[stage_web] 完了: {site}")
    print(f"[stage_web] 転送: {xfer['linked']} hardlink, {xfer['copied']} copy(fallback), "
          f"{xfer['unchanged']} unchanged, {xfer['removed']} removed")
    if xfer["copied"]:
        print("[stage_web] 注意: 一部がコピーにフォールバックしました "
              "(別ボリューム等でハードリンク不可)。site を data と同一ドライブに置くと軽量化されます。")
    print(f"[stage_web] 起動: python \"{site / 'serve.py'}\"  →  http://localhost:{args.port}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
