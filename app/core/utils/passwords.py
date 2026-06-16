"""Password hashing.

Argon2id via argon2-cffi - the password hashing winner of the Password
Hashing Competition, and the current OWASP recommendation. Each hash
embeds its own random salt and cost parameters, so verifying just needs
the stored hash string, not a separately-stored salt.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
