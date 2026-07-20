"""E2E test: a real, ordinary (non-staff) logged-in user cannot reach an
admin-only page through the actual browser - the negative-path counterpart
to test_user_journey.py, confirming report §5.4's RBAC claim holds at the
rendered-page level, not only at the route level (already covered in
tests/integration/test_rbac_permissions.py).
"""
from playwright.sync_api import expect

BASE_URL = "http://localhost"


def test_ordinary_user_cannot_reach_an_admin_only_page(page, e2e_user):
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="email"]', e2e_user["email"])
    page.fill('input[name="password"]', e2e_user["password"])
    page.click('button[type="submit"]:has-text("Login")')
    expect(page).to_have_url(f"{BASE_URL}/dashboard", timeout=10_000)

    # No "Plans" (or any admin) link in the sidebar for an ordinary member.
    expect(page.locator('a[href="/admin/plans/"]')).to_have_count(0)

    # Navigating there directly is rejected, not silently rendered.
    resp = page.goto(f"{BASE_URL}/admin/plans/")
    assert resp.status == 403
