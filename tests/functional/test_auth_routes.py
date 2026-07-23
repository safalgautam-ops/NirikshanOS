"""Functional/route tests: /auth/login and /auth/register in isolation via Flask's test client - each test checks one route's own request -> response contract (report §5.1/§5.2)."""

from tests.helpers import get_csrf


def test_login_valid_credentials_sets_session_cookie_and_redirects(client, make_user):
    user = make_user()
    csrf = get_csrf(client, "/auth/login")

    resp = client.post(
        "/auth/login",
        data={"email": user["email"], "password": user["password"], "csrf_token": csrf},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")
    assert "session_token" in resp.headers.get("Set-Cookie", "")


def test_login_wrong_password_shows_error_no_cookie_set(client, make_user):
    user = make_user()
    csrf = get_csrf(client, "/auth/login")

    resp = client.post(
        "/auth/login",
        data={"email": user["email"], "password": "definitely-wrong", "csrf_token": csrf},
    )

    assert resp.status_code == 200
    assert "Invalid email or password" in resp.get_data(as_text=True)
    assert "session_token" not in resp.headers.get("Set-Cookie", "")


def test_login_nonexistent_email_gives_same_error_as_wrong_password(client):
    """Report §5.1: password is checked first specifically so a wrong password and a non-existent account produce the identical error - prevents account enumeration."""
    csrf = get_csrf(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": "no-such-user@example.test", "password": "whatever", "csrf_token": csrf},
    )
    assert "Invalid email or password" in resp.get_data(as_text=True)


def test_register_duplicate_email_is_rejected(client, make_user):
    existing = make_user()
    csrf = get_csrf(client, "/auth/register")

    resp = client.post(
        "/auth/register",
        data={
            "name": "Someone Else",
            "email": existing["email"],
            "password": "another-password-123",
            "confirm_password": "another-password-123",
            "csrf_token": csrf,
        },
    )

    assert resp.status_code == 200
    assert "already exists" in resp.get_data(as_text=True)


def test_register_password_too_short_is_rejected_before_hitting_the_service(client):
    csrf = get_csrf(client, "/auth/register")
    resp = client.post(
        "/auth/register",
        data={
            "name": "New Person",
            "email": "new-person@example.test",
            "password": "short",
            "confirm_password": "short",
            "csrf_token": csrf,
        },
    )
    assert "at least 8 characters" in resp.get_data(as_text=True)
