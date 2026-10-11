"""元信息字段探测：把各平台原始响应里的可用字段全打出来

用途：为「统一元信息规范」提供事实依据 —— 不靠猜，只看接口真实给什么。

运行：python probe_meta_fields.py
"""
import gzip
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any, Dict

sys.path.insert(0, r'D:\WorkBuddyFILE\CreatorBox\server')

UA_PC = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
         ' (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _get(url: str, referer: str = '') -> Any:
    h = {'User-Agent': UA_PC, 'Accept-Encoding': 'gzip, deflate'}
    if referer:
        h['Referer'] = referer
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers=h),
        timeout=25, context=_SSL).read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw


def _get_json(url: str, referer: str = '') -> Any:
    return json.loads(_get(url, referer).decode('utf-8', 'ignore'))


def _extract_obj(html: str, key: str) -> Any:
    """从 HTML 里按 "key": 定位对象并做花括号配平"""
    i = html.find(key)
    if i < 0:
        return None
    j = html.index('{', i)
    depth = 0
    for k in range(j, len(html)):
        if html[k] == '{':
            depth += 1
        elif html[k] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(html[j:k + 1])
    return None


def dump(obj: Any, label: str, indent: int = 0):
    """只打标量与短 dict，跳过播放地址等超长字段"""
    pad = '  ' * indent
    if isinstance(obj, dict):
        for k in sorted(obj):
            v = obj[k]
            if isinstance(v, (str, int, float, bool)) and str(v).strip():
                sv = str(v)
                if len(sv) > 90:
                    sv = sv[:90] + '…'
                print(f'{pad}{k:24s} = {sv}')
            elif isinstance(v, dict) and len(json.dumps(v)) < 260:
                print(f'{pad}{k}:')
                dump(v, k, indent + 1)
            elif isinstance(v, list):
                print(f'{pad}{k:24s} : list[{len(v)}]')
    print()


def probe_douyin():
    print('=' * 72)
    print('抖音 · aweme_detail 原始标量字段')
    print('=' * 72)
    import asyncio
    from app.parsers.douyin_pure import DouyinPureParser
    r = asyncio.run(DouyinPureParser().parse(
        'https://v.douyin.com/hZMkNvXLtLc/'))
    # 解析器内部已拿到原始 aweme_detail
    raw = getattr(DouyinPureParser, '_last_detail', None)
    if raw:
        dump(raw, 'douyin')
    else:
        print('  （解析器未暴露原始对象，改用结果字段）')
        dump(r, 'result')
    print()


def probe_bilibili():
    print('=' * 72)
    print('B站 · view 接口')
    print('=' * 72)
    d = _get_json('https://api.bilibili.com/x/web-interface/view'
                  '?bvid=BV1GJ411x7h7',
                  'https://www.bilibili.com/')['data']
    dump({k: v for k, v in d.items() if k not in ('pages', 'subtitle')},
         'bili')
    print('  owner:', json.dumps(d.get('owner'), ensure_ascii=False))
    print('  stat :', json.dumps(d.get('stat'), ensure_ascii=False))
    print()


def probe_haokan():
    print('=' * 72)
    print('好看视频 · curVideoMeta')
    print('=' * 72)
    from app.parsers.haokan_pure import _SESSION, API_TMPL, PAGE_TMPL
    j = json.loads(_SESSION.get(
        API_TMPL.format(vid='1688233510589355861'),
        referer=PAGE_TMPL.format(vid='1688233510589355861')
    ).decode('utf-8', 'ignore'))
    cur = j['data']['apiData']['curVideoMeta']
    dump({k: v for k, v in cur.items()
          if k not in ('clarityUrl', 'coverImage')}, 'haokan')
    print()


def probe_sohu():
    print('=' * 72)
    print('搜狐 · video/info')
    print('=' * 72)
    from app.parsers.sohu_pure import _get, API_TMPL
    d = _get(API_TMPL.format(vid='620251480'))['data']
    dump({k: v for k, v in d.items()
          if 'url' not in k.lower() and 'mp4' not in k.lower()}, 'sohu')
    print('  user:', json.dumps(d.get('user'), ensure_ascii=False))
    print()


def probe_weibo():
    print('=' * 72)
    print('微博 · component + statuses/show')
    print('=' * 72)
    from app.parsers.weibo_pure import (_post, COMPONENT_API, SHOW_PAGE,
                                        STATUS_API)
    oid = '1034:5343195622473745'
    j = _post(COMPONENT_API.format(oid=oid),
              {'Component_Play_Playinfo': {'oid': oid}},
              SHOW_PAGE.format(oid=oid))
    info = j['data']['Component_Play_Playinfo']
    dump({k: v for k, v in info.items()
          if k not in ('urls', 'cover_image', 'avatar')}, 'weibo')
    print()


def probe_acfun():
    print('=' * 72)
    print('AcFun · currentVideoInfo + user')
    print('=' * 72)
    from app.parsers.acfun_pure import _get_text, _extract_obj
    html = _get_text('https://www.acfun.cn/v/ac48890260')
    cvi = _extract_obj(html, '"currentVideoInfo"')
    dump({k: v for k, v in cvi.items()
          if 'Json' not in k and 'ranscode' not in k}, 'acfun')
    for k in ('"originImage"', '"coverImgInfo"', '"user"'):
        o = _extract_obj(html, k)
        if o:
            print(f'  {k}:')
            dump(o, k, 2)
    print()


def probe_xhs():
    print('=' * 72)
    print('小红书 · noteData（图集 + 视频各一条）')
    print('=' * 72)
    from app.parsers.xiaohongshu_pure import (_parse_state, _find_note,
                                               IOS_UA, _normalize_url)
    import gzip as _gz
    import urllib.request as _u

    def fetch(url):
        req = _u.Request(url, headers={'User-Agent': IOS_UA,
                                       'Accept-Encoding': 'gzip, deflate'})
        raw = _u.urlopen(req, timeout=30, context=_SSL).read()
        if raw[:2] == b'\x1f\x8b':
            raw = _gz.decompress(raw)
        return raw.decode('utf-8', 'ignore')

    samples = [
        ('图集', 'https://www.xiaohongshu.com/discovery/item/'
                 '6a827209000000002701cde0?xsec_token='
                 'AB7esHwJgaSaSlhVeq7GJlZN8Fi1J6MrUIjviv8R_APxM='
                 '&xsec_source=pc_share'),
        ('视频', 'https://www.xiaohongshu.com/discovery/item/'
                 '6a72adee0000000033036edf?xsec_token='
                 'ABgKYGq72MJJJWO8OVQh3MtnwjRfcqKYxsujnzRIHNdTA='
                 '&xsec_source=pc_share'),
    ]
    for tag, u in samples:
        st = _parse_state(fetch(_normalize_url(u)))
        note = _find_note(st) if st else None
        if not note:
            print(f'  [{tag}] 未取到笔记')
            continue
        print(f'  --- {tag} ---')
        dump({k: v for k, v in note.items()
              if k not in ('imageList', 'video', 'user')}, tag, 1)
        uu = note.get('user') or {}
        print('  user:', json.dumps(
            {k: uu.get(k) for k in ('nickName', 'userId', 'avatar',
                                    'redId', 'desc', 'ipLocation',
                                    'fans', 'interact')},
            ensure_ascii=False)[:260])
        print()


if __name__ == '__main__':
    for fn in (probe_bilibili, probe_haokan, probe_sohu, probe_weibo,
               probe_acfun, probe_xhs):
        try:
            fn()
        except Exception as e:
            print(f'  ❌ {fn.__name__} 失败: {str(e)[:90]}\n')
