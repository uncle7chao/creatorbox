"""广告位配置：settings DAO（离线）+ /api/ads/config 端点（在线，需服务已启动）

运行：python tests/test_ads_config.py
"""
import os
import sys
import tempfile

# 离线部分：临时库
_TMP = tempfile.mkdtemp(prefix='cb_ads_test_')
os.environ['CB_DB_PATH'] = os.path.join(_TMP, 'test.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db                       # noqa: E402

db.init()
passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'   PASS  {name}')
    else:
        failed += 1
        print(f'   FAIL  {name}  <- {detail}')


print('1. settings DAO：写入/覆盖/读回')
check('未配置返回 None', db.settings_get('nope') is None)
db.settings_set('k1', {'a': 1})
check('写入读回', db.settings_get('k1') == {'a': 1})
db.settings_set('k1', {'a': 2, 'b': 'x'})
check('覆盖生效', db.settings_get('k1') == {'a': 2, 'b': 'x'})

print('2. /api/ads/config 端点（在线）')
import json
import urllib.error
import urllib.request

BASE = os.getenv('CB_TEST_BASE', 'http://127.0.0.1:8080')


def req(method, path, payload=None):
    r = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


try:
    code, body = req('GET', '/api/ads/config')
    online = code == 200
    check('服务可达', online, f'HTTP {code}')
except Exception as e:
    online = False
    print(f'   SKIP  服务未启动（{str(e)[:50]}）—— 端点部分跳过')

if online:
    ads = body.get('ads', {})
    # ⚠️ 服务端 DB 是持久化的 —— 若之前跑过本测试，配置非默认值。
    #   这里只断言结构与类型，「默认值」断言只在首次运行时成立。
    check('master 是布尔', isinstance(ads.get('master'), bool))
    check('placements 含 7 个位（2026-10-08 +hero_banner）',
          len(ads.get('placements', {})) == 7)
    check('hero_banner 结构就绪（自宣传轮播位）',
          isinstance(ads.get('placements', {}).get('hero_banner'), dict)
          and ads['placements']['hero_banner']['mode'] == 'image')
    first = next(iter(ads.get('placements', {}).values()), {})
    check('placement 是对象结构（v3）', isinstance(first, dict)
          and 'enabled' in first and 'mode' in first and 'images' in first,
          str(first)[:80])
    check('popup 结构完整', isinstance(ads.get('popup', {}).get('enabled'), bool))

    code, body = req('POST', '/api/ads/config',
                     {'master': True,
                      'placements': {'index_banner': False, 'bogus': True},
                      'popup': {'every_n_parses': 5, 'start_after': 99}})
    check('POST 200', code == 200, str(code))
    check('master 更新', body['ads']['master'] is True)
    check('合法位更新（enabled 落在对象里）',
          body['ads']['placements']['index_banner']['enabled'] is False)
    check('未知位被忽略', 'bogus' not in body['ads']['placements'])
    check('频次合法更新', body['ads']['popup']['every_n_parses'] == 5)
    check('start_after 越界被钳制（<=50）',
          body['ads']['popup']['start_after'] == 50,
          str(body['ads']['popup']['start_after']))

    # v3：模式二选一 + 多图轮播
    code, body = req('POST', '/api/ads/config', {
        'placements': {'result_banner': {
            'mode': 'image',
            'images': ['/media/ads/a.png', '/media/ads/b.png',
                       '/media/ads/a.png', '/media/ads/c.png',
                       '/media/ads/d.png', '/media/ads/e.png']}}})
    rb = body['ads']['placements']['result_banner']
    check('mode=image 落库', rb['mode'] == 'image')
    check('images 去重保序', rb['images'][:3] == ['/media/ads/a.png',
                                                  '/media/ads/b.png',
                                                  '/media/ads/c.png'],
          str(rb['images']))
    check('images 钳制到 5 张', len(rb['images']) <= 5, str(len(rb['images'])))
    check('image 单图字段与 images[0] 同步', rb['image'] == rb['images'][0])
    code, body = req('POST', '/api/ads/config', {
        'placements': {'result_banner': {'mode': 'code',
                                         'unit_id': 'adunit-abc123'}}})
    rb = body['ads']['placements']['result_banner']
    check('mode=code 落库', rb['mode'] == 'code' and rb['unit_id'] == 'adunit-abc123')
    check('切模式不丢自定义图', len(rb['images']) > 0)

    code, body = req('GET', '/api/ads/config')
    check('GET 读到持久化结果', body['ads']['master'] is True
          and body['ads']['popup']['every_n_parses'] == 5)
    check('GET 读回 v3 模式与图片',
          body['ads']['placements']['result_banner']['mode'] == 'code')

    code, _ = req('POST', '/api/ads/config', 'not-json-object')
    check('非法 body → 400', code == 400, str(code))

    # 还原默认（避免影响其他测试；result_banner 要把 v3 测试字段一并还原）
    req('POST', '/api/ads/config', {'master': False,
                                    'placements': {'index_banner': True,
                                                   'result_banner': {
                                                       'mode': 'image',
                                                       'images': [],
                                                       'unit_id': ''}},
                                    'popup': {'every_n_parses': 3,
                                              'start_after': 2}})

print()
print('=' * 52)
print(f'{passed} PASS / {failed} FAIL')
if failed:
    sys.exit(1)
print('OK 广告配置测试全部通过')
