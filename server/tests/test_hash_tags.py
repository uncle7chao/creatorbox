"""话题提取测试（app/meta.py 的 extract_hash_tags）

⭐ 这个测试存在的理由：**原实现的正则要求话题两侧都有 #**，
   那是小红书/微博的格式。抖音只有前侧 #，
   导致抖音的 tags 恒为空数组（实测：title 里明明有 5 个话题，tags 是 []）。

   这种 bug 不会让服务报错，只是「功能静默失效」，
   没有断言守护就永远发现不了。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.meta import extract_hash_tags, _clean_tag, normalize_meta  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✅' if cond else '  ❌') + ' ' + name +
          (f'  | {detail}' if detail and not cond else ''))


print('\n── 各平台格式（实测数据）──')
check('抖音（前侧#）能提出来',
      extract_hash_tags('外卖42元一份的猪脚饭真的好吃吗？ '
                        '#分享你的快餐推荐 #猪脚饭 #真实生活分享计划 '
                        '#美食分享 #快餐')
      == ['分享你的快餐推荐', '猪脚饭', '真实生活分享计划', '美食分享', '快餐'],
      str(extract_hash_tags('外卖42元一份的猪脚饭真的好吃吗？ '
                            '#分享你的快餐推荐 #猪脚饭 #真实生活分享计划 '
                            '#美食分享 #快餐')))

check('微博（双侧#）能提出来',
      extract_hash_tags('这个真的好看 #今日穿搭# #ootd#') == ['今日穿搭', 'ootd'],
      str(extract_hash_tags('这个真的好看 #今日穿搭# #ootd#')))

check('小红书（[话题]后缀）被剥掉',
      extract_hash_tags('好绝的蛋糕 #美食[话题]# #甜品[话题]#') == ['美食', '甜品'],
      str(extract_hash_tags('好绝的蛋糕 #美食[话题]# #甜品[话题]#')))

check('无话题返回空列表', extract_hash_tags('就是一段普通文字') == [])
check('空输入安全', extract_hash_tags('') == [])
check('None 安全', extract_hash_tags(None) == [])

print('\n── 误提防护 ──')
check('URL 里的 # 不被误提',
      extract_hash_tags('看这个 https://x.com/a#b 还有 #真话题#') == ['真话题'],
      str(extract_hash_tags('看这个 https://x.com/a#b 还有 #真话题#')))
check('www 域名里的 # 不被误提',
      extract_hash_tags('www.x.com/a#b #真话题#') == ['真话题'],
      str(extract_hash_tags('www.x.com/a#b #真话题#')))
check('@提及不算话题',
      extract_hash_tags('@某人 说的话 #话题A') == ['话题A'],
      str(extract_hash_tags('@某人 说的话 #话题A')))
check('重复话题去重',
      extract_hash_tags('#同一个 #同一个 #另一个') == ['同一个', '另一个'],
      str(extract_hash_tags('#同一个 #同一个 #另一个')))
check('超长话题被限制长度（正则本身限 24）',
      all(len(t) <= 24 for t in extract_hash_tags('#' + 'x' * 60 + ' #ok')),
      str(extract_hash_tags('#' + 'x' * 60 + ' #ok')))

print('\n── _clean_tag ──')
check('去掉首尾 #', _clean_tag('#话题#') == '话题')
check('去掉 [话题] 后缀', _clean_tag('美食[话题]') == '美食')
check('去掉全角［话题］', _clean_tag('美食［话题］') == '美食')
check('空值返回空串', _clean_tag('') == '')
check('None 返回空串', _clean_tag(None) == '')

print('\n── 走 normalize_meta（真实出口）──')
res = {'platform': 'douyin',
       'title': '外卖42元一份的猪脚饭真的好吃吗？ #分享你的快餐推荐 #猪脚饭',
       'description': '外卖42元一份的猪脚饭真的好吃吗？ #分享你的快餐推荐 #猪脚饭',
       'cover': 'https://x/c.jpg', 'video_url': 'https://x/v.mp4'}
out = normalize_meta(res)
check('normalize_meta 后 tags 非空', bool(out.get('tags')), str(out.get('tags')))
check('tags 内容正确',
      out.get('tags') == ['分享你的快餐推荐', '猪脚饭'], str(out.get('tags')))
check('copy_text 回填到 result（前端读顶层字段）',
      bool(res.get('copy_text')), str(res.get('copy_text')))
check('copy_text 含完整文案',
      '猪脚饭' in (res.get('copy_text') or ''), str(res.get('copy_text')))

print('\n── copy_text 的回落规则 ──')
res2 = {'platform': 'bilibili',
        'title': '【官方 MV】Never Gonna Give You Up - Rick Astley',
        'description': '-'}
out2 = normalize_meta(res2)
check('B站 description 是 "-" 时回落 title（不复制出破折号）',
      out2.get('copy_text') == '【官方 MV】Never Gonna Give You Up - Rick Astley',
      repr(out2.get('copy_text')))
check('copy_text 不会等于 "-"',
      (out2.get('copy_text') or '').strip() != '-')

res3 = {'platform': 'x', 'title': '只有标题', 'description': ''}
out3 = normalize_meta(res3)
check('description 为空时回落 title',
      out3.get('copy_text') == '只有标题', repr(out3.get('copy_text')))

res4 = {'platform': 'x', 'title': '标题', 'description': '这是正文内容'}
out4 = normalize_meta(res4)
check('description 有效时优先用它',
      out4.get('copy_text') == '这是正文内容', repr(out4.get('copy_text')))

print('\n── 回归：话题提取不能影响其它字段 ──')
res5 = {'platform': 'douyin', 'title': '普通标题', 'description': '普通文案',
        'cover': 'https://x/c.jpg'}
out5 = normalize_meta(res5)
check('无 # 的文本不产生话题', out5.get('tags') == [], str(out5.get('tags')))
check('title 不被改', out5.get('title') == '普通标题')
check('description 不被改', out5.get('description') == '普通文案')

print(f'\n════ 话题提取：{len(PASS)} 通过 / {len(FAIL)} 失败')
sys.exit(1 if FAIL else 0)