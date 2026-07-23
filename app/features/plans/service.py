"""Plans business logic — subscription assignment and Redis-cached access checks."""

from __future__ import annotations

import json

from app.extensions import get_redis
from app.features.plans import repository

KNOWN_TIERS: list[str] = ["basic", "core_forensics", "specialized_forensics", "enterprise"]

_SUB_CACHE_TTL = 300


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


async def _build_plan_snapshot(plan: dict) -> dict:
    """Snapshot the full plan as of right now — immutable once written into a subscription."""
    return {
        "id": plan["id"],
        "display_name": plan["display_name"],
        "resources": plan["resources"],
        "allowed_tiers": plan["allowed_tiers"],
        "allowed_instance_ids": await repository.get_instance_ids_for_plan(plan["id"]),
        "price_monthly": str(plan["price_monthly"]),
        "price_annual": str(plan["price_annual"]),
    }


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

    existing = await repository.get_active_subscription_db(org_id)
    if existing:
        await repository.cancel_subscription(existing["id"])

    snapshot = await _build_plan_snapshot(plan)

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


async def refresh_subscription_snapshot(sub_id: str, *, org_id: str, plan_id: str) -> None:
    """Rebuild one subscription's plan_snapshot from the plan's current, live definition."""
    plan = await repository.get_plan(plan_id)
    if plan is None:
        raise ValueError(f"Plan '{plan_id}' not found.")
    snapshot = await _build_plan_snapshot(plan)
    await repository.update_subscription_snapshot(sub_id, snapshot)
    await invalidate_subscription_cache(org_id)


def get_allowed_tiers(sub: dict | None) -> list[str]:
    """Return the tier list from a subscription snapshot, or basic defaults if no sub."""
    if sub is None:
        return ["basic"]
    snapshot = sub.get("plan_snapshot") or {}
    tiers = snapshot.get("allowed_tiers", [])
    if isinstance(tiers, str):
        try:
            tiers = json.loads(tiers)
        except Exception:
            tiers = []
    tiers = tiers if isinstance(tiers, list) else ["basic"]
    return tiers if tiers else ["basic"]


def get_highest_allowed_tier(sub: dict | None) -> str:
    """The single highest tier a subscription grants, ranked by KNOWN_TIERS order — not by position in the allowed_tiers array."""
    tiers = get_allowed_tiers(sub)
    ranked = [t for t in KNOWN_TIERS if t in tiers]
    return ranked[-1] if ranked else "basic"


def get_allowed_instance_ids(sub: dict | None) -> list[str]:
    """Return the granted instance_id list from a subscription snapshot."""
    if sub is None:
        return []
    snapshot = sub.get("plan_snapshot") or {}
    ids = snapshot.get("allowed_instance_ids", [])
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except Exception:
            ids = []
    return ids if isinstance(ids, list) else []
