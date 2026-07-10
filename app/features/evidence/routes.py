"""Evidence routes: JSON endpoints behind the upload table (init, presigned
part-URL issuance, status/resume, finalize, pause/resume, delete) - driven
by client-side JS, not full page renders. Read-only routes (list/status/
part-url) are gated purely by the same case-membership visibility check as
case detail (owner/creator/case member) - viewing evidence on a case you
have access to never requires a separate org-wide permission, same
reasoning as cases/routes.py's view routes. State-changing upload-lifecycle
routes (init/finalize/pause/resume) still require EVIDENCE_UPLOAD on top of
that, and delete still requires EVIDENCE_DELETE - those are real management
actions, not viewing.

Only the routes the app's own JS calls are CSRF-protected form posts
(init/finalize/pause/resume/delete) - the part-URL route is a GET (CSRF
only ever guards state-changing methods, see core/security/csrf.py) and the
part bytes themselves never touch this app at all: the browser PUTs them
straight to MinIO using the presigned URL this route hands back.
"""

from __future__ import annotations

from quart import Blueprint, abort, g, jsonify, request

from app.core.security.org_permissions import (
    get_user_org_membership,
    is_org_owner,
    require_org_permission,
)
from app.core.security.sessions import login_required
from app.features.audit import service as audit_service
from app.features.cases.permissions import EVIDENCE_DELETE, EVIDENCE_UPLOAD
from app.features.cases.service import get_case_for_user
from app.features.evidence.repository import get_evidence as _get_evidence_row
from app.features.evidence.service import (
    EvidenceError,
    cancel_or_delete,
    finalize_upload,
    get_part_upload_url,
    get_upload_state,
    init_upload,
    list_case_evidence,
    pause_upload,
    resume_upload,
)

evidence_bp = Blueprint("evidence", __name__, url_prefix="/cases")


def _ip() -> str | None:
    return request.remote_addr


async def _is_owner() -> bool:
    membership = await get_user_org_membership(g.user_id)
    return bool(membership and is_org_owner(g.user_id, membership))


async def _require_visible_case(case_id: str):
    case = await get_case_for_user(case_id, g.user_id, is_owner=await _is_owner())
    if not case:
        abort(404)
    return case


async def _require_evidence_in_case(evidence_id: str, case_id: str):
    """404 if evidence_id doesn't exist or belongs to a different case.
    Prevents IDOR: a user who can see case A cannot read evidence from case B
    by guessing evidence IDs and substituting the case_id in the URL."""
    ev = await _get_evidence_row(evidence_id)
    if not ev or ev["case_id"] != case_id:
        abort(404)
    return ev


@evidence_bp.route("/<case_id>/evidence")
@login_required
async def list_view(case_id: str):
    await _require_visible_case(case_id)
    items = await list_case_evidence(case_id)
    return jsonify(
        {
            "items": [
                {
                    "id": item["id"],
                    "filename": item["filename"],
                    "mime_type": item["mime_type"],
                    "size_bytes": item["size_bytes"],
                    "received_bytes": item["received_bytes"],
                    "status": item["status"],
                    "sha256": item["sha256"],
                    "uploaded_by_name": item["uploaded_by_name"],
                    "uploaded_at": item["uploaded_at"].isoformat() if item["uploaded_at"] else None,
                }
                for item in items
            ]
        }
    )


@evidence_bp.route("/<case_id>/evidence/init", methods=["POST"])
@require_org_permission(EVIDENCE_UPLOAD)
async def init_view(case_id: str):
    # Form-encoded, not JSON - the CSRF middleware only ever inspects
    # request.form for the csrf_token field (see core/security/csrf.py), so
    # every state-changing request in this app must be sent that way.
    await _require_visible_case(case_id)
    form = await request.form
    try:
        result = await init_upload(
            case_id=case_id,
            filename=form.get("filename", ""),
            size_bytes=int(form.get("size_bytes", 0) or 0),
            uploaded_by=g.user_id,
        )
    except EvidenceError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@evidence_bp.route("/<case_id>/evidence/<evidence_id>/status")
@login_required
async def status_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    await _require_evidence_in_case(evidence_id, case_id)
    try:
        state = await get_upload_state(evidence_id)
    except EvidenceError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(state)


@evidence_bp.route("/<case_id>/evidence/<evidence_id>/parts/<int:part_number>/url")
@login_required
async def part_url_view(case_id: str, evidence_id: str, part_number: int):
    await _require_visible_case(case_id)
    await _require_evidence_in_case(evidence_id, case_id)
    try:
        url = await get_part_upload_url(evidence_id, part_number)
    except EvidenceError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"url": url})


@evidence_bp.route("/<case_id>/evidence/<evidence_id>/finalize", methods=["POST"])
@require_org_permission(EVIDENCE_UPLOAD)
async def finalize_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    await _require_evidence_in_case(evidence_id, case_id)
    try:
        result = await finalize_upload(evidence_id)
    except EvidenceError as exc:
        await audit_service.record_case_activity(
            case_id=case_id,
            actor_id=g.user_id,
            action=audit_service.EVIDENCE_UPLOAD_FAILED,
            target_label=evidence_id,
            status="failure",
            ip_address=_ip(),
            metadata={"error": str(exc)},
        )
        return jsonify({"error": str(exc)}), 400
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.EVIDENCE_UPLOADED,
        target_label=result["filename"],
        ip_address=_ip(),
    )
    return jsonify(result)


@evidence_bp.route("/<case_id>/evidence/<evidence_id>/pause", methods=["POST"])
@require_org_permission(EVIDENCE_UPLOAD)
async def pause_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    await _require_evidence_in_case(evidence_id, case_id)
    try:
        await pause_upload(evidence_id)
    except EvidenceError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@evidence_bp.route("/<case_id>/evidence/<evidence_id>/resume", methods=["POST"])
@require_org_permission(EVIDENCE_UPLOAD)
async def resume_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    await _require_evidence_in_case(evidence_id, case_id)
    try:
        await resume_upload(evidence_id)
    except EvidenceError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@evidence_bp.route("/<case_id>/evidence/<evidence_id>/delete", methods=["POST"])
@require_org_permission(EVIDENCE_DELETE)
async def delete_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    await _require_evidence_in_case(evidence_id, case_id)
    try:
        result = await cancel_or_delete(evidence_id)
    except EvidenceError as exc:
        return jsonify({"error": str(exc)}), 400
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.EVIDENCE_DELETED,
        target_label=result["filename"],
        ip_address=_ip(),
    )
    return jsonify({"ok": True})
