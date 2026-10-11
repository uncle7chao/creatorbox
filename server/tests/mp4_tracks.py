"""微博1080P 完整性与音轨核查

三个疑点：
1. 分辨率 1078x1744（比例接近 9:16 竖屏）—— 但 tkhd 宽高是"显示尺寸"，
   真实编码分辨率要看 avc1 box的 codedWidth/Height
2. trak 盒数 = 1 → 只有一个轨道，**可能没有音轨**（无声视频？）
3. 112MB / 319秒≈ 2.8 Mbps，1080P 竖屏合理
"""
import json
import ssl
import struct
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OID = '1034:5343195622473745'
REF = f'https://h5.video.weibo.com/show/{OID}'

PATH = sys.argv[1] if len(sys.argv) > 1 else 'weibo_1080p.mp4'


def walk(buf, off, end):
    out = []
    while off + 8 <= end:
        try:
            sz = struct.unpack('>I', buf[off:off + 4])[0]
        except struct.error:
            break
        typ = buf[off + 4:off + 8]
        if sz == 1:
            if off + 16 > end:
                break
            sz = struct.unpack('>Q', buf[off + 8:off + 16])[0]
        elif sz == 0:
            sz = end - off
        if sz < 8:
            break
        out.append((typ, off, sz))
        if typ in (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'edts'):
            out += walk(buf, off + 8, off + sz)
        off += sz
    return out


def analyze(path):
    d = open(path, 'rb').read()
    boxes = walk(d, 0, len(d))
    print(f'文件: {path}')
    print(f'大小: {len(d)} 字节 ({len(d) / 1048576:.2f} MB)')
    print(f'顶层盒: {sorted({t[0].decode("latin1") for t in boxes})}')

    ts = dur = None
    for typ, off, sz in boxes:
        if typ == b'mvhd':
            if d[off + 8] == 0:
                ts = struct.unpack('>I', d[off + 20:off + 24])[0]
                dur = struct.unpack('>I', d[off + 24:off + 28])[0]
    if ts:
        print(f'mvhd: {dur / ts:.2f}s timescale={ts}')

    n = 0
    for typ, off, sz in boxes:
        if typ != b'trak':
            continue
        n += 1
        handler = None
        w = h = 0
        cwd = chd = None
        for t2, o2, s2 in walk(d, off + 8, off + sz):
            if t2 == b'hdlr':
                handler = d[o2 + 16:o2 + 20].decode('latin1', 'ignore')
            if t2 == b'tkhd':
                w = struct.unpack('>I', d[o2 + 84:o2 + 88])[0] >> 16
                h = struct.unpack('>I', d[o2 + 88:o2 + 92])[0] >> 16
            if t2 in (b'avc1', b'avc3', b'hev1', b'mp4v'):
                cwd = struct.unpack('>H', d[o2 + 24:o2 + 26])[0]
                chd = struct.unpack('>H', d[o2 + 26:o2 + 28])[0]
        kind = {'vide': '视频', 'soun': '音频'}.get(handler, handler)
        print(f'  trak#{n}: handler={kind} 显示尺寸={w}x{h} '
              f'编码尺寸={cwd or "?"}x{chd or "?"}')

    codecs = [b'avc1', b'avc3', b'mp4a', b'hev1', b'hev1', b'Opus']
    print('编解码 box: ' + ', '.join(
        f'{c.decode()}' for c in codecs if c in d))
    if b'mp4a' in d:
        print('  ✅ 含AAC 音频轨 (mp4a)')
    else:
        print('  ⚠️ 未找到 mp4a —— 疑似无音轨')
    return n


if __name__ == '__main__':
    analyze(PATH)
