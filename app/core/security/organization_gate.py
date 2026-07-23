"""Organization-onboarding gate."""

from __future__ import annotations

from app.core.db.orm import db
from app.core.security.permissions import user_has_any_role

STATE_NONE = "none"
STATE_PENDING = "pending"
STATE_REJECTED = "rejected"
STATE_ACTIVE = "active"


async def get_organization_state(user_id: str) -> str:
    if await user_has_any_role(user_id):
        return STATE_ACTIVE

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
    """True while the user should be locked to the dashboard + Organization route only - no org yet, or their org hasn't been approved."""
    return await get_organization_state(user_id) != STATE_ACTIVE
