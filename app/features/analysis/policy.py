"""Analysis policy engine: decides whether a user may run a set of modules."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.security.org_permissions import get_user_org_permission_names
from app.features.analysis.service import get_module, is_module_compatible
from app.features.cases.permissions import EVIDENCE_ANALYZE
from app.features.instances import repository as instances_repository
from app.features.plans.service import get_active_subscription, get_allowed_instance_ids, get_allowed_tiers


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

    sub = await get_active_subscription(org_id)
    allowed_tiers = get_allowed_tiers(sub)
    allowed_instance_ids = get_allowed_instance_ids(sub)
    plan_name = (sub["plan_snapshot"].get("display_name", "your plan")
                 if sub and isinstance(sub.get("plan_snapshot"), dict)
                 else "Free")

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
        if not mod.get("instance_id"):
            violations.append(PolicyViolation(
                module_id=module_id,
                reason=f"Module '{mod['display_name']}' has no instance assigned yet — an admin needs to configure it.",
            ))
            continue
        instance = await instances_repository.get_instance(mod["instance_id"])
        if not instance or not instance["is_active"]:
            violations.append(PolicyViolation(
                module_id=module_id,
                reason=f"Module '{mod['display_name']}' is assigned to an instance that no longer exists or is inactive.",
            ))
            continue
        if instance["image_status"] != "ready":
            violations.append(PolicyViolation(
                module_id=module_id,
                reason=f"Module '{mod['display_name']}' cannot run — its instance '{instance['display_name']}' has not been built yet.",
            ))
            continue
        tier = mod.get("tier") or "free"
        if tier not in allowed_tiers:
            violations.append(PolicyViolation(
                module_id=module_id,
                reason=f"Module '{mod['display_name']}' requires a higher plan. Current: {plan_name}.",
            ))
            continue
        if mod["instance_id"] not in allowed_instance_ids:
            violations.append(PolicyViolation(
                module_id=module_id,
                reason=f"Module '{mod['display_name']}' requires an instance not included in your plan. Current: {plan_name}.",
            ))

    return PolicyResult(allowed=len(violations) == 0, violations=violations)
