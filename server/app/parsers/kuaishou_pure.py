"""快手纯 HTTP 解析器

⭐ 突破口：主站 www.kuaishou.com 的 GraphQL 被反爬滑块拦死，
   但**另一个域名 m.gifshow.com 完全不拦**（gifshow 是快手最早的品牌名）。

2026-10-05 实测证据链（分离变量，每一步都排除了技术问题）：

| 尝试 | 结果 |
|---|---|
| www.kuaishou.com 短链 → /short-video/{workId} | 302 ✅ 拿到 workId |
| 最终页面 | 仅 82 字节 `{"result":2}` → 完全 CSR |
| 4 种 UA（PC/iOS/Android/微信）× 3 个 workId | **全部 result=400002 + captcha** |
| → 拦截发生在 workId 校验**之前**，与内容/UA 无关 |
| ⭐ **m.gifshow.com/fw/photo/{workId}** | **200 / 98-163KB / INIT_STATE 完整** |

→ 反爬只针对主站，m.gifshow.com 这条路完全畅通，且是**纯 HTTP + 零浏览器**。

【数据链】
短链 /f/{token}
  → 302 Location 取 shareObjectId（= workId，形如 3xy2kubupu94q74）
  → GET https://m.gifshow.com/fw/photo/{workId}   （iOS UA）
  → window.INIT_STATE（⚠️ 顶层 key 被混淆，但内层 result/photo 正常）
  → 找 result==1 的节点 → .photo
  → mainMvUrls[0].url  ⭐ 无水印（抽帧确认）

【字段陷阱】
- INIT_STATE 顶层只有 2 个 key，且**都被混淆过**（乱码-like），
  不能按 key 名找 → 必须遍历找「含 result+photo 的 dict」
- `duration` 单位是**毫秒**（13100 = 13.1s）
- `mainMvUrls[0]` 与 `[1]` 可能是**同一条**（cdn+url 完全相同），
  去重后再报档位数，否则会虚报
- CDN 域名每个作品不同（tymov2 / txmov2 / ... .a.kwimgs.com）
  → 白名单要用通配 `*.kwimgs.com`
"""
from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# 直接 `python app/parsers/kuaishou_pure.py` 运行时补上包上下文
if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    __package__ = 'app.parsers'

from .base import BaseParser

# ── 常量 ──
IOS_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 '
          'Mobile/15E148 Safari/604.1')
PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
HOME = 'https://www.kuaishou.com/'

# ⭐ 突破口域名（不是 www）
GIFSHOW_PAGE = 'https://m.gifshow.com/fw/photo/{work_id}'

URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')
# 短链 kuaishou.com/f/{token}
SHORT_RE = re.compile(r'kuaishou\.com/f/([A-Za-z0-9\-_]+)')
# workId：字母数字混合，14-20 位（3xy2kubupu94q74 / 3xha63juacrpw69）
WORK_ID_RE = re.compile(r'\b(3[a-z0-9]{10,20})\b', re.I)
# location 里的 shareObjectId 最可靠
SHARE_OBJ_RE = re.compile(r'shareObjectId=([A-Za-z0-9\-_]+)')
PHOTO_ID_RE = re.compile(r'\b(\d{15,22})\b')

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


# ── HTTP ──
def _get(url: str, referer: str = '', ua: str = IOS_UA,
         timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Language': 'zh-CN,zh;q=9',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': referer or HOME,
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':          # P7
        raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


def _get_no_redirect(url: str, ua: str = IOS_UA,
                     timeout: int = 20) -> str:
    """不跟随重定向，只读 Location（拿 workId 用）"""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    try:
        opener.open(req, timeout=timeout)
        return url
    except urllib.error.HTTPError as e:
        loc = (e.headers or {}).get('Location') or ''
        return loc or url
    except Exception:
        return url


def _https(u: str) -> str:
    if not u:
        return ''
    s = str(u).replace('\\u002F', '/').replace('\\/', '/')
    if s.startswith('//'):
        return 'https:' + s
    return s


# ── ID 提取 ──
def extract_work_id(text: str) -> str:
    """从任意快手链接/文案提取 workId

    顺序：直接匹配 workId 形态 → location 的 shareObjectId → 短链先 302
    """
    m = WORK_ID_RE.search(text or '')
    if m:
        return m.group(1)
    m = SHARE_OBJ_RE.search(text or '')
    if m:
        return m.group(1)
    m = re.search(r'/short-video/([A-Za-z0-9\-_]+)', text or '')
    if m:
        return m.group(1)
    return ''


async def resolve_work_id(url: str) -> str:
    """短链 → workId（跟随一次 302）"""
    m = SHORT_RE.search(url or '')
    if not m:
        return extract_work_id(url)
    loc = await asyncio.get_event_loop().run_in_executor(
        None, _get_no_redirect, url)
    return extract_work_id(loc) or ''


# ── INIT_STATE 解析 ──
def _extract_init_state(html: str) -> Optional[Dict[str, Any]]:
    """取 window.INIT_STATE 并做花括号配平

    ⚠️ 不能用正则 `\\{.*\\}` —— 字符串里含转义引号与花括号。
    ⚠️ 顶层 key 被混淆，所以后面要遍历找节点，不能按 key 名取。
    """
    key = 'window.INIT_STATE = '
    i = html.find(key)
    if i < 0:
        return None
    i += len(key)
    depth = 0
    end = 0
    in_str = False
    esc = False
    for k in range(i, len(html)):
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
                end = k + 1
                break
    if not end:
        return None
    try:
        return json.loads(html[i:end])
    except json.JSONDecodeError:
        return None


def _find_photo_node(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """在 INIT_STATE 里找「result==1 且含 photo」的节点

    ⚠️ 顶层 key 被混淆（形如 tusjoh.0sftu0{...}）→ 只能按**结构**找。
    """
    for v in state.values():
        if not isinstance(v, dict):
            continue
        if 'photo' in v and isinstance(v.get('photo'), dict):
            if v.get('result') == 1:
                return v
    # 退化：只要有 photo 就算（实测 result 恒为 1）
    for v in state.values():
        if isinstance(v, dict) and isinstance(v.get('photo'), dict):
            return v
    return None


def _pick_image_url(item: Any) -> str:
    """图集项取url（原样，暂不换域名—— 需实测水印）"""
    if isinstance(item, str):
        return _https(item)
    if isinstance(item, dict):
        return _https(item.get('url') or item.get('urlList') or '')
    return ''


# ── 主解析 ──
def _parse_sync(work_id: str, quality: str = '1080p') -> Dict[str, Any]:
    url = GIFSHOW_PAGE.format(work_id=work_id)
    try:
        html = _get(url)
    except urllib.error.HTTPError as e:
        return {'success': False, 'platform': 'kuaishou',
                'error': f'm.gifshow.com HTTP {e.code}',
                'work_id': work_id}
    except Exception as e:
        return {'success': False, 'platform': 'kuaishou',
                'error': f'页面请求失败: {str(e)[:70]}',
                'work_id': work_id}

    state = _extract_init_state(html)
    if not state:
        return {'success': False, 'platform': 'kuaishou',
                'error': '页面里没有 window.INIT_STATE（结构可能已改版）',
                'work_id': work_id}

    node = _find_photo_node(state)
    if not node:
        return {'success': False, 'platform': 'kuaishou',
                'error': 'INIT_STATE 里没有 photo 节点',
                'work_id': work_id,
                'state_keys': len(state)}

    p = node['photo']

    # ---- 视频地址：mainMvUrls 去重 ----
    raw_mv = p.get('mainMvUrls') or []
    seen = set()
    mvs: List[Dict[str, Any]] = []
    for m in raw_mv:
        u = _https(m.get('url') if isinstance(m, dict) else m)
        if not u or u in seen:
            continue
        seen.add(u)
        mvs.append({'url': u,
                    'cdn': m.get('cdn') if isinstance(m, dict) else ''})
    video_url = mvs[0]['url'] if mvs else ''

    # ---- 高清备选：manifest.adaptationSet[].representation[] ----
    mf = p.get('manifest') or {}
    ads = mf.get('adaptationSet')
    if isinstance(ads, dict):
        ads = [ads]
    options: List[Dict[str, Any]] = []
    for m in mvs:
        options.append({'index': len(options),
                        'gear': '主地址',
                        'cdn': m['cdn'],
                        'no_watermark': True,
                        'url': m['url']})
    for a in (ads or []):
        for r in (a.get('representation') or []):
            u = _https(r.get('url') or '')
            if not u or any(o['url'] == u for o in options):
                continue
            options.append({
                'index': len(options),
                'gear': f"{r.get('width')}x{r.get('height')}"
                        f"rep{r.get('id')}",
                'width': r.get('width'),
                'height': r.get('height'),
                'cdn': urllib.parse.urlparse(u).netloc,
                'no_watermark': True,
                'url': u,
            })
    if not video_url and options:
        video_url = options[0]['url']

    # ---- 图集 ----
    atlas = ((p.get('ext_params') or {}).get('atlas') or {})
    images: List[Dict[str, Any]] = []
    if isinstance(atlas, dict):
        cdn = atlas.get('cdn') or []
        prefix = _https(cdn[0]) if cdn else ''
        for it in (atlas.get('list') or []):
            raw = _pick_image_url(it)
            if not raw:
                continue
            # list 里常是相对路径
            if prefix and not raw.startswith('http'):
                raw = prefix.rstrip('/') + '/' + raw.lstrip('/')
            images.append({'url': raw, 'format': 'jpeg'})
    image_count = len(images)

    # ---- 封面 ----
    cover = ''
    for c in (p.get('coverUrls') or []):
        if isinstance(c, dict) and c.get('url'):
            cover = _https(c['url'])
            break

    is_video = bool(video_url)
    dur_ms = p.get('duration') or 0

    return {
        'success': True,
        'platform': 'kuaishou',
        'method': 'm_gifshow_ssr',
        'type': 'video' if is_video else ('image' if images
                                          else 'unknown'),
        'work_id': work_id,
        'photo_id': str(p.get('photoId') or ''),
        # ---- 元信息 ----
        'title': (p.get('caption') or '').strip(),
        'description': (p.get('caption') or '').strip(),
        'author': p.get('userName') or '',
        'author_id': str(p.get('kwaiId') or ''),
        'author_avatar': _https(p.get('headUrl') or ''),
        'cover': cover,
        'duration_ms': dur_ms,
        'publish_time_ms': p.get('timestamp'),
        'like_count': p.get('likeCount'),
        'comment_count': p.get('commentCount'),
        'share_count': p.get('forwardCount'),
        'view_count': p.get('viewCount'),
        'width': p.get('width'),
        'height': p.get('height'),
        # ---- 媒体 ----
        'video_url': video_url,
        'options': options,
        'options_count': len(options),
        'images': images,
        'image_count': image_count,
        'cdn_hosts': sorted({o['cdn'] for o in options if o.get('cdn')}),
        # ---- 能力标记 ----
        'need_proxy': True,       # kwimgs.com 域名每个作品不同
        'anonymous': True,        # 游客态可读（实测）
        'no_watermark': True,     # mainMvUrls 抽帧确认无水印
        'watermark_free': True,
        'entry_note': ('⭐ 走 m.gifshow.com 而非 www.kuaishou.com —— '
                       '主站 GraphQL 有反爬滑块（result=400002）'),
        'cache_ttl_hint': 1800,
    }


class KuaishouPureParser(BaseParser):
    name = 'kuaishou_pure'
    domains = ('kuaishou.com', 'gifshow.com', 'chenzhongtech.com')

    def match(self, url: str) -> bool:
        return any(d in (url or '') for d in self.domains)

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        m = URL_RE.search(text or '')
        url = m.group(0) if m else (text or '')
        if not url:
            return {'success': False, 'platform': 'kuaishou',
                    'error': '未识别到快手链接'}

        work_id = await resolve_work_id(url)
        if not work_id:
            return {'success': False, 'platform': 'kuaishou',
                    'error': '未能从链接提取 workId',
                    'hint': '快手短链形如 kuaishou.com/f/{token}，'
                            '需先 302 拿 shareObjectId'}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _parse_sync, work_id, quality)

    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'm_gifshow_ssr',
                'note': '纯 HTTP，走 m.gifshow.com 绕开主站反爬'}


if __name__ == '__main__':
    import time

    SAMPLES = [
        ('竖屏 13s', 'https://www.kuaishou.com/f/X-3M7HpE9Kh3sh1V'),
        ('横屏 48s', 'https://www.kuaishou.com/f/X3n2Z5bXSt9g1wp'),
    ]
    for tag, u in SAMPLES:
        t = time.time()
        r = asyncio.run(KuaishouPureParser().parse(u))
        print(f'\n--- {tag} {(time.time() - t):.2f}s ---')
        for k in ('success', 'type', 'work_id', 'photo_id', 'title',
                  'author', 'duration_ms', 'width', 'height',
                  'options_count', 'like_count', 'view_count', 'error'):
            if k in r:
                print(f'  {k:14s}: {str(r[k])[:60]}')
        if r.get('cdn_hosts'):
            print(f'  cdn_hosts     : {r["cdn_hosts"]}')
        if r.get('video_url'):
            print(f'  video_url     : {r["video_url"][:78]}')
