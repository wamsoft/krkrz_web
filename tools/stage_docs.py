#!/usr/bin/env python3
"""静的ホスト (GitHub Pages 等) 埋め込み用の資材ステージング。

`make build` 済みの共有バイナリ + サイドカーを、**coi-serviceworker 同梱の
自己完結ディレクトリ**として任意の出力先へ配置する。ドキュメント (mkdocs 等) の
`_assets/` へ置いて iframe 埋め込み or 直リンクで動かす用途。

stage_web.py との違い:
  - stage_web.py … 案件 (PROJECT_DIR) を web:// オンデマンド配信 + serve.py
                   (COOP/COEP を返す専用サーバ) 前提でステージング。
  - stage_docs.py … **ヘッダを設定できない静的ホスト**前提。COOP/COEP は
                   coi-serviceworker (SW) でクライアント側に注入する。データは
                   preload (krkrz.data 同梱) をそのまま使う (web:// 不要)。

配置物 (出力ディレクトリ):
  index.html            … krkrz.html を改名し、先頭に coi-serviceworker を注入
  coi-serviceworker.js  … COOP/COEP を注入する SW (既定で同梱・同ディレクトリ参照)
  krkrz.js / .wasm / .data          … 共有エンジンバイナリ + preload データ
  webconfig.js / resource.list / resource/  … 起動時構成・エンジンリソース

前提: 先に共有バイナリをビルドしておく。
  export EMSDK=/path/to/emsdk; source $EMSDK/emsdk_env.sh
  cmake --preset wasm32-emscripten -DCMAKE_BUILD_TYPE=Release   # 初回のみ
  cmake --build build/wasm32-emscripten/Release
埋め込むデモ/案件データを変えたいときは -DKRKRZ_WEB_DATA_DIR=<dir> でビルドし直す。

usage:
  python tools/stage_docs.py <output_dir> [options]
    --build-type T   Release (既定) / Debug — 参照する共有バイナリ
    --coi-href HREF  index.html に注入する coi-serviceworker の src を上書きする。
                     既定は同ディレクトリの "coi-serviceworker.js" を同梱参照。
                     例: サイト直下の SW を共有する場合 --coi-href ../../coi-serviceworker.js
                     (この場合 SW ファイルは同梱せず、参照先に別途置く前提)
    --no-coi         coi-serviceworker を同梱も注入もしない (親側で全ページ登録
                     する等、埋め込み側で隔離を用意する場合)
    --clean          出力先の既存 krkrz.* / resource/ を消してから配置する

出力後、mkdocs 等での iframe 埋め込みには **親ページも crossOriginIsolated**
である必要がある (子 iframe の隔離は親の隔離が前提)。mkdocs なら
`extra_javascript` にサイト直下の coi-serviceworker.js を足して全ページに適用する。
直リンク / 別タブ表示だけなら本ツールの自己完結ディレクトリ単体で動く。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# 出力先へ配置する共有バイナリ + サイドカー (存在するものだけコピー)。
BINARY_FILES = ["krkrz.js", "krkrz.wasm", "krkrz.data"]
SIDECAR_FILES = ["webconfig.js", "resource.list"]
SIDECAR_DIRS = ["resource"]
COI_FILENAME = "coi-serviceworker.js"


def find_build_dir(build_type: str) -> Path:
    d = REPO / "build" / "wasm32-emscripten" / build_type / "krkrz"
    if not (d / "krkrz.html").is_file():
        sys.exit(
            f"[stage_docs] 共有バイナリが見つかりません: {d}/krkrz.html\n"
            f"  先に emsdk を通して `cmake --build build/wasm32-emscripten/{build_type}` を実行してください。"
        )
    return d


def inject_coi(html: str, coi_href: str | None) -> str:
    """<title>...</title> の直後に coi-serviceworker の <script> を差し込む。
    krkrz.html は minify 済み 1 行なので </title> をアンカーにする。"""
    if coi_href is None:
        return html
    tag = f'<script src="{coi_href}"></script>'
    anchor = "</title>"
    idx = html.find(anchor)
    if idx < 0:
        # 予期しない構造: <head> 直後にフォールバック
        anchor = "<head>"
        idx = html.find(anchor)
        if idx < 0:
            sys.exit("[stage_docs] index.html に <title>/<head> が見つからず coi を注入できません。")
    pos = idx + len(anchor)
    return html[:pos] + tag + html[pos:]


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser(description="静的ホスト埋め込み用の資材ステージング")
    ap.add_argument("output_dir", help="配置先ディレクトリ (例: <krkrz_dev>/doc/_assets/demo)")
    ap.add_argument("--build-type", default="Release", help="Release (既定) / Debug")
    ap.add_argument("--coi-href", default=COI_FILENAME,
                    help=f'index.html に注入する SW の src (既定: {COI_FILENAME})')
    ap.add_argument("--no-coi", action="store_true", help="coi-serviceworker を同梱も注入もしない")
    ap.add_argument("--clean", action="store_true", help="既存の krkrz.*/resource/ を消してから配置")
    args = ap.parse_args()

    build_dir = find_build_dir(args.build_type)
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if args.clean:
        for name in BINARY_FILES + SIDECAR_FILES + ["index.html", COI_FILENAME]:
            p = out / name
            if p.exists():
                p.unlink()
        for d in SIDECAR_DIRS:
            shutil.rmtree(out / d, ignore_errors=True)

    copied = []

    # 共有バイナリ + サイドカー (存在するものだけ)
    for name in BINARY_FILES + SIDECAR_FILES:
        src = build_dir / name
        if src.is_file():
            copy_file(src, out / name)
            copied.append(name)
    for d in SIDECAR_DIRS:
        srcd = build_dir / d
        if srcd.is_dir():
            dstd = out / d
            shutil.rmtree(dstd, ignore_errors=True)
            shutil.copytree(srcd, dstd)
            copied.append(d + "/")

    # web:// 配信 (gamedata) 構成のビルドを検出したら注意を促す
    if not (build_dir / "krkrz.data").is_file():
        print("[stage_docs] 注意: krkrz.data (preload) がありません。web:// 配信構成の可能性があります。\n"
              "  静的ホスト埋め込みは preload 構成 (既定サンプル) を推奨します。gamedata/ を使う場合は\n"
              "  別途 gamedata とマニフェストの配置が必要です (stage_web.py を参照)。", file=sys.stderr)

    # coi-serviceworker
    coi_href = None if args.no_coi else args.coi_href
    if not args.no_coi and args.coi_href == COI_FILENAME:
        # 同梱参照: テンプレートを出力先へコピー
        tpl = HERE / COI_FILENAME
        if not tpl.is_file():
            sys.exit(f"[stage_docs] coi テンプレートが見つかりません: {tpl}")
        copy_file(tpl, out / COI_FILENAME)
        copied.append(COI_FILENAME)

    # index.html (krkrz.html を改名 + coi 注入)
    html = (build_dir / "krkrz.html").read_text(encoding="utf-8")
    html = inject_coi(html, coi_href)
    (out / "index.html").write_text(html, encoding="utf-8")
    copied.append("index.html")

    print(f"[stage_docs] 配置完了: {out}")
    for name in copied:
        print(f"  + {name}")
    print()
    print("次のステップ:")
    print(f"  - 直リンク / 別タブ: {out.name}/ を開けば単体で動く (coi 同梱・secure context 必須)")
    print("  - iframe 埋め込み: 親ページも crossOriginIsolated が必要。mkdocs なら")
    print("    サイト直下に coi-serviceworker.js を置き extra_javascript で全ページ登録する。")


if __name__ == "__main__":
    main()
