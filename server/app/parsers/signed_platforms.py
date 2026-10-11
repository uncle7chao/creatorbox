"""
小红书 / 快手 解析器骨架
========================
⚠️ 2026-10-04 实测：两个平台均需请求签名，本文件记录已确认的事实与待实现部分。

实测结论
--------
小红书：
  - 访问 /explore 被重定向到登录页（前端登录墙）
  - 内部 API 全部 500 "create invoker failed, service: jarvis-gateway-default"
    → 网关拒绝未签名请求
  - 需要 x-s / x-t 签名（JS 逆向，与抖音 a_bogus 同类问题）

快手：
  - 无登录墙，能到 /new-reco，9 个 cookie（含 did / clientid / kwssectoken）
  - /rest/v/feed/hot 返回 {"result":11, "error_msg":"请检查下网络连接是否正常"}
    → 同样需要 __clientid / GraphQL 签名
  - 已知快手无水印地址字段名为 srcNoWatermark（社区已知，需实测确认）

可行实施路径
------------
A. 签名逆向（与抖音 a_bogus 同性质）
   - 小红书 x-s：JS 混淆，逆向成本高
   - 快手 __clientid：相对简单
   → 需持续维护，平台改版即失效

B. 页面内提取（推荐先试，成本最低）
   - 打开详情页 → 等 JS 渲染 → 从 DOM/内存提取已加载的无水印地址
   - 优点：不需要逆向签名，因为页面自己会请求
   - 缺点：慢（5-8s/次）、依赖页面结构

C. 只做抖音（当前状态）
   - 已验证可用，先上线验证需求
   - 小红书/快手放到 v2
"""
import asyncio
import json
import re

from playwright.async_api import async_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

XHS_RE = re.compile(
    r'https?://(?:xhslink\.com/[A-Za-z0-9/]+|'
    r'www\.xiaohongshu\.com/(?:explore|discovery/item)/[A-Za-z0-9]+)')
KS_RE = re.compile(
    r'https?://(?:www\.kuaishou\.com/short-video/[\w-]+|'
    r'v\.kuaishou\.com/[A-Za-z0-9]+)')


class SignedPlatformParser:
    """需签名平台的基类：页面内提取模式（B方案）"""

    name = 'base'
    domains: list[str] = []
    home = ''
    id_re = re.compile(r'/(\d{16,})')

    def __init__(self, headless=True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._ready = False
        self._lock = asyncio.Lock()

    def match(self, url: str) -> bool:
        return any(d in url for d in self.domains)

    async def start(self):
        if self._ready:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            channel='chrome', headless=self.headless,
            args=['--disable-blink-features=AutomationControlled'])
        self._ctx = await self._browser.new_context(
            user_agent=UA, viewport={'width': 1400, 'height': 900})
        self._page = await self._ctx.new_page()
        await self._page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        try:
            await self._page.goto(self.home,
                                  wait_until='domcontentloaded', timeout=45000)
        except Exception:
            pass
        await self._page.wait_for_timeout(8000)
        self._ready = True

    async def stop(self):
        if self._ready:
            try:
                await self._browser.close()
                await self._pw.stop()
            except Exception:
                pass
            self._ready = False

    async def health(self) -> dict:
        return {'ready': self._ready, 'platform': self.name}

    async def parse(self, share_text: str, quality: str = '1080p') -> dict:
        """B 方案：打开详情页后从渲染结果提取"""
        m = re.search(r'https?://[^\s，。、"\')）)】\]]+', share_text or '')
        if not m:
            return {'success': False, 'error': '未识别到链接'}
        url = m.group(0)
        if not self.match(url):
            return {'success': False, 'error': f'不是{self.name}链接'}

        try:
            await self.start()
        except Exception as e:
            return {'success': False, 'error': f'浏览器启动失败: {str(e)[:80]}'}

        async with self._lock:
            data = await self._extract(self._page, url)

        if not data:
            return {'success': False,
                    'error': f'{self.name} 解析失败，可能需要登录或接口已变更'}
        return data

    async def _extract(self, page, url):
        raise NotImplementedError


class XhsParser(SignedPlatformParser):
    name = 'xiaohongshu'
    domains = ['xiaohongshu.com', 'xhslink.com']
    home = 'https://www.xiaohongshu.com/'

    async def _extract(self, page, url):
        # 短链先在浏览器里跳转
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=40000)
        except Exception:
            pass
        await page.wait_for_timeout(8000)

        if 'login' in page.url:
            return {'success': False, 'error': '小红书要求登录（游客态无法解析）'}

        # 从 __INITIAL_STATE__ 提取
        return await page.evaluate("""() => {
            const html = document.documentElement.outerHTML;
            const m = html.match(/window\\.__INITIAL_STATE__\\s*=\\s*\\{/);
            if (!m) return null;
            let i = m.index + m[0].length - 1, depth = 0;
            for (let k = i; k < html.length; k++) {
                if (html[k] === '{') depth++;
                else if (html[k] === '}') { depth--; if (!depth) {
                    try { return JSON.parse(html.slice(i, k + 1).replace(/undefined/g,'null')); }
                    catch(e) { return null; }
                }}
            }
            return null;
        }""")


class KuaishouParser(SignedPlatformParser):
    name = 'kuaishou'
    domains = ['kuaishou.com', 'chenzhongtech.com', 'gifshow.com']
    home = 'https://www.kuaishou.com/'

    async def _extract(self, page, url):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=40000)
        except Exception:
            pass
        await page.wait_for_timeout(7000)

        # 快手详情页数据在 __APOLLO_STATE__ 或 window.INIT_STATE
        return await page.evaluate("""() => {
            const html = document.documentElement.outerHTML;
            for (const key of ['__APOLLO_STATE__', '__INIT_STATE__', 'INIT_STATE']) {
                const m = html.match(new RegExp('window\\\\.' + key + '\\\\s*=\\\\s*\\\\{'));
                if (!m) continue;
                let i = m.index + m[0].length - 1, depth = 0;
                for (let k = i; k < html.length; k++) {
                    if (html[k] === '{') depth++;
                    else if (html[k] === '}') { depth--; if (!depth) {
                        try { return {key, data: JSON.parse(
                            html.slice(i, k+1).replace(/undefined/g,'null'))}; }
                        catch(e) { break; }
                    }}
                }
            }
            return null;
        }""")


# 已知字段（待实测确认）
KS_NOWATERMARK_FIELD = 'srcNoWatermark'
XHS_IMAGE_FIELDS = ['urlDefault', 'url', 'urlPre']
XHS_VIDEO_FIELDS = ['originVideoKey', 'videoUrl', 'masterUrl']
