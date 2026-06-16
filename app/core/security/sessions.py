"""Server-side sessions, backed by the `session` table.

This is the opaque token session pattern, and the docstring nails the security property:
the browser holds nothing but a random string. There's no signed payload, no user ID, no expiry baked into the cookie
— just a meaningless 43-character token. Everything that means anything
(who you are, when the session dies) lives in the session table. Because the token carries no information,
the client can't tamper with it to escalate privileges or extend its own expiry;
the worst it can do is send a token that doesn't match any row, which reads as "not logged in."

This contrasts with the stateless approach (e.g. JWTs), where the cookie itself contains signed claims and
the server trusts the signature without a DB lookup.

This design pays a DB read on every request in exchange for instant, reliable revocation
(delete_session and the session is dead immediately) and zero forgery surface.
For an auth system that's usually the right call.

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

# name of the cookie -- the label the token is saved under in the browser
# The word "session_token" is only the label you'd see in browser devtools.
# The real secret is the token stored inside the cookie, not this name.
SESSION_COOKIE = "session_token"
# how long a session lasts: 30 days
# timedelta is Python's way of representing a duration (spans 30 days)
# it feeds two different places that need to agree:
# Server side: expires_at = datetime.now(timezone.utc) + SESSION_TTL → the expiresAt written to the DB row.
# Browser side: max_age=int(SESSION_TTL.total_seconds()) → how long the browser keeps the cookie
# (.total_seconds() converts the 30-day span to a raw number of seconds,
# ~2,592,000, because max_age wants seconds).
SESSION_TTL = timedelta(days=30)


# issue a new session at login
async def create_session(user_id: str, ip: str | None, user_agent: str | None) -> str:
    # secrets.token_urlsafe: cryptographically random, not guessable - (~43 char URL-safe string: 32 random bytes + base64url-encodes them).
    # this is the only thing(this token is the entire secret) the browser gets, so it must be unforgeable.
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
        (token,),  # the database driver expects the parameters as a sequence (a tuple)
    )
    return row[0] if row else None


async def delete_session(token: str) -> None:
    await execute("DELETE FROM session WHERE token = %s", (token,))


# once the session cookie is set, the browser attaches it to every request going to your site
# the browser attaches the cookie based on where the request is going, not where it came from.
# so if a request is heading to our app, the browser includes my session cookie -- even if some other website triggered that request.
# that's called CSRF: a malicious site making your browser send authenticated requests to a site you're logged into, riding on your cookie
def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,  # not readable from JS (the cookie is invisible to document.cookie) - mitigates token theft via XSS
        # Among Strict, Lax, None; Strict blocks the cookie on all cross-site requests(clicking link the friend sent you, you land on the page logged out)
        # Lax is the middle ground: top-level navigation (you click a link, or type the URL): cookie is sent
        # Background / embedded requests (a form POST, an image load, a script fetch), a page fires without you navigating: cookie is withheld
        samesite="Lax",
        # secure=True tells the browser to send the cookie only over HTTPS, which would break local development
        # over http://localhost. The instruction to flip it to True behind TLS in production is important since plain HTTP the token travels in cleartext
        secure=False,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def apply_session_loader(app: Quart) -> None:
    @app.before_request
    async def load_session() -> None:
        token = request.cookies.get(SESSION_COOKIE)
        g.user_id = await get_user_id_for_token(token) if token else None


# decorator wrapping a route to redirect to othe login page if g.user_id is NONE
def login_required(view):
    @wraps(
        view
    )  # preserves the wrapped function's name and metadata because Quart/Flask identify endpoints by function name
    # wrapped is the route - Quart has registered it as the handler for some URL.
    # So when a request matches that URL, Quart calls wrapped, and Quart is what fills in the arguments, pulled from the URL's dynamic segments.
    # a request to /posts/42/edit makes Quart called wrapped(post_id=42)
    async def wrapped(*args, **kwargs):
        if g.user_id is None:
            return redirect(url_for("auth.login"))
        return await view(*args, **kwargs)

    return wrapped
