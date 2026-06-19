"""WebAuthn / Passkey server-side helpers.

Registration: server generates options → browser calls
navigator.credentials.create() → client sends result here → we store
the credential.

Authentication: server generates challenge → browser calls
navigator.credentials.get() → client sends assertion here → we verify
using the stored public key and update the counter.

Challenges are stored in Redis with a 5-minute TTL so they survive the
round-trip to the browser without keeping DB state.
"""

from __future__ import annotations

import json

import webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from quart import current_app

from app.extensions import get_redis

_CHALLENGE_TTL = 300  # 5 minutes


async def _save_challenge(key: str, challenge: bytes) -> None:
    await get_redis().setex(key, _CHALLENGE_TTL, bytes_to_base64url(challenge))


async def _load_challenge(key: str) -> bytes | None:
    val = await get_redis().get(key)
    if not val:
        return None
    await get_redis().delete(key)
    return base64url_to_bytes(val)


# ── Registration ──────────────────────────────────────────────────────────────

async def begin_registration(
    user_id: str,
    user_email: str,
    user_name: str,
    existing_credentials: list[dict],
) -> dict:
    """Generate registration options and cache the challenge. Returns JSON-safe dict."""
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credentialID"]))
        for c in existing_credentials
    ]
    options = webauthn.generate_registration_options(
        rp_id=current_app.config["WEBAUTHN_RP_ID"],
        rp_name=current_app.config["WEBAUTHN_RP_NAME"],
        user_id=user_id.encode(),
        user_name=user_email,
        user_display_name=user_name,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    await _save_challenge(f"pk_reg:{user_id}", options.challenge)
    return json.loads(webauthn.options_to_json(options))


async def complete_registration(user_id: str, credential: dict) -> dict:
    """Verify the browser's registration response. Returns data to store in DB."""
    challenge = await _load_challenge(f"pk_reg:{user_id}")
    if not challenge:
        raise ValueError("Registration challenge expired.")

    verified = webauthn.verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=current_app.config["WEBAUTHN_RP_ID"],
        expected_origin=current_app.config["WEBAUTHN_RP_ORIGIN"],
        require_user_verification=False,
    )
    return {
        "credentialID": bytes_to_base64url(verified.credential_id),
        "publicKey": bytes_to_base64url(verified.credential_public_key),
        "counter": verified.sign_count,
        "backedUp": verified.credential_backed_up,
        "deviceType": verified.credential_device_type.value,
        "transports": ",".join(t.value for t in (verified.credential_transports or [])),
        "aaguid": str(verified.aaguid) if verified.aaguid else None,
    }


# ── Authentication ────────────────────────────────────────────────────────────

async def begin_authentication(challenge_key: str, allowed_credentials: list[dict]) -> dict:
    """Generate authentication options (discoverable = empty allow_credentials)."""
    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credentialID"]))
        for c in allowed_credentials
    ]
    options = webauthn.generate_authentication_options(
        rp_id=current_app.config["WEBAUTHN_RP_ID"],
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    await _save_challenge(f"pk_auth:{challenge_key}", options.challenge)
    return json.loads(webauthn.options_to_json(options))


async def complete_authentication(
    challenge_key: str,
    credential: dict,
    stored: dict,
) -> int:
    """Verify the browser's assertion. Returns the new sign counter."""
    challenge = await _load_challenge(f"pk_auth:{challenge_key}")
    if not challenge:
        raise ValueError("Authentication challenge expired.")

    verified = webauthn.verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=current_app.config["WEBAUTHN_RP_ID"],
        expected_origin=current_app.config["WEBAUTHN_RP_ORIGIN"],
        credential_public_key=base64url_to_bytes(stored["publicKey"]),
        credential_current_sign_count=stored["counter"],
        require_user_verification=False,
    )
    return verified.new_sign_count
