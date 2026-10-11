#!/usr/bin/env python3
"""首页四套皮肤渲染对照图（纯代码绘制，零依赖）——改完 UI 用来肉眼验收"""
import os, struct, zlib, math, sys

W, H = 340, 720
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'miniapp', '_preview')

SKINS = {
 'classic': dict(page='#F7F2EA', card='#FFFFFF', soft='#F3EDE4', line='#E2D9CB',
                 ink900='#2A1B0C', ink700='#5A4A3A', ink500='#8B7D6E', ink300='#B3A695',
                 brand='#D97A26', brand3='#F2C879', soft_brand='#FBEEDA',
                 h1='#33210F', h2='#3D2812', h3='#291A0C'),
 'dark':    dict(page='#0E0E11', card='#17171C', soft='#1F1F26', line='#2C2C34',
                 ink900='#F2EFE9', ink700='#C4BFB6', ink500='#948D84', ink300='#6B655D',
                 brand='#D8B98E', brand3='#F0DDBE', soft_brand='#2A2620',
                 h1='#1A1A20', h2='#141419', h3='#0B0B0E'),
 'jade':    dict(page='#0C1210', card='#121A17', soft='#16201C', line='#23302B',
                 ink900='#E8F0EC', ink700='#B9C9C2', ink500='#8A9A93', ink300='#64736C',
                 brand='#2E9E7B', brand3='#6FD3B2', soft_brand='#14261F',
                 h1='#12241E', h2='#0D1A16', h3='#081310'),
 'sakura':  dict(page='#FBF6F8', card='#FFFFFF', soft='#F7ECF1', line='#EBD9E1',
                 ink900='#2B1B22', ink700='#5A414B', ink500='#9A8290', ink300='#C4AAB5',
                 brand='#E85D8F', brand3='#FFA8C4', soft_brand='#FDEEF4',
                 h1='#5C2440', h2='#43182E', h3='#360f24'),
}

def hx(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

class C:
    def __init__(s, w, h, bg):
        s.w, s.h = w, h
        s.px = bytearray(bytes(bg) * (w * h))
    def rect(s, x0, y0, x1, y1, col, r=0, alpha=1.0):
        col = col if len(col) == 3 else col[:3]
        y_lo, y_hi = max(0, int(y0)), min(s.h, int(y1))
        x_lo, x_hi = max(0, int(x0)), min(s.w, int(x1))
        if y_hi <= y_lo or x_hi <= x_lo:
            return
        for y in range(y_lo, y_hi):
            for x in range(x_lo, x_hi):
                if r > 0:
                    cx = min(max(x, x0 + r), x1 - r - 1)
                    cy = min(max(y, y0 + r), y1 - r - 1)
                    if math.hypot(x - cx, y - cy) > r:
                        continue
                i = (y * s.w + x) * 4
                if i + 3 > len(s.px):
                    continue
                d = s.px[i:i + 3]
                s.px[i:i + 3] = bytes(int(col[k] * alpha + d[k] * (1 - alpha)) for k in range(3))
    def vgrad(s, x0, y0, x1, y1, c1, c2):
        a, b = hx(c1), hx(c2)
        h = max(1, int(y1 - y0))
        for y in range(max(0, int(y0)), min(s.h, int(y1))):  # noqa
            t = (y - y0) / h
            row = mix(a, b, t)
            for x in range(max(0, int(x0)), min(s.w, int(x1))):
                i = (y * s.w + x) * 4
                if i + 3 <= len(s.px):
                    s.px[i:i + 3] = bytes(row)
    def card(s, x0, y0, x1, y1, bg, r=14, border=None, shadow=True):
        if shadow:
            for k in range(5):
                s.rect(x0 - 2 + k, y1 + k, x1 + 2 - k, y1 + k + 1, (0, 0, 0), 0, 0.05)
        s.rect(x0, y0, x1, y1, hx(bg), r)
        if border:
            s.rect(x0, y0, x1, y1, hx(border), r, 0.9)
    def write(s, path):
        raw = bytearray()
        for y in range(s.h):
            raw.append(0)
            raw += s.px[y * s.w * 4:(y + 1) * s.w * 4]
        def ch(t, d):
            c = struct.pack('>I', len(d)) + t + d
            return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        png = b'\x89PNG\r\n\x1a\n'
        png += ch(b'IHDR', struct.pack('>IIBBBBB', s.w, s.h, 8, 6, 0, 0, 0))
        png += ch(b'IDAT', zlib.compress(bytes(raw), 9)) + ch(b'IEND', b'')
        open(path, 'wb').write(png)

# 极简 5x7 点阵字体（只做 ASCII，够标注文字）
FONT = {
'A':["01110","10001","10001","11111","10001","10001","10001"],
'B':["11110","10001","11110","10001","10001","10001","11110"],
'C':["01110","10001","10000","10000","10000","10001","01110"],
'D':["11110","10001","10001","10001","10001","10001","11110"],
'E':["11111","10000","11110","10000","10000","10000","11111"],
'F':["11111","10000","11110","10000","10000","10000","10000"],
'G':["01110","10001","10000","10111","10001","10001","01111"],
'H':["10001","10001","11111","10001","10001","10001","10001"],
'I':["11111","00100","00100","00100","00100","00100","11111"],
'J':["00111","00010","00010","00010","00010","10010","01100"],
'K':["10001","10010","11100","10010","10001","10001","10001"],
'L':["10000","10000","10000","10000","10000","10000","11111"],
'M':["10001","11011","10101","10001","10001","10001","10001"],
'N':["10001","11001","10101","10011","10001","10001","10001"],
'O':["01110","10001","10001","10001","10001","10001","01110"],
'P':["11110","10001","10001","11110","10000","10000","10000"],
'Q':["01110","10001","10001","10001","10101","10011","01111"],
'R':["11110","10001","10001","11110","10100","10010","10001"],
'S':["01111","10000","10000","01110","00001","00001","11110"],
'T':["11111","00100","00100","00100","00100","00100","00100"],
'U':["10001","10001","10001","10001","10001","10001","01110"],
'V':["10001","10001","10001","10001","10001","01010","00100"],
'W':["10001","10001","10001","10101","10101","11011","10001"],
'X':["10001","10001","01010","00100","01010","10001","10001"],
'Y':["10001","10001","01010","00100","00100","00100","00100"],
'Z':["11111","00001","00010","00100","01000","10000","11111"],
'0':["01110","10001","10011","10101","11001","10001","01110"],
'1':["00100","01100","00100","00100","00100","00100","01110"],
'2':["01110","10001","00001","00010","00100","01000","11111"],
'3':["11111","00010","00100","00010","00001","10001","01110"],
'4':["00010","00110","01010","10010","11111","00010","00010"],
'5':["11111","10000","11110","00001","00001","10001","01110"],
'6':["00110","01000","10000","11110","10001","10001","01110"],
'7':["11111","00001","00010","00100","01000","01000","01000"],
'8':["01110","10001","10001","01110","10001","10001","01110"],
'9':["01110","10001","10001","01111","00001","00010","01100"],
' ':["00000"]*7, '.':["00000","00000","00000","00000","00000","01100","01100"],
'-':["00000","00000","00000","11111","00000","00000","00000"],
'/':["00001","00010","00010","00100","01000","01000","10000"],
}

def text(cv, s, x, y, col, sc=1):
    for ch in s.upper():
        g = FONT.get(ch, FONT[' '])
        for r, row in enumerate(g):
            for cc, b in enumerate(row):
                if b == '1':
                    cv.rect(x + cc * sc, y + r * sc, x + (cc + 1) * sc, y + (r + 1) * sc, hx(col))
        x += (len(g[0]) + 1) * sc
    return x

def render(name, k):
    cv = C(W, H, hx(k['page']))
    M = 12
    # hero：同色系三段渐变（修后）
    cv.vgrad(0, 0, W, 150, k['h1'], k['h3'])
    text(cv, 'CREATORBOX', M + 2, 16, '#FFFFFF', 1)
    cv.rect(W - 92, 14, W - M, 36, hx(k['brand3']), 11, 0.16)
    text(cv, '9.9 VIP', W - 84, 21, k['brand3'], 1)
    text(cv, 'GO WATERMARK FREE', M + 2, 44, '#FFFFFF', 2)
    text(cv, 'DOUYIN  BILIBILI  8 APPS', M + 2, 76, k['brand3'], 1)
    # 输入卡（上提浮起）
    cv.card(M, 118, W - M, 300, k['card'], 14, k['line'])
    cv.rect(M + 12, 132, W - M - 12, 196, hx(k['soft']), 10)
    text(cv, 'PASTE LINK HERE', M + 22, 152, k['ink300'], 1)
    text(cv, 'CONTENT FROM PUBLIC APIS', M + 12, 206, k['ink300'], 1)
    cv.rect(M + 12, 222, W - M - 12, 262, hx(k['brand']), 12)
    text(cv, 'START PARSE', M + 60, 236, k['ink900'], 1)
    cv.rect(M + 12, 270, M + 92, 292, hx(k['soft']), 10, 0)
    cv.rect(M + 12, 270, M + 92, 292, hx(k['line']), 10)
    cv.rect(M + 100, 270, W - M - 12, 292, hx(k['soft']), 10, 0)
    cv.rect(M + 100, 270, W - M - 12, 292, hx(k['line']), 10)
    # 额度卡（同族，靠间距分开）
    cv.card(M, 312, W - M, 396, k['card'], 14, k['line'])
    for i, (lab, big) in enumerate([('UNLIMITED', 'INF'), ('SAVED', '0/2'), ('QUALITY', '720P')]):
        cx = M + (W - 2 * M) * (i + 0.5) / 3
        col = k['brand3'] if i == 0 else k['ink900']
        wlen = len(big) * 6 * 2
        text(cv, big, cx - wlen / 2, 330, col, 2)
        text(cv, lab, cx - len(lab) * 3, 368, k['ink500'], 1)
        if i < 2:
            cv.rect(cx + (W - 2 * M) / 6, 330, cx + (W - 2 * M) / 6 + 1, 380, hx(k['line']))
    # 工具格
    cv.card(M, 408, W - M, 508, k['card'], 14, k['line'])
    for i in range(4):
        cx = M + 14 + i * ((W - 2 * M - 28) / 4)
        s = (W - 2 * M - 28) / 4
        cv.rect(cx, 424, cx + s - 12, 424 + 40, hx(k['brand']), 12, 0.16)
        cv.rect(cx + s / 2 - 12, 434, cx + s / 2 - 2, 456, hx(k['brand3']))
        cv.rect(cx + s / 2 - 9, 440, cx + s / 2 - 4, 450, hx(k['brand3']))
    # 平台标签卡（4 列栅格）
    cv.card(M, 520, W - M, 616, k['card'], 14, k['line'])
    text(cv, 'SUPPORTED APPS', M + 14, 536, k['ink500'], 1)
    cv.rect(W - M - 88, 532, W - M - 14, 550, hx(k['soft_brand']), 8)
    cv.rect(W - M - 80, 539, W - M - 74, 545, hx(k['brand']))
    text(cv, 'VERIFIED', W - M - 68, 536, k['brand'] if name != 'classic' else '#1B8A5A', 1)
    names = ['TIKTOK', 'BILIBILI', 'HAOKAN', 'WEIBO', 'XHS', 'KUAISHOU', 'SOUHU', 'ACFUN']
    for i, nm in enumerate(names):
        r_, c_ = divmod(i, 4)
        x0 = M + 14 + c_ * ((W - 2 * M - 28) / 4)
        y0 = 560 + r_ * 30
        cv.rect(x0, y0, x0 + (W - 2 * M - 28) / 4 - 8, y0 + 24, hx(k['soft']), 7)
        tw = len(nm) * 6
        text(cv, nm, x0 + ((W - 2 * M - 28) / 4 - 8 - tw) / 2, y0 + 9, k['ink700'], 1)
    text(cv, 'USER RESPONSIBILITY NOTICE', M + 8, 640, k['ink300'], 1)
    # tabBar
    cv.rect(0, H - 46, W, H, hx(k['card']))
    cv.rect(0, H - 46, W, H - 45, hx(k['line']))
    for i, nm in enumerate(['PARSE', 'TOOLS', 'RANK', 'LIB', 'VIP']):
        cx = W * (i + 0.5) / 5
        col = k['brand'] if i == 0 else k['ink500']
        cv.rect(cx - 6, H - 32, cx + 6, H - 20, hx(col), 3)
        text(cv, nm, cx - len(nm) * 3, H - 14, col, 1)
    return cv

def main():
    os.makedirs(OUT, exist_ok=True)
    order = ['classic', 'dark', 'jade', 'sakura']
    for n in order:
        cv = render(n, SKINS[n])
        p = os.path.join(OUT, 'home_%s.png' % n)
        cv.write(p)
        print(p)
    # 拼 4联对照
    gap = 10
    W2 = W * 4 + gap * 3
    sheet = C(W2, H + 26, (26, 24, 22))
    for i, n in enumerate(order):
        sub = render(n, SKINS[n])
        x0 = i * (W + gap)
        for y in range(H):
            for x in range(W):
                si = (y * W + x) * 4
                di = (y * W2 + x0 + x) * 4
                sheet.px[di:di + 4] = sub.px[si:si + 4]
        text(sheet, n.upper(), x0 + 6, H + 8, '#D8CFC0', 2)
    p = os.path.join(OUT, 'home_all.png')
    sheet.write(p)
    print('四联对照 →', p)

if __name__ == '__main__':
    main()
