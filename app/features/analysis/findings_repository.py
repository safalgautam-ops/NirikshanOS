"""Raw DB access for case findings and indicators of compromise."""

from __future__ import annotations

import hashlib

try:
    from asyncmy.errors import IntegrityError as _IntegrityError
except ImportError:
    _IntegrityError = Exception  # type: ignore[misc,assignment]

from app.core.db.orm import db
from app.core.utils.ids import new_id


def _indicator_hash(case_id: str, ioc_type: str, value: str) -> str:
    return hashlib.sha256(f"{case_id}|{ioc_type}|{value}".encode()).hexdigest()


# ── Findings ─────────────────────────────────────────────────────────────────

async def create_finding(
    *,
    case_id: str,
    evidence_id: str | None,
    module_id: str | None,
    author_id: str,
    title: str,
    description: str,
    severity: str,
    confidence: str,
    source_evidence: str | None,
    source_module: str | None,
) -> str:
    finding_id = new_id()
    await db.table("case_findings").create({
        "id": finding_id,
        "case_id": case_id,
        "evidence_id": evidence_id,
        "module_id": module_id,
        "author_id": author_id,
        "title": title,
        "description": description,
        "severity": severity,
        "confidence": confidence,
        "source_evidence": source_evidence,
        "source_module": source_module,
    })
    return finding_id


async def list_findings(case_id: str) -> list[dict]:
    return await (
        db.table("case_findings")
        .where("case_id", case_id)
        .order_by("created_at", "asc")
        .all(allow_full_table=True)
    )


async def mark_finding_included(case_id: str, finding_id: str) -> int:
    return await (
        db.table("case_findings")
        .where("id", finding_id)
        .where("case_id", case_id)
        .update({"included_in_report": 1})
    )


# ── Indicators ────────────────────────────────────────────────────────────────

async def create_indicator(
    *,
    case_id: str,
    evidence_id: str | None,
    module_id: str | None,
    author_id: str,
    ioc_type: str,
    value: str,
    severity: str,
    confidence: str,
    source_evidence: str | None,
    source_module: str | None,
) -> str | None:
    """Returns the new indicator ID, or None if the (case, type, value) already exists.

    Handles concurrent duplicate inserts safely: the DB UNIQUE constraint is the
    authoritative dedup guard; the pre-check is a fast-path only. An IntegrityError
    from a race is treated the same as finding an existing row.
    """
    value_hash = _indicator_hash(case_id, ioc_type, value)
    existing = await (
        db.table("case_indicators")
        .where("value_hash", value_hash)
        .first()
    )
    if existing:
        return None
    indicator_id = new_id()
    try:
        await db.table("case_indicators").create({
            "id": indicator_id,
            "case_id": case_id,
            "evidence_id": evidence_id,
            "module_id": module_id,
            "author_id": author_id,
            "ioc_type": ioc_type,
            "value": value,
            "value_hash": value_hash,
            "severity": severity,
            "confidence": confidence,
            "source_evidence": source_evidence,
            "source_module": source_module,
        })
    except _IntegrityError:
        return None
    return indicator_id


async def list_indicators(case_id: str) -> list[dict]:
    return await (
        db.table("case_indicators")
        .where("case_id", case_id)
        .order_by("created_at", "asc")
        .all(allow_full_table=True)
    )


async def mark_indicator_included(case_id: str, indicator_id: str) -> int:
    return await (
        db.table("case_indicators")
        .where("id", indicator_id)
        .where("case_id", case_id)
        .update({"included_in_report": 1})
    )
