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

from flask import Blueprint, abort, g, jsonify, request

from app.config import Config
from app.core.security.org_permissions import get_user_org_membership, is_org_owner
from app.core.security.sessions import login_required
from app.features.analysis import findings_service, job_service, notes_service, repository, result_service
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


async def _owner_org_id() -> str | None:
    membership = await get_user_org_membership(g.user_id)
    if membership and is_org_owner(g.user_id, membership):
        return membership["organization_id"]
    return None


async def _require_visible_case(case_id: str):
    case = await get_case_for_user(case_id, g.user_id, owner_org_id=await _owner_org_id())
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
    modules = await get_compatible_modules(evidence_type)
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
    modules = await list_modules()
    return jsonify({"modules": [serialize_module(module) for module in modules]})


@analysis_bp.route("/analysis/modules/<module_id>")
@login_required
async def get_module_view(module_id: str):
    module = await get_module(module_id)
    if module is None or not module["is_enabled"] or module["status"] != "published":
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

    body = request.get_json(silent=True) or {}
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
    selected_modules = await validate_selected_modules(module_ids, evidence_type)

    # Group into the minimal set of jobs.
    plan = await create_analysis_plan(selected_modules)

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


@analysis_bp.route("/analysis/jobs/<job_id>/cancel", methods=["POST"])
@login_required
async def cancel_job_view(job_id: str):
    """Cancel a queued or running job and all its tasks.

    Idempotent: already-terminal jobs (completed/failed/cancelled) return 200
    without touching the DB. The frontend updates its local state optimistically;
    this route makes the DB and worker consistent with that.
    """
    job = await repository.get_job(job_id)
    if not job:
        abort(404)
    await _require_visible_case(job["case_id"])
    if job["status"] not in ("queued", "running"):
        return jsonify({"job_id": job_id, "status": job["status"]}), 200
    await repository.cancel_job(job_id)
    return jsonify({"job_id": job_id, "status": "cancelled"}), 200


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/notes/<module_id>", methods=["PUT"])
@login_required
async def save_note_view(case_id: str, evidence_id: str, module_id: str):
    """Create or update the caller's note for one evidence+module pair.

    One note per (evidence, module, author). Subsequent PUTs overwrite the body.
    Returns 204 on success.
    """
    await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    body = request.get_json(silent=True) or {}
    note_body: str = body.get("body", "")

    try:
        await notes_service.save_note(
            case_id=case_id,
            evidence_id=evidence_id,
            module_id=module_id,
            author_id=g.user_id,
            body=note_body,
        )
    except notes_service.NoteError as exc:
        return jsonify({"error": str(exc)}), 400

    return "", 204


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/notes")
@login_required
async def list_notes_view(case_id: str, evidence_id: str):
    """Return all notes the caller authored for one evidence file.

    Keyed as { "<module_id>": "<body>" } so the frontend can populate
    notesByKey on canvas open without a note-per-module round trip.
    """
    await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    notes = await notes_service.list_notes_for_evidence(evidence_id)
    my_notes = {n["module_id"]: n["body"] for n in notes if n["author_id"] == g.user_id}
    return jsonify({"notes": my_notes})


# ── Findings ──────────────────────────────────────────────────────────────────

@analysis_bp.route("/cases/<case_id>/findings", methods=["POST"])
@login_required
async def create_finding_view(case_id: str):
    """Persist an analyst-authored finding for a case. Returns the new ID."""
    await _require_visible_case(case_id)
    body = request.get_json(silent=True) or {}
    try:
        finding_id = await findings_service.create_finding(
            case_id=case_id,
            evidence_id=body.get("evidence_id"),
            module_id=body.get("module_id"),
            author_id=g.user_id,
            title=body.get("title", ""),
            description=body.get("description", ""),
            severity=body.get("severity", "medium"),
            confidence=body.get("confidence", "medium"),
            source_evidence=body.get("source_evidence"),
            source_module=body.get("source_module"),
        )
    except findings_service.FindingError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"id": finding_id}), 201


@analysis_bp.route("/cases/<case_id>/findings")
@login_required
async def list_findings_view(case_id: str):
    """Return all findings for a case, ordered oldest-first."""
    await _require_visible_case(case_id)
    findings = await findings_service.list_findings(case_id)
    return jsonify({"findings": [
        {
            "id": f["id"],
            "title": f["title"],
            "description": f["description"],
            "severity": f["severity"],
            "confidence": f["confidence"],
            "evidence_id": f["evidence_id"],
            "module_id": f["module_id"],
            "source_evidence": f["source_evidence"],
            "source_module": f["source_module"],
            "author_id": f["author_id"],
            "created_at": _serialize_dt(f.get("created_at")),
        }
        for f in findings
    ]})


# ── Indicators ────────────────────────────────────────────────────────────────

@analysis_bp.route("/cases/<case_id>/indicators", methods=["POST"])
@login_required
async def create_indicator_view(case_id: str):
    """Persist an IOC for a case. Silently deduplicates by (case, type, value)."""
    await _require_visible_case(case_id)
    body = request.get_json(silent=True) or {}
    try:
        indicator_id = await findings_service.create_indicator(
            case_id=case_id,
            evidence_id=body.get("evidence_id"),
            module_id=body.get("module_id"),
            author_id=g.user_id,
            ioc_type=body.get("type", ""),
            value=body.get("value", ""),
            severity=body.get("severity", "medium"),
            confidence=body.get("confidence", "medium"),
            source_evidence=body.get("source_evidence"),
            source_module=body.get("source_module"),
        )
    except findings_service.FindingError as exc:
        return jsonify({"error": str(exc)}), 400
    # 200 for a silently-skipped duplicate (no resource was created), 201 for new.
    status = 201 if indicator_id is not None else 200
    return jsonify({"id": indicator_id}), status


@analysis_bp.route("/cases/<case_id>/indicators")
@login_required
async def list_indicators_view(case_id: str):
    """Return all indicators for a case, ordered oldest-first."""
    await _require_visible_case(case_id)
    indicators = await findings_service.list_indicators(case_id)
    return jsonify({"indicators": [
        {
            "id": i["id"],
            "type": i["ioc_type"],
            "value": i["value"],
            "severity": i["severity"],
            "confidence": i["confidence"],
            "evidence_id": i["evidence_id"],
            "module_id": i["module_id"],
            "source_evidence": i["source_evidence"],
            "source_module": i["source_module"],
            "author_id": i["author_id"],
            "created_at": _serialize_dt(i.get("created_at")),
        }
        for i in indicators
    ]})
