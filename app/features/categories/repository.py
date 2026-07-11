"""DB access for the categories table."""

from __future__ import annotations

from app.core.db.orm import db


async def list_categories() -> list[dict]:
    return await (
        db.table("categories")
        .order_by("sort_order", "asc")
        .order_by("name", "asc")
        .all(allow_full_table=True)
    )


async def get_category(category_id: str) -> dict | None:
    return await db.table("categories").where("id", category_id).first()


async def get_category_by_name(name: str) -> dict | None:
    return await db.table("categories").where("name", name).first()


async def create_category(
    *, category_id: str, name: str, description: str | None, sort_order: int
) -> None:
    await db.table("categories").create({
        "id": category_id,
        "name": name,
        "description": description,
        "sort_order": sort_order,
    })


async def update_category(
    category_id: str, *, name: str, description: str | None, sort_order: int
) -> None:
    await db.table("categories").where("id", category_id).update({
        "name": name,
        "description": description,
        "sort_order": sort_order,
    })


async def delete_category(category_id: str) -> None:
    await db.table("categories").where("id", category_id).delete()
