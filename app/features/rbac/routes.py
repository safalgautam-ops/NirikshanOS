"""Admin RBAC routes — roles list + the Display/Permissions/Sidebar/Members editor."""

from __future__ import annotations

from quart import Blueprint, g, redirect, render_template, request, url_for

from app.core.security.permissions import NAV_KEYS, get_visible_nav_keys, require_permission
from app.features.rbac import repository, service
from app.features.rbac.permissions import ROLE_CREATE, ROLE_DELETE, ROLE_EDIT, ROLE_VIEW
from app.features.rbac.service import RBACError

rbac_bp = Blueprint("rbac", __name__, url_prefix="/admin/roles")


@rbac_bp.route("/")
@require_permission(ROLE_VIEW)
async def list_view():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    result = await service.get_roles_page(search=search, page=page)
    visible_keys = await get_visible_nav_keys(g.user_id)

    return await render_template(
        "admin/rbac/list.html",
        page=result,
        search=search,
        visible_keys=visible_keys,
        error=request.args.get("error"),
    )


@rbac_bp.route("/", methods=["POST"])
@require_permission(ROLE_CREATE)
async def create_view():
    role_id = await service.create_role("New role")
    return redirect(url_for("rbac.edit_view", role_id=role_id))


@rbac_bp.route("/<role_id>")
@require_permission(ROLE_VIEW)
async def edit_view(role_id: str):
    role = await repository.get_role(role_id)
    if not role:
        return redirect(url_for("rbac.list_view"))

    all_roles = await repository.get_all_roles_ordered()
    permission_groups = await service.get_permissions_grouped()
    checked_permission_ids = await repository.get_role_permission_ids(role_id)
    members = await repository.get_role_members(role_id)
    visible_keys = await get_visible_nav_keys(g.user_id)

    checked_nav_keys = (
        {key for key, _ in NAV_KEYS} if role["sidebar_keys"] is None else set(role["sidebar_keys"])
    )

    return await render_template(
        "admin/rbac/edit.html",
        role=role,
        all_roles=all_roles,
        permission_groups=permission_groups,
        checked_permission_ids=checked_permission_ids,
        members=members,
        nav_keys=NAV_KEYS,
        checked_nav_keys=checked_nav_keys,
        visible_keys=visible_keys,
        error=request.args.get("error"),
        active_tab=request.args.get("tab", "display"),
    )


@rbac_bp.route("/<role_id>/display", methods=["POST"])
@require_permission(ROLE_EDIT)
async def update_display(role_id: str):
    form = await request.form
    try:
        await service.update_role_display(
            role_id,
            name=form.get("name", ""),
            description=form.get("description", ""),
            color=form.get("color", "#5865F2"),
        )
    except RBACError as exc:
        return redirect(url_for("rbac.edit_view", role_id=role_id, error=str(exc)))
    return redirect(url_for("rbac.edit_view", role_id=role_id))


@rbac_bp.route("/<role_id>/permissions", methods=["POST"])
@require_permission(ROLE_EDIT)
async def update_permissions(role_id: str):
    form = await request.form
    await service.update_role_permissions(role_id, form.getlist("permission_ids"))
    return redirect(url_for("rbac.edit_view", role_id=role_id, tab="permissions"))


@rbac_bp.route("/<role_id>/sidebar", methods=["POST"])
@require_permission(ROLE_EDIT)
async def update_sidebar(role_id: str):
    form = await request.form
    await service.update_role_sidebar(role_id, form.getlist("nav_keys"))
    return redirect(url_for("rbac.edit_view", role_id=role_id, tab="sidebar"))


@rbac_bp.route("/<role_id>/members/add", methods=["POST"])
@require_permission(ROLE_EDIT)
async def add_member(role_id: str):
    form = await request.form
    user_id = form.get("user_id", "")
    try:
        if user_id:
            await service.add_member(role_id, user_id, assigned_by=g.user_id)
    except RBACError as exc:
        return redirect(url_for("rbac.edit_view", role_id=role_id, tab="members", error=str(exc)))
    return redirect(url_for("rbac.edit_view", role_id=role_id, tab="members"))


@rbac_bp.route("/<role_id>/members/<user_id>/remove", methods=["POST"])
@require_permission(ROLE_EDIT)
async def remove_member(role_id: str, user_id: str):
    try:
        await service.remove_member(role_id, user_id, requested_by=g.user_id)
    except RBACError as exc:
        return redirect(url_for("rbac.edit_view", role_id=role_id, tab="members", error=str(exc)))
    return redirect(url_for("rbac.edit_view", role_id=role_id, tab="members"))


@rbac_bp.route("/<role_id>/duplicate", methods=["POST"])
@require_permission(ROLE_CREATE)
async def duplicate_view(role_id: str):
    new_role_id = await service.duplicate_role(role_id)
    return redirect(url_for("rbac.edit_view", role_id=new_role_id))


@rbac_bp.route("/<role_id>/toggle-assignable", methods=["POST"])
@require_permission(ROLE_EDIT)
async def toggle_assignable_view(role_id: str):
    try:
        await service.toggle_assignable(role_id)
    except RBACError as exc:
        return redirect(url_for("rbac.list_view", error=str(exc)))
    return redirect(url_for("rbac.list_view"))


@rbac_bp.route("/<role_id>/delete", methods=["POST"])
@require_permission(ROLE_DELETE)
async def delete_view(role_id: str):
    try:
        await service.delete_role(role_id)
    except RBACError as exc:
        return redirect(url_for("rbac.list_view", error=str(exc)))
    return redirect(url_for("rbac.list_view"))


@rbac_bp.route("/<role_id>/members/search")
@require_permission(ROLE_VIEW)
async def search_members(role_id: str):
    search = request.args.get("q", "").strip()
    users = await repository.search_assignable_users(role_id, search)
    return await render_template(
        "admin/rbac/_member_options.html", users=users, role_id=role_id
    )
