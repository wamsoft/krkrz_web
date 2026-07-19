#!/usr/bin/env python3
"""web:// メディア用ファイル一覧マニフェスト生成

krkrz の自動検索パス (addAutoPath) は、フォルダのファイル一覧を GetListAt で
取得して検索テーブルを構築する。サーバ上のバラファイル配信ではディレクトリ
列挙ができないため、ビルド時にファイル一覧を JSON マニフェストに書き出し、
web:// メディアがそれを参照して CheckExistentStorage / GetListAt を解決する。

出力: <outfile> に、パス (小文字、'/' 区切り、先頭 './' 無し) の JSON 配列。
      TVP_AUTOPATH_IGNORECASE 前提で小文字化しておく。
      小文字化は ASCII のみ (エンジン側 HttpStorageMedia::NormKey と同一規約。
      Python の str.lower() は全角英字等まで変換してしまい照合がズレるため)。

usage: python gen_manifest.py <srcdir> <outfile> [--exclude PAT ...]
"""
import argparse
import json
import os
import string
import sys

ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("srcdir")
    ap.add_argument("outfile")
    ap.add_argument("--exclude", nargs="*", default=[],
                    help="除外する拡張子 (例 .bak .psd)")
    args = ap.parse_args()

    excl = tuple(e.lower() for e in args.exclude)
    files = []
    for root, dirs, names in os.walk(args.srcdir):
        dirs.sort()
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(root, n), args.srcdir)
            rel = rel.replace("\\", "/").translate(ASCII_LOWER)
            if excl and rel.endswith(excl):
                continue
            # マニフェスト自身は含めない
            if rel == os.path.basename(args.outfile).lower():
                continue
            files.append(rel)

    with open(args.outfile, "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, separators=(",", ":"))
    print(f"manifest: {len(files)} file(s) -> {args.outfile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
