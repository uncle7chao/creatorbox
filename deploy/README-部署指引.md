# CreatorBox 服务器部署指引（v2：大陆主部署，2026-10-11 修订）

> **架构定案（用户拍板）**：微信流量主/广告变现要求域名 ICP 备案，备案要求大陆服务器
> → **生产主部署 = 大陆服务器**。香港服务器不作为对公入口。

---

## 一、服务器与备案（启动项，时间线最长）

1. **购大陆轻量服务器**：腾讯云轻量 2C2G 即可（国内 8 平台解析 + 全业务，成本同 HK 档）
2. **域名**：iyama.cn 若已备案可直接加解析；否则新购域名走备案（个人主体，工具类目，1~2 周）
3. **备案要求**：服务器在大陆 + 域名实名 + 网站底部信息合规（解析工具站可过）
4. **流量主（广告变现）**：开通需 UV ≥1000 + 服务器域名已备案——备案是变现链路第一环

## 二、部署流程（备案下来后，30 分钟）

本机打包（PowerShell）：

```powershell
cd D:\WorkBuddyFILE\CreatorBox
powershell -ExecutionPolicy Bypass -File deploy\pack.ps1
# 产物 deploy\creatorbox_server_<date>.zip，宝塔上传或 scp
```

服务器端（Ubuntu/Debian，宝塔已有 python3）：

```bash
mkdir -p /www/creatorbox && cd /www/creatorbox
unzip -o creatorbox_server_*.zip -d server
cd server && bash ../deploy/install.sh      # venv + 依赖 + playwright chromium
sudo cp ../deploy/creatorbox.service /etc/systemd/system/
# 编辑 service：填 CB_API_KEY、CB_DB_PATH
sudo systemctl enable --now creatorbox
curl -s http://127.0.0.1:8080/api/health | head -c 200
```

## 三、Nginx + HTTPS（宝塔）

- 站点域名（如 api.iyama.cn）→ 反向代理 `http://127.0.0.1:8080`
- SSL 用 Let's Encrypt（Full 模式，比 Flexible 稳且无重定向坑）
- 防火墙只开 80/443；8080 不对公网

## 四、国际平台分层（大陆部署下的关键调整）

| 端 | 国际平台（TikTok/X/YT/FB）策略 |
|---|---|
| **小程序** | 服务端 `CB_INTL_ENABLED=0`：国际组整体关闭（大陆服务器连不上，且提审更安全）。入口由健康下发动态控制 |
| **App/PC** | ✅ **本机引擎承载**（v4 §2.3 既定架构）：用户设备直连 TikTok/X/YT，零服务器成本，天然合规 |
| HK 内部节点（可选） | 仅服务器间内部转发国际解析——**灰色地带，默认不做**；未来有真实需求再单独立项评估 |

结论：dtk 签名 / tikwm / yt-dlp 的国际解析代码**全部保留**，它们的归宿是 App/PC 本机引擎，不在小程序服务端。

## 五、部署后验证（国内链路）

```bash
bash ../deploy/verify-cn.sh     # 健康/平台数(8)/国内平台真网/账号中台
```

人工核对：
- [ ] health ready=true，platforms=8（国际组关闭态）
- [ ] 小程序 request 合法域名 = https://api.<你的域名>，全功能可用
- [ ] /admin 已加访问保护（IP 白名单或 BasicAuth）

## 六、安全与运维

- `CB_API_KEY` 必配（写操作鉴权）
- SQLite 每日备份 crontab（保留 7 天）
- 月度 `pip install -U yt-dlp`（App/PC 本机引擎版本对齐参考）
- 规模触发线（v4）：~2000 日活 Cookie 池 / 过万 IP 池 / SQLite→PostgreSQL
