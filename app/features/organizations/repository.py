"""DB access for organizations - the admin Organizations page, plus the
member-facing reads/writes onboarding needs (membership, invite codes)."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from app.core.db.orm import Page, db
from app.core.utils.ids import new_id


# Excludes visually-ambiguous characters (0/O, 1/I/L) since this gets typed
# by hand, not just clicked as a link.
_INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_invite_code(length: int = 10) -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(length))


async def list_organizations(
    *, search: str = "", status: str = "", verification: str = "", page: int = 1, per_page: int = 20
) -> Page:
    query = db.table("organizations")

    if search:
        query = query.search(["name", "description"], search)
    if status:
        query = query.where("status", status)
    if verification:
        query = query.where("verification_status", verification)

    return await query.order_by("created_at", "DESC").paginate(page=page, per_page=per_page)


async def get_member_counts(org_ids: list[str]) -> dict[str, int]:
    if not org_ids:
        return {}

    rows = await (
        db.table("organization_members")
        .where_in("organization_id", org_ids)
        .select("organization_id")
        .all(allow_full_table=True)
    )

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["organization_id"]] = counts.get(row["organization_id"], 0) + 1
    return counts


async def get_organization(org_id: str):
    return await db.table("organizations").where("id", org_id).first()


async def get_by_slug(slug: str):
    return await db.table("organizations").where("slug", slug).first()


async def get_by_invite_code(code: str):
    return await db.table("organizations").where("invite_code", code).first()


async def create_organization(
    *,
    name: str,
    slug: str,
    description: str,
    status: str,
    created_by: str,
    logo_path: str | None = None,
    org_type: str | None = None,
    employee_count: str | None = None,
    address: str | None = None,
    country: str | None = None,
    state: str | None = None,
    city: str | None = None,
    postal_code: str | None = None,
    registration_number: str | None = None,
    pan_number: str | None = None,
    owner_name: str | None = None,
    verification_status: str = "approved",
) -> str:
    org_id = new_id()
    # Every org gets a code up front - admin-created or self-created, it's
    # always ready to share, no separate "generate one" step needed later.
    invite_code = _generate_invite_code()
    await db.table("organizations").create(
        {
            "id": org_id,
            "name": name,
            "slug": slug,
            "invite_code": invite_code,
            "description": description or None,
            "status": status,
            "created_by": created_by,
            # Admin-created orgs (app/features/organizations) skip review -
            # only the onboarding wizard passes "pending" explicitly.
            "verification_status": verification_status,
            # Only the onboarding wizard (app/features/onboarding) fills
            # these in - the admin-side Organizations form still only
            # collects name/description/status, so every field here is
            # optional and defaults to NULL for that path.
            "logo_path": logo_path,
            "org_type": org_type,
            "employee_count": employee_count,
            "address": address,
            "country": country,
            "state": state,
            "city": city,
            "postal_code": postal_code,
            "registration_number": registration_number,
            "pan_number": pan_number,
            "owner_name": owner_name,
        }
    )
    return org_id


async def update_organization(org_id: str, *, name: str, description: str, status: str) -> None:
    await db.table("organizations").where("id", org_id).patch(
        {"name": name, "description": description or None, "status": status}
    )


async def regenerate_invite_code(org_id: str) -> str:
    code = _generate_invite_code()
    await db.table("organizations").where("id", org_id).patch({"invite_code": code})
    return code


async def set_verification_status(
    org_id: str, status: str, *, reviewed_by: str, reason: str | None = None
) -> None:
    await db.table("organizations").where("id", org_id).patch(
        {
            "verification_status": status,
            "rejection_reason": reason,
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(timezone.utc),
        }
    )


async def add_member(org_id: str, user_id: str, role_id: str | None = None) -> None:
    await db.table("organization_members").create(
        {"id": new_id(), "organization_id": org_id, "user_id": user_id, "role_id": role_id}
    )


async def remove_member(org_id: str, user_id: str) -> None:
    await (
        db.table("organization_members")
        .where("organization_id", org_id)
        .where("user_id", user_id)
        .delete()
    )


async def list_members(org_id: str) -> list:
    return await (
        db.table("organization_members")
        .join("user", "organization_members.user_id", "user.id")
        .left_join("organization_roles", "organization_members.role_id", "organization_roles.id")
        .where("organization_members.organization_id", org_id)
        .select(
            "user.id",
            "user.name",
            "user.email",
            "organization_roles.id as role_id",
            "organization_roles.name as role_name",
            "organization_roles.color as role_color",
            "organization_members.joined_at",
        )
        .order_by("user.name")
        .all(allow_full_table=True)
    )


async def is_member(org_id: str, user_id: str) -> bool:
    row = (
        await db.table("organization_members")
        .where("organization_id", org_id)
        .where("user_id", user_id)
        .first()
    )
    return row is not None


async def transfer_ownership(org_id: str, new_owner_id: str) -> None:
    await db.table("organizations").where("id", org_id).patch({"created_by": new_owner_id})


async def get_user_organization(user_id: str):
    """The single organization this user belongs to, or None. Joined with
    organizations for display on the onboarding/invite profile page."""
    return await (
        db.table("organization_members")
        .join("organizations", "organization_members.organization_id", "organizations.id")
        .where("organization_members.user_id", user_id)
        .select(
            "organizations.id",
            "organizations.name",
            "organizations.invite_code",
            "organizations.logo_path",
            "organizations.org_type",
            "organizations.employee_count",
            "organizations.address",
            "organizations.country",
            "organizations.state",
            "organizations.city",
            "organizations.postal_code",
            "organizations.registration_number",
            "organizations.owner_name",
            "organizations.verification_status",
            "organizations.rejection_reason",
        )
        .first()
    )


async def add_document(org_id: str, file_path: str, original_filename: str) -> str:
    doc_id = new_id()
    await db.table("organization_documents").create(
        {
            "id": doc_id,
            "organization_id": org_id,
            "file_path": file_path,
            "original_filename": original_filename,
        }
    )
    return doc_id


async def get_document(doc_id: str):
    return await db.table("organization_documents").where("id", doc_id).first()


async def delete_document(doc_id: str) -> None:
    await db.table("organization_documents").where("id", doc_id).delete()


async def list_documents(org_id: str):
    return await (
        db.table("organization_documents")
        .where("organization_id", org_id)
        .order_by("uploaded_at", "ASC")
        .all(allow_full_table=True)
    )


async def delete_organization(org_id: str) -> tuple[str | None, list[str]]:
    """Deletes the organization row - organization_members, organization_roles
    (and its organization_role_permissions), and organization_documents all
    cascade via FK ON DELETE CASCADE (see migrations 006/007). Returns
    (logo_path, [document file_path, ...]) from before the delete, so the
    caller can clean up the actual files on disk - those aren't DB rows, so
    nothing cascades them automatically."""
    org = await db.table("organizations").where("id", org_id).first()
    if not org:
        return None, []
    documents = await list_documents(org_id)
    await db.table("organizations").where("id", org_id).delete()
    return org["logo_path"], [doc["file_path"] for doc in documents]


# ── org-scoped roles & permissions ──────────────────────────────────────────
# Mirrors app/features/rbac/repository.py's role CRUD exactly, just scoped to
# one organization_id throughout - see app/core/security/org_permission_registry.py
# for why this is a fully separate table set rather than a shared one.


async def list_org_roles(org_id: str) -> list:
    return await (
        db.table("organization_roles")
        .where("organization_id", org_id)
        .order_by("priority", "DESC")
        .all(allow_full_table=True)
    )


async def get_org_role(role_id: str):
    return await db.table("organization_roles").where("id", role_id).first()


async def get_org_role_member_counts(role_ids: list[str]) -> dict[str, int]:
    if not role_ids:
        return {}
    rows = await (
        db.table("organization_members")
        .where_in("role_id", role_ids)
        .select("role_id")
        .all(allow_full_table=True)
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["role_id"]] = counts.get(row["role_id"], 0) + 1
    return counts


async def get_unique_org_role_name(org_id: str, base: str) -> str:
    existing = {r["name"] for r in await list_org_roles(org_id)}
    if base not in existing:
        return base
    suffix = 2
    while f"{base} {suffix}" in existing:
        suffix += 1
    return f"{base} {suffix}"


async def create_org_role(org_id: str, *, name: str, description: str = "", color: str = "#5865F2") -> str:
    role_id = new_id()
    name = await get_unique_org_role_name(org_id, name)
    await db.table("organization_roles").create(
        {
            "id": role_id,
            "organization_id": org_id,
            "name": name,
            "description": description or None,
            "color": color,
            "priority": 0,
            "is_system": False,
            "is_default": False,
            "is_assignable": True,
        }
    )
    return role_id


async def update_org_role_display(role_id: str, *, name: str, description: str, color: str) -> None:
    await db.table("organization_roles").where("id", role_id).patch(
        {"name": name, "description": description or None, "color": color}
    )


async def set_org_role_assignable(role_id: str, is_assignable: bool) -> None:
    await db.table("organization_roles").where("id", role_id).patch({"is_assignable": is_assignable})


async def set_org_role_sidebar_keys(role_id: str, keys: list[str] | None) -> None:
    value = json.dumps(keys) if keys is not None else None
    await db.table("organization_roles").where("id", role_id).patch({"sidebar_keys": value})


async def delete_org_role(role_id: str) -> None:
    await db.table("organization_roles").where("id", role_id).delete()


async def duplicate_org_role(role_id: str) -> str:
    original = await get_org_role(role_id)
    new_role_id = new_id()
    name = await get_unique_org_role_name(original["organization_id"], f"{original['name']} (copy)")
    async with db.transaction():
        await db.table("organization_roles").create(
            {
                "id": new_role_id,
                "organization_id": original["organization_id"],
                "name": name,
                "description": original["description"],
                "color": original["color"],
                "priority": 0,
                "is_system": False,
                "is_default": False,
                "is_assignable": True,
                "sidebar_keys": json.dumps(original["sidebar_keys"]) if original["sidebar_keys"] is not None else None,
            }
        )
        permission_ids = await get_org_role_permission_ids(role_id)
        for permission_id in permission_ids:
            await db.table("organization_role_permissions").create(
                {"role_id": new_role_id, "permission_id": permission_id}
            )
    return new_role_id


async def get_all_org_permissions() -> list:
    return await (
        db.table("organization_permissions")
        .order_by("category")
        .order_by("name")
        .all(allow_full_table=True)
    )


async def get_org_role_permission_ids(role_id: str) -> set[str]:
    rows = await (
        db.table("organization_role_permissions")
        .where("role_id", role_id)
        .select("permission_id")
        .all(allow_full_table=True)
    )
    return {row["permission_id"] for row in rows}


async def set_org_role_permissions(role_id: str, permission_ids: list[str]) -> None:
    async with db.transaction():
        await db.table("organization_role_permissions").where("role_id", role_id).delete()
        for permission_id in permission_ids:
            await db.table("organization_role_permissions").create(
                {"role_id": role_id, "permission_id": permission_id}
            )


async def get_org_role_members(role_id: str) -> list:
    return await (
        db.table("organization_members")
        .join("user", "organization_members.user_id", "user.id")
        .where("organization_members.role_id", role_id)
        .select("user.id", "user.name", "user.email")
        .order_by("user.name")
        .all(allow_full_table=True)
    )


async def search_org_assignable_users(org_id: str, role_id: str, search: str) -> list:
    """This org's members NOT already holding this role, for the 'add member' picker."""
    other_members = await (
        db.table("organization_members")
        .where("organization_id", org_id)
        # role_id IS NULL for most members (nobody's assigned them a role
        # yet) - a plain `!= role_id` silently drops those rows, since SQL
        # NULL != anything is UNKNOWN, not TRUE. Has to be spelled out as an
        # explicit OR so members with no role still show up as assignable.
        .or_where([("role_id", None), ("role_id", "!=", role_id)])
        .select("user_id")
        .all(allow_full_table=True)
    )
    candidate_ids = [row["user_id"] for row in other_members]
    if not candidate_ids:
        return []

    query = db.table("user").where_in("id", candidate_ids)
    if search:
        query = query.search(["name", "email"], search)
    return await query.select("id", "name", "email").order_by("name").limit(20).all()


async def assign_member_role(org_id: str, user_id: str, role_id: str) -> None:
    await (
        db.table("organization_members")
        .where("organization_id", org_id)
        .where("user_id", user_id)
        .patch({"role_id": role_id})
    )


async def clear_member_role(org_id: str, user_id: str) -> None:
    """"Removing" a member from a role (Members tab) doesn't kick them out of
    the org - it just leaves them with no role, same as any other member
    nobody's assigned one to yet."""
    await (
        db.table("organization_members")
        .where("organization_id", org_id)
        .where("user_id", user_id)
        .patch({"role_id": None})
    )
