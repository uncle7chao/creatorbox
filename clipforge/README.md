# 星创映画（CreatorBox）· 桌面剪辑版

> 星创映画（CreatorBox）· 桌面剪辑版，基于 Concat 引擎开发，AGPL-3.0-or-later 开源，与 Concat 官方无隶属或合作关系。

一个完全开源、本地优先的桌面视频剪辑应用。代码标识与仓库名为 **ClipForge**，属于"星创映画"产品系列。

## 与同品牌小程序的边界

本桌面版与"星创映画"微信小程序（去水印工具）是**同一品牌下的两款独立产品**。小程序用于品牌引流，与本桌面版之间：

- 不共享任何源代码文件或代码片段
- 不存在任何代码链接、接口调用或网络请求关系
- 各自拥有完全独立的代码库

本项目的 AGPL-3.0 许可证仅覆盖本项目自身，不延伸至小程序项目。

## 开源许可证

本项目采用 **GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later）**。完整许可证文本见 [LICENSE](LICENSE)。

合规要点与自查清单见 [AGPL-COMPLIANCE.md](AGPL-COMPLIANCE.md)。

## 技术构成

- 应用形态：**Concat 完整应用源码二开**（路线 A）。Concat 固定版本源码存放于 `vendor/Concat/`，本项目在其上做品牌化定制，直接编译出完整剪辑器（Slint 界面 + 全部引擎模块：渲染 / 导出 / 字幕 / 特效 / 语音 / API）。
- 剪辑引擎：[Concat](https://github.com/jub0t/Concat)，作者 **Jareer Abdullah**，AGPL-3.0-or-later
- 界面框架：Slint（Concat 自带），主题色/圆角/字号全部集中在上游的 `ui/theme/` 目录，本项目仅改该目录内的强调色与品牌文案
- 依赖：FFmpeg 8.1.3 开发库（Windows 推荐用 Concat 官方 CI 同款 LGPL shared 版，可运行 `安装FFmpeg.ps1` 一键装好）、LLVM/libclang、MSVC、cmake
- 构建：运行 `编译完整版.ps1`（已内置 Skia 预编译包离线方案），详见 [BUILD.md](BUILD.md)

## 成品与运行

编译完成后程序位于：

```
clipforge\星创映画\星创映画.exe
```

该目录内已包含程序本体与全部运行库（FFmpeg 等），**双击即可运行，绿色免安装**，整个文件夹可拷贝到其他 Windows 电脑直接使用。

来源说明：本项目**不使用 Tauri 网页外壳**。早期曾尝试 Tauri 壳 + 引擎模块的方案（残留在 `src-tauri/`，不参与当前构建），因会丢弃 Concat 现成的完整剪辑界面与预览性能而放弃。

## 与上游 Concat 的关系

本项目基于 **Concat** 视频编辑引擎开发。

- 原作者：**Jareer Abdullah**
- 原项目地址：<https://github.com/jub0t/Concat>
- 上游许可证：AGPL-3.0-or-later
- 锁定版本：**tag `v0.2.12`**，对应 commit **`995b205492f2da908cc8aa8c83812008b10ae22f`**（用 `更新Concat源码.ps1` 下载该固定版本到 `vendor/Concat/`；`src-tauri/Cargo.toml` 以本地 path 依赖引用，首次构建后生成 `src-tauri/Cargo.lock` 锁定传递依赖）
- 接入方式：**源码二开（路线 A）**。Concat 完整应用源码存放在 `vendor/Concat/`，本项目直接在其源码上做品牌与视觉定制，保留其全部剪辑功能（时间线、字幕、抠像、关键帧、特效、导出等）。
- 本项目对上游源码的修改：见下方"主要修改"（已按 AGPL 要求逐条登记，并在被修改文件头部标注）。
- **修改标注规则**：今后凡修改 `vendor/Concat/` 内的任何文件，必须在该文件头部添加标注：`Modified by ClipForge / 星创映画桌面剪辑版 on [日期]`，并在此处"主要修改"小节逐条登记（文件路径 + 日期 + 修改内容）。

### 主要修改

| 文件路径 | 日期 | 修改内容 |
|---|---|---|
| `src/crates/concat/ui/app.slint` | 2026-11-23 | 窗口标题 `Concat` → `星创映画（CreatorBox）· 桌面剪辑版`；窗口图标 → `clipforge_logo_256.png` |
| `src/crates/concat/ui/theme/dark.slint` | 2026-11-23 | 默认强调色（第 1 个 accent）由 lime `#cbf53f` → 品牌蓝 `#2f6fed` |
| `src/crates/concat/ui/theme/light.slint` | 2026-11-23 | 默认强调色（第 1 个 accent）由 lime `#4d7c0f` → 品牌蓝 `#1f5fd6` |
| `src/crates/concat/build.rs` | 2026-11-23 | exe 图标 → `clipforge.ico`；ProductName/FileDescription 改为本项目；LegalCopyright 改为保留上游署名的本项目声明；新增 `RC_TOOLKIT_PATH` 支持；图标嵌入失败改为警告不中断编译 |
| `assets/icons/clipforge.ico`、`clipforge_logo_256.png` | 2026-11-23 | 新增自有品牌图标（星创映画 LOGO），非上游文件 |
| `src/crates/concat/locales/*.json`（全部 26 个语言包） | 2026-11-24 | 应用名品牌化：简体 → `星创映画`，繁体 → `星創映畫`，其他语言 → `CreatorBox`；保留 `Concat API` / `Concat Mirror` / `Concat Sounds` 三个指向上游服务的专有名词 |

本项目同样以 AGPL-3.0-or-later 开源，与上游许可证保持一致。上游的完整源码随本项目一并提供（见 `vendor/Concat/`）。

### 商业许可联系方式

如果不想遵守 AGPL 的开源义务（例如用于闭源产品、保留修改私有、或在不开源的场景下使用），上游 Concat 提供单独的商业许可。请通过其官方渠道咨询：

- 邮箱：**jub0trd@gmail.com**（上游作者 Jareer Abdullah 在 `LICENSING.md` 中公布的商务联系邮箱）
- 说明：只有上游所有者签署的书面协议才构成商业许可，仓库的任何 issue、PR、讨论都不构成授权。

> 注意：本项目本身是 AGPL-3.0-or-later 开源项目。若你需要闭源使用，需同时解决 Concat 引擎与本项目两部分的授权问题。

## 商标与视觉

"Concat" 的名称与 Logo 归其所有者所有。本项目不使用 Concat 的 Logo，也不使用任何暗示与 Concat 官方存在联名、合作、隶属或背书关系的表述。"星创映画（CreatorBox）"是本项目的品牌名。

## 构建与安装

见 [BUILD.md](BUILD.md)。

## 关于页面

应用内"关于"页面包含"获取源代码"入口，指向本项目的公开仓库地址（当前为占位地址，仓库创建后替换）。
