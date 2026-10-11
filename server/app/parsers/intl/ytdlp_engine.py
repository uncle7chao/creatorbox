# -*- coding: utf-8 -*-
"""yt-dlp 万能兜底引擎（2026-10-11，国际平台最后一层）

参考：uvd core/downloader.py + VnaSeek backend.py 的集成模式。
职责：自研通道失败后的统一兜底——YouTube/Facebook/其他国际平台，
     以及 X/TikTok 自研通道失效时的降级。

⚠️ 维护动作：每月 `pip -U yt-dlp`（YouTube 对抗靠上游版本追）
⚠️ googlevideo 直链有 IP 锁——YouTube 下载建议走扩展端（用户设备跑 yt-dlp）
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

try:
    import yt_dlp
    _HAS_YTDLP = True
except ImportError:
    yt_dlp = None
    _HAS_YTDLP = False

_CHROME_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/126.0.0.0 Safari/537.36')


def available() -> bool:
    return _HAS_YTDLP


def _ydl_opts() -> Dict[str, Any]:
    # 选项集来自 uvd/VnaSeek 实测模式（extract_info download=False 纯解析）
    return {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'retries': 2,
        'skip_download': True,
        'http_headers': {
            'User-Agent': _CHROME_UA,
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }


def _extract_sync(url: str) -> Optional[Dict[str, Any]]:
    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.sanitize_info(ydl.extract_info(url, download=False))
    return info


def _int(v: Any) -> Optional[int]:
    # 字段宽容：上游数字可能以字符串/None 任意形态出现
    try:
        if v is None or v == '':
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def normalize(url: str, info: Dict[str, Any], platform: str) -> Dict[str, Any]:
    """yt-dlp info → 我们统一返回结构。

    ⚠️ 分类必须按 protocol/vcodec 的 **none 语义**，不能只看 codec 值——
    progressive 合体格式（video+audio 单文件）的 vcodec/acodec 常为 null
    （nuncij 范本实测教训），按 codec 分类会误杀全部好文件。
    """
    formats: List[Dict[str, Any]] = info.get('formats') or []

    # progressive 合体（可直下的单文件，音视频都有或未知）
    progressive = [f for f in formats
                   if f.get('vcodec') != 'none'
                   and (f.get('acodec') not in (None, 'none')
                        or str(f.get('protocol', '')).startswith('http'))
                   and f.get('url')]
    # 纯视频轨（需合并，高度更高）
    video_only = [f for f in formats
                  if f.get('vcodec') not in (None, 'none')
                  and f.get('acodec') == 'none' and f.get('url')]

    options: List[Dict[str, Any]] = []
    seen_h = set()
    for f in sorted(progressive, key=lambda x: -(_int(x.get('height')) or 0)):
        h = _int(f.get('height')) or 0
        if h in seen_h:
            continue
        seen_h.add(h)
        options.append({'url': f['url'], 'height': h,
                        'gear': f.get('format_id') or f'{h}p',
                        'size': _int(f.get('filesize')),
                        'no_watermark': True, 'watermark': False})

    best_video_only_h = max((_int(f.get('height')) or 0)
                            for f in video_only) if video_only else 0
    if video_only and best_video_only_h > (max(seen_h) if seen_h else 0):
        # 有更高的分轨档位：标记为需合并（服务端 ffmpeg），前端锁定提示
        top = max(video_only, key=lambda x: _int(x.get('height')) or 0)
        options.append({'url': top['url'], 'height': best_video_only_h,
                        'gear': top.get('format_id') or 'hls',
                        'size': _int(top.get('filesize')),
                        'no_watermark': True, 'watermark': False,
                        'merge_required': True})

    # 音频（BGM/纯音乐下载用）
    audio_only = [f for f in formats
                  if f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')
                  and f.get('url')]
    audio_url = max(audio_only, key=lambda x: _int(x.get('abr')) or 0)['url'] \
        if audio_only else ''

    thumbnails = info.get('thumbnails') or []
    cover = (thumbnails[-1].get('url') if thumbnails else '') or \
            info.get('thumbnail') or ''

    return {
        'success': True,
        'platform': platform,
        'method': 'ytdlp_engine',
        'type': 'video' if (options or info.get('duration')) else 'video',
        'title': (info.get('title') or '').strip(),
        'description': (info.get('description') or '')[:2000],
        'author': info.get('uploader') or info.get('channel') or '',
        'author_id': str(info.get('uploader_id') or info.get('channel_id') or ''),
        'author_avatar': info.get('uploader_url') or '',
        'cover': cover,
        'duration_s': _int(info.get('duration')),
        'video_url': options[0]['url'] if options else '',
        'quality': f"{options[0]['height']}P" if options else '',
        'options': options,
        'options_count': len(options),
        'watermark_free': True,
        'music_url': audio_url,
        'music_title': (info.get('track') or info.get('title') or ''),
        'input_url': url,
    }


async def extract(url: str, platform: str) -> Optional[Dict[str, Any]]:
    """yt-dlp 解析。未安装/失败返回 None（调用方降级）。"""
    if not _HAS_YTDLP:
        return None
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _extract_sync, url)
        if not info:
            return None
        result = normalize(url, info, platform)
        await attach_subtitle(url, info, result)
        return result
    except Exception:
        return None


# ── 字幕提取（2026-10-11：YouTube/FB 文案素材第一环，uvd AI 管线同源思路）──

_SUB_EXT_PREF = ('vtt', 'srt', 'json3', 'srv3')
_SUB_MAX_BYTES = 256 * 1024      # 字幕文件上限
_SUB_TEXT_MAX = 20000            # 输出纯文本上限


def _pick_subtitle_track(info: Dict[str, Any]) -> tuple:
    """挑最佳字幕轨：人工字幕 > 自动字幕；语言 zh > en > 首个。

    返回 (lang, track_url, is_auto)；没有字幕返回 ('', '', False)。
    """
    manual = info.get('subtitles') or {}
    auto = info.get('automatic_captions') or {}
    for is_auto, pool in ((False, manual), (True, auto)):
        if not pool:
            continue
        for lang_pref in ('zh-Hans', 'zh', 'zh-CN', 'en', 'en-US'):
            if lang_pref in pool:
                lang = lang_pref
                break
        else:
            lang = next(iter(pool.keys()))
        tracks = pool.get(lang) or []
        url = ''
        for ext in _SUB_EXT_PREF:
            url = next((t['url'] for t in tracks
                        if t.get('ext') == ext and t.get('url')), '')
            if url:
                break
        if not url and tracks:
            url = tracks[0].get('url') or ''
        if url:
            return lang, url, is_auto
    return '', '', False


def _vtt_to_text(data: str) -> str:
    """vtt/srt → 纯文案：去头/时间轴/标签，连续重复行去重。"""
    out: List[str] = []
    for raw in (data or '').splitlines():
        line = raw.strip()
        if (not line or line == 'WEBVTT' or line.startswith(('NOTE', 'Kind:',
                'Language:', 'STYLE', 'REGION'))
                or '-->' in line or line.isdigit()):
            continue
        # 去内联标签 <c>、<00:00:01.000> 等
        while '<' in line and '>' in line:
            a = line.find('<')
            b = line.find('>', a)
            if b < 0:
                break
            line = line[:a] + line[b + 1:]
        line = line.strip()
        if line and (not out or out[-1] != line):
            out.append(line)
        if sum(len(x) for x in out) > _SUB_TEXT_MAX:
            break
    return '\n'.join(out)[:_SUB_TEXT_MAX]


def _fetch_subtitle_sync(url: str) -> str:
    """下载字幕文件并转纯文案（独立小请求，10s 超时，256KB 上限）。"""
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': _CHROME_UA})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        data = resp.read(_SUB_MAX_BYTES)
    text = data.decode('utf-8', errors='replace')
    return _vtt_to_text(text)


async def attach_subtitle(url: str, info: Dict[str, Any],
                          result: Dict[str, Any]) -> None:
    """解析结果附加字幕文案（失败静默——字幕是增强项不是必选项）。"""
    try:
        lang, track_url, is_auto = _pick_subtitle_track(info)
        if not track_url:
            return
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _fetch_subtitle_sync, track_url)
        if text:
            result['subtitle_text'] = text
            result['subtitle_lang'] = lang
            result['subtitle_auto'] = is_auto
    except Exception:
        pass
