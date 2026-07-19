#!/usr/bin/env python3
"""krkrz wasm 開発用サーバ。

SharedArrayBuffer (pthread ビルド) に必要な COOP/COEP ヘッダを付けて
ビルド出力フォルダを配信する。<video> ストリーミング (VideoOverlay) 用に
HTTP Range リクエスト (単一レンジ) とマルチスレッド配信に対応。

usage: python web/serve.py <docroot> [port]
"""
import os
import re
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


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
        # <video> のシークに Range を使わせる
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def do_GET(self):
        # Range 対応 (単一レンジのみ。<video> のシーク/ストリーミング用)
        rh = self.headers.get('Range')
        path = self.translate_path(self.path)
        if rh and os.path.isfile(path):
            self.send_range(path, rh)
        else:
            super().do_GET()

    def send_range(self, path, rh):
        size = os.path.getsize(path)
        m = re.match(r'bytes=(\d*)-(\d*)$', rh.strip())
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
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
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


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    os.chdir(root)
    print(f'serving {os.getcwd()}')
    print(f'  -> http://localhost:{port}/krkrz.html')
    ThreadingHTTPServer(('localhost', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
