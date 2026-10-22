# -*- coding: utf-8 -*-
"""未支持平台的报错测试（2026-10-22）。

修的是什么
----------
`pick_platform` 原实现最后 `return self.pure[0], None` ——
任何**不认识**的域名都被丢给抖音解析器，于是报：

    短链未解析出 aweme_id

⭐ 这个错误信息把用户引向完全错误的方向：抖音没抽风，
是「这个平台压根没接入」。实测「百度视频 / 西瓜视频」都踩这个坑。

修法：返回 None，调用方报「暂不支持该平台链接」并列出已支持清单。

跑法： python tests/test_unsupported_platform.py
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix='cb_unsup_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'unsup.db')
sys.path.insert(0, '.')

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

# 未接入的平台域名（实测过的）
UNSUPPORTED = [
    ('百度视频 web', 'https://v.baidu.com/some-video'),
    ('百度首页', 'https://www.baidu.com/'),
    ('西瓜视频', 'https://www.ixigua.com/123456'),
    ('优酷', 'https://v.youku.com/v_show/id_XNz.html'),
    ('爱奇艺', 'https://www.iqiyi.com/v_19rr7depxo.html'),
    # ⚠️ 不要把 B 站番剧放这里 —— 那是 bilibili 域名，
    #    会被 B 站解析器正确接管（报「未识别到 BV/av 号」是准确的）。
    #    本测试只针对【完全未接入】的域名。
]

with TestClient(app) as cl:
    for name, url in UNSUPPORTED:
        r = cl.post('/api/parse', json={'text': url, 'no_cache': True})
        try:
            d = r.json()
        except Exception:
            d = {}
        msg = str(d.get('error', ''))
        check(f'{name}：不再报「短链未解析出 aweme_id」',
              'aweme_id' not in msg, msg[:80])
        check(f'{name}：明确说平台不支持',
              '暂不支持' in msg or '不支持' in msg, msg[:80])
        check(f'{name}：platform 不再谎报成 douyin',
              d.get('platform') != 'douyin', f"platform={d.get('platform')!r}")
        check(f'{name}：标了 unsupported_platform 标记',
              d.get('unsupported_platform') is True, str(d)[:80])

    # 已支持平台不能被这次改动误伤
    s, d = cl.post('/api/parse', json={
        'text': 'https://haokan.baidu.com/v?vid=1688233510589355861',
        'no_cache': True}).json(), None
    check('好看视频（haokan.baidu.com）仍能解析',
          s.get('success') is True, str(s.get('error') or '')[:80])
    check('好看视频 platform 正确', s.get('platform') == 'haokan',
          str(s.get('platform')))

print(f'\n════ 未支持平台报错：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')