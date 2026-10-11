"""微博视频/图集纯 HTTP 解析器

⭐ 2026-10-05首次拿到真实 oid样本，接口全链路跑通
────────────────────────────────────────────────────
真实样本：https://weibo.com/tv/show/1034:5343195622473745?mid=5343196424963244
作者「陆屿熙」，1080P / 319.41s / 112.83MB 完整下载，非截断。

【接口 1】视频播放信息（POST）
    POST https://h5.video.weibo.com/api/component?page=/show/{oid}
    Referer: https://h5.video.weibo.com/show/{oid}
    Content-Type: application/x-www-form-urlencoded
    body: data={"Component_Play_Playinfo":{"oid":"{oid}"}}
    → data.Component_Play_Playinfo
      urls        = {"高清 1080P": "//f.video.weibocdn.com/...", ...}  3 档
      stream_url  = 最低档（与 urls[末档] 同源）
      title/author/nickname/author_id/avatar/verified_reason
      real_date / attitudes_count / comments_count / followers_count

【接口 2】正文与封面（GET，可选但强烈建议调）
    GET https://m.weibo.cn/statuses/show?id={mid}
    Referer: https://m.weibo.cn/    X-Requested-With: XMLHttpRequest
    → data.page_info.page_pic.url   封面（480 宽，竖屏视频 480x776）
      data.page_info.content2       文案描述（比 title「XX的微博视频」有用得多）
      data.page_info.video_orientation  "vertical" / "horizontal"
      data.page_info.play_count     播放量文案
      data.text                    正文 HTML（需剥标签）
      data.user.screen_name / profile_image_url
    → data.pics[]                  图集（纯图片微博，video_orientation 缺失）

⚠️ 修正知识库的错误（实测发现）
    文档原写「urls 的**第一个 key 是最高码率**」—— 实测第一个确实是最高档
    （高清 1080P），但**理由是 dict 保序 + 平台按降序插入**，
    不是"第一个 key 天然代表最高"。所以正确做法是**按 label 解析高度**，
    不要依赖下标 —— 万一平台调整顺序就会取错档。

⚠️ oid 提取有两种形态
    weibo.com/tv/show/1034:5343195622473745   → oid = "1034:5343195622473745"
        （格式 {prefix}:{media_id}，冒号前是 prefix，冒号后才是 media_id）
    video.weibo.com/show?fid=1034:5343195622473745
    mid（正文 id）可从 ?mid= 拿，或从 component 返回里取 data.mid

⚠️ CDN 与缓存
    f.video.weibocdn.com，URL 带 Expires + ssig 签名 → 短期有效，
    缓存 TTL 建议 ≤ 10 分钟（同好看视频）。
    域名是 weibocdn.com 单域名，**可枚举，可加小程序白名单**。
"""
from __future__ import annotations

import asyncio
import gzip
import html
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
MOBILE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
             'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 '
             'Mobile/15E148 Safari/604.1')

COMPONENT_API = 'https://h5.video.weibo.com/api/component?page=/show/{oid}'
SHOW_PAGE = 'https://h5.video.weibo.com/show/{oid}'
STATUS_API = 'https://m.weibo.cn/statuses/show?id={mid}'

# oid 形态：1034:5343195622473745
OID_RE = re.compile(r'\b(\d{3,6}):(\d{9,})\b')
# 也接受纯 media_id（部分短链只有数字）
FID_RE = re.compile(r'(?:fid|oid)=(\d{3,6}:\d{9,})')
MID_RE = re.compile(r'[?&]mid=(\d{9,})')
URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')

# label → 高度（不要依赖 dict 下标，见文件头说明）
GEAR_HEIGHT = [
    ('1080', 1080), ('超清', 1080), ('蓝光', 1080),
    ('720', 720), ('高清', 720),
    ('480', 480), ('标清', 480), ('标清 480', 480),
    ('360', 360), ('流畅', 360),
]

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

_TAG_RE = re.compile(r'<[^>]+>')


def _https(u: str) -> str:
    """微博大量 // 前缀与 http 明文地址"""
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http://'):
        return 'https://' + u[len('http://'):]
    return u


def _strip_tags(s: str) -> str:
    return html.unescape(_TAG_RE.sub('', s or '')).strip()


def _post(url: str, data: dict, referer: str,
          timeout: int = 25) -> Dict[str, Any]:
    body = urllib.parse.urlencode(
        {'data': json.dumps(data, ensure_ascii=False)})
    req = urllib.request.Request(url, data=body.encode(), headers={
        'User-Agent': PC_UA,
        'Referer': referer,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate',
        'X-Requested-With': 'XMLHttpRequest',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':           # P7
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


def _get(url: str, referer: str, mobile: bool = False,
         timeout: int = 25) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={
        'User-Agent': MOBILE_UA if mobile else PC_UA,
        'Referer': referer,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate',
        'X-Requested-With': 'XMLHttpRequest',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


def _probe_size(url: str, referer: str, timeout: int = 20) -> Optional[int]:
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': PC_UA, 'Referer': referer, 'Range': 'bytes=0-1'})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            cr = r.headers.get('Content-Range') or ''
        if '/' in cr:
            tail = cr.rsplit('/', 1)[-1].strip()
            if tail.isdigit():
                return int(tail)
    except Exception:
        pass
    return None


def _height_of(label: str) -> int:
    """从档位名解析高度，如「高清 1080P」→ 1080"""
    for key, h in GEAR_HEIGHT:
        if key in (label or ''):
            return h
    m = re.search(r'(\d{3,4})', label or '')
    return int(m.group(1)) if m else 0


def extract_ids(url: str) -> tuple:
    """从微博链接提取 (oid, mid)

    oid 形如 1034:5343195622473745（冒号前是 prefix，不是 media_id）
    """
    oid = mid = ''
    m = OID_RE.search(url)
    if m:
        oid = f'{m.group(1)}:{m.group(2)}'
    if not oid:
        m = FID_RE.search(url)
        if m:
            oid = m.group(1)
    m = MID_RE.search(url)
    if m:
        mid = m.group(1)
    return oid, mid


def _parse_video_sync(oid: str, mid: str) -> Dict[str, Any]:
    referer = SHOW_PAGE.format(oid=oid)
    try:
        j = _post(COMPONENT_API.format(oid=oid),
                  {'Component_Play_Playinfo': {'oid': oid}}, referer)
    except Exception as e:
        return {'success': False, 'platform': 'weibo',
                'error': f'component 接口失败: {str(e)[:70]}'}

    if str(j.get('code')) not in ('100000', '0'):
        return {'success': False, 'platform': 'weibo',
                'error': f'component 返回 code={j.get("code")} '
                         f'{j.get("msg", "")[:40]}'}

    info = ((j.get('data') or {}).get('Component_Play_Playinfo') or {})
    if not info:
        return {'success': False, 'platform': 'weibo',
                'error': '组件为空（oid 无效或内容已删除）', 'oid': oid}

    urls = info.get('urls') or {}
    if not urls:
        return {'success': False, 'platform': 'weibo',
                'error': 'urls 为空（可能需要登录或内容已下架）', 'oid': oid}

    # ⚠️ 按 label 解析高度排序，不依赖 dict 下标
    options: List[Dict[str, Any]] = []
    for label, raw in urls.items():
        u = _https(raw)
        if not u:
            continue
        h = _height_of(label)
        options.append({
            'gear': label,
            'height': h,
            'size': _probe_size(u, referer),
            'no_watermark': True,
            'url': u,
        })
    options.sort(key=lambda o: o.get('height') or 0, reverse=True)
    for i, o in enumerate(options):
        o['index'] = i

    best = options[0]

    result: Dict[str, Any] = {
        'success': True,
        'platform': 'weibo',
        'method': 'component_api',
        'type': 'video',
        'oid': oid,
        'mid': str(info.get('mid') or mid or ''),
        'media_id': str(info.get('media_id') or ''),
        'title': info.get('title') or '',
        'author': info.get('author') or info.get('nickname') or '',
        'author_id': str(info.get('author_id') or ''),
        'author_avatar': _https(info.get('avatar') or ''),
        # ⭐ 2026-10-05 修正：cover_image 就在 component 接口里！
        #   我之前误以为「component 不给封面」，绕道第二个接口取
        #   page_info.page_pic.url。实测两者是**同一张图**
        #   （都 56268 字节），所以第二个接口对封面是多余的。
        #   （开源 parse-video-py / parse-video(Go) 用的就是 cover_image）
        'cover': _https(info.get('cover_image') or ''),
        'verified': bool(info.get('verified')),
        'verified_reason': info.get('verified_reason') or '',
        'publish_time_ts': info.get('real_date'),      # Unix 秒
        'publish_time': info.get('real_date'),
        'date_text': info.get('date') or '',            # "20天前"
        'like_count': _to_int(info.get('attitudes_count')),
        'comment_count': _to_int(info.get('comments_count')),
        'share_count': _to_int(info.get('reposts_count')),   # 微博叫转发
        'repost_count': _to_int(info.get('reposts_count')),
        'view_count_text': info.get('play_count') or '',      # "450万"
        'follower_count_text': info.get('followers_count') or '',  # "115.9万"
        'follower_count': info.get('followers_count') or '',
        'ip_location': info.get('ip_info_str') or '',   # "发布于 广东"
        # ⚠️ P28：微博的 duration_time 是**秒**（319.414），
        #   不是毫秒。duration_ms 是我们自己的统一字段。
        'duration_time': info.get('duration_time'),
        'duration_ms': int(float(info.get('duration_time') or 0) * 1000),
        'video_url': best['url'],
        'quality': best['gear'],
        'size': best.get('size'),
        'options': options,
        'options_count': len(options),
        'dash': False,                 # mp4 单文件含 AAC 音轨（实测 trak=2）
        'need_proxy': False,            # f.video.weibocdn.com 单域名，可加白名单
        'anonymous': True,
        'no_watermark': True,
        'watermark_free': True,
        'url_expiry_note': 'URL 带 Expires + ssig 签名，缓存 TTL ≤ 10 分钟',
        'cache_ttl_hint': 600,
    }

    # ---- 接口 2：文案 / 方向 / 播放量（可选，失败不影响主流程）----
    # ⭐ 封面**不需要**这个接口（component 自带 cover_image），
    #   这里只补 component 没有的：真实文案、横竖屏、播放量。
    mid_val = result['mid'] or mid
    if mid_val:
        try:
            st = _get(STATUS_API.format(mid=mid_val), 'https://m.weibo.cn/',
                      mobile=True)
            d = st.get('data') or {}
            if st.get('ok') == 1 and d:
                pi = d.get('page_info') or {}
                # 封面兜底（正常不会走到，component 已经给了）
                if not result.get('cover'):
                    pic = pi.get('page_pic') or {}
                    if pic.get('url'):
                        result['cover'] = _https(pic['url'])
                c2 = _strip_tags(pi.get('content2') or '')
                if c2:
                    result['description'] = c2
                if pi.get('video_orientation'):
                    result['orientation'] = pi['video_orientation']
                if pi.get('play_count'):
                    result['play_count_text'] = pi['play_count']
                text = _strip_tags(d.get('text') or '')
                if text:
                    result['caption'] = text
                u = d.get('user') or {}
                if u.get('profile_image_url') and not result.get(
                        'author_avatar'):
                    result['author_avatar'] = _https(u['profile_image_url'])
                if u.get('followers_count') and not result.get(
                        'follower_count'):
                    result['follower_count'] = u['followers_count']
        except Exception:
            pass          # 封面拿不到不影响解析成功

    if not result.get('cover'):
        result['cover'] = ''
    return result


def _parse_images_sync(mid: str) -> Dict[str, Any]:
    """纯图集微博：data.pics[]"""
    try:
        st = _get(STATUS_API.format(mid=mid), 'https://m.weibo.cn/', mobile=True)
    except Exception as e:
        return {'success': False, 'platform': 'weibo',
                'error': f'图集接口失败: {str(e)[:70]}'}
    d = st.get('data') or {}
    if st.get('ok') != 1 or not d:
        return {'success': False, 'platform': 'weibo',
                'error': f'图集接口 ok={st.get("ok")}（mid 无效？）'}

    pics = d.get('pics') or []
    if not pics:
        return {'success': False, 'platform': 'weibo',
                'error': 'pics 为空（既不是视频也没有图集）'}

    # ⭐ 按 large → original → bmiddle → url 顺序取首个（实测 pic_id 型）
    images = []
    for p in pics:
        u = ''
        for key in ('large', 'original', 'bmiddle', 'url', 'mw2000'):
            if isinstance(p.get(key), dict) and p[key].get('url'):
                u = p[key]['url']
                break
            if isinstance(p.get(key), str) and p[key]:
                u = p[key]
                break
        if not u:
            continue
        images.append({
            'url': _https(u),
            'width': p.get('width'),
            'height': p.get('height'),
            'format': 'jpeg',
            'no_watermark': True,
        })

    if not images:
        return {'success': False, 'platform': 'weibo',
                'error': 'pics 有数据但所有候选字段都取不到 url'}

    u = d.get('user') or {}
    return {
        'success': True,
        'platform': 'weibo',
        'method': 'statuses_show',
        'type': 'image',
        'mid': mid,
        'title': (d.get('text') or '').strip()[:80],
        'caption': _strip_tags(d.get('text') or ''),
        'author': u.get('screen_name') or '',
        'author_id': str(u.get('id') or ''),
        'author_avatar': _https(u.get('profile_image_url') or ''),
        'cover': images[0]['url'],
        'publish_time': d.get('created_at'),
        'images': images,
        'image_count': len(images),
        'options': images,
        'options_count': len(images),
        'like_count': _to_int(d.get('attitudes_count')),
        'comment_count': _to_int(d.get('comments_count')),
        'repost_count': _to_int(d.get('reposts_count')),
        'need_proxy': False,
        'anonymous': True,
        'no_watermark': True,
        'watermark_free': True,
    }


def _to_int(v: Any) -> Optional[int]:
    """微博的计数有的是字符串「115.9万」"""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v)
    m = re.match(r'([\d.]+)\s*万', s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.match(r'([\d.]+)\s*亿', s)
    if m:
        return int(float(m.group(1)) * 100000000)
    digits = re.sub(r'[^\d]', '', s)
    return int(digits) if digits else None


class WeiboPureParser:
    """纯 HTTP 微博解析 —— 视频 + 图集，无浏览器"""

    name = 'weibo_pure'
    domains = ('weibo.com', 'weibo.cn')

    @staticmethod
    def extract_url(text: str) -> str:
        m = URL_RE.search(text or '')
        return m.group(0) if m else ''

    def match(self, url: str) -> bool:
        return 'weibo.com' in url or 'weibo.cn' in url

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        url = self.extract_url(text)
        if not url:
            return {'success': False, 'platform': 'weibo',
                    'error': '未识别到链接'}
        if not self.match(url):
            return {'success': False, 'platform': 'weibo',
                    'error': '不是微博链接'}

        oid, mid = extract_ids(url)
        if not oid and not mid:
            return {'success': False, 'platform': 'weibo',
                    'error': f'未能从链接提取 oid/mid: {url[:60]}',
                    'hint': '微博视频链接应含 1034:5343195622473745 或 mid='}

        loop = asyncio.get_event_loop()
        if oid:
            return await loop.run_in_executor(
                None, lambda: _parse_video_sync(oid, mid))
        return await loop.run_in_executor(
            None, lambda: _parse_images_sync(mid))

    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'component_api',
                'note': '纯 HTTP；3 档 1080P/720P/480P，匿名可用'}


if __name__ == '__main__':
    import sys
    import time

    async def _main():
        samples = sys.argv[1:] or [
            'https://weibo.com/tv/show/1034:5343195622473745'
            '?mid=5343196424963244',
        ]
        p = WeiboPureParser()
        for s in samples:
            t0 = time.time()
            r = await p.parse(s)
            print(f'\n--- {s[:60]}  {time.time() - t0:.2f}s')
            print(f"  success      : {r.get('success')}")
            for k in ('type', 'oid', 'mid', 'title', 'author', 'verified_reason',
                      'quality', 'size', 'orientation', 'play_count_text',
                      'like_count', 'comment_count', 'options_count',
                      'need_proxy', 'anonymous'):
                if k in r:
                    print(f'  {k:16s}: {str(r[k])[:56]}')
            if r.get('description'):
                print(f"  {'description':16s}: {r['description'][:56]}")
            if r.get('cover'):
                print(f"  {'cover':16s}: {r['cover'][:66]}")
            for o in r.get('options', []):
                sz = o.get('size')
                print(f"    [{o['index']}] {o['gear']:12s} "
                      f"{sz / 1048576:.1f}MB" if sz else
                      f"    [{o['index']}] {o['gear']:12s} ?")
            print('  video_url    :', (r.get('video_url') or '')[:80])
            if r.get('image_count'):
                for im in r['images'][:3]:
                    print('   img:', im['url'][:78])
            if not r.get('success'):
                print('  error        :', r.get('error'))

    asyncio.run(_main())
