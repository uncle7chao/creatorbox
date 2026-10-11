/// 账号设置页：注销 / 退出 / 合规声明 / 服务地址。
///
/// 注销是《小程序隐私保护指引》§四的硬要求，也是审核会点的地方，
/// 因此做成「先预览 → 明示影响 → 二次确认 → 才调用」的完整链路：
///   · 预览把「将删除多少条」摆给用户看，不让他盲删
///   · 确认弹窗必须回显「不可恢复」
///   · confirm 回传 user_id（服务端校验），这是第二道闸
///
/// ⚠️ 注销成功后要清掉本地 token —— 否则下次启动仍会带着已注销身份进首页。
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart' show ApiError;
import '../config.dart';
import '../main.dart' show onSessionChanged;
import '../state/session.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.session});
  final Session session;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  bool _busy = false;

  Future<void> _copyApiBase() async {
    await Clipboard.setData(ClipboardData(text: AppConfig.apiBase));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('服务地址已复制')));
  }

  // ── 退出登录 ─────────────────────────────────────────────────────────────
  Future<void> _confirmLogout() async {
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
    // 通知启动闸切回登录态
    onSessionChanged?.call();
  }

  // ── 注销账号（不可逆）─────────────────────────────────────────────────────
  Future<void> _confirmPurge() async {
    if (_busy) return;
    setState(() => _busy = true);
    Map<String, dynamic> pv;
    try {
      pv = await widget.session.api.purgePreview();
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('查询失败：$e')));
      return;
    }

    final userId = pv['user_id']?.toString() ?? '';
    final counts = (pv['counts'] as Map?) ?? const {};
    // 名称用中文，让人看得懂「删的是什么」；只展示 >0 的项
    const labels = {
      'library_items': '素材库条目',
      'quota_daily': '配额记录',
      'banned_daily': '违禁词记录',
      'points_sign': '签到记录',
      'identities': '跨端绑定身份',
      'auth_tokens': '登录凭证',
    };
    final lines = <String>[];
    counts.forEach((k, v) {
      final n = v is int ? v : int.tryParse('$v') ?? 0;
      if (n > 0) lines.add('· ${labels[k] ?? k}：$n 条');
    });

    if (!mounted) return;
    setState(() => _busy = false);

    if (userId.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('登录态已失效，请重新绑定账号')));
      return;
    }

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('注销账号'),
        content: Text(
            '将删除以下数据：\n${lines.isEmpty ? '· 无' : lines.join('\n')}\n\n'
            '⚠️ 此操作【不可恢复】，且会同时退出 App / 电脑端登录。\n'
            '平台运营数据（卡密库、违禁词库）不受影响。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('再想想')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确认注销'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _busy = true);
    try {
      await widget.session.api.purgeAccount(userId);
      // 先清本地登录态，再通知启动闸 —— 顺序反了会带着死 token 重建首页
      await widget.session.logout();
      if (!mounted) return;
      setState(() => _busy = false);
      onSessionChanged?.call();
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('账号已注销，全部数据已删除')));
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('注销失败：${e.detail}')));
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('注销失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        children: [
          // ── 账号 ──
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Text('账号', style: theme.textTheme.labelLarge),
          ),
          ListTile(
            leading: const Icon(Icons.badge_outlined),
            title: const Text('当前账号'),
            subtitle: Text(widget.session.userLabel),
          ),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('退出登录 / 换账号'),
            subtitle: const Text('保留本机设备标识，便于再次绑定'),
            onTap: _confirmLogout,
          ),
          const Divider(height: 24),

          // ── 数据与隐私 ──
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
            child: Text('数据与隐私', style: theme.textTheme.labelLarge),
          ),
          ListTile(
            leading: Icon(Icons.delete_forever_outlined,
                color: Colors.red.shade700),
            title: Text('注销账号',
                style: TextStyle(color: Colors.red.shade700)),
            subtitle: const Text('删除全部个人数据，不可恢复'),
            onTap: _busy ? null : _confirmPurge,
          ),
          ListTile(
            leading: const Icon(Icons.description_outlined),
            title: const Text('服务说明与免责声明'),
            subtitle: const Text('内容权利、适用范围、投诉渠道'),
            onTap: () => showDialog<void>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: const Text('服务说明'),
                content: const SingleChildScrollView(
                  child: Text(
                    '本工具提供的是「内容地址解析」服务 —— 获取平台在分发环节使用的'
                    '原始地址，从而获得平台源头就干净的原始文件。\n\n'
                    '我们不提供、不协助去除他人作品上的署名、版权水印或其他权利标识。\n\n'
                    '内容的著作权归原作者及原平台所有。使用前请确保已获合法授权，'
                    '并遵守原平台的使用条款。\n\n'
                    '你的数据：账号标识、素材库条目、跨端绑定身份会保存在服务端；'
                    '可在「注销账号」中一次性删除。PDF 工具上传的文件保留 1 天后自动清除。',
                    style: TextStyle(fontSize: 13, height: 1.6),
                  ),
                ),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('知道了')),
                ],
              ),
            ),
          ),
          const Divider(height: 24),

          // ── 技术信息 ──
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
            child: Text('技术信息', style: theme.textTheme.labelLarge),
          ),
          ListTile(
            leading: const Icon(Icons.dns_outlined),
            title: const Text('解析服务地址'),
            subtitle: Text(AppConfig.apiBase),
            trailing: const Icon(Icons.copy, size: 20),
            onTap: _copyApiBase,
          ),
          const SizedBox(height: 24),
          Center(
            child: Text('CreatorBox · 内容地址解析',
                style: theme.textTheme.bodySmall),
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }
}