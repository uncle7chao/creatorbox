<#
  CreatorBox 解析服务· 启动脚本（PowerShell）

用法（三选一）：
  1. 右键本文件 →「使用 PowerShell 运行」
  2. 在项目根目录执行：.\start-server.ps1
  3. 手动执行（等价）：
     cd D:\WorkBuddyFILE\CreatorBox\server
     python -m uvicorn app.main:app --host 127.0.0.1 --port 8080

启动后打开运营后台： http://127.0.0.1:8080/admin
#>

$ErrorActionPreference = 'Stop'
$PORT = 8080
$ROOT = 'D:\WorkBuddyFILE\CreatorBox'
$PY   = 'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe'

Write-Host ''
Write-Host '  CreatorBox 解析服务' -ForegroundColor Cyan
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray

# ---- 1. 端口占用检查（杀旧进程后【轮询等端口真释放】，防止新服务绑定失败闪退） ----
$busy = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $pids = $busy.OwningProcess | Sort-Object -Unique
    foreach ($p in $pids) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match 'python') {
            Write-Host "  端口 $PORT 被旧进程占用 (PID $p)，正在结束..." -ForegroundColor Yellow
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
    # 轮询最多 15 秒，端口真正释放才继续
    $released = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        if (-not (Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue)) {
            $released = $true; break
        }
    }
    if (-not $released) {
        Write-Host "  端口 $PORT 15 秒后仍被占用，无法启动。" -ForegroundColor Red
        Write-Host '  请重启电脑后重试，或手动排查占用进程。' -ForegroundColor Red
        Read-Host '按回车退出'
        exit 1
    }
    Write-Host '  旧进程已结束，端口已释放' -ForegroundColor Green
}

# ---- 2. Python 解释器 ----
if (-not (Test-Path $PY)) {
    Write-Host "  找不到虚拟环境 Python: $PY" -ForegroundColor Red
    Write-Host '  请先执行: C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m pip install -r requirements.txt' -ForegroundColor DarkGray
    Read-Host '按回车退出'
    exit 1
}

# ---- 2.5 小红书 Cookie（可选，存在即加载）----
$cookieFile = "$ROOT\server\xhs-cookie.txt"
if (Test-Path $cookieFile) {
    $env:CB_XHS_COOKIE = (Get-Content $cookieFile -Raw).Trim()
    Write-Host '  小红书 Cookie: 已加载' -ForegroundColor Green
}

# ---- 2.6 微博 Cookie（可选，存在即加载：热榜-微博 tab 需要）----
$wbCookieFile = "$ROOT\server\weibo-cookie.txt"
if (Test-Path $wbCookieFile) {
    $env:CB_WEIBO_COOKIE = (Get-Content $wbCookieFile -Raw).Trim()
    Write-Host '  微博 Cookie: 已加载' -ForegroundColor Green
} else {
    Write-Host '  微博 Cookie: 未配置（热榜-微博 tab 会提示配置方法）' -ForegroundColor DarkGray
}

# ---- 2.7 管理密钥 CB_API_KEY（运营后台 /api/admin/* 用）----
# 为什么要有这段：服务端对管理接口采取【默认拒绝】——
# 未配置 Key 时所有 /api/admin/* 返回 503 锁死。这是故意的安全设计：
# 忘配密钥的部署不该把卡密、违禁词、用户名单敞开。
# 这里做「首次自动生成 + 之后一直复用同一个」，
# 这样你不用手抄，也不会出现重启后密钥变了导致后台连不上的情况。
$keyFile = "$ROOT\server\.api_key"
if (Test-Path $keyFile) {
    $env:CB_API_KEY = (Get-Content $keyFile -Raw).Trim()
    Write-Host '  管理密钥: 已加载（server\.api_key）' -ForegroundColor Green
} else {
    # 32 字节随机 → 43 字符 base64url，足够长且不含易混字符
    $gen = & $PY -c "import secrets; print(secrets.token_urlsafe(32))"
    if ($gen) {
        $gen = $gen.Trim()
        Set-Content -Path $keyFile -Value $gen -Encoding ASCII -NoNewline
        $env:CB_API_KEY = $gen
        Write-Host '  管理密钥: 首次已自动生成 → server\.api_key' -ForegroundColor Yellow
        Write-Host "           $gen" -ForegroundColor DarkGray
        Write-Host '           ↑ 填进运营后台顶部「CB_API_KEY」框（只需填这一次）' -ForegroundColor DarkGray
    }
}

# ---- 3. 启动（try/catch 兜底：任何报错都停住窗口，绝不闪退） ----
Set-Location "$ROOT\server"
Write-Host "  工作目录: $ROOT\server" -ForegroundColor DarkGray
Write-Host "  监听地址: http://127.0.0.1:$PORT" -ForegroundColor Green
Write-Host "  运营后台: http://127.0.0.1:$PORT/admin" -ForegroundColor Green
    Write-Host "    （若刚更新过代码，请重启本脚本以加载新版后台）" -ForegroundColor DarkGray
Write-Host ''
Write-Host '  服务启动后【不要关这个窗口】（关闭 = 停止服务）' -ForegroundColor Yellow
Write-Host '  按 Ctrl+C 可停止服务' -ForegroundColor DarkGray
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray
Write-Host ''

try {
    & $PY -m uvicorn app.main:app --host 127.0.0.1 --port $PORT
}
catch {
    Write-Host ''
    Write-Host "  启动失败: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ''
Write-Host '  服务已退出（正常停止或出错）。按回车关闭窗口。' -ForegroundColor Yellow
Read-Host '按回车退出'
