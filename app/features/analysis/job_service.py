"""Persists a planner output into the database.

This is the write side of the analysis feature. It takes the structured
job plan from planner.create_analysis_plan and turns each AnalysisJobPlan
into one analysis_jobs row + N analysis_tasks rows (one per module).

No Docker, no Redis, no workers are touched here. All jobs land with
status='queued'. Dispatching to a real queue is a later step.
"""

from __future__ import annotations

from app.features.analysis import repository
from app.features.analysis.planner import AnalysisJobPlan


async def submit_analysis(
    *,
    case_id: str,
    evidence_id: str,
    org_id: str,
    created_by: str,
    plan: list[AnalysisJobPlan],
) -> list[str]:
    """Persist every job plan as DB rows and return the new job IDs.

    One analysis_jobs row per AnalysisJobPlan, one analysis_tasks row per
    module inside it. All rows start with status='queued'.
    """
    job_ids: list[str] = []

    for job_plan in plan:
        job_id = await repository.create_job(
            case_id=case_id,
            evidence_id=evidence_id,
            org_id=org_id,
            created_by=created_by,
            queue_name=job_plan.queue_name,
            runtime_image=job_plan.runtime_image,
            isolation_level=job_plan.isolation_level,
            batch_group=job_plan.batch_group,
            batchable=job_plan.batchable,
        )
        for module in job_plan.modules:
            await repository.create_task(
                job_id=job_id,
                module_id=module.id,
                module_name=module.name,
            )
        job_ids.append(job_id)

    return job_ids


async def get_job_with_tasks(job_id: str) -> dict | None:
    """Fetch a job row with its tasks nested under 'tasks' key."""
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
