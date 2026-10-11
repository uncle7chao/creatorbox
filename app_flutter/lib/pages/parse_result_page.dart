/// 解析结果页：信息卡 + 档位列表（复制直链）+ BGM + 字幕文案（复制）。
///
/// P1 产出形态 = 复制直链/文案（本地下载引擎是 P2 的本机引擎，
/// 服务端直链对 YouTube 有 IP 锁——如实提示，不假装能下载）。
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/session.dart';

class ParseResultPage extends StatefulWidget {
  const ParseResultPage({super.key, required this.session, required this.result});
  final Session session;
  final Map<String, dynamic> result;

  @override
  State<ParseResultPage> createState() => _ParseResultPageState();
}

class _ParseResultPageState extends State<ParseResultPage> {
  bool _saving = false;
  bool _saved = false;

  Session get session => widget.session;
  Map<String, dynamic> get result => widget.result;

  void _copy(String text, String tip, BuildContext context) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(tip)));
  }

  /// 存入素材库（= 跨端解析历史，与小程序同库同一条记录）。
  /// 走服务端 token→openid 兑换，客户端不缓存 openid。
  Future<void> _saveToLibrary() async {
    if (_saving || _saved) return;
    setState(() => _saving = true);
    try {
      final openid = await session.api.authOpenid();
      await session.api.libraryAdd(
        openid,
        itemType: 'video',
        title: _title,
        platform: _str(result['platform']),
        author: _str(result['author']),
        cover: _str(result['cover']),
        sourceText: _mainUrl.isEmpty
            ? _str(result['short_url'])
            : _mainUrl,
      );
      if (!mounted) return;
      setState(() => _saved = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已存入素材库（小程序端同步可见）')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('存入失败：$e')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String get _title => (result['title'] as String?) ?? '（无标题）';
  String get _author => (result['author'] as String?) ?? '';
  List get _options => (result['options'] as List?) ?? [];
  String get _subtitle => (result['subtitle_text']?.toString() ?? '');
  String get _musicUrl => (result['music_url']?.toString() ?? '');

  /// 主档直链：取排序后第一条（= 最清晰那档），无 options 时退回顶层 video_url。
  String get _mainUrl {
    final sorted = _sortedOptions;
    if (sorted.isNotEmpty) {
      final u = _str(sorted.first['url']);
      if (u.isNotEmpty) return u;
    }
    return _str(result['video_url']);
  }

  /// 服务端缓存写入时剔除了 options（slim 策略，见 server/app/main.py:457），
  /// 所以命中缓存时 options_count>0 但 options 为空 —— 此时提示重解析，别让用户以为没有档位。
  bool get _strippedByCache =>
      _options.isEmpty && ((result['options_count'] as int?) ?? 0) > 0;

  /// 各解析器的 quality 可能为 null（抖音就是），统一安全取值，避免 as String 崩。
  static String _str(dynamic v) => v?.toString() ?? '';

  /// 按「清晰度 + 码率」排序后的档位列表。
  ///
  /// 实测抖音返回的 6 条是按内部编码排的（720_2_1 / 540_2_1 / 720_3_1 …），
  /// 顺序对用户没意义 —— 我们按 height 降序、同高按 bit_rate 降序重排，
  /// 让第一档就是最清晰的。1080P 走 play_api 时 bit_rate 可能为 null，排在同高度末尾。
  List get _sortedOptions {
    // ⚠️ options 是 List<dynamic>，服务端若混入非 Map 元素，
    // 直接 o['height'] 会抛 NoSuchMethodError —— 这里只留 Map。
    final list = _options.whereType<Map>().toList();
    list.sort((a, b) {
      final ha = _int(a['height']), hb = _int(b['height']);
      if (ha != hb) return hb.compareTo(ha);          // 高度高的在前
      final ba = _int(a['bit_rate']), bb = _int(b['bit_rate']);
      if (ba != bb) return bb.compareTo(ba);          // 同高码率高的在前
      return _int(a['index']).compareTo(_int(b['index']));
    });
    return list;
  }

  static int _int(dynamic v) =>
      v is int ? v : (int.tryParse(v?.toString() ?? '') ?? 0);

  /// 把解析器内部档位编码翻成人话。
  /// 实测抖音返回 '720_2_1' / '1080p(play-api)' 这类内部码（B站是 '720P' 正常），
  /// 直接展示给用户是乱码 —— 这里取高度 + 码率做展示名。
  static String _gearLabel(Map o) {
    final h = o['height'];
    final raw = _str(o['gear']);
    final head = (h is int && h > 0) ? '${h}P' : '';

    // B站等已经是 '720P' 这种干净值，直接用
    if (RegExp(r'^\d{3,4}P$').hasMatch(raw)) return raw;

    if (raw.isEmpty) return head.isEmpty ? '默认档' : head;

    // 抖音 '1080p(play-api)' → '1080P（play 通道）'
    final inner = raw.contains('(') && raw.endsWith(')')
        ? raw.substring(raw.indexOf('(') + 1, raw.length - 1)
        : '';
    final base = RegExp(r'(\d{3,4})').firstMatch(raw.split('(').first)?.group(1);
    final label = base != null ? '${base}P' : (head.isEmpty ? '清晰档' : head);
    if (inner.isNotEmpty) return '$label（$inner 通道）';

    // 抖音 '720_2_1'：同高度多路并存，用码率做区分（比取内部序号对用户更有意义）。
    // ⚠️ 不能取末段——实测 720_2_1 / 720_3_1 / 720_4_1 末段都是 1，会显示成三个一样的名字。
    if (raw.contains('_')) {
      final br = _int(o['bit_rate']);
      if (br > 0) return '$label · ${(br / 1000).round()}kbps';
      final parts = raw.split('_');
      if (parts.length >= 2 && parts[1].isNotEmpty) return '$label · 第 ${parts[1]} 路';
      return '$label · 备用轨';
    }
    return label;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('解析结果')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(_title, style: theme.textTheme.titleLarge
              ?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text([_author, _str(result['platform']), _str(result['quality'])]
              .where((s) => s.isNotEmpty)
              .join(' · '),
              style: theme.textTheme.bodySmall),
          const SizedBox(height: 16),

          // ── 主档直链（第一诉求：拿最好的那条）──
          if (_mainUrl.isNotEmpty) ...[
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () =>
                    _copy(_mainUrl, '主档直链已复制，可粘贴到下载器', context),
                icon: const Icon(Icons.download),
                label: Text('复制主档直链（${_str(result['quality']).isEmpty ? '默认' : _str(result['quality'])}）'),
              ),
            ),
            const SizedBox(height: 8),
          ],

          // ── 存入素材库（= 跨端历史；小程序端同步可见）──
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: (_saving || _saved) ? null : _saveToLibrary,
              icon: Icon(_saved ? Icons.check : Icons.bookmark_add_outlined),
              label: Text(_saved ? '已存入素材库' : '存入素材库（小程序同步）'),
            ),
          ),
          const SizedBox(height: 12),

          // ── 缓存瘦身提示（options 被服务端剔除，非 bug）──
          if (_strippedByCache) ...[
            Card(
              color: theme.colorScheme.secondaryContainer,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                    '本次命中服务端缓存，缓存不保存清晰度档位（共 ${result['options_count']} 档）。'
                    '返回后勾选「强制重新解析」即可看到完整档位。',
                    style: theme.textTheme.bodySmall),
              ),
            ),
            const SizedBox(height: 12),
          ],

          // ── 下载档位 ──
          if (_options.isNotEmpty) ...[
            Text('清晰度档位（点击复制直链）',
                style: theme.textTheme.titleSmall),
            ..._sortedOptions.map((o) {
              final url = _str(o['url']);
              final gear = _gearLabel(o);
              return Card(
                child: ListTile(
                  leading: const Icon(Icons.hd_outlined),
                  title: Text(gear),
                  subtitle: Text(url.isEmpty
                      ? '该档位无直链'
                      : (o['merge_required'] == true)
                          ? '分轨档 · 需合并（本机引擎 P2 支持直下）'
                          : '直链可复制，浏览器/下载器打开'),
                  trailing: const Icon(Icons.copy),
                  onTap: url.isEmpty ? null : () => _copy(url, '$gear 直链已复制', context),
                ),
              );
            }),
          ],

          // ── BGM ──
          if (_musicUrl.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('背景音乐', style: theme.textTheme.titleSmall),
            Card(
              child: ListTile(
                leading: const Icon(Icons.music_note),
                title: Text(_str(result['music_title']).isEmpty
                    ? 'BGM'
                    : _str(result['music_title']),
                    maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: const Text('点击复制音频直链'),
                trailing: const Icon(Icons.copy),
                onTap: () => _copy(_musicUrl, '音频直链已复制', context),
              ),
            ),
          ],

          // ── 字幕文案 ──
          if (_subtitle.isNotEmpty) ...[
            const SizedBox(height: 8),
            Row(children: [
              Text('字幕文案', style: theme.textTheme.titleSmall),
              const SizedBox(width: 8),
              Text('${result['subtitle_lang'] ?? ''}'
                      '${result['subtitle_auto'] == true ? ' · 自动生成' : ''}'
                      ' · ${_subtitle.length} 字',
                  style: theme.textTheme.bodySmall),
            ]),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(children: [
                  Text(_subtitle.length > 600
                          ? '${_subtitle.substring(0, 600)}…'
                          : _subtitle,
                      style: theme.textTheme.bodySmall),
                  const SizedBox(height: 8),
                  FilledButton.tonalIcon(
                    onPressed: () => _copy(
                        _subtitle, '字幕文案已复制（可去小程序跑违禁词检测）',
                        context),
                    icon: const Icon(Icons.copy),
                    label: const Text('复制字幕全文'),
                  ),
                ]),
              ),
            ),
          ],

          // ── 说明 ──
          const SizedBox(height: 16),
          if (_options.length == 1)
            Text('该平台本次只返回 1 个档位：B站多档依赖 wbi 签名，属已知限制（v4 §3.2 登记为 P2 专项）。'
                '需要多档请用抖音或快手验证。',
                style: theme.textTheme.bodySmall),
          const SizedBox(height: 8),
          Text('提示：直链由服务端解析。YouTube 直链绑定解析出口 IP，'
                  '本机下载能力将由 P2 本机引擎提供。',
              style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}
