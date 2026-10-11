# -*- coding: utf-8 -*-
"""X/Twitter 解析器（2026-10-11，国际平台第一号）

三层降级（nuncij MIT 范本架构 + parse-video-py MIT syndication 实现）：
    L1 syndication π-token（自研，twimg 不锁 IP → 302 直链）
    L2 FxTwitter API（免鉴权 JSON，补 L1 缺口：photo-only/GIF/限频）
    L3 yt-dlp 万能兜底

已知事实（生态实测情报）：
    · progressive MP4（合体单文件）最高 720P，以上是 HLS 分轨
    · syndication 接口偶尔收紧 token 校验 → 自动落 L2/L3
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import ssl
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseParser
from . import IntlParserMixin

_CHROME_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/126.0.0.0 Safari/537.36')
_TWEET_ID_RE = re.compile(r'(?:twitter\.com|x\.com)/[^/]+/status(?:es)?/(\d+)')

# 独立 UA 池语义：X 对 UA 不敏感，固定 Chrome 即可（生态共识）
_HEADERS = {'User-Agent': _CHROME_UA, 'Accept': 'application/json',
            'Referer': 'https://platform.twitter.com/'}


def tweet_token(tweet_id: str) -> str:
    """syndication token：(tweetId / 1e15) * π 去掉 0 和小数点（parse-video-py 同款）"""
    num = float(tweet_id)
    return str((num / 1e15) * math.pi).replace('0', '').replace('.', '')


def extract_tweet_id(url: str) -> Optional[str]:
    m = _TWEET_ID_RE.search(url or '')
    return m.group(1) if m else None


def _get_json_sync(url: str, timeout: int = 12):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read())


def _pick_best_video(variants: List[Dict[str, Any]]) -> str:
    """video/mp4 变体里取最高 bitrate（非固定下标——parse-video-py 同款）"""
    best, best_br = '', -1
    for v in variants:
        if v.get('content_type') != 'video/mp4':
            continue
        br = v.get('bitrate') or 0
        if br > best_br or not best:
            best, best_br = v.get('url') or '', br
    return best


def _from_syndication(tweet_id: str) -> Optional[Dict[str, Any]]:
    try:
        j = _get_json_sync('https://cdn.syndication.twimg.com/'
                           f'tweet-result?id={tweet_id}'
                           f'&token={tweet_token(tweet_id)}')
    except Exception:
        return None
    media = j.get('mediaDetails') or []
    video_url, images = '', []
    top = [m for m in media if m.get('type') == 'video']
    if top:
        video_url = _pick_best_video(top[0].get('video_info', {})
                                     .get('variants') or [])
    if not video_url:
        for m in media:
            if m.get('type') == 'photo' and m.get('media_url_https'):
                images.append({'url': m['media_url_https']})
        if not images:
            return None
    user = j.get('user') or {}
    return {
        'success': True, 'platform': 'x', 'method': 'syndication',
        'type': 'video' if video_url else 'image',
        'title': (j.get('text') or '').strip()[:300],
        'author': user.get('name') or user.get('screen_name') or '',
        'author_id': user.get('id_str') or '',
        'author_avatar': user.get('profile_image_url_https') or '',
        'cover': (top[0].get('video_info', {}).get('variants') and
                  j.get('video', {}).get('poster')) or
                 (images[0]['url'] if images else ''),
        'images': images,
        'image_count': len(images),
        'video_url': video_url,
        'watermark_free': True,
    }


def _from_fxtwitter(tweet_id: str) -> Optional[Dict[str, Any]]:
    try:
        j = _get_json_sync(f'https://api.fxtwitter.com/status/{tweet_id}')
    except Exception:
        return None
    if not j.get('tweet'):
        return None
    tw = j['tweet']
    media = tw.get('media') or {}
    videos = media.get('videos') or []
    photos = media.get('photos') or []
    author = tw.get('author') or {}
    video_url = videos[0].get('url') if videos else ''
    images = [{'url': p['url']} for p in photos if p.get('url')]
    if not video_url and not images:
        return None
    return {
        'success': True, 'platform': 'x', 'method': 'fxtwitter',
        'type': 'video' if video_url else 'image',
        'title': (tw.get('text') or '').strip()[:300],
        'author': author.get('name') or author.get('screen_name') or '',
        'author_id': author.get('screen_name') or '',
        'author_avatar': author.get('avatar_url') or '',
        'cover': (videos[0].get('thumbnail_url') if videos else '') or
                 (images[0]['url'] if images else ''),
        'images': images,
        'image_count': len(images),
        'video_url': video_url,
        'watermark_free': True,
    }


class XPureParser(IntlParserMixin, BaseParser):
    method_label = 'syndication/fxtwitter/ytdlp'
    """X/Twitter（三层降级：syndication → FxTwitter → yt-dlp）"""

    name = 'x'
    domains = ['twitter.com', 'x.com', 't.co', 'mobile.twitter.com']

    async def parse(self, text: str, quality: str = '1080p') -> Dict[str, Any]:
        from ...parsers.base import URL_RE
        raw = text or ''
        m = URL_RE.search(raw)
        url = m.group(0) if m else raw.strip()

        # t.co 短链 301 解析
        if 't.co/' in url:
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers={
                    'User-Agent': _CHROME_UA})
                # 不跟随跳转，直接取 Location（等价 302 首跳）
                opener = urllib.request.build_opener(_NoRedirect)
                with opener.open(req, timeout=12, context=ctx) as r:
                    loc = r.headers.get('Location') or ''
                if loc:
                    url = loc
            except Exception:
                pass

        tweet_id = extract_tweet_id(url)
        if not tweet_id:
            return {'success': False, 'platform': 'x',
                    'error': '无法从链接中提取推文 ID（仅支持推文/视频链接）'}

        result: Optional[Dict[str, Any]] = None
        errors: List[str] = []

        # L1 syndication（自研，不锁 IP 可 302）
        result = _from_syndication(tweet_id)
        if not result:
            errors.append('syndication')

        # L2 FxTwitter
        if not result:
            result = _from_fxtwitter(tweet_id)
            if not result:
                errors.append('fxtwitter')

        # L3 yt-dlp 万能兜底
        if not result:
            from . import ytdlp_engine
            result = await ytdlp_engine.extract(url, 'x')
            if not result:
                errors.append('ytdlp')

        if not result:
            return {'success': False, 'platform': 'x',
                    'error': ('三条通道均失败（' + '/'.join(errors) +
                              '）——推文可能已删除、设为私密或地区受限')}

        result['tweet_id'] = tweet_id
        result['short_url'] = url
        if result.get('type') == 'image':
            result.setdefault('video_url', None)
            result['quality'] = None
        else:
            result.setdefault('options', [{
                'url': result.get('video_url'), 'height': 720,
                'gear': 'progressive', 'no_watermark': True}])
            result.setdefault('quality', '720P')
        return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
