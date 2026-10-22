/// 品牌名集中定义（单一事实源）。
///
/// 为什么要这个文件
/// ────────────────────
/// 「星创映画」是项目的中文品牌名，英文名保留 CreatorBox。
/// 此前品牌名散落在小程序 4 处、Flutter 4 处、后台 3 处、平台配置 3 处、
/// 教程页 7 处 —— 改一次要动 20+ 个文件，漏一处就留下不一致的尾巴。
///
/// 现在：改这一个文件，再跑 `python tools/apply_brand.py` 即可全量同步。
///
/// ⭐ 内部代号 vs 品牌名
///   - **品牌名（星创映画）**：用户能看到的一切 —— 界面文字、窗口标题、
///     Android 桌面图标名、网页 title
///   - **内部代号（CreatorBox / creatorbox）**：包名 com.creatorbox.app、
///     接口 service 名 creatorbox-parser、类名 CreatorBoxApp、
///     目录名 D:\WorkBuddyFILE\CreatorBox、Python 模块名
///     → 这些**不改**，改了会破坏包路径、构建配置与历史对应关系

// ── 品牌名 ──────────────────────────────────────────────────────────────
/// 中文品牌名（用户可见）
const String BRAND_CN = '星创映画';

/// 英文名（保留）
const String BRAND_EN = 'CreatorBox';

// 完整标题位（各端统一用同一套措辞，避免同一产品在不同端叫法不一）
/// App 窗口标题 / Android 桌面图标名
const String TITLE_APP = BRAND_CN;

/// PC 端底部署名
const String TITLE_PC = '$BRAND_CN · 内容地址解析';

/// 运营后台
const String TITLE_ADMIN = '$BRAND_CN 运营后台';

/// 旧版只读看板
const String TITLE_DASHBOARD = '$BRAND_CN · 运维看板';

/// 服务窗口标题提示
const String TITLE_SERVICE = '$BRAND_CN 解析服务';

/// 教程页标题（[sub] 会被替换为具体子标题）
String titleTutorial(String sub) => '$BRAND_CN $sub';
