#!/usr/bin/env python3
"""簡易 XP3 アーカイバ / 展開ツール

吉里吉里の XP3 アーカイブを作成・検査・展開する。
フォーマットは krkrz core (common/base/XP3Archive.cpp) の読み込み実装準拠:

  ヘッダ  : 11 バイトマジック + int64LE インデックス絶対オフセット
  インデックス: 1 バイトフラグ (0=raw / 1=zlib, 0x80=継続) +
            zlib 時: int64 圧縮サイズ + int64 元サイズ + zlib データ
  チャンク : 名前 4 バイト + int64 ペイロードサイズ + ペイロード
    File > info: uint32 flags, int64 元サイズ, int64 格納サイズ,
                 uint16 ファイル名文字数, UTF-16LE ファイル名
    File > segm: セグメント配列 (28 バイト each):
                 uint32 flags(0=raw/1=zlib), int64 絶対オフセット,
                 int64 元サイズ, int64 格納サイズ
    File > adlr: uint32 adler32 (元データ)

usage:
  python xp3pack.py pack <srcdir> <out.xp3> [--no-compress] [--protect]
  python xp3pack.py list <archive.xp3>
  python xp3pack.py extract <archive.xp3> <outdir>
"""
import argparse
import os
import struct
import sys
import zlib

XP3_MAGIC = bytes((0x58, 0x50, 0x33, 0x0D, 0x0A, 0x20, 0x0A, 0x1A, 0x8B, 0x67, 0x01))

# 既に圧縮済みの形式は格納のみ (zlib をかけても縮まらない)
STORE_EXTS = {
    '.png', '.jpg', '.jpeg', '.webp', '.tlg',
    '.ogg', '.opus', '.mp3', '.m4a',
    '.mp4', '.webm', '.mkv',
    '.xp3', '.zip', '.7z', '.gz',
}


def chunk(name: bytes, payload: bytes) -> bytes:
    assert len(name) == 4
    return name + struct.pack('<Q', len(payload)) + payload


def collect_files(srcdir: str):
    result = []
    for root, dirs, names in os.walk(srcdir):
        dirs.sort()
        for n in sorted(names):
            full = os.path.join(root, n)
            rel = os.path.relpath(full, srcdir).replace('\\', '/')
            result.append((rel, full))
    return result


def cmd_pack(args) -> int:
    files = collect_files(args.srcdir)
    if not files:
        print(f'error: no files under {args.srcdir}', file=sys.stderr)
        return 1

    index = bytearray()
    with open(args.output, 'wb') as f:
        f.write(XP3_MAGIC)
        f.write(struct.pack('<Q', 0))  # インデックスオフセット (後で書き戻す)

        for rel, full in files:
            with open(full, 'rb') as src:
                data = src.read()
            adler = zlib.adler32(data) & 0xFFFFFFFF

            stored = data
            seg_flags = 0  # raw
            ext = os.path.splitext(rel)[1].lower()
            if not args.no_compress and data and ext not in STORE_EXTS:
                comp = zlib.compress(data, 9)
                if len(comp) < len(data):
                    stored = comp
                    seg_flags = 1  # zlib

            start = f.tell()
            f.write(stored)

            name16 = rel.encode('utf-16-le')
            info = struct.pack('<IQQH',
                               0x80000000 if args.protect else 0,
                               len(data), len(stored),
                               len(name16) // 2) + name16
            segm = struct.pack('<IQQQ', seg_flags, start, len(data), len(stored))
            adlr = struct.pack('<I', adler)
            index += chunk(b'File',
                           chunk(b'info', info) +
                           chunk(b'segm', segm) +
                           chunk(b'adlr', adlr))
            mark = 'z' if seg_flags else '-'
            print(f'  {mark} {rel} ({len(data)} -> {len(stored)})')

        index_ofs = f.tell()
        zindex = zlib.compress(bytes(index), 9)
        f.write(struct.pack('<B', 1))  # zlib インデックス
        f.write(struct.pack('<QQ', len(zindex), len(index)))
        f.write(zindex)
        f.seek(11)
        f.write(struct.pack('<Q', index_ofs))

    print(f'packed {len(files)} file(s) -> {args.output}')
    return 0


def read_index(path: str):
    """(entries, f) を返す。entry = (name, org_size, segments, adler)"""
    f = open(path, 'rb')
    magic = f.read(11)
    if magic != XP3_MAGIC:
        raise ValueError('not an XP3 archive (bad magic)')
    (index_ofs,) = struct.unpack('<Q', f.read(8))
    f.seek(index_ofs)
    (flag,) = struct.unpack('<B', f.read(1))
    if flag & 0x07 == 1:
        csize, osize = struct.unpack('<QQ', f.read(16))
        index = zlib.decompress(f.read(csize))
        assert len(index) == osize
    elif flag & 0x07 == 0:
        (osize,) = struct.unpack('<Q', f.read(8))
        index = f.read(osize)
    else:
        raise ValueError(f'unknown index encoding {flag}')

    entries = []
    pos = 0
    while pos + 12 <= len(index):
        cname = index[pos:pos + 4]
        (csize,) = struct.unpack_from('<Q', index, pos + 4)
        body_start = pos + 12
        if cname == b'File':
            sub = {}
            p = body_start
            while p + 12 <= body_start + csize:
                sn = index[p:p + 4]
                (ssz,) = struct.unpack_from('<Q', index, p + 4)
                sub[sn] = index[p + 12:p + 12 + ssz]
                p += 12 + ssz
            info = sub[b'info']
            flags, org, arc, namelen = struct.unpack_from('<IQQH', info, 0)
            name = info[22:22 + namelen * 2].decode('utf-16-le')
            segs = []
            segm = sub[b'segm']
            for i in range(len(segm) // 28):
                segs.append(struct.unpack_from('<IQQQ', segm, i * 28))
            (adler,) = struct.unpack_from('<I', sub[b'adlr'], 0)
            entries.append((name, org, segs, adler))
        pos = body_start + csize
    return entries, f


def cmd_list(args) -> int:
    entries, f = read_index(args.archive)
    f.close()
    for name, org, segs, adler in entries:
        comp = 'z' if any(s[0] & 7 for s in segs) else '-'
        print(f'  {comp} {name} ({org} bytes, adler32={adler:08x}, {len(segs)} seg)')
    print(f'{len(entries)} file(s)')
    return 0


def cmd_extract(args) -> int:
    entries, f = read_index(args.archive)
    try:
        for name, org, segs, adler in entries:
            data = bytearray()
            for seg_flags, start, orgsz, arcsz in segs:
                f.seek(start)
                raw = f.read(arcsz)
                data += zlib.decompress(raw) if (seg_flags & 7) == 1 else raw
            if len(data) != org or (zlib.adler32(bytes(data)) & 0xFFFFFFFF) != adler:
                print(f'error: verify failed: {name}', file=sys.stderr)
                return 1
            out = os.path.join(args.outdir, name.replace('/', os.sep))
            os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
            with open(out, 'wb') as o:
                o.write(data)
            print(f'  {name} ({org} bytes) OK')
    finally:
        f.close()
    print(f'extracted {len(entries)} file(s) -> {args.outdir}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='simple XP3 archiver')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('pack', help='フォルダを XP3 にパック')
    p.add_argument('srcdir')
    p.add_argument('output')
    p.add_argument('--no-compress', action='store_true', help='全ファイル無圧縮格納')
    p.add_argument('--protect', action='store_true', help='protected フラグを立てる')
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser('list', help='アーカイブ内容を一覧')
    p.add_argument('archive')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('extract', help='展開 + adler32 検証')
    p.add_argument('archive')
    p.add_argument('outdir')
    p.set_defaults(func=cmd_extract)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
