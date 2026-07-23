"""Admin module management routes — list, IDE, and file/schema CRUD."""

from __future__ import annotations

import json
import re

from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for

from app.config import Config
from app.core.object_storage import put_object
from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.core.utils.ids import new_id
from app.extensions import get_redis
from app.features.admin_modules import repository
from app.features.admin_modules.permissions import MODULE_DELETE, MODULE_EDIT, MODULE_VIEW
from app.features.categories import repository as categories_repository
from app.features.instances import repository as instances_repository
from app.features.plans import repository as plans_repository
from app.features.plans.service import KNOWN_TIERS

admin_modules_bp = Blueprint("admin_modules", __name__, url_prefix="/admin/modules")

_MAX_TEST_UPLOAD_BYTES = 200 * 1024 * 1024

_ALLOWED_EXTENSIONS = {
    ".py",
    ".yaml",
    ".yml",
    ".sh",
    ".json",
    ".txt",
    ".md",
    ".toml",
    ".ini",
    ".conf",
}
_ID_RE = re.compile(r"^[a-z0-9_\-]{1,100}$")


def _ext_ok(filename: str) -> bool:
    import os

    return os.path.splitext(filename.lower())[1] in _ALLOWED_EXTENSIONS


async def _validate_meta_fields(body: dict) -> tuple[dict | None, str | None]:
    """Shared validation for create/update."""
    display_name = (body.get("display_name") or "").strip()
    if not display_name:
        return None, "Display name is required"
    tier = (body.get("tier") or "basic").strip()
    if tier not in KNOWN_TIERS:
        return None, f"Invalid tier '{tier}'"

    category_id = (body.get("category_id") or "").strip() or None
    if category_id and not await categories_repository.get_category(category_id):
        return None, f"Category '{category_id}' does not exist"

    instance_id = (body.get("instance_id") or "").strip() or None
    if instance_id:
        instance = await instances_repository.get_instance(instance_id)
        if not instance:
            return None, f"Instance '{instance_id}' does not exist"
        if not instance["is_active"]:
            return None, f"Instance '{instance_id}' is not active"

    return {
        "display_name": display_name,
        "description": (body.get("description") or "").strip() or None,
        "category_id": category_id,
        "tier": tier,
        "instance_id": instance_id,
    }, None


@admin_modules_bp.route("/")
@require_permission(MODULE_VIEW)
async def list_view():
    modules = await repository.list_modules()
    categories = await categories_repository.list_categories()
    instances = await instances_repository.list_ready_instances()
    visible_keys = await get_visible_nav_keys(g.user_id)
    return render_template(
        "admin/modules/list.html",
        modules=modules,
        categories=categories,
        instances=instances,
        known_tiers=KNOWN_TIERS,
        visible_keys=visible_keys,
    )


@admin_modules_bp.route("/", methods=["POST"])
@require_permission(MODULE_EDIT)
async def create_view():
    body = request.get_json(silent=True) or {}
    module_id = (body.get("id") or "").strip().lower().replace(" ", "_")
    if not module_id or not _ID_RE.match(module_id):
        return jsonify({"error": "ID must be 1–100 lowercase alphanumeric/underscore/hyphen characters"}), 400
    if await repository.get_module(module_id):
        return jsonify({"error": f"Module '{module_id}' already exists"}), 409

    fields, error = await _validate_meta_fields(body)
    if error:
        return jsonify({"error": error}), 400

    await repository.create_custom_module(
        module_id=module_id,
        created_by=g.user_id,
        **fields,
    )
    return jsonify({"ok": True, "id": module_id})


@admin_modules_bp.route("/<module_id>/ide")
@require_permission(MODULE_VIEW)
async def ide_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return redirect(url_for("admin_modules.list_view"))
    raw_files = await repository.list_files(module_id)
    files = [
        {"id": f["id"], "filename": f["filename"], "is_entry_point": bool(f["is_entry_point"])}
        for f in raw_files
    ]
    categories = await categories_repository.list_categories()
    instances = await instances_repository.list_ready_instances()
    if mod["instance_id"] and not any(i["id"] == mod["instance_id"] for i in instances):
        current = await instances_repository.get_instance(mod["instance_id"])
        if current:
            instances = [current] + instances
    instances_for_js = [
        {
            "id": i["id"],
            "display_name": i["display_name"],
            "image_tag": i["image_tag"],
            "image_status": i["image_status"],
        }
        for i in instances
    ]
    visible_keys = await get_visible_nav_keys(g.user_id)
    module_meta = {
        "display_name": mod["display_name"],
        "description": mod["description"] or "",
        "category_id": mod["category_id"],
        "tier": mod["tier"],
        "instance_id": mod["instance_id"],
    }
    all_plans = await plans_repository.list_plans()
    affected_plans = [p["display_name"] for p in all_plans if mod["tier"] in (p["allowed_tiers"] or [])]
    return render_template(
        "admin/modules/ide.html",
        module=mod,
        module_meta=module_meta,
        files=files,
        categories=categories,
        instances=instances,
        instances_for_js=instances_for_js,
        known_tiers=KNOWN_TIERS,
        affected_plans=affected_plans,
        visible_keys=visible_keys,
    )


@admin_modules_bp.route("/<module_id>", methods=["PATCH"])
@require_permission(MODULE_EDIT)
async def update_meta_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
    fields, error = await _validate_meta_fields(body)
    if error:
        return jsonify({"error": error}), 400
    await repository.update_module_meta(module_id, **fields)
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/toggle", methods=["POST"])
@require_permission(MODULE_EDIT)
async def toggle_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    if not mod["is_enabled"] and not mod["instance_id"]:
        return jsonify({"error": "Assign an instance in Settings before enabling this module."}), 400
    new_state = not bool(mod["is_enabled"])
    await repository.set_enabled(module_id, new_state)
    return jsonify({"ok": True, "is_enabled": new_state})


@admin_modules_bp.route("/<module_id>", methods=["DELETE"])
@require_permission(MODULE_DELETE)
async def delete_view(module_id: str):
    if not await repository.get_module(module_id):
        return jsonify({"error": "not found"}), 404
    await repository.delete_module(module_id)
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/files", methods=["POST"])
@require_permission(MODULE_EDIT)
async def create_file_view(module_id: str):
    if not await repository.get_module(module_id):
        return jsonify({"error": "module not found"}), 404
    body = request.get_json(silent=True) or {}
    filename: str = (body.get("filename") or "").strip()
    if not filename:
        return jsonify({"error": "filename required"}), 400
    if not _ext_ok(filename):
        return (
            jsonify({"error": f"Extension not allowed. Use: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"}),
            400,
        )
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
    return jsonify(
        {
            "id": f["id"],
            "filename": f["filename"],
            "content": f["content"] or "",
            "is_entry_point": bool(f["is_entry_point"]),
        }
    )


@admin_modules_bp.route("/<module_id>/files/<file_id>", methods=["PUT"])
@require_permission(MODULE_EDIT)
async def update_file_view(module_id: str, file_id: str):
    f = await repository.get_file(file_id)
    if not f or f["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
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
    body = request.get_json(silent=True) or {}
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


@admin_modules_bp.route("/<module_id>/pipeline", methods=["PUT"])
@require_permission(MODULE_EDIT)
async def save_pipeline_view(module_id: str):
    if not await repository.get_module(module_id):
        return jsonify({"error": "not found"}), 404
    body = request.get_json(silent=True) or {}
    raw = body.get("pipeline", "")
    if raw:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list):
                return jsonify({"error": "pipeline must be a JSON object with a 'steps' array"}), 400
            step_ids = set()
            for step in parsed["steps"]:
                if not isinstance(step, dict) or not step.get("id"):
                    return jsonify({"error": "every step needs an 'id'"}), 400
                if step["id"] in step_ids:
                    return jsonify({"error": f"duplicate step id '{step['id']}'"}), 400
                step_ids.add(step["id"])
                if "run" not in step or not ("argv" in step["run"] or "script" in step["run"]):
                    return jsonify({"error": f"step '{step['id']}' needs run.argv or run.script"}), 400
                for dep in step.get("depends_on", []):
                    if dep not in step_ids and dep not in {s.get("id") for s in parsed["steps"]}:
                        return jsonify({"error": f"step '{step['id']}' depends_on unknown step '{dep}'"}), 400
        except json.JSONDecodeError as exc:
            return jsonify({"error": f"Invalid JSON: {exc}"}), 400
        await repository.save_pipeline(module_id, raw)
    else:
        await repository.save_pipeline(module_id, None)
    return jsonify({"ok": True})


@admin_modules_bp.route("/<module_id>/test/upload", methods=["POST"])
@require_permission(MODULE_EDIT)
async def test_upload_view(module_id: str):
    if not await repository.get_module(module_id):
        return jsonify({"error": "not found"}), 404
    files = request.files
    file = files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400
    data = file.read()
    if len(data) > _MAX_TEST_UPLOAD_BYTES:
        return (
            jsonify(
                {"error": f"File too large — max {_MAX_TEST_UPLOAD_BYTES // (1024*1024)}MB for test uploads"}
            ),
            400,
        )
    upload_id = new_id()
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename)
    s3_key = f"module-tests/{module_id}/{upload_id}/{safe_filename}"
    await put_object(
        bucket=Config.MINIO_BUCKET_PRIVATE,
        key=s3_key,
        data=data,
        content_type=file.content_type or "application/octet-stream",
    )
    return jsonify({"ok": True, "s3_key": s3_key})


@admin_modules_bp.route("/<module_id>/test/run", methods=["POST"])
@require_permission(MODULE_EDIT)
async def test_run_view(module_id: str):
    mod = await repository.get_module(module_id)
    if not mod:
        return jsonify({"error": "not found"}), 404
    if not mod["instance_id"]:
        return jsonify({"error": "Assign an instance in Settings before testing this module."}), 400
    instance = await instances_repository.get_instance(mod["instance_id"])
    if not instance or not instance["is_active"]:
        return (
            jsonify(
                {
                    "error": "This module's instance no longer exists or is inactive. Assign a different one in Settings."
                }
            ),
            400,
        )
    if instance["image_status"] != "ready":
        return (
            jsonify(
                {
                    "error": f"Instance '{instance['display_name']}' has not been built yet — build the image and click Recheck on /admin/instances before testing."
                }
            ),
            400,
        )
    files = await repository.list_files(module_id)
    has_entry = any(f["is_entry_point"] for f in files)
    if not has_entry and not mod.get("pipeline_spec"):
        return jsonify({"error": "No entry point set and no pipeline defined — nothing to run."}), 400

    body = request.get_json(silent=True) or {}
    s3_key = (body.get("s3_key") or "").strip()
    if not s3_key:
        return jsonify({"error": "Upload a sample file first."}), 400

    run_id = await repository.create_test_run(
        module_id=module_id,
        instance_id=mod["instance_id"],
        s3_key=s3_key,
        created_by=g.user_id,
    )
    redis = get_redis()
    await redis.lpush("nirikshan:test_queue", run_id)
    return jsonify({"ok": True, "run_id": run_id})


@admin_modules_bp.route("/<module_id>/test/<run_id>")
@require_permission(MODULE_VIEW)
async def test_status_view(module_id: str, run_id: str):
    run = await repository.get_test_run(run_id)
    if not run or run["module_id"] != module_id:
        return jsonify({"error": "not found"}), 404
    raw_result = run["result_json"]
    if isinstance(raw_result, str):
        try:
            raw_result = json.loads(raw_result)
        except json.JSONDecodeError:
            raw_result = None
    return jsonify(
        {
            "id": run["id"],
            "status": run["status"],
            "error_message": run["error_message"],
            "result": raw_result,
            "finished_at": run["finished_at"].isoformat() if run["finished_at"] else None,
        }
    )
