"""四平台端到端回归：走真实 HTTP 接口 /api/parse"""
import json
import sys
import time
import urllib.request

# ⭐ 端口从环境变量读，不要写死 ——
#   写死会导致「改了服务端口忘了改这里」，回归静默打到旧服务/别的服务，
#   报出莫名其妙的失败（我已踩过两次：快手用例报成 douyin 解析失败）。
import os
BASE = os.environ.get('CB_TEST_BASE', 'http://127.0.0.1:8080')

CASES = [
    ('抖音视频', 'https://v.douyin.com/hZMkNvXLtLc/'),
    ('B站', 'https://www.bilibili.com/video/BV1GJ411x7h7'),
    ('好看视频', 'https://haokan.baidu.com/v?vid=1688233510589355861'),
    ('好看视频2', 'https://haokan.baidu.com/v?vid=1615713059572946930'),
    ('搜狐(30s内)', 'https://tv.sohu.com/v/MjAyNjA5MzAvbjYyMDI1MzY2MC5zaHRtbA==.html'),
    ('搜狐(76s截断)', 'https://tv.sohu.com/v/MjAyNjA5MjgvbjYyMDI1MzA0Ni5zaHRtbA==.html'),
    ('微博视频', 'https://weibo.com/tv/show/1034:5343195622473745'
                '?mid=5343196424963244'),
    ('AcFun', 'https://www.acfun.cn/v/ac48890260'),
    ('小红书图集', 'https://www.xiaohongshu.com/discovery/item/6a827209000000002701cde0'
                  '?xsec_token=AB7esHwJgaSaSlhVeq7GJlZN8Fi1J6MrUIjviv8R_APxM='
                  '&xsec_source=pc_share'),
    ('小红书视频', 'https://www.xiaohongshu.com/discovery/item/6a72adee0000000033036edf'
                  '?source=webshare&xhsshare=pc_web'
                  '&xsec_token=ABgKYGq72MJJJWO8OVQh3MtnwjRfcqKYxsujnzRIHNdTA='
                  '&xsec_source=pc_share'),
    ('快手(竖屏)', 'https://www.kuaishou.com/f/X-3M7HpE9Kh3sh1V'),
    ('快手(横屏)', 'https://www.kuaishou.com/f/X3n2Z5bXSt9g1wp'),
]


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


ok = 0
print(f'{"用例":16s} {"结果":6s} {"耗时":>7s} {"平台":9s} {"画质":12s} 说明')
print('-' * 88)
for name, url in CASES:
    t0 = time.time()
    try:
        d = post('/api/parse', {'text': url, 'quality': '1080p'})
    except Exception as e:
        print(f'{name:16s} EXC    {"":7s} {str(e)[:40]}')
        continue
    dt = time.time() - t0
    good = d.get('success')
    ok += bool(good)
    note = ''
    if d.get('truncated'):
        note = f"⚠️截断 {d.get('duration_actual_s')}s/{d.get('duration_claimed_s')}s"
    elif d.get('user_warning'):
        note = d['user_warning'][:34]
    elif d.get('cross_platform_fallback'):
        note = '跨库回退自 ' + d['cross_platform_fallback']
    elif d.get('fallback_from'):
        note = '浏览器兜底'
    elif not good:
        note = d.get('error', '')[:40]
    else:
        note = f"{d.get('options_count')} 档 | " \
               f"{(d.get('size') or 0) / 1048576:.1f}MB"
    print(f'{name:16s} {"OK" if good else "FAIL":6s} {dt:6.2f}s '
          f'{str(d.get("platform")):9s} {str(d.get("quality")):12s} {note}')

print(f'\n成功 {ok}/{len(CASES)}')

# 缓存验证
print('\n=== 缓存复用验证（同 URL 再请求一次）===')
t0 = time.time()
d = post('/api/parse', {'text': CASES[2][1], 'quality': '1080p'})
print(f"  cached={d.get('cached')}  耗时 {time.time() - t0:.3f}s")

# 批量
print('\n=== 批量解析 ===')
b = post('/api/batch', {'items': [{'text': u, 'quality': '1080p'}
                                 for _, u in CASES]})
print(f"  total={b['total']} ok={b['ok']} fail={b['fail']}")

# 知识库
print('\n=== 知识库 API ===')
with urllib.request.urlopen(BASE + '/api/knowledge/platforms', timeout=20) as r:
    k = json.loads(r.read().decode())
print(f"  total={k['total']} ready={k['ready']} "
      f"partial={k['partial']} blocked={len(k['blocked'])} "
      f"pending={k['pending']}")
print(f"  踩坑 {k['pitfalls_count']} 条，critical={k['critical_pitfalls']}")
print(f"  纯 HTTP 平台: {k['pure_http']}")
print(f"  已知缺口: {[g['gap'] for g in k['known_gaps']]}")
