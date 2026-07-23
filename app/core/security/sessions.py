"""Server-side sessions, backed by the `session` table."""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, Response, g, request, url_for

from app.core.db.orm import db, raw_sql
from app.core.security.htmx import redirect_or_htmx
from app.core.security.org_permissions import get_org_visible_nav_keys
from app.core.security.organization_gate import needs_organization_onboarding
from app.core.security.permissions import user_has_any_role
from app.core.utils.ids import new_id

SESSION_COOKIE = "session_token"
SESSION_TTL = timedelta(days=30)


async def create_session(user_id: str, ip: str | None, user_agent: str | None) -> str:
    """Start a new session for a user: make a random token, save a session row, and return the token (the caller then puts it in a cookie)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_TTL

    await db.table("session").create(
        {
            "id": new_id(),
            "expiresAt": expires_at,
            "token": token,
            "ipAddress": ip,
            "userAgent": user_agent,
            "userId": user_id,
        }
    )
    await db.table("user").where("id", user_id).patch({"lastLoginAt": datetime.now(timezone.utc)})
    return token


async def get_user_id_for_token(token: str) -> str | None:
    """Given a token, return the user id it belongs to — but ONLY if the session is still valid (not expired)."""
    row = await (
        db.table("session").where("token", token).where_raw(raw_sql("expiresAt > UTC_TIMESTAMP()")).first()
    )
    return row["userId"] if row else None


async def delete_session(token: str) -> None:
    """Delete a session (used on logout). After this, the token no longer identifies anyone."""
    await db.table("session").where("token", token).delete()


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session cookie to an outgoing response so the browser stores the token."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="Lax",
        secure=False,
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie from the browser (used on logout, alongside delete_session)."""
    response.delete_cookie(SESSION_COOKIE)


def apply_session_loader(app: Flask) -> None:
    """Wire up automatic session loading."""

    @app.before_request
    async def load_session() -> None:
        token = request.cookies.get(SESSION_COOKIE)
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
            g.current_user_name = user["name"] if user else None
            g.current_user_image = user["image"] if user else None
            g.is_platform_staff = await user_has_any_role(g.user_id)
            g.org_locked = await needs_organization_onboarding(g.user_id)
            g.org_nav_keys = await get_org_visible_nav_keys(g.user_id)


PENDING_2FA_COOKIE = "pending_2fa"
_PENDING_2FA_TTL = 300


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
    """A decorator that protects a route: if no one is logged in, redirect to the login page; otherwise run the route as normal."""

    @wraps(view)
    async def wrapped(*args, **kwargs):
        if g.user_id is None:
            destination = request.path
            if request.query_string:
                destination += "?" + request.query_string.decode()
            return redirect_or_htmx(url_for("auth.login", next=destination))
        return await view(*args, **kwargs)

    return wrapped
