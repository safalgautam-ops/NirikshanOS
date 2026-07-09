"""Raw DB access for analyst notes on analysis results."""

from __future__ import annotations

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def upsert_note(
    *,
    case_id: str,
    evidence_id: str,
    module_id: str,
    author_id: str,
    body: str,
) -> str:
    existing = await (
        db.table("analysis_notes")
        .where("evidence_id", evidence_id)
        .where("module_id", module_id)
        .where("author_id", author_id)
        .first()
    )
    if existing:
        await db.table("analysis_notes").where("id", existing["id"]).patch({"body": body})
        return existing["id"]
    note_id = new_id()
    await db.table("analysis_notes").create({
        "id": note_id,
        "case_id": case_id,
        "evidence_id": evidence_id,
        "module_id": module_id,
        "author_id": author_id,
        "body": body,
    })
    return note_id


async def get_note(
    *,
    evidence_id: str,
    module_id: str,
    author_id: str,
) -> dict | None:
    return await (
        db.table("analysis_notes")
        .where("evidence_id", evidence_id)
        .where("module_id", module_id)
        .where("author_id", author_id)
        .first()
    )


async def list_notes_for_evidence(evidence_id: str) -> list[dict]:
    return await (
        db.table("analysis_notes")
        .where("evidence_id", evidence_id)
        .all(allow_full_table=True)
    )
