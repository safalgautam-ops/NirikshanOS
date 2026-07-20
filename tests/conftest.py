"""Shared fixtures for the whole test suite.

Forces every test process to point at the disposable nirikshan_test database
and a separate Redis keyspace (db 1, not 0) BEFORE `app` is ever imported -
Config reads these as class attributes at import time, so this must happen
first, above every other import in this file.
"""
from __future__ import annotations

import os

os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "nirikshan_test")
os.environ["REDIS_URL"] = os.environ.get(
    "TEST_REDIS_URL",
    os.environ.get("REDIS_URL", "redis://redis:6379/0").rsplit("/", 1)[0] + "/1",
)

import uuid
from typing import Any

import pytest

from app import create_app
from app.core.utils.passwords import hash_password


@pytest.fixture(scope="session")
def app():
    """One Flask app for the whole test session - mirrors production: one
    process, one persistent AsyncRuntime loop, one DB pool."""
    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture(scope="session")
def run_async(app):
    """Run an awaitable on the app's own persistent event loop - lets
    integration tests call async service/repository functions directly,
    without a second, conflicting event loop or DB pool (see
    AsyncFlask.run_async in app/core/async_runtime.py)."""
    def _run(awaitable):
        return app.run_async(awaitable)
    return _run


@pytest.fixture(autouse=True)
def _flush_test_redis(app, run_async):
    """Every test starts against an empty Redis keyspace (db 1, isolated
    from dev's db 0 - see the REDIS_URL override above). Without this,
    rate-limit counters (login attempts share one IP-keyed counter) would
    accumulate across unrelated tests and start failing later ones with a
    429 that has nothing to do with what that test is actually checking."""
    from app.extensions import get_redis

    async def _flush():
        app._ensure_started()
        r = get_redis()
        await r.flushdb()

    run_async(_flush())
    yield


@pytest.fixture()
def client(app):
    """A fresh Flask test client per test. The first request through any
    client (whichever test runs first) lazily triggers the app's real
    startup sequence (DB pool, Redis, permission-registry sync) via
    AsyncFlask's before_request hook - identical to a real deployment."""
    return app.test_client()


def unique(prefix: str = "t") -> str:
    """A short, collision-free identifier for anything with a uniqueness
    constraint (email, slug, ...) so tests never collide with each other or
    with a previous run against the same disposable database."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def make_user(run_async):
    """Creates a real, fully-active user row (bypassing the email-OTP
    activation flow, which is out of this suite's scope) and returns its id
    + the plaintext password, so a test can log in with it."""
    from app.features.auth.repository import create_user_with_password

    created_ids: list[str] = []

    def _make(*, name: str = "Test User", password: str = "correct horse battery staple") -> dict[str, Any]:
        email = f"{unique('user')}@example.test"
        user_id = run_async(
            create_user_with_password(
                name=name,
                email=email,
                password_hash=hash_password(password),
                is_active=True,
                email_verified=True,
            )
        )
        created_ids.append(user_id)
        return {"id": user_id, "email": email, "password": password, "name": name}

    yield _make


@pytest.fixture()
def make_org(run_async):
    """Creates a real, approved organization directly via the repository -
    bypassing the onboarding wizard's document-upload steps, which are out
    of this suite's scope."""
    from app.features.organizations.repository import create_organization

    def _make(*, created_by: str, name: str = "Test Org") -> dict[str, Any]:
        slug = unique("org")
        org_id = run_async(
            create_organization(
                name=name,
                slug=slug,
                description="",
                status="active",
                created_by=created_by,
                verification_status="approved",
            )
        )
        return {"id": org_id, "slug": slug}

    return _make


@pytest.fixture()
def grant_permission(run_async):
    """Creates a fresh role holding exactly one platform permission
    (resource.action, e.g. "plans.view") and assigns it to a user - the
    real path a permission actually reaches a user through (report §5.4)."""
    from app.core.db.orm import db
    from app.features.rbac.repository import add_member, create_role, set_role_permissions

    def _grant(user_id: str, resource: str, action: str) -> str:
        perm_row = run_async(
            db.table("permissions").where("resource", resource).where("action", action).first()
        )
        assert perm_row, f"permission {resource}.{action} is not registered - has the app started up yet?"
        role_id = run_async(create_role(name=unique("role")))
        run_async(set_role_permissions(role_id, [perm_row["id"]]))
        run_async(add_member(role_id, user_id, user_id))
        return role_id

    return _grant
