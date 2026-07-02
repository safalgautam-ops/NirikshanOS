"""Orchestrates the persistence of a planner output into the database.

This is the write side of the analysis feature. It takes the structured
job plan from planner.create_analysis_plan and turns each AnalysisJobPlan
into one analysis_jobs row + N analysis_tasks rows (one per module).

No Docker, no Redis, no workers are touched here. All rows land with
status='queued'. Dispatching to a real queue is a later step.
"""

from __future__ import annotations

from app.features.analysis import repository
from app.features.analysis.planner import AnalysisJobPlan


async def create_jobs_from_plan(
    *,
    case_id: str,
    evidence_id: str,
    org_id: str,
    created_by: str,
    plan: list[AnalysisJobPlan],
    module_options: dict[str, dict] | None = None,
) -> list[str]:
    """Persist every job plan as DB rows and return the new job IDs.

    For each AnalysisJobPlan:
      - Creates one analysis_jobs row.
      - Creates one analysis_tasks row per module inside that job.
      - Stores per-module options in options_json if provided.

    `module_options` maps module_id → options dict, e.g.:
      {"generic.strings_extraction": {"min_length": 8}}
    Modules with no entry in the dict get options_json = NULL.
    """
    job_ids: list[str] = []

    for job_plan in plan:
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
        for module in job_plan.modules:
            options = (module_options or {}).get(module.id)
            await repository.create_task(
                job_id=job_id,
                module_id=module.id,
                module_name=module.name,
                options_json=options,
            )
        job_ids.append(job_id)

    return job_ids


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
