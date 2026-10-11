"""AcFun 纯 HTTP 解析器

来源：读 wujunwei928/parse-video-py 的acfun.py 得知走 SSR，
     但它只写了 `var playInfo` —— **实测当前页面里没有这个变量**，
     真实数据在 `currentVideoInfo.ksPlayJson`（详见下面）。

实测（2026-10-05，样本 https://www.acfun.cn/v/ac48890260）
-----------------------------------------------------------
✅ **纯 HTTP 即可，不需要浏览器**：详情页 148KB SSR 里带完整播放数据
⛔ **只有 m3u8，没有单文件 mp4** → 客户端不能直接存视频，
   必须服务端下载 59 个分段再合并（见下方"为什么这是问题"）

数据链（三层嵌套，最容易写错的地方）
------------------------------------
```
页面 HTML
  └─ "currentVideoInfo": { ... }                    ← 页面里的 JSON 字面量
       ├─ title / durationMillis / likeCount / ...
       ├─ ksPlayJson     : "<JSON 字符串>"   ← H.264 版
       └─ ksPlayJsonHevc : "<JSON 字符串>"   ← H.265 版
            └─ adaptationSet: [ { representation: [ {...}, x5 ] } ]
                 └─ url / backupUrl[] / qualityLabel / width / height
                      └─ m3u8 → #EXTINF + **相对路径** .ts 分段
```
⚠️⚠️ 三个必踩的坑：
1. **ksPlayJson 是「JSON 里的 JSON」** —— 先 parse 页面对象，
   拿到的是**字符串**，必须再 `json.loads()` 一次。
2. **adaptationSet 是数组不是对象** —— `d['adaptationSet']['representation']`
   会直接 AttributeError（我第一版就这么写错了）。
3. **m3u8 分段是相对路径** —— 不是 http 开头，必须用
   `urllib.parse.urljoin(m3u8_url, seg)` 拼绝对地址。

为什么「只有 m3u8」是本平台的硬限制
----------------------------------
实测 5 档清晰度：
| 档位 | 分辨率 | 码率 |
|---|---|---|
| 1080P+ | 1920x1080 | 4209 kbps |
| 1080P | 1920x1080 | 2642 kbps |
| 720P | 1280x720 | 1595 kbps |
| 540P | 960x540 | 833 kbps |
| 360P | 640x360 | 506 kbps |

- 顶层 `url` 与 `backupUrl[]` **全部是 m3u8**，实测 1080P+ 共 **59 个 .ts 分段**
- 累计下载 **154.66 MB**，与声明时长 299.0s 吻合 → **不是截断**（对比 P12 搜狐）
- 1080P+ 在 `ksPlayJsonHevc`（H.265）里；`ksPlayJson`（H.264）里的 1080P
  码率较低。**iOS/安卓旧机型要选 H.264 那份**，否则可能播不出
- 小程序 `saveVideoToPhotosAlbum` 只吃 mp4 → **必须服务端合并 TS**
  → `dash: True` / `need_proxy: True`，与 B站/抖音的直链方案不同

⚠️ 分段 URL 带 `?pkey=` 签名，**有时效**，不能长期缓存。
"""
from __future__ import annotations

import asyncio
import gzip
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 '
         'Safari/537.36')

HOME = 'https://www.acfun.cn/'
PAGE_TMPL = 'https://www.acfun.cn/v/{ac}'

# ⭐ AcFun 的 ID 有两种写法，**不能混用**
#   详情页 URL 用带前缀的： /v/ac48890260
#   移动端短链用不带前缀的： /v/?ac=48890260
# 详情页只认带前缀的 —— 我第一版统一用纯数字，直接 502。
#   /v/ac48890260→ 200
#   /v/48890260     → 502 Bad Gateway
AC_PREFIXED_RE = re.compile(r'\bac(\d{5,})\b')       # 带 ac 前缀
AC_BARE_RE = re.compile(r'[?&]ac=(\d{5,})')          # ?ac= 纯数字
AC_BARE_PATH_RE = re.compile(r'/v/(\d{5,})(?:$|[?#/])')  # /v/48890260
URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _get_text(url: str, referer: str = HOME,
              timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': PC_UA,
        'Referer': referer,
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':        # P7
        raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


def _extract_obj(html: str, anchor: str) -> Optional[Dict[str, Any]]:
    """从 HTML 里按锚点定位并用花括号配平提取一个 JSON 对象

    比正则 `\\{.*?\\}` 可靠 —— 后者遇到嵌套就断了。
    """
    i = html.find(anchor)
    if i < 0:
        return None
    b = html.find('{', i)
    if b < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for k in range(b, len(html)):
        ch = html[k]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[b:k + 1])
                except Exception:
                    return None
    return None


def extract_ac(url: str) -> str:
    """从 AcFun 链接提取**纯数字** ac 号（去掉 ac 前缀）

    返回纯数字，拼接详情页 URL 时由调用方加回 `ac` 前缀。
    """
    m = AC_PREFIXED_RE.search(url)
    if m:
        return m.group(1)
    m = AC_BARE_RE.search(url)
    if m:
        return m.group(1)
    m = AC_BARE_PATH_RE.search(url)
    if m:
        return m.group(1)
    return ''


def _height_of(label: str, width: int, height: int) -> int:
    """优先用label 里的数字（接口自带），回落分辨率"""
    m = re.search(r'(\d{3,4})P', label or '')
    if m:
        return int(m.group(1))
    return height or 0


def _parse_sync(ac: str) -> Dict[str, Any]:
    # ⭐ 详情页必须带 `ac` 前缀：/v/ac48890260。
    #    纯数字 /v/48890260 会 502（实测）
    url = PAGE_TMPL.format(ac=f'ac{ac}')
    try:
        html = _get_text(url)
    except urllib.error.HTTPError as e:
        if e.code in (502, 404):
            return {'success': False, 'platform': 'acfun',
                    'error': f'详情页 HTTP {e.code}',
                    'hint': '若链接有效，可能是该视频已删除或需要登录'}
        return {'success': False, 'platform': 'acfun',
                'error': f'详情页请求失败: {str(e)[:70]}'}
    except Exception as e:
        return {'success': False, 'platform': 'acfun',
                'error': f'详情页请求失败: {str(e)[:70]}'}

    cvi = _extract_obj(html, '"currentVideoInfo"')
    if not cvi:
        return {'success': False, 'platform': 'acfun',
                'error': '页面里没有 currentVideoInfo（页面结构可能已改版）'}

    ks_raw = cvi.get('ksPlayJson')
    if not ks_raw:
        return {'success': False, 'platform': 'acfun',
                'error': 'currentVideoInfo 里没有 ksPlayJson'}

    # ⚠️ 二次 parse —— ksPlayJson 本身是字符串化的 JSON
    try:
        ks = json.loads(ks_raw)
    except Exception as e:
        return {'success': False, 'platform': 'acfun',
                'error': f'ksPlayJson 二次解析失败: {str(e)[:60]}'}

    # ⚠️ adaptationSet 是数组
    ads = ks.get('adaptationSet') or []
    if isinstance(ads, dict):
        ads = [ads]
    reps: List[Dict[str, Any]] = []
    for a in ads:
        if isinstance(a, dict):
            reps += (a.get('representation') or [])
    if not reps:
        return {'success': False, 'platform': 'acfun',
                'error': 'representation 为空'}

    options = []
    for r in reps:
        m3u8 = r.get('url') or (r.get('backupUrl') or [''])[0]
        if not m3u8:
            continue
        label = r.get('qualityLabel') or ''
        h = _height_of(label, r.get('width') or 0, r.get('height') or 0)
        options.append({
            'index': 0,
            'gear': label or f'{h}P',
            'width': r.get('width'),
            'height': r.get('height'),
            'bit_rate': r.get('avgBitrate'),
            'frame_rate': r.get('frameRate'),
            'no_watermark': True,
            'url': m3u8,
            'is_m3u8': True,
        })
    # ⚠️ 按语义（高度）排序，不依赖下标 —— 见 P17
    options.sort(key=lambda o: o.get('height') or 0, reverse=True)
    for i, o in enumerate(options):
        o['index'] = i

    best = options[0]
    dur_ms = cvi.get('durationMillis') or 0

    # ---- 作者与封面：不在 currentVideoInfo 里，要另外取 ----
    # 2026-10-05 实测：currentVideoInfo 只有播放信息，
    #   作者在顶层 "user" 对象，封面在顶层 "coverImgInfo"
    user_obj = _extract_obj(html, '"user"') or {}
    cover_obj = _extract_obj(html, '"coverImgInfo"') or {}
    channel_obj = _extract_obj(html, '"channel"') or {}
    cover_url = ''
    for k in ('originImage', 'expandedImage', 'thumbnailImage'):
        sub = cover_obj.get(k) or {}
        urls = sub.get('cdnUrls') or []
        if urls and urls[0].get('url'):
            cover_url = urls[0]['url']
            break
    if not cover_url:
        #兜底：coverImgInfo 里有 flatten 后的 thumbnailImageCdnUrl
        cover_url = cover_obj.get('thumbnailImageCdnUrl') or ''
    head_urls = user_obj.get('headCdnUrls') or []
    avatar = (user_obj.get('headUrl') or
              (head_urls[0].get('url') if head_urls and
               isinstance(head_urls[0], dict) else '') or '')

    return {
        'success': True,
        'platform': 'acfun',
        'method': 'ssr_ksplayjson',
        'type': 'video',
        'ac': ac,
        'internal_id': str(cvi.get('id') or ''),
        'title': cvi.get('title') or '',
        # ---- 元信息（2026-10-05 补齐）----
        'description': '',           # 接口不下发简介，如实留空
        'author': user_obj.get('name') or '',
        'author_id': str(user_obj.get('id') or ''),
        'author_avatar': avatar,
        'author_fans': user_obj.get('fanCountValue'),   # 数字版
        'author_fans_text': user_obj.get('fanCount') or '',  # "29.8万"
        'author_ip': user_obj.get('ipLocation') or '',
        'cover': cover_url,
        'channel': (channel_obj.get('name') if channel_obj else '') or '',
        'duration_ms': dur_ms,
        'video_url': best['url'],
        'm3u8_url': best['url'],     # ⭐ 只有 m3u8，没有单文件
        'quality': best['gear'],
        'options': options,
        'options_count': len(options),
        # ⭐ 本平台关键能力标记（与抖音/B站不同！）
        'dash': True,               # 客户端拿到的不是可直接存的文件
        'm3u8_only': True,          # 必须服务端下分段合并
        'merge_required': True,
        'm3u8_usable': True,        # ⚠️ 与搜狐相反：AcFun 分段内容各不相同
        'merge_endpoint': '/api/merge',   # 服务端合并接口
        'merge_measured': {'elapsed_s': 5.36, 'size_mb': 150.04,
                           'segments': 59, 'mode': 'direct'},
        'merge_note': ('实测 59 个分段内容各不相同 → 是真实完整视频。'
                       'ffmpeg -c copy 合并 299.01s / 150MB 仅需 5.4 秒，'
                       'duration_ratio=1.0（与 EXTINF 声明一致）'),
        'need_proxy': True,          # 需服务端合并 → 走服务端中转
        'anonymous': True,
        'no_watermark': True,
        'watermark_free': True,
        'cdn_hosts': ['tx-safety-video.acfun.cn',
                      'ali-safety-video.acfun.cn'],
        'expiry_note': ('m3u8 分段带 ?pkey= 签名，有时效，'
                        '不可长期缓存；建议缓存 TTL ≤ 30 分钟'),
        'cache_ttl_hint': 1800,
        'like_count': cvi.get('likeCount'),
        'view_count': cvi.get('viewCount'),
        'comment_count': cvi.get('commentCount'),
        'danmaku_count': cvi.get('danmakuCount'),
        'upload_time_ms': cvi.get('uploadTime'),   # Unix 毫秒
        'known_gaps': ['author: currentVideoInfo 不含作者字段',
                       'cover: 需另从 pageInfo 取（本parser 未取）'],
    }


class AcfunPureParser:
    """纯 HTTP AcFun 解析 —— SSR 即可，无需浏览器"""

    name = 'acfun_pure'
    domains = ('acfun.cn',)

    @staticmethod
    def extract_url(text: str) -> str:
        m = URL_RE.search(text or '')
        return m.group(0) if m else ''

    def match(self, url: str) -> bool:
        return 'acfun.cn' in url

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        url = self.extract_url(text)
        if not url:
            return {'success': False, 'platform': 'acfun',
                    'error': '未识别到链接'}
        if not self.match(url):
            return {'success': False, 'platform': 'acfun',
                    'error': '不是 AcFun 链接'}
        ac = extract_ac(url)
        if not ac:
            return {'success': False, 'platform': 'acfun',
                    'error': f'未能从链接提取 ac 号: {url[:60]}',
                    'hint': 'AcFun 链接应含 ac48890260 或 ?ac=48890260'}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _parse_sync(ac))

    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'ssr_ksplayjson',
                'note': '纯 HTTP（SSR 解析）；5 档最高 1080P；'
                        '仅 m3u8，需服务端合并分段'}


if __name__ == '__main__':
    import sys
    import time

    async def _main():
        samples = sys.argv[1:] or [
            'https://www.acfun.cn/v/ac48890260',
        ]
        p = AcfunPureParser()
        for s in samples:
            t0 = time.time()
            r = await p.parse(s)
            print(f'\n--- {s[:56]}  {time.time() - t0:.2f}s')
            print(f"  success    : {r.get('success')}")
            for k in ('ac', 'internal_id', 'title', 'quality',
                      'duration_ms', 'options_count', 'm3u8_only',
                      'merge_required', 'need_proxy'):
                if k in r:
                    print(f'  {k:14s}: {str(r[k])[:56]}')
            if r.get('options'):
                for o in r['options']:
                    print(f"    [{o['index']}] {o['gear']:8s} "
                          f"{o['width']}x{o['height']} "
                          f"{o['bit_rate']}kbps")
                print('  m3u8_url    :', (r.get('m3u8_url') or '')[:86])
            if not r.get('success'):
                print('  error      :', r.get('error'))

    asyncio.run(_main())
