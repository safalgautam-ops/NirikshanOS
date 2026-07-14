"""
Generic audit-log writer - the one place that inserts into `audit_logs`.

This logger is domain-agnostic and should be used by any feature that needs to log audit events.

"""

from __future__ import annotations

import json

from app.core.db.orm import db
from app.core.utils.ids import new_id


# async helper function that writes an audit log entry to the database
async def log_event(
    *,
    actor_id: str | None,
    action: str,
    entity_type: str | None = None,  # type of thing affected by the action
    entity_id: str | None = None,  # id of the thing affected by the action
    status: str = "success",  # success or failure
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> None:  # starts an asynchronous task to write the log entry
    await db.table("audit_logs").create(
        {
            "id": new_id(),
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": status,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": json.dumps(metadata) if metadata is not None else None,
        }
    )


async def list_entity_events(
    entity_type: str, entity_id: str, *, limit: int = 200
) -> list:
    """fetches audit log events for one specific entity (e.g. one case), newest first, with the
    actor's current name joined in - actor_id goes NULL (not the row) if
    that account is later deleted, see audit_logs' actor_fk.
    """
    return (
        await db.table("audit_logs")
        .left_join("user", "audit_logs.actor_id", "user.id")
        .where("audit_logs.entity_type", entity_type)
        .where("audit_logs.entity_id", entity_id)
        .order_by("audit_logs.created_at", "DESC")
        .select("audit_logs.*", "user.name as actor_name")
        .limit(limit)
        .all()
    )


async def list_events_for_entities(
    entity_type: str, entity_ids: list[str], *, limit: int = 200
) -> list:
    """Same as list_entity_events, but across several entities at once (e.g.
    every case a dashboard viewer can see) instead of one - used to build a
    single merged recent-activity feed without one query per entity."""
    if not entity_ids:
        return []
    return (
        await db.table("audit_logs")
        .left_join("user", "audit_logs.actor_id", "user.id")
        .where("audit_logs.entity_type", entity_type)
        .where_in("audit_logs.entity_id", entity_ids)
        .order_by("audit_logs.created_at", "DESC")
        .select("audit_logs.*", "user.name as actor_name")
        .limit(limit)
        .all()
    )
