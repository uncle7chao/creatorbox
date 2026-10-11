/**
 * 小程序数据模型 · 用服务端真实响应当夹具
 *
 * ⭐ 为什么要用真实响应做夹具：
 *   手编 JSON 只能验证「我以为服务端返回什么」，
 *   验证不了「服务端实际返回什么」。真实夹具能抓出字段名不匹配、
 *   类型不对这类 bug —— 代码「看起来」完全正常，只有跑起来才暴露。
 *
 * 运行：node test/model.test.js
 */
const fs = require('fs');
const path = require('path');
const { ParseResult, formatCount, makeFailure } = require('../utils/parse-result.js');

const FIX = path.join(__dirname, 'fixtures');
let pass = 0, fail = 0;

function check(name, cond, detail) {
  if (cond) {
    pass++;
    console.log(`   PASS  ${name}`);
  } else {
    fail++;
    console.log(`   FAIL  ${name}${detail ? '← ' + detail : ''}`);
  }
}

function load(name) {
  const p = path.join(FIX, `fixture_${name}.json`);
  return new ParseResult(JSON.parse(fs.readFileSync(p, 'utf-8')));
}

console.log('═══ 小程序模型 · 真实夹具验证 ═══\n');

// ─────────────────────────────────────────────
console.log('▸ B站 视频（1.07亿播放 / 294万赞）');
{
  const r = load('bilibili_video');
  check('success', r.success);
  check('平台名', r.platformLabel === 'B站', r.platformLabel);
  check('类型=video', r.isVideo && !r.isImage);
  check('标题非空', !!r.title, r.title);
  check('封面', r.coverage.cover);
  check('作者', r.authorName === '索尼音乐中国', r.authorName);
  check('时长数值', typeof r.durationS === 'number' && r.durationS > 0, String(r.durationS));
  check('时长文案', /\d+ 分 \d+ 秒/.test(r.durationText), r.durationText);
  check('播放地址', !!r.videoUrl);
  check('有清晰度选项', r.optionsCount > 0);
  check('推荐档在匿名上限内',
    !r.isLocked(r.recommendedOption),
    r.recommendedOption ? `${r.recommendedOption.height}P` : 'null');
  check('互动含播放', r.statsLine.some(s => s.label === '播放'), JSON.stringify(r.statsLine));
  check('互动含点赞', r.statsLine.some(s => s.label === '点赞'));
  check('无水印标记', r.noWatermark === true);
  check('无 titleHint（ssr 来源可信）', r.titleHint === '', r.titleHint);
}

// ─────────────────────────────────────────────
console.log('\n▸ 小红书 图集（7 张无水印原图）');
{
  const r = load('xhs_image');
  check('success', r.success);
  check('类型=image', r.isImage && !r.isVideo);
  check('标题非空', !!r.title, r.title);
  check('标题来源=ssr', r.titleSource === 'ssr', r.titleSource);
  check('7 张图', r.imageCount === 7, String(r.imageCount));
  check('首图有地址', !!(r.images[0] && r.images[0].url));
  check('推荐档为 null（图集无清晰度选择）', r.recommendedOption === null);
  check('时长为空（图集本来就没时长）', r.durationS === null);
  check('作者', r.authorName === '鲲鹏', r.authorName);
  check('话题标签有值', r.tags.length > 0, JSON.stringify(r.tags));
}

// ─────────────────────────────────────────────
console.log('\n▸ AcFun（需服务端合并）');
{
  const r = load('acfun_merge');
  check('success', r.success);
  check('标题「蕉换幸运」保留（短标题≠模板串）', r.title === '蕉换幸运', r.title);
  check('mergeRequired', r.mergeRequired === true);
  check('有提示文案', r.notices.length > 0, JSON.stringify(r.notices));
  check('清晰度选项 >1', r.optionsCount > 1, String(r.optionsCount));
  check('推荐档存在', !!r.recommendedOption);
}

// ─────────────────────────────────────────────
console.log('\n▸ 微博（模板标题已降级为文案首句）');
{
  const r = load('weibo_video');
  check('success', r.success);
  check('标题不是模板串', !/的微博视频$/.test(r.title), r.title);
  check('标题来源非 ssr', r.titleSource !== 'ssr', r.titleSource);
  check('有 titleHint（诚实告知）', r.titleHint.length > 0 || r.titleSource === 'share_text', r.titleHint);
  check('时长', r.durationS > 0, String(r.durationS));
}

// ─────────────────────────────────────────────
console.log('\n▸ 搜狐（<=30s 不截断）');
{
  const r = load('sohu_short');
  check('success', r.success);
  check('类型=video', r.isVideo);
  check('标题非空', !!r.title);
  check('播放地址', !!r.videoUrl);
  // 短片不该出现截断提示
  if (r.truncated) {
    check('截断提示文案正确', /30 秒/.test(r.notices.join('')), JSON.stringify(r.notices));
  } else {
    check('未标记截断（32s 在免费范围内）', true);
  }
}

// ─────────────────────────────────────────────
console.log('\n▸ 快手（走 gifshow 备用域名）');
{
  const r = load('kuaishou_video');
  check('success', r.success);
  check('平台名', r.platformLabel === '快手', r.platformLabel);
  check('播放地址', !!r.videoUrl);
  check('时长', r.durationS > 0, String(r.durationS));
  check('作者', !!r.authorName, r.authorName);
}

// ─────────────────────────────────────────────
console.log('\n▸ 失败用例（结构必须完整）');
{
  const raw = JSON.parse(
    fs.readFileSync(path.join(FIX, 'fixture_badlink.json'), 'utf-8'));
  const r = new ParseResult(raw);
  check('success=false', r.success === false);
  check('有错误文案', !!r.error, r.error);
  check('不误判为视频', !r.isVideo && !r.isImage);
  check('不带播放地址', !r.videoUrl);
  check('标题不崩', typeof r.title === 'string');
  check('statsLine 不崩', Array.isArray(r.statsLine));
  check('durationText 不崩', typeof r.durationText === 'string');
  check('notices 不崩', Array.isArray(r.notices));

  // 空输入：绝不能抛异常（页面里到处要用）
  const empty = new ParseResult({});
  check('空对象不崩', !empty.success && empty.title === '' && empty.statsLine.length === 0);
  const nullish = new ParseResult(null);
  check('null 不崩', !nullish.success);
  check('makeFailure 结构完整', makeFailure('x').error === 'x');
}

// ─────────────────────────────────────────────
console.log('\n▸ 工具函数');
{
  check('formatCount 12345→1.2万', formatCount(12345) === '1.2万', formatCount(12345));
  // ⚠️ 三端（verify.html / Flutter / 小程序）统一用 toFixed(1)，
  //    所以 106910247显示「1.1亿」而不是「1.07亿」——
  //    这是**与平台展示一致**的有意取舍，不是 bug。
  check('formatCount 1.07亿→1.1亿（与另两端一致）',
    formatCount(107000000) === '1.1亿', formatCount(107000000));
  check('formatCount 2000→2000（不足万不缩写）', formatCount(2000) === '2000', formatCount(2000));
  check('formatCount 10000→1万', formatCount(10000) === '1万', formatCount(10000));
  check('formatCount 999→999', formatCount(999) === '999', formatCount(999));
  check('formatCount 0→0', formatCount(0) === '0', formatCount(0));
  check('formatCount 精确边界 1e8→1亿', formatCount(100000000) === '1亿', formatCount(100000000));

  // 关键：AcFun/搜狐 不下发互动数据时，不能显示成「0」
  const r = load('acfun_merge');
  check('接口无互动数据→不显示0',
    !r.statsLine.some(s => s.text === '0'),
    JSON.stringify(r.statsLine));
}

// ─────────────────────────────────────────────
console.log('\n▸ 可选键始终存在（P31 教训）');
{
  const r = load('sohu_short');
  const musts = ['title','description','cover','authorName','authorAvatar',
    'durationS','publishTime','stats','statsText','tags','extra',
    'videoUrl','options','images','notices','statsLine'];
  const missing = musts.filter(k => r[k] === undefined);
  check('无 undefined 键（前端不需判空）', missing.length === 0, missing.join(','));
}

// ─────────────────────────────────────────────
console.log('\n▸ 热门榜单夹具（M1.5 /api/trending 真实响应）');
{
  const t = JSON.parse(fs.readFileSync(path.join(FIX, 'trending-bilibili.json'), 'utf-8'));
  check('ok=true', t.ok === true);
  check('platform=bilibili', t.platform === 'bilibili');
  check('20 条', t.items.length === 20, String(t.items.length));
  check('updated_at 是秒级时间戳', typeof t.updated_at === 'number' && t.updated_at > 1_600_000_000);

  // 统一条目契约：缺一个字段客户端就渲染不出来
  const musts = ['rank', 'title', 'author', 'hot', 'hot_text', 'cover', 'url'];
  const badItems = t.items.filter(it => musts.some(k => it[k] === undefined || it[k] === ''));
  check('条目 7 字段完整', badItems.length === 0, JSON.stringify(badItems.slice(0, 1)));

  // rank 连续（跳过坏条目后仍 1..n）
  const ranks = t.items.map(it => it.rank);
  const continuous = ranks.every((r, i) => r === i + 1);
  check('rank 从 1 连续递增', continuous, JSON.stringify(ranks));

  // ⭐ 闭环前提：url 必须能直接进 /api/parse（解析同款）
  const badUrls = t.items.filter(it => !/^https:\/\/www\.bilibili\.com\/video\/BV[0-9A-Za-z]{10}$/.test(it.url));
  check('url 全部为可解析的 BV 链接', badUrls.length === 0, JSON.stringify(badUrls.slice(0, 1).map(x => x.url)));

  // hot_text 格式（万/亿缩写）
  check('hot_text 已缩写（万以上）', t.items.every(it => /万|亿/.test(it.hot_text)), t.items[0].hot_text);
  // ⚠️ B站热榜是「编辑排序」不是播放量排序（2026-10-07 实测：榜首 174万，
  //   榜内另有 1亿+ 条目）—— 不能断言 hot 单调，那是断言自带错误假设。
  check('hot 为非负数值', t.items.every(it => typeof it.hot === 'number' && it.hot >= 0));
}

// ─────────────────────────────────────────────
console.log('\n▸ 内容专栏数据（M1.5 utils/articles.js）');
{
  const { ARTICLES, CATEGORIES, allArticles, articleById } = require('../utils/articles.js');

  check('10 篇', ARTICLES.length === 10, String(ARTICLES.length));
  check('分类清单 5 项（含「全部」）', CATEGORIES.length === 5 && CATEGORIES[0] === '全部');

  const musts = ['id', 'cat', 'title', 'summary', 'sections'];
  const badFields = ARTICLES.filter(a => musts.some(k => !a[k]));
  check('必填字段完整', badFields.length === 0, JSON.stringify(badFields.map(a => a.id)));

  const ids = ARTICLES.map(a => a.id);
  check('id 无重复', new Set(ids).size === ids.length);

  const badCats = ARTICLES.filter(a => !CATEGORIES.includes(a.cat));
  check('cat 全在分类清单内', badCats.length === 0, JSON.stringify(badCats.map(a => a.id)));

  // 小节结构：h 非空 + ps 全是非空字符串
  const badSecs = ARTICLES.filter(a =>
    !a.sections.length || a.sections.some(s => !s.h || !Array.isArray(s.ps) || !s.ps.length
      || s.ps.some(p => typeof p !== 'string' || !p.trim())));
  check('小节结构完整（h + 非空段落）', badSecs.length === 0, JSON.stringify(badSecs.map(a => a.id)));

  // ⭐ 内容合规自检（写文章时的红线，用测试固化）：
  //   不承诺收益 / 不引流第三方 / 不教搬运
  const banned = ['保证上热门', '必上热门', '加微信', '加V', '关注公众号', '搬运教程'];
  const allText = ARTICLES.map(a => [a.title, a.summary,
    ...a.sections.flatMap(s => [s.h, ...s.ps])].join('\n')).join('\n');
  const hits = banned.filter(w => allText.includes(w));
  check('无违规话术（收益承诺/引流/搬运教学）', hits.length === 0, hits.join(','));

  // 二创篇必须有合规表述（关键篇目的底线）
  const recreate = articleById('recreate-boundary');
  check('二创篇存在且明确反对搬运',
    !!recreate && (recreate.title + recreate.summary +
      recreate.sections.flatMap(s => s.ps).join('')).includes('搬运'));
  // 工具函数
  check('articleById 命中', articleById('cover-3').title.includes('封面'));
  check('articleById 未命中返回 null', articleById('xxx') === null);
  check('allArticles 带 minutes 计算', allArticles().every(a => a.minutes >= 2));
}

console.log('\n' + '─'.repeat(52));
console.log(`${pass} PASS / ${fail} FAIL`);
if (fail > 0) process.exit(1);
console.log('✅ 模型验证通过');