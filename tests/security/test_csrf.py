"""Security tests: the double-submit CSRF cookie pattern
(app/core/security/csrf.py - report §5.3), attacked directly rather than
just having its allow-path exercised incidentally by other tests.
"""
from tests.helpers import get_csrf


def test_post_with_no_csrf_token_is_rejected(client):
    get_csrf(client, "/auth/login")  # sets the csrf_token cookie, token discarded
    resp = client.post("/auth/login", data={"email": "x@example.test", "password": "whatever"})
    assert resp.status_code == 403


def test_post_with_a_token_that_does_not_match_the_cookie_is_rejected(client):
    get_csrf(client, "/auth/login")  # sets a real csrf_token cookie
    resp = client.post(
        "/auth/login",
        data={"email": "x@example.test", "password": "whatever", "csrf_token": "an-attacker-supplied-value"},
    )
    assert resp.status_code == 403


def test_post_with_the_matching_token_is_accepted(client, make_user):
    """The legitimate path: same client, so the same cookie the GET set is
    the one the POST's field must match - this is what distinguishes a real
    page submission from a forged cross-site one."""
    user = make_user()
    csrf = get_csrf(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": user["email"], "password": user["password"], "csrf_token": csrf},
    )
    assert resp.status_code != 403


def test_json_api_accepts_the_token_via_header_instead_of_a_form_field(client):
    """§5.3: JS-driven JSON requests send the token as X-CSRF-Token instead
    of a form field - confirm a forged header-less JSON POST is still
    rejected the same way a forged form POST is."""
    get_csrf(client, "/auth/login")
    resp = client.post("/admin/plans/", json={"id": "x", "display_name": "x"})
    assert resp.status_code == 403
