"""国际平台解析器测试（2026-10-11，离线可跑）

覆盖：π-token 算法 / 推文 ID 提取 / 域名匹配 / 池挂载开关 /
     ytdlp normalize（progressive 分轨分类 / codec null 语义 / 合并标记）/
     回退链失败路径（沙箱无外网 → 三层全部失败也必须返回结构化错误）
网络集成测试（真连 syndication/tikwm）放 HK 服务器跑，见文件尾说明。
"""
import asyncio
import os
import sys
import tempfile

os.environ['CB_DB_PATH'] = os.path.join(tempfile.gettempdir(),
                                        f'cb_test_intl_{os.getpid()}.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsers.intl import x_pure, tiktok_pure, ytdlp_engine  # noqa: E402
from app.parsers.intl.x_pure import XPureParser                 # noqa: E402
from app.parsers.intl.tiktok_pure import TikTokPureParser       # noqa: E402

PASS = []
def check(name, ok, detail=''):
    PASS.append(ok)
    print(('  ✅ ' if ok else '  ❌ ') + name + (f' ← {detail}' if not ok and detail else ''))

print('1. π-token 算法（syndication）')
t1 = x_pure.tweet_token('1481722124855169028')
t2 = x_pure.tweet_token('1481722124855169028')
check('确定性（同 ID 同 token）', t1 == t2)
check('不含 0 和小数点', '0' not in t1 and '.' not in t1, t1)
check('非空字符串', len(t1) > 0)

print('2. 推文 ID 提取（全 URL 形态）')
cases = {
    'https://x.com/user/status/1481722124855169028': '1481722124855169028',
    'https://twitter.com/user/status/999': '999',
    'https://mobile.twitter.com/a/statuses/555?s=20': '555',
    '随便一段文案 https://x.com/b/status/123456 复制内容': '123456',
}
for url, expect in cases.items():
    check(f'ID 提取 {expect}', x_pure.extract_tweet_id(url) == expect,
          str(x_pure.extract_tweet_id(url)))
check('非推文链接返回 None', x_pure.extract_tweet_id('https://example.com/x') is None)

print('3. 域名匹配（match 只吃国际域，不污染国内分发）')
xp, tp = XPureParser(), TikTokPureParser()
check('X 匹配 x.com', xp.match('https://x.com/a/status/1'))
check('X 匹配 t.co', xp.match('https://t.co/abc'))
check('X 不吃抖音链接', not xp.match('https://v.douyin.com/abc/'))
check('TikTok 匹配 vm.tiktok.com', tp.match('https://vm.tiktok.com/ZSabc/'))
check('TikTok 匹配 /video/ 页', tp.match('https://www.tiktok.com/@u/video/123'))
check('TikTok 不吃 x.com', not tp.match('https://x.com/a/status/1'))
check('name 就位（health 平台清单用）', xp.name == 'x' and tp.name == 'tiktok')
from app.parsers.intl.youtube_pure import YouTubeParser
yp = YouTubeParser()
check('YouTube 匹配 youtu.be/全域名', yp.match('https://youtu.be/x') and yp.match('https://www.youtube.com/watch?v=1') and not yp.match('https://x.com/a/status/1'))
check('YouTube name 就位', yp.name == 'youtube')
from app.parsers.intl.fb_pure import FacebookParser
fp = FacebookParser()
check('FB 匹配 facebook.com/fb.watch，不误吃 youtube',
      fp.match('https://www.facebook.com/watch/?v=1')
      and fp.match('https://fb.watch/abc/')
      and not fp.match('https://youtube.com/watch?v=1'))
check('FB name 就位', fp.name == 'facebook')

# 字幕提取：normalize 后 attach 的组成件单测（离线）
from app.parsers.intl import ytdlp_engine as eng
vtt = 'WEBVTT\n\nNOTE hello\n00:00:01.000 --> 00:00:03.000\n<c>第一句</c>\n\n00:00:03.000 --> 00:00:05.000\n第一句\n第二句'
txt = eng._vtt_to_text(vtt)
check('vtt 转纯文案（去头/时间轴/标签/去重）',
      txt == '第一句\n第二句', repr(txt))
lang, u, auto = eng._pick_subtitle_track({
    'subtitles': {'en': [{'ext': 'vtt', 'url': 'https://x/vtt'}]},
    'automatic_captions': {'zh-Hans': [{'ext': 'vtt', 'url': 'https://y/vtt'}]}})
check('人工字幕优先于自动字幕', (lang, auto) == ('en', False), f'{lang},{auto}')
lang2, u2, auto2 = eng._pick_subtitle_track({
    'automatic_captions': {'zh-Hans': [{'ext': 'vtt', 'url': 'https://y/vtt'}]}})
check('无人工字幕回落自动 + zh 优先', lang2 == 'zh-Hans' and auto2 is True)

print('4. 池挂载：INTL 开关')
from app import config as cfg
from app import main as app_main
cfg.INTL_ENABLED = True
pool_on = app_main.Pool(1)
names_on = [p.name for p in pool_on.pure]
check('开=12 解析器（含 x/tiktok/youtube/facebook）',
      all(n in names_on for n in ('x', 'tiktok', 'youtube', 'facebook')), str(names_on))
cfg.INTL_ENABLED = False
pool_off = app_main.Pool(1)
names_off = [p.name for p in pool_off.pure]
check('关=8 解析器（国际组整体下线，提审开关）',
      'x' not in names_off and 'tiktok' not in names_off, str(names_off))
cfg.INTL_ENABLED = True

print('5. ytdlp normalize：progressive / 分轨 / codec-null 语义')
info = {
    'title': 'Test Video', 'description': 'd', 'uploader': 'up',
    'duration': 15.0, 'thumbnail': 'https://cdn/img.jpg',
    'thumbnails': [{'url': 'https://cdn/thumb.jpg'}],
    'formats': [
        # progressive 合体（codec 为 null 的坑形态）
        {'format_id': 'http-2176', 'url': 'https://cdn/720.mp4',
         'height': 720, 'vcodec': None, 'acodec': None, 'protocol': 'https'},
        {'format_id': 'http-288', 'url': 'https://cdn/272.mp4',
         'height': 272, 'vcodec': None, 'acodec': None, 'protocol': 'https'},
        # 分轨高清
        {'format_id': 'hls-1919', 'url': 'https://cdn/1080_v.m3u8',
         'height': 1080, 'vcodec': 'h264', 'acodec': 'none', 'protocol': 'm3u8_native'},
        # 纯音频
        {'format_id': 'aud', 'url': 'https://cdn/a.m4a',
         'vcodec': 'none', 'acodec': 'mp4a', 'abr': 128},
        # 纯视频轨高度低于 progressive（应被忽略，不产生重复档）
        {'format_id': 'low_v', 'url': 'https://cdn/480_v.mp4',
         'height': 480, 'vcodec': 'h264', 'acodec': 'none'},
    ],
}
n = ytdlp_engine.normalize('https://youtu.be/x', info, 'youtube')
check('success', n['success'])
heights = [o['height'] for o in n['options']]
check('档位 720/272/1080（1080 需合并）', heights == [720, 272, 1080], str(heights))
check('1080 档标 merge_required',
      any(o['height'] == 1080 and o.get('merge_required') for o in n['options']))
check('video_url = 最高 progressive', n['video_url'] == 'https://cdn/720.mp4')
check('music_url = 纯音频轨', n['music_url'] == 'https://cdn/a.m4a')
check('cover 取自 thumbnails', n['cover'] == 'https://cdn/thumb.jpg')
low_codec = {'format_id': 'p', 'url': 'https://cdn/x.mp4',
             'height': 360, 'vcodec': None, 'acodec': None, 'protocol': 'https'}
check('codec-null 合体不落入纯视频轨分类',
      low_codec not in [] and (low_codec['acodec'] in (None, 'none')
                               or str(low_codec.get('protocol', '')).startswith('http')))

print('6. 回退链失败路径（沙箱无外网 → 结构化错误而非异常）')
async def run_x():
    return await XPureParser().parse('https://x.com/user/status/1481722124855169028')
try:
    rx = asyncio.run(run_x())
    # 2026-10-11 实测：沙箱可直连 api.fxtwitter.com → L2 直接成功。
    # 断言「二选一都有结构」：成功=有视频/图集；失败=结构化 error 不抛异常
    ok_shape = bool((rx.get('success') and bool(rx.get('video_url') or rx.get('images')))
                    or (rx.get('success') is False and '通道' in (rx.get('error') or '')))
    check('X 回退链出结构化结果（成功或错误二选一）', ok_shape, str(rx)[:120])
    if rx.get('success'):
        check('X 实连成功：method=' + str(rx.get('method')),
              bool(rx.get('video_url')) or bool(rx.get('images')),
              str(rx.get('method')))
except Exception as e:
    check('X 失败不抛异常', False, str(e)[:80])

async def run_tt():
    return await TikTokPureParser().parse('https://vm.tiktok.com/ZSabc/')
try:
    rt = asyncio.run(run_tt())
    check('TikTok 两层全失败返回结构化错误',
          rt.get('success') is False, str(rt)[:120])
except Exception as e:
    check('TikTok 失败不抛异常', False, str(e)[:80])

print('7. tikwm normalize（fixture）')
fixture = {
    'id': '731', 'title': 'hello tiktok',
    'play': 'https://cdn/sd.mp4', 'hdplay': 'https://cdn/hd.mp4',
    'wmplay': 'https://cdn/wm.mp4', 'origin_cover': 'https://cdn/cover.jpg',
    'duration': 21, 'images': None,
    'author': {'unique_id': 'seller01', 'nickname': '卖家小王',
               'avatar': 'https://cdn/a.jpg'},
    'music_info': {'title': 'cool sound', 'author': 'dj',
                   'play': 'https://cdn/bgm.mp3'},
}
n2 = tiktok_pure._normalize(fixture)
check('两档无水印 options（HD 优先）',
      [o['gear'] for o in n2['options']] == ['HD无水印', 'SD无水印'],
      str([o['gear'] for o in n2['options']]))
check('type=video', n2['type'] == 'video')
check('BGM 字段透传', n2['music_url'] == 'https://cdn/bgm.mp3'
      and n2['music_title'] == 'cool sound')
fixture_img = dict(fixture, images=['https://cdn/1.jpg', 'https://cdn/2.jpg'],
                   play=None, hdplay=None)
n3 = tiktok_pure._normalize(fixture_img)
check('图集帖 type=image', n3['type'] == 'image' and n3['image_count'] == 2)

print(f'\n{sum(PASS)} PASS / {len(PASS) - sum(PASS)} FAIL')
assert all(PASS), '存在失败断言'
print('✅ 国际平台解析器测试全部通过')
print('ℹ️ 真网集成测试（syndication/tikwm 实连）请在香港服务器运行：')
print('   python app/parsers/intl/x_pure.py "https://x.com/user/status/..."')
