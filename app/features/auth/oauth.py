"""OAuth 2.0 helpers for Google and GitHub.

State tokens are stored in Redis (TTL 10 min) to prevent CSRF on the callback.
Intent is encoded in the state payload so the callback knows whether this is a
fresh login/signup flow or an account-linking flow for an already-logged-in user.
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

import httpx
from quart import current_app

from app.extensions import get_redis

_STATE_TTL = 600  # 10 minutes

# ── Google ────────────────────────────────────────────────────────────────────

_GOOGLE_AUTH_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"  # google authorization endpoint
)
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # google token endpoint
_GOOGLE_USERINFO_URL = (
    "https://www.googleapis.com/oauth2/v2/userinfo"  # google userinfo endpoint
)

# ── GitHub ────────────────────────────────────────────────────────────────────

_GITHUB_AUTH_URL = (
    "https://github.com/login/oauth/authorize"  # github authorization endpoint
)
_GITHUB_TOKEN_URL = (
    "https://github.com/login/oauth/access_token"  # github token endpoint
)
_GITHUB_USERINFO_URL = "https://api.github.com/user"  # github userinfo endpoint
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"  # github emails endpoint


# ── State helpers ─────────────────────────────────────────────────────────────


# before sending the user to Google, we create a state token -- a random unguessable string
# and save it in redis for 10 minutes along with what we are doing: {"provider": "google", "intent": "login"}
# we check this ticket to prove the request really started on our site
async def create_oauth_state(
    provider: str, intent: str, user_id: str | None = None
) -> str:
    """
    Create a CSRF-proof state token and store the metadata in Redis.

    The problem before: Google redirects back to your callback URL like:
        https://yoursite.com/google/callback?code=ABC123

    Your callback URL just accepts whatever code arrives. It has no memory of who started the login.
    So attacker can abuse this: the attacker starts a login themselves and gets to the point where Google
    hands out a code for the attacker's own account.

    Instead of using that code, the attacker captures it and plants it in a link or hidden auto-submitting page
    The attacker tricks a logged-in victim into visiting that link (email, malicious page, image tag, etc.)

    Now the attacker can log into the victim's account on your site using his own Google
    credentials. The victim never knowingly did anything. That's the CSRF: a request the victim
    didn't intend, riding on the victim's browser/session.

    The key weakness is that the callback couldn't tell the difference between
    "a login my site actually started" and "a code an attacker pasted in."

    The state token fixes exactly that gap. It's a secret your server creates at the start and checks at the end,
    so the callback can verify the flow genuinely began on your site.
    """

    state = secrets.token_urlsafe(32)
    payload: dict = {"provider": provider, "intent": intent}
    if user_id:
        payload["user_id"] = user_id
    await get_redis().setex(f"oauth_state:{state}", _STATE_TTL, json.dumps(payload))
    return state


# delete the state in Redis immediately so the same callback URL can never be replayed a second time
async def consume_oauth_state(state: str) -> dict | None:
    """Look up and delete the state — returns None if missing/expired."""
    redis = get_redis()
    key = f"oauth_state:{state}"
    raw = await redis.get(key)
    if not raw:
        return None
    await redis.delete(key)
    return json.loads(raw)


# ── Google ────────────────────────────────────────────────────────────────────

"""
google_auth_url(state)` then builds Google's login page URL, attaching our app's `client_id`,
the page we want Google to return to (`redirect_uri`), and the `state` token.
"""


def google_auth_url(state: str) -> str:
    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": f"{current_app.config['APP_URL']}/auth/google/callback",
        "response_type": "code",  # request a code from the Google (a short-lived voucher that means "this specific person just authenticated with us")
        "scope": "openid email profile",  # OpenID Connect (you get an ID token proving who the user is), email and profile request their email addresses and basic profile info
        "state": state,
        "access_type": "offline",  # asks google for refresh tokens to get new access tokens
        "prompt": "select_account",  # forces google to show the account-picker every time
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"  # /auth/google/callback?code=XXXX&state=YYYY


async def google_exchange_code(code: str) -> dict:
    """Exchange auth code for user info. Returns a normalised user dict."""
    redirect_uri = f"{current_app.config['APP_URL']}/auth/google/callback"
    # creats an async HTTP client (httpx) for making outbound requests to Google
    async with httpx.AsyncClient() as client:
        # exchange the auth code for an access token and refresh token
        # a POST request to Google's token endpoint with the auth code and client credentials
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,  # the same voucher you are redeeming
                "client_id": current_app.config[
                    "GOOGLE_CLIENT_ID"
                ],  # your app's public identifier
                "client_secret": current_app.config[
                    "GOOGLE_CLIENT_SECRET"
                ],  # the secret password only your server knows
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",  # proves continuity with the original request
            },
            timeout=10,
        )
        token_resp.raise_for_status()  # raises an exception if the request was not successful
        tokens = token_resp.json()  # parse Google's JSON response into a Python dict

        # a GET request to Google's userinfo endpoint with the access token to get the user's information
        info_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            # Bearer <token> is the authorization header, containing the access token
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10,
        )
        info_resp.raise_for_status()
        info = info_resp.json()

    return {
        "id": info["id"],
        "email": info["email"],
        "name": info.get("name", ""),
        "image": info.get("picture"),
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
    }


# ── GitHub ────────────────────────────────────────────────────────────────────


def github_auth_url(state: str) -> str:
    params = {
        "client_id": current_app.config["GITHUB_CLIENT_ID"],
        "redirect_uri": f"{current_app.config['APP_URL']}/auth/github/callback",
        # what you're requesting permission for. read:user allows access to the user's profile,
        # user:email allows access to the user's email
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{_GITHUB_AUTH_URL}?{urlencode(params)}"


async def github_exchange_code(code: str) -> dict:
    """Exchange auth code for user info. Returns a normalised user dict."""
    redirect_uri = f"{current_app.config['APP_URL']}/auth/github/callback"
    """
    GitHub's token endpoint, by default, replies in a URL-encoded format (access_token=xxx&scope=yyy),
    not JSON. We need to parse the response manually.
    """
    headers_json = {"Accept": "application/json"}  # tells Github to return JSON instead
    headers_gh = {
        "Accept": "application/vnd.github.v3+json"
    }  # GitHub's recommended Accept value for its API calls (user/email endpoints)

    # exchange the auth code for an access token
    # POST to GitHub's token endpoint, sending the Accept header to request JSON response
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _GITHUB_TOKEN_URL,
            headers=headers_json,
            data={
                "client_id": current_app.config["GITHUB_CLIENT_ID"],
                "client_secret": current_app.config["GITHUB_CLIENT_SECRET"],
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        access_token = tokens["access_token"]
        auth_header = {"Authorization": f"Bearer {access_token}", **headers_gh}

        user_resp = await client.get(
            _GITHUB_USERINFO_URL, headers=auth_header, timeout=10
        )
        user_resp.raise_for_status()
        # use the token to fetch the user's profile
        info = user_resp.json()

        email = info.get("email")
        # Github may return None here even though you asked for the user:email scope,
        # because users can mark their email private. So, we need fallback to fetch the hidden email
        if not email:
            # fetch the user's emails from the GitHub's dedicated emails endpoint
            emails_resp = await client.get(
                _GITHUB_EMAILS_URL, headers=auth_header, timeout=10
            )
            emails_resp.raise_for_status()
            # GitHub returns a list of user's email addresses.
            # next(..) finds the first email that is both primary and verified, if any
            primary = next(
                (
                    e
                    for e in emails_resp.json()
                    if e.get("primary") and e.get("verified")
                ),
                None,
            )
            # if a qualifying email was found, pull its address; otherwise leave email as None
            email = primary["email"] if primary else None

    return {
        "id": str(info["id"]),
        "email": email,
        "name": info.get("name") or info.get("login", ""),
        "image": info.get("avatar_url"),
        "access_token": access_token,
        "refresh_token": None,
    }
