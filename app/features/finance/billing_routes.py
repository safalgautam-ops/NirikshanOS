"""Org-facing billing: pick a plan, pay via eSewa, land on a public
callback that verifies the payment server-side before activating anything.
Kept in the finance feature (not onboarding) since it's really finance
business logic wearing an org-facing UI, but registered as its own
blueprint so the callback routes can be public while the plan-picker route
stays org-gated.
"""

from __future__ import annotations

from quart import Blueprint, abort, g, redirect, render_template, request, url_for

from app.config import Config
from app.core.security.org_permissions import require_org_permission
from app.core.security.permissions import get_visible_nav_keys
from app.features.finance import service as finance_service
from app.features.onboarding.permissions import ORG_BILLING_MANAGE
from app.features.onboarding.service import get_user_organization
from app.features.plans import repository as plans_repository
from app.features.plans import service as plans_service

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


@billing_bp.route("/")
@require_org_permission(ORG_BILLING_MANAGE)
async def plan_picker_view():
    org = await get_user_organization(g.user_id)
    if not org:
        abort(404)
    all_plans = await plans_repository.list_plans()
    plans = [p for p in all_plans if p["is_active"]]
    current_sub = await plans_service.get_active_subscription(org["id"])
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "billing/plan_picker.html",
        org=org,
        visible_keys=visible_keys,
        plans=plans,
        current_sub=current_sub,
    )


@billing_bp.route("/pay", methods=["POST"])
@require_org_permission(ORG_BILLING_MANAGE)
async def pay_view():
    org = await get_user_organization(g.user_id)
    if not org:
        abort(404)
    form = await request.form
    plan_id = form.get("plan_id") or ""
    billing_period = form.get("billing_period") or "monthly"
    coupon_code = form.get("coupon_code") or None

    try:
        result = await finance_service.initiate_payment(
            org_id=org["id"],
            plan_id=plan_id,
            billing_period=billing_period,
            coupon_code=coupon_code,
            created_by=g.user_id,
            success_url=f"{Config.APP_URL}/billing/esewa/success",
            failure_url=f"{Config.APP_URL}/billing/esewa/failure",
        )
    except finance_service.PaymentError as exc:
        return redirect(url_for("billing.plan_picker_view") + f"?error={exc}")

    # Same-origin auto-submitting form POSTing straight to eSewa — the
    # server built and signed every field; the browser only carries it over.
    return await render_template(
        "billing/esewa_redirect.html",
        form_action=result["form_action"],
        form_fields=result["form_fields"],
    )


# ── eSewa callbacks — public, no login required ───────────────────────────────
# eSewa's redirect must reach these regardless of session state. The handler
# re-derives the org from the stored transaction row (see
# finance/service.py), never from the request, so there is no session
# dependency to exploit here.

@billing_bp.route("/esewa/success")
async def esewa_success_view():
    raw_payload = request.args.get("data", "")
    success, message = await finance_service.handle_success_callback(raw_payload)
    return await render_template("billing/esewa_result.html", success=success, message=message)


@billing_bp.route("/esewa/failure")
async def esewa_failure_view():
    # eSewa's failure redirect carries the same base64 `data` param in some
    # integrations and just a bare transaction_uuid in others - try the
    # base64 payload first since it's more informative for the ledger.
    raw_payload = request.args.get("data", "")
    if raw_payload:
        payload = None
        try:
            import base64
            import json
            payload = json.loads(base64.b64decode(raw_payload))
        except Exception:
            payload = None
        transaction_uuid = payload.get("transaction_uuid") if payload else None
    else:
        transaction_uuid = request.args.get("transaction_uuid")

    if transaction_uuid:
        await finance_service.handle_failure_callback(transaction_uuid)
    return await render_template(
        "billing/esewa_result.html", success=False, message="Payment was cancelled or failed."
    )
