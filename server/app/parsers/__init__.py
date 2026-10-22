"""解析器包

⚠️ 2026-10-05 修复：原来这里直接 `from .douyin import DouyinParser`，
   而 douyin.py 顶层 `from playwright.async_api import async_playwright`。
   结果：**playwright 没装时，导入任何一个纯 HTTP 解析器都会炸**
   （playwright 已是可选依赖，requirements.txt 里已注释掉）。
   → 改为惰性导入 __getattr__，纯 HTTP 解析器不再依赖浏览器栈。
"""
from .base import BaseParser, ParserRegistry

__all__ = [
    'BaseParser', 'ParserRegistry',
    'DouyinPureParser', 'BilibiliPureParser', 'HaokanPureParser',
    'SohuPureParser', 'WeiboPureParser', 'AcfunPureParser',
    'XiaohongshuPureParser', 'KuaishouPureParser', 'BaiduVideoPureParser',
    'DouyinParser', 'BilibiliParser',
]

# 纯 HTTP 解析器：零浏览器依赖，可直接导入
from .douyin_pure import DouyinPureParser
from .bilibili_pure import BilibiliPureParser
from .haokan_pure import HaokanPureParser
from .sohu_pure import SohuPureParser
from .weibo_pure import WeiboPureParser
from .acfun_pure import AcfunPureParser
from .xiaohongshu_pure import XiaohongshuPureParser
from .kuaishou_pure import KuaishouPureParser
from .baidu_pure import BaiduVideoPureParser

# 浏览器解析器：惰性导入，缺 playwright 时不影响上面三个
_LAZY = {
    'DouyinParser': ('.douyin', 'DouyinParser'),
    'BilibiliParser': ('.bilibili', 'BilibiliParser'),
    'XhsParser': ('.signed_platforms', 'XhsParser'),
    'KuaishouParser': ('.signed_platforms', 'KuaishouParser'),
}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        mod, attr = _LAZY[name]
        try:
            return getattr(importlib.import_module(mod, __package__), attr)
        except ModuleNotFoundError as e:
            raise AttributeError(
                f'{name} 需要浏览器依赖（playwright），当前未安装：{e}.'
                f'纯 HTTP 解析器不受影响，可用：'
                f'DouyinPureParser / BilibiliPureParser / '
                f'HaokanPureParser / SohuPureParser'
            ) from e
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
