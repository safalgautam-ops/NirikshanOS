"""Admin module management routes — list, multi-file IDE, and toggles."""

from __future__ import annotations

from quart import Blueprint, g, jsonify, redirect, render_template, request, url_for

from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.admin_modules import repository
from app.features.admin_modules.permissions import MODULE_EDIT, MODULE_VIEW

admin_modules_bp = Blueprint("admin_modules", __name__, url_prefix="/admin/modules")

_ALLOWED_EXTENSIONS = {
    ".py", ".yaml", ".yml", ".sh", ".json", ".txt", ".md", ".toml", ".ini", ".conf",
}


def _ext_ok(filename: str) -> bool:
    import os
    return os.path.splitext(filename.lower())[1] in _ALLOWED_EXTENSIONS


@admin_modules_bp.route("/")
@require_permission(MODULE_VIEW)
async def list_view():
    modules = await repository.list_modules()
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "admin/modules/list.html",
        modules=modules,
        visible_keys=visible_keys,
    )


@admin_modules_bp.route("/<module_id>/ide")
@require_permission(MODULE_VIEW)
async def ide_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return redirect(url_for("admin_modules.list_view"))
    files = await repository.list_files(module_id)
    return await render_template(
        "admin/modules/ide.html",
        module=mod,
        files=files,
    )


@admin_modules_bp.route("/<module_id>/toggle", methods=["POST"])
@require_permission(MODULE_EDIT)
async def toggle_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    new_state = not bool(mod["is_enabled"])
    await repository.set_enabled(module_id, new_state)
    return jsonify({"ok": True, "is_enabled": new_state})


# ---------------------------------------------------------------------------
# Module file CRUD
# ---------------------------------------------------------------------------


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


@admin_modules_bp.route("/<module_id>/files/<file_id>", methods=["PUT"])
@require_permission(MODULE_EDIT)
async def update_file_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    body = await request.get_json(silent=True) or {}
    await repository.update_file_content(file_id, body.get("content") or "")
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/files/<file_id>", methods=["GET"])
@require_permission(MODULE_VIEW)
async def get_file_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id":            f["id"],
        "filename":      f["filename"],
        "content":       f["content"] or "",
        "is_entry_point": bool(f["is_entry_point"]),
    })


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
    import json as _json
    if not await repository.get_module(module_id):
        return jsonify({"error": "not found"}), 404
    body = await request.get_json(silent=True) or {}
    raw = body.get("schema", "")
    if raw:
        try:
            parsed = _json.loads(raw)
            if not isinstance(parsed, list):
                return jsonify({"error": "schema must be a JSON array"}), 400
        except _json.JSONDecodeError as exc:
            return jsonify({"error": f"Invalid JSON: {exc}"}), 400
        await repository.save_options_schema(module_id, raw)
    else:
        await repository.save_options_schema(module_id, None)
    return jsonify({"ok": True})
