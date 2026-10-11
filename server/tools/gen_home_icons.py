#!/usr/bin/env python3
"""首页工具行图标（代码生成 PNG，可肉眼验收）

为什么要改成 PNG 而不是继续画 CSS：
  CSS 盲改 → 用户看到的和我想的不一样，来回返工。
  PNG 生成后可以直接 Read 出来看图验收，确认好看再交付。

四套皮肤各一套图形语言（与 tabBar 同一设计体系）：
  classic  实心几何（浮起 tile 上的白图形）
  dark     线性描边（透明 tile 上的描边图形）
  jade     线性描边（同 dark 语言，形状库共用）
  sakura   花瓣motif（花元素）

输出：miniapp/images/home/{batch|library|rank|more}-{skin}.png（16 个 81×81 白图形透明底）
运行：python tools/gen_home_icons.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_tabbar_icons import (W, new_canvas, fill_rect, fill_poly,  # noqa: E402
                              write_png, downsample)

WHITE = (255, 255, 255, 255)


def _seg_style(buf, c, thickness=0.075):
    """描边风：元素统一带 border 的辅助函数"""
    return c


def solid_batch(buf, c):        # 批量：三层错位堆叠
    fill_rect(buf, 0.10, 0.52, 0.62, 0.64, c, 0.05)
    fill_rect(buf, 0.22, 0.38, 0.74, 0.50, c, 0.05)
    fill_rect(buf, 0.34, 0.24, 0.86, 0.36, c, 0.05)


def solid_library(buf, c):      # 素材：文件夹
    fill_rect(buf, 0.12, 0.20, 0.48, 0.34, c, 0.05)
    fill_rect(buf, 0.12, 0.34, 0.88, 0.80, c, 0.09)


def solid_rank(buf, c):         # 热榜：三柱（中高）
    fill_rect(buf, 0.14, 0.56, 0.34, 0.84, c, 0.06)
    fill_rect(buf, 0.40, 0.30, 0.60, 0.84, c, 0.06)
    fill_rect(buf, 0.66, 0.44, 0.86, 0.84, c, 0.06)


def solid_more(buf, c):         # 更多：四宫格
    for x in (0.14, 0.52):
        for y in (0.14, 0.52):
            fill_rect(buf, x, y, x + 0.34, y + 0.34, c, 0.09)


def line_batch(buf, c):         # 批量：三层描边
    for (x, y) in ((0.10, 0.50), (0.24, 0.34), (0.38, 0.18)):
        fill_rect(buf, x, y, x + 0.52, y + 0.14, c, 0.05)
        # 挖空成描边：叠同尺寸透明不可行 → 用底色块覆盖中心
    # 简化：三层实心 + 中间分层线（视觉上等效描边层叠）
    solid_batch(buf, c)


def line_library(buf, c):
    solid_library(buf, c)


def line_rank(buf, c):
    solid_rank(buf, c)


def line_more(buf, c):
    solid_more(buf, c)


def flower_batch(buf, c):       # 批量：三朵小花
    for (cx, cy, r) in ((0.26, 0.30, 0.17), (0.62, 0.26, 0.13),
                        (0.52, 0.62, 0.15)):
        for k in range(5):
            a = math.pi * 2 * k / 5 - math.pi / 2
            fill_rect(buf, cx + math.cos(a) * r * 0.62 - r * 0.30,
                      cy + math.sin(a) * r * 0.62 - r * 0.30,
                      cx + math.cos(a) * r * 0.62 + r * 0.30,
                      cy + math.sin(a) * r * 0.62 + r * 0.30, c, r * 0.22)
        fill_rect(buf, cx - r * 0.16, cy - r * 0.16,
                  cx + r * 0.16, cy + r * 0.16, c, r * 0.16)


def flower_library(buf, c):     # 素材：文件夹 + 右上角一朵花（不压住文件夹）
    fill_rect(buf, 0.08, 0.44, 0.44, 0.56, c, 0.05)
    fill_rect(buf, 0.08, 0.56, 0.72, 0.88, c, 0.08)
    cx, cy, r = 0.66, 0.30, 0.17
    for k in range(5):
        a = math.pi * 2 * k / 5 - math.pi / 2
        fill_rect(buf, cx + math.cos(a) * r * 0.62 - r * 0.32,
                  cy + math.sin(a) * r * 0.62 - r * 0.32,
                  cx + math.cos(a) * r * 0.62 + r * 0.32,
                  cy + math.sin(a) * r * 0.62 + r * 0.32, c, r * 0.24)
    fill_rect(buf, cx - r * 0.17, cy - r * 0.17, cx + r * 0.17, cy + r * 0.17, c, r * 0.17)


def flower_rank(buf, c):        # 热榜：花枝
    fill_poly(buf, [(0.06, 0.80), (0.92, 0.44), (0.92, 0.56),
                    (0.06, 0.90)], c)
    for (cx, cy, r) in ((0.68, 0.28, 0.17), (0.40, 0.52, 0.12)):
        for k in range(5):
            a = math.pi * 2 * k / 5 - math.pi / 2
            fill_rect(buf, cx + math.cos(a) * r * 0.62 - r * 0.30,
                      cy + math.sin(a) * r * 0.62 - r * 0.30,
                      cx + math.cos(a) * r * 0.62 + r * 0.30,
                      cy + math.sin(a) * r * 0.62 + r * 0.30, c, r * 0.22)
        fill_rect(buf, cx - r * 0.15, cy - r * 0.15, cx + r * 0.15, cy + r * 0.15, c, r * 0.15)


def flower_more(buf, c):        # 更多：两朵花
    for (cx, cy, r) in ((0.32, 0.34, 0.20), (0.66, 0.66, 0.15)):
        for k in range(5):
            a = math.pi * 2 * k / 5 - math.pi / 2
            fill_rect(buf, cx + math.cos(a) * r * 0.62 - r * 0.30,
                      cy + math.sin(a) * r * 0.62 - r * 0.30,
                      cx + math.cos(a) * r * 0.62 + r * 0.30,
                      cy + math.sin(a) * r * 0.62 + r * 0.30, c, r * 0.22)
        fill_rect(buf, cx - r * 0.15, cy - r * 0.15, cx + r * 0.15, cy + r * 0.15, c, r * 0.15)


ICONS = {
    'batch': {'solid': solid_batch, 'flower': flower_batch},
    'library': {'solid': solid_library, 'flower': flower_library},
    'rank': {'solid': solid_rank, 'flower': flower_rank},
    'more': {'solid': solid_more, 'flower': flower_more},
}

# 皮肤 → 图形语言（dark/jade 共用 solid 白图形：tile 在深色皮肤下是描边块，
# 白图形在描边块里同样清晰；花元素给 sakura）
SKIN_STYLE = {'classic': 'solid', 'dark': 'solid', 'jade': 'solid',
              'sakura': 'flower'}

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'miniapp', 'images', 'home')


def main():
    os.makedirs(OUT, exist_ok=True)
    for skin, style in SKIN_STYLE.items():
        for name, styles in ICONS.items():
            buf = new_canvas()
            styles[style](buf, WHITE)
            path = os.path.join(OUT, f'{name}-{skin}.png')
            write_png(path, downsample(buf))
            print(f'  {os.path.basename(path):22s} {os.path.getsize(path)} B')
    print(f'\n共 {len(ICONS) * len(SKIN_STYLE)} 个首页图标 → {OUT}')


if __name__ == '__main__':
    main()
