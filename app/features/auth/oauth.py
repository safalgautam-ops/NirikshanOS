"""OAuth 2.0 helpers for Google and GitHub."""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

import httpx
from flask import current_app

from app.extensions import get_redis

_STATE_TTL = 600

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USERINFO_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


async def create_oauth_state(provider: str, intent: str, user_id: str | None = None) -> str:
    """Create a CSRF-proof state token and store the metadata in Redis."""

    state = secrets.token_urlsafe(32)
    payload: dict = {"provider": provider, "intent": intent}
    if user_id:
        payload["user_id"] = user_id
    await get_redis().setex(f"oauth_state:{state}", _STATE_TTL, json.dumps(payload))
    return state


async def consume_oauth_state(state: str) -> dict | None:
    """Look up and delete the state — returns None if missing/expired."""
    redis = get_redis()
    key = f"oauth_state:{state}"
    raw = await redis.get(key)
    if not raw:
        return None
    await redis.delete(key)
    return json.loads(raw)


"""
google_auth_url(state)` then builds Google's login page URL, attaching our app's `client_id`,
the page we want Google to return to (`redirect_uri`), and the `state` token.
"""


def google_auth_url(state: str) -> str:
    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": f"{current_app.config['APP_URL']}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def google_exchange_code(code: str) -> dict:
    """Exchange auth code for user info. Returns a normalised user dict."""
    redirect_uri = f"{current_app.config['APP_URL']}/auth/google/callback"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": current_app.config["GOOGLE_CLIENT_ID"],
                "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        info_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10,
        )
        info_resp.raise_for_status()
        info = info_resp.json()

    return {
        "id": info["id"],
        "email": info["email"],
        "email_verified": info.get("verified_email", False),
        "name": info.get("name", ""),
        "image": info.get("picture"),
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
    }


def github_auth_url(state: str) -> str:
    params = {
        "client_id": current_app.config["GITHUB_CLIENT_ID"],
        "redirect_uri": f"{current_app.config['APP_URL']}/auth/github/callback",
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
    headers_json = {"Accept": "application/json"}
    headers_gh = {"Accept": "application/vnd.github.v3+json"}

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

        user_resp = await client.get(_GITHUB_USERINFO_URL, headers=auth_header, timeout=10)
        user_resp.raise_for_status()
        info = user_resp.json()

        email = info.get("email")
        if not email:
            emails_resp = await client.get(_GITHUB_EMAILS_URL, headers=auth_header, timeout=10)
            emails_resp.raise_for_status()
            primary = next(
                (e for e in emails_resp.json() if e.get("primary") and e.get("verified")),
                None,
            )
            email = primary["email"] if primary else None

    return {
        "id": str(info["id"]),
        "email": email,
        "email_verified": email is not None,
        "name": info.get("name") or info.get("login", ""),
        "image": info.get("avatar_url"),
        "access_token": access_token,
        "refresh_token": None,
    }
