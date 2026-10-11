"""抖音纯 HTTP 解析器（无浏览器依赖）

来源：读wujunwei928/parse-video-py 源码发现的关键参数
     GET /web/api/v2/aweme/slidesinfo/?aweme_ids=%5B{id}%5D
     注意是 aweme_ids=数组格式（复数），不是 aweme_id=单数

实测（2026-10-05）：
- 视频：status_code=0 + aweme_details[0]，play_addr/bit_rate 全档无水印
- 图集：images[].url_list，过滤 webp 取首个可用
- 纯 urllib，无 cookie、无签名、无浏览器，3 秒内完成

保留 Playwright 实现作为兜底（本文件纯 HTTP 优先，失败自动降级）
"""
from __future__ import annotations

import asyncio
import gzip
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# 移动端 UA —— 抖音 v2 接口对 iOS UA 最宽容
MOBILE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 '
    'Mobile/15E148 Safari/604.1'
)

URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')

SHORT_DOMAINS = ('v.douyin.com',)


def extract_url(text: str) -> Optional[str]:
    """从分享口令里提取短链（排除中文标点）"""
    m = URL_RE.search(text or '')
    return m.group(0) if m else None


async def resolve_short_url(url: str, timeout: int = 15,
                            retries: int = 3) -> Dict[str, str]:
    """跟随 302 拿最终地址与 aweme_id

    短链 v.douyin.com/xxx/ → www.iesdouyin.com/share/video/{id}/...

    ⚠️ 2026-10-05 加重试：原来 `except Exception: final = url` 是**静默兜底**，
    网络抖动时短链解析失败 → aweme_id 为空 → 后面两条通道都拿不到数据 →
    报「两条纯 HTTP 通道均无数据」，这个错误信息完全指不到真因
    （实测 8 用例回归时偶发一次，直接调用重试又正常）。
    → 现在失败会重试，重试仍失败才兜底，并记录 attempts。
    """
    loop = asyncio.get_event_loop()

    def _do() -> Dict[str, str]:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                # 只跟随一次，手动读 Location
                raise urllib.error.HTTPError(
                    req.full_url, code, msg, headers, fp)

        final = url
        attempts = 0
        last_err = ''
        for i in range(max(1, retries)):
            attempts += 1
            opener = urllib.request.build_opener(NoRedirect)
            req = urllib.request.Request(
                url, headers={'User-Agent': MOBILE_UA})
            try:
                r = opener.open(req, timeout=timeout)
                final = r.geturl()
                break
            except urllib.error.HTTPError as e:
                loc = e.headers.get('Location') if e.headers else None
                if loc:
                    final = loc
                    break
                # 4xx/5xx 不重试（重试也不会好），只记录
                last_err = f'HTTP {e.code}'
                if e.code and 400 <= e.code < 500:
                    break
            except Exception as e:
                # 网络类异常（超时/连接重置/DNS）→ 值得重试
                last_err = f'{type(e).__name__}: {str(e)[:50]}'

        out = {'final_url': final, 'attempts': attempts}
        m = re.search(r'/(?:video|note|slides)/(\d+)', final)
        if not m:
            m = re.search(r'[?&]aweme_id=(\d+)', final) or \
                re.search(r'modal_id=(\d+)', final)
        out['aweme_id'] = m.group(1) if m else ''
        if not out['aweme_id']:
            out['error'] = last_err or '短链未返回 302，且无法提取 aweme_id'
        return out

    return await loop.run_in_executor(None, _do)


def _pick_image_url(im: Dict[str, Any]) -> Optional[str]:
    """图集取图：小程序 saveImageToPhotosAlbum 不支持 webp

    url_list 里的模板标记：
      ~tplv-dy-aweme-images → 原始图（无水印）
      ~tplv-dy-water-v2     → 下载版（底部有账号水印）← 必须排除
    """
    cands = list(im.get('url_list') or []) or \
        list(im.get('download_url_list') or [])
    if not cands:
        return None
    # 优先 jpeg
    jpeg = next((u for u in cands
                 if '.jpeg' in u or '.jpg' in u), None)
    # 其次非 webp
    plain = next((u for u in cands if '.webp' not in u), None)
    # 再次排除带 water 模板的
    nowm = next((u for u in cands if 'dy-water' not in u), None)
    return jpeg or nowm or plain or cands[0]


def _gear_to_h(gear: str, idx: int, qtype: int) -> int:
    """bit_rate 档位名 → 高度（px）"""
    m = re.match(r'(\d{3,4})_', gear or '')
    if m:
        return int(m.group(1))
    return {11: 480, 12: 480, 22: 540, 23: 540,
            40: 720, 41: 720, 42: 720}.get(qtype, 720)


def normalize_v2(a: Dict[str, Any], quality: str = '1080p',
                  want_h: int = 1080) -> Dict[str, Any]:
    """v2 接口响应 → 统一返回结构"""
    aweme_id = str(a.get('aweme_id') or '')
    media_type = a.get('media_type')
    images = a.get('images') or []
    author_obj = a.get('author') or {}
    author = author_obj.get('nickname') or ''
    cover_list = ((a.get('video') or {}).get('cover') or {}).get('url_list') or []
    cover = next((u for u in cover_list if '.webp' not in u),
                 cover_list[0] if cover_list else '')
    stats = a.get('statistics') or {}
    avatar_list = (author_obj.get('avatar_thumb') or {}).get('url_list') or []
    # ---- BGM 提取（2026-10-11，二创人群拿背景音乐）----
    # v2 slidesinfo 与 detail 两条通道的响应都带 music 对象，
    # play_url.url_list[0] 即音频直链（mp3/m4a，有时效但可复解析刷新）
    music = a.get('music') or {}
    music_urls = (music.get('play_url') or {}).get('url_list') or []

    base: Dict[str, Any] = {
        'success': True,
        'platform': 'douyin',
        'method': 'pure_http_v2',
        'aweme_id': aweme_id,
        'title': (a.get('desc') or '').strip(),
        # ---- 元信息（2026-10-05 补齐）----
        # ⚠️ 抖音的标题与文案是同一个字段 desc，视频没有独立标题
        #   → description 留空，前端不要重复显示。
        'description': a.get('preview_title') or '',
        'author': author,
        'author_id': str(author_obj.get('uid') or
                         author_obj.get('sec_uid') or ''),
        'author_avatar': next((u for u in avatar_list
                               if '.jpeg' in u or '.jpg' in u),
                              avatar_list[0] if avatar_list else ''),
        'cover': cover,
        'duration_ms': (a.get('video') or {}).get('duration'),
        'publish_time_ts': a.get('create_time'),      # Unix 秒
        'like_count': stats.get('digg_count'),
        'comment_count': stats.get('comment_count'),
        'collect_count': stats.get('collect_count'),
        'share_count': stats.get('share_count'),
        'view_count': stats.get('play_count'),
        # ---- BGM（2026-10-11）----
        'music_title': (music.get('title') or '').strip(),
        'music_author': (music.get('author') or {}).strip(),
        'music_url': next((u for u in music_urls if u), ''),
        'music_duration_ms': music.get('duration'),
    }

    # ---------- 图集 ----------
    if media_type == 68 or images:
        imgs: List[Dict[str, Any]] = []
        for im in images:
            u = _pick_image_url(im)
            if not u:
                continue
            res = im.get('resolution_log_param') or {}
            imgs.append({
                'url': u,
                'width': im.get('width') or res.get('image_publish_width'),
                'height': im.get('height') or res.get('image_publish_height'),
                'format': 'jpeg' if ('.jpeg' in u or '.jpg' in u) else 'webp',
            })
        base.update({
            'type': 'image',
            'video_url': None,
            'quality': None,
            'images': imgs,
            'image_count': len(imgs),
            'watermark_free': all('dy-water' not in i['url']
                                  for i in imgs) if imgs else None,
        })
        return base

    # ---------- 视频 ----------
    v = a.get('video') or {}
    options: List[Dict[str, Any]] = []
    for i, o in enumerate(v.get('bit_rate') or []):
        ul = (o.get('play_addr') or {}).get('url_list') or []
        if not ul:
            continue
        # 抖音 v2 返回的地址已是 tos 路径（无 playwm），选 https 优先
        pick = next((x for x in ul if x.startswith('https://')), ul[0])
        options.append({
            'index': i,
            'gear': o.get('gear_name') or '',
            'width': None,
            'height': _gear_to_h(o.get('gear_name') or '',
                                  i, o.get('quality_type') or 0),
            'bit_rate': o.get('bit_rate'),
            'no_watermark': 'playwm' not in pick,
            'url': pick,
        })

    # 老式 play_addr 兜底（通常是最高或默认档）
    pal = (v.get('play_addr') or {}).get('url_list') or []
    if pal and not options:
        pick = next((x for x in pal if x.startswith('https://')), pal[0])
        options.append({
            'index': 0, 'gear': 'default', 'width': None, 'height': 720,
            'bit_rate': v.get('bit_rate') or 0,
            'no_watermark': 'playwm' not in pick,
            'url': pick,
        })

    if not options:
        return {'success': False, 'platform': 'douyin',
                'error': '未取到可用视频地址', 'aweme_id': aweme_id}

    # ---- 清晰度升级（L3）----
    # v2 的 bit_rate 数组实测最高只到 720_3_1，要1080P 必须走 play 接口
    uri = (v.get('play_addr') or {}).get('uri')
    max_h = max((o['height'] or 0) for o in options)
    extra: Dict[str, Any] = {}

    if want_h > max_h and uri:
        up_url = _play_api_uri(uri, f'{want_h}p')
        if up_url:
            options.append({
                'index': len(options), 'gear': f'{want_h}p(play-api)',
                'width': None, 'height': want_h, 'bit_rate': None,
                'no_watermark': 'playwm' not in up_url,
                'url': up_url, 'via': 'play_api',
            })
            chosen = options[-1]
            extra = {'quality_upgraded_via': 'play_api',
                     'max_quality_bitrate': f'{max_h}P'}
        else:
            chosen = max(options, key=lambda o: (o['height'] or 0))
            extra = {'quality_note': f'请求 {want_h}P 不可得，'
                                     f'实发 {chosen["height"]}P'}
    else:
        # 选档：不低于 want_h 的最小档，否则取最大的
        cand = [o for o in options if (o['height'] or 0) >= want_h]
        chosen = min(cand, key=lambda o: o['height']) if cand else \
            max(options, key=lambda o: (o['height'] or 0))

    base.update({
        'type': 'video',
        'video_url': chosen['url'],
        'quality': f"{chosen['height']}P",
        'max_quality_free': f'{max_h}P',
        'options': options,
        'options_count': len(options),
        'watermark_free': all(o['no_watermark'] for o in options),
    })
    base.update(extra)
    return base


def _play_api_uri(uri: str, ratio: str = '1080p',
                  timeout: int = 15) -> Optional[str]:
    """L3 清晰度升级：uri + ratio → 302 到真实 mp4

    技巧来自 lzwme/m3u8-dl 的 douyin-parser.ts（第 36 行）。
    实测 ratio=1080p → 1920x1080（31.9MB），ratio=720p → 1280x720（23.2MB）。
    这是免费拿到 1080P 的唯一通道。
    """
    api = (f'https://www.iesdouyin.com/aweme/v1/play/'
           f'?video_id={uri}&ratio={ratio}&line=0')

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise urllib.error.HTTPError(req.full_url, code, msg,
                                         headers, fp)

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(urllib.request.Request(
            api, headers={'User-Agent': MOBILE_UA}), timeout=timeout)
        return None                      # 未重定向，属意外
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return e.headers.get('Location') if e.headers else None
        return None
    except Exception:
        return None


class DouyinPureParser:
    """纯 HTTP 抖音解析器 —— 无 Playwright、无登录 cookie

    三级通道（都纯 HTTP）：
      L1  v2 slidesinfo（免 cookie 免签名）→ 短视频基本信息0.6s
      L2  detail + a_bogus（ttwid + SM3签名）→ 图集 / L1 兜底 1.0s
      L3  play_addr.uri + /aweme/v1/play/?ratio=  → 任意清晰度（最高 1080P）

    L3 技巧来自 lzwme/m3u8-dl 的 douyin-parser.ts：
        https://www.iesdouyin.com/aweme/v1/play/
          ?video_id={play_addr.uri}&ratio=1080p&line=0
        接口 302 跳转到真实 mp4，ratio 可指定 1080p/720p/540p。
        ⚠️ v2 接口的 bit_rate 数组里没有 1080P 档（实测最高 720_3_1），
           但 L3 能拿到真 1080P —— 这是清晰度上限的唯一来源。

    实测 2026-10-05：视频、图集、1080P 全部纯 HTTP 跑通
    """

    name = 'douyin_pure'
    domains = ('douyin.com', 'iesdouyin.com', 'amemv.com')

    # uvd 的关键反直觉点：msToken 传空串 + 只带 ttwid + Chrome 90 UA
    UA_PC = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 '
             'Safari/537.36')

    COMMON_PARAMS = {
        'device_platform': 'webapp', 'aid': '6383',
        'channel': 'channel_pc_web', 'pc_client_type': '1',
        'version_code': '290100', 'version_name': '29.1.0',
        'cookie_enabled': 'true', 'screen_width': '1920',
        'screen_height': '1080', 'browser_language': 'zh-CN',
        'browser_platform': 'Win32', 'browser_name': 'Chrome',
        'browser_version': '130.0.0.0', 'browser_online': 'true',
        'engine_name': 'Blink', 'engine_version': '130.0.0.0',
        'os_name': 'Windows', 'os_version': '10', 'cpu_core_num': '12',
        'device_memory': '8', 'platform': 'PC', 'downlink': '10',
        'effective_type': '4g', 'round_trip_time': '0',
    }

    def __init__(self):
        self._ttwid = ''
        self._ttwid_at = 0.0
        self._ok = 0
        self._fail = 0

    def match(self, url: str) -> bool:
        return 'douyin' in url or 'iesdouyin' in url

    async def health(self) -> Dict[str, Any]:
        # 纯 HTTP 解析器无需预热，只要类可实例化即为就绪
        return {
            'ready': True,
            'method': 'pure_http(v2 + a_bogus)',
            'cookie': 'ttwid',
            'ok': self._ok, 'fail': self._fail,
            'browser': False,
            'ttwid': bool(self._ttwid),
        }

    # ---------- ttwid ----------
    async def _get_ttwid(self) -> str:
        loop = asyncio.get_event_loop()
        now = asyncio.get_event_loop().time()
        if self._ttwid and (now - self._ttwid_at) < 20 * 3600:
            return self._ttwid
        try:
            self._ttwid = await loop.run_in_executor(
                None, lambda: _register_ttwid())
            self._ttwid_at = now
        except Exception:
            self._ttwid = ''
        return self._ttwid

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        url = extract_url(text)
        if not url:
            return {'success': False, 'error': '未识别到链接',
                    'platform': 'douyin'}

        info = await resolve_short_url(url)
        aweme_id = info.get('aweme_id')
        if not aweme_id:
            return {'success': False, 'platform': 'douyin',
                    'error': '短链未解析出 aweme_id',
                    'final_url': info.get('final_url')}

        want_h = {'1080p': 1080, '720p': 720, '540p': 540,
                  '480p': 480}.get((quality or '').lower(), 1080)

        loop = asyncio.get_event_loop()

        # ---- L1: v2 slidesinfo（免签名，最快）----
        data = await loop.run_in_executor(
            None, lambda: _fetch_v2(aweme_id))
        method = 'pure_http_v2'

        # ---- L2: detail + a_bogus（v2 对图集无效，走这条）----
        if not data or not data.get('images') and (
                not data.get('video', {}).get('bit_rate')):
            ttwid = await self._get_ttwid()
            d2 = await loop.run_in_executor(
                None, lambda: _fetch_detail(
                    aweme_id, ttwid, self.COMMON_PARAMS, self.UA_PC))
            if d2:
                data = d2
                method = 'pure_http_a_bogus'

        # ---- L3: ttwid 失效自救（2026-10-07 实测新增）----
        # 实测：ttwid 被抖音提前作废时，两通道拿不到数据，而缓存 20h
        # 不刷新 → 服务一直撞墙（本次 down 持续到进程重启才恢复）。
        # 自救：两通道全空 → 作废缓存 ttwid、重新注册、重试一轮。
        if not data:
            self._ttwid = ''
            self._ttwid_at = 0.0
            ttwid2 = await self._get_ttwid()
            if ttwid2:
                data = await loop.run_in_executor(
                    None, lambda: _fetch_v2(aweme_id))
                if not data or not data.get('images') and (
                        not data.get('video', {}).get('bit_rate')):
                    d3 = await loop.run_in_executor(
                        None, lambda: _fetch_detail(
                            aweme_id, ttwid2, self.COMMON_PARAMS, self.UA_PC))
                    if d3:
                        data = d3
                        method = 'pure_http_a_bogus(ttwid_refresh)'

        if not data:
            self._fail += 1
            # ⚠️ 错误信息必须指向真因：如果 aweme_id 都没拿到，
            #    问题在「短链解析」而不是「两个接口都挂了」——
            #    原先一律报"两条通道均无数据"，排障时完全指不到方向。
            if not aweme_id:
                why = info.get('error') or '短链未返回 302'
                err = f'短链解析失败（尝试 {info.get("attempts", 0)} 次）：{why}'
            else:
                err = ('两条纯 HTTP 通道均无数据'
                       f'（aweme_id={aweme_id}，可能是内容已删除或接口变更）')
            return {'success': False, 'platform': 'douyin',
                    'method': method,
                    'error': err,
                    'aweme_id': aweme_id}

        self._ok += 1
        r = normalize_v2(data, quality, want_h)
        r['method'] = method
        r['short_url'] = url
        r['fallback_url'] = info.get('final_url')
        return r


def _register_ttwid(timeout: int = 15) -> str:
    """免登取 ttwid（uvd 方案，来自 bytedance 官方注册接口）"""
    body = json.dumps({
        'region': 'cn', 'aid': 1768,
        'service': 'www.ixigua.com', 'union': True,
    }).encode()
    req = urllib.request.Request(
        'https://ttwid.bytedance.com/ttwid/union/register/',
        data=body,
        headers={'Content-Type': 'application/json',
                 'User-Agent': 'Mozilla/5.0'})
    r = urllib.request.urlopen(req, timeout=timeout)
    ck = r.headers.get('Set-Cookie') or ''
    for part in ck.split(';'):
        p = part.strip()
        if p.startswith('ttwid='):
            return p.split('=', 1)[1]
    return ''


def _fetch_detail(aweme_id: str, ttwid: str, common: Dict[str, str],
                  ua: str, timeout: int = 20) -> Optional[Dict[str, Any]]:
    """detail 接口 + a_bogus 签名

    关键三点（缺一即返回空 body，实测踩过）：
      1. msToken 必须传空字符串
      2. Cookie 只带 ttwid，多带反而触发风控
      3. UA 用 Chrome 90（旧版本反而更安全）
    """
    try:
        from .abogus import ABogusSigner
    except ImportError:
        from abogus import ABogusSigner

    p = dict(common)
    p['aweme_id'] = aweme_id
    p['msToken'] = ''
    qs = urllib.parse.urlencode(p)

    sig = ABogusSigner().sign(qs)          # 签名基于签名前的同一份 qs
    url = f'https://www.douyin.com/aweme/v1/web/aweme/detail/?{qs}&a_bogus={sig}'

    headers = {
        'User-Agent': ua,
        'Referer': 'https://www.douyin.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    if ttwid:
        headers['Cookie'] = f'ttwid={ttwid}'

    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=timeout)
        raw = r.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        if not raw.strip():
            return None
        d = json.loads(raw.decode('utf-8', 'ignore'))
    except Exception:
        return None

    if d.get('status_code') != 0:
        return None
    return d.get('aweme_detail') or None


def _fetch_v2(aweme_id: str, timeout: int = 20) -> Optional[Dict[str, Any]]:
    """调 v2 接口。

    关键：参数是 aweme_ids=数组格式（复数），不能用 aweme_id=单数。
    实测单数格式返回 status_code=0 但 aweme_details=null（空）。
    """
    api = ('https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/'
           f'?aweme_ids=%5B{aweme_id}%5D')
    req = urllib.request.Request(
        api, headers={'User-Agent': MOBILE_UA,
                      'Accept': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        d = json.loads(raw.decode('utf-8', 'ignore'))
    except Exception:
        return None

    if d.get('status_code') != 0:
        return None
    details = d.get('aweme_details')
    if isinstance(details, list):
        return details[0] if details else None
    if isinstance(details, dict):
        return details
    return None


# 供独立测试
if __name__ == '__main__':
    import sys
    import time

    async def main():
        t0 = time.time()
        p = DouyinPureParser()
        txt = sys.argv[1] if len(sys.argv) > 1 else \
            'https://v.douyin.com/ntaaK4aH9pE/'
        q = sys.argv[2] if len(sys.argv) > 2 else '1080p'
        r = await p.parse(txt, q)
        print(f'耗时 {time.time() - t0:.2f}s')
        print('success    :', r.get('success'))
        print('method     :', r.get('method'))
        print('type       :', r.get('type'))
        print('title      :', (r.get('title') or '')[:48])
        print('author     :', r.get('author'))
        print('quality    :', r.get('quality'))
        print('watermark_free:', r.get('watermark_free'))
        if r.get('type') == 'image':
            print('image_count:', r.get('image_count'))
            for i, im in enumerate((r.get('images') or [])[:3]):
                print(f"  [{i+1}] {im['width']}x{im['height']} {im['format']}")
                print('     ', im['url'][:96])
        else:
            print('options    :', r.get('options_count'))
            for o in (r.get('options') or [])[:5]:
                print(f"  {o['gear']:12s} {o['height']}P无水印={o['no_watermark']}")
            print('video_url  :', (r.get('video_url') or '')[:110])
        if not r.get('success'):
            print('error      :', r.get('error'))

    asyncio.run(main())