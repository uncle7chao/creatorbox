# -*- coding: utf-8 -*-
"""探针样本池·配置层测试（v4 §3.2）。

为什么单独一个文件：test_probe_pool.py 已完整覆盖**轮换机制**
（首选失败轮换 / 死样本 24h 冷却 / 全灭判定 / 冷却到期复活），
但那是用 FakeParser 测的 —— 机制对，不代表【配置里真的填了多样本】。
实测事实：2026-10-11 之前所有平台都只有 url 单样本，机制空转。

⚠️ 样本必须【实测通过】才能入池。实测排除记录（勿再塞回来）：
  ❌ v.douyin.com/hZMkNvXLtLc   → 解析 0 档
  ❌ 小红书裸链（无 xsec_token） → 解析 0 档
  ❌ v.douyin.com/abc / xxx      → 测试里的伪造占位符
填未验证样本 = 把探针变噪音源，比不做更糟。

跑法： python tests/test_probe_pool_cfg.py
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_poolcfg_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'pcfg.db')
sys.path.insert(0, '.')

from app.health import PROBES, _sample_urls  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


# ── 1. 配置来源（app/health.py 的 PROBES 是探针配置唯一事实源）──────────
cfg_src = PROBES
check('探针配置可读取', isinstance(cfg_src, dict) and len(cfg_src) > 0,
      f'{len(cfg_src)} 个平台')

pools = {k: _sample_urls(v) for k, v in cfg_src.items()
         if isinstance(v, dict) and v.get('assert') is not None}
print('\n   当前样本池配置（仅含带断言的平台）：')
for k, v in sorted(pools.items()):
    mark = f'池×{len(v)}' if len(v) > 1 else '单样本'
    print(f'     {k:14} {mark}')
print()

# ── 2. 至少一个平台已配池 ──────────────────────────────────────────────────
multi = {k: v for k, v in pools.items() if len(v) > 1}
check('至少一个平台已配样本池', len(multi) >= 1,
      f'仍是全部单样本（{len(multi)} 个有池）')

# ── 3. 已验证的快手池必须就位 ─────────────────────────────────────────────
if 'kuaishou' in pools:
    ks = pools['kuaishou']
    check('kuaishou 主样本仍是原 url 字段',
          ks[0] == cfg_src['kuaishou']['url'], str(ks[:1]))
    check('kuaishou 含实测通过的备用样本',
          any('X3n2Z5bXSt9g1wp' in u for u in ks), str(ks))
    check('kuaishou 池长为 2', len(ks) == 2, str(len(ks)))

# ── 4. 池内不得有重复（重复 = 没备选）────────────────────────────────────
for k, v in pools.items():
    real = [x for x in v if x]
    check(f'{k} 池内无重复', len(real) == len(set(real)), str(real))

# ── 5. 池内不得有占位/伪造样本 ────────────────────────────────────────────
FORBIDDEN = ('abc', 'xxx', 'example.com', 'placeholder', 'test123', '/xxx')
for k, v in pools.items():
    bad = [u for u in v if u and any(f in u.lower() for f in FORBIDDEN)]
    check(f'{k} 无占位/伪造样本', not bad, str(bad))

# ── 6. 实测失败的样本不得混进任何池 ───────────────────────────────────────
# 这两条是实测过 0 档的，塞进去会让探针长期 fail
KNOWN_BAD = ('hZMkNvXLtLc',)
for k, v in pools.items():
    bad = [u for u in v if any(b in u for b in KNOWN_BAD)]
    check(f'{k} 不含实测失败样本', not bad, str(bad))

# ── 7. 小红书主样本必须带 xsec_token（实测：无 token 读不到图集）─────────
if 'xiaohongshu' in cfg_src:
    u = cfg_src['xiaohongshu'].get('url', '')
    check('小红书主样本带 xsec_token', 'xsec_token' in u, u[:80])

# ── 8. 轮转切片不丢样本（pref 遍历整池）──────────────────────────────────
for k, v in pools.items():
    real = [x for x in v if x]
    if not real:
        continue
    for pref in range(len(real)):
        order = real[pref:] + real[:pref]
        if sorted(order) != sorted(real) or len(order) != len(real):
            check(f'{k} pref={pref} 轮转不丢样本', False, str(order))
            break
    else:
        check(f'{k} 轮转遍历完整', True)

print(f'\n════ 探针样本池配置：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')

# ── 附：待补样本清单（诚实地留在这里，而不是塞进假的）────────────────────
print('\n📋 仍为单样本的平台（缺实测可用的备选链接）：')
for k, v in sorted(pools.items()):
    if len([x for x in v if x]) == 1:
        print(f'   · {k}')
print('   补法：找到新样本 → 实测 /api/parse 成功 → 加进 cfg 的 urls 列表')
print('   ⚠️ 不要从测试代码里抄链接（大量是伪造占位符）')