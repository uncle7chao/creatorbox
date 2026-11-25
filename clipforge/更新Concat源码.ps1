# ============================================================
# ClipForge 二开工具 —— 下载 / 更新 Concat 引擎源码
# 把 Concat 固定版本的完整源码放到 vendor\Concat\ 目录，供本地 path 依赖使用
#
# 用法：在项目根目录打开 PowerShell，运行：
#       powershell -ExecutionPolicy Bypass -File .\更新Concat源码.ps1
#
# 想换版本：改下面的 $COMMIT 和 $EXPECTED_SHA 即可（SHA 从 deps 或官方获取）。
# ============================================================

$ErrorActionPreference = "Stop"

# ---- 锁定的版本（与 src-tauri/Cargo.toml 注释、README、合规文档一致）----
$COMMIT       = "995b205492f2da908cc8aa8c83812008b10ae22f"
$TAG          = "v0.2.12"
$URL          = "https://github.com/jub0t/Concat/archive/$COMMIT.zip"
# 该归档的 sha256：首次运行脚本会在下载后打印实际值；把它填回来即可启用校验。
# 留空字符串则跳过校验（仍会用固定 commit 下载，来源可靠）。
$EXPECTED_SHA = ""

# ---- 目录 ----
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorDir  = Join-Path $ProjectDir "vendor"
$TargetDir  = Join-Path $VendorDir "Concat"
$ZipPath    = Join-Path $env:TEMP "concat-$COMMIT.zip"
$ExtractTmp = Join-Path $env:TEMP "concat-extract-$COMMIT"

Write-Host "=== ClipForge / 更新 Concat 引擎源码 ===" -ForegroundColor Cyan
Write-Host "目标版本: $TAG ($COMMIT)"
Write-Host "目标目录: $TargetDir"
Write-Host ""

# ---- 若已存在，先询问是否覆盖（保护你可能的二开修改）----
if (Test-Path $TargetDir) {
    Write-Host "⚠ vendor\Concat 已存在。" -ForegroundColor Yellow
    Write-Host "  如果里面有你改过的代码，覆盖会丢失！请先备份。" -ForegroundColor Yellow
    $answer = Read-Host "确认覆盖并重新下载? 输入 YES 继续（其他任意键取消）"
    if ($answer -ne "YES") {
        Write-Host "已取消，未改动任何文件。" -ForegroundColor Green
        exit 0
    }
    Remove-Item -Recurse -Force $TargetDir
}

# ---- 1. 下载 ----
if (-not (Test-Path $ZipPath) -or ((Get-Item $ZipPath).Length -lt 1000000)) {
    Write-Host "正在下载 Concat 源码（约 80-100MB，请耐心等待）..." -ForegroundColor Yellow
    $ok = $false
    for ($i = 1; $i -le 3; $i++) {
        try {
            Invoke-WebRequest -Uri $URL -OutFile $ZipPath -UseBasicParsing -TimeoutSec 900
            $ok = $true
            break
        } catch {
            Write-Host "第 $i 次下载失败: $($_.Exception.Message)" -ForegroundColor Red
            if ($i -lt 3) { Start-Sleep -Seconds 3 }
        }
    }
    if (-not $ok) { throw "下载失败。请检查网络，或手动下载：$URL" }
} else {
    Write-Host "发现已下载的压缩包，跳过下载。" -ForegroundColor Yellow
}

# ---- 2. 校验 ----
$actualSha = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLower()
Write-Host "下载文件 SHA256: $actualSha" -ForegroundColor Gray
if ($EXPECTED_SHA -and $actualSha -ne $EXPECTED_SHA.ToLower()) {
    throw "SHA256 校验失败！期望 $EXPECTED_SHA，实际 $actualSha。文件可能损坏。"
}

# ---- 3. 解压 ----
Write-Host "正在解压..."
if (Test-Path $ExtractTmp) { Remove-Item -Recurse -Force $ExtractTmp }
Expand-Archive -Path $ZipPath -DestinationPath $ExtractTmp -Force
$top = Get-ChildItem -Directory -Path $ExtractTmp | Select-Object -First 1
if (-not $top) { throw "解压后未找到顶层目录" }
New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null
Move-Item -Path $top.FullName -Destination $TargetDir -Force
Write-Host "源码已放到: $TargetDir" -ForegroundColor Green

# ---- 4. 校验关键文件 ----
$must = @(
  "src\Cargo.toml",
  "src\crates\concat-core\Cargo.toml",
  "src\crates\concat-media\Cargo.toml",
  "LICENSE"
)
foreach ($f in $must) {
  if (-not (Test-Path (Join-Path $TargetDir $f))) { throw "缺少关键文件: $f（源码不完整）" }
}
Write-Host "关键文件校验通过。" -ForegroundColor Green
Write-Host ""
Write-Host "=== 完成！===" -ForegroundColor Green
Write-Host "接下来进入 src-tauri 目录运行 cargo build 即可。"
Write-Host "若你想启用 SHA256 校验，把上面打印的 SHA 填回脚本顶部的 `$EXPECTED_SHA。"
