"""好看视频：纯 HTTP + 会话 cookie 是否够用（避免不必要的浏览器开销）

背景：知识库记为 engine=browser（需过滑块），但那次验证用的是
      「浏览器内 fetch」。这里分离变量：只靠 cookie 能不能过？
"""
import gzip
import http.cookiejar
import json
import ssl
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(JAR),
    urllib.request.HTTPSHandler(context=CTX))

VIDS = ['1688233510589355861', '1615713059572946930',
        '1891980261675370327', '16481085785828018426']


def fetch(url, referer=None, timeout=20):
    h = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate',
         'Accept': '*/*'}
    if referer:
        h['Referer'] = referer
    r = OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout)
    raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw, r.geturl()


print('=== 1) 先逛首页拿 cookie ===')
try:
    body, final = fetch('https://haokan.baidu.com/')
    print(f'   HTTP 200 / {len(body)} 字节 / 最终URL {final[:60]}')
    print(f'   cookie 数: {len(JAR)}')
    for c in list(JAR)[:8]:
        print(f'     - {c.name} = {str(c.value)[:28]}')
except Exception as e:
    print('首页失败:', str(e)[:80])

print('\n=== 2) 带 cookie 打 _format=json ===')
for vid in VIDS:
    try:
        raw, _ = fetch(f'https://haokan.baidu.com/v?_format=json&vid={vid}',
                       referer=f'https://haokan.baidu.com/v?vid={vid}')
        j = json.loads(raw.decode('utf-8', 'ignore'))
        errno = j.get('errno')
        meta = ((j.get('data') or {}).get('apiData') or {})
        cur = meta.get('curVideoMeta') or {}
        clarity = cur.get('clarityUrl') or []
        print(f'   vid={vid}  errno={errno}  '
              f'apiData={"有" if meta else "无"}  '
              f'curVideoMeta={"有" if cur else "无"}  '
              f'清晰度档数={len(clarity)}')
        if cur.get('title'):
            print(f'      标题: {cur["title"][:40]}')
    except Exception as e:
        print(f'   vid={vid}异常: {str(e)[:60]}')

print('\n=== 3) 试SSR 页面里的 __PRELOADED_STATE__ ===')
try:
    raw, _ = fetch('https://haokan.baidu.com/v?vid=' + VIDS[0])
    txt = raw.decode('utf-8', 'ignore')
    print(f'   页面 {len(txt)} 字节')
    for k in ('__PRELOADED_STATE__', 'curVideoMeta', 'clarityUrl',
              'web_hkoffline', '安全验证', '滑块'):
        print(f'     {k:22s}: {txt.count(k)}')
except Exception as e:
    print('页面失败:', str(e)[:80])
