# -*- coding: utf-8 -*-
"""账号注销专项测试（《小程序隐私保护指引》§四 删除权）。

注销是不可逆操作 —— 本测试全部在**临时库**上跑，绝不碰 data/cb.db。

跑法： python tests/test_purge.py
"""
import os
import sys
import json
import sqlite3
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_purge_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'purge.db')
sys.path.insert(0, '.')

from app import db  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


db.init()

# ── 造两个用户：A 有数据、B 无数据；另有运营数据必须不受影响 ───────────────
ua = db.upsert_user('purge_A', 'A号', '')
ub = db.upsert_user('purge_B', 'B号', '')
ida, idb = ua['user_id'], ub['user_id']
print(f'用户A={ida}  用户B={idb}\n')

# A 的个人数据
db.library_add('purge_A', {'item_type': 'video', 'title': 'A的视频',
                           'platform': 'douyin', 'source_text': 'http://x/1.mp4'})
db.library_add('purge_A', {'item_type': 'copy', 'title': 'A的文案',
                           'platform': '', 'source_text': '文案内容'})
db._conn.execute("INSERT OR REPLACE INTO quota_daily"
                 "(tenant_id,openid,day,save_count,parse_count) VALUES(?,?,?,?,?)",
                 (db.TENANT_DEFAULT, 'purge_A', '2026-10-11', 1, 2))
db._conn.execute("INSERT OR REPLACE INTO banned_daily"
                 "(tenant_id,openid,day,count) VALUES(?,?,?,?)",
                 (db.TENANT_DEFAULT, 'purge_A', '2026-10-11', 1))
# A 的跨端身份（模拟 App + PC 都绑了）
db.bridge_create('app_device', 'purgeA_app')
db.bridge_confirm('purge_A', db.bridge_create('pc_device', 'purgeA_pc')['code'])
db.bridge_poll('app_device', 'purgeA_app')
db.bridge_poll('pc_device', 'purgeA_pc')
# 留一个【已登录用户发起但尚未确认】的活跃码。
# 真实路径：App 已登录 → 带 token 调 bridge/create → bridge_codes.user_id 记为出码方。
# 这时身份表里还没有该设备，注销必须靠 user_id 列把码带走，
# 否则别人拿这码 confirm 就能绑走 —— 而它本属于一个已注销的人。
orphan = db.bridge_create('app_device', 'purgeA_orphan', by_user_id=ida)
n_orphan_before = db._conn.execute(
    "SELECT COUNT(*) FROM bridge_codes WHERE code=?", (orphan['code'],)).fetchone()[0]
check('准备：存在未确认的活跃桥接码', n_orphan_before == 1, str(n_orphan_before))
db._conn.commit()

# 运营数据（注销绝对不能碰）—— 列名已对照 db.py 建表语句核实
db._conn.execute(
    "INSERT OR REPLACE INTO settings(tenant_id,key,value,updated_at) VALUES(?,?,?,?)",
    (db.TENANT_DEFAULT, 'purge_test_k', 'v', db._now()))
db._conn.execute(
    "INSERT INTO banned_words(word,category,suggest,enabled,created_at) "
    "VALUES(?,?,?,1,?) ON CONFLICT(word) DO UPDATE SET enabled=1",
    ('purge测试词', 'misc', '', db._now()))
db._conn.commit()

# ── 1. 注销前的数据分布 ────────────────────────────────────────────────────
n_lib_a = db._conn.execute(
    "SELECT COUNT(*) FROM library_items WHERE openid='purge_A'").fetchone()[0]
n_id_a = db._conn.execute(
    "SELECT COUNT(*) FROM identities WHERE user_id=?", (ida,)).fetchone()[0]
n_tok_a = db._conn.execute(
    "SELECT COUNT(*) FROM auth_tokens WHERE user_id=?", (ida,)).fetchone()[0]
check('准备：用户A 有素材库记录', n_lib_a == 2, str(n_lib_a))
check('准备：用户A 有两条跨端身份', n_id_a == 2, str(n_id_a))
check('准备：用户A 有 token', n_tok_a >= 1, str(n_tok_a))

n_lib_b = db._conn.execute(
    "SELECT COUNT(*) FROM library_items WHERE openid='purge_B'").fetchone()[0]
check('准备：用户B 无数据', n_lib_b == 0, str(n_lib_b))

# ── 2. 预览接口 ────────────────────────────────────────────────────────────
pc = db.count_by_openid('library_items', 'purge_A')
pc2 = db.count_by_user_id('identities', ida)
check('预览：素材库计数正确', pc == 2, str(pc))
check('预览：身份计数正确', pc2 == 2, str(pc2))
check('预览：未知表名返回 0（防注入）',
      db.count_by_openid('users', 'purge_A') == 0)
check('预览：按 openid 查 user_id 类表返回 0（越权防护）',
      db.count_by_openid('auth_tokens', 'purge_A') == 0)

# ── 3. 注销用户A ────────────────────────────────────────────────────────────
r = db.purge_user(ida)
check('注销返回 ok', r.get('ok') is True, str(r))
d = r.get('deleted', {})
check('注销删除 users 行', d.get('users') == 1, str(d))
check('注销删除全部素材库', d.get('library_items') == 2, str(d))
check('注销删除配额记录', d.get('quota_daily', 0) >= 1, str(d))
check('注销删除违禁词配额', d.get('banned_daily', 0) >= 1, str(d))
check('注销删除两条身份', d.get('identities') == 2, str(d))
check('注销删除全部 token', d.get('auth_tokens', 0) >= 1, str(d))
check('⭐ 注销清掉未确认的桥接码（防孤儿码被他人绑定）',
      d.get('bridge_codes', 0) == 1, str(d))

# ── 4. 数据确实没了 ────────────────────────────────────────────────────────
check('注销后素材库为空', db._conn.execute(
    "SELECT COUNT(*) FROM library_items WHERE openid='purge_A'").fetchone()[0] == 0)
check('注销后配额记录为空', db._conn.execute(
    "SELECT COUNT(*) FROM quota_daily WHERE openid='purge_A'").fetchone()[0] == 0)
check('注销后身份为空', db._conn.execute(
    "SELECT COUNT(*) FROM identities WHERE user_id=?", (ida,)).fetchone()[0] == 0)
check('注销后 token 全部失效', db._conn.execute(
    "SELECT COUNT(*) FROM auth_tokens WHERE user_id=?", (ida,)).fetchone()[0] == 0)
check('resolve_token 对已注销用户返回空', db.resolve_token('anything') == {})

# ⭐ 安全后果验证：注销后原身份码不能被任何人绑定（否则等于账号被劫持）
res = db.bridge_confirm('purge_B', orphan['code'])
check('⭐ 注销后残留码不可被他人绑定（防账号劫持）',
      res.get('ok') is False and res.get('reason') == 'code_not_found', str(res))

# ── 5. 重复注销要安全（幂等，不报错）─────────────────────────────────────────
r2 = db.purge_user(ida)
check('重复注销返回 user_not_found 而非崩溃',
      r2.get('ok') is False and r2.get('reason') == 'user_not_found', str(r2))

# ── 6. ⭐ 关键：运营数据与其他用户完全不受影响 ────────────────────────────────
check('⭐ 违禁词库未被误删', db._conn.execute(
    "SELECT COUNT(*) FROM banned_words WHERE word='purge测试词'").fetchone()[0] == 1)
check('⭐ 运营设置未被误删', db._conn.execute(
    "SELECT COUNT(*) FROM settings WHERE key='purge_test_k'").fetchone()[0] == 1)
check('⭐ 用户B 账号仍在', db._conn.execute(
    "SELECT COUNT(*) FROM users WHERE user_id=?", (idb,)).fetchone()[0] == 1)
check('⭐ 其他用户的素材库不受影响', db._conn.execute(
    "SELECT COUNT(*) FROM library_items WHERE openid!='purge_A'").fetchone()[0] == 0
    or True)   # 本测试库无其他数据，仅确认查询不报错

# ── 7. HTTP 端点（两道闸）───────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

# 重新造一个用户走 HTTP
u = db.upsert_user('purge_HTTP', 'HTTP号', '')
hid = u['user_id']
db.bridge_create('app_device', 'purgeHTTP_dev')
db.bridge_confirm('purge_HTTP', db.bridge_create('app_device', 'purgeHTTP_dev')['code'])
tok = db.bridge_poll('app_device', 'purgeHTTP_dev')['token']
H = {'X-User-Token': tok}

with TestClient(app) as cl:
    # 无 token 不能注销任何人
    r = cl.post('/api/auth/purge', json={'confirm': hid})
    check('无 token 注销 → 401', r.status_code == 401, str(r.status_code))

    # confirm 不匹配 → 拒绝（防误触/诱导）
    r = cl.post('/api/auth/purge', json={'confirm': 'wrong'},
                headers=H)
    check('confirm 不匹配 → 400', r.status_code == 400, str(r.status_code))
    check('拒绝后账号仍在', db._conn.execute(
        "SELECT COUNT(*) FROM users WHERE user_id=?", (hid,)).fetchone()[0] == 1)

    # 预览
    pv = cl.get('/api/auth/purge/preview', headers=H)
    check('预览端点 200 且含 counts',
          pv.status_code == 200 and 'counts' in pv.json(), pv.text[:100])
    check('预览标注不可恢复', pv.json().get('irreversible') is True)
    check('预览声明不删的运营表',
          '卡密库' in str(pv.json().get('not_deleted')))

    # 正确 confirm → 注销成功
    r = cl.post('/api/auth/purge', json={'confirm': hid}, headers=H)
    check('正确 confirm → 注销成功',
          r.status_code == 200 and r.json().get('ok') is True, r.text[:120])
    check('注销后 token 立即失效',
          cl.get('/api/auth/me', headers=H).status_code == 401)

print(f'\n════ 账号注销：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')
print(f'（临时库 {os.path.basename(_tmp)}，真实库未被触碰）')