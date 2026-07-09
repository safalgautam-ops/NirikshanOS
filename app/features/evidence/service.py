"""Evidence business logic: S3 multipart upload lifecycle (init, part-URL
issuance, resume-state via ListParts, finalize) plus pause/resume/cancel -
the pieces behind the file table's progress/pause/play/delete actions.

MinIO is the source of truth for "which parts have arrived" - there's no
parallel DB ledger to keep in sync (see app/core/object_storage.list_parts).
Pausing/resuming never touches MinIO at all: the multipart session simply
sits open until finalized or aborted, so these two are pure DB/UI state for
the audit trail, not upload-protocol operations.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import mimetypes

from app.config import Config
from app.core import object_storage, storage
from app.core.utils.ids import new_id
from app.features.audit import service as audit_service
from app.features.evidence import repository

# S3/MinIO requires every part except the last to be at least 5MB - this
# default is well above that and keeps a multi-GB evidence file from
# needing thousands of parts.
DEFAULT_PART_SIZE = 32 * 1024 * 1024

_BUCKET = Config.MINIO_BUCKET_PRIVATE


class EvidenceError(Exception):
    """A user-visible evidence failure - safe to display directly."""


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _guess_mime_type(extension: str) -> str:
    guessed, _ = mimetypes.guess_type(f"file.{extension}" if extension else "file")
    return guessed or "application/octet-stream"


async def init_upload(*, case_id: str, filename: str, size_bytes: int, uploaded_by: str) -> dict:
    filename = (filename or "").strip()
    if not filename:
        raise EvidenceError("A file name is required.")
    if size_bytes <= 0:
        raise EvidenceError("File appears to be empty.")
    if size_bytes > storage.MAX_EVIDENCE_SIZE_BYTES:
        raise EvidenceError(
            f"Evidence files must be smaller than {storage.MAX_EVIDENCE_SIZE_BYTES // (1024**3)}GB."
        )

    total_parts = math.ceil(size_bytes / DEFAULT_PART_SIZE)
    extension = _extension(filename)
    s3_key = f"evidence/{case_id}/{new_id()}{f'.{extension}' if extension else ''}"
    upload_id = await object_storage.create_multipart_upload(
        _BUCKET, s3_key, _guess_mime_type(extension)
    )
    evidence_id = await repository.create_evidence(
        case_id=case_id,
        filename=filename,
        size_bytes=size_bytes,
        s3_key=s3_key,
        upload_id=upload_id,
        part_size=DEFAULT_PART_SIZE,
        total_parts=total_parts,
        uploaded_by=uploaded_by,
    )
    return {"evidence_id": evidence_id, "total_parts": total_parts, "part_size": DEFAULT_PART_SIZE}


async def get_part_upload_url(evidence_id: str, part_number: int) -> str:
    """A presigned PUT for one part - the browser sends that part's bytes
    straight to MinIO with this, the app never sees them. Several of these
    can be requested and used concurrently, which is what makes parallel
    part upload possible."""
    evidence = await repository.get_evidence(evidence_id)
    if not evidence:
        raise EvidenceError("Evidence not found.")
    if evidence["status"] != "uploading":
        raise EvidenceError("This upload can no longer accept parts.")
    if not (1 <= part_number <= evidence["total_parts"]):
        raise EvidenceError("Part number out of range.")
    return await object_storage.presigned_part_url(
        _BUCKET, evidence["s3_key"], evidence["upload_id"], part_number
    )


async def get_upload_state(evidence_id: str) -> dict:
    """Resume's ground truth: asks MinIO itself which parts exist (rather
    than trusting any client-side record) and updates received_bytes to
    match, so a client that reloads mid-upload can diff against this and
    only request what's actually still missing."""
    evidence = await repository.get_evidence(evidence_id)
    if not evidence:
        raise EvidenceError("Evidence not found.")

    received_part_numbers: list[int] = []
    received_bytes = evidence["received_bytes"]
    if evidence["upload_id"]:
        parts = await object_storage.list_parts(_BUCKET, evidence["s3_key"], evidence["upload_id"])
        received_part_numbers = sorted(p["part_number"] for p in parts)
        received_bytes = sum(p["size"] for p in parts)
        await repository.set_received_bytes(evidence_id, received_bytes)

    return {
        "status": evidence["status"],
        "total_parts": evidence["total_parts"],
        "part_size": evidence["part_size"],
        "received_part_numbers": received_part_numbers,
        "received_bytes": received_bytes,
        "size_bytes": evidence["size_bytes"],
    }


async def finalize_upload(evidence_id: str) -> dict:
    evidence = await repository.get_evidence(evidence_id)
    if not evidence:
        raise EvidenceError("Evidence not found.")
    if not evidence["upload_id"]:
        raise EvidenceError("This upload was already finalized.")

    parts = await object_storage.list_parts(_BUCKET, evidence["s3_key"], evidence["upload_id"])
    received = {p["part_number"] for p in parts}
    expected = set(range(1, evidence["total_parts"] + 1))
    if received != expected:
        missing = sorted(expected - received)
        raise EvidenceError(f"Upload incomplete - missing {len(missing)} part(s).")

    try:
        size_bytes = await object_storage.complete_multipart_upload(
            _BUCKET, evidence["s3_key"], evidence["upload_id"]
        )
    except Exception as exc:
        await repository.mark_failed(evidence_id)
        raise EvidenceError(f"Failed to complete upload: {exc}") from exc

    mime_type = _guess_mime_type(_extension(evidence["filename"]))
    await repository.mark_completed(evidence_id, size_bytes=size_bytes, mime_type=mime_type)
    asyncio.create_task(
        _hash_evidence(evidence_id, evidence["s3_key"], evidence["case_id"], evidence["uploaded_by"], evidence["filename"])
    )
    return {"status": "completed", "size_bytes": size_bytes, "filename": evidence["filename"]}


async def _hash_evidence(evidence_id: str, s3_key: str, case_id: str, uploaded_by: str, filename: str) -> None:
    """Background sha256/md5 fill-in. The app never sees evidence's raw
    bytes during upload (presigned-PUT goes straight browser-to-MinIO), so
    the only way to hash it is to stream it back after the fact via
    GetObject. This is a stopgap — hashing belongs in a dedicated worker
    job eventually, not an in-process asyncio task.

    This is the one audit-log write that happens from service.py rather
    than routes.py: it runs in a detached background task with no HTTP
    request behind it by the time it finishes, so there's no routes.py
    call site to log from - the uploader is attributed as the actor since
    hashing is just a continuation of their upload."""
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    async for chunk in object_storage.stream_object(_BUCKET, s3_key):
        sha256.update(chunk)
        md5.update(chunk)
    await repository.set_hash(evidence_id, sha256=sha256.hexdigest(), md5=md5.hexdigest())
    await audit_service.record_case_activity(
        case_id=case_id,
        actor_id=uploaded_by,
        action=audit_service.EVIDENCE_HASHED,
        target_label=filename,
    )


async def pause_upload(evidence_id: str) -> None:
    """UI/audit state only - MinIO doesn't need to be told anything, since
    pausing is just the client stopping part requests on its own."""
    evidence = await repository.get_evidence(evidence_id)
    if not evidence:
        raise EvidenceError("Evidence not found.")
    if evidence["status"] not in ("uploading", "paused"):
        raise EvidenceError("Only an in-progress upload can be paused.")
    await repository.set_status(evidence_id, "paused")


async def resume_upload(evidence_id: str) -> None:
    evidence = await repository.get_evidence(evidence_id)
    if not evidence:
        raise EvidenceError("Evidence not found.")
    if evidence["status"] != "paused":
        raise EvidenceError("Only a paused upload can be resumed.")
    await repository.set_status(evidence_id, "uploading")


async def cancel_or_delete(evidence_id: str) -> dict:
    evidence = await repository.get_evidence(evidence_id)
    if not evidence:
        raise EvidenceError("Evidence not found.")
    if evidence["upload_id"]:
        await object_storage.abort_multipart_upload(_BUCKET, evidence["s3_key"], evidence["upload_id"])
    elif evidence["s3_key"]:
        await object_storage.delete_object(_BUCKET, evidence["s3_key"])
    await repository.delete_evidence(evidence_id)
    return {"filename": evidence["filename"]}


async def list_case_evidence(case_id: str):
    return await repository.list_case_evidence(case_id)


async def get_evidence(evidence_id: str):
    return await repository.get_evidence(evidence_id)
