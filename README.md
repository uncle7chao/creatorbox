# 星创映画 · CreatorBox

Windows 桌面视频剪辑软件，以及配套的服务端与微信小程序。

本仓库同时是**「星创映画 · 桌面剪辑版」的完整对应源码**（AGPL-3.0 要求，见下文「许可证」一节）。

---

## 桌面剪辑版（`clipforge/`）

基于开源引擎 [Concat](https://github.com/jub0t/Concat) 0.2.12 二次开发，UI 使用
[Slint](https://slint.dev) 声明式框架，渲染走 Skia / wgpu。

### 能做什么

- 多轨时间线剪辑（默认 4 轨）、逐帧定位、吸附、剃刀、ripple 删除
- 素材库：视频 / 音频 / 文本字幕 / 贴纸 / 转场 / 效果 / 滤镜 / 调节
- 预览与导出：H.264、HEVC、AV1、ProRes 4444、VP9 alpha
- 语音识别字幕（Whisper，本地推理）
- 全程本地处理，素材不上传、工程存本地

### 怎么跑

绿色免安装。解压后双击 `星创映画.exe` 即可，同目录需附带 7 个 FFmpeg 运行库
（`avcodec / avformat / avutil / avfilter / avdevice / swresample / swscale`）。

### 怎么编

见 [`clipforge/BUILD.md`](clipforge/BUILD.md)。三档编译脚本：

| 脚本 | 用途 | 产物目录 |
|---|---|---|
| `clipforge/编译开发版.ps1` | 日常改界面迭代（quick profile） | `target/quick` |
| `clipforge/编译正式版.ps1` | 交付分发（release profile） | `target/release` |

> 注意：`vendor/Concat/src/target/` 是构建产物（约 25 GB），**不在版本控制内**，
> 需要本地编译生成。

---

## 仓库结构

```
clipforge/          桌面剪辑版（Base: Concat，AGPL-3.0）
  ├─ vendor/Concat/ 上游引擎源码 + 我们的修改
  ├─ 编译开发版.ps1
  ├─ 编译正式版.ps1
  └─ BUILD.md
server/             服务端（FastAPI）
miniapp/            微信小程序
app_flutter/        早期 Flutter 客户端工程
deploy/             部署脚本与配置样例
docs/               设计与评估文档
tools/              各类工具脚本
```

---

## 许可证

**`clipforge/`（桌面剪辑版）采用 [AGPL-3.0-or-later](clipforge/LICENSE) 发布。**

它包含并修改了 Concat 的源码，因此整体作为 AGPL-3.0 衍生作品分发。对上游源码的每一处
修改都已就地标注：

```
// Modified by ClipForge / 星创映画桌面剪辑版 on YYYY-MM-DD: <原因>
```

### 如果你拿到的是编译后的程序

本仓库就是 AGPL-3.0 第 6 条所指的**对应源码**（Corresponding Source）：
包括全部构建脚本、修改过的上游源码，以及重新生成可执行文件所需的一切。

上游 Concat 的原始源码：<https://github.com/jub0t/Concat>

### 其他部分

`server/`、`miniapp/`、`app_flutter/`、`tools/` 等为自研代码，版权归作者所有。

---

## 已知限制

| 限制 | 说明 |
|---|---|
| 仅 Windows | 当前构建目标是 Windows x86_64 |
| 缩略图 | 项目未渲染过首帧前，卡片显示占位图标而非真实截图 |
| 窗口 | 150% DPI 下默认窗口会超出屏幕，因此启动即最大化 |
| 自动更新 | 已关闭。本构建不会自动升级为上游 Concat 官方版 |
