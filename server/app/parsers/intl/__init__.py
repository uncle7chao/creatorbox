# -*- coding: utf-8 -*-
"""国际平台解析器包（2026-10-11）

命名空间：parsers/intl/ —— TikTok / X / YouTube / Facebook
与国内解析器完全同构（BaseParser 接口），由 main.py 池按 config.INTL_ENABLED 挂载。

可用性分层：
    自研通道（x_pure syndication / tiktok tikwm）→ yt-dlp 万能兜底
    （yt-dlp 未安装时兜底层静默不可用，不影响前两层）

许可注意：本包全部自写；yt-dlp 为 Unlicense；未引用 JoeanAmier/TwiGram（GPL）代码。
"""


class IntlParserMixin:
    """国际解析器公共 health 实现（pool.health 会对每个 pure 解析器调 health）。

    纯解析无预热，类可实例化即就绪；与国内 pure 解析器口径一致。
    子类需提供类属性 method_label（如 'syndication/fxtwitter/ytdlp'）。
    """

    method_label = 'intl'

    async def health(self) -> dict:
        return {
            'ready': True,
            'method': self.method_label,
            'ok': getattr(self, '_ok', 0),
            'fail': getattr(self, '_fail', 0),
            'browser': False,
            'intl': True,
        }

