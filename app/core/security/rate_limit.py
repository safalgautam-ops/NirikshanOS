"""Redis-backed rate limiter for brute-force protection.

Uses the INCR + EXPIRE pattern: the first increment for a key also sets the
TTL, so the window resets naturally after `window_seconds` without a
background job. A race between two concurrent first-requests is harmless —
both will call EXPIRE, and the second just resets the TTL to the same value.
"""
from __future__ import annotations

from quart import abort

from app.extensions import get_redis


async def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    """Increment the attempt counter for `key`. Aborts 429 if over limit.

    Call at the start of any handler that should be rate-limited. The key
    should embed enough context to scope the limit correctly, e.g.:
        f"rate:login:{ip}"          — per-IP login throttle
        f"rate:otp:{email}"         — per-email OTP throttle
        f"rate:2fa:{token_prefix}"  — per-pending-session 2FA throttle
    """
    r = get_redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds)
    if count > max_attempts:
        abort(429)
