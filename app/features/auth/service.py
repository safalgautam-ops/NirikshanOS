"""Auth business logic: registration and credential login.

Kept separate from routes.py so the rules ("email already taken",
"account disabled", ...) aren't tangled up with request/response/cookie
handling.
"""

from app.core.utils.passwords import hash_password, verify_password
from app.features.auth import repository


class AuthError(Exception):
    """A user-facing auth failure - safe to show its message directly."""


async def register(*, name: str, email: str, password: str) -> str:
    if await repository.get_user_by_email(email):
        raise AuthError("An account with that email already exists.")

    return await repository.create_user_with_password(
        name=name, email=email, password_hash=hash_password(password)
    )


async def authenticate(*, email: str, password: str) -> str:
    user = await repository.get_user_by_email(email)
    if not user:
        # Same message as "wrong password" - don't reveal which emails exist.
        raise AuthError("Invalid email or password.")

    # user is now a plain dict returned by db_get — access values by key.
    if not user["isActive"]:
        raise AuthError("This account has been disabled.")

    password_hash = await repository.get_credential_password_hash(user["id"])
    if not password_hash or not verify_password(password_hash, password):
        raise AuthError("Invalid email or password.")

    return user["id"]
