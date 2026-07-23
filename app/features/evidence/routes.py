"""Evidence routes: JSON endpoints behind the upload table (init, presigned part-URL issuance, status/resume, finalize, pause/resume, delete) - driven by client-side JS, not full page renders."""

from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, request

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


async def _require_evidence_in_case(evidence_id: str, case_id: str):
    """404 if evidence_id doesn't exist or belongs to a different case."""
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
    await _require_visible_case(case_id)
    form = request.form
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
