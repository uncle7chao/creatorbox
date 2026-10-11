"""平台可见性收敛开关测试（v4 §3.3 提审收敛）

全离线：不碰网络、不碰真实库，只验证「模式裁决 + 清单裁剪」这条逻辑。
跑法： python tests/test_visibility.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅ ' if cond else '❌ ') + name + (f'  [{detail}]' if detail and not cond else ''))


def load(mode):
    """按指定 REVIEW_MODE 重新加载 visibility（换环境变量 + 清模块缓存）。"""
    if mode is None:
        os.environ.pop('CB_REVIEW_MODE', None)
    else:
        os.environ['CB_REVIEW_MODE'] = mode
    for m in ('app.config', 'app.visibility'):
        sys.modules.pop(m, None)
    import app.config as cfg
    import app.visibility as vis
    return cfg, vis


# ── 1. 默认全开 ────────────────────────────────────────────────────────────
cfg, vis = load(None)
check('默认 REVIEW_MODE = full', vis.mode() == 'full', vis.mode())
p = vis.payload()
check('full 模式 review_mode=False', p['review_mode'] is False)
check('full 模式无隐藏平台', len(p['hidden_keys']) == 0, str(p['hidden_keys']))
check('full 模式全部平台可见',
      len(p['visible_keys']) == len(p['hidden_keys']) + len(p['visible_keys']))
check('清单与 knowledge 单一事实源一致',
      set(p['visible_keys']) == set(vis.PLATFORMS.keys()),
      f"{len(p['visible_keys'])} vs {len(vis.PLATFORMS)}")

# ── 2. 提审收敛 ────────────────────────────────────────────────────────────
cfg, vis = load('review')
p = vis.payload()
check('review 模式识别正确', vis.mode() == 'review', vis.mode())
check('review 模式 review_mode=True', p['review_mode'] is True)
check('review 仅保留白名单两个平台',
      p['visible_keys'] == ['bilibili', 'douyin'], str(p['visible_keys']))
check('review 下 douyin 可见', vis.is_visible('douyin') is True)
check('review 下 bilibili 可见', vis.is_visible('bilibili') is True)
for k in ('youtube', 'tiktok', 'x', 'facebook', 'xiaohongshu', 'kuaishou'):
    check(f'review 下 {k} 隐藏', vis.is_visible(k) is False)
check('review 隐藏不等于停用解析', p['hidden_still_parseable'] is True)
check('review 提示文案区分模式', '提审收敛' in p['note'], p['note'])

# 白名单兜底：knowledge 里新增任何平台，默认都会被收敛掉（提审漏配风险归零）
extra = [k for k in vis.PLATFORMS if k not in vis.REVIEW_VISIBLE]
check('非白名单平台一律收敛（含将来新增）',
      all(not vis.is_visible(k) for k in extra),
      str([k for k in extra if vis.is_visible(k)]))

# ── 3. 条目字段完整性（客户端渲染入口所需）────────────────────────────────
need = {'key', 'name_cn', 'types', 'max_quality', 'free_quality', 'status'}
for it in p['platforms']:
    check(f"条目 {it.get('key')} 字段齐全", need <= set(it.keys()), str(sorted(it.keys())))
    break  # 字段结构一致，查一条即可

# ── 4. 异常兜底 ────────────────────────────────────────────────────────────
cfg, vis = load('GARBAGE')
check('非法值回落 full（不因配置写错导致线上裸奔）', vis.mode() == 'full', vis.mode())
cfg, vis = load('')
check('空值回落 full', vis.mode() == 'full', vis.mode())
cfg, vis = load('Review')          # 大小写容错
check('大小写容错 review', vis.mode() == 'review', vis.mode())

# ── 5. 未知平台查询不崩 ────────────────────────────────────────────────────
cfg, vis = load(None)
try:
    vis.is_visible('never_existed_platform')
    check('查询未知平台不崩（返回 False 而非异常）', vis.is_visible('never_existed_platform') is False)
except Exception as e:
    check('查询未知平台不崩', False, str(e))

os.environ.pop('CB_REVIEW_MODE', None)

print(f'\n════ 提审收敛开关：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')