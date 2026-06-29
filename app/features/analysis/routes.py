"""Analysis module routes: read-only JSON endpoints over the module
registry (app/features/analysis/module_registry.py) - what modules exist,
and which ones are compatible with a given evidence file.

No url_prefix here, unlike cases_bp/evidence_bp: those blueprints only use
one because every one of their routes shares it. This blueprint's routes
don't (one is case+evidence scoped under /cases/..., the other two are
registry-wide under /analysis/...), so each route spells out its full path
instead.

The evidence-scoped route reuses the exact same case-visibility rule as
evidence_bp (owner/creator/case member - see cases/service.py.
can_access_case) and intentionally requires no extra org permission:
listing which modules *could* run against evidence you can already see is
not a management action, the same reasoning timeline/routes.py and
evidence_bp's own read-only routes already use.

This phase is read-only. No job is created, no Docker/Redis/worker is
involved - see service.py's module docstring.
"""

from __future__ import annotations

from quart import Blueprint, abort, g, jsonify

from app.core.security.org_permissions import get_user_org_membership, is_org_owner
from app.core.security.sessions import login_required
from app.features.cases.service import get_case_for_user
from app.features.evidence.service import get_evidence
from app.features.analysis.service import (
    detect_evidence_type,
    get_compatible_modules,
    get_module,
    list_modules,
    serialize_module,
)

analysis_bp = Blueprint("analysis", __name__)


async def _is_owner() -> bool:
    membership = await get_user_org_membership(g.user_id)
    return bool(membership and is_org_owner(g.user_id, membership))


async def _require_visible_case(case_id: str):
    case = await get_case_for_user(case_id, g.user_id, is_owner=await _is_owner())
    if not case:
        abort(404)
    return case


@analysis_bp.route("/cases/<case_id>/evidence/<evidence_id>/modules")
@login_required
async def compatible_modules_view(case_id: str, evidence_id: str):
    await _require_visible_case(case_id)
    evidence = await get_evidence(evidence_id)
    if not evidence or evidence["case_id"] != case_id:
        abort(404)

    evidence_type = detect_evidence_type(evidence)
    modules = get_compatible_modules(evidence_type)
    return jsonify(
        {
            "case_id": case_id,
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "modules": [serialize_module(module) for module in modules],
        }
    )


@analysis_bp.route("/analysis/modules")
@login_required
async def list_modules_view():
    modules = list_modules()
    return jsonify({"modules": [serialize_module(module) for module in modules]})


@analysis_bp.route("/analysis/modules/<module_id>")
@login_required
async def get_module_view(module_id: str):
    module = get_module(module_id)
    if module is None or not module.enabled:
        abort(404)
    return jsonify(serialize_module(module))
