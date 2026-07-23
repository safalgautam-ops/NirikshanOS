"""Analysis worker — real execution via docker_runner."""

import asyncio
import json
from pathlib import Path

import yaml

import redis.asyncio as aioredis

from app.config import Config
from app.core.db.pool import close_pool, init_pool
from app.core.object_storage import download_object
from app.features.admin_modules import repository as module_defs_repo
from app.features.analysis import repository
from app.features.analysis.queue_service import POP_TIMEOUT, _key
from app.features.evidence.repository import get_evidence
from app.features.instances import repository as instances_repo
from workers.analyzers.docker_runner import RunConfig, run_container

QUEUES = ["light_queue", "medium_queue", "heavy_queue", "full_queue"]

INSTANCE_CHECK_QUEUE_KEY = "nirikshan:instance_check_queue"

TEST_QUEUE_KEY = "nirikshan:test_queue"


def _build_module_entry(
    module_id: str, module_name: str, options: dict, db_mod: dict, files: list[dict]
) -> dict:
    """Convert a DB-managed module (admin_modules) into the execution_spec shape run_analysis.py dispatches via registry.dispatch_spec() → loader.run_yaml_module()."""
    entry: dict = {"id": module_id, "name": module_name, "options": options}
    pipeline_spec = db_mod.get("pipeline_spec")
    if pipeline_spec:
        try:
            spec = json.loads(pipeline_spec) if isinstance(pipeline_spec, str) else pipeline_spec
            spec["id"] = module_id
            entry["execution_spec"] = spec
        except Exception as exc:
            print(f"[worker] failed to parse pipeline_spec for {module_id}: {exc}")
    elif files:
        entry_file = next((f for f in files if f["is_entry_point"]), files[0])
        filename = entry_file["filename"]
        content = entry_file["content"] or ""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext in ("yaml", "yml"):
            try:
                spec = yaml.safe_load(content) or {}
                spec["id"] = module_id
                entry["execution_spec"] = spec
            except Exception as exc:
                print(f"[worker] failed to parse YAML entry point for {module_id}: {exc}")
        else:
            entry["execution_spec"] = {
                "id": module_id,
                "script": content,
            }
    return entry


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
    running_task_ids = [t["id"] for t in tasks]

    evidence = await get_evidence(job["evidence_id"])
    if not evidence or not evidence.get("s3_key"):
        error_msg = "Evidence not found or not uploaded to storage"
        await repository.update_job_status(job_id, "failed", error_message=error_msg)
        for task_id in running_task_ids:
            try:
                await repository.update_task_status(task_id, "failed", error_message=error_msg)
            except Exception:
                pass
        return

    local_evidence = Path(Config.JOBS_DIR) / job_id / "input" / "evidence"
    print(f"[worker] downloading evidence s3_key={evidence['s3_key']}")
    await download_object(
        bucket=Config.MINIO_BUCKET_PRIVATE,
        key=evidence["s3_key"],
        local_path=str(local_evidence),
    )

    _module_defs: dict[str, dict] = {}
    _module_files: dict[str, list[dict]] = {}
    for t in tasks:
        db_mod = await module_defs_repo.get_module(t["module_id"])
        if db_mod:
            _module_defs[t["module_id"]] = db_mod
            _module_files[t["module_id"]] = await module_defs_repo.list_files(t["module_id"])

    modules_list = []
    for t in tasks:
        options: dict = {}
        if t.get("options_json"):
            try:
                options = json.loads(t["options_json"])
            except json.JSONDecodeError as exc:
                print(f"[worker] malformed options_json for task {t['id']}: {exc}")
        db_mod = _module_defs.get(t["module_id"]) or {}
        files = _module_files.get(t["module_id"], [])
        modules_list.append(_build_module_entry(t["module_id"], t["module_name"], options, db_mod, files))

    timeout = max(
        (_module_defs[m["id"]]["timeout_seconds"] if m["id"] in _module_defs else 120 for m in modules_list),
        default=120,
    )

    config = RunConfig(
        job_id=job_id,
        evidence_path=str(local_evidence),
        runtime_image=job["runtime_image"],
        modules=modules_list,
        timeout_seconds=timeout,
    )

    print(f"[worker] running container image={config.runtime_image} timeout={timeout}s")
    result = await run_container(config)
    print(f"[worker] container done exit_code={result.exit_code} time={result.execution_time:.1f}s")

    module_statuses: dict = {}
    result_json = Path(result.output_dir) / "result.json"
    result_json_missing = not result_json.exists()
    if result_json_missing:
        if result.exit_code == 0:
            print("[worker] result.json not written by container — treating as failure")
            result = result.__class__(
                exit_code=-1,
                stdout_path=result.stdout_path,
                stderr_path=result.stderr_path,
                output_dir=result.output_dir,
                artifacts=result.artifacts,
                execution_time=result.execution_time,
                error_message="Container exited 0 but did not write result.json — image may not implement the NirikshanOS analyzer contract",
            )
    else:
        try:
            parsed_json = json.loads(result_json.read_text())
            module_statuses = parsed_json.get("modules", {})
            if parsed_json.get("status") == "partial" and not result.error_message:
                result = result.__class__(
                    exit_code=result.exit_code,
                    stdout_path=result.stdout_path,
                    stderr_path=result.stderr_path,
                    output_dir=result.output_dir,
                    artifacts=result.artifacts,
                    execution_time=result.execution_time,
                    error_message="One or more modules failed (partial)",
                )
        except Exception as e:
            print(f"[worker] could not parse result.json: {e}")

    for task in tasks:
        entry = module_statuses.get(task["module_id"], {})
        status = entry.get("status", "")
        if status == "success":
            await repository.update_task_status(task["id"], "completed")
        elif status in ("failed", "skipped"):
            await repository.update_task_status(task["id"], "failed", error_message=entry.get("error"))
        else:
            if result.exit_code == 0 and not result_json_missing:
                await repository.update_task_status(task["id"], "completed")
            else:
                await repository.update_task_status(task["id"], "failed", error_message=result.error_message)

        safe_module = task["module_id"].replace(".", "_").replace("/", "_")
        stdout_path = str(Path(result.output_dir) / f"{safe_module}.txt")
        stderr_path = str(Path(result.output_dir) / f"{safe_module}.stderr.txt")
        try:
            await repository.save_result(
                job_id=job_id,
                task_id=task["id"],
                case_id=job["case_id"],
                evidence_id=job["evidence_id"],
                module_id=task["module_id"],
                summary_json={},
                normalized_json={"iocs": [], "findings": [], "artifacts": []},
                stdout_path=stdout_path if Path(stdout_path).exists() else None,
                stderr_path=stderr_path if Path(stderr_path).exists() else None,
                artifact_path=None,
            )
            print(f"[worker] saved result for task={task['id']} module={task['module_id']}")
        except Exception as e:
            print(f"[worker] could not save result for task={task['id']}: {e}")

    if result.error_message:
        await repository.update_job_status(job_id, "failed", error_message=result.error_message)
    else:
        await repository.update_job_status(job_id, "completed")

    print(f"[worker] job {job_id} finished")


async def _process_test_run(run_id: str) -> None:
    """Ad-hoc IDE 'Test' run — no case, no evidence row, just a sample file uploaded straight from the Test dialog."""
    run = await module_defs_repo.get_test_run(run_id)
    if run is None:
        print(f"[worker] test run {run_id} not found in DB — skipping")
        return

    await module_defs_repo.update_test_run_status(run_id, "running")
    module_id = run["module_id"]

    db_mod = await module_defs_repo.get_module(module_id)
    if not db_mod:
        await module_defs_repo.update_test_run_status(
            run_id, "failed", error_message="Module no longer exists"
        )
        return

    instance = await instances_repo.get_instance(run["instance_id"])
    if not instance:
        await module_defs_repo.update_test_run_status(
            run_id, "failed", error_message="Instance no longer exists"
        )
        return

    files = await module_defs_repo.list_files(module_id)
    job_id = f"test_{run_id}"
    local_evidence = Path(Config.JOBS_DIR) / job_id / "input" / "evidence"

    print(f"[worker] test run={run_id} module={module_id} downloading s3_key={run['s3_key']}")
    await download_object(
        bucket=Config.MINIO_BUCKET_PRIVATE,
        key=run["s3_key"],
        local_path=str(local_evidence),
    )

    entry = _build_module_entry(module_id, db_mod["display_name"], {}, db_mod, files)

    config = RunConfig(
        job_id=job_id,
        evidence_path=str(local_evidence),
        runtime_image=instance["image_tag"],
        modules=[entry],
        timeout_seconds=db_mod.get("timeout_seconds") or 120,
    )

    print(f"[worker] test run={run_id} running container image={config.runtime_image}")
    result = await run_container(config)
    print(
        f"[worker] test run={run_id} container done exit_code={result.exit_code} time={result.execution_time:.1f}s"
    )

    result_json_path = Path(result.output_dir) / "result.json"
    module_entry: dict = {}
    if result_json_path.exists():
        try:
            module_entry = json.loads(result_json_path.read_text()).get("modules", {}).get(module_id, {})
        except Exception as exc:
            print(f"[worker] test run={run_id} could not parse result.json: {exc}")

    def _read_capped(filename: str | None, cap: int = 100_000) -> str | None:
        if not filename:
            return None
        path = Path(result.output_dir) / filename
        if not path.exists():
            return None
        text = path.read_text(errors="replace")
        return text if len(text) <= cap else text[:cap] + "\n...[truncated]"

    output = {
        "status": module_entry.get("status") or ("success" if result.exit_code == 0 else "failed"),
        "stdout": _read_capped(module_entry.get("stdout_file")),
        "stderr": _read_capped(module_entry.get("stderr_file")),
        "steps": module_entry.get("steps"),
        "exit_code": result.exit_code,
        "execution_time": round(result.execution_time, 2),
    }

    if result.error_message or output["status"] == "failed":
        await module_defs_repo.update_test_run_status(
            run_id,
            "failed",
            error_message=result.error_message or module_entry.get("error") or "Module reported failure",
            result_json=json.dumps(output),
        )
    else:
        await module_defs_repo.update_test_run_status(run_id, "completed", result_json=json.dumps(output))

    print(f"[worker] test run={run_id} finished")


async def _mark_running_tasks_failed(job_id: str, error: str) -> None:
    """Best-effort: find any tasks still in 'running' for job_id and mark them failed."""
    try:
        tasks = await repository.list_tasks_for_job(job_id)
        for task in tasks:
            if task.get("status") == "running":
                try:
                    await repository.update_task_status(task["id"], "failed", error_message=error)
                except Exception:
                    pass
    except Exception:
        pass


async def _check_instance_image(instance_id: str) -> None:
    """`docker image inspect <tag>` — the only reliable way to know if an admin-registered instance's image actually exists on the host."""
    instance = await instances_repo.get_instance(instance_id)
    if instance is None:
        return
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "image",
        "inspect",
        instance["image_tag"],
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    status = "ready" if rc == 0 else "missing"
    await instances_repo.set_image_status(instance_id, status)
    print(f"[worker] instance {instance_id} image_tag={instance['image_tag']} status={status}")


async def _check_all_instances() -> None:
    """One pass over every registered instance at worker startup, so the admin Instances page shows real status without needing a manual Recheck click for the common case of "worker just started, images already built"."""
    instances = await instances_repo.list_instances()
    for instance in instances:
        try:
            await _check_instance_image(instance["id"])
        except Exception as exc:
            print(f"[worker] instance check failed for {instance['id']}: {exc}")


async def _run_worker(redis_client: aioredis.Redis) -> None:
    queue_keys = [_key(q) for q in QUEUES] + [INSTANCE_CHECK_QUEUE_KEY, TEST_QUEUE_KEY]
    print(f"[worker] listening on queues: {QUEUES} + {INSTANCE_CHECK_QUEUE_KEY} + {TEST_QUEUE_KEY}")

    while True:
        result = await redis_client.brpop(queue_keys, timeout=POP_TIMEOUT)
        if result is None:
            continue
        queue_key, value = result

        if queue_key == INSTANCE_CHECK_QUEUE_KEY:
            try:
                await _check_instance_image(value)
            except Exception as exc:
                print(f"[worker] ERROR checking instance {value}: {exc}")
            continue

        if queue_key == TEST_QUEUE_KEY:
            run_id = value
            try:
                await _process_test_run(run_id)
            except Exception as exc:
                print(f"[worker] ERROR processing test run {run_id}: {exc}")
                try:
                    await module_defs_repo.update_test_run_status(run_id, "failed", error_message=str(exc))
                except Exception:
                    pass
            continue

        job_id = value
        try:
            await _process_job(job_id)
        except Exception as exc:
            print(f"[worker] ERROR processing job {job_id}: {exc}")
            try:
                await repository.update_job_status(job_id, "failed", error_message=str(exc))
            except Exception:
                pass
            await _mark_running_tasks_failed(job_id, str(exc))


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

    await _check_all_instances()

    try:
        await _run_worker(redis_client)
    finally:
        await redis_client.aclose()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
