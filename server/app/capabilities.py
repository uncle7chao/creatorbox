"""
平台能力矩阵 —— 已废弃，数据已迁移到 knowledge.py

⚠️ 保留此文件仅为向后兼容，请勿在此编辑平台信息。
新代码请直接用：
    from app.knowledge import PLATFORMS, FIELD_PATTERNS, PITFALLS, summary
"""
import warnings

from app.knowledge import PLATFORMS as _PLATFORMS
from app.knowledge import summary as _summary

warnings.warn(
    'app.capabilities 已废弃，请改用 app.knowledge（单一事实源）',
    DeprecationWarning, stacklevel=2,
)

CAPABILITY = {
    name: {
        'tested_at': '2026-10-05',
        'status': cfg['status'],
        'need_browser': cfg['engine'] == 'browser',
        'need_proxy': not cfg.get('whitelist_ok', False),
        'cdn_whitelist_ok': cfg.get('whitelist_ok'),
        'cdn_hosts': cfg.get('cdn_hosts', []),
        'types': cfg.get('types', []),
        'max_quality': cfg.get('max_quality'),
        'free_max_quality': cfg.get('free_quality'),
        'proxy_reason': cfg.get('blocked_reason', ''),
        'measured': cfg.get('measured', {}),
    }
    for name, cfg in _PLATFORMS.items()
}

WHITELIST_HINT = {
    name: {
        'ok': cfg.get('whitelist_ok'),
        'domains': [f'https://{h}' for h in cfg.get('cdn_hosts', [])],
    }
    for name, cfg in _PLATFORMS.items()
}

summary = _summary
