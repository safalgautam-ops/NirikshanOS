"""Onboarding business logic: create-or-join an organization.

No new tables of its own for the org/membership data - organizations/
organization_members already hold everything needed, owned by
app.features.organizations. This just orchestrates that feature's
repository for the self-service, member-facing flow (as opposed to the
admin-only Organizations page, which only ever collects name/description/
status). organization_documents is the one new table this feature actually
owns the writes for.
"""

from __future__ import annotations

from itertools import groupby

from werkzeug.datastructures import FileStorage

from app.core import storage
from app.core.security.org_permissions import ORG_NAV_KEYS
from app.features.organizations import repository as org_repository
from app.features.organizations.choices import EMPLOYEE_COUNT_RANGES, ORG_TYPES
from app.features.organizations.countries import COUNTRIES
from app.features.organizations.service import slugify

_ORG_TYPE_VALUES = {value for value, _label in ORG_TYPES}
_COUNTRY_SET = set(COUNTRIES)


class OnboardingError(Exception):
    """A user-visible onboarding failure - safe to display directly."""


async def create_and_join(
    *,
    created_by: str,
    name: str,
    description: str,
    org_type: str,
    employee_count: str,
    address: str,
    country: str,
    state: str,
    city: str,
    postal_code: str,
    registration_number: str,
    pan_number: str,
    owner_name: str,
    logo: FileStorage | None,
    documents: list[FileStorage],
) -> str:
    """Validate and create an organization from the 3-step wizard, then add
    the creator as its first member. Raises OnboardingError - with a
    message safe to show directly - on any validation failure."""
    name = name.strip()
    address = address.strip()
    registration_number = registration_number.strip()
    owner_name = owner_name.strip()

    if not name:
        raise OnboardingError("Organization name is required.")
    if org_type not in _ORG_TYPE_VALUES:
        raise OnboardingError("Select a valid organization type.")
    if employee_count not in EMPLOYEE_COUNT_RANGES:
        raise OnboardingError("Select a valid employee count range.")
    if not address:
        raise OnboardingError("Organization address is required.")
    if country not in _COUNTRY_SET:
        raise OnboardingError("Select a valid country.")
    if not registration_number:
        raise OnboardingError("Registration number is required.")
    if not owner_name:
        raise OnboardingError("Owner name is required.")

    real_documents = [doc for doc in documents if doc and doc.filename]
    if not real_documents:
        raise OnboardingError("Upload at least one government document.")

    slug = slugify(name)
    if await org_repository.get_by_slug(slug):
        raise OnboardingError("An organization with that name already exists.")

    logo_path = None
    if logo and logo.filename:
        try:
            logo_path = await storage.save_logo(logo)
        except ValueError as exc:
            raise OnboardingError(str(exc)) from exc

    saved_documents: list[tuple[str, str]] = []
    try:
        for doc in real_documents:
            saved_documents.append(await storage.save_document(doc))
    except ValueError as exc:
        raise OnboardingError(str(exc)) from exc

    org_id = await org_repository.create_organization(
        name=name,
        slug=slug,
        description=description.strip(),
        status="active",
        created_by=created_by,
        # Self-registered orgs wait for an administrator to review the
        # submitted KYC details/documents before unlocking the rest of the
        # app for their members - see app/core/security/organization_gate.py.
        verification_status="pending",
        logo_path=logo_path,
        org_type=org_type,
        employee_count=employee_count,
        address=address,
        country=country,
        state=state.strip(),
        city=city.strip(),
        postal_code=postal_code.strip(),
        registration_number=registration_number,
        pan_number=pan_number.strip(),
        owner_name=owner_name,
    )

    for file_path, original_filename in saved_documents:
        await org_repository.add_document(org_id, file_path, original_filename)

    # No roles exist until the owner creates some - ownership is a separate,
    # role-independent seat (see org_permissions.is_org_owner) that already
    # bypasses every permission check, and a fresh org has no other members
    # yet to need one either. The owner builds out roles (Discord-style)
    # from the Roles page and decides who gets what, instead of inheriting
    # a "Org Admin"/"Member" pair nobody asked for.
    await org_repository.add_member(org_id, created_by)
    return org_id


async def join_by_code(*, code: str, user_id: str) -> str:
    code = code.strip().upper()
    if not code:
        raise OnboardingError("Enter an invite code.")

    org = await org_repository.get_by_invite_code(code)
    if not org:
        raise OnboardingError("That invite code isn't valid.")

    if await org_repository.is_member(org["id"], user_id):
        raise OnboardingError("You're already a member of this organization.")

    # New members join with no role - they get whatever the owner/an admin
    # later decides to grant them, not an implicit "Member" role.
    await org_repository.add_member(org["id"], user_id)
    return org["id"]


async def get_user_organization(user_id: str):
    return await org_repository.get_user_organization(user_id)


async def list_documents(org_id: str):
    return await org_repository.list_documents(org_id)


async def _ensure_org_not_yet_verified(org_id: str) -> None:
    """Once a platform admin has approved an organization, its submitted
    documents are locked from the org's own side - only a platform admin can
    change them from then on (see organizations/routes.py's admin-side
    upload/delete), so a verified org can't quietly swap out what was
    reviewed. Before approval, the org can still fix/replace what it
    submitted."""
    org = await org_repository.get_organization(org_id)
    if org and org["verification_status"] == "approved":
        raise OnboardingError(
            "Documents are locked after verification - contact a platform admin to change them."
        )


async def add_documents(org_id: str, files: list[FileStorage]) -> None:
    """Uploads more government documents to an already-existing organization
    - the 3-step wizard only collects these once, at creation, but an org
    admin/owner may need to add or replace one before the organization is
    verified."""
    await _ensure_org_not_yet_verified(org_id)
    real_files = [file for file in files if file and file.filename]
    if not real_files:
        raise OnboardingError("Choose at least one file to upload.")
    for file in real_files:
        try:
            file_path, original_filename = await storage.save_document(file)
        except ValueError as exc:
            raise OnboardingError(str(exc)) from exc
        await org_repository.add_document(org_id, file_path, original_filename)


async def delete_document(org_id: str, doc_id: str) -> None:
    await _ensure_org_not_yet_verified(org_id)
    doc = await org_repository.get_document(doc_id)
    if not doc or doc["organization_id"] != org_id:
        raise OnboardingError("Document not found.")
    await org_repository.delete_document(doc_id)
    await storage.delete_file(doc["file_path"])


async def regenerate_invite_code(user_id: str) -> str:
    org = await org_repository.get_user_organization(user_id)
    if not org:
        raise OnboardingError("You don't belong to an organization.")
    return await org_repository.regenerate_invite_code(org["id"])


async def get_document_for_download(*, doc_id: str, user_id: str):
    """Returns (presigned download URL, original filename) if the
    requesting user belongs to the document's organization, else None - the
    route turns that into a 404 rather than leaking whether the id exists."""
    doc = await org_repository.get_document(doc_id)
    if not doc:
        return None
    if not await org_repository.is_member(doc["organization_id"], user_id):
        return None
    return await storage.get_document_url(doc["file_path"]), doc["original_filename"]


async def delete_organization(org_id: str, *, requested_by: str) -> None:
    """Permanently deletes the organization - members, roles, and document
    records all cascade at the DB level (see repository.delete_organization),
    this just adds the one rule the DB can't express: only the org's owner
    (whoever created it, see org_permissions.is_org_owner) may do this, no
    matter what permissions some other role grants - same "owner is above
    the role system" guarantee as remove_staff's owner-removal block."""
    org = await org_repository.get_organization(org_id)
    if not org:
        raise OnboardingError("Organization not found.")
    if org["created_by"] != requested_by:
        raise OnboardingError("Only the organization's owner can delete it.")
    logo_path, document_paths = await org_repository.delete_organization(org_id)
    if logo_path:
        await storage.delete_file(logo_path)
    for document_path in document_paths:
        await storage.delete_file(document_path)


# ── org staff (the org's own member list) ───────────────────────────────────


async def list_staff(org_id: str):
    return await org_repository.list_members(org_id)


async def remove_staff(org_id: str, user_id: str, *, removed_by: str) -> None:
    if user_id == removed_by:
        raise OnboardingError("You can't remove yourself from the organization.")
    org = await org_repository.get_organization(org_id)
    if org and org["created_by"] == user_id:
        raise OnboardingError("The organization's owner can't be removed.")
    await org_repository.remove_member(org_id, user_id)


async def leave_organization(org_id: str, user_id: str) -> None:
    """Any member can leave on their own - this isn't gated by ORG_STAFF_REMOVE,
    it's a basic membership right, not an admin action. The one exception is
    the owner: leaving would orphan the organization (no one left who can
    manage roles/settings/billing-equivalent decisions), so they must transfer
    ownership to another member first - see transfer_ownership below."""
    if await _is_owner(org_id, user_id):
        raise OnboardingError("Transfer ownership to another member before leaving.")
    await org_repository.remove_member(org_id, user_id)


async def transfer_ownership(org_id: str, *, current_owner_id: str, new_owner_id: str) -> None:
    """Discord-style ownership transfer: the only way an owner's special,
    role-independent access (see org_permissions.is_org_owner) ever moves to
    someone else. The new owner must already be a member - this doesn't
    invite anyone, it just hands off the one seat that bypasses the role
    system entirely."""
    if new_owner_id == current_owner_id:
        raise OnboardingError("Choose a different member to transfer ownership to.")
    if not await _is_owner(org_id, current_owner_id):
        raise OnboardingError("Only the organization's owner can transfer ownership.")
    if not await org_repository.is_member(org_id, new_owner_id):
        raise OnboardingError("That user isn't a member of this organization.")
    await org_repository.transfer_ownership(org_id, new_owner_id)
    # Both sides keep whatever role they already held (likely none, for
    # either) - ownership isn't a role and doesn't grant or require one. The
    # outgoing owner becomes a perfectly ordinary roleless member, same as
    # anyone else who hasn't been granted a role yet.


# ── org roles & permissions ──────────────────────────────────────────────────
# Mirrors app/features/rbac/service.py exactly, just org_id-scoped throughout.


async def get_org_roles_page(org_id: str):
    roles = await org_repository.list_org_roles(org_id)
    counts = await org_repository.get_org_role_member_counts([r["id"] for r in roles])
    for role in roles:
        role["member_count"] = counts.get(role["id"], 0)
    return roles


async def create_org_role(org_id: str, name: str) -> str:
    name = name.strip() or "New role"
    return await org_repository.create_org_role(org_id, name=name)


async def update_org_role_display(role_id: str, *, name: str, description: str, color: str) -> None:
    name = name.strip()
    if not name:
        raise OnboardingError("Role name is required.")
    await org_repository.update_org_role_display(
        role_id, name=name, description=description.strip(), color=color
    )


async def _is_owner(org_id: str, user_id: str) -> bool:
    org = await org_repository.get_organization(org_id)
    return bool(org and org["created_by"] == user_id)


async def toggle_org_role_assignable(role_id: str, *, requested_by: str) -> None:
    role = await org_repository.get_org_role(role_id)
    if not role:
        raise OnboardingError("Role not found.")
    # is_system (the bootstrap "Org Admin" role) is locked against everyone
    # except the org's owner - same "owner is above the role system"
    # guarantee as everywhere else owner bypasses apply. Discord-style: the
    # owner has full, unrestricted role customization; nobody else gets to
    # touch the one role that's otherwise structurally protected.
    if role["is_system"] and not await _is_owner(role["organization_id"], requested_by):
        raise OnboardingError("Only the organization's owner can change this role.")
    await org_repository.set_org_role_assignable(role_id, not role["is_assignable"])


async def delete_org_role(org_id: str, role_id: str, *, requested_by: str) -> None:
    role = await org_repository.get_org_role(role_id)
    if not role:
        raise OnboardingError("Role not found.")
    # No role is structurally protected anymore - members don't need *some*
    # role to fall back to (see remove_role_member/join_by_code), so even
    # the role flagged is_default can be deleted, owner or not.
    if role["is_system"] and not await _is_owner(org_id, requested_by):
        raise OnboardingError("Only the organization's owner can delete this role.")
    # Members holding the deleted role simply lose it - no implicit
    # fallback role to land on.
    for member in await org_repository.get_org_role_members(role_id):
        await org_repository.clear_member_role(org_id, member["id"])
    await org_repository.delete_org_role(role_id)


async def duplicate_org_role(role_id: str) -> str:
    return await org_repository.duplicate_org_role(role_id)


async def get_org_permissions_grouped() -> list[tuple[str, list]]:
    """[(category, [permission, ...]), ...] - ready for the Permissions tab."""
    permissions = await org_repository.get_all_org_permissions()
    return [
        (category or "Other", list(group))
        for category, group in groupby(permissions, key=lambda p: p["category"])
    ]


async def update_org_role_permissions(role_id: str, permission_ids: list[str]) -> None:
    await org_repository.set_org_role_permissions(role_id, permission_ids)


async def update_org_role_sidebar(role_id: str, selected_keys: list[str]) -> None:
    """NULL = unrestricted (every nav key was checked); otherwise store
    exactly what's checked - same contract as the system rbac's sidebar."""
    all_keys = {key for key, _ in ORG_NAV_KEYS}
    keys = None if set(selected_keys) >= all_keys else selected_keys
    await org_repository.set_org_role_sidebar_keys(role_id, keys)


async def assign_role_member(org_id: str, role_id: str, user_id: str) -> None:
    if await _is_owner(org_id, user_id):
        raise OnboardingError("The organization's owner doesn't hold a role - ownership already grants full access.")
    role = await org_repository.get_org_role(role_id)
    if role and not role["is_assignable"]:
        raise OnboardingError("This role's assignment is currently blocked.")
    await org_repository.assign_member_role(org_id, user_id, role_id)


async def remove_role_member(org_id: str, user_id: str) -> None:
    """"Removing" a member from a role in the Members tab just clears their
    role - it doesn't kick them out of the organization, and there's no
    fallback role to land on since none is mandatory."""
    await org_repository.clear_member_role(org_id, user_id)
