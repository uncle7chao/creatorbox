"""搜狐视频纯 HTTP 解析器

来源：读 wujunwei928/parse-video-py + parse-video(Go) 的 sohu 解析器，
     两个开源项目的实现**完全一致**，字段与参数也一致（无实现差异可借鉴）。

实测（2026-10-05，本机curl + Python 双重验证）
------------------------------------------------
✅ 接口可用：GET https://api.tv.sohu.com/v4/video/info/{vid}.json
   必带两个参数，缺一即返回「视频不存在」：
       ?site=2&api_key=9854b2afa779e1a6bcdd07b217417549&sver=6.2.0
   ⚠️ 早期我只传 site=2 → status=10001「视频(620254006, 2)不存在」，
      差点误判接口已死。补上 api_key + sver 后同一 ID 正常返回。
      → 这是 P3（参数格式决定成败）的又一例，id 真实存在与否要分开验证。

⛔⭐ 本平台最重要的发现：url_high_mp4 是「30 秒试看片段」，不是完整视频
   | vid          | 声明时长 | MP4 实际时长 | 声明体积 | MP4 实际体积 |
   |--------------|---------|-------------|---------|-------------|
   | 620139607    |30s      | 30.04s      | 1.76 MB | 0.45 MB     |
   | 620251480    |30s      | 30.04s      | 2.79 MB | 0.45 MB     |
   | 620253660|32s      | 30.04s      | 2.26 MB | 0.45 MB     |
   | 620253046    |**76s**  | **30.04s**  | 9.43 MB | 0.45 MB     |
   - download_url / url_high_share_mp4 是**同一个 URL**（逐字节相同）
   - 完整视频只存在于 m3u8：76s 那条 m3u8 实测 7.28 MB（12 段）
   → 结论：**30s 以内的视频 mp4 够用；超过 30s 一律被截断。**
   → 10 个开源项目（含 parse-video-py/Go）都只取 url_high_mp4，
     所以它们对 >30s 的搜狐视频都会返回残缺文件。这是全行业通病，
     不是我们的实现问题，但**我们必须显式告知用户**，否则算我们交付 defective。

⚠️ m3u8 的坑：url_high 的 /v2/play/ 路径带签名（末段 key），
   改任何一段都返回「sign field length error.」→ 不可枚举多档清晰度。
   要完整视频必须自己下分段再合并（需 ffmpeg 或 TS concat）。

⚠️ 详情页是 GB18030 编码（不是 UTF-8），且只有 15KB 空壳，
   真实数据在 hotvrs.js.tv.itc.cn 的 init_video_info.js 里（且那文件只有元数据，
   没有播放地址）。→ 走 API 路线是对的，别去解析页面。
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 '
         'Safari/537.36')

REFERER = 'https://tv.sohu.com/'

# ⚠️ 这两个参数缺一不可（实测：不带 api_key 返回「视频不存在」）
API_KEY = '9854b2afa779e1a6bcdd07b217417549'
SVER = '6.2.0'

API_TMPL = ('https://api.tv.sohu.com/v4/video/info/{vid}.json'
            '?site=2&api_key=' + API_KEY + '&sver=' + SVER)

# tv.sohu.com/v/{base64}.html → base64 解码后是 us/{uid}/{vid}.shtml
B64_URL_RE = re.compile(r'/v/([A-Za-z0-9+/=]+)\.html')
# us/{uid}/{vid}.shtml
US_URL_RE = re.compile(r'/?us/\d+/(\d+)\.shtml')
# ⚠️ 2026-10-05 实测：现在的 /v/{base64}.html 解码出来**不再是** us/...，
#    而是 {YYYYMMDD}/n{vid}.shtml（例：20261005/n620254006.shtml）
#    —— parse-video-py / parse-video(Go) 的 US_URL_RE 匹配不到这种，
#    所以开源实现对当前格式的链接会直接报「不是有效的搜狐视频链接」。
#    两种格式都留着，老链接继续能解析。
DATED_URL_RE = re.compile(r'/?\d{6,8}/n?(\d{6,})\.shtml')
# 兜底：路径里任意 9+ 位数字
LOOSE_ID_RE = re.compile(r'/(\d{9,})')

# 分享口令里提链接（排除中文标点）
URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')

# mp4 试看片段的固定上限（实测 4/4 全部恰好 30.04s / 468026 字节）
PREVIEW_SECONDS = 30
PREVIEW_BYTES = 468026

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _get(url: str, referer: str = REFERER, timeout: int = 20) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={
        'User-Agent': PC_UA,
        'Referer': referer,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    })
    r = urllib.request.urlopen(req, timeout=timeout, context=_SSL)
    raw = r.read()
    if raw[:2] == b'\x1f\x8b':          # P7: 不解压会误判无数据
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'ignore'))


def _probe_size(url: str, timeout: int = 20) -> Optional[int]:
    """用Range 探真实体积，返回 None 表示不支持/失败"""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': PC_UA, 'Referer': REFERER, 'Range': 'bytes=0-1'})
        r = urllib.request.urlopen(req, timeout=timeout, context=_SSL)
        cr = r.headers.get('Content-Range') or ''
        r.close()
        if '/' in cr:
            tail = cr.rsplit('/', 1)[-1].strip()
            if tail.isdigit():
                return int(tail)
    except Exception:
        pass
    return None


def _probe_mp4_duration(url: str, max_bytes: int = 2 << 20,
                        timeout: int = 30) -> Optional[float]:
    """读 MP4 的 mvhd box 拿真实时长（秒）—— 用于判定是否被截断

    只取前 max_bytes：moov 通常在文件头，但若在尾部则返回 None（不误判）。
    """
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': PC_UA, 'Referer': REFERER,
            'Range': f'bytes=0-{max_bytes - 1}'})
        r = urllib.request.urlopen(req, timeout=timeout, context=_SSL)
        buf = r.read(max_bytes)
        r.close()
    except Exception:
        return None
    return _mvhd_duration(buf)


def _mvhd_duration(buf: bytes) -> Optional[float]:
    """解析 mvhd box 的 timescale / duration"""
    import struct
    i = buf.find(b'mvhd')
    if i < 4:
        return None
    base = i - 4                      # box header 4 字节 type 在前
    try:
        version = buf[base + 8]
        if version == 0:
            timescale = struct.unpack('>I', buf[base + 20:base + 24])[0]
            duration = struct.unpack('>I', buf[base + 24:base + 28])[0]
        else:
            timescale = struct.unpack('>I', buf[base + 28:base + 32])[0]
            duration = struct.unpack('>Q', buf[base + 32:base + 40])[0]
    except Exception:
        return None
    if not timescale:
        return None
    return round(duration / timescale, 2)


def extract_vid(url: str) -> str:
    """从搜狐链接提取 vid

    支持三种形态（实测首页三种都有）：
      1. tv.sohu.com/v/{base64}.html   → base64 解码后再匹配
      2. my.tv.sohu.com/us/{uid}/{vid}.shtml
      3. tv.sohu.com/us/{uid}/{vid}.shtml
    """
    m = B64_URL_RE.search(url)
    if m:
        raw = m.group(1)
        pad = '=' * (-len(raw) % 4)
        try:
            decoded = base64.b64decode(raw + pad).decode('utf-8', 'ignore')
            for rex in (US_URL_RE, DATED_URL_RE, LOOSE_ID_RE):
                m2 = rex.search(decoded)
                if m2:
                    return m2.group(1)
        except Exception:
            pass
    for rex in (US_URL_RE, DATED_URL_RE, LOOSE_ID_RE):
        m = rex.search(url)
        if m:
            return m.group(1)
    return ''


def _https(u: str) -> str:
    """搜狐的CDN 大量 http 明文地址，小程序 / iOS 会拦http"""
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http://'):
        return 'https://' + u[len('http://'):]
    return u


def _parse_sync(vid: str) -> Dict[str, Any]:
    try:
        j = _get(API_TMPL.format(vid=vid))
    except Exception as e:
        return {'success': False, 'platform': 'sohu',
                'error': f'搜狐接口请求失败: {str(e)[:70]}'}

    if j.get('status') != 200:
        return {'success': False, 'platform': 'sohu',
                'error': f'搜狐接口返回 {j.get("status")}: '
                         f'{j.get("statusText", "")[:60]}',
                'hint': '若确认链接有效，多半是缺 api_key/sver 参数'}

    d = j.get('data') or {}
    mp4 = d.get('url_high_mp4') or d.get('download_url') or ''
    if not mp4:
        return {'success': False, 'platform': 'sohu',
                'error': '接口正常但未返回播放地址（该视频可能付费/已下架）',
                'tvName': d.get('video_name') or ''}

    mp4 = _https(mp4)
    claimed_dur = d.get('clips_duration_high')
    claimed_size = d.get('file_size_high') or 0
    user = d.get('user') or {}

    # ---- ⭐ 截断检测：拿 MP4 真实时长与声明时长比对 ----
    actual_dur = _probe_mp4_duration(mp4)
    truncated = False
    if actual_dur and claimed_dur:
        try:
            truncated = float(claimed_dur) - actual_dur > 2.0
        except (TypeError, ValueError):
            truncated = False

    result: Dict[str, Any] = {
        'success': True,
        'platform': 'sohu',
        'method': 'api_v4',
        'type': 'video',
        'vid': vid,
        'title': d.get('video_name') or '',
        'description': d.get('keyword') or '',      # 接口的关键词字段当文案
        'author': user.get('nickname') or '',
        'author_uid': str(user.get('user_id') or ''),
        'author_avatar': _https(user.get('small_pic') or ''),
        'author_fans': user.get('total_fans_count'),
        'publish_time_ms': d.get('publishTime'),   # Unix 毫秒
        'publish_date_text': d.get('publish_time') or '',  # "2025-02-22"
        'keyword': d.get('keyword') or '',
        'upload_region': d.get('uploadAddr') or '',
        'view_count': d.get('play_count'),
        'cover': _https(d.get('originalCutCover') or d.get('cusCoverUrlNew') or ''),
        'video_url': mp4,
        'duration_ms': int(float(claimed_dur or 0) * 1000),
        'dash': False,                # mp4 单文件含音轨
        'need_proxy': True,           # data.vod.itc.cn 带签名长URL，不适合小程序白名单
        'anonymous': True,
        'no_watermark': True,
        'watermark_free': True,
    }

    if truncated:
        actual_size = _probe_size(mp4)
        m3u8 = _https(d.get('url_high') or '')
        result.update({
            'quality': '720P',
            'truncated': True,
            'duration_actual_s': actual_dur,
            'duration_claimed_s': float(claimed_dur),
            'size': actual_size,
            'm3u8_url': m3u8,
            'merge_required': True,
            'm3u8_note': ('完整视频只在此 m3u8 中。'
                          f'声明 {claimed_size / 1048576:.2f}MB / '
                          f'实测 mp4 仅 {PREVIEW_BYTES / 1048576:.2f}MB。'
                          '需要服务端下分段合并后才能拿到完整版'),
            'user_warning': (f'该视频声明 {float(claimed_dur):.0f} 秒，'
                             f'免登录直链只能取到前 {actual_dur:.0f} 秒'
                             f'（约 {PREVIEW_SECONDS} 秒试看片段）。'
                             '要完整视频需服务端合并 m3u8 分段。'),
        })
        # ⚠️ 2026-10-05 二次实测：搜狐的 m3u8 **也是试看片段**
        #   m3u8 写 12 段、EXTINF 合计 76.85s，但**12 段 MD5 完全相同**
        #   （全是同一个 30 秒内容）→ 合并只会得到 6 分钟的重复垃圾，
        #   而 ffmpeg **不会报错**（它只按 EXTINF 累加时长）。
        #   所以这里直接告诉调用方：合并救不了这个平台的长视频。
        result['m3u8_usable'] = False
        result['m3u8_blocked_reason'] = (
            '实测该 m3u8 的全部分段内容相同（同一段试看内容重复 N 次），'
            '合并无意义。搜狐长视频需登录态才能拿到完整版')
        result['m3u8_note'] += '。⚠️ 但实测 m3u8 分段内容重复，合并无效'
    else:
        result.update({
            'quality': '720P',
            'truncated': False,
            'duration_actual_s': actual_dur,
            'size': _probe_size(mp4) or claimed_size,
        })

    result['options'] = [{
        'index': 0, 'gear': '720P', 'width': 1280, 'height': 720,
        'bit_rate': None, 'no_watermark': True, 'url': mp4,
    }]
    result['options_count'] = 1
    return result


class SohuPureParser:
    """纯 HTTP 搜狐视频解析 —— 无浏览器、无签名"""

    name = 'sohu_pure'
    domains = ('sohu.com',)

    @staticmethod
    def extract_url(text: str) -> str:
        m = URL_RE.search(text or '')
        return m.group(0) if m else ''

    def match(self, url: str) -> bool:
        return 'sohu.com' in url

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        url = self.extract_url(text)
        if not url:
            return {'success': False, 'platform': 'sohu',
                    'error': '未识别到链接'}
        if not self.match(url):
            return {'success': False, 'platform': 'sohu',
                    'error': '不是搜狐视频链接'}
        vid = extract_vid(url)
        if not vid:
            return {'success': False, 'platform': 'sohu',
                    'error': f'未能从链接提取 vid: {url[:60]}'}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _parse_sync(vid))

    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'api_v4',
                'note': '纯 HTTP；>30s 视频 mp4 会被截断（需 m3u8 合并）'}


if __name__ == '__main__':
    import sys
    import time

    async def _main():
        samples = sys.argv[1:] or [
            'https://tv.sohu.com/v/MjAyNjEwMDUvbjYyMDI1NDAwNi5zaHRtbA==.html',
            'https://tv.sohu.com/v/MjAyNjA5MzAvbjYyMDI1MzY2MC5zaHRtbA==.html',
        ]
        p = SohuPureParser()
        for s in samples:
            t0 = time.time()
            r = await p.parse(s)
            print(f'\n--- {s[:64]}')
            print(f'耗时 {time.time() - t0:.2f}s')
            for k in ('success', 'vid', 'title', 'author', 'quality',
                      'truncated', 'duration_claimed_s', 'duration_actual_s',
                      'size', 'user_warning'):
                if k in r:
                    print(f'  {k:22s}: {str(r[k])[:64]}')
            print('  video_url              :',
                  (r.get('video_url') or r.get('error') or '')[:88])
            if r.get('m3u8_url'):
                print('  m3u8_url:',
                      r['m3u8_url'][:88])

    asyncio.run(_main())
