/// 违禁词自检（对齐小程序 pages/banned）。
///
/// 为什么 PC 端更需要它：小程序里只能看/复制文案，而 PC 端是创作者的
/// 真正工作场景 —— 写文案、写脚本、准备发布。用发布前自查代替事后被限流，
/// 是这个工具对PC 用户的独特价值。
///
/// 服务端规则（server/app/main.py bannedCheck）：
///   免费用户限次（基础词库），会员不限次 + 全类目；超额返回 quota_exhausted。
///   本页如实展示服务端判定，不做本地预判 —— 本地词库与服务端不一致会让
///   用户以为「过了就没事」，那是更危险的误导。
import 'package:flutter/material.dart';

import '../api/client.dart' show ApiError;
import '../state/session.dart';

class BannedPage extends StatefulWidget {
  const BannedPage({super.key, required this.session});
  final Session session;

  @override
  State<BannedPage> createState() => _BannedPageState();
}

class _BannedPageState extends State<BannedPage> {
  final _ctrl = TextEditingController();
  bool _busy = false;
  bool _checked = false;

  // 服务端返回（结构已实跑核对，勿凭想象改）：
  //   {ok, total, risk_level, marks:[{start,end,word,category}],
  //    groups:[{category,name,risk,count,words:[{word,count,suggest}]}],
  //    locked:[类目名], quota:{...}}
  // ⚠️ risk_level 空文本时服务端返回 'clean'（不是空串）
  String _riskText = '';
  int _total = 0;
  List<Map<String, dynamic>> _groups = const [];
  List<String> _locked = const [];
  String? _error;
  int _freeLeft = -1;      // -1 = 服务端未下发

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  static String _s(dynamic v) => v?.toString() ?? '';

  Future<void> _check() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty) {
      setState(() => _error = '请输入要检查的文案');
      return;
    }
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final openid = await widget.session.api.authOpenid();
      final r = await widget.session.api.bannedCheck(openid, text);
      if (!mounted) return;
      setState(() {
        _busy = false;
        _checked = true;
        _total = (r['total'] as num?)?.toInt() ?? 0;
        final risk = _s(r['risk_level']);
        _riskText = switch (risk) {
          'clean' => '无风险',
          'high' => '高风险',
          'medium' => '中风险',
          'low' => '低风险',
          '' => '未检出',
          _ => risk,
        };
        final g = r['groups'];
        _groups = g is List
            ? g.whereType<Map>().toList()
            : const [];
        _locked = (r['locked'] as List?)?.map(_s).toList() ?? const [];
        final q = r['quota'];
        if (q is Map) {
          final left = q['left'];
          _freeLeft = left is int ? left : int.tryParse('$left') ?? -1;
        }
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.detail;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = '检查失败：$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final risky = _total > 0;

    return Scaffold(
      appBar: AppBar(title: const Text('违禁词自检')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
              '发布前自查，避免内容被平台限流或下架。\n'
              '检查的是文案中的违禁表述，不涉及版权判断。',
              style: theme.textTheme.bodySmall),
          const SizedBox(height: 12),
          TextField(
            controller: _ctrl,
            maxLines: 8,
            minLines: 4,
            decoration: const InputDecoration(
              hintText: '粘贴要发布的文案或口播稿…',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _busy ? null : _check,
                  icon: _busy
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.fact_check_outlined),
                  label: Text(_busy ? '检查中' : '开始检查'),
                ),
              ),
              const SizedBox(width: 10),
              OutlinedButton(
                onPressed: () {
                  _ctrl.clear();
                  setState(() {
                    _checked = false;
                    _total = 0;
                    _groups = const [];
                    _error = null;
                  });
                },
                child: const Text('清空'),
              ),
            ],
          ),
          if (_freeLeft >= 0)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('今日剩余次数：$_freeLeft（会员不限次）',
                  style: theme.textTheme.bodySmall),
            ),

          if (_error != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.shade200),
              ),
              child: Text(_error!, style: theme.textTheme.bodySmall),
            ),
          ],

          if (_checked) ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          risky ? Icons.warning_amber_rounded : Icons.check_circle,
                          color: risky ? Colors.orange.shade700 : Colors.green,
                        ),
                        const SizedBox(width: 10),
                        Text(
                          _total == 0 ? '未检出问题表述' : '检出 $_total 处',
                          style: theme.textTheme.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const Spacer(),
                        Text('风险：$_riskText',
                            style: theme.textTheme.bodySmall),
                      ],
                    ),
                    if (_groups.isNotEmpty) ...[
                      const Divider(height: 24),
                      ..._groups.map((g) {
                        final name = _s(g['name']).isEmpty
                            ? _s(g['category'])
                            : _s(g['name']);
                        // ⚠️ words 是 [{word,count,suggest}] 数组（已实跑核对），
                        // 不是 Map —— 按 Map 读会直接崩。
                        final words = (g['words'] as List?) ?? const [];
                        if (words.isEmpty) return const SizedBox.shrink();
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(name,
                                      style: theme.textTheme.labelMedium
                                          ?.copyWith(
                                              fontWeight: FontWeight.w700)),
                                  const SizedBox(width: 8),
                                  Text(
                                      '${g['count'] ?? words.length} 处',
                                      style: theme.textTheme.bodySmall),
                                ],
                              ),
                              const SizedBox(height: 6),
                              ...words.whereType<Map>().map((w) {
                                final word = _s(w['word']);
                                final cnt =
                                    (w['count'] as num?)?.toInt() ?? 1;
                                final sug = _s(w['suggest']);
                                return Padding(
                                  padding:
                                      const EdgeInsets.only(bottom: 5),
                                  child: Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Container(
                                        padding: const EdgeInsets.symmetric(
                                            horizontal: 7, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: Colors.orange.shade50,
                                          borderRadius:
                                              BorderRadius.circular(4),
                                          border: Border.all(
                                              color:
                                                  Colors.orange.shade200),
                                        ),
                                        child: Text(
                                          cnt > 1 ? '$word×$cnt' : word,
                                          style: theme.textTheme.bodySmall
                                              ?.copyWith(
                                                  color: Colors
                                                      .orange.shade900),
                                        ),
                                      ),
                                      // 服务端内置了改写建议，这是本页最有用的输出
                                      if (sug.isNotEmpty) ...[
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: Text('→ $sug',
                                              style:
                                                  theme.textTheme.bodySmall
                                                      ?.copyWith(
                                                          color: Colors.green
                                                              .shade800)),
                                        ),
                                      ],
                                    ],
                                  ),
                                );
                              }),
                            ],
                          ),
                        );
                      }),
                      if (_locked.isNotEmpty) ...[
                        const Divider(height: 20),
                        Text(
                          '会员可解锁全类目检查，本次未检查：${_locked.join('、')}',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ],
                    const SizedBox(height: 8),
                    Text(
                      risky
                          ? '建议改写上述表述后重新检查。本工具只做表述层面的自查，'
                              '不保证通过平台审核。'
                          : '本次检查未发现常见违禁表述。内容合规仍需自行判断。',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}