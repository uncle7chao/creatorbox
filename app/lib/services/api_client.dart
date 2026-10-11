import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/parse_result.dart';

/// 解析服务 API 客户端
///
/// ⭐ 契约严格对齐 server/app/main.py：
/// ```
/// POST /api/parse
///   { "text": str, "quality": str = "1080p", "no_cache": bool = false }
/// GET  /api/health        → { engine, platforms, browser_available, ... }
/// GET  /api/capabilities
/// ```
///
/// ⚠️ 超时策略：解析可能要下载 m3u8 合并（AcFun 实测 5.4s），
///    但网络差时会更久 → 30s 起步，不设太短。
class ApiClient {
  ApiClient({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ?? defaultBaseUrl,
        _client = client ?? http.Client();

  /// ⭐ 真机调试要改成局域网 IP，不能用 127.0.0.1
  /// （127.0.0.1 指的是手机自己）
  ///
  /// 改法：`adb reverse tcp:8080 tcp:8080` 后仍可用 127.0.0.1，
  ///      或直接填电脑的局域网 IP。
  static const defaultBaseUrl = String.fromEnvironment(
    'CB_API',
    defaultValue: 'http://127.0.0.1:8080',
  );

  final String baseUrl;
  final http.Client _client;

  static const _timeout = Duration(seconds: 30);

  /// 解析
  Future<ParseResult> parse(
    String text, {
    String quality = '1080p',
    bool noCache = false,
  }) async {
    if (text.trim().isEmpty) {
      return ParseResult.failure('请输入链接');
    }
    try {
      final resp = await _client
          .post(
            Uri.parse('$baseUrl/api/parse'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({
              'text': text.trim(),
              'quality': quality,
              'no_cache': noCache,
            }),
          )
          .timeout(_timeout);

      if (resp.statusCode != 200) {
        return ParseResult.failure(
          '服务返回 ${resp.statusCode}',
          hint: resp.statusCode >= 500
              ? '服务端异常，请稍后重试'
              : '请求被拒绝（${resp.statusCode}）',
        );
      }

      final body = jsonDecode(utf8.decode(resp.bodyBytes));
      return ParseResult.fromJson((body as Map).cast<String, dynamic>());
    } on TimeoutException {
      return const ParseResult.failure(
        '解析超时',
        hint: '网络较慢或视频过大，可稍后重试',
      );
    } catch (e) {
      return ParseResult.failure(
        '连接失败',
        hint: '无法连接解析服务（$baseUrl）\n'
            '请确认：\n'
            '· 电脑已运行 start-server.ps1\n'
            '· 手机与电脑在同一 WiFi',
      );
    }
  }

  /// 服务健康状态
  Future<ServiceHealth?> health() async {
    try {
      final resp = await _client
          .get(Uri.parse('$baseUrl/api/health'))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode != 200) return null;
      return ServiceHealth.fromJson(
          (jsonDecode(utf8.decode(resp.bodyBytes)) as Map)
              .cast<String, dynamic>());
    } catch (_) {
      return null;
    }
  }

  void dispose() => _client.close();
}

/// 服务健康状态
class ServiceHealth {
  final String engine;
  final List<String> platforms;
  final bool browserAvailable;
  final bool allOk;

  const ServiceHealth({
    required this.engine,
    required this.platforms,
    required this.browserAvailable,
    required this.allOk,
  });

  /// 是否是零浏览器依赖的纯 HTTP 模式（v3 定位的「韧性」卖点）
  bool get isPureHttp => engine == 'pure_http';

  factory ServiceHealth.fromJson(Map<String, dynamic> j) {
    final platforms = (j['platforms'] as List?)?.map((e) => e.toString()).toList() ??
        const <String>[];
    return ServiceHealth(
      engine: j['engine'] as String? ?? 'unknown',
      platforms: platforms,
      browserAvailable: j['browser_available'] as bool? ?? false,
      allOk: j['all_ok'] as bool? ?? true,
    );
  }
}
