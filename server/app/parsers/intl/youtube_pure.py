# -*- coding: utf-8 -*-
"""YouTube 解析器（2026-10-11，yt-dlp 引擎封装）

为什么走 yt-dlp 而不是自研 innertube：
    · YouTube 的 nsig 挑战要跟 player JS 的签名算法，yt-dlp 上游全职对抗，
      自研维护成本失控（生态共识：uvd/VnaSeek/Yeguo 全部收敛到 yt-dlp）
    · yt-dlp = Unlicense（公有领域），零许可风险

⚠️ IP 锁注意：googlevideo 直链绑定请求 IP——
    服务器解析的直链给用户手机可能 403。
    结果里带 notice 提示；文件下载的彻底解法是扩展端（App/PC 本机跑 yt-dlp）。

依赖：venv 装 yt-dlp（requirements 已含）；服务器需可直连 youtube.com。
"""
from __future__ import annotations

from ..base import BaseParser
from . import IntlParserMixin
from . import ytdlp_engine


class YouTubeParser(IntlParserMixin, BaseParser):
    method_label = 'ytdlp'
    """YouTube（yt-dlp 引擎封装，纯解析不落盘）"""

    name = 'youtube'
    domains = ['youtube.com', 'youtu.be', 'm.youtube.com',
               'www.youtube.com', 'music.youtube.com']

    async def parse(self, text: str, quality: str = '1080p') -> dict:
        from ...parsers.base import URL_RE
        raw = text or ''
        m = URL_RE.search(raw)
        url = m.group(0) if m else raw.strip()

        result = await ytdlp_engine.extract(url, 'youtube')
        if not result:
            return {
                'success': False, 'platform': 'youtube',
                'error': ('YouTube 解析失败——确认链接有效、服务器可直连 '
                          'youtube.com，且 yt-dlp 为最新版（pip -U yt-dlp）'),
            }

        # IP 锁提示：progressive 直链可能对用户设备不可用
        result.setdefault('notices', []).append(
            'YouTube 直链与解析出口 IP 绑定，手机直接下载可能失败——'
            '建议保存后在电脑浏览器打开链接，或等待 App 端版本')
        return result
