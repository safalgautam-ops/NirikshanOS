"""Server-side sessions, backed by the `session` table.

The browser holds nothing but an opaque random token. Everything that
matters (who the user is, when the session dies) lives in MySQL. There's
nothing for the client to forge or tamper with.

Why this module uses orm.py instead of raw execute/fetchone
-----------------------------------------------------------
All DB writes and reads go through the generic ORM helpers (db_insert,
db_delete, db_get) with SESSION_SCHEMA as the schema. This is the same
approach as repository.py: pass a table name + schema dict instead of
building SQL by hand.

The one exception: db_get's `extra_condition` param.
  db_get("session", ..., extra_condition="expiresAt > UTC_TIMESTAMP()")

This is needed because the expiry check compares a column to a DB function
call — not to a Python value — which the WHERE dict ({column: value}) can't
express. extra_condition is a hardcoded string from our own code, not
user input, so it's safe to include verbatim in the SQL.

apply_session_loader() runs before every request and sets g.user_id
(or None), so every route can check "am I logged in?" via g.user_id
without repeating the cookie-read + DB-lookup logic itself.
"""

import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from quart import Quart, Response, g, redirect, request, url_for

from app.core.db.fields import DateTimeField, StringField
from app.core.db.orm import Schema, db_delete, db_get, db_insert
from app.core.utils.ids import new_id

# The label this cookie is stored under in the browser.
# The security comes from the random VALUE inside the cookie, not this name.
SESSION_COOKIE = "session_token"

# 30 days expressed as a Python timedelta. Used in two places:
#   expires_at = now + SESSION_TTL  → stored in the DB row
#   max_age = SESSION_TTL.total_seconds() → tells the browser when to drop the cookie
# Both must agree so the browser and the DB expire the session at the same time.
SESSION_TTL = timedelta(days=30)

# Schema for the `session` table.
# Passed to db_insert / db_get / db_delete so they know which columns are
# valid, what types to validate, and which columns to SELECT.
SESSION_SCHEMA: Schema = {
    "id": StringField(max_length=191, required=False),
    # expiresAt is a datetime object in Python; asyncmy sends it as a
    # MySQL TIMESTAMP. DateTimeField validates it's really a datetime.
    "expiresAt": DateTimeField(),
    "token": StringField(max_length=255),
    "ipAddress": StringField(max_length=255, required=False),
    "userAgent": StringField(max_length=65535, required=False),
    "userId": StringField(max_length=191),
}


async def create_session(user_id: str, ip: str | None, user_agent: str | None) -> str:
    # secrets.token_urlsafe(32) produces 43 URL-safe characters of
    # cryptographic randomness. This token is the entire secret — the
    # browser gets it, and we look it up on every request.
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_TTL

    # db_insert validates every value against SESSION_SCHEMA before writing.
    # Columns not passed (updatedAt etc.) use MySQL's DEFAULT values.
    await db_insert("session", SESSION_SCHEMA, {
        "id": new_id(),
        "expiresAt": expires_at,
        "token": token,
        "ipAddress": ip,
        "userAgent": user_agent,
        "userId": user_id,
    })
    return token


async def get_user_id_for_token(token: str) -> str | None:
    # extra_condition "expiresAt > UTC_TIMESTAMP()" adds an expiry check
    # that the WHERE dict can't express (column vs DB function, not column
    # vs Python value). It's a hardcoded string — never user input.
    row = await db_get(
        "session",
        SESSION_SCHEMA,
        where={"token": token},
        extra_condition="expiresAt > UTC_TIMESTAMP()",
    )
    return row["userId"] if row else None


async def delete_session(token: str) -> None:
    # db_delete whitelists "token" against SESSION_SCHEMA before it
    # touches the SQL — no raw string building here.
    await db_delete("session", SESSION_SCHEMA, where={"token": token})


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        # httponly: the cookie is invisible to JavaScript (document.cookie).
        # This means XSS can't steal the session token even if it runs.
        httponly=True,
        # samesite="Lax": the browser sends the cookie on top-level
        # navigation (you click a link to the site) but withholds it on
        # background cross-site requests (image loads, AJAX from evil.com).
        # This is a second layer on top of CSRF token protection.
        samesite="Lax",
        # secure=False for local HTTP development. Behind a TLS-terminating
        # reverse proxy in production, set this to True — otherwise the
        # session token travels in cleartext.
        secure=False,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def apply_session_loader(app: Quart) -> None:
    # Runs before every request. Reads the session cookie → looks up the
    # user id in MySQL → stores it in g.user_id for the rest of the request.
    # g (the "request context global") lives exactly one request — it's
    # created fresh each time and thrown away when the response is sent.
    @app.before_request
    async def load_session() -> None:
        token = request.cookies.get(SESSION_COOKIE)
        g.user_id = await get_user_id_for_token(token) if token else None


def login_required(view):
    # A decorator: wraps a route function so that unauthenticated requests
    # are redirected to the login page before the route body ever runs.
    # @wraps preserves the original function's name — Quart uses the name
    # to identify route endpoints (e.g. url_for("dashboard")).
    @wraps(view)
    async def wrapped(*args, **kwargs):
        if g.user_id is None:
            return redirect(url_for("auth.login"))
        return await view(*args, **kwargs)

    return wrapped
