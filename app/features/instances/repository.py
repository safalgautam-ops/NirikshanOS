"""DB access for the instances table (registered container runtimes)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.db.orm import db


async def list_instances() -> list[dict]:
    return await (
        db.table("instances")
        .order_by("display_name", "asc")
        .all(allow_full_table=True)
    )


async def list_active_instances() -> list[dict]:
    return await (
        db.table("instances")
        .where("is_active", 1)
        .order_by("display_name", "asc")
        .all(allow_full_table=True)
    )


async def list_ready_instances() -> list[dict]:
    """Active instances whose image has actually been confirmed built
    (`docker image inspect` succeeded — see workers/worker_main.py's
    _check_instance_image). Used everywhere a module is about to be run
    (assignment dropdowns, Test) so a not-built instance is never offered
    or executed against."""
    return await (
        db.table("instances")
        .where("is_active", 1)
        .where("image_status", "ready")
        .order_by("display_name", "asc")
        .all(allow_full_table=True)
    )


async def get_instance(instance_id: str) -> dict | None:
    return await db.table("instances").where("id", instance_id).first()


async def get_instance_by_image_tag(image_tag: str) -> dict | None:
    return await db.table("instances").where("image_tag", image_tag).first()


async def create_instance(
    *,
    instance_id: str,
    display_name: str,
    image_tag: str,
    cpu_limit: str,
    memory_limit: str,
    pids_limit: int,
    queue_name: str,
    default_timeout_seconds: int,
    created_by: str,
) -> None:
    await db.table("instances").create({
        "id":                      instance_id,
        "display_name":            display_name,
        "image_tag":               image_tag,
        "cpu_limit":               cpu_limit,
        "memory_limit":            memory_limit,
        "pids_limit":              pids_limit,
        "queue_name":              queue_name,
        "default_timeout_seconds": default_timeout_seconds,
        "created_by":              created_by,
    })


async def update_instance(
    instance_id: str,
    *,
    display_name: str,
    image_tag: str,
    cpu_limit: str,
    memory_limit: str,
    pids_limit: int,
    queue_name: str,
    default_timeout_seconds: int,
    is_active: bool,
) -> None:
    await db.table("instances").where("id", instance_id).update({
        "display_name":            display_name,
        "image_tag":               image_tag,
        "cpu_limit":               cpu_limit,
        "memory_limit":            memory_limit,
        "pids_limit":              pids_limit,
        "queue_name":              queue_name,
        "default_timeout_seconds": default_timeout_seconds,
        "is_active":               int(is_active),
        # Image identity may have changed — status is stale until rechecked.
        "image_status":            "unknown",
    })


async def delete_instance(instance_id: str) -> None:
    await db.table("instances").where("id", instance_id).delete()


async def set_image_status(instance_id: str, status: str) -> None:
    await (
        db.table("instances")
        .where("id", instance_id)
        .update({"image_status": status, "image_checked_at": datetime.now(timezone.utc)})
    )
