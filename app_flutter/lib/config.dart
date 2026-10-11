/// 全局配置。API 地址用 --dart-define 覆盖：
///   flutter run --dart-define=CB_API_BASE=http://192.168.x.x:8080
/// 公网部署后默认值改为 https://api.你的域名
class AppConfig {
  static const apiBase = String.fromEnvironment(
    'CB_API_BASE',
    defaultValue: 'http://127.0.0.1:8080',
  );

  /// 桥接轮询间隔（毫秒）
  static const bridgePollMs = 3000;

  /// 单次请求超时（秒）。解析类接口较慢，给足 45s；
  /// 桥接轮询是 3s 节奏，远小于超时，不会互相干扰。
  static const requestTimeoutSec = 45;

  /// 桥接码有效期（秒），与服务端 _BRIDGE_TTL 一致
  static const bridgeTtl = 300;
}
