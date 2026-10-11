/// 批量解析页（对齐小程序 pages/batch）。
///
/// 服务端 /api/batch 串行执行、**单条失败不阻塞其余**，返回 results[]，
/// 每条带 index/success/error。本页据此做到：
///   · 逐条展示成功与失败，失败原因原样透出（不吞掉、不统一报「解析失败」）
///   · 成功的可一键复制主档直链
///   · 全部成功后支持「复制全部直链」——这是批量场景真正的价值
///
/// 配额说明：服务端为准（免费 3 条 / 会员 10 条，硬上限 10）。本页只提示，
/// 不自行截断 —— 截断了用户会以为解析过了，是更坏的欺骗。
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart' show ApiError;
import '../state/session.dart';

class BatchPage extends StatefulWidget {
  const BatchPage({super.key, required this.session});
  final Session session;

  @override
  State<BatchPage> createState() => _BatchPageState();
}

class _BatchPageState extends State<BatchPage> {
  final _input = TextEditingController();
  bool _running = false;
  String? _error;              // 整批级别的错误（超配额 / 连不上）
  List<Map<String, dynamic>> _results = const [];

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  /// 把用户粘贴的多行文本拆成链接列表。
  /// 兼容两种常见输入：每行一条，或空格分隔的长串分享文案。
  List<String> _extract() {
    final raw = _input.text.trim();
    if (raw.isEmpty) return const [];
    final byLine = raw
        .split(RegExp(r'[\r\n]+'))
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    // 单行里含多个链接（分享文案常见）
    if (byLine.length == 1) {
      final inline = RegExp(r'https?://\S+').allMatches(byLine.first)
          .map((m) => m.group(0)!)
          .toList();
      if (inline.isNotEmpty) return inline;
    }
    return byLine;
  }

  Future<void> _run() async {
    final items = _extract();
    if (items.isEmpty) {
      setState(() => _error = '请先粘贴至少一个链接');
      return;
    }
    if (_running) return;
    setState(() {
      _running = true;
      _error = null;
      _results = const [];
    });

    try {
      // 批量接口以 openid 为主键 → 服务端兑换，不在本地缓存
      final openid = await widget.session.api.authOpenid();
      final res = await widget.session.api.batch(items, openid);
      if (!mounted) return;
      setState(() {
        _results = res;
        _running = false;
        if (res.isEmpty) _error = '服务端未返回结果，请稍后再试';
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _running = false;
        // 超配额是有业务含义的 400，要如实告知而不是笼统报错
        _error = e.statusCode == 400
            ? e.detail
            : (e.statusCode == 429 ? '操作过于频繁，请稍后再试' : e.detail);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _running = false;
        _error = '解析失败：$e';
      });
    }
  }

  static String _s(dynamic v) => v?.toString() ?? '';

  /// 主档直链：与结果页同一套取值逻辑（options 首条 → video_url）
  static String _mainUrl(Map r) {
    final opts = r['options'];
    if (opts is List && opts.isNotEmpty) {
      final first = opts.first;
      if (first is Map) {
        final u = _s(first['url']);
        if (u.isNotEmpty) return u;
      }
    }
    final v = _s(r['video_url']);
    if (v.isNotEmpty) return v;
    final img = r['images'];
    if (img is List && img.isNotEmpty && img.first is Map) {
      return _s((img.first as Map)['url']);
    }
    return '';
  }

  Future<void> _copy(String text, String tip) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(tip)));
  }

  void _copyAll() {
    final links = _results
        .where((r) => r['success'] == true)
        .map(_mainUrl)
        .where((u) => u.isNotEmpty)
        .toList();
    if (links.isEmpty) return;
    _copy(links.join('\n'), '已复制 ${links.length} 条直链');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final okCount =
        _results.where((r) => r['success'] == true).length;
    final failCount = _results.length - okCount;

    return Scaffold(
      appBar: AppBar(
        title: const Text('批量解析'),
        actions: [
          if (okCount > 1)
            TextButton.icon(
              onPressed: _copyAll,
              icon: const Icon(Icons.copy_all, size: 18),
              label: const Text('复制全部'),
            ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: _input,
                  maxLines: 6,
                  minLines: 3,
                  decoration: const InputDecoration(
                    hintText: '粘贴多个链接，每行一条\n（也支持直接粘贴带链接的分享文案）',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _input.text.trim().isEmpty
                            ? '免费单次 3 条 · 会员 10 条'
                            : '已识别 ${_extract().length} 条链接'
                                '${_extract().length > 3 ? '（超出免费额度，需会员）' : ''}',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: _extract().length > 3
                              ? Colors.orange.shade700
                              : null,
                        ),
                      ),
                    ),
                    FilledButton.icon(
                      onPressed: _running ? null : _run,
                      icon: _running
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.play_arrow),
                      label: Text(_running ? '解析中' : '开始解析'),
                    ),
                  ],
                ),
                if (_error != null) ...[
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.red.shade50,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.red.shade200),
                    ),
                    child: Text(_error!,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: Colors.red.shade900)),
                  ),
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _results.isEmpty
                ? Center(
                    child: Text(
                      _running ? '解析中，请稍候…' : '结果会显示在这里',
                      style: theme.textTheme.bodySmall,
                    ),
                  )
                : ListView(
                    padding: const EdgeInsets.all(12),
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8, left: 4),
                        child: Text(
                          '共 ${_results.length} 条 · 成功 $okCount'
                          '${failCount > 0 ? ' · 失败 $failCount' : ''}',
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                      ...List.generate(_results.length, (i) {
                        final r = _results[i];
                        final ok = r['success'] == true;
                        final link = ok ? _mainUrl(r) : '';
                        final title = _s(r['title']);
                        final err = _s(r['error']);
                        return Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            leading: CircleAvatar(
                              radius: 14,
                              backgroundColor: ok
                                  ? Colors.green.shade50
                                  : Colors.red.shade50,
                              child: Text(
                                '${i + 1}',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: ok
                                      ? Colors.green.shade800
                                      : Colors.red.shade800,
                                ),
                              ),
                            ),
                            title: Text(
                              ok
                                  ? (title.isEmpty ? '（无标题）' : title)
                                  : '解析失败',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 14,
                                color: ok ? null : Colors.red.shade700,
                              ),
                            ),
                            subtitle: Text(
                              ok
                                  ? '${_s(r['platform'])} · ${link.isEmpty ? '无可用直链' : '点击复制直链'}'
                                  : (err.isEmpty ? '未识别到链接' : err),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            trailing: (ok && link.isNotEmpty)
                                ? const Icon(Icons.copy, size: 20)
                                : (ok
                                    ? null
                                    : const Icon(Icons.error_outline,
                                        size: 20, color: Colors.red)),
                            onTap: (ok && link.isNotEmpty)
                                ? () => _copy(link, '直链已复制')
                                : null,
                          ),
                        );
                      }),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}