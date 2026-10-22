#!/usr/bin/env bash
# CreatorBox 部署后验证（大陆服务器）
# 用法：cd /www/creatorbox/server && bash ../deploy/verify-cn.sh
#
# ⭐ 为什么要自动验证：部署"看起来成功"和"真的能用"是两件事。
#   最常见的翻车：systemd 起来了但端口没监听 / 绑到了 127.0.0.1
#   导致 Nginx 502 / 密钥没配导致管理接口全 503 / 探针全 down。
#   这些在浏览器里看都是"白屏"，只有逐条打接口才能定位。
set -u
BASE="${1:-http://127.0.0.1:8080}"
PASS=0; FAIL=0
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RST=$'\033[0m'

# ⭐ 临时文件放当前目录而不是 /tmp：
#   Git Bash（Windows）下 /tmp 可能不存在或与 Python 看到的路径不一致，
#   实测踩过：「响应不是合法 JSON: No such file or directory: /tmp/...」
#   —— 报错指向 JSON，实际是路径问题，极易查错方向。
TMP="$(mktemp 2>/dev/null || true)"
if [ -z "$TMP" ] || [ ! -f "$TMP" ]; then
  TMP="./cb_verify_$$.json"
fi
cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

# ⭐ 是否需要 API Key：
#   配了 CB_API_KEY 时，/api/parse 也要带 Key（check_admin_or_open：
#   配了就校验，没配才放行）。脚本要跟着实际部署走，不能硬编码「无 Key」。
#   优先从 /etc/creatorbox/env 读，读不到就试本机 .api_key。
API_KEY=""
# 路径要覆盖多种运行位置：从项目根跑、从 server/ 跑、从 deploy/ 跑
for f in /etc/creatorbox/env \
         ./server/.api_key ./server/server/.api_key \
         ./.api_key ../.api_key ../server/.api_key; do
  if [ -f "$f" ]; then
    # 两种格式都要认：
    #   ① /etc/creatorbox/env → CB_API_KEY=xxx（systemd EnvironmentFile 格式）
    #   ② server/.api_key     → 裸密钥（start-server.ps1 自动生成的，43位无换行）
    v=$(grep -E '^CB_API_KEY=' "$f" 2>/dev/null | head -1 | cut -d= -f2-)
    if [ -z "$v" ]; then
      v=$(head -c 200 "$f" 2>/dev/null | tr -d '\r\n' | head -c 100)
      # 只在没有 '=' 的情况下当裸密钥用
      case "$v" in *'='*) v='' ;; esac
    fi
    if [ -n "$v" ]; then API_KEY="$v"; break; fi
  fi
done
[ -z "$API_KEY" ] && API_KEY="${CB_API_KEY:-}"

ok()   { PASS=$((PASS+1)); echo "${GRN}  ✅ $1${RST}"; }
bad()  { FAIL=$((FAIL+1)); echo "${RED}  ❌ $1${RST}"; [ -n "${2:-}" ] && echo "      $2"; }
warn() { echo "${YEL}  ⚠  $1${RST}"; }

# 带 Key 的 curl 包装
api_curl() {   # api_curl <method> <path> [json_body]
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$API_KEY" ]; then
    if [ -n "$body" ]; then
      curl -s -o "$TMP" -w '%{http_code}' -X "$method" "$BASE$path" \
        -H "X-Api-Key: $API_KEY" -H 'Content-Type: application/json' -d "$body"
    else
      curl -s -o "$TMP" -w '%{http_code}' -X "$method" "$BASE$path" \
        -H "X-Api-Key: $API_KEY"
    fi
  else
    if [ -n "$body" ]; then
      curl -s -o "$TMP" -w '%{http_code}' -X "$method" "$BASE$path" \
        -H 'Content-Type: application/json' -d "$body"
    else
      curl -s -o "$TMP" -w '%{http_code}' -X "$method" "$BASE$path"
    fi
  fi
}

echo ""
echo "  CreatorBox 部署验证 → $BASE"
echo "  ────────────────────────────────────────"

# ── 1. 服务存活 ────────────────────────────────────────────────
code=$(api_curl GET /api/health || echo 000)
if [ "$code" = "200" ]; then
  ok "服务可访问（/api/health 200）"
else
  bad "服务不可访问（HTTP $code）" "检查：systemctl status creatorbox / ss -lntp | grep 8080"
  echo ""; echo "${RED}服务没起来，后续检查无意义，先解决这个。${RST}"
  exit 1
fi

# ── 2. 关键字段 ───────────────────────────────────────────────
CB_TMP="$TMP" python3 - <<'PY'
import json, os, sys
try:
    d = json.load(open(os.environ['CB_TMP']))
except Exception as e:
    print(f'  ❌ health 响应不是合法 JSON: {e}'); sys.exit(1)
plats = d.get('platforms') or []
if isinstance(plats, dict):
    n = len(plats)
elif isinstance(plats, list):
    n = len(plats)
else:
    n = 0
print(f'  {"✅" if d.get("ready") else "❌"} ready={d.get("ready")}  平台数={n}  版本={d.get("version","?")}')
if not d.get('ready'):
    print('      服务未就绪 —— 看 journalctl -u creatorbox -n 50')
PY

# ── 3. 管理接口鉴权（应 401，不是 200 更不是 503）─────────────
if [ -n "$API_KEY" ]; then
  code=$(api_curl GET /api/admin/codes)
  if [ "$code" = "200" ]; then
    ok "管理接口可用（带 Key → 200）"
  elif [ "$code" = "503" ]; then
    bad "管理接口锁死（503）" "服务端进程读不到 /etc/creatorbox/env 的 CB_API_KEY"
  else
    bad "管理接口异常（HTTP $code）" "检查 systemctl show creatorbox | grep CB_API_KEY"
  fi
  # 反向验证：不带 Key 必须被拒（确认鉴权真的生效）
  raw=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/admin/codes")
  if [ "$raw" = "401" ]; then
    ok "管理接口鉴权生效（无 Key → 401）"
  else
    bad "⚠ 不带 Key 竟返回 $raw —— 鉴权失效，必须立刻查"
  fi
else
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/admin/codes")
  if [ "$code" = "503" ]; then
    bad "管理接口锁死（503）" "CB_API_KEY 没配 → 填 /etc/creatorbox/env 后 systemctl restart"
  else
    warn "未读到 CB_API_KEY（可能未配），管理接口返回 $code"
  fi
fi

# ── 4. 解析接口可用 ───────────────────────────────────────────
code=$(api_curl POST /api/parse '{"text":"not-a-url"}')
if [ "$code" = "200" ] || [ "$code" = "400" ]; then
  ok "解析接口可达（HTTP $code）"
elif [ "$code" = "401" ]; then
  bad "解析接口要鉴权但脚本没拿到 Key" "脚本读不到 /etc/creatorbox/env 的 CB_API_KEY"
else
  bad "解析接口异常（HTTP $code）" "看 journalctl -u creatorbox -n 50"
fi

# ── 5. 公开接口（小程序入口依赖）──────────────────────────────
for ep in /api/visibility /api/capabilities; do
  code=$(api_curl GET "$ep")
  if [ "$code" = "200" ]; then ok "$ep 正常"; else bad "$ep 异常（HTTP $code）"; fi
done

# ── 6. 数据库可写 ─────────────────────────────────────────────
DB=${CB_DB_PATH:-/www/creatorbox/server/data/cb.db}
if [ -f "$DB" ]; then
  if [ -w "$DB" ] || [ -w "$(dirname "$DB")" ]; then
    ok "数据库可写（$DB）"
  else
    bad "数据库不可写" "chown -R www:www /www/creatorbox/server/data"
  fi
else
  warn "数据库不存在（首次启动会自动创建）：$DB"
fi

# ── 7. 国内平台真网连通 ───────────────────────────────────────
echo ""
echo "  平台真网探测（逐个平台实测，可能较慢）"
for u in "https://v.douyin.com/ntaaK4aH9pE/" \
         "https://www.bilibili.com/video/BV1GJ411x7h7"; do
  r=$(api_curl POST /api/parse "{\"text\":\"$u\",\"no_cache\":true}")
  if [ "$r" = "200" ]; then ok "解析可用：$u"; else bad "解析失败（HTTP $r）：$u"; fi
done

echo ""
echo "  ────────────────────────────────────────"
if [ "$FAIL" -eq 0 ]; then
  echo "${GRN}  ✅ 验证通过：$PASS 项${RST}"
  echo ""
  echo "  下一步（在小程序后台「开发-开发设置-服务器域名」配置）："
  echo "    request 合法域名：https://<你的域名>"
  echo "    uploadFile 域名：https://<你的域名>    ← PDF 工具上传需要"
  echo "    downloadFile 域名：https://<你的域名>  ← 图片/视频下载需要"
else
  echo "${RED}  ❌ ${FAIL} 项失败 / ${PASS} 项通过${RST}"
  echo "  排错：journalctl -u creatorbox -n 100 --no-pager"
fi
echo ""
