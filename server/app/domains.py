"""域名自适应注册表
=================

解决两个实际问题（都是实测踩出来的，不是设计出来的）：

1. **微信小程序域名白名单必须提前枚举，且上限 20 个**
   微信要求「request/socket/downloadFile 合法域名」提前在后台配置，
   而且**域名带随机性时必然超上限**。

   实测各平台 CDN 域名情况（2026-10-05）：

   | 平台 | CDN 域名 | 可枚举？ | 白名单 |
   |---|---|---|---|
   | 抖音图集 | p3/p9-pc-sign.douyinpic.com | ✅ 只有 2 个 | 可 |
   | 抖音视频 | v*-aw-web.douyinvod.com | ⚠️ 前缀有变化 | 谨慎 |
   | B站 | cn-jsnt-ct-01-*.bilivideo.com | ❌ 编号随机 | 走中转 |
   | 好看视频 | vdept*.bdstatic.com | ❌ 子域编号随机 | 走中转 |
   | 微博 | f.video.weibocdn.com | ✅ 单域名 | 可 |
   | 搜狐 | data.vod.itc.cn | ✅ 单域名 | 可 |
   | AcFun | tx-/ali-safety-video.acfun.cn | ✅ 2 个 | 可（但需合并）|

   → 结论：**不是所有平台都能走白名单**。这张表就是用来
     驱动「M3 小程序端哪些平台走直连、哪些走服务端中转」的决策。

2. **平台改版后 CDN 域名会变**
   域名写死在代码里 → 改版即全线失败。
   本表支持**多域名候选 + 运行时探测**。

⭐ 关键设计：域名来自 `knowledge.PLATFORMS`，
   本文件只做「匹配 + 判定 + 候选管理」，不重复维护域名事实。
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from app import knowledge
except ImportError:                     # 直接跑脚本时
    import knowledge

# 白名单上限（微信小程序硬限制）
WECHAT_WHITELIST_LIMIT = 20


def _host_of(url: str) -> str:
    m = re.match(r'https?://([^/?#]+)', url or '')
    return m.group(1).lower() if m else ''


def _pattern_to_regex(pat: str) -> re.Pattern:
    """把域名模式转成匹配正则

    实测踩过的三种写法（knowledge.PLATFORMS 里都出现了）：
      `*.bilivideo.com`→ `*.` 在开头，表示任意子域
      `vdept*.bdstatic.com`     → `*` 在**中间**（好看视频实测就是这个形态）
      `v*-aw-web.douyinvod.com` → `*` 在**中间**（抖音视频）
      `p3-pc-sign.douyinpic.com` → 无通配（精确）
    """
    p = pat.lower()
    # 转义所有正则元字符，只留我们自己的 *
    parts = [re.escape(x) for x in p.split('*')]
    # 中间的 * → 匹配任意多个字符（域名里的连字符/数字段）
    body = '.*'.join(parts)
    # 开头是 '*' 时，额外允许匹配根域本身
    if p.startswith('*.'):
        body = '(?:.*\\.)?' + re.escape(p[2:])
    return re.compile('^' + body + '$')


class DomainRegistry:
    """平台 CDN 域名注册表"""

    def __init__(self):
        # {platform: {'hosts': [...], 'whitelist_ok': bool, 'note': str}}
        self._domains: Dict[str, Dict[str, Any]] = {}
        # 探测结果 {platform: {'hit': [host...], 'ts': float}}
        self._probed: Dict[str, Dict[str, Any]] = {}
        # 未登记域名 {host: {...}} —— 平台新增 CDN 的信号
        self._unknown: Dict[str, Dict[str, Any]] = {}
        self.reload()

    # ---------- 装载 ----------
    def reload(self):
        """从 knowledge.PLATFORMS 重建（唯一事实源仍是 knowledge.py）"""
        self._domains.clear()
        for name, cfg in knowledge.PLATFORMS.items():
            hosts = [h.lower() for h in (cfg.get('cdn_hosts') or [])]
            if not hosts:
                continue
            self._domains[name] = {
                'hosts': hosts,
                'whitelist_ok': cfg.get('whitelist_ok'),
                'status': cfg.get('status'),
                'need_proxy': cfg.get('whitelist_ok') is False,
            }
        return len(self._domains)

    # ---------- 查询 ----------
    def domains_of(self, platform: str) -> List[str]:
        return list(self._domains.get(platform, {}).get('hosts', []))

    def need_proxy(self, platform: str) -> bool:
        """该平台是否必须走服务端中转（CDN 域名不可枚举）"""
        d = self._domains.get(platform)
        if not d:
            return True                    # 未知平台 →保守走中转
        return d.get('whitelist_ok') is not True

    def match(self, url: str) -> Optional[str]:
        """URL 归属哪个平台的 CDN 域

        ⚠️ 域名模式支持**任意位置**的 `*`（实测 knowledge 里有三种形态：
           开头 `*.x.com`、中间 `vdept*.x.com`、中间 `v*-aw-web.x.com`）。
           第一版只处理了 `*.` 开头，导致 B站/好看视频全部匹配失败。
        """
        host = _host_of(url)
        if not host:
            return None
        for name, d in self._domains.items():
            for pat in d['hosts']:
                if _pattern_to_regex(pat).match(host):
                    return name
        return None

    def classify(self, url: str) -> dict:
        """给定 URL，判断能否走小程序直连"""
        name = self.match(url)
        if not name:
            return {'platform': None, 'host': _host_of(url),
                    'whitelist_ok': None, 'reason': '未匹配任何已知 CDN 域'}
        d = self._domains[name]
        ok = d.get('whitelist_ok') is True
        return {
            'platform': name,
            'host': _host_of(url),
            'whitelist_ok': ok,
            'need_proxy': not ok,
            'reason': ('' if ok else
                       f'{name} 的 CDN 域名不可枚举（{d["hosts"]}），'
                       f'需服务端中转'),
        }

    # ---------- 微信白名单导出 ----------
    def wechat_whitelist(self, platforms: Optional[List[str]] = None
                         ) -> Dict[str, Any]:
        """生成小程序后台要填的域名清单

        ⚠️ 只包含**实测确认域名有限**的平台；
           域名随机的平台必须走中转，不要往白名单里塞。
        """
        names = platforms or list(self._domains.keys())
        rows = []
        for n in names:
            d = self._domains.get(n)
            if not d:
                continue
            ok = d.get('whitelist_ok') is True
            rows.append({
                'platform': n,
                'name_cn': knowledge.PLATFORMS.get(n, {}).get('name_cn', n),
                'status': d.get('status'),
                'whitelist_ok': ok,
                'domains': [f'https://{h}' for h in d['hosts']],
                'count': len(d['hosts']),
                'note': ('' if ok else
                         '域名不可枚举 → 该平台走服务端中转，勿配置'),
            })
        usable = [r for r in rows if r['whitelist_ok']]
        total = sum(r['count'] for r in usable)
        over = total > WECHAT_WHITELIST_LIMIT
        return {
            'rows': rows,
            'usable': [r['platform'] for r in usable],
            'must_proxy': [r['platform'] for r in rows if not r['whitelist_ok']],
            'total_domains': total,
            'limit': WECHAT_WHITELIST_LIMIT,
            'within_limit': not over,
            'ready_to_configure': [r for r in usable
                                   if r['status'] == 'ready'],
            'note': ('小程序「downloadFile 合法域名」上限 20。'
                     + (f'当前 {total} 个，未超。' if not over
                        else f'当前 {total} 个，**已超限**，'
                             '需中转或申请提额。')),
        }

    # ---------- 运行时探测 ----------
    def record_probe(self, url: str, ok: bool):
        """解析成功时调用，记录哪些域名实际在用"""
        name = self.match(url)
        host = _host_of(url)
        if not host:
            return
        if not name:
            # ⭐ 未归属任何平台的域名：可能是平台**新增了 CDN**
            #    （老 CDN 被停用、新域名上线时就会这样）
            rec = self._unknown.setdefault(
                host, {'hits': 0, 'first_seen': time.time(), 'last_seen': 0.0,
                       'ok': 0})
            rec['hits'] += 1
            rec['last_seen'] = time.time()
            if ok:
                rec['ok'] += 1
            return
        rec = self._probed.setdefault(
            name, {'hit': [], 'miss': 0, 'ts': time.time()})
        if ok and host and host not in rec['hit']:
            rec['hit'].append(host)
            rec['ts'] = time.time()
        elif not ok:
            rec['miss'] += 1

    def unknown_hosts(self, min_hits: int = 1) -> List[dict]:
        """⭐ 出现过的「未登记域名」—— 平台新增 CDN 的最强信号

        典型场景：平台把CDN 换了，老域名下线、新域名上线。
        表现为：本表里开始出现从未登记过的域名。
        """
        out = []
        for host, rec in self._unknown.items():
            if rec['hits'] >= min_hits:
                out.append({
                    'host': host,
                    'hits': rec['hits'],
                    'ok': rec['ok'],
                    'first_seen': rec['first_seen'],
                    'last_seen': rec['last_seen'],
                })
        return sorted(out, key=lambda x: -x['hits'])

    def observed(self, platform: str) -> List[str]:
        """实际观测到的域名（可能超出配置列表 → 说明平台新增了 CDN）"""
        return list(self._probed.get(platform, {}).get('hit', []))

    def unlisted_hosts(self) -> List[dict]:
        """⭐ 反向发现：实际用到但未登记的域名

        这是**平台改版的早期信号** —— 新域名出现 = 平台可能动了 CDN。

        ⚠️ 判定必须用与 match() 相同的模式匹配，
           不能用「字符串完全相等」——
           否则 `cn-sccd-ct-02-23.bilivideo.com` 会被误报为
           「未登记」，而它明明匹配 `*.bilivideo.com`
           （第一版就踩了这个坑，一开服务就冒出两条假告警）。
        """
        out = []
        for name, rec in self._probed.items():
            pats = [p for p in self.domains_of(name)]
            for h in rec['hit']:
                if not any(_pattern_to_regex(p).match(h) for p in pats):
                    out.append({'platform': name, 'host': h,
                                'known': pats})
        return out

    def snapshot(self) -> Dict[str, Any]:
        return {
            'platforms': len(self._domains),
            'whitelist_ok': [n for n, d in self._domains.items()
                             if d.get('whitelist_ok') is True],
            'must_proxy': [n for n, d in self._domains.items()
                           if d.get('whitelist_ok') is not True],
            'observed': {n: self.observed(n) for n in self._domains
                         if self.observed(n)},
            'unlisted_hosts': self.unlisted_hosts(),
            'unknown_hosts': self.unknown_hosts(),
        }


registry = DomainRegistry()


if __name__ == '__main__':
    import json
    print('=' * 66)
    print('域名自适应注册表')
    print('=' * 66)
    print(f'已登记平台: {registry._domains.keys()}\n')

    print('--- 各平台 CDN 域与白名单可行性 ---')
    for n, d in registry._domains.items():
        ok = '✅ 可白名单' if d['whitelist_ok'] is True else \
             '❌ 需中转'
        print(f'  {n:10s} {ok:12s} {d["hosts"]}')

    print('\n--- URL 归属判定（实测）---')
    samples = [
        'https://p3-pc-sign.douyinpic.com/tos-cn-i-0813c001/x~tplv-dy-aweme-images.jpeg',
        'https://v3-dy-aw-web.douyinvod.com/abc/video.mp4',
        'https://cn-jsnt-ct-01-123.bilivideo.com/x/y.mp4',
        'https://f.video.weibocdn.com/u0/abc.mp4',
        'https://data.vod.itc.cn/?k=xxx',
        'https://vdept3.bdstatic.com/mda-x/1080p/cae_h264/1.mp4',
        'https://tx-safety-video.acfun.cn/mediacloud/a.m3u8',
        'https://unknown-cdn.example.com/x.mp4',
    ]
    for u in samples:
        c = registry.classify(u)
        mark = '✅' if c['whitelist_ok'] else \
               ('⚠️ ' if c['whitelist_ok'] is None else '❌')
        print(f'  {mark} {c["platform"] or "(未匹配)":10s} '
              f'{c["host"][:44]}')
        if c['reason']:
            print(f'      → {c["reason"][:66]}')

    print('\n--- 微信小程序白名单清单 ---')
    wl = registry.wechat_whitelist()
    print(f'  可配置: {wl["usable"]}')
    print(f'  需中转: {wl["must_proxy"]}')
    print(f'  域名总数: {wl["total_domains"]} / 上限 {wl["limit"]}'
          f' → {"✅ 未超" if wl["within_limit"] else "❌ 超限"}')
    print(f'  {wl["note"]}')

    print('\n--- 完整快照 ---')
    print(json.dumps(registry.snapshot(), ensure_ascii=False, indent=2))
