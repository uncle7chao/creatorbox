/**
 * Flutter 端素材清单测试（2026-10-22，与小程序端同契约）
 *
 * 两端必须一致：
 *   · 固定 4 行（视频/封面/标题文案/话题）
 *   · 缺项灰显 + 点击提示「本视频没有xx」
 *   · 话题复制带 # 号
 *   · 标题文案用 copy_text（description 有效则用，否则回落 title）
 *
 * ⚠️ 为什么用正则而不是跑 Dart 测试：
 *   沙箱内 flutter test 需要 pub get（拉依赖），跑不了。
 *   这里做的是**结构与契约检查** —— 挡的是「改了一端忘了另一端」
 *   和「把固定四行改回有才列」这两类真实会犯的错。
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

const dart = read('lib/pages/parse_result_page.dart');
const miniJs = read('../miniapp/pages/result/result.js');

// ── 1. 四行固定 ────────────────────────────────────────────────
check('有 _assetRows 方法', /_assetRows\(/.test(dart));
['视频', '封面', '标题文案', '话题'].forEach(n => {
  check(`有「${n}」行`, dart.includes(`name: '${n}'`));
});
check('四行都无条件 add（不被 if 守卫 → 缺项也占位）',
  // 每一行的 name: 'xxx' 往前 200 字符内不应出现 "if ("
  ['视频', '封面', '标题文案', '话题'].every(n => {
    const idx = dart.indexOf(`name: '${n}'`);
    if (idx < 0) return false;
    const before = dart.slice(Math.max(0, idx - 200), idx);
    return !/if\s*\([^)]*\)\s*rows\.add/.test(before);
  }),
  '某行被 if 包住了（回到「有才列」旧设计）');

// ── 2. 缺项提示 ────────────────────────────────────────────────
['本视频没有视频', '本视频没有封面', '本视频没有文案', '本视频没有话题']
  .forEach(t => {
    check(`有提示「${t}」`, dart.includes(t));
  });
check('提示走统一方法 _toast', /void _toast\(/.test(dart));
check('缺项也走 onTap（不是死按钮）',
  /onTap: \(\) \{\s*if \([^)]*\) \{\s*_toast/.test(dart.replace(/\s+/g, ' ')) ||
  /onTap: \(\) \{[^}]*_toast\('本视频没有视频'/.test(dart));

// ── 3. 话题 ────────────────────────────────────────────────────
check('有 _tags getter', /List<String> get _tags/.test(dart));
check('复制话题带 # 号', /map\(\(t\) => '#\$t'\)/.test(dart));
check('话题数量进提示', /个话题已复制/.test(dart));

// ── 4. 标题文案 ────────────────────────────────────────────────
check('有 _copyText getter', /String get _copyText/.test(dart));
check('优先用服务端的 copy_text', /result\['copy_text'\]/.test(dart));
check('copy_text 空时回落 description',
  /result\['description'\]/.test(dart) && /!= '-'/ .test(dart),
  'B站 description 是 "-" 必须排除');
check('最后回落 title', /return _title/.test(dart));

// ── 5. 灰显 ────────────────────────────────────────────────────
check('缺项用 disabledColor', /theme\.disabledColor/.test(dart));
check('有 has 字段控制颜色', /has: /.test(dart));

// ── 6. 与小程序端契约一致 ──────────────────────────────────────
check('小程序端也有 copyTags 动作', /onCopyTags/.test(miniJs));
check('小程序端也有「本视频没有话题」', miniJs.includes('本视频没有话题'));
check('两端话题提示文案一致',
  dart.includes('本视频没有话题') && miniJs.includes('本视频没有话题'));
check('两端话题都带 # 号',
  /#\$t/.test(dart) && /'#' \+ t/.test(miniJs));

// ── 7. 类型安全 ────────────────────────────────────────────────
// ⚠️ 第一版用 List<Object?> + 下标强制转换，写错类型要到运行期才炸。
//   改成 record（有具名字段）后，编译期就能查出来。
check('素材行用 record（具名字段，编译期可查错）',
  /\{IconData icon, String name, bool has, String action, VoidCallback onTap\}/.test(dart));
check('不用 List<Object?> + 下标强转', !/List<Object\?>>\s*_assetRows/.test(dart));
check('渲染处用具名字段（row.icon 等）',
  /row\.icon/.test(dart) && /row\.name/.test(dart) &&
  /row\.has/.test(dart) && /row\.action/.test(dart) && /row\.onTap/.test(dart));

console.log(`\n════ Flutter 素材清单：${PASS.length} 通过 / ${FAIL.length} 失败`);
process.exit(FAIL.length ? 1 : 0);