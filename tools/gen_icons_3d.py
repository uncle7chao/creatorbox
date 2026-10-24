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
# 配色：白 3D「白瓷」三阶（图形浮在品牌色渐变底座上）
#
# ⭐ 三次试错才定下来，这里把原因写清楚，别再来一遍：
#
#   ① 第一版：顶面 #fff + 侧面 rgba(255,255,255,.46)「半透明白」
#      → 白透在橙底上 = 「变浅的橙」，不是灰
#      → 白 vs 浅橙，明暗差只跨半阶 → 44px 下就是「加了点阴影」
#
#   ② 第二版：顶面 #fff + 侧面 rgba(0,0,0,.26)「半透明黑」
#      → 压暗成立，立体感有了，但**形状没了**：
#        文件夹的后板变深绿、厚度更深绿，跟绿底座糊成一片，
#        只剩前板那块白，看起来像「一个白条」而不是文件夹
#
#   ③ 现在：**固定灰阶，不用半透明**
#        受光面 #FFFFFF → 中间面 #DDE2E8 → 背光面 #B4BCC7
#      → 灰阶是绝对色，不随底色变，对比恒定
#      → 三个明度阶跨度足够（L 100 / 89 / 76），小尺寸也分得开
#      → 底色只负责「品牌色块」，图形只负责「体积」，互不干扰
#
#   ⚠️ 结论：彩色底上的 3D 白物体，要画成**白瓷**（白+灰），
#      不是「半透明白」。透光会带底色，白瓷不会。
# ══════════════════════════════════════════════════════════════════════
LIT = '#ffffff'        # 受光面（正对光）
MID = '#e9eef4'        # 中间面（侧光）—— 提亮，避免整体发灰
DIM = '#c7cfda'        # 背光面 / 挤出厚度 —— 同上，白瓷的灰要「浅灰」
EDGE = '#ffffff'       # 棱线（面与面的分界，小尺寸下必须有）


def stack(p):
    """批量解析：三层等轴测叠板"""
    o = [HEAD]
    d = 20
    # (x, y, w, 顶面色)  —— 越靠上层越亮，模拟「叠在光里」
    layers = [(22, 153, 212, '#eef1f5'), (40, 99, 176, '#f7f9fb'), (58, 45, 140, LIT)]
    for x, y, w, face in layers:
        h, rx = 38, 14
        o.append(f'<rect x="{x}" y="{y + d}" width="{w}" height="{h}" rx="{rx}" fill="{DIM}"/>')
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{face}"/>')
        # 顶面下缘棱线：把顶面和厚度分开（也模拟边缘高光）
        o.append(f'<rect x="{x + rx - 2}" y="{y + h - 3}" width="{w - 2 * rx + 4}" '
                 f'height="3" rx="1.5" fill="{EDGE}"/>')
    o.append('</svg>')
    return ''.join(o)


def folder(p):
    """我的素材：等轴测文件夹（前板亮 / 后板中 / 厚度与内腔暗）"""
    o = [HEAD]
    x0, x1, tab = 18, 238, 118
    y_tab, y_top, y_split, y_front, y_bot = 36, 56, 106, 132, 196
    d = 24

    def outline(dy):
        """带标签凸起的文件夹轮廓。dy = 向下偏移（画厚度用）"""
        return (f'M{x0 + 18},{y_tab + dy} L{tab},{y_tab + dy} '
                f'L{tab + 14},{y_top + dy} L{x1 - 18},{y_top + dy} '
                f'Q{x1},{y_top + dy} {x1},{y_top + dy + 18} '
                f'L{x1},{y_bot + dy - 18} Q{x1},{y_bot + dy} {x1 - 18},{y_bot + dy} '
                f'L{x0 + 18},{y_bot + dy} Q{x0},{y_bot + dy} {x0},{y_bot + dy - 18} '
                f'L{x0},{y_tab + dy + 18} Q{x0},{y_tab + dy} {x0 + 18},{y_tab + dy} Z')

    o.append(f'<path d="{outline(d)}" fill="{DIM}"/>')      # 挤出厚度（最深）
    o.append(f'<path d="{outline(0)}" fill="{MID}"/>')      # 后板（中）
    # 内腔：比后板更暗的一道缝，做出「打开」的深度
    o.append(f'<rect x="{x0 + 12}" y="{y_split}" width="{x1 - x0 - 24}" height="24" '
             f'rx="7" fill="{DIM}"/>')
    # 前板（受光面，最亮）—— 它的面积决定这个图标像不像文件夹
    o.append(f'<rect x="{x0}" y="{y_front}" width="{x1 - x0}" height="{y_bot - y_front}" '
             f'rx="16" fill="{LIT}"/>')
    o.append(f'<rect x="{x0 + 18}" y="{y_front + 3}" width="{x1 - x0 - 36}" height="3" '
             f'rx="1.5" fill="{EDGE}"/>')                     # 前板上缘棱线
    o.append('</svg>')
    return ''.join(o)


def chart(p):
    """热榜：三根等轴测柱（顶面亮 / 正面中 / 右侧面暗）"""
    o = [HEAD]
    dx, dy, w = 17, 10, 56      # 灰面窄一点 = 白面占比更大 = 更「白瓷」
    base = 196
    for x, y_top, face in [(20, 132, MID), (92, 44, '#f2f5f8'), (164, 148, MID)]:
        h = base - y_top
        o.append(f'<rect x="{x}" y="{y_top}" width="{w}" height="{h}" fill="{face}"/>')
        o.append(f'<path d="M{x + w},{y_top} L{x + w + dx},{y_top - dy} '
                 f'L{x + w + dx},{base - dy} L{x + w},{base} Z" fill="{DIM}"/>')
        o.append(f'<path d="M{x},{y_top} L{x + w},{y_top} L{x + w + dx},{y_top - dy} '
                 f'L{x + dx},{y_top - dy} Z" fill="{LIT}"/>')
        # 正面与右侧面的棱线（这道线是「立体」的关键，去掉就成三块平板）
        o.append(f'<rect x="{x + w - 1.5}" y="{y_top}" width="2.5" height="{h}" fill="{EDGE}"/>')
        o.append(f'<rect x="{x}" y="{y_top - 1.5}" width="{w}" height="2.5" fill="{EDGE}" opacity=".8"/>')
    # 地面（三根柱子站同一平面）
    o.append(f'<rect x="16" y="{base}" width="228" height="11" rx="5" fill="{DIM}" opacity=".85"/>')
    o.append('</svg>')
    return ''.join(o)


def cubes(p):
    """更多工具：四个等轴测立方体"""
    o = [HEAD]
    s_, dx, dy = 76, 16, 10
    for x, y, face in [(16, 46, LIT), (130, 46, '#f2f5f8'),
                       (16, 148, '#f2f5f8'), (130, 148, LIT)]:
        o.append(f'<rect x="{x}" y="{y}" width="{s_}" height="{s_}" fill="{face}"/>')
        o.append(f'<path d="M{x + s_},{y} L{x + s_ + dx},{y - dy} '
                 f'L{x + s_ + dx},{y + s_ - dy} L{x + s_},{y + s_} Z" fill="{DIM}"/>')
        o.append(f'<path d="M{x},{y} L{x + s_},{y} L{x + s_ + dx},{y - dy} '
                 f'L{x + dx},{y - dy} Z" fill="{LIT}"/>')
        o.append(f'<rect x="{x + s_ - 1.5}" y="{y}" width="2.5" height="{s_}" fill="{EDGE}"/>')
        o.append(f'<rect x="{x}" y="{y - 1.5}" width="{s_}" height="2.5" fill="{EDGE}"/>')
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
        svg = builder(None)      # 白 3D 版不依赖配色表；参数保留便于以后扩展彩色版
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
