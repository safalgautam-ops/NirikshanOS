"""Admin Organizations routes — list/search/filter + create/edit/delete."""

from __future__ import annotations

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from app.core import storage
from app.core.security.permissions import get_visible_nav_keys, require_permission
from app.features.organizations import repository, service
from app.features.organizations.choices import ORG_TYPES
from app.features.organizations.permissions import ORG_APPROVE, ORG_CREATE, ORG_DELETE, ORG_EDIT, ORG_VIEW
from app.features.organizations.service import OrganizationError

organizations_bp = Blueprint("organizations", __name__, url_prefix="/admin/organizations")


@organizations_bp.route("/")
@require_permission(ORG_VIEW)
async def list_view():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    verification = request.args.get("verification", "")
    page = request.args.get("page", 1, type=int)
    org_param = request.args.get("org", "")

    result = await service.get_organizations_page(
        search=search, status=status, verification=verification, page=page
    )
    all_orgs = await repository.list_organizations(page=1, per_page=200)
    counts = await repository.get_member_counts([o["id"] for o in all_orgs.items])
    for org in all_orgs.items:
        org["member_count"] = counts.get(org["id"], 0)

    visible_keys = await get_visible_nav_keys(g.user_id)
    error = request.args.get("error")

    selected_org = None
    is_new = False
    documents = []
    if org_param == "new":
        is_new = True
        selected_org = {
            "id": None,
            "name": "",
            "description": "",
            "status": "active",
            "slug": None,
            "member_count": 0,
        }
    elif org_param:
        selected_org = await repository.get_organization(org_param)
        if selected_org:
            mc = await repository.get_member_counts([selected_org["id"]])
            selected_org["member_count"] = mc.get(selected_org["id"], 0)
            documents = await repository.list_documents(selected_org["id"])

    return render_template(
        "admin/organizations/list.html",
        page=result,
        all_orgs=all_orgs.items,
        search=search,
        status=status,
        verification=verification,
        visible_keys=visible_keys,
        error=error,
        selected_org=selected_org,
        is_new=is_new,
        documents=documents,
        org_type_labels=dict(ORG_TYPES),
    )


@organizations_bp.route("/create", methods=["POST"])
@require_permission(ORG_CREATE)
async def create_view():
    form = request.form
    try:
        org_id = await service.create_organization(
            name=form.get("name", ""),
            description=form.get("description", ""),
            status=form.get("status", "active"),
            created_by=g.user_id,
        )
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org="new", error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))


@organizations_bp.route("/", methods=["POST"])
@require_permission(ORG_CREATE)
async def create_view_legacy():
    return await create_view()


@organizations_bp.route("/<org_id>/update", methods=["POST"])
@require_permission(ORG_EDIT)
async def update_view(org_id: str):
    form = request.form
    try:
        await service.update_organization(
            org_id,
            name=form.get("name", ""),
            description=form.get("description", ""),
            status=form.get("status", "active"),
        )
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org=org_id, error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))


@organizations_bp.route("/<org_id>", methods=["POST"])
@require_permission(ORG_EDIT)
async def update_view_legacy(org_id: str):
    return await update_view(org_id)


@organizations_bp.route("/<org_id>/update-status", methods=["POST"])
@require_permission(ORG_EDIT)
async def update_status_view(org_id: str):
    form = request.form
    new_status = form.get("status", "active")
    try:
        org = await repository.get_organization(org_id)
        await service.update_organization(
            org_id,
            name=(org or {}).get("name", ""),
            description=(org or {}).get("description", ""),
            status=new_status,
        )
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org=org_id, error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))


@organizations_bp.route("/<org_id>/delete", methods=["POST"])
@require_permission(ORG_DELETE)
async def delete_view(org_id: str):
    await service.delete_organization(org_id)
    return redirect(url_for("organizations.list_view"))


@organizations_bp.route("/<org_id>/approve", methods=["POST"])
@require_permission(ORG_APPROVE)
async def approve_view(org_id: str):
    try:
        await service.approve_organization(org_id, reviewed_by=g.user_id)
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org=org_id, error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))


@organizations_bp.route("/<org_id>/reject", methods=["POST"])
@require_permission(ORG_APPROVE)
async def reject_view(org_id: str):
    form = request.form
    try:
        await service.reject_organization(org_id, reviewed_by=g.user_id, reason=form.get("reason", ""))
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org=org_id, error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))


@organizations_bp.route("/documents/<doc_id>")
@require_permission(ORG_VIEW)
async def download_document_view(doc_id: str):
    doc = await repository.get_document(doc_id)
    if not doc:
        abort(404)
    url = await storage.get_document_url(doc["file_path"])
    return redirect(url)


@organizations_bp.route("/<org_id>/documents", methods=["POST"])
@require_permission(ORG_EDIT)
async def upload_document_view(org_id: str):
    files = request.files
    try:
        await service.add_documents(org_id, files.getlist("documents"))
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org=org_id, error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))


@organizations_bp.route("/<org_id>/documents/<doc_id>/delete", methods=["POST"])
@require_permission(ORG_EDIT)
async def delete_document_view(org_id: str, doc_id: str):
    try:
        await service.delete_document(org_id, doc_id)
    except OrganizationError as exc:
        return redirect(url_for("organizations.list_view", org=org_id, error=str(exc)))
    return redirect(url_for("organizations.list_view", org=org_id))
