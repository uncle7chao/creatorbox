"""AcFun 详情页解析 —— ksPlayJson 是「JSON 套 JSON」

实测要点：
- 页面 SSR 里就有完整数据，**不需要浏览器**
- 数据在 `pageInfo.currentVideoInfo.ksPlayJson`，
  它本身是一个**被字符串化的 JSON**（\\" 转义），要 parse 两次
- 还有 `ksPlayJsonHevc`（H.265 编码），非 H265 设备要用 avc 那份
"""
import json
import re
import ssl
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

VID = sys.argv[1] if len(sys.argv) > 1 else 'ac48890260'
URL = f'https://www.acfun.cn/v/{VID}'


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        import gzip
        raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


html = get(URL)
print(f'页面 {len(html)} 字节')

# ---- 提取 window.pageInfo 之类的 JSON 块 ----
candidates = {}
for pat, name in [
    (r'window\.pageInfo\s*=\s*(\{.*?\});', 'pageInfo'),
    (r'window\.initialState\s*=\s*(\{.*?\});', 'initialState'),
]:
    m = re.search(pat, html, re.S)
    if m:
        candidates[name] = m.group(1)

print(f'找到 JS 块: {list(candidates)}')

# ---- 直接定位 currentVideoInfo ----
i = html.find('"currentVideoInfo"')
if i < 0:
    print('✗ 未找到 currentVideoInfo')
    sys.exit(1)

# 花括号配平提取该对象
start = html.rfind('{', 0, html.find(':', i))if False else None
# 从currentVideoInfo 后的第一个 { 开始配平
b = html.index('{', i)
depth = 0
for k in range(b, len(html)):
    if html[k] == '{':
        depth += 1
    elif html[k] == '}':
        depth -= 1
        if depth == 0:
            end = k + 1
            break
cvi = json.loads(html[b:end])
print('\n=== currentVideoInfo keys ===')
for k in sorted(cvi.keys()):
    v = cvi[k]
    if isinstance(v, str) and len(v) > 90:
        print(f'  {k:20s} = <str {len(v)} 字符>')
    elif not isinstance(v, (dict, list)):
        print(f'  {k:20s} = {v}')

# ---- ksPlayJson 是字符串化的 JSON ----
for key in ('ksPlayJson', 'ksPlayJsonHevc'):
    raw = cvi.get(key)
    if not raw:
        print(f'\n{key}: 无')
        continue
    print(f'\n=== {key} (字符串长度 {len(raw)}) ===')
    try:
        d = json.loads(raw)
    except Exception as e:
        print(f'  parse 失败: {e}')
        print('  原文前200:', raw[:200])
        continue
    print('  keys:', sorted(d.keys()))
    # ⚠️ adaptationSet 是**数组**不是对象（第一版按 dict 写直接 AttributeError）
    ads = d.get('adaptationSet') or []
    if isinstance(ads, dict):
        ads = [ads]
    print(f'  adaptationSet 数: {len(ads)}')
    reps = []
    for a in ads:
        if isinstance(a, dict):
            reps += (a.get('representation') or [])
    print(f'  representation 数: {len(reps)}')
    for r in reps:
        print(f"    quality={r.get('quality')} "
              f"qualityLabel={r.get('qualityLabel')} "
              f"size={r.get('width')}x{r.get('height')} "
              f"avgBitrate={r.get('avgBitrate')}")
        for bq in (r.get('backupUrl') or [])[:2]:
            print(f"      backup: {bq[:96]}")
        print(f"      keys: {sorted(r.keys())[:16]}")
    c = d.get('currentVideoInfo') or {}
    if c:
        print('  currentVideoInfo:', {k: c[k] for k in list(c)[:8]})

print('\n=== 视频元信息 ===')
for k in ('title', 'uploadId', 'durationMillis', 'likeCount', 'viewCount',
          'commentCount', 'description', 'user', 'createTime'):
    if k in cvi:
        v = cvi[k]
        if isinstance(v, dict):
            print(f'  {k:16s} = {json.dumps(v, ensure_ascii=False)[:150]}')
        else:
            print(f'  {k:16s} = {str(v)[:110]}')
