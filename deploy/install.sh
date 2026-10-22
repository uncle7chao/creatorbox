#!/usr/bin/env bash
# CreatorBox 服务器端安装（Ubuntu/Debian，宝塔机已有 python3）
# 用法：cd /www/creatorbox/server && bash ../deploy/install.sh
set -e
cd "$(dirname "$0")/.."      # server/

PY=python3
echo ""
echo "  CreatorBox · 服务端安装"
echo "  ────────────────────────────────────────"

$PY --version

# ── 1. venv（幂等）────────────────────────────────────────────
if [ ! -d venv ]; then
  echo ">> 创建 venv"
  $PY -m venv venv
fi
source venv/bin/activate
python -V

# ── 2. 依赖 ───────────────────────────────────────────────────
echo ">> 安装 Python 依赖"
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── 3. playwright + chromium ───────────────────────────────────
# 用途：小红书热榜（要 Cookie + 页面签名）+ 解析兜底通道
# ⚠️ 约 170MB；国内服务器可换镜像加速：
#    export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
if ! python -c "import playwright" 2>/dev/null; then
  pip install playwright -q
fi
echo ">> 安装 chromium（~170MB）"
python -m playwright install --with-deps chromium || {
  echo ">> with-deps 失败，尝试无系统依赖安装（可能缺库，届时 apt 手补）"
  python -m playwright install chromium
}

# ── 4. 数据目录 ───────────────────────────────────────────────
echo ">> 初始化数据目录"
mkdir -p data/backup

# ── 5. 权限 ───────────────────────────────────────────────────
# ⭐ 必须在 service 启动前设好，否则 sqlite 写入报
#   "attempt to write a readonly database" —— 报错指向 DB 文件，
#   实际根因是目录属主，很容易查错方向
if id www >/dev/null 2>&1; then
  chown -R www:www data
  chmod 750 data
  echo ">> 数据目录属主已设为 www"
else
  echo ">> ⚠ 没有 www 用户（宝塔通常有）。当前用户：$(whoami)"
  echo "   请手动确保运行服务的用户对 data/ 有写权限"
fi

# ── 6. 环境变量文件 ───────────────────────────────────────────
if [ ! -f /etc/creatorbox/env ]; then
  echo ">> 创建 /etc/creatorbox/env（请填入 CB_API_KEY 等）"
  mkdir -p /etc/creatorbox
  if [ -f ../deploy/creatorbox.env.example ]; then
    cp ../deploy/creatorbox.env.example /etc/creatorbox/env
  else
    printf 'CB_API_KEY=\n' > /etc/creatorbox/env
  fi
  chmod 600 /etc/creatorbox/env
  echo "   ⭐ 必须填 CB_API_KEY，否则管理接口全部 503 锁死"
else
  echo ">> /etc/creatorbox/env 已存在，跳过"
fi

# ── 7. systemd ────────────────────────────────────────────────
if [ -f ../deploy/creatorbox.service ]; then
  echo ">> 安装 systemd 单元"
  sudo cp ../deploy/creatorbox.service /etc/systemd/system/
  sudo systemctl daemon-reload
  echo "   已执行 daemon-reload（先填好 env 再 start）"
else
  echo ">> ⚠ 找不到 deploy/creatorbox.service，跳过 systemd 安装"
fi

echo ""
echo "  ────────────────────────────────────────"
echo "  安装完成。接下来："
echo ""
echo "  1) 填密钥与小程序配置："
echo "     sudo nano /etc/creatorbox/env"
echo "     # 至少填 CB_API_KEY（管理后台用）与 CB_WX_APPID / CB_WX_SECRET"
echo ""
echo "  2) 启动服务："
echo "     sudo systemctl enable --now creatorbox"
echo "     systemctl status creatorbox"
echo ""
echo "  3) 验证（逐条打接口，指出哪一项坏了）："
echo "     bash ../deploy/verify-cn.sh"
echo ""
echo "  4) Nginx 反代 + HTTPS（宝塔面板或手工配置）："
echo "     站点域名 → 反向代理到 http://127.0.0.1:8080"
echo "     SSL 用 Let's Encrypt（Full 模式）"
echo "     防火墙只开 80/443，8080 不对公网"
echo ""
