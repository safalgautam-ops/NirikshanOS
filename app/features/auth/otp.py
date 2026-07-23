"""OTP (one-time password) generation and verification."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.core.db.orm import db, raw_sql
from app.core.utils.ids import new_id
from app.core.utils.passwords import hash_password, verify_password

_TTL = timedelta(minutes=10)
_LENGTH = 6


def _identifier(email: str, purpose: str) -> str:
    return f"{email}:{purpose}"


async def create_otp(email: str, purpose: str) -> str:
    code = "".join(secrets.choice("0123456789") for _ in range(_LENGTH))
    identifier = _identifier(email, purpose)

    await db.table("verification").where("identifier", identifier).delete()
    await db.table("verification").create(
        {
            "id": new_id(),
            "identifier": identifier,
            "value": hash_password(code),
            "expiresAt": datetime.now(timezone.utc) + _TTL,
        }
    )
    return code


async def verify_otp(email: str, purpose: str, code: str) -> bool:
    identifier = _identifier(email, purpose)
    row = await (
        db.table("verification")
        .where("identifier", identifier)
        .where_raw(raw_sql("expiresAt > UTC_TIMESTAMP()"))
        .first()
    )
    if not row:
        return False
    if not verify_password(row["value"], code):
        return False
    await db.table("verification").where("id", row["id"]).delete()
    return True
