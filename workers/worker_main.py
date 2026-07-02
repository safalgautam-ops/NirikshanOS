"""Mock analysis worker.

Polls all four Redis queues in round-robin order. For each job_id it pops:
  1. Load the analysis_jobs row from DB.
  2. Load the analysis_tasks rows for that job.
  3. Mark job + all tasks as 'running'.
  4. Sleep 2-5 seconds (simulating real tool execution).
  5. Mark all tasks as 'completed'.
  6. Mark job as 'completed'.

No Docker, no real tools, no result parsing. This proves the full pipeline
(API → DB → Redis → worker → DB status updates) before any real execution
is wired in. When Docker integration is added, replace the sleep block with
a real runner call and keep everything else identical.
"""

import asyncio
import random

import redis.asyncio as aioredis  # imports the async Redis client

from app.config import Config
from app.core.db.pool import close_pool, init_pool
from app.features.analysis import repository
from app.features.analysis.queue_service import POP_TIMEOUT, _key

# All Redis queues the worker listens on, in priority order.
# fast_queue is checked first so quick triage jobs don't queue behind heavy ones.
# Each queue is a Redis list. The API probably pushes a job_id into one of these lists when a new analysis request is created.
QUEUES = ["fast_queue", "standard_queue", "heavy_queue", "sandbox_queue"]


async def _process_job(job_id: str) -> None:
    """Run one job through the mock execution lifecycle."""
    job = await repository.get_job(job_id)
    if job is None:
        print(f"[worker] job {job_id} not found in DB — skipping")
        return

    tasks = await repository.list_tasks_for_job(job_id)
    print(f"[worker] starting job={job_id} type={job['job_type']} tasks={len(tasks)}")

    # Mark job + all tasks as running.
    await repository.update_job_status(job_id, "running")
    for task in tasks:
        await repository.update_task_status(task["id"], "running")

    # Simulate tool execution.
    delay = random.uniform(2, 5)  # 2-5s
    print(f"[worker] simulating execution for {delay:.1f}s ...")
    await asyncio.sleep(delay)

    # Mark all tasks completed, then the job.
    for task in tasks:
        await repository.update_task_status(task["id"], "completed")
    await repository.update_job_status(job_id, "completed")

    print(f"[worker] job {job_id} completed")


# main worker loop: keeps running forever and waits for jobs from Redis queues.
async def _run_worker(redis_client: aioredis.Redis) -> None:
    """Main loop: BRPOP from all queues in round-robin(but priority-based), process each job."""
    # name builder: takes a simple queue name and adds a prefix before it to make actual Redis key.
    queue_keys = [_key(q) for q in QUEUES]
    print(f"[worker] listening on queues: {QUEUES}")

    # the worker is desgined to run continuously, processing jobs from the queues.
    while True:
        # BRPOP: blocking right pop:
        # waits until one of the Redis list(analysis:fast_queue or others) has an item, .
        result = await redis_client.brpop(
            queue_keys, timeout=POP_TIMEOUT
        )  # ("analysis:standard_queue", "job_123")
        if result is None:
            # Timeout: all queues were empty. Loop back and wait again.
            continue
        _queue_key, job_id = result  # wait for job IDs from redis
        try:
            await _process_job(job_id)  # process the job
        except Exception as exc:
            # Catch-all so one bad job doesn't kill the worker.
            print(f"[worker] ERROR processing job {job_id}: {exc}")
            try:
                await repository.update_job_status(
                    job_id, "failed", error_message=str(exc)
                )
            except Exception:
                pass


async def main() -> None:
    print("[worker] starting up")

    # Open DB pool (same pattern as app/__init__.py startup hook).
    await init_pool(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        db=Config.DB_NAME,
    )

    # Create own Redis client (not shared with the web app process).
    redis_client = aioredis.from_url(Config.REDIS_URL, decode_responses=True)

    try:
        await _run_worker(redis_client)
    finally:
        await redis_client.aclose()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
