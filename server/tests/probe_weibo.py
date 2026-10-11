"""微博视频接口实测 —— 首次拿到真实 oid

⚠️ 本脚本验证 knowledge.FIELD_PATTERNS.weibo 的字段假设，其中
   「urls 第一个 key 是最高码率」这条**实测是错的**（第一个是 1080P，
   恰好也是最高，但排序规则与文档描述不符，需修正）。
"""
import gzip
import json
import ssl
import sys
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

OID = '1034:5343195622473745'


def post(url, data, referer, timeout=25):
    body = urllib.parse.urlencode({'data': json.dumps(data, ensure_ascii=False)})
    req = urllib.request.Request(url, data=body.encode(), headers={
        'User-Agent': UA, 'Referer': referer,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate',
        'X-Requested-With': 'XMLHttpRequest',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


def get(url, referer, timeout=25):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': referer,
        'Accept-Encoding': 'gzip, deflate'})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw


def probe(url, referer, timeout=25):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': referer, 'Range': 'bytes=0-1'})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        cr = r.headers.get('Content-Range') or ''
        ct = r.headers.get('Content-Type') or ''
    total = int(cr.rsplit('/', 1)[-1]) if '/' in cr and \
        cr.rsplit('/', 1)[-1].strip().isdigit() else -1
    return total, ct


print('=== 1. component 接口 ===')
j = post(f'https://h5.video.weibo.com/api/component?page=/show/{OID}',
         {'Component_Play_Playinfo': {'oid': OID}},
         f'https://h5.video.weibo.com/show/{OID}')
print(f"  code={j.get('code')} msg={j.get('msg')}")
info = ((j.get('data') or {}).get('Component_Play_Playinfo') or {})
if not info:
    print('  组件为空 —— oid 无效')
    sys.exit(1)

for k in ('oid', 'title', 'author', 'nickname', 'author_id', 'verified',
          'verified_reason', 'date', 'real_date', 'media_id', 'user'):
    if k in info:
        print(f'  {k:16s}: {str(info[k])[:70]}')
print(f"  followers_count : {info.get('followers_count')}")
print(f"  attitudes_count : {info.get('attitudes_count')}")
print(f"  comments_count  : {info.get('comments_count')}")

print('\n=== 2. 清晰度档位（urls 的 key 顺序很关键）===')
urls = info.get('urls') or {}
REF = f'https://h5.video.weibo.com/show/{OID}'
for i, (label, u) in enumerate(urls.items()):
    full = 'https:' + u if u.startswith('//') else u
    try:
        total, ct = probe(full, REF)
        print(f'  [{i}] {label:14s} {total / 1048576:8.2f}MB  {ct}')
    except Exception as e:
        print(f'  [{i}] {label:14s} ERR {str(e)[:44]}')
    print(f'       {full[:96]}')

print(f"\n  stream_url 存在: {bool(info.get('stream_url'))}")
if info.get('stream_url'):
    print(f"    {str(info['stream_url'])[:96]}")

# 取最高档
best_label, best_url = next(iter(urls.items()))
best = 'https:' + best_url if best_url.startswith('//') else best_url
print(f'\n=== 3. 首档（{best_label}）下载验证 ===')
req = urllib.request.Request(best, headers={'User-Agent': UA, 'Referer': REF})
with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
    blob = r.read()
    ct = r.headers.get('Content-Type')
print(f'  HTTP 下载 {len(blob)} 字节 ({len(blob) / 1048576:.2f} MB)  ct={ct}')
print(f'  ftyp: {blob[4:12]}')

import struct
i = blob.find(b'tkhd')
if i >= 4:
    b = i - 4
    w = struct.unpack('>I', blob[b + 84:b + 88])[0] >> 16
    h = struct.unpack('>I', blob[b + 88:b + 92])[0] >> 16
    print(f'  分辨率: {w}x{h}')
j2 = blob.find(b'mvhd')
if j2 >= 4:
    b = j2 - 4
    ts = struct.unpack('>I', blob[b + 20:b + 24])[0]
    du = struct.unpack('>I', blob[b + 24:b + 28])[0]
    print(f'  时长: {du / ts:.2f}s (timescale={ts})')
tracks = blob.count(b'trak')
print(f'  trak 盒数: {tracks // 2} (视频+音频=2 → 单文件含音轨)')

print('\n=== 4. 页面 SSR（拿封面）===')
try:
    page = get(f'https://weibo.com/tv/show/{OID}', 'https://weibo.com/')
    txt = page.decode('utf-8', 'ignore')
    print(f'  页面 {len(txt)} 字节')
    for k in ('poster', 'cover', 'page_info', 'status'):
        print(f'    {k:12s}: {txt.count(k)}')
except Exception as e:
    print(f'  页面抓取失败: {str(e)[:60]}')
