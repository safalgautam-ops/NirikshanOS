"""Admin Users routes — list/search/filter + status toggle + role assignment."""

from __future__ import annotations

from quart import Blueprint, g, redirect, render_template, request, url_for

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.users import repository
from app.features.users.permissions import USER_DELETE, USER_EDIT, USER_VIEW
from app.features.users.service import (
    UserError,
    delete_user,
    get_users_page,
    toggle_user_active,
    update_user_roles,
)

users_bp = Blueprint("users", __name__, url_prefix="/admin/users")


@users_bp.route("/")
@require_permission(USER_VIEW)
async def list_view():
    search = request.args.get("q", "").strip()
    role_id = request.args.get("role", "")
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    result = await get_users_page(
        search=search, role_id=role_id, status=status, page=page
    )
    roles = await repository.get_all_roles()
    visible_keys = await get_visible_nav_keys(g.user_id)

    return await render_template(
        "admin/users/list.html",
        page=result,
        roles=roles,
        search=search,
        role_id=role_id,
        status=status,
        visible_keys=visible_keys,
        error=request.args.get("error"),
    )


@users_bp.route("/<user_id>/status", methods=["POST"])
@require_permission(USER_EDIT)
async def update_status(user_id: str):
    form = await request.form
    await toggle_user_active(user_id, form.get("is_active") == "1")
    return redirect(url_for("users.list_view"))


@users_bp.route("/<user_id>/roles", methods=["POST"])
@require_permission(USER_EDIT)
async def update_roles(user_id: str):
    form = await request.form
    role_ids = form.getlist("role_ids")
    await update_user_roles(user_id, role_ids, assigned_by=g.user_id)
    return redirect(url_for("users.list_view"))


@users_bp.route("/<user_id>/update", methods=["POST"])
@require_permission(USER_EDIT)
async def update_view(user_id: str):
    form = await request.form
    if "status" in form:
        status = form.get("status")
        is_active = status == "active"
        await toggle_user_active(user_id, is_active)
    return redirect(url_for("users.list_view"))


@users_bp.route("/<user_id>/delete", methods=["POST"])
@require_permission(USER_DELETE)
async def delete_view(user_id: str):
    try:
        await delete_user(user_id, requested_by=g.user_id)
    except UserError as exc:
        return redirect(url_for("users.list_view", error=str(exc)))
    return redirect(url_for("users.list_view"))
