"""Orchestrates the persistence of a planner output into the database.

This is the write side of the analysis feature. It takes the structured
job plan from planner.create_analysis_plan and turns each AnalysisJobPlan
into one analysis_jobs row + N analysis_tasks rows (one per module).

Deduplication rule:
  - If a module is already queued/running for the same evidence → skip it.
  - If a module previously completed/failed → allow re-run (new rows created).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.features.analysis import queue_service, repository
from app.features.analysis.planner import AnalysisJobPlan


@dataclass
class CreateJobsResult:
    job_ids: list[str] = field(default_factory=list)
    skipped_modules: list[str] = field(default_factory=list)


async def create_jobs_from_plan(
    *,
    case_id: str,
    evidence_id: str,
    org_id: str,
    created_by: str,
    plan: list[AnalysisJobPlan],
    module_options: dict[str, dict] | None = None,
) -> CreateJobsResult:
    """Persist new job plans as DB rows, skipping modules already in flight.

    Modules already queued/running for this evidence are filtered out before
    any DB write. Plans that become empty after filtering are dropped entirely.
    Modules that previously completed or failed are NOT filtered — they get
    fresh rows (re-run semantics).
    """
    active_module_ids = await repository.get_active_module_ids_for_evidence(evidence_id)

    result = CreateJobsResult()

    for job_plan in plan:
        new_modules = [m for m in job_plan.modules if m["id"] not in active_module_ids]
        already_active = [m["id"] for m in job_plan.modules if m["id"] in active_module_ids]
        result.skipped_modules.extend(already_active)

        if not new_modules:
            continue

        job_id = await repository.create_job(
            case_id=case_id,
            evidence_id=evidence_id,
            org_id=org_id,
            created_by=created_by,
            job_type=job_plan.job_type,
            queue_name=job_plan.queue_name,
            runtime_image=job_plan.runtime_image,
            isolation_level=job_plan.isolation_level,
            batch_group=job_plan.batch_group,
            batchable=job_plan.batchable,
        )
        for module in new_modules:
            options = (module_options or {}).get(module["id"])
            await repository.create_task(
                job_id=job_id,
                module_id=module["id"],
                module_name=module["display_name"],
                options_json=options,
            )
        await queue_service.enqueue_job(job_id, job_plan.queue_name)
        result.job_ids.append(job_id)

    return result


async def get_job_with_tasks(job_id: str) -> dict | None:
    """Fetch one job with its tasks nested under a 'tasks' key."""
    job = await repository.get_job(job_id)
    if not job:
        return None
    job["tasks"] = await repository.list_tasks_for_job(job_id)
    return job


async def list_jobs_for_evidence(evidence_id: str) -> list[dict]:
    """All jobs for one evidence file, each with its tasks."""
    jobs = await repository.list_jobs_for_evidence(evidence_id)
    for job in jobs:
        job["tasks"] = await repository.list_tasks_for_job(job["id"])
    return jobs
