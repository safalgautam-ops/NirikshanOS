"""Redis-backed rate limiter for brute-force protection."""

from __future__ import annotations

from flask import abort

from app.extensions import get_redis


async def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    """Increment the attempt counter for `key`."""
    r = get_redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds)
    if count > max_attempts:
        abort(429)
