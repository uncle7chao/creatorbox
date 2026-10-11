"""M2 前置 Gate：元信息覆盖度验证

原则：**接口没给就留None，绝不编造**。所以验收标准不是「全部有值」，
而是「该有的有，且缺失的都记在案」。

运行：python test_meta_coverage.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, r'D:\WorkBuddyFILE\CreatorBox\server')

from app.meta import field_coverage, normalize_meta   # noqa: E402
from app.parsers.acfun_pure import AcfunPureParser      # noqa: E402
from app.parsers.bilibili_pure import BilibiliPureParser  # noqa: E402
from app.parsers.douyin_pure import DouyinPureParser    # noqa: E402
from app.parsers.haokan_pure import HaokanPureParser    # noqa: E402
from app.parsers.kuaishou_pure import KuaishouPureParser  # noqa: E402
from app.parsers.sohu_pure import SohuPureParser        # noqa: E402
from app.parsers.weibo_pure import WeiboPureParser      # noqa: E402
from app.parsers.xiaohongshu_pure import (             # noqa: E402
    XiaohongshuPureParser)

CASES = [
    ('douyin', DouyinPureParser(),
     'https://v.douyin.com/ntaaK4aH9pE/'),
    ('bilibili', BilibiliPureParser(),
     'https://www.bilibili.com/video/BV1GJ411x7h7'),
    ('haokan', HaokanPureParser(),
     'https://haokan.baidu.com/v?vid=1688233510589355861'),
    ('sohu', SohuPureParser(),
     'https://tv.sohu.com/v/MjAyNjA5MzAvbjYyMDI1MzY2MC5zaHRtbA==.html'),
    ('weibo', WeiboPureParser(),
     'https://weibo.com/tv/show/1034:5343195622473745'
     '?mid=5343196424963244'),
    ('acfun', AcfunPureParser(),
     'https://www.acfun.cn/v/ac48890260'),
    ('kuaishou', KuaishouPureParser(),
     'https://www.kuaishou.com/f/X-3M7HpE9Kh3sh1V'),
    # ⭐ 用分享文案形态 —— 视频笔记的标题只能从分享文案取（P34）
    ('xiaohongshu', XiaohongshuPureParser(),
     '16 【一部上映十天却惨遭下架的电影，却赚足了观众的眼泪 '
     '虐心虐恋 古装玄幻 虐心片段 - 怪咖解说 | 小红书 - 你的生活兴趣社区】'
     ' \U0001f606 kkceQvt29agF6eV \U0001f606 '
     'https://www.xiaohongshu.com/discovery/item/6a72adee0000000033036edf'
     '?xsec_token=ABgKYGq72MJJJWO8OVQh3MtnwjRfcqKYxsujnzRIHNdTA='
     '&xsec_source=pc_share'),
]

# 关键字段：这些是产品必须展示的，缺任何一个都算 Gate 失败
CRITICAL = ('title', 'cover', 'author_name', 'duration_s')

# 已知缺口（接口确实不下发，如实记录而非伪造）
KNOWN_GAPS = {
    'haokan': ('author_name', 'author_avatar', 'description'),
    'douyin': ('description',),       # 抖音标题与文案同字段，不重复
    'acfun': ('description',),        # 接口无简介
    'kuaishou': (),                    # 字段最全
}


async def main() -> int:
    print('=' * 78)
    print('M2 前置 Gate · 元信息覆盖度')
    print('=' * 78)
    hdr = ('title', 'desc', 'cover', 'author', 'avatar', 'dur', 'time',
           'stats', 'tags')
    print(f"{'平台':14s}" + ''.join(f'{h:>7s}' for h in hdr))
    print('-' * 78)

    rows = {}
    for name, parser, url in CASES:
        try:
            r = await parser.parse(url)
        except Exception as e:
            print(f'{name:14s} 解析异常: {str(e)[:50]}')
            rows[name] = None
            continue
        if not r.get('success'):
            print(f'{name:14s} 解析失败（内容可能已失效）: '
                  f'{str(r.get("error"))[:44]}')
            rows[name] = None
            continue
        normalize_meta(r)
        cov = field_coverage(r)
        rows[name] = (r, cov)
        line = f'{name:14s}'
        for k in ('title', 'description', 'cover', 'author_name',
                  'author_avatar', 'duration_s', 'publish_time',
                  'stats', 'tags'):
            mark = '✅' if cov[k] else '—'
            if not cov[k] and k in KNOWN_GAPS.get(name, ()):
                mark = '○'          # 已知缺口
            line += f'{mark:>7s}'
        print(line)

    print()
    print('○ = 接口不下发（已在 KNOWN_GAPS 记录）')
    print()

    # ---- 映射表路径有效性（P31 防御）----
    # 映射表里写了某个 key，但解析器实际不返回它→ 静默失效。
    # 没有任何报错，只是字段永远为空 —— 必须主动查。
    from app.meta import (DURATION_RULES, EXTRA_RULES, PUBLISH_SOURCES,
                          STAT_SOURCES, TEXT_STAT_SOURCES)
    path_fails = []
    for name, row in rows.items():
        if not row:
            continue
        keys = set(row[0].keys())
        for std, per in STAT_SOURCES.items():
            paths = per.get(name, per.get('_default', []))
            # 只校验**主路径**（第1 个）—— 备用候选是容错，
            # 允许「当前没走到那」而不是「写错了」。
            # 但主路径必须存在，否则该字段永远取不到值。
            for path in paths[:1]:
                if path not in keys:
                    path_fails.append(f'{name}.stats.{std} →主路径 "{path}" '
                                      f'解析器不返回此 key')
        for path in PUBLISH_SOURCES.get(name, [])[:1]:
            if path not in keys:
                path_fails.append(f'{name}.publish → 主路径 "{path}" 不存在')
        for path in DURATION_RULES.get(name, [])[:1]:
            if path.split('.')[0] not in keys:
                path_fails.append(f'{name}.duration → 主路径 "{path}" 不存在')
        for std, path in TEXT_STAT_SOURCES.get(name, {}).items():
            if path not in keys:
                path_fails.append(f'{name}.stats_text.{std} → "{path}" 不存在')
        for std, path in EXTRA_RULES.get(name, {}).items():
            if path and path not in keys:
                path_fails.append(f'{name}.extra.{std} → "{path}" 不存在')

    print('映射表路径有效性:')
    if path_fails:
        for f in path_fails:
            print('  ❌', f)
    else:
        print('  ✅ 所有映射路径都指向解析器真实返回的 key')
    print()

    # ---- Gate 判定 ----
    fails = []
    for name, row in rows.items():
        if row is None:
            fails.append(f'{name}: 解析未成功，无法验收元信息')
            continue
        r, cov = row
        gaps = set(KNOWN_GAPS.get(name, ()))
        # ⭐ 图集没有「时长」是**正确行为**，不是缺口。
        #   抖音图集的 duration_ms 实测就是 0。
        #   判据必须看内容类型 —— 这是 P27 的同类问题：
        #   「字段为空」不等于「字段应该有却缺了」。
        if r.get('type') == 'image':
            gaps.add('duration_s')
        for k in CRITICAL:
            if not cov[k] and k not in gaps:
                fails.append(f'{name}: 关键字段 {k} 缺失且未登记为已知缺口'
                             f'（type={r.get("type")}）')

    # meta 结构完整性：所有键必须存在
    for name, row in rows.items():
        if not row:
            continue
        m = row[0].get('meta') or {}
        for k in ('title', 'description', 'cover', 'author_name',
                  'author_id', 'author_avatar', 'duration_s',
                  'publish_ts', 'publish_time', 'publish_time_text',
                  'stats', 'stats_text', 'tags', 'extra'):
            if k not in m:
                fails.append(f'{name}: meta 缺键 {k}'
                             f'（前端会崩，必须始终存在）')

    # 展示样本
    sample = next((v for v in rows.values() if v), None)
    if sample:
        print('样例（B站 meta 全文）:')
        print(json.dumps(sample[0]['meta'], ensure_ascii=False, indent=2))

    print()
    if fails or path_fails:
        total = len(fails) + len(path_fails)
        print(f'❌ Gate 未通过（{total} 项）:')
        for f in fails:
            print('   -', f)
        for f in path_fails:
            print('   - [映射]', f)
        return 1
    print('✅ Gate 通过：关键字段齐全 + meta 结构完整 '
          '+ 映射路径全部有效 + 缺失项均已登记')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
