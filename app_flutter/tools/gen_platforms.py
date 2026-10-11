# -*- coding: utf-8 -*-
"""从 Flutter SDK 模板生成平台壳（Windows / Android）。

为什么需要
----------
本项目的 lib/ 是手写的（沙箱内 flutter 工具链因命名管道 bug err 231 不可用），
所以没有 windows/ android/ 目录。`flutter run` / `flutter build` 会直接报
「没有支持的设备」。

而平台壳本身是**确定性文件**（CMake 工程 / Gradle 配置），可以从 SDK 里的
templates 渲染出来，不必调用 flutter 命令 —— 这样在本机之外也能生成。

用法：
  python tools/gen_platforms.py            # 生成 Windows + Android
  python tools/gen_platforms.py windows    # 只生成 Windows
  python tools/gen_platforms.py android

⚠️ 生成后仍需在本机执行：
  flutter pub get          # 装依赖（需要网络）
  flutter build windows    # 首次建议 --debug，验证能跑再 --release
"""

import os
import re
import sys
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = ROOT  # app_flutter 目录本身
FLUTTER_ROOT = os.environ.get('FLUTTER_ROOT', r'D:\dev\flutter')
TPL = os.path.join(FLUTTER_ROOT, 'packages', 'flutter_tools', 'templates', 'app')

# 渲染时替换的占位符（对齐 flutter create 的取值）
VARS = {
    'projectName': 'creatorbox',
    'description': 'CreatorBox · 内容地址解析',
    'orgName': 'creatorbox',          # 反向域名，用作 Android package / 公司名
    'companyName': 'CreatorBox',
    'organization': 'CreatorBox',     # ⚠️ 与 orgName 不同：这是 Windows 资源里的
                                      #「公司名」显示字段，容易漏掉
    'year': '2026',
    'projectType': 'app',
    'androidPackage': 'com.creatorbox.app',
    'iosBundleIdentifier': 'com.creatorbox.app',
    # 以下三个必须与 Flutter 3.47.5 自带值一致
    # （来源：flutter_tools/lib/src/android/gradle_utils.dart 的 template* 常量）
    # 填错会导致 Gradle 拉不到对应发行版，构建期才炸。
    'agpVersion': '9.1.0',          # templateAndroidGradlePluginVersion
    'gradleVersion': '9.3.1',       # templateDefaultGradleVersion
    'kotlinVersion': '2.4.0',       # templateKotlinGradlePluginVersion
    # Android 模板里另有一组标识占位符（某些变体模板会用到）
    'androidIdentifier': 'com.creatorbox.app',
    'androidSdkVersion': 'android-36',
}

# mustachestyle条件块的处理：{{#key}}…{{/key}} 表示「key 为真时保留这段」
# flutter 的模板用它控制是否注入插件注册代码。默认为假 = 删掉整段
# （方法通道插件钩子由 flutter 工具在 pub get/build 时另行注入）。
BOOLEAN_FLAGS = {
    'withPlatformChannelPluginHook': False,
    'withPluginHook': False,
    'withFfiPluginHook': False,
    'withFfiPackage': False,
}

# 生成的目录不进版本库（已在 .gitignore），但列出以便自检
IGNORE_HINT = ['windows/flutter/ephemeral', 'windows/flutter/generated_plugin_registrant.cc',
               '.dart_tool', 'build']


def render(text: str) -> str:
    """渲染 flutter 模板。

    三类语法都要处理：
      · mustache 变量：{{projectName}} → VARS 里的值
      · mustache 段落：{{#key}}…{{/key}} → key 为真保留整段，否则删除
        （第一版漏了段落处理，残留 {{#withPlatformChannelPluginHook}} 会让
          CMake 直接报错——模板里的坑不处理就会变成构建期失败）
      · ⭐ 【裸占位符】：模板路径/文件名里的 androidIdentifier / projectName
        是**不带花括号**的字面串（flutter 内部按整名匹配替换）。
        第一版只处理了 {{}}，结果生成出
        `app/src/main/kotlin/androidIdentifier/MainActivity.kt`
        和 `projectName_android.iml` —— 这种包路径 Gradle 根本不认。
    """
    # 1) 段落（必须先做，否则段内的 {{变量}} 会跟着一起删/留错位）
    for key, keep in BOOLEAN_FLAGS.items():
        text = re.sub(
            r'\{\{#' + key + r'\}\}.*?\{\{/' + key + r'\}\}',
            lambda m: m.group(0) if keep else '',
            text, flags=re.S)

    # 2) 带花括号变量；未知占位符原样保留，避免误伤 flutter 运行时才填的
    text = re.sub(r'\{\{\s*([a-zA-Z_]+)\s*\}\}',
                  lambda m: VARS.get(m.group(1), m.group(0)), text)

    # 3) 裸占位符：模板里的「整名占位符」，不带花括号。
    #    例：`projectName_android.iml`、`kotlin/androidIdentifier/MainActivity.kt`
    #    ⚠️ 用 (?<![A-Za-z0-9]) / (?![A-Za-z0-9]) 而不是 \w：
    #       \w 在 Python 里含中文与下划线，会导致 projectName_ 这种
    #       「后面紧跟下划线」的合法替换被 (?!\w) 挡掉（第一版就栽在这）。
    for key in ('projectName', 'androidIdentifier'):
        val = VARS.get(key)
        if not val:
            continue
        text = re.sub(r'(?<![A-Za-z0-9])' + key + r'(?![A-Za-z0-9])',
                      lambda m, v=val: v, text)
    return text


def copy_tree(src: str, dst: str, must_render: bool = True):
    """复制模板树 → 渲染 .tmpl 文件 → 去掉 .tmpl 后缀。

    ⭐ 路径也要渲染：Android 模板的目录名本身就含占位符
      （app/src/main/kotlin/androidIdentifier/），只渲染文件内容会生成
      一个名字literally 叫 androidIdentifier 的包目录，Gradle 直接找不到。

    渲染后会自查残留占位符 —— 模板里的坑不该等到 CMake/Gradle 报错才发现，
    那时候已经是在构建阶段，报错信息还指向生成的工程文件而非根因。
    """
    n = 0
    leftovers = []
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        if rel != '.':
            rel = render(rel)          # ← 目录名渲染
        out_dir = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(out_dir, exist_ok=True)
        for f in files:
            s = os.path.join(dirpath, f)
            name = render(f[:-len('.tmpl')] if f.endswith('.tmpl') else f)
            d = os.path.join(out_dir, name)
            if os.path.exists(d):
                continue
            if f.endswith('.tmpl') and must_render:
                with open(s, encoding='utf-8') as fh:
                    content = fh.read()
                content = render(content)
                for m in re.finditer(r'\{\{\s*([a-zA-Z_#]+)\s*\}\}', content):
                    leftovers.append(f'{name}: {{{{{m.group(1)}}}}}')
                with open(d, 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write(content)
            else:
                shutil.copy2(s, d)
            n += 1
    if leftovers:
        print(f'    ⚠ 渲染后仍有未处理占位符（会导致构建失败）：')
        for x in leftovers[:8]:
            print(f'      · {x}')
    return n


def gen_windows() -> bool:
    src = os.path.join(TPL, 'windows.tmpl')
    if not os.path.isdir(src):
        print(f'  ✗ 找不到模板: {src}')
        return False
    dst = os.path.join(APP, 'windows')
    n = copy_tree(src, dst)
    print(f'  ✓ windows/ 已生成（{n} 个文件）')
    return True


def gen_android() -> bool:
    """Android 壳：需要【合并两个模板目录】。

    ⚠️ Flutter 的 Android 模板是拆开的（这是很容易踩的坑）：
      · android.tmpl           → 基础壳：manifest / res 图标 / gradle.properties /
                                 settings.gradle.kts / wrapper（16 文件）
                                 ⚠️ 但【不含】build.gradle.kts 与 MainActivity！
      · android-kotlin.tmpl    → 补上 app/build.gradle.kts 与 MainActivity.kt
      · android-java.tmpl      → 同上，Java 版（Kotlin 版的替代）

       只用 android.tmpl 会生成出【缺 app/build.gradle.kts】的残缺工程，
       表现为 Gradle 配置阶段直接失败 —— 第一版就是这么错的。

    Kotlin 版是现代默认（MainActivity.kt），优先用它。
    """
    base = os.path.join(TPL, 'android.tmpl')
    lang = os.path.join(TPL, 'android-kotlin.tmpl')
    for p in (base, lang):
        if not os.path.isdir(p):
            print(f'  ✗ 找不到模板: {p}')
            print(f'    可用 FLUTTER_ROOT 环境变量指定 SDK 路径')
            return False
    dst = os.path.join(APP, 'android')
    n1 = copy_tree(base, dst)
    n2 = copy_tree(lang, dst)      # 语言层文件覆盖/补齐到同一目录
    print(f'  ✓ android/ 已生成（基础 {n1} + Kotlin {n2} = {n1 + n2} 个文件）')
    return True


def main():
    which = sys.argv[1:] or ['windows', 'android']
    if not os.path.isdir(TPL):
        print(f'找不到 Flutter 模板目录: {TPL}')
        print('请设置环境变量 FLUTTER_ROOT 指向 Flutter SDK 根目录')
        return 1
    print(f'模板来源: {TPL}')
    print(f'项目名称: {VARS["projectName"]}  组织: {VARS["orgName"]}')
    ok = True
    for w in which:
        if w == 'windows':
            ok &= gen_windows()
        elif w == 'android':
            ok &= gen_android()
        else:
            print(f'  ? 未知目标: {w}')
            ok = False
    if ok:
        print('\n下一步（需在本机执行）：')
        print('  cd D:\\WorkBuddyFILE\\CreatorBox\\app_flutter')
        print('  flutter pub get')
        print('  flutter build windows --debug    # 先验证能跑')
        print('\n注：生成物已在 .gitignore 中（平台壳与机器相关，不入库）')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())