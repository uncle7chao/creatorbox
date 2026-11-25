# ============================================================
# 星创映画（CreatorBox）· 桌面剪辑版 —— 完整版一键编译
# 路线 A：编译 Concat 完整应用（已做品牌化改动）
#
# 用法（在项目根目录）：
#   powershell -ExecutionPolicy Bypass -File .\编译完整版.ps1
#
# 说明：Concat 的界面用 Slint，依赖 Skia 渲染库。Skia 从 GitHub 拉不动时，
# 本脚本会自动用镜像下载"预编译包"并喂给构建系统，跳过耗时数小时的源码编译。
# ============================================================
$ErrorActionPreference = "Stop"

# ---- 本机工具路径（换机器时改这里）----
$MSVC   = "D:\dev\vs2022bt\VC\Tools\MSVC\14.44.35207"
$SDK    = "C:\Program Files (x86)\Windows Kits\10"
$SDKV   = "10.0.26100.0"
$FFMPEG = "E:\clipforge-tools\ffmpeg"
$LLVM   = "C:\Program Files\LLVM\bin"
$CMAKE  = "E:\clipforge-tools\cmake\bin"

# ---- Skia 预编译包（必须与 Slint 的 features 匹配；Windows 需 d3d 后端）----
$SkiaKey = "b7f043e0b1e2a850e702-x86_64-pc-windows-msvc-d3d-ganesh-gl-jpegd-jpege-pdf-textlayout"
$SkiaDir = "E:\skia-cache"
$SkiaPkg = Join-Path $SkiaDir "skia-binaries-$SkiaKey.tar.gz"
$SkiaUrl = "https://gh-proxy.com/https://github.com/rust-skia/skia-binaries/releases/download/0.153.3/skia-binaries-$SkiaKey.tar.gz"

Write-Host "=== 星创映画桌面剪辑版 · 开发版编译（quick，日常迭代用）===" -ForegroundColor Cyan

# ---- 1. 前置检查 ----
$checks = @(
  @{ p = "$MSVC\bin\Hostx64\x64\cl.exe";               n = "MSVC 编译器" },
  @{ p = "$SDK\bin\$SDKV\x64\rc.exe";                  n = "Windows SDK rc.exe" },
  @{ p = "$FFMPEG\lib\avcodec.lib";                    n = "FFmpeg 开发库" },
  @{ p = "$LLVM\libclang.dll";                         n = "LLVM libclang" },
  @{ p = "$PSScriptRoot\vendor\Concat\src\Cargo.toml"; n = "Concat 源码" }
)
foreach ($c in $checks) {
  if (-not (Test-Path $c.p)) {
    Write-Host "✗ 缺少: $($c.n)  ($($c.p))" -ForegroundColor Red
    exit 1
  }
  Write-Host "✓ $($c.n)" -ForegroundColor Green
}

# ---- 2. 准备 Skia 预编译包 ----
if (-not (Test-Path $SkiaDir)) { New-Item -ItemType Directory -Force -Path $SkiaDir | Out-Null }
if ((Test-Path $SkiaPkg) -and ((Get-Item $SkiaPkg).Length -gt 10MB)) {
  Write-Host "✓ Skia 预编译包已就绪" -ForegroundColor Green
} else {
  Write-Host "正在下载 Skia 预编译包（约 24MB）..." -ForegroundColor Yellow
  & curl.exe -L -o $SkiaPkg --connect-timeout 20 --max-time 900 $SkiaUrl
  if (-not (Test-Path $SkiaPkg) -or (Get-Item $SkiaPkg).Length -lt 10MB) {
    Write-Host "✗ Skia 包下载失败，请检查网络后重试。" -ForegroundColor Red
    exit 1
  }
  Write-Host "✓ Skia 预编译包下载完成" -ForegroundColor Green
}

# ---- 3. 给 skia-bindings 打补丁（允许用 SKIA_FORCE_KEY 指定包）----
$cargoHome = if ($env:CARGO_HOME) { $env:CARGO_HOME } else { Join-Path $env:USERPROFILE ".cargo" }
$dl = Get-ChildItem "$cargoHome\registry\src\*\skia-bindings-*\build_support\binary_cache\download.rs" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($dl) {
  if (Select-String -Path $dl.FullName -Pattern 'SKIA_FORCE_KEY' -Quiet) {
    Write-Host "✓ skia-bindings 补丁已存在" -ForegroundColor Green
  } else {
    $text = [IO.File]::ReadAllText($dl.FullName)
    $anchor = "    let tag = cargo::package_version();"
    $i = $text.IndexOf($anchor)
    if ($i -ge 0) {
      $inject = $anchor + "`r`n`r`n    // Patched by ClipForge: allow forcing a key for mirror/offline builds.`r`n    if let Ok(key) = ::std::env::var(`"SKIA_FORCE_KEY`") {`r`n        return Some((tag, key));`r`n    }"
      $text = $text.Substring(0, $i) + $inject + $text.Substring($i + $anchor.Length)
      [IO.File]::WriteAllText($dl.FullName, $text, (New-Object Text.UTF8Encoding $false))
      Write-Host "✓ 已给 skia-bindings 打补丁" -ForegroundColor Green
    } else {
      Write-Host "⚠ 未找到补丁插入点（不影响，稍后若失败请告知）" -ForegroundColor Yellow
    }
  }
} else {
  Write-Host "⚠ 尚未下载到 skia-bindings 源码；本次编译会先拉依赖，若停在 Skia 请再运行一次本脚本。" -ForegroundColor Yellow
}

# ---- 4. 环境变量 ----
$env:LIB     = "$MSVC\lib\x64;$SDK\Lib\$SDKV\um\x64;$SDK\Lib\$SDKV\ucrt\x64"
$env:INCLUDE = "$MSVC\include;$SDK\Include\$SDKV\um;$SDK\Include\$SDKV\ucrt;$SDK\Include\$SDKV\shared;$SDK\Include\$SDKV\winrt;$SDK\Include\$SDKV\cppwinrt"
$env:PATH    = "$SDK\bin\$SDKV\x64;$LLVM;$MSVC\bin\Hostx64\x64;$FFMPEG\bin;$CMAKE;$env:PATH"
$env:RC_TOOLKIT_PATH  = "$SDK\bin\$SDKV\x64"
$env:FFMPEG_DIR       = $FFMPEG
$env:LIBCLANG_PATH    = $LLVM
$env:CC               = "cl.exe"
$env:CXX              = "cl.exe"
$env:RUSTUP_TOOLCHAIN = "1.95.0"

$env:FORCE_SKIA_BINARIES_DOWNLOAD = "1"
$env:SKIA_FORCE_KEY    = $SkiaKey
$env:SKIA_BINARIES_URL = 'file://' + ($SkiaPkg -replace '\\','/')

Write-Host ""
Write-Host "开始编译开发版（quick profile：依赖用 release 优化、界面 crate 不优化 + 增量，之后每次改界面只需 1-3 分钟）..." -ForegroundColor Yellow

# ---- 5. 编译 ----
Push-Location (Join-Path $PSScriptRoot "vendor\Concat\src")
try {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & cargo build -p concat --profile quick 2>&1 | ForEach-Object { Write-Host $_ }
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
  if ($code -ne 0) { throw "cargo build 失败，退出码 $code" }
} finally {
  Pop-Location
}

# ---- 6. 复制 FFmpeg 运行库，便于直接运行 ----
$exeDir = Join-Path $PSScriptRoot "vendor\Concat\src\target\quick"
$dlls = Get-ChildItem -Path "$FFMPEG\bin" -Filter *.dll -ErrorAction SilentlyContinue
if ($dlls -and (Test-Path $exeDir)) { $dlls | Copy-Item -Destination $exeDir -Force }

# ---- 7. 同步到发布目录（双击即可运行的成品）----
$pubDir = Join-Path $PSScriptRoot "星创映画（开发版）"
New-Item -ItemType Directory -Force -Path $pubDir | Out-Null
Copy-Item (Join-Path $exeDir "concat.exe") -Destination (Join-Path $pubDir "星创映画.exe") -Force
if ($dlls) { $dlls | Copy-Item -Destination $pubDir -Force }
$pubExe = Join-Path $pubDir "星创映画.exe"

Write-Host ""
Write-Host "=== 编译成功 ===" -ForegroundColor Green
Write-Host "双击这个文件即可运行："
Write-Host "  $pubExe" -ForegroundColor Cyan
Write-Host ""
Write-Host "（编译产物原始位置: $exeDir\concat.exe）"
