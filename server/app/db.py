"""CreatorBox · SQLite 数据层

为什么用 SQLite 而不是 MySQL/PG：
  · 2C2G 验证机，MVP 阶段写并发极低（配额扣减/素材库同步）
  · 零运维（无独立进程）、零网络开销（同机文件）
  · 蓝图要求「预留 tenant_id」—— 所有表第一列就是它，迁移多租户只改索引
  ⚠️ 升级路径：数据量 >10万行 或 写并发 >50/s 时迁 PostgreSQL，
     迁移时只需替换本文件的 DAO 实现，表结构不变。

为什么用 sqlite3 而不是 SQLAlchemy：
  · 项目轻依赖风格（fastapi/uvicorn/cache 均手写），引 ORM 得不偿失
  · 表少（4 张）查询简单，原生 SQL 更可控

线程模型：
  · FastAPI 事件循环内调用，DAO 操作毫秒级 → 全局锁串行即可，
    不引入 to_thread 复杂度（现有 cache/limiter 同样模式）

设计原则（来自 meta.py 的教训）：
  · 会员/配额判定**以服务端为准**，客户端本地计数只作乐观显示
  · 游客（未登录）也有配额 —— 用 device_id 当身份，防止无成本刷
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(os.getenv('CB_DB_PATH',
                         Path(__file__).resolve().parent.parent / 'data' / 'cb.db'))

# ── 配额常量（与 miniapp/utils/quota.js 保持一致 —— 改一处要同步另一处）──
SAVE_LIMIT_FREE = 2        # 免费：视频保存 每日 2 次
BATCH_LIMIT_FREE = 3       # 免费：批量解析单次 3 条
BATCH_LIMIT_MEMBER = 10    # 会员：单次 10 条（2C2G 串行解析的保护上限）
BATCH_MAX_HARD = 10        # 硬上限：超过直接 400，会员也不行

TENANT_DEFAULT = 'cbx'

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL UNIQUE,
  nickname TEXT NOT NULL DEFAULT '',
  avatar_url TEXT NOT NULL DEFAULT '',
  is_member INTEGER NOT NULL DEFAULT 0,
  member_expire_at INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quota_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL,
  day TEXT NOT NULL,
  save_count INTEGER NOT NULL DEFAULT 0,
  parse_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE(tenant_id, openid, day)
);
CREATE INDEX IF NOT EXISTS idx_quota_looked
  ON quota_daily(tenant_id, openid, day);

CREATE TABLE IF NOT EXISTS library_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL,
  item_type TEXT NOT NULL DEFAULT 'video',   -- video / image / copy
  title TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT '',
  author TEXT NOT NULL DEFAULT '',
  cover TEXT NOT NULL DEFAULT '',
  source_text TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lib_openid
  ON library_items(tenant_id, openid, deleted);

-- 订单表：支付未接（M1.5），先建结构 —— 接入时零迁移
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL,
  product_id TEXT NOT NULL DEFAULT 'member_month',
  amount_fen INTEGER NOT NULL DEFAULT 990,
  status TEXT NOT NULL DEFAULT 'created',    -- created/paid/refunded
  wx_transaction_id TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  paid_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_orders_openid
  ON orders(tenant_id, openid, status);

-- 健康度历史（M1.5 缺口#3）：每轮探针每平台一行，只留 HEALTH_RETENTION_DAYS 天
CREATE TABLE IF NOT EXISTS health_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  platform TEXT NOT NULL,
  status TEXT NOT NULL,                      -- ok / degraded / down
  ok INTEGER NOT NULL,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  consecutive_fail INTEGER NOT NULL DEFAULT 0,
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_hist
  ON health_history(tenant_id, platform, ts);

-- 健康告警（down 进入时建档，恢复时销案；degraded 不建档只进历史，防骚扰）
CREATE TABLE IF NOT EXISTS health_alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  platform TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT 'critical',    -- critical / warning
  message TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',       -- open / resolved
  first_ts INTEGER NOT NULL,
  last_ts INTEGER NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  resolved_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_health_alert
  ON health_alerts(tenant_id, platform, status);

-- 运行时配置（广告位开关等后台可调项；JSON 序列化存 value）
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  key TEXT NOT NULL,
  value TEXT NOT NULL DEFAULT '{{}}',
  updated_at INTEGER NOT NULL,
  UNIQUE(tenant_id, key)
);

-- 积分签到（每日一条，幂等防重复；积分余额不存表 = 由签到记录累加，
-- 防止余额与流水不一致；兑换直接改 users.member_until 并留 redeem 流水）
CREATE TABLE IF NOT EXISTS points_sign (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL,
  day TEXT NOT NULL,                          -- 'YYYY-MM-DD'（本地时区）
  points INTEGER NOT NULL DEFAULT 10,
  streak INTEGER NOT NULL DEFAULT 1,          -- 签到时连续天数
  created_at INTEGER NOT NULL,
  UNIQUE(tenant_id, openid, day)
);
CREATE INDEX IF NOT EXISTS idx_points_openid
  ON points_sign(tenant_id, openid, day);

-- 积分兑换流水（points 流出留痕）
CREATE TABLE IF NOT EXISTS points_redeem (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL,
  points INTEGER NOT NULL,                    -- 消耗的积分
  days INTEGER NOT NULL,                      -- 兑换的会员天数
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_points_redeem
  ON points_redeem(tenant_id, openid);

-- 会员卡密（线下收款 → 发码 → 小程序兑换；一次性核销，事务防并发双花）
CREATE TABLE IF NOT EXISTS redeem_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  code TEXT NOT NULL,                         -- CBXXXX-XXXX-XXXX
  days INTEGER NOT NULL,                      -- 面值天数（月卡 30）
  status TEXT NOT NULL DEFAULT 'unused',      -- unused / used / disabled
  used_by TEXT NOT NULL DEFAULT '',           -- 核销的 openid
  used_at INTEGER NOT NULL DEFAULT 0,
  batch TEXT NOT NULL DEFAULT '',             -- 批次备注（如「首发月卡」）
  created_at INTEGER NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE INDEX IF NOT EXISTS idx_redeem_codes_status
  ON redeem_codes(tenant_id, status);

-- 违禁词检测每日计数（免费 3 次/日，会员不限；与 quota_daily 分开，避免动配额表结构）
CREATE TABLE IF NOT EXISTS banned_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT '{t}',
  openid TEXT NOT NULL,
  day TEXT NOT NULL,                          -- 'YYYY-MM-DD'（本地时区）
  count INTEGER NOT NULL DEFAULT 0,
  UNIQUE(tenant_id, openid, day)
);
""".replace('{t}', TENANT_DEFAULT)


def init() -> None:
    """建库建表（幂等）。main.py 启动时调用一次。"""
    global _conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.executescript(SCHEMA)
        _migrate_account_hub()
        _migrate_banned_words()
        _conn.commit()


# ──────────────────── 账号中台迁移（v4 §2.4，2026-10-11）────────────────────
# 旧库平滑升级：users 补 user_id 列 + 存量行回填 + wechat_mini identity 播种。
# 新库直接建全。全部幂等，可重复执行。

def _migrate_banned_words() -> None:
    """违禁词库用户覆盖层（2026-10-11）：看板热管理。

    行存在 = 有用户决策：
    · enabled=1 + 非内置词 → 自定义新增词
    · enabled=1 + 内置词   → 显式启用（几乎不用，幂等兜底）
    · enabled=0            → 停用该词（内置/自定义都适用）
    """
    _conn.execute("""CREATE TABLE IF NOT EXISTS banned_words (
      word TEXT PRIMARY KEY,
      category TEXT NOT NULL,
      suggest TEXT NOT NULL DEFAULT '',
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at INTEGER NOT NULL
    )""")


# ──────────────────── 违禁词库覆盖层（2026-10-11）────────────────────

def banned_word_upsert(word: str, category: str,
                       suggest: str = '', enabled: int = 1) -> None:
    assert _conn, 'db.init() 未调用'
    with _lock:
        _conn.execute(
            """INSERT INTO banned_words(word, category, suggest, enabled, created_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(word) DO UPDATE SET
                 category=excluded.category, suggest=excluded.suggest,
                 enabled=excluded.enabled""",
            (word.strip(), category, suggest or '', int(bool(enabled)), _now()))
        _conn.commit()


def banned_word_delete(word: str) -> int:
    """删除自定义词的覆盖行（内置词恢复默认，自定义词彻底消失）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        n = _conn.execute('DELETE FROM banned_words WHERE word=?',
                          (word,)).rowcount
        _conn.commit()
    return n


def banned_custom_snapshot() -> Dict[str, Dict[str, Any]]:
    """全部覆盖行：{word: {category, suggest, enabled}}"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        rows = _conn.execute(
            'SELECT word, category, suggest, enabled FROM banned_words').fetchall()
    return {r['word']: {'category': r['category'], 'suggest': r['suggest'],
                        'enabled': bool(r['enabled'])} for r in rows}


def _migrate_account_hub() -> None:
    """账号中台迁移（v4 §2.4，2026-10-11）。

    旧库平滑升级：users 补 user_id 列 + 存量行回填 + wechat_mini identity 播种。
    新库直接建全。全部幂等，可重复执行。
    """
    cols = [r['name'] for r in _conn.execute('PRAGMA table_info(users)')]
    if 'user_id' not in cols:
        _conn.execute('ALTER TABLE users ADD COLUMN user_id TEXT')
    _conn.execute("""CREATE TABLE IF NOT EXISTS identities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL DEFAULT '{t}',
      user_id TEXT NOT NULL,
      provider TEXT NOT NULL,           -- wechat_mini / app_device / phone / email ...
      provider_uid TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      UNIQUE(provider, provider_uid)
    )""".replace('{t}', TENANT_DEFAULT))
    _conn.execute("""CREATE INDEX IF NOT EXISTS idx_ident_user
      ON identities(user_id)""")
    _conn.execute("""CREATE TABLE IF NOT EXISTS bridge_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL DEFAULT '{t}',
      code TEXT NOT NULL UNIQUE,        -- 6 位数字，5 分钟有效，一次性
      user_id TEXT NOT NULL,            -- 绑定目标（小程序用户）
      provider TEXT NOT NULL,           -- 待绑定的对端身份类型
      provider_uid TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL
    )""".replace('{t}', TENANT_DEFAULT))
    _conn.execute("""CREATE TABLE IF NOT EXISTS auth_tokens (
      token TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL DEFAULT '{t}',
      user_id TEXT NOT NULL,
      provider TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL       -- 90 天滚动续期
    )""".replace('{t}', TENANT_DEFAULT))
    _conn.execute("""CREATE INDEX IF NOT EXISTS idx_token_user
      ON auth_tokens(user_id)""")
    # 存量用户回填 user_id + 播种 wechat_mini 身份
    import secrets as _secrets
    rows = _conn.execute(
        "SELECT id, openid FROM users WHERE user_id IS NULL OR user_id=''").fetchall()
    for r in rows:
        uid = 'u_' + _secrets.token_hex(8)
        _conn.execute('UPDATE users SET user_id=? WHERE id=?', (uid, r['id']))
        _conn.execute(
            """INSERT OR IGNORE INTO identities(user_id, provider, provider_uid, created_at)
               VALUES(?,?,?,?)""", (uid, 'wechat_mini', r['openid'], _now()))


def _today() -> str:
    return date.today().isoformat()


def _now() -> int:
    return int(time.time())


# ──────────────────────────── 用户 ────────────────────────────

def upsert_user(openid: str, nickname: str = '',
                avatar_url: str = '') -> Dict[str, Any]:
    """登录即建档（幂等）。返回用户行。

    账号中台（2026-10-11）：新建用户同时生成跨端主键 user_id
    并播种 wechat_mini 身份；存量用户缺 user_id 时即时回填。
    """
    assert _conn, 'db.init() 未调用'
    import secrets as _secrets
    with _lock:
        _conn.execute(
            """INSERT INTO users(openid, nickname, avatar_url, created_at, last_seen_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(openid) DO UPDATE SET
                 last_seen_at=excluded.last_seen_at,
                 nickname=CASE WHEN excluded.nickname != ''
                               THEN excluded.nickname ELSE users.nickname END,
                 avatar_url=CASE WHEN excluded.avatar_url != ''
                                 THEN excluded.avatar_url ELSE users.avatar_url END""",
            (openid, nickname, avatar_url, _now(), _now()))
        row = _conn.execute('SELECT * FROM users WHERE openid=?', (openid,)).fetchone()
        if not row['user_id']:
            uid = 'u_' + _secrets.token_hex(8)
            _conn.execute('UPDATE users SET user_id=? WHERE id=?', (uid, row['id']))
            row = _conn.execute('SELECT * FROM users WHERE openid=?', (openid,)).fetchone()
        _conn.execute(
            """INSERT OR IGNORE INTO identities(user_id, provider, provider_uid, created_at)
               VALUES(?,?,?,?)""",
            (row['user_id'], 'wechat_mini', openid, _now()))
        _conn.commit()
    return dict(row) if row else {}


def get_member_state(openid: str) -> Dict[str, Any]:
    """会员判定：is_member 且未过期。客户端不得信任本地标记。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        row = _conn.execute(
            'SELECT is_member, member_expire_at FROM users WHERE openid=?',
            (openid,)).fetchone()
    if not row or not row['is_member']:
        return {'is_member': False, 'expire_at': 0}
    if row['member_expire_at'] and row['member_expire_at'] < _now():
        return {'is_member': False, 'expire_at': row['member_expire_at']}
    return {'is_member': True, 'expire_at': row['member_expire_at']}


def _member_add_days_locked(openid: str, days: int, now: int) -> None:
    """member_add_days 的核心（调用方必须已持有 _lock）。

    独立抽出：卡密核销与加天数必须同一事务，不能二次拿锁
    （threading.Lock 不可重入，嵌套即死锁）。
    """
    row = _conn.execute(
        'SELECT is_member, member_expire_at FROM users WHERE openid=?',
        (openid,)).fetchone()
    if not row:
        # 用户不存在（正常流程 ensureLogin 已建；此处兜底 upsert）
        _conn.execute(
            """INSERT INTO users (tenant_id, openid, is_member,
               member_expire_at, created_at, last_seen_at)
               VALUES (?,?,?,?,?,?)""",
            (TENANT_DEFAULT, openid, 1, now + days * 86400, now, now))
    else:
        base = max(int(row['member_expire_at'] or 0), now)
        _conn.execute(
            """UPDATE users SET is_member=1, member_expire_at=?
               WHERE openid=?""",
            (base + days * 86400, openid))


def member_add_days(openid: str, days: int) -> Dict[str, Any]:
    """积分兑换会员：从当前过期时间顺延（未开通则从现在起算）。

    自动置 is_member=1 并刷新过期时间。返回新会员状态。
    """
    assert _conn, 'db.init() 未调用'
    now = _now()
    with _lock:
        _member_add_days_locked(openid, days, now)
        _conn.commit()
    return get_member_state(openid)


# ──────────────────── 会员卡密（线下收款 → 发码兑换）────────────────────

_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # 去掉易混淆的 I/O/0/1


def codes_generate(days: int, count: int, batch: str = '') -> List[str]:
    """批量生成卡密（端点层负责 count 上限与鉴权）。返回生成的码列表。"""
    import secrets
    assert _conn, 'db.init() 未调用'
    days = max(1, min(int(days), 3650))
    count = max(1, min(int(count), 500))
    batch = str(batch or '')[:40]
    made: List[str] = []
    now = _now()
    with _lock:
        while len(made) < count:
            body = ''.join(secrets.choice(_CODE_ALPHABET) for _ in range(12))
            code = f'CB{body[:4]}-{body[4:8]}-{body[8:12]}'
            try:
                _conn.execute(
                    """INSERT INTO redeem_codes
                       (tenant_id, code, days, batch, created_at)
                       VALUES (?,?,?,?,?)""",
                    (TENANT_DEFAULT, code, days, batch, now))
                made.append(code)
            except Exception:
                continue                     # 撞码重摇（概率≈0）
        _conn.commit()
    return made


def codes_list(status: str = '', limit: int = 100) -> Dict[str, Any]:
    """卡密列表（新→旧）+ 全量状态统计。"""
    assert _conn, 'db.init() 未调用'
    limit = max(1, min(int(limit), 500))
    with _lock:
        stats = {'unused': 0, 'used': 0, 'disabled': 0}
        for r in _conn.execute(
                """SELECT status, COUNT(*) FROM redeem_codes
                   WHERE tenant_id=? GROUP BY status""",
                (TENANT_DEFAULT,)).fetchall():
            if r[0] in stats:
                stats[r[0]] = r[1]
        if status:
            rows = _conn.execute(
                """SELECT code, days, status, used_by, used_at, batch,
                          created_at
                   FROM redeem_codes WHERE tenant_id=? AND status=?
                   ORDER BY id DESC LIMIT ?""",
                (TENANT_DEFAULT, str(status)[:10], limit)).fetchall()
        else:
            rows = _conn.execute(
                """SELECT code, days, status, used_by, used_at, batch,
                          created_at
                   FROM redeem_codes WHERE tenant_id=?
                   ORDER BY id DESC LIMIT ?""",
                (TENANT_DEFAULT, limit)).fetchall()
    return {'stats': stats, 'items': [dict(r) for r in rows]}


def codes_disable(code: str) -> int:
    """作废未用卡密（已核销的不动）。返回作废条数。"""
    assert _conn, 'db.init() 未调用'
    code = (code or '').strip().upper().replace(' ', '')
    if not code:
        return 0
    with _lock:
        cur = _conn.execute(
            """UPDATE redeem_codes SET status='disabled'
               WHERE tenant_id=? AND code=? AND status='unused'""",
            (TENANT_DEFAULT, code))
        _conn.commit()
    return cur.rowcount


# ──────────────────── 违禁词检测配额 ────────────────────

BANNED_FREE_DAILY = 3            # 免费用户每日检测次数


def banned_consume(openid: str) -> Dict[str, Any]:
    """违禁词检测计数：会员不限，免费每日 3 次。

    先查后加（配额耗尽时不产生空计数）。返回：
        {ok, used, limit(0=不限), is_member}
    """
    assert _conn, 'db.init() 未调用'
    member = get_member_state(openid).get('is_member', False)
    day = _today()
    now_inc = not member
    with _lock:
        if now_inc:
            _conn.execute(
                """INSERT INTO banned_daily (tenant_id, openid, day, count)
                   VALUES (?,?,?,1)
                   ON CONFLICT(tenant_id, openid, day) DO UPDATE SET
                     count = count + 1""",
                (TENANT_DEFAULT, openid, day))
            _conn.commit()
        row = _conn.execute(
            """SELECT count FROM banned_daily
               WHERE tenant_id=? AND openid=? AND day=?""",
            (TENANT_DEFAULT, openid, day)).fetchone()
        used = int(row['count']) if row else 0
    if member:
        return {'ok': True, 'used': used, 'limit': 0, 'is_member': True}
    return {'ok': used <= BANNED_FREE_DAILY, 'used': used,
            'limit': BANNED_FREE_DAILY, 'is_member': False}


# ──────────────────── 用户管理（看板名单）────────────────────

def users_list(keyword: str = '', member_only: bool = False,
               limit: int = 50) -> Dict[str, Any]:
    """用户列表（最近活跃→早）+ 统计。keyword 子串匹配 openid/昵称。"""
    assert _conn, 'db.init() 未调用'
    limit = max(1, min(int(limit), 200))
    keyword = str(keyword or '').strip()[:60]
    today0 = int(_now()) - (_now() % 86400)          # UTC 零点近似，仅统计用
    with _lock:
        total = _conn.execute(
            'SELECT COUNT(*) FROM users WHERE tenant_id=?',
            (TENANT_DEFAULT,)).fetchone()[0]
        members = _conn.execute(
            """SELECT COUNT(*) FROM users
               WHERE tenant_id=? AND is_member=1
                 AND member_expire_at > ?""",
            (TENANT_DEFAULT, _now())).fetchone()[0]
        active_today = _conn.execute(
            """SELECT COUNT(*) FROM users
               WHERE tenant_id=? AND last_seen_at >= ?""",
            (TENANT_DEFAULT, today0)).fetchone()[0]
        cond, args = [], [TENANT_DEFAULT]
        if keyword:
            cond.append('(openid LIKE ? OR nickname LIKE ?)')
            args += [f'%{keyword}%', f'%{keyword}%']
        if member_only:
            cond.append('is_member=1 AND member_expire_at > ?')
            args.append(_now())
        where = (' AND ' + ' AND '.join(cond)) if cond else ''
        rows = _conn.execute(
            f"""SELECT openid, nickname, is_member, member_expire_at,
                       created_at, last_seen_at
                FROM users WHERE tenant_id=?{where}
                ORDER BY last_seen_at DESC LIMIT ?""",
            (*args, limit)).fetchall()
    return {'stats': {'total': total, 'members': members,
                      'active_today': active_today},
            'items': [dict(r) for r in rows]}


def code_redeem(openid: str, code: str) -> Dict[str, Any]:
    """卡密兑换会员（核销 + 加天数同一事务，防并发双花）。

    返回 {'ok': bool, 'error': str, 'days': int, 'member': {...}}
    """
    assert _conn, 'db.init() 未调用'
    code = (code or '').strip().upper().replace(' ', '')
    openid = str(openid or '').strip()
    if not openid:
        return {'ok': False, 'error': '缺少用户身份（请重新进入小程序）'}
    if not code:
        return {'ok': False, 'error': '请输入卡密'}
    now = _now()
    with _lock:
        row = _conn.execute(
            """SELECT id, days, status FROM redeem_codes
               WHERE tenant_id=? AND code=?""",
            (TENANT_DEFAULT, code)).fetchone()
        if not row:
            return {'ok': False, 'error': '卡密不存在，请核对输入'}
        if row['status'] == 'used':
            return {'ok': False, 'error': '卡密已被使用'}
        if row['status'] != 'unused':
            return {'ok': False, 'error': '卡密已作废'}
        # 核销（WHERE status='unused' 再挡一次并发双花）
        cur = _conn.execute(
            """UPDATE redeem_codes
               SET status='used', used_by=?, used_at=?
               WHERE id=? AND status='unused'""",
            (openid, now, row['id']))
        if cur.rowcount == 0:
            _conn.rollback()
            return {'ok': False, 'error': '卡密已被使用'}
        # 同一事务内加会员天数（core 无锁版，见函数头说明）
        _member_add_days_locked(openid, int(row['days']), now)
        _conn.commit()
    return {'ok': True, 'error': '', 'days': int(row['days']),
            'member': get_member_state(openid)}


# ──────────────────────────── 配额 ────────────────────────────

def get_quota(openid: str) -> Dict[str, Any]:
    """当日配额状态。免费判定在此处，客户端只读。"""
    member = get_member_state(openid).get('is_member', False)
    save_limit = 0 if member else SAVE_LIMIT_FREE   # 会员不限 → 0 表示无限
    with _lock:
        row = _conn.execute(
            """SELECT save_count FROM quota_daily
               WHERE tenant_id=? AND openid=? AND day=?""",
            (TENANT_DEFAULT, openid, _today())).fetchone()
    used = row['save_count'] if row else 0
    if member:
        left = -1                                    # -1 = 不限
    else:
        left = max(0, SAVE_LIMIT_FREE - used)
    return {
        'is_member': member,
        'day': _today(),
        'save_used': used,
        'save_limit': save_limit,
        'save_left': left,
        'batch_limit': BATCH_LIMIT_MEMBER if member else BATCH_LIMIT_FREE,
    }


def consume_save(openid: str, n: int = 1) -> Dict[str, Any]:
    """扣保存配额。会员不扣但仍记数（用于运营看板）。"""
    assert _conn, 'db.init() 未调用'
    member = get_member_state(openid).get('is_member', False)
    with _lock:
        _conn.execute(
            """INSERT INTO quota_daily(tenant_id, openid, day, save_count, parse_count)
               VALUES(?,?,?,?,0)
               ON CONFLICT(tenant_id, openid, day) DO UPDATE SET
                 save_count = save_count + excluded.save_count""",
            (TENANT_DEFAULT, openid, _today(), n))
        _conn.commit()
    q = get_quota(openid)
    q['consumed'] = n
    return q


# ──────────────────────────── 云端素材库 ────────────────────────

def library_add(openid: str, item: Dict[str, Any]) -> int:
    """同步一条到云端素材库。返回 id。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        cur = _conn.execute(
            """INSERT INTO library_items
               (tenant_id, openid, item_type, title, platform, author,
                cover, source_text, created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (TENANT_DEFAULT, openid,
             str(item.get('item_type') or 'video')[:12],
             str(item.get('title') or '')[:200],
             str(item.get('platform') or '')[:24],
             str(item.get('author') or '')[:80],
             str(item.get('cover') or '')[:500],
             str(item.get('source_text') or '')[:25000],   # 文案类（如 YouTube 字幕 20K）需要更大空间
             _now()))
        _conn.commit()
        return int(cur.lastrowid or 0)


def library_list(openid: str, limit: int = 100) -> List[Dict[str, Any]]:
    assert _conn, 'db.init() 未调用'
    with _lock:
        rows = _conn.execute(
            """SELECT id, item_type, title, platform, author, cover,
                      source_text, created_at
               FROM library_items
               WHERE tenant_id=? AND openid=? AND deleted=0
               ORDER BY id DESC LIMIT ?""",
            (TENANT_DEFAULT, openid, limit)).fetchall()
    return [dict(r) for r in rows]


def library_delete(openid: str, item_id: int) -> bool:
    """软删除（误删可恢复，审计友好）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        cur = _conn.execute(
            """UPDATE library_items SET deleted=1
               WHERE tenant_id=? AND openid=? AND id=?""",
            (TENANT_DEFAULT, openid, item_id))
        _conn.commit()
        return cur.rowcount > 0


# ──────────────────────────── 订单（预留）────────────────────────────

def order_create(openid: str, product_id: str = 'member_month',
                 amount_fen: int = 990) -> int:
    """M1.5 支付接入时使用。现在仅建结构，端点不暴露。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        cur = _conn.execute(
            """INSERT INTO orders(tenant_id, openid, product_id, amount_fen, created_at)
               VALUES(?,?,?,?,?)""",
            (TENANT_DEFAULT, openid, product_id, amount_fen, _now()))
        _conn.commit()
        return int(cur.lastrowid or 0)


def order_mark_paid(order_id: int, wx_transaction_id: str) -> bool:
    assert _conn, 'db.init() 未调用'
    with _lock:
        cur = _conn.execute(
            """UPDATE orders SET status='paid', wx_transaction_id=?, paid_at=?
               WHERE id=? AND status='created'""",
            (wx_transaction_id, _now(), order_id))
        _conn.commit()
        return cur.rowcount > 0


# ──────────────────── 健康度历史 + 告警（M1.5 缺口#3）────────────────────

def health_record(recs: List[Dict[str, Any]]) -> int:
    """每轮探针结果落库（每平台一行）。返回写入条数。

    recs 元素：{platform, status, ok, latency_ms?, error?, consecutive_fail?, ts}
    """
    assert _conn, 'db.init() 未调用'
    now = _now()
    rows = []
    for r in recs:
        plat = str(r.get('platform') or '')[:40]
        if not plat:
            continue
        rows.append((
            TENANT_DEFAULT, plat,
            str(r.get('status') or 'unknown')[:12],
            1 if r.get('ok') else 0,
            int(r.get('latency_ms') or 0),
            str(r.get('error') or '')[:120],
            int(r.get('consecutive_fail') or 0),
            int(r.get('ts') or now),
        ))
    with _lock:
        _conn.executemany(
            """INSERT INTO health_history
               (tenant_id, platform, status, ok, latency_ms, error,
                consecutive_fail, ts)
               VALUES(?,?,?,?,?,?,?,?)""", rows)
        _conn.commit()
    return len(rows)


def health_alert_upsert(platform: str, level: str, message: str,
                        action: str = '') -> bool:
    """down 告警建档/续档。返回 True=新建（需要通知），False=续档（已通知过）。

    ⭐ 同一平台持续 down 只通知一次：count/last_ts 递增，message 刷新为最新。
    """
    assert _conn, 'db.init() 未调用'
    now = _now()
    with _lock:
        row = _conn.execute(
            """SELECT id, count FROM health_alerts
               WHERE tenant_id=? AND platform=? AND status='open'""",
            (TENANT_DEFAULT, platform)).fetchone()
        if row:
            _conn.execute(
                """UPDATE health_alerts
                   SET count=count+1, last_ts=?, message=?, level=?
                   WHERE id=?""",
                (now, str(message or '')[:160], level, row['id']))
            _conn.commit()
            return False
        _conn.execute(
            """INSERT INTO health_alerts
               (tenant_id, platform, level, message, action, status,
                first_ts, last_ts, count)
               VALUES(?,?,?,?,?,'open',?,?,1)""",
            (TENANT_DEFAULT, str(platform)[:40], level,
             str(message or '')[:160], str(action or '')[:120], now, now))
        _conn.commit()
        return True


def health_alert_resolve(platform: str) -> bool:
    """恢复销案。返回 True=确实有 open 告警被关掉（值得发恢复通知）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        cur = _conn.execute(
            """UPDATE health_alerts
               SET status='resolved', resolved_ts=?
               WHERE tenant_id=? AND platform=? AND status='open'""",
            (_now(), TENANT_DEFAULT, str(platform)[:40]))
        _conn.commit()
        return cur.rowcount > 0


def health_alerts_open(limit: int = 50) -> List[Dict[str, Any]]:
    """当前 open 告警（按 last_ts 倒序）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        rows = _conn.execute(
            """SELECT platform, level, message, action, first_ts, last_ts, count
               FROM health_alerts
               WHERE tenant_id=? AND status='open'
               ORDER BY last_ts DESC LIMIT ?""",
            (TENANT_DEFAULT, int(limit))).fetchall()
    return [dict(r) for r in rows]


def health_history_list(platform: str = '', limit: int = 200
                        ) -> List[Dict[str, Any]]:
    """历史明细。platform 为空返回全部平台混排（时间倒序）。"""
    assert _conn, 'db.init() 未调用'
    limit = max(1, min(int(limit), 1000))
    with _lock:
        if platform:
            rows = _conn.execute(
                """SELECT platform, status, ok, latency_ms, error,
                          consecutive_fail, ts
                   FROM health_history
                   WHERE tenant_id=? AND platform=? ORDER BY ts DESC LIMIT ?""",
                (TENANT_DEFAULT, str(platform)[:40], limit)).fetchall()
        else:
            rows = _conn.execute(
                """SELECT platform, status, ok, latency_ms, error,
                          consecutive_fail, ts
                   FROM health_history
                   WHERE tenant_id=? ORDER BY ts DESC LIMIT ?""",
                (TENANT_DEFAULT, limit)).fetchall()
    return [dict(r) for r in rows]


def health_cleanup(retention_days: int = 7) -> int:
    """清理过期历史 + 已销案告警。返回删除行数。"""
    assert _conn, 'db.init() 未调用'
    cutoff = _now() - int(retention_days) * 86400
    with _lock:
        c1 = _conn.execute(
            'DELETE FROM health_history WHERE tenant_id=? AND ts < ?',
            (TENANT_DEFAULT, cutoff)).rowcount
        c2 = _conn.execute(
            """DELETE FROM health_alerts
               WHERE tenant_id=? AND status='resolved' AND resolved_ts < ?""",
            (TENANT_DEFAULT, cutoff)).rowcount
        _conn.commit()
    return c1 + c2


# ──────────────────── 积分中心（P2）────────────────────

def points_sign_record(openid: str, day: str, points: int, streak: int) -> bool:
    """签到落库（UNIQUE(openid,day) 幂等）。返回是否新插入。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        try:
            _conn.execute(
                """INSERT INTO points_sign
                   (tenant_id, openid, day, points, streak, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (TENANT_DEFAULT, openid, day, points, streak, _now()))
            _conn.commit()
            return True
        except Exception:                    # UNIQUE 冲突 = 今日已签
            return False


def points_summary(openid: str) -> Dict[str, Any]:
    """积分余额（流水累加）+ 最近 7 天签到日期 + 当前连签天数。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        earned = _conn.execute(
            """SELECT COALESCE(SUM(points),0) FROM points_sign
               WHERE tenant_id=? AND openid=?""",
            (TENANT_DEFAULT, openid)).fetchone()[0]
        spent = _conn.execute(
            """SELECT COALESCE(SUM(points),0) FROM points_redeem
               WHERE tenant_id=? AND openid=?""",
            (TENANT_DEFAULT, openid)).fetchone()[0]
        rows = _conn.execute(
            """SELECT day, streak FROM points_sign
               WHERE tenant_id=? AND openid=?
               ORDER BY day DESC LIMIT 7""",
            (TENANT_DEFAULT, openid)).fetchall()
    days = [r[0] for r in rows]
    streak = rows[0][1] if rows else 0
    return {'balance': int(earned) - int(spent), 'days': days, 'streak': streak}


def points_redeem_record(openid: str, points: int, days: int) -> None:
    """兑换流水（调用方负责余额校验与 member_until 写入）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        _conn.execute(
            """INSERT INTO points_redeem (tenant_id, openid, points, days, created_at)
               VALUES (?,?,?,?,?)""",
            (TENANT_DEFAULT, openid, points, days, _now()))
        _conn.commit()


# ──────────────────── 运行时配置（settings）────────────────────

def settings_set(key: str, value: Dict[str, Any]) -> None:
    """写入/覆盖一个配置项（value 整体 JSON 序列化）。"""
    import json as _json
    assert _conn, 'db.init() 未调用'
    with _lock:
        _conn.execute(
            """INSERT INTO settings(tenant_id, key, value, updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(tenant_id, key) DO UPDATE SET
                 value=excluded.value, updated_at=excluded.updated_at""",
            (TENANT_DEFAULT, str(key)[:60],
             _json.dumps(value, ensure_ascii=False), _now()))
        _conn.commit()


def settings_get(key: str) -> Optional[Dict[str, Any]]:
    """读配置项。不存在返回 None。"""
    import json as _json
    assert _conn, 'db.init() 未调用'
    with _lock:
        row = _conn.execute(
            'SELECT value FROM settings WHERE tenant_id=? AND key=?',
            (TENANT_DEFAULT, str(key)[:60])).fetchone()
    if not row:
        return None
    try:
        return _json.loads(row['value'])
    except Exception:
        return None


# ──────────────────────────── 自检 ────────────────────────────

if __name__ == '__main__':
    # 独立自检：python app/db.py
    # ⚠️ 必须用临时库 —— 真实库里有用户数据/配额记录，断言会互相干扰
    import tempfile
    _tmpdir = tempfile.mkdtemp(prefix='cb_dbcheck_')
    DB_PATH = Path(_tmpdir) / 'check.db'
    if _conn is not None:
        _conn.close()
        _conn = None
    init()
    # 独立自检：python app/db.py
    init()
    uid = 'test_openid_selfcheck'

    upsert_user(uid, '测试用户', 'https://a.jpg')
    upsert_user(uid, '测试用户2', '')          # 幂等：空值不覆盖

    st = get_member_state(uid)
    assert st['is_member'] is False, st

    q0 = get_quota(uid)
    assert q0['save_limit'] == SAVE_LIMIT_FREE and q0['save_left'] == SAVE_LIMIT_FREE, q0

    consume_save(uid)
    consume_save(uid)
    q1 = get_quota(uid)
    assert q1['save_used'] == 2 and q1['save_left'] == 0, q1

    # 会员：不扣额度，batch 上限提高
    with _lock:
        _conn.execute(
            'UPDATE users SET is_member=1, member_expire_at=? WHERE openid=?',
            (_now() + 86400 * 30, uid))
        _conn.commit()
    q2 = get_quota(uid)
    assert q2['is_member'] is True and q2['save_left'] == -1, q2
    assert q2['batch_limit'] == BATCH_LIMIT_MEMBER, q2

    # 过期会员降级
    with _lock:
        _conn.execute(
            'UPDATE users SET member_expire_at=? WHERE openid=?',
            (_now() - 10, uid))
        _conn.commit()
    q3 = get_quota(uid)
    assert q3['is_member'] is False, q3

    # 素材库
    iid = library_add(uid, {'item_type': 'copy', 'title': '测试文案',
                            'platform': 'douyin', 'source_text': 'abc'})
    items = library_list(uid)
    assert len(items) == 1 and items[0]['title'] == '测试文案', items
    assert library_delete(uid, iid)
    assert library_list(uid) == []

    # 订单（预留结构验证）
    oid = order_create(uid)
    assert order_mark_paid(oid, 'wx_tx_001')

    # 空值/异常输入防御
    library_add(uid, {'title': None, 'cover': 'x' * 9999})   # 截断不抛
    print('✅ db 自检通过（用户/配额/会员过期/素材库/订单/防御）')


# ──────────────────── 账号中台核心（v4 §2.4，2026-10-11）────────────────────
# 跨端主键 user_id + 多身份绑定 + 桥接码换 token。
# 兼容铁律：小程序 openid 全链路照旧；user_id 是伞形主键，不动存量表结构。

import secrets as _acc_secrets
import string as _acc_string

_BRIDGE_TTL = 300          # 桥接码 5 分钟
_BRIDGE_MAX_TRIES = 5      # 防爆破
_TOKEN_TTL = 90 * 86400    # token 90 天


def _gen_bridge_code() -> str:
    return ''.join(_acc_secrets.choice(_acc_string.digits) for _ in range(6))


def get_user_by_user_id(user_id: str) -> Dict[str, Any]:
    """按跨端主键取用户行。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        row = _conn.execute('SELECT * FROM users WHERE user_id=?', (user_id,)).fetchone()
    return dict(row) if row else {}


def resolve_user(provider: str, provider_uid: str) -> Dict[str, Any]:
    """按身份找用户（找不到返回空 dict，不创建）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        row = _conn.execute(
            """SELECT u.* FROM identities i JOIN users u ON u.user_id=i.user_id
               WHERE i.provider=? AND i.provider_uid=?""",
            (provider, provider_uid)).fetchone()
    return dict(row) if row else {}


def bind_identity(user_id: str, provider: str, provider_uid: str) -> Dict[str, Any]:
    """给已有用户绑定新身份（幂等：同身份重复绑直接成功）。

    冲突语义：该 (provider, provider_uid) 已绑在别的 user 上 → ok=False。
    """
    assert _conn, 'db.init() 未调用'
    with _lock:
        ex = _conn.execute(
            'SELECT user_id FROM identities WHERE provider=? AND provider_uid=?',
            (provider, provider_uid)).fetchone()
        if ex:
            if ex['user_id'] == user_id:
                return {'ok': True, 'already': True}
            return {'ok': False, 'reason': 'identity_taken'}
        _conn.execute(
            """INSERT INTO identities(user_id, provider, provider_uid, created_at)
               VALUES(?,?,?,?)""", (user_id, provider, provider_uid, _now()))
        _conn.commit()
    return {'ok': True}


def bridge_create(provider: str, provider_uid: str,
                  by_user_id: str = '') -> Dict[str, Any]:
    """跨端绑定第一步：App/PC 用本地身份换一次性桥接码（用户去小程序确认）。

    绑定目标（user_id）留空——真正要绑到谁，由小程序端 confirm 时决定。

    但要记下【是谁在出码】(by_user_id)：
      - App 端通常已登录（有 token），把它写进 user_id 列作为「出码发起方」标记，
        这样用户中途注销时能精确清掉自己名下所有未确认的码；
      - 未登录时（首次安装）留空，行为与从前一致。
      ⚠️ 注意：bridge_confirm 以 code 查行时会覆写 user_id 为真正绑定目标，
        因此该列在「已确认」阶段语义是绑定账号，在「未确认」阶段是出码发起方 ——
        注销清理只依赖 provider_uid 与该列非空，不依赖具体值语义。
    """
    assert _conn, 'db.init() 未调用'
    if provider == 'wechat_mini':
        return {'ok': False, 'reason': 'invalid_provider'}
    with _lock:
        # 清理该身份的旧码（一个身份同时只有一个活跃码）
        _conn.execute(
            'DELETE FROM bridge_codes WHERE provider=? AND provider_uid=?',
            (provider, provider_uid))
        code = _gen_bridge_code()
        now = _now()
        _conn.execute(
            """INSERT INTO bridge_codes(code, user_id, provider, provider_uid,
                                        created_at, expires_at)
               VALUES(?,?,?,?,?,?)""",
            (code, by_user_id, provider, provider_uid, now, now + _BRIDGE_TTL))
        _conn.commit()
    return {'ok': True, 'code': code, 'expires_in': _BRIDGE_TTL}


def identities_of(user_id: str) -> list:
    """某用户绑定的全部身份（/api/auth/me 用）。"""
    assert _conn, 'db.init() 未调用'
    with _lock:
        rows = _conn.execute(
            'SELECT provider, provider_uid, created_at FROM identities '
            'WHERE user_id=? ORDER BY created_at', (user_id,)).fetchall()
    return [dict(r) for r in rows]


def bridge_confirm(openid: str, code: str) -> Dict[str, Any]:
    """跨端绑定第二步：小程序用户输入桥接码，把对端身份绑到自己账号。"""
    assert _conn, 'db.init() 未调用'
    code = (code or '').strip()
    with _lock:
        row = _conn.execute(
            'SELECT * FROM bridge_codes WHERE code=?', (code,)).fetchone()
        if not row:
            return {'ok': False, 'reason': 'code_not_found'}
        if row['expires_at'] < _now():
            _conn.execute('DELETE FROM bridge_codes WHERE code=?', (code,))
            _conn.commit()
            return {'ok': False, 'reason': 'code_expired'}
        if row['attempts'] >= _BRIDGE_MAX_TRIES:
            _conn.execute('DELETE FROM bridge_codes WHERE code=?', (code,))
            _conn.commit()
            return {'ok': False, 'reason': 'code_locked'}
        if not openid:
            _conn.execute(
                'UPDATE bridge_codes SET attempts=attempts+1 WHERE code=?', (code,))
            _conn.commit()
            return {'ok': False, 'reason': 'need_openid'}
        u = _conn.execute('SELECT user_id FROM users WHERE openid=?',
                          (openid,)).fetchone()
        if not u or not u['user_id']:
            return {'ok': False, 'reason': 'user_not_found'}
        # 身份冲突预检（已在别的账号上 → 明确拒绝，不让用户绑错）
        ex = _conn.execute(
            'SELECT user_id FROM identities WHERE provider=? AND provider_uid=?',
            (row['provider'], row['provider_uid'])).fetchone()
        if ex and ex['user_id'] != u['user_id']:
            return {'ok': False, 'reason': 'identity_taken'}
        _conn.execute(
            """INSERT OR IGNORE INTO identities(user_id, provider, provider_uid, created_at)
               VALUES(?,?,?,?)""",
            (u['user_id'], row['provider'], row['provider_uid'], _now()))
        _conn.execute('DELETE FROM bridge_codes WHERE code=?', (code,))
        _conn.commit()
    return {'ok': True, 'user_id': u['user_id']}


def bridge_poll(provider: str, provider_uid: str) -> Dict[str, Any]:
    """跨端绑定第三步：App/PC 轮询——身份已绑定则发 token。"""
    assert _conn, 'db.init() 未调用'
    u = resolve_user(provider, provider_uid)
    if not u:
        return {'ok': False, 'reason': 'not_bound'}
    token = _acc_secrets.token_urlsafe(24)
    with _lock:
        _conn.execute(
            """INSERT INTO auth_tokens(token, user_id, provider, created_at, expires_at)
               VALUES(?,?,?,?,?)""",
            (token, u['user_id'], provider, _now(), _now() + _TOKEN_TTL))
        _conn.commit()
    ms = get_member_state(u['openid'])
    return {'ok': True, 'token': token, 'user_id': u['user_id'],
            'expires_in': _TOKEN_TTL, 'member': ms}


def resolve_token(token: str) -> Dict[str, Any]:
    """token → 用户行（过期即焚）。"""
    assert _conn, 'db.init() 未调用'
    if not token:
        return {}
    with _lock:
        row = _conn.execute('SELECT * FROM auth_tokens WHERE token=?',
                            (token,)).fetchone()
        if not row:
            return {}
        if row['expires_at'] < _now():
            _conn.execute('DELETE FROM auth_tokens WHERE token=?', (token,))
            _conn.commit()
            return {}
        u = _conn.execute('SELECT * FROM users WHERE user_id=?',
                          (row['user_id'],)).fetchone()
    return dict(u) if u else {}


# ── 账号注销：用户删除权的数据面（隐私保护指引 §四）────────────────────────

def count_by_openid(table: str, openid: str) -> int:
    """注销预览用：统计某用户在该表里的数据条数。

    table 名来自代码常量而非用户输入，外部调用务必只传白名单内的表名。
    """
    assert _conn, 'db.init() 未调用'
    if table not in {t for t, _ in _USER_SCOPED_TABLES}:
        return 0
    with _lock:
        try:
            return _conn.execute(
                f'SELECT COUNT(*) FROM {table} WHERE openid=?',
                (openid,)).fetchone()[0]
        except sqlite3.OperationalError:
            return 0


def count_by_user_id(table: str, user_id: str) -> int:
    """注销预览用：按 user_id 统计（identities / auth_tokens）。"""
    assert _conn, 'db.init() 未调用'
    if table not in {'identities', 'auth_tokens'}:
        return 0
    with _lock:
        try:
            return _conn.execute(
                f'SELECT COUNT(*) FROM {table} WHERE user_id=?',
                (user_id,)).fetchone()[0]
        except sqlite3.OperationalError:
            return 0


# 只清「用户自己的数据」。以下表是运营资产，【绝不能】跟着用户一起删：
#   banned_words / redeem_codes / settings / health_* / orders（平台订单需留档）
_USER_SCOPED_TABLES = (
    ('library_items', 'openid'),
    ('quota_daily', 'openid'),
    ('banned_daily', 'openid'),
    ('points_sign', 'openid'),
    ('points_redeem', 'openid'),
    ('identities', 'user_id'),
    ('auth_tokens', 'user_id'),
)
# bridge_codes 不在此表：它要按 user_id 列单独删（该列存的是「出码发起方」，
# 不是 provider_uid 关联），见 purge_user 内注释。


def user_id_by_openid(openid: str) -> str:
    """openid → user_id（小程序侧注销用；取不到返回空串）。"""
    assert _conn, 'db.init() 未调用'
    if not openid:
        return ''
    with _lock:
        r = _conn.execute('SELECT user_id FROM users WHERE openid=?',
                          (openid,)).fetchone()
    return (r['user_id'] if r else '') or ''


def purge_user(user_id: str) -> Dict[str, Any]:
    """删除用户的全部个人数据（注销账号）。

    分两批删是刻意的：
      1) 先按 user_id 拿到 openid 与所有身份 uid —— 身份表里还有别的身份，
         拿不到就无法清 quota/library 这些按 openid 索引的表。
      2) 再逐表删。

    ⚠️ 不可逆。调用方（main.py）必须先二次确认用户意图。
    """
    assert _conn, 'db.init() 未调用'
    deleted: Dict[str, int] = {}
    with _lock:
        u = _conn.execute('SELECT * FROM users WHERE user_id=?',
                          (user_id,)).fetchone()
        if not u:
            return {'ok': False, 'reason': 'user_not_found', 'deleted': {}}
        openid = u['openid']
        # ⚠️ 收集范围必须【先收集齐再删】，因为删除 identities/auth_tokens 后
        #    就再也查不出这些 uid 了 —— 顺序反了会漏删桥接码。
        #
        # 孤儿码场景：用户在 App 端出了码、还没在小程序确认（此时还没写 identities）
        # 就注销了账号。码还留在 bridge_codes，若不清掉，别人拿这码 confirm 就能绑走，
        # 而它本属于一个已注销的人 —— 这是安全漏洞。
        # 关联路径：bridge_codes.provider_uid ⇄ auth_tokens.provider_uid ⇄ user_id
        uids: List[str] = []
        for tbl, col in (('identities', 'user_id'), ('auth_tokens', 'user_id')):
            try:
                uids += [r['provider_uid'] for r in _conn.execute(
                    f'SELECT provider_uid FROM {tbl} WHERE {col}=?',
                    (user_id,)).fetchall()]
            except sqlite3.OperationalError:
                continue
        # 未确认码：bridge_codes.user_id 记的是「出码发起方」，
        # 匹配即视为该用户名下 —— 不再依赖 provider_uid 关联。
        try:
            n_codes = _conn.execute(
                'DELETE FROM bridge_codes WHERE user_id=?', (user_id,)).rowcount
            deleted['bridge_codes'] = n_codes
        except sqlite3.OperationalError:
            pass
        # 去重且保持顺序（identities 与 auth_tokens 之间有重叠）
        uids = list(dict.fromkeys([x for x in uids if x]))
        for tbl, key in _USER_SCOPED_TABLES:
            try:
                if key == 'openid':
                    cur = _conn.execute(f'DELETE FROM {tbl} WHERE openid=?',
                                        (openid,))
                elif key == 'user_id':
                    cur = _conn.execute(f'DELETE FROM {tbl} WHERE user_id=?',
                                        (user_id,))
                else:   # provider_uid：对该用户的每个身份各清一次
                    cur = _conn.execute(
                        f'DELETE FROM {tbl} WHERE provider_uid IN ({",".join(["?"] * len(uids))})',
                        tuple(uids)) if uids else None
                    if cur is None:
                        continue
                deleted[tbl] = cur.rowcount
            except sqlite3.OperationalError:
                # 表不存在（旧库）不该让注销整体失败
                continue
        deleted['users'] = _conn.execute(
            'DELETE FROM users WHERE user_id=?', (user_id,)).rowcount
        _conn.commit()
    return {'ok': True, 'deleted': deleted}
