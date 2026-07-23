"""Unit tests: Argon2id password hashing (app/core/utils/passwords.py)."""

from app.core.utils.passwords import hash_password, verify_password


def test_correct_password_verifies():
    hashed = hash_password("correct horse battery staple")
    assert verify_password(hashed, "correct horse battery staple") is True


def test_wrong_password_fails():
    hashed = hash_password("correct horse battery staple")
    assert verify_password(hashed, "wrong password entirely") is False


def test_same_password_hashed_twice_differs():
    """Argon2id embeds a fresh random salt every call - two hashes of the same password must never be byte-identical."""
    first = hash_password("same input twice")
    second = hash_password("same input twice")
    assert first != second
    assert verify_password(first, "same input twice") is True
    assert verify_password(second, "same input twice") is True
