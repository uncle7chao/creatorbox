#!/usr/bin/env python3
"""生成《微信广告接入方案》HTML（2026-10-24）

数据来源：
- 广告形式清单 = 微信官方「广告分析数据接口」的 SLOT_ID 枚举（最权威，
  后台「广告位管理」实际可建的也就是这些）
- 开通门槛 = kf.qq.com 官方客服页「小程序累计独立访客 UV 500 以上」
  ⚠️ ad.weixin.qq.com/docs/280 写的是 1000，两处官方文档不一致，
     以你后台「流量主」页实际显示的为准
- 现有自宣传位 = 服务端 app/main.py 的 PLACEMENT_LABELS（7 个）
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, '微信广告接入方案.html')

# ── 8 种广告形式（官方 SLOT_ID）────────────────────────────────────
# (官方名称, SLOT_ID, 形态, 触发, 我们的判定, 理由)
FORMS = [
    ('激励视频广告', 'REWARD_VIDEO', '全屏视频 15~30s',
     '用户主动点击 → 看完发奖',
     '✅ 主力',
     '用户为「换权益」主动看，意愿最高，eCPM 也最高。我们有三处天然需求（画质、配额、批量条数）'),
    ('Banner 横幅', 'BANNER', '320×100 常驻横条',
     '自动展示',
     '✅ 做',
     '单页只允许 1 个实例，放页脚不打断操作。收益低但稳定，是收益底盘'),
    ('插屏广告', 'INTERSTITIAL', '半屏/全屏卡片',
     '在流程断点弹出',
     '✅ 做（限 2 处）',
     '只在「任务已完成、用户要离开」时弹。工具类最忌讳一进页面就弹，那会让「即用即走」的价值归零'),
    ('原生模板广告', 'TEMPLATE', '5 种画布 / 15 套模板，可调圆角边距',
     '自动展示，可融入列表',
     '✅ 做',
     '素材库、热榜是列表页，原生模板能伪装成一条内容。用户抵触感最低'),
    ('格子广告', 'BOX', '2×N 网格小卡',
     '自动展示',
     '✅ 做（1 处）',
     '入口式曝光，占位小。放工具箱最合适 —— 用户在那儿本来就是「找工具」的探索心态'),
    ('封面广告', 'COVER', '启动开屏，5 秒可跳过',
     '冷启动自动展示',
     '⚠️ 慎用',
     '曝光最大但打断最强。工具类用户一天开好几次，每次都弹会赶人。建议每天首次启动才出'),
    ('视频贴片广告', 'VIDEO_BEGIN', '视频前贴',
     '播放视频前插入',
     '❌ 无处可放',
     '我们**没有播放器** —— 结果页只有「保存到相册」，不做站内播放。为了贴片广告去做播放器是本末倒置'),
    ('视频 Feeds 广告', 'VIDEO_FEEDS', '视频内容流中的广告',
     '融入视频流',
     '❌ 无处可放',
     '同上，我们没有视频内容流。热榜是图文榜单，不是视频流'),
    ('支付订单详情页广告', '—', '支付成功页底部',
     '自动展示',
     '❌ 不适用',
     '我们现在走卡密，没有微信支付流程。以后开通商户号才轮得到它'),
]

# ── 位置预安排（按用户真实动线排，不按页面排）──────────────────────
# (阶段, 页面, 形式, 触发条件, 用户此刻在想什么, 优先级)
SLOTS = [
    ('① 打开', '小程序冷启动', '封面广告', '每天首次启动才出（自行判断，非官方限制）',
     '「我要解析个视频」——目的明确，容忍度最低', 'P2'),
    ('② 首页', 'index 首页底部', 'Banner', '常驻，工具区下方',
     '「粘贴框在哪」——正在找主操作', 'P0'),
    ('③ 解析中', '（loading 态）', '无', '**故意不放**',
     '等待结果，任何广告都会让等待显得更长', '—'),
    ('④ 结果页', 'result 画质选择', '激励视频', '点「1080P / 原画」时提示看广告解锁',
     '「想要更清晰的」——有明确欲望', 'P0'),
    ('⑤ 结果页', 'result 保存', '激励视频', '当日保存配额用完 → 看广告 +1 次',
     '「我必须现在保存」——刚需最强的时刻', 'P0'),
    ('⑥ 结果页', 'result 保存成功 → 返回', '插屏', '保存成功后点返回时，每人每天 ≤2 次',
     '「事办完了」——心理最放松，最适合一次性曝光', 'P1'),
    ('⑦ 批量', 'batch 添加链接', '激励视频', '本次已满 3 条，看广告扩到 10 条',
     '「还想再多批几条」', 'P1'),
    ('⑧ 批量', 'batch 全部完成', '插屏', '最后一条解析完成时',
     '「终于完了」——任务结算点', 'P2'),
    ('⑨ 素材库', 'library 列表流', '原生模板', '每 6 条内容插 1 条',
     '「翻我的历史素材」——浏览态，抵触低', 'P1'),
    ('⑩ 工具箱', 'toolbox 工具网格下', '格子', '常驻',
     '「看看还有啥工具」——探索态', 'P1'),
    ('⑪ 热榜', 'ranking 列表流', '原生模板', '每 5 条插 1 条',
     '「刷榜单」——已经是刷内容的心态', 'P2'),
    ('⑫ 会员页', 'member', '无', '**故意不放**',
     '用户正在考虑付钱，这时候弹广告等于把他推走', '—'),
]

# ── 和现有自宣传位的冲突 ───────────────────────────────────────────
CONFLICT = [
    ('首页顶部轮播', 'hero_banner', '自宣传图 1~3 张', '不冲突', '一个在启动开屏、一个在页内顶部'),
    ('首页横幅', 'index_banner', '自宣传横条', '⚠️ 抢位', '首页底部只有一个位置。建议优先给自宣传（会员转化），微信 Banner 放工具区下方'),
    ('结果页横幅', 'result_banner', '自宣传横条', '⚠️ 建议撤', '结果页已经很长（视频 + 四行清单 + 保存按钮），底部再塞横条会挤走主按钮。这块用激励视频替代'),
    ('工具箱横幅', 'toolbox_banner', '自宣传横条', '⚠️ 二选一', '格子和横幅都在工具箱。建议：格子留在上方、横幅撤掉'),
    ('热榜横幅', 'ranking_banner', '自宣传横条', '⚠️ 让位', '列表流中间放原生模板就够了，底部再放横幅重复'),
    ('素材库横幅', 'library_banner', '自宣传横条', '⚠️ 让位', '同上'),
    ('会员中心横幅', 'member_banner', '自宣传横条', '保留', '会员页不该出现任何第三方广告，自宣传可以留'),
]

RULES = [
    ('主路径零打断',
     '粘贴 → 解析 → 结果，这三步之间**不放任何插屏/开屏**。用户在这条路上的唯一念头是「拿到文件」，'
     '打断一次就可能直接退出。'),
    ('激励视频只换「增量」',
     '基础能力永远免费：720P、每天 2 次保存、3 条批量。'
     '广告换的是**加成**（1080P、+1 次、扩到 10 条），不能把基础功能锁进广告 —— 那会让新用户直接流失。'),
    ('会员必须全站去广告',
     '付费用户看不到任何流量主广告，这是 ¥9.9 最硬的权益。'
     '否则用户会算「看广告也能用，为什么付钱」（会员方案里已经算过这笔账）。'),
    ('奖励由服务端发放',
     '前端加次数等于「改本地存储就能无限白嫖」。'
     '激励视频的 `onClose({isEnded:true})` 只是**信号**，真正加次数必须调服务端接口、走已有的配额体系。'),
    ('广告拉取失败要放行',
     '广告没加载出来时，**直接给用户权益**，不能让他为「我们广告没加载」买单。'
     '这也是微信官方要求的兜底逻辑。'),
    ('频次上限（我们的自律，非官方限制）',
     '插屏：每人每天 ≤2 次、两次间隔 ≥3 分钟；激励视频 ≤5 次/天；'
     '封面广告：每天首次启动才出。宁可少赚，不要赶人。'),
]

# ── 待确认 ────────────────────────────────────────────────────────
TODO = [
    ('准备 1', '确认开通门槛',
     '累计 UV 500（kf.qq.com 官方客服页）还是 1000（ad.weixin.qq.com 文档）？'
     '去你后台「推广 → 流量主」看它显示哪个数，那个才是真的。'),
    ('准备 2', '开通流量主',
     '个人主体可以开（微信社区官方回复确认）。开通后绑定结算银行卡 —— '
     '必须是中大型银行（工行/农行/中行/建行/招行/邮储等），甘肃农信这类不支持。'),
    ('准备 3', '创建 6 个广告位',
     '本方案用到：激励视频 ×1（复用三处）、Banner ×1、插屏 ×1、原生模板 ×1、格子 ×1、封面 ×1。'
     '每个位会生成一个 `adUnitId`，填进服务端配置即可，前端不用改代码。'),
    ('决策 1', '封面广告要不要开？',
     '它曝光最大，但工具类一天开好几次，每次都弹很赶人。我建议开「每天首次」这一档，或者干脆先不开。'),
    ('决策 2', '自宣传位让不让位？',
     '上面 CONFLICT 表里 5 处冲突，最需要你定的是**结果页横幅要不要撤**（我建议撤，给激励视频腾出注意力）。'),
]


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def md_bold(s):
    """把 **x** 转成 <b>x</b>，其余转义"""
    s = esc(s)
    while '**' in s:
        s = s.replace('**', '<b>', 1)
        if '**' in s:
            s = s.replace('**', '</b>', 1)
    return s


html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信广告接入方案 · 星创映画</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(160deg,#FAF6F0 0%,#F2EAE0 100%);
  color:#241C15;padding:40px 24px 70px;line-height:1.75;
}}
.wrap{{max-width:1000px;margin:0 auto}}
header{{text-align:center;margin-bottom:38px}}
header h1{{font-size:27px;font-weight:800;letter-spacing:.5px}}
header h1 em{{color:#D97A26;font-style:normal}}
header p{{color:#8B7D6E;font-size:13px;margin-top:9px}}

.blk{{background:#fff;border-radius:16px;padding:26px 26px 22px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(90,60,30,.07);border:1px solid #EFE6D6}}
h2{{font-size:18px;font-weight:800;margin-bottom:6px;display:flex;align-items:center;gap:9px}}
h2 .n{{display:inline-flex;align-items:center;justify-content:center;
  width:26px;height:26px;border-radius:8px;background:#FBF1E2;color:#A85D18;
  font-size:12px;font-weight:800;flex-shrink:0}}
.sub{{font-size:12.5px;color:#8B7D6E;margin-bottom:16px;padding-left:35px}}

.warn{{background:#FFF8E9;border:1px solid #F5D9A0;border-radius:12px;
  padding:15px 17px;font-size:13px;margin:14px 0}}
.warn b{{color:#A85D18}}
.ok{{background:#F0FAF5;border:1px solid #C6E9D2;border-radius:12px;padding:15px 17px;font-size:13px;margin:14px 0}}
.ok b{{color:#0F7A50}}
.danger{{background:#FFF3F1;border:1px solid #F8D8D4;border-radius:12px;padding:15px 17px;font-size:13px;margin:14px 0}}
.danger b{{color:#B3322F}}

table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
th{{background:#FBF6EE;text-align:left;padding:9px 10px;font-weight:700;
  color:#4F443A;border-bottom:1.5px solid #EFE6D6;white-space:nowrap;font-size:12px}}
td{{padding:10px;border-bottom:1px solid #F4EEE3;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
td code{{background:#F7F2EA;padding:1px 5px;border-radius:4px;font-size:11px;
  font-family:ui-monospace,Consolas,monospace;color:#8B5A1E}}
.num{{white-space:nowrap;font-variant-numeric:tabular-nums}}

.badge{{display:inline-block;padding:1px 7px;border-radius:5px;font-size:10.5px;
  font-weight:700;white-space:nowrap}}
.b-p0{{background:#E24B4A;color:#fff}}
.b-p1{{background:#F2A03A;color:#fff}}
.b-p2{{background:#C8B9A6;color:#fff}}
.b-no{{background:#EDE7DD;color:#9A8D7C}}
.b-ok{{background:#E4F6EC;color:#0F7A50}}
.b-warn{{background:#FFF3DC;color:#A85D18}}
.b-mid{{background:#F0EDE8;color:#6B5D4E}}

ul{{margin:8px 0 0 18px;font-size:13px}}
li{{margin:7px 0}}
li b{{color:#A85D18}}

.flow{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:12px;margin:10px 0 4px}}
.flow .st{{background:#FBF6EE;border:1px solid #EFE6D6;border-radius:8px;
  padding:6px 11px;white-space:nowrap}}
.flow .st.ad{{background:#FFF1E2;border-color:#F2C879;color:#A85D18;font-weight:700}}
.flow .st.no{{background:#F5F2EC;border-color:#E2DCD2;color:#B5A895}}
.flow .ar{{color:#C8B9A6;font-weight:700}}

.rule{{display:flex;gap:12px;padding:13px 0;border-bottom:1px solid #F4EEE3}}
.rule:last-child{{border-bottom:none}}
.rule .rk{{flex-shrink:0;width:22px;height:22px;border-radius:50%;background:#D97A26;
  color:#fff;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;margin-top:2px}}
.rule .rt{{flex:1}}
.rule .rt h4{{font-size:13.5px;font-weight:700;margin-bottom:3px}}
.rule .rt p{{font-size:12.5px;color:#5A4E43;line-height:1.7}}

.todo{{display:flex;gap:12px;padding:13px 0;border-bottom:1px solid #F4EEE3}}
.todo:last-child{{border-bottom:none}}
.todo .tk{{flex-shrink:0;font-size:10.5px;font-weight:800;padding:3px 8px;border-radius:6px;
  background:#FBF1E2;color:#A85D18;height:fit-content;margin-top:2px;white-space:nowrap}}
.todo .td2{{flex:1}}
.todo .td2 h4{{font-size:13.5px;font-weight:700;margin-bottom:3px}}
.todo .td2 p{{font-size:12.5px;color:#5A4E43;line-height:1.7}}

footer{{text-align:center;color:#B5A895;font-size:11.5px;margin-top:34px;line-height:1.9}}
</style></head><body><div class="wrap">

<header>
  <h1>微信广告接入方案 · <em>全形式 + 位置预安排</em></h1>
  <p>星创映画 CreatorBox · 2026-10-24 · 只出方案，未改代码</p>
</header>

<!-- 0. 前提 -->
<div class="blk">
  <h2><span class="n">00</span>先说一个前提：现在还不能接</h2>
  <div class="sub">不是技术问题，是账号状态不满足</div>

  <div class="warn">
    <b>开通流量主的硬门槛：小程序累计独立访客（UV）≥ 500</b>，且无违规记录。<br>
    你现在的状态：备案审核中、UV = 0。<b>所以代码可以先埋好，但广告位拿不到、也展示不出来。</b>
  </div>

  <div class="ok">
    <b>好消息：个人主体可以开通流量主。</b>
    微信开放社区官方回复原文：「满足以下条件的<b>个人/企业</b>可开通流量主功能：1. 累计独立访客 (UV) 达到 500 人及以上；2. 无刷粉行为且未曾有严重违规记录。」
  </div>

  <div class="danger">
    <b>⚠️ 但官方两处文档门槛不一致，这个必须你去后台确认：</b><br>
    · <code>kf.qq.com</code> 客服页 与 社区官方回复 = <b>500 UV</b><br>
    · <code>ad.weixin.qq.com/docs/280</code> = <b>1000 UV</b><br>
    不要按我说的做判断 —— 打开你后台「推广 → 流量主」，它显示哪个数就是哪个数。
  </div>

  <div class="flow">
    <span class="st">备案通过</span><span class="ar">→</span>
    <span class="st">上线攒 UV</span><span class="ar">→</span>
    <span class="st ad">UV 达标</span><span class="ar">→</span>
    <span class="st">开通流量主</span><span class="ar">→</span>
    <span class="st">建广告位拿 adUnitId</span><span class="ar">→</span>
    <span class="st ad">填进服务端配置</span>
  </div>
  <div style="font-size:12px;color:#8B7D6E;margin-top:8px">
    最后两步是分开的：<b>广告位 ID 走服务端配置下发</b>，所以拿到 ID 之后前端不用改一行代码、不用重新提审。
  </div>
</div>

<!-- 1. 形式清单 -->
<div class="blk">
  <h2><span class="n">01</span>微信小程序能接的广告形式（9 种，含官方 ID）</h2>
  <div class="sub">清单来自微信「广告分析数据接口」的 <code>SLOT_ID</code> 枚举 —— 后台能建的位就是这些</div>

  <table>
    <tr>
      <th style="width:120px">形式</th>
      <th style="width:120px">官方 ID</th>
      <th style="width:150px">长什么样</th>
      <th style="width:130px">触发方式</th>
      <th style="width:90px">我们</th>
      <th>理由</th>
    </tr>
    {''.join(f"""<tr>
      <td><b>{esc(n)}</b></td>
      <td><code>{esc(sid)}</code></td>
      <td>{esc(form)}</td>
      <td>{esc(trig)}</td>
      <td>{verdict}</td>
      <td style="color:#5A4E43">{esc(why)}</td>
    </tr>""" for (n, sid, form, trig, vd, why) in FORMS
     for verdict in [f'<span class="badge {"b-ok" if vd.startswith("✅") else ("b-warn" if vd.startswith("⚠️") else "b-no")}">{esc(vd)}</span>'])}
  </table>

  <div class="warn">
    <b>两种「做不了」要分清：</b><br>
    · <b>视频贴片 / 视频 Feeds</b> —— 不是我们不想接，是<b>没有播放器</b>。结果页只保存到相册，不做站内播放。
      为了贴片广告去做播放器，是本末倒置（播放器还要处理画质、进度、缓存，成本远超广告收益）。<br>
    · <b>支付订单页广告</b> —— 现在走卡密，没有微信支付流程。以后开了商户号才轮得到。
  </div>
</div>

<!-- 2. 位置预安排 -->
<div class="blk">
  <h2><span class="n">02</span>位置预安排（按用户动线排，不按页面排）</h2>
  <div class="sub">同一件事：每个位置先问「用户此刻在想什么」，再决定放什么</div>

  <table>
    <tr>
      <th style="width:70px">阶段</th>
      <th style="width:150px">位置</th>
      <th style="width:100px">形式</th>
      <th style="width:200px">触发条件</th>
      <th>用户此刻在想什么</th>
      <th style="width:52px">优先级</th>
    </tr>
    {''.join(f"""<tr>
      <td class="num">{esc(stage)}</td>
      <td>{esc(page)}</td>
      <td>{f'<span class="badge b-ok">{esc(form)}</span>' if form not in ('无',) else f'<span class="badge b-no">{esc(form)}</span>'}</td>
      <td>{md_bold(trig)}</td>
      <td style="color:#5A4E43">{esc(think)}</td>
      <td>{f'<span class="badge b-{pri.lower()}">{pri}</span>' if pri != '—' else '—'}</td>
    </tr>""" for (stage, page, form, trig, think, pri) in SLOTS)}
  </table>

  <div class="ok">
    <b>三处「故意不放」比放了更重要：</b><br>
    ① <b>解析 loading 态</b> —— 等待时插广告，会让 3 秒的等待感觉像 10 秒<br>
    ② <b>会员页</b> —— 用户正在考虑付钱，这时弹广告等于亲手把他推走<br>
    ③ <b>结果页底部 Banner</b> —— 那里是「保存到相册」主按钮，横条会把主操作挤下去
  </div>
</div>

<!-- 3. 冲突 -->
<div class="blk">
  <h2><span class="n">03</span>和现有 7 个自宣传位的冲突</h2>
  <div class="sub">服务端 <code>PLACEMENT_LABELS</code> 里已经有 7 个自有广告位，同一个位置只能给一方</div>

  <table>
    <tr>
      <th style="width:130px">现有位置</th>
      <th style="width:130px">配置键</th>
      <th style="width:120px">现在放什么</th>
      <th style="width:90px">判定</th>
      <th>处理建议</th>
    </tr>
    {''.join(f"""<tr>
      <td>{esc(name)}</td>
      <td><code>{esc(key)}</code></td>
      <td style="color:#6B5D4E">{esc(cur)}</td>
      <td>{f'<span class="badge {"b-ok" if v == "不冲突" or v == "保留" else "b-warn"}">{esc(v)}</span>'}</td>
      <td style="color:#5A4E43">{esc(advice)}</td>
    </tr>""" for (name, key, cur, v, advice) in CONFLICT)}
  </table>

  <div class="warn">
    <b>我的建议：自宣传优先，微信广告补位。</b><br>
    自宣传位是用来<b>转化会员</b>的（¥9.9 × 1000 人 = 9900 元），
    而 Banner 曝光 1000 次大概只有几块钱。<b>同一个位置，会员转化的价值远高于 banner 收益。</b>
    所以只在「没有自宣传内容」的位置给微信广告。
  </div>
</div>

<!-- 4. 规则 -->
<div class="blk">
  <h2><span class="n">04</span>六条硬规则（不遵守会同时损失体验和收益）</h2>
  <div class="sub">前四条是底线，后两条是我们给自己加的自律上限</div>

  {''.join(f'''<div class="rule">
    <div class="rk">{i + 1}</div>
    <div class="rt"><h4>{esc(t)}</h4><p>{md_bold(d)}</p></div>
  </div>''' for i, (t, d) in enumerate(RULES))}
</div>

<!-- 5. 顺序 -->
<div class="blk">
  <h2><span class="n">05</span>上线顺序（拿到 adUnitId 之后按这个顺序开）</h2>
  <div class="sub">一次全开是最糟的做法 —— 出问题分不清是哪一处</div>
  <table>
    <tr><th style="width:70px">批次</th><th style="width:230px">开哪些</th><th>为什么这个顺序</th></tr>
    <tr>
      <td><span class="badge b-p0">第一批</span></td>
      <td>激励视频（画质 / 配额 / 批量三处复用同一广告位）</td>
      <td>需求最强、用户主动、eCPM 最高。先用它验证「用户愿不愿意为权益看广告」这个前提</td>
    </tr>
    <tr>
      <td><span class="badge b-p1">第二批</span></td>
      <td>首页底部 Banner + 素材库原生模板 + 工具箱格子</td>
      <td>常驻位，不打断流程。跑一周看留存有没有掉，再决定要不要继续加</td>
    </tr>
    <tr>
      <td><span class="badge b-p1">第三批</span></td>
      <td>插屏（结果页返回时，每天 ≤2 次）</td>
      <td>插屏最容易伤体验，等前两批数据稳定、确认留存没崩再加</td>
    </tr>
    <tr>
      <td><span class="badge b-p2">第四批</span></td>
      <td>封面广告 + 热榜原生模板</td>
      <td>封面广告单独观察 —— 它影响的是「打开率」，一旦掉了立刻关</td>
    </tr>
  </table>
</div>

<!-- 6. 待确认 -->
<div class="blk">
  <h2><span class="n">06</span>需要你做 / 决定的事</h2>
  <div class="sub">3 个准备动作 + 2 个拍板</div>

  {''.join(f'''<div class="todo">
    <div class="tk">{esc(k)}</div>
    <div class="td2"><h4>{esc(t)}</h4><p>{md_bold(d)}</p></div>
  </div>''' for k, t, d in TODO)}
</div>

<div class="blk">
  <h2><span class="n">07</span>我现在可以先做的部分</h2>
  <div class="sub">不依赖 adUnitId，现在就能埋好，等 ID 一到就生效</div>
  <ul>
    <li><b>广告配置层</b>：服务端加 <code>/api/ads/wechat</code>，把各形式的 <code>adUnitId</code> 下发给前端 —— 换 ID 不用改代码、不用重新提审</li>
    <li><b>广告组件封装</b>：一个 <code>utils/wxads.js</code> 统一管激励视频/插屏/Banner 的加载、失败兜底、频次控制</li>
    <li><b>频次控制</b>：插屏「每天 ≤2 次、间隔 ≥3 分钟」的计数放服务端（和现有配额体系同一套）</li>
    <li><b>会员去广告</b>：一个 <code>isMember</code> 判断把全站广告位短路掉</li>
    <li><b>占位 UI</b>：广告位先留空 div（高度固定），避免广告加载后页面跳动</li>
  </ul>
  <div class="ok">
    <b>这套东西现在做，UV 达标后只需做一件事：去后台建位、把 ID 填进配置。</b>
    代码、测试、UI 位置全都不用再动。
  </div>
</div>

<footer>
  数据来源：微信「广告分析数据接口」SLOT_ID 枚举 · kf.qq.com 流量主开通流程 · 微信开放社区官方回复 · ad.weixin.qq.com/docs/49<br>
  方案不含收益预测 —— eCPM 随行业/季节/人群波动很大，任何具体数字都是猜的
</footer>

</div></body></html>'''

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✓ 已生成 {os.path.basename(OUT)}  ({len(html) // 1024} KB)')
