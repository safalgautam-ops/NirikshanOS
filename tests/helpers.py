"""Small shared helpers for functional/integration/security tests that go
through Flask's test client (not used by pure unit tests)."""
from __future__ import annotations

import re

_CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]*)"')


def get_csrf(client, path: str = "/auth/login") -> str:
    """GET a page that renders the csrf_field() macro and pull the token out
    of the hidden input - the test client's cookie jar automatically carries
    the matching csrf_token cookie forward to the next request on the same
    client, exactly like a real browser."""
    resp = client.get(path)
    match = _CSRF_RE.search(resp.get_data(as_text=True))
    assert match, f"no csrf_token field found on {path}"
    return match.group(1)


def login_as(client, user: dict) -> None:
    """Logs a test-client session in as `user` (from the make_user fixture)
    via the real /auth/login route, so subsequent requests on the same
    client carry a genuine session cookie."""
    csrf = get_csrf(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": user["email"], "password": user["password"], "csrf_token": csrf},
    )
    assert resp.status_code == 302, f"login failed: {resp.get_data(as_text=True)[:300]}"
