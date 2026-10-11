"""平台可见性收敛开关（v4 §3.3 上架主线）

为什么需要
----------
小程序审核对「视频解析」类目持续收紧。提审版本需要在**不提审不行、正常用户又不丢失功能**
之间找平衡 —— 做法是：提审构建把高风险平台整体隐藏，只留工具矩阵叙事能过的平台；
正式版再打开。开关必须由服务端下发，否则三端各写一套隐藏逻辑，很快失控。

设计要点
--------
1. **默认全开**（`mode = 'full'`）。日常开发与现有用户不受影响，
   提审时才用环境变量切成 `review` 收敛。
2. **收敛只影响「入口可见性」，不影响解析能力** —— 隐藏的平台若被直接提交链接，
   仍可解析成功。这避免「入口没了接口就废」的连带故障。
3. 单一事实源仍是 `app.knowledge.PLATFORMS`，这里只做叠加裁决，不复制平台元数据。
4. 动态热更：每次请求读 config，不缓存 —— 改环境变量重启即生效，便于提审前演练。

风险分级依据（为什么这几个要藏）
------------------------------
- youtube / tiktok / x / facebook：海外平台，审核场景下「去水印」语义最刺眼
- xiaohongshu / kuaishou：图文/短视频平台，与「工具」类目叙事契合度低
- weibo / acfun / sohu / haokan：低频，且部分需代理/浏览器通道
保留默认展示：douyin / bilibili —— 需求最集中、审核相对安全的两个
"""
from typing import Any, Dict, List

from app import config
from app.knowledge import PLATFORMS

# 提审模式下允许展示的平台（白名单）。
#
# 为什么用白名单而不是「列出要藏的」：提审前漏藏一个平台的概率直接归零 ——
# 将来 knowledge 新增平台会自动收敛，不需要同步改这里。
# 风险分级依据：
#   藏：youtube/tiktok/x/facebook（海外平台，「去水印」语义在审核语境最刺眼）
#       xiaohongshu/kuaishou（图文/短视频，与「工具」类目叙事契合度低）
#       其余低频平台（部分还需代理/浏览器通道）
#   留：douyin / bilibili —— 需求最集中、审核相对安全的两个
REVIEW_VISIBLE: tuple = ('douyin', 'bilibili')


def mode() -> str:
    """当前收敛模式：full（全开） / review（提审收敛）。"""
    m = (getattr(config, 'REVIEW_MODE', '') or '').strip().lower()
    return m if m in ('full', 'review') else 'full'


def is_visible(platform: str) -> bool:
    """该平台在当前模式下是否对用户展示入口。

    ⚠️ 未知平台一律 False，即便在 full 模式下 —— 客户端可能传入拼错的 key 或
    已下线平台，放行等于让不存在的入口通过裁决。白名单语义必须严。
    """
    if platform not in PLATFORMS:
        return False
    if mode() != 'review':
        return True
    return platform in REVIEW_VISIBLE


def visible_platforms() -> List[Dict[str, Any]]:
    """按 knowledge 的元数据生成「用户可见平台清单」，供三端渲染入口。"""
    out: List[Dict[str, Any]] = []
    for key, meta in PLATFORMS.items():
        if not is_visible(key):
            continue
        out.append({
            'key': key,
            'name_cn': meta.get('name_cn', key),
            'types': meta.get('types', ['video']),
            'max_quality': meta.get('max_quality', ''),
            'free_quality': meta.get('free_quality', ''),
            'status': meta.get('status', ''),
        })
    return out


def payload() -> Dict[str, Any]:
    """下发给客户端的完整裁决结果。

    客户端只按这份数据渲染，不要自己再判断 —— 否则三端口径迟早不一致。
    """
    m = mode()
    hidden = sorted(k for k in PLATFORMS if not is_visible(k))
    return {
        'mode': m,
        'review_mode': m == 'review',
        # 是否允许「入口隐藏后仍可通过粘贴链接解析」
        'hidden_still_parseable': True,
        'platforms': visible_platforms(),
        'visible_keys': sorted(p['key'] for p in visible_platforms()),
        'hidden_keys': hidden,
        'note': ('提审收敛模式：仅保留高频且审核风险低的平台；'
                 '隐藏不等于停用，粘贴链接仍可解析' if m == 'review'
                 else '全量模式：所有平台可见'),
    }