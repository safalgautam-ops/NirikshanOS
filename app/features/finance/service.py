"""Finance business logic — pricing, payment initiation, and the two-layer verification that must both pass before a plan is ever activated."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.core import esewa
from app.features.finance import repository
from app.features.plans import repository as plans_repository
from app.features.plans import service as plans_service


class PaymentError(Exception):
    """User-visible payment-flow failure — safe to surface as a 400."""


def _quantize(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _apply_discount(base_amount: Decimal, discount_type: str, discount_value) -> Decimal:
    value = Decimal(str(discount_value))
    if discount_type == "percent":
        discount = base_amount * value / Decimal("100")
    else:
        discount = value
    return min(discount, base_amount)


async def compute_total(*, plan: dict, billing_period: str, coupon_code: str | None, org_id: str) -> dict:
    """The one place price math happens."""
    if billing_period == "monthly":
        base_amount = _quantize(plan["price_monthly"])
    elif billing_period == "annual":
        base_amount = _quantize(plan["price_annual"])
    else:
        raise PaymentError(f"Invalid billing_period '{billing_period}'")

    candidates: list[tuple[Decimal, dict | None, dict | None]] = []

    if coupon_code:
        coupon = await repository.get_valid_coupon(coupon_code.strip())
        if not coupon:
            raise PaymentError("Coupon code is invalid, expired, or fully redeemed.")
        if await repository.has_org_redeemed_coupon(coupon["id"], org_id):
            raise PaymentError("This organization has already used that coupon.")
        discount = _apply_discount(base_amount, coupon["discount_type"], coupon["discount_value"])
        candidates.append((discount, coupon, None))

    org_discount = await repository.get_active_org_discount(org_id)
    if org_discount:
        discount = _apply_discount(base_amount, org_discount["discount_type"], org_discount["discount_value"])
        candidates.append((discount, None, org_discount))

    if candidates:
        discount_amount, coupon, org_discount = max(candidates, key=lambda c: c[0])
    else:
        discount_amount, coupon, org_discount = Decimal("0.00"), None, None

    total_amount = base_amount - discount_amount
    return {
        "base_amount": base_amount,
        "discount_amount": discount_amount,
        "total_amount": total_amount,
        "coupon": coupon,
        "org_discount": org_discount,
    }


async def initiate_payment(
    *,
    org_id: str,
    plan_id: str,
    billing_period: str,
    coupon_code: str | None,
    created_by: str,
    success_url: str,
    failure_url: str,
) -> dict:
    """Creates the `initiated` transaction row and returns the signed eSewa form fields the route renders as an auto-submitting form."""
    plan = await plans_repository.get_plan(plan_id)
    if plan is None:
        raise PaymentError(f"Plan '{plan_id}' not found.")

    pricing = await compute_total(
        plan=plan, billing_period=billing_period, coupon_code=coupon_code, org_id=org_id
    )
    if pricing["total_amount"] <= 0:
        raise PaymentError("This plan doesn't require payment. Please refresh the page and try again.")

    transaction_uuid = str(uuid.uuid4())
    transaction_id = await repository.create_transaction(
        org_id=org_id,
        plan_id=plan_id,
        billing_period=billing_period,
        base_amount=pricing["base_amount"],
        discount_amount=pricing["discount_amount"],
        total_amount=pricing["total_amount"],
        transaction_uuid=transaction_uuid,
        coupon_id=pricing["coupon"]["id"] if pricing["coupon"] else None,
        org_discount_id=pricing["org_discount"]["id"] if pricing["org_discount"] else None,
        created_by=created_by,
    )

    form_fields = esewa.build_payment_form_fields(
        total_amount=pricing["total_amount"],
        transaction_uuid=transaction_uuid,
        success_url=success_url,
        failure_url=failure_url,
    )
    return {
        "transaction_id": transaction_id,
        "form_action": esewa.form_url(),
        "form_fields": form_fields,
    }


def _compute_ends_at(billing_period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if billing_period == "annual":
        return now + timedelta(days=365)
    return now + timedelta(days=30)


async def handle_success_callback(raw_payload: str) -> tuple[bool, str]:
    """The two-layer verification from the plan: (1) regenerate the HMAC signature over the callback's own signed_field_names, (2) independently call eSewa's transaction-status endpoint."""
    payload = esewa.verify_callback(raw_payload)
    if payload is None:
        try:
            unverified = json.loads(base64.b64decode(raw_payload))
            unverified_uuid = unverified.get("transaction_uuid")
        except Exception:
            unverified_uuid = None
        if unverified_uuid:
            txn = await repository.get_transaction_by_uuid(unverified_uuid)
            if txn and txn["status"] == "initiated":
                await repository.mark_transaction_failed(txn["id"], reason="Signature verification failed")
        return False, "Payment verification failed."

    transaction_uuid = payload.get("transaction_uuid", "")
    txn = await repository.get_transaction_by_uuid(transaction_uuid)
    if not txn:
        return False, "Unknown transaction."
    if txn["status"] == "completed":
        return True, "Payment already processed."
    if txn["status"] != "initiated":
        return False, f"Transaction is already {txn['status']}."

    try:
        reported_amount = _quantize(payload.get("total_amount", "0"))
    except Exception:
        await repository.mark_transaction_failed(txn["id"], reason="Malformed total_amount in callback")
        return False, "Malformed payment amount."
    expected_amount = _quantize(txn["total_amount"])
    if reported_amount != expected_amount:
        await repository.mark_transaction_failed(
            txn["id"], reason=f"Amount mismatch: expected {expected_amount}, got {reported_amount}"
        )
        return False, "Payment amount did not match — rejected."

    if payload.get("status") != "COMPLETE":
        await repository.mark_transaction_failed(txn["id"], reason=f"eSewa status: {payload.get('status')}")
        return False, "Payment was not completed."

    live_status = await esewa.check_transaction_status(
        transaction_uuid=transaction_uuid, total_amount=txn["total_amount"]
    )
    if live_status != "COMPLETE":
        await repository.mark_transaction_failed(txn["id"], reason=f"Status check returned {live_status}")
        return False, "Payment could not be independently confirmed."

    await repository.mark_transaction_completed(
        txn["id"], esewa_transaction_code=payload.get("transaction_code", "")
    )
    if txn["coupon_id"]:
        await repository.record_coupon_redemption(
            coupon_id=txn["coupon_id"], org_id=txn["org_id"], transaction_id=txn["id"]
        )

    await plans_service.assign_plan(
        org_id=txn["org_id"],
        plan_id=txn["plan_id"],
        billing_period=txn["billing_period"],
        ends_at=_compute_ends_at(txn["billing_period"]),
        notes=f"Paid via eSewa — transaction_code {payload.get('transaction_code', '')}",
        created_by=txn["created_by"],
    )
    return True, "Payment successful — plan activated."


async def handle_failure_callback(transaction_uuid: str) -> None:
    txn = await repository.get_transaction_by_uuid(transaction_uuid)
    if txn and txn["status"] == "initiated":
        await repository.mark_transaction_failed(txn["id"], reason="Cancelled or failed at eSewa")
