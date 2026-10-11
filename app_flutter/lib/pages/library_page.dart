/// 素材库页（跨端解析历史）。
///
/// 为什么复用素材库而不是新建表（v4 §2.4 openid 全链路零改动）：
/// 服务端 library 表以 openid 为主键、已有 add/list/delete 三端点，
/// 本端通过 /api/auth/openid 换 openid 后直接复用 —— 同一账号在
/// 小程序存的文案、在 PC 存的视频，落在同一条记录里，天然打通。
///
/// 展示语义：本端主要是「解析历史」，所以按存入时间倒序，
/// 并把 source_text 里的直链直接变成可再次复制的一行。
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../state/session.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key, required this.session});
  final Session session;

  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  late Future<List<Map<String, dynamic>>> _future;
  String _openid = '';   // 本次会话内有效；token 失效时整体重取

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    // 每次刷新都重新兑换 openid，不缓存 —— token 换了也不会拿旧 openid
    setState(() {
      _future = _fetch();
    });
  }

  Future<List<Map<String, dynamic>>> _fetch() async {
    final openid = await widget.session.api.authOpenid();
    _openid = openid;
    return widget.session.api.libraryList(openid);
  }

  Future<void> _refresh() async {
    setState(() => _future = _fetch());
    try {
      await _future;
    } catch (_) {/* 错误由 FutureBuilder 统一展示 */}
  }

  Future<void> _delete(Map item) async {
    final id = int.tryParse(item['id']?.toString() ?? '');
    if (id == null || _openid.isEmpty) return;
    try {
      await widget.session.api.libraryDelete(_openid, id);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('已删除')));
      await _refresh();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('删除失败：$e')));
    }
  }

  static String _s(dynamic v) => v?.toString() ?? '';

  /// 素材库有 3 类：video / image / copy。本端以 video 为主，
  /// 但列表要能显示文案类（小程序存的字幕文案会出现在这里）。
  static ({String icon, String label}) _kind(Map item) {
    return switch (_s(item['item_type'])) {
      'image' => (icon: '🖼', label: '图集'),
      'copy' => (icon: '📝', label: '文案'),
      _ => (icon: '🎬', label: '视频'),
    };
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('素材库 / 历史'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: '刷新',
            onPressed: _load,
          ),
        ],
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (ctx, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.cloud_off, size: 42, color: Colors.grey),
                    const SizedBox(height: 12),
                    Text('加载失败：${snap.error}',
                        style: theme.textTheme.bodySmall,
                        textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton(
                        onPressed: _load, child: const Text('重试')),
                  ],
                ),
              ),
            );
          }
          final items = snap.data ?? const <Map<String, dynamic>>[];
          if (items.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.inbox_outlined, size: 42, color: Colors.grey),
                    const SizedBox(height: 12),
                    Text('还没有记录',
                        style: theme.textTheme.titleSmall),
                    const SizedBox(height: 4),
                    Text('解析后点「存入素材库」，这里会同步显示；\n'
                        '小程序端存的文案也会出现在这里',
                        style: theme.textTheme.bodySmall,
                        textAlign: TextAlign.center),
                  ],
                ),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: items.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (_, i) {
                final it = items[i];
                final k = _kind(it);
                final link = _s(it['source_text']);
                final title = _s(it['title']).isEmpty
                    ? '（未命名）'
                    : _s(it['title']);
                final meta = [_s(it['author']), _s(it['platform'])]
                    .where((x) => x.isNotEmpty)
                    .join(' · ');
                return Card(
                  child: ListTile(
                    leading: Text(k.icon,
                        style: const TextStyle(fontSize: 22)),
                    title: Text(title,
                        maxLines: 2, overflow: TextOverflow.ellipsis),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (meta.isNotEmpty) Text(meta),
                        // 直链常很长，截断展示 + 可整条复制
                        if (link.startsWith('http'))
                          Padding(
                            padding: const EdgeInsets.only(top: 2),
                            child: Text(
                              link.length > 60
                                  ? '${link.substring(0, 60)}…'
                                  : link,
                              style: theme.textTheme.bodySmall?.copyWith(
                                  fontFamily: 'Consolas',
                                  color: theme.colorScheme.primary),
                            ),
                          ),
                      ],
                    ),
                    isThreeLine: link.startsWith('http'),
                    trailing: PopupMenuButton<String>(
                      itemBuilder: (_) => const [
                        PopupMenuItem(
                          value: 'copy',
                          height: 44,
                          child: Row(children: [
                            Icon(Icons.copy, size: 18),
                            SizedBox(width: 10),
                            Text('复制直链'),
                          ]),
                        ),
                        PopupMenuItem(
                          value: 'del',
                          height: 44,
                          child: Row(children: [
                            Icon(Icons.delete_outline, size: 18),
                            SizedBox(width: 10),
                            Text('删除'),
                          ]),
                        ),
                      ],
                      onSelected: (v) async {
                        if (v == 'copy') {
                          if (!link.startsWith('http')) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('这条没有直链')));
                            return;
                          }
                          await Clipboard.setData(
                              ClipboardData(text: link));
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text('直链已复制')));
                        } else if (v == 'del') {
                          await _delete(it);
                        }
                      },
                    ),
                    onTap: link.startsWith('http')
                        ? () {
                            Clipboard.setData(ClipboardData(text: link));
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('直链已复制')));
                          }
                        : null,
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}