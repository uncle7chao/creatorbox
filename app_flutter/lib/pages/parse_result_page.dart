/// 解析结果页：信息卡 + 档位列表（复制直链）+ BGM + 字幕文案（复制）。
///
/// P1 产出形态 = 复制直链/文案（本地下载引擎是 P2 的本机引擎，
/// 服务端直链对 YouTube 有 IP 锁——如实提示，不假装能下载）。
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/session.dart';
import 'ai_create_page.dart';

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
  bool _bgmSaving = false;
  bool _bgmSaved = false;

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

  /// 是否值得去创作：至少要有文案或字幕
  bool get _canCreate =>
      _copyText.trim().isNotEmpty || _subtitle.trim().isNotEmpty;

  /// 带着素材跳到文案创作页（按「标题 / 文案 / 字幕」分段，模型更好理解）
  void _goCreate() {
    final parts = <String>[
      if (_title.trim().isNotEmpty && _title != '（无标题）') '标题：${_title.trim()}',
      if (_copyText.trim().isNotEmpty) '文案：${_copyText.trim()}',
      if (_subtitle.trim().isNotEmpty) '字幕：${_subtitle.trim()}',
    ];
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => AiCreatePage(seedMaterial: parts.join('\n\n'))));
  }
  String get _musicUrl => (result['music_url']?.toString() ?? '');

  // ⭐ 素材清单（2026-10-22，与小程序端同契约）
  // 固定 4 行（视频/封面/标题文案/话题），缺项灰显占位。
  // 语义是「这个链接能提取什么」的**能力说明**，不是「这次提取到了什么」。
  // 缺项隐藏 → 用户不知道这个能力存在，会怀疑解析不完整。
  String get _copyText {
    final t = result['copy_text']?.toString() ?? '';
    if (t.trim().isNotEmpty) return t;
    final d = result['description']?.toString() ?? '';
    if (d.trim().isNotEmpty && d.trim() != '-') return d;
    return _title;
  }

  List<String> get _tags {
    final raw = result['tags'];
    if (raw is! List) return const [];
    return raw.map((e) => e.toString()).where((s) => s.isNotEmpty).toList();
  }

  String get _coverUrl => result['cover']?.toString() ?? '';
  String get _videoUrl => result['video_url']?.toString() ?? '';

  /// 一行素材。
  /// ⚠️ 用 record 而不是 List<Object?>：List 要靠下标 + 强制转换，
  ///   写错类型要到运行期才炸；record 有具名字段，编译期就能查出来。
  ///   字段：[图标, 名称, 是否有值, 动作标签, 动作回调]
  List<({IconData icon, String name, bool has, String action, VoidCallback onTap})>
      _assetRows(BuildContext context) {
    final rows = <({IconData icon, String name, bool has, String action, VoidCallback onTap})>[];

    // ① 视频
    rows.add((
      icon: Icons.movie_outlined,
      name: '视频',
      has: _videoUrl.isNotEmpty,
      action: '复制直链',
      onTap: () {
        if (_videoUrl.isEmpty) {
          _toast('本视频没有视频', context);
        } else {
          _copy(_videoUrl, '视频直链已复制', context);
        }
      },
    ));

    // ② 封面（PC 端没有「保存到相册」，改为复制封面直链）
    rows.add((
      icon: Icons.image_outlined,
      name: '封面',
      has: _coverUrl.isNotEmpty,
      action: '复制直链',
      onTap: () {
        if (_coverUrl.isEmpty) {
          _toast('本视频没有封面', context);
        } else {
          _copy(_coverUrl, '封面直链已复制', context);
        }
      },
    ));

    // ③ 标题文案
    rows.add((
      icon: Icons.notes_outlined,
      name: '标题文案',
      has: _copyText.trim().isNotEmpty,
      action: '复制文案',
      onTap: () {
        if (_copyText.trim().isEmpty) {
          _toast('本视频没有文案', context);
        } else {
          _copy(_copyText, '文案已复制', context);
        }
      },
    ));

    // ④ 话题
    final tags = _tags;
    rows.add((
      icon: Icons.tag,
      name: '话题',
      has: tags.isNotEmpty,
      action: '复制话题',
      onTap: () {
        if (tags.isEmpty) {
          _toast('本视频没有话题', context);
        } else {
          _copy(tags.map((t) => '#$t').join(' '),
              '${tags.length} 个话题已复制', context);
        }
      },
    ));

    return rows;
  }

  /// 统一提示（缺项时用，语气与小程序端一致）
  void _toast(String msg, BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 2)));
  }

  // ⭐ 文件大小与时长文本（2026-10-22，竞品对齐）
  // 服务端统一格式化后下发（size_text / duration_text），各端口径一致。
  String get _fileSizeText => (result['size_text']?.toString() ?? '');
  String get _durationText => (result['duration_text']?.toString() ?? '');

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

  /// BGM 单独入库（item_type=audio），与视频条目分开 ——
  /// 素材库里按类型区分，回看时知道这是音频不是视频。
  Future<void> _saveBgm() async {
    if (_bgmSaving || _bgmSaved || _musicUrl.isEmpty) return;
    setState(() => _bgmSaving = true);
    try {
      final openid = await session.api.authOpenid();
      await session.api.libraryAdd(
        openid,
        itemType: 'audio',
        title: _str(result['music_title']).isEmpty
            ? '${_str(result['author']).isEmpty ? 'BGM' : _str(result['author'])} 的BGM'
            : _str(result['music_title']),
        platform: _str(result['platform']),
        author: _str(result['music_author']),
        sourceText: _musicUrl,
      );
      if (!mounted) return;
      setState(() => _bgmSaved = true);
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('BGM 已存入素材库（小程序端同步可见）')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('存入失败：$e')));
    } finally {
      if (mounted) setState(() => _bgmSaving = false);
    }
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

          // ── 解析完成 + 「数据不做存储」（竞品对齐：合规护身符）──
          // 明确告知不存储用户解析的内容，配合我们「不提供去除版权水印」的定位：
          // 能力是「获取平台源头就干净的原始文件」，不是「擦除他人作品的版权标识」。
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.check_circle_outline, size: 16,
                  color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Expanded(
                child: Text.rich(
                  TextSpan(children: [
                    const TextSpan(
                        text: '解析已完成',
                        style: TextStyle(fontWeight: FontWeight.w500)),
                    TextSpan(
                        text: _fileSizeText.isEmpty && _durationText.isEmpty
                            ? ' · 数据不做存储，请保存后离开本页面'
                            : ' · ${[
                                if (_durationText.isNotEmpty) _durationText,
                                if (_fileSizeText.isNotEmpty) _fileSizeText,
                              ].join(' ')} · 数据不做存储',
                        style: const TextStyle(
                            color: Color(0xFF888780))),
                  ]),
                  style: theme.textTheme.bodySmall,
                ),
              ),
            ],
          ),
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
          const SizedBox(height: 8),
          // ⭐ 用这段文案去创作（2026-10-24）
          //    素材自动带过去（标题 + 文案 + 字幕），省掉「复制→切窗口→粘贴」。
          SizedBox(
            width: double.infinity,
            child: FilledButton.tonalIcon(
              onPressed: _canCreate ? _goCreate : null,
              icon: const Icon(Icons.edit_note),
              label: const Text('用这段文案创作（DeepSeek）'),
            ),
          ),
          const SizedBox(height: 12),

          // ── 素材清单（2026-10-22，与小程序端同契约）──
          // 固定 4 行，缺项灰显 —— 语义是「能提取什么」的能力说明。
          Card(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('本次可提取',
                      style: theme.textTheme.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  for (final row in _assetRows(context))
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: Row(
                        children: [
                          Icon(row.icon,
                              size: 20,
                              color: row.has
                                  ? theme.colorScheme.primary
                                  : theme.disabledColor),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: 66,
                            child: Text(
                              row.name,
                              style: theme.textTheme.bodyMedium?.copyWith(
                                color: row.has ? null : theme.disabledColor,
                              ),
                            ),
                          ),
                          const Spacer(),
                          TextButton(
                            onPressed: row.onTap,
                            child: Text(row.action,
                                style: TextStyle(
                                  color: row.has
                                      ? theme.colorScheme.primary
                                      : theme.disabledColor,
                                )),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
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
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.music_note),
                    title: Text(_str(result['music_title']).isEmpty
                        ? 'BGM'
                        : _str(result['music_title']),
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                    subtitle: Text(_str(result['music_author']).isEmpty
                        ? '点击复制音频直链（试听可在小程序端）'
                        : '${_str(result['music_author'])} · 点击复制音频直链'),
                    trailing: const Icon(Icons.copy),
                    onTap: () => _copy(_musicUrl, '音频直链已复制', context),
                  ),
                  const Divider(height: 1),
                  // ⭐ BGM 入库走 item_type=audio（服务端 library 表已支持），
                  // 与小程序素材库同库 —— 手机端打开素材库即可试听复用。
                  // 不在本端做试听：不为此引入音频播放器依赖，
                  // 那会让用户多下一个原生包，收益不抵编译风险。
                  ListTile(
                    dense: true,
                    leading: Icon(_bgmSaved ? Icons.check : Icons.library_music_outlined,
                        size: 20,
                        color: _bgmSaved ? Colors.green : null),
                    title: Text(_bgmSaved ? 'BGM 已存入素材库' : '把 BGM 存入素材库',
                        style: const TextStyle(fontSize: 14)),
                    onTap: _bgmSaved ? null : _saveBgm,
                  ),
                ],
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
