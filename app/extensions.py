"""Redis client."""

import redis.asyncio as redis

_redis: redis.Redis | None = None


async def init_redis(url: str) -> redis.Redis:
    global _redis
    _redis = redis.from_url(url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> redis.Redis:
    if _redis is None:
        raise RuntimeError("Redis client has not been initialized. Call init_redis() first.")
    return _redis
