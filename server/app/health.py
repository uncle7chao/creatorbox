"""平台健康度监控 —— v3 方案第4 章的「生命线」
==========================================

为什么必须做（不是可选项）
--------------------------
v3 定位是「护城河不在功能，在**韧性**」。而实测证明：
平台改版是**常态**，不是意外 —— 仅我这十几轮实测就撞上：
| 平台 | 变化 | 表现 |
|---|---|---|
| 好看视频| 需先访问首页拿 cookie | 裸调接口 errno:101007 |
| 搜狐 | api_key/sver 必带 | 缺了就报"视频不存在" |
| 搜狐 | m3u8 分段全是重复内容 | ffmpeg 合并静默产出垃圾 |
| 快手 | GraphQL 加了反爬滑块 | result=400002 + captcha |
| 微博 | 主站域名要cookie，h5 不用 | 匿名可用性天差地别 |

如果这些改版发生时**没有告警**，用户看到的就是「解析失败」，
我们却不知道是代码 bug 还是平台变了 —— 这就是韧性不足。

三层监控
--------
```
L1 存活probe  定时打一个「已知一定可解析」的固定样本
              → 快（<3s），能发现「接口挂了/被风控」
L2 真实流量  记录 /api/parse 的每次成败（按平台）
              → 慢，但能发现「某些视频解析不了」
L3 能力断言  检查解析器该有的能力标记是否还在
              → 例：抖音应拿到 1080P、AcFun 应有 5 档
```

⚠️ L1 最大的坑：**探针样本本身会失效**。
搜狐那条探针（620253046）现在解析成功但返回 truncated=True
—— 如果只看「HTTP 200」会误判为健康。所以探针必须**断言能力**，
不只是断言不报错。
"""
from __future__ import annotations

import asyncio
import time
from collections import deque

_WB_PROBE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
                'Mobile/15E148 Safari/604.1')
from typing import Any, Callable, Deque, Dict, List, Optional

try:
    from app import config, knowledge
except ImportError:
    import config
    import knowledge

# ---------- L1 探针样本（都是实测跑通的真实链接） ----------
# 2026-10-11 起支持样本池：cfg['urls'] 可配多条候选；某条样本内容被删时
# 自动冷却 24h 并轮换下一条，全部失败才判平台故障（消灭单样本误报）。
PROBES: Dict[str, Dict[str, Any]] = {
    'douyin': {
        'url': 'https://v.douyin.com/ntaaK4aH9pE/',
        # 断言：要么拿到视频地址，要么拿到图集
        'assert': lambda r: bool(r.get('video_url')
                                 or r.get('images')),
        'note': '图集样本（type=image，8 张无水印）',
    },
    'bilibili': {
        'url': 'https://www.bilibili.com/video/BV1GJ411x7h7',
        'assert': lambda r: bool(r.get('video_url')),
        'note': '720P / 49.6MB / 单文件含音轨',
    },
    'haokan': {
        'url': 'https://haokan.baidu.com/v?vid=1688233510589355861',
        # ⚠️ 必须断言清晰度，否则平台退化成只给一档也发现不了
        'assert': lambda r: r.get('options_count', 0) >= 4,
        'note': '4 档 360/480/720/1080P，26s / 6.2MB',
    },
    'sohu': {
        'url': ('https://tv.sohu.com/v/'
                'MjAyNjA5MzAvbjYyMDI1MzY2MC5zaHRtbA==.html'),
        # 已知 30s 内视频应完整；>30s 会 truncated（属预期，非故障）
        'assert': lambda r: bool(r.get('video_url')),
        'note': '⚠️ 该平台 >30s 视频必然 truncated，探针只用 30s 内的',
    },
    'weibo': {
        'url': ('https://weibo.com/tv/show/1034:5343195622473745'
                '?mid=5343196424963244'),
        'assert': lambda r: bool(r.get('video_url')),
        'note': '3 档 1080P / 319s / 112MB',
    },
    # ⭐ 快手走m.gifshow.com 这个「未跟进反爬」的域名 ——
    #   万一平台哪天补上反爬，只有探针能第一时间发现。
    'kuaishou': {
        'url': 'https://www.kuaishou.com/f/X-3M7HpE9Kh3sh1V',
        # 样本池（2026-10-11 实测：备用样本 X3n2Z5bXSt9g1wp 解析成功 3 档）。
        # ⚠️ 只填【实测通过】的样本 —— 填错会让探针长期 false alarm，
        #    比单样本更糟。轮换见 _sample_urls + Monitor 的轮转逻辑。
        #    这里【不重复列 url 本身】：_sample_urls 会把 url 插到池首。
        'urls': [
            'https://www.kuaishou.com/f/X3n2Z5bXSt9g1wp',
        ],
        # 必须断言拿到播放地址 + 时长量级对，
        # 否则「页面 200 但结构空」会漏报
        'assert': lambda r: (r.get('type') == 'video'
                             and bool(r.get('video_url'))
                             and (r.get('duration_ms') or 0) > 5000),
        'note': '13.1s / 720x1280 / 4档（含 manifest 备选）',
        'caveat': '★ 依赖 m.gifshow.com 未被反爬覆盖。'
                  '若平台补上反爬，此探针会fail —— '
                  '那是「平台加固」而非「我们改坏」，需换入口',
    },
    'acfun': {
        'url': 'https://www.acfun.cn/v/ac48890260',
        # 必须断言 5 档，少一档说明 manifest 结构变了
        'assert': lambda r: r.get('options_count', 0) >= 5,
        'note': '5 档 360~1080P+ / 59 段 / 299s',
    },
    'xiaohongshu': {
        # ⚠️ 必须带 xsec_token，且**必须用完整链接**（短链无 token 读不到）
        'url': ('https://www.xiaohongshu.com/discovery/item/'
                '6a827209000000002701cde0'
                '?xsec_token=AB7esHwJgaSaSlhVeq7GJlZN8Fi1J6MrUIjviv8R_APxM='
                '&xsec_source=pc_share'),
        # L3 能力断言：必须**恰好 7 张**且类型判为 image。
        # ⚠️ 之前写 >= 1，平台若把 7 张退化成 1 张会漏报；
        #    更严重的是「视频笔记被误判成图集」也测不出来（P27）。
        'assert': lambda r: (r.get('type') == 'image'
                             and r.get('image_count') == 7
                             and r.get('no_watermark') is True),
        'note': '7 张图 / 1080x1683 / fileId 拼无水印原图',
        'caveat': 'xsec_token 有时效 —— 过期后这个探针会失败，'
                  '属于预期行为（需换新 token），不是平台改版',
    },
    # ⭐ 第二条样本：视频笔记。必须有独立探针 ——
    #   图集探针全绿不代表视频链路可用（两条链路取址方式完全不同）。
    'xiaohongshu_video': {
        # ⚠️ 这里必须写**去掉 _pure 后缀**的名字（attach 用它做匹配）
        'parser': 'xiaohongshu',
        'url': ('https://www.xiaohongshu.com/discovery/item/'
                '6a72adee0000000033036edf?source=webshare&xhsshare=pc_web'
                '&xsec_token=ABgKYGq72MJJJWO8OVQh3MtnwjRfcqKYxsujnzRIHNdTA='
                '&xsec_source=pc_share'),
        # 断言 type=video（P27 核心）+ 时长数量级正确（P28 核心）
        'assert': lambda r: (r.get('type') == 'video'
                             and r.get('options_count', 0) >= 2
                             and (r.get('video_meta') or {}).get('duration_s', 0)
                             > 60),
        'note': '3 档 h264/h265 / 1920x1080 / 261.39s / 63.78MB',
        'caveat': '同 xiaohongshu，token 过期需更换',
    },
}


def _now() -> float:
    return time.time()


def _sample_urls(cfg: dict) -> list:
    """探针候选样本列表：cfg['url']（首选）+ cfg['urls']（池）。

    旧配置只有 url 也兼容（单元素池，行为与升级前一致）。

    ⚠️ 去重是必需的，不是保险：按直觉写法会在 urls 里也列上 url 本身
      （因为 urls 读着像是「备选」，自然会包含首选），导致合并后同一条出现
      两次 —— 轮转时等于白白多试一次同一条，掩盖了真实故障。
    """
    urls = [u for u in (cfg.get('urls') or []) if u]
    if cfg.get('url'):
        urls.insert(0, cfg['url'])
    # 保序去重
    return list(dict.fromkeys(urls)) or ['']


def verify_cookie(platform: str, cookie: str) -> Dict[str, Any]:
    """即时验证一条登录态 Cookie（看板保存时调用，不走 24h 节流）。

    与 _check_cookies 的判定口径一致：
    · xhs   ：带 Cookie 访问 explore，被 302 到 /login = 失效
    · weibo ：带 Cookie 访问 m 站话题接口，非 200 = 失效
    返回 {'ok': bool, 'error': str}；网络异常按失败处理（err 带原因）。
    """
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cookie = (cookie or '').strip()
    try:
        if platform == 'xhs':
            req = urllib.request.Request(
                'https://www.xiaohongshu.com/explore',
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                         'Cookie': cookie})
            with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                final = r.geturl()
            if '/login' in final:
                return {'ok': False, 'error': 'Cookie 已失效（被重定向到登录页）'}
            return {'ok': True, 'error': ''}
        if platform == 'weibo':
            req = urllib.request.Request(
                'https://m.weibo.cn/api/container/getIndex'
                '?containerid=100103type%3D1%26q%3Dtest&page_type=searchall',
                headers={'User-Agent': _WB_PROBE_UA, 'Cookie': cookie})
            with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                if r.status != 200:
                    return {'ok': False, 'error': f'Cookie 已失效（HTTP {r.status}）'}
            return {'ok': True, 'error': ''}
        return {'ok': False, 'error': f'未知平台 {platform}'}
    except Exception as e:
        return {'ok': False, 'error': f'验证请求失败: {str(e)[:70]}'}


class PlatformProbe:
    """L1 · 单个平台的存活探针

    2026-10-11 升级：**样本池**。cfg['url'] 之外可配 cfg['urls'] 候选列表——
    平台活着但某条样本内容被删（解析报错）时，该样本进 24h 冷却并自动轮换
    到下一条；只有**全部候选失败**才记为平台故障（消灭「样本死了被误报
    平台挂了」这一真实误报源——10-11 两次踩坑：抖音 hZMkNvXLtLc 被删）。
    """

    _SAMPLE_DEAD_COOLDOWN = 24 * 3600   # 样本死亡冷却（秒），到期自动重试复活

    def __init__(self, name: str, parser, cfg: dict):
        self.name = name
        self.parser = parser
        self.cfg = cfg
        self.history: Deque[dict] = deque(maxlen=50)
        self.consecutive_fail = 0
        self.last_error = ''
        self._dead_until: Dict[str, float] = {}   # 样本 url → 冷却截止时间
        self._preferred = 0                        # 上次成功的样本下标（优先复试）

    def _display_name(self) -> str:
        """平台中文名。

        一个平台可能挂多条探针（如小红书图集 + 视频），
        后缀 `_video` 不是平台名的一部分，要剥掉再查。
        """
        base = self.name.split('_')[0]
        return knowledge.PLATFORMS.get(base, {}).get(
            'name_cn', self.name)

    async def run(self) -> dict:
        t0 = _now()
        rec: Dict[str, Any] = {
            'platform': self.name,
            'ts': t0,
            'name_cn': self._display_name(),
            'variant': self.name if self.name in knowledge.PLATFORMS else None,
        }

        # ── 样本池轮换 ──
        urls = _sample_urls(self.cfg)
        now = _now()
        order = urls[self._preferred:] + urls[:self._preferred]
        candidates = [u for u in order
                      if self._dead_until.get(u, 0) <= now] or order
        rec['samples_total'] = len(urls)
        rec['samples_tried'] = len(candidates)

        failed_samples: list = []
        parsed: Dict[str, Any] | None = None
        last_err = ''
        for u in candidates:
            try:
                r = await asyncio.wait_for(
                    self.parser.parse(u), timeout=30)
                if not r.get('success'):
                    failed_samples.append(u)
                    last_err = str(r.get('error', ''))[:80]
                    continue
                try:
                    good = self.cfg['assert'](r)
                except Exception as e:
                    good = False
                    rec['assert_error'] = str(e)[:60]
                if good:
                    parsed = r
                    idx = urls.index(u)
                    rec.update(ok=True,
                               latency_ms=round((_now() - t0) * 1000),
                               sample_idx=idx,
                               type=r.get('type'),
                               quality=r.get('quality'),
                               options=r.get('options_count'),
                               truncated=bool(r.get('truncated')),
                               size=r.get('size'))
                    if r.get('truncated'):
                        rec['warning'] = '返回内容被截断（平台可能改了预览策略）'
                    # 平台明确活着 → 本轮失败的样本标记冷却（多为内容被删）
                    for fu in failed_samples:
                        self._dead_until[fu] = now + self._SAMPLE_DEAD_COOLDOWN
                    self._preferred = idx
                    break
                failed_samples.append(u)
                last_err = (f"能力断言失败：拿到数据但 options="
                            f"{r.get('options_count')} / type={r.get('type')}"
                            f"（接口结构可能已变）")
            except asyncio.TimeoutError:
                failed_samples.append(u)
                last_err = '探针超时（>30s）'
            except Exception as e:
                failed_samples.append(u)
                last_err = f'{type(e).__name__}: {str(e)[:70]}'

        if parsed is None:
            # 全部候选失败 → 平台级故障（真实告警，不再是样本误报）
            rec.update(ok=False, error=last_err)
            if len(urls) > 1 and len(failed_samples) >= len(urls):
                rec['pool_exhausted'] = True

        if rec['ok']:
            self.consecutive_fail = 0
        else:
            self.consecutive_fail += 1
            self.last_error = rec.get('error', '')
        rec['consecutive_fail'] = self.consecutive_fail
        rec['status'] = self._status(rec)
        self.history.append(rec)
        return rec

    def _status(self, rec: dict) -> str:
        """状态机：ok / degraded / down / unknown"""
        if rec['ok']:
            if rec.get('warning'):
                return 'degraded'
            return 'ok'
        # 1 次失败可能是网络抖动，2 次才判定
        return 'down' if self.consecutive_fail >= 2 else 'degraded'


class TrafficRecorder:
    """L2 · 真实流量成败记录（按平台）"""

    def __init__(self, window: int = 1800):
        self.window = window
        self._data: Dict[str, Deque[dict]] = {}

    def record(self, platform: str, ok: bool, latency: float = 0.0,
               error: str = '', truncated: bool = False):
        dq = self._data.setdefault(platform, deque(maxlen=500))
        dq.append({'ts': _now(), 'ok': ok, 'ms': round(latency * 1000),
                   'error': error[:80], 'truncated': truncated})
        self._gc()

    def _gc(self):
        cutoff = _now() - self.window
        for dq in self._data.values():
            while dq and dq[0]['ts'] < cutoff:
                dq.popleft()

    def stats(self, platform: str) -> dict:
        dq = self._data.get(platform)
        if not dq:
            return {'samples': 0}
        n = len(dq)
        ok = sum(1 for x in dq if x['ok'])
        tr = sum(1 for x in dq if x.get('truncated'))
        lats = sorted(x['ms'] for x in dq if x['ok'])
        p50 = lats[len(lats) // 2] if lats else None
        p95 = lats[int(len(lats) * 0.95)] if lats else None
        return {
            'samples': n,
            'ok': ok,
            'fail': n - ok,
            'success_rate': round(ok / n, 3) if n else None,
            'truncated': tr,
            'p50_ms': p50,
            'p95_ms': p95,
            'last_error': next((x['error'] for x in reversed(dq)
                                if not x['ok']), ''),
        }

    def all_stats(self) -> dict:
        return {p: self.stats(p) for p in self._data}


class HealthMonitor:
    """平台健康度总控

    M1.5 缺口#3 补齐：历史持久化 + down 告警落库 + webhook 通知。
    · 每轮探针结果写 health_history（保留 HEALTH_RETENTION_DAYS 天）
    · 状态机进入 down（连续 2 次失败）→ health_alerts 建档并通知（只通知一次，
      持续 down 只递增 count，防轰炸）
    · 恢复 ok → 销案并通知
    · degraded（单次失败/能力警告）只进历史和 summary，不建告警 —— 防骚扰
    """

    def __init__(self):
        self.probes: Dict[str, PlatformProbe] = {}
        self.traffic = TrafficRecorder()
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self.last_run: float = 0.0
        self._prev_status: Dict[str, str] = {}   # 平台 → 上一轮状态（迁移检测）
        self._cycles = 0                          # 每 10 轮清一次过期历史

    def attach(self, parsers: List[Any]):
        """从解析器列表注册探针

        ⭐ 一个解析器可挂**多条探针**（靠 PROBES 里的 `parser` 字段复用）——
        小红书的图集链路与视频链路取址方式完全不同，必须分别探测：
        图集全绿不代表视频可用。
        """
        by_name: Dict[str, List[str]] = {}
        for key, cfg in PROBES.items():
            pname = cfg.get('parser') or key
            by_name.setdefault(pname, []).append(key)

        for p in parsers:
            base = p.name.replace('_pure', '')
            for probe_key in by_name.get(base, [base]):
                cfg = PROBES.get(probe_key)
                if not cfg:
                    continue
                self.probes[probe_key] = PlatformProbe(probe_key, p, cfg)
            if base in PROBES and base not in self.probes:
                self.probes[base] = PlatformProbe(base, p, PROBES[base])

    _cookie_last_check: float = 0.0

    async def _check_cookies(self) -> list:
        """小红书/微博服务端 Cookie 有效性检查（24 小时一次）。

        · 小红书：带 Cookie 访问 explore，被 302 到 /login = 失效
        · 微博：带 Cookie 访问 m 站话题接口，432 = 失效
        结果走常规落库/告警链路（platform=xhs_cookie / weibo_cookie）。
        """
        if _now() - self._cookie_last_check < 24 * 3600:
            return []
        self._cookie_last_check = _now()

        import urllib.request
        import ssl
        out = []
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        xhs = (getattr(config, 'XHS_COOKIE', '') or '').strip()
        if xhs:
            ok, err = False, ''
            try:
                req = urllib.request.Request(
                    'https://www.xiaohongshu.com/explore',
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0',
                             'Cookie': xhs})
                with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                    final = r.geturl()
                ok = '/login' not in final
                if not ok:
                    err = 'Cookie 已失效（被重定向到登录页）'
            except Exception as e:
                err = str(e)[:60]
            out.append({'platform': 'xhs_cookie', 'ok': ok,
                        'status': 'ok' if ok else 'down',
                        'error': err, 'consecutive_fail': 0 if ok else 1,
                        'ts': _now()})

        wb = (getattr(config, 'WEIBO_COOKIE', '') or '').strip()
        if wb:
            ok, err = False, ''
            try:
                req = urllib.request.Request(
                    'https://m.weibo.cn/api/container/getIndex'
                    '?containerid=100103type%3D1%26q%3Dtest&page_type=searchall',
                    headers={'User-Agent': _WB_PROBE_UA, 'Cookie': wb})
                with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                    ok = r.status == 200
                if not ok:
                    err = f'Cookie 已失效（HTTP {r.status}）'
            except Exception as e:
                err = str(e)[:60]
            out.append({'platform': 'weibo_cookie', 'ok': ok,
                        'status': 'ok' if ok else 'down',
                        'error': err, 'consecutive_fail': 0 if ok else 1,
                        'ts': _now()})
        return out

    async def run_once(self) -> dict:
        async with self._lock:
            results = await asyncio.gather(
                *[pr.run() for pr in self.probes.values()],
                return_exceptions=True)
        out = []
        for pr, r in zip(self.probes.values(), results):
            if isinstance(r, Exception):
                out.append({'platform': pr.name, 'ok': False,
                            'status': 'down',
                            'error': str(r)[:70]})
            else:
                out.append(r)
        self.last_run = _now()

        # Cookie 有效性探针（24h 节流）：服务端配了小红书/微博 Cookie 时，
        # 每天验证一次登录态——失效自动进历史+告警，比用户报障早
        try:
            cookie_probes = await self._check_cookies()
            if cookie_probes:
                out.extend(cookie_probes)
        except Exception as e:
            print(f'[health] cookie 探针异常: {str(e)[:60]}')

        return self.summary(out)

    def summary(self, latest: Optional[List[dict]] = None) -> dict:
        latest = latest if latest is not None else [
            h[-1] for h in (pr.history for pr in self.probes.values()) if h]
        by = {r['platform']: r for r in latest}
        counts = {'ok': 0, 'degraded': 0, 'down': 0}
        for r in latest:
            counts[r.get('status', 'unknown')] = \
                counts.get(r.get('status', 'unknown'), 0) + 1
        alerts = []
        for r in latest:
            if r.get('status') == 'down':
                alerts.append({
                    'level': 'critical',
                    'platform': r['platform'],
                    'name_cn': r.get('name_cn', r['platform']),
                    'message': f"连续 {r.get('consecutive_fail')} 次探针失败"
                               f"：{r.get('error', '')[:50]}",
                    'action': '可能是平台改版或风控 —— 立即用浏览器核对页面',
                })
            elif r.get('status') == 'degraded':
                alerts.append({
                    'level': 'warning',
                    'platform': r['platform'],
                    'name_cn': r.get('name_cn', r['platform']),
                    'message': r.get('error') or r.get('warning')
                               or '偶发失败',
                    'action': '关注趋势，连续出现则人工核查',
                })
        return {
            'ts': self.last_run,
            'checked': len(latest),
            'counts': counts,
            'all_ok': counts['ok'] == len(latest) and latest != [],
            'probes': latest,
            'traffic': self.traffic.all_stats(),
            'alerts': alerts,
        }

    # ---------- 持久化 + 告警（M1.5 缺口#3） ----------

    def _persist_and_alert(self, report: dict) -> None:
        """探针结果落库 + down 告警建档/销案 + 通知。

        db 不可用（init 未调用/磁盘故障）时静默降级为纯内存模式 ——
        健康监控自己不能成为故障源。
        """
        try:
            from app import db
        except ImportError:
            import db
        try:
            recs = [{'platform': p['platform'], 'status': p.get('status'),
                     'ok': p.get('ok'), 'latency_ms': p.get('latency_ms', 0),
                     'error': p.get('error') or p.get('warning') or '',
                     'consecutive_fail': p.get('consecutive_fail', 0),
                     'ts': p.get('ts')} for p in report.get('probes', [])]
            db.health_record(recs)

            for p in report.get('probes', []):
                plat = p['platform']
                status = p.get('status')
                prev = self._prev_status.get(plat, 'ok')

                if status == 'down':
                    is_new = db.health_alert_upsert(
                        plat, 'critical',
                        f"连续 {p.get('consecutive_fail', 2)} 次探针失败："
                        f"{(p.get('error') or '')[:80]}",
                        '可能是平台改版或风控 —— 立即用浏览器核对页面')
                    if is_new:
                        self._notify(
                            f"[CreatorBox] {p.get('name_cn', plat)} 解析不可用",
                            p)
                elif status == 'ok' and prev == 'down':
                    if db.health_alert_resolve(plat):
                        self._notify(
                            f"[CreatorBox] {p.get('name_cn', plat)} 已恢复",
                            {'platform': plat, 'recovered': True})

                self._prev_status[plat] = status

            self._cycles += 1
            if self._cycles % 10 == 0:
                removed = db.health_cleanup(config.HEALTH_RETENTION_DAYS)
                if removed:
                    print(f'[health] 清理过期历史 {removed} 行')
        except Exception as e:
            print(f'[health] 持久化/告警失败（不影响探针）: {str(e)[:70]}')

    def _notify(self, title: str, payload: dict) -> None:
        """通知渠道：console 恒有；配了 CB_ALERT_WEBHOOK 再 POST 一份。

        webhook 在线程池里发（5s 超时，失败只打日志）—— 通知失败不能阻塞探针循环。
        """
        print(f'[health][ALERT] {title}  {str(payload.get("error") or "")[:60]}')
        url = config.ALERT_WEBHOOK_URL
        if not url:
            return

        def _post():
            import json as _json
            import urllib.request
            body = _json.dumps({
                'title': title,
                'platform': payload.get('platform'),
                'error': payload.get('error'),
                'ts': payload.get('ts') or _now(),
            }, ensure_ascii=False).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._safe_post, _post)

    @staticmethod
    def _safe_post(fn):
        try:
            fn()
        except Exception as e:
            print(f'[health] webhook 通知失败: {str(e)[:70]}')

    # ---------- 后台定时 ----------
    async def _loop(self):
        interval = max(config.HEALTH_INTERVAL, 60)
        while not self._stop:
            try:
                r = await self.run_once()
                c = r['counts']
                print(f"[health] ok={c['ok']} degraded={c['degraded']} "
                      f"down={c['down']}")
                self._persist_and_alert(r)
            except Exception as e:
                print(f'[health] 探针执行异常: {str(e)[:70]}')
            await asyncio.sleep(interval)

    def start(self):
        if self._task and not self._task.done():
            return
        if not config.ENABLE_HEALTH_PROBE:
            print('[health] 健康探针已关闭（CB_ENABLE_HEALTH=1 开启）')
            return
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        print(f'[health] 健康探针已启动，'
              f'覆盖 {len(self.probes)} 个平台，'
              f'间隔 {max(config.HEALTH_INTERVAL, 60)}s')

    async def stop(self):
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None


monitor = HealthMonitor()


if __name__ == '__main__':
    import asyncio
    import json
    import os
    import sys

    # 直接 `python app/health.py` 运行时包上下文不存在，补上父目录
    if __package__ in (None, ''):
        sys.path.insert(0, os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        __package__ = 'app'

    from app.parsers.acfun_pure import AcfunPureParser
    from app.parsers.bilibili_pure import BilibiliPureParser
    from app.parsers.douyin_pure import DouyinPureParser
    from app.parsers.haokan_pure import HaokanPureParser
    from app.parsers.kuaishou_pure import KuaishouPureParser
    from app.parsers.sohu_pure import SohuPureParser
    from app.parsers.weibo_pure import WeiboPureParser
    from app.parsers.xiaohongshu_pure import XiaohongshuPureParser

    async def _main():
        monitor.attach([DouyinPureParser(), BilibiliPureParser(),
                        HaokanPureParser(), SohuPureParser(),
                        WeiboPureParser(), AcfunPureParser(),
                        XiaohongshuPureParser(), KuaishouPureParser()])
        print(f'已注册 {len(monitor.probes)} 个探针\n')
        r = await monitor.run_once()
        print('=' * 70)
        print(f"{'平台':12s} {'状态':9s} {'耗时':>7s} {'画质':10s} {'档':>3s} 说明")
        print('-' * 70)
        for p in r['probes']:
            mark = {'ok': '✅ ok', 'degraded': '⚠️ degraded',
                    'down': '❌ down'}.get(p['status'], '?')
            print(f"{p['name_cn']:12s} {mark:9s} "
                  f"{str(p.get('latency_ms', '-')) + 'ms':>7s} "
                  f"{str(p.get('quality') or '-'):10s} "
                  f"{str(p.get('options') or '-'):>3s} "
                  f"{(p.get('error') or p.get('warning') or '')[:32]}")
        print(f"\n统计: {r['counts']}  全绿={r['all_ok']}")
        if r['alerts']:
            print('\n告警:')
            for a in r['alerts']:
                print(f"  [{a['level']}] {a['name_cn']}: {a['message']}")
                print(f"      → {a['action']}")
        else:
            print('\n无告警')
        print('\n' + json.dumps({'counts': r['counts'],
                                'all_ok': r['all_ok']},
                               ensure_ascii=False))

    asyncio.run(_main())
