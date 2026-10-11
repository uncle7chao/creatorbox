# CreatorBox Flutter 端（P1 骨架）

一条码线覆盖 **Windows + Android**（v4 方案 §2.1 决策）。
P1 范围：桥接登录（账号中台）+ 12 平台解析核心 + 直链/字幕产出。

## 本机首次运行（3 步）

```powershell
cd D:\WorkBuddyFILE\CreatorBox\app_flutter

# 1) 生成平台壳（lib/ 与 pubspec.yaml 已写好，create 只补 windows/android 等脚手架）
flutter create . --org cn.iyama --project-name creatorbox_app

# 2) 拉依赖
flutter pub get

# 3) 跑 Windows 桌面端（解析服务需已启动）
flutter run -d windows
```

> 联调其他设备（Android 真机/模拟器）时指定服务地址：
> `flutter run --dart-define=CB_API_BASE=http://<本机局域网IP>:8080`

## 静态自检（不需要 flutter 命令）

```bash
bash tools/cb_check.sh
```

走 `dartaotruntime + dartdevc` 真编译，做语法/类型检查。
**设计原则：依赖未解析时它会报「⛔ 无法给出可信结论」并返回退出码 2，绝不谎报通过**——
只有 `flutter pub get` 跑过之后给出的 ✅ 才是可信结论。

## P1 已实现

| 模块 | 文件 | 说明 |
|---|---|---|
| 启动闸 | `lib/main.dart` | 有 token 验活 → 首页；无 token → 桥接登录；注册全局 `onSessionChanged` 供退出登录回切 |
| API 客户端 | `lib/api/client.dart` | bridge/create、bridge/poll、auth/me、**auth/openid**、**素材库增删查**、parse、health；X-User-Token 头；45s 超时 + 非 JSON 响应兜底 |
| 会话 | `lib/state/session.dart` | token/设备身份持久化（SharedPreferences）；logout 清 token 保留设备身份 |
| 桥接登录页 | `lib/pages/bridge_login_page.dart` | 6 位码 + 3s 轮询 + 5 分钟过期自动换码；轮询异常显式报错 |
| 首页 | `lib/pages/home_page.dart` | 链接输入 / 剪贴板一键读取 / 强制重解析开关 / 服务状态红字 / 账号菜单（素材库·刷新·退出）|
| 结果页 | `lib/pages/parse_result_page.dart` | 主档直链 + 档位按清晰度重排 + BGM + 字幕 + **存入素材库** |
| 素材库页 | `lib/pages/library_page.dart` | 跨端解析历史：列表 / 复制直链 / 删除 / 下拉刷新；video·image·copy 三类 |

登录流程（与服务端账号中台对接）：
App 生成设备 uuid → `bridge/create` 换 6 位码 → 用户在小程序「会员 → 跨端绑定」输码 → App 轮询 `bridge/poll` 拿 90 天 token → `auth/me` 拉账号。

### 跨端身份：为什么客户端不缓存 openid

存量接口（素材库 / 配额 / 会员 / 违禁词）全部以 `openid` 为主键，而 App/PC 手里只有 token。
**方案**：调 `GET /api/auth/openid`（带 `X-User-Token`）在服务端兑换一次。

- 客户端**不缓存 openid**，每次调用现取 —— 避免 token 换了/过期后仍拿旧 openid 请求导致串号或 401
- 存量接口**一行都不用改**（v4 §2.4「openid 全链路零改动」）
- 该端点同时下发配额，省一次往返

实测：无 token → 401；兑换出的 openid 与登录 openid 一致；可驱动素材库增删查闭环。

## 服务端实测基线（2026-10-11 沙箱实跑）

| 场景 | 结果 |
|---|---|
| `/api/health` | 12 平台就绪 |
| 桥接 6 步全链路 | 全通（`identities` 实测同一 user_id 下挂 wechat_mini + app_device 两个身份）|
| 抖音 `v.douyin.com/ntaaK4aH9pE/` | 0.9s / 6 档 / 有 BGM / 无字幕（字幕仅 YouTube 有）|
| B站 `BV1GJ411x7h7` | 0.6s / 仅 1 档 720P（wbi 签名门槛，v4 §3.2 已登记 P2 spike）|
| 缓存行为 | 首次 0.83s options=6 → 二次 0.00s options=0 但 options_count=6（服务端 slim 策略）|

⚠️ 命中缓存时档位列表为空是**预期行为**，勾选「强制重新解析」即可看到完整档位。

## P2 待做（按 v4 §2.3）

- 本机引擎：PC 内嵌 yt-dlp（解决 YouTube IP 锁直下）/ App 端 youtubedl-android
- 下载管理器（队列/断点/历史——参考 Yeguo-IDM 模式）
- 桥接发起端视觉打磨（二维码化）
- 素材库页、会员展示页

## 已知约束

- 服务端直链对 YouTube 有 IP 锁（解析信息可看，本机直下可能 403）——P2 本机引擎根治
- `flutter create` 会生成 `windows/`、`android/` 等目录；本仓库只提交 lib/ 与 pubspec.yaml，脚手架不入库
