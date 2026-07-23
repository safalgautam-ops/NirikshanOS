"""Assembles the full Result Canvas payload for one evidence file."""

from __future__ import annotations

import json

from app.features.analysis import repository


def _decode(value) -> dict | list | None:
    """Safely JSON-decode a DB value that may already be a dict/list or a string."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


async def get_results_for_evidence(
    evidence_id: str,
    evidence: dict,
    jobs: list[dict],
) -> dict:
    """Return the full Result Canvas shape for one evidence file."""
    raw_results = await repository.get_results_for_evidence(evidence_id)
    results_by_task: dict[str, dict] = {r["task_id"]: r for r in raw_results}

    jobs_out = []
    for job in jobs:
        tasks_out = []
        for task in job.get("tasks", []):
            saved = results_by_task.get(task["id"])
            task_result = None
            if saved:
                summary = _decode(saved.get("summary_json")) or {}
                normalized = _decode(saved.get("normalized_json")) or {}
                task_result = {
                    "summary": summary,
                    "iocs": normalized.get("iocs", []),
                    "findings": normalized.get("findings", []),
                    "artifacts": normalized.get("artifacts", []),
                    "raw_output": {
                        "stdout_path": saved.get("stdout_path"),
                        "stderr_path": saved.get("stderr_path"),
                    },
                }
            tasks_out.append(
                {
                    "task_id": task["id"],
                    "module_id": task["module_id"],
                    "module_name": task["module_name"],
                    "status": task["status"],
                    "result": task_result,
                }
            )
        jobs_out.append(
            {
                "job_id": job["id"],
                "job_type": job["job_type"],
                "status": job["status"],
                "tasks": tasks_out,
            }
        )

    return {
        "case_id": evidence["case_id"],
        "evidence_id": evidence_id,
        "evidence": {
            "filename": evidence.get("filename"),
            "type": evidence.get("file_type", "unknown"),
            "sha256": evidence.get("sha256"),
        },
        "jobs": jobs_out,
    }
