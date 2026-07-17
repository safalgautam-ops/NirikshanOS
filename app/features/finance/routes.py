"""Admin routes for the Finance area — transactions ledger, coupons, org discounts.
Mirrors the admin_instances/admin_categories blueprint shape added earlier."""

from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, render_template, request

from app.core.db.orm import db
from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.finance import repository
from app.features.finance.permissions import FINANCE_MANAGE, FINANCE_VIEW

finance_bp = Blueprint("finance", __name__, url_prefix="/admin/finance")

_DISCOUNT_TYPES = {"percent", "flat"}
_CODE_RE = re.compile(r"^[A-Z0-9_-]{3,64}$")


def _validate_discount_fields(body: dict) -> tuple[dict | None, str | None]:
    discount_type = (body.get("discount_type") or "").strip()
    if discount_type not in _DISCOUNT_TYPES:
        return None, f"discount_type must be one of {sorted(_DISCOUNT_TYPES)}"
    try:
        discount_value = float(body.get("discount_value"))
    except (TypeError, ValueError):
        return None, "discount_value must be a number"
    if discount_value <= 0:
        return None, "discount_value must be greater than 0"
    if discount_type == "percent" and discount_value > 100:
        return None, "A percent discount cannot exceed 100"
    return {"discount_type": discount_type, "discount_value": discount_value}, None


# ── Transactions (view-only ledger) ───────────────────────────────────────────

@finance_bp.route("/transactions")
@require_permission(FINANCE_VIEW)
async def transactions_view():
    org_id = request.args.get("org_id") or None
    status = request.args.get("status") or None
    transactions = await repository.list_transactions(org_id=org_id, status=status)
    orgs = await db.table("organizations").order_by("name", "asc").all(allow_full_table=True)
    visible_keys = await get_visible_nav_keys(g.user_id)
    return render_template(
        "admin/finance/transactions.html",
        transactions=transactions,
        orgs=orgs,
        selected_org_id=org_id,
        selected_status=status,
        visible_keys=visible_keys,
    )


# ── Coupons ────────────────────────────────────────────────────────────────────

@finance_bp.route("/coupons")
@require_permission(FINANCE_VIEW)
async def coupons_view():
    coupons = await repository.list_coupons()
    visible_keys = await get_visible_nav_keys(g.user_id)
    return render_template(
        "admin/finance/coupons.html", coupons=coupons, visible_keys=visible_keys
    )


@finance_bp.route("/coupons", methods=["POST"])
@require_permission(FINANCE_MANAGE)
async def create_coupon_view():
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip().upper()
    if not code or not _CODE_RE.match(code):
        return jsonify({"error": "Code must be 3-64 uppercase letters/numbers/hyphens/underscores"}), 400
    if await repository.get_coupon_by_code(code):
        return jsonify({"error": f"Coupon '{code}' already exists"}), 409
    fields, error = _validate_discount_fields(body)
    if error:
        return jsonify({"error": error}), 400
    max_redemptions = body.get("max_redemptions")
    coupon_id = await repository.create_coupon(
        code=code,
        max_redemptions=int(max_redemptions) if max_redemptions else None,
        valid_from=body.get("valid_from") or None,
        valid_until=body.get("valid_until") or None,
        is_active=bool(body.get("is_active", True)),
        created_by=g.user_id,
        **fields,
    )
    return jsonify({"ok": True, "id": coupon_id})


@finance_bp.route("/coupons/<coupon_id>", methods=["PUT"])
@require_permission(FINANCE_MANAGE)
async def update_coupon_view(coupon_id: str):
    if not await repository.get_coupon(coupon_id):
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
    fields, error = _validate_discount_fields(body)
    if error:
        return jsonify({"error": error}), 400
    max_redemptions = body.get("max_redemptions")
    await repository.update_coupon(
        coupon_id,
        max_redemptions=int(max_redemptions) if max_redemptions else None,
        valid_from=body.get("valid_from") or None,
        valid_until=body.get("valid_until") or None,
        is_active=bool(body.get("is_active", True)),
        **fields,
    )
    return jsonify({"ok": True})


@finance_bp.route("/coupons/<coupon_id>", methods=["DELETE"])
@require_permission(FINANCE_MANAGE)
async def delete_coupon_view(coupon_id: str):
    if not await repository.get_coupon(coupon_id):
        return jsonify({"error": "not found"}), 404
    await repository.delete_coupon(coupon_id)
    return jsonify({"ok": True})


# ── Org discounts ──────────────────────────────────────────────────────────────

@finance_bp.route("/discounts")
@require_permission(FINANCE_VIEW)
async def discounts_view():
    discounts = await repository.list_org_discounts()
    orgs = await db.table("organizations").order_by("name", "asc").all(allow_full_table=True)
    visible_keys = await get_visible_nav_keys(g.user_id)
    return render_template(
        "admin/finance/discounts.html", discounts=discounts, orgs=orgs, visible_keys=visible_keys
    )


@finance_bp.route("/discounts", methods=["POST"])
@require_permission(FINANCE_MANAGE)
async def create_discount_view():
    body = request.get_json(silent=True) or {}
    org_id = (body.get("org_id") or "").strip()
    if not org_id:
        return jsonify({"error": "org_id is required"}), 400
    fields, error = _validate_discount_fields(body)
    if error:
        return jsonify({"error": error}), 400
    discount_id = await repository.create_org_discount(
        org_id=org_id,
        reason=(body.get("reason") or "").strip() or None,
        valid_until=body.get("valid_until") or None,
        is_active=bool(body.get("is_active", True)),
        created_by=g.user_id,
        **fields,
    )
    return jsonify({"ok": True, "id": discount_id})


@finance_bp.route("/discounts/<discount_id>", methods=["PUT"])
@require_permission(FINANCE_MANAGE)
async def update_discount_view(discount_id: str):
    if not await repository.get_org_discount(discount_id):
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
    fields, error = _validate_discount_fields(body)
    if error:
        return jsonify({"error": error}), 400
    await repository.update_org_discount(
        discount_id,
        reason=(body.get("reason") or "").strip() or None,
        valid_until=body.get("valid_until") or None,
        is_active=bool(body.get("is_active", True)),
        **fields,
    )
    return jsonify({"ok": True})


@finance_bp.route("/discounts/<discount_id>", methods=["DELETE"])
@require_permission(FINANCE_MANAGE)
async def delete_discount_view(discount_id: str):
    if not await repository.get_org_discount(discount_id):
        return jsonify({"error": "not found"}), 404
    await repository.delete_org_discount(discount_id)
    return jsonify({"ok": True})
