# P1b 任务清单：TikTok dtk 自持化（vendor Evil0ctal 签名栈）

> **执行前提**：在有境外网络的机器上（香港服务器）——本任务的每一步验证都需要直连 tiktok.com。
> 本地（无境外网络）能完成的只有 ①② 两步，③④⑤ 必须在 HK 服务器执行。
> 源码已就位：`C:\Users\Administrator\cb_research\src_intl\evil0ctal\`（v4 main 分支，2026-10-11 clone）
> 目标：TikTok 解析从「tikwm 第三方依赖」升级为「dtk 签名自持（guest 免登录）」，tikwm 降级为兜底。

---

## ① 本地：vendor 签名与端点模块（纯复制，无网络）

从 `src_intl/evil0ctal/Douyin_TikTok_Download_API-main/src/dtk/` 复制到
`server/app/parsers/intl/dtk/`（保持目录结构，**逐字复制不改算法**）：

```
dtk/
├── signing/native/tiktok_sign.py      # 755 行，核心签名（ChaCha-like + TLV）
├── platforms/tiktok/endpoints.py      # 端点 URL 表（P0 端点）
├── platforms/tiktok/params.py         # 参数构造（guest profile，599 行）
├── platforms/tiktok/parser.py         # 响应 → 结构化模型（645 行）
└── platforms/base.py                  # EndpointSpec/EndpointTable 依赖
```

- **保留每个文件头部的 Apache-2.0 版权与出处声明**（Evil0ctal 的注释明确记录了
  GPL/NOASSERTION 规避史——这是我们合规的证明文件，删了就是自找麻烦）
- dtk 内部互相 import 用 `dtk.` 绝对路径 → 在 dtk 目录加 `__init__.py` 并把包放进
  `sys.path` 即可，不改文件内容
- 依赖检查：`tiktok_sign.py` 纯标准库（uuid/random/hashlib/struct）——确认无第三方 import

## ② 本地：移植 golden 测试（离线自证）

- 复制 `tests/unit/test_signing_golden.py`（X-Bogus 15 向量）+ `tests/unit/test_signing.py`
  中与 content_detail 相关的用例 → `server/tests/test_dtk_signing.py`
- 跑通 = 签名移植字节级正确（这部分不需要网络）
- ⚠️ 注意该仓库注释：**不要恢复 A-Bogus golden 对拍**（V4 的 a_bogus 来自 GPL 代码，
  且已落后平台一代——参考 test_signing_golden.py 头部长注释）

## ③ HK 服务器：guest 直连验证（关键闸门）

```bash
# 在 server/ 目录（venv 已装 playwright/yt-dlp）
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from app.parsers.intl.dtk_tiktok import DtkTikTokParser   # ⑤ 步骤完成后存在
r = asyncio.run(DtkTikTokParser().parse('https://www.tiktok.com/@tiktok/video/7106594312292453675'))
print(r.get('success'), r.get('method'), bool(r.get('video_url')), (r.get('title') or '')[:50])
"
```
- ✅ success=True → dtk guest 通道在生产环境成立
- ❌ 报风控/403 → 查 `detect_risk_control` 返回值；备选：给 dtk 配一个 tiktok.com
  登录 Cookie（config 加 `CB_TIKTOK_COOKIE`，与小红书同型管理）

## ④ HK 服务器：切换层级并回归

- `tiktok_pure.py` 层级改为：**L1 dtk guest → L2 tikwm → L3 yt-dlp**（tikwm 降为兜底）
- 全量回归：test_intl.py + 手工验 3 条真实 TikTok 链接（官方号/带货号/图集帖）
- 连续 20 次解析无风控 → 视为稳定

## ⑤ 收尾

- config 加 `CB_TIKTOK_DTK`（默认 1）开关，异常时可切回 tikwm-only
- 看板探针：TikTok 探针样本挂 dtk 通道
- 运营登记：Evil0ctal 仓库 watch（上游对抗平台，我们跟版本）

---

## 预估与风险

| 项 | 估时 | 风险 |
|---|---|---|
| ① vendor + ② golden 移植 | 1 天 | 低（纯复制+适配 import 路径） |
| ③ guest 直连验证 | 0.5 天 | **中**：风控策略可能变化（备选 CB_TIKTOK_COOKIE 登录态） |
| ④ 层级切换 + 回归 | 0.5 天 | 低（tikwm 保留为兜底，可随时回退） |

**回退方案**：任何一步卡死，tikwm 主通道保持原样——扩展功能失败不影响现有能力。
