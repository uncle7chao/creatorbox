"""服务配置"""
import os

# ---------- 浏览器实例池 ----------
# ---------- 解析引擎 ----------
# 【一级】纯 HTTP 解析器（抖音/ B站），无需浏览器，实测 0.6~1.5s
ENABLE_BROWSER_FALLBACK = os.getenv('CB_BROWSER_FALLBACK', '0') == '1'
# ↑默认关闭。抖音/B站纯 HTTP 双通道已跑通；平台改版时开启动浏览器排查。
# 开启后每实例占 500MB-1GB 内存，仅建议排查时使用。

INSTANCE_COUNT = int(os.getenv('CB_INSTANCES', '1'))
HEADLESS = os.getenv('CB_HEADLESS', '1') == '1'
BROWSER_WARMUP = os.getenv('CB_WARMUP', '1') == '1'
BROWSER_CHANNEL = os.getenv('CB_BROWSER_CHANNEL', 'chrome')  # 复用本机 Chrome

# 需请求签名的平台（小红书 x-s / 快手 __clientid）
# 实测 2026-10-04：两者游客态均被拒（小红书 500、快手 result:11）
# 保持关闭，签名逆向完成后再开
ENABLE_SIGNED = os.getenv('CB_ENABLE_SIGNED', '0') == '1'

# B站解析器
# ⚠️ 实测两个限制：
#  1. 匿名会话只给 480P（accept_quality 声明支持 1080P 但拿不到）→ 上限受限
#  2. CDN 域名带随机性（xy120x220x70x61xy.mcdn.bilivideo.cn）→ 必然超 20 个
#     微信白名单上限，必须走服务端中转
ENABLE_BILIBILI = os.getenv('CB_ENABLE_BILIBILI', '1') == '1'

# ---------- 国际平台（2026-10-11，TikTok/X/YT/FB）----------
# 需要服务器能直连境外平台（香港服务器 ✅）。提审构建可置 0 隐藏国际入口。
INTL_ENABLED = os.getenv('CB_INTL_ENABLED', '1') == '1'
# TikTok dtk 自持通道（guest 免 Cookie；离线 golden 验证通过，真网验证待 HK 服务器）
TIKTOK_DTK = os.getenv('CB_TIKTOK_DTK', '1') == '1'
BILI_LOGIN_COOKIE = os.getenv('CB_BILI_COOKIE', '')   # 登录 Cookie（解 1080P 限制）

# ---------- 缓存 ----------
REDIS_URL = os.getenv('CB_REDIS_URL', '')
CACHE_TTL = int(os.getenv('CB_CACHE_TTL', '600'))          # 10 分钟

# ---------- 限流（内存态，单进程） ----------
RATE_LIMIT_PER_MIN = int(os.getenv('CB_RATE_LIMIT', '30'))
RATE_LIMIT_WINDOW = 60

# ---------- 降级阈值（平台改版预警） ----------
DEGRADE_FAIL_RATIO = 0.4      # 失败率超 40% 告警
DEGRADE_MIN_SAMPLES = 5

# ---------- 平台健康度探针（M1 Gate 条件） ----------
# 定时打已知可解析的样本，发现平台改版/风控。
# ⚠️ 探针不只是「打一遍」，还会断言能力（如 AcFun 必须有 5 档清晰度），
#    否则平台退化成只给一档也发现不了。
ENABLE_HEALTH_PROBE = os.getenv('CB_ENABLE_HEALTH', '1') == '1'
HEALTH_INTERVAL = int(os.getenv('CB_HEALTH_INTERVAL', '600'))  # 10 分钟
# 健康历史/告警持久化（M1.5 缺口#3）：历史落 SQLite，down 告警支持 webhook 通知
HEALTH_RETENTION_DAYS = int(os.getenv('CB_HEALTH_RETENTION_DAYS', '7'))
ALERT_WEBHOOK_URL = os.getenv('CB_ALERT_WEBHOOK', '')   # 空=只 console+落库

# ---------- 服务 ----------
HOST = os.getenv('CB_HOST', '0.0.0.0')
PORT = int(os.getenv('CB_PORT', '8000'))
API_KEY = os.getenv('CB_API_KEY', '')

# 解析类端点是否强制要求 X-Api-Key（仅自建代理/内网互调用）
# ⚠️ 默认 0：解析类走的是 C 端体系（openid + 配额 + 限流），
#    与管理密钥无关。设成 1 会让小程序/App 全部 401 —— 它们拿不到管理密钥。
API_KEY_REQUIRED = os.getenv('CB_API_KEY_REQUIRED', '0') in ('1', 'true', 'True')

# ---------- 提审收敛（v4 §3.3）----------
# full   = 全量平台可见（默认，日常开发与线上正常版）
# review = 提审收敛版，只保留 REVIEW_VISIBLE 白名单里的平台入口
# 注意：收敛只隐藏「入口」，不关闭解析能力 —— 粘贴链接仍可解析。
REVIEW_MODE = os.getenv('CB_REVIEW_MODE', 'full')

# ---------- 配额（与 app/db.py、miniapp/utils/quota.js 三处同步） ----------
SAVE_LIMIT_FREE = int(os.getenv('CB_SAVE_LIMIT_FREE', '2'))    # 视频保存/日
BATCH_LIMIT_FREE = int(os.getenv('CB_BATCH_FREE', '3'))        # 批量/次（免费）
BATCH_LIMIT_MEMBER = int(os.getenv('CB_BATCH_MEMBER', '10'))   # 批量/次（会员）
BATCH_MAX_HARD = 10                                            # 硬上限
DEFAULT_QUALITY = os.getenv('CB_QUALITY', '720p')   # 免费默认 720P（v2 方案）

# ---------- 微信登录（M1.5 支付前先走游客态） ----------
WX_APPID = os.getenv('CB_WX_APPID', '')
WX_SECRET = os.getenv('CB_WX_SECRET', '')

# ---------- 小红书登录态（2026-10-07 实测：App 分享的 xsec_token 对
#            无 cookie 访问会被登录墙拦截；配 Cookie 后全量通行） ----------
XHS_COOKIE = os.getenv('CB_XHS_COOKIE', '')

# ---------- 微博登录态（2026-10-07：热搜榜只给话题词，需 Cookie 走
#            m.weibo.cn 话题接口换出「带视频的微博」才能进解析闭环） ----------
WEIBO_COOKIE = os.getenv('CB_WEIBO_COOKIE', '')
