"""积分中心全链路测试（P2 · 2026-10-08）

临时库：签到幂等/连签判定/余额累加/兑换扣减/会员顺延
"""
import os
import sys
import time
import tempfile

os.environ['CB_DB_PATH'] = os.path.join(tempfile.gettempdir(),
                                        f'cb_test_points_{int(time.time())}.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, main                      # noqa: E402

PASS = []
def check(name, ok, detail=''):
    PASS.append(ok)
    print(('  ✅ ' if ok else '  ❌ ') + name + (f' ← {detail}' if not ok and detail else ''))

db.init()
OID = 'guest_test_points_001'

print('1. 查询：新用户余额 0')
s = db.points_summary(OID)
check('新用户余额 0', s['balance'] == 0 and s['streak'] == 0)

print('2. 今日签到 +10')
today = time.strftime('%Y-%m-%d')
ok = db.points_sign_record(OID, today, 10, 1)
check('签到落库', ok)
s = db.points_summary(OID)
check('余额 10', s['balance'] == 10, str(s))

print('3. 同一天重复签到（幂等）')
ok2 = db.points_sign_record(OID, today, 10, 1)
check('UNIQUE 拦截返回 False', ok2 is False)
check('余额仍 10', db.points_summary(OID)['balance'] == 10)

print('4. 连签判定：补昨天记录 → streak 应为 2')
yesterday = time.strftime('%Y-%m-%d', time.localtime(time.time() - 86400))
# 直接改昨天那条的 day 字段模拟（干净造数：删重插）
with db._lock:
    db._conn.execute("UPDATE points_sign SET day=? WHERE openid=? AND day=?",
                     (yesterday, OID, today))
    db._conn.commit()
db.points_sign_record(OID, today, 10, 2)          # 今天再签（模拟跨天）
s = db.points_summary(OID)
check('连签 streak=2', s['streak'] == 2, str(s))
check('余额 20（两次各 10）', s['balance'] == 20, str(s))

print('5. 兑换：余额 20 < 100 → 端点 400')
import asyncio
async def redeem():
    try:
        await main.api_points_redeem(type('B', (), {'openid': OID})())
        return None
    except Exception as e:
        return getattr(e, 'status_code', None) or 'EXC'
code = asyncio.run(redeem())
check('余额不足被拒（400）', code == 400, str(code))

print('6. 攒够 100 → 兑换 1 天会员')
# 造 8 条额外签到（每天 +10，streak 不影响余额）
with db._lock:
    for i in range(2, 10):
        d = time.strftime('%Y-%m-%d', time.localtime(time.time() - i * 86400))
        db._conn.execute(
            """INSERT OR IGNORE INTO points_sign
               (tenant_id, openid, day, points, streak, created_at)
               VALUES ('cbx', ?, ?, 10, 1, 0)""", (OID, d))
    db._conn.commit()
s = db.points_summary(OID)
check('余额 >= 100', s['balance'] >= 100, str(s['balance']))

before = db.get_member_state(OID)
r = asyncio.run(main.api_points_redeem(type('B', (), {'openid': OID})()))
days = r['redeemed_days']
check('兑换成交', r['ok'] and days >= 1, f"days={days}")
member = db.get_member_state(OID)
check('会员已生效（is_member=True）', member['is_member'] is True)
check('会员时间顺延', member['expire_at'] > before['expire_at'],
      f"{before['expire_at']} → {member['expire_at']}")
check('兑换后余额 = 旧余额 - days*100',
      db.points_summary(OID)['balance'] == s['balance'] - days * 100)

print('7. main 端点：sign 幂等返回 signed=False')
async def sign():
    return await main.api_points_sign(type('B', (), {'openid': OID})())
r2 = asyncio.run(sign())
check('今日已签 → signed=False + message', r2['signed'] is False and bool(r2.get('message')))

print(f"\n{'─' * 46}")
ok = sum(PASS)
print(f'{ok} PASS / {len(PASS) - ok} FAIL')
if ok != len(PASS):
    sys.exit(1)
print('✅ 积分中心全链路通过')
