"""Business logic for analyst notes."""

from __future__ import annotations

from app.features.analysis import notes_repository


class NoteError(Exception):
    pass


async def save_note(
    *,
    case_id: str,
    evidence_id: str,
    module_id: str,
    author_id: str,
    body: str,
) -> str:
    body = (body or "").strip()
    if not body:
        raise NoteError("Note body cannot be empty.")
    if len(body) > 20_000:
        raise NoteError("Note exceeds maximum length.")
    return await notes_repository.upsert_note(
        case_id=case_id,
        evidence_id=evidence_id,
        module_id=module_id,
        author_id=author_id,
        body=body,
    )


async def get_note(*, evidence_id: str, module_id: str, author_id: str) -> dict | None:
    return await notes_repository.get_note(
        evidence_id=evidence_id,
        module_id=module_id,
        author_id=author_id,
    )


async def list_notes_for_evidence(evidence_id: str) -> list[dict]:
    return await notes_repository.list_notes_for_evidence(evidence_id)
