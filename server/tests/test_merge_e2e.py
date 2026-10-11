"""m3u8 合并服务的端到端测试（走真实 HTTP 接口）

覆盖：
1. /api/ffmpeg 能力自检
2. /api/merge 搜狐（重复分段 → 应被拒绝，不产出垃圾文件）
3. /api/merge AcFun（正常分段 → 应成功，核对时长与抽帧）
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.getenv('CB_TEST_BASE', 'http://127.0.0.1:8101')
SOHU_M3U8 = r'D:\WorkBuddyFILE\CreatorBox\sohu_m3u8.txt'
ACFUN_M3U8 = r'D:\WorkBuddyFILE\CreatorBox\acfun_m3u8.txt'


def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'ignore'))


def post(path, payload, timeout=600):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'ignore'))
    except urllib.error.HTTPError as e:
        return {'success': False, 'http_error': e.code,
                'body': e.read().decode('utf-8', 'ignore')[:200]}


print('=' * 68)
print('1. /api/ffmpeg 能力自检')
print('=' * 68)
d = get('/api/ffmpeg')
c = d['capabilities']
for k in ('available', 'libx264', 'aac', 'mp4_muxer', 'faststart', 'tls'):
    print(f'  {k:14s}: {c.get(k)}')
print(f'  version: {c.get("version", "")[:60]}')
print(f'  许可提示: {d["license_note"][:70]}...')

print()
print('=' * 68)
print('2. /api/merge 搜狐 —— 分段内容重复，应拒绝')
print('=' * 68)
with open(SOHU_M3U8, encoding='utf-8') as f:
    sohu = f.read().strip()
t0 = time.time()
r = post('/api/merge', {'text': sohu, 'referer': 'https://tv.sohu.com/'})
print(f'  success              : {r.get("success")}')
print(f'  error                : {str(r.get("error"))[:70]}')
print(f'  duplicate_segments   : {r.get("duplicate_segments")}')
print(f'  唯一内容 / 总分段    : {r.get("unique_count")} / '
      f'{r.get("total_segments")}')
print(f'  hint                 : {str(r.get("hint"))[:56]}')
print(f'  耗时                 : {time.time() - t0:.2f}s')
assert r.get('success') is False, '重复分段必须被拒绝！'
assert r.get('duplicate_segments') is True
print('  ✅ 正确拒绝了重复分段（未产出垃圾文件）')

print()
print('=' * 68)
print('3. /api/merge AcFun —— 正常分段，应成功')
print('=' * 68)
with open(ACFUN_M3U8, encoding='utf-8') as f:
    acfun = f.read().strip()
t0 = time.time()
r = post('/api/merge', {'text': acfun, 'referer': 'https://www.acfun.cn/'})
dt = time.time() - t0
print(f'  success        : {r.get("success")}')
print(f'  mode           : {r.get("mode")}')
print(f'  产物体积       : {r.get("size_mb") or (r.get("size") or 0) / 1048576:.2f} MB')
out = r.get('output') or {}
print(f'  产物时长       : {out.get("duration_s")}s')
print(f'  faststart      : {out.get("faststart")}')
print(f'  duration_ratio : {r.get("duration_ratio")}')
print(f'  总耗时         : {dt:.2f}s')
if r.get('success') and r.get('path'):
    print(f'  产物路径       : {r["path"]}')
    assert abs(out.get('duration_s', 0) - 299.0) < 3, '时长与声明不符'
    assert r.get('duration_ratio') and 0.9 < r['duration_ratio'] < 1.1
    print('  ✅ 时长与 EXTINF 声明一致（299s）')
else:
    print(f'  ❌ 合并失败: {r.get("error")}')

print()
print('=' * 68)
print('4. 完整回归（八用例）')
print('=' * 68)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e_regression as e2e      # noqa

ok = 0
for name, url in e2e.CASES:
    t = time.time()
    d2 = post('/api/parse', {'text': url, 'quality': '1080p'}, timeout=90)
    good = d2.get('success')
    ok += bool(good)
    note = ''
    if d2.get('truncated'):
        note = f"⚠️截断 {d2.get('duration_actual_s')}s/{d2.get('duration_claimed_s')}s"
    elif d2.get('m3u8_only'):
        note = f"{d2.get('options_count')}档 需合并 m3u8"
    elif not good:
        note = str(d2.get('error'))[:36]
    else:
        note = f"{d2.get('options_count')} 档"
    print(f'  {name:16s} {"OK" if good else "FAIL":5s} '
          f'{time.time() - t:5.2f}s  {str(d2.get("platform")):9s} {note}')
print(f'\n  成功 {ok}/{len(e2e.CASES)}')
