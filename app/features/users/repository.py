"""DB access for the admin Users page."""

from __future__ import annotations

from app.core.db.orm import Page, db


async def list_users(
    *,
    search: str = "",
    role_id: str = "",
    status: str = "",
    page: int = 1,
    per_page: int = 20,
) -> Page:
    query = db.table("user")

    if search:
        query = query.search(["name", "email"], search)
    if status == "active":
        query = query.where("isActive", True)
    elif status == "inactive":
        query = query.where("isActive", False)
    if role_id:
        member_ids = await db.table("user_roles").where("role_id", role_id).all(allow_full_table=True)
        query = query.where_in("id", [row["user_id"] for row in member_ids] or [""])

    return await query.order_by("createdAt", "DESC").paginate(page=page, per_page=per_page)


async def get_top_roles_for_users(user_ids: list[str]) -> dict[str, dict]:
    """Map user_id -> their highest-priority role (id/name/color), for the table's Role column."""
    if not user_ids:
        return {}

    rows = await (
        db.table("user_roles")
        .join("roles", "user_roles.role_id", "roles.id")
        .where_in("user_roles.user_id", user_ids)
        .select("user_roles.user_id", "roles.id", "roles.name", "roles.color")
        .order_by("roles.priority", "DESC")
        .all(allow_full_table=True)
    )

    top_role: dict[str, dict] = {}
    for row in rows:
        top_role.setdefault(row["user_id"], row)
    return top_role


async def get_all_roles() -> list:
    return await db.table("roles").order_by("priority", "DESC").all(allow_full_table=True)


async def get_role_ids_for_users(user_ids: list[str]) -> dict[str, set[str]]:
    """Map user_id -> set of role_ids they currently hold (for the 'Manage roles' dialog)."""
    if not user_ids:
        return {}

    rows = await (
        db.table("user_roles")
        .where_in("user_id", user_ids)
        .select("user_id", "role_id")
        .all(allow_full_table=True)
    )

    by_user: dict[str, set[str]] = {}
    for row in rows:
        by_user.setdefault(row["user_id"], set()).add(row["role_id"])
    return by_user


async def set_user_active(user_id: str, is_active: bool) -> None:
    await db.table("user").where("id", user_id).patch({"isActive": is_active})


async def delete_user(user_id: str) -> None:
    await db.table("user").where("id", user_id).delete()


async def replace_user_roles(user_id: str, role_ids: list[str], assigned_by: str) -> None:
    async with db.transaction():
        await db.table("user_roles").where("user_id", user_id).delete()
        for role_id in role_ids:
            await db.table("user_roles").create(
                {"user_id": user_id, "role_id": role_id, "assigned_by": assigned_by}
            )
