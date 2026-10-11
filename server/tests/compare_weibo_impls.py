"""微博实现对比：4 个开源项目 vs 我们的实现

用途：P9「多项目对比要找实现差异」—— 差异点= 别人踩过的坑。
本脚本把 3 个项目的微博实现要点与我们的实测结论并排列出。

结论摘要（实测）：
| 维度 | parse-video-py | parse-video(Go) | m3u8-dl | 我们 |
|---|---|---|---|---|
| 接口域名 | h5.video.weibo.com | h5.video.weibo.com | **weibo.com/tv** | h5.video.weibo.com |
| 是否需 cookie | ❌ 不需要 | ⚠️ 硬编码一份 | **强制要求** | ❌ 不需要 |
| 封面字段 | cover_image | cover_image | cover_image | cover_image（本轮修正）|
| 档位选取 | urls 第一条 | urls 第一条 | 第一条 | **按 label 解析高度排序** |
| 图集降级 | m.weibo.cn → $render_data | 同左 | ❌ 未实现 | m.weibo.cn |
| 额外能力 | — | — | music | 文案/横竖屏/播放量/认证 |
"""
import re

# ---------- 各项目实现要点（源码摘录） ----------
IMPLS = {
    'parse-video-py (MIT)': {
        'file': 'src/parse_video_py/parser/weibo.py',
        'api': 'https://h5.video.weibo.com/api/component?page=/show/{id}',
        'method': 'POST',
        'body': 'data={"Component_Play_Playinfo":{"oid":"{id}"}}',
        'ua': 'fake_useragent iOS 随机',
        'cookie': '❌ 不需要',
        'video_field': 'stream_url 回退 → urls 第一条',
        'cover': 'data["cover_image"]（"https:" + 前缀）',
        'author': 'data["user"]["id"] / data["author"] / data["avatar"]',
        'gallery': 'm.weibo.cn/statuses/show → 失败降级 $render_data 正则',
        'pick': ['large', 'original', 'bmiddle', 'url'],
    },
    'parse-video (Go, MIT)': {
        'file': 'parser/weibo.go',
        'api': 'https://h5.video.weibo.com/api/component?page=/show/{id}',
        'method': 'POST',
        'body': 'data={"Component_Play_Playinfo":{"oid":"{id}"}}',
        'ua': 'DefaultUserAgent（Chrome）',
        'cookie': '⚠️ **硬编码一整串**含SUB/SUBP/XSRF-TOKEN',
        'video_field': 'urls 第一条（无 stream_url 回退）',
        'cover': 'data["cover_image"]',
        'author': 'data["author"] / data["avatar"]（无 uid）',
        'gallery': '同 Python 版',
        'pick': ['large', 'original', 'bmiddle', 'url'],
    },
    'm3u8-dl (MIT)': {
        'file': 'src/video-parser/parsers/weibo-parser.ts',
        'api': 'https://weibo.com/tv/api/component'
               '?page={encodeURIComponent("/tv/show/{id}")}',
        'method': 'POST',
        'body': 'data={"Component_Play_Playinfo":{"oid":"{id}"}}',
        'ua': '调用方传入',
        'cookie': '❗ **强制要求**（无 cookie 直接返回 400）',
        'video_field': 'urls 第一条',
        'cover': 'item.cover_image',
        'author': 'item.author_id / item.avatar',
        'gallery': '❌ 未实现',
        'extra': 'music.author / music.cover_large',
        'id_re': '/\\d+:\\d+/',
    },
    '我们 (自研)': {
        'file': 'server/app/parsers/weibo_pure.py',
        'api': 'h5.video.weibo.com（实测匿名可用，无需 cookie）',
        'method': 'POST',
        'body': '同开源',
        'ua': '固定 PC Chrome（不用随机 UA，便于复现）',
        'cookie': '❌ 不需要（实测）',
        'video_field': '按 label 解析高度 → 排序 → 取最高（不用下标）',
        'cover': 'cover_image（本轮修正，曾绕道第二接口取）',
        'author': 'author_id / author / avatar / verified_reason',
        'gallery': 'm.weibo.cn/statuses/show → pics[]（large→original→bmiddle→url→mw2000）',
        'extra': '文案 content2、横竖屏、播放量、粉丝数、认证信息',
    },
}

# ---------- 实测结论（2026-10-05） ----------
MEASURED = [
    ('h5.video.weibo.com 匿名可用',
     'HTTP 200 / 2615 字节 / code=100000，无需任何 cookie'),
    ('weibo.com/tv/api/component 无 cookie → 302',
     '跳 passport.weibo.com/visitor/visitor（访客系统）→ 拿不到数据'),
    ('weibo.com/tv 带 cookie 可用',
     '用Go 版硬编码的那串 cookie → 200 / 2616 字节，'
     '与 h5 域名返回大小几乎一致（数据等价）'),
    ('cover_image 与 page_pic 是同一张图',
     '两者 URL 都是 .../orj480/8dfbeab2gy1ih3mp8r6shj20ty1cgn1j.jpg，'
     '下载均56268 字节 → 我之前绕道第二接口取封面是多余的'),
    ('like_count 字段不存在',
     'm3u8-dl 用 item.like_count → 实测 None。'
     '真实字段是 attitudes_count（点赞）'),
    ('music 字段不存在',
     'm3u8-dl 用 item.music?.author → 实测 None（该视频无音乐信息）'),
    ('Go 版硬编码 cookie 已过期',
     '含 SUB/SUBP/APACHE 时间戳 1625663522（2021-07），'
     '如今 SUBP 早已轮换 → 这份cookie 大概率失效'),
    ('开源测试样本仍有效',
     '1034:4808181919187090（2022 年视频）实测 code=100000，'
     '我们解析器可跑通：2 档 / 2.4MB / 竖屏 / 逗拍模板视频'),
]

if __name__ == '__main__':
    W = 78
    print('=' * W)
    print('微博实现对比：3 个开源项目 vs 我们')
    print('=' * W)

    for name, d in IMPLS.items():
        print(f'\n【{name}】')
        print(f'  文件: {d["file"]}')
        print(f'  接口: {d["api"]}')
        print(f'  Cookie: {d["cookie"]}')
        print(f'  取视频: {d["video_field"]}')
        print(f'  封面  : {d["cover"]}')
        if d.get('gallery'):
            print(f'  图集  : {d["gallery"]}')
        if d.get('extra'):
            print(f'  额外  : {d["extra"]}')

    print('\n' + '=' * W)
    print('实测结论（2026-10-05）')
    print('=' * W)
    for k, v in MEASURED:
        print(f'\n▸ {k}')
        for i in range(0, len(v), W - 6):
            print('   ', v[i:i + W - 6])

    print('\n' + '=' * W)
    print('ID 正则对比（m3u8-dl vs 我们）')
    print('=' * W)
    theirs = re.compile(r'\d+:\d+')
    ours = re.compile(r'\b(\d{3,6}):(\d{9,})\b')
    for u in ('https://weibo.com/tv/show/1034:5343195622473745?mid=5343',
              'https://video.weibo.com/show?fid=1034:5343195622473745',
              'https://weibo.com/2543858012/Q9pcJ4S21（图集帖）'):
        a = theirs.search(u)
        b = ours.search(u)
        print(f'  {u[:48]:50s}')
        print(f'      m3u8-dl: {a.group(0) if a else "未匹配"}')
        print(f'      我们    : {b.group(0) if b else "未匹配（走图集分支）"}')

    print('\n' + '=' * W)
    print('结论')
    print('=' * W)
    print("""
1. **两个域名等价，但门槛不同**
   h5.video.weibo.com 匿名可用 → 我们用它，无需 cookie
   weibo.com/tv       强制要 cookie（访客系统 302）→ m3u8-dl 因此要求 cookie
   → 选h5 域名是对的，匿名用户的体验好得多

2. **Go 版的硬编码 cookie 是历史包袱**
   含 2021 年的时间戳，SUBP 早已轮换，现在大概率失效
   → 印证 P9：实现差异暴露的是「作者当时遇到了什么」
     他遇到的是「需要登录态」，我们遇到的是「不需要」

3. **两处字段是开源代码写错/写旧的**
   like_count → 真实是 attitudes_count
   music→ 该视频无此字段（可选，不算错）
   → 又一次印证 P1：字段不能靠猜，要下载实测

4. **我本轮犯了个可避免的错误**
   以为「component 不给封面」，绕道第二个接口取 page_pic.url
   实际上 cover_image 就在第一个接口里，且与 page_pic 是同一张图
   → 已修正，少一次 HTTP 请求

5. **两处我们比开源项目做得更好**
   - 档位按 label 解析高度排序，不用「第一条」的下标假设（见 P17）
   - 补了文案、横竖屏、播放量、认证信息 —— 开源项目都只返回标题
""")
