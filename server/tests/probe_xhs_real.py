"""小红书真实样本验证（用户提供带 xsec_token 的链接）

⚠️ 重要发现：PC UA 会被 302 到 /login，**iOS UA 直接 200**。
这意味着小红书对「桌面 UA + 无 cookie」强制登录墙，
但移动 UA 游客态可读 —— 这是与开源项目实现的关键差异。
"""
import gzip
import json
import re
import ssl
import urllib.error
import urllib.request

try:
    import yaml
except ImportError:
    yaml = None

IOS = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
       'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 '
       'Mobile/15E148 Safari/604.1')
PC = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

URL_IOS = ('https://www.xiaohongshu.com/discovery/item/6a827209000000002701cde0'
           '?source=webshare&xhsshare=pc_web'
           '&xsec_token=AB7esHwJgaSaSlhVeq7GJlZN8Fi1J6MrUIjviv8R_APxM='
           '&xsec_source=pc_share')


def get(url, ua, ref='https://www.xiaohongshu.com/', follow=False):
    h = {'User-Agent': ua, 'Accept': 'text/html,application/xhtml+xml,*/*',
         'Accept-Encoding': 'gzip, deflate',
         'Accept-Language': 'zh-CN,zh;q=9',
         'Referer': ref}
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX))
    if not follow:
        class NR(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                raise urllib.error.HTTPError(a[0].full_url, *a[1:6], None)
        op = urllib.request.build_opener(NR,
                                         urllib.request.HTTPSHandler(
                                             context=CTX))
    try:
        r = op.open(urllib.request.Request(url, headers=h), timeout=30)
    except urllib.error.HTTPError as e:
        return None, e, ''
    raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw, r, r.geturl()


print('=' * 70)
print('1. UA 对比（决定性）')
print('=' * 70)
for name, ua in (('iOS UA', IOS), ('PC UA', PC)):
    raw, r, final = get(URL_IOS, ua)
    if raw is None:
        loc = r.headers.get('Location') or ''
        verdict = '→ /login 登录墙' if '/login' in loc else \
                  f'→ {loc[:50]}'
        print(f'  {name:8s} HTTP {r.code}  {verdict}')
    else:
        print(f'  {name:8s} HTTP 200  {len(raw)} 字节 ✅')

print()
print('=' * 70)
print('2. iOS UA 抓取__INITIAL_STATE__')
print('=' * 70)
raw, r, final = get(URL_IOS, IOS)
if raw is None:
    print('  失败')
    raise SystemExit(1)

txt = raw.decode('utf-8', 'ignore')
m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(.*?)</script>', txt, re.S)
print(f'  页面 {len(txt)} 字符   __INITIAL_STATE__={"有" if m else "无"}')
if not m:
    print('  正文前 200:', repr(txt[:200]))
    raise SystemExit(1)

body = m.group(1)
print(f'  state 长度 {len(body)} 字符')
try:
    json.loads(body)
    print('  json.loads: ✅')
except Exception as e:
    print(f'  json.loads: ❌ {str(e)[:50]}')
if yaml:
    try:
        d = yaml.safe_load(body)
        print('  yaml.safe_load: ✅（开源项目用这个的原因就在这）')
    except Exception as e:
        print(f'  yaml.safe_load: ❌ {str(e)[:50]}')
        d = None

if d:
    note_root = d.get('note') or {}
    cid = note_root.get('currentNoteId')
    ndm = note_root.get('noteDetailMap') or {}
    print(f'\n  currentNoteId : {cid!r}')
    print(f'  noteDetailMap : {len(ndm)} 条')
    if str(cid) == 'undefined' or not ndm:
        print('  ⛔ 无笔记数据')
    else:
        for k, v in list(ndm.items())[:1]:
            n = v.get('note') or {}
            print(f'\n  ┌─ noteId {k}')
            print(f"  │ type    : {n.get('type')}")
            print(f"  │ title   : {str(n.get('title'))[:44]}")
            desc = str(n.get('desc') or '')
            print(f"  │ desc    : {desc[:60]}")
            u = n.get('user') or {}
            print(f"  │ author  : {u.get('nickname')}  ({u.get('userId')})")
            il = n.get('imageList') or []
            print(f"  │ imageList: {len(il)} 张")
            for i, im in enumerate(il[:3]):
                ud = str(im.get('urlDefault') or '')
                print(f"  │   [{i}] {ud[:78]}")
                print(f"  │       notes_pre_post={'notes_pre_post' in ud}"
                      f"  spectrum={'spectrum' in ud}")
                print(f"  │       livePhoto={im.get('livePhoto')}")
            vid = n.get('video') or {}
            print(f"  │ video keys: {sorted(vid.keys())}")
            if vid:
                st = (vid.get('media') or {}).get('stream') or {}
                print(f"  │   stream keys: {sorted(st.keys())}")
                h264 = st.get('h264') or []
                if h264:
                    print(f"  │   h264[0] masterUrl: "
                          f"{str(h264[0].get('masterUrl'))[:74]}")
                cons = vid.get('consumer') or {}
                if cons:
                    print(f"  │   consumer: {sorted(cons.keys())[:8]}")
