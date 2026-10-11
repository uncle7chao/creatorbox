import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'config.dart';
import 'pages/bridge_login_page.dart';
import 'pages/home_page.dart';
import 'state/session.dart';

/// 登录态变化的全局回调。
/// 退出登录时首页需要「退回登录页」—— 但 HomePage 无法反向操作 _Gate，
/// 用全局回调让 Gate 自己处理，避免命名路由（无 routes 配置时 pushNamed 会崩）。
typedef SessionChanged = void Function();

SessionChanged? onSessionChanged;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final session = Session(prefs);

  runApp(CreatorBoxApp(session: session));
}

class CreatorBoxApp extends StatelessWidget {
  const CreatorBoxApp({super.key, required this.session});
  final Session session;

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xFFE8890C);      // 品牌琥珀橙，与小程序同源
    return MaterialApp(
      title: 'CreatorBox',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: seed),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
            seedColor: seed, brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: _Gate(session: session),
    );
  }
}

/// 启动闸：已有 token 先验活，失败或无 token → 桥接登录
class _Gate extends StatefulWidget {
  const _Gate({required this.session});
  final Session session;

  @override
  State<_Gate> createState() => _GateState();
}

class _GateState extends State<_Gate> {
  bool _checking = true;
  bool _loggedIn = false;

  @override
  void initState() {
    super.initState();
    // 首页退出登录时回调这里切回登录态
    onSessionChanged = () {
      if (mounted) setState(() => _loggedIn = false);
    };
    widget.session.tryResume().then((ok) {
      if (mounted) setState(() {
        _loggedIn = ok;
        _checking = false;
      });
    });
  }

  @override
  void dispose() {
    onSessionChanged = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Scaffold(
          body: Center(child: CircularProgressIndicator()));
    }
    return _loggedIn
        ? HomePage(session: widget.session)
        : BridgeLoginPage(
            session: widget.session,
            onLoggedIn: () => setState(() => _loggedIn = true),
          );
  }
}
