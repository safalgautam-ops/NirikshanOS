"""Redis queue operations for analysis jobs.

This file only talks to Redis. It does not know about modules, Docker,
policy, or results. Its only job is to push and pop job IDs between the
four named queues.

Queue names map to Redis list keys:
  light_queue  → analysis:light_queue
  medium_queue → analysis:medium_queue
  heavy_queue  → analysis:heavy_queue
  full_queue   → analysis:full_queue

Push (by job_service) uses LPUSH — adds to the left of the list.
Pop  (by worker)      uses BRPOP — blocks until an item appears on the right.
This gives FIFO order: first pushed is first popped.
"""

from __future__ import annotations

from app.extensions import get_redis

# Prefix keeps analysis queues separate from any other Redis keys in the app.
_QUEUE_PREFIX = "analysis"

# How long BRPOP waits (in seconds) before returning None when the queue is
# empty. Worker uses this to loop and check all queues in round-robin.
POP_TIMEOUT = 2


def _key(queue_name: str) -> str:
    """Redis list key for a given queue name."""
    return f"{_QUEUE_PREFIX}:{queue_name}"


async def enqueue_job(job_id: str, queue_name: str) -> None:
    """Push a job_id onto the named queue. Called by job_service after DB rows are created."""
    redis = get_redis()
    await redis.lpush(_key(queue_name), job_id)


async def dequeue_job(queue_name: str) -> str | None:
    """Pop the next job_id from the named queue. Blocks up to POP_TIMEOUT seconds.
    Returns None if the queue was empty during the timeout window."""
    redis = get_redis()
    # BRPOP returns (key, value) or None on timeout.
    result = await redis.brpop(_key(queue_name), timeout=POP_TIMEOUT)
    if result is None:
        return None
    _key_returned, job_id = result
    return job_id


async def queue_length(queue_name: str) -> int:
    """Number of jobs currently waiting in the named queue."""
    redis = get_redis()
    return await redis.llen(_key(queue_name))
