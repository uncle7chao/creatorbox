<#
  CreatorBox · 生成平台工程目录

  ⭐ 为什么需要这个
  ────────────────────
  本项目的 lib/ 是**手写**的（沙箱内 flutter 工具链不可用，见 memory），
  所以没有 android/ ios/ 等平台目录。
  `flutter run` 会直接报：
      No supported devices connected.
      The following devices were found, but are not supported by this project

  `flutter create .` 会生成平台目录，**且不会覆盖 lib/ 与 pubspec.yaml**
  （同名文件已存在时它会跳过）。

用法：
  cd D:\WorkBuddyFILE\CreatorBox\app
  .\setup-platforms.ps1
#>

$ErrorActionPreference = 'Continue'
$APP_DIR = $PSScriptRoot

Write-Host ''
Write-Host '  CreatorBox · 生成平台工程' -ForegroundColor Cyan
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray

# ── 1. 检查现状 ──
$hasAndroid = Test-Path (Join-Path $APP_DIR 'android')
$hasLib= Test-Path (Join-Path $APP_DIR 'lib\main.dart')

Write-Host '  当前状态：' -ForegroundColor DarkGray
Write-Host "    android/     : $(if ($hasAndroid) { '已存在' } else { '缺失' })" -ForegroundColor Gray
Write-Host "    lib/main.dart: $(if ($hasLib) { '存在（会被保留）' } else { '缺失（异常）' })" -ForegroundColor Gray

if (-not $hasLib) {
    Write-Host ''
    Write-Host '  ❌ lib/main.dart 不存在，停止操作' -ForegroundColor Red
    Write-Host '    这一步会创建 main.dart 并覆盖你的代码' -ForegroundColor DarkYellow
    Write-Host ''
    exit 1
}

# ── 2. 清代理（同setup-pub.ps1 的原因）──
$proxyVars = 'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
             'all_proxy', 'ALL_PROXY'
$saved = @{}
foreach ($v in $proxyVars) {
    $val = [Environment]::GetEnvironmentVariable($v)
    if ($val) {
        $saved[$v] = $val
        [Environment]::SetEnvironmentVariable($v, $null)
    }
}
# flutter create 也会读这两个
foreach ($v in 'PUB_HOSTED_URL', 'FLUTTER_STORAGE_BASE_URL') {
    $old = [Environment]::GetEnvironmentVariable($v)
    if ($old) {
        $saved[$v] = $old
        [Environment]::SetEnvironmentVariable($v, $null)
    }
}

Set-Location $APP_DIR

try {
    if ($hasAndroid) {
        Write-Host ''
        Write-Host '  android/ 已存在，跳过生成' -ForegroundColor Yellow
        Write-Host '  如需重建，先手动删除 android/ 目录' -ForegroundColor DarkGray
    } else {
        Write-Host ''
        Write-Host '  生成 Android 工程...' -ForegroundColor Cyan
        Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray

        # --platforms=android : 只生成 Android（我们要上架的是小程序/App，
        #   Windows/Web 只是本地预览用，需要时再加）
        # --org com.creatorbox : 包名，影响应用商店与包路径
        & flutter create . --platforms=android --org com.creatorbox
        $exit = $LASTEXITCODE

        if ($exit -eq 0) {
            Write-Host ''
            Write-Host '  ✅ Android 工程已生成' -ForegroundColor Green
            if (Test-Path 'android') {
                Write-Host "    路径: $APP_DIR\android" -ForegroundColor DarkGray
            }
        } else {
            Write-Host ''
            Write-Host "  ❌ 生成失败（退出码 $exit）" -ForegroundColor Red
            Write-Host '  请完整贴出错误信息' -ForegroundColor Yellow
        }
    }
} finally {
    foreach ($k in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($k, $saved[$k])
    }
}

# ── 3. 提示下一步 ──
Write-Host ''
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray
Write-Host '  接下来：' -ForegroundColor DarkGray
Write-Host ''
Write-Host '  1. 连上手机（USB 调试已开），然后：' -ForegroundColor Gray
Write-Host '       flutter devices          # 确认设备被识别' -ForegroundColor Cyan
Write-Host ''
Write-Host '  2. 转发端口（手机上的 127.0.0.1 是手机自己）：' -ForegroundColor Gray
Write-Host '       adb reverse tcp:8080 tcp:8080' -ForegroundColor Cyan
Write-Host ''
Write-Host '  3. 电脑另开一个窗口跑解析服务：' -ForegroundColor Gray
Write-Host '       cd D:\WorkBuddyFILE\CreatorBox' -ForegroundColor Cyan
Write-Host '       .\start-server.ps1' -ForegroundColor Cyan
Write-Host ''
Write-Host '  4. 运行 App：' -ForegroundColor Gray
Write-Host '       flutter run' -ForegroundColor Cyan
Write-Host ''
Write-Host '  没有手机？可先加 web 平台在电脑浏览器里看：' -ForegroundColor DarkGray
Write-Host '       flutter create . --platforms=web' -ForegroundColor Gray
Write-Host ''
