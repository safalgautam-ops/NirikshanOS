"""
DB access for the BetterAuth-style `user`/`account` tables.

This file is a "repository" layer: a thin set of functions that wrap database
operations so the rest of the app calls clear names like `get_user_by_email(...)`
instead of writing query-builder chains everywhere. It keeps all SQL/table
knowledge in one place.

Background on the two tables:
- `user`    -> one row per person (id, name, email, isActive, ...).
- `account` -> how a user logs in. BetterAuth supports many login methods
               ("providers"), so a single user can have several account rows.
               A "credential" account is the email+password login method, and
               its `password` column holds the hashed password.
"""

from __future__ import (
    annotations,  # lets type hints be lazy/forward-referenced (no runtime cost)
)

# The query builder (`db`) and the safe-raw-SQL wrapper (`raw_sql`) from the ORM layer.
from app.core.db.orm import db, raw_sql

# Generates a fresh unique id string for new rows (e.g. a UUID-like value).
from app.core.utils.ids import new_id


async def get_user_by_email(email: str):
    """Find a single user by their email address (or None if no match)."""
    # db.table("user")        -> start a query on the `user` table
    # .where("email", email)  -> filter: WHERE email = <email>
    # .first()                -> run it, return just the first row (or None)
    return await db.table("user").where("email", email).first()


async def get_user_by_id(user_id: str):
    """Find a single user by their id (or None if no match)."""
    return await db.table("user").where("id", user_id).first()


async def create_user(*, name: str, email: str) -> str:
    """
    Create a new user row and return its id.
    (The `*` forces callers to pass name/email by name, e.g. create_user(name=..., email=...),
    which prevents accidentally swapping the two strings.)
    """
    user_id = (
        new_id()
    )  # we generate the id ourselves so we can return it without a second query
    # .create({...}) builds and runs an INSERT with these column/value pairs.
    await db.table("user").create({"id": user_id, "name": name, "email": email})
    return user_id  # hand the new id back to the caller


async def create_credential_account(*, user_id: str, password_hash: str) -> None:
    """
    Create the email+password ("credential") login record for an existing user.
    NOTE: it stores password_hash, never the raw password — hashing happens before this is called.
    """
    await db.table(
        "account"
    ).create(
        {
            "id": new_id(),  # unique id for this account row
            "accountId": user_id,  # BetterAuth's "account id" — here it mirrors the user id
            "providerId": "credential",  # marks this as the email/password login method
            "userId": user_id,  # which user this login belongs to
            "password": password_hash,  # the HASHED password (safe to store)
        }
    )


async def create_user_with_password(
    *, name: str, email: str, password_hash: str
) -> str:
    """
    Create BOTH a user AND their credential account together, as one all-or-nothing unit.

    Why a transaction here? These two inserts must succeed together. If we created the
    user but the account insert failed, we'd be left with a user who can never log in.
    The transaction guarantees: either both rows are saved, or neither is.
    """
    user_id = new_id()  # id for the new user row
    account_id = new_id()  # id for the new account row

    # `async with db.transaction():` opens a transaction. Everything inside is provisional.
    # If the block finishes normally -> all changes are committed (saved) at once.
    # If anything inside raises an error -> all changes are rolled back (undone).
    async with db.transaction():
        await db.table("user").create({"id": user_id, "name": name, "email": email})
        await db.table("account").create(
            {
                "id": account_id,
                "accountId": user_id,
                "providerId": "credential",
                "userId": user_id,
                "password": password_hash,
            }
        )
    # (Reaching here means both inserts succeeded and the transaction committed.)
    return user_id


async def get_credential_account_by_user_id(user_id: str):
    """
    Fetch a user's email+password login record (or None).
    A user can have multiple account rows (different login methods), so we filter on
    BOTH the userId AND providerId="credential" to pick out the right one.
    """
    return (
        await db.table("account")
        .where("userId", user_id)  # WHERE userId = <user_id>
        .where("providerId", "credential")  # AND providerId = 'credential'
        .first()  # take the first match (or None)
    )


async def get_credential_password_hash(user_id: str) -> str | None:
    """
    Return just the stored password HASH for a user (or None if they have no credential account).
    Used during login to compare against the password the user typed.
    """
    account = await get_credential_account_by_user_id(user_id)
    # If an account row exists, pull out its "password" field; otherwise return None.
    return account["password"] if account else None


async def get_valid_session_by_token(token: str):
    """
    Look up a login session by its token, but ONLY return it if the session is still
    valid: not expired AND belonging to an active user. Also pulls some user fields
    along with it in a single query (via a JOIN).

    Returns the matching row (with userId, email, name, isActive) or None.
    """
    return await (
        # Start on the `session` table, giving it the short alias "s" to reference its columns.
        db.table("session", alias="s")
        # Select the columns we care about: a few from session (s) and a few from user (u).
        .select("s.userId", "u.email", "u.name", "u.isActive")
        # Bring in the `user` table (aliased "u"), matching session.userId to user.id.
        # LEFT JOIN keeps the session row even if (somehow) no matching user exists.
        .left_join("user", "s.userId", "u.id", alias="u")
        # Match the specific session by its token: WHERE s.token = <token>
        .where("s.token", token)
        # Only keep sessions that haven't expired yet. This needs a SQL function
        # (UTC_TIMESTAMP()), which the normal .where() can't express — so we use raw_sql.
        # raw_sql(...) is the deliberate, safety-checked way to inject raw SQL.
        .where_raw(raw_sql("s.expiresAt > UTC_TIMESTAMP()"))
        # And only if the user is currently active: AND u.isActive = True
        .where("u.isActive", True)
        # Run it and return the first matching row (or None).
        .first()
    )
