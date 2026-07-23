"""TOTP (time-based one-time password) helpers for 2FA."""

from __future__ import annotations

import base64
import io
import json
import secrets

import pyotp
import qrcode

from app.core.utils.passwords import hash_password, verify_password

BACKUP_CODE_COUNT = 10
_ISSUER = "NirikshanOS"

"""
you call this once when a user enables 2FA, store it against their account,
and the same value gets handed to their phone via the QR code.
"""


def generate_secret() -> str:
    return pyotp.random_base32()


"""
builds the provisioning URI (otpauth://) that authenticator apps understand
bundles everything into one string -- otpauth://totp/NirikshanOS:alice@x.com?secret=XXXX&issuer=NirikshanOS
when a phone scans this, it knows everything it needs to generate TOTP codes.

"""


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(email, issuer_name=_ISSUER)


def qr_base64(secret: str, email: str) -> str:
    """Return a base64-encoded PNG of the TOTP QR code."""
    uri = provisioning_uri(secret, email)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def verify_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def generate_backup_codes() -> tuple[list[str], list[str]]:
    """Return (plain_codes, hashed_codes). plain_codes shown once; hashed stored."""
    plain = [secrets.token_hex(4) for _ in range(BACKUP_CODE_COUNT)]
    hashed = [hash_password(c) for c in plain]
    return plain, hashed


def encode_backup_codes(hashed: list[str]) -> str:
    return json.dumps(hashed)


def decode_backup_codes(raw: str) -> list[str]:
    return json.loads(raw)


def consume_backup_code(hashed_codes: list[str], submitted: str) -> tuple[bool, list[str]]:
    """Try to redeem a backup code (single-use). Returns (success, remaining)."""
    cleaned = submitted.strip().lower().replace("-", "").replace(" ", "")
    for i, h in enumerate(hashed_codes):
        if verify_password(h, cleaned):
            return True, hashed_codes[:i] + hashed_codes[i + 1 :]
    return False, hashed_codes
