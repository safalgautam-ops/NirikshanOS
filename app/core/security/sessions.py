"""
Server-side sessions, backed by the `session` table.

What "server-side sessions" means here:
- When a user logs in, we create a row in the `session` table and generate a random
  secret string called a TOKEN.
- We send that token to the browser as a cookie.
- On every later request, the browser sends the cookie back; we look the token up in
  the table to figure out WHO the user is.
The actual identity lives in the database; the cookie only carries the lookup key (token).
This is safer than storing user info directly in the cookie, because a token reveals nothing
on its own and can be revoked (deleted) server-side at any time.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

# Quart is an async web framework (like Flask, but async). These are its request/response tools:
#   Quart    -> the app type
#   Response -> an outgoing HTTP response (where we set/clear cookies)
#   g        -> a per-request scratchpad; data put here is available during that one request
#   redirect -> send the browser to another URL
#   request  -> the incoming HTTP request (where we read cookies)
#   url_for  -> build a URL from a route name
from quart import Quart, Response, g, redirect, request, url_for

from app.core.db.orm import db, raw_sql  # the query builder + safe raw-SQL wrapper
from app.core.security.organization_gate import needs_organization_onboarding
from app.core.security.org_permissions import get_org_visible_nav_keys
from app.core.security.permissions import user_has_any_role
from app.core.utils.ids import new_id  # generates unique ids for new rows

SESSION_COOKIE = "session_token"  # the name of the cookie we store the token in
SESSION_TTL = timedelta(
    days=30
)  # how long a session stays valid (TTL = "time to live")


async def create_session(user_id: str, ip: str | None, user_agent: str | None) -> str:
    """
    Start a new session for a user: make a random token, save a session row, and
    return the token (the caller then puts it in a cookie). ip/user_agent are stored
    for auditing/security (e.g. "where was this session created from").
    """
    # token_urlsafe(32) -> a random, URL-safe, unguessable string (the session secret).
    token = secrets.token_urlsafe(32)
    # Expiry = right now (in UTC) + the time-to-live. Using UTC avoids timezone bugs.
    expires_at = datetime.now(timezone.utc) + SESSION_TTL

    # Insert the session row.
    await db.table("session").create(
        {
            "id": new_id(),  # unique id for the row itself
            "expiresAt": expires_at,  # when this session becomes invalid
            "token": token,  # the lookup key sent to the browser
            "ipAddress": ip,  # client IP (may be None)
            "userAgent": user_agent,  # client browser/app string (may be None)
            "userId": user_id,  # which user this session belongs to
        }
    )
    await db.table("user").where("id", user_id).patch(
        {"lastLoginAt": datetime.now(timezone.utc)}
    )
    return token  # caller will store this in the cookie


async def get_user_id_for_token(token: str) -> str | None:
    """
    Given a token, return the user id it belongs to — but ONLY if the session is still
    valid (not expired). Returns None if the token is unknown or expired.
    """
    row = await (
        db.table("session")
        .where("token", token)  # find the session with this token
        # Only accept it if it hasn't expired. UTC_TIMESTAMP() is a SQL function for "now in UTC",
        # which the normal .where() can't express — so we use the deliberate raw_sql() escape hatch.
        .where_raw(raw_sql("expiresAt > UTC_TIMESTAMP()"))
        .first()  # first matching row, or None
    )
    # If we found a valid session, return its userId; otherwise return None.
    return row["userId"] if row else None


async def delete_session(token: str) -> None:
    """Delete a session (used on logout). After this, the token no longer identifies anyone."""
    await db.table("session").where("token", token).delete()


def set_session_cookie(response: Response, token: str) -> None:
    """
    Attach the session cookie to an outgoing response so the browser stores the token.
    The flags here are important security settings:
    """
    response.set_cookie(
        SESSION_COOKIE,  # cookie name
        token,  # cookie value (the session token)
        max_age=int(
            SESSION_TTL.total_seconds()
        ),  # how long the browser keeps it (in seconds)
        httponly=True,  # JavaScript on the page CANNOT read this cookie -> protects against XSS theft
        samesite="Lax",  # don't send the cookie on most cross-site requests -> helps prevent CSRF
        secure=False,  # if True, only sent over HTTPS. False here likely for local dev;
        # this should be True in production so the token never travels over plain HTTP.
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie from the browser (used on logout, alongside delete_session)."""
    response.delete_cookie(SESSION_COOKIE)


def apply_session_loader(app: Quart) -> None:
    """
    Wire up automatic session loading. Call this once at startup with the app.
    It registers a function that runs BEFORE every request, so each request already
    knows who the current user is (if anyone) before any route code runs.
    """

    # @app.before_request registers this to run automatically before each incoming request.
    @app.before_request
    async def load_session() -> None:
        # Read the token from the incoming request's cookies (None if the cookie isn't there).
        token = request.cookies.get(SESSION_COOKIE)
        # Look up the user id for that token, and stash it on `g` (the per-request scratchpad)
        # so any route handler this request can read g.user_id. If no token, it's None.
        g.user_id = await get_user_id_for_token(token) if token else None

        g.must_change_password = False
        g.org_locked = False
        g.org_nav_keys = []
        g.is_platform_staff = False
        g.current_user_name = None
        g.current_user_image = None
        if g.user_id is not None:
            user = (
                await db.table("user")
                .where("id", g.user_id)
                .select("must_change_password", "name", "image")
                .first()
            )
            g.must_change_password = bool(user and user["must_change_password"])
            # Display-only fields the topbar's user menu reads directly
            # (g is injected into every template context) - avoids every
            # route that renders the topbar needing to fetch and pass the
            # user explicitly, same rationale as g.org_locked below.
            g.current_user_name = user["name"] if user else None
            g.current_user_image = user["image"] if user else None
            # Holds any system role - platform staff. Drives the
            # sidebar: staff never see organization onboarding UI at all (see
            # sidebar.html and onboarding/routes.py's blueprint guard), since
            # they manage every org from /admin/organizations instead of
            # being a tenant member themselves. Checked by role membership,
            # not by whether any granted permission currently exists - a
            # staff role with zero permissions assigned is still staff.
            g.is_platform_staff = await user_has_any_role(g.user_id)
            # Drives the sidebar's lock icons - templates read g.org_locked
            # directly (Quart injects g into every template context).
            g.org_locked = await needs_organization_onboarding(g.user_id)
            # Drives the sidebar's "Your Organization" group - same g-injection
            # pattern as g.org_locked above, read directly by sidebar.html.
            g.org_nav_keys = await get_org_visible_nav_keys(g.user_id)


PENDING_2FA_COOKIE = "pending_2fa"
_PENDING_2FA_TTL = 300  # 5 minutes


def create_pending_2fa_token(user_id: str, secret_key: str) -> str:
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}"
    sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_pending_2fa_token(value: str, secret_key: str) -> str | None:
    try:
        parts = value.split(".", 2)
        if len(parts) != 3:
            return None
        user_id, ts_str, sig = parts
        payload = f"{user_id}.{ts_str}"
        expected = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts_str) > _PENDING_2FA_TTL:
            return None
        return user_id
    except Exception:
        return None


def login_required(view):
    """
    A decorator that protects a route: if no one is logged in, redirect to the login page;
    otherwise run the route as normal. Use it like:

        @login_required
        async def dashboard(): ...
    """

    # @wraps(view) keeps the original function's name and docstring on the wrapper,
    # so debugging/route-registration still sees the real view name.
    @wraps(view)
    async def wrapped(*args, **kwargs):
        # g.user_id was set earlier by load_session(). None means "not logged in".
        if g.user_id is None:
            # Send the visitor to login, but remember where they were headed
            # (e.g. an invite link's GET /onboarding/join?code=...) so login()
            # can send them back there instead of always landing on dashboard.
            destination = request.path
            if request.query_string:
                destination += "?" + request.query_string.decode()
            return redirect(url_for("auth.login", next=destination))
        # Logged in -> run the actual route handler and return its result.
        return await view(*args, **kwargs)

    return wrapped  # the decorator returns the wrapped version to replace the original view
