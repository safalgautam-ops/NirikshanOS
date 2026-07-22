"""Security test: server-side plan-tier enforcement for running analysis
modules (app/features/analysis/policy.py::check_can_run).

The UI was recently changed to hide plan-locked modules from both the
Analyze dialog and the Results Canvas (they used to render with a lock icon
and an upgrade prompt instead). That UI change is convenience only - the
real security boundary has always been this server-side policy check, run
independently of whatever the client chose to display. This test exists to
prove that boundary still holds on its own: even a request built by hand
for a module the UI would never show must still be rejected.

The disposable test database starts with no catalogue data at all (see
migration 025's own comment: "No seed rows: admins register their own,
nothing hardcoded" - the real instances/modules only exist in the dev
database via the separate, dev-only seed_catalog.py). So this test seeds
its own minimal instance + enterprise-tier module directly, rather than
assuming a specific dev-seeded module id exists here.
"""
from app.core.db.orm import db
from app.core.utils.ids import new_id
from app.features.cases.repository import create_case
from app.features.evidence.repository import create_evidence
from app.features.organizations.repository import add_member as add_org_member
from app.features.plans.service import assign_plan

from tests.conftest import unique
from tests.helpers import get_csrf, login_as


def _seed_enterprise_module(run_async) -> str:
    """A real, ready-to-run instance + module def, at tier "enterprise" -
    the highest tier, so only the Enterprise plan's allowed_tiers includes
    it (see migrations/019 for the four plans' seeded allowed_tiers).

    A subscription snapshot resolves allowed_instance_ids once, from the
    live plan_instances join table, at the moment assign_plan() is called
    (see plans/service.py::_build_plan_snapshot) - so the instance must be
    linked to the "enterprise" plan here, before either test assigns a plan,
    or even the Enterprise-plan test would still get rejected on the
    instance check right after passing the tier check.
    """
    instance_id = unique("instance")
    run_async(db.table("instances").create({
        "id": instance_id,
        "display_name": "Test Instance",
        "image_tag": f"nirikshan/{instance_id}:1.0",
        "is_active": 1,
        "image_status": "ready",
    }))
    run_async(db.table("plan_instances").create({"plan_id": "enterprise", "instance_id": instance_id}))
    module_id = unique("module")
    run_async(db.table("analysis_module_defs").create({
        "id": module_id,
        "display_name": "Test Enterprise Module",
        "instance_id": instance_id,
        "tier": "enterprise",
        "is_enabled": 1,
        "status": "published",
        "source": "custom",
    }))
    return module_id


def _make_case_and_evidence(run_async, org_id, user_id):
    case_id = run_async(
        create_case(
            organization_id=org_id,
            title="Tier Enforcement Case",
            description="",
            classification="internal",
            severity="low",
            forensic_status="not_started",
            created_by=user_id,
        )
    )
    evidence_id = run_async(
        create_evidence(
            case_id=case_id,
            filename="sample.bin",
            size_bytes=1024,
            s3_key="test/sample.bin",
            upload_id="test-upload",
            part_size=1024,
            total_parts=1,
            uploaded_by=user_id,
        )
    )
    return case_id, evidence_id


def test_free_plan_org_cannot_run_an_enterprise_tier_module(client, make_user, make_org, run_async):
    module_id = _seed_enterprise_module(run_async)
    owner = make_user()
    org = make_org(created_by=owner["id"])
    run_async(add_org_member(org["id"], owner["id"]))
    run_async(assign_plan(
        org_id=org["id"], plan_id="free", billing_period="monthly",
        ends_at=None, notes=None, created_by=None,
    ))
    case_id, evidence_id = _make_case_and_evidence(run_async, org["id"], owner["id"])

    login_as(client, owner)
    csrf = get_csrf(client, f"/cases/{case_id}")
    resp = client.post(
        f"/cases/{case_id}/evidence/{evidence_id}/analyze",
        json={"module_ids": [module_id]},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 403
    body = resp.get_json()
    assert "violations" in body
    assert body["violations"][0]["module_id"] == module_id
    assert "higher plan" in body["violations"][0]["reason"]


def test_enterprise_plan_org_can_submit_the_same_module(client, make_user, make_org, run_async):
    """Same module, same request shape, only the plan differs - confirms the
    403 above is really about the plan tier and not something else about the
    request (a wrong module id, missing evidence, etc)."""
    module_id = _seed_enterprise_module(run_async)
    owner = make_user()
    org = make_org(created_by=owner["id"])
    run_async(add_org_member(org["id"], owner["id"]))
    run_async(assign_plan(
        org_id=org["id"], plan_id="enterprise", billing_period="monthly",
        ends_at=None, notes=None, created_by=None,
    ))
    case_id, evidence_id = _make_case_and_evidence(run_async, org["id"], owner["id"])

    login_as(client, owner)
    csrf = get_csrf(client, f"/cases/{case_id}")
    resp = client.post(
        f"/cases/{case_id}/evidence/{evidence_id}/analyze",
        json={"module_ids": [module_id]},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 201
