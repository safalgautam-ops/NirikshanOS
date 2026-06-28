"""Audit feed for the case workspace's Activity tab.

1. Writes case-related audit events using record_case_activity() for mutations
2. Reads and formats those events using get_case_activity_log()
"""

from __future__ import annotations

import json

# shared audit logger: instead of writing directly to the database, this file calls the audit logger to record events
from app.core.audit import logger as audit_logger

# constants to define the internal action names that get stored in the audit logs(database)
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

# converts internal action names to human-readable labels for display in the audit log(ui)
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
}

# Matches the status values the activity_row macro in cases/detail.html
# already renders (success -> green/"Completed", failure -> red/"Failed").
_STATUS_LABELS = {"success": "Completed", "failure": "Failed"}


# defines an async function to record case activity in the audit log
async def record_case_activity(
    *,
    case_id: str,  # id of the case being audited
    actor_id: str | None,  # id of the actor performing the action
    action: str,  # the action being performed
    status: str = "success",  # the status of the action
    ip_address: str | None = None,  # the IP address of the actor
    target_label: str | None = None,  # the label of the target object
    metadata: dict | None = None,  # additional metadata
) -> None:
    """
    every audit row created by this function is scoped to the case being audited
    it uses: entity_type="case", entity_id=case_id since the activity tab is for the whole case

    If a user uploads evidence, the audit log still belongs to the case
    The specific evidence file can be stored inside metadata.
    Example: metadata={"evidence_file": "path/to/evidence.pdf"}

    The generic audit log table only has one entity reference: entity_type and entity_id
    So the code uses that one reference to link the audit log to the case
    """
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


async def get_case_activity_log(case_id: str, *, limit: int = 200) -> list[dict]:
    rows = await audit_logger.list_entity_events("case", case_id, limit=limit)
    formatted = []
    for row in rows:
        metadata = row.get("metadata") or {}
        # The driver only auto-decodes JSON columns selected plainly - once
        # they're pulled in via a joined `table.*` (see list_entity_events),
        # it comes back as a raw JSON string instead.
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
