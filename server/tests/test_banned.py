"""违禁词检测全链路测试（2026-10-09）

临时库：引擎命中/类目分组/标红分段/重叠去重/免费配额/会员全库/替换建议
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='cb_banned_test_')
os.environ['CB_DB_PATH'] = os.path.join(_TMP, 'test.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db                          # noqa: E402
from app import banned                      # noqa: E402

db.init()
PASS = []
def check(name, ok, detail=''):
    PASS.append(ok)
    print(('  ✅ ' if ok else '  ❌ ') + name + (f' ← {detail}' if not ok and detail else ''))

OID = 'guest_test_banned_001'

print('1. 引擎：基础命中与分类')
sample = '全网最低价！祖传秘方，包治近视。加微信领福利，扣1免费送，稳赚不赔月入十万！'
r = banned.detect(sample, full=True)
check('命中总数 9', r['total'] == 9, str(r['total']))
check('风险级别 high', r['risk_level'] == 'high')
cats = {g['category'] for g in r['groups']}
check('覆盖 5 个类目', cats == {'fake', 'induce', 'money', 'adlaw', 'import'},
      str(cats))
check('medical 未命中不出现组', 'medical' not in cats)

print('2. 标红分段：hit 片段拼接后等于原文')
segs = banned.build_segments(sample, r['marks'])
check('分段还原原文', ''.join(s['t'] for s in segs) == sample)
check('命中片段数 = marks 数', sum(1 for s in segs if s['hit']) == len(r['marks']))
check('hit 片段含祖传', any(s['hit'] and s['t'] == '祖传' for s in segs))

print('3. 跨类目重叠去重：长词优先')
r2 = banned.detect('这是全网最低价的稳赚不赔好项目', full=True)
words = [m['word'] for m in r2['marks']]
check('最低价/稳赚不赔 整词命中（非碎片重叠）',
      '全网最低' in words and '稳赚不赔' in words, str(words))
starts = [m['start'] for m in r2['marks']]
check('marks 位置严格递增', starts == sorted(starts) and
      all(r2['marks'][i]['end'] <= r2['marks'][i + 1]['start']
          for i in range(len(r2['marks']) - 1)), str(r2['marks']))

print('4. 免费视野：full=False 只报基础类目，locked 提示升级')
r3 = banned.detect(sample, full=False)
check('免费模式命中最少有 adlaw/induce',
      {'adlaw', 'induce'} <= {g['category'] for g in r3['groups']})
check('money/fake 被锁', {'money', 'fake'} <= set(r3['locked']))
check('locked 含全部付费类目', set(r3['locked']) == {'medical', 'money', 'import', 'fake'})

print('5. 免费配额：每日 3 次，第 4 次拒绝；会员无限')
states = [db.banned_consume(OID) for _ in range(3)]
check('前 3 次全部放行', all(s['ok'] for s in states), str(states))
check('计数 1→3', [s['used'] for s in states] == [1, 2, 3])
s4 = db.banned_consume(OID)
check('第 4 次拒绝', not s4['ok'] and s4['used'] == 4, str(s4))
s5 = db.banned_consume(OID)
check('第 5 次仍拒绝（计数不再膨胀影响判断）', not s5['ok'])

MEMBER = 'guest_test_banned_vip'
db.member_add_days(MEMBER, 30)
svip = db.banned_consume(MEMBER)
check('会员 ok=True 且 limit=0（不限）', svip['ok'] and svip['limit'] == 0, str(svip))

print('6. 替换建议：高频词带建议，冷门词不强造')
check('第一 → 领先', banned.SUGGEST.get('第一') == '领先')
check('祖传 → 配方', banned.SUGGEST.get('祖传') == '配方')
empty = banned.detect('', full=True)
check('空文本 clean', empty['total'] == 0 and empty['risk_level'] == 'clean')
clean = banned.detect('今天天气不错，适合出去走走拍点素材', full=True)
check('正常文案零命中', clean['total'] == 0, str(clean['groups']))

print(f'\n{sum(PASS)} PASS / {len(PASS) - sum(PASS)} FAIL')
assert all(PASS), '存在失败断言'
print('✅ 违禁词检测测试全部通过')
