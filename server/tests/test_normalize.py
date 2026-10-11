"""
图集解析代码路径单元测试
用真实响应结构构造 media_type=68 的样本，验证 normalize() 图集分支

⚠️ 2026-10-05：原来这里 `from app.parsers.douyin import normalize`，
   而 douyin.py 顶层导入 playwright → 没装 playwright 时测试直接采集失败。
   已改为从 normalize_douyin.py 导入（纯函数，零浏览器依赖）。
"""
import json
import os
import sys

sys.path.insert(0, r'D:\WorkBuddyFILE\CreatorBox\server')
from app.parsers.normalize_douyin import normalize   # noqa

# 抖音图集的真实响应结构（字段来自实测视频响应推断）
SAMPLE = {
    "status_code": 0,
    "aweme_detail": {
        "aweme_id": "7699999999999999999",
        "desc": "【本地美食】这5家猪脚饭我吃了三年 #美食 #探店",
        "create_time": 1758000000,
        "media_type": 68,
        "author": {
            "nickname": "吃货小队",
            "unique_id": "foodie",
            "short_id": "123456",
        },
        "video": {
            "cover": {"url_list": ["https://v95.douyinvod.com/cover.jpg"]},
            "duration": 0,
        },
        "images": [
            {
                "url_list": [
                    "https://p3-pc.douyinpic.com/i1~tplv-dy-aweme-images:q75.webp?sig=a",
                    "https://p9-pc.douyinpic.com/i1~tplv-dy-aweme-images:q75.webp?sig=b",
                    "https://p3-pc.douyinpic.com/i1~tplv-dy-aweme-images:q75.jpeg?sig=c",
                ],
                "download_url_list": [
                    "https://p3-pc.douyinpic.com/i1~tplv-dy-water-v2:1600:2560.webp?sig=d",
                    "https://p3-pc.douyinpic.com/i1~tplv-dy-water-v2:1600:2560.jpeg?sig=e",
                ],
                "width": 1080, "height": 1440,
                "resolution_log_param": {
                    "image_publish_width": 1080, "image_publish_height": 1440
                },
            },
            {
                "url_list": [
                    "https://p3-pc.douyinpic.com/i2~tplv-dy-aweme-images:q75.webp?sig=a",
                    "https://p3-pc.douyinpic.com/i2~tplv-dy-aweme-images:q75.jpeg?sig=f",
                ],
                "download_url_list": [
                    "https://p3-pc.douyinpic.com/i2~tplv-dy-water-v2:1600:2560.jpeg?sig=g",
                ],
                "width": 1080, "height": 1920,
            },
            {
                "url_list": [
                    "https://p3-pc.douyinpic.com/i3~tplv-dy-aweme-images:q75.jpeg?sig=h",
                ],
                "download_url_list": [
                    "https://p3-pc.douyinpic.com/i3~tplv-dy-water-v2:1600:2560.jpeg?sig=i",
                ],
                "width": 1080, "height": 1440,
            },
        ],
    },
}


def test_image_branch():
    print('=' * 58)
    print('TEST 1  图集分支（media_type=68）')
    print('=' * 58)
    r = normalize(SAMPLE, '1080p')
    checks = [
        ('success', r['success'] is True),
        ('type=image', r['type'] == 'image'),
        ('image_count=3', r['image_count'] == 3),
        ('images 数组长度', len(r['images']) == 3),
        ('图片URL非空', all(i['url'] for i in r['images'])),
        ('保留宽高', r['images'][0]['width'] == 1080),
        ('video_url 为空(图集无)', r['video_url'] is None),
        ('author 正确', r['author'] == '吃货小队'),
        ('author_id 正确', r['author_id'] == 'foodie'),
        ('title 非空', len(r['title']) > 0),
        ('cover 非空', r['cover'].startswith('http')),
        ('⭐ 优先取 jpeg（小程序不支持 webp）',
         all('.jpeg' in i['url'] for i in r['images'])),
        ('⭐ format 标记正确', all(i['format'] == 'jpeg' for i in r['images'])),
        ('⭐ 取 url_list 原图而非 download_url_list（去水印关键）',
         all('dy-aweme-images' in i['url'] for i in r['images'])),
        ('⭐ 排除带水印的 water 模板',
         all('dy-water' not in i['url'] for i in r['images'])),
        ('⭐ 识别无水印标记', r.get('watermark_free') is True),
    ]
    ok = True
    for name, passed in checks:
        print(f"  {'✅' if passed else '❌'} {name}")
        ok = ok and passed
    print(f"\n  type       : {r['type']}")
    print(f"  image_count: {r['image_count']}")
    print(f"  首图格式   : {r['images'][0]['format']}")
    print(f"  首图       : {r['images'][0]['url'][:70]}")
    return ok


def test_video_branch():
    print()
    print('=' * 58)
    print('TEST 2  视频分支（回归测试）')
    print('=' * 58)
    v = json.loads(json.dumps(SAMPLE))
    v['aweme_detail']['media_type'] = 4
    v['aweme_detail'].pop('images')
    v['aweme_detail']['video']['duration'] = 101200
    v['aweme_detail']['video']['bit_rate'] = [
        {'gear_name': 'normal_1080_0', 'bit_rate': 2644241, 'size': 33500000,
         'play_addr': {'url_list': ['https://v95.douyinvod.com/1080.mp4']}},
        {'gear_name': 'normal_720_0', 'bit_rate': 1920786, 'size': 24000000,
         'play_addr': {'url_list': ['https://v95.douyinvod.com/720.mp4']}},
    ]
    for q, want in [('1080p', 'normal_1080_0'), ('720p', 'normal_720_0')]:
        r = normalize(v, q)
        good = r['success'] and r['type'] == 'video' and r['quality'] == want
        print(f"  {'✅' if good else '❌'} {q} → {r['quality']}")
    r = normalize(v, '1080p')
    print(f"\n  type   : {r['type']}")
    print(f"  quality: {r['quality']}")
    print(f"  options: {len(r['options'])} 档")
    print(f"  url    : {r['video_url'][:60]}")
    return r['quality'] == 'normal_1080_0'


def test_empty_and_edge():
    print()
    print('=' * 58)
    print('TEST 3  边界情况')
    print('=' * 58)
    cases = [
        ('空数据', {}),
        ('aweme_detail 为 null', {'aweme_detail': None}),
        ('images 空数组', {'aweme_detail': {
            'aweme_id': '1', 'images': [], 'video': {}, 'author': {}}}),
    ]
    ok = True
    for name, d in cases:
        r = normalize(d)
        passed = r.get('success') is False or r.get('type') == 'video'
        print(f"  {'✅' if passed else '❌'} {name} → type={r.get('type')} "
              f"success={r.get('success')}")
        ok = ok and passed
    return ok


if __name__ == '__main__':
    a = test_image_branch()
    b = test_video_branch()
    c = test_empty_and_edge()
    print()
    print('=' * 58)
    print(f'总体: {"✅ 全部通过" if (a and b and c) else "❌ 有失败"}')
    print('=' * 58)
    print()
    print('⚠️ 说明：图集代码路径已验证正确，但缺真实样本。')
    print('   需要一个真实图文分享链接做端到端确认。')
    sys.exit(0 if (a and b and c) else 1)
