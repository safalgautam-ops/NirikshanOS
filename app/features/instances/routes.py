"""Admin routes for registering and managing container instances."""

from __future__ import annotations

import re

from quart import Blueprint, g, jsonify, render_template, request

from app.core.db.pool import ForeignKeyError
from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.extensions import get_redis
from app.features.instances import repository
from app.features.instances.permissions import INSTANCE_EDIT, INSTANCE_VIEW

instances_bp = Blueprint("instances", __name__, url_prefix="/admin/instances")

_ID_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")
_QUEUE_NAMES = {"fast_queue", "standard_queue", "heavy_queue", "sandbox_queue"}
_CPU_RE = re.compile(r"^\d+(\.\d+)?$")
_MEM_RE = re.compile(r"^\d+[mg]$", re.IGNORECASE)


def _validate_instance_fields(body: dict) -> tuple[dict | None, str | None]:
    """Shared validation for create/update. Returns (clean_fields, error)."""
    display_name = (body.get("display_name") or "").strip()
    if not display_name:
        return None, "Display name is required"
    image_tag = (body.get("image_tag") or "").strip()
    if not image_tag:
        return None, "Image tag is required"
    cpu_limit = str(body.get("cpu_limit") or "1.0").strip()
    if not _CPU_RE.match(cpu_limit):
        return None, "CPU limit must be a number like 1.0 or 0.5"
    memory_limit = str(body.get("memory_limit") or "512m").strip()
    if not _MEM_RE.match(memory_limit):
        return None, "Memory limit must look like 512m or 2g"
    try:
        pids_limit = int(body.get("pids_limit") or 128)
    except (TypeError, ValueError):
        return None, "PIDs limit must be a number"
    queue_name = (body.get("queue_name") or "standard_queue").strip()
    if queue_name not in _QUEUE_NAMES:
        return None, f"Invalid queue_name. Must be one of: {sorted(_QUEUE_NAMES)}"
    try:
        timeout_seconds = int(body.get("default_timeout_seconds") or 120)
    except (TypeError, ValueError):
        return None, "Timeout must be a number"
    if timeout_seconds <= 0 or timeout_seconds > 600:
        return None, "Timeout must be between 1 and 600 seconds"
    return {
        "display_name": display_name,
        "image_tag": image_tag,
        "cpu_limit": cpu_limit,
        "memory_limit": memory_limit,
        "pids_limit": pids_limit,
        "queue_name": queue_name,
        "default_timeout_seconds": timeout_seconds,
    }, None


@instances_bp.route("/")
@require_permission(INSTANCE_VIEW)
async def list_view():
    instances = await repository.list_instances()
    visible_keys = await get_visible_nav_keys(g.user_id)
    return await render_template(
        "admin/instances/list.html",
        instances=instances,
        visible_keys=visible_keys,
    )


@instances_bp.route("/", methods=["POST"])
@require_permission(INSTANCE_EDIT)
async def create_view():
    body = await request.get_json(silent=True) or {}
    instance_id = (body.get("id") or "").strip().lower().replace(" ", "_")
    if not instance_id or not _ID_RE.match(instance_id):
        return jsonify({"error": "ID must be 1–64 lowercase alphanumeric/underscore/hyphen characters"}), 400
    if await repository.get_instance(instance_id):
        return jsonify({"error": f"Instance '{instance_id}' already exists"}), 409

    fields, error = _validate_instance_fields(body)
    if error:
        return jsonify({"error": error}), 400
    if await repository.get_instance_by_image_tag(fields["image_tag"]):
        return jsonify({"error": f"Image tag '{fields['image_tag']}' is already registered as another instance"}), 409

    await repository.create_instance(instance_id=instance_id, created_by=g.user_id, **fields)
    return jsonify({"ok": True, "id": instance_id})


@instances_bp.route("/<instance_id>", methods=["PUT"])
@require_permission(INSTANCE_EDIT)
async def update_view(instance_id: str):
    existing = await repository.get_instance(instance_id)
    if not existing:
        return jsonify({"error": "not found"}), 404
    body = await request.get_json(silent=True) or {}
    fields, error = _validate_instance_fields(body)
    if error:
        return jsonify({"error": error}), 400
    conflict = await repository.get_instance_by_image_tag(fields["image_tag"])
    if conflict and conflict["id"] != instance_id:
        return jsonify({"error": f"Image tag '{fields['image_tag']}' is already registered as another instance"}), 409

    await repository.update_instance(
        instance_id,
        is_active=bool(body.get("is_active", existing["is_active"])),
        **fields,
    )
    return jsonify({"ok": True})


@instances_bp.route("/<instance_id>", methods=["DELETE"])
@require_permission(INSTANCE_EDIT)
async def delete_view(instance_id: str):
    if not await repository.get_instance(instance_id):
        return jsonify({"error": "not found"}), 404
    try:
        await repository.delete_instance(instance_id)
    except ForeignKeyError:
        return jsonify({
            "error": "This instance is still referenced by modules or test runs. "
                     "Reassign or delete those first, or deactivate this instance instead.",
        }), 409
    return jsonify({"ok": True})


@instances_bp.route("/<instance_id>/recheck", methods=["POST"])
@require_permission(INSTANCE_EDIT)
async def recheck_view(instance_id: str):
    """Ask the worker (the only container with Docker access) to run
    `docker image inspect` on this instance's image_tag and update
    image_status. Fire-and-forget — the frontend polls list_view/get for
    the updated status a moment later."""
    if not await repository.get_instance(instance_id):
        return jsonify({"error": "not found"}), 404
    redis = get_redis()
    await redis.lpush("nirikshan:instance_check_queue", instance_id)
    return jsonify({"ok": True, "message": "Recheck queued — refresh in a few seconds."})
