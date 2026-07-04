"""Analysis worker — real execution via docker_runner.

For each job_id popped from Redis:
  1. Load job + tasks from DB.
  2. Mark job + tasks as 'running'.
  3. Download evidence from MinIO to local workspace.
  4. Build RunConfig from DB job data.
  5. Call docker_runner.run_container() — starts the analyzer container.
  6. Read /output/result.json produced by run_analysis.py inside the container.
  7. Update per-task and job status from result.json.
"""

import asyncio
import json
from pathlib import Path

import redis.asyncio as aioredis

from app.config import Config
from app.core.db.pool import close_pool, init_pool
from app.core.object_storage import download_object
from app.features.analysis import repository
from app.features.analysis.module_registry import MODULES
from app.features.analysis.parser_service import parse_module_output
from app.features.analysis.queue_service import POP_TIMEOUT, _key
from app.features.evidence.repository import get_evidence
from workers.analyzers.docker_runner import RunConfig, run_container

QUEUES = ["fast_queue", "standard_queue", "heavy_queue", "sandbox_queue"]


async def _process_job(job_id: str) -> None:
    job = await repository.get_job(job_id)
    if job is None:
        print(f"[worker] job {job_id} not found in DB — skipping")
        return

    tasks = await repository.list_tasks_for_job(job_id)
    print(f"[worker] starting job={job_id} type={job['job_type']} tasks={len(tasks)}")

    await repository.update_job_status(job_id, "running")
    for task in tasks:
        await repository.update_task_status(task["id"], "running")

    # Fetch evidence row to get the MinIO s3_key.
    evidence = await get_evidence(job["evidence_id"])
    if not evidence or not evidence.get("s3_key"):
        await repository.update_job_status(
            job_id, "failed", error_message="Evidence not found or not uploaded to storage"
        )
        return

    # Download evidence from MinIO to local path for docker bind mount.
    local_evidence = Path(Config.JOBS_DIR) / job_id / "input" / "evidence"
    print(f"[worker] downloading evidence s3_key={evidence['s3_key']}")
    await download_object(
        bucket=Config.MINIO_BUCKET_PRIVATE,
        key=evidence["s3_key"],
        local_path=str(local_evidence),
    )

    # Build the modules list for job_config.json (same format run_analysis.py reads).
    modules_list = [
        {
            "id":      t["module_id"],
            "name":    t["module_name"],
            "options": json.loads(t["options_json"]) if t.get("options_json") else {},
        }
        for t in tasks
    ]

    # Use the maximum timeout across all modules in this job.
    timeout = max(
        (MODULES[m["id"]].timeout_seconds for m in modules_list if m["id"] in MODULES),
        default=120,
    )

    config = RunConfig(
        job_id=job_id,
        evidence_path=str(local_evidence),
        runtime_image=job["runtime_image"],
        modules=modules_list,
        timeout_seconds=timeout,
        isolation_level=job["isolation_level"],
    )

    print(f"[worker] running container image={config.runtime_image} timeout={timeout}s")
    result = await run_container(config)
    print(f"[worker] container done exit_code={result.exit_code} time={result.execution_time:.1f}s")

    # Read result.json the entrypoint wrote to /output.
    module_statuses: dict = {}
    result_json = Path(result.output_dir) / "result.json"
    if result_json.exists():
        try:
            module_statuses = json.loads(result_json.read_text()).get("modules", {})
        except Exception as e:
            print(f"[worker] could not parse result.json: {e}")

    # Update per-task status and parse + save results.
    for task in tasks:
        entry = module_statuses.get(task["module_id"], {})
        status = entry.get("status", "")
        if status == "success":
            await repository.update_task_status(task["id"], "completed")
        elif status in ("failed", "skipped"):
            await repository.update_task_status(
                task["id"], "failed", error_message=entry.get("error")
            )
        else:
            if result.exit_code == 0:
                await repository.update_task_status(task["id"], "completed")
            else:
                await repository.update_task_status(
                    task["id"], "failed", error_message=result.error_message
                )

        # Parse output and save to analysis_results regardless of status so the
        # Result Canvas always has something to show even for partial runs.
        module = MODULES.get(task["module_id"])
        if module is not None:
            safe_module = task["module_id"].replace(".", "_").replace("/", "_")
            stdout_path = str(Path(result.output_dir) / f"{safe_module}.txt")
            stderr_path = str(Path(result.output_dir) / f"{safe_module}.stderr.txt")
            exit_code = entry.get("exit_code")
            if exit_code is None:
                exit_code = result.exit_code

            parsed = parse_module_output(
                parser_name=module.parser_name,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_code=exit_code,
            )
            normalized = {
                "iocs":      parsed.iocs,
                "findings":  parsed.findings,
                "artifacts": parsed.artifacts,
            }
            try:
                await repository.save_result(
                    job_id=job_id,
                    task_id=task["id"],
                    case_id=job["case_id"],
                    evidence_id=job["evidence_id"],
                    module_id=task["module_id"],
                    summary_json=parsed.summary,
                    normalized_json=normalized,
                    stdout_path=stdout_path if Path(stdout_path).exists() else None,
                    stderr_path=stderr_path if Path(stderr_path).exists() else None,
                    artifact_path=None,
                )
                print(f"[worker] saved result for task={task['id']} module={task['module_id']}")
            except Exception as e:
                print(f"[worker] could not save result for task={task['id']}: {e}")

    # Update job status.
    if result.error_message:
        await repository.update_job_status(job_id, "failed", error_message=result.error_message)
    else:
        await repository.update_job_status(job_id, "completed")

    print(f"[worker] job {job_id} finished")


async def _run_worker(redis_client: aioredis.Redis) -> None:
    queue_keys = [_key(q) for q in QUEUES]
    print(f"[worker] listening on queues: {QUEUES}")

    while True:
        result = await redis_client.brpop(queue_keys, timeout=POP_TIMEOUT)
        if result is None:
            continue
        _queue_key, job_id = result
        try:
            await _process_job(job_id)
        except Exception as exc:
            print(f"[worker] ERROR processing job {job_id}: {exc}")
            try:
                await repository.update_job_status(job_id, "failed", error_message=str(exc))
            except Exception:
                pass


async def main() -> None:
    print("[worker] starting up")

    await init_pool(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        db=Config.DB_NAME,
    )

    redis_client = aioredis.from_url(Config.REDIS_URL, decode_responses=True)

    try:
        await _run_worker(redis_client)
    finally:
        await redis_client.aclose()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
