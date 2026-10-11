#!/usr/bin/env bash
# CreatorBox 服务器端安装（Ubuntu/Debian，宝塔机已有 python3）
# 用法：cd /www/creatorbox/server && bash ../deploy/install.sh
set -e
cd "$(dirname "$0")/.."      # server/

PY=python3
$PY --version

# venv（幂等）
if [ ! -d venv ]; then
  $PY -m venv venv
fi
source venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q

# playwright + chromium（浏览器兜底层 & 小红书热榜通道）
if ! python -c "import playwright" 2>/dev/null; then
  pip install playwright -q
fi
echo '>> 安装 chromium（~170MB，境外网络约 1 分钟）'
python -m playwright install --with-deps chromium || {
  echo '>> with-deps 失败，尝试无系统依赖安装（可能缺库，届时 apt 手补）'
  python -m playwright install chromium
}

# 数据目录
mkdir -p data/backup

echo '>> 安装完成。下一步：'
echo '   sudo cp ../deploy/creatorbox.service /etc/systemd/system/'
echo '   先在 service 文件里填好 CB_API_KEY，再 systemctl enable --now creatorbox'
