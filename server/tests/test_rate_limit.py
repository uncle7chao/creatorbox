"""限流测试：双维度（openid 优先 + IP 兜底）

⭐ 这个测试存在的理由（2026-10-24 改动的根因）：

原来只用 `request.client.host` 做限流 key，阈值 30 次/分钟。
单个用户每天用 2 次完全够，但**共享出口 IP 的场景会误伤真实用户**：
  · 公司 / 学校 / 网吧 共享出口 IP
  · 移动网络运营商 NAT —— 一个基站下大量用户共享 IP（小程序端最常见）

压测实测：同 IP 40 并发 → 38 个被 429 拒。

改法是「openid 优先 + IP 兜底」。这里守四件事：
  ① openid 维度独立计数（A 超限不影响 B）
  ② 匿名仍按 IP 限流（不能因为有了 openid 就把匿名放开）
  ③ IP 兜底确实拦住「换 openid 刷」（openid 是客户端可传的，不能盲信）
  ④ 非法 openid 退化成 IP（防止用一个畸形字符串占一个独立额度）
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

import app.config as config  # noqa: E402
from app.main import _enforce_rate, _valid_openid, limiter, limiter_ip  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✅' if cond else '  ❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeReq:
    """只提供 _enforce_rate 用到的 request.client.host"""
    def __init__(self, host='1.1.1.1'):
        self.client = _FakeClient(host)


def reset():
    """清空两个限流器的内存计数（每个用例独立）"""
    limiter._hits.clear()
    limiter_ip._hits.clear()


async def hit(n, openid='', ip='1.1.1.1', scope='parse'):
    """连打 n 次，返回 (成功数, 首次被拒时的 detail 或 None, 被拒在第几次)"""
    ok = 0
    for i in range(1, n + 1):
        try:
            await _enforce_rate(_FakeReq(ip), openid, scope=scope)
            ok += 1
        except HTTPException as e:
            return ok, e.detail, i
    return ok, None, None


async def main():
    # ── 1. openid 维度独立计数 ────────────────────────────────
    print('\n── 1. openid 维度 ──')
    reset()
    ok, detail, at = await hit(35, openid='userA_1234567890')
    check(f'openid 额度 = {limiter.per_min} 次', ok == limiter.per_min,
          f'成功 {ok} 次')
    check('超限后拒绝（第 N+1 次）', at == limiter.per_min + 1, f'第 {at} 次被拒')
    check('拒绝时给出 retry_after', detail and '请' in detail, str(detail))

    # ⭐ 核心：换一个 openid 不受影响
    try:
        await _enforce_rate(_FakeReq('1.1.1.1'), 'userB_1234567890')
        check('换 openid 不被前一个的超限牵连（核心修复）', True)
    except HTTPException as e:
        check('换 openid 不被前一个的超限牵连（核心修复）', False, e.detail)

    # ── 2. 匿名仍按 IP ────────────────────────────────────────
    print('\n── 2. 匿名按 IP ──')
    reset()
    ok, detail, at = await hit(35, openid='')
    check(f'匿名额度 = {limiter.per_min} 次/IP', ok == limiter.per_min,
          f'成功 {ok} 次')
    check('匿名超限被拒', at == limiter.per_min + 1, f'第 {at} 次被拒')

    # 换 IP 应重新有额度
    try:
        await _enforce_rate(_FakeReq('2.2.2.2'), '')
        check('匿名换 IP 重新计数', True)
    except HTTPException as e:
        check('匿名换 IP 重新计数', False, e.detail)

    # ── 3. IP 兜底：拦住「换 openid 刷」 ──────────────────────
    print('\n── 3. IP 兜底（openid 是客户端可传的，不能盲信）──')
    reset()
    # 每个 openid 只用 1 次，换 300 个身份证 → 用户维度永不超限
    blocked_at = None
    for i in range(limiter_ip.per_min + 30):
        try:
            await _enforce_rate(_FakeReq('3.3.3.3'), f'bruteforce_{i:08d}')
        except HTTPException as e:
            blocked_at = i + 1
            detail = e.detail
            break
    check(f'换 openid 刷会被 IP 兜底拦（上限 {limiter_ip.per_min}）',
          blocked_at is not None and blocked_at <= limiter_ip.per_min + 1,
          f'第 {blocked_at} 次被拦')
    check('兜底的错误措辞与用户维度区分开（便于排查）',
          detail and '同网络' in detail, str(detail))

    # ── 4. 非法 openid 退化成 IP ──────────────────────────────
    print('\n── 4. openid 格式校验 ──')
    check('正常微信 openid 合法', _valid_openid('o1234567890abcdef1234567890ab'))
    check('游客 guest_xxx 合法', _valid_openid('guest_abc12345'))
    check('空串非法', not _valid_openid(''))
    check('过短非法（< 8）', not _valid_openid('ab'))
    check('过长非法（> 64）', not _valid_openid('x' * 70))
    check('含空格非法', not _valid_openid('has space'))
    check('含特殊字符非法', not _valid_openid('a;b/c'))

    reset()
    ok, detail, at = await hit(35, openid='bad openid!')
    check('非法 openid 走 IP 维度（与匿名同一份额度）',
          ok == limiter.per_min and at == limiter.per_min + 1,
          f'成功 {ok} 次，第 {at} 次被拒')

    # ── 5. scope 分桶：功能之间不互相挤占额度 ──────────────────
    print('\n── 5. scope 分桶（parse 用光不影响 pdf）──')
    reset()
    # 把 parse 桶打满
    ok_p, detail, at = await hit(35, openid='')
    check('（前置）parse 桶已打满', ok_p == limiter.per_min, f'{ok_p} 次')
    # 换个 scope，同一个 IP 应该还有额度
    try:
        await _enforce_rate(_FakeReq('1.1.1.1'), '', scope='pdf')
        check('parse 额度用光后 pdf 仍可用（不该互相挤占）', True)
    except HTTPException as e:
        check('parse 额度用光后 pdf 仍可用（不该互相挤占）', False, e.detail)
    # 但 IP 兜底是跨功能共享的 —— 这点用「带 openid 的路径」验证
    reset()
    for i in range(limiter_ip.per_min):
        await _enforce_rate(_FakeReq('4.4.4.4'), f'cross_{i:08d}', scope='parse')
    try:
        await _enforce_rate(_FakeReq('4.4.4.4'), 'cross_new_0001', scope='pdf')
        check('IP 兜底跨功能共享（换 endpoint 绕不过）', False, '居然通过了')
    except HTTPException as e:
        check('IP 兜底跨功能共享（换 endpoint 绕不过）', '同网络' in str(e.detail),
              str(e.detail))

    # ── 6. 两个限流器必须是各自独立的实例 ─────────────────────
    print('\n── 6. 实例隔离（防「改配置时不小心共用」）──')
    check('limiter 与 limiter_ip 不是同一对象', limiter is not limiter_ip)
    check('两者的 _hits 不是同一个 dict', limiter._hits is not limiter_ip._hits)
    check('IP 兜底阈值 > 用户维度阈值（否则兜底没有意义）',
          limiter_ip.per_min > limiter.per_min,
          f'{limiter_ip.per_min} vs {limiter.per_min}')

    # ── 7. PDF 并发闸（立即拒绝，不排队）────────────────────
    print('\n── 7. PDF 并发闸 ──')
    from app.main import _pdf_slot
    import app.main as _m

    _m._pdf_active = 0
    limit = config.PDF_CONCURRENCY
    entered = 0
    try:
        # 占满 N 个槽
        for _ in range(limit):
            await _pdf_slot().__aenter__()
            entered += 1
        check(f'可同时进入 {limit} 个（PDF_CONCURRENCY={limit}）', entered == limit,
              f'实际进入 {entered}')
        # 第 N+1 个应立刻 503（不是排队等）
        blocked = False
        detail = ''
        try:
            await _pdf_slot().__aenter__()
        except HTTPException as e:
            blocked = (e.status_code == 503)
            detail = str(e.detail)
        check('超出上限立刻 503（而不是排队干等）', blocked, detail)
        check('503 措辞说明「同时最多 N 个」（用户知道该怎么办）',
              '繁忙' in detail and str(limit) in detail, detail)
    finally:
        # 释放所有已进入的槽，避免污染后续用例
        for _ in range(entered):
            _m._pdf_active -= 1
        if _m._pdf_active < 0:
            _m._pdf_active = 0
    check('槽位释放后计数归零', _m._pdf_active == 0, str(_m._pdf_active))
    # 释放后应能重新进入
    try:
        async with _pdf_slot():
            pass
        check('释放后可再次进入', True)
    except HTTPException as e:
        check('释放后可再次进入', False, str(e.detail))

    # ── 8. 配置可用环境变量调整 ───────────────────────────────
    print('\n── 8. 运维可调 ──')
    check('CB_RATE_LIMIT 覆盖用户维度', hasattr(config, 'RATE_LIMIT_PER_MIN'))
    check('CB_RATE_LIMIT_IP 覆盖 IP 兜底', hasattr(config, 'RATE_LIMIT_IP_PER_MIN'))
    check('PDF 并发可配', hasattr(config, 'PDF_CONCURRENCY'))

    reset()
    print(f'\n════ 限流：{len(PASS)} 通过 / {len(FAIL)} 失败')
    if FAIL:
        for f in FAIL:
            print('  -', f)
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
