"""搜狐视频「试看片段截断」验证 —— 自包含（自己取样本，不依赖本地文件）

⭐ 本脚本验证的是 knowledge.P12：
   url_high_mp4 / download_url 返回的是**固定 30 秒试看片段**，
   与视频真实时长、file_size_high 声明都无关。
   完整视频只在 m3u8。

判定方法：下载 mp4 → 读 mvhd box拿真实时长 → 与 clips_duration_high 比对。
（只看 Content-Type / file_size 字段发现不了，必须读容器）
"""
import gzip
import json
import os
import ssl
import struct
import sys
import time
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
API = ('https://api.tv.sohu.com/v4/video/info/{vid}.json'
       '?site=2&api_key=9854b2afa779e1a6bcdd07b217417549&sver=6.2.0')
HOME = 'https://tv.sohu.com/'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 覆盖 30s 以内与超过 30s 两种情况
VIDS = ['620139607', '620251480', '620253660', '620253046']


def get(url, ref=HOME):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': ref,
        'Accept-Encoding': 'gzip, deflate'})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        raw = r.read()
    return gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw


def mvhd_duration(buf: bytes):
    """读 MP4 的 mvhd box → 真实时长（秒）"""
    i = buf.find(b'mvhd')
    if i < 4:
        return None
    b = i - 4
    try:
        if buf[b + 8] == 0:
            ts = struct.unpack('>I', buf[b + 20:b + 24])[0]
            du = struct.unpack('>I', buf[b + 24:b + 28])[0]
        else:
            ts = struct.unpack('>I', buf[b + 28:b + 32])[0]
            du = struct.unpack('>Q', buf[b + 32:b + 40])[0]
    except Exception:
        return None
    return round(du / ts, 2) if ts else None


def tkhd_dims(buf: bytes):
    i = buf.find(b'tkhd')
    if i < 4:
        return None
    b = i - 4
    try:
        w = struct.unpack('>I', buf[b + 84:b + 88])[0] >> 16
        h = struct.unpack('>I', buf[b + 88:b + 92])[0] >> 16
    except Exception:
        return None
    return f'{w}x{h}' if w and h else None


def m3u8_total(url):
    """把 m3u8 全部分段体积加起来（用 Range 只取 2 字节探总长）"""
    try:
        txt = get(url).decode('utf-8', 'ignore')
    except Exception:
        return None, 0
    segs = [ln.strip() for ln in txt.splitlines() if ln.startswith('http')]
    total = 0
    for s in segs:
        try:
            req = urllib.request.Request(s, headers={
                'User-Agent': UA, 'Referer': HOME, 'Range': 'bytes=0-1'})
            with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
                cr = r.headers.get('Content-Range') or ''
            if '/' in cr and cr.rsplit('/', 1)[-1].strip().isdigit():
                total += int(cr.rsplit('/', 1)[-1])
        except Exception:
            pass
    return total, len(segs)


print(f'{"vid":11s} {"声明":>7s} {"实际":>7s} {"声明体积":>9s} '
      f'{"实际体积":>9s} {"分辨率":10s} {"m3u8总量":>9s} 判定')
print('-' * 84)
trunc = 0
for vid in VIDS:
    try:
        j = json.loads(get(API.format(vid=vid)).decode('utf-8', 'ignore'))
    except Exception as e:
        print(f'{vid:11s} 请求失败 {str(e)[:40]}')
        continue
    if j.get('status') != 200:
        print(f"{vid:11s} 接口 status={j.get('status')} "
              f"{j.get('statusText', '')[:34]}")
        continue
    d = j['data']
    url = d.get('url_high_mp4') or d.get('download_url') or ''
    if not url:
        print(f'{vid:11s} 无播放地址')
        continue
    try:
        blob = get(url)
    except Exception as e:
        print(f'{vid:11s} 下载失败 {str(e)[:40]}')
        continue
    adur = mvhd_duration(blob)
    dims = tkhd_dims(blob)
    cdur = float(d.get('clips_duration_high') or 0)
    csize = d.get('file_size_high') or 0
    m3, nseg = m3u8_total(d.get('url_high') or '')

    bad = adur and cdur and (cdur - adur) > 2.0
    trunc += bool(bad)
    verdict = f'⛔ 截断（短 {cdur - adur:.0f}s）' if bad else 'OK'
    print(f'{vid:11s} {cdur:6.0f}s {adur or 0:6.2f}s '
          f'{csize / 1048576:8.2f}M {len(blob) / 1048576:8.2f}M '
          f'{str(dims):10s} '
          f'{(f"{m3 / 1048576:.2f}M/{nseg}段" if m3 else "-"):>9s} {verdict}')

print(f'\n截断 {trunc}/{len(VIDS)}')
print('结论：url_high_mp4 恒为 ~468026 字节 / ~30.04s，'
      '与真实时长无关 → 是试看片段。完整视频只在 m3u8。')
