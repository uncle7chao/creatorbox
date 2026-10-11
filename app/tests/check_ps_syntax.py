"""PowerShell 脚本语法预检

为什么要写这个：
  PS 5.1 对**无 BOM 的 UTF-8 .ps1 会按 GBK 解码** → 中文乱码 → 语法错误。
  报错信息本身极具误导性（看起来像括号不配对，实际是编码问题）。
  症状：`-not $hasProxy) { Write-Host '  （无）' -ForegroundColor ...`
  → 报「表达式或语句中包含意外的标记 }」

本脚本用 PowerShell 自带的 AST 解析器做**纯语法检查，不执行**。

用法：python check_ps_syntax.py
"""
import os
import subprocess
import sys

SCRIPTS = ['run.ps1', 'setup-pub.ps1', 'setup-platforms.ps1']
# ⚠️ 脚本在**项目根**，本文件在 tests/ → 上一级
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 纯 ASCII 的检查命令，避开中文与编码干扰。
# ⚠️ 不能用 str.format —— PowerShell 的 `${...}`/`$e.Count` 里的花括号
#    会被 format 当成占位符 → KeyError。改用字符串替换。
PS_CHECK_TMPL = (
    "$f='__PATH__';"
    "$e=$null;$t=$null;"
    "[System.Management.Automation.Language.Parser]::ParseFile("
    "$f,[ref]$t,[ref]$e)|Out-Null;"
    "if($e -and $e.Count -gt 0){"
    "  'ERR '+$e.Count;"
    "  $e[0..([Math]::Min(2,$e.Count-1))]|ForEach-Object{ '  MSG '+$_.Message }"
    "}else{'OK'}"
)


def check(path):
    cmd = ['powershell', '-NoProfile', '-NonInteractive', '-Command',
           PS_CHECK_TMPL.replace('__PATH__', path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.stdout.strip()
    except Exception as e:
        return f'EXC {e}'


def main():
    print('=== PowerShell 脚本语法预检 ===\n')
    bad = 0
    for name in SCRIPTS:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            print(f'  --  {name:22s} 不存在')
            continue

        # 1. BOM 检查
        head = open(p, 'rb').read(3)
        bom = head == b'\xef\xbb\xbf'
        bom_label = '有BOM' if bom else '无BOM(PS5.1会乱码)'
        if not bom:
            bad += 1

        # 2. 语法检查
        out = check(p)
        ok = out.startswith('OK')
        if not ok:
            bad += 1

        flag = 'OK  ' if ok else 'FAIL'
        print(f'  {flag} {name:22s} {bom_label}')
        if not ok:
            for line in out.splitlines():
                print(f'         {line}')

    print()
    if bad == 0:
        print('全部通过')
        return 0
    print(f'{bad} 项有问题')
    return 1


if __name__ == '__main__':
    sys.exit(main())
