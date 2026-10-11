"""
B站解析器（Playwright 常驻浏览器）
数据来源：window.__playinfo__（B站只对真实浏览器注入）
无水印地址：data.dash.video[].baseUrl（多档），音频 dash.audio[].baseUrl
"""
import asyncio
import json
import re

from playwright.async_api import async_playwright

from .base import BaseParser

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

RE_BV = re.compile(r'BV[0-9A-Za-z]{10}')
RE_AV = re.compile(r'av(\d{6,})')


class BilibiliParser(BaseParser):
    name = 'bilibili'
    domains = ['bilibili.com', 'b23.tv', 'bili2233.cn', 'acg.tv']

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._ready = False
        self._lock = asyncio.Lock()
        self.stats = {'ok': 0, 'fail': 0, 'last_error': None, 'started_at': None}

    async def start(self):
        if self._ready:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            channel='chrome', headless=self.headless,
            args=['--disable-blink-features=AutomationControlled'])
        self._ctx = await self._browser.new_context(
            user_agent=UA, viewport={'width': 1400, 'height': 900},
            locale='zh-CN', timezone_id='Asia/Shanghai',
            extra_http_headers={'Accept-Language': 'zh-CN,zh;q=0.9'})
        self._page = await self._ctx.new_page()
        await self._page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        try:
            await self._page.goto('https://www.bilibili.com/',
                                  wait_until='domcontentloaded', timeout=45000)
        except Exception:
            pass
        await self._page.wait_for_timeout(8000)
        self._ready = True
        import time
        self.stats['started_at'] = time.time()

    async def stop(self):
        if self._ready:
            try:
                await self._browser.close()
                await self._pw.stop()
            except Exception:
                pass
            self._ready = False

    async def health(self) -> dict:
        if not self._ready:
            return {'ready': False, 'platform': self.name}
        try:
            ck = await self._ctx.cookies()
            names = {c['name'] for c in ck}
            return {'ready': True, 'platform': self.name,
                    'cookie_count': len(ck),
                    'has_buvid': 'buvid3' in names,
                    'ok': self.stats['ok'], 'fail': self.stats['fail']}
        except Exception as e:
            return {'ready': False, 'platform': self.name, 'error': str(e)[:80]}

    async def parse(self, share_text: str, quality: str = '1080p') -> dict:
        url = self.extract_url(share_text)
        if not url:
            return {'success': False, 'error': '未识别到链接'}
        if not self.match(url):
            return {'success': False, 'error': '不是B站链接'}

        try:
            await self.start()
        except Exception as e:
            return {'success': False, 'error': f'浏览器启动失败: {str(e)[:80]}'}

        try:
            async with self._lock:
                data = await self._extract(self._page, url, quality)
        except Exception as e:
            self.stats['fail'] += 1
            self.stats['last_error'] = str(e)[:200]
            return {'success': False, 'error': f'解析异常: {str(e)[:100]}'}

        if not data or not data.get('success'):
            self.stats['fail'] += 1
            self.stats['last_error'] = (data or {}).get('error')
            return data or {'success': False, 'error': '解析失败'}
        self.stats['ok'] += 1
        return data

    async def _extract(self, page, url: str, quality: str):
        # 短链跳转
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)

        vid = RE_BV.search(page.url) or RE_AV.search(page.url)
        if not vid:
            return {'success': False,
                    'error': '链接跳转后未找到 BV/AV 号（可能是动态页或已失效）'}
        vid = vid.group(0)
        page_url = (f'https://www.bilibili.com/video/{vid}'
                    if vid.startswith('BV') else
                    f'https://www.bilibili.com/video/av{vid[2:]}')

        await page.goto(page_url, wait_until='domcontentloaded', timeout=40000)
        await page.wait_for_timeout(6000)

        raw = await page.evaluate("""() => {
            const pi = window.__playinfo__;
            const st = window.__INITIAL_STATE__;
            if (!pi) return {err:'no playinfo'};
            const d = pi.data || pi;
            const vd = (st && st.videoData) || {};
            return {
                play: {
                    quality: d.quality,
                    accept: d.accept_quality,
                    acceptDesc: d.accept_description,
                    dash: (d.dash && d.dash.video || []).map(v => ({
                        id: v.id, w: v.width, h: v.height, bw: v.bandwidth,
                        codec: v.codecs || '',
                        url: v.baseUrl || (v.backupUrl || [])[0] || ''
                    })),
                    audio: ((d.dash && d.dash.audio) || []).map(a => ({
                        id: a.id, bw: a.bandwidth,
                        url: a.baseUrl || (a.backupUrl || [])[0] || ''
                    })),
                    durl: (d.durl || []).map(x => ({
                        url: x.url || '', size: x.size, len: x.length
                    }))
                },
                meta: {
                    title: vd.title || '', pic: vd.pic || '',
                    up: (vd.owner || {}).name || '',
                    duration: vd.duration || 0,
                    aid: vd.aid || '', bvid: vd.bvid || ''
                }
            };
        }""")

        if raw.get('err'):
            return {'success': False, 'error': '未找到 __playinfo__（B站风控或结构变更）'}

        play = raw.get('play') or {}
        meta = raw.get('meta') or {}
        vids = [v for v in (play.get('dash') or []) if v.get('url')]

        # 老格式 durl 兜底
        if not vids and play.get('durl'):
            d0 = play['durl'][0]
            vids = [{'id': 0, 'w': 0, 'h': 0, 'bw': 0, 'codec': 'flv',
                     'url': d0['url']}]
        if not vids:
            return {'success': False, 'error': 'playinfo 里无视频数据'}

        # 排序：分辨率 → 编码兼容(H.264优先) → 码率
        vids.sort(
            key=lambda v: ((v.get('w') or 0) * (v.get('h') or 0),
                           1 if 'avc1' in (v.get('codec') or '') else 0,
                           v.get('bw') or 0),
            reverse=True)

        want = {'1080p': 1080, '720p': 720, '480p': 480, '360p': 360}.get(quality, 1080)
        chosen = next((v for v in vids if v.get('h') == want), None) or vids[0]

        auds = play.get('audio') or []
        pic = meta.get('pic') or ''

        return {
            'success': True,
            'platform': 'bilibili',
            'type': 'video',
            'bvid': meta.get('bvid') or (vid if vid.startswith('BV') else None),
            'aid': meta.get('aid') or (vid[2:] if vid.startswith('av') else None),
            'title': meta.get('title') or '',
            'author': meta.get('up') or '',
            'cover': pic if pic.startswith('http') else ('https:' + pic if pic else ''),
            'duration_ms': (meta.get('duration') or 0) * 1000 or None,
            'video_url': chosen['url'],
            'quality': f"{chosen.get('h')}P" if chosen.get('h') else None,
            'size': chosen.get('bw'),
            'options': [{
                'id': v.get('id'), 'width': v.get('w'), 'height': v.get('h'),
                'codec': (v.get('codec') or '').split('.')[0],
                'bit_rate': v.get('bw'), 'url': v['url'],
            } for v in vids],
            'audio_url': auds[0]['url'] if auds else None,
            'accept_quality': play.get('acceptDesc') or [],
            # ⚠️ B站特有约束，客户端必须知道
            'dash': bool(auds),          # 音视频分离，需合并
            'need_proxy': True,          # CDN 域名带随机性，必须服务端中转
            'cdn_hosts': sorted({_host(v['url']) for v in vids}),
            'max_height': max((v.get('h') or 0) for v in vids) or None,
            'anonymous': True,           # 未登录只给 480P
            'note': ('B站为音视频分离(dash)，小程序端需服务端合并；'
                     'CDN 域名随机，必须中转；匿名会话上限 480P'),
        }


def _host(url: str) -> str:
    m = re.match(r'https?://([^/]+)', url or '')
    return m.group(1) if m else ''
