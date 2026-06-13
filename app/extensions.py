"""Redis client.

Mirrors app/core/db/pool.py: a single module-level async Redis client,
used from Week 2 onward for sessions and rate limiting, and from Week 4
for WebSocket pub/sub.

The client lives in a module-level variable (_redis) because a module is loaded once
and lives in memory for the entire runtime of the app.
It is created in init_redis(), shared via get_redis(), and destroyed in close_redis().
"""

# Async Redis library -- non blocking, works with the event loop instead of freezing
import redis.asyncio as redis

_redis: redis.Redis | None = None  # lives here in memory forever
# every part of the app that calls get_redis reads this same object


# called once at server startup -- creates the shared Redis client from a URL
async def init_redis(url: str) -> redis.Redis:
    global _redis
    # Create the client from a URL like "redis://localhost:6379/0"
    # decode_responses=True so reads return str instead of bytes everywhere.
    _redis = redis.from_url(url, decode_responses=True)
    # Return the client so the caller can confirm it was created if eneded
    return _redis


async def close_redis() -> None:
    global _redis
    # Only close if a client actually exists
    if _redis is not None:
        # Closes the underlying connection pool on app shutdown.
        await _redis.aclose()
        _redis = None


def get_redis() -> redis.Redis:
    # If startup never ran, fail immediately with a clear message
    if _redis is None:
        # Fails loudly if something tries to use Redis before startup ran.
        raise RuntimeError(
            "Redis client has not been initialized. Call init_redis() first."
        )
    return _redis
