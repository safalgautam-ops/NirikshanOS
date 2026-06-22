"""
authorization helper module that decides which sidebar navigation items a user is allowed to see,
based on the roles assigned to them.
"""

from __future__ import annotations

from functools import wraps

from quart import abort, g, redirect, url_for

from app.core.db.orm import db
from app.core.security.permission_registry import Permission

# hardcoded list of every dashboard navigation item that can be toggled-per role, paired with its display label
# single source of truth: both the sidebar template(sidebar.html) and the RBAC "Sidebar" tab both render from this list
# same data doesn't guarantee same behaviour
NAV_KEYS: list[tuple[str, str]] = [
    ("dashboard", "Dashboard"),
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
            "roles.priority",  #  role priority, used to sort roles by priority
            "roles.sidebar_keys",  # sidebar keys for this role
        )
        .order_by("roles.priority", "DESC")  # highest priority first
        .all(allow_full_table=True)
    )


async def get_visible_nav_keys(user_id: str) -> list[str] | None:
    """
     Which sidebar nav keys this user may see, or None for "no restriction".

    The critical distinction the code is built around is None vs. empty list:

    sidebar_keys = None (NULL) → that role can see everything. NULL and "the admin checked every box"
    are treated identically by the editor.
    sidebar_keys = [] (empty list) → that role is explicitly restricted to nothing.

     If ANY of the user's roles is unrestricted, the user is unrestricted —
     restrictions only narrow things down when every held role has one.

     In Python, if not keys is a shortcut for "is this thing empty or absent?" The problem is
     that it treats several different values as the same thing — they're all "falsy":

     if not None:   # True  — None is falsy
     if not []:     # True  — empty list is falsy
     if not 0:      # True  — zero is falsy

     So None and [] both make if not keys fire. Python can't tell them apart with that check.

     If the author had written if not keys instead of if keys is None, then an empty list []
     would also trigger that branch — because [] is falsy too. So a role meant to grant nothing would
     accidentally be read as granting everything. That's a serious bug: someone you locked out of every page
     would suddenly see all of them.
     Using is None checks for exactly None and nothing else. An empty list is not None,
     so it skips that branch and instead falls through to the normal code, which adds its keys (none of them)
     to the allowed set — correctly granting access to nothing.
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
                return redirect(url_for("auth.login"))
            granted = await get_user_permission_names(g.user_id)
            required = {permission.name for permission in permissions}
            if not required.issubset(granted):
                abort(403)
            return await view(*args, **kwargs)

        return wrapped

    return decorator
