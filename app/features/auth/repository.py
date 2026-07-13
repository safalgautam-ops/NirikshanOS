"""DB access for all auth-related tables.

Thin functions that wrap the ORM query builder. Business rules live in
service.py; this file only knows about columns and tables.
"""

from __future__ import annotations

from app.core.db.orm import db
from app.core.utils.ids import new_id


async def get_user_by_email(email: str):
    return (
        await db.table("user").where("email", email).first()
    )  # Returns a Row (dict-like object with attribute access)


async def get_user_by_id(user_id: str):
    return await db.table("user").where("id", user_id).first()


# called once after a successful OTP activation
async def set_email_verified(user_id: str) -> None:
    await (
        db.table("user")
        .where("id", user_id)
        .patch(
            {
                "emailVerified": True,
                "isActive": True,
            }
        )
    )


async def set_two_factor_enabled(user_id: str, enabled: bool) -> None:
    await db.table("user").where("id", user_id).patch({"twoFactorEnabled": enabled})


async def update_user_name(user_id: str, name: str) -> None:
    await db.table("user").where("id", user_id).patch({"name": name})


async def update_user_image(user_id: str, image_path: str) -> None:
    await db.table("user").where("id", user_id).patch({"image": image_path})


async def create_user_with_password(
    *,
    name: str,
    email: str,
    password_hash: str,
    is_active: bool = False,
    email_verified: bool = False,
    must_change_password: bool = False,
) -> str:
    """Create user row + credential account atomically.

    Defaults match self-registration (inactive, needs an activation OTP).
    Admin-created accounts (e.g. staff) pass is_active=True/email_verified=True
    since an admin is already vouching for them, plus must_change_password=True
    when the password was auto-generated rather than chosen by the user.
    """
    user_id = new_id()
    async with db.transaction():
        await db.table("user").create(
            {
                "id": user_id,
                "name": name,
                "email": email,
                "emailVerified": email_verified,
                "isActive": is_active,
                "must_change_password": must_change_password,
            }
        )
        await db.table("account").create(
            {
                "id": new_id(),
                "accountId": user_id,
                "providerId": "credential",
                "userId": user_id,
                "password": password_hash,
            }
        )
    return user_id


# access tokens and refresh tokens by provided by Google and Github
async def create_user_with_oauth(
    *,
    name: str,
    email: str,
    image: str | None,
    provider_id: str,
    account_id: str,
    access_token: str | None,
    refresh_token: str | None,
) -> str:
    user_id = new_id()
    async with db.transaction():
        await db.table("user").create(
            {
                "id": user_id,
                "name": name,
                "email": email,
                "image": image,
                "emailVerified": True,
                "isActive": True,
            }
        )
        await db.table("account").create(
            {
                "id": new_id(),
                "accountId": account_id,
                "providerId": provider_id,
                "userId": user_id,
                "accessToken": access_token,
                "refreshToken": refresh_token,
            }
        )
    return user_id


async def get_credential_account_by_user_id(user_id: str):
    return await (
        db.table("account")
        .where("userId", user_id)
        .where("providerId", "credential")
        .first()
    )


async def get_credential_password_hash(user_id: str) -> str | None:
    account = await get_credential_account_by_user_id(user_id)
    return account["password"] if account else None


async def update_credential_password(user_id: str, password_hash: str) -> None:
    await (
        db.table("account")
        .where("userId", user_id)
        .where("providerId", "credential")
        .patch({"password": password_hash})
    )


async def clear_must_change_password(user_id: str) -> None:
    await db.table("user").where("id", user_id).patch({"must_change_password": False})


async def get_account_by_provider(provider_id: str, account_id: str):
    return await (
        db.table("account")
        .where("providerId", provider_id)
        .where("accountId", account_id)
        .first()
    )


async def get_accounts_by_user(user_id: str) -> list:
    return await db.table("account").where("userId", user_id).all(allow_full_table=True)


async def create_oauth_account(
    *,
    user_id: str,
    provider_id: str,
    account_id: str,
    access_token: str | None,
    refresh_token: str | None,
) -> None:
    await db.table("account").create(
        {
            "id": new_id(),
            "accountId": account_id,
            "providerId": provider_id,
            "userId": user_id,
            "accessToken": access_token,
            "refreshToken": refresh_token,
        }
    )


async def delete_account_by_provider(user_id: str, provider_id: str) -> None:
    await (
        db.table("account")
        .where("userId", user_id)
        .where("providerId", provider_id)
        .delete()
    )


async def get_two_factor(user_id: str):
    return await db.table("twoFactor").where("userId", user_id).first()


async def create_two_factor(*, user_id: str, secret: str, backup_codes: str) -> None:
    # Delete any existing record first (re-setup scenario)
    await db.table("twoFactor").where("userId", user_id).delete()
    await db.table("twoFactor").create(
        {
            "id": new_id(),
            "secret": secret,
            "backupCodes": backup_codes,
            "userId": user_id,
        }
    )


async def update_two_factor_backup_codes(user_id: str, backup_codes: str) -> None:
    await (
        db.table("twoFactor")
        .where("userId", user_id)
        .patch(
            {"backupCodes": backup_codes}
        )  # patch is the ORM's way of doing a partial update (change only specific column you name)
    )


async def delete_two_factor(user_id: str) -> None:
    await db.table("twoFactor").where("userId", user_id).delete()
