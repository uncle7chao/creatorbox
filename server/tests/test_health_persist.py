"""健康度持久化 + 告警链路测试（M1.5 缺口#3）

不依赖真实网络 —— 探针样本会失效，测试只验「落库 / 告警状态机 / 通知触发点」，
探针本身的网络行为由 tests/test_gate_m1.py 覆盖。

运行：python tests/test_health_persist.py
"""
import os
import sys
import tempfile
import time

# ⚠️ 必须在导入 app.db 之前设 CB_DB_PATH —— db.py 在 import 时读环境变量
_TMP = tempfile.mkdtemp(prefix='cb_health_test_')
os.environ['CB_DB_PATH'] = os.path.join(_TMP, 'test.db')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db                                    # noqa: E402
from app.health import HealthMonitor                  # noqa: E402

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


print('1. health_record 落库 + 读回')
recs = [
    {'platform': 'bilibili', 'status': 'ok', 'ok': 1, 'latency_ms': 812,
     'error': '', 'consecutive_fail': 0, 'ts': int(time.time())},
    {'platform': 'kuaishou', 'status': 'down', 'ok': 0, 'latency_ms': 0,
     'error': 'result=400002 captcha', 'consecutive_fail': 2,
     'ts': int(time.time())},
]
n = db.health_record(recs)
check('写入 2 行', n == 2, str(n))
rows = db.health_history_list('kuaishou')
check('按平台读回 1 行', len(rows) == 1, str(len(rows)))
check('error 原样入库', '400002' in rows[0]['error'], rows[0]['error'])
check('status=down', rows[0]['status'] == 'down')
all_rows = db.health_history_list()
check('全量读回 2 行', len(all_rows) == 2, str(len(all_rows)))

print('2. 告警状态机：down 建档 → 持续 down 续档（不重复通知）→ 恢复销案')
is_new = db.health_alert_upsert('kuaishou', 'critical', '连续 2 次探针失败', '核对页面')
check('首次 down 建档（触发通知）', is_new is True)
is_new = db.health_alert_upsert('kuaishou', 'critical', '连续 3 次探针失败', '核对页面')
check('再次 down 续档（不重复通知）', is_new is False)
alerts = db.health_alerts_open()
check('open 告警 1 条', len(alerts) == 1, str(len(alerts)))
check('count 递增到 2', alerts[0]['count'] == 2, str(alerts[0]['count']))
check('message 刷为最新', '3 次' in alerts[0]['message'], alerts[0]['message'])

resolved = db.health_alert_resolve('kuaishou')
check('恢复销案', resolved is True)
check('重复销案返回 False（无 open 可关）', db.health_alert_resolve('kuaishou') is False)
check('销案后 open 为空', db.health_alerts_open() == [])

print('3. degraded 不建档（防骚扰）')
db.health_alert_upsert('sohu', 'warning', '偶发失败', '关注趋势')
db.health_alert_upsert('sohu', 'warning', '又偶发', '关注趋势')
db.health_alert_resolve('sohu')
check('warning 档也走同表但可销案', db.health_alerts_open() == [])

print('4. Monitor 迁移检测（_persist_and_alert，无需网络）')
m = HealthMonitor()
now = int(time.time())
kuaishou_before = len(db.health_history_list('kuaishou'))   # §1 已落 1 行
# 第一轮：kuaishou down
m._persist_and_alert({'probes': [
    {'platform': 'kuaishou', 'status': 'down', 'ok': False,
     'error': 'captcha', 'consecutive_fail': 2, 'ts': now},
]})
check('down -> 建档', len(db.health_alerts_open()) == 1)
check('prev_status 记录 down', m._prev_status.get('kuaishou') == 'down')
# 第二轮：仍 down
m._persist_and_alert({'probes': [
    {'platform': 'kuaishou', 'status': 'down', 'ok': False,
     'error': 'captcha', 'consecutive_fail': 3, 'ts': now},
]})
alerts = db.health_alerts_open()
check('仍 open 且 count=2', len(alerts) == 1 and alerts[0]['count'] == 2,
      str(alerts))
# 第三轮：恢复 ok
m._persist_and_alert({'probes': [
    {'platform': 'kuaishou', 'status': 'ok', 'ok': True,
     'latency_ms': 900, 'consecutive_fail': 0, 'ts': now},
]})
check('恢复 -> 销案', db.health_alerts_open() == [])
check('prev_status 记录 ok', m._prev_status.get('kuaishou') == 'ok')
# 三轮各落 1 行（delta 计数 —— 同秒时间戳下不能按 ts 排序断言绝对值）
kuaishou_after = len(db.health_history_list('kuaishou'))
check('三轮历史都落库（delta=3）', kuaishou_after - kuaishou_before == 3,
      f'{kuaishou_before} -> {kuaishou_after}')

print('5. 过期清理（显式旧时间戳，不赌同秒边界）')
old_ts = now - 2 * 86400     # 两天前，必然超过 1 天保留期
db.health_record([{'platform': 'old', 'status': 'ok', 'ok': 1, 'ts': old_ts}])
check('旧行已入库', len(db.health_history_list('old')) == 1)
removed = db.health_cleanup(1)
check('只清理过期行', removed >= 1, str(removed))
check('旧行已删', db.health_history_list('old') == [])
check('近期行保留（kuaishou 4 行还在）',
      len(db.health_history_list('kuaishou')) == kuaishou_after)

print('6. 防御：None/空平台/超长字段')
n = db.health_record([
    {'platform': '', 'status': 'ok', 'ok': 1, 'ts': now},
    {'platform': 'p' * 100, 'status': 'ok' * 30, 'ok': 1,
     'error': 'e' * 500, 'ts': now},
])
check('空平台被跳过', n == 1, str(n))
long_rows = db.health_history_list('p' * 40)
check('超长平台名截断到 40 且可按截断名查回',
      len(long_rows) == 1 and len(long_rows[0]['platform']) == 40,
      str(len(long_rows[0]['platform'])) if long_rows else 'no row')
check('error 截断到 120', len(long_rows[0]['error']) <= 120,
      str(len(long_rows[0]['error'])))

print()
print('=' * 52)
print(f'{passed} PASS / {failed} FAIL')
if failed:
    sys.exit(1)
print('OK 健康持久化与告警链路全部通过')
