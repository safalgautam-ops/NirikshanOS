"""Admin Users business logic — thin glue over repository.py."""

from __future__ import annotations

from app.features.users import repository


class UserError(Exception):
    """A user-visible users-admin failure."""


"""
    fetch one page of users, filtered by search item, a role filter, and a status filter
    collect their IDs into user_ids
    fetch their top roles and current role IDs from the repository
    annotate each user with their top role and current role IDs
"""


async def get_users_page(*, search: str, role_id: str, status: str, page: int):
    """One page of users, each annotated with `.top_role` (dict or None)."""
    result = await repository.list_users(search=search, role_id=role_id, status=status, page=page)
    user_ids = [u["id"] for u in result.items]
    top_roles = await repository.get_top_roles_for_users(user_ids)
    role_ids_by_user = await repository.get_role_ids_for_users(user_ids)
    for user in result.items:
        user["top_role"] = top_roles.get(user["id"])
        user["current_role_ids"] = role_ids_by_user.get(user["id"], set())
    return result


async def toggle_user_active(user_id: str, is_active: bool, *, requested_by: str) -> None:
    if user_id == requested_by:
        raise UserError("You can't deactivate your own account.")
    await repository.set_user_active(user_id, is_active)


async def update_user_roles(user_id: str, role_ids: list[str], assigned_by: str) -> None:
    if user_id == assigned_by:
        raise UserError("You can't change your own role assignments.")
    await repository.replace_user_roles(user_id, role_ids, assigned_by)


async def delete_user(user_id: str, *, requested_by: str) -> None:
    if user_id == requested_by:
        raise UserError("You can't delete your own account.")
    await repository.delete_user(user_id)
