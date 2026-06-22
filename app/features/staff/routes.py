"""Admin Staff routes."""

from __future__ import annotations

from quart import Blueprint, g, redirect, render_template, request, url_for

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.staff import service
from app.features.staff.permissions import STAFF_CREATE, STAFF_EDIT, STAFF_VIEW
from app.features.staff.service import StaffError

staff_bp = Blueprint("staff", __name__, url_prefix="/admin/staff")


@staff_bp.route("/")
@require_permission(STAFF_VIEW)
async def list_view():
    search = request.args.get("q", "").strip()
    member_param = request.args.get("member", "")

    staff = await service.get_staff_list(search=search)
    roles = await service.get_all_roles()
    visible_keys = await get_visible_nav_keys(g.user_id)

    selected_member = None
    is_new = False
    error = request.args.get("error")

    if member_param == "new":
        is_new = True
        selected_member = {
            "id": None,
            "name": "",
            "email": "",
            "isActive": True,
            "roles": [],
            "role_ids": set(),
        }
    elif member_param:
        selected_member = await service.get_staff_member(member_param)

    return await render_template(
        "admin/staff/list.html",
        staff=staff,
        selected_member=selected_member,
        is_new=is_new,
        roles=roles,
        search=search,
        visible_keys=visible_keys,
        error=error,
    )


@staff_bp.route("/create", methods=["POST"])
@require_permission(STAFF_CREATE)
async def create_view():
    form = await request.form
    roles = await service.get_all_roles()
    role_ids = [r["id"] for r in roles if form.get(f"role_{r['id']}") == "1"]
    try:
        member_id = await service.create_staff(
            name=form.get("name", ""),
            email=form.get("email", ""),
            role_ids=role_ids,
            created_by=g.user_id,
        )
    except StaffError as exc:
        return redirect(url_for("staff.list_view", member="new", error=str(exc)))
    return redirect(url_for("staff.list_view", member=member_id))


@staff_bp.route("/<member_id>/save", methods=["POST"])
@require_permission(STAFF_EDIT)
async def save_view(member_id: str):
    form = await request.form
    roles = await service.get_all_roles()
    role_ids = [r["id"] for r in roles if form.get(f"role_{r['id']}") == "1"]
    try:
        await service.save_staff(
            member_id,
            name=form.get("name", ""),
            role_ids=role_ids,
            saved_by=g.user_id,
        )
    except StaffError as exc:
        return redirect(url_for("staff.list_view", member=member_id, error=str(exc)))
    return redirect(url_for("staff.list_view", member=member_id))
