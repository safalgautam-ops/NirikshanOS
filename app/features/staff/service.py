"""Admin Staff business logic."""

from __future__ import annotations

import secrets

from app.core.email.client import send_staff_credentials_email
from app.core.utils.passwords import hash_password
from app.features.staff import repository


class StaffError(Exception):
    """A user-visible staff failure."""


async def get_staff_list(*, search: str = "") -> list:
    return await repository.list_staff(search=search)


async def get_staff_member(member_id: str):
    return await repository.get_staff_member(member_id)


# normalization of inputs, validation with user-safe errors, audit fields
async def create_staff(
    *, name: str, email: str, role_ids: list[str], created_by: str
) -> str:
    name = name.strip()
    email = email.strip().lower()
    if not name:
        raise StaffError("Name is required.")
    if not email:
        raise StaffError("Email is required.")
    existing = await repository.get_user_by_email(email)
    if existing:
        raise StaffError("A user with that email already exists.")

    # Cryptographically random, not derived from name/email — a password
    # guessable from public-ish identity fields would defeat the point.
    temp_password = secrets.token_urlsafe(12)
    member_id = await repository.create_staff_user(
        name=name, email=email, password_hash=hash_password(temp_password)
    )
    if role_ids:
        await repository.replace_staff_roles(
            member_id, role_ids, assigned_by=created_by
        )
    await send_staff_credentials_email(to=email, name=name, password=temp_password)
    return member_id


async def save_staff(
    member_id: str, *, name: str, role_ids: list[str], saved_by: str
) -> None:
    name = name.strip()
    if not name:
        raise StaffError("Name is required.")
    await repository.update_staff_user(member_id, name=name)
    await repository.replace_staff_roles(member_id, role_ids, assigned_by=saved_by)


async def get_all_roles() -> list:
    return await repository.get_all_roles()
