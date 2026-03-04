from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, TypeVar

from cachetools import TTLCache

from app.config import get_settings
from app.utils.logging import get_logger

try:
    import redis.asyncio as redis
except ModuleNotFoundError:  # pragma: no cover
    redis = None

logger = get_logger(__name__)

T = TypeVar("T")


class CacheService:
    def __init__(self) -> None:
        settings = get_settings()
        self._local_cache: TTLCache[str, Any] = TTLCache(maxsize=256, ttl=60 * 60 * 12)
        self._redis = None
        if settings.redis_url and redis:
            self._redis = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

    async def get_or_set(self, key: str, ttl_seconds: int, factory: Callable[[], Awaitable[T]]) -> T:
        if key in self._local_cache:
            return self._local_cache[key]

        if self._redis:
            cached = await self._redis.get(key)
            if cached is not None:
                value = json.loads(cached)
                self._local_cache[key] = value
                return value

        value = await factory()
        self._local_cache[key] = value
        if self._redis and _is_json_safe(value):
            await self._redis.set(key, json.dumps(value), ex=ttl_seconds)
        return value


cache_service = CacheService()


def _is_json_safe(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except TypeError:
        return False
