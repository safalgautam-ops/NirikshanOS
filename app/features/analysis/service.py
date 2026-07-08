"""Analysis module business logic: which modules exist, which ones are
compatible with a given evidence type, and validating an analyst's module
selection before it's handed off to a job.

This is the read side of the registry only. It answers "what modules exist,
which evidence types support them, which plan/queue/image will run them,
can they be batched, which parser reads their output" - it never runs
anything. Execution is a later phase, built on top of this registry by
analysis_planner / job_service / worker_service / docker_runner /
result_parser - none of which exist yet.
"""

from __future__ import annotations

from app.features.analysis.module_registry import (
    MODULES,
    EVIDENCE_TYPES,
    AnalysisModule,
    ModuleTier,
    detect_evidence_type_from_filename,
)


class AnalysisError(Exception):
    """A user-visible analysis-selection failure - safe to display directly."""


def list_modules() -> list[AnalysisModule]:
    return [module for module in MODULES.values() if module.enabled]


def get_module(module_id: str) -> AnalysisModule | None:
    return MODULES.get(module_id)


def is_module_compatible(module: AnalysisModule, evidence_type: str) -> bool:
    """Whether `module` may run against an evidence file of `evidence_type`.

    Generic modules ("*" in supported_types, or category == "generic")
    always match. For everything else, the module must explicitly list the
    evidence type.

    Files we couldn't classify at all (evidence_type == "unknown") are
    deliberately narrower: only generic modules and modules that explicitly
    opted into "unknown" match. Without this, memory/disk/mobile modules
    would also show up for an unclassified file just because the
    evidence_type happens to be the string "unknown" - which is exactly
    the wrong call for a forensic tool (you don't get to run a Volatility
    plugin against a file you can't even identify).
    """
    if "*" in module.supported_types or module.category == "generic":
        return True
    if evidence_type == "unknown":
        return "unknown" in module.supported_types
    return evidence_type in module.supported_types


def get_compatible_modules(evidence_type: str) -> list[AnalysisModule]:
    return [
        module
        for module in MODULES.values()
        if module.enabled and is_module_compatible(module, evidence_type)
    ]


def validate_selected_modules(module_ids: list[str], evidence_type: str) -> list[AnalysisModule]:
    """Validates that every selected module exists, is enabled, and is
    actually compatible with this evidence's type - raises AnalysisError
    (not a bare ValueError) so routes.py can turn it into a clean 400."""
    selected: list[AnalysisModule] = []
    for module_id in module_ids:
        module = get_module(module_id)
        if module is None:
            raise AnalysisError(f"Module '{module_id}' does not exist.")
        if not module.enabled:
            raise AnalysisError(f"Module '{module.name}' is not enabled.")
        if not is_module_compatible(module, evidence_type):
            raise AnalysisError(f"Module '{module.name}' does not support this evidence type.")
        selected.append(module)
    return selected


def group_modules_by_tier(modules: list[AnalysisModule]) -> dict[ModuleTier, list[AnalysisModule]]:
    """Groups modules the same way the Analyze dialog displays them - by
    execution tier (Basic Triage Bundle, Network Modules, Memory Modules,
    etc.) rather than by evidence-type category."""
    grouped: dict[ModuleTier, list[AnalysisModule]] = {}
    for module in modules:
        grouped.setdefault(module.tier, []).append(module)
    return grouped


def group_batchable_modules(modules: list[AnalysisModule]) -> list[dict]:
    """Groups batchable modules by batch_group, but only when every module
    in that group truly shares the same queue/runtime/isolation - the
    actual contract batching requires (same evidence file, same container).
    Non-batchable modules each get their own single-module group so callers
    can treat the return value as "the full execution plan's grouping"
    rather than having to special-case ungrouped modules separately."""
    groups: dict[str, list[AnalysisModule]] = {}
    standalone: list[AnalysisModule] = []
    for module in modules:
        if module.batchable and module.batch_group:
            groups.setdefault(module.batch_group, []).append(module)
        else:
            standalone.append(module)

    result: list[dict] = []
    for batch_group, group_modules in groups.items():
        result.append(
            {
                "batch_group": batch_group,
                "batchable": True,
                "queue_name": group_modules[0].queue_name,
                "runtime_image": group_modules[0].runtime_image,
                "isolation_level": group_modules[0].isolation_level,
                "modules": group_modules,
            }
        )
    for module in standalone:
        result.append(
            {
                "batch_group": None,
                "batchable": False,
                "queue_name": module.queue_name,
                "runtime_image": module.runtime_image,
                "isolation_level": module.isolation_level,
                "modules": [module],
            }
        )
    return result


def detect_evidence_type(evidence: dict) -> str:
    """The evidence_type to use for compatibility checks: prefers a real
    detected type on the evidence row, falls back to filename-extension
    guessing, and finally "unknown". `evidence` doesn't currently carry a
    `detected_type` column (see migrations/008.cases.sql /
    migrations/009.object_storage.sql) - `.get(...)` keeps this forward
    compatible with adding one later without this function needing to
    change."""
    detected_type = evidence.get("detected_type")
    if detected_type and detected_type in EVIDENCE_TYPES:
        return detected_type
    filename = evidence.get("filename") or ""
    return detect_evidence_type_from_filename(filename)


def serialize_module(module: AnalysisModule) -> dict:
    """Frontend-safe module JSON - no raw command templates, host paths,
    internal parser import paths, or other backend-only execution details."""
    return {
        "id": module.id,
        "name": module.name,
        "category": module.category,
        "tool": module.tool,
        "description": module.description,
        "output_type": module.output_type,
        "supported_types": module.supported_types,
        "required_plan": module.required_plan,
        "queue_name": module.queue_name,
        "container_tier": module.container_tier,
        "batchable": module.batchable,
        "batch_group": module.batch_group,
        "timeout_seconds": module.timeout_seconds,
        "estimated_runtime": module.estimated_runtime,
        "risk_level": module.risk_level,
        "isolation_level": module.isolation_level,
        "tier": module.tier,
        "fields": [
            {
                "key": option.key,
                "label": option.label,
                "type": option.type,
                "default": option.default,
                "options": option.options,
            }
            for option in module.fields
        ],
        "enabled": module.enabled,
    }
