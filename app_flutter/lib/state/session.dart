/// 会话状态：token / 设备身份 / 账号信息，SharedPreferences 持久化。
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../api/client.dart';

class Session {
  Session(this._prefs) {
    _token = _prefs.getString('cb_token') ?? '';
    _deviceUid = _prefs.getString('cb_device_uid') ?? '';
    if (_deviceUid.isEmpty) {
      // 不用 const：v4() 是运行时方法，const 在此无任何收益，
      // 却在 uuid 版本差异（有无 const 构造器）下可能变成编译错误。
      _deviceUid = Uuid().v4();
      _prefs.setString('cb_device_uid', _deviceUid);
    }
    api.setToken(_token);
  }

  final SharedPreferences _prefs;
  final CBApi api = CBApi();

  String _token = '';
  String _deviceUid = '';
  Map<String, dynamic>? me;      // /api/auth/me 的返回
  bool loggedIn = false;

  String get deviceUid => _deviceUid;

  /// member 是嵌套 dict（server: get_member_state 返回 {is_member, expire_at}），
  /// 这里逐层兜住：任一层缺失/类型不对都退化为「非会员」，不崩。
  bool get isMember {
    final m = me?['member'];
    if (m is Map && m['is_member'] == true) return true;
    return false;
  }

  String get userLabel {
    final uid = me?['user_id']?.toString() ?? '';
    return uid.length > 10 ? '用户 ${uid.substring(0, 8)}…' : '未登录';
  }

  /// 已有 token → 直接验活；成功即登录态成立
  Future<bool> tryResume() async {
    if (_token.isEmpty) return false;
    me = await api.authMe();
    loggedIn = me != null;
    return loggedIn;
  }

  /// 桥接轮询成功后调用：保存 token 并拉取账号信息
  Future<void> completeLogin(String token) async {
    _token = token;
    await _prefs.setString('cb_token', token);
    api.setToken(token);
    me = await api.authMe();
    loggedIn = me != null;
  }

  /// 退出登录（保留 device uid —— 同设备可重新桥接）
  Future<void> logout() async {
    _token = '';
    loggedIn = false;
    me = null;
    await _prefs.remove('cb_token');
    api.setToken('');
  }
}
