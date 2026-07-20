"""Security tests: authentication/authorisation boundaries (report §4.5,
§5.4) - both decorator families reject anonymous access the same way, and
an inaccessible case returns 404 rather than 403, so an attacker can't use
the response code to confirm a guessed case id exists.
"""
from app.features.cases.repository import create_case
from app.features.organizations.repository import add_member as add_org_member

from tests.helpers import login_as


def test_unauthenticated_request_to_a_login_required_route_is_redirected(client):
    resp = client.get("/cases/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_unauthenticated_request_to_a_permission_gated_route_is_redirected(client):
    resp = client.get("/admin/instances/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_case_outside_your_organization_returns_404_not_403(client, make_user, make_org, run_async):
    """The specific report §4.5 claim: a non-member gets 404, never 403 -
    a 403 would confirm the id exists at all, which is exactly the leak a
    404-always policy prevents."""
    owner = make_user()
    outsider = make_user()
    owner_org = make_org(created_by=owner["id"])
    outsider_org = make_org(created_by=outsider["id"])
    run_async(add_org_member(owner_org["id"], owner["id"]))
    run_async(add_org_member(outsider_org["id"], outsider["id"]))

    case_id = run_async(
        create_case(
            organization_id=owner_org["id"],
            title="Private Case",
            description="",
            classification="internal",
            severity="low",
            forensic_status="not_started",
            created_by=owner["id"],
        )
    )

    login_as(client, outsider)
    resp = client.get(f"/cases/{case_id}")

    assert resp.status_code == 404


def test_case_you_were_never_added_to_also_returns_404(client, make_user, make_org, run_async):
    """Same organisation, not the same result: being an org member is not
    enough on its own - membership on the specific case is what
    _require_visible_case actually checks (report §4.2)."""
    creator = make_user()
    same_org_non_member = make_user()
    org = make_org(created_by=creator["id"])
    run_async(add_org_member(org["id"], creator["id"]))
    run_async(add_org_member(org["id"], same_org_non_member["id"]))

    case_id = run_async(
        create_case(
            organization_id=org["id"],
            title="Not Shared",
            description="",
            classification="internal",
            severity="low",
            forensic_status="not_started",
            created_by=creator["id"],
        )
    )

    login_as(client, same_org_non_member)
    resp = client.get(f"/cases/{case_id}")

    assert resp.status_code == 404
