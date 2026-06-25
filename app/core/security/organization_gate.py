"""Organization-onboarding gate.

A regular self-registered user (Member role, zero permissions) has nothing
useful to do in the app until they belong to an *approved* organization -
they're locked to the dashboard + Organization route only. Staff/admins
(anyone holding at least one system role) are exempt; onboarding doesn't
apply to them.

Kept here, not in app/features/onboarding/, for the same reason
permissions.py's get_visible_nav_keys lives in core/security rather than in
the rbac feature: app/__init__.py's global before_request gate needs this on
every request, and core/security must not depend on a feature package.
"""

from __future__ import annotations

from app.core.db.orm import db
from app.core.security.permissions import user_has_any_role

STATE_NONE = "none"  # no permissions, no org membership - show create/join
STATE_PENDING = "pending"  # member of an org awaiting admin review
STATE_REJECTED = "rejected"  # member of an org an admin rejected
STATE_ACTIVE = "active"  # holds a system role, or member of an approved org


async def get_organization_state(user_id: str) -> str:
    if await user_has_any_role(user_id):
        return STATE_ACTIVE  # staff/admin - onboarding doesn't apply

    member_row = await (
        db.table("organization_members")
        .join("organizations", "organization_members.organization_id", "organizations.id")
        .where("organization_members.user_id", user_id)
        .select("organizations.verification_status")
        .first()
    )
    if not member_row:
        return STATE_NONE

    return {
        "pending": STATE_PENDING,
        "rejected": STATE_REJECTED,
    }.get(member_row["verification_status"], STATE_ACTIVE)


async def needs_organization_onboarding(user_id: str) -> bool:
    """True while the user should be locked to the dashboard + Organization
    route only - no org yet, or their org hasn't been approved."""
    return await get_organization_state(user_id) != STATE_ACTIVE
