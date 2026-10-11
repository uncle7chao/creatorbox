"""快手 GraphQL 探测 —— 分离变量：到底缺什么才能拿数据

背景：`https://www.kuaishou.com/f/{token}` 会 302到
      `/short-video/{workId}?shareToken={token}&...`
      workId 形如 `3xha63juacrpw69`（**不是数字 photoId**）

已知：
- 最终页面只返回 `{"result":2,...}` 82 字节 → 需要 CSR
- GraphQL 端点 `/graphql` 活着，且**会告诉你正确的字段名**
  （我瞎写 visionPhotoDetail，它回 "Did you mean visionVideoDetail?"）

本脚本要回答：只加 cookie 够不够？还是要 __clientid 签名？
"""
import gzip
import http.cookiejar
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SHARE = 'https://www.kuaishou.com/f/X3n2Z5bXSt9g1wp'
GQL = 'https://www.kuaishou.com/graphql'

JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(JAR),
    urllib.request.HTTPSHandler(context=CTX))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


NOREDIR = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(JAR), NoRedirect,
    urllib.request.HTTPSHandler(context=CTX))


def fetch(url, data=None, referer=None, headers=None, timeout=25,
          follow=True):
    h = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate',
         'Accept-Language': 'zh-CN,zh;q=0.9',
         'Accept': 'text/html,application/xhtml+xml,*/*'}
    if referer:
        h['Referer'] = referer
    if headers:
        h.update(headers)
    op = OPENER if follow else NOREDIR
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        r = op.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        return None, e
    raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw, r


print('=== 1. 短链 302 → 拿 workId ===')
raw, resp = fetch(SHARE, follow=False)
if resp is None:
    print('  失败', resp)
    sys.exit(1)
loc = resp.headers.get('Location') or resp.headers.get('location') or ''
WORK = ''
MID = ''
if 'short-video/' in loc:
    WORK = loc.split('/short-video/', 1)[1].split('?')[0]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    MID = (q.get('shareId') or [''])[0]
print(f'  workId = {WORK}')
print(f'  shareId = {MID}')
print(f'  短链 token 形态: {SHARE.rsplit("/", 1)[-1]}（非数字）')

print('\n=== 2. 逛首页建立会话 ===')
raw, _ = fetch('https://www.kuaishou.com/')
print(f'  首页 {len(raw) if raw else 0} 字节, cookie {len(JAR)} 个')
for c in list(JAR)[:10]:
    print(f'    - {c.name} = {str(c.value)[:26]}')

print('\n=== 3. 带会话请求 short-video 页 ===')
raw, _ = fetch(f'https://www.kuaishou.com/short-video/{WORK}')
if raw:
    txt = raw.decode('utf-8', 'ignore')
    print(f'  页面 {len(txt)} 字符')
    for k in ('INIT_STATE', 'APOLLO', 'photoId', 'mainMvUrls',
              'srcNoWatermark', 'workId', WORK):
        print(f'    {k:18s}: {txt.count(k)}')

print('\n=== 4. GraphQL visionVideoDetail（带会话）===')
Q = ('query visionVideoDetail($photoId: String, $type: String, '
     '$page: String, $webPageArea: String) { visionVideoDetail('
     'photoId: $photoId, type: $type, page: $page, webPageArea: $webPageArea) {'
     ' status photo { id caption duration likeCount viewCount photoUrl } } }')
for tag, payload in [
    ('photoId=workId', {'photoId': WORK, 'type': 'video',
                        'page': 'short-video'}),
    ('photoId=shareId', {'photoId': MID, 'type': 'video',
                         'page': 'short-video'}),
]:
    body = json.dumps({
        'operationName': 'visionVideoDetail',
        'variables': payload, 'query': Q}).encode()
    raw, err = fetch(GQL, data=body,
                     referer=f'https://www.kuaishou.com/short-video/{WORK}',
                     headers={'Content-Type': 'application/json'},
                     timeout=25)
    if raw is None:
        print(f'  {tag:18s} HTTP {getattr(err, "code", "?")}')
        continue
    txt = raw.decode('utf-8', 'ignore')
    print(f'  {tag:18s} {txt[:170]}')

print('\n=== 5. 试 REST 风格接口 ===')
for path in [
    f'/rest/wd/photo/detail?photoId={WORK}',
    f'/rest/wd/share/video?shareToken={SHARE.rsplit("/", 1)[-1]}',
    f'/rest/reco/feed?photoId={WORK}',
]:
    raw, err = fetch(f'https://www.kuaishou.com{path}',
                     referer='https://www.kuaishou.com/')
    if raw is None:
        print(f'  {path[:48]:50s} HTTP {getattr(err, "code", "?")}')
    else:
        print(f'  {path[:48]:50s} {raw[:110].decode("utf-8", "ignore")}')
