#!/usr/bin/env python3
"""首页图标合成预览图：把 16 个图标贴到各自皮肤的色块上（可直接肉眼验收）"""
import os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_tabbar_icons import SIZE, SS, W, new_canvas, fill_rect, fill_poly, write_png, downsample
from gen_home_icons import ICONS, SKIN_STYLE

BG = (18, 16, 14, 255)
PAGE = (247, 242, 234, 255)
TILES = {   # 各皮肤 tile 底色（近似实际渐变中段）
  'classic': (222, 138, 48, 255),
  'dark':    (26, 26, 32, 255),
  'jade':    (32, 92, 74, 255),
  'sakura':  (240, 150, 180, 255),
}
TILE = 120; PAD = 16; COLS = 4; ROWS = 4
IW = COLS * TILE + (COLS + 1) * PAD
IH = ROWS * TILE + (ROWS + 1) * PAD


def read_png_rgba(path):
    """读本脚本自己生成的 PNG（filter0, RGBA8）"""
    data = open(path, 'rb').read()
    pos, w, h, idat = 8, 0, 0, b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b'IHDR':
            w, h = struct.unpack('>II', body[:8])
        elif tag == b'IDAT':
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    rows, stride, off = [], w * 4 + 1, 0
    for _ in range(h):
        rows.append(raw[off + 1:off + 1 + w * 4]); off += stride
    return w, h, rows


def paste(dst, src_rows, sw, sh, x0, y0):
    for y in range(sh):
        for x in range(sw):
            p = src_rows[y][x * 4:x * 4 + 4]
            if p[3] == 0: continue
            a = p[3] / 255
            X, Y = x0 + x, y0 + y
            if 0 <= X < IW and 0 <= Y < IH:
                i = (Y * IW + X) * 4          # dst 是扁平 bytearray
                d = dst[i:i + 4]
                dst[i:i + 4] = bytes((
                    int(p[0] * a + d[0] * (1 - a)),
                    int(p[1] * a + d[1] * (1 - a)),
                    int(p[2] * a + d[2] * (1 - a)), 255))


OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'miniapp', 'images', 'home')


def main():
    canvas = [[BG[i] for i in range(4)] for _ in range(IW * IH)]
    flat = [px for row in canvas for px in row]
    names = list(ICONS.keys())
    for ri, skin in enumerate(SKIN_STYLE):
        y0 = PAD + ri * (TILE + PAD)
        for ci, name in enumerate(names):
            x0 = PAD + ci * (TILE + PAD)
            for y in range(TILE):
                for x in range(TILE):
                    # 圆角 tile
                    cx = min(max(x, 18), TILE - 18); cy = min(max(y, 18), TILE - 18)
                    import math
                    inside = (x < 18 or x > TILE - 19 or y < 18 or y > TILE - 19
                              or math.hypot(x - cx, y - cy) <= 18)
                    if inside:
                        px = (x0 + x) * 4; py = (y0 + y) * 4
                        flat[py:py + 4] = bytes(TILES[skin])
            sw, sh, rows = read_png_rgba(os.path.join(OUT, f'{name}-{skin}.png'))
            paste(flat, rows, sw, sh, x0 + (TILE - SIZE) // 2, y0 + (TILE - SIZE) // 2)
    # 打包成 PNG（filter 0）
    raw = bytearray()
    for y in range(IH):
        raw.append(0)
        raw += bytes(flat[y * IW * 4:(y + 1) * IW * 4])
    import struct as _s, zlib as _z

    def chunk(tag, data):
        c = _s.pack('>I', len(data)) + tag + data
        return c + _s.pack('>I', _z.crc32(tag + data) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', _s.pack('>IIBBBBB', IW, IH, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', _z.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    path = os.path.join(OUT, '_sheet.png')
    open(path, 'wb').write(png)
    print(f'_sheet.png {IW}x{IH} → {path}')


if __name__ == '__main__':
    main()
