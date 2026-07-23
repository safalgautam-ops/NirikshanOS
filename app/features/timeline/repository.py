"""DB access for the manual investigation timeline - thin wrappers around the ORM, no business rules (see service.py for validation/access checks)."""

from __future__ import annotations

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def create_timeline_item(
    *,
    case_id: str,
    item_type: str,
    title: str,
    description: str | None,
    timeline_time,
    created_by: str,
    status: str | None = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    due_date=None,
    linked_evidence_id: str | None = None,
    linked_result_label: str | None = None,
    visibility: str | None = None,
) -> str:
    item_id = new_id()
    await db.table("timeline_items").create(
        {
            "id": item_id,
            "case_id": case_id,
            "type": item_type,
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "assigned_to": assigned_to,
            "due_date": due_date,
            "linked_evidence_id": linked_evidence_id,
            "linked_result_label": linked_result_label,
            "visibility": visibility,
            "timeline_time": timeline_time,
            "created_by": created_by,
        }
    )
    return item_id


async def get_timeline_item(item_id: str):
    return await db.table("timeline_items").where("id", item_id).first()


async def update_timeline_item(item_id: str, fields: dict) -> None:
    await db.table("timeline_items").where("id", item_id).patch(fields)


async def list_timeline_items(case_id: str) -> list:
    """Every item for one case, oldest first (chronological log), with the assignee/creator names and linked evidence's filename joined in so the template never has to issue its own lookups."""
    return await (
        db.table("timeline_items")
        .left_join("user", "timeline_items.assigned_to", "assignee.id", alias="assignee")
        .left_join("user", "timeline_items.created_by", "creator.id", alias="creator")
        .left_join("evidence", "timeline_items.linked_evidence_id", "evidence.id")
        .where("timeline_items.case_id", case_id)
        .order_by("timeline_items.timeline_time", "ASC")
        .select(
            "timeline_items.*",
            "assignee.name as assigned_to_name",
            "creator.name as created_by_name",
            "evidence.filename as linked_evidence_filename",
        )
        .all(allow_full_table=True)
    )


async def list_items_for_cases(case_ids: list[str]) -> list:
    """Every timeline item across a set of cases, unsorted - used purely to compute the Timeline Center's per-case counts/last-updated in Python rather than a SQL aggregate (same approach this app already uses for evidence counts on the case detail page)."""
    if not case_ids:
        return []
    return await (
        db.table("timeline_items")
        .left_join("user", "timeline_items.created_by", "user.id")
        .where_in("timeline_items.case_id", case_ids)
        .select(
            "timeline_items.case_id",
            "timeline_items.type",
            "timeline_items.updated_at",
            "user.name as created_by_name",
        )
        .all(allow_full_table=True)
    )
