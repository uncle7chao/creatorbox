"""百度信息流视频解析器（mbd.baidu.com/newspage/data/videoshare）—— 纯 HTTP

来源与形态
----------
用户从「百度 APP」分享出来的视频短链：
    https://mr.baidu.com/r/<code>?...   → 302 → 
    https://mbd.baidu.com/newspage/data/videoshare?nid=sv_<vid>&...

⭐ 关键点：落地页是 **SSR 直出**的，HTML 里内嵌完整 videoInfo JSON：
    "videoInfo": {
      "play_url":  "https://vd3.bdstatic.com/.../mda-xxx.mp4",
      "duration":  "494",                ← 秒
      "vid":       "2325954398339771924",
      "posterImage": "http://f7.baidu.com/it/...",
      "title":     "...",
      "clarityArr": [ {key,title,rank,url}, ... ]   ← 多清晰度
    }

→ **零签名、零浏览器、零 Cookie**，与抖音/快手同构的纯 HTTP 通道。

⚠️ 与「好看视频」（haokan.baidu.com）是两个不同的产品：
   好看视频走 _format=json 接口；本解析器走信息流分享页 SSR。
   两者都是百度旗下但 URL 与接口形态完全不同，别混用。

⚠️ 短链 mr.baidu.com 必须先跟随 302 拿到 nid，否则拿不到 videoInfo。
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

# 分享短链（要跟随 302）与落地页
SHORT_HOST = 'mr.baidu.com'
LAND_HOSTS = ('mbd.baidu.com', 'mbd.baidu.cn')

# URL 提取：短链或落地页都算
URL_RE = re.compile(
    r'https?://(?:mr\.baidu\.com/r/[A-Za-z0-9]+'
    r'|mbd\.baidu\.(?:com|cn)/newspage/data/videoshare[^\s\'"<>]*)',
    re.IGNORECASE)

_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
       'AppleWebKit/605.1.15 (KHTML, like Gecko) '
       'Version/17.0 Mobile/15E148 Safari/604.1')

_TIMEOUT = 20


def _http_get(url: str, timeout: int = _TIMEOUT) -> tuple:
    """GET 一个 URL，返回 (status, body_text, final_url)。

    ⭐ 跟随重定向是必须的：mr.baidu.com 短链靠 302 跳到带 nid 的落地页。
    """
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        final_url = r.geturl()
        # 部分站点返回 gzip
        if r.headers.get('Content-Encoding', '').lower() == 'gzip':
            import gzip
            body = gzip.decompress(body)
        return r.status, body.decode('utf-8', 'ignore'), final_url


def _extract_json_obj(html: str, marker: str) -> Optional[Dict[str, Any]]:
    """从 HTML 里抠出某个 key 对应的完整 JSON 对象（括号配平法）。

    ⭐ 两个关键点：
      1) 不用正则 `.*?}`：嵌套 JSON 会在第一个 } 就截断。
         用括号配平才能拿到完整对象。
      2) 起点必须是 marker **之后紧邻的那个 {**（即 "key":{ 的 {），
         不能用 rfind('{', 0, marker_pos) —— 那会命中更外层对象的 {，
         抠出来是外层（实测抠到了 {"b":1} 而不是 videoInfo）。
    """
    i = html.find(marker)
    if i < 0:
        return None
    start = html.find('{', i + len(marker))
    if start < 0:
        return None
    depth = 0
    for j in range(start, len(html)):
        c = html[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:j + 1])
                except Exception:
                    return None
    return None


def _clarity_key(item: Dict[str, Any]) -> str:
    """档位标识：优先 key（1080p/sc/hd），回退 title。"""
    k = (item.get('key') or '').strip()
    if k:
        return k
    t = (item.get('title') or '').strip()
    return t or 'default'


def _height_of(key: str, item: Dict[str, Any],
               url: str = '') -> Optional[int]:
    """从档位 key / URL 路径 / height 字段推算高度。

    ⚠️ 百度 clarityArr 的 key 是 `1080p`/`sc`/`hd` 三种混用：
       只有 1080p 能从 key 直接读出数字，sc(超清)/hd(高清) 要看 URL 路径
       （`/1080p/`、`/sc/`、`/hd/`）—— 实测 sc 对应 720P、hd 对应 480P。
    ⚠️ 推不出来就返回 None —— 不编造。
    """
    m = re.search(r'(\d{3,4})p', key or '', re.IGNORECASE)
    if m:
        return int(m.group(1))
    # URL 路径里的档位目录
    m = re.search(r'/(\d{3,4}p|sc|hd|sd)/', url or '', re.IGNORECASE)
    if m:
        seg = m.group(1).lower()
        if seg.isdigit():
            return int(seg)
        # 百度清晰度目录的对应关系（实测：1080p/sc/hd/sd）
        return {'1080p': 1080, 'sc': 720, 'hd': 480, 'sd': 360}.get(seg)
    h = item.get('height')
    if h:
        try:
            return int(h)
        except (TypeError, ValueError):
            pass
    return None


class BaiduVideoPureParser:
    """纯 HTTP 百度信息流视频解析（实测直出 videoInfo，无需浏览器）"""

    name = 'baidu_pure'
    domains = ('mr.baidu.com', 'mbd.baidu.com', 'mbd.baidu.cn')

    @staticmethod
    def extract_url(text: str) -> str:
        m = URL_RE.search(text or '')
        return m.group(0) if m else ''

    def match(self, url: str) -> bool:
        u = (url or '').lower()
        return any(h in u for h in self.domains)

    async def parse(self, text: str, quality: str = '1080p') -> Dict[str, Any]:
        url = self.extract_url(text)
        if not url:
            return {'success': False, 'platform': 'baidu',
                    'error': '未识别到百度视频链接'}
        if not self.match(url):
            return {'success': False, 'platform': 'baidu',
                    'error': '不是百度视频链接'}

        try:
            status, html, final_url = await asyncio.to_thread(_http_get, url)
        except urllib.error.HTTPError as e:
            return {'success': False, 'platform': 'baidu',
                    'error': f'访问失败 HTTP {e.code}'}
        except Exception as e:
            return {'success': False, 'platform': 'baidu',
                    'error': f'访问失败: {str(e)[:80]}'}

        if status != 200 or not html:
            return {'success': False, 'platform': 'baidu',
                    'error': f'页面返回异常（HTTP {status}）'}

        vi = self._pick_video_info(html)
        if not vi:
            return {'success': False, 'platform': 'baidu',
                    'error': '页面里没有 videoInfo（可能是非视频页或已失效）'}

        return self._build_result(vi, quality, final_url)

    # ── 内部 ──────────────────────────────────────────────────────────
    @staticmethod
    def _pick_video_info(html: str) -> Optional[Dict[str, Any]]:
        """从页面里找 videoInfo 对象。

        ⭐ 直接抠 "videoInfo": 后紧邻的那个 { —— 它本身就是我们要的对象，
           不用再从外层包里取（之前那版依赖外层，实际会抠错）。
        """
        obj = _extract_json_obj(html, '"videoInfo":')
        if obj and ('play_url' in obj or 'clarityArr' in obj):
            return obj
        return None

    def _build_result(self, vi: Dict[str, Any], quality: str,
                      final_url: str) -> Dict[str, Any]:
        play_url = (vi.get('play_url') or '').strip()
        clarity = vi.get('clarityArr') or []

        options: List[Dict[str, Any]] = []
        for idx, item in enumerate(clarity):
            if not isinstance(item, dict):
                continue
            u = (item.get('url') or '').strip()
            if not u:
                continue
            key = _clarity_key(item)
            options.append({
                'index': idx,
                'gear': key,
                'width': item.get('width'),
                'height': _height_of(key, item, u),
                'bit_rate': None,
                # bdstatic 的 mp4 是源头文件，天然无水印
                'no_watermark': True,
                'url': u,
                'label': item.get('title') or key,
            })

        # clarityArr 为空时用 play_url 兜底
        if not options and play_url:
            options.append({
                'index': 0, 'gear': 'default', 'width': vi.get('width'),
                'height': _height_of('', {'height': vi.get('height')}, play_url),
                'bit_rate': None, 'no_watermark': True, 'url': play_url,
                'label': '默认',
            })
        if not options:
            return {'success': False, 'platform': 'baidu',
                    'error': '未取到可用视频地址'}

        # 选档：不低于 want_h 的最小档
        want = 1080
        m = re.search(r'(\d{3,4})', quality or '')
        if m:
            want = int(m.group(1))
        heights = [o['height'] or 0 for o in options]
        cand = [o for o in options if (o['height'] or 0) >= want]
        chosen = min(cand, key=lambda o: o['height'] or 0) if cand else \
            max(options, key=lambda o: o['height'] or 0)

        dur = vi.get('duration')
        try:
            dur_ms = int(float(dur) * 1000) if dur else 0
        except (TypeError, ValueError):
            dur_ms = 0

        return {
            'success': True,
            'platform': 'baidu',
            'method': 'pure_http(ssr)',
            'title': (vi.get('title') or '').strip(),
            'description': '',
            'author': '',
            'author_id': '',
            'author_avatar': '',
            'cover': (vi.get('posterImage') or '').strip(),
            'duration_ms': dur_ms,
            'type': 'video',
            'video_url': chosen['url'],
            'quality': f"{chosen['height']}P" if chosen.get('height') else
                       (chosen.get('label') or ''),
            'max_quality_free': f'{max(heights)}P' if heights else '',
            'options': options,
            'options_count': len(options),
            'dash': False,
            'need_proxy': True,     # bdstatic 带签名，需走封面/下载代理
            'anonymous': True,
            'no_watermark': True,
            'watermark_free': True,
            'vid': vi.get('vid') or '',
            'resource_type': vi.get('resourceType') or '',
            'page_url': final_url,
            'known_gaps': ['author: SSR 页面不下发作者名'],
        }
