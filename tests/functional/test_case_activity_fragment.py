"""Functional test: GET /cases/<case_id>/activity (the Activity tab's HTMX
fragment route, app/features/cases/routes.py::activity_fragment_view).

Regression guard for a real bug: the case detail page's tabs are a
client-side show/hide toggle on one already-loaded page, so a note/report
saved through a background request never showed up on the Activity tab
without a full browser reload. This route is what the tab now re-fetches
from every time it's opened - this test checks the route itself, on both
the visible-case and not-a-member boundary (the same 404-not-403 rule
tested elsewhere in this suite, applied to the new route too).
"""
from app.features.audit import service as audit_service
from app.features.cases.repository import create_case
from app.features.organizations.repository import add_member as add_org_member

from tests.helpers import login_as


def test_activity_fragment_returns_recorded_events_for_a_visible_case(client, make_user, make_org, run_async):
    user = make_user()
    org = make_org(created_by=user["id"])
    run_async(add_org_member(org["id"], user["id"]))
    case_id = run_async(create_case(
        organization_id=org["id"], title="Fragment Visible Case", description="",
        classification="internal", severity="low", forensic_status="not_started",
        created_by=user["id"],
    ))
    # create_case is the bare repository function (matching this suite's
    # usual pattern) - it has no reason to write an audit row itself, that
    # only happens in the real create_view route. Seed one directly so this
    # test is actually checking the fragment's rendering, not case creation.
    run_async(audit_service.record_case_activity(
        case_id=case_id, actor_id=user["id"], action=audit_service.NOTE_SAVED, target_label="A note",
    ))
    login_as(client, user)

    resp = client.get(f"/cases/{case_id}/activity")

    assert resp.status_code == 200
    assert "Note saved" in resp.get_data(as_text=True)


def test_activity_fragment_returns_404_for_a_case_you_cannot_see(client, make_user, make_org, run_async):
    owner = make_user()
    outsider = make_user()
    owner_org = make_org(created_by=owner["id"])
    outsider_org = make_org(created_by=outsider["id"])
    run_async(add_org_member(owner_org["id"], owner["id"]))
    run_async(add_org_member(outsider_org["id"], outsider["id"]))
    case_id = run_async(create_case(
        organization_id=owner_org["id"], title="Fragment Private Case", description="",
        classification="internal", severity="low", forensic_status="not_started",
        created_by=owner["id"],
    ))
    login_as(client, outsider)

    resp = client.get(f"/cases/{case_id}/activity")

    assert resp.status_code == 404
