"""Org-scoped equivalent of permissions.py.

The system version (permissions.py) restricts based on a user's *global*
role. This restricts based on a user's role *within their organization* -
a completely separate axis, since an org's custom roles must never grant
visibility into another org or into the platform admin area (see
app/core/security/org_permission_registry.py for why these are kept as
separate tables rather than one with a scope column).
"""

from __future__ import annotations

from functools import wraps

from flask import abort, g, url_for

from app.core.db.orm import db
from app.core.security.htmx import redirect_or_htmx
from app.core.security.org_permission_registry import OrgPermission, all_org_permissions

# Single source of truth for both sidebar.html and the org Roles editor's
# Sidebar tab - same role NAV_KEYS plays for the system side.
ORG_NAV_KEYS: list[tuple[str, str]] = [
    ("org_staff", "Staff"),
    ("org_role", "Roles"),
    ("case", "Cases"),
    ("timeline", "Timeline"),
    ("org_billing", "Billing"),
]


async def get_user_org_membership(user_id: str) -> dict | None:
    """This user's organization_members row, joined with their org role's
    sidebar_keys - one query, reused by both the nav-key and permission
    lookups below. None if the user belongs to no organization."""
    return await (
        db.table("organization_members")
        .join("organizations", "organization_members.organization_id", "organizations.id")
        .left_join("organization_roles", "organization_members.role_id", "organization_roles.id")
        .where("organization_members.user_id", user_id)
        .select(
            "organizations.id as organization_id",
            "organizations.verification_status",
            "organizations.created_by",
            "organization_members.role_id",
            "organization_roles.sidebar_keys",
        )
        .first()
    )


def is_org_owner(user_id: str, membership: dict) -> bool:
    """Discord-style ownership: whoever created the org has permanent, full
    access that doesn't depend on holding (or keeping) any role - editing,
    deleting, or reassigning roles can never lock the owner out. Roles exist
    purely to delegate slices of that access to other members."""
    return membership["created_by"] == user_id


async def get_org_visible_nav_keys(user_id: str) -> list[str] | None:
    """Which ORG_NAV_KEYS this user may see, or None for "no restriction".
    Empty list (not None) if the user belongs to no org, or their org role
    hasn't been assigned yet - same None-vs-[] contract as
    permissions.get_visible_nav_keys, see that function's docstring."""
    membership = await get_user_org_membership(user_id)
    if not membership:
        return []
    if is_org_owner(user_id, membership):
        return None
    if not membership["role_id"]:
        return []
    return membership["sidebar_keys"]


async def get_user_org_permission_names(user_id: str) -> set[str]:
    """Every org permission ('resource.action') granted via this user's role
    in their organization - or every permission that exists, unconditionally,
    if this user is the org's owner (see is_org_owner)."""
    membership = await get_user_org_membership(user_id)
    if membership and is_org_owner(user_id, membership):
        return {permission.name for permission in all_org_permissions()}

    rows = await (
        db.table("organization_members")
        .join("organization_role_permissions", "organization_members.role_id", "organization_role_permissions.role_id")
        .join("organization_permissions", "organization_role_permissions.permission_id", "organization_permissions.id")
        .where("organization_members.user_id", user_id)
        .select("organization_permissions.name")
        .all(allow_full_table=True)
    )
    return {row["name"] for row in rows}


def require_org_permission(*permissions: OrgPermission):
    """Route decorator: redirects to login if nobody's signed in, aborts 403
    if the signed-in user's org role is missing any of the given permissions
    (including if they belong to no organization at all)."""

    def decorator(view):
        @wraps(view)
        async def wrapped(*args, **kwargs):
            if g.user_id is None:
                return redirect_or_htmx(url_for("auth.login"))
            granted = await get_user_org_permission_names(g.user_id)
            required = {permission.name for permission in permissions}
            if not required.issubset(granted):
                abort(403)
            return await view(*args, **kwargs)

        return wrapped

    return decorator


def require_any_org_permission(*permissions: OrgPermission):
    """Like require_org_permission, but OR instead of AND - passes if the
    signed-in user's org role holds at least one of the given permissions,
    not necessarily all of them. Used where a broader "manage" permission
    and a narrower "view" permission should both unlock the same read-only
    route (e.g. a role granted only document-viewing shouldn't need full
    settings-management access just to download what it can already see)."""

    def decorator(view):
        @wraps(view)
        async def wrapped(*args, **kwargs):
            if g.user_id is None:
                return redirect_or_htmx(url_for("auth.login"))
            granted = await get_user_org_permission_names(g.user_id)
            required = {permission.name for permission in permissions}
            if not required & granted:
                abort(403)
            return await view(*args, **kwargs)

        return wrapped

    return decorator
