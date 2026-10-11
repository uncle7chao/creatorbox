# -*- coding: utf-8 -*-
"""探针样本池专项测试（2026-10-11）。

验证：候选轮换 / 死样本 24h 冷却 / preferred 优先 / 全灭=平台故障 /
冷却到期自动复活 / 单样本旧配置兼容。FakeParser 全离线，零网络。
"""
import os
import sys
import tempfile
import asyncio

_tmp = tempfile.mkdtemp(prefix='cb_probe_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'probe.db')
sys.path.insert(0, '.')

from app.health import PlatformProbe, _sample_urls  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name + (f'  | {detail}' if detail and not cond else ''))


class FakeParser:
    """按 url 分发结果的假解析器：routes[url] = result dict 或 Exception"""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def parse(self, url, quality=None):
        self.calls.append(url)
        r = self.routes[url]
        if isinstance(r, Exception):
            raise r
        return r


GOOD = lambda u: {'success': True, 'video_url': u, 'options_count': 5}
cfg2 = {'urls': ['dead_a', 'live_b'],
        'assert': lambda r: bool(r.get('video_url'))}

# ── 1. _sample_urls 兼容 ────────────────────────────────────────────────
check('旧配置单 url 兼容', _sample_urls({'url': 'x'}) == ['x'])
check('urls 池 + url 首选', _sample_urls(
    {'url': 'a', 'urls': ['b', 'c']}) == ['a', 'b', 'c'])

# ── 2. 首选死了自动轮换到第二条 ──────────────────────────────────────────
fp = FakeParser({'dead_a': RuntimeError('视频不存在'),
                 'live_b': GOOD('live_b')})
p = PlatformProbe('douyin', fp, cfg2)
rec = asyncio.run(p.run())
check('首选失败轮换第二条 → ok', rec['ok'] is True, str(rec)[:100])
check('本轮试了 2 条样本', rec['samples_tried'] == 2)
check('记录命中的样本下标', rec['sample_idx'] == 1)
check('死样本进冷却', fp.routes and p._dead_until.get('dead_a', 0) > 0)

# ── 3. 冷却生效：下次 run 只试活样本 ─────────────────────────────────────
fp.calls.clear()
rec2 = asyncio.run(p.run())
check('冷却期内跳过死样本（只试 1 条）', rec2['samples_tried'] == 1
      and fp.calls == ['live_b'], str(fp.calls))
check('连续成功不积累 fail', rec2['consecutive_fail'] == 0)

# ── 4. preferred 记忆：活样本排在首选位 ──────────────────────────────────
check('preferred 指向成功样本', p._preferred == 1)

# ── 5. 全部候选失败 = 平台真故障 ─────────────────────────────────────────
fp2 = FakeParser({'dead_a': RuntimeError('x'), 'live_b': RuntimeError('y')})
p2 = PlatformProbe('douyin', fp2, cfg2)
rec3 = asyncio.run(p2.run())
check('全候选失败 → ok=False（平台级告警）', rec3['ok'] is False)
check('全灭打 pool_exhausted 标记', rec3.get('pool_exhausted') is True)
check('全灭记录 tried 数', rec3['samples_tried'] == 2)
check('全灭连续失败计数', rec3['consecutive_fail'] == 1)

# ── 6. 冷却到期自动复活 ─────────────────────────────────────────────────
p3 = PlatformProbe('douyin', fp2, cfg2)
p3._dead_until['dead_a'] = 1          # 已过期
rec4 = asyncio.run(p3.run())
check('冷却过期样本重新参与轮换', rec4['samples_tried'] == 2, str(rec4.get('samples_tried')))

# ── 7. assert 失败也算样本问题（平台活着以他样本为准）────────────────────
fp3 = FakeParser({
    'bad_struct': {'success': True, 'video_url': None},   # 结构坏
    'ok_c': GOOD('ok_c'),
})
p4 = PlatformProbe('douyin', fp3, {
    'urls': ['bad_struct', 'ok_c'],
    'assert': lambda r: bool(r.get('video_url'))})
rec5 = asyncio.run(p4.run())
check('首样本断言失败、次样本成功 → ok', rec5['ok'] is True)
check('断言失败样本同样进冷却', p4._dead_until.get('bad_struct', 0) > 0)

# ── 8. 单样本旧配置：行为与升级前一致 ────────────────────────────────────
fp4 = FakeParser({'only': RuntimeError('死了')})
p5 = PlatformProbe('weibo', fp4, {'url': 'only',
                                  'assert': lambda r: bool(r.get('video_url'))})
rec6 = asyncio.run(p5.run())
check('单样本失败 → ok=False', rec6['ok'] is False)
check('单样本不打 pool_exhausted（池没意义）',
      'pool_exhausted' not in rec6)

print(f'\n════ 探针样本池：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')
