"""Integration tests: the server-side session mechanism end to end (app/core/security/sessions.py - report §5.2), exercising the real test database rather than mocking it."""

from app.core.security.sessions import create_session, delete_session, get_user_id_for_token


def test_session_created_at_login_resolves_to_the_right_user(run_async, make_user):
    user = make_user()
    token = run_async(create_session(user["id"], "127.0.0.1", "pytest-agent"))

    resolved_user_id = run_async(get_user_id_for_token(token))

    assert resolved_user_id == user["id"]


def test_unknown_token_resolves_to_no_one(run_async):
    assert run_async(get_user_id_for_token("this-token-was-never-issued")) is None


def test_deleting_the_session_row_immediately_revokes_it(run_async, make_user):
    """Report §5.2's core comparison against JWTs: revocation is 'delete the row', effective on the very next lookup - proven here directly, not just asserted in prose."""
    user = make_user()
    token = run_async(create_session(user["id"], "127.0.0.1", "pytest-agent"))
    assert run_async(get_user_id_for_token(token)) == user["id"]

    run_async(delete_session(token))

    assert run_async(get_user_id_for_token(token)) is None
