"""Security test: Redis-backed login rate limiting
(app/core/security/rate_limit.py - report §5.1), attacked directly by
actually exhausting the limit rather than only checking the code path
exists. auth/routes.py calls check_rate_limit(f"rate:login:{ip}",
max_attempts=10, window_seconds=900) at the very top of the login POST
handler; the test-suite-wide Redis flush (conftest._flush_test_redis)
guarantees this test starts from a clean counter.
"""
from tests.helpers import get_csrf


def test_11th_login_attempt_within_the_window_is_throttled(client):
    csrf = get_csrf(client, "/auth/login")

    for attempt in range(1, 11):
        resp = client.post(
            "/auth/login",
            data={"email": "nobody@example.test", "password": "wrong", "csrf_token": csrf},
        )
        assert resp.status_code == 200, f"attempt {attempt} unexpectedly throttled early"

    eleventh = client.post(
        "/auth/login",
        data={"email": "nobody@example.test", "password": "wrong", "csrf_token": csrf},
    )
    assert eleventh.status_code == 429
