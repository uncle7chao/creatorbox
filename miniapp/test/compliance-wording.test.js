/**
 * 界面文案合规检查（小程序 + Flutter）
 *
 * ⭐ 为什么需要这个
 * ---------------
 * 「去水印」是微信审核语境里的刺眼词。我们做的能力是
 * 「获取平台在分发环节就干净的原始文件」，**不是**「擦除他人作品上的
 * 版权标识」—— 后者才是《小程序运营规范》4.3「不为违法行为提供便利」
 * 禁止的。措辞把自己放进「水印擦除工具」类目，等于主动送驳回。
 *
 * 2026-10-22 统一改为「解析视频」。本测试防止以后被改回去 ——
 * 改文案时最容易顺手带出敏感词，而审核驳回是事后才知道的。
 *
 * ⚠️ 关键区分：**只查用户可见的界面文案**（wxml 文本、dart 里的 UI 字符串）。
 *    代码注释与技术文档里的「去水印」是决策依据与事实描述
 *    （如「抖音的去水印原理」），删掉反而丢失技术准确性 —— 不查它们。
 *
 * 运行：node test/compliance-wording.test.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const APP_ROOT = path.join(ROOT, '..');

let pass = 0, fail = 0;

function check(name, cond, detail) {
  if (cond) { pass++; console.log(`   PASS  ${name}`); }
  else { fail++; console.log(`   FAIL  ${name}${detail ? '  ← ' + detail : ''}`); }
}

function read(p) { return fs.readFileSync(p, 'utf8'); }

// ── 1. 禁用的措辞 ──────────────────────────────────────────────────────
// ⚠️ 2026-10-23 补：「去掉水印」曾经漏网。
//   首页 hero 主标题写的是「去掉水印 只要干净素材」——
//   它**不等于**「去水印」（中间多了个「掉」字），所以老的词条匹配不到。
//   ⭐ 教训：禁词表必须覆盖**变体**，不能只列最标准的那一种写法。
const BANNED = [
  { word: '去水印', why: '把自己放进「水印擦除工具」类目' },
  { word: '去掉水印', why: '「去水印」的变体（多一个「掉」字，曾漏网）' },
  { word: '去水印解析', why: '同上' },
  { word: '去掉水印解析', why: '同上' },
  { word: '擦除水印', why: '同上' },
  { word: '去除水印', why: '同上' },
  { word: '消除水印', why: '同上' },
  { word: '水印擦除', why: '同上' },
  { word: '无水印下载', why: '「下载」+「无水印」组合易被判为资源搬运' },
];

// ── 2. 小程序：所有 wxml 的可见文本 ─────────────────────────────────────
console.log('\n── 1. 小程序界面文案（.wxml 可见文本）──');
const miniPages = path.join(ROOT, 'pages');
let wxmlCount = 0;
for (const dir of fs.readdirSync(miniPages)) {
  const wxml = path.join(miniPages, dir, `${dir}.wxml`);
  if (!fs.existsSync(wxml)) continue;
  wxmlCount++;
  const src = read(wxml);
  // 只取标签内的文本（去掉注释与属性值，避免误报）
  const visible = src
    .replace(/<!--[\s\S]*?-->/g, '')          // 去注释
    .replace(/<[^>]+>/g, ' ')                  // 去标签
    .replace(/[a-zA-Z]+="[^"]*"/g, ' ');       // 去属性
  for (const b of BANNED) {
    check(`${dir}.wxml 不含「${b.word}」`, !visible.includes(b.word),
      visible.includes(b.word) ? `出现于界面文本：${b.why}` : '');
  }
}
check(`已扫描 ${wxmlCount} 个 wxml 页面`, wxmlCount >= 10, `只扫到 ${wxmlCount} 个`);

// ── 3. 小程序：JS 里 setData 的字符串（会显示到界面的）────────────────
console.log('\n── 2. 小程序 JS 中的界面字符串 ──');
for (const dir of fs.readdirSync(miniPages)) {
  const js = path.join(miniPages, dir, `${dir}.js`);
  if (!fs.existsSync(js)) continue;
  const src = read(js);
  // 只看 setData({...}) 里的字符串值
  const setDataBlocks = src.match(/setData\(\{[\s\S]*?\}\)/g) || [];
  for (const blk of setDataBlocks) {
    for (const b of BANNED) {
      check(`${dir}.js 的 setData 不含「${b.word}」`, !blk.includes(b.word),
        blk.includes(b.word) ? b.why : '');
    }
  }
}

// ── 4. Flutter：UI 字符串 ─────────────────────────────────────────────
console.log('\n── 3. Flutter 界面文案（.dart 的 Text 字符串）──');
const flutterLib = path.join(APP_ROOT, 'app_flutter', 'lib');
if (fs.existsSync(flutterLib)) {
  const walk = (dir) => {
    for (const f of fs.readdirSync(dir)) {
      const p = path.join(dir, f);
      if (fs.statSync(p).isDirectory()) { walk(p); continue; }
      if (!f.endsWith('.dart')) continue;
      const src = read(p);
      // Text('...') / Text("...") 里的字面量
      const texts = src.match(/Text\(\s*'[^']*'/g) || [];
      for (const t of texts) {
        for (const b of BANNED) {
          check(`${f} 的 Text 不含「${b.word}」`, !t.includes(b.word),
            t.includes(b.word) ? `${t.slice(0, 50)} ← ${b.why}` : '');
        }
      }
    }
  };
  walk(flutterLib);
} else {
  check('找到 app_flutter/lib 目录', false, '路径不存在');
}

// ── 5. 正确表述存在（防止改过头）──────────────────────────────────────
console.log('\n── 4. 正确表述已就位 ──');
const homeDart = path.join(flutterLib, 'pages', 'home_page.dart');
if (fs.existsSync(homeDart)) {
  const src = read(homeDart);
  check('Flutter 首页使用「解析视频」', src.includes('解析视频'),
    '应有一键解析视频');
}
const ranking = path.join(miniPages, 'ranking', 'ranking.wxml');
if (fs.existsSync(ranking)) {
  check('小程序榜单页使用「解析视频」', read(ranking).includes('解析视频'));
}

console.log(`\n${'─'.repeat(56)}`);
console.log(`界面文案合规：${pass} PASS / ${fail} FAIL`);
if (fail) {
  console.log('❌ 有失败项 —— 敏感措辞会直接影响审核');
  process.exit(1);
}
console.log('✅ 全部通过');
console.log('（代码注释与技术文档中的技术描述不在检查范围 —— 那是事实与决策依据）');
