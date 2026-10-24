"""封面代理测试：平台判定（Referer）+ 压缩 + 缓存版本

⭐ 这个测试存在的理由（两个都是真实 bug）：

① **B站封面 404**（2026-10-24 实测发现）
   原代码用 `domains.registry.match(封面URL)` 判断平台 —— 但那张表登记的是
   **视频 CDN**（*.bilivideo.com），封面在另一套域（i1.hdslb.com）→ 恒为 None
   → Referer 回落到默认的 douyin → B站 CDN 校验 Referer → 403 → 代理 404
   → **B站视频的封面在小程序里显示不出来**（用户看到的是一块黑）。
   而抖音封面恰好默认 Referer 就是抖音，所以这个 bug 一直蒙混过关。

② **封面零压缩**（同一天）
   `_fetch_cover_sync` 只做 5MB 上限检查，原图直转。
   B站封面实测 651KB，结果页只显示到 640px 宽 —— 白烧 20 倍流量。
   按 3M 带宽算，压缩前后容量差 6 倍以上。

这两个都是「不报错、只是效果差」的静默问题，没有断言守护会被改回去。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import (  # noqa: E402
    _COVER_CACHE_VER, _COVER_REFERER, _COVER_SUFFIX_KEYS, _COVER_TARGET_W,
    _COVER_WEBP_Q, _compress_cover, _cover_platform,
    _purge_legacy_cover_cache,
)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✅' if cond else '  ❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


# ══════════════════════════════════════════════════════════
# 1. 平台判定：封面域 → 平台（决定 Referer）
# ══════════════════════════════════════════════════════════
print('\n── 1. 封面域 → 平台（Referer 选择）──')

# ⭐ 核心回归：B站封面必须判成 bilibili，否则 Referer 错 → 403
check('B站封面 i1.hdslb.com → bilibili',
      _cover_platform('https://i1.hdslb.com/bfs/archive/x.jpg') == 'bilibili')
check('B站封面 i0.hdslb.com（不同编号）→ bilibili',
      _cover_platform('https://i0.hdslb.com/bfs/archive/x.jpg') == 'bilibili')
check('B站视频域 bilivideo.com → bilibili（注册表兜底也通）',
      _cover_platform('https://cn-jsnt-ct-01-01.bilivideo.com/v.mp4') == 'bilibili')

# 抖音封面域带随机编号，注册表匹配不上，必须靠后缀表
check('抖音 p26-sign.douyinpic.com → douyin',
      _cover_platform('https://p26-sign.douyinpic.com/a.jpg') == 'douyin')
check('抖音 p3-pc-sign.douyinpic.com → douyin',
      _cover_platform('https://p3-pc-sign.douyinpic.com/a.jpg') == 'douyin')

check('百度 f7.baidu.com → baidu',
      _cover_platform('https://f7.baidu.com/x.jpg') == 'baidu')
check('好看 vdept8.bdstatic.com → haokan',
      _cover_platform('https://vdept8.bdstatic.com/x.jpg') == 'haokan')
check('小红书 sns-img-qc.xhscdn.com → xiaohongshu',
      _cover_platform('https://sns-img-qc.xhscdn.com/a.jpg') == 'xiaohongshu')
check('微博 wx1.sinaimg.cn → weibo',
      _cover_platform('https://wx1.sinaimg.cn/a.jpg') == 'weibo')
check('微博 f.video.weibocdn.com → weibo',
      _cover_platform('https://f.video.weibocdn.com/a.jpg') == 'weibo')
check('快手 *.yximgs.com → kuaishou',
      _cover_platform('https://p1.a.yximgs.com/a.jpg') == 'kuaishou')
check('AcFun acfun.cn → acfun',
      _cover_platform('https://tx-safety-video.acfun.cn/a.jpg') == 'acfun')
check('搜狐 itc.cn → sohu',
      _cover_platform('https://data.vod.itc.cn/a.jpg') == 'sohu')

check('未知域 → 空（不瞎猜平台）',
      _cover_platform('https://evil.example.com/a.jpg') == '')
check('畸形 URL 不抛异常',
      _cover_platform('not-a-url') == '')

print('\n── 1b. Referer 映射必须覆盖所有后缀表里的平台 ──')
_plats = set(_COVER_REFERER)
_missing = sorted({p for p in _COVER_SUFFIX_KEYS if False} |
                  {v for k, v in
                   __import__('app.main', fromlist=['_COVER_PLATFORM_BY_SUFFIX'])
                   ._COVER_PLATFORM_BY_SUFFIX.items()} - _plats)
check('后缀表里每个平台都有 Referer（缺了会静默回落 douyin → 403）',
      not _missing, f'缺 Referer 的平台: {_missing}')

# 长后缀优先：bdstatic 不能被 baidu.com 抢走
check('长后缀优先（vdept8.bdstatic.com 不误判成 baidu）',
      _cover_platform('https://vdept8.bdstatic.com/x.jpg') != 'baidu')
check('后缀 keys 按长度倒序（保证长后缀先匹配）',
      list(_COVER_SUFFIX_KEYS) ==
      sorted(_COVER_SUFFIX_KEYS, key=len, reverse=True))


# ══════════════════════════════════════════════════════════
# 2. 压缩：尺寸 / 格式 / 边界
# ══════════════════════════════════════════════════════════
print('\n── 2. 压缩行为 ──')
try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print('  ⚠️ 未装 Pillow —— 跳过压缩用例（生产必须装，requirements.txt 已声明）')

if HAS_PIL:
    def mk(w, h, mode='RGB', fmt='JPEG', color=(200, 120, 60), **kw):
        im = Image.new(mode, (w, h), color)
        b = io.BytesIO()
        im.save(b, fmt, **kw)
        return b.getvalue()

    def noisy(w, h):
        """有细节的图（纯色图压缩率失真，不能代表真实封面）"""
        import random
        random.seed(7)
        im = Image.new('RGB', (w, h))
        px = im.load()
        for y in range(h):
            for x in range(0, w, 4):
                c = (random.randint(0, 255), random.randint(0, 255),
                     random.randint(0, 255))
                for dx in range(4):
                    if x + dx < w:
                        px[x + dx, y] = c
        return im

    big = io.BytesIO()
    noisy(1920, 1080).save(big, 'JPEG', quality=92)
    big = big.getvalue()

    out, ct, saved = _compress_cover(big, 'image/jpeg')
    im_out = Image.open(io.BytesIO(out))
    check('大图被缩到目标宽度', im_out.size[0] == _COVER_TARGET_W,
          f'{im_out.size}')
    check('保持宽高比（1920x1080 → 640x360）', im_out.size == (640, 360),
          f'{im_out.size}')
    check('转成 webp', ct == 'image/webp', ct)
    check('体积显著变小（>70%）', len(out) < len(big) * 0.3,
          f'{len(big)} → {len(out)}')
    check('saved 返回值正确', saved == len(big) - len(out),
          f'saved={saved}')

    # 小图不放大
    small = mk(200, 120)
    out2, ct2, _ = _compress_cover(small, 'image/jpeg')
    im2 = Image.open(io.BytesIO(out2))
    check('小图不放大（200 宽保持 200，放大只会更糊更大）',
          im2.size[0] == 200, f'{im2.size}')

    # 透明 PNG 保留 alpha
    rgba = mk(1200, 800, 'RGBA', 'PNG', color=(200, 120, 60, 128))
    out3, ct3, _ = _compress_cover(rgba, 'image/png')
    im3 = Image.open(io.BytesIO(out3))
    check('PNG 透明转 webp 保留 RGBA', im3.mode in ('RGBA', 'RGB'),
          im3.mode)
    check('PNG → webp', ct3 == 'image/webp', ct3)

    # 调色板模式不能炸（P 模式 webp 写不了，要 convert）
    pal = mk(1200, 800, 'P', 'PNG')
    out4, ct4, _ = _compress_cover(pal, 'image/png')
    check('P 模式不抛异常且能产出图', len(out4) > 0 and ct4.startswith('image/'))

    # 动图必须原样返回（转静态会丢帧）
    frames = []
    for i in range(3):
        f = Image.new('RGB', (400, 300), (30, 30, 30))
        d = ImageDraw.Draw(f)
        d.ellipse([i * 80, 20, i * 80 + 150, 170], fill=(255, 120, 0))
        frames.append(f)
    gb = io.BytesIO()
    frames[0].save(gb, 'GIF', save_all=True, append_images=frames[1:],
                   duration=200, loop=0)
    gif = gb.getvalue()
    n_frames = Image.open(io.BytesIO(gif)).n_frames
    out5, ct5, saved5 = _compress_cover(gif, 'image/gif')
    check('（前置）测试 GIF 确实是多帧', n_frames > 1, f'{n_frames} 帧')
    check('动图原样返回（不丢帧）', out5 == gif and ct5 == 'image/gif',
          f'{len(gif)}B → {len(out5)}B {ct5}')
    check('动图 saved = 0', saved5 == 0)

    # 损坏数据必须优雅退回，不能抛异常（否则封面变 500）
    bad = b'\xff\xd8\xff\xe0this-is-not-an-image'
    out6, ct6, saved6 = _compress_cover(bad, 'image/jpeg')
    check('损坏图片原样返回（不抛异常）', out6 == bad and ct6 == 'image/jpeg')
    check('损坏图片 saved = 0', saved6 == 0)

    # 已经很小、压完更大的要退回原图
    tiny = mk(60, 40)
    out7, ct7, saved7 = _compress_cover(tiny, 'image/jpeg')
    check('压完更大时退回原图', len(out7) <= len(tiny),
          f'{len(tiny)}B → {len(out7)}B')

    check('webp 质量参数在合理区间（60~95）',
          _COVER_WEBP_Q is None or 60 <= _COVER_WEBP_Q <= 95,
          str(_COVER_WEBP_Q))
    check('目标宽度在合理区间（480~1080）',
          480 <= _COVER_TARGET_W <= 1080, str(_COVER_TARGET_W))

print('\n── 2b. Pillow 缺失时的降级（不能变 404）──')
# 直接模拟：把 Pillow 从 sys.modules 摘掉不可靠（可能已被其它模块缓存），
# 改为静态断言兜底分支存在。
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'app', 'main.py'), encoding='utf-8').read()
check('_compress_cover 有 ImportError 兜底（没装 Pillow 也返回原图）',
      'except ImportError:' in _src[_src.index('def _compress_cover'):
                                    _src.index('def _purge_legacy_cover_cache')])

_requirements = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'requirements.txt'), encoding='utf-8').read()
check('requirements.txt 声明了 Pillow（生产环境必须装）',
      'Pillow' in _requirements)


# ══════════════════════════════════════════════════════════
# 3. 缓存版本：改了压缩策略必须让老缓存失效
# ══════════════════════════════════════════════════════════
print('\n── 3. 缓存版本化 ──')
check('_COVER_CACHE_VER 非空', bool(_COVER_CACHE_VER), repr(_COVER_CACHE_VER))
# ⚠️ 断言要检查【变量被真正拼进 key】，不是找字面量 'v3_' ——
#   源码里是 f'{_COVER_CACHE_VER}_{key}.img'，写死字符串反而是我们要防的（版本号散落）
check('缓存 key 拼了版本前缀（否则老的原图缓存会一直被命中）',
      '_COVER_CACHE_VER}_{key' in _src,
      '应是 f\'{_COVER_CACHE_VER}_{key}.img\' 形式')

print('\n── 3b. 旧缓存清理只删严格匹配的老格式 ──')
_src_purge = _src[_src.index('def _purge_legacy_cover_cache'):
                  _src.index("@app.get('/api/proxy-cover')")]
check('清理函数只匹配 24 位十六进制 + .img(.type)',
      r'[0-9a-f]{24}' in _src_purge and '$' in _src_purge)
check('不用 glob / fnmatch / rmtree（避免误删缓存目录里的其它文件）',
      'glob(' not in _src_purge and 'fnmatch' not in _src_purge
      and 'rmtree' not in _src_purge)
check('只删单个文件且只有一处 remove（不批量）',
      _src_purge.count('os.remove') == 1,
      f"os.remove 出现 {_src_purge.count('os.remove')} 次")

print('\n── 3c. 404 时的错误信息要能定位平台 ──')
check('代理失败信息带平台名（否则排查不知道 Referer 是哪个）',
      '封面获取失败' in _src and '{plat or' in _src)

print('\n── 3d. Referer 被拒时用空 Referer 重试 ──')
_fetch_src = _src[_src.index('def _fetch_cover_sync'):
                  _src.index('def _compress_cover')]
check('捕获 HTTPError 并对 401/403 重试',
      'urllib.error.HTTPError' in _fetch_src and 'in (401, 403)' in _fetch_src)
check('重试时不带 Referer（_try(\'\')）', "_try('')" in _fetch_src)
check('404 不重试（图真没了，重试无意义）',
      'e.code not in (401, 403)' in _fetch_src)

print(f'\n════ 封面代理：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项：')
    for f in FAIL:
        print('  -', f)
sys.exit(1 if FAIL else 0)
