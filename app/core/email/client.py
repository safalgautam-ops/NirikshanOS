"""Transactional email via Resend REST API.

In production it sends real email through Resend,
but in local development — where you haven't configured a mail provider —
it just prints the email to your terminal.
"""

# makes type hints lazy so we don't need to import types we don't use (evaluated at runtime)
from __future__ import annotations

import httpx
from flask import current_app, render_template


async def send_email(*, to: str, subject: str, html: str) -> None:
    api_key = current_app.config["RESEND_API_KEY"]

    if not api_key:
        print(f"\n[EMAIL] To: {to}  Subject: {subject}\n{html}\n")
        return

    from_addr = current_app.config["RESEND_FROM_EMAIL"]
    # open an async HTTP client (auto-closes via async with)
    async with httpx.AsyncClient() as client:
        # post to the Resend API to send the email
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"from": from_addr, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        # raise an error if the response status is not 200 (OK)
        resp.raise_for_status()


async def send_activation_email(*, to: str, name: str, code: str) -> None:
    html = render_template("email/activate.html", name=name, code=code)
    await send_email(to=to, subject="Activate your NirikshanOS account", html=html)


async def send_reset_email(*, to: str, code: str) -> None:
    html = render_template("email/reset_password.html", code=code)
    await send_email(to=to, subject="Reset your NirikshanOS password", html=html)


async def send_staff_credentials_email(*, to: str, name: str, password: str) -> None:
    html = render_template(
        "email/staff_credentials.html", name=name, email=to, password=password
    )
    await send_email(to=to, subject="Your NirikshanOS account", html=html)
