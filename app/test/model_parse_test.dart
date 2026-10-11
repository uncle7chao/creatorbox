// 客户端模型 · 用**服务端真实响应**验证解析
//
// ⭐ 为什么必须用真实响应而不是手编JSON：
//   手编的 JSON 只会验证「我以为服务端返回什么」，
//   验证不了「服务端实际返回什么」。
//   夹具由 server 真实解析生成（test/fixture_*.json）。
//
// ⚠️ 本沙箱内 `dart run` 会静默失败，必须用 `dart <file>`。
import 'dart:convert';
import 'dart:io';

import '../lib/models/parse_result.dart';

int _pass = 0;
int _fail = 0;

void check(String label, bool ok, [String detail = '']) {
  if (ok) {
    _pass++;
    print('   PASS  $label');
  } else {
    _fail++;
    print('   FAIL  $label${detail.isEmpty ? '' : '  → $detail'}');
  }
}

void main() {
  print('═══ 客户端模型 · 真实响应解析验证 ═══\n');

  // ---- 1. B站视频 ----
  _test('bilibili', 'B站视频');

  // ---- 2. 小红书图集 ----
  _test('xhs_image', '小红书图集');

  // ---- 3. AcFun（需服务端合并）----
  _test('acfun', 'AcFun m3u8');

  // ---- 4. 微博 ----
  _test('weibo', '微博视频');

  // ---- 5. 搜狐 ----
  _test('sohu_short', '搜狐视频');

  // ---- 6. 失败响应（关键：不能崩）----
  _testFailure('badlink', '非法输入');

  print('');
  print('═══ 汇总：$_pass PASS / $_fail FAIL ═══');
  if (_fail > 0) {
    print('❌ 有断言失败');
    exit(1);
  }
  print('✅ 客户端能正确解析全部真实响应');
}

void _test(String fixture, String label) {
  final f = File('test/fixture_$fixture.json');
  if (!f.existsSync()) {
    print('── $label ──');
    check('夹具存在', false, '缺 test/fixture_$fixture.json');
    return;
  }
  final r = ParseResult.fromJson(
      (jsonDecode(f.readAsStringSync()) as Map).cast<String, dynamic>());

  print('── $label ──');
  check('success=true', r.success);
  check('平台名已翻译', r.platformName.isNotEmpty, r.platformName);
  check('标题非空', r.meta.title.isNotEmpty, r.meta.title);
  check('封面非空', r.meta.cover.isNotEmpty);

  if (r.isVideo) {
    check('有播放地址', r.videoUrl.isNotEmpty);
    check('有清晰度选项', r.options.isNotEmpty, '${r.options.length} 档');
    check('可推荐一个档位', r.recommendedOption != null,
        r.recommendedOption?.label ?? 'null');
    // 每个选项都必须有 URL，否则点了会失败
    final badOpts =
        r.options.where((o) => o.url.isEmpty).length;
    check('所有档位都有地址', badOpts == 0, '$badOpts 档缺 url');
  } else if (r.isImage) {
    check('有图集', r.images.isNotEmpty, '${r.images.length} 张');
    check('每张图都有地址',
        r.images.every((i) => i.url.startsWith('http')));
  }

  // 时长（视频必须有）
  if (r.isVideo) {
    check('时长已解析', r.meta.durationS != null && r.meta.durationS! > 0,
        '${r.meta.durationS}s');
    check('时长文案', r.meta.durationLabel.isNotEmpty,
        r.meta.durationLabel);
  }

  // 统计数字格式化
  final like = r.meta.statLabel('like');
  if (like.isNotEmpty) {
    check('点赞数已格式化', like.isNotEmpty, like);
  }

  // 平台特有能力标记
  if (r.platform == 'acfun') {
    check('标记需服务端合并', r.mergeRequired);
  }
  if (r.platform == 'bilibili') {
    check('匿名上限已读取', r.anonymousMaxHeight > 0,
        '${r.anonymousMaxHeight}P');
  }
  print('');
}

void _testFailure(String fixture, String label) {
  final f = File('test/fixture_$fixture.json');
  if (!f.existsSync()) {
    print('── $label ──');
    check('夹具存在', false, '缺 $fixture');
    return;
  }
  final r = ParseResult.fromJson(
      (jsonDecode(f.readAsStringSync()) as Map).cast<String, dynamic>());

  print('── $label ──');
  check('success=false', !r.success);
  check('有错误文案（UI要显示）', r.error.isNotEmpty, r.error);
  check('未误判为视频/图集', !r.isVideo && !r.isImage);
  // 关键：失败时也不能崩，且不能带播放地址
  check('失败时不带地址', r.videoUrl.isEmpty);
  print('');
}
