"""Admin routes for managing module categories."""

from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, render_template, request

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.categories import repository
from app.features.categories.permissions import CATEGORY_EDIT, CATEGORY_VIEW

categories_bp = Blueprint("categories", __name__, url_prefix="/admin/categories")

_ID_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")


@categories_bp.route("/")
@require_permission(CATEGORY_VIEW)
async def list_view():
    categories = await repository.list_categories()
    visible_keys = await get_visible_nav_keys(g.user_id)
    return render_template(
        "admin/categories/list.html",
        categories=categories,
        visible_keys=visible_keys,
    )


@categories_bp.route("/", methods=["POST"])
@require_permission(CATEGORY_EDIT)
async def create_view():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    category_id = name.strip().lower().replace(" ", "_").replace("-", "_")
    if not _ID_RE.match(category_id):
        return jsonify({"error": "Name must produce a valid id (letters, numbers, spaces, hyphens)"}), 400
    if await repository.get_category(category_id) or await repository.get_category_by_name(name):
        return jsonify({"error": f"Category '{name}' already exists"}), 409
    await repository.create_category(
        category_id=category_id,
        name=name,
        description=(body.get("description") or "").strip() or None,
        sort_order=int(body.get("sort_order") or 0),
    )
    return jsonify({"ok": True, "id": category_id})


@categories_bp.route("/<category_id>", methods=["PUT"])
@require_permission(CATEGORY_EDIT)
async def update_view(category_id: str):
    if not await repository.get_category(category_id):
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    conflict = await repository.get_category_by_name(name)
    if conflict and conflict["id"] != category_id:
        return jsonify({"error": f"Category '{name}' already exists"}), 409
    await repository.update_category(
        category_id,
        name=name,
        description=(body.get("description") or "").strip() or None,
        sort_order=int(body.get("sort_order") or 0),
    )
    return jsonify({"ok": True})


@categories_bp.route("/<category_id>", methods=["DELETE"])
@require_permission(CATEGORY_EDIT)
async def delete_view(category_id: str):
    if not await repository.get_category(category_id):
        return jsonify({"error": "not found"}), 404
    await repository.delete_category(category_id)
    return jsonify({"ok": True})
