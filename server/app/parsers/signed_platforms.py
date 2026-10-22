"""
需签名 / 需浏览器渲染的平台解析器（方案 B：页面内提取）
============================================================

⚠️ 2026-10-22 实测重做。原骨架（2026-10-04 写）有**三处致命问题**，
   每一处都会导致「明明浏览器能打开，解析器却说失败」。

一、为什么需要浏览器
------------------
小红书的笔记数据**不在 SSR 里**：
  · 纯 HTTP 抓 /discovery/item/{id}?xsec_token=...
    → __INITIAL_STATE__ 里 noteData 是**空数组**、notFoundPage=true
    → 笔记数据全靠前端 XHR 异步拉
  · 桌面 UA → 302 跳登录墙
  · iOS UA  → 纯 HTTP 能过（200），但内容同样是空的

⚠️ 最坑的地方：**接口 200、日志干净、字段齐全**，表现却与「笔记不存在」
   一模一样 —— 会把人一直引向错误方向。

实测（2026-10-22，用户给的未登录分享视频链接）：
  纯 HTTP      → notFoundPage=true，noteData=[]，22KB
  真实 Chrome  → 标题「阿姨：这下我想报警了」，视频直链 13.1MB ✅

二、原骨架的三处致命问题
------------------------
1. **headless=True** → 被小红书风控识别，页面跳「安全限制」/404
   ✅ 修复：headed 模式（headless=False）。有头浏览器指纹完整，风控过不了。

2. **channel='chrome'** → 用的是 Playwright 自带的 Chromium，
   与用户本机真实 Chrome 的指纹不同 → 同样触发风控
   ✅ 修复：显式指定系统 Chrome 可执行路径（executable_path），
             找不到时回退 channel='chrome'。

3. **只从 __INITIAL_STATE__ 提取** → 该对象含**循环引用**，
   JSON.parse 直接抛「Converting circular structure to JSON」；
   且视频直链根本不在 state 里，而在**页面发出的网络请求**中
   （<video>.src 是 blob:，是 MSE 流式播放，真实地址在请求 URL 里）
   ✅ 修复：监听 network request，收集 sns-video / .mp4 直链；
             同时用「安全 JSON 序列化」读 state 里的标题等元信息。

三、还有一处误判逻辑
------------------
原代码：`if 'login' in page.url: return 失败`
实测：带 redirectPath 参数的正常笔记页 URL 里也含 'login'（如
  /login?redirectPath=...  →  跳回来是 /explore/{id}）
→ 用它判「要求登录」会误伤。
✅ 修复：判「最终停在登录页」而不是「URL 里出现过 login」。

四、成本与取舍（必须诚实）
--------------------------
浏览器通道**慢**（约 8~12s/次，比纯 HTTP 的 1~2s 慢一个数量级）
且吃内存（一个 Chromium 实例约 150~300MB）。
所以：
  · 只在【纯 HTTP 通道已确认拿不到】时启用（小红书就是这样）
  · 浏览器实例**复用**（启动一次，解析多次），不每次起进程
  · 解析失败不重试到浏览器 —— 避免把慢路径扩散到所有平台
  · 生产环境需要显式开关（CB_BROWSER_PARSER=1），默认关闭：
    服务器上开有头浏览器需要图形环境/虚拟显示，且内存成本高。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

# ── UA ────────────────────────────────────────────────────────────
# 用真实 Chrome 的 UA（headless 也填这个，让服务端看到的是常规浏览器）
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# ── 系统 Chrome 可执行路径候选（Windows 优先）─────────────────────
_CHROME_CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]


def find_system_chrome() -> Optional[str]:
    """找系统已装的浏览器可执行文件。

    ⭐ 为什么要用系统的而不是 Playwright 自带的：
       小红书风控会看浏览器指纹，自带 Chromium 的指纹与真实 Chrome 不同，
       实测会被判「安全限制」。系统 Chrome 是用户天天在用的那个，最像真人。
    """
    env = os.getenv('CB_CHROME_PATH', '').strip()
    if env and os.path.exists(env):
        return env
    for p in _CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


# ── 页面内安全求值脚本 ────────────────────────────────────────────
# 循环引用的 state 不能直接 JSON.stringify，用 WeakSet 去重兜底。
_SAFE_STATE_JS = """
() => {
  const seen = new WeakSet();
  const safe = (obj) => {
    if (obj === null || typeof obj !== 'object') return obj;
    if (seen.has(obj)) return '[Circular]';
    seen.add(obj);
    if (Array.isArray(obj)) return obj.map(safe);
    const o = {};
    for (const k of Object.keys(obj)) o[k] = safe(obj[k]);
    return o;
  };
  const out = { title: document.title, url: location.href, note: null };
  try {
    const raw = window.__INITIAL_STATE__;
    if (raw) {
      const st = safe(raw);
      // 笔记容器在小红书是 note.noteDetailMap[noteId].note
      const ndm = st && st.note && st.note.noteDetailMap;
      if (ndm) {
        for (const k of Object.keys(ndm)) {
          const n = ndm[k] && ndm[k].note;
          if (n) {
            out.note = {
              id: k,
              title: n.title || '',
              desc: (n.desc || '').slice(0, 2000),
              type: n.type || '',
              author: (n.user && (n.user.nickname || n.user.name)) || '',
              images: ((n.imageList || n.imagesList) || [])
                        .map(i => i && (i.url || i.urlDefault)).filter(Boolean)
                        .slice(0, 20),
              hasVideo: !!(n.video && n.video.media),
            };
            break;
          }
        }
      }
    }
  } catch (e) { out.stateErr = String(e).slice(0, 160); }
  return JSON.stringify(out);
}
"""


class SignedPlatformParser:
    """需浏览器渲染的平台基类：打开页面 → 收集网络直链 → 提取元信息。

    浏览器实例**复用**（start 时创建，stop 时销毁），
    解析用锁串行化（同一个 page 不能并发导航）。
    """

    name = 'base'
    domains: List[str] = []
    home = ''

    # 等待时长：实测小红书前端解密+渲染需要 8~12s
    wait_ms = 10000
    nav_timeout = 45000

    def __init__(self, headless: bool = False):
        # ⭐ 默认 headed —— headless 会被小红书风控判「安全限制」。
        #   服务端无图形环境时由部署方显式传 headless=True 并配 Xvfb。
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._ready = False
        self._lock = asyncio.Lock()

    def match(self, url: str) -> bool:
        return any(d in url for d in self.domains)

    async def start(self) -> None:
        if self._ready:
            return
        self._pw = await async_playwright().start()
        exe = find_system_chrome()
        launch_kwargs: Dict[str, Any] = {
            'headless': self.headless,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
        }
        if exe:
            launch_kwargs['executable_path'] = exe
        else:
            # 找不到系统浏览器 → 回退自带内核（可能被风控，但至少能跑）
            launch_kwargs['channel'] = 'chrome'
        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        self._ctx = await self._browser.new_context(
            user_agent=UA, viewport={'width': 1400, 'height': 1000},
            locale='zh-CN')
        # 抹掉自动化标记
        await self._ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        self._page = await self._ctx.new_page()
        self._ready = True

    async def stop(self) -> None:
        if self._ready:
            try:
                if self._browser:
                    await self._browser.close()
                if self._pw:
                    await self._pw.stop()
            except Exception:
                pass
        self._ready = False
        self._browser = None
        self._pw = None
        self._page = None

    async def health(self) -> dict:
        return {'ready': self._ready, 'platform': self.name,
                'headless': self.headless,
                'chrome': bool(find_system_chrome())}

    async def parse(self, share_text: str, quality: str = '1080p') -> dict:
        m = re.search(r'https?://[^\s，。、"\')）)】\]]+', share_text or '')
        if not m:
            return {'success': False, 'platform': self.name,
                    'error': '未识别到链接'}
        url = m.group(0)
        if not self.match(url):
            return {'success': False, 'platform': self.name,
                    'error': f'不是{self.name}链接'}

        try:
            await self.start()
        except Exception as e:
            return {'success': False, 'platform': self.name,
                    'error': f'浏览器启动失败: {str(e)[:100]}'}

        async with self._lock:
            try:
                data = await self._extract(self._page, url)
            except Exception as e:
                return {'success': False, 'platform': self.name,
                        'error': f'页面处理失败: {str(e)[:100]}'}
        return data

    async def _extract(self, page, url):
        raise NotImplementedError


class XhsParser(SignedPlatformParser):
    """小红书：视频/图集笔记 —— 从网络请求里取直链。

    ⭐ 为什么从【网络请求】取而不是从 __INITIAL_STATE__ 取：
       视频走 MSE 流式播放，<video>.src 是 blob:，
       真实 mp4 地址是页面自己发出的请求 URL；
       __INITIAL_STATE__ 里只有元信息（标题/作者/类型），
       而且该对象含循环引用，直接 JSON.parse 会抛异常。
    """

    name = 'xiaohongshu'
    domains = ['xiaohongshu.com', 'xhslink.com']
    home = 'https://www.xiaohongshu.com/'

    # 视频直链的特征
    _VIDEO_HINT = ('sns-video', '.mp4')
    # 图片直链的特征
    _IMG_HINT = ('sns-img', 'sns-webpic')

    async def _extract(self, page, url):
        captured: List[str] = []

        async def on_request(req):
            u = req.url
            if any(h in u for h in self._VIDEO_HINT) or \
               any(h in u for h in self._IMG_HINT):
                if u not in captured:
                    captured.append(u)

        page.on('request', on_request)
        try:
            try:
                await page.goto(url, wait_until='domcontentloaded',
                                timeout=self.nav_timeout)
            except Exception:
                pass
            await page.wait_for_timeout(self.wait_ms)

            final_url = page.url
            title = await page.title()

            # ⭐ 登录判定修正：看【最终停在哪个路径】，
            #   而不是「URL 里出现过 login」——
            #   带 redirectPath 的正常笔记 URL 里也含 login（会误伤）。
            if '/login' in final_url and 'redirectPath' not in final_url:
                return {'success': False, 'platform': self.name,
                        'error': '小红书要求登录（游客态无法解析该链接）'}

            meta: Dict[str, Any] = {}
            try:
                raw = await page.evaluate(_SAFE_STATE_JS)
                meta = json.loads(raw)
            except Exception:
                meta = {}

            note = meta.get('note') or {}
            videos = [u for u in captured if any(h in u for h in self._VIDEO_HINT)]
            images = [u for u in captured if any(h in u for h in self._IMG_HINT)]

            # 封面：从页面里取第一张非头像图片（头像 URL 含 /avatar/）
            cover = ''
            try:
                cover = await page.evaluate(
                    """() => {
                      const imgs = [...document.querySelectorAll('img')]
                        .map(i => i.src)
                        .filter(s => s && (s.includes('sns-img') ||
                                           s.includes('sns-webpic')));
                      for (const s of imgs) if (!s.includes('/avatar/')) return s;
                      return imgs[0] || '';
                    }""")
            except Exception:
                pass

            if not videos and not images:
                return {
                    'success': False, 'platform': self.name,
                    'error': ('页面已打开但没抓到素材直链'
                              '（笔记可能需登录、已删除，或平台改了接口）'),
                    'page_title': title, 'final_url': final_url[:200],
                    'captured': len(captured),
                }

            is_video = bool(videos)
            # 视频档位：小红书通常只有单档；多段就都列上
            options: List[Dict[str, Any]] = []
            for i, v in enumerate(dict.fromkeys(videos)):
                options.append({
                    'index': i, 'gear': '原画' if i == 0 else f'源{i+1}',
                    'label': '原画' if i == 0 else f'源{i+1}',
                    'url': v, 'height': None, 'bitrate': None,
                })

            title_text = (note.get('title') or '').strip()
            if not title_text:
                # state 里没有标题就用 <title>（去掉「 - 小红书」后缀）
                title_text = re.sub(r'\s*[-|]\s*小红书.*$', '', title or '').strip()

            return {
                'success': True,
                'platform': self.name,
                'type': 'video' if is_video else 'image',
                'title': title_text or '（无标题）',
                'description': note.get('desc') or '',
                'author_name': note.get('author') or '',
                'cover': cover,
                'video_url': options[0]['url'] if is_video else '',
                'images': [{'url': u} for u in dict.fromkeys(images)],
                'options': options,
                'options_count': len(options),
                'method': 'browser_cdp',
                'page_url': final_url[:300],
            }
        finally:
            try:
                page.remove_listener('request', on_request)
            except Exception:
                pass


class KuaishouParser(SignedPlatformParser):
    """快手：骨架保留，尚未做端到端验证。

    ⚠️ 诚实状态：快手纯 HTTP 通道（kuaishou_pure.py）已可用且实测通过，
       本浏览器通道只是备选，**没有端到端验证**，
       启用前必须先跑通再放进 pool —— 否则会用一个未验证的路径
       去覆盖一个已验证的路径。
    """

    name = 'kuaishou'
    domains = ['kuaishou.com', 'chenzhongtech.com', 'gifshow.com']
    home = 'https://www.kuaishou.com/'

    async def _extract(self, page, url):
        return {'success': False, 'platform': self.name,
                'error': '快手浏览器通道尚未验证，请使用纯 HTTP 通道'}
