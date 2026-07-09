"""DB access for analysis_module_defs and module_files."""

from __future__ import annotations

from app.core.db.orm import db, raw_sql
from app.core.utils.ids import new_id


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


async def delete_module(module_id: str) -> None:
    await db.table("analysis_module_defs").where("id", module_id).delete()


# ---------------------------------------------------------------------------
# Module files
# ---------------------------------------------------------------------------


async def list_files(module_id: str) -> list[dict]:
    return await (
        db.table("module_files")
        .where("module_id", module_id)
        .order_by("is_entry_point", "desc")
        .order_by("filename", "asc")
        .all(allow_full_table=True)
    )


async def get_file(file_id: str) -> dict | None:
    return await db.table("module_files").where("id", file_id).first()


async def create_file(
    module_id: str,
    filename: str,
    content: str = "",
    is_entry_point: bool = False,
) -> str:
    file_id = new_id()
    await db.table("module_files").create({
        "id":            file_id,
        "module_id":     module_id,
        "filename":      filename,
        "content":       content,
        "is_entry_point": int(is_entry_point),
    })
    return file_id


async def update_file_content(file_id: str, content: str) -> None:
    await db.table("module_files").where("id", file_id).update({"content": content})


async def delete_file(file_id: str) -> None:
    await db.table("module_files").where("id", file_id).delete()


async def set_entry_point(module_id: str, file_id: str) -> None:
    # Set new entry point first — if clearing others fails, at least one entry point exists.
    await db.table("module_files").where("id", file_id).update({"is_entry_point": 1})
    await (
        db.table("module_files")
        .where("module_id", module_id)
        .where_raw(raw_sql(f"id <> '{file_id}'"))
        .update({"is_entry_point": 0})
    )


async def save_options_schema(module_id: str, schema_json: str) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update(
        {"options_schema": schema_json}
    )
