"""eSewa payment gateway client — HMAC signing/verification and the
server-to-server transaction-status check. No business logic here (that's
app/features/finance/service.py); this module only knows eSewa's wire
format, mirroring how object_storage.py isolates the S3 client from
evidence/service.py.

Every field name, the signature algorithm, and both endpoint pairs below
are copied directly from eSewa's own developer docs
(developer.esewa.com.np/pages/Epay), not guessed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import httpx

from app.config import Config

# Sandbox vs production base URLs - eSewa uses entirely different hosts,
# not just a path prefix.
_FORM_URLS = {
    "sandbox": "https://rc-epay.esewa.com.np/api/epay/main/v2/form",
    "production": "https://epay.esewa.com.np/api/epay/main/v2/form",
}
_STATUS_URLS = {
    "sandbox": "https://rc.esewa.com.np/api/epay/transaction/status/",
    "production": "https://esewa.com.np/api/epay/transaction/status/",
}


def form_url() -> str:
    return _FORM_URLS[Config.ESEWA_ENV]


def _amount_str(value) -> str:
    """eSewa's own docs give "100"/"110" as example amount values, not
    "100.00" - their backend re-derives total_amount from amount + charges
    and compares it against what was signed, so a forced ".00" suffix on a
    whole-number amount makes the client's signed string diverge from
    eSewa's own reconstruction and the payment page rejects it with
    "Invalid payload signature" even though the HMAC math is internally
    correct. Quantize first (still avoids float binary-representation
    artifacts, e.g. Decimal(110.1) != Decimal("110.1")), then strip a
    trailing ".00"/trailing zero so "1490.00" -> "1490" and "24.50" ->
    "24.5", matching eSewa's own formatting exactly. Applied consistently
    everywhere an amount is stringified so the signed value is
    byte-identical to the submitted value."""
    from decimal import Decimal
    quantized = str(Decimal(str(value)).quantize(Decimal("0.01")))
    if "." in quantized:
        quantized = quantized.rstrip("0").rstrip(".")
    return quantized or "0"


def build_signature(*, total_amount, transaction_uuid: str, product_code: str) -> str:
    """HMAC-SHA256, base64-encoded, over
    "total_amount=<value>,transaction_uuid=<value>,product_code=<value>" -
    eSewa signs "field=value" pairs joined by commas, not bare values in
    field order (confirmed by brute-forcing eSewa's own documented example
    against their live sandbox: the bare-value message this function used
    to build was rejected with ES104 "Invalid payload signature", while the
    field=value form was accepted)."""
    message = (
        f"total_amount={_amount_str(total_amount)},"
        f"transaction_uuid={transaction_uuid},"
        f"product_code={product_code}"
    )
    digest = hmac.new(
        Config.ESEWA_SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


def build_payment_form_fields(
    *,
    total_amount,
    transaction_uuid: str,
    success_url: str,
    failure_url: str,
) -> dict[str, str]:
    """Every field the signed HTML form needs. tax/service/delivery are
    always 0 here - NirikshanOS plans have no separate tax/shipping line
    items, so `amount` and `total_amount` are the same discounted price."""
    amount = _amount_str(total_amount)
    signature = build_signature(
        total_amount=total_amount,
        transaction_uuid=transaction_uuid,
        product_code=Config.ESEWA_PRODUCT_CODE,
    )
    return {
        "amount": amount,
        "tax_amount": "0",
        "product_service_charge": "0",
        "product_delivery_charge": "0",
        "total_amount": amount,
        "transaction_uuid": transaction_uuid,
        "product_code": Config.ESEWA_PRODUCT_CODE,
        "success_url": success_url,
        "failure_url": failure_url,
        "signed_field_names": "total_amount,transaction_uuid,product_code",
        "signature": signature,
    }


def verify_callback(raw_base64_payload: str) -> dict[str, Any] | None:
    """Decode eSewa's redirect payload and confirm its signature was
    actually produced with our secret key - the payload travels through the
    user's browser, so it must never be trusted without this check.

    Regenerates the signature over exactly the fields `signed_field_names`
    lists (in that order), formatted the same "field=value" way as the
    outbound request signature (see build_signature) - eSewa signs
    different field sets for the request vs. the callback, so this can't
    hardcode the request's 3-field list. Returns the parsed payload only if
    the signature matches, else None.
    """
    try:
        decoded = base64.b64decode(raw_base64_payload)
        payload = json.loads(decoded)
    except Exception:
        return None

    signed_field_names = payload.get("signed_field_names", "")
    provided_signature = payload.get("signature", "")
    if not signed_field_names or not provided_signature:
        return None

    fields = signed_field_names.split(",")
    try:
        message = ",".join(f"{f}={payload[f]}" for f in fields)
    except KeyError:
        return None

    expected_digest = hmac.new(
        Config.ESEWA_SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(expected_digest).decode()

    if not hmac.compare_digest(expected_signature, provided_signature):
        return None
    return payload


async def check_transaction_status(*, transaction_uuid: str, total_amount) -> str:
    """Server-to-server confirmation, independent of the browser callback -
    eSewa's own docs recommend this as defense in depth. Returns one of:
    COMPLETE, PENDING, FULL_REFUND, PARTIAL_REFUND, AMBIGUOUS, NOT_FOUND,
    CANCELED. Any transport/parse failure is treated as PENDING (fail
    closed - never treated as COMPLETE) rather than raising, so a flaky
    network call can't accidentally read as a confirmed payment."""
    params = {
        "product_code": Config.ESEWA_PRODUCT_CODE,
        "total_amount": _amount_str(total_amount),
        "transaction_uuid": transaction_uuid,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_STATUS_URLS[Config.ESEWA_ENV], params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("status", "PENDING")
    except Exception:
        return "PENDING"
