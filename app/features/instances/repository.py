"""DB access for the instances table (registered container runtimes)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core import storage
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


async def get_usage_counts(instance_id: str) -> dict:
    """How many rows in each dependent table currently reference this
    instance - shown in the delete confirmation so an admin knows the
    blast radius before confirming, since two of these three references
    (modules, plan grants) change silently on delete (SET NULL / CASCADE)
    rather than blocking it. Only test_runs actually blocks deletion (see
    delete_view's ForeignKeyError handling) - surfaced here too so the
    confirmation dialog can explain why Delete might be refused."""
    modules = await (
        db.table("analysis_module_defs")
        .where("instance_id", instance_id)
        .count()
    )
    plans = await (
        db.table("plan_instances")
        .where("instance_id", instance_id)
        .count()
    )
    test_runs = await (
        db.table("module_test_runs")
        .where("instance_id", instance_id)
        .count()
    )
    return {"modules": modules, "plans": plans, "test_runs": test_runs}


async def clear_test_runs_for_instance(instance_id: str) -> int:
    """Deletes every module_test_runs row referencing this instance - the
    one reference that actually blocks instance deletion (module_test_runs
    has no ON DELETE rule, unlike plan_instances/analysis_module_defs which
    cascade/null out silently - see get_usage_counts). Best-effort deletes
    each run's uploaded sample file from object storage too, so clearing
    history doesn't leave orphaned files in MinIO. Returns how many rows
    were removed, for the confirmation UI to report back."""
    runs = await (
        db.table("module_test_runs")
        .where("instance_id", instance_id)
        .select("id", "s3_key")
        .all(allow_full_table=True)
    )
    for run in runs:
        if run["s3_key"]:
            await storage.delete_file(run["s3_key"])
    await db.table("module_test_runs").where("instance_id", instance_id).delete()
    return len(runs)


async def delete_instance(instance_id: str) -> None:
    await db.table("instances").where("id", instance_id).delete()


async def set_image_status(instance_id: str, status: str) -> None:
    await (
        db.table("instances")
        .where("id", instance_id)
        .update({"image_status": status, "image_checked_at": datetime.now(timezone.utc)})
    )
