"""CSRF protection - double-submit cookie pattern.

A random token is stored in a cookie and must be echoed back as a hidden
form field on every state-changing request. A cross-site form can make
the browser send the cookie automatically, but it can't *read* the
cookie to copy its value into the hidden field - so a forged request's
field won't match the cookie, and is rejected.

This works even for logged-out users (login/register forms), unlike a
token tied to a session, since the cookie is set on first GET regardless
of auth state.
"""

import hmac
import secrets

from quart import Quart, Response, abort, g, request

CSRF_COOKIE = "csrf_token"
CSRF_FIELD = "csrf_token"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token() -> str:
    """Exposed to templates as a Jinja global - {{ csrf_token() }}."""
    return g.csrf_token


def apply_csrf_protection(app: Quart) -> None:
    @app.before_request
    async def check_csrf() -> None:
        # Reuse the existing cookie if present, otherwise mint a new token
        # for this request (persisted by persist_csrf_cookie below).
        g.csrf_token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)

        if request.method not in SAFE_METHODS:
            form = await request.form
            submitted = form.get(CSRF_FIELD, "")
            cookie_token = request.cookies.get(CSRF_COOKIE)
            # compare_digest: constant-time comparison, avoids leaking the
            # token byte-by-byte through response-time differences.
            if not cookie_token or not hmac.compare_digest(cookie_token, submitted):
                abort(403)

    @app.after_request
    async def persist_csrf_cookie(response: Response) -> Response:
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE,
                g.csrf_token,
                httponly=True,
                samesite="Strict",
                secure=False,  # see sessions.py - set True behind TLS
            )
        return response

    # Makes {{ csrf_token() }} available in every template without an import.
    app.jinja_env.globals["csrf_token"] = csrf_token
