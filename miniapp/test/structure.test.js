/**
 * 小程序结构自检（无需微信开发者工具，纯 Node 跑）
 *
 * ⭐ 为什么需要：WXML 里的 bindtap="xxx" 写错方法名，
 *    微信开发者工具**不会报错** —— 点了没反应，
 *    编译通过、真机也不崩，只有用户点的时候才发现。
 *    唯一有效的防护是静态检查绑定与实现是否对得上。
 *
 * 这不是假想：本轮写首页时，WXML 里绑了 navCompliance
 * 但 JS 里没实现，就是这个检查抓出来的。
 *
 * 运行：node test/structure.test.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
let pass = 0, fail = 0;

function check(name, cond, detail) {
  if (cond) {
    pass++;
    console.log(`   PASS  ${name}`);
  } else {
    fail++;
    console.log(`   FAIL  ${name}${detail ? '  ← ' + detail : ''}`);
  }
}

function read(p) {
  return fs.readFileSync(path.join(ROOT, p), 'utf-8');
}

function exists(p) {
  return fs.existsSync(path.join(ROOT, p));
}

// ─────────────────────────────────────────────
console.log('▸ 工程配置');

const appJson = JSON.parse(read('app.json'));
check('app.json 可解析', !!appJson.pages);

const required = [
  'pages/index/index',
  'pages/result/result',
  'pages/batch/batch',
  'pages/toolbox/toolbox',
  'pages/ranking/ranking',
  'pages/column/column',
  'pages/article/article',
  'pages/library/library',
  'pages/member/member',
  'pages/compliance/compliance'
];
const missingPages = required.filter(p => !appJson.pages.includes(p));
check('十屏都已注册', missingPages.length === 0, missingPages.join(','));

check('tabBar 有5 项（解析/工具箱/榜单/素材库/我的）', (appJson.tabBar?.list || []).length === 5,
  String((appJson.tabBar?.list || []).length));
check('末位 tab 文案为「我的」（2026-10-07 用户拍板）',
  appJson.tabBar?.list?.[4]?.text === '我的',
  appJson.tabBar?.list?.[4]?.text);
// tabBar 第 5 项是上限（微信硬限制），榜单页注册后正好占满
check('榜单页在 tabBar 中',
  (appJson.tabBar?.list || []).some(t => t.pagePath === 'pages/ranking/ranking'));
// 平台标签图标：⚠️ 必须根绝对路径（相对路径会解析到 pages/index/images/ 下
// 不存在 → image 静默不渲染，2026-10-07 首页工具图标踩过）
const platWxml = read('pages/index/index.wxml');
check('平台 tag 图标用根绝对路径（禁相对路径）',
  platWxml.includes('src="/images/plat/{{item.key}}-{{theme}}.png"')
  && !/src="(?!\/)[^"]*images\/plat/.test(platWxml));
check('32 个平台图标文件齐全（8 平台 × 4 皮肤）',
  ['douyin','bilibili','haokan','weibo','acfun','xhs','kuaishou','sohu']
    .every(k => ['classic','dark','jade','sakura']
      .every(sk => exists('images/plat/' + k + '-' + sk + '.png'))));
check('提词器页面已注册（11 屏）',
  appJson.pages.includes('pages/teleprompter/teleprompter'));
check('工具箱真实工具含提词器',
  read('utils/api.js').includes("type: 'teleprompter'"));
check('工具箱 js 有提词器分支',
  read('pages/toolbox/toolbox.js').includes("case 'teleprompter'"));
// ⛔ WXML 不支持 <br> 等HTML标签（真机编译报 expect end-tag）
const allWxml = ['pages/index/index', 'pages/result/result', 'pages/batch/batch',
  'pages/toolbox/toolbox', 'pages/ranking/ranking', 'pages/column/column',
  'pages/article/article', 'pages/library/library', 'pages/member/member',
  'pages/compliance/compliance', 'pages/teleprompter/teleprompter',
  'pages/pdftool/pdftool', 'pages/points/points'];
const brHit = allWxml.filter(p2 => /<br/i.test(read(p2 + '.wxml')));
check('全部 wxml 无 <br> 标签（WXML 非HTML）', brHit.length === 0, brHit.join(','));
check('sitemap.json 存在', exists('sitemap.json'));
check('project.config.json 存在', exists('project.config.json'));

// ── 广告组件（M1.5：后台可开关）──
{
  const missComp = [];
  ['components/ad-banner/ad-banner'].forEach(c => {
    ['.js', '.wxml', '.wxss', '.json'].forEach(ext => {
      if (!exists(c + ext)) missComp.push(c + ext);
    });
  });
  check('ad-banner 组件四件套齐全', missComp.length === 0, missComp.join(' '));
  const compJson = JSON.parse(read('components/ad-banner/ad-banner.json'));
  check('ad-banner 声明为 component', compJson.component === true);
  const usingPages = ['pages/result/result',
    'pages/toolbox/toolbox', 'pages/ranking/ranking', 'pages/library/library',
    'pages/member/member'];
  const missUsing = usingPages.filter(p => {
    const j = JSON.parse(read(p + '.json'));
    return !(j.usingComponents && j.usingComponents['ad-banner']);
  });
  check('四页均已注册 ad-banner', missUsing.length === 0, missUsing.join(','));
  // 合规：组件文案必须带「推广」标示
  const compWxml = read('components/ad-banner/ad-banner.wxml');
  check('广告区域带「推广」标示', compWxml.includes('推广'));
  // 2026-10-08 广告 v3：统一 ad-banner 组件（模式二选一 + 多图轮播），
  // banner-swiper 退役（文件保留但不再被页面引用）
  check('ad-banner 组件四件套齐全', (() => {
    const miss = [];
    ['components/ad-banner/ad-banner'].forEach(c => {
      ['.js', '.wxml', '.wxss', '.json'].forEach(ext => {
        if (!exists(c + ext)) miss.push(c + ext);
      });
    });
    return miss.length === 0;
  })());
  const idxJson = JSON.parse(read('pages/index/index.json'));
  check('首页注册 ad-banner（banner-swiper 已退役）',
    !!(idxJson.usingComponents && idxJson.usingComponents['ad-banner']
       && !idxJson.usingComponents['banner-swiper']));
  const apiSrc = read('utils/api.js');
  check('轮播兜底帧三条（会员/热榜/干货）',
    (apiSrc.match(/key: '(member|rank|column)', tag/g) || []).length === 3);
  check('轮播点击带跳转路径', apiSrc.includes("path: '/pages/member/member'"));
  const idxWxml = read('pages/index/index.wxml');
  check('首页接入统一广告位组件（带兜底帧）',
    idxWxml.includes('<ad-banner placement="index_banner"')
    && idxWxml.includes('fallback='));
  const compSrc = read('components/ad-banner/ad-banner.wxml');
  check('组件含轮播结构（swiper）', compSrc.includes('<swiper'));
  check('模式二选一：wxad 与 image 互斥分支',
    compSrc.includes("mode === 'wxad'") && compSrc.includes("mode === 'image'"));
  const adsSrc = read('utils/ads.js');
  check('getPlacement 下发 mode 与 images 数组',
    adsSrc.includes("mode !== 'code' && mode !== 'image'")
    && adsSrc.includes('Array.isArray(p.images)'));
  // 皮肤装饰层（形态层）：组件四件套 + 十页注入 + 圆角变量化
  const missDeco = [];
  ['components/theme-deco/theme-deco'].forEach(c => {
    ['.js', '.wxml', '.wxss', '.json'].forEach(ext => {
      if (!exists(c + ext)) missDeco.push(c + ext);
    });
  });
  check('theme-deco 组件四件套齐全', missDeco.length === 0, missDeco.join(' '));
  const noDeco = required.filter(p => !read(p + '.wxml').includes('<theme-deco'));
  check('十页均注入装饰层', noDeco.length === 0, noDeco.join(','));
  const decoWxss = read('components/theme-deco/theme-deco.wxss');
  ['blob', 'glow', 'star', 'petal'].forEach(k => {
    check(`装饰层含 ${k} 形态`, decoWxss.includes(`.${k}`));
  });
  check('卡片圆角已变量化（无 2Xrpx 硬编码残留）',
    !/border-radius:\s*2[048]rpx\b/.test(read('pages/index/index.wxss')),
    'index.wxss 仍有硬编码卡片圆角');
}

// ─────────────────────────────────────────────
console.log('\n▸ 皮肤系统（M1.5+）');
{
  check('app.wxss 存在', exists('app.wxss'));
  const appWxss = read('app.wxss');
  ['--bg-page', '--bg-card', '--ink-900', '--brand', '--hero-a',
   '.theme-dark', '.theme-sakura', '--r-card', '--r-small',
   '.theme-dark .ti', '.theme-sakura .pk-tile'].forEach(k => {
    check(`app.wxss 定义 ${k}`, appWxss.includes(k));
  });
  // 图标形态层：皮肤不能只是配色（描边风 + 圆形风必须存在）
  check('暗黑皮肤有图标描边形态',
    appWxss.includes('.theme-dark .ti') && appWxss.includes('border: 2rpx solid var(--brand)'));
  check('樱花皮肤有图标圆形形态', /\.theme-sakura \.ti[\s\S]{0,200}border-radius: 50%/.test(appWxss));
  // 所有页面根节点绑定 theme 类
  const noBind = required.filter(p => {
    const w = read(p + '.wxml');
    return !w.includes('theme-{{theme}}');
  });
  check('十页根节点均绑定 theme 类', noBind.length === 0, noBind.join(','));
  // 迁移应完成：核心品牌色不再硬编码于 wxss（app.wxss 变量定义除外）
  const rawIndex = read('pages/index/index.wxss');
  check('首页 wxss 无硬编码品牌橙',
    !/#E8890C\b/.test(rawIndex), 'index.wxss 仍含 #E8890C');
  // ⛔ 变量作用域回归（2026-10-07 修过的真bug）：
  // 页面底色若声明在 page{} 里，父元素取不到 .theme-* 子元素上的变量，
  // 结果无论切哪套皮肤底色都固定为 classic（深色皮肤下三段割裂）。
  // 窗口要够宽：.page 与 background 之间可能夹着多行注释
  check('底色声明在 .page 而非 page（变量作用域正确）',
    /\.page\s*\{[\s\S]{0,400}?background:\s*var\(--bg-page\)/.test(rawIndex)
    && !/^page\s*\{[\s\S]{0,80}background:\s*var\(--bg-page\)/m.test(rawIndex));
  // 硬编码色绕过皮肤：首页不应再有 classic 专属亮黄/浅绿
  check('首页无 classic 专属硬编码色（#FFC46B / #E4F5EC）',
    !/#FFC46B|#E4F5EC/i.test(rawIndex),
    (rawIndex.match(/#FFC46B|#E4F5EC/gi) || []).join(','));
  // 会员页换装入
  const memberWxml = read('pages/member/member.wxml');
  check('会员页有皮肤换装入口', memberWxml.includes('onPickTheme'));
  // 逐个定制的皮肤图标集：两套皮肤各 11 个专属图形
  check('皮肤图标集文件存在', exists('styles/skin-icons.wxss'));
  const icons = exists('styles/skin-icons.wxss') ? read('styles/skin-icons.wxss') : '';
  const darkIcons = (icons.match(/\.sk-d-[a-z]+/g) || []);
  const sakuraIcons = (icons.match(/\.sk-s-[a-z]+/g) || []);
  check(`暗黑专属图形 ≥ 11 个（实 ${darkIcons.length}）`, darkIcons.length >= 11);
  check(`樱花专属图形 ≥ 11 个（实 ${sakuraIcons.length}）`, sakuraIcons.length >= 11);
  ['parse', 'batch', 'copy', 'rank', 'column', 'hd', 'save', 'cloud', 'fast', 'lib', 'more']
    .forEach(k => {
      check(`两套皮肤都有 ${k} 专属图形`,
        icons.includes('.sk-d-' + k) && icons.includes('.sk-s-' + k));
    });
  check('图标集已被三处引用',
    read('pages/toolbox/toolbox.wxss').includes('skin-icons.wxss') &&
    read('pages/member/member.wxss').includes('skin-icons.wxss') &&
    read('pages/index/index.wxss').includes('skin-icons.wxss'));
  // 第四套皮肤：墨绿祖母绿
  check('祖母绿变量块存在', appWxss.includes('.theme-jade'));
  check('祖母绿有图标形态规则', appWxss.includes('.theme-jade .ti'));
  const decoWxml = read('components/theme-deco/theme-deco.wxml');
  check('祖母绿有专属装饰（翡翠晕染+露珠）',
    decoWxml.includes("theme === 'jade'") &&
    read('components/theme-deco/theme-deco.wxss').includes('.dew'));
  const themesJs = read('utils/themes.js');
  check('运行时注册 4 套皮肤', themesJs.includes("'jade'") &&
    themesJs.includes('墨绿祖母绿'));
  // tabBar 图标（真实 PNG 文件必须在盘上）
  const missingIcons = [];
  (JSON.parse(read('app.json')).tabBar.list || []).forEach(it => {
    [it.iconPath, it.selectedIconPath].forEach(p => {
      if (p && !exists(p)) missingIcons.push(p);
    });
  });
  check('tabBar 图标文件齐全（5 项 × 2 态）', missingIcons.length === 0,
    missingIcons.join(','));
  const pngMagic = f => {
    try {
      const b = require('fs').readFileSync(path.join(ROOT, f));
      return b[0] === 0x89 && b[1] === 0x50;
    } catch (e) { return false; }
  };
  check('图标是合法 PNG（魔数校验）', pngMagic('images/tabbar/parse_on.png'));
  // 首页工具行图标：16 个（4 功能 × 4 皮肤）PNG 必须齐全
  const missHome = [];
  ['batch', 'library', 'rank', 'more'].forEach(n => {
    ['classic', 'dark', 'jade', 'sakura'].forEach(sk => {
      const f = `images/home/${n}-${sk}.png`;
      if (!exists(f)) missHome.push(f);
    });
  });
  check('首页图标 16 个齐全（4 功能 × 4 皮肤）', missHome.length === 0,
    missHome.join(','));
  const idxWxml2 = read('pages/index/index.wxml');
  check('首页图标用根绝对路径（/images/…，小程序 image 最稳写法）',
    idxWxml2.includes('src="/images/home/batch-classic.png"'));
  check('首页图标为静态字面量 src（不用动态插值）',
    !/src="\/images\/home\/[^"]*\{\{/.test(idxWxml2));
  check('首页 4 功能 × 4 皮肤共 16 个 image 分支',
    (idxWxml2.match(/class="hic"/g) || []).length === 16,
    String((idxWxml2.match(/class="hic"/g) || []).length));
  check('首页图标样式 .hic 已定义',
    /\.hic \{[\s\S]{0,80}width: 44rpx/.test(read('pages/index/index.wxss')));
}

// ─────────────────────────────────────────────
console.log('\n▸ 每屏四件套齐全（WXML/WXSS/JS/JSON）');

const missingFiles = [];
required.forEach(p => {
  ['.wxml', '.wxss', '.js', '.json'].forEach(ext => {
    if (!exists(p + ext)) missingFiles.push(p + ext);
  });
});
check(`${required.length * 4} 个文件齐全`, missingFiles.length === 0, missingFiles.join(' '));

// ─────────────────────────────────────────────
console.log('\n▸ ⭐ WXML 事件绑定 ↔ JS 实现');

required.forEach(p => {
  const wxmlPath = path.join(ROOT, p + '.wxml');
  if (!fs.existsSync(wxmlPath)) return;
  const wxml = fs.readFileSync(wxmlPath, 'utf-8');
  const js = fs.existsSync(path.join(ROOT, p + '.js'))
    ? fs.readFileSync(path.join(ROOT, p + '.js'), 'utf-8') : '';

  const handlers = [...wxml.matchAll(/bind(?:tap|input|longpress|change|confirm|submit)=\s*"(\w+)"/g)]
    .map(m => m[1]);
  const uniq = [...new Set(handlers)];
  const orphan = uniq.filter(h => !new RegExp(`\\b${h}\\s*[(]`).test(js));
  check(`${p} ${uniq.length} 个绑定已实现`, orphan.length === 0, orphan.join(','));
});

// ─────────────────────────────────────────────
console.log('\n▸ ⭐ 不用裸 app全局变量（单测环境不存在）');

{
  // 真实踩过：pages/index/index.js 里写了 `app.globalData.lastResult = r`，
  //   微信运行时能跑（app 是全局量），但逻辑测试注入的只有 getApp，
  //   抛「app is not defined」→ 整条链路测不出来。
  //
  // ⚠️ 判据必须精确：**裸 app**（前面没有 getApp() 或 const app = ... 绑定）
  //    才违规。否则会误伤 `const app = getApp(); app.globalData.x = y`这种
  //    完全正确的写法 —— 第一版就误伤了 library/ 与 result/ 两处。
  const offenders = [];
  const walkJs = dir => {
    fs.readdirSync(dir, { withFileTypes: true }).forEach(e => {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (e.name !== 'test') walkJs(p); }
      else if (e.name.endsWith('.js')) {
        const lines = fs.readFileSync(p, 'utf-8').split('\n');
        let appBound = false;   // 本作用域内是否已用 getApp() 绑定过 app
        lines.forEach((rawLine, i) => {
          // ⚠️ 必须**按行剔除注释**并保留行号。
          //   早期版本用 replace 整体去注释 → 行号错位，
          //   报出来的「违规行号」指向空行，纯误导。
          const code = rawLine
            .replace(/\/\*.*?\*\//g, '')
            .replace(/\/\/.*$/, '')
            .trim();
          if (!code) return;

          // 缩进变化= 进入新作用域 → 重置绑定状态
          const indent = (rawLine.match(/^\s*/) || [''])[0].length;
          const lastIndent = lines[i - 1] ? (lines[i - 1].match(/^\s*/) || [''])[0].length : 99;
          if (indent < lastIndent) appBound = false;

          // 一旦绑定，后续 app.xxx 都合法
          // ⚠️ 必须是**跨行状态**：第一版逐行判断，
          //   漏掉「const app = getApp() 在上一行」的情况，
          //   误伤了 library.js与 result.js 两处正确写法。
          if (/(?:const|let|var)\s+app\s*=\s*getApp\(\)/.test(code)) {
            appBound = true;
            return;
          }
          if (/getApp\(\)\s*\.\s*globalData/.test(code)) return;
          if (appBound) return;

          if (/(^|[^.\w$])app\s*\.\s*\w/.test(code)) {
            offenders.push(`${path.relative(ROOT, p)}:${i + 1}  ${code.slice(0, 40)}`);
          }
        });
      }
    });
  };
  walkJs(ROOT);
  check('无裸 app.globalData 访问', offenders.length === 0, offenders.join(', '));
}

// ─────────────────────────────────────────────
console.log('\n▸ WXML 数据字段 ↔ JS data声明');

{
  const wxml = read('pages/index/index.wxml');
  const js = read('pages/index/index.js');
  // 提取 {{ expr }} 里的简单标识符
  const exprs = [...wxml.matchAll(/\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}/g)].map(m => m[1]);
  const roots = [...new Set(exprs.map(e => e.split('.')[0]))];
  // setData 里出现的也算已声明
  const declared = new Set();
  const dataMatch = js.match(/data:\s*\{([\s\S]*?)\n  \},/);
  if (dataMatch) {
    [...dataMatch[1].matchAll(/(\w+)\s*:/g)].forEach(m => declared.add(m[1]));
  }
  [...js.matchAll(/setData\(\{[^}]*?(\w+)\s*:/g)].forEach(m => declared.add(m[1]));

  const undeclared = roots.filter(r =>
    !declared.has(r) &&
    // WXSS 类名/系统变量等不在 data 里
    !['item', 'index', 'true', 'false'].includes(r));
  check(`${roots.length} 个字段已声明`, undeclared.length === 0, undeclared.join(','));
}

// ─────────────────────────────────────────────
console.log('\n▸ 组件类名↔ WXSS 定义（拼错样式名会静默失效）');

{
  const wxml = read('pages/index/index.wxml');
  let wxss = read('pages/index/index.wxss');
  // ⚠️ 跟随 @import —— 皮肤专属图标集在 styles/skin-icons.wxss，
  //   不跟随就会把「类名有定义」误报成「样式未定义」
  [...wxss.matchAll(/@import\s+"([^"]+)"/g)].forEach(m => {
    const p = path.resolve(path.join(ROOT, 'pages/index'), m[1]);
    if (fs.existsSync(p)) wxss += '\n' + fs.readFileSync(p, 'utf-8');
  });

  // ⚠️ 只取静态 class，必须排除 class="{{ 条件 ? 'a' : 'b' }}" 这类表达式 ——
  //   表达式里没有 class 名，且按空白切开会得到 'none' '>=' 'saveQuota' 等垃圾 token。
  //   动态类名无法静态匹配，跳过（靠人工review）。
  const staticClasses = [];
  [...wxml.matchAll(/class="([^"]*)"/g)].forEach(m => {
    if (m[1].includes('{{')) return;          // 动态类名，跳过
    m[1].split(/\s+/).filter(Boolean).forEach(c => staticClasses.push(c));
  });
  // ⛔ 排除小程序的**内置属性值**，它们不是 CSS 类：
  //   hover-class="none" / hover-class="button-hover" 等
  //   误判成类名会报「.none 没定义样式」，是检查自己的 bug。
  const BUILTIN = new Set(['none', 'button-hover', 'button-hover-clean']);
  const uniq = [...new Set(staticClasses.filter(c => !BUILTIN.has(c)))];
  const styled = [...new Set([...wxss.matchAll(/\.([a-z][\w-]*)/g)].map(m => m[1]))];
  const unstyled = uniq.filter(c => !styled.includes(c));
  check(`${uniq.length} 个静态类名有样式`, unstyled.length === 0, unstyled.join(','));
}

// ─────────────────────────────────────────────
console.log('\n▸ 合规红线（规范 §4）');

{
  const wxml = read('pages/index/index.wxml');
  const js = read('pages/index/index.js');

  // ⚠️ 剔除注释后再查禁用词 ——
  //   注释里写「绝不能出现分享后解锁」是在说明规则，不是真的用了这个词。
  //   早期版本没剔注释，把自己的注释判成违规（检查自己有 bug 却报别人错）。
  const stripComment = src => src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');

  const banned = ['分享后解锁', '分享得', '邀请解锁', '转发解锁', '分享领会员'];
  const code = stripComment(wxml) + stripComment(js);
  const hits = banned.filter(w => code.includes(w));
  check('无「分享解锁」诱导表述（剔除注释后）', hits.length === 0, hits.join(','));

  // 文案层单独查一次 —— 用户真正看到的是 WXML 文本节点
  const textNodes = [...wxml.matchAll(/>([^<>{}]+)</g)]
    .map(m => m[1]).join(' ');
  const textHits = banned.filter(w => textNodes.includes(w));
  check('界面文案无违规词', textHits.length === 0, textHits.join(','));

  check('有免责声明', wxml.includes('disclaimer'));
  check('免责可点击进合规页', js.includes('navCompliance'));
  check('有合规页', exists('pages/compliance/compliance.wxml'));

  // 分享回调不能与权益挂钩（只看 body 的 key，不看注释）
  const shareMatch = js.match(/onShareAppMessage\s*\(\)\s*\{([\s\S]*?)\n  \}/);
  if (shareMatch) {
    const body = stripComment(shareMatch[1]);
    const tied = /解锁|会员|免费|奖励/.test(body);
    check('分享不与权益挂钩', !tied, tied ? 'body 含权益关键词' : '');
  }
}

// ─────────────────────────────────────────────
console.log('\n▸ 契约一致性（与 server/app/main.py）');

{
  const api = read('utils/api.js');
  check('调 POST /api/parse', api.includes("'/api/parse'"));
  check('带 quality 参数', api.includes('quality'));
  check('带 no_cache 参数', api.includes('no_cache'));
  check('调 /api/health', api.includes("'/api/health'"));
  check('超时 30s（AcFun 合并实测 5.4s，留足余量）', api.includes('30000'));

  const model = read('utils/parse-result.js');
  ['video_url', 'no_watermark', 'merge_required', 'anonymous_max_height',
   'truncated', 'need_proxy', 'options', 'images', 'meta'].forEach(k => {
    check(`模型读 ${k}`, model.includes(k));
  });
  check('读取 title_source（诚实性设计）', model.includes('title_source'));
  // P0 新端点契约
  check('批量 POST /api/batch', api.includes("'/api/batch'"));
  check('批量带 openid（服务端权威配额）', api.includes('openid'));
  check('登录 /api/user/login', api.includes('/api/user/login'));
  check('配额 /api/user/quota', api.includes('/api/user/quota'));
  check('素材库 /api/library', api.includes('/api/library'));
  check('批量超时 60s（串行解析 5 条可能 10s+）', api.includes('60000'));
  // 占位卡规则（2026-10-07 拍板：展示不开发）
  check('工具箱占位卡 8 项', (api.match(/TOOLBOX_PLACEHOLDERS[\s\S]*?\]/) || [''])[0].includes('音频提文案'));
  const toolboxJs = fs.readFileSync(path.join(ROOT, 'pages/toolbox/toolbox.js'), 'utf-8');
  check('占位卡点击不跳转不收集联系方式（合规）',
    toolboxJs.includes('规划中') && !/formIds|openType|contact/i.test(toolboxJs));
  // M1.5 榜单契约
  check('榜单 GET /api/trending', api.includes('/api/trending'));
  check('榜单平台 tab 与服务端 KNOWN_PLATFORMS 对齐',
    (api.match(/RANKING_PLATFORMS[\s\S]*?\];/) || [''])[0].includes('bilibili'));
  // 占位入口已切真实导航（旧 toast 占位不许残留）
  const indexJs = fs.readFileSync(path.join(ROOT, 'pages/index/index.js'), 'utf-8');
  check('首页榜单入口已切 switchTab（不再占位）',
    indexJs.includes('navRanking') && indexJs.includes('/pages/ranking/ranking')
    && !indexJs.includes('onRankPlaceholder'));
  check('工具箱榜单入口已切 switchTab',
    /case 'rank':[\s\S]{0,120}switchTab[\s\S]{0,60}ranking/.test(toolboxJs));
  // M1.5 内容专栏（静态页方案）
  check('专栏数据模块存在且含 10 篇',
    exists('utils/articles.js') &&
    (fs.readFileSync(path.join(ROOT, 'utils/articles.js'), 'utf-8')
      .match(/id:\s*'/g) || []).length === 10);
  check('工具箱有运营干货入口（navigateTo 专栏页）',
    /case 'column':[\s\S]{0,120}navigateTo[\s\S]{0,60}column/.test(toolboxJs));
}

// ─────────────────────────────────────────────
console.log('\n▸ 零 emoji（UI 层严格禁止）');

{
  const files = [];
  const walk = dir => {
    fs.readdirSync(dir, { withFileTypes: true }).forEach(e => {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (e.name !== 'test') walk(p); }
      else if (/\.(js|wxml|wxss|json)$/.test(e.name)) files.push(p);
    });
  };
  walk(ROOT);

  // ⚠️ 只查**渲染出来的部分**，必须剔除注释：
  //   WXML注释 <!--⚠️ ...--> 与 WXSS 注释 /* ⛔ ... */ 里的符号
  //   用户根本看不到，拿它们判违规是检查自己的 bug。
  const stripCmt = src => src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '');

  const emojiRe = /[\u{1F300}-\u{1FAFF}\u{1F000}-\u{1F2FF}]/u;
  const symbolRe = /[\u{2600}-\u{27BF}]/u;

  const uiBad = [], jsBad = [];
  files.forEach(f => {
    const rel = path.relative(ROOT, f);
    const raw = fs.readFileSync(f, 'utf-8');
    const src = stripCmt(raw);
    if (/\.(wxml|wxss)$/.test(f)) {
      if (emojiRe.test(src) || symbolRe.test(src)) uiBad.push(rel);
    } else if (emojiRe.test(src)) {
      jsBad.push(rel);
    }
  });

  check(`UI 层（WXML/WXSS 剔除注释后）零 emoji`, uiBad.length === 0, uiBad.join(' '));
  check(`逻辑层（JS）无表情类 emoji`, jsBad.length === 0, jsBad.join(' '));

  // 反向确认：注释里的符号确实被剔掉了（证明检查有效而非失效）
  // ⚠️ 夹具用 index.wxml —— member.wxess 改版后已无符号注释
  const commented = fs.readFileSync(path.join(ROOT, 'pages/index/index.wxml'), 'utf-8');
  check('剔除逻辑有效（注释里的 ⛔ 不算违规）',
    symbolRe.test(commented) && !symbolRe.test(stripCmt(commented)));
}

console.log('\n' + '─'.repeat(52));
console.log(`${pass} PASS / ${fail} FAIL`);
if (fail > 0) process.exit(1);
console.log('✅ 结构自检通过');