"""抖音响应归一化 —— 无浏览器依赖的纯函数模块

⭐ 为什么要单独抽出来（2026-10-05）
──────────────────────────────────
`normalize()` 原来定义在 `douyin.py` 里，而 `douyin.py` 顶层
`from playwright.async_api import async_playwright`。
结果：**playwright 没装时，连单元测试都跑不起来**（导入即炸）。

把纯逻辑抽到这里，`douyin.py` / `douyin_pure.py` / 测试都从这里import，
纯逻辑与浏览器依赖彻底解耦。

⭐⭐ 本模块承载的是「去水印」的核心判据，改动前务必读P1
   无水印地址取自 `bit_rate[].play_addr.url_list`，
   **不是** `download_addr`（有水印），也不是把URL 里的 playwm 换成 play
   （URL 路径根本判断不了水印）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 清晰度偏好：quality 参数 → gear_name 关键字
GEAR_PREF = {
    'origin': 'origin',
    '1080p': '1080',
    '720p': '720',
    '540p': '540',
}


def pick_image_url(im: dict) -> Optional[str]:
    """⭐ 图集选无水印原图

    ⚠️⚠️ 必须用 `url_list`（模板标记 ~tplv-dy-aweme-images，原始无水印图），
       **不能用 `download_url_list`**（模板 ~tplv-dy-water-v2，
       底部带「抖音号」水印，且与原图同尺寸 1600x2560，不是缩略图）。

    小程序 `saveImageToPhotosAlbum` 不支持 webp，
    所以优先挑 .jpeg/.jpg 候选。
    """
    cands = list(im.get('url_list') or [])
    if not cands:
        return None
    jpeg = next((u for u in cands if '.jpeg' in u or '.jpg' in u), None)
    no_webp = next((u for u in cands if '.webp' not in u), None)
    return jpeg or no_webp or cands[0]


def collect_images(ad: dict) -> List[Dict[str, Any]]:
    """提取图集全部图片（只走无水印的 url_list）"""
    out: List[Dict[str, Any]] = []
    for im in ad.get('images') or []:
        pick = pick_image_url(im)
        if not pick:
            continue
        res = im.get('resolution_log_param') or {}
        out.append({
            'url': pick,
            'width': im.get('width') or res.get('image_publish_width'),
            'height': im.get('height') or res.get('image_publish_height'),
            'format': 'jpeg' if ('.jpeg' in pick or '.jpg' in pick) else 'webp',
        })
    return out


def collect_options(v: dict) -> List[Dict[str, Any]]:
    """提取视频全部清晰度档位（按码率降序）"""
    options: List[Dict[str, Any]] = []
    for b in (v.get('bit_rate') or []):
        pa = ((b.get('play_addr') or {}).get('url_list')) or []
        if not pa or not pa[0]:
            continue
        options.append({
            'gear': b.get('gear_name'),
            'bit_rate': b.get('bit_rate'),
            'size': b.get('size'),
            'url': pa[0],
        })
    options.sort(key=lambda x: x.get('bit_rate') or 0, reverse=True)
    return options


def normalize(d: dict, quality: str = '1080p') -> dict:
    """统一抖音响应结构（视频 + 图集）

    入参是含 `aweme_detail` 的原始响应（如 a_bogus detail 接口返回）。
    """
    ad = d.get('aweme_detail') or {}
    if not ad:
        return {'success': False, 'error': '无数据'}

    v = ad.get('video') or {}
    images = collect_images(ad)
    is_image = bool(ad.get('images')) or bool(images)

    options = collect_options(v)

    chosen = None
    if not is_image:
        want = GEAR_PREF.get(quality, '1080')
        chosen = next((o for o in options if want in (o.get('gear') or '')),
                      options[0] if options else None)

    author = ad.get('author') or {}
    return {
        'success': True,
        'platform': 'douyin',
        'type': 'image' if is_image else 'video',
        'aweme_id': ad.get('aweme_id'),
        'title': ad.get('desc', ''),
        # ---- 元信息（2026-10-05 补齐）----
        # ⚠️ 抖音的「文案」和「标题」是同一个字段 desc，
        #   视频没有独立标题（图集也没有）→ description 留空，
        #   不把 desc 重复一遍当标题（前端会显示两遍一样的内容）。
        'description': ad.get('preview_title') or '',
        'author': author.get('nickname', ''),
        'author_id': author.get('unique_id') or author.get('short_id') or '',
        'author_avatar': ((((author.get('avatar_thumb') or {})
                            .get('url_list')) or [''])[0]),
        'cover': (((v.get('cover') or {}).get('url_list')) or [''])[0],
        'duration_ms': v.get('duration'),
        'create_time': ad.get('create_time'),
        'publish_time_ts': ad.get('create_time'),   # Unix 秒
        # ---- 互动数据（statistics）----
        'like_count': (ad.get('statistics') or {}).get('digg_count'),
        'comment_count': (ad.get('statistics') or {}).get('comment_count'),
        'collect_count': (ad.get('statistics') or {}).get('collect_count'),
        'share_count': (ad.get('statistics') or {}).get('share_count'),
        'view_count': (ad.get('statistics') or {}).get('play_count'),
        'video_url': chosen['url'] if chosen else None,
        'quality': chosen['gear'] if chosen else None,
        'size': chosen.get('size') if chosen else None,
        'options': options,
        'images': images,
        'image_count': len(images),
        # 无水印判据：图集必须全部来自 ~tplv-dy-aweme-images 模板
        'watermark_free': (all('dy-aweme-images' in (i['url'] or '')
                               for i in images)
                           if images else None),
    }
