"""搜狐视频接口批量验证 —— 确认成功率与字段真实性"""
import gzip
import json
import os
import ssl
import sys
import time
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
KEY = 'api_key=9854b2afa779e1a6bcdd07b217417549&sver=6.2.0'
OUT = os.path.dirname(os.path.abspath(__file__))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

VIDS = ['620251480', '620251533', '620250536', '620253046',
        '620253660', '620251321', '620254006', '620139607']


def get(url, ref='https://tv.sohu.com/'):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': ref,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate'})
    r = urllib.request.urlopen(req, timeout=25, context=CTX)
    raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw


def probe_size(url, ref='https://tv.sohu.com/'):
    """只取前 1MB 验证可下载 + 真实体积（Range）"""
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': ref, 'Range': 'bytes=0-1048575'})
    r = urllib.request.urlopen(req, timeout=30, context=CTX)
    data = r.read()
    cr = r.headers.get('Content-Range')
    total = int(cr.split('/')[-1]) if cr and '/' in cr else len(data)
    return len(data), total, r.status


ok = 0
for vid in VIDS:
    t0 = time.time()
    try:
        j = json.loads(get(
            f'https://api.tv.sohu.com/v4/video/info/{vid}.json?site=2&{KEY}'
        ).decode('utf-8', 'ignore'))
    except Exception as e:
        print(f'{vid}  EXC {str(e)[:60]}')
        continue
    if j.get('status') != 200:
        print(f"{vid}  FAIL status={j.get('status')} {j.get('statusText','')[:38]}")
        continue
    d = j['data']
    u = d.get('url_high_mp4') or d.get('download_url') or ''
    if not u:
        print(f'{vid}  NO_URL')
        continue
    try:
        got, total, code = probe_size(u)
    except Exception as e:
        print(f'{vid}  DL_FAIL {str(e)[:50]}')
        continue
    ok += 1
    name = (d.get('video_name') or '')[:20]
    print(f'{vid}  OK  {code}  {name!r:24s} dur={d.get("clips_duration_high")}s '
          f'real={total/1048576:.2f}MB claimed={d.get("file_size_high")} '
          f'user={(d.get("user") or {}).get("nickname","")[:12]} {time.time()-t0:.2f}s')
    with open(os.path.join(OUT, f'sohu_{vid}.json'), 'w',
              encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)

print(f'\n可用 {ok}/{len(VIDS)}')
