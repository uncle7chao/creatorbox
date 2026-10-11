# CreatorBox 开发方案 v3

> **本版基于 2026-10-05 的10 个开源项目源码级调研 + 全链路实测重写**
> v2 及更早版本的技术判断有三处根本性错误，本版已全部推翻并给出实测依据。

---

## 零、本版推翻的三个错误假设

写在前面的不是免责声明，是**这轮调研的实际产出**。我前两轮用推测代替实测，参数层面的细节决定了架构。

| 错误假设 | 实测结果 | 根因 |
|---|---|---|
| "抖音必须用Playwright 浏览器" | **纯 HTTP 79MB 内存跑通，0.6–1.3s** | 抖音 v2 接口根本不需签名，我之前参数写错了 |
| "B站必须 ffmpeg 合并音视频" | **`fnval=0` 返回单文件，零合并** | 用了 `fnval=16`(dash) 才需要合并 |
| "抖音清晰度上限 720P" | **`uri + ratio=1080p` → 真1920×1080** | `bit_rate` 数组最高只到 720P，但有 play 接口 |

### ① 抖音 v2 接口：我把参数写错了

之前测 `slidesinfo` 用的是：
```
/web/api/v2/aweme/slidesinfo/?aweme_id={id}&aweme_type=0
                                    ^^^^^^^^^^ 单数
```
返回 `status_code:0` + `aweme_details:null`，我据此判定"通道已关闭"。

读 parse-video-py 源码发现用的是**数组格式**：
| 参数 | 响应长度 | aweme_details |
|---|---|---|
| `aweme_ids=%5B{id}%5D` | **65122 B** | ✅ FOUND |
| `aweme_id={id}`（我之前） | 260 B | null |

**这个接口免 cookie、免签名、免 a_bogus**，只要一个 iOS UA。

### ② detail 接口：我归因错了

我此前"真实 cookie + a_bogus"失败，归因 TLS指纹。读 uvd 源码发现是三个反直觉点：

| 参数 | 我之前 | 正确做法 |
|---|---|---|
| msToken | 真实值 | **空字符串** |
| Cookie | 4 个（ttwid/s_v_web_id/odin_tt/passport_csrf_token） | **只带 ttwid**（多带触发风控） |
| User-Agent | Chrome **140** | Chrome **90.0.4430.212**（越旧越安全） |

照改后视频与图集**全部成功**。

### 教训

**涉及第三方平台的技术方案，必须先跑通再定架构。** 参数名、UA 版本、cookie 数量这类细节，会直接决定"需不需要浏览器"这个架构级问题。

---

## 一、10 个项目的架构范式对比

### 项目分类（先纠正一个我自己的分类错误）

我之前把 10 个项目当同类比较，这是错的：

| 项目 | 类别 | 平台数 | 自研解析器 | 底层引擎 |
|---|---|---|---|---|
| **parse-video-py** | 解析器集合 | **25 视频 + 5 图集** | ✅ 25 个独立文件 | httpx |
| **parse-video (Go)** | 同上 | 22 + 火山 | ✅ 23 个 .go | go-resty |
| **video-parser** | 下载服务 + AI 抽帧 | 8 | ✅ 8 个 downloader | requests + bs4 |
| **m3u8-dl** | m3u8 下载器（含轻解析） | 3 | ✅ 3 个 TS | Node fetch |
| **uvd** | FastAPI 服务 | **1**（仅抖音） | ✅ 仅抖音 | httpx + gmssl |
| **VnaSeek** | 下载器 | yt-dlp 全平台 | ❌ 无 | yt-dlp |
| **Yeguo-IDM** | 桌面下载管理器 | yt-dlp 全平台 | ❌ 无 | yt-dlp |
| **phlsM3U8_downner** | 纯 m3u8 库 | **0** | ❌ 无 | aiohttp |
| **kitty** | 影视源聚合 | CMS 源 | N/A | TS |
| **TVHelper** | 多源聚合层 | CMS 源 | N/A | Go |

⚠️ **拿 VnaSeek「yt-dlp 支持 1000 平台」比 parse-video-py「25 平台」是不公平的** —— 前者是下载器，后者是解析器集合。

### 三种范式的取舍

| | A. 解析器集合<br/>(parse-video-py) | B. 下载器封装<br/>(VnaSeek) | **C. 混合架构<br/>（我们要做的）** |
|---|---|---|---|
| **平台广度** | ✅ 25+ | ✅ 无限 | ✅ 逐步扩展 |
| **无水印能力** | ✅ 可控 | ❌ yt-dlp 常拿不到 | ✅ 可控 |
| **改版韧性** | ❌ 无降级 | ⚠️ 靠 yt-dlp 更新 | ✅ 三级降级 |
| **成本** | ✅ 纯 HTTP | ⚠️ 服务端双倍带宽 | ✅ 纯 HTTP |
| **可否商用** | ✅ MIT | ❌ VnaSeek 无授权 | ✅ 自研 |

### 为什么不能直接用 yt-dlp

**「无水印」是我们的核心卖点，不能外包给通用引擎。** 但 yt-dlp 的平台覆盖广，值得借鉴它的封装思路。

---

## 二、目标架构：三层混合

```
第 1 层 · 域名路由
    解析器数组 + 依次尝试 + 首个成功即用
    （借鉴 parse-video-py 的路由表 + TVHelper 的订阅链思想）
         ↓
第 2 层 · 三级降级
    L1  免签名 API（抖音 v2 slidesinfo）    0.6s
    L2  a_bogus 签名（抖音 detail）          1.0s
    L3  浏览器兜底（改版时排查用，默认关闭）
         ↓
第 3 层 · 能力声明
    每个平台返回 dash / need_proxy / anonymous 等字段
    客户端读字段决定怎么处理，不写死业务逻辑
```

### 第 1 层：域名路由（借鉴两个项目）

parse-video-py 的路由表是硬编码 dict，我要改成**可配置 + 依次尝试**：

```python
# parsers/__init__.py
PARSERS = [
    DouyinPureParser(),      # 抖音
    BilibiliPureParser(),    # B站
    HaokanParser(),          # 好看视频
    WeiboParser(),           # 微博
    # ... 新增平台只需 append 一个实例
]

def pick(url: str):
    """依次尝试，首个 match 的解析器胜出"""
    for p in PARSERS:
        if p.match(url):
            return p
    return None
```

**借鉴 TVHelper 的两点**（GPL-3.0，只读设计不抄代码）：
1. **依次尝试机制** —— 多个源订阅，第一个成功的作主源，后续合并
2. **类型宽容解码** —— 上游 JSON 字段类型不可信，`UnmarshalJSON` 要对 bool/string/number 三形态都接受

### 第 2 层：三级降级（核心改进）

**这是我们相对所有调研项目的核心优势** —— parse-video-py 是"接口挂了直接失败"，我们是三级降级 + 质量监控。

| 级| 通道 | 抖音耗时 | 何时启用 |
|---|---|---|---|
| L1 | v2 slidesinfo（免签名） | 0.6s | 默认 |
| L2 | detail + a_bogus（ttwid） | 1.0s | L1 失败 / 图集 |
| L3 | Playwright | 3–10s | 改版排查（`CB_BROWSER_FALLBACK=1`） |

**L3 默认关闭** —— 79MB 内存跑生产，改版时临时开启排查。

### 第 3 层：能力声明（客户端可编程）

每个平台返回的字段让客户端知道该怎么处理：

| 字段 | 含义 | 客户端动作 |
|---|---|---|
| `dash` | 是否音视频分离 | true → 不能直接存 |
| `need_proxy` | CDN 是否需白名单 | true → 走服务端中转 |
| `anonymous` | 是否匿名态| true → 清晰度受限 |
| `max_quality_free` | 免登录清晰度上限 | 引导会员 |
| `watermark_free` | 是否无水印 | false → 提示用户 |
| `quality_upgraded_via` | 清晰度怎么来的 | 灰度诊断 |

---

## 三、已验证的平台与手段

### 已跑通（实测）

| 平台 | 类型 | 手段 | 耗时 | 关键字段 |
|---|---|---|---|---|
| **抖音** | 视频 | v2 API + play uri 拼 ratio | **0.81s** | `bit_rate[].play_addr.url_list` + `play_addr.uri` |
| **抖音** | 图集 | detail + a_bogus | **0.84s** | `images[].url_list`（排除 `dy-water` 模板） |
| **B站** | 视频 | view + playurl(fnval=0) | **0.32s** | `data.durl[0].url` |

### 待接入（字段与手段已确认，免签名）

按优先级：

| 平台 | 手段 | 字段 | 难度 |
|---|---|---|---|
| **好看视频** | API `haokan.baidu.com/v?_format=json` | `data.apiData.curVideoMeta.playurl` | 🟢 最低 |
| **西瓜** | SSR 正则 `_ROUTER_DATA`（与抖音同构） | `video.play_addr.url_list[0]` + `playwm→play` | 🟢 |
| **微博** | API `h5.video.weibo.com/api/component` | `data.urls` 第一个 key（码率最高） | 🟡 |
| **皮皮虾** | API | `video.video_high.url_list[0].url` | 🟡 可能有水印 |
| **AcFun** | SSR `var playInfo` | `playInfo.streams[0].playUrls[0]`（**m3u8**） | 🟡 需 m3u8 下载 |
| **央视网** | SSR + API | `hls_url`（注释警告高码率被加扰会花屏） | 🟡 |
| **小红书** | SSR `__INITIAL_STATE__` | `video.media.stream.h264[0].masterUrl` | 🟡 结构脆弱 |
| **快手** | SSR `INIT_STATE` | `mainMvUrls[0].url` | 🟡 有硬编码 cookie |

### ⭐ 25 平台的手段分类（全部免签名）

| 手段 | 平台数 | 举例 |
|---|---|---|
| SSR 正则 | 6 | 抖音回退、西瓜、小红书、快手、AcFun、全民K歌 |
| API 接口 | 14 | 好看视频、度小视、微视、微博、腾讯(JSONP)、皮皮虾 |
| 双 API | 2 | B站(view→playurl)、新片场(SSR→二次API) |
| CSS 选择器 | 2 | 绿洲、美拍(base64 混淆 4 步) |

**关键认知：25 个平台全部不需要签名。** 我之前"解析必须逆向"的认知是错的。

### 两个独特技巧（已落地）

**① 清晰度拼接（来自 m3u8-dl `douyin-parser.ts:36`）**
```
play_addr.uri + /aweme/v1/play/?video_id={uri}&ratio=1080p&line=0  → 302
```
实测：`1080p` → **1920×1080**（31.9MB）；`720p` → 1280×720（23.2MB）

**② B站 fnval=0 而非16**
```
playurl?fnver=0&fnval=0&qn=80&bvid={}&cid={}&platform=html5
```
`fnval=0` 返回 **durl 单文件含音轨** → `dash:false`，**不需要 ffmpeg**
⚠️ Referer **必须**设为视频页自身，否则返回挑战页
⚠️ 代价：匿名上限 720P（要 1080P 需登录 Cookie）

---

## 四、平台健康度监控（生命线）

**这是纯解析路线的根本风险** —— 平台改版随时发生，没有这个看板就是用户流失几天才发现。

借鉴 TVHelper 的**源元数据设计**（`site.go:11-33`：`Timeout` / `Header` 配置在源上而非散落代码）。

### 每个平台采集的指标

```sql
CREATE TABLE platform_health (
    platform        VARCHAR(32) NOT NULL,   -- douyin/bilibili/haokan
    channel         VARCHAR(16) NOT NULL,   -- v2_api / a_bogus / api_durl
    ok_count        INT DEFAULT 0,
    fail_count      INT DEFAULT 0,
    avg_ms          INT,                -- 平均耗时
    last_success_at TIMESTAMP,
    last_fail_at    TIMESTAMP,
    last_error      TEXT,
    PRIMARY KEY (platform, channel)
);
```

### 告警阈值

| 指标 | 告警 | 自动降级 | 动作 |
|---|---|---|---|
| 单平台成功率 <70% | ✅ 告警 | — | 运营介入适配 |
| 成功率 <40% | ✅ 告警 | ✅ 自动降级 | 只显示"已验证平台" |
| 连续失败 5 次 | ✅ 告警 | — | 触发浏览器兜底排查 |
| 平均耗时 >5s | ⚠️ 观察 | — | 检查平台响应 |

### ⭐ 域名自适应注册表

**实测域名是有限可枚举的**，但平台扩容会新增：

| 平台 | 实测域名 | 是否稳定 |
|---|---|---|
| 抖音图集 | `p3-pc-sign.douyinpic.com` / `p9-` | 2 个，稳定 |
| 抖音视频 | `v95-aw-web.douyinvod.com` / `365yg.com` | 有编号但可枚举 |
| B站 | `cn-jsnt-ct-01-07.bilivideo.com` | 标准域名 |

```sql
CREATE TABLE cdn_domain_registry (
    platform   VARCHAR(32),
    host       VARCHAR(128),
    kind       VARCHAR(16),    -- image / video
    first_seen TIMESTAMP,
    last_seen  TIMESTAMP,
    in_whitelist BOOLEAN DEFAULT FALSE,
    UNIQUE (platform, host)
);
```
**每次解析自动登记新域名** —— 平台加节点时后台自动跟进，人工只需定期核对白名单。

---

## 五、成本结构（用实测数据重算）

### 实测文件大小

| 类型 | 大小 |
|---|---|
| 抖音 1080P（101 秒） | 31.9 MB |
| 抖音 720P（101 秒） | 23.2 MB |
| B站 720P（213 秒） | 49.6 MB |
| 抖音图集单张 | 0.46 MB |

### 成本对比（1000 DAU，每人每天 2 次保存）

| 内容 | 月流量 | 平台CDN直连 | 国内CDN中转 | 香港中转 |
|---|---|---|---|---|
| 抖音 720P | 1359 GB | **¥0** | ¥285 | ¥2719 |
| 抖音 1080P | 1869 GB | **¥0** | ¥393 | ¥3738 |
| B站 720P | 2906 GB | **¥0** | ¥610 | ¥5812 |
| 图集（8 张） | 7 GB | **¥0** | ¥1 | ¥14 |

### ⚠️ 我之前的 923 元错在哪

我算 `923 元`时用了三个假设：25MB/条、3000 DAU、每天 2 次保存 —— **只有单价是真实的**。

**关键结论：只有小程序需要中转。** 官网 H5 和 App 走平台 CDN 直连（白名单），带宽成本归零。

### 服务器成本（纯 HTTP 方案）

| 项 | Playwright 方案 | **纯 HTTP 方案** |
|---|---|---|
| 单实例内存 | 500MB–1GB | **79.4 MB** |
| 浏览器子进程 | 21 个（1.8GB） | **0 个** |
| 抖音视频耗时 | 3.0s | **0.6–1.3s** |
| B站耗时 | 10.5s | **0.3s** |
| 服务器规格 | 8C16G | **2C4G** |
| 月成本 | ¥1200–2000 | **¥100–700** |

### 起步成本

| 项 | 选型 | 成本 |
|---|---|---|
| API 服务 | 2C4G（纯 HTTP 无需 8C16G） | **¥700/月**（包年更低） |
| 带宽 | 纯 HTTP 不占带宽 | **¥0** |
| 域名 + SSL | `.com` + 免费 DV | ¥70–90/年 |
| 对象存储 | COS 轻量（可选） | ¥0–20/月 |
| **合计** | | **≈ ¥800/月起** |

**vs v2 方案的 ¥300–400/年** —— 差价在于我 v2 误判"带宽是主要成本"，实际上**纯 HTTP 后带宽成本归零，主要成本变成服务器本身**（但 2C4G 比 8C16G 便宜得多）。

---

## 六、里程碑（重排）

周期从 v2 的 10–12 周调整为 **8–10 周** —— 因为不需要浏览器，开发量大幅下降。

### M0 · 技术验证 ✅ 已完成
- [x] 抖音视频纯 HTTP（0.81s，含 1080P）
- [x] 抖音图集纯 HTTP（0.84s，8 张无水印）
- [x] B站纯 HTTP（0.32s，单文件无需 ffmpeg）
- [x] 许可证台账（5 个可商用 / 3 个不可 / 2 个无授权）

### M1 · 平台扩展（2 周）✅ 已完成 2026-10-05

- [x] 好看视频 —— 纯 HTTP，4 档 1080P（**实测不需要浏览器**，原判有误）
- [x] 微博 —— 纯 HTTP，3 档 1080P，112MB / 319s
- [x] AcFun —— 纯 HTTP + ffmpeg 合并，5 档 1080P+
- [x] 西瓜 —— 判定不可接入（PC 站已并入抖音精选，非技术问题）
- [x] **域名自适应注册表** —— `server/app/domains.py`
- [x] **平台健康度采集** —— `server/app/health.py`（三层监控）

**Gate 达成**：6 平台端到端 8/8 通过 · 域名表 3 可白名单 / 3 需中转 · 健康度 6/6 全绿

### M1 的结果与原计划出入

| 原计划 | 实际 |
|---|---|
| 好看视频「API，最简单」 | 需先访问首页拿 cookie（原记「需浏览器过滑块」，实测有误） |
| 西瓜（与抖音同构） | **已并入抖音精选**，独立平台不存在 |
| 新增 3 平台 | 变成 **5 ready**（多了 AcFun）+ **4 blocked** |
| —— | 快手因反爬滑块不接入；小红书需 xsec_token；六间房是直播 |

### M1 顺带产出（v3 未列但必需）

- `server/app/m3u8_merge.py` —— m3u8 合并（AcFun 必需，含重复分段预检）
- `server/app/ffmpeg_util.py` —— ffmpeg 定位与能力探测（4 级回退）
- **25 条踩坑记录**（6 条 critical），全部来自实测而非推测

### M1 沉淀的关键工程决策

1. **零浏览器依赖**：6 个平台全纯 HTTP，服务内存 ~80MB
2. **域名可枚举性决定架构**：B站 5 个视频 5 个子域 → 必走中转；
   好看视频 4 个视频同一域 → 可白名单（这张表驱动 M3）
3. **健康度要断言能力而非只看存活**：平台退化成只给 1 档时
   HTTP 仍是 200，只有断言 `options_count` 才能发现

### M2 · 官网 H5（2 周）
- [ ] 解析页（粘贴 → 解析 → 预览 → 下载）
- [ ] 结果页（视频/图集分支 + 清晰度选择）
- [ ] 免责页（合规必需）
- [ ] SEO 内容页（"抖音水印怎么去掉"这类长尾词）

**为什么先做官网而不是小程序**：
- 零审核风险（绕开 3.10/4.3/5.6 三条红线）
- 零带宽成本（不走白名单约束）
- 一周内能验证需求
- ⚠️ iOS Safari 不能直接存视频 → 需要引导"在浏览器中打开"

### M3 · 小程序（2–3 周）
- [ ] 微信登录 + 配额系统
- [ ] 广告位接入（激励视频 3 触点）
- [ ] 合规中心（3.10 硬要求）
- [ ] 域名白名单配置（域名自适应表驱动）

**Gate：提审通过**

### M4 · 商业化闭环（2 周）
- [ ] 9.9 订阅（不限次数 / 1080P / 批量 / 无广告）
- [ ] 支付接入（小程序端受iOS 虚拟支付限制，主战场放App）
- [ ] 管理后台（平台健康度 + 广告收益 + 投诉工单）

### M5 · App（延后，5–6 周）
- [ ] Flutter + PlatformChannel
- [ ] 端侧零流量，天然零带宽成本

---

## 七、功能矩阵（重定）

### 核心定位调整（重要）

**竞品魔音工坊的「一键解析」是纯链接解析**（读其知识手册确认：粘贴链接 → 下载），**没有像素级处理**。

但我们 v2 方案里把定位搞错了两轮。最终定位：

> **不是"帮你绕过水印拿到原片"（魔音已做，上市公司免费功能）**
> **而是"不管平台怎么改版，都能给你拿到干净素材"（三层降级 + 快速跟版）**

**护城河不在功能，在韧性。**

### 功能清单

| 功能 | 优先级 | 说明 |
|---|---|---|
| 链接解析（视频） | 🔴 P0 | 已跑通，扩展平台 |
| 链接解析（图集） | 🔴 P0 | 已跑通 8 张 |
| 多清晰度选择 | 🔴 P0 | 720P / 1080P |
| **批量解析** | 🔴 P0 | **会员核心卖点** —— 自媒体人一次要几十条 |
| 平台健康度看板 | 🔴 P0 | **生命线**，改版预警 |
| 域名自适应 | 🟡 P1 | 白名单自动跟进 |
| 好看视频/西瓜/微博 | 🟡 P1 | 字段已知免签名 |
| AcFun/央视 m3u8 | 🟢 P2 | 需 m3u8 下载器 |
| 9.9 订阅 | 🟡 P1 | 不限次数 + 批量 + 1080P |
| 小红书/快手 | 🟢 P2 | 结构脆弱，优先级低 |
| ~~App 端AI 净化~~ | ❌ | **已删除** —— 纯解析路线不需要 |

### 会员权益设计（关键）

**不能只放"更高清"** —— 免费拿到的是干净原片，画质差距感知弱。必须放非画质刚需：

| 权益 | 免费 | 会员 |
|---|---|---|
| 解析次数 | **不限** | 不限 |
| 视频保存 | 每日 2 次 | **不限** |
| 图集保存 | 每月 3 次 | 不限 |
| **批量解析** | 每日 1 条 | **不限** ⭐ |
| 清晰度 | 720P | **1080P** |
| 广告 | 有 | 无 |
| 历史记录 | 7 天 | 永久 |

**批量解析是"值不值 9.9"的分界线** —— 免费额度根本不够自媒体人用。

---

## 八、许可证红线（合规必需）

| 项目 | 许可证 | 可商用 |
|---|---|---|
| parse-video-py | MIT | ✅ |
| parse-video (Go) | MIT | ✅ |
| m3u8-dl | MIT | ✅ |
| phlsM3U8_downner | MIT | ✅ |
| video-parser | MIT | ✅ |
| kitty | ISC（仅声明，无文件） | ⚠️ 存疑 |
| **Yeguo-IDM** | **AGPL-3.0** | ❌ 闭源服务触发源码开放 |
| **TVHelper** | **GPL-3.0** | ❌ 非开源即侵权 |
| **uvd** | README 写 MIT但无文件 | ❌ 无授权 |
| **VnaSeek** | 无| ❌ 无授权 |

### 已在工程中处理

`server/app/parsers/abogus_ref.py` 是从 uvd 复制的 a_bogus 实现，其溯源：
```
来源: Evil0ctal/Douyin_TikTok_Download_API (Apache 2.0)
原始: JoeanAmier/TikTokDownloader (GPL 3.0)
```
- **已保留出处声明**
- SM3/RC4 算法本身不受版权约束（公开算法）
- ⚠️ 风险在 payload 拼装与字母表表达形式
- **建议**：正式商用前让法务确认，或照算法思路自己实现

---

## 九、工程现状

```
server/
├── app/
│   ├── main.py                    ← Pool 已重构为三级降级
│   ├── config.py                ← ENABLE_BROWSER_FALLBACK 默认关
│   ├── cache.py                   ← Redis + 内存双层
│   ├── capabilities.py            ← 平台能力矩阵
│   └── parsers/
│       ├── douyin_pure.py         ← 三级通道（v2/a_bogus/play-api）
│       ├── bilibili_pure.py       ← API 路线（fnval=0）
│       ├── abogus_ref.py          ← a_bogus 签名（已标注出处）
│       ├── douyin.py              ← Playwright 兜底（保留）
│       ├── bilibili.py            ← Playwright 兜底（保留）
│       └── signed_platforms.py    ← 小红书/快手（未启用）
├── tests/
│   └── test_normalize.py          ← 16 项断言
└── requirements.txt               ← playwright 已改为可选
```

### 部署

```powershell
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
⚠️ **不需要 `playwright install`** —— 默认不开浏览器。改版排查时才用 `CB_BROWSER_FALLBACK=1`。

---

## 十、待你决策的三件事

1. **平台扩展顺序** —— 我建议好看视频 → 西瓜 → 微博（都免签名、字段已确认），但小红书需求最大只是结构脆弱。**要先做哪类？**

2. **官网优先还是小程序优先** —— 官网零风险零成本但没广告，小程序有流量主但要过审。**我的建议是官网先跑需求**，但广告变现要等小程序。

3. **H5 的 iOS 限制怎么处理** —— Safari 不能直接存视频到相册。选项：A 只做 Android 体验好 / B 引导"在浏览器中打开" / C 小程序做 iOS 兼容。**这影响 H5 的转化率设计。**

---

## 附：给未来的自己

- **涉及第三方平台，先跑通再定架构** —— 参数名、UA 版本、cookie 数量都会决定架构级结论
- **字段语义不能靠字面猜** —— `dy-water` 我理解成 "watermark removed"，实际是"加上水印"，必须下载后肉眼看
- **成本估算里的假设必须标出来** —— 923 元那个数字只有单价是真的，其余三个参数都是我拍的
- **落地后必须看效果** —— v3 方案的 79MB / 0.6s 都是实测，不是估算