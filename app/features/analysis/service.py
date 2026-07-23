"""Analysis module business logic — DB-driven. No hardcoded catalog."""

from __future__ import annotations

import json

from app.core.db.orm import db
from app.features.analysis.evidence_types import EVIDENCE_TYPES, detect_evidence_type_from_filename


class AnalysisError(Exception):
    """User-visible analysis-selection failure — safe to surface as a 400."""


async def list_modules() -> list[dict]:
    """All published, enabled modules, with category/instance display info joined in."""
    return await (
        db.table("analysis_module_defs")
        .left_join("categories", "analysis_module_defs.category_id", "categories.id")
        .left_join("instances", "analysis_module_defs.instance_id", "instances.id")
        .where("analysis_module_defs.status", "published")
        .where("analysis_module_defs.is_enabled", 1)
        .select(
            "analysis_module_defs.*",
            "categories.name as category_name",
            "instances.image_tag as runtime_image",
            "instances.queue_name as queue_name",
        )
        .order_by("categories.sort_order", "asc")
        .order_by("analysis_module_defs.display_name", "asc")
        .all(allow_full_table=True)
    )


async def get_module(module_id: str) -> dict | None:
    return await db.table("analysis_module_defs").where("id", module_id).first()


def is_module_compatible(module: dict, evidence_type: str) -> bool:
    raw = module.get("supported_types")
    supported: list[str] | None = json.loads(raw) if raw else None
    if not supported or "*" in supported:
        return True
    if evidence_type == "unknown":
        return "unknown" in supported
    return evidence_type in supported


async def get_compatible_modules(evidence_type: str) -> list[dict]:
    modules = await list_modules()
    return [m for m in modules if is_module_compatible(m, evidence_type)]


async def validate_selected_modules(module_ids: list[str], evidence_type: str) -> list[dict]:
    selected: list[dict] = []
    for mid in module_ids:
        mod = await get_module(mid)
        if mod is None:
            raise AnalysisError(f"Module '{mid}' does not exist.")
        if not mod["is_enabled"]:
            raise AnalysisError(f"Module '{mod['display_name']}' is not enabled.")
        if mod["status"] != "published":
            raise AnalysisError(f"Module '{mod['display_name']}' is not published.")
        if not is_module_compatible(mod, evidence_type):
            raise AnalysisError(
                f"Module '{mod['display_name']}' does not support {evidence_type!r} evidence."
            )
        selected.append(mod)
    return selected


def serialize_module(module: dict) -> dict:
    raw_st = module.get("supported_types")
    supported = json.loads(raw_st) if raw_st else ["*"]
    raw_schema = module.get("options_schema")
    fields: list[dict] = []
    if raw_schema:
        try:
            parsed = json.loads(raw_schema) if isinstance(raw_schema, str) else raw_schema
            if isinstance(parsed, list):
                fields = parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": module["id"],
        "name": module["display_name"],
        "category": module.get("category_name"),
        "description": module.get("description") or "",
        "supported_types": supported,
        "tier": module["tier"],
        "required_plan": module["tier"],
        "queue_name": module.get("queue_name"),
        "runtime_image": module.get("runtime_image"),
        "instance_id": module.get("instance_id"),
        "timeout_seconds": module["timeout_seconds"],
        "parser_name": module.get("parser_name") or "",
        "source": module["source"],
        "fields": fields,
    }


def detect_evidence_type(evidence: dict) -> str:
    detected = evidence.get("detected_type")
    if detected and detected in EVIDENCE_TYPES:
        return detected
    return detect_evidence_type_from_filename(evidence.get("filename") or "")
