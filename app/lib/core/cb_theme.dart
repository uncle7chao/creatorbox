import 'package:flutter/material.dart';

import 'cb_colors.dart';

/// CreatorBox 主题（橙金 v2）
///
/// 设计约束来自 docs/小程序UI设计规范.md：
///   - 底部免责灰字 11px（规范 3.13 硬要求，但不显眼 —— 显眼会伤转化）
///   - 主 CTA 是唯一视觉焦点
class CBTheme {
  CBTheme._();

  static ThemeData light() {
    final base = ThemeData.light(useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: CBColors.bgPage,
      colorScheme: base.colorScheme.copyWith(
        primary: CBColors.brand500,
        // ⚠️ onPrimary 必须是深色 —— 规则 1
        onPrimary: CBColors.ink900,
        secondary: CBColors.brand700,
        surface: CBColors.bgCard,
        onSurface: CBColors.ink900,
        error: CBColors.danger500,
      ),

      // ---- 主 CTA：唯一视觉焦点 ----
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: CBColors.brand500,
          foregroundColor: CBColors.ink900, // 规则 1：深色字
          disabledBackgroundColor: CBColors.ink300,
          disabledForegroundColor: CBColors.bgCard,
          minimumSize: const Size.fromHeight(48), // 占满 + 足够大的点击区
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          elevation: 0,
        ),
      ),

      // ---- 次要按钮：虚线弱化（结果页的变现触点用）----
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: CBColors.brand700,
          minimumSize: const Size.fromHeight(44),
          side: const BorderSide(color: CBColors.brand300, width: 1.2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: CBColors.info500,
        ),
      ),

      // ---- 输入区 ----
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: CBColors.bgSunken,
        hintStyle: const TextStyle(color: CBColors.ink500, fontSize: 14),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: CBColors.brand500, width: 1.5),
        ),
      ),

      // ---- 额度三指标（常驻可见，成本闸门）----
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w500,
          color: CBColors.ink900,
        ),
        titleLarge: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w500,
          color: CBColors.ink900,
        ),
        titleMedium: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w500,
          color: CBColors.ink900,
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          color: CBColors.ink700,
          height: 1.5,
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          color: CBColors.ink500,
        ),
        // 免责灰字 11px —— 规范 3.13 硬要求
        disclaimer: TextStyle(
          fontSize: 11,
          color: CBColors.ink500,
          height: 1.6,
        ),
      ),

      dividerTheme: const DividerThemeData(
        color: CBColors.bgSunken,
        thickness: 1,
        space: 1,
      ),
    );
  }

  /// 深色区渐变上的文字样式（Hero 区域专用）
  static const heroTitle = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w500,
    color: Colors.white,
  );

  static const heroSubtitle = TextStyle(
    fontSize: 13,
    color: CBColors.brand300,
  );
}

/// 统一的圆角与间距（避免各处随手写）
class CBRadius {
  CBRadius._();
  static const card = BorderRadius.all(Radius.circular(12));
  static const control = BorderRadius.all(Radius.circular(10));
  static const pill = BorderRadius.all(Radius.circular(99));
}

class CBSpacing {
  CBSpacing._();
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
}
