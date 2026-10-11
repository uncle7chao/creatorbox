import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/cb_theme.dart';
import 'screens/home_screen.dart';
import 'services/api_client.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  setupErrorHandler();
  runApp(const CreatorBoxApp());
}

class CreatorBoxApp extends StatelessWidget {
  const CreatorBoxApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        // 解析服务客户端（全局单例）
        Provider(create: (_) => ApiClient()),
      ],
      child: MaterialApp(
        title: 'CreatorBox',
        debugShowCheckedModeBanner: false,
        theme: CBTheme.light(),
        home: const HomeScreen(),
      ),
    );
  }
}

/// ⭐ 全局错误捕获
///
/// 为什么必须写：
/// Flutter 在 release 模式下会把未捕获异常**静默吞掉**，
/// 用户只看到白屏，日志在真机上根本拿不到 → 无法定位线上问题。
void setupErrorHandler() {
  FlutterError.onError = (details) {
    debugPrint('❌ Flutter 异常: ${details.exception}');
    debugPrint('   库: ${details.library}');
    debugPrint('   上下文: ${details.context}');
    // 生产环境应上报到自己的日志服务
  };

  // 异步错误（Future 里没 await 到的）
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('❌ 未捕获异步异常: $error');
    debugPrint('   堆栈: ${stack}');
    return true; // true = 视为已处理，不崩进程
  };
}
