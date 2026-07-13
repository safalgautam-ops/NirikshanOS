"""DB access for payment_transactions, coupons, org_discounts, coupon_redemptions."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.db.orm import db
from app.core.utils.ids import new_id


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------

async def list_coupons() -> list[dict]:
    return await db.table("coupons").order_by("created_at", "desc").all(allow_full_table=True)


async def get_coupon(coupon_id: str) -> dict | None:
    return await db.table("coupons").where("id", coupon_id).first()


async def get_coupon_by_code(code: str) -> dict | None:
    return await db.table("coupons").where("code", code).first()


async def get_valid_coupon(code: str) -> dict | None:
    """A coupon usable right now: active, within its validity window, and
    (if it has a redemption cap) not yet exhausted. All three checks done
    here so callers never have to re-derive "is this coupon usable"."""
    coupon = await get_coupon_by_code(code)
    if not coupon or not coupon["is_active"]:
        return None
    now = datetime.now(timezone.utc)
    if coupon["valid_from"] and coupon["valid_from"].replace(tzinfo=timezone.utc) > now:
        return None
    if coupon["valid_until"] and coupon["valid_until"].replace(tzinfo=timezone.utc) < now:
        return None
    if coupon["max_redemptions"] is not None and coupon["times_redeemed"] >= coupon["max_redemptions"]:
        return None
    return coupon


async def create_coupon(
    *,
    code: str,
    discount_type: str,
    discount_value: float,
    max_redemptions: int | None,
    valid_from: str | None,
    valid_until: str | None,
    is_active: bool,
    created_by: str,
) -> str:
    coupon_id = new_id()
    await db.table("coupons").create({
        "id": coupon_id,
        "code": code,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "max_redemptions": max_redemptions,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "is_active": int(is_active),
        "created_by": created_by,
    })
    return coupon_id


async def update_coupon(
    coupon_id: str,
    *,
    discount_type: str,
    discount_value: float,
    max_redemptions: int | None,
    valid_from: str | None,
    valid_until: str | None,
    is_active: bool,
) -> None:
    await db.table("coupons").where("id", coupon_id).update({
        "discount_type": discount_type,
        "discount_value": discount_value,
        "max_redemptions": max_redemptions,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "is_active": int(is_active),
    })


async def delete_coupon(coupon_id: str) -> None:
    await db.table("coupons").where("id", coupon_id).delete()


async def record_coupon_redemption(*, coupon_id: str, org_id: str, transaction_id: str) -> None:
    await db.table("coupon_redemptions").create({
        "id": new_id(),
        "coupon_id": coupon_id,
        "org_id": org_id,
        "transaction_id": transaction_id,
    })
    # .update() always binds values as plain parameters (see orm.py) — no
    # raw "col + 1" expression support — so this increments in Python. Coupon
    # redemption isn't a hot path and per-org re-redemption is already
    # blocked by has_org_redeemed_coupon, so the narrow race window on a
    # shared multi-use coupon's counter is an acceptable tradeoff here.
    coupon = await get_coupon(coupon_id)
    if coupon:
        await db.table("coupons").where("id", coupon_id).update({
            "times_redeemed": coupon["times_redeemed"] + 1,
        })


async def has_org_redeemed_coupon(coupon_id: str, org_id: str) -> bool:
    row = await (
        db.table("coupon_redemptions")
        .where("coupon_id", coupon_id)
        .where("org_id", org_id)
        .first()
    )
    return row is not None


# ---------------------------------------------------------------------------
# Org discounts
# ---------------------------------------------------------------------------

async def get_org_discount(discount_id: str) -> dict | None:
    return await db.table("org_discounts").where("id", discount_id).first()


async def list_org_discounts() -> list[dict]:
    return await (
        db.table("org_discounts")
        .join("organizations", "org_discounts.org_id", "organizations.id")
        .select("org_discounts.*", "organizations.name as org_name")
        .order_by("org_discounts.created_at", "desc")
        .all(allow_full_table=True)
    )


async def get_active_org_discount(org_id: str) -> dict | None:
    now = datetime.now(timezone.utc)
    rows = await (
        db.table("org_discounts")
        .where("org_id", org_id)
        .where("is_active", 1)
        .all(allow_full_table=True)
    )
    for row in rows:
        if row["valid_until"] and row["valid_until"].replace(tzinfo=timezone.utc) < now:
            continue
        return row
    return None


async def create_org_discount(
    *,
    org_id: str,
    discount_type: str,
    discount_value: float,
    reason: str | None,
    valid_until: str | None,
    is_active: bool,
    created_by: str,
) -> str:
    discount_id = new_id()
    await db.table("org_discounts").create({
        "id": discount_id,
        "org_id": org_id,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "reason": reason,
        "valid_until": valid_until,
        "is_active": int(is_active),
        "created_by": created_by,
    })
    return discount_id


async def update_org_discount(
    discount_id: str,
    *,
    discount_type: str,
    discount_value: float,
    reason: str | None,
    valid_until: str | None,
    is_active: bool,
) -> None:
    await db.table("org_discounts").where("id", discount_id).update({
        "discount_type": discount_type,
        "discount_value": discount_value,
        "reason": reason,
        "valid_until": valid_until,
        "is_active": int(is_active),
    })


async def delete_org_discount(discount_id: str) -> None:
    await db.table("org_discounts").where("id", discount_id).delete()


# ---------------------------------------------------------------------------
# Payment transactions
# ---------------------------------------------------------------------------

async def list_transactions(*, org_id: str | None = None, status: str | None = None) -> list[dict]:
    query = (
        db.table("payment_transactions")
        .join("organizations", "payment_transactions.org_id", "organizations.id")
        .join("plans", "payment_transactions.plan_id", "plans.id")
        .select(
            "payment_transactions.*",
            "organizations.name as org_name",
            "plans.display_name as plan_name",
        )
    )
    if org_id:
        query = query.where("payment_transactions.org_id", org_id)
    if status:
        query = query.where("payment_transactions.status", status)
    return await query.order_by("payment_transactions.created_at", "desc").all(allow_full_table=True)


async def get_transaction_by_uuid(transaction_uuid: str) -> dict | None:
    return await db.table("payment_transactions").where("transaction_uuid", transaction_uuid).first()


async def create_transaction(
    *,
    org_id: str,
    plan_id: str,
    billing_period: str,
    base_amount: float,
    discount_amount: float,
    total_amount: float,
    transaction_uuid: str,
    coupon_id: str | None,
    org_discount_id: str | None,
    created_by: str,
) -> str:
    transaction_id = new_id()
    await db.table("payment_transactions").create({
        "id": transaction_id,
        "org_id": org_id,
        "plan_id": plan_id,
        "billing_period": billing_period,
        "base_amount": base_amount,
        "discount_amount": discount_amount,
        "total_amount": total_amount,
        "transaction_uuid": transaction_uuid,
        "coupon_id": coupon_id,
        "org_discount_id": org_discount_id,
        "status": "initiated",
        "created_by": created_by,
    })
    return transaction_id


async def mark_transaction_completed(transaction_id: str, *, esewa_transaction_code: str) -> None:
    await db.table("payment_transactions").where("id", transaction_id).update({
        "status": "completed",
        "esewa_transaction_code": esewa_transaction_code,
        "verified_at": datetime.now(timezone.utc),
    })


async def mark_transaction_failed(transaction_id: str, *, reason: str) -> None:
    await db.table("payment_transactions").where("id", transaction_id).update({
        "status": "failed",
        "failure_reason": reason,
    })
