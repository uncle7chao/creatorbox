# -*- coding: utf-8 -*-
"""Facebook 解析器（2026-10-11 spike 结论落地）。

零自研：yt-dlp 自带 FacebookIE/FacebookReelIE（5 个 FB extractor），
本解析器只做域名匹配 + 路由到 ytdlp_engine 万能兜底。

⚠️ spike 实测（2026-10-11）：facebook.com/mbasic/m 全部被墙（000 超时），
   沙箱无法真网验证——**部署机必须能直连 FB（香港服务器 ✅）**。
   生态情报（Universal-Video-Downloader 排障表）：2025 起 FB 渐严，
   公开视频 yt-dlp 多数可用，Reels 部分需登录 Cookie——失败时
   报错文案引导用户，不做 Cookie 池（合规边界）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..base import BaseParser
from . import IntlParserMixin
from . import ytdlp_engine


class FacebookParser(IntlParserMixin, BaseParser):
    name = 'facebook'
    method_label = 'ytdlp'
    domains = ['facebook.com', 'www.facebook.com', 'm.facebook.com',
               'mbasic.facebook.com', 'fb.watch']

    def match(self, url: str) -> bool:
        u = (url or '').lower()
        return any(d in u for d in self.domains)

    async def parse(self, text: str, quality: str = '1080p') -> Dict[str, Any]:
        from ...parsers.base import URL_RE
        raw = text or ''
        m = URL_RE.search(raw)
        url = m.group(0) if m else raw.strip()

        if not ytdlp_engine.available():
            return {'success': False, 'platform': 'facebook',
                    'error': '服务端未安装 yt-dlp（pip install -U yt-dlp）'}

        result: Optional[Dict[str, Any]] = await ytdlp_engine.extract(url, 'facebook')
        if result:
            return result

        return {'success': False, 'platform': 'facebook',
                'error': 'Facebook 解析失败：仅支持公开视频/Reel，'
                         '且部署服务器需可直连 Facebook（需境外网络出口）。'
                         '登录墙内容与私密视频不支持。'}


if __name__ == '__main__':
    import sys
    import asyncio
    p = FacebookParser()
    print('name:', p.name)
    for u in ('https://www.facebook.com/watch/?v=100000000000000',
              'https://fb.watch/abcd1234/',
              'https://youtube.com/watch?v=x'):
        print(u[:50], '→ match:', p.match(u))
    if len(sys.argv) > 1:                      # 真网验证入口（HK 服务器）
        r = asyncio.run(p.parse(sys.argv[1]))
        print('success:', r.get('success'), '| title:', (r.get('title') or '')[:50])
        print('subtitle:', (r.get('subtitle_lang') or '无'),
              '| 字幕字数:', len(r.get('subtitle_text') or ''))
