"""OTP (one-time password) generation and verification.

Codes are 6-digit numeric strings stored hashed (argon2) in the
`verification` table so the DB row reveals nothing on its own.
Each identifier is deleted after one successful use or when a new
code is requested (no stacking).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.core.db.orm import db, raw_sql
from app.core.utils.ids import new_id
from app.core.utils.passwords import hash_password, verify_password

_TTL = timedelta(minutes=10)  # code is dead even if it was never used
_LENGTH = 6  # always 6-digit number


# defining one composite key for email+purpose to avoid collisions
def _identifier(email: str, purpose: str) -> str:
    return f"{email}:{purpose}"


# generates a new OTP code(OS's cryptographically secure random number generator) for the given email and purpose
async def create_otp(email: str, purpose: str) -> str:
    code = "".join(secrets.choice("0123456789") for _ in range(_LENGTH))
    identifier = _identifier(email, purpose)

    # Remove any existing pending code for this email+purpose before issuing a new one
    await db.table("verification").where("identifier", identifier).delete()
    # Insert the new code into the database with identifier
    await db.table("verification").create(
        {
            "id": new_id(),
            "identifier": identifier,
            "value": hash_password(code),
            "expiresAt": datetime.now(timezone.utc) + _TTL,
        }
    )
    return code


# identifier should match and the expiry time is in the future
async def verify_otp(email: str, purpose: str, code: str) -> bool:
    identifier = _identifier(email, purpose)
    row = await (
        db.table("verification")
        .where("identifier", identifier)
        # a normal orm where call compares column to a value
        # not comparing column to a value — using raw SQL to check expiry time
        # If you tried to pass the string "expiresAt > UTC_TIMESTAMP()" through the normal .where() path, the ORM would do its safety job too well: it would quote the whole thing as a literal string and compare against it, which is nonsense.
        .where_raw(
            raw_sql("expiresAt > UTC_TIMESTAMP()")
        )  # UTC_TIMESTAMP() is a MySQL function — it's an instruction the database must execute
        .first()
    )
    if not row:
        return False
    if not verify_password(row["value"], code):
        return False
    # Single-use: delete immediately after first successful check
    await db.table("verification").where("id", row["id"]).delete()
    return True
