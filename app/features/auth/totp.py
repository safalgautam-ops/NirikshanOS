"""TOTP (time-based one-time password) helpers for 2FA.

Uses pyotp for code generation/verification and qrcode+Pillow for the
setup QR image.  Backup codes are argon2-hashed before storage so that
a DB dump doesn't expose usable codes.
"""

from __future__ import annotations

import base64
import io  # in-memory binary stream for QR code generation
import json
import secrets  # cryptographically strong randomness

import pyotp  # time-based one-time password generation/verification
import qrcode  # QR code generation

from app.core.utils.passwords import hash_password, verify_password

BACKUP_CODE_COUNT = 10
_ISSUER = "NirikshanOS"

"""
you call this once when a user enables 2FA, store it against their account,
and the same value gets handed to their phone via the QR code.
"""


def generate_secret() -> str:
    return pyotp.random_base32()  # new random totp secret (base-32 encoded)


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
    # io.BytesIO() is an in-memory file — instead of saving the PNG to disk, you save it into a memory buffer. (Avoids touching the filesystem, which is cleaner and faster.)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    # base64 encodes the PNG data into a string that can be embedded in HTML or sent over the network.
    return base64.b64encode(buf.getvalue()).decode()


# the login time check
def verify_code(secret: str, code: str) -> bool:
    # valid_window=1 tells pyotp to also accept the code from the immediately previous and next 30-second windows, not just the current one.
    # a code is valid for roughly a 90-second span instead of a strict 30.
    # this is to account for clock skew and network latency.
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def generate_backup_codes() -> tuple[list[str], list[str]]:
    """Return (plain_codes, hashed_codes). plain_codes shown once; hashed stored."""
    plain = [
        secrets.token_hex(4) for _ in range(BACKUP_CODE_COUNT)
    ]  # 10 random codes in readable form (gives an 8-character hex string)
    hashed = [hash_password(c) for c in plain]  # hash each code to store securely
    return plain, hashed


# since the database column stores the backup codes as a single text field
# need to encode the hashed codes into a JSON string before storing
def encode_backup_codes(hashed: list[str]) -> str:
    return json.dumps(hashed)


# decode the JSON string back into a list of hashed codes when retrieving from the database
def decode_backup_codes(raw: str) -> list[str]:
    return json.loads(raw)


def consume_backup_code(
    hashed_codes: list[str], submitted: str
) -> tuple[bool, list[str]]:
    """Try to redeem a backup code (single-use). Returns (success, remaining)."""
    cleaned = submitted.strip().lower().replace("-", "").replace(" ", "")
    for i, h in enumerate(hashed_codes):
        if verify_password(h, cleaned):
            return True, hashed_codes[:i] + hashed_codes[i + 1 :]
    return False, hashed_codes
