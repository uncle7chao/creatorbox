<#
  CreatorBox · 一键跑起来（Android 真机）

  把你需要敲的四条命令串成一条：
    1. 清代理 + flutter pub get（依赖没装时才会跑，已装则跳过）
    2. 起解析服务（127.0.0.1:8080，自动清掉占端口的旧进程）
    3. adb reverse tcp:8080 tcp:8080（让手机的 127.0.0.1 指向电脑）
    4. flutter run

  用法：
    cd D:\WorkBuddyFILE\CreatorBox\app
    .\run.ps1                 # 自动挑设备
    .\run.ps1 -Device chrome  # 在电脑浏览器跑（不需要手机）
    .\run.ps1 -SkipServer      # 服务已在跑时跳过第2 步
    .\run.ps1 -Api http://192.168.1.5:8080   # 手机连同一 WiFi，走局域网 IP

  ⚠️ 为什么需要第 3 步：手机上的 127.0.0.1 是「手机自己」，
     不是你的电脑。adb reverse 建立端口转发后才等价。
#>

param(
  [string]$Device = '',
  [switch]$SkipServer,
  [string]$Api = ''
)

$ErrorActionPreference = 'Continue'
$APP_DIR = $PSScriptRoot
$ROOT = Split-Path $APP_DIR -Parent
$PORT = 8080

function Say($msg, $color = 'Gray') { Write-Host "  $msg" -ForegroundColor $color }

Write-Host ''
Write-Host '  CreatorBox · 一键启动' -ForegroundColor Cyan
Write-Host '  ─────────────────────────────────' -ForegroundColor DarkGray

# ── 1. 依赖 ──
Write-Host ''
Say '[1/4] 检查依赖...' 'Cyan'
if (Test-Path (Join-Path $APP_DIR '.dart_tool\package_config.json')) {
    Say '依赖已就绪，跳过 pub get'
} else {
    Say '依赖未安装，先跑 setup-pub.ps1 ...' 'Yellow'
    & (Join-Path $APP_DIR 'setup-pub.ps1')
    if (-not (Test-Path (Join-Path $APP_DIR '.dart_tool\package_config.json'))) {
        Say '依赖获取失败，已中止（详见上方报错）' 'Red'
        exit 1
    }
    Say '依赖获取完成'
}

Set-Location $APP_DIR

# ── 2. 解析服务 ──
Write-Host ''
Say '[2/4] 解析服务...' 'Cyan'
$needServer = -not $SkipServer
if ($SkipServer) {
    Say '按要求跳过（-SkipServer）'
} else {
    # 先看端口是否已被健康的实例占用
    $health = $null
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/api/health" -TimeoutSec 3
    } catch { }

    if ($health) {
        Say "端口 $PORT 上已有服务在跑（$($health.platforms.Count) 个平台）→ 复用" 'Green'
        $needServer = $false
    } else {
        # 端口被占但不是健康实例 → 结束旧进程
        $conn = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            foreach ($pid0 in ($conn.OwningProcess | Sort-Object -Unique)) {
                $proc = Get-Process -Id $pid0 -ErrorAction SilentlyContinue
                if ($proc) {
                    Say "结束占用端口的旧进程 PID $pid0 ($($proc.ProcessName))" 'Yellow'
                    Stop-Process -Id $pid0 -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep -Seconds 2
        }
        Say "启动解析服务（后台，日志见 $ROOT\server.log）" 'Yellow'
        $serverPy = 'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
        if (-not (Test-Path $serverPy)) {
            # 回退到系统python
            $serverPy = (Get-Command python -ErrorAction SilentlyContinue).Source
        }
        if (-not $serverPy) {
            Say '找不到 Python，无法启动服务' 'Red'
            Say '请手动开一个窗口执行：cd ...\server; python -m uvicorn app.main:app --port 8080' 'Gray'
            exit 1
        }
        $srvDir = Join-Path $ROOT 'server'
        Start-Process -FilePath $serverPy `
            -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$PORT" `
            -WorkingDirectory $srvDir `
            -RedirectStandardOutput (Join-Path $ROOT 'server.log') `
            -RedirectStandardError (Join-Path $ROOT 'server.err.log') `
            -WindowStyle Hidden

        # 等它真的就绪（最多 30 秒）
        $ok = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 2
            try {
                $h = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/api/health" -TimeoutSec 3
                Say "服务就绪：$($h.platforms.Count) 个平台，engine=$($h.engine)" 'Green'
                $ok = $true
                break
            } catch { }
        }
        if (-not $ok) {
            Say '服务 30 秒内没就绪' 'Red'
            Say "看日志： Get-Content $ROOT\server.err.log -Tail 30" 'Gray'
            Say '仍可继续（App 会提示「服务未连」）' 'Yellow'
        }
    }
}

# ── 3. 设备与端口转发 ──
Write-Host ''
Say '[3/4] 设备与端口转发...' 'Cyan'

if (-not $Device) {
    $devs = & flutter devices 2>$null | Select-Object -Skip 3
    $phones = @()
    $others = @()
    foreach ($line in $devs) {
        if ($line -match '^\s*(\S+)\s+\((\w+)\)') {
            $name = $Matches[1]; $kind = $Matches[2]
            if ($kind -match 'android') { $phones += $name } else { $others += $name }
        }
    }
    if ($phones.Count -eq 1) {
        $Device = $phones[0]
        Say "自动选中唯一手机：$Device" 'Green'
    } elseif ($phones.Count -gt 1) {
        Say "检测到多台手机：$($phones -join ', ')" 'Yellow'
        $Device = $phones[0]
        Say "先用第一台（可用 -Device 指定）" 'Yellow'
    } else {
        $web = $others | Where-Object { $_ -in @('chrome', 'msedge', 'edge') }
        if ($web.Count -gt 0) {
            $Device = $web[0]
            Say "没检测到手机，自动改用浏览器：$Device" 'Yellow'
        } else {
            Say '没有可用设备' 'Red'
            Say '连手机：开 USB 调试 + 数据线，然后 flutter devices 确认' 'Gray'
            Say '或加 web 平台： flutter create . --platforms=web' 'Gray'
            exit 1
        }
    }
} else {
    Say "指定设备：$Device"
}

# android 才需要端口转发
$isWeb = $Device -in @('chrome', 'msedge', 'edge', 'web-server')
if (-not $isWeb -and $Device -notmatch 'emulator|simulator') {
    & adb reverse "tcp:$PORT" "tcp:$PORT" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Say "adb reverse 已建立：手机 127.0.0.1:$PORT → 电脑 $PORT" 'Green'
    } else {
        Say 'adb reverse 失败 —— 手机上的 127.0.0.1 会指向手机自己' 'Yellow'
        Say "改用局域网 IP： .\run.ps1 -Api http://<你的电脑IP>:$PORT" 'Yellow'
        Say '查电脑 IP： ipconfig | Select-String IPv4' 'Gray'
    }
} else {
    Say '浏览器版不需要端口转发（127.0.0.1 就是电脑自己）'
}

# ── 4. 跑 App ──
Write-Host ''
Say '[4/4] 启动 App...' 'Cyan'

$runArgs = @('run')
if ($Device) { $runArgs += @('-d', $Device) }
if ($Api) {
    $runArgs += "--dart-define=CB_API=$Api"
    Say "服务地址：$Api" 'DarkGray'
} else {
    Say '服务地址：http://127.0.0.1:8080（默认）' 'DarkGray'
}
Say '按 Ctrl+C 停止' 'DarkGray'
Write-Host ''

& flutter @runArgs
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Say 'App 已退出（正常）' 'Green'
} else {
    Say "App 退出码 $code" 'Yellow'
    Say '常见问题：' 'Gray'
    Say '  ·No supported devices → flutter devices 看设备名，用 -Device 指定' 'Gray'
    Say '  ·Connection refused 且服务端无日志 → 检查 adb reverse / -Api 局域网 IP' 'Gray'
    Say '  ·Cleartext HTTP not permitted → debug manifest 已配明文白名单，确认是 debug 构建' 'Gray'
}
Write-Host ''