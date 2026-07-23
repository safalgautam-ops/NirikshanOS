"""Provisions one real, verified user (+ an approved org they own) directly in the real dev database, for the E2E tier to log into via a real browser."""

import asyncio
import json
import sys
import uuid

sys.path.insert(0, "/app")

from app.core.db.pool import close_pool, init_pool
from app.core.utils.passwords import hash_password
from app.config import Config


async def main() -> None:
    await init_pool(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        db=Config.DB_NAME,
    )
    from app.features.auth.repository import create_user_with_password
    from app.features.organizations.repository import add_member, create_organization

    suffix = uuid.uuid4().hex[:10]
    email = f"e2e-test-{suffix}@example.test"
    password = "correct horse battery staple"

    user_id = await create_user_with_password(
        name="E2E Test User",
        email=email,
        password_hash=hash_password(password),
        is_active=True,
        email_verified=True,
    )
    org_id = await create_organization(
        name=f"E2E Test Org {suffix}",
        slug=f"e2e-test-org-{suffix}",
        description="",
        status="active",
        created_by=user_id,
        verification_status="approved",
    )
    await add_member(org_id, user_id)

    await close_pool()
    print(json.dumps({"email": email, "password": password, "user_id": user_id, "org_id": org_id}))


if __name__ == "__main__":
    asyncio.run(main())
