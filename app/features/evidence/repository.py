"""DB access for evidence - the per-file rows tracked through an S3
multipart upload's lifecycle (init, in-progress, completed/failed/
cancelled). MinIO itself is the source of truth for which parts have
actually landed (see app/core/object_storage.list_parts) - this table only
tracks what the DB needs to know: status, the s3 key/upload id, and the
final hash/size once complete."""

from __future__ import annotations

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def create_evidence(
    *,
    case_id: str,
    filename: str,
    size_bytes: int,
    s3_key: str,
    upload_id: str,
    part_size: int,
    total_parts: int,
    uploaded_by: str,
) -> str:
    evidence_id = new_id()
    await db.table("evidence").create(
        {
            "id": evidence_id,
            "case_id": case_id,
            "filename": filename,
            "size_bytes": size_bytes,
            "status": "uploading",
            "received_bytes": 0,
            "s3_key": s3_key,
            "upload_id": upload_id,
            "part_size": part_size,
            "total_parts": total_parts,
            "uploaded_by": uploaded_by,
        }
    )
    return evidence_id


async def get_evidence(evidence_id: str):
    return await db.table("evidence").where("id", evidence_id).first()


async def list_case_evidence(case_id: str) -> list:
    """Joins in the uploader's name for display (Evidences/Analyze tabs'
    "Uploaded By" field) - evidence itself only stores uploaded_by as a
    user id."""
    return await (
        db.table("evidence")
        .join("user", "evidence.uploaded_by", "user.id")
        .where("evidence.case_id", case_id)
        .order_by("evidence.uploaded_at", "DESC")
        .select("evidence.*", "user.name as uploaded_by_name")
        .all(allow_full_table=True)
    )


async def set_status(evidence_id: str, status: str) -> None:
    await db.table("evidence").where("id", evidence_id).patch({"status": status})


async def set_received_bytes(evidence_id: str, received_bytes: int) -> None:
    await db.table("evidence").where("id", evidence_id).patch({"received_bytes": received_bytes})


async def mark_completed(evidence_id: str, *, size_bytes: int, mime_type: str) -> None:
    """Flips status to completed and clears upload_id - the multipart
    session is gone once CompleteMultipartUpload succeeds. sha256/md5 land
    later via set_hash, once the background hashing task finishes (the app
    never sees the bytes during a presigned-PUT upload, so it can't hash
    inline the way the old local-disk reassembly did)."""
    await (
        db.table("evidence")
        .where("id", evidence_id)
        .patch(
            {
                "status": "completed",
                "upload_id": None,
                "size_bytes": size_bytes,
                "received_bytes": size_bytes,
                "mime_type": mime_type,
            }
        )
    )


async def set_hash(evidence_id: str, *, sha256: str, md5: str) -> None:
    await db.table("evidence").where("id", evidence_id).patch({"sha256": sha256, "md5": md5})


async def mark_failed(evidence_id: str) -> None:
    await db.table("evidence").where("id", evidence_id).patch({"status": "failed"})


async def delete_evidence(evidence_id: str) -> None:
    await db.table("evidence").where("id", evidence_id).delete()
