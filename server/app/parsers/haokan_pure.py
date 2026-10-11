"""好看视频纯 HTTP 解析器 —— ⭐ 无需浏览器（知识库原先记为 browser，已修正）

来源：parse-video-py + video-parser 的haokan 实现（两者字段一致）
关键接口：
    GET https://haokan.baidu.com/v?_format=json&vid={vid}
    → data.apiData.curVideoMeta.clarityUrl[]  4 档，取 [-1] 最高
    → data.apiData.curVideoMeta.playurl/6s_play_url

⭐⭐ 本轮最重要的修正（2026-10-05）
──────────────────────────────────
知识库此前把好看视频标为 `engine: browser`，理由是「纯 HTTP 返回
errno:101007 =未过滑块验证」。**这个结论不准确。**

我这次把变量拆开单独测：只做「GET 首页拿 cookie → 带 cookie 打接口」，
**4/4 全部errno=0，1080P 完整文件全部可下载，不需要浏览器、不需要过滑块。**

| 做法 | 结果 |
|---|---|
| 无 cookie 直接打接口 | ❌ errno:101007 |
| **先 GET 首页拿 BAIDUID，再打接口** | ✅ **errno=0，4/4 全成功** |

也就是说：首页只是「种cookie」，**并没有触发滑块**。之前必须开浏览器，
是因为我在浏览器里顺手做了 goto 视频页（那一步才是滑块）。
真正必需的那一步是**访问一次首页**，纯 HTTP 就能做到。

⚠️ 结论修正的实际意义：好看视频从「必须常驻浏览器」降级为「纯 HTTP」，
   服务端内存结构不变（本来抖音/B站就已是纯 HTTP），但少了一个平台级
   浏览器依赖 —— 也说明 P2「接口报错≠平台不可用」连着坑了我两次。

⚠️ 仍然保留的约束：
  1. playurl URL **不能截断**（带 auth_key 签名，截断 → 403）→ P5
  2. URL 带 auth_key，**有时效**（实测形如 1791190576 ≈ 时间戳），
     不能长期缓存 → 见下方TTL 建议
  3. 清晰度 4 档固定顺序：cae_h264 / hd / sc / 1080p，[-1] 是 1080P
"""
from __future__ import annotations

import asyncio
import gzip
import http.cookiejar
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 '
         'Safari/537.36')

HOME = 'https://haokan.baidu.com/'
API_TMPL = 'https://haokan.baidu.com/v?_format=json&vid={vid}'
PAGE_TMPL = 'https://haokan.baidu.com/v?vid={vid}'

VID_RE = re.compile(r'vid=(\d{10,})')
# 路径形态兜底：/v/{19位数字}
PATH_VID_RE = re.compile(r'/v/(\d{15,})')
URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')

# ⚠️ P1 又一次应验：不要靠 URL 路径猜字段。
#    我最初按路径（cae_h264 / hd / sc / 1080p）反推清晰度，结果全标成 360P。
#    实际接口**已经给了权威字段**，根本不用猜：
#       title        = "蓝光 1080P"（平台自己的档位名，最可信）
#       vodVideoHW   = "1080$$1920"（高$$宽）
#       videoBps     = 码率 kbps
#       videoSize    = 体积 MB
#       rank= 0..3   = 档位序号（升序）
GEAR_FALLBACK = ['标清 360P', '高清 480P', '超清 720P', '蓝光 1080P']

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


class _Session:
    """带 cookie 的纯 HTTP 会话（进程内复用，避免每次都重取 cookie）"""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=_SSL))
        self._lock = threading.Lock()
        self._seeded_at = 0.0
        # cookie 有效期保守取 30 分钟；过期后重新访问首页
        self.ttl = 1800

    def _seed(self) -> None:
        """访问首页种 cookie（这一步是接口能通的关键，不能省）"""
        req = urllib.request.Request(HOME, headers={
            'User-Agent': PC_UA,
            'Accept': 'text/html,application/xhtml+xml,*/*',
            'Accept-Encoding': 'gzip, deflate',
        })
        with self.opener.open(req, timeout=20) as r:
            r.read(2048)
        self._seeded_at = time.time()

    def ensure_cookie(self) -> None:
        with self._lock:
            if not self._seeded_at or \
                    time.time() - self._seeded_at > self.ttl:
                self._seed()

    def get(self, url: str, referer: str = '',
            timeout: int = 20) -> bytes:
        self.ensure_cookie()
        headers = {
            'User-Agent': PC_UA,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
        }
        if referer:
            headers['Referer'] = referer
        with self.opener.open(
                urllib.request.Request(url, headers=headers),
                timeout=timeout) as r:
            raw = r.read()
        if raw[:2] == b'\x1f\x8b':        # P7
            raw = gzip.decompress(raw)
        return raw

    def probe_size(self, url: str, referer: str = '',
                   timeout: int = 20) -> Optional[int]:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': PC_UA, 'Referer': referer,
                'Range': 'bytes=0-1'})
            with self.opener.open(req, timeout=timeout) as r:
                cr = r.headers.get('Content-Range') or ''
            if '/' in cr:
                tail = cr.rsplit('/', 1)[-1].strip()
                if tail.isdigit():
                    return int(tail)
        except Exception:
            pass
        return None


_SESSION = _Session()


def extract_vid(url: str) -> str:
    m = VID_RE.search(url)
    if m:
        return m.group(1)
    m = PATH_VID_RE.search(url)
    if m:
        return m.group(1)
    return ''


def _unescape(u: str) -> str:
    """页面里URL 是 JSON 转义 + 可能带 \\/ ，必须还原（否则签名失效）"""
    if not u:
        return ''
    out = u.replace('\\/', '/').replace('\\u002F', '/')
    out = out.replace('\\u0026', '&').replace('&amp;', '&')
    return urllib.parse.unquote(out) if '%' in out else out


def _gear_of(item: Dict[str, Any], url: str, idx: int) -> str:
    """档位名优先取平台自带的 title，其次按 rank 兜底"""
    t = str(item.get('title') or '').strip()
    if t:
        return t
    if '1080p/' in url:
        return '蓝光 1080P'
    if '/sc/' in url:
        return '超清 720P'
    if '/576p/' in url or '/hd/' in url:
        return '高清 480P'
    return GEAR_FALLBACK[idx] if idx < len(GEAR_FALLBACK) else f'档{idx}'


def _hw_of(item: Dict[str, Any]) -> tuple:
    """vodVideoHW 形如 "1080$$1920"（高$$宽），竖屏视频宽>高"""
    s = str(item.get('vodVideoHW') or '')
    m = re.match(r'^(\d+)\$\$(\d+)$', s)
    if not m:
        return None, None
    h, w = int(m.group(1)), int(m.group(2))
    return (w, h) if w >= h else (h, w)   # 统一成 (宽, 高)


def _parse_sync(vid: str) -> Dict[str, Any]:
    referer = PAGE_TMPL.format(vid=vid)
    try:
        raw = _SESSION.get(API_TMPL.format(vid=vid), referer=referer)
    except Exception as e:
        return {'success': False, 'platform': 'haokan',
                'error': f'好看视频接口请求失败: {str(e)[:70]}'}

    try:
        j = json.loads(raw.decode('utf-8', 'ignore'))
    except Exception as e:
        return {'success': False, 'platform': 'haokan',
                'error': f'响应非 JSON: {str(e)[:60]}'}

    errno = j.get('errno')
    if errno != 0:
        # 走到这里通常意味着会话 cookie 没种上，重置一次再试
        _SESSION._seeded_at = 0.0
        return {'success': False, 'platform': 'haokan',
                'error': f'好看视频返回 errno={errno} '
                         f'{j.get("error", "")[:40]}',
                'hint': '会话 cookie 可能过期，服务端会自动重置'}

    api = ((j.get('data') or {}).get('apiData') or {})
    cur = api.get('curVideoMeta') or {}
    if not cur:
        return {'success': False, 'platform': 'haokan',
                'error': 'errno=0 但 curVideoMeta 为空（内容可能已下架）'}

    options: List[Dict[str, Any]] = []
    # 按 rank 升序（实测 rank 就是清晰度档位序号 0..3）
    raw_items = [it for it in (cur.get('clarityUrl') or [])
                 if isinstance(it, dict) and it.get('url')]
    raw_items.sort(key=lambda it: it.get('rank', 99))

    for item in raw_items:
        u = _unescape(item.get('url') or '')
        if not u:
            continue
        idx = len(options)
        w, h = _hw_of(item)
        # 体积：优先接口给的 videoSize(MB)，否则 Range 探真实值
        size_mb = item.get('videoSize')
        size = int(size_mb * 1048576) if size_mb else \
            _SESSION.probe_size(u, referer=referer)
        options.append({
            'index': idx,
            'gear': _gear_of(item, u, idx),
            'width': w,
            'height': h,
            'bit_rate': item.get('videoBps'),
            'size': size,
            'no_watermark': True,
            'url': u,                # ⚠️ P5：完整传递，不截断
        })

    if not options:
        return {'success': False, 'platform': 'haokan',
                'error': 'clarityUrl 为空（该视频可能无免费清晰度）'}

    # 取最高档（clarityUrl 固定按清晰度升序）
    best = options[-1]
    best_url = best['url'] or ''
    if not best_url:
        best_url = _unescape(cur.get('playurl') or
                             cur.get('6s_play_url') or '')

    return {
        'success': True,
        'platform': 'haokan',
        'method': 'pure_http_json',
        'type': 'video',
        'vid': cur.get('id') or vid,
        'title': cur.get('title') or '',
        # ⚠️ 实测：_format=json 的 curVideoMeta 里**没有作者字段**
        #   （遍历了全部 30 个 key，没有 author/user_name/uname）
        #   SSR 的 __PRELOADED_STATE__ 里 uname 也是空串（游客态）
        #   → 只能返回空字符串，不要编造
        'author': '',
        'cover': _unescape(cur.get('poster') or ''),
        'publish_time_ts': cur.get('publish_time'),   # Unix 秒
        'play_count': cur.get('playcnt'),
        'view_count': cur.get('playcnt'),
        'like_count': cur.get('like'),
        'comment_count': cur.get('comment') or cur.get('fmcomment_num'),
        # 展示文本（接口直接给的原文，比自己换算更贴近平台显示）
        'date_text': cur.get('date') or '',
        'play_count_text': cur.get('fmplaycnt') or '',
        'is_long_video': bool(cur.get('isLongVideo')),
        'video_url': best_url,
        'quality': best['gear'],
        'duration_ms': int((cur.get('duration') or 0) * 1000),
        'size': best.get('size'),
        'options': options,
        'options_count': len(options),
        'dash': False,                  # mp4 单文件
        'need_proxy': True,             # vdept*.bdstatic.com 带签名，不适合白名单
        'anonymous': True,
        'no_watermark': True,
        'watermark_free': True,
        'url_expiry_note': ('playurl 带 auth_key 签名且有时效，'
                            '不可长期缓存；建议缓存 TTL ≤ 10 分钟'),
        'cache_ttl_hint': 600,
        'known_gaps': ['author: 接口不下发作者名（游客态）'],
    }


class HaokanPureParser:
    """纯 HTTP 好看视频解析 —— 已实测 4/4 成功，不需要浏览器"""

    name = 'haokan_pure'
    domains = ('haokan.baidu.com', 'haokan.hao123.com')

    @staticmethod
    def extract_url(text: str) -> str:
        m = URL_RE.search(text or '')
        return m.group(0) if m else ''

    def match(self, url: str) -> bool:
        return 'haokan.baidu.com' in url or 'haokan.hao123.com' in url

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        url = self.extract_url(text)
        if not url:
            return {'success': False, 'platform': 'haokan',
                    'error': '未识别到链接'}
        if not self.match(url):
            return {'success': False, 'platform': 'haokan',
                    'error': '不是好看视频链接'}
        vid = extract_vid(url)
        if not vid:
            return {'success': False, 'platform': 'haokan',
                    'error': f'未能从链接提取 vid: {url[:60]}',
                    'hint': '好看视频链接应含 vid=19位数字'}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _parse_sync(vid))

    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'pure_http_json',
                'note': '纯 HTTP（首页取 cookie + _format=json），无需浏览器'}


if __name__ == '__main__':
    import sys
    import time

    async def _main():
        samples = sys.argv[1:] or [
            'https://haokan.baidu.com/v?vid=1688233510589355861',
            'https://haokan.baidu.com/v?vid=1615713059572946930',
            'https://haokan.baidu.com/v?vid=1891980261675370327',
            'https://haokan.baidu.com/v?vid=16481085785828018426',
        ]
        p = HaokanPureParser()
        ok = 0
        for s in samples:
            t0 = time.time()
            r = await p.parse(s)
            good = r.get('success')
            ok += bool(good)
            print(f"\n--- {s[:58]}{time.time() - t0:.2f}s")
            print(f"  success     : {good}")
            for k in ('vid', 'title', 'author', 'quality', 'options_count',
                      'duration_ms', 'size', 'need_proxy', 'anonymous'):
                if k in r:
                    print(f'  {k:12s}: {str(r[k])[:56]}')
            if good:
                for o in r.get('options', []):
                    sz = o.get('size')
                    print(f"    [{o['index']}] {o['gear']:8s} "
                          f"{sz / 1048576:.2f}MB" if sz else
                          f"    [{o['index']}] {o['gear']:8s} ?")
                print('  url         :', (r.get('video_url') or '')[:96])
            else:
                print('  error       :', r.get('error'))
        print(f'\n可用 {ok}/{len(samples)}')

    asyncio.run(_main())
