# -*- coding: utf-8 -*-
"""违禁词库热更新专项测试（v4 §3.2「违禁词库看板热更新」）。

功能本身已实现（refresh_overrides + /api/admin/banned/words/*），
但既有 test_banned.py 对热更新 **0 覆盖** —— 没有测试的「即时生效」等于没有承诺。

本测试验证三件事：
  1. 看板新增自定义词 → 立即参与检测（不重启、不发版）
  2. 停用内置词 → 立即不再命中
  3. 恢复内置词 → 回到默认行为

全部在临时库上跑，不碰 data/cb.db。
跑法： python tests/test_banned_hotupdate.py
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_bh_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'bh.db')
sys.path.insert(0, '.')

from app import db, banned  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


db.init()
banned.refresh_overrides(db.banned_custom_snapshot())

# ── 基线：确认用词确实在内置库、且当前会命中 ────────────────────────────────
probe = '这是一款祖传秘方，保证根治'
base = banned.detect(probe, full=True)
check('基线：内置词「祖传」能命中', '祖传' in str(base['marks']), str(base['marks'])[:120])
check('基线：内置词「秘方」能命中', '秘方' in str(base['marks']))
cat_builtin = banned.builtin_category('祖传')
check('基线：builtin_category 能识别内置词', bool(cat_builtin), repr(cat_builtin))


def reapply():
    """模拟看板改词后主流程做的事（main.py 里就是这一句）。"""
    banned.refresh_overrides(db.banned_custom_snapshot())


# ── 1. 新增自定义词 → 立即命中 ──────────────────────────────────────────────
CUSTOM = '沙雕测试词'
check('改词前：自定义词不命中',
      CUSTOM not in str(banned.detect(f'这是{CUSTOM}内容', full=True)['marks']))

db.banned_word_upsert(CUSTOM, 'adlaw', '换成正常说法', 1)
reapply()
r1 = banned.detect(f'这是{CUSTOM}内容', full=True)
check('新增后：自定义词立即命中（无需重启）',
      CUSTOM in str(r1['marks']), str(r1['marks'])[:120])
check('新增后：total 计数包含新词', r1['total'] >= 1, str(r1['total']))
# 建议也要生效 —— 这是看板热更新的价值之一
grp = next((g for g in r1['groups'] if g['category'] == 'adlaw'), None)
sug_ok = bool(grp) and any(w.get('suggest') == '换成正常说法'
                           for w in grp.get('words', []))
check('新增后：替换建议一并生效', sug_ok, str(grp)[:150] if grp else '无 adlaw 组')

# ── 2. 停用内置词 → 立即不命中 ──────────────────────────────────────────────
db.banned_word_upsert('祖传', cat_builtin or 'medical', '', 0)
reapply()
r2 = banned.detect('这是一款祖传秘方，保证根治', full=True)
check('停用后：内置词「祖传」立即不再命中',
      '祖传' not in str(r2['marks']), str(r2['marks'])[:120])
check('停用后：同句其他词仍命中（没把整句都干掉）',
      '秘方' in str(r2['marks']), str(r2['marks'])[:120])

# ── 3. 恢复内置词 → 回到默认 ───────────────────────────────────────────────
db.banned_word_delete('祖传')
reapply()
r3 = banned.detect('这是一款祖传秘方，保证根治', full=True)
check('恢复后：内置词重新命中', '祖传' in str(r3['marks']), str(r3['marks'])[:120])

# ── 4. 删除自定义词 → 立即消失 ─────────────────────────────────────────────
db.banned_word_delete(CUSTOM)
reapply()
r4 = banned.detect(f'这是{CUSTOM}内容', full=True)
check('删除后：自定义词立即不再命中',
      CUSTOM not in str(r4['marks']), str(r4['marks'])[:120])
check('删除后：回到干净状态', r4['total'] == 0, str(r4['total']))

# ── 5. 边界：空词 / 特殊字符不能把正则搞崩 ────────────────────────────────
for bad_word in ('', '   ', '(', '[a-z]+', '.*', '\\'):
    try:
        db.banned_word_upsert(bad_word, 'adlaw', '', 1)
        reapply()
        banned.detect('普通内容没有任何问题', full=True)
        check(f'特殊词 {bad_word!r} 不导致崩溃', True)
    except Exception as e:
        check(f'特殊词 {bad_word!r} 不导致崩溃', False, str(e)[:80])
    finally:
        db.banned_word_delete(bad_word)
        reapply()

# ── 6. 边界：热更新后线程可见（并发检测不会读到半更新状态）────────────────
import threading  # noqa: E402
errors = []


def worker():
    try:
        for _ in range(20):
            banned.detect('祖传 秘方 最好 第一', full=True)
    except Exception as e:      # noqa: BLE001
        errors.append(str(e))


ths = [threading.Thread(target=worker) for _ in range(4)]
for t in ths:
    t.start()
# 检测期间不断热切换，模拟运营边改词边检测
for i in range(10):
    db.banned_word_upsert(f'并发词{i}', 'adlaw', '', 1 if i % 2 else 0)
    reapply()
for t in ths:
    t.join()
check('并发检测 + 热更新不抛异常', not errors, '; '.join(errors[:2]))

# ── 7. 幂等：重复 upsert 同一词不产生重复条目 ─────────────────────────────
db.banned_word_upsert('幂等词', 'adlaw', '建议A', 1)
reapply()
db.banned_word_upsert('幂等词', 'adlaw', '建议B', 1)
reapply()
snap = db.banned_custom_snapshot()
check('重复 upsert 仍只有一条',
      len([w for w in snap if w == '幂等词']) == 1, str(snap.get('幂等词')))
check('重复 upsert 更新的是建议值',
      snap.get('幂等词', {}).get('suggest') == '建议B',
      str(snap.get('幂等词')))
db.banned_word_delete('幂等词')
reapply()

# ── 8. API 层必须校验类目（否则运营填错类目会「看起来成功」但词不生效）──
# ⚠️ 上面 1. 的失败正是这个坑：banned_word_upsert 本身不校验类目，
#非法类目在 refresh_overrides 里被 `if v['category'] in CATEGORIES` 静默丢弃。
# API 层挡住了，但只有断言能保证它别被删掉。
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import config as _cfg  # noqa: E402

# ⚠️ 必须设 API_KEY：管理端点已改为【默认拒绝】（未配 Key → 503 全部锁定）。
# 这条测试原先没设，于是被安全修复顶掉了 —— 修法是给测试配 Key，而不是放宽安全。
_cfg.API_KEY = 'test-key'
_AH = {'X-Api-Key': 'test-key'}

with TestClient(app) as cl:
    r = cl.post('/api/admin/banned/words', json={
        'word': '端到端测试词', 'category': '不存在的类目', 'suggest': ''}, headers=_AH)
    check('API 拒绝非法类目（400）', r.status_code == 400, f'{r.status_code} {r.text[:80]}')

    r2 = cl.post('/api/admin/banned/words', json={
        'word': '端到端测试词', 'category': 'adlaw', 'suggest': '换个说法'}, headers=_AH)
    check('API 接受合法类目（200）', r2.status_code == 200, f'{r2.status_code} {r2.text[:80]}')

    r3 = cl.post('/api/admin/banned/words', json={
        'word': 'x' * 30, 'category': 'adlaw', 'suggest': ''}, headers=_AH)
    check('API 拒绝超长词（400）', r3.status_code == 400, f'{r3.status_code}')

    r4 = cl.post('/api/admin/banned/words',
                 json={'word': '', 'category': 'adlaw'}, headers=_AH)
    check('API 拒绝空词（400）', r4.status_code == 400, f'{r4.status_code}')

    # 「未配 Key → 503 默认拒绝」由 tests/test_admin_auth.py 专项覆盖。
    # 这里不适合断言：本格测试为跑通 API 已把 _cfg.API_KEY 设为 'test-key'
    # （模块级全局），无 Key 调用自然落到 401 而非 503。

# 端到端：看板新增的词，真能参与检测
reapply()
r5 = banned.detect('这是端到端测试词啊', full=True)
check('API 新增的词端到端立即生效',
      '端到端测试词' in str(r5['marks']), str(r5['marks'])[:120])
db.banned_word_delete('端到端测试词')
reapply()

print(f'\n════ 违禁词库热更新：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')
print(f'（临时库 {os.path.basename(_tmp)}，真实库未被触碰）')