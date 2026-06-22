"""DB access for the admin Staff page.
Staff = users who have at least one role assigned (user_roles junction table).
"""

from __future__ import annotations

from app.core.db.orm import db


async def list_staff(*, search: str = "") -> list:
    """All users who have at least one role assigned, with their roles."""
    # Get user IDs who have at least one role
    role_rows = await (
        db.table("user_roles").select("user_id").all(allow_full_table=True)
    )
    staff_ids = list({row["user_id"] for row in role_rows})
    if not staff_ids:
        return []

    query = db.table("user").where_in("id", staff_ids)
    if search:
        query = query.search(["name", "email"], search)
    users = await query.order_by("name").all(allow_full_table=True)

    # Attach roles to each user
    role_assignments = await (
        db.table("user_roles")
        .join("roles", "user_roles.role_id", "roles.id")
        .where_in("user_roles.user_id", staff_ids)
        .select("user_roles.user_id", "roles.id", "roles.name", "roles.color")
        .all(allow_full_table=True)
    )
    roles_by_user: dict[str, list] = {}
    for row in role_assignments:
        roles_by_user.setdefault(row["user_id"], []).append(
            {"id": row["id"], "name": row["name"], "color": row["color"]}
        )

    for user in users:
        user["roles"] = roles_by_user.get(user["id"], [])
    return users


async def get_staff_member(user_id: str):
    """Get a single user with their role assignments."""
    user = await db.table("user").where("id", user_id).first()
    if not user:
        return None
    rows = await (
        db.table("user_roles")
        .join("roles", "user_roles.role_id", "roles.id")
        .where("user_roles.user_id", user_id)
        .select("roles.id", "roles.name", "roles.color")
        .all(allow_full_table=True)
    )
    user["roles"] = [
        {"id": r["id"], "name": r["name"], "color": r["color"]} for r in rows
    ]
    user["role_ids"] = {r["id"] for r in rows}
    return user


async def create_staff_user(*, name: str, email: str, password_hash: str) -> str:
    """Create the user + credential account atomically, so the new staff
    member can actually log in (admin-created, so it skips the
    email-ownership OTP self-registration normally requires)."""
    from app.features.auth.repository import create_user_with_password

    return await create_user_with_password(
        name=name,
        email=email,
        password_hash=password_hash,
        is_active=True,
        email_verified=True,
        must_change_password=True,
    )


async def update_staff_user(user_id: str, *, name: str) -> None:
    await db.table("user").where("id", user_id).patch({"name": name})


async def get_user_by_email(email: str):
    return await db.table("user").where("email", email).first()


async def replace_staff_roles(
    user_id: str, role_ids: list[str], assigned_by: str
) -> None:
    """Replace all role assignments for a staff member."""
    async with db.transaction():
        await db.table("user_roles").where("user_id", user_id).delete()
        for role_id in role_ids:
            await db.table("user_roles").create(
                {
                    "user_id": user_id,
                    "role_id": role_id,
                    "assigned_by": assigned_by,
                }
            )


async def get_all_roles() -> list:
    return (
        await db.table("roles").order_by("priority", "DESC").all(allow_full_table=True)
    )
