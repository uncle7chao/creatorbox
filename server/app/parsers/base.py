"""解析器基类与注册表"""
import re
from typing import Optional

URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')


class BaseParser:
    """所有平台解析器的基类"""

    name = 'base'
    domains: list[str] = []

    def match(self, url: str) -> bool:
        return any(d in url for d in self.domains)

    async def parse(self, share_text: str, quality: str = '1080p') -> dict:
        raise NotImplementedError

    @staticmethod
    def extract_url(text: str) -> Optional[str]:
        m = URL_RE.search(text or '')
        return m.group(0) if m else None


class ParserRegistry:
    """按域名分发到对应解析器"""

    def __init__(self):
        self._parsers: list[BaseParser] = []

    def register(self, p: BaseParser):
        self._parsers.append(p)
        return p

    def pick(self, url: str) -> Optional[BaseParser]:
        for p in self._parsers:
            if p.match(url):
                return p
        return None

    def names(self) -> list[str]:
        return [p.name for p in self._parsers]
