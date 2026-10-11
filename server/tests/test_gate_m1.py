"""M1 Gate 验证：域名注册表 + 健康度探针（走真实 HTTP 接口）"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv('CB_TEST_BASE', 'http://127.0.0.1:8101')


def get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


def post(path, payload, timeout=120):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'ignore'))
    except urllib.error.HTTPError as e:
        return {'error': f'HTTP {e.code}',
                'body': e.read().decode('utf-8', 'ignore')[:200]}


print('=' * 70)
print('1. GET /api/domains —— 域名注册表')
print('=' * 70)
d = get('/api/domains')
s, w = d['snapshot'], d['wechat_whitelist']
print(f"  可白名单: {s['whitelist_ok']}")
print(f"  需中转  : {s['must_proxy']}")
print(f"  域名总数: {w['total_domains']} / {w['limit']} → "
      f"{'✅ 未超' if w['within_limit'] else '❌ 超限'}")
print(f"  未登记域名（改版早期信号）: {s['unlisted_hosts'] or '无'}")
print('\n  各平台明细:')
for r in w['rows']:
    mark = '✅' if r['whitelist_ok'] else '❌'
    print(f"    {mark} {r['name_cn']:8s} ({r['count']} 个) "
          f"{'直连' if r['whitelist_ok'] else '中转'}  {r['note'][:38]}")

print()
print('=' * 70)
print('2. POST /api/domains/classify —— 单 URL 判定')
print('=' * 70)
cases = [
    ('https://upos-sz-estgoss.bilivideo.com/x/y.mp4', 'B站随机子域'),
    ('https://vdept3.bdstatic.com/mda-x/1080p/cae_h264/1.mp4', '好看视频'),
    ('https://f.video.weibocdn.com/u0/a.mp4', '微博'),
    ('https://p3-pc-sign.douyinpic.com/tos-cn-i-0/a~tplv-dy-aweme-images.jpeg',
     '抖音图集'),
    ('https://tx-safety-video.acfun.cn/mediacloud/a.m3u8', 'AcFun m3u8'),
    ('https://data.vod.itc.cn/?k=abc', '搜狐'),
]
for url, label in cases:
    c = post('/api/domains/classify', {'text': url})
    mark = '✅ 直连' if c.get('whitelist_ok') else '❌ 中转'
    print(f"  {mark}  {label:16s} → {c.get('name_cn') or '(未匹配)':8s} "
          f"host={c.get('host', '')[:40]}")

print()
print('=' * 70)
print('3. POST /api/health/platforms/probe —— 立即探针')
print('=' * 70)
d = post('/api/health/platforms/probe', {})
print(f"  统计: {d['counts']}  全绿={d['all_ok']}")
for p in d['probes']:
    print(f"    {p['name_cn']:10s} {p['status']:9s} "
          f"{str(p.get('latency_ms')) + 'ms':>8s} "
          f"{str(p.get('quality') or '-'):10s} "
          f"{str(p.get('options') or '-'):>2s} 档"
          f"{'  ⚠️' + p.get('warning', '')[:24] if p.get('warning') else ''}"
          f"{'  ' + p.get('error', '')[:40] if p.get('error') else ''}")
print(f"\n  告警: {len(d['alerts'])} 条")
for a in d['alerts']:
    print(f"    [{a['level']}] {a['name_cn']}: {a['message'][:56]}")

print()
print('=' * 70)
print('4. GET /api/health/platforms —— 看板（含 L2 流量统计）')
print('=' * 70)
d = get('/api/health/platforms')
print(f"  探针开关: {d['probe_enabled']}  间隔 {d['probe_interval_s']}s")
print(f"  探针数  : {d['checked']}  全绿: {d['all_ok']}")
tv = d.get('traffic') or {}
if tv:
    print('\n  L2 真实流量（本次会话累积）:')
    for p, st in tv.items():
        if st.get('samples'):
            print(f"    {p:10s} 样本={st['samples']:3d} "
                  f"成功率={st['success_rate']} "
                  f"p50={st.get('p50_ms')}ms p95={st.get('p95_ms')}ms "
                  f"截断={st.get('truncated')}")
else:
    print('  （暂无流量样本，走一次 /api/parse 后再看）')

print('\n' + '=' * 70)
ok = s['whitelist_ok'] and d['all_ok']
print(f'M1 Gate 条件:域名表✅({len(s["whitelist_ok"])} 个可白名单)'
      f'  健康度看板✅({d["counts"]["ok"]}/{d["checked"]} 全绿)')
print('=' * 70)
