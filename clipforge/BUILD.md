# 从源码构建与安装（面向编程小白）

本文件说明如何在你自己的电脑上从源码构建 ClipForge（星创映画桌面剪辑版）。
以下命令以 **Windows / PowerShell** 为主，Mac 的差异单独列出。

---

## ⚡ 本机已配置完成（实测通过，先看这里）

**当前这台电脑的所有环境和源码都已装好，并且已经完整编译、验证通过。** 程序已经在跑：

```powershell
# 运行成品：双击这个 exe 即可（同目录已含全部运行库，绿色免安装）
D:\WorkBuddyFILE\CreatorBox\clipforge\星创映画\星创映画.exe
```

以后改了代码要重新编译，只需一条命令：

```powershell
cd D:\WorkBuddyFILE\CreatorBox\clipforge
powershell -ExecutionPolicy Bypass -File .\编译完整版.ps1
```

该脚本会自动完成：环境检查 → 准备 Skia 预编译包（离线，不联网卡下载）→ 打补丁 → 编译完整 Concat → 复制 FFmpeg 运行库 → **同步到 `星创映画\` 发布目录**。首次约 15–25 分钟。

> 注：`一键编译.ps1` 是早期 Tauri 壳方案（`src-tauri/`）的脚本，**当前路线 A 不再使用**，请用 `编译完整版.ps1`。

本机环境实测记录（2026-11-23）：

| 组件 | 版本 | 安装位置 |
|---|---|---|
| Rust / Cargo | 1.95.0 | 系统默认 |
| VS C++ 编译器 (cl.exe) | 19.44 | `D:\dev\vs2022bt\` |
| Windows SDK | 10.0.26100 | `C:\Program Files (x86)\Windows Kits\` |
| cmake | 4.4.4 | `E:\clipforge-tools\cmake\` |
| FFmpeg (LGPL shared) | 8.1.3 | `E:\clipforge-tools\ffmpeg\` |
| LLVM / libclang | 23.1.6 | `C:\Program Files\LLVM\` |
| Tauri CLI | 2.12.6 | cargo bin |
| Concat 源码 | v0.2.12 | 项目内 `vendor\Concat\` |

验证结果：`cargo build` 成功；独立运行时验证程序确认
`FFmpeg linked version: n8.1.3` 且 `probe()` 能真实打开视频文件（`ENGINE_RUNTIME_OK`）。

> 下面的第 1～6 步是"**换一台全新电脑时**"的完整手动安装流程，供以后参考。本机无需再执行。

---

## 第 0 步：看懂整体流程（30 秒）

你要准备的东西有四样：

1. **Rust 工具链** —— 编译 Rust 代码的"编译器"，本项目主体用它（你电脑已装）。
2. **系统构建工具** —— C++ 编译器（VS Build Tools）、cmake、WebView 组件。
3. **FFmpeg 开发库** —— Concat 引擎探测视频所必需。
4. **Concat 引擎源码** —— 本项目采用源码二开，需下载到项目里（有脚本自动做）。
5. **Tauri 命令行** —— 一条命令帮你启动/打包桌面窗口。

按顺序装完后：`下载源码 -> 编译 -> 运行 -> 出现窗口`。

> 偷懒提示：第 2、3 步的 C++ 编译器 / cmake 可用系统自带的 winget 安装，
> 我也可以再给你一个"一键装全部工具"的脚本。

---

## 第 1 步：安装 Rust 工具链

### Windows

1. 打开浏览器访问 <https://rustup.rs/>
2. 下载并运行 `rustup-init.exe`
3. 安装时一路回车（选择默认配置即可）
4. 安装完成后，**重新打开 PowerShell**（很重要，否则环境变量不生效）
5. 验证：在 PowerShell 输入
   ```powershell
   rustc --version
   cargo --version
   ```
   能看到版本号即成功。

### macOS

1. 打开"终端"（Terminal），输入：
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
2. 一路回车使用默认配置
3. 验证：
   ```bash
   rustc --version
   cargo --version
   ```

> 本项目要求 Rust 1.93 或更高。若版本过低，运行 `rustup update` 升级。

---

## 第 2 步：安装系统构建依赖

本项目接入了 Concat 引擎的运行时核心，`concat-media` 会**直接链接 FFmpeg 开发库**
（不是调用命令行 ffmpeg），因此这一步比普通 Tauri 项目多装一个 FFmpeg 开发库。

### Windows

**A. C++ 编译器与 WebView：**

> 偷懒方式：以**管理员身份**打开 PowerShell，复制运行下面两行即可自动安装
> VS C++ 编译器和 cmake，装完重启电脑：
> ```powershell
> winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-source-agreements --accept-package-agreements --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
> winget install --id Kitware.CMake -e --accept-source-agreements --accept-package-agreements
> ```
> 下面的手动步骤是给 winget 装失败时用的。

- 安装 **Visual Studio Build Tools（生成工具）**：
  1. 访问 <https://visualstudio.microsoft.com/visual-cpp-build-tools/>
  2. 下载"适用于 Visual Studio 2022 的生成工具"
  3. 安装时勾选 **"使用 C++ 的桌面开发"（Desktop development with C++）**
- **WebView2**：Windows 11 已自带；Windows 10 多数也已预装。若没有，访问
  <https://developer.microsoft.com/microsoft-edge/webview2/> 安装 "Evergreen Runtime"。

**B. FFmpeg 开发库（关键）——推荐一键安装：**

最简单的方式：在本文件夹空白处按住 **Shift + 右键 → 在此处打开 PowerShell 窗口**，运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\安装FFmpeg.ps1
```

脚本会自动下载 **FFmpeg 8.1.3（LGPL shared 版，Concat 官方 CI 锁定的同款版本）**、
校验 SHA256、解压，并打印出接下来要复制的命令。**你不用手动选版本。**

> 为什么要指定这个版本：Concat 引擎用的是 `ffmpeg-the-third 6.x` 绑定，官方 CI 明确锁定
> FFmpeg 8.1.3 这个固定构建。用它最稳；用会每天变化的 `latest` 或 9.x 可能链接失败。

**手动安装（不想用脚本时）：**

1. 打开固定版本的下载地址（BtbN 的 FFmpeg 8.1.3 LGPL shared）：
   <https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n8.1.3-9-g29e619e767-win64-lgpl-shared-8.1.zip>
2. 解压到一个**不带中文和空格**的路径，例如 `D:\ffmpeg\`
3. 解压后的文件夹里应该有 `bin`、`include`、`lib` 三个子目录（注意 BtbN 的 zip 解开后
   还有一层顶层文件夹，要把那一层里面的内容放到 `D:\ffmpeg\` 下）

**C. 设置环境变量（PowerShell）：**

```powershell
$env:FFMPEG_DIR = "D:\ffmpeg"
$env:PATH = "D:\ffmpeg\bin;$env:PATH"
```

> 上面的路径换成你实际解压的位置。此设置只在当前 PowerShell 窗口有效；
> 关掉窗口再开需要重新设置。想永久生效可用系统属性→环境变量，或用：
> `setx FFMPEG_DIR "D:\ffmpeg"`（重开窗口生效）。

### macOS

- 安装 Xcode 命令行工具：
  ```bash
  xcode-select --install
  ```
- 用 Homebrew 安装 FFmpeg（若没装 Homebrew，见 <https://brew.sh/>）：
  ```bash
  brew install ffmpeg
  ```
  Homebrew 装的是 7 或更新版本即可；构建脚本会通过 pkg-config 自动找到，
  一般无需额外设置环境变量。若 pkg-config 找不到，可加：
  `export FFMPEG_DIR="$(brew --prefix ffmpeg)"`

---

## 第 3 步：安装 Tauri 命令行

```powershell
cargo install tauri-cli --version "^2"
```

> 这一步会编译一会儿，属于正常现象。Mac 用户把命令放到终端里执行即可（命令相同）。

---

## 第 4 步：下载 Concat 引擎源码（二开必需）

本项目采用**源码二开**方式：Concat 的完整源码会放到项目内的 `vendor\Concat\` 目录。
进入项目根目录，运行下载脚本（固定版本 v0.2.12，约 90MB）：

```powershell
cd D:\WorkBuddyFILE\CreatorBox\clipforge
powershell -ExecutionPolicy Bypass -File .\更新Concat源码.ps1
```

> 脚本会下载固定 commit 的源码、解压到 `vendor\Concat\`，并校验关键文件。
> 若 `vendor\Concat` 已存在，脚本会先询问是否覆盖（保护你已做的二开修改）。
> Mac 用户：手动从
> <https://github.com/jub0t/Concat/archive/995b205492f2da908cc8aa8c83812008b10ae22f.zip>
> 下载并解压到 `vendor/Concat/` 即可（解开后把顶层文件夹里的内容放到该目录）。

---

## 第 5 步：首次编译

进入 src-tauri 文件夹：

```powershell
cd D:\WorkBuddyFILE\CreatorBox\clipforge\src-tauri
```

然后编译一次（首次会下载 Rust 依赖并编译 Concat 引擎，可能需要十几分钟到更久）：

```powershell
cargo build
```

> 说明：这里编译 Concat 引擎的运行时核心——`concat-core`（时间线模型）与
> `concat-media`（FFmpeg 视频探测）。相比 Concat 的完整应用，我们**刻意不引入**
> 它的 Slint 图形界面和 ONNX/GPU 模块（那些会让 Tauri 外壳冲突、且编译极慢）。
> 但 FFmpeg 开发库是必需的，请务必完成第 2 步；源码是必需的，请务必完成第 4 步。

---

## 第 6 步：运行应用

```powershell
cargo tauri dev
```

出现窗口后，点击 **"运行引擎自检"** 按钮：
- 若显示"✅ 成功：Concat 引擎代码已在程序中运行"并列出工程数据，
  即证明 Concat 代码已编译进同一个可执行文件且可运行。

> 打包成安装包（可选，用于分发）：`cargo tauri build`
> 分发时请随安装包附上本仓库的 `LICENSE` 与 `AGPL-COMPLIANCE.md`。

---

## 常见问题

- **拉取 Concat 很慢或失败**：项目用的是 GitHub 仓库，网络不佳时多试几次；
  也可在 `Cargo.toml` 中确认 rev 锁定未被改动。
- **Windows 报证书/网络错误**：多为系统代理或证书吊销检查导致，可稍后重试或检查网络代理设置。
- **找不到 C++ 编译器**：回到第 2 步确认已勾选"使用 C++ 的桌面开发"并重启电脑。

---

本项目以 AGPL-3.0-or-later 开源。完整条款见 [LICENSE](LICENSE)。
