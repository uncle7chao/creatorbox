#!/usr/bin/env python3
"""皮肤系统迁移脚本：把全部 WXSS 的硬编码颜色映射到 CSS 变量，
并给所有页面根节点注入 theme 类绑定。

规则：
  1. 上下文规则先行：`background: #FFFFFF` → var(--bg-card)（白底卡）
     —— 其余 #FFFFFF（多为深色底上的白字/白图形）保持不动
  2. 全局映射：品牌色/墨色/分隔线/软底 → var()（大小写不敏感，词边界）
  3. 有意不迁移：小写 #fff（彩色底上的白字/白图形，全皮肤通用）、
     rgba() 阴影与高光、成功绿/错误红/琥珀状态色
运行：python tools/migrate_skin.py   （幂等：已是 var() 的不重复处理）
"""
import re
import glob
import os

ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'miniapp')

# 全局映射（大小写不敏感；长键优先防前缀误伤——本表无前缀冲突，直接整词替换）
GLOBAL = {
    '#E8890C': 'var(--brand)',
    '#E8790C': 'var(--brand)',
    '#C77700': 'var(--brand-deep)',
    '#C8791A': 'var(--brand-deep)',
    '#B86300': 'var(--brand-deep)',
    '#8A4B00': 'var(--brand-deep)',
    '#F5A623': 'var(--brand-2)',
    '#FFA733': 'var(--brand-2)',
    '#FFC457': 'var(--brand-3)',
    '#FFB84D': 'var(--brand-3)',
    '#B47B3A': 'var(--brand-ink)',
    '#FDF3E4': 'var(--brand-soft)',
    '#FFF4E0': 'var(--brand-soft)',
    '#FFF0D9': 'var(--brand-soft)',
    '#3D2000': 'var(--hero-a)',
    '#2E1800': 'var(--hero-b)',
    '#4A2A08': 'var(--hero-a2)',
    '#5C3200': 'var(--hero-a2)',
    '#1A1614': 'var(--ink-900)',
    '#33261A': 'var(--ink-900)',
    '#4A423C': 'var(--ink-700)',
    '#5C5148': 'var(--ink-700)',
    '#8C8279': 'var(--ink-500)',
    '#7D736B': 'var(--ink-500)',
    '#888780': 'var(--ink-500)',
    '#9A8D80': 'var(--ink-500)',
    '#B8AEA6': 'var(--ink-300)',
    '#B4B2A9': 'var(--ink-300)',
    '#B7A897': 'var(--ink-300)',
    '#A79B8E': 'var(--ink-300)',
    '#C8BFB4': 'var(--ink-300)',
    '#D6CEC4': 'var(--line)',
    '#ECE5DD': 'var(--line)',
    '#F0E9E1': 'var(--bg-soft-2)',
    '#F3EEE9': 'var(--bg-soft)',
    '#F1EFE8': 'var(--bg-soft)',
    '#EDE8E1': 'var(--bg-soft)',
    '#F2ECE5': 'var(--track)',
    '#FAF7F4': 'var(--bg-page)',
    '#F6F1EA': 'var(--bg-page)',
}

# 上下文规则：仅 background 声明里的白色 → 卡片底变量
CTX_BG_WHITE = re.compile(r'(background\s*:\s*)#FFFFFF\b', re.I)
CTX_PAGE_BG = re.compile(r'(background\s*:\s*)#F[6A][67][1F][16][E4A][F4]\b', re.I)


def migrate(path):
    src = open(path, encoding='utf-8').read()
    orig = src
    n_ctx = len(CTX_BG_WHITE.findall(src))
    src = CTX_BG_WHITE.sub(r'\1var(--bg-card)', src)
    for hex_, var in GLOBAL.items():
        # 词边界替换：hex 后面不能跟 hex 字符
        src = re.sub(re.escape(hex_) + r'\b(?![\w-]*\()', var, src, flags=re.I)
    # 幂等保护：var(--xxx) 内不会被再匹配（hex 已不在）
    if src != orig:
        open(path, 'w', encoding='utf-8').write(src)
    return n_ctx, src != orig


def inject_root(path):
    """页面根节点 class="page" → class="page theme-{{theme}}"（幂等）"""
    src = open(path, encoding='utf-8').read()
    if 'theme-{{theme}}' in src:
        return False
    new = src.replace('class="page"', 'class="page theme-{{theme}}"', 1)
    if new == src:
        return False
    open(path, 'w', encoding='utf-8').write(new)
    return True


def main():
    total = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'pages', '*', '*.wxss')) +
                    glob.glob(os.path.join(ROOT, 'components', '*', '*.wxss'))):
        n_ctx, changed = migrate(f)
        total += n_ctx
        rel = os.path.relpath(f, ROOT)
        print(f'{"✎" if changed else "·"} {rel}  (bg-white→card: {n_ctx})')
    print(f'\n上下文替换 {total} 处')

    print('\n根节点 theme 类注入:')
    for f in sorted(glob.glob(os.path.join(ROOT, 'pages', '*', '*.wxml'))):
        rel = os.path.relpath(f, ROOT)
        done = inject_root(f)
        print(f'{"✎" if done else "·"} {rel}')


if __name__ == '__main__':
    main()
