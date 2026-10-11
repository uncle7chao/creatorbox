"""内存缓存 + 限流（Redis 可选，未配置则用内存）"""
import asyncio
import time

try:
    from app import config
except ImportError:                                  # 直接跑脚本时
    import config


class Cache:
    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        self._mem: dict[str, tuple[float, object]] = {}
        self._redis = None
        self._lock = asyncio.Lock()

    async def init(self):
        if config.REDIS_URL:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    config.REDIS_URL, encoding='utf-8', decode_responses=True)
                await self._redis.ping()
                print('[cache] Redis 已连接')
            except Exception as e:
                print(f'[cache] Redis 连接失败，回退内存: {str(e)[:60]}')
                self._redis = None

    async def get(self, key: str):
        if self._redis:
            try:
                v = await self._redis.get(key)
                if v:
                    import json
                    return json.loads(v)
                return None
            except Exception:
                pass
        async with self._lock:
            item = self._mem.get(key)
            if not item:
                return None
            exp, val = item
            if exp < time.time():
                self._mem.pop(key, None)
                return None
            return val

    async def set(self, key: str, value):
        if self._redis:
            try:
                import json
                await self._redis.set(key, json.dumps(value, ensure_ascii=False),
                                     ex=self.ttl)
                return
            except Exception:
                pass
        async with self._lock:
            self._mem[key] = (time.time() + self.ttl, value)
            # 简单清理，防止无限增长
            if len(self._mem) > 2000:
                now = time.time()
                for k in [k for k, (e, _) in self._mem.items() if e < now]:
                    self._mem.pop(k, None)

    async def clear(self):
        if self._redis:
            try:
                await self._redis.flushdb()
            except Exception:
                pass
        async with self._lock:
            self._mem.clear()


class RateLimiter:
    def __init__(self, per_min: int, window: int = 60):
        self.per_min = per_min
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, ident: str = 'global') -> tuple[bool, dict]:
        # 豁免前缀（Go 版中间件豁免表的同型设计，2026-10-11）：
        # 探针/内部调用以 `internal:` 开头，不占业务配额——
        # 防止「自探自毙」：监控打满限流把真实用户也挡在外面
        if ident and ident.startswith('internal:'):
            return True, {'remaining': self.per_min, 'exempt': True}
        now = time.time()
        async with self._lock:
            arr = [t for t in self._hits.get(ident, []) if now - t < self.window]
            if len(arr) >= self.per_min:
                self._hits[ident] = arr
                return False, {'limit': self.per_min,
                               'retry_after': int(self.window - (now - arr[0]))}
            arr.append(now)
            self._hits[ident] = arr
            # 清理空桶
            if len(self._hits) > 2000:
                for k in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(k, None)
            return True, {'remaining': self.per_min - len(arr)}


cache = Cache(config.CACHE_TTL)
limiter = RateLimiter(config.RATE_LIMIT_PER_MIN, config.RATE_LIMIT_WINDOW)
