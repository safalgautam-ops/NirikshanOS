"""CSRF protection - double-submit cookie pattern."""

import hmac
import secrets

from flask import Flask, Response, abort, g, request

CSRF_COOKIE = "csrf_token"
CSRF_FIELD = "csrf_token"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token() -> str:
    """Exposed to templates as a Jinja global - {{ csrf_token() }}."""
    return g.csrf_token


def apply_csrf_protection(app: Flask) -> None:
    @app.before_request
    async def check_csrf() -> None:
        g.csrf_token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        if request.method not in SAFE_METHODS:
            form = request.form
            submitted = form.get(CSRF_FIELD, "") or request.headers.get("X-CSRF-Token", "")
            cookie_token = request.cookies.get(CSRF_COOKIE)
            if not cookie_token or not hmac.compare_digest(cookie_token, submitted):
                abort(403)

    @app.after_request
    async def persist_csrf_cookie(response: Response) -> Response:
        token = getattr(g, "csrf_token", None)
        if token and not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE,
                token,
                httponly=False,
                samesite="Strict",
                secure=False,
            )
        return response

    app.jinja_env.globals["csrf_token"] = csrf_token
