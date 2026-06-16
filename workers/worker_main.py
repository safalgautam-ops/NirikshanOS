"""Worker entrypoint.

Planned for Week 4: pulls analysis jobs from a Redis queue, dispatches
them to an approved analyzer (workers/analyzers/), and publishes
progress/results via Redis pub/sub (app/core/ws/pubsub.py).

For now this just idles so the worker container stays up.
"""

import asyncio


async def main() -> None:
    print("worker: idle - analysis jobs are implemented in Week 4")
    # Keeps the container alive without busy-looping; replaced in Week 4
    # by a loop that pops jobs off a Redis queue.
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
