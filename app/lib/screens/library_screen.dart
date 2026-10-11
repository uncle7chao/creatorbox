import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/cb_colors.dart';
import '../core/cb_theme.dart';
import '../models/parse_result.dart';

/// 素材库（解析历史）
///
/// ⭐ 会员核心权益是**批量解析**，素材库是它的载体。
/// ⚠️ 当前为本地存储（M1 阶段不上云），会员体系在 M4。
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  /// 供结果页调用：解析成功后记一笔
  static Future<void> addItem(LibraryItem item) async {
    final prefs = await SharedPreferences.getInstance();
    final list = [item.jsonString, ...(prefs.getStringList(_key) ?? const [])];
    // 最多留 100 条
    if (list.length > 100) list.removeRange(100, list.length);
    await prefs.setStringList(_key, list);
  }

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  List<LibraryItem> _items = [];
  bool _loading = true;

  static const _key = 'cb_library_v1';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getStringList(_key) ?? const [];
      setState(() {
        _items = raw
            .map((e) => LibraryItem.fromJsonString(e))
            .where((e) => e.url.isNotEmpty)
            .toList();
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CBColors.bgPage,
      appBar: AppBar(
        title: const Text('素材库'),
        backgroundColor: CBColors.bgCard,
        surfaceTintColor: Colors.transparent,
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: CBColors.brand500))
          : _items.isEmpty
              ? _emptyState()
              : ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemCount: _items.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(height: 8),
                  itemBuilder: (_, i) => _tile(_items[i]),
                ),
    );
  }

  Widget _emptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.inbox_outlined, size: 44, color: CBColors.ink300),
          const SizedBox(height: 12),
          const Text('还没有解析记录',
              style: TextStyle(fontSize: 14, color: CBColors.ink500)),
          const SizedBox(height: 4),
          const Text('回首页粘贴链接试试',
              style: TextStyle(fontSize: 12, color: CBColors.ink300)),
        ],
      ),
    );
  }

  Widget _tile(LibraryItem item) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: CBColors.bgCard,
        borderRadius: CBRadius.card,
        border: Border.all(color: CBColors.bgSunken),
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(
              width: 52,
              height: 52,
              child: item.cover.isEmpty
                  ? Container(color: CBColors.bgSunken)
                  : Image.network(
                      item.cover,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) =>
                          Container(color: CBColors.bgSunken),
                    ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title.isEmpty ? '（无标题）' : item.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, height: 1.4),
                ),
                const SizedBox(height: 4),
                Text(
                  '${platformDisplayName(item.platform)}'
                  '${item.saved ? ' · 已保存' : ''}',
                  style:
                      const TextStyle(fontSize: 11, color: CBColors.ink500),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 素材库条目
///
/// ⚠️ 只存展示需要的字段 —— **不存播放地址**。
///    理由：CDN 地址带签名会过期，存了也用不了；
///    重新解析一次即可拿到新地址。
class LibraryItem {
  final String title;
  final String platform;
  final String cover;
  final String sourceUrl;
  final bool saved;
  final String time;

  const LibraryItem({
    required this.title,
    required this.platform,
    required this.cover,
    required this.sourceUrl,
    this.saved = false,
    this.time = '',
  });

  String get url => sourceUrl; // 供列表过滤用

  String get jsonString =>
      '{"t":"$title","p":"$platform","c":"$cover","u":"$sourceUrl",'
      '"s":$saved,"d":"$time"}';

  factory LibraryItem.fromJsonString(String s) {
    try {
      final m = jsonDecode(s) as Map<String, dynamic>;
      return LibraryItem(
        title: m['t'] as String? ?? '',
        platform: m['p'] as String? ?? '',
        cover: m['c'] as String? ?? '',
        sourceUrl: m['u'] as String? ?? '',
        saved: m['s'] as bool? ?? false,
        time: m['d'] as String? ?? '',
      );
    } catch (_) {
      return const LibraryItem(
          title: '', platform: '', cover: '', sourceUrl: '');
    }
  }
}
