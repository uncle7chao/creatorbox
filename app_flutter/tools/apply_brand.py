# -*- coding: utf-8 -*-
"""品牌名全量同步脚本。

用途
----
「星创映画」是中文品牌名，英文名保留 CreatorBox。改品牌名时**只改这里**，
然后跑本脚本，全项目（小程序 / Flutter / 后台 / 平台配置 / 教程页）同步。

  python tools/apply_brand.py            # 预览要改什么（不落盘）
  python tools/apply_brand.py --apply    # 真正写入

⭐ 关键区分：品牌名 vs 内部代号
   改：用户能看到的一切（界面文字、窗口标题、Android 图标名、网页 title）
   不改：包名 com.creatorbox.app、接口 service 名 creatorbox-parser、
        类名 CreatorBoxApp、目录名 D:\\WorkBuddyFILE\\CreatorBox
   —— 改后者会破坏包路径、构建配置与历史对应关系。

本脚本用【精确字符串对】而不是正则替换，避免误伤：
   · 路径里的 CreatorBox 不动
   · 注释里的 CreatorBox 不动（除非明确列入替换表）
"""
import os
import re
import sys

# ⚠️ 路径基准是【项目根】不是 app_flutter/：
#    替换表里包含 miniapp/ server/ app_flutter/ 等多个顶层目录。
#    曾经写成 app_flutter/ 基准 → 所有条目都报「文件不存在」而静默跳过，
#    看起来像「无需改动」，其实是路径错了 —— 这类静默失败最危险。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CN = '星创映画'
EN = 'CreatorBox'

# ── (相对路径, 原串, 新串, 说明) ────────────────────────────────────────
# 只列【用户可见】的品牌位。路径、内部代号、注释不在此列。
EDITS = [
    # ── 小程序 ──
    ('miniapp/pages/compliance/compliance.wxml',
     f'{EN} v{{{{version}}}}', f'{CN} v{{{{version}}}}', '免责页版本署名'),
    ('miniapp/pages/member/member.wxml',
     f'{EN} 用户', f'{CN} 用户', '会员页用户名占位'),
    ('miniapp/pages/member/member.wxml',
     f'{EN} 会员', f'{CN} 会员', '会员标识'),
    ('miniapp/pages/pdftool/pdftool.wxml',
     f'如：{EN}', f'如：{CN}', 'PDF 水印示例'),

    # ── 平台配置（用户第一眼看到的名字）──
    ('app_flutter/android/app/src/main/AndroidManifest.xml',
     f'android:label="{EN.lower()}"', f'android:label="{CN}"', 'Android 桌面图标名'),
    ('app/android/app/src/main/AndroidManifest.xml',
     f'android:label="{EN.lower()}"', f'android:label="{CN}"', 'Android 桌面图标名(app)'),

    # ── 后台与说明页 ──
    ('server/admin/index.html',
     f'{EN} 运营后台', f'{CN} 运营后台', '后台标题/页脚'),
    ('server/admin/dashboard.html',
     f'{EN} · 运维看板', f'{CN} · 运维看板', '旧版看板 title'),
    ('server/admin/dashboard.html',
     f'{EN} 运维看板', f'{CN} 运维看板', '旧版看板 h1'),
    ('server/admin/密钥设置说明.html',
     f'{EN} · 密钥设置说明', f'{CN} · 密钥设置说明', '密钥说明 title'),
    ('app_flutter/P1首跑手把手教程.html',
     f'{EN} P1 首跑 · 手把手教程', f'{CN} P1 首跑 · 手把手教程', '教程 title/h1'),
    ('app_flutter/P1首跑联调手册.html',
     f'{EN} P1 首跑联调手册', f'{CN} P1 首跑联调手册', '联调手册 title/h1'),
]

# Windows 窗口标题：必须用 \uXXXX 转义（MSVC 源码页 GBK 会把中文解成乱码）
WIN_TITLE_FILE = 'app_flutter/windows/runner/main.cpp'
WIN_OLD = 'window.Create(L"creatorbox", origin, size)'
WIN_NEW = 'window.Create(L"%s", origin, size)' % ''.join(f'\\u{ord(c):04X}' for c in CN)


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with open(os.path.join(ROOT, p), 'w', encoding='utf-8', newline='') as f:
        f.write(s)


def main():
    apply = '--apply' in sys.argv
    changes = []

    for rel, old, new, why in EDITS:
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            print(f'  – 跳过（文件不存在）: {rel}')
            continue
        s = read(rel)
        if old not in s:
            continue
        n = s.count(old)
        changes.append((rel, old, new, why, n))
        print(f'  {"改" if apply else "将改"} {why:20} {rel}  ×{n}')

    # Windows 窗口标题
    if os.path.exists(os.path.join(ROOT, WIN_TITLE_FILE)):
        s = read(WIN_TITLE_FILE)
        if WIN_OLD in s:
            changes.append((WIN_TITLE_FILE, WIN_OLD, WIN_NEW, 'Windows 窗口标题', 1))
            print(f'  {"改" if apply else "将改"} {"Windows 窗口标题":20} {WIN_TITLE_FILE}  ×1')
        elif WIN_NEW in s:
            print(f'  – 已是最新: Windows 窗口标题')
        else:
            print(f'  ⚠ Windows 窗口标题未匹配（可能已手工改过，请人工确认）')

    if not changes:
        print('\n无需改动。')
        return 0

    if apply:
        for rel, old, new, _why, _n in changes:
            s = read(rel)
            write(rel, s.replace(old, new))
        print(f'\n✅ 已写入 {len(changes)} 个文件')
    else:
        print(f'\n共 {len(changes)} 处待改。加 --apply 执行写入。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
