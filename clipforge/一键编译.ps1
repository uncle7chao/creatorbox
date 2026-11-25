# ============================================================
# ClipForge 一键编译脚本（Windows）
# 自动配置 MSVC / FFmpeg / LLVM 环境并编译项目
# 用法：在项目根目录右键"用 PowerShell 运行"，或：
#       powershell -ExecutionPolicy Bypass -File .\一键编译.ps1
# 编译成功后会打印可执行文件路径。
# ============================================================

$ErrorActionPreference = "Stop"

# ---- 工具路径（按本机实测填好；换机器时改这里）----
$MSVC      = "D:\dev\vs2022bt\VC\Tools\MSVC\14.44.35207"
$SDK       = "C:\Program Files (x86)\Windows Kits\10"
$SDKV      = "10.0.26100.0"
$FFMPEG    = "E:\clipforge-tools\ffmpeg"
$LLVM      = "C:\Program Files\LLVM\bin"
$CMAKE     = "E:\clipforge-tools\cmake\bin"

Write-Host "=== ClipForge 一键编译 ===" -ForegroundColor Cyan

# ---- 前置检查 ----
$need = @(
  @{ p = "$MSVC\bin\Hostx64\x64\cl.exe";       n = "MSVC 编译器 cl.exe" },
  @{ p = "$SDK\Lib\$SDKV\um\x64\kernel32.lib"; n = "Windows SDK kernel32.lib" },
  @{ p = "$FFMPEG\lib\avcodec.lib";            n = "FFmpeg 开发库 avcodec.lib" },
  @{ p = "$LLVM\libclang.dll";                 n = "LLVM libclang.dll" },
  @{ p = "$PSScriptRoot\vendor\Concat\src\Cargo.toml"; n = "Concat 源码" }
)
foreach ($item in $need) {
  if (-not (Test-Path $item.p)) {
    Write-Host "✗ 缺少: $($item.n)  ($($item.p))" -ForegroundColor Red
    Write-Host "  请参考 BUILD.md 安装缺失的组件。" -ForegroundColor Yellow
    exit 1
  }
  Write-Host "✓ $($item.n)" -ForegroundColor Green
}

# ---- 构造环境变量 ----
$env:LIB      = "$MSVC\lib\x64;$SDK\Lib\$SDKV\um\x64;$SDK\Lib\$SDKV\ucrt\x64"
$env:INCLUDE  = "$MSVC\include;$SDK\Include\$SDKV\um;$SDK\Include\$SDKV\ucrt;$SDK\Include\$SDKV\shared;$SDK\Include\$SDKV\winrt;$SDK\Include\$SDKV\cppwinrt"
$env:PATH     = "$LLVM;$MSVC\bin\Hostx64\x64;$FFMPEG\bin;$CMAKE;$env:PATH"
$env:FFMPEG_DIR     = $FFMPEG
$env:LIBCLANG_PATH  = $LLVM
$env:CC       = "cl.exe"
$env:CXX      = "cl.exe"

# ---- 编译 ----
Push-Location (Join-Path $PSScriptRoot "src-tauri")
try {
  Write-Host "开始编译（首次可能几分钟）..." -ForegroundColor Yellow
  # cargo 的进度输出走 stderr，在 Stop 模式下会被误判为错误；临时改回 Continue
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & cargo build 2>&1 | ForEach-Object { Write-Host $_ }
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
  if ($code -ne 0) { throw "cargo build 失败，退出码 $code" }
} finally {
  Pop-Location
}

# ---- 关键：把 FFmpeg 运行时 dll 复制到 exe 同目录 ----
# Windows 会优先在 exe 所在目录查找 dll，这样双击 exe 即可运行，无需手动设 PATH。
$debugDir = Join-Path $PSScriptRoot "src-tauri\target\debug"
$dllSrc   = Join-Path $FFMPEG "bin"
if ((Test-Path $debugDir) -and (Test-Path $dllSrc)) {
  $dlls = Get-ChildItem -Path $dllSrc -Filter *.dll -ErrorAction SilentlyContinue
  if ($dlls) {
    Write-Host "复制 FFmpeg 运行库到 exe 目录（$($dlls.Count) 个 dll）..." -ForegroundColor Yellow
    $dlls | Copy-Item -Destination $debugDir -Force
    Write-Host "✓ 已复制，exe 可直接运行" -ForegroundColor Green
  }
}

$exe = Join-Path $PSScriptRoot "src-tauri\target\debug\clipforge.exe"
Write-Host ""
Write-Host "=== 编译成功 ===" -ForegroundColor Green
Write-Host "可执行文件: $exe" -ForegroundColor Cyan
Write-Host "FFmpeg 运行库已复制到同目录，可直接运行（双击或下面命令）："
Write-Host "  & `"$exe`""
