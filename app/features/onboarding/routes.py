"""Onboarding routes: a single "Organization" page that shows the 3-step
create/join wizard if the user has no org yet, or the org's profile/invite
info if they do - see app/templates/onboarding/{index,invite}.html."""

from __future__ import annotations

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from app.core.security.org_permissions import (
    ORG_NAV_KEYS,
    get_user_org_membership,
    get_user_org_permission_names,
    is_org_owner,
    require_any_org_permission,
    require_org_permission,
)
from app.core.security.permissions import get_visible_nav_keys, user_has_any_role
from app.core.security.sessions import login_required
from app.features.onboarding.permissions import (
    ORG_DOCUMENT_VIEW,
    ORG_ROLE_CREATE,
    ORG_ROLE_DELETE,
    ORG_ROLE_EDIT,
    ORG_ROLE_VIEW,
    ORG_SETTINGS_MANAGE,
    ORG_STAFF_REMOVE,
    ORG_STAFF_VIEW,
)
from app.features.organizations import repository as org_repository
from app.features.organizations.choices import EMPLOYEE_COUNT_RANGES, ORG_TYPES
from app.features.organizations.countries import COUNTRIES
from app.features.onboarding.service import (
    OnboardingError,
    add_documents,
    assign_role_member,
    create_and_join,
    create_org_role,
    delete_document,
    delete_organization,
    delete_org_role,
    duplicate_org_role,
    get_document_for_download,
    get_org_permissions_grouped,
    get_org_roles_page,
    get_user_organization,
    join_by_code,
    leave_organization,
    list_documents,
    list_staff,
    regenerate_invite_code,
    remove_role_member,
    remove_staff,
    toggle_org_role_assignable,
    transfer_ownership,
    update_org_role_display,
    update_org_role_permissions,
    update_org_role_sidebar,
)

onboarding_bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")


@onboarding_bp.before_request
async def _block_platform_staff() -> None:
    """Organization create/join/staff/role self-service is for regular,
    tenant-side users only. Platform staff (anyone holding a system role -
    see permissions.py) already manage every organization from
    /admin/organizations; they must never become a tenant member through
    their own platform identity, so this entire blueprint doesn't exist for
    them. Checked by role membership, not by granted permissions - a staff
    role with zero permissions assigned is still staff."""
    if g.user_id is not None and await user_has_any_role(g.user_id):
        return redirect(url_for("dashboard"))


async def _require_org_id() -> str:
    """Every org-scoped route below is already gated by require_org_permission
    (so the caller is necessarily a member of some org) - this just resolves
    which one, for queries that need to scope by organization_id."""
    org = await get_user_organization(g.user_id)
    if not org:
        abort(404)
    return org["id"]


@onboarding_bp.route("/")
@login_required
async def index():
    org = await get_user_organization(g.user_id)
    if org:
        visible_keys = await get_visible_nav_keys(g.user_id)
        org_type_labels = dict(ORG_TYPES)
        membership = await get_user_org_membership(g.user_id)
        owner = bool(membership and is_org_owner(g.user_id, membership))
        granted = await get_user_org_permission_names(g.user_id)
        can_manage_org = ORG_SETTINGS_MANAGE.name in granted
        # A role with only the narrower "view documents" grant should still
        # see the documents list (just not the upload/delete controls or
        # the invite code/link, which stay behind can_manage_org).
        can_view_documents = can_manage_org or ORG_DOCUMENT_VIEW.name in granted
        documents = await list_documents(org["id"]) if can_view_documents else []
        other_members = [m for m in await list_staff(org["id"]) if m["id"] != g.user_id]
        member_options = [(m["id"], m["name"]) for m in other_members]
        if org["verification_status"] != "approved":
            return render_template(
                "onboarding/pending.html",
                org=org,
                documents=documents,
                org_type_label=org_type_labels.get(org["org_type"], org["org_type"]),
                visible_keys=visible_keys,
                can_manage_org=can_manage_org,
                can_view_documents=can_view_documents,
                is_owner=owner,
                other_members=other_members,
                error=request.args.get("error"),
            )
        return render_template(
            "onboarding/invite.html",
            org=org,
            documents=documents,
            org_type_label=org_type_labels.get(org["org_type"], org["org_type"]),
            visible_keys=visible_keys,
            can_manage_org=can_manage_org,
            can_view_documents=can_view_documents,
            is_owner=owner,
            other_members=other_members,
            member_options=member_options,
            error=request.args.get("error"),
        )

    return render_template(
        "onboarding/index.html",
        error=request.args.get("error"),
        code=request.args.get("code", ""),
        org_types=ORG_TYPES,
        employee_count_ranges=EMPLOYEE_COUNT_RANGES,
        countries=COUNTRIES,
    )


@onboarding_bp.route("/create", methods=["POST"])
@login_required
async def create_view():
    form = request.form
    files = request.files
    try:
        await create_and_join(
            created_by=g.user_id,
            name=form.get("name", ""),
            description=form.get("description", ""),
            org_type=form.get("org_type", ""),
            employee_count=form.get("employee_count", ""),
            address=form.get("address", ""),
            country=form.get("country", ""),
            state=form.get("state", ""),
            city=form.get("city", ""),
            postal_code=form.get("postal_code", ""),
            registration_number=form.get("registration_number", ""),
            pan_number=form.get("pan_number", ""),
            owner_name=form.get("owner_name", ""),
            logo=files.get("logo"),
            documents=files.getlist("documents"),
        )
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("onboarding.index"))


@onboarding_bp.route("/join", methods=["GET", "POST"])
@login_required
async def join_view():
    if request.method == "GET":
        # The actual invite *link* lands here - if they're already a member,
        # send them to the org page (now showing profile/invite info)
        # instead of re-running the join flow.
        org = await get_user_organization(g.user_id)
        if org:
            return redirect(url_for("onboarding.index"))
        return redirect(url_for("onboarding.index", code=request.args.get("code", "")))

    form = request.form
    try:
        await join_by_code(code=form.get("code", ""), user_id=g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc), code=form.get("code", "")))
    return redirect(url_for("onboarding.index"))


@onboarding_bp.route("/invite/regenerate", methods=["POST"])
@require_org_permission(ORG_SETTINGS_MANAGE)
async def regenerate_invite_view():
    try:
        await regenerate_invite_code(g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("onboarding.index"))


@onboarding_bp.route("/documents/<doc_id>")
@require_any_org_permission(ORG_SETTINGS_MANAGE, ORG_DOCUMENT_VIEW)
async def download_document_view(doc_id: str):
    result = await get_document_for_download(doc_id=doc_id, user_id=g.user_id)
    if not result:
        abort(404)
    url, _original_filename = result
    return redirect(url)


@onboarding_bp.route("/documents", methods=["POST"])
@require_org_permission(ORG_SETTINGS_MANAGE)
async def upload_document_view():
    org_id = await _require_org_id()
    files = request.files
    try:
        await add_documents(org_id, files.getlist("documents"))
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("onboarding.index"))


@onboarding_bp.route("/documents/<doc_id>/delete", methods=["POST"])
@require_org_permission(ORG_SETTINGS_MANAGE)
async def delete_document_view(doc_id: str):
    org_id = await _require_org_id()
    try:
        await delete_document(org_id, doc_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("onboarding.index"))


@onboarding_bp.route("/delete", methods=["POST"])
@login_required
async def delete_organization_view():
    org_id = await _require_org_id()
    try:
        await delete_organization(org_id, requested_by=g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("dashboard"))


@onboarding_bp.route("/leave", methods=["POST"])
@login_required
async def leave_view():
    org_id = await _require_org_id()
    try:
        await leave_organization(org_id, g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("dashboard"))


@onboarding_bp.route("/transfer-ownership", methods=["POST"])
@login_required
async def transfer_ownership_view():
    org_id = await _require_org_id()
    form = request.form
    try:
        await transfer_ownership(
            org_id, current_owner_id=g.user_id, new_owner_id=form.get("new_owner_id", "")
        )
    except OnboardingError as exc:
        return redirect(url_for("onboarding.index", error=str(exc)))
    return redirect(url_for("onboarding.index"))


# ── org staff (this org's own member list) ──────────────────────────────────


@onboarding_bp.route("/staff")
@require_org_permission(ORG_STAFF_VIEW)
async def staff_list_view():
    org_id = await _require_org_id()
    members = await list_staff(org_id)
    org = await org_repository.get_organization(org_id)
    visible_keys = await get_visible_nav_keys(g.user_id)
    return render_template(
        "onboarding/staff/list.html",
        members=members,
        owner_id=org["created_by"] if org else None,
        visible_keys=visible_keys,
        error=request.args.get("error"),
    )


@onboarding_bp.route("/staff/<user_id>/remove", methods=["POST"])
@require_org_permission(ORG_STAFF_REMOVE)
async def staff_remove_view(user_id: str):
    org_id = await _require_org_id()
    try:
        await remove_staff(org_id, user_id, removed_by=g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.staff_list_view", error=str(exc)))
    return redirect(url_for("onboarding.staff_list_view"))


# ── org roles & permissions ──────────────────────────────────────────────────


@onboarding_bp.route("/roles")
@require_org_permission(ORG_ROLE_VIEW)
async def org_roles_list_view():
    org_id = await _require_org_id()
    roles = await get_org_roles_page(org_id)
    visible_keys = await get_visible_nav_keys(g.user_id)
    membership = await get_user_org_membership(g.user_id)
    is_owner = bool(membership and is_org_owner(g.user_id, membership))
    return render_template(
        "onboarding/roles/list.html",
        roles=roles,
        visible_keys=visible_keys,
        is_owner=is_owner,
        error=request.args.get("error"),
    )


@onboarding_bp.route("/roles", methods=["POST"])
@require_org_permission(ORG_ROLE_CREATE)
async def org_roles_create_view():
    org_id = await _require_org_id()
    role_id = await create_org_role(org_id, "New role")
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id))


@onboarding_bp.route("/roles/<role_id>")
@require_org_permission(ORG_ROLE_VIEW)
async def org_roles_edit_view(role_id: str):
    org_id = await _require_org_id()
    role = await org_repository.get_org_role(role_id)
    if not role or role["organization_id"] != org_id:
        return redirect(url_for("onboarding.org_roles_list_view"))

    all_roles = await org_repository.list_org_roles(org_id)
    permission_groups = await get_org_permissions_grouped()
    checked_permission_ids = await org_repository.get_org_role_permission_ids(role_id)
    members = await org_repository.get_org_role_members(role_id)
    visible_keys = await get_visible_nav_keys(g.user_id)

    checked_nav_keys = (
        {key for key, _ in ORG_NAV_KEYS} if role["sidebar_keys"] is None else set(role["sidebar_keys"])
    )
    membership = await get_user_org_membership(g.user_id)
    is_owner = bool(membership and is_org_owner(g.user_id, membership))

    return render_template(
        "onboarding/roles/edit.html",
        role=role,
        all_roles=all_roles,
        permission_groups=permission_groups,
        checked_permission_ids=checked_permission_ids,
        members=members,
        nav_keys=ORG_NAV_KEYS,
        checked_nav_keys=checked_nav_keys,
        visible_keys=visible_keys,
        is_owner=is_owner,
        error=request.args.get("error"),
        active_tab=request.args.get("tab", "display"),
    )


@onboarding_bp.route("/roles/<role_id>/display", methods=["POST"])
@require_org_permission(ORG_ROLE_EDIT)
async def org_roles_update_display(role_id: str):
    form = request.form
    try:
        await update_org_role_display(
            role_id,
            name=form.get("name", ""),
            description=form.get("description", ""),
            color=form.get("color", "#5865F2"),
        )
    except OnboardingError as exc:
        return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id, error=str(exc)))
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id))


@onboarding_bp.route("/roles/<role_id>/permissions", methods=["POST"])
@require_org_permission(ORG_ROLE_EDIT)
async def org_roles_update_permissions(role_id: str):
    form = request.form
    await update_org_role_permissions(role_id, form.getlist("permission_ids"))
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id, tab="permissions"))


@onboarding_bp.route("/roles/<role_id>/sidebar", methods=["POST"])
@require_org_permission(ORG_ROLE_EDIT)
async def org_roles_update_sidebar(role_id: str):
    form = request.form
    await update_org_role_sidebar(role_id, form.getlist("nav_keys"))
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id, tab="sidebar"))


@onboarding_bp.route("/roles/<role_id>/members/add", methods=["POST"])
@require_org_permission(ORG_ROLE_EDIT)
async def org_roles_add_member(role_id: str):
    org_id = await _require_org_id()
    form = request.form
    user_id = form.get("user_id", "")
    try:
        if user_id:
            await assign_role_member(org_id, role_id, user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id, tab="members", error=str(exc)))
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id, tab="members"))


@onboarding_bp.route("/roles/<role_id>/members/<user_id>/remove", methods=["POST"])
@require_org_permission(ORG_ROLE_EDIT)
async def org_roles_remove_member(role_id: str, user_id: str):
    org_id = await _require_org_id()
    await remove_role_member(org_id, user_id)
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=role_id, tab="members"))


@onboarding_bp.route("/roles/<role_id>/duplicate", methods=["POST"])
@require_org_permission(ORG_ROLE_CREATE)
async def org_roles_duplicate_view(role_id: str):
    new_role_id = await duplicate_org_role(role_id)
    return redirect(url_for("onboarding.org_roles_edit_view", role_id=new_role_id))


@onboarding_bp.route("/roles/<role_id>/toggle-assignable", methods=["POST"])
@require_org_permission(ORG_ROLE_EDIT)
async def org_roles_toggle_assignable_view(role_id: str):
    try:
        await toggle_org_role_assignable(role_id, requested_by=g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.org_roles_list_view", error=str(exc)))
    return redirect(url_for("onboarding.org_roles_list_view"))


@onboarding_bp.route("/roles/<role_id>/delete", methods=["POST"])
@require_org_permission(ORG_ROLE_DELETE)
async def org_roles_delete_view(role_id: str):
    org_id = await _require_org_id()
    try:
        await delete_org_role(org_id, role_id, requested_by=g.user_id)
    except OnboardingError as exc:
        return redirect(url_for("onboarding.org_roles_list_view", error=str(exc)))
    return redirect(url_for("onboarding.org_roles_list_view"))


@onboarding_bp.route("/roles/<role_id>/members/search")
@require_org_permission(ORG_ROLE_VIEW)
async def org_roles_search_members(role_id: str):
    org_id = await _require_org_id()
    search = request.args.get("q", "").strip()
    users = await org_repository.search_org_assignable_users(org_id, role_id, search)
    return render_template(
        "onboarding/roles/_member_options.html", users=users, role_id=role_id
    )
