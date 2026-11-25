# ============================================================
# ClipForge 依赖一键安装脚本 —— FFmpeg 8.1.3 (LGPL shared)
# 版本来源：Concat 官方 CI 锁定的同一版本（deps.lock），带 SHA256 校验
# 用法：在本文件夹空白处按住 Shift + 右键 -> "在此处打开 PowerShell 窗口"
#       然后运行： powershell -ExecutionPolicy Bypass -File .\安装FFmpeg.ps1
# ============================================================

$ErrorActionPreference = "Stop"

# ---- 可改：安装根目录（默认放 D 盘；D 盘不存在则退回 E 盘）----
if (Test-Path "D:\") {
    $InstallRoot = "D:\ffmpeg"
} else {
    $InstallRoot = "E:\ffmpeg"
}
$ZipName     = "ffmpeg-n8.1.3-9-g29e619e767-win64-lgpl-shared-8.1.zip"
$Url         = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/$ZipName"
$ExpectedSha = "3e47bda1607740550141e37c0e49d1e5182b34699f15adfd137ee266d346811a"

Write-Host "=== ClipForge FFmpeg 安装 ===" -ForegroundColor Cyan
Write-Host "安装位置: $InstallRoot"
Write-Host "版本: FFmpeg 8.1.3 LGPL shared (Concat 官方 CI 同款)"
Write-Host ""

# 若已装过且目录里有 include/lib，直接跳过
if ((Test-Path "$InstallRoot\include") -and (Test-Path "$InstallRoot\lib")) {
    Write-Host "检测到 FFmpeg 已安装：$InstallRoot （含 include/lib），跳过下载。" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    $ZipPath = Join-Path $env:TEMP $ZipName

    # ---- 1. 下载（带重试）----
    if (-not (Test-Path $ZipPath) -or ((Get-Item $ZipPath).Length -lt 70000000)) {
        Write-Host "正在下载 FFmpeg（约 80MB，请耐心等待）..." -ForegroundColor Yellow
        $ok = $false
        for ($i = 1; $i -le 3; $i++) {
            try {
                Invoke-WebRequest -Uri $Url -OutFile $ZipPath -UseBasicParsing -TimeoutSec 600
                $ok = $true
                break
            } catch {
                Write-Host "第 $i 次下载失败：$($_.Exception.Message)" -ForegroundColor Red
                if ($i -lt 3) { Start-Sleep -Seconds 3 }
            }
        }
        if (-not $ok) { throw "下载失败，请检查网络后重试，或手动下载：$Url" }
    } else {
        Write-Host "发现已下载的压缩包，跳过下载。" -ForegroundColor Yellow
    }

    # ---- 2. 校验 SHA256（防止文件损坏）----
    Write-Host "正在校验文件完整性..."
    $ActualSha = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLower()
    if ($ActualSha -ne $ExpectedSha) {
        throw "SHA256 校验失败！`n期望: $ExpectedSha`n实际: $ActualSha`n文件可能损坏或被篡改，已删除，请重新运行。"
    }
    Write-Host "SHA256 校验通过。" -ForegroundColor Green

    # ---- 3. 解压到临时目录，再把内容移到 $InstallRoot ----
    Write-Host "正在解压..."
    $ExtractRoot = Join-Path $env:TEMP "ffmpeg_extract"
    if (Test-Path $ExtractRoot) { Remove-Item -Recurse -Force $ExtractRoot }
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractRoot -Force
    $Inner = Get-ChildItem -Directory -Path $ExtractRoot | Select-Object -First 1
    if (-not $Inner) { throw "解压后未找到顶层文件夹" }
    Copy-Item -Path (Join-Path $Inner.FullName "*") -Destination $InstallRoot -Recurse -Force
    Write-Host "已解压到 $InstallRoot" -ForegroundColor Green
}

# ---- 4. 最终检查 ----
$Need = @("include", "lib", "bin")
foreach ($d in $Need) {
    if (-not (Test-Path "$InstallRoot\$d")) { throw "缺少目录 $d，安装可能不完整。" }
}
Write-Host ""
Write-Host "=== 安装完成！===" -ForegroundColor Green
Write-Host "FFmpeg 目录: $InstallRoot"
Write-Host ""
Write-Host ">>> 请在【同一个 PowerShell 窗口】复制运行下面两行 <<<" -ForegroundColor Cyan
Write-Host ""
Write-Host "  `$env:FFMPEG_DIR = `"$InstallRoot`"" -ForegroundColor Yellow
Write-Host "  `$env:PATH = `"$InstallRoot\bin;`$env:PATH`"" -ForegroundColor Yellow
Write-Host ""
Write-Host "然后进入项目编译："
Write-Host "  cd D:\WorkBuddyFILE\CreatorBox\clipforge\src-tauri" -ForegroundColor Yellow
Write-Host "  cargo build" -ForegroundColor Yellow
