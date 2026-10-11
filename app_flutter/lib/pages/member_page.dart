/// 会员中心 + 积分（对齐小程序 member/points 两页的核心能力）。
///
/// 为什么合到一页：App/PC 端用户数远少于小程序，拆两页会让「我的」变得稀疏；
/// 而「卡密兑换 → 积分签到 → 积分换会员」本质是一条留存链路，放一起更顺。
///
/// 关键约束（来自服务端实现，不是猜的）：
/// · 积分 100 = 会员 1 天（POINTS_REDEEM_COST）
/// · 每日签到 +10，连签 7 天额外 +20（POINTS_PER_SIGN / POINTS_STREAK_BONUS）
/// · 签到幂等：当天重复签不会重复加分
import 'package:flutter/material.dart';

import '../api/client.dart' show ApiError;
import '../state/session.dart';

class MemberPage extends StatefulWidget {
  const MemberPage({super.key, required this.session});
  final Session session;

  @override
  State<MemberPage> createState() => _MemberPageState();
}

class _MemberPageState extends State<MemberPage> {
  final _codeCtrl = TextEditingController();

  bool _loading = true;
  String? _error;
  String _openid = '';
  int _balance = 0;
  int _streak = 0;
  int _redeemCost = 100;
  List<String> _days = const [];
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _codeCtrl.dispose();
    super.dispose();
  }

  /// 服务端返回的 day 是 'YYYY-MM-DD'，只取日号做日历点。
  static String _dayNum(String d) => d.length >= 10 ? d.substring(8, 10) : d;

  Future<void> _load() async {
    try {
      final openid = await widget.session.api.authOpenid();
      final p = await widget.session.api.points(openid);
      if (!mounted) return;
      setState(() {
        _openid = openid;
        _balance = _asInt(p['balance']);
        _streak = _asInt(p['streak']);
        _redeemCost = _asInt(p['redeem_cost'], fallback: 100);
        _days = (p['days'] as List?)?.map((e) => '$e').toList() ?? const [];
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  static int _asInt(dynamic v, {int fallback = 0}) {
    if (v is int) return v;
    return int.tryParse(v?.toString() ?? '') ?? fallback;
  }

  Future<void> _run(Future<void> Function() action, String okTip) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(okTip)));
      await _load();          // 操作后必须刷新，否则余额显示会骗人
    } on ApiError catch (e) {
      if (!mounted) return;
      // 400 是业务语义（积分不足/码无效），要如实告知而不是笼统报错
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
      if (e.statusCode >= 400) await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('操作失败：$e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _sign() => _run(() async {
        final r = await widget.session.api.pointsSign(_openid);
        // 幂等：当天已签过时服务端会标记，这里按实际返回提示
        final already = r['already_signed'] == true || r['ok'] == false;
        if (already) throw ApiError(400, '今天已签到过，明天再来');
      }, '签到成功');

  Future<void> _redeemPoints() => _run(() async {
        final r = await widget.session.api.pointsRedeem(_openid);
        final days = _asInt(r['days']);
        if (r['ok'] != true) {
          throw ApiError(400, r['message']?.toString() ?? '兑换失败');
        }
        if (days > 0) {
          throw ApiError(400, '已兑换 $days 天会员');   // 借异常通道提示成功信息
        }
      }, '兑换成功');

  Future<void> _redeemCode() {
    final code = _codeCtrl.text.trim();
    if (code.isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('请输入卡密')));
      return;
    }
    return _run(() async {
      final r = await widget.session.api.redeemCode(_openid, code);
      if (r['ok'] != true) {
        throw ApiError(400, r['message']?.toString() ?? '卡密无效');
      }
      _codeCtrl.clear();
      // 兑换会改会员态，通知外层刷新账号信息
      await widget.session.refresh();
    }, '兑换成功，会员已开通');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isMember = widget.session.isMember;
    final signedToday = _days.isNotEmpty;

    return Scaffold(
      appBar: AppBar(title: const Text('会员与积分')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_error != null)
                  Container(
                    padding: const EdgeInsets.all(12),
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: Colors.red.shade50,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.red.shade200),
                    ),
                    child: Text('加载失败：$_error',
                        style: theme.textTheme.bodySmall),
                  ),

                // ── 会员状态 ──
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              isMember
                                  ? Icons.workspace_premium
                                  : Icons.person_outline,
                              color: isMember ? Colors.amber.shade700 : null,
                            ),
                            const SizedBox(width: 10),
                            Text(isMember ? '会员' : '未开通会员',
                                style: theme.textTheme.titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          isMember
                              ? '已享受会员权益：批量 10 条 / 高清档位 / 不限次'
                              : '开通会员：批量解析 10 条、更高清晰度、积分翻倍',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // ── 积分 ──
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('积分',
                                style: theme.textTheme.titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                            Text('$_balance',
                                style: theme.textTheme.headlineSmall
                                    ?.copyWith(
                                        fontWeight: FontWeight.w800,
                                        color: Colors.amber.shade800)),
                          ],
                        ),
                        Text('连签 $_streak 天 · 签到 +10，连满 7 天额外 +20',
                            style: theme.textTheme.bodySmall),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: _busy ? null : _sign,
                                icon: const Icon(Icons.calendar_today,
                                    size: 18),
                                label: Text(signedToday ? '今日已签' : '签到'),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: FilledButton.icon(
                                onPressed:
                                    _busy || _balance < _redeemCost ? null : () {
                                  // 余额够才点得动，不够时按钮禁用并给出说明
                                  final days = _balance ~/ _redeemCost;
                                  showDialog<void>(
                                    context: context,
                                    builder: (ctx) => AlertDialog(
                                      title: const Text('兑换会员'),
                                      content: Text(
                                          '将用 $_redeemCost 积分兑换 1 天会员'
                                          '${days > 1 ? '，本次最多兑换 $days 天' : ''}？'),
                                      actions: [
                                        TextButton(
                                          onPressed: () => Navigator.pop(ctx),
                                          child: const Text('取消'),
                                        ),
                                        FilledButton(
                                          onPressed: () {
                                            Navigator.pop(ctx);
                                            _redeemPoints();
                                          },
                                          child: const Text('确认兑换'),
                                        ),
                                      ],
                                    ),
                                  );
                                },
                                icon: const Icon(Icons.card_giftcard,
                                    size: 18),
                                label: const Text('换会员'),
                              ),
                            ),
                          ],
                        ),
                        if (_balance < _redeemCost)
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(
                                '还差 ${_redeemCost - _balance} 积分可兑换 1 天',
                                style: theme.textTheme.bodySmall),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // ── 卡密兑换 ──
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('卡密兑换',
                            style: theme.textTheme.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _codeCtrl,
                          decoration: const InputDecoration(
                            hintText: '输入卡密（不区分大小写）',
                            border: OutlineInputBorder(),
                          ),
                          onSubmitted: (_) => _redeemCode(),
                        ),
                        const SizedBox(height: 10),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                            onPressed: _busy ? null : _redeemCode,
                            child: const Text('立即兑换'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text('会员与支付相关功能正在按平台规则逐步开放。',
                    style: theme.textTheme.bodySmall,
                    textAlign: TextAlign.center),
              ],
            ),
    );
  }
}