"""Analysis policy engine: decides whether a user may run a set of modules."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.security.org_permissions import get_user_org_permission_names
from app.features.analysis.service import get_module, is_module_compatible
from app.features.cases.permissions import EVIDENCE_ANALYZE


@dataclass
class PolicyViolation:
    module_id: str
    reason: str


@dataclass
class PolicyResult:
    allowed: bool
    violations: list[PolicyViolation] = field(default_factory=list)

    def first_reason(self) -> str | None:
        return self.violations[0].reason if self.violations else None


async def check_can_run(
    org_id: str,
    user_id: str,
    module_ids: list[str],
    evidence_type: str,
) -> PolicyResult:
    violations: list[PolicyViolation] = []

    granted = await get_user_org_permission_names(user_id)
    if EVIDENCE_ANALYZE.name not in granted:
        return PolicyResult(
            allowed=False,
            violations=[PolicyViolation(
                module_id="*",
                reason="You do not have permission to run analysis modules.",
            )],
        )

    for module_id in module_ids:
        mod = await get_module(module_id)
        if mod is None:
            violations.append(PolicyViolation(module_id=module_id, reason=f"Module '{module_id}' does not exist."))
            continue
        if not mod["is_enabled"]:
            violations.append(PolicyViolation(module_id=module_id, reason=f"Module '{mod['display_name']}' is disabled."))
            continue
        if mod["status"] != "published":
            violations.append(PolicyViolation(module_id=module_id, reason=f"Module '{mod['display_name']}' is not published."))
            continue
        if not is_module_compatible(mod, evidence_type):
            violations.append(PolicyViolation(
                module_id=module_id,
                reason=f"Module '{mod['display_name']}' does not support {evidence_type!r} evidence.",
            ))
            continue

        # Plan tier stub — replace with real org plan lookup when billing is built.
        _plan_violation = _check_plan_stub(org_id, module_id, mod["tier"])
        if _plan_violation:
            violations.append(_plan_violation)
            continue

    return PolicyResult(allowed=len(violations) == 0, violations=violations)


def _check_plan_stub(org_id: str, module_id: str, tier: str) -> PolicyViolation | None:
    return None
