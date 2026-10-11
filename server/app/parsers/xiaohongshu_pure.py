"""小红书纯 HTTP 解析器 —— ⭐ 2026-10-05 从「不接入」改为「可接入」

🔴🔴 本平台的结构**全部改版了**，3 个开源项目的实现**全部失效**。
   本文件的数据链是实测重新定位的，与开源项目**完全不同**。

════════════════════════════════════════════════════════════════════
一、开源项目怎么做的（已全部失效）
════════════════════════════════════════════════════════════════════
3 个项目（parse-video-py / parse-video Go / video-parser）都用：
    页面 → window.__INITIAL_STATE__ → note.noteDetailMap[{id}].note

实测（带真 xsec_token 的真实笔记）：
| 字段 | 开源项目读的 | 实测现在 |
|---|---|---|
| 顶层 key | `note` | **❌ 不存在** |
| 笔记容器 | `note.noteDetailMap` | **❌ 0 条** |
| noteId | `note.currentNoteId` | **None** |
| 图片字段 | `imageList[].urlDefault` | **❌ 空字符串** |
| 真实位置 | — | **noteData.data.noteData** |
| 真实图片字段 | — | **imageList[].url**（+ fileId） |

⭐「开源项目的去水印换域名规则」也已失效：
    ci.xiaohongshu.com/notes_pre_post/{id}   → **实测 404**
但用 fileId 拼 sns-na-i6 / sns-img-qc 可拿到**无水印原图**（见下）

════════════════════════════════════════════════════════════════════
二、实测能跑通的数据链
════════════════════════════════════════════════════════════════════
【入口】必须是 /discovery/item/{noteId}?xsec_token=...
   ⚠️ PC UA → 302 到 /login 登录墙
   ⚠️ iOS UA → **HTTP 200 直接通过**（实测 170KB vs PC 的 73KB）
   → 采集端必须伪装移动端

【解析】yaml.safe_load(window.__INITIAL_STATE__)
   ⚠️ json.loads 会失败（state 含 undefined / 裸值）——
      这正是 parse-video-py 用 yaml 的原因，实测确认

【取笔记】
   state.noteData.data.noteData
     .title / .desc / .type(normal|video) / .user
     .imageList[]  → .url（带水印）/ .fileId / .width / .height
     .video        → 视频笔记用（本次样本为空）

【去水印】⚠️ 核心技巧
   原始 url（sns-webpic-qc...）**带「小红书」文字水印**（已下载确认）
   → 用 fileId 拼 {sns-na-i6 | sns-img-qc}.xhscdn.com 才是**无水印原图**
     https://sns-na-i6.xhscdn.com/{fileId}?imageView2/2/w/1080/format/jpg
   实测两者都是 1080×1683，画面对比确认水印确实消失

   ⚠️ P1 再次应验：**「urlDefault 是无水印图」是我从开源代码读来的假设，
     实测它有水印**。字段名骗人，必须下载看图。
"""
from __future__ import annotations

import asyncio
import gzip
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# ⚠️ 必须用移动端 UA —— PC UA 会被 302 到 /login（实测）
IOS_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 '
          'Mobile/15E148 Safari/604.1')

HOME = 'https://www.xiaohongshu.com/'

# /discovery/item/{24位hex}?xsec_token=...
ITEM_RE = re.compile(
    r'(?:xiaohongshu\.com|xhslink\.[a-z]+)/(?:discovery/item|explore)/([0-9a-f]{16,32})')
XSEC_RE = re.compile(r'xsec_token=([A-Za-z0-9_\-=]+)')
NOTE_ID_RE = re.compile(r'\b([0-9a-f]{24})\b')
URL_RE = re.compile(r'https?://[^\s，。、"\')）)】\]]+')

# ⭐ 分享文案里的标题（2026-10-05 用户指出后补上）
#
# 小红书 App/浏览器 分享出来的文本是固定格式：
#   {序号} 【{标题} - {作者} | 小红书 - 你的生活兴趣社区】 😆 {短码} 😆 {url}
#
# 为什么需要它：
#   SSR 的 `note.title` **只有图集笔记才有**（type=normal），
#   视频笔记（type=video）的 title 恒为空字符串。
#   但分享文案里**两种笔记都有标题** → 这是视频笔记唯一的标题来源。
#
# 注意标题里可能含「 - 」（如「美颜前 - 美颜后」），
# 所以分隔符要用「 + | 小红书」来定位右侧边界，不能简单 split(' - ')。
SHARE_TITLE_RE = re.compile(
    r'【\s*(.+?)\s+-\s+([^|]{1,40}?)\s*\|\s*小红书')
# 兜底：只取方括号里的前半段（作者名可能含「-」）
SHARE_TITLE_LOOSE_RE = re.compile(r'【\s*([^【】|]{2,120}?)\s*\|\s*小红书')

# 无水印原图域名候选（实测 sns-na-i6 与 sns-img-qc 都可用）
NOWATERMARK_HOSTS = (
    'sns-na-i6.xhscdn.com',
    'sns-img-qc.xhscdn.com',
    'sns-img-bd.xhscdn.com',
)

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

STATE_RE = re.compile(
    r'window\.__INITIAL_STATE__\s*=\s*(.*?)</script>', re.S)


def _get(url: str, timeout: int = 30) -> str:
    headers = {
        'User-Agent': IOS_UA,
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Language': 'zh-CN,zh;q=9',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': HOME,
    }
    # 登录态（CB_XHS_COOKIE / server/xhs-cookie.txt）：App 分享的新 token
    # 对无 cookie 访问会被登录墙拦截（实测 2026-10-07）
    try:
        from app import config
    except ImportError:
        import config
    if getattr(config, 'XHS_COOKIE', ''):
        headers['Cookie'] = config.XHS_COOKIE
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':        # P7
        raw = gzip.decompress(raw)
    return raw.decode('utf-8', 'ignore')


def _normalize_url(url: str) -> str:
    """路由归一化：/explore/{id} 与 /discovery/item/{id} 等价

    ⚠️ 实测 2026-10-05：`/explore/{id}` 会**间歇性**返回
    state 里带 `notFoundPage` 顶层key、noteData 为空的情况，
    而同一 id 走 `/discovery/item/{id}` 稳定可读。
    → 统一走 /discovery/item/，避开这个坑。
    """
    m = re.search(r'xiaohongshu\.com/(?:explore|discovery/item)/'
                  r'([0-9a-f]{16,32})', url)
    if not m:
        return url
    q = urllib.parse.urlparse(url).query
    return (f'https://www.xiaohongshu.com/discovery/item/{m.group(1)}'
            + (f'?{q}' if q else ''))


def _resolve_xhslink(url: str, timeout: int = 15) -> str:
    """xhslink.com 短链 → 完整 xiaohongshu.com 链接（含 xsec_token）

    小红书 App「复制链接」给的是 xhslink.com/a/{随机码} 形态的短链，
    里面没有笔记 ID，必须先跟 302 拿到完整链接才能解析。
    （与 bilibili_pure.resolve_b23 同款手法）
    失败时原样返回 —— 上层会给出可读的失败信息。
    """
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise urllib.error.HTTPError(
                req.full_url, code, msg, headers, fp)

    # ⚠️ context 要在 build_opener 时交给 HTTPSHandler，
    #   opener.open() 不接受 context 参数（传了会 TypeError）
    opener = urllib.request.build_opener(
        NoRedirect, urllib.request.HTTPSHandler(context=_SSL))
    cur = url
    try:
        for _ in range(4):                      # 最多跟 4 跳
            req = urllib.request.Request(cur, headers={'User-Agent': IOS_UA})
            try:
                r = opener.open(req, timeout=timeout)
                final = r.geturl()
                r.close()
                return final
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    loc = (e.headers or {}).get('Location', '')
                    if not loc:
                        return url
                    cur = urllib.parse.urljoin(cur, loc)
                    if 'xiaohongshu.com' in cur:
                        return cur
                    continue
                return url
    except Exception:
        return url
    return cur if 'xiaohongshu.com' in cur else url


def _parse_state(html: str) -> Optional[Dict[str, Any]]:
    """解析 __INITIAL_STATE__

    ⚠️ 必须用 yaml.safe_load：实测 json.loads 在这里必失败
    （state 里含 undefined 和裸值，不是合法 JSON）。
    这也是 parse-video-py 当年选 yaml 的原因。
    """
    m = STATE_RE.search(html)
    if not m:
        return None
    body = m.group(1)
    try:
        import yaml
        return yaml.safe_load(body)
    except ImportError:
        # 没装 pyyaml 时退回 json（可能失败，但给出可读错误）
        try:
            return json.loads(body)
        except Exception:
            return None
    except Exception:
        return None


def _find_note(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """⭐ 按优先级找笔记数据（兼容改版前后多种结构）

    2026-10-05 实测路径（当前）：
        state.noteData.data.noteData
    开源项目用的旧路径（已失效，但保留兼容）：
        state.note.noteDetailMap[{id}].note
    """
    #① 当前结构
    nd = state.get('noteData')
    if isinstance(nd, dict):
        d = nd.get('data')
        if isinstance(d, dict):
            n = d.get('noteData')
            if isinstance(n, dict) and n:
                return n
        #② preload 结构（内容更少，作为兜底）
        pre = nd.get('normalNotePreloadData')
        if isinstance(pre, dict) and pre.get('imagesList'):
            return pre
    # ③ 旧结构（开源项目用的）
    note = state.get('note')
    if isinstance(note, dict):
        ndm = note.get('noteDetailMap')
        if isinstance(ndm, dict) and ndm:
            for v in ndm.values():
                if isinstance(v, dict) and v.get('note'):
                    return v['note']
    return None


def _https(url: str) -> str:
    """补全协议 + 还原被转义的斜杠

    ⚠️ SSR 里的 masterUrl 常见两种问题：
       1. 协议是 `http://`（页面是 https，混合内容浏览器会拦）
       2. 路径里的 `/` 被 JSON 转义成 `\\u002F`（同 P20 的 originVideoKey）
    """
    if not url:
        return ''
    s = str(url).replace('\\u002F', '/').replace('\\/', '/')
    if s.startswith('//'):
        return 'https:' + s
    if s.startswith('http://'):
        return 'https://' + s[7:]
    return s


def nowatermark_url(file_id: str, width: int = 1080,
                   host: str = NOWATERMARK_HOSTS[0]) -> str:
    """用 fileId 拼无水印原图地址

    实测：sns-webpic-qc 的 url 带「小红书」水印；
         换 {sns-na-i6|sns-img-qc} + fileId  → 无水印
    """
    return (f'https://{host}/{file_id}'
            f'?imageView2/2/w/{width}/format/jpg')


def _extract_share_title(text: str) -> str:
    """从分享文案里提取标题

    小红书分享格式（实测两种笔记一致）：
        {序号} 【{标题} - {作者} | 小红书 - 你的生活兴趣社区】 😆 {码} 😆 {url}

    ⚠️ 标题本身可能含「 - 」（如「美颜前 - 美颜后」），
    所以**不能简单 split(' - ')**，要用右侧的「| 小红书」定位边界。
    失败时用宽松正则兜底（只要「| 小红书」前的内容）。
    """
    if not text or '小红书' not in text:
        return ''
    m = SHARE_TITLE_RE.search(text)
    if m:
        title = m.group(1).strip().strip('-').strip()
        if title:
            return title
    m = SHARE_TITLE_LOOSE_RE.search(text)
    if m:
        return m.group(1).strip().strip('-').strip()
    return ''


def _pick_image(im: Dict[str, Any]) -> Dict[str, Any]:
    """选图：优先无水印原图，回退原始 url

    ⚠️ 原始 url 实测**有水印**，别直接用。
    """
    fid = im.get('fileId') or ''
    out = {
        'width': im.get('width'),
        'height': im.get('height'),
        'no_watermark': bool(fid),
    }
    if fid:
        out['url'] = nowatermark_url(fid)
        out['source'] = 'fileId 拼接（无水印）'
    else:
        out['url'] = im.get('url') or ''
        out['source'] = '原始 url（可能带水印）'
        out['no_watermark'] = False
    # 带水印的原图也留一份，便于对照
    if im.get('url'):
        out['url_with_watermark'] = im['url']
    return out


async def _parse_sync(text: str) -> Dict[str, Any]:
    m = URL_RE.search(text or '')
    if not m:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': '未识别到链接'}
    url = m.group(0)
    if 'xiaohongshu.com' not in url and 'xhslink' not in url:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': '不是小红书链接'}

    # ⭐ xhslink.com 短链（App「复制链接」最常给的形态）：
    #   xhslink.com/a/{随机码} 里没有笔记 ID，先跟 302 换完整链接
    if 'xhslink' in url and not ITEM_RE.search(url):
        resolved = _resolve_xhslink(url)
        if ITEM_RE.search(resolved):
            url = resolved
        else:
            return {'success': False, 'platform': 'xiaohongshu',
                    'error': '短链解析失败，未能取得完整笔记链接',
                    'hint': '请回到小红书 App 重新「分享 → 复制链接」',
                    'short_url': url[:60]}

    mi = ITEM_RE.search(url)
    if not mi:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': f'未能提取笔记 ID: {url[:60]}',
                'hint': '链接应含 /discovery/item/{id} 或 /explore/{id}'}
    note_id = mi.group(1)

    # xsec_token 是必需的（实测缺失会被拦）
    mt = XSEC_RE.search(url)
    if not mt:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': '链接缺少 xsec_token',
                'hint': ('小红书分享链接必须带 ?xsec_token=...，'
                         '请让用户用 App「分享 → 复制链接」得到的完整链接'),
                'note_id': note_id}

    fetch_url = _normalize_url(url)
    try:
        html = _get(fetch_url)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302) or 'location' in (e.headers or {}):
            loc = (e.headers or {}).get('Location', '')
            if '/login' in loc:
                return {'success': False, 'platform': 'xiaohongshu',
                        'error': '被重定向到登录页（xsec_token 可能已失效）',
                        'hint': '让用户重新分享一次拿新 token'}
            return {'success': False, 'platform': 'xiaohongshu',
                    'error': f'HTTP {e.code}'}
        return {'success': False, 'platform': 'xiaohongshu',
                'error': f'请求失败: HTTP {e.code}'}
    except Exception as e:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': f'请求失败: {str(e)[:70]}'}

    state = _parse_state(html)
    note = _find_note(state) if state else None

    # ⭐ 登录墙精准识别（2026-10-07 实测）：App 分享的新 xsec_token
    #   对无 cookie 访问返回 fe-login 客户端渲染壳 —— 页面里根本没有
    #   __INITIAL_STATE__，重试无用。必须配 Cookie 才能过。
    if not state and 'fe-login' in html:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': '该笔记需要登录才能访问（小红书对部分分享链接的限制）',
                'hint': ('服务端配置小红书 Cookie 后即可解析：电脑浏览器登录'
                         '小红书 → F12 → Network → 复制 Cookie 值 → 存入'
                         ' server/xhs-cookie.txt 后重启服务'),
                'login_wall': True}

    # ⚠️ 重试：实测小红书对同一 token 会**间歇性**返回空 noteData
    #   （state 里有 noteData 但 data.noteData 为空，
    #     有时还多一个 notFoundPage 顶层 key）。
    #   重试一次通常就好 —— 与抖音短链抖动同类问题（见 P26）。
    attempts = 1
    if not note:
        for i in range(2):
            attempts += 1
            await asyncio.sleep(0.6 * (i + 1))
            try:
                html = _get(fetch_url)
                state = _parse_state(html)
                note = _find_note(state) if state else None
            except Exception:
                pass
            if note:
                break

    if not state:
        return {'success': False, 'platform': 'xiaohongshu',
                'error': '页面里没有 __INITIAL_STATE__（可能需要登录）',
                'attempts': attempts}

    if not note:
        # 明确区分几种失败（开源项目源码注释也提到过 undefined）
        nd = state.get('noteData') or {}
        has_err = nd.get('hasError') if isinstance(nd, dict) else None
        if 'notFoundPage' in state:
            # ⚠️ notFoundPage 不一定是「笔记被删」—— App 分享的 xsec_token
            #   时效很短且与会话绑定，过期/被拒同样返回这个 state。
            #   文案必须两个原因都覆盖，并给出用户能执行的动作。
            err = ('笔记无法访问（分享令牌已过期，或笔记已被作者删除）'
                    '—— 请回到小红书重新「分享 → 复制链接」再试')
        elif has_err is False:
            err = ('笔记数据为空（xsec_token 过期或被限制访问）'
                    f'—— 已重试 {attempts} 次')
        else:
            err = '在 __INITIAL_STATE__ 里没找到笔记数据'
        return {'success': False, 'platform': 'xiaohongshu',
                'error': err,
                'hint': '实测：带真 token 也会遇到 300031「当前笔记暂时无法浏览」',
                'note_id': note_id,
                'attempts': attempts,
                'state_keys': sorted(state.keys())}

    imgs_raw = note.get('imageList') or note.get('imagesList') or []
    images = [_pick_image(im) for im in imgs_raw if isinstance(im, dict)]
    images = [im for im in images if im.get('url')]

    user = note.get('user') or {}

    # ---- 互动数据（interactInfo，图集与视频都有）----
    inter = note.get('interactInfo') or {}

    def _count(v: Any) -> int:
        """⭐ P30：小红书的互动数有两种格式，必须分别处理
        - 数字：2730 / 1731
        - 带千分位字符串："22.8K" / "1,810"
        直接 int() 会抛异常或得到错误值。"""
        if v in (None, ''):
            return 0
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip().replace(',', '')
        if not s:
            return 0
        m = re.match(r'^([\d.]+)\s*([KkWw万亿]?)$', s)
        if not m:
            return 0
        try:
            num = float(m.group(1))
        except ValueError:
            return 0
        mult = {'K': 1_000, 'k': 1_000, 'W': 10_000, 'w': 10_000,
                '万': 10_000, '亿': 100_000_000}.get(m.group(2), 1)
        return int(num * mult)

    # ---------- 类型判定 ----------
    # ⚠️ P27：视频笔记 ALSO 带 imageList（那是封面图），
    #   所以「images 非空」不能作为图集判据 —— 必须看 note.type。
    #   我曾因此把一条 262 秒视频误报成「1 张图的图集」。
    note_type = (note.get('type') or '').strip().lower()
    is_video = note_type == 'video'

    # ---------- 视频地址 ----------
    video_url = ''
    video_options: List[Dict[str, Any]] = []
    video_meta: Dict[str, Any] = {}
    vid = note.get('video') or {}

    if is_video and vid:
        stream = (vid.get('media') or {}).get('stream') or {}
        mv = (vid.get('media') or {}).get('video') or {}

        # 档位：h264 优先（iOS/旧安卓都能播），再 h265/av1
        for enc in ('h264', 'h265', 'av1', 'h266'):
            for idx, item in enumerate(stream.get(enc) or []):
                if not isinstance(item, dict):
                    continue
                u = _https(item.get('masterUrl') or '')
                if not u:
                    continue
                backups = [_https(b) for b in (item.get('backupUrls') or [])
                           if b]
                video_options.append({
                    'index': len(video_options),
                    'gear': f"{enc.upper()} {item.get('videoBitrate', '') and str(item.get('videoBitrate')) + 'kbps'}".strip(),
                    'codec': enc,
                    'bitrate': item.get('videoBitrate'),
                    'audio_bitrate': item.get('audioBitrate'),
                    'duration_ms': item.get('duration'),
                    'signed': True,          # masterUrl 带 sign= 有时效
                    'url': u,
                    'backup_urls': backups,
                })

        # ⭐ 优先用 consumer.originVideoKey 拼无签名地址
        #   masterUrl 带 ?sign= 有时效，缓存会失效；
        #   originVideoKey 拼出的地址无签名，可长期缓存。实测两者皆 200。
        key = (vid.get('consumer') or {}).get('originVideoKey') or ''
        stable_url = ''
        if key:
            stable_url = _https(
                'https://sns-video-bd.xhscdn.com/'
                + str(key).replace('\\u002F', '/'))

        if stable_url:
            video_url = stable_url
            video_options.insert(0, {
                'index': 0,
                'gear': '原画（无签名/稳定）',
                'codec': 'h264',
                'bitrate': (video_options[0].get('bitrate')
                            if video_options else None),
                'duration_ms': (video_options[0].get('duration_ms')
                                if video_options else None),
                'signed': False,
                'url': stable_url,
                'note': '由 consumer.originVideoKey 拼出，不带 sign 参数',
            })
            for i, o in enumerate(video_options):
                o['index'] = i
        elif video_options:
            video_url = video_options[0]['url']

        # ⚠️ P28：同名字段单位不一致（实测这条视频）
        #   media.video.duration = 262       → 【秒】（ffprobe 261.39s ✓）
        #   stream.h264[0].duration = 261389 → 【毫秒】
        # 优先用 stream 的毫秒值（两个编码档一致，更可信）
        dur_ms = None
        for o in video_options:
            if o.get('duration_ms'):
                dur_ms = o['duration_ms']
                break
        if dur_ms is None and mv.get('duration'):
            dur_ms = int(mv['duration']) * 1000

        video_meta = {
            'duration_ms': dur_ms,
            'duration_s': round(dur_ms / 1000, 2) if dur_ms else None,
            'duration_field_note': (
                'media.video.duration 是【秒】，'
                'stream.*.duration 是【毫秒】，勿混用'),
            'hdr': mv.get('hdrType'),
            'drm': mv.get('drmType'),
            'stream_types': mv.get('streamTypes'),
            'cover_thumbnail': _https(
                'https://sns-video-bd.xhscdn.com/'
                + str((vid.get('image') or {}).get('thumbnailFileid') or ''))
            if isinstance(vid.get('image'), dict) else '',
        }

    if is_video:
        kind = 'video' if video_url else 'video_unresolved'
    else:
        kind = 'image' if images else 'unknown'

    # ---- 标题：三级来源 ----
    # ① SSR note.title          → 只有图集笔记（type=normal）有
    # ② 分享文案【标题 - 作者】  → ⭐ 视频笔记唯一的标题来源
    # ③ desc 首句兜底            → 两者都空时（如用户只贴了裸链接）
    #
    # ⚠️ P34：我上一轮断言「视频笔记无独立 title，接口不下发」——
    #    **不准确**。用户分享文案里一直带着标题，是我没去看分享格式。
    #    「我读过的字段里没有 X」≠「平台不给 X」（同 P24）。
    title = (note.get('title') or '').strip()
    title_source = 'ssr' if title else ''
    if not title:
        share = _extract_share_title(text)   # text = 原始输入（可能是分享文案）
        if share:
            title, title_source = share, 'share_text'
    desc = note.get('desc') or ''
    if not title and desc:
        # 兜底：取 desc 第一个句子（按中文句号/问号/感叹号断）
        m = re.split(r'[。！？!?\n]', desc.strip(), 1)
        head = (m[0] if m else '').strip()
        # 去掉话题标记后再取
        head = re.sub(r'#[^#\s]{0,24}\[话题\]#?', '', head).strip()
        if len(head) >= 4:
            title, title_source = head[:60], 'desc_head'

    result: Dict[str, Any] = {
        'success': True,
        'platform': 'xiaohongshu',
        'method': 'ssr_initial_state',
        'note_id': note_id,
        'note_type': note_type or kind,
        'title': title,
        'title_source': title_source,      # ssr / share_text / desc_head
        'title_is_desc': title_source == 'desc_head',
        'description': desc,
        'author': user.get('nickName') or user.get('nickname') or '',
        'author_id': str(user.get('userId') or ''),
        'author_avatar': user.get('avatar') or '',
        'publish_time_ms': note.get('time'),         # Unix 毫秒
        'last_update_ms': note.get('lastUpdateTime'),
        # ---- 互动数据（2026-10-05 补齐）----
        'like_count': _count(inter.get('likedCount')),
        'collect_count': _count(inter.get('collectedCount')),
        'comment_count': _count(inter.get('commentCount')),
        'share_count': _count(inter.get('shareCount')),
        'nice_count': _count(inter.get('niceCount')),
        'cover': (images[0]['url'] if images
                  else video_meta.get('cover_thumbnail', '')),
        'type': kind,
        'images': [] if is_video else images,
        'image_count': 0 if is_video else len(images),
        'video_url': video_url,
        'need_proxy': True,          # xhscdn.com 域名多且带鉴权参数
        'anonymous': True,           # 游客态可读（实测）
        'no_watermark': (True if is_video and video_url
                         else bool(images) and all(
                             i.get('no_watermark') for i in images)),
        'watermark_free': (True if is_video and video_url
                           else bool(images) and all(
                               i.get('no_watermark') for i in images)),
        'state_layout': (
            'noteData.data.noteData' if 'noteData' in state else 'note.*（旧）'),
        'expiry_note': 'xsec_token 有有效期，过期后笔记不可读',
    }
    if video_meta:
        result['video_meta'] = video_meta

    if is_video:
        result['options'] = video_options
        result['options_count'] = len(video_options)
        if not video_url:
            result['success'] = False
            result['error'] = ('笔记是视频，但没取到播放地址'
                               '（stream 与 consumer 均为空）')
    else:
        result['options'] = [
            {'index': i, 'gear': f"{im.get('width')}x{im.get('height')}",
             'width': im.get('width'), 'height': im.get('height'),
             'url': im['url'], 'no_watermark': im.get('no_watermark')}
            for i, im in enumerate(images)]
        result['options_count'] = len(images)
    return result


class XiaohongshuPureParser:
    """纯 HTTP 小红书解析 —— iOS UA + yaml 解析 + fileId 去水印"""

    name = 'xiaohongshu_pure'
    domains = ('xiaohongshu.com', 'xhslink.com', 'xhslink.cn')

    @staticmethod
    def extract_url(text: str) -> str:
        m = URL_RE.search(text or '')
        return m.group(0) if m else ''

    def match(self, url: str) -> bool:
        return any(d in url for d in self.domains)

    async def parse(self, text: str,
                    quality: str = '1080p') -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await _parse_sync(text)
    async def health(self) -> Dict[str, Any]:
        return {'ready': True, 'method': 'ssr_initial_state',
                'note': ('必须 iOS UA + 完整 xsec_token；'
                         '图片用 fileId 拼无水印原图')}


if __name__ == '__main__':
    import sys
    import time

    # ⭐ 演示分享文案形态 —— 视频笔记的标题只能从这里来
    SAMPLE = ('16 【一部上映十天却惨遭下架的电影，却赚足了观众的眼泪 '
              '虐心虐恋 古装玄幻 虐心片段 - 怪咖解说 | 小红书 - 你的生活兴趣社区】'
              ' \U0001f606 kkceQvt29agF6eV \U0001f606 '
              'https://www.xiaohongshu.com/discovery/item/6a72adee0000000033036edf'
              '?xsec_token=ABgKYGq72MJJJWO8OVQh3MtnwjRfcqKYxsujnzRIHNdTA='
              '&xsec_source=pc_share')

    async def _main():
        p = XiaohongshuPureParser()
        for s in (sys.argv[1:] or [SAMPLE]):
            t0 = time.time()
            r = await p.parse(s)
            print(f'\n--- {s[:64]}  {time.time() - t0:.2f}s')
            print(f"  success : {r.get('success')}")
            for k in ('type', 'note_id', 'title', 'title_source', 'author', 'image_count',
                      'no_watermark', 'state_layout', 'need_proxy'):
                if k in r:
                    print(f'  {k:13s}: {str(r[k])[:52]}')
            if r.get('description'):
                print(f"  {'description':13s}: {r['description'][:52]}")
            for im in (r.get('images') or [])[:3]:
                print(f"    {im.get('width')}x{im.get('height')} "
                      f"无水印={im.get('no_watermark')} {im.get('url', '')[:60]}")
            if not r.get('success'):
                print(f"  error     : {r.get('error')}")
                if r.get('hint'):
                    print(f"  hint      : {r['hint'][:64]}")

    asyncio.run(_main())
