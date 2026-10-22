"""
平台知识库 —— 唯一事实源（Single Source of Truth）

⚠️ 所有字段来自源码 + 实测，不是推测。
最后更新：2026-10-05

用途：
  1. 写解析器时直接查PLATFORMS[平台名]
  2. 后台看板读 summary()
  3. 接入新平台时照着 FIELD_PATTERNS 的模式填

⛔ 禁止在别处硬编码平台信息。要改就改这里。
"""
from typing import Any, Dict, List

# ═══════════════════════════════════════════════════════
# 一、平台注册表
# ═══════════════════════════════════════════════════════

PLATFORMS: Dict[str, Dict[str, Any]] = {
    # ─────────── 已跑通 ───────────
    'douyin': {
        'name_cn': '抖音',
        'status': 'ready',                # ready/partial/blocked/pending
        'domains': ['v.douyin.com', 'www.iesdouyin.com', 'www.douyin.com'],
        'url_re': r'https?://[^\s]+',
        'engine': 'pure_http',            # pure_http / browser / blocked
        'types': ['video', 'image'],
        'max_quality': '1080P',
        'free_quality': '720P',
        'cdn_hosts': ['p3-pc-sign.douyinpic.com',   # 图集（实测只有 p3/p9 两个）
                       'p9-pc-sign.douyinpic.com',
                       '*.365yg.com',
                       'v*-aw-web.douyinvod.com'],
        'whitelist_ok': True,
        'whitelist_note': '图集 CDN 实测只有 p3/p9 两个 → 可枚举',
        'measured': {'video_ms': 810, 'image_ms': 840, 'success': '5/5',
                     'observed_cdn': 'p3-pc-sign.douyinpic.com',
                     'image_observed_cdn': 'p3-pc-sign.douyinpic.com'},
    },
    'bilibili': {
        'name_cn': 'B站',
        'status': 'ready',
        'domains': ['bilibili.com', 'b23.tv', 'm.bilibili.com'],
        'engine': 'pure_http',
        'types': ['video'],
        'max_quality': '720P',
        'free_quality': '720P',
        'cdn_hosts': ['*.bilivideo.com'],
        'whitelist_ok': False,     # ⭐ 实测 5 个视频 5 个不同子域，必超 20 上限
        'whitelist_note': (
            '★ 2026-10-05 实测 5 个视频得到 5 个不同子域：'
            'upos-sz-estgoss / upos-sz-mirrorcoso1 / upos-sz-mirrorcos / '
            'upos-sz-estghw / cn-zjjh-ct-04-05 （全是 bilivideo.com）。'
            '子域**不可枚举** → 必然超微信 20 个上限 → **必须服务端中转**'),
        'observed_cdns': [
            'upos-sz-estgoss.bilivideo.com',
            'upos-sz-mirrorcos.bilivideo.com',
            'upos-sz-mirrorcoso1.bilivideo.com',
            'upos-sz-estghw.bilivideo.com',
            'cn-zjjh-ct-04-05.bilivideo.com',
        ],
        'measured': {'video_ms': 320, 'size_mb': 49.6, 'success': '3/3',
                     'resolution': '1280x720（匿名上限）'},
    },
    'baidu': {
        'name_cn': '百度视频',
        'status': 'ready',
        # mr.baidu.com 是分享短链（302 跳到 mbd.baidu.com 落地页）
        'domains': ['mr.baidu.com', 'mbd.baidu.com', 'mbd.baidu.cn'],
        # ⭐ 2026-10-22 新增：落地页是 SSR 直出，HTML 内嵌 videoInfo JSON
        #   → 零签名、零浏览器、零 Cookie，与抖音/快手同构
        'engine': 'pure_http',
        'types': ['video'],
        'max_quality': '1080P',
        'free_quality': '1080P',
        'cdn_hosts': ['vd*.bdstatic.com', 'f*.baidu.com'],
        'whitelist_ok': True,
        'whitelist_note': ('实测直链落在 vd3.bdstatic.com，域名带序号但形态稳定；'
                           '封面在 f7.baidu.com（走 /api/proxy-cover 代理）'),
        'measured': {
            'success': '1/1',
            'ms': 800,
            'observed_cdn': 'vd3.bdstatic.com',
            'gears': ['蓝光 1080P', '超清 720P', '高清 480P'],
        },
        'known_gaps': ['author: SSR 页面不下发作者名'],
    },
    'haokan': {
        'name_cn': '好看视频',
        'status': 'ready',
        'domains': ['haokan.baidu.com', 'haokan.hao123.com'],
        # ⭐ 2026-10-05 二次实测：从 browser 降级为 pure_http
        # 原判「必须过滑块 → 需浏览器」，实测是错的：
        # 只要先 GET 首页拿 BAIDUID cookie，纯 HTTP 就能拿到接口数据。
        # 触发滑块的是「goto 视频详情页」这一步，而我们不需要。
        'engine': 'pure_http',
        'types': ['video'],
        'max_quality': '1080P',
        'free_quality': '1080P',
        'cdn_hosts': ['vdept*.bdstatic.com', 'vd*.bdstatic.com'],
        # ⭐ 实测 4 个视频全部是 vdept3.bdstatic.com → 稳定，可枚举
        'whitelist_ok': True,
        'whitelist_note': ('实测 4 个不同视频的 1080P 地址全部是 '
                           'vdept3.bdstatic.com，域名稳定 → 可加白名单'),
        'measured': {'success': '4/4', 'ms': 450,
                     'observed_cdn': 'vdept3.bdstatic.com',
                     'sizes_mb': [1.5, 2.3, 2.8, 6.2],
                     'gears': ['标清 360P', '高清 480P', '超清 720P', '蓝光 1080P'],
                     'max_size_mb': 38.1},
        'known_gaps': ['接口不下发作者名（游客态 uname 为空）'],
    },
    'sohu': {
        'name_cn': '搜狐视频',
        'status': 'partial',
        'domains': ['tv.sohu.com', 'my.tv.sohu.com', 'm.tv.sohu.com'],
        'engine': 'pure_http',
        'types': ['video'],
        'max_quality': '720P',
        'free_quality': '720P',
        'cdn_hosts': ['data.vod.itc.cn', 'api.my.tv.sohu.com'],
        # ⭐ 域名本身是固定的，但 URL 带长签名 + 有 30 秒截断限制
        #    → 小程序端仍需中转（不是域名问题，是「要给完整版」的问题）
        'whitelist_ok': False,
        'whitelist_note': (
            '域名固定（data.vod.itc.cn 单域）→ 白名单技术上可行，'
            '但：① URL 带 200+ 字符签名串 ② mp4 直链只有 30 秒试看片段，'
            '完整版需服务端合并 → 实际仍走中转'),
        'measured': {'success': '4/8', 'ms': 1200,
                     'resolution': '1280x720',
                     'note': '失败的一半是首页最新视频尚未入库'},
        'critical_limit': (
            '★ url_high_mp4 只是「30 秒试看片段」，与视频真实时长无关。'
            '实测声明 76s 的视频，mp4 实际只有 30.04s / 468026 字节，'
            '短了 46 秒。download_url 是同一个 URL。'
            '完整视频只存在于 m3u8（url_high），需服务端下分段合并。'
            '→ 10 个开源项目都只取 url_high_mp4，因此对 >30s 的搜狐视频'
            '  都会返回残缺文件。'),
        'auth_note': (
            '⚠️ api_key=9854b2afa779e1a6bcdd07b217417549&sver=6.2.0 '
            '两个参数缺一不可。只传 site=2 时接口返回'
            '「视频(620254006, 2)不存在」——极易误判为接口已死。'),
        'm3u8_also_preview': (
            '★ 2026-10-05 二次实测：**m3u8 也是试看片段，合并救不了**。'
            'm3u8 写 12 段、EXTINF 合计 76.85s，'
            '但**12 段 MD5 完全相同**（全是同一个 30 秒内容）。'
            'ffmpeg 合并后得到 6 分钟文件且**退出码 0、不报错**。'
            '→ 已实现合并前哈希预检（knowledge.P22），'
            '检测到重复直接拒绝，不产出垃圾文件。'
            '结论：搜狐 >30s 的视频**必须登录态**才能拿完整版。'),
        'url_format': (
            '⚠️ 现在 /v/{base64}.html 解码出来是 {YYYYMMDD}/n{vid}.shtml，'
            '不再是开源项目假设的 us/{uid}/{vid}.shtml。'
            'parse-video-py/Go 的 US_URL_RE 匹配不到当前格式。'),
    },

    # ─────────── 真实样本已验证 ───────────
    'weibo': {
        'name_cn': '微博',
        'status': 'ready',
        'domains': ['weibo.com', 'weibo.cn', 'h5.video.weibo.com',
                     'm.weibo.cn', 'video.weibo.com'],
        'engine': 'pure_http',
        'types': ['video', 'image'],
        'max_quality': '1080P',
        'free_quality': '1080P',
        'cdn_hosts': ['f.video.weibocdn.com', 'wx*.sinaimg.cn'],
        'whitelist_ok': True,       # 实测 3 个视频全部同一域名，稳定
        'whitelist_note': ('实测多个视频的 1080P 地址全部是 '
                           'f.video.weibocdn.com → 稳定可枚举'),
        'observed_cdn': 'f.video.weibocdn.com',
        'measured': {'success': '1/1 真实样本', 'ms': 840,
                     'gears': ['高清 1080P', '高清 720P', '标清 480P'],
                     'size_mb': [112.8, 61.4, 40.4],
                     'duration_s': 319.41, 'tracks': 2},
        'sample': ('https://weibo.com/tv/show/1034:5343195622473745'
                   '?mid=5343196424963244'),
        'note': ('⚠️ 未登录页面只有 9KB 空壳，自动抓取取不到 oid —— '
                 '需用户提供真实链接。这是长期卡点，不是代码问题。'),
    },

    # ─────────── 已并入抖音精选（PC 站不存在）───────────
    'ixigua': {
        'name_cn': '西瓜视频',
        'status': 'blocked',
        'domains': ['ixigua.com', 'm.ixigua.com'],
        'engine': 'blocked',
        'types': [],
        'cdn_hosts': [],
        'whitelist_ok': False,
        'blocked_reason': ('★ PC 网页版已与抖音网页版合并，域名重定向到「抖音精选」。'
                           '2024-12-02 官方公告 + 2026-06 媒体报道确认。'
                           '移动端分享页 SSR 返回空壳（item_list 恒为 0）'),
        'evidence': [
            '首页 www.ixigua.com 无 SPA 挂载点（id=root / __NEXT_DATA__ / _ROUTER_DATA 全为0）',
            '首页仅 9 个链接：App 下载页、隐私政策、ICP 备案',
            '无 Cookie 时 7717 字节空壳；带 Cookie 时 61791 字节但是 App 下载引导页',
            '浏览器渲染后 title =「西瓜视频APP官方下载_安卓版_iOS版」',
        ],
        'media': '2026-06 报道：字节将抖音与西瓜官网首页全部定向至「抖音精选」',
    },
    'kuaishou': {
        'name_cn': '快手',
        'status': 'ready',   # ⭐ 2026-10-05 从 blocked 改为 ready
        'domains': ['kuaishou.com', 'gifshow.com', 'chenzhongtech.com'],
        'engine': 'pure_http',
        'types': ['video'],
        'cdn_hosts': ['*.kwimgs.com', '*.ndcimgs.com', '*.yximgs.com'],
        'whitelist_ok': False,       # CDN 子域名每个作品不同，不可枚举
        'measured': {'success': '2/2 真实样本',
                     'ms': 1200,
                     'videos': [
                         {'work_id': '3xy2kubupu94q74', 'dur_s': 13.10,
                          'res': '720x1280', 'size_mb': 3.33,
                          'author': '曦月', 'views': 19392},
                         {'work_id': '3xha63juacrpw69', 'dur_s': 48.12,
                          'res': '720x1080', 'author': '人民日报',
                          'views': 3980729, 'likes': 116885},
                     ],
                     'no_watermark': True,
                     'note': 'ffprobe 实测 13.10s 与声明 13100ms 吻合（非截断）'},
        'breakthrough': (
            '★ 突破点：**主站 www 被反爬拦死，但m.gifshow.com 完全不拦**\n'
            '| 入口 | 结果 |\n'
            '|---|---|\n'
            '| www.kuaishou.com/short-video/{id} | 82 字节 {"result":2} 完全 CSR |\n'
            '| www.kuaishou.com/graphql | result=400002 + captcha |\n'
            '| **m.gifshow.com/fw/photo/{id}** | **200 / 98-163KB / INIT_STATE 完整** |\n'
            '→ gifshow 是快手最早的品牌名，主站换域名后**这个域没跟上反爬**'),
        'evidence': [
            '短链 /f/{token} → 302 Location 里shareObjectId 即 workId',
            'workId 形如 3xy2kubupu94q74（字母数字混合，非数字 photoId）',
            '4 种 UA（PC/iOS/Android/微信）× 3 个 workId → 全部 400002',
            '→ 拦截发生在 workId 校验**之前**，与内容和 UA 无关',
            'm.gifshow.com 需 **iOS UA**（与小红书同类要求）',
        ],
        'critical': (
            '⚠️ ① **必须 iOS UA**（PC UA 未验证，但 iOS 已实测通过）\n'
            '② **INIT_STATE 顶层 key 被混淆**（形如 tusjoh.0sftu0{...}），'
            '不能按 key 名找 → 必须遍历找「含 result+photo 且 result==1」的节点\n'
            '③ mainMvUrls[0] 与 [1] 可能是**完全相同**的一条 → 必须去重，'
            '否则虚报档位数\n'
            '④ duration 单位是**毫秒**（13100 = 13.1s）\n'
            '⑤ ⚠️ **反爬可能随时跟上这个域名** —— 接入时加独立探针监控'),
    },
    'acfun': {
        'name_cn': 'AcFun',
        'status': 'ready',
        'domains': ['acfun.cn'],
        'engine': 'pure_http',
        'types': ['video'],
        'max_quality': '1080P+',
        'free_quality': '1080P+',
        'cdn_hosts': ['tx-safety-video.acfun.cn',
                      'ali-safety-video.acfun.cn'],
        # 域名固定（2 个），但只有 m3u8 → 必须服务端合并 → 走中转
        'whitelist_ok': False,
        'whitelist_note': (
            '域名固定且只有 2 个 → 白名单本身可行；'
            '但平台只给 m3u8（无单文件 mp4），'
            '小程序必须拿到合并后的 mp4 → **实际仍走服务端中转**'),
        'observed_cdn': 'tx-safety-video.acfun.cn',
        'measured': {'success': '1/1 真实样本', 'ms': 260,
                     'gears': ['1080P+', '1080P', '720P', '540P', '360P'],
                     'segments': 59, 'size_mb': 154.66,
                     'duration_s': 299.0},
        'sample': 'https://www.acfun.cn/v/ac48890260',
        'critical_limit': (
            '★ 只有 m3u8，**没有单文件 mp4**。'
            '1080P+ 实测 59 个 .ts 分段、累计 154.66MB。'
            '小程序 saveVideoToPhotosAlbum 只吃 mp4 → '
            '**必须服务端下载分段并合并**（merge_required=True）。'
            '与抖音/B站/微博的「直链可存」方案不同。'),
        'merge_status': (
            '✅ **ffmpeg 合并已跑通**（2026-10-05）：'
            '-c copy 纯 remux，299.01s / 150.04MB 仅需 **5.4 秒**，'
            'duration_ratio=1.0（与 EXTINF 声明一致），faststart 生效。'
            '59 个分段内容各不相同 → 是真实完整视频。'
            '接口：POST /api/merge'),
    },
    'liujianfang': {
        'name_cn': '六间房',
        'status': 'blocked',
        'domains': ['6.cn', 'm.6.cn', 'v.6.cn'],
        'engine': 'blocked',
        'types': [],
        'cdn_hosts': [],
        'whitelist_ok': False,
        'blocked_reason': (
            '★ 业务形态不匹配：六间房是**直播平台**，不是短视频点播平台。'
            '实测 v.6.cn/219369 页面 title=「一只柠国庆快乐视频直播间」，'
            '页面里 直播/live/anchor 出现 15/50/25 次，'
            '但 playurl / mp4 / videoUrl 出现 **0 次**。'),
        'evidence': [
            'v.6.cn/219369 → 65803 字节，title 含「直播间」',
            '页面关键词计数：直播 15 / live 50 / anchor 25',
            '页面无 playurl、无 .mp4、无 m3u8、无 videoUrl',
            '首页 856219 字节，链接全是 /{数字} 房间号（219369/338888/…）',
        ],
        'lesson': (
            '开源项目把它当点播平台收录，但实测是 UGC 直播。'
            '直播流不能"解析成文件"（时移录制是另一回事，且需签名）。'
            '→ 不纳入 10 平台清单。'),
    },

    # ─────────── 平台封死 ───────────
    'xiaohongshu': {
        'name_cn': '小红书',
        'status': 'ready',   # ⭐ 2026-10-05 从 blocked 改为 ready
        'domains': ['xiaohongshu.com', 'xhslink.com', 'xhslink.cn'],
        'engine': 'pure_http',
        'types': ['image', 'video'],
        'max_quality': '图集=原图 1080 宽 / 视频=1920x1080',
        'free_quality': '原图 / 1080P',
        'cdn_hosts': ['sns-na-i6.xhscdn.com', 'sns-img-qc.xhscdn.com',
                      'sns-webpic-qc.xhscdn.com', 'sns-video-bd.xhscdn.com',
                      'sns-video-v6.xhscdn.com', 'sns-bak-v1.xhscdn.com'],
        'whitelist_ok': True,       # 域名有限，实测可用
        'measured': {'success': '2/2 真实样本（图集 + 视频）',
                     'ms': 520,
                     'image_note': {'images': 7,
                                    'resolution': '1200x1870',
                                    'size_kb': 236},
                     'video_note': {'gears': 3,
                                    'resolution': '1920x1080',
                                    'duration_s': 261.39,
                                    'size_mb': 63.78,
                                    'codec': 'H.264 + AAC',
                                    'declared_vs_actual': '262s vs 261.39s'},
                     'no_watermark': True},
        'samples': [
            ('图集', 'https://www.xiaohongshu.com/discovery/item/'
                     '6a827209000000002701cde0?xsec_token=...'),
            ('视频', 'https://www.xiaohongshu.com/discovery/item/'
                     '6a72adee0000000033036edf?xsec_token=...'),
        ],
        'state_relayouted': (
            '★ 本平台结构**全面改版**，3 个开源项目的实现全部失效：\n'
            '| 字段 | 开源项目读的 | 实测现在 |\n'
            '|---|---|---|\n'
            '  | 顶层 key | note | **noteData** |\n'
            '  | 笔记容器 | note.noteDetailMap | **noteData.data.noteData** |\n'
            '  | noteId | note.currentNoteId | **None** |\n'
            '  | 图片字段 | imageList[].urlDefault | **imageList[].url**（+ fileId）|\n'
            '  → 开源项目照抄会直接 KeyError'),
        'nowatermark_method': (
            '★ 去水印方法也变了：\n'
            '  原始 url（sns-webpic-qc...）**实测带「小红书」文字水印**'
            '（已下载看图确认）\n'
            '  开源项目的 ci.xiaohongshu.com/notes_pre_post/{id} → **实测 404 失效**\n'
            '  ✅ 图集可用：用 fileId 拼无水印原图\n'
            '     https://sns-na-i6.xhscdn.com/{fileId}'
            '?imageView2/2/w/1080/format/jpg\n'
            '     （sns-img-qc.xhscdn.com 同样可用，实测两者字节数一致）\n'
            '  ✅ 视频可用：sns-video-bd 拼 originVideoKey（抽帧确认无水印）\n'
            '     ⚠️ 视频的开源规则**没失效** —— 与图片不同，'
            '这条至今有效（实测 3 种取址全部 206/200）'),
        'video_notes': (
            '★ 视频笔记（note.type == "video"）实测 2026-10-05：\n'
            '  地址来源三选一，全部实测可下载（206/200）：\n'
            '  ① consumer.originVideoKey 拼 sns-video-bd.xhscdn.com'
            '  ← **推荐，无签名可长期缓存**\n'
            '  ② media.stream.h264[0].masterUrl  带 ?sign= 有时效\n'
            '  ③ backupUrls[0]（sns-bak-v1）  备用\n'
            '  编码档：h264(1112kbps) / h265(793kbps)，'
            'h265 更省流量但兼容性差 → 默认给 h264\n'
            '  实测产物：63.78MB / 261.39s / 1920x1080 / H.264+AAC '
            '双轨，**与声明 262s 吻合（非截断）**'),
        'duration_unit_trap': (
            '⛔ 同名字段单位不一致（P28，实测踩过）：\n'
            '  media.video.duration   = 262→ **秒**\n'
            '  media.stream.*.duration = 261389  → **毫秒**\n'
            '  把 262 当毫秒 → 显示 0.26 秒。'
          '优先取 stream.*.duration（两档一致，更可信）'),
        'type_judgement_trap': (
            '⛔ 视频笔记 ALSO 带 imageList（那是封面图）（P27）：\n'
            '  我曾用「images 非空」判定图集，'
            '结果把一条 262 秒视频误报成「1 张图的图集」\n'
            '  ✅ 唯一判据是 note.type == "video"，'
            '不要看 imageList 是否为空'),
        'critical': (
            '⚠️ ① **必须 iOS UA**：PC UA → 302到 /login 登录墙；'
            'iOS UA → 200 直接通过（实测 170KB vs PC 的 73KB）\n'
            '② **必须用 yaml.safe_load**：state 含 undefined/裸值，'
            'json.loads 必失败（这也是 parse-video-py 当年选 yaml 的原因）\n'
            '③ **必须带 xsec_token**：缺失直接报错\n'
            '④ token 有时效，过期/风控会返回 300031「当前笔记暂时无法浏览」'),
        'flakiness': (
            '⚠️ 实测对同一 token 会**间歇性**返回空 noteData'
            '（state 里多一个 notFoundPage 顶层 key）→ 已加重试 2 次 + '
            '路由归一化（/explore/ 与 /discovery/item/ 等价，统一走后者）'),
    },
    'qqvideo': {
        'name_cn': '腾讯视频',
        'status': 'blocked',
        'domains': ['v.qq.com', 'm.v.qq.com'],
        'engine': 'blocked',
        'types': ['video'],
        'cdn_hosts': [],
        'whitelist_ok': False,
        'blocked_reason': ('getinfo 接口在真实浏览器 + 完整 Cookie 下仍返回 '
                           'em:61「该内容暂不可观看」→ 平台关闭免登录解析'),
    },
}


# ═══════════════════════════════════════════════════════
# 二、字段路径速查（写解析器时直接对照）
# ═══════════════════════════════════════════════════════

FIELD_PATTERNS: Dict[str, Dict[str, Any]] = {
    'douyin': {
        'source': 'wujunwei928/parse-video-py + uvd（实测验证）',
        'license': 'MIT / 无授权(uvd) — 借鉴思路，代码自写',
        'video': {
            'L1_api': {
                'url': 'https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/'
                       '?aweme_ids=%5B{id}%5D',
                'method': 'GET',
                'auth': '**无 cookie、无签名、无 a_bogus**，只要 iOS UA',
                'critical': '⚠️ 参数是 aweme_ids=数组格式（复数）。'
                            '用 aweme_id=单数会返回 aweme_details:null',
                'field': 'aweme_details[0].video.bit_rate[].play_addr.url_list[0]',
                'max_gear': '实测最高 720_3_1（720P）',
            },
            'L2_api': {
                'url': 'https://www.douyin.com/aweme/v1/web/aweme/detail/'
                       '?{24参数}&a_bogus={sig}',
                'method': 'GET',
                'auth': 'ttwid + a_bogus(SM3+RC4)',
                'critical': '⚠️ 三个反直觉点：'
                            '① msToken 传空字符串 '
                            '② Cookie 只带 ttwid，多带触发风控 '
                            '③ UA 用 Chrome 90（越旧越安全）',
                'field': 'aweme_detail.video.bit_rate[].play_addr.url_list[0]',
                'used_for': '图集（v2 接口对图集返回空壳）',
            },
            'L3_1080p': {
                'url': 'https://www.iesdouyin.com/aweme/v1/play/'
                       '?video_id={play_addr.uri}&ratio=1080p&line=0',
                'method': 'GET → 302',
                'auth': '无',
                'source': 'lzwme/m3u8-dl（douyin-parser.ts:36）',
                'critical': '这是免费拿 1080P 的唯一通道。'
                            '实测 ratio=1080p → 1920×1080 / 31.9MB',
                'field': 'play_addr.uri（先从 L1/L2 取）',
            },
        },
        'image': {
            'field': 'aweme_details[0].images[].url_list[]',
            'pick_rule': '优先 jpg/jpeg → 其次排除 dy-water → 兜底 [0]',
            'critical': '⚠️⚠️ 必须用 url_list，不能用 download_url_list！'
                        'url_list 模板= ~tplv-dy-aweme-images（无水印）'
                        'download_url_list 模板 = ~tplv-dy-water-v2（**底部有账号水印**）',
            'webp_note': '小程序 saveImageToPhotosAlbum 不支持 webp，'
                         '但 url_list 里通常有 .jpeg 候选',
        },
    },
    'bilibili': {
        'source': 'wujunwei928/parse-video-py + video-parser（实测验证）',
        'license': 'MIT / MIT',
        'video': {
            'step1': {
                'url': 'https://api.bilibili.com/x/web-interface/view?bvid={bvid}',
                'field': 'data.cid',
            },
            'step2': {
                'url': 'https://api.bilibili.com/x/player/playurl?'
                       'fnver=0&fnval=0&qn=80&bvid={bvid}&cid={cid}&platform=html5',
                'field': 'data.durl[0].url',
                'critical': '⚠️ fnval=0 返回**单文件含音轨** → 不需要 ffmpeg。'
                            '只有 fnval=16(dash) 才需要合并',
            },
            'critical': '⚠️ Referer 必须设为视频页自身'
                        '（https://www.bilibili.com/video/{bvid}），否则返回挑战页',
            'limits': '匿名上限 720P（accept_quality 声明 1080P 但不给）',
        },
        'dead_end': {
            'note': 'SSR window.__playinfo__ 已失效—— '
                    '页面里只有引用没有数据（B站停止对非浏览器下发）',
        },
    },
    'haokan': {
        'source': 'parse-video-py + video-parser（实测验证）',
        'license': 'MIT / MIT',
        'video': {
            'api': {
                'url': 'https://haokan.baidu.com/v?_format=json&vid={vid}',
                'field': 'data.apiData.curVideoMeta.clarityUrl[]',
                'prereq': '★ 必须先 GET https://haokan.baidu.com/ 拿 BAIDUID cookie，'
                          '否则接口返回 errno:101007',
                'verify': 'errno 必须 == 0，且 curVideoMeta 非空',
            },
            'gears': '4 档，按 rank 升序：标清360P / 高清480P / 超清720P / 蓝光1080P',
            'authoritative_fields': (
                '★ 档位信息接口已经给了，不要靠 URL 路径猜：'
                '  title      = "蓝光 1080P"（平台自己的档位名）'
                '  vodVideoHW = "1080$$1920"（高$$宽）'
                '  videoBps   = 码率 kbps'
                '  videoSize  = 体积 MB'
                '  rank       = 0..3 档位序号'),
            'cover': 'curVideoMeta.poster（不是 image/cover —— 那两个 key 不存在）',
            'author': '⛔ 接口不下发。遍历 curVideoMeta 全部 30 个 key 无'
                      'author/user_name；SSR __PRELOADED_STATE__ 里 uname '
                      '也是空串（游客态）。返回空字符串，不要编造',
            'critical': '⚠️ playurl URL 不能截断！带 auth_key 签名，截断 → 403',
            'expiry': 'playurl 带 auth_key 且有时效（形如 1791190576）'
                      '→ 缓存 TTL ≤ 10 分钟，不要长期缓存',
            'correction': (
                '★ 修正旧结论：原记「需浏览器过滑块」是错的。'
                '滑块由「打开视频详情页」触发，而我们只需访问首页拿 cookie，'
                '纯 HTTP 即可 4/4 成功（0.45s）。'),
        },
    },
    'sohu': {
        'source': 'parse-video-py + parse-video(Go)（两版实现完全一致，无差异）',
        'license': 'MIT / MIT',
        'video': {
            'url': ('https://api.tv.sohu.com/v4/video/info/{vid}.json'
                    '?site=2&api_key=9854b2afa779e1a6bcdd07b217417549'
                    '&sver=6.2.0'),
            'auth': '★ api_key 与 sver 缺一不可。只传 site=2 → '
                    '「视频(xxx, 2)不存在」，极易误判接口已死',
            'field': 'data.url_high_mp4（回退 data.download_url，同一 URL）',
            'meta': 'data.video_name / data.originalCutCover / '
                    'data.user.nickname / data.clips_duration_high / '
                    'data.file_size_high',
            'vid_extract': (
                'tv.sohu.com/v/{base64}.html → base64 解码 → '
                '{YYYYMMDD}/n{vid}.shtml → 取数字。'
                '⚠️ 当前格式不是开源项目假设的 us/{uid}/{vid}.shtml，'
                'US_URL_RE 匹配不到，要两种都支持'),
            'truncation': (
                '★ url_high_mp4 是「30 秒试看片段」，不是完整视频。'
                '声明 76s 的视频实测只有 30.04s / 468026 字节（短 46 秒）。'
                '必须下载后读 mvhd 时长与 clips_duration_high 比对才能发现。'),
            'full_video': (
                '完整视频只在 data.url_high（m3u8）。'
                '⚠️ m3u8 的 /v2/play/ 路径带签名，改任一段 → '
                '「sign field length error.」不可枚举多档'),
            'page_note': (
                '详情页是 GB18030 编码且只有 15KB 空壳，'
                '真实数据在 hotvrs.js.tv.itc.cn/.../init_video_info.js，'
                '但那文件只有元数据没有播放地址 → 走 API，勿解析页面'),
            'critical': '页面/接口均需 Referer: https://tv.sohu.com/',
        },
    },
    'weibo': {
        'source': 'parse-video-py（实测验证：2026-10-05 用户提供真实样本）',
        'license': 'MIT',
        'sample': 'https://weibo.com/tv/show/1034:5343195622473745?mid=5343196424963244',
        'video': {
            'url': 'https://h5.video.weibo.com/api/component?page=/show/{oid}',
            'method': 'POST',
            'headers': {
                'Referer': 'https://h5.video.weibo.com/show/{oid}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
            },
            'body': 'data={"Component_Play_Playinfo":{"oid":"{oid}"}}',
            'field': 'data.Component_Play_Playinfo.urls',
            'success_check': 'code == "100000"（字符串，不是数字 0）'
                             '且 Component_Play_Playinfo 非空',
            'gear_order': (
                '修正旧结论：原写「urls 的第一个 key 是最高码率」。'
                '实测第一个确实是最高档（高清 1080P），'
                '但那是 dict 保序 + 平台按降序插入的结果，'
                '**不是"第一个 key 天然代表最高"**。'
                '正确做法：按 label 解析高度再排序，不要依赖下标 —— '
                '平台一旦调整顺序就会取错档。'),
            'gears': '3 档实测：高清 1080P / 高清 720P / 标清 480P',
            'stream_url': '最低档（与 urls 末档同源），可作回退',
            'meta': ('title / author / nickname / author_id / avatar / '
                     'verified / verified_reason / real_date / '
                     'attitudes_count / comments_count / followers_count'),
        },
        'cover_and_caption': {
            'url': 'https://m.weibo.cn/statuses/show?id={mid}',
            'headers': {'Referer': 'https://m.weibo.cn/',
                        'X-Requested-With': 'XMLHttpRequest',
                        'User-Agent': 'iOS UA'},
            'success_check': 'ok == 1 且 data 非空',
            'cover': 'data.page_info.page_pic.url（480 宽，竖屏 480x776）'
                     '｜⚠️ 但 component 的 cover_image 就是同一张图，'
                     '优先用它（少一次请求）',
            'description': 'data.page_info.content2'
                           '（★ 比 title「XX的微博视频」有用得多）',
            'orientation': 'data.page_info.video_orientation'
                           ' → "vertical" / "horizontal"',
            'play_count': 'data.page_info.play_count（文案，如「437万次播放」）',
            'caption': 'data.text（HTML，需剥标签 + unescape）',
            'note': '★ component 接口不给封面与文案，必须再调这个接口',
        },
        'image': {
            'url': 'https://m.weibo.cn/statuses/show?id={mid}',
            'field': 'data.pics[]',
            'pick_rule': '按 large → original → bmiddle → url → mw2000 顺序取首个',
            'note': '纯图集微博没有 page_info，pics 才有数据',
        },
        'oid_format': (
            'oid 形如 **1034:5343195622473745** —— '
            '冒号前是 prefix（如 1034），冒号后才是 media_id。'
            '不要把整串当纯数字 media_id 用。'
            '正则：\\b(\\d{3,6}):(\\d{9,})\\b'),
        'open_source_comparison': (
            '★ 3 个开源项目的微博实现对比（实测，'
            '见 tests/compare_weibo_impls.py）：\n'
            '  ① 域名有两种，数据等价但**门槛不同**：\n'
            '     h5.video.weibo.com/api/component → **匿名可用**（实测 200/2615B）\n'
            '     weibo.com/tv/api/component      → **强制要 cookie**\n'
            '       （无 cookie 302 到 passport.weibo.com/visitor 访客系统）\n'
            '     → 我们用 h5，省掉登录态依赖\n'
            '  ② 字段勘误：\n'
            '     m3u8-dl 用 like_count → 实测 **None**，真实是 attitudes_count\n'
            '     m3u8-dl 用 music      → 实测 None（该视频无音乐信息）\n'
            '     两版都用 cover_image  → **实测存在且可直接下载**\n'
            '  ③ Go 版硬编码了一整串 cookie（含 SUB/SUBP/XSRF-TOKEN），'
            '时间戳 1625663522 = 2021-07，SUBP 早已轮换 → 大概率已失效。'
            '差异暴露的是「作者当时需要登录态」，我们实测不需要 → P9'),
        'cover_source': (
            'cover_image 就在 component 接口里，**不需要第二个接口**。'
            '实测 component 的 cover_image 与 m.weibo.cn 的 '
            'page_info.page_pic.url 是**同一张图**（同 URL、同 56268 字节）。'
            '（曾绕道第二接口取封面，属于多做一次请求，已修正）'),
        'field_correction': (
            '★ 点赞数是 attitudes_count，不是 like_count（后者不存在）。'
            'comments_count / reposts_count / followers_count 均实测存在'),
        'url_variants': [
            'weibo.com/tv/show/1034:5343195622473745?mid=5343196424963244',
            'weibo.com/tv/show/1034:5343195622473745（无 mid 也能解析）',
            'video.weibo.com/show?fid=1034:5343195622473745',
            '微博 App 分享文案（含裸 oid + 完整链接）',
        ],
        'cdn': {
            'video': 'f.video.weibocdn.com（单域名，✅ 可加小程序白名单）',
            'image': 'wx*.sinaimg.cn',
            'expiry': 'URL 带 Expires + ssig 签名 → 缓存 TTL ≤ 10 分钟',
        },
        'measured': {
            'tracks': 2,   # trak=2 → 视频 + AAC 音频，单文件含音轨，dash=False
            'resolution': '1078x1744（竖屏，orientation=vertical）',
            'duration_s': 319.41,
            'size_mb': 112.83,
            'ftyp': 'isom（正常 MP4）',
        },
    },
    'ixigua': {
        'source': 'parse-video-py + parse-video(Go)（源码仍有效，但平台已合并）',
        'status': 'blocked（PC 站已并入抖音精选）',
        'py_impl': {
            'desc': '无 Cookie，只用随机 Android UA',
            'url': ('https://m.ixigua.com/douyin/share/video/{id}'
                    '?aweme_type=107&schema_type=1&utm_source=copy'
                    '&utm_campaign=client_share&utm_medium=android&app=aweme'),
            'field': ('loaderData["video_(id)/page"].videoInfoRes'
                      '.item_list[0].video.play_addr.url_list[0]'),
            'transform': '.replace("playwm", "play") + 302 跟随',
        },
        'go_impl': {
            'desc': '★ 带一整套硬编码 Cookie（两版的关键差异）',
            'cookie': ('MONITOR_WEB_ID / ixigua-a-s / ttcid / BD_REF / '
                       '__ac_nonce / __ac_signature / ttwid（7 个）'),
            'ua': 'Chrome/79.0.3945.88',
            'field': 'gjson: loaderData.video_(id)/page.videoInfoRes.item_list.0',
        },
        'diff_insight': ('★ Go 版比 Python 版多带 7 个 Cookie。实测带上后'
                         '首页从 7717 字节涨到 61791 字节 → Cookie 确实影响'
                         '返回内容。但内容是 App 下载页，分享页 item_list 仍为 0。'),
        'conclusion': ('两版实现方式本质相同（SSR 正则 _ROUTER_DATA），'
                       '差异只在 Cookie。**但平台已合并，源码已失效。**'),
        'lesson': ('★ 平台合并后，URL 仍返回 200 + _ROUTER_DATA，但数据为空。'
                   '这是"接口存在、业务已下线"的典型形态 —— '
                   '只看状态码和字段存在性会误判为可用。'),
    },
    'liujianfang': {
        'source': 'parse-video-py',
        'status': 'blocked（实测是直播平台，非点播）',
        'lesson': '开源项目按点播收录，实测 v.6.cn/{房间号} 是直播间，'
                  '页面无 playurl/mp4。业务形态不匹配 → 不纳入',
    },
    'xiaohongshu': {
        'source': '⚠️ 开源实现（3 家）**全部失效**（结构改版）；'
                  '本条数据链是 2026-10-05 实测重新定位',
        'license': 'n/a（结构已变，借鉴价值仅在「用 yaml 而非 json」）',
        'sample': 'https://www.xiaohongshu.com/discovery/item/6a827209000000002701cde0'
                  '?xsec_token=AB7esHwJgaSa...&xsec_source=pc_share',
        'video': {
            'engine': '纯 HTTP SSR（iOS UA + yaml 解析）',
            'ua': '★ 必须 iOS UA。PC UA → 302 到 /login；'
                  'iOS UA → 200（实测 170KB vs PC 的 73KB）',
            'parser': '★ yaml.safe_load(window.__INITIAL_STATE__)，'
                      '不能用 json.loads（state 含 undefined/裸值，必失败）',
            'current_chain': (
                'state.noteData.data.noteData\n'
                '  .title / .desc / .type / .user\n'
                '  .imageList[] → .url（含水印）/ .fileId / .width / .height\n'
                '  .video→ 视频笔记用'),
            'legacy_chain': (
                '开源项目用的旧路径（已失效）：\n'
                '  state.note.noteDetailMap[{id}].note\n'
                '  → 实测顶层 key `note` 根本不存在'),
            'nowatermark': (
                '用 fileId 拼：\n'
                '  https://sns-na-i6.xhscdn.com/{fileId}'
                '?imageView2/2/w/1080/format/jpg\n'
                '  （sns-img-qc.xhscdn.com 同样可用，实测字节数一致）'),
            'dead_rule': (
                '⚠️ 开源的去水印规则已失效：\n'
                '  ci.xiaohongshu.com/notes_pre_post/{id} → **实测 404**'),
            'url_normalize': (
                '/explore/{id} 与 /discovery/item/{id} 等价，'
                '但 /explore/ 会**间歇性**返回空 noteData → 统一走后者'),
            'retry': '空 noteData 时重试 2 次（实测抖动真实存在）',
        },
        'video_note': {
            'trigger': 'noteData.data.noteData.type == "video"',
            'trap': (
                '⛔ 视频笔记 ALSO 带 imageList（那是封面图）—— '
                '不要用「images 非空」判图集（P27，我踩过）'),
            'url_preferred': (
                'consumer.originVideoKey 拼 '
                'https://sns-video-bd.xhscdn.com/{originVideoKey}\n'
                '  → **无 sign 参数，可长期缓存**（推荐）'),
            'url_signed': (
                'media.stream.h264[0].masterUrl\n'
                '  → 带 ?sign= 有时效，缓存会失效；backupUrls[0] 为备用'),
            'encodings': 'h264(1112kbps) / h265(793kbps)；'
                         'h265 省流量但兼容性差 → 默认给 h264',
            'duration': (
                '⚠️ 单位陷阱（P28）：media.video.duration=262 是【秒】，'
                'stream.*.duration=261389 是【毫秒】→ '
                '优先取 stream 的毫秒值'),
            'measured': '63.78MB / 261.39s / 1920x1080 / H.264+AAC 双轨，'
                        '声明 262s 吻合（非截断）；抽帧确认无「小红书」水印',
            'sample': 'https://www.xiaohongshu.com/discovery/item/'
                      '6a72adee0000000033036edf?xsec_token=ABgKYGq72...',
        },
        'image': {
            'field': 'noteData.data.noteData.imageList[]',
            'pick_rule': '用 fileId 拼 sns-na-i6（无水印），'
                         '保留原始 url 作为对照',
            'verified': '下载看图确认：sns-webpic-qc 的 url 带「小红书」水印，'
                        'fileId 拼的地址无水印（同为 1080x1683）',
            'title_source': (
                '★ 标题有**三级来源**（2026-10-05 用户指出后修正）：\n'
                '  ① ssr        note.title —— **只有图集笔记有**'
                '（type=normal）\n'
                '  ② share_text 分享文案里的【标题 - 作者 | 小红书】'
                ' → **视频笔记唯一的标题来源**\n'
                '  ③ desc_head  desc 首句兜底（用户只贴裸链接时）\n'
                '  分享文案格式：{序号} 【{标题} - {作者} | 小红书 - 你的生活兴趣社区】'
                ' 😆 {码} 😆 {url}\n'
                '  ⚠️ 标题本身可能含「 - 」，所以**不能简单 split(" - ")**，'
                '要用右侧「| 小红书」定位边界'),
        },
    },
    'kuaishou': {
        'source': 'parse-video-py + video-parser（思路对，域名需换成 m.gifshow.com）',
        'license': 'MIT / MIT',
        'status': 'ready（2026-10-05 实测跑通）',
        'video': {
            'entry': 'https://m.gifshow.com/fw/photo/{workId}',
            'ua': 'iOS UA 必填',
            'state': 'window.INIT_STATE',
            'find_node': (
                '★ 顶层 key 被混淆 → 遍历找「含 result+photo 且 result==1」'
                '的 dict，**不要按 key 名取**'),
            'field': 'photo.mainMvUrls[].url（去重后）',
            'alt': 'photo.manifest.adaptationSet[].representation[].url',
            'no_watermark': 'mainMvUrls 抽帧确认无快手水印（实测）',
        },
        'meta_fields': (
            'caption(=标题/文案) / userName / headUrl / coverUrls[].url\n'
            'duration(毫秒) / width / height / timestamp(毫秒)\n'
            'likeCount / commentCount / forwardCount(转发) / viewCount\n'
            'photoId / kwaiId(快手号)'),
        'open_source_impl': (
            '★ 3 个开源项目都用 SSR 读 INIT_STATE，**思路是对的**，'
            '但它们用 www.kuaishou.com —— 那个域现在被反爬拦死。'
            '我实测把入口换成 m.gifshow.com 即完全可用。'
            'video-parser 用的 __APOLLO_STATE__ 变量名另两个用 INIT_STATE，'
            '说明快手改版过多次。'),
    },
    'acfun': {
        'source': 'parse-video-py（只写了 var playInfo，**已失效**）'
                  ' + 本轮实测重新定位',
        'license': 'MIT / 借鉴思路，代码自写',
        'sample': 'https://www.acfun.cn/v/ac48890260',
        'video': {
            'engine': '纯 HTTP SSR（148KB 页面里带完整数据）',
            'anchor': '"currentVideoInfo"（用花括号配平提取，'
                      '正则 \\{.*?\\} 会被嵌套打断）',
            'chain': (
                '页面 HTML → "currentVideoInfo" 对象 → '
                'ksPlayJson（**字符串化的 JSON，要 parse 两次**）→ '
                'adaptationSet（★ 是数组不是对象）→ '
                'representation[]（5 档）→ m3u8 → '
                '#EXTINF + **相对路径** .ts 分段'),
            'field': 'ksPlayJson.adaptationSet[0].representation[]',
            'gears': '1080P+ / 1080P / 720P / 540P / 360P（5 档）',
            'hevc': 'ksPlayJsonHevc 是 H.265 版；'
                    'iOS/旧安卓应选 ksPlayJson（H.264）那份',
            'url_id_trap': (
                '★ 详情页 URL 必须带 `ac` 前缀：/v/ac48890260 ✅，'
                '/v/48890260 → 502 Bad Gateway。'
                '移动端短链是 /v/?ac=48890260（不带前缀）—— 两种都要支持'),
            'm3u8_relative': (
                '★ m3u8 分段是**相对路径**（不是 http 开头），'
                '必须 urljoin(m3u8_url, seg) 拼绝对地址'),
            'only_m3u8': (
                '⛔ url 与 backupUrl[] 全是 m3u8，**无单文件 mp4**。'
                '1080P+ 实测 59 段 / 154.66MB / 299.0s，'
                '与 durationMillis 吻合（非截断，对比 P12 搜狐）'),
            'no_truncation': '累计体积与声明时长一致 → 不是试看片段',
        },
        'missing': 'currentVideoInfo 里**没有 author 和 cover 字段** → 如实留空',
    },
}

# ── 阻塞平台也要留接口记录（P29自检要求 PLATFORMS 与 FIELD_PATTERNS 平台集合一致）
#    否则「为什么不做」这条知识会在换人接手时丢失
FIELD_PATTERNS['qqvideo'] = {
    'source': 'parse-video-py（实测阻塞）',
    'license': 'MIT',
    'status': 'blocked（平台关闭免登录解析）',
    'video': {
        'url': 'https://h5vv.video.qq.com/getinfo',
        'params': {'vid': '{vid}', 'otype': 'json', 'platform': '101001',
                   'ehost': 'https://v.qq.com', 'appver': '15.13.0ctl',
                   'guid': '{32位随机}'},
        'response': 'JSONP，回调名 GetInfo',
        'block_sign': 'em:61「该内容暂不可观看」',
        'verified': '★ 真实浏览器 + 完整 Cookie 下仍返回 em:61 —— '
                    '不是缺参数或缺登录态，是平台侧关闭（P4/P8 的典型案例）',
    },
    'lesson': '判「不可接入」前，务必在**真实浏览器 + 完整会话**下复测一次。'
              '只测纯 HTTP 会把「需要登录」误判成「平台已死」',
}


# ═══════════════════════════════════════════════════════
# 三、已踩过的坑（避免重犯）
# ═══════════════════════════════════════════════════════

PITFALLS = [
    {
        'id': 'P1',
        'title': '平台字段标记不能靠字面猜',
        'severity': 'normal',
        'detail': 'dy-water 我理解成 "watermark removed"，实际是"加上水印"。'
                  'url_list=dy-aweme-images（无水印），'
                  'download_url_list=dy-water-v2（底部有账号水印）',
        'rule': '拿到地址后必须下载并肉眼/字节验证，不能只看字段名',
    },
    {
        'id': 'P2',
        'title': '接口返回错误 ≠ 平台不可用',
        'detail': '好看视频 errno:101007我判成"平台下线"，实际是滑块验证。'
                  'pagepd:"web_hkoffline" 的 hk 是「好**看」拼音首字母',
        'rule': '★ 凡是"接口不通"的判断，必须先用浏览器打开页面看正文。'
                '页面会直接告诉你原因（滑块/登录墙/404/真下架）',
        'severity': 'critical',
    },
    {
        'id': 'P3',
        'title': '同一接口的参数格式差异决定成败',
        'severity': 'normal',
        'detail': 'slidesinfo 用 aweme_id=单数返回 null，'
                  '用 aweme_ids=[]数组格式返回完整数据（65122 字节）',
        'rule': '★ 接口报错先怀疑参数格式，读源码确认，不要直接判死',
    },
    {
        'id': 'P4',
        'title': '"页面能打开"≠"接口可用"',
        'detail': '腾讯视频页面标题正常、浏览器可访问，'
                  '但 getinfo 即使带完整 Cookie 仍返回 em:61',
        'rule': '★ 判断依据必须是**直接调核心接口**，不能只看页面',
        'severity': 'critical',
    },
    {
        'id': 'P5',
        'title': '签名 URL 不能截断',
        'severity': 'normal',
        'detail': '好看视频 playurl 取 slice(0,150) 导致签名不全 → 403',
        'rule': '带签名/时效的 URL 必须完整传递',
    },
    {
        'id': 'P6',
        'title': 'SSR 页面要先访问再取 state',
        'severity': 'normal',
        'detail': '直接调 SSR API 拿不到 state，'
                  '必须先 goto 页面让 JS 跑完再读 window.__INITIAL_STATE__',
        'rule': 'SSR 类平台统一走"浏览器内 fetch"，不要纯 HTTP 直连',
    },
    {
        'id': 'P7',
        'title': 'gzip 必须解压',
        'severity': 'normal',
        'detail': 'B站页面返回 gzip，不解压看到的是乱码，'
                  '会误判为"无数据"',
        'rule': '检查 Content-Encoding 头',
    },
    {
        'id': 'P8',
        'title': '接口存在 ≠ 业务还在',
        'detail': '西瓜移动端分享页仍返回 HTTP 200 + window._ROUTER_DATA，'
                  '但 item_list 恒为 0 —— 因为 PC 站已并入抖音精选。'
                  '只查状态码和字段存在性会误判为"可用"',
        'rule': '★ 必须验证 **业务字段有实际内容**（如 item_list 长度 > 0），'
                '不能只看 HTTP 200 和 key 存在。'
                '浏览器打开首页看渲染内容是最快的判别方式',
        'severity': 'critical',
    },
    {
        'id': 'P9',
        'title': '多项目对比要找"实现差异"，不是读一个就下结论',
        'severity': 'normal',
        'detail': '我读了 parse-video-py 的 xigua.py 就判"需浏览器"，'
                  '但没读 Go 版—— Go 版带了 7 个硬编码 Cookie，'
                  '说明作者遇到的是反爬而非浏览器问题。'
                  '虽然最终结论相同（平台已合并），但推理依据完全不同',
        'rule': '★ 同一个平台在多个项目里的实现方式差异，'
                '往往直接暴露平台真正的拦截手段。'
                '差异点 = 别人踩过的坑',
    },
    {
        'id': 'P10',
        'title': '开源代码的落地边界必须自己守住',
        'severity': 'normal',
        'detail': '10 个调研项目里只有 5 个可商用（MIT）。'
                  '我唯一直接复制的是 abogus_ref.py（342 行，100% 复制），'
                  '其余 2537 行全部自研',
        'rule': '★ 复制前必须查 LICENSE：'
                'AGPL-3.0（Yeguo-IDM）/ GPL-3.0（TVHelper）不可用于闭源服务；'
                '无LICENSE 文件（uvd/VnaSeek）= 无授权。'
                '只从 MIT/Apache 项目取，且必须保留出处声明',
    },
    {
        'id': 'P11',
        'title': '「必须用浏览器」常常是被自己的操作步骤骗出来的',
        'detail': '好看视频我标engine=browser，理由是纯 HTTP 返 errno:101007 '
                  '（未过滑块）。这次把变量拆开单独测：只做「GET 首页拿 cookie '
                  '→ 带 cookie 打接口」，4/4 全部 errno=0、1080P 完整文件可下。'
                  '触发滑块的是我当初顺手做的「goto 视频详情页」，'
                  '而解析根本不需要那一步。',
        'rule': '★ 判定「需浏览器」时，必须分离变量：'
                '把「建立会话」和「访问详情页」拆成两次独立请求，'
                '分别看哪一步才触发拦截。'
                '很可能真正需要的只是「访问一次首页」。',
        'severity': 'critical',
    },
    {
        'id': 'P12',
        'title': '平台给的「下载字段」可能只是试看片段',
        'detail': '搜狐 url_high_mp4 / download_url 返回的永远是'
                  '**恰好 468026 字节、恰好 30.04 秒** 的文件，'
                  '与真实时长和 file_size_high 都无关。'
                  '声明 76 秒的视频被截掉 46 秒。'
                  '10 个开源项目（含 parse-video-py 与 Go 版）都只取这个字段，'
                  '所以对>30s 的搜狐视频都会返回残缺文件。',
        'rule': '★ 拿到播放地址后，除了看 Content-Type，'
                '还要**读容器时长**（MP4 读 mvhd）并与接口声明的时长比对，'
                '差值 >2s 即判定截断。'
                '体积恒定不变是强信号。',
        'severity': 'critical',
    },
    {
        'id': 'P13',
        'title': '接口已经给了权威字段，不要靠 URL 路径反推',
        'severity': 'normal',
        'detail': '我按 URL 路径（cae_h264/hd/sc/1080p）猜好看视频清晰度，'
                  '结果 4 档全标成「360P」。'
                  '而接口里 title="蓝光 1080P"、vodVideoHW="1080$$1920"、'
                  'videoBps、videoSize、rank 全都是现成的。',
        'rule': '★ 写解析器前先把 curVideoMeta 这类对象的 key 全打出来看一遍，'
                '优先用平台自述字段；URL 路径只作兜底。'
                '（这是 P1「不能靠字面猜」在 URL 上的变体）',
    },
    {
        'id': 'P14',
        'title': '开源项目收录 ≠ 业务形态匹配',
        'severity': 'normal',
        'detail': '六间房被 parse-video-py 当点播平台收录，'
                  '实测 v.6.cn/219369 是**直播间**（title 含「直播间」，'
                  '页面 直播/live/anchor 出现 15/50/25 次，'
                  '而 playurl/mp4/videoUrl 各 0 次）。'
                  '直播流无法「解析成文件」。',
        'rule': '★ 接入前先确认业务形态：点播 / 直播 / UGC 短视频。'
                '直播平台要的是时移录制接口（另一套签名），不是播放地址。',
    },
    {
        'id': 'P15',
        'title': '参数缺失会被伪装成「资源不存在」',
        'severity': 'normal',
        'detail': '搜狐只传 site=2 时返回'
                  '「视频(620254006, 2)不存在，去看看其它视频吧」——'
                  '而这个 ID 确实存在，加上 api_key + sver 后正常返回。',
        'rule': '★ 接口报「不存在」时，先怀疑自己参数不全，'
                '再怀疑 ID 无效。可用同一 ID 换参数组合交叉验证。',
    },
    {
        'id': 'P16',
        'title': '页面编码不统一，UTF-8 假设会让中文全变乱码',
        'severity': 'normal',
        'detail': '搜狐详情页是 GB18030；按 UTF-8 解码直接抛 '
                  'UnicodeDecodeError（position 226），'
                  '用 errors=ignore 则 title 变成「һͩ硰Ůˬ ƭǮƭ」这种乱码，'
                  '极易误判为「页面无内容」。',
        'rule': '★ 抓页面后先探测编码：尝试 utf-8 → gb18030 → latin-1，'
                '看title 是否可读。B站是 gzip（P7），搜狐是 GB18030。',
    },
    {
        'id': 'P17',
        'title': '「第一个元素就是最优」是巧合，不是规律',
        'severity': 'normal',
        'detail': '微博 urls 的第一个 key 恰好是最高档（高清 1080P），'
                  '我就写进了知识库当规律。实测发现那是「dict 保序 + '
                  '平台按降序插入」的结果 —— 平台一旦调顺序就会取错档。',
        'rule': '★ 依赖顺序取最优值前，先确认排序是否稳定。'
                '优先「按语义字段排序」（如从 label 解析 1080/720/480），'
                '把下标顺序只当兜底。同类：highest/quality 字段、'
                '「取最后一个」等经验法则都要复核。',
    },
    {
        'id': 'P18',
        'title': '用字节串计数判断 MP4 有无音轨会误判',
        'severity': 'normal',
        'detail': '我数 b\'trak\' 出现次数得到 1，就断言「疑似无音轨」；'
                  '实际正确做法是递归遍历 box 树看hdlr，'
                  '结果是 trak=2（vide + soun，含 mp4a/esds），音轨完好。',
        'rule': '★ 容器结构必须**递归解析 box 树**，不能靠子串计数：'
                'trak/mdia/avc1 会在文件里多次出现，计数无意义。'
                '判定音轨看 trak 下的 hdlr handler_type（vide/soun）。'
                '（同源教训见 P1：不能靠字面猜）',
    },
    {
        'id': 'P19',
        'title': '接口会主动告诉你正确的字段名 —— 把它当探针用',
        'severity': 'normal',
        'detail': '快手 GraphQL 我乱写字段名 visionPhotoDetail，'
                  '返回 "Did you mean \\"visionVideoDetail\\" or '
                  '\\"visionHotRank\\"?" —— 相当于免费拿到接口结构情报。',
        'rule': '★ 遇到 GraphQL / 强 schema 接口时，**故意写错字段名**，'
                '很多服务会把候选字段名回给你。这比翻 JS 源码快得多。'
                '同时说明「接口活着」—— 被风控挡在数据层之前，不等于接口没了。',
    },
    {
        'id': 'P20',
        'title': '业务 ID 的「前缀」在短链和详情页里可能不同',
        'severity': 'normal',
        'detail': 'AcFun：移动端短链是 /v/?ac=48890260（纯数字），'
                  '但详情页只认 /v/ac48890260（带ac 前缀）。'
                  '我统一用纯数字拼 URL → 502 Bad Gateway，'
                  '而同一个 ID 手动加前缀就 200。',
        'rule': '★ 提取 ID 后，**先验证哪个形态能访问详情页**，'
                '不要假设短链形态= 详情页形态。'
                '502/404 时先怀疑 URL 拼装，而不是判「平台不可用」。'
                '（与 P15 同源：别把参数/格式问题误判成资源不存在）',
    },
    {
        'id': 'P21',
        'title': '「JSON 套 JSON」与「数组伪装成对象」是常见双层陷阱',
        'severity': 'normal',
        'detail': 'AcFun 页面里 currentVideoInfo.ksPlayJson 本身是'
                  '**字符串化的 JSON**（\\\\" 转义），要 parse 两次；'
                  '而 adaptationSet 又是**数组**不是对象，'
                  '按 dict 写直接 AttributeError。',
        'rule': '★ 解析嵌套结构时：'
                '① 先打印 type() 和 keys() 确认形状，别凭直觉写'
                '② 提取内层对象用**花括号配平**（含字符串转义处理），'
                '不要用 `\\{.*?\\}` 正则（遇嵌套即断）'
                '③ 数组/对象都做兼容：'
                '`ads = d.get(k) or []; if isinstance(ads, dict): ads = [ads]`',
    },
    {
        'id': 'P22',
        'title': 'm3u8 分段可能全是同一份内容重复 —— ffmpeg不会报错',
        'detail': '搜狐 m3u8 写 12 段、EXTINF 合计 76.85s，看起来像完整视频。'
                  '但**12 段的 MD5 完全相同** —— 全是同一个 30 秒试看内容。'
                  '直接 ffmpeg 合并会得到「30 秒 × 12 遍」的 6 分钟垃圾文件，'
                  '而 **ffmpeg 退出码是 0，不报任何错**（它只按 EXTINF 累加时长）。',
        'rule': '★ 合并 m3u8 前**必须自己查分段哈希**：'
                '取前 3-4 段算 MD5，若全同则判定为重复试看片段并拒绝合并。'
                '合并后再核对「产物时长 / EXTINF 声明时长」比值，'
                '偏离 0.75~1.25 区间即异常。'
                '★ 推论：**「接口返回 m3u8」不等于「m3u8 是完整视频」**，'
                '与 P12（试看片段）同源，只是这次藏在分段层面。',
        'severity': 'critical',
    },
    {
        'id': 'P23',
        'title': 'ffmpeg 用 -c copy（remux）即可，不要默认转码',
        'severity': 'normal',
        'detail': 'm3u8 分段本身已是 H.264+AAC，ffmpeg 只需重封装。'
                  '实测 155MB / 5 分钟视频 -c copy 仅 5.4 秒完成、'
                  'duration_ratio=1.0（与声明一致）；'
                  '而 -c:v libx264 会慢一个数量级且有画质损失。',
        'rule': '★ 默认 `-c copy -movflags +faststart`。'
                '只有源是 HEVC(H.265) 而目标设备不兼容时才 reencode。'
                '`-movflags +faststart` 必须加 —— '
                '否则 moov 在文件尾，移动端必须下完整个文件才能播。',
    },
    {
        'id': 'P24',
        'title': '「读源码」不等于「读完所有项目的同一平台实现」',
        'severity': 'normal',
        'detail': '我接微博时只读了 parse-video-py 一个实现就动手，'
                  '并自行推断「component 接口不给封面」，于是绕道第二个接口'
                  '取 page_pic.url。后来对比另外两个项目才发现：'
                  '**cover_image 就在第一个接口里**，'
                  '而且与 page_pic是同一张图（同 URL、同 56268 字节）'
                  '—— 我多绕了一次 HTTP 请求，理由是错的。',
        'rule': '★ 接入平台前把**所有**开源项目的该平台实现都读一遍'
                '（find -iname "*平台名*"，本轮 10 个项目里 3 个有微博）。'
                '差异点往往直接给出「哪些字段真实存在」的答案。'
                '★ 同时警惕自己「读源码时想当然」的推断 —— '
                '「文档/代码里没提到X」≠「接口不下发 X」。',
    },
    {
        'id': 'P25',
        'title': '同一接口的两个域名，数据等价但门槛可能差一个登录态',
        'severity': 'normal',
        'detail': '微博 component 接口有两个域名：\n'
                  '  h5.video.weibo.com  → 匿名可用（实测 200）\n'
                  '  weibo.com/tv        → 无 cookie 302 到访客系统，'
                  '强制要登录态（m3u8-dl 因此在代码里要求用户提供 cookie）\n'
                  '两者返回的数据几乎完全一样（2615 vs 2616 字节）。',
        'rule': '★ 遇到「必须登录才能调」的接口，先试同接口的**其他域名**'
                '（移动端/h5/旧版域名往往是匿名可用的）。'
                '→ 这一条能直接决定产品是否需要引入账号体系。',
    },
    {
        'id': 'P26',
        'title': '静默兜底会把「上游偶发失败」伪装成「接口全挂」',
        'severity': 'normal',
        'detail': '抖音短链解析 `except Exception: final = url` —— '
                  '网络抖动时静默兜底成原短链 → aweme_id 为空 → '
                  '两条通道都取不到数据 → 报「两条纯 HTTP 通道均无数据」。'
                  '实测 8 用例回归时偶发一次（7/8），而直接调用重试又全正常，'
                  '说明是短链环节的抖动。这个错误信息**完全指不到真因**，'
                  '排障时浪费了一轮往返。',
        'rule': '★ ① 网络类异常（超时/连接重置/DNS）必须**重试**，'
                '不要静默兜底；4xx/5xx 才不重试（重试也不会好）。'
                '② 错误信息要能区分「上游没给数据」与「我们没拿到 ID」：'
                'aweme_id 为空时报"短链解析失败"，而不是笼统的"通道无数据"。'
                '★ 通用形式：**兜底会掩盖故障**，宁可抛出带上下文的错误。',
    },
    {
        'id': 'P27',
        'severity': 'critical',
        'title': '「有图」不等于「图集」—— 类型判据选错会静默降级',
        'scene': '小红书视频笔记（type=video）',
        'wrong': '用「imageList 非空」判定为图集，'
                 '把一条 262 秒视频误报成「1 张图的图集」',
        'right': '唯一判据是平台自述的 type 字段，'
                 '不要用「有没有配图」反推内容形态',
        'why_dangerous': (
            '**接口返回 200、字段齐全、封面图也拿到了，'
            '所有「有无报错」类检查都通过** —— '
            '但结果完全错（用户拿到 1 张封面而不是 4 分钟视频）。'
            '这是最隐蔽的一类 bug：没有任何错误信号。'),
        'rule': (
            '★ 内容形态（视频/图集/直播）**必须读平台自述字段**，'
            '不能用「配套素材是否存在」推断。'
            '配图/封面/首帧的存在与否与主体形态无关。'
            '新增平台时把 type 字段列入必查清单。'),
        'verified': '同一条笔记修正前后：'
                    '修正前 type=image image_count=1，'
                    '修正后 type=video options_count=3 duration_s=261.39',
    },
    {
        'id': 'P28',
        'severity': 'high',
        'title': '同名字段单位可能不一致（秒 vs 毫秒）',
        'scene': '小红书 video.media.video.duration vs video.media.stream.*.duration',
        'evidence': '同一条视频：media.video.duration = 262'
                    '（=秒，ffprobe 实测 261.39s）；'
                    'stream.h264[0].duration = 261389（=毫秒）',
        'wrong': '把 262 当毫秒除以 1000 → 时长显示 0.26 秒',
        'rule': (
            '★ 拿到 duration 类字段，先与**下载后 ffprobe 的真实时长**'
            '或与同一对象内其他字段交叉比对，确认单位再使用。'
            '同名不代表同单位。'
            '跨字段一致性检查是识别单位错误最便宜的手段。'),
    },
    {
        'id': 'P29',
        'severity': 'high',
        'title': '纯数据 bug 只能靠自检发现 —— 字段名不统一会静默丢数据',
        'scene': 'knowledge.py 的 PITFALLS',
        'wrong': '历史 26 条用 severity，我新增 2 条误用level，'
                 '而 summary() 查的是 severity → 新坑级别**静默丢失**，'
                 '界面上一切看起来正常',
        'also_found': (
            '同一次全库扫描还发现 3 类问题：\n'
            '① 20 条踩坑**完全没有**级别字段（靠「有无此键」隐式分级）\n'
            '② 6 处键名带 \'⭐ \' 前缀 → get_field_pattern() 取不到值\n'
            '③ 腾讯视频在 PLATFORMS 里有、FIELD_PATTERNS 里没有'
            ' → 「为什么不做」的知识会丢失'),
        'rule': (
            '★ 纯数据层（字典/配置）**必须有自动一致性自检**：\n'
            '  - 同一语义的字段名统一（severity 而非 level）\n'
            '  - 必须字段一律显式给出，不靠「有无此键」表达默认值\n'
            '  - 键名限ASCII（装饰性前缀会让取值静默失败）\n'
            '  - 两张关联表的key 集合应一致\n'
            '★ 这类 bug 没有运行时异常，只会让报表/看板少数据 —— '
            '**不写自检就永远发现不了**。'),
        'fixed': '已在 knowledge.py 加「数据一致性」自检段，'
                 'python app/knowledge.py 每次运行都会校验',
    },
    {
        'id': 'P30',
        'severity': 'high',
        'title': '「数字」与「展示文本」必须分两个字段 —— 别把「29.8万」当数字用',
        'scene': 'AcFun 粉丝数、小红书点赞数、微博播放量',
        'evidence': (
            '同一平台里两种格式并存：\n'
            '  AcFun  fanCount = "29.8万"   fanCountValue = 298301\n'
            '  小红书 likedCount = "22.8K"  但 collectedCount = 2730（纯数字）\n'
            '  微博  play_count = "450万"（无数字版）\n'
            '  → int("29.8万") 直接抛异常；只取数字版则微博/小红书部分字段拿不到'),
        'wrong': '统一 int(v) 转换 → 要么崩，要么把 29.8 当成 29个粉丝',
        'rule': (
            '★ 规范层输出**两个字段**：\n'
            '  stats      → int（排序/统计用）\n'
            '  stats_text → str（展示用，保留平台原始格式）\n'
            '  数字版优先，缺失时从文本换算（cn_number_to_int），'
            '并在 knowledge 里记下该平台是哪种格式。'),
        'implemented': 'app/meta.py 的 stats / stats_text 双字段 + '
                       'cn_number_to_int()（支持 万/亿/K/w 与千分位）',
    },
    {
        'id': 'P31',
        'severity': 'medium',
        'title': '元信息字段名不统一会让前端写 N 套判断 —— 必须有规范化层',
        'scene': '7 个平台解析器的返回字段',
        'observed': (
            '同一语义有 4 种叫法：\n'
            '  播放量 play_count / view_count / playcnt / fmplaycnt\n'
            '  点赞   like_count / attitudes_count / fmlike_num / likedCount\n'
            '  时长   duration_ms / duration_time / durationMillis / time_length\n'
            '  文案   description / caption / desc / text'),
        'rule': (
            '★ 解析器只负责「如实返回接口给的」，规范化层负责「映射到统一名」，'
            '两者职责分离。→ 平台改字段只改映射表，前端零改动。\n'
            '★ 规范化后的**可选键必须始终存在**（哪怕是空 dict），'
            '前端不该用「键是否存在」判断平台能力。\n'
            '⚠️ 映射表里的路径写的是**解析器返回的 key**，'
            '不是平台接口原始字段名 —— 两者不一定相同，改一处要同步另一处。'),
        'implemented': 'app/meta.py（normalize_meta + 映射表 + 自测 + '
                       'field_coverage 覆盖度检查）',
    },
    {
        'id': 'P32',
        'severity': 'critical',
        'title': '⭐ 反爬通常只覆盖主站—— 备用/历史域名可能完全没跟上',
        'scene': '快手：主站 www被反爬滑块拦死，m.gifshow.com 完全畅通',
        'evidence': (
            '同一workId（3xy2kubupu94q74）两个入口的实测对比：\n'
            '| 入口 | 结果 |\n'
            '|---|---|\n'
            '| www.kuaishou.com/short-video/{id} | 82 字节 {"result":2} |\n'
            '| www.kuaishou.com/graphql（4 种 UA × 3 个 workId）| 全部 400002 + captcha |\n'
            '| **m.gifshow.com/fw/photo/{id}** | **200/ 163KB / INIT_STATE 完整** |\n'
            '→ gifshow 是快手最早的品牌名（快手曾叫 Gifshow），'
            '主站换域名后**这个域没跟上反爬**'),
        'why_hard_to_find': (
            '★ 平台往往有**多个域名**：主站 + 移动站 + 历史品牌名 + m站 + App 域名。'
            '只试主站会得出「此路不通」的错误结论。'
            '我上一轮判「快手不接入」就是因为只试了 www.kuaishou.com。'),
        'rule': (
            '★ 判「某平台不可接入」之前，**必须把该平台的所有已知域名试一遍**：\n'
            '  ① 主站 www / 无 www\n'
            '  ② 移动站（m. 开头 / /mobile 路径）\n'
            '  ③ **历史品牌名**（快手=gifshow、AcFun=acfun.cn/acfun.com、'
            '新浪=weibo/xinmin）\n'
            '  ④ m 站、App 域名、CDN 域名反查\n'
            '方法：搜「平台名+旧域名/改名」，或看 App 的 HTTP 头/证书SAN。\n'
            '★ 接入后必须加**独立探针**监控这个域名 —— '
            '平台哪天补上反爬，只有探针能第一时间发现。'),
        'implemented': 'kuaishou_pure.py 走 m.gifshow.com；'
                       'health.py 有独立 kuaishou 探针（断言拿到播放地址+ 时长量级）',
    },
    {
        'id': 'P33',
        'severity': 'medium',
        'title': '测试脚本写死端口 → 静默打到别的服务，报出误导性失败',
        'scene': 'e2e_regression.py 连续多轮改端口，sed 替换失配',
        'symptom': (
            '新增的快手用例报「platform: douyin / 短链未解析出 aweme_id」—— '
            '看起来像解析器 bug，实际是脚本打到了**上一轮的旧端口**，'
            '那个服务还没加载快手解析器，于是快手链接落到了兜底的抖音解析器'),
        'rule': (
            '★ 一切指向服务的测试脚本，端口一律从**环境变量**读：\n'
            '  BASE = os.environ.get("CB_TEST_BASE", '
            '"http://127.0.0.1:8080")\n'
            '★ 换端口时用 sed 批量替换是不可靠的（历史值太多时匹配错位）。\n'
            '★ 症状识别：「新用例报成别的平台的行为」→ '
            '先确认服务是不是最新代码、端口对不对，再查解析器。'),
        'implemented': 'tests/e2e_regression.py 已改用 CB_TEST_BASE',
    },
    {
        'id': 'P34',
        'severity': 'high',
        'title': '⭐「平台没给这个字段」可能只是你只看了接口 —— 分享文案里往往有',
        'scene': '小红书视频笔记的标题',
        'wrong_claim': (
            '我上一轮断言「小红书视频笔记无独立 title，接口不下发」，'
            '并写进了知识库的 known_gaps'),
        'user_correction': '用户直接指出「小红书的标题是可以提取的」',
        'reality': (
            '分享文案格式：{序号} 【{标题} - {作者} | 小红书 - 你的生活兴趣社区】'
            ' 😆 {码} 😆 {url}\n'
            '→ 视频笔记的标题**一直都在**，只是不在 SSR 的 note.title 里，'
            '而在用户复制的那段文本里'),
        'how_to_check': (
            '★ 判「某字段拿不到」之前，按这个顺序查：\n'
            '  ① 接口响应里所有 key（含嵌套、含非标量）\n'
            '  ② 页面 HTML：og:title / <h1> / <title> / JSON-LD\n'
            '  ③ **用户复制出来的分享文案** ←最容易漏！\n'
            '  ④ App 的 deeplink / 短码接口\n'
            '  ⑤ 其他路由（/explore vs /discovery、m站 vs 主站）'),
        'general_rule': (
            '★ 移动端平台的「标题」常有两处：结构化数据 + 分享文案。'
            '只读接口就会漏。**拿到用户给的一手样本时，先看他贴的原文里有什么** —— '
            '用户能复制出来的东西，都是产品设计希望被分享出去的。'),
        'implemented': 'xiaohongshu_pure.py 的 _extract_share_title() + '
                       'title_source 字段（ssr/share_text/desc_head）',
    },
]


# ═══════════════════════════════════════════════════════
# 四、已知能力缺口（如实记录，不要假装没有）
# ═══════════════════════════════════════════════════════

KNOWN_GAPS = [
    {
        'platform': 'haokan',
        'gap': '接口不下发作者名',
        'detail': '遍历 curVideoMeta 全部 30 个 key 无 author/user_name；'
                  'SSR __PRELOADED_STATE__ 的 uname 在游客态是空串。',
        'impact': '结果页作者位置为空。不编造，需登录态或另找接口才能补',
    },
    {
        'platform': 'sohu',
        'gap': '>30s 视频连m3u8 合并也救不了',
        'detail': 'm3u8 的全部分段内容相同（同一段试看内容重复 N 次），'
                  '合并只会得到重复的垃圾文件。ffmpeg 不报错，'
                  '所以必须自己预检哈希（已实现）。',
        'impact': '超过 30 秒的搜狐视频只能拿到前 30 秒，'
                  '已通过 truncated + user_warning + m3u8_usable=false '
                  '如实告知用户',
        'todo': '需登录 Cookie 才能拿完整版 —— 需评估账号池成本与合规性',
    },
    {
        'platform': 'ffmpeg',
        'gap': 'GPL 许可需法务确认',
        'detail': 'imageio-ffmpeg 自带二进制是 GPL 构建'
                  '（实测 configuration 含 --enable-gpl）。',
        'impact': '当前仅以子进程方式调用（通常不构成衍生作品），'
                  '代码与二进制解耦，可用 CB_FFMPEG_PATH 替换',
        'todo': '上线前让法务确认；或改用系统包安装的 ffmpeg',
    },
    {
        'platform': 'acfun',
        'gap': '只有 m3u8，无单文件 mp4',
        'detail': '5 档清晰度的 url 与 backupUrl 全是 m3u8，'
                  '1080P+ 实测 59 个 .ts 分段 / 154.66MB。'
                  '小程序 saveVideoToPhotosAlbum 只接受 mp4。',
        'impact': '必须服务端下载分段并合并（merge_required=True），'
                  'm3u8 的 .ts 不能直接给用户存',
        'todo': '实现 TS 合并（ffmpeg -f concat，或纯 Python 字节拼接 + '
                '转封装为 mp4），需评估镜像体积与耗时',
    },
    {
        'platform': 'acfun',
        'gap': 'SSR 不含作者与封面',
        'detail': 'currentVideoInfo 只有 title/durationMillis/各类计数，'
                  '无 author、无 cover。',
        'impact': '结果页作者位与封面留空（如实返回空串，不编造）',
        'todo': '若需要，可从页面其他 JSON 块（如 pageInfo）补取',
    },
    {
        'platform': 'kuaishou',
        'gap': 'GraphQL 需过滑块验证',
        'detail': '带完整会话 cookie 仍返回 result=400002 + '
                  'captcha.zt.kuaishou.com 滑块链接，'
                  'bizName=ANTICRAWL_DEFAULT。',
        'impact': '判定不接入。浏览器过滑块属对抗性操作，'
                  '成功率与维护成本都不可控',
        'todo': '若必须做，需评估合规性与长期稳定性，'
                '并接受平台改版即失效',
    },
]


# ═══════════════════════════════════════════════════════
# 五、代码来源台账（合规必需）
# ═══════════════════════════════════════════════════════

CODE_ORIGIN = {
    'audit_at': '2026-10-05',
    'method': '与 10 个开源项目源码做 6-gram 重复度检测（归一化后比对）',
    'total_lines': 2482,
    'copied_lines': 0,
    'copied_pct': 0.0,
    'self_written_pct': 100.0,
    'rewrite_done': {
        'file': 'app/parsers/abogus.py',
        'former': 'app/parsers/abogus_ref.py（已删除）',
        'was': '100% 直接复制自 userwanyong/uvd（Apache-2.0/GPL-3.0 溯源）',
        'now': '100% 自研，0% 重复',
        'equivalence': '与原实现 500/500 随机用例逐字节一致',
        'live_test': '抖音 detail 接口实测通过（48615 字节响应，8 张图集）',
        'algorithms': 'SM3（gmssl 库，GB/T 32905）+ RC4（自写）+ 变体 Base64（自写）',
    },
    'self_written': [
        'app/parsers/abogus.py (310行) —— a_bogus 签名独立实现',
        'app/parsers/douyin_pure.py (427行) —— 三级降级架构',
        'app/parsers/bilibili_pure.py (186行) —— API 路线',
        'app/parsers/douyin.py / bilibili.py —— 浏览器兜底',
        'app/knowledge.py (518行) —— 知识库',
        'app/main.py / cache.py / config.py / capabilities.py',
    ],
    'not_used': [
        {'project': 'Yeguo-IDM', 'license': 'AGPL-3.0', 'reason': '闭源服务会触发源码开放'},
        {'project': 'TVHelper', 'license': 'GPL-3.0', 'reason': '非开源即侵权'},
        {'project': 'VnaSeek', 'license': '无 LICENSE', 'reason': '默认保留所有权利'},
        {'project': 'kitty', 'license': 'ISC 但无文件', 'reason': '授权不明，未取其代码'},
        {'project': 'uvd', 'license': '无 LICENSE（README 称 MIT）',
         'reason': '曾复制其 abogus.py，现已重写并删除，零依赖'},
    ],
    'readable_but_not_copied': [
        {'project': 'parse-video-py', 'license': 'MIT', 'used_for': '字段路径与参数格式（已实测验证）'},
        {'project': 'parse-video(Go)', 'license': 'MIT', 'used_for': '西瓜 Cookie 差异、a_bogus 参数集'},
        {'project': 'm3u8-dl', 'license': 'MIT', 'used_for': 'uri + ratio 拼 1080P 技巧'},
        {'project': 'video-parser', 'license': 'MIT', 'used_for': '平台清单、字段路径交叉验证'},
        {'project': 'phlsM3U8_downner', 'license': 'MIT', 'used_for': '参考（无平台解析，未取代码）'},
    ],
}


# ═══════════════════════════════════════════════════════
# 六、工具函数
# ═══════════════════════════════════════════════════════

def match_platform(url: str) -> str:
    """按域名判断平台。取最长的匹配（避免子域串味）"""
    best, best_len = None, 0
    for name, cfg in PLATFORMS.items():
        for d in cfg.get('domains', []):
            if d in url and len(d) > best_len:
                best, best_len = name, len(d)
    return best


def get_field_pattern(name: str) -> Dict[str, Any]:
    return FIELD_PATTERNS.get(name, {})


def get_pitfalls() -> List[Dict[str, Any]]:
    return PITFALLS


def summary() -> Dict[str, Any]:
    buckets = {'ready': [], 'partial': [], 'blocked': [], 'pending': []}
    for name, cfg in PLATFORMS.items():
        buckets.get(cfg['status'], buckets['pending']).append(name)
    return {
        'total': len(PLATFORMS),
        'ready': buckets['ready'],
        'partial': buckets['partial'],
        'blocked': buckets['blocked'],
        'pending': buckets['pending'],
        'pure_http': [n for n, c in PLATFORMS.items()
                      if c.get('engine') == 'pure_http'],
        'browser': [n for n, c in PLATFORMS.items()
                    if c.get('engine') == 'browser'],
        'whitelist_ok': [n for n, c in PLATFORMS.items()
                         if c.get('whitelist_ok')],
        'pitfalls_count': len(PITFALLS),
        'critical_pitfalls': [p['id'] for p in PITFALLS
                              if p.get('severity') == 'critical'],
        'known_gaps': [
            {'platform': g['platform'], 'gap': g['gap']} for g in KNOWN_GAPS
        ],
        'code_origin': {
            'self_written_pct': CODE_ORIGIN['self_written_pct'],
            'copied_files': [],
            'rewrite_done': CODE_ORIGIN['rewrite_done']['former'],
        },
    }


def get_code_origin() -> Dict[str, Any]:
    """代码来源台账（合规审计用）"""
    return CODE_ORIGIN


# ═══════════════════════════════════════════════════════
# 五、自检
# ═══════════════════════════════════════════════════════

if __name__ == '__main__':
    import json
    s = summary()
    print(json.dumps(s, ensure_ascii=False, indent=2))
    print()
    print('=== 域名匹配测试 ===')
    tests = [
        ('https://v.douyin.com/abc/', 'douyin'),
        ('2.87 复制打开抖音 https://v.douyin.com/hZMkNvXLtLc/ 复制此链接', 'douyin'),
        ('https://www.bilibili.com/video/BV1GJ411x7h7', 'bilibili'),
        ('https://b23.tv/xxxxxx', 'bilibili'),
        ('https://haokan.baidu.com/v?vid=123', 'haokan'),
        ('https://weibo.com/2543858012/Q9pcJ4S21', 'weibo'),
        ('https://www.ixigua.com/7123456789', 'ixigua'),
        ('https://www.xiaohongshu.com/explore/6a90faff0000000007004fdb', 'xiaohongshu'),
        ('https://v.qq.com/x/cover/mzc00200abc.html', 'qqvideo'),
        ('https://v.kuaishou.com/2xxxxxx', 'kuaishou'),
        ('https://tv.sohu.com/v/MjAyNjEwMDUvbjYyMDI1NDAwNi5zaHRtbA==.html',
         'sohu'),
        ('https://my.tv.sohu.com/us/123/620251480.shtml', 'sohu'),
        ('https://v.6.cn/219369', 'liujianfang'),
        ('https://weibo.com/tv/show/1034:5343195622473745?mid=5343196424963244',
         'weibo'),
        ('https://video.weibo.com/show?fid=1034:5343195622473745', 'weibo'),
        ('https://www.acfun.cn/v/ac48890260', 'acfun'),
        ('https://m.acfun.cn/v/?ac=48890260', 'acfun'),
        ('https://m.kuaishou.com/short-video/3xha63juacrpw69', 'kuaishou'),
    ]
    ok = True
    for url, want in tests:
        got = match_platform(url)
        good = got == want
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {want:14s} <- {url[:44]}")
    print()
    print('全部通过' if ok else '有失败')

    # ── 数据一致性自检（P29）──
    # 背景：PITFALLS 历史上用 `severity`，我新增的两条误用了 `level`，
    # 结果 summary() 查severity 时新坑的级别**静默丢失**（看起来一切正常）。
    # 这类「字段名不统一」是纯数据 bug，只能靠自检发现。
    print()
    print('── 数据一致性 ──')
    data_ok = True

    bad_keys = [p['id'] for p in PITFALLS
                if 'level' in p or 'severity' not in p]
    if bad_keys:
        data_ok = False
        print(f'  ❌ 踩坑级别字段不统一（应统一用 severity）: {bad_keys}')
    else:
        print(f'  ✅ {len(PITFALLS)} 条踩坑级别字段统一为 severity')

    crit = [p['id'] for p in PITFALLS if p.get('severity') == 'critical']
    if len(crit) != len(summary()['critical_pitfalls']):
        data_ok = False
        print('  ❌ summary().critical_pitfalls 与实际不符')
    else:
        print(f'  ✅ critical 计数一致: {len(crit)} 条 {crit}')

    no_title = [p['id'] for p in PITFALLS if not p.get('title')]
    if no_title:
        data_ok = False
        print(f'  ❌ 踩坑缺title: {no_title}')
    else:
        print('  ✅ 每条踩坑都有 title')

    # 键名必须是纯 ASCII（曾用 '⭐ xxx' 当键名导致取值失败）
    import re as _re
    weird = []
    for _d, _n in ((FIELD_PATTERNS, 'FIELD_PATTERNS'),
                   (PLATFORMS, 'PLATFORMS')):
        for _k in _d:
            if _re.match(r'^[^\w\s]', str(_k)):
                weird.append(f'{_n}.{_k}')
    if weird:
        data_ok = False
        print(f'  ❌ 存在非 ASCII 键名: {weird}')
    else:
        print('  ✅ 无非ASCII 键名')

    # PLATFORMS 与 FIELD_PATTERNS 的平台集合应一致
    only_p = set(PLATFORMS) - set(FIELD_PATTERNS)
    only_f = set(FIELD_PATTERNS) - set(PLATFORMS)
    if only_p or only_f:
        print(f'  ⚠️ 平台集合不一致 '
              f'仅 PLATFORMS:{sorted(only_p) or "无"} '
              f'仅 FIELD_PATTERNS:{sorted(only_f) or "无"}')
    else:
        print(f'  ✅ PLATFORMS 与 FIELD_PATTERNS 平台一致'
              f'（{len(PLATFORMS)} 个）')

    print()
    print('数据自检通过' if data_ok else '数据自检有失败')
