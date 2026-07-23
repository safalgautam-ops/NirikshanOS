"""Security tests: SQL injection resistance (report §4.3's parameterised query builder claim), attacked at both layers the report names - the value layer (real classic injection strings sent through a real HTTP field) and the identifier layer (a query builder-level attempt to smuggle SQL through a column/table name instead of a value)."""

import pytest

from app.core.db.orm import _check_identifier
from tests.helpers import get_csrf


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "admin'--",
        "'; DROP TABLE user; --",
        "' UNION SELECT * FROM user --",
    ],
)
def test_classic_injection_strings_in_the_login_form_are_treated_as_literal_values(client, payload):
    """None of these should authenticate, crash the server, or return anything other than the normal 'invalid credentials' response - proving the value is bound as a parameter, never concatenated into SQL."""
    csrf = get_csrf(client, "/auth/login")
    resp = client.post(
        "/auth/login",
        data={"email": payload, "password": payload, "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert "Invalid email or password" in resp.get_data(as_text=True)


@pytest.mark.parametrize(
    "malicious_identifier",
    [
        "id; DROP TABLE user;--",
        "email` = `email` OR `1`=`1",
        "email -- ",
        "*/DROP TABLE user/*",
    ],
)
def test_query_builder_rejects_sql_injected_through_an_identifier(malicious_identifier):
    """Values are parameterised, but column/table names can't be - the builder instead validates every identifier against a strict letters/digits/underscore pattern before quoting it (report §4.3)."""
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        _check_identifier(malicious_identifier)


def test_a_plain_safe_identifier_is_still_accepted():
    _check_identifier("email")
    _check_identifier("organization_id")
