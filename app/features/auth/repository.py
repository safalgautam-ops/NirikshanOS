"""DB access for the BetterAuth-style `user`/`account` tables.

No Model subclasses here. Instead:
  - A schema dict declares the columns and their types once per table.
  - Generic orm functions (db_insert, db_get, …) receive the table name
    and schema explicitly, validate the data, and build safe SQL.
  - Every function returns either a plain dict or None — no special object.

BetterAuth convention: passwords are NOT stored on the `user` row.
They live in the `account` table, in the row where providerId = 'credential'.
The same `account` table will later hold Google/GitHub OAuth rows
(providerId = 'google', with tokens instead of a password). This is why
the password column isn't on `user` at all — all login methods are
represented uniformly as rows in `account`.
"""

from app.core.db.fields import BoolField, StringField
from app.core.db.orm import Schema, db_get, db_insert
from app.core.utils.ids import new_id

# Schema: plain dict of {column_name: Field_instance}.
# This replaces the "class User(Model)" approach — no inheritance needed.
# The ORM reads these field types to validate values and build column lists.

USER_SCHEMA: Schema = {
    # required=False because the DB assigns/generates it (we pass it ourselves via new_id())
    "id": StringField(max_length=191, required=False),
    "name": StringField(max_length=191),
    "email": StringField(max_length=191),
    # required=False + default: the DB has its own DEFAULT for these, so we
    # don't include them in the INSERT — MySQL fills them in automatically.
    "isActive": BoolField(required=False, default=True),
    "twoFactorEnabled": BoolField(required=False, default=False),
}

ACCOUNT_SCHEMA: Schema = {
    "id": StringField(max_length=191, required=False),
    # accountId: the provider's own identifier for the user.
    # For 'credential' (password) logins we just reuse the user's id.
    # For 'google' it would be Google's subject ID.
    "accountId": StringField(max_length=255),
    # providerId: which login method this row represents.
    # 'credential' = email+password, 'google' = Google OAuth, etc.
    "providerId": StringField(max_length=255),
    "userId": StringField(max_length=191),
    # required=False: 'google' rows have tokens here instead of a password.
    "password": StringField(max_length=65535, required=False),
}


async def get_user_by_email(email: str) -> dict | None:
    # db_get selects exactly the columns in USER_SCHEMA and returns a dict.
    # "email" is whitelisted against USER_SCHEMA before it touches the SQL.
    return await db_get("user", USER_SCHEMA, where={"email": email})


async def get_user_by_id(user_id: str) -> dict | None:
    return await db_get("user", USER_SCHEMA, where={"id": user_id})


async def create_user(*, name: str, email: str) -> str:
    user_id = new_id()  # generate the string PK up front (BetterAuth tables don't auto-increment)
    await db_insert("user", USER_SCHEMA, {
        "id": user_id,
        "name": name,
        "email": email,
        # isActive / twoFactorEnabled are omitted → MySQL uses its DEFAULT values
    })
    return user_id


async def create_credential_account(*, user_id: str, password_hash: str) -> None:
    await db_insert("account", ACCOUNT_SCHEMA, {
        "id": new_id(),
        "accountId": user_id,       # reuse user id as the credential account id
        "providerId": "credential", # marks this as an email+password account
        "userId": user_id,
        "password": password_hash,
    })


async def get_credential_password_hash(user_id: str) -> str | None:
    # Look up the credential account: the row for this user where the
    # provider is 'credential' (i.e. the email+password login method).
    account = await db_get(
        "account",
        ACCOUNT_SCHEMA,
        where={"userId": user_id, "providerId": "credential"},
    )
    return account["password"] if account else None
