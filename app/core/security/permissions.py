"""
authorization helper module that decides which sidebar navigation items a user is allowed to see,
based on the roles assigned to them.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, g, url_for

from app.core.db.orm import db
from app.core.security.htmx import redirect_or_htmx
from app.core.security.permission_registry import Permission

# Platform-admin pages only - Dashboard and Organization are NOT here, they're
# baseline navigation every logged-in user always gets (see sidebar.html's
# Platform group), not something a system role can be configured to hide.
# single source of truth: both the sidebar template(sidebar.html) and the RBAC "Sidebar" tab both render from this list
# same data doesn't guarantee same behaviour
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
            "roles.priority",  #  role priority, used to sort roles by priority
            "roles.sidebar_keys",  # sidebar keys for this role
        )
        .order_by("roles.priority", "DESC")  # highest priority first
        .all(allow_full_table=True)
    )


async def get_visible_nav_keys(user_id: str) -> list[str] | None:
    """
     Which Administration nav keys this user may see, or None for "no restriction".

    The critical distinction the code is built around is None vs. empty list:

    sidebar_keys = None (NULL) → that role can see everything. NULL and "the admin checked every box"
    are treated identically by the editor.
    sidebar_keys = [] (empty list) → that role is explicitly restricted to nothing.

     If ANY of the user's roles is unrestricted, the user is unrestricted —
     restrictions only narrow things down when every held role has one.

     Holding zero system roles at all (every org admin/member is in this boat -
     org-scope roles are a completely separate table, see org_permissions.py)
     must resolve to [] here, not None - otherwise everyone without a system
     role would see the entire Administration group and 403 on every click.
     That naturally falls out of the loop below: zero roles means it never
     runs, so `allowed` stays the empty set it started as.
    """
    roles = await get_user_roles(user_id)

    allowed: set[str] = set()
    for role in roles:
        keys = role["sidebar_keys"]
        if keys is None:
            return None  # this role grants full access — nothing to restrict
        allowed.update(keys)

    return list(allowed)


async def user_has_any_role(user_id: str) -> bool:
    """Whether this user holds at least one system role - the same
    definition of "staff" already used by the admin Staff page (see
    staff/repository.py's list_staff docstring). Deliberately not based on
    whether any of those roles currently grant a permission: a role with
    zero permissions assigned (e.g. freshly created, or every permission it
    held got pruned by the registry) still means this is a platform-staff
    account, not a regular tenant user - they just can't do much yet."""
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
    """Route decorator: redirects to login if nobody's signed in, aborts 403 if
    the signed-in user is missing any of the given permissions. Self-contained —
    replaces @login_required on the routes it guards rather than stacking with it."""

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
