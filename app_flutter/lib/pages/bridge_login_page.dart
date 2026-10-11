/// 桥接登录页：显示 6 位绑定码 → 用户去小程序「会员 → 跨端绑定」输入
/// → 本页每 3 秒轮询，绑定成功自动进入首页。
import 'dart:async';
import 'package:flutter/material.dart';

import '../config.dart';
import '../state/session.dart';

class BridgeLoginPage extends StatefulWidget {
  const BridgeLoginPage({super.key, required this.session, required this.onLoggedIn});
  final Session session;
  final VoidCallback onLoggedIn;

  @override
  State<BridgeLoginPage> createState() => _BridgeLoginPageState();
}

class _BridgeLoginPageState extends State<BridgeLoginPage> {
  String _code = '';
  String _error = '';
  bool _binding = false;      // 正在创建码/轮询中
  int _leftSec = 0;
  Timer? _pollTimer;
  Timer? _ttlTimer;

  @override
  void initState() {
    super.initState();
    _newCode();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _ttlTimer?.cancel();
    super.dispose();
  }

  Future<void> _newCode() async {
    setState(() {
      _binding = true;
      _error = '';
    });
    try {
      _code = await widget.session.api
          .bridgeCreate('app_device', widget.session.deviceUid);
      _leftSec = AppConfig.bridgeTtl;
      _startPolling();
    } catch (e) {
      _error = '生成绑定码失败：$e\n请确认解析服务已启动';
    }
    if (mounted) setState(() => _binding = false);
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _ttlTimer?.cancel();
    _pollTimer = Timer.periodic(
        const Duration(milliseconds: AppConfig.bridgePollMs), (_) async {
      try {
        final token = await widget.session.api
            .bridgePoll('app_device', widget.session.deviceUid);
        if (token != null && mounted) {
          _pollTimer?.cancel();
          _ttlTimer?.cancel();
          await widget.session.completeLogin(token);
          if (!mounted) return;
          widget.onLoggedIn();
        }
      } catch (e) {
        // 服务中途重启/网络抖动：停轮询并显式报错，别让 Timer 静默死掉
        _pollTimer?.cancel();
        _ttlTimer?.cancel();
        if (mounted) {
          setState(() => _error = '轮询失败：$e\n请确认解析服务仍在运行，然后点「刷新绑定码」');
        }
      }
    });
    _ttlTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_leftSec <= 0) {
        _pollTimer?.cancel();
        _ttlTimer?.cancel();
        _newCode();                      // 过期自动换新码
        return;
      }
      if (mounted) setState(() => _leftSec--);
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Text('CreatorBox', style: theme.textTheme.headlineMedium
                    ?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                Text('与小程序同账号 · 会员/素材库全端同步',
                    style: theme.textTheme.bodySmall),
                const SizedBox(height: 48),
                if (_binding)
                  const CircularProgressIndicator()
                else ...[
                  Text('输入此绑定码到小程序', style: theme.textTheme.bodyLarge),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 32, vertical: 20),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(_code,
                        style: theme.textTheme.displaySmall?.copyWith(
                            fontWeight: FontWeight.w800,
                            letterSpacing: 8)),
                  ),
                  const SizedBox(height: 16),
                  Text('路径：小程序 → 会员 → 跨端绑定\n有效期 $_leftSec 秒，过期自动刷新',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall),
                ],
                if (_error.isNotEmpty) ...[
                  const SizedBox(height: 24),
                  Text(_error,
                      style: const TextStyle(color: Colors.red),
                      textAlign: TextAlign.center),
                ],
                const SizedBox(height: 32),
                TextButton(onPressed: _newCode, child: const Text('刷新绑定码')),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
