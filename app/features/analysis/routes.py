"""Analysis routes: module registry reads + job creation.

No url_prefix here — this blueprint's routes span two different path
prefixes (/cases/... and /analysis/...) so each route spells out its
full path.

GET routes require no extra org permission beyond case visibility (reading
which modules exist is not a management action). The POST /analyze route
additionally requires the EVIDENCE_ANALYZE org permission, enforced via
policy.check_can_run.

JSON POST routes send the CSRF token as an X-CSRF-Token request header
(the cookie double-submit pattern still applies — the client must echo the
csrf_token cookie value in this header). Form POST routes use the hidden
field as usual.
"""

from __future__ import annotations

from pathlib import Path

from quart import Blueprint, abort, g, jsonify, request

from app.config import Config
from app.core.security.org_permissions import get_user_org_membership, is_org_owner
from app.core.security.sessions import login_required
from app.features.analysis import job_service, repository, result_service
from app.features.analysis.planner import create_analysis_plan
from app.features.analysis.policy import check_can_run
from app.features.analysis.service import (
    detect_evidence_type,
    get_compatible_modules,
    get_module,
    list_modules,
    serialize_module,
    validate_selected_modules,
)
from app.features.cases.service import get_case_for_user
from app.features.evidence.service import get_evidence

analysis_bp = Blueprint("analysis", __name__)


async def _is_owner() -> bool:
    membership = await get_user_org_membership(g.user_id)
    return bool(membership and is_org_owner(g.user_id, membership))


async def _require_visible_case(case_id: str):
    case = await get_case_for_user(case_id, g.user_id, is_owner=await _is_owner())
    if not case:
        abort(404)
    return case


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/modules")
@login_required
async def compatible_modules_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    evidence_type = detect_evidence_type(evidence)
    modules = get_compatible_modules(evidence_type)
    return jsonify(
        {
            "case_id": case_id,
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "modules": [serialize_module(module) for module in modules],
        }
    )


@analysis_bp.route("/analysis/modules")
@login_required
async def list_modules_view():
    modules = list_modules()
    return jsonify({"modules": [serialize_module(module) for module in modules]})


@analysis_bp.route("/analysis/modules/<module_id>")
@login_required
async def get_module_view(module_id: str):
    module = get_module(module_id)
    if module is None or not module.enabled:
        abort(404)
    return jsonify(serialize_module(module))


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/analyze", methods=["POST"])
@login_required
async def analyze_evidence_view(case_id: str, evidence_id: str):
    """Submit selected modules for analysis against one evidence file.

    Steps:
      1. Confirm the user can access the case and evidence.
      2. Parse the request body (module_ids, optional module_options).
      3. Detect the evidence type for compatibility checks.
      4. Policy check: permission + module validity.
      5. Plan: group modules into the minimal set of jobs.
      6. Persist: create analysis_jobs + analysis_tasks rows.
      7. Return the created job IDs.

    No worker is dispatched yet. All jobs land with status='queued'.
    """
    case = await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    body = await request.get_json(silent=True) or {}
    module_ids: list[str] = body.get("module_ids", [])
    module_options: dict[str, dict] = body.get("module_options", {})

    if not module_ids:
        return jsonify({"error": "module_ids is required and must not be empty."}), 400

    org_id: str = case["organization_id"]
    evidence_type: str = detect_evidence_type(evidence)

    # Policy check: org permission + per-module existence/compatibility.
    policy_result = await check_can_run(
        org_id=org_id,
        user_id=g.user_id,
        module_ids=module_ids,
        evidence_type=evidence_type,
    )
    if not policy_result.allowed:
        return jsonify({"error": policy_result.first_reason(), "violations": [
            {"module_id": v.module_id, "reason": v.reason}
            for v in policy_result.violations
        ]}), 403

    # Load the full AnalysisModule objects (validated by policy above).
    selected_modules = validate_selected_modules(module_ids, evidence_type)

    # Group into the minimal set of jobs.
    plan = create_analysis_plan(selected_modules)

    # Persist jobs + tasks (dedup: skips modules already queued/running).
    result = await job_service.create_jobs_from_plan(
        case_id=case_id,
        evidence_id=evidence_id,
        org_id=org_id,
        created_by=g.user_id,
        plan=plan,
        module_options=module_options or None,
    )

    # Build the response — one entry per newly created job, including task IDs
    # so the frontend can match poll results to the queue entries it built.
    jobs_response = []
    for job_id, job_plan in zip(result.job_ids, plan):
        tasks = await repository.list_tasks_for_job(job_id)
        jobs_response.append({
            "job_id": job_id,
            "job_type": job_plan.job_type,
            "tasks": [
                {
                    "task_id": t["id"],
                    "module_id": t["module_id"],
                    "module_name": t["module_name"],
                }
                for t in tasks
            ],
        })

    return jsonify({
        "case_id": case_id,
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "jobs": jobs_response,
        "skipped_modules": result.skipped_modules,
    }), 201


def _serialize_dt(dt) -> str | None:
    return dt.isoformat() if dt else None


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/jobs")
@login_required
async def list_evidence_jobs_view(case_id: str, evidence_id: str):
    """Return all jobs + tasks for one evidence file, with live statuses.

    Polled by the frontend every 2 s while any job is in queued/running state.
    """
    await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    jobs = await repository.list_jobs_for_evidence(evidence_id)
    result = []
    for job in jobs:
        tasks = await repository.list_tasks_for_job(job["id"])
        result.append({
            "id": job["id"],
            "status": job["status"],
            "job_type": job["job_type"],
            "error_message": job.get("error_message"),
            "created_at": _serialize_dt(job.get("created_at")),
            "started_at": _serialize_dt(job.get("started_at")),
            "finished_at": _serialize_dt(job.get("finished_at")),
            "tasks": [
                {
                    "id": t["id"],
                    "module_id": t["module_id"],
                    "module_name": t["module_name"],
                    "status": t["status"],
                    "error_message": t.get("error_message"),
                    "started_at": _serialize_dt(t.get("started_at")),
                    "finished_at": _serialize_dt(t.get("finished_at")),
                }
                for t in tasks
            ],
        })

    return jsonify({"jobs": result})


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/results")
@login_required
async def get_evidence_results_view(case_id: str, evidence_id: str):
    """Return parsed results for every completed task on one evidence file.

    Backed by the analysis_results table written by the worker after parsing.
    Returns an empty jobs list (not 404) when no jobs have been run yet.
    """
    await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    jobs = await job_service.list_jobs_for_evidence(evidence_id)
    payload = await result_service.get_results_for_evidence(evidence_id, evidence, jobs)
    return jsonify(payload)


@analysis_bp.route("/analysis/tasks/<task_id>/output")
@login_required
async def get_task_output_view(task_id: str):
    """Return the raw stdout + stderr produced by the analyzer container for one task.

    Reads files from the job workspace on disk. Returns empty strings if the
    output files don't exist yet (task still running) or the job workspace was
    cleaned up.
    """
    task = await repository.get_task(task_id)
    if not task:
        abort(404)

    job = await repository.get_job(task["job_id"])
    if not job:
        abort(404)

    # Authorization: the caller must be able to see the case this task belongs to.
    await _require_visible_case(job["case_id"])

    safe_module = task["module_id"].replace(".", "_").replace("/", "_")
    output_dir = Path(Config.JOBS_DIR) / task["job_id"] / "output"
    stdout_file = output_dir / f"{safe_module}.txt"
    stderr_file = output_dir / f"{safe_module}.stderr.txt"

    stdout = stdout_file.read_text(errors="replace") if stdout_file.exists() else ""
    stderr = stderr_file.read_text(errors="replace") if stderr_file.exists() else ""

    return jsonify({
        "task_id": task_id,
        "module_id": task["module_id"],
        "stdout": stdout,
        "stderr": stderr,
    })
