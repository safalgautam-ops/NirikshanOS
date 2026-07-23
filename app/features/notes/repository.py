"""Raw DB access for the shared case notepad."""

from __future__ import annotations

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def get_case_note(case_id: str) -> dict | None:
    return await db.table("case_note").where("case_id", case_id).first()


async def upsert_case_note(case_id: str, content: str, editor_user_id: str) -> None:
    membership = await (
        db.table("case_members").where("case_id", case_id).where("user_id", editor_user_id).first()
    )
    member_id = membership["id"] if membership else None

    existing = await db.table("case_note").where("case_id", case_id).first()
    if existing:
        await db.table("case_note").where("case_id", case_id).update(
            {"content": content, "last_edited_by_member": member_id}
        )
    else:
        await db.table("case_note").create(
            {"case_id": case_id, "content": content, "last_edited_by_member": member_id}
        )
    await db.table("case_note_revisions").create(
        {"id": new_id(), "case_id": case_id, "content": content, "edited_by_member": member_id}
    )
