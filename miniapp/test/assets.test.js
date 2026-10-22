/**
 * 素材清单测试（2026-10-22 竞品对齐）
 *
 * 这块UI 的核心不是「长得像竞品」，而是这张表里列的每一样东西
 * **必须真的能拿到**。列一个点了没反应的动作，比不列更糟——
 * 用户会以为是 bug，下次就不信这个页面了。
 *
 * 所以重点测的是：
 *   ① 有素材才列，没素材不列
 *   ② 每个动作都能映射到真实存在的实现
 *   ③ 不泄露配额（封面不扣次数）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

const PASS = [], FAIL = [];
const check = (name, cond, detail) => {
  (cond ? PASS : FAIL).push(name);
  if (!cond) console.log('  ❌ ' + name + (detail ? '  | ' + detail : ''));
};

const wxml = read('pages/result/result.wxml');
const js = read('pages/result/result.js');
const wxss = read('pages/result/result.wxss');
const saver = read('utils/saver.js');

// ── 1. 清单区块存在且数据源正确 ────────────────────────────────
check('WXML 有素材清单区块', /class="assets"/.test(wxml));
check('清单按 assets 循环渲染', /wx:for="\{\{assets\}\}"/.test(wxml));
check('空清单时整块不渲染', /wx:if="\{\{assets\.length\}\}"/.test(wxml));
check('动作带 data-act 供分发', /data-act="\{\{a\.key\}\}"/.test(wxml));
check('动作绑定到统一分发器', /bindtap="onAssetAction"/.test(wxml));

// ── 2. 类型图标：CSS 绘制，不用 emoji / 图片 ───────────────────
check('四种类型图标都有 CSS 类', ['as-tri', 'as-img', 'as-txt', 'as-wave']
  .every(c => new RegExp('\\.' + c + '\\b').test(wxss)));
check('图标不依赖图片资源', !/as-ic.*\.(png|jpg|svg)/.test(wxss));

// ── 3. 固定四行 + 缺项灰显（2026-10-22 用户要求的设计变更）─────────
const src = js.slice(js.indexOf('buildAssets(r)'),
                     js.indexOf('onAssetAction(e)'));
check('buildAssets 存在', src.length > 200, `切片长度 ${src.length}`);

// ⭐ 固定 4 行：视频 / 封面 / 标题文案 / 话题，**都要 push**（不管有没有值）
check('四行都无条件 push（缺项也要占位）',
  /key: 'video'/.test(src) &&
  /key: 'cover'/.test(src) &&
  /key: 'text'/.test(src) &&
  /key: 'tags'/.test(src));
// ⭐⭐ 这一条才是「固定四行」的关键断言：
//   每一行的 push 都**不能**被 if 包着（包了 = 缺项隐藏 = 回到旧设计）。
//   ⭐ 自证时发现：只查 key 存在是不够的 —— 把话题行改成
//      `if (tags.length) list.push({...})` 后，测试竟然全绿。
//      所以必须断言「push 前面没有 if 守卫」。
{
  const rows = ['video', 'cover', 'text', 'tags'];
  rows.forEach(k => {
    const idx = src.indexOf(`key: '${k}'`);
    if (idx < 0) { check(`${k} 行存在`, false); return; }
    // 从 push( 往前看 260 字符，若出现 if ( 则说明被条件包住
    const before = src.slice(Math.max(0, idx - 260), idx);
    const guarded = /if\s*\([^)]*\)\s*(?:\{\s*)?$/.test(before) ||
                    /if\s*\([^)]*\)\s*list\.push/.test(before);
    check(`${k} 行无条件 push（不被 if 守卫 → 缺项也占位）`, !guarded,
      `该行被 if 包住了：...${before.slice(-90).trim()}`);
  });
}
check('每行都有 empty 标记',
  (src.match(/empty:/g) || []).length >= 4,
  `empty 出现 ${(src.match(/empty:/g) || []).length} 次`);
check('每行都有 emptyText（用于点击提示）',
  (src.match(/emptyText:/g) || []).length >= 4,
  `emptyText 出现 ${(src.match(/emptyText:/g) || []).length} 次`);
check('空项文案统一为「本视频没有xx」',
  /emptyText: '本视频没有视频'/.test(src) &&
  /emptyText: '本视频没有封面'/.test(src) &&
  /emptyText: '本视频没有文案'/.test(src) &&
  /emptyText: '本视频没有话题'/.test(src));
check('封面行判空考虑了图集（有图不算没有封面）',
  /hasImages/.test(src) && /empty: !hasCover && !hasImages/.test(src),
  '图集场景不能显示「本视频没有封面」');
check('图集时封面行变成「图片 N 张 / 全部保存」',
  // ⚠️ action key 是**条件表达式**（hasImages ? 'saveImages' : 'saveCover'），
  //   不是固定字面量 —— 所以要断言条件本身，不是断言 'images' 这个 key。
  /hasImages && !hasCover \? 'saveImages' : 'saveCover'/.test(src) &&
  /hasImages && !hasCover \? `图片 \$\{r\.images\.length\} 张` : '封面'/.test(src));
check('BGM 无 musicUrl 时不列', /if\s*\(r\.musicUrl\)/.test(src));
check('字幕无 subtitleText 时不列', /if\s*\(r\.subtitleText\)/.test(src));
// ⭐ 核心：不能有「配音」这类我们做不到的动作。
//   ⚠️ 注意要先剥掉注释 —— buildAssets 的注释里就写了
//   「竞品有配音→搜索相似声音，那是另一个服务的能力」，
//   那是【说明为什么不做】，不是动作本身。直接正则会误报。
const srcNoComment = src.replace(/\/\*[\s\S]*?\*\//g, '')
                          .replace(/^\s*\/\/.*$/gm, '');
check('不列我们不具备的能力（如配音/声音搜索）',
  !/配音|相似声音|voice/i.test(srcNoComment));
check('（对照）注释里确实说明了为何不做配音',
  /配音/.test(src) && /竞品/.test(src),
  '应保留决策依据，否则以后会有人「补上」这个动作');
check('动作 key 与实现一一对应（无占位动作）',
  // 每个 push 里的 key 都必须在分发映射表里出现
  (srcNoComment.match(/key: '(\w+)', label:/g) || []).every(m => {
    const k = m.match(/key: '(\w+)'/)[1];
    const tail = js.slice(js.indexOf('onAssetAction(e)'));
    return new RegExp("'\\s*" + k + "'\\s*:").test(tail) ||
           new RegExp(k + ":\\s*this\\.").test(tail);
  }),
  '存在未实现的 action key');

// （原「图集走全部保存而非单张」断言已并入上面的
//   「图集时封面行变成『图片 N 张 / 全部保存』」——
//   action key 现在是条件表达式，旧写法断言固定字面量会误报）

// ── 4. 动作分发：显式映射表，不动态执行 ────────────────────────
const disp = js.slice(js.indexOf('onAssetAction(e)'),
                       js.indexOf('onCopyTitle('));
check('用显式映射表分发', /const map = \{/.test(disp));
check('⭐ 不把 WXML 字符串当方法名直接执行',
  !/this\s*\[\s*key\s*\]|this\s*\[\s*act\s*\]/.test(disp));
check('未映射的动作被安全忽略', /typeof fn === 'function'/.test(disp));
check('saveImages 映射到既有批量保存', /saveImages:\s*this\.onSave/.test(disp));

// ── 5. 配额决策：封面不扣次数 ─────────────────────────────────
// 理由写在【函数上方的 JSDoc】里，防止以后有人「顺手补上扣减」
// 导致用户为几十 KB 的图片付视频下载的代价。
const coverFn = js.slice(js.indexOf('onSaveCover()'),
                         js.indexOf('onSaveCover()') + 1400);
const coverDoc = js.slice(Math.max(0, js.indexOf('onSaveCover()') - 700),
                          js.indexOf('onSaveCover()'));
check('保存封面不调用 afterSaved/consumeQuota',
  !/afterSaved|consume/.test(coverFn),
  '封面不应扣视频配额');
check('配额决策有注释说明（在函数上方的 JSDoc 里）',
  /配额不扣|不扣|配额保护/.test(coverDoc));

// ── 6. 错误路径必须给可操作提示 ───────────────────────────────
check('无封面时提示而非静默', /本视频没有封面/.test(coverFn));
check('权限被拒引导去设置', /wx\.openSetting/.test(coverFn));
check('区分权限与下载失败', /reason === 'auth'/.test(coverFn));
check('保存中防重复点击', /if\s*\(this\.data\.saving\)\s*return/.test(coverFn));
check('saving 状态被复位', /setData\(\{ saving: false \}\)/.test(coverFn));

check('无标题时不复制占位符',
  /=== '（无标题）'/.test(js) || /无标题/.test(js));

// ── 7. saver.saveImage 契约 ───────────────────────────────────
// ⚠️ 不能用 `module.exports = {[^}]*saveImage` —— 对象里含嵌套
//    调用（afterSaved 等），`[^}]*` 会在第一个 } 处截断导致误报。
check('saver 导出 saveImage',
  /module\.exports\s*=\s*\{/.test(saver) &&
  /saveImage/.test(saver.slice(saver.indexOf('module.exports'))));
check('saveImage 用 downloadFile + saveImageToPhotosAlbum',
  /function saveImage[\s\S]{0,900}?wx\.saveImageToPhotosAlbum/.test(saver));
check('saveImage 区分 auth 原因',
  /function saveImage[\s\S]{0,900}?reason: 'auth'/.test(saver));
check('⭐ 不重复实现下载逻辑（复用既有 download）',
  /function saveImage[\s\S]{0,300}?return download\(/.test(saver));

// ── 8. 空项拦截：点空项给「本视频没有xx」而不是静默 ─────────────
const dispSec = js.slice(js.indexOf('onAssetAction(e)'),
                         js.indexOf('onAssetAction(e)') + 900);
check('分发层统一拦截空项（不在每个动作里各写一遍）',
  /ds\.empty|empty === '1'/.test(dispSec) &&
  /emptyText/.test(dispSec));
check('空项提示用的是该行自己的文案',
  /String\(ds\.emptyText/.test(dispSec));
check('空项提示默认文案兜底',
  /本视频没有该内容/.test(dispSec));
check('空项不执行实际动作（提前 return）',
  /empty[\s\S]{0,220}?return;[\s\S]{0,120}?const map/.test(dispSec));
check('WXML 把 empty 标记传给动作',
  /data-empty="\{\{item\.empty \? 1 : 0\}\}"/.test(wxml) &&
  /data-empty-text="\{\{item\.emptyText\}\}"/.test(wxml));

// ── 9. 新增动作：复制话题 ────────────────────────────────────────
check('存在 onCopyTags', /onCopyTags\(\)/.test(js));
check('复制话题带上 # 号（少了 # 就只是普通词）',
  /tags\.map\(t => '#' \+ t\)\.join\(' '\)/.test(js));
check('无话题时给明确提示', /本视频没有话题/.test(js));
check('copyTags 在分发映射表里', /copyTags:\s*this\.onCopyTags/.test(js));
check('话题预览显示实际内容（用户一眼看到是什么）',
  /preview: tags\.slice/.test(src));

// ── 10. 标题文案：合成字段，避免 B站复制出 "-" ───────────────────
check('优先用服务端的 copy_text',
  /r\.copyText \|\| r\.description \|\| r\.title/.test(js));
check('模型层暴露 copyText',
  /this\.copyText\s*=/.test(read('utils/parse-result.js')));
check('文案行合并为一项（不拆标题/文案两行）',
  !/key: 'title'/.test(srcNoComment));

// ── 11. 视觉层级：不是每个动作都抢按钮 ─────────────────────────
check('每行只有一个主动作', /\.as-act-main\s*\{/.test(wxss));
check('次级动作是文字链样式', /\.as-act\s*\{[^}]*font-size/.test(wxss));

console.log(`\n════ 素材清单：${PASS.length} 通过 / ${FAIL.length} 失败`);
process.exit(FAIL.length ? 1 : 0);