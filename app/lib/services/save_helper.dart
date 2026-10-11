import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../core/cb_colors.dart';
import '../models/parse_result.dart';
import '../screens/library_screen.dart';

/// 下载并分享
///
/// ⭐ 为什么必须先下载再分享（2026-10-06 修正）：
///   我原来写 `Share.shareXFiles([XFile(url)])`，把**远程 URL 字符串**
///   当成文件路径传了。`XFile` 走的是 `File(uri)`，
///   传http 字符串会直接抛异常 —— 分享面板根本调不起来。
///
///   正确流程：dio 下载到临时目录 → 用**本地路径**构造 XFile → 调起分享。
class SaveHelper {
  SaveHelper._();

  static final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 180), // 大文件要给足
  ));

  /// 下载并调起分享
  ///
  /// [url] 远程直链（可能带签名与时效）
  /// [fallbackTitle] 兜底文件名
  /// 返回是否成功
  static Future<bool> downloadAndShare({
    required BuildContext context,
    required String url,
    required String fallbackTitle,
    List<String> extraUrls = const [],
  }) async {
    var dir = '';
    try {
      dir = (await getTemporaryDirectory()).path;
      final safe = _safeName(fallbackTitle);
      final ext = _guessExt(url);
      final path = p.join(dir, '$safe$ext');

      // 进度回调
      await _dio.download(
        url,
        path,
        onReceiveProgress: (received, total) {
          if (!context.mounted) return;
          // 静默更新按钮文案，不 setState 整页（避免频繁重建）
        },
        options: Options(
          followRedirects: true,
          headers: const {
            // 某些 CDN 校验 Referer
            'User-Agent':
                'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
          },
        ),
      );

      final files = <XFile>[XFile(path)];
      // 多图：把其余图也带上（一次分享多张）
      for (final u in extraUrls.take(9)) {
        final p2 = p.join(dir, '${safe}_${files.length}$(_guessExt(u))');
        try {
          await _dio.download(u, p2, options: Options(followRedirects: true));
          files.add(XFile(p2));
        } catch (_) {
          // 单张失败不影响整体
        }
      }

      await SharePlus.instance.share(
        ShareParams(
          files: files,
          fileNameOverrides: [safe + ext],
          text: '$fallbackTitle\n来自 CreatorBox',
        ),
      );
      return true;
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(
            content: Text('保存失败：${_brief(e)}'),
            behavior: SnackBarBehavior.floating,
            backgroundColor: CBColors.danger500,
          ));
      }
      return false;
    } finally {
      // 清理临时文件（分享是异步的，延后删）
      if (dir.isNotEmpty) {
        Future.delayed(const Duration(minutes: 5), () {
          try {
            final d = Directory(dir);
            if (d.existsSync()) d.deleteSync(recursive: true);
          } catch (_) {}
        });
      }
    }
  }

  /// 文件名安全化（Windows/Android 都非法的那批字符）
  static String _safeName(String title) {
    var s = title.replaceAll(RegExp(r'[\\/:*?"<>|\r\n\t]'), '_').trim();
    if (s.isEmpty) s = 'creatorbox';
    if (s.length > 40) s = s.substring(0, 40);
    return s;
  }

  /// 从 URL 猜扩展名
  static String _guessExt(String url) {
    final clean = url.split('?').first;
    final m = RegExp(r'\.(mp4|mov|m4v|webm|mkv|flv|jpg|jpeg|png|webp|gif)$',
            caseSensitive: false)
        .firstMatch(clean);
    if (m != null) return '.${m.group(1)}';
    // 播放地址常见 ?x-expires 参数，取不到就按视频猜
    return '.mp4';
  }

  /// 把异常压成一行
  static String _brief(Object e) {
    final s = e.toString();
    if (s.length <= 60) return s;
    return '${s.substring(0, 57)}…';
  }
}
