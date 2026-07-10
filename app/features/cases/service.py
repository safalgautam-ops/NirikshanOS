"""Case business logic: field validation, member management, and the
row-level visibility rule (org owner, or the case's creator, or anyone
added as a case member - see app/features/cases/repository.py for the
queries this is built on)."""

from __future__ import annotations

from app.features.cases import repository
from app.features.cases.choices import CLASSIFICATIONS, FORENSIC_STATUSES, SEVERITIES
from app.features.organizations import repository as org_repository

_CLASSIFICATION_VALUES = {value for value, _label in CLASSIFICATIONS}
_SEVERITY_VALUES = {value for value, _label in SEVERITIES}
_FORENSIC_STATUS_VALUES = {value for value, _label in FORENSIC_STATUSES}


class CaseError(Exception):
    """A user-visible case failure - safe to display directly."""


def _validate_fields(*, title: str, classification: str, severity: str, forensic_status: str) -> str:
    title = title.strip()
    if not title:
        raise CaseError("Case title is required.")
    if classification not in _CLASSIFICATION_VALUES:
        raise CaseError("Select a valid case classification.")
    if severity not in _SEVERITY_VALUES:
        raise CaseError("Select a valid case severity.")
    if forensic_status not in _FORENSIC_STATUS_VALUES:
        raise CaseError("Select a valid forensic examination status.")
    return title


async def can_access_case(case, user_id: str, *, is_owner: bool) -> bool:
    if is_owner or case["created_by"] == user_id:
        return True
    return await repository.is_case_member(case["id"], user_id)


async def get_case_for_user(case_id: str, user_id: str, *, is_owner: bool):
    """The case row if this user may view it, else None. Callers should turn
    None into a 404 (not 403) so a non-member can't confirm a case id exists
    just by guessing it."""
    case = await repository.get_case(case_id)
    if not case:
        return None
    if not await can_access_case(case, user_id, is_owner=is_owner):
        return None
    return case


async def list_cases_for_user(organization_id: str, user_id: str, *, is_owner: bool, limit: int | None = None):
    if is_owner:
        return await repository.list_org_cases(organization_id, limit=limit)
    return await repository.list_member_cases(organization_id, user_id, limit=limit)


async def create_case(
    *,
    organization_id: str,
    title: str,
    description: str,
    classification: str,
    severity: str,
    forensic_status: str,
    created_by: str,
    member_ids: list[str],
) -> str:
    title = _validate_fields(
        title=title, classification=classification, severity=severity, forensic_status=forensic_status
    )
    case_id = await repository.create_case(
        organization_id=organization_id,
        title=title,
        description=description.strip(),
        classification=classification,
        severity=severity,
        forensic_status=forensic_status,
        created_by=created_by,
    )
    org_member_ids = {m["id"] for m in await org_repository.list_members(organization_id)}
    for member_id in dict.fromkeys(member_ids):
        if member_id and member_id != created_by and member_id in org_member_ids:
            await repository.add_member(case_id, member_id, added_by=created_by)
    return case_id


async def update_case(
    case_id: str,
    *,
    title: str,
    description: str,
    classification: str,
    severity: str,
    forensic_status: str,
) -> None:
    title = _validate_fields(
        title=title, classification=classification, severity=severity, forensic_status=forensic_status
    )
    await repository.update_case(
        case_id,
        title=title,
        description=description.strip(),
        classification=classification,
        severity=severity,
        forensic_status=forensic_status,
    )


async def delete_case(case_id: str) -> None:
    await repository.delete_case(case_id)


async def add_member(case_id: str, user_id: str, *, added_by: str) -> None:
    case = await repository.get_case(case_id)
    if not case:
        raise CaseError("Case not found.")
    org_member_ids = {m["id"] for m in await org_repository.list_members(case["organization_id"])}
    if user_id not in org_member_ids:
        raise CaseError("That user is not a member of this organization.")
    if user_id == case["created_by"]:
        raise CaseError("The case's creator already has access.")
    if await repository.is_case_member(case_id, user_id):
        raise CaseError("That member is already on this case.")
    await repository.add_member(case_id, user_id, added_by=added_by)


async def remove_member(case_id: str, user_id: str, *, requested_by: str, is_owner: bool) -> None:
    """Removing a member is something a manager does to them, not a
    self-service "quit" action - a regular member holding CASE_EDIT (needed
    to manage *other* members) shouldn't be able to turn that same control
    on themselves. The org owner is exempt, same "owner is above every
    other rule" guarantee used everywhere else (see is_org_owner)."""
    if user_id == requested_by and not is_owner:
        raise CaseError("You can't remove yourself from a case - ask the case owner or a manager.")
    await repository.remove_member(case_id, user_id)


async def get_case_members(case_id: str):
    return await repository.get_case_members(case_id)


async def search_addable_members(organization_id: str, case_id: str, search: str):
    return await repository.search_org_members_not_in_case(organization_id, case_id, search)
