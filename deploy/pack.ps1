# CreatorBox 服务端打包脚本（本机 PowerShell）
# 产出：deploy\creatorbox_server_<date>.zip
# 排除：本地数据库、__pycache__、浏览器缓存、测试产物（tests 保留）
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot          # CreatorBox/
$server = Join-Path $root 'server'
$stamp = Get-Date -Format 'yyyyMMdd'
$zip = Join-Path $PSScriptRoot "creatorbox_server_$stamp.zip"

if (Test-Path $zip) { Remove-Item $zip -Force }

# 打包内容：app/ admin/ tests/ requirements.txt（其余一律不入包）
$staging = Join-Path $env:TEMP "cb_pack_$stamp"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null

foreach ($item in @('app', 'admin', 'tests', 'requirements.txt')) {
    Copy-Item (Join-Path $server $item) (Join-Path $staging $item) -Recurse
}
# 清理 __pycache__
Get-ChildItem $staging -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force

Compress-Archive -Path "$staging\*" -DestinationPath $zip -Force
Remove-Item $staging -Recurse -Force

$size = '{0:N1} KB' -f ((Get-Item $zip).Length / 1KB)
Write-Host "打包完成: $zip ($size)"
Write-Host '上传到服务器 /www/creatorbox/ 后按 deploy\README-部署指引.md 继续'
