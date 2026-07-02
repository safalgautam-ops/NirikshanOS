# check whether the user is allowed to run selected modules
"""Analysis policy engine: decides whether a user may run a set of modules
against a given evidence file.

This sits between routes.py (which enforces case-level row access and
authentication) and service.py (which knows about module compatibility).
Routes.py calls check_can_run after confirming the user can *see* the
evidence; this layer answers "can they *run* analysis against it?"

Checks performed, in order:
  1. module exists
  2. module enabled
  3. module is compatible with the evidence type
  4. user holds the EVIDENCE_ANALYZE org permission
  5. user's plan covers the module's required_plan tier  <- stub (no plan table yet)
  6. user's quota has capacity                           <- stub (no quota table yet)

Stubs 5 and 6 always pass. They are explicit stubs, not dead code: the
logic skeleton is here so wiring in real plan/quota data later is a
one-function change, not an architectural addition.
"""

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
    """Check whether `user_id` (a member of `org_id`) may run every module
    in `module_ids` against an evidence file of `evidence_type`.

    `org_id` is required even though the current permission check resolves
    the org internally via user membership — plan tier and quota are both
    org-level, so every downstream check needs it.

    The case-level row access check (is this user a case member / can they
    see this evidence?) is the caller's responsibility — routes.py does it
    via _require_visible_case before calling here.
    """
    violations: list[PolicyViolation] = []

    # --- check 4: org permission (once, not per module) ---
    granted = await get_user_org_permission_names(user_id)
    if EVIDENCE_ANALYZE.name not in granted:
        # Short-circuit: no point checking module details if the user
        # isn't allowed to run analysis at all.
        return PolicyResult(
            allowed=False,
            violations=[
                PolicyViolation(
                    module_id="*",
                    reason="You do not have permission to run analysis modules.",
                )
            ],
        )

    for module_id in module_ids:
        # --- check 1: exists ---
        module = get_module(module_id)
        if module is None:
            violations.append(
                PolicyViolation(
                    module_id=module_id, reason=f"Module '{module_id}' does not exist."
                )
            )
            continue

        # --- check 2: enabled ---
        if not module.enabled:
            violations.append(
                PolicyViolation(
                    module_id=module_id,
                    reason=f"Module '{module.name}' is not currently available.",
                )
            )
            continue

        # --- check 3: evidence type compatibility ---
        if not is_module_compatible(module, evidence_type):
            violations.append(
                PolicyViolation(
                    module_id=module_id,
                    reason=f"Module '{module.name}' does not support {evidence_type!r} evidence.",
                )
            )
            continue

        # --- check 5: plan tier (stub) ---
        # No plan column exists on users or organizations yet. When a plan
        # system is added, replace this with a real lookup:
        #   user_plan = await get_user_plan(user_id)
        #   if not _plan_covers(user_plan, module.required_plan): ...
        _plan_violation = _check_plan_stub(org_id, module_id, module.required_plan)
        if _plan_violation:
            violations.append(_plan_violation)
            continue

        # --- check 6: quota (stub) ---
        # No quota table exists yet. When added, replace with:
        #   remaining = await get_remaining_quota(org_id)
        #   if remaining <= 0: ...
        # IMPORTANT: real quota check should happen AFTER the planner runs,
        # not here per-module. Batching changes how many fast/standard/heavy/
        # sandbox jobs are actually consumed — 6 batchable modules may cost
        # only 1 fast_queue slot, not 6. Policy pre-flight only validates
        # permission and module access; quota is a post-plan concern.
        _quota_violation = _check_quota_stub(org_id, module_id)
        if _quota_violation:
            violations.append(_quota_violation)
            continue

    return PolicyResult(allowed=len(violations) == 0, violations=violations)


# ---------------------------------------------------------------------------
# Stubs for plan + quota — always pass until those systems are built
# ---------------------------------------------------------------------------

_PLAN_ORDER: list[str] = ["free", "analyst", "advanced"]


def _check_plan_stub(org_id: str, module_id: str, required_plan: str) -> PolicyViolation | None:
    return None


def _check_quota_stub(org_id: str, module_id: str) -> PolicyViolation | None:
    return None
