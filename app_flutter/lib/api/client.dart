/// CreatorBox 后端 API 客户端（P1 最小面）。
///
/// 服务端契约见 CreatorBox/server/app/main.py：
/// · POST /api/auth/bridge/create {provider, provider_uid} → {ok, code, expires_in}
/// · POST /api/auth/bridge/poll  {provider, provider_uid} → {ok, token, user_id, member}
///   （未绑定返回 400 {detail:'not_bound'}——轮询的常态，不是错误）
/// · GET  /api/auth/me   (X-User-Token) → {user_id, nickname, member, identities}
/// · POST /api/parse     {text} → 解析结果（12 平台统一结构）
/// · GET  /api/health    → {ready, platforms}
import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config.dart';

class ApiError implements Exception {
  final int statusCode;
  final String detail;
  ApiError(this.statusCode, this.detail);
  @override
  String toString() => detail;
}

class CBApi {
  CBApi({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  String _token = '';

  void setToken(String token) => _token = token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token.isNotEmpty) 'X-User-Token': _token,
      };

  Uri _u(String path) => Uri.parse('${AppConfig.apiBase}$path');

  Future<Map<String, dynamic>> _send(String method, String path,
      {Map<String, dynamic>? body}) async {
    final req = http.Request(method, _u(path))
      ..headers.addAll(_headers);
    if (body != null) req.body = jsonEncode(body);

    // 超时兜底：默认 http 包不设超时，服务假死时界面会永远转圈
    final res = await _client.send(req).then(http.Response.fromStream).timeout(
          const Duration(seconds: AppConfig.requestTimeoutSec),
          onTimeout: () => throw ApiError(
              0, '请求超时（${AppConfig.requestTimeoutSec}s），服务可能已假死'),
        );

    // ⚠️ 网关/反向代理出错时返回的是 HTML 而非 JSON，
    // 直接 jsonDecode 会抛 FormatException，用户看到的是天书。
    // 这里统一兜住：解析失败一律按状态码给出可读信息。
    Map<String, dynamic> decoded;
    try {
      final raw = utf8.decode(res.bodyBytes);
      decoded = raw.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      if (res.statusCode >= 400) {
        throw ApiError(res.statusCode,
            '服务返回非 JSON（HTTP ${res.statusCode}）'
            '——请确认 ${AppConfig.apiBase} 是 CreatorBox 服务而非反向代理');
      }
      rethrow;
    }

    if (res.statusCode >= 400) {
      throw ApiError(res.statusCode,
          (decoded['detail']?.toString()) ?? 'HTTP ${res.statusCode}');
    }
    return decoded;
  }

  // ── 账号中台 ──

  /// 发起跨端绑定：返回 6 位桥接码（5 分钟有效，用户去小程序输入）
  Future<String> bridgeCreate(String provider, String providerUid) async {
    final r = await _send('POST', '/api/auth/bridge/create',
        body: {'provider': provider, 'provider_uid': providerUid});
    if (r['ok'] != true) throw ApiError(200, 'bridge_create_failed');
    // ⚠️ 不裸 as String：服务端少字段时强转会抛 TypeError，用户只看到天书
    final code = r['code']?.toString() ?? '';
    if (code.isEmpty) throw ApiError(200, '服务端未返回绑定码');
    return code;
  }

  /// 轮询绑定状态。返回 token；未绑定返回 null（非错误）。
  Future<String?> bridgePoll(String provider, String providerUid) async {
    try {
      final r = await _send('POST', '/api/auth/bridge/poll',
          body: {'provider': provider, 'provider_uid': providerUid});
      if (r['ok'] != true) return null;
      final t = r['token']?.toString() ?? '';
      return t.isEmpty ? null : t;
    } on ApiError catch (e) {
      if (e.statusCode == 400 && e.detail == 'not_bound') return null;
      rethrow;
    }
  }

  /// token → 账号全貌。token 失效返回 null。
  Future<Map<String, dynamic>?> authMe() async {
    if (_token.isEmpty) return null;
    try {
      return await _send('GET', '/api/auth/me');
    } on ApiError catch (e) {
      if (e.statusCode == 401) return null;
      rethrow;
    }
  }

  /// token → openid。
  ///
  /// 素材库 / 配额 / 会员等存量接口以 openid 为主键，而本端只有 token。
  /// 服务端做一次兑换，客户端【不缓存 openid】—— 每次现取，
  /// 避免 token 过期后仍拿着旧 openid 去请求导致串号或 401。
  Future<String> authOpenid() async {
    final r = await _send('GET', '/api/auth/openid');
    final v = r['openid']?.toString() ?? '';
    if (v.isEmpty) throw ApiError(200, '服务端未返回 openid');
    return v;
  }

  // ── 素材库（跨端共用，与小程序同库）──

  /// 素材库列表。服务端限制上限 200 条。
  Future<List<Map<String, dynamic>>> libraryList(String openid,
      {int limit = 100}) async {
    final r = await _send('GET',
        '/api/library/list?openid=${Uri.encodeQueryComponent(openid)}&limit=$limit');
    final items = r['items'];
    if (items is! List) return const [];
    return items.whereType<Map>().toList();
  }

  /// 加入素材库。itemType: video / image / copy
  Future<int> libraryAdd(String openid,
      {String itemType = 'video',
      String title = '',
      String platform = '',
      String author = '',
      String cover = '',
      String sourceText = ''}) async {
    final r = await _send('POST', '/api/library/add', body: {
      'openid': openid,
      'item_type': itemType,
      'title': title,
      'platform': platform,
      'author': author,
      'cover': cover,
      'source_text': sourceText,
    });
    return int.tryParse(r['id']?.toString() ?? '') ?? 0;
  }

  /// 删除素材库条目。
  Future<void> libraryDelete(String openid, int itemId) async {
    // 服务端复用 source_text 传要删的 id（见 server/app/main.py:831）
    await _send('POST', '/api/library/delete',
        body: {'openid': openid, 'source_text': itemId.toString()});
  }

  // ── 解析 ──

  /// 12 平台统一解析入口（小程序同款 /api/parse）
  Future<Map<String, dynamic>> parse(String text,
      {bool noCache = false}) async {
    return _send('POST', '/api/parse',
        body: {'text': text, 'no_cache': noCache});
  }

  Future<Map<String, dynamic>> health() => _send('GET', '/api/health');

  void dispose() => _client.close();
}
