"""DB access for cases - thin wrappers around the ORM, no business rules."""

from __future__ import annotations

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def create_case(
    *,
    organization_id: str,
    title: str,
    description: str,
    classification: str,
    severity: str,
    forensic_status: str,
    created_by: str,
) -> str:
    case_id = new_id()
    await db.table("cases").create(
        {
            "id": case_id,
            "organization_id": organization_id,
            # id is already globally unique - reusing it rules out any
            # collision without a retry loop or a second query.
            "case_number": f"CASE-{case_id[:8].upper()}",
            "title": title,
            "description": description,
            "classification": classification,
            "severity": severity,
            "forensic_status": forensic_status,
            "created_by": created_by,
        }
    )
    return case_id


async def get_case(case_id: str):
    return await db.table("cases").where("id", case_id).first()


async def update_case(
    case_id: str,
    *,
    title: str,
    description: str,
    classification: str,
    severity: str,
    forensic_status: str,
) -> None:
    await (
        db.table("cases")
        .where("id", case_id)
        .patch(
            {
                "title": title,
                "description": description,
                "classification": classification,
                "severity": severity,
                "forensic_status": forensic_status,
            }
        )
    )


async def delete_case(case_id: str) -> None:
    await db.table("cases").where("id", case_id).delete()


async def list_org_cases(organization_id: str, *, limit: int | None = None) -> list:
    """Every case in the org - only valid for the org's owner, who bypasses
    per-case membership the same way they bypass everything else."""
    query = db.table("cases").where("organization_id", organization_id).order_by("created_at", "DESC")
    if limit:
        return await query.limit(limit).all()
    return await query.all(allow_full_table=True)


async def list_member_cases(organization_id: str, user_id: str, *, limit: int | None = None) -> list:
    """Cases this user can see: their own + whatever they've been added to."""
    member_case_ids = await (
        db.table("case_members").where("user_id", user_id).select("case_id").all(allow_full_table=True)
    )
    ids = list({row["case_id"] for row in member_case_ids})

    query = (
        db.table("cases")
        .where("organization_id", organization_id)
        .or_where([("created_by", user_id), ("id", "in", ids)] if ids else [("created_by", user_id)])
        .order_by("created_at", "DESC")
    )
    if limit:
        return await query.limit(limit).all()
    return await query.all(allow_full_table=True)


async def is_case_member(case_id: str, user_id: str) -> bool:
    row = await db.table("case_members").where("case_id", case_id).where("user_id", user_id).first()
    return row is not None


async def add_member(case_id: str, user_id: str, *, added_by: str) -> None:
    await db.table("case_members").create(
        {
            "id": new_id(),
            "case_id": case_id,
            "user_id": user_id,
            "added_by": added_by,
        }
    )


async def remove_member(case_id: str, user_id: str) -> None:
    await db.table("case_members").where("case_id", case_id).where("user_id", user_id).delete()


async def get_case_members(case_id: str) -> list:
    return await (
        db.table("case_members")
        .join("user", "case_members.user_id", "user.id")
        .where("case_members.case_id", case_id)
        .select("user.id", "user.name", "user.email")
        .order_by("user.name")
        .all(allow_full_table=True)
    )


async def search_org_members_not_in_case(organization_id: str, case_id: str, search: str) -> list:
    """This org's members who aren't already on this case (and aren't the
    case's own creator, who needs no membership row to access it) - for the
    'add member' combobox."""
    case = await get_case(case_id)
    existing = await (
        db.table("case_members").where("case_id", case_id).select("user_id").all(allow_full_table=True)
    )
    excluded_ids = {row["user_id"] for row in existing}
    if case:
        excluded_ids.add(case["created_by"])

    member_rows = await (
        db.table("organization_members")
        .where("organization_id", organization_id)
        .select("user_id")
        .all(allow_full_table=True)
    )
    candidate_ids = [row["user_id"] for row in member_rows if row["user_id"] not in excluded_ids]
    if not candidate_ids:
        return []

    query = db.table("user").where_in("id", candidate_ids)
    if search:
        query = query.search(["name", "email"], search)
    return await query.order_by("name").all(allow_full_table=True)
