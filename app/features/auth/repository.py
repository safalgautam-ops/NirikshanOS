"""Raw SQL access to the BetterAuth-style `user`/`account` tables.

These tables (migrations/001.initial_schema.sql) use varchar(191) string
primary keys assigned by the app - not the auto-increment int id the
Model base class assumes - so this talks to core/db/pool directly
instead of going through Model.

BetterAuth convention: a user's password isn't a column on `user` at
all. It lives in `account`, as the row where providerId = 'credential'
for that user - the same table a future Google/GitHub login would add a
row to (providerId = 'google', with OAuth tokens instead of a password).

So "email + password login" is just one provider among potentially many.
The password is the credential for the 'credential' provider specifically.
If Alice later adds "Sign in with Google," that's a new row in the same account table with providerId
= 'google' and OAuth tokens instead of a password — the user row doesn't change at all.
This is why the password isn't on user: the design treats all login methods uniformly as rows in account,
and a password is simply the data for one particular method.
"""

from app.core.db.pool import execute, fetchone
from app.core.utils.ids import new_id


async def get_user_by_email(email: str) -> tuple | None:
    return await fetchone(
        "SELECT id, name, email, isActive, twoFactorEnabled FROM user WHERE email = %s",
        (email,),
    )


async def get_user_by_id(user_id: str) -> tuple | None:
    return await fetchone(
        "SELECT id, name, email, isActive, twoFactorEnabled FROM user WHERE id = %s",
        (user_id,),
    )


async def create_user(*, name: str, email: str) -> str:
    user_id = new_id()  # mint the UUID primary key up front
    await execute(
        "INSERT INTO user (id, name, email) VALUES (%s, %s, %s)",
        (user_id, name, email),
    )
    return user_id


async def create_credential_account(*, user_id: str, password_hash: str) -> None:
    await execute(
        "INSERT INTO account (id, accountId, providerId, userId, password) "
        "VALUES (%s, %s, 'credential', %s, %s)",
        (new_id(), user_id, user_id, password_hash),
    )


async def get_credential_password_hash(user_id: str) -> str | None:
    row = await fetchone(
        "SELECT password FROM account WHERE userId = %s AND providerId = 'credential'",
        (user_id,),
    )
    return row[0] if row else None
