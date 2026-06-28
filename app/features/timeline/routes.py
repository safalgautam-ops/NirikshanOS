"""Timeline routes: the sidebar-level Timeline Center (`/timeline`, case
cards only) and the per-case manual investigation timeline
(`/cases/<case_id>/timeline`). Same row-level case-access rule as every
other case-scoped page (owner/creator/case member - see
cases/service.py.can_access_case) and no separate org permission, per the
reasoning in timeline/service.py's module docstring."""

from __future__ import annotations

from datetime import datetime

from quart import Blueprint, abort, g, redirect, render_template, request, url_for

from app.core.security.org_permissions import get_user_org_membership, is_org_owner
from app.core.security.permissions import get_visible_nav_keys
from app.core.security.sessions import login_required
from app.features.audit import service as audit_service
from app.features.auth.repository import get_user_by_id
from app.features.cases.choices import CLASSIFICATIONS, FORENSIC_STATUSES, SEVERITIES
from app.features.cases.service import get_case_for_user, get_case_members, list_cases_for_user
from app.features.evidence.service import list_case_evidence
from app.features.timeline.choices import NOTE_VISIBILITIES, TASK_PRIORITIES, TASK_STATUSES
from app.features.timeline.service import TimelineError, case_timeline_summaries, create_item, get_item, list_items, update_item

timeline_bp = Blueprint("timeline", __name__)


def _ip() -> str | None:
    return request.remote_addr


async def _is_owner() -> bool:
    membership = await get_user_org_membership(g.user_id)
    return bool(membership and is_org_owner(g.user_id, membership))


async def _require_org_id() -> str:
    membership = await get_user_org_membership(g.user_id)
    if not membership:
        abort(404)
    return membership["organization_id"]


async def _require_visible_case(case_id: str):
    case = await get_case_for_user(case_id, g.user_id, is_owner=await _is_owner())
    if not case:
        abort(404)
    return case


@timeline_bp.route("/timeline")
@login_required
async def center_view():
    org_id = await _require_org_id()
    is_owner = await _is_owner()
    cases = await list_cases_for_user(org_id, g.user_id, is_owner=is_owner)
    summaries = await case_timeline_summaries(cases)
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "timeline/center.html",
        cases=summaries,
        classification_labels=dict(CLASSIFICATIONS),
        severity_labels=dict(SEVERITIES),
        status_labels=dict(FORENSIC_STATUSES),
        visible_keys=visible_keys,
    )


@timeline_bp.route("/cases/<case_id>/timeline")
@login_required
async def case_view(case_id: str):
    case = await _require_visible_case(case_id)
    items = await list_items(case_id)
    members = await get_case_members(case_id)
    creator = await get_user_by_id(case["created_by"])
    assignees = ([{"id": creator["id"], "name": creator["name"]}] if creator else []) + [
        {"id": m["id"], "name": m["name"]} for m in members
    ]
    evidence = await list_case_evidence(case_id)
    visible_keys = await get_visible_nav_keys(g.user_id)
    # JSON-safe subset for the Edit dialog's Alpine state - datetime/date
    # columns get pre-formatted to the exact string each <input> expects,
    # same reasoning as cases/routes.py's analyze_evidence subset.
    items_json_by_id = {
        i["id"]: {
            "id": i["id"],
            "type": i["type"],
            "title": i["title"],
            "description": i["description"] or "",
            "status": i["status"] or "",
            "priority": i["priority"] or "",
            "assigned_to": i["assigned_to"] or "",
            "due_date": i["due_date"].isoformat() if i["due_date"] else "",
            "linked_evidence_id": i["linked_evidence_id"] or "",
            "linked_result_label": i["linked_result_label"] or "",
            "visibility": i["visibility"] or "",
            "timeline_time": i["timeline_time"].strftime("%Y-%m-%dT%H:%M"),
        }
        for i in items
    }
    return await render_template(
        "timeline/case_timeline.html",
        case=case,
        items=items,
        items_json_by_id=items_json_by_id,
        assignees=assignees,
        evidence=evidence,
        task_statuses=TASK_STATUSES,
        task_priorities=TASK_PRIORITIES,
        note_visibilities=NOTE_VISIBILITIES,
        severity_label=dict(SEVERITIES).get(case["severity"], case["severity"]),
        status_label=dict(FORENSIC_STATUSES).get(case["forensic_status"], case["forensic_status"]),
        # The case has no dedicated "assignee" column - the creator is the
        # closest real, unambiguous stand-in for "lead analyst" shown in the
        # header (see cases/repository.py: cases.created_by).
        assigned_to_label=creator["name"] if creator else "—",
        now=datetime.now().strftime("%Y-%m-%dT%H:%M"),
        visible_keys=visible_keys,
        error=request.args.get("error"),
    )


@timeline_bp.route("/cases/<case_id>/timeline/items", methods=["POST"])
@login_required
async def create_item_view(case_id: str):
    await _require_visible_case(case_id)
    form = await request.form
    try:
        await create_item(
            case_id=case_id,
            item_type=form.get("type", ""),
            title=form.get("title", ""),
            description=form.get("description", ""),
            timeline_time=form.get("timeline_time", ""),
            created_by=g.user_id,
            status=form.get("status", ""),
            priority=form.get("priority", ""),
            assigned_to=form.get("assigned_to", ""),
            due_date=form.get("due_date", ""),
            linked_evidence_id=form.get("linked_evidence_id", ""),
            linked_result_label=form.get("linked_result_label", ""),
            visibility=form.get("visibility", ""),
        )
    except TimelineError as exc:
        return redirect(url_for("timeline.case_view", case_id=case_id, error=str(exc)))
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.TIMELINE_ITEM_ADDED,
        target_label=form.get("title", ""),
        ip_address=_ip(),
        metadata={"type": form.get("type", "")},
    )
    return redirect(url_for("timeline.case_view", case_id=case_id))


@timeline_bp.route("/cases/<case_id>/timeline/items/<item_id>/edit", methods=["POST"])
@login_required
async def update_item_view(case_id: str, item_id: str):
    await _require_visible_case(case_id)
    item = await get_item(item_id)
    if not item or item["case_id"] != case_id:
        abort(404)
    form = await request.form
    try:
        await update_item(
            item_id,
            item_type=item["type"],
            title=form.get("title", ""),
            description=form.get("description", ""),
            timeline_time=form.get("timeline_time", ""),
            status=form.get("status", ""),
            priority=form.get("priority", ""),
            assigned_to=form.get("assigned_to", ""),
            due_date=form.get("due_date", ""),
            linked_evidence_id=form.get("linked_evidence_id", ""),
            linked_result_label=form.get("linked_result_label", ""),
            visibility=form.get("visibility", ""),
        )
    except TimelineError as exc:
        return redirect(url_for("timeline.case_view", case_id=case_id, error=str(exc)))
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.TIMELINE_ITEM_UPDATED,
        target_label=form.get("title", ""),
        ip_address=_ip(),
        metadata={"type": item["type"]},
    )
    return redirect(url_for("timeline.case_view", case_id=case_id))
