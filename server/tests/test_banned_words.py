# -*- coding: utf-8 -*-
"""违禁词库热管理专项测试（2026-10-11）。

覆盖：停用内置词 / 自定义新增词热生效 / 建议透传 / 恢复与删除 /
合并视图 / 覆盖持久化（重 init 不丢）。全部离线临时库。
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_bw_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'bw.db')
sys.path.insert(0, '.')

from app import db           # noqa: E402
from app import banned       # noqa: E402

db.init()
PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name + (f'  | {detail}' if detail and not cond else ''))


snap = db.banned_custom_snapshot

# ── 1. 基线：内置词命中 ────────────────────────────────────────────────
banned.refresh_overrides(snap())
r0 = banned.detect('性价比第一的选择', full=False)
check('基线：内置词「第一」命中', any(
    m['word'] == '第一' for m in r0['marks']), str(r0['marks'])[:80])

# ── 2. 停用内置词 → 热生效 ─────────────────────────────────────────────
db.banned_word_upsert('第一', banned.builtin_category('第一'), '', 0)
banned.refresh_overrides(snap())
r1 = banned.detect('性价比第一的选择', full=False)
check('停用内置词后不再命中', not any(
    m['word'] == '第一' for m in r1['marks']), str(r1['marks'])[:80])
check('内置词类目回填正确', banned.builtin_category('第一') == 'adlaw')

# ── 3. 自定义新增词 → 热生效 + 建议透传 ────────────────────────────────
db.banned_word_upsert('神奇药水', 'medical', '普通饮品', 1)
banned.refresh_overrides(snap())
r2 = banned.detect('这款神奇药水包治百病', full=True)
hit = next((m for m in r2['marks'] if m['word'] == '神奇药水'), None)
check('自定义词命中', hit is not None, str(r2['marks'])[:100])
check('自定义词类目正确', hit and hit['category'] == 'medical')
g = next((g for g in r2['groups'] if g['category'] == 'medical'), {})
w = next((w for w in g.get('words', []) if w['word'] == '神奇药水'), {})
check('替换建议透传到 groups', w.get('suggest') == '普通饮品', str(w))

# ── 4. 自定义词免费类目隔离 ────────────────────────────────────────────
r2f = banned.detect('这款神奇药水很好', full=False)
check('付费类目自定义词 full=False 不查（进 locked）',
      not any(m['word'] == '神奇药水' for m in r2f['marks'])
      and 'medical' in r2f['locked'])

# ── 5. 停用自定义词 → 不命中；启用恢复 ─────────────────────────────────
db.banned_word_upsert('神奇药水', 'medical', '普通饮品', 0)
banned.refresh_overrides(snap())
r3 = banned.detect('这款神奇药水包治百病', full=True)
check('停用自定义词后不命中', not any(
    m['word'] == '神奇药水' for m in r3['marks']))
db.banned_word_upsert('神奇药水', 'medical', '普通饮品', 1)
banned.refresh_overrides(snap())
r4 = banned.detect('这款神奇药水包治百病', full=True)
check('重新启用后恢复命中', any(
    m['word'] == '神奇药水' for m in r4['marks']))

# ── 6. 删除覆盖行：自定义词消失 / 内置词恢复 ───────────────────────────
db.banned_word_upsert('临时词Z', 'adlaw', '', 1)
db.banned_word_delete('临时词Z')
db.banned_word_delete('第一')            # 内置词删覆盖行 = 恢复默认
banned.refresh_overrides(snap())
check('自定义词删除后消失', not any(
    m['word'] == '临时词Z' for m in banned.detect('临时词Z大甩卖', full=True)['marks']))
check('内置词删覆盖行后恢复命中', any(
    m['word'] == '第一' for m in banned.detect('性价比第一', full=False)['marks']))

# ── 7. 合并视图 ───────────────────────────────────────────────────────
db.banned_word_upsert('神奇药水', 'medical', '普通饮品', 0)
merged = banned.words_merged(snap())
by_word = {w['word']: w for w in merged}
check('合并视图含内置词（source=builtin）',
      by_word.get('第一', {}).get('source') == 'builtin')
check('合并视图含自定义词（source=custom）',
      by_word.get('神奇药水', {}).get('source') == 'custom')
check('覆盖停用状态体现在视图', by_word['神奇药水']['enabled'] is False)
check('视图规模 ≥ 内置词数', len(merged) >= sum(
    len(ws) for ws in banned.WORDS.values()))

# ── 8. 覆盖持久化：重新 init 不丢 ─────────────────────────────────────
db.init()                                # 幂等重跑
merged2 = banned.words_merged(db.banned_custom_snapshot())
by2 = {w['word']: w for w in merged2}
check('重 init 后覆盖仍在', by2['神奇药水']['enabled'] is False)

# ── 9. 非法类目被 refresh 忽略（防御）────────────────────────────────
db.banned_word_upsert('坏类目词', 'not_a_cat', '', 1)
banned.refresh_overrides(db.banned_custom_snapshot())
check('非法类目词不进编译表（不崩溃）',
      '坏类目词' not in banned._COMPILED.get('adlaw').pattern)
db.banned_word_delete('坏类目词')
banned.refresh_overrides(snap())

print(f'\n════ 违禁词库热管理：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')
