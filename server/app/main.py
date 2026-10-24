"""
CreatorBox 解析服务
==================
POST /api/parse        解析分享口令
GET  /api/health       健康检查（含平台改版预警）
POST /api/batch        批量解析
"""
import asyncio
import hashlib
import io
import logging
import os
import time
from typing import Dict, List
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (Body, Depends, FastAPI, File, Header, HTTPException, Request,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger('creatorbox')

try:
    from app import config
    from app import db
    from app import domains
    from app import ffmpeg_util
    from app import health
    from app import m3u8_merge
    from app import meta
    from app import size_probe
    from app.cache import cache, limiter
    from app.parsers.acfun_pure import AcfunPureParser
    from app.parsers.baidu_pure import BaiduVideoPureParser
    from app.parsers.base import URL_RE, ParserRegistry
    from app.parsers.bilibili_pure import BilibiliPureParser
    from app.parsers.douyin_pure import DouyinPureParser
    from app.parsers.haokan_pure import HaokanPureParser
    from app.parsers.kuaishou_pure import KuaishouPureParser
    from app.parsers.sohu_pure import SohuPureParser
    from app.parsers.weibo_pure import WeiboPureParser
    from app.parsers.xiaohongshu_pure import XiaohongshuPureParser
    from app.capabilities import CAPABILITY, WHITELIST_HINT
    from app import pdftools
    from app import knowledge
    from app import trending
    from app import visibility
except ImportError:
    import config
    import db
    import domains
    import ffmpeg_util
    import health
    import m3u8_merge
    import meta
    from cache import cache, limiter
    from parsers.acfun_pure import AcfunPureParser
    from parsers.baidu_pure import BaiduVideoPureParser
    from parsers.base import URL_RE, ParserRegistry
    from parsers.bilibili_pure import BilibiliPureParser
    from parsers.douyin_pure import DouyinPureParser
    from parsers.haokan_pure import HaokanPureParser
    from parsers.kuaishou_pure import KuaishouPureParser
    from parsers.sohu_pure import SohuPureParser
    from parsers.weibo_pure import WeiboPureParser
    from parsers.xiaohongshu_pure import XiaohongshuPureParser
    from capabilities import CAPABILITY, WHITELIST_HINT
    from pdftools import __name__ as _pdftools_ok  # noqa
    import trending
    import visibility

# 浏览器解析器（playwright）按需惰性导入 —— 缺依赖不影响纯 HTTP 平台
try:
    from app.parsers.douyin import DouyinParser
    from app.parsers.bilibili import BilibiliParser
    from app.parsers.signed_platforms import XhsParser
    _HAS_BROWSER = True
except Exception:          # pragma: no cover - 取决于运行环境
    DouyinParser = BilibiliParser = None
    KuaishouParser = XhsParser = None
    _HAS_BROWSER = False


# ---------- 实例池 ----------

class Pool:
    """解析器池 —— 纯 HTTP 优先，浏览器仅作兜底

    2026-10-05 改造：读parse-video-py / uvd 源码后找到免签名通道，
    纯 HTTP 覆盖抖音（视频+图集）与B站，浏览器降为三级兜底。
    单实例内存从 500MB-1GB 降到 ~50MB。
    """

    def __init__(self, n: int):
        # 【一级】纯 HTTP，无需浏览器
        # 2026-10-05：抖音 / B站 / 好看视频 / 搜狐 / 微博 / AcFun 全部纯 HTTP。
        # - 好看视频原记「需浏览器过滑块」，二次实测证明只需访问首页拿 cookie（P11）
        # - 微博拿到真实 oid 后实测 3 档 1080P 可用
        # - AcFun SSR 即含完整数据，5 档最高 1080P+
        # - 快手实测被反爬滑块拦截（400002 + captcha），判定不接入
        self.pure = [
            DouyinPureParser(),
            BilibiliPureParser(),
            # 百度系两个产品：haokan（好看视频）与 baidu（信息流视频），
            # URL 与接口形态不同，match 规则互不重叠
            HaokanPureParser(),
            BaiduVideoPureParser(),
            SohuPureParser(),
            WeiboPureParser(),
            AcfunPureParser(),
            XiaohongshuPureParser(),
            KuaishouPureParser(),
        ]
        # 【国际平台】2026-10-11：X / TikTok（香港服务器直连优势）
        # CB_INTL_ENABLED=0 可整体关闭（提审构建用），详见 docs/国际平台解析竞品拆解与开发方案v2.md
        if config.INTL_ENABLED:
            try:
                from app.parsers.intl.x_pure import XPureParser
                from app.parsers.intl.tiktok_pure import TikTokPureParser
                from app.parsers.intl.youtube_pure import YouTubeParser
                from app.parsers.intl.fb_pure import FacebookParser
            except ImportError:
                from parsers.intl.x_pure import XPureParser
                from parsers.intl.tiktok_pure import TikTokPureParser
                from parsers.intl.youtube_pure import YouTubeParser
                from parsers.intl.fb_pure import FacebookParser
            self.pure += [XPureParser(), TikTokPureParser(),
                          YouTubeParser(), FacebookParser()]
        self.by_name = {p.name: p for p in self.pure}

        # 【三级兜底】Playwright，仅当纯 HTTP 全失败时启用
        self.instances = []
        self.bili = None
        if config.ENABLE_BROWSER_FALLBACK and _HAS_BROWSER:
            self.instances = [
                DouyinParser(headless=config.HEADLESS, instance_id=i)
                for i in range(n)]
            if config.ENABLE_BILIBILI:
                self.bili = BilibiliParser(headless=config.HEADLESS)

        # 需签名的平台（实验性，仍未攻克）
        # ⚠️ 2026-10-05：快手已由 KuaishouPureParser（纯 HTTP 走
        #    m.gifshow.com）接管，这里**移除 KuaishouParser** ——
        #    否则会留下一个永不生效的死分支，维护时容易误以为它在跑。
        #    小红书同理，已由 XiaohongshuPureParser 接管。
        self.signed = ([XhsParser(headless=config.HEADLESS)]
                       if (_HAS_BROWSER and config.ENABLE_SIGNED) else [])

        self._idx = 0
        self._lock = asyncio.Lock()

    async def pick_platform(self, url: str):
        """按 URL 选平台解析器（返回元组：纯HTTP优先）

        ⚠️ 2026-10-22 修正：原实现最后 `return self.pure[0], None` ——
           任何**不认识**的域名都会被当成抖音去解析，报「短链未解析出 aweme_id」。
           这个错误信息把用户引向错误方向（以为是抖音抽风，其实是平台不支持），
           比如百度视频/西瓜视频这类未接入的域名就会这样。

           现在改成返回 None，调用方据此报「暂不支持该平台」并给出已支持清单。
        """
        for p in self.pure:
            if p.match(url):
                return p, None
        for p in self.signed:
            if p.match(url):
                return p, None
        if self.instances:
            async with self._lock:
                inst = self.instances[self._idx % len(self.instances)]
                self._idx += 1
            return inst, inst
        return None, None

    async def start_all(self):
        names = '/'.join(p.name for p in self.pure)
        print(f'[pool] 纯 HTTP 解析器就绪（{names}，零浏览器）')
        if not _HAS_BROWSER:
            print('[pool] 未安装 playwright，浏览器兜底通道不可用'
                  '（不影响上面 4 个纯 HTTP 平台）')
        for inst in self.instances:
            try:
                await inst.start()
                print(f'[pool] douyin#{inst.instance_id} ready (fallback)')
            except Exception as e:
                print(f'[pool] douyin#{inst.instance_id} 启动失败: {str(e)[:80]}')
        if self.bili:
            try:
                await self.bili.start()
                print('[pool] bilibili ready (fallback)')
            except Exception as e:
                print(f'[pool] bilibili 启动失败: {str(e)[:80]}')
        for p in self.signed:
            try:
                await p.start()
                print(f'[pool] {p.name} ready')
            except Exception as e:
                print(f'[pool] {p.name} 启动失败: {str(e)[:80]}')
        if not self.signed and config.ENABLE_SIGNED:
            print('[pool] 小红书/快手签名通道已关闭，不启动浏览器')
        elif not self.signed:
            print('[pool] 小红书/快手签名通道未启用，不启动浏览器')

    async def stop_all(self):
        for inst in self.instances:
            try:
                await inst.stop()
            except Exception:
                pass
        if self.bili:
            try:
                await self.bili.stop()
            except Exception:
                pass
        for p in self.signed:
            try:
                await p.stop()
            except Exception:
                pass

    async def pick(self) -> DouyinParser:
        """轮询取实例（每个实例内部自带锁，串行）"""
        async with self._lock:
            inst = self.instances[self._idx % len(self.instances)]
            self._idx += 1
            return inst

    async def health(self) -> dict:
        # 纯 HTTP 通道健康度
        pure = {}
        for p in self.pure:
            try:
                pure[p.name] = await p.health()
            except Exception as e:
                pure[p.name] = {'ready': False, 'error': str(e)[:80]}

        # 浏览器兜底通道
        res = []
        if self.instances:
            res = await asyncio.gather(
                *[i.health() for i in self.instances],
                return_exceptions=True)
            res = [r for r in res if isinstance(r, dict)]

        total_ok = sum(x.get('ok', 0) for x in res) + \
            sum(1 for x in pure.values() if x.get('ready'))
        total_fail = sum(x.get('fail', 0) for x in res)
        total = total_ok + total_fail
        ratio = (total_fail / total) if total >= config.DEGRADE_MIN_SAMPLES else 0
        degraded = ratio > config.DEGRADE_FAIL_RATIO

        bili_h = {}
        if self.bili:
            try:
                bili_h = await self.bili.health()
            except Exception as e:
                bili_h = {'ready': False, 'error': str(e)[:80]}

        signed_h = {}
        for p in self.signed:
            try:
                signed_h[p.name] = await p.health()
            except Exception as e:
                signed_h[p.name] = {'ready': False, 'error': str(e)[:80]}

        return {
            'ready': all(x.get('ready') for x in pure.values()),
            'engine': ('pure_http' if not self.instances
                       else 'pure_http + browser_fallback'),
            'pure_http': pure,
            'browser_fallback': {
                'enabled': bool(self.instances),
                'instances': res,
                'bilibili': bili_h,
            },
            'instances': res,
            'total_ok': total_ok,
            'total_fail': total_fail,
            'fail_ratio': round(ratio, 3),
            'degraded': degraded,
            'alert': '平台接口可能已变更，失败率超阈值' if degraded else None,
            'bilibili': bili_h,
            'signed_platforms': signed_h,
            'platform_status': {
                name: ('ready' if pure.get(name, {}).get('ready') else 'down')
                for name in self.by_name
            },
            'browser_available': _HAS_BROWSER,
        }


pool = Pool(config.INSTANCE_COUNT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()          # SQLite：用户/配额/素材库/订单（幂等建表）
    # 违禁词库用户覆盖（2026-10-11）：启动即应用看板保存的增删决策
    from app import banned as _banned
    _banned.refresh_overrides(db.banned_custom_snapshot())
    await cache.init()
    await pool.start_all()
    # M1 Gate：平台健康度探针 + 域名注册表
    health.monitor.attach(pool.pure)
    health.monitor.start()

    # 封面压缩（2026-10-24）升级后，老的无版本前缀缓存永远命中不到 → 清掉省磁盘
    try:
        _purged = _purge_legacy_cover_cache()
        if _purged:
            logger.info('清理旧封面缓存 %d 个（压缩策略升级前的原图）', _purged)
    except Exception as e:
        logger.warning('清理旧封面缓存失败（不影响启动）: %s', str(e)[:60])

    # P2：PDF 产物定期清理（默认保留 1 天——1TB 月流量下不能堆积）
    async def _pdf_cleanup_loop():
        while True:
            await asyncio.sleep(6 * 3600)          # 每 6 小时清一次
            try:
                n = await asyncio.get_event_loop().run_in_executor(
                    None, pdftools.cleanup)
                if n:
                    print(f'[pdf-cleanup] 移除 {n} 个过期产物')
            except Exception as e:
                print(f'[pdf-cleanup] 异常: {str(e)[:60]}')

    app.state.pdf_cleanup_task = asyncio.create_task(_pdf_cleanup_loop())

    yield
    await health.monitor.stop()
    app.state.pdf_cleanup_task.cancel()
    await pool.stop_all()


app = FastAPI(title='CreatorBox Parser', version='2.0.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


# ---------- 模型 ----------

class ParseReq(BaseModel):
    text: str = Field(..., description='分享口令全文或纯链接')
    quality: str = Field('1080p', description='origin/1080p/720p/540p')
    no_cache: bool = Field(False, description='跳过缓存')


class BatchItem(BaseModel):
    text: str
    quality: str = '720p'          # 免费默认 720P（v2 方案），与 config.DEFAULT_QUALITY 一致
    no_cache: bool = Field(False, description='跳过缓存（批量调试用）')


class BatchReq(BaseModel):
    items: list[BatchItem]


async def check_auth(x_api_key: str = Header(default='')):
    """**管理类**端点鉴权（/api/admin/* 等）。

    ⚠️ 默认拒绝：API_KEY 为空时【不是不鉴权，而是全部拒绝】(503)。
       原实现是 `if config.API_KEY and ...` —— 空 Key 等于放行。
       一旦运维忘配 CB_API_KEY，卡密/违禁词/用户名单端点会直接裸奔。

    ⭐ 解析类端点（/api/parse、/api/batch 等）**不用这个**，
       它们用下面的 check_admin_or_open —— 那里的 C 端鉴权是
       openid + 配额 + 限流，与管理密钥无关。
       ⚠️ 千万别把「配了 Key 就校验」套到解析类：
       小程序/App 是 C 端用户，持有不了管理密钥 → 全线 401。
    """
    if not config.API_KEY:
        raise HTTPException(
            503,
            '服务端未配置 CB_API_KEY，管理接口已全部锁定。'
            '请在环境变量中设置后重启（本地自测可设 CB_API_KEY=dev）')
    if x_api_key != config.API_KEY:
        raise HTTPException(401, 'Invalid API key')


async def check_admin_or_open(x_api_key: str = Header(default='')):
    """**解析类**端点鉴权。

    ⭐ 2026-10-22 修正：这里**不再校验管理密钥 CB_API_KEY**。
       之前写成「配了 Key 就校验」，实测后果：小程序与 App 全部 401 ——
       因为小程序是 C 端用户，**不可能持有管理密钥**（那是运营后台用的）。
       生产环境必然配了 CB_API_KEY → C 端流量全被挡死。

    C 端的鉴权体系是另一套：
      · openid 主键（/api/parse 走游客 openid，由 /api/user/login 发放）
      · 配额闸（db.get_quota：免费 N 次/天）
      · 双层限流（limiter：IP + openid）
    这些都在端点内部做，与管理密钥无关。

    这里只保留一个**可选**的全局开关 CB_API_KEY_REQUIRED：
    仅当运营显式设为 1 时，解析类端点才要求携带 X-Api-Key
    （自建代理/内网互调场景用，正常 C 端不要开）。

    ⚠️ 不要把这里改回「校验 config.API_KEY」——
       那会让「配了管理密钥」直接等价于「C 端全挂」。
    """
    if getattr(config, 'API_KEY_REQUIRED', False):
        if not config.API_KEY:
            raise HTTPException(
                503, '服务端配置了 CB_API_KEY_REQUIRED 但未设置 CB_API_KEY')
        if x_api_key != config.API_KEY:
            raise HTTPException(401, 'Invalid API key')


# ---------- 平台改版预警 ----------

_health_history: list[dict] = []


def record_health(h: dict):
    _health_history.append({'t': time.time(), **{
        k: h.get(k) for k in ('total_ok', 'total_fail', 'fail_ratio', 'degraded')}})
    if len(_health_history) > 2000:
        del _health_history[:-1000]


# ---------- 接口 ----------

class SingleFlight:
    """同 key 并发请求合并（方案 A，2026-10-08 防风控）

    场景：一条链接突然爆了，缓存 TTL 过期瞬间几十个用户同时请求。
    没有合并层 → 几十次真实解析同时打到平台（触发风控的典型姿势）。
    有了合并层 → 第 1 个请求真正干活，其余挂起等同一个结果，平台只看到 1 次。

    key 用与缓存一致的 hash（链接+清晰度），链接不同互不影响。
    """

    def __init__(self):
        self._inflight: dict = {}

    async def run(self, key: str, factory):
        fut = self._inflight.get(key)
        if fut is not None:
            # 在途任务已存在：等它出结果（它内部连异常都不会抛——解析器
            # 返回 {'success': False}，所以跟随者拿到的是完整结果对象）。
            # ⚠️ 给跟随者浅拷贝：批量场景下跟随者要改 index/cached 等字段，
            # 不能污染发起者已经返回、正在序列化的那份 dict。
            return dict(await fut), False
        fut = asyncio.get_event_loop().create_future()
        self._inflight[key] = fut
        try:
            result = await factory()
            if not fut.done():
                fut.set_result(result)
            return result, True
        except BaseException as e:      # noqa: 解析核心按契约不抛异常，兜底
            if not fut.done():
                fut.set_exception(e)
            raise
        finally:
            self._inflight.pop(key, None)


single_flight = SingleFlight()


async def _parse_one(text: str, quality: str, short: str, key: str) -> dict:
    """单链接解析核心（单条 /api/parse 与批量 /api/batch 共用）

    流程：平台选择 → 解析 → 跨库回退（西瓜→抖音）→ 浏览器兜底
          → 元信息规范化 → 流量统计 → CDN 域名记录 → 写缓存
    """
    primary, fallback = await pool.pick_platform(short)
    if primary is None:
        # ⚠️ 平台未接入 —— 明确说出来，并列出已支持的平台。
        # 别再用抖音去试（那会报「短链未解析出 aweme_id」，把人引向错误方向）。
        supported = '、'.join(sorted(
            {p.name.replace('_pure', '') for p in pool.pure
             if getattr(p, 'name', '')})) or '（无）'
        return {'success': False, 'platform': '',
                'error': f'暂不支持该平台链接（当前支持：{supported}）',
                'unsupported_platform': True}
    result = await primary.parse(text, quality)

    # 跨库回退：西瓜与抖音共用字节系 ID 体系
    # 实测（knowledge.FIELD_PATTERNS.ixigua）：slidesinfo 接口把 Referer
    # 换成 ixigua.com 同样返回抖音数据 → 西瓜链接可零成本试抖音解析器。
    # 只在「西瓜链接」上做，避免对其它平台乱试。
    if not result.get('success') and 'ixigua.com' in short:
        dy = pool.by_name.get('douyin_pure')
        if dy:
            alt = await dy.parse(text, quality)
            if alt.get('success'):
                alt['cross_platform_fallback'] = primary.name
                result = alt

    # 三级降级：纯 HTTP 失败 → 浏览器兜底
    if not result.get('success') and fallback is not None \
            and fallback is not primary:
        fb = await fallback.parse(text, quality)
        if fb.get('success'):
            fb['fallback_from'] = getattr(primary, 'name', 'pure')
            fb['method'] = (fb.get('method') or '') + '+browser_fallback'
            result = fb

    result['short_url'] = short
    result.setdefault('platform', getattr(primary, 'name', 'douyin'))

    # ---- 统一元信息（M2 前置，2026-10-05）----
    # 各平台解析器返回的字段名不统一（play_count / view_count /
    # playcnt / fmplaycnt 都表示播放量），前端要写 7 套判断。
    # 这里统一映射成 meta 子字典，前端只读 meta 即可。
    if result.get('success'):
        try:
            meta.normalize_meta(
                result, str(result.get('platform', '')).replace('_pure', ''))
        except Exception as e:      # noqa
            # 规范化失败**不能影响解析结果** —— 元信息是附加价值
            result['meta_error'] = str(e)[:80]

    # L2 真实流量统计（供健康度看板）
    t_parse = time.time()
    health.monitor.traffic.record(
        platform=str(result.get('platform', '')).replace('_pure', ''),
        ok=bool(result.get('success')),
        latency=time.time() - t_parse,
        error=str(result.get('error', '')),
        truncated=bool(result.get('truncated')))

    # 记录实际用到的 CDN 域名（用于反查平台是否新增了 CDN）
    for u in ([result.get('video_url')] +
              [o.get('url') for o in (result.get('options') or [])] +
              [i.get('url') for i in (result.get('images') or [])]):
        if u:
            domains.registry.record_probe(u, bool(result.get('success')))
            break   # 同一结果只记一个代表域名，避免噪声

    if result.get('success'):
        # 精简后再缓存，避免存整个 options 数组
        slim = {k: v for k, v in result.items() if k != 'options'}
        slim['options_count'] = len(result.get('options') or [])
        await cache.set(key, slim)

    return result


@app.post('/api/parse', dependencies=[Depends(check_admin_or_open)])
async def api_parse(req: ParseReq, request: Request):
    ident = request.client.host if request.client else 'global'
    ok, info = await limiter.allow(ident)
    if not ok:
        raise HTTPException(429, f'请求过于频繁，请 {info["retry_after"]}s 后重试')

    # ⭐ 缓存 key 用提取出的短链，不含分享文案
    # 否则同一视频「带文案」和「纯链接」会命中两份缓存
    m = URL_RE.search(req.text or '')
    if not m:
        return {'success': False, 'error': '未识别到链接'}
    short = m.group(0)
    key = hashlib.sha256(
        f'{short}|{req.quality}'.encode()).hexdigest()[:32]

    if not req.no_cache:
        cached = await cache.get(key)
        if cached:
            cached['cached'] = True
            return cached

    # ⭐ 方案 A：单链接并发锁 —— 同 key 并发请求合并为一次真实解析
    result, leader = await single_flight.run(
        key, lambda: _parse_one(req.text, req.quality, short, key))
    if not leader:
        result.setdefault('coalesced', True)   # 标记：蹭了在途请求的结果
    result['cached'] = False

    # ⭐ 文件大小探测（竞品对齐：视频卡显示「时长 + 大小」）
    # 只探【选中并将要返回的那一档】video_url，不探全部档位（8 档全探太慢）。
    # 拿不到就是 0（界面显示"大小未知"），不编造。
    await _attach_size(result)

    return result


async def _attach_size(result: dict) -> None:
    """给解析结果补 size 字段（字节）与人类可读文本。

    ⭐ 为什么放这里而不是解析器里：
       各平台字段不统一（抖音 bit_rate 可能带 data_size，但并非都有），
       逐平台适配是长期维护成本。HTTP HEAD/Range 拿 content-length 是通用的。
    ⚠️ 只探 video_url 一个地址，且失败静默 —— 探测失败不该让整个解析失败。
    """
    if not result or not result.get('success'):
        return
    if result.get('type') != 'video':
        return
    url = result.get('video_url') or ''
    if not url:
        return
    try:
        n = await size_probe.probe_size(url)
    except Exception:
        n = 0
    if n:
        result['size'] = n
        result['size_text'] = size_probe.human_size(n)
    else:
        result['size'] = 0
        result['size_text'] = ''
    # 时长文本（客户端也要，格式化口径统一放服务端）
    result['duration_text'] = size_probe.human_duration(result.get('duration_ms'))


# ---------- 用户 / 配额 / 云端素材库（P0，2026-10-07） ----------

class LoginReq(BaseModel):
    code: str = Field('', description='wx.login 的 code；空则走游客态')
    device_id: str = Field('', description='游客态设备标识（未配微信secret时使用）')
    nickname: str = Field('', description='昵称（可选，用户授权后补传）')
    avatar_url: str = Field('', description='头像（可选）')


class PointsReq(BaseModel):
    openid: str = Field('', description='用户 openid（客户端已持有）')


def _openid_from_code(code: str) -> str:
    """code2Session 换 openid。
    未配置 WX_SECRET（M1.5 支付前）→ 返回空串，调用方降级游客态。
    """
    if not (config.WX_APPID and config.WX_SECRET and code):
        return ''
    import json as _json
    import urllib.request as _u
    url = ('https://api.weixin.qq.com/sns/jscode2session'
           f'?appid={config.WX_APPID}&secret={config.WX_SECRET}'
           f'&js_code={code}&grant_type=authorization_code')
    try:
        with _u.urlopen(url, timeout=8) as r:
            d = _json.loads(r.read().decode('utf-8'))
        return d.get('openid') or ''
    except Exception:      # noqa —— 微信侧抖动不能挡登录
        return ''


@app.post('/api/user/login')
async def api_user_login(req: LoginReq):
    """登录：微信 code 优先，缺失降级游客态（device_id）。

    ⚠️ 游客态限制：配额以 device_id 计 —— 卸载重装会重置，
    支付接入后（M1.5）必须走正式 openid，游客配额仅是过渡。
    """
    openid = _openid_from_code(req.code)
    via = 'wechat'
    if not openid:
        if not req.device_id:
            raise HTTPException(400, '缺少 code 或 device_id')
        openid = 'guest_' + req.device_id[:40]
        via = 'guest'
    user = db.upsert_user(openid, req.nickname or '', req.avatar_url or '')
    return {
        'openid': openid,
        'via': via,
        'user_id': user.get('user_id') or '',   # 账号中台：跨端主键随登录下发
        'is_member': bool(user.get('is_member')),
        'quota': db.get_quota(openid),
    }


# ---------- 账号中台·跨端桥接（v4 §2.4，2026-10-11）----------
# App/PC 本地身份 → 桥接码 → 小程序确认 → 轮询换 token。openid 链路零改动。

class BridgeCreateReq(BaseModel):
    provider: str = Field(..., description='对端身份类型，如 app_device / pc_device')
    provider_uid: str = Field(..., description='对端本地身份标识（安装时生成的 uuid）')


class BridgeConfirmReq(BaseModel):
    openid: str = Field(..., description='小程序用户标识')
    code: str = Field(..., description='6 位桥接码')


class BridgePollReq(BaseModel):
    provider: str = Field(...)
    provider_uid: str = Field(...)


@app.post('/api/auth/bridge/create')
async def api_bridge_create(req: BridgeCreateReq,
                             x_user_token: str = Header(default='')):
    """App/PC 发起绑定：返回一次性 6 位码（5 分钟有效），用户去小程序输入。

    若已登录（带 token），把出码发起方记进 bridge_codes.user_id ——
    这样用户中途注销时能精确清掉自己名下所有未确认的码（防孤儿码被他人绑定）。
    未登录时不记，行为与从前一致。
    """
    if not req.provider or not req.provider_uid:
        raise HTTPException(400, '缺少 provider / provider_uid')
    by_user = ''
    if x_user_token:
        u = db.resolve_token(x_user_token)
        by_user = (u or {}).get('user_id', '')
    r = db.bridge_create(req.provider.strip(), req.provider_uid.strip(),
                          by_user_id=by_user)
    if not r.get('ok'):
        raise HTTPException(400, r.get('reason') or 'bridge_create_failed')
    return r


@app.post('/api/auth/bridge/confirm')
async def api_bridge_confirm(req: BridgeConfirmReq):
    """小程序端确认：把桥接码对应的对端身份绑到自己的 user_id 上。"""
    r = db.bridge_confirm(req.openid, req.code)
    if not r.get('ok'):
        raise HTTPException(400, r.get('reason') or 'bridge_confirm_failed')
    return r


@app.post('/api/auth/bridge/poll')
async def api_bridge_poll(req: BridgePollReq):
    """App/PC 轮询：身份已绑定 → 签发 90 天 token。未绑定返回 400 not_bound。"""
    r = db.bridge_poll(req.provider.strip(), req.provider_uid.strip())
    if not r.get('ok'):
        raise HTTPException(400, r.get('reason') or 'not_bound')
    return r


@app.get('/api/auth/me')
async def api_auth_me(x_user_token: str = Header(default='')):
    """token → 账号全貌（跨端通用身份接口，Flutter 端的登录态来源）。"""
    u = db.resolve_token(x_user_token)
    if not u:
        raise HTTPException(401, 'token 无效或已过期')
    return {
        'user_id': u['user_id'],
        'nickname': u['nickname'],
        'avatar_url': u['avatar_url'],
        'member': db.get_member_state(u['openid']),
        'identities': [dict(r) for r in db.identities_of(u['user_id'])],
    }


@app.get('/api/auth/openid')
async def api_auth_openid(x_user_token: str = Header(default='')):
    """token → openid（Flutter 端调用「按 openid 索引」的存量接口时用）。

    为什么需要（v4 §2.4 openid 全链路零改动）：
    素材库 / 配额 / 会员 / 违禁词 等存量接口都以 openid 为主键，
    而 App/PC 端手里只有 token。让客户端在每次调用时传 openid，
    等于把 openid 暴露给跨端并要求它缓存 —— 身份一旦过期或串号就出错。
    这里在服务端做一次「token → openid」兑换，客户端不持有、不缓存 openid，
    存量接口一行都不用改。
    """
    u = db.resolve_token(x_user_token)
    if not u:
        raise HTTPException(401, 'token 无效或已过期')
    return {
        'openid': u['openid'],
        'user_id': u['user_id'],
        'quota': db.get_quota(u['openid']),
    }


class PurgeReq(BaseModel):
    confirm: str = Field('', description='二次确认串，必须等于用户ID，防误触')


@app.post('/api/auth/purge')
async def api_auth_purge(req: PurgeReq, x_user_token: str = Header(default='')):
    """账号注销：删除当前 token 对应用户的全部个人数据。

    ⚠️ 不可逆操作，因此设两道闸：
      1) 必须携带有效 token —— 不传 token 拿不到 user_id，陌生人无法注销他人账号
      2) confirm 必须回传 user_id —— 前端要在确认弹窗里明确告知「不可恢复」后回传，
         防止手滑或被诱导点击

    对应《小程序隐私保护指引》§四「删除权」。上线前需先在灰度环境验证。
    """
    u = db.resolve_token(x_user_token)
    if not u:
        raise HTTPException(401, 'token 无效或已过期')
    if (req.confirm or '').strip() != u['user_id']:
        raise HTTPException(400, 'confirm 与当前用户不匹配，请确认后再试')
    r = db.purge_user(u['user_id'])
    if not r.get('ok'):
        raise HTTPException(404, r.get('reason') or '注销失败')
    return {'ok': True, 'deleted': r['deleted'],
            'note': '全部个人数据已删除，不可恢复'}


@app.get('/api/auth/purge/preview')
async def api_auth_purge_preview(x_user_token: str = Header(default='')):
    """注销前预览：将影响哪些数据、当前有多少条。

    给用户看清楚「删什么」再决定，也是审核看「删除权是否真实可用」的落点。
    """
    u = db.resolve_token(x_user_token)
    if not u:
        raise HTTPException(401, 'token 无效或已过期')
    oid, uid = u['openid'], u['user_id']
    return {
        'user_id': uid,
        'counts': {
            'library_items': db.count_by_openid('library_items', oid),
            'quota_daily': db.count_by_openid('quota_daily', oid),
            'banned_daily': db.count_by_openid('banned_daily', oid),
            'points_sign': db.count_by_openid('points_sign', oid),
            'identities': db.count_by_user_id('identities', uid),
            'auth_tokens': db.count_by_user_id('auth_tokens', uid),
        },
        'not_deleted': ['卡密库', '违禁词库', '运营设置'],
        'irreversible': True,
    }


# ── 小程序侧注销（openid 路径）───────────────────────────────────────────────
# 为什么小程序走 openid 而 App/PC 走 token：
#   小程序从 wx.login 拿到 openid 后全程持有，且现有全部存量接口
#   （素材库/配额/会员/违禁词）本来就是 openid 主键 —— 注销沿用同一套身份口径，
#   不引入第二套凭证机制，避免两端口径不一致。
# 风险控制：注销是不可逆操作，用 confirm 回传 openid 做二次确认闸，
#   与 token 版对齐；实际风险等级与既有 /api/library/delete 相同。

class MiniPurgeReq(BaseModel):
    openid: str = Field('', description='当前用户 openid')
    confirm: str = Field('', description='二次确认串，必须等于 openid，防误触')


def _purge_counts(oid: str, uid: str) -> Dict[str, int]:
    return {
        'library_items': db.count_by_openid('library_items', oid),
        'quota_daily': db.count_by_openid('quota_daily', oid),
        'banned_daily': db.count_by_openid('banned_daily', oid),
        'points_sign': db.count_by_openid('points_sign', oid),
        'identities': db.count_by_user_id('identities', uid),
        'auth_tokens': db.count_by_user_id('auth_tokens', uid),
    }


@app.get('/api/auth/purge/preview_by_openid')
async def api_purge_preview_by_openid(openid: str = ''):
    """小程序侧注销预览（openid 路径）。"""
    if not openid:
        raise HTTPException(400, '缺少 openid')
    uid = db.user_id_by_openid(openid)
    if not uid:
        return {'counts': {}, 'irreversible': True, 'unknown_user': True,
                'not_deleted': ['卡密库', '违禁词库', '运营设置']}
    return {
        'openid': openid,
        'user_id': uid,
        'counts': _purge_counts(openid, uid),
        'not_deleted': ['卡密库', '违禁词库', '运营设置'],
        'irreversible': True,
    }


@app.post('/api/auth/purge_by_openid')
async def api_purge_by_openid(req: MiniPurgeReq):
    """小程序侧注销账号（不可逆）。"""
    if not req.openid:
        raise HTTPException(400, '缺少 openid')
    if (req.confirm or '').strip() != req.openid:
        raise HTTPException(400, 'confirm 与 openid 不匹配，请确认后再试')
    uid = db.user_id_by_openid(req.openid)
    if not uid:
        raise HTTPException(404, '账号不存在')
    r = db.purge_user(uid)
    if not r.get('ok'):
        raise HTTPException(404, r.get('reason') or '注销失败')
    return {'ok': True, 'deleted': r['deleted'],
            'note': '全部个人数据已删除，不可恢复'}


@app.get('/api/user/quota')
async def api_user_quota(openid: str = ''):
    if not openid:
        raise HTTPException(400, '缺少 openid')
    return db.get_quota(openid)


class ConsumeReq(BaseModel):
    openid: str = Field(..., description='用户标识')
    n: int = Field(1, ge=1, le=5, description='本次消耗次数')


@app.post('/api/user/quota/consume')
async def api_user_quota_consume(req: ConsumeReq):
    """保存成功后由客户端调用扣减。

    ⚠️ 防刷现状：游客态 openid 可伪造 → MVP 接受（配额价值低），
    支付接入后切正式 openid + 签名校验，此注释届时删除。
    """
    before = db.get_quota(req.openid)
    if not before.get('is_member') and before.get('save_left', 0) <= 0:
        return {'ok': False, 'reason': 'quota_exhausted', 'quota': before}
    q = db.consume_save(req.openid, req.n)
    return {'ok': True, 'quota': q}


# ---------- 会员卡密（购买闭环：线下收款 → 发码 → 小程序兑换，2026-10-08） ----------

class CodeRedeemReq(BaseModel):
    openid: str = Field(..., description='用户标识')
    code: str = Field(..., description='卡密，形如 CBXXXX-XXXX-XXXX')


class CodeGenReq(BaseModel):
    days: int = Field(30, ge=1, le=3650, description='面值天数（月卡 30）')
    count: int = Field(10, ge=1, le=200, description='生成数量')
    batch: str = Field('', description='批次备注')


@app.post('/api/member/redeem')
async def api_member_redeem(req: CodeRedeemReq):
    """卡密兑换会员。

    防刷：兑换尝试按 openid 限流（错码暴力枚举不可行——码空间 32^12）；
    游客态 openid 伪造风险与配额闸门同源，正式 openid 后统一收紧。
    """
    ok, info = await limiter.allow(f'redeem:{req.openid}')
    if not ok:
        raise HTTPException(429, '尝试过于频繁，请稍后再试')
    r = db.code_redeem(req.openid, req.code)
    return {**r, 'quota': db.get_quota(req.openid)} if r.get('ok') else r


class BannedCheckReq(BaseModel):
    openid: str = Field(..., description='用户标识')
    text: str = Field(..., max_length=5000, description='待检测文案')


@app.post('/api/banned/check')
async def api_banned_check(req: BannedCheckReq):
    """违禁词检测（2026-10-09）：免费 3 次/日只查基础类目，会员不限次+全类目。

    付费点=词库范围与完整报告；检测口径为「风险提示非法律意见」，
    客户端必须透传免责说明。
    """
    ok, info = await limiter.allow(f'banned:{req.openid}')
    if not ok:
        raise HTTPException(429, f'请求过于频繁，请 {info["retry_after"]}s 后重试')
    quota = db.banned_consume(req.openid)
    if not quota.get('ok'):
        return {'ok': False, 'reason': 'quota_exhausted', 'quota': quota,
                'message': f'今日免费额度已用完（{quota["limit"]} 次/日），'
                           '开通会员不限次+全类目检测'}
    from app import banned as banned_mod
    try:
        import banned as banned_mod_local   # 直跑兜底
    except ImportError:
        banned_mod_local = banned_mod
    r = banned_mod.detect(req.text, full=quota.get('is_member', False))
    return {'ok': True, 'quota': quota, 'is_member': quota.get('is_member'),
            'total': r['total'], 'risk_level': r['risk_level'],
            'marks': r['marks'], 'groups': r['groups'],
            'locked': r['locked'],
            'segments': banned_mod.build_segments(req.text, r['marks'])}


@app.get('/api/admin/codes', dependencies=[Depends(check_auth)])
async def admin_codes_list(status: str = '', limit: int = 100):
    return {'ok': True, **db.codes_list(status=status, limit=limit)}


@app.post('/api/admin/codes', dependencies=[Depends(check_auth)])
async def admin_codes_generate(req: CodeGenReq):
    codes = db.codes_generate(req.days, req.count, req.batch)
    return {'ok': True, 'days': req.days, 'count': len(codes), 'codes': codes}


class WordOnlyReq(BaseModel):
    """只带一个词的请求体。字段必须【有默认值】，否则无 body 的 query 调用会 422。"""
    word: str = Field('', description='词（留空则从 query 读）')


class CodeDisableReq(BaseModel):
    code: str = Field('', description='要作废的卡密（留空则从 query 读）')


@app.post('/api/admin/codes/disable', dependencies=[Depends(check_auth)])
async def admin_codes_disable(req: CodeDisableReq = Body(default=None),
                              request: Request = None):
    """作废单个未用卡密（输错价格/送错人时用）。

    ⚠️ 这里踩过一个坑，值得记下来：
       Pydantic 模型即使所有字段都有默认值，FastAPI 仍会把 requestBody 标为
       `required: true`（OpenAPI 实测），于是「不带 body 的 query 调用」直接 405。
       所以兼容层必须写成 `= Body(default=None)` —— **是默认值本身让它可选**，
       只给字段默认值是没用的。判别方法：看 /openapi.json 里 requestBody.required。

       最终支持两种传法：body {"code": "..."} 与 query ?code=...
    """
    c = ''
    if req is not None:
        c = (req.code or '').strip()
    if not c and request is not None:
        c = (request.query_params.get('code') or '').strip()
    if not c:
        raise HTTPException(400, '缺少 code（body.code 或 ?code= 二选一）')
    n = db.codes_disable(c)
    return {'ok': True, 'disabled': n, 'code': c}


# ---------- 违禁词库热管理（2026-10-11，看板自助扩词/停词）----------

class BannedWordReq(BaseModel):
    word: str = Field(..., description='词（1~20 字）')
    # ⚠️ 类目 key 取自 banned.CATEGORIES 的真实键名。
    # 原注释写的 finance/offsite/exaggerate 是错的（实际是 money/import/fake），
    # 照着旧注释填会被 API 拒 400。类目元数据请 GET /api/admin/banned/words 取。
    category: str = Field(..., description='类目 key：adlaw / induce / medical / money / import / fake')
    suggest: str = Field('', description='替换建议（可选）')


class BannedWordToggleReq(BaseModel):
    word: str = Field(...)
    enabled: bool = Field(...)


def _banned_mod():
    from app import banned as banned_mod
    try:
        import banned as banned_mod_local   # 直跑兜底
    except ImportError:
        banned_mod_local = banned_mod
    return banned_mod


@app.get('/api/admin/banned/words', dependencies=[Depends(check_auth)])
async def admin_banned_words():
    """看板词库卡：内置+自定义合并视图 + 类目元数据。"""
    bm = _banned_mod()
    return {'ok': True, 'categories': bm.CATEGORIES,
            'words': bm.words_merged(db.banned_custom_snapshot())}


@app.post('/api/admin/banned/words', dependencies=[Depends(check_auth)])
async def admin_banned_words_add(req: BannedWordReq):
    """新增/更新自定义词：落覆盖表 → 热刷新（同进程立即生效）。"""
    bm = _banned_mod()
    word = req.word.strip()
    if not (1 <= len(word) <= 20):
        raise HTTPException(400, '词长度需在 1~20 字之间')
    if req.category not in bm.CATEGORIES:
        raise HTTPException(400, f'未知类目: {req.category}')
    db.banned_word_upsert(word, req.category, req.suggest.strip(), 1)
    bm.refresh_overrides(db.banned_custom_snapshot())
    return {'ok': True, 'word': word, 'hot': True}


@app.post('/api/admin/banned/words/toggle', dependencies=[Depends(check_auth)])
async def admin_banned_words_toggle(req: BannedWordToggleReq):
    """停用/启用一个词（内置词停用=覆盖行 enabled=0；自定义词同表）。"""
    bm = _banned_mod()
    word = req.word.strip()
    if req.enabled:
        # 启用：有覆盖行则翻开 enabled；内置词本就默认启用（幂等 noop）
        snap = db.banned_custom_snapshot()
        if word in snap:
            row = snap[word]
            db.banned_word_upsert(word, row['category'], row['suggest'], 1)
        elif bm.builtin_category(word):
            return {'ok': True, 'word': word, 'enabled': True, 'noop': True}
        else:
            raise HTTPException(400, '未知词')
    else:
        cat = bm.builtin_category(word)
        if not cat:
            snap = db.banned_custom_snapshot()
            if word in snap:
                cat = snap[word]['category']
            else:
                raise HTTPException(400, '未知词')
        db.banned_word_upsert(word, cat, '', 0)
    bm.refresh_overrides(db.banned_custom_snapshot())
    return {'ok': True, 'word': word, 'enabled': req.enabled, 'hot': True}


@app.post('/api/admin/banned/words/delete', dependencies=[Depends(check_auth)])
async def admin_banned_words_delete(word: str = '',
                                    req: WordOnlyReq = Body(default=None),
                                    request: Request = None):
    """删除覆盖行：自定义词彻底移除，内置词恢复默认。

    word 支持 query（历史用法）与 body 两种传法。
    ⚠️ `= Body(default=None)` 不是装饰，是让 body 真正可选的关键 ——
       见 admin_codes_disable 的注释（OpenAPI 实测 required=true 的坑）。
    """
    w = (word or '').strip() or ((req.word or '').strip() if req else '')
    if not w and request is not None:
        w = (request.query_params.get('word') or '').strip()
    if not w:
        raise HTTPException(400, '缺少 word（body.word 或 ?word= 二选一）')
    n = db.banned_word_delete(w)
    _banned_mod().refresh_overrides(db.banned_custom_snapshot())
    return {'ok': True, 'deleted': n, 'word': w, 'hot': True}


@app.get('/api/admin/users', dependencies=[Depends(check_auth)])
async def admin_users_list(keyword: str = '', member_only: int = 0,
                           limit: int = 50):
    """看板用户名单：统计 + 最近活跃列表（keyword 搜 openid/昵称）。"""
    return {'ok': True,
            **db.users_list(keyword=keyword,
                            member_only=bool(member_only),
                            limit=limit)}


class LibItemReq(BaseModel):
    openid: str
    item_type: str = Field('video', description='video/image/copy')
    title: str = ''
    platform: str = ''
    author: str = ''
    cover: str = ''
    source_text: str = ''


@app.post('/api/library/add')
async def api_library_add(req: LibItemReq):
    item_id = db.library_add(req.openid, req.model_dump())
    return {'ok': True, 'id': item_id}


@app.get('/api/library/list')
async def api_library_list(openid: str, limit: int = 100):
    if not openid:
        raise HTTPException(400, '缺少 openid')
    return {'items': db.library_list(openid, min(limit, 200))}


@app.post('/api/library/delete')
async def api_library_delete(req: LibItemReq):
    # 复用字段：source_text 传要删的 item id
    try:
        item_id = int(req.source_text or '0')
    except ValueError:
        raise HTTPException(400, 'item id 非法')
    ok = db.library_delete(req.openid, item_id)
    return {'ok': ok}


class BatchReqV2(BaseModel):
    openid: str = Field('', description='用户标识（游客 guest_xxx 亦可）')
    items: list[BatchItem]


@app.post('/api/batch', dependencies=[Depends(check_admin_or_open)])
async def api_batch(req: BatchReqV2, request: Request):
    """批量解析（P0 增强，2026-10-07）

    ⭐ 配额以服务端为准（db.get_quota），客户端传值只作展示：
      · 免费：单次 3 条
      · 会员：单次 10 条（BATCH_MAX_HARD 硬上限，超直接 400）
      · 未登录：按游客 3 条 —— openid 为空时按 IP 限流已有兜底
    ⭐ 串行解析（2C2G）：一条失败不阻塞后续（工具箱验证的体验）
    ⭐ 每条走与单条相同的 normalize_meta + 缓存 —— 前端读同一份契约
    """
    ident = request.client.host if request.client else 'global'
    ok_rate, info = await limiter.allow(ident)
    if not ok_rate:
        raise HTTPException(429, f'请求过于频繁，请 {info["retry_after"]}s 后重试')

    # ---- 配额闸门（服务端权威） ----
    if req.openid:
        q = db.get_quota(req.openid)
        limit = q.get('batch_limit', config.BATCH_LIMIT_FREE)
    else:
        limit = config.BATCH_LIMIT_FREE
    if len(req.items) > config.BATCH_MAX_HARD:
        raise HTTPException(400, f'单次最多 {config.BATCH_MAX_HARD} 条')
    if len(req.items) > limit:
        raise HTTPException(403, f'当前身份单次最多 {limit} 条，'
                                 f'会员可至 {config.BATCH_LIMIT_MEMBER} 条')

    out = []
    for idx, item in enumerate(req.items):
        m = URL_RE.search(item.text or '')
        if not m:
            out.append({'index': idx, 'success': False, 'error': '未识别到链接'})
            continue
        short = m.group(0)

        # 与单条一致的缓存 key（同一视频两条入口只解析一次）
        key = hashlib.sha256(f'{short}|{item.quality}'.encode()).hexdigest()[:32]
        if not item.no_cache:
            cached = await cache.get(key)
            if cached:
                cached['cached'] = True
                cached['index'] = idx
                out.append(cached)
                continue

        # ⭐ 方案 A：批量与单条共用解析核心（含单链接并发锁）
        # 批量内部同 key 重复条目也会被合并（同一视频出现两次只解析一次）
        r, _leader = await single_flight.run(
            key, lambda: _parse_one(item.text, item.quality, short, key))
        r['short_url'] = short
        r['index'] = idx
        r['cached'] = False

        # 失败短条目瘦身：不透传冗余字段
        if not r.get('success'):
            r = {'index': idx, 'success': False, 'error': r.get('error', '解析失败'),
                 'platform': r.get('platform', '')}
        out.append(r)

    ok = sum(1 for r in out if r.get('success'))
    return {'total': len(out), 'ok': ok, 'fail': len(out) - ok, 'results': out}


# ---------- 广告位配置（后台可开关，DB 持久化） ----------

# ⭐ 默认值：master=false = 全站无广告（合规最稳态）。
#    后台开启后，banner 位当前渲染「自营推广」（会员卡），流量主开通后
#    可切微信官方 <ad> 组件；弹窗有频次上限（every_n_parses）防骚扰。
ADS_DEFAULT = {
    'master': False,
    'placements': {
        'hero_banner': True,        # 首页顶部轮播（自宣传，2026-10-08 新增）
        'index_banner': True,
        'result_banner': True,
        'toolbox_banner': True,
        'ranking_banner': True,     # 2026-10-08 用户要求：热榜/素材库默认开
        'library_banner': True,
        'member_banner': False,
    },
    'popup': {
        'enabled': True,
        'every_n_parses': 3,   # 每 N 次解析成功弹一次
        'start_after': 2,      # 前 N 次不弹（新客先体验）
    },
}

# 各广告位的人类可读名（后台看板显示 + 用户可自定义覆盖）
PLACEMENT_LABELS = {
    'hero_banner': '首页顶部轮播',
    'index_banner': '首页横幅',
    'result_banner': '结果页横幅',
    'toolbox_banner': '工具箱横幅',
    'ranking_banner': '热榜横幅',
    'library_banner': '素材库横幅',
    'member_banner': '会员中心横幅',
}
POPUP_LABEL = '弹窗广告'


_ADS_IMAGES_MAX = 5                     # 每位自定义图上限（轮播 2~5 张）


def _placement_obj(v, label: str) -> dict:
    """placement 归一化 v3（2026-10-08）：模式二选一 + 多图轮播

    mode='code'  → 只渲染微信流量主 <ad unit_id>（选了广告平台就只显示平台的）
    mode='image' → 只渲染自定义图片（1 张静图 / 2~5 张自动轮播）
    两种配置都保留存储，切换模式不丢数据。
    旧结构迁移：image（单图）→ images[0]；unit_id 有值且无 mode → code。
    """
    if isinstance(v, dict):
        images = v.get('images')
        if not isinstance(images, list):
            images = []
        images = [str(u) for u in images if str(u).strip()][:_ADS_IMAGES_MAX]
        legacy = str(v.get('image') or '').strip()
        if legacy and legacy not in images:
            images = [legacy] + images
            images = images[:_ADS_IMAGES_MAX]
        unit_id = str(v.get('unit_id') or '').strip()
        mode = str(v.get('mode') or '').strip().lower()
        if mode not in ('code', 'image'):
            mode = 'code' if unit_id else 'image'
        return {
            'enabled': bool(v.get('enabled', False)),
            'label': str(v.get('label') or label),
            'mode': mode,
            'unit_id': unit_id,
            'images': images,
            'image': images[0] if images else '',   # 旧字段兼容（读侧）
            'link': str(v.get('link') or ''),
        }
    return {'enabled': bool(v), 'label': label, 'mode': 'image',
            'unit_id': '', 'images': [], 'image': '', 'link': ''}


def _ads_config_merged() -> dict:
    saved = db.settings_get('ads_config') or {}
    cfg = {**ADS_DEFAULT, **saved}
    merged = {}
    for k, label in PLACEMENT_LABELS.items():
        merged[k] = _placement_obj(
            (saved.get('placements') or {}).get(k,
                                                ADS_DEFAULT['placements'][k]),
            label)
    p = saved.get('popup') or {}
    cfg['popup'] = {
        **ADS_DEFAULT['popup'], **p,
        'image': str(p.get('image') or ''),
        'unit_id': str(p.get('unit_id') or ''),
        'link': str(p.get('link') or ''),
        'label': POPUP_LABEL,
    }
    cfg['placements'] = merged
    return cfg


# 广告素材上传目录（/media/ads 静态服务）
ADS_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             '..', 'media', 'ads')
_ADS_IMG_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
_ADS_IMG_MAX = 2 * 1024 * 1024          # 2MB（2C2G 本地服务足够 banner 用）

# 广告素材静态服务：mount 必须挂 media 的「父目录」——
# 前缀 /media 剥掉后剩余路径是 /ads/xxx.png，若直接挂 media/ads
# 会变成 .../media/ads/ads/xxx.png 双重路径（实测 404 的根因）
ADS_MEDIA_ROOT = os.path.dirname(ADS_MEDIA_DIR)          # server/media
os.makedirs(ADS_MEDIA_DIR, exist_ok=True)
app.mount('/media', StaticFiles(directory=ADS_MEDIA_ROOT), name='media')


@app.post('/api/ads/upload', dependencies=[Depends(check_admin_or_open)])
async def api_ads_upload(file: UploadFile = File(...)):
    """上传广告图片（后台看板用，需 API Key）。

    存 server/media/ads/{uuid}{ext}，经 /media/ads/... 静态下发。
    客户端 <image> 直接用返回的 url（本机服务 = 同源）。
    """
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in _ADS_IMG_EXT:
        raise HTTPException(400, f'仅支持图片格式: {", ".join(sorted(_ADS_IMG_EXT))}')
    data = await file.read()
    if len(data) > _ADS_IMG_MAX:
        raise HTTPException(400, '图片不能超过 2MB')
    if not data:
        raise HTTPException(400, '文件为空')
    os.makedirs(ADS_MEDIA_DIR, exist_ok=True)
    name = uuid.uuid4().hex[:12] + ext
    with open(os.path.join(ADS_MEDIA_DIR, name), 'wb') as f:
        f.write(data)
    return {'ok': True, 'url': f'/media/ads/{name}'}


# ────────────────── PDF 极轻三件（P2 · 合并/提取/水印）──────────────────

@app.post('/api/pdf/merge')
async def api_pdf_merge(files: List[UploadFile] = File(...)):
    """PDF 合并（2-5 个文件按顺序拼接）。"""
    try:
        payload = [(f.filename or f'{i}.pdf', await f.read())
                   for i, f in enumerate(files)]
        url = pdftools.merge(payload)
        return {'ok': True, 'url': url}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f'合并失败: {str(e)[:60]}')


# ────────────────── 积分中心（P2 · 签到 → 兑换会员天数）──────────────────

POINTS_PER_SIGN = 10              # 每日签到
POINTS_STREAK_BONUS = 20          # 连续 7 天额外奖励
POINTS_REDEEM_COST = 100          # 兑换 1 天会员
_DATE_FMT = '%Y-%m-%d'


def _today() -> str:
    return time.strftime(_DATE_FMT)


def _yesterday() -> str:
    return time.strftime(_DATE_FMT, time.localtime(time.time() - 86400))


@app.get('/api/points')
async def api_points(openid: str = ''):
    """积分余额 + 近 7 天签到 + 连签天数。"""
    openid = (openid or '').strip()
    if not openid:
        raise HTTPException(400, '缺少 openid')
    return {'ok': True, **db.points_summary(openid),
            'redeem_cost': POINTS_REDEEM_COST}


@app.post('/api/points/sign')
async def api_points_sign(body: PointsReq):
    """每日签到：+10，连续 7 天额外 +20。幂等（同一天重复签返回已签状态）。"""
    openid = (body.openid or '').strip()
    if not openid:
        raise HTTPException(400, '缺少 openid')

    summary = db.points_summary(openid)
    # 连签判定：昨天签过 → streak+1，否则重置 1
    streak = summary['streak'] + 1 if _yesterday() in summary['days'] else 1
    gained = POINTS_PER_SIGN + (POINTS_STREAK_BONUS if streak % 7 == 0 else 0)

    if not db.points_sign_record(openid, _today(), gained, streak):
        fresh = db.points_summary(openid)
        return {'ok': True, 'signed': False, **fresh,
                'message': '今天已签到过啦'}

    fresh = db.points_summary(openid)
    return {'ok': True, 'signed': True, 'gained': gained, **fresh}


@app.post('/api/points/redeem')
async def api_points_redeem(body: PointsReq):
    """积分兑换会员天数：100 积分 = 1 天（余额足额才成交）。"""
    openid = (body.openid or '').strip()
    if not openid:
        raise HTTPException(400, '缺少 openid')
    summary = db.points_summary(openid)
    if summary['balance'] < POINTS_REDEEM_COST:
        raise HTTPException(
            400, f'积分不足：余额 {summary["balance"]}，兑换需要 {POINTS_REDEEM_COST}')

    # 兑换天数 = 余额整除单价（一次换完，避免零头滞留）
    days = summary['balance'] // POINTS_REDEEM_COST
    member = db.member_add_days(openid, days)
    db.points_redeem_record(openid, days * POINTS_REDEEM_COST, days)
    fresh = db.points_summary(openid)
    # ⚠️ redeemed_days 独立命名：fresh 里有同名 days（近7天列表）会覆盖整型天数
    return {'ok': True, 'redeemed_days': days, 'member': member, **fresh}


@app.post('/api/pdf/extract')
async def api_pdf_extract(file: UploadFile = File(...), page: int = 1):
    """提取指定页为单独 PDF（1-based）。"""
    try:
        data = await file.read()
        url = pdftools.split(data, file.filename or 'doc.pdf', 'range', page)
        return {'ok': True, 'url': url}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f'提取失败: {str(e)[:60]}')


@app.post('/api/pdf/watermark')
async def api_pdf_watermark(file: UploadFile = File(...), text: str = ''):
    """整份 PDF 平铺文字水印。"""
    try:
        data = await file.read()
        url = pdftools.watermark(data, file.filename or 'doc.pdf', text)
        return {'ok': True, 'url': url}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f'水印失败: {str(e)[:60]}')


@app.get('/api/ads/config')
async def api_ads_config():
    """广告位配置（公开只读，客户端启动时拉取并缓存）"""
    return {'ok': True, 'ads': _ads_config_merged()}


@app.post('/api/ads/config', dependencies=[Depends(check_admin_or_open)])
async def api_ads_config_update(request: Request):
    """更新广告配置（后台看板/运维用，需 API Key）。

    接受部分更新：{master} / {placements:{...}} / {popup:{...}} 任意组合。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, 'body 必须是 JSON')
    if not isinstance(body, dict):
        raise HTTPException(400, 'body 必须是 JSON 对象')

    cfg = _ads_config_merged()
    if isinstance(body.get('master'), bool):
        cfg['master'] = body['master']
    if isinstance(body.get('placements'), dict):
        for k, v in body['placements'].items():
            if k not in cfg['placements']:
                continue
            if isinstance(v, bool):              # 兼容旧客户端的纯开关
                cfg['placements'][k]['enabled'] = v
            elif isinstance(v, dict):            # 新结构：enabled/label/image/unit_id/link
                dst = cfg['placements'][k]
                if isinstance(v.get('enabled'), bool):
                    dst['enabled'] = v['enabled']
                if isinstance(v.get('label'), str):
                    dst['label'] = v['label'][:20] or dst['label']
                # 模式二选一（2026-10-08）：code=广告平台 <ad> / image=自定义多图
                if isinstance(v.get('mode'), str) \
                        and v['mode'] in ('code', 'image'):
                    dst['mode'] = v['mode']
                for fld in ('unit_id', 'link'):
                    if isinstance(v.get(fld), str):
                        dst[fld] = v[fld][:60] if fld == 'unit_id' else v[fld][:300]
                if isinstance(v.get('image'), str):
                    # 旧单图字段：作为 images 的首帧合并（不清已有列表）
                    img = v['image'].strip()[:300]
                    if img and img not in dst['images']:
                        dst['images'] = ([img] + dst['images'])[:_ADS_IMAGES_MAX]
                if isinstance(v.get('images'), list):
                    urls = [str(u).strip()[:300] for u in v['images']
                            if str(u).strip()]
                    # 去重保序 + 钳制数量（轮播 2~5 张体验最好，1 张也合法）
                    seen, dedup = set(), []
                    for u in urls:
                        if u not in seen:
                            seen.add(u)
                            dedup.append(u)
                    dst['images'] = dedup[:_ADS_IMAGES_MAX]
                # 单图便捷字段与 images[0] 保持同步（旧读侧兼容）
                dst['image'] = dst['images'][0] if dst['images'] else ''
    if isinstance(body.get('popup'), dict):
        p = body['popup']
        if isinstance(p.get('enabled'), bool):
            cfg['popup']['enabled'] = p['enabled']
        # 越界值钳制到合法区间（不是忽略 —— 忽略会让用户困惑为何没生效）
        if isinstance(p.get('every_n_parses'), int):
            cfg['popup']['every_n_parses'] = min(50, max(1, p['every_n_parses']))
        if isinstance(p.get('start_after'), int):
            cfg['popup']['start_after'] = min(50, max(0, p['start_after']))
        for fld in ('image', 'unit_id', 'link'):
            if isinstance(p.get(fld), str):
                cfg['popup'][fld] = p[fld][:300] if fld != 'unit_id' else p[fld][:60]

    db.settings_set('ads_config', cfg)
    return {'ok': True, 'ads': cfg}


# ---------- 封面防盗链代理（2026-10-11，uvd proxy-thumbnail 思路） ----------
# 抖音/快手等封面 CDN 带防盗链与签名，小程序 <image> 直连偶发裂图。
# 服务端中转一次 + 磁盘缓存 → 二次请求零出网。
# SSRF 三闸：仅 https ｜ 必须命中 domains 注册表的已知平台 CDN 域 ｜ 5MB 上限。

_COVER_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'media', 'covers')
os.makedirs(_COVER_CACHE_DIR, exist_ok=True)
_COVER_MAX_BYTES = 5 * 1024 * 1024
_COVER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
             'AppleWebKit/537.36 (KHTML, like Gecko) '
             'Chrome/126.0.0.0 Safari/537.36')
_COVER_REFERER = {
    'bilibili': 'https://www.bilibili.com/',
    'douyin': 'https://www.douyin.com/',
    'kuaishou': 'https://www.kuaishou.com/',
    'xiaohongshu': 'https://www.xiaohongshu.com/',
    'weibo': 'https://weibo.com/',
    'haokan': 'https://haokan.baidu.com/',
    # 百度信息流视频（mbd.baidu.com分享页）的图片走 *.baidu.com，
    # 实测 2026-10-22：不给Referer 直接 403。
    #⚠️ 缺这一条时它会 fallback 到默认值（douyin）→ 403 → 结果页封面全黑，
    #   而接口本身返回 200 正常，排查方向容易被带偏（会以为是渲染问题）。
    'baidu': 'https://mbd.baidu.com/',
    'acfun': 'https://www.acfun.cn/',
    'sohu': 'https://tv.sohu.com/',
}

# ⭐ 图片 CDN 后缀 → 平台（2026-10-24 新增，修 B站封面 404）
#
# 为什么不能复用 domains.registry.match()：那张表登记的是【视频 CDN】，
# 图片 CDN 是另一套域名，两者根本没有交集。实测：
#   registry.match('https://i1.hdslb.com/x.jpg')          → None
#   registry.match('https://p26-sign.douyinpic.com/x.jpg') → None
#   registry.match('https://cn-jsnt-ct-01-01.bilivideo.com/v.mp4') → bilibili ✅
# plat 恒为 None → Referer 回落到默认的 douyin：
#   · B站封面对 Referer 校验严 → 403 → 代理 404 → **结果页封面全黑**
#   · 抖音封面恰好默认值就是抖音 → 蒙对，所以这个 bug 一直没被发现
#
# 正确做法：直接按图片域后缀反查平台（与 _COVER_HOST_SUFFIXES 同源）。
# 长后缀优先匹配（'v.video.weibocdn.com' 之类），故按长度倒序查。
_COVER_PLATFORM_BY_SUFFIX = {
    'hdslb.com': 'bilibili',
    'bilivideo.com': 'bilibili',
    'douyinpic.com': 'douyin',
    'byteimg.com': 'douyin',
    'zjcdn.com': 'douyin',
    'kwaicdn.com': 'kuaishou',
    'kwimgs.com': 'kuaishou',
    'yximgs.com': 'kuaishou',
    'xhscdn.com': 'xiaohongshu',
    'sinaimg.cn': 'weibo',
    'weibocdn.com': 'weibo',
    'bdstatic.com': 'haokan',
    'bcebos.com': 'haokan',
    'baidu.com': 'baidu',
    'acfun.cn': 'acfun',
    'itc.cn': 'sohu',
    'sohu.com': 'sohu',
}
_COVER_SUFFIX_KEYS = tuple(sorted(_COVER_PLATFORM_BY_SUFFIX,
                                  key=len, reverse=True))

# ── 封面压缩（2026-10-24）────────────────────────────────────────
# 目标：结果页封面容器宽约 347px 逻辑宽（400rpx 高 × 16:9），
#       2x 屏需要 ~694 物理像素 → 取 640px 宽，肉眼无差。
# 效果：B站原图 651KB → 约 30KB（实测），单次出网 253KB → 40KB 级别。
_COVER_TARGET_W = 640
_COVER_WEBP_Q = 80
# 缓存 key 加版本前缀：老缓存是「原图直转」的，不换版本会一直被命中，
# 压缩就永远不生效（这是最容易漏的一步）。
_COVER_CACHE_VER = 'v3'

# 图片 CDN 域名后缀白名单（SSRF 闸①）。
# ⚠️ 不能直接复用 domains.registry 的视频 CDN 模式——图片子域编号随机
#   （p26-sign.douyinpic.com 就匹配不上 p3/p9-pc-sign 模式，实测 403）。
#   后缀匹配天然覆盖「编号随机」的子域形态；发现新 CDN 域在此追加。
_COVER_HOST_SUFFIXES = (
    'douyinpic.com', 'byteimg.com', 'zjcdn.com',          # 抖音
    'bilivideo.com', 'hdslb.com',                          # B站
    'kwaicdn.com', 'kwimgs.com', 'yximgs.com',             # 快手
    'xhscdn.com',                                          # 小红书
    'sinaimg.cn', 'weibocdn.com',                          # 微博
    'bdstatic.com', 'bcebos.com',                          # 好看/百度系
    # 百度信息流视频（mbd.baidu.com 分享页）的图片在 *.baidu.com 下，
    # 实测 2026-10-22：封面域名形如 f7.baidu.com / f8.baidu.com（编号随机，
    # 与 bdstatic 不是同一套）。缺了它→ 代理返回 404 → 结果页封面全黑。
    # 后缀写 .baidu.com 能覆盖随机编号子域。
    'baidu.com',
    'acfun.cn',                                            # AcFun
    'itc.cn', 'sohu.com',                                  # 搜狐
    'fbcdn.net', 'cdninstagram.com',                       # Facebook/IG
    'twimg.com',                                           # X
    'tiktokcdn.com', 'tiktokcdn-us.com', 'tiktokv.com', 'tikwm.com',  # TikTok
)


def _cover_host_allowed(url: str) -> bool:
    """SSRF 闸：host 必须命中已知图片 CDN 后缀（或视频域名注册表）"""
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(url).hostname or '').lower()
    except Exception:
        return False
    if not host or host in ('localhost',):
        return False
    if any(host == s or host.endswith('.' + s) for s in _COVER_HOST_SUFFIXES):
        return True
    return domains.registry.match(url) is not None     # 注册表兜底


def _cover_platform(url: str) -> str:
    """封面 URL 属于哪个平台 —— 用来选 Referer。

    ⭐ 顺序很重要：先查【图片 CDN 后缀表】，再回落视频注册表。
      反过来（原来那样只查注册表）会让所有图片域都匹配不到，
      Referer 全部落到默认的 douyin —— B站因此 403/404。
    """
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(url).hostname or '').lower()
    except Exception:
        return ''
    for suf in _COVER_SUFFIX_KEYS:          # 长后缀优先，避免 v.x.com 被 x.com 抢
        if host == suf or host.endswith('.' + suf):
            return _COVER_PLATFORM_BY_SUFFIX[suf]
    return domains.registry.match(url) or ''


def _fetch_cover_sync(url: str, referer: str):
    """阻塞拉图（线程池跑）。返回 (data, content_type) 或 (None, err_msg)。

    ⭐ 两道保险（2026-10-24）：
      ① 带平台 Referer 先试；
      ② 若被 401/403 拒（Referer 校验没通过 / 平台判断错了），
         用【不带 Referer】重试一次 —— 实测很多图片 CDN 对空 Referer
         比错 Referer 宽容（B站 i1.hdslb.com：错 Referer 403，空 Referer 200）。
         不重试的后果是「封面全黑」，而错误信息只是 403，很难联想到是 Referer。
    """
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def _try(ref: str):
        headers = {
            'User-Agent': _COVER_UA,
            'Accept': 'image/avif,image/webp,image/*,*/*',
        }
        if ref:
            headers['Referer'] = ref
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            data = r.read(_COVER_MAX_BYTES + 1)
            ctype = (r.headers.get('Content-Type')
                     or 'image/jpeg').split(';')[0].strip()
        return data, ctype

    try:
        data, ctype = _try(referer)
    except urllib.error.HTTPError as e:
        # 只有 401/403 值得换 Referer 重试；404 是图真没了，重试没意义
        if e.code not in (401, 403):
            return None, f'HTTP {e.code}'
        try:
            data, ctype = _try('')
        except Exception as e2:
            return None, f'HTTP {e.code}（无 Referer 重试也失败: {str(e2)[:40]}）'
    except Exception as e:
        return None, str(e)[:80]

    if len(data) > _COVER_MAX_BYTES:
        return None, '封面超过 5MB'
    if not ctype.startswith('image/'):
        return None, f'非图片内容（{ctype}）'
    return data, ctype


def _compress_cover(data: bytes, ctype: str):
    """缩图 + 转 webp。返回 (data, ctype, saved_bytes)。

    ⭐ 三条铁律（都是为了「压缩失效也不能影响可用」）：
      ① Pillow 没装 / 解码失败 / 是动图 → 原样返回，绝不让压缩变成 404；
      ② 压完反而更大（小图、已优化过的图）→ 返回原图；
      ③ 只缩不放 —— 宽于 640 才缩，小图原样保留（放大只会更糊更大）。

    ⚠️ 为什么转 webp：同样 640px 宽，JPEG q80 约 60~80KB，webp q80 约 25~35KB。
       微信小程序 <image> 全平台支持 webp（iOS 一直支持，Android 需基础库 2.9+，
       2026 年线上基础库版本远高于此），所以优先 webp。
       万一要回退 JPEG：把 _COVER_WEBP_Q 置 None 即可（见下方分支）。
    """
    try:
        from PIL import Image
    except ImportError:
        return data, ctype, 0                    # 没装 Pillow：原图直转

    try:
        im = Image.open(io.BytesIO(data))
        # ⭐ JPEG 专用加速：draft() 让解码器直接按 1/2、1/4、1/8 降采样解码，
        #    不解出全尺寸再缩。B站 1920x1080 封面实测 397ms → 约 100ms。
        #    对非 JPEG 是无操作（PIL 自己判断），所以可以无脑调。
        try:
            im.draft('RGB', (_COVER_TARGET_W, _COVER_TARGET_W))
        except Exception:
            pass
        # 动图（GIF/webp 动画）转静态会丢帧 → 不动它
        if getattr(im, 'n_frames', 1) > 1:
            return data, ctype, 0
        # 调色板 / CMYK / LA 等模式 webp 写不了，统一转 RGBA（保透明）或 RGB
        if im.mode in ('P', 'CMYK', 'LA', 'PA'):
            im = im.convert('RGBA' if 'transparency' in im.info
                            or im.mode in ('LA', 'PA') else 'RGB')
        elif im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGB')

        w, h = im.size
        if w > _COVER_TARGET_W:
            nh = max(1, round(h * _COVER_TARGET_W / w))
            im = im.resize((_COVER_TARGET_W, nh), Image.LANCZOS)

        buf = io.BytesIO()
        if _COVER_WEBP_Q is None:                # 回退通道：JPEG
            if im.mode == 'RGBA':
                bg = Image.new('RGB', im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            im.save(buf, 'JPEG', quality=82, optimize=True)
            new_ctype = 'image/jpeg'
        else:
            im.save(buf, 'WEBP', quality=_COVER_WEBP_Q, method=4)
            new_ctype = 'image/webp'
        out = buf.getvalue()

        if len(out) >= len(data):                # 压完更大 → 用原图
            return data, ctype, 0
        return out, new_ctype, len(data) - len(out)
    except Exception:
        return data, ctype, 0                    # 任何解码异常都退回原图


def _purge_legacy_cover_cache() -> int:
    """清掉压缩策略升级前的老缓存（无 `v*_` 前缀的 xx.img / xx.img.type）。

    老缓存不删也不会被命中（key 已加版本前缀），但会白占磁盘。
    ⚠️ 只删【严格匹配老格式】的名字：24 位小写十六进制 + .img(.type)。
       不用通配符批量删 —— 缓存目录以后可能放别的东西，通配符是隐患。
    """
    import re
    pat = re.compile(r'^[0-9a-f]{24}\.img(?:\.type)?$')
    n = 0
    try:
        for name in os.listdir(_COVER_CACHE_DIR):
            if not pat.match(name):
                continue
            try:
                os.remove(os.path.join(_COVER_CACHE_DIR, name))
                n += 1
            except OSError:
                pass
    except OSError:
        return 0
    return n



@app.get('/api/proxy-cover')
async def api_proxy_cover(url: str = ''):
    url = (url or '').strip()
    if not url.startswith('https://'):
        raise HTTPException(400, '仅支持 https 封面地址')
    if not _cover_host_allowed(url):
        raise HTTPException(403, '非已知平台 CDN 域名')
    plat = _cover_platform(url)                      # 决定 Referer（图片域反查）

    key = hashlib.sha1(url.encode()).hexdigest()[:24]
    # 版本前缀：换压缩策略后老缓存必须失效，否则「改了代码但用户还收原图」
    cache_path = os.path.join(_COVER_CACHE_DIR, f'{_COVER_CACHE_VER}_{key}.img')
    type_path = cache_path + '.type'
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        try:
            ctype = open(type_path, encoding='utf-8').read().strip() or 'image/jpeg'
        except Exception:
            ctype = 'image/jpeg'
        return FileResponse(cache_path, media_type=ctype,
                            headers={'Cache-Control': 'public, max-age=86400'})

    referer = _COVER_REFERER.get(plat or '', 'https://www.douyin.com/')
    loop = asyncio.get_event_loop()
    data, ctype = await loop.run_in_executor(
        None, _fetch_cover_sync, url, referer)
    if data is None:
        raise HTTPException(404, f'封面获取失败({plat or "未知平台"}): {ctype}')

    # ⭐ 压缩（CPU 也放线程池，别阻塞事件循环）
    data, ctype, saved = await loop.run_in_executor(
        None, _compress_cover, data, ctype)

    tmp = cache_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, cache_path)          # 原子落盘，并发请求不读到半个文件
    with open(type_path, 'w', encoding='utf-8') as f:
        f.write(ctype)
    if saved:
        logger.info('封面压缩 %s → %s KB（省 %s KB）',
                    url[:60], len(data) // 1024, saved // 1024)
    return FileResponse(cache_path, media_type=ctype,
                        headers={'Cache-Control': 'public, max-age=86400'})



@app.get('/api/trending')
async def api_trending(platform: str = ''):
    """热门榜单（M1.5 屏 6）—— 官方公开热榜，缓存 10 分钟

    未接入平台返回 ok=false + code=not_implemented（客户端渲染「接入中」态），
    不造假数据。榜单条目 url 均可直接进 /api/parse（解析同款闭环）。
    """
    try:
        r = await trending.get_trending(platform)
        if not r.get('ok'):
            # unknown_platform / not_implemented 是业务语义，用 200 + code 下发
            return r
        return r
    except Exception as e:
        return {'ok': False, 'code': 'upstream_error',
                'message': f'热榜源暂时不可用: {str(e)[:80]}'}


@app.get('/api/knowledge/platforms')
async def api_kb_platforms():
    """平台注册表（唯一事实源，供后台看板与客户端判断）"""
    return knowledge.summary()


@app.get('/api/knowledge/fields/{name}')
async def api_kb_fields(name: str):
    """某平台的字段路径速查（写解析器时查这个）"""
    p = knowledge.get_field_pattern(name)
    if not p:
        raise HTTPException(404, f'未收录平台: {name}')
    return {'platform': name, 'pattern': p}


@app.get('/api/knowledge/pitfalls')
async def api_kb_pitfalls():
    """已踩过的坑（避免重犯）"""
    return {'pitfalls': knowledge.get_pitfalls()}


# ---------- M1 Gate：健康度 + 域名 ----------

@app.get('/api/health/platforms')
async def api_health_platforms():
    """⭐ 平台健康度看板（M1 Gate 条件）

    三层数据：
      probes  L1 定时探针（含能力断言，能发现「静默降级」）
      traffic L2 真实流量成败（p50/p95/成功率）
      alerts  告警列表（critical / warning）
    """
    r = health.monitor.summary()
    r['probe_interval_s'] = max(config.HEALTH_INTERVAL, 60)
    r['probe_enabled'] = config.ENABLE_HEALTH_PROBE
    return r


@app.post('/api/health/platforms/probe', dependencies=[Depends(check_admin_or_open)])
async def api_health_probe_now():
    """立即跑一轮探针（排障用，不等定时）"""
    return await health.monitor.run_once()


@app.get('/api/health/history')
async def api_health_history(platform: str = '', limit: int = 200):
    """健康历史明细（SQLite 持久化，重启不丢）

    用途：复盘「平台什么时候开始坏的」—— down 前的 degraded 趋势
    就是改版早期信号。默认保留 HEALTH_RETENTION_DAYS 天。
    """
    try:
        return {'ok': True, 'platform': platform, 'items':
                db.health_history_list(platform, limit)}
    except Exception as e:
        return {'ok': False, 'message': f'历史查询失败: {str(e)[:80]}'}


@app.get('/api/health/alerts')
async def api_health_alerts():
    """当前 open 告警（down 建档 / 恢复销案，持续 down 只递增不重复通知）"""
    try:
        return {'ok': True, 'alerts': db.health_alerts_open()}
    except Exception as e:
        return {'ok': False, 'message': f'告警查询失败: {str(e)[:80]}'}


@app.get('/api/domains')
async def api_domains():
    """域名自适应注册表 —— 驱动小程序白名单配置"""
    return {
        'snapshot': domains.registry.snapshot(),
        'wechat_whitelist': domains.registry.wechat_whitelist(),
        'note': ('white名单只收「域名有限可枚举」的平台；'
                 '子域随机的（如 B站）必须走服务端中转。'
                 'unlisted_hosts 非空 = 平台可能新增了 CDN，是改版早期信号'),
    }


@app.post('/api/domains/classify', dependencies=[Depends(check_admin_or_open)])
async def api_domains_classify(req: ParseReq):
    """判定某个 URL 能否走小程序直连（还是要中转）"""
    url = URL_RE.search(req.text or '')
    if not url:
        return {'error': '未识别到链接'}
    c = domains.registry.classify(url.group(0))
    kb = knowledge.PLATFORMS.get(c.get('platform') or '', {})
    c['name_cn'] = kb.get('name_cn')
    c['engine'] = kb.get('engine')
    return c


@app.get('/api/capabilities')
async def api_capabilities():
    """各平台已验证的约束（供客户端与后台判断）"""
    return {'capabilities': CAPABILITY, 'whitelist_hint': WHITELIST_HINT}


@app.get('/api/visibility')
async def api_visibility():
    """平台入口可见性裁决（v4 §3.3 提审收敛开关）。

    客户端**只按本接口下发结果渲染入口**，不要自己再判断隐藏逻辑 ——
    三端各写一套是这类开关失控的根因。收敛只隐藏入口，不关闭解析能力。
    """
    return visibility.payload()


class MergeReq(BaseModel):
    text: str = Field(..., description='m3u8 地址，或含 m3u8 的分享链接')
    referer: str = Field('', description='CDN 需要的 Referer')
    prefer: str = Field('auto', description='direct/segments/auto')
    keep: bool = Field(False, description='true=保留文件（供下载）'
                              'false=返回路径不删除（调试用）')


@app.post('/api/merge', dependencies=[Depends(check_admin_or_open)])
async def api_merge(req: MergeReq):
    """m3u8 → mp4 服务端合并

    ⭐ 合并前会做**重复分段检测**（knowledge.P22）：
       搜狐的 m3u8 是同一段试看内容重复 N 次，合并只会得到垃圾文件，
       而 ffmpeg 不会报错。这种情况直接拒绝并说明原因。
    """
    ident = req.text
    ok, info = await limiter.allow(f'merge:{ident[:40]}')
    if not ok:
        raise HTTPException(429, f'请求过于频繁，请 {info["retry_after"]}s 后重试')

    url = req.text.strip()
    if not url.startswith('http'):
        m = URL_RE.search(req.text or '')
        if not m:
            return {'success': False, 'error': '未识别到 m3u8 地址'}
        url = m.group(0)
    if '.m3u8' not in url:
        return {'success': False,
                'error': '不是 m3u8 地址（该平台可能提供的是直链 mp4，'
                         '无需合并）'}

    t0 = time.time()
    r = await m3u8_merge.merge_m3u8_to_mp4(
        url, None, req.referer, prefer=req.prefer)
    r['elapsed_total'] = round(time.time() - t0, 2)
    r['success'] = bool(r.get('ok'))
    return r


@app.get('/api/ffmpeg')
async def api_ffmpeg():
    """ffmpeg 可用性与能力（供部署自检）"""
    return {
        'capabilities': ffmpeg_util.capabilities(),
        'license_note': ('imageio-ffmpeg 自带二进制为 GPL 构建。'
                         '闭源商用建议仅以子进程方式调用，'
                         '或改用系统包安装的 ffmpeg；上线前请法务确认'),
        'note': ('合并时用 -c copy（纯 remux，不转码），'
                 '实测 155MB / 5 分钟视频 5.4 秒完成'),
    }


@app.get('/api/health')
async def api_health():
    h = await pool.health()
    record_health(h)
    return {
        'service': 'creatorbox-parser',
        'version': '2.1.0',
        'platforms': [p.name.replace('_pure', '') for p in pool.pure],
        **h,
        'cache_ttl': config.CACHE_TTL,
        'rate_limit_per_min': config.RATE_LIMIT_PER_MIN,
    }


@app.post('/api/cache/clear', dependencies=[Depends(check_admin_or_open)])
async def api_clear_cache():
    await cache.clear()
    return {'success': True}


# ---------- 登录态 Cookie 运维（看板自助闭环，2026-10-08） ----------
# 闭环：探针告警 → /admin 看板粘贴新 Cookie → 保存即热生效 → 即时验证
# 之前配 Cookie 要手工建文件 + 重启服务，小白流程断在两处，这里全收进看板。

_COOKIE_MANAGE = {
    # key: (config 属性, 落盘文件, 中文名, 用途说明)
    'xhs': ('XHS_COOKIE', 'xhs-cookie.txt', '小红书',
            '解析 + 热榜共用；失效时解析报登录墙、热榜报 need_cookie'),
    'weibo': ('WEIBO_COOKIE', 'weibo-cookie.txt', '微博',
              '仅热榜用；解析本来就不需要 Cookie'),
}


class CookieSaveReq(BaseModel):
    platform: str = Field(..., description="xhs / weibo")
    cookie: str = Field(..., description='浏览器 F12 复制的完整 Cookie 串')


@app.get('/api/admin/cookies', dependencies=[Depends(check_auth)])
async def admin_cookie_status():
    """看板 Cookie 卡片数据：配置状态 + 落盘文件 + 最近探针结论

    GET 公开（与 /api/ads/config 同口径，只含状态不含内容本身）；
    保存走 POST 且需 API Key。"""
    root = Path(__file__).resolve().parent.parent
    out = []
    for key, (attr, fname, label, usage) in _COOKIE_MANAGE.items():
        val = (getattr(config, attr, '') or '').strip()
        f = root / fname
        last = {'ok': None, 'error': '', 'ts': None}
        try:
            rows = db.health_history_list(platform=f'{key}_cookie', limit=1)
            if rows:
                last = {'ok': bool(rows[0].get('ok')),
                        'error': rows[0].get('error') or '',
                        'ts': rows[0].get('ts')}
        except Exception:
            pass                                    # 历史为空不影响状态展示
        out.append({
            'platform': key, 'label': label, 'file': fname, 'usage': usage,
            'configured': bool(val), 'length': len(val),
            'file_exists': f.exists(),
            'updated_at': int(f.stat().st_mtime) if f.exists() else None,
            'last_probe': last,
        })
    return {'ok': True, 'cookies': out}


@app.post('/api/admin/cookies', dependencies=[Depends(check_auth)])
async def admin_cookie_save(req: CookieSaveReq):
    key = (req.platform or '').strip().lower()
    if key not in _COOKIE_MANAGE:
        raise HTTPException(400, 'platform 只支持 xhs / weibo')
    cookie = (req.cookie or '').strip().strip('"')
    if len(cookie) < 40 or '=' not in cookie:
        raise HTTPException(
            400, '内容不像有效 Cookie（太短或没有键值对）——'
                 '请在目标网站按 F12 → Network → 任一请求 → 复制 Cookie 请求头')
    attr, fname, label, _usage = _COOKIE_MANAGE[key]

    # 1) 热更新当前进程（立即生效，不用重启）
    setattr(config, attr, cookie)
    # 2) 落盘（重启后的兜底，start-server.ps1 会读这个文件）
    f = Path(__file__).resolve().parent.parent / fname
    f.write_text(cookie + '\n', encoding='utf-8')
    # 3) 复位 Cookie 探针节流，让下一轮定时探针立刻用新值复查
    try:
        health.monitor._cookie_last_check = 0
    except Exception:
        pass
    # 4) 即时验证（口径与定时探针一致）
    verdict = health.verify_cookie(key, cookie)
    return {
        'ok': True, 'platform': key, 'label': label,
        'hot_reloaded': True, 'saved_file': fname,
        'verify': verdict,
        'message': ('验证通过，已即时生效' if verdict['ok']
                    else f'已保存并生效，但验证未通过：{verdict["error"]}'),
    }


@app.get('/')
async def root():
    return {'service': 'CreatorBox Parser', 'version': '2.0.0',
            'docs': '/docs', 'health': '/api/health', 'admin': '/admin'}


@app.get('/admin')
async def admin_dashboard():
    """运营后台（单文件，同源可用）。

    ⚠️ 2026-10-11：这里原先服务的是 admin/dashboard.html（只读看板）。
       现在改为服务 admin/index.html —— 它是 dashboard 的【超集】
       （大盘 + 卡密/违禁词/用户/Cookie 的读写），旧文件保留未删，
       需要旧版可直接访问 /admin/legacy。

       同源提供的好处：浏览器同源策略下 fetch 不会遇到 file:// 的跨域问题，
       也不需要用户手工填服务地址。file:// 直接打开双击也行。
    """
    name = 'index.html' if (Path(__file__).resolve().parent.parent
                            / 'admin' / 'index.html').exists() else 'dashboard.html'
    path = Path(__file__).resolve().parent.parent / 'admin' / name
    if not path.exists():
        raise HTTPException(404, f'admin/{name} 不存在')
    return HTMLResponse(path.read_text(encoding='utf-8'))


@app.get('/admin/legacy')
async def admin_legacy_dashboard():
    """旧版只读看板（保留）。新版在 /admin。"""
    path = Path(__file__).resolve().parent.parent / 'admin' / 'dashboard.html'
    if not path.exists():
        raise HTTPException(404, 'admin/dashboard.html 不存在')
    return HTMLResponse(path.read_text(encoding='utf-8'))
