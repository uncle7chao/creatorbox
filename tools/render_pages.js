#!/usr/bin/env node
/**
 * 小程序页面渲染器（2026-10-24）
 *
 * 目的：把 14 个页面的 WXML + WXSS 渲染成可在浏览器里看的 HTML，
 *      用来「肉眼检查每个页面长什么样」，不用每改一次就开微信开发者工具。
 *
 * 为什么不逐个手抄 HTML：
 *   手抄必然和真实代码脱节 —— 改完 wxml 忘了改预览，预览就成了假的。
 *   转换器读的是同一份源文件，界面一变重跑一次就同步。
 *
 * 能做什么 / 不能做什么（先划清边界，避免误判）：
 *   ✅ 标签映射、class 保留、WXSS 转 CSS（rpx→px）、wx:if / wx:for / {{}} 求值
 *   ✅ 主题变量（app.wxss 的 page{} 转 body{}）
 *   ❌ 不执行业务逻辑（onLoad 里的网络请求、setData 的运行时变化）
 *      → 所以每个页面配一份 mock 数据，模拟「加载完成后」的样子
 *   ❌ 不模拟滚动吸顶、原生组件（video/canvas/web-view 只画占位）
 *
 * 用法：
 *   node tools/render_pages.js            # 渲染全部
 *   node tools/render_pages.js index      # 只渲某个
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const MP = path.join(ROOT, 'miniapp');
const OUT = path.join(ROOT, 'test', 'pages');

// ── 标签映射：小程序组件 → HTML ────────────────────────────────
// block 是「透明容器」，不产生标签，只渲染子节点
const TAG_MAP = {
  view: 'div', text: 'span', image: 'img', block: null,
  'scroll-view': 'div', swiper: 'div', 'swiper-item': 'div',
  navigator: 'a', button: 'button', form: 'form', label: 'label',
  textarea: 'div', input: 'div', picker: 'div', 'picker-view': 'div',
  'rich-text': 'div', video: 'div', canvas: 'div', 'web-view': 'div',
  'cover-view': 'div', 'cover-image': 'img', 'movable-area': 'div',
  'movable-view': 'div', slot: 'div', 'checkbox-group': 'div',
  checkbox: 'div', radio: 'div', switch: 'div', slider: 'div',
  icon: 'span', progress: 'div', 'map': 'div', camera: 'div',
};

// 这些标签在 HTML 里加 class 标记，方便调试时认出来
const TAG_HINT = {
  'scroll-view': 'wx-scroll', swiper: 'wx-swiper', 'swiper-item': 'wx-swiper-item',
  textarea: 'wx-textarea', video: 'wx-video', canvas: 'wx-canvas',
  'web-view': 'wx-webview',
};

// ══════════════════════════════════════════════════════════════
// 1. WXML 解析
// ══════════════════════════════════════════════════════════════

function parseWxml(src) {
  // 去注释（保留换行，避免行号错位影响可读性）
  src = src.replace(/<!--[\s\S]*?-->/g, '');

  const root = { tag: '#root', attrs: {}, children: [] };
  const stack = [root];
  let i = 0;

  const top = () => stack[stack.length - 1];

  while (i < src.length) {
    const lt = src.indexOf('<', i);

    // 文本节点
    if (lt === -1) {
      const t = src.slice(i);
      if (t.trim()) top().children.push({ text: t });
      break;
    }
    if (lt > i) {
      const t = src.slice(i, lt);
      if (t.trim()) top().children.push({ text: t });
    }

    // 闭标签
    // ⚠️ 必须从 lt 处切片再匹配：直接 src.match(/^.../) 只会锚定整个字符串开头，
    //    结果所有闭标签都匹配失败、节点树全乱（踩过：整个页面渲染成空壳）
    const close = src.slice(lt).match(/^<\/\s*([\w-]+)\s*>/);
    if (close) {
      i = lt + close[0].length;
      // 弹栈到匹配的标签（容错：不对齐时也能继续）
      for (let k = stack.length - 1; k > 0; k--) {
        if (stack[k].tag === close[1]) { stack.length = k; break; }
      }
      continue;
    }

    // 开标签
    const open = src.slice(lt).match(/^<\s*([\w-]+)((?:[^>"']|"[^"]*"|'[^']*')*)>/);
    if (open) {
      const tag = open[1];
      const attrStr = open[2] || '';
      const selfClose = /\/\s*$/.test(attrStr);
      const node = { tag, attrs: parseAttrs(attrStr), children: [] };
      top().children.push(node);
      if (!selfClose) stack.push(node);
      i = lt + open[0].length;
      continue;
    }

    // 不是标签，当文本
    i = lt + 1;
  }
  return root;
}

function parseAttrs(s) {
  const attrs = {};
  s = s.replace(/\/\s*$/, '');
  const re = /([\w:.-]+)(?:\s*=\s*("([^"]*)"|'([^']*)'))?/g;
  let m;
  while ((m = re.exec(s))) {
    const name = m[1];
    const val = m[3] !== undefined ? m[3] : (m[4] !== undefined ? m[4] : '');
    if (name) attrs[name] = val;
  }
  return attrs;
}

// ══════════════════════════════════════════════════════════════
// 2. 表达式求值
// ══════════════════════════════════════════════════════════════

function evalExpr(expr, data) {
  const e = String(expr).trim();
  if (!e) return '';
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function('$d', `with($d){ return (${e}); }`);
    const v = fn(data);
    return v === undefined ? '' : v;
  } catch (err) {
    return '';   // 求值失败一律当空，不中断整页渲染
  }
}

/** 处理一个属性值（可能含 {{}} 混排，如 class="a {{b ? 'c' : ''}}"） */
/** 解码 WXML 里的 HTML 实体（placeholder 常用 &#10; 表示换行） */
function decodeEntities(s) {
  return String(s)
    .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(parseInt(d, 10)))
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&amp;/g, '&');
}

function interp(raw, data) {
  if (raw === undefined) return '';
  if (!raw.includes('{{')) return decodeEntities(raw);
  // 整串就是一个表达式 → 返回原始类型（数组/对象/布尔）
  // ⚠️ 中间不能含 `}}`：否则 {{a}}/{{b}} 这种「两个插值」会被误判成
  //    单个表达式 "a}}/{{b"，求值抛错后返回空 —— 页面数值全消失（踩过）
  const whole = raw.match(/^\s*\{\{((?:(?!\}\})[\s\S])*)\}\}\s*$/);
  if (whole) return evalExpr(whole[1], data);
  // 混排 → 拼字符串
  return decodeEntities(String(raw).replace(/\{\{([\s\S]*?)\}\}/g, (_, e) => {
    const v = evalExpr(e, data);
    return v === false || v === undefined || v === null ? '' : String(v);
  }));
}

// ══════════════════════════════════════════════════════════════
// 3. 渲染成 HTML
// ══════════════════════════════════════════════════════════════

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** 图片路径：小程序里是 /images/x.png，HTML 里要指到真实文件 */
function fixSrc(src) {
  if (!src) return '';
  if (/^https?:|^data:/.test(src)) return src;
  if (src.startsWith('/')) return '../../miniapp' + src;
  return src;
}

function renderNodes(nodes, data) {
  const out = [];
  let chainOpen = false;   // wx:if / wx:elif 链：一旦有分支命中，后续 else 都不出

  for (const n of nodes) {
    // 文本
    if (n.text !== undefined) {
      const t = interp(n.text, data);
      let txt = esc(typeof t === 'object' ? JSON.stringify(t) : t);
      // 小程序 text 组件把 \n 当换行，HTML 里默认会塌成空格
      // （提词器的稿子整段是 \n 分隔，不转就成一大坨）
      if (txt.includes('\n')) txt = txt.replace(/\n/g, '<br>');
      out.push(txt);
      continue;
    }

    const a = n.attrs;

    // ── wx:if / wx:elif / wx:else ──
    if ('wx:if' in a) {
      const v = interp(a['wx:if'], data);
      const truthy = !!v && v !== 'false';
      chainOpen = truthy;
      if (!truthy) continue;
    } else if ('wx:elif' in a) {
      if (chainOpen) continue;
      const v = interp(a['wx:elif'], data);
      const truthy = !!v && v !== 'false';
      chainOpen = truthy;
      if (!truthy) continue;
    } else if ('wx:else' in a) {
      if (chainOpen) continue;
      chainOpen = true;
    }

    // ── wx:for ──
    if ('wx:for' in a) {
      const list = interp(a['wx:for'], data);
      const itemName = a['wx:for-item'] || 'item';
      const idxName = a['wx:for-index'] || 'index';
      const arr = Array.isArray(list) ? list : [];
      for (let k = 0; k < arr.length; k++) {
        const scope = Object.create(data);
        scope[itemName] = arr[k];
        scope[idxName] = k;
        // 去掉 wx:for 相关属性，避免递归
        const clone = { tag: n.tag, attrs: { ...a }, children: n.children };
        delete clone.attrs['wx:for'];
        delete clone.attrs['wx:key'];
        delete clone.attrs['wx:for-item'];
        delete clone.attrs['wx:for-index'];
        out.push(renderNodes([clone], scope));
      }
      continue;
    }

    out.push(renderElement(n, data));
  }
  return out.join('');
}

function renderElement(n, data) {
  // ── 自定义组件：渲染成占位块，标出它是什么位 ──
  // 组件内部逻辑（读服务端配置、按 mode 分支）转换器不执行，
  // 所以只画出「这里有一个广告位」+ 位置名，用来检查排布位置对不对。
  if (n.tag === 'ad-banner') {
    const place = interp(n.attrs.placement, data) || '(未指定)';
    return `<div class="wx-ad-banner"><span class="wx-ad-tag">广告位</span>`
      + `<span class="wx-ad-name">${esc(String(place))}</span>`
      + `<span class="wx-ad-note">banner · 320×100 等比</span></div>`;
  }
  if (n.tag === 'theme-deco') return '';   // 装饰层不影响排版，跳过

  const mapped = TAG_MAP[n.tag];
  // block / 未知标签 → 透明
  if (mapped === null) return renderNodes(n.children, data);
  const tag = mapped || 'div';

  const a = n.attrs;
  const attrs = [];

  // class（求值 + 加组件提示类）
  let cls = interp(a.class, data);
  cls = (cls === 0 || cls === false) ? '' : String(cls || '');
  if (TAG_HINT[n.tag]) cls = (cls + ' ' + TAG_HINT[n.tag]).trim();
  if (cls) attrs.push(`class="${esc(cls)}"`);

  // style
  const style = interp(a.style, data);
  if (style) attrs.push(`style="${esc(String(style).replace(/([\d.]+)rpx/g, (_, v) => (v * 0.5) + 'px'))}"`);

  // 图片
  if (tag === 'img') {
    const src = interp(a.src, data);
    if (src) attrs.push(`src="${esc(fixSrc(String(src)))}"`);
    const mode = a.mode || 'scaleToFill';
    // aspectFill ≈ object-fit:cover；aspectFit ≈ contain
    const fit = mode === 'aspectFill' ? 'cover' : (mode === 'aspectFit' ? 'contain' : 'fill');
    const extra = `object-fit:${fit};`;
    attrs.push(`style="${extra}${attrs.some(x => x.startsWith('style=')) ? '' : ''}"`);
    // 合并 style
    const st = attrs.pop().replace(/^style="|"$/g, '');
    attrs.push(`style="${esc(st)}${style ? esc(String(style)) : ''}"`);
    attrs.push('alt=""');
  }

  // 输入类组件：小程序 textarea/input 的 placeholder 要显出来，
  // 否则预览里就是一块空白（看不出这里该填什么）
  if (n.tag === 'textarea' || n.tag === 'input') {
    const ph = interp(a.placeholder, data) || interp(a['placeholder-class'] ? '' : '') || '';
    const val = interp(a.value, data);
    if (val) {
      attrs.push(`data-value="1"`);
    } else if (ph) {
      attrs.push(`data-ph="${esc(String(ph))}"`);
    }
    const maxlen = a['maxlength'];
    if (maxlen) attrs.push(`data-max="${esc(maxlen)}"`);
  }

  // 占位组件
  if (['wx-video', 'wx-canvas', 'wx-webview'].some(c => cls.includes(c))) {
    attrs.push('data-placeholder="1"');
  }

  const html = `<${tag}${attrs.length ? ' ' + attrs.join(' ') : ''}>`;
  let inner;
  if ((n.tag === 'textarea' || n.tag === 'input') && n.attrs.value) {
    // 有 value → 直接显示值（小程序里 textarea 的 value 就是正文）
    const v = interp(n.attrs.value, data);
    inner = String(v || '').replace(/\n/g, '<br>');
  } else {
    inner = renderNodes(n.children, data);
  }
  const close = ['img'].includes(tag) ? '' : `</${tag}>`;
  return html + inner + close;
}

// ══════════════════════════════════════════════════════════════
// 4. WXSS → CSS
// ══════════════════════════════════════════════════════════════

function wxssToCss(src, isApp) {
  let css = src;

  // @import 展开（app.wxss 可能引入其他文件）
  css = css.replace(/@import\s+["']([^"']+)["'];?/g, (_, p) => {
    try {
      const f = path.join(MP, p);
      return fs.existsSync(f) ? wxssToCss(fs.readFileSync(f, 'utf8'), false) : '';
    } catch (e) { return ''; }
  });

  // rpx → px：375 设计宽，1rpx = 0.5px
  css = css.replace(/(-?[\d.]+)rpx/g, (_, v) => {
    const px = parseFloat(v) * 0.5;
    return (Number.isInteger(px) ? px : px.toFixed(2)) + 'px';
  });

  // page 选择器 → body（小程序的 page 就是页面根）
  // ⚠️ 只替换独立的 page，不能碰 .page / pages 等
  css = css.replace(/(^|[\s,}])page(\s*[{,])/g, '$1body$2');

  // :host / ::after 之类保持原样；小程序特有伪类丢弃
  css = css.replace(/::?\w+-placeholder/g, '::placeholder');

  return css;
}

// ══════════════════════════════════════════════════════════════
// 5. 组装页面
// ══════════════════════════════════════════════════════════════

const MOCK = require('./render_mock.js');

const PHONE_CSS = `
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;
}
/* 小程序里 view 是块级、text 是行内 */
div{display:block}
span{display:inline}
a{color:inherit;text-decoration:none;display:block}
img{display:block}
/* 小程序 button 默认 display:block + width:100% + 左右 padding，
   不显式给会让按钮缩成内容宽度（和真机完全不一样） */
button{
  font-family:inherit;border:0;background:none;
  display:block;width:100%;box-sizing:border-box;
  padding-left:7px;padding-right:7px;margin-left:auto;margin-right:auto;
  font-size:inherit;line-height:inherit;color:inherit;text-align:center;
}
/* 让 flex/grid 内部正常 */
img{max-width:100%}
`;

function buildPage(name, wxmlSrc, wxssSrc, appCss, data) {
  const tree = parseWxml(wxmlSrc);
  const body = renderNodes(tree.children, data);
  const pageCss = wxssToCss(wxssSrc, false);
  const appStyle = wxssToCss(appCss, true);

  return `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${name} · 页面预览</title>
<style>
${PHONE_CSS}
${appStyle}
/* ══ 页面样式（原样转自 ${name}.wxss）══ */
${pageCss}
/* ══ 预览容器 ══ */
/* ⚠️ 必须 overflow-x:hidden：页面里若有个别元素宽于 375，
   会把 body 撑宽、让 margin:auto 的居中偏移（踩过：截图整体右移 70px） */
html,body{background:#EDE5D8;padding:0;margin:0;overflow-x:hidden}
.screen{
  width:375px;min-height:812px;background:var(--bg-page,#F7F2EA);
  /* ⚠️ margin:0 而不是 auto：页面里个别元素宽于 375 时会把 body 撑宽，
     此时 auto 的居中会算出 69px 左边距，截图整体右移、右侧被裁。
     左对齐后无论 body 多宽，screen 都从 0 开始。 */
  margin:0;position:relative;overflow-x:hidden;
}
.wx-scroll{overflow:auto}
.wx-textarea{min-height:42px}
/* 广告位占位：虚线框 + 位置名（检查排布用，不是真实广告） */
.wx-ad-banner{
  margin:11px 12px 0;height:66px;border:1px dashed #C9B99F;border-radius:10px;
  background:repeating-linear-gradient(45deg,#FBF6EE,#FBF6EE 7px,#F5EEE2 7px,#F5EEE2 14px);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  color:#A08C6E;font-size:10px;
}
.wx-ad-tag{font-size:9px;font-weight:800;color:#B4671F;letter-spacing:1px}
.wx-ad-name{font-size:10.5px;font-weight:700;color:#8B7355;font-family:ui-monospace,Consolas,monospace}
.wx-ad-note{font-size:9px;color:#B5A895}
/* placeholder：小程序里是灰色提示文字，这里用 ::before 还原 */
[data-ph]::before{content:attr(data-ph);color:#B5A895;pointer-events:none}
[data-value]::after{content:""}
.wx-video,.wx-canvas,.wx-webview{
  background:repeating-linear-gradient(45deg,#EFE8DC,#EFE8DC 8px,#E7DFD1 8px,#E7DFD1 16px);
  display:flex;align-items:center;justify-content:center;
  color:#B5A895;font-size:11px;
}
.wx-video::after{content:"video 占位"}
.wx-canvas::after{content:"canvas 占位"}
.wx-webview::after{content:"web-view 占位"}
</style></head>
<body><div class="screen">
${body}
</div></body></html>`;
}

function main() {
  // 支持多个页名：node tools/render_pages.js index result
  const only = process.argv.slice(2).filter(Boolean);
  const appCss = fs.readFileSync(path.join(MP, 'app.wxss'), 'utf8');
  const appJson = JSON.parse(fs.readFileSync(path.join(MP, 'app.json'), 'utf8'));

  fs.mkdirSync(OUT, { recursive: true });

  const pages = appJson.pages
    .map(p => p.split('/')[1])
    .filter(n => !only.length || only.includes(n));

  let ok = 0, fail = 0;
  for (const name of pages) {
    const dir = path.join(MP, 'pages', name);
    const wxmlPath = path.join(dir, `${name}.wxml`);
    const wxssPath = path.join(dir, `${name}.wxss`);
    if (!fs.existsSync(wxmlPath)) { console.log(`  ⚠️  ${name}: 无 wxml`); continue; }

    try {
      const wxml = fs.readFileSync(wxmlPath, 'utf8');
      const wxss = fs.existsSync(wxssPath) ? fs.readFileSync(wxssPath, 'utf8') : '';
      const data = MOCK[name] || MOCK._default;
      const html = buildPage(name, wxml, wxss, appCss, data);
      const outFile = path.join(OUT, `${name}.html`);
      fs.writeFileSync(outFile, html, 'utf8');
      const kb = (Buffer.byteLength(html) / 1024).toFixed(0);
      console.log(`  ✓ ${name.padEnd(14)} ${kb.padStart(5)} KB`);
      ok++;
    } catch (e) {
      console.log(`  ✗ ${name.padEnd(14)} ${e.message}`);
      fail++;
    }
  }
  console.log(`\n渲染完成：${ok} 成功${fail ? `，${fail} 失败` : ''}`);
  console.log(`输出目录：${OUT}`);
}

main();
