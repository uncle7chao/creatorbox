# 国际平台解析方案（TikTok / X / YouTube / Facebook）

> 2026-10-11 · 配套《平台解析实现手段全解-25平台.md》
> 结论先行：**香港服务器无墙直连是竞品没有的天然优势**；TikTok 与 IYAMA 的 TikTok 电商业务战略对齐；
> 四平台按「 certainty」排序：X（现成实现）> TikTok（公共 API）> YouTube（yt-dlp 引擎）> Facebook（spike）。

---

## 一、为什么国际平台值得做（战略判断）

1. **服务器优势**：香港 43.159.141.17 直连 TikTok/X/YT/FB 无墙——国内服务器做不了，这是**结构性护城河**
2. **用户对齐**：IYAMA Studio 的 TikTok 电商陪跑业务，用户群就是 TikTok 卖家——保存自己的带货素材、下载竞品视频分析，是他们的日常工作流
3. **竞品空白**：国内解析小程序全部止步于国内平台；「支持 TikTok/X」是差异化卖点
4. **参考生态答案统一**：parse-video 系 10 个项目里，国际平台的解全部收敛到 **yt-dlp 兜底引擎**（uvd：抖音自研+其余 yt-dlp；VnaSeek：全 yt-dlp）——架构已被验证

---

## 二、四平台逐个拆解

### 2.1 X/Twitter 🟢 确定性最高（实现已就绪）

- **手段**：`cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token={token}`，无需登录
- **token 算法**：`(tweetId / 1e15) * π` 转字符串去掉 `0` 和 `.`（parse-video-py twitter.py 逐行拆解完成）
- **字段**：`mediaDetails[]` 视频过滤 `video/mp4` 取最高 bitrate；图片 `media_url_https`；支持 GIF/图集；t.co 短链 301 解析
- **直链可行性**：`video.twimg.com` **不锁 IP** → 302 直链方案直接可用
- **工作量**：**1 天**（实现已拆解到位，翻译成我们的解析器规范即可）
- **风险**：syndication 接口偶尔收紧 token 校验——失败时回退 yt-dlp 兜底

### 2.2 TikTok 🟢 用户价值最大（与 IYAMA 业务对齐）

三条实现路线（按推荐顺序）：

| 路线 | 原理 | 优点 | 风险 |
|---|---|---|---|
| **A. tikwm 公共 API**（推荐首发） | `POST https://www.tikwm.com/api/?url={分享链接}` 免 key 免签名，直接返回**无水印 HD/SD + 音乐** | 零逆向成本，社区维护 | 第三方依赖（限频/跑路风险）→ 需缓存 + 失败降级 |
| B. Web SSR | GET `tiktok.com/@user/video/{id}` → `__UNIVERSAL_DATA_FOR_REHYDRATION__` → `itemStruct.video.playAddr` | 不依赖第三方 | playAddr 部分带水印/地区锁定；需要维持 Cookie 池 |
| C. 移动端 API 逆向 | 抖音 a_bogus 的**加强版**（X-Argus/X-Gnexus/Ladon 多重签名） | 最彻底 | 逆向难度远超抖音 a_bogus，维护成本极高，**不做** |

- **直链可行性**：TikTok CDN（tiktokcdn*.com）**不锁 IP** → 302 直链可用
- **入口识别**：`vm.tiktok.com` / `vt.tiktok.com` 短链 302、`tiktok.com/@user/video/{id}`
- **工作量**：路线 A **1 天**（含失败降级到路线 B）
- **坑**：地区封锁（部分视频按 IP 地区返回不同内容——香港 IP 覆盖亚太区）；tikwm 有请求频率限制（~1 req/sec），高并发要排队

### 2.3 YouTube 🟡 唯一有架构坑的（IP 锁）

两条路线：

| 路线 | 原理 | 坑 |
|---|---|---|
| **yt-dlp 引擎**（推荐） | `yt_dlp.YoutubeDL(opts).extract_info(url, download=False)` 拿 formats | 引擎本身成熟，但 **YouTube 对抗持续**——yt-dlp 需要定期升级（`pip -U yt-dlp`），每次 YT 改版有 1-7 天失效窗口 |
| innertube API 直调 | POST `youtubei/v1/player`（ANDROID client context 绕签名） | streaming URL 带签名 decipher，要跟 player JS 的 `s` 参数算法——维护重，不推荐自研 |

**⚠️ 核心坑：googlevideo 直链 IP 锁**——innertube/yt-dlp 从**服务器 IP** 拿到的直链，很多情况下只对**同一 IP** 有效。我们 302 给用户手机 → 用户手机 IP 不同 → **403**。

应对三选一：
1. **服务端中转**（流式转发）——回到 VnaSeek 双倍带宽问题，❌ 不做
2. **只做解析信息 + 让用户在 PC/App 端下载**（App 端请求时用用户自己的网络走 yt-dlp → IP 一致）——✅ 符合「成本承担者」架构：**YouTube 解析信息小程序可看，文件下载放扩展端**
3. 试探 googlevideo 是否严格 IP 锁（部分场景只是 UA/Cookie 校验）——spike 验证后再定

**工作量**：yt-dlp 引擎集成 2-3 天（含 formats → 我们 meta 结构映射）

### 2.4 Facebook 🟡 不确定性最高（spike 先行）

- **现状**：FB 全面登录墙化——`mbasic.facebook.com` 的 `hd_src` 抓取是老路子，近年大量内容必须登录才能看源
- **可行路径**：登录 Cookie 池（与小红书同型架构）+ mbasic SSR；或第三方 API
- **风险**：FB 反爬激进，Cookie 池易封；用户量级存疑
- **建议**：**不做首发**——先 spike（半天验证 mbasic 现状），可行再立项

---

## 三、架构设计：国际解析域 + yt-dlp 万能兜底

```
/api/parse 请求进来
  ├─ 国内平台 → 现有自研解析器链（不动）
  └─ 国际平台 → 新命名空间 parsers/intl/
        ├─ x_pure.py        （syndication π-token，自研）
        ├─ tiktok_pure.py   （tikwm API → SSR 降级）
        └─ ytdlp_engine.py  （万能兜底：YT/FB/其他）★ 全部国际平台失败后的最终兜底
```

**yt-dlp 引擎集成要点**（参考 uvd `core/downloader.py:144-175` + VnaSeek `backend.py:353-369`）：
```python
ydl_opts = {
    "quiet": True, "no_warnings": True, "noplaylist": True,
    "socket_timeout": 15, "retries": 2,
    "http_headers": {"User-Agent": CHROME_UA, "Accept-Language": "en-US"},
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.sanitize_info(ydl.extract_info(url, download=False))
# info['formats'] → 映射我们的 options 结构（height/url/ext/filesize）
```
- `skip_download=True` 纯解析不落盘（与我们 302 架构一致）
- yt-dlp 是 **Unlicense（公有领域）**——无许可风险 ✅
- 维护动作：**每月 `pip -U yt-dlp`**（YT 对抗靠上游），加进运维看板健康探针（检测 yt-dlp 版本落后天数）

**域名注册表**：新增国际域（tiktok.com/tiktokcdn.com/twitter.com/x.com/twimg.com/youtube.com/googlevideo.com/youtu.be/fb.watch/fbcdn.net）——同时登记进封面代理白名单与微信审核收敛开关的「国际组」。

## 四、审核与合规

1. **小程序审核风险**：境外平台内容在国内小程序里是敏感项 → 所有国际平台入口挂**收敛开关**（提审时隐藏，过审后放开——与国内平台同一机制）
2. **正当用途叙事**：TikTok 卖家保存自己的带货素材/授权内容（IYAMA 陪跑业务场景），使用规范页已有声明基础上补「境外平台」条目
3. **版权责任**：与国内平台同一口径——用户自担，平台提供工具

## 五、排期与依赖

| 阶段 | 内容 | 工作量 | 依赖 |
|---|---|---|---|
| **P1** | X/Twitter 解析器（实现已拆解） | 1 天 | 无 |
| **P1** | TikTok 路线 A（tikwm）+ 路线 B 降级 | 1.5 天 | 验证 tikwm 从香港服务器可达与限频 |
| **P2** | yt-dlp 引擎 + YouTube | 3 天 | 服务器装 ffmpeg/yt-dlp；IP 锁 spike 结论 |
| **P3** | Facebook spike（mbasic 现状验证） | 0.5 天 | spike 可行才立项 |
| 横切 | 收敛开关覆盖国际组 + 域名表 + 封面代理白名单 + 探针样本池 | 0.5 天 | — |

**总计**：P1 两天拿到 X + TikTok 两个高价值平台；YouTube 和 FB 的取舍看 spike 结果。

## 六、明确不做

- TikTok 移动端 API 多重签名逆向（X-Argus/X-Gnexus）——成本失控
- YouTube 服务端流式中转——双倍带宽，违反成本承担者架构
- Facebook 登录 Cookie 池规模化——封号风险与维护成本不匹配（除非 spike 证明 mbasic 还活着）
