import 'package:flutter/material.dart';

/// CreatorBox 橙金色板
///
/// 依据：docs/配色规范-橙金v2.md（2026-10-06 用户拍板）
///原深绿方案（#173404）保留在 git 历史里，本文件是生效版本。
///
/// ⚠️ 三条不可违背的规则（都在配色规范里踩过）：
///   1. 主 CTA 文字必须 **深色 #1A1614**（8.1:1），白字只有 2.6:1 不达 AA
///   2. 成功/可信语义色**不跟主色走暖** —— 无水印徽章保持冷绿 #1B8A5A
///   3. 深色区用**深棕→橙渐变**，不能用纯橙（纯橙大面积刺眼且文字对比度不足）
class CBColors {
  CBColors._();

  // ---- 主色（品牌 / CTA）----
  static const brand900 = Color(0xFF3D2000);
  static const brand800 = Color(0xFF5C3200);
  static const brand700 = Color(0xFF8A4B00);
  static const brand600 = Color(0xFFB86300);
  static const brand500 = Color(0xFFE8890C); // ⭐ 主 CTA
  static const brand400 = Color(0xFFFFA733);
  static const brand300 = Color(0xFFFFC46B);
  static const brand100 = Color(0xFFFFF0D9);

  // ---- 语义色（冷绿/暖橙/红，各自守语义）----
  /// 无水印徽章 —— 冷绿，**不跟主色走暖**
  /// 理由：暖色=「要花钱」，冷绿=「已达成」；且与主 CTA 撞色会失去区分度
  static const success500 = Color(0xFF1B8A5A);
  static const success100 = Color(0xFFE4F5EC);

  static const warn500 = Color(0xFFC77700);
  static const warn100 = Color(0xFFFFF4E0);

  static const danger500 = Color(0xFFC0392B);
  static const info500 = Color(0xFF2A6FB0);

  // ---- 中性色（微暖，与橙金同调）----
  static const ink900 = Color(0xFF1A1614);
  static const ink700 = Color(0xFF4A423C);
  static const ink500 = Color(0xFF7D736B);
  static const ink300 = Color(0xFFB8AEA6);
  static const bgPage = Color(0xFFFAF7F4); // 微暖白，比纯白柔和
  static const bgCard = Color(0xFFFFFFFF);
  static const bgSunken = Color(0xFFF3EEE9);

  // ---- 深色区渐变（规则 3）----
  static const heroGradient = LinearGradient(
    colors: [brand900, brand700],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// 框选水印的标记色 —— **必须高对比红，不能用主色**
  /// 理由：用户要精确框水印位置，暖橙会与图片内容混在一起看不清
  static const markWatermark = Color(0xFFFF3B30);
  static const markWatermarkFill = Color(0x33FF3B30);
}
