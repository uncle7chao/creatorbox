/// AI 文案创作页（PC / Android）—— 内嵌 DeepSeek 网页版
///
/// ⭐⭐ 为什么是「内嵌浏览器」而不是「服务端调接口」（2026-10-24 设计决策）
///
/// 用户要的是「让用户自己登录 DS，然后用它做创作」。查证后确认这条路是唯一可行的：
///
/// | 方案 | 可行性 | 原因 |
/// |---|---|---|
/// | 服务端代调 chat.deepseek.com 接口 | ❌ 不可行 | ① 每次请求要解 PoW（x-ds-pow-response，SHA3 WASM 挑战）② 平台检测 TLS 指纹，非浏览器直接封 ③ **致命**：所有用户共用我们一台服务器出口 IP，风控会很快封掉 |
/// | 用户交 token 给我们代调 | ❌ 不可行 | 普通用户不会去 F12 复制 localStorage.userToken |
/// | **内嵌浏览器 + 用户自己登录** | ✅ 可行 | 签名/PoW 由页面自己的 JS 算，请求从【用户自己的 IP】发出，用【用户自己的额度】 |
///
/// 这样做的代价是「半自动」：我们负责把素材填进去，**发送由用户自己点**。
/// 不代点是因为程序触发的点击 `event.isTrusted === false`，容易被判自动化。
///
/// ⚠️ 小程序端不提供这个能力（微信「深度合成-AI 创作」类目只允许企业主体，
///    个人主体提审必驳回）→ 小程序只做占位引导，见 toolbox 页的 pcOnly 卡片。
///
/// ⚠️⚠️ Windows 上的 WebView 是【原生窗口叠加】，不是 Flutter 纹理：
///    · Flutter 的 Dialog / SnackBar / DropdownButton 菜单会被它**盖住**
///    · 所以本页**刻意不用**这些组件，状态提示走工具栏内的 Text
///    · WebView 必须放在 Expanded 里占满剩余区域，不能和它重叠
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// DeepSeek 网页版首页（登录后自动进对话页）
const _dsHome = 'https://chat.deepseek.com/';

/// 提示词模板：每个都是「完整指令 + 素材占位」
/// ⭐ 模板决定了 80% 的产出质量 —— 这里不用「帮我写个文案」这种空话，
///    而是给角色、结构、字数、禁忌词，让模型有明确约束。
class _Tpl {
  final String key;
  final String name;
  final String prompt;
  const _Tpl(this.key, this.name, this.prompt);
}

const _templates = <_Tpl>[
  _Tpl(
    'xhs',
    '小红书',
    '你是资深小红书爆款笔记编辑。请基于下面的原始素材，写一篇小红书种草笔记。\n\n'
        '要求：\n'
        '1. 标题给 3 个备选，每个不超过 20 字，要带情绪钩子（好奇 / 反差 / 痛点）\n'
        '2. 正文 200~300 字，第一人称、口语化、有具体细节（数字、场景、感受）\n'
        '3. 结尾附 6~8 个话题标签，用 #标签 格式\n'
        '4. 不要用「家人们」「宝子们」「姐妹们冲」这类烂梗\n'
        '5. 不要编造素材里没有的信息（价格、成分、效果）\n\n'
        '原始素材：\n{{MATERIAL}}\n\n'
        '直接输出文案，不要解释你的思路。',
  ),
  _Tpl(
    'douyin',
    '抖音口播',
    '你是短视频口播稿写手。请基于下面的素材，写一段 30~45 秒的抖音口播稿。\n\n'
        '要求：\n'
        '1. 第一句必须是钩子（3 秒内抓住人），制造悬念或反常识\n'
        '2. 全文口语化，像跟朋友说话，不要书面语\n'
        '3. 每句尽量短（不超过 18 字），方便断句和字幕\n'
        '4. 结尾给一个行动引导（关注 / 评论 / 收藏），要自然不生硬\n'
        '5. 只输出口播正文，不要分镜说明\n\n'
        '原始素材：\n{{MATERIAL}}',
  ),
  _Tpl(
    'title',
    '10 个标题',
    '你是标题党专家。基于下面的素材，生成 10 个短视频标题。\n\n'
        '要求：\n'
        '1. 每个不超过 20 字\n'
        '2. 覆盖不同风格：悬念型 2 个、数字型 2 个、反差型 2 个、痛点型 2 个、'
        '共鸣型 2 个\n'
        '3. 不许夸张造假（不写「震惊」「必看」这类违规词）\n'
        '4. 一行一个，前面标上风格类型\n\n'
        '原始素材：\n{{MATERIAL}}',
  ),
  _Tpl(
    'desc',
    '视频简介',
    '请基于下面的素材，写一段 60~100 字的视频简介（用于发布时的描述区）。\n\n'
        '要求：\n'
        '1. 第一句概括视频讲了什么，第二句给价值点，第三句引导互动\n'
        '2. 语气自然，不要营销腔\n'
        '3. 末尾放 3~5 个话题标签\n'
        '4. 只输出简介正文\n\n'
        '原始素材：\n{{MATERIAL}}',
  ),
  _Tpl(
    'polish',
    '改写润色',
    '请把下面这段文案改写得更口语、更有感染力，但**不要改变原意，不要添加原文没有的事实**。\n\n'
        '要求：\n'
        '1. 长度和原文接近（±20%）\n'
        '2. 去掉书面语和重复啰嗦的表达\n'
        '3. 保留所有具体信息（数字、名称、时间）\n'
        '4. 只输出改写后的文案\n\n'
        '原文：\n{{MATERIAL}}',
  ),
];

class AiCreatePage extends StatefulWidget {
  /// 从解析结果页带过来的素材（标题 / 字幕 / 文案）
  final String seedMaterial;

  const AiCreatePage({super.key, this.seedMaterial = ''});

  @override
  State<AiCreatePage> createState() => _AiCreatePageState();
}

class _AiCreatePageState extends State<AiCreatePage> {
  late final WebViewController _ctl;

  int _progress = 0;
  String _url = '';
  String _status = '正在加载 DeepSeek…';
  int _tplIdx = 0;
  bool _busy = false;
  bool _webOk = true;

  /// 素材：可编辑（默认带入解析结果）
  late final TextEditingController _materialCtl;
  bool _editing = false;

  @override
  void initState() {
    super.initState();
    _materialCtl = TextEditingController(text: widget.seedMaterial);
    _initWeb();
  }

  void _initWeb() {
    _ctl = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFF7F8FA))
      ..setNavigationDelegate(NavigationDelegate(
        onProgress: (p) {
          if (!mounted) return;
          setState(() => _progress = p);
        },
        onPageStarted: (u) {
          if (!mounted) return;
          setState(() => _url = u);
        },
        onPageFinished: (u) {
          if (!mounted) return;
          setState(() {
            _url = u;
            _status = _loggedIn ? '已登录，可以填入素材了' : '请先在右侧登录自己的 DeepSeek 账号';
          });
        },
        onWebResourceError: (e) {
          if (!mounted) return;
          // 只有主文档失败才算致命（子资源失败不影响使用）
          if (e.isForMainFrame == true) {
            setState(() {
              _webOk = false;
              _status = '页面加载失败：${e.description}';
            });
          }
        },
      ))
      ..loadRequest(Uri.parse(_dsHome));
  }

  /// 登录态判断：登录后 URL 会离开 /sign_in
  bool get _loggedIn =>
      _url.isNotEmpty && !_url.contains('sign_in') && !_url.contains('login');

  @override
  void dispose() {
    _materialCtl.dispose();
    super.dispose();
  }

  // ────────────────────────── 动作 ──────────────────────────

  /// 把「模板 + 素材」填进 DeepSeek 的输入框。
  ///
  /// ⭐ 关键：DeepSeek 是 React 受控组件，直接 `textarea.value = x` 不会生效
  ///    （React 的 value tracker 会认为值没变，不触发 onChange 更新 state）。
  ///    必须用原型上的原生 setter 赋值，再手动派发 input 事件。
  Future<void> _fill() async {
    final material = _materialCtl.text.trim();
    if (material.isEmpty) {
      _toast('素材是空的 —— 先在上面填入要改写的标题 / 字幕 / 文案');
      return;
    }
    if (!_loggedIn) {
      _toast('请先在右侧登录 DeepSeek 账号');
      return;
    }

    final tpl = _templates[_tplIdx];
    final prompt = tpl.prompt.replaceAll('{{MATERIAL}}', material);

    setState(() {
      _busy = true;
      _status = '正在填入…';
    });
    final js = '''
(function(t){
  try {
    var ta = Array.prototype.slice.call(document.querySelectorAll('textarea'))
      .filter(function(e){ return e.offsetParent !== null; })
      .sort(function(a,b){ return (b.clientHeight||0)-(a.clientHeight||0); })[0];
    if (!ta) {
      var ed = Array.prototype.slice.call(
        document.querySelectorAll('[contenteditable="true"]'))
        .filter(function(e){ return e.offsetParent !== null; })[0];
      if (ed) {
        ed.focus();
        document.execCommand('insertText', false, t);
        return 'ok-editable';
      }
      return 'no-input';
    }
    var proto = window.HTMLTextAreaElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(ta, t);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    ta.focus();
    return 'ok';
  } catch (e) { return 'err:' + (e && e.message ? e.message : e); }
})(${jsonEncode(prompt)})
''';

    final res = await _runJs(js);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _status = switch (res) {
        'ok' || 'ok-editable' => '已填入，请在右侧点「发送」',
        'no-input' => '没找到输入框 —— 确认已登录并打开了对话页',
        _ => '填入失败：$res',
      };
    });
  }

  /// 把最后一条 AI 回复读回剪贴板
  Future<void> _readBack() async {
    setState(() {
      _busy = true;
      _status = '正在读取回复…';
    });
    // 选择器按「可能性从高到低」兜底 —— 平台改版时前几个会失效，后面还能命中
    const js = r'''
(function(){
  var sels = ['.ds-markdown', '.ds-markdown--block', '[class*="markdown"]',
              '[class*="message-content"]', '[class*="chat-message"]'];
  for (var i = 0; i < sels.length; i++) {
    var els = Array.prototype.slice.call(document.querySelectorAll(sels[i]))
      .filter(function(e){ return ((e.innerText || '').trim().length > 0); });
    if (els.length) return els[els.length - 1].innerText.trim();
  }
  return '';
})()
''';
    final res = await _runJs(js);
    if (!mounted) return;
    setState(() => _busy = false);
    if (res.isEmpty) {
      _toast('没读到回复 —— 等 DeepSeek 输出完再点一次');
      return;
    }
    await Clipboard.setData(ClipboardData(text: res));
    setState(() => _status = '已复制到剪贴板（${res.length} 字）');
  }

  /// 执行 JS 并归一化返回值
  ///
  /// ⚠️ `runJavaScriptReturningResult` 返回的是 **JSON 编码**的结果
  ///    （字符串会带双引号且内部转义），不能直接 toString 用。
  Future<String> _runJs(String js) async {
    try {
      final raw = await _ctl.runJavaScriptReturningResult(js);
      var s = raw.toString();
      if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) {
        try {
          return jsonDecode(s) as String;
        } catch (_) {
          return s.substring(1, s.length - 1);
        }
      }
      return s;
    } catch (e) {
      return 'err:${e.toString().split('\n').first}';
    }
  }

  /// 状态提示：**不用 SnackBar** —— Windows 上 WebView 是原生窗口，
  /// 会盖住 Flutter 的 SnackBar / Dialog。改走工具栏内的 Text。
  void _toast(String msg) {
    if (!mounted) return;
    setState(() => _status = msg);
  }

  // ────────────────────────── UI ──────────────────────────

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('文案创作'),
        actions: [
          IconButton(
            tooltip: '重新加载 DeepSeek',
            icon: const Icon(Icons.refresh),
            onPressed: () {
              setState(() => _status = '正在刷新…');
              _ctl.reload();
            },
          ),
          IconButton(
            tooltip: '打开登录页',
            icon: const Icon(Icons.login),
            onPressed: () {
              setState(() => _status = '请在右侧完成登录');
              _ctl.loadRequest(Uri.parse(_dsHome));
            },
          ),
        ],
        bottom: _progress < 100
            ? PreferredSize(
                preferredSize: const Size.fromHeight(2),
                child: LinearProgressIndicator(value: _progress / 100, minHeight: 2),
              )
            : null,
      ),
      body: Column(
        children: [
          _toolbar(theme),
          const Divider(height: 1),
          Expanded(
            child: _webOk
                ? WebViewWidget(controller: _ctl)
                : Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.public_off, size: 48, color: theme.disabledColor),
                          const SizedBox(height: 12),
                          Text(_status, textAlign: TextAlign.center),
                          const SizedBox(height: 16),
                          FilledButton(
                            onPressed: () {
                              setState(() {
                                _webOk = true;
                                _status = '正在重试…';
                              });
                              _ctl.loadRequest(Uri.parse(_dsHome));
                            },
                            child: const Text('重试'),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '若提示缺少 WebView2 Runtime，'
                            '请安装 Microsoft Edge WebView2（Win11 一般自带）',
                            style: theme.textTheme.bodySmall,
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _toolbar(ThemeData theme) {
    final material = _materialCtl.text;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
      color: theme.colorScheme.surfaceContainerLowest,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ① 素材（默认折叠成一行摘要，点「编辑」展开）
          Row(
            children: [
              Icon(Icons.notes_outlined, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  material.isEmpty ? '素材未填写' : '素材：${_summary(material)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: material.isEmpty ? theme.disabledColor : null,
                  ),
                ),
              ),
              TextButton(
                onPressed: () => setState(() => _editing = !_editing),
                child: Text(_editing ? '收起' : '编辑'),
              ),
            ],
          ),
          if (_editing)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: TextField(
                controller: _materialCtl,
                maxLines: 4,
                minLines: 2,
                decoration: const InputDecoration(
                  hintText: '粘贴要改写的标题 / 字幕 / 原文',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),

          // ② 模板选择：用 ChoiceChip 而不是 DropdownButton
          //    （下拉菜单是 Flutter overlay，会被 Windows 原生 WebView 盖住）
          Wrap(
            spacing: 8,
            runSpacing: -8,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 6, right: 4),
                child: Text('模板', style: theme.textTheme.labelMedium),
              ),
              for (var i = 0; i < _templates.length; i++)
                ChoiceChip(
                  label: Text(_templates[i].name),
                  selected: _tplIdx == i,
                  onSelected: (_) => setState(() => _tplIdx = i),
                ),
            ],
          ),
          const SizedBox(height: 4),

          // ③ 动作 + 状态
          Row(
            children: [
              FilledButton.icon(
                onPressed: _busy ? null : _fill,
                icon: const Icon(Icons.upload, size: 18),
                label: const Text('填入 DeepSeek'),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: _busy ? null : _readBack,
                icon: const Icon(Icons.download, size: 18),
                label: const Text('读回回复'),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  _status,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _summary(String s) {
    final one = s.replaceAll(RegExp(r'\s+'), ' ').trim();
    return one.length <= 40 ? one : '${one.substring(0, 40)}…（${s.length} 字）';
  }
}
