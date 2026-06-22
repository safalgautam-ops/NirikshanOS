"""DB access for the admin Organizations page."""

from __future__ import annotations

from app.core.db.orm import Page, db
from app.core.utils.ids import new_id


async def list_organizations(
    *, search: str = "", status: str = "", page: int = 1, per_page: int = 20
) -> Page:
    query = db.table("organizations")

    if search:
        query = query.search(["name", "description"], search)
    if status:
        query = query.where("status", status)

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


async def create_organization(
    *, name: str, slug: str, description: str, status: str, created_by: str
) -> str:
    org_id = new_id()
    await db.table("organizations").create(
        {
            "id": org_id,
            "name": name,
            "slug": slug,
            "description": description or None,
            "status": status,
            "created_by": created_by,
        }
    )
    return org_id


async def update_organization(org_id: str, *, name: str, description: str, status: str) -> None:
    await db.table("organizations").where("id", org_id).patch(
        {"name": name, "description": description or None, "status": status}
    )


async def delete_organization(org_id: str) -> None:
    await db.table("organizations").where("id", org_id).delete()
