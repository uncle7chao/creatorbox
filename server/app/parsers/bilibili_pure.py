"""B站纯 HTTP 解析器（无浏览器、无 ffmpeg）

来源：读 wujunwei928/parse-video-py 源码得到的双接口方案
     1) x/web-interface/view?bvid=  → 拿 cid
     2) x/player/playurl?fnval=0&platform=html5  → 拿 durl（单文件含音轨）

实测（2026-10-05）：
- API code=0，durl[0] 49.57MB 单文件 MP4，Range 支持（HTTP 206）
- CDN 域名是标准 bilivideo.com，**不是** 随机 MCDN → 微信白名单可枚举
- 关键：Referer 必须设为视频页自身，否则返回挑战页
- ⚠️ fnval=0 走老式 durl，代价：最高只给 720P（fnval=16 才有 1080P dash）

⚠️ dash（fnval=16）需要登录 Cookie拿 1080P，且音视频分离需 ffmpeg 合并
"""
from __future__ import annotations

import asyncio
import gzip
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 '
         'Safari/537.36')

BV_RE = re.compile(r'(BV[0-9A-Za-z]{10})')
AV_RE = re.compile(r'av(\d+)')
B23_RE = re.compile(r'b23\.tv/([0-9A-Za-z]+)')


def _get(url: str, referer: str, timeout: int = 20) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={
        'User-Agent': PC_UA,
        'Referer': referer,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    })
    r = urllib.request.urlopen(req, timeout=timeout)
    raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


async def resolve_b23(url: str) -> str:
    """b23.tv 短链 → BV号"""
    loop = asyncio.get_event_loop()

    def _do() -> str:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise urllib.error.HTTPError(
                    req.full_url, code, msg, headers, fp)
        opener = urllib.request.build_opener(NoRedirect)
        try:
            r = opener.open(urllib.request.Request(
                url, headers={'User-Agent': PC_UA}), timeout=15)
            final = r.geturl()
        except urllib.error.HTTPError as e:
            final = (e.headers.get('Location') if e.headers else '') or url
        except Exception:
            final = url
        m = BV_RE.search(final)
        return m.group(1) if m else ''

    return await loop.run_in_executor(None, _do)


class BilibiliPureParser:
    """纯 HTTP B站解析—— API 路线，不需要浏览器也不需要 ffmpeg"""

    name = 'bilibili_pure'
    domains = ('bilibili.com', 'b23.tv')

    def match(self, url: str) -> bool:
        return 'bilibili.com' in url or 'b23.tv' in url

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        m = B23_RE.search(text or '')
        if m:
            bvid = await resolve_b23(text)
        else:
            mb = BV_RE.search(text or '')
            ma = AV_RE.search(text or '')
            bvid = mb.group(1) if mb else (
                f'av{ma.group(1)}' if ma else '')

        if not bvid:
            return {'success': False, 'platform': 'bilibili',
                    'error': '未识别到 BV/av 号'}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: _parse_sync(bvid, quality))

    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'api_durl',
                'note': '纯 HTTP，无需浏览器'}


def _parse_sync(video_id: str, quality: str) -> Dict[str, Any]:
    referer = ('https://www.bilibili.com/video/'
               f'{video_id}' if video_id.startswith('BV')
               else 'https://www.bilibili.com/')

    # ---- 1. view拿 cid ----
    try:
        d = _get(f'https://api.bilibili.com/x/web-interface/'
                 f'view?{"bvid" if video_id.startswith("BV") else "aid"}='
                 f'{video_id}', referer='https://www.bilibili.com/')
    except Exception as e:
        return {'success': False, 'platform': 'bilibili',
                'error': f'view 接口失败: {str(e)[:70]}',
                'bvid': video_id}
    if d.get('code') != 0:
        return {'success': False, 'platform': 'bilibili',
                'error': f'view 返回 code={d.get("code")} '
                         f'{d.get("message")}', 'bvid': video_id}

    meta = d.get('data') or {}
    cid = meta.get('cid')
    if not cid:
        return {'success': False, 'platform': 'bilibili',
                'error': '未取到 cid', 'bvid': video_id}

    # ---- 2. playurl 取 durl（fnval=0 老式单文件）----
    # qn=80 是 1080P，但匿名会话实际只给 720P(qn=64)
    p = urllib.parse.urlencode({
        'fnver': 0, 'fnval': 0, 'qn': 80,
        'bvid': video_id if video_id.startswith('BV') else '',
        'aid': '' if video_id.startswith('BV') else video_id[2:],
        'cid': cid, 'platform': 'html5',
    })
    try:
        d2 = _get(f'https://api.bilibili.com/x/player/playurl?{p}',
                  referer=referer)
    except Exception as e:
        return {'success': False, 'platform': 'bilibili',
                'error': f'playurl 失败: {str(e)[:70]}', 'bvid': video_id}
    if d2.get('code') != 0:
        return {'success': False, 'platform': 'bilibili',
                'error': f'playurl code={d2.get("code")} '
                         f'{d2.get("message")}', 'bvid': video_id}

    pd = d2.get('data') or {}
    durl = pd.get('durl') or []
    if not durl:
        return {'success': False, 'platform': 'bilibili',
                'error': 'durl 为空（可能需要登录 Cookie）',
                'bvid': video_id}

    url = durl[0].get('url') or ''
    accept = pd.get('accept_quality') or []
    desc = pd.get('accept_description') or []
    qmap = {64: 720, 32: 480, 16: 360, 80: 1080, 112: 1080}
    height = qmap.get(pd.get('quality') or 64, 720)

    owner = meta.get('owner') or {}
    stat = meta.get('stat') or {}

    return {
        'success': True,
        'platform': 'bilibili',
        'method': 'api_durl',
        'type': 'video',
        'bvid': meta.get('bvid') or (video_id if
                                     video_id.startswith('BV') else None),
        'aid': meta.get('aid'),
        'cid': cid,
        'title': meta.get('title') or '',
        # ---- 元信息（2026-10-05 补齐，字段来源见app/meta.py META_RULES）----
        'description': meta.get('desc') or '',
        'author': owner.get('name') or '',
        'author_id': str(owner.get('mid') or ''),
        'author_avatar': _pic(owner.get('face')),
        'cover': _pic(meta.get('pic')),
        'duration_ms': (meta.get('duration') or 0) * 1000,
        'publish_time_ts': meta.get('pubdate'),      # Unix 秒
        'like_count': stat.get('like'),
        'comment_count': stat.get('reply'),
        'collect_count': stat.get('favorite'),
        'share_count': stat.get('share'),
        'view_count': stat.get('view'),
        'danmaku_count': stat.get('danmaku'),
        'coin_count': stat.get('coin'),
        'tname': meta.get('tname') or '',
        'copyright': meta.get('copyright'),
        'width': (meta.get('dimension') or {}).get('width'),
        'height_src': (meta.get('dimension') or {}).get('height'),
        'video_url': url,
        'quality': f'{height}P',
        'size': durl[0].get('size'),
        'duration_ms_note': durl[0].get('length'),
        'options': [{
            'index': 0, 'gear': f'{height}P', 'width': meta.get('dimension', {}).get('width'),
            'height': height, 'bit_rate': None,
            'no_watermark': True, 'url': url,
        }],
        'options_count': 1,
        # 关键能力标记（客户端读这些字段决定怎么处理）
        'dash': False,            # 单文件含音轨，不需要 ffmpeg
        'need_proxy': False,      # CDN 是标准域名，可加白名单
        'anonymous': True,        # 匿名上限 720P
        'anonymous_max_height': 720,
        'accept_quality': desc or accept,
        'accept_note': 'fnval=0 单文件路线；1080P 需登录 Cookie + fnval=16(dash)',
        'no_watermark': True,
        'watermark_free': True,
    }


def _pic(p: Optional[str]) -> str:
    if not p:
        return ''
    return p if p.startswith('http') else f'https:{p}'


if __name__ == '__main__':
    import sys
    import time

    async def main():
        t0 = time.time()
        p = BilibiliPureParser()
        txt = sys.argv[1] if len(sys.argv) > 1 else \
            'https://www.bilibili.com/video/BV1GJ411x7h7'
        r = await p.parse(txt)
        print(f'耗时 {time.time() - t0:.2f}s')
        for k in ('success', 'method', 'title', 'author', 'quality',
                  'dash', 'need_proxy', 'anonymous', 'size'):
            if k in r:
                print(f'{k:12s}:', str(r[k])[:56])
        print('video_url  :', (r.get('video_url') or '')[:110])
        if not r.get('success'):
            print('error      :', r.get('error'))

    asyncio.run(main())