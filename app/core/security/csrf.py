"""CSRF protection - double-submit cookie pattern.
Recall the CSRF attack from before: a malicious page makes your browser fire an authenticated request to your-app.com,
and the browser helpfully attaches your cookies. The session's samesite="Lax" blunts a lot of this,
but the double-submit pattern is a second, independent layer — and crucially,
it works even when there's no session at all (login and register forms, where you're not logged in yet).

The core trick: read vs. send
The whole pattern hinges on one asymmetry in how browsers treat cookies, and the docstring states it exactly:
A cross-site page can make the browser send a cookie automatically (that's the CSRF problem).
But a cross-site page cannot read the cookie's value — the same-origin policy walls off evil.com from your-app.com's cookies.

So the defense is: require every state-changing request to prove it could read the cookie,
by echoing the cookie's value back in a second place. The legitimate form (served by your-app.com)
can read the cookie and copy it into a hidden field. A forged form on evil.com can trigger the cookie
to be sent, but can't read it to fill in the matching field. The server then checks: does the value in the
cookie equal the value in the form field?

Legitimate request: both present, both equal → allowed.
Forged request: cookie sent automatically, but the field is missing or wrong
(evil.com couldn't read the cookie to copy it) → rejected.

It's called "double-submit" because the same token is submitted twice — once via the cookie (automatic)
and once via the form field (manual) — and they must match.
"""

import hmac
import secrets

from quart import Quart, Response, abort, g, request

# they happen to share the string "csrf_token", but they name two different things --
# one is where the cookie lives, the other is where the form value lives.
CSRF_COOKIE = "csrf_token"
CSRF_FIELD = "csrf_token"

# HTTP methods that don't change state -- they only read.
# These shouldn't modify anything, so they don't need CSRF protection.
# Everything else (POST, PUT, PATCH, DELETE) should have CSRF protection.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# a tiny helper to expose the CSRF token to templates as a Jinja global to drop the token into a hidden field.
def csrf_token() -> str:
    """Exposed to templates as a Jinja global - {{ csrf_token() }}."""
    return g.csrf_token


def apply_csrf_protection(app: Quart) -> None:
    @app.before_request
    async def check_csrf() -> None:
        # Reuse the existing cookie if present(sent by browser), otherwise mint a new token with secrets
        # for this request (persisted by persist_csrf_cookie below).
        g.csrf_token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        # enforcement only for state-changing requests (POST, PUT, PATCH, DELETE)
        if request.method not in SAFE_METHODS:
            form = await request.form
            # Form submissions send the token in a hidden field.
            # JSON API calls (Content-Type: application/json) send it in
            # the X-CSRF-Token request header instead.
            submitted = (
                form.get(CSRF_FIELD, "")
                or request.headers.get("X-CSRF-Token", "")
            )
            cookie_token = request.cookies.get(
                CSRF_COOKIE
            )  # token from the cookie sent by the browser
            # compare_digest: constant-time comparison, avoids leaking the
            # token byte-by-byte through response-time differences.
            # if there is no cookie token or the submitted token doesn't match, reject the request.
            if not cookie_token or not hmac.compare_digest(cookie_token, submitted):
                # the more leading characters that match, the longer == runs.
                # the time it takes quickly reveals how much of the front matched.
                # so, instead of guessing the entire token at once, they crack it one character at a time
                # the timing differences between correct and incorrect guesses reveal how close they are to the actual token.
                # this turns the timing attack into a brute-force attack, where they guess each character until they find the correct one.
                # hmac.compare_digest compares the two values in constant time, so the time it takes to run doesn't depend on how many characters match.
                # it does not bail out early if the token is incorrect, so the attacker must guess each character until they find the correct one.
                abort(403)

    # the CSRF token is persisted in a cookie so it can be used across requests.
    @app.after_request
    async def persist_csrf_cookie(response: Response) -> Response:
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE,
                g.csrf_token,
                httponly=False,  # must be readable by JS for double-submit cookie pattern
                samesite="Strict",
                secure=False,  # set True behind TLS in production
            )
        return response

    # Makes {{ csrf_token() }} available in every template without an import.
    app.jinja_env.globals["csrf_token"] = csrf_token
