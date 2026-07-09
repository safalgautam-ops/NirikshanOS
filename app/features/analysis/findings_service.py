"""Business logic for case findings and indicators of compromise."""

from __future__ import annotations

from app.features.analysis import findings_repository

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}
_VALID_CONFIDENCES = {"low", "medium", "high"}
_VALID_IOC_TYPES = {"ip", "domain", "url", "hash", "email", "filename", "registry", "other"}


class FindingError(Exception):
    pass


def _severity(value: str) -> str:
    v = value.lower() if value else "medium"
    return v if v in _VALID_SEVERITIES else "medium"


def _confidence(value: str) -> str:
    v = value.lower() if value else "medium"
    return v if v in _VALID_CONFIDENCES else "medium"


async def create_finding(
    *,
    case_id: str,
    evidence_id: str | None,
    module_id: str | None,
    author_id: str,
    title: str,
    description: str,
    severity: str = "medium",
    confidence: str = "medium",
    source_evidence: str | None = None,
    source_module: str | None = None,
) -> str:
    title = (title or "").strip()
    description = (description or "").strip()
    if not title:
        raise FindingError("Finding title is required.")
    if not description:
        raise FindingError("Finding description is required.")
    return await findings_repository.create_finding(
        case_id=case_id,
        evidence_id=evidence_id or None,
        module_id=module_id or None,
        author_id=author_id,
        title=title[:255],
        description=description,
        severity=_severity(severity),
        confidence=_confidence(confidence),
        source_evidence=(source_evidence or "")[:255] or None,
        source_module=(source_module or "")[:255] or None,
    )


async def list_findings(case_id: str) -> list[dict]:
    return await findings_repository.list_findings(case_id)


async def create_indicator(
    *,
    case_id: str,
    evidence_id: str | None,
    module_id: str | None,
    author_id: str,
    ioc_type: str,
    value: str,
    severity: str = "medium",
    confidence: str = "medium",
    source_evidence: str | None = None,
    source_module: str | None = None,
) -> str | None:
    ioc_type = (ioc_type or "").lower().strip()
    value = (value or "").strip()
    if not ioc_type:
        raise FindingError("Indicator type is required.")
    if not value:
        raise FindingError("Indicator value is required.")
    if ioc_type not in _VALID_IOC_TYPES:
        ioc_type = "other"
    return await findings_repository.create_indicator(
        case_id=case_id,
        evidence_id=evidence_id or None,
        module_id=module_id or None,
        author_id=author_id,
        ioc_type=ioc_type,
        value=value[:2048],
        severity=_severity(severity),
        confidence=_confidence(confidence),
        source_evidence=(source_evidence or "")[:255] or None,
        source_module=(source_module or "")[:255] or None,
    )


async def list_indicators(case_id: str) -> list[dict]:
    return await findings_repository.list_indicators(case_id)
