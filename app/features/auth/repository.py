"""DB access for all auth-related tables.

Thin functions that wrap the ORM query builder. Business rules live in
service.py; this file only knows about columns and tables.
"""

from __future__ import annotations

from app.core.db.orm import db, raw_sql
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


async def create_user_with_password(
    *, name: str, email: str, password_hash: str
) -> str:
    """Create user row + credential account atomically. User starts inactive (needs OTP)."""
    user_id = new_id()
    async with db.transaction():
        await db.table("user").create(
            {
                "id": user_id,
                "name": name,
                "email": email,
                "emailVerified": False,
                "isActive": False,
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


async def get_passkeys_by_user(user_id: str) -> list:
    return await db.table("passkey").where("userId", user_id).all(allow_full_table=True)


async def get_passkey_by_credential_id(credential_id: str):
    return await db.table("passkey").where("credentialID", credential_id).first()


async def create_passkey(
    *,
    user_id: str,
    name: str | None,
    credentialID: str,
    publicKey: str,
    counter: int,
    backedUp: bool,
    deviceType: str,
    transports: str,
    aaguid: str | None,
) -> None:
    await db.table("passkey").create(
        {
            "id": new_id(),
            "name": name,
            "userId": user_id,
            "credentialID": credentialID,
            "publicKey": publicKey,
            "counter": counter,
            "backedUp": backedUp,
            "deviceType": deviceType,
            "transports": transports,
            "aaguid": aaguid,
        }
    )


async def update_passkey_counter(credential_id: str, counter: int) -> None:
    await (
        db.table("passkey")
        .where("credentialID", credential_id)
        .patch({"counter": counter})
    )


async def delete_passkey(passkey_id: str, user_id: str) -> None:
    # Require user_id to prevent cross-user deletion
    await db.table("passkey").where("id", passkey_id).where("userId", user_id).delete()


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
