"""Admin module management routes — list, view, and YAML IDE."""

from __future__ import annotations

from quart import Blueprint, g, jsonify, render_template, request

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.admin_modules import repository
from app.features.admin_modules.permissions import MODULE_EDIT, MODULE_VIEW

admin_modules_bp = Blueprint("admin_modules", __name__, url_prefix="/admin/modules")


@admin_modules_bp.route("/")
@require_permission(MODULE_VIEW)
async def list_view():
    modules = await repository.list_modules()
    visible_keys = await get_visible_nav_keys(g.user_id)
    selected_id = request.args.get("m")
    selected = None
    if selected_id:
        selected = await repository.get_module(selected_id)
    return await render_template(
        "admin/modules/list.html",
        modules=modules,
        selected=selected,
        visible_keys=visible_keys,
    )


@admin_modules_bp.route("/<module_id>/yaml", methods=["PUT"])
@require_permission(MODULE_EDIT)
async def save_yaml_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    body = await request.get_json(silent=True) or {}
    yaml_text: str = body.get("yaml_definition") or ""
    await repository.save_yaml(module_id, yaml_text)
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/toggle", methods=["POST"])
@require_permission(MODULE_EDIT)
async def toggle_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    new_state = not bool(mod["is_enabled"])
    await repository.set_enabled(module_id, new_state)
    return jsonify({"ok": True, "is_enabled": new_state})
