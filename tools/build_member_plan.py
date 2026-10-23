# -*- coding: utf-8 -*-
"""生成会员体系方案书（HTML）。

数据来源：
  · 现状诊断 = 实际 grep/读码得到（不是推测）
  · 经济模型 = 本文件内的 calculate() 实算，参数取自 docs/CreatorBox-商业模式设计.md
生成：python tools/build_member_plan.py
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ══════════════════════════════════════════════════════════
# 经济模型（参数取自 docs/CreatorBox-商业模式设计.md）
# ══════════════════════════════════════════════════════════
ECPM = 60.0        # 激励视频 eCPM（元/千次）
BW = 0.12          # 国内 CDN 带宽（元/GB）
PRICE = 9.9        # 月费
FEE = 0.006        # 微信支付费率
ONE_AD = ECPM / 1000

# ⚠️ 2026-10-23 三次修正，最终口径：
#   ① 一开始按「服务器中转 25MB 视频」→ 错（视频直连 CDN）
#   ② 改成「按 GB 单价算每次成本」→ 方法错（流量费小到无意义）
#   ③ 最终（本次）：服务器是【固定月租 + 月流量包】，包内边际流量成本 = 0
#      → **成本 = 月租 ÷ 用户数**，流量只有在「爆包」时才成为问题
#      → 参考 docs/CreatorBox-云资源选型与成本重算.md（那份文档早就写清了
#         「没有任何云厂商提供不限流量的固定带宽」，我漏看了）
RENT = 15.7        # 腾讯云轻量 2C4G/5M 年付折月（文档实测价）
QUOTA_GB = 500     # 该套餐月流量包
PARSE_MB = 1058 / 1024    # 单次解析出网 ≈ 1.03MB
VIDEO_MB = 25      # 一条典型视频
PARSE_CAP = int(QUOTA_GB * 1024 / PARSE_MB)    # 流量包能撑的解析次数
VIDEO_CAP = int(QUOTA_GB * 1024 / VIDEO_MB)    # 流量包能撑的中转下载次数


def cost_per_user(dau):
    """每用户每月成本 = 月租 ÷ 日活（包内流量不额外花钱）"""
    return RENT / dau


def quota_pct(dau, per_day=2):
    """流量包使用率（只做解析）"""
    return dau * per_day * 30 * PARSE_MB / (QUOTA_GB * 1024) * 100


def monthly(ad_per_day, dau=1000):
    return ONE_AD * ad_per_day * 30 - cost_per_user(dau)


FREE_NONE = monthly(0)
FREE_AD2 = monthly(2)
FREE_AD5 = monthly(5)
MEMBER = PRICE * (1 - FEE) - cost_per_user(1000)

CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#F7F8FA;color:#1F2329;line-height:1.65;padding:0 0 70px;
}
.wrap{max-width:1080px;margin:0 auto;padding:0 26px}

/* ── 头部 ── */
.hero{background:linear-gradient(135deg,#2B1B0E,#4A2F14 60%,#7A4A1E);
  color:#fff;padding:40px 26px 34px;margin-bottom:26px}
.hero-in{max-width:1080px;margin:0 auto}
.hero h1{font-size:27px;font-weight:800;letter-spacing:.4px}
.hero h1 em{font-style:normal;color:#F2C879}
.hero p{opacity:.72;font-size:13.5px;margin-top:9px}
.hero .tags{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap}
.hero .tags span{font-size:11.5px;padding:4px 11px;border-radius:99px;
  background:rgba(242,200,121,.14);color:#F2C879;border:1px solid rgba(242,200,121,.28)}

/* ── 区块 ── */
h2{font-size:19px;font-weight:800;margin:32px 0 6px;padding-left:11px;
  border-left:4px solid #D97A26;line-height:1.35}
h2 .n{color:#D97A26;margin-right:7px}
.sub{color:#6B7280;font-size:12.5px;margin:0 0 16px 15px}
h3{font-size:15px;font-weight:700;margin:20px 0 9px;color:#2B3440}

.card{background:#fff;border-radius:14px;padding:18px 20px;margin-bottom:14px;
  box-shadow:0 1px 3px rgba(16,24,40,.06);border:1px solid #EBEDF0}
.card.warn{border-left:3px solid #E24B4A}
.card.ok{border-left:3px solid #0F9E66}
.card.info{border-left:3px solid #2F6BC4}

table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}
th{background:#F3F4F6;text-align:left;padding:9px 12px;font-weight:700;
  color:#374151;border-bottom:1px solid #E5E7EB;font-size:12.5px}
td{padding:9px 12px;border-bottom:1px solid #F0F1F3;vertical-align:top}
tr:last-child td{border-bottom:0}
td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}

.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:5px;
  font-weight:700;white-space:nowrap}
.b-have{background:#E8F5EC;color:#0F7A50}
.b-empty{background:#FDECEC;color:#C0392B}
.b-part{background:#FFF6E5;color:#A85D18}
.b-p0{background:#FDECEC;color:#C0392B}
.b-p1{background:#FFF6E5;color:#A85D18}
.b-p2{background:#EEF2F8;color:#4A5A70}

.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin:14px 0}
.kpi div{background:#fff;border-radius:12px;padding:14px 16px;border:1px solid #EBEDF0}
.kpi b{display:block;font-size:21px;font-weight:800;color:#D97A26;
  font-variant-numeric:tabular-nums;margin-bottom:3px}
.kpi span{font-size:11.5px;color:#6B7280}
.kpi div.neg b{color:#C0392B}
.kpi div.pos b{color:#0F7A50}

.quote{background:#FBF7F1;border-radius:11px;padding:14px 17px;margin:13px 0;
  font-size:13px;color:#4A3A2A;border:1px solid #F0E4D2}
.quote b{color:#A85D18}

ol,ul{margin:9px 0 9px 22px;font-size:13.5px}
li{margin:6px 0}
code{background:#F3F4F6;padding:1.5px 6px;border-radius:4px;
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:#B4325A}

.tier{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0}
@media(max-width:860px){.tier{grid-template-columns:1fr}}
.tier>div{background:#fff;border-radius:14px;padding:19px;border:1.5px solid #EBEDF0;position:relative}
.tier>div.hot{border-color:#D97A26;box-shadow:0 6px 20px rgba(217,122,38,.14)}
.tier .tt{font-size:15px;font-weight:800;margin-bottom:3px}
.tier .tp{font-size:22px;font-weight:800;color:#D97A26;margin:8px 0 3px;
  font-variant-numeric:tabular-nums}
.tier .tp small{font-size:12px;font-weight:600;color:#6B7280}
.tier .td{font-size:11.5px;color:#6B7280;margin-bottom:11px}
.tier ul{margin-left:17px;font-size:12.5px;color:#374151}
.tier li{margin:4px 0}
.tier .rec{position:absolute;top:-9px;right:14px;font-size:10.5px;font-weight:700;
  background:#D97A26;color:#fff;padding:2px 9px;border-radius:99px}

.flow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;margin:12px 0}
.flow i{background:#EEF2F8;color:#2F6BC4;padding:6px 11px;border-radius:8px;
  font-style:normal;font-weight:600}
.flow u{color:#B0B7C3;text-decoration:none;font-weight:700}

.foot{text-align:center;color:#9CA3AF;font-size:11.5px;margin-top:38px;
  padding-top:18px;border-top:1px solid #E5E7EB}
'''


def row(name, state, badge_cls, note):
    return (f'<tr><td><b>{name}</b></td>'
            f'<td><span class="badge {badge_cls}">{state}</span></td>'
            f'<td>{note}</td></tr>')


HTML = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>星创映画 · 会员体系方案</title>
<style>{CSS}</style></head><body>

<div class="hero"><div class="hero-in">
  <h1>星创映画 · <em>会员体系方案</em></h1>
  <p>两条获取路径：① 充值　② 看广告　—— 现状诊断 / 分层设计 / 经济模型 / 落地清单</p>
  <div class="tags">
    <span>基于代码实际状态诊断</span>
    <span>经济模型参数取自商业模式设计文档</span>
    <span>2026-10-23</span>
  </div>
</div></div>

<div class="wrap">

<h2><span class="n">01</span>现状诊断：充值和广告现在都是「空壳」</h2>
<div class="sub">读了实际代码，不是根据文档推测</div>

<table>
<tr><th style="width:180px">能力</th><th style="width:110px">真实状态</th><th>说明</th></tr>
{row('微信支付', '未接入', 'b-empty', '游客 AppID 无法开商户号；<code>onBuy()</code> 直接弹「请用卡密」')}
{row('卡密兑换', '可用', 'b-have', '完整闭环：后台生码 → 用户输码 → <code>member_add_days</code> 加天数')}
{row('激励视频广告', '空壳', 'b-empty', '只有 <code>showModal</code> 提示「广告位开发中」，<b>没有 createRewardedVideoAd</b>')}
{row('Banner 广告位', '配置化可用', 'b-have', '7 个位置 + 弹窗，后台可开关；但素材靠手工上传')}
{row('积分体系', '可用', 'b-have', '签到 +10 / 连签 7 天 +20 / 100 积分 = 1 天会员')}
{row('配额闸门', '可用', 'b-have', '免费：保存 2 次/日、批量 3 条、违禁词 3 次/日；会员不限')}
{row('订单记录', '未做', 'b-empty', '会员页写着「支付开放后可用」—— 没有订单表')}
</table>

<div class="card warn">
  <b>关键结论：用户现在能「真正付钱」的路径只有一条 —— 找你买卡密。</b><br>
  而「看广告换权益」是点了没反应的，这会让用户怀疑产品坏了（比不放按钮更伤）。
  <b>这两条路必须至少有一条真正跑通，否则变现是零。</b>
</div>

<h2><span class="n">02</span>三层用户模型</h2>
<div class="sub">免费 / 看广告 / 付费 —— 每一层都要「有理由往上走」</div>

<div class="tier">
  <div>
    <div class="tt">免费用户</div>
    <div class="tp">¥0</div>
    <div class="td">先证明有用，别一上来就要钱</div>
    <ul>
      <li>每日保存 <b>2 次</b></li>
      <li>最高 <b>720P</b></li>
      <li>批量 3 条 / 次</li>
      <li>违禁词 3 次 / 日</li>
      <li>有 banner 广告</li>
    </ul>
  </div>
  <div class="hot">
    <div class="rec">主推</div>
    <div class="tt">广告解锁层</div>
    <div class="tp">¥0 <small>看广告</small></div>
    <div class="td">免费但愿意付出时间的人</div>
    <ul>
      <li>每日 <b>再 +2 次</b>保存（看广告）</li>
      <li>单次 <b>1080P</b> 解锁（看广告）</li>
      <li>上限 <b>2 条 / 天</b>（关键）</li>
      <li>仍看得到 banner</li>
    </ul>
  </div>
  <div>
    <div class="tt">付费会员</div>
    <div class="tp">¥9.9 <small>/ 月</small></div>
    <div class="td">高频使用者，一次付费去掉所有摩擦</div>
    <ul>
      <li>保存 <b>不限次</b></li>
      <li>最高 <b>1080P / 原画</b></li>
      <li><b>全站去广告</b></li>
      <li>批量 10 条 / 次</li>
      <li>违禁词不限</li>
      <li>云素材库 <b>5GB</b></li>
      <li>App/PC 端下载</li>
    </ul>
  </div>
</div>

<div class="quote">
  <b>⚠️ 广告上限必须是 2 条/天，不能给 5 条。</b>下面第 05 节有实测数据：
  给 5 条时广告重度用户月贡献 {FREE_AD5:.2f} 元，而付费用户只有 {MEMBER:.2f} 元 ——
  <b>用户会算出来「看广告就够了」，付费转化被自己的广告体系吃掉。</b>
</div>

<h2><span class="n">03</span>充值链路（4 条通道，按可用性排序）</h2>

<h3>通道 A：卡密 —— 今天就能用</h3>
<div class="flow">
  <i>用户点「立即开通」</i><u>→</u><i>展示卡密购买方式</i><u>→</u>
  <i>线下收款（微信/支付宝）</i><u>→</u><i>后台批量生码</i><u>→</u>
  <i>发给用户</i><u>→</u><i>用户输码开通</i>
</div>
<div class="card ok">
  <b>优点：零资质门槛，当天可用。</b>服务端 <code>redeem_codes</code> 表 + 核销逻辑都现成，
  后台还有批量生成/作废。缺的只是「用户怎么付钱给你」这一步的引导页。
  <br><br>
  <b>要补的：</b>会员页加一个「如何购买」弹层（放收款码 + 说明），
  并给卡密加 <code>price</code> 字段记录成交价（现在只有 <code>days</code>，算不出营收）。
</div>

<h3>通道 B：微信支付（JSAPI）—— 需要商户号</h3>
<div class="card warn">
  <b>硬门槛：</b>个人主体小程序<b>无法</b>开通微信支付商户号，必须有营业执照（个体户或公司）。
  <br>
  <b>如果拿到资质：</b>服务端加 <code>/api/pay/order</code>（统一下单）+ <code>/api/pay/notify</code>（回调），
  前后端约 1 天。回调<b>必须验签 + 幂等</b>（微信会重复通知，不幂等会重复加天数）。
</div>

<h3>通道 C：小程序虚拟支付 —— 需确认类目</h3>
<div class="card info">
  v4 文档里记过「个人主体 + 工具类目可开通虚拟支付，月限额 10 万」，
  <b>但这条我无法在代码层验证，必须你到微信后台实际确认</b>（不同类目政策不同）。
  <br>
  它和商户号是两套东西：虚拟支付走 <code>wx.requestVirtualPayment</code>，适合卖会员这种虚拟商品，
  费率通常更低，但 iOS 端有平台限制。
</div>

<h3>通道 D：积分兑换 —— 已有，作为兜底</h3>
<div class="card ok">
  100 积分 = 1 天会员，签到 10 分/天、连签 7 天额外 +20。
  <b>它的定位不是「替代付费」，而是「给不花钱的人一个念想」</b> ——
  连续签到 10 天换 1 天会员，成本约等于 0，但能让用户每天都回来。
</div>

<h2><span class="n">04</span>广告链路（三个触点 + 频次控制）</h2>

<h3>触点设计</h3>
<table>
<tr><th style="width:150px">触点</th><th style="width:120px">触发时机</th><th style="width:130px">换什么</th><th>设计理由</th></tr>
<tr><td><b>① 配额用完</b></td><td>点保存但当日 2 次已用完</td><td>+1 次保存</td>
    <td>这是<b>需求最强的时刻</b>——用户已经点了保存，不给就走。转化率最高</td></tr>
<tr><td><b>② 想要高清</b></td><td>点 1080P 档位时</td><td>单次 1080P 解锁</td>
    <td>画质是「可以妥协但想要」的需求，看广告的意愿比配额用完时高</td></tr>
<tr><td><b>③ 每日签到</b></td><td>会员页签到旁边</td><td>双倍积分</td>
    <td>低成本互动，主要作用是<b>培养打开习惯</b>，不是赚广告费</td></tr>
</table>

<h3>频次与反作弊（必须做，否则一定被刷）</h3>
<table>
<tr><th style="width:150px">规则</th><th style="width:110px">值</th><th>为什么</th></tr>
<tr><td>每日广告上限</td><td>2 条</td><td>见 05 节：给 3 条以上就开始侵蚀付费转化</td></tr>
<tr><td>单次间隔</td><td>≥ 60 秒</td><td>防止连续点，也符合激励视频的自然观看时长</td></tr>
<tr><td>奖励发放</td><td><b>服务端下发</b></td><td>⭐ 前端只能上报「看完了」，奖励必须服务端校验后发。
    纯前端加次数 = 用户改本地存储就能无限白嫖</td></tr>
<tr><td>广告未看完</td><td>不发奖励</td><td>用 <code>isEnded</code> 判断，中途关闭不算</td></tr>
<tr><td>无广告填充</td><td>降级放行</td><td>⚠️ 广告加载失败时<b>必须直接给奖励</b>——
    不能让用户为「我们的广告没加载」买单</td></tr>
</table>

<div class="card warn">
  <b>⚠️ 现在代码里这两个按钮是「骗」用户的：</b>点了只弹「广告位开发中」。
  在真正接入 <code>createRewardedVideoAd</code> 之前，<b>建议先隐藏这两个入口</b>，
  比放着点了没反应好。
</div>

<h2><span class="n">05</span>成本模型（三次修正后的最终口径）</h2>
<div class="sub">套餐：腾讯云轻量 2C4G/5M · ¥{RENT}/月（年付折月）· 月流量包 {QUOTA_GB}GB</div>

<div class="card warn">
  <b>⚠️ 这个成本模型我改了三版，把错误过程也留下 —— 因为它会影响你怎么做决策：</b><br>
  <b>第一版</b>：按「服务器中转 25MB 视频」算 → 错，视频是直连 CDN，服务器压根不碰<br>
  <b>第二版</b>：改成按 GB 单价算每次成本 → 数字对，<b>但方法错</b>：
  流量费小到千分之一元，算它只会制造「每次操作都花钱」的错觉<br>
  <b>第三版（本版）</b>：你是<b>固定月租 + 月流量包</b>，<b>包内边际流量成本 = 0</b>
  → 成本就是 <b>月租 ÷ 用户数</b>，只有「爆包」时流量才成为问题
</div>

<div class="card ok">
  <b>关于「不限流量」要说清楚一件事：</b><br>
  主流云（腾讯/阿里/华为）<b>没有真正「不限流量的固定带宽」套餐</b>。
  你买的是「固定带宽 + 月流量包」（如 {QUOTA_GB}GB），<b>包内不额外收费</b>，
  这在使用体验上就等于不限流量 —— 但<b>超了会限速</b>。<br>
  <br>
  这个区别很关键：<b>它决定了「能不能做视频中转」</b>（见下方红线表）。
</div>

<h3>真实成本构成</h3>
<table>
<tr><th>项</th><th style="width:150px">金额</th><th>说明</th></tr>
<tr><td><b>保存视频</b></td><td class="num" style="color:#0F7A50">0 元</td>
    <td>直连平台 CDN，服务器不参与</td></tr>
<tr><td>解析（流量）</td><td class="num" style="color:#0F7A50">0 元</td>
    <td>包内不额外收费。单次约 {PARSE_MB:.2f}MB，{QUOTA_GB}GB 包可撑 <b>{PARSE_CAP:,} 次/月</b></td></tr>
<tr><td><b>服务器月租</b></td><td class="num" style="color:#C0392B">¥{RENT}/月</td>
    <td><b>唯一的成本项</b>，固定支出</td></tr>
</table>

<h3>每用户成本（月租摊薄，日活 1000 档）</h3>
<table>
<tr><th>日活</th><th style="width:150px">每用户成本/月</th><th style="width:130px">流量包使用率</th><th>说明</th></tr>
<tr><td>100 人</td><td class="num">{cost_per_user(100):.3f} 元</td>
    <td class="num">{quota_pct(100):.1f}%</td><td>早期成本几乎全是月租</td></tr>
<tr><td>500 人</td><td class="num">{cost_per_user(500):.3f} 元</td>
    <td class="num">{quota_pct(500):.1f}%</td><td></td></tr>
<tr><td><b>1000 人</b></td><td class="num">{cost_per_user(1000):.3f} 元</td>
    <td class="num">{quota_pct(1000):.1f}%</td><td>定价测算按这一档</td></tr>
<tr><td>3000 人</td><td class="num">{cost_per_user(3000):.3f} 元</td>
    <td class="num">{quota_pct(3000):.1f}%</td><td></td></tr>
<tr><td>8000 人</td><td class="num">{cost_per_user(8000):.3f} 元</td>
    <td class="num" style="color:#A85D18">{quota_pct(8000):.1f}%</td>
    <td>⚠️ 接近 {QUOTA_GB}GB 包上限，该升级套餐了</td></tr>
</table>

<h3>⭐ 流量包红线：为什么「绝对不能全量中转」</h3>
<table>
<tr><th>做法</th><th style="width:150px">流量包能撑</th><th style="width:140px">对应日活上限</th><th>说明</th></tr>
<tr><td><b>只做解析（直连保存）</b></td><td class="num">{PARSE_CAP:,} 次/月</td>
    <td class="num" style="color:#0F7A50">≈ {PARSE_CAP/60:,.0f} 人</td>
    <td>✅ 现在的架构。单次仅 {PARSE_MB:.2f}MB</td></tr>
<tr><td>如果视频走服务器中转</td><td class="num">{VIDEO_CAP:,} 次/月</td>
    <td class="num" style="color:#C0392B">≈ {VIDEO_CAP/30:,.0f} 人</td>
    <td>❌ 单次 25MB，<b>日活 700 就爆包限速</b></td></tr>
</table>

<div class="quote">
  <b>差 12 倍。</b>这就是 P0 那个决策的量化依据：<br>
  · <b>直连保存</b>：{QUOTA_GB}GB 包撑得住日活 {PARSE_CAP/60:,.0f} 人<br>
  · <b>全量中转</b>：同样套餐只撑得住日活 {VIDEO_CAP/30:,.0f} 人<br>
  <br>
  ✅ 所以 <code>need_proxy</code> 的正确用途是<b>「直连失败时的兜底」</b>，
  不是「所有视频都中转」。按 90% 直连成功、10% 兜底中转算，
  流量包仍然够用（中转只占 {VIDEO_CAP*0.1/VIDEO_CAP*100:.0f}% 的调用量）。
</div>

<h3>三类用户月净收益（日活 1000 档）</h3>
<table>
<tr><th>用户类型</th><th style="width:140px">月净收益</th><th>说明</th></tr>
<tr><td>免费 · 完全不看广告</td><td class="num" style="color:#6B7280">{FREE_NONE:+.4f} 元</td>
    <td>只摊 {cost_per_user(1000):.4f} 元月租，<b>不产生收入</b></td></tr>
<tr><td>免费 · 每天看 2 条（<b>建议上限</b>）</td><td class="num" style="color:#0F7A50">{FREE_AD2:+.2f} 元</td>
    <td>✅ 与付费差 {MEMBER-FREE_AD2:.1f} 元</td></tr>
<tr><td>免费 · 每天看 5 条（⚠️ 不建议）</td><td class="num" style="color:#A85D18">{FREE_AD5:+.2f} 元</td>
    <td>❌ 与付费只差 {MEMBER-FREE_AD5:.2f} 元</td></tr>
<tr><td><b>付费会员 ¥{PRICE}</b></td><td class="num" style="color:#0F7A50">{MEMBER:+.2f} 元</td>
    <td>扣支付费率与月租分摊</td></tr>
</table>

<div class="quote">
  <b>三条结论：</b><br>
  ① <b>成本可以忽略</b>：日活 1000 时每用户 {cost_per_user(1000):.4f} 元/月
     （月租 {RENT} 元摊到 1000 人），流量包只用 {quota_pct(1000):.0f}%。<br>
  ② <b>所以「广告上限」跟成本完全无关</b>，纯粹是商业策略：
     看满 5 条月贡献 {FREE_AD5:.2f} 元 vs 付费 {MEMBER:.2f} 元，
     差距只剩 {MEMBER-FREE_AD5:.2f} 元 —— 用户会算出来「看广告就够了」。<br>
  ③ <b>广告不能换「会员天数」</b>：¥{PRICE} ÷ {ONE_AD:.2f} = {PRICE/ONE_AD:.0f} 条才等值一个月，
     按 2 条/天上限要 {PRICE/ONE_AD/2:.0f} 天 —— 只能换<b>单次权益</b>。<br>
  <br>
  <b>一句话：成本是固定的月租，收入是转化的结果；流量只在你自己做中转时才是问题。</b>
</div>

<div class="card info">
  <b>但直连有一个真实门槛（比成本重要得多）：</b><br>
  <code>wx.downloadFile</code> 要求域名在<b>微信后台的 downloadFile 合法域名</b>里，
  且<b>不支持通配符</b>。平台 CDN 域名带随机/地域前缀：<br>
  <code>n98-v-ncdncold.douyinvod.com</code>（抖音）·
  <code>cn-hbyc-ct-01-01.bilivideo.com</code>（B站，含地域+运营商）·
  <code>vd3.bdstatic.com</code>（百度）<br>
  <b>白名单配不全 → 用户点保存直接失败。</b>
  代码里 <code>need_proxy</code> 标记（百度=True / B站=False）目前
  <b>只用于显示「需中转，会稍慢」的提示，实际仍直连</b> ——
  服务端只有 <code>/api/proxy-cover</code>，<b>没有视频中转端点</b>。<br>
  <br>
  <b>P0：付费用户点保存可能下不了，这是最伤付费意愿的故障。</b>
</div>

<h2><span class="n">06</span>落地清单</h2>

<table>
<tr><th style="width:52px">优先</th><th style="width:190px">事项</th><th style="width:110px">改动位置</th><th>说明</th></tr>
<tr><td><span class="badge b-p0">P0</span></td><td>先隐藏假的广告按钮</td><td>小程序 result.js</td>
    <td>点了只弹「开发中」比不放更伤。二选一：隐藏，或真接入</td></tr>
<tr><td><span class="badge b-p0">P0</span></td><td><b>核实 CDN 域名白名单 / 决定直连还是中转</b></td><td>微信后台 + server</td>
    <td>⭐ 用户点了保存却下不了 = 付费也白付。要么把各平台 CDN 域名逐个加进
        downloadFile 合法域名（不支持通配符，域名会变），
        要么把 <code>need_proxy</code> 真正实现成视频中转端点（耗带宽但稳）。
        <b>这个决定影响整个成本结构，必须先定</b></td></tr>
<tr><td><span class="badge b-p0">P0</span></td><td>卡密购买引导页</td><td>小程序 member 页</td>
    <td>放收款码 + 说明 + 到账时间，让通道 A 真正能成交</td></tr>
<tr><td><span class="badge b-p0">P0</span></td><td>卡密加 <code>price</code> 字段</td><td>server/db.py</td>
    <td>现在只有 days 没有金额，<b>算不出营收</b>，等于没有财务报表</td></tr>
<tr><td><span class="badge b-p1">P1</span></td><td>接入激励视频广告</td><td>小程序 + server</td>
    <td>需先在微信后台开通流量主（需 1000 访问量）。奖励必须服务端发放</td></tr>
<tr><td><span class="badge b-p1">P1</span></td><td>广告频次表 + 服务端校验</td><td>server/db.py</td>
    <td><code>ad_reward_daily</code> 表：记录 openid/日期/次数/来源触点</td></tr>
<tr><td><span class="badge b-p1">P1</span></td><td>订单表 + 订单记录页</td><td>server + 小程序</td>
    <td>会员页已经写了「订单记录」但点了没有 —— 要么做，要么先删入口</td></tr>
<tr><td><span class="badge b-p2">P2</span></td><td>微信支付 JSAPI</td><td>server + 小程序</td>
    <td>依赖商户号资质。回调必须验签 + 幂等（微信会重复通知）</td></tr>
<tr><td><span class="badge b-p2">P2</span></td><td>付费独占权益落地</td><td>全端</td>
    <td>云素材库 5GB / App 下载 —— 否则 9.9 只买到「不限次」，说服力不够</td></tr>
</table>

<h2><span class="n">07</span>需要你拍板的 4 件事</h2>
<div class="card info">
  <ol>
    <li><b>广告每日上限给几条？</b> 我建议 <b>2 条</b>（经济模型算出来的）。
        如果你更想先冲用户量、不在乎短期付费转化，可以给 3 条，但 5 条一定不行。</li>
    <li><b>卡密怎么卖？</b> 现在只有「天数」没有「价格」。
        建议定死三档：<b>月卡 ¥9.9 / 季卡 ¥25 / 半年 ¥45</b>（季卡半年卡给折扣，提高客单价）。
        或者你只想单档 9.9，也好 —— 但不做多档会少一部分收入。</li>
    <li><b>微信支付资质能不能拿到？</b> 有营业执照（个体户也算）就能开商户号。
        拿不到的话，<b>卡密就是唯一通道</b>，需要把它做得足够顺（自动发码更好）。</li>
    <li><b>假的广告入口先隐藏还是直接接入？</b>
        流量主需要 1000 访问量，如果还没到，<b>建议先隐藏</b>。</li>
  </ol>
</div>

<div class="foot">
  星创映画 · 会员体系方案 · 2026-10-23<br>
  现状诊断基于代码实际读码 · 经济模型参数取自 docs/CreatorBox-商业模式设计.md
</div>

</div></body></html>'''

out = os.path.join(BASE, '会员体系方案.html')
open(out, 'w', encoding='utf-8').write(HTML)
print(f'✓ {out}  {len(HTML)//1024} KB')
