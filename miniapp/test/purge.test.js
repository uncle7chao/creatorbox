/**
 * 注销账号专项测试（小程序侧，隐私保护指引 §四 删除权）
 *
 * ⭐ 关注两件事：
 *   1) WXML 绑定的 onPurgePreview 在 JS 里真的存在 —— 绑错方法名微信不报错，
 *      点了没反应，只有用户才发现（这正是 structure.test.js 抓过的历史坑）。
 *   2) 注销流程的安全属性：必须【预览 → 二次确认 → 才调接口】，
 *      且必须显式清掉本地身份缓存 —— 漏清会导致下次进来还拿着已注销的 openid。
 *
 * 无需微信开发者工具，纯 Node 跑：node test/purge.test.js
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

function read(p) { return fs.readFileSync(path.join(ROOT, p), 'utf8'); }

const memberJs = read('pages/member/member.js');
const memberWxml = read('pages/member/member.wxml');
const apiJs = read('utils/api.js');

// ── 1. 绑定与实现对得上 ────────────────────────────────────────────────────
console.log('\n── 1. WXML 绑定 ──');
check('WXML 绑定了 onPurgePreview', /bindtap="onPurgePreview"/.test(memberWxml));
check('member.js 实现了 onPurgePreview',
  /onPurgePreview\s*\(\s*\)\s*\{/.test(memberJs));
check('内部调用 _doPurge 有实现',
  /_doPurge\s*\(\s*openid\s*\)\s*\{/.test(memberJs));

// ── 2. 接口封装 ────────────────────────────────────────────────────────────
console.log('\n── 2. API 封装 ──');
check('api.js 导出 purgePreview', /purgePreview/.test(apiJs));
check('api.js 导出 purgeAccount', /purgeAccount/.test(apiJs));
check('预览走 preview_by_openid 端点', /preview_by_openid/.test(apiJs));
check('注销走 purge_by_openid 端点', /purge_by_openid/.test(apiJs));
// confirm 必须回传 openid（服务端会校验），不能空传
check('purgeAccount 带 confirm 字段',
  /data:\s*\{\s*openid,\s*confirm:\s*openid\s*\}/.test(apiJs));

// ── 3. ⭐ 安全属性：先预览再确认 ────────────────────────────────────────────
console.log('\n── 3. 安全流程（不可逆操作必须双闸）──');
check('调用前先拉预览', /api\.purgePreview\(/.test(memberJs));
// 顺序检查必须限定在 onPurgePreview 方法体内——
// 文件里更早的 onBridgeBind / onRedeemCode 也有 showModal，用全局 indexOf 会误判。
// ⚠️ 不要匹配含 \n 的多行字面量：本仓库文件是 CRLF 行尾，字面量匹配必然失败。
const purgeIdx = memberJs.indexOf('onPurgePreview()');
const previewIdx = memberJs.indexOf('api.purgePreview(', purgeIdx);
const modalIdx = memberJs.indexOf('确认注销账号', previewIdx);
check('预览成功后才弹确认框（顺序正确）',
  purgeIdx > -1 && previewIdx > purgeIdx && modalIdx > previewIdx,
  `purge=${purgeIdx} preview=${previewIdx} modal=${modalIdx}`);
check('弹的是二次确认（showModal）', /wx\.showModal\(\{[\s\S]*?title:\s*'确认注销账号？'/.test(memberJs));
check('确认文案明示不可恢复', /不可恢复/.test(memberJs));
check('弹窗带取消项（再想想）', /cancelText:\s*'再想想'/.test(memberJs));
check('用户取消时不调注销接口',
  /if\s*\(\s*!res\.confirm\s*\)\s*return;/.test(memberJs));
check('销毁数据标注为 danger 色', /confirmColor:\s*'#D92D20'/.test(memberJs));

// ── 4. ⭐ 注销后必须清本地缓存 ─────────────────────────────────────────────
console.log('\n── 4. 本地缓存清理 ──');
check('清除 openid', /wx\.removeStorageSync\(\s*'openid'\s*\)/.test(memberJs));
check('清除 user', /wx\.removeStorageSync\(\s*'user'\s*\)/.test(memberJs));
check('清除会员态', /wx\.removeStorageSync\(\s*'isMember'\s*\)/.test(memberJs));
// 限定在 _doPurge【方法定义】体内检查：先判成功、再清缓存，顺序不能反。
// 用 lastIndexOf —— 首次出现的是调用处。
const doPurgeIdx = memberJs.lastIndexOf('_doPurge(openid)');
const doPurgeBody = memberJs.slice(doPurgeIdx);
const guardAt = doPurgeBody.indexOf('statusCode !== 200');
const clearAt = doPurgeBody.indexOf("removeStorageSync('openid')");
check('注销成功才清（先判 statusCode===200 再清缓存）',
  doPurgeIdx > -1 && guardAt > -1 && clearAt > guardAt,
  `guard=${guardAt} clear=${clearAt}`);

// ── 5. 失败路径不能误清缓存 ────────────────────────────────────────────────
console.log('\n── 5. 失败处理 ──');
check('非 200 时提前 return（不清缓存）',
  /if\s*\(\s*statusCode\s*!== 200\s*\|\|\s*!data\s*\|\|\s*!data\.ok\s*\)[\s\S]{0,200}?return;/.test(memberJs));
check('失败时提示而非静默',
  /title:\s*'注销未完成'/.test(memberJs));
// ⚠️ 边界：`this._doPurge(openid)` 的【调用】也出现在 onPurgePreview 内，
// 首次 indexOf 命中的是调用处而非方法定义处 —— 必须取最后一次出现（定义处）。
// 另：仓库是 CRLF 行尾，不能用含 \n 的多行字面量。
const defAt = memberJs.lastIndexOf('_doPurge(openid)');
const purgeSec = memberJs.slice(memberJs.indexOf('onPurgePreview()'), defAt);
const doPurgeSec2 = memberJs.slice(defAt);
const catchToast = sec => /\.catch\([\s\S]{0,300}?showToast/.test(sec);
check('预览请求异常也提示', catchToast(purgeSec),
  '预览段内未找到 catch+showToast');
check('注销请求异常也提示', catchToast(doPurgeSec2),
  '注销段内未找到 catch+showToast');
check('未登录时直接拦下', /if\s*\(\s*!openid\s*\)[\s\S]{0,120}?showToast/.test(memberJs));

// ── 6. 样式类齐备（WXML 用的类必须在 wxss 有定义）───────────────────────────
console.log('\n── 6. 样式类定义 ──');
const memberWxss = read('pages/member/member.wxss');
for (const cls of ['mi-body', 'mi-s', 'mi-danger', 'danger-note']) {
  check(`.${cls} 有样式定义`, new RegExp(`\\.${cls}\\s*\\{`).test(memberWxss));
}
// 复用类不该重复定义
check('复用 .sec / .mi / .mi-t / .mi-arrow（未重复定义）',
  !/\.sec\s*\{/.test(memberWxss.split('/* ── 账号安全区')[1] || ''));

// ── 7. 文案合规 ────────────────────────────────────────────────────────────
console.log('\n── 7. 文案 ──');
check('明写不可恢复', /不可恢复/.test(memberWxml));
check('说明哪些不受影响（运营数据）', /不受影响/.test(memberWxml));
check('未使用敏感词「去水印」', !/去水印/.test(memberWxml));

console.log(`\n${'─'.repeat(56)}`);
console.log(`注销账号：${pass} PASS / ${fail} FAIL`);
if (fail) {
  console.log('❌ 有失败项');
  process.exit(1);
}
console.log('✅ 全部通过');