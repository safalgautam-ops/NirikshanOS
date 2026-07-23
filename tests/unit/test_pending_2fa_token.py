"""Unit tests: the pending-2FA token (app/core/security/sessions.py)."""

import time
from unittest.mock import patch

from app.core.security.sessions import create_pending_2fa_token, verify_pending_2fa_token

SECRET = "test-secret-key"


def test_valid_unexpired_token_is_accepted():
    token = create_pending_2fa_token("user-123", SECRET)
    assert verify_pending_2fa_token(token, SECRET) == "user-123"


def test_tampered_signature_is_rejected():
    token = create_pending_2fa_token("user-123", SECRET)
    user_id, ts, sig = token.split(".", 2)
    tampered_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    tampered = f"{user_id}.{ts}.{tampered_sig}"
    assert verify_pending_2fa_token(tampered, SECRET) is None


def test_wrong_secret_key_is_rejected():
    token = create_pending_2fa_token("user-123", SECRET)
    assert verify_pending_2fa_token(token, "a-completely-different-secret") is None


def test_expired_token_is_rejected():
    """TTL is 300s (_PENDING_2FA_TTL)."""
    token = create_pending_2fa_token("user-123", SECRET)
    real_time = time.time
    with patch("app.core.security.sessions.time.time", return_value=real_time() + 301):
        assert verify_pending_2fa_token(token, SECRET) is None


def test_malformed_token_is_rejected():
    assert verify_pending_2fa_token("not-a-real-token", SECRET) is None
    assert verify_pending_2fa_token("only.two-parts", SECRET) is None
