"""Case routes: org-scoped CRUD plus the row-level visibility check that
decides which specific cases a member may see/manage - owner, creator, or
someone explicitly added as a case member (see
app/features/cases/service.py's can_access_case). *Viewing* a case you have
access to never requires a separate org-wide permission (there is no
CASE_VIEW - see cases/permissions.py for why) - being added as a case
member is itself the authorization decision, and shouldn't be silently
overridden by a role that happens to grant nothing else. CASE_CREATE/
CASE_EDIT/CASE_DELETE remain permission-gated on top of that row-level
check, since those are real management actions, not viewing."""

from __future__ import annotations

from quart import Blueprint, abort, g, redirect, render_template, request, url_for

from app.core.security.org_permissions import (
    get_user_org_membership,
    get_user_org_permission_names,
    is_org_owner,
    require_org_permission,
)
from app.core.security.permissions import get_visible_nav_keys
from app.core.security.sessions import login_required
from app.features.audit import service as audit_service
from app.features.cases.choices import CASE_STATUSES, CLASSIFICATIONS, FORENSIC_STATUSES, SEVERITIES
from app.features.cases.permissions import CASE_CREATE, CASE_DELETE, CASE_EDIT
from app.features.cases.service import (
    CaseError,
    add_member,
    create_case,
    delete_case,
    get_case_for_user,
    get_case_members,
    list_cases_for_user,
    remove_member,
    search_addable_members,
    update_case,
)
from app.features.auth.repository import get_user_by_id
from app.features.evidence.service import list_case_evidence
from app.features.organizations import repository as org_repository
from app.features.plans.service import get_active_subscription, get_highest_allowed_tier


cases_bp = Blueprint("cases", __name__, url_prefix="/cases")


def _ip() -> str | None:
    return request.remote_addr


async def _require_org_id() -> str:
    """Resolves which org the caller belongs to, 404ing if they belong to
    none - every route below needs this to scope queries by
    organization_id, regardless of which (if any) CASE_* permission they
    hold."""
    membership = await get_user_org_membership(g.user_id)
    if not membership:
        abort(404)
    return membership["organization_id"]


async def _is_owner() -> bool:
    membership = await get_user_org_membership(g.user_id)
    return bool(membership and is_org_owner(g.user_id, membership))


async def _require_visible_case(case_id: str):
    """The case row if the current user may access it, else a 404 - never a
    403, so a non-member can't confirm a case id exists just by guessing."""
    case = await get_case_for_user(case_id, g.user_id, is_owner=await _is_owner())
    if not case:
        abort(404)
    return case


@cases_bp.route("/")
@login_required
async def list_view():
    org_id = await _require_org_id()
    is_owner = await _is_owner()
    recent_cases = await list_cases_for_user(org_id, g.user_id, is_owner=is_owner, limit=6)
    all_cases = await list_cases_for_user(org_id, g.user_id, is_owner=is_owner)
    org_members = [m for m in await org_repository.list_members(org_id) if m["id"] != g.user_id]
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "cases/list.html",
        recent_cases=recent_cases,
        all_cases=all_cases,
        classifications=CLASSIFICATIONS,
        severities=SEVERITIES,
        forensic_statuses=FORENSIC_STATUSES,
        org_members=org_members,
        visible_keys=visible_keys,
        error=request.args.get("error"),
    )


@cases_bp.route("/create", methods=["POST"])
@require_org_permission(CASE_CREATE)
async def create_view():
    org_id = await _require_org_id()
    form = await request.form
    try:
        case_id = await create_case(
            organization_id=org_id,
            title=form.get("title", ""),
            description=form.get("description", ""),
            classification=form.get("classification", ""),
            severity=form.get("severity", ""),
            forensic_status=form.get("forensic_status", ""),
            created_by=g.user_id,
            member_ids=form.getlist("member_ids"),
        )
    except CaseError as exc:
        return redirect(url_for("cases.list_view", error=str(exc)))
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.CASE_CREATED,
        target_label=form.get("title", ""),
        ip_address=_ip(),
    )
    # ?created=1 tells the case detail page to open the evidence-upload
    # dialog immediately - the create-case dialog's "step 2" in spirit, just
    # backed by a real page load instead of client-only dialog chaining, so
    # evidence upload always has a real, persisted case_id behind it.
    return redirect(url_for("cases.detail_view", case_id=case_id, created="1"))


async def _member_rows(case: dict, members: list, creator: dict | None, organization_id: str) -> list[dict]:
    """Members-tab rows: the creator (who never needs a case_members row to
    have access - see can_access_case) plus everyone explicitly added,
    each annotated with their *organization* role (there's no separate
    case-level role system - see cases/permissions.py) for the Role column."""
    role_by_user_id = {
        m["id"]: m["role_name"] for m in await org_repository.list_members(organization_id) if m.get("role_name")
    }
    rows = []
    if creator:
        rows.append(
            {
                "id": creator["id"],
                "name": creator["name"],
                "email": creator["email"],
                "role_label": "Case Creator",
                "last_activity": case["created_at"],
                "is_creator": True,
            }
        )
    for member in members:
        rows.append(
            {
                "id": member["id"],
                "name": member["name"],
                "email": member["email"],
                "role_label": role_by_user_id.get(member["id"], "Member"),
                "last_activity": member["added_at"],
                "is_creator": False,
            }
        )
    return rows


@cases_bp.route("/<case_id>")
@login_required
async def detail_view(case_id: str):
    case = await _require_visible_case(case_id)
    org_id = await _require_org_id()
    members = await get_case_members(case_id)
    evidence = await list_case_evidence(case_id)
    completed_evidence = [e for e in evidence if e["status"] == "completed"]
    # Lightweight, JSON-safe subset for the Analyze tab's Alpine state - the
    # full evidence rows carry datetime columns (uploaded_at) that don't
    # belong baked into the page as JSON just to back a client-side planner.
    analyze_evidence = [
        {
            "id": e["id"],
            "filename": e["filename"],
            "mime_type": e["mime_type"],
            "size_bytes": e["size_bytes"],
            "sha256": e["sha256"],
        }
        for e in completed_evidence
    ]
    creator = await get_user_by_id(case["created_by"])
    creator_name = creator["name"] if creator else "—"
    current_user = await get_user_by_id(g.user_id)
    current_user_name = current_user["name"] if current_user else "Analyst"
    visible_keys = await get_visible_nav_keys(g.user_id)
    is_owner = await _is_owner()
    granted_permissions = await get_user_org_permission_names(g.user_id)
    can_edit = is_owner or CASE_EDIT.name in granted_permissions
    can_delete = is_owner or CASE_DELETE.name in granted_permissions
    return await render_template(
        "cases/detail.html",
        case=case,
        creator_name=creator_name,
        current_user_name=current_user_name,
        members=members,
        member_rows=await _member_rows(case, members, creator, org_id),
        evidence=evidence,
        analyze_evidence=analyze_evidence,
        user_plan=get_highest_allowed_tier(await get_active_subscription(org_id)),
        activity_log=await audit_service.get_case_activity_log(case_id),
        classification_label=dict(CLASSIFICATIONS).get(case["classification"], case["classification"] or "—"),
        severity_label=dict(SEVERITIES).get(case["severity"], case["severity"]),
        forensic_status_label=dict(FORENSIC_STATUSES).get(case["forensic_status"], case["forensic_status"]),
        case_status_label=dict(CASE_STATUSES).get(case["status"], case["status"]),
        classifications=CLASSIFICATIONS,
        severities=SEVERITIES,
        forensic_statuses=FORENSIC_STATUSES,
        case_statuses=CASE_STATUSES,
        visible_keys=visible_keys,
        is_owner=is_owner,
        can_edit=can_edit,
        can_delete=can_delete,
        just_created=request.args.get("created") == "1",
        error=request.args.get("error"),
    )


@cases_bp.route("/<case_id>/edit", methods=["POST"])
@require_org_permission(CASE_EDIT)
async def update_view(case_id: str):
    await _require_visible_case(case_id)
    form = await request.form
    try:
        await update_case(
            case_id,
            title=form.get("title", ""),
            description=form.get("description", ""),
            classification=form.get("classification", ""),
            severity=form.get("severity", ""),
            forensic_status=form.get("forensic_status", ""),
            status=form.get("status", ""),
        )
    except CaseError as exc:
        await audit_service.record_case_activity(
            case_id=case_id,
            actor_id=g.user_id,
            action=audit_service.CASE_UPDATED,
            target_label=form.get("title", ""),
            status="failure",
            ip_address=_ip(),
            metadata={"error": str(exc)},
        )
        return redirect(url_for("cases.detail_view", case_id=case_id, error=str(exc)))
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.CASE_UPDATED,
        target_label=form.get("title", ""),
        ip_address=_ip(),
    )
    return redirect(url_for("cases.detail_view", case_id=case_id))


@cases_bp.route("/<case_id>/delete", methods=["POST"])
@require_org_permission(CASE_DELETE)
async def delete_view(case_id: str):
    case = await _require_visible_case(case_id)
    await delete_case(case_id)
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.CASE_DELETED,
        target_label=case["title"],
        ip_address=_ip(),
    )
    return redirect(url_for("cases.list_view"))


@cases_bp.route("/<case_id>/members/add", methods=["POST"])
@require_org_permission(CASE_EDIT)
async def add_member_view(case_id: str):
    await _require_visible_case(case_id)
    form = await request.form
    user_id = form.get("user_id", "")
    try:
        if user_id:
            await add_member(case_id, user_id, added_by=g.user_id)
            added_user = await get_user_by_id(user_id)
            await audit_service.record_case_activity(
                case_id=case_id,
                actor_id=g.user_id,
                action=audit_service.MEMBER_ADDED,
                target_label=added_user["name"] if added_user else user_id,
                ip_address=_ip(),
            )
    except CaseError as exc:
        return redirect(url_for("cases.detail_view", case_id=case_id, error=str(exc)))
    return redirect(url_for("cases.detail_view", case_id=case_id))


@cases_bp.route("/<case_id>/members/<user_id>/remove", methods=["POST"])
@require_org_permission(CASE_EDIT)
async def remove_member_view(case_id: str, user_id: str):
    await _require_visible_case(case_id)
    target_user = await get_user_by_id(user_id)
    target_label = target_user["name"] if target_user else user_id
    try:
        await remove_member(case_id, user_id, requested_by=g.user_id, is_owner=await _is_owner())
    except CaseError as exc:
        await audit_service.record_case_activity(
            case_id=case_id,
            actor_id=g.user_id,
            action=audit_service.MEMBER_REMOVED,
            target_label=target_label,
            status="failure",
            ip_address=_ip(),
            metadata={"error": str(exc)},
        )
        return redirect(url_for("cases.detail_view", case_id=case_id, error=str(exc)))
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=g.user_id,
        action=audit_service.MEMBER_REMOVED,
        target_label=target_label,
        ip_address=_ip(),
    )
    return redirect(url_for("cases.detail_view", case_id=case_id))


@cases_bp.route("/<case_id>/members/search")
@require_org_permission(CASE_EDIT)
async def search_members_view(case_id: str):
    await _require_visible_case(case_id)
    org_id = await _require_org_id()
    search = request.args.get("q", "").strip()
    users = await search_addable_members(org_id, case_id, search)
    return await render_template("cases/_member_options.html", users=users, case_id=case_id)
