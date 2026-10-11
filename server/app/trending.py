"""热门榜单（M1.5 屏 6）

设计要点：
- 数据源用各平台「官方公开热榜 API」，纯 HTTP（与解析器同通道，无浏览器依赖）
- 统一条目结构（客户端一套渲染逻辑通吃所有平台）：
    { rank, title, author, hot, hot_text, cover, url }
  其中 url 必须是本服务 /api/parse 可直接消化的链接 —— 保证「解析同款」闭环
- 缓存 10 分钟（config.CACHE_TTL，与解析缓存同实例）：
  榜单是只读展示，不买会员不加签，靠缓存扛量，2C2G 上零成本
- 未接入平台返回 not_implemented（客户端渲染「接入中」态），不造假数据

已接入：
- bilibili  api.bilibili.com/x/web-interface/popular（与 bilibili_pure 同域同风格，
  实测 code=0 返回 20 条，bvid 可构造 https://www.bilibili.com/video/{bvid} 进解析）

暂缓：
- douyin / kuaishou：热榜条目是「话题词」且无 ID（2026-10-07 实测：抖音搜索接口
  被风控 2483、快手无公开热榜接口），拿不到可解析链接，不硬接。

已接入（2026-10-07）：
- weibo  weibo.com/ajax/side/hotSearch（50 词）→ 配 Cookie 后逐词查
  m.weibo.cn 话题接口 → 只取 page_info.type=='video' 的微博 →
  objectid（1034:xxx）构造 https://weibo.com/tv/show/{oid} 进解析器
  （weibo_pure 主通道正是 oid + component API，闭环成立）。
  未配 Cookie → need_cookie 语义，客户端弹窗说明。
已接入（2026-10-08）：
- xhs  小红书「热点榜」词条形态：搜索框热榜 XHR（/api/sns/web/v1/search/hotlist）
  需要 Cookie + x-s 签名 → 签名由页面 JS 自算，不逆向：
  无头浏览器注入服务端 Cookie（与解析共用 CB_XHS_COOKIE）→ 拦截自家 XHR。
  热词无笔记 ID → type='word'（复制关键词去小红书搜，同抖音/快手）。
  缓存 TTL 内只开一次浏览器。
"""
import asyncio
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

try:
    from app import config
    from app.cache import cache
    from app.parsers import bilibili_pure
except ImportError:                                  # 直接跑脚本时
    import config
    from cache import cache
    from parsers import bilibili_pure

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

_WB_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
          'Mobile/15E148 Safari/604.1')


class NeedCookieError(RuntimeError):
    """平台热榜需要登录态（服务端未配 Cookie）"""


def _wb_json(url: str, cookie: str, timeout: int = 12) -> Dict[str, Any]:
    """带 Cookie 的 JSON GET（微博两域共用一个 Cookie）"""
    req = urllib.request.Request(url, headers={
        'User-Agent': _WB_UA,
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest',
        'Cookie': cookie,
        'Referer': 'https://m.weibo.cn/',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


_TAG = re.compile(r'<[^>]+>')


def _wb_resolve_word(word: str, hot: int, cookie: str) -> Dict[str, Any]:
    """一个热搜词 → 第一条「带视频的微博」条目；找不到返回 None"""
    q = urllib.parse.quote(f'#{word}#')
    try:
        j = _wb_json('https://m.weibo.cn/api/container/getIndex'
                     '?containerid=100103type%3D1%26q%3D' + q
                     + '&page_type=searchall', cookie)
    except Exception:
        return None
    for card in (j.get('data') or {}).get('cards') or []:
        mb = card.get('mblog') or {}
        pi = mb.get('page_info') or {}
        if pi.get('type') != 'video':
            continue
        oid = (pi.get('objectid')
               or (pi.get('media_info') or {}).get('media_id') or '')
        if not oid:
            continue
        if ':' not in oid:                        # 有的只给纯数字 media_id
            oid = f'1034:{oid}'
        title = _TAG.sub('', mb.get('text') or word).strip()
        return {
            'title': title[:60] or word,
            'author': (mb.get('user') or {}).get('screen_name') or '',
            'hot': int(hot or 0),
            'hot_text': _fmt_count(int(hot or 0)),
            'cover': (pi.get('page_pic') or {}).get('url') or '',
            'url': f'https://weibo.com/tv/show/{oid}',
        }
    return None


# ── B 站热门榜 ──────────────────────────────────────────────

def _fetch_bilibili_sync() -> List[Dict[str, Any]]:
    d = bilibili_pure._get(
        'https://api.bilibili.com/x/web-interface/popular?ps=20',
        referer='https://www.bilibili.com/')
    if d.get('code') != 0:
        raise RuntimeError(f"bilibili popular code={d.get('code')}")
    items: List[Dict[str, Any]] = []
    for i, it in enumerate((d.get('data') or {}).get('list') or [], 1):
        bvid = it.get('bvid') or ''
        if not bvid:
            continue
        stat = it.get('stat') or {}
        view = int(stat.get('view') or 0)
        items.append({
            'rank': len(items) + 1,          # 跳过无 bvid 条目后仍连续
            'title': (it.get('title') or '').strip(),
            'author': (it.get('owner') or {}).get('name') or '',
            'hot': view,
            'hot_text': _fmt_count(view),
            'cover': it.get('pic') or '',
            'url': f'https://www.bilibili.com/video/{bvid}',
        })
    if len(items) < 5:
        raise RuntimeError(f'bilibili popular 仅 {len(items)} 条，疑似结构变更')
    return items


# ── 微博热榜 ────────────────────────────────────────────────

def _fetch_weibo_sync() -> List[Dict[str, Any]]:
    cookie = (config.WEIBO_COOKIE or '').strip()
    if not cookie:
        raise NeedCookieError(
            '微博热榜需要登录态：请在服务端配置 CB_WEIBO_COOKIE'
            '（电脑登录 weibo.com → F12 → Network → 复制 Cookie）')
    d = _wb_json('https://weibo.com/ajax/side/hotSearch', cookie)
    realtime = ((d.get('data') or {}).get('realtime')) or []
    words = [(r.get('word') or '', r.get('num') or 0)
             for r in realtime if r.get('word')][:15]
    if not words:
        raise RuntimeError('weibo hotSearch 返回空，疑似结构变更')

    # 5 并发换词 → 带视频的微博（保证每条都能进解析）
    with ThreadPoolExecutor(max_workers=5) as ex:
        resolved = list(ex.map(lambda w: _wb_resolve_word(w[0], w[1], cookie),
                               words))
    items: List[Dict[str, Any]] = []
    for r in resolved:
        if r:
            r['rank'] = len(items) + 1
            items.append(r)
        if len(items) >= 10:
            break
    if len(items) < 3:
        raise RuntimeError(f'weibo 仅换出 {len(items)} 条视频微博，'
                           '疑似 Cookie 失效或接口变更')
    return items


# ── 平台注册表（新增平台 = 加一行 + 一个 _fetch_xxx_sync）──

def _fetch_douyin_sync() -> List[Dict[str, Any]]:
    """抖音「热点榜」——词条形态（2026-10-07 用户拍板上线）

    数据源：iesdouyin 官方公开词榜（实测 HTTP 200、50 条、含热度与封面）。
    ⚠️ 词条无 aweme_id（搜索接口补 ID 被风控 2483），所以条目
    url 留空 + type='word' —— 客户端渲染为「复制关键词去搜」，
    不假装能解析（闭环承诺不破坏：能解析的榜走 video 型）。
    """
    d = bilibili_pure._get(
        'https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/',
        referer='https://www.douyin.com/')
    if d.get('status_code') != 0:
        raise RuntimeError(f'douyin word榜 status={d.get("status_code")}')
    items: List[Dict[str, Any]] = []
    for w in (d.get('word_list') or [])[:20]:
        word = (w.get('word') or '').strip()
        if not word:
            continue
        hot = int(w.get('hot_value') or 0)
        cover = ((w.get('word_cover') or {}).get('url_list') or [''])[0]
        items.append({
            'rank': len(items) + 1,
            'title': word,
            'author': '',
            'hot': hot,
            'hot_text': _fmt_count(hot),
            'cover': cover,
            'url': '',
            'type': 'word',          # 客户端按词条渲染（复制去搜）
        })
    if len(items) < 5:
        raise RuntimeError(f'douyin word榜仅 {len(items)} 条，疑似结构变更')
    return items


def _fetch_html(url: str, referer: str, timeout: int = 20) -> str:
    """通用 HTML 拉取（gzip 解压；快手/其它 SSR 页用）

    ⚠️ 必须用桌面 UA：快手按 UA 差异化响应，iPhone UA 拿到的首页
    没有热榜模块（实测 rank-container 缺失）。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/126.0.0.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': referer,
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


_KS_ITEM = re.compile(
    r'class="rank-name"[^>]*>\s*([^<]+?)\s*</a>.*?([\d\.]+)万热度', re.S)


def _fetch_kuaishou_sync() -> List[Dict[str, Any]]:
    """快手「热点榜」——词条形态（2026-10-07 用户发现首页热榜模块）

    数据源：快手官网首页 SSR（?isHome=1）——热榜模块直接在 HTML 里
    （rank-item 结构：词条名 + /search/ 链接 + 万热度）。实测 50 条。
    ⚠️ 链接是搜索页非视频 → type='word'，与抖音热点榜同形态：
    客户端点击=复制关键词去快手搜，不假装能解析。
    """
    html = _fetch_html('https://www.kuaishou.com/?isHome=1&source=NewReco',
                       'https://www.kuaishou.com/')
    if 'rank-container' not in html:
        raise RuntimeError('快手首页无热榜模块，疑似改版')
    items: List[Dict[str, Any]] = []
    for block in re.split(r'<div class="rank-item"', html)[1:]:
        name = _KS_ITEM.search(block)
        if not name:
            continue
        word = name.group(1).strip()
        if not word:
            continue
        # ⚠️ 收录条件 = 块内有热度值：置顶推广位（rank-top-0）天然无热度被过滤，
        # 10+ 位次无 rank-top-N 类也不能用作判断；SSR 首屏只渲染 10 条
        hot = float(name.group(2)) * 10000
        items.append({
            'rank': len(items) + 1,
            'title': word,
            'author': '',
            'hot': int(hot),
            'hot_text': f'{name.group(2)}万',
            'cover': '',
            'url': '',
            'type': 'word',
        })
        if len(items) >= 10:
            break
    if len(items) < 5:
        raise RuntimeError(f'快手热榜仅 {len(items)} 条，疑似结构变更')
    return items


def _fetch_acfun_sync() -> List[Dict[str, Any]]:
    """AcFun 日榜——视频型（2026-10-07 无头浏览器抓到端点后接入）

    数据源：rest/pc-direct/rank/channel（榜单页 XHR，30 条）。
    条目含 dougaId（视频 ID）→ url = acfun.cn/v/ac{dougaId}，
    AcFun 解析器现成 → 视频榜闭环（与 B 站同款：点击直接解析）。
    """
    d = bilibili_pure._get(
        'https://www.acfun.cn/rest/pc-direct/rank/channel'
        '?channelId=&subChannelId=&rankLimit=30&rankPeriod=DAY',
        referer='https://www.acfun.cn/rank/list/')
    if d.get('result') != 0:
        raise RuntimeError(f'acfun rank result={d.get("result")}')
    items: List[Dict[str, Any]] = []
    for r in (d.get('rankList') or []):
        vid = str(r.get('dougaId') or r.get('contentId') or '')
        if not vid or not vid.isdigit():
            continue
        view = int(r.get('viewCount') or 0)
        items.append({
            'rank': len(items) + 1,
            'title': (r.get('contentTitle') or '').strip()[:60],
            'author': ((r.get('user') or {}).get('name') or '').strip(),
            'hot': view,
            'hot_text': _fmt_count(view),
            'cover': r.get('coverUrl') or '',
            'url': f'https://www.acfun.cn/v/ac{vid}',
            'type': 'video',
        })
        if len(items) >= 20:
            break
    if len(items) < 5:
        raise RuntimeError(f'acfun rank 仅 {len(items)} 条，疑似结构变更')
    return items


# ── 小红书热榜（词条型，浏览器通道）────────────────────────

_XHS_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
           'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 '
           'Safari/537.36')
_XHS_HOTLIST_XHR = re.compile(r'/api/sns/web/v1/search/hotlist')

# 浏览器单例（与 bilibili/douyin 解析器同策略：进程内复用，榜单个例共享浏览器池）
_xhs_pw = None
_xhs_browser = None


def _xhs_cookies(cookie_str: str) -> List[Dict[str, str]]:
    """「k=v; k2=v2」文本 → playwright cookie 数组（域固定 .xiaohongshu.com）"""
    out: List[Dict[str, str]] = []
    for pair in cookie_str.replace('\n', ' ').split(';'):
        pair = pair.strip()
        if '=' not in pair:
            continue
        k, _, v = pair.partition('=')
        k, v = k.strip(), v.strip()
        if k and v:
            out.append({'name': k, 'value': v,
                        'domain': '.xiaohongshu.com', 'path': '/'})
    return out


async def _fetch_xhs_async() -> List[Dict[str, Any]]:
    """小红书「热点榜」——词条形态（2026-10-08）

    为什么走浏览器：edith 接口要 Cookie **和** x-s 签名（实测无签名 406，
    纯 HTTP 逆向签名是持久战且随版本失效）。页面自己的 JS 会算好签名发
    XHR —— 无头浏览器注入 Cookie 打开 explore，拦截自家 XHR 响应即可，
    不碰签名算法（AcFun 榜单同款方法论，30 秒定位）。

    Cookie 失效判定：页面被 302 到 /login，或超时拿不到 XHR。
    热词无笔记 ID（搜索接口同样要签名，不硬解）→ type='word'，
    客户端渲染「复制关键词去小红书搜」——诚实词条，不假装能解析。
    """
    cookie = (config.XHS_COOKIE or '').strip()
    if not cookie:
        raise NeedCookieError(
            '小红书热榜需要登录态：请在服务端配置 CB_XHS_COOKIE'
            '（与解析共用同一个 Cookie：电脑登录 xiaohongshu.com → '
            'F12 → Network → 复制 Cookie）')

    global _xhs_pw, _xhs_browser
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            '小红书热榜需要 playwright：pip install playwright '
            '&& playwright install chromium')

    if _xhs_pw is None:
        _xhs_pw = await async_playwright().start()
        # channel='chromium'：用完整版 Chrome 的 headless 模式，
        # 不依赖 chromium_headless_shell（部署机少装一个 ~80MB 的包）。
        # --no-proxy-server：服务端直连，不读系统代理 —— 出口 IP 必须与
        # Cookie 的常用登录环境一致，过代理反而增大风控特征差异。
        _xhs_browser = await _xhs_pw.chromium.launch(
            headless=True, channel='chromium',
            args=['--no-proxy-server'])

    box: Dict[str, Any] = {}
    got = asyncio.Event()

    async def _sniff(resp):
        if _XHS_HOTLIST_XHR.search(resp.url or ''):
            try:
                box['json'] = await resp.json()
                got.set()
            except Exception:
                pass                    # 非 JSON 响应忽略

    ctx = await _xhs_browser.new_context(user_agent=_XHS_UA)
    await ctx.add_cookies(_xhs_cookies(cookie))
    page = await ctx.new_page()
    page.on('response',
            lambda r: asyncio.ensure_future(_sniff(r)))
    try:
        try:
            await page.goto('https://www.xiaohongshu.com/explore',
                            wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            # 无效/畸形 Cookie 会直接被服务端 5xx 拒页（ERR_HTTP_RESPONSE_CODE_FAILURE）
            raise RuntimeError(
                f'小红书页面打开失败（Cookie 失效或平台风控）: '
                f'{str(e).splitlines()[0][:80]}')
        if '/login' in (page.url or ''):
            raise NeedCookieError(
                '小红书 Cookie 已失效（被重定向到登录页），请重新配置')
        # 热榜 XHR 由搜索框触发：新版页面自动发，旧版要点一下输入框
        for sel in ('#search-input', '.search-input', 'input[placeholder]'):
            try:
                await page.click(sel, timeout=2500)
                if got.is_set():
                    break
            except Exception:
                continue                # 换下一个选择器 / 自动发的版本点不到就算了
        try:
            await asyncio.wait_for(got.wait(), timeout=12)
        except asyncio.TimeoutError:
            if '/login' in (page.url or ''):
                raise NeedCookieError('小红书 Cookie 已失效，请重新配置')
        j = box.get('json')
        if not j:
            raise RuntimeError(
                '未拦截到小红书热榜 XHR（页面结构或登录态变更）')
        if not j.get('success'):
            raise RuntimeError(
                f"xhs hotlist code={j.get('code')}（疑似 Cookie 失效或接口变更）")
        data = j.get('data') or {}
        raw = data.get('items') or data.get('hot_list') or []
        items: List[Dict[str, Any]] = []
        for w in raw:
            word = (w.get('name') or w.get('word') or '').strip()
            if not word:
                continue
            try:
                score = int(str(w.get('score') or 0))
            except ValueError:
                score = 0
            items.append({
                'rank': len(items) + 1,
                'title': word[:40],
                'author': '',
                'hot': score,
                'hot_text': _fmt_count(score) if score else '',
                'cover': w.get('icon') or '',
                'url': '',
                'type': 'word',
            })
            if len(items) >= 20:
                break
        if len(items) < 5:
            raise RuntimeError(f'小红书热榜仅 {len(items)} 条，疑似结构变更')
        return items
    finally:
        await ctx.close()


_FETCHERS = {
    'bilibili': _fetch_bilibili_sync,
    'weibo': _fetch_weibo_sync,
    'douyin': _fetch_douyin_sync,
    'kuaishou': _fetch_kuaishou_sync,
    'acfun': _fetch_acfun_sync,
    'xhs': _fetch_xhs_async,
}

# 客户端要展示「接入中」的完整平台清单
KNOWN_PLATFORMS = ['bilibili', 'douyin', 'kuaishou', 'weibo', 'acfun', 'xhs']


def _fmt_count(n: int) -> str:
    """播放量展示：1.1亿 / 234.5万 / 8,921（与 meta.stats_text 风格一致）"""
    if n >= 100_000_000:
        return f'{n / 100_000_000:.1f}亿'.replace('.0亿', '亿')
    if n >= 10_000:
        return f'{n / 10_000:.1f}万'.replace('.0万', '万')
    return f'{n:,}'


async def get_trending(platform: str) -> Dict[str, Any]:
    """取某平台热榜（带缓存）。返回统一结构，失败抛异常由端点兜底。"""
    platform = (platform or '').strip().lower()
    if platform not in KNOWN_PLATFORMS:
        return {'ok': False, 'code': 'unknown_platform', 'platform': platform}
    if platform not in _FETCHERS:
        return {'ok': False, 'code': 'not_implemented', 'platform': platform}

    key = f'trending:{platform}'
    cached = await cache.get(key)
    if cached:
        return {'ok': True, 'platform': platform, 'cached': True, **cached}

    loop = asyncio.get_event_loop()
    try:
        fn = _FETCHERS[platform]
        if asyncio.iscoroutinefunction(fn):
            # xhs：浏览器通道，必须跑在事件循环上（不能进线程池）
            items = await fn()
        else:
            items = await loop.run_in_executor(None, fn)
    except NeedCookieError as e:
        return {'ok': False, 'code': 'need_cookie', 'platform': platform,
                'message': str(e)}
    payload = {
        'items': items,
        'updated_at': int(time.time()),
        'ttl': config.CACHE_TTL,
    }
    await cache.set(key, payload)
    return {'ok': True, 'platform': platform, 'cached': False, **payload}


# ── 自检：python app/trending.py ───────────────────────────
if __name__ == '__main__':
    async def _main():
        r = await get_trending('bilibili')
        assert r['ok'], r
        print(f"B站热榜 {len(r['items'])} 条 · cached={r['cached']}")
        for it in r['items'][:3]:
            print(f"  {it['rank']}. {it['title'][:24]} | {it['author']} "
                  f"| {it['hot_text']} | {it['url']}")
        again = await get_trending('bilibili')
        assert again['cached'] is True, '第二次应命中缓存'
        ks = await get_trending('kuaishou')
        if ks.get('ok'):
            assert ks['items'][0]['type'] == 'word', ks['items'][0]
            print(f"快手热点榜 {len(ks['items'])} 条（词条型）")
            print('  首条:', ks['items'][0]['title'][:24], '|', ks['items'][0]['hot_text'])
        else:
            print('快手热点榜不可用:', str(ks)[:80])
        dy = await get_trending('douyin')
        if dy.get('ok'):
            assert dy['items'][0]['type'] == 'word', dy['items'][0]
            print(f"抖音热点榜 {len(dy['items'])} 条（词条型，点击复制去搜）")
            print('  首条:', dy['items'][0]['title'][:24], '|', dy['items'][0]['hot_text'])
        else:
            print('抖音热点榜不可用:', str(dy)[:80])
        wb = await get_trending('weibo')
        if config.WEIBO_COOKIE:
            assert wb['ok'], str(wb)[:120]
            print(f"微博热榜 {len(wb['items'])} 条（含 Cookie 实测）")
            for it in wb['items'][:3]:
                print(f"  {it['rank']}. {it['title'][:26]} | {it['author']} "
                      f"| {it['hot_text']} | {it['url'][:52]}")
        else:
            assert wb['code'] == 'need_cookie', str(wb)[:120]
            print('微博热榜：need_cookie（未配 Cookie，语义正确）')
        xh = await get_trending('xhs')
        if config.XHS_COOKIE:
            if xh.get('ok'):
                assert xh['items'][0]['type'] == 'word', xh['items'][0]
                print(f"小红书热榜 {len(xh['items'])} 条（词条型，浏览器通道）")
                for it in xh['items'][:3]:
                    print(f"  {it['rank']}. {it['title'][:26]} | {it['hot_text']}")
            else:
                print('小红书热榜不可用（Cookie 失效或 playwright 缺失）:',
                      str(xh)[:100])
        else:
            assert xh['code'] == 'need_cookie', str(xh)[:120]
            print('小红书热榜：need_cookie（未配 Cookie，语义正确）')
        print('自检通过：缓存命中 + not_implemented/need_cookie 兜底')

    asyncio.run(_main())
