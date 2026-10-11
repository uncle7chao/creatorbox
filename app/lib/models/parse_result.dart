/// 解析结果模型 —— ⭐ 严格对齐服务端 `/api/parse` 的返回
///
/// 契约来源：server/app/main.py + server/app/meta.py
/// 改动服务端字段时**必须同步这里**，否则客户端会静默丢数据。
///
///设计约束：可选字段一律给默认值，**不因缺字段而崩溃**。
///   理由：服务端 8 个平台字段完备度不同（如好看视频不下发作者名），
///   客户端必须能优雅降级。
library;

/// 清晰度选项（对应服务端 options[]）
class QualityOption {
  final String gear;
  final int? width;
  final int? height;
  final String url;
  final String cdn;
  final bool noWatermark;

  /// 地址是否带签名/时效（决定能否长期缓存）
  final bool signed;

  const QualityOption({
    required this.gear,
    required this.url,
    this.width,
    this.height,
    this.cdn = '',
    this.noWatermark = true,
    this.signed = false,
  });

  /// 「1080P」这样的展示文案
  String get label {
    if (gear.isNotEmpty) return gear;
    if (height != null) return '${height}P';
    return '默认';
  }

  factory QualityOption.fromJson(Map<String, dynamic> j) {
    return QualityOption(
      gear: j['gear'] as String? ?? '',
      width: j['width'] as int?,
      height: j['height'] as int?,
      url: j['url'] as String? ?? '',
      cdn: j['cdn'] as String? ?? '',
      noWatermark: j['no_watermark'] as bool? ?? true,
      // 服务端用 url_expiry_note / m3u8_only 表达「带签名」
      signed: j['signed'] as bool? ?? false,
    );
  }
}

/// 图集的一张图
class ImageItem {
  final String url;
  final int? width;
  final int? height;
  final String format;

  const ImageItem({
    required this.url,
    this.width,
    this.height,
    this.format = '',
  });

  factory ImageItem.fromJson(Map<String, dynamic> j) => ImageItem(
        url: j['url'] as String? ?? '',
        width: j['width'] as int?,
        height: j['height'] as int?,
        format: j['format'] as String? ?? '',
      );
}

/// 统一元信息（服务端 meta 字段）
class ParseMeta {
  final String title;

  /// 标题来源：ssr / share_text / desc_head / template_skipped
  /// 客户端用它提示「标题可能不完整」
  final String titleSource;
  final String description;
  final String cover;
  final String authorName;
  final String authorId;
  final String authorAvatar;

  /// 时长（秒）
  final double? durationS;

  /// 发布时间（'YYYY-MM-DD HH:MM'）
  final String? publishTime;

  /// 平台自带的展示文本（如「20天前」）
  final String? publishTimeText;

  /// 统计数字 {like, comment, collect, share, view, danmaku, coin}
  final Map<String, int> stats;

  /// 统计展示文本（如「450万」）
  final Map<String, String> statsText;

  /// 话题标签
  final List<String> tags;

  /// 平台特有字段
  final Map<String, dynamic> extra;

  const ParseMeta({
    required this.title,
    this.titleSource = '',
    this.description = '',
    this.cover = '',
    this.authorName = '',
    this.authorId = '',
    this.authorAvatar = '',
    this.durationS,
    this.publishTime,
    this.publishTimeText,
    this.stats = const {},
    this.statsText = const {},
    this.tags = const [],
    this.extra = const {},
  });

  /// 时长的友好展示（1分23秒）
  String get durationLabel {
    if (durationS == null || durationS! <= 0) return '';
    final s = durationS!.round();
    final m = s ~/ 60;
    return m > 0 ? '$m分${s % 60}秒' : '$s秒';
  }

  /// 标题是否来自降级路径（UI 应提示用户可能不完整）
  bool get titleIsApproximate =>
      titleSource == 'desc_head' || titleSource == 'template_skipped';

  /// 按标准名取统计值，优先用平台原始文本（如「450万」而非 4500000）
  String statLabel(String key) {
    final t = statsText[key];
    if (t != null && t.isNotEmpty) return t;
    final v = stats[key];
    if (v == null) return '';
    if (v >= 100000000) {
      return '${(v / 100000000).toStringAsFixed(1).replaceAll('.0', '')}亿';
    }
    if (v >= 10000) {
      return '${(v / 10000).toStringAsFixed(1).replaceAll('.0', '')}万';
    }
    return '$v';
  }

  factory ParseMeta.fromJson(Map<String, dynamic> j) {
    return ParseMeta(
      title: j['title'] as String? ?? '',
      titleSource: j['title_source'] as String? ?? '',
      description: j['description'] as String? ?? '',
      cover: j['cover'] as String? ?? '',
      authorName: j['author_name'] as String? ?? '',
      authorId: j['author_id'] as String? ?? '',
      authorAvatar: j['author_avatar'] as String? ?? '',
      durationS: (j['duration_s'] as num?)?.toDouble(),
      publishTime: j['publish_time'] as String?,
      publishTimeText: j['publish_time_text'] as String?,
      stats: (j['stats'] as Map?)?.map((k, v) =>
              MapEntry(k.toString(), (v as num?)?.toInt() ?? 0)) ??
          const {},
      statsText: (j['stats_text'] as Map?)?.map((k, v) =>
              MapEntry(k.toString(), v.toString())) ??
          const {},
      tags: (j['tags'] as List?)?.map((e) => e.toString()).toList() ??
          const [],
      // ⚠️ 服务端返回的是 Map<dynamic,dynamic>，必须显式 cast。
      //    直接 `(j['extra'] as Map?)` 会编译失败（类型不匹配）。
      extra: ((j['extra'] as Map?)?.cast<String, dynamic>()) ?? const {},
    );
  }
}

/// 解析结果
class ParseResult {
  final bool success;
  final String platform;
  final String platformName;
  final String type; // video / image
  final String method;
  final ParseMeta meta;

  final String videoUrl;
  final List<QualityOption> options;

  /// 图集
  final List<ImageItem> images;

  // ---- 能力标记（决定 UI 怎么显示）----
  final bool noWatermark;
  final bool needProxy;
  final bool truncated;
  final bool mergeRequired; // AcFun 只有 m3u8，需服务端合并
  final int anonymousMaxHeight;
  final String error;
  final String? hint;
  final String? fallbackUrl;

  const ParseResult({
    required this.success,
    required this.platform,
    this.platformName = '',
    this.type = 'video',
    this.method = '',
    this.meta = const ParseMeta(title: ''),
    this.videoUrl = '',
    this.options = const [],
    this.images = const [],
    this.noWatermark = false,
    this.needProxy = false,
    this.truncated = false,
    this.mergeRequired = false,
    this.anonymousMaxHeight = 0,
    this.error = '',
    this.hint,
    this.fallbackUrl,
  });

  bool get isVideo => type == 'video' && videoUrl.isNotEmpty;
  bool get isImage => type == 'image' && images.isNotEmpty;

  /// 当前应选中的清晰度
  ///
  /// ⚠️ 规则：优先选不超过 1080P 的最高档；
  ///    匿名上限（anonymousMaxHeight）以上的档位标注为「需登录/付费」。
  QualityOption? get recommendedOption {
    if (options.isEmpty) return null;
    if (isImage) return null;
    final sorted = [...options]..sort((a, b) {
        final ah = a.height ?? 0;
        final bh = b.height ?? 0;
        return bh.compareTo(ah);
      });
    for (final o in sorted) {
      if ((o.height ?? 0) <= 1080) return o;
    }
    return sorted.last;
  }

  /// 某档位是否超过匿名上限
  bool exceedsAnonymousLimit(QualityOption o) =>
      anonymousMaxHeight > 0 &&
      (o.height ?? 0) > anonymousMaxHeight;

  /// 解析失败时的构造
  factory ParseResult.failure(String error, {String? hint, String? fallback}) =>
      ParseResult(
        success: false,
        platform: '',
        error: error,
        hint: hint,
        fallbackUrl: fallback,
      );

  factory ParseResult.fromJson(Map<String, dynamic> j) {
    final meta = ParseMeta.fromJson(
        (j['meta'] as Map?)?.cast<String, dynamic>() ?? const {});
    return ParseResult(
      success: j['success'] as bool? ?? false,
      platform: j['platform'] as String? ?? '',
      platformName: platformDisplayName(j['platform'] as String? ?? ''),
      type: j['type'] as String? ?? 'video',
      method: j['method'] as String? ?? '',
      meta: meta,
      videoUrl: j['video_url'] as String? ?? '',
      options: (j['options'] as List?)
              ?.map((e) => QualityOption.fromJson(
                  (e as Map).cast<String, dynamic>()))
              .toList() ??
          const [],
      images: (j['images'] as List?)
              ?.map((e) =>
                  ImageItem.fromJson((e as Map).cast<String, dynamic>()))
              .toList() ??
          const [],
      noWatermark: j['no_watermark'] as bool? ?? false,
      needProxy: j['need_proxy'] as bool? ?? false,
      truncated: j['truncated'] as bool? ?? false,
      mergeRequired: j['merge_required'] as bool? ?? false,
      anonymousMaxHeight: j['anonymous_max_height'] as int? ?? 0,
      error: j['error'] as String? ?? '',
      hint: j['hint'] as String?,
      fallbackUrl: j['fallback_url'] as String?,
    );
  }
}

/// 平台中文名（UI 展示用）
String platformDisplayName(String key) {
  const map = {
    'douyin': '抖音',
    'bilibili': 'B站',
    'haokan': '好看视频',
    'sohu': '搜狐视频',
    'weibo': '微博',
    'acfun': 'AcFun',
    'xiaohongshu': '小红书',
    'kuaishou': '快手',
    'ixigua': '西瓜',
    'qqvideo': '腾讯视频',
  };
  return map[key] ?? key;
}

/// 平台标签（首页展示，按 v3 规范只列已验证的）
const supportedPlatforms = <String>[
  'douyin',
  'bilibili',
  'haokan',
  'weibo',
  'acfun',
  'xiaohongshu',
  'kuaishou',
];
