# -*- coding: utf-8 -*-
"""TikTok 解析器（2026-10-11，国际平台第二号）

两层（v2 方案）：
    L1 tikwm 公共 API（免签名免 key，直接返回无水印 HD + 音乐）
    L2 yt-dlp 万能兜底
    （P1b-next：vendor Evil0ctal dtk 签名 guest 通道，自持化替代 tikwm——
     源码已入库 src_intl/evil0ctal/，Apache-2.0，2400 行，guest 免 Cookie 实测）

⚠️ tikwm 是第三方公共服务：有限频（约 1 req/s），高并发场景必须排队；
   失败自动落 yt-dlp。长期自持化靠 dtk vendor。
"""
from __future__ import annotations

import asyncio
import json
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from ..base import BaseParser
from . import IntlParserMixin

_API = 'https://www.tikwm.com/api/'
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_TIKTOK_ID_RE = re.compile(r'/video/(\d+)') if False else None
import re
_TIKTOK_ID_RE = re.compile(r'(?:/video/|/photo/)(\d+)')


def _post_tikwm(share_url: str, hd: int = 1, timeout: int = 20):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = urllib.parse.urlencode(
        {'url': share_url, 'hd': hd}).encode()
    req = urllib.request.Request(_API, data=data, headers={
        'User-Agent': _UA,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read())


def _normalize(d: Dict[str, Any]) -> Dict[str, Any]:
    """tikwm data → 我们统一结构。

    tikwm 不返回高度数值，只有 play（SD 无水印）/hdplay（HD 无水印）/
    wmplay（带水印）三条直链——按档位语义给 options，HD 优先。
    """
    options = []
    if d.get('hdplay'):
        options.append({'url': d['hdplay'], 'height': 1080,
                        'gear': 'HD无水印', 'no_watermark': True,
                        'size': d.get('hd_size')})
    if d.get('play'):
        options.append({'url': d['play'], 'height': 720,
                        'gear': 'SD无水印', 'no_watermark': True,
                        'size': d.get('size')})
    music = d.get('music_info') or {}
    author = d.get('author') or {}
    images = [{'url': u} for u in
              (d.get('images') or []) if isinstance(u, str)]
    # 图集帖：images 非空时 type=image
    is_image = bool(images)
    return {
        'success': True,
        'platform': 'tiktok',
        'method': 'tikwm',
        'tiktok_id': d.get('id') or '',
        'type': 'image' if is_image else 'video',
        'title': (d.get('title') or '').strip()[:300],
        'author': author.get('nickname') or '',
        'author_id': author.get('unique_id') or '',
        'author_avatar': author.get('avatar') or '',
        'cover': d.get('origin_cover') or d.get('cover') or '',
        'duration_s': d.get('duration'),
        'video_url': None if is_image else
                     (options[0]['url'] if options else d.get('play') or ''),
        'quality': options[0]['gear'] if options else '',
        'options': options,
        'options_count': len(options),
        'watermark_free': True,
        'images': images,
        'image_count': len(images),
        'music_url': music.get('play') or d.get('music') or '',
        'music_title': music.get('title') or '',
        'music_author': music.get('author') or '',
    }


class TikTokPureParser(IntlParserMixin, BaseParser):
    method_label = 'tikwm/ytdlp'
    """TikTok（L1 tikwm → L2 yt-dlp；dtk vendor 自持化在 P1b-next）"""

    name = 'tiktok'
    domains = ['tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
               'www.tiktok.com']

    async def parse(self, text: str, quality: str = '1080p') -> Dict[str, Any]:
        from ...parsers.base import URL_RE
        raw = text or ''
        m = URL_RE.search(raw)
        url = m.group(0) if m else raw.strip()

        errors: list[str] = []

        # L0 dtk 自持签名（guest 免 Cookie；离线 golden 字节级验证通过）
        # 真网验证待 HK 服务器——失败自动落 tikwm，无感回退
        item_id = None
        mm = re.search(r'/video/(\d+)', url) or re.search(r'/photo/(\d+)', url)
        item_id = mm.group(1) if mm else None
        if item_id:
            from ... import config as _cfg
            if getattr(_cfg, 'TIKTOK_DTK', False):
                try:
                    from . import dtk_params
                    loop0 = asyncio.get_event_loop()
                    j = await loop0.run_in_executor(
                        None, dtk_params.fetch_detail_sync, item_id)
                    if j.get('statusCode') == 0 and \
                            ((j.get('itemInfo') or {}).get('itemStruct')):
                        result = dtk_params.parse_item_struct(
                            j['itemInfo']['itemStruct'])
                        result['short_url'] = url
                        return result
                    errors.append(f"dtk:{(j.get('statusCode'))}")
                except Exception as e:
                    errors.append(f'dtk:{str(e)[:50]}')

        # L1 tikwm（带一次重试：限频 429 常见）
        result: Optional[Dict[str, Any]] = None
        for attempt in (1, 2):
            try:
                loop = asyncio.get_event_loop()
                j = await loop.run_in_executor(None, _post_tikwm, url)
                if j.get('code') == 0 and j.get('data'):
                    result = _normalize(j['data'])
                    result['short_url'] = url
                    break
                errors.append(f"tikwm:{j.get('msg') or j.get('code')}")
            except Exception as e:
                errors.append(f'tikwm:{str(e)[:50]}')
            if attempt == 1:
                await asyncio.sleep(2)      # tikwm 限频间隔

        # L2 yt-dlp 万能兜底
        if not result:
            from . import ytdlp_engine
            result = await ytdlp_engine.extract(url, 'tiktok')
            if not result:
                errors.append('ytdlp')

        if not result:
            return {'success': False, 'platform': 'tiktok',
                    'error': ('解析失败（' + '/'.join(errors) +
                              '）——链接可能无效、私密或地区受限')}
        return result
