"""
抖音解析器（Playwright 常驻浏览器）

已验证：2026-10-04 / aweme_id 7692364828996128121
  首次 3.67s，后续 2.87~3.05s，20 档无水印地址
"""
import asyncio
import json
import re
import time

from playwright.async_api import async_playwright

from .base import BaseParser

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

ID_RE = re.compile(r'/video/(\d{6,})')
NOTE_RE = re.compile(r'/(?:note|slides)/(\d{6,})')

DETAIL_API = '/aweme/v1/web/aweme/detail/'

GEAR_PREF = {
    'origin': 'origin',
    '1080p': '1080',
    '720p': '720',
    '540p': '540',
}


class DouyinParser(BaseParser):
    name = 'douyin'
    domains = ['douyin.com', 'iesdouyin.com', 'v.douyin.com']

    def __init__(self, headless: bool = True, instance_id: int = 0):
        self.headless = headless
        self.instance_id = instance_id
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._ready = False
        self._lock = asyncio.Lock()
        self.stats = {'ok': 0, 'fail': 0, 'last_error': None,
                      'last_ok_at': None, 'started_at': None}

    async def start(self):
        if self._ready:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            channel='chrome',
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled'],
        )
        self._ctx = await self._browser.new_context(
            user_agent=UA, viewport={'width': 1400, 'height': 900})
        self._page = await self._ctx.new_page()
        await self._page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        try:
            await self._page.goto('https://www.douyin.com/',
                                  wait_until='domcontentloaded', timeout=45000)
        except Exception:
            pass
        await self._page.wait_for_timeout(10000)
        self._ready = True
        self.stats['started_at'] = time.time()

    async def stop(self):
        if self._ready:
            try:
                await self._browser.close()
                await self._pw.stop()
            except Exception:
                pass
            self._ready = False

    async def restart(self):
        await self.stop()
        await self.start()

    async def health(self) -> dict:
        if not self._ready:
            return {'ready': False, 'instance': self.instance_id}
        try:
            cookies = await self._ctx.cookies()
            names = {c['name'] for c in cookies}
            return {
                'ready': True,
                'instance': self.instance_id,
                'cookie_count': len(cookies),
                'has_ttwid': 'ttwid' in names,
                'has_s_v_web_id': 's_v_web_id' in names,
                'ok': self.stats['ok'],
                'fail': self.stats['fail'],
                'uptime_s': int(time.time() - (self.stats['started_at'] or time.time())),
                'last_error': self.stats['last_error'],
                'last_ok_at': self.stats['last_ok_at'],
            }
        except Exception as e:
            return {'ready': False, 'instance': self.instance_id,
                    'error': str(e)[:120]}

    async def parse(self, share_text: str, quality: str = '1080p') -> dict:
        url = self.extract_url(share_text)
        if not url:
            return {'success': False, 'error': '未识别到链接'}

        try:
            await self.start()
        except Exception as e:
            return {'success': False, 'error': f'浏览器启动失败: {str(e)[:80]}'}

        try:
            async with self._lock:
                detail = await self._fetch(self._page, url)
        except Exception as e:
            self.stats['fail'] += 1
            self.stats['last_error'] = str(e)[:200]
            return {'success': False, 'error': f'解析异常: {str(e)[:100]}'}

        if not detail:
            self.stats['fail'] += 1
            self.stats['last_error'] = '接口无数据'
            return {'success': False,
                    'error': '解析失败，链接可能已删除、设为私密或平台接口已变更'}

        self.stats['ok'] += 1
        self.stats['last_ok_at'] = time.time()
        return normalize(detail, quality)

    async def _fetch(self, page, url: str):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)

        m = ID_RE.search(page.url) or NOTE_RE.search(page.url)
        if not m:
            return None
        aid = m.group(1)

        raw = await page.evaluate(
            """async ({aid, api}) => {
                const p = new URLSearchParams({
                    device_platform:'webapp', aid:'6383',
                    channel:'channel_pc_web',
                    version_code:'190500', version_name:'19.5.0',
                    browser_language:'zh-CN', browser_platform:'Win32',
                    browser_name:'Chrome', browser_version:'140.0.0.0',
                    aweme_id: aid
                });
                const r = await fetch(api + '?' + p.toString(),
                                     {credentials:'include'});
                return await r.text();
            }""", {'aid': aid, 'api': DETAIL_API})

        if not raw or not raw.strip():
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None


def normalize(d: dict, quality: str = '1080p') -> dict:
    """统一响应结构 —— 已迁移到 normalize_douyin.py

    保留此函数名只为向后兼容（历史测试与调用方都从这导入）。
    实际实现见 app/parsers/normalize_douyin.py，那是唯一事实源。
    之所以抽出去：normalize 是纯函数，却因为和 playwright 顶层耦合
    导致「没装 playwright 就连单元测试都跑不起来」。
    """
    from .normalize_douyin import normalize as _impl
    return _impl(d, quality)
