"""DB access for analysis_module_defs."""

from __future__ import annotations

from app.core.db.orm import db


async def list_modules() -> list[dict]:
    return await (
        db.table("analysis_module_defs")
        .order_by("category", "asc")
        .order_by("id", "asc")
        .all(allow_full_table=True)
    )


async def get_module(module_id: str) -> dict | None:
    return await db.table("analysis_module_defs").where("id", module_id).first()


async def upsert_module(
    *,
    module_id: str,
    display_name: str,
    description: str | None,
    category: str,
    tier: str,
    runtime_image: str,
    is_enabled: bool,
    yaml_definition: str | None,
    source: str,
    created_by: str | None = None,
) -> None:
    existing = await get_module(module_id)
    data: dict = {
        "display_name": display_name,
        "description": description,
        "category": category,
        "tier": tier,
        "runtime_image": runtime_image,
        "is_enabled": int(is_enabled),
        "yaml_definition": yaml_definition,
        "source": source,
    }
    if existing:
        await db.table("analysis_module_defs").where("id", module_id).update(data)
    else:
        await db.table("analysis_module_defs").create({**data, "id": module_id, "created_by": created_by})


async def set_enabled(module_id: str, enabled: bool) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update(
        {"is_enabled": int(enabled)}
    )


async def save_yaml(module_id: str, yaml_definition: str) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update(
        {"yaml_definition": yaml_definition, "source": "custom"}
    )


async def delete_module(module_id: str) -> None:
    await db.table("analysis_module_defs").where("id", module_id).delete()
