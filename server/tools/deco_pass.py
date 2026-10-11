#!/usr/bin/env python3
"""皮肤 pass 2：卡片圆角变量化 + theme-deco 装饰层注入。

规则：
  border-radius: 18/20/24/28rpx → var(--r-card)
  border-radius: 16rpx          → var(--r-small)
  其余（999 胶囊 / 14 按钮 / 3-12 小件 / 多值组合）不动。
  幂等：var(--r-card) 不再匹配 rpx 模式。
注入：
  页面 wxml 根节点后插 <theme-deco theme="{{theme}}" />
  页面 json usingComponents 注册 theme-deco（幂等）。
"""
import re
import glob
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'miniapp')

RADIUS = re.compile(r'(border-radius:\s*)(18|20|24|28)rpx\b')
RADIUS_SMALL = re.compile(r'(border-radius:\s*)16rpx\b')


def migrate_radius(path):
    src = open(path, encoding='utf-8').read()
    n1 = len(RADIUS.findall(src))
    src = RADIUS.sub(r'\1var(--r-card)', src)
    n2 = len(RADIUS_SMALL.findall(src))
    src = RADIUS_SMALL.sub(r'\1var(--r-small)', src)
    if n1 + n2:
        open(path, 'w', encoding='utf-8').write(src)
    return n1, n2


def inject_deco(wxml, jsonf):
    src = open(wxml, encoding='utf-8').read()
    if '<theme-deco' in src:
        w_ok = 'skip'
    else:
        # 根节点行（含 theme-{{theme}}）之后插入
        lines = src.split('\n')
        out = []
        done = False
        for line in lines:
            out.append(line)
            if not done and 'class="page theme-{{theme}}"' in line:
                out.append('  <theme-deco theme="{{theme}}" />')
                done = True
        if not done:
            return 'FAIL-no-root', False
        src = '\n'.join(out)
        open(wxml, 'w', encoding='utf-8').write(src)
        w_ok = 'injected'

    j = json.loads(open(jsonf, encoding='utf-8').read())
    uc = j.setdefault('usingComponents', {})
    if 'theme-deco' in uc:
        j_ok = 'skip'
    else:
        uc['theme-deco'] = '/components/theme-deco/theme-deco'
        open(jsonf, 'w', encoding='utf-8').write(
            json.dumps(j, ensure_ascii=False, indent=2) + '\n')
        j_ok = 'injected'
    return f'wxml:{w_ok} json:{j_ok}', True


def main():
    print('── 圆角变量化 ──')
    t1 = t2 = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'pages', '*', '*.wxss')) +
                    glob.glob(os.path.join(ROOT, 'components', '*', '*.wxss'))):
        n1, n2 = migrate_radius(f)
        t1 += n1
        t2 += n2
        if n1 + n2:
            print(f'✎ {os.path.relpath(f, ROOT)}  card:{n1} small:{n2}')
    print(f'共 card {t1} 处 / small {t2} 处')

    print('── 装饰层注入 ──')
    for f in sorted(glob.glob(os.path.join(ROOT, 'pages', '*', '*.wxml'))):
        rel = os.path.relpath(f, ROOT)
        jf = f[:-5] + '.json'
        if not os.path.exists(jf):
            print(f'SKIP(no json) {rel}')
            continue
        status, ok = inject_deco(f, jf)
        print(f'{status:22s} {rel}')


if __name__ == '__main__':
    main()
