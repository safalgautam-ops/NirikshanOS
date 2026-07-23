"""Audit feed for the case workspace's Activity tab."""

from __future__ import annotations

import json

from app.core.audit import logger as audit_logger

CASE_CREATED = "case.created"
CASE_UPDATED = "case.updated"
CASE_DELETED = "case.deleted"
EVIDENCE_UPLOADED = "evidence.uploaded"
EVIDENCE_UPLOAD_FAILED = "evidence.upload_failed"
EVIDENCE_HASHED = "evidence.hashed"
EVIDENCE_DELETED = "evidence.deleted"
MEMBER_ADDED = "member.added"
MEMBER_REMOVED = "member.removed"
TIMELINE_ITEM_ADDED = "timeline_item.added"
TIMELINE_ITEM_UPDATED = "timeline_item.updated"
REPORT_SAVED = "report.saved"
NOTE_SAVED = "note.saved"

ACTION_LABELS = {
    CASE_CREATED: "Case created",
    CASE_UPDATED: "Case updated",
    CASE_DELETED: "Case deleted",
    EVIDENCE_UPLOADED: "Evidence uploaded",
    EVIDENCE_UPLOAD_FAILED: "Evidence upload failed",
    EVIDENCE_HASHED: "Hash generated",
    EVIDENCE_DELETED: "Evidence deleted",
    MEMBER_ADDED: "Member added",
    MEMBER_REMOVED: "Member removed",
    TIMELINE_ITEM_ADDED: "Timeline item added",
    TIMELINE_ITEM_UPDATED: "Timeline item updated",
    REPORT_SAVED: "Report saved",
    NOTE_SAVED: "Note saved",
}

_STATUS_LABELS = {"success": "Completed", "failure": "Failed"}


async def record_case_activity(
    *,
    case_id: str,
    actor_id: str | None,
    action: str,
    status: str = "success",
    ip_address: str | None = None,
    target_label: str | None = None,
    metadata: dict | None = None,
) -> None:
    """every audit row created by this function is scoped to the case being audited it uses: entity_type="case", entity_id=case_id since the activity tab is for the whole case"""
    full_metadata = dict(metadata or {})
    if target_label is not None:
        full_metadata["label"] = target_label
    await audit_logger.log_event(
        actor_id=actor_id,
        action=action,
        entity_type="case",
        entity_id=case_id,
        status=status,
        ip_address=ip_address,
        metadata=full_metadata or None,
    )


def _format_rows(rows: list[dict]) -> list[dict]:
    formatted = []
    for row in rows:
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        formatted.append(
            {
                "timestamp": row["created_at"],
                "actor": row["actor_name"] or "Unknown user",
                "action": ACTION_LABELS.get(row["action"], row["action"]),
                "target": metadata.get("label", "—"),
                "status": _STATUS_LABELS.get(row["status"], row["status"]),
            }
        )
    return formatted


async def get_case_activity_log(case_id: str, *, limit: int = 200) -> list[dict]:
    rows = await audit_logger.list_entity_events("case", case_id, limit=limit)
    return _format_rows(rows)


async def get_activity_log_for_cases(case_ids: list[str], *, limit: int = 20) -> list[dict]:
    """Merged, newest-first activity feed across several cases at once - the dashboard's Recent Activity widget, scoped to whichever cases the viewer can already see (see cases/service.py's list_cases_for_user)."""
    rows = await audit_logger.list_events_for_entities("case", case_ids, limit=limit)
    return _format_rows(rows)
