#!/usr/bin/env python3
"""底部 tabBar 图标生成器（零依赖：纯 Python + zlib 写 PNG）

为什么不用现成方案：小程序 tabBar 只认 PNG（不支持 SVG），
而项目里没有设计资源、也不该为 5 个图标引入 Pillow 依赖。
3 倍超采样 + 距离场判定，输出 81×81 抗锯齿图标（微信推荐尺寸）。

图标语言：实心几何（小程序 tabBar 尺寸小，实心比线性更易识别）
  解析 = 向下箭头入托盘      工具箱 = 四宫格
  热榜 = 三根柱（中间最高）  素材库 = 文件夹
  会员 = 皇冠

运行：python tools/gen_tabbar_icons.py
输出：miniapp/images/tabbar/{name}.png（默认色）+ {name}_on.png（选中色）
"""
import math
import os
import struct
import zlib

SIZE = 81
SS = 3                      # 超采样倍数
W = SIZE * SS
STROKE = 0.085              # 相对线宽

NORMAL = (0x9A, 0x90, 0x88, 255)     # 未选中：中性灰（浅/深底都可读）
ACTIVE = (0xD9, 0x7A, 0x26, 255)     # 选中：琥珀品牌色


# ── 画布 ──
def new_canvas():
    return [[0] * W for _ in range(W)]


def px(buf, x, y, rgb):
    if 0 <= x < W and 0 <= y < W:
        buf[y][x] = rgb


def fill_rect(buf, x0, y0, x1, y1, rgb, radius=0.0):
    """圆角矩形填充（坐标为 0..1 相对值）"""
    X0, Y0, X1, Y1 = x0 * W, y0 * W, x1 * W, y1 * W
    r = radius * W
    for yy in range(max(0, int(Y0)), min(W, int(math.ceil(Y1)) + 1)):
        for xx in range(max(0, int(X0)), min(W, int(math.ceil(X1)) + 1)):
            if r <= 0:
                inside = True
            else:
                cx = min(max(xx, X0 + r), X1 - r)
                cy = min(max(yy, Y0 + r), Y1 - r)
                d = math.hypot(xx - cx, yy - cy)
                inside = d <= r + 0.5
            if inside:
                px(buf, xx, yy, rgb)


def fill_poly(buf, pts, rgb):
    """多边形填充（扫描线奇偶规则）"""
    ys = [p[1] * W for p in pts]
    y_min = max(0, int(min(ys)))
    y_max = min(W - 1, int(math.ceil(max(ys))))
    n = len(pts)
    for yy in range(y_min, y_max + 1):
        yc = yy + 0.5
        xs = []
        for i in range(n):
            x1, y1 = pts[i][0] * W, pts[i][1] * W
            x2, y2 = pts[(i + 1) % n][0] * W, pts[(i + 1) % n][1] * W
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                xs.append(x1 + (yc - y1) / (y2 - y1) * (x2 - x1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for xx in range(max(0, int(xs[i])), min(W, int(xs[i + 1]) + 1)):
                px(buf, xx, yy, rgb)


def downsample(buf):
    """3×3 均值降采样 → 抗锯齿"""
    out = bytearray()
    for y in range(SIZE):
        out.append(0)                       # PNG filter type 0
        for x in range(SIZE):
            r = g = b = a = 0
            for dy in range(SS):
                for dx in range(SS):
                    p = buf[y * SS + dy][x * SS + dx]
                    if p:
                        r += p[0]; g += p[1]; b += p[2]; a += p[3]
            n = SS * SS
            if a == 0:
                out += bytes((0, 0, 0, 0))
            else:
                # 预乘还原（半透明边缘不产生黑边）
                cnt = sum(1 for dy in range(SS) for dx in range(SS)
                          if buf[y * SS + dy][x * SS + dx])
                out += bytes((r // cnt, g // cnt, b // cnt, a // n))
    return bytes(out)


def write_png(path, raw):
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


# ── 五个图标（0..1 相对坐标）──
def icon_parse(buf, c):
    """解析 = 视频窗 + 播放三角 + 下箭头（视频「取走」）

    比旧版「箭头入托盘」更贴解析语义，且与另外四图标
    （四宫格/三柱/文件夹/皇冠）图形语言不撞。
    播放三角用透明像素「打孔」实现（单色 PNG 无法混色）。
    """
    CLEAR = (0, 0, 0, 0)
    fill_rect(buf, 0.13, 0.14, 0.87, 0.60, c, 0.10)              # 视频窗
    fill_poly(buf, [(0.40, 0.27), (0.40, 0.47), (0.58, 0.37)], CLEAR)  # 播放孔
    fill_rect(buf, 0.455, 0.66, 0.545, 0.82, c, 0.03)            # 箭杆
    fill_poly(buf, [(0.33, 0.80), (0.67, 0.80), (0.5, 0.96)], c)  # 箭头


def icon_tools(buf, c):
    for x in (0.16, 0.56):
        for y in (0.16, 0.56):
            fill_rect(buf, x, y, x + 0.28, y + 0.28, c, 0.09)


def icon_rank(buf, c):
    fill_rect(buf, 0.16, 0.56, 0.34, 0.86, c, 0.055)
    fill_rect(buf, 0.41, 0.32, 0.59, 0.86, c, 0.055)
    fill_rect(buf, 0.66, 0.46, 0.84, 0.86, c, 0.055)


def icon_library(buf, c):
    fill_rect(buf, 0.14, 0.22, 0.46, 0.34, c, 0.05)               # 文件夹标签
    fill_rect(buf, 0.14, 0.34, 0.86, 0.80, c, 0.09)               # 文件夹体


def icon_member(buf, c):
    """「我的」= 人形（圆头 + 肩膀弧）。
    tab 文案已从「会员」改为「我的」（2026-10-07 用户拍板），
    皇冠是会员语义、与「我的」错位，换人形。文件名保持 member.png 不变。"""
    fill_rect(buf, 0.34, 0.10, 0.66, 0.42, c, 0.16)                # 头（正圆）
    fill_rect(buf, 0.18, 0.50, 0.82, 0.88, c, 0.17)                # 肩（上缘大圆角）


ICONS = {
    'parse': icon_parse,
    'tools': icon_tools,
    'rank': icon_rank,
    'library': icon_library,
    'member': icon_member,
}

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'miniapp', 'images', 'tabbar')


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in ICONS.items():
        for suffix, color in (('', NORMAL), ('_on', ACTIVE)):
            buf = new_canvas()
            fn(buf, color)
            path = os.path.join(OUT, f'{name}{suffix}.png')
            write_png(path, downsample(buf))
            print(f'  {os.path.basename(path):18s} {os.path.getsize(path)} B')
    print(f'\n共 {len(ICONS) * 2} 个图标 → {OUT}')


if __name__ == '__main__':
    main()
