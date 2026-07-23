"""Integration tests: the require_permission decorator end to end (app/core/security/permissions.py - report §5.4), through a real route (GET /admin/plans/, gated by PLAN_VIEW) and a real granted-vs-ungranted role, not a unit test of the decorator in isolation."""

from app.features.organizations.repository import add_member as add_org_member

from tests.helpers import login_as


def test_anonymous_user_is_redirected_to_login(client):
    resp = client.get("/admin/plans/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_logged_in_user_without_the_permission_gets_403(client, make_user, make_org, run_async):
    user = make_user()
    org = make_org(created_by=user["id"])
    run_async(add_org_member(org["id"], user["id"]))
    login_as(client, user)

    resp = client.get("/admin/plans/")

    assert resp.status_code == 403


def test_logged_in_user_with_the_permission_is_allowed(
    client, make_user, make_org, grant_permission, run_async
):
    user = make_user()
    org = make_org(created_by=user["id"])
    run_async(add_org_member(org["id"], user["id"]))
    grant_permission(user["id"], "plans", "view")
    login_as(client, user)

    resp = client.get("/admin/plans/")

    assert resp.status_code == 200
