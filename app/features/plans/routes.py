"""Admin routes for plans and org subscriptions."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.instances import repository as instances_repository
from app.features.plans import repository
from app.features.plans.permissions import PLAN_EDIT, PLAN_VIEW
from app.features.plans.service import KNOWN_TIERS

plans_bp = Blueprint("plans", __name__, url_prefix="/admin/plans")


@plans_bp.route("/")
@require_permission(PLAN_VIEW)
async def list_view():
    plans = await repository.list_plans()
    instances = await instances_repository.list_active_instances()
    instances_for_js = [
        {"id": i["id"], "display_name": i["display_name"], "image_tag": i["image_tag"]}
        for i in instances
    ]
    # Subscriptions render directly on this page (read-only audit view) -
    # orgs take/cancel their own plan from their Billing page via eSewa,
    # there is no separate admin subscriptions route anymore.
    subscriptions = await repository.list_subscriptions()
    visible_keys = await get_visible_nav_keys(g.user_id)
    selected_id = request.args.get("p")
    is_new = selected_id == "new"
    selected = None
    if selected_id and not is_new:
        selected = await repository.get_plan(selected_id)
    return render_template(
        "admin/plans/list.html",
        plans=plans,
        instances_for_js=instances_for_js,
        subscriptions=subscriptions,
        selected=selected,
        is_new=is_new,
        known_tiers=KNOWN_TIERS,
        visible_keys=visible_keys,
    )


@plans_bp.route("/", methods=["POST"])
@require_permission(PLAN_EDIT)
async def create_view():
    form = request.form
    plan_id = (form.get("id") or "").strip().lower().replace(" ", "_")
    if not plan_id:
        return redirect(url_for("plans.list_view") + "?p=new")
    if await repository.get_plan(plan_id):
        return redirect(url_for("plans.list_view") + f"?p=new&error=exists")
    resources = {
        "ram_gb":     int(form.get("ram_gb") or 2),
        "vcpu":       int(form.get("vcpu") or 2),
        "storage_gb": int(form.get("storage_gb") or 20),
    }
    await repository.create_plan(
        plan_id=plan_id,
        display_name=form.get("display_name") or plan_id,
        description=form.get("description") or None,
        price_monthly=float(form.get("price_monthly") or 0),
        price_annual=float(form.get("price_annual") or 0),
        resources=resources,
        allowed_tiers=form.getlist("allowed_tiers"),
        is_active=form.get("is_active") == "1",
        sort_order=int(form.get("sort_order") or 0),
    )
    await repository.set_plan_instances(plan_id, form.getlist("allowed_instance_ids"))
    return redirect(url_for("plans.list_view") + f"?p={plan_id}")


@plans_bp.route("/<plan_id>", methods=["PUT"])
@require_permission(PLAN_EDIT)
async def update_view(plan_id: str):
    if not await repository.get_plan(plan_id):
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(silent=True) or {}
    ram_gb = body.get("ram_gb")
    vcpu = body.get("vcpu")
    storage_gb = body.get("storage_gb")
    resources = {
        "ram_gb":     int(ram_gb) if ram_gb is not None else 2,
        "vcpu":       int(vcpu) if vcpu is not None else 2,
        "storage_gb": int(storage_gb) if storage_gb is not None else 20,
    }
    await repository.update_plan(
        plan_id,
        display_name=body.get("display_name") or plan_id,
        description=body.get("description") or None,
        price_monthly=float(body.get("price_monthly") or 0),
        price_annual=float(body.get("price_annual") or 0),
        resources=resources,
        allowed_tiers=body.get("allowed_tiers") or [],
        is_active=bool(body.get("is_active", True)),
        sort_order=int(body.get("sort_order") or 0),
    )
    await repository.set_plan_instances(plan_id, body.get("allowed_instance_ids") or [])
    return jsonify({"ok": True})


@plans_bp.route("/<plan_id>", methods=["DELETE"])
@require_permission(PLAN_EDIT)
async def delete_view(plan_id: str):
    if not await repository.get_plan(plan_id):
        return jsonify({"error": "Not found"}), 404
    await repository.delete_plan(plan_id)
    return jsonify({"ok": True})
