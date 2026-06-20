"""RBAC read helpers used outside the rbac feature itself.

Full role/permission CRUD lives in app/features/rbac. This module only
answers the question every page needs on every request: "what can this
user see?" — kept here (next to sessions.py) so routes don't have to
import the whole rbac feature just to filter a sidebar.
"""

from __future__ import annotations

from app.core.db.orm import db

# Every dashboard nav key that can be hidden per-role. Kept here as the
# single source of truth; sidebar.html and the RBAC "Sidebar" tab both
# render from this list so a renamed/added page can't drift out of sync.
NAV_KEYS: list[tuple[str, str]] = [
    ("dashboard", "Dashboard"),
    ("cases", "Cases"),
    ("evidence", "Evidence"),
    ("analysis", "Analysis"),
    ("notes", "Notes"),
    ("reports", "Reports"),
    ("audit", "Audit Log"),
    ("admin_users", "Users"),
    ("admin_organizations", "Organizations"),
    ("admin_roles", "Roles"),
    ("admin_staff", "Staff"),
]


async def get_user_roles(user_id: str) -> list:
    """All roles held by a user, highest priority first."""
    return await (
        db.table("user_roles")
        .join("roles", "user_roles.role_id", "roles.id")
        .where("user_roles.user_id", user_id)
        .select(
            "roles.id",
            "roles.name",
            "roles.color",
            "roles.priority",
            "roles.sidebar_keys",
        )
        .order_by("roles.priority", "DESC")
        .all(allow_full_table=True)
    )


async def get_visible_nav_keys(user_id: str) -> list[str] | None:
    """
    Which sidebar nav keys this user may see, or None for "no restriction".

    A role with sidebar_keys = NULL grants access to everything (NULL and
    "explicitly checked every box" are treated the same by the editor — see
    rbac/service.py). An empty list [] is different: it means "explicitly
    restricted to nothing", not "unrestricted" — so this checks `is None`,
    never falsiness, to keep the two cases apart.

    If ANY of the user's roles is unrestricted, the user is unrestricted —
    restrictions only narrow things down when every held role has one.
    """
    roles = await get_user_roles(user_id)
    if not roles:
        return None

    allowed: set[str] = set()
    for role in roles:
        keys = role["sidebar_keys"]
        if keys is None:
            return None  # this role grants full access — nothing to restrict
        allowed.update(keys)

    return list(allowed)
