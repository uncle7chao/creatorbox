"""平台图标合成验收：4 皮肤行 × 8 平台列，贴真实 tag 底色"""
import os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_tabbar_icons import SIZE
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'miniapp', 'images', 'plat')

def read_png_rgba(path):
    d = open(path, 'rb').read(); pos = 8; w = h = 0; idat = b''
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]; tag = d[pos+4:pos+8]
        body = d[pos+8:pos+8+ln]
        if tag == b'IHDR': w, h = struct.unpack('>II', body[:8])
        elif tag == b'IDAT': idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat); st = w*4+1
    return w, h, [raw[y*st+1:(y+1)*st] for y in range(h)]

PLATS = ['douyin','bilibili','haokan','weibo','acfun','xhs','kuaishou','sohu']
SKINS = {
  'classic': dict(soft=(243,237,228,255), card=(255,255,255,255)),
  'dark':    dict(soft=(31,31,38,255),   card=(23,23,28,255)),
  'jade':    dict(soft=(22,32,28,255),   card=(18,26,23,255)),
  'sakura':  dict(soft=(247,236,241,255),card=(255,255,255,255)),
}
TILE, GAP, ROW = 64, 10, 4
IW = 8*TILE + 9*GAP
IH = 4*(TILE+GAP) + GAP
flat = bytearray()
for _ in range(IW*IH): flat += bytes((255,255,255,255))
for ri,(skin,k) in enumerate(SKINS.items()):
    y0 = GAP + ri*(TILE+GAP)
    for ci,plat in enumerate(PLATS):
        x0 = GAP + ci*(TILE+GAP)
        for y in range(TILE):
            for x in range(TILE):
                i = ((y0+y)*IW + x0+x)*4
                flat[i:i+4] = bytes(k['soft'] if ri==0 or ri==2 or ri==3 else k['soft'])
        w,h,rows = read_png_rgba(os.path.join(OUT, f'{plat}-{skin}.png'))
        for y in range(h):
            for x in range(w):
                p = rows[y][x*4:x*4+4]
                if p[3]==0: continue
                a = p[3]/255
                X = x0 + x + (TILE-SIZE)//2; Y = y0 + y + (TILE-SIZE)//2
                i = (Y*IW+X)*4; d = flat[i:i+4]
                flat[i:i+4] = bytes((int(p[0]*a+d[0]*(1-a)),int(p[1]*a+d[1]*(1-a)),
                                     int(p[2]*a+d[2]*(1-a)),255))
raw = bytearray()
for y in range(IH):
    raw.append(0); raw += flat[y*IW*4:(y+1)*IW*4]
def ch(t,d):
    c = struct.pack('>I',len(d))+t+d
    return c + struct.pack('>I', zlib.crc32(t+d)&0xffffffff)
png = b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', IW, IH, 8, 6, 0, 0, 0))
png += ch(b'IDAT', zlib.compress(bytes(raw),9)) + ch(b'IEND', b'')
open(os.path.join(OUT,'_sheet.png'),'wb').write(png)
print('_sheet.png', IW, 'x', IH, '（行序：classic/dark/jade/sakura）')
