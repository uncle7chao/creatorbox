# -*- coding: utf-8 -*-
"""TikTok dtk 通道：guest 参数构造 + 签名 + item/detail 拉取（P1b，2026-10-11）

字段清单与常量来自 Evil0ctal v4 params.py（Apache-2.0，已标注出处）；
签名算法本体在 dtk/tiktok_sign.py（逐字 vendor，未改一行）。

要点（v4 实测结论）：
    · guest identity 免 Cookie：content detail / author posts 多端点验证
    · msToken 传空比伪造安全（平台只在有 token 时校验）
    · 签名每次现场算（per-call 密钥不可缓存）
    · 签名参数**原样拼接不 urlencode**（字母表含 / 和 =，平台页面也不转义）
"""
from __future__ import annotations

import json
import random
import ssl
import urllib.request
from typing import Any, Dict

from .dtk import tiktok_sign

# ── 常量（Evil0ctal params.py，Apache-2.0）─────────────────────
APP_ID = '1988'
APP_NAME = 'tiktok_web'
CHANNEL = 'tiktok_web'
WEB_ORIGIN = 'https://www.tiktok.com/'
ITEM_DETAIL = 'https://www.tiktok.com/api/item/detail/'

# UA 必须与签名时的 user_agent 一致（签的是 UA 参与算出的 payload）
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36')

_PROFILE = {
    'language': 'en-US', 'region': 'US', 'timezone': 'America/New_York',
    'browser_language': 'en-US', 'browser_name': 'Chrome',
    'browser_platform': 'Win32', 'browser_version': '139.0.0.0',
    'os_name': 'Windows', 'screen_height': 1080, 'screen_width': 1920,
}

_call_sequence = [0]      # SDK 从 1 起自计调用次数（payload 内有该字段）


def _device_id() -> str:
    """合规形态的 TikTok web device id（19 位数字，首位非零）"""
    import random as _r
    return str(_r.randint(1, 9)) + ''.join(
        str(_r.randint(0, 9)) for _ in range(18))


def base_params(item_id: str) -> Dict[str, str]:
    """每次 TikTok web API 调用都带的参数集（Evil0ctal base_params 同源）"""
    return {
        'aid': APP_ID,
        'app_language': _PROFILE['language'],
        'app_name': APP_NAME,
        'browser_language': _PROFILE['browser_language'],
        'browser_name': _PROFILE['browser_name'],
        'browser_online': 'true',
        'browser_platform': _PROFILE['browser_platform'],
        'browser_version': _PROFILE['browser_version'],
        'channel': CHANNEL,
        'cookie_enabled': 'true',
        'device_id': _device_id(),
        'device_platform': 'web_pc',
        'focus_state': 'true',
        'from_page': 'user',
        'history_len': '4',
        'is_fullscreen': 'false',
        'is_page_visible': 'true',
        'language': _PROFILE['language'],
        'os': _PROFILE['os_name'].lower(),
        'priority_region': _PROFILE['region'],
        'referer': '',
        'region': _PROFILE['region'],
        'root_referer': WEB_ORIGIN,
        'screen_height': str(_PROFILE['screen_height']),
        'screen_width': str(_PROFILE['screen_width']),
        'tz_name': _PROFILE['timezone'],
        'webcast_language': _PROFILE['language'],
        'itemId': str(item_id),
    }


def _fetch_sync(url: str, timeout: int = 20) -> Dict[str, Any]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': WEB_ORIGIN,
        'Origin': WEB_ORIGIN,
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read())


def fetch_detail_sync(item_id: str, sequence: int = 1) -> Dict[str, Any]:
    """签名 → 请求 /api/item/detail/ → 返回 JSON（或抛异常）。"""
    pairs = list(base_params(item_id).items())
    signed, _params = tiktok_sign.sign(
        pairs, UA, ms_token='', sequence=max(1, sequence % 1000))
    url = f'{ITEM_DETAIL}?{signed}'
    return _fetch_sync(url)


# ── 响应解析（itemStruct → 我们统一结构；最小实现）──────────────

def _url_from(holder: Any) -> str:
    """字段宽容取直链：字符串直链 / {url_list} / PascalCase {UrlList}"""
    if isinstance(holder, str):
        return holder
    if isinstance(holder, dict):
        lst = holder.get('url_list') or holder.get('UrlList') or []
        return (lst[0] if lst and isinstance(lst[0], str) else
                (lst[0].get('url') or lst[0].get('Url') or '')
                if lst and isinstance(lst[0], dict) else '')
    return ''


def _best_play(item: Dict[str, Any]) -> Dict[str, Any]:
    """从 video.bitrateInfo 取最高码率档；回退 playAddr。

    ⚠️ 字段宽容（真实 API 两种形态并存，TVHelper 教训）：
    · playAddr 可能是字符串（直链）也可能是 {url_list:[...]}（旧版）
    · bitrateInfo 用 PascalCase（Bitrate/PlayAddr.UrlList）
    """
    video = item.get('video') or {}

    best, best_br = '', -1
    for b in video.get('bitrateInfo') or []:
        play = b.get('PlayAddr') or b.get('playAddr') or {}
        u = _url_from(play)
        br = b.get('Bitrate') or b.get('bitrate') or 0
        if u and br > best_br:
            best, best_br = u, br
    if not best:
        best = _url_from(video.get('playAddr'))
    return {'url': best, 'bitrate': best_br}


def parse_item_struct(item: Dict[str, Any]) -> Dict[str, Any]:
    video = item.get('video') or {}
    images_raw = item.get('images') or []
    author = item.get('author') or {}
    music = item.get('music') or {}
    images = []
    for im in images_raw:
        u = ((im.get('urlList') or []) or [''])[0]
        if u:
            images.append({'url': u})
    best = _best_play(item)
    stats = item.get('stats') or {}
    return {
        'success': True,
        'platform': 'tiktok',
        'method': 'dtk_guest',
        'tiktok_id': str(item.get('id') or ''),
        'type': 'image' if (images and not best['url']) else 'video',
        'title': (item.get('desc') or '').strip()[:300],
        'author': author.get('nickname') or '',
        'author_id': str(author.get('uniqueId') or author.get('id') or ''),
        'author_avatar': author.get('avatarLarger') or '',
        'cover': _url_from(video.get('cover')),
        'duration_s': (lambda d: int(float(d) / 1000) if d else None)(
            video.get('duration')),
        'video_url': best['url'] if not images else None,
        'quality': 'HD' if best['bitrate'] > 0 else '',
        'options': ([{'url': best['url'], 'gear': 'dtk_best',
                      'no_watermark': True, 'bitrate': best['bitrate']}]
                    if best['url'] else []),
        'watermark_free': True,
        'images': images,
        'image_count': len(images),
        'music_url': _url_from(music.get('playUrl')) or '',
        'music_title': music.get('title') or '',
        'music_author': music.get('authorName') or '',
        'like_count': stats.get('diggCount'),
        'comment_count': stats.get('commentCount'),
        'view_count': stats.get('playCount'),
    }
