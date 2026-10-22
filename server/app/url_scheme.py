"""资源URL 协议规范化：把 http:// 升级为 https://

## 为什么必须有这个模块

微信小程序（以及 iOS ATS / 现代浏览器 / 大部分 CDN 策略）**只允许 https**。
部分平台的 CDN 仍返回 `http://` 的直链，例如：

    百度的 cover     http://f7.baidu.com/it/u=...
    百度的 video_url http://vd3.bdstatic.com/mda-.../1080p/cae_h264/...

这些URL 在浏览器里能打开、在小程序里**必然加载失败**——
表现是「视频卡一片黑、封面不显示」，但服务端日志与接口响应全部正常，
**排查方向会被完全带偏**（会以为是封面字段没下发、或渲染逻辑写错了）。

实测（2026-10-22）：把 `http://` 换成 `https://` 后两个 URL 都返回 200，
`Content-Length` 与原 http 完全一致（封面 111482B / 视频 76643219B）。
CDN 普遍同一资源同时监听 80 与 443，改协议不会改变内容。

## 为什么不写在客户端

- 小程序、Flutter、App 三个端都要改 → 改三遍，且**极易漏掉一端**
- 服务端是唯一出口，改一次三个端同时受益
- 顺带解决「未来新增平台又返回 http」的问题（不改代码就自动正确）

## 为什么不做探测式回退

有人会想「先试 https，失败再退回 http」。这里刻意不做：

1. 小程序端**根本不允许 http 退路** —— 退回去也是失败，只是多了个请求
2. 探测会让每次解析多 1~2 个 RTT，直接拖慢首屏
3. https 在CDN 侧已经是「同等资源的加密入口」，退到 http 是倒退而非兜底

⚠️ 唯一需要注意的边界：**极少数只监听 80 的老旧 CDN** 会让升级后 404。
真遇到时（表现为「升级后所有该平台都失败」），应当**为该平台显式豁免**，
而不是把整体降级 —— 一家平台的问题不该拖累所有平台。
`EXEMPT_HOSTS` 就是为此预留的。
"""

import re
from typing import Any, Dict, Iterable, List, Optional

# 需要逐个升级的 URL 字段名。
# 用显式白名单而非递归扫描 —— 递归会把 page_url / short_url 这类
# 「只是给用户看的来源链接」也一起改，虽然无害但会让「来源链接可点击
# 复现原始解析条件」的语义变得不精确。
_URL_FIELDS = (
    'video_url',      # 视频直链
    'cover',          # 封面
    'music_url',      # BGM 音频
    'subtitle_url',   # 字幕文件
    'live_photo_url', # 实况图/动图
)

# 同类字段的列表形态（如多档 options 里的 url、多张图的 images[].url）
_LIST_FIELDS = ('images', 'options', 'qualities', 'segments')

# 豁免名单：只监听 80 端口的老旧 CDN 填这里（形如'cdn.example.com'）。
# ⚠️ 保持为空 —— 加之前先确认该域名的 https 真的不可用，
#    否则等于为一家平台牺牲全部平台的健壮性。
EXEMPT_HOSTS: tuple = ()


def https_url(url: Optional[str]) -> Optional[str]:
    """单个 URL 的协议升级。空值原样返回，不编造。"""
    if not url or not isinstance(url, str):
        return url
    if not url.startswith('http://'):
        return url
    host = url[7:].split('/', 1)[0].split('?', 1)[0].split('#', 1)[0]
    # 去掉端口号后比对，避免 'cdn:8080' 匹配不到 'cdn'
    bare = host.split(':', 1)[0].lower()
    if bare in EXEMPT_HOSTS or host.lower() in EXEMPT_HOSTS:
        return url
    return 'https://' + url[7:]


def _upgrade_obj(obj: Dict[str, Any]) -> None:
    """就地升级一个 dict 里的 URL 字段。"""
    for f in _URL_FIELDS:
        if isinstance(obj.get(f), str):
            obj[f] = https_url(obj[f])


def upgrade_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """升级解析结果里所有可下载资源的 URL。

    只动【资源直链】，不动 page_url / short_url / share_url：
    那几个是「这条结果从哪来」的溯源信息，改协议没有收益，
    却会让用户复制出来的来源链接与原平台不一致。

    就地修改并返回同一对象（调用方多数已经持有它）。
    """
    if not isinstance(result, dict):
        return result

    _upgrade_obj(result)

    for lf in _LIST_FIELDS:
        items = result.get(lf)
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, dict):
                _upgrade_obj(it)
                # 有些解析器把直链放在 key/url/link/backup_url 等别名下
                for k in ('url', 'link', 'backup_url', 'src'):
                    if isinstance(it.get(k), str):
                        it[k] = https_url(it[k])
                # 多清晰度常见的分层字段。
                # ⚠️ backups 里装的是【字典】而非字符串（第一版只处理了
                #    urls 里的字符串，漏掉 backups → 备选清晰度仍是 http）。
                #    这种情况只有真跑一遍才会发现 —— 断言能覆盖，但要先写出来。
                for k in ('urls', 'backups'):
                    sub = it.get(k)
                    if isinstance(sub, list):
                        for i, s in enumerate(sub):
                            if isinstance(s, str):
                                sub[i] = https_url(s)
                            elif isinstance(s, dict):
                                _upgrade_obj(s)
                                for k2 in ('url', 'link', 'backup_url', 'src'):
                                    if isinstance(s.get(k2), str):
                                        s[k2] = https_url(s[k2])
    return result


def count_http(result: Dict[str, Any]) -> int:
    """统计结果里仍残留的 http:// 资源直链数（自检/测试用）。

    正常升级后应为 0。残留意味着有新字段没被纳入 _URL_FIELDS ——
    这时该补字段，而不是让客户端去容错 http。
    """
    n = 0
    if not isinstance(result, dict):
        return 0

    def scan(v: Any, depth: int = 0) -> None:
        nonlocal n
        if depth > 6:
            return
        if isinstance(v, str):
            if v.startswith('http://'):
                n += 1
        elif isinstance(v, dict):
            for x in v.values():
                scan(x, depth + 1)
        elif isinstance(v, list):
            for x in v:
                scan(x, depth + 1)

    for f in _URL_FIELDS + _LIST_FIELDS:
        if f in result:
            scan(result[f])
    return n