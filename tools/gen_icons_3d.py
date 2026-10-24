#!/usr/bin/env python3
"""首页工具图标的 3D 拟物版生成器（2026-10-24）

═══ 为什么需要这个脚本 ═══

首页工具有 4 个图标（批量解析 / 我的素材 / 热榜 / 更多工具），
原来每个主题一套 81×81 的 PNG，是「彩色圆角块 + 白色平面图形」。

用户要求「3D 拟物图标」。试过只改 CSS（渐变 + 内阴影 + 投影），
**44px 下几乎看不出来** —— 因为：

  ① 图形只有 26px，厚度没有空间显形
  ② 半透明的"暗面"在彩色底上透色后，明暗差被抹平
  ③ 同色系的面之间没有分界线，小尺寸下必然糊成一块

所以必须重画**图形本身**：把平面形状改成多面体（顶面 / 侧面 / 厚度），
并给每条棱加白色高光线。这三件事是 CSS 做不到的。

═══ 用法 ═══

    python tools/gen_icons_3d.py

依赖：本机 Chrome（用 headless 把 SVG 渲成透明 PNG，
     因为小程序 <image> 不支持 SVG）。
输出：miniapp/images/home/3d-<name>.png（256×256 透明底）

═══ 改配色 ═══

只改 PALETTE。每个图标三个明度阶：
  top  顶面（最亮，正对光）
  face 正面（中）
  side 侧面 / 厚度（最暗，背光）
"""

import base64
import os
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, 'miniapp', 'images', 'home')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
SIZE = 256  # 输出尺寸；显示 40px，3x 屏需 120px，256 有足够余量

HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
        f'viewBox="0 0 {SIZE} {SIZE}">')

# ══════════════════════════════════════════════════════════════════════
# 配色：严格对齐原来的语义色（批量=橙 / 素材=绿 / 热榜=红 / 更多=灰）
#   ⚠️ 侧面必须比顶面深两个明度阶，否则 44px 下看不出体积。
#      这是踩过的坑：第一版侧面用 rgba(255,255,255,.46) 半透明白，
#      在橙色底上透色后变成"稍暗的橙"，跟白顶面的对比被抹平 ——
#      看起来就像"只加了个阴影"。
# ══════════════════════════════════════════════════════════════════════
PALETTE = {
    'batch':   dict(top='#FFD79B', face='#F5A03A', side='#A85D18', back='#D9862C'),
    'library': dict(top='#A8F0CE', face='#2EC98A', side='#0B7A4A', back='#1FA96E'),
    'rank':    dict(top='#FFB8B2', face='#F2665E', side='#A32F2A', back='#D14A44'),
    'more':    dict(top='#E4EAF3', face='#A8B2C4', side='#5A6577', back='#8A94A8'),
}


def stack(p):
    """批量解析：三层等轴测叠板（每层 = 顶面 + 厚度 + 棱线高光）"""
    o = [HEAD]
    d = 24                                  # 挤出厚度（显示时约 3.7px）
    # y 值经过 bbox 实测校准：让三层叠板的视觉中心落在画布 128
    layers = [(22, 153, 212, .86), (40, 99, 176, .95), (58, 45, 140, 1.0)]
    for x, y, w, lum in layers:
        h, rx = 34, 14
        # 厚度：同形状下移（圆角保持，否则底边会变成直角、看出破绽）
        o.append(f'<rect x="{x}" y="{y + d}" width="{w}" height="{h}" rx="{rx}" '
                 f'fill="{p["side"]}" opacity="{lum}"/>')
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
                 f'fill="{p["top"]}" opacity="{lum}"/>')
        # ⭐ 顶面下缘的高光线：既是棱边反光，也是顶面/侧面的分界线
        o.append(f'<rect x="{x + rx - 2}" y="{y + h - 4}" width="{w - 2 * rx + 4}" '
                 f'height="4" rx="2" fill="#fff" opacity=".92"/>')
    o.append('</svg>')
    return ''.join(o)


def folder(p):
    """我的素材：等轴测文件夹（后板暗 / 前板亮 / 中间露内腔）"""
    o = [HEAD]
    x0, x1, tab = 18, 238, 126
    # 同样按 bbox 校准过（原中心 140 → 128）
    y_tab, y_top, y_split, y_front, y_bot = 36, 56, 110, 136, 196
    d = 24

    def outline(dy):
        """带标签凸起的文件夹轮廓。dy = 向下偏移量（画厚度用）"""
        return (f'M{x0 + 18},{y_tab + dy} L{tab},{y_tab + dy} '
                f'L{tab + 14},{y_top + dy} L{x1 - 18},{y_top + dy} '
                f'Q{x1},{y_top + dy} {x1},{y_top + dy + 18} '
                f'L{x1},{y_bot + dy - 18} Q{x1},{y_bot + dy} {x1 - 18},{y_bot + dy} '
                f'L{x0 + 18},{y_bot + dy} Q{x0},{y_bot + dy} {x0},{y_bot + dy - 18} '
                f'L{x0},{y_tab + dy + 18} Q{x0},{y_tab + dy} {x0 + 18},{y_tab + dy} Z')

    o.append(f'<path d="{outline(d)}" fill="{p["side"]}"/>')      # 厚度
    o.append(f'<path d="{outline(0)}" fill="{p["back"]}"/>')      # 后板
    o.append(f'<rect x="{x0 + 12}" y="{y_split}" width="{x1 - x0 - 24}" height="28" '
             f'rx="8" fill="{p["side"]}" opacity=".75"/>')         # 内腔（开口）
    o.append(f'<rect x="{x0}" y="{y_front}" width="{x1 - x0}" height="{y_bot - y_front}" '
             f'rx="16" fill="{p["top"]}"/>')                        # 前板
    o.append(f'<rect x="{x0 + 20}" y="{y_front + 4}" width="{x1 - x0 - 40}" height="4" '
             f'rx="2" fill="#fff" opacity=".95"/>')                 # 前板上缘高光
    o.append('</svg>')
    return ''.join(o)


def chart(p):
    """热榜：三根等轴测柱（正面 / 右侧面 / 顶面菱形）"""
    o = [HEAD]
    # ⚠️ 右边界算过：最后一根柱 x+w+dx 必须 < 256，否则右侧面被裁掉
    dx, dy, w = 20, 12, 54
    base = 196
    for x, y_top, lum in [(20, 132, .90), (92, 44, 1.0), (164, 148, .90)]:
        h = base - y_top
        o.append(f'<rect x="{x}" y="{y_top}" width="{w}" height="{h}" '
                 f'fill="{p["face"]}" opacity="{lum}"/>')
        o.append(f'<path d="M{x + w},{y_top} L{x + w + dx},{y_top - dy} '
                 f'L{x + w + dx},{base - dy} L{x + w},{base} Z" '
                 f'fill="{p["side"]}" opacity="{lum}"/>')
        o.append(f'<path d="M{x},{y_top} L{x + w},{y_top} L{x + w + dx},{y_top - dy} '
                 f'L{x + dx},{y_top - dy} Z" fill="{p["top"]}" opacity="{lum}"/>')
        # 正面与右侧面的分界线
        o.append(f'<rect x="{x + w - 2}" y="{y_top}" width="3" height="{h}" '
                 f'fill="#fff" opacity=".70"/>')
    # 地面（让三根柱子站在同一平面上，否则会显得浮空）
    o.append(f'<rect x="18" y="{base}" width="224" height="12" rx="6" '
             f'fill="{p["side"]}" opacity=".40"/>')
    o.append('</svg>')
    return ''.join(o)


def cubes(p):
    """更多工具：四个等轴测立方体（2×2）"""
    o = [HEAD]
    s, dx, dy = 74, 20, 12
    for x, y, lum in [(16, 46, 1.0), (130, 46, .92), (16, 148, .92), (130, 148, 1.0)]:
        o.append(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" '
                 f'fill="{p["face"]}" opacity="{lum}"/>')
        o.append(f'<path d="M{x + s},{y} L{x + s + dx},{y - dy} '
                 f'L{x + s + dx},{y + s - dy} L{x + s},{y + s} Z" '
                 f'fill="{p["side"]}" opacity="{lum}"/>')
        o.append(f'<path d="M{x},{y} L{x + s},{y} L{x + s + dx},{y - dy} '
                 f'L{x + dx},{y - dy} Z" fill="{p["top"]}" opacity="{lum}"/>')
        o.append(f'<rect x="{x + s - 2}" y="{y}" width="3" height="{s}" '
                 f'fill="#fff" opacity=".65"/>')
        o.append(f'<rect x="{x}" y="{y - 2}" width="{s}" height="3" '
                 f'fill="#fff" opacity=".65"/>')
    o.append('</svg>')
    return ''.join(o)


BUILDERS = {'batch': stack, 'library': folder, 'rank': chart, 'more': cubes}


def render(svg_text, out_png, chrome):
    """用 headless Chrome 把 SVG 渲成透明 PNG

    ⚠️ 必须带 --default-background-color=00000000，否则出来是白底。
    （小程序 <image> 不支持 SVG，只能走 PNG。）
    """
    with tempfile.TemporaryDirectory() as td:
        svg_path = os.path.join(td, 'i.svg')
        html_path = os.path.join(td, 'i.html')
        with open(svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_text)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write('<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
                    'html,body{margin:0;padding:0;background:transparent}'
                    f'img{{display:block;width:{SIZE}px;height:{SIZE}px}}'
                    '</style></head><body><img src="i.svg"></body></html>')
        subprocess.run([
            chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
            '--hide-scrollbars', '--default-background-color=00000000',
            f'--window-size={SIZE},{SIZE}', f'--screenshot={out_png}',
            'file:///' + html_path.replace('\\', '/'),
        ], capture_output=True, timeout=60)


def main():
    chrome = CHROME
    if not os.path.exists(chrome):
        print(f'✗ 找不到 Chrome：{chrome}')
        print('  这个脚本靠 Chrome 渲染 SVG，没有它跑不了。')
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, builder in BUILDERS.items():
        svg = builder(PALETTE[name])
        out = os.path.join(OUT_DIR, f'3d-{name}.png')
        render(svg, out, chrome)
        if not os.path.exists(out):
            print(f'✗ {name} 渲染失败')
            return 1
        with open(out, 'rb') as f:
            head = f.read(8)
        print(f'  ✓ 3d-{name}.png  {os.path.getsize(out) / 1024:.1f} KB  '
              f'{"PNG" if head[:4] == b"\x89PNG" else "非PNG!"}')
    print(f'\n输出目录：{OUT_DIR}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
