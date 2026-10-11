# CreatorBox（创作素材箱）手机版开发方案

> 版本 v1.0 ｜ 2026-10-04 ｜ 基于 15 个开源项目的技术尽调

---

## 0. 一句话定位

**CreatorBox 是一个「素材不留在别人服务器里」的创作素材采集与净化工具。**
端侧完成 80% 的去水印/去字幕工作，素材不出设备；云端只做解析与高清精修。

---

## 1. 开源项目尽调结论（先看这个，省得走弯路）

### 1.1 三个必须避开的法律地雷

| 项目 | 问题 | 结论 |
|---|---|---|
| **Moonshine-Image** | 代码 **GPL-3.0** + 核心模型 MAT 权重 **CC BY-NC 4.0（非商用）** + 仅 Windows 桌面 | ❌ **彻底放弃**。它 173 star 最活跃、demo 效果最好，恰恰是最不能碰的 |
| **VSR 内置 ProPainter** | 仓库是 Apache-2.0，但 ProPainter 是 **S-Lab License 1.0 非商业**，仓库授权不向下覆盖 | ⚠️ **可借鉴代码，不可打包 ProPainter 模式**。云端改用 E2FGVI（MIT） |
| **JoeanAmier/Douyin_TikTok** | 已归档 + 签名模块是 **GPL-3.0 代码移植** + 强依赖手工 Cookie | ❌ **排除**。Apache-2.0 壳包着 GPL 内核 |

> ⚠️ 商业闭源项目必须在动工前把这些结论落成一份《第三方依赖许可证台账》，逐条记录：项目名、许可证、权重许可证、是否可商用闭源、署名义务。

### 1.2 移动端模型的真实性能数据（关键修正）

「ProPainter/STTN 跑不了手机」这个说法**不准确**，真实原因如下：

| 模型 | 参数量 | 权重体积 | 移动端实测 | 商用许可 | 判定 |
|---|---|---|---|---|---|
| **MI-GAN** | 5.95M | FP16 **16.3MB** | Pixel 8a GPU **~6ms** @512×512 | 待核实 | ✅ **端侧首选** |
| **LaMa** | 45.6M | INT8 **44MB** / FP16 174MB | S23 Ultra NPU **87ms** | Apache-2.0 | ✅ 端侧备用 |
| STTN | 16.6M | — | 未有实测 | MIT | ❌ FLOPs 1315G/10帧，瓶颈是算力不是参数量 |
| ProPainter | 39.4M + RAFT | — | 无 | **非商业** | ❌ 720p 需 **7GB 显存**（光流网络驻留） |

**MI-GAN 为什么天生适合移动端**：纯 depthwise-separable Conv2d + nearest upsample，**无转置卷积、无归一化层**。Places2 FID 11.83，**优于 LaMa（22.00）与 ZITS（16.78）**。

**逐帧闪烁的真正解法不是换模型，而是时序复用**：只接受跨帧位置稳定的标记 → 光流对齐 → 时序混合 → 仅边缘 blend。参考 `remove-ai-watermarks` 的 temporal consistency 实现，纯几何运算，端侧 CPU 即可完成。

### 1.3 逐帧处理能力对比（视频）

| 项目 | 许可 | 活跃度 | 移动端 | 可借鉴点 |
|---|---|---|---|---|
| **Timeline Studio** | MIT（模型另计） | 887★，创建仅 3 个月 | **70/100** | ⭐ **架构范本**：纯 WebGPU + MI-GAN + WebCodecs，不需 ffmpeg、不需 GPU |
| **remove-ai-watermarks** | Apache-2.0 | 5754★，**v0.44.0，2 天前** | 45/100 | ⭐ **时序一致性处理** + 四层能力划分（identify/visible/invisible/metadata） |
| VSR | Apache-2.0 ⚠️ | 13134★，189 issues | 25/100 | 「检测→掩码→多算法可插拔」架构 + `--inpaint-mode opencv` |
| SoraWatermarkCleaner | Apache-2.0 | 1146★，**已归档** | 20/100 | 「专用检测器 + 通用填充器」分层 |

### 1.4 链接解析：官方 API 全部走不通

| 平台 | 开放 API 情况 | 结论 |
|---|---|---|
| 抖音 | 只有「我们发内容」，读不到第三方作品 | ❌ 无效 |
| 小红书 | 面向商家/电商，创作者接口不开放，需中国境内企业主体 + 2~4 周审核 | ❌ 基本不可能过审 |
| 视频号 | 完全无对外开放 API | ❌ |
| B站 | 半开放，仅投稿类 | ❌ |

**但 2026 年出现了免签名通道，这是最重要的技术情报：**

- 抖音移动端 Feed 接口 `api5-normal-c-hl.amemv.com/aweme/v1/feed/` —— **免 Cookie、免 a_bogus、403 率 0%、约 200ms**
- 抖音 `iesdouyin.com/share/video/{id}` 移动端 SSR 仍稳定下发 `_ROUTER_DATA`（PC 端已是 CSR 空壳）
- 抖音公开 `web/api/v2/aweme/slidesinfo/` 至今仍返回 `aweme_details`
- 小红书 SSR `window.__INITIAL_STATE__` 仍注入全部高清流

**X-Bogus 已死，a_bogus 也不是解法**（字节 2024-06 换主签名机制，JS VM 加密 + 前端每周迭代，还原代码随时作废）。**不要自研签名逆向。**

| 项目 | 许可 | Star | 结论 |
|---|---|---|---|
| **parse-video-py** | MIT | 703 | ✅ **主力**，直接 fork 部署 |
| **ucmao/media-parser** | MIT | 342 | ✅ 抄架构（双 UA 回退、终端状态短路熔断） |
| parse-video (Go) | MIT | 1053 | ✅ 内存吃紧时的降级预案 |
| JoeanAmier fork | GPL 风险 | 15 | ❌ 排除 |
| PyPI media-parser | MIT | 1 | ❌ 不支持国内平台、要求 Py3.12 |

---

## 2. 技术选型

### 2.1 客户端框架

| 方案 | 评价 |
|---|---|
| **Flutter + 平台通道** ⭐ 推荐 | 一套代码双端；AI 推理走 Platform Channel 调原生（TFLite/LiteRT on Android、CoreML on iOS）；**UI 一致性好，算法层各写各的** |
| React Native | 生态更大，但 AI 推理仍需原生桥接，收益不明显 |
| 原生双端 | 性能最优但工作量 ×2，不划算 |
| 纯 Web/PWA | Timeline Studio 已验证 WebGPU 可行，但**移动端 Safari/Android Chrome 上 WebGPU 可用性不稳定**，不能作为主方案 |

**决策：Flutter，UI 与业务层跨端，L1/L2/L3 算法层用 Kotlin + Swift 各写一份，通过 Platform Channel 暴露。**

### 2.2 端侧 AI 运行时

| 平台 | 运行时 | 模型格式 |
|---|---|---|
| Android | **LiteRT / TFLite**（GPU delegate + NNAPI） | MI-GAN FP16 16.3MB、LaMa INT8 44MB |
| iOS | **CoreML**（ANE 神经网络引擎） | 同上，转换自同一 TFLite 权重 |

> ⚠️ **MI-GAN 的许可证本次未核实**（Timeline Studio 的 MIT 只覆盖自身代码，未标注模型许可）。**这是动工前第一件必须确认的事**，商业闭源前需拿到书面授权。

### 2.3 后端

沿用 GEO Optimizer 已定的技术栈思路，CreatorBox 后端保持一致：

- **FastAPI + PostgreSQL + Redis**，宝塔 + Python 3.10.12
- 解析服务：fork `parse-video-py`，叠加 `ucmao/media-parser` 的抖音移动端 Feed 一级通道
- 视频精修队列：Redis + worker，调 E2FGVI（MIT）
- 部署：起步可用现有香港机 43.159.141.17（2C2G），**但 E2FGVI 需 CUDA，与 2C2G 不兼容 → 精修服务需独立 GPU 实例**

---

## 3. 功能模块设计

### 3.1 模块一：素材采集（链接解析）

```
主链路：App 内置「分享到 CreatorBox」Share Intent 接收
        ↓ 拿不到时
降级链路：监听剪贴板 → 解析服务
        ↓ 仍失败
兜底：手动粘贴链接
```

**Android 实现要点（极易踩坑）：**
- `intent-filter` 接收 `ACTION_SEND` + `text/plain`
- ⚠️ **必须与 `ACTION_MAIN` 分成两个 filter**，否则系统只按 MAIN 匹配、分享被静默忽略
- Android 12+ 必须显式 `android:exported="true"`

**iOS 实现要点：**
- Share Extension（`com.apple.share-services`）
- `NSItemProvider.loadItem(forTypeIdentifier: UTType.url.identifier)`
- `ActivationRule` 放开 `SupportsWebURLWithMaxCount 1`
- 通过 **App Group** 容器传给主 App
- ⚠️ Extension 内存时间受限，**只做「取 URL + 落盘」，网络请求交主 App**

> 🔴 **开工前第一项验证任务**：真机实测抖音/小红书/快手分享面板是否真的走系统 `ACTION_SEND`。抖音有大量自定义 scheme（`snssdk1128://aweme/detail/{id}`）和自研分享 SDK，可能走私有通道。**若不成立，整个主链路要重新设计。**

### 3.2 模块二：图片去水印

| 层级 | 技术 | 速度 | 质量 | 适用 |
|---|---|---|---|---|
| L1 检测 | 手动框选（主）+ 端侧轻量 DBNet ONNX ~5MB（辅） | 即时 | — | 所有场景 |
| L2 兜底 | **调和扩散 + 仿制图章**（移植 pamelaaaaa1218 算法） | <5ms | 背景平整 ✓，复杂纹理 ✗ | 80% 日常图 |
| L3 精修 | MI-GAN 16.3MB（主）/ LaMa INT8 44MB（备） | 6ms / 87ms | 高 | 复杂纹理 |
| 云端 | 扩散模型（Qwen-Image-2512 + ControlNet） | 分钟级 | 最高 | 付费「专业精修」 |

**元数据净化**（从 Universal-AI-Watermark-Remover 借鉴，端侧可做）：
- C2PA / JUMBF 二进制流扫描剥离
- EXIF / XMP / IPTC 清除
- Unicode 零宽字符隐写清理

### 3.3 模块三：视频去水印/去字幕

```
用户框选水印区域 → 跨帧稳定性检测（过滤移动的水印）
    ↓
ROI 裁剪（通常占画面 10~20%）
    ↓
L2 OpenCV inpaint 逐帧（TELEA/NS，单帧 <5ms）
    ↓ 效果不足
L3 MI-GAN 逐帧 + 光流对齐 + 时序混合 + 边缘 blend
    ↓ 用户点「高清导出」
云端 E2FGVI（MIT，非 ProPainter）
```

**ROI 裁剪是把「不可行」变成「可行」的关键杠杆**：ProPainter 跑不动的根因是 1280×720 全画布 + 光流驻留；裁到水印框（如 1080×200）后，MI-GAN 在 512×512 上推理 —— 这恰好落在移动端已实测的甜点区间。

### 3.4 模块四：AI 内容检测（不是去除）

⚠️ **必须调整预期**：`dewatermark`（MIT）**明确不支持 Claude/Anthropic 水印**，自述「无任何已跟踪的统计结果满足完整 benchmark 协议」，内置 KGW/Unigram 是封闭词表的离线参考配置。

**所以产品定位应为「AI 内容检测与举证」，不是「AI 水印去除」。** 对外不能宣称能去除 AI 水印。

**但它的设计范式值得全盘借鉴**：
- **证据回执（evidence receipt）** —— 每次检测产出可审计报告
- **fail-closed 设计** —— 检测器不确定时不放行
- **检测器 / 验证器分离** —— 避免自证自话

> ⚠️ `remove-ai-watermarks` README 自述提示：包括中国在内的一些司法辖区可能限制移除 AI 标签。**跨境产品必须先做法务评估。**

---

## 4. 里程碑排期

| 阶段 | 周期 | 交付物 | 关键验证 |
|---|---|---|---|
| **M0 可行性验证** | 1~2 周 | 技术验证 Demo（非产品） | ① 真机抓抖音/小红书分享 Intent 原始内容<br>② MI-GAN 在 TFLite/CoreML 转换 + 端侧跑通 + **确认许可证**<br>③ 端侧调和扩散算法效果 |
| **M1 采集 MVP** | 3~4 周 | 分享接收 + 剪贴板 + 解析服务 + 素材库 | 解析成功率 ≥90%（抖音/小红书/B站） |
| **M2 图片去水印** | 3~4 周 | L1+L2+L3 完整链路 + 元数据净化 | MI-GAN 端侧 512×512 <150ms |
| **M3 视频去水印** | 4~5 周 | ROI 裁剪 + 时序一致性 + 分级导出 | 30fps 1080p 无可见闪烁 |
| **M4 商业化** | 2~3 周 | 账号 + 内购 + 素材云同步 | GPU 精修服务成本模型跑通 |

**M0 是 Gate，不通过不进 M1。** 特别是分享 Intent 那条 —— 若平台走私有通道，需要在 M0 就改设计，别做到 M1 才发现。

---

## 5. 风险清单

| 风险 | 等级 | 应对 |
|---|---|---|
| **MI-GAN 许可证未确认** | 🔴 高 | M0 第一件事确认，拿不到书面授权则改用 LaMa（Apache-2.0） |
| **分享 Intent 拿不到链接** | 🔴 高 | M0 真机验证；失败则降级为「剪贴板监听 + 手动粘贴」为主链路 |
| **平台解析失效（平台改版）** | 🟡 中 | 三级降级通道（Feed 接口 → slidesinfo → 移动端 SSR）；**不承诺 100% 成功率**；建立平台改版监控 |
| **E2FGVI 需 CUDA，2C2G 跑不动** | 🟡 中 | 独立 GPU 实例；或 M0 阶段先只做图片，视频精修延后 |
| 逐帧处理闪烁 | 🟡 中 | 时序复用方案（光流对齐 + 时序混合 + 边缘 blend） |
| MI-GAN 自定义算子转换失败 | 🟢 低 | 备选 LaMa INT8 44MB（已有 NPU 实测背书） |
| AI 标签移除合规风险 | 🟡 中 | 功能定位改为「检测与举证」；跨境前做法务评估 |
| pamelaaaaa1218 无 LICENSE 文件 | 🟢 低 | 仅借鉴算法思路（调和扩散是经典算法本身），不复制代码；或请作者补发授权 |

---

## 6. 立即可执行的下一步

1. **建《第三方依赖许可证台账》** —— 把本文档 §1.1 的三个雷区 + MI-GAN 待确认项落成表格存档
2. **M0 真机验证分享 Intent** —— Android `onNewIntent` 打印原始 Intent，抖音/小红书/快手逐个平台抓
3. **fork parse-video-py + ucmao/media-parser** 部署到现有服务器，跑通抖音/小红书解析
4. **MI-GAN 许可证核实** + TFLite 转换 POC

---

> ⚠️ **本文档部分内容已被 [CreatorBox-产品方案v2-纯解析.md](./CreatorBox-产品方案v2-纯解析.md) 取代。**
> 其中「端侧 AI 像素净化」相关的功能规划已作废（纯解析路线不需要 AI 模型）。
> 本文档保留作为调研记录与技术参考。
