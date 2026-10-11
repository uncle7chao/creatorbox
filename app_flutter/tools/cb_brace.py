# -*- coding: utf-8 -*-
"""Dart 源码括号平衡检查（沙箱跑不了 dart analyze 时的兜底）。

⚠️ 为什么需要清理字符串与注释
   朴素的 `s.count('(')` 会把字符串里的括号也算进去，例如：
       '· 素材库条目：$n 条'   无括号，但
       '(missing'             会被算成未闭合
   实测曾因此误报 batch_page.dart「差 -7」，逐行核对后确认代码完全正常。
   真实编译错误请以 dartdevc / flutter analyze 为准，本脚本只做快速筛查。

用法：python tools/cb_brace.py [lib目录]
"""
import re
import sys
import glob
import os


def strip_noise(src: str) -> str:
    """去掉注释与字符串字面量，只留结构字符。"""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        # 行注释
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        # 块注释
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            continue
        # 三引号字符串（模板）
        if src.startswith("'''", i) or src.startswith('"""', i):
            q = src[i:i + 3]
            i += 3
            while i < n and not src.startswith(q, i):
                i += 1
            i += 3
            continue
        # 普通字符串
        if c in "'\"":
            q = c
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                if src[i] == '$' and i + 1 < n and src[i + 1] == '{':
                    # 模板插值 ${...} 内是真实表达式，要保留其结构
                    i += 2
                    depth = 1
                    while i < n and depth:
                        if src[i] == '{':
                            depth += 1
                        elif src[i] == '}':
                            depth -= 1
                        i += 1
                    out.append(' ' * 0)
                    continue
                i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


PAIRS = {'()': ('(', ')'), '{}': ('{', '}'), '[]': ('[', ']')}


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'lib'
    files = sorted(glob.glob(os.path.join(root, '**', '*.dart'), recursive=True))
    if not files:
        print(f'{root} 下没有 .dart 文件')
        return 1
    bad = 0
    print(f'括号平衡检查（{len(files)} 个文件，已剔除注释与字符串）')
    print('=' * 52)
    for p in files:
        s = strip_noise(open(p, encoding='utf-8').read())
        diffs = {k: s.count(a) - s.count(b) for k, (a, b) in PAIRS.items()}
        name = p.split('\\')[-1].split('/')[-1]
        if all(v == 0 for v in diffs.values()):
            print(f'  OK   {name}')
        else:
            bad += 1
            print(f'  BAD  {name}  {diffs}')
            # 定位首个失衡行，帮助快速找到问题处
            depth = 0
            for ln, line in enumerate(strip_noise(
                    open(p, encoding='utf-8').read()).split('\n'), 1):
                depth += line.count('(') - line.count(')')
                if depth < 0:
                    print(f'        ↳ 首个深度转负在第 {ln} 行')
                    break
    print('=' * 52)
    if bad:
        print(f'❌ {bad} 个文件括号不平衡')
        return 1
    print('✅ 全部平衡')
    return 0


if __name__ == '__main__':
    sys.exit(main())