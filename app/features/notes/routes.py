"""Case notepad routes — one shared scratchpad per case."""

from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, request

from app.core.security.org_permissions import get_user_org_membership, is_org_owner
from app.core.security.sessions import login_required
from app.features.audit import service as audit_service
from app.features.cases.service import get_case_for_user
from app.features.notes import repository

notes_bp = Blueprint("notes", __name__)


async def _require_visible_case(case_id: str):
    membership = await get_user_org_membership(g.user_id)
    owner_org_id = (
        membership["organization_id"] if membership and is_org_owner(g.user_id, membership) else None
    )
    case = await get_case_for_user(case_id, g.user_id, owner_org_id=owner_org_id)
    if not case:
        abort(404)
    return case


@notes_bp.route("/cases/<case_id>/note")
@login_required
async def get_note_view(case_id: str):
    await _require_visible_case(case_id)
    row = await repository.get_case_note(case_id)
    return jsonify({"content": row["content"] if row else None})


@notes_bp.route("/cases/<case_id>/note", methods=["PUT"])
@login_required
async def save_note_view(case_id: str):
    await _require_visible_case(case_id)
    body = request.get_json(silent=True) or {}
    content: str = (body.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    await repository.upsert_case_note(case_id, content, g.user_id)

    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.NOTE_SAVED,
        target_label=(content.splitlines()[0] if content else "")[:80],
        ip_address=request.remote_addr,
    )

    return jsonify({"ok": True}), 200
