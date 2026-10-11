# 归档：M1 平台接入进度（2026-10-05 第十一轮及之前的旧章节）

> 这些是前几轮的原始实测记录，**结论已被后续轮次修正**，保留作依据。
> 现行结论请看  顶部的新章节。

> 已修正的关键结论：
> 1. 好看视频「需浏览器过滑块」→ **错**，纯 HTTP 即可（见 P11）
> 2. 好看视频分辨率「1440x1080」→ **错**，4 档最高是蓝光 1080P
> 3. 腾讯视频「从清单移除」已执行，替换位是搜狐视频（已接入）
> 4. 六间房「可做」→ **错**，实测是直播平台

---


## 逐平台实测详情

### ✅ 好看视频 —— 完全可用（我之前的"已下线"判断是错的）

**⚠️ 先纠正我的错误结论**：我之前看到 `errno: 101007` + `web_hkoffline` 就断定"平台已下线"。**这是错误的推断** —— 平台活着，只是我没通过验证。

#### 平台确实活着

| 检查 | 结果 |
|---|---|
| 首页 `haokan.baidu.com` | HTTP 200，**56608 字节**，`vid` 出现 **399 次** |
| 首页链接格式 | `/v?vid={19位数字}&tab=recommen...` |
| 百度搜索"好看视频" | 95 处匹配 |
| 备用域名 `haokan.hao123.com` | HTTP 200，53124 字节，9 个 vid |

#### 真正的原因：滑块验证

纯 HTTP 请求 `/v?vid=xxx` 返回 `{"errno": 101007, "error": "未知错误"}`，而页面 state 里带 `pagepd: "web_hkoffline"`。

⚠️ **我误读了**：这个 `hk` 是"**好**看"的拼音首字母，不是"下架"。

浏览器打开后，正文明确显示：
> **「好看安全验证 · 请完成下方验证后继续操作」**
> 「拖动左侧滑块使图片为正」

**是未通过滑块验证的降级页，不是下架页。**

#### 浏览器内 API 完全可用（4/4 成功）

| vid | errno | 标题 |
|---|---|---|
| 1688233510589355861 | ✅ 0 | 1953年，一位抗美援朝归来的志愿军女战士… |
| 1615713059572946930 | ✅ 0 | 惊魂寻宝队和画中女郎并肩作战 |
| 1891980261675370327 | ✅ 0 | 男女在一起后，为什么女人非常冷淡 |
| 16481085785828018426 | ✅ 0 | 雨露要接三个孩子回家照顾… |

#### 4 档清晰度全部下载成功，1080P 可用

`curVideoMeta.clarityUrl` 有 4 档，**全部实测下载成功**：

| 档位路径 | 体积 | HTTP | MP4 |
|---|---|---|---|
| `/cae_h264/`（标清） | 1.5 MB | ✅ 200 | ✅ |
| `/hd/cae_h264/` | 2.3 MB | ✅ 200 | ✅ |
| `/sc/cae_h264/` | 2.8 MB | ✅ 200 | ✅ |
| **`/1080p/cae_h264/`** | **6.2 MB** | ✅ 200 | ✅ |

**下载后实测：`1440×1080` / 25.6 秒 / 6MB，抽帧肉眼确认画面完全干净（无角标、无空漂、无水印）。**

#### 关键实现要点

```javascript
// ① 先逛首页建立会话 cookie
await page.goto('https://haokan.baidu.com/');
await page.waitForTimeout(5000);
// ② 再访问视频页过滑块
await page.goto('https://haokan.baidu.com/v?vid={vid}');
await page.waitForTimeout(7000);
// ③ 页面内 fetch（自动带全部 cookie）
```

⚠️ **playurl URL 不能截断** —— 我第一次取 `slice(0,150)` 导致签名不完整，纯 HTTP 下载返回 403。必须用完整 URL。

⚠️ **CDN 域名**：`vdept3.bdstatic.com`（`bdstatic` = 百度静态资源）

#### 结论

**好看视频 = 需要 Playwright，但值得。** 4 档清晰度 + 1080P + 4/4 成功率，是目前除抖音外质量最好的平台。

---

### ⛔ 西瓜视频 —— PC 站已并入抖音精选（不是"需浏览器"）

**双项目实现对比**（用户提示我去对比 10 个项目后发现关键差异）：

| | parse-video-py | parse-video (Go) |
|---|---|---|
| Cookie | **无**，只用随机 Android UA | **带 7 个硬编码 Cookie**（MONITOR_WEB_ID / ixigua-a-s / ttcid / BD_REF / __ac_nonce / __ac_signature / ttwid）|
| UA | 随机 | Chrome/79.0.3945.88 |
| 接口 | `m.ixigua.com/douyin/share/video/{id}?aweme_type=107&app=aweme` | 同 |
| 字段 | `loaderData["video_(id)/page"].videoInfoRes.item_list[0]` | 同（gjson 语法）|

**实测 Go 版 Cookie 方案**：

| 测试 | 结果 |
|---|---|
| 带 7 Cookie + Chrome79 | 首页 7717 → **61791 字节**（Cookie 有效）|
| 但内容是 | **App 下载引导页**（下载/APP/营业执照/ICP备案）|
| 分享页 `item_list` | **仍为 0 条** |

**⭐ 根本原因：PC 网页版已与抖音网页版合并**

实测证据：
| 检查 | 结果 |
|---|---|
| 首页 SPA 挂载点 | `id=root` / `__NEXT_DATA__` / `_ROUTER_DATA` **全为 0** |
| 首页链接总数 | **仅 9 个**：App 下载、隐私政策、ICP 备案 |
| 浏览器渲染后 title | **「西瓜视频APP官方下载_安卓版_iOS版」** |
| 移动端分享页 | HTTP 200 + `_ROUTER_DATA` 存在，但 `item_list: 0` |

**外部证据**：
- **2024-12-02 官方公告**：「西瓜视频宣布网页版全面升级，与抖音网页版合并，原西瓜视频不再独立运营，跳转至抖音网页版下的精选区」
- **2026-06 媒体报道**：「字节跳动将抖音、西瓜视频这两个产品的官网首页全部定向至抖音精选」（新浪财经/头条/读佳）

**结论**：西瓜视频作为独立平台**已不存在**。它不是"需浏览器"，而是**业务已合并**。

⚠️ **注意这是第 5 种误判形态**（新增 P8）：
> 平台合并后，URL 仍返回 HTTP 200 + `_ROUTER_DATA`，但业务字段为空。
> **只看状态码和字段存在性会误判为"可用"** —— 必须验证业务字段有实际内容。

---

### 🔶 微博 —— 接口验证通过，缺真实样本

**接口形态**（读源码确认）：
```
POST https://h5.video.weibo.com/api/component?page=/show/{oid}
Referer: https://h5.video.weibo.com/show/{oid}
Content-Type: application/x-www-form-urlencoded
body: data={"Component_Play_Playinfo":{"oid":"{oid}"}}
```
**取地址**：`data.Component_Play_Playinfo.urls` **第一个 key 的 value**（码率最高），前缀 `https:`；回退 `stream_url`

**实测**：
- 接口 HTTP 200，响应结构符合预期（`data.Component_Play_Playinfo` 可寻址）
- 我编的 oid 返回 `keys=EMPTY`（组件为空）→ **接口本身活着，只是 oid 无效**
- 首页 `h5.video.weibo.com` 只有 800 字节，取不到真实 oid

**⏳ 阻塞点**：需要一个**真实的微博视频链接**才能完成验证。

**图集接口**（待做）：
```
GET https://m.weibo.cn/statuses/show?id={post_id}
Referer: https://m.weibo.cn/
X-Requested-With: XMLHttpRequest
取 data.pics[i]  按 large → original → bmiddle → url 顺序取首个
```

---

### ⛔ 腾讯视频 —— getinfo 接口已全面要求登录（用户指定要接，但实测不可行）

**接口形态**（读源码确认）：
```
GET https://vv.video.qq.com/getinfo
    ?vids={vid}&platform=101001&otype=json&defn=shd
返回: JSONP，剥掉 QZOutputJson= 前缀和尾部 ; 后 parse
取址: vl.vi[0].ul.ui[0].url + fn + ?vkey={fvkey}
封面: https://puui.qpic.cn/vpic_cover/{vid}/{vid}_hz.jpg/496
```

**vid 提取**：
- `m.v.qq.com/x/m/play?vid={vid}` → 查query 的 vid
- `v.qq.com/x/cover/{vid}.html` → 正则 `/x/(?:page|cover)/(?:[^/]+/)?(\w+)\.html`

**实测过程**：

| 测试 | 结果 |
|---|---|
| 从 `v.qq.com` 首页抓到 8 个真实 vid | `mzc002003kpyd2m` 等 ✅ 抓取成功 |
| 4 个 vid × 3档 defn（shd/hd/fhd）| 全部 `em:61` |
| 换 5 种 platform（101001/101006/1102/0/10200）× 5 种 defn | 全部失败 |
| 换 Referer（v.qq.com / m.v.qq.com）| 全部 `em:61` |
| m.v.qq.com 体系的 vid（`zc0030ay0dbqx`）| 同样 `em:61` |
| **真实浏览器内 fetch（带完整 Cookie）** | **`em:61`** |

**错误详情**：`{"em":61,"exem":1,"msg":"该内容暂不可观看","code":"61.1"}`

**⭐ 关键判定**：
- 页面本身**能正常打开**（标题：「先导片上：丘比特集结，杨超越元老回归」，`pg.url()` 正常）
- 但 `getinfo` 接口即使在**真实浏览器上下文 + 完整 Cookie** 下仍返回 `em:61`
- **结论：平台主动关闭了免登录解析接口，不是参数问题**

⚠️ 这类"页面能看但接口要登录"的情况，**纯 HTTP 和浏览器都无解**，只有登录 Cookie 才能过。

---

### 🔶 候选替代平台探测

| 平台 | 首页访问 | 数据完整度 | 手段 | 判断 |
|---|---|---|---|---|
| **AcFun** | HTTP 200，**153999 字节** | ✅ 页面完整 | SSR `var playInfo` → **m3u8** | 🟢 可做，需 m3u8 下载器 |
| **搜狐视频** | HTTP 200，**178116 字节** | ✅ 页面完整 | API `api.tv.sohu.com/v4/video/info/{id}.json` | 🟢 **可做，API 最简单** |
| **六间房** | HTTP 200，**867438 字节** | ✅ 页面最完整 | API `v.6.cn/coop/mobile/index.php` | 🟢 可做 |
| **逗拍** | HTTP 200，3303 字节 | ⚠️ 疑似 SPA 空壳 | API `v2.doupai.cc/topic/{id}.json` | 🟡 待验证 |

**建议**：用**搜狐视频**（API 最简单）+ **六间房**（页面数据最丰富）替换。

---

## 平台清单调整建议

| 原编号 | 调整前 | 调整后 | 理由 |
|---|---|---|---|
| 4 | ~~好看视频（已下线）~~ | **保留** ✅ | **误判，实际完全可用（4/4）** |
| 5 | ~~腾讯视频（需登录）~~ | 删除 | `em:61` 无解 |
| — | — | **+ 搜狐视频** | API 最简单，首页 178KB 完整 |
| — | — | **+ 六间房** | 页面数据最丰富，867KB |

**调整后清单（10 个）**：

| # | 平台 | 状态 | 备注 |
|---|---|---|---|
| 1 | 抖音视频 | ✅ 完成 | 0.81s / 1080P |
| 2 | 抖音图集 | ✅ 完成 | 0.84s / 8 张无水印 |
| 3 | B站 | ✅ 完成 | 0.32s / 单文件 |
| 4 | **好看视频** | ✅ **完成** | **4/4 成功 / 1440×1080，需 Playwright** |
| 5 | 微博视频 | 🔶 待样本 | 接口通 |
| 6 | 微博图集 | 🔶 待样本 | 接口通 |
| 7 | 西瓜视频 | ⛔ 已合并 | PC 站并入抖音精选 |
| 8 | 小红书 | ⛔ 需 xsec_token | 平台封死 |
| 9 | 快手 | ⏸ 待验证 | 推荐流 CSR |
| 10 | **搜狐视频** | 🆕 待接入 | API 最简单 |

⚠️ **需要你确认是否接受这个调整** —— 或者你有其他想加的平台。

---

## 需要你提供的样本链接

我已尝试自行抓取（2026-10-05），结论是**这三个平台的真实链接无法自动获取**，原因如下。

---

### 🔶 我自己抓样本的结果

#### 微博 —— 页面全是 CSR 空壳

| 入口 | HTTP | 长度 | 抓到的 oid |
|---|---|---|---|
| `weibo.com/hot/video` | 200 | 9092 B | ❌ 0 个 |
| `m.weibo.cn/` | 200 | 9020 B | ❌ 0 个 |
| `www.weibo.com/tv/` | 200 | 9048 B | ❌ 0 个 |

三处都只有 9KB 左右 —— **是未登录的空壳页**，内容全部靠登录后 JS 加载。

#### 小红书 —— noteId 拿到了，但 xsec_token 拿不到（**这是硬阻塞**）

| 抓取方式 | 结果 |
|---|---|
| 纯 HTTP `explore` 页 | ❌ `__INITIAL_STATE__` 里 `noteDetailMap: 0 条` |
| 纯 HTTP 页面正则找 `xsec_token` | ❌ **0 个** |
| 真实浏览器 + DOM 查`a[href*=explore]` | ❌ **0 个带 token 的链接** |
| 真实浏览器 + 遍历 `INIT_STATE` | ✅ 拿到 **23 个 noteId**，但 **0 个 token** |
| 真实浏览器 + HTML 全文正则 | ❌ id=0, token=0 |

**⭐ 关键结论**：小红书从 2024 年起，笔记详情**必须带 `xsec_token`**，而 token **只在登录态下由客户端接口生成**。

源码 `video-parser/README.md:69` 的示例链接也带 `xsec_token=`，正说明这一点。

**这意味着小红书纯 HTTP 解析的路已被官方封死** —— 除非拿到用户登录后的 token。

#### 快手 —— 首页有 INIT_STATE 但无 photoId

| 检查 | 结果 |
|---|---|
| 首页 HTTP | 200，**335236 字节**（页面数据完整） |
| `window.INIT_STATE` | ✅ 存在，**262151 字节完整 JSON** |
| 顶层 keys | `tusjoh.0sftu0w0tztufn0tubsuvq-pckfdu.`（混淆后的命名空间） |
| `"id"` 字段 | 276 个（但是内部 ID，不是 photoId） |
| **递归找 `photoId`** | ❌ **None** |
| **递归找 `mainMvUrls`** | ❌ **None** |
| `short-video/` 链接 | ❌ 0 个 |

**结论**：快手推荐流是**CSR 异步加载**，SSR 的 INIT_STATE 里只有配置没有内容。

#### 皮皮虾 —— 站点规模太小

| 域名 | HTTP | 长度 |
|---|---|---|
| `h5.pipix.com` | 200 | **2414 B** |
| `www.pipix.com` | 200 | 21178 B |
| `api.pipix.com` | 404 | — |

平台已大幅萎缩，API 域名 404。

---

### 📌 仍然需要你提供样本

| 平台 | 需要什么 | 为什么我拿不到 |
|---|---|---|
| **微博** | 真实微博视频链接 | 未登录页面是 9KB 空壳 |
| **小红书** | **带 `xsec_token` 的完整链接** | token 只在登录态生成 |
| **快手** | 真实快手视频链接 | 推荐流 CSR，SSR 无内容 |
| **皮皮虾** | 真实视频链接 | 平台萎缩，首页仅 2.4KB |

⚠️ **注意小红书这一条**：普通分享链接（不带 token）**现在可能也解析不了** —— 如果用户是登录态分享的，token 就在链接里；如果是未登录时分享的，可能需要我们自己有登录态。

**这涉及一个产品决策**：是否要维护一个**小红书登录账号**用于解析？这有账号安全与合规成本。

---

## 🔴 一个更重要的判断

这轮测试暴露了平台的**共同演进方向**：

| 平台 | 变化 | 时间 |
|---|---|---|
| 腾讯视频 | getinfo 要求登录 | 接口收紧 |
| 小红书 | noteId 需配 xsec_token | 2024 起 |
| 快手 | 推荐流改 CSR | — |
| **西瓜** | **PC 站并入抖音精选** | **2024-12 公告** |
| 微博 | 未登录空壳 | — |

**规律：所有平台都在把"免登录解析"这条路封死。**

这印证了 v3 方案里那句「**护城河不在功能，在韧性**」—— 但也意味着：

⚠️ **纯 HTTP 解析的长期可持续性是风险，不是一劳永逸的。**

**建议的应对**：
1. **保持 Playwright 兜底能力**（v3 已设计，默认关闭但随时可开）
2. **平台健康度看板必须做** —— 改版预警是生命线
3. **考虑维护一个平台账号池**（成本换稳定性），但要评估合规风险

---

## 平台替换建议

好看视频已下线，建议从 10 个平台清单里换成：

| 候选 | 理由 | 风险 |
|---|---|---|
| **腾讯视频** | 源码确认走 JSONP，字段已知 | 有 vkey 签名，可能已失效 |
| **AcFun** | SSR `var playInfo`，字段已知 | 返回 m3u8，需下载器 |
| **搜狐/六间房/逗拍** | 简单 API | 小众，用户需求低 |
| **皮皮高笑** | video-parser 有实现 | 小众 |
| **西瓜视频** | 需求大 | 需浏览器，成本上升 |

**我的建议**：西瓜保留（用 Playwright，抖音解析器同构可复用），再补**腾讯视频**或**AcFun**顶上好看视频的位置。

---

## 工程影响

### 新增能力声明字段

```python
CAPABILITY = {
    'douyin': {
        'types': ['video', 'image'],
        'max_quality': '1080P',      # L3 uri+ratio 通道
        'anonymous': False,
        'browser': False,            # 纯 HTTP
    },
    'bilibili': {
        'types': ['video'],
        'max_quality': '720P',       # 匿名上限
        'dash': False,               # fnval=0 单文件
        'browser': False,
    },
    'haokan': {
        'available': False,
        'reason': '平台已下线 (web_hkoffline)',
    },
    'ixigua': {
        'types': ['video'],
        'browser': True,             # ⚠️ 需要 Playwright
        'note': '与抖音同构，可复用 normalize',
    },
    'weibo': {
        'types': ['video', 'image'],
        'browser': False,
        'note': '视频走 component，图片走 m.weibo.cn',
    },
}
```

### 服务配置需调整

```python
# 开启浏览器兜底（西瓜需要）
ENABLE_BROWSER_FALLBACK = True   # 西瓜接入时打开
```
⚠️ 打开后**服务内存从 79MB 涨到约 600MB** —— 这是西瓜带来的唯一成本。