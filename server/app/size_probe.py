"""视频文件大小探测（content-length）。

为什么需要
----------
竞品（截图参考）在视频卡右下角显示「时长:4分3秒 大小:45MB」——
用户在下载前就知道文件多大。这是真实决策信息：
大文件下载失败率高、耗流量，知道了才好决策。

我们此前只显示时长，没有大小。

⭐ 为什么用 HEAD 请求而不是各平台的私有字段
--------------------------------------------
各家 API 字段不统一（抖音 bit_rate 项可能带 data_size，但并非所有平台有），
逐个平台适配 = 长期维护成本 + 新平台又要加一遍。
HTTP HEAD 拿 content-length 是**通用**的：任何静态文件服务器都支持。

⚠️ 代价：HEAD 会多一次网络往返。所以：
  · 只对【选中的那一档】探测，不是每档都探（8 档全探太慢）
  · 并发执行，超时短（3 秒）
  · 拿不到就返回 0（不编造大小 —— 界面显示"大小未知"比显示错值好）
"""

import asyncio
import urllib.request
import urllib.error
from typing import Optional

# UA 要像浏览器，部分 CDN 对空 UA 直接 403
_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
       'AppleWebKit/605.1.15 (KHTML, like Gecko) '
       'Version/17.0 Mobile/15E148 Safari/604.1')

_TIMEOUT = 3.0


def _probe_sync(url: str, timeout: float = _TIMEOUT) -> int:
    """HEAD 请求拿 content-length，失败返回 0。

    ⚠️ 部分 CDN 不支持 HEAD（返回 405），这时退化为 Range 请求：
       `Range: bytes=0-0` 只取 1 字节，响应头里 Content-Range 形如
       `bytes 0-0/12345678` —— 斜杠后面就是总大小。
       这招能绕过「不支持 HEAD」的限制，且实际只下载 1 字节。
    """
    if not url or not url.startswith('http'):
        return 0
    try:
        req = urllib.request.Request(url, method='HEAD', headers={
            'User-Agent': _UA,
            'Accept': '*/*',
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cl = r.headers.get('Content-Length')
            n = int(cl) if cl and cl.isdigit() else 0
            if n:
                return n
    except Exception:
        pass  # 落到 Range 兜底

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': _UA,
            'Range': 'bytes=0-0',
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cr = r.headers.get('Content-Range') or ''
            if '/' in cr:
                total = cr.rsplit('/', 1)[-1].strip()
                if total.isdigit():
                    return int(total)
            cl = r.headers.get('Content-Length')
            return int(cl) if cl and cl.isdigit() else 0
    except Exception:
        return 0


async def probe_size(url: str, timeout: float = _TIMEOUT) -> int:
    """异步探测大小（字节）。拿不到返回 0。"""
    if not url:
        return 0
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_probe_sync, url, timeout), timeout=timeout + 0.5)
    except Exception:
        return 0


def human_size(num_bytes: int) -> str:
    """字节 → 人类可读（对齐竞品口径：45MB）。

    ⭐ 用 1024 进制（MB=1024*1024），与安卓/文件管理器习惯一致；
    小程序 wx.getFileSystemManager 也按这个算。
    """
    if not num_bytes or num_bytes <= 0:
        return ''
    mb = num_bytes / (1024 * 1024)
    if mb >= 1:
        return f'{mb:.1f}MB' if mb < 100 else f'{mb:.0f}MB'
    kb = num_bytes / 1024
    if kb >= 1:
        return f'{kb:.0f}KB'
    return f'{num_bytes}B'


def human_duration(ms: Optional[int]) -> str:
    """毫秒 → 「4分3秒」/「45秒」/「1小时2分」。

    ⭐ 竞品口径是「4分3秒」（不含 0 秒位）。这里保持一致：
      4分3秒 → '4分3秒'
      45秒  → '45秒'
      62分  → '1小时2分'
    """
    if not ms or ms <= 0:
        return ''
    total = int(ms // 1000)
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    if h:
        return f'{h}小时{m}分' if m else f'{h}小时'
    if m:
        return f'{m}分{s}秒' if s else f'{m}分'
    return f'{s}秒'
