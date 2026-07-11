"""Auth business logic.

All rules ("email taken", "wrong password", "2FA required", ...) live here.
Routes call these functions and react to the exceptions they raise.
"""

from __future__ import annotations

from werkzeug.datastructures import FileStorage

from app.config import Config
from app.core import storage
from app.core.utils.passwords import hash_password, verify_password
from app.features.auth import repository
from app.features.auth.otp import create_otp, verify_otp
from app.features.auth.totp import (
    consume_backup_code,
    decode_backup_codes,
    encode_backup_codes,
    generate_backup_codes,
    generate_secret,
    qr_base64,
    verify_code,
)


class AuthError(Exception):
    """A user-visible auth failure — safe to display directly."""


class EmailNotVerifiedError(AuthError):
    """Raised when the user's email hasn't been confirmed via OTP yet."""

    def __init__(self, email: str):
        super().__init__("Please activate your account. Check your email for the code.")
        self.email = email


class TwoFactorRequiredError(Exception):
    """Raised when credentials are correct but a TOTP code is still needed."""

    def __init__(self, user_id: str):
        self.user_id = user_id


async def register(*, name: str, email: str, password: str) -> None:
    """Create an inactive user and send an activation OTP. Does NOT log the user in."""
    from app.core.email.client import send_activation_email

    if await repository.get_user_by_email(email):
        raise AuthError("An account with that email already exists.")

    await repository.create_user_with_password(
        name=name, email=email, password_hash=hash_password(password)
    )
    code = await create_otp(email, "activate")
    await send_activation_email(to=email, name=name, code=code)


async def activate_account(email: str, code: str) -> None:
    """Verify the activation OTP and mark the account active."""
    user = await repository.get_user_by_email(email)
    if not user:
        raise AuthError("Account not found.")
    if user["emailVerified"]:
        return  # already active — idempotent
    if not await verify_otp(email, "activate", code):
        raise AuthError("Invalid or expired code.")
    await repository.set_email_verified(user["id"])


async def resend_activation(email: str) -> None:
    """Issue a fresh activation OTP (rate limiting should be added later)."""
    from app.core.email.client import send_activation_email

    user = await repository.get_user_by_email(email)
    if not user or user["emailVerified"]:
        return  # silent — don't reveal whether the email exists
    code = await create_otp(email, "activate")
    await send_activation_email(to=email, name=user["name"], code=code)


async def authenticate(*, email: str, password: str) -> str:
    """
    Validate email+password credentials. Returns user_id on success.
    Raises EmailNotVerifiedError, TwoFactorRequiredError, or AuthError.

    Password is checked FIRST so that a wrong password and a non-existent
    account both return the same error — prevents account enumeration via
    error-message differences or timing differences between a missing-user
    fast-path and a real password check.
    """
    user = await repository.get_user_by_email(email)
    pw_hash = await repository.get_credential_password_hash(user["id"]) if user else None
    password_ok = pw_hash is not None and verify_password(pw_hash, password)
    if not password_ok:
        raise AuthError("Invalid email or password.")

    # Password is correct. Now reveal account-state issues to help the user.
    if not user["emailVerified"]:
        raise EmailNotVerifiedError(user["email"])

    if not user["isActive"]:
        raise AuthError("This account has been disabled.")

    if user["twoFactorEnabled"]:
        raise TwoFactorRequiredError(user["id"])

    return user["id"]


async def verify_2fa(user_id: str, code: str) -> None:
    """Verify a TOTP code or backup code for a pending login."""
    two_factor = await repository.get_two_factor(user_id)
    if not two_factor:
        raise AuthError("2FA is not configured for this account.")

    if verify_code(two_factor["secret"], code):
        return

    # Try backup code
    hashed = decode_backup_codes(two_factor["backupCodes"])
    success, remaining = consume_backup_code(hashed, code)
    if success:
        await repository.update_two_factor_backup_codes(
            user_id, encode_backup_codes(remaining)
        )
        return

    raise AuthError("Invalid code. Try your authenticator app or a backup code.")


# ── Password reset ────────────────────────────────────────────────────────────


async def forgot_password(email: str) -> None:
    """Send a password-reset OTP. Always succeeds silently to avoid email enumeration."""
    from app.core.email.client import send_reset_email

    user = await repository.get_user_by_email(email)
    if not user:
        return
    code = await create_otp(email, "reset")
    print(code)
    await send_reset_email(to=email, code=code)


async def reset_password(email: str, code: str, new_password: str) -> None:
    """Verify OTP and update the password."""
    user = await repository.get_user_by_email(email)
    if not user:
        raise AuthError("Account not found.")
    if not await verify_otp(email, "reset", code):
        raise AuthError("Invalid or expired code.")
    await repository.update_credential_password(user["id"], hash_password(new_password))
    if not user["emailVerified"]:
        await repository.set_email_verified(user["id"])


async def change_own_password(user_id: str, new_password: str) -> None:
    """Set a new password for an already-authenticated user (the forced
    first-login change for accounts created with an auto-generated
    password — being logged in already proves possession of the old one,
    so no code/old-password is required here)."""
    await repository.update_credential_password(user_id, hash_password(new_password))
    await repository.clear_must_change_password(user_id)


async def change_password(user_id: str, *, current_password: str, new_password: str) -> None:
    """Voluntary password change from the settings page - unlike
    change_own_password() above, this one isn't already-proven-by-login, so
    it requires the current password before accepting a new one."""
    pw_hash = await repository.get_credential_password_hash(user_id)
    if not pw_hash:
        raise AuthError("This account doesn't have a password set - sign in with your connected provider instead.")
    if not verify_password(pw_hash, current_password):
        raise AuthError("Current password is incorrect.")
    if len(new_password) < 8:
        raise AuthError("New password must be at least 8 characters.")
    await repository.update_credential_password(user_id, hash_password(new_password))


# ── Profile ───────────────────────────────────────────────────────────────────


async def update_profile(user_id: str, *, name: str, avatar: FileStorage | None) -> None:
    name = name.strip()
    if not name:
        raise AuthError("Name is required.")
    await repository.update_user_name(user_id, name)
    if avatar and avatar.filename:
        old_user = await repository.get_user_by_id(user_id)
        image_path = await storage.save_avatar(avatar)
        await repository.update_user_image(user_id, image_path)
        if old_user and old_user["image"] and old_user["image"].startswith(Config.MINIO_PUBLIC_URL):
            await storage.delete_file(old_user["image"])


# ── OAuth ─────────────────────────────────────────────────────────────────────


async def oauth_authenticate(provider_id: str, user_info: dict) -> str:
    """
    Find or create a user from an OAuth login. Returns user_id.
    Auto-links the OAuth account if a user with the same email already exists.
    If both no, brand-new person so create one.
    """
    # look up an OAuth account by provider and account ID (the account ID is Google's internal user ID for this person)
    account = await repository.get_account_by_provider(provider_id, user_info["id"])
    if account:
        return account["userId"]

    # Email already registered → link and return, but only if the provider
    # has actually verified this email address. An unverified provider email
    # could be a name squatting attack: attacker claims any email, gets
    # auto-linked to the victim's account.
    if user_info.get("email") and user_info.get("email_verified", False):
        user = await repository.get_user_by_email(user_info["email"])
        if user:
            await repository.create_oauth_account(
                user_id=user["id"],
                provider_id=provider_id,
                account_id=user_info["id"],
                access_token=user_info.get("access_token"),
                refresh_token=user_info.get("refresh_token"),
            )
            return user["id"]

    # Brand-new user
    if not user_info.get("email"):
        raise AuthError(
            f"No email address available from {provider_id}. "
            "Please make your email public or use another sign-in method."
        )
    return await repository.create_user_with_oauth(
        name=user_info["name"],
        email=user_info["email"],
        image=user_info.get("image"),
        provider_id=provider_id,
        account_id=user_info["id"],
        access_token=user_info.get("access_token"),
        refresh_token=user_info.get("refresh_token"),
    )


async def link_oauth_account(user_id: str, provider_id: str, user_info: dict) -> None:
    """Link an OAuth account to an already-logged-in user."""
    existing = await repository.get_account_by_provider(provider_id, user_info["id"])
    if existing:
        if existing["userId"] != user_id:
            raise AuthError("This account is already connected to a different user.")
        return  # already linked to the same user

    accounts = await repository.get_accounts_by_user(user_id)
    if any(a["providerId"] == provider_id for a in accounts):
        raise AuthError(f"You already have a {provider_id} account connected.")

    await repository.create_oauth_account(
        user_id=user_id,
        provider_id=provider_id,
        account_id=user_info["id"],
        access_token=user_info.get("access_token"),
        refresh_token=user_info.get("refresh_token"),
    )


async def disconnect_provider(user_id: str, provider_id: str) -> None:
    """Unlink an OAuth provider. Prevents lock-out by checking remaining login methods."""
    accounts = await repository.get_accounts_by_user(user_id)
    remaining = [a for a in accounts if a["providerId"] != provider_id]

    has_credential = any(a["providerId"] == "credential" for a in remaining)
    has_oauth = any(a["providerId"] not in ("credential",) for a in remaining)

    if not (has_credential or has_oauth):
        raise AuthError("Cannot disconnect — you need at least one way to log in.")

    await repository.delete_account_by_provider(user_id, provider_id)


# ── TOTP / 2FA setup ──────────────────────────────────────────────────────────


async def begin_totp_setup(user_id: str) -> tuple[str, str]:
    """Generate a new TOTP secret. Returns (secret, qr_base64). Not saved yet."""
    user = await repository.get_user_by_id(user_id)
    secret = generate_secret()
    qr = qr_base64(secret, user["email"])
    return secret, qr


async def confirm_totp_setup(user_id: str, secret: str, code: str) -> list[str]:
    """
    Verify the first TOTP code, save the secret, enable 2FA.
    Returns the plain backup codes (shown once, never stored in plain text).
    """
    if not verify_code(secret, code):
        raise AuthError("Invalid code. Make sure your authenticator app is in sync.")

    plain_codes, hashed_codes = generate_backup_codes()
    await repository.create_two_factor(
        user_id=user_id,
        secret=secret,
        backup_codes=encode_backup_codes(hashed_codes),
    )
    await repository.set_two_factor_enabled(user_id, True)
    return plain_codes


async def disable_totp(user_id: str) -> None:
    await repository.delete_two_factor(user_id)
    await repository.set_two_factor_enabled(user_id, False)


