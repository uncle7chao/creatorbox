# -*- coding: utf-8 -*-
"""管理接口鉴权测试（默认拒绝）。

修的是什么
----------
原实现：`if config.API_KEY and x_api_key != config.API_KEY: raise 401`
→ API_KEY 为空时**放行**。而 API_KEY 默认就是空。
→ 一旦运维忘配 CB_API_KEY，所有 /api/admin/* 裸奔：
   任何人都能改卡密、改违禁词、导出用户名单。

修法：拆成两类，**失败方向相反**
  · check_admin       管理类 → 未配 Key 直接锁死（503）
  · check_admin_or_open解析类 → 配了才校验，未配放行

⚠️ 为什么解析类必须放行：/api/parse 与 /api/batch 也挂着鉴权依赖。
   曾差点把默认拒绝套到它们头上 → 小程序与 App 解析全线失败。

跑法： python tests/test_admin_auth.py
"""
import os
import sys
import importlib
import tempfile

# 临时库：本测试会 reload app.config，绝不能碰真实 data/cb.db
_tmp = tempfile.mkdtemp(prefix='cb_auth_')
os.environ['CB_DB_PATH'] = os.path.join(_tmp, 'auth.db')
sys.path.insert(0, '.')

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('✅' if cond else '❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


def fresh_client(api_key=''):
    """按给定 API_KEY 重载 app.main，返回 (TestClient, config, main模块)。

    reload 会清掉 db 的全局连接状态，必须重新 init() —— 否则任何碰库的
    端点都会 AssertionError: db.init() 未调用。
    """
    import app.config as cfg
    import app.db as dbm
    import app.main as m
    importlib.reload(cfg)
    importlib.reload(dbm)
    importlib.reload(m)
    cfg.API_KEY = api_key
    dbm.init()
    from fastapi.testclient import TestClient
    return TestClient(m.app), cfg, m


# ============ 场景 1：未配 API_KEY（默认状态）============
client, cfg, m = fresh_client('')

r = client.post('/api/admin/codes', json={})
check('未配 Key：管理端点锁死 503（不是放行）', r.status_code == 503,
      f'实得 {r.status_code} —— 若为 200/401 说明安全修复失效')
check('未配 Key：响应里说明了原因',
      'CB_API_KEY' in (r.json().get('detail', '') if r.headers.get(
          'content-type', '').startswith('application/json') else r.text),
      r.text[:100])

# 管理类清单：全部必须 503
ADMIN_POST = [
    ('/api/admin/codes', {}),
    ('/api/admin/codes/disable', {'code': 'X'}),
    ('/api/admin/banned/words', {'word': 'x', 'category': 'adlaw'}),
    ('/api/admin/banned/words/toggle', {'word': 'x', 'enabled': False}),
    ('/api/admin/banned/words/delete?word=x', {}),
    ('/api/admin/cookies', {}),
]
for ep, body in ADMIN_POST:
    r = client.post(ep, json=body)
    check(f'未配 Key：{ep} 拒绝', r.status_code == 503, f'实得 {r.status_code}')

for ep in ('/api/admin/codes', '/api/admin/cookies', '/api/admin/users'):
    r = client.get(ep)
    # GET 类端点有的没挂 check_auth —— 至少不能是「能读到数据」
    if r.status_code == 200:
        check(f'⚠️ {ep} 未挂鉴权且可访问（需人工确认）', False,
              '管理数据可能泄露，请给它加 Depends(check_auth)')
    else:
        check(f'未配 Key：{ep} 拒绝（{r.status_code}）', True)

# 解析类：必须放行，否则 C 端全线挂
r = client.post('/api/parse', json={'text': 'not-a-url'})
check('未配 Key：/api/parse 仍可用（不被误伤）',
      r.status_code != 503, f'实得 {r.status_code} —— 解析被误锁了！')
check('未配 Key：/api/parse 返回业务响应（4xx 属正常）',
      r.status_code in (200, 400, 404), f'实得 {r.status_code}')


# ============ 场景 2：配了 API_KEY ============
client, cfg, m = fresh_client('test-key-123')

# 无 Key / 错 Key → 401
r = client.post('/api/admin/codes', json={})
check('配了 Key：管理端点无凭证 → 401', r.status_code == 401, f'实得 {r.status_code}')
r = client.post('/api/admin/codes', json={},
                headers={'X-Api-Key': 'wrong'})
check('配了 Key：错 Key → 401', r.status_code == 401, f'实得 {r.status_code}')

# 解析类：错 Key 也要 401（配了就该校验）
r = client.post('/api/parse', json={'text': 'x'}, headers={'X-Api-Key': 'wrong'})
check('配了 Key：解析类错 Key 也校验 → 401', r.status_code == 401,
      f'实得 {r.status_code}')
r = client.post('/api/parse', json={'text': 'x'})
check('配了 Key：解析类无 Key → 401（配了就必须校验）', r.status_code == 401,
      f'实得 {r.status_code}')


# ============ 场景 3：依赖声明是否挂对 ============
from fastapi.routing import APIRoute  # noqa: E402

ADMIN_PATHS = {r.path for r in m.app.routes
               if isinstance(r, APIRoute) and r.path.startswith('/api/admin')}
dep_by_path = {}
for r in m.app.routes:
    if isinstance(r, APIRoute):
        dep_by_path[r.path] = [getattr(d.call, '__name__', '') for d in r.dependant.dependencies]

for p in sorted(ADMIN_PATHS):
    deps = dep_by_path.get(p, [])
    names = ' '.join(deps)
    check(f'{p} 挂了鉴权依赖', 'check_auth' in names or 'check_admin' in names,
          f'实际依赖={deps or "无"} —— 管理端点裸奔')


# ============ 场景 4：双通道参数（query 与 body 都得能用）============
# 实测踩坑记录：这两个端点原本只有 query 取参，但后来统一改成 body，
# 改的过程中一度出现「无 body 请求直接 405」的回归。根因是：
#   Pydantic 模型即使所有字段都有默认值，FastAPI 仍把 requestBody 标为
#   required:true —— 必须写 `= Body(default=None)` 才是真正可选。
# 判别方法：看 /openapi.json 的 requestBody.required。
client, cfg, m = fresh_client('k')
KH = {'X-Api-Key': 'k'}          # 这些端点挂了 check_auth，不带 Key 一律 401
with client:
    r = client.post('/api/admin/codes/disable?code=CB-TEST-QUERY', headers=KH)
    check('query 传参：作废端点可用', r.status_code == 200, f'{r.status_code} {r.text[:80]}')
    r = client.post('/api/admin/codes/disable', json={'code': 'CB-TEST-BODY'}, headers=KH)
    check('body 传参：作废端点可用', r.status_code == 200, f'{r.status_code} {r.text[:80]}')
    r = client.post('/api/admin/codes/disable', headers=KH)
    check('两处都缺 → 400 且提示明确',
          r.status_code == 400 and 'code' in r.text, f'{r.status_code} {r.text[:80]}')

    r = client.post('/api/admin/banned/words/delete?word=临时词q', headers=KH)
    check('query 传参：词删除端点可用', r.status_code == 200, f'{r.status_code} {r.text[:80]}')
    r = client.post('/api/admin/banned/words/delete', json={'word': '临时词b'}, headers=KH)
    check('body 传参：词删除端点可用', r.status_code == 200, f'{r.status_code} {r.text[:80]}')
    r = client.post('/api/admin/banned/words/delete', headers=KH)
    check('两处都缺 → 400 且提示明确',
          r.status_code == 400 and 'word' in r.text, f'{r.status_code} {r.text[:80]}')

    # 没带 Key 时必须 401（确认这些端点确实受保护，不是裸奔）
    r = client.post('/api/admin/codes/disable', json={'code': 'X'})
    check('无 Key 调用管理写接口 → 401', r.status_code == 401, f'{r.status_code}')

    # OpenAPI 层面确认 body 真的可选（这是上面的根因所在）
    spec = client.get('/openapi.json').json()
    for path in ('/api/admin/codes/disable', '/api/admin/banned/words/delete'):
        rb = spec['paths'][path]['post'].get('requestBody') or {}
        check(f'{path} 的 body 非必需（OpenAPI 契约）',
              rb.get('required') is not True, str(rb.get('required')))

print(f'\n════ 管理接口鉴权：{len(PASS)} 通过 / {len(FAIL)} 失败')
if FAIL:
    print('失败项:', FAIL)
    sys.exit(1)
print('✅ 全部通过')