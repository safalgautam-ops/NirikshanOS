"""authorization helper module that decides which sidebar navigation items a user is allowed to see, based on the roles assigned to them."""

from __future__ import annotations

from functools import wraps

from flask import abort, g, url_for

from app.core.db.orm import db
from app.core.security.htmx import redirect_or_htmx
from app.core.security.permission_registry import Permission

NAV_KEYS: list[tuple[str, str]] = [
    ("admin_users", "Users"),
    ("admin_organizations", "Organizations"),
    ("admin_roles", "Roles"),
    ("admin_staff", "Staff"),
    ("admin_modules", "Modules"),
    ("admin_instances", "Instances"),
    ("admin_categories", "Categories"),
    ("admin_plans", "Plans"),
    ("admin_transactions", "Transactions"),
    ("admin_coupons", "Coupons"),
    ("admin_discounts", "Discounts"),
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
    """Which Administration nav keys this user may see, or None for "no restriction"."""
    roles = await get_user_roles(user_id)

    # Zero roles held falls through to an empty set, not None - a user with no system role sees nothing.
    allowed: set[str] = set()
    for role in roles:
        keys = role["sidebar_keys"]
        if keys is None:
            return None
        allowed.update(keys)

    return list(allowed)


async def user_has_any_role(user_id: str) -> bool:
    """Whether this user holds at least one system role - the same definition of "staff" already used by the admin Staff page (see staff/repository.py's list_staff docstring)."""
    row = await db.table("user_roles").where("user_id", user_id).first()
    return row is not None


async def get_user_permission_names(user_id: str) -> set[str]:
    """Every permission ('resource.action') granted via any role this user holds."""
    rows = await (
        db.table("user_roles")
        .join("role_permissions", "user_roles.role_id", "role_permissions.role_id")
        .join("permissions", "role_permissions.permission_id", "permissions.id")
        .where("user_roles.user_id", user_id)
        .select("permissions.name")
        .all(allow_full_table=True)
    )
    return {row["name"] for row in rows}


def require_permission(*permissions: Permission):
    """Route decorator: redirects to login if nobody's signed in, aborts 403 if the signed-in user is missing any of the given permissions."""

    def decorator(view):
        @wraps(view)
        async def wrapped(*args, **kwargs):
            if g.user_id is None:
                return redirect_or_htmx(url_for("auth.login"))
            granted = await get_user_permission_names(g.user_id)
            required = {permission.name for permission in permissions}
            if not required.issubset(granted):
                abort(403)
            return await view(*args, **kwargs)

        return wrapped

    return decorator
