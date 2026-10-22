"""资源URL 协议升级测试（app/url_scheme.py）

为什么这个必须有测试：
  平台 CDN 返回 http:// 时，小程序会**静默拒绝加载**（图片空白/视频黑屏），
  而接口 200、日志正常 —— 不写断言，下一个人很容易在客户端
  加个容错分支把它「绕过去」，反而把问题散到三端。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.url_scheme import (  # noqa: E402
    https_url, upgrade_result, count_http, EXEMPT_HOSTS)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✅' if cond else '  ❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


print('\n── 单个URL ──')
check('http → https', https_url('http://a.com/x.jpg') == 'https://a.com/x.jpg')
check('https 保持不变', https_url('https://a.com/x.jpg') == 'https://a.com/x.jpg')
check('None 原样返回（不编造）', https_url(None) is None)
check('空串原样返回', https_url('') == '')
check('非 URL 字符串不动', https_url('cb_local_1.jpg') == 'cb_local_1.jpg')
check('带 query 的 URL 保留 query',
      https_url('http://a.com/x?b=1&c=2') == 'https://a.com/x?b=1&c=2')
check('带端口的 URL 保留端口',
      https_url('http://cdn:8080/a.mp4') == 'https://cdn:8080/a.mp4')
check('只升级第一个 http（不会把 https 变 httpss）',
      https_url('https://a.com/?u=http://x') == 'https://a.com/?u=http://x')

print('\n── 字段覆盖 ──')
r = upgrade_result({'video_url': 'http://a.com/v.mp4',
                    'cover': 'http://a.com/c.jpg',
                    'music_url': 'http://a.com/m.mp3',
                    'subtitle_url': 'http://a.com/s.vtt'})
check('video_url 升级', r['video_url'].startswith('https://'))
check('cover 升级', r['cover'].startswith('https://'))
check('music_url 升级', r['music_url'].startswith('https://'))
check('subtitle_url 升级', r['subtitle_url'].startswith('https://'))

print('\n── 溯源链接不该被改（语义不同）──')
r = upgrade_result({'page_url': 'http://a.com/p',
                    'short_url': 'http://a.com/s'})
check('page_url 保持原样（来源链接要与原平台一致）',
      r['page_url'] == 'http://a.com/p', r['page_url'])
check('short_url 保持原样', r['short_url'] == 'http://a.com/s')

print('\n── 列表字段 ──')
r = upgrade_result({'options': [{'url': 'http://a.com/1.mp4'},
                                {'url': 'https://a.com/2.mp4'}]})
check('options[].url 升级', r['options'][0]['url'].startswith('https://'))
check('已是 https 的不动', r['options'][1]['url'].startswith('https://'))

r = upgrade_result({'images': [{'url': 'http://a.com/1.jpg'}]})
check('images[].url 升级', r['images'][0]['url'].startswith('https://'))

r = upgrade_result({'options': [{'urls': ['http://a.com/1.mp4',
                                          'http://a.com/2.mp4']}]})
check('分层备选 urls[] 也升级',
      all(u.startswith('https://') for u in r['options'][0]['urls']))

r = upgrade_result({'options': [{'backups': [{'url': 'http://a.com/b.mp4'}]}]})
check('backups[] 里的 url 也升级',
      r['options'][0]['backups'][0]['url'].startswith('https://'))

r = upgrade_result({'options': [{'link': 'http://a.com/l.mp4'}]})
check('link 别名字段也升级', r['options'][0]['link'].startswith('https://'))

print('\n── 畸形输入不能崩 ──')
check('None 入参安全', upgrade_result(None) is None)
check('非 dict 安全', upgrade_result('x') == 'x')
check('空对象安全', upgrade_result({}) == {})
check('options 为 null 安全',
      upgrade_result({'options': None})['options'] is None)
check('options 内非 dict 元素不崩',
      upgrade_result({'options': ['x', 1, None]}) is not None)
check('images 为字符串不崩',
      upgrade_result({'images': 'http://a.com/1.jpg'}) is not None)

print('\n── 残留自检（这是「新增字段漏了」的哨兵）──')
r = upgrade_result({'video_url': 'http://a.com/v.mp4',
                    'cover': 'http://a.com/c.jpg',
                    'options': [{'url': 'http://a.com/1.mp4'}]})
check('升级后残留 http 数为 0', count_http(r) == 0, f'实得 {count_http(r)}')
check('未处理时能数出来（哨兵有效）',
      count_http({'video_url': 'http://a.com/v.mp4'}) == 1)

print('\n── 豁免机制（当前应为空）──')
check('EXEMPT_HOSTS默认为空（不预先放行任何域）',
      isinstance(EXEMPT_HOSTS, tuple) and len(EXEMPT_HOSTS) == 0,
      str(EXEMPT_HOSTS))

print('\n── 幂等（重复调用不产生 httpss）──')
r = {'video_url': 'http://a.com/v.mp4'}
r = upgrade_result(r)
r = upgrade_result(r)
r = upgrade_result(r)
check('连跑三次仍是正常 https', r['video_url'] == 'https://a.com/v.mp4',
      r['video_url'])

print('\n── 与 normalize_meta 集成（真实出口）──')
# ⚠️ normalize_meta 返回的是 **meta 子字典**，result 是【就地修改】的。
#    断言必须看传进去的那个对象，不是返回值 —— 否则会误判成「没生效」。
try:
    from app.meta import normalize_meta
    res = {'platform': 'test', 'video_url': 'http://a.com/v.mp4',
           'cover': 'http://a.com/c.jpg', 'title': 'x'}
    out = normalize_meta(res)
    check('normalize_meta 就地升级了 result.video_url',
          res.get('video_url') == 'https://a.com/v.mp4',
          str(res.get('video_url')))
    check('normalize_meta 就地升级了 result.cover',
          res.get('cover') == 'https://a.com/c.jpg',
          str(res.get('cover')))
    check('meta 子字典里的 cover 同步为 https',
          (out.get('cover') or '').startswith('https://')
          or out.get('cover') is None,
          str(out.get('cover')))
except Exception as e:
    check('normalize_meta 集成正常', False, str(e)[:80])

print('\n── 关键回归：不能影响正常解析字段 ──')
from app.meta import normalize_meta  # noqa: E402
res = {'platform': 'douyin', 'title': '原标题', 'duration_s': 10}
out = normalize_meta(res)
check('title 不被改', res.get('title') == '原标题')
check('duration_s 不被改', res.get('duration_s') == 10,
      str(res.get('duration_s')))

print(f'\n════ 资源URL 协议升级：{len(PASS)} 通过 / {len(FAIL)} 失败')
sys.exit(1 if FAIL else 0)