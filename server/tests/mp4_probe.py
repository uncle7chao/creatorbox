"""验证：url_high_mp4 是固定体积的截断预览（读mvhd 时长 + tkhd 分辨率）"""
import os
import struct
import sys


def walk(buf, off, end, depth=0):
    out = []
    while off + 8 <= end:
        sz = struct.unpack('>I', buf[off:off + 4])[0]
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
            out += walk(buf, off + 8, off + sz, depth + 1)
        off += sz
    return out


def inspect(path):
    d = open(path, 'rb').read()
    res = {'size': len(d), 'tracks': 0}
    for typ, off, sz in walk(d, 0, len(d)):
        if typ == b'mvhd':
            ver = d[off + 8]
            if ver == 0:
                ts = struct.unpack('>I', d[off + 20:off + 24])[0]
                dur = struct.unpack('>I', d[off + 24:off + 28])[0]
            else:
                ts = struct.unpack('>I', d[off + 28:off + 32])[0]
                dur = struct.unpack('>Q', d[off + 32:off + 40])[0]
            res['timescale'] = ts
            res['duration_s'] = round(dur / ts, 2) if ts else None
        if typ == b'tkhd':
            res['tracks'] += 1
            w = struct.unpack('>I', d[off + 84:off + 88])[0] >> 16
            h = struct.unpack('>I', d[off + 88:off + 92])[0] >> 16
            ver = d[off + 8]
            if ver == 0:
                td = struct.unpack('>I', d[off + 28:off + 32])[0]
            else:
                td = struct.unpack('>Q', d[off + 36:off + 44])[0]
            res.setdefault('track_dims', []).append(f'{w}x{h}')
            res.setdefault('track_dur_s', []).append(
                round(td / res.get('timescale', 1), 2))
    return res


if __name__ == '__main__':
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print(f'{p}: 不存在')
            continue
        r = inspect(p)
        print(f"{os.path.basename(p)}")
        print(f"   size        : {r['size']} bytes "
              f"({r['size']/1048576:.3f} MB)")
        print(f"   mvhd 时长   : {r.get('duration_s')}s  "
              f"(timescale={r.get('timescale')})")
        print(f"   trak 数     : {r['tracks']}")
        print(f"   各轨分辨率  : {r.get('track_dims')}")
        print(f"   各轨时长    : {r.get('track_dur_s')}")
