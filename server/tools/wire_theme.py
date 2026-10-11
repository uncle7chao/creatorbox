#!/usr/bin/env python3
"""皮肤系统页面接线：给每个页面 JS 注入
  1. require themes.js（require 块末尾）
  2. data 首行 theme: 'classic'
  3. onShow：已有则在函数体首行插 theme.sync(this)；没有则在 data 块后补一个
幂等（重复跑不重复注入）。跑完必须 node --check 全量验证。
"""
import re
import glob
import os

ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'miniapp')

REQ = "const themeUtil = require('../../utils/themes.js');\n"


def inject(path):
    src = open(path, encoding='utf-8').read()
    if "utils/themes.js" in src:
        return 'skip-already'
    notes = []

    # 1. require：插在最后一个顶层 require 行之后
    reqs = list(re.finditer(r"^.*require\([^\n]+\);\n", src, re.M))
    if reqs:
        last = reqs[-1]
        src = src[:last.end()] + REQ + src[last.end():]
    else:
        # compliance 无 require —— 插在 Page({ 之前
        src = src.replace('Page({', REQ + '\nPage({', 1)
    notes.append('require')

    # 2. data 首行
    src = re.sub(r'(data:\s*\{)', r"\1\n    theme: 'classic',", src, count=1)
    notes.append('data')

    # 3. onShow
    m = re.search(r'  onShow\([^)]*\)\s*\{\n', src)
    if m:
        src = src[:m.end()] + '    themeUtil.sync(this);\n' + src[m.end():]
        notes.append('onShow+sync')
    else:
        # 没有 onShow：插在 onLoad 之前 / data 块结束后
        m2 = re.search(r'\n  onLoad\(', src)
        hook = '\n  onShow() {\n    themeUtil.sync(this);\n  },\n'
        if m2:
            src = src[:m2.start()] + hook + src[m2.start():]
        else:
            # data 块结尾 `  },\n\n  onLoad` 或第一个方法前 —— 找 data:\s*{...} 块结束
            m3 = re.search(r"(data:\s*\{[\s\S]*?\n  \},\n)", src)
            if m3:
                src = src[:m3.end()] + hook + src[m3.end():]
            else:
                return 'FAIL-no-anchor'
        notes.append('onShow(new)')

    open(path, 'w', encoding='utf-8').write(src)
    return '+'.join(notes)


def main():
    for f in sorted(glob.glob(os.path.join(ROOT, 'pages', '*', '*.js'))):
        rel = os.path.relpath(f, ROOT)
        r = inject(f)
        print(f'{r:20s} {rel}')


if __name__ == '__main__':
    main()
