"""小红书 xhslink 短链解析 + 失败路由测试（离线，本地 302 服务器）

背景：2026-10-07 用户实测 App 分享的小红书链接解析报 notFoundPage。
本轮修复：① xhslink.com 短链支持（跟 302 拿完整链接）② notFoundPage 文案分层。

运行：python tests/test_xhslink_resolve.py
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsers import xiaohongshu_pure as xhs          # noqa: E402

passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'   PASS  {name}')
    else:
        failed += 1
        print(f'   FAIL  {name}  <- {detail}')


FULL_URL = ('https://www.xiaohongshu.com/discovery/item/'
            '6a827209000000002701cde0'
            '?xsec_token=AB7esHwJgaSaSlhVeq7GJlZN8Fi1J6MrUIjviv8R_APxM='
            '&xsec_source=pc_share')

# ── 本地 302 服务器：/s/xxx → FULL_URL；/dead → 302 无 Location ──
class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/dead'):
            self.send_response(302)             # 无 Location —— 异常响应
            self.end_headers()
            return
        self.send_response(302)
        self.send_header('Location', FULL_URL)
        self.end_headers()

    def log_message(self, *a):      # 静音
        pass


srv = HTTPServer(('127.0.0.1', 0), RedirectHandler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

print('1. _resolve_xhslink：跟 302 拿完整链接')
short = f'http://127.0.0.1:{port}/s/AbCdEf123'
got = xhs._resolve_xhslink(short)
check('短链解析出完整链接', got == FULL_URL, got[:80])
check('完整链接含 xsec_token', 'xsec_token=' in got)

print('2. 短链解析失败 → 原样返回（上层给可读错误）')
dead = f'http://127.0.0.1:{port}/dead'      # 无 Location 头的 302
got2 = xhs._resolve_xhslink(dead, timeout=3)
check('无 Location 时原样返回', got2 == dead, got2[:80])

print('3. _parse_sync 路由：短链触发解析、解析失败给可读错误')
import asyncio
# ⚠️ 真实 xhslink.com 会出网 —— monkeypatch 成「解析失败」模拟离线路由
orig_resolve = xhs._resolve_xhslink
xhs._resolve_xhslink = lambda u, timeout=15: u      # 恒返回原 URL = 解析失败
r = asyncio.run(xhs._parse_sync(
    '83 【标题 - 作者 | 小红书 - 你的生活兴趣社区】 '
    'http://xhslink.com/a/AbCdEf123'))
xhs._resolve_xhslink = orig_resolve
check('短链 + 解析失败 → 「短链解析失败」', '短链解析失败' in (r.get('error') or ''),
      str(r.get('error')))
check('失败时带「重新分享」提示', '重新' in (r.get('hint') or ''), str(r.get('hint')))
r2 = asyncio.run(xhs._parse_sync(
    '看看这个 https://www.xiaohongshu.com/explore/'
    '6a827209000000002701cde0 没了'))
check('完整链接但缺 token → 「缺少 xsec_token」',
      'xsec_token' in (r2.get('error') or ''), str(r2.get('error')))

print('4. notFoundPage 文案分层（不再误导为「笔记已删除」）')
import inspect
src = inspect.getsource(xhs._parse_sync)
check('文案覆盖「令牌过期」与「已删除」两种原因',
      '令牌已过期' in src and '删除' in src)
check('文案给出用户可执行动作（重新分享）', '重新' in src and '复制链接' in src)

print('5. 登录态 Cookie 注入 + 登录墙识别（2026-10-07）')
# 5a. 配置 Cookie 后 _get 必须带上 Cookie 头
echo_html = ['<html><body>echo</body></html>']
captured = {}

class EchoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        captured['cookie'] = self.headers.get('Cookie', '')
        body = echo_html[0].encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

srv2 = HTTPServer(('127.0.0.1', 0), EchoHandler)
port2 = srv2.server_address[1]
threading.Thread(target=srv2.serve_forever, daemon=True).start()

try:
    from app import config as cfg
except ImportError:
    import config as cfg

cfg.XHS_COOKIE = 'web_session=abc123; a1=x1'
xhs._get(f'http://127.0.0.1:{port2}/echo')
check('配置 Cookie 后请求携带 Cookie 头', captured.get('cookie') == 'web_session=abc123; a1=x1',
      str(captured.get('cookie')))
cfg.XHS_COOKIE = ''
xhs._get(f'http://127.0.0.1:{port2}/echo')
check('未配置时不带 Cookie 头', captured.get('cookie') == '', str(captured.get('cookie')))

# 5b. 登录墙（fe-login 壳）→ 精准报错，不做无谓重试
orig_get = xhs._get
xhs._get = lambda url, timeout=30: '<html><script>fe-login</script></html>'
r3 = asyncio.run(xhs._parse_sync(
    '85 【测试 - 作者 | 小红书 - 你的生活兴趣社区】 ' + FULL_URL))
xhs._get = orig_get
check('登录墙 → 精准错误文案', '需要登录' in (r3.get('error') or ''), str(r3.get('error')))
check('login_wall 标记', r3.get('login_wall') is True, str(r3.get('login_wall')))
check('提示配置 Cookie', 'Cookie' in (r3.get('hint') or ''), str(r3.get('hint')))

srv.shutdown()
srv2.shutdown()
print()
print('=' * 52)
print(f'{passed} PASS / {failed} FAIL')
if failed:
    sys.exit(1)
print('OK xhslink 短链解析测试全部通过')
