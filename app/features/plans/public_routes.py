"""Public, read-only subscription plan data used by the marketing homepage."""

from __future__ import annotations

from flask import Blueprint, jsonify, make_response

from app.features.plans import repository


public_plans_bp = Blueprint("public_plans", __name__, url_prefix="/api")


def _serialize_plan(plan: dict) -> dict:
    return {
        "id": plan["id"],
        "display_name": plan["display_name"],
        "description": plan.get("description") or "",
        "price_monthly": str(plan["price_monthly"]),
        "price_annual": str(plan["price_annual"]),
        "resources": plan.get("resources") or {},
        "allowed_tiers": plan.get("allowed_tiers") or [],
        "allowed_instance_count": len(plan.get("allowed_instance_ids") or []),
    }


@public_plans_bp.get("/plans")
async def list_public_plans():
    plans = await repository.list_plans()
    payload = [_serialize_plan(plan) for plan in plans if plan["is_active"]]
    response = make_response(jsonify({"plans": payload}))
    response.headers["Cache-Control"] = "public, max-age=60"
    return response
