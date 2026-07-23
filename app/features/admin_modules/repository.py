"""DB access for analysis_module_defs and module_files."""

from __future__ import annotations

from app.core.db.orm import db, raw_sql
from app.core.utils.ids import new_id


async def list_modules() -> list[dict]:
    """All modules, with their category/instance display info joined in — category_id/instance_id are FKs now, not free-text columns."""
    rows = await (
        db.table("analysis_module_defs")
        .left_join("categories", "analysis_module_defs.category_id", "categories.id")
        .left_join("instances", "analysis_module_defs.instance_id", "instances.id")
        .select(
            "analysis_module_defs.*",
            "categories.name as category_name",
            "instances.display_name as instance_display_name",
            "instances.image_tag as instance_image_tag",
        )
        .order_by("categories.sort_order", "asc")
        .order_by("analysis_module_defs.id", "asc")
        .all(allow_full_table=True)
    )
    for row in rows:
        row["category_name"] = row["category_name"] or "Uncategorized"
    return rows


async def get_module(module_id: str) -> dict | None:
    return await db.table("analysis_module_defs").where("id", module_id).first()


async def create_custom_module(
    *,
    module_id: str,
    display_name: str,
    description: str | None,
    category_id: str | None,
    tier: str,
    instance_id: str | None,
    created_by: str,
) -> None:
    await db.table("analysis_module_defs").create(
        {
            "id": module_id,
            "display_name": display_name,
            "description": description,
            "category_id": category_id,
            "tier": tier,
            "instance_id": instance_id,
            "timeout_seconds": 120,
            "is_enabled": 0,
            "status": "published",
            "source": "custom",
            "created_by": created_by,
        }
    )


async def delete_module(module_id: str) -> None:
    """Deletes the module definition - module_files and module_test_runs cascade automatically (fk_module_files_module/fk_module_test_runs_module are both ON DELETE CASCADE)."""
    await db.table("analysis_module_defs").where("id", module_id).delete()


async def set_enabled(module_id: str, enabled: bool) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update({"is_enabled": int(enabled)})


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
    await db.table("module_files").create(
        {
            "id": file_id,
            "module_id": module_id,
            "filename": filename,
            "content": content,
            "is_entry_point": int(is_entry_point),
        }
    )
    return file_id


async def update_file_content(file_id: str, content: str) -> None:
    await db.table("module_files").where("id", file_id).update({"content": content})


async def delete_file(file_id: str) -> None:
    await db.table("module_files").where("id", file_id).delete()


async def set_entry_point(module_id: str, file_id: str) -> None:
    await db.table("module_files").where("id", file_id).update({"is_entry_point": 1})
    await (
        db.table("module_files")
        .where("module_id", module_id)
        .where_raw(raw_sql(f"id <> '{file_id}'"))
        .update({"is_entry_point": 0})
    )


async def update_module_meta(
    module_id: str,
    *,
    display_name: str,
    description: str | None,
    category_id: str | None,
    tier: str,
    instance_id: str | None,
) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update(
        {
            "display_name": display_name,
            "description": description,
            "category_id": category_id,
            "tier": tier,
            "instance_id": instance_id,
        }
    )


async def save_options_schema(module_id: str, schema_json: str) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update({"options_schema": schema_json})


async def save_pipeline(module_id: str, pipeline_json: str | None) -> None:
    await db.table("analysis_module_defs").where("id", module_id).update({"pipeline_spec": pipeline_json})


async def create_test_run(*, module_id: str, instance_id: str, s3_key: str, created_by: str) -> str:
    run_id = new_id()
    await db.table("module_test_runs").create(
        {
            "id": run_id,
            "module_id": module_id,
            "instance_id": instance_id,
            "s3_key": s3_key,
            "status": "queued",
            "created_by": created_by,
        }
    )
    return run_id


async def get_test_run(run_id: str) -> dict | None:
    return await db.table("module_test_runs").where("id", run_id).first()


async def update_test_run_status(
    run_id: str,
    status: str,
    *,
    error_message: str | None = None,
    result_json: str | None = None,
) -> None:
    data: dict = {"status": status}
    if error_message is not None:
        data["error_message"] = error_message
    if result_json is not None:
        data["result_json"] = result_json
    if status in ("completed", "failed"):
        from datetime import datetime, timezone

        data["finished_at"] = datetime.now(timezone.utc)
    await db.table("module_test_runs").where("id", run_id).update(data)
