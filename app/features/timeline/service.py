"""Manual investigation timeline business logic: per-type field validation
and the Timeline Center's per-case summary counts.

This is deliberately NOT gated by an org permission the way evidence
upload/delete is (see app/features/cases/permissions.py) - a task/note/
milestone is the analyst's own day-to-day investigation record, not a
management action over the case itself. The same row-level case-access
check used for *viewing* a case (see cases/service.py.can_access_case) is
treated as sufficient authorization to read and maintain its timeline too;
routes.py is the one place that enforces it, same split as everywhere else.
"""

from __future__ import annotations

from datetime import date, datetime

from app.features.timeline import repository
from app.features.timeline.choices import ITEM_TYPES, NOTE_VISIBILITIES, TASK_PRIORITIES, TASK_STATUSES

_ITEM_TYPE_VALUES = {value for value, _label in ITEM_TYPES}
_TASK_STATUS_VALUES = {value for value, _label in TASK_STATUSES}
_TASK_PRIORITY_VALUES = {value for value, _label in TASK_PRIORITIES}
_NOTE_VISIBILITY_VALUES = {value for value, _label in NOTE_VISIBILITIES}


class TimelineError(Exception):
    """A user-visible timeline failure - safe to display directly."""


def _require_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise TimelineError("Title is required.")
    return title


def _parse_timeline_time(value: str) -> datetime:
    """Defaults to right now if left blank - every dialog pre-fills this
    field, but a missing/blank submission shouldn't be a hard error."""
    value = (value or "").strip()
    if not value:
        return datetime.now()
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")  # <input type="datetime-local">
    except ValueError:
        raise TimelineError("Enter a valid timeline date/time.")


def _parse_due_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise TimelineError("Enter a valid due date.")


def _type_specific_fields(
    item_type: str,
    *,
    status: str,
    priority: str,
    assigned_to: str,
    due_date: str,
    linked_evidence_id: str,
    linked_result_label: str,
    visibility: str,
) -> dict:
    if item_type == "task":
        if status not in _TASK_STATUS_VALUES:
            raise TimelineError("Select a valid task status.")
        if priority not in _TASK_PRIORITY_VALUES:
            raise TimelineError("Select a valid task priority.")
        return {
            "status": status,
            "priority": priority,
            "assigned_to": assigned_to or None,
            "due_date": _parse_due_date(due_date),
            "linked_evidence_id": linked_evidence_id or None,
            "linked_result_label": (linked_result_label or "").strip() or None,
        }
    if item_type == "note":
        if visibility not in _NOTE_VISIBILITY_VALUES:
            raise TimelineError("Select a valid visibility.")
        return {"visibility": visibility}
    return {}  # milestone needs nothing beyond the shared fields


async def create_item(
    *,
    case_id: str,
    item_type: str,
    title: str,
    description: str,
    timeline_time: str,
    created_by: str,
    status: str = "",
    priority: str = "",
    assigned_to: str = "",
    due_date: str = "",
    linked_evidence_id: str = "",
    linked_result_label: str = "",
    visibility: str = "",
) -> str:
    if item_type not in _ITEM_TYPE_VALUES:
        raise TimelineError("Select a valid item type.")
    fields = _type_specific_fields(
        item_type,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        due_date=due_date,
        linked_evidence_id=linked_evidence_id,
        linked_result_label=linked_result_label,
        visibility=visibility,
    )
    return await repository.create_timeline_item(
        case_id=case_id,
        item_type=item_type,
        title=_require_title(title),
        description=(description or "").strip() or None,
        timeline_time=_parse_timeline_time(timeline_time),
        created_by=created_by,
        **fields,
    )


async def update_item(
    item_id: str,
    *,
    item_type: str,
    title: str,
    description: str,
    timeline_time: str,
    status: str = "",
    priority: str = "",
    assigned_to: str = "",
    due_date: str = "",
    linked_evidence_id: str = "",
    linked_result_label: str = "",
    visibility: str = "",
) -> None:
    fields = _type_specific_fields(
        item_type,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        due_date=due_date,
        linked_evidence_id=linked_evidence_id,
        linked_result_label=linked_result_label,
        visibility=visibility,
    )
    fields.update(
        title=_require_title(title),
        description=(description or "").strip() or None,
        timeline_time=_parse_timeline_time(timeline_time),
    )
    await repository.update_timeline_item(item_id, fields)


async def get_item(item_id: str):
    return await repository.get_timeline_item(item_id)


async def list_items(case_id: str) -> list:
    return await repository.list_timeline_items(case_id)


async def case_timeline_summaries(cases: list) -> list[dict]:
    """Annotates each case with its timeline counts + last-updated time for
    the Timeline Center's cards - one bulk query across every visible case,
    aggregated here in Python rather than a COUNT-per-card SQL query (same
    approach already used for evidence counts on the case detail page)."""
    items = await repository.list_items_for_cases([c["id"] for c in cases])
    by_case: dict[str, list] = {}
    for item in items:
        by_case.setdefault(item["case_id"], []).append(item)

    summaries = []
    for case in cases:
        case_items = by_case.get(case["id"], [])
        last_item = max(case_items, key=lambda i: i["updated_at"], default=None)
        summaries.append(
            {
                **case,
                "total_items": len(case_items),
                "task_count": sum(1 for i in case_items if i["type"] == "task"),
                "note_count": sum(1 for i in case_items if i["type"] == "note"),
                "milestone_count": sum(1 for i in case_items if i["type"] == "milestone"),
                "last_updated_at": last_item["updated_at"] if last_item else None,
                "last_updated_by": last_item["created_by_name"] if last_item else None,
            }
        )
    return summaries
