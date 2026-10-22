"""统一元信息规范层（M2 前置）

ⓐ 为什么要有这个模块
─────────────────────
审计发现 7 个平台解析器返回的字段**命名完全不统一**：

    播放量   play_count / play_count_text / view_count / fmplaycnt
    点赞likelike_count / attitudes_count / fmlike_num / likedCount
    时长     duration_ms / duration_time / durationMillis / time_length
    文案     description / caption / desc / text

前端要为此写7 套判断，且加平台就得改前端 —— 这不可持续。

ⓑ 设计原则
─────────────────────
1. **规范化与解析分离**：解析器只负责「如实返回接口给的」，
   规范化层负责「映射到统一字段名」，两者职责不混。
   → 这样平台改字段时只改映射表，不改前端。
2. **数字与展示文本分离**：
   `like_count`(int 22800) 与 `like_count_text`("2.3万") 分开两个字段。
   排序/统计用数字，展示用文本。
3. **缺失就是缺失**：接口没给就留None，**绝不用其他字段推算或编造**。
   每个字段都记 `meta_sources` 说明来源路径，便于核对。
4. **单位显式**：所有时长统一成秒（`_s` 后缀），所有数量统一成个。

ⓒ 字段清单（前端唯一需要关心的）
─────────────────────
    title            标题
    description      文案/简介
    cover            封面（视频笔记的封面已是无水印原图）
    author_name      作者昵称
    author_id        作者 ID
    author_avatar    作者头像
    duration_s时长（秒，float）
    publish_ts       发布时间（Unix 秒，int）
    publish_time_text发布时间（平台原始文本，如"20天前"）
    stats            统计数字 {like,comment,collect,share,view,danmaku}
    stats_text       统计文本 {like:"2.3万",view:"450万"}
    tags             话题标签（小红书/微博有）
    extra            平台特有字段（如搜狐关键词、B站分区）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ══════════════════════════════════════════════════════════
# 一、工具函数
# ══════════════════════════════════════════════════════════

_CN_UNITS = {'万': 10_000, '亿': 100_000_000, 'w': 10_000, 'W': 10_000}


def cn_number_to_int(text: Any) -> Optional[int]:
    """「2.3万」→ 230000；「115.9万」→ 1159000

    ⚠️ P30：平台的「人数字段」有两个，必须分清：
       - `followers_count` = "115.9万"  → 字符串，要换算
       - `fanCountValue`   = 1159000   → 已经是数字，别再乘
    混淆会导致粉丝数差1e4 倍。
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).strip().replace(',', '')
    if not s:
        return None
    m = re.match(r'^([\d.]+)\s*([万亿wW]?)', s)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2)
    return int(num * _CN_UNITS.get(unit, 1))


def ms_to_s(ms: Any) -> Optional[float]:
    """毫秒 → 秒。⚠️ P28：同名 duration 字段单位可能不一致，
    调用方必须先确认单位（见 META_RULES 里的duration_ms_sources）。"""
    try:
        v = float(ms)
    except (TypeError, ValueError):
        return None
    return round(v / 1000.0, 2) if v > 0 else None


def hms_to_s(text: Any) -> Optional[float]:
    """「5:19」/ 「00:26」/「01:16」→ 秒"""
    if not text:
        return None
    s = str(text).strip()
    if re.match(r'^\d+$', s):
        return float(s)
    parts = s.split(':')
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return round(total, 2)


def ts_to_s(value: Any) -> Optional[str]:
    """Unix 秒/毫秒 → 'YYYY-MM-DD HH:MM'"""
    if value in (None, '', 0, '0'):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    # 毫秒判定：> 1e11 视为毫秒（1973 年之后的秒时间戳都< 1e11）
    if v > 1e11:
        v = v / 1000.0
    import time
    try:
        return time.strftime('%Y-%m-%d %H:%M', time.localtime(v))
    except (ValueError, OSError, OverflowError):
        return None


def _clean_tag(tag: str) -> str:
    """清理话题标签

    ⚠️ 小红书的标签在文案里是 `#杨幂[话题]#` ——
    提取出来会带 `[话题]` 后缀，直接显示给用户很怪。
    其他平台是干净的 `#杨幂#`。

    ⚠️ 2026-10-22 修：原来第一行是 `str(tag).strip()`，
       传 None 会得到字符串 'None'（不是空串）——
       那个值会被当成一个叫「None」的话题塞进 tags。
       现在先判空值。调用方虽然大多判过，但这类隐患应该在这里堵死。
    """
    if tag is None:
        return ''
    if not isinstance(tag, str):
        tag = str(tag)
    s = tag.strip().lstrip('#').rstrip('#')
    s = s.replace('[话题]', '').replace('［话题］', '')
    s = s.strip().strip('#').strip()
    return s or ''


# 从文本里提取 #话题# 的两条规则（2026-10-22 实测各平台格式）
#   A. 两侧都有 #   → 微博 `#今日穿搭#`、小红书 `#美食[话题]#`
#   B. 只有前侧 #   → 抖音 `#分享你的快餐推荐 #猪脚饭`
# ⭐ 两条都要跑：只用 A 会漏掉抖音（恒为空），只用 B 会漏掉微博。
_HASH_TAG_RULES = (
    r'#([^#\s@]{1,24})#',          # A 双侧
    r'#([^\s#@]{1,24})(?=\s|$)',    # B 前侧（后面必须空白或结尾）
)


def extract_hash_tags(text: Any) -> List[str]:
    """从文本里提取话题标签。

    ⚠️ 必须先剔除 URL 段：`https://x.com/a#b` 里的 `#b` 不是话题，
       实测不剔除会被误提成一个叫「b」的话题。
    """
    if not text:
        return []
    s = str(text)
    # URL 段整体替换成空格（保留其他内容的边界）
    s = re.sub(r'https?://\S+', ' ', s)
    s = re.sub(r'www\.\S+', ' ', s)

    out: List[str] = []
    for pat in _HASH_TAG_RULES:
        for m in re.finditer(pat, s):
            cleaned = _clean_tag(m.group(1))
            if cleaned and cleaned not in out:
                out.append(cleaned)
    return out


def strip_html(text: Any) -> str:
    """去 HTML 标签与多余空白（微博 content2 带 <a> 等）"""
    if not text:
        return ''
    s = re.sub(r'<[^>]+>', '', str(text))
    s = (s.replace('&nbsp;', ' ').replace('&amp;', '&')
          .replace('&lt;', '<').replace('&gt;', '>')
          .replace('&quot;', '"').replace('&#39;', "'"))
    return re.sub(r'\s+', ' ', s).strip()


# ══════════════════════════════════════════════════════════
# 二、平台字段映射表
#
# ⚠️ 这里的路径写的是**解析器返回结果的 key**，不是平台接口的原始字段名。
#    两者不一定相同 —— 解析器可能已经重命名过。
#    例如 B站接口的 pubdate，解析器返回时叫 publish_time。
#    改解析器字段名时必须同步改这里（meta.py 自带覆盖度检查会抓到遗漏）。
# ══════════════════════════════════════════════════════════

# 统计字段的标准名 → 各平台的候选来源（按优先级）
STAT_SOURCES: Dict[str, Dict[str, List[str]]] = {
    'like': {
        'bilibili': ['like_count'],
        'haokan': ['like_count'],
        'weibo': ['like_count'],
        'acfun': ['like_count'],
        'xiaohongshu': ['like_count'],
        'douyin': ['like_count'],
        'kuaishou': ['like_count'],
        'sohu': [],
    },
    'comment': {
        'bilibili': ['comment_count'],
        'haokan': ['comment_count'],
        'weibo': ['comment_count'],
        'acfun': ['comment_count'],
        'xiaohongshu': ['comment_count'],
        'douyin': ['comment_count'],
        'kuaishou': ['comment_count'],
        'sohu': [],
    },
    'collect': {
        'bilibili': ['collect_count'],
        'haokan': [],
        'weibo': [],
        'acfun': [],
        'xiaohongshu': ['collect_count'],
        'douyin': ['collect_count'],
        'sohu': [],
    },
    'share': {
        'bilibili': ['share_count'],
        'haokan': [],
        'weibo': ['share_count'],
        'acfun': [],
        'xiaohongshu': ['share_count'],
        'douyin': ['share_count'],
        'kuaishou': ['share_count'],   # 快手叫 forwardCount
        'sohu': [],
    },
    'view': {
        'bilibili': ['view_count'],
        'haokan': ['view_count'],
        'weibo': [],
        'acfun': ['view_count'],
        'xiaohongshu': [],
        'douyin': ['view_count'],
        'kuaishou': ['view_count'],
        'sohu': ['view_count'],
    },
    'danmaku': {
        'bilibili': ['danmaku_count'],
        'acfun': ['danmaku_count'],
        '_default': [],
    },
    'coin': {                       # B站专属（投币）
        'bilibili': ['coin_count'],
        '_default': [],
    },
    'favorite': {                   # 收藏（与 collect 语义相近，分开以防平台混淆）
        'acfun': [],
        '_default': [],
    },
}

# 发布时间来源（解析器返回的 key）
PUBLISH_SOURCES: Dict[str, List[str]] = {
    'bilibili': ['publish_time_ts', 'publish_time'],
    'haokan': ['publish_time_ts'],
    'weibo': ['publish_time_ts', 'publish_time'],
    'acfun': ['upload_time_ms'],
    'xiaohongshu': ['publish_time_ms'],
    'douyin': ['publish_time_ts', 'create_time'],
    'sohu': ['publish_time_ms'],
    'kuaishou': ['publish_time_ms'],   # photo.timestamp（毫秒）
}

# 平台特有字段（实测可得，通用字段放不下但前端有用）
EXTRA_RULES: Dict[str, Dict[str, str]] = {
    'bilibili': {
        'category': 'tname',# 分区
        'copyright': 'copyright',        # 1=自制 2=转载
        'aid': 'aid',
        'cid': 'cid',
    },
    'haokan': {
        'is_long_video': 'isLongVideo',
    },
    'weibo': {
        'verified': 'verified',
        'verified_reason': 'verified_reason',   # 认证说明「情感博主」
        'ip_location': 'ip_location',           # 「发布于 广东」
        'orientation': 'orientation',    # vertical/horizontal
    },
    'acfun': {
        'channel': 'channel',                  # 频道
        'user_ip': 'author_ip',                # 用户 IP 属地
    },
    'xiaohongshu': {
        'note_type_raw': 'note_type',          # normal / video
    },
    'sohu': {
        'keyword': 'keyword',                  # 关键词
        'upload_region': 'upload_region',      # 上传地
    },
    'haokan': {
        'is_long_video': 'is_long_video',
    },
    'kuaishou': {
        'photo_id': 'photo_id',
        'work_id': 'work_id',
        'kwai_id': 'author_id',           # 快手号
    },
    'douyin': {
        'aweme_id': 'aweme_id',
    },
}

# 各平台「展示文本」字段（数字之外的原文，如"20天前"、"450万"）
# ⚠️ 路径写的是**解析器返回的 key**。若某平台无此项，映射里就不要出现，
#    避免给前端一个永远取不到值的键。
TEXT_STAT_SOURCES: Dict[str, Dict[str, str]] = {
    'weibo': {'view': 'view_count_text',
              'follower': 'follower_count_text'},
    'haokan': {'view': 'play_count_text'},
    'acfun': {'fan': 'author_fans_text'},
    'bilibili': {},
    'xiaohongshu': {},
    'sohu': {},
    'douyin': {},
}


def _is_template_title(title: str, author: str = '') -> bool:
    """判断 title 是否是平台自动生成的模板串

    真实案例：微博 `title` 恒为「{作者}的微博视频」，
    不是用户写的内容 —— 展示给用户毫无信息量。

    ⚠️ 判定必须**保守**：只认「明确的平台模板后缀」。
       我第一版还加了条「过短且无标点 → 判模板」，
       结果把AcFun 的真标题「蕉换幸运」（4 字）误杀了。
       → 短不等于假，漏判只是少个优化，误判是给出错误信息。
    """
    t = (title or '').strip()
    if not t:
        return False
    # 明确的平台模板后缀（各平台实测）
    for suffix in ('的微博视频', '的微博', '的视频', '的动态',
                   '的快手视频', '的抖音视频', '的AcFun视频'):
        if t.endswith(suffix) and len(t) > len(suffix):
            return True
    # 与「作者 + 模板」完全一致
    if author and t == f'{author}的微博视频':
        return True
    return False


def _dig(obj: Any, path: str) -> Any:
    """按点号路径取值，取不到返回 None"""
    cur = obj
    for part in path.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _first(obj: Any, paths: List[str], conv: str = 'raw') -> Any:
    """按优先级取第一个非空值并转换"""
    for p in paths:
        v = _dig(obj, p)
        if v in (None, '', [], {}):
            continue
        if conv == 'ms':
            r = ms_to_s(v)
        elif conv == 'hms':
            r = hms_to_s(v)
        elif conv == 'cn':
            r = cn_number_to_int(v)
        elif conv == 'ts':
            r = ts_to_s(v)
        elif conv == 'html':
            r = strip_html(v)
        else:
            r = v
        if r not in (None, ''):
            return r
    return None


# ══════════════════════════════════════════════════════════
# 三、规范化主函数
# ══════════════════════════════════════════════════════════

# duration 来源与单位（P28 的防御措施）
#
# ⚠️ **逐字段**声明单位，而不是逐平台。
#    我第一版按平台标（'weibo': 's'），结果同一平台内两个字段单位不同
#    就标错了 —— 搜狐的 duration_ms(毫秒) 和 duration_actual_s(秒) 混在一起。
#    平台维度标不出来，字段维度才行。
DURATION_RULES: Dict[str, List[str]] = {
    'douyin': ['duration_ms'],
    'bilibili': ['duration_ms'],       # 由接口 duration(秒)*1000 而来
    'haokan': ['duration_ms'],
    'weibo': ['duration_ms'],# 解析器已把 duration_time(秒)*1000
    'acfun': ['duration_ms'],
    # ⭐ 小红书视频笔记的时长**只存在于 video_meta.duration_ms**，
    #   顶层没有 duration_ms（图集才走顶层，而图集本来就没时长）。
    #   所以 video_meta 必须是主路径。
    'xiaohongshu': ['video_meta.duration_ms', 'duration_ms'],
    # ⭐ 快手 duration 单位是**毫秒**（13100 = 13.1s），
    #   实测与 ffprobe 的 13.10s 吻合。
    'kuaishou': ['duration_ms'],
    'sohu': ['duration_ms', 'duration_actual_s'],
}
DURATION_FIELD_UNIT: Dict[str, str] = {
    'duration_ms': 'ms',
    'video_meta.duration_ms': 'ms',
    'duration_actual_s': 's',          # 搜狐截断检测算出的真实秒数
}
# 备用：文本型时长（hms）
DURATION_TEXT_SOURCES: Dict[str, List[str]] = {
    'haokan': ['time_length'],
    'weibo': ['duration_text'],
    'sohu': ['time_length_format', 'tip'],
    'bilibili': [],
    'acfun': [],
    'xiaohongshu': [],
    'douyin': [],
}


# 中文平台名 → 内部 key（防止调用方传错；P29 同类问题）
PLATFORM_ALIAS: Dict[str, str] = {
    '抖音': 'douyin', 'B站': 'bilibili', '哔哩哔哩': 'bilibili',
    '好看视频': 'haokan', '搜狐': 'sohu', '搜狐视频': 'sohu',
    '微博': 'weibo', 'AcFun': 'acfun', 'acfun': 'acfun',
    '小红书': 'xiaohongshu',
}


def resolve_platform(name: str) -> str:
    """把平台名归一到内部 key

    ⚠️ 解析器的 name 带 `_pure` 后缀（douyin_pure），
    结果里的 platform 字段不带 —— 两处都要能解析。
    """
    n = (name or '').strip()
    n = n.replace('_pure', '')
    return PLATFORM_ALIAS.get(n, n)


def normalize_meta(result: Dict[str, Any],
                   platform: str = '') -> Dict[str, Any]:
    """把解析器的原始结果规范化成统一元信息结构

    platform 省略时自动取result['platform']。
    在原 result 上**就地补字段**（保持向后兼容），
    同时返回 `meta` 子字典供前端直接使用。

    原则：接口没给 → None。不用别的字段推算，不编造。
    """
    if not result:
        return {}

    platform = resolve_platform(platform or result.get('platform', ''))
    if platform not in STAT_SOURCES and platform not in DURATION_RULES:
        # 未知平台：至少把标题/文案/封面归一，缺失项留None
        platform = platform or ''


    src = result           # 解析器返回值即数据源
    meta: Dict[str, Any] = {}

    # ---- 标题 ----
    # ⚠️ 有些平台的 title 是**模板串**而非真标题：
    #   微博 title = "陆屿熙的微博视频"（= 作者 + "的微博视频"）
    #   真实文案在 text/description里。
    #   → 命中模板特征时改用文案首句，标title_source 说明。
    raw_title = (result.get('title') or '').strip()
    title_source = 'ssr'
    if _is_template_title(raw_title, result.get('author') or ''):
        # 模板串（如微博「XX的微博视频」）→ 丢弃，改由文案首句兜底
        raw_title = ''
        title_source = 'template_skipped'
    meta['title'] = raw_title
    meta['title_source'] = title_source

    # ---- 文案 ----
    desc = (result.get('description') or result.get('caption')
            or result.get('desc') or '')
    desc = strip_html(desc)
    # title 是模板串时，用文案首句当标题（比"XX的微博视频"有用得多）
    if not meta['title'] and desc:
        head = re.split(r'[。！？!?\n]', desc.strip(), 1)[0]
        head = re.sub(r'#\S{0,24}#?', '', head).strip()
        if len(head) >= 4:
            meta['title'] = head[:60]
            meta['title_source'] = 'desc_head'
    meta['description'] = desc

    # ---- 标题文案（2026-10-22：给「复制文案」用）----
    # ⭐ 为什么要有这个合成字段，而不是让前端自己挑 title/description：
    #   各平台的 title 与 description 关系不一样 ——
    #     抖音：两者**完全相同**（话题也塞在 desc 里）
    #     B站：description 是 '-'（1 个字符，等于没有）
    #   前端若直接复制 description，B站用户复制到的就是一个「-」。
    #   这里统一成一条规则：description 有效就用它，否则回落 title。
    #   抖音 → 复制完整文案（含话题）；B站 → 复制视频标题。
    _copy_text = desc.strip()
    if len(_copy_text) <= 1 or _copy_text in ('-', '－', '—'):
        _copy_text = (meta.get('title') or '').strip()
    meta['copy_text'] = _copy_text

    # ---- 封面 ----
    meta['cover'] = result.get('cover') or ''

    # ---- 作者 ----
    meta['author_name'] = result.get('author') or ''
    meta['author_id'] = str(result.get('author_id')
                or result.get('author_uid') or '')
    meta['author_avatar'] = result.get('author_avatar') or ''

    # ---- BGM（2026-10-11，抖音先行）----
    # 字段宽容：上游给的可能是 None/''/非串，一律安全收敛成 ''（不编造）
    meta['music_url'] = str(result.get('music_url') or '')
    meta['music_title'] = str(result.get('music_title') or '')
    meta['music_author'] = str(result.get('music_author') or '')

    # ---- 时长（统一秒）----
    # ⚠️ P28防御：各平台同名 duration 字段单位不同，
    #   所以映射表必须显式声明单位，不能靠字段名猜。
    dur: Optional[float] = None
    for p in DURATION_RULES.get(platform, []):
        v = _dig(result, p)
        if v in (None, '', 0):
            continue
        unit = DURATION_FIELD_UNIT.get(p, 'ms')
        dur = float(v) if unit == 's' else ms_to_s(v)
        if dur:
            break
    if not dur:
        dur = _first(result, DURATION_TEXT_SOURCES.get(platform, []), 'hms')
    meta['duration_s'] = dur

    # ---- 发布时间 ----
    # ⚠️ 各平台时间戳单位不同（B站/微博=秒，AcFun/小红书/搜狐=毫秒）。
    #   这里统一归一到「秒」，超过 1e11 判定为毫秒（P30）。
    raw_ts = _first(result, PUBLISH_SOURCES.get(platform, []))
    ts_sec: Optional[int] = None
    if isinstance(raw_ts, (int, float)) and raw_ts > 0:
        ts_sec = int(raw_ts / 1000) if raw_ts > 1e11 else int(raw_ts)
    meta['publish_ts'] = ts_sec
    # 平台自带的展示文本优先（「20天前」比"2026-09-15"更贴近平台显示）
    meta['publish_time_text'] = (result.get('date_text')
                                 or result.get('publish_date_text')
                                 or result.get('date')
                                 or ts_to_s(ts_sec))
    meta['publish_time'] = ts_to_s(ts_sec)      # 规范化的 'YYYY-MM-DD HH:MM'

    # ---- 统计数字 ----
    stats: Dict[str, int] = {}
    for std, per_plat in STAT_SOURCES.items():
        paths = per_plat.get(platform, per_plat.get('_default', []))
        v = _first(result, paths, 'cn')
        # 字段宽容解码（TVHelper 教训，2026-10-11）：上游把数字变字符串
        # 是改版常见形态，"123" 也要吃下去，不能只认 int/float
        if isinstance(v, str) and v.strip().isdigit():
            v = int(v.strip())
        if isinstance(v, (int, float)) and v >= 0:
            stats[std] = int(v)
    meta['stats'] = stats

    # ---- 统计展示文本 ----
    # ⚠️ 键必须始终存在（哪怕为空 dict）—— 前端不该用「键是否存在」
    # 来判断平台支不支持，否则每加一个平台都要改前端判断逻辑。
    stats_text: Dict[str, str] = {}
    for std, path in TEXT_STAT_SOURCES.get(platform, {}).items():
        v = _dig(result, path)
        if v:
            stats_text[std] = str(v)
    meta['stats_text'] = stats_text

    # ---- 话题标签 ----
    tags: List[str] = []
    for t in (result.get('tags') or result.get('tag_list') or []):
        if isinstance(t, str) and t.strip():
            tags.append(_clean_tag(t))
        elif isinstance(t, dict):
            nm = t.get('name') or t.get('tagName') or ''
            if nm:
                tags.append(_clean_tag(str(nm)))
    if not tags:
        # 从文案里提 #话题#
        # ⭐ 2026-10-22 修复：原来只用 `#([^#\s]{1,24})#`（要求**两侧**都有 #），
        #   那是小红书/微博的格式。**抖音只有前侧 #**
        #   （`#分享你的快餐推荐 #猪脚饭 #美食分享`），
        #   一个都匹配不上 → 抖音的 tags 恒为空数组。
        #   实测：抖音 title 明明带 5 个话题，tags 却是 []。
        #   两条规则都要跑：先双侧（微博/小红书），再前侧（抖音）。
        tags.extend(extract_hash_tags(meta['description']))
        if not tags:
            # description 空的平台（B站）话题常在 title 里
            tags.extend(extract_hash_tags(meta.get('title') or ''))
    meta['tags'] = list(dict.fromkeys(t for t in tags if t))

    # ---- 平台特有 ----
    # ⚠️ 同 stats_text：键始终存在，前端不必判断「有没有这个键」
    extra: Dict[str, Any] = {}
    for std, path in EXTRA_RULES.get(platform, {}).items():
        if not path:
            continue
        v = _dig(result, path)
        if v not in (None, '', [], {}):
            extra[std] = v
    meta['extra'] = extra

    # ---- 回写到 result（向后兼容 +便于老代码读取）----
    result['meta'] = meta
    for k in ('title', 'description', 'cover', 'duration_s',
              'publish_time', 'author_name', 'music_url'):
        if meta.get(k) and not result.get(k):
            result[k] = meta[k]
    # 统一别名（前端只用这些）
    result.setdefault('stats', meta['stats'])
    result.setdefault('tags', meta['tags'])
    # ⭐ copy_text 必须回填到 result —— 前端读的是顶层字段，
    #   只放在 meta 子字典里客户端拿不到。
    result.setdefault('copy_text', meta.get('copy_text') or '')
    if meta['stats_text']:
        result.setdefault('stats_text', meta['stats_text'])
    if meta['extra']:
        result.setdefault('extra', meta['extra'])
    result['meta_schema_version'] = 1

    # 资源直链统一升级为 https —— 小程序只允许 https，
    # 平台的 CDN 却常返回 http://，不改的话封面/视频在端上必然加载失败。
    # 放在 normalize_meta 是因为它是**所有平台解析器的统一出口**，
    # 改一次三端（小程序/Flutter/App）同时受益，
    # 且未来新平台返回 http 也不用再改代码。
    # 详见 app/url_scheme.py 的说明（含为什么不做探测式 http 回退）。
    try:
        from app.url_scheme import upgrade_result, https_url
        upgrade_result(result)
        # ⚠️ meta 是 result 的**字段子集拷贝**，上面升级 result 不会
        #    自动同步到已经写进 meta 的值。若不同步，meta 里会留着一个
        #    http:// 的 cover，而 result 里是 https:// —— 同一个响应里
        #    出现两种协议，比不升级更难排查。所以这里要同步一次。
        for _f in ('cover', 'music_url', 'subtitle_url'):
            if isinstance(meta.get(_f), str):
                meta[_f] = https_url(meta[_f])
    except Exception:                       # pragma: no cover - 绝不因协议升级而让解析失败
        pass

    return meta


def field_coverage(result: Dict[str, Any]) -> Dict[str, bool]:
    """返回各元信息字段的填充情况（自检/测试用）"""
    meta = result.get('meta') or {}
    return {
        'title': bool(meta.get('title')),
        'description': bool(meta.get('description')),
        'cover': bool(meta.get('cover')),
        'author_name': bool(meta.get('author_name')),
        'author_avatar': bool(meta.get('author_avatar')),
        'duration_s': bool(meta.get('duration_s')),
        'publish_time': bool(meta.get('publish_time')),
        'stats': bool(meta.get('stats')),
        'tags': bool(meta.get('tags')),
    }


if __name__ == '__main__':
    import json
    # ---- 单元自测 ----
    # 中文数字换算
    assert cn_number_to_int('115.9万') == 1159000
    assert cn_number_to_int('2.3万') == 23000
    assert cn_number_to_int('1,810') == 1810
    assert cn_number_to_int(298301) == 298301
    assert cn_number_to_int('4.9万次播放') == 49000
    # 时长
    assert ms_to_s(261389) == 261.39
    assert hms_to_s('5:19') == 319.0
    assert hms_to_s('00:26') == 26.0
    # 文本
    assert strip_html('<a href="#">#话题#</a> hi') == '#话题# hi'
    assert _clean_tag('杨幂[话题]') == '杨幂'
    assert ts_to_s(1577835803).startswith('2020-01-01')
    # 时间戳归一（毫秒 → 秒）
    assert ts_to_s(1791099362184).startswith('2026-10')

    r = normalize_meta({
        'platform': 'bilibili', 'title': 'T', 'cover': 'C',
        'duration_ms': 213000, 'publish_time_ts': 1577835803,
        'like_count': 2943304, 'view_count': 106761993,
        'comment_count': 236112, 'collect_count': 1548287,
        'coin_count': 1278841, 'share_count': 497035,
        'danmaku_count': 150315, 'copyright': 1, 'aid': 1, 'cid': 2,
    }, 'bilibili')
    print(json.dumps(r, ensure_ascii=False, indent=2))
    assert r['duration_s'] == 213.0
    assert r['stats']['like'] == 2943304
    assert r['stats']['coin'] == 1278841
    assert r['publish_time'].startswith('2020-01-01')
    # ⚠️ 键必须始终存在，前端不该用「有没有这个键」判断平台能力
    for k in ('stats', 'stats_text', 'tags', 'extra'):
        assert k in r, f'meta 缺键 {k}'

    # 微博：title 是模板串「XX的微博视频」→ 应改用文案首句
    assert _is_template_title('陆屿熙的微博视频', '陆屿熙')
    assert _is_template_title('某某的微博视频')
    assert not _is_template_title('真正的手写标题内容', '作者')
    # ⚠️ 保守判定：短标题≠ 模板串（AcFun 真实标题只有 4 字）
    assert not _is_template_title('蕉换幸运', '九星之歌')
    assert not _is_template_title('短标题', '作者')

    # 微博：秒级时长 + 中文播放量
    w = normalize_meta({
        'platform': 'weibo', 'title': 'W', 'duration_ms': 319414,
        'publish_time_ts': 1789400571, 'date_text': '20天前',
        'like_count': 4383, 'comment_count': 359, 'share_count': 316,
        'view_count_text': '450万', 'ip_location': '发布于 广东',
        'verified_reason': '情感博主', 'orientation': 'vertical',
    }, 'weibo')
    assert w['duration_s'] == 319.41, w['duration_s']
    assert w['stats']['share'] == 316
    assert w['stats_text']['view'] == '450万'
    assert w['publish_time_text'] == '20天前'
    assert w['extra']['ip_location'] == '发布于 广东'
    # 模板标题 → 降级到文案首句
    w2 = normalize_meta({
        'platform': 'weibo', 'title': '陆屿熙的微博视频', 'author': '陆屿熙',
        'description': '活了几百年的疑惑终于解开，原来大变活人的机关是这样的！',
    }, 'weibo')
    assert w2['title'] == '活了几百年的疑惑终于解开，原来大变活人的机关是这样的', \
        w2['title']
    assert w2['title_source'] == 'desc_head', w2['title_source']

    # 搜狐：秒级 duration_actual_s 回退
    s_ = normalize_meta({
        'platform': 'sohu', 'title': 'S', 'duration_actual_s': 30.04,
        'publish_time_ms': 1740200026905, 'keyword': '网络歌曲',
        'upload_region': '陕西',
    }, 'sohu')
    assert s_['duration_s'] == 30.04
    assert s_['publish_time'].startswith('2025-02')
    assert s_['extra']['upload_region'] == '陕西'

    print('\n✅ 元信息规范层自测通过')
