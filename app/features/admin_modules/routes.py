"""Admin module management routes — list, IDE, and file/schema CRUD."""

from __future__ import annotations

import json
import re

from quart import Blueprint, g, jsonify, redirect, render_template, request, url_for

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.admin_modules import repository
from app.features.admin_modules.permissions import MODULE_EDIT, MODULE_VIEW
from app.features.plans.service import KNOWN_TIERS

admin_modules_bp = Blueprint("admin_modules", __name__, url_prefix="/admin/modules")

_ALLOWED_EXTENSIONS = {
    ".py", ".yaml", ".yml", ".sh", ".json", ".txt", ".md", ".toml", ".ini", ".conf",
}
_ID_RE = re.compile(r"^[a-z0-9_\-]{1,100}$")


def _ext_ok(filename: str) -> bool:
    import os
    return os.path.splitext(filename.lower())[1] in _ALLOWED_EXTENSIONS


# ── List + create ─────────────────────────────────────────────────────────────

@admin_modules_bp.route("/")
@require_permission(MODULE_VIEW)
async def list_view():
    modules = await repository.list_modules()
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "admin/modules/list.html",
        modules=modules,
        known_tiers=KNOWN_TIERS,
        visible_keys=visible_keys,
    )


@admin_modules_bp.route("/", methods=["POST"])
@require_permission(MODULE_EDIT)
async def create_view():
    body = await request.get_json(silent=True) or {}
    module_id = (body.get("id") or "").strip().lower().replace(" ", "_")
    if not module_id or not _ID_RE.match(module_id):
        return jsonify({"error": "ID must be 1–100 lowercase alphanumeric/underscore/hyphen characters"}), 400
    if await repository.get_module(module_id):
        return jsonify({"error": f"Module '{module_id}' already exists"}), 409
    display_name = (body.get("display_name") or "").strip()
    if not display_name:
        return jsonify({"error": "Display name is required"}), 400
    category = (body.get("category") or "").strip()
    if not category:
        return jsonify({"error": "Category is required"}), 400
    tier = body.get("tier") or "free"
    if tier not in KNOWN_TIERS:
        return jsonify({"error": f"Invalid tier '{tier}'"}), 400
    runtime_image = (body.get("runtime_image") or "python:3.11-slim").strip()
    await repository.create_custom_module(
        module_id=module_id,
        display_name=display_name,
        description=(body.get("description") or "").strip() or None,
        category=category,
        tier=tier,
        runtime_image=runtime_image,
        created_by=g.user_id,
    )
    return jsonify({"ok": True, "id": module_id})


# ── IDE ───────────────────────────────────────────────────────────────────────

@admin_modules_bp.route("/<module_id>/ide")
@require_permission(MODULE_VIEW)
async def ide_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return redirect(url_for("admin_modules.list_view"))
    raw_files = await repository.list_files(module_id)
    # Strip content + timestamps — fileTree only needs id/filename/is_entry_point.
    # Content is loaded lazily via GET when a file is opened.
    files = [
        {"id": f["id"], "filename": f["filename"], "is_entry_point": bool(f["is_entry_point"])}
        for f in raw_files
    ]
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "admin/modules/ide.html",
        module=mod,
        files=files,
        visible_keys=visible_keys,
    )


# ── Toggle enabled ────────────────────────────────────────────────────────────

@admin_modules_bp.route("/<module_id>/toggle", methods=["POST"])
@require_permission(MODULE_EDIT)
async def toggle_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    new_state = not bool(mod["is_enabled"])
    await repository.set_enabled(module_id, new_state)
    return jsonify({"ok": True, "is_enabled": new_state})


# ── Test (placeholder — runs a smoke check via Docker) ────────────────────────

@admin_modules_bp.route("/<module_id>/test", methods=["POST"])
@require_permission(MODULE_EDIT)
async def test_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    files = await repository.list_files(module_id)
    entry = next((f for f in files if f["is_entry_point"]), None)
    if not files:
        return jsonify({"ok": False, "message": "No files — add an entry point file first."}), 400
    if not entry:
        return jsonify({"ok": False, "message": "No entry point set — star a file to mark it as the entry point."}), 400
    return jsonify({
        "ok": True,
        "message": f"Test run queued for entry point '{entry['filename']}'. (Full test execution coming soon.)",
    })


# ── Module file CRUD ──────────────────────────────────────────────────────────

@admin_modules_bp.route("/<module_id>/files", methods=["POST"])
@require_permission(MODULE_EDIT)
async def create_file_view(module_id: str):
    if not await repository.get_module(module_id):
        return jsonify({"error": "module not found"}), 404
    body = await request.get_json(silent=True) or {}
    filename: str = (body.get("filename") or "").strip()
    if not filename:
        return jsonify({"error": "filename required"}), 400
    if not _ext_ok(filename):
        return jsonify({"error": f"Extension not allowed. Use: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"}), 400
    existing = await repository.list_files(module_id)
    if any(f["filename"] == filename for f in existing):
        return jsonify({"error": "A file with that name already exists"}), 409
    is_entry = len(existing) == 0
    file_id = await repository.create_file(module_id, filename, content="", is_entry_point=is_entry)
    return jsonify({"ok": True, "id": file_id, "filename": filename, "is_entry_point": is_entry})


@admin_modules_bp.route("/<module_id>/files/<file_id>", methods=["GET"])
@require_permission(MODULE_VIEW)
async def get_file_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id":             f["id"],
        "filename":       f["filename"],
        "content":        f["content"] or "",
        "is_entry_point": bool(f["is_entry_point"]),
    })


@admin_modules_bp.route("/<module_id>/files/<file_id>", methods=["PUT"])
@require_permission(MODULE_EDIT)
async def update_file_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    body = await request.get_json(silent=True) or {}
    await repository.update_file_content(file_id, body.get("content") or "")
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/files/<file_id>", methods=["DELETE"])
@require_permission(MODULE_EDIT)
async def delete_file_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    await repository.delete_file(file_id)
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/files/<file_id>/set-entry", methods=["POST"])
@require_permission(MODULE_EDIT)
async def set_entry_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    await repository.set_entry_point(module_id, file_id)
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/options-schema", methods=["PUT"])
@require_permission(MODULE_EDIT)
async def save_options_schema_view(module_id: str):
    if not await repository.get_module(module_id):
        return jsonify({"error": "not found"}), 404
    body = await request.get_json(silent=True) or {}
    raw = body.get("schema", "")
    if raw:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                return jsonify({"error": "schema must be a JSON array"}), 400
        except json.JSONDecodeError as exc:
            return jsonify({"error": f"Invalid JSON: {exc}"}), 400
        await repository.save_options_schema(module_id, raw)
    else:
        await repository.save_options_schema(module_id, None)
    return jsonify({"ok": True})
