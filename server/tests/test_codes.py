"""会员卡密全链路测试（2026-10-08）

临时库：生成/列表统计/兑换核销/防双花/续期顺延/作废/输入归一化
"""
import os
import sys
import time
import tempfile

os.environ['CB_DB_PATH'] = os.path.join(tempfile.gettempdir(),
                                        f'cb_test_codes_{int(time.time())}.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db                            # noqa: E402

PASS = []
def check(name, ok, detail=''):
    PASS.append(ok)
    print(('  ✅ ' if ok else '  ❌ ') + name + (f' ← {detail}' if not ok and detail else ''))

db.init()
OID = 'guest_test_codes_001'
OID2 = 'guest_test_codes_002'

print('1. 生成：月卡 30 天 × 3')
codes = db.codes_generate(30, 3, batch='测试月卡')
check('生成 3 张', len(codes) == 3, str(codes))
check('码格式 CBXXXX-XXXX-XXXX', all(
    len(c) == 16 and c.startswith('CB') and c[6] == '-' and c[11] == '-'
    for c in codes), str(codes))

print('2. 列表：统计 unused=3')
lst = db.codes_list()
check('unused=3', lst['stats']['unused'] == 3, str(lst['stats']))
check('列表含批次备注', all(it['batch'] == '测试月卡' for it in lst['items']))

print('3. 兑换：第一张核销 + 会员 30 天')
r = db.code_redeem(OID, codes[0])
check('兑换成功', r['ok'], str(r))
check('面值 30 天', r.get('days') == 30)
check('is_member=True', r.get('member', {}).get('is_member') is True)
expire1 = r.get('member', {}).get('expire_at', 0)
check('到期时间在 29~31 天后', 29 * 86400 < expire1 - int(time.time()) < 31 * 86400,
      f'offset={expire1 - int(time.time())}s')

print('4. 防双花：同码再兑 / 他人再兑')
r2 = db.code_redeem(OID, codes[0])
check('同码再兑被拒', not r2['ok'] and '已被使用' in r2['error'], str(r2))
r2b = db.code_redeem(OID2, codes[0])
check('他人再用被拒', not r2b['ok'])

print('5. 续期顺延：第二张在第一张到期时间上 +30 天')
r3 = db.code_redeem(OID, codes[1])
check('第二张成功', r3['ok'], str(r3))
expire2 = r3['member']['expire_at']
check('顺延 ≈ +30 天', abs((expire2 - expire1) - 30 * 86400) < 60,
      f'diff={expire2 - expire1}s')

print('6. 输入归一化：小写 + 空格 + 复制带尾换行')
r4 = db.code_redeem(OID, ' ' + codes[1].lower() + '\n')  # 已用码，但验证归一化路径
check('归一化后命中已用判定（而非"不存在"）',
      not r4['ok'] and '已被使用' in r4['error'], str(r4))

print('7. 作废：第三张 disabled 后不可兑')
n = db.codes_disable(codes[2])
check('作废 1 张', n == 1)
r5 = db.code_redeem(OID, codes[2])
check('作废后兑换被拒', not r5['ok'] and '作废' in r5['error'], str(r5))

print('8. 错码与统计')
r6 = db.code_redeem(OID, 'CBZZZZ-ZZZZ-ZZZZ')
check('错码报不存在', not r6['ok'] and '不存在' in r6['error'])
lst = db.codes_list()
check('统计 unused=0 used=2 disabled=1',
      lst['stats'] == {'unused': 0, 'used': 2, 'disabled': 1},
      str(lst['stats']))
check('member_add_days 公共入口仍可用（重构未破坏）',
      db.member_add_days(OID, 1)['is_member'] is True)

print(f'\n{sum(PASS)} PASS / {len(PASS) - sum(PASS)} FAIL')
assert all(PASS), '存在失败断言'
print('✅ 卡密系统测试全部通过')
