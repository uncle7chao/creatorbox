# CreatorBox 文档索引

>更新：2026-10-05 ｜ **当前有效方案：v3**
> ⚠️ **知识库以代码为准**：`server/app/knowledge.py` 是平台信息的唯一事实源，本索引只做导航。

---

## 🔴 先看这三个

| 文档 | 作用 |
|---|---|
| **[CreatorBox-开发方案v3.md](./CreatorBox-开发方案v3.md)** | **总纲** —— 架构、平台策略、成本模型、M0-M5 排期 |
| **[开源项目源码调研报告.md](./开源项目源码调研报告.md)** | 10 个开源项目的源码级拆解（平台字段、许可证红线） |
| **[M1平台接入进度.md](./M1平台接入进度.md)** | 10 个平台逐一实测结果 + 踩坑记录 |
| [_archive_M1旧章节.md](./_archive_M1旧章节.md) | ⛔ 归档：第十一轮及之前的旧实测记录（结论已被修正，仅作依据） |

---

## 📁 文档分层

### A. 方案与决策（当前有效）

| 文档 | 内容 |
|---|---|
| [CreatorBox-开发方案v3.md](./CreatorBox-开发方案v3.md) | ⭐ 总纲。含推翻了v2 的三处错误假设 |
| [开源项目源码调研报告.md](./开源项目源码调研报告.md) | 25 平台手段分类、字段路径、许可证台账 |
| [M1平台接入进度.md](./M1平台接入进度.md) | 平台实测状态、每个平台的卡点 |
| [小程序UI设计规范.md](./小程序UI设计规范.md) | 三屏设计稿 + 变现触点 + 硬约束 |
| [竞品-魔音工坊对标报告.md](./竞品-魔音工坊对标报告.md) | 竞品 23 篇手册全量抓取分析 |

### B. 技术验证记录（保留作为依据）

| 文档 | 关键结论 |
|---|---|
| [抖音解析可行性验证结论.md](./抖音解析可行性验证结论.md) | ⭐ 纯 HTTP 可行的决定性证据（Playwright 3s → 纯 HTTP 0.6s） |
| [图集解析验证报告.md](./图集解析验证报告.md) | `dy-water` 是"加水印"不是"去水印"的证据 |
| [解析服务实现报告.md](./解析服务实现报告.md) | FastAPI 封装、三级降级 |
| [解析链路实现方案.md](./解析链路实现方案.md) | 链路六步 + 完整代码 |
| [素材存储与带宽成本方案.md](./素材存储与带宽成本方案.md) | 存储方案对比、域名可枚举性 |
| [抖音解析技术验证报告.md](./抖音解析技术验证报告.md) | ⚠️ 该文档结论已被推翻，见下方"已作废" |

### C. 商业与运营

| 文档 | 内容 |
|---|---|
| [CreatorBox-商业模式设计.md](./CreatorBox-商业模式设计.md) | 免费额度+广告+9.9 订阅的成本模型 |
| [CreatorBox-管理后台方案.md](./CreatorBox-管理后台方案.md) | 运营后台模块（合规中心是硬要求） |
| [CreatorBox-功能取舍与矩阵.md](./CreatorBox-功能取舍与矩阵.md) | 魔音 14 项工具的取舍判断 |
| [竞品-魔音工坊手册抓取.md](./竞品-魔音工坊手册抓取.md) | 飞书知识库抓取方法与原文归档 |

### D. ⛔ 已作废（仅作历史记录，勿参考）

| 文档 | 被什么取代 |
|---|---|
| ~~CreatorBox-产品方案v2-纯解析.md~~ | → v3（三处技术错误） |
| ~~CreatorBox-开发蓝图与实施计划.md~~ | → v3 |
| ~~CreatorBox-手机版开发方案.md~~ | → v3（AI 净化路线已废弃） |
| ~~CreatorBox-双端方案与广告变现.md~~ | → v3（小程序/APP 定位已改） |
| ~~CreatorBox-云资源选型与成本重算.md~~ | → v3（带宽成本归零） |
| ~~抖音解析技术验证报告.md~~ | → 抖音解析可行性验证结论.md |

> **为什么作废**：v2 及更早版本基于"必须用浏览器解析"的假设，而 v3 实测证明纯 HTTP 即可（服务内存 79MB vs 500MB-1GB）。

---

## 💡 代码即知识

平台信息不要在文档里改，改这里：

| 文件 | 作用 |
|---|---|
| **`server/app/knowledge.py`** | ⭐ **唯一事实源** —— 平台注册表、字段路径、**25 条踩坑记录**、已知能力缺口 |
| `server/app/capabilities.py` | 已废弃，转发到 knowledge.py（兼容旧代码） |
| `server/app/domains.py` | 域名自适应注册表（驱动小程序白名单 + CDN 改版预警） |
| `server/app/health.py` | 平台健康度三层监控（探针 / 真实流量 / 能力断言） |
| `server/app/parsers/*.py` | 各平台解析器实现 |
| **`server/app/meta.py`** | ⭐ **元信息规范层** —— 7 平台字段名统一（标题/文案/封面/作者/时长/统计/标签）|
| `server/app/m3u8_merge.py` | m3u8 → mp4 合并（AcFun 必需，含重复分段预检） |
| `server/app/ffmpeg_util.py` | ffmpeg 定位与能力探测 |
| `server/app/parsers/normalize_douyin.py` | 抖音归一化纯函数（无浏览器依赖，供全部抖音通道 + 测试共用） |

### 服务接口一览

```
POST /api/parse                    解析（统一入口）
POST /api/batch                    批量解析（会员功能）
POST /api/merge                    m3u8 → mp4 服务端合并
GET  /api/ffmpeg                   ffmpeg 能力自检（含 GPL 许可提示）
GET  /api/health                   进程健康 + 降级预警
GET  /api/health/platforms         ⭐ 平台健康度看板（三层）
POST /api/health/platforms/probe   立即跑一轮探针（排障）
GET  /api/domains                  ⭐ 域名注册表 + 微信白名单清单
POST /api/domains/classify         判定某 URL 能否直连
GET  /api/knowledge/platforms      平台注册表
GET  /api/knowledge/fields/{name}  某平台字段路径速查
GET  /api/knowledge/pitfalls       已踩过的坑
```

### 域名可枚举性（M3 白名单的依据，实测）

| 平台 | 实测 CDN | 白名单 | 原因 |
|---|---|---|---|
| 抖音 | `p3/p9-pc-sign.douyinpic.com` | ✅ | 只有 2 个 |
| 好看视频 | `vdept3.bdstatic.com` | ✅ | 4 个视频全同域，稳定 |
| 微博 | `f.video.weibocdn.com` | ✅ | 单域名 |
| **B站** | `upos-sz-estgoss` / `cn-zjjh-ct-04-05` / … | ❌ | **5 个视频 5 个子域** |
| 搜狐 | `data.vod.itc.cn` | ❌ | 域名固定但需合并/有截断 |
| AcFun | `tx-safety-video.acfun.cn` | ❌ | 域名固定但只有 m3u8 |

**合计 15 个域名 / 上限 20 → 可配置**（`GET /api/domains` 可导出清单）

### 当前接入状态（2026-10-05）

| 状态 | 平台 |
|---|---|
| ✅ ready | 抖音（视频+图集）、B站、好看视频、微博、**AcFun**、**小红书**（图集+视频）、**快手**（⭐走 m.gifshow.com 绕开反爬） |
| 🔶 partial | **搜狐视频**（>30s 只有试看片段，m3u8 也是重复段，合并无效） |
| ⛔ blocked | 腾讯视频（需登录）、西瓜（已并入抖音精选）、六间房（是直播平台） |

**服务零浏览器依赖**：`engine=pure_http`，**6 个平台全部就绪**。

### 🔧 m3u8 合并服务（AcFun 必需）

| 文件 | 作用 |
|---|---|
| `server/app/ffmpeg_util.py` | 定位 ffmpeg（4 级回退）+ 能力探测 |
| `server/app/m3u8_merge.py` | m3u8 → mp4 合并，**含重复分段预检** |
| `POST /api/merge` | 合并接口 |
| `GET /api/ffmpeg` | 能力自检（含 GPL 许可提示） |

**实测**：AcFun 299.01s / 150MB，`-c copy` 纯 remux 仅 **5.4 秒**，
`duration_ratio=1.0`，faststart 生效。

⚠️ **ffmpeg 许可**：imageio-ffmpeg 自带二进制是 **GPL 构建**。
当前仅以子进程调用（通常不构成衍生作品），可用 `CB_FFMPEG_PATH` 替换
为合规版本。**上线前请法务确认。**

⚠️ **重复分段预检（P22）**：搜狐的 m3u8 写着 12 段、EXTINF 合计 76.85s，
但 **12 段 MD5 完全相同** —— 全是同一个 30 秒试看内容。
ffmpeg 合并会得到 6 分钟垃圾文件**且退出码 0、不报错**。
所以合并前必须自己算哈希，检测到重复直接拒绝。

### 知识库 API

```bash
GET /api/knowledge/platforms      # 平台注册表 + 状态汇总
GET /api/knowledge/fields/douyin # 某平台字段路径速查
GET /api/knowledge/pitfalls      # 已踩过的坑
```

### 直接读（Python）

```python
from app.knowledge import PLATFORMS, FIELD_PATTERNS, PITFALLS, match_platform

match_platform('https://v.douyin.com/xxx/')   # → 'douyin'
FIELD_PATTERNS['douyin']['video']['L1_api']    # → 接口+字段+坑
```

---

## ⚠️ 必读的 5 条 critical 踩坑记录

| ID | 坑 | 规则 |
|---|---|---|
| **P2** | 接口返回错误 ≠ 平台不可用 | **凡"接口不通"必须先在浏览器里看页面正文** |
| **P4** | 页面能打开 ≠ 接口可用 | 判断必须基于**直接调核心接口** |
| **P8** | 接口存在 ≠ 业务还在 | 必须验证**业务字段有实际内容**（如 item_list 长度 > 0） |
| **P11** | 「必须用浏览器」常是被自己的操作步骤骗出来的 | 判定前**分离变量**：建立会话 / 访问详情页 分开测 |
| **P12** | 平台给的「下载字段」可能只是试看片段 | 必须**读容器时长**（MP4 读 mvhd）与声明值比对 |

### 另外 4 条也很有用

| ID | 坑 | 规则 |
|---|---|---|
| **P1** | 字段标记不能靠字面猜 | `dy-water` 是"加水印"，必须下载验证 |
| **P3** | 参数格式差异决定成败 | `aweme_ids=[]` 数组 vs `aweme_id=` 单数 |
| **P13** | 接口已给权威字段，别靠 URL 路径反推 | 好看视频 4 档全被我猜成 360P |
| **P14** | 开源项目收录 ≠ 业务形态匹配 | 六间房被当点播收录，实测是直播 |
| **P15** | 参数缺失会被伪装成「资源不存在」 | 搜狐缺 api_key 就报"视频不存在" |
| **P16** | 页面编码不统一 | 搜狐 GB18030 / B站 gzip / 抖音 UTF-8 |
| **P17** | 「第一个元素就是最优」是巧合不是规律 | 微博改从 label 解析高度排序，不依赖下标 |
| **P18** | 字节串计数判断 MP4 音轨会误判 | 必须递归遍历 box 树看 hdlr |
| **P19** | 接口会主动告诉你正确字段名 | 快手 GraphQL 乱写字段名，它回"Did you mean visionVideoDetail?" |
| **P20** | 业务 ID 前缀在短链与详情页可能不同 | AcFun `/v/?ac=48890260` 能用但 `/v/48890260` 502 |
| **P21** | 「JSON 套 JSON」与「数组伪装成对象」 | AcFun ksPlayJson 要 parse 两次；adaptationSet 是数组 |
| **P22** | **m3u8 分段可能全是同一份内容重复** | 搜狐 12 段 MD5 全同；ffmpeg 合并退出码 0 不报错，必须自己预检哈希 |
| **P27** | 「有图」≠「图集」，类型判据选错会静默降级 | 小红书视频笔记被误报成 1 张图 |
| **P28** | 同名字段单位可能不一致 | duration 262（秒）vs 261389（毫秒） |
| **P29** | 纯数据 bug 只能靠自检发现 | severity/level 字段名不统一 → 级别静默丢失 |
| **P30** | 「数字」与「展示文本」要分两个字段 | `int("29.8万")` 直接崩；AcFun 有 fanCount/fanCountValue 两版 |
| **P31** | 字段名不统一 → 必须有规范化层 | 播放量有 4 种叫法，前端要写 7 套判断 |
| **P32** | **反爬只覆盖主站，备用域名可能没跟上** | 快手 www 被滑块拦死，m.gifshow.com 完全畅通 |
| **P33** | 测试脚本写死端口 → 静默打到别的服务 | 表现为「新用例报成别的平台解析失败」，极难定位 |
| **P34** | 「平台没给这个字段」可能只是你只看了接口 | 小红书视频标题在**分享文案**里，不在 `note.title` |
| **P23** | ffmpeg 用 `-c copy` 而非转码 | 155MB/5分钟仅 5.4 秒；必须加 `+faststart` |
| **P24** | 「读源码」≠「读完所有项目的同一平台实现」 | 微博只读一个项目就动手，漏了 m3u8-dl 用的另一个域名 |
| **P25** | 同一接口常有多个域名，门槛差一个登录态 | 微博 h5 域名匿名可用 / 主站域名强制要 cookie |

**我在这 7 条 critical 上连续判断错了 3-4 次** —— 接入新平台前先读完。
完整 25 条见 `GET /api/knowledge/pitfalls` 或 `knowledge.py` 的 `PITFALLS`。

---

## 🧪 验证脚本（都可独立运行）

```bash
# 先启动服务
cd server && python -m uvicorn app.main:app --port 8000

cd tests
python e2e_regression.py            # 六平台端到端（需服务已启动）
python test_merge_e2e.py            # m3u8 合并端到端（ffmpeg +重复段预检）
python probe_acfun.py               # AcFun SSR 数据链探测
python probe_kuaishou.py            # 快手 GraphQL 与滑块拦截验证
python probe_weibo.py               # 微博接口实测
python compare_weibo_impls.py       # 微博：3 个开源项目 vs 我们（逐项对比）
python probe_sohu_truncation.py     # 搜狐 30 秒截断验证（P12）
python probe_haokan.py              # 好看视频纯 HTTP 可行性验证（P11）
python mp4_tracks.py <file.mp4>     # MP4 轨道/分辨率/时长解析
python -m pytest test_normalize.py  # 图集无水印字段单元测试
python ../app/knowledge.py          # 知识库自检（22 项域名 + 数据一致性）
python ../app/meta.py              # 元信息规范层自测
python test_meta_coverage.py        # M2 前置 Gate：元信息覆盖度

# ⚠️ Flutter 首次使用（lib/ 是手写的，必须先生成平台目录）
cd \d\WorkBuddyFILE\CreatorBox\app
.\setup-pub.ps1          # 清代理 → 预检归档接口 → pub get
.\setup-platforms.ps1    # flutter create . --platforms=android（不覆盖 lib/）

# ⚠️ 关键：测pub 连通性要测【归档接口】不是元数据接口
#   镜像的元数据 0.16s 但归档 301 到死链 → 换镜像反而更糟
curl -sSL -m 30 -o /dev/null -w "%{http_code} %{time_total}s\n" \
  https://pub.dev/api/archives/path-1.9.0.tar.gz

# ⚠️ 跑服务相关测试必须指定端口（不要写死在脚本里）
cd /d/WorkBuddyFILE/CreatorBox/server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8141
cd tests
CB_TEST_BASE=http://127.0.0.1:8141 python e2e_regression.py
python ../app/ffmpeg_util.py        # ffmpeg 能力自检
python ../app/domains.py            # 域名注册表 + 微信白名单清单
python ../app/health.py             # 平台健康度探针（6 平台）
```

## 📊 M1 里程碑状态：✅ 已完成

| Gate 条件 | 状态 |
|---|---|
| 平台端到端跑通 | ✅ 6 平台 / 8 用例全通过 |
| 域名自适应注册表 | ✅ 3 可白名单 + 3 需中转，8 域名未超 20 上限 |
| 平台健康度看板有数据 | ✅ 6/6 全绿，含L2 真实流量统计 |
