#!/usr/bin/env python3
"""krkrz wasm 開発用サーバ。

SharedArrayBuffer (pthread ビルド) に必要な COOP/COEP ヘッダを付けて
ビルド出力フォルダを配信する。

usage: python web/serve.py <docroot> [port]
"""
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.wasm': 'application/wasm',
        '.mjs': 'text/javascript',
    }

    def end_headers(self):
        # SharedArrayBuffer (pthread) 用
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        # 開発用: 常に最新を読む
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    os.chdir(root)
    print(f'serving {os.getcwd()}')
    print(f'  -> http://localhost:{port}/krkrz.html')
    HTTPServer(('localhost', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
