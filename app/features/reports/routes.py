"""Report persistence routes.

One report per case (the analyst's draft). GET returns the latest version's
content; PUT upserts the draft, creating the report row on first save and
appending a new version row on every subsequent save.
"""

from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, request

from app.core.db.orm import db
from app.core.security.org_permissions import get_user_org_membership, is_org_owner
from app.core.security.sessions import login_required
from app.core.utils.ids import new_id
from app.features.audit import service as audit_service
from app.features.cases.service import get_case_for_user

reports_bp = Blueprint("reports", __name__)


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


@reports_bp.route("/cases/<case_id>/report")
@login_required
async def get_report_view(case_id: str):
    """Return the latest draft content for a case report, or empty if none exists."""
    await _require_visible_case(case_id)
    report = await db.table("reports").where("case_id", case_id).first()
    if not report:
        return jsonify({"content": None, "title": None})
    version = await (
        db.table("report_versions")
        .where("report_id", report["id"])
        .order_by("version", "desc")
        .first()
    )
    return jsonify({
        "report_id": report["id"],
        "title": report["title"],
        "status": report["status"],
        "content": version["content"] if version else None,
        "version": version["version"] if version else 0,
    })


@reports_bp.route("/cases/<case_id>/report", methods=["PUT"])
@login_required
async def save_report_view(case_id: str):
    """Upsert the case report draft and append a version row."""
    await _require_visible_case(case_id)
    body = request.get_json(silent=True) or {}
    content: str = (body.get("content") or "").strip()
    title: str = (body.get("title") or "Investigation Report").strip()[:255]

    if not content:
        return jsonify({"error": "content is required"}), 400

    report = await db.table("reports").where("case_id", case_id).first()
    if report:
        report_id = report["id"]
        await db.table("reports").where("id", report_id).update({"title": title})
    else:
        report_id = new_id()
        await db.table("reports").create({
            "id": report_id,
            "case_id": case_id,
            "title": title,
            "status": "draft",
            "created_by": g.user_id,
        })

    last_version = await (
        db.table("report_versions")
        .where("report_id", report_id)
        .order_by("version", "desc")
        .first()
    )
    next_version = (last_version["version"] + 1) if last_version else 1
    await db.table("report_versions").create({
        "id": new_id(),
        "report_id": report_id,
        "version": next_version,
        "content": content,
        "created_by": g.user_id,
    })

    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.REPORT_SAVED,
        target_label=title,
        ip_address=request.remote_addr,
        metadata={"version": next_version},
    )

    return jsonify({"report_id": report_id, "version": next_version}), 200
