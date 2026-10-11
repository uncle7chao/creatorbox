import 'package:flutter/material.dart';

import '../core/cb_colors.dart';
import '../core/cb_theme.dart';
import '../models/parse_result.dart';
import '../screens/library_screen.dart';
import '../services/save_helper.dart';

/// 解析结果页
///
/// ⭐ 三个变现触点（规范要求）：清晰度选择 / 1080P 引导 / 保存
/// ⚠️ 规范硬约束：**保存按钮放在广告位上方** —— 先满足需求，再要求看广告。
class ParseResultView extends StatefulWidget {
  final ParseResult result;
  final String inputText;

  const ParseResultView({
    super.key,
    required this.result,
    required this.inputText,
  });

  @override
  State<ParseResultView> createState() => _ParseResultViewState();
}

class _ParseResultViewState extends State<ParseResultView> {
  late QualityOption? _selected;
  int _savedCount = 0;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _selected = widget.result.recommendedOption;
  }

  Future<void> _save() async {
    final r = widget.result;
    setState(() => _busy = true);
    try {
      // ---- 存入素材库（只存展示字段，播放地址会过期不能存）----
      await LibraryScreen.addItem(LibraryItem(
        title: r.meta.title,
        platform: r.platform,
        cover: r.meta.cover.isEmpty
            ? (r.images.isEmpty ? '' : r.images.first.url)
            : r.meta.cover,
        sourceUrl: widget.inputText,
        saved: true,
      ));

      // ---- 下载后调起分享 ----
      if (r.isVideo) {
        final url = _selected?.url ?? r.videoUrl;
        if (url.isEmpty) {
          _toast('没有可保存的地址');
          return;
        }
        if (r.mergeRequired) {
          _toast('该平台只有 m3u8 分段，需服务端合并，下载可能失败');
        }
        final ok = await SaveHelper.downloadAndShare(
          context: context,
          url: url,
          fallbackTitle: r.meta.title,
        );
        if (ok) {
          setState(() => _savedCount++);
          _toast('已调起保存');
        }
      } else if (r.isImage) {
        // 图集：一次分享多张（分享面板可分别存）
        final ok = await SaveHelper.downloadAndShare(
          context: context,
          url: r.images.first.url,
          fallbackTitle: r.meta.title,
          extraUrls: r.images.skip(1).map((e) => e.url).toList(),
        );
        if (ok) {
          setState(() => _savedCount++);
          _toast('已调起保存（${r.images.length} 张）');
        }
      } else {
        _toast('没有可保存的内容');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg),
        behavior: SnackBarBehavior.floating,
        backgroundColor: CBColors.ink900,
        duration: const Duration(seconds: 2),
      ));
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.result;
    return Scaffold(
      backgroundColor: CBColors.bgPage,
      appBar: AppBar(
        title: Text(platformDisplayName(r.platform)),
        backgroundColor: CBColors.bgCard,
        surfaceTintColor: Colors.transparent,
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(child: SingleChildScrollView(child: _content(r))),
            // ---- 保存区固定底部（先满足需求）----
            _saveBar(r),
          ],
        ),
      ),
    );
  }

  Widget _content(ParseResult r) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (r.isVideo) _videoSection(r) else if (r.isImage) _imageSection(r),
        _metaSection(r),
        if (r.options.length > 1 && r.isVideo) _qualitySection(r),
        if (r.truncated) _warnBanner('该视频超过 30 秒，平台只提供试看片段'),
        if (r.mergeRequired)
          _warnBanner('该平台只提供 m3u8 分段，需服务端合并后才能保存'),
        const SizedBox(height: 20),
      ],
    );
  }

  // ---- 视频预览 ----
  Widget _videoSection(ParseResult r) {
    final url = _selected?.url ?? r.videoUrl;
    return Container(
      margin: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: CBRadius.card,
      ),
      clipBehavior: Clip.antiAlias,
      child: AspectRatio(
        aspectRatio: 16 / 9,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // 封面（点击播放更稳，避免网络视频源在部分机型播不了）
            if (r.meta.cover.isNotEmpty)
              Image.network(
                r.meta.cover,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const Center(
                  child: Icon(Icons.play_circle_outline,
                      color: Colors.white38, size: 48),
                ),
              )
            else
              const Center(
                child: Icon(Icons.play_circle_outline,
                    color: Colors.white38, size: 48),
              ),
            // 绿底「无水印」徽章 —— 兑现承诺的信任点
            if (r.noWatermark)
              Positioned(
                left: 10,
                top: 10,
                child: _badge('无水印', CBColors.success500, Colors.white),
              ),
            Positioned(
              right: 10,
              bottom: 10,
              child: _badge(
                r.meta.durationLabel,
                Colors.black54,
                Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ---- 图集网格 ----
  Widget _imageSection(ParseResult r) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Row(
            children: [
              const Text('原图',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                      color: CBColors.ink900)),
              const SizedBox(width: 8),
              Text('${r.images.length} 张 · 无水印',
                  style: const TextStyle(
                      fontSize: 12, color: CBColors.ink500)),
              const Spacer(),
              if (r.noWatermark)
                _badge('无水印', CBColors.success500, Colors.white),
            ],
          ),
        ),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 3,
            crossAxisSpacing: 6,
            mainAxisSpacing: 6,
          ),
          itemCount: r.images.length,
          itemBuilder: (_, i) => ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Image.network(
              r.images[i].url,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                color: CBColors.bgSunken,
                child: const Icon(Icons.broken_image_outlined,
                    size: 18, color: CBColors.ink300),
              ),
            ),
          ),
        ),
      ],
    );
  }

  // ---- 元信息 ----
  Widget _metaSection(ParseResult r) {
    final m = r.meta;
    // 互动数据：按平台可得字段动态显示
    final stats = <String>[];
    for (final (key, label) in const [
      ('view', '播放'),
      ('like', '点赞'),
      ('comment', '评论'),
      ('collect', '收藏'),
      ('share', '分享'),
    ]) {
      final v = m.statLabel(key);
      if (v.isNotEmpty) stats.add('$label $v');
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: CBColors.bgCard,
        borderRadius: CBRadius.card,
        border: Border.all(color: CBColors.bgSunken),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 标题（长文省略）
          Text(
            m.title.isEmpty ? '（无标题）' : m.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w500,
              height: 1.4,
            ),
          ),
          // ⭐ 标题来自降级路径时如实告知，不假装准确
          if (m.titleIsApproximate && m.title.isNotEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text(
                '标题由文案推断，可能不完整',
                style: TextStyle(fontSize: 11, color: CBColors.warn500),
              ),
            ),
          if (m.authorName.isNotEmpty) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                if (m.authorAvatar.isNotEmpty)
                  ClipOval(
                    child: Image.network(
                      m.authorAvatar,
                      width: 22,
                      height: 22,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const CircleAvatar(
                        radius: 11,
                        backgroundColor: CBColors.bgSunken,
                      ),
                    ),
                  ),
                if (m.authorAvatar.isNotEmpty) const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    m.authorId.isNotEmpty
                        ? '${m.authorName} · @${m.authorId}'
                        : m.authorName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, color: CBColors.ink700),
                  ),
                ),
              ],
            ),
          ],
          if (stats.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              stats.join('·  '),
              style: const TextStyle(fontSize: 12, color: CBColors.ink500),
            ),
          ],
          if (m.publishTime != null && m.publishTime!.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              m.publishTime!,
              style: const TextStyle(fontSize: 12, color: CBColors.ink500),
            ),
          ],
          if (m.tags.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final t in m.tags.take(6))
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: CBColors.bgSunken,
                      borderRadius: CBRadius.pill,
                    ),
                    child: Text('#$t',
                        style: const TextStyle(
                            fontSize: 11, color: CBColors.ink700)),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  // ---- 清晰度选择（变现触点）----
  Widget _qualitySection(ParseResult r) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 14, 16, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: CBColors.bgCard,
        borderRadius: CBRadius.card,
        border: Border.all(color: CBColors.bgSunken),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('清晰度',
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: CBColors.ink900)),
              const Spacer(),
              // 诚实告知匿名上限
              if (r.anonymousMaxHeight > 0)
                Text('免登录上限 ${r.anonymousMaxHeight}P',
                    style: const TextStyle(
                        fontSize: 11, color: CBColors.ink500)),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final o in r.options)
                _qualityChip(o, r.exceedsAnonymousLimit(o)),
            ],
          ),
          if (r.options.any(r.exceedsAnonymousLimit)) ...[
            const SizedBox(height: 10),
            // 虚线弱化按钮（可感可选）
            OutlinedButton.icon(
              onPressed: () => _toast('看广告解锁 1080P（功能开发中）'),
              icon: const Icon(Icons.play_circle_outline, size: 16),
              label: const Text('看广告解锁 1080P'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(40),
                foregroundColor: CBColors.warn500,
                side: const BorderSide(color: CBColors.warn500, width: 1.2),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _qualityChip(QualityOption o, bool locked) {
    final active = _selected?.url == o.url;
    return GestureDetector(
      onTap: () => setState(() => _selected = o),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: active ? CBColors.brand500 : Colors.transparent,
          borderRadius: CBRadius.control,
          border: Border.all(
            color: active
                ? CBColors.brand500
                : (locked ? CBColors.warn500 : CBColors.ink300),
            width: 1.2,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 超出免费额度用小锁标记（图形而非 emoji）
            if (locked) ...[
              Icon(Icons.lock_outline,
                  size: 12,
                  color: active ? CBColors.ink900 : CBColors.warn500),
              const SizedBox(width: 4),
            ],
            Text(
              o.label,
              style: TextStyle(
                fontSize: 13,
                color: active
                    ? CBColors.ink900
                    : (locked ? CBColors.warn500 : CBColors.ink700),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _warnBanner(String text) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 14, 16, 0),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: CBColors.warn100,
        borderRadius: CBRadius.control,
        border: const Border(
          left: BorderSide(color: CBColors.warn500, width: 3),
        ),
      ),
      child: Text(
        text,
        style: const TextStyle(fontSize: 12, color: CBColors.warn500),
      ),
    );
  }

  Widget _badge(String text, Color bg, Color fg) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: CBRadius.pill,
      ),
      child: Text(text,
          style: TextStyle(fontSize: 11, color: fg)),
    );
  }

  // ---- 底部保存区（规范：保存在广告位上方）----
  Widget _saveBar(ParseResult r) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      decoration: const BoxDecoration(
        color: CBColors.bgCard,
        border: Border(top: BorderSide(color: CBColors.bgSunken)),
      ),
      child: SafeArea(
        top: false,
        child: ElevatedButton(
          onPressed: _busy ? null : _save,
          child: _busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: CBColors.ink900),
                )
              : Text(
                  r.isImage
                      ? '保存图集（${r.images.length} 张）'
                      : '保存视频${_selected == null ? '' : ' · ${_selected!.label}'}',
                  style: const TextStyle(fontSize: 15),
                ),
        ),
      ),
    );
  }
}
