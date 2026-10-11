import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/cb_colors.dart';
import '../core/cb_theme.dart';
import '../models/parse_result.dart';
import '../services/api_client.dart';
import '../widgets/parse_result_view.dart';
import 'library_screen.dart';

/// 解析首页 —— 转化率最高的一屏
///
/// ⭐ 严格按 docs/小程序UI设计规范.md 的 v3 约束实现：
/// | v3 结论 | 本页体现|
/// |---|---|
/// | 定位是"韧性"不是"功能多" | **不列功能清单**，只强调「全部已验证」 |
/// | 解析不限次 | 额度区第一个指标是「不限」 |
/// | 免费能拿到干净原片 | 只说「无水印」，不说「去水印质量」 |
/// | 平台改版是主要风险 | 「全部已验证」+ 服务健康徽章 |
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _inputCtrl = TextEditingController();
  final _inputFocus = FocusNode();

  bool _loading = false;
  String? _error;
  String? _hint;
  ServiceHealth? _health;
  Timer? _healthTimer;

  @override
  void initState() {
    super.initState();
    _checkHealth();
    // 每 30 秒探一次服务状态 —— 「韧性」定位要求把风险显性化
    _healthTimer = Timer.periodic(
        const Duration(seconds: 30), (_) => _checkHealth());
  }

  @override
  void dispose() {
    _healthTimer?.cancel();
    _inputCtrl.dispose();
    _inputFocus.dispose();
    super.dispose();
  }

  Future<void> _checkHealth() async {
    final h = await context.read<ApiClient>().health();
    if (mounted) setState(() => _health = h);
  }

  Future<void> _paste() async {
    //读剪贴板：优先用系统剪贴板，无需额外权限
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim();
    if (text == null || text.isEmpty) {
      _toast('剪贴板是空的');
      return;
    }
    _inputCtrl.text = text;
    _toast('已粘贴，点击解析');
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        backgroundColor: CBColors.ink900,
      ));
  }

  Future<void> _parse() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty) {
      setState(() => _error = '请粘贴视频链接');
      return;
    }
    _inputFocus.unfocus();
    setState(() {
      _loading = true;
      _error = null;
      _hint = null;
    });

    final r = await context.read<ApiClient>().parse(text);

    if (!mounted) return;
    setState(() => _loading = false);

    if (!r.success) {
      setState(() {
        _error = r.error.isEmpty ? '解析失败' : r.error;
        _hint = r.hint;
      });
      return;
    }

    // 成功 → 推结果页
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ParseResultView(result: r, inputText: text),
      ),
    );
    // 返回后刷新健康状态（结果页可能触发了下载）
    _checkHealth();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CBColors.bgPage,
      body: SafeArea(
        bottom: false,
        child: CustomScrollView(
          slivers: [
            // ---- 深色渐变区 + 悬浮白卡 ----
            SliverToBoxAdapter(child: _hero()),

            // ---- 额度三指标（常驻可见）----
            SliverToBoxAdapter(child: _quotaRow()),

            // ---- 平台标签 ----
            SliverToBoxAdapter(child: _platformTags()),

            // ---- 素材库入口 ----
            SliverToBoxAdapter(child: _libraryEntry()),

            // ---- 免责声明（规范 3.13 硬要求，11px 不显眼）----
            SliverToBoxAdapter(child: _disclaimer()),

            const SliverToBoxAdapter(child: SizedBox(height: 28)),
          ],
        ),
      ),
    );
  }

  // ══════════════════════════════════════════════════
  // 深色区（渐变）+ 悬浮白卡
  // ══════════════════════════════════════════════════
  Widget _hero() {
    return Container(
      decoration: const BoxDecoration(gradient: CBColors.heroGradient),
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 66),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ---- 顶栏：标题 + 会员入口 ----
          Row(
            children: [
              const Text('素材解析', style: CBTheme.heroTitle),
              const Spacer(),
              // 会员入口（9.9 开通）
              GestureDetector(
                onTap: () => _toast('会员功能开发中'),
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    borderRadius: CBRadius.pill,
                    border: Border.all(color: CBColors.brand300, width: 1),
                  ),
                  child: const Text(
                    '9.9 开通会员',
                    style: TextStyle(
                        fontSize: 12, color: CBColors.brand300),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          // ---- 主文案：转化核心 ----
          const Text(
            '源头就干净',
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.w500,
              color: Colors.white,
              height: 1.25,
            ),
          ),
          const SizedBox(height: 6),
          // ---- 副文案：只说「无水印」，不说「去水印质量」----
          Text(
            '抖音 · B站 · 小红书 · ${supportedPlatforms.length} 个平台',
            style: CBTheme.heroSubtitle,
          ),
        ],
      ),
    );
  }

  // 悬浮白卡（负margin 上提，让「粘贴链接」成为唯一视觉焦点）
  Widget _inputCard() {
    return Transform.translate(
      offset: const Offset(0, -50),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16),
        padding: const EdgeInsets.all(14),
        decoration: const BoxDecoration(
          color: CBColors.bgCard,
          borderRadius: CBRadius.card,
          boxShadow: [
            BoxShadow(
              color: Color(0x14000000),
              blurRadius: 16,
              offset: Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _inputCtrl,
              focusNode: _inputFocus,
              maxLines: 3,
              minLines: 3,
              style: const TextStyle(fontSize: 14, height: 1.5),
              decoration: InputDecoration(
                hintText: '粘贴视频或图集链接\n支持 App 复制文案',
                errorText: _error,
                errorStyle: const TextStyle(fontSize: 12),
                suffixIcon: _loading
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.content_paste, size: 20),
                        color: CBColors.ink500,
                        onPressed: _paste,
                        tooltip: '从剪贴板粘贴',
                      ),
              ),
            ),
            if (_hint != null) ...[
              const SizedBox(height: 8),
              Text(
                _hint!,
                style: const TextStyle(
                    fontSize: 12, color: CBColors.danger500, height: 1.5),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: _loading ? null : _parse,
                    child: _loading
                        ? const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              SizedBox(
                                width: 15,
                                height: 15,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: CBColors.ink900,
                                ),
                              ),
                              SizedBox(width: 8),
                              Text('解析中…'),
                            ],
                          )
                        : const Text('开始解析'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ══════════════════════════════════════════════════
  // 额度三指标（成本闸门，必须常驻可见）
  // ══════════════════════════════════════════════════
  Widget _quotaRow() {
    return Transform.translate(
      offset: const Offset(0, -32),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: CBColors.bgCard,
            borderRadius: CBRadius.card,
            border: Border.all(color: CBColors.bgSunken),
          ),
          child: const Row(
            children: [
              // ⭐ 「不限」字号最大 —— 免费策略的差异点（竞品通常限次）
              _QuotaItem(value: '不限', label: '解析次数', highlight: true),
              _QuotaDivider(),
              _QuotaItem(value: '2/2', label: '今日保存'),
              _QuotaDivider(),
              _QuotaItem(value: '720P', label: '免费画质'),
            ],
          ),
        ),
      ),
    );
  }

  // ══════════════════════════════════════════════════
  // 平台标签 + 「全部已验证」徽章
  // ══════════════════════════════════════════════════
  Widget _platformTags() {
    final offline = _health == null;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final p in supportedPlatforms)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 9, vertical: 4),
                    decoration: BoxDecoration(
                      color: CBColors.bgSunken,
                      borderRadius: CBRadius.pill,
                    ),
                    child: Text(
                      platformDisplayName(p),
                      style: const TextStyle(
                          fontSize: 12, color: CBColors.ink700),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          // ⭐ 把「改版预警」转成信任背书（v3 定位要求）
          _verifiedBadge(offline),
        ],
      ),
    );
  }

  Widget _verifiedBadge(bool offline) {
    final (color, text) = offline
        ? (CBColors.ink500, '服务未连')
        : (CBColors.success500, '全部已验证');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: offline ? CBColors.bgSunken : CBColors.success100,
        borderRadius: CBRadius.pill,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 5),
          Text(text,
              style: TextStyle(fontSize: 11, color: color)),
        ],
      ),
    );
  }

  // ══════════════════════════════════════════════════
  // 素材库入口
  // ══════════════════════════════════════════════════
  Widget _libraryEntry() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
      child: Material(
        color: CBColors.bgCard,
        borderRadius: CBRadius.card,
        child: InkWell(
          borderRadius: CBRadius.card,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const LibraryScreen()),
          ),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
            decoration: BoxDecoration(
              borderRadius: CBRadius.card,
              border: Border.all(color: CBColors.bgSunken),
            ),
            child: const Row(
              children: [
                Icon(Icons.folder_open_outlined,
                    size: 20, color: CBColors.ink500),
                SizedBox(width: 10),
                Text('素材库',
                    style: TextStyle(
                        fontSize: 14, color: CBColors.ink900)),
                Spacer(),
                Text('解析记录都在这',
                    style: TextStyle(fontSize: 12, color: CBColors.ink500)),
                SizedBox(width: 4),
                Icon(Icons.chevron_right,
                    size: 18, color: CBColors.ink300),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ══════════════════════════════════════════════════
  // 免责声明（规范 3.13：须披露投诉渠道，11px 不显眼）
  // ══════════════════════════════════════════════════
  Widget _disclaimer() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
      child: Text(
        '本工具仅供个人学习与二次创作使用，请勿用于侵权或商业盗用。\n'
        '素材版权归原作者所有，争议与投诉请联系：creatorbox@example.com',
        style: Theme.of(context).textTheme.disclaimer,
      ),
    );
  }
}

/// 额度指标项
class _QuotaItem extends StatelessWidget {
  final String value;
  final String label;
  final bool highlight;

  const _QuotaItem({
    required this.value,
    required this.label,
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: highlight ? 22 : 18,
              fontWeight: FontWeight.w500,
              color: highlight ? CBColors.brand500 : CBColors.ink900,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(fontSize: 11, color: CBColors.ink500),
          ),
        ],
      ),
    );
  }
}

class _QuotaDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) =>
      Container(width: 1, height: 28, color: CBColors.bgSunken);
}
