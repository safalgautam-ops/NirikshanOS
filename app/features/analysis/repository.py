"""Raw DB access for analysis jobs and tasks.

Thin ORM wrappers only — no policy checks, no planner logic, no queue
dispatch, no business decisions. See job_service.py for orchestration.
"""

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
        .all()
    )


async def get_active_module_ids_for_evidence(evidence_id: str) -> set[str]:
    """Return module_ids that are currently queued or running for this evidence.

    Used by job_service to skip re-queuing a module that's already in flight.
    Completed/failed modules are not included — those are eligible for re-run.
    """
    active_jobs = await (
        db.table("analysis_jobs")
        .where("evidence_id", evidence_id)
        .where_in("status", ["queued", "running"])
        .all()
    )
    if not active_jobs:
        return set()
    job_ids = [j["id"] for j in active_jobs]
    tasks = await (
        db.table("analysis_tasks")
        .where_in("job_id", job_ids)
        .all()
    )
    return {t["module_id"] for t in tasks}


async def list_tasks_for_job(job_id: str) -> list[dict]:
    return await (
        db.table("analysis_tasks")
        .where("job_id", job_id)
        .order_by("created_at", "asc")
        .all()
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
