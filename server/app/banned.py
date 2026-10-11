"""违禁词检测（2026-10-09，创作发布前的合规自检工具）

词库六大类（free 两类人人可查，full 四类会员专享）：
    adlaw   广告法极限词   ——「最/第一/国家级」新广告法明令（free）
    induce  诱导互动       ——平台限流高压线「扣1/求关注/私信领取」（free）
    medical 医疗功效       ——普通商品宣称疗效（member）
    money   金融承诺       ——稳赚保本类（member）
    import  站外导流       ——加微信/看主页类，平台最恨（member）
    fake    虚假夸大       ——永久/祖传/秒杀全网（member）

⚠️ 免责：词库来自公开资料整理（广告法 + 平台社区规范），是**风险提示**
    不是法律意见。检测结果=「建议人工复核」，不构成合规保证 —— 页面
    必须带此说明，否则用户拿检测报告当免死金牌出了事会回来找我们。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# ── 类目元信息 ──────────────────────────────────────────────

CATEGORIES: Dict[str, Dict[str, Any]] = {
    'adlaw':   {'name': '广告法极限词', 'free': True,
                'risk': '新广告法明令禁止，最高罚 20 万起'},
    'induce':  {'name': '诱导互动', 'free': True,
                'risk': '平台限流高压线：诱导点赞/私信/跳转'},
    'medical': {'name': '医疗功效', 'free': False,
                'risk': '普通商品宣称疗效 = 虚假宣传'},
    'money':   {'name': '金融承诺', 'free': False,
                'risk': '收益承诺类，平台直接下架'},
    'import':  {'name': '站外导流', 'free': False,
                'risk': '导流微信/主页，限流重灾区'},
    'fake':    {'name': '虚假夸大', 'free': False,
                'risk': '绝对化承诺，举报率高'},
}

FREE_CATEGORIES = {k for k, v in CATEGORIES.items() if v['free']}

# ── 词库（持续补充；每个词一个小写 key，检测时原文不区分大小写）──

WORDS: Dict[str, List[str]] = {
    'adlaw': [
        '最好', '最佳', '最优', '最爱', '最赚', '最强', '最高级', '最先进',
        '最优秀', '最大程度', '最低价', '最便宜', '最受欢迎', '最实用',
        '第一', 'NO.1', 'No1', 'TOP1', 'Top1', '全网第一', '全国第一',
        '销量第一', '排名第一', '世界第一', '全网最低', '国家级', '世界级',
        '宇宙级', '全国级', '顶级', '顶尖', '极品', '极致', '终极',
        '独家', '独创', '独有', '独享', '独家秘方', '全国首家', '首家',
        '首发', '首款', '首个', '唯一', '仅有', '仅此一款', '史无前例',
        '万能', '百分百', '100%有效', '纯天然', '纯手工无添加',
        '全方位', '全能', '冠军', '王牌', '领军者', '掌门人', '首选',
        '完美', '绝对', '空前', '绝后', '千古', '绝无仅有', '前所未有的',
        '最高档', '最顶级', '最有价值', '最符合', '最先进工艺',
    ],
    'induce': [
        '点赞收藏', '求点赞', '求关注', '求转发', '求分享', '互关', '互赞',
        '双击666', '老铁双击', '扣1', '扣2', '扣666', '扣个1', '评论区扣1',
        '评论区告诉我', '私信我', '私信领取', '私信免费领', '关注后领取',
        '关注公众号', '点赞过万更新', '转发这个视频', '分享给好友',
        '@你的好友', '艾特好友', '叫上朋友', '点击下方链接', '点击链接',
        '戳链接', '限时免费领', '免费送', '0元领', '0元购', '免费抽',
    ],
    'medical': [
        '治疗', '治愈', '根治', '痊愈', '药到病除', '特效', '神药', '偏方',
        '消炎', '杀菌', '抑菌', '抗菌', '抗炎', '降血压', '降血糖', '降血脂',
        '美白', '祛斑', '祛疤', '祛痘', '瘦身', '燃脂', '减脂', '瘦脸',
        '瘦腿', '丰胸', '壮阳', '补肾', '生发', '防脱', '防脱发育发',
        '抗衰老', '延缓衰老', '提高免疫力', '增强免疫力', '抗癌', '防癌',
        '溶脂', '排毒', '养胃', '调理身体', '改善睡眠', '安神', '补血',
        '活血', '通络', '缓解疼痛', '止痛', '修复受损', '促进生长',
        '恢复视力', '矫正视力', '助长高', '增高',
    ],
    'money': [
        '稳赚', '稳赚不赔', '保本', '保收益', '保障收益', '零风险', '无风险',
        '躺赚', '躺着赚钱', '躺着收钱', '日入过千', '日入几百', '月入十万',
        '月入过万', '暴富', '财务自由', '必涨', '稳涨', '暴涨', '翻倍',
        '内部消息', '内幕消息', '高回报', '高收益', '保证回报', '收益率保证',
        '稳赚项目', '割韭菜', '拉人头', '躺平赚钱', '睡觉都赚钱', '无脑赚',
        '挂机赚钱', '打字员日结', '刷单', '兼职日入',
    ],
    'import': [
        '加微信', '加V', '加VX', '加WX', '加v信', '加好友', '加我好友',
        '威信', '薇信', '微❤', 'V❤', '+V', '+v', '+VX', 'vx号', 'VX号',
        '私聊', '联系我', '联系方式在主页', '主页联系方式', '看主页',
        '简介有联系方式', '简介自取', '拨打电话', '电话联系', '电话在简介',
        '扫码', '扫二维码', '二维码进群', '扫码进群', '进群', '进群领取',
        '社群福利', '加群', '入驻链接', '外部链接', '复制此链接',
    ],
    'fake': [
        '永久', '永久有效', '永久免费', '终身', '终身免费', '终身使用',
        '无效退款', '不满意退款', '随时退', '包治', '包好', '包过',
        '立竿见影', '一学就会', '秒会', '三天学会', '7天见效', '一次见效',
        '祖传', '秘方', '神效', '奇效', '破价', '亏本清仓', '跳楼价',
        '清仓大甩卖', '免税', '畅销全球', '无人不知', '世界首创',
        '全球首发', '全网爆款', '断货王', '点击就送', '错过再等一年',
        '最后一天', '仅此一天',
    ],
}

# ── 高频词替换建议（没有建议的词不给，宁缺毋滥）──────────────

SUGGEST: Dict[str, str] = {
    '最好': '相当不错', '最佳': '优质', '最优': '优选', '最强': '能打',
    '第一': '领先', 'NO.1': '口碑之选', '顶级': '高端', '顶尖': '专业级',
    '独家': '自主研发', '首发': '新品', '首款': '新推出', '唯一': '少见',
    '万能': '多用途', '百分百': '高比例', '100%有效': '效果因人而异',
    '首选': '值得考虑', '完美': '完成度高', '绝对': '相对靠谱',
    '永久': '长期', '终身': '长期', '秒杀': '限时优惠', '治疗': '呵护',
    '根治': '改善', '瘦身': '身材管理', '燃脂': '轻体计划', '美白': '提亮',
    '稳赚': '有机会获得回报', '零风险': '风险自评', '躺赚': '副业尝试',
    '包治': '针对性护理', '立竿见影': '逐步改善', '秘方': '配方',
    '祖传': '配方',
    '加微信': '通过官方渠道联系', '私聊': '官方客服', '扣1': '留言交流',
    '求关注': '感兴趣可以关注', '免费送': '福利活动',
}

# ── 检测引擎 ───────────────────────────────────────────────

_COMPILED: Dict[str, re.Pattern] = {
    cat: re.compile('|'.join(re.escape(w) for w in sorted(ws, key=len, reverse=True)),
                    re.IGNORECASE)
    for cat, ws in WORDS.items() if ws
}

# ── 用户覆盖层（2026-10-11：看板热管理）────────────────────
# _DISABLED：被停用的词（内置/自定义都可停）
# _EXTRA：自定义新增词 {category: [word, ...]}
# 两者由 refresh_overrides() 依据 db 覆盖表重建，_COMPILED 随之热刷新。
_DISABLED: set = set()
_EXTRA: Dict[str, List[str]] = {}
_CUSTOM_SUGGEST: Dict[str, str] = {}       # 自定义词 → 替换建议


def refresh_overrides(snapshot: Dict[str, Dict[str, Any]]) -> None:
    """应用用户覆盖（main.py 启动时 & 看板改词后调用）。

    snapshot 来自 db.banned_custom_snapshot()：
        {word: {category, suggest, enabled}}
    内置词被停用 → 从 _COMPILED 移除；自定义启用词 → 并入所属类目。
    """
    global _COMPILED, _DISABLED, _EXTRA, _CUSTOM_SUGGEST
    _DISABLED = {w for w, v in snapshot.items() if not v['enabled']}
    _EXTRA = {}
    _CUSTOM_SUGGEST = {}
    for w, v in snapshot.items():
        if v['enabled'] and v['category'] in CATEGORIES:
            _EXTRA.setdefault(v['category'], []).append(w)
            if v.get('suggest'):
                _CUSTOM_SUGGEST[w] = v['suggest']
    _COMPILED = {}
    for cat in CATEGORIES:
        ws = [w for w in WORDS.get(cat, []) if w not in _DISABLED]
        ws += [w for w in _EXTRA.get(cat, []) if w not in _DISABLED]
        if ws:
            _COMPILED[cat] = re.compile(
                '|'.join(re.escape(w) for w in sorted(ws, key=len, reverse=True)),
                re.IGNORECASE)


def builtin_category(word: str) -> str:
    """查内置词所属类目（看板停用内置词时需要回填 category）。"""
    for cat, ws in WORDS.items():
        if word in ws:
            return cat
    return ''


def words_merged(snapshot: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """看板展示用合并视图：内置词（可被停用）+ 自定义词。

    返回 [{word, category, suggest, source, enabled}]，按类目+词排序。
    suggest 取值优先级：覆盖行 > 内置 SUGGEST 表。
    """
    out: Dict[str, Dict[str, Any]] = {}
    for cat, ws in WORDS.items():
        for w in ws:
            out[w] = {'word': w, 'category': cat,
                      'suggest': SUGGEST.get(w, ''),
                      'source': 'builtin', 'enabled': True}
    for w, v in snapshot.items():
        if w in out:
            out[w]['enabled'] = bool(v['enabled'])
            if v.get('suggest'):
                out[w]['suggest'] = v['suggest']
        else:
            out[w] = {'word': w, 'category': v['category'],
                      'suggest': v.get('suggest', ''),
                      'source': 'custom', 'enabled': bool(v['enabled'])}
    return sorted(out.values(), key=lambda x: (x['category'], x['word']))


def detect(text: str, full: bool = False) -> Dict[str, Any]:
    """检测文案中的违禁词。

    full=False 只查免费类目（adlaw/induce），full=True 查全类目。
    返回：
        total        命中总次数
        risk_level   high（≥3 或含 high 危类）/ medium（1~2）/ clean
        marks        [{start, end, word, category}] —— 按出现位置排序、
                     跨类目去重叠（保留先出现者），供前端原文标红
        groups       按类目聚合 [{category, name, risk, count,
                                  words:[{word, count, suggest}]}]
        locked       被会员门槛锁住的类目名列表（full=False 时提示升级）
    """
    text = text or ''
    if not text.strip():
        return {'total': 0, 'risk_level': 'clean', 'marks': [],
                'groups': [], 'locked': []}

    cats = set(_COMPILED.keys()) if full else FREE_CATEGORIES
    locked = sorted(c for c in _COMPILED.keys() if c not in cats)

    raw: List[Dict[str, Any]] = []
    for cat, pattern in _COMPILED.items():
        if cat not in cats:
            continue
        for m in pattern.finditer(text):
            raw.append({'start': m.start(), 'end': m.end(),
                        'word': m.group(0), 'category': cat})
    raw.sort(key=lambda x: (x['start'], -(x['end'] - x['start'])))

    # 跨类目去重叠：保留起点最早、覆盖最长的命中
    marks: List[Dict[str, Any]] = []
    last_end = -1
    for m in raw:
        if m['start'] >= last_end:
            marks.append(m)
            last_end = m['end']

    # 聚合
    agg: Dict[str, Dict[str, Any]] = {}
    # 建议优先级：内置 SUGGEST 表 > 用户自定义建议（看板热管理 2026-10-11）
    suggest_map = {k.lower(): v for k, v in SUGGEST.items()}
    suggest_map.update({k: v for k, v in _CUSTOM_SUGGEST.items()
                        if k not in suggest_map})
    for m in marks:
        g = agg.setdefault(m['category'], {})
        item = g.setdefault(m['word'], {'count': 0})
        item['count'] += 1
    groups: List[Dict[str, Any]] = []
    total = 0
    for cat, words in agg.items():
        meta = CATEGORIES[cat]
        wl = [{'word': w, 'count': d['count'],
               'suggest': suggest_map.get(w.lower(), '')}
              for w, d in sorted(words.items(),
                                 key=lambda x: -x[1]['count'])]
        total += sum(w['count'] for w in wl)
        groups.append({'category': cat, 'name': meta['name'],
                       'risk': meta['risk'],
                       'count': sum(w['count'] for w in wl), 'words': wl})
    groups.sort(key=lambda g: -g['count'])

    high_cats = {'medical', 'money'}
    has_high = any(g['category'] in high_cats for g in groups)
    risk_level = ('clean' if total == 0
                  else 'high' if total >= 3 or has_high else 'medium')

    return {'total': total, 'risk_level': risk_level, 'marks': marks,
            'groups': groups, 'locked': locked}


def build_segments(text: str, marks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """原文 + 命中标记 → 前端渲染用的分段数组（hit=True 的片段标红）。"""
    segs: List[Dict[str, Any]] = []
    pos = 0
    for m in marks:
        if m['start'] > pos:
            segs.append({'t': text[pos:m['start']], 'hit': False})
        segs.append({'t': text[m['start']:m['end']], 'hit': True})
        pos = m['end']
    if pos < len(text):
        segs.append({'t': text[pos:], 'hit': False})
    return segs


# ── 自检 ───────────────────────────────────────────────────
if __name__ == '__main__':
    sample = ('全网最低价！祖传秘方，包治近视，用了都说好。'
              '加微信领福利，扣1免费送，稳赚不赔月入十万！')
    r = detect(sample, full=True)
    print('total:', r['total'], '| risk:', r['risk_level'])
    for g in r['groups']:
        print(f"  [{g['name']}] {g['count']} 处: "
              + ', '.join(w['word'] for w in g['words']))
    segs = build_segments(sample, r['marks'])
    print('segments:', ''.join(('【' + s['t'] + '】' if s['hit'] else s['t'])
                               for s in segs))
