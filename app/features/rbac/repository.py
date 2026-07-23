"""DB access for the admin RBAC (roles & permissions) pages."""

from __future__ import annotations

import json

from app.core.db.orm import Page, db
from app.core.utils.ids import new_id


async def list_roles(*, search: str = "", page: int = 1, per_page: int = 20) -> Page:
    query = db.table("roles")
    if search:
        query = query.search(["name", "description"], search)
    return await query.order_by("priority", "DESC").paginate(page=page, per_page=per_page)


async def get_all_roles_ordered() -> list:
    return await db.table("roles").order_by("priority", "DESC").all(allow_full_table=True)


async def get_member_counts(role_ids: list[str]) -> dict[str, int]:
    if not role_ids:
        return {}
    rows = await (
        db.table("user_roles").where_in("role_id", role_ids).select("role_id").all(allow_full_table=True)
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["role_id"]] = counts.get(row["role_id"], 0) + 1
    return counts


async def get_role(role_id: str):
    return await db.table("roles").where("id", role_id).first()


async def get_unique_role_name(base: str) -> str:
    """`roles.name` is UNIQUE - find the first free '{base}', '{base} 2', '{base} 3', ... ."""
    existing = {r["name"] for r in await get_all_roles_ordered()}
    if base not in existing:
        return base
    suffix = 2
    while f"{base} {suffix}" in existing:
        suffix += 1
    return f"{base} {suffix}"


async def create_role(*, name: str, description: str = "", color: str = "#5865F2") -> str:
    role_id = new_id()
    name = await get_unique_role_name(name)
    await db.table("roles").create(
        {
            "id": role_id,
            "name": name,
            "description": description or None,
            "color": color,
            "priority": 0,
            "is_system": False,
            "is_default": False,
            "is_assignable": True,
        }
    )
    return role_id


async def update_role_display(role_id: str, *, name: str, description: str, color: str) -> None:
    await (
        db.table("roles")
        .where("id", role_id)
        .patch({"name": name, "description": description or None, "color": color})
    )


async def set_assignable(role_id: str, is_assignable: bool) -> None:
    await db.table("roles").where("id", role_id).patch({"is_assignable": is_assignable})


async def set_sidebar_keys(role_id: str, keys: list[str] | None) -> None:
    value = json.dumps(keys) if keys is not None else None
    await db.table("roles").where("id", role_id).patch({"sidebar_keys": value})


async def delete_role(role_id: str) -> None:
    await db.table("roles").where("id", role_id).delete()


"""
 copying a role means:
    create a new role with the same name and description as the original
    copy the sidebar keys from the original role to the new role and all of its permissions
    return the ID of the new role
"""


async def duplicate_role(role_id: str) -> str:
    original = await get_role(role_id)
    new_role_id = new_id()
    name = await get_unique_role_name(f"{original['name']} (copy)")
    async with db.transaction():
        await db.table("roles").create(
            {
                "id": new_role_id,
                "name": name,
                "description": original["description"],
                "color": original["color"],
                "priority": 0,
                "is_system": False,
                "is_default": False,
                "is_assignable": True,
                "sidebar_keys": (
                    json.dumps(original["sidebar_keys"]) if original["sidebar_keys"] is not None else None
                ),
            }
        )
        permission_ids = await get_role_permission_ids(role_id)
        for permission_id in permission_ids:
            await db.table("role_permissions").create(
                {"role_id": new_role_id, "permission_id": permission_id}
            )
    return new_role_id


async def get_all_permissions() -> list:
    return await db.table("permissions").order_by("category").order_by("name").all(allow_full_table=True)


async def get_role_permission_ids(role_id: str) -> set[str]:
    rows = await (
        db.table("role_permissions")
        .where("role_id", role_id)
        .select("permission_id")
        .all(allow_full_table=True)
    )
    return {row["permission_id"] for row in rows}


async def set_role_permissions(role_id: str, permission_ids: list[str]) -> None:
    async with db.transaction():
        await db.table("role_permissions").where("role_id", role_id).delete()
        for permission_id in permission_ids:
            await db.table("role_permissions").create({"role_id": role_id, "permission_id": permission_id})


async def get_role_members(role_id: str) -> list:
    return await (
        db.table("user_roles")
        .join("user", "user_roles.user_id", "user.id")
        .where("user_roles.role_id", role_id)
        .select("user.id", "user.name", "user.email")
        .order_by("user.name")
        .all(allow_full_table=True)
    )


async def search_assignable_users(role_id: str, search: str) -> list:
    """Users NOT already holding this role, for the 'add member' picker."""
    existing = await (
        db.table("user_roles").where("role_id", role_id).select("user_id").all(allow_full_table=True)
    )
    existing_ids = [row["user_id"] for row in existing]

    query = db.table("user")
    if existing_ids:
        query = query.where_not_in("id", existing_ids)
    if search:
        query = query.search(["name", "email"], search)

    return await query.select("id", "name", "email").order_by("name").limit(20).all()


async def add_member(role_id: str, user_id: str, assigned_by: str) -> None:
    await db.table("user_roles").create({"user_id": user_id, "role_id": role_id, "assigned_by": assigned_by})


async def remove_member(role_id: str, user_id: str) -> None:
    await db.table("user_roles").where("role_id", role_id).where("user_id", user_id).delete()
