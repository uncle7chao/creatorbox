"""dtk TikTok 签名移植验证（2026-10-11，离线字节级）

Golden 向量来自 Evil0ctal v4 tests/unit/test_signing.py（TikTok's genuine
webmssdk 2.0.0.561 在 Node 里执行产出，时钟/nonce/key 全部钉死）——
向量证明**移植忠实于原实现**；平台侧常量是否仍被接受只能真网验证。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsers.intl.dtk import tiktok_sign  # noqa: E402

PASS = []
def check(name, ok, detail=''):
    PASS.append(ok)
    print(('  ✅ ' if ok else '  ❌ ') + name + (f' ← {detail}' if not ok and detail else ''))

TIKTOK_UA_MAC = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
)
HARNESS_ENV_CODE = 129
HARNESS_UB_CODE = 14

VECTOR_0 = {
    'query': 'aid=1988&count=10',
    'user_agent': TIKTOK_UA_MAC,
    'ms_token': '',
    'timestamp': 1788856077,
    'nonce': 51705231,
    'sequence': 1,
    'dynosaur_key': (978422917, 297502614, 495476334, 3283317692,
                     2976530683, 1833255788, 640912066, 837161194,
                     1669461668, 1494236015, 394043533, 3049628592),
    'dynosaur': ('MxmNRRv/B-a6aTHjkvVe9cmFRhMeLS613kBZFzkI/aJYxnjdutQ24acX9B9/EWqDls27AI1WNuyaY9yQV-fvFZ'
                 '98HD8AuO8owhWWl/k/NA8VrqhUi8SisGI7yUrOkPYuhjSfZRLYkGGOgiGZxl3WaGSlTOfZpAFId0'
                 'mkGwpCrZfrPHFoydYsLb/yWgabzJa1dqhKx2GbbaB6PX4aDjR9dLL7UrKk0s/DzRU/QVPXTcZV5S'
                 'A-0iNUlMpHBc66oAf6S1vX5d6EOit0cum8dabUKE2owzmAG4jC9mibKZdkNQXy02gCJVgP31bnbFMM'
                 'W3u-ZI4sE0Pi-gGzNtwdlNvF1ABzqrSpSockDCh84FYrmmOGRNL-vbyAwnYm7cmYIKuQ-a97tCivXvA='),
    'gnarly_timestamp': 1788856077,
    'gnarly_nonce': 51705346,
    'nonce2': 4243271951,
    'gnarly_sequence': 1,
    'gnarly_key': (1630480152, 2370805161, 303572552, 3085792651,
                   989762755, 2481426789, 1111047770, 4159623281,
                   1698763817, 2164255245, 1245854549, 1546723756),
    'gnarly_order': [0, 12, 1, 11, 15, 3, 6, 4, 5, 2, 8, 10, 9, 14, 16, 13],
    'gnarly': ('MC3KKmrckRFfMdp/YlNaTDaQpDXunCTZoDhfUcF5ak2ml87IfMPZmHnU4Rmo-BpWi3stE8dkD0LI'
               'z0I2EF3q2zc6M9AAbGYCHTdt4-/KooU2WCGcrzg8RrH5DVV0oZ5BP/0LrRgDj9b8sUAMK2vH8Gq/4-CPgq5874-'
               'RFPYho9vzV3omXS9BRFCK6d6FNpDaPVFaIw/hwJzNwu7lZJkb7tewprbTvuM5jZIDC9/0CjnDNT3'
               'FESXpDFqIY9XU-yGfFGxZMScDZRqgNZkRQxDAa2ojWjVhui4pZdBxy4E0UBsQ1DNu5pquE4wuNnxIEsajo3u='),
}

print('1. Golden 向量：X-Dynosaur 字节级复现')
payload = tiktok_sign.dynosaur_payload(
    VECTOR_0['query'], VECTOR_0['user_agent'],
    timestamp=VECTOR_0['timestamp'], nonce=VECTOR_0['nonce'],
    sequence=VECTOR_0['sequence'],
    env_code=HARNESS_ENV_CODE, ub_code=HARNESS_UB_CODE)
sealed = tiktok_sign.seal(payload, VECTOR_0['dynosaur_key'])
check('dynosaur 字节一致', sealed == VECTOR_0['dynosaur'],
      f'{sealed[:40]}... vs {VECTOR_0["dynosaur"][:40]}...')

print('2. Golden 向量：X-Gnarly 字节级复现')
sealed_q = (f"{VECTOR_0['query']}&{tiktok_sign.DYNOSAUR_PARAM}={VECTOR_0['dynosaur']}"
            f"&{tiktok_sign.MS_TOKEN_PARAM}={VECTOR_0['ms_token']}")
gp = tiktok_sign.gnarly_payload(
    sealed_q, VECTOR_0['user_agent'],
    timestamp=VECTOR_0['gnarly_timestamp'], nonce=VECTOR_0['gnarly_nonce'],
    nonce2=VECTOR_0['nonce2'], sequence=VECTOR_0['gnarly_sequence'],
    order=VECTOR_0['gnarly_order'],
    env_code=HARNESS_ENV_CODE, ub_code=HARNESS_UB_CODE)
gnarly = tiktok_sign.seal(gp, VECTOR_0['gnarly_key'])
check('gnarly 字节一致', gnarly == VECTOR_0['gnarly'],
      f'{gnarly[:40]}... vs {VECTOR_0["gnarly"][:40]}...')

print('3. unseal 往返（seal 自带密钥可解）')
payload_b = b'hello-creatorbox-2026'
key = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
token = tiktok_sign.seal(payload_b, key)
recovered, rkey = tiktok_sign.unseal(token)
check('payload 往返一致', recovered == payload_b)
check('密钥往返一致', list(rkey) == list(key))

print('4. ms_token 进签名字节（改动必然改变 gnarly）')
vec = dict(VECTOR_0)
vec['ms_token'] = 'not-the-signed-token'
sq = (f"{vec['query']}&{tiktok_sign.DYNOSAUR_PARAM}={vec['dynosaur']}"
      f"&{tiktok_sign.MS_TOKEN_PARAM}={vec['ms_token']}")
gp2 = tiktok_sign.gnarly_payload(
    sq, vec['user_agent'], timestamp=vec['gnarly_timestamp'],
    nonce=vec['gnarly_nonce'], nonce2=vec['nonce2'],
    sequence=vec['gnarly_sequence'], order=vec['gnarly_order'],
    env_code=HARNESS_ENV_CODE, ub_code=HARNESS_UB_CODE)
check('ms_token 参与 seal（换 token 签名必变）',
      tiktok_sign.seal(gp2, vec['gnarly_key']) != VECTOR_0['gnarly'])

print('5. sign() 端到端：输出含全部四个签名参数')
signed, params = tiktok_sign.sign(
    [('aid', '1988'), ('itemId', '731')], TIKTOK_UA_MAC,
    timestamp=VECTOR_0['timestamp'], nonce=VECTOR_0['nonce'],
    key=VECTOR_0['dynosaur_key'], key2=VECTOR_0['gnarly_key'])
check('signed 查询串包含业务参数', signed.startswith('aid=1988&itemId=731&'))
check('四签名参数齐全',
      all(p in signed for p in (tiktok_sign.DYNOSAUR_PARAM,
                                tiktok_sign.MS_TOKEN_PARAM,
                                tiktok_sign.BOGUS_PARAM,
                                tiktok_sign.GNARLY_PARAM)))
check('parameters dict 与查询串一致',
      params[tiktok_sign.DYNOSAUR_PARAM] in signed)

print('6. fixture 解析：video_normal.json → itemStruct')
fx = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  'fixtures', 'tiktok_video_normal.json')
if os.path.exists(fx):
    data = json.load(open(fx, encoding='utf-8'))
    item = (((data.get('itemInfo') or {}).get('itemStruct')) or {})
    from app.parsers.intl.dtk_params import parse_item_struct
    if item:
        n = parse_item_struct(item)
        check('fixture 解析 success', n['success'])
        check('有标题', bool(n['title']), str(n['title'])[:40])
        check('有封面或视频', bool(n['cover']) or bool(n['video_url']))
    else:
        check('fixture 无 itemStruct（记录并跳过）', True)
else:
    check('fixture 文件存在', False, fx)

print(f'\n{sum(PASS)} PASS / {len(PASS) - sum(PASS)} FAIL')
assert all(PASS), '存在失败断言'
print('✅ dtk TikTok 签名移植验证通过（离线字节级）')
