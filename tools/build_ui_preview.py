# -*- coding: utf-8 -*-
"""生成「当前界面」预览页 —— 用真实解析数据 + 真实主题值 + 真实图标。

为什么要有这个：用户问「当下的整体界面」，文字描述不可靠，
直接把小程序界面按真实数据渲染出来最直观。

⚠️ 数据不是画的：全部来自 .tmp_view_data.json（实际调 /api/parse 得到），
   封面是实际下载后 base64 内嵌（预览页自包含，不依赖服务在线）。
⚠️ 主题色取自 miniapp/app.wxss 的 page{} 变量，不是我自己配的。
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根（脚本在 tools/ 下）
VIEW = json.load(open(os.path.join(BASE, '.tmp_view_data.json'), encoding='utf-8'))
COVERS = json.load(open(os.path.join(BASE, '.tmp_covers.json'), encoding='utf-8'))
ICONS = json.load(open(os.path.join(BASE, '.tmp_icons.json'), encoding='utf-8'))


def esc(s):
    return (str(s or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


# 素材行图标：与小程序 result.wxss 的 CSS 图形视觉等价
SVG = {
    'video': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    'cover': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">'
             '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 15l5-4 4 3 3-2 6 4"/></svg>',
    'text': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">'
            '<path d="M4 6h16M4 11h16M4 16h10"/></svg>',
    'tags': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">'
            '<path d="M9 3L7 21M17 3l-2 18M4 9h16M3 15h16"/></svg>',
}

# 抖音这条实测：5 个话题、8 档、1080P、31.9MB
DY = VIEW['douyin']
BL = VIEW['bilibili']
BD = VIEW['baidu']


def asset_rows(v, cover, is_video=True):
    tags = v.get('tags') or []
    ct = v.get('copy_text') or ''
    return [
        ('video', '视频', '保存到相册', bool(v.get('video_url')), ''),
        ('cover', '封面', '保存封面', bool(cover), ''),
        ('text', '标题文案', '复制文案', bool(ct),
         (ct[:24] + '…') if len(ct) > 24 else ct),
        ('tags', '话题', '复制话题', bool(tags),
         ' '.join('#' + t for t in tags[:3])),
    ]


def result_html(v, cover):
    rows = ''
    for kind, name, act, has, prev in asset_rows(v, cover):
        cls = '' if has else ' empty'
        sub = esc(prev) if prev else ('未提取到' if not has else '')
        rows += f'''
        <div class="as-row{cls}">
          <div class="as-ic">{SVG[kind]}</div>
          <div class="as-mid">
            <div class="as-name">{name}</div>
            <div class="as-prev">{sub}</div>
          </div>
          <div class="as-act">{act}</div>
        </div>'''
    return f'''
      <div class="topbar">
        <div class="topbar-l">
          <div class="topbar-title">{esc(v.get('title'))}</div>
          <div class="topbar-sub">{esc(v.get('duration_text'))} · {esc(v.get('platform'))}</div>
        </div>
        <div class="wm-badge">无水印</div>
      </div>

      <div class="done-line">
        <div class="done-tick"></div>
        <span class="done-ok">解析已完成</span>
        <span class="done-note">数据不做存储，请保存后离开本页面</span>
      </div>

      <div class="video-wrap">
        <img class="video-cover" src="{cover}" alt="">
        <div class="video-play"></div>
        <div class="video-meta">
          <span>{esc(v.get('duration_text'))}</span>
          <span>{esc(v.get('size_text'))}</span>
        </div>
      </div>

      <div class="assets">
        <div class="as-head">本次可提取</div>
        {rows}
      </div>

      <div class="quals-row">
        <span class="ql-label">清晰度</span>
        <span class="chip on">{esc(v.get('quality'))}</span>
        <span class="chip-more">共 {v.get('options_count')} 档</span>
      </div>

      <button class="btn-primary">保存到相册</button>
      <div class="quota">今日免费保存剩 2 次 · 开通会员不限次</div>'''


HOME = f'''
      <div class="hero">
        <div class="hero-top">
          <span class="hero-title">素材解析</span>
          <span class="hero-vip">9.9 开通会员</span>
        </div>
        <div class="hero-main">粘贴链接 一键解析视频</div>
        <div class="hero-sub">抖音 · B站 · 小红书 · 8 个平台</div>
      </div>

      <div class="card">
        <div class="paste-box">
          <div class="paste-ph">粘贴抖音 / B站 / 小红书 / 快手链接</div>
          <div class="paste-btns">
            <span class="ghost-btn">从剪贴板粘贴</span>
            <span class="main-btn">解析</span>
          </div>
        </div>

        <div class="tools">
          <div class="tool">
            <div class="tool-i ti-orange"><img src="{ICONS.get('batch', '')}" alt=""></div>
            <div class="tool-l">批量解析<em>新</em></div>
          </div>
          <div class="tool">
            <div class="tool-i ti-green"><img src="{ICONS.get('library', '')}" alt=""></div>
            <div class="tool-l">我的素材</div>
          </div>
          <div class="tool">
            <div class="tool-i ti-red"><img src="{ICONS.get('rank', '')}" alt=""></div>
            <div class="tool-l">热榜</div>
          </div>
          <div class="tool">
            <div class="tool-i ti-ghost"><img src="{ICONS.get('more', '')}" alt=""></div>
            <div class="tool-l">更多</div>
          </div>
        </div>

        <div class="quota-bar">
          <div><b>2</b>/3<span>今日解析</span></div>
          <div><b>2</b>/2<span>今日保存</span></div>
          <div><b>1080P</b><span>免费画质</span></div>
        </div>
      </div>

      <div class="compline">内容来自公开平台，请确认已获授权 · 使用规范</div>'''


CSS = '''
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(160deg,#FAF6F0,#F1E7DA);color:#241C15;
  padding:34px 24px 56px;min-height:100vh;
}
.head{text-align:center;margin-bottom:30px}
.head h1{font-size:25px;font-weight:800;letter-spacing:.4px}
.head h1 em{font-style:normal;color:#D97A26}
.head p{color:#8B7D6E;font-size:12.5px;margin-top:7px}
.head .pill{display:inline-flex;gap:6px;align-items:center;margin-top:11px;padding:5px 13px;
  border-radius:99px;background:#FBF1E2;color:#A85D18;font-size:11.5px;border:1px solid #F2C879}

.stage{display:flex;gap:26px;justify-content:center;align-items:flex-start;
  flex-wrap:wrap;max-width:1240px;margin:0 auto}
.pw{display:flex;flex-direction:column;align-items:center}
.pl{font-size:13px;font-weight:700;margin-bottom:11px;color:#4F443A}
.ps{font-size:11px;color:#8B7D6E;margin-top:11px;text-align:center;
  max-width:320px;line-height:1.65}
.ps b{color:#A85D18}

.phone{width:326px;height:678px;background:#191310;border-radius:36px;padding:7px;
  box-shadow:0 22px 54px rgba(60,40,20,.24),0 2px 5px rgba(60,40,20,.12);position:relative}
.notch{position:absolute;top:7px;left:50%;transform:translateX(-50%);width:112px;height:20px;
  background:#191310;border-radius:0 0 14px 14px;z-index:9}
.sbar{position:absolute;top:12px;left:0;right:0;display:flex;justify-content:space-between;
  padding:0 24px;font-size:10.5px;color:#fff;z-index:10;font-weight:600}
.screen{width:100%;height:100%;background:#F7F2EA;border-radius:30px;
  overflow-y:auto;overflow-x:hidden;padding:36px 0 16px}
.screen::-webkit-scrollbar{width:0}

.hero{background:linear-gradient(150deg,#33210F,#22160A);color:#fff;
  padding:15px 17px 50px;border-radius:0 0 24px 24px}
.hero-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.hero-title{font-size:14.5px;font-weight:700;opacity:.94}
.hero-vip{font-size:10.5px;background:rgba(242,200,121,.16);color:#F2C879;
  padding:5px 11px;border-radius:99px;border:1px solid rgba(242,200,121,.3)}
.hero-main{font-size:20px;font-weight:800;line-height:1.35;letter-spacing:.2px}
.hero-sub{font-size:10.5px;opacity:.48;margin-top:6px}

.card{background:#fff;border-radius:17px;margin:-36px 13px 0;padding:13px;
  box-shadow:0 6px 20px rgba(90,60,30,.08)}
.paste-box{background:#FBF1E2;border:1px solid #F2C879;border-radius:11px;padding:11px}
.paste-ph{font-size:11.5px;color:#A9743F;line-height:1.5;min-height:32px}
.paste-btns{display:flex;gap:7px;margin-top:9px}
.ghost-btn{flex:1;text-align:center;font-size:11.5px;padding:8px;border-radius:8px;
  border:1px solid #E0D5C3;color:#4F443A;background:#fff}
.main-btn{flex:1;text-align:center;font-size:11.5px;padding:8px;border-radius:8px;
  background:#D97A26;color:#fff;font-weight:700}

.tools{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;margin-top:15px}
.tool{text-align:center;padding:6px 0}
.tool-i{width:40px;height:40px;border-radius:12px;margin:0 auto;display:flex;
  align-items:center;justify-content:center}
.tool-i img{width:22px;height:22px;object-fit:contain;
  filter:brightness(0) invert(1);opacity:.95}
.ti-orange{background:linear-gradient(135deg,#F2C879,#D97A26);
  box-shadow:0 6px 14px rgba(217,122,38,.30)}
.ti-green{background:linear-gradient(135deg,#3DCA8C,#0F9E66);
  box-shadow:0 6px 14px rgba(15,158,102,.26)}
.ti-red{background:linear-gradient(135deg,#FF7B6B,#E24B4A);
  box-shadow:0 6px 14px rgba(226,75,74,.26)}
.ti-ghost{background:#F1E9DC}
.ti-ghost img{filter:none;opacity:.55}
.tool-l{font-size:9.5px;color:#4F443A;margin-top:5px}
.tool-l em{font-style:normal;font-size:8px;color:#fff;background:#E24B4A;
  padding:1px 3px;border-radius:3px;margin-left:2px;vertical-align:top}

.quota-bar{display:flex;justify-content:space-around;border-top:1px solid #EFE6D6;
  margin-top:11px;padding-top:11px}
.quota-bar div{text-align:center;font-size:9.5px;color:#8B7D6E}
.quota-bar b{display:block;font-size:15px;color:#D97A26;font-weight:800;margin-bottom:1px}
.compline{text-align:center;font-size:9.5px;color:#B5A895;margin-top:16px;padding:0 13px}

.topbar{display:flex;justify-content:space-between;align-items:flex-start;
  gap:9px;padding:2px 15px 0}
.topbar-l{flex:1;min-width:0}
.topbar-title{font-size:13.5px;font-weight:700;line-height:1.42;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.topbar-sub{font-size:9.5px;color:#8B7D6E;margin-top:4px}
.wm-badge{flex-shrink:0;font-size:9.5px;padding:3px 8px;border-radius:6px;
  background:#E8F5EC;color:#2F855A;border:1px solid #C6E9D2;font-weight:700}

.done-line{display:flex;align-items:center;gap:6px;padding:9px 15px 0;flex-wrap:wrap}
.done-tick{width:12px;height:12px;border-radius:50%;background:#E8F5EC;
  position:relative;flex-shrink:0}
.done-tick::after{content:'';position:absolute;left:3.5px;top:4.5px;width:4px;height:2px;
  border-left:1.5px solid #2F855A;border-bottom:1.5px solid #2F855A;transform:rotate(-45deg)}
.done-ok{font-size:11.5px;font-weight:700;color:#4F443A}
.done-note{font-size:9.5px;color:#8B7D6E}

.video-wrap{margin:9px 15px 0;position:relative;aspect-ratio:16/9;border-radius:13px;
  overflow:hidden;background:#241C15}
.video-cover{width:100%;height:100%;object-fit:cover;display:block}
.video-play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:42px;height:42px;border-radius:50%;background:rgba(0,0,0,.42);
  border:1.5px solid rgba(255,255,255,.55)}
.video-play::after{content:'';position:absolute;left:16px;top:12.5px;
  border-left:13px solid #fff;border-top:9px solid transparent;border-bottom:9px solid transparent}
.video-meta{position:absolute;right:8px;bottom:8px;display:flex;gap:7px;
  background:rgba(0,0,0,.56);padding:4px 9px;border-radius:99px}
.video-meta span{font-size:9.5px;color:rgba(255,255,255,.94)}

.assets{background:#fff;border-radius:13px;margin:9px 15px 0;
  border:1px solid #E0D5C3;overflow:hidden}
.as-head{font-size:11.5px;font-weight:700;color:#4F443A;padding:10px 13px 5px}
.as-row{display:flex;align-items:center;padding:8px 13px;
  border-top:1px solid #F0E8DB;gap:8px}
.as-ic{width:25px;height:25px;border-radius:8px;background:#FBF1E2;color:#D97A26;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.as-ic svg{width:14px;height:14px}
.as-mid{flex:1;min-width:0}
.as-name{font-size:11.5px;color:#241C15;font-weight:600}
.as-prev{font-size:9.5px;color:#8B7D6E;margin-top:1px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:142px}
.as-act{font-size:10.5px;color:#A85D18;background:#FBF1E2;border:1px solid #F2C879;
  padding:4px 9px;border-radius:7px;flex-shrink:0;font-weight:700}

.as-row.empty .as-ic{background:#F1E9DC;color:#B5A895}
.as-row.empty .as-name{color:#B5A895}
.as-row.empty .as-prev{color:#B5A895}
.as-row.empty .as-act{background:transparent;border-color:transparent;
  color:#B5A895;font-weight:400}

.quals-row{display:flex;align-items:center;gap:7px;padding:10px 15px 0}
.ql-label{font-size:10.5px;color:#8B7D6E}
.chip{font-size:10.5px;padding:3px 10px;border-radius:7px;background:#F1E9DC;color:#4F443A}
.chip.on{background:#D97A26;color:#fff;font-weight:700}
.chip-more{font-size:9.5px;color:#B5A895;margin-left:auto}

.btn-primary{display:block;width:calc(100% - 30px);margin:11px 15px 0;padding:12px;
  border:0;border-radius:11px;background:linear-gradient(135deg,#D97A26,#E89B3C);
  color:#fff;font-size:13.5px;font-weight:800;font-family:inherit;
  box-shadow:0 6px 15px rgba(217,122,38,.28);cursor:pointer}
.quota{text-align:center;font-size:9.5px;color:#B5A895;margin-top:8px;padding:0 15px 6px}
'''


def phone(tag, body, note):
    return f'''
    <div class="pw">
      <div class="pl">{tag}</div>
      <div class="phone">
        <div class="notch"></div>
        <div class="sbar"><span>9:41</span><span>100%</span></div>
        <div class="screen">{body}</div>
      </div>
      <div class="ps">{note}</div>
    </div>'''


HTML = f'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<title>星创映画 · 当前界面</title>
<style>{CSS}</style></head>
<body>
<div class="head">
  <h1>星创映画 · <em>当前界面</em></h1>
  <p>小程序端界面还原 · 数据全部来自实际解析，不是示意图</p>
  <div class="pill">奶油纸感 #F7F2EA · 焦糖琥珀 #D97A26 · 手机屏内可滚动</div>
</div>
<div class="stage">
  {phone('① 首页', HOME, '深色 hero + 粘贴框 + 4 个工具入口<br>今日配额一目了然')}
  {phone('② 结果页 · 抖音', result_html(DY, COVERS['douyin']),
         '素材清单四行<b>全部有值</b><br>话题：#分享你的快餐推荐 #猪脚饭')}
  {phone('③ 结果页 · B站', result_html(BL, COVERS['bilibili']),
         '话题为空 → <b>灰显占位</b>（不隐藏）<br>点击提示「本视频没有话题」')}
  {phone('④ 结果页 · 百度', result_html(BD, COVERS['baidu']),
         '8 分 14 秒 / 73.1MB / 3 档<br>新接入平台的完整呈现')}
</div>
</body></html>'''

out = os.path.join(BASE, '界面预览.html')
open(out, 'w', encoding='utf-8').write(HTML)
print(f'✓ {out}  {len(HTML) // 1024} KB')
