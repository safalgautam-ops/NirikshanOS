"""Server-side sessions, backed by the `session` table.

The browser only ever holds an opaque random token in a cookie. All
session state - which user, when it expires - lives in MySQL (the
`session` table from migrations/001.initial_schema.sql, the same table
BetterAuth itself would write to). Every request looks the token up
against that table; there is nothing for the client to forge.

apply_session_loader() runs before every request and sets `g.user_id`
(or None), so routes/templates can check "am I logged in" without each
one re-reading the cookie and querying the DB.
"""

import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from quart import Quart, Response, g, redirect, request, url_for

from app.core.db.pool import execute, fetchone
from app.core.utils.ids import new_id

SESSION_COOKIE = "session_token"
SESSION_TTL = timedelta(days=30)


async def create_session(user_id: str, ip: str | None, user_agent: str | None) -> str:
    # secrets.token_urlsafe: cryptographically random, not guessable -
    # this is the only thing the browser gets, so it must be unforgeable.
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    await execute(
        "INSERT INTO session (id, expiresAt, token, ipAddress, userAgent, userId) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (new_id(), expires_at, token, ip, user_agent, user_id),
    )
    return token


async def get_user_id_for_token(token: str) -> str | None:
    # expiresAt > now: an expired row is treated as if it doesn't exist.
    row = await fetchone(
        "SELECT userId FROM session WHERE token = %s AND expiresAt > UTC_TIMESTAMP()",
        (token,),
    )
    return row[0] if row else None


async def delete_session(token: str) -> None:
    await execute("DELETE FROM session WHERE token = %s", (token,))


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,  # not readable from JS - mitigates token theft via XSS
        samesite="Lax",
        # secure=True drops the cookie over plain HTTP, which is how this
        # runs locally. Behind a TLS-terminating reverse proxy in
        # production, switch this to True.
        secure=False,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def apply_session_loader(app: Quart) -> None:
    @app.before_request
    async def load_session() -> None:
        token = request.cookies.get(SESSION_COOKIE)
        g.user_id = await get_user_id_for_token(token) if token else None


def login_required(view):
    @wraps(view)
    async def wrapped(*args, **kwargs):
        if g.user_id is None:
            return redirect(url_for("auth.login"))
        return await view(*args, **kwargs)

    return wrapped
