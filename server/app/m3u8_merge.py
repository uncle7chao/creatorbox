"""m3u8 → mp4 合并服务（服务端侧）

解决两个平台的「只有 m3u8、客户端存不了」问题：
- **搜狐**：>30s 的视频 mp4 直链只给30 秒试看片段，完整版在 m3u8
- **AcFun**：全部档位都只有 m3u8（5 档最高 1080P+）

⚠️ 两种模式，代价差别很大，**按需选择**
────────────────────────────────────
模式 A「ffmpeg 直拉」：把 m3u8 URL 交给 ffmpeg 自己拉分段
    ✅ 快（不落盘分段）、磁盘占用小
    ⚠️ 拿不到自定义header。实测搜狐 m3u8 不带 Referer 能拉通，
       但**AcFun 分段带 ?pkey= 签名且可能校验 Referer** → 见模式 B

模式 B「先下后合」：自己并发下分段 → 落盘 → concat
    ✅ 可带任意 header、可控重试、可复用缓存
    ⚠️ 占磁盘、需要清理

实现方式：**优先 A，A 失败自动降级 B**（实测 AcFun 走 A 成功，
搜狐走 A 也成功；但B 作为兜底必须留着，因为签名/header 需求不可预测）。

⭐ 关键：不重编码（-c copy）
────────────────────────────────────
m3u8 的分段本身就是 H.264+AAC，ffmpeg 只需重封装（remux），
不需要转码。实测 155MB / 5 分钟视频 **20 秒内完成**，CPU 占用极低。
只有源是 HEVC 而目标不兼容时才 reencode。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import gzip
import json
import os
import re
import shutil
import ssl
import tempfile
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app import ffmpeg_util

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

# 单个视频的分段下载并发
SEG_CONCURRENCY = 8
# 整体超时（秒）—— 155MB / 5 分钟视频实测 20s 内，留足余量
MERGE_TIMEOUT = 600
# 临时目录
TMP_ROOT = os.getenv('CB_TMP_DIR',
                      os.path.join(tempfile.gettempdir(), 'cb_merge'))


class MergeError(Exception):
    pass


def _get(url: str, referer: str = '', timeout: int = 30) -> bytes:
    h = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate'}
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return raw


def parse_m3u8(text: str, base_url: str) -> Tuple[List[str], float]:
    """解析 m3u8 → (绝对地址分段列表, 总时长秒)

    ⚠️⚠️ **分段很可能是相对路径**（AcFun 实测就是），
    必须用 urljoin 拼绝对地址，不能直接用。
    """
    segs: List[str] = []
    durs: List[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            m = re.match(r'#EXTINF:\s*([\d.]+)', line)
            if m:
                try:
                    durs.append(float(m.group(1)))
                except ValueError:
                    pass
        elif line.startswith('#'):
            continue
        else:
            segs.append(urllib.parse.urljoin(base_url, line))
    return segs, sum(durs)


async def _merge_direct(m3u8_url: str, dst: str,
                        referer: str = '') -> Dict[str, Any]:
    """模式 A：ffmpeg 直接拉 m3u8 并 remux"""
    exe = ffmpeg_util.get_ffmpeg()
    if not exe:
        raise MergeError('ffmpeg 不可用')
    headers = [f'Referer: {referer}\r\n'] if referer else []
    cmd = ffmpeg_util.build_cmd(m3u8_url, dst, reencode=False,
                                 extra_headers=headers)
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), MERGE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MergeError(f'ffmpeg 超时（>{MERGE_TIMEOUT}s）')
    if proc.returncode != 0:
        msg = err.decode('utf-8', 'ignore').strip().splitlines()
        raise MergeError(f'ffmpeg 失败: {msg[-1][:120] if msg else "?"}')
    return {
        'mode': 'direct',
        'elapsed': round(time.time() - t0, 2),
        'size': os.path.getsize(dst) if os.path.exists(dst) else 0,
    }


def _download_segments(m3u8_url: str, workdir: str,
                       referer: str = '') -> Tuple[int, float, int]:
    """模式 B 的分段下载阶段（同步，在线程池里跑）"""
    text = _get(m3u8_url, referer).decode('utf-8', 'ignore')
    segs, total_dur = parse_m3u8(text, m3u8_url)
    if not segs:
        raise MergeError('m3u8 里没有分段')

    os.makedirs(workdir, exist_ok=True)
    paths: List[str] = [os.path.join(workdir, f'{i:05d}.ts')
                        for i in range(len(segs))]

    def _one(i: int) -> int:
        data = _get(segs[i], referer, timeout=60)
        with open(paths[i], 'wb') as f:
            f.write(data)
        return len(data)

    done = 0
    total_bytes = 0
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=SEG_CONCURRENCY) as ex:
        for n in ex.map(_one, range(len(segs))):
            done += 1
            total_bytes += n
    return len(segs), total_dur, total_bytes


async def _merge_from_segments(m3u8_url: str, dst: str,
                               referer: str = '') -> Dict[str, Any]:
    """模式 B：并发下分段 → concat 清单 → ffmpeg remux"""
    exe = ffmpeg_util.get_ffmpeg()
    if not exe:
        raise MergeError('ffmpeg 不可用')

    os.makedirs(TMP_ROOT, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix='seg_', dir=TMP_ROOT)
    t0 = time.time()
    try:
        loop = asyncio.get_event_loop()
        n_seg, dur, nbytes = await loop.run_in_executor(
            None, _download_segments, m3u8_url, workdir, referer)
        dl_time = round(time.time() - t0, 2)

        # concat 清单（ffmpeg concat demuxer 格式）
        list_path = os.path.join(workdir, 'list.txt')
        with open(list_path, 'w', encoding='utf-8') as f:
            for name in sorted(os.listdir(workdir)):
                if name.endswith('.ts'):
                    # 绝对路径 + 正斜杠（Windows 路径要转）
                    p = os.path.join(workdir, name).replace('\\', '/')
                    f.write(f"file '{p}'\n")

        cmd = [exe, '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'concat', '-safe', '0', '-i', list_path,
               '-c', 'copy', '-movflags', '+faststart', dst]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        _, err = await asyncio.wait_for(proc.communicate(), MERGE_TIMEOUT)
        if proc.returncode != 0:
            msg = err.decode('utf-8', 'ignore').strip().splitlines()
            raise MergeError(f'ffmpeg concat 失败: '
                             f'{msg[-1][:120] if msg else "?"}')
        return {
            'mode': 'segments',
            'segments': n_seg,
            'declared_duration_s': round(dur, 2),
            'downloaded_mb': round(nbytes / 1048576, 2),
            'download_elapsed': dl_time,
            'elapsed': round(time.time() - t0, 2),
            'size': os.path.getsize(dst) if os.path.exists(dst) else 0,
        }
    finally:
        # ⭐ 必须清理，否则并发大时会堆满磁盘
        shutil.rmtree(workdir, ignore_errors=True)


async def merge_m3u8_to_mp4(m3u8_url: str, dst: Optional[str] = None,
                            referer: str = '',
                            prefer: str = 'auto',
                            verify: bool = True) -> Dict[str, Any]:
    """把 m3u8 合成单个 mp4

    prefer: 'direct' | 'segments' | 'auto'（默认 auto：先A失败降级 B）
    verify: True 时做**重复分段检测**（见下）
    返回 {ok, path, size, elapsed, mode, ...}
    """
    if not ffmpeg_util.is_available():
        return {'ok': False,
                'error': 'ffmpeg 不可用，无法合并 m3u8',
                'hint': 'pip install imageio-ffmpeg，'
                        '或设置 CB_FFMPEG_PATH 指向系统 ffmpeg'}

    # ⭐ 预检：m3u8 分段是否全是同一份内容（搜狐的坑，见 P22）
    if verify:
        dup = await _check_duplicate_segments(m3u8_url, referer)
        if dup.get('duplicate'):
            return {
                'ok': False,
                'error': f'm3u8 的 {dup["total"]} 个分段内容完全相同，'
                         f'是重复的试看片段而非完整视频',
                'duplicate_segments': True,
                'unique_count': dup['unique'],
                'total_segments': dup['total'],
                'per_segment_duration_s': dup['per_seg_duration'],
                'hint': '不要合并—— 合并只会得到同一段内容的多份拷贝',
            }

    if not dst:
        os.makedirs(TMP_ROOT, exist_ok=True)
        dst = os.path.join(
            TMP_ROOT,
            f'merged_{int(time.time())}_{os.getpid()}.mp4')
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

    order = (['direct', 'segments'] if prefer == 'auto'
             else [prefer])
    errors: List[str] = []
    for mode in order:
        try:
            fn = _merge_direct if mode == 'direct' else _merge_from_segments
            info = await fn(m3u8_url, dst, referer)
            if info.get('size', 0) <= 0:
                raise MergeError('产物为 0 字节')
            # 合并后核对时长：产物时长应接近 EXTINF 声明
            if verify:
                chk = await asyncio.get_event_loop().run_in_executor(
                    None, probe_mp4, dst)
                info['output'] = chk
                declared = await _declared_duration(m3u8_url, referer)
                if declared and chk.get('duration_s'):
                    ratio = chk['duration_s'] / declared
                    info['duration_ratio'] = round(ratio, 3)
                    # 时长明显超出声明 → 分段里有重复/异常
                    if ratio > 1.25 or ratio < 0.75:
                        info['duration_mismatch'] = True
            info.update({'ok': True, 'path': dst})
            return info
        except MergeError as e:
            errors.append(f'{mode}: {e}')
        except Exception as e:      # noqa
            errors.append(f'{mode}: {str(e)[:100]}')
    return {'ok': False, 'error': '；'.join(errors)[:300],
            'tried': order}


async def _declared_duration(m3u8_url: str,
                             referer: str = '') -> Optional[float]:
    try:
        text = _get(m3u8_url, referer).decode('utf-8', 'ignore')
        _, dur = parse_m3u8(text, m3u8_url)
        return dur or None
    except Exception:
        return None


async def _check_duplicate_segments(m3u8_url: str, referer: str = '',
                                    sample: int = 4) -> Dict[str, Any]:
    """⭐ 检测 m3u8 分段是否为同一份内容重复

    真实坑（搜狐，2026-10-05）：m3u8 写着 12 段、EXTINF 合计 76.85s，
    但**12 段的 MD5 完全相同** —— 全是同一个 30 秒试看片段。
    直接合并会得到「30 秒内容 × 12 遍」的 6 分钟垃圾文件，
    而 ffmpeg **不会报错**（它只按 EXTINF 累加时长）。

    所以合并前必须自己查：取前 N 段算哈希，若全同则判定为重复。
    """
    loop = asyncio.get_event_loop()

    def _work() -> Dict[str, Any]:
        try:
            text = _get(m3u8_url, referer).decode('utf-8', 'ignore')
            segs, total = parse_m3u8(text, m3u8_url)
        except Exception:
            return {'duplicate': False, 'total': 0, 'unique': 0,
                    'per_seg_duration': 0}
        if len(segs) < 2:
            return {'duplicate': False, 'total': len(segs),
                    'unique': len(segs), 'per_seg_duration': total}
        import hashlib
        hashes = set()
        n = min(sample, len(segs))
        for i in range(n):
            try:
                data = _get(segs[i], referer, timeout=40)
                hashes.add(hashlib.md5(data).hexdigest())
            except Exception:
                continue
        return {
            'duplicate': len(hashes) == 1 and n >= 2,
            'total': len(segs),
            'unique': len(hashes),
            'sampled': n,
            'per_seg_duration': round(total / len(segs), 2) if segs else 0,
        }

    return await loop.run_in_executor(None, _work)


def probe_mp4(path: str) -> Dict[str, Any]:
    """读产物基本信息（不重新下载）"""
    import struct
    try:
        with open(path, 'rb') as f:
            head = f.read(2 << 20)
        size = os.path.getsize(path)
        info: Dict[str, Any] = {
            'size': size, 'size_mb': round(size / 1048576, 2),
            'ftyp': head[4:12].decode('latin1', 'ignore'),
        }
        i = head.find(b'mvhd')
        if i >= 4:
            b = i - 4
            if head[b + 8] == 0:
                ts = struct.unpack('>I', head[b + 20:b + 24])[0]
                du = struct.unpack('>I', head[b + 24:b + 28])[0]
                info['duration_s'] = round(du / ts, 2) if ts else None
        info['tracks'] = head.count(b'trak') // 2
        # moov 是否在文件头（faststart 生效的标志）
        info['faststart'] = head[:4096].find(b'moov') > 0
        return info
    except Exception as e:
        return {'error': str(e)[:80]}


if __name__ == '__main__':
    import sys
    # 直接 `python app/m3u8_merge.py` 运行时补上父目录
    if __package__ in (None, ''):
        import os
        sys.path.insert(0, os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
    print('ffmpeg 能力:', json.dumps(
        ffmpeg_util.capabilities(), ensure_ascii=False))
    if len(sys.argv) > 1:
        url = sys.argv[1]
        ref = sys.argv[2] if len(sys.argv) > 2 else ''
        out = sys.argv[3] if len(sys.argv) > 3 else 'merged_test.mp4'
        r = asyncio.run(merge_m3u8_to_mp4(url, out, ref))
        print('合并结果:', json.dumps(r, ensure_ascii=False, indent=2))
        if r.get('ok'):
            print('产物:', json.dumps(
                probe_mp4(r['path']), ensure_ascii=False))
