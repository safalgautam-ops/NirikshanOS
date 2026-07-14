"""DB access for plans and org_subscriptions."""
from __future__ import annotations

import json

from app.core.db.orm import db, raw_sql
from app.core.utils.ids import new_id


def _parse_plan(plan: dict) -> dict:
    """Parse JSON fields on a plan row so templates receive real dicts/lists."""
    if plan is None:
        return plan
    for field in ("resources", "allowed_tiers"):
        val = plan.get(field)
        if isinstance(val, str):
            try:
                plan[field] = json.loads(val)
            except Exception:
                plan[field] = {} if field == "resources" else []
    return plan


def _parse_sub(sub: dict) -> dict:
    """Parse JSON fields on a subscription row."""
    if sub is None:
        return sub
    val = sub.get("plan_snapshot")
    if isinstance(val, str):
        try:
            sub["plan_snapshot"] = json.loads(val)
        except Exception:
            sub["plan_snapshot"] = {}
    return sub


# ── Plans ─────────────────────────────────────────────────────────────────────

async def list_plans() -> list[dict]:
    rows = await (
        db.table("plans")
        .order_by("sort_order", "asc")
        .order_by("display_name", "asc")
        .all(allow_full_table=True)
    )
    plans = [_parse_plan(dict(r)) for r in rows]
    for plan in plans:
        plan["allowed_instance_ids"] = await get_instance_ids_for_plan(plan["id"])
    return plans


async def get_plan(plan_id: str) -> dict | None:
    row = await db.table("plans").where("id", plan_id).first()
    if not row:
        return None
    plan = _parse_plan(dict(row))
    plan["allowed_instance_ids"] = await get_instance_ids_for_plan(plan_id)
    return plan


async def get_free_plan() -> dict | None:
    """The active plan with zero cost — auto-assigned to a new org on
    creation. Looked up by cost rather than a hardcoded id so it still works
    if an admin renames/recreates the free-tier plan."""
    row = await (
        db.table("plans")
        .where("is_active", 1)
        .where("price_monthly", 0)
        .order_by("sort_order", "asc")
        .first()
    )
    if not row:
        return None
    plan = _parse_plan(dict(row))
    plan["allowed_instance_ids"] = await get_instance_ids_for_plan(plan["id"])
    return plan


async def create_plan(
    *,
    plan_id: str,
    display_name: str,
    description: str | None,
    price_monthly: float,
    price_annual: float,
    resources: dict,
    allowed_tiers: list[str],
    is_active: bool,
    sort_order: int,
) -> None:
    await db.table("plans").create({
        "id":            plan_id,
        "display_name":  display_name,
        "description":   description,
        "price_monthly": price_monthly,
        "price_annual":  price_annual,
        "resources":     json.dumps(resources),
        "allowed_tiers": json.dumps(allowed_tiers),
        "is_active":     int(is_active),
        "sort_order":    sort_order,
    })


async def update_plan(
    plan_id: str,
    *,
    display_name: str,
    description: str | None,
    price_monthly: float,
    price_annual: float,
    resources: dict,
    allowed_tiers: list[str],
    is_active: bool,
    sort_order: int,
) -> None:
    await db.table("plans").where("id", plan_id).update({
        "display_name":  display_name,
        "description":   description,
        "price_monthly": price_monthly,
        "price_annual":  price_annual,
        "resources":     json.dumps(resources),
        "allowed_tiers": json.dumps(allowed_tiers),
        "is_active":     int(is_active),
        "sort_order":    sort_order,
    })


async def get_instance_ids_for_plan(plan_id: str) -> list[str]:
    rows = await db.table("plan_instances").where("plan_id", plan_id).all(allow_full_table=True)
    return [r["instance_id"] for r in rows]


async def set_plan_instances(plan_id: str, instance_ids: list[str]) -> None:
    """Replace-all: same pattern update_plan already uses for allowed_tiers,
    just as real rows in a join table instead of a JSON column."""
    await db.table("plan_instances").where("plan_id", plan_id).delete()
    for instance_id in instance_ids:
        await db.table("plan_instances").create({"plan_id": plan_id, "instance_id": instance_id})


async def delete_plan(plan_id: str) -> None:
    # Existing active subscribers become grandfathered — they keep their snapshot.
    await (
        db.table("org_subscriptions")
        .where("plan_id", plan_id)
        .where("status", "active")
        .update({"status": "grandfathered"})
    )
    await db.table("plans").where("id", plan_id).delete()


# ── Subscriptions ─────────────────────────────────────────────────────────────

async def list_subscriptions() -> list[dict]:
    rows = await (
        db.table("org_subscriptions")
        .join("organizations", "org_subscriptions.org_id", "organizations.id")
        .select(
            "org_subscriptions.id",
            "org_subscriptions.org_id",
            "org_subscriptions.plan_id",
            "org_subscriptions.plan_snapshot",
            "org_subscriptions.status",
            "org_subscriptions.billing_period",
            "org_subscriptions.starts_at",
            "org_subscriptions.ends_at",
            "org_subscriptions.notes",
            "org_subscriptions.created_at",
            "organizations.name as org_name",
        )
        .order_by("org_subscriptions.created_at", "desc")
        .all(allow_full_table=True)
    )
    return [_parse_sub(dict(r)) for r in rows]


async def get_active_subscription_db(org_id: str) -> dict | None:
    row = await (
        db.table("org_subscriptions")
        .where("org_id", org_id)
        .where_in("status", ["active", "grandfathered"])
        .where_raw(raw_sql("(ends_at IS NULL OR ends_at > NOW())"))
        .order_by("created_at", "desc")
        .first()
    )
    return _parse_sub(dict(row)) if row else None


async def create_subscription(
    *,
    org_id: str,
    plan_id: str,
    plan_snapshot: dict,
    billing_period: str,
    ends_at: str | None,
    notes: str | None,
    created_by: str,
) -> str:
    sub_id = new_id()
    await db.table("org_subscriptions").create({
        "id":             sub_id,
        "org_id":         org_id,
        "plan_id":        plan_id,
        "plan_snapshot":  json.dumps(plan_snapshot, default=str),
        "status":         "active",
        "billing_period": billing_period,
        "ends_at":        ends_at,
        "notes":          notes,
        "created_by":     created_by,
    })
    return sub_id


async def cancel_subscription(sub_id: str) -> None:
    await db.table("org_subscriptions").where("id", sub_id).update({"status": "cancelled"})


async def update_subscription_snapshot(sub_id: str, plan_snapshot: dict) -> None:
    """Overwrite a subscription's frozen plan_snapshot in place — used to
    repair subscriptions whose snapshot predates a tier/instance vocabulary
    migration (grandfathering is meant to protect against routine admin plan
    edits, not leave a subscription permanently referencing tier names that
    no longer exist anywhere else in the system)."""
    await db.table("org_subscriptions").where("id", sub_id).update(
        {"plan_snapshot": json.dumps(plan_snapshot, default=str)}
    )
