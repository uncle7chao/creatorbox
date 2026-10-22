# -*- coding: utf-8 -*-
"""百度信息流视频解析器测试（2026-10-22 新增平台）。

平台形态（实测）：
    mr.baidu.com/r/<code>  → 302 → mbd.baidu.com/newspage/data/videoshare?nid=sv_<vid>
    落地页 SSR 内嵌 videoInfo JSON（play_url / duration / clarityArr / posterImage）

⭐ 与「好看视频」（haokan.baidu.com）是两个不同产品：
   好看走 _format=json 接口，本平台走信息流分享页 SSR —— URL 与接口形态都不同。

跑法： python tests/test_baidu_parser.py
（真网测试会受网络波动影响；离线部分永远可跑）
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_baidu_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'baidu.db')
sys.path.insert(0, '.')

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


from app.parsers.baidu_pure import (  # noqa: E402
    BaiduVideoPureParser, _extract_json_obj, _height_of, URL_RE)

# ══════════════ 1. 离线：URL 提取与匹配 ══════════════
p = BaiduVideoPureParser()
print('\n── 1. URL 识别 ──')

check('能识别 mr.baidu.com 短链',
      p.extract_url('https://mr.baidu.com/r/24UZVL6dTCo?f=cp&rs=743')
      == 'https://mr.baidu.com/r/24UZVL6dTCo')
check('能从分享文案里抠出短链',
      p.extract_url('看看这个 https://mr.baidu.com/r/abc123 很有意思')
      == 'https://mr.baidu.com/r/abc123')
check('能识别 mbd.baidu.com 落地页',
      p.extract_url(
          'https://mbd.baidu.com/newspage/data/videoshare?nid=sv_123&x=1')
      .startswith('https://mbd.baidu.com/newspage/data/videoshare'))
check('非百度链接提取为空',
      p.extract_url('https://v.douyin.com/abc/') == '')
check('match：mr.baidu.com → True',
      p.match('https://mr.baidu.com/r/abc'))
check('match：mbd.baidu.com → True',
      p.match('https://mbd.baidu.com/newspage/data/videoshare?nid=sv_1'))
check('match：抖音链接 → False', not p.match('https://v.douyin.com/abc/'))
check('match：好看视频 → False（不同产品）',
      not p.match('https://haokan.baidu.com/v?vid=1'))
check('match：非 http → False', not p.match('ftp://x.com/'))

# ══════════════ 2. 离线：清晰度推算 ══════════════
print('\n── 2. 清晰度推算 ──')
check('key=1080p → 1080', _height_of('1080p', {}) == 1080)
check('key=sc → 720（百度 sc 档对应超清）',
      _height_of('sc', {}, '/x/sc/cae_h264/1.mp4') == 720)
check('key=hd → 480（百度 hd 档对应高清）',
      _height_of('hd', {}, '/x/hd/cae_h264/1.mp4') == 480)
check('key=sd → 360', _height_of('sd', {}, '/x/sd/1.mp4') == 360)
check('URL 里的 1080p 目录可识别',
      _height_of('x', {}, '/1080p/cae/1.mp4') == 1080)
check('推不出时返回 None（不编造）', _height_of('zzz', {}) is None)

# ══════════════ 3. 离线：JSON 提取（括号配平）══════════════
print('\n── 3. videoInfo 提取 ──')
NESTED = ('x{"a":{"b":1},"videoInfo":{"play_url":"http://a/b.mp4",'
          '"clarityArr":[{"key":"1080p","url":"u1"}]}}y')
obj = _extract_json_obj(NESTED, '"videoInfo":')
check('能抠出嵌套 JSON（不被第一个 } 截断）', obj is not None)
check('抠出的对象含 play_url',
      bool(obj) and obj.get('play_url') == 'http://a/b.mp4')
check('抠出的对象含 clarityArr',
      bool(obj) and len(obj.get('clarityArr') or []) == 1)
check('找不到时返回 None',
      _extract_json_obj('no marker here', '"videoInfo":') is None)

# ══════════════ 4. 离线：结果构造 ══════════════
print('\n── 4. 结果构造 ──')
vi = {
    'play_url': 'https://vd3.bdstatic.com/mda/hd/cae_h264/1/mda.mp4',
    'duration': '494',
    'vid': '2325954398339771924',
    'posterImage': 'http://f7.baidu.com/it/u=1&fm=222',
    'title': '测试标题',
    'clarityArr': [
        {'key': '1080p', 'title': '蓝光', 'rank': 3,
         'url': 'https://vd3.bdstatic.com/mda/1080p/cae_h264/1/mda.mp4'},
        {'key': 'sc', 'title': '超清', 'rank': 2,
         'url': 'https://vd3.bdstatic.com/mda/sc/cae_h264/1/mda.mp4'},
        {'key': 'hd', 'title': '高清', 'rank': 1,
         'url': 'https://vd3.bdstatic.com/mda/hd/cae_h264/1/mda.mp4'},
    ],
}
r = p._build_result(vi, '1080p', 'https://mbd.baidu.com/x')
check('success=True', r.get('success') is True)
check('platform=baidu', r.get('platform') == 'baidu')
check('title 正确', r.get('title') == '测试标题')
check('duration 换算成毫秒（494 秒 → 494000）',
      r.get('duration_ms') == 494000, str(r.get('duration_ms')))
check('3 个档位', r.get('options_count') == 3)
check('选了 1080P（不低于 want_h 的最小档）',
      r.get('quality') == '1080P', str(r.get('quality')))
check('max_quality_free=1080P', r.get('max_quality_free') == '1080P')
check('直链是 1080p 那条', '/1080p/' in (r.get('video_url') or ''))
check('封面取 posterImage', 'f7.baidu.com' in (r.get('cover') or ''))
check('vid 已带出', r.get('vid') == '2325954398339771924')
check('档位 label 保留（蓝光/超清/高清）',
      [o.get('label') for o in r['options']] == ['蓝光', '超清', '高清'])
check('页面上游 URL 已记录', 'mbd.baidu.com' in (r.get('page_url') or ''))

# clarityArr 缺失 → 用 play_url 兜底
r2 = p._build_result({'play_url': 'https://x/y.mp4', 'duration': '10'},
                      '1080p', 'https://mbd.baidu.com/x')
check('无 clarityArr 时用 play_url 兜底', r2.get('success') is True)
check('兜底时也有 1 个档位', r2.get('options_count') == 1)

# 两者都无 → 失败
r3 = p._build_result({'duration': '10'}, '1080p', 'https://x')
check('既无 clarityArr 又无 play_url → 失败',
      r3.get('success') is False)

print(f'\n════ 百度视频解析器：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过（离线部分）')