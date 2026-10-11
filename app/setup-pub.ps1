<#
  CreatorBox · Flutter 依赖获取

  ⭐ 2026-10-06 重要更正
  ────────────────────────────
  上一版脚本让我设了国内镜像（pub.flutter-io.cn），**结果更糟**：
    · 镜像的归档接口 301 跳转到 storage.flutter-io.cn
    · 该域名在你本机 DNS 解析失败（直连）/ 被代理拦成 502（走代理）
    · pub 跟重定向时挂死 → 45 分钟 0 个包

  实测对照（清代理后）：
    pub.dev 直连         1.4–1.8s/包，可用 ✅
    清华 dart-pub 镜像   404 ❌
    pub.flutter-io.cn    301 → 死链 ❌

  所以正确做法是：**只清代理，用官方源**。

用法：
  cd D:\WorkBuddyFILE\CreatorBox\app
  .\setup-pub.ps1
#>

$ErrorActionPreference = 'Continue'
$APP_DIR = $PSScriptRoot

Write-Host ''
Write-Host '  CreatorBox · 依赖获取' -ForegroundColor Cyan
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray

# ── 1. 打印并临时清除代理 ──
# pub 走 Dart HttpClient，它读这些环境变量。代理不是「没它上不了网」，
# 本例中反而让速度慢 11 倍。
$proxyVars = 'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
             'all_proxy', 'ALL_PROXY'
$saved = @{}

Write-Host '  当前代理：' -ForegroundColor DarkGray
$hasProxy = $false
foreach ($v in $proxyVars) {
    $val = [Environment]::GetEnvironmentVariable($v)
    if ($val) {
        Write-Host "    $v = $val" -ForegroundColor DarkYellow
        $saved[$v] = $val
        [Environment]::SetEnvironmentVariable($v, $null)
        $hasProxy = $true
    }
}
if (-not $hasProxy) { Write-Host '    （无）' -ForegroundColor DarkGray }
else { Write-Host '    → 已临时清除（仅本进程）' -ForegroundColor Green }

# ── 2. 确保不残留镜像配置 ──
# ⭐ 上一版设的 PUB_HOSTED_URL 会导致归档下载 301 到死链，必须清掉。
foreach ($v in 'PUB_HOSTED_URL', 'FLUTTER_STORAGE_BASE_URL') {
    $old = [Environment]::GetEnvironmentVariable($v)
    if ($old) {
        Write-Host "  清除残留 $($v) = $old" -ForegroundColor Yellow
        [Environment]::SetEnvironmentVariable($v, $null)
    }
}
Write-Host '  使用源：pub.dev（官方，实测直连 1.4s/包）' -ForegroundColor DarkGray

# ── 3. 预检：先花 10 秒确认网络，别再跑 45 分钟才发现不通 ──
Write-Host ''
Write-Host '  预检网络...' -ForegroundColor DarkGray
try {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    # 用归档接口测（这才是真正会卡住的地方），不只测元数据
    $null = Invoke-WebRequest -Uri 'https://pub.dev/api/archives/path-1.9.0.tar.gz' `
         -TimeoutSec 15 -UseBasicParsing
    $sw.Stop()
    Write-Host ("    ✅ 通  {0}ms" -f $sw.ElapsedMilliseconds) -ForegroundColor Green
} catch {
    Write-Host "    ❌ 不通：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    Write-Host '    可能原因：' -ForegroundColor DarkGray
    Write-Host '    ·代理未清干净 → 关掉代理软件后重试' -ForegroundColor Gray
    Write-Host '    · 需要 VPN → 开代理时改为保留 http_proxy' -ForegroundColor Gray
    Write-Host '    · DNS 问题 → 试试 8.8.8.8 或 114.114.114.114' -ForegroundColor Gray
    Write-Host ''
    Write-Host '  已中止（避免再空等几十分钟）' -ForegroundColor Yellow
    foreach ($k in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($k, $saved[$k])
    }
    Write-Host ''
    exit 1
}

# ── 4. 执行 pub get ──
Write-Host ''
Write-Host '  开始获取依赖（首次约需 1-3 分钟）...' -ForegroundColor Cyan
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray
Write-Host ''

Set-Location $APP_DIR
$exit = 1
try {
    & flutter pub get
    $exit = $LASTEXITCODE
} finally {
    foreach ($k in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($k, $saved[$k])
    }
}

Write-Host ''
if ($exit -eq 0) {
    Write-Host '  ✅ 依赖获取完成' -ForegroundColor Green
    Write-Host ''
    Write-Host '  ⚠ 当前项目只有 lib/，还没有平台目录。' -ForegroundColor Yellow
    Write-Host '    执行下面这条生成 Android 工程（不会覆盖 lib/）：' -ForegroundColor Gray
    Write-Host ''
    Write-Host '      flutter create . --platforms=android --org com.creatorbox' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '  ⚠ 真机调试需转发端口：' -ForegroundColor Yellow
    Write-Host '      adb reverse tcp:8080 tcp:8080' -ForegroundColor Gray
} else {
    Write-Host "  ❌ 失败（退出码 $exit）" -ForegroundColor Red
    Write-Host '  排查：' -ForegroundColor DarkGray
    Write-Host '  1. 磁盘空间（pub cache 需 1–2GB）: Get-PSDrive C' -ForegroundColor Gray
    Write-Host '  2. 代理软件是否在运行 → 关掉再试' -ForegroundColor Gray
    Write-Host '  3. 具体报错请完整贴给我' -ForegroundColor Gray
}
Write-Host ''
