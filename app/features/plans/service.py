"""Plans business logic — subscription assignment and Redis-cached access checks."""
from __future__ import annotations

import json

from app.extensions import get_redis
from app.features.plans import repository

# Canonical tier order — matches the `tier` column in analysis_module_defs.
# Plans declare which of these tiers their subscribers may access.
KNOWN_TIERS: list[str] = ["free", "basic_triage", "standard", "advanced", "enterprise"]

_SUB_CACHE_TTL = 300  # 5 minutes — acceptable lag for admin plan changes


async def get_active_subscription(org_id: str) -> dict | None:
    """Return the active subscription for an org, Redis-cached for 5 minutes."""
    r = get_redis()
    key = f"nirikshan:sub:{org_id}"
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached) if cached != "null" else None
    sub = await repository.get_active_subscription_db(org_id)
    payload = json.dumps(sub, default=str) if sub else "null"
    await r.set(key, payload, ex=_SUB_CACHE_TTL)
    return sub


async def invalidate_subscription_cache(org_id: str) -> None:
    r = get_redis()
    await r.delete(f"nirikshan:sub:{org_id}")


async def assign_plan(
    *,
    org_id: str,
    plan_id: str,
    billing_period: str,
    ends_at: str | None,
    notes: str | None,
    created_by: str,
) -> str:
    plan = await repository.get_plan(plan_id)
    if plan is None:
        raise ValueError(f"Plan '{plan_id}' not found.")

    # Cancel any existing active subscription before creating the new one.
    existing = await repository.get_active_subscription_db(org_id)
    if existing:
        await repository.cancel_subscription(existing["id"])

    # Snapshot the full plan at subscription time — immutable after this point.
    # If the plan is later edited or deleted, this org's access stays as-was
    # until ends_at (grandfathering).
    snapshot = {
        "id":            plan["id"],
        "display_name":  plan["display_name"],
        "resources":     plan["resources"],
        "allowed_tiers": plan["allowed_tiers"],
        "price_monthly": str(plan["price_monthly"]),
        "price_annual":  str(plan["price_annual"]),
    }

    sub_id = await repository.create_subscription(
        org_id=org_id,
        plan_id=plan_id,
        plan_snapshot=snapshot,
        billing_period=billing_period,
        ends_at=ends_at or None,
        notes=notes,
        created_by=created_by,
    )
    await invalidate_subscription_cache(org_id)
    return sub_id


async def cancel_subscription(sub_id: str, org_id: str) -> None:
    await repository.cancel_subscription(sub_id)
    await invalidate_subscription_cache(org_id)


def get_allowed_tiers(sub: dict | None) -> list[str]:
    """Return the tier list from a subscription snapshot, or free defaults if no sub."""
    if sub is None:
        return ["free", "basic_triage"]
    snapshot = sub.get("plan_snapshot") or {}
    tiers = snapshot.get("allowed_tiers", [])
    if isinstance(tiers, str):
        try:
            tiers = json.loads(tiers)
        except Exception:
            tiers = []
    tiers = tiers if isinstance(tiers, list) else ["free", "basic_triage"]
    return tiers if tiers else ["free"]
