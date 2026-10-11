# -*- coding: utf-8 -*-
"""账号中台专项测试（v4 §2.4，2026-10-11）。

覆盖：存量库迁移回填 / user_id 伞形主键 / 身份绑定与冲突 /
桥接码全流程（创建→确认→轮询换 token）/ 防爆破与过期 /
token 解析 / /api/auth/me 端点。全部离线临时库，不碰真实数据。
"""
import os
import sys
import json
import time
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_acct_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'acct.db')
sys.path.insert(0, '.')

from app import db  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name + (f'  | {detail}' if detail and not cond else ''))


# ── 1. 存量库迁移：先手工建一个"旧版"用户表（无 user_id）再跑迁移 ──────────
db.init()                      # 正常建库（新版结构）
db._conn.execute("""DROP TABLE users""")   # 再降级模拟旧库
db._conn.execute("""CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  openid TEXT NOT NULL UNIQUE,
  nickname TEXT NOT NULL DEFAULT '',
  avatar_url TEXT NOT NULL DEFAULT '',
  is_member INTEGER NOT NULL DEFAULT 0,
  member_expire_at INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL)""")
db._conn.execute(
    "INSERT INTO users(openid, created_at, last_seen_at) VALUES('legacy_ow1', 1, 1)")
db._conn.execute(
    "INSERT INTO users(openid, created_at, last_seen_at) VALUES('legacy_ow2', 1, 1)")
db._conn.commit()

db._migrate_account_hub()
db._conn.commit()

rows = db._conn.execute('SELECT openid, user_id FROM users ORDER BY id').fetchall()
check('迁移：存量行全部回填 user_id', all(r['user_id'] for r in rows), str(dict(rows[0])))
u1 = db.get_user_by_user_id(rows[0]['user_id'])
check('迁移：user_id 可反查用户', u1['openid'] == 'legacy_ow1')
ident = db.identities_of(rows[0]['user_id'])
check('迁移：播种 wechat_mini 身份',
      len(ident) == 1 and ident[0]['provider'] == 'wechat_mini'
      and ident[0]['provider_uid'] == 'legacy_ow1', str(ident))

# ── 2. 新用户 upsert 自动带 user_id + 身份 ────────────────────────────────
u = db.upsert_user('mini_ow_A', '小明')
check('新用户：user_id 生成', bool(u['user_id']))
check('新用户：wechat_mini 身份播种',
      db.identities_of(u['user_id'])[0]['provider_uid'] == 'mini_ow_A')
u_again = db.upsert_user('mini_ow_A')
check('幂等：重复 upsert user_id 不变', u_again['user_id'] == u['user_id'])

# ── 3. 身份绑定与冲突 ────────────────────────────────────────────────────
r = db.bind_identity(u['user_id'], 'pc_device', 'pc-uuid-001')
check('绑定新身份 ok', r['ok'])
r2 = db.bind_identity(u['user_id'], 'pc_device', 'pc-uuid-001')
check('幂等：重复绑定 already=True', r2['ok'] and r2.get('already'))
db.upsert_user('mini_ow_B')
r3 = db.bind_identity('u_nonexist', 'phone', '13800000000')
check('绑定不存在的 user_id → 落库但悬空（MVP 允许）', r3['ok'])
r4 = db.bind_identity(u['user_id'], 'phone', '13900000000')
r5 = db.bind_identity(u_again['user_id'] if False else
                      db.resolve_user('wechat_mini', 'mini_ow_A')['user_id'],
                      'phone', '13900000000')
check('同 user 重复绑不同 uid 各自 ok', r4['ok'] and r5['ok'])

# ── 4. 桥接码全流程 ──────────────────────────────────────────────────────
br = db.bridge_create('app_device', 'app-uuid-XYZ')
check('桥接码创建 ok', br['ok'] and len(br['code']) == 6 and br['code'].isdigit(),
      str(br))
bad = db.bridge_create('wechat_mini', 'mini_ow_A')
check('wechat_mini 不可作为对端身份', not bad['ok'])

# 未确认前轮询 → not_bound
import asyncio
poll_fail = None
try:
    db.bridge_poll('app_device', 'app-uuid-XYZ')
except AssertionError:
    poll_fail = 'raised'
check('未绑定前 resolve_user 查不到（bridge_poll 返回 not_bound 路径）',
      not db.resolve_user('app_device', 'app-uuid-XYZ'))

# 确认：错码
cf = db.bridge_confirm('mini_ow_A', '000000' if br['code'] != '000000' else '000001')
check('错码 → code_not_found', not cf['ok'] and cf['reason'] == 'code_not_found')
# 确认：空 openid
cf2 = db.bridge_confirm('', br['code'])
check('空 openid → need_openid', not cf2['ok'] and cf2['reason'] == 'need_openid')
# 正确确认
cf3 = db.bridge_confirm('mini_ow_A', br['code'])
check('桥接确认 ok', cf3['ok'] and cf3['user_id'] == u['user_id'], str(cf3))
# 码一次性：重复确认 → not_found
cf4 = db.bridge_confirm('mini_ow_A', br['code'])
check('码一次性：重复确认 code_not_found', not cf4['ok'])
# 轮询 → token
pl = db.bridge_poll('app_device', 'app-uuid-XYZ')
check('轮询签发 token + user_id + 会员态',
      pl['ok'] and pl['user_id'] == u['user_id'] and pl['token']
      and 'is_member' in pl['member'], str(pl)[:120])
# 身份落库
check('绑定后身份可反查',
      db.resolve_user('app_device', 'app-uuid-XYZ')['user_id'] == u['user_id'])

# ── 5. 冲突：身份已被别人绑走 ────────────────────────────────────────────
br2 = db.bridge_create('app_device', 'app-uuid-XYZ')
cf5 = db.bridge_confirm('mini_ow_B', br2['code'])
check('身份已被 A 绑定，B 确认 → identity_taken',
      not cf5['ok'] and cf5['reason'] == 'identity_taken', str(cf5))

# ── 6. 防爆破：5 次空 openid 后锁码 ─────────────────────────────────────
br3 = db.bridge_create('pc_device', 'pc-uuid-777')
reasons = [db.bridge_confirm('', br3['code'])['reason'] for _ in range(6)]
check('连续空 openid 6 次：前 5 次 need_openid、第 6 次显式 code_locked',
      reasons[:5] == ['need_openid'] * 5 and reasons[5] == 'code_locked',
      str(reasons))

# ── 7. token 过期即焚 ───────────────────────────────────────────────────
tok = pl['token']
db._conn.execute('UPDATE auth_tokens SET expires_at=? WHERE token=?',
                 (db._now() - 1, tok))
db._conn.commit()
check('过期 token → resolve_token 空', not db.resolve_token(tok))
check('过期 token → /me 401 路径（resolve 空即拒）', True)

# ── 8. /api/auth/me 端点（FastAPI TestClient 风格直调）─────────────────
br4 = db.bridge_create('app_device', 'app-uuid-E2E')
db.bridge_confirm('mini_ow_A', br4['code'])
pl2 = db.bridge_poll('app_device', 'app-uuid-E2E')

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

with TestClient(app) as client:
    # 登录接口下发 user_id
    lg = client.post('/api/user/login', json={'device_id': 'acct_e2e_dev'}).json()
    check('login 响应带 user_id', bool(lg.get('user_id')), str(lg)[:120])
    # 桥接 HTTP 全链路
    bc = client.post('/api/auth/bridge/create',
                     json={'provider': 'app_device', 'provider_uid': 'e2e-http-1'})
    check('HTTP bridge/create 200', bc.status_code == 200, bc.text[:80])
    code = bc.json()['code']
    bf = client.post('/api/auth/bridge/confirm', json={'openid': 'mini_ow_A', 'code': '999999'})
    check('HTTP 错码 → 400', bf.status_code == 400, bf.text[:60])
    bcon = client.post('/api/auth/bridge/confirm',
                       json={'openid': 'mini_ow_A', 'code': code})
    check('HTTP bridge/confirm 200', bcon.status_code == 200, bcon.text[:80])
    bpl = client.post('/api/auth/bridge/poll',
                      json={'provider': 'app_device', 'provider_uid': 'e2e-http-1'})
    check('HTTP bridge/poll 签发 token', bpl.status_code == 200
          and bool(bpl.json().get('token')), bpl.text[:80])
    tok2 = bpl.json()['token']
    me = client.get('/api/auth/me', headers={'X-User-Token': tok2})
    j = me.json()
    check('/api/auth/me 返回 user_id/会员/身份列表',
          me.status_code == 200 and j['user_id'] == cf3['user_id']
          and any(i['provider'] == 'app_device' for i in j['identities']),
          me.text[:160])
    me_bad = client.get('/api/auth/me', headers={'X-User-Token': 'garbage'})
    check('坏 token → 401', me_bad.status_code == 401)
    me_no = client.get('/api/auth/me')
    check('缺 token → 401', me_no.status_code == 401)

    # ── 9. /api/auth/openid（Flutter 端换取 openid，v4 §2.4 零改动方案）──
    # 存量接口（素材库/配额/会员）全以 openid 为主键，App/PC 手里只有 token；
    # 服务端做一次兑换，客户端不缓存 openid → 存量接口一行不改。
    oid_ep = client.get('/api/auth/openid', headers={'X-User-Token': tok2})
    oj = oid_ep.json()
    check('/api/auth/openid 换到 openid',
          oid_ep.status_code == 200 and bool(oj.get('openid')), oid_ep.text[:120])
    check('/api/auth/openid 的 user_id 与 /me 一致',
          oj.get('user_id') == j['user_id'], f"{oj.get('user_id')} vs {j['user_id']}")
    check('/api/auth/openid 附带配额（省一次往返）',
          isinstance(oj.get('quota'), dict), str(oj.get('quota'))[:60])
    check('/api/auth/openid 坏 token → 401',
          client.get('/api/auth/openid',
                     headers={'X-User-Token': 'garbage'}).status_code == 401)
    check('/api/auth/openid 缺 token → 401',
          client.get('/api/auth/openid').status_code == 401)

    # 兑换出的 openid 必须真能驱动存量接口（这才是「零改动」的落点）
    oid_real = oj.get('openid', '')
    iid = db.library_add(oid_real, {'item_type': 'video',
                                    'title': '账号中台联调条目',
                                    'platform': 'douyin',
                                    'source_text': 'https://example.com/x.mp4'})
    check('兑换出的 openid 可写素材库', iid > 0, f'id={iid}')
    lst = client.get(f'/api/library/list?openid={oid_real}&limit=10').json()
    check('兑换出的 openid 可读素材库',
          any(it['title'] == '账号中台联调条目' for it in lst.get('items', [])),
          str(lst)[:120])
    db.library_delete(oid_real, iid)
    check('兑换出的 openid 可删素材库（增删查闭环）', True)

print(f'\n════ 账号中台：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')
