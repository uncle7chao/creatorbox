/// 首页：解析入口（12 平台统一 /api/parse）。
/// MVP 交互：粘贴链接 → 解析 → 结果页。
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../brand.dart';
import '../config.dart';
import '../main.dart' show onSessionChanged;
import '../state/session.dart';
import 'banned_page.dart';
import 'batch_page.dart';
import 'library_page.dart';
import 'member_page.dart';
import 'parse_result_page.dart';
import 'settings_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.session});
  final Session session;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _urlCtrl = TextEditingController();
  bool _parsing = false;
  bool _noCache = false;   // 绕过服务端缓存（缓存不存 options 档位）
  String? _error;
  int _platforms = 0;
  bool _serviceUp = true;  // 健康检查结果：false 时首屏给红字提示，别让用户干等报错
  bool _reviewMode = false; // 提审收敛模式（服务端下发，客户端不自判）
  List<String> _platformNames = const [];

  @override
  void initState() {
    super.initState();
    _loadHealth();
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadHealth() async {
    try {
      final h = await widget.session.api.health();
      if (mounted) {
        setState(() {
          _platforms = (h['platforms'] as List?)?.length ?? 0;
          _serviceUp = true;
        });
      }
    } catch (_) {
      // 服务未启动：首屏就红字说明，别让用户点完解析才报错
      if (mounted) setState(() => _serviceUp = false);
    }
    // 可见性裁决独立取：失败不影响主流程，只是退化为不显示平台名
    try {
      final v = await widget.session.api.visibility();
      final list = (v['platforms'] as List?) ?? const [];
      if (!mounted || list.isEmpty) return;
      setState(() {
        _reviewMode = v['review_mode'] == true;
        _platforms = list.length;
        _platformNames = list
            .map((e) => (e is Map ? e['name_cn']?.toString() ?? '' : ''))
            .where((s) => s.isNotEmpty)
            .toList();
      });
    } catch (_) {/* 拿不到就保持旧值，不打扰首屏 */}
  }

  /// 从系统剪贴板读取链接（桌面端主路径：用户已在浏览器/微信里复制了分享口令）
  Future<void> _pasteFromClipboard() async {
    try {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      final text = (data?.text ?? '').trim();
      if (text.isEmpty) {
        setState(() => _error = '剪贴板是空的，先去复制一条分享链接');
        return;
      }
      _urlCtrl.text = text;
      setState(() => _error = null);
      // 读取到就直接解析，省一次点击
      _go();
    } catch (e) {
      setState(() => _error = '读取剪贴板失败：$e');
    }
  }

  Future<void> _go() async {
    final text = _urlCtrl.text.trim();
    if (text.isEmpty || _parsing) return;
    setState(() {
      _parsing = true;
      _error = null;
    });
    try {
      final r = await widget.session.api.parse(text, noCache: _noCache);
      if (!mounted) return;
      if (r['success'] == true) {
        Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => ParseResultPage(
                session: widget.session, result: r)));
      } else {
        // 服务端解析失败时 error 可能是 null，给个兜底文案而不是空白
        final msg = (r['error'] ?? r['message'])?.toString();
        setState(() => _error = (msg == null || msg.isEmpty)
            ? '解析失败（服务端未返回原因）'
            : msg);
      }
    } on ApiError catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = '连接失败：$e\n请确认解析服务已启动');
    } finally {
      if (mounted) setState(() => _parsing = false);
    }
  }

  Future<void> _onMenu(String v) async {
    if (v == 'library') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => LibraryPage(session: widget.session)));
      return;
    }
    if (v == 'batch') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => BatchPage(session: widget.session)));
      return;
    }
    if (v == 'member') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => MemberPage(session: widget.session)));
      return;
    }
    if (v == 'settings') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => SettingsPage(session: widget.session)));
      return;
    }
    if (v == 'banned') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => BannedPage(session: widget.session)));
      return;
    }
    if (v == 'refresh') {
      await _loadHealth();
      return;
    }
    if (v == 'logout') {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('退出登录'),
          content: const Text('退出后可重新用小程序绑定另一个账号。\n'
              '本机设备标识会保留，同一账号再次绑定无需重新输入设备。'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('取消')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('退出')),
          ],
        ),
      );
      if (ok != true || !mounted) return;
      await widget.session.logout();
      if (!mounted) return;
      // 通知启动闸切回登录态（main.dart 注册的全局回调）
      onSessionChanged?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text(brand.TITLE_APP),
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Chip(
                avatar: Icon(widget.session.isMember
                    ? Icons.workspace_premium
                    : Icons.person_outline),
                label: Text(widget.session.userLabel),
              ),
            ),
          ),
          // 账号菜单：当前 Chip 只读，这里给出换账号/退出的出口
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert),
            onSelected: _onMenu,
            // ⚠️ PopupMenuItem 高度上限 48px（Flutter 运行期断言），
            // 里面放 ListTile 会超高直接崩 —— 用紧凑 Row。
            itemBuilder: (_) => const [
              PopupMenuItem(
                value: 'batch',
                height: 44,
                child: Row(children: [
                  Icon(Icons.playlist_add, size: 18),
                  SizedBox(width: 10),
                  Text('批量解析'),
                ]),
              ),
              PopupMenuItem(
                value: 'library',
                height: 44,
                child: Row(children: [
                  Icon(Icons.inbox_outlined, size: 18),
                  SizedBox(width: 10),
                  Text('素材库 / 历史'),
                ]),
              ),
              PopupMenuItem(
                value: 'member',
                height: 44,
                child: Row(children: [
                  Icon(Icons.card_membership, size: 18),
                  SizedBox(width: 10),
                  Text('会员与积分'),
                ]),
              ),
              PopupMenuItem(
                value: 'banned',
                height: 44,
                child: Row(children: [
                  Icon(Icons.fact_check_outlined, size: 18),
                  SizedBox(width: 10),
                  Text('违禁词自检'),
                ]),
              ),
              PopupMenuItem(
                value: 'settings',
                height: 44,
                child: Row(children: [
                  Icon(Icons.settings_outlined, size: 18),
                  SizedBox(width: 10),
                  Text('设置 / 注销账号'),
                ]),
              ),
              PopupMenuItem(
                value: 'refresh',
                height: 44,
                child: Row(children: [
                  Icon(Icons.refresh, size: 18),
                  SizedBox(width: 10),
                  Text('刷新服务状态'),
                ]),
              ),
              PopupMenuItem(
                value: 'logout',
                height: 44,
                child: Row(children: [
                  Icon(Icons.logout, size: 18),
                  SizedBox(width: 10),
                  Text('退出登录 / 换账号'),
                ]),
              ),
            ],
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(_reviewMode ? '多平台素材解析工具' : '粘贴任意链接，一键解析视频',
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(_serviceUp
                ? (_platformNames.isEmpty
                    ? '支持 $_platforms 个平台'
                    : '当前支持 $_platforms 个平台：${_platformNames.join(' / ')}')
                : '解析服务未连接 —— 请先启动 server（start-server.ps1）',
                style: theme.textTheme.bodySmall
                    .copyWith(color: _serviceUp ? null : Colors.red)),
            const SizedBox(height: 16),
            TextField(
              controller: _urlCtrl,
              maxLines: 3,
              minLines: 1,
              decoration: InputDecoration(
                hintText: '粘贴分享链接或口令…',
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                    icon: const Icon(Icons.clear), onPressed: () {
                  _urlCtrl.clear();
                }),
              ),
              onSubmitted: (_) => _go(),
            ),
            const SizedBox(height: 8),
            // 桌面端主路径：用户已在浏览器/微信复制好分享口令，一键读取
            OutlinedButton.icon(
              onPressed: _parsing ? null : _pasteFromClipboard,
              icon: const Icon(Icons.content_paste),
              label: const Text('从剪贴板读取并解析'),
            ),
            const SizedBox(height: 8),
            // 批量是高频入口，不该藏在 ⋮ 菜单里
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => BatchPage(session: widget.session)));
              },
              icon: const Icon(Icons.playlist_add),
              label: const Text('批量解析（多条一次）'),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _parsing ? null : _go,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: _parsing
                    ? const SizedBox(
                        width: 20, height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('开始解析',
                        style: TextStyle(fontSize: 16)),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!,
                  style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 4),
            SwitchListTile(
              value: _noCache,
              onChanged: _parsing ? null : (v) => setState(() => _noCache = v),
              title: const Text('强制重新解析'),
              subtitle: const Text('跳过服务端缓存。缓存不保存清晰度档位，想看完整档位请开启',
                  style: TextStyle(fontSize: 12)),
              contentPadding: EdgeInsets.zero,
              dense: true,
            ),
            const Spacer(),
            InkWell(
              onTap: () {
                Clipboard.setData(ClipboardData(text: AppConfig.apiBase));
                ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('服务地址已复制')));
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Text('服务地址：${AppConfig.apiBase}（点击复制）',
                    style: theme.textTheme.bodySmall),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
