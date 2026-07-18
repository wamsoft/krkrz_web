#!/usr/bin/env python3
"""PROJECT_DIR ベースの web 版ステージング (krkrz_android の PROJECT_DIR 方式の web 版)。

案件フォルダの web-config.json (無ければ慣例) を読み、その resource (charset を含む
config.cf 等) で krkrz_web をビルドし、案件フォルダ配下 (${PROJECT_DIR}/build/web/site)
に実行用サーバ一式を出力する。エンジンは resource 非埋め込み (共有 wasm) なので、案件
差し替えは resource の preload (krkrz.data) 差分のみ。巨大 data は web:// でオンデマンド
配信する (preload しない)。

web-config.json (すべて任意。無指定は慣例で補完):
  {
    "name":     "marco",            // 表示名 (既定: フォルダ名)
    "resource": "setup/nxresource", // config.cf/messages/フォント (既定: setup/nxresource)
    "data":     "data",             // web:// 配信するゲームデータ (既定: data)
    "exclude":  [".bak", ".psd"],   // manifest 生成の除外拡張子
    "port":     8100                // 生成 serve.py の既定ポート
  }
※ Android の app-config.json とは別ファイル (名前衝突を避けるため web-config.json)。

  usage: python stage_web.py <PROJECT_DIR> [options]
    --data DIR        web:// 配信するゲームデータフォルダ (既定: PROJECT_DIR/data)
    --build-type T    Release (既定) / Debug
    --no-build        ビルドをスキップし、既存ビルド成果物をステージングだけする
    --port N          生成する serve.py の既定ポート (既定 8100)

出力: ${PROJECT_DIR}/build/web/site/  (この中の serve.py を実行すれば起動)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent   # krkrz_web/


def load_config(project_dir: Path) -> dict:
    cfg = project_dir / "web-config.json"
    if not cfg.exists():
        print(f"[stage_web] web-config.json が無いので慣例で続行: {cfg}")
        return {}
    return json.loads(cfg.read_text(encoding="utf-8"))


def resolve_resource_dir(project_dir: Path, cfg: dict) -> Path | None:
    """resource フォルダ (config.cf/messages.json/フォント等) を解決。

    web-config.json の "resource" 指定 → 慣例 (setup/nxresource) の順。
    charset はここの config.cf (readencoding=...) で決まる。
    """
    if cfg.get("resource"):
        p = project_dir / cfg["resource"]
        if (p / "config.cf").exists():
            return p
        print(f"[stage_web] 警告: 指定 resource に config.cf が無い: {p}", file=sys.stderr)
    # fallback: 慣例のパス
    for cand in ("setup/nxresource", "setup/andspec/res"):
        p = project_dir / cand
        if (p / "config.cf").exists():
            return p
    return None


def run(cmd, **kw):
    print("[stage_web] $", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, **kw)


SERVE_TEMPLATE = '''\
#!/usr/bin/env python3
# 生成物 (stage_web.py): 案件 web サイトの実行用サーバ。
#   - site/ 直下 (index.html / krkrz.js / krkrz.wasm / krkrz.data) を配信
#   - /gamedata/<path> を案件データフォルダから配信 (web:// オンデマンド取得元)
#   - /gamedata/krkrz_files.json は生成マニフェストを返す (autopath 用)
#   - SharedArrayBuffer/pthread 用に COOP/COEP を付与
import os, sys, posixpath
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = r"{data_dir}"
MANIFEST = os.path.join(SITE_DIR, "gamedata.krkrz_files.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else {port}

class H(SimpleHTTPRequestHandler):
    extensions_map = {{**SimpleHTTPRequestHandler.extensions_map,
                       '.wasm': 'application/wasm', '.mjs': 'text/javascript',
                       '.js': 'text/javascript'}}
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def translate_path(self, path):
        p = unquote(path.split('?', 1)[0].split('#', 1)[0])
        p = posixpath.normpath(p)
        if p == '/gamedata/krkrz_files.json':
            return MANIFEST
        prefix = '/gamedata/'
        if p.startswith(prefix):
            rel = p[len(prefix):]
            return os.path.join(DATA_DIR, *rel.split('/'))
        # それ以外は site/ 配下
        rel = p.lstrip('/')
        return os.path.join(SITE_DIR, *rel.split('/'))

print(f"serving  site={{SITE_DIR}}\\n         data={{DATA_DIR}}\\n  http://localhost:{{PORT}}/")
HTTPServer(('localhost', PORT), H).serve_forever()
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--data", default=None)
    ap.add_argument("--build-type", default="Release")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"[stage_web] PROJECT_DIR が無い: {project_dir}", file=sys.stderr)
        return 2

    cfg = load_config(project_dir)
    res_dir = resolve_resource_dir(project_dir, cfg)
    if args.data:
        data_dir = Path(args.data).resolve()
    else:
        data_dir = (project_dir / cfg.get("data", "data")).resolve()
    name = cfg.get("name", project_dir.name)
    excludes = cfg.get("exclude", [".bak", ".psd"])
    # 既定起動引数 (config.cf より優先)。既定は空 = 案件 resource の config.cf
    # 準拠。wasm32 は 2GB 上限なので、巨大プール (例 pc2 の bitmappoolsize=1280+
    # filepoolsize=384) の案件は web-config.json の "args" で縮小指定する。
    #   例: "args": ["-bitmappoolsize=640", "-filepoolsize=320", "-soundpoolsize=96"]
    extra_args = cfg.get("args", [])
    default_args = " ".join(extra_args)
    if args.port == 8100 and cfg.get("port"):
        args.port = int(cfg["port"])

    print(f"[stage_web] PROJECT_DIR = {project_dir}")
    print(f"[stage_web] name        = {name}")
    print(f"[stage_web] resource    = {res_dir}")
    print(f"[stage_web] data (web://)= {data_dir}")
    print(f"[stage_web] extra args  = {default_args}")
    if res_dir is None:
        print("[stage_web] 警告: resource が見つかりません (config.cf 無し)。"
              "engine 既定 (UTF-8) でビルドします。", file=sys.stderr)
    if not data_dir.is_dir():
        print(f"[stage_web] 警告: data フォルダが無い: {data_dir}", file=sys.stderr)

    build_dir = WEB_ROOT / "build" / "wasm32-emscripten" / args.build_type
    env = dict(os.environ)
    env.setdefault("EMSDK", "D:/work/emsdk")

    if not args.no_build:
        cfg_cmd = [
            "cmake", str(build_dir),
            "-DKRKRZ_WEB_DATA_PRELOAD=OFF",
            "-DKRKRZ_WEB_DEFAULT_WEBBASE=gamedata/",
            f"-DKRKRZ_WEB_DEFAULT_ARGS={default_args}",
        ]
        if res_dir is not None:
            cfg_cmd.append(f"-DKRKRZ_WEB_RESOURCE_DIR={res_dir.as_posix()}")
        else:
            cfg_cmd.append("-UKRKRZ_RESOURCE_DIR")
            cfg_cmd.append("-DKRKRZ_WEB_RESOURCE_DIR=")
        if not (build_dir / "CMakeCache.txt").exists():
            print(f"[stage_web] {build_dir} 未構成。先に `make prebuild` してください。",
                  file=sys.stderr)
            return 2
        run(cfg_cmd, env=env)
        run(["cmake", "--build", str(build_dir)], env=env)

    krkrz_out = build_dir / "krkrz"
    site = project_dir / "build" / "web" / "site"
    site.mkdir(parents=True, exist_ok=True)

    # バイナリ一式をコピー (krkrz.html → index.html)
    for f in ("krkrz.js", "krkrz.wasm", "krkrz.data"):
        src = krkrz_out / f
        if not src.exists():
            print(f"[stage_web] ビルド成果物が無い: {src}", file=sys.stderr)
            return 2
        shutil.copy2(src, site / f)
    shutil.copy2(krkrz_out / "krkrz.html", site / "index.html")

    # web:// autopath 用マニフェスト生成
    manifest = site / "gamedata.krkrz_files.json"
    if data_dir.is_dir():
        run([sys.executable, str(WEB_ROOT / "tools" / "gen_manifest.py"),
             str(data_dir), str(manifest), "--exclude", *excludes])
    else:
        manifest.write_text("[]", encoding="utf-8")

    # 実行用サーバスクリプト生成
    serve_py = site / "serve.py"
    serve_py.write_text(
        SERVE_TEMPLATE.format(data_dir=str(data_dir), port=args.port),
        encoding="utf-8")

    print(f"\n[stage_web] 完了: {site}")
    print(f"[stage_web] 起動: python \"{serve_py}\"  →  http://localhost:{args.port}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
