"""Raw DB access for analysis jobs and tasks."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def create_job(
    *,
    case_id: str,
    evidence_id: str,
    org_id: str,
    created_by: str,
    job_type: str,
    queue_name: str,
    runtime_image: str,
    isolation_level: str,
    batch_group: str | None,
    batchable: bool,
) -> str:
    job_id = new_id()
    await db.table("analysis_jobs").create(
        {
            "id": job_id,
            "case_id": case_id,
            "evidence_id": evidence_id,
            "org_id": org_id,
            "created_by": created_by,
            "job_type": job_type,
            "queue_name": queue_name,
            "runtime_image": runtime_image,
            "isolation_level": isolation_level,
            "batch_group": batch_group,
            "batchable": 1 if batchable else 0,
            "status": "queued",
        }
    )
    return job_id


async def create_task(
    *,
    job_id: str,
    module_id: str,
    module_name: str,
    options_json: dict | None = None,
) -> str:
    task_id = new_id()
    await db.table("analysis_tasks").create(
        {
            "id": task_id,
            "job_id": job_id,
            "module_id": module_id,
            "module_name": module_name,
            "options_json": json.dumps(options_json) if options_json else None,
            "status": "queued",
        }
    )
    return task_id


async def get_job(job_id: str) -> dict | None:
    return await db.table("analysis_jobs").where("id", job_id).first()


async def list_jobs_for_evidence(evidence_id: str) -> list[dict]:
    return await (
        db.table("analysis_jobs")
        .where("evidence_id", evidence_id)
        .order_by("created_at", "desc")
        .all(allow_full_table=True)
    )


async def get_active_module_ids_for_evidence(evidence_id: str) -> set[str]:
    """Return module_ids that are currently queued or running for this evidence."""
    active_jobs = await (
        db.table("analysis_jobs")
        .where("evidence_id", evidence_id)
        .where_in("status", ["queued", "running"])
        .all(allow_full_table=True)
    )
    if not active_jobs:
        return set()
    job_ids = [j["id"] for j in active_jobs]
    tasks = await db.table("analysis_tasks").where_in("job_id", job_ids).all(allow_full_table=True)
    return {t["module_id"] for t in tasks}


async def get_task(task_id: str) -> dict | None:
    return await db.table("analysis_tasks").where("id", task_id).first()


async def list_tasks_for_job(job_id: str) -> list[dict]:
    return await (
        db.table("analysis_tasks")
        .where("job_id", job_id)
        .order_by("created_at", "asc")
        .all(allow_full_table=True)
    )


async def save_result(
    *,
    job_id: str,
    task_id: str,
    case_id: str,
    evidence_id: str,
    module_id: str,
    summary_json: dict | None,
    normalized_json: dict | None,
    stdout_path: str | None,
    stderr_path: str | None,
    artifact_path: str | None,
) -> str:
    result_id = new_id()
    await db.table("analysis_results").create(
        {
            "id": result_id,
            "job_id": job_id,
            "task_id": task_id,
            "case_id": case_id,
            "evidence_id": evidence_id,
            "module_id": module_id,
            "summary_json": json.dumps(summary_json) if summary_json is not None else None,
            "normalized_json": json.dumps(normalized_json) if normalized_json is not None else None,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "artifact_path": artifact_path,
        }
    )
    return result_id


async def get_results_for_evidence(evidence_id: str) -> list[dict]:
    return await (
        db.table("analysis_results")
        .where("evidence_id", evidence_id)
        .order_by("created_at", "asc")
        .all(allow_full_table=True)
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    data: dict = {"status": status}
    if status == "running":
        data["started_at"] = _now()
    elif status in ("completed", "failed", "cancelled"):
        data["finished_at"] = _now()
    if error_message is not None:
        data["error_message"] = error_message
    await db.table("analysis_jobs").where("id", job_id).patch(data)


async def update_task_status(
    task_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    data: dict = {"status": status}
    if status == "running":
        data["started_at"] = _now()
    elif status in ("completed", "failed", "cancelled"):
        data["finished_at"] = _now()
    if error_message is not None:
        data["error_message"] = error_message
    await db.table("analysis_tasks").where("id", task_id).patch(data)


async def cancel_job(job_id: str) -> None:
    """Mark all queued/running tasks cancelled, then mark the job cancelled."""
    now = _now()
    tasks = await (
        db.table("analysis_tasks")
        .where("job_id", job_id)
        .where_in("status", ["queued", "running"])
        .all(allow_full_table=True)
    )
    for task in tasks:
        await db.table("analysis_tasks").where("id", task["id"]).patch(
            {"status": "cancelled", "finished_at": now}
        )
    await db.table("analysis_jobs").where("id", job_id).patch({"status": "cancelled", "finished_at": now})
