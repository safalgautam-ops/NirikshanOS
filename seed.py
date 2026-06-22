"""Dev-only seed script: creates a default System Admin user.

Run inside the web container (so it picks up the same DB_* env vars the app
uses):

    docker compose exec web python seed.py

Idempotent - safe to run more than once. If the user already exists it's
left alone (password isn't reset); if they don't yet hold System Admin,
that gets granted.
"""

from __future__ import annotations

import asyncio

from app.config import Config
from app.core.db.orm import db
from app.core.db.pool import close_pool, init_pool
from app.core.utils.passwords import hash_password
from app.features.auth.repository import create_user_with_password

ADMIN_NAME = "Dev Admin"
ADMIN_EMAIL = "deadeye@gmail.com"
ADMIN_PASSWORD = "deadeye@123"


async def seed_system_admin() -> None:
    role = await db.table("roles").where("name", "System Admin").first()
    if not role:
        raise RuntimeError("System Admin role not found - run the migrations first.")

    user = await db.table("user").where("email", ADMIN_EMAIL).first()
    if user:
        print(f"User already exists: {ADMIN_EMAIL}")
        user_id = user["id"]
    else:
        user_id = await create_user_with_password(
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            is_active=True,
            email_verified=True,
        )
        print(f"Created user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")

    holds_role = (
        await db.table("user_roles")
        .where("user_id", user_id)
        .where("role_id", role["id"])
        .first()
    )
    if holds_role:
        print("Already holds System Admin.")
        return

    # assigned_by=None - this is a system/seed assignment, not done by another user.
    await db.table("user_roles").create(
        {"user_id": user_id, "role_id": role["id"], "assigned_by": None}
    )
    print(f"Granted System Admin to {ADMIN_EMAIL}.")


async def main() -> None:
    await init_pool(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        db=Config.DB_NAME,
    )
    try:
        await seed_system_admin()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
