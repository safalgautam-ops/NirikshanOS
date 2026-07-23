"""Redis queue operations for analysis jobs."""

from __future__ import annotations

from app.extensions import get_redis

_QUEUE_PREFIX = "analysis"

POP_TIMEOUT = 2


def _key(queue_name: str) -> str:
    """Redis list key for a given queue name."""
    return f"{_QUEUE_PREFIX}:{queue_name}"


async def enqueue_job(job_id: str, queue_name: str) -> None:
    """Push a job_id onto the named queue. Called by job_service after DB rows are created."""
    redis = get_redis()
    await redis.lpush(_key(queue_name), job_id)
