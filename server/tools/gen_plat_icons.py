#!/usr/bin/env python3
"""平台标签小图标（支持平台标签区，文字前缀）

设计约束：
  · 显示尺寸极小（约 26rpx ≈ 14px）→ 全部实心剪影，粗壮可辨，不用描边
  · 颜色 = 各皮肤 --ink-700（tag 底是 --bg-soft，同皮肤下必然可读）
  · 8 平台 × 4 皮肤 = 32 个 PNG（81×81 透明底）
  · 与现有图形不撞：抖音=音符 / B站=小电视 / 好看=圆环播放 /
    微博=眼睛 / AcFun=A / 小红书=翻开的书 / 快手=取景框播放 / 搜狐=四角星

输出：miniapp/images/plat/{key}-{skin}.png
运行：python tools/gen_plat_icons.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_tabbar_icons import (W, new_canvas, fill_rect, fill_poly,  # noqa: E402
                              write_png, downsample)

# 各皮肤 --ink-700（与 app.wxss 同步；改皮肤色后重跑本脚本）
SKIN_INK = {
    'classic': (0x4F, 0x44, 0x3A, 255),
    'dark':    (0xC6, 0xBF, 0xB4, 255),
    'jade':    (0xB9, 0xC9, 0xC2, 255),
    'sakura':  (0x5A, 0x41, 0x4B, 255),
}
CLEAR = (0, 0, 0, 0)


def circle(buf, c, cx, cy, r, n=24):
    """圆的多边形近似（生成器只有 fill_poly/fill_rect）"""
    fill_poly(buf, [(cx + r * math.cos(2 * math.pi * i / n),
                     cy + r * math.sin(2 * math.pi * i / n))
                    for i in range(n)], c)


def ico_douyin(buf, c):
    """抖音：音符（竖杆 + 右上旗 + 底部圆头）"""
    fill_rect(buf, 0.40, 0.08, 0.56, 0.62, c, 0.06)                 # 竖杆
    fill_poly(buf, [(0.56, 0.08), (0.56, 0.26), (0.84, 0.34),
                    (0.84, 0.16)], c)                                # 旗
    circle(buf, c, 0.30, 0.74, 0.18)                                 # 圆头


def ico_bilibili(buf, c):
    """B站：小电视（机身 + 双天线 + 屏幕孔）"""
    fill_poly(buf, [(0.26, 0.06), (0.32, 0.04), (0.44, 0.26),
                    (0.38, 0.28)], c)                                # 左天线
    fill_poly(buf, [(0.68, 0.04), (0.74, 0.06), (0.62, 0.28),
                    (0.56, 0.26)], c)                                # 右天线
    fill_rect(buf, 0.10, 0.30, 0.90, 0.84, c, 0.10)                  # 机身
    fill_rect(buf, 0.24, 0.44, 0.76, 0.70, CLEAR, 0.07)              # 屏幕孔


def ico_haokan(buf, c):
    """好看视频：圆环 + 播放三角"""
    circle(buf, c, 0.5, 0.5, 0.42)
    circle(buf, CLEAR, 0.5, 0.5, 0.28)
    fill_poly(buf, [(0.44, 0.36), (0.44, 0.64), (0.68, 0.50)], c)    # 播放


def ico_weibo(buf, c):
    """微博：眼睛（外环 + 瞳）"""
    circle(buf, c, 0.5, 0.5, 0.42)
    circle(buf, CLEAR, 0.5, 0.5, 0.26)
    circle(buf, c, 0.5, 0.5, 0.14)


def ico_acfun(buf, c):
    """AcFun：字母 A（三角 + 内孔 + 横杠）"""
    fill_poly(buf, [(0.5, 0.06), (0.90, 0.90), (0.10, 0.90)], c)
    fill_poly(buf, [(0.5, 0.34), (0.72, 0.78), (0.28, 0.78)], CLEAR)
    fill_rect(buf, 0.36, 0.66, 0.64, 0.76, c, 0.02)                  # 横杠


def ico_xhs(buf, c):
    """小红书：翻开的书（两页 + 中缝）"""
    fill_poly(buf, [(0.10, 0.20), (0.46, 0.30), (0.46, 0.86),
                    (0.10, 0.76)], c)                                # 左页
    fill_poly(buf, [(0.90, 0.20), (0.54, 0.30), (0.54, 0.86),
                    (0.90, 0.76)], c)                                # 右页


def ico_kuaishou(buf, c):
    """快手：取景框 + 播放（与好看「圆环」区分用方框）"""
    fill_rect(buf, 0.08, 0.16, 0.92, 0.84, c, 0.16)
    fill_rect(buf, 0.24, 0.32, 0.76, 0.68, CLEAR, 0.08)
    fill_poly(buf, [(0.42, 0.38), (0.42, 0.62), (0.64, 0.50)], c)


def ico_sohu(buf, c):
    """搜狐：四角星（锐利、与三柱/四宫格不撞）"""
    fill_poly(buf, [(0.50, 0.04), (0.62, 0.38), (0.96, 0.50),
                    (0.62, 0.62), (0.50, 0.96), (0.38, 0.62),
                    (0.04, 0.50), (0.38, 0.38)], c)


PLATFORM_ICONS = {
    'douyin': ico_douyin, 'bilibili': ico_bilibili, 'haokan': ico_haokan,
    'weibo': ico_weibo, 'acfun': ico_acfun, 'xhs': ico_xhs,
    'kuaishou': ico_kuaishou, 'sohu': ico_sohu,
}

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'miniapp', 'images', 'plat')


def main():
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for skin, color in SKIN_INK.items():
        for key, fn in PLATFORM_ICONS.items():
            canvas = new_canvas()
            fn(canvas, color)
            write_png(os.path.join(OUT, f'{key}-{skin}.png'),
                      downsample(canvas))
            n += 1
    print(f'共 {n} 个平台图标 → {OUT}')


if __name__ == '__main__':
    main()
